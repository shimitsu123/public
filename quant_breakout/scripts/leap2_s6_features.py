"""leap2_s6_features.py — 「选股本身的质的飞跃」第 S6 轮：全部指标表（每笔突破交易在信号日的约 33 个指标；只用信号日为止的数据）。

用户（2026-09-27）：「继续找新方向 各个分析指数互相搭配 调整阈值进行研究」→ 先把以前各轮用过的指标汇总到同一张表，
scripts/leap2_s6_combo.py 再做搭配与阈值搜索（只用 E / J；Z 只留给登记后的确认）。
交易 = 第 1 轮缓存的单独交易（var/cache/leap_r1_trades.pkl：今天的日経225 + 扩大池、现行卖出规则去掉 W2、扣成本；信号日 ≥ 2006-10-01）。
指标（来源）：
  个股（第 1 轮缓存）：dy 股息率、r12 / r2y / r3y / r5y 过去涨跌、sec 业种强弱、rsec 个股 − 业种、vr1 突破日量比、w5v 周线量比、
    hi52 离 250 日高点、vol60 波动、lturn 成交额；w2（周线量比 ≥ 1）
  事件（S2 event_features）：gap 突破日跳空、earn 决算季、hi3y 3 年新高、base 距上次 250 日新高的天数
  行情（S3 market_frame）：n225_r63 / r126 / r252、n225_ma200、n225_vol20、vix、usdjpy_r63、spx_r63、breadth50、newhigh、disp20、wave5
  美国同行业（S4）：us12 = 美国对应行业 12 个月强弱百分位（月数据只用到两个月前）
  宏观敏感度（S5）：b_n225、b_fx、b_us10、b_wti（104 周回归）
另加：seg（N225 / T500x / S1x）。结果缓存 var/cache/leap2_s6_features.pkl（不入库；J-Quants 以外的公开数据，但与第 1 轮缓存同样不入库）。
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
import leap_common as LC                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402

CACHE = "leap2_s6_features.pkl"
STOCK = ["dy", "r12", "r2y", "r3y", "r5y", "sec", "rsec", "vr1", "w5v", "hi52", "vol60", "lturn"]
EVENT = ["gap", "earn", "hi3y", "base"]
MARKET = ["n225_r63", "n225_r126", "n225_r252", "n225_ma200", "n225_vol20", "vix", "usdjpy_r63", "spx_r63", "breadth50", "newhigh",
          "disp20", "wave5"]
MACRO = ["us12", "b_n225", "b_fx", "b_us10", "b_wti"]


def build(refresh: bool = False) -> pd.DataFrame:
    fp = paths.sub("cache") / CACHE
    if fp.exists() and not refresh:
        return pd.read_pickle(fp)
    import leap_data as LD
    from bullbear_study import load
    from leap2_s2_explore import event_features
    from leap2_s3_explore import asof_upto, market_frame
    from leap2_s4_explore import S33_FF49, us_rank_asof
    from leap2_s5_explore import rolling_betas, weekly
    from qbreak import factors as F
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    t0 = time.time()
    T = pd.read_pickle(paths.sub("cache") / "leap_r1_trades.pkl")
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    LC.assert_explore_dates(T["sig_date"])
    T = T.reset_index(drop=True)
    names = sorted(T["ticker"].unique())
    data = LD.ohlcv(names)
    # 事件
    ev = [event_features(data[t], d) if t in data else {} for t, d in zip(T["ticker"], T["sig_date"])]
    E = pd.DataFrame(ev, index=T.index)
    for c in EVENT:
        T[c] = E[c] if c in E else np.nan
    print(f"  事件：{time.time() - t0:.0f}s", flush=True)
    # 行情
    n225n = list(universe("JP", "broad"))
    closes = pd.DataFrame({t: data[t]["Close"] for t in n225n if t in data}).sort_index()
    mk = market_frame(load("^N225", "1998-01-01")["Close"], load("^VIX", "1998-01-01")["Close"],
                      load("JPY=X", "1998-01-01")["Close"].where(lambda s: (s > 60) & (s < 250)), load("^GSPC", "1998-01-01")["Close"], closes)
    sig = T.groupby("sig_date").size()
    mk["wave5"] = sig.reindex(mk.index).fillna(0.0).rolling(5, min_periods=1).sum()
    for c in MARKET:
        T[c] = asof_upto(mk[c], pd.DatetimeIndex(T["sig_date"]))
    print(f"  行情：{time.time() - t0:.0f}s", flush=True)
    # 美国同行业
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    P = us_rank_asof(F.ff_industries(49, "vw"))
    mon = T["sig_date"].dt.to_period("M").dt.to_timestamp()
    ff = T["ticker"].map(s33).map(S33_FF49)
    T["us12"] = [P.at[m, f] if (isinstance(f, str) and f in P.columns and m in P.index) else np.nan for m, f in zip(mon, ff)]
    # 宏观敏感度
    C = pd.DataFrame({t: data[t]["Close"] for t in names if t in data}).sort_index()
    del data
    Yw = C.resample("W-FRI").last().pct_change(fill_method=None).clip(-0.5, 0.5)
    X = pd.DataFrame({"n225": weekly(load("^N225", "1998-01-01")["Close"]).pct_change(),
                      "fx": weekly(load("JPY=X", "1998-01-01")["Close"].where(lambda s: (s > 60) & (s < 250))).pct_change().shift(1),
                      "us10": weekly(load("^TNX", "1998-01-01")["Close"]).diff().shift(1),
                      "wti": weekly(load("CL=F", "2000-01-01")["Close"].where(lambda s: s > 1)).pct_change().shift(1)}).reindex(Yw.index)
    B = {"b_n225": rolling_betas(Yw, X[["n225"]], None)["n225"]}
    for f in ("fx", "us10", "wti"):
        B[f"b_{f}"] = rolling_betas(Yw, X[[f, "n225"]], "n225")[f]
    wk = T["sig_date"].dt.to_period("W-FRI").dt.start_time - pd.Timedelta(days=1)
    for k, M in B.items():
        idx = M.index.searchsorted(wk.to_numpy(), side="right") - 1
        T[k] = [M.iat[i, M.columns.get_loc(t)] if (i >= 0 and t in M.columns) else np.nan for i, t in zip(idx, T["ticker"])]
    print(f"  β：{time.time() - t0:.0f}s", flush=True)
    seg = WU.segment_of(WU.load())
    T["seg"] = np.where(T["n225"], "N225", T["ticker"].map(seg).fillna("other"))
    T["earn"] = T["earn"].astype(float)
    T["hi3y"] = T["hi3y"].astype(float)
    T.to_pickle(fp)
    return T


if __name__ == "__main__":
    t0 = time.time()
    T = build(refresh="--refresh" in sys.argv)
    print(f"{len(T)} 笔、{T.shape[1]} 列；用时 {time.time() - t0:.0f}s")
    print(T[STOCK + EVENT + MARKET + MACRO].notna().mean().round(2).to_string())
