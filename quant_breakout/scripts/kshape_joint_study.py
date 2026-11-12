"""kshape_joint_study.py — 日K + 周K + 月K 合起来（不是各看各的）：能不能预测之后 1 / 5 / 21 个交易日的涨跌、
比只用一个周期好不好、用来优化现行算法（B4）会不会更好（登记版：规则、代码与登记前个数一起提交，之后不改、只运行一次）。

来由：用户 2026-10-23「日周月K结合到一起进行研究的话如何 而不是只分析单独的日周月」（接 kshape_link_study 的结果之后）。
以前和「多周期一起」有关的（结论都是不改）：多周期 R1（mtf_study：日 / 周 / 月线趋势状态的 8 种组合 → 之后超额 ≈ 0）、
起涨 / 起跌点 × 日 / 周 / 月线 46 个特征（turn_shape_study：认得出新高 / 新低、认不出会不会转）、月K 往上 + 日 / 周K 往下（month_up_dip_study）、
kshape_link_study 的 XC（日 + 周 + 月各最近 1 块的 9 种形状查表 → 方向一致但不够）。
**这次的不同**：① 每个周期都取 3 块、用连续的数（涨跌 ÷ 波动、收在哪儿、振幅 ÷ 波动），不分 9 种；② 周 / 月里加上**正在走的这一周 / 这一月**
（到当天收盘为止，= 面板上看到的那一根）；③ 模型能学三个周期之间的搭配（梯度提升树 = 交互），并且和「只用日K / 只用周K / 只用月K」的同样模型
在同一批行上比 → 直接回答「合起来是不是比单独的好」；④ 预测的是每个交易日收盘时的之后 1 / 5 / 21 日（不是对齐到下一块），可以直接接到 B4 的信号日。

〇 特征（每只票、每个交易日 t 收盘时；只用到 t 收盘为止的数据；研究行情 = 调整后价；qbreak.kline.ohlcv）
  日K（9 个）：t、t−1、t−2 三天各 3 个：z = 涨跌 ÷ σd（σd = 前 20 天 log 涨跌的标准差，不含这一天）、CLV =（收盘 − 最低）÷（最高 − 最低）
    （最高 = 最低 → 0.5）、rg =（最高 − 最低）÷ 前一天收盘 ÷ σd。
  周K（10 个）：正在走的这一周（W-FRI；到 t 为止：涨跌 = t 的收盘 ÷ 上周收盘 − 1、最高 / 最低 = 本周到 t 为止）+ 上一周、上上周（走完的）各 3 个
    （z、CLV、rg；σw = 那一周之前 20 个走完的周的 log 涨跌的标准差）+ 这周已经过了几天 ÷ 5。
  月K（10 个）：同周K（σm = 之前 12 个走完的月；过了几天 ÷ 21）。合计 29 个；29 个都算得出的行才进来（研究与打分都一样）。
一 目标与模型（每个期限 h = 1 / 5 / 21 个交易日 —— 日 / 周 / 月的尺度）
  目标 = t+1 开盘买、t+h 收盘卖的涨跌（%）减去同一样本同一天全部行的平均（超额）；训练时超额截到 ±10 / ±20 / ±40 pp。
  每个 h 5 个模型（同一批行）：JG = 29 个特征的梯度提升树（qbreak.ml.HistGBM：300 棵、lr 0.05、深 3、叶 ≥ 200、32 桶、行 0.5、列 0.8、λ 1、种子 0
  = allstock_study 同一组超参数）；JR = 29 个特征的岭回归（标准化、惩罚 0.01 × 行数）；SD / SW / SM = 只用日K 9 个 / 周K 10 个 / 月K 10 个特征的同样的树。
  行 = 每个样本的交易日每 5 天取 1 天（年代日历的第 0、5、10… 天；t ≥ 窗口起点、t+h 的日期 < 窗口终点）。
  交叉拟合（同 kshape_link_study）：模型 I = E + W 训练 → 预测 Z、Zx、J、Jx；模型 II = J + Jx 训练 → 预测 E、W。6 个样本都是样本外。
二 判定（JG、JR × 3 个期限 = 6 个；P_MAX = 0.05 / 6）
  每天横截面：IC = 预测与实际超额的秩相关（那天 ≥ 20 行）；分档差 = 预测前三分之一 − 后三分之一的实际超额平均（pp）。
  合起来 = 同一天在几个样本里 → 先取平均，再按块做单侧 t 检验（h = 1 / 5：每个取样日一块；h = 21：连续 5 个取样日 ≈ 25 个交易日一块，避免重叠）。
  「有可用的信息」(info) = 6 个样本平均 IC 都 > 0、合起来 p < P_MAX、合起来分档差 ≥ 0.15 / 0.30 / 0.60 pp（h = 1 / 5 / 21；同 kshape_link_study）。
  「比单独的好」(better) = 同一批行上 ΔIC = IC（这个模型）− IC（单周期里最好的那个：SD / SW / SM 中合起来平均 IC 最高的，在评价数据上挑 → 偏向单周期，
    对「合起来」是保守的）：合起来（同上按块）p < P_MAX，且 6 个样本里 ≥ 5 个 ΔIC 平均 > 0。
  判定：V0「合起来有可用的信息，而且比单独一个周期好」= info ∧ better；V1「有可用的信息，但单独一个周期就差不多」= info ∧ ¬better；
  V2「合起来比单独的好，但还不够用」= ¬info ∧ better ∧ 6 个样本 IC 都 > 0；V3「方向一致但不够」= 6 个样本 IC 都 > 0；V4「没有信息」= 其余。
三 结合现行 B4（买点过滤；3 个做法；看到任何结果之前设计 → posthoc = False；不管二的判定如何都运行）
  JBD / JBW / JBM =「信号日 t 收盘时 JG（h = 1 / 5 / 21）预测的超额在当天同一样本里算得出的票中排后三分之一 → 不开新仓」
  （模型 = 没见过这个样本的那一折：Z / J / Jx / Zx ← I、E / W ← II；TBF 挡的照旧不买；算不出 → 不挡）。打分用每个交易日（不是每 5 天）。
  基准 / 先决条件 / 第一关 / 池子 / 几乎不触发（< 10 笔）/ 第二关 = kshape_link_study 三（规则指纹 1241753c8f2529c6、接线核对、
  B4 重算 = 同一份 B4_PREP：Z 27 笔 77.8% 1.186、E 39 / 43.6% / 0.664、J 57 / 50.9% / 0.676；任一不过 → 停）。
  两关都过 =「更好候选」→ 报告给用户；进模拟盘 / 执行器要用户决定（不自动改）。
四 只描述（不参与判定）：① 15 个模型各样本的 IC / 分档差；② 日K 今天 × 这一周到今天 × 这一月到今天的方向（z 按 ±0.5 分涨 / 平 / 跌）= 27 种组合，
  之后 5 日 / 21 日的平均超额与行数，分三个年代（2001〜06 Z + Zx、2006〜16 E + W、2017〜26 J + Jx）—— 三个年代同号的标出来；
  ③ JR 的标准化系数绝对值按日 / 周 / 月分的占比（哪个周期在起作用）；④ B4 实际成交按信号日 JG 预测的三档的胜率 / 每笔。
五 事前预期（运行前写，照实）：日本个股的短期反转 → 日K 与这一周的涨跌系数为负、h = 1 / 5 的 IC 约 +0.01〜+0.03；合起来比单独的日K 略好
  （周 / 月的部分有一点额外的反转 / 动量信息），better 可能在 h = 5 过（约 30%）；但扣开盘跳空后分档差多半不到门槛 → 多半 V2 / V3，
  V0 约 5〜10%；h = 21 几乎没有信息。B：JBD / JBW 学到反转 → 会挡掉「大涨收在高位」的突破日 → 账户多半变差；每个做法第一关约 2〜5%。
六 局限：日経225 用今天的成员（幸存者偏差）；Jx 不按当时的成员筛；调整后价；停牌时 t+h 跨的日历时间会更长；特征只有 K 线的形状
  （量、基本面不在里面 —— 这次只回答「日周月K 合起来」）；多重检验：二 6 个判断（P_MAX = 0.05 / 6）、三 3 个做法。模拟盘 / 执行器不因这次研究改。
登记前只数个数（--prep；不拟合模型、不算任何收益）：见 var/sim_changes.md 的登记节（与本文件同一次提交）。
用法：python scripts/kshape_joint_study.py --prep（载入 + 先决条件 + 只数个数）；--run（只运行一次：输出已经存在就停）。
输出：var/out/kshape_joint_study.md / .json（只有汇总统计，没有个股名单）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kshape_link_study as KS                                               # noqa: E402

OUT = "kshape_joint_study"
NVOL = {"D": 20, "W": 20, "M": 12}
FRAC_DEN = {"W": 5.0, "M": 21.0}
DIR_Z = 0.5
FEATS = ([f"d_{k}{i}" for i in range(3) for k in ("z", "clv", "rg")]
         + [f"w_{k}{i}" for i in range(3) for k in ("z", "clv", "rg")] + ["w_frac"]
         + [f"m_{k}{i}" for i in range(3) for k in ("z", "clv", "rg")] + ["m_frac"])
GROUP = {"D": [i for i, f in enumerate(FEATS) if f.startswith("d_")],
         "W": [i for i, f in enumerate(FEATS) if f.startswith("w_")],
         "M": [i for i, f in enumerate(FEATS) if f.startswith("m_")]}
HORIZONS = (1, 5, 21)
H_TF = {1: "D", 5: "W", 21: "M"}
CLIP = {1: 10.0, 5: 20.0, 21: 40.0}
MIN_SPREAD = {1: 0.15, 5: 0.30, 21: 0.60}
BLOCK = {1: 1, 5: 1, 21: 5}
STEP = 5
MIN_ROWS = 20
MODELS = ("JG", "JR", "SD", "SW", "SM")
JUDGED = ("JG", "JR")
SINGLES = ("SD", "SW", "SM")
MODEL_NAME = {"JG": "日 + 周 + 月K 合起来（树）", "JR": "日 + 周 + 月K 合起来（线性）", "SD": "只用日K（树）", "SW": "只用周K（树）",
              "SM": "只用月K（树）"}
GBM = dict(loss="l2", n_trees=300, lr=0.05, depth=3, min_leaf=200, n_bins=32, subsample=0.5, colsample=0.8, l2=1.0, seed=0)
RIDGE_ALPHA = 0.01
P_MAX = 0.05 / (len(JUDGED) * len(HORIZONS))
MIN_BETTER_SAMPLES = 5
VERDICTS = ("合起来有可用的信息，而且比单独一个周期好", "有可用的信息，但单独一个周期就差不多", "合起来比单独的好，但还不够用",
            "方向一致但不够", "没有信息")
SAMPLES = KS.SAMPLES
TRAIN = KS.TRAIN
MODEL_OF = KS.MODEL_OF
N225_ERAS = KS.N225_ERAS
POOLS = KS.POOLS
B_IDS = ("JBD", "JBW", "JBM")
B_H = {"JBD": 1, "JBW": 5, "JBM": 21}
B_NAME = {"JBD": "合起来预测之后 1 日排后三分之一 → 不买", "JBW": "合起来预测之后 5 日排后三分之一 → 不买",
          "JBM": "合起来预测之后 21 日排后三分之一 → 不买"}
MIN_TRIG = 10
ERA_GROUPS = {"2001〜06": ("Z", "Zx"), "2006〜16": ("E", "W"), "2017〜26": ("J", "Jx")}
DIR_NAME = ("跌", "平", "涨")


# ───────────────────────── 〇 特征（纯函数；tests/test_kshape_joint_study.py） ─────────────────────────
def _sigma(lr: np.ndarray, n: int) -> np.ndarray:
    """第 j 块的波动 = 前 n 块（不含 j）log 涨跌的标准差。"""
    return pd.Series(lr).rolling(n, min_periods=n).std(ddof=1).shift(1).to_numpy()


def _clv(c, h, lo) -> np.ndarray:
    rng = h - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(rng > 0, (c - lo) / np.where(rng > 0, rng, 1.0), 0.5)


def _shift(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if k == 0:
        return np.asarray(x, float).copy()
    if len(x) > k:
        out[k:] = x[:-k]
    return out


def daily_feats(c, h, lo) -> list[np.ndarray]:
    """日K 9 个：t、t−1、t−2 的 z / CLV / rg。"""
    n = len(c)
    r = np.full(n, np.nan)
    prev = np.full(n, np.nan)
    prev[1:] = c[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        r[1:] = c[1:] / c[:-1] - 1
        sd = _sigma(np.log1p(r), NVOL["D"])
        z = r / sd
        rg = (h - lo) / prev / sd
    clv = _clv(c, h, lo)
    return [_shift(v, k) for k in range(3) for v in (z, clv, rg)]


def coarse_feats(idx: pd.DatetimeIndex, c, h, lo, tf: str) -> list[np.ndarray]:
    """周K / 月K 10 个：正在走的这一块（到当天为止）+ 上一块、上上块（走完的）的 z / CLV / rg + 这一块过了几天 ÷ 5 / 21。"""
    n = len(c)
    key = idx.to_period("W-FRI" if tf == "W" else "M").asi8
    starts = np.r_[True, key[1:] != key[:-1]] if n else np.zeros(0, bool)
    bid = np.cumsum(starts) - 1
    st = np.flatnonzero(starts)
    end = np.r_[st[1:] - 1, n - 1] if n else np.zeros(0, int)
    bc = c[end]
    bh = np.maximum.reduceat(h, st) if n else np.zeros(0)
    bl = np.minimum.reduceat(lo, st) if n else np.zeros(0)
    nb = len(st)
    br = np.full(nb, np.nan)
    bprev = np.full(nb, np.nan)
    if nb > 1:
        bprev[1:] = bc[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        br[1:] = bc[1:] / bc[:-1] - 1
        sb = _sigma(np.log1p(br), NVOL[tf])
        bz = br / sb
        brg = (bh - bl) / bprev / sb
    bclv = _clv(bc, bh, bl)
    cumh = pd.Series(h).groupby(bid).cummax().to_numpy()
    cuml = pd.Series(lo).groupby(bid).cummin().to_numpy()
    p = bprev[bid]
    s = sb[bid]
    with np.errstate(invalid="ignore", divide="ignore"):
        z0 = (c / p - 1) / s
        rg0 = (cumh - cuml) / p / s
    clv0 = _clv(c, cumh, cuml)

    def lagb(v, k):
        j = bid - k
        return np.where(j >= 0, v[np.clip(j, 0, None)], np.nan)

    frac = (np.arange(n) - st[bid] + 1) / FRAC_DEN[tf]
    return [z0, clv0, rg0, lagb(bz, 1), lagb(bclv, 1), lagb(brg, 1), lagb(bz, 2), lagb(bclv, 2), lagb(brg, 2), frac]


def ticker_feats(df: pd.DataFrame) -> dict | None:
    """一只票 → {date, X (n × 29), o, c}（升序；X 的行 = 那一天收盘时的特征）。"""
    from qbreak import kline as K
    d = K.ohlcv(df)
    if len(d) < 60:
        return None
    c, h, lo, o = (d[k].to_numpy(float) for k in ("Close", "High", "Low", "Open"))
    cols = daily_feats(c, h, lo) + coarse_feats(d.index, c, h, lo, "W") + coarse_feats(d.index, c, h, lo, "M")
    return {"date": d.index.values.astype("datetime64[ns]"), "X": np.column_stack(cols).astype(np.float32), "o": o, "c": c}


def targets(o: np.ndarray, c: np.ndarray, dates: np.ndarray, hz: int) -> tuple[np.ndarray, np.ndarray]:
    """第 i 行：t+1 开盘买、t+hz 收盘卖的涨跌 %（没有 → NaN）与 t+hz 的日期（没有 → NaT）。"""
    n = len(c)
    r = np.full(n, np.nan)
    e = np.full(n, np.datetime64("NaT"), "datetime64[ns]")
    if n > hz:
        with np.errstate(invalid="ignore", divide="ignore"):
            r[:n - hz] = (c[hz:] / o[1:n - hz + 1] - 1) * 100
        e[:n - hz] = dates[hz:]
    return r, e


def dir3(z: np.ndarray) -> np.ndarray:
    return np.where(z > DIR_Z, 2, np.where(z < -DIR_Z, 0, 1))


# ───────────────────────── 一 模型 ─────────────────────────
class Ridge:
    def fit(self, X, y):
        X = np.asarray(X, float)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-12
        from qbreak import ml as ML
        self.w = ML.ridge_fit((X - self.mu) / self.sd, np.asarray(y, float), RIDGE_ALPHA)
        return self

    def predict(self, X):
        from qbreak import ml as ML
        return ML.ridge_predict(self.w, (np.asarray(X, float) - self.mu) / self.sd)


def cols_of(model: str) -> list[int]:
    return {"SD": GROUP["D"], "SW": GROUP["W"], "SM": GROUP["M"]}.get(model, list(range(len(FEATS))))


def fit_model(model: str, X: np.ndarray, y: np.ndarray, hz: int):
    from qbreak import ml as ML
    yc = np.clip(np.asarray(y, float), -CLIP[hz], CLIP[hz])
    Xs = np.asarray(X, float)[:, cols_of(model)]
    return Ridge().fit(Xs, yc) if model == "JR" else ML.HistGBM(**GBM).fit(Xs, yc)


def predict_model(model: str, F, X: np.ndarray) -> np.ndarray:
    return F.predict(np.asarray(X, float)[:, cols_of(model)])


def block_t(series: pd.Series, hz: int) -> dict:
    """每天的值（index = 日期，已按样本平均）→ 按块平均后单侧 t 检验（h = 21：连续 5 个取样日一块）。"""
    s = series.dropna().sort_index()
    if BLOCK[hz] > 1 and len(s):
        s = s.groupby(np.arange(len(s)) // BLOCK[hz]).mean()
    return KS.t_one_sided(s.to_numpy(float))


def verdict(each_ic: list, pooled_p, pooled_spread, hz: int, better_p, better_n: int) -> str:
    ic_all = len(each_ic) == len(SAMPLES) and all(v is not None and np.isfinite(v) and v > 0 for v in each_ic)
    info = ic_all and pooled_p is not None and pooled_p < P_MAX and pooled_spread is not None and pooled_spread >= MIN_SPREAD[hz]
    better = better_p is not None and better_p < P_MAX and better_n >= MIN_BETTER_SAMPLES
    if info:
        return VERDICTS[0] if better else VERDICTS[1]
    if better and ic_all:
        return VERDICTS[2]
    return VERDICTS[3] if ic_all else VERDICTS[4]


# ───────────────────────── 数据 ─────────────────────────
def sample_days(W: dict, s: str) -> np.ndarray:
    """样本 s 的取样日：年代日历每 STEP 天取 1 天。"""
    import trendline_study as TS
    days = pd.DatetimeIndex(W["ctx"][TS.WIN_ERA[s]]["days"])
    return days.values.astype("datetime64[ns]")[::STEP]


def sample_table(FR: dict, sdays: np.ndarray, window) -> pd.DataFrame:
    """一个样本：取样日、29 个特征都有、t ≥ 窗口起点的行 + 三个期限的目标（t+h < 窗口终点，否则 NaN）与超额。"""
    a, b = (np.datetime64(pd.Timestamp(x), "ns") for x in window)
    parts = []
    for t, df in FR.items():
        f = ticker_feats(df)
        if f is None:
            continue
        keep = np.isin(f["date"], sdays) & (f["date"] >= a) & np.isfinite(f["X"]).all(1)
        if not keep.any():
            continue
        p = pd.DataFrame(f["X"][keep], columns=FEATS)
        p.insert(0, "date", f["date"][keep])
        p.insert(1, "ticker", t)
        for hz in HORIZONS:
            r, e = targets(f["o"], f["c"], f["date"], hz)
            r = r[keep]
            r[~(e[keep] < b)] = np.nan
            p[f"tg{hz}"] = r
        parts.append(p)
    if not parts:
        return pd.DataFrame(columns=["date", "ticker"] + FEATS + [f"tg{hz}" for hz in HORIZONS] + [f"ex{hz}" for hz in HORIZONS])
    X = pd.concat(parts, ignore_index=True)
    for hz in HORIZONS:
        X[f"ex{hz}"] = X[f"tg{hz}"] - X.groupby("date")[f"tg{hz}"].transform("mean")
    return X


def _key(dates) -> np.ndarray:
    return np.asarray(dates).astype("datetime64[D]").astype(np.int64)


# ───────────────────────── 运行 ─────────────────────────
def part_a(TABS: dict, say=print) -> tuple[dict, dict]:
    out: dict = {"horizons": {}, "align": {}, "ridge_share": {}}
    FITS: dict = {}
    for hz in HORIZONS:
        ex = f"ex{hz}"
        fits = {}
        for fold, tr in TRAIN.items():
            X = pd.concat([TABS[s] for s in tr], ignore_index=True)
            X = X[np.isfinite(X[ex])]
            for m in MODELS:
                fits[(m, fold)] = fit_model(m, X[FEATS].to_numpy(float), X[ex].to_numpy(float), hz)
            say(f"A h={hz} 折 {fold} 训练完（{len(X)} 行）")
        FITS[hz] = fits
        ics: dict = {m: {} for m in MODELS}
        sps: dict = {m: {} for m in MODELS}
        each: dict = {m: {} for m in MODELS}
        for s in SAMPLES:
            X = TABS[s]
            X = X[np.isfinite(X[ex])]
            for m in MODELS:
                pred = predict_model(m, fits[(m, MODEL_OF[s])], X[FEATS].to_numpy(float)) if len(X) else np.zeros(0)
                pb = KS.per_block(_key(X["date"]), pred, X[ex], MIN_ROWS)
                ics[m][s], sps[m][s] = pb["ic"], pb["spread"]
                each[m][s] = {"rows": int(len(X)), "days": int(len(pb)), "ic": float(pb["ic"].mean()) if len(pb) else None,
                              "spread": float(pb["spread"].mean()) if len(pb) else None}
        pooled = {}
        for m in MODELS:
            ic_by = pd.concat(ics[m].values()).groupby(level=0).mean()
            sp_by = pd.concat(sps[m].values()).groupby(level=0).mean()
            pooled[m] = {"ic": block_t(ic_by, hz), "spread": float(sp_by.mean()) if len(sp_by) else None}
        best = max(SINGLES, key=lambda m: -np.inf if pooled[m]["ic"]["mean"] is None else pooled[m]["ic"]["mean"])
        res = {"best_single": best, "models": {}}
        for m in MODELS:
            r = {"name": MODEL_NAME[m], "each": each[m], "pooled": pooled[m]}
            if m in JUDGED:
                d_each, d_all = {}, []
                for s in SAMPLES:
                    d = (ics[m][s] - ics[best][s]).dropna()
                    d_each[s] = float(d.mean()) if len(d) else None
                    d_all.append(d)
                d_by = pd.concat(d_all).groupby(level=0).mean() if d_all else pd.Series(dtype=float)
                bt = block_t(d_by, hz)
                npos = sum(1 for v in d_each.values() if v is not None and v > 0)
                r["better"] = {"vs": best, "each": d_each, "pooled": bt, "n_pos": npos}
                r["verdict"] = verdict([each[m][s]["ic"] for s in SAMPLES], pooled[m]["ic"]["p"], pooled[m]["spread"], hz,
                                       bt["p"], npos)
            res["models"][m] = r
        out["horizons"][hz] = res
        out["ridge_share"][hz] = ridge_share(fits)
        say(f"A h={hz} 完成（判定只写在文件里）")
    out["align"] = align_table(TABS)
    return out, FITS


def ridge_share(fits: dict) -> dict:
    """JR 的标准化系数绝对值按日 / 周 / 月的占比（%）。"""
    out = {}
    for fold in TRAIN:
        w = np.abs(fits[("JR", fold)].w[1:])
        tot = w.sum()
        out[fold] = {g: float(w[GROUP[g]].sum() / tot * 100) if tot > 0 else None for g in ("D", "W", "M")}
    return out


def align_table(TABS: dict) -> dict:
    """只描述 ②：日K 今天 × 这一周到今天 × 这一月到今天的方向 27 种 → 三个年代之后 5 / 21 日的平均超额与行数。"""
    out = {}
    for hz in (5, 21):
        rows = []
        for era, ss in ERA_GROUPS.items():
            X = pd.concat([TABS[s] for s in ss], ignore_index=True)
            X = X[np.isfinite(X[f"ex{hz}"])]
            k = dir3(X["d_z0"].to_numpy()) * 9 + dir3(X["w_z0"].to_numpy()) * 3 + dir3(X["m_z0"].to_numpy())
            g = pd.DataFrame({"k": k, "e": X[f"ex{hz}"].to_numpy(float)}).groupby("k")["e"].agg(["mean", "size"])
            for kk, v in g.iterrows():
                rows.append({"k": int(kk), "era": era, "mean": float(v["mean"]), "n": int(v["size"])})
        T = {}
        for r in rows:
            T.setdefault(r["k"], {})[r["era"]] = {"mean": r["mean"], "n": r["n"]}
        out[hz] = [{"combo": f"日{DIR_NAME[k // 9]} · 周{DIR_NAME[(k // 3) % 3]} · 月{DIR_NAME[k % 3]}", "k": k, "eras": T[k],
                    "same_sign": len(T[k]) == len(ERA_GROUPS) and (all(v["mean"] > 0 for v in T[k].values())
                                                                     or all(v["mean"] < 0 for v in T[k].values()))}
                   for k in sorted(T)]
    return out


def score_wide(FR: dict, F, model: str, days: pd.DatetimeIndex, chunk: int = 150) -> pd.DataFrame:
    """一个样本：每个交易日收盘时的预测（29 个特征都有的行；其余 NaN）→ 日期 × 票。"""
    out = {}
    names = sorted(FR)
    for k0 in range(0, len(names), chunk):
        fs, Xs = [], []
        for t in names[k0:k0 + chunk]:
            f = ticker_feats(FR[t])
            if f is None:
                continue
            ok = np.isfinite(f["X"]).all(1)
            fs.append((t, f["date"], ok))
            Xs.append(f["X"][ok])
        if not fs:
            continue
        allX = np.concatenate(Xs) if Xs else np.zeros((0, len(FEATS)))
        pred = predict_model(model, F, allX) if len(allX) else np.zeros(0)
        i = 0
        for t, dt, ok in fs:
            v = np.full(len(dt), np.nan)
            v[ok] = pred[i:i + ok.sum()]
            i += int(ok.sum())
            out[t] = pd.Series(v, index=pd.DatetimeIndex(dt)).reindex(days)
    return pd.DataFrame(out, index=days)


def part_b(W: dict, FR: dict, FITS: dict, tbf: dict, tbf_pool: dict, pre: dict, say=print) -> dict:
    import combo_all_common as CA
    import loop9_common as C9
    import research_loop11 as R11
    import trendline_study as TS
    out: dict = {"cand": {}, "other": {}, "stage1": {}, "trig": {}, "verdict": {}, "describe": {}}
    base = pre["base"]
    b4tr = {e: TS.b4_trades(W, e, tbf[e], {}) for e in N225_ERAS}
    SW: dict = {}
    for s in SAMPLES:
        days = pd.DatetimeIndex(W["ctx"][TS.WIN_ERA[s]]["days"])
        for k in B_IDS:
            SW[(k, s)] = score_wide(FR[s], FITS[B_H[k]][("JG", MODEL_OF[s])], "JG", days)
        say(f"B 打分 {s} 完成")
    for k in B_IDS:
        cand, other, trig, desc = {}, {}, 0, {}
        for s in SAMPLES:
            Sw = SW[(k, s)]
            Fl = KS.block_flags(Sw)
            if s in N225_ERAS:
                S = C9.signals(W, s)
                g = np.asarray(tbf[s], bool) | KS.lookup_wide(Fl, S["ticker"], S["date"])
                cand[s] = C9.acct(C9.run_block(W, s, g))
                tr = b4tr[s]
                trig += int(KS.lookup_wide(Fl, tr["ticker"], tr["sig"]).sum())
                ter = KS.tercile_of(Sw, tr["ticker"], tr["sig"])
                net = tr["net"].to_numpy(float)
                desc[s] = {lab: ({"n": int((ter == v).sum()), "win": float((net[ter == v] > 0).mean() * 100),
                                  "mean": float(net[ter == v].mean())} if (ter == v).any() else {"n": 0})
                           for v, lab in ((0, "后三分之一"), (1, "中间"), (2, "前三分之一"), (-1, "算不出"))}
            else:
                X = TS.pool_x(W, s)[~np.asarray(tbf_pool[s], bool)].reset_index(drop=True)
                gp = KS.lookup_wide(Fl, X["ticker"], X["date"])
                net = X["net"].to_numpy(float)
                dl = CA.delta(net, ~gp)
                gone = net[gp]
                other[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "changed": int(gp.sum()), "dwin": dl["dwin"], "dmean": dl["dmean"],
                            "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                            "gone_mean": float(gone.mean()) if len(gone) else None}
        out["cand"][k], out["other"][k], out["trig"][k], out["describe"][k] = cand, other, trig, desc
        out["stage1"][k] = R11.stage1(cand, base, other, lenses=None, posthoc=False)
        out["verdict"][k] = ("几乎不触发" if trig < MIN_TRIG else
                             ("第一关通过（要另行登记第二关）" if out["stage1"][k]["ok"] else "第一关不过"))
        say(f"B {k} 完成（判定只写在文件里）")
    out["base"] = base
    out["b4_trades"] = {e: int(len(b4tr[e])) for e in N225_ERAS}
    return out


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/kshape_joint_study.py", "scripts/kshape_link_study.py",
                                     "qbreak/kline.py", "qbreak/ml.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def load_all(say=print) -> tuple[dict, dict, dict, dict]:
    import loop10_common as C10
    import trendline_study as TS
    t0 = time.time()
    W = C10.load()
    say(f"载入 B3 + Zx：{time.time() - t0:.0f}s")
    tbf, tbf_pool = TS.tbf_gates(W, say)
    return W, KS.sample_frames(W), tbf, tbf_pool


def build_tables(W: dict, FR: dict, say=print) -> dict:
    TABS = {}
    for s in SAMPLES:
        TABS[s] = sample_table(FR[s], sample_days(W, s), KS.window_of(W, s))
        say(f"{s}：{TABS[s]['ticker'].nunique() if len(TABS[s]) else 0} 只、{len(TABS[s])} 行")
    return TABS


def prep(say=print) -> dict:
    import loop9_common as C9
    import trendline_study as TS
    W, FR, tbf, tbf_pool = load_all(say)
    pre = KS.prereq(W, tbf, say)
    TABS = build_tables(W, FR, say)
    out: dict = {"prereq": {k: v for k, v in pre.items() if k != "base"}, "git": git_info(), "tickers": {}, "rows": {}, "days": {}, "B": {}}
    for s in SAMPLES:
        X = TABS[s]
        out["tickers"][s] = int(X["ticker"].nunique()) if len(X) else 0
        out["rows"][s] = {hz: int(np.isfinite(X[f"tg{hz}"]).sum()) for hz in HORIZONS}
        out["days"][s] = int(X["date"].nunique()) if len(X) else 0
    for e in N225_ERAS:
        S = C9.signals(W, e)
        tr = TS.b4_trades(W, e, tbf[e], {})
        out["B"][e] = {"signals": int(len(S)), "not_tbf": int((~np.asarray(tbf[e], bool)).sum()), "b4_trades": int(len(tr))}
    for s in POOLS:
        X = TS.pool_x(W, s)
        out["B"][s] = {"signals": int(len(X)), "b4_buy": int((~np.asarray(tbf_pool[s], bool)).sum())}
    return out


def run(say=print) -> dict:
    t0 = time.time()
    W, FR, tbf, tbf_pool = load_all(say)
    pre = KS.prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit(f"先决条件不满足：{ {k: v for k, v in pre.items() if k != 'base'} } → 停")
    res: dict = {"study": OUT, "git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}}
    TABS = build_tables(W, FR, say)
    res["A"], FITS = part_a(TABS, say)
    del TABS
    res["B"] = part_b(W, FR, FITS, tbf, tbf_pool, pre, say)
    res["elapsed_s"] = round(time.time() - t0)
    return res


# ───────────────────────── 输出 ─────────────────────────
_f = KS._f


def report(res: dict) -> str:
    A, B = res["A"], res["B"]
    L = [f"# 日K + 周K + 月K 合起来：能不能预测之后 1 / 5 / 21 日、比单独一个周期好不好（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         "规则见 scripts/kshape_joint_study.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件：规则指纹 {res['prereq'].get('fingerprint')}、"
         f"B4 重算 = 登记前 {all(res['prereq'].get(e, {}).get('same_prep') for e in N225_ERAS)}、接线核对 {all(res['prereq'].get(e, {}).get('wired') for e in N225_ERAS)}；"
         f"用时 {res['elapsed_s']} s。", "", "## 一 / 二 判定（6 个样本都是样本外）", "",
         f"| 期限 | 模型 | 判定 | 合起来 IC | p（要 < {P_MAX:.4f}） | 分档差 pp（门槛） | 比最好的单周期（{'、'.join(SINGLES)}）多的 IC | p | 样本里多的个数 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for hz in HORIZONS:
        H = A["horizons"][hz] if hz in A["horizons"] else A["horizons"][str(hz)]
        for m in JUDGED:
            r = H["models"][m]
            po, bt = r["pooled"], r["better"]
            L.append(f"| {hz} 日 | {m} {r['name']} | **{r['verdict']}** | {_f(po['ic']['mean'], '{:+.4f}')}（{po['ic']['n']} 块） | "
                     f"{_f(po['ic']['p'], '{:.4f}')} | {_f(po['spread'])}（{MIN_SPREAD[hz]}） | vs {bt['vs']} {_f(bt['pooled']['mean'], '{:+.4f}')} | "
                     f"{_f(bt['pooled']['p'], '{:.4f}')} | {bt['n_pos']} / 6 |")
    L += ["", "15 个模型各样本（平均 IC / 分档差 pp）：", ""]
    for hz in HORIZONS:
        H = A["horizons"][hz] if hz in A["horizons"] else A["horizons"][str(hz)]
        for m in MODELS:
            r = H["models"][m]
            L.append(f"- {hz} 日 {m}（{r['name']}；合起来 IC {_f(r['pooled']['ic']['mean'], '{:+.4f}')}、分档差 {_f(r['pooled']['spread'])}）："
                     + "；".join(f"{s} {_f(x['ic'], '{:+.3f}')} / {_f(x['spread'], '{:+.2f}')}" for s, x in r["each"].items()))
    L += ["", "JR（线性）系数绝对值按周期的占比 %（折 I / 折 II）：", ""]
    for hz in HORIZONS:
        rs = A["ridge_share"][hz] if hz in A["ridge_share"] else A["ridge_share"][str(hz)]
        L.append(f"- {hz} 日：" + "；".join(f"{g} " + " / ".join(_f(rs[f][g], '{:.0f}') for f in TRAIN) for g in ("D", "W", "M")))
    L += ["", "## 三 结合现行 B4（买点过滤；第一关 = research_loop11.stage1，posthoc = False）", "",
          "| 做法 | 判定 | 挡掉的 B4 成交（Z + E + J） | Calmar 差 Z / E / J | 合起来胜率差 pp | 每笔差 pp | 池子 W / Jx / Zx 胜率差 pp |", "|---|---|---|---|---|---|---|"]
    for k in B_IDS:
        s1 = B["stage1"][k]
        d = s1.get("d") or {}
        oth = B["other"][k]
        L.append(f"| {k} {B_NAME[k]} | **{B['verdict'][k]}** | {B['trig'][k]} | "
                 + " / ".join(_f((d.get(e) if isinstance(d, dict) else None)) for e in N225_ERAS)
                 + f" | {_f(s1.get('dwin'), '{:+.2f}')} | {_f(s1.get('dmean'), '{:+.2f}')} | "
                 + " / ".join(_f((oth.get(s) or {}).get("dwin"), "{:+.2f}") for s in POOLS) + " |")
    L += ["", "B4 实际成交按信号日 JG 预测的三档（只描述；笔数 / 胜率 % / 每笔 %）：", ""]
    for k in B_IDS:
        L.append(f"- {k}：" + "；".join(f"{e} " + "、".join(
            f"{lab} {v['n']} 笔" + (f" {v['win']:.0f}% / {v['mean']:+.2f}%" if v.get("n") else "")
            for lab, v in B["describe"][k][e].items()) for e in N225_ERAS))
    L += ["", "## 四 只描述：日K 今天 × 这一周到今天 × 这一月到今天的方向（27 种）→ 之后的平均超额 pp（行数）；★ = 三个年代同号", ""]
    for hz in (5, 21):
        rows = A["align"][hz] if hz in A["align"] else A["align"][str(hz)]
        L += [f"之后 {hz} 日：", "", "| 组合 | " + " | ".join(ERA_GROUPS) + " |", "|---|" + "---|" * len(ERA_GROUPS)]
        for r in rows:
            L.append(f"| {'★ ' if r['same_sign'] else ''}{r['combo']} | "
                     + " | ".join((f"{r['eras'][e]['mean']:+.2f}（{r['eras'][e]['n']}）" if e in r["eras"] else "—") for e in ERA_GROUPS) + " |")
        L.append("")
    L += ["只研究，不改模拟盘 / 执行器 / 面板 / 策略参数。非投资建议。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prep", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if not (a.prep or a.run):
        raise SystemExit("要 --prep 或 --run")
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    t0 = time.time()
    say = lambda s_: print(f"{s_}；{time.time() - t0:.0f}s", flush=True)     # noqa: E731
    from qbreak import paths
    if a.prep:
        print(json.dumps(prep(say), ensure_ascii=False, indent=1, default=str))
        return 0
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    md, js = out_dir / f"{OUT}.md", out_dir / f"{OUT}.json"
    if md.exists() or js.exists():
        raise SystemExit(f"{md.name} / {js.name} 已经存在：只运行一次 → 停")
    res = run(say)
    out_dir.mkdir(parents=True, exist_ok=True)
    js.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)) + "\n",
                  encoding="utf-8")
    md.write_text(report(res), encoding="utf-8")
    print("完成（判定写在 md / json 里）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
