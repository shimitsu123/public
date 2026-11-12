"""core_switch_study.py — 核心层「按状态选模型」：把七个核心模型的长处合起来，按当天能观测到的状态决定用哪一个
（2026-09-30 事先登记：先提交后只运行一次，结果出来不改规则）。

来由：用户「把上述每个模型的优点结合一下，根据当前情况自动判断在哪一段用哪种模型之类的 进行研究」。「上述模型」= 2026-09-30
「Calmar 还能怎么问」里列的核心层模型。它们各自在某一段好、另一段差（登记检验都没通过或差一条；Calmar 对现行的差）：
  常配黄金 G3：2006〜2016 +0.070（回撤浅 8.7 pp）、2017〜2026 +0.056；输在 2011〜2016 后半（2013 年 +45% vs +62%）
  汇率对冲 F1：日元升值的年代好（1986〜2005 +0.037、2006〜2016 +0.098），日元贬值的 2017〜2026 −0.098
  季节性 H1：1950〜2005 +0.140、2006〜2016 +0.189；2017〜2026 −0.140
  深跌加仓 D2：2017〜2026 +0.071（回撤浅 4 pp）、2006〜2016 +0.019（差 0.001）
  纳指核心 N1 / Q1：两个年代都好（E +0.169、J +0.139；模拟盘 2026-09-30 起已用 1545），1987〜2005 回撤深 7 pp、2022 科技股熊市差
  晚卖守卫（新）：牛熊分界发出转现金信号时指数已经跌了 15% 以上就不卖 —— 针对 2020 年卖在 −28.7% 的情形；没测过
账户的四次大回撤都来自核心 + 牛熊分界这一层（2026-09-30 回撤分解），所以这里只动核心层；个股层（W2 突破 + X6、4 × 25%）不变。

一、资产（都是日元、东证交易日 d 的价 = 前一个美国收盘 × 前一个汇率，与 equity_idle_study 同一做法；全程合成，价格水平按 2026-08-31 定）
  1655 S&P500 总收益 − 0.066%/年（1988 年以前 ^GSPC + 3.5%/年）；1545 纳指总收益 − 0.22%/年（1999 年以前 ^NDX + 0.6%/年）；
  2563 对冲版 S&P500 = S&P500 本地总收益 + (日本 − 美国 短期利率)/252（fxhedge_study 的做法；费用同 1655）；2845 对冲版纳指（同法；费用同 1545）；
  1540 黄金 = COMEX 金期货连续 GC=F（2004-11 起 GLD）× USD/JPY ÷ 3.11 —— **2000-08-30 起才有**，之前「黄金」这一档不可用（→ 现金）；
  1321 日経225 + 1.6%/年股息（深跌加仓用）；现金 0%。汇率：2000 年起 yfinance JPY=X（FRED 修正错价，与 equity_idle 同），之前 FRED DEXJPUS。
  牛熊分界 T0 = 现行检测器用在 S&P500（var/bullbear.json）；熊 → 股票类 ETF 目标 0（现行做法）。
二、状态（每天收盘时都能算、只用当天为止的数据；美国数据按引擎现行做法同一天生效）
  bear：T0 熊；guard：守卫后的熊 —— T0 从牛翻熊那天 S&P500 收盘 ≤ 过去 250 天最高收盘 × 0.85 → 这一段熊全部当牛（不卖），T0 回牛后恢复；
  yen：USD/JPY < 200 日线（日元走强，F1 的定义）；gold_up：黄金（日元）月末收盘 > 最近 10 个月末的平均（qbreak/idle_cash K2 的定义）→ 下个月；
  rs_ndx：月末 过去 252 天 纳指总收益 > S&P500 总收益（美元）→ 下个月用纳指，否则 S&P500（不够 252 天 → S&P500）；
  summer：5〜10 月；dip：日経225 13 周线乖离第一次 ≤ −15% 起 60 个交易日（stack_study / deepdip_forward 同一定义）。
三、八个模型（每天给核心的配比；剩下 = 现金；「指数」= 1655，Q 与 F 例外）
  A 现行 S&P500 + 牛熊（= K0 / S0）        Q 模拟盘现在：纳指 1545 + 牛熊（= equity_idle 的 Q1；**判定的「现行」**）
  B 常配黄金：牛市 指数 80% + 黄金 20%（黄金不可用 → 指数 100%）；熊 → 现金          C 汇率对冲：牛市 且 yen → 对冲版 100%，否则指数 100%
  D 季节性：牛市 且 summer → 指数 50%，否则 100%                                      E 深跌加仓：dip 里 1321 = 25%；牛市 指数 75%（dip 外 100%）；熊 只拿 1321 25%
  F 择强指数：牛市 rs_ndx → 纳指 100%，否则 S&P500 100%                                G 晚卖守卫：A，但用 guard 代替 bear
四、候选（事先固定，不调参）
  S1 状态表：指数按 F 选、牛熊用 guard；每天按优先级选一个：dip → E 的配比；熊 → 现金；yen → 对冲版 100%；gold_up → 指数 80% + 黄金 20%；
     summer → 指数 50%；其余 指数 100%
  S2 近期择优：每月末在 A / Q / B / C / D / E / F / G 里选过去 36 个月「只有核心」Calmar 最高的（不足 24 个月 → A），下个月用它
  S3 等权混合：每天拿八个模型配比的平均
  S4 全叠加：指数按 F 选、牛熊用 guard、yen 时换对冲版、gold_up 时 20% 黄金、summer 时基数减半、dip 时 1321 25% 且股票类 × 0.75，全部同时生效
五、对照：八个模型各自；安慰剂 P1 = 每月随机选一个模型（20 个种子；给 S2 / S3 用）；安慰剂 P2 = S4 但 yen / gold_up / rs_ndx / summer / dip / guard
  整体循环平移一个随机天数（250 天以上；20 个种子；给 S1 / S4 用）；上限 = 每月事后选下个月收益最高的模型（作弊，只描述）。
六、判定（事先写定；「现行」= Q；全部满足才「提议」）
  主 P（想法来源之外）：1987-01〜2005-12 只有核心（日元计、前一天收盘的状态决定当天持仓、每次调整按换手扣 0.1%）：
    Calmar ≥ Q + 0.05、最大回撤不比 Q 深 2 pp、两个半段（1987〜1996 / 1997〜2005）各自 Calmar ≥ Q；
  账户（S0C2 + W2 + X6，立花费用，真实一手；候选的配比进引擎 = 权益 − 个股 的部分按配比分）：E 2006-10〜2016-09 与 J 2017-01〜 的
    Calmar 都 ≥ Q + 0.02 且最大回撤都不比 Q 深 2 pp；Z 2001-01〜2006-09 Calmar ≥ Q − 0.02；
  安慰剂：P 里 Calmar > 对应安慰剂的 95 分位，J 里也 > 对应安慰剂的 95 分位。
  多个通过 → 提议 P 的 Calmar 最高的。通过也只是提议：模拟盘改不改要用户确认，执行器还要会买 1540 / 2563 / 2845 / 1321。
七、事前预期（写在运行前）：S3 最容易满足回撤条件但 Calmar 提高不到 +0.05 → 不通过；S2 会慢半拍（同双动量 M1 / M2）→ 不通过；
  S1 / S4 在 1987〜1996（日元升值）靠对冲、在 2017〜2026 靠守卫 + 深跌加仓可能更好，但 1997〜2005 半段与 2011〜2016 后半（黄金 / 季节性拖累）
  可能翻车 → 通过的概率约 20%；上限会高很多（每月事后选）；P1 中位 ≈ 各模型的平均 ≈ Q 附近，P2 中位低于 S4。
八、另报（只描述）：各状态占的天数比例、S1 每个分支占的天数、每年切换次数、每年收益（S 候选 vs Q）、2006〜2016 与 2017〜2026 只有核心的对照。
九、局限：全程合成价（对冲版的实际费用与对冲成本、黄金 ETF 的价差会不同）；黄金 2000-08 以前没有；候选是看过各模型结果之后设计的
  （所以主判定放在 1987〜2005、并加循环平移安慰剂）；引擎的核心调仓带宽 10% 让 S3 的小幅变化不会每天执行（账户里 S3 = 带 10% 带宽的混合）；税前。
登记前做过的检查：tests/test_core_switch_study.py（守卫、状态不偷看、配比之和 ≤ 1 与不可用 → 现金、只有核心的净值、S1 优先级、S2 只用过去、
  上限 / 安慰剂、引擎编码 = 单资产核心）；QBREAK_SMOKE=1 只跑接线检查（不看任何结果数字）。
运行时的硬检查：Q 的配比经通用编码进引擎 → 必须与 Q1 的直接设定一致（三个年代 Calmar 差 ≤ 0.001），不一致就停下、不算候选。
输出：var/out/core_switch_study.md / .json（只有统计）。非投资建议。
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
ASSETS = ("1655.T", "1545.T", "2563.T", "2845.T", "1540.T", "1321.T")
ANAME = {"1655.T": "S&P500", "1545.T": "纳指", "2563.T": "S&P500 对冲", "2845.T": "纳指对冲", "1540.T": "黄金", "1321.T": "日経225"}
HEDGED = {"1655.T": "2563.T", "1545.T": "2845.T"}
MODELS = {"A": "现行 S&P500 + 牛熊", "Q": "模拟盘现在：纳指 1545 + 牛熊", "B": "常配黄金 20%（G3）", "C": "日元走强时对冲（F1）",
          "D": "5〜10 月核心 50%（H1）", "E": "深跌加仓（D2）", "F": "择强指数（纳指 vs S&P500）", "G": "晚卖守卫（−15%）"}
CANDS = {"S1": "状态表（每天按优先级选一个）", "S2": "近期择优（每月按过去 36 个月 Calmar 选）", "S3": "等权混合（8 个模型的平均）",
         "S4": "全叠加（所有条件同时生效）"}
BASE = "Q"
GUARD_DD, GUARD_N = -15.0, 250
GOLD_W, GOLD_MONTHS = 0.20, 10
SEASON_W = 0.5
RS_N = 252
DIP_W = 0.25
SEL_MONTHS, SEL_MIN = 36, 24
SWITCH_COST = 0.1
PLACEBO_SEEDS = 20
SHIFT_MIN = 250
P_WIN = {"P": ("1987-01-01", "2006-01-01"), "P1": ("1987-01-01", "1997-01-01"), "P2": ("1997-01-01", "2006-01-01")}
REF_WIN = {"E 只有核心": ("2006-10-01", "2016-10-01"), "J 只有核心": ("2017-01-01", "2027-01-01")}
CAL_UP_P, CAL_UP, DD_TOL, Z_TOL, HARD_TOL = 0.05, 0.02, 2.0, 0.02, 0.001
ERAS = ("Z", "E", "J")
GOLD_DIV = 3.11
FEE_H = {"2563.T": 0.066, "2845.T": 0.22}
PLACEBO_FAMILY = {"S1": "P2", "S2": "P1", "S3": "P1", "S4": "P2"}
ACCT_FROM = "1999-01-01"                                                     # 账户用的合成 K 线从这里起（Z 窗口 2001 年起）
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 状态 ─────────────────────────
def guard_bear(spx: pd.Series, bear: pd.Series, dd_thr: float = GUARD_DD, n: int = GUARD_N) -> pd.Series:
    """守卫后的熊：T0 从牛翻熊那天 收盘 ≤ 过去 n 天（含当天）最高收盘 × (1 + dd_thr/100) → 这一段熊全部当牛，T0 回牛后恢复。"""
    b = bear.reindex(spx.index).fillna(False).to_numpy(bool)
    c = spx.to_numpy(float)
    hi = pd.Series(c, index=spx.index).rolling(n, min_periods=n).max().to_numpy(float)
    out = b.copy()
    skip = False
    for i in range(len(b)):
        if b[i] and (i == 0 or not b[i - 1]):
            skip = bool(np.isfinite(hi[i]) and hi[i] > 0 and c[i] / hi[i] - 1 <= dd_thr / 100)
        if not b[i]:
            skip = False
        if b[i] and skip:
            out[i] = False
    return pd.Series(out, index=spx.index)


def on_days(s: pd.Series, days: pd.DatetimeIndex, fill=False) -> pd.Series:
    """放到东证日历上（向前填，与引擎读牛熊 / 状态的方式相同）。"""
    days = pd.DatetimeIndex(days)
    return s.reindex(days.union(s.index)).ffill().reindex(days).fillna(fill)


def month_ends(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    d = pd.DatetimeIndex(days)
    return pd.DatetimeIndex([g.max() for _, g in d.to_series().groupby([d.year, d.month])])


def next_month_flag(flag_at_me: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """月末收盘时定的布尔 → 下个月（月末之后到下一个月末为止）每天的值；之前没有 → False。"""
    days = pd.DatetimeIndex(days)
    out = pd.Series(False, index=days)
    me = flag_at_me.dropna().sort_index()
    for d, v in me.items():
        k = int(days.searchsorted(pd.Timestamp(d), side="right"))
        if k >= len(days):
            continue
        nxt = me.index[me.index > d]
        k2 = int(days.searchsorted(nxt[0], side="right")) if len(nxt) else len(days)
        out.iloc[k:k2] = bool(v)
    return out


def gold_up_flag(gold_jpy: pd.Series, days: pd.DatetimeIndex, months: int = GOLD_MONTHS) -> pd.Series:
    """黄金月末收盘 > 最近 months 个月末的平均（含这个月末）→ 下个月 True（idle_cash K2 的定义）；不可用 → False。"""
    g = gold_jpy.dropna()
    if not len(g):
        return pd.Series(False, index=pd.DatetimeIndex(days))
    me = g.groupby([g.index.year, g.index.month]).last()
    me.index = [g[(g.index.year == y) & (g.index.month == m)].index[-1] for y, m in me.index]
    me = pd.Series(me.to_numpy(float), index=pd.DatetimeIndex(me.index))
    avg = me.rolling(months, min_periods=months).mean()
    return next_month_flag((me > avg) & avg.notna(), days)


def rs_flag(ndx_usd: pd.Series, spx_usd: pd.Series, days: pd.DatetimeIndex, n: int = RS_N) -> pd.Series:
    """月末 过去 n 天 纳指总收益 > S&P500 总收益 → 下个月 True；不够 n 天 → False。"""
    idx = ndx_usd.dropna().index.union(spx_usd.dropna().index)
    a, b = ndx_usd.reindex(idx).ffill(), spx_usd.reindex(idx).ffill()
    ra, rb = a / a.shift(n) - 1, b / b.shift(n) - 1
    me = month_ends(idx)
    f = ((ra > rb) & ra.notna() & rb.notna() & a.notna() & b.notna()).reindex(me)
    return next_month_flag(f.fillna(False), days)


def dip_flag(days: pd.DatetimeIndex, events) -> pd.Series:
    import stack_study as SS
    return SS.window_mask(days, events)


def states_frame(days: pd.DatetimeIndex, spx_usd: pd.Series, ndx_tr: pd.Series, spx_tr: pd.Series, fx: pd.Series,
                 gold_jpy: pd.Series, events) -> pd.DataFrame:
    """每天的状态（bear / guard / yen / gold_up / rs_ndx / summer / dip / gold_ok）。"""
    import fxhedge_study as FX
    from qbreak.bullbear import BEAR, Detector, load_config
    d = load_config()["detector"]
    spx = spx_usd.dropna()
    bear = pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(spx)) == BEAR, index=spx.index)
    days = pd.DatetimeIndex(days)
    S = pd.DataFrame(index=days)
    S["bear"] = on_days(bear, days).astype(bool)
    S["guard"] = on_days(guard_bear(spx, bear), days).astype(bool)
    S["yen"] = on_days(FX.yen_strong(fx.dropna()), days).astype(bool)
    S["gold_up"] = gold_up_flag(gold_jpy, days).astype(bool)
    S["gold_ok"] = gold_jpy.reindex(days).notna().to_numpy()
    S["rs_ndx"] = rs_flag(ndx_tr, spx_tr, days).astype(bool)
    S["summer"] = ((days.month >= 5) & (days.month <= 10))
    S["dip"] = dip_flag(days, events).astype(bool)
    return S


# ───────────────────────── 模型的配比 ─────────────────────────
def _empty(S: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(0.0, index=S.index, columns=list(ASSETS))


def _put(W: pd.DataFrame, mask: pd.Series, ticker_by_day: pd.Series, w: pd.Series | float) -> None:
    """mask 为 True 的日子：把 w 加到 ticker_by_day 指的那一列。"""
    for t in ASSETS:
        m = mask & (ticker_by_day == t)
        if m.any():
            W.loc[m, t] = W.loc[m, t] + (w[m] if isinstance(w, pd.Series) else w)


def index_series(S: pd.DataFrame, model: str) -> pd.Series:
    if model == "Q":
        return pd.Series("1545.T", index=S.index)
    if model in ("F", "S1", "S4"):
        return pd.Series(np.where(S["rs_ndx"].to_numpy(bool), "1545.T", "1655.T"), index=S.index)
    return pd.Series("1655.T", index=S.index)


def hedged_of(idx: pd.Series) -> pd.Series:
    return idx.map(HEDGED)


def model_weights(model: str, S: pd.DataFrame) -> pd.DataFrame:
    W = _empty(S)
    idx = index_series(S, model)
    bull = ~S["guard"] if model in ("G", "S1", "S4") else ~S["bear"]
    dip, yen, gu, summer = S["dip"], S["yen"], S["gold_up"] & S["gold_ok"], S["summer"]
    if model in ("A", "Q", "F", "G"):
        _put(W, bull, idx, 1.0)
    elif model == "B":
        _put(W, bull & S["gold_ok"], idx, 1 - GOLD_W)
        W.loc[bull & S["gold_ok"], "1540.T"] = GOLD_W
        _put(W, bull & ~S["gold_ok"], idx, 1.0)
    elif model == "C":
        _put(W, bull & yen, hedged_of(idx), 1.0)
        _put(W, bull & ~yen, idx, 1.0)
    elif model == "D":
        _put(W, bull & summer, idx, SEASON_W)
        _put(W, bull & ~summer, idx, 1.0)
    elif model == "E":
        _put(W, bull & dip, idx, 1 - DIP_W)
        _put(W, bull & ~dip, idx, 1.0)
        W.loc[dip, "1321.T"] = DIP_W
    elif model == "S1":
        eq = pd.Series(np.where(yen.to_numpy(bool), hedged_of(idx).to_numpy(), idx.to_numpy()), index=S.index)
        b1 = dip
        b2 = ~dip & ~bull
        b3 = ~dip & bull & yen
        b4 = ~dip & bull & ~yen & gu
        b5 = ~dip & bull & ~yen & ~gu & summer
        b6 = ~dip & bull & ~yen & ~gu & ~summer
        W.loc[b1, "1321.T"] = DIP_W
        _put(W, b1 & bull, idx, 1 - DIP_W)
        _put(W, b3, eq, 1.0)
        _put(W, b4, idx, 1 - GOLD_W)
        W.loc[b4, "1540.T"] = GOLD_W
        _put(W, b5, idx, SEASON_W)
        _put(W, b6, idx, 1.0)
        W.attrs["branches"] = {"dip": int(b1.sum()), "cash": int(b2.sum()), "hedge": int(b3.sum()), "gold": int(b4.sum()),
                               "summer": int(b5.sum()), "index": int(b6.sum())}
    elif model == "S4":
        eq = pd.Series(np.where(yen.to_numpy(bool), hedged_of(idx).to_numpy(), idx.to_numpy()), index=S.index)
        base = pd.Series(np.where(summer.to_numpy(bool), SEASON_W, 1.0), index=S.index)
        gold = pd.Series(np.where(gu.to_numpy(bool), GOLD_W, 0.0), index=S.index) * base
        stock = (base - gold) * pd.Series(np.where(dip.to_numpy(bool), 1 - DIP_W, 1.0), index=S.index)
        _put(W, bull, eq, stock)
        W.loc[bull, "1540.T"] = gold[bull]
        W.loc[dip, "1321.T"] = DIP_W
    else:
        raise ValueError(model)
    return W


def blend_weights(WM: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return sum(WM[m] for m in MODELS) / len(MODELS)


def weights_from_choice(choice: pd.Series, WM: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """每天选的模型（字符串 Series）→ 配比。"""
    W = _empty(next(iter(WM.values())))
    for m in MODELS:
        mask = (choice == m).to_numpy(bool)
        if mask.any():
            W.loc[mask, :] = WM[m].loc[mask, :].to_numpy()
    return W


# ───────────────────────── 只有核心的净值 ─────────────────────────
def core_sim(W: pd.DataFrame, R: pd.DataFrame, cost_pct: float = SWITCH_COST) -> pd.Series:
    """前一天收盘决定的配比 × 当天收益；不可用的资产（收益 NaN）配比当 0（现金）；换手 × cost_pct%。"""
    Rv = R.reindex(index=W.index, columns=W.columns)
    ok = Rv.notna().to_numpy()
    Wv = np.where(ok, W.to_numpy(float), 0.0)
    Rv = np.nan_to_num(Rv.to_numpy(float))
    prev = np.vstack([np.zeros((1, Wv.shape[1])), Wv[:-1]])                 # 前一天定的配比
    prev2 = np.vstack([np.zeros((1, Wv.shape[1])), prev[:-1]])
    ret = (prev * Rv).sum(axis=1)
    cost = np.abs(prev - prev2).sum(axis=1) * cost_pct / 100
    return pd.Series(np.cumprod(1 + ret - cost), index=W.index)


def seg(eq: pd.Series, a: str, b: str | None) -> dict:
    e = eq[(eq.index >= pd.Timestamp(a)) & ((eq.index < pd.Timestamp(b)) if b else True)].dropna()
    if len(e) < 20:
        return {"cagr": None, "dd": None, "calmar": None}
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1
    dd = float((e / e.cummax() - 1).min())
    return {"cagr": round(cagr * 100, 2), "dd": round(dd * 100, 2), "calmar": round(cagr / abs(dd), 3) if dd < 0 else None}


def trailing_choice(EQ: dict[str, pd.Series], days: pd.DatetimeIndex, months: int = SEL_MONTHS, min_months: int = SEL_MIN) -> pd.Series:
    """S2：每个月末看过去 months 个月各模型只有核心的 Calmar，最高的下个月用；不足 min_months 个月 → A。"""
    days = pd.DatetimeIndex(days)
    me = month_ends(days)
    pick = {}
    for k, d in enumerate(me):
        if k < min_months:
            pick[d] = "A"
            continue
        a = me[max(0, k - months)]
        best, bv = "A", -np.inf
        for m in MODELS:
            e = EQ[m][(EQ[m].index > a) & (EQ[m].index <= d)]
            s = seg(e, str(e.index[0].date()), None) if len(e) >= 20 else {"calmar": None}
            v = s["calmar"] if s["calmar"] is not None else (np.inf if (s.get("cagr") or 0) > 0 else -np.inf)
            if v > bv:
                best, bv = m, v
        pick[d] = best
    return choice_days(pd.Series(pick), days)


def choice_days(pick_at_me: pd.Series, days: pd.DatetimeIndex, default: str = "A") -> pd.Series:
    """月末定的模型 → 下个月每天。"""
    days = pd.DatetimeIndex(days)
    out = pd.Series(default, index=days, dtype=object)
    me = pick_at_me.sort_index()
    for i, (d, v) in enumerate(me.items()):
        k = int(days.searchsorted(pd.Timestamp(d), side="right"))
        k2 = int(days.searchsorted(me.index[i + 1], side="right")) if i + 1 < len(me) else len(days)
        out.iloc[k:k2] = v
    return out


def oracle_choice(EQ: dict[str, pd.Series], days: pd.DatetimeIndex) -> pd.Series:
    """上限（作弊）：每月末事后选下个月收益最高的模型。"""
    days = pd.DatetimeIndex(days)
    me = month_ends(days)
    pick = {}
    for k in range(len(me) - 1):
        a, b = me[k], me[k + 1]
        best, bv = "A", -np.inf
        for m in MODELS:
            e = EQ[m]
            v = float(e.asof(b) / e.asof(a) - 1) if e.asof(a) and np.isfinite(e.asof(a)) else -np.inf
            if v > bv:
                best, bv = m, v
        pick[a] = best
    return choice_days(pd.Series(pick), days)


def random_choice(days: pd.DatetimeIndex, seed: int) -> pd.Series:
    """安慰剂 P1：每月随机选一个模型。"""
    rng = np.random.default_rng(seed)
    me = month_ends(pd.DatetimeIndex(days))
    return choice_days(pd.Series(rng.choice(list(MODELS), size=len(me)), index=me), days)


def shifted_states(S: pd.DataFrame, seed: int, cols=("yen", "gold_up", "rs_ndx", "summer", "dip", "guard")) -> pd.DataFrame:
    """安慰剂 P2：条件状态整体循环平移一个随机天数（≥ SHIFT_MIN），bear / gold_ok 不动。"""
    rng = np.random.default_rng(seed)
    n = len(S)
    k = int(rng.integers(SHIFT_MIN, n - SHIFT_MIN))
    S2 = S.copy()
    for c in cols:
        S2[c] = np.roll(S[c].to_numpy(bool), k)
    S2["guard"] = S2["guard"] & S["bear"]                                    # 守卫只能把熊改成牛，平移后不能凭空造熊
    return S2


# ───────────────────────── 账户：配比进引擎 ─────────────────────────
def encode(W: pd.DataFrame) -> tuple[dict, dict, dict]:
    """通用编码：split 模式、每个资产权重 1、自己的牛熊键（配比 0 = 熊）、比例键 = 配比 × 资产数（split 的份额是 1/资产数）。"""
    n = len(W.columns)
    cfg_over = {"core": {a: 1.0 for a in W.columns}, "core_index": {a: f"CS:{a}" for a in W.columns}, "core_mode": "split"}
    bear = {f"CS:{a}": (W[a] <= 1e-12) for a in W.columns}
    expo = {f"CS:{a}": W[a].astype(float) * n for a in W.columns}
    return cfg_over, bear, expo


def engine_cls():
    import candle_portfolio as CP

    class SwitchEngine(CP.MixEngine):
        """与 MixEngine 相同；EXPO 给另加的牛熊键按日的比例（MixEngine 对另加的键一律给 1）。"""
        EXPO: dict[str, pd.Series] = {}

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            for key, s in SwitchEngine.EXPO.items():
                if key in self.bear:
                    self.core_expo[key] = s.reindex(self.gidx.union(s.index)).ffill().reindex(self.gidx).fillna(0.0).to_numpy(float)
    return SwitchEngine


# ───────────────────────── 判定 ─────────────────────────
def _c(x):
    return -np.inf if x is None else float(x)


def verdict(c: str, RP: dict, ACCT: dict, pl_p95: float | None, pl_j95: float | None) -> tuple[str, list[str]]:
    f = []
    q, r = RP[BASE], RP[c]
    if _c(r["P"]["calmar"]) < _c(q["P"]["calmar"]) + CAL_UP_P:
        f.append(f"P 1987〜2005 Calmar {r['P']['calmar']} < 现行 {q['P']['calmar']} + {CAL_UP_P}")
    if r["P"]["dd"] is None or q["P"]["dd"] is None or r["P"]["dd"] < q["P"]["dd"] - DD_TOL:
        f.append(f"P 最大回撤 {r['P']['dd']}% 比现行 {q['P']['dd']}% 深 {DD_TOL} pp 以上")
    for k, lab in (("P1", "1987〜1996"), ("P2", "1997〜2005")):
        if _c(r[k]["calmar"]) < _c(q[k]["calmar"]):
            f.append(f"{lab} Calmar {r[k]['calmar']} < 现行 {q[k]['calmar']}")
    for era in ("E", "J"):
        a, b = ACCT[era].get(c), ACCT[era].get(BASE)
        if not a or not b:
            f.append(f"{era} 没有账户结果")
            continue
        if _c(a["calmar"]) < _c(b["calmar"]) + CAL_UP:
            f.append(f"{era} Calmar {a['calmar']} < 现行 {b['calmar']} + {CAL_UP}")
        if a["dd"] is None or b["dd"] is None or a["dd"] < b["dd"] - DD_TOL:
            f.append(f"{era} 回撤 {a['dd']}% 比现行 {b['dd']}% 深 {DD_TOL} pp 以上")
    a, b = ACCT["Z"].get(c), ACCT["Z"].get(BASE)
    if a and b and _c(a["calmar"]) < _c(b["calmar"]) - Z_TOL:
        f.append(f"Z Calmar {a['calmar']} < 现行 {b['calmar']} − {Z_TOL}")
    if pl_p95 is not None and _c(r["P"]["calmar"]) <= pl_p95:
        f.append(f"P Calmar {r['P']['calmar']} ≤ 安慰剂 95 分位 {pl_p95}")
    if pl_j95 is not None and ACCT["J"].get(c) and _c(ACCT["J"][c]["calmar"]) <= pl_j95:
        f.append(f"J Calmar {ACCT['J'][c]['calmar']} ≤ 安慰剂 95 分位 {pl_j95}")
    return ("提议" if not f else "不通过"), f


def switches_per_year(W: pd.DataFrame, a: str, b: str | None) -> float | None:
    w = W[(W.index >= pd.Timestamp(a)) & ((W.index < pd.Timestamp(b)) if b else True)]
    if len(w) < 2:
        return None
    ch = (w.diff().abs().sum(axis=1) > 1e-9).sum()
    yrs = (w.index[-1] - w.index[0]).days / 365.25
    return round(float(ch / yrs), 1) if yrs > 0 else None


def yearly(eq: pd.Series, y0: int, y1: int) -> dict[str, float]:
    e = eq.dropna()
    ye = e.groupby(e.index.year).last()
    out = {}
    for y in range(y0, y1 + 1):
        if y in ye.index and (y - 1) in ye.index:
            out[str(y)] = round(float(ye[y] / ye[y - 1] - 1) * 100, 1)
    return out


# ───────────────────────── 数据 ─────────────────────────
def load_data() -> dict:
    import equity_idle_study as EI
    import fxhedge_study as FX
    import stack_study as SS
    from bullbear_study import SYM, load
    from qbreak import factors
    inp = EI.load_inputs()
    dex = factors.fred("DEXJPUS", max_age_h=1e9).dropna()
    fx_new = inp["fx"].dropna()
    fx = pd.concat([dex[dex.index < fx_new.index[0]], fx_new]).sort_index()
    fx = fx[~fx.index.duplicated()]
    n225 = inp["n225"]
    days = pd.DatetimeIndex(n225.index[n225.index >= "1985-01-01"])
    spx_tr, ndx_tr = EI.spx_tr(inp), EI.ndx_tr(inp)
    us_r, jp_r = factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9)
    gld, gc = load("GLD", "2000-01-01")["Close"], load("GC=F", "2000-01-01")["Close"]
    first = gld.index[0]
    kk = float(gld.iloc[0]) / float(gc[gc.index <= first].iloc[-1])
    gold_usd = pd.concat([gc[gc.index < first] * kk, gld]).dropna()
    closes = {
        "1655.T": EI.on_jp(EI.grow(spx_tr, -EI.FEE["1655.T"]), fx, days),
        "1545.T": EI.on_jp(EI.grow(ndx_tr, -EI.FEE["1545.T"]), fx, days),
        "2563.T": EI.on_jp(EI.grow(FX.hedged_index(spx_tr, us_r, jp_r), -FEE_H["2563.T"]), None, days),
        "2845.T": EI.on_jp(EI.grow(FX.hedged_index(ndx_tr, us_r, jp_r), -FEE_H["2845.T"]), None, days),
        "1540.T": EI.on_jp(gold_usd, fx, days) / GOLD_DIV,
    }
    j = EI.jp_product(n225, 1.0, None, None, EI.FEE["1321.T"])
    closes["1321.T"] = j["Close"].reindex(days)
    frames_1321 = j
    events = SS.dd_events()
    S = states_frame(days, load(*SYM["US"])["Close"], ndx_tr, spx_tr, fx, closes["1540.T"], events)
    C = pd.DataFrame(closes).reindex(days)
    R = C.pct_change()
    R[C.shift(1).isna() | C.isna()] = np.nan                                 # 不可用 → NaN（core_sim 当现金）
    return {"days": days, "closes": C, "R": R, "S": S, "events": events, "frames_1321": frames_1321, "fx": fx}


def account_frames(d: dict) -> dict[str, pd.DataFrame]:
    """引擎用的 K 线（价格水平按 equity_idle 的 REF_PX；对冲版 / 黄金按各自的基准）；从 ACCT_FROM 起。"""
    import equity_idle_study as EI
    C = d["closes"]
    out = {}
    for t in ("1655.T", "1545.T"):
        out[t] = EI.frame_close(EI.scale(C[t], t))
    for t, ref in (("2563.T", "1655.T"), ("2845.T", "1545.T")):
        s = C[t].dropna()
        k = EI.REF_PX[ref] / float(s[s.index <= pd.Timestamp(EI.REF_DATE)].iloc[-1])
        out[t] = EI.frame_close(s * k)
    out["1540.T"] = EI.frame_close(C["1540.T"])
    out["1321.T"] = EI.frame_ohlc(EI.scale(d["frames_1321"], "1321.T"))
    return {t: f[f.index >= pd.Timestamp(ACCT_FROM)] for t, f in out.items()}


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import jq_study as JS
    import leap_confirm as LF
    import candle_portfolio as CP
    from qbreak import exit_rules as EXR
    from qbreak import idle_cash as IC
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/core_switch_study.py", "scripts/candle_portfolio.py",
                                 "qbreak/unified.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 核心层「按状态选模型」（登记检验，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/core_switch_study.py 开头（先提交后只跑一次）。「现行」= Q（模拟盘现在：纳指 1545 + 美股牛熊分界）。")
    d = load_data()
    days, S, R = d["days"], d["S"], d["R"]
    WM = {m: model_weights(m, S) for m in MODELS}
    EQ = {m: core_sim(WM[m], R) for m in MODELS}
    WC = {"S1": model_weights("S1", S), "S3": blend_weights(WM), "S4": model_weights("S4", S)}
    WC["S2"] = weights_from_choice(trailing_choice(EQ, days), WM)
    W_or = weights_from_choice(oracle_choice(EQ, days), WM)
    seeds = 2 if SMOKE else PLACEBO_SEEDS
    W_p1 = {s: weights_from_choice(random_choice(days, s), WM) for s in range(seeds)}
    W_p2 = {s: model_weights("S4", shifted_states(S, s)) for s in range(seeds)}
    for c in CANDS:
        EQ[c] = core_sim(WC[c], R)
    EQ["上限"] = core_sim(W_or, R)
    PL = {"P1": [core_sim(w, R) for w in W_p1.values()], "P2": [core_sim(w, R) for w in W_p2.values()]}
    RP = {k: {w: seg(EQ[k], a, b) for w, (a, b) in {**P_WIN, **REF_WIN}.items()} for k in EQ}
    plc = {fam: {w: [seg(e, a, b)["calmar"] for e in PL[fam]] for w, (a, b) in {**P_WIN, **REF_WIN}.items()} for fam in PL}
    occ = {k: round(float(S[k].mean() * 100), 1) for k in ("bear", "guard", "yen", "gold_up", "gold_ok", "rs_ndx", "summer", "dip")}
    say(f"- 状态天数比例（1985〜）：" + "、".join(f"{k} {v}%" for k, v in occ.items()) + f"；深跌事件 {len(d['events'])} 个")
    say(f"- S1 各分支天数：{WC['S1'].attrs.get('branches')}；只有核心算完 {time.time() - t0:.0f} s")

    # ── 账户（S0C2 + W2 + X6；Z / E / J）──
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    fr_core = account_frames(d)
    Eng = engine_cls()
    ACCT: dict[str, dict] = {}
    PLA: dict[str, dict[str, list]] = {}
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    q_spec = {"cfg_over": {"core": dict(IC.MODES["Q1"]["core"]), "core_index": dict(IC.MODES["Q1"]["core_index"]),
                           "core_mode": IC.MODES["Q1"]["core_mode"]}, "extra_core": {"1545.T": fr_core["1545.T"]}}
    a_spec = {"cfg_over": {"core": {"1655.T": 1.0}, "core_index": {"1655.T": "US"}, "core_mode": "split"},
              "extra_core": {"1655.T": fr_core["1655.T"]}}
    for era in ERAS:
        t1 = time.time()
        ctx = LF.context(era, names=smoke_names) if (SMOKE and era != "J") else LF.context(era)
        if SMOKE and era == "J":
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in set(smoke_names)]
        fa = LF.frames(ctx, p0)
        keep = LF.w2_keep(ctx, fa)
        fr = LF.with_mask(fa, keep)
        run_fn = LF.runner(ctx, fr)
        a, b = ctx["windows"][era]

        def run_w(W: pd.DataFrame | None = None, spec: dict | None = None) -> dict:
            if spec is not None:
                r = LF.run(ctx, run_fn, fr, px, **spec)
            else:
                cfg_over, bear, expo = encode(W)
                old = CP.MixEngine
                CP.MixEngine, Eng.EXPO = Eng, expo
                try:
                    r = LF.run(ctx, run_fn, fr, px, cfg_over=cfg_over, extra_bear=bear, extra_core=fr_core)
                finally:
                    CP.MixEngine, Eng.EXPO = old, {}
            eng = JS.RealLotEngine.LAST[-1]
            tr = pd.DataFrame(eng.st.trades)
            n = int(len(tr[(tr["reason"] != "end") & (~tr["ticker"].isin(ASSETS))])) if len(tr) else 0
            return {**{k: r[era][k] for k in ("cagr", "dd", "calmar")}, "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")],
                    "n": n}

        ACCT[era] = {BASE: run_w(spec=q_spec), "A": run_w(spec=a_spec)}
        hard = run_w(WM["Q"])
        same = (hard["calmar"] is not None and ACCT[era][BASE]["calmar"] is not None
                and abs(hard["calmar"] - ACCT[era][BASE]["calmar"]) <= HARD_TOL and hard["n"] == ACCT[era][BASE]["n"])
        say(f"- {era}（{a}〜{b or '今'}）：Q 直接设定 Calmar {ACCT[era][BASE]['calmar']} / {ACCT[era][BASE]['n']} 笔 vs 通用编码 "
            f"{hard['calmar']} / {hard['n']} 笔 → {'一致' if same else '**不一致**'}")
        if not same:
            raise RuntimeError(f"{era}：Q 的通用编码与直接设定不一致 → 停止，不算候选")
        for m in MODELS:
            if m not in ("A", "Q"):
                ACCT[era][m] = run_w(WM[m])
        for c in CANDS:
            ACCT[era][c] = run_w(WC[c])
        ACCT[era]["上限"] = run_w(W_or)
        PLA[era] = {"P1": [run_w(w)["calmar"] for w in W_p1.values()], "P2": [run_w(w)["calmar"] for w in W_p2.values()]}
        say(f"- {era} 账户算完：{time.time() - t1:.0f} s")

    # ── 判定 ──
    def q95(v):
        x = [t for t in v if t is not None]
        return round(float(np.quantile(x, 0.95)), 3) if x else None

    def med(v):
        x = [t for t in v if t is not None]
        return round(float(np.median(x)), 3) if x else None

    VER = {}
    for c in CANDS:
        fam = PLACEBO_FAMILY[c]
        VER[c] = verdict(c, RP, ACCT, q95(plc[fam]["P"]), q95(PLA["J"][fam]))
    passed = [c for c in CANDS if VER[c][0] == "提议"]
    best = max(passed, key=lambda c: _c(RP[c]["P"]["calmar"])) if passed else None
    if SMOKE:
        say("\n（QBREAK_SMOKE=1：只做接线检查，不写结果）")
        return 0

    # ── 报告 ──
    fmt = lambda s: (f"{s['cagr']:+.2f}% / {s['dd']:.2f}% / {s['calmar']:.3f}" if s and s.get("calmar") is not None else "—")   # noqa: E731
    say("\n## 一、只有核心（日元计；各格 = 年化 / 最大回撤 / Calmar）")
    say("| 做法 | P 1987〜2005 | 1987〜1996 | 1997〜2005 | 2006-10〜2016-09 | 2017〜 |")
    say("|---|---|---|---|---|---|")
    for k in list(MODELS) + list(CANDS) + ["上限"]:
        lab = MODELS.get(k) or CANDS.get(k) or "上限（作弊：每月事后选）"
        say(f"| {k} {lab} | " + " | ".join(fmt(RP[k][w]) for w in ("P", "P1", "P2", "E 只有核心", "J 只有核心")) + " |")
    for fam, lab in (("P1", "安慰剂 P1 每月随机选模型"), ("P2", "安慰剂 P2 条件平移的全叠加")):
        say(f"| {lab}（中位 / 95 分位） | " + " | ".join(f"{med(plc[fam][w])} / {q95(plc[fam][w])}" for w in ("P", "P1", "P2", "E 只有核心", "J 只有核心")) + " |")
    say("\n## 二、整个账户（S0C2 + W2 + X6，立花费用，真实一手；年化 / 最大回撤 / Calmar · 前半 / 后半 Calmar · 个股笔数）")
    say("| 做法 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 |")
    say("|---|---|---|---|")
    for k in list(MODELS) + list(CANDS) + ["上限"]:
        lab = MODELS.get(k) or CANDS.get(k) or "上限（作弊）"
        say(f"| {k} {lab} | " + " | ".join(
            f"{fmt(ACCT[e][k])} · {ACCT[e][k]['halves'][0]} / {ACCT[e][k]['halves'][1]} · {ACCT[e][k]['n']} 笔" for e in ERAS) + " |")
    for fam, lab in (("P1", "安慰剂 P1"), ("P2", "安慰剂 P2")):
        say(f"| {lab}（Calmar 中位 / 95 分位） | " + " | ".join(f"{med(PLA[e][fam])} / {q95(PLA[e][fam])}" for e in ERAS) + " |")
    say("\n## 三、判定（事先写定：P Calmar ≥ Q + 0.05、回撤不深 2 pp、两个半段 ≥ Q；E / J ≥ Q + 0.02 且回撤不深 2 pp；Z ≥ Q − 0.02；P 与 J 都 > 安慰剂 95 分位）")
    for c in CANDS:
        lab, f = VER[c]
        say(f"- **{c} {CANDS[c]}**：{lab}" + ("" if not f else "（" + "；".join(f) + "）"))
    say(f"\n**结论：{'提议 ' + best + '（' + CANDS[best] + '）→ 要用户确认才改模拟盘' if best else '没有候选「通过」→ 模拟盘不变'}**")
    say("\n## 四、另报（只描述）")
    say("- 状态天数比例（1985〜）：" + "、".join(f"{k} {v}%" for k, v in occ.items()))
    say(f"- S1 各分支的天数：{WC['S1'].attrs.get('branches')}")
    say("- 每年切换次数（只有核心，配比有变的天数 ÷ 年数）：" + "；".join(
        f"{k} P {switches_per_year(WC.get(k, WM.get(k)), *P_WIN['P'])} / E {switches_per_year(WC.get(k, WM.get(k)), *REF_WIN['E 只有核心'])} / "
        f"J {switches_per_year(WC.get(k, WM.get(k)), *REF_WIN['J 只有核心'])}" for k in list(CANDS) + ["Q", "B", "C"]))
    ys = {k: yearly(EQ[k], 1987, int(days[-1].year)) for k in ["Q", "A"] + list(CANDS)}
    yrs_all = sorted(set().union(*[set(v) for v in ys.values()]))
    say("- 每年收益（只有核心，%）：")
    say("| 年 | " + " | ".join(["Q", "A"] + list(CANDS)) + " |")
    say("|---|" + "---|" * (2 + len(CANDS)))
    for y in yrs_all:
        say(f"| {y} | " + " | ".join(f"{ys[k].get(y, '—'):+}" if isinstance(ys[k].get(y), float) else "—" for k in ["Q", "A"] + list(CANDS)) + " |")
    say(f"- 用时 {time.time() - t0:.0f} s")
    say("\n非投资建议。")
    out = {"code": code, "dirty": dirty, "core_only": RP, "placebo_core": plc, "account": ACCT, "placebo_account": PLA,
           "verdict": {c: {"label": VER[c][0], "fails": VER[c][1]} for c in CANDS}, "passed": passed, "proposal": best,
           "occupancy": occ, "branches": WC["S1"].attrs.get("branches"), "yearly": ys, "events": [str(e.date()) for e in d["events"]],
           "elapsed_s": round(time.time() - t0)}
    fp = paths.out_dir() / "core_switch_study"
    fp.with_suffix(".md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    fp.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
