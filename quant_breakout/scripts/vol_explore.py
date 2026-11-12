"""vol_explore.py — 探索（只用 2017-01〜2026-09 的 J-Quants 数据；2006〜2016 完全不看，留给登记后的主判定）：
「量」的其他特征能不能在周线量比（W2）之外再分出好 / 坏的突破（2026-09-27）。

来由：到现在为止两期都成立的个股特征只有「量」（周线量比、日线量比）→ 试没有试过的量的形状：
  UD50  上涨日成交量 ÷ 下跌日成交量（信号日之前 50 天；> 1 = 吸筹 accumulation）
  CMF20 蔡金资金流 Chaikin Money Flow（20 天，收在当天振幅上半部的量 − 下半部的量）
  OBV20 能量潮 On-Balance Volume 20 天的变化 ÷（20 × 均量）
  DRY20 信号日之前 20 天下跌日的平均量 ÷ 之前 60 天均量（卖压干涸）
  VEXP  最近 20 天均量 ÷ 再之前 60 天均量（量在放大）
  VR1   信号日的量 ÷ 之前 20 天均量（日线量比）
  W5v   周线量比（最近完成的一周 ÷ 之前 10 周平均；W2 用的）
对象：现行突破的独立交易（每只票单独、扣成本；pit_retrain_study 同一套），时点 TOPIX 1000（U2，主要）与今天的日経225（U0）。
输出：var/out/vol_explore.md / .json（只有统计）
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
import candle_data as CD                                                     # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

FEATS = {"UD50": "上涨日量 ÷ 下跌日量（前 50 天）", "CMF20": "蔡金资金流（20 天）", "OBV20": "OBV 20 天变化 ÷ 20×均量",
         "DRY20": "前 20 天下跌日均量 ÷ 前 60 天均量", "VEXP": "20 天均量 ÷ 再之前 60 天均量", "VR1": "信号日量 ÷ 前 20 天均量",
         "W5v": "周线量比"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def vol_features(P: dict) -> dict[str, np.ndarray]:
    """T × N 的特征面板；只用当天收盘为止的数据。"""
    C, H, L, V = (pd.DataFrame(np.asarray(P[k], float)) for k in ("C", "H", "L", "V"))
    dC = C.diff()
    up, dn = dC > 0, dC < 0
    Vu, Vd = V.where(up, 0.0), V.where(dn, 0.0)
    ud = Vu.shift(1).rolling(50, min_periods=40).sum() / Vd.shift(1).rolling(50, min_periods=40).sum()
    rng = H - L
    mfm = (((C - L) - (H - C)) / rng.where(rng > 0)).fillna(0.0)
    cmf = (mfm * V).rolling(20, min_periods=15).sum() / V.rolling(20, min_periods=15).sum()
    obv = (np.sign(dC).fillna(0.0) * V.fillna(0.0)).cumsum()
    obv20 = (obv - obv.shift(20)) / (V.rolling(20, min_periods=15).mean() * 20)
    dry = (Vd.shift(1).rolling(20, min_periods=15).sum() / dn.shift(1).astype(float).rolling(20, min_periods=15).sum()
           / V.shift(1).rolling(60, min_periods=45).mean())
    vexp = V.rolling(20, min_periods=15).mean() / V.shift(20).rolling(60, min_periods=45).mean()
    vr1 = V / V.shift(1).rolling(20, min_periods=15).mean()
    ok = C.notna()
    out = {"UD50": ud, "CMF20": cmf, "OBV20": obv20, "DRY20": dry, "VEXP": vexp, "VR1": vr1}
    return {k: v.where(ok).replace([np.inf, -np.inf], np.nan).to_numpy(float) for k, v in out.items()}


def attach(T: pd.DataFrame, F: dict, days: pd.DatetimeIndex, names: list[str], fr: dict) -> pd.DataFrame:
    col = {t: j for j, t in enumerate(names)}
    ii = days.get_indexer(pd.DatetimeIndex(T["sig_date"]))
    jj = np.array([col[t] for t in T["ticker"]])
    T = T.copy()
    for k, a in F.items():
        T[k] = a[ii, jj]
    T["W5v"] = [fr[t]["w5v"].get(d, np.nan) for t, d in zip(T["ticker"], T["sig_date"])]
    T["year"] = pd.DatetimeIndex(T["sig_date"]).year
    return T


def tert(T: pd.DataFrame, k: str) -> dict:
    x = T[k].to_numpy(float)
    ok = np.isfinite(x)
    q1, q2 = np.quantile(x[ok], [1 / 3, 2 / 3])
    g = {"低": T[ok & (x <= q1)], "中": T[ok & (x > q1) & (x <= q2)], "高": T[ok & (x > q2)]}
    s = {n: CS_.tstat(d) for n, d in g.items()}
    yrs = [(y, g["高"][g["高"]["year"] == y]["net"].mean() - g["低"][g["低"]["year"] == y]["net"].mean()) for y in sorted(T["year"].unique())]
    yrs = [(y, v) for y, v in yrs if np.isfinite(v)]
    return {"q": (float(q1), float(q2)), "s": s, "diff": s["高"].get("mean", np.nan) - s["低"].get("mean", np.nan),
            "years_up": sum(v > 0 for _, v in yrs), "years": len(yrs)}


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    P, days, names = D["P"], D["days"], D["names"]
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    F = vol_features(P)
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}%"   # noqa: E731
    res: dict = {}
    say("# 探索：量的其他特征（只用 2017-01〜2026-09；2006〜2016 不看）")
    say("对象 = 现行突破的独立交易（每只票单独、扣成本）。每格 = 笔数 / 胜率 / 每笔平均净收益。「高 − 低」= 最高三分之一 − 最低三分之一 的每笔平均差。")
    Ts = {}
    for u in ("U2", "U0"):
        mem = D["mem"][u]
        cols = [j for j in range(len(names)) if mem[:, j].any()]
        fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {"m": mem}), P, days, names)
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in fr.items()}
        T = CPH.trades(fr, p0, "2017-01-04")
        Ts[u] = T = attach(T, F, days, names, fr)
        lab = "时点 TOPIX 1000" if u == "U2" else "今天的日経225"
        say(f"\n## {lab}：{len(T)} 笔（全部 {c4(CS_.tstat(T))}）")
        say("| 特征 | 三分位点 | 低 | 中 | 高 | 高 − 低 | 高 > 低 的年数 | W2 保留组里 高 − 低 |")
        say("|---|---|---|---|---|---|---|---|")
        keep = W.keep_mask(T["W5v"].to_numpy(float), W.CUT2, False)
        res[u] = {}
        for k in FEATS:
            r = tert(T, k)
            rk = tert(T[keep], k) if k != "W5v" else {"diff": np.nan}
            res[u][k] = {"all": r, "w2": rk}
            say(f"| {k} {FEATS[k]} | {r['q'][0]:.3f} / {r['q'][1]:.3f} | {c4(r['s']['低'])} | {c4(r['s']['中'])} | {c4(r['s']['高'])} | "
                f"{r['diff']:+.2f} | {r['years_up']} / {r['years']} | {rk['diff']:+.2f} |")
    say("\n## 相关（时点 TOPIX 1000 的交易，Spearman）")
    T = Ts["U2"]
    cm = T[list(FEATS)].rank().corr()
    say("| | " + " | ".join(FEATS) + " |")
    say("|---|" + "---|" * len(FEATS))
    for a in FEATS:
        say(f"| {a} | " + " | ".join(f"{cm.loc[a, b]:+.2f}" for b in FEATS) + " |")
    say("\n## 整数门槛（时点 TOPIX 1000 / 今天的日経225；每格 = 保留组 笔数 / 胜率 / 每笔，过滤掉的组）")
    grid = {"UD50": (1.0, 1.2, 1.5), "CMF20": (0.0, 0.1, 0.2), "OBV20": (0.0, 0.1, 0.2), "DRY20": (0.8, 1.0), "VEXP": (1.0, 1.2, 1.5), "VR1": (2.0, 3.0)}
    say("| 规则 | TOPIX 1000 保留 | TOPIX 1000 过滤掉 | 日経225 保留 | 日経225 过滤掉 | W2 ∧ 规则（TOPIX 1000） | W2 ∧ 规则（日経225） |")
    say("|---|---|---|---|---|---|---|")
    res["grid"] = {}
    for k, cuts in grid.items():
        for c in cuts:
            row = []
            for u in ("U2", "U0"):
                T = Ts[u]
                x = T[k].to_numpy(float)
                keep = ~np.isfinite(x) | ((x <= c) if k == "DRY20" else (x >= c))
                row.append((CS_.tstat(T[keep]), CS_.tstat(T[~keep])))
            both = []
            for u in ("U2", "U0"):
                T = Ts[u]
                x = T[k].to_numpy(float)
                keep = (~np.isfinite(x) | ((x <= c) if k == "DRY20" else (x >= c))) & W.keep_mask(T["W5v"].to_numpy(float), W.CUT2, False)
                both.append(CS_.tstat(T[keep]))
            res["grid"][f"{k}|{c}"] = {"U2": row[0], "U0": row[1], "w2_and": both}
            op = "≤" if k == "DRY20" else "≥"
            say(f"| {k} {op} {c} | {c4(row[0][0])} | {c4(row[0][1])} | {c4(row[1][0])} | {c4(row[1][1])} | {c4(both[0])} | {c4(both[1])} |")
    w2 = {u: CS_.tstat(Ts[u][W.keep_mask(Ts[u]["W5v"].to_numpy(float), W.CUT2, False)]) for u in ("U2", "U0")}
    say(f"| （参照）只有 W2 | {c4(w2['U2'])} | — | {c4(w2['U0'])} | — | — | — |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "vol_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
