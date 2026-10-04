"""loop8_r01_vrp.py — 第八个研究循环（新的独立信息来源）第 1 轮：期权的波动风险溢价 VRP（隐含方差 − 已实现方差）→ 信息检查 + 规则 VRN
（2026-10-04 登记；先提交后只运行一次；来源「期权·波动风险溢价」1 / 3；不是事后（这个项目里 VRP 从没算过）→ S7 不适用）。

用户（2026-10-04）：「进行真正提高，需要新的、独立的信息来源的研究」。循环的规则：scripts/research_loop8.py 开头。
为什么第一个做这个（照实写）：
  - 期权价格里的「隐含方差」= 市场为之后一个月的波动付的价；减去最近一个月实际的「已实现方差」= 波动风险溢价 VRP（variance risk premium）。
    文献：Bollerslev, Tauchen & Zhou（2009, Review of Financial Studies）美国 1990〜2007：VRP 高 → 之后一个季度股票收益高（方向 +）；
    Bollerslev, Marrone, Xu & Zhou（2014, Journal of Financial and Quantitative Analysis）8 个发达市场 2000〜2011 同样成立；
    Bekaert & Hoerova（2014, Journal of Econometrics）：VRP 预测股票收益、条件方差预测经济。
  - 与这个项目以前的「危险」信号不同：说的是「之后涨多少」（方向）；大跌之后恐慌还在、实际波动已经下来时 VRP 高 = 该拿，
    实际的动荡超过期权市场预期时 VRP < 0 = 不该满仓 —— 正好对着「危险信号在反弹里少赚」的毛病（09-30 研究习惯 ④）。
  - 以前只把 VIX 的水平（与 20 日变化）当「危险」因素用过（威胁指数、T4 / T6），「隐含 − 已实现」从没算过。
数据（登记前只核对了起止日期、有无缺口与拼接，没算任何收益；原始数据只在已 gitignore 的 var/cache/）：
  US：VIX（FRED VIXCLS，1990-01-02〜）× S&P 500（^GSPC）；EU：VSTOXX（STOXX h_v2tx.txt，1999-01-04〜）× EURO STOXX 50（STOXX hbrbcpe.txt 的 SX5E
  1986-12-31〜2016-10-04，之后接 Yahoo ^STOXX50E（2007-03-30〜），按重叠期比值的中位数接上）；AU：S&P/ASX 200 VIX（^AXVI，2008〜）× ASX 200（^AXJO）；
  IN：India VIX（^INDIAVIX，2008-03〜）× Nifty 50（^NSEI）；BR：CBOE EWZ 波动率（FRED VXEWZCLS，2011-03〜）× EWZ（美元 ETF，含分红调整）。
  只描述：纳斯达克 100：VXN（FRED VXNCLS，2001-02〜）× ^NDX。日本（日経 VI 拒绝程序访问）、香港、韩国、中国（VXFXI 2022 年停）没有可用的每日数据 → 不收。
信号：VRP_t = (IV_t / 100)² − RV22_t；RV22_t = 252 / 22 × 最近 22 个交易日（含当天）日对数收益的平方和（年化方差）；IV 在标的的交易日上取日期 ≤ 当天的
  最近一个值（最多回看 5 天，再旧 = 空）。
A 信息检查（research_loop8 二 A）：市场 US、EU、AU、IN、BR；样本 = 各自已结束的月末（VRP 与目标都有值）；目标 = 月末之后第 1 个交易日起 63 个交易日的
  对数收益；方向 +（文献）；IC = Spearman；合并 = 5 个市场等权；联合区块自助法（12 个月一块、2,000 次、种子 20261010）→ 单侧 p；
  I1 合并 IC > 0 且 p ≤ 0.10；I2 IC > 0 的市场 ≥ 4 / 5；I3 2012-01 以后（BMXZ 2014 的样本到 2011 年 → 之后 = 文献发表之后）的合并 IC > 0。
B 规则 VRN（A 过了才运行；规则现在写定）：每个已结束的月末收盘：T0 牛 ∧ VRP ≤ 0（实际的波动超过期权市场的预期 = 风险溢价为负）→ 到下一个月末为止
  核心拿 2/3、1/3 现金；其余牛 → 100%；熊 → 照旧。月中不改（月度决定，同文献的月度样本）；T0 月中翻熊照旧离场。
  第一关（账户，B3 上）：美国 S&P 500 的 VRP（VIX）→ 东证日（美国日期 ≤ 东证日，同 B3 的美股熊）→ 1545 的 core_expo["US"]
    （loop7_r02_voltarget.vtx_over，同 VTX / VSX / ENB；减下来的留现金）；research_loop6.stage1（S1〜S4；S7 不适用；1987〜2000 只有核心照报、只描述）。
  第二关（横展开，US / EU / AU / IN 4 个市场；BR 历史太短只进 A）：窗口 2009-01-01〜2026-09-30；基准 = 自己的牛熊分界（牛 100%、其余现金）；
    比例序列在窗口内同一个 k 循环平移 400 次（k ∈ [250, N_min − 250]，numpy default_rng([20261011, 0, s])）；research_loop7.judge
    （合并 > 0 且严格大于 400 次最大、Δ > 0 的市场 ≥ 3 / 4、两半的合并都 > 0）。
判定：A 不过 →「信息检查不过」（B 不运行）；A 过 → 更好候选 / 第一关不过 / 第二关不过。
只描述：各市场 IC（全样本 / 2012 年以后 / 美国 1990〜2007 = 文献样本内）、VRP 五分位之后 63 天的平均收益、牛市月末 VRP ≤ 0 与 > 0 之后的平均收益、
  21 天目标的合并 IC、纳指 100（VXN）的 IC；B：各市场 Δ、各自的随机百分位、核心换仓笔数、每年收益差。
接线核对（--wiring，不看任何收益）：比例全 1 → 三个年代与 B3 逐项相同、4 个市场 Δ 全为 0；月度比例只在月末之后变（tests/test_loop8_r01.py）。
规模（--scale，只数日子）：各市场数据起止、可用月末数、VRP ≤ 0 的月末比例（全部 / T0 牛）、规则在牛市日子里减仓的比例、EU 拼接的比值。
运行：python scripts/loop8_r01_vrp.py（只运行一次）；--scale；--wiring。输出 var/out/loop8_r01_vrp.md / .json。非投资建议。
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
import loop7_r02_voltarget as P2                                             # noqa: E402
import research_loop7 as R7                                                  # noqa: E402
import research_loop8 as RL8                                                 # noqa: E402

ROUND = 1
FAMILY = "期权·波动风险溢价"
IDS = ("VRN",)
POSTHOC = False
RV_N = 22
IV_TOL_DAYS = 5
THRESH = 0.0                                                                 # VRP ≤ 0 → 减
KEEP = 2.0 / 3.0
MARKETS = {"US": ("美国 S&P 500", "VIX"), "EU": ("欧元区 EURO STOXX 50", "VSTOXX"), "AU": ("澳大利亚 ASX 200", "S&P/ASX 200 VIX"),
           "IN": ("印度 Nifty 50", "India VIX"), "BR": ("巴西 EWZ（美元）", "CBOE EWZ 波动率")}
DESC = {"NDX": ("美国 纳斯达克 100（只描述）", "VXN")}
CROSS = ("US", "EU", "AU", "IN")
WINDOW_B = ("2009-01-01", "2026-09-30")
POST = "2012-01-01"
LIT_END = "2007-12-31"                                                       # Bollerslev, Tauchen & Zhou（2009）的样本到 2007 年
H_SHORT = 21
SEED_INFO, SEED_B = 20261010, 20261011
PLACEBO_N, SHIFT_GAP = 400, 250
OUT = "loop8_r01_vrp"
STOXX = "https://www.stoxx.com/download/historical_values/{}"


# ───────────────────────── 数据（原始数据只进 var/cache/factors，已 gitignore） ─────────────────────────
def _stoxx_text(fname: str) -> str:
    from qbreak import factors as F
    return F._get(STOXX.format(fname)).decode("utf-8", "replace")


def parse_v2tx(text: str) -> pd.Series:
    """STOXX h_v2tx.txt：Date;Symbol;Indexvalue（日.月.年）。"""
    out = {}
    for ln in text.splitlines()[1:]:
        p = [x.strip() for x in ln.split(";")]
        if len(p) >= 3 and p[0] and p[2]:
            try:
                out[pd.to_datetime(p[0], format="%d.%m.%Y")] = float(p[2])
            except ValueError:
                continue
    s = pd.Series(out, dtype=float).sort_index().rename("V2TX")
    return s[s > 0]


def parse_sx5e(text: str) -> pd.Series:
    """STOXX hbrbcpe.txt（Blue-Chip / Broad 价格指数）里的 SX5E 列（第 3 列）；0 / 负数 = 休市日的占位（例 2016-03-25 / 03-28 复活节）→ 去掉。"""
    out = {}
    for ln in text.splitlines():
        p = [x.strip() for x in ln.split(";")]
        if len(p) >= 3 and len(p[0]) == 10 and p[0][2] == "." and p[0][5] == ".":
            try:
                out[pd.to_datetime(p[0], format="%d.%m.%Y")] = float(p[2])
            except ValueError:
                continue
    s = pd.Series(out, dtype=float).sort_index().rename("SX5E")
    return s[s > 0]


def v2tx() -> pd.Series:
    from qbreak import factors as F
    return F._cached("stoxx_v2tx", lambda: parse_v2tx(_stoxx_text("h_v2tx.txt")))


def sx5e_old() -> pd.Series:
    from qbreak import factors as F
    return F._cached("stoxx_sx5e_hbrbcpe", lambda: parse_sx5e(_stoxx_text("hbrbcpe.txt")), max_age_h=24 * 30)


def splice(old: pd.Series, new: pd.Series) -> tuple[pd.Series, dict]:
    """old（到它的最后一天）接 new（之后），new 按重叠期 new / old 的中位数缩放；返回 (序列, 重叠期比值的统计)。"""
    old, new = old.dropna().sort_index(), new.dropna().sort_index()
    old, new = old[old > 0], new[new > 0]
    ov = old.index.intersection(new.index)
    if len(ov) < 250:
        raise RuntimeError(f"拼接的重叠期太短（{len(ov)} 天）")
    rt = (new.reindex(ov) / old.reindex(ov)).astype(float)
    k = float(np.median(rt))
    tail = new[new.index > old.index[-1]] / k
    s = pd.concat([old, tail]).sort_index()
    return s[~s.index.duplicated(keep="first")], {"overlap_days": int(len(ov)), "ratio_median": round(k, 5),
                                                    "ratio_p01": round(float(rt.quantile(0.01)), 5), "ratio_p99": round(float(rt.quantile(0.99)), 5)}


def yf_raw(sym: str) -> pd.Series:
    """Yahoo 收盘（波动率指数不去「错价」：一天翻倍是真的）。"""
    from qbreak import factors as F
    s = F.yf_close(sym)
    return s[s > 0].dropna().sort_index()


def load_market(m: str) -> dict:
    """{"close": 标的收盘, "iv": 波动率指数, "note": …}。"""
    from qbreak import factors as F
    if m == "US":
        return {"close": R7.load_close("^GSPC"), "iv": F.fred("VIXCLS"), "note": "VIX（FRED VIXCLS）× ^GSPC"}
    if m == "NDX":
        return {"close": R7.load_close("^NDX"), "iv": F.fred("VXNCLS"), "note": "VXN（FRED VXNCLS）× ^NDX"}
    if m == "EU":
        close, st = splice(sx5e_old(), R7.load_close("^STOXX50E"))
        return {"close": close, "iv": v2tx(), "note": "VSTOXX（STOXX V2TX）× EURO STOXX 50（STOXX SX5E 接 Yahoo ^STOXX50E）", "splice": st}
    if m == "AU":
        return {"close": R7.load_close("^AXJO"), "iv": yf_raw("^AXVI"), "note": "S&P/ASX 200 VIX（^AXVI）× ^AXJO"}
    if m == "IN":
        return {"close": R7.load_close("^NSEI"), "iv": yf_raw("^INDIAVIX"), "note": "India VIX（^INDIAVIX）× ^NSEI"}
    if m == "BR":
        return {"close": R7.load_close("EWZ"), "iv": F.fred("VXEWZCLS"), "note": "CBOE EWZ 波动率（FRED VXEWZCLS）× EWZ"}
    raise KeyError(m)


# ───────────────────────── 信号与规则（纯函数，tests/test_loop8_r01.py） ─────────────────────────
def align_iv(iv: pd.Series, idx: pd.DatetimeIndex, tol_days: int = IV_TOL_DAYS) -> pd.Series:
    """标的交易日上：日期 ≤ 当天的最近一个 IV（最多回看 tol_days 天）。"""
    s = iv.dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index().astype(float)
    return s.reindex(pd.DatetimeIndex(idx), method="ffill", tolerance=pd.Timedelta(days=tol_days))


def realized_var(close: pd.Series, n: int = RV_N) -> pd.Series:
    """252 / n × 最近 n 个日对数收益的平方和（至少 n 个）。"""
    r = np.log(close.dropna().astype(float)).diff()
    return (r ** 2).rolling(n, min_periods=n).sum() * (252.0 / n)


def vrp(close: pd.Series, iv: pd.Series) -> pd.DataFrame:
    c = close.dropna().sort_index().astype(float)
    ivs = align_iv(iv, c.index)
    rv = realized_var(c)
    return pd.DataFrame({"iv": ivs, "rv": rv, "vrp": (ivs / 100.0) ** 2 - rv}, index=c.index)


def ratio_vrn(close: pd.Series, vrp_s: pd.Series, thresh: float = THRESH, keep: float = KEEP) -> pd.Series:
    """月度比例：已结束的月末收盘 VRP ≤ thresh → 到下一个月末为止 keep，否则 1；第一个月末之前 / VRP 算不了 = 1。
    月末当天就用当天的值（收盘决定，research_loop7.nav 从下一个交易日起生效）。"""
    c = close.dropna().sort_index()
    me = RL8.month_ends_done(c)
    v = vrp_s.reindex(me)
    r_me = pd.Series(np.where(v.to_numpy(float) <= thresh, keep, 1.0), index=me)
    r_me[v.isna()] = 1.0
    out = r_me.reindex(c.index.union(me)).ffill().reindex(c.index).fillna(1.0)
    return out.astype(float)


def samples(close: pd.Series, vrp_s: pd.Series, h: int = RL8.H) -> pd.DataFrame:
    """信息检查的样本：已结束的月末 → x = 当天 VRP、y = 之后第 1 个交易日起 h 天的对数收益（两者都有值的）。"""
    d = RL8.month_ends_done(close)
    return pd.DataFrame({"x": vrp_s.reindex(d), "y": RL8.fwd_log_ret(close, d, h)}, index=d).dropna()


def spans_of(c: pd.Series, w=WINDOW_B) -> list[tuple[str, str]]:
    days = R7.window_days(c, w)
    h1, h2 = R7.halves(days)
    return [(str(days[0].date()), str(days[-1].date())), h1, h2]


def shift_ks(n_min: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    if n_min <= 2 * gap:
        raise ValueError(f"窗口太短（{n_min} ≤ {2 * gap}）")
    return [int(np.random.default_rng([SEED_B, 0, int(s)]).integers(gap, n_min - gap + 1)) for s in seeds]


def deltas(closes: dict, ratios: dict, bulls: dict, k: int | None, w=WINDOW_B) -> dict[str, list[float | None]]:
    """每个市场：窗口 / 前一半 / 后一半的 Calmar（候选 = 牛 × 平移后的比例）− 基准（牛 100%）。"""
    out = {}
    for m, c in closes.items():
        b = bulls[m]
        base = R7.nav(c, b.astype(float))
        cand = R7.nav(c, P2.expo(b, P2.shifted_num(ratios[m], k, w)))
        row = []
        for a, z in spans_of(c, w):
            cb, cc = R7.calmar(base, a, z), R7.calmar(cand, a, z)
            row.append(None if cb is None or cc is None else cc - cb)
        out[m] = row
    return out


# ───────────────────────── A 信息检查 ─────────────────────────
def quintile_means(df: pd.DataFrame) -> list[float | None]:
    if len(df) < 25:
        return [None] * 5
    q = pd.qcut(df["x"].rank(method="first"), 5, labels=False)
    return [round(float(df["y"][q == i].mean() * 100), 2) for i in range(5)]


def info_check(D: dict) -> dict:
    S = {m: samples(D[m]["close"], D[m]["vrp"]["vrp"]) for m in MARKETS}
    ics = {m: RL8.spearman(S[m]["x"], S[m]["y"]) for m in MARKETS}
    post = {m: RL8.spearman(S[m]["x"][S[m].index >= pd.Timestamp(POST)], S[m]["y"][S[m].index >= pd.Timestamp(POST)]) for m in MARKETS}
    boot = RL8.joint_bootstrap(S, seed=SEED_INFO)
    jd = RL8.info_judge(ics, post, boot, sign=+1)
    desc = {}
    for m in list(MARKETS) + list(DESC):
        s = samples(D[m]["close"], D[m]["vrp"]["vrp"])
        s21 = samples(D[m]["close"], D[m]["vrp"]["vrp"], H_SHORT)
        b = D[m]["bull"].reindex(s.index).fillna(False).astype(bool)
        lo, hi = s[b & (s["x"] <= THRESH)], s[b & (s["x"] > THRESH)]
        desc[m] = {"n": int(len(s)), "first": str(s.index[0].date()) if len(s) else None, "last": str(s.index[-1].date()) if len(s) else None,
                   "ic": RL8.spearman(s["x"], s["y"]), "ic_post": RL8.spearman(s["x"][s.index >= pd.Timestamp(POST)], s["y"][s.index >= pd.Timestamp(POST)]),
                   "ic21": RL8.spearman(s21["x"], s21["y"]), "quintiles_pct": quintile_means(s),
                   "bull_neg": {"n": int(len(lo)), "mean_pct": round(float(lo["y"].mean() * 100), 2) if len(lo) else None},
                   "bull_pos": {"n": int(len(hi)), "mean_pct": round(float(hi["y"].mean() * 100), 2) if len(hi) else None}}
    us = samples(D["US"]["close"], D["US"]["vrp"]["vrp"])
    desc["US"]["ic_lit"] = RL8.spearman(us["x"][us.index <= pd.Timestamp(LIT_END)], us["y"][us.index <= pd.Timestamp(LIT_END)])
    desc["US"]["ic_after_lit"] = RL8.spearman(us["x"][us.index > pd.Timestamp(LIT_END)], us["y"][us.index > pd.Timestamp(LIT_END)])
    s21 = {m: samples(D[m]["close"], D[m]["vrp"]["vrp"], H_SHORT) for m in MARKETS}
    bb = boot[np.isfinite(boot)]
    return {"judge": jd, "ics": ics, "post_ics": post, "pooled21": RL8.pooled({m: RL8.spearman(s21[m]["x"], s21[m]["y"]) for m in MARKETS}),
            "boot_q": {q: round(float(np.quantile(bb, q / 100)), 4) for q in (5, 50, 95)} if len(bb) else None, "desc": desc}


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(keys=None) -> dict:
    keys = list(MARKETS) + list(DESC) if keys is None else list(keys)
    D = {}
    for m in keys:
        x = load_market(m)
        c = x["close"]
        v = vrp(c, x["iv"])
        D[m] = {**x, "vrp": v, "bull": R7.bull(c), "ratio": ratio_vrn(c, v["vrp"])}
    return D


def scale(D: dict) -> dict:
    out = {}
    for m, x in D.items():
        v = x["vrp"]["vrp"].dropna()
        me = RL8.month_ends_done(x["close"])
        vm = x["vrp"]["vrp"].reindex(me).dropna()
        bm = x["bull"].reindex(vm.index).fillna(False).astype(bool)
        days = R7.window_days(x["close"], WINDOW_B)
        b = x["bull"].reindex(days).fillna(False).astype(bool)
        r = x["ratio"].reindex(days)
        out[m] = {"close": f"{x['close'].index[0].date()}〜{x['close'].index[-1].date()}", "iv": f"{x['iv'].dropna().index[0].date()}〜{x['iv'].dropna().index[-1].date()}",
                  "vrp_from": str(v.index[0].date()) if len(v) else None, "iv_missing_pct": round(float(x["vrp"]["iv"].loc[v.index[0]:].isna().mean() * 100), 2) if len(v) else None,
                  "month_ends": int(len(vm)), "neg_pct": round(float((vm <= THRESH).mean() * 100), 1) if len(vm) else None,
                  "neg_bull_pct": round(float((vm[bm] <= THRESH).mean() * 100), 1) if bm.any() else None, "bull_month_ends": int(bm.sum()),
                  "daily_neg_pct": round(float((v <= THRESH).mean() * 100), 1) if len(v) else None,
                  "window_days": int(len(days)), "window_bull_cut_pct": round(float((b & (r < 1 - 1e-12)).sum() / max(int(b.sum()), 1) * 100), 1),
                  **({"splice": x["splice"]} if "splice" in x else {})}
    return out


def account_inputs(W: dict, D: dict) -> dict:
    """B3 的输入（loop6_r07_volbond.inputs）+ 美国 S&P 500 的 VRN 比例（美国日）与东证日上的比例。"""
    import loop6_r07_volbond as V
    M = V.inputs(W)
    M["ratio_us"] = D["US"]["ratio"]
    M["ratio_t"] = P2.as_of(M["ratio_us"], M["days"])
    return M


def account_scale(W: dict, M: dict) -> dict:
    import loop6_common as L6
    import loop6_r07_volbond as V
    out = {}
    for e in L6.ERAS:
        d = V.era_days(W, e)
        out[e] = P2.cut_share(~V.on_idx(M["bear_t"], d), M["ratio_t"].reindex(d))
    old = M["ratio_us"][(M["ratio_us"].index >= pd.Timestamp(P2.OLD[0])) & (M["ratio_us"].index <= pd.Timestamp(P2.OLD[1]))]
    out["old"] = P2.cut_share(~V.on_idx(W["bear"]["US"], old.index), old)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "ratio": round(float(M["ratio_t"].iloc[-1]), 3)}
    return out


# ───────────────────────── B 规则检验 ─────────────────────────
def stage_one(W: dict, M: dict) -> dict:
    import loop2_r05_ddbrake as R5
    import loop6_common as L6
    import research_loop6 as R6
    t0 = time.time()
    ov = P2.vtx_over(M["ratio_t"])
    reg = RL8.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**P2._acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**P2._acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VRN": nc}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = R6.stage1(cand, base, posthoc=None)
    old = {"B3": P2.old_core(W, None), "VRN": P2.old_core(W, M["ratio_us"])}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "core_trades": trades, "old": old, "drift": drift,
            "scale": account_scale(W, M), "seconds": round(time.time() - t0)}


def stage_two(D: dict) -> dict:
    t0 = time.time()
    closes = {m: D[m]["close"] for m in CROSS}
    ratios = {m: D[m]["ratio"] for m in CROSS}
    bulls = {m: D[m]["bull"] for m in CROSS}
    real = deltas(closes, ratios, bulls, None)
    n_min = min(len(R7.window_days(closes[m], WINDOW_B)) for m in CROSS)
    ks = shift_ks(n_min)
    plac, per = [], {m: [] for m in CROSS}
    for i, k in enumerate(ks):
        r = deltas(closes, ratios, bulls, k)
        full = [v[0] for v in r.values()]
        plac.append(None if any(x is None for x in full) else float(np.mean(full)))
        for m in CROSS:
            per[m].append(r[m][0])
        if (i + 1) % 100 == 0:
            print(f"随机 {i + 1} / {len(ks)}（{time.time() - t0:.0f}s）", flush=True)
    jd = R7.judge(real, plac)
    pct = {m: (round(float(np.mean([1.0 if (p is not None and p < real[m][0]) else 0.0 for p in per[m]]) * 100), 1)
               if real[m][0] is not None else None) for m in CROSS}
    extra = deltas({m: D[m]["close"] for m in ("BR", "NDX")}, {m: D[m]["ratio"] for m in ("BR", "NDX")},
                   {m: D[m]["bull"] for m in ("BR", "NDX")}, None)
    return {"real": real, "own_pctile": pct, "extra": extra, "n_min": int(n_min), "ks": ks, "placebo": plac, "judge": jd,
            "seconds": round(time.time() - t0)}


# ───────────────────────── 运行 ─────────────────────────
def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop8_r01_vrp.py", "scripts/research_loop8.py",
                                 "scripts/research_loop7.py", "scripts/loop7_r02_voltarget.py", "qbreak/bullbear.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def run_all() -> int:
    t0 = time.time()
    code, dirty = git_head()
    D = inputs()
    A = info_check(D)
    res = {"loop": 8, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty,
           "scale": scale(D), "info": A}
    if not A["judge"]["ok"]:
        res["verdict"] = RL8.FAIL_INFO
    else:
        import loop6_common as L6
        W = L6.load3()
        M = account_inputs(W, D)
        a = stage_one(W, M)
        b = stage_two(D)
        res["account"], res["cross"] = a, b
        res["verdict"] = R7.FOUND if (a["ok"] and b["judge"]["ok"]) else (R7.FAIL1 if not a["ok"] else R7.FAIL2)
    res["seconds"] = round(time.time() - t0)
    write(res)
    return 0


_f = P2._f


def write(res: dict) -> None:
    from qbreak import paths
    A, jd, ds, sc = res["info"], res["info"]["judge"], res["info"]["desc"], res["scale"]
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    L = [f"# 第八个研究循环第 1 轮：期权的波动风险溢价 VRP（隐含方差 − 已实现方差）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop8_r01_vrp.py 开头）", "", f"**{res['verdict']}**", "",
         f"## A 信息检查：{'过' if jd['ok'] else '不过'}",
         f"I1 {yn(jd['I1'])}（合并 IC {_f(jd['pooled'])}，联合区块自助法单侧 p = {_f(jd['p'], '{:.3f}')}，要 ≤ 0.10；90% 区间 "
         f"{' 〜 '.join(_f(v) for v in (jd.get('boot_ci') or [None, None]))}）；I2 {yn(jd['I2'])}（IC > 0 的市场 {jd['agree']} / {jd['n']}，要 ≥ {jd['need']}）；"
         f"I3 {yn(jd['I3'])}（2012 年以后合并 IC {_f(jd['post_pooled'])}）；21 天目标的合并 IC（只描述）{_f(A['pooled21'])}", "",
         "| 市场 | 数据 | 月末数（起〜止） | IC 全样本 | IC 2012〜 | IC 21 天 | VRP 五分位之后 63 天平均收益（低 → 高，%） | 牛市月末 VRP ≤ 0：次数 / 之后 63 天 | VRP > 0 |",
         "|---|---|---|---:|---:|---:|---|---|---|"]
    for m, (name, ivn) in {**MARKETS, **DESC}.items():
        d = ds[m]
        L.append(f"| {name} | {ivn} | {d['n']}（{(d['first'] or '—')[:7]}〜{(d['last'] or '—')[:7]}） | {_f(d['ic'])} | {_f(d['ic_post'])} | {_f(d['ic21'])} | "
                 f"{' / '.join(_f(v, '{:+.2f}') for v in d['quintiles_pct'])} | {d['bull_neg']['n']} / {_f(d['bull_neg']['mean_pct'], '{:+.2f}')}% | "
                 f"{d['bull_pos']['n']} / {_f(d['bull_pos']['mean_pct'], '{:+.2f}')}% |")
    L += ["", f"美国：文献样本内 1990〜2007 IC {_f(ds['US'].get('ic_lit'))}、2008 年以后 {_f(ds['US'].get('ic_after_lit'))}（只描述）。",
          "规模：" + "；".join(f"{m} VRP ≤ 0 的月末 {sc[m]['neg_pct']}%（牛市月末 {sc[m]['neg_bull_pct']}%）" for m in list(MARKETS) + list(DESC))]
    if "account" in res:
        a, b = res["account"], res["cross"]
        s, bj = a["stage1"], b["judge"]
        cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                          f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
        L += ["", f"## B 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
              f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；S5 / S6 / S7 不适用", "",
              "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VRN（Calmar 差） |", "|---|---|---|"]
        import loop6_common as L6
        for e in L6.ERAS:
            L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
        o = a["old"]
        L += ["", "只描述：" + "；".join(f"{e} 美股牛 {a['scale'][e]['bull_days']} 天里减仓 {_f(a['scale'][e]['cut_pct'], '{:.1f}')}%、核心换仓 "
                                        f"B3 {a['core_trades'][e]['B3']} → VRN {a['core_trades'][e]['VRN']} 笔" for e in L6.ERAS),
              "1987〜2000 只有核心：" + "、".join(f"{k} {_f(o[k]['calmar'], '{:.3f}')}（回撤 {_f(o[k].get('dd'), '{:.2f}')}%）" for k in ("B3", "VRN")),
              "", f"## B 第二关（横展开，{' / '.join(CROSS)}，{WINDOW_B[0]}〜{WINDOW_B[1]}）：{'三条都过' if bj.get('ok') else '不过'}",
              f"C1 {yn(bj.get('C1'))}（合并 {_f(bj.get('pooled'))}，400 次随机最大 {_f(bj.get('max'))}、中位 {_f((bj.get('q') or {}).get(50))}）；"
              f"C2 {yn(bj.get('C2'))}（{bj.get('positive')} / {bj.get('n')}，要 ≥ {bj.get('need')}）；C3 {yn(bj.get('C3'))}（{_f(bj.get('h1'))} / {_f(bj.get('h2'))}）",
              "各市场 Δ（全窗口 / 前一半 / 后一半；随机百分位）：" + "；".join(
                  f"{m} {' / '.join(_f(v) for v in b['real'][m])}（{_f(b['own_pctile'][m], '{:.1f}')}）" for m in CROSS)
              + "；只描述：" + "；".join(f"{m} {' / '.join(_f(v) for v in b['extra'][m])}" for m in b["extra"])]
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    D = inputs()
    out = {"markets": scale(D)}
    try:
        import loop6_common as L6
        W = L6.load3()
        out["account"] = account_scale(W, account_inputs(W, D))
    except Exception as e:                                                   # noqa: BLE001
        out["account_error"] = f"{type(e).__name__}: {str(e)[:160]}"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    """登记前用（不看任何收益）：比例全 1 → 三个年代与 B3 逐项相同、4 个市场 Δ 全为 0（平移后也是）；B3 没有别的 core_expo。"""
    import loop6_common as L6
    D = inputs()
    W = L6.load3()
    M = account_inputs(W, D)
    no_other = {e: "core_expo" not in (W["kw"][e] or {}) and "core_expo" not in (W.get("b1") or {}) for e in L6.ERAS}
    ov1 = P2.vtx_over(pd.Series(1.0, index=M["ratio_t"].index))
    same = {e: bool(all(L6.run(W, e).get(x) == L6.run(W, e, **ov1).get(x) for x in P2.KEYS)) for e in L6.ERAS}
    one = {m: pd.Series(1.0, index=D[m]["close"].index) for m in CROSS}
    cl, bu = {m: D[m]["close"] for m in CROSS}, {m: D[m]["bull"] for m in CROSS}
    z, zs = deltas(cl, one, bu, None), deltas(cl, one, bu, 1234)
    zero = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in z.values())
    zero_s = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in zs.values())
    out = {"no_other_core_expo": no_other, "ones_same_as_b3": same, "cross_ones_zero": zero, "cross_ones_shift_zero": zero_s}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if (all(no_other.values()) and all(same.values()) and zero and zero_s) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第八个研究循环第 1 轮：期权的波动风险溢价 VRP → 信息检查 + 规则 VRN")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看任何收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
