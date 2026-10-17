"""leap2_s7_features.py — 「选股本身的质的飞跃」第 S7 轮：新指标家族「突破当天本身」（只用信号日为止的数据；接在 S6 指标表后面）。

用户（2026-09-27）：「A 继续搜索」（各指标搭配、调阈值）。S6 的 33 个指标是个股的历史、行情、宏观；这里加突破当天自己的结构与「个别驱动」度量：
  day_ret  信号日涨跌；clv 收盘在当天振幅里的位置（0 = 最低、1 = 最高）；brk_pos 收盘 ÷ 之前 60 日最高 − 1（比箱顶高多少）；
  range60  之前 60 日的箱体宽度（最高 − 最低）÷ 最低；vtrend 信号日前 5 天均量 ÷ 再之前 20 天均量（突破前量在不在放大）；
  up5 最近 5 天里收涨的天数；ext20 收盘 ÷ 20 日均线 − 1；corr60 最近 60 天日收益与日経225 的相关；
  mkt_day 日経225 当天涨跌；ex_mkt = day_ret − mkt_day（相对大盘的超额）；
  sec_ex = day_ret − 同業種（東証 33，日経225 + 扩大池里的成员）当天的中位数；sec_vr = 突破日量比 ÷ 同業種当天量比的中位数。
交易 = S6 指标表（var/cache/leap2_s6_features.pkl）的 3,749 笔；结果缓存 var/cache/leap2_s7_features.pkl（不入库）。
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap2_s6_features as F6                                               # noqa: E402
import leap_common as LC                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402

CACHE = "leap2_s7_features.pkl"
NEW = ["day_ret", "clv", "brk_pos", "range60", "vtrend", "up5", "ext20", "corr60", "mkt_day", "ex_mkt", "sec_ex", "sec_vr"]


def day_features(df: pd.DataFrame, sig: pd.Timestamp, mkt_ret: pd.Series) -> dict:
    """一只票的日线 + 信号日 → 突破当天的结构（只用信号日为止；mkt_ret = 日経225 日收益）。"""
    i = int(df.index.searchsorted(sig))
    if i >= len(df) or df.index[i] != sig or i < 61:
        return {}
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close", "Volume"))
    out = {"day_ret": c[i] / c[i - 1] - 1 if c[i - 1] > 0 else np.nan}
    out["clv"] = (c[i] - l[i]) / (h[i] - l[i]) if h[i] > l[i] else np.nan
    top, bot = np.nanmax(h[i - 60:i]), np.nanmin(l[i - 60:i])
    out["brk_pos"] = c[i] / top - 1 if top > 0 else np.nan
    out["range60"] = (top - bot) / bot if bot > 0 else np.nan
    v5, v20 = np.nanmean(v[i - 5:i]), np.nanmean(v[i - 25:i - 5])
    out["vtrend"] = v5 / v20 if v20 > 0 else np.nan
    out["up5"] = float(np.sum(c[i - 4:i + 1] > c[i - 5:i]))
    ma20 = np.nanmean(c[i - 19:i + 1])
    out["ext20"] = c[i] / ma20 - 1 if ma20 > 0 else np.nan
    r = pd.Series(c[i - 60:i + 1]).pct_change().to_numpy()[1:]
    m = mkt_ret.reindex(df.index[i - 59:i + 1]).to_numpy(float)
    ok = np.isfinite(r) & np.isfinite(m)
    out["corr60"] = float(np.corrcoef(r[ok], m[ok])[0, 1]) if ok.sum() >= 40 else np.nan
    md = mkt_ret.get(sig, np.nan)
    out["mkt_day"] = float(md)
    out["ex_mkt"] = out["day_ret"] - md if np.isfinite(md) else np.nan
    return out


def sector_relative(T: pd.DataFrame, R: pd.DataFrame, VR: pd.DataFrame, s33: dict[str, str]) -> tuple[np.ndarray, np.ndarray]:
    """每笔：当天涨跌 − 同業種中位数；量比 ÷ 同業種量比中位数（業種成员 = R 的列里同一業種的票，至少 5 只）。"""
    groups: dict[str, list[str]] = {}
    for t in R.columns:
        s = s33.get(t)
        if s:
            groups.setdefault(s, []).append(t)
    med_r = {s: R[cols].median(axis=1) for s, cols in groups.items() if len(cols) >= 5}
    med_v = {s: VR[cols].median(axis=1) for s, cols in groups.items() if len(cols) >= 5}
    ex, vr = np.full(len(T), np.nan), np.full(len(T), np.nan)
    for k, (t, d) in enumerate(zip(T["ticker"], T["sig_date"])):
        s = s33.get(t)
        if s in med_r and d in R.index and t in R.columns:
            ex[k] = R.at[d, t] - med_r[s].get(d, np.nan)
            mv = med_v[s].get(d, np.nan)
            vr[k] = VR.at[d, t] / mv if np.isfinite(mv) and mv > 0 else np.nan
    return ex, vr


def build(refresh: bool = False) -> pd.DataFrame:
    fp = paths.sub("cache") / CACHE
    if fp.exists() and not refresh:
        return pd.read_pickle(fp)
    import leap_data as LD
    from bullbear_study import load
    t0 = time.time()
    T = F6.build().reset_index(drop=True)
    LC.assert_explore_dates(T["sig_date"])
    names = sorted(T["ticker"].unique())
    data = LD.ohlcv(names)
    mkt = load("^N225", "1998-01-01")["Close"].pct_change()
    rows = [day_features(data[t], d, mkt) if t in data else {} for t, d in zip(T["ticker"], T["sig_date"])]
    D = pd.DataFrame(rows, index=T.index)
    for c in NEW:
        if c in D:
            T[c] = D[c]
    print(f"  当天结构：{time.time() - t0:.0f}s", flush=True)
    C = pd.DataFrame({t: data[t]["Close"] for t in names if t in data}).sort_index()
    V = pd.DataFrame({t: data[t]["Volume"] for t in names if t in data}).sort_index()
    del data
    R = C.pct_change(fill_method=None)
    VR = V / V.shift(1).rolling(20, min_periods=15).mean()
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    T["sec_ex"], T["sec_vr"] = sector_relative(T, R, VR, s33)
    print(f"  同業種：{time.time() - t0:.0f}s", flush=True)
    T.to_pickle(fp)
    return T


if __name__ == "__main__":
    t0 = time.time()
    T = build(refresh="--refresh" in sys.argv)
    print(f"{len(T)} 笔、{T.shape[1]} 列；用时 {time.time() - t0:.0f}s")
    print(T[NEW].describe().T[["count", "mean", "50%"]].round(4).to_string())
