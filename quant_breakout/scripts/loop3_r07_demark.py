"""loop3_r07_demark.py — 第三个研究循环第 7 轮（用户的题）：Jason Perl（DeMark 指标）的观点 → 日本个股的离场与买点
DMX / DMT / DMN 三个做法（2026-10-02 登记；先提交后只运行一次；用掉 3 个做法 → 12 / 20）。

用户（2026-10-02）：「jason perl的观点也要进行详细分析加到现在的研究中 继续现在的研究 然后再继续现在提出的观点」。
循环的规则：scripts/research_loop3.py（三个做法都改个股交易 → kind = "stock"，第二关的形状在第一关全过之后另行登记时写定）；
基准 B1：scripts/loop2_common.py；离场的接法 = candle_portfolio.run 的 exit_tick（第三个循环第 3 轮 FXX / 第二个循环第 19 轮 EBX 同一个钩子）；
买点的接法 = em_tick（第 6 轮 IBS 同一个钩子）。
Jason Perl 是谁、他的观点（2026-10-02 联网核对；仅对检索时点有效）：
  - 能确认的：《DeMark Indicators》（Bloomberg Market Essentials: Technical Analysis，Bloomberg Press 2008，Tom DeMark 写序）的作者；
    写书时任 UBS 投资银行 FICC（固定收益、外汇、大宗商品）技术策略全球主管；DeMark 是他的导师。2026 年的职务与最近的市场判断没有查到可靠来源 → 不写。
  - 他的方法（书第 1 章 TD Sequential；实现在 qbreak/demark.py，规则与简化处写在那里）：趋势会「衰竭」，TD Setup（9）/ TD Countdown（13）找衰竭点；
    卖 countdown 13 = 上涨衰竭 → 多头分批了结；TDST（setup 的支撑 / 阻力）= 偏多 / 偏空的分界；不要抢在 13 之前；多个周期（周线 → 日线）配合。
为什么这样做（照实写）：以前没有做过 DeMark 指标（仓库里搜不到）→ 新方法、新家族，不是事后组合（S7 不适用）；参数全用书里的推荐设定
  （9 / 13、4 根 / 2 根、第 13 根对第 8 根收盘）→ 没有学出来的参数（S6 不适用）；改个股交易 → S5 适用。B1 是顺势突破系统，Perl 的方法是逆势找衰竭，
  三个做法分别把他的三条用法套到 B1 的日本个股上：
做法 DMX（个股层·DeMark 离场 1 / 3）：持有的日本个股出现日线「卖 countdown 13」（上涨衰竭）→ 第二天开盘全部卖出（书：13 时了结；分批了结引擎做不到 → 全卖）。
做法 DMT（个股层·DeMark 离场 2 / 3）：持有的日本个股收盘跌破「最近一次完成的卖 setup 的 TDST」（setup 9 根里最低的真实低点；Perl：TDST 之下 = 偏空）→ 第二天开盘卖。
做法 DMN（个股层·DeMark 买点 1 / 3）：日本个股的买点信号日或之前 4 个交易日（一共 5 个交易日 = 一周）这只票出现过日线卖 countdown 13 → 这个候选不开新仓
  （书：13 = 衰竭；不在衰竭刚出现时追高）。5 天是事先选的（一周），不是学出来的。
  三个做法里买点、其余离场（X6 吊灯止损、+25% 止盈等）、核心（FJE）、判断层全部同 B1；TD Sequential 用引擎同一份日线（qbreak/demark.sequential，
  第 i 天收盘才知道 → 第 i + 1 天开盘成交；exit_tick 只给日本个股，不给核心 ETF）。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折的规则）：
  DMX / DMT = 逐笔单独模拟 X6 vs X6 + 那条离场（loop3_r03_yenexit.trade_pair 原样，只把触发日换成这只票自己的 13 / TDST 跌破日）；
  DMN = 被挡的信号去掉之后保留 vs 全部；都要胜率差、每笔差 ≥ 0。
第一关：research_loop3.stage1（trade = W / Jx 的差，lenses = None，posthoc = None），三个做法各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状在那时写定（预定：每只票自己的触发日在它的交易日上整体循环平移同一个 k，
  research_loop3.shift_ks 同一组种子；DMN 同样平移挡的日子）。
接线核对（登记前，不看候选的收益）：J 年代 ① 触发日全空 → 账户与 B1 逐项相同；② DMX / DMT 的触发日个数 > 0、DMN 的 em_tick 对数 > 0。
规模核对（登记前，只看 B1 的持仓与信号、不看收益）：见 sim_changes 的登记一节（--scale）。
只描述（不参与判定；「详细分析 Perl 的观点」）：
  D1 指数（26 个：K4 研究的 25 个市场 + 纳指 100 ^NDX，日线与周线，1990 起）：卖 / 买 countdown 13、完美的卖 / 买 setup 9 之后 5 / 10 / 20 个交易日
     （周线 4 / 8 / 13 周）的涨跌 − 同一个指数同样长度的平均涨跌（pp），与「方向对」的比例（卖信号之后跌、买信号之后涨）vs 平时；
     26 个指数各自的差取平均，另报方向对的指数个数。
  D2 个股（B1 的日本个股：Z / E / J 年代的日経225 成分）：日线卖 / 买 countdown 13 之后 10 / 20 个交易日 − 平时（逐笔平均，pp）。
  D3 现在（数据最后一天）：日経225、S&P500、纳指 100 的日线 / 周线 TD Sequential 状态（setup 计数、countdown 计数、最近的 13、TDST）。
  D1 / D3 只用已经收盘的 K 线（complete_bars：^N225 按东京收盘、其余按纽约收盘；盘中运行时去掉当日还没收盘的那一根）。
事前预期（照实写，按一般的研究与市场历史估计，不是这个项目的结果）：
  - DeMark 指标的公开学术检验很少；常见的结论是单独用的预测力弱、因市场与周期而异。B1 的利润主要来自少数大赢家（突破之后的长趋势）→
    DMX 在 13 卖掉会砍掉一部分大赢家（可能为负），DMT 是另一种追踪止损、与 X6 差不多（差小），DMN 挡的信号少。
  - 第一关：DMX 约 10%、DMT 约 10%、DMN 约 5%；第二关各约 10% → 三个合起来「更好候选」约 2〜3%。
  - D1：卖 13 之后指数的超额收益接近 0、买 13 之后略正（跌多了反弹）的可能性大；D2 类似。
运行：python scripts/loop3_r07_demark.py（第一关 + 只描述）；--scale（只数个数、不算收益）；--wiring（登记前的接线核对）；--now（只算 D3 现在的状态）。
输出 var/out/loop3_r07_demark.md / .json。非投资建议。
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
import loop3_r03_yenexit as X3                                               # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 7
IDS = ("DMX", "DMT", "DMN")
FAMILY = {"DMX": "个股层·DeMark 离场", "DMT": "个股层·DeMark 离场", "DMN": "个股层·DeMark 买点"}
POSTHOC = False
KIND = "stock"
WIN_N = 5                                                                     # DMN：信号日与之前 4 个交易日
OUT = "loop3_r07_demark"
CORE = X3.CORE
IDX_FROM = "1990-01-01"
HZ_D, HZ_W = (5, 10, 20), (4, 8, 13)
NOW_SYMS = {"^N225": "日経225", "^GSPC": "S&P500", "^NDX": "纳指 100"}


# ───────────────────────── 触发日（纯函数，tests/test_loop3_r07.py） ─────────────────────────
def triggers(df: pd.DataFrame) -> dict[str, pd.DatetimeIndex]:
    """一只票的日线 → {"sell13": 卖 countdown 13 完成的日子, "tdst": 收盘 < 最近一次卖 setup 的 TDST 的日子, "gate": DMN 挡的日子}。"""
    from qbreak import demark as DM
    x = df[["Open", "High", "Low", "Close"]].astype(float).dropna()
    if len(x) < 30:
        e = pd.DatetimeIndex([])
        return {"sell13": e, "tdst": e, "gate": e}
    s = DM.sequential(x)
    s13 = s["sell13"].to_numpy(bool)
    below = (x["Close"].to_numpy(float) < s["sell_setup_tdst"].to_numpy(float))   # NaN（还没有卖 setup）→ False
    gate = pd.Series(s13.astype(float), index=x.index).rolling(WIN_N, min_periods=1).max().to_numpy() > 0.5
    idx = pd.DatetimeIndex(x.index).normalize()
    return {"sell13": idx[s13], "tdst": idx[below], "gate": idx[gate]}


def all_triggers(fa: dict, names=None) -> dict[str, dict[str, pd.DatetimeIndex]]:
    keys = list(fa) if names is None else [t for t in names if t in fa]
    return {t: triggers(fa[t]) for t in keys if str(t).endswith(".T") and t not in CORE}


def exit_tick_of(trig: dict, key: str) -> dict[str, frozenset]:
    """exit_tick {日本票: {触发收盘日}}（那天收盘还拿着 → 第二天开盘卖）。"""
    return {t: frozenset(v[key]) for t, v in trig.items() if len(v[key])}


def em_tick_of(trig: dict, days=None) -> dict:
    """DMN 的 em_tick {(票, 信号日): 0.0}：挡的日子（只留引擎的交易日里的）。"""
    keep = None if days is None else pd.DatetimeIndex(days)
    out = {}
    for t, v in trig.items():
        g = v["gate"] if keep is None else v["gate"].intersection(keep)
        for d in g:
            out[(t, d)] = 0.0
    return out


def gated(trig: dict, tickers, dates) -> np.ndarray:
    """每个（票, 信号日）是不是 DMN 挡的日子。"""
    out = np.zeros(len(tickers), bool)
    for k, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        v = trig.get(str(t))
        if v is not None and len(v["gate"]):
            out[k] = pd.Timestamp(d).normalize() in v["gate"]
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, trig_w: dict, trig_jx: dict) -> dict:
    """S5：DMX / DMT = 逐笔 X6 vs X6 + 触发日离场（X3.trade_pair）；DMN = 被挡的信号去掉之后保留 vs 全部（W2 + C 那一折）。"""
    import combo_all_common as CA
    import combo_all_study as CS
    import sell_confirm as SCF
    D, SM = W["D"], W["SM"]
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold, trig in (("W", "E", trig_w), ("Jx", "J", trig_jx)):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        fa = (SM["J2"] if s == "Jx" else SM[s])["fa"]
        Xk = X[kc]
        for key, aid in (("sell13", "DMX"), ("tdst", "DMT")):
            rows, mism = [], 0
            for _, r in Xk.iterrows():
                t = r["ticker"]
                days = (trig.get(t) or {}).get(key, pd.DatetimeIndex([]))
                x = X3.trade_pair(t, fa[t], r["date"], W["p0"], bt, days, CS.END_BARS)
                if x is None:
                    continue
                mism += int(abs((x["x6"] - rt) - float(r["net"])) > 1e-6)
                rows.append(x)
            x6 = np.array([x["x6"] for x in rows]) - rt
            fx = np.array([x["fxx"] for x in rows]) - rt
            ch = np.array([x["changed"] for x in rows], bool)
            out[aid][s] = {"n": int(len(rows)), "mismatch_vs_panel": int(mism),
                           "dwin": float(((fx > 0).mean() - (x6 > 0).mean()) * 100) if len(rows) else None,
                           "dmean": float(fx.mean() - x6.mean()) if len(rows) else None, "changed": int(ch.sum()),
                           "changed_x6_mean": float(x6[ch].mean()) if ch.any() else None,
                           "changed_new_mean": float(fx[ch].mean()) if ch.any() else None}
        net = Xk["net"].to_numpy(float)
        g = gated(trig, Xk["ticker"].to_numpy(), Xk["date"].to_numpy())
        dl = CA.delta(net, ~g)
        gone = net[g]
        out["DMN"][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的持仓与信号） ─────────────────────────
def held_through(tr: pd.DataFrame, trig: dict, key: str, a: str, b: str | None) -> int:
    """B1 的日本个股交易里，持有期间（买入日 ≤ d < 卖出日）出现过触发日的笔数 = 这个做法会提前卖的。"""
    x = X3.jp_stock_trades(tr, a, b)
    n = 0
    for t, d0, d1 in zip(x["ticker"], pd.to_datetime(x["entry_date"]), pd.to_datetime(x["exit_date"])):
        v = (trig.get(t) or {}).get(key, pd.DatetimeIndex([]))
        n += int(((v >= d0) & (v < d1)).any()) if len(v) else 0
    return n


def scale(W: dict, trig: dict, trig_w: dict, trig_jx: dict, b1_trades: dict) -> dict:
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        lo, hi = pd.Timestamp(a), pd.Timestamp(b) if b else pd.Timestamp(L2.J_END)
        n13 = sum(int(((v["sell13"] >= lo) & (v["sell13"] < hi)).sum()) for v in trig[e].values())
        nt = sum(int(((v["tdst"] >= lo) & (v["tdst"] < hi)).sum()) for v in trig[e].values())
        X = A[e][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != e]), A[e])]
        tr = b1_trades[e]
        out[e] = {"stocks": len(trig[e]), "sell13": n13, "tdst_days": nt, "b1_trades": int(len(X3.jp_stock_trades(tr, a, b))),
                  "held_through_13": held_through(tr, trig[e], "sell13", a, b), "held_through_tdst": held_through(tr, trig[e], "tdst", a, b),
                  "signals": int(len(X)), "gated": int(gated(trig[e], X["ticker"].to_numpy(), X["date"].to_numpy()).sum())}
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    for s, fold, tg in (("W", "E", trig_w), ("Jx", "J", trig_jx)):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        out[s] = {"signals": int(len(X)), "gated": int(gated(tg, X["ticker"].to_numpy(), X["date"].to_numpy()).sum()),
                  "sell13": sum(len(v["sell13"]) for v in tg.values())}
    return out


# ───────────────────────── 只描述 D1〜D3 ─────────────────────────
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 4) if np.isfinite(f) else None


def fwd(close: pd.Series, h: int) -> pd.Series:
    """每一根 → 之后 h 根的涨跌（%，收盘到收盘）；最后 h 根 = NaN。"""
    c = close.astype(float)
    return (c.shift(-h) / c - 1) * 100


def event_stats(df: pd.DataFrame, hz) -> dict:
    """一个指数 / 一只票：{事件: {h: {n, ex（事件之后 − 平时，pp）, right（方向对的比例 %）, base_right}}}。事件 = sell13 / buy13 / sell9p / buy9p。"""
    from qbreak import demark as DM
    x = df[["Open", "High", "Low", "Close"]].astype(float).dropna()
    s = DM.sequential(x)
    ev = {"sell13": s["sell13"], "buy13": s["buy13"], "sell9p": s["sell9"] & s["sell_perfect"], "buy9p": s["buy9"] & s["buy_perfect"]}
    out = {}
    for k, m in ev.items():
        m = m.to_numpy(bool)
        sign = -1.0 if k.startswith("sell") else 1.0
        out[k] = {}
        for h in hz:
            f = fwd(x["Close"], h).to_numpy()
            ok = np.isfinite(f)
            base, hit = f[ok], f[ok & m]
            out[k][h] = {"n": int(len(hit)), "ex": _num(hit.mean() - base.mean()) if len(hit) else None,
                         "right": _num(((sign * hit) > 0).mean() * 100) if len(hit) else None,
                         "base_right": _num(((sign * base) > 0).mean() * 100) if len(base) else None}
    return out


def complete_bars(df: pd.DataFrame, sym: str, now=None) -> pd.DataFrame:
    """只留已经收盘的 K 线：^N225 = 东京那天收盘之后；其余指数 = 纽约那天收盘之后（纽约最后收盘；亚洲 / 欧洲当天已收盘的也等到纽约收盘，少一天无妨）。
    （登记前 --now 预检发现：盘中运行时 yfinance 会返回还没收盘的当日 K 线 → S&P500 的「卖 13」出在未收盘的那一根上。）"""
    from qbreak.trader import market_session_closed
    if df is None or not len(df):
        return df
    today, closed = market_session_closed("JP" if sym == "^N225" else "US", now)
    d = pd.DatetimeIndex(df.index).normalize()
    t = pd.Timestamp(today)
    return df[(d < t) | ((d == t) & closed)]


def index_frames() -> dict[str, pd.DataFrame]:
    """D1 的 26 个指数（K4 研究的 25 个市场 + ^NDX）日线 OHLC（1990 起、只留已收盘的；缓存 = qbreak.data 的指数缓存，不入库）。"""
    import k4_horizontal_study as K4

    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    syms = [v[0] for v in K4.MARKETS.values()] + ["^NDX"]
    got = load_universe(syms, DataConfig(years=37))
    return {t: complete_bars(df[df.index >= pd.Timestamp(IDX_FROM)], t) for t, df in got.items() if len(df)}


def pooled(per: dict, ev: str, h: int) -> dict:
    """各个指数的 ex 取平均、方向对的指数个数（ex 的符号：卖信号 < 0、买信号 > 0 = 方向对）。"""
    xs = [(t, v[ev][h]["ex"]) for t, v in per.items() if v[ev][h]["ex"] is not None and v[ev][h]["n"] >= 3]
    if not xs:
        return {"markets": 0, "mean_ex": None, "right_markets": 0, "events": 0}
    sign = -1.0 if ev.startswith("sell") else 1.0
    return {"markets": len(xs), "mean_ex": _num(np.mean([x for _, x in xs])), "right_markets": int(sum(1 for _, x in xs if sign * x > 0)),
            "events": int(sum(per[t][ev][h]["n"] for t, _ in xs))}


def describe_indices(frames: dict) -> dict:
    from qbreak import demark as DM
    day = {t: event_stats(df, HZ_D) for t, df in frames.items()}
    wk = {t: event_stats(DM.weekly(df), HZ_W) for t, df in frames.items()}
    return {"daily": {ev: {h: pooled(day, ev, h) for h in HZ_D} for ev in ("sell13", "buy13", "sell9p", "buy9p")},
            "weekly": {ev: {h: pooled(wk, ev, h) for h in HZ_W} for ev in ("sell13", "buy13", "sell9p", "buy9p")},
            "per_daily": day, "per_weekly": wk, "symbols": sorted(frames)}


def describe_stocks(W: dict) -> dict:
    """D2：Z / E / J 年代的日経225 成分，日线 sell13 / buy13 之后 10 / 20 个交易日 − 平时（逐笔平均，年代窗口里）。"""
    from qbreak import demark as DM
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        lo, hi = pd.Timestamp(a), pd.Timestamp(b) if b else pd.Timestamp(L2.J_END)
        acc = {k: {h: [] for h in (10, 20)} for k in ("sell13", "buy13", "all")}
        for t, df in W["SM"][e]["fa"].items():
            if not str(t).endswith(".T") or t in CORE:
                continue
            x = df[["Open", "High", "Low", "Close"]].astype(float).dropna()
            if len(x) < 60:
                continue
            s = DM.sequential(x)
            inw = (x.index >= lo) & (x.index < hi)
            for h in (10, 20):
                f = fwd(x["Close"], h).to_numpy()
                ok = np.isfinite(f) & inw
                acc["all"][h].append(f[ok])
                acc["sell13"][h].append(f[ok & s["sell13"].to_numpy(bool)])
                acc["buy13"][h].append(f[ok & s["buy13"].to_numpy(bool)])
        out[e] = {}
        for k in ("sell13", "buy13"):
            out[e][k] = {}
            for h in (10, 20):
                v = np.concatenate(acc[k][h]) if acc[k][h] else np.array([])
                base = np.concatenate(acc["all"][h]) if acc["all"][h] else np.array([])
                sign = -1.0 if k == "sell13" else 1.0
                out[e][k][h] = {"n": int(len(v)), "ex": _num(v.mean() - base.mean()) if len(v) else None,
                                "right": _num(((sign * v) > 0).mean() * 100) if len(v) else None,
                                "base_right": _num(((sign * base) > 0).mean() * 100) if len(base) else None}
    return out


def now_state(frames: dict) -> dict:
    """D3：数据最后一天的 TD Sequential 状态（日线 / 周线）。"""
    from qbreak import demark as DM
    out = {}
    for sym, name in NOW_SYMS.items():
        df = frames.get(sym)
        if df is None or not len(df):
            continue
        row = {"name": name, "last": str(df.index[-1].date()), "close": _num(df["Close"].iloc[-1])}
        for tf, x in (("daily", df), ("weekly", DM.weekly(df))):
            s = DM.sequential(x)
            r = s.iloc[-1]
            l13s = s.index[s["sell13"].to_numpy(bool)]
            l13b = s.index[s["buy13"].to_numpy(bool)]
            row[tf] = {"bar": str(s.index[-1].date()), "sell_setup": int(r["sell_setup"]), "buy_setup": int(r["buy_setup"]), "sell_cd": int(r["sell_cd"]),
                       "buy_cd": int(r["buy_cd"]), "last_sell13": str(l13s[-1].date()) if len(l13s) else None,
                       "last_buy13": str(l13b[-1].date()) if len(l13b) else None,
                       "sell_setup_tdst": _num(r["sell_setup_tdst"]), "buy_setup_tdst": _num(r["buy_setup_tdst"])}
        out[sym] = row
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r07_demark.py", "qbreak/demark.py",
                                 "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop3.py", "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def inputs(W: dict) -> tuple[dict, dict, dict]:
    """各年代的触发日（引擎同一份日线）+ W / Jx 的。"""
    SM = W["SM"]
    trig = {e: all_triggers(SM[e]["fa"], L2_era_names(W, e)) for e in L2.ERAS}
    return trig, all_triggers(SM["W"]["fa"]), all_triggers(SM["J2"]["fa"])


def L2_era_names(W: dict, e: str) -> list[str]:
    ctx = W["ctx"][e]
    return [str(ctx["names"][j]) for j in ctx["cols"]]


def runs(W: dict, e: str, trig: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {"DMX": {"exit_tick": exit_tick_of(trig[e], "sell13")}, "DMT": {"exit_tick": exit_tick_of(trig[e], "tdst")},
            "DMN": {"em_tick": em_tick_of(trig[e], days)}}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    trig, trig_w, trig_jx = inputs(W)
    reg = R2.load_state().get("baseline") or {}
    base, cand, trades, b1_trades, cnt = {}, {k: {} for k in IDS}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        a, b = W["ctx"][e]["windows"][e]
        for k, over in runs(W, e, trig).items():
            rc = L2.run(W, e, **over)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
            if k in ("DMX", "DMT"):
                cnt.setdefault(k, {})[e] = X3.fxx_exits(X3.last_trades(), a, b)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, trig_w, trig_jx)
    s1 = {k: R2.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    frames = index_frames()
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades, "tick_exits": cnt,
           "scale": scale(W, trig, trig_w, trig_jx, b1_trades), "d1": describe_indices(frames), "d2": describe_stocks(W),
           "d3": now_state(frames), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def d_lines(res: dict) -> list[str]:
    L = ["", "## 只描述（不参与判定）：Perl 的 TD Sequential 信号本身准不准", ""]
    name = {"sell13": "卖 countdown 13", "buy13": "买 countdown 13", "sell9p": "完美的卖 setup 9", "buy9p": "完美的买 setup 9"}
    for tf, hz, unit in (("daily", HZ_D, "个交易日"), ("weekly", HZ_W, "周")):
        L.append(f"- D1 {len(res['d1']['symbols'])} 个指数（{'日线' if tf == 'daily' else '周线'}，1990 起）：信号之后 − 平时（各指数取平均，pp；方向对的指数个数）")
        for ev in ("sell13", "buy13", "sell9p", "buy9p"):
            cells = [f"{h}{unit} {_f(res['d1'][tf][ev][h]['mean_ex'], '{:+.2f}')}（{res['d1'][tf][ev][h]['right_markets']} / "
                     f"{res['d1'][tf][ev][h]['markets']}；{res['d1'][tf][ev][h]['events']} 次）" for h in hz]
            L.append(f"  - {name[ev]}：" + "、".join(cells))
    for e in L2.ERAS:
        d = res["d2"][e]
        L.append(f"- D2 {e} 日経225 成分（日线）：" + "；".join(
            f"{name[k]} 之后 {h} 天 {_f(d[k][h]['ex'], '{:+.2f}')} pp（{d[k][h]['n']} 次；方向对 {_f(d[k][h]['right'], '{:.1f}')}% vs 平时 "
            f"{_f(d[k][h]['base_right'], '{:.1f}')}%）" for k in ("sell13", "buy13") for h in (10, 20)))
    for sym, r in res["d3"].items():
        cells = []
        for tf in ("daily", "weekly"):
            x = r[tf]
            tag = "日线" if tf == "daily" else f"周线（最后一根 = 到 {x['bar']} 的这一周）"
            cells.append(f"{tag} 卖 setup {x['sell_setup']} / 买 setup {x['buy_setup']}、卖 countdown {x['sell_cd']} / "
                         f"买 countdown {x['buy_cd']}；最近的卖 13 {x['last_sell13'] or '—'}、买 13 {x['last_buy13'] or '—'}；"
                         f"卖 setup 的 TDST {_f(x['sell_setup_tdst'], '{:,.0f}')}、买 setup 的 TDST {_f(x['buy_setup_tdst'], '{:,.0f}')}")
        L.append(f"- D3 现在 {r['name']}（{r['last']} 收盘 {_f(r['close'], '{:,.0f}')}）：" + "；".join(cells))
    return L


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"DMX": "持有的日本个股出现日线卖 countdown 13 → 第二天开盘卖", "DMT": "收盘跌破最近一次卖 setup 的 TDST → 第二天开盘卖",
            "DMN": "信号日与之前 4 天出现过日线卖 countdown 13 → 不开新仓"}
    L = [f"# 第三个研究循环第 7 轮：Jason Perl（DeMark 指标）的观点 DMX / DMT / DMN（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r07_demark.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | DMX（Calmar 差） | DMT（Calmar 差） | DMN（Calmar 差） | 个股笔数 B1 → DMX / DMT / DMN |",
          "|---|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS)
            + f" | {t['B1']} → {t['DMX']} / {t['DMT']} / {t['DMN']} |")
    sc = res["scale"]
    L += ["", "规模与被改变的（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：{x['stocks']} 只票的日线卖 13 共 {x['sell13']} 次、收盘在卖 setup TDST 之下 {x['tdst_days']} 天；B1 的日本个股 {x['b1_trades']} 笔里"
                 f"持有期间碰到卖 13 的 {x['held_through_13']} 笔、碰到 TDST 跌破的 {x['held_through_tdst']} 笔；B1 会买的信号 {x['signals']} 个里 DMN 挡 {x['gated']} 个；"
                 f"账户里 DMX / DMT 的离场 {res['tick_exits'].get('DMX', {}).get(e, '—')} / {res['tick_exits'].get('DMT', {}).get(e, '—')} 笔")
    for k in ("DMX", "DMT"):
        for s in ("W", "Jx"):
            o = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：逐笔 {o['n']} 笔（与面板不一致 {o['mismatch_vs_panel']}）；被改变 {o['changed']} 笔 X6 {_f(o['changed_x6_mean'], '{:+.2f}')}% → "
                     f"{_f(o['changed_new_mean'], '{:+.2f}')}%；胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    for s in ("W", "Jx"):
        o = res["other_stocks"]["DMN"][s]
        L.append(f"- DMN {s}：B1 会买的信号 {o['n']} 个，挡掉 {o['gone_n']} 个（胜率 {_f(o['gone_win'], '{:.1f}')}%、每笔 {_f(o['gone_mean'], '{:+.2f}')}%）；"
                 f"保留 {o['kept']} 个 → 胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    L += d_lines(res)
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。数据仅对本次取数时点有效。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数 B1 的持仓与信号碰到触发日的个数（跑 B1、不跑候选、不看收益）。"""
    W = L2.load()
    trig, trig_w, trig_jx = inputs(W)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps(scale(W, trig, trig_w, trig_jx, b1), ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 触发日全空 → 三个做法的账户都与 B1 逐项相同；② 触发日个数 > 0（不跑候选本身、不看收益）。"""
    W = L2.load()
    trig, _, _ = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {t: {"sell13": pd.DatetimeIndex([]), "tdst": pd.DatetimeIndex([]), "gate": pd.DatetimeIndex([])} for t in trig["J"]}
    same = {k: all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys) for k, over in runs(W, "J", {"J": empty}).items()}
    n = {"sell13": sum(len(v["sell13"]) for v in trig["J"].values()), "tdst": sum(len(v["tdst"]) for v in trig["J"].values()),
         "em_tick": len(em_tick_of(trig["J"], W["ctx"]["J"]["days"]))}
    print(json.dumps({"empty_same_as_b1": same, "counts_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def now_only() -> int:
    """D3 现在的状态（只有指标的状态，不看收益）。"""
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    got = load_universe(list(NOW_SYMS), DataConfig(years=37))
    print(json.dumps(now_state({t: complete_bars(df[df.index >= pd.Timestamp(IDX_FROM)], t) for t, df in got.items()}), ensure_ascii=False,
                     indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 7 轮：DMX / DMT / DMN（Jason Perl 的 DeMark 指标）")
    ap.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（J；不看候选的收益）")
    ap.add_argument("--now", action="store_true", help="只算 D3 现在的状态")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    if a.now:
        return now_only()
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
