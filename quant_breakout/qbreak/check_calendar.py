"""check_calendar.py — 检查日历（2026-09-28 用户「依据现在的所有研究整理出一整个check时间线…结合实际的情况 横展开一下」；只展示，不改交易）。

全貌与每一项的来由：CHECK_TIMELINE.md。这里只把「有日期的检查」从今天往后排出来，日报「检查日历」一栏显示：
  ① 大事件日程 var/macro_events.json（季度复核按官方日期维护）里会引出检查的：日银 / FOMC（政策事件库录入）、短観（X2 与成本 × 销售换成新一次调查）、
     日経225 入替（资格检查）、选举 / 贸易 / 财政 / 国内政治（威胁指数 + 政策事件库）；
  ② 指数入替记录 var/index_changes.json 的公布日 / 生效日；
  ③ 固定规则：每月第一个交易日（月度记录）、季度复核（1 / 4 / 7 / 10 月 12 日）、日経225 定期入替的公布（3 月 / 9 月上旬）；
  ④ 事先写定的判定 / 评估日（模拟期结束、影子账户评估、W2 / K2 / USW 年度判定、K4、时代主线与 S2 的 36 / 60 个月）。
每一项：date、what（事项）、check（看什么 / 怎么做）、who（自动 / 例行任务 / Mac / 你）、src（依据）。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import paths

HORIZON_DAYS = 45

# 大事件的种类 → (看什么 / 怎么做, 谁, 依据)；没列的种类（CPI / NFP / SQ / OPEX / 峰会 / OPEC / 美国指数）只在日报「接下来的已知大事件」里提示
KIND_CHECK = {
    "BOJ": ("会后按日银官方公告在政策事件库分类录入（Mac：liveu.sh policy add），前向记录由 sim-day 自动记；交易规则不因会议改变（事件窗口关闭）",
            "你 / Mac Claude", "政策事件库 G1（policy_event_study.md）"),
    "FOMC": ("会后按美联储官方公告在政策事件库分类录入（美国当地日期）；威胁指数的美债利率项可能跳动（只展示）；交易规则不因会议改变",
             "你 / Mac Claude", "政策事件库 G1"),
    "TANKAN": ("短観公布：之后第 4 天起（4/5、7/5、10/5、12/20）买点前向记录的 X2 与「成本 × 销售」的销售数据换成这一次调查；月末的 S2 分组随之更新",
               "自动", "fund_study（X2）、cost_sales_study（S2）"),
    "ELECTION": ("大事件：看威胁指数 / 仪表盘；结果属于政策事件库的类别（关税、消费税、财政等）→ 录入", "自动 + 你", "威胁指数、政策事件库"),
    "TRADE": ("关税 / 贸易期限：属于政策事件库强类别（关税）→ 有决定就录入；看威胁指数的政策不确定性", "自动 + 你", "政策事件库 G1"),
    "FISCAL": ("财政期限 / 预算：看威胁指数；有税制决定（消费税等）→ 政策事件库录入", "自动 + 你", "政策事件库 G1"),
    "POLITICS": ("国内政治日程：有政策决定（消费税等）→ 政策事件库录入", "你 / Mac Claude", "政策事件库 G1"),
}
N225_WORDS = ("日経225", "日经225", "日経平均")
KIND_LABEL = {"BOJ": "日银会合", "FOMC": "FOMC", "TANKAN": "日银短観", "ELECTION": "选举", "TRADE": "贸易 / 关税", "FISCAL": "财政",
              "POLITICS": "国内政治"}

# 事先写定的判定 / 评估（日期 = 最早可以判的那天；到期后的第一次季度复核或例行任务里自动算）
MILESTONES = [
    ("2026-12-24", "模拟期最后一天（9/28〜12/24）", "按事先的格式总结（累计收益、最大回撤、交易笔数、胜率、与买入持有对比）→ 你决定继续 / 上实盘 / 调整", "你",
     "HANDOFF 路线图 5"),
    ("2026-12-25", "影子账户（判断型）3 个月评估", "例行任务 07:45 自动运行 shadow_account.py evaluate；只是记录，模拟盘不改；之后可以删这个例行任务", "例行任务",
     "scripts/shadow_account.py 第四节"),
    *[(f"{y}-09-28", f"W2 / K2 / USW 前向记录的第 {y - 2026} 次年度判定", "之后第一次季度复核（2f / 2i）自动算：W2「挡掉 − 保留」95% 区间下限 > 0 → 失效警报"
       " → 提议关 W2（你确认才改）；K2 / USW 证实也只是记录", "季度复核", "w2_forward / w2_forward_all / idio_forward") for y in range(2027, 2032)],
    ("2029-09-01", "时代主线、成本 × 销售 S2 前向记录记满 36 个月", "之后的复核开始判定：时代主线 95% 上限 < 0 → 失效；S2 平均 > 0 且 t ≥ 1.645 → 前向复现、平均 ≤ 0 → 没复现"
     "（都只改日报标签）", "季度复核 / 手动", "qbreak/era_forward.py、qbreak/cost_sales_forward.py"),
    ("2029-09-28", "K4（成品油需求 → 新仓减半）3 年判定", "energy_forward.py --review 前向成立 → 提议（你确认才改模拟盘）", "季度复核", "scripts/energy_forward.py"),
    ("2031-09-01", "成本 × 销售 S2 记满 60 个月（最后一次判定）", "仍未定 → 「证据不足」，维持只展示", "手动", "qbreak/cost_sales_forward.py"),
    ("2031-09-28", "K4 5 年判定", "同上", "季度复核", "scripts/energy_forward.py"),
]


def _is_trading(d: dt.date) -> bool:
    from .calendar_jp import is_trading_day
    return bool(is_trading_day(d))


def first_trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out, m = [], dt.date(start.year, start.month, 1)
    while m <= end:
        d = m
        while not _is_trading(d):
            d += dt.timedelta(days=1)
        if start <= d <= end:
            out.append(d)
        m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


def _events(path: Path | None = None) -> list[dict]:
    fp = Path(path or (paths.PROJECT_ROOT / "var" / "macro_events.json"))
    try:
        return (json.loads(fp.read_text(encoding="utf-8")) or {}).get("events") or []
    except Exception:                                                    # noqa: BLE001
        return []


def _changes() -> list[dict]:
    from .universes import index_changes
    return index_changes("JP")


def items(today: dt.date, horizon: int = HORIZON_DAYS, events=None, changes=None) -> list[dict]:
    """今天〜今天 + horizon 天里有日期的检查（按日期排）。"""
    end = today + dt.timedelta(days=horizon)
    out: list[dict] = []
    within = lambda s: today.isoformat() <= str(s)[:10] <= end.isoformat()                      # noqa: E731
    for e in (events if events is not None else _events()):
        kind, d, name = e.get("kind"), str(e.get("date") or "")[:10], str(e.get("name") or "")
        if not d or not within(d):
            continue
        if kind == "INDEX" and e.get("home") == "JP" and any(w in name for w in N225_WORDS):
            out.append({"date": d, "what": f"日経225 入替：{name}", "who": "自动 + 例行任务", "src": "qbreak/eligibility.py（G2）",
                        "check": "var/index_changes.json 有这次入替吗（没有 → 例行任务按公告原文录入）；公布日起待剔除股不开新仓、生效日起股票池自动增删；"
                                 "日报「下单前资格检查」看名单对照"})
        elif kind in KIND_CHECK:
            chk, who, src = KIND_CHECK[kind]
            out.append({"date": d, "what": f"{KIND_LABEL.get(kind, kind)}：{name}".rstrip("："),
                        "who": who, "src": src, "check": chk})
    for c in (changes if changes is not None else _changes()):
        for key, lab in (("announced", "公布（待剔除股从今天起不开新仓）"), ("effective", "生效（股票池自动增删）")):
            d = str(c.get(key) or "")[:10]
            if d and within(d):
                out.append({"date": d, "what": f"日経225 入替{lab}：+{'/'.join(c.get('add') or [])} −{'/'.join(c.get('delete') or [])}",
                            "who": "自动", "src": "var/index_changes.json", "check": "日报「下单前资格检查」确认待剔除 / 新纳入的票；持仓里有待剔除股 → 规则照常持有到出场信号"})
    for d in first_trading_days(today, end):
        out.append({"date": d.isoformat(), "what": "月度记录（每月第一个交易日）", "who": "自动（sim-day）",
                    "src": "qbreak/era_forward.py、qbreak/cost_sales_forward.py、qbreak/energy_now.py",
                    "check": "日报：时代主线记上个月末的排名；「成本 × 销售」换成上个月末的分组（原材料在涨吗、偏间接 / 偏直接）并追加前向记录；能源消费一栏"})
    y = today.year
    for yy in (y, y + 1):
        for m in (1, 4, 7, 10):
            d = dt.date(yy, m, 12)
            if within(d):
                extra = "；1 月另重估威胁指数配比、主题影响度加一年" if m == 1 else ""
                out.append({"date": d.isoformat(), "what": "季度复核（例行任务 09:56 JST）", "who": "例行任务 → 你看汇报",
                            "src": "季度复核例行任务（2〜2k）", "check": "汇报第一行有没有「★ …需要用户确认」（顶底、前瞻观察、威胁指数、配比、质量分 / W2、新联动群 / 新上市、"
                                                                      f"K4、时代主线、政策事件）{extra}"})
        for m, lab in ((3, "春季（4 月生效）"), (9, "秋季（10 月生效）")):
            d = dt.date(yy, m, 1)
            if within(d):
                out.append({"date": d.isoformat(), "what": f"日経225 定期入替的公布期（{lab}，通常上旬；日期以日经公告为准）", "who": "例行任务 → 自动",
                            "src": "qbreak/eligibility.py（G2）", "check": "公布后例行任务按公告原文录入 var/index_changes.json；之后资格检查自动挡待剔除股的新仓"})
    for d, what, chk, who, src in MILESTONES:
        if within(d):
            out.append({"date": d, "what": what, "check": chk, "who": who, "src": src})
    return sorted(out, key=lambda x: (x["date"], x["what"]))


def upcoming_milestones(today: dt.date, n: int = 3) -> list[dict]:
    """远期的判定 / 评估（今天之后最近的 n 个）。"""
    rows = [{"date": d, "what": what, "check": chk, "who": who, "src": src} for d, what, chk, who, src in MILESTONES if d > today.isoformat()]
    return sorted(rows, key=lambda x: x["date"])[:n]


def panel(today: dt.date) -> dict:
    return {"as_of": today.isoformat(), "horizon_days": HORIZON_DAYS, "items": items(today), "milestones": upcoming_milestones(today)}
