"""leap_confirm.py — 「质的飞跃」各轮确认运行的共用部分（2026-09-27；判定规则在 scripts/leap_common.py，登记 543a447）。

三个窗口的数据与组合回测（S0C2 = var/sim.json 同一套设定，candle_portfolio.make_runner）：
  Z 2001-01〜2006-09：yfinance 27 年（今天的日経225），2000 年热身；宏观序列与 1655 用 27 年（1655 上市前 = S&P500 × USD/JPY 合成）
  E 2006-10〜2016-09：同一份 yfinance 27 年行情（与 Z 同一口径）
  J 2017-01〜2026-09：J-Quants 今天的日経225、真实一手（candle_data，与以前各研究同一口径）
每个窗口给出：现行（W2）、只有核心（个股一个都不买）、候选、随机对照；逐笔 = 组合里的个股交易（扣手续费的净收益 ÷ 买入金额）。
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap_common as LC                                                     # noqa: E402

Z_DAYS = ("2000-01-04", "2007-06-29")
E_DAYS = ("2005-09-01", "2016-12-30")


def _windows(era: str) -> dict:
    a, b = LC.WINDOWS[era]
    (a1, b1), (a2, b2) = LC.HALVES[era]
    return {era: (a, b), f"{era}1": (a1, b1), f"{era}2": (a2, b2)}


def yf_panel(names: list[str], lo: str, hi: str) -> tuple[dict, pd.DatetimeIndex, list[str]]:
    import leap_data as LD
    from qbreak import candles as K
    data = LD.ohlcv(names)
    nm = [t for t in names if t in data and len(data[t])]
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in nm])))
    days = days[(days >= pd.Timestamp(lo)) & (days <= pd.Timestamp(hi))]
    P = K.panel(data, days, nm)
    keep = [j for j in range(len(nm)) if np.isfinite(P["C"][:, j]).sum() >= 80]
    return {k: v[:, keep] for k, v in P.items()}, days, [nm[j] for j in keep]


def context(era: str, names: list[str] | None = None) -> dict:
    """{P, days, names, cols, ratio, start, end, windows, years, delist}。names 缺省 = 今天的日経225（Z / E）。"""
    import pit_retrain_study as PRS
    from qbreak.config import universe
    if era in ("Z", "E"):
        lo, hi = Z_DAYS if era == "Z" else E_DAYS
        P, days, nm = yf_panel(names or list(universe("JP", "broad")), lo, hi)
        a, b = LC.WINDOWS[era]
        return {"era": era, "P": P, "days": days, "names": nm, "cols": list(range(len(nm))), "ratio": {}, "start": a, "end": b,
                "windows": _windows(era), "years": 27, "delist": {}}
    import candle_data as CD
    D = CD.load()
    P, days, nm = D["P"], D["days"], D["names"]
    last = {nm[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(nm)) if np.isfinite(P["C"][:, j]).any()}
    delist = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    cols = [j for j in range(len(nm)) if D["mem"]["U0"][:, j].any()]
    ratio = {nm[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
    a, b = LC.WINDOWS["J"]
    return {"era": "J", "P": P, "days": days, "names": nm, "cols": cols, "ratio": ratio, "start": a, "end": b,
            "windows": _windows("J"), "years": 21, "delist": delist, "D": D}


def frames(ctx: dict, p) -> dict[str, pd.DataFrame]:
    import candle_study as CS_
    return CS_.frames_from(ctx["P"], ctx["days"], ctx["names"], ctx["cols"], p, {})


def runner(ctx: dict, fr: dict):
    import candle_portfolio as CP
    import pit_retrain_study as PRS
    PRS.PitEngine.DELIST = ctx["delist"]
    closes = pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(ctx["days"])
    return CP.make_runner(closes, ctx["ratio"], ctx["windows"], end=ctx["end"], start=ctx["start"], years=ctx["years"])


def trade_stats(tr: pd.DataFrame, a: str, b: str | None) -> dict:
    """组合里的个股交易（不含 1655、不含期末未平仓）：买入日在窗口内的每笔净收益 % 与胜率。"""
    if not len(tr):
        return {"n": 0, "mean": None, "win": None}
    ed = pd.to_datetime(tr["entry_date"])
    m = (ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)
    x = tr[m.to_numpy()]
    if not len(x):
        return {"n": 0, "mean": None, "win": None}
    net = x["pnl"].to_numpy(float) / (x["shares"].to_numpy(float) * x["entry_px"].to_numpy(float)) * 100
    return {"n": int(len(x)), "mean": round(float(net.mean()), 3), "win": round(float((x["pnl"].to_numpy(float) > 0).mean() * 100), 1)}


def run(ctx: dict, run_fn, fr: dict, p, **kw) -> dict:
    """一次组合回测 → {窗口: {cagr, dd, calmar, tot, n, mean, win}}（逐笔按买入日落在哪个窗口）。"""
    import jq_study as JS
    r = run_fn(fr, p, **kw)
    eng = JS.RealLotEngine.LAST[-1]
    tr = pd.DataFrame(eng.st.trades)
    if len(tr):
        tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")]
    out = {}
    for w, (a, b) in ctx["windows"].items():
        s = r.get(w) or {}
        out[w] = {"cagr": s.get("cagr"), "dd": s.get("dd"), "calmar": s.get("calmar"), "tot": s.get("tot"), **trade_stats(tr, a, b)}
    out["_years"] = r.get("years")
    return out


def summary(res: dict, era: str) -> dict:
    """leap_common.leap_fails 要的格式。"""
    w = res[era]
    return {"calmar": w["calmar"], "dd": w["dd"], "halves": [res[f"{era}1"]["calmar"], res[f"{era}2"]["calmar"]],
            "mean": w["mean"], "win": w["win"], "n": w["n"]}


def no_entries(fr: dict) -> dict:
    return {t: df.assign(entry=False) for t, df in fr.items()}


def with_mask(fr: dict, keep: dict[str, np.ndarray]) -> dict:
    """entry ∧ keep（keep 缺 → 不改）。"""
    return {t: (df.assign(entry=df["entry"].to_numpy(bool) & np.asarray(keep[t], bool)) if t in keep else df) for t, df in fr.items()}


def keep_frac(fr: dict, keep: dict[str, np.ndarray]) -> float:
    n = sum(int(df["entry"].to_numpy(bool).sum()) for df in fr.values())
    k = sum(int((df["entry"].to_numpy(bool) & np.asarray(keep.get(t, np.ones(len(df), bool)), bool)).sum()) for t, df in fr.items())
    return k / n if n else float("nan")


def placebo_q(ctx: dict, run_fn, fr: dict, p, frac: float, seeds: int = LC.PLACEBO_SEEDS, q: float = LC.PLACEBO_Q) -> tuple[float, list]:
    """把 fr 的信号按「股票 × 周」随机保留 frac（wvol_placebo.week_lottery），seeds 次 → 该窗口 Calmar 的 q 分位与全部值。"""
    import wvol_placebo as WP
    era = ctx["era"]
    vals = []
    for s in range(seeds):
        r = run(ctx, run_fn, WP.week_lottery(fr, frac, s), p)
        vals.append(r[era]["calmar"])
    v = np.array([x for x in vals if x is not None], float)
    return (float(np.percentile(v, q)) if len(v) else float("nan")), vals
