"""mac_login.py — Mac 登录 / 开机时的自动启动（LaunchAgent com.qbreak.login，RunAtLoad；由 scripts/liveu.sh login 调用）。

这里只决定要做什么（打印「动作<TAB>参数」，liveu.sh 照着执行）：
- 市场仪表盘 com.qbreak.news 没加载 → 加载（plist 不在 → 安装）
- 模拟操盘补跑（RUN_PAPER）：今天是日本交易日、已过 07:40 JST、今天还没跑成（<数据目录>/out/live_unified_paper.json 的修改日期不是今天）、
  装的是模拟操盘（com.qbreak.liveu.paper）且没装立花本番（com.qbreak.liveu.morning）、现在没有执行器在跑 → liveu.sh run --broker paper。
  模拟账户同一决策日重复运行不会重复下单；立花本番（真钱）永远不在登录时补跑。
- 打开账本页面 page_paper.html 与市场仪表盘 dashboard.html（数据目录里有 NO_OPEN 就不打开；补跑本身会打开账本页面，不重复打开）。
测试时用环境变量 QBREAK_NOW（ISO 时刻，按 JST）固定「现在」。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path

from . import paths
from .calendar_jp import JST, is_trading_day, now_jst

RUN_AFTER = dt.time(7, 40)
NEWS, PAPER, LIVE = "com.qbreak.news", "com.qbreak.liveu.paper", "com.qbreak.liveu.morning"


def ran_today(home: Path, today: dt.date) -> bool:
    fp = home / "out" / "live_unified_paper.json"
    return fp.exists() and dt.datetime.fromtimestamp(fp.stat().st_mtime, JST).date() == today


def plan(now: dt.datetime, home: Path, agents: Path, loaded: set[str], running: bool) -> dict:
    """→ {"actions": [(动作, 参数)], "notes": [说明]}。动作：LOAD_NEWS / INSTALL_NEWS / RUN_PAPER / OPEN。"""
    acts: list[tuple[str, str]] = []
    notes: list[str] = []
    news = agents / f"{NEWS}.plist"
    if NEWS not in loaded:
        acts.append(("LOAD_NEWS", str(news)) if news.exists() else ("INSTALL_NEWS", ""))
        notes.append("市场仪表盘没有在运行 → " + ("加载" if news.exists() else "安装"))
    today = now.date()
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
    if (home / "NO_OPEN").exists():
        notes.append("有 NO_OPEN：不打开页面")
    else:
        pages = ([] if why is None else [home / "out" / "page_paper.html"]) + [home / "out" / "dashboard.html"]
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
