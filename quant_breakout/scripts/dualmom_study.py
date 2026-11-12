"""dualmom_study.py — 核心仓位的双动量（dual momentum）：美股 / 日本哪个更强就拿哪个（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：组合的收益主要来自核心（layer_study）；以前比过「只拿 1655 / 只拿 1329 / 各半 / 各半且熊市那份给另一只」（unified_study C1〜C4，
C3 20 年 Calmar 0.39 ≈ C2 0.38）与「熊市换黄金 / 长债」（refuge_study，没通过），**没试过按相对强弱切换**。
双动量是文献上的做法（相对动量选市场 + 各自的牛熊判定当绝对动量），不是从这里的数据里挑出来的 → 直接登记。
用户这一轮：「…不同的搭配…考虑没有考虑过的方法」。

一、资产：1655.T（S&P500，日元；上市前 S&P500 × USD/JPY + 1.3%/年）与 1329.T（日経225；2009 年以前的行情用日経225 + 1.6%/年拼接，与 unified_study 同一做法）
二、规则（每月最后一个交易日收盘决定「哪边强」，下个月照用；牛熊判定照现行每天）
  强弱 = 最近 K 个交易日的涨幅：美股 = S&P500 × USD/JPY（日元计，前一个美国收盘 × 当天早上的汇率），日本 = 日経225；
  两边都牛 → 闲置资金全部拿强的那边的 ETF；只有一边牛 → 拿那边；都熊 → 现金。
  M1 K = 252（12 个月）；M2 K = 126（6 个月）。「现行」= 闲置资金只拿 1655（美股牛熊）。
三、判定（与 layer_study / refuge_study 同一套）
  主（E）：2006-10〜2016-09（yfinance 今天的日経225 做个股）Calmar ≥ 现行 + 0.05，最大回撤不比现行深 2 pp 以上，两个半段各自 Calmar ≥ 现行
  次（J）：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）Calmar ≥ 现行
  都满足 → 通过；多个 → 提议 E 的 Calmar 最高的（一样取编号小的）。通过也只是提议（用户确认才改模拟盘；实盘还要让执行器会买 1329）。
四、另报（只描述）：每年的收益；拿日本的时间比例、每年切换次数。
五、局限：1329 在 2009 年以前、1655 在 2017 年以前是指数合成（股息按估计）；切换有成本（照立花手续费 + 滑点算进去了）；税前。
登记前做过的检查：tests/test_dualmom_study.py（核心目标：两边都牛拿强的、一边牛拿那边、都熊现金；强弱只用月末为止的数据）。
输出：var/out/dualmom_study.md / .json（只有统计）
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

JP_ETF = "1329.T"
CANDS = {"M1": ("12 个月强弱", 252), "M2": ("6 个月强弱", 126)}
CFG = {"core": {"1655.T": 1.0, JP_ETF: 1.0}, "core_index": {"1655.T": "MU", JP_ETF: "MJ"}, "core_mode": "follow"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def pref_us(us: pd.Series, jp: pd.Series, k: int) -> pd.Series:
    """每月最后一个交易日：美股 K 日涨幅 ≥ 日本 → True（美股强）。只用当天收盘为止；历史不够 → 不给（引擎按美股处理）。"""
    df = pd.concat([us.rename("us"), jp.rename("jp")], axis=1).ffill().dropna()
    mu, mj = df["us"] / df["us"].shift(k) - 1, df["jp"] / df["jp"].shift(k) - 1
    ok = mu.notna() & mj.notna()
    me = df.index.to_series().groupby(df.index.to_period("M")).max()
    me = pd.DatetimeIndex(me.to_numpy())
    s = (mu >= mj)[ok]
    return s[s.index.isin(me)]


def jp_core_frame() -> pd.DataFrame:
    from bullbear_study import SYM, load
    from qbreak.config import DataConfig
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    etf = load_universe([JP_ETF], d21)[JP_ETF]
    return core_frame(etf, load(*SYM["JP"]), div_yield_pct=1.6)


def main() -> int:
    from bullbear_study import SYM, load
    from unified_study import spx_jpy_on_jp_days
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/dualmom_study.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True).stdout.strip())
    D = CD.load()
    p0 = load_params(market="JP")
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fx = load("JPY=X", "2000-01-01")
    fx = fx[(fx["Close"] > 60) & (fx["Close"] < 250)]["Close"]
    us_jpy = spx_jpy_on_jp_days(idx["US"], fx, idx["JP"].index)["Close"]
    jp = idx["JP"]["Close"]
    prefs = {c: pref_us(us_jpy, jp, k) for c, (_, k) in CANDS.items()}
    jpf = jp_core_frame()
    res, stats = {}, {}
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
        fr = CS_.frames_from(P, days, names, cols, p0, {})
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        res[era] = {"现行": run(fr, p0)}
        for c in CANDS:
            res[era][c] = run(fr, p0, cfg_over=CFG, extra_core={JP_ETF: jpf}, pref_us=prefs[c])
        lo, hi = pd.Timestamp(start), (pd.Timestamp(end) if end else days[-1])
        stats[era] = {}
        for c in CANDS:
            s = prefs[c][(prefs[c].index >= lo) & (prefs[c].index <= hi)]
            stats[era][c] = {"jp_share_months": float((~s).mean()) if len(s) else None, "switches_per_year": float((s != s.shift()).iloc[1:].sum() / max(len(s) / 12, 1e-9)) if len(s) > 1 else None}
    RE, RJ = res["E"], res["J"]
    fails, passed = {}, {}
    for c in CANDS:
        ef, jf = L.e_fails(RE[c], RE["现行"]), L.j_fails(RJ[c], RJ["现行"])
        fails[c] = {"E": ef, "J": jf}
        if not ef and not jf:
            passed[c] = RE[c]
    best = max(passed, key=lambda k: (L.MS._c(passed[k]["E"]["calmar"]), -int(k[1:]))) if passed else None
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("# 核心仓位的双动量：美股 / 日本哪个强拿哪个（登记检验，2026-09-27）")
    say("规则见 scripts/dualmom_study.py 开头（先提交后运行）。S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say("\n## 主：2006-10〜2016-09")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 拿日本的月份比例 / 每年切换次数 | 判定 |")
    say("|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RE[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["E"] else "✗")
        st = "—" if k == "现行" else f"{fa(stats['E'][k]['jp_share_months'] * 100, '{:.0f}')}% / {fa(stats['E'][k]['switches_per_year'], '{:.1f}')}"
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k][0]} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | {st} | {g} |")
    say("\n## 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）")
    say("| 方案 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 拿日本的月份比例 / 每年切换次数 | 判定 |")
    say("|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RJ[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["J"] else "✗")
        st = "—" if k == "现行" else f"{fa(stats['J'][k]['jp_share_months'] * 100, '{:.0f}')}% / {fa(stats['J'][k]['switches_per_year'], '{:.1f}')}"
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k][0]} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {cell(r['V'])} | {cell(r['H'])} | {st} | {g} |")
    for c, g in fails.items():
        msg = (g["E"] or []) + (g["J"] or [])
        if msg:
            say(f"- {c}：" + "；".join(msg))
    say("\n## 每一年的收益（%，只描述）")
    ys = [str(y) for y in range(2006, 2027)]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ["现行"] + list(CANDS):
        vals = {**{y: v for y, v in RE[k]["years"].items() if y <= "2016"}, **{y: v for y, v in RJ[k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    if best:
        say(f"\n**结论：{best} {CANDS[best][0]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；实盘还要让执行器会买 {JP_ETF}）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "E": RE, "J": RJ, "fails": fails, "passed": list(passed), "proposal": best, "stats": stats}
    fp = paths.out_dir() / "dualmom_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
