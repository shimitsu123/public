"""k4_horizontal_study.py — K4 横向到其他市场：「本国成品油需求走弱 → 个股新仓减半」在别的市场也成立吗；成立就启用 K4
（2026-09-30 用户：「K4横向到其他市场看看 如果表现好的话就直接启用」；登记 = 本提交，提交后不改规则、只运行一次；
  「表现好」的定义与「启用」写在下面，结果出来不改；启用 = 用户在这次对话里的明确要求，通过就改模拟盘并记进 var/sim_changes.md）。

K4（scripts/energy_forward.py 前向记录中）：日本成品油需求（JODI，最近 3 个月合计的同比）< θ = −4.626%（发现期 2006-10〜2015-12 的 30% 分位）
  → 日本个股新仓 ×0.5。它在能源研究（登记 c8b697b）里发现期只 +0.016（门槛 +0.03）没过、验证期是 15 个版本里最好的（事后）→ 只做前向记录；
  现在它作为前向记录判断层的 A5（1 分）已经在影响模拟盘。这次问的是：同一个逻辑用「各国自己的」成品油需求，放到别的市场也成立吗。

一、数据
  - JODI-Oil 各国「成品油合计 需求」（TOTPRODS / TOTDEMO / 千桶 / 日；2002-01 起；年度 CSV 逐年下载，只留下面的国家，派生表缓存在
    var/cache/factors/、不入库）；公布滞后一律按 M + 2 个月（JODI 约 53 天后公布；没有历史版本 → 用现在的修订值，轻微偷看，写进局限；
    印度等报送晚的国家按 M + 2 会多看到一点，同样写进局限）。
  - 指数：threat_intl_study 的 21 个外国市场（yfinance 调整后收盘，缓存 var/cache/threat_intl/）+ 美国 S&P 500 + 日本 日経225；
    另试 韩国 KOSPI（^KS11）与 中国 上证综指（000001.SS）—— 取不到行情就跳过（数据问题，不是规则）。
  - 账户级（两个有个股框架的市场；scripts/market_compare_study.py 同一套：近似时点日経225 × 立花、今天的 S&P 500 × 楽天 / 去掉费用，
    W2 + X6 离场，4 × 25%，只有个股层、闲置资金现金，2006-10-01 起）：日本用 K4 登记的 θ = −4.626%（JODI 日本，M + 2）；
    美国用 EIA 周度成品油供应量（13 周同比，周五截止 + 7 天可用；能源研究 K2 的信号），θ_US = 发现期 30% 分位。
二、指数级（每个市场 m，月末）
  信号 s_m(t) = 该国成品油需求最近 3 个月合计 ÷ 一年前同期 的对数变化（%），按 M + 2 放到月末 t；
  θ_m = s_m 在发现期（2006-10 月末〜2015-12 月末）的 30% 分位（与 K4 同一取法，不再选）；发现期有效月 < 60 → 这个市场不算。
  硬检查：这样算出的 θ_JP 与登记的 −4.626% 相差 ≤ 0.15 pp（JODI 事后修订的余量）；不然停止（数据管道对不上，不出结果）。
  规则：t − 1 月末 s_m < θ_m（缺值 = 不满足）→ t 月指数仓位 ×0.5（其余 0% 现金），否则 100%；评估 2006-11〜最新完整月，
  两半 2006-11〜2016-09 / 2016-10〜；Calmar = 月度权益的年化 ÷ 最大回撤；Δ_m = Calmar(规则) − Calmar(持有)；
  另报 满足月的次月平均收益 − 不满足月的（diff_m，预期为负）、满足月的比例；
  安慰剂：状态序列在评估期内循环平移 k ∈ [12, N − 12] 个月（30 个种子，各市场独立）→ Δ 的 95 分位（各市场）与
  「外国市场平均 Δ」的 95 分位（合并）。评估月 < 120 的市场不参与判定（只列出）。
三、账户级（market_compare_study 的引擎与设定不变）
  JP-T 现行 vs JP-T + K4；US-0（去掉楽天费用，看方法本身）现行 vs + K-US；US-R（楽天费用）现行 vs + K-US（只描述）。
  系数：信号日（≤ 它的最近月末的值）< θ → 0.5，挪到下一交易日成交（energy_study.month_factor + combo_study.fill_scale，与能源研究相同）。
  看 E 2006-10〜2016-09、J 2017-01〜、20 年 2006-10〜最新 的 年化 / 最大回撤 / Calmar、笔数，系数 < 1 的成交日比例。
四、判定（事先写定；「表现好」= 五条全过）
  外国市场 F = 评估月 ≥ 120 的市场（美国算外国、日本不算）：
  H1a F 里 Δ_m ≥ 0 的占比 ≥ 2/3；H1b F 的平均 Δ > 合并安慰剂的 95 分位；H1c F 里 diff_m < 0 的占比 ≥ 2/3；
  H2a US-0 + K-US：20 年 Calmar ≥ 现行 + 0.03，且 E、J 各自 ≥ 现行 − 0.01，且 20 年最大回撤不比现行深 2 pp 以上；
  H2b JP-T + K4：20 年 Calmar ≥ 现行，且 E、J 各自 ≥ 现行 − 0.01（启用不能让日本更差）。
  五条全过 → **启用 K4**：模拟盘 + 执行器的日本个股新仓在 K4 满足时 ×0.5（与判断层 / 原有各层取小；qbreak/fwd_judgment 的 k4_rule 开关，
  var/sim.json 记 since，下一个决策日起；前向记录照旧、判定日不变）；有一条不过 → 不启用，K4 继续只做前向记录（写明哪条没过）。
  日本指数级的结果、US-R、各市场明细都只描述。
五、事前预期（写在运行前）：各国石油需求走弱大多与衰退同步（2008〜09、2020），但 M + 2 的滞后让信号在暴跌之后才亮、反弹时还亮着 →
  Δ_m 正负各半左右、合并平均接近 0；diff_m < 0 的市场应多于一半；账户级 US-0 的个股层本来就弱（Calmar 0.05〜0.25），K-US 的提高不到 +0.03；
  五条全过约 10〜15%，最可能卡在 H1b 与 H2a。
六、局限：JODI 用现在的修订值（没有历史版本）；各国报送速度不同、一律按 M + 2；指数级只是 ×0.5 的粗略规则、不含股息与费用；
  账户级美股用今天的 S&P 500（幸存者偏差）；发现期 θ 与评估期重叠（与 K4 相同的取法，θ 只是分位、没有再选）。
登记前做过的检查：tests/test_k4_horizontal_study.py（θ 的取法、月度规则与 Calmar、循环平移安慰剂、判定）；--smoke 接线检查。
输出：var/out/k4_horizontal_study.md / .json（只有统计）
"""
from __future__ import annotations

import io
import json
import os
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
from qbreak import energy_demand as E                                        # noqa: E402
from qbreak import factors as F                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

W, LAG, Q, HALF = 3, 2, 0.30, 0.5
THETA_JP, THETA_TOL = -4.626, 0.15
DISC = ("2006-10-31", "2015-12-31")
EVAL0, SPLIT = "2006-10-31", "2016-09-30"                                    # 评估的第一个月末（收益从 2006-11 起）、两半分界
MIN_DISC, MIN_MONTHS, SEEDS, SHIFT_MIN = 60, 120, 30, 12
SHARE_2_3, POOL_UP, US_UP, TOL, DD_TOL = 2 / 3, 0.0, 0.03, 0.01, 2.0
MARKETS = {                                                                  # JODI 代码：(指数代码, 名称)
    "US": ("^GSPC", "美国 S&P 500"), "JP": ("^N225", "日本 日経225"), "DE": ("^GDAXI", "德国 DAX"), "GB": ("^FTSE", "英国 FTSE 100"),
    "FR": ("^FCHI", "法国 CAC 40"), "CH": ("^SSMI", "瑞士 SMI"), "NL": ("^AEX", "荷兰 AEX"), "ES": ("^IBEX", "西班牙 IBEX 35"),
    "IT": ("FTSEMIB.MI", "意大利 FTSE MIB"), "BE": ("^BFX", "比利时 BEL 20"), "AT": ("^ATX", "奥地利 ATX"), "IE": ("^ISEQ", "爱尔兰 ISEQ"),
    "AU": ("^AXJO", "澳大利亚 ASX 200"), "NZ": ("^NZ50", "新西兰 NZX 50"), "HK": ("^HSI", "香港 恒生"), "SG": ("^STI", "新加坡 STI"),
    "CA": ("^GSPTSE", "加拿大 TSX"), "TW": ("^TWII", "台湾 加权"), "IN": ("^BSESN", "印度 Sensex"), "BR": ("^BVSP", "巴西 Bovespa"),
    "MX": ("^MXX", "墨西哥 IPC"), "MY": ("^KLSE", "马来西亚 KLCI"), "ID": ("^JKSE", "印尼 雅加达综合"),
    "KR": ("^KS11", "韩国 KOSPI"), "CN": ("000001.SS", "中国 上证综指"),
}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 数据 ─────────────────────────
def jodi_intl(max_age_h: float = 24.0 * 7) -> pd.DataFrame:
    """月初 × 国家代码 的成品油合计需求（千桶 / 日）。"""
    areas = sorted(MARKETS)

    def fetch():
        parts = []
        this = pd.Timestamp.today().year
        for y in range(E.JODI_FIRST, this + 1):
            name = f"secondaryyear{y}" if y == this else str(y)
            try:
                parts.append(E.parse_jodi(F._get(E.JODI_URL.format(name=name), timeout=300), areas, ["TOTPRODS"]))
            except Exception:                                                # noqa: BLE001
                if y < this - 1:
                    raise
        L = pd.concat(parts, ignore_index=True)
        Wd = L.pivot_table(index="month", columns="area", values="value", aggfunc="last")
        Wd.index = pd.DatetimeIndex(pd.to_datetime(Wd.index + "-01"))
        return Wd.sort_index()
    return F._cached("jodi_totprods_intl", fetch, max_age_h)


def month_ends(last: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range("2003-12-31", last, freq="ME")


def theta_of(sig: pd.Series, disc=DISC, q: float = Q, min_n: int = MIN_DISC) -> float | None:
    d = sig[(sig.index >= pd.Timestamp(disc[0])) & (sig.index <= pd.Timestamp(disc[1]))].dropna()
    return None if len(d) < min_n else round(float(d.quantile(q)), 3)


def month_close(close: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    """每个月末：≤ 月末的最后一个收盘（那个月没有交易 → NaN）。"""
    c = close.dropna().sort_index()
    pos = c.index.searchsorted(months, side="right") - 1
    v = c.to_numpy(float)
    out = np.where(pos >= 0, v[np.clip(pos, 0, None)], np.nan)
    stale = np.array([(t - c.index[p]).days > 40 if p >= 0 else True for p, t in zip(pos, months)])
    return pd.Series(np.where(stale, np.nan, out), index=months)


def calmar_m(R: pd.Series) -> dict:
    """月收益序列 → 年化 %、最大回撤 %、Calmar。"""
    r = R.dropna()
    if len(r) < 12:
        return {"cagr": None, "dd": None, "calmar": None, "n": int(len(r))}
    eq = (1 + r).cumprod()
    cagr = (float(eq.iloc[-1]) ** (12 / len(r)) - 1) * 100
    dd = float((eq / eq.cummax() - 1).min() * 100)
    return {"cagr": round(cagr, 2), "dd": round(dd, 2), "calmar": (round(cagr / abs(dd), 3) if dd < 0 else None), "n": int(len(r))}


def rule_returns(r: pd.Series, state: pd.Series) -> pd.Series:
    """t 月收益 × (t − 1 月末满足 → 0.5，否则 1)。"""
    e = state.shift(1).fillna(False).astype(bool).map({True: HALF, False: 1.0})
    return r * e.reindex(r.index).fillna(1.0)


def shifted(state: pd.Series, k: int) -> pd.Series:
    v = state.to_numpy(bool)
    return pd.Series(np.roll(v, k), index=state.index)


def market_eval(close: pd.Series, sig: pd.Series, theta: float, months: pd.DatetimeIndex, seeds: int = SEEDS, rng_seed: int = 0) -> dict:
    """一个市场的指数级结果。"""
    mc = month_close(close, months)
    r = (mc / mc.shift(1) - 1)
    r = r[(r.index > pd.Timestamp(EVAL0))].dropna()
    st = (sig.reindex(months) < theta).fillna(False).astype(bool)
    st = st.reindex(r.index.union([months[months.get_loc(r.index[0]) - 1]])).fillna(False).astype(bool)   # 含评估前一个月末的状态
    ok = st.reindex(r.index).fillna(False).astype(bool)
    n = int(len(r))
    hold = calmar_m(r)
    rule = calmar_m(rule_returns(r, st))
    prev = st.shift(1).reindex(r.index).fillna(False).astype(bool)
    on, off = r[prev], r[~prev]
    out = {"n": n, "theta": theta, "hold": hold, "rule": rule, "delta": (None if hold["calmar"] is None or rule["calmar"] is None else round(rule["calmar"] - hold["calmar"], 3)),
           "on_share": round(float(prev.mean()) * 100, 1), "on_mean": (round(float(on.mean()) * 100, 2) if len(on) else None),
           "off_mean": (round(float(off.mean()) * 100, 2) if len(off) else None),
           "diff": (round(float(on.mean() - off.mean()) * 100, 2) if len(on) and len(off) else None), "halves": {}}
    for tag, (a, b) in {"h1": (EVAL0, SPLIT), "h2": (SPLIT, None)}.items():
        m = (r.index > pd.Timestamp(a)) & ((r.index <= pd.Timestamp(b)) if b else True)
        h, ru = calmar_m(r[m]), calmar_m(rule_returns(r, st)[m])
        out["halves"][tag] = {"hold": h["calmar"], "rule": ru["calmar"], "delta": (None if h["calmar"] is None or ru["calmar"] is None else round(ru["calmar"] - h["calmar"], 3))}
    rng = np.random.default_rng(rng_seed)
    pl = []
    for _ in range(seeds):
        k = int(rng.integers(SHIFT_MIN, max(SHIFT_MIN + 1, len(ok) - SHIFT_MIN)))
        ru = calmar_m(rule_returns(r, shifted(ok, k)))
        pl.append(None if hold["calmar"] is None or ru["calmar"] is None else round(ru["calmar"] - hold["calmar"], 3))
    v = [x for x in pl if x is not None]
    out["placebo"] = {"vals": pl, "q95": (round(float(np.percentile(v, 95)), 3) if v else None), "median": (round(float(np.median(v)), 3) if v else None)}
    return out


# ───────────────────────── 判定 ─────────────────────────
def decide_index(RES: dict) -> dict:
    """RES = {代码: market_eval 结果}；外国市场 = 评估月 ≥ MIN_MONTHS 且不是 JP。"""
    F_ = [k for k, v in RES.items() if k != "JP" and v.get("n", 0) >= MIN_MONTHS and v.get("delta") is not None]
    if not F_:
        return {"F": [], "h1a": False, "h1b": False, "h1c": False, "share_pos": None, "share_neg": None, "pool_mean": None, "pool_q95": None}
    share_pos = sum(1 for k in F_ if RES[k]["delta"] >= 0) / len(F_)
    share_neg = sum(1 for k in F_ if RES[k]["diff"] is not None and RES[k]["diff"] < 0) / len(F_)
    pool_mean = float(np.mean([RES[k]["delta"] for k in F_]))
    per_seed = []
    for s in range(SEEDS):
        vals = [RES[k]["placebo"]["vals"][s] for k in F_ if s < len(RES[k]["placebo"]["vals"]) and RES[k]["placebo"]["vals"][s] is not None]
        if vals:
            per_seed.append(float(np.mean(vals)))
    pool_q95 = float(np.percentile(per_seed, 95)) if per_seed else None
    return {"F": F_, "share_pos": round(share_pos, 3), "share_neg": round(share_neg, 3), "pool_mean": round(pool_mean, 4),
            "pool_q95": (None if pool_q95 is None else round(pool_q95, 4)), "pool_vals": per_seed,
            "h1a": share_pos >= SHARE_2_3 - 1e-12, "h1b": pool_q95 is not None and pool_mean > pool_q95 + POOL_UP, "h1c": share_neg >= SHARE_2_3 - 1e-12}


def decide_account(A: dict) -> dict:
    """A = {"US-0": {"base": {...}, "k": {...}}, "JP-T": {...}}；每个 = {"all": seg, "E": seg, "J": seg}（seg 有 calmar / dd）。"""
    def c(x):
        return -9.0 if x is None else float(x)
    u0, uk = A["US-0"]["base"], A["US-0"]["k"]
    h2a = (c(uk["all"]["calmar"]) >= c(u0["all"]["calmar"]) + US_UP and c(uk["E"]["calmar"]) >= c(u0["E"]["calmar"]) - TOL
           and c(uk["J"]["calmar"]) >= c(u0["J"]["calmar"]) - TOL and c(uk["all"]["dd"]) >= c(u0["all"]["dd"]) - DD_TOL)
    j0, jk = A["JP-T"]["base"], A["JP-T"]["k"]
    h2b = c(jk["all"]["calmar"]) >= c(j0["all"]["calmar"]) and c(jk["E"]["calmar"]) >= c(j0["E"]["calmar"]) - TOL and c(jk["J"]["calmar"]) >= c(j0["J"]["calmar"]) - TOL
    return {"h2a": bool(h2a), "h2b": bool(h2b)}


def verdict(d1: dict, d2: dict) -> tuple[bool, list[str]]:
    fails = []
    for k, lab in (("h1a", "H1a 外国市场 Δ ≥ 0 的占比 ≥ 2/3"), ("h1b", "H1b 外国市场平均 Δ > 合并安慰剂 95 分位"), ("h1c", "H1c 外国市场 diff < 0 的占比 ≥ 2/3")):
        if not d1.get(k):
            fails.append(lab)
    for k, lab in (("h2a", "H2a US-0 + K-US 20 年 Calmar ≥ 现行 + 0.03、E / J 不差 0.01、回撤不深 2 pp"), ("h2b", "H2b JP-T + K4 20 年 ≥ 现行、E / J 不差 0.01")):
        if not d2.get(k):
            fails.append(lab)
    return (not fails), fails


# ───────────────────────── 账户级 ─────────────────────────
def scale_for(sig: pd.Series, theta: float, g: pd.DatetimeIndex) -> pd.Series:
    import combo_study as CB
    import energy_study as ES
    return CB.fill_scale(ES.month_factor(sig, theta, g), g)


def acct_stats(r, market: str, MC, idx_close: pd.Series, fx_close: pd.Series, days: pd.DatetimeIndex, spread: float) -> dict:
    import capital_study as CS
    sm = MC.summarize(r, market, idx_close, fx_close, days, spread)
    out = {w: {**sm[w]["acct"], "trades": sm[w]["trades"].get("n"), "win": sm[w]["trades"].get("win"), "mean": sm[w]["trades"].get("mean")} for w in MC.WIN}
    out["all"] = CS.seg_stats(r.equity, MC.START, None)
    return out


def run_accounts(smoke: bool, theta_us: float, sig_jp: pd.Series, sig_us: pd.Series) -> dict:
    import equity_idle_study as EQ
    import market_compare_study as MC
    from dataclasses import replace
    from qbreak import exit_rules as EXR
    from qbreak.config import ExecConfig
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    t0 = time.time()
    L = MC.load_all()
    pj = load_params(market="JP")
    px6 = EXR.apply(pj, "X6")
    bear = {m: EQ.t0_bear(L["idx"][m]["Close"]) for m in ("JP", "US")}
    ex = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    ex0 = {**ex, "US": replace(ex["US"], commission_pct=0.0, commission_max=0.0)}

    def build(data: dict, p) -> dict:
        return {t: compute_indicators(df, p) for t, df in data.items() if len(df) >= 300}
    jp_data, us_data = L["jp"], L["us"]
    if smoke:
        jp_data = {t: jp_data[t] for t in list(jp_data)[:8]}
        us_data = {t: us_data[t] for t in list(us_data)[:8]}
    jp_ind = MC.membership(build(jp_data, px6), "JP", L["added"])
    us_ind = MC.membership(build(us_data, px6), "US", L["added"])
    say(f"- 账户级数据与指标（{time.time() - t0:.0f} s）：日本 {len(jp_ind)} 只、美国 {len(us_ind)} 只")
    em = {"JP": MC.entry_mult(jp_ind, "JP", L["idx"]["JP"], L["d21"]), "US": MC.entry_mult(us_ind, "US", L["idx"]["US"], L["d21"])}
    sc = {"JP": scale_for(sig_jp, THETA_JP, em["JP"].index), "US": scale_for(sig_us, theta_us, em["US"].index)}
    emk = {m: em[m].mul(sc[m].reindex(em[m].index).fillna(1.0), axis=0) for m in em}
    ratio = MC.jp_ratio(list(jp_ind))
    fx, q1 = L["fx"], L["q1"]
    params = {"JP": px6, "US": px6}
    runs = {("JP-T", "base"): MC.run_arm("JP", jp_ind, em, bear, fx, params, ex, ratio),
            ("JP-T", "k"): MC.run_arm("JP", jp_ind, emk, bear, fx, params, ex, ratio),
            ("US-0", "base"): MC.run_arm("US", us_ind, em, bear, fx, params, ex0, {}, fx_spread_yen=0.0, passive=q1),
            ("US-0", "k"): MC.run_arm("US", us_ind, emk, bear, fx, params, ex0, {}, fx_spread_yen=0.0, passive=q1),
            ("US-R", "base"): MC.run_arm("US", us_ind, em, bear, fx, params, ex, {}, passive=q1),
            ("US-R", "k"): MC.run_arm("US", us_ind, emk, bear, fx, params, ex, {}, passive=q1)}
    say(f"- 账户级回测完成（{time.time() - t0:.0f} s）")
    idx_close = {m: L["idx"][m]["Close"] for m in ("JP", "US")}
    days = {m: L["idx"][m].index for m in ("JP", "US")}
    A: dict = {}
    for (arm, kind), r in runs.items():
        m = "JP" if arm.startswith("JP") else "US"
        A.setdefault(arm, {})[kind] = acct_stats(r, m, MC, idx_close[m], fx["Close"], days[m], 0.0 if arm == "US-0" else 0.03)
    A["on_share"] = {m: round(float((sc[m] < 1).mean()) * 100, 1) for m in sc}
    A["theta"] = {"JP": THETA_JP, "US": theta_us}
    return A


# ───────────────────────── 主流程 ─────────────────────────
def main(argv=None) -> int:
    import threat_intl_study as TI
    argv = list(sys.argv[1:] if argv is None else argv)
    smoke = "--smoke" in argv or os.environ.get("QBREAK_SMOKE") == "1"
    seeds = 2 if smoke else SEEDS
    t0 = time.time()
    root = str(paths.PROJECT_ROOT)
    code = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    watched = ["scripts/k4_horizontal_study.py", "scripts/market_compare_study.py", "qbreak/energy_demand.py", "scripts/energy_study.py", "scripts/combo_study.py"]
    dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", *watched], capture_output=True, text=True).stdout.strip())
    say(f"# K4 横向到其他市场（登记检验，{pd.Timestamp.today().date()}；代码 {code}{'（脏）' if dirty else ''}）")
    say("规则与判定见 scripts/k4_horizontal_study.py 开头（先提交后运行、只运行一次）。")
    J = jodi_intl()
    last = pd.Timestamp(J.index[-1]) + pd.offsets.MonthEnd(0)
    months = month_ends(pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(-1))
    say(f"- JODI 成品油需求：{len(J.columns)} 个国家、{J.index[0].date()}〜{J.index[-1].date()}")
    sigs = {k: E.monthly_growth(J[k], months, W, LAG) for k in MARKETS if k in J.columns}
    th_jp = theta_of(sigs["JP"])
    say(f"- 硬检查：θ_JP 重算 {th_jp} vs 登记 {THETA_JP}（容差 {THETA_TOL} pp）→ {'一致' if th_jp is not None and abs(th_jp - THETA_JP) <= THETA_TOL else '**不一致**'}")
    if th_jp is None or abs(th_jp - THETA_JP) > THETA_TOL:
        if not smoke:
            raise RuntimeError("θ_JP 与登记值不一致 → 停止")
    keys = list(MARKETS) if not smoke else ["JP", "US", "DE"]
    RES: dict = {}
    skipped: dict = {}
    for k in keys:
        sym, nm = MARKETS[k]
        if k not in sigs:
            skipped[k] = "JODI 没有这个国家"
            continue
        th = theta_of(sigs[k])
        if th is None:
            skipped[k] = f"发现期有效月 < {MIN_DISC}"
            continue
        try:
            close, _ = TI.index_close(sym)
        except Exception as e:                                                # noqa: BLE001
            skipped[k] = f"行情取不到：{type(e).__name__}"
            continue
        if not len(close):
            skipped[k] = "行情为空"
            continue
        RES[k] = {**market_eval(close, sigs[k], th, months, seeds=seeds, rng_seed=sum(map(ord, k))), "name": nm, "sym": sym}
    say(f"- 指数级算完 {len(RES)} 个市场（跳过 {len(skipped)}：{skipped}）；{time.time() - t0:.0f} s")
    d1 = decide_index(RES)
    # 账户级
    raw = E.load_all()
    X3 = E.signals(raw, months, (3,))[3]
    sig_jp, sig_us = X3["jp_total"], X3["us_total"]
    theta_us = theta_of(sig_us)
    say(f"- 账户级信号：日本 θ = {THETA_JP}（登记值）、美国 EIA 13 周同比 θ_US = {theta_us}（发现期 30% 分位）")
    A = run_accounts(smoke, theta_us, sig_jp, sig_us)
    d2 = decide_account(A)
    ok, fails = verdict(d1, d2)
    if smoke:
        say("\n（--smoke：只做接线检查，不写结果）")
        return 0
    fmt = lambda s: ("—" if not s or s.get("calmar") is None else f"{s['cagr']:.2f}% / {s['dd']:.2f}% / {s['calmar']:.3f}")   # noqa: E731
    say("\n## 一、指数级（月度；规则 = 上月末本国成品油需求 3 个月同比 < θ → 当月指数仓位 ×0.5；Calmar 持有 → 规则 · Δ · 两半 Δ · 满足月比例 · 满足月次月均值 − 不满足月 · 安慰剂 Δ 95 分位）")
    say("| 市场 | 评估月 | θ | 持有 | 规则 | Δ | Δ 前半 / 后半 | 满足月 % | diff pp | 安慰剂 中位 / 95 分位 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for k in sorted(RES, key=lambda k: -(RES[k]["delta"] if RES[k]["delta"] is not None else -9)):
        x = RES[k]
        h = x["halves"]
        pf = lambda v, f="{:+.3f}": "—" if v is None else f.format(v)                              # noqa: E731
        tag = "（不参与判定）" if x["n"] < MIN_MONTHS or k == "JP" else ""
        say(f"| {x['name']}{tag} | {x['n']} | {x['theta']} | {fmt(x['hold'])} | {fmt(x['rule'])} | {pf(x['delta'])} | "
            f"{pf(h['h1']['delta'])} / {pf(h['h2']['delta'])} | {x['on_share']} | {pf(x['diff'], '{:+.2f}')} | {x['placebo']['median']} / {x['placebo']['q95']} |")
    say(f"- 外国市场 F（评估月 ≥ {MIN_MONTHS}、不含日本）{len(d1['F'])} 个：Δ ≥ 0 的占比 {d1['share_pos']}、diff < 0 的占比 {d1['share_neg']}、"
        f"平均 Δ {d1['pool_mean']:+.4f} vs 合并安慰剂 95 分位 {d1['pool_q95']}")
    say("\n## 二、账户级（个股层，2006-10-01 起；年化 / 最大回撤 / Calmar；E 2006-10〜2016-09、J 2017-01〜、20 年）")
    say("| 账户 | 方案 | E | J | 20 年 | 20 年笔数 |")
    say("|---|---|---|---|---|---|")
    for arm in ("JP-T", "US-0", "US-R"):
        for kind, lab in (("base", "现行"), ("k", "+ K4" if arm == "JP-T" else "+ K-US")):
            s = A[arm][kind]
            say(f"| {arm} | {lab} | {fmt(s['E'])}（{s['E'].get('trades')} 笔） | {fmt(s['J'])}（{s['J'].get('trades')} 笔） | {fmt(s['all'])} | — |")
    say(f"- 系数 < 1 的成交日比例：日本 {A['on_share']['JP']}%、美国 {A['on_share']['US']}%；θ_US {A['theta']['US']}")
    say("\n## 三、判定（事先写定：五条全过才启用）")
    for k, lab, v in (("h1a", "H1a", d1["h1a"]), ("h1b", "H1b", d1["h1b"]), ("h1c", "H1c", d1["h1c"]), ("h2a", "H2a", d2["h2a"]), ("h2b", "H2b", d2["h2b"])):
        say(f"- {lab}：{'过' if v else '不过'}")
    say(f"\n**结论：{'五条全过 → 启用 K4（模拟盘 + 执行器：K4 满足时日本个股新仓 ×0.5，与各层取小；记进 sim_changes）' if ok else '不启用（没过：' + '；'.join(fails) + '）→ K4 继续只做前向记录'}**")
    say(f"- 用时 {time.time() - t0:.0f} s。非投资建议。")
    out = {"git": code, "dirty": dirty, "theta_jp_recomputed": th_jp, "markets": RES, "skipped": skipped, "index_decision": d1, "account": A,
           "account_decision": d2, "enable": ok, "fails": fails, "seeds": seeds, "elapsed_s": round(time.time() - t0), "lines": list(LINES)}
    fp = paths.out_dir() / "k4_horizontal_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
