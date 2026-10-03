"""breadth_study.py — 市场宽度确认的突破：日経225 成分里站上 50 日线的比例（A50）高时才买（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：scripts/breadth_explore.py（只用 2017-01〜2021-12；var/out/breadth_explore.md）：A50 最高三分之一时的突破两个股票池都更好
（时点 TOPIX 1000 +0.07% vs 其他约 −0.6% 每笔，今天的日経225 +0.74% vs −0.80%，两个都是 5 年里 4 年），其他宽度（站上 200 日线、
60 日新高、突破扎堆）不一致。用日経225 成分自己算的 A50 与 TOPIX 1000 的相关 0.96；2017〜2021 日経225 逐笔 A50 ≥ 0.6：+0.52% vs −0.86%、
≥ 0.7：+0.97% vs −0.78%。这是看 2017〜2021 得出的 → 主判定放在 2006-10〜2016-09；2022 年以后也没看过。
和现有的「量化状态层」（日経225 指数跌破 200 日线等 → 新仓 0 倍）不同：这里看的是有多少股票一起在涨（参与度），不是指数本身。

一、定义：A50(d) = 当天收盘时，交易股票池（今天的日経225 成分，有数据的）里收盘 > 自己 50 日均线的比例（只用当天为止）；缺值 → 不过滤。
二、候选（其余 = var/sim.json 同一套 S0C2；个股 = 现行突破再加过滤）
  B1 A50 ≥ 0.6 才买；B2 A50 ≥ 0.7 才买；B3 W2 ∧ A50 ≥ 0.6；B4 W2 ∧ A50 ≥ 0.7（W2 = 周线量比 ≥ 1.0，wvol_study）
三、判定（都要满足才通过）
  E 主：2006-10〜2016-09（yfinance 今天的日経225）Calmar ≥ 现行 + 0.05；最大回撤不比现行深 2 pp 以上；两个半段各自 Calmar ≥ 现行
  P 随机对照：E 的 Calmar > 「按周整体抽签、保留同样比例的信号」30 次（种子 0〜29）的 95% 分位（A50 是全市场的条件 → 随机也按整周去掉）
  J 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）Calmar ≥ 现行
  另判「比 W2 更好」：E Calmar ≥ W2 + 0.05 且 J ≥ W2。
  结论：通过且比 W2 更好 → 提议换成它（多个取 E Calmar 最高、一样取编号小的）；通过但不比 W2 好 → 两个都报告，提议仍是 W2 或它（B1 / B2 与 W2 是
  不同的维度，可以由用户选）；都没通过 → 维持现行，提议仍是 W2。都只是提议：用户在对话里确认才改模拟盘。
四、另报（只描述）：逐笔保留组 / 过滤掉的组；2022-01〜2023-09 与 2023-10〜（探索没用过）；每年的收益。
五、局限：E 的股票池有幸存者偏差（今天的成分 → 过去的 A50 可能偏高）；过滤按整段时间去掉交易 → 1655 比重变大（随机对照就是为这个）；税前。
登记前做过的检查：tests/test_breadth_study.py（A50 只用当天为止、缺值不过滤、按周抽签、判定）。
输出：var/out/breadth_study.md / .json（只有统计）
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
import candle_data as CD                                                     # noqa: E402
import candle_portfolio as CP                                                # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

CUTS = {"B1": 0.6, "B2": 0.7, "B3": 0.6, "B4": 0.7}
CANDS = {"B1": "A50 ≥ 0.6 才买", "B2": "A50 ≥ 0.7 才买", "B3": "W2 ∧ A50 ≥ 0.6", "B4": "W2 ∧ A50 ≥ 0.7"}
SEEDS = 30
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def a50(C: np.ndarray, mem: np.ndarray) -> np.ndarray:
    """日期 × 票 的收盘宽表 → 每天「成员里收盘 > 50 日均线」的比例（只用当天为止；没有成员有均线 → NaN）。"""
    ma = pd.DataFrame(C).rolling(50, min_periods=50).mean().to_numpy()
    ok = mem & np.isfinite(C) & np.isfinite(ma)
    with np.errstate(invalid="ignore"):
        up = (C > ma) & ok
    n = ok.sum(axis=1)
    return np.where(n > 0, up.sum(axis=1) / np.maximum(n, 1), np.nan)


def masks(df: pd.DataFrame, a: pd.Series) -> dict[str, np.ndarray]:
    x = a.reindex(df.index).to_numpy(float)
    k2 = W.keep_mask(df["w5v"], W.CUT2, False)
    out = {"W2": k2}
    for k, c in CUTS.items():
        kb = W.keep_mask(x, c, False)
        out[k] = kb & k2 if k in ("B3", "B4") else kb
    return out


def week_lottery_all(fr: dict, frac: float, seed: int) -> dict:
    """按周整体抽签（所有票同一周一起留或一起去），概率 frac 保留。"""
    rng = np.random.default_rng(seed)
    weeks = pd.PeriodIndex(sorted(set().union(*[set(df.index.to_period("W-FRI")) for df in fr.values()])))
    keep = pd.Series(rng.random(len(weeks)) < frac, index=weeks)
    return {t: df.assign(entry=df["entry"].to_numpy(bool) & keep.reindex(df.index.to_period("W-FRI")).to_numpy(bool)) for t, df in fr.items()}


def decide(RE: dict, RJ: dict, p95: dict) -> dict:
    c = L.MS._c
    fails, passed, better = {}, [], []
    for k in CANDS:
        f = (L.e_fails(RE[k], RE["现行"]) + ([] if c(RE[k]["E"]["calmar"]) > p95[k] else
                                             [f"2006〜2016 Calmar {RE[k]['E']['calmar']} ≤ 按周随机去掉同样比例的 95% 分位 {p95[k]:.3f}"])
             + L.j_fails(RJ[k], RJ["现行"]))
        fails[k] = f
        if not f:
            passed.append(k)
            if c(RE[k]["E"]["calmar"]) >= c(RE["W2"]["E"]["calmar"]) + L.CALMAR_UP and c(RJ[k]["J"]["calmar"]) >= c(RJ["W2"]["J"]["calmar"]):
                better.append(k)
    best = max(better, key=lambda k: (c(RE[k]["E"]["calmar"]), -int(k[1:]))) if better else None
    return {"fails": fails, "passed": passed, "better_than_w2": better, "proposal": best or ("W2 或 " + "、".join(passed) if passed else "W2")}


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/breadth_study.py"], capture_output=True, text=True).stdout.strip())
    D = CD.load()
    p0 = load_params(market="JP")
    res, trd, rnd, frac, amed = {}, {}, {}, {}, {}
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols, win, ratio, start, end = list(range(len(names))), L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30"
            mem = np.isfinite(P["C"])
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end = L.J_WIN, "2017-01-04", None
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
            mem = D["mem"]["U0"] & np.isfinite(P["C"])
        A = pd.Series(a50(P["C"], mem), index=days)
        lo, hi = pd.Timestamp(start), (pd.Timestamp(end) if end else days[-1])
        amed[era] = float(A[(A.index >= lo) & (A.index <= hi)].median())
        fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {}), P, days, names)
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        M = {t: masks(df, A) for t, df in fr.items()}
        res[era] = {"现行": run(fr, p0)}
        for k in ("W2", *CANDS):
            res[era][k] = run({t: df.assign(entry=df["entry"].to_numpy(bool) & M[t][k]) for t, df in fr.items()}, p0)
        n_all = sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool)).sum()) for df in fr.values())
        frac[era] = {k: sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool) & M[t][k]).sum()) for t, df in fr.items())
                     / max(n_all, 1) for k in ("W2", *CANDS)}
        if era == "E":
            for k in CANDS:
                rnd[k] = [run(week_lottery_all(fr, frac["E"][k], s), p0)["E"]["calmar"] for s in range(SEEDS)]
        T = CPH.trades(fr, p0, start)
        if len(T):
            T = T[(T["sig_date"] >= lo) & (T["sig_date"] <= hi)]
            km = {k: np.array([bool(M[t][k][fr[t].index.get_loc(d)]) for t, d in zip(T["ticker"], T["sig_date"])]) for k in ("W2", *CANDS)}
            trd[era] = {"全部": CS_.tstat(T), **{f"{k} 保留": CS_.tstat(T[km[k]]) for k in ("W2", *CANDS)},
                        **{f"{k} 过滤掉": CS_.tstat(T[~km[k]]) for k in ("W2", *CANDS)}}
    p95 = {k: float(np.quantile([L.MS._c(x) for x in rnd[k]], 0.95)) for k in CANDS}
    RE, RJ = res["E"], res["J"]
    dec = decide(RE, RJ, p95)
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    lab = lambda k: k if k in ("现行", "W2") else f"{k} {CANDS[k]}"                                                 # noqa: E731
    pct = lambda k, e: "100%" if k == "现行" else "{:.1f}%".format(frac[e][k] * 100)                                # noqa: E731
    say("# 市场宽度确认的突破（登记检验，2026-09-27）")
    say("规则见 scripts/breadth_study.py 开头（先提交后运行）。S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say(f"A50 的中位数：2006-10〜2016-09 {amed['E']:.3f}、2017-01〜2026-09 {amed['J']:.3f}")
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
        say(f"\n**结论：{b} {CANDS[b]} 通过全部门槛、而且比 W2 更好 → 提议换成它（要你在对话里确认才改模拟盘）。**")
    elif dec["passed"]:
        say(f"\n**结论：{'、'.join(dec['passed'])} 通过门槛，但不比 W2 更好 → 提议：W2 或 {'、'.join(dec['passed'])}（不同的维度，由你选；确认才改模拟盘）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行；提议仍是 W2（等你确认）。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "E": RE, "J": RJ, "trades": trd, "random_E": rnd, "p95": p95, "frac": frac, "a50_median": amed, **dec}
    fp = paths.out_dir() / "breadth_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
