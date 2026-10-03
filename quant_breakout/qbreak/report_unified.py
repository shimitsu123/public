"""report_unified.py — 一个账户（日元 + 美元）的模拟盘日报：今天要做的事（按日本时间）、持仓、核心 ETF、权益曲线、成交与换汇。

数据来自 var/state/unified_state.json（推进器状态）与 var/out/unified_today.json（今天的操作与市场状态）。
写 var/out/report.html（例行任务发布到同一个 Artifact）与 var/out/report_data.json。
"""
from __future__ import annotations

import datetime as dt
import json
from html import escape
from pathlib import Path

from . import paths
from .calendar_jp import now_jst
from .fees import BROKERS, broker_of
from .unified import config_from_sim
from .utils import read_json


def _us_open_jst(d: dt.date) -> str:
    """美股常规交易开盘的日本时间：夏令时 22:30，冬令时 23:30（美国夏令时：3 月第 2 个周日 ～ 11 月第 1 个周日）。"""
    y = d.year
    mar = dt.date(y, 3, 8) + dt.timedelta(days=(6 - dt.date(y, 3, 8).weekday()) % 7)
    nov = dt.date(y, 11, 1) + dt.timedelta(days=(6 - dt.date(y, 11, 1).weekday()) % 7)
    return "22:30" if mar <= d < nov else "23:30"


def build_unified_data() -> dict:
    st = read_json(paths.state_dir() / "unified_state.json", {}) or {}
    td = read_json(paths.out_dir() / "unified_today.json", {}) or {}
    sim = read_json(paths.home() / "sim.json", {}) or {}
    hist = st.get("history") or []
    cap = float(sim.get("capital_jpy") or 1_000_000)
    eq = float(hist[-1][1]) if hist else float(td.get("equity_jpy") or cap)
    fx = float(hist[-1][4]) if hist and hist[-1][4] else (float(td["usdjpy"]) if td.get("usdjpy") else None)
    peak, mdd = cap, 0.0
    for h in hist:
        peak = max(peak, float(h[1]))
        mdd = min(mdd, float(h[1]) / peak - 1)
    trades = st.get("trades") or []
    wins = [t for t in trades if float(t.get("pnl_jpy") or 0) > 0]
    d = {"generated": now_jst().strftime("%Y-%m-%d %H:%M JST"), "mode": "unified", "sim": sim,
            "capital_jpy": cap, "equity_jpy": eq, "ret_pct": round((eq / cap - 1) * 100, 2), "max_dd_pct": round(mdd * 100, 2),
            "cash_jpy": st.get("cash_jpy") if st else td.get("cash_jpy"),       # 开始前：预览给的初始现金
            "cash_usd": st.get("cash_usd") if st else td.get("cash_usd"), "usdjpy": fx,
            "usdjpy_src": "模拟盘状态" if hist and hist[-1][4] else td.get("usdjpy_src"),
            "preview": bool(td.get("preview")) and not hist, "data_dates": td.get("data_dates") or {},
            "lagging": td.get("lagging") or {},
            "bar_date": st.get("last_date"),
            "positions": td.get("positions") or {}, "core_units": st.get("core_units") or {},
            "core_last": st.get("core_last") or {}, "todo": td.get("todo") or {}, "extras": td.get("extras") or {},
            "history": hist, "trades": trades[-30:], "fx_trades": (st.get("fx_trades") or [])[-15:],
            "core_trades": (st.get("core_trades") or [])[-15:], "n_trades": len(trades),
            "corp_log": (st.get("corp_log") or [])[-10:],
            "threat": td.get("threat") or read_json(paths.out_dir() / "threat_today.json", {}) or {},
            "executor": td.get("executor") or {},                # 实盘执行器的演练账户（模拟券商）与模拟盘的逐日比较
            "score_forward": td.get("score_forward") or {},      # 买点质量分的前向记录（只记录，不影响交易）
            "themes": td.get("themes") or {},                    # 主题 / 业种强弱、影响度、新出现的联动（只作展示）
            "macro_now": td.get("macro_now") or {},              # 仪表盘：市场健康度 + 消费 / 零售等新数据（只作展示）
            "news": td.get("news") or {},                        # 仪表盘：经济威胁消息的汇总（只作展示；标题不入库）
            "energy": td.get("energy") or {},                    # 仪表盘：能源消费（每月）+ K4 前向记录的状态（只作展示 / 记录）
            "era": td.get("era") or {},                          # 时代主线前向记录的状态（qbreak/era_forward.py；只记录）
            "deepdip": td.get("deepdip") or {},                  # 「≤ −15% 深跌」前向记录（qbreak/deepdip_forward.py；只记录 / 展示）
            "policy": td.get("policy") or {},                    # 政策事件反应库（qbreak/policy_forward.py；只展示 + 前向记录）
            "eligibility": td.get("eligibility") or {},          # 下单前资格检查（qbreak/eligibility.py：被踢出 / 被指定的票不开新仓）
            "delist": td.get("delist") or {},                    # 股票池更新时间表（qbreak/delist_schedule.py：上場廃止到日自动去掉）
            "cost_sales": td.get("cost_sales") or {},            # 成本 × 销售（S2）分组与前向记录（qbreak/cost_sales_forward.py；只展示）
            "invest_flow": td.get("invest_flow") or {},          # 投资流向的季度快照（㉟，qbreak/invest_flow.py；只作背景）
            "interest_burden": td.get("interest_burden") or {},  # 企业利息负担的季度快照（㊶ ③，qbreak/interest_burden.py；仪表盘里只作背景）
            "timeline": td.get("timeline") or {},                  # 买卖时间线（qbreak/timeline.py；每天按前一天收盘重算，只展示）
            "earn_state": td.get("earn_state") or {},              # 最近一次决算的形态（qbreak/earn_state.py，㊱；只展示）
            "calendar": td.get("calendar") or {},                # 检查日历（qbreak/check_calendar.py；只展示，全貌 CHECK_TIMELINE.md）
            "price_check": td.get("price_check") or {},          # 行情交叉核对（qbreak/price_check.py；yfinance × J-Quants，只报警）
            "fwdj": td.get("fwdj") or {},                        # 前向记录判断层（qbreak/fwd_judgment.py；2026-09-30 起影响日本个股新仓）
            "combo_c": td.get("combo_c") or {},                  # 关联搭配 C（qbreak/combo_c.py；2026-10-01 的决策起影响日本个股新仓）
            "exit_mode": td.get("exit_mode") or {},              # 个股的离场方式（qbreak/exit_rules.py；var/sim.json exits）
            "idle_cash": td.get("idle_cash") or {},              # 闲置资金的方式与现在拿什么（qbreak/idle_cash.py；var/sim.json idle_cash）
            "survey_failed": td.get("survey_failed") or {},      # 因子调查取不到的数据源（qbreak/survey.LAST_FAILED）
            "shadow": read_json(paths.out_dir() / "shadow_today.json", {}) or {},   # 影子账户（判断型，只前向记录，不影响交易）
            "commod": _commod_rows(),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else None,
            "config": td.get("config") or config_from_sim(sim).to_dict(),     # 首次运行前从 sim.json 取
            "broker": td.get("broker") or broker_of("JP", sim.get("unified")), "skipped": td.get("skipped") or {},
            # 例行任务（旧提示按分市场日报写）也能找到：markets.<市场>.regime.bullbear / watchlist
            "markets": {m: {"regime": e.get("regime") or {}, "macro": e.get("macro") or {},
                            "watchlist": e.get("watchlist") or [], "core_only": e.get("core_only")}
                        for m, e in (td.get("extras") or {}).items()},
            "hint": ("一个账户模式：账户数值在顶层（equity_jpy / ret_pct / max_dd_pct / cash_jpy / cash_usd / positions / "
                     "core_units×core_last / todo / trades / core_trades / fx_trades / corp_log）；当日损益 = history 最后两行的权益差；"
                     "牛熊分界在 markets.JP.regime.bullbear（日経）与 markets.US.regime.bullbear（S&P500，只用于核心 ETF 的择时：基准账户的 1655、"
                     "闲置资金方式跟美股分界时的那只 ETF，见 idle_cash），"
                     "其中 phase_label / phase_text = 现在处于哪个阶段（牛·稳固 / 牛·走弱 / 牛→熊确认中 / 熊·回升 …）"
                     "与直观百分比（离 250 日线的距离、20 个交易日的变化、还要跌 / 涨多少才翻转），汇报时先写这个；"
                     "候补队列在 markets.JP.watchlist；todo 的个股买单与候补队列的 breakout / to_box_top_pct = 「真突破」标签"
                     "（收盘是否高于过去 60 日最高、距箱顶 %；只作参考，不改交易）；大事件威胁指数在 threat（只展示，不参与交易）；"
                     "主题 / 业种强弱在 themes.groups（r1m / r3m = 近 1 / 3 个月相对 TOPIX 1000 平均的 %，rank3m / of = 排名，"
                     "r12 / rank12 / of12 = 时代主线（12 个月、跳过最近 1 个月）与排名，"
                     "r2_now / r2_hist = 与日経225 的同步度 R²）与 themes.emerging（新出现的联动群 clusters、个股 links；只作展示，不改交易）；"
                     "missing = 日报应有而没取到的数据（项目 + 原因），汇报时逐项列出；"
                     "仪表盘数据在 macro_now（health.tiles = 市场健康度、releases = 消费 / 零售等新公布的数据）与 news.summary"
                     "（经济威胁消息的汇总），都只作展示、不参与交易；能源消费在 energy（rows = 18 个来源的 3 个月同比 value %、"
                     "历史分位 pct、偏弱 / 偏强 state、同期一起动的行业 links；k4 = K4 前向观察的状态，forward = 前向记录的天数），只作展示 / 记录。")}
    d["missing"] = missing_items(d)
    d["fixed"] = fixed_items(d)
    return d


_MNAME = {"JP": "日本（日経225）", "US": "美股（S&P500）"}


def fixed_items(d: dict) -> list[str]:
    """数据层自动修好的（不算缺，写在「数据完整性」下面让你看得见）：指数日线用分钟线合成、拆股当天的分红口径修正、能被分红解释的比值变化。"""
    out = []
    for k, v in sorted((d.get("filled") or {}).items()):
        ds = "、".join(v.get("dates") or [])
        c = v.get("close")
        out.append(f"{k} {ds} 的日线 Yahoo 没给收盘（只有开盘）→ 用当天的 5 分钟线合成（收盘 {c:,.2f}；与正式收盘可能差 0.1% 以内，"
                   "正式日线到了会自动换掉）—— 指数 / 核心 ETF 判断与判断层市场读数按合成的收盘" if isinstance(c, (int, float))
                   else f"{k} {ds} 的日线用 5 分钟线合成")
    for f in d.get("data_fixes") or []:
        out.append(f"{f.get('ticker')} {f.get('date')}：拆股 1 拆 {f.get('split'):g} 当天的分红 {f.get('div'):g} 円是拆股前每股的金额，Yahoo 当成 "
                   f"{f.get('yield_yahoo'):.1f}% 的分红把之前的价格整体调低 → 已改按拆股后口径 {f.get('yield_fixed'):.2f}% 调整（60 日箱体 / MACD / 止损参考按修正后的价格）")
    pc = d.get("price_check") or {}
    dv = [x for x in (pc.get("info") or []) if x.get("kind") == "dividend"]
    n_dv = (pc.get("info_counts") or {}).get("dividend", len(dv))
    if n_dv:
        big = [f"{x['ticker']} {x['date']} {x['yield_pct']:.1f}%" for x in dv[:3]]
        out.append(f"行情交叉核对：{n_dv} 只的比值变化能被当天的分红解释（例 {'、'.join(big)}）—— yfinance 按分红调整、J-Quants 不调，不是错位")
    return out


def missing_items(d: dict) -> list[str]:
    """日报应有而没取到的数据（项目：原因）。写在日报顶部；例行任务汇报时逐项列出，避免静默缺数据。"""
    out = []
    sim, cfg = d.get("sim") or {}, d.get("config") or {}
    started, preview = bool(d.get("history")), bool(d.get("preview"))
    if not started and not preview:
        out.append(f"账户数值、市场状态、候补队列：模拟盘还没有运行过（开始日 {sim.get('start') or '—'}），开始前的预览也没有运行")
    if started and not d.get("bar_date"):
        out.append("数据截至日期：账户状态里没有")
    if d.get("usdjpy") is None:
        out.append("USD/JPY：账户状态、Yahoo、FRED、市场风险报告都没取到")
    usd = "US" in (BROKERS.get(d.get("broker") or "", {}).get("markets") or {"US": 1})
    for key, label in (("cash_jpy", "日元现金"), ("cash_usd", "美元现金"))[:2 if usd else 1]:
        if d.get(key) is None and (started or preview):
            out.append(f"{label}：账户状态里没有")
    ex = d.get("extras") or {}
    if started or preview:
        for m in list(cfg.get("stock_markets") or []) + sorted(set((cfg.get("core_index") or {}).values())):
            e = ex.get(m) or {}
            if not e:
                out.append(f"{_MNAME.get(m, m)} 市场状态：没有算出")
                continue
            bb = (e.get("regime") or {}).get("bullbear") or {}
            if bb.get("state") in (None, "unknown"):
                out.append(f"{_MNAME.get(m, m)} 牛熊分界：{bb.get('note') or '指数行情取不到'}")
            if m in (cfg.get("stock_markets") or []) and not e.get("watchlist"):
                out.append(f"{_MNAME.get(m, m)} 候补队列：空（股票池行情取不到或生成失败，见运行日志）")
    lag = d.get("lagging") or {}
    idx = {k: v for k, v in lag.items() if k.startswith("^") or k in ((cfg.get("core") or {}))}
    for k, v in idx.items():
        out.append(f"行情落后：{k} 最新 {v['last']}，应有 {v['expected']}（已重新下载仍缺，指数 / 核心 ETF 相关判断按旧数据）")
    stocks = sorted(k for k in lag if k not in idx)
    if stocks:
        out.append(f"行情落后：个股 {len(stocks)} 只（例 {'、'.join(stocks[:3])} 最新 {lag[stocks[0]]['last']}，"
                   f"应有 {lag[stocks[0]]['expected']}），候补队列里这些股票用的是旧收盘")
    t = d.get("threat") or {}
    if not t or t.get("error"):
        out.append(f"大事件威胁指数：{t.get('error') or '没有算出'}")
    th = d.get("themes") or {}
    if (started or preview) and (th.get("error") or not th.get("groups")):
        out.append(f"主题 / 业种强弱：{th.get('error') or '没有算出'}（只作展示，不影响交易）")
    for k, lab in (("macro_now", "一眼看懂的市场健康度 / 新公布的数据"), ("news", "一眼看懂的经济威胁消息"), ("energy", "能源消费（每月）")):
        v = d.get(k) or {}
        if v.get("error"):
            out.append(f"{lab}：{v['error']}（只作展示，不影响交易）")
    en = d.get("energy") or {}
    if started and not en.get("error"):
        miss = [r["name"] for r in en.get("rows") or [] if r.get("value") is None]
        if miss:
            out.append(f"能源消费（每月）：{len(miss)} 个来源没取到（{'、'.join(miss[:4])}{'…' if len(miss) > 4 else ''}）（只作展示，不影响交易）")
        fe = (en.get("forward") or {}).get("error")
        if fe:
            out.append(f"K4 前向记录：今天没记上（{fe}）—— 不影响交易，不补写")
    sf = d.get("score_forward") or {}
    if started and sf.get("error"):
        out.append(f"买点质量分前向记录：今天没记上（{sf['error']}）—— 不影响交易，下次运行会补最近 5 个交易日")
    if started and sf.get("wide_error"):
        out.append(f"买点质量分前向记录（扩大池）：今天没记上（{sf['wide_error']}）—— 不影响交易，下次运行会补最近 5 个交易日")
    if started and sf.get("x2_error"):
        out.append(f"买点质量分前向记录的 X2（短観）：取不到（{sf['x2_error']}）—— 今天记下的信号 X2 为空（不补写），不影响交易")
    if started and sf.get("idio_error"):
        out.append(f"买点质量分前向记录的 K2 / USW：部分输入取不到（{sf['idio_error']}）—— 今天记下的信号里对应的列为空（不补写），不影响交易")
    if started and sf.get("cc_error"):
        out.append(f"买点质量分前向记录的关联搭配 C：部分输入取不到（{sf['cc_error']}）—— 今天记下的信号市场格为空（不补写），不影响交易")
    cc = d.get("combo_c") or {}
    if cc.get("enabled") and not cc.get("applied"):
        out.append(f"关联搭配 C 今天没生效：{cc.get('why') or '—'} —— 明天的新仓按原规则（不跳过任何票）")
    elif cc.get("enabled") and cc.get("errors"):
        out.append("关联搭配 C 有算不了的项（按 0 票 / 这一天 C 不动）：" + "；".join(f"{k}：{v}" for k, v in cc["errors"].items()))
    ef = d.get("era") or {}
    if started and ef.get("error"):
        out.append(f"时代主线前向记录：这次没记上（{ef['error']}）—— 不影响交易；这个月不补写，下个月第一次运行照常记")
    if started and ef.get("us_error"):
        out.append(f"时代主线前向记录的美国 49 行业：取不到（{ef['us_error']}）—— 只记了日本；下次取到时记最新的月份（不补写），不影响交易")
    dd = d.get("deepdip") or {}
    if started and dd.get("error"):
        out.append(f"深跌前向记录（≤ −15%）：这次没算 / 没记上（{dd['error']}）—— 不影响交易；下次运行会按行情补上漏掉的事件")
    infl = (d.get("themes") or {}).get("influence") or {}
    if started and infl.get("error"):
        out.append(f"各业种影响占比（J-Quants 東証業種別指数）：取不到（{infl['error']}）—— 时代主线旁边不标占比，不影响交易")
    pf = d.get("policy") or {}
    if started and pf.get("error"):
        out.append(f"政策事件反应库：这次没算 / 没记上（{pf['error']}）—— 不影响交易；前向记录不补写")
    if started and (pf.get("status") or {}).get("pending"):
        out.append(f"政策事件反应库：{pf['status']['pending']} 个已过去的日银 / FOMC 日程还没有分类录入（待分类，Mac 上 `bash scripts/liveu.sh policy add …`）")
    ck = d.get("calendar") or {}
    if started and ck.get("error"):
        out.append(f"检查日历：这次没排出来（{ck['error']}）—— 只作展示，不影响交易")
    cs = d.get("cost_sales") or {}
    if started and cs.get("error"):
        out.append(f"成本 × 销售（S2）：这次没算出（{cs['error']}）—— 只作展示，不影响交易；前向记录下次运行再记（不补写）")
    tl = d.get("timeline") or {}
    if started and tl.get("error"):
        out.append(f"买卖时间线：这次没算出（{tl['error']}）—— 只作展示，不影响交易")
    es = d.get("earn_state") or {}
    hard = {k: v for k, v in (es.get("errors") or {}).items() if not str(v).startswith("用了缓存")}
    if started and hard:
        k0 = next(iter(hard))
        out.append(f"最近一次决算的形态：{len(hard)} 项取不到（例 {k0}：{hard[k0]}）—— 那几只不标形态；只作展示，不影响交易")
    el = d.get("eligibility") or {}
    if el.get("error") and not el.get("sources"):
        out.append(f"下单前资格检查的日报块：没算出（{el['error']}）—— 闸门本身在引擎里照常生效")
    for n in el.get("needs_user") or []:
        out.append(f"下单前资格检查（告警，不是缺数据）：{n}")
    ds = d.get("delist") or {}
    if ds.get("error"):
        out.append(f"股票池更新时间表：这次没更新（{ds['error']}）—— 上一次的表照常生效（已到日去掉的不变）")
    for n in ds.get("needs_user") or []:
        out.append(f"股票池更新时间表（告警，不是缺数据）：{n}")
    fj = d.get("fwdj") or {}
    if started and fj.get("enabled"):                              # 前向记录判断层：算不了的项按中性（0）；日期对不上 → 这一层今天没生效
        for k, v in (fj.get("errors") or {}).items():
            out.append(f"前向记录判断层：{v}" if k == "生效" else
                       f"前向记录判断层的「{k}」：取不到（{v}）—— 这一项按中性（0 分），其余照常")
        if (fj.get("baseline") or {}).get("error"):
            out.append(f"前向记录判断层的基准账户（不加判断层的对照）：这次没走（{fj['baseline']['error']}）—— 不影响模拟盘")
        md = (fj.get("market") or {}).get("date")
        if md and fj.get("as_of") and md != fj.get("as_of") and "市场层读数" not in (fj.get("errors") or {}):
            out.append(f"前向记录判断层的市场层读数用的是 {md} 的（{fj['as_of']} 的日経225 K 线当时还没有，最多落后 1 个交易日）—— 各项照常计分")
    sv = d.get("survey_failed") or {}
    if started and sv:
        out.append(f"因子调查的数据源取不到 {len(sv)} 个（{'、'.join(list(sv)[:4])}{'…' if len(sv) > 4 else ''}）—— 威胁指数前向记录的 S / A0+Wj、"
                   "日経前瞻观察 Wj 今天不算（不拿少了因素的版本凑数，不补写）；判断层对应的项按中性")
    if started:
        from .price_check import summary_lines
        out += summary_lines(d.get("price_check") or {})             # 行情交叉核对（J-Quants，只报警）：没做 / 取不到 / 告警
    x = d.get("executor") or {}
    if started and x.get("error"):
        out.append(f"实盘执行器演练账户：运行失败（{x['error']}）—— 不影响模拟盘，但实盘要走的那条路今天没验证")
    elif started and x and x.get("same_as_sim") is False:
        diff = x.get("equity_diff_jpy")
        out.append("实盘执行器演练账户与模拟盘不一致（执行器告警，不是缺数据）："
                   + (f"权益差 {'+' if diff >= 0 else '−'}¥{abs(diff):,.0f}" if diff is not None else "持仓 / 现金不同")
                   + " —— 实盘要走的那条路（下单 → 券商回报 → 对账）有问题，见 var/out/live_unified_paper.json")
    mr = read_json(paths.home() / "market_regime.json", {}) or {}
    for m in cfg.get("stock_markets") or ["JP"]:                   # 判断层只影响做个股的市场的新仓倍数
        if not (mr.get(m) or {}).get("action"):
            out.append(f"{_MNAME[m]} 市场风险报告的判断层（行动四选一）：没取到（按量化层单独判断）")
    ref = pd_date(d.get("data_dates", {}).get("JP")) or pd_date(d.get("bar_date")) or now_jst().date()
    asof = pd_date(mr.get("as_of"))
    if asof and (ref - asof).days > 4:
        out.append(f"市场风险报告的判断层：已过期（{asof}，数据日 {ref}）")
    mj = read_json(paths.home() / "macro.json", {}) or {}
    nulls = [k for k in ("brent", "wti", "us10y", "us2y", "vix", "hy_oas_bp", "usdjpy", "jgb10y") if mj.get(k) is None]
    if nulls:
        out.append("宏观数值（市场风险报告）缺：" + "、".join(nulls))
    return out


def pd_date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


_STATUS = {"triggered": "已触发", "imminent": "即将", "watch": "观察", "far": "远"}


def _bo_tag(o: dict) -> str:
    """「真突破」标签（只作展示，不改交易）。买单 / 已触发：真突破 或 未破箱顶（差 x%）；还没触发：距箱顶 x%。
    没有这个字段（旧数据、核心 ETF、卖单）→ 空。"""
    if "breakout" not in o:
        return ""
    x = o.get("to_box_top_pct")
    if o.get("status", "triggered") == "triggered":
        if o.get("breakout"):
            return '<span class="tag">真突破</span>'
        return '<span class="tag dim">未破箱顶' + (f"（差 {float(x):.1f}%）" if x is not None else "") + "</span>"
    if x is None:
        return '<span class="muted">—</span>'
    x = float(x)
    return f'<span class="muted">{"已在箱顶上方 " + format(-x, ".1f") if x < 0 else "距箱顶 " + format(x, ".1f")}%</span>'


def _timeline_card(d: dict) -> str:
    """买卖时间线卡片；时间线数据缺键 / 坏了 → 只这一块显示原因，不让整份日报失败。"""
    try:
        return _timeline_card_inner(d)
    except Exception as e:                                                # noqa: BLE001
        return f"<section class='card' id='timeline'><h2>买卖时间线</h2><p class='muted'>这次没画出（{escape(f'{type(e).__name__}: {e}'[:160])}）</p></section>"


def _timeline_card_inner(d: dict) -> str:
    """买卖时间线（qbreak/timeline.py；每天按前一天收盘重算，只展示）。旧数据没有这个字段 → 不显示。"""
    tl = d.get("timeline")
    if not tl:
        return ""
    from .earn_state import tag_html
    from .timeline import html as tl_html
    return f"<section class='card' id='timeline'>{tl_html(tl, tag_html)}</section>"


def _money(v, ccy="JPY") -> str:
    if v is None:
        return "—"
    return f"${float(v):,.2f}" if ccy == "USD" else f"¥{float(v):,.0f}"


def _fxr(v) -> str:
    """汇率带单位。"""
    return "—" if not v else f"{float(v):.2f} 円/USD"


def _lvl(v, market: str) -> str:
    """指数点位带单位：日経平均按「円」，S&P500 按「pt」。"""
    if v is None:
        return "—"
    return f"{float(v):,.0f} 円" if market == "JP" else f"{float(v):,.1f} pt"


def _pct(v, nd: int = 1, sign: bool = False) -> str:
    if v is None or v != v:
        return "—"
    return f"{float(v):+.{nd}f}%" if sign else f"{float(v):.{nd}f}%"


_QLAB = {"risk_on": "偏多（站上 200 日线、波动低、回撤小）", "neutral": "中性", "risk_off": "偏空（跌破 200 日线 / 回撤大 / 波动大）",
         "unknown": "未知"}
_BB = {"bull": "牛市", "bear": "熊市", "unknown": "未知"}


def _spark(hist: list, w: int = 640, h: int = 120) -> str:
    ys = [float(x[1]) for x in hist]
    if len(ys) < 2:
        return '<p class="muted">权益曲线：数据还不够两天</p>'
    lo, hi = min(ys), max(ys)
    rng = (hi - lo) or 1.0
    pts = " ".join(f"{i * (w - 8) / (len(ys) - 1) + 4:.1f},{h - 6 - (y - lo) / rng * (h - 12):.1f}" for i, y in enumerate(ys))
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" role="img" aria-label="权益曲线">'
            f'<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="{pts}"/></svg>'
            f'<div class="muted">{escape(hist[0][0])} ～ {escape(hist[-1][0])}：{_money(ys[0])} → {_money(ys[-1])}</div>')


def _has_usd(broker: str | None) -> bool:
    """该券商的账户有没有美元（楽天：日元 + 美元；立花：只有日元，只做东证）。"""
    return "US" in ((BROKERS.get(broker or "") or {}).get("markets") or {"US": 1})


def _acct(broker: str | None, with_us: bool) -> str:
    lab = (BROKERS.get(broker or "") or {}).get("label") or "楽天証券"
    return f"{lab}，日元 + 美元" if _has_usd(broker) else f"{lab}，日元，只做东证"


def _fee_rule(broker: str | None, cfg: dict) -> str:
    """规则栏的手续费说明（与 qbreak/fees.py 同一份费用表）。"""
    b = BROKERS.get(broker or "") or {}
    if broker == "tachibana":
        tiers = "、".join(f"≤{int(cap) // 10000} 万 ¥{int(fee)}" for cap, fee in (b["markets"]["JP"]["commission_tiers"])[:4])
        return (f"{b['label']} 個別コース：每笔按约定金额 {tiers}…（ETF 同表；新开户前 60 个营业日 0 円未计入；{b.get('checked')} 核对）；"
                "只做东证（不做美股、不换汇），1655.T 用日元在东京开盘时买卖；API 可无人值守自动下单"
                "（15:30～16:30 值洗い期间不受理，之后受理翌营业日的单）。")
    return (f"楽天：日本株 / 东证 ETF 0 円，美股 0.495%（上限 $22），换汇 片道 {round(float(cfg.get('fx_spread_yen', 0.25)) * 100):g} 銭/USD；"
            "美股卖出后的美元在下一个换汇窗口换回日元。")


def _bar_txt(d: dict) -> str:
    if d.get("bar_date"):
        return f"{d['bar_date']}（日本收盘 + 美股收盘都已知的最后一天）"
    dd = d.get("data_dates") or {}
    if dd:
        return "、".join(f"{'日本' if m == 'JP' else '美股'} {v} 收盘" for m, v in dd.items() if v) + "（开始前的预览）"
    return "—（还没有运行过）"


def _missing_html(items: list[str], fixed: list[str] | None = None) -> str:
    fx = ("<details><summary>自动修复 " + str(len(fixed)) + " 项（不算缺）</summary><ul>"
          + "".join(f"<li>{escape(x)}</li>" for x in fixed) + "</ul></details>") if fixed else ""
    if not items:
        return '<div class="muted">数据完整性：日报需要的数据都取到了' + ("；" + fx if fx else "") + "</div>"
    return ("<div class=\"card warn\"><b>数据完整性：缺 " + str(len(items)) + " 项</b><ul>"
            + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>" + fx + "</div>")


def _executor_html(d: dict) -> str:
    """实盘执行器的演练账户（模拟券商，qbreak/live_unified.py）：每天与模拟盘同一套行情走一遍，比较结果。"""
    x = d.get("executor") or {}
    if not x or not d.get("history"):
        return ""
    if x.get("error"):
        return f'<div class="muted">实盘执行器演练账户：<b class="neg">运行失败</b>（{escape(str(x["error"]))}）</div>'
    ok = x.get("same_as_sim")
    diff = x.get("equity_diff_jpy")
    txt = ("与模拟盘一致（持仓、1655、现金、权益）" if ok else
           f"<b class='neg'>与模拟盘不一致</b>（权益差 {_money(diff) if diff is not None else '—'}）")
    return (f'<div class="muted">实盘执行器演练账户（模拟券商，走「下单 → 券商回报 → 对账」这条实盘的路）：{txt}；'
            f'决策日 {escape(str(x.get("decided_on") or "—"))}，今天的单 {int(x.get("orders") or 0)} 笔'
            + (f"；没下单：{escape(str(x['blocked']))}" if x.get("blocked") else "") + "</div>")


def _eligibility_html(d: dict, meta: tuple) -> str:
    """下单前资格检查（qbreak/eligibility.py）：被踢出 / 被指定 / 确认不了的票不开新个股仓；持仓只报警（规则不自动卖）。"""
    e = d.get("eligibility") or {}
    if not e or not e.get("sources"):
        return ""
    nm = meta[2] if len(meta) > 2 else {}
    lab = lambda c: f"{c} {nm[c]}" if c in nm else c                                  # noqa: E731
    srcs = "".join(f"<li>{escape(x['label'])}：{'有效' if x.get('fresh') else '<b class=neg>过期 / 取不到</b>'}"
                   f"（最后成功 {escape(str(x.get('ok_at') or '—'))}；{int(x.get('n') or 0)} 条"
                   + (f"；{escape(x['note'])}" if x.get("note") else "") + (f"；错误 {escape(x['error'])}" if x.get("error") else "")
                   + "）</li>" for x in (e.get("sources") or {}).values())
    needs = "".join(f"<li class='neg'>{escape(n)}</li>" for n in e.get("needs_user") or [])
    blocked = "".join(f"<tr><td>{escape(lab(b['code']))}</td><td>{escape(b['why'])}</td></tr>" for b in e.get("blocked") or [])
    today = "".join(f"<li>{escape(x['date'])} {escape(lab(str(x['ticker']).split('.')[0]))}：{escape(x['why'])}</li>"
                    for x in e.get("blocked_today") or [])
    held = "".join(f"<li class='{'neg' if h.get('level') == 'warn' else 'muted'}'>{escape(lab(str(h['ticker']).split('.')[0]))}"
                   f"（{escape(str(h.get('account') or '—'))}）：{escape(h['why'])}</li>" for h in e.get("held") or [])
    diff = "".join(f"<li>{'ja.wikipedia（主）' if k == 'ja_wiki' else 'en.wikipedia（参考，不挡）'}：我们有它没有 "
                   f"{escape('、'.join(v.get('ours_only') or []) or '无')}；它有我们没有 {escape('、'.join(v.get('src_only') or []) or '无')}"
                   + (f"；已记录的纳入它还没更新 {escape('、'.join(v['lag']))}" if v.get("lag") else "") + "</li>"
                   for k, v in (e.get("diff") or {}).items())
    return ("<section class='card'><h2>下单前资格检查（被踢出 / 被指定的票不开新仓）</h2>"
            f"<p><b>{escape(str(e.get('text') or ''))}</b></p>"
            + (f"<h3>要你确认的事</h3><ul>{needs}</ul>" if needs else "")
            + (f"<h3>今天被挡掉的信号</h3><ul>{today}</ul>" if today else "")
            + (f"<h3>股票池里今天不开新仓的票</h3><div class='scroll'><table><tr><th>代码</th><th>理由</th></tr>{blocked}</table></div>"
               if blocked else "")
            + (f"<h3>持仓的标记（规则不自动卖）</h3><ul>{held}</ul>" if held else "")
            + f"<h3>日経225 名单对照</h3><ul>{diff or '<li class=muted>—</li>'}</ul>"
            + f"<details><summary class='muted'>数据来源（只存代码、类别、日期）</summary><ul>{srcs}</ul></details>"
            "<p class='muted'>规则（2026-09-28 用户要求「以后要确认要下单的股票被没被踢出」）：今天的交易股票池以外、日経225 待剔除、"
            "ja.wikipedia 名单里没有（var/index_changes.json 解释不了）、JPX 特別注意 / 監理 / 整理銘柄、上場廃止（含预定）→ 不开新个股仓；"
            "必需来源超过 4 天没取到 → 当天不开新个股仓；执行器发买单前再查一次；核心 ETF 只看 JPX 标记。"
            "持仓被标记只报警，要不要提前卖由你决定（人工买卖执行器管的票之前先 HALT）。代码在 qbreak/eligibility.py。</p></section>")


def _delist_html(d: dict, meta: tuple) -> str:
    """股票池更新时间表（qbreak/delist_schedule.py）：上場廃止日 / 最終売買日 / 定期入替；到了上場廃止日自动从股票池去掉（只减）；
    补入要用户确认；持仓只报警。"""
    x = d.get("delist") or {}
    if not x or (not x.get("items") and not x.get("error") and not x.get("applied")):
        return ""
    nm = meta[2] if len(meta) > 2 else {}
    lab = lambda c: f"{c} {nm[c]}" if c in nm else c                                  # noqa: E731
    badge = {"待生效": "▲", "今天生效": "■", "已生效": "✓", "日期未定": "…"}

    def rel(r):
        return "；".join(s for s in (("股票池" if r.get("in_pool") else ""), ("持仓 " + "、".join(r["held"]) if r.get("held") else ""),
                                     ("核心 ETF" if r.get("core") else ""), ("<b>已从股票池去掉</b>" if r.get("removed") else "")) if s) or "—"
    rows = []
    for r in x.get("ours") or []:
        if r["kind"] == "上場廃止":
            when, what = r["date"], f"上場廃止（{escape(r.get('why') or '—')}）；最終売買日 {escape(str(r.get('last_trade') or '—'))}，剩 {int(r.get('days_left') or 0)} 个交易日"
        elif r["kind"] == "整理銘柄":
            when, what = "未定", f"JPX 整理銘柄（{escape(str(r.get('designated') or '—'))} 指定；上場廃止日还没公布）"
        else:
            when, what = r["date"], f"日経225 {r['kind']}（{escape(str(r.get('announced') or '—'))} 公布）"
        rows.append(f"<tr><td>{escape(str(when))}</td><td>{escape(lab(r['code']))}</td><td>{what}</td>"
                    f"<td>{badge.get(r['status'], '')} {escape(r['status'])}</td><td>{rel(r)}</td></tr>")
    applied = "".join(f"<li>{escape(lab(a['code']))}：{escape(a['date'])} 上場廃止（{escape(a.get('why') or '—')}），{escape(str(a.get('applied_on') or '—'))} 起不在股票池</li>"
                      for a in x.get("applied") or [])
    other = [r for r in x.get("items") or [] if r["kind"] == "上場廃止" and not (r.get("in_pool") or r.get("held") or r.get("core") or r.get("removed"))]
    other_html = "、".join(f"{escape(r['code'])} {escape(r['date'])}" for r in other)
    needs = "".join(f"<li class='neg'>{escape(n)}</li>" for n in x.get("needs_user") or [])
    err = f"<p class='neg'>这次没更新：{escape(x['error'])} —— 上一次的表（{escape(str(x.get('as_of') or '—'))}）照常生效</p>" if x.get("error") else ""
    return ("<section class='card'><h2>股票池更新时间表（上場廃止 / 定期入替；到日自动去掉）</h2>"
            f"<p><b>{escape(str(x.get('text') or ''))}</b></p>{err}"
            + (f"<h3>要你看的事</h3><ul>{needs}</ul>" if needs else "")
            + "<div class='scroll'><table><tr><th>日期</th><th>代码</th><th>事</th><th>状态</th><th>与我们的关系</th></tr>"
            + ("".join(rows) or "<tr><td colspan=5 class='muted'>股票池 / 持仓 / 核心 ETF 里没有有日期的事</td></tr>") + "</table></div>"
            + (f"<h3>已从股票池去掉（到了上場廃止日）</h3><ul>{applied}</ul>" if applied else "")
            + (f"<details><summary class='muted'>JPX 一览里其他 {len(other)} 只（不在股票池；代码 上場廃止日）</summary><p class='muted'>{other_html}</p></details>"
               if other else "")
            + "<p class='muted'>规则（2026-09-30 用户要求「做一个实时股票退市时间表 check，到日期后就把对应股票池更新」）：每次决策前用资格检查的同一份 JPX 快照更新；"
            "上場廃止日 ≤ 今天 → 自动从交易股票池去掉（只减，记在 var/delist_schedule.json 的 applied，模拟盘 / 执行器 / 候补队列同一张表）；"
            "定期入替照旧按 var/index_changes.json 生效日增删；补入的票（臨時入替的替补）要你确认后改名单；持仓不自动卖（要提前卖先 HALT）。"
            "代码在 qbreak/delist_schedule.py，命令 run.py delist-schedule。</p></section>")


def _calendar_html(c: dict) -> str:
    """检查日历：接下来 45 天有日期的检查 + 远期判定（只展示；每一项的来由见 CHECK_TIMELINE.md）。"""
    if not c or c.get("error") or not (c.get("items") or c.get("milestones")):
        return ""
    wd = "一二三四五六日"
    row = lambda x: (f"<tr><td>{escape(x['date'])}（{wd[dt.date.fromisoformat(x['date']).weekday()]}）</td><td>{escape(x['what'])}</td>"   # noqa: E731
                     f"<td class='muted'>{escape(x['check'])}</td><td>{escape(x['who'])}</td></tr>")
    body = "".join(row(x) for x in c.get("items") or [])
    far = "".join(f"<li>{escape(x['date'])}：{escape(x['what'])} —— {escape(x['check'])}</li>" for x in c.get("milestones") or [])
    return ("<section class='card'><details open><summary><h2 style='display:inline'>检查日历（接下来 "
            f"{int(c.get('horizon_days') or 45)} 天有日期的检查；只展示）</h2></summary>"
            + (f"<div class='scroll'><table><tr><th>日期</th><th>事项</th><th>看什么 / 怎么做</th><th>谁</th></tr>{body}</table></div>" if body else "")
            + (f"<h3>远期的判定 / 评估（事先写定）</h3><ul>{far}</ul>" if far else "")
            + "<p class='muted'>每天固定的流程（06:57 云端日报 → 07:40 Mac 执行器 → 09:00 寄付）、每周 / 每月 / 每季 / 每年要看的事与每一项的研究来由："
              "仓库里的 CHECK_TIMELINE.md。</p></details></section>")


def _price_check_html(pc: dict) -> str:
    """行情交叉核对（qbreak/price_check.py，㉚-1）：yfinance × J-Quants 调整后收盘；只报警（有告警时默认展开）。"""
    if not pc:
        return ""
    from .price_check import KIND_ZH, describe
    why = pc.get("error") or pc.get("skipped")
    al = pc.get("alerts") or []
    if why:
        body = f"<p class='muted'>今天没做：{escape(str(why))}（只报警的检查，不影响交易）</p>"
    else:
        body = (f"<p>{escape(str(pc.get('from')))}〜{escape(str(pc.get('to')))}：核对 {int(pc.get('checked') or 0)} / {int(pc.get('wanted') or 0)} 只"
                + (f"（J-Quants 没有 {len(pc['not_in_jq'])} 只：{escape('、'.join(pc['not_in_jq'][:5]))}）" if pc.get("not_in_jq") else "")
                + (f"；取不到 {int(pc['n_errors'])} 只" if pc.get("n_errors") else "")
                + (f"；时间到没核对 {int(pc['timeout'])} 只" if pc.get("timeout") else "") + "。</p>")
        body += ("<ul>" + "".join(f"<li>⚠ {escape(describe(a))}</li>" for a in al) + "</ul>") if al else \
            "<p>✓ 近 200 天没有复权错位，最新收盘一致，近 20 个交易日不缺。</p>"
        cnt = pc.get("info_counts") or {}
        if cnt:
            body += "<p class='muted'>只提示（不影响指标或已过去）：" + "；".join(f"{escape(KIND_ZH.get(k, k))} {int(v)}" for k, v in cnt.items()) + "</p>"
    return ("<section class='card'><details" + (" open" if al else "") + "><summary><h2 style='display:inline'>行情交叉核对（yfinance × J-Quants；只报警）"
            + (f" ⚠ {len(al)} 条" if al else "") + "</h2></summary>" + body
            + "<p class='muted'>模拟盘 / 执行器用 yfinance 的行情（拆股 + 分红调整）；每天拿 J-Quants（JPX 官方，只做拆股 / 合并调整）核对近 200 天："
              "同一天涨跌差 &gt; 5 pp 且之后比值变了 &gt; 4% = 复权错位；最新一天两边的比值比前 5 天跳了 &gt; 1%；yfinance 落后或缺交易日。"
              "除息日那天比值往上跳 1〜5% 是 yfinance 的分红调整，只提示。"
              "只报警：不改行情、不改交易、不挡下单。告警的票若在今天的买单 / 持仓里，先核对哪边对；要停下单就在 Mac 对话里说「今天不要下单」。"
              "（数据体检 ㉚-1，2026-09-28 用户决定；代码 qbreak/price_check.py）</p></details></section>")


def _invest_flow_html(v: dict) -> str:
    """投资流向（㉟，qbreak/invest_flow.py 的季度快照；財務省 法人企業統計 季報）：只作背景，不改交易。"""
    if not v:
        return ""
    if v.get("error"):
        return ("<section class='card'><h2>投资流向（季度快照，只作背景）</h2>"
                f"<p class='muted'>这一季（{escape(str(v.get('want') or '—'))}）没取到：{escape(str(v['error']))} —— 只作展示，不影响交易；下次运行再取。</p></section>")

    def li(rows, share: bool) -> str:
        if not rows:
            return "<li class='muted'>无</li>"
        out = []
        for r in rows:
            if share:
                g = "" if r.get("growth") is None else f"，投资额 {float(r['growth']):+.1f}%"
                out.append(f"<li>{escape(r['industry'])}：占比 {float(r['share']):.1f}%，比一年前 {float(r['v']):+.1f}%{g}</li>")
            else:
                out.append(f"<li>{escape(r['industry'])}：{float(r['v']):+.1f}%</li>")
        return "".join(out)
    tg = v.get("total_growth")
    head = (f"<p>{escape(str(v.get('period')))}（{escape(str(v.get('quarter')))}；按研究口径 {escape(str(v.get('avail')))} 起用）："
            f"全产业设备投资（4 季合计）比一年前 {'—' if tg is None else f'{float(tg):+.1f}%'}。"
            + (f"<br><b>注意</b>：{escape(str(v['stale']))}" if v.get("stale") else "") + "</p>")
    return ("<section class='card'><h2>投资流向（季度快照，只作背景，不改交易）</h2>" + head
            + "<h3>设备投资占比上升最多（4 季合计，比一年前）</h3><ul>" + li(v.get("share_up"), True) + "</ul>"
            + "<h3>占比下降最多</h3><ul>" + li(v.get("share_down"), True) + "</ul>"
            + "<h3>投资的钱流向：国内产出因设备投资变化而增加的业种</h3><ul>" + li(v.get("flow_up"), False) + "</ul>"
            + "<h3>减少的业种</h3><ul>" + li(v.get("flow_down"), False) + "</ul>"
            + f"<p class='muted'>占比 &lt; {float(v.get('min_share') or 1):g}% 的小业种波动大，不排（{int(v.get('n_small') or 0)} 个）。"
            f"「投资的钱流向」= 各行业设备投资的增速 × 2020 年固定資本マトリックス与产业连关表算出的国内诱发产出比例。{escape(str(v.get('note') or ''))}。"
            f"来源：{escape(str(v.get('source') or ''))}；财务省在季末后第 3 个月的第 1 个工作日公布，这里在那个月的月末才换成新的一季。</p></section>")


def _cost_sales_html(c: dict) -> str:
    """成本 × 销售（S2，qbreak/cost_sales_forward.py）：原材料在涨的月份，销售好且成本上涨的业种按间接占比分组（只展示，不改交易）。"""
    if not c or c.get("error") or not c.get("rows"):
        return ""
    st = c.get("study") or {}
    rows = {r["industry"]: r for r in c.get("rows") or []}
    g = c.get("groups") or {}

    def li(names):
        return "".join(f"<li>{escape(j)}：间接占比 {float(rows[j]['share'] or 0) * 100:.0f}%，原材料成本 +{float(rows[j]['cost3p'] or 0):.2f}%"
                       f"（占产出额），销售 {float(rows[j]['sales'] or 0):+.2f}（按自己历年同一次调查标准化）</li>" for j in names if j in rows)
    fw = c.get("forward") or {}
    if not c.get("cost_up"):
        body = (f"<p>{escape(str(c.get('month_end')))} 末：原材料<b>没在涨</b>（18 个业种的成本净变化平均 {float(c.get('cost_net') or 0):+.2f}%）"
                "→ 这个月不分组（研究里也只看原材料在涨的月份）。</p>")
    elif not g.get("ok"):
        body = (f"<p>{escape(str(c.get('month_end')))} 末：原材料在涨，但销售好且成本上涨的业种只有 {int(g.get('n') or 0)} 个（不到 4 个）"
                "→ 这个月不分组（研究里也不算）。</p>")
    else:
        body = (f"<p>{escape(str(c.get('month_end')))} 末：原材料在涨（成本净变化平均 {float(c.get('cost_net') or 0):+.2f}%）；"
                f"销售好（前一半）且成本上涨的业种 {int(g.get('n') or 0)} 个：</p>"
                f"<h3>偏间接（成本主要经供应链间接上升）</h3><ul>{li(g.get('indirect') or [])}</ul>"
                f"<h3>偏直接（直接吃到原材料涨价）</h3><ul>{li(g.get('direct') or [])}</ul>"
                + (f"<p class='muted'>中间（不算）：{escape('、'.join(g.get('middle') or []))}</p>" if g.get("middle") else ""))
    return ("<section class='card'><h2>成本 × 销售：原材料在涨时，销售好的业种里「偏间接」的更好（只展示，不改交易）</h2>" + body
            + f"<p class='muted'>历史（{escape(str(st.get('period')))}，事先登记 {escape(str(st.get('reg')))}）：之后 3 个月 偏间接 − 偏直接 平均 "
            f"+{st.get('S2')}%（t {float(st.get('S2_t') or 0):.2f}，{st.get('S2_n')} 个月）；不看销售只有 +{st.get('S2b')}%（销售这一条件的增量 +{st.get('pair')} pp，"
            f"t {float(st.get('pair_t') or 0):.2f}）；只看销售前 1/3 为 +{st.get('top3')}%（t {float(st.get('top3_t') or 0):.2f}）。「销售盖过成本」（S1）不成立；"
            "用它挑突破的个股（S4 / S5）没有改进 —— 只看行业，不是个股买卖建议。"
            f"前向记录（2026-10 起每月一次，36 个月后判定）：已记 {int(fw.get('months') or 0)} 个月"
            + (f"（{escape(str(fw.get('first')))}〜{escape(str(fw.get('last')))}，其中原材料在涨 {int(fw.get('cost_up_months') or 0)} 个月）"
               if fw.get("months") else "") + "。非投资建议。</p></section>")


def _combo_c_html(d: dict) -> str:
    """关联搭配 C（qbreak/combo_c.py；2026-10-01 用户「加进模拟盘并记录」，研究 scripts/combo_all_study.py 登记 7f2ca59 /
    结果 729c4ee / 事后核对 63fa4d2）：今天的市场格、候选的 5 个特征 / 投票 / 分数、跳过了哪些。"""
    c = d.get("combo_c") or {}
    if not c.get("enabled"):
        return ""
    from .combo_c import FEATS, LABELS, RULE, SKIP_BELOW, VIX_MAX
    if not c.get("applied"):
        head = f"<p class='neg'>今天没生效：{escape(str(c.get('why') or '—'))}（明天按原规则）</p>"
    else:
        ma, vx = c.get("n225_ma200"), c.get("vix")
        cell = "—" if ma is None or vx is None else f"日経离 200 日线 {float(ma) * 100:+.1f}%、VIX {float(vx):.1f}"
        on = c.get("on")
        sk = c.get("skipped") or []
        head = (f"<p>判定日 {escape(str(c.get('as_of')))}（最新收盘）：{escape(cell)} → "
                + ("<b>平静的牛市：C 起作用</b>" if on is True else "不在「平静的牛市」：C 不动" if on is False else "市场格算不了：C 不动")
                + (f"；明天不开新仓（C 跳过）：<b>{escape('、'.join(sk))}</b>" if on is True and sk else
                   "；没有要跳过的候选" if on is True else "") + "</p>")
    rows = []
    for t, v in sorted((c.get("stocks") or {}).items(), key=lambda kv: (kv[1].get("score", 0), kv[0])):
        fe, vt = v.get("features") or {}, v.get("votes") or {}

        def cell(k: str) -> str:
            x = fe.get(k)
            if x is None:
                return "<td class='n muted'>—（0 票）</td>"
            txt = f"{float(x) * 100:+.1f}%" if k == "r12" else f"{float(x) * 100:.2f}%" if k == "atrp" else f"{float(x):.3f}"
            g = int(vt.get(k, 0))
            return f"<td class='n'>{txt} <span class='{'pos' if g > 0 else 'neg' if g < 0 else 'muted'}'>{'+1' if g > 0 else '−1' if g < 0 else '0'}</span></td>"
        rows.append(f"<tr><td>{escape(t)}</td>" + "".join(cell(k) for k in FEATS)
                    + f"<td class='n'>{int(v.get('score', 0)):+d}</td><td>{'<b>跳过</b>' if v.get('skip') else '不变'}</td></tr>")
    tbl = ("<div class='scroll'><table><tr><th>候选</th>" + "".join(f"<th class='n'>{escape(LABELS[k])}</th>" for k in FEATS)
           + "<th class='n'>分数</th><th>新仓</th></tr>" + "".join(rows) + "</table></div>") if rows else         "<p class='muted'>最新收盘没有日本个股的买入候选</p>"
    cuts = "；".join(f"{escape(LABELS[k])} {'越大越好' if RULE[k][0] > 0 else '越小越好'}（切点 {RULE[k][1]:g} / {RULE[k][2]:g}）" for k in FEATS)
    err = c.get("errors") or {}
    errs = ("<p class='muted'>算不了的项（按 0 票 / C 不动）：" + "；".join(f"{escape(str(k))}：{escape(str(v))}" for k, v in err.items()) + "</p>") if err else ""
    return ("<section class='card'><h2>关联搭配 C：市场状态 × 个股特征（2026-10-01 的决策起影响日本个股新仓；用户要求）</h2>" + head + tbl + errs
            + f"<p class='muted'>只在「日経225 收盘在 200 日线上、且 VIX（前一个美国收盘）&lt; {VIX_MAX:g}」时起作用：5 个特征各投一票"
            f"（有利的三分之一 +1、不利的三分之一 −1、中间 / 缺值 0）：{cuts}；分数 &lt; {SKIP_BELOW:g}（不利多 2 票以上）→ 这只明天不开新仓，"
            "其余不变（不放大）；其他市场格不动。基准账户（原规则）不加。</p>"
            "<p class='muted'>证据（照实写）：研究（scripts/combo_all_study.py，登记 7f2ca59）按事先写定的 D1〜D4b 全部通过 —— 2017〜2026 日経225 "
            "W2 信号胜率 40.1% → 46.5%、每笔 +0.91% → +1.88%（保留 74%）；但 2001〜2016 只略好，别的股票几乎没有效果（+0.05 / +0.04 pp），"
            "日経225 每年约只有 2〜3 笔会被跳过（2017〜2026：23 笔）→ 前向记录（scripts/score_forward.py 第十二节）只能抓住明显变坏。"
            "<b>只用过去学时前推不成立</b>（2026-10-01 选股第二轮，登记 92e2ef2：每年只用之前的信号、按同一做法重学，2016〜2026 每笔只 +0.13 pp、2021-06 以后 −0.10 pp；"
            "C 的效果对学习样本怎么切很敏感）→ C 照旧在用，要不要关掉由你决定。"
            "关掉：var/sim.json 的 combo_c.enabled = false。非投资建议。</p></section>")


def _fwdj_html(d: dict) -> str:
    """前向记录判断层（qbreak/fwd_judgment.py；2026-09-29 用户要求加进模拟盘，规则登记 c5ef50d）：今天的市场分数与倍数、
    候选的个股判定、基准账户（不加判断层）对照。"""
    f = d.get("fwdj") or {}
    if not f.get("enabled"):
        return ""
    from .fwd_judgment import LABELS, POINTS
    m = f.get("market") or {}
    it, rd = m.get("items") or {}, m.get("readings") or {}

    def pc(v) -> str:
        return "—" if v is None else f"{float(v):.0f} 分位"

    def yn(k: str, yes: str = "<b>警示</b>", no: str = "否") -> str:
        v = it.get(k)
        return "算不了（按 0）" if v is None else (yes if v else no)
    read = {"A1": f"C_rel {'—' if rd.get('C_rel') is None else rd['C_rel']}（满分 100）→ 自身历史 {pc(rd.get('crel_pct'))}",
            "A2": f"各版本分位的中位数 {pc(rd.get('tv_pct'))}", "A3": pc(rd.get("wj_pct")), "A4": pc(rd.get("w_pct")),
            "A5": yn("A5", "成立", "不成立"), "A6": yn("A6", "熊", "不是熊"), "A+": yn("A+", "在窗口里", "不在")}
    rows = "".join(f"<tr><td>{k}</td><td>{escape(LABELS[k])}</td><td class='n'>{POINTS[k]} 分</td><td>{read[k]}</td><td>{yn(k)}</td></tr>"
                   for k in POINTS)
    rows += (f"<tr><td>A+</td><td>{escape(LABELS['A+'])}</td><td class='n'>−1 分</td><td>{read['A+']}</td>"
             f"<td>{yn('A+', '<b>抵消 1 分</b>', '否')}</td></tr>")
    rg = ((d.get("extras") or {}).get("JP") or {}).get("regime") or {}
    fr = rg.get("fwd_judgment") or {}
    if f.get("applied"):
        head = (f"<p>判定日 {escape(str(f.get('as_of')))}（最新收盘）：市场 <b>{m.get('points')} 分 → 日本个股新仓 ×{m.get('mult')}</b>；"
                f"原有各层 {fr.get('before', '—')} 倍 → 取小后明天实际 <b>{rg.get('final_mult', '—')} 倍</b></p>")
    else:
        head = f"<p class='neg'>今天没生效：{escape(str(f.get('why') or '—'))}（明天按原规则）</p>"
    names = {"B1": "F2", "B2": "X2", "B3": "K2", "B4": "USW", "B5": "时代主线", "B6": "S2", "B7": "G1"}
    st_rows = []
    for t, v in sorted((f.get("stocks") or {}).items(), key=lambda kv: (-float(kv[1].get("score", 0)), -float(kv[1].get("F2") or -9))):
        fl = "、".join(f"{names[k]} {'+1' if x > 0 else '−1'}" for k, x in (v.get("flags") or {}).items() if x) or "全部 0"
        ind = (v.get("inputs") or {}).get("industry") or "—"
        f2 = "—" if v.get("F2") is None else f"{float(v['F2']):+.2f}"
        st_rows.append(f"<tr><td>{escape(t)}</td><td class='muted'>{escape(str(ind))}</td><td>{escape(fl)}</td>"
                       f"<td class='n'>{int(v.get('score', 0)):+d}</td><td class='n'>{f2}</td>"
                       f"<td>{'<b>×0.5</b>' if float(v.get('mult', 1)) < 1 else '不变'}</td></tr>")
    stock = ("<div class='scroll'><table><tr><th>候选</th><th>業種</th><th>不为 0 的项</th><th class='n'>合计 s</th><th class='n'>F2</th>"
             "<th>新仓</th></tr>" + "".join(st_rows) + "</table></div>") if st_rows else "<p class='muted'>最新收盘没有日本个股的买入候选</p>"
    b = f.get("baseline") or {}
    diff = f.get("diff_jpy")
    base = (f"<p>基准账户（原规则：同一套行情、不加这一层、离场用死叉、闲置资金 1655 + 美股牛熊分界，{escape(str(b.get('since') or '—'))} 起）：权益 {_money(b.get('equity_jpy'))}；"
            f"模拟盘 {_money(f.get('equity_jpy'))}；差 <b class='{'pos' if (diff or 0) > 0 else 'neg' if (diff or 0) < 0 else ''}'>"
            f"{'—' if diff is None else ('+' if diff >= 0 else '−') + f'¥{abs(diff):,.0f}'}</b>"
            f"（持仓 基准 {len(b.get('positions') or [])} 只）</p>") if b and not b.get("error") else \
        f"<p class='muted'>基准账户：{escape(str(b.get('error') or '还没有'))}</p>"
    return ("<section class='card'><h2>前向记录判断层（2026-09-30 起影响日本个股新仓；用户要求）</h2>" + head
            + "<div class='scroll'><table><tr><th>项</th><th>内容</th><th class='n'>分数</th><th>今天的读数</th><th>判定</th></tr>" + rows
            + "</table></div><p class='muted'>分数 n = 警示分 − 深跌抵消（最低 0）：0 → ×1、1 → ×0.75、≥ 2 → ×0.5；与量化层 / 判断层 / 宏观层取小（不放大）。"
            "个股层：每只候选 7 项各 +1 / −1 / 0，合计 s &lt; 0 → 这只新仓 ×0.5；同一天抢名额时 s 高的先、再按 F2。</p>"
            + stock + base
            + "<p class='muted'>证据（照实写）：这些项目大多是事先规则没通过才进前向记录的；只有 C_rel 在 21 个外国市场确认过（指数层）。"
            "历史检验（scripts/fwd_judgment_check.py，登记 c5ef50d）：市场层整体 E / J 两个窗口「差不多」；只加 C_rel 与现行完全相同 ——"
            "C_rel 警示的成交日，原有各层多半已经不开新仓（E、Z 100%，J 80%），剩下的日子也没有突破成交（事后描述）。"
            "关掉：var/sim.json 的 fwd_judgment.enabled = false。非投资建议。</p></section>")


def _shadow_html(d: dict) -> str:
    """影子账户（判断型选股，scripts/shadow_account.py；只前向记录，不影响模拟盘与交易）。"""
    s = d.get("shadow") or {}
    if not s:
        return ""
    diff = s.get("diff_pp")
    cls = "pos" if (diff or 0) > 0 else "neg" if (diff or 0) < 0 else ""
    dec = s.get("last_decision") or {}
    orders = "；".join(f"{escape(o['side'])} {escape(o['ticker'])} {int(o['shares']):,} 股（{escape(o.get('reason') or '')}）"
                      for o in dec.get("orders") or []) or "不动"
    rows = "".join(f"<tr><td>{escape(t)}</td><td class='n'>{int(p['shares']):,} 股</td><td class='n'>{_money(p.get('cost'))}</td>"
                   f"<td class='n'>{_money(p.get('close'))}</td><td class='n'>{_money(p.get('value'))}</td>"
                   f"<td class='n'>{float(p.get('pnl_pct') or 0):+.2f}%</td></tr>" for t, p in (s.get("positions") or {}).items())
    return (f'<section class="card"><h2>影子账户（判断型选股，只记录，不影响模拟盘与交易）</h2>'
            f'<p>截至 {escape(str(s.get("as_of") or "—"))}：权益 <b>{_money(s.get("equity_jpy"))}</b>（{float(s.get("ret_pct") or 0):+.2f}%），'
            f'规则账户 {_money(s.get("rule_equity_jpy"))}，差 <b class="{cls}">{"—" if diff is None else f"{diff:+.2f} pp"}</b>；现金 {_money(s.get("cash_jpy"))}</p>'
            f'<p class="muted">{escape(str(dec.get("for_date") or "—"))} 的判断：{escape(str(dec.get("view") or "—"))} → {orders}</p>'
            + (f'<div class="scroll"><table><tr><th>代码</th><th class="n">股数</th><th class="n">成本</th><th class="n">收盘</th>'
               f'<th class="n">市值</th><th class="n">损益</th></tr>{rows}</table></div>' if rows else "")
            + f'<p class="muted">记录期间 {escape(" 〜 ".join(s.get("period") or []))}；评估标准事先登记在 scripts/shadow_account.py（3 个月后评估）。'
            f'{escape(str(s.get("note") or ""))}</p></section>')


# ───────────────────────── 持仓仪表盘（日报最上面；重要度从高到低；每个参数带「现在在哪、危不危险」）─────────────────────────
# 状态色是固定的四档（好 / 注意 / 警戒 / 危险），一律配图标 + 文字，不单靠颜色；分类色（资产构成）用四个经校验的色槽。
_ST_ICON = {"good": "✓", "warn": "▲", "serious": "■", "crit": "✖", "na": "·", "info": "○"}
_ST_LAB = {"good": "安全", "warn": "注意", "serious": "警戒", "crit": "危险", "na": "未知", "info": ""}


def _chip(st: str, text: str | None = None) -> str:
    """状态徽章：图标 + 文字（颜色只是辅助）。"""
    lab = _ST_LAB.get(st, "") if text is None else text
    return f'<span class="st st-{st}">{_ST_ICON.get(st, "·")} {escape(lab)}</span>'


def _grade(x, cuts: tuple, worse_high: bool = True) -> str:
    """x 对三个门槛 (注意, 警戒, 危险) → good / warn / serious / crit；worse_high = 越大越危险。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "na"
    if v != v:
        return "na"
    a, b, c = cuts
    if worse_high:
        return "crit" if v >= c else "serious" if v >= b else "warn" if v >= a else "good"
    return "crit" if v <= c else "serious" if v <= b else "warn" if v <= a else "good"


def _meter(frac, st: str, zones=(), ticks=(), w: int = 320, label: str = "") -> str:
    """横条：淡色区带 = 各档的位置（门槛在哪一眼能看到）、实心条 = 现在到哪里（颜色 = 危险度）、▼ = 现在；ticks = [(位置 0〜1, 文字)]。"""
    def X(f) -> float:
        return round(max(0.0, min(1.0, float(f))) * w, 1)
    rows_of: list[int] = []                                             # 刻度文字挨得太近（< 70px）→ 换到第二行
    last_x = {0: -1e9, 1: -1e9}
    for f, _ in ticks:
        x = X(f)
        r = 0 if x - last_x[0] >= 70 else 1
        rows_of.append(r)
        last_x[r] = x
    h = 42 if 1 in rows_of else 30
    parts = [f'<svg viewBox="0 0 {w} {h}" class="meter" role="img" aria-label="{escape(label)}">',
             f'<rect x="0" y="9" width="{w}" height="6" rx="3" fill="var(--line)"/>']
    for f0, f1, z in zones:
        wd = max(0.0, X(f1) - X(f0))
        if wd > 0:
            parts.append(f'<rect x="{X(f0)}" y="9" width="{wd}" height="6" fill="var(--st-{z})" opacity="0.28"/>')
    if frac is not None and frac == frac:
        x = X(frac)
        parts.append(f'<rect x="0" y="9" width="{x}" height="6" rx="3" fill="var(--st-{st})"/>')
        parts.append(f'<polygon points="{x - 5},0 {x + 5},0 {x},7" fill="var(--fg)"/>')
    for (f, txt), r in zip(ticks, rows_of):
        x = X(f)
        parts.append(f'<line x1="{x}" y1="8" x2="{x}" y2="{17 if r == 0 else 29}" stroke="var(--muted)" stroke-width="1"/>')
        anchor = "start" if f < 0.12 else ("end" if f > 0.88 else "middle")
        parts.append(f'<text x="{x}" y="{27 if r == 0 else 39}" font-size="9" fill="var(--muted)" text-anchor="{anchor}">{escape(txt)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _mrow(name: str, sub: str, meter: str, value: str, chip: str, note: str = "") -> str:
    """仪表盘的一行：名称 · 说明 / 数值 + 状态徽章 / 横条 / 备注（name / sub / value / note 已是 HTML）。"""
    return (f'<div class="mrow"><div class="mlab"><b>{name}</b>{(" <span class=muted>" + sub + "</span>") if sub else ""}</div>'
            f'<div class="mval">{value} {chip}</div><div class="mbar">{meter}</div>'
            + (f'<div class="muted small">{note}</div>' if note else "") + "</div>")


def _segments(cells: list[tuple[str, str]], w: int = 320, h: int = 14) -> str:
    """分段条（名额、倍数档）：cells = [(fill 变量名, 文字)]，段与段之间留 2px 空隙。"""
    n = max(1, len(cells))
    gap = 2
    cw = (w - gap * (n - 1)) / n
    out = [f'<svg viewBox="0 0 {w} {h}" class="seg" role="img" aria-label="分段">']
    for i, (fill, txt) in enumerate(cells):
        x = round(i * (cw + gap), 1)
        out.append(f'<rect x="{x}" y="2" width="{cw:.1f}" height="10" rx="2" fill="{fill}"/>')
        if txt:
            tf = "var(--muted)" if fill == "var(--line)" else "var(--card)"
            out.append(f'<text x="{x + cw / 2:.1f}" y="10.5" font-size="8" fill="{tf}" text-anchor="middle">{escape(txt)}</text>')
    out.append("</svg>")
    return "".join(out)


def _account_block(d: dict) -> str:
    """① 账户：总权益 / 累计 / 离峰值的回撤（门槛 −5 / −12 / −20%）/ 现金 / 名额 / 已平仓。"""
    hist = d.get("history") or []
    eq = float(d.get("equity_jpy") or 0)
    cap = float(d.get("capital_jpy") or 0)
    ys = [float(x[1]) for x in hist] + ([eq] if eq else [])
    peak = max(ys) if ys else cap
    dd = (eq / peak - 1) * 100 if peak else None
    st = _grade(dd, (-5.0, -12.0, -20.0), worse_high=False)
    frac = None if dd is None else min(1.0, max(0.0, -dd / 30.0))
    zones = [(0, 5 / 30, "good"), (5 / 30, 12 / 30, "warn"), (12 / 30, 20 / 30, "serious"), (20 / 30, 1, "crit")]
    meter = _meter(frac, st, zones, ticks=[(0, "峰值"), (5 / 30, "−5%"), (12 / 30, "−12%"), (20 / 30, "−20%"), (1, "−30%")], label="离峰值的回撤")
    ret = d.get("ret_pct")
    ret_txt = "—" if ret is None else f"{float(ret):+.2f}%"
    mdd = d.get("max_dd_pct")
    dd_txt = "—" if dd is None else f"{dd:+.2f}%"
    tl = d.get("timeline") or {}
    sl = tl.get("slots") or {}
    cfg = d.get("config") or {}
    nmax = int(sl.get("max") or cfg.get("max_positions") or 4)
    held = int(sl.get("held") if sl.get("held") is not None else len(d.get("positions") or {}))
    selling, buying = int(sl.get("selling") or 0), int(sl.get("buying") or 0)
    free = int(sl.get("free")) if sl.get("free") is not None else max(0, nmax - held - buying)
    cells = ([("var(--s1)", "持")] * max(0, held - selling) + [("var(--st-warn)", "卖")] * selling
             + [("var(--s2)", "买")] * buying + [("var(--line)", "空")] * free)[:nmax]
    n_tr = int(d.get("n_trades") or 0)
    win = _pct(d.get("win_rate")) if d.get("win_rate") is not None else "—（还没有平仓）"
    fx = d.get("usdjpy") or 0
    usd = (f'<div><span class="muted">美元现金</span><b>{_money(d.get("cash_usd"), "USD")}</b><span class="muted">USD/JPY {_fxr(fx)}</span></div>'
           if _has_usd(d.get("broker")) else
           f'<div><span class="muted">USD/JPY（只影响核心 ETF 的日元价值）</span><b>{_fxr(fx)}</b><span class="muted">{escape(str(d.get("usdjpy_src") or ""))}</span></div>')
    return (f'<section class="card top"><h2>① 账户</h2>'
            f'<div class="hero"><span class="muted">总权益（日元）</span><b class="big">{_money(eq)}</b>'
            f'<span class="{"pos" if (ret or 0) >= 0 else "neg"} big2">{ret_txt}</span><span class="muted">起始 {_money(cap)}</span></div>'
            + _mrow("离峰值的回撤", f"峰值 {_money(peak)}；模拟期最大回撤 {escape(str(mdd))}%", meter, dd_txt, _chip(st))
            + f'<div class="kpi"><div><span class="muted">日元现金</span><b>{_money(d.get("cash_jpy"))}</b></div>{usd}'
            f'<div><span class="muted">个股名额 {held} / {nmax} 在用</span>{_segments(cells)}<span class="muted">持 {held} · 明天卖 {selling} · 明天买 {buying} · 空 {free}</span></div>'
            f'<div><span class="muted">已平仓</span><b>{n_tr} 笔</b><span class="muted">胜率 {win}</span></div></div></section>')


def _positions_block(d: dict, closes: dict) -> str:
    """② 个股持仓：每只票一条「卖出线 ← 现价 → 止盈」的横条（门槛 = 距最近的卖出线 6 / 3 / 1.5%）+ 持有天数。"""
    from .earn_state import tag_html as _es_tag
    pos = d.get("positions") or {}
    tl = d.get("timeline") or {}
    hs = {h.get("ticker"): h for h in (tl.get("holdings") or [])}
    es_map = (d.get("earn_state") or {}).get("states") or {}
    cfg = d.get("config") or {}
    nmax = int((tl.get("slots") or {}).get("max") or cfg.get("max_positions") or 4)
    if not pos:
        return (f'<section class="card top"><h2>② 个股持仓</h2><p class="muted">无：{nmax} 个名额全空（明天开盘要不要买，看下面「今天要做的事」与候补队列）。</p></section>')
    rows = []
    for t, p in pos.items():
        h = hs.get(t) or {}
        ccy = "USD" if p.get("market") == "US" else "JPY"
        entry, stop0 = float(p["entry_px"]), float(p["stop_px"])
        close = closes.get(t)
        lv = h.get("levels") or []
        downs = [x for x in lv if x.get("side") == "down" and x.get("px") is not None]
        ups = [x for x in lv if x.get("side") == "up" and x.get("px") is not None]
        hard = max((float(x["px"]) for x in downs), default=stop0)
        hard_rule = next((str(x.get("rule") or "").split("（")[0] for x in downs if float(x["px"]) == hard), "止损")
        tp = max((float(x["px"]) for x in ups), default=entry * 1.25)
        if close:
            d_down, d_up, pnl = (hard / close - 1) * 100, (tp / close - 1) * 100, (close / entry - 1) * 100
        else:
            d_down = d_up = pnl = None
        st = _grade(None if d_down is None else -d_down, (6.0, 3.0, 1.5), worse_high=False)
        span = tp - hard

        def F(x: float) -> float:
            return (x - hard) / span if span > 0 else 0.0
        frac = None if close is None else F(close)
        zones = [(0, F(hard * 1.015), "crit"), (F(hard * 1.015), F(hard * 1.03), "serious"), (F(hard * 1.03), F(hard * 1.06), "warn"),
                 (F(hard * 1.06), 1, "good")]
        ticks = [(0, f"卖出线 {_money(hard, ccy)}"), (F(entry), f"成本 {_money(entry, ccy)}"), (1, f"止盈 {_money(tp, ccy)}")]
        meter = _meter(frac, st, zones, ticks, label=f"{t} 现价在卖出线与止盈之间的位置")
        val = (f"现价 {_money(close, ccy)}<span class='{'pos' if pnl >= 0 else 'neg'}'>（{pnl:+.1f}%）</span>"
               f"<span class='muted'> 距止盈 {d_up:+.1f}%</span>" if close else "现价：今天没算出")
        chip = _chip(st, f"距{hard_rule} {d_down:+.1f}%" if d_down is not None else "位置未知")
        hold = int(h.get("hold") or p.get("hold") or 0)
        hmax = int(h.get("max_hold_days") or 60)
        mh = h.get("max_hold") or {}
        left = max(0, hmax - hold)
        hst = "warn" if left <= 10 else "info"
        hmeter = _meter(hold / hmax if hmax else None, hst, [], [(0, "买入"), (1, f"满 {hmax} 天")], label=f"{t} 持有天数")
        q = h.get("queued") or {}
        qtxt = f"；<b>明天开盘卖</b>（{escape(str(q.get('reason') or ''))}）" if q else ""
        head = (f"<b>{escape(t)}</b> <span class='muted'>{'美股' if ccy == 'USD' else '日本'} · {int(p['shares']):,} 股 · 买入 {escape(str(p.get('entry_date') or ''))}"
                f" · 止损 {_money(stop0, ccy)}</span> {_es_tag(es_map.get(t)) if (ccy == 'JPY' and es_map.get(t)) else ''}{qtxt}")
        rows.append(f'<div class="posrow"><div class="mlab">{head}</div><div class="mval">{val} {chip}</div><div class="mbar">{meter}</div>'
                    + _mrow("持有", f"最迟 {escape(str(mh.get('sell_day') or '—'))} 开盘卖", hmeter, f"{hold} / {hmax} 天",
                            _chip(hst, f"还有 {left} 天")) + "</div>")
    return f'<section class="card top"><h2>② 个股持仓（{len(pos)} / {nmax} 个名额）</h2>{"".join(rows)}</section>'


_SLOT_FILL = ("var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)")


def _donut(slices: list[tuple[str, float, str]], size: int = 120) -> str:
    """环形图：slices = [(名称, 金额, 色变量)]（金额 ≤ 0 的不画）；段之间留 2px 空隙；名称与数值在旁边的图例里。"""
    tot = sum(v for _, v, _ in slices if v > 0)
    if tot <= 0:
        return ""
    r, cx = 42.0, size / 2
    circ = 2 * 3.141592653589793 * r
    out = [f'<svg viewBox="0 0 {size} {size}" class="donut" role="img" aria-label="资产构成">']
    off = 0.0
    for name, v, fill in slices:
        if v <= 0:
            continue
        seg = circ * v / tot
        vis = max(0.0, seg - 2)
        out.append(f'<circle cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke="{fill}" stroke-width="16" stroke-dasharray="{vis:.2f} {circ - vis:.2f}" '
                   f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 {cx} {cx})"/>')
        off += seg
    out.append("</svg>")
    return "".join(out)


def _allocation_block(d: dict, closes: dict, core_rows: str) -> str:
    """④ 资产构成（环形图 + 图例）+ 核心 ETF 表。"""
    fx = float(d.get("usdjpy") or 0) or 1.0
    stock = 0.0
    for t, p in (d.get("positions") or {}).items():
        px = closes.get(t) or float(p["entry_px"])
        stock += float(p["shares"]) * px * (fx if p.get("market") == "US" else 1.0)
    names = _IC_NAMES()
    core = []
    for i, (t, u) in enumerate((d.get("core_units") or {}).items()):
        v = int(u) * float((d.get("core_last") or {}).get(t) or 0)
        core.append((names.get(t, t), v, _SLOT_FILL[1 + (i % 2)]))
    cash = float(d.get("cash_jpy") or 0) + float(d.get("cash_usd") or 0) * fx
    slices = [("个股", stock, _SLOT_FILL[0])] + core + [("现金", cash, _SLOT_FILL[3])]
    tot = sum(v for _, v, _ in slices)
    leg = "".join(f'<li><span class="sw" style="background:{fill}"></span>{escape(n)} <b>{_money(v)}</b> <span class="muted">{(v / tot * 100 if tot else 0):.0f}%</span></li>'
                  for n, v, fill in slices if v > 0)
    return (f'<section class="card top"><h2>④ 资产构成与核心 ETF（闲置资金）</h2><div class="alloc">{_donut(slices)}<ul class="legend">{leg}</ul></div>'
            f'<div class="scroll"><table><tr><th>代码</th><th class="n">份额</th><th class="n">收盘</th><th class="n">市值</th></tr>{core_rows}</table></div></section>')


def _market_block(d: dict) -> str:
    """⑤ 市场状态仪表：牛熊分界离翻转多远、明天新仓倍数、大事件威胁指数、前向记录判断层。"""
    from .fwd_judgment import LABELS as _FJ
    rows = []
    for m, e in (d.get("extras") or {}).items():
        r = e.get("regime") or {}
        bb = r.get("bullbear") or {}
        name = _MNAME.get(m, m)
        dist = bb.get("distance_pct")
        if bb.get("state") in ("bull", "bear") and dist is not None:
            dist = float(dist)
            st = _grade(dist, (10.0, 5.0, 2.0), worse_high=False)
            zones = [(0, 2 / 25, "crit"), (2 / 25, 5 / 25, "serious"), (5 / 25, 10 / 25, "warn"), (10 / 25, 1, "good")]
            ticks = [(0, "翻转价位"), (5 / 25, "5%"), (10 / 25, "10%"), (1, "25%")]
            flip = bb.get("flip_to") or ("bear" if bb["state"] == "bull" else "bull")
            sub = (f"{escape(str(bb.get('phase_label') or _BB.get(bb['state'], '')))}；{'转熊' if flip == 'bear' else '转牛'}价位 {_lvl(bb.get('level'), m)}"
                   + (f"，现价 {_lvl(bb['close'], m)}" if bb.get("close") is not None else "")
                   + (f"（{escape(str(bb.get('asof')))}）" if bb.get("asof") else ""))
            rows.append(_mrow(f"{escape(name)} 牛熊分界", sub, _meter(min(1.0, dist / 25), st, zones, ticks, label=f"{name} 距翻转"),
                              f"距翻转 {dist:+.1f}%", _chip(st)))
        if e.get("core_only"):
            continue
        fm = r.get("final_mult")
        if fm is not None:
            fm = float(fm)
            steps = [0.0, 0.5, 0.75, 1.0]
            cells = [("var(--s1)" if fm >= v and v > 0 else "var(--line)", f"×{v:g}") for v in steps[1:]]
            fj = r.get("fwd_judgment") or {}
            why = [f"量化层 {escape(_QLAB.get(r.get('quant_label') or '', str(r.get('quant_label') or '')).split('（')[0])} ×{r.get('quant_mult', '—')}"]
            if r.get("overlay_action"):
                why.append(f"市场风险报告「{escape(str(r['overlay_action']))}」×{r.get('overlay_mult')}")
            if fj.get("applied"):
                why.append(f"前向记录判断层 {fj.get('points')} 分 ×{fj.get('mult')}")
            fired = (e.get("macro") or {}).get("fired") or []
            if fired:
                why.append("宏观触发 " + "、".join(escape(str(x)) for x in fired))
            st = "serious" if fm <= 0 else ("warn" if fm < 1 else "good")
            lab = "今天不开新仓" if fm <= 0 else (f"减到 ×{fm:g}" if fm < 1 else "正常 ×1")
            rows.append(_mrow(f"{escape(name)} 明天新仓倍数", "各层取最小", _segments(cells), f"×{fm:g}", _chip(st, lab), "；".join(why)))
    th = d.get("threat") or {}
    for mk, nm in (("JP", "日経"), ("US", "美股")):
        t = th.get(mk) or {}
        v = t.get("value")
        if v is None:
            continue
        v = float(v)
        st = _grade(v, (50.0, 65.0, 80.0))
        zones = [(0, 0.5, "good"), (0.5, 0.65, "warn"), (0.65, 0.8, "serious"), (0.8, 1, "crit")]
        ticks = [(0, "0"), (0.5, "50"), (0.65, "65"), (0.8, "80 = 历史事件线"), (1, "100")]
        p20 = t.get("prev20")
        sub = f"{escape(str(t.get('date') or ''))}；20 个交易日前 {float(p20):.1f}" if p20 is not None else escape(str(t.get("date") or ""))
        top = "、".join(escape(str(x.get("label"))) for x in (t.get("top") or [])[:3])
        rows.append(_mrow(f"{nm} 大事件威胁指数", sub, _meter(v / 100, st, zones, ticks, label=f"{nm} 威胁指数"), f"{v:.1f} 分", _chip(st),
                          (f"主因 {top}（只展示，不参与交易）" if top else "只展示，不参与交易")))
    fj = d.get("fwdj") or {}
    if fj.get("enabled"):
        mk = fj.get("market") or {}
        pts, mult = fj.get("points"), fj.get("mult")
        items = mk.get("items") or {}
        on = [f"{k} {escape(_FJ.get(k, k))}" for k, v in items.items() if v]
        st = "good" if (mult or 1) >= 1 else ("warn" if (mult or 1) >= 0.75 else "serious")
        cells = [("var(--s1)" if (pts or 0) >= i else "var(--line)", str(i)) for i in range(1, 5)]
        rows.append(_mrow("前向记录判断层（市场层）", f"按 {escape(str(mk.get('date') or fj.get('as_of') or ''))} 收盘；0〜1 分 ×1 / ×0.75，≥ 2 分 ×0.5",
                          _segments(cells), f"{pts} 分", _chip(st, f"×{mult}"), ("触发：" + "；".join(on)) if on else "没有触发项"))
    if not rows:
        return ""
    return f'<section class="card top"><h2>⑤ 市场状态（离危险多远）</h2>{"".join(rows)}</section>'


def render_unified_html(d: dict) -> str:
    today = now_jst().date()
    usopen = _us_open_jst(today)
    td = d.get("todo") or {}
    cfg = d.get("config") or {}
    with_us = "US" in (cfg.get("stock_markets") or ["JP", "US"])

    meta = _groups_meta()

    def rows(items, market):
        out = []
        for o in items:
            if market == "FX":
                arrow = "日元 → 美元" if o["dir"] == "JPY>USD" else "美元 → 日元"
                out.append(f"<li>{arrow}：{_money(o['usd'], 'USD')}（约 {_money(o.get('jpy_est'))}）</li>")
                continue
            ccy = "USD" if market == "US" else "JPY"
            lim = f"，指値 {_money(o['limit'], ccy)}" if o.get("limit") else ""
            why = f"（{escape(str(o.get('reason')))}）" if o.get("reason") else ""
            unit = "口" if (str(o.get("ticker", "")) in _IC_NAMES()
                           or str(o.get("ticker", "")).startswith(("1655", "1329", "2558"))) else "股"
            tag = f" {_bo_tag(o)}" if o.get("side") == "BUY" and "breakout" in o else ""
            if o.get("side") == "BUY":
                tag += f" {_grp_tag(o.get('ticker', ''), d.get('themes') or {}, meta)}"
            out.append(f"<li><b>{'买入' if o['side'] == 'BUY' else '卖出'}</b> {escape(o['ticker'])} × {o['qty']:,} {unit}"
                       f" {escape(o.get('type', ''))}{lim}{why}{tag}</li>")
        return "".join(out) or (f'<li class="muted">首次运行（{escape(str(d.get("sim", {}).get("start")))} 07:00 JST 前后）后给出当天要下的单'
                                '（现在是开始前的预览，不下单）</li>' if d.get("preview") else '<li class="muted">无</li>')

    sen = round(float(cfg.get("fx_spread_yen", 0.25)) * 100)
    from .calendar_jp import is_trading_day, next_trading_day
    from .holiday_gap import html as _fut_html
    wdn = "月火水木金土日"
    fill = next_trading_day(dt.date.fromisoformat(str(d["bar_date"])[:10])) if d.get("bar_date") else None
    head = f"{fill:%m/%d}（{wdn[fill.weekday()]}）09:00 日本开盘（寄付）" if fill else "09:00 日本开盘（寄付）"
    hol = (f"<p class='muted'>今天 {today:%m/%d}（{wdn[today.weekday()]}）东证休市：上面的单在 {fill:%m/%d}（{wdn[fill.weekday()]}）开盘成交"
           f"（执行器在休市日发出的寄付单，券商按下一个营业日受理）。</p>") if fill and today < fill and not is_trading_day(today) else ""
    todo_html = f'<h3>{head}</h3><ul>{rows(td.get("JP", []), "JP")}</ul>{hol}{_fut_html(d.get("jp_futures"))}'
    if with_us or td.get("FX") or td.get("US") or float(d.get("cash_usd") or 0) > 0:   # 只做日本个股且没有美元时不显示
        todo_html += (f'<h3>日间 换汇（リアルタイム為替：手数料 0 銭，价差按片道 {sen:g} 銭估）</h3><ul>{rows(td.get("FX", []), "FX")}</ul>'
                      f'<h3>{usopen} 美股开盘（日本时间）</h3><ul>{rows(td.get("US", []), "US")}</ul>')
    fx = d.get("usdjpy") or 0
    from .earn_state import tag_html as _es_tag
    es_map = (d.get("earn_state") or {}).get("states") or {}
    pos_rows = []
    for t, p in (d.get("positions") or {}).items():
        ccy = "USD" if p["market"] == "US" else "JPY"
        pos_rows.append(f"<tr><td>{escape(t)}</td><td>{'美股' if ccy == 'USD' else '日本'}</td><td class='n'>{p['shares']:,} 股</td>"
                        f"<td class='n'>{_money(p['entry_px'], ccy)}</td><td class='n'>{_money(p['stop_px'], ccy)}</td>"
                        f"<td>{escape(p['entry_date'])}</td><td>{_es_tag(es_map.get(t)) if ccy == 'JPY' else '—'}</td></tr>")
    core_rows = []
    for t, u in (d.get("core_units") or {}).items():
        px = float((d.get("core_last") or {}).get(t) or 0)
        core_rows.append(f"<tr><td>{escape(t)}</td><td class='n'>{int(u):,} 口</td><td class='n'>{_money(px)}</td>"
                         f"<td class='n'>{_money(int(u) * px)}</td></tr>")
    tr_rows = "".join(
        f"<tr><td>{escape(t['exit_date'])}</td><td>{escape(t['ticker'])}</td><td>{'美股' if t['market'] == 'US' else '日本'}</td>"
        f"<td class='n'>{t['shares']:,} 股</td><td class='n {'pos' if float(t['pnl_jpy']) > 0 else 'neg'}'>{_money(t['pnl_jpy'])}</td>"
        f"<td>{escape(t['reason'])}</td></tr>" for t in reversed(d.get("trades") or []))
    fx_rows = "".join(f"<tr><td>{escape(x[0])}</td><td>{'日元→美元' if x[1] == 'JPY>USD' else '美元→日元'}</td>"
                      f"<td class='n'>{_money(x[2], 'USD')}</td><td class='n'>{_fxr(x[3])}</td></tr>"
                      for x in reversed(d.get("fx_trades") or []))
    mk, watch = [], []
    for m, e in (d.get("extras") or {}).items():
        r = e.get("regime") or {}
        bb = r.get("bullbear") or {}
        name = _MNAME.get(m, m)
        if bb.get("state") in ("bull", "bear"):
            flip = bb.get("flip_to") or ("bear" if bb["state"] == "bull" else "bull")
            days = f"，已 {bb['days']} 个交易日" if bb.get("days") is not None else ""
            head = (f"<b>{escape(str(bb['phase_label']))}</b>：{escape(str(bb.get('phase_text') or ''))}。明细："
                    if bb.get("phase_label") else "")              # 现在处于哪个阶段（只用于展示）
            line = (f"牛熊分界 {head}{_BB[bb['state']]}（自 {escape(str(bb.get('since')))}{days}；"
                    f"{'转熊' if flip == 'bear' else '转牛'}价位 {_lvl(bb.get('level'), m)}，"
                    + (f"现价 {_lvl(bb['close'], m)}，" if bb.get("close") is not None else "")
                    + f"距翻转价位 {_pct(bb.get('distance_pct'), 2, True)}"
                    + (f"；数据日 {escape(str(bb['asof']))}" if bb.get("asof") else "") + "）")
        else:
            line = f"牛熊分界 未知（{escape(str(bb.get('note') or '指数行情取不到'))}）"
        if e.get("core_only"):
            icm = (d.get("idle_cash") or {}).get("mode")
            lab = escape(str((d.get("idle_cash") or {}).get("label") or icm))
            if icm and icm != "K0" and m in _ic_markets(icm):              # 闲置资金的方式也跟这条分界（例：Q1 纳指 1545）
                use = f"用于核心 ETF 的择时：模拟盘的闲置资金「{lab}」与基准账户（原规则）的 1655（牛市持有、熊市那份留现金）"
            elif icm and icm != "K0":
                use = "只给基准账户（原规则）的 1655 择时；模拟盘的闲置资金现在按「" + lab + "」"
            else:
                use = f"只用于核心 ETF {escape('、'.join(e['core_only']))} 的择时（牛市持有、熊市那份留现金）"
            mk.append(f"<dt>{name}</dt><dd>{line}；{use}</dd>")
            continue
        fired = "；".join((e.get("macro") or {}).get("fired") or []) or "无"
        q = r.get("quant_label") or "unknown"
        qd = (f"（{'站上' if r.get('above_ma200') else '跌破'} 200 日线，20 日波动 {_pct(r.get('vol20_pct'))}（年化），"
              f"离一年高点 {_pct(r.get('dd252_pct'), 1, True)}）") if r.get("vol20_pct") is not None else ""
        ov = (f"；判断层（市场风险报告 {escape(str(r.get('overlay_as_of') or '—'))}）：{escape(str(r.get('overlay_action')))}"
              f"（24 小时崩盘概率 {_pct(r.get('crash_prob'), 0)}，倍数 {r.get('overlay_mult')} 倍）") if r.get("overlay_action") else "；判断层：没取到"
        fjr = r.get("fwd_judgment") or {}
        fjt = ((f"（含前向记录判断层 {fjr.get('points')} 分 ×{fjr.get('mult')}，原有各层 {fjr.get('before')} 倍，取小）" if fjr.get("applied")
                else "（前向记录判断层今天没生效）") if fjr else "")
        mk.append(f"<dt>{name}</dt><dd>量化层 {_QLAB.get(q, escape(q))}{qd}{ov}；<b>明天新仓倍数 {r.get('final_mult')} 倍</b>{fjt}；{line}；"
                  f"宏观触发：{escape(fired)}</dd>")
        ccy = "USD" if m == "US" else "JPY"
        for i, w in enumerate((e.get("watchlist") or [])[:10], 1):
            tilt = w.get("tilt")
            lot = f"（一手 {_money(w.get('lot_cost'), ccy)}）" if w.get("lot_cost") else ""
            watch.append(f"<tr><td>{i}</td><td>{escape(str(w.get('ticker')))}</td><td class='muted'>{escape(str(w.get('sector') or '—'))}</td>"
                         f"<td>{_grp_tag(str(w.get('ticker')), d.get('themes') or {}, meta) if m == 'JP' else '—'}</td>"
                         f"<td>{_STATUS.get(w.get('status'), escape(str(w.get('status'))))}</td>"
                         f"<td>{_es_tag(es_map.get(str(w.get('ticker')))) if m == 'JP' else '—'}</td><td>{_bo_tag(w) or '—'}</td>"
                         f"<td class='n'>{float(w.get('score') or 0):.1f} 分</td>"
                         f"<td class='n'>{_money(w.get('close'), ccy)}</td><td>{'是' if w.get('affordable') else '否'}{lot}</td>"
                         f"<td class='muted'>{'—' if tilt is None or tilt >= 1 else f'{tilt:g} 倍'}</td>"
                         f"<td class='muted'>{escape(str(w.get('fit_tier') or '—'))}"
                         f"{('：' + escape(w['fit_why'])) if w.get('fit_why') else ''}</td></tr>")
    core_desc = " / ".join(f"{t} {float(w) * 100:g}%" for t, w in (cfg.get("core") or {}).items())
    stocks = ("日本 + 美股合计、一起排名：日本 → 美元已够的美股 → 要换汇的美股" if with_us
              else "只做日本个股，美股敞口经由东证 ETF；事先登记的研究显示 ¥100 万规模下加美股个股会拉低收益")
    from .dashboard import render as _dash
    nw = d.get("news") or {}
    dash = _dash(d, d.get("macro_now") or {}, {"summary": nw.get("summary") or {}, "generated": nw.get("generated"), "error": nw.get("error")})
    closes = {h.get("ticker"): float(h["close"]) for h in ((d.get("timeline") or {}).get("holdings") or []) if h.get("close")}
    return _PAGE.format(
        generated=escape(d["generated"]), bar=escape(_bar_txt(d)), dash=dash,
        account=_account_block(d), positions_block=_positions_block(d, closes),
        allocation=_allocation_block(d, closes, "".join(core_rows) or "<tr><td colspan=4 class='muted'>无</td></tr>"),
        market=_market_block(d),
        missing=_missing_html(d.get("missing") or [], d.get("fixed") or []) + _executor_html(d),
        first="" if d.get("history") else (
            f'<div class="muted"><b>开始前的预览</b>：模拟期 {escape(str((d.get("sim") or {}).get("start")))} 开始，现在还没有交易；'
            '下面的市场状态、候补队列、汇率都用最新收盘数据计算（不下单、不动账户）。首次运行在开始日 07:00 JST 前后'
            '（之后每个日本营业日早上一次）</div>' if d.get("preview") else
            f'<div class="muted">一个账户模式已开启，还没有运行过；首次运行在 '
            f'{escape(str((d.get("sim") or {}).get("start") or "下一个日本营业日"))} '
            f'07:00 JST 前后（之后每个日本营业日早上一次）</div>'),
        equity=_money(d["equity_jpy"]), ret=d["ret_pct"], mdd=d["max_dd_pct"], cap=_money(d["capital_jpy"]),
        cash_jpy=_money(d.get("cash_jpy")), acct=escape(_acct(d.get("broker"), with_us)),
        usd_tile=(f'<div><span class="muted">美元现金</span><b>{_money(d.get("cash_usd"), "USD")}</b>'
                  f'<span class="muted">USD/JPY {_fxr(fx)}</span></div>' if _has_usd(d.get("broker")) else
                  f'<div><span class="muted">USD/JPY（只影响核心 ETF 的日元价值）</span><b>{_fxr(fx)}</b>'
                  f'<span class="muted">{escape(str(d.get("usdjpy_src") or ""))}</span></div>'),
        todo=todo_html,
        positions="".join(pos_rows) or "<tr><td colspan=7 class='muted'>无</td></tr>",
        core="".join(core_rows) or "<tr><td colspan=4 class='muted'>无</td></tr>",
        spark=_spark(d.get("history") or []), trades=tr_rows or "<tr><td colspan=6 class='muted'>还没有平仓的交易</td></tr>",
        fx=fx_rows or "<tr><td colspan=4 class='muted'>还没有换汇</td></tr>", markets="".join(mk),
        watch="".join(watch) or "<tr><td colspan=12 class='muted'>尚无候补数据</td></tr>",
        timeline=_timeline_card(d),
        themes=_themes_html(d.get("themes") or {}, meta), policy=_policy_html(d.get("policy") or {}),
        deepdip=_deepdip_html(d.get("deepdip") or {}), fwdj=_fwdj_html(d), combo_c=_combo_c_html(d),
        threat=_threat_html(d.get("threat") or {}), commod=_commod_html(d.get("commod") or [], with_us), shadow=_shadow_html(d),
        elig=_eligibility_html(d, meta), delist=_delist_html(d, meta), cost_sales=_cost_sales_html(d.get("cost_sales") or {}),
        invest_flow=_invest_flow_html(d.get("invest_flow") or {}),
        calendar=_calendar_html(d.get("calendar") or {}), pcheck=_price_check_html(d.get("price_check") or {}),
        corp="".join(f"<li>{escape(c['date'])} {escape(c['ticker'])}：{escape(c['note'])}</li>"
                     for c in reversed(d.get("corp_log") or [])) or '<li class="muted">无</li>',
        n_trades=d.get("n_trades", 0), win=_pct(d.get("win_rate")) if d.get("win_rate") is not None else "—（还没有平仓）",
        rules=escape(f"个股 {cfg.get('max_positions')}×{int(float(cfg.get('position_pct', 0)) * 100)}%（{stocks}）；"
                     + (f"个股离场：{(d.get('exit_mode') or {}).get('label')}；" if (d.get('exit_mode') or {}).get('JP') not in (None, 'DC') else "")
                     + (f"闲置资金：{(d.get('idle_cash') or {}).get('label')}（现在：{_ic_now(d.get('idle_cash') or {})}；"
                        f"{escape(str((d.get('idle_cash') or {}).get('since') or ''))} 起；原规则 1655 + 牛熊分界只给基准账户）；"
                        if (d.get('idle_cash') or {}).get('mode') not in (None, 'K0') else
                        f"闲置资金 {core_desc}（{'熊市那份留现金' if cfg.get('core_mode') == 'split' else '熊市那份转给牛市的一只'}；"
                        "牛熊分界 = 指数收盘连续 5 天低于 250 日线 ×0.97 转熊、高于 ×1.03 转牛，2026-09-25 多因子研究后维持）；")
                     + _fee_rule(d.get("broker"), cfg)))


_EV = {"FOMC": "美联储议息", "BOJ": "日银议息", "CPI": "美国 CPI", "NFP": "美国非农就业", "ELECTION": "选举",
       "POLITICS": "政治日程", "FISCAL": "财政期限", "TRADE": "贸易 / 关税期限", "OPEC": "OPEC+ 会议", "SUMMIT": "峰会",
       "TANKAN": "日银短观", "SQ": "日本 SQ（定期）", "OPEX": "美股季度期权到期（定期）", "INDEX": "指数调整"}


def _IC_NAMES() -> dict:
    from .idle_cash import NAMES
    return NAMES


def _ic_markets(mode: str | None) -> set[str]:
    from .idle_cash import uses_market
    return uses_market(mode)


def _ic_now(ic: dict) -> str:
    """闲置资金现在拿什么（与执行器日志同一句）。"""
    from .live_unified import ic_text
    return ic_text(ic)


def _groups_meta() -> tuple[dict, dict, dict]:
    """(代码 → 東証业种, 代码 → 主题, 代码 → 公司名)。"""
    from . import jpx_list as JL
    from . import themes as TH
    from .universes import JP_READDED_S33
    s33 = dict(JP_READDED_S33)                   # 2026-09-30 起加回的航空 / 陆运（30 业种表不含，只作标签）
    s33.update((read_json(paths.home() / "industry_s33.json", {}) or {}).get("s33") or {})
    return s33, TH.members(), JL.names()


def _sg(v, nd: int = 1) -> str:
    return "—" if v is None else f"{'+' if v > 0 else '−' if v < 0 else '±'}{abs(float(v)):.{nd}f}%"


def _grp_tag(ticker: str, th: dict, meta: tuple) -> str:
    """个股的主题 / 业种标签 + 近 3 个月相对强弱（排名）。主题优先；不在主题里的写東証业种。只作参考。"""
    s33, mem, _ = meta
    g = (th or {}).get("groups") or {}
    code = str(ticker).split(".")[0]
    out = []
    for key, label, kind in ((mem.get(code), None, "主题"), (s33.get(code), None, "业种")):
        if not key or key not in g:
            continue
        x = g[key]
        name = ((th.get("themes") or {}).get(key) or {}).get("name", key)
        rk = f"（{x['rank3m']}/{x['of']}）" if x.get("rank3m") else ""
        out.append(f'<span class="tag dim" title="{kind}：近 3 个月相对 TOPIX 1000 平均，括号 = {kind}里的排名">'
                   f"{escape(name)} {_sg(x.get('r3m'))}{rk}</span>")
    return " ".join(out) or '<span class="muted">—</span>'


def _themes_html(th: dict, meta: tuple) -> str:
    """主题 / 业种：近 1 / 3 个月强弱、影响度（与日経的同步度）、新出现的联动（只作参考，不改交易）。"""
    g = (th or {}).get("groups") or {}
    if not g:
        return ""
    s33, mem, nm = meta
    names = {k: v.get("name", k) for k, v in ((th.get("themes") or {}).items())}
    yr = int(str(th.get("asof") or now_jst().date())[:4])
    y3, y10 = str(yr - 3), str(yr - 10)

    def r2(x, y=None):
        v = x.get("r2_now") if y is None else (x.get("r2_hist") or {}).get(y)
        return "—" if v is None else f"{float(v):.2f}"

    def row(k, lab):
        x = g[k]
        cls = "pos" if (x.get("r3m") or 0) > 0 else "neg"
        return (f"<tr><td>{escape(lab)}</td><td class='n'>{x.get('n', 0)} 只</td><td class='n'>{_sg(x.get('r1m'))}</td>"
                f"<td class='n {cls}'>{_sg(x.get('r3m'))}（{x.get('rank3m', '—')}/{x.get('of', '—')}）</td>"
                f"<td class='n'>{_sg(x.get('r12'))}（{x.get('rank12', '—')}/{x.get('of12', '—')}）</td>"
                f"<td class='n'>{r2(x)} / {r2(x, y3)} / {r2(x, y10)}</td></tr>")
    tk = sorted([k for k in g if k in names and g[k].get("r3m") is not None], key=lambda k: -g[k]["r3m"])
    ik = sorted([k for k in g if k not in names and g[k].get("r3m") is not None], key=lambda k: -g[k]["r3m"])
    head = (f"<tr><th>组</th><th class='n'>成员</th><th class='n'>近 1 月</th><th class='n'>近 3 月（排名）</th>"
            f"<th class='n'>12-1 个月（排名）</th><th class='n'>与日経同步度 R²：近 1 年 / {y3} / {y10}</th></tr>")
    era_i = sorted([k for k in g if k not in names and g[k].get("r12") is not None], key=lambda k: -g[k]["r12"])[:7]
    era_t = sorted([k for k in g if k in names and g[k].get("r12") is not None], key=lambda k: -g[k]["r12"])[:3]
    era = _era_q_html(th, names) + ("<p>12-1 个月领先（2026-09-28 以前的时代主线，照旧列出、照旧每月记）：业种 " + escape("、".join(era_i) or "—")
           + "；主题 " + escape("、".join(f"{k} {names[k]}" for k in era_t) or "—")
           + "<br><span class='muted'>依据 var/out/era_study.md：这样排在前面的行业之后平均还会跑赢（美国 1931〜2026 按 12 个月算 70% 的时候、"
           "日本 2006〜2026 68〜83%），但领先 3 年以上的反而容易反转。只作参考，不改交易。</span></p>") + _influence_html(th)
    t_rows = "".join(row(k, f"{k} {names[k]}") for k in tk)
    i_rows = "".join(row(k, k) for k in ik[:5]) + ("<tr><td colspan=6 class='muted'>…</td></tr>" if len(ik) > 10 else "") \
        + "".join(row(k, k) for k in ik[-5:] if k not in ik[:5])
    e = th.get("emerging") or {}
    lab = lambda t: escape(f"{t.split('.')[0]} {nm.get(t.split('.')[0], '')}".strip())            # noqa: E731
    gname = lambda k: escape(f"{k} {names[k]}" if k in names else str(k))                           # noqa: E731
    cl = "".join(
        f"<li><b>{escape(c['kind'])}</b> {c['n']} 只，群内平均相关 {c['corr_before']:.2f} → {c['corr_now']:.2f}；"
        f"最像：{'、'.join(f'{gname(k)} {v:.2f}' for k, v in c['similar'])}；"
        f"业种分布：{escape('、'.join(f'{k} {v}' for k, v in list(c['industries'].items())[:5]))}；"
        f"成员：{'、'.join(lab(t) for t in c['members'])}{' …' if c['n'] > len(c['members']) else ''}</li>"
        for c in e.get("clusters") or [])
    lk = "；".join(
        f"{lab(x['ticker'])}（{escape(str(x['own_ind'] or '—'))}）→ {gname(x['group'])} {x['corr_before']:+.2f} → {x['corr_now']:+.2f}"
        for x in (e.get("links") or [])[:10])
    emer = (f"<h3>新出现的联动（近 6 个月 {escape(' 〜 '.join(e['window']))}，对比之前 1 年）</h3>"
            f"<ul>{cl or '<li class=muted>没有新形成的股票群</li>'}</ul>"
            f"<p class='muted'>个股（现在最像的「非所属」组，相关 之前 → 现在）：{lk or '无'}</p>") if e.get("window") else (
            f"<p class='muted'>新出现的联动：{escape(str(e.get('note') or '没有算出'))}</p>")
    return ("<section class=\"card\"><h2>主题与业种：强弱、影响度、新出现的联动（只作参考，不改交易）</h2>"
            f"<p class='muted'>数据截至 {escape(str(th.get('asof') or '—'))}；近 1 / 3 月 = 近 21 / 63 个交易日相对 TOPIX 1000 平均（对数收益之和，%）；"
            "影响度 = 这一组每天的涨跌与日経225 同步的程度（R²，0〜1；历年值每年 1 月更新 var/theme_influence.json）。</p>"
            f"{era}<h3>12 个主题</h3><div class='scroll'><table>{head}{t_rows}</table></div>"
            f"<h3>東証业种（最强 5 / 最弱 5）</h3><div class='scroll'><table>{head}{i_rows}</table></div>{emer}"
            "<p class='muted'>读法：主题成员按主营业务事先写定（qbreak/themes.py）；「新联动群」= 最近半年开始一起动、以前不一起动的股票（平均连接聚类），"
            "附上它和现有业种 / 主题最像哪几个 —— 新出现的行业先这样和现有行业做关联对比，要正式加进主题表先跑 "
            "scripts/theme_link_check.py。2026-09-26 的研究：主题动量用来挑买点没有通过、行业之间的领先关系多半是时代现象"
            "（var/out/theme_study.md、us_replication_study.md）—— 这里只帮助看清结构，不是买卖信号。</p></section>")


def _era_q_html(th: dict, names: dict) -> str:
    """时代主线的 3 个月判定（qbreak/theme_monitor.quarter_rank）+ 各业种影响占比（qbreak/sector_influence.py）。"""
    eq = th.get("era_q") or {}
    ir = ((th.get("influence") or {}).get("now") or {}).get("rows") or {}
    if not eq.get("industries"):
        return f"<p class='muted'>时代主线（3 个月判定）：这次没算出（{escape(str(eq.get('quarter') or '数据不够'))}）</p>"

    def nm(g):
        return str(g).replace("、", "・")                                  # 「証券、商品先物取引業」在「、」分隔的列表里读不清

    def ind(gv):
        g, sc = gv
        v = ir.get(g)
        return escape(f"{nm(g)}（{sc:+.1f}%" + (f"｜影响占比 {v['share']:.1f}%" if v else "") + "）")
    qtd = eq.get("qtd") or {}
    q_line = ("；本季进行中（" + escape(" 〜 ".join(qtd.get("range") or [])) + "，季末才正式判定）：业种 "
              + escape("、".join(nm(g) for g, _ in qtd.get("industries") or []) or "—")) if qtd.get("industries") else ""
    return ("<p><b>时代主线（每 3 个月判定：" + escape(f"{eq['quarter']}，{eq['range'][0]} 〜 {eq['range'][1]}")
            + "，业种等权相对 TOPIX 1000 平均；影响占比 = 近 3 个月 TOPIX 涨跌里来自这个业种的份额，见下表）</b>：业种 "
            + "、".join(ind(x) for x in eq["industries"])
            + "；主题 " + escape("、".join(f"{k} {names.get(k, k)}（{v:+.1f}%）" for k, v in eq.get("themes") or []) or "—") + q_line
            + "<br><span class='muted'>2026-09-28 用户要求从「12 个月（跳过最近 1 个月）」改为每 3 个月判定；每季第一次运行记进 var/out/era_forward.csv"
            "（JP-S33Q / JP-THQ / 影响占比 JP-INFQ），记满 12 个季度起判定。事后描述（var/out/crash_mainline_posthoc.md）：3 个月的前 7 名下一季平均只多 "
            "+0.0〜0.2%（区间含 0），12-1 个月的前 7 名 +0.3〜0.9% —— 3 个月的主线是「最近谁强」，不代表下一季还强。只作参考，不改交易。</span></p>")


def _influence_html(th: dict) -> str:
    """各业种影响占比表：近 63 个交易日 TOPIX 每天的涨跌里来自各业种的份额（全部 33 业种合计 100%）。"""
    inf = th.get("influence") or {}
    now = inf.get("now") or {}
    rows = list((now.get("rows") or {}).items())
    if not rows:
        why = inf.get("error") or now.get("error") or "没有数据"
        return f"<p class='muted'>各业种影响占比：这次取不到（{escape(str(why))}）</p>"
    ml = {g for g, _ in ((th.get("era_q") or {}).get("industries") or [])}
    body = "".join(f"<tr><td>{'★ ' if g in ml else ''}{escape(str(g).replace('、', '・'))}</td><td class='n'>{v['share']:.1f}%</td><td class='n'>{v['weight']:.1f}%</td>"
                   f"<td class='n {'pos' if v['rel'] > 0 else 'neg'}'>{v['rel']:+.1f}%</td></tr>" for g, v in rows[:10])
    rest = sum(v["share"] for _, v in rows[10:])
    body += f"<tr><td class='muted'>其余 {len(rows) - 10} 个业种</td><td class='n'>{rest:.1f}%</td><td></td><td></td></tr>"
    w = now.get("window") or ["", ""]
    return (f"<h3>各业种影响占比（近 {now.get('n_days', '—')} 个交易日 {escape(w[0])} 〜 {escape(w[-1])}，TOPIX 口径）</h3>"
            "<div class='scroll'><table><tr><th>业种（★ = 时代主线）</th><th class='n'>影响占比</th><th class='n'>时价总额比重（估计）</th>"
            f"<th class='n'>这段时间相对 TOPIX</th></tr>{body}</table></div>"
            "<p class='muted'>影响占比 = 这段时间 TOPIX 每天的涨跌里来自这个业种的份额（全部 33 业种合计 100%；比重大、又和大盘同涨同跌的业种占比高）；"
            f"J-Quants 東証業種別指数（qbreak/sector_influence.py，拟合 R² {now.get('r2', '—')}）。只作参考，不改交易。</p>")


def _deepdip_html(dd: dict) -> str:
    """「≤ −15% 深跌」前向记录（qbreak/deepdip_forward.py）：现在离触发线多远、最近 120 个交易日内的事件与之后的涨跌、判定进度。只作参考，不改交易。"""
    if not dd:
        return ""
    if dd.get("error"):
        return f"<section class='card'><h2>深跌前向记录（≤ −15%）</h2><p class='muted'>这次没算出（{escape(str(dd['error']))}）</p></section>"
    st = dd.get("status") or {}
    now = "；".join(f"{escape(v.get('name', k))} 13 周线乖离 {v['dev']:+.1f}%（{escape(v['date'])}；触发线 {v['thr']:+g}%，还差 {v['gap_pp']:.1f} pp）"
                    if "dev" in v else f"{escape(k)}：{escape(str(v.get('error')))}" for k, v in st.items())
    rev = dd.get("review") or {}

    def f(x, fmt="{:+.1f}%"):
        return "—（还没到）" if x is None else fmt.format(x)
    act = "".join(
        f"<li><b>★ {escape(e['market'])} {escape(e['event_date'])}</b> 乖离 {e['dev']:+.1f}%"
        + (f"、脱线个股 {e['breadth']:.0f}%" if e.get("breadth") is not None else "")
        + f"：之后 20 天 {f(e['r20'])}、60 天 {f(e['r60'])}（历史平均 {f(e['base60'], '{:+.2f}%')}）、"
        f"买后最低 {f(e['mae60'])}{'' if e.get('mae_done') else '（到现在）'}</li>" for e in dd.get("active") or [])
    jp, pool = rev.get("jp") or {}, rev.get("pool") or {}
    judge = escape(str(jp.get("label") or "—")) + (f"（{jp['n']} 个：60 日超额平均 {jp['mean']:+.2f}%、涨的比例 {jp['win']:.0f}%）" if jp.get("mean") is not None else "")
    from . import deepdip_forward as DF
    hist = "、".join(escape(v) for v in DF.HIST.values())
    eps = f"，独立的大跌段 {pool['episodes']} 个" if pool.get("episodes") else ""
    return ("<section class='card'><h2>深跌前向记录（日経225 13 周线乖离 ≤ −15%；只记录，不改交易）</h2>"
            f"<p>现在：{now}</p>"
            + (f"<ul>{act}</ul>" if act else "")
            + f"<p class='muted'>已记事件 {dd.get('n', 0)} 个（{escape(str(dd.get('start', '')))} 起）；判定：{judge}；JP + 对照合并：{escape(str(pool.get('label') or '—'))}{eps}。"
            "最后一天的乖离是暂定值（这一周是否已完要等下一个交易日），事件第二天才判、才记，事件日不变。"
            f"历史参考（日本 / 美国是事后描述；欧洲是 2026-09-29 事先登记的核对，判定「方向一致」）：13 周线第一次到门槛之后 60 个交易日比平时多 {hist}；"
            "区间都含 0，之后 60 天涨的比例与任意一天差不多，买进后 60 天内平均还跌 6〜13%（任意一天买约 5〜6%）。"
            "规则见 qbreak/deepdip_forward.py 开头（2026-09-29 登记）。</p></section>")


def _policy_html(p: dict) -> str:
    """政策事件反应库：最近事件（事前受益 / 受损业种、到今天的实际价差）、类别历史统计、前向记录进度、60 天内的日程。只展示，不改交易。"""
    if not p:
        return ""
    st = p.get("status") or {}
    head = (f"<section class='card'><h2>政策事件反应库（只展示 + 前向记录，不改交易）</h2>"
            f"<p class='muted'>{escape(str(p.get('label') or ''))}；前向记录 {st.get('total', 0)} 条（及时 {st.get('on_time', 0)}、W20 到期 {st.get('due_w20', 0)}、"
            f"待分类 {st.get('pending', 0)}）；{escape(str(st.get('next_judge') or ''))}。事前名单由规则机械推出（2026-09 写定，含事后知识）；"
            f"「登记确认」只由前向记录授予。{('错误：' + escape(str(p['error']))) if p.get('error') else ''}</p>")
    rows = []
    for e in p.get("recent") or []:
        real = e.get("real") or {}
        rows.append(f"<tr><td>{escape(e.get('date', ''))}</td><td>{escape(e.get('category', ''))}/{escape(e.get('subtype', ''))}</td><td>{escape(e.get('name_ja', ''))}</td>"
                    f"<td>{escape('、'.join(e.get('benef') or []) or '—')}</td><td>{escape('、'.join(e.get('victim') or []) or '—')}</td>"
                    f"<td>{escape(e.get('r', ''))} / {escape(e.get('t0', ''))}</td><td class='n'>{real.get('D0', '—')}</td><td class='n'>{real.get('W5', '—')}</td><td class='n'>{real.get('W20', '—')}</td>"
                    f"<td>{'核对' if e.get('verified') else '未核对'}{'・覆面' if str(e.get('covert')) == '1' else ''}</td></tr>")
    recent = ("<h3>最近 60 个交易日的事件（确认窗口之后）</h3><div class='scroll'><table><tr><th>公布日</th><th>类别</th><th>事件</th><th>事前受益</th><th>事前受损</th>"
              "<th>反应日 / 买点</th><th class='n'>D0 价差 pp</th><th class='n'>W5 pp</th><th class='n'>W20 pp</th><th>状态</th></tr>" + "".join(rows) + "</table></div>") if rows else         "<p class='muted'>确认窗口之后还没有新事件（或研究还没跑、库不存在）。</p>"
    cats = p.get("categories") or {}
    crow = []
    for k, c in sorted(cats.items()):
        w5, w20 = c.get("W5") or {}, c.get("W20") or {}
        crow.append(f"<tr><td>{escape(k)}</td><td class='n'>{c.get('n')}</td><td>{escape('、'.join(c.get('benef') or []) or '—')}</td><td>{escape('、'.join(c.get('victim') or []) or '—')}</td>"
                    f"<td class='n'>{w5.get('mean', '—')}</td><td class='n'>{w5.get('hit', '—')}</td><td class='n'>{w20.get('mean', '—')}</td><td class='n'>{w20.get('hit', '—')}</td></tr>")
    lib = ("<h3>类别历史统计（P1 名单价差，全历史描述，不是预测）</h3><div class='scroll'><table><tr><th>类别/子类</th><th class='n'>n</th><th>受益</th><th>受损</th>"
           "<th class='n'>W5 均值 pp</th><th class='n'>W5 命中 %</th><th class='n'>W20 均值 pp</th><th class='n'>W20 命中 %</th></tr>" + "".join(crow) + "</table></div>") if crow else ""
    up = "".join(f"<li>{escape(str(x.get('date')))} {escape(str(x.get('kind')))} {escape(str(x.get('name') or ''))}</li>" for x in p.get("upcoming") or [])
    upcoming = f"<h3>60 天内的相关日程（公布后再分类录入）</h3><ul>{up}</ul>" if up else ""
    return head + recent + lib + upcoming + "</section>"


def _commod_rows() -> list[dict]:
    """商品 × 行业（同周联动；研究 var/out/commodity_fit_study.json 的 A 段）：每个商品受益 / 受损最多的行业各 2 个。"""
    from .sectors import SECTOR_ETF_JP, SECTOR_ETF_US
    r = read_json(paths.out_dir() / "commodity_fit_study.json", {}) or {}
    a, lab = r.get("A") or {}, r.get("labels") or {}
    rows = []
    for c, name in lab.items():
        row = {"k": c, "label": name}
        for side, key, names in (("jp", "jp_etf", SECTOR_ETF_JP), ("us", "us_etf", SECTOR_ETF_US)):
            v = sorted(((names.get(e, e), bt[c][0], bt[c][1]) for e, bt in (a.get(key) or {}).items() if c in bt),
                       key=lambda z: z[1])
            fm = lambda z: f"{z[0]} {z[1]:+.2f}%{'*' if abs(z[2]) >= 2 else ''}"                   # noqa: E731
            row[side + "_up"] = "、".join(fm(z) for z in v[::-1][:2] if z[1] > 0) or "—"
            row[side + "_dn"] = "、".join(fm(z) for z in v[:2] if z[1] < 0) or "—"
        rows.append(row)
    return rows


def _commod_html(rows: list[dict], with_us: bool = True) -> str:
    """商品 × 行业；不做美股个股时只列日本行业（美国行业的敏感度只对挑美股有用）。"""
    if not rows:
        return ""
    us = lambda r: f"<td>{escape(r['us_up'])}</td><td>{escape(r['us_dn'])}</td>" if with_us else ""       # noqa: E731
    tr = "".join(f"<tr><td>{escape(r['label'])}</td><td>{escape(r['jp_up'])}</td><td>{escape(r['jp_dn'])}</td>{us(r)}</tr>"
                 for r in rows)
    return ("<section class=\"card\"><details><summary><h2 style=\"display:inline\">商品 × 行业：商品涨 1% 时各行业相对大盘同周多涨 / 少涨几 %"
            "（只作参考）</h2></summary><div class=\"scroll\"><table><tr><th>商品</th><th>日本行业受益</th><th>日本行业受损</th>"
            + ("<th>美国行业受益</th><th>美国行业受损</th>" if with_us else "") + f"</tr>{tr}</table></div>"
            "<p class=\"muted\">最近 104 周、控制大盘（" + ("日本 日経225 / 美国 S&amp;P500" if with_us else "日経225")
            + "）后的回归系数，* = t ≥ 2；日本行业用 TOPIX-17 行业 ETF" + ("，美国用行业 ETF" if with_us else "")
            + "。敏感度会随时间变化，研究见 var/out/commodity_fit_study.md。</p></details></section>")


def _threat_html(t: dict) -> str:
    if not t or t.get("error"):
        return f'<p class="muted">暂不可用{("：" + escape(t["error"])) if t.get("error") else "（首次运行后出现）"}</p>'
    rows = []
    for m, name in (("US", "美股（S&P500）"), ("JP", "日本（日経225）")):
        x = t.get(m)
        if not x:
            continue
        prev = f"，20 日前 {x['prev20']:.0f} 分" if x.get("prev20") is not None else ""
        top = "、".join(f"{escape(f['label'])} {f['pct']} 分位" for f in x.get("top", []))
        obs = x.get("obs") or []
        hot = [o for o in obs if o["pct"] >= 70]
        obs_txt = ("；其他观察因子（不计入指数）：" + ("、".join(f"{escape(o['label'])} {o['pct']} 分位" for o in hot[:6])
                                                  if hot else "都在 70 分位以下")) if obs else ""
        w = x.get("watch")
        watch_txt = (f"<br>前瞻观察（金银比 + 商品波动，2026-09-25 登记、每天记录，还没验证）：{w['W']:.0f} / 100 分，自身历史 {w['W_pct']:.0f} 分位"
                     f"（≥80 = 预警、≥90 = 警戒{'，<b>现在警戒</b>' if w['W_pct'] >= 90 else ('，<b>现在预警</b>' if w['W_pct'] >= 80 else '')}）；"
                     f"金银比 60 日 {w['gs_raw']:+.1f}%、"
                     f"商品波动 {w['cv_raw']:.1f}%（年化）") if w else ""
        wj = x.get("watch_jp")
        if wj:
            flag = "，<b>现在警戒</b>" if wj["Wj_pct"] >= 90 else ("，<b>现在预警</b>" if wj["Wj_pct"] >= 80 else "")
            watch_txt += (f"<br>前瞻观察（日経两段都有效的 8 个因素，2026-09-25 登记、每天记录，还没验证）：{wj['Wj']:.0f} / 100 分，"
                          f"自身历史 {wj['Wj_pct']:.0f} 分位（≥80 = 预警、≥90 = 警戒{flag}）；对照：金银比 + 商品波动 {wj['W2']:.0f} 分"
                          f"（{wj['W2_pct']:.0f} 分位）")
        wf = x.get("wfc")
        if wf and wf.get("p10") is not None:
            pct1 = lambda v: "—" if v is None else f"{v * 100:.0f}%"                  # noqa: E731
            oos = wf.get("oos") or {}
            src = ("现行指数按 2005 年以来逐年校准折算" if wf.get("show") == "A0"
                   else f"配比优化「{escape(_WNAMES.get(wf['show'], wf['show']))}」，样本外 AUC {(oos.get('auc10') or 0):.2f}")
            watch_txt += (f"<br><b>之后 60 个交易日内跌 ≥10% 的概率：{pct1(wf['p10'])}</b>（{src}；2005 年以来平均 {pct1(wf.get('base10'))}；"
                          f"跌 ≥15%：{pct1(wf.get('p15'))}，平均 {pct1(wf.get('base15'))}）"
                          + ("。配比最优化（11 种配比方式，事先登记）在样本外都没有稳定胜过现行等权，暂不采用"
                             if not wf.get("adopted") else "")
                          + ("；这个概率在样本外也不比直接用历史平均准，只作参考" if (oos.get("bss10") or 0) <= 0 else "")
                          + ("；主要来源：" + "、".join(f"{escape(_LAB.get(f['k'], f['k']))} {f['pct']} 分位" for f in wf["top"])
                             if wf.get("top") else ""))
        fw = x.get("fwd") or {}
        fwd_txt = ("<br>前瞻对照（只记录、未验证）：" + "、".join(
            f"{ {'A0x': '去掉曲线倒挂与油价冲击', 'S': '因子调查组合', 'DOM': '领域均衡'}[k] } {v:.0f} 分" for k, v in fw.items())
            + (f"；另记录「现行 + 观察因素」{x['fwd_plus']} 个版本" if x.get("fwd_plus") else "")) if fw else ""
        rows.append(f"<dt>{name}：{x['value']:.0f} / 100 分{prev}（数据日 {escape(str(x.get('date') or '—'))}）</dt>"
                    f"<dd>同档位（{escape(str(x.get('band')))} 分）历史上"
                    f"{escape(t.get('event_def', ''))}的频率 {x.get('band_freq')}%（全期平均 {x.get('base_rate')}%）；"
                    f"主要来源（百分位）：{top}{obs_txt}{watch_txt}{fwd_txt}</dd>")
    ev = "".join(f"<li>{escape(e['date'])} {escape(_EV.get(e.get('kind'), e.get('kind', '')))}"
                 f"{('（' + escape(e['name']) + '）') if e.get('name') else ''}</li>" for e in t.get("events", []))
    us, jp = t.get("US", {}), t.get("JP", {})
    auc, hits = us.get("auc") or [None, None], us.get("hit80") or [None, None]
    note = ("只能说明风险比平时高还是低，不能预测具体哪天发生：历史检验 AUC（0.5 = 瞎猜，1 = 完美）美股 "
            f"{(auc[0] or 0):.2f} / {(auc[1] or 0):.2f}（1995–2010 / 2011–），日経 "
            f"{((jp.get('auc') or [0, 0])[0] or 0):.2f} / {((jp.get('auc') or [0, 0])[1] or 0):.2f}；"
            f"过去 {hits[1]} 次美股 ≥10% 下跌里只有 {hits[0]} 次在高点前 60 个交易日内到过 80 分。"
            "加入更多因素（v2：金融条件、MOVE 等；v3：黄金、金银比、铜、天然气、粮食、银行信贷、地缘风险 GPR）的事先登记研究"
            "都没有在两个市场稳定胜出，指数仍用原算法；配比最优化（11 种配比方式、逐年滚动的样本外检验）也没有方式通过事先定的五条标准，"
            "按历史拟合的权重在样本外反而常常更差。观察因子只列出处在自身历史 70 分位以上的。")
    return (f"<dl>{''.join(rows)}</dl><p class='muted'>{escape(note)}</p>{_domains_html(us, jp)}"
            f"<h3>接下来的已知大事件</h3><ul>{ev or '<li class=muted>无</li>'}</ul>")


def _wnames() -> tuple[dict, dict]:
    from .survey import LABELS as SL
    from .threat import LABELS as TL
    from .weights import NAMES
    return NAMES, {**TL, **SL}


_WNAMES, _LAB = _wnames()
_CLS = {"两段都提升": "有帮助", "只前半": "只在 2010 年前", "只后半": "只在 2011 年后", "都没有": "没帮助"}


def _domains_html(us: dict, jp: dict) -> str:
    """因子调查：各经济领域当前的危险度百分位（领域内不在现行模型里的因素平均）+ 历史上加进现行模型有没有帮助。"""
    du, dj = us.get("domains") or {}, jp.get("domains") or {}
    if not du and not dj:
        return ""
    order = {"两段都提升": 0, "只后半": 1, "只前半": 2, "都没有": 3}
    names = sorted(set(du) | set(dj), key=lambda n: (order.get((du.get(n) or {}).get("class"), 4), -((du.get(n) or {}).get("pct") or 0)))
    cell = lambda v: (f"<td class='n'>{v['pct']} 分位</td><td>{escape(_CLS.get(v.get('class'), '—'))}</td>" if v   # noqa: E731
                      else "<td class='n'>—</td><td>—</td>")
    tr = "".join(f"<tr><td>{escape(n)}</td>{cell(du.get(n))}{cell(dj.get(n))}</tr>" for n in names)
    return ("<details><summary>各经济领域现在的危险度（百分位，越高越危险；只作观察）</summary><div class='scroll'><table>"
            "<tr><th>领域</th><th class='n'>美股</th><th>历史上加进现行模型</th><th class='n'>日経</th><th>历史上加进现行模型</th></tr>"
            f"{tr}</table></div><p class='muted'>2026-09-25 事先登记的因子调查（22 个领域约 100 个因素）：逐个放进现行模型，两段历史都有帮助的领域不多；"
            "只用 2010 年以前挑出的因素组合在 2011 年后反而比现行模型差，所以指数不换，这张表只用来看现在哪些领域偏高。"
            "研究见 var/out/threat_factor_survey.md。</p></details>")


def write_unified_report() -> Path:
    d = build_unified_data()
    (paths.out_dir() / "report_data.json").write_text(json.dumps(d, ensure_ascii=False, indent=1, default=float),
                                                      encoding="utf-8")
    hp = paths.out_dir() / "report.html"
    hp.write_text(render_unified_html(d), encoding="utf-8")
    return hp


_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>模拟盘日报</title>
<style>
:root{{--bg:#fbfbf9;--fg:#1d1d1b;--muted:#6b6b66;--card:#ffffff;--line:#e4e2dc;--accent:#2f6f8f;--pos:#1f7a4d;--neg:#b23b2e}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#161615;--fg:#ecebe6;--muted:#a09f98;--card:#1f1f1d;--line:#34332f;--accent:#6fb3d2;--pos:#5cc08c;--neg:#e0796c}}}}
:root[data-theme="dark"]{{--bg:#161615;--fg:#ecebe6;--muted:#a09f98;--card:#1f1f1d;--line:#34332f;--accent:#6fb3d2;--pos:#5cc08c;--neg:#e0796c}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Hiragino Sans","Noto Sans CJK SC",sans-serif}}
main{{max-width:880px;margin:0 auto;padding:16px}} h1{{font-size:20px;margin:4px 0 2px}} h2{{font-size:16px;margin:0 0 8px}} h3{{font-size:14px;margin:10px 0 4px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:12px 0}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px}} .kpi div{{border:1px solid var(--line);border-radius:8px;padding:8px}}
.kpi b{{display:block;font-size:17px}} .muted{{color:var(--muted);font-size:13px}} ul{{margin:4px 0 8px;padding-left:20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{border-bottom:1px solid var(--line);padding:5px 4px;text-align:left}}
.n{{text-align:right;font-variant-numeric:tabular-nums}} .warn{{border-color:var(--neg)}} .pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .spark{{width:100%;height:120px}}
.scroll{{overflow-x:auto}} dt{{font-weight:600;margin-top:6px}} dd{{margin:0 0 4px}}
.tag{{display:inline-block;border:1px solid var(--accent);color:var(--accent);border-radius:4px;padding:0 4px;font-size:12px;white-space:nowrap}} .tag.dim{{border-color:var(--line);color:var(--muted)}}
:root{{--st-good:#0ca30c;--st-warn:#fab219;--st-serious:#ec835a;--st-crit:#d03b3b;--st-na:#8f8f89;--st-info:#2f6f8f;--s1:#2a78d6;--s2:#1baf7a;--s3:#4a3aa7;--s4:#eda100}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--st-info:#6fb3d2;--s1:#3987e5;--s2:#199e70;--s3:#9085e9;--s4:#c98500}}}}
:root[data-theme="dark"]{{--st-info:#6fb3d2;--s1:#3987e5;--s2:#199e70;--s3:#9085e9;--s4:#c98500}}
.card.top{{border-left:3px solid var(--accent)}} .hero{{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px;margin:2px 0 8px}} .hero .big{{font-size:34px;font-weight:600;line-height:1.1}} .hero .big2{{font-size:20px;font-weight:600}}
.mrow,.posrow{{display:grid;grid-template-columns:1fr;gap:2px;padding:8px 0;border-top:1px solid var(--line)}} .mrow:first-of-type,.posrow:first-of-type{{border-top:0}}
.posrow .mrow{{border-top:0;padding:4px 0 0}} .mlab{{font-size:14px}} .mval{{font-size:15px}} .mval b{{font-size:17px}}
.meter{{width:100%;height:auto;display:block;max-width:520px}} .seg{{width:100%;height:auto;display:block;max-width:360px}}
.st{{display:inline-block;border-radius:999px;padding:1px 8px;font-size:12px;font-weight:600;color:#fff;white-space:nowrap;vertical-align:middle}}
.st-good{{background:var(--st-good)}} .st-warn{{background:var(--st-warn);color:#1d1d1b}} .st-serious{{background:var(--st-serious);color:#1d1d1b}} .st-crit{{background:var(--st-crit)}} .st-na{{background:var(--st-na)}} .st-info{{background:var(--st-info)}}
.alloc{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:4px 0 8px}} .donut{{width:120px;height:120px;flex:none}} .legend{{list-style:none;padding:0;margin:0}} .legend li{{margin:2px 0}}
.sw{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
@media (min-width:640px){{.mrow{{grid-template-columns:1fr 1fr;grid-template-areas:"lab val" "bar bar" "note note"}} .mrow .mlab{{grid-area:lab}} .mrow .mval{{grid-area:val;text-align:right}} .mrow .mbar{{grid-area:bar}} .mrow .small{{grid-area:note}}}}
</style></head><body><main>
<h1>模拟盘日报 · 一个账户（{acct}）</h1>
<div class="muted">生成 {generated}；数据截至 {bar}；上面 ①〜⑦ 是持仓相关、按重要度排（每条横条：▼ = 现在，淡色区带 = 门槛，徽章 = 危不危险）</div>{first}{missing}
{account}
{positions_block}
<section class="card top"><h2>③ 今天要做的事（日本时间）</h2>{todo}</section>
{allocation}
{market}
<section class="card top"><h2>⑥ 权益曲线（日元）</h2>{spark}</section>
<section class="card top"><h2>⑦ 除息 / 拆股（已补到持仓与现金）</h2><ul>{corp}</ul></section>
{dash}
{elig}
{delist}
{pcheck}
{calendar}
<section class="card"><h2>市场状态（文字明细）</h2><dl>{markets}</dl></section>
<section class="card"><h2>个股持仓（表）</h2><div class="scroll"><table><tr><th>代码</th><th>市场</th><th class="n">股数</th><th class="n">成本</th><th class="n">止损</th><th>买入日</th><th>最近一次决算的形态</th></tr>{positions}</table></div></section>
<section class="card"><h2>核心 ETF（闲置资金，表）</h2><div class="scroll"><table><tr><th>代码</th><th class="n">份额</th><th class="n">收盘</th><th class="n">市值</th></tr>{core}</table></div></section>
{fwdj}
{combo_c}
{deepdip}
<section class="card"><details><summary><h2 style="display:inline">大事件威胁指数的明细（只展示，不参与交易）</h2></summary>{threat}</details></section>
<section class="card"><h2>候补队列（状态 → 宏观顺风度 → 就绪度，不是收益预测）</h2><div class="scroll"><table><tr><th>#</th><th>代码</th><th>板块</th><th>主题 / 业种（近 3 月相对）</th><th>状态</th><th>最近一次决算的形态</th><th>突破</th><th class="n">就绪度（满分 100）</th><th class="n">收盘</th><th>买得起一个名额</th><th>宏观倾斜</th><th>宏观顺风度</th></tr>{watch}</table></div>
<p class="muted">宏观顺风度 = 个股对日本 / 美国利率、油价、日元、信用利差，以及农产品、工业金属、黄金、天然气 ETF 的历史敏感度 × 近 60 个交易日的变化（当日横截面三分位：顺风 / 中性 / 逆风），只作参考：2026-09-25 事先登记研究显示它对之后 20 日的收益没有可靠的预测力（加商品后月末前 1/5 − 后 1/5 为 +0.35%，t 1.40；秩相关 0.006），交易排序不用它。</p>
<p class="muted">突破：<b>真突破</b> = 信号当天收盘高于过去 60 个交易日的最高价（不含当天）；<b>未破箱顶</b> = 信号成立但收盘还在箱顶之下（括号里是还差的 %）；还没触发的票显示距箱顶 %（今天要做的事里的买单也标了）。只作参考，不改交易：2026-09-26 事先登记的研究（2006-10〜，日経225 股票池，现行出场规则，每笔扣来回手续费）全部信号 638 笔：胜率 42.5%、每笔平均 +0.70%、盈亏比 1.89；其中真突破 163 笔：胜率 49.7%、每笔 +0.83%、盈亏比 1.44；未破箱顶 475 笔：胜率 40.0%、每笔 +0.66%、盈亏比 2.08。只做真突破：胜率 +7.2 pp（95% 区间 +0.7〜+13.6 pp），每笔期望 +0.13 pp 但不显著（95% 区间 −0.78〜+0.96 pp），组合 20 年年化 11.2%（现行 12.8%）、最大回撤 −36.4%（现行 −35.1%）——现行策略靠盈亏比赚钱，不是靠命中率（var/out/signal_study.md）。</p></section>
{timeline}
{themes}
{cost_sales}
{invest_flow}
{policy}
{commod}
{shadow}
<section class="card"><h2>最近平仓</h2><div class="scroll"><table><tr><th>日期</th><th>代码</th><th>市场</th><th class="n">股数</th><th class="n">损益（日元）</th><th>原因</th></tr>{trades}</table></div></section>
<section class="card"><h2>换汇记录</h2><div class="scroll"><table><tr><th>日期</th><th>方向</th><th class="n">美元</th><th class="n">汇率</th></tr>{fx}</table></div></section>
<section class="card"><h2>规则</h2><p class="muted">{rules}</p></section>
</main></body></html>"""
