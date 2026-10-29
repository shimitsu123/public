"""kshape_full_study.py — 把 K 线的形状考虑完全（开盘跳空、实体、上影线、下影线）：日 / 周 / 月K 能不能预测之后 1 / 5 / 21 个交易日、
比以前只用「涨跌 / 收在哪儿 / 振幅」的好不好、用来优化现行算法（B4）会不会更好（登记版：规则、代码与登记前个数一起提交，之后不改、只运行一次）。

来由：用户 2026-10-24「K线的尾巴现在在图形分析预测下一个的时候考虑进去了么 要把k线的形态考虑完全」。
照实写：kshape_link_study（9 种形状 = 涨跌 × 收在哪儿）与 kshape_joint_study（每块 z / CLV / rg 三个数）都**没有用开盘价** →
上影线和下影线分不开、实体大小与开盘跳空都不在里面（例：十字星与「低开高走的大阳线」CLV 可以一样）。这次补上；这是看过那两次结果之后的研究 → 三按事后判。
以前与影线有关的（结论都是不改）：现行策略「上影 ÷ 实体 > 3 不买」（只上影、只信号日）；用户的上影陽線（candle_user_test：不成立）；
K 线形态 / kNN 相似形状 / 形状聚类 / K 线机器学习（都不通过）。这次的不同：每块完整的 OHLC（4 个自由度）都进模型，日 / 周 / 月三个周期、各 3 块，
并在同一批行上和 kshape_joint_study 的 29 个特征（JG）直接比。

〇 特征（每只票、每个交易日 t 收盘时；只用到 t 收盘为止的数据；研究行情 = 调整后价；qbreak.kline.ohlcv）
  每块 5 个（p = 前一块收盘、σ = 那一块之前的波动，同 kshape_joint_study：日 20 天 / 周 20 周 / 月 12 月 log 涨跌的标准差，不含这一块）：
    z =（收盘 ÷ p − 1）÷ σ；gap =（开盘 ÷ p − 1）÷ σ；body =（收盘 − 开盘）÷ p ÷ σ；up =（最高 − max(开盘, 收盘)）÷ p ÷ σ；
    lw =（min(开盘, 收盘) − 最低）÷ p ÷ σ   → 开盘 / 最高 / 最低 / 收盘相对前一块收盘全部还原得出来（= K 线形状完全）。
  日K：t、t−1、t−2 各 5 个 = 15；周K / 月K：正在走的这一块（开盘 = 这一块第一天的开盘，最高 / 最低到 t 为止，收盘 = t 的收盘）+ 上一块、上上块
  各 5 个 + 这一块过了几天 ÷ 5 / 21 = 16；合计 47 个（FEATS）。另外每行带 kshape_joint_study 的 29 个特征（OLD），只给对照模型 JG 用；
  76 个都算得出的行才进来（两组模型同一批行）。
一 目标与模型（同 kshape_joint_study：h = 1 / 5 / 21；t+1 开盘买、t+h 收盘卖的涨跌减去同一样本同一天的平均；截到 ±10 / ±20 / ±40 pp；
  每 5 个交易日取 1 天；交叉拟合 E + W → Z / Zx / J / Jx、J + Jx → E / W，6 个样本都是样本外；树 = 同一组 HistGBM 超参数）
  FG = 47 个特征的树（判定对象）；JG = 旧的 29 个特征的树（对照：以前的做法）；FD = 只用日K 的 15 个特征的树；FR = 47 个特征的岭回归（只描述系数占比）。
二 判定（FG × 3 个期限 = 3 个；P_MAX = 0.05 / 3）
  info = 6 个样本平均 IC 都 > 0、合起来（按块 t 检验，同 kshape_joint_study）p < P_MAX、合起来分档差 ≥ 0.15 / 0.30 / 0.60 pp；
  better = 同一批行上 ΔIC = IC(FG) − IC(JG) 合起来 p < P_MAX，且 6 个样本里 ≥ 5 个 > 0（= 加上影线 / 下影线 / 实体 / 跳空真的多出信息）。
  V0「完整 K 线有可用的信息，而且比以前的好」= info ∧ better；V1「有可用的信息，但加上影线等没有多出来」= info ∧ ¬better；
  V2「加上影线等比以前好，但还不够用」= ¬info ∧ better ∧ 6 个样本 IC 都 > 0；V3「方向一致但不够」= 6 个样本 IC 都 > 0；V4「没有信息」= 其余。
三 结合现行 B4（买点过滤；3 个做法；看过 kshape_joint_study 的结果之后设计 → posthoc = True：多一条 V6 Zx；不管二的判定如何都运行）
  FBD / FBW / FBM =「信号日 t 收盘时 FG（h = 1 / 5 / 21）预测的超额在当天同一样本里算得出的票中排后三分之一 → 不开新仓」
  （模型 = 没见过这个样本的那一折；TBF 挡的照旧不买；算不出 → 不挡）；第一关 = research_loop11.stage1(posthoc = True)；
  挡掉的 B4 成交 < 10 笔 →「几乎不触发」；先决条件 = kshape_link_study.prereq（规则指纹、接线核对、B4 重算 = B4_PREP；任一不过 → 停）。
  第一关过了才另行登记第二关（400 次随机挡）；两关都过 =「更好候选」→ 报告给用户、进模拟盘要用户决定。
四 只描述（不参与判定）：① 4 个模型各样本的 IC / 分档差；② FR 系数绝对值按成分（z / gap / body / up / lw / frac）与按周期的占比；
  ③ 经典 K 线形状（日K 今天、上一周、上一月各自）→ 之后的平均超额（日K：1 / 5 日；周K：5 / 21 日；月K：21 日），分三个年代、同号标 ★：
     长上影（up ≥ 2|body| 且 ≥ 一半振幅）、长下影（lw 同样）、十字（|body| ≤ 振幅 10%）、大阳实体（body ≥ 振幅 70% 且 ≥ 1σ）、大阴实体、
     向上跳空（gap ≥ 1σ）、向下跳空（gap ≤ −1σ）；振幅 = up + |body| + lw，长上影 / 长下影 / 十字要振幅 ≥ 1σ；可以同时属于几种；
  ④ B4 实际成交按信号日 FG 预测的三档的胜率 / 每笔。
五 事前预期（运行前写，照实）：上影线 / 下影线 / 跳空多半只是「涨跌 + 收在哪儿」已经有的短期反转的另一种写法 → better 多半不过（约 20%）；
  日K 的 IC 约 +0.01〜+0.02、分档差到不了门槛 → 多半 V3；长下影 / 向下跳空之后 1 日略好（反转）、长上影略差，但幅度 ≤ 0.1〜0.2 pp（比来回成本小）；
  FBD / FBW 会挡掉一部分「大涨收在高位」的突破日 → 账户多半变差；每个做法第一关约 2〜5%。
六 局限：日経225 用今天的成员（幸存者偏差）；Jx 不按当时的成员筛；调整后价（开盘也按同一比例调整，形状不变）；多重检验：二 3 个判断、三 3 个做法、
  四只描述。模拟盘 / 执行器 / 面板 / 策略参数不因这次研究改。
登记前只数个数（--prep；不拟合模型、不算任何收益）：见 var/sim_changes.md 的登记节（与本文件同一次提交）。
用法：python scripts/kshape_full_study.py --prep；--run（只运行一次：输出已经存在就停）。输出：var/out/kshape_full_study.md / .json（只有汇总统计）。非投资建议。
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

import kshape_joint_study as KJ                                              # noqa: E402
import kshape_link_study as KS                                               # noqa: E402

OUT = "kshape_full_study"
COMP = ("z", "gap", "body", "up", "lw")
FEATS = ([f"d_{k}{i}" for i in range(3) for k in COMP]
         + [f"w_{k}{i}" for i in range(3) for k in COMP] + ["w_frac"]
         + [f"m_{k}{i}" for i in range(3) for k in COMP] + ["m_frac"])
OLD = [f"o_{f}" for f in KJ.FEATS]
ALL = FEATS + OLD
HORIZONS = KJ.HORIZONS
CLIP, MIN_SPREAD, MIN_ROWS = KJ.CLIP, KJ.MIN_SPREAD, KJ.MIN_ROWS
MODELS = ("FG", "JG", "FD", "FR")
MODEL_NAME = {"FG": "完整 K 线 日 + 周 + 月（树）", "JG": "以前的 29 个特征（树，对照）", "FD": "完整 K 线 只用日K（树）",
              "FR": "完整 K 线 日 + 周 + 月（线性，只描述）"}
P_MAX = 0.05 / len(HORIZONS)
MIN_BETTER_SAMPLES = 5
VERDICTS = ("完整 K 线有可用的信息，而且比以前的好", "有可用的信息，但加上影线等没有多出来", "加上影线等比以前好，但还不够用",
            "方向一致但不够", "没有信息")
SAMPLES, TRAIN, MODEL_OF, N225_ERAS, POOLS = KS.SAMPLES, KS.TRAIN, KS.MODEL_OF, KS.N225_ERAS, KS.POOLS
B_IDS = ("FBD", "FBW", "FBM")
B_H = {"FBD": 1, "FBW": 5, "FBM": 21}
B_NAME = {"FBD": "完整 K 线预测之后 1 日排后三分之一 → 不买", "FBW": "完整 K 线预测之后 5 日排后三分之一 → 不买",
          "FBM": "完整 K 线预测之后 21 日排后三分之一 → 不买"}
POSTHOC = True
MIN_TRIG = KJ.MIN_TRIG
ERA_GROUPS = KJ.ERA_GROUPS
SHAPES = ("长上影", "长下影", "十字", "大阳实体", "大阴实体", "向上跳空", "向下跳空")
SHAPE_TF = {"d": (0, (1, 5)), "w": (1, (5, 21)), "m": (1, (21,))}         # 周期 → (第几块：日K 今天 / 上一周 / 上一月, 期限)
TF_NAME = {"d": "日K（今天）", "w": "周K（上一周）", "m": "月K（上一月）"}
LONG_TAIL, TAIL_SHARE, DOJI, BIG_BODY, BIG_MIN, GAP_MIN, RANGE_MIN = 2.0, 0.5, 0.1, 0.7, 1.0, 1.0, 1.0


# ───────────────────────── 〇 特征（纯函数；tests/test_kshape_full_study.py） ─────────────────────────
def five(o, h, lo, c, p, s) -> list[np.ndarray]:
    """一块的 5 个数：z / gap / body / up / lw（都 ÷ 前一块收盘 ÷ σ）。"""
    with np.errstate(invalid="ignore", divide="ignore"):
        d = p * s
        return [(c / p - 1) / s, (o / p - 1) / s, (c - o) / d, (h - np.maximum(o, c)) / d, (np.minimum(o, c) - lo) / d]


def daily_feats(o, h, lo, c) -> list[np.ndarray]:
    """日K 15 个：t、t−1、t−2 的 z / gap / body / up / lw。"""
    n = len(c)
    r = np.full(n, np.nan)
    prev = np.full(n, np.nan)
    prev[1:] = c[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        r[1:] = c[1:] / c[:-1] - 1
    sd = KJ._sigma(np.log1p(r), KJ.NVOL["D"])
    v = five(o, h, lo, c, prev, sd)
    return [KJ._shift(x, k) for k in range(3) for x in v]


def coarse_feats(idx: pd.DatetimeIndex, o, h, lo, c, tf: str) -> list[np.ndarray]:
    """周K / 月K 16 个：正在走的这一块（开盘 = 这一块第一天的开盘、最高 / 最低到当天、收盘 = 当天）+ 上一块、上上块的 5 个数 + 过了几天 ÷ 5 / 21。"""
    n = len(c)
    key = idx.to_period("W-FRI" if tf == "W" else "M").asi8
    starts = np.r_[True, key[1:] != key[:-1]] if n else np.zeros(0, bool)
    bid = np.cumsum(starts) - 1
    st = np.flatnonzero(starts)
    end = np.r_[st[1:] - 1, n - 1] if n else np.zeros(0, int)
    bo, bc = o[st], c[end]
    bh = np.maximum.reduceat(h, st) if n else np.zeros(0)
    bl = np.minimum.reduceat(lo, st) if n else np.zeros(0)
    nb = len(st)
    br = np.full(nb, np.nan)
    bprev = np.full(nb, np.nan)
    if nb > 1:
        bprev[1:] = bc[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        br[1:] = bc[1:] / bc[:-1] - 1
    sb = KJ._sigma(np.log1p(br), KJ.NVOL[tf])
    bv = five(bo, bh, bl, bc, bprev, sb)
    cumh = pd.Series(h).groupby(bid).cummax().to_numpy()
    cuml = pd.Series(lo).groupby(bid).cummin().to_numpy()
    cur = five(bo[bid], cumh, cuml, c, bprev[bid], sb[bid])

    def lagb(v, k):
        j = bid - k
        return np.where(j >= 0, v[np.clip(j, 0, None)], np.nan)

    frac = (np.arange(n) - st[bid] + 1) / KJ.FRAC_DEN[tf]
    return cur + [lagb(x, 1) for x in bv] + [lagb(x, 2) for x in bv] + [frac]


def ticker_feats(df: pd.DataFrame) -> dict | None:
    """一只票 → {date, X (n × 76：47 个完整特征 + 以前的 29 个), o, c}。"""
    from qbreak import kline as K
    d = K.ohlcv(df)
    if len(d) < 60:
        return None
    o, h, lo, c = (d[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    cols = daily_feats(o, h, lo, c) + coarse_feats(d.index, o, h, lo, c, "W") + coarse_feats(d.index, o, h, lo, c, "M")
    old = KJ.ticker_feats(df)
    X = np.column_stack(cols + [old["X"][:, j].astype(float) for j in range(len(KJ.FEATS))]).astype(np.float32)
    return {"date": d.index.values.astype("datetime64[ns]"), "X": X, "o": o, "c": c}


def shape_flags(z, gap, body, up, lw) -> dict[str, np.ndarray]:
    """经典 K 线形状（可以同时属于几种）。"""
    z, gap, body, up, lw = (np.asarray(v, float) for v in (z, gap, body, up, lw))
    ab = np.abs(body)
    rg = up + ab + lw
    big = rg >= RANGE_MIN
    with np.errstate(invalid="ignore"):
        return {"长上影": big & (up >= LONG_TAIL * ab) & (up >= TAIL_SHARE * rg),
                "长下影": big & (lw >= LONG_TAIL * ab) & (lw >= TAIL_SHARE * rg),
                "十字": big & (ab <= DOJI * rg),
                "大阳实体": (body >= BIG_BODY * rg) & (body >= BIG_MIN),
                "大阴实体": (-body >= BIG_BODY * rg) & (-body >= BIG_MIN),
                "向上跳空": gap >= GAP_MIN, "向下跳空": gap <= -GAP_MIN}


def cols_of(model: str) -> list[int]:
    if model == "JG":
        return list(range(len(FEATS), len(ALL)))
    if model == "FD":
        return [i for i, f in enumerate(FEATS) if f.startswith("d_")]
    return list(range(len(FEATS)))


def fit_model(model: str, X: np.ndarray, y: np.ndarray, hz: int):
    from qbreak import ml as ML
    yc = np.clip(np.asarray(y, float), -CLIP[hz], CLIP[hz])
    Xs = np.asarray(X, float)[:, cols_of(model)]
    return KJ.Ridge().fit(Xs, yc) if model == "FR" else ML.HistGBM(**KJ.GBM).fit(Xs, yc)


def predict_model(model: str, F, X: np.ndarray) -> np.ndarray:
    return F.predict(np.asarray(X, float)[:, cols_of(model)])


def verdict(each_ic: list, pooled_p, pooled_spread, hz: int, better_p, better_n: int) -> str:
    ic_all = len(each_ic) == len(SAMPLES) and all(v is not None and np.isfinite(v) and v > 0 for v in each_ic)
    info = ic_all and pooled_p is not None and pooled_p < P_MAX and pooled_spread is not None and pooled_spread >= MIN_SPREAD[hz]
    better = better_p is not None and better_p < P_MAX and better_n >= MIN_BETTER_SAMPLES
    if info:
        return VERDICTS[0] if better else VERDICTS[1]
    if better and ic_all:
        return VERDICTS[2]
    return VERDICTS[3] if ic_all else VERDICTS[4]


def comp_share(w: np.ndarray) -> dict:
    """FR 的标准化系数绝对值（47 个，不含截距）→ 按成分与按周期的占比 %。"""
    w = np.abs(np.asarray(w, float))
    tot = w.sum()
    if tot <= 0:
        return {}
    out = {k: float(sum(w[i] for i, f in enumerate(FEATS) if f[2:].rstrip("012") == k) / tot * 100) for k in COMP + ("frac",)}
    out.update({g: float(sum(w[i] for i, f in enumerate(FEATS) if f.startswith(g + "_")) / tot * 100) for g in ("d", "w", "m")})
    return out


# ───────────────────────── 数据 ─────────────────────────
def sample_table(FR: dict, sdays: np.ndarray, window) -> pd.DataFrame:
    a, b = (np.datetime64(pd.Timestamp(x), "ns") for x in window)
    parts = []
    for t, df in FR.items():
        f = ticker_feats(df)
        if f is None:
            continue
        keep = np.isin(f["date"], sdays) & (f["date"] >= a) & np.isfinite(f["X"]).all(1)
        if not keep.any():
            continue
        p = pd.DataFrame(f["X"][keep], columns=ALL)
        p.insert(0, "date", f["date"][keep])
        p.insert(1, "ticker", t)
        for hz in HORIZONS:
            r, e = KJ.targets(f["o"], f["c"], f["date"], hz)
            r = r[keep]
            r[~(e[keep] < b)] = np.nan
            p[f"tg{hz}"] = r
        parts.append(p)
    if not parts:
        return pd.DataFrame(columns=["date", "ticker"] + ALL + [f"tg{hz}" for hz in HORIZONS] + [f"ex{hz}" for hz in HORIZONS])
    X = pd.concat(parts, ignore_index=True)
    for hz in HORIZONS:
        X[f"ex{hz}"] = X[f"tg{hz}"] - X.groupby("date")[f"tg{hz}"].transform("mean")
    return X


def build_tables(W: dict, FR: dict, say=print) -> dict:
    TABS = {}
    for s in SAMPLES:
        TABS[s] = sample_table(FR[s], KJ.sample_days(W, s), KS.window_of(W, s))
        say(f"{s}：{TABS[s]['ticker'].nunique() if len(TABS[s]) else 0} 只、{len(TABS[s])} 行")
    return TABS


# ───────────────────────── 运行 ─────────────────────────
def part_a(TABS: dict, say=print) -> tuple[dict, dict]:
    out: dict = {"horizons": {}, "share": {}, "shapes": shape_table(TABS)}
    FITS: dict = {}
    for hz in HORIZONS:
        ex = f"ex{hz}"
        fits = {}
        for fold, tr in TRAIN.items():
            X = pd.concat([TABS[s] for s in tr], ignore_index=True)
            X = X[np.isfinite(X[ex])]
            for m in MODELS:
                fits[(m, fold)] = fit_model(m, X[ALL].to_numpy(float), X[ex].to_numpy(float), hz)
            say(f"A h={hz} 折 {fold} 训练完（{len(X)} 行）")
        FITS[hz] = fits
        ics: dict = {m: {} for m in MODELS}
        sps: dict = {m: {} for m in MODELS}
        each: dict = {m: {} for m in MODELS}
        for s in SAMPLES:
            X = TABS[s]
            X = X[np.isfinite(X[ex])]
            for m in MODELS:
                pred = predict_model(m, fits[(m, MODEL_OF[s])], X[ALL].to_numpy(float)) if len(X) else np.zeros(0)
                pb = KS.per_block(KJ._key(X["date"]), pred, X[ex], MIN_ROWS)
                ics[m][s], sps[m][s] = pb["ic"], pb["spread"]
                each[m][s] = {"rows": int(len(X)), "days": int(len(pb)), "ic": float(pb["ic"].mean()) if len(pb) else None,
                              "spread": float(pb["spread"].mean()) if len(pb) else None}
        pooled = {}
        for m in MODELS:
            ic_by = pd.concat(ics[m].values()).groupby(level=0).mean()
            sp_by = pd.concat(sps[m].values()).groupby(level=0).mean()
            pooled[m] = {"ic": KJ.block_t(ic_by, hz), "spread": float(sp_by.mean()) if len(sp_by) else None}
        res = {"models": {}}
        for m in MODELS:
            r = {"name": MODEL_NAME[m], "each": each[m], "pooled": pooled[m]}
            if m == "FG":
                d_each, d_all = {}, []
                for s in SAMPLES:
                    d = (ics["FG"][s] - ics["JG"][s]).dropna()
                    d_each[s] = float(d.mean()) if len(d) else None
                    d_all.append(d)
                d_by = pd.concat(d_all).groupby(level=0).mean() if d_all else pd.Series(dtype=float)
                bt = KJ.block_t(d_by, hz)
                npos = sum(1 for v in d_each.values() if v is not None and v > 0)
                r["better"] = {"vs": "JG", "each": d_each, "pooled": bt, "n_pos": npos}
                r["verdict"] = verdict([each["FG"][s]["ic"] for s in SAMPLES], pooled["FG"]["ic"]["p"], pooled["FG"]["spread"], hz, bt["p"], npos)
            res["models"][m] = r
        out["horizons"][hz] = res
        out["share"][hz] = {fold: comp_share(fits[("FR", fold)].w[1:]) for fold in TRAIN}
        say(f"A h={hz} 完成（判定只写在文件里）")
    return out, FITS


def shape_table(TABS: dict) -> list[dict]:
    """只描述 ③：经典 K 线形状 → 之后的平均超额（pp）与行数，分三个年代。"""
    rows = []
    for tf, (k, hzs) in SHAPE_TF.items():
        for hz in hzs:
            T: dict = {}
            for era, ss in ERA_GROUPS.items():
                X = pd.concat([TABS[s] for s in ss], ignore_index=True)
                X = X[np.isfinite(X[f"ex{hz}"])]
                fl = shape_flags(*(X[f"{tf}_{c}{k}"].to_numpy(float) for c in COMP))
                e = X[f"ex{hz}"].to_numpy(float)
                for name, m in fl.items():
                    T.setdefault(name, {})[era] = {"mean": float(e[m].mean()) if m.any() else None, "n": int(m.sum()),
                                                   "share": float(m.mean() * 100) if len(m) else None}
            for name in SHAPES:
                v = [x["mean"] for x in T[name].values() if x["mean"] is not None]
                rows.append({"tf": tf, "hz": hz, "shape": name, "eras": T[name],
                             "same_sign": len(v) == len(ERA_GROUPS) and (all(x > 0 for x in v) or all(x < 0 for x in v))})
    return rows


def score_wide(FR: dict, F, model: str, days: pd.DatetimeIndex, chunk: int = 150) -> pd.DataFrame:
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
        allX = np.concatenate(Xs) if Xs else np.zeros((0, len(ALL)))
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
            SW[(k, s)] = score_wide(FR[s], FITS[B_H[k]][("FG", MODEL_OF[s])], "FG", days)
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
        out["stage1"][k] = R11.stage1(cand, base, other, lenses=None, posthoc=POSTHOC)
        out["verdict"][k] = ("几乎不触发" if trig < MIN_TRIG else
                             ("第一关通过（要另行登记第二关）" if out["stage1"][k]["ok"] else "第一关不过"))
        say(f"B {k} 完成（判定只写在文件里）")
    out["base"] = base
    out["b4_trades"] = {e: int(len(b4tr[e])) for e in N225_ERAS}
    return out


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/kshape_full_study.py", "scripts/kshape_joint_study.py",
                                     "scripts/kshape_link_study.py", "qbreak/kline.py", "qbreak/ml.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def prep(say=print) -> dict:
    import loop9_common as C9
    import trendline_study as TS
    W, FR, tbf, tbf_pool = KJ.load_all(say)
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
    W, FR, tbf, tbf_pool = KJ.load_all(say)
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


def _h(D: dict, hz):
    return D[hz] if hz in D else D[str(hz)]


def report(res: dict) -> str:
    A, B = res["A"], res["B"]
    L = [f"# 把 K 线的形状考虑完全（跳空 / 实体 / 上影线 / 下影线）：能不能预测之后 1 / 5 / 21 日、比以前的好不好（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         "规则见 scripts/kshape_full_study.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件：规则指纹 {res['prereq'].get('fingerprint')}、"
         f"B4 重算 = 登记前 {all(res['prereq'].get(e, {}).get('same_prep') for e in N225_ERAS)}、接线核对 {all(res['prereq'].get(e, {}).get('wired') for e in N225_ERAS)}；"
         f"用时 {res['elapsed_s']} s。", "", "## 一 / 二 判定（FG = 完整 K 线；6 个样本都是样本外）", "",
         f"| 期限 | 判定 | 合起来 IC | p（要 < {P_MAX:.4f}） | 分档差 pp（门槛） | 比以前（JG）多的 IC | p | 样本里多的个数 |", "|---|---|---|---|---|---|---|---|"]
    for hz in HORIZONS:
        r = _h(A["horizons"], hz)["models"]["FG"]
        po, bt = r["pooled"], r["better"]
        L.append(f"| {hz} 日 | **{r['verdict']}** | {_f(po['ic']['mean'], '{:+.4f}')}（{po['ic']['n']} 块） | {_f(po['ic']['p'], '{:.4f}')} | "
                 f"{_f(po['spread'])}（{MIN_SPREAD[hz]}） | {_f(bt['pooled']['mean'], '{:+.4f}')} | {_f(bt['pooled']['p'], '{:.4f}')} | {bt['n_pos']} / 6 |")
    L += ["", "4 个模型各样本（平均 IC / 分档差 pp）：", ""]
    for hz in HORIZONS:
        for m in MODELS:
            r = _h(A["horizons"], hz)["models"][m]
            L.append(f"- {hz} 日 {m}（{r['name']}；合起来 IC {_f(r['pooled']['ic']['mean'], '{:+.4f}')}、分档差 {_f(r['pooled']['spread'])}）："
                     + "；".join(f"{s} {_f(x['ic'], '{:+.3f}')} / {_f(x['spread'], '{:+.2f}')}" for s, x in r["each"].items()))
    L += ["", "FR（线性）系数绝对值的占比 %（折 I / 折 II）：", ""]
    for hz in HORIZONS:
        sh = _h(A["share"], hz)
        L.append(f"- {hz} 日：" + "；".join(f"{k} " + " / ".join(_f(sh[f].get(k), '{:.0f}') for f in TRAIN) for k in COMP + ("frac", "d", "w", "m")))
    L += ["", "## 三 结合现行 B4（买点过滤；第一关 = research_loop11.stage1，posthoc = True）", "",
          "| 做法 | 判定 | 挡掉的 B4 成交（Z + E + J） | Calmar 差 Z / E / J | 合起来胜率差 pp | 每笔差 pp | 池子 W / Jx / Zx 胜率差 pp |", "|---|---|---|---|---|---|---|"]
    for k in B_IDS:
        s1 = B["stage1"][k]
        d = s1.get("d") or {}
        oth = B["other"][k]
        L.append(f"| {k} {B_NAME[k]} | **{B['verdict'][k]}** | {B['trig'][k]} | "
                 + " / ".join(_f((d.get(e) if isinstance(d, dict) else None)) for e in N225_ERAS)
                 + f" | {_f(s1.get('dwin'), '{:+.2f}')} | {_f(s1.get('dmean'), '{:+.2f}')} | "
                 + " / ".join(_f((oth.get(s) or {}).get("dwin"), "{:+.2f}") for s in POOLS) + " |")
    L += ["", "B4 实际成交按信号日 FG 预测的三档（只描述；笔数 / 胜率 % / 每笔 %）：", ""]
    for k in B_IDS:
        L.append(f"- {k}：" + "；".join(f"{e} " + "、".join(
            f"{lab} {v['n']} 笔" + (f" {v['win']:.0f}% / {v['mean']:+.2f}%" if v.get("n") else "")
            for lab, v in B["describe"][k][e].items()) for e in N225_ERAS))
    L += ["", "## 四 只描述：经典 K 线形状 → 之后的平均超额 pp（行数；占全部行 %）；★ = 三个年代同号", "",
          "| 周期 | 之后 | 形状 | " + " | ".join(ERA_GROUPS) + " |", "|---|---|---|" + "---|" * len(ERA_GROUPS)]
    for r in A["shapes"]:
        L.append(f"| {TF_NAME[r['tf']]} | {r['hz']} 日 | {'★ ' if r['same_sign'] else ''}{r['shape']} | "
                 + " | ".join((f"{_f(r['eras'][e]['mean'], '{:+.2f}')}（{r['eras'][e]['n']}；{_f(r['eras'][e]['share'], '{:.1f}')}%）"
                               if e in r["eras"] else "—") for e in ERA_GROUPS) + " |")
    L += ["", "只研究，不改模拟盘 / 执行器 / 面板 / 策略参数。非投资建议。"]
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
