"""bullbear_study.py — 实时牛熊分界算法的校准（2005 年前）与样本外检验（2006 年后）。

事先登记的选择规则（跑之前写定）：
  训练期  S&P500 1951-01-01～2005-12-31，日経225 1966-01-01～2005-12-31（真值 = 20%/20% 事后标注）
  约束    两个指数都满足：①每年切换 ≤ 1.0 次 ②择时组合（牛持指数/熊持现金）Calmar ≥ 买入持有 Calmar
  目标    两个指数「平衡准确率」（牛召回与熊召回的平均）的均值最大
  平局    差 < 0.005 时取切换更少者
  样本外  2006-01-01～今天，同一套参数，两个指数分别报告
输出：var/out/bullbear_study.csv / .md，选定检测器写入 var/bullbear.json
"""
from __future__ import annotations

import itertools
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                      # noqa: E402
from qbreak.bullbear import Detector, date_phases, evaluate, hmm_fit, synthetic_inverse  # noqa: E402

TRAIN = {"US": ("1951-01-01", "2005-12-31"), "JP": ("1966-01-01", "2005-12-31")}
TEST = ("2006-01-01", None)
SYM = {"US": ("^GSPC", "1950-01-01"), "JP": ("^N225", "1965-01-01")}


def load(sym: str, start: str) -> pd.DataFrame:
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    h = yf.Ticker(sym).history(period="max", auto_adjust=True)
    h.index = h.index.tz_localize(None).normalize()
    h = h[~h.index.duplicated(keep="last")]
    return h[h.index >= start][["Open", "High", "Low", "Close", "Volume"]]


def candidates() -> list[Detector]:
    out = [Detector("ma_band", {"L": L, "b": b, "k": k})
           for L, b, k in itertools.product([100, 150, 200, 250], [0.0, 0.01, 0.02, 0.03, 0.05], [1, 3, 5, 10])]
    out += [Detector("dd_rally", {"x": x, "y": y})
            for x, y in itertools.product([0.07, 0.10, 0.12, 0.15, 0.20], [0.07, 0.10, 0.12, 0.15, 0.20])]
    out += [Detector("hybrid", {"L": L, "b": b, "x": x, "y": y})
            for L, b, x, y in itertools.product([150, 200], [0.0, 0.02], [0.05, 0.08, 0.10], [0.10, 0.15, 0.20])]
    out += [Detector("hmm", {"p_on": a, "p_off": c})
            for a, c in [(0.6, 0.4), (0.7, 0.3), (0.8, 0.3), (0.8, 0.2), (0.9, 0.3), (0.9, 0.1), (0.95, 0.2), (0.95, 0.05)]]
    return out


REFS = [Detector("ma_band", {"L": 200, "b": 0.0, "k": 1}), Detector("dd_rally", {"x": 0.20, "y": 0.20}),
        Detector("cross", {"fast": 50, "slow": 200})]


def main() -> int:
    data = {m: load(*SYM[m]) for m in ("US", "JP")}
    labels = {m: date_phases(d["Close"])[1] for m, d in data.items()}
    hmm = {}
    for m, d in data.items():
        r = d["Close"].pct_change().dropna() * 100
        a, b = TRAIN[m]
        hmm[m] = hmm_fit(r[(r.index >= a) & (r.index <= b)].values)
        print(m, "HMM", {k: np.round(v, 4).tolist() if isinstance(v, list) else v for k, v in hmm[m].items() if k != "ll"})
    rows = []
    for det in candidates() + REFS:
        row = {"detector": det.name, "kind": det.kind, "params": json.dumps(det.params)}
        for m, d in data.items():
            st = det.states(d["Close"], hmm[m])
            tr = evaluate(st, labels[m], d["Close"], *TRAIN[m])
            te = evaluate(st, labels[m], d["Close"], *TEST)
            for k, v in tr.items():
                row[f"{m}_tr_{k}"] = v
            for k, v in te.items():
                row[f"{m}_te_{k}"] = v
        rows.append(row)
    df = pd.DataFrame(rows)
    ok = np.ones(len(df), dtype=bool)
    for m in ("US", "JP"):
        ok &= (df[f"{m}_tr_switches_per_yr"] <= 1.0) & (df[f"{m}_tr_sw_calmar"] >= df[f"{m}_tr_bh_calmar"])
    df["eligible"] = ok & ~df["kind"].eq("cross")
    df["obj"] = (df["US_tr_bal_acc"] + df["JP_tr_bal_acc"]) / 2
    df["sw_mean"] = (df["US_tr_switches_per_yr"] + df["JP_tr_switches_per_yr"]) / 2
    el = df[df["eligible"]].sort_values(["obj", "sw_mean"], ascending=[False, True])
    best = None
    if len(el):
        top = el.iloc[0]
        ties = el[el["obj"] >= top["obj"] - 0.005].sort_values("sw_mean")
        best = ties.iloc[0]
    out = paths.out_dir() / "bullbear_study"
    df.to_csv(f"{out}.csv", index=False, encoding="utf-8-sig")
    show = ["detector", "eligible", "obj", "US_tr_bal_acc", "JP_tr_bal_acc", "US_tr_switches_per_yr", "JP_tr_switches_per_yr",
            "US_te_bal_acc", "JP_te_bal_acc", "US_te_bear_lag_med", "JP_te_bear_lag_med", "US_te_bull_lag_med", "JP_te_bull_lag_med",
            "US_te_false_alarms", "JP_te_false_alarms", "US_te_missed_bears", "JP_te_missed_bears",
            "US_te_sw_calmar", "US_te_bh_calmar", "JP_te_sw_calmar", "JP_te_bh_calmar",
            "US_te_inv_calmar", "JP_te_inv_calmar", "US_te_sw_dd", "US_te_bh_dd", "JP_te_sw_dd", "JP_te_bh_dd"]
    pd.set_option("display.width", 250)
    print("\n== 训练期入选前 12 ==")
    print(el[show].head(12).to_string(index=False))
    print("\n== 参照 ==")
    print(df[df["detector"].isin([d.name for d in REFS])][show].to_string(index=False))
    if best is not None:
        print("\n== 选定 ==", best["detector"])
        cfg = {"detector": {"kind": best["kind"], "params": json.loads(best["params"])},
               "hmm": hmm if best["kind"] == "hmm" else {},
               "selected_on": "train 1951/1966–2005, objective mean balanced accuracy, constraints switches≤1/yr & timing Calmar≥B&H",
               "test_2006_on": {m: {k.replace(f"{m}_te_", ""): best[k] for k in df.columns if k.startswith(f"{m}_te_")}
                                for m in ("US", "JP")}}
        (paths.home() / "bullbear.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    # 合成反向 vs 实际 ETF
    import yfinance as yf
    for m, etf, fee in (("JP", "1571.T", 0.88), ("US", "SH", 0.89)):
        syn = synthetic_inverse(data[m], fee)["Close"]
        act = yf.Ticker(etf).history(period="max", auto_adjust=True)["Close"]
        act.index = act.index.tz_localize(None).normalize()
        j = pd.concat([syn.pct_change(), act.pct_change()], axis=1, keys=["syn", "act"]).dropna()
        yrs = (j.index[-1] - j.index[0]).days / 365.25
        diff = (np.prod(1 + j["act"]) ** (1 / yrs) - np.prod(1 + j["syn"]) ** (1 / yrs)) * 100
        print(f"{m} 合成反向 vs {etf}: {j.index[0].date()}～ 日收益相关 {j['syn'].corr(j['act']):.4f}  年化差 {diff:+.2f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
