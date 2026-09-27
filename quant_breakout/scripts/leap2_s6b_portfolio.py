"""leap2_s6b_portfolio.py — 「选股本身的质的飞跃」第 S6 轮探索续：搜索里过筛选的搭配放进组合（只描述、不登记；E / J，Z 不看）。

S6（scripts/leap2_s6_combo.py，日経225 的全部突破 × 130 条规则两两搭配 ≈ 8,500 个组合）：过筛选 2 个（打乱结果的偶然基线平均 0.1 个、最多 2 个）：
  C1 日経225 离 200 日线 ≤ +4.828%（行情不过热）∧ 个股对美国 10 年利率周变化的 β ≤ −0.01162（利率升时跌、利率降时涨的票）
  C2 突破日量比 ≥ 2.184 ∧ 个股对日経225 的 β ≤ 0.7803（放量的、个别因素驱动的突破）
（阈值 = 搜索时 E + J 合起来的分位点，固定数字；β = 信号日所在周之前一周为止的 104 周回归，美国利率用再前一周的周变化。）
这里放进同一套 S0C2（日経225；买点 = 全部突破 ∧ 搭配；逐笔 = 组合里的个股交易），门槛 S5 的随机对照 = 全部突破按「股票 × 周」
随机保留同样比例、30 次；另看同一个搭配再加 W2（C1w / C2w）。
输出：var/out/leap2_s6b_portfolio.md / .json（只有统计）
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
import leap2_common as L2                                                    # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap2_s1_explore import targets                                         # noqa: E402
from leap_r11_explore import vr1                                             # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

TH = {"n225_ma200": 0.04828, "b_us10": -0.01162, "vr1": 2.184, "b_n225": 0.7803}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def weekly_betas(names: list[str]) -> dict[str, pd.DataFrame]:
    """yfinance 27 年的复权收盘 → 周 × 票 的 b_n225 与 b_us10（与 scripts/leap2_s6_features.py 同一算法）。"""
    import leap_data as LD
    from bullbear_study import load
    from leap2_s5_explore import rolling_betas, weekly
    data = LD.ohlcv(names)
    C = pd.DataFrame({t: data[t]["Close"] for t in names if t in data}).sort_index()
    Yw = C.resample("W-FRI").last().pct_change(fill_method=None).clip(-0.5, 0.5)
    X = pd.DataFrame({"n225": weekly(load("^N225", "1998-01-01")["Close"]).pct_change(),
                      "us10": weekly(load("^TNX", "1998-01-01")["Close"]).diff().shift(1)}).reindex(Yw.index)
    return {"b_n225": rolling_betas(Yw, X[["n225"]], None)["n225"], "b_us10": rolling_betas(Yw, X[["us10", "n225"]], "n225")["us10"]}


def daily_from_weekly(M: pd.DataFrame, t: str, days: pd.DatetimeIndex) -> np.ndarray:
    """每个交易日 d：d 所在周之前的那个周五为止最后一个周值（与指标表同一口径）。"""
    if t not in M.columns:
        return np.full(len(days), np.nan)
    wk = days.to_period("W-FRI").start_time - pd.Timedelta(days=1)
    i = M.index.searchsorted(wk.to_numpy(), side="right") - 1
    v = M[t].to_numpy(float)
    return np.where(i >= 0, v[np.clip(i, 0, len(v) - 1)], np.nan)


def main() -> int:
    from bullbear_study import load
    from leap2_s3_explore import asof_upto
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    B = weekly_betas(list(universe("JP", "broad")))
    n225 = load("^N225", "1998-01-01")["Close"]
    ma = n225 / n225.rolling(200, min_periods=150).mean() - 1
    say(f"# 「选股本身的质的飞跃」第 S6 轮探索续：搜索里过筛选的搭配放进组合（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s6b_portfolio.py 开头；门槛 scripts/leap2_common.py。各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔净收益 / 胜率。")
    out = {}
    for era in ("E", "J"):
        te = time.time()
        p = load_params(market="JP")
        ctx = LF.context(era)
        fw = LF.frames(ctx, p)
        base = LF.run(ctx, LF.runner(ctx, fw), fw, p)
        fa = LF.frames(ctx, SF.no_w2_params(p))
        run_fn = LF.runner(ctx, fa)
        w2 = LF.w2_keep(ctx, fa)
        keep = {}
        for t, df in fa.items():
            d = df.index
            m_ok = asof_upto(ma, d) <= TH["n225_ma200"]
            bu = daily_from_weekly(B["b_us10"], t, d)
            bn = daily_from_weekly(B["b_n225"], t, d)
            v = vr1(df)
            keep.setdefault("C1", {})[t] = m_ok & (np.nan_to_num(bu, nan=np.inf) <= TH["b_us10"])
            keep.setdefault("C2", {})[t] = (np.nan_to_num(v, nan=0.0) >= TH["vr1"]) & (np.nan_to_num(bn, nan=np.inf) <= TH["b_n225"])
        for k in ("C1", "C2"):
            keep[k + "w"] = {t: keep[k][t] & w2[t] for t in fa}
        lab = {"C1": "C1 行情不过热 ∧ 利率 β 低", "C2": "C2 突破日量比 ≥ 2.18 ∧ 市场 β ≤ 0.78", "C1w": "C1 + W2", "C2w": "C2 + W2"}
        res, pq = {"现行（W2 · 日経225）": base}, {}
        for k in ("C1", "C2", "C1w", "C2w"):
            frac = LF.keep_frac(fa, keep[k])
            res[lab[k]] = LF.run(ctx, run_fn, LF.with_mask(fa, keep[k]), p)
            q = LF.placebo_trades(ctx, run_fn, fa, p, frac, seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            pq[lab[k]] = {"frac": round(frac, 3), "win_q95": round(q["win"], 1), "mean_q95": round(q["mean"], 3)}
        b = {era: base[era]}
        say(f"\n## {era} — {targets(b, era)}（{time.time() - te:.0f}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 | 保留的信号（全部突破里） | 随机对照 95% 分位：胜率 / 每笔 |")
        say("|---|---|---|---|---|---|")
        for k, r in res.items():
            q = pq.get(k)
            fails = L2.s_fails({era: r[era]}, b, {era: {"win": q["win_q95"], "mean": q["mean_q95"]}}) if q else ["—"]
            ok = q and not [x for x in fails if x.split(" ")[1] == era]
            qs = f"{q['win_q95']:.1f}% / {q['mean_q95']:+.2f}%" if q else "—"
            say(f"| {k}{'（这个年代到门槛 S1〜S5）' if ok else ''} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} | "
                f"{(q['frac'] * 100):.0f}% | {qs} |" if q else f"| {k} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} | — | — |")
        out[era] = {"res": {k: {w: x for w, x in r.items() if not w.startswith("_")} for k, r in res.items()}, "placebo": pq}
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s6b_portfolio"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
