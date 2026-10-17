"""regime_exit_explore.py — 探索（只用 2017-01〜2026-09 的 J-Quants 数据；2006〜2016 不看）：按行情类型切换突破仓位的离场（2026-09-27）。

来由：exit_explore（var/out/exit_explore.md）里「跌破 5 日线就卖」在 2017〜2023 的震荡期更好、2023-10 以后的趋势行情里更差；
mtf_study、K 线研究也是「趋势类在强势行情里好、其他时候坏」→ 如果能事先知道现在是趋势还是震荡，就可以切换。
行情类型 = 日経225 的效率比 ER（Kaufman efficiency ratio）：|N 天涨跌| ÷ N 天每日涨跌绝对值之和（0〜1，高 = 单边趋势，低 = 来回震荡），
用当天收盘为止的数据。做法：
  ① 同一批突破（按「票 × 信号日」配对），「现行 + 收盘 < 5 日线就卖」减「现行」的每笔差，按信号日的 ER60 三分位、按时期分组；
  ② 条件离场：只在 ER60（当天）< 门槛时才用 5 日线离场（门槛 = 2017〜2026 ER60 的 1/3 分位、中位数），逐笔与组合。
输出：var/out/regime_exit_explore.md / .json（只有统计）
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
import exit_explore as XE                                                    # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

PERIODS = {"2017〜2021": ("2017-01-01", "2022-01-01"), "2022-01〜2023-09": ("2022-01-01", "2023-10-01"), "2023-10〜": ("2023-10-01", None)}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def efficiency_ratio(close: pd.Series, n: int) -> pd.Series:
    """|C_t − C_{t−n}| ÷ Σ|ΔC|（最近 n 天）；只用当天收盘为止。"""
    c = close.astype(float)
    num = (c - c.shift(n)).abs()
    den = c.diff().abs().rolling(n, min_periods=n).sum()
    return num / den.where(den > 0)


def market_er(days: pd.DatetimeIndex, n: int = 60) -> pd.Series:
    from bullbear_study import load
    nk = load("^N225", "2000-01-01")["Close"]
    er = efficiency_ratio(nk, n)
    return er.reindex(days.union(er.index)).ffill().reindex(days)


def cond_exit(fr: dict, er: pd.Series, thr: float) -> dict:
    """离场 = MACD 死叉 或（收盘 < 5 日线 且 当天 ER60 < thr）。"""
    out = {}
    for t, df in fr.items():
        low = (er.reindex(df.index).to_numpy(float) < thr)
        out[t] = df.assign(dead_cross=df["dead_cross"].to_numpy(bool) | (XE.below_ma(df["Close"], 5, 1) & low))
    return out


def paired(T0: pd.DataFrame, T1: pd.DataFrame) -> pd.DataFrame:
    a = T0.set_index(["ticker", "sig_date"])["net"]
    b = T1.set_index(["ticker", "sig_date"])["net"]
    j = pd.concat([a.rename("n0"), b.rename("n1")], axis=1, join="inner").reset_index()
    j["d"] = j["n1"] - j["n0"]
    return j


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    P, days, names = D["P"], D["days"], D["names"]
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    er = market_er(days, 60)
    ej = er[er.index >= pd.Timestamp("2017-01-01")].dropna()
    q1, q2 = float(ej.quantile(1 / 3)), float(ej.quantile(2 / 3))
    med = float(ej.median())
    out: dict = {"q": (q1, q2), "median": med}
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    say("# 探索：按行情类型（日経225 效率比 ER60）切换突破仓位的离场（只用 2017-01〜2026-09；2006〜2016 不看）")
    say(f"ER60 在 2017〜2026 的三分位点 {q1:.3f} / {q2:.3f}、中位数 {med:.3f}（0 = 来回震荡，1 = 单边）。")
    say("各时期 ER60 的平均：" + "、".join(f"{k} {ej[(ej.index >= pd.Timestamp(a)) & ((ej.index < pd.Timestamp(b)) if b else True)].mean():.3f}"
                                          for k, (a, b) in PERIODS.items()))
    for u in ("U2", "U0"):
        mem = D["mem"][u]
        cols = [j for j in range(len(names)) if mem[:, j].any()]
        fr = CS_.frames_from(P, days, names, cols, p0, {"m": mem})
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in fr.items()}
        T0 = CPH.trades(fr, p0, "2017-01-04")
        T5 = CPH.trades(XE.with_exit(fr, "S5"), p0, "2017-01-04")
        J = paired(T0, T5)
        J["er"] = er.reindex(pd.DatetimeIndex(J["sig_date"])).to_numpy(float)
        lab = "时点 TOPIX 1000" if u == "U2" else "今天的日経225"
        say(f"\n## {lab}：「+ 5 日线离场」− 「现行」的每笔差（pp，配对 {len(J)} 笔；括号 = 笔数）")
        say("| 信号日 ER60 | " + " | ".join(PERIODS) + " | 全部 |")
        say("|---|" + "---|" * (len(PERIODS) + 1))
        out[u] = {}
        for g, (a, b) in (("低（震荡）", (-1, q1)), ("中", (q1, q2)), ("高（趋势）", (q2, 2))):
            m = (J["er"] > a) & (J["er"] <= b)
            cells = []
            for k, (pa, pb) in PERIODS.items():
                mm = m & (J["sig_date"] >= pd.Timestamp(pa)) & ((J["sig_date"] < pd.Timestamp(pb)) if pb else True)
                cells.append((float(J.loc[mm, "d"].mean()) if mm.any() else float("nan"), int(mm.sum())))
            allc = (float(J.loc[m, "d"].mean()), int(m.sum()))
            out[u][g] = {"periods": cells, "all": allc}
            say(f"| {g} | " + " | ".join(f"{fa(v, '{:+.2f}')}（{n}）" for v, n in cells) + f" | {fa(allc[0], '{:+.2f}')}（{allc[1]}） |")
        say(f"\n{lab}：条件离场的逐笔（格式 = 笔数 / 胜率 / 每笔平均 / 盈亏比）")
        say("| 离场 | 全部 | " + " | ".join(PERIODS) + " |")
        say("|---|---|" + "---|" * len(PERIODS))
        c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])}"   # noqa: E731
        for nm, T in (("现行", T0), ("+ 5 日线（总是）", T5), (f"+ 5 日线（只在 ER60 < {q1:.3f}）", CPH.trades(cond_exit(fr, er, q1), p0, "2017-01-04")),
                      (f"+ 5 日线（只在 ER60 < {med:.3f}）", CPH.trades(cond_exit(fr, er, med), p0, "2017-01-04"))):
            say(f"| {nm} | {c4(CS_.tstat(T))} | " + " | ".join(c4(CS_.tstat(T, a, b)) for a, b in PERIODS.values()) + " |")
    say("\n## S0C2 组合（今天的日経225，J-Quants 真实一手；年化 / 最大回撤 / Calmar）")
    cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
    fr = CS_.frames_from(P, days, names, cols, p0, {})
    run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days),
                         {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}, L.J_WIN)
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("| 离场 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 |")
    say("|---|---|---|---|")
    out["port"] = {}
    for nm, f in (("现行", fr), ("+ 5 日线（总是）", XE.with_exit(fr, "S5")), (f"+ 5 日线（只在 ER60 < {q1:.3f}）", cond_exit(fr, er, q1)),
                  (f"+ 5 日线（只在 ER60 < {med:.3f}）", cond_exit(fr, er, med))):
        r = run(f, p0)
        out["port"][nm] = r
        say(f"| {nm} | {cell(r['J'])} | {cell(r['V'])} | {cell(r['H'])} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "regime_exit_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
