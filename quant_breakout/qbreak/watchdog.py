"""watchdog.py — 09:30 自检：死人开关的本机一半 + 外部心跳（只看、只提醒；不下单、不改账本）。

LaunchAgent com.qbreak.watchdog（周一至五 09:30，scripts/install_launchd_watchdog.sh）→ scripts/liveu.sh watchdog → run.py live-watchdog。
- 看装的是哪种：<LaunchAgents>/com.qbreak.liveu.morning.plist 在 → 立花本番的账本（tachibana）；否则 com.qbreak.liveu.paper.plist 在 →
  模拟账户（paper）；都不在 → 只打印、不发。
- 休市日 → 心跳成功（「休市」）。交易日：今天早上的运行跑完了（账本处理到上一个交易日、这个决策没有 PLANNED / BLOCKED 的单）、
  没有状态不明的单、（立花）没有留到现在的开盘后买单（DEFERRED）→ 心跳成功、不发通知；否则 → 手机通知 + Mac 通知 + 心跳失败，原因写清
  （执行器停下的原因读运行状态文件 out/live_unified_<账本>_run.json，qbreak/run_status.py）。
- HALT 存在：不算失败（心跳成功），通知「HALT 生效中」同一天只一次（qbreak/notify_seen.py）。
- 模拟账户在模拟期开始日（sim.json 的 start）之前不推进：不算失败（心跳成功）。
- 执行器正在运行（拿着运行锁；例：Mac 睡着错过 07:40，醒来时 launchd 把错过的任务和自检一起拉起）→ 等它结束再判定（最多 10 分钟）；
  还在跑 → 这次不判定、不发通知 / 心跳。
- 写 out/watchdog_<账本>.json（at、ok、reasons；面板 / 手机顶部显示今天没通过的原因）。
- 发出去的文字（手机通知 / 心跳）里的本机路径换成「数据目录」/「~」（不带 Mac 的用户名）。
- dry=True（liveu.sh watchdog --dry）：只判定、打印；不写结果文件、不发通知 / 心跳、不等运行锁。
外部心跳（healthchecks.io 之类）是另一半：在服务上建「周一至五 09:30 JST、宽限 30 分钟」的检查 —— Mac 关机 / 睡着 / 断网时
这里根本不会运行、不会 ping，服务那边就会推送到手机。地址存钥匙串 qbreak-heartbeat（qbreak/notify.py）。
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from . import paths
from .calendar_jp import JST, is_trading_day, now_jst, prev_trading_day
from .utils import atomic_write_text, setup_logging

log = setup_logging("watchdog")

LIVE_PLIST, PAPER_PLIST = "com.qbreak.liveu.morning", "com.qbreak.liveu.paper"
LABEL = "com.qbreak.watchdog"
JUDGE_FROM = dt.time(9, 0)          # 这之前早上的运行（07:40〜08:55）可能还在进行：不判定
OPEN_DONE = dt.time(9, 25)          # 这之后 09:05 / 09:20 的开盘后补单应该已经跑完
ESHITEN_SP = "https://kabuka.e-shiten.jp/mfds_smp.php"     # 立花 e支店的手机网站（注文一覧在这里看）
HALT_KEY = "09:30 自检：HALT 生效中"                          # 去重用的固定文字（同一天只提醒一次）
LOCK_WAIT_S, LOCK_POLL_S = 600, 15                            # 执行器正在运行：最多等 10 分钟、每 15 秒看一次


def installed(agents) -> str | None:
    """装的是哪种执行器：立花本番 → "tachibana"；模拟操盘 → "paper"；都没装 → None。"""
    agents = Path(agents)
    if (agents / f"{LIVE_PLIST}.plist").exists():
        return "tachibana"
    if (agents / f"{PAPER_PLIST}.plist").exists():
        return "paper"
    return None


def path(tag: str) -> Path:
    return paths.out_dir() / f"watchdog_{tag}.json"


def _halt() -> str | None:
    p = paths.halt_file()
    if not p.exists():
        return None
    try:
        return (p.read_text(encoding="utf-8", errors="replace").splitlines() or ["HALT"])[0][:160] or "HALT"
    except OSError:
        return "HALT"


def _sim_start() -> str | None:
    """模拟期开始日（执行器读的数据目录 sim.json 的 start；liveu.sh 每次运行前从仓库拷过来）。读不了 → None。"""
    from .utils import read_json
    try:
        v = (read_json(paths.home() / "sim.json", {}) or {}).get("start")
        return str(dt.date.fromisoformat(str(v))) if v else None
    except (ValueError, TypeError, AttributeError):
        return None


def _otext(o: dict) -> str:
    from . import run_status as RS
    st = {**RS.STATUS_TEXT, "PLANNED": "还没发"}.get(o.get("status"), str(o.get("status")))
    unit = "口" if o.get("kind") == "core" else "股"
    note = str(o.get("note") or "")
    return (f"{o.get('ticker')} {'买' if o.get('side') == 'BUY' else '卖'} {int(o.get('sent_qty') or o.get('qty') or 0):,} {unit} {st}"
            + (f"：{note}" if note else ""))


def evaluate(tag: str, now: dt.datetime | None = None) -> dict:
    """→ {"at", "tag", "trading", "judged", "ok", "halt", "reasons": [...], "note"}。只读（账本读坏也不改名）。"""
    from . import run_status as RS
    from .live_unified import UNKNOWN, morning_done, open_pending
    now = now or now_jst()
    now = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    today = now.date()
    rec = {"at": now.isoformat(timespec="seconds"), "tag": tag, "trading": is_trading_day(today), "judged": True,
           "ok": True, "halt": None, "reasons": [], "note": ""}
    if not rec["trading"]:
        rec["note"] = f"{today} 休市"
        return rec
    if now.time() < JUDGE_FROM:
        rec["judged"] = False
        rec["note"] = f"还早：{JUDGE_FROM:%H:%M} 之前不判定（早上的运行 07:40〜08:55 可能还在进行）"
        return rec
    start = _sim_start() if tag.startswith("paper") else None
    if start and today.isoformat() < start:                   # 执行器在开始日之前故意不推进模拟账户（run.py live-u）
        rec["note"] = f"模拟期开始日 {start} 之前（模拟账户还不推进）"
        return rec
    reasons: list[str] = []
    bp = paths.state_dir() / f"live_unified_{tag}.json"
    book = RS.peek_json(bp)
    if book is None and bp.exists():
        reasons.append("账本文件读不了（可能损坏）：在 Mac 对话里说「看一下执行器日志」")
    book = book or {}
    st = book.get("state") or {}
    ld = st.get("last_date")
    exp = prev_trading_day(today).isoformat()                 # 今天早上应该处理到的决策日
    done = morning_done(book, exp)
    if not done and str(ld or "") != exp:
        reasons.append(f"今天早上的执行器没有跑完（上次决策 {ld or '—'}）")
    rs = RS.read(tag)
    t_rs = RS.ts((rs or {}).get("at"))
    rs_today = bool(rs) and t_rs is not None and t_rs.astimezone(JST).date() == today
    if rs_today:
        if rs.get("ok") is False:
            reasons.append(f"执行器停下（{t_rs.astimezone(JST):%H:%M}）：{rs.get('error') or '原因不明（看数据目录 logs/ 的 .err）'}")
        if rs.get("blocked") and not done:
            reasons.append(f"今天的单没下：{rs['blocked']}")
    if not done and str(ld or "") == exp:                     # 决策处理了，但有单没下（被挡 / 还没发 / 被拒）：逐笔说清
        stuck = [o for o in book.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == exp
                 and o.get("status") in ("PLANNED", "BLOCKED", "REJECTED")]
        stuck = RS.uncovered(stuck, rs.get("blocked") if rs_today else None)   # 「今天的单没下：…」已经说了原因的不再逐笔列
        if stuck:
            reasons.append(f"决策 {exp} 处理了，但有 {len(stuck)} 笔没下：" + "；".join(_otext(o) for o in stuck[:5])
                           + ("…" if len(stuck) > 5 else ""))
    unk = [o for o in book.get("orders") or [] if isinstance(o, dict) and o.get("status") in UNKNOWN]
    if unk:
        what = "、".join(f"{o.get('ticker')} {'买' if o.get('side') == 'BUY' else '卖'} {int(o.get('sent_qty') or o.get('qty') or 0):,}"
                        for o in unk[:5])
        reasons.append(f"有状态不明的单 {len(unk)} 笔（{what}）：" + (
            "在 Mac 对话里看一下" if tag.startswith("paper")
            else f"去立花的注文一覧核对（手机网站 {ESHITEN_SP}），再在 Mac 对话里登记"))
    if tag.startswith("tachibana") and now.time() >= OPEN_DONE and open_pending(book):
        n = sum(1 for o in book.get("orders") or [] if o.get("decided_on") == ld and o.get("status") == "DEFERRED")
        reasons.append(f"开盘后的买单还没下（{n} 笔：09:05 / 09:20 的补单没跑成）")
    rec["reasons"] = reasons
    rec["halt"] = _halt()
    rec["ok"] = bool(rec["halt"]) or not reasons                # HALT 生效中：不下单是预期的，不算失败
    return rec


def write(rec: dict) -> None:
    """out/watchdog_<账本>.json（面板读 at / ok / reasons）。写不成只记 warning。"""
    try:
        atomic_write_text(path(rec["tag"]), json.dumps({k: rec[k] for k in ("at", "ok", "reasons", "halt", "note")},
                                                       ensure_ascii=False, indent=1))
    except Exception as e:                                    # noqa: BLE001
        log.warning("自检结果文件没写成（不影响交易）：%s", e)


def _sent(res) -> str:
    """{webhook / email: True / False / None} → 「webhook 已发、邮件 没设置」（不含任何值）。"""
    from .notify import LABEL as NL
    word = {True: "已发", False: "★ 失败", None: "没设置"}
    return "、".join(f"{NL.get(k, k)} {word.get(v, v)}" for k, v in (res or {}).items()) or "—"


def run(agents, now: dt.datetime | None = None, *, send=None, beat=None, mac=None, seen=None, out=print, sleep=None,
        dry: bool = False) -> int:
    """自检一次：（执行器正在运行 → 等它结束）判定 → 写结果文件 → 通知 / 心跳。0 = 通过（含休市、HALT、还早、没装、
    模拟期开始前、执行器一直在跑），1 = 没通过。dry：只判定、打印（不写、不发、不等）。
    send / beat / mac / seen / sleep：测试注入（默认 qbreak.notify.send / heartbeat、Mac 通知、qbreak.notify_seen.first、time.sleep）。"""
    from . import notify, notify_seen
    from . import run_status as RS
    from .live_unified import lock_held
    send = send or notify.send
    beat = beat or notify.heartbeat
    seen = seen or notify_seen.first
    sleep = sleep or time.sleep
    if mac is None:
        from .live_unified import mac_notify as mac
    tag = installed(agents)
    if tag is None:
        out(f"没装执行器的定时任务（{agents} 里 {LIVE_PLIST} / {PAPER_PLIST} 都没有）：只打印，不发通知、不发心跳")
        return 0
    name = "立花实盘" if tag == "tachibana" else "模拟操盘"
    lock = paths.state_dir() / f"live_unified_{tag}.lock"
    if not dry and lock_held(lock):                           # 执行器正在运行：判定的是还没跑完的账本 → 等它结束
        out(f"（{name}的执行器正在运行：等它结束再判定，最多 {LOCK_WAIT_S // 60} 分钟）")
        waited = 0
        while lock_held(lock) and waited < LOCK_WAIT_S:
            sleep(LOCK_POLL_S)
            waited += LOCK_POLL_S
        if lock_held(lock):
            out(f"{name}：执行器跑了 {LOCK_WAIT_S // 60} 分钟以上还没结束 → 这次不判定、不发通知 / 心跳"
                "（心跳服务那边过了宽限时间会提醒；之后只看：bash scripts/liveu.sh watchdog --dry）")
            return 0
        now = None if now is None else now + dt.timedelta(seconds=waited)
    now = now or now_jst()
    r = evaluate(tag, now)
    when = r["at"][:16].replace("T", " ")
    if dry:
        busy = "（执行器正在运行：结果可能还会变）" if lock_held(lock) else ""
        if not r["judged"] or not r["trading"] or not r["reasons"]:
            out(f"{name}（{when} JST，只看不发）：{r['note'] or '自检通过（今天早上的运行跑完、没有状态不明的单）'}{busy}")
        else:
            out(f"{name}（{when} JST，只看不发）：{'HALT 生效中（不算失败）；' if r['halt'] else '★ 没通过：'}\n"
                + "\n".join(f"- {x}" for x in r["reasons"]) + busy)
        return 0 if r["ok"] else 1
    r["reasons"] = [RS.local_paths_out(x) for x in r["reasons"]]   # 手机通知 / 心跳的正文不带本机路径（Mac 的用户名）
    if not r["judged"]:
        out(f"{name}（{when} JST）：{r['note']}；不发心跳")
        return 0
    write(r)
    if not r["trading"] or (r["ok"] and r["note"] and not r["reasons"]):   # 休市 / 模拟期开始日之前
        hb = beat(True, f"qbreak {name}：{r['note']}")
        out(f"{name}（{when} JST）：{r['note']} → 心跳 {_beat(hb)}")
        return 0
    if r["halt"]:
        extra = ("\n另外：" + "；".join(r["reasons"])) if r["reasons"] else ""
        text = RS.local_paths_out(f"HALT 生效中（{r['halt']}）：执行器不下单、持仓不动；解除只在 Mac 上、你明确说之后{extra}")
        if seen(tag, HALT_KEY, now):
            title = f"qbreak {name}：HALT 生效中"
            res = send(title, text, "info")
            mac(title, text[:200])
            out(f"{name}（{when} JST）：{text}\n  通知：{_sent(res)}")
        else:
            out(f"{name}（{when} JST）：{text}\n  （今天已经提醒过 HALT：这次不再发通知）")
        hb = beat(True, f"qbreak {name}：HALT 生效中")
        out(f"  心跳 {_beat(hb)}")
        return 0
    if r["ok"]:
        hb = beat(True, f"qbreak {name}：{when} 自检通过")
        out(f"{name}（{when} JST）：自检通过（今天早上的运行跑完、没有状态不明的单） → 心跳 {_beat(hb)}")
        return 0
    title = f"qbreak {name} ★ 09:30 自检没通过"
    text = "\n".join(f"- {x}" for x in r["reasons"])
    res = send(title, text, "warn")
    mac(title, r["reasons"][0][:200])
    hb = beat(False, f"{title}\n{text}")
    out(f"{title}（{when} JST）：\n{text}\n  通知：{_sent(res)}；心跳（失败）{_beat(hb)}")
    return 1


def _beat(hb) -> str:
    return {True: "已发", False: "★ 没发成", None: "没设置（钥匙串 qbreak-heartbeat）"}.get(hb, str(hb))


__all__ = ["installed", "evaluate", "write", "run", "path", "LABEL"]
