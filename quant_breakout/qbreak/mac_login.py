"""mac_login.py — Mac 登录 / 开机时的自动启动（LaunchAgent com.qbreak.login，RunAtLoad；由 scripts/liveu.sh login 调用）。

这里只决定要做什么（打印「动作<TAB>参数」，liveu.sh 照着执行）：
- 市场仪表盘 com.qbreak.news 没加载 → 加载（plist 不在 → 安装）
- 模拟操盘补跑（RUN_PAPER）：今天是日本交易日、已过 07:40 JST、今天还没跑成（<数据目录>/out/live_unified_paper.json 的修改日期不是今天）、
  装的是模拟操盘（com.qbreak.liveu.paper）且没装立花本番（com.qbreak.liveu.morning）、现在没有执行器在跑 → liveu.sh run --broker paper。
  模拟账户同一决策日重复运行不会重复下单；立花本番（真钱）永远不在登录时补跑。
- 打开账本页面与市场仪表盘 dashboard.html（数据目录里有 NO_OPEN 就不打开；补跑本身会打开账本页面，不重复打开）：
  装了立花本番 → page_tachibana.html（B12：模拟操盘的定时任务已卸载，page_paper.html 不再更新）；否则 page_paper.html。
- 立花本番（MAC_ALERT）：交易日 07:40〜15:30、今天早上的运行还没完成（账本没处理到应有的决策日，或这个决策还有 PLANNED / BLOCKED 的单；
  同 live_unified.morning_done）、没有执行器在跑、没有 HALT → Mac 通知（只提醒，不补跑：真钱只按定时任务）。
测试时用环境变量 QBREAK_NOW（ISO 时刻，按 JST）固定「现在」。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from . import paths
from .calendar_jp import JST, is_trading_day, now_jst, prev_trading_day

RUN_AFTER = dt.time(7, 40)
RETRY_AT, LIVE_UNTIL = dt.time(8, 35), dt.time(15, 30)     # 立花：08:35 的重试；15:30 之后不再提醒（下一个交易日照常）
NEWS, PAPER, LIVE = "com.qbreak.news", "com.qbreak.liveu.paper", "com.qbreak.liveu.morning"


def _morning_done(book: dict, expected_bar: str) -> bool:
    """今天早上的运行完成了吗：和 live_unified.morning_done 同一条规则（这里不 import 它：登录时的检查不加载 pandas，
    Python 环境坏了也能跑）。账本处理到应有的决策日、而且这个决策没有 PLANNED / BLOCKED 的单。"""
    st = (book or {}).get("state") or {}
    if st.get("last_date") != expected_bar:
        return False
    return not any(o.get("decided_on") == expected_bar and o.get("status") in ("PLANNED", "BLOCKED")
                   for o in (book or {}).get("orders") or [] if isinstance(o, dict))


def live_alert(now: dt.datetime, home: Path, running: bool) -> str | None:
    """立花本番（B12）：交易日 07:40〜15:30、今天早上的运行还没完成 → Mac 通知的文字；不用提醒 → None。
    执行器正在跑 / HALT 生效中（单本来就不下）→ 不提醒。只提醒，不补跑（真钱只按定时任务）。"""
    today = now.date()
    if not is_trading_day(today) or not (RUN_AFTER <= now.time() < LIVE_UNTIL) or running or (home / "HALT").exists():
        return None
    try:
        book = json.loads((home / "state" / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        book = {}
    if _morning_done(book if isinstance(book, dict) else {}, prev_trading_day(today).isoformat()):
        return None
    if now.time() < RETRY_AT:
        return ("今天立花早上的运行还没完成（可能还在等云端的数据）：08:35 的重试会再跑一次；登录时不补跑真钱的单")
    return ("今天立花早上的运行没有完成（08:35 的重试也没跑成？）：看操作面板顶部，或在 Mac 对话里说「看一下执行器日志」；"
            "登录时不补跑真钱的单")


def ran_today(home: Path, today: dt.date) -> bool:
    fp = home / "out" / "live_unified_paper.json"
    return fp.exists() and dt.datetime.fromtimestamp(fp.stat().st_mtime, JST).date() == today


def plan(now: dt.datetime, home: Path, agents: Path, loaded: set[str], running: bool) -> dict:
    """→ {"actions": [(动作, 参数)], "notes": [说明]}。动作：LOAD_NEWS / INSTALL_NEWS / RUN_PAPER / MAC_ALERT / OPEN。"""
    acts: list[tuple[str, str]] = []
    notes: list[str] = []
    news = agents / f"{NEWS}.plist"
    if NEWS not in loaded:
        acts.append(("LOAD_NEWS", str(news)) if news.exists() else ("INSTALL_NEWS", ""))
        notes.append("市场仪表盘没有在运行 → " + ("加载" if news.exists() else "安装"))
    today = now.date()
    live = (agents / f"{LIVE}.plist").exists()
    why = None
    if not (agents / f"{PAPER}.plist").exists():
        why = "没装模拟操盘的定时任务"
    elif (agents / f"{LIVE}.plist").exists():
        why = "装的是立花本番：登录时不补跑（真钱只按定时任务）"
    elif not is_trading_day(today):
        why = f"{today} 不是交易日"
    elif now.time() < RUN_AFTER:
        why = f"还没到 {RUN_AFTER:%H:%M}（到点定时任务会跑）"
    elif ran_today(home, today):
        why = "今天已经跑过"
    elif running:
        why = "执行器正在跑"
    if why is None:
        acts.append(("RUN_PAPER", ""))
        notes.append(f"今天（{today}）模拟操盘还没跑 → 补跑")
    else:
        notes.append(f"不补跑：{why}")
    if live:                                              # 立花本番：今天早上的运行没完成 → Mac 通知（不补跑）
        alert = live_alert(now, home, running)
        if alert:
            acts.append(("MAC_ALERT", alert))
            notes.append("立花本番：今天早上的运行还没完成 → Mac 通知（不补跑）")
    if (home / "NO_OPEN").exists():
        notes.append("有 NO_OPEN：不打开页面")
    else:
        book_page = home / "out" / ("page_tachibana.html" if live else "page_paper.html")   # 上线后打开立花的页面（B12）
        pages = ([] if why is None else [book_page]) + [home / "out" / "dashboard.html"]
        acts += [("OPEN", str(p)) for p in pages if p.exists()]
    return {"actions": acts, "notes": notes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=str(Path.home() / "Library" / "LaunchAgents"))
    ap.add_argument("--loaded", default="", help="launchctl list 里已加载的 com.qbreak.*（逗号分隔）")
    ap.add_argument("--running", default="0")
    a = ap.parse_args(argv)
    now = dt.datetime.fromisoformat(os.environ["QBREAK_NOW"]).replace(tzinfo=JST) if os.environ.get("QBREAK_NOW") else now_jst()
    p = plan(now, paths.home(), Path(a.agents), {x for x in a.loaded.split(",") if x}, a.running == "1")
    for n in p["notes"]:
        print(f"NOTE\t{n}")
    for act, arg in p["actions"]:
        print(f"{act}\t{arg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
