"""loop13_rc_jq.py — 第十三个研究循环 C 轮：FYB / SRN / CHR（定义见 scripts/research_loop13.py；J-Quants，路线 J）。非投资建议。"""
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
import loop12_r03_fund3 as R3                                                # noqa: E402
import loop13_common as L13                                                  # noqa: E402

IDS = ("FYB", "SRN", "CHR")
FYB_DAYS, FYB_MAX, SRN_N, CHR_MIN = 90, -5.0, 20, 0.30


def fy_surprise(F: pd.DataFrame) -> pd.DataFrame:
    """年度决算短信：实绩利润 ÷ 这个决算期最后一次会社予想 − 1（%）。予想 = 之前（开示日更早）同一个决算期末的「当期予想」。"""
    rows, last_fc = [], {}
    for r in F.sort_values(["ticker", "date"], kind="mergesort").to_dict("records"):
        a, f, _ = LC._profit(r)
        key = (r["ticker"], r["fye"])
        if r["per"] == "FY" and np.isfinite(a) and key in last_fc and last_fc[key] > 0:
            rows.append({"ticker": r["ticker"], "date": r["date"], "fyb": (a / last_fc[key] - 1) * 100})
        if r["per"] in ("1Q", "2Q", "3Q") and np.isfinite(f):
            last_fc[key] = f
    return pd.DataFrame(rows, columns=["ticker", "date", "fyb"])


def srn_gate(SP: pd.DataFrame, days: pd.DatetimeIndex, tickers, dates) -> np.ndarray:
    by = {t: (g["avail"].to_numpy("datetime64[ns]"), g["holders"].to_numpy(int)) for t, g in SP.sort_values(["ticker", "avail"]).groupby("ticker")}
    out = []
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates))):
        x = by.get(str(t))
        k = days.searchsorted(d, side="left")
        if x is None or k - SRN_N < 0:
            out.append(False)
            continue
        i_now = int(np.searchsorted(x[0], np.datetime64(d), side="left")) - 1
        i_old = int(np.searchsorted(x[0], np.datetime64(days[k - SRN_N]), side="left")) - 1
        h_now = x[1][i_now] if i_now >= 0 else 0
        h_old = x[1][i_old] if i_old >= 0 else 0
        out.append(bool(h_now > h_old))
    return np.array(out, bool)


def build(W: dict) -> dict:
    import jq_extra_data as JX
    F = LC.fins_rows()
    FY = fy_surprise(F)
    C = pd.DataFrame({"ticker": F["ticker"], "date": F["date"], "chr": np.where(F["TA"] > 0, F["CashEq"] / F["TA"].replace(0, np.nan), np.nan)})
    days = L13.trading_days()
    SP = JX.short_positions(pd.DatetimeIndex(sorted(set(W["ctx"]["J"]["days"]))))
    G = {k: {"era": {}, "pool": {}} for k in IDS}

    def gates(tickers, dates):
        fyb = LC.asof(FY, "fyb", tickers, dates, stale_days=FYB_DAYS)
        chr_ = LC.asof(C, "chr", tickers, dates)
        chr_ = np.where(R3._fin(tickers), np.nan, chr_)
        return {"FYB": np.nan_to_num(fyb, nan=0.0) < FYB_MAX, "SRN": srn_gate(SP, days, tickers, dates),
                "CHR": np.nan_to_num(chr_, nan=0.0) >= CHR_MIN}
    S = LC.signals(W, "J")
    gj = gates(S["ticker"], S["date"])
    X = LC.pool_x(W, "Jx")
    gp = gates(X["ticker"], X["date"])
    for k in IDS:
        G[k]["era"]["J"], G[k]["pool"]["Jx"] = gj[k], gp[k]
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
    L13.run(W, G, "# 第十三个研究循环 C 轮：年度业绩意外 / 新空卖方 / 现金比率 FYB / SRN / CHR", "loop13_rc_jq")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
