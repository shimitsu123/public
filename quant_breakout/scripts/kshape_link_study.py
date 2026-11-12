"""kshape_link_study.py — K 线块图形之间的关联预测：前几块日 / 周 / 月K 的形状能不能预测下一块的形状与涨跌、
用来优化现行算法（B4）会不会更好（登记版：规则、代码与登记前个数一起提交，之后不改、只运行一次）。

来由：用户 2026-10-23「做图形之间的关联预测 比如知道哪几个K线块图形可以预测以后日 周 月块的形状 从而进行优化现行的算法」。
以前相关的（结论都是不改）：K 线形态 / 上影陽線（candle_*、candle_user_test）、缩量押し目 C1〜C5、起涨 / 起跌点 × 日 / 周 / 月线图形
（turn_shape_*：认得出「现在是不是新高 / 新低」，认不出之后会不会转）、结合 B3 的 TBF（= 现行 B4 的一部分）/ TBR / TXF / TXR、
图形轮动（shape_rotation_study：形状类型的月度惯性没有信息）、趋势线（trendline_*）、月K 往上 + 日K / 周K 往下（month_up_dip_study）、
多周期 R1（mtf_study）、W2 × 日 / 周 / 月线的量（w2mtf_study）。
**没测过的**：一块一块的 K 线形状序列 →「下一块」的形状（条件分布）与涨跌；同周期（前 3 块）、跨周期（日 + 周 + 月各最近 1 块）、
细的块预测粗的块（最后 3 个日K → 下一周、最后 3 个周K → 下一月）。

〇 K 线块与形状（qbreak.kline.bars = 操作面板同一份日K / 周K / 月K；研究行情 = 调整后价；只用到那一块收盘为止的数据）
  每一块：涨跌 r = 收盘 ÷ 上一块收盘 − 1；波动 σ = 前 N 块（不含这一块）log 涨跌的标准差（N：日 20、周 20、月 12；不够 → 这一块没有形状）；
  方向：z = r ÷ σ > +0.5 → 涨（U）、< −0.5 → 跌（D）、其余 → 平（F）；
  收在哪儿：CLV = (收盘 − 最低) ÷ (最高 − 最低)（最高 = 最低 → 0.5）≥ 2/3 → 高（H）、≤ 1/3 → 低（L）、其余 → 中（M）；
  形状 = 方向 × 收在哪儿 = 9 种（编号 = 3 × 方向 + 位置；方向 跌 0 / 平 1 / 涨 2，位置 低 0 / 中 1 / 高 2）。
  门槛（0.5σ、1/3、N）在看任何收益之前定，不调。
一 模型（「哪几块 → 下一块」；8 个，事先列全）
  目标 = 同一只票、目标周期的下一块：形状（9 种）与可成交的涨跌 rx = 下一块收盘 ÷ 下一块开盘 − 1（%；下一块第一个交易日开盘买、
  最后一个交易日收盘卖）；超额 = 减去同一样本里同一块（日 = 同一天、周 = 同一周、月 = 同一月）全部票的等权平均。
  周 / 月：下一块要是紧接着的那一周 / 那一月（中间整周 / 整月没有成交 → 这一行不算）。
  上下文（都是已经走完的块；第 1 个最重要，退回时按 1 → 2 → 3 的顺序）：
  - D-SC：日K 最近 3 块；D-XC：日K 最近 1 块 + 那天为止最近走完的周K、月K 各 1 块。
  - W-SC：周K 最近 3 块；W-XC：周K 最近 1 块 + 那周为止最近走完的月K + 那周最后一天的日K；W-FD：那周最后 3 个日K（细的块 → 下一周）。
  - M-SC：月K 最近 3 块；M-XC：月K 最近 1 块 + 那月最后一周的周K + 那月最后一天的日K；M-FW：那月最后 3 个周K（细的块 → 下一月）。
  「那天为止最近走完的周K / 月K」= 日期 ≤ 那一天的最后一根（周K / 月K 的日期 = 那周 / 那月最后一个交易日）。
  估计 = 退回平滑（back-off）：p0 = 训练里 9 种的频率（各 +1）；p_k(y | 前 k 个) = (n_k(·, y) + α p_{k−1}) ÷ (n_k + α)，α = 30；
  预测的超额 m_k 同样（m0 = 训练里的平均超额）；用 p_3 / m_3。
  交叉拟合（每个样本都用没见过它的模型）：模型 I = 用 E + W（2006-10〜2016-09）训练 → 预测 Z、Zx、J、Jx；模型 II = 用 J + Jx（2017-01〜2026-09）
  训练 → 预测 E、W。样本 = trendline_study 的 6 个：日経225 Z / E / J + 池子 W / Jx / Zx（同那里的行情、窗口与去掉的票）；
  这一块的收盘日 ≥ 窗口起点、下一块的收盘日 < 窗口终点。
二 判定（每个模型一个，8 个；6 个样本都是样本外）
  形状：skill = 1 − 对数损失（模型）÷ 对数损失（只用训练里的 9 种频率）（%）。
  涨跌：每一块（日 / 周 / 月）横截面上「预测的超额」与「实际的超额」的秩相关 IC（那一块 ≥ 20 只、预测不全一样）；
       分档差 = 预测排前三分之一 − 后三分之一的实际超额平均（pp）；合起来 = 同一块在几个样本里都有 → 先取平均，再按块做 t 检验（单侧、正态近似）。
  ①「涨跌有可用的信息」：6 个样本 IC 都 > 0，合起来 p < 0.05 / 8，且合起来分档差 ≥ 门槛（日 0.15 / 周 0.30 / 月 0.60 pp
     —— 约为来回手续费 0.15% 的 1 / 2 / 4 倍）。
  ②「形状能预测一点，涨跌没有可用的信息」：① 不过，6 个样本 skill 都 > 0 且合起来 ≥ 1.0%。
  ③「涨跌方向一致但不够」：①② 都不过，6 个样本 IC 都 > 0。
  ④「没有信息」：其余。
三 结合现行 B4（买点过滤；3 个做法；看到任何形状结果之前设计 → posthoc = False；不管一 / 二的判定如何都运行）
  KXD / KXW / KXM「XC 模型预测下一块（日 / 周 / 月）的超额在当天排后三分之一 → 不开新仓」：
  信号日 t 收盘时，用 t 为止走完的块（日K = t 这一天；周K / 月K = 日期 ≤ t 的最后一根，其上下文同一的 XC）和没见过这个样本的模型
  （Z / J ← 模型 I、E ← 模型 II；池子 W ← II、Jx / Zx ← I）算预测的超额；同一天同一样本里算得出的票里百分位 ≤ 1/3 → 挡
  （那个（票, 信号日）不开新仓，名额留给下一个候选、钱留在核心；TBF 挡的照旧不买；算不出 → 不挡）。
  周 / 月：t 不是那周 / 那月最后一天时，「下一块」= 正在走的这一周 / 这一月 —— 用的仍然只是 t 之前走完的块。
  基准 = 同一次运行里重算的 B4（B3 + TBF；trendline_study.prereq 的 base）。照实写：2026-10-12 分红修正（064f328）重建研究缓存后，
  B4 已不等于 turn_shape_combo 结果文件里的参照（那一节写明「各做法都和同一次运行的基准比」）→ 先决条件 = 规则指纹 1241753c8f2529c6、
  接线核对（trendline_study.prereq 的 wired）、B4 重算与登记前 --prep 记下的 B4_PREP 相同（笔数、胜率相同、Calmar 差 ≤ 1e-6 = 同一份数据）；
  任一不过 → 停。第一关 / 池子 = trendline_study 二（research_loop11.stage1，posthoc = False → V6 Zx 只描述；
  池子 = B4 会买的信号的假想单笔：保留的 vs 全部）。
  B4 实际成交里被挡的 Z + E + J 合计 < 10 笔 →「几乎不触发」。
  第二关（第一关过了才做；另行登记后只运行一次）：同 trendline_study（按实际挡掉的比例随机挡 400 次，严格大于最大值）。
  两关都过 =「更好候选」→ 报告给用户；进模拟盘 / 执行器要用户决定（不自动改）。
四 只描述（不参与判定）：① 9 × 9 转移表（上一块 → 下一块的形状；全部样本合起来，与基础频率之比）；
  ②「哪几个图形」：SC 模型的前 2 块（81 种）里，在一折训练里出现 ≥ 300 次、下一块平均超额最高 / 最低的各 5 种 → 它们在另一折的平均超额与次数
  （I → II、II → I 两个方向）；③ 各模型猜方向（涨 / 平 / 跌）的命中率 vs 只猜最多的那种；④ 收盘到收盘（含跳空）的 IC；
  ⑤ B4 实际成交按信号日 XC 预测的三档（后 / 中 / 前三分之一）的胜率 / 每笔。
五 事前预期（运行前写，照实）：日本个股有短期反转（跌多的第二天 / 下一周略好）→ D / W 的 IC 多半略 > 0，
  但扣开盘跳空后（rx 从下一块开盘算）分档差多半不到门槛 →「方向一致但不够」或「没有信息」；月K 层面形状几乎没有信息；
  skill 多半 > 0 但 < 1%（只是波动大小的聚集）。B：突破日多半是「大涨收在高位」的日K → 日K 模型若学到反转，KXD 会挡掉不少突破、
  账户变差；KXW / KXM 挡的是随机的三分之一左右 → 每笔接近不变。每个做法第一关约 2〜5%、两关都过约 1%。
六 局限：日経225 用今天的成员（幸存者偏差）；Jx 不按当时的成员筛；调整后价；9 种形状是粗分（换分法结论可能不同）；
  多重检验：一 / 二 8 个判断（① 用 0.05 / 8）、三 3 个做法。模拟盘 / 执行器不因这次研究改。非投资建议。
登记前只数个数（--prep；不拟合模型、不算任何收益）：见 var/sim_changes.md 的登记节（与本文件同一次提交）。
用法：python scripts/kshape_link_study.py --prep（载入 + 先决条件 + 只数个数）；--run（只运行一次：输出已经存在就停）。
输出：var/out/kshape_link_study.md / .json（只有汇总统计，没有个股名单）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = "kshape_link_study"
SCALES = ("D", "W", "M")
NVOL = {"D": 20, "W": 20, "M": 12}
DIR_Z = 0.5
POS_LO, POS_HI = 1 / 3, 2 / 3
NCLS = 9
DIR_NAME = ("跌", "平", "涨")
POS_NAME = ("收在低位", "收在中间", "收在高位")
ALPHA = 30.0
MODELS = ("D-SC", "D-XC", "W-SC", "W-XC", "W-FD", "M-SC", "M-XC", "M-FW")
MODEL_NAME = {"D-SC": "日K 最近 3 块 → 下一个日K", "D-XC": "日K + 周K + 月K 各最近 1 块 → 下一个日K",
              "W-SC": "周K 最近 3 块 → 下一个周K", "W-XC": "周K + 月K + 日K 各最近 1 块 → 下一个周K",
              "W-FD": "那周最后 3 个日K → 下一个周K", "M-SC": "月K 最近 3 块 → 下一个月K",
              "M-XC": "月K + 周K + 日K 各最近 1 块 → 下一个月K", "M-FW": "那月最后 3 个周K → 下一个月K"}
MIN_ROWS = 20
MIN_SPREAD = {"D": 0.15, "W": 0.30, "M": 0.60}
P_MAX = 0.05 / len(MODELS)
MIN_SKILL = 1.0
VERDICTS = ("涨跌有可用的信息", "形状能预测一点，涨跌没有可用的信息", "涨跌方向一致但不够", "没有信息")
SAMPLES = ("Z", "E", "J", "W", "Jx", "Zx")
TRAIN = {"I": ("E", "W"), "II": ("J", "Jx")}
MODEL_OF = {"Z": "I", "Zx": "I", "J": "I", "Jx": "I", "E": "II", "W": "II"}
B_IDS = ("KXD", "KXW", "KXM")
B_MODEL = {"KXD": "D-XC", "KXW": "W-XC", "KXM": "M-XC"}
B_NAME = {"KXD": "日K + 周K + 月K 预测下一个日K 排后三分之一 → 不买", "KXW": "预测下一个周K 排后三分之一 → 不买",
          "KXM": "预测下一个月K 排后三分之一 → 不买"}
CUT = 1 / 3
MIN_TRIG = 10
TOP_MIN_N = 300
TOP_K = 5
N225_ERAS = ("Z", "E", "J")
POOLS = ("W", "Jx", "Zx")
FP = "1241753c8f2529c6"                                                       # B4 = B3 + TBF 的模拟盘规则指纹
B4_PREP = {"Z": {"n": 27, "win": 77.8, "calmar": 1.186}, "E": {"n": 39, "win": 43.6, "calmar": 0.664},   # 登记前 --prep（2026-10-23）重算的 B4
           "J": {"n": 57, "win": 50.9, "calmar": 0.676}}
B4_PREP_TOL = 1e-6


# ───────────────────────── 〇 形状（纯函数；tests/test_kshape_link_study.py） ─────────────────────────
def shape_codes(b: pd.DataFrame, n: int) -> np.ndarray:
    """一只票某个周期的 K 线（升序）→ 每块的形状编号 0〜8（算不出 → −1）。"""
    c = b["Close"].to_numpy(float)
    h, lo = b["High"].to_numpy(float), b["Low"].to_numpy(float)
    r = np.full(len(c), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r[1:] = c[1:] / c[:-1] - 1
        lr = np.log1p(r)
    sig = pd.Series(lr).rolling(n, min_periods=n).std(ddof=1).shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        z = r / sig
        rng = h - lo
        clv = np.where(rng > 0, (c - lo) / np.where(rng > 0, rng, 1.0), 0.5)
    d = np.where(z > DIR_Z, 2, np.where(z < -DIR_Z, 0, 1))
    p = np.where(clv >= POS_HI, 2, np.where(clv <= POS_LO, 0, 1))
    ok = np.isfinite(z) & np.isfinite(sig) & (sig > 0) & np.isfinite(clv)
    return np.where(ok, 3 * d + p, -1).astype(np.int8)


def shape_name(code: int) -> str:
    return f"{DIR_NAME[code // 3]}·{POS_NAME[code % 3]}" if 0 <= code < NCLS else "—"


def _key(idx: pd.DatetimeIndex, tf: str) -> np.ndarray:
    """块的编号（同一样本里横截面对齐用）：日 = 日期（天数）、周 = W-FRI 周期序号、月 = 月序号。"""
    if tf == "D":
        return (idx.values.astype("datetime64[D]").astype(np.int64))
    return idx.to_period("W-FRI" if tf == "W" else "M").asi8.astype(np.int64)


def ticker_blocks(df: pd.DataFrame) -> dict | None:
    """一只票的日线 → 三个周期的块表 {tf: {date, key, code, rx, rr, y, nkey, ndate}}（rx / rr / y = 下一块；没有 → NaN / −1）。"""
    from qbreak import kline as K
    d = K.ohlcv(df)
    if len(d) < 60:
        return None
    out = {}
    for tf in SCALES:
        b = K.bars(d, tf)
        code = shape_codes(b, NVOL[tf])
        o, c = b["Open"].to_numpy(float), b["Close"].to_numpy(float)
        key = _key(b.index, tf)
        n = len(b)
        rx, rr = np.full(n, np.nan), np.full(n, np.nan)
        y = np.full(n, -1, np.int8)
        nkey = np.full(n, -1, np.int64)
        ndate = np.full(n, np.datetime64("NaT"), "datetime64[ns]")
        if n > 1:
            with np.errstate(invalid="ignore", divide="ignore"):
                rx[:-1] = (c[1:] / o[1:] - 1) * 100
                rr[:-1] = (c[1:] / c[:-1] - 1) * 100
            y[:-1] = code[1:]
            nkey[:-1] = key[1:]
            ndate[:-1] = b.index.values[1:]
            if tf != "D":                                                     # 下一块要紧接着（中间整周 / 整月没有成交 → 不算）
                gap = np.r_[key[1:] - key[:-1] != 1, True]
                rx[gap], rr[gap], y[gap] = np.nan, np.nan, -1
        out[tf] = {"date": b.index.values.astype("datetime64[ns]"), "key": key, "code": code, "rx": rx, "rr": rr, "y": y,
                   "nkey": nkey, "ndate": ndate}
    return out


def last_le(dates: np.ndarray, at: np.ndarray) -> np.ndarray:
    """at 里每个日期 → dates（升序）里 ≤ 它的最后一个的位置（没有 → −1）。"""
    return np.searchsorted(dates, at, side="right") - 1


def _pick(code: np.ndarray, i: np.ndarray) -> np.ndarray:
    return np.where(i >= 0, code[np.clip(i, 0, None)], -1).astype(np.int8) if len(code) else np.full(len(i), -1, np.int8)


def contexts(B: dict, model: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """一只票的块表 → 模型 model 在目标周期每一块上的上下文 (c1, c2, c3)（−1 = 缺）。"""
    tf, kind = model[0], model[2:]
    T = B[tf]
    n = len(T["code"])
    idx = np.arange(n)
    if kind == "SC":
        code = T["code"]
        return code, _pick(code, idx - 1), _pick(code, idx - 2)
    if kind == "XC":
        other = {"D": ("W", "M"), "W": ("M", "D"), "M": ("W", "D")}[tf]
        o1, o2 = (_pick(B[o]["code"], last_le(B[o]["date"], T["date"])) for o in other)
        return T["code"], o1, o2
    fine = {"FD": "D", "FW": "W"}[kind]
    j = last_le(B[fine]["date"], T["date"])
    fc = B[fine]["code"]
    return _pick(fc, j), _pick(fc, j - 1), _pick(fc, j - 2)


def model_rows(B: dict, model: str) -> pd.DataFrame:
    """模型 model 的样本行（这只票）：date / key（下一块）/ c1〜c3 / y / rx / rr（上下文全有的块；下一块可以没有 = 只用来打分）。"""
    T = B[model[0]]
    c1, c2, c3 = contexts(B, model)
    ok = (c1 >= 0) & (c2 >= 0) & (c3 >= 0)
    return pd.DataFrame({"date": T["date"][ok], "ndate": T["ndate"][ok], "key": T["nkey"][ok], "c1": c1[ok], "c2": c2[ok],
                         "c3": c3[ok], "y": T["y"][ok], "rx": T["rx"][ok], "rr": T["rr"][ok]})


# ───────────────────────── 一 模型（退回平滑） ─────────────────────────
def _k3(c1, c2, c3) -> np.ndarray:
    return (np.asarray(c1, np.int64) * NCLS + np.asarray(c2, np.int64)) * NCLS + np.asarray(c3, np.int64)


def fit(c1, c2, c3, y, ex, alpha: float = ALPHA) -> dict:
    """训练 → {p0 (9), p (729 × 9), m0, m (729), n1 / n2 / n3（各层次数）, s2（前 2 块的超额合计）}。y < 0 的行不进形状；ex 非有限的不进超额。"""
    c1, c2, c3, y, ex = (np.asarray(v) for v in (c1, c2, c3, y, ex))
    k1 = c1.astype(np.int64)
    k2 = k1 * NCLS + c2.astype(np.int64)
    k3 = k2 * NCLS + c3.astype(np.int64)
    fy = y >= 0
    p0 = np.bincount(y[fy].astype(np.int64), minlength=NCLS).astype(float) + 1.0
    p0 /= p0.sum()
    P = p0
    for lvl, k in ((1, k1), (2, k2), (3, k3)):
        size = NCLS ** lvl
        N = np.bincount(k[fy] * NCLS + y[fy].astype(np.int64), minlength=size * NCLS).reshape(size, NCLS).astype(float)
        parent = P if lvl == 1 else P[np.arange(size) // NCLS]
        prior = np.broadcast_to(parent, (size, NCLS)) if lvl == 1 else parent
        P = (N + alpha * prior) / (N.sum(1, keepdims=True) + alpha)
    fe = np.isfinite(ex.astype(float))
    exf = ex.astype(float)[fe]
    m0 = float(exf.mean()) if len(exf) else 0.0
    M = np.array([m0])
    cnt, sums = {}, {}
    for lvl, k in ((1, k1), (2, k2), (3, k3)):
        size = NCLS ** lvl
        C = np.bincount(k[fe], minlength=size).astype(float)
        S = np.bincount(k[fe], weights=exf, minlength=size)
        parent = np.full(size, m0) if lvl == 1 else M[np.arange(size) // NCLS]
        M = (S + alpha * parent) / (C + alpha)
        cnt[lvl], sums[lvl] = C, S
    return {"p0": p0, "p": P, "m0": m0, "m": M, "n1": cnt[1], "n2": cnt[2], "n3": cnt[3], "s2": sums[2]}


def predict(F: dict, c1, c2, c3) -> tuple[np.ndarray, np.ndarray]:
    """→ (9 种的概率 n × 9, 预测的超额 n)。"""
    k = _k3(c1, c2, c3)
    return F["p"][k], F["m"][k]


def log_loss_bits(p: np.ndarray, y: np.ndarray) -> float:
    y = np.asarray(y, np.int64)
    return float(-np.mean(np.log2(np.clip(p[np.arange(len(y)), y], 1e-12, None)))) if len(y) else float("nan")


def per_block(key, pred, ex, min_n: int = MIN_ROWS) -> pd.DataFrame:
    """每一块（key）横截面：IC（秩相关）与分档差（前三分之一 − 后三分之一的实际超额平均）；≥ min_n 只、预测不全一样的块。"""
    d = pd.DataFrame({"k": np.asarray(key), "m": np.asarray(pred, float), "e": np.asarray(ex, float)})
    d = d[np.isfinite(d["m"]) & np.isfinite(d["e"])]
    if not len(d):
        return pd.DataFrame(columns=["ic", "spread", "n"])
    g = d.groupby("k")
    d = d.assign(n=g["m"].transform("size"), rm=g["m"].rank(), re=g["e"].rank(), q=g["m"].rank(pct=True))
    d = d[d["n"] >= min_n]
    if not len(d):
        return pd.DataFrame(columns=["ic", "spread", "n"])
    g = d.groupby("k")
    a = d["rm"] - g["rm"].transform("mean")
    b = d["re"] - g["re"].transform("mean")
    cov = (a * b).groupby(d["k"]).sum()
    va = (a * a).groupby(d["k"]).sum()
    vb = (b * b).groupby(d["k"]).sum()
    good = (va > 0) & (vb > 0)
    ic = (cov[good] / np.sqrt(va[good] * vb[good]))
    top = d[d["q"] > POS_HI].groupby("k")["e"].mean()
    bot = d[d["q"] <= POS_LO].groupby("k")["e"].mean()
    out = pd.DataFrame({"ic": ic})
    out["spread"] = (top - bot).reindex(out.index)
    out["n"] = g["m"].size().reindex(out.index)
    return out


def t_one_sided(x) -> dict:
    """平均 > 0 的单侧 t 检验（正态近似）。"""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3 or x.std(ddof=1) == 0:
        return {"n": int(n), "mean": float(x.mean()) if n else None, "t": None, "p": None}
    t = float(x.mean() / (x.std(ddof=1) / math.sqrt(n)))
    return {"n": int(n), "mean": float(x.mean()), "t": t, "p": 0.5 * math.erfc(t / math.sqrt(2))}


def verdict(each_ic: list, each_skill: list, pooled_p, pooled_spread, pooled_skill, tf: str) -> str:
    """二的判定。"""
    ic_all = len(each_ic) == len(SAMPLES) and all(v is not None and np.isfinite(v) and v > 0 for v in each_ic)
    sk_all = len(each_skill) == len(SAMPLES) and all(v is not None and np.isfinite(v) and v > 0 for v in each_skill)
    if ic_all and pooled_p is not None and pooled_p < P_MAX and pooled_spread is not None and pooled_spread >= MIN_SPREAD[tf]:
        return VERDICTS[0]
    if sk_all and pooled_skill is not None and pooled_skill >= MIN_SKILL:
        return VERDICTS[1]
    if ic_all:
        return VERDICTS[2]
    return VERDICTS[3]


# ───────────────────────── 三 打分（结合 B4 用） ─────────────────────────
def daily_scores(B: dict, model: str, F: dict, days: np.ndarray) -> np.ndarray:
    """一只票：每个交易日 t（days，升序）收盘时 XC 模型的预测超额 = 日期 ≤ t 的最后一块（目标周期）的上下文 → m（缺 → NaN）。"""
    T = B[model[0]]
    c1, c2, c3 = contexts(B, model)
    ok = (c1 >= 0) & (c2 >= 0) & (c3 >= 0)
    m = np.full(len(c1), np.nan)
    if ok.any():
        m[ok] = predict(F, c1[ok], c2[ok], c3[ok])[1]
    i = last_le(T["date"], days)
    out = np.where(i >= 0, m[np.clip(i, 0, None)], np.nan) if len(m) else np.full(len(days), np.nan)
    if model[0] == "D":                                                       # 日K：只用 t 这一天自己的块（停牌没有这一天 → 不打分）
        same = (i >= 0) & (T["date"][np.clip(i, 0, None)] == days) if len(m) else np.zeros(len(days), bool)
        out = np.where(same, out, np.nan)
    return out


def block_flags(S: pd.DataFrame, cut: float = CUT) -> pd.DataFrame:
    """日期 × 票的预测超额 → 当天百分位 ≤ cut 的为 True（算不出 → False）。"""
    q = S.rank(axis=1, pct=True)
    return (q <= cut) & S.notna()


def lookup_wide(Fl: pd.DataFrame, tickers, dates) -> np.ndarray:
    out = np.zeros(len(tickers), bool)
    cols = {t: j for j, t in enumerate(Fl.columns)}
    di = Fl.index.get_indexer(pd.to_datetime(np.asarray(dates)))
    V = Fl.to_numpy(bool)
    for n, (t, i) in enumerate(zip(tickers, di)):
        j = cols.get(str(t))
        if j is not None and i >= 0:
            out[n] = V[i, j]
    return out


def tercile_of(Sw: pd.DataFrame, tickers, dates) -> np.ndarray:
    """（票, 日）的当天百分位 → 0 后 / 1 中 / 2 前三分之一（算不出 → −1）。"""
    q = Sw.rank(axis=1, pct=True)
    cols = {t: j for j, t in enumerate(q.columns)}
    di = q.index.get_indexer(pd.to_datetime(np.asarray(dates)))
    V = q.to_numpy(float)
    out = np.full(len(tickers), -1, np.int8)
    for n, (t, i) in enumerate(zip(tickers, di)):
        j = cols.get(str(t))
        if j is not None and i >= 0 and np.isfinite(V[i, j]):
            v = V[i, j]
            out[n] = 0 if v <= POS_LO else (2 if v > POS_HI else 1)
    return out


# ───────────────────────── 数据 ─────────────────────────
def sample_frames(W: dict) -> dict:
    """6 个样本的 {票: 日线}（trendline_study 同一份：Jx = J2 里不在日経225（J）的票；去掉核心 ETF）。"""
    import trendline_study as TS
    n225_j = set(W["SM"]["J"]["fa"])
    out = {}
    for s in SAMPLES:
        fa = W["SM"][TS.SM_KEY[s]]["fa"]
        out[s] = {t: fa[t] for t in sorted(fa)
                  if t.endswith(".T") and t not in TS.STOCK_SKIP and not (s == "Jx" and t in n225_j)}
    return out


def window_of(W: dict, s: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    import trendline_study as TS
    e = TS.WIN_ERA[s]
    return TS._win(*W["ctx"][e]["windows"][e])


def build_blocks(FR: dict, say=print) -> dict:
    t0 = time.time()
    out = {}
    for s in SAMPLES:
        out[s] = {}
        for t, df in FR[s].items():
            b = ticker_blocks(df)
            if b is not None:
                out[s][t] = b
        say(f"{s}：{len(out[s])} 只票的块；{time.time() - t0:.0f}s")
    return out


def sample_table(BL: dict, model: str, window) -> pd.DataFrame:
    """一个样本、一个模型的行（这一块的收盘日 ≥ 窗口起点、下一块的收盘日 < 窗口终点）+ 超额（同一块横截面去均值）。"""
    a, b = window
    parts = []
    for t, B in BL.items():
        r = model_rows(B, model)
        if len(r):
            parts.append(r)
    if not parts:
        return pd.DataFrame(columns=["date", "ndate", "key", "c1", "c2", "c3", "y", "rx", "rr", "ex", "exr"])
    X = pd.concat(parts, ignore_index=True)
    X = X[(X["date"] >= a) & X["ndate"].notna() & (X["ndate"] < b) & (X["y"] >= 0)].reset_index(drop=True)
    g = X.groupby("key")
    X["ex"] = X["rx"] - g["rx"].transform("mean")
    X["exr"] = X["rr"] - g["rr"].transform("mean")
    return X


def count_rows(BL: dict, model: str, window) -> int:
    """--prep：样本行数（上下文全有、下一块在窗口内；不算收益）。"""
    a, b = window
    n = 0
    for B in BL.values():
        r = model_rows(B, model)
        n += int(((r["date"] >= a) & r["ndate"].notna() & (r["ndate"] < b) & (r["y"] >= 0)).sum())
    return n


# ───────────────────────── 运行 ─────────────────────────
def part_a(BLS: dict, W: dict, say=print) -> tuple[dict, dict]:
    """一 / 二 + 只描述 ①〜④。返回 (结果, 模型 {model: {I: fit, II: fit}})。"""
    out: dict = {"models": {}, "transition": {}, "top": {}}
    FITS: dict = {}
    for model in MODELS:
        tf = model[0]
        tabs = {s: sample_table(BLS[s], model, window_of(W, s)) for s in SAMPLES}
        fits = {}
        for fold, tr in TRAIN.items():
            X = pd.concat([tabs[s] for s in tr], ignore_index=True)
            fits[fold] = fit(X["c1"], X["c2"], X["c3"], X["y"], X["ex"])
        FITS[model] = fits
        r = {"name": MODEL_NAME[model], "each": {}}
        pool_ic, pool_sp, pool_icr = [], [], []
        ll_m = ll_b = n_ll = 0.0
        for s in SAMPLES:
            X = tabs[s]
            F = fits[MODEL_OF[s]]
            p, m = predict(F, X["c1"], X["c2"], X["c3"])
            y = X["y"].to_numpy(np.int64)
            lm, lb = log_loss_bits(p, y), log_loss_bits(np.broadcast_to(F["p0"], p.shape), y)
            pb = per_block(X["key"], m, X["ex"])
            pr = per_block(X["key"], m, X["exr"])
            dir_hit = float(np.mean(p.reshape(-1, 3, 3).sum(2).argmax(1) == y // 3) * 100) if len(y) else None
            base_dir = int(F["p0"].reshape(3, 3).sum(1).argmax())
            r["each"][s] = {"rows": int(len(X)), "blocks": int(len(pb)), "ic": float(pb["ic"].mean()) if len(pb) else None,
                            "spread": float(pb["spread"].mean()) if len(pb) else None,
                            "skill": (1 - lm / lb) * 100 if lb > 0 else None, "ll_model": lm, "ll_base": lb,
                            "dir_hit": dir_hit, "dir_base": float(np.mean(y // 3 == base_dir) * 100) if len(y) else None,
                            "ic_raw": float(pr["ic"].mean()) if len(pr) else None}
            pool_ic.append(pb["ic"])
            pool_sp.append(pb["spread"])
            pool_icr.append(pr["ic"])
            if len(y):
                ll_m += lm * len(y)
                ll_b += lb * len(y)
                n_ll += len(y)
        ic_by = pd.concat(pool_ic).groupby(level=0).mean() if pool_ic else pd.Series(dtype=float)
        sp_by = pd.concat(pool_sp).groupby(level=0).mean() if pool_sp else pd.Series(dtype=float)
        icr_by = pd.concat(pool_icr).groupby(level=0).mean() if pool_icr else pd.Series(dtype=float)
        r["pooled"] = {"ic": t_one_sided(ic_by), "spread": float(sp_by.mean()) if len(sp_by) else None,
                       "skill": (1 - ll_m / ll_b) * 100 if ll_b > 0 else None, "ic_raw": t_one_sided(icr_by)}
        r["verdict"] = verdict([r["each"][s]["ic"] for s in SAMPLES], [r["each"][s]["skill"] for s in SAMPLES],
                               r["pooled"]["ic"]["p"], r["pooled"]["spread"], r["pooled"]["skill"], tf)
        out["models"][model] = r
        if model.endswith("SC"):
            allX = pd.concat(tabs.values(), ignore_index=True)
            T = np.zeros((NCLS, NCLS))
            np.add.at(T, (allX["c1"].to_numpy(np.int64), allX["y"].to_numpy(np.int64)), 1)
            base = T.sum(0) / T.sum()
            with np.errstate(invalid="ignore", divide="ignore"):
                lift = (T / T.sum(1, keepdims=True)) / base
            out["transition"][tf] = {"n": int(T.sum()), "base": base.round(4).tolist(), "lift": np.round(lift, 3).tolist(),
                                     "rows": T.sum(1).astype(int).tolist()}
            out["top"][tf] = top_patterns(fits)
        say(f"A {model} 完成（判定只写在文件里）")
    return out, FITS


def top_patterns(fits: dict) -> dict:
    """只描述 ②：前 2 块（81 种）里在一折训练出现 ≥ TOP_MIN_N 次、下一块平均超额最高 / 最低的各 TOP_K 种 → 在另一折的平均与次数。"""
    out = {}
    for a, b in (("I", "II"), ("II", "I")):
        Fa, Fb = fits[a], fits[b]
        with np.errstate(invalid="ignore", divide="ignore"):
            ma = Fa["s2"] / Fa["n2"]
            mb = Fb["s2"] / Fb["n2"]
        ok = np.where(Fa["n2"] >= TOP_MIN_N)[0]
        order = ok[np.argsort(ma[ok])]
        pick = {"best": order[::-1][:TOP_K], "worst": order[:TOP_K]}
        out[f"{a}->{b}"] = {k: [{"pattern": f"{shape_name(int(i) % NCLS)} → {shape_name(int(i) // NCLS)}（前一块 → 最近一块）",
                                 "train_mean": float(ma[i]), "train_n": int(Fa["n2"][i]),
                                 "other_mean": float(mb[i]) if Fb["n2"][i] > 0 else None, "other_n": int(Fb["n2"][i])} for i in v]
                            for k, v in pick.items()}
    return out


def score_wide(BL: dict, model: str, F: dict, days: pd.DatetimeIndex) -> pd.DataFrame:
    dv = days.values.astype("datetime64[ns]")
    return pd.DataFrame({t: daily_scores(B, model, F, dv) for t, B in BL.items()}, index=days)


def part_b(W: dict, BLS: dict, FITS: dict, tbf: dict, tbf_pool: dict, pre: dict, say=print) -> dict:
    import combo_all_common as CA
    import loop9_common as C9
    import research_loop11 as R11
    import trendline_study as TS
    out: dict = {"cand": {}, "other": {}, "stage1": {}, "trig": {}, "verdict": {}, "describe": {}}
    base = pre["base"]
    b4tr = {e: TS.b4_trades(W, e, tbf[e], {}) for e in N225_ERAS}
    for k in B_IDS:
        model = B_MODEL[k]
        cand, other, trig, desc = {}, {}, 0, {}
        for s in SAMPLES:
            e = TS.WIN_ERA[s]
            days = pd.DatetimeIndex(W["ctx"][e]["days"])
            Sw = score_wide(BLS[s], model, FITS[model][MODEL_OF[s]], days)
            Fl = block_flags(Sw)
            if s in N225_ERAS:
                S = C9.signals(W, s)
                g = np.asarray(tbf[s], bool) | lookup_wide(Fl, S["ticker"], S["date"])
                cand[s] = C9.acct(C9.run_block(W, s, g))
                tr = b4tr[s]
                trig += int(lookup_wide(Fl, tr["ticker"], tr["sig"]).sum())
                ter = tercile_of(Sw, tr["ticker"], tr["sig"])
                net = tr["net"].to_numpy(float)
                desc[s] = {lab: ({"n": int((ter == v).sum()), "win": float((net[ter == v] > 0).mean() * 100),
                                  "mean": float(net[ter == v].mean())} if (ter == v).any() else {"n": 0})
                           for v, lab in ((0, "后三分之一"), (1, "中间"), (2, "前三分之一"), (-1, "算不出"))}
            else:
                X = TS.pool_x(W, s)[~np.asarray(tbf_pool[s], bool)].reset_index(drop=True)
                gp = lookup_wide(Fl, X["ticker"], X["date"])
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


def same_prep(now: dict, ref: dict | None, tol: float = B4_PREP_TOL) -> bool:
    """B4 重算 = 登记前记下的（笔数、胜率相同、Calmar 差 ≤ tol）。"""
    try:
        return (int(now["n"]) == int(ref["n"]) and abs(float(now["win"]) - float(ref["win"])) < 1e-9
                and abs(float(now["calmar"]) - float(ref["calmar"])) <= tol)
    except (KeyError, TypeError, ValueError):
        return False


def prereq(W: dict, tbf: dict, say=print) -> dict:
    """三的先决条件：规则指纹、接线核对、B4 重算 = B4_PREP（turn_shape_combo 的旧参照只记下、不要求一致）。"""
    import trendline_study as TS
    pre = TS.prereq(W, tbf, say)
    for e in N225_ERAS:
        pre[e]["same_prep"] = same_prep(pre["base"][e], B4_PREP.get(e))
    pre["ok"] = bool(pre["fp_ok"] and pre["fingerprint"] == FP and all(pre[e]["wired"] and pre[e]["same_prep"] for e in N225_ERAS))
    pre["b4_now"] = {e: {k: pre["base"][e].get(k) for k in ("n", "win", "calmar")} for e in N225_ERAS}
    return pre


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/kshape_link_study.py", "qbreak/kline.py"],
                                    capture_output=True, text=True).stdout.strip())
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
    BLS = build_blocks(sample_frames(W), say)
    return W, BLS, tbf, tbf_pool


def prep(say=print) -> dict:
    import loop9_common as C9
    import trendline_study as TS
    W, BLS, tbf, tbf_pool = load_all(say)
    pre = prereq(W, tbf, say)
    out: dict = {"prereq": {k: v for k, v in pre.items() if k != "base"}, "git": git_info(), "rows": {}, "tickers": {}, "B": {}}
    for s in SAMPLES:
        w = window_of(W, s)
        out["tickers"][s] = len(BLS[s])
        out["rows"][s] = {m: count_rows(BLS[s], m, w) for m in MODELS}
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
    W, BLS, tbf, tbf_pool = load_all(say)
    pre = prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit(f"先决条件不满足：{ {k: v for k, v in pre.items() if k != 'base'} } → 停")
    res: dict = {"study": OUT, "git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}}
    res["A"], FITS = part_a(BLS, W, say)
    res["B"] = part_b(W, BLS, FITS, tbf, tbf_pool, pre, say)
    res["elapsed_s"] = round(time.time() - t0)
    return res


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def report(res: dict) -> str:
    A, B = res["A"], res["B"]
    L = [f"# K 线块图形之间的关联预测：前几块日 / 周 / 月K → 下一块（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/kshape_link_study.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件：规则指纹 {res['prereq'].get('fingerprint')}、"
         f"B4 重算 = 登记前 {all(res['prereq'].get(e, {}).get('same_prep') for e in N225_ERAS)}、接线核对 {all(res['prereq'].get(e, {}).get('wired') for e in N225_ERAS)}；"
         f"用时 {res['elapsed_s']} s。", "", "## 一 / 二 能不能预测下一块（6 个样本都是样本外）", "",
         f"| 模型 | 判定 | 合起来 IC | p（要 < {P_MAX:.4f}） | 合起来分档差 pp（门槛） | 合起来 skill % | 6 个样本 IC |", "|---|---|---|---|---|---|---|"]
    for m in MODELS:
        r = A["models"][m]
        po = r["pooled"]
        L.append(f"| {m} {r['name']} | **{r['verdict']}** | {_f(po['ic']['mean'], '{:+.4f}')}（{po['ic']['n']} 块） | {_f(po['ic']['p'], '{:.4f}')} | "
                 f"{_f(po['spread'])}（{MIN_SPREAD[m[0]]}） | {_f(po['skill'], '{:+.2f}')} | "
                 + " / ".join(f"{s} {_f(r['each'][s]['ic'], '{:+.3f}')}" for s in SAMPLES) + " |")
    L += ["", "各样本（IC / 分档差 pp / skill % / 方向命中率 vs 只猜最多 / 含跳空的 IC）：", ""]
    for m in MODELS:
        r = A["models"][m]
        L.append(f"- {m}：" + "；".join(
            f"{s} {_f(x['ic'], '{:+.3f}')} / {_f(x['spread'], '{:+.2f}')} / {_f(x['skill'], '{:+.2f}')} / {_f(x['dir_hit'], '{:.1f}')}% vs {_f(x['dir_base'], '{:.1f}')}% / {_f(x['ic_raw'], '{:+.3f}')}"
            for s, x in r["each"].items()))
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
    L += ["", "B4 实际成交按信号日 XC 预测的三档（只描述；笔数 / 胜率 % / 每笔 %）：", ""]
    for k in B_IDS:
        L.append(f"- {k}：" + "；".join(f"{e} " + "、".join(
            f"{lab} {v['n']} 笔" + (f" {v['win']:.0f}% / {v['mean']:+.2f}%" if v.get("n") else "")
            for lab, v in B["describe"][k][e].items()) for e in N225_ERAS))
    L += ["", "## 四 只描述：哪几个图形（前一块 → 最近一块）之后下一块最好 / 最差，在另一折还成不成立", ""]
    for tf in SCALES:
        for fold, v in A["top"][tf].items():
            for side, lab in (("best", "最好"), ("worst", "最差")):
                L.append(f"- {tf} {fold} {lab}：" + "；".join(
                    f"{x['pattern']} {x['train_mean']:+.3f}（{x['train_n']}）→ {_f(x['other_mean'])}（{x['other_n']}）" for x in v[side]))
    L += ["", "转移表（上一块 → 下一块的形状，与基础频率之比；行 = 上一块）在 json 的 A.transition。",
          "只研究，不改模拟盘 / 执行器 / 面板 / 策略参数。非投资建议。"]
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
