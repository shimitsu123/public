"""ndx_study.py — 核心仓位拿纳斯达克 100（NASDAQ-100）会不会比 S&P500 更好（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：核心（1655 = S&P500 + 美股牛熊择时）是组合收益的主要来源；以前比过核心「拿什么」（1329 / 各半 / 黄金 / 长债 / 双动量 / 对冲版），
没有比过纳指。最近 10 年纳指明显更强，但 2000〜2002 年科网泡沫破裂跌了约 80% → 不能只看最近。
纳指（^NDX，yfinance）从 1985-10 起有 → **主判定放在 1987-01〜2005-12**（这个项目从没用过的年代，含泡沫与崩盘；前一年给牛熊检测器预热）。
用户这一轮：「…不同的搭配…考虑没有考虑过的方法」。

一、资产（都换成日元）：S&P500 × USD/JPY（现行 1655）；纳指 × USD/JPY（东证有 2631.T 等纳指 ETF；这里合成，**不加股息**，比 S&P500 的估计股息更保守）
二、候选（美股熊市 → 现金，与现行相同）
  N1 核心换成纳指，牛熊仍按 S&P500 的判定
  N2 核心换成纳指，牛熊按纳指自己的判定（同一个检测器、同一组参数）
  N3 S&P500 / 纳指各半，牛熊按 S&P500
  「现行」= S&P500（1655），牛熊按 S&P500
三、判定
  P 主：1987-01〜2005-12，只有核心（日元计：USD/JPY = FRED DEXJPUS；前一天收盘的状态决定当天持仓；每次调整扣 0.1%）：
    Calmar ≥ 现行 + 0.05，最大回撤不比现行深 2 pp 以上，两个半段（1987〜1996 / 1997〜2005）各自 Calmar ≥ 现行
  E 次：2006-10〜2016-09 S0C2 组合 Calmar ≥ 现行；J 次：2017-01〜2026-09 S0C2 组合 Calmar ≥ 现行
  都满足 → 通过；多个 → 提议 P 的 Calmar 最高的。通过也只是提议（用户确认才改模拟盘；实盘还要让执行器会买纳指 ETF）。
四、局限：指数不含股息（S&P500 的只有核心回测也不含；组合里 1655 上市前的合成含 1.3%/年估计股息、纳指不含 → 对纳指偏保守）；税前。
登记前做过的检查：tests/test_ndx_study.py（只有核心的持仓与切换、另外的牛熊判定在引擎里生效）。
输出：var/out/ndx_study.md / .json（只有统计）
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
import candle_study as CS_                                                   # noqa: E402
import halloween_study as HW                                                 # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import refuge_study as RF                                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402

NQ = "2631.T"
CANDS = {"N1": "核心换成纳指（牛熊按 S&P500）", "N2": "核心换成纳指（牛熊按纳指）", "N3": "S&P500 / 纳指各半（牛熊按 S&P500）"}
CFG = {"N1": {"core": {NQ: 1.0}, "core_index": {NQ: "US"}, "core_mode": "split"},
       "N2": {"core": {NQ: 1.0}, "core_index": {NQ: "NQ"}, "core_mode": "split"},
       "N3": {"core": {"1655.T": 0.5, NQ: 0.5}, "core_index": {"1655.T": "US", NQ: "US"}, "core_mode": "split"}}
P_WIN = {"P": ("1987-01-01", "2006-01-01"), "P1": ("1987-01-01", "1997-01-01"), "P2": ("1997-01-01", "2006-01-01")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def core_mix(assets: dict[str, pd.Series], weights: dict[str, float], bear: dict[str, pd.Series]) -> pd.Series:
    """只有核心的净值：每个资产 × 权重，熊（按它自己的判定，前一天收盘）→ 那部分现金；每次持仓变化扣 0.1% × 变化的权重。"""
    idx = next(iter(assets.values())).index
    ret = pd.Series(0.0, index=idx)
    turn = pd.Series(0.0, index=idx)
    for k, px in assets.items():
        b = bear[k].reindex(idx).ffill().fillna(True).astype(bool)
        pos = ((~b).astype(float) * weights[k]).shift(1).fillna(0.0)
        ret += pos * px.pct_change().fillna(0.0)
        turn += pos.diff().abs().fillna(pos.abs())
    return (1 + ret - turn * HW.SWITCH_COST / 100).cumprod()


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak import factors
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/ndx_study.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True).stdout.strip())
    spx = load(*SYM["US"])["Close"]
    ndx_df = load("^NDX", "1985-01-01")
    ndx = ndx_df["Close"]
    d = load_config()["detector"]
    det = Detector(d["kind"], d["params"])
    bear_s = pd.Series(np.asarray(det.states(spx)) == BEAR, index=spx.index)
    bear_n = pd.Series(np.asarray(det.states(ndx)) == BEAR, index=ndx.index)
    fx = factors.fred("DEXJPUS", max_age_h=1e9)
    idx = ndx.index
    fxs = fx.reindex(idx.union(fx.index)).ffill().reindex(idx)
    S_j, N_j = (spx.reindex(idx.union(spx.index)).ffill().reindex(idx) * fxs).dropna(), (ndx * fxs).dropna()
    common = S_j.index.intersection(N_j.index)
    S_j, N_j = S_j.reindex(common), N_j.reindex(common)
    eqs = {"现行": core_mix({"S": S_j}, {"S": 1.0}, {"S": bear_s}),
           "N1": core_mix({"N": N_j}, {"N": 1.0}, {"N": bear_s}),
           "N2": core_mix({"N": N_j}, {"N": 1.0}, {"N": bear_n}),
           "N3": core_mix({"S": S_j, "N": N_j}, {"S": 0.5, "N": 0.5}, {"S": bear_s, "N": bear_s})}
    RP = {k: {w: HW.seg(e, a, b) for w, (a, b) in P_WIN.items()} for k, e in eqs.items()}
    D = CD.load()
    p0 = load_params(market="JP")
    fxy = load("JPY=X", "2000-01-01")
    fxy = fxy[(fxy["Close"] > 60) & (fxy["Close"] < 250)]["Close"]
    res = {}
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols, win, ratio, start, end = list(range(len(names))), L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30"
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: dd for t, dd in last.items() if dd < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end = L.J_WIN, "2017-01-04", None
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
        fr = CS_.frames_from(P, days, names, cols, p0, {})
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        nframe = RF.jpy_frame(ndx_df, fxy, days, 10.0)                            # 东证交易日 d = 前一个美国收盘 × 当天早上的汇率（每口 ÷ 10）
        res[era] = {"现行": run(fr, p0)}
        for c in CANDS:
            res[era][c] = run(fr, p0, cfg_over=CFG[c], extra_core={NQ: nframe}, extra_bear={"NQ": bear_n})
    fails, passed = {}, {}
    for c in CANDS:
        pf = HW.p_fails(RP[c], RP["现行"])
        pf = [x.replace("1950〜2005", "1987〜2005").replace("1950〜1977", "1987〜1996").replace("1978〜2005", "1997〜2005") for x in pf]
        ef = [] if L.MS._c(res["E"][c]["E"]["calmar"]) >= L.MS._c(res["E"]["现行"]["E"]["calmar"]) else \
            [f"2006〜2016 组合 Calmar {res['E'][c]['E']['calmar']} < 现行 {res['E']['现行']['E']['calmar']}"]
        jf = L.j_fails(res["J"][c], res["J"]["现行"])
        fails[c] = pf + ef + jf
        if not fails[c]:
            passed[c] = RP[c]
    best = max(passed, key=lambda k: (L.MS._c(passed[k]["P"]["calmar"]), -int(k[1:]))) if passed else None
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("# 核心仓位拿纳斯达克 100 会不会更好（登记检验，2026-09-27）")
    say("规则见 scripts/ndx_study.py 开头（先提交后运行）。各格 = 年化 / 最大回撤 / Calmar。")
    say("\n## 主：1987-01〜2005-12，只有核心（日元计、指数不含股息）")
    say("| 方案 | 1987〜2005 | 1987〜1996 | 1997〜2005 | 判定 |")
    say("|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        g = "—" if k == "现行" else ("✓" if not HW.p_fails(RP[k], RP["现行"]) else "✗")
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k]} | {cell(RP[k]['P'])} | {cell(RP[k]['P1'])} | {cell(RP[k]['P2'])} | {g} |")
    say("\n## 次：S0C2 组合（日元）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 |")
    say("|---|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        e, j = res["E"][k], res["J"][k]
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k]} | {cell(e['E'])} | {cell(e['E1'])} | {cell(e['E2'])} | {cell(j['J'])} | {cell(j['V'])} | {cell(j['H'])} |")
    for c, f in fails.items():
        if f:
            say(f"- {c}：" + "；".join(f))
    say("\n## 组合每一年的收益（%，只描述）")
    yl = [str(y) for y in range(2006, 2027)]
    say("| 方案 | " + " | ".join(yl) + " |")
    say("|---|" + "---|" * len(yl))
    for k in ["现行"] + list(CANDS):
        vals = {**{y: v for y, v in res["E"][k]["years"].items() if y <= "2016"}, **{y: v for y, v in res["J"][k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in yl) + " |")
    if best:
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；实盘还要让执行器会买纳指 ETF）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "core_only": RP, "E": res["E"], "J": res["J"], "fails": fails, "passed": list(passed), "proposal": best}
    fp = paths.out_dir() / "ndx_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
