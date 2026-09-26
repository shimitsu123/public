"""exit_explore.py — 探索（只用 2017-01〜2026-09 的 J-Quants 数据；2006〜2016 不看）：突破仓位的「卖顶」——
现行离场（MACD 死叉等）之外，再加「收盘跌破 N 日线就卖」会不会更好（2026-09-27）。

来由：现行离场 94% 是 MACD 死叉（平均持有约 10 天）；param_study 试过止损 / 止盈 / 跟踪止损 / 最长持有 / 时间止损，没有试过均线离场；
candle_posthoc 里押し目「回到 5 日线就卖」胜率各年代 58〜72%。用户：「…快到顶该卖了的转换点…」。
做法：把离场列 dead_cross 换成「MACD 死叉 或 收盘 < N 日均线」（N = 5 / 10 / 20），也试「连续 2 天收盘 < N 日线」；
对象 = 现行突破的独立交易（时点 TOPIX 1000、今天的日経225）与 S0C2 组合（今天的日経225）。只描述。
输出：var/out/exit_explore.md / .json（只有统计）
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
import candle_portfolio as CP                                                # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

RULES = {"X0": ("现行（MACD 死叉等）", None, 1), "S5": ("+ 收盘 < 5 日线", 5, 1), "S10": ("+ 收盘 < 10 日线", 10, 1),
         "S20": ("+ 收盘 < 20 日线", 20, 1), "S5x2": ("+ 连续 2 天收盘 < 5 日线", 5, 2), "S10x2": ("+ 连续 2 天收盘 < 10 日线", 10, 2)}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def below_ma(close: pd.Series, n: int, k: int) -> np.ndarray:
    """收盘 < n 日均线（含当天）连续 k 天。"""
    c = close.astype(float)
    b = (c < c.rolling(n, min_periods=n).mean()).astype(int)
    return (b.rolling(k, min_periods=k).sum() >= k).to_numpy(bool)


def with_exit(fr: dict, rule: str) -> dict:
    _, n, k = RULES[rule]
    if n is None:
        return fr
    return {t: df.assign(dead_cross=df["dead_cross"].to_numpy(bool) | below_ma(df["Close"], n, k)) for t, df in fr.items()}


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    P, days, names = D["P"], D["days"], D["names"]
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    c6 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])} / {s.get('hold', float('nan')):.1f} 天"   # noqa: E731
    out: dict = {}
    say("# 探索：突破仓位加「跌破 N 日线就卖」（只用 2017-01〜2026-09；2006〜2016 不看）")
    say("逐笔 = 每只票单独、扣成本；格式 = 笔数 / 胜率 / 每笔平均净收益 / 盈亏比 / 平均持有。")
    for u in ("U2", "U0"):
        mem = D["mem"][u]
        cols = [j for j in range(len(names)) if mem[:, j].any()]
        fr = CS_.frames_from(P, days, names, cols, p0, {"m": mem})
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in fr.items()}
        lab = "时点 TOPIX 1000" if u == "U2" else "今天的日経225"
        say(f"\n## {lab}：逐笔（2017-01〜2026-09 / 2017〜2021 / 2022-01〜2023-09 / 2023-10〜）")
        say("| 离场 | 全部 | 2017〜2021 | 2022-01〜2023-09 | 2023-10〜 | 每年比现行好的年数 |")
        say("|---|---|---|---|---|---|")
        base_y = None
        out[u] = {}
        for r in RULES:
            T = CPH.trades(with_exit(fr, r), p0, "2017-01-04")
            T["hold"] = T["hold_days"]
            st = lambda a, b: {**CS_.tstat(T, a, b), "hold": float(T[(T["sig_date"] >= pd.Timestamp(a)) & ((T["sig_date"] < pd.Timestamp(b)) if b else True)]["hold"].mean())}   # noqa: E731
            cells = [st("2017-01-01", None), st("2017-01-01", "2022-01-01"), st("2022-01-01", "2023-10-01"), st("2023-10-01", None)]
            yr = T.groupby(pd.DatetimeIndex(T["sig_date"]).year)["net"].mean()
            if base_y is None:
                base_y, better = yr, "—"
            else:
                better = f"{int((yr.reindex(base_y.index) > base_y).sum())} / {len(base_y)}"
            out[u][r] = {"cells": cells, "years": yr.to_dict()}
            say(f"| {RULES[r][0]} | " + " | ".join(c6(c) for c in cells) + f" | {better} |")
    say("\n## S0C2 组合（今天的日経225，J-Quants 真实一手；年化 / 最大回撤 / Calmar）")
    say("| 离场 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 个股笔数 / 胜率 / 平均持有 |")
    say("|---|---|---|---|---|")
    cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
    fr = CS_.frames_from(P, days, names, cols, p0, {})
    run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days),
                         {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}, L.J_WIN)
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    out["port"] = {}
    for r in RULES:
        res = run(with_exit(fr, r), p0)
        out["port"][r] = res
        say(f"| {RULES[r][0]} | {cell(res['J'])} | {cell(res['V'])} | {cell(res['H'])} | {res['trades']} / {fa(res.get('win'), '{:.1f}%')} / {fa(res.get('hold'), '{:.1f}')} 天 |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "exit_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
