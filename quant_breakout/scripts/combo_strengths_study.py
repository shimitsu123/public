"""combo_strengths_study.py — 「把各个方法的长处结合在一起」：以前登记过、能在每个市场上算的核心择时规则里「离场 / 减仓一侧」的 11 个，
等权平均成一个规则 ENB（2026-10-04 登记；先提交后只运行一次；不属于任何研究循环；11 个成分都看过结果 → 事后，S7 适用）。

用户（2026-10-04，待办〔51〕之后）：「继续找研究方法，把各个方法的长处都结合在一起可不可行」。
为什么这样组合（照实写）：
  - 预测组合（forecast combination；Bates & Granger 1969、Timmermann 2006）的经验：几个各有一点信息、错得不一样的预测，固定等权平均
    往往比单个、也比按历史表现定权重的更稳（权重一估就带进噪音）；前提是各成分真的有信息、而且信息来源不同。
  - 这个项目里「有长处」的核心规则大多只在美国 / 某一段历史上成立：第七个循环 VCX / VTX / VSX 在 17 个市场合并 ≈ 0（VTX 与 VSX 各市场的 Δ
    相关 0.69 = 同一种信息）；VSX 在美国 1929〜1986 不支持；牛熊分界第二、三轮 T7〜T15 在美日的半段不达标、独立市场有好有坏
    （T12 10 个里 8 个择时 Calmar 不低于 T0、T7 只有 3 个）。单个都不够强 → 检验「合起来」是不是更强：各成分的错误若互不相关，
    等权平均能把各自的偶然抵消掉、留下共同的信息。检验力测算（power_study）：17 个市场横展开能认出 q ≥ 0.25 的规则。
  - 只收「离场 / 减仓一侧」：现行分界 T0 是牛时，各成分各自说该拿多少（不是熊 → 1、熊 → 0；分级 / 比例照原样）→ 平均 = 牛市里拿的比例；
    T0 熊时照旧不拿。回补一侧（T11 / T14 / T15 的提前回补、T2 / T3 的「熊要确认」）在 T0 牛的日子全都 = 1、不减仓，不收。
成分（选法事先写定、不按结果挑：以前登记过的核心择时规则中，① 只用这个市场自己的指数 + 美国宏观（VIX、Baa−10Y、失业率、10Y−3M）就能算、
  ② T0 牛的日子里会减仓或离场、③ 参数不需要用 1998 年以后的数据定、④ 不是已写定「不再用」的信号；同一个动作的重复只留一个）：
  T4 压力提前离场（VIX ≥ 30 且利差 20 日走阔 ≥ 0.3pt）、T5 12 个月绝对动量（月末）、T6 五因子多数表决、T7 双速离场、T8 信用加快离场、
  T10 临界减半、T12 快速离场要信用确认、T13 快速离场要另一个大市场确认（qbreak/timing.py 原样）；
  VCX 急跌减 1/3、VTX 波动目标、VSX 波动冲击（第七个循环第 1〜3 轮原样：loop7_r01 / r02 / r03 的函数）。共 11 个，等权（每个 1/11）。
  不收（EXCLUDED）：T1（汇率，只有日元计价的美股有）、T2 / T3 / T11 / T14（T0 牛的日子 = 1）、T15（离场 = T12，重复）、
  T9（带宽系数用到 2005 年的数据定 → 窗口里偷看）、威胁指数 A0 / C_rel（2026-09-30 写定不再用作核心层开关）、K4（用户 2026-09-30 拿掉）、
  NDR / NDB / ZSP（要同一个市场的第二个指数）、汇率 / 债券类（不是每个市场都有数据）。
做法 ENB（权重固定、不学参数 → S6 不适用；不改个股 → S5 不适用）：
  - 每个市场：11 个成分每个交易日「拿的比例」e_i（T 规则：不是熊 → 1、熊 → 0；T10 分级 1 / 0.5 / 0；VCX：急跌 → 2/3、否则 1；
    VTX / VSX：比例）→ r = 11 个的平均（缺值当 1）→ 自己的牛熊分界 T0 牛 → 指数 × r、其余现金。
    美国宏观（qbreak/timing.factor_frame：VIX 当天、Baa 与美债滞后 1 个营业日、失业率次月 10 日起）：非美国市场用前一个美国日的值
    （timing2 / timing3 同一套对齐）。T13 的「另一个大市场收在 250 日线下」：非美国市场 = S&P 500（前一天），美国 = 日経225（同一天）。
  - 账户（第一关，B3 上）：美国 = S&P 500（1980-01-01 起的历史；横展开同一个函数）的 r（美国日）→ 东证日 = 美国日期 ≤ 东证日的最近一个值
    （同 B3 的「美股熊」）→ 1545 的 core_expo["US"]（loop7_r02_voltarget.vtx_over，同 VTX / VSX；减下来的留现金）；
    research_loop6.stage1（S1〜S4 + S7；S7 = 1987〜2000 只有核心，loop7_r02_voltarget.old_core）。
  - 第二关 = research_loop7 三（17 个市场、窗口 1998-01-01〜2026-09-30、比例序列在窗口内同一个 k 循环平移 400 次（与第七个循环相同的 k）、
    C1 合并平均 > 0 且严格大于 400 次随机的最大值、C2 Δ > 0 的市场 ≥ 12 / 17、C3 前后两半的合并平均都 > 0）。
    平移用的比例序列：8 个 T 规则在 T0 不是牛的日子记 1（「牛市里拿多少」只在牛的日子有意义；候选本身只在 T0 牛的日子用 r → 不受影响），
    波动类三个每天照原样（同第七个循环）。登记前的规模核对（只数日子、没算收益）发现：不这样记时 T 规则在熊市的 0 会被平移进牛市日子，
    随机对照牛市日子平均只拿 0.705（真实 0.943）= 拿「随机大减仓」当对照、不公平；这样记之后 0.948 vs 0.943（减仓量相当）。
  - 判定：第一关全过 ∧ 第二关三条都过 → 「更好候选」（停下等用户决定；模拟盘与执行器不改）；否则「第一关不过」/「第二关不过」。
只描述（不参与判定）：每个成分单独（同一个写法：T0 牛 × e_i）在 17 个市场与账户上的 Δ；「组合增益」= ENB 的合并 Δ − 11 个成分合并 Δ 的平均；
  成分之间各市场 Δ 的平均相关；各市场自己的随机百分位；美国 S&P 500 同样的数字；随机平移后牛市日子里减仓的比例（与真实的比）。
接线核对（登记前，不看候选的结果；--wiring）：① 比例全 1 → 三个年代与 B3 逐项相同、17 个市场 Δ 全为 0（平移后也是 0）；② old_core 比例全 1 = B3；
  ③ B3 没有别的 core_expo；④ 组合 = 11 个成分的平均、成分 = 登记的函数（tests/test_combo_strengths.py）。
规模（登记前，只数日子；--scale）：三个年代 / 1987〜2000 美股牛的日子里 r < 1 的比例、段数、平均；17 个市场同样的数字 + 每个成分的减仓比例
  + 随机平移后的减仓比例。
多重检验（照实写）：只一个候选、只运行一次；11 个成分都在以前的研究里看过结果（事后），所以账户上的结果偏乐观 → 判定靠 17 个市场。
原始数据（Yahoo 指数日线、FRED）只在内存 / 已 gitignore 的缓存，不入库；输出只存导出的数字。
运行：python scripts/combo_strengths_study.py（第一关 + 第二关，只运行一次）；--scale；--wiring。输出 var/out/combo_strengths_study.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop6_common as L6                                                    # noqa: E402
import loop6_r07_volbond as V                                                # noqa: E402
import loop7_r01_vctx as P1                                                  # noqa: E402
import loop7_r02_voltarget as P2                                             # noqa: E402
import loop7_r03_volshock as P3                                              # noqa: E402
import research_loop6 as R6                                                  # noqa: E402
import research_loop7 as R7                                                  # noqa: E402
from qbreak import timing as T                                               # noqa: E402
from qbreak.bullbear import BEAR, _sma                                       # noqa: E402

IDS = ("ENB",)
COMPONENTS = ("T4", "T5", "T6", "T7", "T8", "T10", "T12", "T13", "VCX", "VTX", "VSX")
T_RULES = ("T4", "T5", "T6", "T7", "T8", "T10", "T12", "T13")                # 只在 T0 牛的日子有意义 → T0 不是牛的日子 = 1
VOL_RULES = ("VCX", "VTX", "VSX")                                            # 每天都有定义（与第七个循环相同）
EXCLUDED = {"T1": "汇率（只有日元计价的美股有）", "T2": "T0 牛的日子 = 1（熊要失业率确认）", "T3": "T0 牛的日子 = 1（熊要信用确认）",
            "T9": "带宽系数用到 2005 年的数据定（窗口里偷看）", "T11": "回补一侧（T0 牛的日子 = 1）", "T14": "回补一侧（T0 牛的日子 = 1）",
            "T15": "离场 = T12（重复）", "A0 / C_rel": "2026-09-30 写定不再用作核心层开关", "K4": "用户 2026-09-30 拿掉",
            "NDR / NDB / ZSP": "要同一个市场的第二个指数", "汇率 / 债券类": "不是每个市场都有数据"}
POSTHOC = True
MACRO = ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "UNRATE")
OUT = "combo_strengths_study"
KEYS = P2.KEYS


# ───────────────────────── 规则（纯函数，tests/test_combo_strengths.py） ─────────────────────────
def asof_prev(s: pd.Series, idx: pd.DatetimeIndex, lag_days: int = 1) -> pd.Series:
    """s → idx 上「日期 ≤ d − lag_days 天的最近一个值」（timing_study.asof 同一个取法；lag_days = 1 = 前一个美国日）。"""
    idx = pd.DatetimeIndex(idx)
    when = idx - pd.Timedelta(days=int(lag_days))
    x = s.dropna()
    v = x.reindex(x.index.union(when)).ffill().reindex(when).to_numpy(float)
    return pd.Series(v, index=idx)


def factor_us(spx: pd.Series, raw: dict) -> pd.DataFrame:
    """美国交易日上的宏观（qbreak/timing.factor_frame 原样；汇率列不用）。"""
    empty = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return T.factor_frame(pd.DatetimeIndex(spx.index), empty, raw["VIXCLS"], raw["BAA10Y"], raw["DGS10"], raw["DGS3MO"], raw["UNRATE"])


def below_ma(close: pd.Series) -> pd.Series:
    """每天是否收在自己的 250 日线下（1 / 0；还没有 250 日线 = 空）—— scripts/timing3_study.below_ma 原样。"""
    v = close.to_numpy(float)
    ma = _sma(v, T.L)
    return pd.Series(np.where(np.isnan(ma), np.nan, (v < ma).astype(float)), index=close.index)


def frame_for(m: str, idx: pd.DatetimeIndex, f_us: pd.DataFrame, sp_below: pd.Series, nk_below: pd.Series) -> pd.DataFrame:
    """一个市场交易日上的美国宏观 + T13 的「另一个大市场在 250 日线下」：美国 = 同一天的宏观、日経（同一天）；
    其余 = 前一个美国日的宏观、S&P 500（前一天）。"""
    idx = pd.DatetimeIndex(idx)
    lag = 0 if m == "US" else 1
    f = pd.DataFrame({c: asof_prev(f_us[c], idx, lag) for c in f_us.columns}, index=idx)
    f["other_below"] = asof_prev(nk_below if m == "US" else sp_below, idx, lag) > 0.5
    return f


def _not_bear(st, idx) -> pd.Series:
    return pd.Series((np.asarray(st) != BEAR).astype(float), index=idx)


def components(close: pd.Series, f: pd.DataFrame) -> pd.DataFrame:
    """一个市场的 11 个成分：每个交易日「拿的比例」（0〜1），都是登记过的函数原样。"""
    c = close.dropna().sort_index().astype(float)
    f = f.reindex(c.index)
    vcx = P1.signal(c)["signal"].reindex(c.index).fillna(False).to_numpy(bool)
    out = {"T4": (~T.t4_stress_exit(c, f).astype(bool)).astype(float),
           "T5": (~T.t5_momentum(c, f).astype(bool)).astype(float),
           "T6": (~T.t6_majority(c, f).astype(bool)).astype(float),
           "T7": _not_bear(T.s7_dual_speed(c, f), c.index),
           "T8": _not_bear(T.s8_credit_fast_exit(c, f), c.index),
           "T10": T.t10_half_expo(c, f).astype(float),
           "T12": _not_bear(T.s12_fast_credit(c, f), c.index),
           "T13": _not_bear(T.s13_fast_global(c, f), c.index),
           "VCX": pd.Series(np.where(vcx, P1.KEEP, 1.0), index=c.index),
           "VTX": P2.market_ratio(c).reindex(c.index).astype(float),
           "VSX": P3.shock_ratio(c).reindex(c.index).astype(float)}
    return pd.DataFrame({k: out[k].reindex(c.index) for k in COMPONENTS}, index=c.index)


def ensemble(comp: pd.DataFrame, bull: pd.Series | None = None) -> pd.Series:
    """等权平均（每个成分 1/11）；缺值当 1（不减）。bull（T0 牛）给了 → T 规则在 T0 不是牛的日子 = 1（「牛市里拿多少」只在牛的日子有意义；
    T0 牛的日子不变 → 候选本身不受影响，只让随机平移带进牛市日子的值与真实的减仓量相当）；波动类三个每天照原样（同第七个循环）。"""
    x = comp[list(COMPONENTS)].astype(float).fillna(1.0).clip(0.0, 1.0)
    if bull is not None:
        off = ~bull.reindex(x.index).fillna(False).astype(bool).to_numpy()
        x.loc[off, list(T_RULES)] = 1.0
    return x.mean(axis=1)


# ───────────────────────── 输入 / 规模 ─────────────────────────
def macro_raw() -> dict:
    from qbreak import factors as F
    return {k: F.fred(k) for k in MACRO}


def market_inputs(keys=None) -> dict:
    """17 个市场 + 美国（S&P 500）：收盘、牛熊（T0）、11 个成分、组合比例。"""
    keys = list(R7.MARKETS) + list(R7.SOURCE) if keys is None else list(keys)
    closes = R7.load_markets(sorted(set(keys) | {"US", "JP"}, key=lambda m: (m not in R7.MARKETS, m)))
    bad = [m for m in keys if m in R7.MARKETS and not R7.eligible(closes[m])]
    if bad:
        raise RuntimeError(f"数据不够（1996-06-30 之前没有 / 窗口里缺）：{bad}")
    f_us = factor_us(closes["US"], macro_raw())
    sp_below, nk_below = below_ma(closes["US"]), below_ma(closes["JP"])
    comps, ratios, bulls = {}, {}, {}
    for m in keys:
        c = closes[m]
        comps[m] = components(c, frame_for(m, c.index, f_us, sp_below, nk_below))
        bulls[m] = R7.bull(c)
        ratios[m] = ensemble(comps[m], bulls[m])
    return {"closes": {m: closes[m] for m in keys}, "comps": comps, "ratios": ratios, "bulls": bulls}


def account_inputs(W: dict, I: dict) -> dict:
    """B3 的输入（loop6_r07_volbond.inputs）+ 美国（S&P 500）的组合比例（美国日）与东证日上的比例 + 各成分。"""
    M = V.inputs(W)
    M["comp_us"] = I["comps"]["US"]
    M["ratio_us"] = I["ratios"]["US"]
    M["ratio_t"] = P2.as_of(M["ratio_us"], M["days"])
    return M


def _cut_pct(bull: pd.Series, x: pd.Series) -> float | None:
    b = bull.astype(bool)
    nb = int(b.sum())
    v = x.reindex(b.index).astype(float).fillna(1.0)
    return round(float((b & (v < 1.0 - 1e-12)).sum()) / nb * 100, 1) if nb else None


def account_scale(W: dict, M: dict) -> dict:
    out = {}
    for e in L6.ERAS:
        d = V.era_days(W, e)
        bull = ~V.on_idx(M["bear_t"], d)
        out[e] = {**P2.cut_share(bull, M["ratio_t"].reindex(d)),
                  "comp_cut_pct": {k: _cut_pct(bull, P2.as_of(M["comp_us"][k], d)) for k in COMPONENTS}}
    old = M["ratio_us"][(M["ratio_us"].index >= pd.Timestamp(P2.OLD[0])) & (M["ratio_us"].index <= pd.Timestamp(P2.OLD[1]))]
    out["old"] = P2.cut_share(~V.on_idx(W["bear"]["US"], old.index), old)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "ratio": round(float(M["ratio_t"].iloc[-1]), 3),
                     "components": {k: round(float(P2.as_of(M["comp_us"][k], M["days"]).iloc[-1]), 3) for k in COMPONENTS}}
    return out


def placebo_density(I: dict, ks: list[int]) -> dict:
    """只数日子：比例序列平移 k 之后，牛的日子里 r < 1 的比例与平均（400 个 k 的平均）—— 与真实的比。"""
    out = {}
    for m in R7.MARKETS:
        c = I["closes"][m]
        days = R7.window_days(c)
        b = I["bulls"][m].reindex(days).fillna(False).to_numpy(bool)
        cuts, means = [], []
        for k in ks:
            x = P2.shifted_num(I["ratios"][m], k).reindex(days).fillna(1.0).to_numpy(float)
            cuts.append(float((x[b] < 1.0 - 1e-12).mean() * 100))
            means.append(float(x[b].mean()))
        out[m] = {"cut_pct": round(float(np.mean(cuts)), 1), "expo_mean_bull": round(float(np.mean(means)), 3)}
    return out


def market_scale(I: dict) -> dict:
    out = {}
    for m, c in I["closes"].items():
        days = R7.window_days(c)
        b = I["bulls"][m].reindex(days).fillna(False).astype(bool)
        comp = I["comps"][m].reindex(days)
        out[m] = {"start": str(c.index[0].date()), "days": int(len(days)), "bull_pct": round(float(b.mean() * 100), 1),
                  **P2.cut_share(b, I["ratios"][m].reindex(days)), "comp_cut_pct": {k: _cut_pct(b, comp[k]) for k in COMPONENTS}}
    n_min = min(v["days"] for m, v in out.items() if m in R7.MARKETS)
    return {"markets": out, "n_min": int(n_min)}


# ───────────────────────── 运行 ─────────────────────────
def run_k(I: dict, k: int | None, keys, ratios: dict | None = None) -> dict[str, list[float | None]]:
    ratios = I["ratios"] if ratios is None else ratios
    return P2.deltas_num({m: I["closes"][m] for m in keys}, {m: ratios[m] for m in keys}, {m: I["bulls"][m] for m in keys}, k,
                         {m: P2.spans_of(I["closes"][m]) for m in keys})


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/combo_strengths_study.py", "scripts/loop7_r01_vctx.py",
                                 "scripts/loop7_r02_voltarget.py", "scripts/loop7_r03_volshock.py", "scripts/research_loop7.py",
                                 "qbreak/timing.py", "qbreak/vct_forward.py", "qbreak/bullbear.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one(W: dict, M: dict) -> dict:
    """第一关（账户，B3 上）：三个年代 B3 / ENB + 1987〜2000 只有核心（S7）；之后只描述：每个成分单独在 B3 上（同一个写法）。"""
    import loop2_r05_ddbrake as R5
    t0 = time.time()
    ov = P2.vtx_over(M["ratio_t"])
    reg = R7.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**P2._acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**P2._acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "ENB": nc}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": P2.old_core(W, None), "ENB": P2.old_core(W, M["ratio_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["ENB"]["calmar"] is None else old["ENB"]["calmar"] - old["B3"]["calmar"]
    s1 = R6.stage1(cand, base, posthoc=unseen)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    comp = {}
    for k in COMPONENTS:                                                     # 只描述（判定之后才算，不影响判定）
        try:
            ovk = P2.vtx_over(P2.as_of(M["comp_us"][k], M["days"]))
            cal = {e: P2._acct(L6.run(W, e, **ovk))["calmar"] for e in L6.ERAS}
            d = {e: (None if cal[e] is None or base[e]["calmar"] is None else round(cal[e] - base[e]["calmar"], 4)) for e in L6.ERAS}
            comp[k] = {"calmar": cal, "d": d, "sum": None if any(v is None for v in d.values()) else round(sum(d.values()), 4)}
        except Exception as ex:                                              # noqa: BLE001
            comp[k] = {"error": f"{type(ex).__name__}: {str(ex)[:120]}"}
    print(f"账户 成分单独 完成（{time.time() - t0:.0f}s）", flush=True)
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "core_trades": trades, "old": old, "drift": drift,
            "components": comp, "scale": account_scale(W, M), "seconds": round(time.time() - t0)}


def stage_two(I: dict) -> dict:
    """第二关（横展开）：17 个市场的真实 Δ + 400 次同一 k 平移 → research_loop7.judge；之后只描述：每个成分单独（不平移）。"""
    t0 = time.time()
    sc = market_scale(I)
    keys = list(R7.MARKETS)
    real = run_k(I, None, keys)
    ks = R7.shift_ks(sc["n_min"])
    plac, per = [], {m: [] for m in keys}
    for i, k in enumerate(ks):
        r = run_k(I, k, keys)
        full = [v[0] for v in r.values()]
        plac.append(None if any(x is None for x in full) else float(np.mean(full)))
        for m in keys:
            per[m].append(r[m][0])
        if (i + 1) % 100 == 0:
            print(f"随机 {i + 1} / {len(ks)}（{time.time() - t0:.0f}s）", flush=True)
    jd = R7.judge(real, plac)
    pct = {m: (round(float(np.mean([1.0 if (p is not None and p < real[m][0]) else 0.0 for p in per[m]]) * 100), 1)
               if real[m][0] is not None else None) for m in keys}
    us = run_k(I, None, list(R7.SOURCE))
    comp_real = {k: run_k(I, None, keys, {m: I["comps"][m][k] for m in keys}) for k in COMPONENTS}
    comp_us = {k: run_k(I, None, list(R7.SOURCE), {m: I["comps"][m][k] for m in R7.SOURCE}) for k in COMPONENTS}
    return {"scale": sc, "placebo_density": placebo_density(I, ks), "real": real, "own_pctile": pct, "us_source": us, "ks": ks,
            "placebo": plac, "judge": jd, "components": comp_real, "components_us": comp_us, "combo": combo_gain(real, comp_real),
            "seconds": round(time.time() - t0)}


def combo_gain(real: dict, comp_real: dict) -> dict:
    """只描述：组合 vs 成分（全窗口 Δ）。"""
    keys = list(real)
    pooled = {k: (float(np.mean([v[m][0] for m in keys])) if all(v[m][0] is not None for m in keys) else None) for k, v in comp_real.items()}
    pos = {k: int(sum(1 for m in keys if v[m][0] is not None and v[m][0] > 0)) for k, v in comp_real.items()}
    ens = float(np.mean([real[m][0] for m in keys])) if all(real[m][0] is not None for m in keys) else None
    vals = [x for x in pooled.values() if x is not None]
    avg = float(np.mean(vals)) if vals else None
    beat = int(sum(1 for m in keys if real[m][0] is not None and all(comp_real[k][m][0] is not None for k in comp_real)
                   and real[m][0] > float(np.mean([comp_real[k][m][0] for k in comp_real]))))
    A = np.array([[comp_real[k][m][0] if comp_real[k][m][0] is not None else np.nan for m in keys] for k in comp_real], float)
    ok = ~np.isnan(A).any(axis=0)
    C = np.corrcoef(A[:, ok]) if ok.sum() >= 3 else None
    mc = None if C is None else float(np.nanmean(C[np.triu_indices(len(C), 1)]))
    return {"ensemble": ens, "component_pooled": pooled, "component_positive": pos, "component_mean": avg,
            "gain": None if ens is None or avg is None else ens - avg, "markets_beat_component_mean": beat,
            "mean_pairwise_corr": None if mc is None else round(mc, 3)}


def run_all() -> int:
    t0 = time.time()
    code, dirty = git_head()
    I = market_inputs()
    W = L6.load3()
    M = account_inputs(W, I)
    a = stage_one(W, M)
    b = stage_two(I)
    jd = b["judge"]
    verdict = R7.FOUND if (a["ok"] and jd["ok"]) else (R7.FAIL1 if not a["ok"] else R7.FAIL2)
    res = {"study": OUT, "ids": list(IDS), "components": list(COMPONENTS), "excluded": EXCLUDED, "posthoc": POSTHOC, "code": code,
           "dirty": dirty, "account": a, "cross": b, "verdict": verdict, "seconds": round(time.time() - t0)}
    write(res)
    return 0


_f = P2._f


def write(res: dict) -> None:
    from qbreak import paths
    a, b = res["account"], res["cross"]
    s, jd, sc = a["stage1"], b["judge"], b["scale"]["markets"]
    pv = s["posthoc"]
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    L = [f"# 各方法长处的等权组合 ENB（11 个离场 / 减仓一侧的核心规则平均；JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/combo_strengths_study.py 开头）", "",
         f"**{res['verdict']}**", "",
         "成分（各 1/11）：" + "、".join(COMPONENTS), "",
         f"## 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
         f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'])}）：{yn(s['S7'])}；S5 / S6 不适用", "",
         "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | ENB（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                      f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L6.ERAS:
        x = a["scale"][e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里 r < 1 的 {_f(x['cut_pct'], '{:.1f}')}%（{x['segments']} 段、这些日子平均 "
                 f"{_f(x['ratio_mean_cut'], '{:.3f}')}；牛的日子平均 {_f(x['expo_mean_bull'], '{:.3f}')}）；核心换仓 B3 {a['core_trades'][e]['B3']} → "
                 f"ENB {a['core_trades'][e]['ENB']} 笔")
    o = a["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'], '{:.3f}')}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、"
        f"美股牛的日子里 r < 1 的 {_f(o[k].get('cut_bull_pct'), '{:.1f}')}%）" for k in ("B3", "ENB")))
    L.append("- 每个成分单独在 B3 上（同一个写法：美股牛 × e_i；Calmar 差 Z / E / J、合计）：" + "；".join(
        (f"{k} {' / '.join(_f(v['d'][e]) for e in L6.ERAS)}（{_f(v['sum'])}）" if "d" in v else f"{k} 算不了（{v.get('error')}）")
        for k, v in a["components"].items()))
    for e in L6.ERAS:
        yb, yc = a["base"][e].get("years") or {}, a["cand"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（ENB − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    lt = a["scale"]["latest"]
    dr = a["drift"]
    L.append(f"- 最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、r = {lt['ratio']}（" +
             "、".join(f"{k} {v}" for k, v in lt["components"].items()) + "）")
    L.append("- B3 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
             + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"))
    cg = b["combo"]
    L += ["", f"## 第二关（横展开，17 个市场）：{'三条都过' if jd.get('ok') else '不过'}",
          f"C1 {yn(jd.get('C1'))}（合并平均 {_f(jd.get('pooled'))}，400 次随机最大 {_f(jd.get('max'))}、≥ 候选 {jd.get('ge_stat')} 次、"
          f"中位 {_f((jd.get('q') or {}).get(50))}、95 分位 {_f((jd.get('q') or {}).get(95))}、99 分位 {_f((jd.get('q') or {}).get(99))}；"
          f"随机比基准好的 {_f(jd.get('pos_share'), '{:.1f}')}%）；C2 {yn(jd.get('C2'))}（Δ > 0 的市场 {jd.get('positive')} / {jd.get('n')}，"
          f"要 ≥ {jd.get('need')}）；C3 {yn(jd.get('C3'))}（前一半 {_f(jd.get('h1'))}、后一半 {_f(jd.get('h2'))}）", "",
          f"组合 vs 成分（只描述）：ENB 合并 {_f(cg['ensemble'])}、11 个成分合并的平均 {_f(cg['component_mean'])} → 组合增益 {_f(cg['gain'])}；"
          f"ENB 比该市场 11 个成分平均好的市场 {cg['markets_beat_component_mean']} / 17；成分之间各市场 Δ 的平均相关 {_f(cg['mean_pairwise_corr'], '{:.2f}')}", "",
          "| 成分 | 合并 Δ | Δ > 0 的市场 | 美国 S&P 500 Δ |", "|---|---:|---:|---:|"]
    for k in COMPONENTS:
        L.append(f"| {k} | {_f(cg['component_pooled'][k])} | {cg['component_positive'][k]} / 17 | {_f(b['components_us'][k]['US'][0])} |")
    L += ["", "| 市场 | 数据起点 | 窗口交易日 | 牛的比例 | 牛里 r < 1 | 段数 | 那些日子平均 | 随机平移后牛里 r < 1 | Δ 全窗口 | Δ 前一半 | Δ 后一半 | 自己的随机百分位 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    pdn = b["placebo_density"]
    for m, (sym, name) in {**R7.MARKETS, **R7.SOURCE}.items():
        x = sc[m]
        v = b["real"][m] if m in R7.MARKETS else b["us_source"][m]
        p = _f(b["own_pctile"][m], "{:.1f}") if m in R7.MARKETS else "—"
        q = f"{_f(pdn[m]['cut_pct'], '{:.1f}')}%" if m in pdn else "—"
        L.append(f"| {name}（{sym}） | {x['start']} | {x['days']} | {x['bull_pct']}% | {_f(x['cut_pct'], '{:.1f}')}% | {x['segments']} | "
                 f"{_f(x['ratio_mean_cut'], '{:.3f}')} | {q} | {_f(v[0])} | {_f(v[1])} | {_f(v[2])} | {p} |")
    L += ["", f"N_min = {b['scale']['n_min']}；随机 = 17 个市场用同一个 k 循环平移比例序列（种子 [20261007, 0, s]，与第七个循环相同的 400 个 k）；"
          "基准 = 自己的牛熊分界（牛 100%、其余现金）；收盘决定、下一个交易日生效；换仓扣 0.1% × 换的比例。",
          f"用时 {res['seconds']} s（账户 {a['seconds']} s、横展开 {b['seconds']} s）。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    I = market_inputs()
    W = L6.load3()
    M = account_inputs(W, I)
    sc = market_scale(I)
    print(json.dumps({"account": account_scale(W, M), "cross": sc, "placebo_density": placebo_density(I, R7.shift_ks(sc["n_min"]))},
                     ensure_ascii=False, indent=1))
    return 0


def _mean_ok(I: dict, m: str) -> bool:
    """T0 牛的日子 r = 11 个成分的平均；其余日子 = T 规则记 1 之后的平均。"""
    comp = I["comps"][m].astype(float).fillna(1.0).clip(0.0, 1.0)
    b = I["bulls"][m].reindex(comp.index).fillna(False).astype(bool).to_numpy()
    plain = comp.mean(axis=1).to_numpy(float)
    masked = comp.assign(**{k: 1.0 for k in T_RULES}).mean(axis=1).to_numpy(float)
    r = I["ratios"][m].to_numpy(float)
    return bool(np.allclose(r[b], plain[b]) and np.allclose(r[~b], masked[~b]))


def wiring() -> int:
    """登记前用（不看候选的结果）：① 比例全 1 → 三个年代与 B3 逐项相同、17 个市场 Δ 全为 0；② old_core 比例全 1 = B3；
    ③ B3 没有别的 core_expo；④ 组合 = 11 个成分的平均、成分 = 登记的函数。"""
    I = market_inputs()
    W = L6.load3()
    M = account_inputs(W, I)
    no_other = {e: "core_expo" not in (W["kw"][e] or {}) and "core_expo" not in (W.get("b1") or {}) for e in L6.ERAS}
    ov1 = P2.vtx_over(pd.Series(1.0, index=M["ratio_t"].index))
    same_b3 = {}
    for e in L6.ERAS:
        rb, r1 = L6.run(W, e), L6.run(W, e, **ov1)
        same_b3[e] = bool(all(rb.get(x) == r1.get(x) for x in KEYS))
    o2 = V.old_core(W, None)
    o3 = P2.old_core(W, pd.Series(1.0, index=M["ratio_us"].index))
    keys = list(R7.MARKETS)
    one = {m: pd.Series(1.0, index=I["ratios"][m].index) for m in keys}
    z, zs = run_k(I, None, keys, one), run_k(I, 1234, keys, one)
    zero = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in z.values())
    zero_shift = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in zs.values())
    mean_ok = all(_mean_ok(I, m) for m in I["ratios"])
    jp = I["closes"]["JP"]
    direct = bool(np.array_equal(I["comps"]["JP"]["T7"].to_numpy(float), _not_bear(T.s7_dual_speed(jp), jp.index).to_numpy(float))
                  and I["comps"]["JP"]["VSX"].equals(P3.shock_ratio(jp).reindex(jp.index).astype(float)))
    out = {"no_other_core_expo": no_other, "ones_same_as_b3": same_b3,
           "old_core_ones_same": bool(o3["calmar"] == o2["calmar"] and o3["cagr"] == o2["cagr"]),
           "markets_ones_zero_delta": zero, "markets_ones_shift_zero_delta": zero_shift, "ensemble_is_mean": mean_ok,
           "components_are_registered_functions": direct}
    print(json.dumps(out, ensure_ascii=False))
    ok = all(no_other.values()) and all(same_b3.values()) and out["old_core_ones_same"] and zero and zero_shift and mean_ok and direct
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="各方法长处的等权组合 ENB（11 个离场 / 减仓一侧的核心规则平均）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
