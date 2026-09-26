"""adaptive_study.py — 跟着时代调整：每年 / 每月按最近的表现重选买点阈值、按行业近况调整，和固定参数比
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「随着科技的发展行业之间的倾斜也都不一样，随着每年、每月要随时调整模型的阈值才会跟随时代的发展取得当前最佳筛选出来的股票，
做一个这样的研究放到当前的股票筛选研究方法里面」。

一、问题：突破买点的阈值（箱体天数 range_n、箱体振幅 range_x_pct、MACD 快 / 慢线）和行业偏好现在是固定的。
  按最近几年的表现定期重选，能不能跟上时代、比固定的好？还是只是在追过去的运气（过拟合，overfitting）？
二、候选（S0C2 其余设定全部不变：¥100 万 × 4 个名额、立花、1655 牛熊择时、宏观 / 板块倍数、出场规则；个股一手按复权价 = 之前各研究的现行口径）
  参数网格 = qbreak/optimize.py DEFAULT_GRID：range_n 40 / 60 / 90 × range_x_pct 10 / 15 / 20 × macd_fast 8 / 12 × macd_slow 21 / 26
  （signal 9）= 36 组，现行 60 / 15 / 12 / 26 在网格里。每组各跑一遍完整的 S0C2（2006-10〜）→ 每组的日权益曲线（重选时的「成绩单」）。
  A1 每年重选：每年第一个交易日，用之前 5 年各组的 Calmar（年化 ÷ |最大回撤|）选最高的一组；
  A2 每月重选：每月第一个交易日，用之前 3 年的 Calmar 选；
  A3 每年重选（求稳）：之前 5 年逐年的 Calmar 名次取平均，平均名次最好的一组（少追一次性的好运气）；
    同分 → 现行。A1〜A3 是「真实切换」的回测：引擎只从指标里读买点（entry）和 MACD 死叉（dead_cross）两列会随阈值变，
    每段把这两列换成那段选中的组（选择日以前 = 现行），其余（价格、ATR、放量阴线、出场参数）不变；持仓跨段自然延续，手续费照算。
  A4 行业随时代跳过（每月）：每月第一个交易日，用之前 36 个月信号、且在这之前已平仓的突破交易（日経225 + 扩大池 927 只，各自独立的交易）
    按东证 33 业种算每笔期望（至少 10 笔的业种参加排名），最低的 1/3 业种这个月的买点不做；
  A5 行业随时代排序（每月）：同样的业种期望只用来排同一天候选的先后（名额不够时先买期望高的业种；没有排名的业种 = 当月中位数），不跳过。
三、比较（事先写定）
  对照 = 现行固定参数（同一个回测）；样本外 = 2012-01〜（A1 / A3 第一次能用满 5 年的时点）；两半 = 2012-01〜2018-12 / 2019-01〜。
  另报（只作参照，实际做不到）：事后看样本外 Calmar 最高的固定一组。
  描述：① 阈值的「持续性」：之前 5 年的 Calmar 名次与下一年名次的 Spearman 相关，逐年（2012〜2025）平均
       （接近 0 = 过去最好的下一年不一定好，重选就跟不上）；② 业种期望的持续性：之前 36 个月与下一年的业种每笔期望的 Spearman 相关（2010〜2025）；
       ③ A1〜A3 选中的组与换组次数；④ A4 被跳过的买点在样本外两半的胜率 / 每笔期望（全部交易口径）。
四、判定（事先写定）
  候选「更好」= 样本外 Calmar ≥ 现行 + 0.05，且两半 Calmar 都不低于现行，且样本外年化不低于现行，且样本外最大回撤不比现行深 2 pp 以上；
  有多个 → 样本外 Calmar 最高的。通过的只是提议：先进前向记录（另行登记），模拟盘改不改由用户确认；没有通过 → 维持固定参数。
五、局限：36 组 × 20 年只有一条历史路径，「持续性」本身也有噪音；重选用的是每组完整回测里那一段的成绩（实际操作时会从零重跑那几年，
  差别只在期初持仓）；股票池是现在的成分（幸存者偏差约 0.05〜0.10 pp / 年，var/out/pit_backtest.md）。
登记前做过的检查：tests/test_adaptive_study.py（选择只用选择日以前的权益、同分选现行、逐年名次、真实切换只换那两列且只换那一段、
业种期望只用之前已平仓的交易、跳过 / 排序、判定）。
输出：var/out/adaptive_study.md / .json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capital_study as CS                                                   # noqa: E402
import earnings_study as ES                                                  # noqa: E402
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak.optimize import DEFAULT_GRID                                     # noqa: E402

W20, OOS0, MID = "2006-10-01", "2012-01-01", "2019-01-01"
PLANS = {"A1": ("Y", 5, "calmar"), "A2": ("M", 3, "calmar"), "A3": ("Y", 5, "rank")}
CANDS = ("A1", "A2", "A3", "A4", "A5")
NAMES = {"A1": "A1 每年重选阈值（之前 5 年 Calmar 最高）", "A2": "A2 每月重选阈值（之前 3 年 Calmar 最高）",
         "A3": "A3 每年重选阈值（之前 5 年逐年名次平均）", "A4": "A4 每月跳过近 36 个月最差 1/3 业种",
         "A5": "A5 每月按业种近 36 个月期望排序"}
SEC_MONTHS, SEC_MIN_N = 36, 10
CALMAR_UP, DD_TOL = 0.05, 2.0
SIG_COLS = ("entry", "dead_cross")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def key_of(p) -> str:
    return f"{p.range_n}/{p.range_x_pct:g}/{p.macd_fast}/{p.macd_slow}"


def combos(base) -> list[tuple[str, object]]:
    """网格的全部合法组合；现行排第一（同分时选现行），其余按网格顺序。"""
    out = []
    for vals in product(*DEFAULT_GRID.values()):
        try:
            p = replace(base, **dict(zip(DEFAULT_GRID, vals))).validate()
        except Exception:                                                     # noqa: BLE001  非法组合（快线 ≥ 慢线）跳过
            continue
        out.append((key_of(p), p))
    cur = key_of(base)
    if cur not in {k for k, _ in out}:
        raise ValueError(f"现行阈值 {cur} 不在网格里")
    return sorted(out, key=lambda z: z[0] != cur)


def period_starts(days, freq: str, first) -> list[pd.Timestamp]:
    """每年（Y）/ 每月（M）第一个交易日，且 ≥ first。"""
    d = pd.DatetimeIndex(days)
    key = np.asarray(d.year) * (1 if freq == "Y" else 12) + (0 if freq == "Y" else np.asarray(d.month))
    m = np.r_[True, key[1:] != key[:-1]]
    return [x for x in d[m] if x >= pd.Timestamp(first)]


def select(E: pd.DataFrame, starts, years: int, how: str) -> dict[pd.Timestamp, str]:
    """每个选择日 s：只看 s 以前（< s）的权益。calmar = 之前 years 年 Calmar 最高；rank = 之前 years 个一年段的 Calmar 名次平均最好。
    同分 → 列顺序靠前的（现行在第一列）。"""
    out = {}
    for s in starts:
        if how == "calmar":
            v = {c: CS.seg_stats(E[c], s - pd.DateOffset(years=years), s)["calmar"] for c in E.columns}
            out[s] = max(E.columns, key=lambda c: -np.inf if v[c] is None else v[c])
        else:
            rk = []
            for j in range(years):
                a, b = s - pd.DateOffset(years=j + 1), s - pd.DateOffset(years=j)
                v = pd.Series({c: CS.seg_stats(E[c], a, b)["calmar"] for c in E.columns}, dtype=float)
                rk.append(v.rank(ascending=False, method="min", na_option="bottom"))
            out[s] = pd.concat(rk, axis=1).mean(axis=1).idxmin()
    return out


def switched(base_ind: dict, sig: dict, picks: dict, base_key: str) -> dict:
    """真实切换：每只票的 entry / dead_cross 在每段换成那段选中的组（sig[组][票] = 这两列的数组，与指标表同一索引）；
    第一个选择日以前 = 现行；其余列不变。"""
    starts = sorted(picks)
    out = {}
    for t, df in base_ind.items():
        d = df.copy()
        ix = d.index
        for j, s in enumerate(starts):
            c = picks[s]
            if c == base_key:
                continue
            m = ix >= s
            if j + 1 < len(starts):
                m &= ix < starts[j + 1]
            for k, col in enumerate(SIG_COLS):
                d.loc[m, col] = sig[c][t][k][m]
        out[t] = d
    return out


def sector_tables(T: pd.DataFrame, sec: dict, starts, months: int = SEC_MONTHS, min_n: int = SEC_MIN_N) -> dict:
    """每个月初 s：信号日在之前 months 个月内、且平仓日 < s 的交易，按业种算每笔期望（%）；不到 min_n 笔的业种不排。"""
    T = T.assign(sector=T["ticker"].map(sec)).dropna(subset=["sector"])
    out = {}
    for s in starts:
        w = T[(T["sig_date"] >= s - pd.DateOffset(months=months)) & (T["exit_date"] < s)]
        g = w.groupby("sector")["net"].agg(["mean", "size"])
        out[s] = {k: float(v) for k, v in g.loc[g["size"] >= min_n, "mean"].items()}
    return out


def cold(tab: dict) -> set:
    """每笔期望最低的 1/3（向下取整）业种。"""
    return set(sorted(tab, key=lambda x: (tab[x], x))[:len(tab) // 3])


def _month_pos(starts: list, dates) -> np.ndarray:
    return pd.DatetimeIndex(starts).searchsorted(pd.DatetimeIndex(dates), side="right") - 1


def skip_cold(ind: dict, sec: dict, tabs: dict) -> tuple[dict, int]:
    """A4：买点所在月份的「冷」业种 → 不做。返回（新指标表，跳过的买点数）。"""
    starts = sorted(tabs)
    cs = [cold(tabs[s]) for s in starts]
    out, n = dict(ind), 0
    for t, df in ind.items():
        sc = sec.get(t)
        if sc is None:
            continue
        e = df["entry"].astype(bool).to_numpy()
        pos = _month_pos(starts, df.index)
        drop = e & np.array([p >= 0 and sc in cs[p] for p in pos])
        if drop.any():
            d = df.copy()
            d.loc[drop, "entry"] = False
            out[t] = d
            n += int(drop.sum())
    return out, n


def sector_prio(ind: dict, sec: dict, tabs: dict) -> dict:
    """A5：(票, 信号日) → 那个月该业种的每笔期望；业种没有排名 → 当月各业种的中位数；那个月还没有任何排名 → 不给分。"""
    starts = sorted(tabs)
    out = {}
    for t, df in ind.items():
        e = df.index[df["entry"].astype(bool).to_numpy()]
        for d, p in zip(e, _month_pos(starts, e)):
            if p < 0 or not tabs[starts[p]]:
                continue
            tab = tabs[starts[p]]
            out[(t, d)] = tab.get(sec.get(t), float(np.median(list(tab.values()))))
    return out


def spearman(a: pd.Series, b: pd.Series) -> float | None:
    x = pd.concat([a, b], axis=1).dropna()
    if len(x) < 5:
        return None
    return round(float(np.corrcoef(x.iloc[:, 0].rank(), x.iloc[:, 1].rank())[0, 1]), 3)


def _summ(vals: dict) -> dict:
    v = [x for x in vals.values() if x is not None]
    return {"per_year": vals, "mean": round(float(np.mean(v)), 3) if v else None, "pos": int(sum(x > 0 for x in v)), "n": len(v)}


def param_persistence(E: pd.DataFrame, years=range(2012, 2026), look: int = 5) -> dict:
    vals = {}
    for y in years:
        s, e = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
        a = pd.Series({c: CS.seg_stats(E[c], s - pd.DateOffset(years=look), s)["calmar"] for c in E.columns}, dtype=float)
        b = pd.Series({c: CS.seg_stats(E[c], s, e)["calmar"] for c in E.columns}, dtype=float)
        vals[y] = spearman(a, b)
    return _summ(vals)


def sector_persistence(T: pd.DataFrame, sec: dict, years=range(2010, 2026)) -> dict:
    T = T.assign(sector=T["ticker"].map(sec)).dropna(subset=["sector"])
    vals = {}
    for y in years:
        s, e = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
        past = T[(T["sig_date"] >= s - pd.DateOffset(months=SEC_MONTHS)) & (T["exit_date"] < s)].groupby("sector")["net"].agg(["mean", "size"])
        fut = T[(T["sig_date"] >= s) & (T["sig_date"] < e)].groupby("sector")["net"].agg(["mean", "size"])
        vals[y] = spearman(past.loc[past["size"] >= SEC_MIN_N, "mean"], fut.loc[fut["size"] >= SEC_MIN_N, "mean"])
    return _summ(vals)


def summarize(eq: pd.Series, trades: int | None = None, win: float | None = None) -> dict:
    return {"oos": CS.seg_stats(eq, OOS0), "h1": CS.seg_stats(eq, OOS0, MID), "h2": CS.seg_stats(eq, MID), "w20": CS.seg_stats(eq),
            "trades": trades, "win": win}


def decide(R: dict, base: str = "BASE") -> dict:
    """第四节：样本外 Calmar ≥ 现行 + 0.05、两半都不低于现行、样本外年化不低于现行、样本外最大回撤不比现行深 2 pp 以上。"""
    b = R[base]
    per, ok = {}, []
    for k in CANDS:
        if k not in R:
            continue
        r, fails = R[k], []
        m, bm = r["oos"]["calmar"], b["oos"]["calmar"]
        if m is None or bm is None or m < bm + CALMAR_UP:
            fails.append(f"样本外 Calmar {m} < 现行 {bm} + {CALMAR_UP}")
        for h in ("h1", "h2"):
            v, bv = r[h]["calmar"], b[h]["calmar"]
            if v is None or bv is None or v < bv:
                fails.append(f"{'前半' if h == 'h1' else '后半'} Calmar {v} < 现行 {bv}")
        v, bv = r["oos"]["cagr"], b["oos"]["cagr"]
        if v is None or bv is None or v < bv:
            fails.append(f"样本外年化 {v}% < 现行 {bv}%")
        v, bv = r["oos"]["dd"], b["oos"]["dd"]
        if v is None or bv is None or v < bv - DD_TOL:
            fails.append(f"样本外最大回撤 {v}% 比现行 {bv}% 深 {DD_TOL} pp 以上")
        per[k] = fails
        if not fails:
            ok.append((m, k))
    return {"per": per, "best": max(ok)[1] if ok else None}


def make_runner(data_n: dict):
    """signal_study.s0c2_builder 同一套设定（行情、1655、宏观、牛熊、手续费、¥100 万 × 4 名额），返回整条权益曲线；可给排序分（A5）。"""
    from bullbear_study import SYM, load
    from unified_study import spx_jpy_on_jp_days
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.config import DataConfig
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    from qbreak.fees import etf_cost
    from qbreak.macro import build_entry_mult, features_frame, load_macro_series
    from qbreak.regime import quant_regime_series
    from qbreak.trader import load_params
    from qbreak.unified import exec_configs
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    broker = (sim.get("unified") or {}).get("broker", "tachibana")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    core = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    names = list(data_n)
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = exec_configs(("JP",), {"broker": broker})
    cc = {"1655.T": etf_cost(broker, "1655.T", "JP")}
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    closes = pd.DataFrame({t: data_n[t]["Close"] for t in names})
    cfg = CS.cfg_for(1_000_000, 4)
    us = load_params(market="US")
    cache: dict = {}

    def run(ind: dict, p, prio: dict | None = None, start: str = W20) -> dict:
        if "em" not in cache:                                                 # 入场倍数只取决于日期与股票，算一次
            g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
            M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")),
                                    use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
            M = M * quant_regime_series(idx["JP"]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
            cache["em"] = {"JP": pd.DataFrame(M, index=g, columns=names)}
        Z._PrioEngine.PRIO = prio
        try:
            r = Z._PrioEngine({**ind, "1655.T": core}, cfg, {"JP": p, "US": us}, ex, cc, fx=fxdf[["Open", "Close"]],
                              entry_mult=cache["em"], bear=bear).run(start=start)
        finally:
            Z._PrioEngine.PRIO = None
        tr = r.trades[(r.trades["reason"] != "end") & (r.trades["ticker"] != "1655.T")]
        return {"equity": r.equity, "trades": int(len(tr)),
                "win": round(float((tr["pnl"] > 0).mean()) * 100, 1) if len(tr) else None}
    return run


def main() -> int:
    from qbreak import wide_universe as W
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/adaptive_study.py", "scripts/capital_study.py", "scripts/earnings_study.py",
                            "scripts/score_study.py", "scripts/signal_study.py", "qbreak/optimize.py", "qbreak/unified.py", "qbreak/engine.py",
                            "qbreak/strategy.py", "qbreak/macro.py", "var/industry_s33.json", "var/universe_wide.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    run = make_runner(data_n)
    C = combos(p)
    base_key = key_of(p)
    E, sig, per, base_ind = {}, {}, {}, None
    for key, pc in C:
        ind = dict(IndicatorCache(data_n).all(pc))
        r = run(ind, p)                                                       # 出场参数用现行（网格只改买点阈值）
        E[key] = r["equity"]
        sig[key] = {t: tuple(ind[t][c].astype(bool).to_numpy() for c in SIG_COLS) for t in ind}
        per[key] = summarize(r["equity"], r["trades"], r["win"])
        if key == base_key:
            base_ind = ind
        print(key, per[key]["oos"], f"{time.time() - t0:.0f}s", flush=True)
    E = pd.DataFrame(E)[[k for k, _ in C]]
    R = {"BASE": per[base_key]}
    picks = {}
    for k, (freq, yrs, how) in PLANS.items():
        starts = period_starts(E.index, freq, pd.Timestamp(W20) + pd.DateOffset(years=yrs))
        picks[k] = select(E, starts, yrs, how)
        r = run(switched(base_ind, sig, picks[k], base_key), p)
        R[k] = summarize(r["equity"], r["trades"], r["win"])
        print(k, R[k]["oos"], f"{time.time() - t0:.0f}s", flush=True)

    # 行业：日経225 + 扩大池 927 只各自独立的交易 → 每月的业种期望
    doc = W.load()
    ind_x = dict(IndicatorCache(load_universe(W.tickers(doc), d21)).all(p))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    T = ES.outcomes({**base_ind, **ind_x}, p, bt)
    sec = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    tabs = sector_tables(T, sec, period_starts(E.index, "M", W20))
    ind4, n_skip = skip_cold(base_ind, sec, tabs)
    r = run(ind4, p)
    R["A4"] = {**summarize(r["equity"], r["trades"], r["win"]), "skipped_signals": n_skip}
    r = run(base_ind, p, prio=sector_prio(base_ind, sec, tabs))
    R["A5"] = summarize(r["equity"], r["trades"], r["win"])
    print("A4 / A5", R["A4"]["oos"], R["A5"]["oos"], f"{time.time() - t0:.0f}s", flush=True)
    # 描述 ④：A4 被跳过的买点（全部交易口径，样本外两半）
    starts = sorted(tabs)
    cs = [cold(tabs[s]) for s in starts]
    pos = _month_pos(starts, T["sig_date"])
    T["cold"] = [q >= 0 and sec.get(t) in cs[q] for t, q in zip(T["ticker"], pos)]
    halves = {"h1": (OOS0, "2018-12-31"), "h2": (MID, None)}
    skipped = {h: {"cold": SS.stats(T[T["cold"] & (T["sig_date"] >= pd.Timestamp(w[0])) & (T["sig_date"] <= pd.Timestamp(w[1] or "2100-01-01"))]),
                   "all": SS.stats(T[(T["sig_date"] >= pd.Timestamp(w[0])) & (T["sig_date"] <= pd.Timestamp(w[1] or "2100-01-01"))])}
               for h, w in halves.items()}
    V = decide(R)
    hind = max(per, key=lambda c: -9 if per[c]["oos"]["calmar"] is None else per[c]["oos"]["calmar"])
    pers, spers = param_persistence(E), sector_persistence(T, sec)
    report(R, V, per, picks, hind, base_key, pers, spers, skipped, len(C), len(ind_x), head, t0)
    return 0


def report(R, V, per, picks, hind, base_key, pers, spers, skipped, n_combo, n_x, head, t0) -> None:
    fa = lambda v, f="{:.2f}": "—" if v is None else f.format(v)                     # noqa: E731
    row = lambda name, r: (f"| {name} | {fa(r['oos']['cagr'])}% / {fa(r['oos']['dd'])}% / {fa(r['oos']['calmar'], '{:.3f}')} | "  # noqa: E731
                           f"{fa(r['h1']['calmar'], '{:.3f}')} / {fa(r['h2']['calmar'], '{:.3f}')} | {fa(r['w20']['cagr'])}% / "
                           f"{fa(r['w20']['dd'])}% / {fa(r['w20']['calmar'], '{:.3f}')} | {r.get('trades', '—')} 笔 | {fa(r.get('win'), '{:.1f}')}% |")
    say(f"# 跟着时代调整：每年 / 每月重选阈值、按行业近况调整（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say(f"阈值网格 {n_combo} 组（现行 {base_key}）；行业期望用日経225 + 扩大池 {n_x} 只的独立交易；规则见 scripts/adaptive_study.py 开头（先提交后运行）。")
    say("\n| 方案 | 样本外 2012〜 年化 / 最大回撤 / Calmar | 前半 / 后半 Calmar | 20 年 年化 / 最大回撤 / Calmar | 个股笔数（20 年） | 个股胜率 |")
    say("|---|---|---|---|---|---|")
    say(row(f"现行固定 {base_key}", R["BASE"]))
    for k in CANDS:
        say(row(NAMES[k], R[k]))
    say(row(f"（参照，事后才知道）样本外最好的固定组 {hind}", per[hind]))
    say("\n## 判定（样本外 Calmar ≥ 现行 + 0.05、两半都不低于现行、样本外年化不低于现行、样本外回撤不深 2 pp 以上）")
    for k, fails in V["per"].items():
        say(f"- {NAMES[k]}：{'通过' if not fails else '不通过（' + '；'.join(fails) + '）'}")
    say(f"\n**提议：{NAMES[V['best']]}**（先进前向记录，要用户确认才改模拟盘）" if V["best"]
        else "\n**没有方案明显好于固定阈值 → 维持现行（固定阈值、不按行业近况调整）。**")
    say("\n## 为什么（描述）")
    say(f"- 阈值的持续性：之前 5 年 Calmar 名次 vs 下一年名次的 Spearman 相关，{pers['n']} 年平均 {fa(pers['mean'], '{:+.3f}')}"
        f"（为正的 {pers['pos']} 年）→ 越接近 0，「过去最好的阈值」越不代表下一年也好。")
    say(f"- 业种的持续性：之前 36 个月 vs 下一年的业种每笔期望 Spearman 相关，{spers['n']} 年平均 {fa(spers['mean'], '{:+.3f}')}（为正的 {spers['pos']} 年）。")
    for k in ("A1", "A3"):
        pk = picks[k]
        say(f"- {NAMES[k]} 每年选中：" + "、".join(f"{s.year} {c}" for s, c in sorted(pk.items())))
    pk = picks["A2"]
    seq = [pk[s] for s in sorted(pk)]
    sw = sum(a != b for a, b in zip(seq, seq[1:]))
    top = pd.Series(seq).value_counts().head(3)
    say(f"- {NAMES['A2']}：{len(seq)} 个月里换组 {sw} 次；用得最多的 " + "、".join(f"{c}（{n} 个月）" for c, n in top.items()))
    for h, lab in (("h1", "前半 2012〜2018"), ("h2", "后半 2019〜")):
        c, a = skipped[h]["cold"], skipped[h]["all"]
        say(f"- A4 {lab}：被跳过的买点 {c.get('n', 0)} 笔，胜率 {c.get('win', '—')}% / 每笔 {c.get('exp', '—')}%"
            f"（全部 {a.get('n', 0)} 笔：{a.get('win', '—')}% / {a.get('exp', '—')}%）")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "adaptive_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "results": R, "decision": V, "per_combo": per, "hindsight": hind,
                                              "picks": {k: {str(s.date()): c for s, c in v.items()} for k, v in picks.items()},
                                              "persistence": {"param": pers, "sector": spers}, "a4_skipped": skipped},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
