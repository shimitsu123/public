"""loop2_r19_earnexit.py — 第二个研究循环第 19 轮：「决算前卖出持仓」EBX（实盘代码里已有、现在关着的 exit_before_earnings）
（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 19 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；离场的接法：candle_portfolio.run 的 exit_tick
（MixEngine.EXIT_TICK / _tick_exit：指定的收盘日还拿着 → 第二天开盘卖，reason = pre_earnings；缺省 None = 不变）。
为什么挑这个题（照实写）：
  - 本轮原来想做 EBG「决算前 2 个交易日不进场」（模拟盘 2026-09-24 起在用、当时记「无法用历史回测验证」）。登记前的规模检查（只数个数、
    没有算任何收益）：B1 的 J 年代日本个股买入 63 笔、E 年代 43 笔里，成交日落在决算前 2 个交易日之内的都是 0 笔（被挡的只有 B1 本来就没买的信号：
    J 128 个里 5 个、Jx 792 个里 36 个）→ 账户必然与 B1 完全相同、S1 必然不过 → 不拿它占做法（没登记、不算做法），
    「现行规则挡不到 B1 的任何一笔」作为事实记进 sim_changes；它在 Jx 上的逐笔对比改成本轮的只描述项（下面）。
  - 换成同一个数据能检验、而且真会改变交易的那一条：trader.exit_reason 里的 exit_before_earnings（决算前 ≤ 1 个交易日 → 卖出；
    现在 var/best_params.json 是 false，统一账户的引擎也没接）。突破买进的票持有几周〜几个月，一年 4 次决算 → 相当一部分持仓会跨过开示；
    决算前卖 = 躲开开示日的跳空（两个方向），代价是错过开示后的漂移（文献：决算公布的风险溢价 Frazzini & Lamont 2007、Barber et al. 2013 →
    拿着过决算平均是赚的；fins_event_study（2026-09-27）：开示后的短期收益为负 → 反过来支持卖）。两边都有理由 → 值得用历史定。
  - 不是事后组合：一条规则、参数 = 实盘代码里的常数（≤ 1 个交易日）、不学参数 → S6 / S7 不适用。家族「个股层·决算日程」1 / 3（新家族）。
做法 EBX（改变个股交易 → S5 适用）：
  - 开示日 = 決算短信（{1Q,2Q,3Q,FY}FinancialStatements，连结 / 单体都算；fins_event_data.FS_RE 同一个口径）每一期 (CurFYEn, CurPerType)
    第一次开示的日期（订正不算）；J-Quants bulk fins/summary（只在缓存，不入库）。
  - 实盘的判断（trader.exit_reason，today = 成交日 f 的早上）：D = f 当天或之后第一个开示日，e = qbreak.events.trading_days_until(D, f)，
    e ≤ 1 → 当天开盘卖。回测里同一件事 = 第 i 天收盘还拿着、下一个交易日 f 的 e ≤ 1 → 第二天开盘卖（= 开示日 D（不是交易日 → 它之前最后一个交易日）
    的前一个交易日开盘卖；D 当天开盘才买进的持仓会拿着过开示，同实盘）。只看日本个股；核心、离场的其它规则、买点全部同 B1。
  - 开示日数据的第一天（数据里最早的开示日，现在 2016-09-01）之前不触发（同实盘「取不到决算日」）→ Z 不变；E 只有 2016-09；J 全部适用。
  - S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折的规则），
    逐笔单独模拟（combo_all_study.outcomes 同一做法：X6 vs X6 + 决算前卖出；第 17 轮 OCX 同一个写法）→ 胜率差、每笔差都要 ≥ 0；
    W 只有 2016-09 有开示日 → 实际主要看 Jx。
第一关：research_loop2.stage1（trade = W / Jx 的逐笔差，lenses = None，posthoc = None）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次；形状预定 = 把所有票的开示日一起平移同一个随机的交易日数（|k| > 5，同样密度的「假决算日」）。
接线核对：登记前（不看 EBX 的结果）：① 触发日全放在数据之后（永远不触发）→ J 的账户与 B1 逐项相同；② 换一组一定触发的日子（每只票每天）→
  pre_earnings 离场 > 0 且账户 ≠ B1。同一次运行里再报 EBX 的 pre_earnings 离场笔数（应 > 0）。
只描述（不参与判定）：各年代 B1 的日本个股持仓里会被 EBX 提前卖的笔数（收盘拿着过触发日）、EBX 的 pre_earnings 离场笔数、个股笔数 / 胜率 / 每笔、
  每年收益差；W / Jx 被改变的笔数与它们 X6 / EBX 的平均；EBG（决算前 2 个交易日不进场）：B1 账户里成交日 e ≤ 2 的买入笔数、
  W / Jx 里 e ≤ 2 的信号（X6 逐笔，面板的 net）与其余信号的胜率 / 每笔差。
事前预期（照实写）：决算公布的风险溢价在美国稳健、日本也有报告 → 提前卖多半略亏；开示日跳空两边都有 → 回撤可能小一点。
  E / Z 几乎不变 → S1 只能靠 J；S5 看 Jx 的逐笔。第一关约 12%、第二关约 20%，「更好候选」约 2%。
局限（照实写）：用的是实际开示日（实盘用事先公布的決算発表予定日，延期时不同、少见）；J-Quants 的数据到 2026-09-25 → J 最后几天看不到 10 月初的开示。
运行：python scripts/loop2_r19_earnexit.py（第一关）；--scale（只数个数、不算收益）；--wiring（登记前的接线核对，只比 B1 与「不触发 / 一定触发」）。
输出 var/out/loop2_r19_earnexit.md / .json（只有汇总数，不含 J-Quants 原始数据）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop_common as LCM                                                    # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 19
IDS = ("EBX",)
FAMILY = "个股层·决算日程"
POSTHOC = False
OUT = "loop2_r19_earnexit"
EXIT_E = 1                       # trader.exit_reason：earnings_in_days ≤ 1 → 卖（实盘代码里的常数）
BLACKOUT = 2                     # = var/best_params.json earnings_blackout_days（EBG 只描述用；tests 核对）
LOOKBACK_CAL_DAYS = 14           # 只在开示日之前 14 个日历日里找（连休最长时 2 个交易日也在这里面）
CORE_T = "1655.T"
REASON = "pre_earnings"


# ───────────────────────── 开示日与触发日（tests/test_loop2_r19.py） ─────────────────────────
def disclosure_dates(F: pd.DataFrame | None = None) -> dict[str, pd.DatetimeIndex]:
    """票 → 開示日（決算短信每一期 (CurFYEn, CurPerType) 第一次开示；连结 / 单体都算、订正不算；升序去重）。"""
    import fins_event_data as FD
    import jq_extra_data as JX
    from qbreak import jq_data as JD
    cols = ["DiscDate", "Code", "DocType", "CurPerType", "CurFYEn"]
    if F is None:
        F = JD.read_bulk(JX.bulk_files("fins/summary"), cols)
    doc = F["DocType"].fillna("").astype(str)
    x = F[doc.str.match(FD.FS_RE)].copy()
    x["DiscDate"] = pd.to_datetime(x["DiscDate"], errors="coerce")
    x = x.dropna(subset=["DiscDate"])
    x["CurFYEn"] = x["CurFYEn"].fillna("").astype(str)
    x["CurPerType"] = x["CurPerType"].fillna("").astype(str)
    first = x.groupby(["Code", "CurFYEn", "CurPerType"])["DiscDate"].min().reset_index()
    first["ticker"] = JX._tickers(first["Code"])
    return {t: pd.DatetimeIndex(sorted(g["DiscDate"].dt.normalize().unique())) for t, g in first.dropna(subset=["ticker"]).groupby("ticker")}


def data_from(disc: dict[str, pd.DatetimeIndex]) -> pd.Timestamp | None:
    """开示日数据的第一天（之前不触发）。"""
    firsts = [d[0] for d in disc.values() if len(d)]
    return min(firsts) if firsts else None


def e_days(disc: pd.DatetimeIndex, f) -> int | None:
    """成交日 f 的早上看：f 当天或之后第一个开示日 D → trading_days_until(D, f)（实盘同一个函数）；没有 → None。"""
    from qbreak.events import trading_days_until
    f = pd.Timestamp(f).normalize()
    k = int(disc.searchsorted(f, side="left"))
    if k >= len(disc):
        return None
    return trading_days_until(disc[k].date(), f.date(), "JP")


def trigger_fills(disc: pd.DatetimeIndex, days, n: int, since=None) -> pd.DatetimeIndex:
    """days 里 e_days ≤ n 的成交日 f（f < since 不算）—— 按开示日往前找（与逐日算 e_days 等价，tests 核对）。"""
    from qbreak.events import trading_days_until
    days = pd.DatetimeIndex(days)
    out = set()
    for D in disc:
        cand = days[(days >= D - pd.Timedelta(days=LOOKBACK_CAL_DAYS)) & (days <= D)]
        for f in cand:
            if since is not None and f < pd.Timestamp(since):
                continue
            if trading_days_until(D.date(), f.date(), "JP") <= n:
                out.add(f)
    return pd.DatetimeIndex(sorted(out))


def fill_map(names, days, disc: dict[str, pd.DatetimeIndex], n: int, since) -> dict[str, pd.DatetimeIndex]:
    """票 → e ≤ n 的成交日（只含有开示日、有这种日子的票）。"""
    out = {}
    for t in names:
        d = disc.get(t)
        if d is None or not len(d):
            continue
        b = trigger_fills(d, days, n, since)
        if len(b):
            out[t] = b
    return out


def exit_tick(days, fills: dict[str, pd.DatetimeIndex]) -> dict[str, frozenset]:
    """{票: {收盘日}}：成交日 f 的 e ≤ 1 → f 的前一个交易日收盘还拿着就第二天（= f）开盘卖。"""
    days = pd.DatetimeIndex(days)
    out = {}
    for t, fs in fills.items():
        k = days.get_indexer(fs)
        s = frozenset(days[j - 1] for j in k[k >= 1])
        if s:
            out[t] = s
    return out


def ebx_flags(index: pd.DatetimeIndex, k_fill: int, fills_t) -> np.ndarray:
    """单笔模拟用：买入那根（位置 k_fill）起每天收盘，下一根 K 线的日子在 fills_t（e ≤ 1 的成交日）里 → True（第二天开盘卖）。"""
    n = len(index)
    out = np.zeros(n, bool)
    if fills_t is None or not len(fills_t) or not 0 <= k_fill < n - 1:
        return out
    nxt = pd.DatetimeIndex(index[1:]).isin(pd.DatetimeIndex(fills_t))
    out[:-1] = nxt
    out[:k_fill] = False
    return out


def signal_hit(tickers, dates, disc: dict[str, pd.DatetimeIndex], n: int, since) -> np.ndarray:
    """每个信号（票, 信号日）：成交日 f = 信号日之后第一个东证交易日；f ≥ since 且 e_days(f) ≤ n → True（EBG 只描述用）。"""
    from qbreak.calendar_jp import next_trading_day
    out = np.zeros(len(tickers), bool)
    nxt: dict = {}
    for i, (t, s) in enumerate(zip(tickers, pd.DatetimeIndex(pd.to_datetime(dates)))):
        d = disc.get(t)
        if d is None or not len(d):
            continue
        if s not in nxt:
            nxt[s] = pd.Timestamp(next_trading_day(s.date()))
        f = nxt[s]
        if since is not None and f < pd.Timestamp(since):
            continue
        e = e_days(d, f)
        out[i] = e is not None and e <= n
    return out


# ───────────────────────── 逐笔（S5）与账户里的交易 ─────────────────────────
def trade_pair(t: str, df: pd.DataFrame, d, p0, bt, fills_t, end_bars: int) -> dict | None:
    """combo_all_study.outcomes 同一做法：先按死叉定买入（a），再把卖出判定换成吊灯 X6（b）、换成 X6 或决算前卖出（c）。没买到 / 没卖出 → None。"""
    from qbreak import exit_forward as XF
    d = pd.Timestamp(d)
    if d not in df.index:
        return None
    pos = int(df.index.get_loc(d))
    end = df.index[min(len(df) - 1, pos + end_bars)]
    f = df.copy()
    f["entry"] = np.asarray(df.index == d)
    try:
        a = XF._one(t, f, p0, bt, d, end)
    except ValueError:
        return None
    if a is None or a["reason"] == "end":
        return None
    kk = int(f.index.get_loc(pd.Timestamp(a["entry_date"])))
    px = float(f["Open"].to_numpy(float)[kk]) * (1 + bt.exec_cfg.slippage_pct / 100)
    ch = XF.chandelier_flags(f, kk, px)
    b = XF._one(t, f.assign(dead_cross=ch), p0, bt, d, end)
    eb = ebx_flags(f.index, kk, fills_t)
    c = XF._one(t, f.assign(dead_cross=ch | eb), p0, bt, d, end)
    if b is None or c is None or b["reason"] == "end" or c["reason"] == "end" or b["entry_date"] != a["entry_date"] \
            or c["entry_date"] != a["entry_date"]:
        return None
    return {"x6": float(b["ret_pct"]), "ebx": float(c["ret_pct"]), "changed": b["exit_date"] != c["exit_date"]}


def other_stocks(W: dict, disc: dict, since) -> dict:
    """S5：W / Jx 里 B1 会买的信号（W2 + C 那一折），逐笔 X6 vs X6 + 决算前卖出（同一批信号；每笔扣同一个来回成本）。
    另报 EBG（只描述）：e ≤ 2 的信号（面板的 net）与其余信号的胜率 / 每笔差。"""
    import combo_all_common as CA
    import combo_all_study as CS
    import sell_confirm as SCF
    D, SM = W["D"], W["SM"]
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    R1 = {e: CA.fit_c([D[x] for x in LCM.ERAS if x != e]) for e in LCM.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        fa = (SM["J2"] if s == "Jx" else SM[s])["fa"]
        rows, mism = [], 0
        fills: dict = {}
        for _, r in X[kc].iterrows():
            t = r["ticker"]
            if t not in fills:
                d = disc.get(t)
                fills[t] = trigger_fills(d, fa[t].index, EXIT_E, since) if d is not None and len(d) else pd.DatetimeIndex([])
            x = trade_pair(t, fa[t], r["date"], W["p0"], bt, fills[t], CS.END_BARS)
            if x is None:
                continue
            mism += int(abs((x["x6"] - rt) - float(r["net"])) > 1e-6)
            rows.append(x)
        x6 = np.array([x["x6"] for x in rows]) - rt
        eb = np.array([x["ebx"] for x in rows]) - rt
        ch = np.array([x["changed"] for x in rows], bool)
        net = X["net"].to_numpy(float)[kc]
        hit = signal_hit(X["ticker"].to_numpy()[kc], X["date"].to_numpy()[kc], disc, BLACKOUT, since)
        dl = CA.delta(net, ~hit)
        out[s] = {"n": int(len(rows)), "mismatch_vs_panel": int(mism),
                  "dwin": float(((eb > 0).mean() - (x6 > 0).mean()) * 100) if len(rows) else None,
                  "dmean": float(eb.mean() - x6.mean()) if len(rows) else None,
                  "changed": int(ch.sum()),
                  "changed_x6_mean": float(x6[ch].mean()) if ch.any() else None,
                  "changed_ebx_mean": float(eb[ch].mean()) if ch.any() else None,
                  "ebg": {"n": int(dl["n"]), "hit": int(hit.sum()), "dwin": dl["dwin"], "dmean": dl["dmean"],
                          "hit_win": float((net[hit] > 0).mean() * 100) if hit.any() else None,
                          "hit_mean": float(net[hit].mean()) if hit.any() else None}}
    return out


def last_trades() -> pd.DataFrame:
    """刚跑完的那次账户回测里的全部交易（含期末未平仓的 reason = end）。"""
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    return pd.DataFrame(eng.st.trades)


def jp_stock_trades(tr: pd.DataFrame, a: str, b: str | None) -> pd.DataFrame:
    """窗口内（买入日 a〜b）的日本个股交易（不含 1655 与其它核心键）。"""
    if not len(tr):
        return tr
    x = tr[tr["ticker"].astype(str).str.endswith(".T") & (tr["ticker"] != CORE_T)]
    ed = pd.to_datetime(x["entry_date"])
    m = (ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)
    return x[m.to_numpy()]


def entries_on(tr: pd.DataFrame, fills: dict[str, pd.DatetimeIndex], a: str, b: str | None) -> dict:
    """EBG 只描述：窗口内日本个股买入里，(票, 买入日 = 成交日) 的 e ≤ 2 的笔数。"""
    x = jp_stock_trades(tr, a, b)
    if not len(x):
        return {"entries": 0, "on": 0}
    hit = [t in fills and pd.Timestamp(d) in fills[t] for t, d in zip(x["ticker"], pd.to_datetime(x["entry_date"]))]
    return {"entries": int(len(x)), "on": int(sum(hit))}


def held_through(tr: pd.DataFrame, tick: dict[str, frozenset], a: str, b: str | None) -> int:
    """B1 的日本个股持仓里，某个触发收盘日 p 还拿着（买入日 ≤ p < 卖出日）的笔数 = EBX 会提前卖的。"""
    x = jp_stock_trades(tr, a, b)
    n = 0
    for t, ed, xd in zip(x["ticker"], pd.to_datetime(x["entry_date"]), pd.to_datetime(x["exit_date"])):
        n += any(ed <= p < xd for p in tick.get(t, ()))
    return n


def pre_exits(tr: pd.DataFrame, a: str, b: str | None) -> int:
    x = jp_stock_trades(tr, a, b)
    return int((x["reason"] == REASON).sum()) if len(x) else 0


def era_maps(W: dict, disc: dict, since) -> dict:
    """每个年代：e ≤ 1 的成交日（EBX）、e ≤ 2 的成交日（EBG 只描述）、EBX 的触发收盘日。"""
    out = {}
    for e in L2.ERAS:
        names, days = W["ctx"][e]["names"], W["ctx"][e]["days"]
        f1 = fill_map(names, days, disc, EXIT_E, since)
        out[e] = {"f1": f1, "f2": fill_map(names, days, disc, BLACKOUT, since), "tick": exit_tick(days, f1)}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r19_earnexit.py", "scripts/candle_portfolio.py",
                                 "scripts/fins_event_data.py", "scripts/jq_extra_data.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop2.py", "scripts/combo_all_study.py", "qbreak/exit_forward.py", "qbreak/events.py",
                                 "qbreak/calendar_jp.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    disc = disclosure_dates()
    since = data_from(disc)
    M = era_maps(W, disc, since)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        rb = L2.run(W, e)
        tb = last_trades()
        tick = M[e]["tick"]
        rc = L2.run(W, e, exit_tick=tick) if tick else rb
        tc = last_trades() if tick else tb
        base[e] = {**_acct(rb), "years": rb.get("years")}
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = {"ticks": int(sum(len(v) for v in tick.values())), "b1_held_through": held_through(tb, tick, a, b),
                   "pre_exits": pre_exits(tc, a, b), "stock_trades": {"B1": rb["n"], "EBX": rc["n"]},
                   "ebg_b1": entries_on(tb, M[e]["f2"], a, b)}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, disc, since)
    s1 = {"EBX": R2.stage1(cand, base, trade=os_, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"EBX": cand}, "stage1": s1, "drift": drift, "describe": desc, "other_stocks": os_,
           "data_from": str(since.date()) if since is not None else None, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["EBX"]
    os_ = res["other_stocks"]
    L = [f"# 第二个研究循环第 19 轮：决算前卖出持仓 EBX（实盘代码里的 exit_before_earnings）（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r19_earnexit.py 开头）", "",
         f"- **EBX：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(os_['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(os_['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(os_['Jx']['dwin'], '{:+.2f}')} / {_f(os_['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | EBX（Calmar 差） | 个股笔数 B1 → EBX |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    ds = res["describe"]
    for e in L2.ERAS:
        t = ds[e]["stock_trades"]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['EBX'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {t['B1']} → {t['EBX']} |")
    hit = sum(ds[e]["pre_exits"] for e in L2.ERAS)
    L += ["", "接线核对（不参与判定）：EBX 的 pre_earnings 离场 " + "、".join(f"{e} {ds[e]['pre_exits']}" for e in L2.ERAS)
          + f" 笔（> 0 = 钩子生效：{'是' if hit > 0 else '★ 否'}）"]
    L += ["", f"只描述（不参与判定；开示日数据从 {res['data_from']} 起）："]
    for e in L2.ERAS:
        x = ds[e]
        L.append(f"- {e}：触发收盘日 {x['ticks']} 个（票 × 日）；B1 的日本个股持仓里会被提前卖的 {x['b1_held_through']} 笔；"
                 f"EBG：B1 的买入 {x['ebg_b1']['entries']} 笔里成交日在决算前 2 个交易日之内的 {x['ebg_b1']['on']} 笔")
    for s in ("W", "Jx"):
        o, g = os_[s], os_[s]["ebg"]
        L.append(f"- {s}：逐笔 {o['n']} 笔（与面板不一致 {o['mismatch_vs_panel']}），被 EBX 改变 {o['changed']} 笔（它们 X6 平均 {_f(o['changed_x6_mean'], '{:+.2f}')}% → "
                 f"EBX {_f(o['changed_ebx_mean'], '{:+.2f}')}%）；EBG：信号 {g['n']} 个里 e ≤ 2 的 {g['hit']} 个（胜率 {_f(g['hit_win'], '{:.1f}')}%、"
                 f"每笔 {_f(g['hit_mean'], '{:+.2f}')}%）→ 去掉它们：胜率差 {_f(g['dwin'], '{:+.2f}')} pp、每笔差 {_f(g['dmean'], '{:+.2f}')} pp")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["EBX"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（EBX − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数个数（触发日、B1 持仓里会被提前卖的笔数、EBG 的买入笔数与被挡信号数；不跑 EBX、不看收益）。"""
    import combo_all_common as CA
    W = L2.load()
    disc = disclosure_dates()
    since = data_from(disc)
    M = era_maps(W, disc, since)
    D, A = W["D"], W["A"]
    out = {"data_from": str(since.date()) if since is not None else None}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        L2.run(W, e)
        tb = last_trades()
        keep = CA.apply_c(CA.fit_c([D[x] for x in LCM.ERAS if x != e]), A[e])
        out[e] = {"ticks": int(sum(len(v) for v in M[e]["tick"].values())), "b1_jp_trades": int(len(jp_stock_trades(tb, a, b))),
                  "b1_held_through": held_through(tb, M[e]["tick"], a, b), "ebg_b1": entries_on(tb, M[e]["f2"], a, b),
                  "ebg_signals": {"n": int(keep.sum()), "hit": int(signal_hit(A[e]["ticker"].to_numpy()[keep], A[e]["date"].to_numpy()[keep],
                                                                                disc, BLACKOUT, since).sum())}}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：J 年代 ① 触发日全在数据之后（永远不触发）→ 账户与 B1 逐项相同；② 每只票每天都触发 → pre_earnings 离场 > 0、账户 ≠ B1（不是 EBX 的触发日）。"""
    W = L2.load()
    e = "J"
    a, b = W["ctx"][e]["windows"][e]
    names = list(W["ctx"][e]["names"])
    days = pd.DatetimeIndex(W["ctx"][e]["days"])
    rb = L2.run(W, e)
    never = {t: frozenset([days[-1] + pd.Timedelta(days=3650)]) for t in names}
    r0 = L2.run(W, e, exit_tick=never)
    n0 = pre_exits(last_trades(), a, b)
    every = {t: frozenset(days) for t in names}
    r1 = L2.run(W, e, exit_tick=every)
    n1 = pre_exits(last_trades(), a, b)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    out = {"never_same_as_b1": all(rb.get(k) == r0.get(k) for k in keys) and n0 == 0,
           "every_differs": n1 > 0 and any(rb.get(k) != r1.get(k) for k in keys), "every_pre_exits": n1}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["never_same_as_b1"] and out["every_differs"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 19 轮：EBX（决算前卖出持仓，实盘代码里的 exit_before_earnings）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（只比 B1 与「不触发 / 一定触发」）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
