"""loop14_ra_price.py — 第十四个研究循环 A 轮：CNQ / PRF / GAP / OVN（定义见 scripts/research_loop14.py；路线 A / B，按事后判）。非投资建议。"""
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
import loop14_common as L14                                                  # noqa: E402

IDS = ("CNQ", "PRF", "GAP", "OVN")
CNQ_N, CNQ_MIN, CNQ_Q = 120, 80, 67
PRF_FROM, PRF_TO, PRF_LOOK, PRF_UP = 60, 5, 120, 1.05
GAP_UP = 1.01
OVN_N, OVN_Q = 60, 80


def cnq(c: np.ndarray, dates: pd.DatetimeIndex, i: int, nq_ret: pd.Series) -> float:
    """信号日 i 为止 CNQ_N 天：个股收盘日收益与日元计纳指日收益（按东证日期对齐）的相关；有效对 < CNQ_MIN → NaN。"""
    if i < CNQ_N:
        return np.nan
    rs = c[i - CNQ_N + 1:i + 1] / c[i - CNQ_N:i] - 1
    rn = nq_ret.reindex(dates[i - CNQ_N + 1:i + 1]).to_numpy(float)
    ok = np.isfinite(rs) & np.isfinite(rn)
    if ok.sum() < CNQ_MIN or np.std(rs[ok]) == 0 or np.std(rn[ok]) == 0:
        return np.nan
    return float(np.corrcoef(rs[ok], rn[ok])[0, 1])


def prf(c: np.ndarray, i: int) -> bool:
    """信号日前 PRF_FROM〜PRF_TO 天里第一个「收盘 > 之前 PRF_LOOK 天最高收盘」的日子 j；j 之后到 i − 1 的最高收盘 < c[j] × PRF_UP → True。"""
    for j in range(i - PRF_FROM, i - PRF_TO + 1):
        if j - PRF_LOOK < 0:
            continue
        if c[j] > np.max(c[j - PRF_LOOK:j]):
            after = c[j + 1:i]
            return bool(len(after) and np.max(after) < c[j] * PRF_UP)
    return False


def gap(o: np.ndarray, h: np.ndarray, i: int) -> bool:
    return bool(i >= 1 and np.isfinite(o[i]) and np.isfinite(h[i - 1]) and o[i] > h[i - 1] * GAP_UP)


def ovn(o: np.ndarray, c: np.ndarray, i: int) -> float:
    """信号日 i 为止 OVN_N 天：Σ ln(开盘 ÷ 前收) − Σ ln(收盘 ÷ 开盘)。"""
    if i < OVN_N:
        return np.nan
    oo, cc, pc = o[i - OVN_N + 1:i + 1], c[i - OVN_N + 1:i + 1], c[i - OVN_N:i]
    with np.errstate(divide="ignore", invalid="ignore"):
        x = np.log(oo / pc) - np.log(cc / oo)
    return float(np.sum(x)) if np.isfinite(x).all() else np.nan


def feats(fa: dict, tickers, dates, nq_ret: pd.Series) -> pd.DataFrame:
    rows = []
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates))):
        df = fa.get(str(t))
        if df is None or d not in df.index:
            rows.append((np.nan, False, False, np.nan))
            continue
        i = df.index.get_loc(d)
        o, h, c = (df[k].astype(float).to_numpy() for k in ("Open", "High", "Close"))
        rows.append((cnq(c, pd.DatetimeIndex(df.index), i, nq_ret), prf(c, i), gap(o, h, i), ovn(o, c, i)))
    return pd.DataFrame(rows, columns=["cnq", "prf", "gap", "ovn"])


def nasdaq_yen_ret() -> pd.Series:
    """东证交易日的日元计纳指（前一个美国收盘 × 东证当天早上的 USD/JPY）的日收益。"""
    import equity_idle_study as EI
    inp = EI.load_inputs()
    days = L14.trading_days("1995-01-01", str(pd.Timestamp.now().date()))
    v = EI.on_jp(EI.ndx_tr(inp), inp["fx"], days)
    return v.pct_change()


def build(W: dict, nq_ret: pd.Series | None = None) -> dict:
    nq_ret = nasdaq_yen_ret() if nq_ret is None else nq_ret
    G = {k: {"era": {}, "pool": {}} for k in IDS}
    X = {e: feats(W["SM"][L14.SM_OF[e]]["fa"], LC.signals(W, e)["ticker"], LC.signals(W, e)["date"], nq_ret) for e in LC.ERAS}
    cut_c = L14.era_cut({e: X[e]["cnq"] for e in LC.ERAS}, CNQ_Q)
    cut_o = L14.era_cut({e: X[e]["ovn"] for e in LC.ERAS}, OVN_Q)

    def gates(x: pd.DataFrame, e: str) -> dict:
        return {"CNQ": L14.at_least(x["cnq"], cut_c[e]), "PRF": x["prf"].to_numpy(bool), "GAP": x["gap"].to_numpy(bool),
                "OVN": L14.at_least(x["ovn"], cut_o[e])}
    for e in LC.ERAS:
        for k, v in gates(X[e], e).items():
            G[k]["era"][e] = v
    for s in ("W", "Jx", "Zx"):
        if s in W["D"]:
            P = LC.pool_x(W, s)
            for k, v in gates(feats(W["SM"][L14.SM_OF[s]]["fa"], P["ticker"], P["date"], nq_ret), L14.ERA_OF[s]).items():
                G[k]["pool"][s] = v
    G["_cut"] = {"CNQ": cut_c, "OVN": cut_o}
    return G


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true")
    a = ap.parse_args(argv)
    W = LC.load()
    G = build(W)
    cut = G.pop("_cut")
    if a.wiring:
        r = L14.wiring(W, G)
        r["cut"] = cut
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r["same_as_b4"] else 1
    L14.run(W, G, "# 第十四个研究循环 A 轮：与核心相关 / 前次突破失败 / 跳空突破 / 隔夜收益 CNQ / PRF / GAP / OVN", "loop14_ra_price")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
