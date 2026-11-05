"""leap_r2_explore.py — 「质的飞跃」第 2 轮探索（只描述、不登记；只统计 2006-10 以后的月份，Z 年代的结果不看）。

问题：不等突破、每月按一个分数直接挑股票拿一个月（「选股组合」），能不能比日経225 等权平均、比核心（S&P500 日元计）更好？
  分数（都只用月末收盘为止）：12-1 个月涨跌（个股动量）、所在業種 12-1 个月强弱 + 业种里最强的票、60 日低波动、股息率高、
  3 年跌得多（长期反转）、合成（股息率 + 低波动 + 业种强弱）。
数据：yfinance 27 年（今天的日経225 股票池 + 扩大池的业种信息，scripts/leap_data.py）；每月末选前 K 只（K = 4 / 8），等权拿到下个月末，
  扣来回成本 0.25%；对照 = 同一股票池等权、S&P500 × USD/JPY（核心，不含择时）。
年代：E 2006-10〜2016-09、J 2017-01〜2026-09。
输出：var/out/leap_r2_explore.md / .json（只有统计）
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
import leap_data as LD                                                       # noqa: E402
import leap_r1_explore as R1                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
COST = 0.25
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_end_rows(days: pd.DatetimeIndex) -> np.ndarray:
    """每个月最后一个交易日在 days 里的位置。"""
    s = pd.Series(np.arange(len(days)), index=days)
    return s.groupby(days.to_period("M")).last().to_numpy()


def pick_top(score: np.ndarray, k: int, ok: np.ndarray) -> np.ndarray:
    """一行分数 → 前 k 个的列号（分数缺值或 ok=False 的不选）。"""
    v = np.where(ok & np.isfinite(score), score, -np.inf)
    idx = np.argsort(-v, kind="stable")[:k]
    return idx[np.isfinite(v[idx])]


def sleeve_returns(C: np.ndarray, rows: np.ndarray, scores: dict[str, np.ndarray], k: int, ok: np.ndarray) -> dict[str, np.ndarray]:
    """每个月末 r：按分数选前 k 只，拿到下一个月末 → 月收益 %（等权、扣来回成本）；另给同一股票池等权。"""
    out = {n: [] for n in scores}
    out["EW"] = []
    for a, b in zip(rows[:-1], rows[1:]):
        r = C[b] / C[a] - 1
        good = ok[a] & np.isfinite(r)
        out["EW"].append(float(np.nanmean(np.where(good, r, np.nan))) * 100 if good.any() else np.nan)
        for n, S in scores.items():
            idx = pick_top(S[a], k, good)
            out[n].append(float(np.mean(r[idx])) * 100 - COST if len(idx) else np.nan)
    return {n: np.array(v) for n, v in out.items()}


def perf(m: pd.Series) -> dict:
    m = m.dropna()
    if not len(m):
        return {}
    eq = (1 + m / 100).cumprod()
    yrs = len(m) / 12
    cagr = (eq.iloc[-1] ** (1 / yrs) - 1) * 100
    dd = float((eq / eq.cummax() - 1).min() * 100)
    return {"cagr": round(float(cagr), 2), "vol": round(float(m.std() * np.sqrt(12)), 2), "dd": round(dd, 2),
            "calmar": round(float(cagr / abs(dd)), 3) if dd < 0 else None, "n": int(len(m))}


def main() -> int:
    from bullbear_study import load
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    t0 = time.time()
    n225 = list(universe("JP", "broad"))
    names = LD.names()
    data = LD.ohlcv(names)
    names = [t for t in names if t in data and len(data[t])]
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in names])))
    days = days[days >= pd.Timestamp(LC.Z_WARMUP_START)]
    C = pd.DataFrame({t: data[t]["Close"] for t in names}).reindex(days).ffill(limit=5).to_numpy(float)
    del data
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    for xs in WU.load()["segments"].values():
        for x in xs:
            s33.setdefault(f"{x['code']}.T", x.get("s33"))
    sectors = [s33.get(t) for t in names]
    LR = R1.long_returns(C)
    SP, RS = R1.sector_strength(C, sectors)
    L = np.log(np.where(C > 0, C, np.nan))
    vol60 = pd.DataFrame(np.vstack([np.full((1, C.shape[1]), np.nan), np.diff(L, axis=0)])).rolling(60, min_periods=45).std().to_numpy()
    DY = np.full(C.shape, np.nan)
    for j, t in enumerate(names):
        DY[:, j] = LD.div_yield(LD.actions(t), days).to_numpy()
    in225 = np.array([t in set(n225) for t in names])
    ok = np.isfinite(C) & in225[None, :]
    rows = month_end_rows(days)
    pct = lambda A: pd.DataFrame(np.where(ok, A, np.nan)).rank(axis=1, pct=True).to_numpy()                     # noqa: E731
    scores = {"MOM 个股 12-1 个月最强": LR["r12"], "SEC 最强業種里最强的票": SP * 10 + pct(RS),
              "LVOL 60 日波动最低": -vol60, "DY 股息率最高": DY, "LTR 3 年跌得最多": -LR["r3y"],
              "COMP 股息率 + 低波动 + 業種强弱": pct(DY) + pct(-vol60) + SP}
    fx = load("JPY=X", "2000-01-01")["Close"]
    spx = load("^GSPC", "1999-01-01")["Close"]
    core = (spx * fx.reindex(spx.index).ffill()).dropna()
    say(f"# 「质的飞跃」第 2 轮探索：每月选股组合（只描述，{pd.Timestamp.today().date()}）")
    say(f"股票池：今天的日経225 {int(in225.sum())} 只（業種强弱用 日経225 + 扩大池 {len(names)} 只算）；每月末选前 K 只等权拿一个月，扣来回 {COST}%")
    out = {}
    for k in (4, 8):
        R = sleeve_returns(C, rows, scores, k, ok)
        me = days[rows[:-1]]
        cm = core.reindex(days[rows], method="ffill").to_numpy()
        corem = pd.Series((cm[1:] / cm[:-1] - 1) * 100, index=me)
        for era, (a, b) in ERAS.items():
            msk = (me >= pd.Timestamp(a)) & (me < pd.Timestamp(b))
            LC.assert_explore_dates(me[msk])
            ew = pd.Series(R["EW"], index=me)[msk]
            say(f"\n## K = {k}，{era} {a[:7]}〜{b[:7]}（{int(msk.sum())} 个月）")
            say("| 组合 | 年化 | 波动 | 最大回撤 | Calmar | 比等权好的月份 | 比等权好的年份 | 与核心月收益相关 |")
            say("|---|---|---|---|---|---|---|---|")
            for n in ["EW"] + list(scores):
                s = pd.Series(R[n], index=me)[msk]
                p = perf(s)
                beat = float((s > ew).mean() * 100) if n != "EW" else None
                yb = s.groupby(s.index.year).sum() > ew.groupby(ew.index.year).sum()
                corr = float(s.corr(corem[msk]))
                out[f"K{k}/{era}/{n}"] = {**p, "beat_m": beat, "beat_y": [int(yb.sum()), int(len(yb))], "corr_core": round(corr, 3)}
                lab = "等权（同一股票池）" if n == "EW" else n
                say(f"| {lab} | {p.get('cagr', '—')}% | {p.get('vol', '—')}% | {p.get('dd', '—')}% | {p.get('calmar', '—')} | "
                    f"{'—' if beat is None else f'{beat:.0f}%'} | {'—' if n == 'EW' else f'{int(yb.sum())}/{len(yb)}'} | {corr:.2f} |")
            pc = perf(corem[msk])
            say(f"| 核心（S&P500 × USD/JPY，不择时） | {pc.get('cagr')}% | {pc.get('vol')}% | {pc.get('dd')}% | {pc.get('calmar')} | — | — | 1.00 |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r2_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
