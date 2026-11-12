"""layer_study.py — 个股层值不值得、占多少（研究路线图 R2a；2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：mtf_posthoc（事后）看到 2017〜2026 同一套 S0C2 设定下「个股一笔不买、只有 1655」年化 14.17% / Calmar 0.424，比现行好；
这是看过 2017〜2026 才知道的 → 这次主要在**没用来得出这个想法的年代 2006-10〜2016-09**（含 2008 年金融危机、日元升到 76 円的时期）检验。
用户这一轮的要求：「…让策略达到登记门槛…不同的搭配…考虑没有考虑过的方法」。

一、数据
  E 2006-10〜2016-09：yfinance 今天的日経225 股票池（213 只，调整后行情；一手按调整后价 —— 以前 20 年回测的口径，拆股前的一手偏便宜）；
    1655 = S&P500 × USD/JPY 合成（上市前）+ 年 1.3% 分红，与以前的 20 年回测相同
  J 2017-01〜2026-09：J-Quants 今天的日経225（= 实盘股票池），一手按当时真实股价（scripts/candle_portfolio.make_runner）
二、候选（其余 = var/sim.json 同一套 S0C2 设定：立花、¥100 万、1655 牛熊择时、宏观 / 板块 / 量化状态层、回撤 HALT；个股 = 现行突破）
  A1 只有 1655：个股一笔不买（闲置资金全部 1655，同一套牛熊择时）
  A2 个股名额减半：最多 2 只 × 权益 25%（个股最多约一半，其余 1655）
  A3 个股只在日本牛市开新仓：日本牛熊判定（var/bullbear.json 同一个判定器，对日経）收盘时为熊 → 第二天不开个股新仓（持仓照常卖）
  「现行」= 同一设定、4 只 × 25%
三、判定
  主（E）：2006-10〜2016-09 的 Calmar ≥ 现行 + 0.05，且最大回撤不比现行深 2 pp 以上；两个半段（2006-10〜2011-09 / 2011-10〜2016-09）
    各自 Calmar ≥ 现行
  次（J）：2017-01〜2026-09 的 Calmar ≥ 现行（不更差；这一段是想法的来源，只要求不更差）
  都满足 → 通过；多个通过 → 提议 E 的 Calmar 最高的（一样取编号小的）。通过也只是提议：模拟盘改不改要用户在对话里确认。都不通过 → 维持现行。
四、另报（只描述）：每一年的收益；个股笔数、胜率；E 期间的「区间总收益」。
五、局限：E 的股票池是今天的日経225（幸存者偏差，个股层偏乐观）且一手按调整后价（偏便宜）→ 对个股层有利、对 A1 不利；
  1655 在 2017 年前是合成的；税前；10 年里真正的熊市只有 2007〜2009 与 2020、2022 几段。
登记前做过的检查：tests/test_layer_study.py（门槛）、tests/test_candle_study.py（同一个组合回测）；数据与 candle_study / mtf_study 同一套。
输出：var/out/layer_study.md / .json（只有统计）
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
import ml_study as MS                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

E_WIN = {"E": ("2006-10-02", "2016-10-01"), "E1": ("2006-10-02", "2011-10-01"), "E2": ("2011-10-01", "2016-10-01")}
J_WIN = {"J": ("2017-01-04", None), "V": ("2022-01-01", "2023-10-01"), "H": ("2023-10-01", None)}
CALMAR_UP, DD_TOL = 0.05, 2.0
CANDS = {"A1": "只有 1655（个股不买）", "A2": "个股名额减半（2 只 × 25%）", "A3": "个股只在日本牛市开新仓"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def e_fails(r: dict, base: dict) -> list[str]:
    f = []
    if MS._c(r["E"]["calmar"]) < MS._c(base["E"]["calmar"]) + CALMAR_UP:
        f.append(f"2006〜2016 Calmar {r['E']['calmar']} < 现行 {base['E']['calmar']} + {CALMAR_UP}")
    if r["E"]["dd"] is None or base["E"]["dd"] is None or r["E"]["dd"] < base["E"]["dd"] - DD_TOL:
        f.append(f"2006〜2016 最大回撤 {r['E']['dd']}% 比现行 {base['E']['dd']}% 深 {DD_TOL} pp 以上")
    for k, lab in (("E1", "前半 2006-10〜2011-09"), ("E2", "后半 2011-10〜2016-09")):
        if MS._c(r[k]["calmar"]) < MS._c(base[k]["calmar"]):
            f.append(f"{lab} Calmar {r[k]['calmar']} < 现行 {base[k]['calmar']}")
    return f


def j_fails(r: dict, base: dict) -> list[str]:
    return [] if MS._c(r["J"]["calmar"]) >= MS._c(base["J"]["calmar"]) else [f"2017〜2026 Calmar {r['J']['calmar']} < 现行 {base['J']['calmar']}"]


def variants(run, fr: dict, p0) -> dict:
    none = {t: df.assign(entry=False) for t, df in fr.items()}
    return {"现行": run(fr, p0), "A1": run(none, p0), "A2": run(fr, p0, cfg_over={"max_positions": 2}), "A3": run(fr, p0, jp_bull_only=True)}


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/layer_study.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True).stdout.strip())
    D = CD.load()
    p0 = load_params(market="JP")
    # E：yfinance 今天的日経225
    E, ed, en = D["E"], D["edays"], D["enames"]
    PRS.PitEngine.DELIST = {}
    fe = CS_.frames_from(E, ed, en, list(range(len(en))), p0, {})
    rune = CP.make_runner(pd.DataFrame({t: fe[t]["Close"] for t in fe}).reindex(ed), {}, E_WIN, end="2016-09-30", start=E_WIN["E"][0])
    RE = variants(rune, fe, p0)
    # J：J-Quants 今天的日経225（真实一手）
    days, P, names = D["days"], D["P"], D["names"]
    mem0 = D["mem"]["U0"]
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    c0 = [j for j in range(len(names)) if mem0[:, j].any()]
    fj = CS_.frames_from(P, days, names, c0, p0, {})
    runj = CP.make_runner(pd.DataFrame({t: fj[t]["Close"] for t in fj}).reindex(days),
                          {t: pd.Series(D["ratio"][:, names.index(t)], index=days) for t in fj}, J_WIN)
    RJ = variants(runj, fj, p0)
    fails, passed = {}, {}
    for c in CANDS:
        ef, jf = e_fails(RE[c], RE["现行"]), j_fails(RJ[c], RJ["现行"])
        fails[c] = {"E": ef, "J": jf}
        if not ef and not jf:
            passed[c] = RE[c]
    best = max(passed, key=lambda k: (MS._c(passed[k]["E"]["calmar"]), -int(k[1:]))) if passed else None
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("# 个股层值不值得、占多少（研究路线图 R2a；登记检验，2026-09-27）")
    say("规则见 scripts/layer_study.py 开头（先提交后运行）。S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say("\n## 主：2006-10〜2016-09（yfinance 今天的日経225；想法来源之外的年代）")
    say("| 方案 | 2006-10〜2016-09 | 前半 2006-10〜2011-09 | 后半 2011-10〜2016-09 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RE[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["E"] else "✗")
        lab = k if k == "现行" else f"{k} {CANDS[k]}"
        say(f"| {lab} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    say("\n## 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手；想法的来源，只要求不更差）")
    say("| 方案 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RJ[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["J"] else "✗")
        lab = k if k == "现行" else f"{k} {CANDS[k]}"
        say(f"| {lab} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {cell(r['V'])} | {cell(r['H'])} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    for c, g in fails.items():
        msg = (g["E"] or []) + (g["J"] or [])
        if msg:
            say(f"- {c}：" + "；".join(msg))
    say("\n## 每一年的收益（%，只描述）")
    ys = sorted(set().union(*[set(RE[k]["years"]) for k in RE]) | set().union(*[set(RJ[k]["years"]) for k in RJ]))
    ys = [y for y in ys if "2006" <= y <= "2026"]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ["现行"] + list(CANDS):
        vals = {**{y: v for y, v in RE[k]["years"].items() if y <= "2016"}, **{y: v for y, v in RJ[k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    if best:
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；改之前记进 sim_changes.md）。**"
            + (f"另外也通过的：{'、'.join(k for k in passed if k != best)}。" if len(passed) > 1 else ""))
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "E": RE, "J": RJ, "fails": fails, "passed": list(passed), "proposal": best}
    fp = paths.out_dir() / "layer_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
