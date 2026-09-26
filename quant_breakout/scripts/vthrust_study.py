"""vthrust_study.py — 放量突破的加强版：周线放量（W2）之外再加「突破日的量」或「20 天均量在放大」
（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：scripts/vol_explore.py（只用 2017-01〜2026-09；var/out/vol_explore.md）里，经典的「吸筹」指标（上涨日量 ÷ 下跌日量、蔡金资金流、OBV）
反而是高的更差；在周线量比之外还能分出好坏的只有「放量」类：突破日量比 VR1（信号日量 ÷ 前 20 天均量）≥ 3 与 20 天均量放大 VEXP ≥ 1
（W2 保留组里：时点 TOPIX 1000 每笔 +0.12% → W2 ∧ VR1≥3 +0.74% / W2 ∧ VEXP≥1 +0.36%；今天的日経225 +0.53% → +1.93% / +1.44%）。
这些是看 2017〜2026 得出的 → 主判定放在 2006-10〜2016-09。注意：param_study（2026-09-26）在 2006-10〜2015-12 试过「放量倍数 2.0」
（Calmar 0.283 vs 现行 0.259，没当选）→ 这个年代对「日线放量」不是完全没看过；3 倍与均量放大没试过。
用户这一轮：「…持续研究…如何能让策略达到登记门槛，并且一直推敲 进步 让预测更准确 不同的搭配…」。

一、候选（其余 = var/sim.json 同一套 S0C2；个股 = 现行突破再加过滤；特征缺值 → 不过滤）
  V1 W2 ∧ VR1 ≥ 3.0（周线放量 + 突破日 3 倍量）
  V2 W2 ∧ VEXP ≥ 1.0（周线放量 + 最近 20 天均量 ≥ 再之前 60 天均量）
  V3 VR1 ≥ 3.0（只看突破日 3 倍量）
  V4 VEXP ≥ 1.0（只看 20 天均量放大）
  特征定义 = scripts/vol_explore.py 的 vol_features（只用当天收盘为止的数据）；W2 = wvol_study 的周线量比 ≥ 1.0。
二、判定（都要满足才通过）
  E 主：2006-10〜2016-09（yfinance 今天的日経225）Calmar ≥ 现行 + 0.05；最大回撤不比现行深 2 pp 以上；两个半段各自 Calmar ≥ 现行
  P 随机对照（新）：E 的 Calmar > 「随机少做同样比例」30 次（按「股票 × 周」抽签，保留比例 = 该候选在 E 保留的信号比例，种子 0〜29）的 95% 分位
    → 排除「只是少做个股、1655 比重变大」
  J 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）Calmar ≥ 现行
  另外判断「比 W2 更好」：E Calmar ≥ W2 + 0.05 且 J Calmar ≥ W2。
  结论：通过且比 W2 更好 → 提议换成它（多个取 E Calmar 最高、一样取编号小的）；通过但不比 W2 好 → 提议仍是 W2；都没通过 → 提议仍是 W2。
  都只是提议：用户在对话里确认才改模拟盘。
三、另报（只描述）：逐笔（每只票单独、扣成本）保留组 / 过滤掉的组；每年的收益。
四、局限：E 的股票池有幸存者偏差、一手按调整后价；过滤越严交易越少（V1 在 2017〜2026 约只剩 1 / 10）→ 随机对照就是为这个；税前。
登记前做过的检查：tests/test_vthrust_study.py（特征对齐、缺值不过滤、判定逻辑）；tests/test_vol_explore.py（特征不偷看、手算）。
输出：var/out/vthrust_study.md / .json（只有统计）
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
import vol_explore as VE                                                     # noqa: E402
import wvol_placebo as WP                                                    # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

VR1_CUT, VEXP_CUT = 3.0, 1.0
CANDS = {"V1": "W2 ∧ 突破日量比 ≥ 3", "V2": "W2 ∧ 20 天均量放大 ≥ 1", "V3": "只看突破日量比 ≥ 3", "V4": "只看 20 天均量放大 ≥ 1"}
SEEDS = 30
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def with_vol(fr: dict, P: dict, days: pd.DatetimeIndex, names: list[str]) -> dict:
    F = VE.vol_features(P)
    col = {t: j for j, t in enumerate(names)}
    out = {}
    for t, df in fr.items():
        j = col[t]
        out[t] = df.assign(vr1=pd.Series(F["VR1"][:, j], index=days).reindex(df.index).to_numpy(float),
                           vexp=pd.Series(F["VEXP"][:, j], index=days).reindex(df.index).to_numpy(float))
    return out


def masks(df: pd.DataFrame) -> dict[str, np.ndarray]:
    k2 = W.keep_mask(df["w5v"], W.CUT2, False)
    kv = W.keep_mask(df["vr1"], VR1_CUT, False)
    ke = W.keep_mask(df["vexp"], VEXP_CUT, False)
    return {"W2": k2, "V1": k2 & kv, "V2": k2 & ke, "V3": kv, "V4": ke}


def decide(RE: dict, RJ: dict, p95: dict) -> dict:
    """RE / RJ：{方案: run 结果}（含 现行、W2、V1〜V4）；p95：{候选: 随机过滤 E Calmar 的 95% 分位}。"""
    c = L.MS._c
    fails, passed, better = {}, [], []
    for k in CANDS:
        f = (L.e_fails(RE[k], RE["现行"]) + ([] if c(RE[k]["E"]["calmar"]) > p95[k] else
                                             [f"2006〜2016 Calmar {RE[k]['E']['calmar']} ≤ 随机少做同样比例的 95% 分位 {p95[k]:.3f}"])
             + L.j_fails(RJ[k], RJ["现行"]))
        fails[k] = f
        if not f:
            passed.append(k)
            if c(RE[k]["E"]["calmar"]) >= c(RE["W2"]["E"]["calmar"]) + L.CALMAR_UP and c(RJ[k]["J"]["calmar"]) >= c(RJ["W2"]["J"]["calmar"]):
                better.append(k)
    best = max(better, key=lambda k: (c(RE[k]["E"]["calmar"]), -int(k[1:]))) if better else None
    return {"fails": fails, "passed": passed, "better_than_w2": better, "proposal": best or "W2"}


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/vthrust_study.py", "scripts/vol_explore.py", "scripts/wvol_placebo.py"],
                                capture_output=True, text=True).stdout.strip())
    D = CD.load()
    p0 = load_params(market="JP")
    res, trd, rnd, frac = {}, {}, {}, {}
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols, win, ratio, start, end = list(range(len(names))), L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30"
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end = L.J_WIN, "2017-01-04", None
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
        fr = with_vol(W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {}), P, days, names), P, days, names)
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        M = {t: masks(df) for t, df in fr.items()}
        res[era] = {"现行": run(fr, p0)}
        for k in ("W2", *CANDS):
            res[era][k] = run({t: df.assign(entry=df["entry"].to_numpy(bool) & M[t][k]) for t, df in fr.items()}, p0)
        lo, hi = pd.Timestamp(start), (pd.Timestamp(end) if end else days[-1])
        n_all = sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool)).sum()) for df in fr.values())
        frac[era] = {k: sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool) & M[t][k]).sum()) for t, df in fr.items())
                     / max(n_all, 1) for k in ("W2", *CANDS)}
        if era == "E":
            for k in CANDS:
                rnd[k] = [run(WP.week_lottery(fr, frac["E"][k], s), p0)["E"]["calmar"] for s in range(SEEDS)]
        T = CPH.trades(fr, p0, start)
        if len(T):
            T = T[(T["sig_date"] >= lo) & (T["sig_date"] <= hi)]
            ii = {t: fr[t].index for t in fr}
            km = {k: np.array([bool(M[t][k][ii[t].get_loc(d)]) for t, d in zip(T["ticker"], T["sig_date"])]) for k in ("W2", *CANDS)}
            trd[era] = {"全部": CS_.tstat(T), **{f"{k} 保留": CS_.tstat(T[km[k]]) for k in ("W2", *CANDS)},
                        **{f"{k} 过滤掉": CS_.tstat(T[~km[k]]) for k in ("W2", *CANDS)}}
    p95 = {k: float(np.quantile([L.MS._c(x) for x in rnd[k]], 0.95)) for k in CANDS}
    RE, RJ = res["E"], res["J"]
    dec = decide(RE, RJ, p95)
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    lab = lambda k: k if k in ("现行", "W2") else f"{k} {CANDS[k]}"                                                 # noqa: E731
    pct = lambda k, e: "100%" if k == "现行" else "{:.1f}%".format(frac[e][k] * 100)                                # noqa: E731
    say("# 放量突破的加强版（登记检验，2026-09-27）")
    say("规则见 scripts/vthrust_study.py 开头（先提交后运行）。S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say("\n## 主：2006-10〜2016-09（yfinance 今天的日経225）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 保留的信号 | 随机少做同样比例 95% 分位 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in ("现行", "W2", *CANDS):
        r = RE[k]
        g = "—" if k in ("现行", "W2") else ("✓" if k in dec["passed"] else "✗")
        say(f"| {lab(k)} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | "
            f"{pct(k, 'E')} | {fa(p95.get(k), '{:.3f}')} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    say("\n## 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）")
    say("| 方案 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 保留的信号 | 个股笔数 / 胜率 |")
    say("|---|---|---|---|---|---|")
    for k in ("现行", "W2", *CANDS):
        r = RJ[k]
        say(f"| {lab(k)} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {cell(r['V'])} | {cell(r['H'])} | "
            f"{pct(k, 'J')} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} |")
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
        say(f"\n**结论：{'、'.join(dec['passed'])} 通过门槛，但不比 W2 更好 → 提议仍是 W2（等你确认）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 提议仍是 W2（等你确认）；现行不变。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "E": RE, "J": RJ, "trades": trd, "random_E": rnd, "p95": p95, "frac": frac, **dec}
    fp = paths.out_dir() / "vthrust_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
