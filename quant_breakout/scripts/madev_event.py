"""madev_event.py — 周 / 月线严重脱离均线之后怎么走：你的直觉单独验证（上涨严重脱离 → 回落？下跌严重脱离 → 反弹？），
再和现行搭配、对比（2026-09-28 事先登记：规则先提交再运行一次，结果出来不改规则）。

用户（2026-09-28）：「单独验证你的直觉 下跌的时候周/月线在下一个交易日严重脱离的时候 也要进行验证 然后和先行进行搭配和对比等等的研究」
  （「先行」按「现行」理解 —— 输入法同音误字；上一轮 madev_study（1ec5121）已把「上涨连续两根严重脱离就卖」加到现行卖点上：几乎不触发）。
以前做过的（不重复）：madev_study 上涨一侧当卖点 → 几乎不触发；dip_study（a2c6fcd）日経225 **指数**的 RSI(2) 回调买 → 1990〜2005 不赚；
  leap_r4 每周 / 每月短期反转组合 → 两个年代不一致；mtf_study E11（离 10 个月线 ≤ 20% 才买）→ 两期不一致。
  这次是新的：**个股**的周 / 月线乖离「严重脱离」事件（上下两侧、两种确认方式）之后的走势，以及拿它和现行突破搭配。

一 事件（只用已完成的周 / 月线：qbreak/mtf.bars；乖离 = 收盘 ÷ 最近 n 根收盘平均 − 1，不够 n 根不判断；同一段只算第一次）
  上涨（U）：乖离 ≥ +θ；下跌（N）：乖离 ≤ −θ。
  「两根」：这一根与这只票上一根已完成 K 线都成立、且上一根与再上一根不是都成立（= 这一段第一次）→ 事件日 = 这一根的完成日
    （这只票那天没有 K 线 → 之后第一根）；
  「下一个交易日」（你说的下跌规则）：这一根成立、上一根不成立（刚脱离）→ 这只票完成日之后第一个交易日的收盘相对这一根的均线仍脱离 ≥ θ
    → 事件日 = 那个交易日（不成立 → 这一段没有事件）。
  θ（只看价格分布定，见第五节；E / J 两段日経225 全部已完成 K 线的分位数取整到 5%）：
    上涨 13 周线 +15% / +25%（95 / 99 分位）、12 个月线 +35%（95 分位）；下跌 13 周线 −15% / −25%（5 / 1 分位）、12 个月线 −25%（5 分位）。
  事件类型（11 个，事先写定）：
    U1 13 周线 两根 +15%（你的规则·周线）   U2 13 周线 两根 +25%   U3 12 个月线 两根 +35%（你的规则·月线）
    U4 13 周线 下一个交易日 +15%            U5 12 个月线 下一个交易日 +35%
    N1 13 周线 两根 −15%   N2 13 周线 两根 −25%   N3 12 个月线 两根 −25%
    N4 13 周线 下一个交易日 −15%（你的下跌规则·周线）   N5 12 个月线 下一个交易日 −25%（你的下跌规则·月线）   N6 13 周线 下一个交易日 −25%
二 数据（五段）：Z = 2001-01〜2006-09 日経225（yfinance，去掉成交量 0 的假行）、E = 2006-10〜2016-09 日経225（yfinance）、
  J = 2017-01〜2026-09 日経225（J-Quants）、J2 = 同期 J-Quants 时点 TOPIX 1000（只算那天是成员的；没有幸存者偏差）、
  W = 另一批股票 714 只 2006-10〜2016-09（TOPIX 1000 里日経225 以外，yfinance）。事件日（信号日）要落在窗口里。
  合并 = Z + E + W + J2（J 是 J2 的一部分，不重复算；J 单独报，用于「日経225 两个年代同方向」）。
三 A 你的直觉单独验证（事件研究，和交易规则无关）
  事件日 e → 下一个交易日开盘买、第 h 个交易日收盘（h = 5 / 10 / 20 / 40 / 60，≈ 1 / 2 / 4 / 8 / 12 周；市场日历，那两天没有价格 → 不算）：
  收益 r；超额 x = r − 同一段股票池同一窗口的等权平均（J2 = 那天的成员）。另报 r < 0、x < 0 的比例与这一段全部「股票 × 日」的基准比例。
  主判定的期间：周线事件 20 个交易日、月线事件 60 个交易日。你的直觉 = 上涨事件之后跑输（x < 0）、下跌事件之后跑赢（x > 0）。
  判定（每个事件类型）：95% 区间 = 按事件所在日历月聚类的自助法 2,000 次（种子 20260928）；
    「成立」= 合并的 x 平均的 95% 区间整个在预期一侧，且 Z / E / J / J2 / W 每段（事件 ≥ 20 个的）点估计都在预期一侧；
    「相反」= 合并的 95% 区间整个在另一侧；「方向一致但不显著」= 每段都在预期一侧、区间含 0；
    合并显著但有一段相反 →「不成立（有一段相反）」；其余「不成立」；合并事件 < 30 个 →「事件太少」。
四 B 和现行搭配、对比（交易规则；现行 = S0C2 + W2 的突破，卖法全部照旧）
  B1 上涨一侧当卖点：madev_study 已做（几乎不触发），不重复。
  B2 上涨一侧当买点过滤（已经严重脱离的突破不买）：信号日收盘时已完成的周 / 月线处于这个状态 → 这个突破不买（缺值 → 不挡）：
    F1 13 周线最近一根 ≥ +15%；F2 13 周线最近两根都 ≥ +15%；F3 12 个月线最近一根 ≥ +35%。
    逐信号（每个 W2 保留的突破单独一笔、现行卖法、扣 ¥25 万来回手续费）：保留组 vs 挡掉组的胜率与每笔；组合（Z / E / J）：S0C2 + W2 + 过滤。
    判定「提高胜率与收益率」= 合并的「保留 − 挡掉」每笔差 95% 下限 > 0（按月聚类、两组各自取那些月）且胜率差 ≥ 0，
      且每段（挡掉 ≥ 10 笔的）两个差都 ≥ 0，且合并保留 ≥ 50%，且组合 Z / E / J 各自 Calmar 不低 0.01 以上、回撤不深 2 pp 以上
      → 结论上限：提议（要你确认）；合并挡掉 < 20 笔 →「几乎不触发」；每段两个差都 ≥ 0 但没过其余条件 →「方向一致但不够」；其余「不成立」。
  B3 下跌一侧当卖点（持仓跌到严重脱离就卖）：突破的持仓要先跌过 −7% 止损才可能到 13 周线 −15% → 逻辑上被止损挡在前面，
    只数现行逐信号交易里持有期内出现 N4 的笔数（只描述）。
  B4 下跌一侧当新的买点（严重脱离就买；卖法同现行：止损 −7%、跟踪 12%、止盈 +25%、死叉、放量阴线、最长 60 个交易日）：
    D1 = N4 事件买、D2 = N1 事件买、D3 = N5 事件买（事件日收盘成立 → 次日开盘买）。
    逐信号：每个事件单独一笔；组合（Z / E / J）：「突破 + 这一种」（同一套 4 个名额；同一天的候选按代码顺序 = 现行做法）、
    「只有这一种」（代替突破，只描述）。
    判定「搭配成立」= 逐信号合并每笔平均的 95% 下限 > 0、每段（≥ 20 笔的）每笔 > 0，且「突破 + 这一种」组合 Z / E / J 各自
      Calmar ≥ 现行、回撤不深 2 pp 以上 → 结论上限：提议（要你确认）；合并 < 30 笔 →「事件太少」；其余「不成立」（注明没过哪一条）。
  多个检验一起看：A 11 个、B2 3 个、B4 3 个；每个都要求每段同方向 + 合并显著（B 另加组合守门），不做别的挑选，不看结果改 θ。
五 登记前的诊断（2026-09-28；只看价格分布，没有算任何收益）：
  E / J 两段日経225（208 + 213 只）全部已完成 K 线：13 周线 21.0 万根 P1 −24.3%、P5 −13.9%、P95 +15.4%、P99 +25.1%（E / J 各自 P5 −15.7 / −11.8%）；
  12 个月线 4.7 万根 P1 −42.9%、P5 −25.5%、P95 +33.5%、P99 +56.4%（E / J 各自 P5 −30.6 / −20.0%）。
六 局限：只用收盘；日経225 与扩大池用今天的成分（Z / E / J / W 有幸存者偏差，J2 没有）；五段以前做过很多别的检验；
  调整后价（yfinance 含分红调整、J-Quants 只调拆股）；持有窗口互相重叠 → 按月聚类；税前。模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/madev_event.md / .json（只有统计）。
"""
from __future__ import annotations

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
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import madev_study as MD                                                     # noqa: E402
from qbreak import mtf                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

EVENTS: dict[str, dict] = {
    "U1": {"side": 1, "freq": "W", "n": 13, "theta": 15.0, "mode": "2bar", "zh": "13 周线 连续两根 ≥ +15%（你的规则·周线）"},
    "U2": {"side": 1, "freq": "W", "n": 13, "theta": 25.0, "mode": "2bar", "zh": "13 周线 连续两根 ≥ +25%"},
    "U3": {"side": 1, "freq": "M", "n": 12, "theta": 35.0, "mode": "2bar", "zh": "12 个月线 连续两根 ≥ +35%（你的规则·月线）"},
    "U4": {"side": 1, "freq": "W", "n": 13, "theta": 15.0, "mode": "next", "zh": "13 周线 ≥ +15%、下一个交易日仍 ≥ +15%"},
    "U5": {"side": 1, "freq": "M", "n": 12, "theta": 35.0, "mode": "next", "zh": "12 个月线 ≥ +35%、下一个交易日仍 ≥ +35%"},
    "N1": {"side": -1, "freq": "W", "n": 13, "theta": 15.0, "mode": "2bar", "zh": "13 周线 连续两根 ≤ −15%"},
    "N2": {"side": -1, "freq": "W", "n": 13, "theta": 25.0, "mode": "2bar", "zh": "13 周线 连续两根 ≤ −25%"},
    "N3": {"side": -1, "freq": "M", "n": 12, "theta": 25.0, "mode": "2bar", "zh": "12 个月线 连续两根 ≤ −25%"},
    "N4": {"side": -1, "freq": "W", "n": 13, "theta": 15.0, "mode": "next", "zh": "13 周线 ≤ −15%、下一个交易日仍 ≤ −15%（你的下跌规则·周线）"},
    "N5": {"side": -1, "freq": "M", "n": 12, "theta": 25.0, "mode": "next", "zh": "12 个月线 ≤ −25%、下一个交易日仍 ≤ −25%（你的下跌规则·月线）"},
    "N6": {"side": -1, "freq": "W", "n": 13, "theta": 25.0, "mode": "next", "zh": "13 周线 ≤ −25%、下一个交易日仍 ≤ −25%"},
}
FILTERS: dict[str, dict] = {
    "F1": {"freq": "W", "n": 13, "theta": 15.0, "k": 1, "zh": "13 周线最近一根 ≥ +15% 的突破不买"},
    "F2": {"freq": "W", "n": 13, "theta": 15.0, "k": 2, "zh": "13 周线最近两根都 ≥ +15% 的突破不买"},
    "F3": {"freq": "M", "n": 12, "theta": 35.0, "k": 1, "zh": "12 个月线最近一根 ≥ +35% 的突破不买"},
}
DIPS: dict[str, str] = {"D1": "N4", "D2": "N1", "D3": "N5"}
HORIZONS = (5, 10, 20, 40, 60)
PRIMARY = {"W": 20, "M": 60}
SAMPLES = ("Z", "E", "J", "J2", "W")
POOL = ("Z", "E", "W", "J2")
PORT = ("Z", "E", "J")
MIN_EV_SAMPLE, MIN_EV_POOL = 20, 30
MIN_REMOVED_SAMPLE, MIN_REMOVED_POOL, KEEP_MIN = 10, 20, 0.5
MIN_DIP_SAMPLE = 20
CAL_TOL, DD_TOL = 0.01, 2.0
BOOT_N, SEED = 2000, 20260928
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 事件与状态（纯函数，有测试）─────────────────────────
def event_days(raw: pd.DataFrame, days: pd.DatetimeIndex, ev: dict, bars: pd.DataFrame | None = None) -> pd.DatetimeIndex:
    """一只票的日线 → 事件 ev 的事件日（这只票的交易日）。bars：已算好的同一周期 K 线（mtf.bars），缺 → 现算。"""
    b = mtf.bars(raw, days, ev["freq"]) if bars is None else bars
    dev = MD.dev_of(b, ev["n"])
    v = dev.to_numpy(float)
    with np.errstate(invalid="ignore"):
        hit = np.isfinite(v) & (ev["side"] * v >= ev["theta"] / 100)
    prev = np.r_[False, hit[:-1]]
    idx = raw.index
    if ev["mode"] == "2bar":
        both = hit & prev
        start = both & ~np.r_[False, both[:-1]]
        pos = idx.searchsorted(dev.index[start], side="left")               # 完成日这只票没有 K 线 → 之后第一根
        return pd.DatetimeIndex(idx[pos[pos < len(idx)]]).unique()
    fresh = hit & ~prev
    ma = b["Close"].astype(float).to_numpy() / (1 + v)                      # 这一根的均线
    c = raw["Close"].to_numpy(float)
    out = []
    for d, m in zip(dev.index[fresh], ma[fresh]):
        q = int(idx.searchsorted(d, side="right"))                          # 完成日之后这只票的第一个交易日
        if q < len(c) and np.isfinite(c[q]) and m > 0 and ev["side"] * (c[q] / m - 1) >= ev["theta"] / 100:
            out.append(idx[q])
    return pd.DatetimeIndex(out).unique()


def filter_state(raw: pd.DataFrame, days: pd.DatetimeIndex, f: dict, idx: pd.DatetimeIndex, bars: pd.DataFrame | None = None) -> np.ndarray:
    """买点过滤的状态（布尔，对齐 idx）：那天收盘时已完成的最近一根（k = 2：最近两根）乖离都 ≥ θ；缺值 → False（不挡）。"""
    b = mtf.bars(raw, days, f["freq"]) if bars is None else bars
    dev = MD.dev_of(b, f["n"])
    v = dev.to_numpy(float)
    with np.errstate(invalid="ignore"):
        hit = np.isfinite(v) & (v >= f["theta"] / 100)
    if f["k"] == 2:
        hit = hit & np.r_[False, hit[:-1]]
    st = pd.DataFrame({"s": np.where(np.isfinite(v), hit.astype(float), np.nan)}, index=dev.index)
    return mtf.state_on(st, pd.DatetimeIndex(idx))["s"].to_numpy(float) == 1.0


def fwd_returns(P: dict, horizons=HORIZONS) -> dict[int, np.ndarray]:
    """R_h[e, j] = 第 e + h 个市场日收盘 ÷ 第 e + 1 个市场日开盘 − 1（事件日 e 收盘成立 → 次日开盘买，持有 h 个交易日）。"""
    op, cl = np.asarray(P["O"], float), np.asarray(P["C"], float)
    T = op.shape[0]
    out = {}
    for h in horizons:
        R = np.full(op.shape, np.nan)
        if T > h:
            with np.errstate(invalid="ignore", divide="ignore"):
                R[:T - h] = cl[h:] / op[1:T - h + 1] - 1
        R[~np.isfinite(R)] = np.nan
        out[h] = R
    return out


def market_mean(R: np.ndarray, member: np.ndarray) -> np.ndarray:
    """每个市场日：成员里有值的等权平均（没有 → NaN）。"""
    X = np.where(member, R, np.nan)
    cnt = np.isfinite(X).sum(axis=1)
    s = np.nansum(X, axis=1)
    return np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)


def boot_mean(x: np.ndarray, months: np.ndarray, n: int = BOOT_N, seed: int = SEED) -> tuple[float, float]:
    """平均的 95% 区间：按月聚类的自助法（抽月份，有放回）。"""
    m = np.isfinite(x)
    x, months = x[m], np.asarray(months)[m]
    if len(x) < 2:
        return (np.nan, np.nan)
    u, inv = np.unique(months, return_inverse=True)
    s, c = np.bincount(inv, weights=x, minlength=len(u)), np.bincount(inv, minlength=len(u)).astype(float)
    rng = np.random.default_rng(seed)
    v = np.empty(n)
    for k in range(n):
        j = rng.integers(0, len(u), len(u))
        v[k] = s[j].sum() / c[j].sum()
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


# ───────────────────────── 判定（纯函数，有测试）─────────────────────────
def verdict_event(pool: dict, per: dict[str, dict], side: int) -> str:
    """pool / per：{n, x_mean, lo, hi}；side = +1 上涨（预期 x < 0）/ −1 下跌（预期 x > 0）。"""
    if pool.get("n", 0) < MIN_EV_POOL:
        return "事件太少"
    want = -side
    lo, hi = pool.get("lo", np.nan), pool.get("hi", np.nan)
    rows = [per[t] for t in SAMPLES if (per.get(t) or {}).get("n", 0) >= MIN_EV_SAMPLE]
    same = bool(rows) and all(np.isfinite(r["x_mean"]) and r["x_mean"] * want > 0 for r in rows)
    pred = (want < 0 and hi < 0) or (want > 0 and lo > 0)
    opp = (want < 0 and lo > 0) or (want > 0 and hi < 0)
    if pred and same:
        return "成立"
    if opp:
        return "相反"
    if pred:
        return "不成立（有一段相反）"
    return "方向一致但不显著" if same else "不成立"


def port_ok(port: dict, strict: bool = False) -> bool:
    """port：{段: {"cur": {calmar, dd}, "var": {calmar, dd}}}；Z / E / J 每段 Calmar 不低 0.01 以上（strict：不低于现行）、回撤不深 2 pp 以上。"""
    for tag in PORT:
        c, v = (port.get(tag) or {}).get("cur") or {}, (port.get(tag) or {}).get("var") or {}
        if None in (c.get("calmar"), v.get("calmar"), c.get("dd"), v.get("dd")):
            return False
        if v["calmar"] < c["calmar"] - (0.0 if strict else CAL_TOL) or v["dd"] < c["dd"] - DD_TOL:
            return False
    return True


def verdict_filter(pool: dict, per: dict[str, dict], port: dict) -> str:
    """pool / per：{removed, keep_frac, dmean, dwin, dmean_lo}（保留 − 挡掉）。"""
    if pool.get("removed", 0) < MIN_REMOVED_POOL:
        return "几乎不触发"
    rows = [per[t] for t in SAMPLES if (per.get(t) or {}).get("removed", 0) >= MIN_REMOVED_SAMPLE]
    same = bool(rows) and all(r.get("dmean", -1) >= 0 and r.get("dwin", -1) >= 0 for r in rows)
    if (pool.get("dmean_lo", -1) > 0 and pool.get("dwin", -1) >= 0 and same and pool.get("keep_frac", 0) >= KEEP_MIN and port_ok(port)):
        return "提高胜率与收益率"
    return "方向一致但不够" if same else "不成立"


def verdict_dip(pool: dict, per: dict[str, dict], port: dict) -> str:
    """pool / per：{n, mean, lo}（逐信号每笔）；port：「突破 + 这一种」vs 现行。"""
    if pool.get("n", 0) < MIN_EV_POOL:
        return "事件太少"
    rows = [per[t] for t in SAMPLES if (per.get(t) or {}).get("n", 0) >= MIN_DIP_SAMPLE]
    why = []
    if not pool.get("lo", -1) > 0:
        why.append("合并每笔 95% 下限不 > 0")
    if not (rows and all(r["mean"] > 0 for r in rows)):
        why.append("有一段每笔 ≤ 0")
    if not port_ok(port, strict=True):
        why.append("组合没过（Calmar 低于现行或回撤深 2 pp 以上）")
    return "搭配成立" if not why else "不成立（" + "；".join(why) + "）"


# ───────────────────────── 样本 ─────────────────────────
def load_sample(tag: str, p0) -> dict:
    """{ctx, fa, keep, member（票 → 日线布尔）, a, b, cols（事件研究的列）, M（市场日 × cols 的成员）}。"""
    import leap_confirm as LF
    import sell_confirm as SCF
    if tag == "W":
        ctx, fa = SCF.wide_context(p0)
        a, b = SCF.W_WIN
        cols = list(range(len(ctx["names"])))
        M = np.ones((len(ctx["days"]), len(cols)), bool)
        member = {t: np.ones(len(df), bool) for t, df in fa.items()}
    else:
        ctx = LF.context("J", jmem="U2") if tag == "J2" else LF.context(tag)
        fa = LF.frames(ctx, p0)
        a, b = ctx["start"], ctx["end"] or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        cols = list(ctx["cols"])
        M = ctx["D"]["mem"]["U2"][:, cols] if tag == "J2" else np.ones((len(ctx["days"]), len(cols)), bool)
        member = LF.member_mask(ctx, fa)
    return {"ctx": ctx, "fa": fa, "keep": LF.w2_keep(ctx, fa), "member": member, "a": a, "b": b, "cols": cols, "M": np.asarray(M, bool)}


def event_study(tag: str, S: dict) -> tuple[pd.DataFrame, dict, dict]:
    """事件表（每行一个事件：set / ev / ticker / date / r_h / x_h）、每只票的事件日 {ev: {票: 日期}}（组合用，不限窗口）、基准比例。"""
    ctx, cols, M = S["ctx"], S["cols"], S["M"]
    P, days = ctx["P"], pd.DatetimeIndex(ctx["days"])
    a, b = pd.Timestamp(S["a"]), pd.Timestamp(S["b"])
    Rh = fwd_returns({"O": P["O"][:, cols], "C": P["C"][:, cols]})
    mk = {h: market_mean(Rh[h], M) for h in HORIZONS}
    inwin = (days >= a) & (days <= b)
    base = {}
    for h in HORIZONS:
        R = np.where(M & inwin[:, None], Rh[h], np.nan)
        X = R - mk[h][:, None]
        f = np.isfinite(X)
        base[h] = {"r_neg": float((R[f] < 0).mean() * 100), "x_neg": float((X[f] < 0).mean() * 100), "n": int(f.sum())}
    rows, alld = [], {k: {} for k in EVENTS}
    for jj, j in enumerate(cols):
        t = ctx["names"][j]
        raw = MD.raw_of(P, days, j)
        if len(raw) < 30:
            continue
        bars = {fq: mtf.bars(raw, days, fq) for fq in ("W", "M")}
        for k, ev in EVENTS.items():
            ed = event_days(raw, days, ev, bars[ev["freq"]])
            if not len(ed):
                continue
            e = days.get_indexer(ed)
            ok = (e >= 0) & M[np.clip(e, 0, None), jj]
            alld[k][t] = ed[ok]
            for d, ei in zip(ed[ok], e[ok]):
                if not (a <= d <= b):
                    continue
                row = {"set": tag, "ev": k, "ticker": t, "date": d}
                for h in HORIZONS:
                    r, m_ = Rh[h][ei, jj], mk[h][ei]
                    row[f"r{h}"] = r * 100 if np.isfinite(r) else np.nan
                    row[f"x{h}"] = (r - m_) * 100 if np.isfinite(r) and np.isfinite(m_) else np.nan
                rows.append(row)
    return pd.DataFrame(rows), alld, base


def ev_summary(T: pd.DataFrame, h: int, ci: bool = True) -> dict:
    if not len(T):
        return {"n": 0}
    x, r = T[f"x{h}"].to_numpy(float), T[f"r{h}"].to_numpy(float)
    f = np.isfinite(x)
    if not f.any():
        return {"n": 0}
    out = {"n": int(f.sum()), "x_mean": float(x[f].mean()), "r_mean": float(r[f].mean()), "x_neg": float((x[f] < 0).mean() * 100),
           "r_neg": float((r[f] < 0).mean() * 100)}
    if ci:
        out["lo"], out["hi"] = boot_mean(x, pd.to_datetime(T["date"]).dt.to_period("M").astype(str).to_numpy())
    return out


def signal_trades(fa: dict, sigs: pd.DataFrame, p, bt, rt: float, end_bars: int = 90) -> pd.DataFrame:
    """每个信号单独一笔（现行卖法）：ticker / date / entry_date / exit_date / net / hold（没卖出的不算）。"""
    import sell_confirm as SCF
    rows = []
    for r in sigs.to_dict("records"):
        t, d = r["ticker"], pd.Timestamp(r["date"])
        df = fa.get(t)
        if df is None or d not in df.index:
            continue
        pos = int(df.index.get_loc(d))
        end = df.index[min(len(df) - 1, pos + end_bars)]
        a = SCF.one_trade(t, df.assign(entry=np.asarray(df.index == d)), d, p, bt, end)
        if a is None or a["reason"] == "end":
            continue
        rows.append({"ticker": t, "date": d, "entry_date": pd.Timestamp(a["entry_date"]), "exit_date": pd.Timestamp(a["exit_date"]),
                     "net": float(a["ret_pct"]) - rt, "hold": int(a["hold_days"]), "reason": a["reason"]})
    return pd.DataFrame(rows, columns=["ticker", "date", "entry_date", "exit_date", "net", "hold", "reason"])


def trade_summary(T: pd.DataFrame, ci: bool = True) -> dict:
    if not len(T):
        return {"n": 0}
    x = T["net"].to_numpy(float)
    w, lo = x[x > 0], x[x <= 0]
    out = {"n": int(len(x)), "win": float((x > 0).mean() * 100), "mean": float(x.mean()), "avg_win": float(w.mean()) if len(w) else None,
           "avg_loss": float(lo.mean()) if len(lo) else None, "hold": float(np.median(T["hold"]))}
    if ci:
        out["lo"], out["hi"] = boot_mean(x, pd.to_datetime(T["date"]).dt.to_period("M").astype(str).to_numpy())
    return out


def filter_compare(T: pd.DataFrame, col: str) -> dict:
    """保留 − 挡掉（col = 挡掉的布尔列）。"""
    import tune_common as TC
    k, r = T[~T[col]], T[T[col]]
    out = {"n": int(len(T)), "removed": int(len(r)), "keep_frac": float(len(k) / len(T)) if len(T) else np.nan}
    if len(k) and len(r):
        out.update({"win_keep": float((k["net"] > 0).mean() * 100), "win_rem": float((r["net"] > 0).mean() * 100),
                    "mean_keep": float(k["net"].mean()), "mean_rem": float(r["net"].mean())})
        out["dwin"], out["dmean"] = out["win_keep"] - out["win_rem"], out["mean_keep"] - out["mean_rem"]
        mk = lambda d: pd.DataFrame({"month": pd.to_datetime(d["date"]).dt.to_period("M").astype(str), "net": d["net"].to_numpy(float)})  # noqa: E731
        if len(r) >= 5:
            out.update(TC.boot_unpaired(mk(k), mk(r), n=BOOT_N, seed=SEED))
    return out


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def main() -> int:
    import bsh_common as BC
    import leap_confirm as LF
    import sell_confirm as SCF
    import sell_explore as SX
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 周 / 月线严重脱离均线之后怎么走：你的直觉单独验证 + 和现行搭配对比（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/madev_event.py 开头（运行前写定）。")
    EV, BASE, BRK, DIPT, PORTR = [], {}, {}, {}, {}
    held_n4 = {}
    for tag in SAMPLES:
        t1 = time.time()
        S = load_sample(tag, p0)
        T, alld, base = event_study(tag, S)
        EV.append(T)
        BASE[tag] = base
        fa, keep, member = S["fa"], S["keep"], S["member"]
        ctx, days = S["ctx"], pd.DatetimeIndex(S["ctx"]["days"])
        col = {t: j for j, t in enumerate(ctx["names"])}
        keepm = {t: np.asarray(keep[t], bool) & np.asarray(member[t], bool) for t in fa}
        sigs = SCF.signals_of(fa, keepm, S["a"], S["b"])
        Tb = signal_trades(fa, sigs, p0, bt, rt)
        st: dict[str, dict] = {k: {} for k in FILTERS}                       # 过滤状态（票 → 日线布尔）
        for t, df in fa.items():
            raw = MD.raw_of(ctx["P"], days, col[t])
            bars = {fq: mtf.bars(raw, days, fq) for fq in ("W", "M")}
            for k, f in FILTERS.items():
                st[k][t] = filter_state(raw, days, f, df.index, bars[f["freq"]])
        for k in FILTERS:
            Tb[k] = [bool(st[k][t][fa[t].index.get_loc(d)]) for t, d in zip(Tb["ticker"], Tb["date"])] if len(Tb) else []
        Tb["set"] = tag
        BRK[tag] = Tb
        n4 = alld["N4"]
        held_n4[tag] = int(sum(any((x >= r.entry_date) & (x < r.exit_date) for x in n4.get(r.ticker, pd.DatetimeIndex([])))
                               for r in Tb.itertuples())) if len(Tb) else 0
        for dk, ek in DIPS.items():
            Te = T[T["ev"] == ek][["ticker", "date"]]
            Td = signal_trades(fa, Te, p0, bt, rt)
            Td["set"] = tag
            DIPT.setdefault(dk, {})[tag] = Td
        if tag in PORT:
            run_fn = LF.runner(ctx, fa)
            fw = LF.with_mask(fa, keep)
            PORTR[tag] = {"现行": SX.summ(LF.run(ctx, run_fn, fw, p), tag)}
            prof = {"现行": BC.trade_profile(BC.last_trades(S["a"], S["b"]))}
            for k in FILTERS:
                PORTR[tag][k] = SX.summ(LF.run(ctx, run_fn, LF.with_mask(fw, {t: ~st[k][t] for t in fw}), p), tag)
            for dk, ek in DIPS.items():
                dipm = {t: np.isin(df.index, alld[ek].get(t, pd.DatetimeIndex([]))) for t, df in fa.items()}
                both = {t: df.assign(entry=df["entry"].to_numpy(bool) | dipm[t]) for t, df in fw.items()}
                PORTR[tag][dk] = SX.summ(LF.run(ctx, run_fn, both, p), tag)
                prof[dk] = BC.trade_profile(BC.last_trades(S["a"], S["b"]))
                only = {t: df.assign(entry=dipm[t]) for t, df in fw.items()}
                PORTR[tag][f"{dk}只"] = SX.summ(LF.run(ctx, run_fn, only, p), tag)
                prof[f"{dk}只"] = BC.trade_profile(BC.last_trades(S["a"], S["b"]))
            PORTR[tag]["_profile"] = prof
        say(f"- {tag}（{S['a']}〜{S['b']}）：事件 {len(T)} 个、W2 保留的突破 {len(Tb)} 笔、超跌买 "
            + " / ".join(f"{dk} {len(DIPT[dk][tag])}" for dk in DIPS) + f" 笔；{round(time.time() - t1)} s")
    EVT = pd.concat(EV, ignore_index=True)

    # ── A 事件研究 ──
    A = {}
    for k, ev in EVENTS.items():
        h = PRIMARY[ev["freq"]]
        per = {t: ev_summary(EVT[(EVT["ev"] == k) & (EVT["set"] == t)], h, ci=False) for t in SAMPLES}
        pool = ev_summary(EVT[(EVT["ev"] == k) & EVT["set"].isin(POOL)], h)
        A[k] = {"h": h, "pool": pool, "per": per, "verdict": verdict_event(pool, per, ev["side"]),
                "by_h": {hh: ev_summary(EVT[(EVT["ev"] == k) & EVT["set"].isin(POOL)], hh, ci=False) for hh in HORIZONS}}
    say("\n## 一、你的直觉单独验证（事件研究；超额 = 减同一段股票池同一窗口的等权平均；主判定：周线 20 个交易日、月线 60 个交易日）")
    say("| 事件 | 合并事件数 | 超额平均（95% 区间） | 跑输的比例 | 每段超额（Z / E / J / J2 / W） | 判定 |")
    say("|---|---|---|---|---|---|")
    for k, ev in EVENTS.items():
        x = A[k]["pool"]
        cells = " / ".join(fmt((A[k]["per"][t] or {}).get("x_mean")) + f"（{(A[k]['per'][t] or {}).get('n', 0)}）" for t in SAMPLES)
        say(f"| {k} {ev['zh']}（{A[k]['h']} 日） | {x.get('n', 0)} | {fmt(x.get('x_mean'))}%（{fmt(x.get('lo'))}〜{fmt(x.get('hi'))}） | "
            f"{fmt(x.get('x_neg'), '{:.1f}')}% | {cells} | **{A[k]['verdict']}** |")
    say("\n基准（这一段全部「股票 × 日」，同一期间）：" + "；".join(
        f"{t} 20 日跑输 {BASE[t][20]['x_neg']:.1f}% / 60 日 {BASE[t][60]['x_neg']:.1f}%" for t in SAMPLES))
    say("\n### 各期间（合并；超额平均 % / 跑输的比例 % / 下跌的比例 %）")
    say("| 事件 | " + " | ".join(f"{h} 日" for h in HORIZONS) + " |")
    say("|---|" + "---|" * len(HORIZONS))
    for k in EVENTS:
        say(f"| {k} | " + " | ".join(f"{fmt(A[k]['by_h'][h].get('x_mean'))} / {fmt(A[k]['by_h'][h].get('x_neg'), '{:.0f}')} / "
                                    f"{fmt(A[k]['by_h'][h].get('r_neg'), '{:.0f}')}" for h in HORIZONS) + " |")

    # ── B2 买点过滤 ──
    B2 = {}
    BRKALL = pd.concat([BRK[t] for t in SAMPLES], ignore_index=True)
    for k in FILTERS:
        per = {t: filter_compare(BRK[t], k) for t in SAMPLES}
        pool = filter_compare(BRKALL[BRKALL["set"].isin(POOL)], k)
        pk = {t: {"cur": PORTR[t]["现行"], "var": PORTR[t][k]} for t in PORT}
        B2[k] = {"pool": pool, "per": per, "verdict": verdict_filter(pool, per, pk)}
    say("\n## 二、和现行搭配 ①：已经严重脱离（向上）的突破不买（逐信号：保留 vs 挡掉；组合：S0C2 + W2 + 过滤）")
    say("| 过滤 | 挡掉 / 全部 | 胜率 保留 vs 挡掉 | 每笔 保留 vs 挡掉（差、95% 区间） | 每段每笔差（Z / E / J / J2 / W） | 组合 Calmar Z / E / J（现行 → 过滤） | 判定 |")
    say("|---|---|---|---|---|---|---|")
    for k, f in FILTERS.items():
        x = B2[k]["pool"]
        cells = " / ".join(fmt(B2[k]["per"][t].get("dmean")) + f"（{B2[k]['per'][t].get('removed', 0)}）" for t in SAMPLES)
        cal = " / ".join(f"{fmt(PORTR[t]['现行'].get('calmar'), '{:.3f}')}→{fmt(PORTR[t][k].get('calmar'), '{:.3f}')}" for t in PORT)
        say(f"| {k} {f['zh']} | {x.get('removed', 0)} / {x.get('n', 0)} | {fmt(x.get('win_keep'), '{:.1f}')}% vs {fmt(x.get('win_rem'), '{:.1f}')}% | "
            f"{fmt(x.get('mean_keep'))}% vs {fmt(x.get('mean_rem'))}%（{fmt(x.get('dmean'))}，{fmt(x.get('dmean_lo'))}〜{fmt(x.get('dmean_hi'))}） | {cells} | {cal} | "
            f"**{B2[k]['verdict']}** |")
    say("\n## 三、和现行搭配 ②：下跌一侧当卖点（持仓跌到严重脱离）")
    say("持有期里出现 N4（13 周线 ≤ −15%、下一个交易日仍 ≤ −15%）的现行交易：" + "、".join(f"{t} {held_n4[t]} / {len(BRK[t])} 笔" for t in SAMPLES)
        + "（−7% 止损在前，登记时的推断）。")

    # ── B4 超跌买 ──
    B4 = {}
    for dk, ek in DIPS.items():
        per = {t: trade_summary(DIPT[dk][t], ci=False) for t in SAMPLES}
        pool = trade_summary(pd.concat([DIPT[dk][t] for t in POOL], ignore_index=True))
        pk = {t: {"cur": PORTR[t]["现行"], "var": PORTR[t][dk]} for t in PORT}
        B4[dk] = {"pool": pool, "per": per, "verdict": verdict_dip(pool, per, pk)}
    say("\n## 四、和现行搭配 ③：下跌严重脱离就买（卖法同现行；逐信号每个事件单独一笔）")
    say("| 买点 | 合并笔数 | 胜率 | 每笔（95% 区间） | 平均赚 / 亏 | 持有中位 | 每段每笔（Z / E / J / J2 / W） | 判定 |")
    say("|---|---|---|---|---|---|---|---|")
    for dk, ek in DIPS.items():
        x = B4[dk]["pool"]
        cells = " / ".join(fmt(B4[dk]["per"][t].get("mean")) + f"（{B4[dk]['per'][t].get('n', 0)}）" for t in SAMPLES)
        say(f"| {dk} = {ek} {EVENTS[ek]['zh']} | {x.get('n', 0)} | {fmt(x.get('win'), '{:.1f}')}% | {fmt(x.get('mean'))}%（{fmt(x.get('lo'))}〜{fmt(x.get('hi'))}） | "
            f"{fmt(x.get('avg_win'))}% / {fmt(x.get('avg_loss'))}% | {fmt(x.get('hold'), '{:.0f}')} 天 | {cells} | **{B4[dk]['verdict']}** |")
    say("现行突破（同一做法，参照）：" + "；".join(f"{t} {trade_summary(BRK[t], ci=False).get('n', 0)} 笔 胜率 {fmt(trade_summary(BRK[t], ci=False).get('win'), '{:.1f}')}%、"
                                          f"每笔 {fmt(trade_summary(BRK[t], ci=False).get('mean'))}%" for t in SAMPLES))
    say("\n## 五、组合（S0C2 + W2；年化 / 最大回撤 / Calmar / 个股胜率 / 每笔 / 笔数）")
    say("| 设定 | Z | E | J |")
    say("|---|---|---|---|")
    keys = ["现行", *FILTERS, *DIPS, *[f"{d}只" for d in DIPS]]
    lab = {**{k: f"{k} 过滤" for k in FILTERS}, **{d: f"突破 + {d}（{e}）" for d, e in DIPS.items()}, **{f"{d}只": f"只有 {d}（{e}）" for d, e in DIPS.items()}}
    for k in keys:
        cells = []
        for t in PORT:
            s = PORTR[t][k]
            cells.append(f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')} / "
                         f"{fmt(s.get('win'), '{:.1f}')}% / {fmt(s.get('mean'))}% / {s.get('n')}")
        say(f"| {lab.get(k, k)} | " + " | ".join(cells) + " |")
    say("\n事件说明：" + "；".join(f"{k} {v['zh']}" for k, v in EVENTS.items()))
    out = {"code": code, "A": A, "base": BASE, "B2": B2, "held_n4": held_n4, "B4": B4,
           "portfolio": {t: {k: v for k, v in PORTR[t].items()} for t in PORT},
           "counts": {"events": {t: int((EVT["set"] == t).sum()) for t in SAMPLES}, "breakouts": {t: int(len(BRK[t])) for t in SAMPLES}},
           "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {out['elapsed_s']} s）。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / "madev_event"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
