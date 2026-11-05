"""loop13_rb_struct.py — 第十三个研究循环 B 轮：VCP / DDS / CSE（定义见 scripts/research_loop13.py；路线 A / B）。非投资建议。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402
import loop13_common as L13                                                  # noqa: E402

IDS = ("VCP", "DDS", "CSE")
VCP_Q, DDS_MAX, CSE_UP, CSE_N = 80, -0.40, 0.20, 20


def one(df: pd.DataFrame | None, d: pd.Timestamp) -> tuple[float, float]:
    if df is None or d not in df.index:
        return np.nan, np.nan
    i = df.index.get_loc(d)
    h, l, c = (df[k].astype(float).to_numpy() for k in ("High", "Low", "Close"))
    vcp = np.nan
    if i >= 51:
        pc = np.r_[np.nan, c[:-1]]
        tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
        a10, a50 = np.nanmean(tr[i - 10:i]), np.nanmean(tr[i - 50:i])                 # 信号日前一天为止
        vcp = a10 / a50 if a50 > 0 else np.nan
    dds = np.nan
    if i >= 249:
        w = c[i - 249:i + 1]
        dds = float(np.min(w / np.maximum.accumulate(w) - 1))
    return vcp, dds


def feats(fa: dict, tickers, dates) -> pd.DataFrame:
    return pd.DataFrame([one(fa.get(str(t)), pd.Timestamp(d)) for t, d in zip(tickers, pd.to_datetime(np.asarray(dates)))], columns=["vcp", "dds"])


def cse_gate(baa: pd.Series, days: pd.DatetimeIndex, dates) -> np.ndarray:
    b = baa.dropna()
    out = []
    for d in pd.to_datetime(np.asarray(dates)):
        x = b[b.index < d]
        k = days.searchsorted(d, side="left")
        if len(x) == 0 or k - CSE_N < 0:
            out.append(False)
            continue
        prev = b[b.index < days[k - CSE_N]]
        out.append(bool(len(prev)) and float(x.iloc[-1] - prev.iloc[-1]) >= CSE_UP)
    return np.array(out, bool)


def build(W: dict) -> dict:
    from qbreak import factors
    baa = factors.fred("BAA10Y")
    days = L13.trading_days()
    G = {k: {"era": {}, "pool": {}} for k in IDS}
    cut = {}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        X = feats(W["SM"][L13.SM_OF[e]]["fa"], S["ticker"], S["date"])
        cut[e] = float(np.nanpercentile(X["vcp"], VCP_Q))
        G["VCP"]["era"][e] = (X["vcp"] >= cut[e]).fillna(False).to_numpy(bool)
        G["DDS"]["era"][e] = (X["dds"] <= DDS_MAX).fillna(False).to_numpy(bool)
        G["CSE"]["era"][e] = cse_gate(baa, days, S["date"])
    for s in ("W", "Jx", "Zx"):
        if s in W["D"]:
            P = LC.pool_x(W, s)
            X = feats(W["SM"][L13.SM_OF[s]]["fa"], P["ticker"], P["date"])
            G["VCP"]["pool"][s] = (X["vcp"] >= cut[L13.ERA_OF[s]]).fillna(False).to_numpy(bool)
            G["DDS"]["pool"][s] = (X["dds"] <= DDS_MAX).fillna(False).to_numpy(bool)
            G["CSE"]["pool"][s] = cse_gate(baa, days, P["date"])
    return G


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true")
    a = ap.parse_args(argv)
    W = LC.load()
    G = build(W)
    if a.wiring:
        r = L13.wiring(W, G)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r["same_as_b4"] else 1
    L13.run(W, G, "# 第十三个研究循环 B 轮：突破前没收缩 / 深跌过 / 信用利差扩大 VCP / DDS / CSE", "loop13_rb_struct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
