"""turn_shape_study.py — 「所有股票的起涨点 / 起跌点 × 日 / 周 / 月线图形」研究（登记版：标注、特征、模型、判定、读法全部写在这里；提交后不改规则、只运行一次）。

来由：用户 2026-10-05「进行所有股票的开始涨跌的日 周 月图形研究」。
以前做过（结论不变）：多周期 R1（scripts/mtf_study.py，2026-09-27：日 / 周 / 月线的趋势状态 → 之后超额 ≈ 0，只有「量」两期一致 → 采用 W2）；
  K 线形态（scripts/candle_*.py：用户的上影陽線、押し目 C1〜C5、kNN 相似形状、形状聚类、K 线机器学习都不通过）；周 / 月线均线乖离（卖点、事件、超跌反弹都不通过）；
  底部判断（不更准确）；DeMark（不过）。
这次的不同：① 先「事后」标出每只票真正的起涨点 / 起跌点（按各股自己的波动大小定义），再看那时的日 / 周 / 月线长什么样、和平时比多见几倍；
  ② 全市场（不只日経225）、三个周期一起、经典 K 线形态在周线 / 月线上也算；③ 把「像起涨点 / 像起跌点」做成分数，在没参与训练的年份检验能不能提前认出来，
  而且要比「波动、规模、12-1 个月动量、20 日涨跌」这四个常用因子多出东西。
结论上限 = 「图形有用 → 提议另外登记策略检验（W2 突破的排序 / 过滤、持仓的离场）」；不改模拟盘、执行器。

一 数据与样本
  全市场面板（scripts/allstock_data.py：J-Quants 东证一般市場内国普通股、复权 OHLCV、时价总额、売買代金、时点上市掩码；2016-09-01〜2026-09-25；不入库）。
  样本 = 从 2017-10-02 起每 5 个交易日取一天（固定），那天：上市中 ∧ 收盘有值 ∧ 含当天的 20 日平均売買代金 ≥ ¥1,000 万 ∧ 有 250 个交易日以上的收盘
  ∧ 之后还有 41 个交易日（结果才完整）。
  探索（训练）2017-10-02〜2021-12-30；确认（只用来检验）2022-01-04〜数据末尾 − 41 个交易日。
  周线 = ISO 周、月线 = 日历月（qbreak/mtf.py 同一口径：只用已经完成的 K 线；完成日 = 那一周 / 那个月市场里最后一个交易日）。

二 标注（事后，只用来描述和训练；信号日 t 收盘时不知道）
  σ = 到 t 为止 60 个交易日的日对数收益标准差；M = clip(2 × σ × √40, 10%, 40%)（各股自己的「40 日 2 倍标准差」）。
  起涨点 RS(t)：t 的收盘是 [t − 10, t + 10] 里最低 ∧ 之后 40 个交易日内收盘先到 C_t × (1 + M)、没先跌到 C_t × (1 − M ÷ 2)。
  起跌点 FS(t)：t 的收盘是 [t − 10, t + 10] 里最高 ∧ 之后 40 日内收盘先到 C_t × (1 − M)、没先涨到 C_t × (1 + M ÷ 2)。
  可交易的结果（检验用）：R20x / R40x = 下一个交易日开盘买、20 / 40 个交易日后收盘（中途退市 = 最后收盘）的收益 − 同一天全部样本的平均；
    U = 下一个交易日开盘买之后 40 日内先涨 M（没先跌 M ÷ 2）；D = 先跌 M（没先涨 M ÷ 2）。

三 图形特征（全部是 t 收盘时已知；周 / 月线只用已完成的 K 线）
  日线 18 个（DAILY）：5 / 20 / 60 日涨跌、离 60 日高点、离 60 日低点、25 日线乖离与 5 日斜率、75 日线乖离、RSI(14)、布林带宽 ÷ 过去 120 日平均、
    量比（÷ 前 20 日平均）、5 日量 ÷ 之前 20 日平均、实体（阴阳带符号 ÷ 振幅）、上影 ÷ 振幅、下影 ÷ 振幅、振幅 ÷ 前一天 ATR、跳空、连涨 / 连跌天数（±7 封顶）；
  周线 14 个（WEEKLY）：4 / 13 / 26 周涨跌、13 周线乖离与 4 周斜率、26 周线乖离、周 RSI(14)、周量比（÷ 前 10 周）、实体、上影、下影、连涨 / 连跌周数、
    离 52 周高点、52 周区间里的位置；
  月线 11 个（MONTHLY）：3 / 12 个月涨跌、12 个月线乖离与 3 个月斜率、月 RSI(6)、月量比（÷ 前 6 个月）、实体、上影、下影、连涨 / 连跌月数、离 12 个月高点；
  另 3 个（BASE_X，也在模型里）：σ（60 日波动）、log 时价总额、12-1 个月动量。
  经典 K 线形态 30 种（qbreak/candles.PATTERNS）在日线、周线、月线上各算一遍（只描述）。

四 描述（图集；探索期与确认期分开报）
  ① 起涨点 / 起跌点前后的平均形状：日线 −60〜+40 日、周线 −26〜+8 周、月线 −24〜+3 个月（log 价格相对 t，减去全部样本的平均 = 超额形状）；
  ② 每个特征的五分位（切点用探索期全部样本）：起涨点 / 起跌点落在各五分位的比例 ÷ 20% = 倍数（起涨、起跌都偏多的 = 只是「波动大」，不是方向）；
  ③ 经典形态：出现时是起涨点 / 起跌点的比例 ÷ 平时的比例（倍数）、出现之后 R20x 的平均。

五 预测（规则写死、没有人工挑选；一次运行里自动完成）
  上涨模型：逻辑回归（L2 = 1.0，特征按探索期 1% / 99% 分位截尾后标准化，缺值的行不用），用探索期 46 个特征拟合 RS；
    基础模型 = 只用 σ、log 时价总额、12-1 动量、20 日涨跌拟合 RS。下跌模型：同样拟合 FS。
  确认期：每个样本日按分数在当天的样本里分十组。判定（上涨模型 s = +1；下跌模型 s = −1，「最高一组」= 最像起跌点的一组）：
    G1 确认期自己标注（RS / FS）的 AUC ≥ 0.55；G2 AUC（全部）− AUC（基础）≥ +0.01；
    G3 s × 最高一组的 R20x 平均 > 0 且按月聚类的 95% 区间（s × 方向）下限 > 0，且 s × (最高 − 最低) ≥ +1.0 pp；
    G4 s × (最高一组 R20x − 基础模型最高一组 R20x) ≥ +0.5 pp（比四个常用因子多出来的）；
    G5 2022〜2026 五个年份里至少 4 年 s × 最高一组 R20x > 0；
    G6 大型股（每个样本日时价总额前 500 名里再分十组）s × (最高 − 最低) > 0。
  档位：G1〜G6 全过 =「图形有用」→ 提议另外登记策略检验（用户确认）；G3 ∧ G5 过、但 G1 / G2 / G4 / G6 有不过 =「有信息、但不比常用因子多 / 只在小型股」→ 只记录；
    其余 =「没有用」。只描述：今天的日経225 子样本、按年、按规模、R40x、U / D 的比例。

六 前视与数据质量（事先声明）：特征只用 t 收盘为止（周 / 月线只用已完成的）；标注与结果用 t 之后的数据（只用来训练 / 检验）；
  样本日每 5 天一个、20 日结果彼此重叠 → 区间按月聚类；复权价；退市按最后收盘；全市场多是小型股（滑点偏乐观）；
  输出只有统计（var/out/turn_shape_study.md / .json），没有个股名单。

七 诚实的预期：图集大概率显示「起涨在急跌、远离均线、波动大之后，起跌在急涨之后」—— 主要是均值回归与波动；经典 K 线形态的倍数多在 0.8〜1.3 倍；
  上涨模型 G1 大概率过，G2 / G4（比常用因子多）约 25%，G6（大型股）约 30%，全过约 10%；下跌模型类似或更低。非投资建议。
用法：python scripts/turn_shape_study.py --counts（登记前只数个数）；python scripts/turn_shape_study.py --run [--out-dir DIR]
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
from qbreak import candles as K                                               # noqa: E402
from qbreak import mtf                                                        # noqa: E402
from qbreak import paths                                                      # noqa: E402

START, X_END, C_START = "2017-10-02", "2021-12-30", "2022-01-04"
STEP, HIST_MIN, VA_MIN, VA_N = 5, 250, 1e7, 20
H_LAB, EXT_WIN, SIG_N, M_K, M_LO, M_HI = 40, 10, 60, 2.0, 0.10, 0.40
H_RET, FWD_NEED = (20, 40), 41
L2, WINSOR = 1.0, (1.0, 99.0)
AUC_MIN, AUC_INC, SPREAD_PP, TOP_INC_PP, YEARS_MIN, LARGE_N, N_DEC = 0.55, 0.01, 1.0, 0.5, 4, 500, 10
BOOT_N, SEED = 2000, 20261005
PATH_D, PATH_W, PATH_M = (-60, 40), (-26, 8), (-24, 3)
DAILY = ["d_r5", "d_r20", "d_r60", "d_dd60", "d_up60", "d_ma25", "d_ma25s", "d_ma75", "d_rsi14", "d_bbw", "d_vr", "d_vr5",
         "d_body", "d_ush", "d_lsh", "d_size", "d_gap", "d_run"]
WEEKLY = ["w_r4", "w_r13", "w_r26", "w_ma13", "w_ma13s", "w_ma26", "w_rsi14", "w_vr", "w_body", "w_ush", "w_lsh", "w_run", "w_dd52", "w_pos52"]
MONTHLY = ["m_r3", "m_r12", "m_ma12", "m_ma12s", "m_rsi6", "m_vr", "m_body", "m_ush", "m_lsh", "m_run", "m_dd12"]
BASE_X = ["sig60", "lmc", "mom12"]
FEATS = DAILY + WEEKLY + MONTHLY + BASE_X
BASELINE = ["sig60", "lmc", "mom12", "d_r20"]
MODELS = {"rise": ("RS", 1), "fall": ("FS", -1)}
OUT_MD, OUT_JSON = "turn_shape_study.md", "turn_shape_study.json"


# ───────────────────────── 基本运算（日期 × 票 的宽表） ─────────────────────────
def sh(a: np.ndarray, k: int) -> np.ndarray:
    return K.sh(a, k)


def fwd(a: np.ndarray, k: int) -> np.ndarray:
    """第 t 行 = 原来第 t + k 行（往前看 k 行；后面补 NaN）。"""
    out = np.full(a.shape, np.nan, dtype=float)
    if k < len(a):
        out[:len(a) - k] = a[k:]
    return out


def rmean(a: np.ndarray, n: int) -> np.ndarray:
    return K.rolling_mean(a, n)


def rmax(a: np.ndarray, n: int) -> np.ndarray:
    return K.rolling_max(a, n)


def rmin(a: np.ndarray, n: int) -> np.ndarray:
    return K.rolling_min(a, n)


def rstd(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).std().to_numpy()


def ffill(a: np.ndarray) -> np.ndarray:
    """沿时间向前填（停牌 / 退市后 = 最后一个值；上市前仍是 NaN）。"""
    return pd.DataFrame(a).ffill().to_numpy(float)


def ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return a / b


def wilder_rsi(C: np.ndarray, n: int) -> np.ndarray:
    """Wilder RSI（与 qbreak/strategy.rsi 同一口径：涨跌的 ewm(alpha = 1/n)；只涨不跌 → 100）。"""
    d = np.diff(C, axis=0, prepend=np.nan)
    upm = pd.DataFrame(np.where(np.isfinite(d), np.clip(d, 0, None), np.nan)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    dnm = pd.DataFrame(np.where(np.isfinite(d), np.clip(-d, 0, None), np.nan)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    rs = ratio(upm, np.where(dnm == 0, np.nan, dnm))
    out = 100 - 100 / (1 + rs)
    return np.where((dnm == 0) & np.isfinite(upm), 100.0, out)


def run_len(C: np.ndarray, cap: int = 7) -> np.ndarray:
    """连涨 / 连跌：收盘比前一根高 → +1 累加、低 → −1 累加、持平或缺 → 0；±cap 封顶。第 0 行 NaN。"""
    T, N = C.shape
    out = np.full((T, N), np.nan)
    prev = np.zeros(N)
    for t in range(1, T):
        with np.errstate(invalid="ignore"):
            up, dn = C[t] > C[t - 1], C[t] < C[t - 1]
        cur = np.where(up, np.where(prev > 0, prev + 1, 1), np.where(dn, np.where(prev < 0, prev - 1, -1), 0))
        prev = np.clip(cur, -cap, cap)
        out[t] = prev
    return out


def candle_shape(O: np.ndarray, H: np.ndarray, L: np.ndarray, C: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(带符号的实体, 上影, 下影) ÷ 振幅；振幅 ≤ 0 → NaN。"""
    rng = np.where(H - L > 0, H - L, np.nan)
    return ratio(C - O, rng), ratio(H - np.fmax(O, C), rng), ratio(np.fmin(O, C) - L, rng)


# ───────────────────────── 周 / 月线 ─────────────────────────
def bar_panels(P: dict, days: pd.DatetimeIndex, freq: str) -> tuple[dict, pd.DatetimeIndex, np.ndarray]:
    """日线宽表 → 周 / 月线宽表（只留已完成的周期；O 第一个有值的开盘、H 最高、L 最低、C 最后一个有值的收盘、V 合计）
    + 每个交易日 → 当天收盘时已完成的最近一根的位置（没有 → −1）。"""
    key = mtf.period_key(days, freq)
    comp = mtf.completion_days(days, freq)
    agg = {}
    for k, how in (("O", "first"), ("H", "max"), ("L", "min"), ("C", "last"), ("V", "sum")):
        g = pd.DataFrame(P[k]).groupby(key, sort=True)
        agg[k] = g.sum(min_count=1) if how == "sum" else getattr(g, how)()
    keep = agg["C"].index.isin(comp.index)
    cdays = pd.DatetimeIndex(comp.reindex(agg["C"].index[keep]).to_numpy())
    bars = {k: v[keep].to_numpy(float) for k, v in agg.items()}
    pos = np.searchsorted(cdays.to_numpy(dtype="datetime64[ns]"), days.to_numpy(dtype="datetime64[ns]"), side="right") - 1
    return bars, cdays, pos


def on_days(Bv: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """周 / 月线的值 → 每个交易日（取当天已完成的最近一根）。"""
    out = np.full((len(pos), Bv.shape[1]), np.nan)
    ok = pos >= 0
    out[ok] = Bv[pos[ok]]
    return out


# ───────────────────────── 特征（逐个产生，用完就丢，省内存） ─────────────────────────
def daily_features(P: dict, MC: np.ndarray):
    O, H, L, C, V = P["O"], P["H"], P["L"], P["C"], P["V"]
    yield "d_r5", ratio(C, sh(C, 5)) - 1
    yield "d_r20", ratio(C, sh(C, 20)) - 1
    yield "d_r60", ratio(C, sh(C, 60)) - 1
    yield "d_dd60", ratio(C, rmax(C, 60)) - 1
    yield "d_up60", ratio(C, rmin(C, 60)) - 1
    m25 = rmean(C, 25)
    yield "d_ma25", ratio(C, m25) - 1
    yield "d_ma25s", ratio(m25, sh(m25, 5)) - 1
    del m25
    yield "d_ma75", ratio(C, rmean(C, 75)) - 1
    yield "d_rsi14", wilder_rsi(C, 14)
    bw = ratio(4 * rstd(C, 20), rmean(C, 20))
    yield "d_bbw", ratio(bw, rmean(bw, 120))
    del bw
    v20 = sh(rmean(V, 20), 1)
    yield "d_vr", ratio(V, v20)
    yield "d_vr5", ratio(rmean(V, 5), sh(rmean(V, 20), 5))
    del v20
    b, u, lo = candle_shape(O, H, L, C)
    yield "d_body", b
    yield "d_ush", u
    yield "d_lsh", lo
    del b, u, lo
    yield "d_size", ratio(H - L, sh(K.atr(H, L, C), 1))
    yield "d_gap", ratio(O, sh(C, 1)) - 1
    yield "d_run", run_len(C)
    yield "lmc", np.log(np.where(MC > 0, MC, np.nan))
    yield "mom12", ratio(sh(C, 21), sh(C, 252)) - 1


def bar_features(B: dict, prefix: str):
    """周线（prefix = "w"）/ 月线（"m"）的特征，在 K 线轴上算（之后再放回交易日）。"""
    O, H, L, C, V = B["O"], B["H"], B["L"], B["C"], B["V"]
    b, u, lo = candle_shape(O, H, L, C)
    if prefix == "w":
        m13 = rmean(C, 13)
        feats = {"w_r4": ratio(C, sh(C, 4)) - 1, "w_r13": ratio(C, sh(C, 13)) - 1, "w_r26": ratio(C, sh(C, 26)) - 1,
                 "w_ma13": ratio(C, m13) - 1, "w_ma13s": ratio(m13, sh(m13, 4)) - 1, "w_ma26": ratio(C, rmean(C, 26)) - 1,
                 "w_rsi14": wilder_rsi(C, 14), "w_vr": ratio(V, sh(rmean(V, 10), 1)), "w_body": b, "w_ush": u, "w_lsh": lo,
                 "w_run": run_len(C), "w_dd52": ratio(C, rmax(C, 52)) - 1,
                 "w_pos52": ratio(C - rmin(C, 52), rmax(C, 52) - rmin(C, 52))}
    else:
        m12 = rmean(C, 12)
        feats = {"m_r3": ratio(C, sh(C, 3)) - 1, "m_r12": ratio(C, sh(C, 12)) - 1, "m_ma12": ratio(C, m12) - 1,
                 "m_ma12s": ratio(m12, sh(m12, 3)) - 1, "m_rsi6": wilder_rsi(C, 6), "m_vr": ratio(V, sh(rmean(V, 6), 1)),
                 "m_body": b, "m_ush": u, "m_lsh": lo, "m_run": run_len(C), "m_dd12": ratio(C, rmax(C, 12)) - 1}
    return feats


def pattern_flags(P: dict) -> dict[str, np.ndarray]:
    """经典 K 线形态（qbreak/candles.patterns；日线或 K 线轴上的宽表）。"""
    g = K.geometry(P)
    return K.patterns(P, g, K.context(P, g))


# ───────────────────────── 标注与结果 ─────────────────────────
def first_pass(Cf: np.ndarray, base: np.ndarray, up: np.ndarray, dn: np.ndarray, h: int = H_LAB) -> tuple[np.ndarray, np.ndarray]:
    """之后第 1〜h 个交易日的收盘（Cf 已向前填）÷ base：第一次 ≥ up 的天数、第一次 ≤ dn 的天数（没有 → inf）。"""
    hu = np.full(Cf.shape, np.inf)
    hd = np.full(Cf.shape, np.inf)
    for k in range(1, h + 1):
        r = ratio(fwd(Cf, k), base)
        with np.errstate(invalid="ignore"):
            a = (r >= up) & np.isinf(hu)
            b = (r <= dn) & np.isinf(hd)
        hu[a] = k
        hd[b] = k
    return hu, hd


def labels(P: dict) -> dict[str, np.ndarray]:
    """σ、M、起涨点 RS、起跌点 FS、可交易的 U / D、R20 / R40（原始收益；超额在取样后算）。"""
    O, C = P["O"], P["C"]
    Cf = ffill(C)
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.diff(np.log(C), axis=0, prepend=np.nan)
    sig = rstd(lr, SIG_N)
    M = np.clip(M_K * sig * np.sqrt(H_LAB), M_LO, M_HI)
    w = 2 * EXT_WIN + 1
    lo = pd.DataFrame(C).rolling(w, center=True, min_periods=EXT_WIN + 5).min().to_numpy()
    hi = pd.DataFrame(C).rolling(w, center=True, min_periods=EXT_WIN + 5).max().to_numpy()
    fin = np.isfinite(C) & np.isfinite(M)
    with np.errstate(invalid="ignore"):
        is_lo, is_hi = fin & (C <= lo), fin & (C >= hi)
    u1, d1 = first_pass(Cf, C, 1 + M, 1 - M / 2)
    RS = is_lo & np.isfinite(u1) & (u1 < d1)
    u2, d2 = first_pass(Cf, C, 1 + M / 2, 1 - M)
    FS = is_hi & np.isfinite(d2) & (d2 < u2)
    del u1, d1, u2, d2
    O1 = fwd(O, 1)
    u3, d3 = first_pass(Cf, O1, 1 + M, 1 - M / 2)
    U = np.isfinite(O1) & np.isfinite(u3) & (u3 < d3)
    u4, d4 = first_pass(Cf, O1, 1 + M / 2, 1 - M)
    D = np.isfinite(O1) & np.isfinite(d4) & (d4 < u4)
    del u3, d3, u4, d4
    out = {"sig60": sig, "M": M, "RS": RS, "FS": FS, "U": U, "D": D}
    for h in H_RET:
        out[f"R{h}"] = ratio(fwd(Cf, h), O1) - 1
    return out


# ───────────────────────── 样本 ─────────────────────────
def sample_mask(A: dict, days: pd.DatetimeIndex, start: str = START) -> np.ndarray:
    C = A["C"]
    T = len(days)
    k0 = int(np.searchsorted(days.to_numpy(dtype="datetime64[ns]"), np.datetime64(pd.Timestamp(start))))
    on = np.zeros(T, bool)
    on[k0::STEP] = True
    on[max(T - FWD_NEED, 0):] = False
    va = rmean(A["VA"].astype(float), VA_N)
    hist = np.cumsum(np.isfinite(C), axis=0)
    with np.errstate(invalid="ignore"):
        return on[:, None] & A["listed"].astype(bool) & np.isfinite(C) & (va >= VA_MIN) & (hist >= HIST_MIN)


def take(a: np.ndarray, kk: np.ndarray, jj: np.ndarray) -> np.ndarray:
    return np.asarray(a[kk, jj], dtype=np.float32)


def build_table(A: dict, days: pd.DatetimeIndex, names: list[str], with_patterns: bool = True, with_paths: bool = True, say=print) -> tuple[pd.DataFrame, dict]:
    """样本表（每行 = 票 × 样本日）：特征、形态、标注、结果；以及画平均形状用的路径。"""
    t0 = time.time()
    P = {k: A[k].astype(float) for k in ("O", "H", "L", "C", "V")}
    S = sample_mask(A, days)
    kk, jj = np.nonzero(S)
    T = pd.DataFrame({"k": kk.astype(np.int32), "j": jj.astype(np.int32)})
    T["date"] = days[kk]
    say(f"样本 {len(T)} 行（{T['date'].nunique()} 个样本日）；{time.time() - t0:.0f}s")
    for name, arr in daily_features(P, A["MC"].astype(float)):
        T[name] = take(arr, kk, jj)
    say(f"日线特征完成；{time.time() - t0:.0f}s")
    bars = {}
    for freq, prefix in (("W", "w"), ("M", "m")):
        B, cdays, pos = bar_panels(P, days, freq)
        bars[prefix] = (B, cdays, pos)
        for name, arr in bar_features(B, prefix).items():
            T[name] = take(on_days(arr, pos), kk, jj)
    say(f"周 / 月线特征完成；{time.time() - t0:.0f}s")
    L = labels(P)
    for k in ("sig60", "M", "RS", "FS", "U", "D", "R20", "R40"):
        T[k] = take(L[k].astype(float), kk, jj)
    for h in H_RET:
        r = T[f"R{h}"]
        T[f"R{h}x"] = (r - r.groupby(T["date"]).transform("mean")).astype(np.float32)
    say(f"标注完成；{time.time() - t0:.0f}s")
    if with_patterns:
        for name, arr in pattern_flags(P).items():
            T["pd_" + name] = arr[kk, jj]
        for prefix in ("w", "m"):
            B, cdays, pos = bars[prefix]
            for name, arr in pattern_flags(B).items():
                T[f"p{prefix}_{name}"] = on_days(arr.astype(float), pos)[kk, jj] > 0.5
        say(f"形态完成；{time.time() - t0:.0f}s")
    T["mc_rank"] = T.groupby("date")["lmc"].rank(ascending=False, method="first").astype(np.float32)
    if not with_paths:
        return T, {}
    Cf = ffill(P["C"])
    paths_ = {"d": {o: take(np.log(ratio(fwd(Cf, o) if o > 0 else sh(Cf, -o) if o < 0 else Cf, Cf)), kk, jj)
                    for o in range(PATH_D[0], PATH_D[1] + 1)}}
    for prefix, rngs in (("w", PATH_W), ("m", PATH_M)):
        B, cdays, pos = bars[prefix]
        Cb = ffill(B["C"])
        p = pos[kk]
        out = {}
        for o in range(rngs[0], rngs[1] + 1):
            q = p + o
            ok = (p >= 0) & (q >= 0) & (q < len(Cb))
            v = np.full(len(kk), np.nan, dtype=np.float32)
            with np.errstate(invalid="ignore", divide="ignore"):
                v[ok] = np.log(Cb[q[ok], jj[ok]] / Cb[p[ok], jj[ok]])
            out[o] = v
        paths_[prefix] = out
    say(f"路径完成；{time.time() - t0:.0f}s")
    return T, paths_


# ───────────────────────── 模型与统计 ─────────────────────────
def winsor_std(X: np.ndarray, Xref: np.ndarray) -> tuple[np.ndarray, dict]:
    """按参考样本的 1% / 99% 分位截尾，再用参考样本的均值 / 标准差标准化。"""
    lo, hi = np.nanpercentile(Xref, WINSOR[0], axis=0), np.nanpercentile(Xref, WINSOR[1], axis=0)
    R = np.clip(Xref, lo, hi)
    mu, sd = np.nanmean(R, axis=0), np.nanstd(R, axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    return (np.clip(X, lo, hi) - mu) / sd, {"lo": lo, "hi": hi, "mu": mu, "sd": sd}


def apply_std(X: np.ndarray, st: dict) -> np.ndarray:
    return (np.clip(X, st["lo"], st["hi"]) - st["mu"]) / st["sd"]


def fit_logit(X: np.ndarray, y: np.ndarray, l2: float = L2, iters: int = 30) -> np.ndarray:
    """L2 逻辑回归（IRLS；截距不罚）。返回 [截距, 系数…]。"""
    n, p = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(p + 1)
    pen = np.full(p + 1, l2)
    pen[0] = 0.0
    for _ in range(iters):
        z = np.clip(Xb @ w, -30, 30)
        mu = 1 / (1 + np.exp(-z))
        Wt = mu * (1 - mu)
        g = Xb.T @ (y - mu) - pen * w
        Hm = (Xb * Wt[:, None]).T @ Xb + np.diag(pen)
        step = np.linalg.solve(Hm, g)
        w = w + step
        if np.max(np.abs(step)) < 1e-7:
            break
    return w


def predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.clip(w[0] + X @ w[1:], -30, 30)


def auc(score: np.ndarray, y: np.ndarray) -> float | None:
    m = np.isfinite(score) & np.isfinite(y)
    s, yy = score[m], y[m] > 0.5
    n1, n0 = int(yy.sum()), int((~yy).sum())
    if not n1 or not n0:
        return None
    r = pd.Series(s).rank().to_numpy()
    return round(float((r[yy].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)), 4)


def deciles_by_day(score: np.ndarray, day: np.ndarray, n: int = N_DEC) -> np.ndarray:
    """每个样本日内按分数排名分 n 组（0 = 最低、n − 1 = 最高）。"""
    s = pd.Series(score)
    r = s.groupby(np.asarray(day)).rank(method="first")
    c = s.groupby(np.asarray(day)).transform("count")
    return np.minimum(((r - 1) * n // c).to_numpy(), n - 1).astype(int)


def boot_ci(x: np.ndarray, cl: np.ndarray, n: int = BOOT_N, seed: int = SEED) -> tuple[float | None, float | None]:
    """按簇（月）聚类的自助法：均值的 2.5 / 97.5 分位。"""
    m = np.isfinite(x)
    x, cl = x[m], np.asarray(cl)[m]
    if len(x) < 30:
        return None, None
    codes, uniq = pd.factorize(cl)
    s = np.bincount(codes, weights=x, minlength=len(uniq))
    c = np.bincount(codes, minlength=len(uniq)).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uniq), size=(n, len(uniq)))
    bm = s[idx].sum(1) / c[idx].sum(1)
    return float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))


def dec_stats(D: pd.DataFrame, dec: np.ndarray) -> dict:
    out = {}
    for d in range(N_DEC):
        x = D[dec == d]
        if not len(x):
            continue
        out[d] = {"n": int(len(x)), "R20x": round(float(np.nanmean(x["R20x"])) * 100, 3), "R40x": round(float(np.nanmean(x["R40x"])) * 100, 3),
                  "U": round(float(np.nanmean(x["U"])) * 100, 2), "D": round(float(np.nanmean(x["D"])) * 100, 2),
                  "RS": round(float(np.nanmean(x["RS"])) * 100, 2), "FS": round(float(np.nanmean(x["FS"])) * 100, 2)}
    return out


def judge(s: int, g1_auc: float | None, auc_base: float | None, top: dict, bottom: dict, top_ci: tuple, top_base: dict,
          years: dict, large: dict) -> dict:
    """G1〜G6（s = +1 上涨模型；−1 下跌模型）。"""
    g = {}
    g["G1"] = g1_auc is not None and g1_auc >= AUC_MIN
    g["G2"] = g1_auc is not None and auc_base is not None and g1_auc - auc_base >= AUC_INC
    lo, hi = top_ci
    s_lo = None if lo is None else (lo * 100 if s > 0 else -hi * 100)
    g["G3"] = (s * top["R20x"] > 0) and s_lo is not None and s_lo > 0 and s * (top["R20x"] - bottom["R20x"]) >= SPREAD_PP
    g["G4"] = s * (top["R20x"] - top_base["R20x"]) >= TOP_INC_PP
    g["G5"] = sum(1 for v in years.values() if v.get("n") and s * v["R20x"] > 0) >= YEARS_MIN
    g["G6"] = bool(large) and s * (large.get("top", np.nan) - large.get("bottom", np.nan)) > 0
    if all(g.values()):
        tier = "图形有用 → 提议另外登记策略检验（用户确认）"
    elif g["G3"] and g["G5"]:
        tier = "有信息、但不比常用因子多 / 只在小型股（只记录）"
    else:
        tier = "没有用"
    return {"gates": g, "tier": tier, "s_ci_lo_pp": None if s_lo is None else round(s_lo, 3)}


# ───────────────────────── 描述（图集） ─────────────────────────
def quintile_lifts(T: pd.DataFrame, ref: pd.DataFrame, feats: list[str]) -> dict:
    """每个特征的五分位（切点 = ref）→ 起涨点 / 起跌点的倍数、各五分位的 R20x 平均。"""
    out = {}
    rs, fs = T["RS"].to_numpy() > 0.5, T["FS"].to_numpy() > 0.5
    r20 = T["R20x"].to_numpy(float)
    for f in feats:
        x = T[f].to_numpy(float)
        cut = np.nanpercentile(ref[f].to_numpy(float), [20, 40, 60, 80])
        q = np.where(np.isfinite(x), np.searchsorted(cut, x, side="right"), -1)
        ok = q >= 0
        row = {}
        for i in range(5):
            m = ok & (q == i)
            row[i] = {"share": round(float(m.sum() / max(ok.sum(), 1)) * 100, 1),
                      "RS": round(float((m & rs).sum() / max((ok & rs).sum(), 1) / max(m.sum() / max(ok.sum(), 1), 1e-9)), 2),
                      "FS": round(float((m & fs).sum() / max((ok & fs).sum(), 1) / max(m.sum() / max(ok.sum(), 1), 1e-9)), 2),
                      "R20x": round(float(np.nanmean(r20[m])) * 100, 3) if m.any() else None}
        out[f] = {"cut": [round(float(c), 4) for c in cut], "q": row}
    return out


def pattern_lifts(T: pd.DataFrame) -> dict:
    out = {}
    rs, fs = T["RS"].to_numpy() > 0.5, T["FS"].to_numpy() > 0.5
    base_rs, base_fs = rs.mean(), fs.mean()
    r20 = T["R20x"].to_numpy(float)
    for c in [c for c in T.columns if c.startswith(("pd_", "pw_", "pm_"))]:
        m = T[c].to_numpy(bool)
        n = int(m.sum())
        if n < 30:
            out[c] = {"n": n}
            continue
        out[c] = {"n": n, "share": round(n / len(T) * 100, 2), "RS": round(float(rs[m].mean() / base_rs), 2) if base_rs else None,
                  "FS": round(float(fs[m].mean() / base_fs), 2) if base_fs else None, "R20x": round(float(np.nanmean(r20[m])) * 100, 3)}
    return out


def mean_paths(T: pd.DataFrame, paths_: dict, masks: dict) -> dict:
    """平均形状（log 价格相对 t × 100）：各标注的平均、全部样本的平均、两者之差（超额）。"""
    out = {}
    for tf, P_ in paths_.items():
        out[tf] = {}
        for lab, m in masks.items():
            out[tf][lab] = {int(o): (round(float(np.nanmean(v[m])) * 100, 3) if m.any() else None) for o, v in P_.items()}
    return out


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/turn_shape_study.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def windows(T: pd.DataFrame) -> dict[str, np.ndarray]:
    d = T["date"]
    return {"X": (d <= pd.Timestamp(X_END)).to_numpy(), "C": (d >= pd.Timestamp(C_START)).to_numpy()}


def counts(T: pd.DataFrame, n225: set, names: list[str]) -> dict:
    """登记前只数个数（标注的出现率、样本量、特征缺值率；不算任何特征与结果的关系）。"""
    w = windows(T)
    tick = np.array(names)[T["j"].to_numpy()]
    out = {"rows": int(len(T)), "days": int(T["date"].nunique()), "first": str(T["date"].min().date()), "last": str(T["date"].max().date())}
    for k, m in w.items():
        x = T[m]
        out[k] = {"rows": int(len(x)), "days": int(x["date"].nunique()), "stocks_per_day": round(float(x.groupby("date").size().mean()), 1),
                  "RS_pct": round(float(x["RS"].mean()) * 100, 2), "FS_pct": round(float(x["FS"].mean()) * 100, 2),
                  "U_pct": round(float(x["U"].mean()) * 100, 2), "D_pct": round(float(x["D"].mean()) * 100, 2),
                  "M_median_pct": round(float(np.nanmedian(x["M"])) * 100, 1),
                  "complete_rows_pct": round(float(x[FEATS].notna().all(axis=1).mean()) * 100, 1),
                  "n225_rows": int(np.isin(tick[m], list(n225)).sum())}
    out["nan_pct"] = {f: round(float(T[f].isna().mean()) * 100, 1) for f in FEATS}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="所有股票的起涨点 / 起跌点 × 日 / 周 / 月线图形（登记版）")
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if not (a.counts or a.run):
        raise SystemExit("要 --counts 或 --run")
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    t0 = time.time()
    say = lambda s_: print(s_, flush=True)                                   # noqa: E731
    import allstock_data as AD
    from qbreak.config import universe
    A = AD.load()
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    n225 = set(universe("JP", "broad"))
    T, paths_ = build_table(A, days, names, with_patterns=a.run, with_paths=a.run, say=say)
    cnt = counts(T, n225, names)
    if a.counts:
        print(json.dumps(cnt, ensure_ascii=False, indent=1))
        return 0
    w = windows(T)
    tick = np.array(names)[T["j"].to_numpy()]
    T["n225"] = np.isin(tick, list(n225))
    T["month"] = T["date"].dt.to_period("M").astype(str)
    res: dict = {"git": git_info(), "counts": cnt, "atlas": {}, "models": {}}
    # 图集
    X = T[w["X"]]
    for wk, m in w.items():
        x = T[m]
        res["atlas"][wk] = {"lifts": quintile_lifts(x, X, FEATS), "patterns": pattern_lifts(x),
                            "paths": mean_paths(x, {tf: {o: v[m] for o, v in P_.items()} for tf, P_ in paths_.items()},
                                                {"RS": x["RS"].to_numpy() > 0.5, "FS": x["FS"].to_numpy() > 0.5, "ALL": np.ones(len(x), bool)})}
    say(f"图集完成；{time.time() - t0:.0f}s")
    # 模型
    comp = T[FEATS].notna().all(axis=1).to_numpy()
    xi, ci = w["X"] & comp, w["C"] & comp
    Xr = T.loc[xi, FEATS].to_numpy(float)
    Xs, st = winsor_std(Xr, Xr)
    Xc = apply_std(T.loc[ci, FEATS].to_numpy(float), st)
    bi = [FEATS.index(f) for f in BASELINE]
    Dc = T[ci].reset_index(drop=True)
    for mk, (lab, s) in MODELS.items():
        y = T.loc[xi, lab].to_numpy(float)
        wf = fit_logit(Xs, y)
        wb = fit_logit(Xs[:, bi], y)
        sc, sb = predict(wf, Xc), predict(wb, Xc[:, bi])
        yc = Dc[lab].to_numpy(float)
        a_full, a_base = auc(sc, yc), auc(sb, yc)
        dec, decb = deciles_by_day(sc, Dc["date"].to_numpy()), deciles_by_day(sb, Dc["date"].to_numpy())
        ds, dsb = dec_stats(Dc, dec), dec_stats(Dc, decb)
        topm = dec == N_DEC - 1
        ci_top = boot_ci(Dc.loc[topm, "R20x"].to_numpy(float), Dc.loc[topm, "month"].to_numpy())
        years = {}
        for yv in sorted(Dc["date"].dt.year.unique()):
            mm = topm & (Dc["date"].dt.year == yv).to_numpy()
            years[int(yv)] = {"n": int(mm.sum()), "R20x": round(float(np.nanmean(Dc.loc[mm, "R20x"])) * 100, 3) if mm.any() else None}
        lg = (Dc["mc_rank"] <= LARGE_N).to_numpy()
        large = {}
        if lg.sum() > 100:
            dl = deciles_by_day(sc[lg], Dc.loc[lg, "date"].to_numpy())
            r = Dc.loc[lg, "R20x"].to_numpy(float)
            large = {"top": round(float(np.nanmean(r[dl == N_DEC - 1])) * 100, 3), "bottom": round(float(np.nanmean(r[dl == 0])) * 100, 3), "n": int(lg.sum())}
        n2 = Dc["n225"].to_numpy(bool)
        n225d = {}
        if n2.sum() > 100:
            dn = deciles_by_day(sc[n2], Dc.loc[n2, "date"].to_numpy())
            r = Dc.loc[n2, "R20x"].to_numpy(float)
            n225d = {"top": round(float(np.nanmean(r[dn == N_DEC - 1])) * 100, 3), "bottom": round(float(np.nanmean(r[dn == 0])) * 100, 3), "n": int(n2.sum())}
        J = judge(s, a_full, a_base, ds[N_DEC - 1], ds[0], ci_top, dsb[N_DEC - 1], years, large)
        coefs = sorted(zip(FEATS, wf[1:]), key=lambda kv: -abs(kv[1]))
        res["models"][mk] = {"label": lab, "sign": s, "n_train": int(xi.sum()), "n_test": int(ci.sum()), "train_rate_pct": round(float(y.mean()) * 100, 2),
                             "auc": a_full, "auc_base": a_base, "auc_train": auc(predict(wf, Xs), y), "deciles": ds, "deciles_base": dsb,
                             "top_ci_pp": [None if v is None else round(v * 100, 3) for v in ci_top], "years": years, "large": large, "n225": n225d,
                             "coef": [{"f": f, "b": round(float(b), 4)} for f, b in coefs], "coef_base": [{"f": f, "b": round(float(b), 4)} for f, b in zip(BASELINE, wb[1:])],
                             **J}
        say(f"{mk}：AUC {a_full} / 基础 {a_base}；{J['tier']}；{time.time() - t0:.0f}s")
    res["elapsed_s"] = round(time.time() - t0)
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report(res)
    (out_dir / OUT_MD).write_text(md + "\n", encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md)
    return 0


NAMES = {"d_r5": "日 5 日涨跌", "d_r20": "日 20 日涨跌", "d_r60": "日 60 日涨跌", "d_dd60": "日 离 60 日高点", "d_up60": "日 离 60 日低点", "d_ma25": "日 25 日线乖离",
         "d_ma25s": "日 25 日线斜率", "d_ma75": "日 75 日线乖离", "d_rsi14": "日 RSI(14)", "d_bbw": "日 布林带宽（÷ 平时）", "d_vr": "日 量比", "d_vr5": "日 5 日量比",
         "d_body": "日 实体（阴阳）", "d_ush": "日 上影", "d_lsh": "日 下影", "d_size": "日 振幅 ÷ ATR", "d_gap": "日 跳空", "d_run": "日 连涨 / 连跌",
         "w_r4": "周 4 周涨跌", "w_r13": "周 13 周涨跌", "w_r26": "周 26 周涨跌", "w_ma13": "周 13 周线乖离", "w_ma13s": "周 13 周线斜率", "w_ma26": "周 26 周线乖离",
         "w_rsi14": "周 RSI(14)", "w_vr": "周 量比", "w_body": "周 实体", "w_ush": "周 上影", "w_lsh": "周 下影", "w_run": "周 连涨 / 连跌", "w_dd52": "周 离 52 周高点",
         "w_pos52": "周 52 周区间位置", "m_r3": "月 3 个月涨跌", "m_r12": "月 12 个月涨跌", "m_ma12": "月 12 个月线乖离", "m_ma12s": "月 12 个月线斜率",
         "m_rsi6": "月 RSI(6)", "m_vr": "月 量比", "m_body": "月 实体", "m_ush": "月 上影", "m_lsh": "月 下影", "m_run": "月 连涨 / 连跌", "m_dd12": "月 离 12 个月高点",
         "sig60": "60 日波动", "lmc": "log 时价总额", "mom12": "12-1 个月动量"}


def report(res: dict) -> str:
    L = [f"# 所有股票的起涨点 / 起跌点 × 日 / 周 / 月线图形（git {res['git']['rev']}{'（脏）' if res['git'].get('dirty') else ''}；只运行一次）", ""]
    c = res["counts"]
    L.append(f"样本 {c['rows']:,} 行（{c['days']} 个样本日，{c['first']}〜{c['last']}）；探索 {c['X']['rows']:,} 行 / 确认 {c['C']['rows']:,} 行；"
             f"起涨点 {c['X']['RS_pct']}% / {c['C']['RS_pct']}%、起跌点 {c['X']['FS_pct']}% / {c['C']['FS_pct']}%（探索 / 确认）；M 中位数 {c['X']['M_median_pct']}%")
    L.append("")
    for mk, r in res["models"].items():
        L.append(f"## {'上涨' if mk == 'rise' else '下跌'}模型（拟合 {r['label']}；训练 {r['n_train']:,} 行、检验 {r['n_test']:,} 行）")
        L.append(f"- AUC：确认 {r['auc']}（基础 {r['auc_base']}；训练 {r['auc_train']}）")
        t, b, tb = r["deciles"][N_DEC - 1], r["deciles"][0], r["deciles_base"][N_DEC - 1]
        L.append(f"- 最高一组：R20x {t['R20x']:+.2f} pp（月聚类区间 {r['top_ci_pp']}）、R40x {t['R40x']:+.2f} pp、U {t['U']}%、D {t['D']}%；"
                 f"最低一组 R20x {b['R20x']:+.2f} pp；基础模型最高一组 R20x {tb['R20x']:+.2f} pp")
        L.append("- 十组 R20x（低 → 高）：" + " / ".join(f"{v['R20x']:+.2f}" for v in r["deciles"].values()))
        L.append("- 按年（最高一组 R20x）：" + "；".join(f"{y} {v['R20x']:+.2f}" for y, v in r["years"].items() if v.get("R20x") is not None))
        L.append(f"- 大型股（时价总额前 {LARGE_N}）：{r['large']}；今天的日経225（只描述）：{r['n225']}")
        L.append("- 系数最大的 10 个（标准化）：" + "、".join(f"{NAMES.get(x['f'], x['f'])} {x['b']:+.3f}" for x in r["coef"][:10]))
        L.append("- 判定：" + "、".join(f"{g} {'✓' if ok else '✗'}" for g, ok in r["gates"].items()) + f" → **{r['tier']}**")
        L.append("")
    for wk in ("X", "C"):
        at = res["atlas"][wk]
        L.append(f"## 图集（{'探索期' if wk == 'X' else '确认期'}）")
        for tf, nm in (("d", "日线"), ("w", "周线"), ("m", "月线")):
            p = at["paths"][tf]
            offs = list(p["RS"].keys())
            pick = [o for o in offs if o in (-60, -26, -24, -20, -13, -12, -10, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 8, 10, 20, 40)]
            L.append(f"- {nm} 平均形状（log ×100，减全部样本）起涨点：" + "、".join(f"{o:+d} {p['RS'][o] - p['ALL'][o]:+.1f}" for o in pick
                                                                      if p['RS'][o] is not None and p['ALL'][o] is not None))
            L.append(f"  起跌点：" + "、".join(f"{o:+d} {p['FS'][o] - p['ALL'][o]:+.1f}" for o in pick if p['FS'][o] is not None and p['ALL'][o] is not None))
        lifts = at["lifts"]
        top_rs = sorted(((f, i, v["q"][i]["RS"]) for f, v in lifts.items() for i in (0, 4)), key=lambda z: -z[2])[:8]
        top_fs = sorted(((f, i, v["q"][i]["FS"]) for f, v in lifts.items() for i in (0, 4)), key=lambda z: -z[2])[:8]
        L.append("- 起涨点最常见（五分位 × 倍数；同一格的起跌点倍数）：" + "；".join(f"{NAMES.get(f, f)} {'最低' if i == 0 else '最高'} 1/5 ×{x:.2f}（起跌 ×{lifts[f]['q'][i]['FS']:.2f}）" for f, i, x in top_rs))
        L.append("- 起跌点最常见：" + "；".join(f"{NAMES.get(f, f)} {'最低' if i == 0 else '最高'} 1/5 ×{x:.2f}（起涨 ×{lifts[f]['q'][i]['RS']:.2f}）" for f, i, x in top_fs))
        pt = at["patterns"]
        ok = {k: v for k, v in pt.items() if v.get("n", 0) >= 200 and v.get("RS") is not None}
        trs = sorted(ok.items(), key=lambda kv: -kv[1]["RS"])[:8]
        tfs = sorted(ok.items(), key=lambda kv: -kv[1]["FS"])[:8]
        L.append("- 经典形态（≥ 200 次）起涨倍数最高：" + "；".join(f"{k} ×{v['RS']}（起跌 ×{v['FS']}，R20x {v['R20x']:+.2f}，n {v['n']}）" for k, v in trs))
        L.append("- 经典形态起跌倍数最高：" + "；".join(f"{k} ×{v['FS']}（起涨 ×{v['RS']}，R20x {v['R20x']:+.2f}，n {v['n']}）" for k, v in tfs))
        L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。读法与档位见脚本开头（登记时写定）。pd_ / pw_ / pm_ = 日 / 周 / 月线上的经典形态（qbreak/candles.PATTERNS）。非投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
