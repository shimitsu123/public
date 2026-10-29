"""learned_exit_study.py — 卖法：用持仓中每天收盘已知的状态，学「照现行卖法再拿下去，到卖出时比明天开盘卖多赚还是少赚」，
预计少赚就第二天开盘卖（ID = LXE；登记版：规则、代码与测试一起提交，之后不改、只运行一次）。

来由：用户 2026-10-23「做卖法的研究」。诊断（b4_weakness_diag，2026-10-23，R3 成立）：B4 的个股 70〜84% 经吊灯止损卖出、
平均从最高浮盈吐回 4.7〜5.6 pp，E 年代吊灯离场胜率 38%、每笔 −0.24%。因为是看了诊断才定的 → 事后（posthoc = True，S7 适用）。
以前做过的卖法（都没过、不重复）：X6 / R4 选择、一直放宽 WXA（4×ATR / 90 天）、日経转弱时收紧 NKT、去掉止盈 TPX、决算前卖 EBX、跑输核心就卖 OCX、
外部事件清仓 FXX、均线 / 死叉类卖点（15 种）、按信号日状态给整笔定参数（ULC / ERK / VOK / SCY / SZK / VRK / FRG / BTK / SMK / ICY / RSD / DVY、
HWT / X2T / JRT、SZS / TAG / N52）、按局势每月切换卖法、ER60 切换、加仓 / 分批止盈 / 保本止损（2026-09-30）。
**没做过的**：持有中每天按「这一笔自己的状态 + 大盘」逐日判断，而且判断标准是从过去的持仓里学出来的（不是手写的一条线）。
已知的不利证据（照实写）：「能提胜率的都把赢家卖早」「最好的卖法跟着年代变」；一直收紧（k 2）每笔明显为负；加仓研究里现行离场把赢家切在 +12〜13%、之后只剩 +2〜4%。
所以目标用「剩下的收益（按金额）」而不是「会不会亏」：只有预计剩下的收益为负才卖，大赢家只要预计还能涨就不卖。

一 池子与单笔（同 nkt_study 的四个池子与单笔做法）：N = Z / E / J 各年代 B4 会买的日経225 信号（C 留一年代保留、TBF 没挡）、W（E 年代扩展池）、
   Jx（J 年代扩展池）、Zx（Z 年代扩展池）；每个信号 = nkt_study._prepare（成交日 kk、成交价 px = 开盘 ×（1 + 滑点））+ 现行 X6 单笔
   （吊灯 3×ATR14 借用死叉列、最长 60 天、止损 −7%、跟踪 12%、止盈 +25%、放量阴线；130 根内没卖掉 → 剔除）；净收益 nb = ret_pct − 往返费用 rt。
二 特征（持有中第 t 天收盘时已知；FEATS 15 个；只用 ≤ t 的行，tests 核对不偷看）：
   这一笔：gain 浮盈 %、mfe 持有以来最高收盘的浮盈 %、dd_atr（max(px, 持有以来最高价) − 收盘）÷ ATR14（吊灯在 > 3 时卖）、hold 持有第几天、
   since_peak 离持有以来最高价几天、atr_pct ATR ÷ 收盘 %、r5 五日涨跌 %；
   指标表现成的列：ext_ma20（离 20 日线 %）、rsi、vol_ratio（量 ÷ 20 日均量）、macd_atr（MACD 柱 ÷ ATR）、ushadow（上影线比）
   （指标表的 rs_pct 在这些行情里全是空值 → 不用；登记前的机制核对发现）；
   大盘：nk_r20 日経 20 日涨跌 %、nk_gap50 日経离 50 日线 %（var/cache 的 ^N225，as-of 当天收盘）、us_bear 美股牛熊分界（前一个日历日及以前的最后一个值，1 = 熊）。
三 目标（每一行 = 持有第 t 天收盘，t 从成交日到 X6 卖出日的前两天；卖出日前一天 X6 自己已经决定卖，不要）：
   rem_t = X6 的卖出价 ÷（第 t+1 天开盘 ×（1 − 滑点））− 1（%）= 「照现行再拿下去」比「明天开盘卖」多赚的；学的时候截到 ±30%（CLIP）。
四 学法：qbreak.ml.HistGBM（loss = l2，200 棵、学习率 0.05、深 3、叶 ≥ 200、32 桶、行抽样 0.5、列抽样 0.8、l2 1、种子 0）。
   逐年前推（主信号）：第 Y 年的行用「X6 卖出日 < Y-01-01 的单笔」学的模型（单笔按（票, 成交日）去重，四个池子合起来）；学的单笔 < MIN_TRAIN = 150 → 那一年不判断（= B4）。
   留一年代（S6 的另一个镜头）：年代 e 的单笔（成交日在 e 的窗口里）用其余全部单笔学的模型（含未来，只作镜头）。
五 候选（事先写定两个门槛，不从数据挑）：预计 rem < 门槛的那天收盘 → 第二天开盘卖（只多一个卖出理由、只会更早卖；其余照 B4）：
   LXR0 门槛 0 %（预计再拿下去少赚就卖）；LXR1 门槛 −1 %（预计少赚 1% 以上才卖）。
六 账户：B4（C10.load + TS.tbf_gates + KS.prereq，B4 = 登记值 B4_PREP 才运行）；每个年代用 N 池子里那个年代的单笔的预测，
   {(票, 成交日): {要卖的收盘日}} 经 make_runner.run(exit_tick=…) 进引擎（这次运行期间把 MixEngine._tick_exit 换成按（票, 成交日）查的版本，
   理由记 learned_exit；运行完换回；离场理由从刚跑完的引擎的成交表数：窗口内买入、已平仓的日本个股）。接线核对：空字典 = B4（八个键完全相同）；正向对照：每一笔都在成交日收盘标记 → 每个年代 learned_exit ≥ 成交笔数的一半；
   单笔层核对：改了卖点的单笔，引擎净收益 = 公式（第一个标记日 t* 的明天开盘卖）的 ≥ 99%（|差| < 0.001 pp，引擎价格取整），不过就停。
七 判定（research_loop2.stage1，基准 B4）：S1〜S4 账户（逐年前推）；S5 W / Jx 池子每笔胜率差与平均差都 ≥ 0（逐年前推）；
   S6 留一年代与逐年前推两个账户各自 S1〜S3；S7（事后）= 诊断没看过的 Zx 池子（Z 年代扩展池）每笔平均差 > 0。
   第一关通过 → 第二关（随机标记日的安慰剂）另行登记；第一关不过 → 结束。
八 描述（不参与判定）：每个年代（行的日期）rem 的平均、< 0 的比例；预测与实际 rem 的秩相关 ρ 与 AUC（rem < 0）；每个特征与 rem 的秩相关（探索变量）；
   完美卖点上限（每笔在 [成交日, 卖出日前两天] 里挑最好的开盘卖，平均多赚几 pp）；各池子改了几笔、每次改的平均差 g、持有天数；账户的 learned_exit 笔数。
九 读法（事先写定）：A1 逐年前推的 ρ ≥ 0.05 的年代 ≥ 2 / 3 →「持仓状态对剩下的收益有信息」；否则「没有可用的信息」。
十 局限：日経225 用今天的成员；池子之间有重叠；单笔与账户的成交价略有差（账户还受名额 / 现金影响）；Z 年代前几年没有可学的数据（= B4）。
只是研究：不改模拟盘、执行器、例行任务、策略参数、仓位、股票池、宏观阈值、牛熊分界参数。
用法：python scripts/learned_exit_study.py --run（只运行一次：输出已经存在就停）。输出：var/out/learned_exit_study.md / .json（只有汇总，没有个股名单）。非投资建议。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = "learned_exit_study"
ID = "LXE"
ERAS = ("Z", "E", "J")
POOLS = ("N", "W", "Jx", "Zx")
FEATS = ["gain", "mfe", "dd_atr", "hold", "since_peak", "atr_pct", "r5", "ext_ma20", "rsi", "vol_ratio", "macd_atr", "ushadow",
         "nk_r20", "nk_gap50", "us_bear"]
K_BASE = 3.0
MAX_HOLD = 60
CLIP = 30.0
MIN_TRAIN = 150
GBM = {"loss": "l2", "n_trees": 200, "lr": 0.05, "depth": 3, "min_leaf": 200, "n_bins": 32, "subsample": 0.5, "colsample": 0.8, "l2": 1.0, "seed": 0}
CANDS = {"LXR0": 0.0, "LXR1": -1.0}
YEARS = range(2001, 2027)
A1_RHO = 0.05
REASON = "learned_exit"
POSTHOC = True
STOCK_SKIP = ("1545.T", "1482.T", "1655.T", "2845.T")
CHECK_TOL = 1e-3                                                            # pp；引擎的成交价取整（登记前机制核对：最大差 0.0005 pp）
CHECK_MIN = 0.99


# ───────────────────────── 二 特征 / 三 目标（纯函数） ─────────────────────────
def since_peak(h: np.ndarray) -> np.ndarray:
    """每一天：离到那天为止的最高价（同价取后一天）几天。"""
    out = np.zeros(len(h))
    best, at = -np.inf, 0
    for i, v in enumerate(np.asarray(h, float)):
        if np.isfinite(v) and v >= best:
            best, at = v, i
        out[i] = i - at
    return out


def nikkei_feats(close: pd.Series) -> pd.DataFrame:
    """日経：20 日涨跌 %、离 50 日线 %（只用当天及以前的收盘）。"""
    c = pd.Series(close, dtype=float).dropna().sort_index()
    return pd.DataFrame({"nk_r20": (c / c.shift(20) - 1) * 100, "nk_gap50": (c / c.rolling(50).mean() - 1) * 100})


def features(f: pd.DataFrame, kk: int, px: float, nkf: pd.DataFrame | None = None, usb: pd.Series | None = None) -> pd.DataFrame:
    """f 的第 kk 行（成交日）到最后一行：每一行收盘时已知的特征（FEATS 的顺序）。"""
    from candle_portfolio import asof_take
    idx = f.index[kk:]
    c = f["Close"].to_numpy(float)
    h = f["High"].to_numpy(float)[kk:]
    a = f["atr"].to_numpy(float)[kk:]
    cc = c[kk:]
    peak = np.maximum(np.maximum.accumulate(np.where(np.isfinite(h), h, -np.inf)), px)
    with np.errstate(divide="ignore", invalid="ignore"):
        prev5 = np.r_[np.full(5, np.nan), c[:-5]][kk:] if len(c) > 5 else np.full(len(cc), np.nan)
        out = {"gain": (cc / px - 1) * 100, "mfe": (np.fmax.accumulate(cc) / px - 1) * 100, "dd_atr": (peak - cc) / a,
               "hold": np.arange(1, len(cc) + 1, dtype=float), "since_peak": since_peak(h), "atr_pct": a / cc * 100,
               "r5": (cc / prev5 - 1) * 100}
        col = lambda k: f[k].to_numpy(float)[kk:] if k in f.columns else np.full(len(cc), np.nan)   # noqa: E731
        out.update({"ext_ma20": col("ext_ma20_pct"), "rsi": col("rsi"), "vol_ratio": col("vol_ratio"), "macd_atr": col("macd_hist") / a,
                    "ushadow": col("upper_shadow_ratio")})
    for k in ("nk_r20", "nk_gap50"):
        out[k] = asof_take(nkf[k], idx) if nkf is not None else np.full(len(cc), np.nan)
    out["us_bear"] = (asof_take(usb.astype(float), idx - pd.Timedelta(days=1)) if usb is not None else np.full(len(cc), np.nan))
    X = pd.DataFrame(out, index=idx)[FEATS]
    return X.replace([np.inf, -np.inf], np.nan)


def remaining(o_next, exit_px: float, slip: float) -> np.ndarray:
    """rem = X6 卖出价 ÷（明天开盘 ×（1 − 滑点））− 1（%）。"""
    o = np.asarray(o_next, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (float(exit_px) / (o * (1 - slip)) - 1) * 100


# ───────────────────────── 一 单笔 ─────────────────────────
def trajectory(tk: str, df: pd.DataFrame | None, d, p0, bt, rt: float, slip: float, nkf=None, usb=None) -> dict | None:
    """一个信号 → 现行 X6 单笔 + 持有中每天的特征与目标（没买到 / 130 根内没卖掉 → None）。"""
    import nkt_study as NK
    from qbreak import exit_forward as XF
    pr, _ = NK._prepare(tk, df, d, p0, bt)
    if pr is None:
        return None
    f, d, end, a, kk, px, pos, end_pos = pr
    ch3 = np.asarray(XF.chandelier_flags(f, kk, px, k=K_BASE), bool)
    b = XF._one(tk, f.assign(dead_cross=ch3), replace(p0, max_hold_days=MAX_HOLD), bt, d, end)
    nb = NK._net(b, a, rt)
    if not np.isfinite(nb):
        return None
    xp = int(f.index.get_loc(pd.Timestamp(b["exit_date"])))
    last = xp - 2
    o = f["Open"].to_numpy(float)
    if last >= kk:
        X = features(f.iloc[:last + 1], kk, px, nkf, usb)
        rem = remaining(o[kk + 1:last + 2], float(b["exit_px"]), slip)
    else:
        X, rem = pd.DataFrame(columns=FEATS, dtype=float), np.zeros(0)
    return {"ticker": str(tk), "date": pd.Timestamp(d), "fill": pd.Timestamp(f.index[kk]), "kk": int(kk), "px": float(px),
            "exit": pd.Timestamp(f.index[xp]), "exit_px": float(b["exit_px"]), "reason": NK._reason(b), "nb": float(nb),
            "hold": int(xp - kk), "X": X, "rem": np.asarray(rem, float),
            "alt": (o[kk + 1:last + 2] * (1 - slip) / px - 1) * 100 - rt if last >= kk else np.zeros(0)}


def tkey(T: dict) -> tuple:
    return (T["ticker"], str(T["fill"].date()))


def unique(trajs: list[dict]) -> list[dict]:
    """按（票, 成交日）去重（保留第一次出现的）。"""
    seen, out = set(), []
    for T in trajs:
        k = tkey(T)
        if k not in seen:
            seen.add(k)
            out.append(T)
    return out


# ───────────────────────── 四 学法 ─────────────────────────
def fit_predict(Xtr: np.ndarray, ytr: np.ndarray, Xs: list[np.ndarray]) -> list[np.ndarray]:
    from qbreak.ml import HistGBM
    m = HistGBM(**GBM).fit(Xtr, np.clip(ytr, -CLIP, CLIP))
    return [m.predict(x) if len(x) else np.zeros(0) for x in Xs]


def _stack(trajs: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    if not trajs:
        return np.zeros((0, len(FEATS))), np.zeros(0)
    return (np.vstack([T["X"].to_numpy(float) for T in trajs if len(T["rem"])] or [np.zeros((0, len(FEATS)))]),
            np.concatenate([T["rem"] for T in trajs if len(T["rem"])] or [np.zeros(0)]))


def fwd_preds(train_pool: list[dict], targets: list[dict], years=YEARS, say=None) -> tuple[list[np.ndarray], dict]:
    """逐年前推：targets 每一笔每一行的预测（第 Y 年的行用 X6 卖出日 < Y-01-01 的单笔学的模型；单笔不够 → NaN）。"""
    preds = [np.full(len(T["rem"]), np.nan) for T in targets]
    cover = {}
    for Y in years:
        cut = pd.Timestamp(f"{Y}-01-01")
        tr = [T for T in train_pool if T["exit"] < cut]
        rows = [(i, np.flatnonzero(T["X"].index.year == Y)) for i, T in enumerate(targets) if len(T["rem"])]
        rows = [(i, r) for i, r in rows if len(r)]
        cover[Y] = len(tr)
        if len(tr) < MIN_TRAIN or not rows:
            continue
        Xtr, ytr = _stack(tr)
        ps = fit_predict(Xtr, ytr, [targets[i]["X"].to_numpy(float)[r] for i, r in rows])
        for (i, r), p in zip(rows, ps):
            preds[i][r] = p
        if say:
            say(f"  {Y}：学 {len(tr)} 笔 / {len(ytr)} 行")
    return preds, cover


def loeo_preds(train_pool: list[dict], targets: list[dict], window) -> list[np.ndarray]:
    """留一年代：成交日在 window [a, b) 之外的单笔学一个模型，预测 targets 的全部行。"""
    a, b = window
    tr = [T for T in train_pool if not (a <= T["fill"] < b)]
    Xtr, ytr = _stack(tr)
    rows = [i for i, T in enumerate(targets) if len(T["rem"])]
    ps = fit_predict(Xtr, ytr, [targets[i]["X"].to_numpy(float) for i in rows]) if rows else []
    out = [np.full(len(T["rem"]), np.nan) for T in targets]
    for i, p in zip(rows, ps):
        out[i] = p
    return out


def flag_days(T: dict, pred: np.ndarray, thr: float) -> frozenset:
    """预测 < 门槛的收盘日（NaN 不算）。"""
    p = np.asarray(pred, float)
    m = np.isfinite(p) & (p < thr)
    return frozenset(pd.DatetimeIndex(T["X"].index[m]).normalize())


def first_flag(pred: np.ndarray, thr: float) -> int | None:
    p = np.asarray(pred, float)
    hit = np.flatnonzero(np.isfinite(p) & (p < thr))
    return int(hit[0]) if len(hit) else None


# ───────────────────────── 单笔层评估 ─────────────────────────
def pool_stats(nb, nv, changed, hold_b=None, hold_c=None) -> dict:
    nb, nv, ch = np.asarray(nb, float), np.asarray(nv, float), np.asarray(changed, bool)
    n = len(nb)
    if not n:
        return {"n": 0}
    out = {"n": int(n), "win_b": float((nb > 0).mean() * 100), "win_c": float((nv > 0).mean() * 100),
           "mean_b": float(nb.mean()), "mean_c": float(nv.mean()), "changed": int(ch.sum()),
           "g": float((nv - nb)[ch].sum() / max(int(ch.sum()), 1))}
    out["dwin"], out["dmean"] = out["win_c"] - out["win_b"], out["mean_c"] - out["mean_b"]
    if hold_b is not None and hold_c is not None:
        out["hold_b"], out["hold_c"] = float(np.mean(hold_b)), float(np.mean(hold_c))
    return out


def eval_trajs(trajs: list[dict], preds: list[np.ndarray], thr: float, frames: dict, p0, bt, rt: float) -> dict:
    """每一笔：第一个标记日 t* → 直接用引擎跑 X6 + 标记（死叉列 = 吊灯 | 标记）；同时核对公式（t* 的 alt）。"""
    import nkt_study as NK
    from qbreak import exit_forward as XF
    nb, nv, ch, hb, hc, diffs = [], [], [], [], [], []
    for T, p in zip(trajs, preds):
        k = first_flag(p, thr)
        nb.append(T["nb"])
        hb.append(T["hold"])
        if k is None:
            nv.append(T["nb"]), ch.append(False), hc.append(T["hold"])
            continue
        pr, _ = NK._prepare(T["ticker"], frames[T["sm"]].get(T["ticker"]), T["date"], p0, bt)
        f, d, end, a, kk, px, pos, end_pos = pr
        ch3 = np.asarray(XF.chandelier_flags(f, kk, px, k=K_BASE), bool)
        one = np.zeros(len(f), bool)
        one[kk + k] = True
        r = XF._one(T["ticker"], f.assign(dead_cross=ch3 | one), replace(p0, max_hold_days=MAX_HOLD), bt, d, end)
        v = NK._net(r, a, rt)
        nv.append(v), ch.append(True)
        hc.append(int(f.index.get_loc(pd.Timestamp(r["exit_date"]))) - kk if r is not None else T["hold"])
        diffs.append(abs(v - float(T["alt"][k])) if np.isfinite(v) else np.inf)
    st = pool_stats(nb, nv, ch, hb, hc)
    dv = np.asarray(diffs, float)
    st["check"] = {"n": int(len(dv)), "ok_share": float((dv < CHECK_TOL).mean()) if len(dv) else 1.0,
                   "max": float(dv[np.isfinite(dv)].max()) if np.isfinite(dv).any() else None}
    return st


def oracle(trajs: list[dict]) -> float | None:
    """完美卖点上限：每笔 max(nb, 持有中任意一天的明天开盘卖) − nb 的平均（pp）。"""
    v = [max(T["nb"], float(np.nanmax(T["alt"]))) - T["nb"] if len(T["alt"]) else 0.0 for T in trajs]
    return float(np.mean(v)) if v else None


# ───────────────────────── 描述 ─────────────────────────
def spearman(x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return None
    r = pd.Series(x[m]).rank().corr(pd.Series(y[m]).rank())
    return None if not np.isfinite(r) else float(r)


def era_rows(trajs: list[dict], preds: list[np.ndarray] | None, window) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """行的日期在 window [a, b) 里的行：特征、rem、预测。"""
    a, b = window
    Xs, ys, ps = [], [], []
    for i, T in enumerate(trajs):
        if not len(T["rem"]):
            continue
        m = (T["X"].index >= a) & (T["X"].index < b)
        if m.any():
            Xs.append(T["X"][m])
            ys.append(T["rem"][m])
            ps.append(preds[i][m] if preds is not None else np.full(int(m.sum()), np.nan))
    if not Xs:
        return pd.DataFrame(columns=FEATS), np.zeros(0), np.zeros(0)
    return pd.concat(Xs), np.concatenate(ys), np.concatenate(ps)


def a1_reading(rho: dict) -> dict:
    pos = sum(1 for e in ERAS if rho.get(e) is not None and rho[e] >= A1_RHO)
    return {"eras": pos, "ok": pos >= 2}


def verdict(s1: dict) -> str:
    return "第一关通过（第二关另行登记）" if s1.get("ok") else "第一关不过"


# ───────────────────────── 账户钩子 ─────────────────────────
def stock_reasons(trades, a, b) -> dict:
    """账户里窗口内（买入日 a〜b）、已平仓的日本个股交易按离场理由的笔数（L6.run 的返回里没有理由 → 从刚跑完的引擎的成交表数）。"""
    tr = pd.DataFrame(trades)
    if not len(tr):
        return {}
    ed = pd.to_datetime(tr["entry_date"])
    m = (tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(STOCK_SKIP) & (tr["reason"] != "end")
         & (ed >= pd.Timestamp(a)) & (ed < pd.Timestamp(b)))
    return {str(k): int(v) for k, v in tr.loc[m.to_numpy(), "reason"].value_counts().items()}


def _tick_exit_entry(self, i: int, xt: dict) -> None:
    """第 i 天收盘：日本个股（票, 成交日）的标记日里有今天、没排队离场 → 第二天开盘卖（reason = learned_exit）。"""
    d = pd.Timestamp(self.gidx[i]).normalize()
    st = self.st
    for t in list(st.pos):
        ps = st.pos[t]
        if ps.market != "JP" or t in st.pending_exit:
            continue
        s = xt.get((t, str(pd.Timestamp(ps.entry_date).date())))
        if s and d in s:
            st.pending_exit[t] = REASON


@contextlib.contextmanager
def entry_hook():
    import candle_portfolio as CP
    old = CP.MixEngine._tick_exit
    CP.MixEngine._tick_exit = _tick_exit_entry
    try:
        yield
    finally:
        CP.MixEngine._tick_exit = old


# ───────────────────────── 运行 ─────────────────────────
def git_info() -> dict:
    root = Path(__file__).resolve().parents[2]
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "quant_breakout/scripts", "quant_breakout/qbreak"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def run(say=print) -> dict:
    import jq_study as JS
    import kshape_link_study as KS
    import loop6_common as L6
    import loop9_common as C9
    import loop10_common as C10
    import loop11_common as LC
    import month_up_dip_study as MUD
    import nkt_study as NK
    import research_loop2 as R2
    import trendline_study as TS
    t0 = time.time()
    W = C10.load()
    say(f"载入：{time.time() - t0:.0f}s")
    tbf, tbf_pool = TS.tbf_gates(W, say)
    pre = KS.prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit("先决条件不满足 → 停")
    ticks = {e: C9.tick_of(C9.signals(W, e)["ticker"], C9.signals(W, e)["date"], tbf[e]) for e in ERAS}

    win = {e: TS._win(*W["ctx"][e]["windows"][e]) for e in ERAS}

    def acct(e: str, flags: dict | None) -> dict:
        kw = {"em_tick": ticks[e]} if ticks[e] else {}
        if flags:
            kw["exit_tick"] = flags
        with entry_hook():
            r = L6.run(W, e, **kw)
        return {**{k: r.get(k) for k in C9.KEYS}, "reasons": stock_reasons(JS.RealLotEngine.LAST[-1].st.trades, *win[e]), "years": r.get("years")}

    base = {e: acct(e, None) for e in ERAS}
    same = {e: KS.same_prep(base[e], KS.B4_PREP[e]) for e in ERAS}
    if not all(same.values()):
        raise SystemExit(f"B4 重算 ≠ 登记值 → 停：{same}")
    say(f"基准（{time.time() - t0:.0f}s）")

    # 池子与单笔
    bt, rt = LC.bt_rt()
    slip = bt.exec_cfg.slippage_pct / 100
    nk = MUD.read_cache_direct("^N225", 27)
    if nk is None:
        raise SystemExit("没有 ^N225 缓存 → 停")
    nkf = nikkei_feats(nk["Close"])
    usb = W["bear"]["US"].astype(float)
    P = NK.pool_signals(W, tbf, tbf_pool)
    frames = NK.pool_frames(W)
    TR: dict[str, list[dict]] = {}
    for s in POOLS:
        X = P[s]
        L = []
        for t, d, sm in zip(X["ticker"], X["date"], X["sm"]):
            T = trajectory(t, frames[sm].get(t), d, W["p0"], bt, rt, slip, nkf, usb)
            if T is not None:
                T["sm"], T["pool"] = sm, s
                L.append(T)
        TR[s] = L
        say(f"{s}：信号 {len(X)}、单笔 {len(L)}、行 {sum(len(T['rem']) for T in L)}（{time.time() - t0:.0f}s）")
    pool_all = unique([T for s in POOLS for T in TR[s]])
    res: dict = {"study": OUT, "id": ID, "git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}, "b4_same": same,
                 "base": base, "rt": rt, "slip": slip,
                 "pools": {s: {"signals": int(len(P[s])), "trajs": len(TR[s]), "rows": int(sum(len(T["rem"]) for T in TR[s]))} for s in POOLS},
                 "unique_trajs": len(pool_all)}

    # 学
    targets = [T for s in POOLS for T in TR[s]]
    pf, cover = fwd_preds(pool_all, targets, say=say)
    res["cover"] = {str(k): v for k, v in cover.items()}
    PF, off = {}, 0
    for s in POOLS:
        PF[s] = pf[off:off + len(TR[s])]
        off += len(TR[s])
    Nn = {e: [i for i, T in enumerate(TR["N"]) if T["sm"] == e] for e in ERAS}
    PL = {e: loeo_preds(pool_all, [TR["N"][i] for i in Nn[e]], win[e]) for e in ERAS}
    say(f"学完（{time.time() - t0:.0f}s）")

    # 描述：信息
    desc: dict = {"base_rate": {}, "rho": {}, "auc": {}, "feat_rho": {}, "oracle": {s: oracle(TR[s]) for s in POOLS}}
    import crash_warn_study as CW
    for e in ERAS:
        Xe, ye, pe = era_rows(targets, pf, win[e])
        desc["base_rate"][e] = {"rows": int(len(ye)), "mean": float(np.mean(ye)) if len(ye) else None,
                                "neg_pct": float((ye < 0).mean() * 100) if len(ye) else None,
                                "pred_rows": int(np.isfinite(pe).sum())}
        desc["rho"][e] = spearman(pe, ye)
        desc["auc"][e] = CW.auc(-pe, (ye < 0).astype(float)) if len(ye) else None
        desc["feat_rho"][e] = {c: spearman(Xe[c].to_numpy(float), ye) for c in FEATS}
    res["desc"] = desc
    res["A1"] = a1_reading(desc["rho"])

    # 单笔层（逐年前推）+ 核对
    res["cands"] = {}
    for cid, thr in CANDS.items():
        row: dict = {"thr": thr, "pools": {}}
        for s in POOLS:
            row["pools"][s] = eval_trajs(TR[s], PF[s], thr, frames, W["p0"], bt, rt)
        bad = [s for s in POOLS if row["pools"][s]["check"]["ok_share"] < CHECK_MIN]
        if bad:
            raise SystemExit(f"{cid} 单笔层核对不过（{bad}）→ 停")
        res["cands"][cid] = row
        say(f"{cid} 单笔层（{time.time() - t0:.0f}s）")

    # 账户：正向对照
    pos_ctl = {}
    for e in ERAS:
        fl = {tkey(TR["N"][i]): frozenset([TR["N"][i]["fill"].normalize()]) for i in Nn[e]}
        r = acct(e, fl)
        pos_ctl[e] = {"learned": int((r.get("reasons") or {}).get(REASON, 0)), "n": r.get("n")}
    res["pos_ctl"] = pos_ctl
    if not all(v["n"] and v["learned"] >= 0.5 * v["n"] for v in pos_ctl.values()):
        raise SystemExit(f"正向对照不过 → 停：{pos_ctl}")
    say(f"正向对照（{time.time() - t0:.0f}s）")

    for cid, thr in CANDS.items():
        row = res["cands"][cid]
        fl_f = {e: {tkey(TR["N"][i]): flag_days(TR["N"][i], PF["N"][i], thr) for i in Nn[e]} for e in ERAS}
        fl_l = {e: {tkey(TR["N"][i]): flag_days(TR["N"][i], p, thr) for i, p in zip(Nn[e], PL[e])} for e in ERAS}
        cand = {e: acct(e, {k: v for k, v in fl_f[e].items() if v}) for e in ERAS}
        cl = {e: acct(e, {k: v for k, v in fl_l[e].items() if v}) for e in ERAS}
        trade = {s: {k: row["pools"][s].get(k) for k in ("n", "dwin", "dmean")} for s in ("W", "Jx")}
        unseen = row["pools"]["Zx"].get("dmean")
        s1 = R2.stage1(cand, base, trade=trade, lenses={"loeo": (cl, base), "fwd": (cand, base)}, posthoc=unseen)
        row.update({"acct": cand, "loeo_acct": cl, "stage1": s1, "verdict": verdict(s1),
                    "d": {e: (None if cand[e]["calmar"] is None else round(cand[e]["calmar"] - base[e]["calmar"], 4)) for e in ERAS},
                    "learned": {e: int((cand[e].get("reasons") or {}).get(REASON, 0)) for e in ERAS}})
        say(f"{cid} 账户（{time.time() - t0:.0f}s）：{row['verdict']}")
    res["elapsed_s"] = round(time.time() - t0)
    return res


# ───────────────────────── 报告 ─────────────────────────
def _f(v, f="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def report(res: dict) -> str:
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    g = res["git"]
    L = [f"# 卖法：持仓状态学出来的离场 LXE（JST {time.strftime('%Y-%m-%d')}；规则见 scripts/learned_exit_study.py 开头）", "",
         f"代码 {g['rev']}（未提交的改动：{g['dirty']}）；B4 = 登记值：{res['b4_same']}；往返费用 {res['rt']:.4f}%、滑点 {res['slip'] * 100:.2f}%；用时 {res['elapsed_s']} s。", "",
         "## 池子与学的数据", "",
         "| 池子 | 信号 | 单笔 | 行（持有日） | 完美卖点上限 pp/笔 |", "|---|---|---|---|---|"]
    for s in POOLS:
        p = res["pools"][s]
        L.append(f"| {s} | {p['signals']} | {p['trajs']} | {p['rows']} | {_f(res['desc']['oracle'][s], '{:+.2f}')} |")
    cov = res["cover"]
    first = next((y for y, n in cov.items() if n >= MIN_TRAIN), None)
    L += ["", f"去重后单笔 {res['unique_trajs']}；逐年前推第一次有模型的年份：{first}（之前的年份 = B4）。", "",
          "## 信息（描述；行 = 持有日，按行的日期分年代）", "",
          "| 年代 | 行 | 剩下的收益平均 % | < 0 的比例 % | 有预测的行 | 秩相关 ρ（预测 vs 实际） | AUC（少赚） |", "|---|---|---|---|---|---|---|"]
    D = res["desc"]
    for e in ERAS:
        b = D["base_rate"][e]
        L.append(f"| {e} | {b['rows']} | {_f(b['mean'], '{:+.2f}')} | {_f(b['neg_pct'], '{:.1f}')} | {b['pred_rows']} | {_f(D['rho'][e])} | {_f(D['auc'][e])} |")
    L += ["", f"A1（ρ ≥ {A1_RHO} 的年代 ≥ 2）：{res['A1']['eras']} / 3 → {'持仓状态对剩下的收益有信息' if res['A1']['ok'] else '没有可用的信息'}", "",
          "每个特征与剩下的收益的秩相关（Z / E / J；探索变量，只描述）：", ""]
    for c in FEATS:
        L.append(f"- {c}：" + " / ".join(_f(D["feat_rho"][e][c]) for e in ERAS))
    for cid, row in res["cands"].items():
        L += ["", f"## {cid}（预计剩下的收益 < {row['thr']:+.0f}% → 第二天开盘卖）：{row['verdict']}", "",
              "| 池子 | 笔数 | 改了几笔 | 胜率 现行 → 候选 % | 每笔 现行 → 候选 % | 差 pp/笔 | 每次改的平均差 g pp | 持有天数 现行 → 候选 |", "|---|---|---|---|---|---|---|---|"]
        for s in POOLS:
            p = row["pools"][s]
            if not p.get("n"):
                L.append(f"| {s} | 0 | — | — | — | — | — | — |")
                continue
            L.append(f"| {s} | {p['n']} | {p['changed']} | {p['win_b']:.1f} → {p['win_c']:.1f} | {p['mean_b']:+.2f} → {p['mean_c']:+.2f} | "
                     f"{p['dmean']:+.3f} | {p['g']:+.2f} | {p['hold_b']:.1f} → {p['hold_c']:.1f} |")
        L += ["", "| 年代 | Calmar B4 → 候选（差） | 年化 % | 回撤 % | 笔数 | 胜率 % | learned_exit 笔数 | 留一年代 Calmar |", "|---|---|---|---|---|---|---|---|"]
        for e in ERAS:
            b, c, cl = res["base"][e], row["acct"][e], row["loeo_acct"][e]
            L.append(f"| {e} | {_f(b['calmar'])} → {_f(c['calmar'])}（{_f(row['d'][e])}） | {_f(b['cagr'], '{:.2f}')} → {_f(c['cagr'], '{:.2f}')} | "
                     f"{_f(b['dd'], '{:.2f}')} → {_f(c['dd'], '{:.2f}')} | {b['n']} → {c['n']} | {_f(b['win'], '{:.1f}')} → {_f(c['win'], '{:.1f}')} | "
                     f"{row['learned'][e]} | {_f(cl['calmar'])} |")
        s = row["stage1"]
        L += ["", f"第一关：S1 {yn(s['S1'])}、S2 {yn(s['S2'])}、S3 {yn(s['S3'])}、S4 {yn(s['S4'])}、S5 {yn(s['S5'])}、S6 {yn(s['S6'])}、"
              f"S7（Zx 每笔差 {_f(s['posthoc']['unseen'])} pp）{yn(s['S7'])}"]
    L += ["", f"正向对照（成交日收盘就标记 → learned_exit / 笔数）：" + "、".join(f"{e} {v['learned']} / {v['n']}" for e, v in res["pos_ctl"].items()), "",
          "只是研究，不改模拟盘 / 执行器 / 策略参数。非投资建议。"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    import os
    from qbreak import paths
    os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
    ap = argparse.ArgumentParser(description="卖法：持仓状态学出来的离场（LXE）")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 0
    out = paths.out_dir()
    if (out / f"{OUT}.json").exists():
        print(f"{OUT}.json 已存在 → 只运行一次，不再运行")
        return 1
    res = run()
    text = report(res)
    print(text)
    (out / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (out / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
