"""breadth_explore.py — 探索（只用 2017-01〜2021-12；2022 年以后与 2006〜2016 不看）：市场宽度（breadth）能不能分出好 / 坏的突破（2026-09-27）。

来由：以前的市场层只看指数本身（日経225 的 200 日线、离高点、波动 → 量化状态层；牛熊判定）；「有多少股票一起涨」（参与度）没有用过。
宽度（时点 TOPIX 1000 成员，当天收盘为止）：
  A50  站上 50 日均线的比例；A200 站上 200 日均线的比例；
  BO10 最近 10 个交易日出过现行突破信号的股票比例（突破扎堆 = 广泛上攻，或者过热）；
  NH20 创 60 日新高的比例（20 天平均）
对象：现行突破的独立交易（时点 TOPIX 1000、今天的日経225），按信号日的宽度三分位。
输出：var/out/breadth_explore.md / .json（只有统计）
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
FEATS = {"A50": "站上 50 日线的比例", "A200": "站上 200 日线的比例", "BO10": "最近 10 天出过突破信号的比例", "NH20": "创 60 日新高的比例（20 天平均）"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def breadth(C: np.ndarray, H: np.ndarray, mem: np.ndarray, sig: np.ndarray) -> pd.DataFrame:
    """日期 × 特征；C / H / mem / sig 是 日期 × 票 的宽表（sig = 现行突破信号）。只用当天为止的数据。"""
    Cd = pd.DataFrame(C)
    ma50 = Cd.rolling(50, min_periods=50).mean().to_numpy()
    ma200 = Cd.rolling(200, min_periods=200).mean().to_numpy()
    hi60 = pd.DataFrame(H).rolling(60, min_periods=60).max().to_numpy()
    ok = mem & np.isfinite(C)
    with np.errstate(invalid="ignore"):
        a50 = np.where(ok & np.isfinite(ma50), C > ma50, np.nan)
        a200 = np.where(ok & np.isfinite(ma200), C > ma200, np.nan)
        nh = np.where(ok & np.isfinite(hi60), H >= hi60, np.nan)
    bo = pd.DataFrame(sig & ok).rolling(10, min_periods=1).max().to_numpy()
    bo = np.where(ok, bo, np.nan)
    out = pd.DataFrame({"A50": np.nanmean(a50, axis=1), "A200": np.nanmean(a200, axis=1), "BO10": np.nanmean(bo, axis=1),
                        "NH20": pd.Series(np.nanmean(nh, axis=1)).rolling(20, min_periods=10).mean().to_numpy()})
    return out


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
    mem2 = D["mem"]["U2"]
    cols = [j for j in range(len(names)) if mem2[:, j].any()]
    fr_all = CS_.frames_from(P, days, names, cols, p0, {"m": mem2})
    sig = np.zeros_like(mem2, dtype=bool)
    col = {t: j for j, t in enumerate(names)}
    for t, df in fr_all.items():
        sig[days.get_indexer(df.index), col[t]] = df["entry"].to_numpy(bool)
    B = breadth(P["C"], P["H"], mem2, sig)
    B.index = days
    Bt = B[(B.index >= pd.Timestamp("2017-01-01")) & (B.index < T_END)]
    res: dict = {"summary": Bt.describe().to_dict()}
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}%"   # noqa: E731
    say("# 探索：市场宽度 → 突破的好坏（只用 2017-01〜2021-12）")
    say("宽度 = 时点 TOPIX 1000 成员里满足条件的比例（当天收盘为止）。每格 = 笔数 / 胜率 / 每笔平均净收益（独立逐笔、扣成本）。")
    say("2017〜2021 的中位数：" + "、".join(f"{k} {Bt[k].median():.3f}" for k in FEATS))
    for u in ("U2", "U0"):
        mem = D["mem"][u]
        fr = fr_all if u == "U2" else CS_.frames_from(P, days, names, [j for j in range(len(names)) if mem[:, j].any()], p0, {"m": mem})
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in fr.items()}
        T = CPH.trades(fr, p0, "2017-01-04")
        T = T[T["sig_date"] < T_END].copy()
        X = B.reindex(pd.DatetimeIndex(T["sig_date"]))
        lab = "时点 TOPIX 1000" if u == "U2" else "今天的日経225"
        say(f"\n## {lab}：{len(T)} 笔（2017〜2021）")
        say("| 宽度 | 三分位点 | 低 | 中 | 高 | 高 − 低 | 高 > 低 的年数 |")
        say("|---|---|---|---|---|---|---|")
        res[u] = {}
        for k in FEATS:
            x = X[k].to_numpy(float)
            ok = np.isfinite(x)
            q1, q2 = np.quantile(x[ok], [1 / 3, 2 / 3])
            g = {n: T[m] for n, m in (("低", ok & (x <= q1)), ("中", ok & (x > q1) & (x <= q2)), ("高", ok & (x > q2)))}
            s = {n: CS_.tstat(v) for n, v in g.items()}
            yrs = sum(1 for y in range(2017, 2022)
                      if g["高"][pd.DatetimeIndex(g["高"]["sig_date"]).year == y]["net"].mean() >
                      g["低"][pd.DatetimeIndex(g["低"]["sig_date"]).year == y]["net"].mean())
            diff = s["高"].get("mean", np.nan) - s["低"].get("mean", np.nan)
            res[u][k] = {"q": (float(q1), float(q2)), "s": s, "diff": diff, "years_up": yrs}
            say(f"| {k} {FEATS[k]} | {q1:.3f} / {q2:.3f} | {c4(s['低'])} | {c4(s['中'])} | {c4(s['高'])} | {diff:+.2f} | {yrs} / 5 |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "breadth_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
