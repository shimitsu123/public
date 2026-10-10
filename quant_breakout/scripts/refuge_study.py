"""refuge_study.py — 核心仓位的搭配：美股熊市时不留现金、改拿黄金 / 美国长债，或平时就配一部分黄金
（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：layer_study（R2a）显示组合的收益主要来自 1655（S&P500）+ 牛熊择时，个股层 20 年整体没有贡献 → 改进核心可能比改进选股更有用。
现在美股熊市（var/bullbear.json 的判定）时 1655 全部卖掉留现金；以前的择时研究（timing / timing2 / timing3）都只比「什么时候进出」，
没有试过「熊市那份拿别的资产」。用户这一轮：「…不同的搭配…考虑没有考虑过的方法」。

一、资产（都换成日元，按东证交易日：前一个美国收盘 × 那天早上的 USD/JPY，与 1655 上市前的合成同一个做法 unified_study.spx_jpy_on_jp_days）
  黄金 = GLD × USD/JPY（记作 1540.T：立花能买的东证黄金 ETF）；美国长债 = TLT（含分配的调整后价）× USD/JPY（记作 2255.T：东证的美国长债 ETF）
  每口价格：黄金 ÷ 3.11（GLD 一股 ≈ 金 0.1 盎司 = 3.11 g → 每口约金 1 g，与 1540 相近）、长债 ÷ 10；只影响一口的粒度，不影响收益率
  成本 = 立花个别コース的手续费 + 0.03% 滑点、1 口一单位（qbreak.fees.etf_cost 的默认）
二、候选（其余 = var/sim.json 同一套 S0C2 设定：个股 = 现行突破、4 个名额；1655 按 S&P500 牛熊择时）
  G1 熊市换黄金：美股牛市 → 闲置资金全部 1655（现行）；美股熊市 → 全部黄金（现行是现金）
  G2 熊市换美国长债：同上，熊市拿美国长债
  G3 常配黄金 20%：闲置资金 1655 80% + 黄金 20%；美股熊市两者都卖、留现金（择时照现行）
  「现行」= 闲置资金全部 1655、熊市留现金
三、数据与判定（与 layer_study 同一套）
  主（E）：2006-10〜2016-09（yfinance 今天的日経225 做个股；想法来源之外的年代，含 2008 年、日元升值期）：Calmar ≥ 现行 + 0.05，
    且最大回撤不比现行深 2 pp 以上；两个半段（2006-10〜2011-09 / 2011-10〜2016-09）各自 Calmar ≥ 现行
  次（J）：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）：Calmar ≥ 现行（不更差）
  都满足 → 通过；多个 → 提议 E 的 Calmar 最高的（一样取编号小的）。通过也只是提议：模拟盘改不改要用户在对话里确认（实盘还要让执行器会买黄金 / 长债 ETF）。
四、另报（只描述）：每年的收益；美股熊市的每一段（前一天判定为熊 → 当天开盘换，到转牛后第一天开盘）S&P500 / 黄金 / 长债（都是日元）的区间收益。
五、局限：黄金 / 长债全程用美国 ETF × 汇率合成（信托报酬按美国 ETF；东证 ETF 的实际价格、与美国市场的时差都有差别）；
  熊市段在 20 年里只有几段（2008、2011、2015〜16、2018、2020、2022 等），样本少；税前。
登记前做过的检查：tests/test_refuge_study.py（「熊市换资产」的核心目标切换：美股牛市全部 1655、熊市全部避险资产；常配 20% 的比例；
  日元价格只用开盘前已知的美国收盘与汇率）；GLD / TLT 的行情取得（2004〜2026）；小样本试跑（只看持仓切换，不看收益）。
输出：var/out/refuge_study.md / .json（只有统计）
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

GOLD, BOND = "1540.T", "2255.T"
CANDS = {"G1": "熊市换黄金", "G2": "熊市换美国长债", "G3": "常配黄金 20%（熊市都留现金）"}
UNIT_DIV = {GOLD: 3.11, BOND: 10.0}                                          # 每口的价格量级（只影响一口的粒度）
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def cfg_for(c: str) -> dict:
    """候选 → UnifiedConfig 的核心设定（XR = 与美股牛熊相反，candle_portfolio.MixEngine）。"""
    if c in ("G1", "G2"):
        r = GOLD if c == "G1" else BOND
        return {"core": {"1655.T": 1.0, r: 1.0}, "core_index": {"1655.T": "US", r: "XR"}, "core_mode": "follow"}
    if c == "G3":
        return {"core": {"1655.T": 0.8, GOLD: 0.2}, "core_index": {"1655.T": "US", GOLD: "US"}, "core_mode": "split"}
    raise ValueError(c)


def jpy_frame(us: pd.DataFrame, fx: pd.Series, days: pd.DatetimeIndex, div: float) -> pd.DataFrame:
    """东证交易日 d 的价格 = 前一个美国收盘 × d 日早上的 USD/JPY ÷ div（与 1655 上市前的合成同一个做法）→ 引擎用的核心 K 线。"""
    from unified_study import spx_jpy_on_jp_days
    from qbreak.core import core_frame
    df = spx_jpy_on_jp_days(us, fx, days)
    px = ["Open", "High", "Low", "Close"]
    df[px] = df[px] / div
    return core_frame(df)


def bear_runs(bear: np.ndarray) -> list[tuple[int, int]]:
    """持有避险资产的日子（前一天收盘判定为熊 → 当天开盘换）连成的段：[(第一天, 结束后第一天)]（最后一段可能到末尾 = len）。"""
    held = np.r_[False, np.asarray(bear, bool)[:-1]]
    out, i, n = [], 0, len(held)
    while i < n:
        if not held[i]:
            i += 1
            continue
        j = i
        while j < n and held[j]:
            j += 1
        out.append((i, j))
        i = j
    return out


def run_returns(px: pd.Series, runs: list[tuple[int, int]]) -> list[float]:
    """每段的区间收益 %：第一天开盘买、结束后第一天开盘卖（到末尾 → 最后一天）。"""
    v = px.to_numpy(float)
    return [round(float(v[min(b, len(v) - 1)] / v[a] - 1) * 100, 2) if np.isfinite(v[a]) and v[a] > 0 else float("nan") for a, b in runs]


def us_bear() -> pd.Series:
    from bullbear_study import SYM, load
    from qbreak.bullbear import BEAR, Detector, load_config
    d = load_config()["detector"]
    us = load(*SYM["US"])
    return pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(us["Close"])) == BEAR, index=us.index)


def refuge_frames(days: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    from bullbear_study import SYM, load
    fx = load("JPY=X", "2000-01-01")
    fx = fx[(fx["Close"] > 60) & (fx["Close"] < 250)]["Close"]
    out = {t: jpy_frame(load(us, "2004-01-01"), fx, days, UNIT_DIV[t]) for t, us in ((GOLD, "GLD"), (BOND, "TLT"))}
    out["SPX"] = jpy_frame(load(*SYM["US"]), fx, days, 1.0)                    # 描述用：S&P500 日元（不含股息）
    return out


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/refuge_study.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True).stdout.strip())
    D = CD.load()
    p0 = load_params(market="JP")
    bear_s = us_bear()
    res, segs = {}, {}
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
        xc = refuge_frames(days)
        w = days[(days >= pd.Timestamp(start)) & ((days <= pd.Timestamp(end)) if end else True)]
        bj = bear_s.reindex(w.union(bear_s.index)).ffill().reindex(w).fillna(False).to_numpy(bool)
        runs = bear_runs(bj)
        rr = {k: run_returns(xc[t]["Open"].reindex(w).ffill(), runs) for k, t in (("SPX", "SPX"), ("gold", GOLD), ("bond", BOND))}
        segs[era] = [{"from": str(w[a].date()), "to": str(w[min(b, len(w) - 1)].date()), "days": int(b - a), **{k: rr[k][n] for k in rr}}
                     for n, (a, b) in enumerate(runs)]
        res[era] = {"现行": run(fr, p0)}
        for c in CANDS:
            extra = {GOLD: xc[GOLD]} if c in ("G1", "G3") else {BOND: xc[BOND]}
            res[era][c] = run(fr, p0, cfg_over=cfg_for(c), extra_core=extra)
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
    say("# 核心仓位的搭配：熊市换黄金 / 美国长债、常配黄金（登记检验，2026-09-27）")
    say("规则见 scripts/refuge_study.py 开头（先提交后运行）。S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say("\n## 主：2006-10〜2016-09")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 判定 |")
    say("|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RE[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["E"] else "✗")
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k]} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | {g} |")
    say("\n## 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）")
    say("| 方案 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 判定 |")
    say("|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RJ[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["J"] else "✗")
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k]} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {cell(r['V'])} | {cell(r['H'])} | {g} |")
    for c, g in fails.items():
        msg = (g["E"] or []) + (g["J"] or [])
        if msg:
            say(f"- {c}：" + "；".join(msg))
    say("\n## 每一年的收益（%，只描述）")
    ys = [y for y in sorted(set().union(*[set(RE[k]["years"]) for k in RE]) | set().union(*[set(RJ[k]["years"]) for k in RJ])) if "2006" <= y <= "2026"]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ["现行"] + list(CANDS):
        vals = {**{y: v for y, v in RE[k]["years"].items() if y <= "2016"}, **{y: v for y, v in RJ[k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    say("\n## 美股熊市的每一段：三种资产的区间收益（日元、%，只描述；前一天判定为熊 → 当天开盘换，到转牛后第一天开盘）")
    say("| 段 | 交易日 | S&P500（不含股息） | 黄金 | 美国长债 |")
    say("|---|---|---|---|---|")
    tot = {k: 1.0 for k in ("SPX", "gold", "bond")}
    for era in ("E", "J"):
        for g in segs[era]:
            say(f"| {g['from']}〜{g['to']} | {g['days']} | {fa(g['SPX'], '{:+.1f}')} | {fa(g['gold'], '{:+.1f}')} | {fa(g['bond'], '{:+.1f}')} |")
            for k in tot:
                tot[k] *= 1 + (g[k] / 100 if np.isfinite(g[k]) else 0.0)
    say(f"| 全部连乘 | {sum(g['days'] for e in segs.values() for g in e)} | " + " | ".join(f"{(tot[k] - 1) * 100:+.1f}" for k in ("SPX", "gold", "bond")) + " |")
    if best:
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；实盘还要让执行器会买 {GOLD if best != 'G2' else BOND}）。**"
            + (f"另外也通过的：{'、'.join(k for k in passed if k != best)}。" if len(passed) > 1 else ""))
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "E": RE, "J": RJ, "fails": fails, "passed": list(passed), "proposal": best, "bear_runs": segs}
    fp = paths.out_dir() / "refuge_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
