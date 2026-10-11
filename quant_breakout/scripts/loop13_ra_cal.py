"""loop13_ra_cal.py — 第十三个研究循环 A 轮：SQW / YRE / MON / IDX（定义见 scripts/research_loop13.py；日历，路线 A / B）。非投资建议。"""
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

IDS = ("SQW", "YRE", "MON", "IDX")


def sq_weeks(days: pd.DatetimeIndex) -> set:
    """每个月 SQ 日（第 2 个星期五；休市 → 前一个交易日）所在那一周（周一〜周五）的全部日子。"""
    out = set()
    for p in pd.period_range(days[0], days[-1], freq="M"):
        fr = [d for d in pd.date_range(p.start_time, p.end_time) if d.weekday() == 4]
        if len(fr) < 2:
            continue
        sq = fr[1]
        k = days.searchsorted(sq, side="right") - 1
        if k < 0:
            continue
        sq = days[k]
        mon = sq - pd.Timedelta(days=sq.weekday())
        out |= set(pd.date_range(mon, mon + pd.Timedelta(days=4)))
    return out


def gates(dates, days: pd.DatetimeIndex, sqw: set) -> dict[str, np.ndarray]:
    D = pd.to_datetime(np.asarray(dates))
    s = pd.Series(days, index=days)
    dec_last = set()
    pre_oct = set()
    for (y, m), g in s.groupby([days.year, days.month]):
        if m == 12:
            dec_last |= set(g.iloc[-10:])
        if m == 10:
            k = days.get_loc(g.iloc[0])
            pre_oct |= set(days[max(0, k - 15):k])
    return {"SQW": np.array([d in sqw for d in D], bool), "YRE": np.array([d in dec_last for d in D], bool),
            "MON": np.array([d.weekday() == 4 for d in D], bool), "IDX": np.array([d in pre_oct for d in D], bool)}


def build(W: dict) -> dict:
    days = L13.trading_days()
    sqw = sq_weeks(days)
    G = {k: {"era": {}, "pool": {}} for k in IDS}
    for e in LC.ERAS:
        g = gates(LC.signals(W, e)["date"], days, sqw)
        for k in IDS:
            G[k]["era"][e] = g[k]
    for s in ("W", "Jx", "Zx"):
        if s in W["D"]:
            g = gates(LC.pool_x(W, s)["date"], days, sqw)
            for k in IDS:
                G[k]["pool"][s] = g[k]
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
    L13.run(W, G, "# 第十三个研究循环 A 轮：SQ 周 / 年末 / 星期五 / 日経225 入替前 SQW / YRE / MON / IDX", "loop13_ra_cal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
