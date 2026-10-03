"""jp_rates_study.py — 日本历年利率等 × 日経 横展开（2026-10-01 用户：「进行日本历年利率等等横展开对日经的影响研究」；
登记 = 本提交，提交后不改规则、只运行一次；判定与事前预期写在下面，结果出来不改）。

问题：日本 1970 年代以来的利率（政策金利、長期金利、曲线、実質金利）与「等等」（物价、汇率、日銀资产 / 货币、美国利率、日米金利差）
处在什么状态 / 往哪个方向走时，之后的日経225 怎么样 —— 分年代看稳不稳，和别的市场比是不是日本特有，能不能变成一条规则。
已有的相关结论（不重做）：多因子研究（09-24，国债曲线 / 利率 … 样本外不通过）、股市压力指数（09-29，利率上升 + 曲线变平 日本 AUC 0.46）、
现行选股方案拆成每月 × 利率 / 国债（09-29，不通过）、政策状态 → 参数（09-30，不通过）。这次不是选股参数，是「利率状态 → 之后的指数」本身，
时间拉长到 1970 年代、变量横展开到 12 个、市场横展开到约 17 个。

一、数据（月末；都是免费官方源，缓存 var/cache/factors/、不入库）
  日経225：yfinance ^N225（1965-01 起，调整后收盘，月末 = 当月最后一个收盘）；S&P 500 ^GSPC（美国变量的对照）；
  其他市场：threat_intl_study 缓存的指数（k4_horizontal_study.MARKETS + 以色列 TA-125）。
  日本（12 个变量；月度数据的「当月值」放到当月月末；日度取月平均）：
    pol  政策金利：FRED INTDSRJPM193N 公定歩合（1953〜1995-12）→ 1996-01 起 OECD 無担保コール月平均（IRSTCI01JPM156N，1985-07 起）
    st   短期金利：IRSTCI01JPM156N（1985-07 起）
    lt   長期金利：財務省 国債金利情報 10 年（1986-07 起）；之前用 5 年（1974-09〜1986-06）；Δ12 分段算再接，接缝不混口径
    curve 曲线 = lt − pol（pp；Δ12 = lt 的 Δ12 − pol 的 Δ12）
    cpi  消費者物価 同比（%）：FRED JPNCPIALLMINMEI（1955〜2021-06；OECD / FRED 之后不再更新；2021-07 起若 IMF IFS 取得到就接上，取不到就到 2021-06 为止）
    real 実質長期金利 = lt − cpi（Δ12 = lt 的 Δ12 − cpi 的 Δ12）
    fx   USD/JPY：FRED EXJPUS（1971 起；状态用 12 个月变化率 %）
    boj  日銀総資産 同比 %：FRED JPNASSETS（1998-04 起）
    m2   マネー 同比 %：FRED MYAGM2JPM189N M2（1967〜2017-02）→ 2017-03 起 MABMM301JPM189S M3（〜2023-11）；状态用 同比 − 过去 120 个月中位
    us10 美国 10 年：FRED GS10；ff 联邦基金：FEDFUNDS；diff 日米金利差 = us10 − lt（Δ12 = us10 的 Δ12 − lt 的 Δ12）
  其他市场（横向）：FRED/OECD 長期 IRLTLT01xxM156N、短期 IRSTCI01xxM156N、CPI 同比 CPALTT01xxM659N（美国 GS10 / FEDFUNDS）；取不到的项跳过。
  公布滞后不另加（利率当天可知；CPI 约 3 周后公布 → 轻微偷看，写进局限）。
二、状态（事先定死的门槛，不选）
  变量 v 的 12 个月变化 Δ12（fx = 12 个月变化率 %）；状态：上 = Δ12 > +d_v，下 = Δ12 < −d_v，平 = 其余（缺值 = 平）。
  d_v：利率类（pol / st / lt / curve / real / us10 / ff / diff）0.5 pp，real 1.0 pp；cpi 1.0 pp；fx 5%（上 = 日元走弱）；
  boj：同比 > 0 = 上（扩张）、< 0 = 下；m2：同比 − 过去 120 个月中位 > 0 = 上。
  水平（只描述）：z = (v − 过去 120 个月均值) ÷ 标准差，高 = z ≥ +1、低 = z ≤ −1。
三、日本：状态 → 之后的日経（只描述 + 安慰剂）
  结果：t 月末之后 6 / 12 个月的收益（%）、之后 12 个月内（按月末）最低点 ≤ −15% 的比例；按 上 / 下 / 平 列 月数、中位、> 0 的比例；
  年代 E1 〜1989-12、E2 1990-01〜2012-12、E3 2013-01〜；「上 − 下」的 12 个月收益中位差 vs 状态序列循环平移（≥ 12 个月，200 次）→ |差| 在平移分布里的分位；
  稳定 = 各状态 ≥ 24 个月的年代（≥ 2 个）里「上 − 下」同号。美国变量（us10 / ff）另对 S&P 500 做一遍（对照）。
  事件（只描述，样本 < 10）：政策金利 加息周期起点（3 个月变化 ≥ +0.1 pp 且 ≥ 过去 12 个月最高、之前 12 个月没有加息月）、降息周期起点（对称）
  → 之后 3 / 6 / 12 / 24 个月的日経，与全样本同长度收益的分位。
四、规则（5 条，指数级，与 K4 横向同一套：t − 1 月末状态满足 → t 月指数仓位 ×0.5，其余 100%；Calmar = 月度年化 ÷ 最大回撤）
  R1 長期金利上升：lt Δ12 > +0.5 pp；R2 加息中：pol Δ12 > +0.1 pp；R3 曲线变平：curve Δ12 < −0.5 pp；R4 実質金利上升：real Δ12 > +1.0 pp；
  R5 日米金利差拡大：diff Δ12 > +1.0 pp。评估 1975-10〜最新完整月；两半 H1 〜2005-12、H2 2006-01〜；安慰剂 = 状态循环平移 30 个种子 → Δ 的 95 分位。
  横向：同一条规则放到其他市场（本国 lt / st / cpi；R2 用本国短期利率；R5 = 美国 10 年 − 本国 lt，美国没有 R5）；评估月 ≥ 120 的市场参与判定。
五、判定（事先写定；D1〜D5 全过 → 提议 = 要用户确认才改模拟盘；有一条不过 → 不通过、只描述）
  D1 两半 Δ 都 ≥ +0.02；D2 全期 Δ ≥ 安慰剂 95 分位；D3 满足月比例 ≤ 50%；
  D4 横向：外国市场（≥ 5 个）里 Δ ≥ 0 的占比 ≥ 2/3 且 平均 Δ > 合并安慰剂（各种子的市场平均）95 分位；
  D5（只对过了 D1〜D4 的规则跑）账户级 JP-T + 规则（market_compare 框架、个股新仓 ×0.5，与 K4 横向相同的系数接法）：
     20 年 Calmar ≥ 现行 + 0.02，E、J 各 ≥ 现行 − 0.01。
六、事前预期（写在运行前）
  ① 日本：長期金利「上」的月份里一半是复苏期（1999、2003〜04、2013、2022〜25），一半在顶部之前（1989〜90、2006〜07）→ 上 − 下 的中位差在 ±5 pp 内、
     不超过平移的 95 分位；三个年代不同号（E1 负、E3 正）；曲线变平 / 実質金利上升 也不稳定；fx 日元走弱 → 之后 12 个月偏正只在 E3 明显。
  ② 事件：加息周期起点约 7 个（1973、1979、1989、2000、2006、2024 …），12〜24 个月后下跌的约 2/3，但样本太少、分位中位 30〜45；
     降息周期起点之后 12 个月中位略负（降息多在下跌中途）。
  ③ 规则：R2（加息中）最可能过 D1（1989〜90、2000、2007〜08 都在加息后），但满足月少、D2 难过；R1 / R3 / R4 在 H2 为负；R5 两半不同号；
     横向：利率上升 ×0.5 在外国市场 Δ ≥ 0 的占比约一半、平均 Δ 在安慰剂范围内；五条全过的概率约 10%。
七、局限：月度平均利率（月内变动被抹平）；1986 年以前長期金利用 5 年；CPI 2021-07 以后可能缺；指数级规则不含股息、费用；
  外国市场的指数多从 1990 年代开始（没有 1970〜80 年代的高利率期）；只有一种仓位 ×0.5 的粗规则；事件样本极少。
登记前做过的检查：tests/test_jp_rates_study.py（月末化 / 分段 Δ12 / 状态 / 分组表与安慰剂 / 周期起点 / 规则评估 / 判定）；--smoke 只看数据覆盖与接线，不看结果。
输出：var/out/jp_rates_study.md / .json（只有统计）
"""
from __future__ import annotations

import argparse
import io
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
from qbreak import factors as F                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402
import k4_horizontal_study as K                                              # noqa: E402

EVAL0, SPLIT = "1975-09-30", "2005-12-31"
ERAS = (("E1", "1900-01-01", "1989-12-31"), ("E2", "1990-01-01", "2012-12-31"), ("E3", "2013-01-01", "2100-12-31"))
D = {"pol": 0.5, "st": 0.5, "lt": 0.5, "curve": 0.5, "real": 1.0, "cpi": 1.0, "fx": 5.0, "us10": 0.5, "ff": 0.5, "diff": 0.5}
GROWTH = ("boj", "m2")
VARS = ("pol", "st", "lt", "curve", "cpi", "real", "fx", "boj", "m2", "us10", "ff", "diff")
RULES = {"R1": ("lt", "up", 0.5, "長期金利上升"), "R2": ("pol", "up", 0.1, "加息中"), "R3": ("curve", "down", 0.5, "曲线变平"),
         "R4": ("real", "up", 1.0, "実質金利上升"), "R5": ("diff", "up", 1.0, "日米金利差拡大")}
LABELS = {"pol": "政策金利（公定歩合 → 無担保コール）", "st": "短期金利（無担保コール）", "lt": "長期金利（10 年；1986-06 以前 5 年）",
          "curve": "曲线（長期 − 政策）", "cpi": "消費者物価 同比", "real": "実質長期金利（長期 − CPI）", "fx": "USD/JPY（上 = 日元走弱）",
          "boj": "日銀総資産 同比（上 = 扩张）", "m2": "マネー（M2 → M3）同比 − 过去 10 年中位", "us10": "美国 10 年", "ff": "联邦基金利率",
          "diff": "日米金利差（美国 10 年 − 長期）"}
MIN_ERA, PLACEBO_N, SEEDS, SHIFT_MIN, MIN_MONTHS, MIN_HALF, Z_WIN = 24, 200, 30, 12, 120, 60, 120
DD_THR, EV_D3, EV_GAP, EV_H, HALF = -15.0, 0.1, 12, (3, 6, 12, 24), 0.5
D1_MIN, D5_UP, D5_TOL, SHARE_2_3, MIN_FOREIGN = 0.02, 0.02, 0.01, 2 / 3, 5
MARKETS = {**K.MARKETS, "IL": ("^TA125.TA", "以色列 TA-125")}
IMF_CPI = "https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/IFS/M.JP.PCPI_IX?startPeriod=2019"
LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


# ───────────────────────── 月度化与变化 ─────────────────────────
def me(s: pd.Series) -> pd.Series:
    """任何频率 → 月末：同一个月的值取平均（日度 = 月平均；月度 = 本身），放到该月最后一天。"""
    s = s.dropna()
    if s.empty:
        return s
    g = s.groupby(s.index.to_period("M")).mean()
    g.index = g.index.to_timestamp(how="end").normalize()
    return g.sort_index()


def full(s: pd.Series) -> pd.Series:
    """补齐为连续的月末索引（缺月 = NaN），shift(12) 才是 12 个月。"""
    if s.empty:
        return s
    return s.reindex(pd.date_range(s.index[0], s.index[-1], freq="ME"))


def d12(s: pd.Series) -> pd.Series:
    s = full(s)
    return s - s.shift(12)


def pct12(s: pd.Series) -> pd.Series:
    s = full(s)
    return (s / s.shift(12) - 1) * 100


def splice(a: pd.Series, b: pd.Series, at: str) -> pd.Series:
    """水平：a 到 at 之前、b 从 at 起。"""
    t = pd.Timestamp(at)
    return pd.concat([a[a.index < t], b[b.index >= t]]).sort_index()


def splice_d12(a: pd.Series, b: pd.Series, at: str, pct: bool = False) -> pd.Series:
    """分段算 Δ12 再接（接缝处不混两种口径）：b 从 at 起、它的前 12 个月没有 Δ12 时用 a 的；之后只用 b。"""
    f = pct12 if pct else d12
    t = pd.Timestamp(at)
    da, db = f(a), f(b[b.index >= t])
    out = db.combine_first(da).sort_index()
    late = out.index >= t + pd.DateOffset(months=12)
    out[late] = db.reindex(out.index)[late]
    return out[out.index >= min(da.index[0], db.index[0])] if len(da) and len(db) else out


def z_of(s: pd.Series, win: int = Z_WIN) -> pd.Series:
    s = full(s)
    m, sd = s.rolling(win, min_periods=win // 2).mean(), s.rolling(win, min_periods=win // 2).std()
    return (s - m) / sd


# ───────────────────────── 数据 ─────────────────────────
def imf_cpi_yoy() -> pd.Series | None:
    """IMF IFS 日本 CPI（2021-07 以后的续接；取不到 → None）。"""
    try:
        d = json.loads(F._get(IMF_CPI, timeout=40, tries=1))
        obs = d["CompactData"]["DataSet"]["Series"]["Obs"]
        s = pd.Series({pd.Timestamp(o["@TIME_PERIOD"]): float(o["@OBS_VALUE"]) for o in obs}).sort_index()
        return pct12(me(s))
    except Exception:                                                        # noqa: BLE001
        return None


def jp_data() -> tuple[dict, dict, dict]:
    """返回 (levels, deltas, notes)：levels[v] 月末水平；deltas[v] = 状态用的 12 个月变化（fx 为 %；boj 为同比 %；m2 为 同比 − 10 年中位）。"""
    fr = lambda i: me(F.fred(i, max_age_h=24 * 7))                          # noqa: E731
    disc, call = fr("INTDSRJPM193N"), fr("IRSTCI01JPM156N")
    pol, pol_d = splice(disc, call, "1996-01-01"), splice_d12(disc, call, "1996-01-01")
    j = F.jgb_curve()
    lt10, lt5 = me(j["10Y"]), me(j["5Y"])
    lt, lt_d = splice(lt5, lt10, "1986-07-01"), splice_d12(lt5, lt10, "1986-07-01")
    cpi = pct12(fr("JPNCPIALLMINMEI"))
    ext = imf_cpi_yoy()
    notes = {"cpi_ext": None}
    if ext is not None and len(ext.dropna()) and ext.dropna().index[-1] > cpi.dropna().index[-1]:
        ext = ext.dropna()
        ext = ext[ext.index > cpi.dropna().index[-1]]
        cpi = pd.concat([cpi.dropna(), ext]).sort_index()
        notes["cpi_ext"] = f"IMF IFS {ext.index[0].date()}〜{ext.index[-1].date()}"
    cpi_d = d12(cpi)
    fx = fr("EXJPUS")
    boj = pct12(fr("JPNASSETS"))
    m2 = splice(pct12(fr("MYAGM2JPM189N")), pct12(fr("MABMM301JPM189S")), "2017-03-01")
    m2f = full(m2)
    m2_x = m2f - m2f.rolling(Z_WIN, min_periods=Z_WIN // 2).median()
    us10, ff = fr("GS10"), fr("FEDFUNDS")
    L = {"pol": pol, "st": call, "lt": lt, "curve": (full(lt) - full(pol)).dropna(), "cpi": cpi.dropna(), "real": (full(lt) - full(cpi)).dropna(),
         "fx": fx, "boj": boj.dropna(), "m2": m2.dropna(), "us10": us10, "ff": ff, "diff": (full(us10) - full(lt)).dropna()}
    X = {"pol": pol_d, "st": d12(call), "lt": lt_d, "curve": (lt_d - pol_d.reindex(lt_d.index)), "cpi": cpi_d,
         "real": (lt_d - cpi_d.reindex(lt_d.index)), "fx": pct12(fx), "boj": full(boj), "m2": m2_x, "us10": d12(us10), "ff": d12(ff),
         "diff": (d12(us10).reindex(lt_d.index) - lt_d)}
    X = {k: v.dropna() for k, v in X.items()}
    return L, X, notes


def monthly_close(close: pd.Series) -> pd.Series:
    """月末收盘；还没结束的当月（最后一个月末在今天之后）不算「完整月」、去掉。"""
    c = close.dropna()
    mc = c.resample("ME").last().dropna()
    if len(mc) and mc.index[-1] > pd.Timestamp.today().normalize():
        mc = mc.iloc[:-1]
    return mc


# ───────────────────────── 状态 ─────────────────────────
def state_of(v: str, x: pd.Series) -> pd.Series:
    thr = 0.0 if v in GROWTH else D[v]
    s = pd.Series("flat", index=x.index, dtype=object)
    s[x > thr] = "up"
    s[x < -thr] = "down"
    return s


def z_state(lvl: pd.Series) -> pd.Series:
    z = z_of(lvl).dropna()
    s = pd.Series("flat", index=z.index, dtype=object)
    s[z >= 1] = "up"
    s[z <= -1] = "down"
    return s


def rule_state(x: pd.Series, direction: str, thr: float) -> pd.Series:
    return ((x > thr) if direction == "up" else (x < -thr)).fillna(False).astype(bool)


# ───────────────────────── 状态 → 之后的指数 ─────────────────────────
def fwd_ret(mc: pd.Series, h: int) -> pd.Series:
    mc = full(mc)
    return (mc.shift(-h) / mc - 1) * 100


def dd_within(mc: pd.Series, h: int = 12) -> pd.Series:
    """t 之后 1〜h 个月末里相对 t 的最低点（%）；不足 h 个月 → NaN。"""
    mc = full(mc)
    arr = pd.concat([(mc.shift(-k) / mc - 1) * 100 for k in range(1, h + 1)], axis=1)
    out = arr.min(axis=1)
    out[arr.isna().any(axis=1)] = np.nan
    return out


def _stats(ix: pd.DatetimeIndex, state: pd.Series, f6, f12, dd) -> dict:
    out = {}
    for st in ("up", "down", "flat"):
        m = ix[(state.reindex(ix) == st).to_numpy()]
        if len(m):
            out[st] = {"n": int(len(m)), "med12": round(float(f12[m].median()), 1), "hit12": round(float((f12[m] > 0).mean()) * 100, 1),
                       "med6": round(float(f6[m].median()), 1), "dd15": round(float((dd[m] <= DD_THR).mean()) * 100, 1)}
    return out


def bucket(state: pd.Series, mc: pd.Series, placebo_n: int = PLACEBO_N, seed: int = 0) -> dict:
    """上 / 下 / 平 → 之后 6 / 12 个月与 12 个月内最低点；年代；「上 − 下」的中位差与循环平移安慰剂；稳定。"""
    f6, f12, dd = fwd_ret(mc, 6), fwd_ret(mc, 12), dd_within(mc, 12)
    idx = state.index.intersection(f12.dropna().index)
    idx = idx[idx >= pd.Timestamp(EVAL0)]
    out = {"n": int(len(idx)), "all": _stats(idx, state, f6, f12, dd), "eras": {}, "diff": None, "pct": None, "stable": None, "era_sign": {}}
    if not len(idx):
        return out
    for name, a, b in ERAS:
        e = idx[(idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b))]
        if len(e):
            out["eras"][name] = _stats(e, state, f6, f12, dd)
    st = state.reindex(idx).to_numpy()
    f = f12[idx].to_numpy()
    up, dn = f[st == "up"], f[st == "down"]
    if len(up) >= MIN_ERA and len(dn) >= MIN_ERA:
        obs = float(np.median(up) - np.median(dn))
        rng = np.random.default_rng(seed)
        vals = []
        for _ in range(placebo_n):
            k = int(rng.integers(SHIFT_MIN, max(SHIFT_MIN + 1, len(st) - SHIFT_MIN)))
            sh = np.roll(st, k)
            u, d_ = f[sh == "up"], f[sh == "down"]
            if len(u) and len(d_):
                vals.append(float(np.median(u) - np.median(d_)))
        out["diff"] = round(obs, 1)
        out["pct"] = round(float(np.mean(np.abs(vals) < abs(obs))) * 100, 0) if vals else None
    for name, e in out["eras"].items():
        if e.get("up", {}).get("n", 0) >= MIN_ERA and e.get("down", {}).get("n", 0) >= MIN_ERA:
            out["era_sign"][name] = int(np.sign(e["up"]["med12"] - e["down"]["med12"]))
    sg = [v for v in out["era_sign"].values() if v != 0]
    out["stable"] = (len(sg) >= 2 and len(set(sg)) == 1) if sg else None
    return out


# ───────────────────────── 事件：加息 / 降息周期起点 ─────────────────────────
def cycle_starts(pol: pd.Series, up: bool = True) -> list[pd.Timestamp]:
    p = full(pol)
    d3 = p - p.shift(3)
    ext = p.rolling(12).max() if up else p.rolling(12).min()
    flag = ((d3 >= EV_D3) & (p >= ext - 1e-9)) if up else ((d3 <= -EV_D3) & (p <= ext + 1e-9))
    starts, last = [], None
    for t, f in flag.items():
        if bool(f):
            if last is None or t > last + pd.DateOffset(months=EV_GAP):
                starts.append(t)
            last = t
    return starts


def event_paths(mc: pd.Series, starts: list, eval0: str = "1965-12-31") -> dict:
    mcf = full(mc)
    base = {h: fwd_ret(mc, h).dropna() for h in EV_H}
    rows = []
    for t in starts:
        if t < pd.Timestamp(eval0) or t not in mcf.index or pd.isna(mcf[t]):
            continue
        row = {"date": t.strftime("%Y-%m")}
        for h in EV_H:
            th = t + pd.offsets.MonthEnd(h)
            v = mcf.get(th)
            if v is not None and not pd.isna(v):
                r = (float(v) / float(mcf[t]) - 1) * 100
                row[f"r{h}"] = round(r, 1)
                row[f"p{h}"] = round(float((base[h] < r).mean()) * 100, 0)
        rows.append(row)
    out = {"n": len(rows), "events": rows}
    for h in EV_H:
        rs = [r[f"r{h}"] for r in rows if f"r{h}" in r]
        ps = [r[f"p{h}"] for r in rows if f"p{h}" in r]
        if rs:
            out[f"med{h}"] = round(float(np.median(rs)), 1)
            out[f"neg{h}"] = round(float(np.mean(np.array(rs) < 0)) * 100, 0)
            out[f"medp{h}"] = round(float(np.median(ps)), 0)
    return out


# ───────────────────────── 规则（指数级） ─────────────────────────
def rule_eval(mc: pd.Series, on: pd.Series, eval0: str = EVAL0, split: str = SPLIT, seeds: int = SEEDS, rng_seed: int = 0) -> dict:
    """t − 1 月末状态满足 → t 月 ×0.5；Calmar 对持有；两半；循环平移安慰剂。"""
    mcf = full(mc)
    r = (mcf / mcf.shift(1) - 1).dropna()
    onf = on.reindex(r.index.union(on.index)).fillna(False).astype(bool)
    prev = onf.shift(1).reindex(r.index).fillna(False).astype(bool)
    e0 = max(pd.Timestamp(eval0), on.index[0] if len(on) else pd.Timestamp(eval0))
    m = r.index > e0
    r, prev = r[m], prev[m]
    n = int(len(r))
    if n < MIN_HALF:
        return {"n": n, "skip": "评估月不够", "delta": None}
    hold = K.calmar_m(r)
    rr = r * np.where(prev.to_numpy(), HALF, 1.0)
    rule = K.calmar_m(rr)
    dl = lambda a, b: (None if a["calmar"] is None or b["calmar"] is None else round(b["calmar"] - a["calmar"], 3))   # noqa: E731
    on_r, off_r = r[prev.to_numpy()], r[~prev.to_numpy()]
    out = {"n": n, "from": str(r.index[0].date()), "to": str(r.index[-1].date()), "hold": hold, "rule": rule, "delta": dl(hold, rule),
           "on_share": round(float(prev.mean()) * 100, 1), "on_mean": (round(float(on_r.mean()) * 100, 2) if len(on_r) else None),
           "off_mean": (round(float(off_r.mean()) * 100, 2) if len(off_r) else None),
           "diff": (round(float(on_r.mean() - off_r.mean()) * 100, 2) if len(on_r) and len(off_r) else None), "halves": {}}
    for tag, (a, b) in {"h1": (None, split), "h2": (split, None)}.items():
        mm = ((r.index > pd.Timestamp(a)) if a else np.ones(n, bool)) & ((r.index <= pd.Timestamp(b)) if b else np.ones(n, bool))
        if int(mm.sum()) >= MIN_HALF:
            h, ru = K.calmar_m(r[mm]), K.calmar_m(rr[mm])
            out["halves"][tag] = {"n": int(mm.sum()), "hold": h["calmar"], "rule": ru["calmar"], "delta": dl(h, ru)}
    rng = np.random.default_rng(rng_seed)
    pl = []
    for _ in range(seeds):
        k = int(rng.integers(SHIFT_MIN, max(SHIFT_MIN + 1, n - SHIFT_MIN)))
        sh = K.shifted(prev, k)
        ru = K.calmar_m(r * np.where(sh.to_numpy(), HALF, 1.0))
        pl.append(dl(hold, ru))
    v = [x for x in pl if x is not None]
    out["placebo"] = {"vals": pl, "q95": (round(float(np.percentile(v, 95)), 3) if v else None), "median": (round(float(np.median(v)), 3) if v else None)}
    return out


# ───────────────────────── 横向：其他市场 ─────────────────────────
def market_series(cc: str) -> dict:
    out = {}
    for key, sid in (("lt", "GS10" if cc == "US" else f"IRLTLT01{cc}M156N"), ("st", "FEDFUNDS" if cc == "US" else f"IRSTCI01{cc}M156N"),
                     ("cpi", f"CPALTT01{cc}M659N")):
        try:
            out[key] = me(F.fred(sid, max_age_h=24 * 7))
        except Exception:                                                    # noqa: BLE001
            out[key] = None
    return out


def market_states(ms: dict, us10: pd.Series) -> dict:
    """五条规则在一个市场的状态序列（取不到的项 → None）。"""
    lt, st, cpi = ms.get("lt"), ms.get("st"), ms.get("cpi")
    S = {}
    S["R1"] = rule_state(d12(lt), "up", RULES["R1"][2]) if lt is not None else None
    S["R2"] = rule_state(d12(st), "up", RULES["R2"][2]) if st is not None else None
    S["R3"] = rule_state(d12((full(lt) - full(st)).dropna()), "down", RULES["R3"][2]) if lt is not None and st is not None else None
    S["R4"] = rule_state(d12((full(lt) - full(cpi)).dropna()), "up", RULES["R4"][2]) if lt is not None and cpi is not None else None
    S["R5"] = rule_state(d12((full(us10) - full(lt)).dropna()), "up", RULES["R5"][2]) if lt is not None and ms.get("not_us", True) else None
    return S


def pooled_q95(res: dict) -> float | None:
    """各种子的「市场平均 Δ」→ 95 分位（与 K4 横向相同）。"""
    rows = [x["placebo"]["vals"] for x in res.values() if x.get("placebo")]
    if not rows:
        return None
    n = min(len(v) for v in rows)
    means = []
    for i in range(n):
        vs = [v[i] for v in rows if v[i] is not None]
        if vs:
            means.append(float(np.mean(vs)))
    return round(float(np.percentile(means, 95)), 3) if means else None


def decide(jp: dict, horiz: dict) -> dict:
    out = {}
    for r in RULES:
        x = jp.get(r) or {}
        h = x.get("halves") or {}
        d1 = bool(h.get("h1") and h.get("h2") and h["h1"]["delta"] is not None and h["h2"]["delta"] is not None
                  and h["h1"]["delta"] >= D1_MIN and h["h2"]["delta"] >= D1_MIN)
        q95 = (x.get("placebo") or {}).get("q95")
        d2 = bool(x.get("delta") is not None and q95 is not None and x["delta"] >= q95)
        d3 = bool(x.get("on_share") is not None and x["on_share"] <= 50)
        Fm = {cc: y for cc, y in (horiz.get(r) or {}).items() if cc != "JP" and y.get("delta") is not None and y.get("n", 0) >= MIN_MONTHS}
        share = (float(np.mean([y["delta"] >= 0 for y in Fm.values()])) if Fm else None)
        mean = (round(float(np.mean([y["delta"] for y in Fm.values()])), 3) if Fm else None)
        pq = pooled_q95(Fm) if Fm else None
        d4 = bool(len(Fm) >= MIN_FOREIGN and share is not None and share >= SHARE_2_3 - 1e-9 and mean is not None and pq is not None and mean > pq)
        out[r] = {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "pass14": d1 and d2 and d3 and d4,
                  "h": {"n_foreign": len(Fm), "share_pos": (round(share * 100, 0) if share is not None else None), "mean": mean, "pooled_q95": pq}}
    return out


def account_check(A: dict) -> dict:
    """D5：JP-T + 规则 20 年 Calmar ≥ 现行 + 0.02，E、J 各 ≥ 现行 − 0.01。"""
    b, k = A["JP-T"]["base"], A["JP-T"]["k"]
    c = lambda d: d.get("calmar")                                            # noqa: E731
    ok = (c(b["all"]) is not None and c(k["all"]) is not None and c(k["all"]) >= c(b["all"]) + D5_UP
          and all(c(k[w]) is not None and c(b[w]) is not None and c(k[w]) >= c(b[w]) - D5_TOL for w in ("E", "J")))
    return {"D5": bool(ok), "base": {w: c(b[w]) for w in ("all", "E", "J")}, "k": {w: c(k[w]) for w in ("all", "E", "J")}}


# ───────────────────────── 主流程 ─────────────────────────
def _f(x, nd=3):
    return "—" if x is None else f"{x:.{nd}f}"


def run(smoke: bool = False) -> dict:
    t0 = time.time()
    placebo_n, seeds = (20, 5) if smoke else (PLACEBO_N, SEEDS)
    say("# 日本历年利率等 × 日経 横展开（登记后只运行一次）")
    say(f"运行 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}；门槛与判定见 scripts/jp_rates_study.py 开头" + ("（smoke：只看接线）" if smoke else ""))
    L, X, notes = jp_data()
    n225, spx = monthly_close(F.yf_close("^N225")), monthly_close(F.yf_close("^GSPC"))
    say("\n## 一、数据覆盖（月末）")
    say(f"- 日経225 {n225.index[0].date()}〜{n225.index[-1].date()}（{len(n225)} 个月）；S&P 500 {spx.index[0].date()}〜")
    for v in VARS:
        say(f"- {v} {LABELS[v]}：水平 {L[v].index[0].date()}〜{L[v].index[-1].date()}；状态值 {X[v].index[0].date()}〜{X[v].index[-1].date()}（{len(X[v])} 个月）")
    say(f"- CPI 续接：{notes.get('cpi_ext') or '没有（到 2021-06 为止）'}")
    out: dict = {"coverage": {v: {"from": str(L[v].index[0].date()), "to": str(L[v].index[-1].date())} for v in VARS}, "notes": notes}
    if smoke:
        say("- smoke：只检查数据与接线，不写结果")
    # 三、状态 → 之后的日経
    say("\n## 二、日本：状态（12 个月变化）→ 之后的日経225（1975-10 起；中位 %，> 0 比例 %，12 个月内 ≤ −15% 比例 %）")
    say("| 变量 | 状态 | 月数 | 6 个月 | 12 个月 | > 0 | ≤ −15% | E1 上/下 | E2 上/下 | E3 上/下 | 上 − 下 | 安慰剂分位 | 稳定 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    T: dict = {}
    for v in VARS:
        b = bucket(state_of(v, X[v]), n225, placebo_n)
        T[v] = b
        if smoke:
            continue
        for st, lab in (("up", "上"), ("down", "下"), ("flat", "平")):
            a = b["all"].get(st)
            if not a:
                continue
            era = " | ".join(f"{(b['eras'].get(e, {}).get('up') or {}).get('med12', '—')}/{(b['eras'].get(e, {}).get('down') or {}).get('med12', '—')}" for e in ("E1", "E2", "E3"))
            tail = (f"{b['diff']:+.1f} | {b['pct']:.0f} | {'稳' if b['stable'] else ('不稳' if b['stable'] is False else '—')}" if st == "up" and b["diff"] is not None
                    else " | | ")
            say(f"| {v} {LABELS[v] if st == 'up' else ''} | {lab} | {a['n']} | {a['med6']:+.1f} | {a['med12']:+.1f} | {a['hit12']:.0f} | {a['dd15']:.0f} | {era} | {tail} |")
    out["tables"] = T
    say("\n### 水平（z 对过去 10 年；高 ≥ +1 / 低 ≤ −1）→ 之后 12 个月（只描述）")
    say("| 变量 | 高：月数 / 中位 / > 0 | 低：月数 / 中位 / > 0 | 高 − 低 | 安慰剂分位 |")
    say("|---|---|---|---|---|")
    Z: dict = {}
    for v in VARS:
        b = bucket(z_state(L[v]), n225, placebo_n)
        Z[v] = b
        if smoke:
            continue
        hi, lo = b["all"].get("up") or {}, b["all"].get("down") or {}
        say(f"| {v} | {hi.get('n', 0)} / {_f(hi.get('med12'), 1)} / {_f(hi.get('hit12'), 0)} | {lo.get('n', 0)} / {_f(lo.get('med12'), 1)} / {_f(lo.get('hit12'), 0)} | "
            f"{_f(b['diff'], 1)} | {_f(b['pct'], 0)} |")
    out["levels"] = Z
    say("\n### 对照：美国变量 → 之后的 S&P 500")
    U: dict = {}
    for v in ("us10", "ff"):
        b = bucket(state_of(v, X[v]), spx, placebo_n)
        U[v] = b
        if not smoke:
            a, d_ = b["all"].get("up") or {}, b["all"].get("down") or {}
            say(f"- {LABELS[v]}：上 {a.get('n', 0)} 个月 中位 {_f(a.get('med12'), 1)}%、下 {d_.get('n', 0)} 个月 {_f(d_.get('med12'), 1)}%；上 − 下 {_f(b['diff'], 1)} pp，"
                f"安慰剂分位 {_f(b['pct'], 0)}，{'稳定' if b['stable'] else '不稳定' if b['stable'] is False else '年代不够'}")
    out["us_control"] = U
    # 事件
    say("\n## 三、事件：政策金利 加息 / 降息周期起点 → 之后的日経（只描述）")
    EV = {"hike": event_paths(n225, cycle_starts(L["pol"], True)), "cut": event_paths(n225, cycle_starts(L["pol"], False))}
    out["events"] = EV
    if not smoke:
        for key, lab in (("hike", "加息周期起点"), ("cut", "降息周期起点")):
            e = EV[key]
            say(f"- {lab} {e['n']} 次：" + "；".join(f"{r['date']} 12 个月 {r.get('r12', float('nan')):+.1f}%（分位 {r.get('p12', float('nan')):.0f}）24 个月 {r.get('r24', float('nan')):+.1f}%"
                                               for r in e["events"]))
            if e["n"]:
                say(f"  中位：3 个月 {_f(e.get('med3'), 1)}%、6 个月 {_f(e.get('med6'), 1)}%、12 个月 {_f(e.get('med12'), 1)}%（下跌 {_f(e.get('neg12'), 0)}%，分位中位 {_f(e.get('medp12'), 0)}）、"
                    f"24 个月 {_f(e.get('med24'), 1)}%（下跌 {_f(e.get('neg24'), 0)}%，分位中位 {_f(e.get('medp24'), 0)}）")
    # 规则：日本
    say("\n## 四、规则（指数级：t − 1 月末满足 → t 月 ×0.5）：日経225")
    say("| 规则 | 评估 | 月数 | 满足 % | 持有 Calmar | 规则 Calmar | Δ | H1 Δ | H2 Δ | 安慰剂 q95 | 满足月次月均 − 不满足 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    JR: dict = {}
    for r, (var, dirn, thr, lab) in RULES.items():
        x = rule_eval(n225, rule_state(X[var], dirn, thr), seeds=seeds)
        JR[r] = x
        if smoke or x.get("skip"):
            continue
        say(f"| {r} {lab} | {x['from']}〜{x['to']} | {x['n']} | {x['on_share']:.0f} | {_f(x['hold']['calmar'])} | {_f(x['rule']['calmar'])} | {_f(x['delta'])} | "
            f"{_f((x['halves'].get('h1') or {}).get('delta'))} | {_f((x['halves'].get('h2') or {}).get('delta'))} | {_f(x['placebo']['q95'])} | {_f(x['diff'], 2)} pp |")
    out["jp_rules"] = JR
    # 横向
    say("\n## 五、横向：同一条规则放到其他市场（Δ = 规则 Calmar − 持有；评估月 ≥ 120 才参与判定）")
    import threat_intl_study as T_
    us10 = L["us10"]
    H: dict = {r: {} for r in RULES}
    codes = list(MARKETS) if not smoke else ["US", "DE", "GB"]
    for cc in codes:
        sym, name = MARKETS[cc]
        try:
            close, _ = T_.index_close(sym)
        except Exception as e:                                               # noqa: BLE001
            say(f"- {cc} {name}：指数取不到（{type(e).__name__}）→ 跳过")
            continue
        mc = monthly_close(close)
        ms = market_series(cc)
        ms["not_us"] = cc != "US"
        S = market_states(ms, us10)
        for r in RULES:
            if S.get(r) is None or not len(S[r]):
                continue
            H[r][cc] = {**rule_eval(mc, S[r], eval0="1960-01-31", seeds=seeds), "name": name}
    for r, (var, dirn, thr, lab) in RULES.items():
        rows = [(cc, y) for cc, y in H[r].items() if y.get("delta") is not None]
        if smoke:
            say(f"- {r} {lab}：{len(rows)} 个市场算得出（smoke 不列数字）")
            continue
        if not rows:
            say(f"- {r} {lab}：没有市场算得出")
            continue
        say(f"\n### {r} {lab}（{len(rows)} 个市场）")
        say("| 市场 | 评估 | 月数 | 满足 % | Δ | H1 Δ | H2 Δ | 安慰剂 q95 | 满足月次月均 − 不满足 |")
        say("|---|---|---|---|---|---|---|---|---|")
        for cc, y in sorted(rows, key=lambda t: -(t[1]["delta"] or 0)):
            say(f"| {cc} {y['name']} | {y['from']}〜{y['to']} | {y['n']} | {y['on_share']:.0f} | {_f(y['delta'])} | {_f((y['halves'].get('h1') or {}).get('delta'))} | "
                f"{_f((y['halves'].get('h2') or {}).get('delta'))} | {_f(y['placebo']['q95'])} | {_f(y['diff'], 2)} pp |")
    out["horizontal"] = H
    # 判定
    dec = decide(JR, H)
    out["decision"] = dec
    say("\n## 六、判定（事先写定）")
    passes = []
    for r, (var, dirn, thr, lab) in RULES.items():
        d = dec[r]
        if smoke:
            say(f"- {r}：smoke 不列判定")
            continue
        say(f"- {r} {lab}：D1 两半 ≥ +0.02 {'过' if d['D1'] else '不过'}；D2 ≥ 安慰剂 95 分位 {'过' if d['D2'] else '不过'}；D3 满足 ≤ 50% {'过' if d['D3'] else '不过'}；"
            f"D4 横向（外国 {d['h']['n_foreign']} 个：Δ ≥ 0 占 {_f(d['h']['share_pos'], 0)}%，平均 Δ {_f(d['h']['mean'])} vs 合并安慰剂 q95 {_f(d['h']['pooled_q95'])}）{'过' if d['D4'] else '不过'}"
            + ("　→ 进账户级（D5）" if d["pass14"] else ""))
        if d["pass14"]:
            passes.append(r)
    out["account"] = {}
    if passes and not smoke:
        say("\n## 七、账户级（D5）：JP-T 现行 vs + 规则（market_compare 框架）")
        for r in passes:
            var, dirn, thr, lab = RULES[r]
            on_jp = rule_state(X[var], dirn, thr)
            sig_jp = pd.Series(np.where(on_jp.to_numpy(), -10.0, 0.0), index=on_jp.index)
            us_states = market_states({**market_series("US"), "not_us": False}, us10)
            on_us = us_states.get(r)
            sig_us = (pd.Series(np.where(on_us.to_numpy(), -10.0, 0.0), index=on_us.index) if on_us is not None and len(on_us)
                      else pd.Series(0.0, index=on_jp.index))
            A = K.run_accounts(False, -0.5, sig_jp, sig_us)
            chk = account_check(A)
            out["account"][r] = {"check": chk, "A": {arm: A[arm] for arm in ("JP-T", "US-0", "US-R") if arm in A}, "on_share": A.get("on_share")}
            say(f"- {r} {lab}：JP-T 现行 Calmar 20 年 / E / J = {_f(chk['base']['all'])} / {_f(chk['base']['E'])} / {_f(chk['base']['J'])} → + 规则 "
                f"{_f(chk['k']['all'])} / {_f(chk['k']['E'])} / {_f(chk['k']['J'])}；D5 {'过' if chk['D5'] else '不过'}")
    adopted = [r for r in passes if (out["account"].get(r) or {}).get("check", {}).get("D5")]
    verdict = ("提议（要用户确认）：" + "、".join(adopted) if adopted else "不通过（只描述）")
    out["passes14"], out["adopted"], out["verdict"] = passes, adopted, verdict
    say(f"\n## 八、结论：{verdict}")
    say(f"用时 {time.time() - t0:.0f} s")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="只检查数据覆盖与接线（结果不写入 var/out 的正式文件）")
    a = ap.parse_args(argv)
    out = run(smoke=a.smoke)
    tag = "_smoke" if a.smoke else ""
    od = paths.PROJECT_ROOT / "var" / "out"
    od.mkdir(parents=True, exist_ok=True)
    (od / f"jp_rates_study{tag}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    (od / f"jp_rates_study{tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: None), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
