"""ecurve_explore.py — 探索（只用 2017-01〜2021-12；2022 年以后与 2006〜2016 不看）：「突破最近管不管用」的自我过滤（equity-curve filter）。

来由：到现在几乎所有结果都是「时代依赖」——突破类在某些时期好、某些时期坏（mtf_study、K 线、离场、宽度）。如果「好 / 坏的时期」会持续一段，
那么最近完成的突破交易整体赚不赚钱，就能事先告诉我们现在是不是突破的好时期。
影子交易 = 同一股票池里所有现行突破信号各自独立的交易（不管组合有没有名额，每只票单独、扣成本）；
在信号日 d，只用 d 收盘之前已经卖出（exit_date ≤ d）的影子交易：
  R20  最近完成的 20 笔的平均净收益；R50 最近 50 笔；D60 最近 60 个自然日内完成的平均
看：这些量的三分位 → 这一笔突破的净收益（按年）；影子池 = 时点 TOPIX 1000（交易多）与今天的日経225（实盘股票池）。
输出：var/out/ecurve_explore.md / .json（只有统计）
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
from qbreak import paths                                                     # noqa: E402

T_END = pd.Timestamp("2022-01-01")
FEATS = {"R20": "最近完成的 20 笔平均", "R50": "最近完成的 50 笔平均", "D60": "最近 60 天内完成的平均"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def shadow_perf(shadow: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """每个日期 d：exit_date ≤ d 的影子交易里最近 20 / 50 笔、最近 60 天的平均净收益（按卖出日排序）。"""
    S = shadow.sort_values("exit_date")
    ex = pd.DatetimeIndex(S["exit_date"]).to_numpy()
    net = S["net"].to_numpy(float)
    cs = np.r_[0.0, np.cumsum(net)]
    d = pd.DatetimeIndex(dates).to_numpy()
    n = np.searchsorted(ex, d, side="right")                          # exit_date ≤ d 的笔数
    out = {}
    for k, w in (("R20", 20), ("R50", 50)):
        lo = np.maximum(n - w, 0)
        out[k] = np.where(n >= w, (cs[n] - cs[lo]) / np.maximum(n - lo, 1), np.nan)
    lo60 = np.searchsorted(ex, d - np.timedelta64(60, "D"), side="right")
    cnt = n - lo60
    out["D60"] = np.where(cnt >= 5, (cs[n] - cs[lo60]) / np.maximum(cnt, 1), np.nan)
    return pd.DataFrame(out, index=pd.DatetimeIndex(dates))


def main() -> int:
    t0 = time.time()
    import candle_data as CD
    import candle_posthoc as CPH
    import candle_study as CS_
    import pit_retrain_study as PRS
    from qbreak.trader import load_params
    D = CD.load()
    p0 = load_params(market="JP")
    P, days, names = D["P"], D["days"], D["names"]
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    TT = {}
    for u in ("U2", "U0"):
        mem = D["mem"][u]
        cols = [j for j in range(len(names)) if mem[:, j].any()]
        fr = CS_.frames_from(P, days, names, cols, p0, {"m": mem})
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in fr.items()}
        T = CPH.trades(fr, p0, "2016-06-01")                               # 影子交易从 2016 年中开始，2017 年初就有历史
        T["exit_date"] = pd.to_datetime(T["exit_date"])
        TT[u] = T
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}%"   # noqa: E731
    res: dict = {}
    say("# 探索：「突破最近管不管用」的自我过滤（只用 2017-01〜2021-12）")
    say("影子交易 = 同一股票池所有现行突破各自独立的交易（扣成本）；信号日只用那天收盘前已卖出的。每格 = 笔数 / 胜率 / 每笔平均净收益。")
    for u, shadow_u in (("U2", "U2"), ("U0", "U0"), ("U0", "U2")):
        T = TT[u]
        T = T[(T["sig_date"] >= pd.Timestamp("2017-01-01")) & (T["sig_date"] < T_END)].copy()
        X = shadow_perf(TT[shadow_u], pd.DatetimeIndex(T["sig_date"]))
        lab = ("时点 TOPIX 1000" if u == "U2" else "今天的日経225") + " 的交易，影子池 = " + ("时点 TOPIX 1000" if shadow_u == "U2" else "今天的日経225")
        say(f"\n## {lab}（{len(T)} 笔）")
        say("| 量 | 三分位点 | 低 | 中 | 高 | 高 − 低 | 高 > 低 的年数 | > 0 vs ≤ 0 |")
        say("|---|---|---|---|---|---|---|---|")
        res[f"{u}|{shadow_u}"] = {}
        for k in FEATS:
            x = X[k].to_numpy(float)
            ok = np.isfinite(x)
            q1, q2 = np.quantile(x[ok], [1 / 3, 2 / 3])
            g = {n: T[m] for n, m in (("低", ok & (x <= q1)), ("中", ok & (x > q1) & (x <= q2)), ("高", ok & (x > q2)))}
            s = {n: CS_.tstat(v) for n, v in g.items()}
            yrs = sum(1 for y in range(2017, 2022)
                      if g["高"][pd.DatetimeIndex(g["高"]["sig_date"]).year == y]["net"].mean() >
                      g["低"][pd.DatetimeIndex(g["低"]["sig_date"]).year == y]["net"].mean())
            pos, neg = CS_.tstat(T[ok & (x > 0)]), CS_.tstat(T[ok & (x <= 0)])
            diff = s["高"].get("mean", np.nan) - s["低"].get("mean", np.nan)
            res[f"{u}|{shadow_u}"][k] = {"q": (float(q1), float(q2)), "s": s, "diff": diff, "years_up": yrs, "pos": pos, "neg": neg}
            say(f"| {k} {FEATS[k]} | {q1:+.2f} / {q2:+.2f} | {c4(s['低'])} | {c4(s['中'])} | {c4(s['高'])} | {diff:+.2f} | {yrs} / 5 | "
                f"{c4(pos)} vs {c4(neg)} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "ecurve_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
