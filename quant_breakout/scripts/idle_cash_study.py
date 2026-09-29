"""idle_cash_study.py — 没有个股可买时，闲置资金拿什么：几种方式放在账户历史上会怎样、按事先写定的规则选一种
（2026-09-29 登记；只跑一次，看完不改规则）。

用户（2026-09-29）：「另外当没有候选股票的时候默认不要选择 sp500 可以选一个更稳定的也可以 换汇也可以 要考虑各国外汇兑日元的趋势
  或者黄金 etf 石油 etf 什么的做空也可以 如果立花上面可以交易的话」。用户已经决定「默认不要 S&P500」→ 这里不决定「换不换」，
  只按事先写定的规则在立花能买的几种里选一种，结果照实报告（比原规则差也照用户的决定换，但汇报时写在第一行，并写明怎么改回）。
立花能做什么（2026-09-29 查官方公开页面，仅对检索时点有效）：ｅ支店现物可以买卖东证上市的 ETF / ETN（含反向型）；FX、外币存款、MMF、
  投信、美股都没有；做空要另开信用账户（制度信用、只限貸借銘柄、保证金 ≥ 30 万円），执行器只做现物 → 做空 = 现物买反向 ETF；
  「换汇」= 东证的美国短期国债 ETF（不对冲 = 美元现金 + 美国短期利息）。欧元 613A（2026-08 才上市、日均约 133 万円）、
  美元 516A / 517A（立会内日均约 59 / 11 万円）成交太少，澳元没有短期品种 → 能买到量的外币只有美元。
零 方式（qbreak/idle_cash.py，同一次提交写定）：K0 原规则（1655 + 美股牛熊分界；只作参照）、K1 现金、K2 黄金趋势 1540、
   K3 美元趋势 133A、K4 原油趋势 1671、K5 美股熊市买 S&P500 反向 2238（牛市现金）、
   K6 趋势轮动（1540 / 133A / 1671 / 2238 里 12 个月涨得最多的一只，最多的也 ≤ 0 → 现金）。
   趋势 = 月末收盘 > 最近 10 个月末收盘的平均（Faber 的 10 个月线）；轮动 = 12 个月动量（Moskowitz / Ooi / Pedersen）；
   都是教科书参数，这里不调、不试别的长度。
一 账户：与 scripts/exit_mode_check.py 相同（S0C2 + W2：日経225 突破 4 个名额 × 25%、离场 X6（模拟盘 2026-09-30 起的离场）、
   新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜、立花个别コース费用、当时真实的一手）；只换闲置资金那部分。
   前向记录判断层（2026-09-30 起）与 HALT 没有历史，不在里面。窗口 E 2006-10〜2016-09、J 2017-01〜；Z 2001〜2006-09 只描述。
二 资产的日元价格（东证交易日 d = 前一个美国收盘 × d 日早上的 USD/JPY，与 1655 上市前的合成同一个做法；全程合成，不用 ETF 的真实价）：
   1540 = GLD × USD/JPY ÷ 3.11（≈ 每克；GLD 2004-11 以前用 COMEX 金先物 GC=F 按 GLD 首日接上，只影响 Z）；
   133A = 美国 3 个月国库券（FRED DTB3）逐日计息 × USD/JPY × 10，扣年 0.0975% 信託報酬；
   1671 = USO × USD/JPY ÷ 20，再扣年 0.2%（1671 的 0.935% 比 USO 高的部分）；USO 2006-04 才有 → Z 没有原油
     （K4 在 Z 等于现金；K6 在 Z 只在其余三只里轮动）；
   2238 = 日元计价、不乘汇率：每天 −（S&P500 总收益）+ 美国 3 个月利率（先物空头的持有收益）− 年 0.8%（信託報酬 0.73% + 其他）；
   滑点（按 2026-08 日均成交额事先写定，登记进 qbreak/fees.py）：1540 0.03%、133A 0.05%、1671 0.05%、2238 0.20%；一手都是 1 口。
   趋势 / 轮动的判定用这些合成价（= ETF 自己的日元价；实时用真实 ETF 价，同一个函数 qbreak/idle_cash.py）。
三 选择（事先写定）：K1〜K6 里按 min(E 的 Calmar, J 的 Calmar) 最大的选；前两名相差 < 0.02 → 选 E、J 最大回撤平均更浅的，再选编号小的。
   读法（与 K0 原规则比）：E、J 的 Calmar 都比 K0 高 ≥ 0.02 →「历史上比原规则好」；都低 ≥ 0.02 →「历史上比原规则差（照你的决定换，写在第一行）」；
   其余「差不多」。另外写明年化收益差多少（闲置资金占账户的大部分，账户收益主要由它决定）。
四 另报（只描述，不进选择）：GA 一直拿黄金（没有趋势规则 → 看趋势规则本身有没有用）；EW 四只等权一直拿（轮动的对照）；
   FXM 各国外币趋势轮动（美元 / 欧元 / 英镑 / 澳元 / 加元 / 瑞郎 / 纽元，日元计 + 各国 3 个月利率，12 个月最强、≤ 0 → 现金；
   FRED 汇率与 OECD 利率；立花买不到，只回答「各国外汇兑日元的趋势」有没有用）；每个方式拿资产的日子比例、各年收益、
   最新的月末判定（按真实 ETF 价：现在切换的话会拿什么）。
五 照实写：这 25 年黄金（日元计约 +20 倍）与美元（76 → 150 円）都是少见的大行情，按这段历史选会偏向它们；S&P500 的这段历史同样很好；
   只有两个判定窗口、几段大的熊市，样本小。事前预期：K2 或 K6 被选中约 60%，K3 约 15%，K1 约 10%，K4 / K5 约 15%；
   与原规则比「历史上比原规则好」约 35%、「差不多」约 40%、「差」约 25%。
输出：var/out/idle_cash_study.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import exit_rules as EXR                                         # noqa: E402
from qbreak import idle_cash as IC                                           # noqa: E402
from qbreak import paths                                                     # noqa: E402

TAGS = ("E", "J", "Z")
JUDGE = ("E", "J")
CANDS = ("K1", "K2", "K3", "K4", "K5", "K6")
TIE, GAIN = 0.02, 0.02
FEE_PCT = {"133A.T": 0.0975, "1671.T": 0.2, "2238.T": 0.8}                   # 年 %，从合成价里扣（GLD / USO 自己的费用已经在价里）
FX_CCY = {"USD": ("DEXJPUS", None, "DTB3"), "EUR": ("DEXUSEU", "mul", "IR3TIB01EZM156N"), "GBP": ("DEXUSUK", "mul", "IR3TIB01GBM156N"),
          "AUD": ("DEXUSAL", "mul", "IR3TIB01AUM156N"), "CAD": ("DEXCAUS", "div", "IR3TIB01CAM156N"),
          "CHF": ("DEXSZUS", "div", "IR3TIB01CHM156N"), "NZD": ("DEXUSNZ", "mul", "IR3TIB01NZM156N")}
DESC = {"GA": "一直拿黄金 1540（没有趋势规则）", "EW": "四只等权一直拿（1540 / 133A / 1671 / 2238 各 25%）",
        "FXM": "各国外币趋势轮动（7 种外币，12 个月最强；立花买不到，只描述）"}


# ───────────────────────── 合成的日元价格 ─────────────────────────
def prev_on(days: pd.DatetimeIndex, s: pd.Series) -> pd.Series:
    """东证交易日 d 的值 = d 之前最近的一个值（美国收盘在日本时间 d 的早上已知；d 当天的美国收盘不用）。"""
    s = s.dropna().sort_index()
    return s.reindex(days.union(s.index)).ffill().shift(1).reindex(days)


def jp_series(us: pd.Series, fx: pd.Series | None, days: pd.DatetimeIndex, scale: float = 1.0) -> pd.Series:
    v = prev_on(days, us)
    if fx is not None:
        v = v * prev_on(days, fx)
    return (v * scale).dropna()


def accrual(rate_pct: pd.Series, fee_pct: float = 0.0, basis: float = 360.0) -> pd.Series:
    """按日计息的指数（前一个观测日的利率 × 天数 / basis），扣年 fee_pct %。"""
    r = rate_pct.dropna().sort_index()
    dt = r.index.to_series().diff().dt.days.fillna(0).to_numpy(float)
    g = (1 + r.shift(1).fillna(0).to_numpy(float) / 100 * dt / basis) * np.exp(-fee_pct / 100 * dt / 365)
    return pd.Series(np.cumprod(g), index=r.index)


def fee_drag(s: pd.Series, fee_pct: float) -> pd.Series:
    s = s.dropna().sort_index()
    yrs = (s.index - s.index[0]).days.to_numpy(float) / 365.0
    return s * np.exp(-fee_pct / 100 * yrs)


def inverse_index(tr: pd.Series, dtb3: pd.Series, fee_pct: float, start: float = 20000.0) -> pd.Series:
    """S&P500 −1 倍（日元计价、不乘汇率）：每天 −总收益 + 美国 3 个月利率 × 天数 / 360 − 费用。"""
    tr = tr.dropna().sort_index()
    r = tr.pct_change().fillna(0.0)
    dt = tr.index.to_series().diff().dt.days.fillna(0).to_numpy(float)
    rf = prev_on(tr.index, dtb3).fillna(0.0).to_numpy(float) / 100 * dt / 360
    g = 1 - r.to_numpy(float) + rf - fee_pct / 100 * dt / 365
    return pd.Series(start * np.cumprod(np.maximum(g, 0.0)), index=tr.index)


START = "2000-01-01"                                                         # 计息指数从这里起算（一口的价格量级只影响粒度）


def load_inputs() -> dict:
    from bullbear_study import load
    from qbreak import factors
    fx = load("JPY=X", START)["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    gld, gc = load("GLD", "2000-01-01")["Close"], load("GC=F", "2000-01-01")["Close"]
    first = gld.index[0]
    k = float(gld.iloc[0]) / float(gc[gc.index <= first].iloc[-1])
    gold = pd.concat([gc[gc.index < first] * k, gld])
    dtb3 = factors.fred("DTB3")
    return {"fx": fx, "gold": gold, "dtb3": dtb3[dtb3.index >= START], "uso": load("USO", "2000-01-01")["Close"],
            "tr": load("^SP500TR", "2000-01-01")["Close"], "jp_days": load("^N225", "2000-01-01").index}


def assets(inp: dict) -> dict[str, pd.Series]:
    """东证交易日上的合成日元价（四只候选）。"""
    days = pd.DatetimeIndex(inp["jp_days"])
    return {"1540.T": jp_series(inp["gold"], inp["fx"], days, 1 / 3.11),
            "133A.T": jp_series(accrual(inp["dtb3"], FEE_PCT["133A.T"]), inp["fx"], days, 10.0),
            "1671.T": jp_series(fee_drag(inp["uso"], FEE_PCT["1671.T"]), inp["fx"], days, 1 / 20),
            "2238.T": jp_series(inverse_index(inp["tr"], inp["dtb3"], FEE_PCT["2238.T"]), None, days)}


def fx_assets(inp: dict) -> dict[str, pd.Series]:
    """FXM：7 种外币的日元价（FRED 汇率 × 各国 3 个月利率计息）× 20。"""
    from qbreak import factors
    days = pd.DatetimeIndex(inp["jp_days"])
    jpus = factors.fred("DEXJPUS")
    out = {}
    for c, (sid, how, rid) in FX_CCY.items():
        x = factors.fred(sid)
        per = jpus if how is None else (jpus * x if how == "mul" else jpus / x)
        per = per.dropna()
        per = per[per.index >= START]
        rate = factors.fred(rid)
        rate = rate.reindex(per.index.union(rate.index)).ffill().reindex(per.index)
        out[f"FX{c}.T"] = jp_series(per * accrual(rate.fillna(0.0), 0.0, 365.0 if c != "USD" else 360.0), None, days, 20.0)
    return out


def frame(s: pd.Series) -> pd.DataFrame:
    from qbreak.core import core_frame
    return core_frame(pd.DataFrame({"Open": s, "High": s, "Low": s, "Close": s, "Volume": 1e9}, index=s.index))


# ───────────────────────── 方式 → 回测框架的参数 ─────────────────────────
def spec(k: str, px: dict[str, pd.Series], fxp: dict[str, pd.Series]) -> dict:
    """{"cfg_over", "extra_core", "extra_bear"}；K0 = 缺省（sim.json 的 1655 + 美股牛熊分界）。"""
    if k == "K0":
        return {}
    days = pd.DatetimeIndex(sorted(set().union(*[s.index for s in px.values()])))
    if k in IC.MODES:
        m = IC.MODES[k]
        core = dict(m["core"])
        xb = IC.extra_bear(k, px, None, days) if k != "K5" else {}          # K5 的 XR = 研究引擎自己的「美股牛市算熊」
        return {"cfg_over": {"core": core, "core_index": dict(m["core_index"]), "core_mode": m["core_mode"]},
                "extra_core": {t: frame(px[t]) for t in core}, "extra_bear": xb}
    on = {"ON": pd.Series(False, index=days)}
    if k == "GA":
        return {"cfg_over": {"core": {"1540.T": 1.0}, "core_index": {"1540.T": "ON"}, "core_mode": "split"},
                "extra_core": {"1540.T": frame(px["1540.T"])}, "extra_bear": on}
    if k == "EW":
        return {"cfg_over": {"core": {t: 0.25 for t in IC.ROT}, "core_index": {t: "ON" for t in IC.ROT}, "core_mode": "split"},
                "extra_core": {t: frame(px[t]) for t in IC.ROT}, "extra_bear": on}
    if k == "FXM":
        fdays = pd.DatetimeIndex(sorted(set().union(*[s.index for s in fxp.values()])))
        return {"cfg_over": {"core": {t: 1.0 for t in fxp}, "core_index": {t: f"RT:{t}" for t in fxp}, "core_mode": "follow"},
                "extra_core": {t: frame(s) for t, s in fxp.items()}, "extra_bear": IC.rotation_off(fxp, fdays)}
    raise KeyError(k)


def held_share(k: str, px: dict, fxp: dict, us_bear: pd.Series, a: str, b: str | None) -> dict[str, float]:
    """窗口里各资产「开着」（引擎目标 > 0）的交易日比例（%）；K0 = 美股不是熊的日子。"""
    days = pd.DatetimeIndex(sorted(set().union(*[s.index for s in px.values()])))
    w = days[(days >= pd.Timestamp(a)) & ((days <= pd.Timestamp(b)) if b else True)]
    if not len(w):
        return {}
    if k == "K0":
        ub = us_bear.reindex(w.union(us_bear.index)).ffill().reindex(w).fillna(False)
        return {"1655.T": round(float((~ub).mean() * 100), 1)}
    if k == "K5":
        ub = us_bear.reindex(w.union(us_bear.index)).ffill().reindex(w).fillna(False)
        return {"2238.T": round(float(ub.mean() * 100), 1)}
    if k in ("GA", "EW", "K1"):
        return {} if k == "K1" else {t: 100.0 for t in (["1540.T"] if k == "GA" else IC.ROT)}
    sp = spec(k, px, fxp)
    out = {}
    for t, key in sp["cfg_over"]["core_index"].items():
        f = sp["extra_bear"][key].reindex(w.union(sp["extra_bear"][key].index)).ffill().reindex(w).fillna(True)
        out[t] = round(float((~f).mean() * 100), 1)
    return out


def pick(acct: dict) -> tuple[str | None, dict]:
    """事先写定的选择：min(E, J 的 Calmar) 最大；相差 < TIE → E、J 最大回撤平均更浅的，再编号小的。"""
    score = {}
    for k in CANDS:
        c = [acct.get(t, {}).get(k, {}).get("calmar") for t in JUDGE]
        if all(v is not None and np.isfinite(v) for v in c):
            score[k] = float(min(c))
    if not score:
        return None, {}
    best = max(score.values())
    near = [k for k in CANDS if k in score and best - score[k] < TIE]
    near.sort(key=lambda k: (float(np.mean([abs(acct[t][k]["dd"]) for t in JUDGE])), CANDS.index(k)))
    return near[0], score


def reading(acct: dict, k: str) -> str:
    d = [acct[t][k]["calmar"] - acct[t]["K0"]["calmar"] for t in JUDGE]
    if all(x >= GAIN - 1e-12 for x in d):
        return "历史上比原规则好"
    if all(x <= -GAIN + 1e-12 for x in d):
        return "历史上比原规则差（照你的决定换，写在第一行）"
    return "差不多"


def latest_status() -> dict:
    """最新完整月末（按真实 ETF 价）：每个方式现在会拿什么。"""
    from bullbear_study import load
    real = {}
    for t in IC.ROT:
        try:
            real[t] = load(t, "2015-01-01")["Close"]
        except Exception as e:                                               # noqa: BLE001
            print(f"{t} 取不到：{type(e).__name__}", flush=True)
    if not real:
        return {}
    days = pd.DatetimeIndex(sorted(set().union(*[s.index for s in real.values()])))
    me = IC.month_ends(days)
    asof = me[-1] if len(me) else None
    out = {"asof": str(asof.date()) if asof is not None else None}
    for k in ("K2", "K3", "K4"):
        t = next(iter(IC.MODES[k]["core"]))
        if t in real:
            f = IC.trend_off(real[t])
            out[k] = "现金" if bool(f.reindex([asof]).iloc[0]) else IC.NAMES[t]
    if all(t in real for t in IC.ROT):
        p = IC.rotation_pick(real)
        out["K6"] = IC.NAMES.get(p.iloc[-1], "现金") if len(p) and p.iloc[-1] else "现金"
        R = {t: float(real[t].reindex(days).ffill().reindex(me).iloc[-1] / real[t].reindex(days).ffill().reindex(me).iloc[-13] - 1) * 100
             for t in IC.ROT if len(me) >= 13}
        out["K6_12m"] = {t: round(v, 1) for t, v in R.items() if np.isfinite(v)}
    return out


def main() -> int:
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    from refuge_study import us_bear
    t0 = time.time()
    inp = load_inputs()
    px = assets(inp)
    try:
        fxp = fx_assets(inp)
    except Exception as e:                                                  # noqa: BLE001
        print(f"FXM 数据取不到（只影响另报）：{type(e).__name__}: {e}", flush=True)
        fxp = {}
    ub = us_bear()
    p = load_params(market="JP")
    p0, px6 = SF.no_w2_params(p), EXR.apply(p, "X6")
    ks = ["K0", *CANDS, "GA", "EW"] + (["FXM"] if fxp else [])
    acct: dict = {t: {} for t in TAGS}
    years: dict = {t: {} for t in TAGS}
    share: dict = {t: {} for t in TAGS}
    for tag in TAGS:
        ctx = LF.context(tag)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        a, b = ctx["windows"][tag]
        for k in ks:
            if tag == "Z" and k == "K4":
                acct[tag][k] = {"na": "Z 没有原油数据（USO 2006-04 起）：等于现金"}
                continue
            sp = spec(k, px, fxp)
            if tag == "Z" and k in ("K6", "EW"):                             # Z：原油还没有 → 只在其余三只里
                keep = [t for t in IC.ROT if t != "1671.T"]
                co = sp["cfg_over"]
                sp = {"cfg_over": {**co, "core": {t: v for t, v in co["core"].items() if t in keep},
                                   "core_index": {t: v for t, v in co["core_index"].items() if t in keep}},
                      "extra_core": {t: v for t, v in sp["extra_core"].items() if t in keep},
                      "extra_bear": (IC.rotation_off({t: px[t] for t in keep}, pd.DatetimeIndex(inp["jp_days"])) if k == "K6"
                                     else sp["extra_bear"])}
                if k == "EW":
                    sp["cfg_over"]["core"] = {t: 1 / 3 for t in keep}
            r = LF.run(ctx, run_fn, fw, px6, **sp)
            acct[tag][k] = {x: r[tag][x] for x in ("cagr", "dd", "calmar", "tot", "n", "mean", "win")}
            acct[tag][k].update({f"{tag}{h}": r[f"{tag}{h}"]["calmar"] for h in ("1", "2")})
            years[tag][k] = r.get("_years") or {}
            share[tag][k] = held_share(k, px, fxp, ub, a, b)
        print(f"{tag} 完成（{time.time() - t0:.0f}s）：" + "、".join(
            f"{k} {acct[tag][k]['calmar']:.3f}" for k in ks if "calmar" in acct[tag][k] and acct[tag][k]["calmar"] is not None), flush=True)
    chosen, score = pick(acct)
    rd = reading(acct, chosen) if chosen else None
    now = latest_status()
    fa_ = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    lab = {**IC.LABELS, **DESC}
    L = ["# 没有个股可买时，闲置资金拿什么（2026-09-29 登记，只跑一次；规则见本脚本开头与 qbreak/idle_cash.py）", ""]
    if chosen:
        dc = {t: acct[t][chosen]["cagr"] - acct[t]["K0"]["cagr"] for t in JUDGE}
        L += [f"选中：**{chosen} {IC.LABELS[chosen]}**（min(E, J 的 Calmar) = {score[chosen]:.3f}）；与原规则 K0 比：**{rd}**",
              f"年化收益 与 K0 的差：E {dc['E']:+.2f} pp、J {dc['J']:+.2f} pp；最大回撤 E {acct['E'][chosen]['dd']:.2f}% vs {acct['E']['K0']['dd']:.2f}%、"
              f"J {acct['J'][chosen]['dd']:.2f}% vs {acct['J']['K0']['dd']:.2f}%", ""]
    else:
        L += ["★ 没有可比较的结果 → 不选（模拟盘不变）", ""]
    L += ["| 方式 | " + " | ".join(f"{t} 年化 / 最大回撤 / Calmar（前半 / 后半）" for t in TAGS) + " | 选择分 |", "|---|" + "---|" * (len(TAGS) + 1)]
    for k in ks:
        cells = []
        for t in TAGS:
            v = acct[t].get(k, {})
            if "na" in v:
                cells.append(v["na"])
                continue
            cells.append(f"{fa_(v.get('cagr'), '{:+.2f}')}% / {fa_(v.get('dd'))}% / {fa_(v.get('calmar'), '{:.3f}')}"
                         f"（{fa_(v.get(t + '1'), '{:.3f}')} / {fa_(v.get(t + '2'), '{:.3f}')}）")
        L.append(f"| {k} {lab.get(k, k)} | " + " | ".join(cells) + f" | {fa_(score.get(k), '{:.3f}') if k in score else '—'} |")
    L += ["", "拿资产的交易日比例（%；其余日子是现金）："]
    for k in ks:
        L.append(f"- {k}：" + "；".join(f"{t} " + ("、".join(f"{IC.NAMES.get(x, x)} {v:.0f}%" for x, v in share[t].get(k, {}).items()) or "全部现金")
                                     for t in TAGS if t in share and k in share[t]))
    L += ["", "各年收益（%；2006 以前 = Z、2007〜2016 = E、2017〜 = J）："]
    ys = sorted({y for t in TAGS for k in ks for y in (years[t].get(k) or {})})
    show = [k for k in ("K0", chosen, "K1") if k] + [k for k in ks if k not in ("K0", chosen, "K1")]
    L += ["| 方式 | " + " | ".join(ys) + " |", "|---|" + "---|" * len(ys)]
    for k in show:
        vals = {}
        for t, (lo, hi) in (("Z", ("0000", "2006")), ("E", ("2007", "2016")), ("J", ("2017", "9999"))):
            vals.update({y: v for y, v in (years[t].get(k) or {}).items() if lo <= y <= hi})
        L.append(f"| {k} | " + " | ".join(fa_(vals.get(y), "{:+.1f}") for y in ys) + " |")
    if now:
        L += ["", f"最新完整月末 {now.get('asof')}（按真实 ETF 价；仅对这个时点有效）：现在切换的话 —— "
              + "；".join(f"{k} {now[k]}" for k in ("K2", "K3", "K4", "K6") if k in now)
              + ("；12 个月涨跌 " + "、".join(f"{IC.NAMES.get(t, t)} {v:+.1f}%" for t, v in now.get("K6_12m", {}).items()) if now.get("K6_12m") else "")]
    L += ["", "照实写：这 25 年黄金与美元都是少见的大行情、S&P500 也一样，按这段历史选会偏向它们；只有两个判定窗口，样本小。"
          "K5 / K6 里的 S&P500 反向是合成的（−总收益 + 美国短期利率 − 费用）；FXM 立花买不到。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "idle_cash_study"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"chosen": chosen, "reading": rd, "score": score, "accounts": acct, "years": years,
                                              "share": share, "latest": now}, ensure_ascii=False, indent=1, default=float),
                                  encoding="utf-8")
    return 0 if chosen else 2


if __name__ == "__main__":
    raise SystemExit(main())
