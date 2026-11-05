"""fxhedge_study.py — 核心仓位的汇率对冲切换：日元走强时改拿「对冲汇率的 S&P500」（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：1655 是不对冲的（S&P500 × USD/JPY）→ 日元急升时按日元计会亏（refuge_study：2008 年日元升值，外币资产按日元计都亏）。
以前的核心研究比过进出时点、黄金 / 长债、日本 / 双动量、季节，没有试过汇率对冲。东证有对冲版的 S&P500 ETF（例：2563.T），
对冲的成本 / 收益 ≈ 日本短期利率 − 美国短期利率。规则是事先按常识定的（汇率的 200 日线），不是从这里的数据挑出来的 → 直接登记。
数据：S&P500（^GSPC）、USD/JPY（FRED DEXJPUS，1971〜）、美国联邦基金利率（FRED DFF，1954〜）、日本无担保隔夜拆借利率（FRED IRSTCI01JPM156N，月，1985〜）
→ **主判定放在 1986-01〜2005-12**（这个项目从没用过的年代；只有核心、日元计）。

一、资产
  不对冲 = S&P500 × USD/JPY（现行 1655）；对冲 = S&P500 本地收益 + (日本短期利率 − 美国短期利率) ÷ 252（每天；利率用前一天 / 前一个月的值）
二、规则（美股牛熊照现行；熊市都是现金）
  F1 美股牛市时：USD/JPY 收盘 < 自己的 200 日均线（日元走强趋势）→ 拿对冲版；否则拿不对冲的 1655
  F2 美股牛市时一直拿对冲版（参照）
  「现行」= 美股牛市时一直拿不对冲的 1655
三、判定
  P 主：1986-01〜2005-12，只有核心（日元计、前一天收盘的状态决定当天持仓、每次调整扣 0.1%）：Calmar ≥ 现行 + 0.05，
    最大回撤不比现行深 2 pp 以上，两个半段（1986〜1995 / 1996〜2005）各自 Calmar ≥ 现行
  E 次：2006-10〜2016-09 S0C2 组合 Calmar ≥ 现行；J 次：2017-01〜2026-09 S0C2 组合 Calmar ≥ 现行
  都满足 → 通过；多个 → 提议 P 的 Calmar 最高的。通过也只是提议（用户确认才改模拟盘；实盘还要让执行器会买对冲版 ETF）。
四、局限：对冲版在组合里是合成的（东证对冲版 ETF 的信托报酬与对冲成本的实际值会不同）；日本利率是月平均；S&P500 价格指数不含股息；税前。
登记前做过的检查：tests/test_fxhedge_study.py（对冲版的计算、日元走强判定只用当天为止、核心目标切换）。
输出：var/out/fxhedge_study.md / .json（只有统计）
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

HEDGED = "2563.T"
CANDS = {"F1": "日元走强（USD/JPY < 200 日线）时拿对冲版", "F2": "一直拿对冲版（参照）"}
P_WIN = {"P": ("1986-01-01", "2006-01-01"), "P1": ("1986-01-01", "1996-01-01"), "P2": ("1996-01-01", "2006-01-01")}
CFG = {"F1": {"core": {"1655.T": 1.0, HEDGED: 1.0}, "core_index": {"1655.T": "UH", HEDGED: "HG"}, "core_mode": "follow"},
       "F2": {"core": {HEDGED: 1.0}, "core_index": {HEDGED: "US"}, "core_mode": "split"}}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def hedged_index(spx: pd.Series, us_rate: pd.Series, jp_rate: pd.Series) -> pd.Series:
    """对冲版：每天 S&P500 本地收益 + (日本 − 美国 短期利率)/252；美国利率用前一天、日本月利率用前一个月的值（保守，不偷看）。"""
    idx = spx.index
    us = us_rate.shift(1).reindex(idx.union(us_rate.index)).ffill().reindex(idx) / 100
    jm = jp_rate.copy()
    jm.index = jm.index + pd.offsets.MonthBegin(1)                              # 月平均：下个月初起才用
    jp = jm.reindex(idx.union(jm.index)).ffill().reindex(idx) / 100
    carry = (jp - us).fillna(0.0) / 252
    r = spx.pct_change().fillna(0.0)
    return (1 + r + carry).cumprod() * float(spx.iloc[0])


def yen_strong(fx: pd.Series, n: int = 200) -> pd.Series:
    """USD/JPY 收盘 < n 日均线 → True（日元走强趋势）；只用当天为止。"""
    ma = fx.rolling(n, min_periods=n).mean()
    return (fx < ma) & ma.notna()


def core_only(unh: pd.Series, hed: pd.Series, bear: pd.Series, use_hedge: pd.Series) -> pd.Series:
    """只有核心的净值：前一天收盘的状态决定当天持仓（熊 → 现金；牛 → 对冲或不对冲），每次调整扣 0.1%。"""
    idx = unh.index
    b = bear.reindex(idx).ffill().fillna(False).astype(bool)
    h = use_hedge.reindex(idx).ffill().fillna(False).astype(bool)
    state = np.where(b, 0, np.where(h, 2, 1))                                  # 0 现金、1 不对冲、2 对冲
    st = pd.Series(state, index=idx).shift(1).fillna(0).astype(int)
    ru, rh = unh.pct_change().fillna(0.0), hed.pct_change().fillna(0.0)
    ret = np.where(st == 1, ru, np.where(st == 2, rh, 0.0))
    chg = (st != st.shift(1).fillna(0)).astype(float) * HW.SWITCH_COST / 100
    return pd.Series(np.cumprod(1 + ret - chg.to_numpy()), index=idx)


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak import factors
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/fxhedge_study.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True).stdout.strip())
    spx = load(*SYM["US"])["Close"]
    fx = factors.fred("DEXJPUS", max_age_h=1e9)
    us_r, jp_r = factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9)
    d = load_config()["detector"]
    bear = pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(spx)) == BEAR, index=spx.index)
    ys = yen_strong(fx)
    hed = hedged_index(spx, us_r, jp_r)
    fxs = fx.reindex(spx.index.union(fx.index)).ffill().reindex(spx.index)
    unh = (spx * fxs).dropna()
    hedp = hed.reindex(unh.index)
    RP = {"现行": None, "F1": None, "F2": None}
    eqs = {"现行": core_only(unh, hedp, bear, pd.Series(False, index=unh.index)),
           "F1": core_only(unh, hedp, bear, ys.reindex(unh.index.union(ys.index)).ffill().reindex(unh.index).fillna(False)),
           "F2": core_only(unh, hedp, bear, pd.Series(True, index=unh.index))}
    RP = {k: {w: HW.seg(e, a, b) for w, (a, b) in P_WIN.items()} for k, e in eqs.items()}
    D = CD.load()
    p0 = load_params(market="JP")
    res = {}
    hdf = pd.DataFrame({"Open": hed, "High": hed, "Low": hed, "Close": hed, "Volume": 1e9})
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
        hframe = RF.jpy_frame(hdf, pd.Series(1.0, index=hdf.index), days, 1.0)   # 东证交易日 d = 前一个美国收盘的对冲版
        res[era] = {"现行": run(fr, p0)}
        res[era]["F1"] = run(fr, p0, cfg_over=CFG["F1"], extra_core={HEDGED: hframe}, yen_strong=ys)
        res[era]["F2"] = run(fr, p0, cfg_over=CFG["F2"], extra_core={HEDGED: hframe})
    fails, passed = {}, {}
    for c in CANDS:
        pf = HW.p_fails({"P": RP[c]["P"], "P1": RP[c]["P1"], "P2": RP[c]["P2"]}, {"P": RP["现行"]["P"], "P1": RP["现行"]["P1"], "P2": RP["现行"]["P2"]})
        pf = [x.replace("1950〜2005", "1986〜2005").replace("1950〜1977", "1986〜1995").replace("1978〜2005", "1996〜2005") for x in pf]
        ef = [] if L.MS._c(res["E"][c]["E"]["calmar"]) >= L.MS._c(res["E"]["现行"]["E"]["calmar"]) else \
            [f"2006〜2016 组合 Calmar {res['E'][c]['E']['calmar']} < 现行 {res['E']['现行']['E']['calmar']}"]
        jf = L.j_fails(res["J"][c], res["J"]["现行"])
        fails[c] = pf + ef + jf
        if not fails[c]:
            passed[c] = RP[c]
    best = max(passed, key=lambda k: (L.MS._c(passed[k]["P"]["calmar"]), -int(k[1:]))) if passed else None
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    ysh = {w: float(ys[(ys.index >= pd.Timestamp(a)) & (ys.index < pd.Timestamp(b))].mean()) for w, (a, b) in
           {"1986〜2005": ("1986-01-01", "2006-01-01"), "2006〜2016": ("2006-10-01", "2016-10-01"), "2017〜2026": ("2017-01-01", "2027-01-01")}.items()}
    say("# 核心仓位的汇率对冲切换（登记检验，2026-09-27）")
    say("规则见 scripts/fxhedge_study.py 开头（先提交后运行）。各格 = 年化 / 最大回撤 / Calmar。")
    say("日元走强（USD/JPY < 200 日线）的日子比例：" + "、".join(f"{k} {v * 100:.0f}%" for k, v in ysh.items()))
    say("\n## 主：1986-01〜2005-12，只有核心（日元计、现行美股牛熊择时）")
    say("| 方案 | 1986〜2005 | 1986〜1995 | 1996〜2005 | 判定 |")
    say("|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        g = "—" if k == "现行" else ("✓" if not [x for x in fails[k] if x.startswith("19")] else "✗")
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
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；实盘还要让执行器会买对冲版 ETF）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "core_only": RP, "E": res["E"], "J": res["J"], "fails": fails, "passed": list(passed), "proposal": best,
           "yen_strong_share": ysh}
    fp = paths.out_dir() / "fxhedge_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
