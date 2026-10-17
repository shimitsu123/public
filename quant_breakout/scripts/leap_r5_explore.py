"""leap_r5_explore.py — 「质的飞跃」第 5 轮探索：增配 / 减配（只描述、不登记；只统计 2006-10 以后）。

信息：每股分红的变化（过去 12 个月合计 ÷ 再之前 12 个月合计 − 1；yfinance 分红，按拆股调整，权利落ち日才算已知），
文献：增配之后股价继续走强、减配之后走弱（管理层对业绩的判断）。以前的研究没用过。
① 突破逐笔（第 1 轮的独立交易 var/cache/leap_r1_trades.pkl）：按分红变化分组的每笔净收益 / 胜率 / 比同期核心多赚多少；
② 每月选股组合：今天的日経225 里「最近 12 个月增配 + 股息率高」前 K 只，与等权、核心比（E / J）。
输出：var/out/leap_r5_explore.md / .json（只有统计）
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
import leap_r2_explore as R2                                                 # noqa: E402
import leap_r3_explore as R3                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def div_growth(act: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    """过去 365 天分红合计 ÷ 再之前 365 天合计 − 1（%）；之前一年没有分红 → 有分红 = +100（开始分红），都没有 → NaN。"""
    if act is None or not len(act):
        return pd.Series(np.nan, index=days)
    cum = act["div"].fillna(0.0).cumsum()
    c = cum.reindex(cum.index.union(days).union(days - pd.Timedelta(days=365)).union(days - pd.Timedelta(days=730))).ffill().fillna(0.0)
    a = c.reindex(days).to_numpy() - c.reindex(days - pd.Timedelta(days=365)).to_numpy()
    b = c.reindex(days - pd.Timedelta(days=365)).to_numpy() - c.reindex(days - pd.Timedelta(days=730)).to_numpy()
    g = np.where(b > 0, (a / np.where(b > 0, b, 1) - 1) * 100, np.where(a > 0, 100.0, np.nan))
    first = act.index[0] + pd.Timedelta(days=730)
    return pd.Series(np.where(days >= first, g, np.nan), index=days)


def bucket(g: float) -> str | None:
    if not np.isfinite(g):
        return None
    return "减配（< −5%）" if g < -5 else ("持平（±5%）" if g <= 5 else ("小幅增配（5〜20%）" if g <= 20 else "大幅增配（> 20%）"))


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.config import universe
    from unified_study import spx_jpy_on_jp_days
    t0 = time.time()
    T = pd.read_pickle(paths.sub("cache") / "leap_r1_trades.pkl")
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    LC.assert_explore_dates(T["sig_date"])
    fx = load("JPY=X", "2000-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    jp = load(*SYM["JP"])
    core = spx_jpy_on_jp_days(load(*SYM["US"]), fx, jp.index)["Close"]
    T["core"] = R3.core_over(core, T["sig_date"], T["hold_days"])
    T["ex"] = T["net"] - T["core"]
    g = np.full(len(T), np.nan)
    for t, idx in T.groupby("ticker").groups.items():
        dg = div_growth(LD.actions(t), pd.DatetimeIndex(T.loc[idx, "sig_date"]))
        g[T.index.get_indexer(idx)] = dg.to_numpy()
    T["dgr"] = g
    T["b"] = [bucket(x) for x in T["dgr"]]
    say(f"# 「质的飞跃」第 5 轮探索：增配 / 减配（只描述，{pd.Timestamp.today().date()}）")
    say("① 突破逐笔（日経225 + 扩大池，现行突破去掉 W2；每笔净收益 / 胜率 / 比同期核心多赚）")
    out = {"trades": {}, "sleeve": {}}
    order = ["减配（< −5%）", "持平（±5%）", "小幅增配（5〜20%）", "大幅增配（> 20%）"]
    for era, (a, b) in ERAS.items():
        E = T[(T["sig_date"] >= pd.Timestamp(a)) & (T["sig_date"] < pd.Timestamp(b))]
        for sub, V in (("全部突破", E), ("W2 保留", E[E["w2"]])):
            say(f"\n### {era} · {sub}（{len(V)} 笔；分红变化有值 {V['dgr'].notna().mean() * 100:.0f}%）")
            say("| 分红变化 | 笔数 | 每笔 | 胜率 | 比核心多赚 | 赢核心 | 各年「增配 > 减配」 |")
            say("|---|---|---|---|---|---|---|")
            yrs = V["sig_date"].dt.year
            for k in order:
                x = V[V["b"] == k]
                out["trades"][f"{era}/{sub}/{k}"] = R3.tstats(x)
                s = R3.tstats(x)
                say(f"| {k} | {s.get('n', 0)} | {s.get('net', float('nan')):+.2f}% | {s.get('win', float('nan')):.0f}% | "
                    f"{s.get('ex', float('nan')):+.2f} pp | {s.get('beat', float('nan')):.0f}% | — |" if s.get("n") else f"| {k} | 0 | — | — | — | — | — |")
            up, dn = V["dgr"] > 5, V["dgr"] < -5
            better = sum(int(V.loc[up & (yrs == y), "net"].mean() > V.loc[dn & (yrs == y), "net"].mean())
                         for y in sorted(yrs.unique()) if (up & (yrs == y)).sum() >= 5 and (dn & (yrs == y)).sum() >= 5)
            ny = sum(1 for y in sorted(yrs.unique()) if (up & (yrs == y)).sum() >= 5 and (dn & (yrs == y)).sum() >= 5)
            say(f"| 增配（> 5%）− 减配 | — | {V.loc[up, 'net'].mean() - V.loc[dn, 'net'].mean():+.2f} pp | — | "
                f"{V.loc[up, 'ex'].mean() - V.loc[dn, 'ex'].mean():+.2f} pp | — | {better}/{ny} |")
    n225 = list(universe("JP", "broad"))
    data = LD.ohlcv(n225)
    nm = [t for t in n225 if t in data and len(data[t])]
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in nm])))
    days = days[days >= pd.Timestamp(LC.Z_WARMUP_START)]
    C = pd.DataFrame({t: data[t]["Close"] for t in nm}).reindex(days).ffill(limit=5).to_numpy(float)
    DG = np.column_stack([div_growth(LD.actions(t), days).to_numpy() for t in nm])
    DY = np.column_stack([LD.div_yield(LD.actions(t), days).to_numpy() for t in nm])
    ok = np.isfinite(C)
    pct = lambda A: pd.DataFrame(np.where(ok, A, np.nan)).rank(axis=1, pct=True).to_numpy()                   # noqa: E731
    scores = {"DG 分红增长最多": DG, "DGY 增配 ∧ 股息率高": np.where(DG > 5, pct(DY), np.nan),
              "DGY2 增配幅度 + 股息率（百分位平均）": (pct(DG) + pct(DY)) / 2}
    rows = R2.month_end_rows(days)
    me = days[rows[:-1]]
    cm = core.reindex(days[rows], method="ffill").to_numpy()
    corem = pd.Series((cm[1:] / cm[:-1] - 1) * 100, index=me)
    say("\n② 每月选股组合（今天的日経225，前 K 只等权拿一个月，扣来回 0.25%）")
    for k in (4, 8):
        R = R2.sleeve_returns(C, rows, scores, k, ok)
        for era, (a, b) in ERAS.items():
            msk = (me >= pd.Timestamp(a)) & (me < pd.Timestamp(b))
            LC.assert_explore_dates(me[msk])
            ew = pd.Series(R["EW"], index=me)[msk]
            say(f"\n### K = {k} · {era}")
            say("| 组合 | 年化 | 最大回撤 | Calmar | 比等权好的月份 / 年份 | 比核心好的月份 |")
            say("|---|---|---|---|---|---|")
            for n in ["EW"] + list(scores):
                s = pd.Series(R[n], index=me)[msk]
                p = R2.perf(s)
                yb = s.groupby(s.index.year).sum() > ew.groupby(ew.index.year).sum()
                out["sleeve"][f"K{k}/{era}/{n}"] = {**p, "beat_y": [int(yb.sum()), int(len(yb))]}
                say(f"| {'等权' if n == 'EW' else n} | {p.get('cagr')}% | {p.get('dd')}% | {p.get('calmar')} | "
                    f"{'—' if n == 'EW' else f'{(s > ew).mean() * 100:.0f}% / {int(yb.sum())}/{len(yb)}'} | {(s > corem[msk]).mean() * 100:.0f}% |")
            pc = R2.perf(corem[msk])
            say(f"| 核心（不择时） | {pc.get('cagr')}% | {pc.get('dd')}% | {pc.get('calmar')} | — | — |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r5_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
