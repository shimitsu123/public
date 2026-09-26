"""candle_data.py — K 线形态研究共用的数据（2026-09-27）：J-Quants 时点股票池的宽表 + yfinance 今天的日経225（2006〜2016 年代）。

JQ：scripts/pit_retrain_study.load_data（批量日线，拆股调整；U2 = 时点 TOPIX 1000、U1 = 时点 TOPIX 500 的每日成员掩码，U0 = 今天的日経225）
E0：yfinance 21 年（今天的日経225 股票池，调整后行情）→ 2006-10〜2016-09 是 J-Quants 之前、没参与任何 K 线研究的年代。
宽表缓存在 var/cache/candle_panels.npz（由 J-Quants 原始数据算出 → 不入库；var/cache 已在 .gitignore）。
时期：E0 2006-10〜2016-09；T 探索期 2017-01〜2021-12；V 验证期 2022-01〜2023-09；H 留出期 2023-10〜2026-09（半段 2025-04 分）。
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

PERIODS = {"E0": ("2006-10-01", "2016-10-01"), "T": ("2017-01-01", "2022-01-01"), "V": ("2022-01-01", "2023-10-01"),
           "H": ("2023-10-01", "2026-10-01")}
PERIOD_NAMES = {"E0": "2006-10〜2016-09（yfinance 今天的日経225，没用过的年代）", "T": "探索期 2017〜2021", "V": "验证期 2022-01〜2023-09",
                "H": "留出期 2023-10〜"}
CACHE = "candle_panels.npz"


def _build() -> dict:
    import pit_retrain_study as PRS
    from qbreak import candles as K
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    D = PRS.load_data()
    cal = pd.DatetimeIndex(sorted(set().union(*[df.index for df in D["data"].values()])))
    days = cal[(cal >= pd.Timestamp(PRS.WINDOW[0])) & (cal <= pd.Timestamp(PRS.WINDOW[1]))]
    names, masks = {}, {}
    for u in ("U0", "U1", "U2"):
        names[u], masks[u] = PRS.universe_members(D, u, days)
    nm = sorted(set(names["U2"]) | set(names["U0"]))
    P = K.panel(D["data"], days, nm)
    mem = {u: pd.DataFrame({t: masks[u][t] for t in names[u]}).reindex(index=days, columns=nm).fillna(False).to_numpy(bool)
           for u in ("U1", "U2")}
    mem["U0"] = np.isin(np.array(nm), names["U0"])[None, :] & np.isfinite(P["C"])
    yf = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    en = sorted(yf)
    ecal = pd.DatetimeIndex(sorted(set().union(*[df.index for df in yf.values()])))
    edays = ecal[(ecal >= pd.Timestamp("2005-09-01")) & (ecal < pd.Timestamp(PERIODS["E0"][1]) + pd.Timedelta(days=60))]
    E = K.panel(yf, edays, en)
    return {"days": days.values, "names": np.array(nm), **{f"J_{k}": v for k, v in P.items()},
            **{f"M_{u}": v for u, v in mem.items()}, "edays": edays.values, "enames": np.array(en), **{f"E_{k}": v for k, v in E.items()},
            "delist_names": np.array(sorted(PRS.delist_dates({t: D["data"][t] for t in nm})))}


def load(rebuild: bool = False) -> dict:
    """{"days", "names", "P" (JQ 宽表), "mem" {U0, U1, U2}, "edays", "enames", "E" (E0 宽表)}。第一次约 2〜3 分钟，之后读缓存。"""
    fp = paths.sub("cache") / CACHE
    t0 = time.time()
    if rebuild or not fp.exists():
        z = _build()
        np.savez(fp, **z)
    z = dict(np.load(fp, allow_pickle=False))
    out = {"days": pd.DatetimeIndex(z["days"]), "names": list(z["names"]), "P": {k: z[f"J_{k}"] for k in "OHLCV"},
           "mem": {u: z[f"M_{u}"] for u in ("U0", "U1", "U2")}, "edays": pd.DatetimeIndex(z["edays"]), "enames": list(z["enames"]),
           "E": {k: z[f"E_{k}"] for k in "OHLCV"}, "load_s": round(time.time() - t0, 1)}
    return out


def period_mask(days: pd.DatetimeIndex, key: str) -> np.ndarray:
    a, b = PERIODS[key]
    return np.asarray((days >= pd.Timestamp(a)) & (days < pd.Timestamp(b)))
