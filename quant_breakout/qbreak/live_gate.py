"""live_gate.py — 立花实盘的上线门槛（HANDOFF 路线图 4，2026-09-26 用户原样采用）与本番运行的准备，逐项检查。

只读：不下单、不改任何文件、不打印任何密钥的值（钥匙串只看「有没有」，私钥只看「在不在、权限是不是 600」，不读内容）。
用法：bash scripts/liveu.sh gate（= run.py live-gate；Mac 对话里问「能上实盘了吗」）。

门槛（四项都满足才上本番，先用较小金额跑 1〜2 周）：
 ① Mac 模拟操盘与云端模拟盘连续 ≥ 10 个交易日一致（或差异都能解释 → 由用户确认）
 ② 没有状态不明的单
 ③ HALT 演练过一次（执行器在 HALT 存在时运行过：账本的 halt_seen；bash scripts/liveu.sh halt-drill）
 ④ デモ发单检查的几点确认（约定字段、余力 / 持仓变化、按注文番号撤单、寄付指値买受理：tachibana-probe --demo --order-test 的结果文件）
准备（本番每天全自动要用到）：⑤ 本番只读检查通过 ⑥ 认证信息在钥匙串、私钥权限 600、cryptography 已装
 （④ / ⑤：结果文件记着当时的 API 版本段；与现在的仕様不同、或是没记版本的旧格式 → 要重新做；做了几天只显示、不判定）
 ⑦ 立花的定时任务已装、Mac 每个交易日早上自动唤醒（pmset）
 ⑧ 人不在 Mac 前也知道出事：手机通知通道（钥匙串 qbreak-webhook / qbreak-smtp）、外部心跳（qbreak-heartbeat）、09:30 自检任务（com.qbreak.watchdog）
参考（不算门槛）：口座课税区分、ARM / HALT 现在的状态、登记过的入出金。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import re
import subprocess
from pathlib import Path

from . import paths
from .utils import read_json

STREAK_NEED = 10
LIVE_LABELS = ("com.qbreak.liveu.morning", "com.qbreak.liveu.retry", "com.qbreak.liveu.open", "com.qbreak.liveu.open2")
KEYCHAIN = (("qbreak-tachibana-authid", "认证 ID", "TACHIBANA_AUTH_ID"),
            ("qbreak-tachibana-2nd", "第二暗証番号", "TACHIBANA_SECOND_PASSWORD"))
WAKE_CMD = "sudo pmset repeat wakeorpoweron MTWRF 07:30:00"
_SAME, _DIFF = "- 与云端模拟盘一致", "- ★ 与云端模拟盘不一致"
REDO = {"demo": "bash scripts/liveu.sh probe --demo --order-test", "live": "bash scripts/liveu.sh probe"}
ACCEPTED = ("SENT", "FILLED", "PARTIAL")


def _cmd(run, args: list[str]) -> tuple[int | None, str]:
    """跑一个只读的系统命令（security / launchctl / pmset）→ (退出码, 标准输出)；命令不存在 → (None, "")。输出只用来判断，不打印。"""
    try:
        r = run(args, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return r.returncode, r.stdout or ""


def compare_days(book: dict, journal: str = "") -> dict[str, bool]:
    """每个决策日与云端比较的结果 {日期: 一致?}：日志（旧的日子）+ 账本的 compare_history（2026-10-04 起；同一天以它为准）。
    「不是同一天，这次不比」的日子不算一致、也不算不一致。"""
    out: dict[str, bool] = {}
    for sec in ("\n" + (journal or "")).split("\n## ")[1:]:
        lines = sec.splitlines()
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", lines[0]) if lines else None
        if not m:
            continue
        for ln in lines[1:]:
            if ln.startswith(_SAME):
                out[m.group(1)] = True
            elif ln.startswith(_DIFF):
                out[m.group(1)] = False
    for h in (book or {}).get("compare_history") or []:
        if h.get("comparable") and h.get("date"):
            out[str(h["date"])] = bool(h.get("same"))
    return dict(sorted(out.items()))


def streak(days: dict[str, bool]) -> tuple[int, str | None]:
    """从最近的决策日往前数连续一致的天数 → (天数, 最近一次不一致的日期 | None)。"""
    n = 0
    for d in sorted(days, reverse=True):
        if not days[d]:
            return n, d
        n += 1
    return n, None


def _book(tag: str) -> dict:
    return read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {}


def _journal(tag: str) -> str:
    p = paths.out_dir() / f"live_unified_{tag}_journal.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _api_now(env: str) -> str | None:
    """现在的仕様（数据目录的 tachibana_spec.json 覆盖默认值）的 base URL 版本段（例如 e_api_v4r10）；仕様文件读不了 → None。"""
    from .brokers.tachibana import TachibanaSpec, api_version
    try:
        sp = TachibanaSpec.load()
    except Exception:                                # noqa: BLE001
        return None
    return api_version(sp.base_demo if env == "demo" else sp.base_live)


def _stale(env: str, rec: dict) -> str | None:
    """probe 结果文件是旧格式（没记 api）/ 当时的 API 版本与现在的仕様不同 → ★ 文字（要重新做）；没问题 → None。"""
    old, now = str(rec.get("api") or ""), _api_now(env)
    if not old:
        return f"★ 检查结果是旧格式：重新做 {REDO[env]}"
    if now is None:
        return f"★ 数据目录的 tachibana_spec.json 读不了：先修好它，再重新做 {REDO[env]}"
    if old != now:
        return f"★ API 版本变了（{old} → {now}）：重新做 {REDO[env]}"
    return None


def _age(at, today: dt.date) -> str:
    """结果文件的 at（"YYYY-MM-DD HH:MM JST"）→ 「（N 天前做的）」；读不出 → ""。只显示、不判定。"""
    try:
        n = (today - dt.date.fromisoformat(str(at or "")[:10])).days
    except ValueError:
        return ""
    return "（今天做的）" if n == 0 else f"（{n} 天前做的）"


def _wake(sched: str) -> tuple[bool | None, str]:
    """pmset -g sched 的「Repeating power events」里有没有工作日（或每天）07:40 之前的唤醒 / 开机。"""
    rep = sched.split("Repeating power events:", 1)[1] if "Repeating power events:" in sched else ""
    rep = rep.split("Scheduled power events:", 1)[0]
    lines = [ln.strip() for ln in rep.splitlines() if "wake" in ln.lower() or "poweron" in ln.lower()]
    if not lines:
        return False, f"★ 没有设定：在终端运行 {WAKE_CMD}（要输入 Mac 的登录密码；Mac 接着电源、不合盖）"
    ln = lines[0]
    m = re.search(r"at\s+(\d{1,2}):(\d{2})\s*([AP]M)?", ln, re.I)
    days = ln.lower()
    if not m or not ("weekday" in days or "every day" in days):
        return None, f"有重复唤醒、读不出是不是工作日 07:40 之前（{ln}）：请确认，或重设 {WAKE_CMD}"
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
    if ap:
        h = h % 12 + (12 if ap == "PM" else 0)
    if (h, mi) <= (7, 40):
        return True, f"已设定：{ln}"
    return False, f"★ 唤醒时间晚于 07:40（{ln}）：{WAKE_CMD}"


def _alerts(add, run, agents: Path, rc_list: int | None, listing: str) -> None:
    """⑧ 人不在 Mac 前也知道出事：手机通知通道、外部心跳、09:30 自检任务（只查钥匙串里有没有，不取出值；不发通知）。"""
    from . import notify as NT

    def kc(name: str):                                # 钥匙串里有没有（定时任务读不到 ~/.zshrc 的环境变量 → 只看钥匙串）
        return NT.configured(name, run=run, env=False)
    env_only = "（环境变量有设置，但定时任务读不到 ~/.zshrc 的环境变量）"
    wh, em = kc("webhook"), kc("email")
    if wh is None and em is None:
        add("准备", "⑧ 手机通知通道（webhook / 邮件）", None, "不是 macOS（没有 security 命令）：跳过")
    elif wh or em:
        add("准备", "⑧ 手机通知通道（webhook / 邮件）", True,
            "钥匙串里有 " + "、".join(s for s, x in (("qbreak-webhook", wh), ("qbreak-smtp", em)) if x)
            + "（只查了有没有；发一条试试：bash scripts/liveu.sh notify-test）")
    else:
        add("准备", "⑧ 手机通知通道（webhook / 邮件）", False,
            "★ 钥匙串里没有 qbreak-webhook / qbreak-smtp"
            + (env_only if os.environ.get("QBREAK_WEBHOOK") or os.environ.get("QBREAK_SMTP") else "")
            + "：在 Discord / Slack / ntfy 建一个只给自己的通知地址，在终端运行 security add-generic-password -s qbreak-webhook -a qbreak -w"
              "（回车后输入，不要贴进聊天），再 bash scripts/liveu.sh notify-test")
    hb = kc("heartbeat")
    if hb is None:
        add("准备", "⑧ 外部心跳（Mac 没跑的提醒）", None, "不是 macOS（没有 security 命令）：跳过")
    elif hb:
        add("准备", "⑧ 外部心跳（Mac 没跑的提醒）", True, "钥匙串里有 qbreak-heartbeat（只查了有没有；每个交易日 09:30 自检时 ping）")
    else:
        add("准备", "⑧ 外部心跳（Mac 没跑的提醒）", False,
            "★ 钥匙串里没有 qbreak-heartbeat" + (env_only if os.environ.get("QBREAK_HEARTBEAT") else "")
            + "：在 healthchecks.io 之类的服务建一个「周一至五 09:30 JST、宽限 30 分钟」的检查（时区选 Asia/Tokyo），"
              "把 ping 地址存进钥匙串：security add-generic-password -s qbreak-heartbeat -a qbreak -w（回车后输入，不要贴进聊天）；"
              "Mac 关机 / 睡着 / 断网时那边会推送到手机")
    lb = "com.qbreak.watchdog"
    has = (agents / f"{lb}.plist").exists()
    loaded = rc_list != 0 or lb in listing
    if has and loaded:
        add("准备", "⑧ 09:30 自检任务（com.qbreak.watchdog）", True, "已装" + ("" if rc_list == 0 else "（没有 launchctl：只看了文件）"))
    else:
        add("准备", "⑧ 09:30 自检任务（com.qbreak.watchdog）", False,
            f"★ {'没装' if not has else '没加载'}：bash scripts/mac_setup.sh（或 bash scripts/install_launchd_watchdog.sh）")


def check(agents=None, run=subprocess.run, today: dt.date | None = None) -> list[dict]:
    """逐项检查 → [{"group": 门槛 / 准备 / 参考, "name", "ok": True / False / None（只供参考）, "text"}]。today：测试注入（JST 的日期）。"""
    from .calendar_jp import now_jst
    from .live_unified import UNKNOWN, flows
    today = today or now_jst().date()
    out: list[dict] = []

    def add(group: str, name: str, ok, text: str) -> None:
        out.append({"group": group, "name": name, "ok": ok, "text": text})

    paper, live = _book("paper"), _book("tachibana")
    days = compare_days(paper, _journal("paper"))
    n, bad = streak(days)
    add("门槛", f"① Mac 模拟操盘与云端连续 ≥ {STREAK_NEED} 个交易日一致", n >= STREAK_NEED,
        f"最近连续一致 {n} 个决策日（一共比过 {len(days)} 天"
        + (f"；最近一次不一致 {bad}：差异如果都能解释，由你确认后算通过" if bad else "") + "）")
    unk = [(br, f"{name} {o.get('cid')} {o.get('side')} {o.get('ticker')}")
           for name, br, b in (("模拟账户", "paper", paper), ("立花", "tachibana", live))
           for o in b.get("orders") or [] if o.get("status") in UNKNOWN]
    how = "；".join(f"bash scripts/liveu.sh --broker {br} --resolve <cid> --filled <股数> --px <均价>"   # 经 liveu.sh：数据目录 ~/.qbreak/home
                   for br in dict.fromkeys(br for br, _ in unk))
    add("门槛", "② 没有状态不明的单", not unk,
        "没有" if not unk else "★ " + "；".join(t for _, t in unk) + f"（在立花的注文一覧确认后：{how}；没成交填 0）")
    seen = sorted(set((paper.get("halt_seen") or []) + (live.get("halt_seen") or [])))
    add("门槛", "③ HALT 演练过一次", bool(seen),
        f"执行器在 HALT 存在时运行过：{'、'.join(seen[-3:])}" if seen
        else "还没有：在 Mac 对话里说「做一次 HALT 演练」（bash scripts/liveu.sh halt-drill；不动真的 HALT）")
    demo = read_json(paths.out_dir() / "tachibana_probe_demo.json", {}) or {}
    ot = demo.get("order_test") or {}
    if not ot:
        add("门槛", "④ デモ发单检查（约定字段、余力变化、按注文番号撤单）", False,
            "还没做：开户、登记デモ用的公钥之后 bash scripts/liveu.sh probe --demo --order-test（デモ环境 9:00〜15:00 / 15:10〜）")
    else:
        miss = ot.get("fields_missing") or []
        olb, oc = ot.get("opening_limit_buy"), ot.get("opening_cancel")
        if "opening_limit_buy" not in ot:            # 旧的检查（2026-10-09 之前）没测执行器最常用的单型 → 要重新做
            olb_txt = "★ 没测（旧的检查）"
        elif olb in ACCEPTED:
            olb_txt = "受理、" + ("撤单成功" if oc else "已成交（不用撤）" if oc is None else "★ 撤单没成功")
        else:
            olb_txt = f"★ 没受理（{olb or '—'}）"
        txt = (f"{demo.get('at', '—')}{_age(demo.get('at'), today)}：约定字段 {'齐' if not miss else '★ 缺 ' + '、'.join(miss)}；"
               f"余力 / 持仓变化 {'有' if ot.get('cash_or_pos_changed') else '★ 没看到'}；"
               f"按注文番号撤单 {'成功' if ot.get('cancel') else '★ 没成功'}；寄付指値买 {olb_txt}")
        st = _stale("demo", demo)
        add("门槛", "④ デモ发单检查（约定字段、余力变化、按注文番号撤单）",
            bool(ot.get("ok")) and olb in ACCEPTED and oc is not False and not st, f"{st}（上次 {txt}）" if st else txt)
    lv = read_json(paths.out_dir() / "tachibana_probe_live.json", {}) or {}
    if not lv:
        add("准备", "⑤ 本番只读检查（登录 / 取价 / 持仓 / 余力 / 立花能不能买）", False, "还没做：bash scripts/liveu.sh probe（只读，不发单）")
    else:
        txt = (f"{lv.get('at', '—')}{_age(lv.get('at'), today)}："
               + ("全部通过" if lv.get("ok") else "★ 没通过：" + "、".join(k for k, v in (lv.get("steps") or {}).items() if not v)))
        if lv.get("ok") and not lv.get("price_checked"):     # 只提醒（不算没通过）：盘外的检查只看到前日終値，现价的字段名没确认
            txt += "；★ 现价字段还没在交易时间里确认过：交易日 09:00〜15:30 再做一次 bash scripts/liveu.sh probe（只读）"
        st = _stale("live", lv)
        add("准备", "⑤ 本番只读检查（登录 / 取价 / 持仓 / 余力 / 立花能不能买）", bool(lv.get("ok")) and not st,
            f"{st}（上次 {txt}）" if st else txt)
    for svc, label, env in KEYCHAIN:
        rc, _ = _cmd(run, ["security", "find-generic-password", "-s", svc, "-a", "qbreak"])   # 不加 -w：不取出值
        name = f"⑥ {label}{' ' if label[-1].isascii() else ''}在钥匙串"
        if rc == 0:
            add("准备", name, True, f"钥匙串里有 {svc}（只查了有没有）")
        elif rc is None:
            add("准备", name, None, "不是 macOS（没有 security 命令）：跳过")
        else:
            add("准备", name, False,
                f"★ 钥匙串里没有 {svc}" + ("（环境变量有设置，但定时任务读不到 ~/.zshrc 的环境变量）" if os.environ.get(env) else "")
                + f"：在终端运行 security add-generic-password -s {svc} -a qbreak -w（回车后输入，不要贴进聊天）")
    key = Path(os.environ.get("TACHIBANA_PRIVATE_KEY") or Path.home() / ".qbreak" / "e_api_private_key.pem").expanduser()
    if not key.exists():
        add("准备", "⑥ 私钥文件", False, f"★ 没有 {key}：放「ｅ支店・API 利用設定」登记的公钥对应的私钥（chmod 600）")
    else:
        mode = key.stat().st_mode & 0o777
        add("准备", "⑥ 私钥文件", mode & 0o077 == 0,
            f"{key} 权限 {mode:o}" + ("" if mode & 0o077 == 0 else f"：★ 太宽，chmod 600 {key}"))
    has_crypto = importlib.util.find_spec("cryptography") is not None
    add("准备", "⑥ cryptography（解密虚拟 URL）", has_crypto, "已装" if has_crypto else "★ 没装：bash scripts/mac_setup.sh")
    agents = Path(agents or os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")
    miss = [lb for lb in LIVE_LABELS if not (agents / f"{lb}.plist").exists()]
    rc_list, listing = _cmd(run, ["launchctl", "list"])
    unloaded = [lb for lb in LIVE_LABELS if lb not in miss and rc_list == 0 and lb not in listing]
    if not miss and not unloaded:
        txt = "已装" + ("" if rc_list == 0 else "（没有 launchctl：只看了文件）")
    else:
        txt = ("★ " + "；".join(x for x in ("没装 " + "、".join(miss) if miss else "", "没加载 " + "、".join(unloaded) if unloaded else "") if x)
               + "：开户、过了门槛之后 bash scripts/install_launchd_live_u.sh tachibana")
    add("准备", "⑦ 立花的定时任务（07:40 / 08:35 / 09:05 / 09:20）", not miss and not unloaded, txt)
    rc, sched = _cmd(run, ["pmset", "-g", "sched"])
    if rc is None:
        add("准备", "⑦ Mac 工作日早上自动唤醒", None, "不是 macOS（没有 pmset）：跳过")
    elif rc != 0:
        add("准备", "⑦ Mac 工作日早上自动唤醒", None, "pmset -g sched 读不出：请自己确认")
    else:
        ok, txt = _wake(sched)
        add("准备", "⑦ Mac 工作日早上自动唤醒", ok, txt)
    _alerts(add, run, agents, rc_list, listing)
    tax = str(lv.get("tax") or "")
    add("参考", "口座课税区分", None, {"1": "特定口座", "": "还不知道（本番只读检查之后显示）"}.get(
        tax, f"{tax}（不是特定口座：执行器按口座的区分发单，没问题；报税方式不同）"))
    arm = paths.home() / "ARM"
    armed = arm.exists() and arm.read_text(encoding="utf-8").strip().upper() == "ARMED"
    add("参考", "ARM（解锁发单）", None, "已解锁" if armed else "未解锁（过了门槛、你在对话里明确说之后才建）")
    add("参考", "HALT", None, f"★ 生效中（{paths.halt_file()}）" if paths.halt_file().exists() else "不存在")
    fl = flows(live)
    add("参考", "登记过的入出金（立花）", None,
        f"{len(fl)} 笔，合计 {sum(float(f.get('jpy') or 0) for f in fl):+,.0f} 円" if fl else "没有")
    return out


def report(items: list[dict]) -> tuple[str, bool]:
    """给人看的几行 + 门槛与准备是否全部满足（None = 跳过 / 只供参考，不算）。"""
    mark = {True: "OK", False: "★ 未完成", None: "—"}
    lines, cur = [], None
    for it in items:
        if it["group"] != cur:
            cur = it["group"]
            lines.append({"门槛": "【上线门槛】（2026-09-26 采用；全部满足才上本番）", "准备": "【本番运行的准备】",
                          "参考": "【参考】"}[cur])
        txt = it["text"][2:] if it["ok"] is False and it["text"].startswith("★ ") else it["text"]
        lines.append(f"  [{mark[it['ok']]}] {it['name']}：{txt}")
    need = [it for it in items if it["group"] in ("门槛", "准备") and it["ok"] is not None]
    ok = all(it["ok"] for it in need)
    lines.append("全部满足：可以在对话里明确说「上实盘」（建 ARM、先用较小金额跑 1〜2 周）" if ok
                 else "还没全部满足（★ 的几项）；这个检查只读，什么都没改")
    return "\n".join(lines), ok
