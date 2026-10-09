"""precheck.py — 立花本番的前一晚预检（立花实盘缺口 B5：TA-08 / C-04 / TA-09 / OPS-07 / OPS-09；只读：不下单、不改账本）。

为什么：交付書面未読、密钥 / 认证失效、时钟、IP、API 版本停用……以前都要到 07:40 的正式运行才发现，那时只剩 1 个多小时、
交付書面又只能在电脑上读。前一晚 20:00 先登录一次，有问题当晚就通知。
LaunchAgent com.qbreak.precheck（周日〜周四 20:00 JST = 下一个交易日的前一晚；scripts/install_launchd_precheck.sh，
install_launchd_live_u.sh tachibana 时一起装、uninstall / 切回模拟时一起卸）→ scripts/liveu.sh precheck → run.py live-precheck。
  ① 只在装了立花本番时做（LaunchAgents 里有 com.qbreak.liveu.morning；没有 → 打印、退出 0；--force 照做）；
     要检查的交易日（20:00 → 明天；05:30〜07:30 → 今天）休市 → 不登录（每次登录立花都会发一封登录通知邮件，官方关不掉 → 一天只登一次）；
     03:30〜05:30 立花闭局（登录不了）、交易日 07:30 之后（执行器自己会登录）→ 不预检。
  ② 拿账本的运行锁（执行器在跑 → 等它结束，免得登录把它的会话踢掉）→ 登录 → 取余力 → 登出（finally）。
     失败 → 原因（错误码对照表 C-15 已经附在错误文字里；HTTP 404 / 应答不是 JSON → 「可能是旧 API 版本已停用」）。
  ③ 登录应答里的两个预告（C-04 / TA-09）：交付書面的更新预定日（sUpdateInformWebDocument）、API 新版本的发布日
     （sUpdateInformAPISpecFunction）→ 预告记录 {值, 第一次看到的日子, 当时代码用的 API 版本段}（结果文件；执行器把它并进账本
     book["tachibana_notices"]）。提醒（reminders）：
       • 交付書面：更新预定日在 5 个交易日以内（含当天）→ 每次预检提醒（同一天同样的文字只通知一次）；
       • API 新版本：只要代码用的版本还没比「第一次看到预告时的版本」新，就每次提醒 —— 发布日之前看到的，发布日之后升 ★
         （旧版本停用前要更新），直到代码更新到新版本；日子 ≤ 代码现在用的版本的发布日（brokers/tachibana.py API_RELEASES）→ 不提醒；
         第一次看到时已经过了的日子 → 只提醒、不升 ★；用户确认「核对过、不用更新」→ --ack-api 日子（ack_api）清掉这个提醒。
  ④ 上线门槛（live_gate.check）：和上一次预检比，「门槛」「准备」里新出现的 ★ → 通知一次（OPS-09：定期自检）。
  ⑤ 结果写 out/precheck_tachibana.json（at、ok、reasons、notices、gate_stars …；面板顶部显示今天 / 昨晚没通过的原因与提醒）。
通知（手机 / Mac）：没通过 / 有提醒 / 新出现 ★ 时才发；同一天同样的文字只发一次（qbreak/notify_seen.py）；文字里不带本机路径与网址。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import paths
from .calendar_jp import JST, is_trading_day, next_trading_day, now_jst
from .utils import atomic_write_text, setup_logging

log = setup_logging("precheck")

LABEL = "com.qbreak.precheck"
LIVE_PLIST = "com.qbreak.liveu.morning"
KEY = "tachibana_notices"                    # 预告记录：账本 / 结果文件里的键
DOC_DAYS = 5                                 # 交付書面的更新预定日在几个交易日以内就提醒
TAG = "tachibana"
CLOSED_FROM, CLOSED_UNTIL = dt.time(3, 30), dt.time(5, 30)    # 立花闭局（登录不了）
MORNING_FROM = dt.time(7, 30)                # 交易日这之后执行器自己会登录：不预检
LOCK_WAIT_S = 600.0
ESHITEN = "https://www.e-shiten.jp/"


def result_path() -> Path:
    return paths.out_dir() / f"precheck_{TAG}.json"


def installed(agents) -> bool:
    """装了立花本番（07:40 的 com.qbreak.liveu.morning）？"""
    return (Path(agents) / f"{LIVE_PLIST}.plist").exists()


def last_result() -> dict:
    """上一次预检的结果文件（没有 / 读坏 → {}）。"""
    from .run_status import peek_json
    return peek_json(result_path()) or {}


# ────────── 预告记录（C-04 / TA-09）──────────
def ymd(v) -> str:
    """登录应答里的日期（YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD，可能带时刻）→ "YYYY-MM-DD"；不是日期 → ""。"""
    s = re.sub(r"\D", "", str(v or ""))
    if len(s) < 8:
        return ""
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])).isoformat()
    except ValueError:
        return ""


def ver(api: str) -> tuple[int, int] | None:
    """API 版本段（e_api_v4r10）→ (4, 10)；认不出 → None。"""
    m = re.search(r"v(\d+)r(\d+)", str(api or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def record(notices: dict | None, *, next_release: str = "", doc_update: str = "", api: str = "",
           today: dt.date | None = None) -> dict:
    """登录应答里的两个预告 → 预告记录 {"next_release" / "doc_update": {value, first_seen, last_seen, api}}。
    同样的值：只更新 last_seen；新的值：重新记（first_seen = 今天、api = 现在代码用的版本段）；空值：不清掉旧的记录
    （发布日之后应答里可能就没有了，提醒照样要持续到代码更新）。"""
    today = today or now_jst().date()
    n = {k: dict(v) for k, v in (notices or {}).items() if isinstance(v, dict)}
    for key, raw in (("next_release", next_release), ("doc_update", doc_update)):
        v = ymd(raw)
        if not v:
            continue
        cur = n.get(key) or {}
        if cur.get("value") == v:
            n[key] = {**cur, "last_seen": today.isoformat()}
        else:
            n[key] = {"value": v, "first_seen": today.isoformat(), "last_seen": today.isoformat(), "api": str(api or "")}
    return n


def merge(*records: dict | None) -> dict:
    """几份预告记录（账本的、预检结果文件的）合在一起：同一个键取最近看到的那份（last_seen 大的；一样 → 前面的）。
    同一个预告（值一样）：第一次看到的日子取早的；用户确认过（acked，--ack-api）的标记只要有一份有就留着。"""
    out: dict = {}
    for r in records:
        for k, v in (r or {}).items():
            if not isinstance(v, dict) or not v.get("value"):
                continue
            cur = out.get(k)
            if cur is None or str(v.get("last_seen") or "") > str(cur.get("last_seen") or ""):
                new = dict(v)
                if cur is not None and cur.get("value") == v.get("value"):
                    _same(new, cur)
                out[k] = new
            elif cur.get("value") == v.get("value"):
                _same(cur, v)
    return out


def _same(dst: dict, other: dict) -> None:
    """同一个预告的两份记录：first_seen 取早的；acked（等于这个值时）留着。"""
    if str(other.get("first_seen") or "9") < str(dst.get("first_seen") or "9"):
        dst["first_seen"] = other["first_seen"]
    if other.get("acked") == dst.get("value") and dst.get("acked") != dst.get("value"):
        dst["acked"] = other["acked"]
        if other.get("acked_on"):
            dst["acked_on"] = other["acked_on"]


def _trading_days_until(today: dt.date, day: dt.date) -> int:
    """today 之后到 day（含）有几个交易日；day ≤ today → 0。"""
    n, d = 0, today
    while d < day:
        d = next_trading_day(d)
        if d <= day:
            n += 1
    return n


def version_resolved(rec: dict, api_now: str) -> bool:
    """代码用的版本已经比「第一次看到预告时的版本」新了 → 这个预告处理完了。版本认不出 → 只在两边文字不同时算处理完。"""
    old, new = ver(rec.get("api") or ""), ver(api_now)
    if old is None or new is None:
        return bool(api_now) and bool(rec.get("api")) and api_now != rec.get("api")
    return new > old


def api_released(api_now: str) -> str:
    """代码现在用的 API 版本的发布日（brokers/tachibana.py 的 API_RELEASES；不知道 → ""）。"""
    from .brokers.tachibana import API_RELEASES
    return str(API_RELEASES.get(str(api_now or ""), "") or "")


def release_handled(rec: dict, api_now: str) -> bool:
    """「新版本发布日」的预告已经不用提醒：代码已经换到比第一次看到时新的版本；或者这个日子 ≤ 代码现在用的版本的发布日
    （应答里显示的就是代码已经在用的这一版 / 更早的）；或者用户确认过这个日子（--ack-api，acked == 值）。"""
    v = str(rec.get("value") or "")
    rel = api_released(api_now)
    return (version_resolved(rec, api_now) or (bool(rel) and bool(v) and v <= rel)
            or (bool(v) and rec.get("acked") == v))


def reminders(notices: dict | None, api_now: str, today: dt.date | None = None) -> list[str]:
    """预告记录 → 要提醒的文字（页面 / 日志 / 通知 / 面板）。「★」开头 = 要动手（通知升 warn）。
    API 新版本：发布日之前看到的 → 发布日之前是提醒、过了发布日升 ★（一直到代码更新到新版本 / 用户确认）；
    第一次看到时发布日已经过了（这个字段在发布之后显示什么不确定：可能是代码已经在用的那一版，或不改版本段的仕様变更）→ 只是提醒、不升 ★。"""
    today = today or now_jst().date()
    out = []
    nr = (notices or {}).get("next_release") or {}
    if nr.get("value") and not release_handled(nr, api_now):
        v = nr["value"]
        ack = f"核对完不用更新 → 你在对话里确认后 Claude 运行 bash scripts/liveu.sh precheck --ack-api {v}（只清这个提醒）"
        if v >= today.isoformat():
            out.append(f"立花通知：e支店 API 新版本 {v} 发布（代码现在用 {api_now or '?'}；发布之后旧版本会在一段时间后停用）："
                       "在 Mac 对话里问「立花 API 要更新吗」，按官方仕様書核对 tachibana_spec.json 与适配器；" + ack)
        elif str(nr.get("first_seen") or "9") <= v:
            out.append(f"★ 立花 e支店 API 新版本已于 {v} 发布，代码还在用 {api_now or '?'}：旧版本停用之前要更新"
                       "（停用后登录会失败、执行器全自动停摆）——在 Mac 对话里问「立花 API 要更新吗」"
                       "（这个提醒一直到代码更新到新版本；" + ack + "）")
        else:
            out.append(f"立花通知：登录应答里的 API 发布日 {v}（第一次看到时已经过了；代码现在用 {api_now or '?'}）："
                       "可能是不改版本的仕様变更 → 在 Mac 对话里问「立花 API 要更新吗」核对；" + ack)
    du = (notices or {}).get("doc_update") or {}
    if du.get("value"):
        try:
            d = dt.date.fromisoformat(du["value"])
        except ValueError:
            d = None
        if d is not None and d >= today and _trading_days_until(today, d) <= DOC_DAYS:
            out.append(f"★ 立花的交付書面 {d.isoformat()} 更新：更新之后要先在电脑上登录 e支店网站读完新书面"
                       "（手机网站 / API 读不了）；没读完的那天 API 登录不上、执行器全自动停摆 → 更新当天早上 07:40 之前读完")
    return out


def ack_api(value: str, now: dt.datetime | None = None) -> tuple[int, str]:
    """用户确认「API 新版本的预告核对过了、不用更新」（在对话里明确说了才运行）：预检结果文件里这个预告记 acked = 值
    （执行器下一次运行时并进账本；之后同一个日子不再提醒；出现新的日子照常提醒）。不登录、不下单、不改账本。
    → (退出码, 说明)：0 = 记了 / 已经记过；2 = 日期认不出 / 没有这个预告。"""
    now = now or now_jst()
    v = ymd(value)
    if not v:
        return 2, f"日期认不出：{value!r}（写 YYYY-MM-DD，和提醒里的发布日一样）"
    book = paths.state_dir() / f"live_unified_{TAG}.json"
    prev = last_result()
    try:
        book_d = json.loads(book.read_text(encoding="utf-8")) if book.exists() else {}
    except (OSError, ValueError):
        book_d = {}
    notes = merge(prev.get(KEY), book_d.get(KEY) if isinstance(book_d, dict) else None)
    nr = notes.get("next_release") or {}
    if nr.get("value") != v:
        have = nr.get("value") or "没有"
        return 2, f"现在记着的 API 新版本发布日是 {have}，不是 {v}：没有改（提醒照旧）"
    if nr.get("acked") == v:
        return 0, f"API 新版本发布日 {v} 的提醒以前已经确认过（不再提醒）"
    nr = {**nr, "acked": v, "acked_on": now.date().isoformat()}
    notes["next_release"] = nr
    rec = dict(prev)
    rec[KEY] = notes
    rec["acked_api"] = {"value": v, "at": now.isoformat(timespec="seconds")}
    rec["notices"] = [n for n in rec.get("notices") or [] if v not in str(n) or "API" not in str(n)]
    atomic_write_text(result_path(), json.dumps(rec, ensure_ascii=False, indent=1))
    return 0, (f"已确认：API 新版本发布日 {v} 的提醒不再出现（记在预检结果文件；执行器下一次运行时并进账本）。"
               "出现新的发布日照常提醒")


# ────────── 什么时候做 ──────────
def target_day(now: dt.datetime) -> tuple[dt.date | None, str]:
    """要预检的交易日：(日子, "") 或 (None, 为什么不做)。20:00 的定时任务 → 明天；Mac 睡着、醒来补跑在早上 05:30〜07:30 → 今天。"""
    now = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    t, today = now.time(), now.date()
    if CLOSED_FROM <= t < CLOSED_UNTIL:
        return None, "现在是 03:30〜05:30（立花闭局，登录不了）：不预检（07:40 的执行器照常运行）"
    if t < CLOSED_FROM:                                       # 半夜：检查的是今天（夜里过了 0 点）
        day = today
    elif t < MORNING_FROM:
        day = today
    elif is_trading_day(today) and t < dt.time(15, 30):
        return None, "交易日 07:30〜15:30：执行器自己会登录（今天早上的运行就是检查）→ 不预检"
    else:
        day = today + dt.timedelta(days=1)
    if not is_trading_day(day):
        return None, (f"{day.isoformat()} 休市：不用预检（下一个交易日 {next_trading_day(day).isoformat()} 的前一晚再做；"
                      "每次登录立花都会发一封登录通知邮件 → 一天只登一次）")
    return day, ""


# ────────── 登录检查 ──────────
def _why(e: BaseException) -> str:
    """失败的原因（去掉网址与本机路径）；HTTP 404 / 应答不是 JSON → 加「可能是旧 API 版本已停用」（TA-09）。"""
    import urllib.error
    from .run_status import scrub
    txt = scrub(f"{type(e).__name__}：{e}") or type(e).__name__
    if (isinstance(e, urllib.error.HTTPError) and getattr(e, "code", None) in (404, 410)) or isinstance(e, json.JSONDecodeError):
        txt += ("（立花的应答是 HTTP 404 / 不是 JSON：可能是这个 API 版本已经停用 → 看立花的公告 "
                f"{ESHITEN}，在 Mac 对话里问「立花 API 要更新吗」）")
    return txt


def login_check(broker) -> tuple[list[str], dict]:
    """登录 → 取余力 → 登出（finally；失败忽略）。→ (没通过的原因, {next_release, doc_update})。不下单、不改账本。"""
    reasons: list[str] = []
    try:
        broker.login()
        broker.cash()
    except Exception as e:                                    # noqa: BLE001
        reasons.append(f"立花登录 / 取余力失败：{_why(e)}")
    finally:
        try:
            broker.logout()
        except Exception:                                     # noqa: BLE001
            pass
    return reasons, {"next_release": str(getattr(broker, "next_release", "") or ""),
                     "doc_update": str(getattr(broker, "doc_update", "") or "")}


def gate_stars(items: list[dict]) -> list[str]:
    """上线门槛的检查结果里「门槛」「准备」没通过的项（名字；★）。"""
    return sorted({f"{it.get('group')}：{it.get('name')}" for it in items or []
                   if it.get("group") in ("门槛", "准备") and it.get("ok") is False})


def compose(reasons: list[str], notices: list[str], new_stars: list[str], target: str) -> tuple[str, str, str]:
    """通知的 (标题, 正文, 级别)。"""
    warn = bool(reasons or new_stars or any(n.startswith("★") for n in notices))
    if reasons:
        title = "qbreak 立花实盘 ★ 前一晚预检没通过"
    elif warn:
        title = "qbreak 立花实盘 ★ 前一晚预检：有要处理的提醒"
    else:
        title = "qbreak 立花实盘 前一晚预检：提醒"
    lines = [f"前一晚预检（{target} 的交易）：" + ("没通过" if reasons else "登录 / 取余力正常")]
    lines += [f"- {r}" for r in reasons]
    if notices:
        lines.append("提醒：")
        lines += [f"- {n}" for n in notices]
    if new_stars:
        lines.append("上线门槛 / 准备里新出现的 ★（全部：bash scripts/liveu.sh gate；只读）：")
        lines += [f"- {s}" for s in new_stars]
    lines.append("（预检只读：登录 → 取余力 → 登出，不下单、不改账本；明天 07:40 的执行器照常运行）")
    return title, "\n".join(lines), "warn" if warn else "info"


def run(agents, *, force: bool = False, now: dt.datetime | None = None, make_broker=None, gate=None,
        send=None, mac=None, lock_wait_s: float = LOCK_WAIT_S) -> int:
    """前一晚预检（run.py live-precheck）。返回 0 = 通过 / 不用做；1 = 没通过；3 = 拿不到运行锁。
    make_broker / gate / send(title, text, level) / mac(title, text)：测试注入（默认：立花本番适配器（只读）/ live_gate.check /
    notify.send / mac_notify）。"""
    from . import notify_seen
    from .brokers.tachibana import api_version
    from .live_unified import ExecutorError, RunLock
    from .run_status import local_paths_out, scrub
    from .versions import code_version
    now = now or now_jst()
    if not force and not installed(agents):
        print(f"立花本番的定时任务没装（{LIVE_PLIST} 不在）：前一晚预检只在立花本番时做（模拟模式不用；--force 照做）")
        return 0
    day, why = target_day(now)
    if day is None and not force:
        print(why)
        return 0
    target = (day or now.date()).isoformat()
    if make_broker is None:
        from .brokers.tachibana import TachibanaBroker

        def make_broker():
            return TachibanaBroker(dry_run=True, require_arm=True)          # 只读：dry_run（万一走到发单也只打印）
    book = paths.state_dir() / f"live_unified_{TAG}.json"
    try:
        lock = RunLock(book.with_suffix(".lock"), wait_s=lock_wait_s).acquire()
    except ExecutorError as e:
        print(f"★ 这次不预检：{e}")
        return 3
    try:
        b = None
        try:
            b = make_broker()
            reasons, ann = login_check(b)
        except Exception as e:                                # noqa: BLE001  建适配器就失败（仕様文件读坏等）
            reasons, ann = [f"立花的适配器建不了：{_why(e)}"], {"next_release": "", "doc_update": ""}
        spec = getattr(b, "spec", None)
        api_now = api_version(getattr(spec, "base_live", "")) if spec is not None else ""
        prev = last_result()
        book_d = {}
        try:
            book_d = json.loads(book.read_text(encoding="utf-8")) if book.exists() else {}
        except (OSError, ValueError):
            book_d = {}
        notes_rec = record(merge(prev.get(KEY), (book_d or {}).get(KEY)), today=now.date(), api=api_now, **ann)
        notices = reminders(notes_rec, api_now, now.date())
        try:
            items = (gate or _gate)(agents)
            stars = gate_stars(items)
            gate_err = ""
        except Exception as e:                                # noqa: BLE001
            stars, gate_err = list(prev.get("gate_stars") or []), scrub(f"{type(e).__name__}：{e}") or "?"
        old = prev.get("gate_stars")
        new_stars = [s for s in stars if s not in set(old or [])]
        if gate_err:
            notices.append(f"上线门槛的检查出错（{gate_err}）：在 Mac 对话里说「看一下预检日志」")
        reasons = [local_paths_out(r) for r in reasons]
        rec = {"at": now.isoformat(timespec="seconds"), "ok": not reasons, "target": target, "reasons": reasons,
               "notices": [local_paths_out(n) for n in notices], "gate_stars": stars, "new_stars": new_stars,
               "api": api_now, "code": code_version(), KEY: notes_rec}
        atomic_write_text(result_path(), json.dumps(rec, ensure_ascii=False, indent=1))
    finally:
        lock.release()
    print(f"前一晚预检（{target} 的交易；只读）：" + ("通过（登录 / 取余力正常，已登出）" if not reasons else "★ 没通过"))
    for r in reasons:
        print(f"  ★ {r}")
    for n in rec["notices"]:
        print(f"  {n}")
    if new_stars:
        print("  上线门槛 / 准备里新出现的 ★：" + "；".join(new_stars) + "（bash scripts/liveu.sh gate 看全部）")
    print(f"结果 {local_paths_out(str(result_path()))}")
    if reasons or rec["notices"] or new_stars:
        title, body, level = compose(reasons, rec["notices"], new_stars, target)
        if notify_seen.first(TAG, title + "\n" + body, now):
            if send is None:
                from .notify import send as send_
                send = send_
            if mac is None:
                from .live_unified import mac_notify as mac
            mac(title, (reasons or rec["notices"] or new_stars)[0][:200])
            send(title, body, level)
        else:
            print("（同样的内容今天已经通知过：这次不再发 Mac / 手机通知）")
    return 0 if not reasons else 1


def _gate(agents) -> list[dict]:
    from . import live_gate
    return live_gate.check(agents=agents)


def panel_lines(rec: dict | None, now: dt.datetime) -> list[str]:
    """面板顶部（立花）：今天 / 昨晚的预检没通过的原因与提醒（30 小时以内的结果；没有 → []）。只展示。"""
    from .run_status import ts
    if not rec:
        return []
    t = ts(rec.get("at"))
    now = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    if t is None or not (dt.timedelta(0) <= now - t <= dt.timedelta(hours=30)):
        return []
    when = t.astimezone(JST).strftime("%m/%d %H:%M")
    out = []
    if rec.get("ok") is False:
        out.append(f"★ 前一晚预检（{when}）没通过：" + "；".join(str(x) for x in rec.get("reasons") or ["原因不明"]))
    out += [str(n) for n in rec.get("notices") or [] if str(n).startswith("★")]
    return out


__all__ = ["run", "record", "merge", "reminders", "ack_api", "release_handled", "target_day", "gate_stars", "panel_lines", "installed", "result_path",
           "last_result", "KEY", "LABEL", "DOC_DAYS"]
