"""halloween_study.py — 核心仓位的季节性：5〜10 月减仓（Halloween 效应 / Sell in May）（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：核心（1655 = S&P500 + 美股牛熊择时）是组合收益的主要来源；以前的核心研究只比「什么时候进出（牛熊）」「拿什么（黄金 / 长债 / 日本 / 双动量）」，
没试过季节。Halloween 效应是文献上跨很多市场、很长时间都被报告过的现象（11〜4 月的收益高于 5〜10 月），不是从这里的数据挑出来的 → 直接登记。
S&P500（^GSPC）从 1950 年就有 → **主判定放在 1950-01〜2005-12**（这个项目从没用过的年代）。用户这一轮：「…不同的搭配…考虑没有考虑过的方法」。

一、规则（牛熊判定照现行：var/bullbear.json 的检测器，美股熊市 → 核心 0）
  美股牛市时核心的比例：H1 5〜10 月 50%、11〜4 月 100%；H2 5〜10 月 0%、11〜4 月 100%。「现行」= 牛市全年 100%。
  月份按决策日（收盘）算；引擎的 core_expo（非熊市时核心目标再乘这个比例）。
二、判定
  P 主：1950-01〜2005-12，只有核心（S&P500 价格指数、美元、收盘到收盘、前一天收盘的状态决定当天持仓、每次调整扣 0.1%）：
    Calmar ≥ 现行 + 0.05，最大回撤不比现行深 2 pp 以上，两个半段（1950〜1977 / 1978〜2005）各自 Calmar ≥ 现行
  E 次：2006-10〜2016-09 S0C2 组合（yfinance 今天的日経225，日元）Calmar ≥ 现行
  J 次：2017-01〜2026-09 S0C2 组合（J-Quants 今天的日経225，真实一手）Calmar ≥ 现行
  都满足 → 通过；多个 → 提议 P 的 Calmar 最高的。通过也只是提议（用户确认才改模拟盘）。
三、另报（只描述）：1950〜2005 每个 10 年的 5〜10 月 / 11〜4 月平均年化；组合每年的收益。
四、局限：S&P500 价格指数不含股息（两个季节都不含，比较是相对的）；1950〜2005 用美元、没有汇率；税前。
登记前做过的检查：tests/test_halloween_study.py（月份比例、单独核心的回测不偷看、判定）。
输出：var/out/halloween_study.md / .json（只有统计）
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
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

CANDS = {"H1": ("5〜10 月核心 50%", 0.5), "H2": ("5〜10 月核心 0%", 0.0)}
P_WIN = {"P": ("1950-01-01", "2006-01-01"), "P1": ("1950-01-01", "1978-01-01"), "P2": ("1978-01-01", "2006-01-01")}
SWITCH_COST = 0.1
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def season_expo(days: pd.DatetimeIndex, summer: float) -> pd.Series:
    """每天的核心比例：5〜10 月 = summer，11〜4 月 = 1。"""
    m = days.month
    return pd.Series(np.where((m >= 5) & (m <= 10), summer, 1.0), index=days)


def core_only(close: pd.Series, bear: pd.Series, expo: pd.Series) -> pd.Series:
    """只有核心的净值（前一天收盘的状态决定当天持仓；每次调整扣 SWITCH_COST%）。"""
    r = close.pct_change().fillna(0.0)
    pos = ((~bear.reindex(close.index).ffill().fillna(False).astype(bool)).astype(float) * expo.reindex(close.index).fillna(1.0)).shift(1).fillna(0.0)
    cost = pos.diff().abs().fillna(pos.abs()) * SWITCH_COST / 100
    return (1 + pos * r - cost).cumprod()


def seg(eq: pd.Series, a: str, b: str) -> dict:
    e = eq[(eq.index >= pd.Timestamp(a)) & (eq.index < pd.Timestamp(b))]
    if len(e) < 2:
        return {"cagr": None, "dd": None, "calmar": None}
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1
    dd = float((e / e.cummax() - 1).min())
    return {"cagr": round(cagr * 100, 2), "dd": round(dd * 100, 2), "calmar": round(cagr / abs(dd), 3) if dd < 0 else None}


def p_fails(r: dict, base: dict) -> list[str]:
    c = L.MS._c
    f = []
    if c(r["P"]["calmar"]) < c(base["P"]["calmar"]) + L.CALMAR_UP:
        f.append(f"1950〜2005 Calmar {r['P']['calmar']} < 现行 {base['P']['calmar']} + {L.CALMAR_UP}")
    if r["P"]["dd"] is None or r["P"]["dd"] < base["P"]["dd"] - L.DD_TOL:
        f.append(f"1950〜2005 最大回撤 {r['P']['dd']}% 比现行 {base['P']['dd']}% 深 {L.DD_TOL} pp 以上")
    for k, lab in (("P1", "1950〜1977"), ("P2", "1978〜2005")):
        if c(r[k]["calmar"]) < c(base[k]["calmar"]):
            f.append(f"{lab} Calmar {r[k]['calmar']} < 现行 {base[k]['calmar']}")
    return f


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/halloween_study.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True).stdout.strip())
    spx = load(*SYM["US"])["Close"]
    d = load_config()["detector"]
    bear = pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(spx)) == BEAR, index=spx.index)
    RP = {"现行": {k: seg(core_only(spx, bear, season_expo(spx.index, 1.0)), a, b) for k, (a, b) in P_WIN.items()}}
    for c, (_, sv) in CANDS.items():
        eq = core_only(spx, bear, season_expo(spx.index, sv))
        RP[c] = {k: seg(eq, a, b) for k, (a, b) in P_WIN.items()}
    r = spx.pct_change()
    decades = {}
    for y0 in range(1950, 2006, 10):
        m = (r.index.year >= y0) & (r.index.year < min(y0 + 10, 2006))
        rs = r[m]
        summer = rs[(rs.index.month >= 5) & (rs.index.month <= 10)].mean() * 252 * 100
        winter = rs[(rs.index.month <= 4) | (rs.index.month >= 11)].mean() * 252 * 100
        decades[f"{y0}〜{min(y0 + 9, 2005)}"] = (round(float(summer), 1), round(float(winter), 1))
    D = CD.load()
    p0 = load_params(market="JP")
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
        allday = pd.bdate_range("2000-01-01", "2027-12-31")
        res[era] = {"现行": run(fr, p0)}
        for c, (_, sv) in CANDS.items():
            res[era][c] = run(fr, p0, core_expo={"US": season_expo(allday, sv)})
    fails, passed = {}, {}
    for c in CANDS:
        pf = p_fails(RP[c], RP["现行"])
        ef = [] if L.MS._c(res["E"][c]["E"]["calmar"]) >= L.MS._c(res["E"]["现行"]["E"]["calmar"]) else \
            [f"2006〜2016 组合 Calmar {res['E'][c]['E']['calmar']} < 现行 {res['E']['现行']['E']['calmar']}"]
        jf = L.j_fails(res["J"][c], res["J"]["现行"])
        fails[c] = pf + ef + jf
        if not fails[c]:
            passed[c] = RP[c]
    best = max(passed, key=lambda k: (L.MS._c(passed[k]["P"]["calmar"]), -int(k[1:]))) if passed else None
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("# 核心仓位的季节性：5〜10 月减仓（登记检验，2026-09-27）")
    say("规则见 scripts/halloween_study.py 开头（先提交后运行）。各格 = 年化 / 最大回撤 / Calmar。")
    say("\n## 主：1950-01〜2005-12，只有核心（S&P500 价格指数、美元、现行牛熊择时）")
    say("| 方案 | 1950〜2005 | 1950〜1977 | 1978〜2005 | 判定 |")
    say("|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        g = "—" if k == "现行" else ("✓" if not p_fails(RP[k], RP["现行"]) else "✗")
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k][0]} | {cell(RP[k]['P'])} | {cell(RP[k]['P1'])} | {cell(RP[k]['P2'])} | {g} |")
    say("\n## 次：S0C2 组合（日元）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 |")
    say("|---|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        e, j = res["E"][k], res["J"][k]
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k][0]} | {cell(e['E'])} | {cell(e['E1'])} | {cell(e['E2'])} | {cell(j['J'])} | {cell(j['V'])} | {cell(j['H'])} |")
    for c, f in fails.items():
        if f:
            say(f"- {c}：" + "；".join(f))
    say("\n## 1950〜2005 每 10 年：S&P500 5〜10 月 / 11〜4 月 的平均年化（%，价格指数，只描述）")
    say("| 年代 | 5〜10 月 | 11〜4 月 |")
    say("|---|---|---|")
    for k, (s_, w_) in decades.items():
        say(f"| {k} | {s_:+.1f} | {w_:+.1f} |")
    say("\n## 组合每一年的收益（%，只描述）")
    ys = [str(y) for y in range(2006, 2027)]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ["现行"] + list(CANDS):
        vals = {**{y: v for y, v in res["E"][k]["years"].items() if y <= "2016"}, **{y: v for y, v in res["J"][k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    if best:
        say(f"\n**结论：{best} {CANDS[best][0]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "core_only": RP, "E": res["E"], "J": res["J"], "fails": fails, "passed": list(passed), "proposal": best,
           "decades": decades}
    fp = paths.out_dir() / "halloween_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
