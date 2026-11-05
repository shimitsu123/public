"""ecurve_study.py — 「突破最近管不管用」的自我过滤：最近 60 天内完成的影子突破交易平均净收益（D60）够好才开新仓
（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：scripts/ecurve_explore.py（只用 2017-01〜2021-12；var/out/ecurve_explore.md）：D60 低的时候突破明显失败——
今天的日経225 的交易、影子池 = 时点 TOPIX 1000：D60 > 0 每笔 +0.63% vs ≤ 0 −0.74%（D60 最低三分之一胜率 18.0%、−1.92%，5 年里 4 年高 > 低）；
影子池 = 日経225：+0.63% vs −0.30%。按笔数的 R20 / R50 不一致（不用）。到现在几乎所有结果都「时代依赖」→ 用突破自己的近况判断现在是不是好时期。
这是看 2017〜2021 得出的 → 主判定放在 2006-10〜2016-09；2022 年以后也没看过。

一、定义：影子交易 = 影子池里所有现行突破信号各自独立的交易（每只票单独、扣成本；pit_retrain_study 同一套）；
  D60(d) = exit_date 在 (d − 60 天, d] 的影子交易的平均净收益（d 收盘时已知；不足 5 笔 → 缺值 → 不过滤）。
  影子池「窄」= 交易股票池本身（今天的日経225）；「宽」= 2006〜2016：日経225 + 扩大池 714 只（yfinance，今天的成分），
  2017〜2026：时点 TOPIX 1000（J-Quants）。
二、候选（其余 = var/sim.json 同一套 S0C2；个股 = 现行突破，信号日 D60 不够就不买）
  Q1 窄池 D60 > 0%；Q2 宽池 D60 > 0%；Q3 窄池 D60 > −1%；Q4 宽池 D60 > −1%
三、判定（都要满足才通过；与 breadth_study 同一套）
  E 主：2006-10〜2016-09 Calmar ≥ 现行 + 0.05；最大回撤不比现行深 2 pp 以上；两个半段各自 Calmar ≥ 现行
  P 随机对照：E 的 Calmar > 「按周整体抽签、保留同样比例的信号」30 次的 95% 分位
  J 次：2017-01〜2026-09 Calmar ≥ 现行
  另判「比 W2 更好」：E Calmar ≥ W2 + 0.05 且 J ≥ W2。结论的写法同 breadth_study。都只是提议：用户在对话里确认才改模拟盘。
四、另报（只描述）：逐笔保留组 / 过滤掉的组；2022-01〜2023-09 与 2023-10〜；每年的收益；被过滤的交易日比例。
五、局限：E 的影子池有幸存者偏差；宽池在实盘要每天多算 700〜1,000 只的影子交易（Mac 上的 J-Quants 日线可以）；税前。
登记前做过的检查：tests/test_ecurve_explore.py（D60 只用已卖出的）、tests/test_ecurve_study.py（过滤按日期、缺值不过滤）。
输出：var/out/ecurve_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import breadth_study as B                                                    # noqa: E402
import candle_data as CD                                                     # noqa: E402
import candle_portfolio as CP                                                # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import ecurve_explore as EX                                                  # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import wvol_study as W                                                       # noqa: E402
import wvol_wide as WW                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

CANDS = {"Q1": ("窄", 0.0, "窄池 D60 > 0%"), "Q2": ("宽", 0.0, "宽池 D60 > 0%"), "Q3": ("窄", -1.0, "窄池 D60 > −1%"), "Q4": ("宽", -1.0, "宽池 D60 > −1%")}
SEEDS = 30
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def d60(shadow: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    return EX.shadow_perf(shadow, days)["D60"]


def gate(df: pd.DataFrame, s: pd.Series, thr: float) -> np.ndarray:
    """保留：信号日 D60 > thr；缺值 → 保留。"""
    x = s.reindex(df.index).to_numpy(float)
    return ~np.isfinite(x) | (x > thr)


def main() -> int:
    from qbreak import wide_universe as WU
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/ecurve_study.py", "scripts/ecurve_explore.py"],
                                capture_output=True, text=True).stdout.strip())
    D = CD.load()
    p0 = load_params(market="JP")
    res, trd, rnd, frac = {}, {}, {}, {}
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols, win, ratio, start, end = list(range(len(names))), L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30"
            fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {}), P, days, names)
            narrow = CPH.trades(fr, p0, "2006-01-04")
            d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
            Pw, dw, nw = WW.panel(load_universe(WU.tickers(WU.load()), d21), "2005-09-01", "2016-11-30")
            fw = CS_.frames_from(Pw, dw, nw, list(range(len(nw))), p0, {})
            wide = pd.concat([narrow, CPH.trades(fw, p0, "2006-01-04")], ignore_index=True)
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end = L.J_WIN, "2017-01-04", None
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
            fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {}), P, days, names)
            narrow = CPH.trades(fr, p0, "2016-06-01")
            m2 = D["mem"]["U2"]
            f2 = CS_.frames_from(P, days, names, [j for j in range(len(names)) if m2[:, j].any()], p0, {"m": m2})
            f2 = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in f2.items()}
            wide = CPH.trades(f2, p0, "2016-06-01")
        for T in (narrow, wide):
            T["exit_date"] = pd.to_datetime(T["exit_date"])
        S = {"窄": d60(narrow, days), "宽": d60(wide, days)}
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        M = {t: {"W2": W.keep_mask(df["w5v"], W.CUT2, False), **{k: gate(df, S[pool], thr) for k, (pool, thr, _) in CANDS.items()}}
             for t, df in fr.items()}
        res[era] = {"现行": run(fr, p0)}
        for k in ("W2", *CANDS):
            res[era][k] = run({t: df.assign(entry=df["entry"].to_numpy(bool) & M[t][k]) for t, df in fr.items()}, p0)
        lo, hi = pd.Timestamp(start), (pd.Timestamp(end) if end else days[-1])
        n_all = sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool)).sum()) for df in fr.values())
        frac[era] = {k: sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool) & M[t][k]).sum()) for t, df in fr.items())
                     / max(n_all, 1) for k in ("W2", *CANDS)}
        if era == "E":
            for k in CANDS:
                rnd[k] = [run(B.week_lottery_all(fr, frac["E"][k], s), p0)["E"]["calmar"] for s in range(SEEDS)]
        T = CPH.trades(fr, p0, start)
        if len(T):
            T = T[(T["sig_date"] >= lo) & (T["sig_date"] <= hi)]
            km = {k: np.array([bool(M[t][k][fr[t].index.get_loc(d)]) for t, d in zip(T["ticker"], T["sig_date"])]) for k in ("W2", *CANDS)}
            trd[era] = {"全部": CS_.tstat(T), **{f"{k} 保留": CS_.tstat(T[km[k]]) for k in ("W2", *CANDS)},
                        **{f"{k} 过滤掉": CS_.tstat(T[~km[k]]) for k in ("W2", *CANDS)}}
    p95 = {k: float(np.quantile([L.MS._c(x) for x in rnd[k]], 0.95)) for k in CANDS}
    RE, RJ = res["E"], res["J"]
    B.CANDS, saved = {k: v[2] for k, v in CANDS.items()}, B.CANDS
    try:
        dec = B.decide(RE, RJ, p95)
    finally:
        B.CANDS = saved
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    lab = lambda k: k if k in ("现行", "W2") else f"{k} {CANDS[k][2]}"                                              # noqa: E731
    pct = lambda k, e: "100%" if k == "现行" else "{:.1f}%".format(frac[e][k] * 100)                                # noqa: E731
    say("# 「突破最近管不管用」的自我过滤（登记检验，2026-09-27）")
    say("规则见 scripts/ecurve_study.py 开头（先提交后运行）。S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say("\n## 主：2006-10〜2016-09（yfinance 今天的日経225）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 保留的信号 | 按周随机去掉同样比例 95% 分位 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in ("现行", "W2", *CANDS):
        r = RE[k]
        g = "—" if k in ("现行", "W2") else ("✓" if k in dec["passed"] else "✗")
        say(f"| {lab(k)} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | "
            f"{pct(k, 'E')} | {fa(p95.get(k), '{:.3f}')} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    say("\n## 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手；2022 年以后探索没用过）")
    say("| 方案 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 保留的信号 | 个股笔数 / 胜率 |")
    say("|---|---|---|---|---|---|")
    for k in ("现行", "W2", *CANDS):
        r = RJ[k]
        say(f"| {lab(k)} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {cell(r['V'])} | {cell(r['H'])} | {pct(k, 'J')} | "
            f"{r['trades']} / {fa(r.get('win'), '{:.1f}%')} |")
    for k, f in dec["fails"].items():
        if f:
            say(f"- {k}：" + "；".join(f))
    say("\n## 逐笔（每只票单独、扣成本；格式 = 笔数 / 胜率 / 每笔平均净收益 / 盈亏比）")
    say("| 组 | 2006-10〜2016-09 | 2017-01〜2026-09 |")
    say("|---|---|---|")
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])}"   # noqa: E731
    for k in ["全部"] + [f"{x} {y}" for x in ("W2", *CANDS) for y in ("保留", "过滤掉")]:
        say(f"| {k} | {c4(trd.get('E', {}).get(k, {}))} | {c4(trd.get('J', {}).get(k, {}))} |")
    say("\n## 每一年的收益（%，只描述）")
    ys = [str(y) for y in range(2006, 2027)]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ("现行", "W2", *CANDS):
        vals = {**{y: v for y, v in RE[k]["years"].items() if y <= "2016"}, **{y: v for y, v in RJ[k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    if dec["better_than_w2"]:
        b = dec["proposal"]
        say(f"\n**结论：{b} {CANDS[b][2]} 通过全部门槛、而且比 W2 更好 → 提议换成它（要你在对话里确认才改模拟盘）。**")
    elif dec["passed"]:
        say(f"\n**结论：{'、'.join(dec['passed'])} 通过门槛，但不比 W2 更好 → 提议：W2 或 {'、'.join(dec['passed'])}（不同的维度，由你选；确认才改模拟盘）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行；提议仍是 W2（等你确认）。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "E": RE, "J": RJ, "trades": trd, "random_E": rnd, "p95": p95, "frac": frac, **dec}
    fp = paths.out_dir() / "ecurve_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
