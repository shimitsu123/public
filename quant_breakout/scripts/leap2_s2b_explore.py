"""leap2_s2b_explore.py — 「选股本身的质的飞跃」第 S2 轮探索续：多年新高的突破放进组合（只描述、不登记；E / J，Z 不看）。

S2（scripts/leap2_s2_explore.py，单独交易、今天的成分）：突破当天收盘创 3 年 / 5 年新高 → 胜率两个年代都高 9〜12 pp，每笔 +0.5〜1.0 pp。
这里放进同一套 S0C2 组合（逐笔 = 组合里的个股交易），J 用時点 TOPIX 500（没有幸存者偏差）：
  特征 hi3y = 信号日收盘 ≥ 之前 750 个交易日收盘的最高（没有 750 天历史 → 不算）；hi5y 同样 1250 天。
  E 的历史用 yfinance 27 年（2000 年起）；J 只用 J-Quants（2016-09 起 → 3 年新高从 2019-09 才有、5 年新高从 2021-09 才有）。
  H1 全部突破（不加 W2）∧ 3 年新高；H2 W2 ∧ 3 年新高；H3 全部突破 ∧ 5 年新高；
  H4 H1 的卖法改成趋势式（不看日线死叉、跟踪止损 15%、最长 120 天；上方没有套牢盘的突破也许走得更远）；H5 H1 ∧ 突破日量比 ≥ 2。
股票池 UW（E = 今天的日経225 + T500x；J = 時点 TOPIX 500）；另报日経225（U0）的 H1。
输出：var/out/leap2_s2b_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import replace
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

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def multi_year_high(close: pd.Series, n: int) -> pd.Series:
    """每天：收盘 ≥ 之前 n 个交易日收盘的最高（不含当天；历史不满 n 天 → False）。"""
    prev = close.shift(1).rolling(n, min_periods=n).max()
    return (close >= prev) & prev.notna()


def hi_masks(fr: dict, closes: dict[str, pd.Series], n: int) -> dict[str, np.ndarray]:
    """closes = 每只票用来算新高的收盘序列（可以比指标表长）→ 对到指标表的日子。"""
    out = {}
    for t, df in fr.items():
        c = closes.get(t)
        out[t] = (multi_year_high(c, n).reindex(df.index).fillna(False).to_numpy(bool) if c is not None
                  else np.zeros(len(df), bool))
    return out


def trend_exit(p):
    return replace(p, exit_on_macd_dead_cross=False, trailing_stop_pct=15.0, trailing_arm_pct=0.0, max_hold_days=120, take_profit_pct=0.0)


def setting(era: str, uni: str) -> dict:
    import leap_data as LD
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    if uni == "U0":
        ctx = LF.context(era)
    else:
        ctx = LF.context("E", L2.uw_names()) if era == "E" else LF.context("J", jmem=L2.J_UW)
    fa = LF.frames(ctx, p0)
    fa = LF.with_mask(fa, LF.member_mask(ctx, fa))
    fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
    run_fn = LF.runner(ctx, fa)
    if era == "E":
        data = LD.ohlcv(list(fa))
        closes = {t: data[t]["Close"] for t in fa if t in data}
    else:
        closes = {t: df["Close"] for t, df in fa.items()}
    h3, h5 = hi_masks(fa, closes, 750), hi_masks(fa, closes, 1250)
    v2 = {t: np.nan_to_num(vr1(df), nan=0.0) >= 2 for t, df in fa.items()}
    res = {}
    if uni == "UW":
        res["H1 全部突破 ∧ 3 年新高"] = LF.run(ctx, run_fn, LF.with_mask(fa, h3), p)
        res["H2 W2 ∧ 3 年新高"] = LF.run(ctx, run_fn, LF.with_mask(fw, h3), p)
        res["H3 全部突破 ∧ 5 年新高"] = LF.run(ctx, run_fn, LF.with_mask(fa, h5), p)
        res["H4 H1，趋势式卖法"] = LF.run(ctx, run_fn, LF.with_mask(fa, h3), trend_exit(p))
        res["H5 H1 ∧ 突破日量比 ≥ 2"] = LF.run(ctx, run_fn, LF.with_mask(fa, {t: h3[t] & v2[t] for t in fa}), p)
    else:
        res["现行（W2 · 日経225）"] = LF.run(ctx, run_fn, fw, p)
        res["日経225 · H1 全部突破 ∧ 3 年新高"] = LF.run(ctx, run_fn, LF.with_mask(fa, h3), p)
    return {"res": res, "secs": round(time.time() - t0), "n": len(fa)}


def main() -> int:
    t0 = time.time()
    say(f"# 「选股本身的质的飞跃」第 S2 轮探索续：多年新高的突破放进组合（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s2b_explore.py 开头；门槛 scripts/leap2_common.py。各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔净收益 / 胜率。")
    out = {}
    for era in ("E", "J"):
        s0 = setting(era, "U0")
        base = {era: s0["res"]["现行（W2 · 日経225）"][era]}
        s1 = setting(era, "UW")
        say(f"\n## {era} — {targets(base, era)}（{s0['secs'] + s1['secs']}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|")
        allres = {**s0["res"], **s1["res"]}
        out[era] = {k: {w: x for w, x in r.items() if not w.startswith("_")} for k, r in allres.items()}
        for k, r in allres.items():
            ok = not [x for x in L2.s_fails({era: r[era]}, base, {era: {"win": -1e9, "mean": -1e9}}) if x.split(" ")[1] == era]
            say(f"| {k}{'（到门槛 S1〜S4）' if ok else ''} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s2b_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
