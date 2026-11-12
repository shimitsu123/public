"""minute_study.py — 分钟 K 线 / 日内规则：A 券商侧逆指値 · B 急跌限价买 · C 向上突破追买 · D 日内大跌隔夜反弹
（2026-10-15 登记；登记全文 = var/sim_changes.md 同日「分钟 K 线 / 日内规则」一节；先提交登记、再只运行一次，结果出来不改规则）。

用户（2026-10-15）：「研究按照股票分钟k线的话怎么做策略才会让收益最大化 实时观测所有股票是否出现买卖点等等」。
问题：在立花现物账户的约束下，用分钟 / 日内的价格路径，能不能找到一条规则，扣掉费用和滑点之后比现行 B0 更好
（「收益最大化」= 回撤不变差前提下的年化（Calmar），不是只看毛收益）。不属于任何研究循环、不占循环名额。

两层数据（照实写）：
  T1 = 现有日线缓存（Z / E：Yahoo 27 年复权；W：Yahoo 21 年复权；J / Jx：J-Quants 拆股 + 分红调整后价），2001〜2026-09-30；
  T2 = 这次 --fetch 取的 Yahoo 盘中线（60m 730 天、15m / 5m / 2m 60 天、1m 30 天）与同时取的不复权日线（auto_adjust=False，只按拆股调整）、
       拆股 / 分红记录 → var/cache/minute/yf_<间隔>_<取数日>.parquet（已 gitignore，不入库）；冻结清单 var/minute_study_freeze.json（入库）。
  寄付 / 收盘竞价的成交价一律用不复权日线的正式开盘 / 收盘；分钟线只用来判断「盘中有没有碰到、在哪一根碰到」；
  60m 的时间戳 = 每根的开始时刻；H1（〜2024-11-01）的 15:00 那根 = 收盘竞价（不参与任何触发 / 止损）；H2（2024-11-05〜2026-09-30）
  的 09:00 那根多从 09:05 开始、没有 15:30 的竞价那根；2026-10-01 之后到取数日的数据只描述。
  Yahoo 分钟线不复权，只和同一天的不复权日线一起算；与复权缓存混用 → ValueError（_need_raw）。

格（11 个进 BH，q = 0.10，m 固定 11；不判定的格 p = 1）：A1、A3、B-2c、B-3c、B-2n、B-3n、C1、C2、C3、D1、D2；A2 = 不变差检验，不进 BH。
  A0（基准）= 现行 B0 的离场（固定止损 7%、跟踪 12%、止盈 25%、X6 吊灯、放量阴线（盈利 ≥ 5%）、满 60 天，都按收盘判定 → 次日寄付卖）。
  A1：入场第二天起常挂「通常＋逆指値」：止盈限价 入场 × 1.25；逆指値 max(入场 × 0.93, 峰值 × 0.88)（峰值 = 到昨天为止）；入场当天只按收盘判定。
  A3：只把 −7% 固定止损改成常挂逆指値（入场第二天起），其余照旧按收盘。
  A2：A0 全部照旧 + 入场第二天起另挂卖出逆指値 max(入场 × 0.88, 峰值 × 0.83)；当天已排寄付卖单 → 寄付先卖、逆指値撤掉。
  B-sc / B-sn（s = 2% / 3%）：09:05 限价 L = 正式开盘 ×(1 − s) 向下取到 tick；最低 ≤ L − 1 tick 才成交、成交价 L；当天 / 次日收盘竞价卖。
  C1 / C2：买入逆指値 触发 = 开盘 × 1.02 / 开盘 + 0.5 ×（前一天高 − 低）；成交价 = 触发 × (1 + 0.10%)；当天收盘竞价卖。
  C3（T2，60m）：开盘区间（正式开盘 + 09:00 那根）；r1 > 0 前 2 只；区间高点 + 1 tick 的买入逆指値（10:00〜14:00 那几根有效）；止损 = 区间低点。
  D1 / D2：每天按 正式收盘 ÷ 正式开盘 − 1 取最低 5 只，收盘竞价买；次日寄付 / 次日收盘竞价卖。D-rt（H2、60m 14:00 那根收盘选票）是硬门槛。
判定：见 STAGE1 / A_RULES / A2_RULES / STAGE2 / STAGE3 常量与 stage1_cell / stage1_A / judge_A2（事先写定，登记全文同一套数字）。

运行（在 quant_breakout/ 下）：
  python scripts/minute_study.py --fetch   只取数进缓存、写冻结清单（sha256、行数、yfinance 版本）；冻结清单已存在 → 拒绝
  python scripts/minute_study.py --check   接线核对：只打印条数 / 比例 / MDE / 一致性 / 耗时，不算、不写、不打印任何候选收益
  python scripts/minute_study.py --smoke   只用合成数据跑通流程（同样不算收益），写 var/out/minute_study_partial.{md,json}（已 gitignore）
  python scripts/minute_study.py --run     第一关 + A2 + 描述项（+ 第一关幸存者的第二关），只运行一次 → var/out/minute_study.{md,json}
    拒绝运行：JSON 里已经有 "ran": true；缓存哈希 / 行数与冻结清单不一致；工作区有未提交的改动（被跟踪的文件，或本研究的脚本 / 测试 / 冻结清单还没提交）。
输出只有汇总统计（不写逐笔价格）；代码一律带名字（qbreak/names.label）。非投资建议。
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
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
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak.fees import TACHIBANA_KOBETSU, FeeSchedule, tachibana_teigaku   # noqa: E402
from qbreak.tick import limit_lock, price_limit_jp, round_to_tick, tick_size  # noqa: E402

# ───────────────────────── 常量（事先写定；登记全文同一套数字） ─────────────────────────
SEED = 20261015                                    # 种子 = [SEED, 家族号, s]
FAMILY_NO = {"A": 1, "B": 2, "C": 3, "C3": 4, "D": 5}
FETCH_DATE_FMT = "%Y-%m-%d"
TICK_ON = pd.Timestamp("2026-10-15").date()       # tick 一律用现行粗档（避开 2027-03 起的 STR 分表）
NOTIONAL = 250_000                                 # 判定金额（每边 ¥187 = 0.0748%）
C3_NOTIONAL = 125_000                              # C3 每笔（每边 ¥99）
AFFORD_CAP = 125_000                               # 「一手 ≤ ¥125,000」子集
LOT = 100                                          # 一手（Z / E / J / W 近似；Jx 用真实一手 = 100 × 不复权价，见 lot_notional）
SLIP = 0.0010                                      # 寄付 / 引け竞价、逆指値触发后、成行：每边 0.10%
SLIP_STRESS = 0.0020                               # 压力测试
TICK_FALLBACK = 0.001                              # 还原不了不复权价的「票·日」：1 tick = 价格的 0.1%
FEE = FeeSchedule(tiers=TACHIBANA_KOBETSU)
THRESH = {"B": 0.25, "C1": 0.35, "C2": 0.35, "D": 0.35, "C3": 0.36}   # 各格往返成本（%；登记全文的表，只记录；MDE 与判定都用净门槛 MDE_NET）
CELLS = ("A1", "A3", "B-2c", "B-3c", "B-2n", "B-3n", "C1", "C2", "C3", "D1", "D2")
BH_M, BH_Q = 11, 0.10
SAMPLES = ("Z", "E", "J", "W", "Jx")
JUDGE = {"A": ("Z", "E", "J", "W", "Jx"), "B": ("Z", "W", "Jx"), "C": ("Z", "E", "J", "W", "Jx"), "D": ("Z", "W", "Jx")}
REFERENCE = {"B": ("E", "J"), "D": ("E", "J")}     # E / J 已被 R2 看过：只参考
J_END = "2026-09-30"
WIN = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", J_END),
       "W": ("2006-10-01", "2016-09-30"), "Jx": ("2017-01-04", J_END)}
HALF_OF = {"Z": "Z", "E": "E", "J": "J", "W": "E", "Jx": "J"}           # W 用 E 的两半、Jx 用 J 的两半
H1_END = "2024-11-01"                                                    # 60m 的 H1 = 开头〜2024-11-01
H2 = ("2024-11-05", J_END)                                               # H2 = 2024-11-05〜2026-09-30（之后只描述）
TURNOVER_MIN = 5e8                                                       # W / Jx：到前一天为止的 20 日平均売買代金 ≥ ¥5 亿
BAD_DATA_SHARE = 0.20                                                    # 「开盘 = 前日收盘」或「O = H = L = C」> 20% → 数据不合格
STAGE1 = {"mean_min": 0.10, "t_min": 2.0, "min_n": 300, "c3_min_n": 200, "placebo_n": 400, "placebo_q": 95.0,
          "afford_min_n": 100, "jx_min": 0.10, "drt_share": 0.50}
A_RULES = {"diff_min": 0.20, "t_min": 2.0, "pooled_min_n": 1000, "each_min_n": 50}
A2_RULES = {"diff_min": -0.10, "cagr_tol": 0.20, "calmar_tol": 0.02, "dd_tol": 1.0}
A_STOP = {"A1": None, "A2": (0.88, 0.83), "A3": None}                    # A2：两条收盘线各再往下 5pp
MDE_POWER = 0.80
MDE_ALPHA = BH_Q / BH_M
STAGE2 = {"S1_sum_min": 0.03, "S2_era_tol": 0.02, "S3_dd_tol": 2.0, "placebo_n": 400, "sleeve_pct": 0.25,
          "bc_pick": 2, "bc_lot_cap": AFFORD_CAP, "bn_max_hold": 2, "d_pick": 1, "d_lot_div": 2, "c3_pick": 2,
          "no_rebuy_days": 20, "core_ref": "1545.T", "capital": 1_000_000}
STAGE3 = {"min_days": 60, "min_trades": 100, "c3_min_days": 120, "share_of_stage1": 0.50,
          "file": "var/out/intraday_{cell}_forward.csv"}
DESC_SEEDS, OUTAGE_P = 200, 0.02
ALIGN_MIN, AUCTION_MIN = 0.95, 0.90                                      # 接线核对 2 的一致率门槛（事先写定）
OUT = "minute_study"
FREEZE = "minute_study_freeze.json"
MINUTE_DIR = "minute"
INTERVALS = {"60m": "730d", "15m": "60d", "5m": "60d", "2m": "60d"}
ONE_MIN_DAYS, ONE_MIN_CHUNK = 30, 7
DAILY_PERIOD = "5y"                                                      # 不复权日线：覆盖 60m 窗口 + 指标热身（realism_at 要 ≥ 300 根）
BATCH, PAUSE_S = 40, 2.0
ETFS = ("1321.T", "1306.T")
LINES: list[str] = []
MODE = {"name": "run"}                                                   # fetch / check / smoke / run（check / smoke 不许算收益）


class ReturnGuardError(RuntimeError):
    """--check / --smoke 里调用了算收益的函数。"""


def set_mode(name: str) -> None:
    MODE["name"] = name


def guard_returns(what: str) -> None:
    """所有「候选 / 基准的收益」都先过这一道：--check / --smoke 一律拒绝（登记：两者不算、不写、不打印任何收益）。"""
    if MODE["name"] in ("check", "smoke", "fetch"):
        raise ReturnGuardError(f"--{MODE['name']} 不许算收益（{what}）")


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def lab(t: str) -> str:
    from qbreak.names import label
    return label(t)


def _r(x, d: int = 3):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, d) if np.isfinite(f) else None


# ───────────────────────── 统计 ─────────────────────────
def _betacf(a: float, b: float, x: float) -> float:
    """不完全 β 函数的连分式（Lentz 法；Numerical Recipes 6.4）。"""
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 10000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """正则化不完全 β 函数 I_x(a, b)。"""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    bt = math.exp(lbt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: float) -> float:
    """Student-t 的单边上尾 P(T > t)（自由度 df > 0）；不用正态近似。t / df 算不出 → nan。"""
    try:
        t, df = float(t), float(df)
    except (TypeError, ValueError):
        return float("nan")
    if not (np.isfinite(t) and np.isfinite(df)) or df <= 0:
        return float("nan")
    x = df / (df + t * t)
    tail = 0.5 * betainc(df / 2.0, 0.5, x)                                 # P(|T| > |t|) / 2
    return tail if t >= 0 else 1.0 - tail


def t_isf(q: float, df: float) -> float:
    """t_sf 的反函数（二分）：P(T > x) = q。"""
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_sf(mid, df) > q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def apply_bh(pvals: dict[str, float | None], q: float = BH_Q, m: int = BH_M) -> dict[str, bool]:
    """BH：m 固定 11；不判定（None / nan）的格 p = 1；格数不足 m 时用 p = 1 补足。"""
    from qbreak.factor_combo import bh
    keys = list(CELLS)
    p = []
    for k in keys:
        v = pvals.get(k)
        p.append(1.0 if v is None or not np.isfinite(v) else float(v))
    while len(p) < m:
        p.append(1.0)
    rej = bh(np.array(p[:max(m, len(keys))], float), q)
    return {k: bool(rej[i]) for i, k in enumerate(keys)}


def month_t(dates, vals) -> dict:
    """按日历月聚类（不同样本的同一个月算同一个簇）：{n, mean（%）, months, t, p（单边，t_sf(t, 簇数 − 1)）}。
    vals 是小数收益（不是 %）。口径同 exec_timing_study.clustered 的 n / mean / t（mean ×100）。"""
    d = pd.DataFrame({"date": pd.to_datetime(pd.Series(list(dates))), "v": np.asarray(vals, float)}).dropna()
    if d.empty:
        return {"n": 0, "mean": None, "months": 0, "t": None, "p": None}
    mm = d.groupby(d["date"].dt.to_period("M"))["v"].mean()
    k = len(mm)
    se = mm.std(ddof=1) / math.sqrt(k) if k > 1 else float("nan")
    t = float(mm.mean() / se) if se and np.isfinite(se) and se > 0 else None
    return {"n": int(len(d)), "mean": float(d["v"].mean() * 100), "median": float(d["v"].median() * 100),
            "win": float((d["v"] > 0).mean() * 100), "months": int(k), "t": t,
            "p": (t_sf(t, k - 1) if t is not None and k > 1 else None)}


def half_bounds(sample: str) -> tuple[tuple[str, str], tuple[str, str]]:
    """样本 → (前半, 后半)（scripts/leap_common.HALVES；W 用 E 的、Jx 用 J 的；J 的后半到 J_END）。"""
    import leap_common as LM
    (a1, b1), (a2, b2) = LM.HALVES[HALF_OF[sample]]
    return (a1, b1), (a2, b2 or J_END)


def half_of(sample: str, dates) -> np.ndarray:
    """每个日期属于前半（1）/ 后半（2）/ 都不是（0）。"""
    d = pd.to_datetime(pd.Series(list(dates))).to_numpy()
    (a1, b1), (a2, b2) = half_bounds(sample)
    h = np.zeros(len(d), int)
    h[(d >= np.datetime64(pd.Timestamp(a1))) & (d <= np.datetime64(pd.Timestamp(b1)))] = 1
    h[(d >= np.datetime64(pd.Timestamp(a2))) & (d <= np.datetime64(pd.Timestamp(b2)))] = 2
    return h


# ───────────────────────── 成本与成交 ─────────────────────────
def fee_pct(notional: float, course: str = "kobetsu") -> float:
    """一边的手续费占约定金额的比例（小数）。個別コース按 fees.TACHIBANA_KOBETSU；定額コース按一天合计（这里当作只有这一笔）。"""
    x = float(notional)
    if x <= 0:
        return float("nan")
    f = FEE(x) if course == "kobetsu" else tachibana_teigaku(x)
    return f / x


def rt_cost(notional: float = NOTIONAL, slip_in: float = 0.0, slip_out: float = 0.0, course: str = "kobetsu") -> float:
    """往返成本（小数）= 两边手续费 + 进出两边的滑点。¥250,000 → 0.1496% + 滑点。"""
    return 2 * fee_pct(notional, course) + slip_in + slip_out


def lot_notional(raw_px: float, lot: int = LOT) -> float:
    """一手的实际金额（円）= 一手股数 × 不复权价（Jx / J：真实一手 = 100 × 不复权价，与 jq_study.RealLotEngine 同一换算）。"""
    return float(lot) * float(raw_px) if raw_px == raw_px and raw_px > 0 else float("nan")


def tick_of(raw_px: float) -> float:
    """不复权价上的 1 tick（现行粗档）；价格算不出 → nan。"""
    if not (raw_px == raw_px) or raw_px <= 0:
        return float("nan")
    return tick_size(float(raw_px), None, on=TICK_ON)


def tick_adj(px_adj: float, factor: float) -> float:
    """复权价 px_adj（不复权 = px_adj × factor）上的 1 tick，换回复权单位；factor 缺 → 价格的 0.1%。"""
    if factor == factor and factor > 0:
        return tick_of(px_adj * factor) / factor
    return px_adj * TICK_FALLBACK


def floor_tick_adj(px_adj: float, factor: float) -> float:
    """向下取到 tick（买单）：在不复权价上取整，再换回复权单位。"""
    if factor == factor and factor > 0:
        return round_to_tick(px_adj * factor, None, "BUY", on=TICK_ON) / factor
    u = px_adj * TICK_FALLBACK
    return math.floor(px_adj / u + 1e-9) * u


def ceil_tick_adj(px_adj: float, factor: float) -> float:
    """向上取到 tick（逆指値的触发价：对自己不利的方向）。"""
    if factor == factor and factor > 0:
        return round_to_tick(px_adj * factor, None, "SELL", on=TICK_ON) / factor
    u = px_adj * TICK_FALLBACK
    return math.ceil(px_adj / u - 1e-9) * u


def limit_band(prev_c_adj: float, factor_prev: float, factor: float) -> tuple[float, float]:
    """当天的制限値幅（复权单位）：按前日收盘的不复权价查表；factor 缺 → 用复权价查表（照实报比例）。"""
    if factor_prev == factor_prev and factor_prev > 0 and factor == factor and factor > 0:
        base = prev_c_adj * factor                                          # 前日收盘换成当天的口径
        w = price_limit_jp(base)
        return (base - w) / factor, (base + w) / factor
    w = price_limit_jp(prev_c_adj)
    return prev_c_adj - w, prev_c_adj + w


def limit_buy_fill(lim: float, low: float, tick: float) -> float | None:
    """限价买：最低 ≤ 限价 − 1 tick 才算成交（只碰到不算），成交价 = 限价、0 滑点。"""
    if not (lim == lim and low == low and tick == tick) or lim <= 0:
        return None
    return float(lim) if low <= lim - tick + 1e-12 * max(1.0, lim) else None


def stop_sell_fill(trig: float, o: float, low: float) -> float | None:
    """卖出逆指値（滑点另算）：开盘 ≤ 触发 → 按开盘；否则最低 ≤ 触发 → 按触发；否则不成交。"""
    if not (trig == trig) or trig <= 0:
        return None
    if o <= trig:
        return float(o)
    if low <= trig:
        return float(trig)
    return None


def stop_buy_fill(trig: float, o: float, high: float, cap: float = float("inf")) -> float | None:
    """买入逆指値（滑点另算）：触发超出当天制限値幅上限 cap → 不成交；开盘 ≥ 触发 → 按开盘；最高 ≥ 触发 → 按触发。"""
    if not (trig == trig) or trig <= 0 or trig > cap + 1e-9 * max(1.0, cap):
        return None
    if o >= trig:
        return float(o)
    if high >= trig:
        return float(trig)
    return None


def lock(prev_c: float, h: float, l: float, c: float, factor_prev: float = 1.0, factor: float = 1.0) -> str | None:
    """制限値幅锁死（qbreak.tick.limit_lock，按还原后的不复权价；系数缺 → 按复权价）。
    基准 = 前日收盘换成「当天的口径」（复权价 × 当天的系数）：拆股 / 除权当天交易所的基准值段也按新口径。"""
    fp_ok = factor_prev == factor_prev and factor_prev > 0
    f_ok = factor == factor and factor > 0
    if fp_ok and f_ok:
        return limit_lock(prev_c * factor, h * factor, l * factor, c * factor, "JP")
    return limit_lock(prev_c, h, l, c, "JP")


# ───────────────────────── 数据：取数、缓存、冻结 ─────────────────────────
def minute_dir() -> Path:
    return paths.sub("cache") / MINUTE_DIR


def freeze_path() -> Path:
    return paths.home() / FREEZE


def out_path(ext: str, partial: bool = False) -> Path:
    return paths.sub("out") / f"{OUT}{'_partial' if partial else ''}.{ext}"


def cache_path(kind: str, fetch_date: str) -> Path:
    """kind：60m / 15m / 5m / 2m / 1m / 1d_raw / actions。"""
    return minute_dir() / f"yf_{kind}_{fetch_date}.parquet"


def fetch_tickers() -> list[str]:
    """今天的日経225（universe("JP", "broad")）+ 1321 / 1306（描述项 1 的 ETF）。"""
    from qbreak.config import universe
    return list(universe("JP", "broad")) + [t for t in ETFS]


def _yf():
    import yfinance as yf
    for nm in ("yfinance", "yfinance.data", "yfinance.utils", "peewee"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    return yf


def bars(tickers: list[str], interval: str, period: str | None = None, start=None, end=None) -> dict[str, pd.DataFrame]:
    """exec_timing_study.hourly 的参数化版：每批 40 只、threads=False、auto_adjust=False、转成 Asia/Tokyo、只留 OHLCV。
    period 必须写成 "Nd"（start= / "max" 只按自然日给 60 / 730 天）；1m 用 start / end 分段。"""
    yf = _yf()
    out: dict[str, pd.DataFrame] = {}
    for k in range(0, len(tickers), BATCH):
        batch = tickers[k:k + BATCH]
        kw = {"period": period} if period else {"start": start, "end": end}
        raw = None
        for attempt in range(3):
            try:
                raw = yf.download(batch, interval=interval, auto_adjust=False, progress=False, group_by="ticker",
                                  threads=False, **kw)
                break
            except Exception as e:                                       # noqa: BLE001
                print(f"  {interval} 第 {k // BATCH + 1} 批失败（{type(e).__name__}），{attempt + 1}/3", flush=True)
                time.sleep(PAUSE_S * (attempt + 2))
        time.sleep(PAUSE_S)
        if raw is None or raw.empty:
            continue
        for t in batch:
            try:
                h = raw[t].dropna(how="all") if isinstance(raw.columns, pd.MultiIndex) else raw.dropna(how="all")
            except KeyError:
                continue
            if h.empty or "Close" not in h.columns:
                continue
            h = h.copy()
            if h.index.tz is not None:
                h.index = h.index.tz_convert("Asia/Tokyo")
            out[t] = h[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return out


def bars_1m(tickers: list[str], days: int = ONE_MIN_DAYS, today: pd.Timestamp | None = None) -> dict[str, pd.DataFrame]:
    """1m：每次最多 8 天 → 按 7 天一段分段取（最多回溯 30 个自然日），按时间戳去重合并。"""
    today = (today or pd.Timestamp.now(tz="Asia/Tokyo")).normalize().tz_localize(None)
    edges = []
    end = today + pd.Timedelta(days=1)
    lo = today - pd.Timedelta(days=days - 1)
    while end > lo:
        st = max(lo, end - pd.Timedelta(days=ONE_MIN_CHUNK))
        edges.append((st, end))
        end = st
    parts: dict[str, list] = {}
    for st, en in reversed(edges):
        got = bars(tickers, "1m", start=st.strftime("%Y-%m-%d"), end=en.strftime("%Y-%m-%d"))
        for t, h in got.items():
            parts.setdefault(t, []).append(h)
    out = {}
    for t, hs in parts.items():
        h = pd.concat(hs).sort_index()
        out[t] = h[~h.index.duplicated(keep="last")]
    return out


def daily_raw(tickers: list[str], period: str = DAILY_PERIOD) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """不复权日线（Yahoo auto_adjust=False：价格只按拆股调整，与分钟线同一口径）+ 拆股 / 分红记录（actions=True）。"""
    yf = _yf()
    px, acts = {}, {}
    for k in range(0, len(tickers), BATCH):
        batch = tickers[k:k + BATCH]
        raw = None
        for attempt in range(3):
            try:
                raw = yf.download(batch, period=period, interval="1d", auto_adjust=False, actions=True, progress=False,
                                  group_by="ticker", threads=False)
                break
            except Exception as e:                                       # noqa: BLE001
                print(f"  1d 第 {k // BATCH + 1} 批失败（{type(e).__name__}），{attempt + 1}/3", flush=True)
                time.sleep(PAUSE_S * (attempt + 2))
        time.sleep(PAUSE_S)
        if raw is None or raw.empty:
            continue
        for t in batch:
            try:
                h = raw[t].dropna(how="all") if isinstance(raw.columns, pd.MultiIndex) else raw.dropna(how="all")
            except KeyError:
                continue
            if h.empty or "Close" not in h.columns:
                continue
            h = h.copy()
            h.index = pd.DatetimeIndex(h.index).tz_localize(None).normalize() if h.index.tz is not None else pd.DatetimeIndex(h.index)
            cols = {"Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Adj Close": "AdjClose", "Volume": "Volume"}
            px[t] = h[[c for c in cols if c in h.columns]].rename(columns=cols).astype(float)
            dv = pd.to_numeric(h.get("Dividends", pd.Series(0.0, index=h.index)), errors="coerce").fillna(0.0)
            sp = pd.to_numeric(h.get("Stock Splits", pd.Series(0.0, index=h.index)), errors="coerce").fillna(0.0)
            a = pd.DataFrame({"div": dv, "split": sp})
            acts[t] = a[(a["div"] > 0) | ((a["split"] > 0) & (a["split"] != 1.0))]
    return px, acts


def to_long(d: dict[str, pd.DataFrame], key: str = "ts") -> pd.DataFrame:
    """{票: 表} → 长表（ticker, ts / date, 各列），按票、时间排序（哈希稳定）。"""
    parts = []
    for t in sorted(d):
        x = d[t].copy()
        x.index.name = key
        x = x.reset_index()
        x.insert(0, "ticker", t)
        parts.append(x)
    if not parts:
        return pd.DataFrame(columns=["ticker", key])
    return pd.concat(parts, ignore_index=True).sort_values(["ticker", key], kind="mergesort").reset_index(drop=True)


def from_long(df: pd.DataFrame, key: str = "ts") -> dict[str, pd.DataFrame]:
    out = {}
    for t, g in df.groupby("ticker", sort=True):
        x = g.drop(columns=["ticker"]).set_index(key).sort_index()
        x.attrs["basis"] = "raw"                                           # Yahoo 不复权（只按拆股调整）
        out[str(t)] = x
    return out


def sha256_file(fp: Path) -> str:
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_cache(kind: str, fetch_date: str, df: pd.DataFrame) -> dict:
    fp = cache_path(kind, fetch_date)
    fp.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(fp, index=False)
    key = "ts" if "ts" in df.columns else "date"
    info = {"file": fp.name, "sha256": sha256_file(fp), "rows": int(len(df)),
            "tickers": int(df["ticker"].nunique()) if len(df) else 0}
    if len(df) and key in df.columns:
        info["first"], info["last"] = str(pd.Timestamp(df[key].min())), str(pd.Timestamp(df[key].max()))
    return info


def load_cache(kind: str, fetch_date: str) -> dict[str, pd.DataFrame]:
    fp = cache_path(kind, fetch_date)
    df = pd.read_parquet(fp)
    key = "ts" if "ts" in df.columns else "date"
    if kind == "actions":
        return from_long(df, "date")
    return from_long(df, key)


def freeze_manifest(files: dict, missing: dict, fetch_date: str, tickers: list[str]) -> dict:
    import yfinance as yf
    return {"fetch_date": fetch_date, "fetched_at": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(timespec="seconds"),
            "yfinance": yf.__version__, "pandas": pd.__version__, "tickers": len(tickers), "files": files,
            "missing": {k: sorted(v) for k, v in missing.items()}}


def read_manifest() -> dict | None:
    fp = freeze_path()
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def verify_manifest(man: dict | None) -> list[str]:
    """缓存文件的 sha256 / 行数与冻结清单逐个比；返回不一致的说明（空 = 一致）。"""
    if not man:
        return ["没有冻结清单（先 --fetch）"]
    bad = []
    files = man.get("files") or {}
    need = [*INTERVALS, "1m", "1d_raw", "actions"]
    gone = [k for k in need if k not in files]
    if gone:
        bad.append(f"冻结清单里少了 {'、'.join(gone)}")
    for kind, info in files.items():
        if kind in need and info.get("file") != cache_path(kind, str(man.get("fetch_date"))).name:
            bad.append(f"{kind} 的文件名 {info.get('file')} ≠ 读取时用的 {cache_path(kind, str(man.get('fetch_date'))).name}")
            continue
        fp = minute_dir() / info["file"]
        if not fp.exists():
            bad.append(f"{info['file']} 不存在")
            continue
        h = sha256_file(fp)
        if h != info["sha256"]:
            bad.append(f"{info['file']} sha256 不一致（{h[:12]} ≠ {info['sha256'][:12]}）")
            continue
        n = len(pd.read_parquet(fp, columns=["ticker"]))
        if n != info["rows"]:
            bad.append(f"{info['file']} 行数不一致（{n} ≠ {info['rows']}）")
    try:
        import yfinance as yf
        if yf.__version__ != man.get("yfinance"):
            bad.append(f"yfinance 版本 {yf.__version__} ≠ 冻结时 {man.get('yfinance')}（只记录，不影响缓存）")
    except Exception:                                                     # noqa: BLE001
        pass
    return bad


def hard_mismatch(bad: list[str]) -> list[str]:
    """拒绝运行的不一致（yfinance 版本只记录）。"""
    return [b for b in bad if "只记录" not in b]


def do_fetch(today: pd.Timestamp | None = None) -> int:
    """--fetch：只取数进缓存，写冻结清单。冻结清单已存在 → 拒绝（数据冻结后不重取、不补取）。"""
    if freeze_path().exists():
        say(f"冻结清单 {freeze_path().name} 已存在 → 不重取（数据冻结后不补取）")
        return 2
    t0 = time.time()
    today = today or pd.Timestamp.now(tz="Asia/Tokyo")
    fd = today.strftime(FETCH_DATE_FMT)
    tickers = fetch_tickers()
    say(f"# 取数 {fd}（{len(tickers)} 只：日経225 今天的成分 + {'、'.join(lab(t) for t in ETFS)}）")
    files, missing = {}, {}
    for iv, per in INTERVALS.items():
        d = bars(tickers, iv, period=per)
        missing[iv] = [t for t in tickers if t not in d]
        files[iv] = save_cache(iv, fd, to_long(d))
        say(f"- {iv}（period={per}）：{len(d)} 只、{files[iv]['rows']:,} 行、{files[iv].get('first', '—')} 〜 {files[iv].get('last', '—')}（{time.time() - t0:.0f}s）")
    d = bars_1m(tickers, today=today)
    missing["1m"] = [t for t in tickers if t not in d]
    files["1m"] = save_cache("1m", fd, to_long(d))
    say(f"- 1m（{ONE_MIN_CHUNK} 天一段，回溯 {ONE_MIN_DAYS} 个自然日）：{len(d)} 只、{files['1m']['rows']:,} 行（{time.time() - t0:.0f}s）")
    px, acts = daily_raw(tickers)
    missing["1d_raw"] = [t for t in tickers if t not in px]
    files["1d_raw"] = save_cache("1d_raw", fd, to_long(px, "date"))
    files["actions"] = save_cache("actions", fd, to_long(acts, "date"))
    say(f"- 1d 不复权（period={DAILY_PERIOD}）：{len(px)} 只、{files['1d_raw']['rows']:,} 行；拆股 / 分红记录 {files['actions']['rows']:,} 行")
    man = freeze_manifest(files, missing, fd, tickers)
    freeze_path().write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for iv, ms in missing.items():
        if ms:
            say(f"- {iv} 拿不到：{'、'.join(lab(t) for t in ms)}（照实列出，不补取）")
    say(f"冻结清单 → {freeze_path().relative_to(ROOT)}（{time.time() - t0:.0f}s）")
    return 0



# ───────────────────────── T2：盘中线的结构 ─────────────────────────
def session(d) -> str | None:
    """日期 → H1（〜2024-11-01）/ H2（2024-11-05〜2026-09-30）/ post（之后到取数日，只描述）。"""
    d = pd.Timestamp(d).normalize()
    if d <= pd.Timestamp(H1_END):
        return "H1"
    if pd.Timestamp(H2[0]) <= d <= pd.Timestamp(H2[1]):
        return "H2"
    if d > pd.Timestamp(H2[1]):
        return "post"
    return None


def _need_raw(*frames) -> None:
    """T2 只准用 Yahoo 不复权（只按拆股调整）的日线与分钟线；复权缓存混进来 → ValueError。"""
    for f in frames:
        if f is None:
            continue
        b = getattr(f, "attrs", {}).get("basis")
        if b != "raw":
            raise ValueError(f"复权日线与分钟线不能混用（basis = {b!r}；T2 只用 --fetch 取的不复权日线）")


def day_groups(h: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    """一只票的 60m（或 5m）→ {日期: 当天的根（索引 = 开始时刻）}。"""
    _need_raw(h)
    out = {}
    if h is None or not len(h):
        return out
    dd = pd.DatetimeIndex(h.index).tz_localize(None).normalize() if h.index.tz is not None else pd.DatetimeIndex(h.index).normalize()
    for d, x in h.groupby(dd):
        out[pd.Timestamp(d)] = x
    return out


def usable_bars(x: pd.DataFrame, sess: str | None) -> pd.DataFrame:
    """当天能用来判断触发 / 止损的 60m 根：H1 去掉 15:00 那根（= 收盘竞价那一个价）。"""
    if sess == "H1":
        return x[x.index.hour != 15]
    return x


def bar_at(x: pd.DataFrame, hour: int, minute: int = 0):
    """当天开始时刻为 hour:minute 的那一根（没有 → None）。"""
    m = (x.index.hour == hour) & (x.index.minute == minute)
    return x[m].iloc[0] if m.any() else None


def synth_hourly(m5: pd.DataFrame) -> pd.DataFrame:
    """5m → 按「开始时刻的钟点」合成 60m（12 点那根 = 12:30〜12:59；15 点那根 = 15:00〜15:24）。"""
    _need_raw(m5)
    if m5 is None or not len(m5):
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    key = m5.index.floor("h")
    g = m5.groupby(key)
    out = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(), "Close": g["Close"].last(),
                        "Volume": g["Volume"].sum()})
    return out


def align_check(h60: dict, m5: dict, d1: dict) -> dict:
    """接线核对 2：60m 与 5m 合成在重叠日子的一致性（时间戳 = 开始时刻）；H1 的 15:00 那根 = 收盘竞价（量 0、收盘 ≈ 正式收盘）。
    对不上 → C3 作废（不改定义）。只数条数 / 比例，不算任何收益。"""
    same = {k: 0 for k in ("O", "H", "L", "C")}
    tot, starts_ok, starts_tot = 0, 0, 0
    v9_zero, v9_tot = 0, 0
    for t, h in h60.items():
        _need_raw(h)
        starts_tot += len(h)
        starts_ok += int(((h.index.minute == 0) & np.isin(h.index.hour, [9, 10, 11, 12, 13, 14, 15])).sum())
        if t not in m5:
            continue
        s = synth_hourly(m5[t])
        both = h.index.intersection(s.index)
        both = both[(both.hour >= 10) & (both.hour <= 14)]                         # 09:00 那根的量 / 15:00 那根另看
        for k, c in (("O", "Open"), ("H", "High"), ("L", "Low"), ("C", "Close")):
            a, b = h.loc[both, c].to_numpy(float), s.loc[both, c].to_numpy(float)
            same[k] += int((np.abs(a - b) <= 1e-6 * np.maximum(1.0, np.abs(a))).sum())
        tot += len(both)
        b9 = h.index[(h.index.hour == 9)]
        b9 = b9[[session(x.tz_localize(None)) == "H2" or session(x.tz_localize(None)) == "post" for x in b9]] if len(b9) else b9
        v9_tot += len(b9)
        v9_zero += int((h.loc[b9, "Volume"].to_numpy(float) == 0).sum()) if len(b9) else 0
    auc_vol0 = auc_close = auc_tot = 0
    for t, h in h60.items():
        d = d1.get(t)
        if d is None:
            continue
        x = h[h.index.hour == 15]
        if not len(x):
            continue
        dd = x.index.tz_localize(None).normalize() if x.index.tz is not None else x.index.normalize()
        h1 = np.array([session(z) == "H1" for z in dd])
        if not h1.any():
            continue
        x, dd = x[h1], dd[h1]
        oc = d["Close"].reindex(dd).to_numpy(float)
        ok = np.isfinite(oc)
        auc_tot += int(ok.sum())
        auc_vol0 += int((x["Volume"].to_numpy(float)[ok] == 0).sum())
        auc_close += int((np.abs(x["Close"].to_numpy(float)[ok] / oc[ok] - 1) <= 0.005).sum())
    share = {k: (v / tot if tot else None) for k, v in same.items()}
    res = {"bars_10_14_compared": tot, "match_share": {k: _r(v, 4) for k, v in share.items()},
           "start_stamp_share": _r(starts_ok / starts_tot, 4) if starts_tot else None,
           "h2_0900_vol0_share": _r(v9_zero / v9_tot, 4) if v9_tot else None,
           "h1_1500_bars": auc_tot, "h1_1500_vol0_share": _r(auc_vol0 / auc_tot, 4) if auc_tot else None,
           "h1_1500_close_share": _r(auc_close / auc_tot, 4) if auc_tot else None}
    ok = (tot > 0 and all((v or 0) >= ALIGN_MIN for v in share.values()) and (res["start_stamp_share"] or 0) >= ALIGN_MIN
          and auc_tot > 0 and (res["h1_1500_vol0_share"] or 0) >= AUCTION_MIN and (res["h1_1500_close_share"] or 0) >= AUCTION_MIN)
    res["ok"] = bool(ok)
    return res


def split_after(acts: pd.DataFrame | None, dates: pd.DatetimeIndex) -> np.ndarray:
    """Yahoo 的价格按取数日为止的全部拆股调整过：真实不复权价 = 价格 × 之后（不含当天）各次拆股比例的乘积。"""
    out = np.ones(len(dates))
    if acts is None or not len(acts):
        return out
    sp = acts["split"] if "split" in acts.columns else pd.Series(dtype=float)
    sp = sp[(sp > 0) & (sp != 1.0)]
    for d, r in sp.items():
        out[np.asarray(dates < pd.Timestamp(d))] *= float(r)
    return out



# ───────────────────────── T1：日线宽表（复权价 + 还原系数 + 合格掩码） ─────────────────────────
def _meta_actions(t: str, years: int) -> dict | None:
    """日线缓存（qbreak.data）的 meta 里存的公司行为：{"div": {日期: 分红率 %}, "split": {日期: 比例}}；没有 → None。"""
    fp = paths.sub("cache") / f"{t}_{years}y.meta.json"
    if not fp.exists():
        return None
    try:
        return (json.loads(fp.read_text(encoding="utf-8")) or {}).get("actions")
    except Exception:                                                     # noqa: BLE001
        return None


def yahoo_factors(acts: dict | None, days: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Yahoo 复权价（qbreak.data.adjust_prices）→ (拆股系数 S, 分红系数 Dv, 除权日 ex)：
    不复权价 = 复权价 × S ÷ Dv；S = 之后各次拆股比例的乘积，Dv = 之后各次除息 (1 − 分红率)；ex[i] = 持有 i−1 → i 跨过除权 / 拆股。"""
    n = len(days)
    S, Dv, ex = np.ones(n), np.ones(n), np.zeros(n, bool)
    if acts is None:
        return np.full(n, np.nan), np.full(n, np.nan), ex
    for kind in ("div", "split"):
        for d, v in (acts.get(kind) or {}).items():
            x = pd.Timestamp(d)
            before = np.asarray(days < x)
            if kind == "div":
                y = float(v) / 100.0
                if 0 < y < 1:
                    Dv[before] *= 1.0 - y
            else:
                r = float(v)
                if r > 0 and r != 1.0:
                    S[before] *= r
            k = int(days.searchsorted(x, side="left"))                       # 除权日（或之后第一个交易日）
            if 0 < k < n:
                ex[k] = True
    return S, Dv, ex


def _act_cache(t: str) -> pd.DataFrame | None:
    """scripts/leap_data.actions 的缓存（只读，不联网）：[close_raw（Yahoo 只按拆股调整的收盘）, div]。"""
    import leap_data as LD
    fp = LD._act_path(t)
    if not fp.exists():
        return None
    try:
        return pd.read_csv(fp, index_col=0, parse_dates=True)
    except Exception:                                                     # noqa: BLE001
        return None


def jq_factors(Pc: np.ndarray, ratio: np.ndarray, act: pd.DataFrame | None, days: pd.DatetimeIndex
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """J-Quants（拆股 + 分红调整后价，qbreak/pit_data.adjust + div_adjust）→ (S, Dv, ex)。
    S = 真实一手比例 J_R（不复权 = 拆股调整价 × J_R）；Dv = 分红系数：用 leap_data 的分红缓存（div_adjust 同一来源）切段，
    每段取「调整后收盘 ÷ Yahoo 只按拆股调整的收盘」的中位数（稳健；与 J-Quants 数据终点之后的除息有没有算进去无关）；
    最后一段 Dv 不在 [0.80, 1.05] → 拆股基准对不上 → 这只还原不了（nan）。ex = J_R 变化（拆股）或除息日。"""
    n = len(days)
    S = np.asarray(ratio, float).copy()
    ex = np.zeros(n, bool)
    rr = S / np.roll(S, 1)
    ex[1:] |= np.isfinite(rr[1:]) & (np.abs(rr[1:] - 1) > 1e-9)
    if act is None or not len(act):
        return S, np.full(n, np.nan), ex
    dv = act["div"].fillna(0.0)
    dv = dv[dv > 0]
    cuts = sorted({int(days.searchsorted(pd.Timestamp(x), side="left")) for x in dv.index})
    cuts = [k for k in cuts if 0 < k < n]
    for k in cuts:
        ex[k] = True
    cr = act["close_raw"].reindex(days).to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = Pc / cr
    Dv = np.full(n, np.nan)
    edges = [0] + cuts + [n]
    for a, b in zip(edges[:-1], edges[1:]):
        seg = r[a:b]
        seg = seg[np.isfinite(seg) & (seg > 0)]
        if len(seg) >= 3:
            Dv[a:b] = float(np.median(seg))
    last = Dv[np.isfinite(Dv)]
    if not len(last) or not (0.80 <= last[-1] <= 1.05):
        return S, np.full(n, np.nan), ex
    return S, Dv, ex


def _roll_prev_mean(X: np.ndarray, w: int = 20, minp: int = 15) -> np.ndarray:
    """每列：到前一行为止的 w 行平均（缺值跳过，至少 minp 个）。"""
    return pd.DataFrame(X).rolling(w, min_periods=minp).mean().shift(1).to_numpy(float)


def _prev_row(X: np.ndarray) -> np.ndarray:
    out = np.full_like(X, np.nan, dtype=float)
    out[1:] = X[:-1]
    return out


def build_panel(name: str, P: dict, days: pd.DatetimeIndex, names: list[str], S: np.ndarray, Dv: np.ndarray,
                ex: np.ndarray, member: np.ndarray | None = None, turnover: bool = False) -> dict:
    """一个样本的宽表 + 合格掩码（「票·日」）。P = 复权价 {O, H, L, C, V}（days × names）。"""
    O, H, L, C, V = (np.asarray(P[k], float) for k in "OHLCV")
    F = S / Dv
    a, b = WIN[name]
    inwin = np.asarray((days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b)))[:, None]
    has = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (O > 0) & (C > 0) & np.isfinite(V) & (V > 0)
    Cp, Fp, hasp = _prev_row(C), _prev_row(F), np.zeros_like(has)
    hasp[1:] = has[:-1]
    tol = 1e-9 * np.fmax(1.0, np.abs(H))
    with np.errstate(invalid="ignore", divide="ignore"):
        consistent = (L <= O + tol) & (O <= H + tol) & (L <= C + tol) & (C <= H + tol)
        base_raw = np.where(np.isfinite(Fp) & np.isfinite(F), Cp * F, Cp)          # 前日收盘换成当天的口径（拆股日的基准值段同样）
        lim = np.vectorize(lambda x: price_limit_jp(x) / x if x == x and x > 0 else np.nan, otypes=[float])(base_raw)
        ov, intr = O / Cp - 1, C / O - 1
        over = (np.abs(ov) > lim + 1e-9) | (np.abs(intr) > lim + 1e-9)
    both = has & hasp & inwin
    mem = np.ones_like(has) if member is None else np.asarray(member, bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        tv = np.where(has, C * V / np.where(np.isfinite(Dv), Dv, 1.0), np.nan)      # 売買代金（円）= 复权收盘 × 复权量 ÷ 分红系数
    turn = _roll_prev_mean(tv)                                                    # 到前一天为止的 20 日平均（第二关的排序也用）
    ok_turn = np.ones_like(has)
    if turnover:
        ok_turn = np.isfinite(turn) & (turn >= TURNOVER_MIN)
    base = both & consistent & ~over & mem & ok_turn
    with np.errstate(invalid="ignore", divide="ignore"):
        q_open_eq = both & (np.abs(O / Cp - 1) < 1e-9)
        q_flat = both & (np.abs(H - L) <= 1e-12 * np.fmax(1.0, H))
    nb = int(both.sum())
    stats = {"tickers": int(len(names)), "days_in_window": int(inwin.sum()), "ticker_days": nb,
             "eligible": int(base.sum()),
             "excl_inconsistent": int((both & ~consistent).sum()), "excl_over_limit": int((both & consistent & over).sum()),
             "excl_member": int((both & ~mem).sum()), "excl_turnover": int((both & mem & ~ok_turn).sum()) if turnover else 0,
             "no_raw_share": _r(float((both & ~np.isfinite(F)).sum()) / nb, 4) if nb else None,
             "open_eq_prev_share": _r(q_open_eq.sum() / nb, 4) if nb else None,
             "flat_share": _r(q_flat.sum() / nb, 4) if nb else None,
             "ex_days": int((ex & both).sum())}
    stats["bad_data"] = bool(nb and max(stats["open_eq_prev_share"] or 0, stats["flat_share"] or 0) > BAD_DATA_SHARE)
    return {"name": name, "days": days, "names": list(names), "O": O, "H": H, "L": L, "C": C, "V": V, "F": F, "S": S, "Dv": Dv,
            "ex": ex, "base": base, "has": has, "turn20": turn, "stats": stats}


def _sub(P: dict, cols: list[int]) -> dict:
    return {k: np.asarray(v)[:, cols] for k, v in P.items()}


def daily_panels(W: dict, smoke_names: set | None = None) -> dict[str, dict]:
    """{样本: 宽表}：Z / E（Yahoo 27 年）、W（Yahoo 21 年扩大池）、J（J-Quants 今天的日経225）、Jx（时点 TOPIX 1000 − 今天的日経225）。"""
    from qbreak.config import universe
    n225 = set(universe("JP", "broad"))
    out = {}
    for e, years in (("Z", 27), ("E", 27)):
        ctx = W["ctx"][e]
        names = [ctx["names"][j] for j in ctx["cols"]]
        days = pd.DatetimeIndex(ctx["days"])
        S = np.ones((len(days), len(names)))
        Dv, ex = np.ones_like(S), np.zeros(S.shape, bool)
        for j, t in enumerate(names):
            S[:, j], Dv[:, j], ex[:, j] = yahoo_factors(_meta_actions(t, years), days)
        out[e] = build_panel(e, _sub(ctx["P"], list(ctx["cols"])), days, names, S, Dv, ex)
    ctxw = W["SM"]["W"]["ctx"]
    names = [ctxw["names"][j] for j in ctxw["cols"]]
    days = pd.DatetimeIndex(ctxw["days"])
    S = np.ones((len(days), len(names)))
    Dv, ex = np.ones_like(S), np.zeros(S.shape, bool)
    for j, t in enumerate(names):
        S[:, j], Dv[:, j], ex[:, j] = yahoo_factors(_meta_actions(t, 21), days)
    out["W"] = build_panel("W", _sub(ctxw["P"], list(ctxw["cols"])), days, names, S, Dv, ex, turnover=True)
    c2 = W["SM"]["J2"]["ctx"]
    D = c2["D"]
    days = pd.DatetimeIndex(c2["days"])
    allnames = list(c2["names"])
    ratio = np.asarray(D["ratio"], float)
    j_cols = [j for j in W["ctx"]["J"]["cols"]]
    jx_cols = [j for j in c2["cols"] if allnames[j] not in n225]
    if smoke_names is not None:
        jx_cols = [j for j in jx_cols if allnames[j] in smoke_names] or jx_cols[:8]
    need = sorted(set(j_cols) | set(jx_cols))
    S = np.ones((len(days), len(allnames)))
    Dv, ex = np.full(S.shape, np.nan), np.zeros(S.shape, bool)
    for j in need:
        S[:, j], Dv[:, j], ex[:, j] = jq_factors(np.asarray(c2["P"]["C"], float)[:, j], ratio[:, j], _act_cache(allnames[j]), days)
    pick = lambda cols, X: X[:, cols]                                     # noqa: E731
    out["J"] = build_panel("J", _sub(c2["P"], j_cols), days, [allnames[j] for j in j_cols], pick(j_cols, S), pick(j_cols, Dv),
                           pick(j_cols, ex))
    mem = np.asarray(D["mem"]["U2"], bool)[:, jx_cols]
    out["Jx"] = build_panel("Jx", _sub(c2["P"], jx_cols), days, [allnames[j] for j in jx_cols], pick(jx_cols, S),
                            pick(jx_cols, Dv), pick(jx_cols, ex), member=mem, turnover=True)
    out["Jx"]["pit"] = pit_check(c2, jx_cols, mem, days)
    return out


def pit_check(c2: dict, jx_cols: list[int], mem: np.ndarray, days: pd.DatetimeIndex) -> dict:
    """Jx 窗口内退市（最后一根 K 线早于窗口终点 − 10 天）/ 被剔除出 TOPIX 1000（成员 True → False）的票数。为 0 → 照实写「Jx 也不是真正的时点池」。"""
    a, b = WIN["Jx"]
    w = np.asarray((days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b)))
    names = [c2["names"][j] for j in jx_cols]
    delist = set(c2.get("delist") or {})
    n_del = sum(1 for t in names if t in delist)
    m = mem[w]
    dropped = int(((m[:-1] & ~m[1:]).any(axis=0)).sum()) if len(m) > 1 else 0
    return {"names": len(names), "delisted_in_window": int(n_del), "dropped_from_topix1000": dropped,
            "true_pit": bool(n_del or dropped)}


def jx_names(W: dict) -> list[str]:
    """J2 的时点 TOPIX 1000（有 mem 的票）去掉今天的日経225。"""
    from qbreak.config import universe
    n225 = set(universe("JP", "broad"))
    return [t for t in W["SM"]["J2"]["fa"] if t not in n225]


def panel_fingerprint(panels: dict) -> dict:
    """日线宽表的指纹（只记录、不拒绝运行）：票数、日数、有值格数、合格数，加上复权对数收益的两个合计（对新除息的整体缩放不变）。
    两个合计只进哈希、不写出来（--check 不写任何收益，哪怕是整个面板的合计）；哈希的算法不变。"""
    out = {}
    for k, P in panels.items():
        C, O = P["C"], P["O"]
        with np.errstate(invalid="ignore", divide="ignore"):
            lr = np.log(C / _prev_row(C))
            lo = np.log(C / O)
        out[k] = {"tickers": len(P["names"]), "days": len(P["days"]), "cells": int(np.isfinite(C).sum()),
                  "sum_logret": round(float(np.nansum(lr)), 3), "sum_log_oc": round(float(np.nansum(lo)), 3),
                  "eligible": int(P["base"].sum())}
    h = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()[:16]
    shown = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("sum_")} for k, v in out.items()}
    return {"sha": h, "samples": shown}



# ───────────────────────── 家族 A：券商侧逆指値（逐信号 + 账户） ─────────────────────────
A_MODES = ("A0", "A1", "A2", "A3")


def exit_params(p) -> dict:
    """B0 的离场参数（X6 版）。逐信号模拟只镜像现行用到的分支；用到别的（死叉 / SAR / 时间止损 / ATR 止损 / 跟踪启动）→ 报错（规则变了要先改模拟）。"""
    bad = [k for k in ("exit_on_macd_dead_cross", "exit_sar_flip") if getattr(p, k, False)]
    bad += [k for k in ("time_stop_days", "atr_stop_mult", "trailing_arm_pct") if float(getattr(p, k, 0) or 0) != 0]
    if bad:
        raise ValueError(f"逐信号模拟没有镜像这些离场分支：{bad}")
    return {"stop": p.stop_loss_pct / 100, "trail": p.trailing_stop_pct / 100, "tp": (p.take_profit_pct / 100) if p.take_profit_pct else None,
            "chand": float(p.exit_chandelier_k or 0), "climax": bool(p.exit_on_climax), "climax_gain": float(p.climax_min_gain_pct),
            "max_hold": int(p.max_hold_days or 0)}


def ticker_arrays(df: pd.DataFrame, F: np.ndarray | None = None) -> dict:
    """指标表 → 逐信号模拟要的数组（复权价；F = 不复权系数，锁死判定用）。"""
    n = len(df)
    return {"days": pd.DatetimeIndex(df.index), "O": df["Open"].to_numpy(float), "H": df["High"].to_numpy(float),
            "L": df["Low"].to_numpy(float), "C": df["Close"].to_numpy(float), "atr": df["atr"].to_numpy(float),
            "climax": df["climax"].fillna(False).to_numpy(bool) if "climax" in df.columns else np.zeros(n, bool),
            "F": np.ones(n) * np.nan if F is None else np.asarray(F, float)}


def simulate_exits(a: dict, i_sig: int, xp: dict, mode: str, gap_pct: float = 3.0, slip: float = SLIP, raw_lock: bool = True,
                   outage: np.ndarray | None = None) -> dict:
    """一个信号（信号日第 i_sig 行）按 E0 入场、按 mode 离场。逐行镜像 qbreak.unified.UnifiedEngine 的 open_phase / _check_exits：
      A0 = 现行（next_open：收盘判定 → 次日寄付卖）；INTRA = 引擎的 intraday 模式（入场当天也查盘中，只用于接线核对）；
      A1 = INTRA 但入场当天只按收盘判定（MinuteStopEngine 同一套）；A3 = 只有固定止损是常挂逆指値（第二天起）；
      A2 = A0 + 第二天起的灾难逆指値 max(入场 × 0.88, 峰值 × 0.83)（当天已排寄付卖单 → 不挂）。
    raw_lock：锁死按还原后的不复权价（研究口径）；False = 按复权价（与引擎逐笔核对的口径）。
    outage：每天执行器有没有跑（True = 没跑：寄付单不下、逆指値的触发价不更新；描述项 6 用）。只返回价格，不算收益。"""
    O, H, L, C, atr, clx, F = a["O"], a["H"], a["L"], a["C"], a["atr"], a["climax"], a["F"]
    n = len(O)
    i = i_sig + 1
    out = {"entered": False, "skip": None}
    if i >= n:
        out["skip"] = "no_bar"
        return out

    def lk(k: int) -> str | None:
        if k <= 0:
            return None
        if raw_lock:
            return lock(C[k - 1], H[k], L[k], C[k], F[k - 1], F[k])
        return limit_lock(C[k - 1], H[k], L[k], C[k], "JP")

    if outage is not None and outage[i]:
        out["skip"] = "outage"
        return out
    if gap_pct and O[i] > C[i_sig] * (1 + gap_pct / 100):
        out["skip"] = "gap"
        return out
    if lk(i) == "up":
        out["skip"] = "limit_up"
        return out
    entry = O[i] * (1 + slip)
    stop_px = entry * (1 - xp["stop"])
    tp_px = entry * (1 + xp["tp"]) if xp["tp"] else np.inf
    peak, hold, pending = entry, 0, None
    cat_trig = None
    out.update({"entered": True, "i_entry": i, "entry_px": entry, "entry_touch": False, "gap_through": False, "cat_hit": False})
    if mode in ("A1", "INTRA"):
        out["entry_touch"] = bool(L[i] <= max(stop_px, peak * (1 - xp["trail"])) or H[i] >= tp_px)
    elif mode == "A3":
        out["entry_touch"] = bool(L[i] <= stop_px)
    elif mode == "A2" and A_STOP["A2"]:
        out["entry_touch"] = bool(L[i] <= max(entry * A_STOP["A2"][0], peak * A_STOP["A2"][1]))

    def done(k: int, px: float, why: str, gap: bool = False) -> dict:
        out.update({"i_exit": k, "exit_px": px, "reason": why, "gap_through": bool(gap), "hold": hold})
        return out

    for k in range(i, n):
        if k > i and pending is not None:                                    # open_phase：昨天收盘排的寄付卖单
            if outage is not None and outage[k]:
                pass                                                         # 执行器没跑 → 寄付单没下，顺延
            elif lk(k) == "down":
                pass                                                         # 跌停锁死 → 卖不出，顺延（引擎同样还会跑当天的离场判断）
            else:
                return done(k, O[k] * (1 - slip), pending)
        hold += 1
        o, h, l, c = O[k], H[k], L[k], C[k]
        queued = None
        first = k == i
        intra = (mode == "INTRA") or (mode == "A1" and not first)
        if intra:
            trail_px = peak * (1 - xp["trail"])
            hard = max(stop_px, trail_px)
            px = why = None
            if o <= hard:
                px, why = o, "gap_stop"
            elif l <= hard:
                px, why = hard, ("trail" if trail_px > stop_px else "stop")
            elif h >= tp_px:
                px, why = max(tp_px, o), "take_profit"
            if px is not None:
                if lk(k) == "down":
                    pending = why
                    continue
                return done(k, px * (1 - slip), why, gap=(why == "gap_stop"))
            peak = max(peak, h)
        elif mode == "A3" and not first:
            px = stop_sell_fill(stop_px, o, l)
            if px is not None:
                if lk(k) == "down":
                    pending = "stop"
                    continue
                return done(k, px * (1 - slip), "stop", gap=(o <= stop_px))
            peak = max(peak, h)
            trail_px = peak * (1 - xp["trail"])
            hard = max(stop_px, trail_px)
            if c <= hard:
                queued = "trail" if trail_px > stop_px else "stop"
            elif c >= tp_px:
                queued = "take_profit"
        else:
            if mode == "A2" and not first and pending is None:
                if outage is None or not outage[k]:                          # 07:40 改一次触发价（峰值 = 到昨天为止）
                    cat_trig = max(entry * A_STOP["A2"][0], peak * A_STOP["A2"][1])
                if cat_trig is not None:
                    px = stop_sell_fill(cat_trig, o, l)
                    if px is not None:
                        out["cat_hit"] = True
                        if lk(k) == "down":
                            pending = "cat_stop"
                            continue
                        return done(k, px * (1 - slip), "cat_stop", gap=(o <= cat_trig))
            peak = max(peak, h)
            trail_px = peak * (1 - xp["trail"])
            hard = max(stop_px, trail_px)
            if c <= hard:
                queued = "trail" if trail_px > stop_px else "stop"
            elif c >= tp_px:
                queued = "take_profit"
        if queued is None:
            chand = xp["chand"] > 0 and np.isfinite(atr[k]) and c < peak - xp["chand"] * atr[k]
            if xp["climax"] and clx[k] and (c / entry - 1) * 100 >= xp["climax_gain"]:
                queued = "climax"
            elif chand:
                queued = "chandelier"
            elif xp["max_hold"] and hold >= xp["max_hold"]:
                queued = "max_hold"
        if queued:
            pending = queued
    out.update({"reason": "end", "hold": hold})
    return out


def a_frames(W: dict) -> dict[str, dict[str, pd.DataFrame]]:
    """各样本的 B0 买点：Z / E / J = LC.load 的 fr（W2 + C 留一年代）；W = W2；Jx = J2 的 W2 ∧ 时点成员，去掉今天的日経225。"""
    import leap_confirm as LF
    out = {e: W["fr"][e] for e in ("Z", "E", "J")}
    sw = W["SM"]["W"]
    out["W"] = LF.with_mask(sw["fa"], sw["keep"])
    s2 = W["SM"]["J2"]
    keep = {t: np.asarray(s2["keep"][t], bool) & np.asarray(s2["mem"].get(t, np.ones(len(df), bool)), bool) for t, df in s2["fa"].items()}
    jx = set(jx_names(W))
    out["Jx"] = {t: df for t, df in LF.with_mask(s2["fa"], keep).items() if t in jx}
    return out


def a_signal_list(frames: dict[str, pd.DataFrame], sample: str) -> list[tuple[str, int, pd.Timestamp]]:
    a, b = WIN[sample]
    lo, hi = pd.Timestamp(a), pd.Timestamp(b)
    out = []
    for t in sorted(frames):
        df = frames[t]
        e = df["entry"].to_numpy(bool)
        for k in np.flatnonzero(e):
            d = df.index[k]
            if lo <= d <= hi:
                out.append((t, int(k), d))
    return out


def panel_F(panel: dict, t: str, idx: pd.DatetimeIndex) -> np.ndarray:
    try:
        j = panel["names"].index(t)
    except ValueError:
        return np.full(len(idx), np.nan)
    return pd.Series(panel["F"][:, j], index=panel["days"]).reindex(idx).to_numpy(float)


def fam_A_signal(W: dict, panels: dict, xp: dict, gap_pct: float, outage_seed: int | None = None) -> dict[str, pd.DataFrame]:
    """逐信号：每个样本每个信号，A0 / A1 / A2 / A3 各自的入场 / 离场价格与原因（研究口径：锁死按不复权价）。只有价格，不算收益。"""
    fr = a_frames(W)
    out = {}
    for smp in SAMPLES:
        rows = []
        for t, k, d in a_signal_list(fr[smp], smp):
            df = fr[smp][t]
            arr = ticker_arrays(df, panel_F(panels[smp], t, df.index))
            rows.append({"sample": smp, "ticker": t, "date": d, **a_signal_row(arr, k, xp, gap_pct)})
        out[smp] = pd.DataFrame(rows)
    return out


def a_signal_row(arr: dict, k: int, xp: dict, gap_pct: float) -> dict:
    """一个信号在 A0 / A1 / A2 / A3 下的入场 / 离场价格、原因、出场日与标记（只有价格）。"""
    row = {}
    for m in A_MODES:
        r = simulate_exits(arr, k, xp, m, gap_pct)
        row[f"{m}_in"] = r["entered"]
        row[f"{m}_skip"] = r.get("skip")
        if r["entered"]:
            row[f"{m}_entry"] = r["entry_px"]
            row[f"{m}_exit"] = r.get("exit_px", np.nan)
            row[f"{m}_why"] = r.get("reason")
            row[f"{m}_xd"] = arr["days"][r["i_exit"]] if "i_exit" in r else pd.NaT
            row[f"{m}_gap"] = r.get("gap_through", False)
            row[f"{m}_touch"] = r.get("entry_touch", False)
            row[f"{m}_cat"] = r.get("cat_hit", False)
    return row


ENGINE_ROWS = 100                                                         # 单信号回测的窗口：信号前 1 行 → 信号后 100 行（≥ 最长持有 60 + 锁死顺延）


def check_vs_engine(W: dict, xp_params, gap_pct: float, samples=SAMPLES, max_signals: int | None = None) -> dict:
    """接线核对 3：每个信号单独跑一次 UnifiedEngine（只这一只、只这一个买点、截取信号前 1 行到后 ENGINE_ROWS 行、名额 1、本金极大（新仓 = 一半，现金不卡）、
    没有核心 ETF、新仓倍数 1）：① next_open（现行）的逐笔 = simulate_exits(A0, 锁死按复权价)；② intraday 模式的逐笔 =
    simulate_exits(INTRA)；③ A1 与 intraday 的差只来自入场当天（入场当天没碰到的信号逐笔相同）。比较入场价、出场日与出场价（4 位小数），
    不算收益。引擎没成交（跳空 / 涨停）的信号模拟也必须没成交；窗口内没平仓（「end」）的不比较、另计。"""
    from dataclasses import replace

    from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs
    xp = exit_params(xp_params)
    fr = a_frames(W)
    ex0 = exec_configs(("JP",), {"broker": "tachibana"})
    exi = {m: replace(c, stop_fill_mode="intraday") for m, c in ex0.items()}
    cfg = UnifiedConfig(capital_jpy=1e12, position_pct=0.5, max_positions=1, max_position_pct=1.0, cash_buffer_pct=0.0,
                        stock_markets=("JP",), core={}, core_index={})
    pp = {"JP": xp_params, "US": xp_params}
    res = {}
    for smp in samples:
        sig = a_signal_list(fr[smp], smp)
        if max_signals:
            sig = sig[:: max(1, len(sig) // max_signals)][:max_signals]
        c = {"signals": len(sig), "A0_trades": 0, "A0_match": 0, "INTRA_trades": 0, "INTRA_match": 0, "A1_same_as_intra": 0,
             "A1_comparable": 0, "A1_entry_touch": 0, "A0_no_entry": 0, "INTRA_no_entry": 0, "A0_unclosed": 0, "INTRA_unclosed": 0,
             "mismatch_examples": []}
        for t, k, d in sig:
            df = fr[smp][t]
            lo, hi = max(0, k - 1), min(len(df), k + 1 + ENGINE_ROWS)
            sub = df.iloc[lo:hi].copy()
            ent = np.zeros(len(sub), bool)
            ent[k - lo] = True
            sub["entry"] = ent
            arr = ticker_arrays(sub)
            ks = k - lo
            for key, exm, mode in (("A0", ex0, "A0"), ("INTRA", exi, "INTRA")):
                tr = UnifiedEngine({t: sub}, cfg, pp, exm, {}).run().trades
                sim = simulate_exits(arr, ks, xp, mode, gap_pct, raw_lock=False)
                if not len(tr):
                    ok = not sim.get("entered")
                    c[f"{key}_no_entry"] += int(ok)
                    if not ok and len(c["mismatch_examples"]) < 5:
                        c["mismatch_examples"].append(f"{smp} {lab(t)} {d.date()} {key}：引擎没成交、模拟成交")
                    c[f"{key}_trades"] += int(not ok)
                    continue
                row = tr.iloc[0]
                if row["reason"] == "end":
                    c[f"{key}_unclosed"] += 1
                    continue
                c[f"{key}_trades"] += 1
                ok = bool(sim.get("entered") and "i_exit" in sim and str(arr["days"][sim["i_exit"]].date()) == str(row["exit_date"])
                          and abs(round(sim["exit_px"], 4) - float(row["exit_px"])) <= 1.01e-4
                          and abs(round(sim["entry_px"], 4) - float(row["entry_px"])) <= 1.01e-4)
                c[f"{key}_match"] += int(ok)
                if not ok and len(c["mismatch_examples"]) < 5:
                    sx = arr["days"][sim["i_exit"]].date() if "i_exit" in sim else "—"
                    c["mismatch_examples"].append(f"{smp} {lab(t)} {d.date()} {key}：引擎 {row['exit_date']} {row['reason']}"
                                                  f" / 模拟 {sx} {sim.get('reason') or sim.get('skip')}")
                if key == "INTRA":
                    if sim.get("entry_touch"):
                        c["A1_entry_touch"] += 1
                        continue
                    s1 = simulate_exits(arr, ks, xp, "A1", gap_pct, raw_lock=False)
                    c["A1_comparable"] += 1
                    c["A1_same_as_intra"] += int(s1.get("i_exit") == sim.get("i_exit")
                                                 and abs(s1.get("exit_px", np.nan) - sim.get("exit_px", np.nan)) <= 1e-9)
        c["ok"] = bool(c["A0_trades"] == c["A0_match"] and c["INTRA_trades"] == c["INTRA_match"]
                       and c["A1_comparable"] == c["A1_same_as_intra"])
        res[smp] = c
    res["ok"] = all(v["ok"] for k, v in res.items() if isinstance(v, dict))
    return res


def minute_engine_class():
    """MinuteStopEngine：candle_portfolio.MixEngine 的子类，覆盖 _check_exits（MODE = A1 / A2 / A3；None = 父类原样）。
    逐行照抄 qbreak.unified.UnifiedEngine._check_exits；入场当天（hold 加 1 之后 = 1）一律按收盘判定。
    用法同 bsh_common.run_variant：临时换掉 CP.MixEngine，跑完换回；模拟盘 / 执行器的代码不动。"""
    import candle_portfolio as CP

    class MinuteStopEngine(CP.MixEngine):
        MODE: str | None = None
        HITS: dict = {}

        def _check_exits(self, m: str, i: int) -> None:
            mode = type(self).MODE
            if not mode or m != "JP":
                return super()._check_exits(m, i)
            cls = type(self)
            if cls.PB or cls.CHAND_K_DAY is not None or cls.OPP_EXIT or cls.EXIT_TICK:
                raise RuntimeError("MinuteStopEngine 不支持 PB / CHAND_K_DAY / OPP_EXIT / EXIT_TICK（B0 不用）")
            st, A = self.st, self.A
            for t in list(st.pos):
                ps = st.pos[t]
                if ps.market != m:
                    continue
                j = self.col[t]
                if not A.has[i, j]:
                    continue
                p = self._p(t)
                ps.hold += 1
                o, h, l, c = A.open[i, j], A.high[i, j], A.low[i, j], A.close[i, j]
                if p.trailing_arm_pct and not ps.armed and h >= ps.entry_px * (1 + p.trailing_arm_pct / 100):
                    ps.armed = True
                trail_on = p.trailing_stop_pct > 0 and (ps.armed or not p.trailing_arm_pct)
                tp_px = ps.entry_px * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
                queued = None
                first = ps.hold == 1
                if mode == "A1" and not first:                              # 引擎 intraday 分支（入场第二天起）
                    trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                    hard = max(ps.stop_px, trail_px)
                    exit_px = reason = None
                    if o <= hard:
                        exit_px, reason = o, "gap_stop"
                    elif l <= hard:
                        exit_px, reason = hard, ("trail" if trail_px > ps.stop_px else "stop")
                    elif h >= tp_px:
                        exit_px, reason = max(tp_px, o), "take_profit"
                    if exit_px is not None:
                        cls.HITS[reason] = cls.HITS.get(reason, 0) + 1
                        if self._locked(i, j) == "down":
                            self.skipped["limit_down_hold"] += 1
                            st.pending_exit[t] = reason
                            ps.last_close = c
                            continue
                        self._close(t, exit_px * (1 - self.slip[m]), i, reason)
                        continue
                    ps.peak = max(ps.peak, h)
                elif mode == "A3" and not first:                            # 只有固定止损常挂
                    px = stop_sell_fill(ps.stop_px, o, l)
                    if px is not None:
                        cls.HITS["stop"] = cls.HITS.get("stop", 0) + 1
                        if self._locked(i, j) == "down":
                            self.skipped["limit_down_hold"] += 1
                            st.pending_exit[t] = "stop"
                            ps.last_close = c
                            continue
                        self._close(t, px * (1 - self.slip[m]), i, "stop")
                        continue
                    ps.peak = max(ps.peak, h)
                    trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                    hard = max(ps.stop_px, trail_px)
                    if c <= hard:
                        queued = "trail" if trail_px > ps.stop_px else "stop"
                    elif c >= tp_px:
                        queued = "take_profit"
                else:
                    if mode == "A2" and not first and t not in st.pending_exit:    # 已排寄付卖单（跌停锁死没卖掉）→ 逆指値撤掉
                        trig = max(ps.entry_px * A_STOP["A2"][0], ps.peak * A_STOP["A2"][1])
                        px = stop_sell_fill(trig, o, l)
                        if px is not None:
                            cls.HITS["cat_stop"] = cls.HITS.get("cat_stop", 0) + 1
                            if self._locked(i, j) == "down":
                                self.skipped["limit_down_hold"] += 1
                                st.pending_exit[t] = "cat_stop"
                                ps.last_close = c
                                continue
                            self._close(t, px * (1 - self.slip[m]), i, "cat_stop")
                            continue
                    ps.peak = max(ps.peak, h)
                    trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                    hard = max(ps.stop_px, trail_px)
                    if c <= hard:
                        queued = "trail" if trail_px > ps.stop_px else "stop"
                    elif c >= tp_px:
                        queued = "take_profit"
                ps.last_close = c
                if queued is None:
                    chand = (p.exit_chandelier_k > 0 and np.isfinite(A.atr[i, j]) and c < ps.peak - p.exit_chandelier_k * A.atr[i, j])
                    if p.exit_on_climax and A.climax[i, j] and (c / ps.entry_px - 1) * 100 >= p.climax_min_gain_pct:
                        queued = "climax"
                    elif p.exit_on_macd_dead_cross and A.dead[i, j]:
                        queued = "dead_cross"
                    elif chand:
                        queued = "chandelier"
                    elif p.exit_sar_flip and A.sarflip[i, j]:
                        queued = "sar_flip"
                    elif p.max_hold_days and ps.hold >= p.max_hold_days:
                        queued = "max_hold"
                    elif (p.time_stop_days and ps.hold >= p.time_stop_days
                          and (c / ps.entry_px - 1) * 100 < p.time_stop_min_ret_pct):
                        queued = "time_stop"
                if queued:
                    st.pending_exit[t] = queued

    return MinuteStopEngine


def run_A_account(W: dict, era: str, mode: str | None, E=None) -> dict:
    """账户级：B0 的账户（LC.run）把离场换成 mode（None = A0 本身）。返回 LC.run 的 {cagr, dd, calmar, n, mean, win, h1, h2, years}。"""
    guard_returns(f"账户 {mode or 'A0'} {era}")
    import candle_portfolio as CP
    import loop_common as LC
    E = E or minute_engine_class()
    old = CP.MixEngine
    E.MODE, E.HITS = mode, {}
    CP.MixEngine = E
    try:
        r = LC.run(W, era)
    finally:
        CP.MixEngine = old
        hits = dict(E.HITS)
        E.MODE, E.HITS = None, {}
    r["hits"] = hits
    return r


# ───────────────────────── 宽表上的 tick / 制限値幅 / 锁死（向量化） ─────────────────────────
from qbreak.tick import _JP_LIMITS, TICK_OTHERS                               # noqa: E402

_TCAP = np.array([c for c, _ in TICK_OTHERS], float)
_TUNIT = np.array([u for _, u in TICK_OTHERS], float)
_LUP = np.array([u for u, _ in _JP_LIMITS], float)
_LWID = np.array([w for _, w in _JP_LIMITS] + [10_000_000.0], float)
MAX_SKIP = 5                                                              # 没数据的行最多跳过 5 行；锁死顺延最多 5 次


def tick_vec(raw) -> np.ndarray:
    """不复权价 → 1 tick（现行粗档；= qbreak.tick.tick_size(价格, on=TICK_ON) 的向量版）。"""
    raw = np.asarray(raw, float)
    ok = np.isfinite(raw) & (raw > 0)
    k = np.clip(np.searchsorted(_TCAP, np.where(ok, raw, 1.0), side="left"), 0, len(_TUNIT) - 1)
    return np.where(ok, _TUNIT[k], np.nan)


def limit_width_vec(base) -> np.ndarray:
    """前日收盘（不复权）→ 制限値幅（円；= price_limit_jp 的向量版）。"""
    base = np.asarray(base, float)
    ok = np.isfinite(base) & (base > 0)
    k = np.searchsorted(_LUP, np.where(ok, base, 1.0), side="right")
    return np.where(ok, _LWID[np.clip(k, 0, len(_LWID) - 1)], np.nan)


def floor_tick_vec(raw, unit=None) -> np.ndarray:
    raw = np.asarray(raw, float)
    u = tick_vec(raw) if unit is None else unit
    return np.floor(raw / u + 1e-9) * u


def ceil_tick_vec(raw, unit=None) -> np.ndarray:
    raw = np.asarray(raw, float)
    u = tick_vec(raw) if unit is None else unit
    return np.ceil(raw / u - 1e-9) * u


def fee_pct_vec(notional) -> np.ndarray:
    x = np.asarray(notional, float)
    return np.array([fee_pct(v) if v == v and v > 0 else np.nan for v in x.ravel()], float).reshape(x.shape)


def next_rows(has: np.ndarray, max_skip: int = MAX_SKIP) -> np.ndarray:
    """nxt[i, j] = i 之后第一行有数据的行（最多跳过 max_skip 行），没有 → −1。"""
    n, m = has.shape
    nxt = np.full((n, m), -1, dtype=np.int64)
    last = np.full(m, -1, dtype=np.int64)
    for i in range(n - 1, -1, -1):
        nxt[i] = last
        last = np.where(has[i], i, last)
    rows = np.arange(n)[:, None]
    nxt[(nxt >= 0) & (nxt - rows > max_skip + 1)] = -1
    return nxt


def raw_scale(P: dict) -> tuple[np.ndarray, np.ndarray]:
    """(还原得了吗, 系数)：不复权 = 复权 × 系数；还原不了的「票·日」系数当 1（tick 用价格的 0.1%，制限値幅按复权价查表）。"""
    F = P["F"]
    ok = np.isfinite(F) & (F > 0)
    return ok, np.where(ok, F, 1.0)


def panel_tick(P: dict, px_adj: np.ndarray) -> np.ndarray:
    """复权价矩阵上的 1 tick（复权单位）。"""
    ok, Fu = raw_scale(P)
    return np.where(ok, tick_vec(px_adj * Fu) / Fu, px_adj * TICK_FALLBACK)


def panel_limits(P: dict) -> tuple[np.ndarray, np.ndarray]:
    """当天制限値幅的上下限（复权单位）：按前一行收盘的不复权价查表。"""
    ok, Fu = raw_scale(P)
    Cp = _prev_row(P["C"])
    okp = _prev_row(ok.astype(float)) == 1.0
    both = ok & okp
    base = np.where(both, Cp * Fu, Cp)                                      # 前日收盘换成当天的口径
    w = limit_width_vec(base)
    lo = np.where(both, (base - w) / Fu, Cp - w)
    hi = np.where(both, (base + w) / Fu, Cp + w)
    return lo, hi


def panel_locks(P: dict) -> tuple[np.ndarray, np.ndarray]:
    """(跌停锁死, 涨停锁死) 矩阵：qbreak.tick.limit_lock 的向量版（前一行收盘为基准；还原后的不复权价）。"""
    ok, Fu = raw_scale(P)
    okp = _prev_row(ok.astype(float)) == 1.0
    both = ok & okp
    pc = np.where(both, _prev_row(P["C"]) * Fu, _prev_row(P["C"]))             # 前日收盘换成当天的口径
    s = np.where(both, Fu, 1.0)
    h, l, c = P["H"] * s, P["L"] * s, P["C"] * s
    with np.errstate(invalid="ignore"):
        good = np.isfinite(pc) & (pc > 0) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & (h > 0) & (l > 0) & (c > 0)
        flat = good & ((h - l) <= pc * 0.005)
        w = limit_width_vec(pc)
        down = flat & (c <= pc - 0.8 * w)
        up = flat & (c >= pc + 0.8 * w)
    return down, up


def prep_panel(P: dict) -> dict:
    """B / C / D 共用的派生矩阵（只有价格与掩码）。"""
    if "_prep" in P:
        return P["_prep"]
    ok, Fu = raw_scale(P)
    dn, up = panel_locks(P)
    lo, hi = panel_limits(P)
    q = {"ok": ok, "Fu": Fu, "down": dn, "up": up, "lim_lo": lo, "lim_hi": hi, "nxt": next_rows(P["has"]),
         "cex": np.cumsum(P["ex"].astype(np.int64), axis=0)}
    P["_prep"] = q
    return q


def resolve_exit(P: dict, i: np.ndarray, j: np.ndarray, kind: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """持有到出场：kind = close0（当天收盘竞价）/ close1（下一个有数据的行的收盘竞价）/ open1（下一行寄付）。
    出场那天跌停锁死 → 顺延到下一行寄付（最多 5 次）。返回 (出场行, 出场价（复权、未扣滑点）, 有效)；跨除权 / 拆股 → 无效（剔除）。"""
    q = prep_panel(P)
    i = np.asarray(i, np.int64)
    j = np.asarray(j, np.int64)
    k = i.copy() if kind == "close0" else q["nxt"][i, j]
    valid = k >= 0
    use_open = np.full(len(i), kind == "open1")
    for _ in range(MAX_SKIP + 1):
        kk = np.where(valid, k, 0)
        lockd = valid & q["down"][kk, j]
        if not lockd.any():
            break
        k2 = q["nxt"][kk, j]
        k = np.where(lockd, k2, k)
        valid &= ~lockd | (k2 >= 0)
        use_open |= lockd
    kk = np.where(valid, k, 0)
    valid &= ~q["down"][kk, j]
    px = np.where(use_open, P["O"][kk, j], P["C"][kk, j])
    valid &= np.isfinite(px) & (px > 0)
    valid &= (q["cex"][kk, j] - q["cex"][i, j]) == 0
    return np.where(valid, k, -1), np.where(valid, px, np.nan), valid


def _rows(P: dict, sample: str, i, j, entry, exit_, xi, si: int, so: int, lot_px=None) -> pd.DataFrame:
    """逐笔（只有价格；不入库）。lot_yen = 100 股 × 不复权的入场价（Jx / J：J-Quants 还原；Z / E / W：Yahoo 还原，近似）。"""
    q = prep_panel(P)
    i, j = np.asarray(i, np.int64), np.asarray(j, np.int64)
    lp = np.asarray(entry if lot_px is None else lot_px, float)
    lot = np.where(q["ok"][i, j], LOT * lp * q["Fu"][i, j], np.nan)
    return pd.DataFrame({"sample": sample, "date": P["days"][i], "i": i, "j": j, "entry": np.asarray(entry, float),
                         "exit": np.asarray(exit_, float), "xi": np.asarray(xi, np.int64), "si": si, "so": so, "lot_yen": lot})


def _pool(P: dict, entry: np.ndarray, exit_: np.ndarray, valid: np.ndarray, si: int, so: int) -> dict:
    """随机对照的抽样池（同一天的合格票，同样的持有窗口；只有价格）。"""
    return {"entry": np.where(valid, entry, np.nan), "exit": np.where(valid, exit_, np.nan), "valid": valid, "si": si, "so": so}


def fam_B(P: dict, s: float, hold: str) -> dict:
    """B-sc / B-sn：09:05 限价买 L = 正式开盘 ×(1 − s) 向下取到 tick；最低 ≤ L − 1 tick 才成交（成交价 L、0 滑点）；
    hold = "c"：当天收盘竞价卖；"n"：下一行收盘竞价卖（跌停锁死顺延）。限价低于当天跌停价 → 下不了单。"""
    q = prep_panel(P)
    O, Lw = P["O"], P["L"]
    base = P["base"]
    Fu = q["Fu"]
    with np.errstate(invalid="ignore"):
        L_raw = np.where(q["ok"], floor_tick_vec(O * Fu * (1 - s)), np.nan)
        L_adj = np.where(q["ok"], L_raw / Fu, np.floor(O * (1 - s) / (O * TICK_FALLBACK) + 1e-9) * (O * TICK_FALLBACK))
        tk = panel_tick(P, L_adj)
        fill = base & np.isfinite(L_adj) & (Lw <= L_adj - tk + 1e-12 * np.fmax(1.0, L_adj)) & (L_adj >= q["lim_lo"] - 1e-9)
    kind = "close0" if hold == "c" else "close1"
    ii, jj = np.nonzero(fill)
    xi, xp, ok = resolve_exit(P, ii, jj, kind)
    rows = _rows(P, P["name"], ii[ok], jj[ok], L_adj[ii[ok], jj[ok]], xp[ok], xi[ok], si=0, so=1)
    bi, bj = np.nonzero(base)
    bxi, bxp, bok = resolve_exit(P, bi, bj, kind)
    E = np.full(O.shape, np.nan)
    X = np.full(O.shape, np.nan)
    E[bi[bok], bj[bok]] = O[bi[bok], bj[bok]]
    X[bi[bok], bj[bok]] = bxp[bok]
    return {"rows": rows, "pool": _pool(P, E, X, np.isfinite(E), si=1, so=1), "fills": int(fill.sum()),
            "dropped_ex_or_nodata": int((~ok).sum())}


def fam_C(P: dict, kind: str) -> dict:
    """C1：买入逆指値 触发 = 正式开盘 × 1.02；C2：触发 = 正式开盘 + 0.5 ×（前一天高 − 低）。触发价向上取到 tick（对自己不利），
    超出当天涨停价 → 不成交；最高 ≥ 触发 → 成交价 = max(触发, 开盘) ×(1 + 0.10%)；当天收盘竞价卖，不设盘中止损。"""
    q = prep_panel(P)
    O, H = P["O"], P["H"]
    Fu, ok = q["Fu"], q["ok"]
    with np.errstate(invalid="ignore"):
        if kind == "C1":
            t_raw = O * Fu * 1.02
        else:
            # 前一天的（高 − 低）换成当天的不复权口径（× 当天的系数，与开盘同一口径；拆股 / 除息日也对）；还原不了 → Fu = 1，全在复权口径
            rng_raw = (_prev_row(P["H"]) - _prev_row(P["L"])) * Fu
            t_raw = O * Fu + 0.5 * rng_raw
        trig = np.where(ok, ceil_tick_vec(t_raw) / Fu,
                        np.ceil(t_raw / (O * TICK_FALLBACK) - 1e-9) * (O * TICK_FALLBACK))
        fill = P["base"] & np.isfinite(trig) & (H >= trig) & (trig <= q["lim_hi"] + 1e-9)
    ii, jj = np.nonzero(fill)
    entry = np.maximum(trig[ii, jj], O[ii, jj])
    xi, xp, v = resolve_exit(P, ii, jj, "close0")
    rows = _rows(P, P["name"], ii[v], jj[v], entry[v], xp[v], xi[v], si=1, so=1)
    bi, bj = np.nonzero(P["base"])
    bxi, bxp, bok = resolve_exit(P, bi, bj, "close0")
    E = np.full(O.shape, np.nan)
    X = np.full(O.shape, np.nan)
    E[bi[bok], bj[bok]] = O[bi[bok], bj[bok]]
    X[bi[bok], bj[bok]] = bxp[bok]
    return {"rows": rows, "pool": _pool(P, E, X, np.isfinite(E), si=1, so=1), "fills": int(fill.sum()),
            "dropped_ex_or_nodata": int((~v).sum())}


def fam_D(P: dict, exit_kind: str, afford: bool = False, pick: int = 5) -> dict:
    """D1（exit_kind = open1：次日寄付卖）/ D2（close1：次日收盘竞价卖）：每行在合格票里按 正式收盘 ÷ 正式开盘 − 1 取最低的 pick 只，
    收盘竞价买（× (1 + 0.10%)）。持有跨除权 / 拆股、下一行没数据的票先剔除再排（跌停锁死顺延之后才跨的也剔除）。
    afford = True：只在「一手 ≤ ¥125,000」（100 股 × 不复权收盘）的票里重新排。"""
    q = prep_panel(P)
    O, C = P["O"], P["C"]
    k1 = q["nxt"]
    n, m = O.shape
    rows_i = np.arange(n)[:, None].repeat(m, 1)
    kk = np.where(k1 >= 0, k1, 0)
    valid = P["base"] & (k1 >= 0) & ((q["cex"][kk, np.arange(m)[None, :]] - q["cex"]) == 0)
    if afford:
        valid &= q["ok"] & (LOT * C * q["Fu"] <= AFFORD_CAP)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(valid, C / O - 1, np.inf)
    sel_i, sel_j = [], []
    for i in np.flatnonzero(valid.any(axis=1)):
        v = np.flatnonzero(valid[i])
        if len(v) > pick:
            v = v[np.argpartition(r[i, v], pick - 1)[:pick]]
        sel_i.extend([i] * len(v))
        sel_j.extend(v.tolist())
    sel_i, sel_j = np.asarray(sel_i, np.int64), np.asarray(sel_j, np.int64)
    xi, xp, ok = resolve_exit(P, sel_i, sel_j, exit_kind)
    rows = _rows(P, P["name"], sel_i[ok], sel_j[ok], C[sel_i[ok], sel_j[ok]], xp[ok], xi[ok], si=1, so=1)
    bi, bj = np.nonzero(valid)
    bxi, bxp, bok = resolve_exit(P, bi, bj, exit_kind)
    E = np.full(O.shape, np.nan)
    X = np.full(O.shape, np.nan)
    E[bi[bok], bj[bok]] = C[bi[bok], bj[bok]]
    X[bi[bok], bj[bok]] = bxp[bok]
    del rows_i
    return {"rows": rows, "pool": _pool(P, E, X, np.isfinite(E), si=1, so=1), "fills": int(len(sel_i)),
            "dropped_ex_or_nodata": int((~ok).sum())}


CELL_SPEC = {"B-2c": ("B", 0.02, "c"), "B-3c": ("B", 0.03, "c"), "B-2n": ("B", 0.02, "n"), "B-3n": ("B", 0.03, "n"),
             "C1": ("C", "C1", None), "C2": ("C", "C2", None), "D1": ("D", "open1", None), "D2": ("D", "close1", None)}


def cell_book(P: dict, cell: str, afford: bool = False) -> dict:
    fam, a, b = CELL_SPEC[cell]
    if fam == "B":
        return fam_B(P, a, b)
    if fam == "C":
        return fam_C(P, a)
    return fam_D(P, a, afford=afford)


def affordable(rows: pd.DataFrame, cap: float = AFFORD_CAP) -> pd.DataFrame:
    """「一手 ≤ ¥125,000」子集（还原不了不复权价的不算进子集）。"""
    return rows[np.isfinite(rows["lot_yen"]) & (rows["lot_yen"] <= cap)]


# ───────────────────────── 收益（只有 --run 能算） ─────────────────────────
def trade_returns(rows: pd.DataFrame, slip: float = SLIP, notional: float | None = NOTIONAL) -> np.ndarray:
    """逐笔净收益（小数）= 出场 ×(1 − 滑点 × so) ÷ 入场 ×(1 + 滑点 × si) − 1 − 两边手续费。
    notional = None → 按一手的实际金额收费（「一手 ≤ ¥125,000」子集）。"""
    guard_returns("逐笔净收益")
    if not len(rows):
        return np.array([], float)
    gross = (rows["exit"].to_numpy(float) * (1 - slip * rows["so"].to_numpy(float))
             / (rows["entry"].to_numpy(float) * (1 + slip * rows["si"].to_numpy(float))) - 1)
    fee = 2 * (fee_pct_vec(rows["lot_yen"].to_numpy(float)) if notional is None else fee_pct(notional))
    return gross - fee


def pool_returns(pool: dict, slip: float = SLIP, notional: float = NOTIONAL) -> np.ndarray:
    guard_returns("随机对照的抽样池")
    with np.errstate(invalid="ignore", divide="ignore"):
        return pool["exit"] * (1 - slip * pool["so"]) / (pool["entry"] * (1 + slip * pool["si"])) - 1 - 2 * fee_pct(notional)


def placebo(books: list[tuple[dict, pd.DataFrame]], n: int, seed: list[int], notional: float = NOTIONAL) -> np.ndarray:
    """随机对照：每个判定样本、每天抽和候选同样多的合格票（不放回），持有窗口相同；返回 n 次的合并净均值（%）。
    books = [(pool, 候选逐笔), ...]（pool["R"] 可以预先给好：每行一个 1 维数组 = 那天的抽样池）。"""
    guard_returns("随机对照")
    rng = np.random.default_rng(seed)
    tot = np.zeros(n)
    cnt = 0
    for pool, rows in books:
        if not len(rows):
            continue
        k_by = rows.groupby("i").size()
        R = pool.get("R")
        if R is None:
            R = pool_returns(pool, notional=notional)
        for i, k in k_by.items():
            v = R.get(int(i)) if isinstance(R, dict) else R[int(i)]
            if v is None:
                continue
            v = np.asarray(v, float)
            v = v[np.isfinite(v)]
            if not len(v):
                continue
            k = int(min(k, len(v)))
            if k == len(v):
                tot += v.sum()
            else:
                keys = rng.random((n, len(v)))
                idx = np.argpartition(keys, k - 1, axis=1)[:, :k]
                tot += v[idx].sum(axis=1)
            cnt += k
    return tot / cnt * 100 if cnt else np.full(n, np.nan)

# ───────────────────────── T2：C3 与 D-rt（60m + 不复权日线，日経225） ─────────────────────────
HOURS = (9, 10, 11, 12, 13, 14, 15)


def t2_table(h60: dict, d1: dict, acts: dict, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """每只票一张「日」表（索引 = 交易日）：正式 O / H / L / C / V（Yahoo 不复权，只按拆股调整）、sf（× sf = 当时的真实价，
    tick / 制限値幅 / 一手用）、合格、除权日、时段、60m 各钟点那根的 O / H / L / C（列名 o9 / h9 / l9 / c9 …）。"""
    out = {}
    for t in tickers:
        d = d1.get(t)
        if d is None or not len(d):
            continue
        _need_raw(d)
        d = d.sort_index()
        idx = pd.DatetimeIndex(d.index)
        x = pd.DataFrame({"O": d["Open"], "H": d["High"], "L": d["Low"], "C": d["Close"], "V": d["Volume"]}, index=idx).astype(float)
        x["sf"] = split_after(acts.get(t), idx)
        ex = np.zeros(len(idx), bool)
        a = acts.get(t)
        if a is not None and len(a):
            for dd in a.index:
                k = int(idx.searchsorted(pd.Timestamp(dd), side="left"))
                if 0 <= k < len(idx):
                    ex[k] = True
        x["ex"] = ex
        has = (np.isfinite(x[["O", "H", "L", "C"]]).all(axis=1) & (x["O"] > 0) & (x["V"] > 0)).to_numpy()
        hasp = np.r_[False, has[:-1]]
        tol = 1e-9 * x["H"].abs().clip(lower=1.0)
        cons = ((x["L"] <= x["O"] + tol) & (x["O"] <= x["H"] + tol) & (x["L"] <= x["C"] + tol) & (x["C"] <= x["H"] + tol)).to_numpy()
        pc = x["C"].shift(1).to_numpy(float)                                # Yahoo 价格已按到取数日为止的拆股调整：前后两天同一口径
        sfv = x["sf"].to_numpy(float)
        w = limit_width_vec(pc * sfv) / sfv                                 # 基准 = 前日收盘换成当天的真实口径
        with np.errstate(invalid="ignore", divide="ignore"):
            over = (np.abs(x["O"].to_numpy() - pc) > w + 1e-9) | (np.abs(x["C"].to_numpy() - x["O"].to_numpy()) > w + 1e-9)
        x["pc"] = pc
        x["lim_hi"] = pc + w
        x["elig"] = has & hasp & cons & ~over
        x["sess"] = [session(z) for z in idx]
        h = h60.get(t)
        if h is not None and len(h):
            _need_raw(h)
            hh = h[h.index.minute == 0]
            day = (hh.index.tz_localize(None) if hh.index.tz is not None else hh.index).normalize()
            hr = hh.index.hour
            for k in HOURS:
                m = hr == k
                if not m.any():
                    continue
                sub = hh[m]
                dk = day[m]
                for col, src in (("o", "Open"), ("h", "High"), ("l", "Low"), ("c", "Close"), ("v", "Volume")):
                    x[f"{col}{k}"] = pd.Series(sub[src].to_numpy(float), index=dk).groupby(level=0).last().reindex(idx).to_numpy(float)
        for k in HOURS:
            for col in "ohlcv":
                if f"{col}{k}" not in x.columns:
                    x[f"{col}{k}"] = np.nan
        x.attrs["basis"] = "raw"
        out[t] = x
    return out


def c3_path(x: pd.DataFrame, k: int, trig: float | None, lo: float, sess: str | None) -> tuple[float, float, int] | None:
    """C3 的一笔（只有价格）：trig = None → 随机对照（10:00 那根开盘买）。返回 (入场, 出场, 出场那根的钟点；16 = 正式收盘竞价) 或 None（没成交）。
    成交那根里也碰到止损 → 当作已经止损（不利的先发生）；之后各根：开盘 ≤ 止损 → 按开盘，最低 ≤ 止损 → 按止损；
    H1 的 15:00 那根（收盘竞价）不查；都没碰到 → 正式收盘竞价卖。"""
    r = x.iloc[k]
    fill_h, entry = None, None
    if trig is None:
        o = r["o10"]
        if not (o == o and o > 0):
            return None
        fill_h, entry = 10, float(o)
        if o <= lo:
            return entry, float(o), 10
        if r["l10"] <= lo:
            return entry, float(lo), 10
    else:
        for hh in (10, 11, 12, 13, 14):
            if not (r[f"h{hh}"] == r[f"h{hh}"]):
                continue
            px = stop_buy_fill(trig, r[f"o{hh}"], r[f"h{hh}"], cap=float(r["lim_hi"]))
            if px is None:
                continue
            fill_h, entry = hh, float(px)
            if r[f"l{hh}"] <= lo:
                return entry, float(lo), hh
            break
        if fill_h is None:
            return None
    last = 15 if sess != "H1" else 14
    for hh in range(fill_h + 1, last + 1):
        o, lw = r[f"o{hh}"], r[f"l{hh}"]
        if not (o == o):
            continue
        px = stop_sell_fill(lo, o, lw)
        if px is not None:
            return entry, float(px), hh
    return entry, float(r["C"]), 16


def fam_C3(tab: dict[str, pd.DataFrame], pick: int = 2) -> dict:
    """C3：开盘区间（正式开盘 + 09:00 那根）；r1 = 09:00 那根收盘 ÷ 开盘 − 1 > 0 的前 2 只；区间高点 + 1 tick 的买入逆指値
    （10:00〜14:00 那几根有效）；止损 = 区间低点；每笔 ¥125,000。只有价格。
    选票只用 10:00 时已知的东西（合格 + 09:00 那根）：不要求 10:00 那根存在（那是 10:00 之后的信息）；没数据的根在 c3_path 里跳过。
    随机对照的池 = 同一批票里 10:00 那根有开盘价的（要在那根开盘买）。"""
    cand, pool = [], {}
    for t, x in tab.items():
        ok = x["elig"].to_numpy(bool) & np.isfinite(x["o9"].to_numpy(float))
        ok &= np.isin(x["sess"].to_numpy(object), ["H1", "H2", "post"])
        for k in np.flatnonzero(ok):
            r = x.iloc[k]
            O = float(r["O"])
            hi, lo = max(O, float(r["h9"])), min(O, float(r["l9"]))
            r1 = float(r["c9"]) / O - 1
            d = x.index[k]
            plc = c3_path(x, k, None, lo, r["sess"])
            if plc is not None:
                pool.setdefault(d, []).append((plc[0], plc[1], float(r["sf"])))
            if r1 > 0:
                cand.append((d, t, k, r1, hi, lo, r["sess"]))
    cdf = pd.DataFrame(cand, columns=["date", "ticker", "k", "r1", "hi", "lo", "sess"])
    rows = []
    if len(cdf):
        top = cdf.sort_values(["date", "r1", "ticker"], ascending=[True, False, True]).groupby("date", sort=True).head(pick)
        for d, t, k, r1, hi, lo, sess in top.itertuples(index=False):
            x = tab[t]
            sf = float(x["sf"].iloc[k])
            trig = hi + tick_of(hi * sf) / sf
            got = c3_path(x, int(k), trig, lo, sess)
            if got is None:
                continue
            rows.append((d, t, sess, got[0], got[1], got[2], LOT * got[0] * sf))
    rows = pd.DataFrame(rows, columns=["date", "ticker", "sess", "entry", "exit", "exit_hour", "lot_yen"])
    days = sorted(set(pool) | set(rows["date"]))
    pos = {d: n for n, d in enumerate(days)}
    rows["i"] = rows["date"].map(pos).astype("int64") if len(rows) else pd.Series(dtype="int64")
    rows["sample"], rows["si"], rows["so"] = "C3", 1, 1
    by_day = {pos[d]: (np.array([a for a, _, _ in v]), np.array([b for _, b, _ in v])) for d, v in pool.items()}
    sess_of = {pos[d]: session(d) for d in pool}
    return {"rows": rows, "pool": {"by_day": by_day, "sess": sess_of, "si": 1, "so": 1}, "cand_days": int(cdf["date"].nunique()) if len(cdf) else 0}


def pool_by_day_returns(pool: dict, slip: float = SLIP, notional: float = C3_NOTIONAL, sess: tuple = ("H1", "H2")) -> dict:
    guard_returns("C3 随机对照的抽样池")
    out = {}
    for i, (e, x) in pool["by_day"].items():
        if pool["sess"].get(i) not in sess:
            continue
        out[i] = x * (1 - slip * pool["so"]) / (e * (1 + slip * pool["si"])) - 1 - 2 * fee_pct(notional)
    return out


def _next_exit_t2(x: pd.DataFrame, k: int, kind: str) -> tuple[int, float] | None:
    """D-rt 的出场：open1 = 下一行寄付；close1 = 下一行收盘竞价；跌停锁死 → 顺延到再下一行寄付（最多 5 次）。下一天是除权日 → None。"""
    n = len(x)
    j = k + 1
    if j >= n or bool(x["ex"].iloc[j]):
        return None
    use_open = kind == "open1"
    for _ in range(MAX_SKIP + 1):
        if j >= n:
            return None
        r = x.iloc[j]
        prev = x.iloc[j - 1]
        sf = float(r["sf"])
        lk = limit_lock(float(prev["C"]) * sf, float(r["H"]) * sf, float(r["L"]) * sf, float(r["C"]) * sf, "JP")
        if lk != "down":
            px = float(r["O"] if use_open else r["C"])
            return (j, px) if px == px and px > 0 else None
        use_open = True
        j += 1
        if j < n and bool(x["ex"].iloc[j]):
            return None
    return None


def fam_D_rt(tab: dict[str, pd.DataFrame], exit_kind: str, cut: int = 14, sessions=("H2",), pick: int = 5) -> dict:
    """D-rt：用 60m 第 cut 点那根的收盘（cut = 14 → 约 15:00 的价）代替正式收盘选最低的 5 只，成交价仍用正式收盘；
    同时在同一批合格票（当天有那一根、下一天有数据、不跨除权）里按正式收盘选一次（D 的对照）。只有价格。"""
    recs = []
    for t, x in tab.items():
        elig = x["elig"].to_numpy(bool) & np.isfinite(x[f"c{cut}"].to_numpy(float)) & np.isin(x["sess"].to_numpy(object), list(sessions))
        for k in np.flatnonzero(elig):
            ex_ = _next_exit_t2(x, int(k), exit_kind)
            if ex_ is None:
                continue
            r = x.iloc[k]
            O = float(r["O"])
            recs.append((x.index[k], t, float(r[f"c{cut}"]) / O - 1, float(r["C"]) / O - 1, float(r["C"]), ex_[1], r["sess"],
                         LOT * float(r["C"]) * float(r["sf"])))
    df = pd.DataFrame(recs, columns=["date", "ticker", "r_rt", "r_off", "entry", "exit", "sess", "lot_yen"])
    out = {}
    for key, col in (("rt", "r_rt"), ("off", "r_off")):
        if not len(df):
            out[key] = df.assign(si=1, so=1, sample="T2")
            continue
        sel = df.sort_values(["date", col, "ticker"]).groupby("date", sort=True).head(pick).copy()
        sel["si"], sel["so"], sel["sample"] = 1, 1, "T2"
        out[key] = sel.reset_index(drop=True)
    out["n_valid"] = int(len(df))
    return out

# ───────────────────────── MDE（同窗口「全部合格票等权」的收益，不是候选的收益；--check 也算） ─────────────────────────
WINDOW_OF = {"B-2c": "oc", "B-3c": "oc", "C1": "oc", "C2": "oc", "B-2n": "on", "B-3n": "on", "D1": "co", "D2": "cc"}
MDE_NET = {c: (A_RULES["diff_min"] if c in ("A1", "A3") else STAGE1["mean_min"]) for c in CELLS}   # MDE 与「净门槛」比


def market_days(P: dict, win: str) -> pd.DataFrame:
    """每天全部合格票的等权窗口收益（均值 m、横截面方差 v、票数 n）：oc 开 → 收；on 开 → 下一行收；co 收 → 下一行开；cc 收 → 下一行收。
    跨除权 / 下一行没数据的不算。只用于 MDE（事先估检验力），不是任何候选的收益。"""
    q = prep_panel(P)
    O, C = P["O"], P["C"]
    n, m = O.shape
    base = P["base"]
    if win == "oc":
        a, b, ok = O, C, base
    else:
        k = q["nxt"]
        kk = np.where(k >= 0, k, 0)
        cols = np.arange(m)[None, :]
        ok = base & (k >= 0) & ((q["cex"][kk, cols] - q["cex"]) == 0)
        a = O if win == "on" else C
        b = O[kk, cols] if win == "co" else C[kk, cols]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(ok, b / a - 1, np.nan)
    cnt = np.isfinite(r).sum(axis=1)
    keep = cnt >= 5
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                     # 票数 < 5 的天整行是 nan（下面丢掉）
        mu = np.nanmean(np.where(keep[:, None], r, np.nan), axis=1)
        va = np.nanvar(np.where(keep[:, None], r, np.nan), axis=1, ddof=1)
    return pd.DataFrame({"date": P["days"], "m": mu, "v": va, "n": cnt})[keep]


def mde_from(days: pd.DataFrame, n_trades: int, alpha: float = MDE_ALPHA, power: float = MDE_POWER) -> dict:
    """s_月² = s_共同² + σ_个别² ÷ 每月笔数；MDE = (t_isf(α, M − 1) + t_isf(1 − 检验力, M − 1)) × s_月 ÷ √M（%）。"""
    if days is None or not len(days) or not n_trades:
        return {"mde": None, "months": 0}
    mm = days.groupby(pd.to_datetime(days["date"]).dt.to_period("M"))["m"].mean()
    M = int(len(mm))
    if M < 3:
        return {"mde": None, "months": M}
    s_c = float(mm.std(ddof=1))
    s_i2 = float(np.nanmean(days["v"]))
    npm = n_trades / M
    s = math.sqrt(s_c ** 2 + s_i2 / npm)
    mde = (t_isf(alpha, M - 1) + t_isf(1 - power, M - 1)) * s / math.sqrt(M) * 100
    return {"mde": mde, "months": M, "per_month": npm, "s_common": s_c * 100, "s_idio": math.sqrt(s_i2) * 100}


def a_market_days(W: dict, panels: dict, sig: pd.DataFrame, smp: str) -> pd.DataFrame:
    """A 的 MDE 用：每个信号的 A0 持有窗口（入场日收盘 → 出场日收盘）上全部合格票的等权收益（偏保守的上界：配对差的方差更小）。"""
    P = panels[smp]
    days = P["days"]
    out = []
    for _, r in sig.iterrows():
        if not r.get("A0_in") or pd.isna(r.get("A0_xd")):
            continue
        a = int(days.searchsorted(pd.Timestamp(r["A0_xd"]) - pd.Timedelta(days=0), side="left"))
        e = int(days.searchsorted(pd.Timestamp(r["date"]), side="right"))
        if not (0 <= e < a < len(days)):
            continue
        ok = P["base"][e] & np.isfinite(P["C"][a])
        with np.errstate(invalid="ignore", divide="ignore"):
            rr = P["C"][a][ok] / P["C"][e][ok] - 1
        rr = rr[np.isfinite(rr)]
        if len(rr) >= 5:
            out.append((r["date"], float(rr.mean()), float(rr.var(ddof=1)), len(rr)))
    return pd.DataFrame(out, columns=["date", "m", "v", "n"])


# ───────────────────────── 判定（事先写定） ─────────────────────────
def stats_rows(parts: list[tuple[str, pd.DataFrame, np.ndarray]]) -> dict:
    """parts = [(样本, 逐笔, 净收益)]：合并的 {n, mean, median, win, months, t, p} + 合并的前半 / 后半均值（各样本自己的两半合在一起）。"""
    ds, vs, hs = [], [], []
    for smp, rows, r in parts:
        if not len(rows):
            continue
        ds.append(pd.to_datetime(rows["date"]).to_numpy())
        vs.append(np.asarray(r, float))
        hs.append(half_of(smp, rows["date"]) if smp in HALF_OF else np.where(np.isin(rows.get("sess", pd.Series(dtype=object)).to_numpy(object), ["H1"]), 1, 2))
    if not ds:
        return {"n": 0, "mean": None, "t": None, "p": None, "h1": None, "h2": None, "months": 0}
    d, v, h = np.concatenate(ds), np.concatenate(vs), np.concatenate(hs)
    out = month_t(d, v)
    for k in (1, 2):
        m = (h == k) & np.isfinite(v)
        out[f"h{k}"] = float(v[m].mean() * 100) if m.any() else None
        out[f"n_h{k}"] = int(m.sum())
    return out


def judge_family_samples(fam: str, panels: dict) -> tuple[list[str], list[str], bool]:
    """(进判定的样本, 数据不合格的样本, 整个家族不判定)：B / C / D 才看「数据不合格」；少了 ≥ 2 个判定样本 → 不判定。"""
    judge = list(JUDGE[fam])
    bad = [s for s in judge if fam in ("B", "C", "D") and (panels.get(s) or {}).get("stats", {}).get("bad_data")]
    return [s for s in judge if s not in bad], bad, len(bad) >= 2


def stage1_cell(cell: str, books: dict, panels: dict, aff_books: dict | None = None, drt: dict | None = None) -> dict:
    """B / C / D 一格的第一关（BH 另做）。books = {样本: fam_* 的结果}；aff_books = D 在「一手 ≤ ¥125,000」里重排的结果。"""
    guard_returns(f"第一关 {cell}")
    fam = CELL_SPEC[cell][0]
    act, bad, void = judge_family_samples(fam, panels)
    res = {"cell": cell, "judge": act, "bad_data": bad, "void": void, "per_sample": {}, "reference": {}}
    parts, stress, aff_parts, gross = [], [], [], []
    for smp in list(JUDGE[fam]) + list(REFERENCE.get(fam, ())):
        b = books.get(smp)
        if b is None:
            continue
        rows = b["rows"]
        r = trade_returns(rows)
        st = stats_rows([(smp, rows, r)])
        g = trade_returns(rows, slip=0.0) + 2 * fee_pct(NOTIONAL)                          # 毛收益（不扣滑点与手续费）
        st["gross"] = float(np.mean(g)) * 100 if len(rows) else None
        st["per_year"] = len(rows) / max(1e-9, (pd.Timestamp(WIN[smp][1]) - pd.Timestamp(WIN[smp][0])).days / 365.25)
        (res["per_sample"] if smp in JUDGE[fam] else res["reference"])[smp] = {k: _r(v, 4) for k, v in st.items()}
        if smp in act:
            parts.append((smp, rows, r))
            gross.append(g)
            stress.append(trade_returns(rows, slip=SLIP_STRESS))
            ar = (aff_books or {}).get(smp, {}).get("rows") if aff_books else affordable(rows)
            if ar is not None and len(ar):
                aff_parts.append((smp, ar, trade_returns(ar, notional=None)))
    pooled = stats_rows(parts)
    res["pooled"] = {k: _r(v, 4) for k, v in pooled.items()}
    res["stress_mean"] = _r(float(np.concatenate(stress).mean() * 100), 4) if stress and sum(len(x) for x in stress) else None
    pl = placebo([(books[s]["pool"], books[s]["rows"]) for s in act], STAGE1["placebo_n"],
                 [SEED, FAMILY_NO[fam], CELLS.index(cell)])
    q95 = float(np.nanpercentile(pl, STAGE1["placebo_q"])) if np.isfinite(pl).any() else None
    res["placebo"] = {"n": int(np.isfinite(pl).sum()), "mean": _r(float(np.nanmean(pl)), 4), "q95": _r(q95, 4)}
    res["gross"] = _r(float(np.concatenate(gross).mean() * 100), 4) if gross and sum(len(x) for x in gross) else None
    res["vs_placebo"] = _r(pooled["mean"] - res["placebo"]["mean"], 4) \
        if pooled["mean"] is not None and res["placebo"]["mean"] is not None else None       # 合并净均值 − 随机对照均值（只报告）
    res["yen"] = {s: yen_per_year(panels[s], cell) for s in act if s in panels}             # ¥/年（只报告，不判定）
    aff = stats_rows(aff_parts)
    res["afford"] = {"n": aff["n"], "mean": _r(aff["mean"], 4)}
    jx = res["per_sample"].get("Jx") or {}
    n_ok = all((res["per_sample"].get(s) or {}).get("n", 0) >= STAGE1["min_n"] for s in act)
    g = {}
    g["G1"] = pooled["mean"] is not None and pooled["mean"] >= STAGE1["mean_min"] and (pooled["t"] or -9) >= STAGE1["t_min"]
    g["G3"] = all(((res["per_sample"].get(s) or {}).get("mean") or -1) > 0 for s in act) and \
        (pooled.get("h1") or -1) > 0 and (pooled.get("h2") or -1) > 0
    g["G4"] = res["stress_mean"] is not None and res["stress_mean"] > 0
    g["G5"] = q95 is not None and pooled["mean"] is not None and pooled["mean"] > q95
    g["G6"] = n_ok
    if fam == "D":
        g["G7"] = bool(drt and drt.get("ok"))
        res["drt"] = drt
    g["G8"] = aff["n"] >= STAGE1["afford_min_n"] and (aff["mean"] or -1) > 0
    g["G9"] = "Jx" in act and (jx.get("mean") or -1) >= STAGE1["jx_min"]
    res["gates"] = g
    res["p"] = pooled["p"] if (n_ok and not void) else None
    res["status"] = "不判定（数据不合格）" if void else ("样本不足、不判定" if not n_ok else "判定")
    return res


def stage1_c3(c3: dict, align_ok: bool) -> dict:
    """C3 的第一关：H1 / H2 各自 ≥ 200 笔、两半都 > 0；接线核对 2 没过 → 作废。"""
    guard_returns("第一关 C3")
    rows = c3["rows"]
    rows = rows[rows["sess"].isin(["H1", "H2"])]
    r = trade_returns(rows, notional=C3_NOTIONAL)
    st = stats_rows([("C3", rows, r)])
    res = {"cell": "C3", "pooled": {k: _r(v, 4) for k, v in st.items()}, "void": not align_ok}
    rs = trade_returns(rows, slip=SLIP_STRESS, notional=C3_NOTIONAL)
    res["stress_mean"] = _r(float(rs.mean() * 100), 4) if len(rs) else None
    R = pool_by_day_returns(c3["pool"])
    pl = placebo([({"R": R}, rows)], STAGE1["placebo_n"], [SEED, FAMILY_NO["C3"], CELLS.index("C3")], notional=C3_NOTIONAL)
    q95 = float(np.nanpercentile(pl, STAGE1["placebo_q"])) if np.isfinite(pl).any() else None
    res["placebo"] = {"n": int(np.isfinite(pl).sum()), "mean": _r(float(np.nanmean(pl)), 4), "q95": _r(q95, 4)}
    g = trade_returns(rows, slip=0.0, notional=C3_NOTIONAL) + 2 * fee_pct(C3_NOTIONAL)
    res["gross"] = _r(float(g.mean() * 100), 4) if len(g) else None
    res["vs_placebo"] = _r(st["mean"] - res["placebo"]["mean"], 4) \
        if st["mean"] is not None and res["placebo"]["mean"] is not None else None
    ar = affordable(rows)
    am = trade_returns(ar, notional=None)
    res["afford"] = {"n": int(len(ar)), "mean": _r(float(am.mean() * 100), 4) if len(am) else None}
    n_ok = st.get("n_h1", 0) >= STAGE1["c3_min_n"] and st.get("n_h2", 0) >= STAGE1["c3_min_n"]
    g = {"G1": st["mean"] is not None and st["mean"] >= STAGE1["mean_min"] and (st["t"] or -9) >= STAGE1["t_min"],
         "G3": (st.get("h1") or -1) > 0 and (st.get("h2") or -1) > 0,
         "G4": res["stress_mean"] is not None and res["stress_mean"] > 0,
         "G5": q95 is not None and st["mean"] is not None and st["mean"] > q95, "G6": n_ok,
         "G8": res["afford"]["n"] >= STAGE1["afford_min_n"] and (res["afford"]["mean"] or -1) > 0}
    res["gates"] = g
    res["p"] = st["p"] if n_ok and align_ok else None
    res["status"] = "作废（接线核对 2 没过）" if not align_ok else ("样本不足、不判定" if not n_ok else "判定")
    return res


def drt_gate(drt: dict, exit_kind: str) -> dict:
    """D 的附加门槛（第 7 条）：D-rt 在 H2 的净均值 > 0，且 ≥ 同期同一批合格票按正式收盘选票的 D 的 50%。"""
    guard_returns("D-rt")
    rt, off = drt["rt"], drt["off"]
    rt, off = rt[rt["sess"] == "H2"], off[off["sess"] == "H2"]
    a, b = trade_returns(rt), trade_returns(off)
    ma = float(a.mean() * 100) if len(a) else None
    mb = float(b.mean() * 100) if len(b) else None
    ok = ma is not None and mb is not None and ma > 0 and ma >= STAGE1["drt_share"] * mb
    return {"exit": exit_kind, "n_rt": int(len(a)), "mean_rt": _r(ma, 4), "n_off": int(len(b)), "mean_off": _r(mb, 4), "ok": bool(ok)}


def a_returns(sig: pd.DataFrame) -> pd.DataFrame:
    """A 家族逐信号的净收益（小数；价格里已经含滑点）：每种离场 ret_<模式>；配对差 d_<模式> = ret_<模式> − ret_A0。"""
    guard_returns("A 家族的收益")
    out = sig.copy()
    fee2 = 2 * fee_pct(NOTIONAL)
    for m in A_MODES:
        if f"{m}_exit" not in out.columns:
            out[f"ret_{m}"] = np.nan
            continue
        out[f"ret_{m}"] = out[f"{m}_exit"].astype(float) / out[f"{m}_entry"].astype(float) - 1 - fee2
    for m in A_MODES[1:]:
        out[f"d_{m}"] = out[f"ret_{m}"] - out["ret_A0"]
    return out


def stage1_A(cell: str, sigs: dict[str, pd.DataFrame]) -> dict:
    """A1 / A3：合并配对差 ≥ +0.20%/笔、按月聚类 t ≥ 2.0；每个样本的配对差 > 0、前后两半都 > 0；合并 ≥ 1,000 个信号、每个样本 ≥ 50。"""
    guard_returns(f"第一关 {cell}")
    parts, per = [], {}
    for smp in JUDGE["A"]:
        s = sigs.get(smp)
        if s is None or not len(s):
            per[smp] = {"n": 0}
            continue
        r = a_returns(s)
        r = r[np.isfinite(r[f"d_{cell}"])]
        st = stats_rows([(smp, r, r[f"d_{cell}"].to_numpy(float))])
        per[smp] = {k: _r(v, 4) for k, v in st.items()}
        parts.append((smp, r, r[f"d_{cell}"].to_numpy(float)))
    pooled = stats_rows(parts)
    n_ok = pooled["n"] >= A_RULES["pooled_min_n"] and all((per.get(s) or {}).get("n", 0) >= A_RULES["each_min_n"] for s in JUDGE["A"])
    g = {"G1": pooled["mean"] is not None and pooled["mean"] >= A_RULES["diff_min"] and (pooled["t"] or -9) >= A_RULES["t_min"],
         "G3": all(((per.get(s) or {}).get("mean") or -1) > 0 for s in JUDGE["A"]) and (pooled.get("h1") or -1) > 0
         and (pooled.get("h2") or -1) > 0, "G6": n_ok}
    return {"cell": cell, "per_sample": per, "pooled": {k: _r(v, 4) for k, v in pooled.items()}, "gates": g,
            "p": pooled["p"] if n_ok else None, "status": "判定" if n_ok else "样本不足、不判定"}


def a_report(sigs: dict[str, pd.DataFrame]) -> dict:
    """A 另报：每年离场次数、跳空直接穿过触发价的比例、入场当天碰到触发价的次数（只报告）、A2 的触发次数。"""
    out = {}
    for m in A_MODES:
        n_exit = gap = touch = cat = 0
        yrs = 0.0
        for smp, s in sigs.items():
            if not len(s) or f"{m}_why" not in s.columns:
                continue
            ex = s[s[f"{m}_in"].fillna(False).astype(bool)]
            n_exit += int((ex[f"{m}_why"].notna() & (ex[f"{m}_why"] != "end")).sum())   # 数据到头还没平仓（end）不算离场
            gap += int(ex[f"{m}_gap"].fillna(False).astype(bool).sum())
            touch += int(ex[f"{m}_touch"].fillna(False).astype(bool).sum())
            cat += int(ex[f"{m}_cat"].fillna(False).astype(bool).sum())
            yrs += (pd.Timestamp(WIN[smp][1]) - pd.Timestamp(WIN[smp][0])).days / 365.25
        out[m] = {"exits": n_exit, "exits_per_year": _r(n_exit / yrs if yrs else None, 1), "gap_through": gap,
                  "gap_share": _r(gap / n_exit if n_exit else None, 4), "entry_day_touch": touch, "cat_hits": cat}
    return out


def judge_A2(sigs: dict[str, pd.DataFrame], acct: dict | None) -> dict:
    """A2（不变差，不进 BH）：信号级合并配对差 ≥ −0.10%/笔；账户级 Z / E / J 每个年代 年化 ≥ A0 − 0.20pp、Calmar ≥ A0 − 0.02、
    最大回撤不比 A0 深 1pp 以上（dd 是负的 %）。"""
    guard_returns("A2")
    parts = []
    for smp in JUDGE["A"]:
        s = sigs.get(smp)
        if s is None or not len(s):
            continue
        r = a_returns(s)
        r = r[np.isfinite(r["d_A2"])]
        parts.append((smp, r, r["d_A2"].to_numpy(float)))
    st = stats_rows(parts)
    sig_ok = st["mean"] is not None and st["mean"] >= A2_RULES["diff_min"]
    eras, acct_ok = {}, acct is not None
    for e in ("Z", "E", "J"):
        if not acct:
            break
        b, c = acct["A0"][e], acct["A2"][e]
        ok = (c["cagr"] >= b["cagr"] - A2_RULES["cagr_tol"] and c["calmar"] >= b["calmar"] - A2_RULES["calmar_tol"]
              and c["dd"] >= b["dd"] - A2_RULES["dd_tol"])
        eras[e] = {"A0": {k: b[k] for k in ("cagr", "dd", "calmar", "n")}, "A2": {k: c[k] for k in ("cagr", "dd", "calmar", "n")},
                   "hits": c.get("hits"), "ok": bool(ok)}
        acct_ok &= bool(ok)
    return {"signal": {k: _r(v, 4) for k, v in st.items()}, "signal_ok": bool(sig_ok), "account": eras,
            "account_ok": bool(acct_ok), "pass": bool(sig_ok and acct_ok)}


def verdict(cell_res: dict, bh: dict[str, bool]) -> str:
    """一格的第一关结论：全部门槛 + BH 都过 → 「第一关通过」；不判定 / 作废照写。"""
    st = cell_res.get("status", "判定")
    if st != "判定":
        return st
    g = dict(cell_res.get("gates") or {})
    g["G2"] = bool(bh.get(cell_res["cell"]))
    cell_res["gates"] = g
    return "第一关通过" if all(g.values()) else "第一关不过（" + "、".join(k for k, v in sorted(g.items()) if not v) + "）"

# ───────────────────────── 第二关（只对第一关的幸存者；现在写死，到时只运行一次） ─────────────────────────
def eq_metrics(eq: pd.Series, a: str, b: str | None) -> dict:
    """权益曲线一段的 {cagr（%）, dd（负的 %）, calmar}（候选与基准用同一个函数算）。"""
    guard_returns("权益曲线的年化 / 回撤")
    x = eq[(eq.index >= pd.Timestamp(a)) & ((eq.index <= pd.Timestamp(b)) if b else True)].dropna()
    if len(x) < 20 or x.iloc[0] <= 0:
        return {"cagr": None, "dd": None, "calmar": None}
    yrs = (x.index[-1] - x.index[0]).days / 365.25
    cagr = ((x.iloc[-1] / x.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs > 0 else None
    dd = float((x / x.cummax() - 1).min() * 100)
    cal = cagr / abs(dd) if cagr is not None and dd < 0 else None
    return {"cagr": cagr, "dd": dd, "calmar": cal}


def era_metrics(eq: pd.Series, e: str) -> dict:
    import leap_common as LM
    a, b = LM.WINDOWS[e]
    out = eq_metrics(eq, a, b or J_END)
    for k, (ha, hb) in zip(("h1", "h2"), LM.HALVES[e]):
        out[k] = eq_metrics(eq, ha, hb or J_END)["calmar"]
    return out


def b0_series(W: dict, e: str) -> dict:
    """跑一次 B0（LC.run），从引擎里取每天的权益、日元现金、核心 ETF 的口数与价格、B0 的个股交易（叠加近似用）。"""
    guard_returns(f"B0 的账户 {e}")
    import jq_study as JS
    import loop_common as LC
    base = LC.run(W, e)
    eng = JS.RealLotEngine.LAST[-1]
    h = pd.DataFrame(eng.st.history, columns=["date", "equity", "cash", "usd", "fx"])
    h["date"] = pd.to_datetime(h["date"])
    h = h.set_index("date")
    g = eng.gidx
    units = {t: np.zeros(len(g)) for t in eng.cfg.core}
    ct = pd.DataFrame(eng.st.core_trades, columns=["date", "t", "side", "units", "px", "fee"])
    for t in units:
        x = ct[ct["t"] == t]
        delta = pd.Series(np.where(x["side"] == "BUY", x["units"], -x["units"]).astype(float), index=pd.to_datetime(x["date"]))
        units[t] = delta.groupby(level=0).sum().reindex(g).fillna(0.0).cumsum().to_numpy(float)
    co = {t: eng.A.open[:, eng.col[t]] for t in units}
    cc = {t: eng.A.close[:, eng.col[t]] for t in units}
    tr = pd.DataFrame(eng.st.trades)
    tr = tr[~tr["ticker"].isin(list(units))] if len(tr) else tr
    return {"base": base, "hist": h.reindex(g).ffill(), "gidx": g, "units": units, "core_open": co, "core_close": cc, "trades": tr}


def core_ret(ser: dict, a: int, a_open: bool, b: int, b_open: bool) -> float:
    """分仓那份钱如果留在核心 ETF 里，从 a（开盘 / 收盘）到 b（开盘 / 收盘）的收益（按 a 那天之前的口数加权）；没拿核心 ETF → 0。"""
    guard_returns("核心 ETF 的机会成本")
    num = den = 0.0
    for t, u in ser["units"].items():
        k = max(a - 1, 0)
        q = u[k]
        if q <= 0:
            continue
        pa = ser["core_open"][t][a] if a_open else ser["core_close"][t][a]
        pb = ser["core_open"][t][b] if b_open else ser["core_close"][t][b]
        if not (np.isfinite(pa) and np.isfinite(pb) and pa > 0):
            continue
        num += q * (pb - pa)
        den += q * pa
    return num / den if den > 0 else 0.0


def b0_busy(ser: dict, days: pd.DatetimeIndex) -> dict[pd.Timestamp, set]:
    """每天 B0 拿着的票 + 当天要买卖的票（分仓不碰）：从买入日（开盘买）到卖出日（开盘卖）为止，两头都算。
    信号日（买入日的前一个交易日）不算：B0 的买点要等那天收盘才知道，09:05 的 B / C 分仓用它就是前视；
    D 在信号日收盘买、B0 第二天开盘买同一只的冲突（执行器「每只票每天只下一笔」）不在叠加近似里处理，照实列为局限。"""
    busy: dict[pd.Timestamp, set] = {}
    tr = ser["trades"]
    if not len(tr):
        return busy
    for t, a, b in zip(tr["ticker"], pd.to_datetime(tr["entry_date"]), pd.to_datetime(tr["exit_date"])):
        lo, hi = int(days.searchsorted(a, side="left")), int(days.searchsorted(b, side="right"))
        for d in days[lo:hi]:
            busy.setdefault(d, set()).add(t)
    return busy


def b0_buys(ser: dict) -> dict[pd.Timestamp, float]:
    """B0 每天开盘买入的金额（円；07:40 定、09:00 成交，09:05 时已知）：分仓的「B0 的新仓优先」用。"""
    tr = ser["trades"]
    if not len(tr):
        return {}
    v = pd.Series(tr["entry_px"].to_numpy(float) * tr["shares"].to_numpy(float), index=pd.to_datetime(tr["entry_date"]))
    return v.groupby(level=0).sum().to_dict()


def sleeve_size(ser: dict | None, buys: dict, day) -> float:
    """当天分仓的金额 = min(权益 × 25%, 闲置资金)。ser = None（W / Jx、第一关的 ¥/年）→ 固定 ¥1,000,000 × 25%。
    权益、现金、核心 ETF 市值都用前一个交易日收盘后的账户（09:05 / 15:25 时已知，不用当天收盘之后才有的数）；
    闲置资金（现金 + 核心 ETF）再扣掉 B0 当天开盘的买入（B0 的新仓优先）。"""
    if ser is None:
        return STAGE2["capital"] * STAGE2["sleeve_pct"]
    hist = ser["hist"]                                                     # 索引 = gidx
    k = int(hist.index.searchsorted(pd.Timestamp(day), side="left")) - 1
    if k < 0:
        return 0.0
    r = hist.iloc[k]
    eq, cash = float(r["equity"]), float(r["cash"])
    if not (np.isfinite(eq) and np.isfinite(cash)):
        return 0.0
    core = sum(float(ser["units"][t][k] * ser["core_close"][t][k]) for t in ser["units"] if np.isfinite(ser["core_close"][t][k]))
    return max(0.0, min(STAGE2["sleeve_pct"] * eq, cash + core - buys.get(pd.Timestamp(day), 0.0)))


def sleeve_s5(trade: dict) -> bool:
    """第二关 S5（B / C / D）：W / Jx 上分仓自己的逐笔净均值都 > 0；没有交易 = 净均值不存在 → 不过。"""
    return all(((trade.get(s) or {}).get("n") or 0) > 0 and ((trade.get(s) or {}).get("mean") or -1) > 0 for s in ("W", "Jx"))


def sleeve_trades(P: dict, cell: str, ser: dict | None, cap_yen: float = AFFORD_CAP, rng: np.random.Generator | None = None,
                  shape: list | None = None) -> list[dict]:
    """按第二关的分仓规则在一个样本上挑交易（只有价格与股数）。shape 给了 → 随机对照：同一天、同样持有窗口，换成随机的合格且买得起的票。"""
    fam = CELL_SPEC[cell][0]
    q = prep_panel(P)
    days, names = P["days"], P["names"]
    busy = b0_busy(ser, days) if ser else {}
    buys = b0_buys(ser) if ser else {}
    lotyen = np.where(q["ok"], LOT * P["O"] * q["Fu"], np.nan)
    if fam == "D":
        lotyen = np.where(q["ok"], LOT * P["C"] * q["Fu"], np.nan)

    def sleeve_cash(i: int) -> float:
        return sleeve_size(ser, buys, days[i])

    out = []
    if shape is not None:                                                  # 随机对照：同样多、同样形状
        for s in shape:
            i, kind = s["i"], s["kind"]
            ok = P["base"][i] & np.isfinite(lotyen[i]) & (lotyen[i] <= s["slot"])
            cand = [j for j in np.flatnonzero(ok) if names[j] not in busy.get(days[i], set())]
            if not cand:
                continue
            j = int(rng.choice(cand))
            xi, xp, v = resolve_exit(P, np.array([i]), np.array([j]), kind)
            if not v[0]:
                continue
            e_px = P["C"][i, j] if fam == "D" else P["O"][i, j]
            out.append({**s, "j": j, "entry": float(e_px), "exit": float(xp[0]), "xi": int(xi[0]), "si": 1, "so": 1,
                        "lot_yen": float(lotyen[i, j])})
        return out
    if fam in ("B", "C"):
        book = cell_book(P, cell)
        fills = {(int(i), int(j)): r for i, j, r in zip(book["rows"]["i"], book["rows"]["j"], book["rows"].itertuples(index=False))}
        kind = "close1" if cell.endswith("n") else "close0"
        holding: list[int] = []
        for i in range(len(days)):
            holding = [x for x in holding if x >= i]                        # 当天收盘才卖的，09:05 时还拿着
            slot = sleeve_cash(i) / STAGE2["bc_pick"]
            if cell.endswith("n") and len(holding) >= STAGE2["bn_max_hold"]:
                continue
            ok = P["base"][i] & np.isfinite(lotyen[i]) & (lotyen[i] <= min(cap_yen, slot)) & np.isfinite(P["turn20"][i])
            cand = [j for j in np.flatnonzero(ok) if names[j] not in busy.get(days[i], set())]
            if not cand:
                continue
            room = STAGE2["bc_pick"] - (len(holding) if cell.endswith("n") else 0)
            top = sorted(cand, key=lambda j: (-P["turn20"][i, j], names[j]))[:max(0, room)]
            for j in top:
                r = fills.get((i, j))
                if r is None:
                    continue
                out.append({"i": i, "j": j, "kind": kind, "slot": slot, "entry": r.entry, "exit": r.exit, "xi": r.xi, "si": r.si,
                            "so": r.so, "lot_yen": float(lotyen[i, j])})
                holding.append(int(r.xi))
        return out
    exit_kind = CELL_SPEC[cell][1]
    k1 = q["nxt"]
    m = len(names)
    sold_open: set = set()
    cur = None                                                             # D2：连续入选同一只 → 继续拿着
    for i in range(len(days)):
        slot = sleeve_cash(i) / STAGE2["d_lot_div"]
        kk = np.where(k1[i] >= 0, k1[i], 0)
        ok = P["base"][i] & (k1[i] >= 0) & ((q["cex"][kk, np.arange(m)] - q["cex"][i]) == 0) & np.isfinite(lotyen[i]) & (lotyen[i] <= slot)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.where(ok, P["C"][i] / P["O"][i] - 1, np.inf)
        busy_i = busy.get(days[i], set())
        order = [j for j in np.argsort(r, kind="stable") if np.isfinite(r[j]) and names[j] not in busy_i
                 and not (exit_kind == "open1" and (i, j) in sold_open)]
        if not order:
            continue
        j = int(order[0])
        xi, xp, v = resolve_exit(P, np.array([i]), np.array([j]), exit_kind)
        if not v[0]:
            continue
        if exit_kind == "close1" and cur is not None and cur["j"] == j and cur["xi"] == i:
            cur.update({"exit": float(xp[0]), "xi": int(xi[0])})            # 同一只连续入选：不卖不买，延长
            continue
        cur = {"i": i, "j": j, "kind": exit_kind, "slot": slot, "entry": float(P["C"][i, j]), "exit": float(xp[0]), "xi": int(xi[0]),
               "si": 1, "so": 1, "lot_yen": float(lotyen[i, j])}
        out.append(cur)
        if exit_kind == "open1":
            sold_open.add((int(xi[0]), j))
    return out


def overlay(ser: dict, P: dict, trades: list[dict], slip: float = SLIP) -> pd.Series:
    """叠加近似：组合权益 = B0 的权益 + 分仓逐笔的円损益（按一手的实际金额收费）− 那份钱留在核心 ETF 里的收益（机会成本）。
    分仓的盈亏不回头影响 B0 的仓位（近似，照实写）。"""
    guard_returns("第二关 叠加")
    g = ser["gidx"]
    pnl = pd.Series(0.0, index=g)
    days = P["days"]
    for t in trades:
        lots = int(t["slot"] // t["lot_yen"]) if t["lot_yen"] > 0 else 0
        if lots <= 0:
            continue
        yen = lots * t["lot_yen"]
        ret = t["exit"] * (1 - slip * t["so"]) / (t["entry"] * (1 + slip * t["si"])) - 1 - 2 * fee_pct(yen)
        da, db = days[t["i"]], days[t["xi"]]
        if da not in g or db not in g:
            continue
        ia, ib = g.get_loc(da), g.get_loc(db)
        opp = core_ret(ser, ia, t.get("fam") != "D", ib, t["kind"] == "open1")     # B / C 开盘买；D 收盘买
        pnl.iloc[ib] += yen * (ret - opp)
    return ser["hist"]["equity"] + pnl.cumsum()


def yen_per_year(P: dict, cell: str) -> dict:
    """第一关另报的 ¥/年（只报告，不判定）：按第二关的分仓规则在这个样本上挑交易（第一关没有 B0 账户 → 分仓固定
    ¥1,000,000 × 25% = ¥250,000；B / C 每只 ≤ ¥125,000 且按到前一天为止的売買代金取前 2 只；D 每天 1 只、一手 ≤ 分仓 ÷ 2），
    按一手的实际金额（手数 × 一手）收個別コース的手续费，扣滑点；窗口内合计 ÷ 年数。"""
    guard_returns(f"¥/年 {cell}")
    tot, n = 0.0, 0
    for t in sleeve_trades(P, cell, None):
        lots = int(t["slot"] // t["lot_yen"]) if t["lot_yen"] > 0 else 0
        if lots <= 0:
            continue
        amt = lots * t["lot_yen"]
        ret = t["exit"] * (1 - SLIP * t["so"]) / (t["entry"] * (1 + SLIP * t["si"])) - 1 - 2 * fee_pct(amt)
        tot += amt * ret
        n += 1
    a, b = WIN[P["name"]]
    yrs = max(1e-9, (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25)
    return {"n": n, "yen_per_year": _r(tot / yrs, 0), "sleeve_yen": STAGE2["capital"] * STAGE2["sleeve_pct"]}


def stage2_cell(W: dict, cell: str, panels: dict, s1_cells: dict) -> dict:
    """B / C / D 的第二关：Z / E / J 账户叠加分仓 → research_loop.stage1（S1〜S4；S5 = W / Jx 上分仓自己的逐笔净均值 > 0）
    + 400 次「同样多、同样形状」的随机交易（S1 统计量严格大于其中最大值）。"""
    guard_returns(f"第二关 {cell}")
    import research_loop as RL
    fam = CELL_SPEC[cell][0]
    cand, base, shapes, sers = {}, {}, {}, {}
    for e in ("Z", "E", "J"):
        ser = b0_series(W, e)
        sers[e] = ser
        tr = sleeve_trades(panels[e], cell, ser)
        for t in tr:
            t["fam"] = fam
        shapes[e] = tr
        base[e] = era_metrics(ser["hist"]["equity"], e)
        cand[e] = era_metrics(overlay(ser, panels[e], tr), e)
    trade = {}
    for s in ("W", "Jx"):
        tr = sleeve_trades(panels[s], cell, None)
        rows = pd.DataFrame(tr)
        if len(rows):
            r = trade_returns(rows.assign(date=panels[s]["days"][rows["i"]]), notional=None)
            trade[s] = {"n": int(len(r)), "mean": _r(float(r.mean() * 100), 4)}
        else:
            trade[s] = {"n": 0, "mean": None}
    s1 = RL.stage1(cand, base, None, None)
    s1["S5"] = sleeve_s5(trade)
    s1["ok"] = all(bool(s1[k]) for k in ("S1", "S2", "S3", "S4", "S5", "S6"))
    rng = np.random.default_rng([SEED, FAMILY_NO[fam], 100 + CELLS.index(cell)])
    plc = []
    for _ in range(STAGE2["placebo_n"]):
        d = {}
        for e in ("Z", "E", "J"):
            tr = sleeve_trades(panels[e], cell, sers[e], rng=rng, shape=shapes[e])
            for t in tr:
                t["fam"] = fam
            d[e] = era_metrics(overlay(sers[e], panels[e], tr), e)
        plc.append(RL.era_checks(d, base)["sum"])
    s2 = RL.stage2(s1.get("sum"), plc, STAGE2["placebo_n"])
    teig = teigaku_report(sers, panels, shapes)
    return {"cell": cell, "base": {e: {k: _r(v, 4) for k, v in base[e].items()} for e in base},
            "cand": {e: {k: _r(v, 4) for k, v in cand[e].items()} for e in cand}, "stage1": {k: v for k, v in s1.items() if k != "lenses"},
            "trade": trade, "stage2": s2, "teigaku": teig, "verdict": RL.verdict(s1, s2), "approx": "叠加近似（分仓盈亏不回头影响 B0 的仓位）"}


def teigaku_report(sers: dict, panels: dict, shapes: dict) -> dict:
    """定額コース另报：全账户（B0 + 分仓）每天约定合计按 tachibana_teigaku 收费 vs 個別コース（每年円）。只报告，不判定。"""
    guard_returns("定額コース")
    out = {}
    for e, ser in sers.items():
        day_tot: dict = {}
        kob = 0.0
        tr = ser["trades"]
        for col_d, col_px in (("entry_date", "entry_px"), ("exit_date", "exit_px")):
            if not len(tr):
                break
            for d, px, sh in zip(tr[col_d], tr[col_px], tr["shares"]):
                v = float(px) * float(sh)
                day_tot[d] = day_tot.get(d, 0.0) + v
                kob += FEE(v)
        days = panels[e]["days"]
        for t in shapes[e]:
            lots = int(t["slot"] // t["lot_yen"]) if t["lot_yen"] > 0 else 0
            if lots <= 0:
                continue
            v = lots * t["lot_yen"]
            for d in (days[t["i"]], days[t["xi"]]):
                k = str(pd.Timestamp(d).date())
                day_tot[k] = day_tot.get(k, 0.0) + v
                kob += FEE(v)
        teig = sum(tachibana_teigaku(v) for v in day_tot.values())
        yrs = max(1e-9, (pd.Timestamp(WIN[e][1]) - pd.Timestamp(WIN[e][0])).days / 365.25)
        out[e] = {"kobetsu_per_year": _r(kob / yrs, 0), "teigaku_per_year": _r(teig / yrs, 0)}
    return out


def stage2_A(W: dict, cell: str, sigs: dict[str, pd.DataFrame]) -> dict:
    """A1 / A3 的第二关：B0 账户把离场换成 MinuteStopEngine（Z / E / J）→ research_loop.stage1；
    S5 = W / Jx 的逐笔胜率差与每笔差都 ≥ 0（信号级配对）；配对设计（入场完全相同）不做随机交易对照，照实写。"""
    guard_returns(f"第二关 {cell}")
    import loop_common as LC
    import research_loop as RL
    E = minute_engine_class()
    base = {e: LC.run(W, e) for e in ("Z", "E", "J")}
    cand = {e: run_A_account(W, e, cell, E) for e in ("Z", "E", "J")}
    trade = {}
    for s in ("W", "Jx"):
        r = a_returns(sigs[s])
        r = r[np.isfinite(r[f"d_{cell}"])]
        trade[s] = {"n": int(len(r)), "dwin": float(((r[f"ret_{cell}"] > 0).mean() - (r["ret_A0"] > 0).mean()) * 100) if len(r) else None,
                    "dmean": float(r[f"d_{cell}"].mean() * 100) if len(r) else None}
    s1 = RL.stage1(cand, base, trade, None)
    return {"cell": cell, "base": base, "cand": cand, "trade": trade, "stage1": {k: v for k, v in s1.items() if k != "lenses"},
            "stage2": "不适用（配对设计，入场完全相同）", "verdict": RL.FOUND if s1["ok"] else RL.FAIL1}


def stage3_check(cell: str, csv_path: Path, stage1_mean: float) -> dict:
    """第三关（前向，只追加）：至少 60 个交易日且至少 100 笔（C3：120 个交易日）；前向净均值 > 0 且 ≥ 第一关合并净均值的 50%。
    csv 的列：date, ticker, entry, exit, net_pct（成交用 com.qbreak.minutebars 存下的 Yahoo 1m 线模拟，不是真实成交）。"""
    guard_returns(f"第三关 {cell}")
    if not Path(csv_path).exists():
        return {"cell": cell, "status": "还没有前向记录"}
    df = pd.read_csv(csv_path)
    nd = int(pd.to_datetime(df["date"]).dt.normalize().nunique()) if len(df) else 0
    need_d = STAGE3["c3_min_days"] if cell == "C3" else STAGE3["min_days"]
    if nd < need_d or len(df) < STAGE3["min_trades"]:
        return {"cell": cell, "status": "样本还不够", "days": nd, "n": int(len(df))}
    m = float(df["net_pct"].mean())
    ok = m > 0 and m >= STAGE3["share_of_stage1"] * float(stage1_mean)
    return {"cell": cell, "status": "第三关通过" if ok else "第三关不过（停、不提议）", "days": nd, "n": int(len(df)), "mean": _r(m, 4)}

# ───────────────────────── 只描述（不参与判定） ─────────────────────────
def _ols(x: np.ndarray, y: np.ndarray) -> dict:
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 10 or np.std(x) == 0:
        return {"n": int(n)}
    b = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
    a = float(y.mean() - b * x.mean())
    e = y - a - b * x
    se = math.sqrt(float((e ** 2).sum()) / (n - 2) / float(((x - x.mean()) ** 2).sum()))
    return {"n": int(n), "slope": b, "t": b / se if se > 0 else None, "corr": float(np.corrcoef(x, y)[0, 1])}


def desc_etf_momentum(tab: dict[str, pd.DataFrame]) -> dict:
    """描述 1：1321 / 1306 的日内动量（Gao, Han, Li & Zhou 2018）。x = 前日正式收盘 → 10:00（09:00 那根收盘）；
    y = H1：14:00（13:00 那根收盘）→ 正式收盘；H2：15:00（14:00 那根收盘）→ 正式收盘。「全知上限」= 平均 |y| vs 往返成本。"""
    guard_returns("描述 1")
    out = {}
    cost = rt_cost(NOTIONAL, SLIP, SLIP) * 100
    for t in ETFS:
        x = tab.get(t)
        if x is None:
            continue
        for sess, cut in (("H1", 13), ("H2", 14)):
            m = (x["sess"] == sess).to_numpy()
            with np.errstate(invalid="ignore", divide="ignore"):
                xx = (x["c9"] / x["pc"] - 1).to_numpy(float)[m]
                yy = (x["C"] / x[f"c{cut}"] - 1).to_numpy(float)[m]
            r = _ols(xx, yy)
            ay = np.abs(yy[np.isfinite(yy)])
            r.update({"mean_abs_last_pct": _r(float(ay.mean() * 100), 4) if len(ay) else None, "rt_cost_pct": _r(cost, 4)})
            out[f"{lab(t)} {sess}"] = {k: (_r(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
    return out


def realism_at(d1: dict, tab: dict, m5: dict, p) -> dict:
    """描述 2：盘中暂定信号的准确率（照 exec_timing_study.realism 的做法）。截止：截至 14:00 = 13:00 那根收盘（H1 / H2）、
    截至 15:00 = 14:00 那根收盘（只 H2）、5m 的 15:20。「价格」= 成交量按日线正式量（只估价格）；「价格 + 量」只在 H2：
    量 = 截止前盘中量 ÷ 中位比例（分母 = 日线正式成交量）。必要条件（横盘、昨天 MACD ≤ 信号线、收盘 > 箱顶）都不满足的日子估算必然为假，不重算。"""
    guard_returns("描述 2")
    from qbreak.strategy import compute_indicators
    fr_h2 = {}
    for cut in (13, 14):
        v = []
        for t, x in tab.items():
            if t in ETFS:
                continue
            m = (x["sess"] == "H2").to_numpy() & (x["V"] > 0).to_numpy()
            pre = x[[f"v{h}" for h in range(9, cut + 1)]].sum(axis=1, min_count=1).to_numpy(float)
            r = pre[m] / x["V"].to_numpy(float)[m]
            v.extend(r[np.isfinite(r)].tolist())
        fr_h2[cut] = float(np.median(v)) if v else None
    res = {f"cut{c}": {} for c in (13, 14)}
    res["m5_1520"] = {}
    acc = {}

    def tally(key, est, final):
        a = acc.setdefault(key, [0, 0, 0, 0])
        a[0] += est and final
        a[1] += est and not final
        a[2] += final and not est
        a[3] += 1

    buf = 1 + float(getattr(p, "breakout_buffer_pct", 0.0)) / 100
    need_bo = bool(getattr(p, "require_breakout", True))
    for t, df in d1.items():
        if t in ETFS or t not in tab or len(df) < 400:
            continue
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        full = compute_indicators(df, p)
        mac, sig = full["macd"].to_numpy(float), full["macd_sig"].to_numpy(float)
        isr = full["is_range"].to_numpy(bool)
        bt = full["box_top"].to_numpy(float)
        ent = full["entry"].to_numpy(bool)
        x = tab[t]
        pos = {d: k for k, d in enumerate(df.index)}
        g5 = day_groups(m5[t]) if t in m5 else {}
        for d in x.index:
            k = pos.get(d)
            if k is None or k < 300:
                continue
            sess = session(d)
            r = x.loc[d]
            variants = []
            for cut in (13, 14):
                if cut == 14 and sess not in ("H2",):
                    continue
                if sess not in ("H1", "H2"):
                    continue
                cols = [h for h in range(9, cut + 1)]
                hs = [r[f"h{h}"] for h in cols if r[f"h{h}"] == r[f"h{h}"]]
                if not hs or not (r[f"c{cut}"] == r[f"c{cut}"]):
                    continue
                hi = max([r["O"]] + hs)
                lo = min([r["O"]] + [r[f"l{h}"] for h in cols if r[f"l{h}"] == r[f"l{h}"]])
                pre_v = float(np.nansum([r[f"v{h}"] for h in cols]))
                variants.append((f"cut{cut}|{sess}|price", hi, lo, float(r[f"c{cut}"]), float(r["V"])))
                if sess == "H2" and fr_h2.get(cut):
                    variants.append((f"cut{cut}|{sess}|price+vol", hi, lo, float(r[f"c{cut}"]), pre_v / fr_h2[cut]))
            day5 = g5.get(d)
            if day5 is not None and len(day5):
                pre = day5[(day5.index.hour < 15) | ((day5.index.hour == 15) & (day5.index.minute < 20))]
                if len(pre):
                    hi = max(float(r["O"]), float(pre["High"].max()))
                    lo = min(float(r["O"]), float(pre["Low"].min()))
                    variants.append((f"m5_1520|{sess}|price", hi, lo, float(pre["Close"].iloc[-1]), float(r["V"])))
            final = bool(ent[k])
            for key, hi, lo, cl, vol in variants:
                necessary = isr[k] and mac[k - 1] <= sig[k - 1] and (not need_bo or cl > bt[k] * buf)
                if not necessary and not final:
                    tally(key, False, final)
                    continue
                tail = df.iloc[k - 300:k + 1].copy()
                tail.iloc[-1, tail.columns.get_loc("High")] = hi
                tail.iloc[-1, tail.columns.get_loc("Low")] = lo
                tail.iloc[-1, tail.columns.get_loc("Close")] = cl
                tail.iloc[-1, tail.columns.get_loc("Volume")] = vol
                est = bool(compute_indicators(tail, p)["entry"].iloc[-1])
                tally(key, est, final)
    out = {"vol_frac_h2": {f"cut{c}": _r(v, 4) for c, v in fr_h2.items()}}
    for key, (tp, fp, fn, n) in sorted(acc.items()):
        out[key] = {"days": n, "tp": tp, "fp": fp, "fn": fn, "precision": _r(tp / (tp + fp), 3) if tp + fp else None,
                    "recall": _r(tp / (tp + fn), 3) if tp + fn else None}
    return out


def _first_touch(day: pd.DataFrame, level: float, side: str):
    """当天第一次碰到 level 的那根（side = low：最低 ≤；high：最高 ≥）；没有 → None。"""
    m = (day["Low"] <= level) if side == "low" else (day["High"] >= level)
    if not m.any():
        return None
    return day[m].iloc[0], day.index[np.argmax(m.to_numpy())]


def desc_fill_calib(bars_by: dict[str, dict], tab: dict) -> dict:
    """描述 3：5m / 1m 线上逆指値 / 限价的成交校准。B-2 的限价 L = 开盘 × 0.98 向下取 tick：碰到的日子里「穿过 1 tick」/「只碰到」各占多少；
    C1 的买入逆指値（开盘 × 1.02 向上取 tick）与同样距离的卖出逆指値（开盘 × 0.98）：触发那根里超过触发价多少（中位，%）、开盘直接跳过的比例。"""
    guard_returns("描述 3")
    out = {}
    for iv, bars_ in bars_by.items():
        thru = touch = 0
        over_b, close_b, gap_b, over_s, close_s, gap_s = [], [], [], [], [], []
        days = 0
        for t, h in bars_.items():
            if t in ETFS or t not in tab:
                continue
            x = tab[t]
            for d, day in day_groups(h).items():
                if d not in x.index:
                    continue
                r = x.loc[d]
                O, sf = float(r["O"]), float(r["sf"])
                if not (O == O and O > 0):
                    continue
                days += 1
                L = math.floor(O * 0.98 * sf / tick_of(O * 0.98 * sf) + 1e-9) * tick_of(O * 0.98 * sf) / sf
                tk = tick_of(L * sf) / sf
                ft = _first_touch(day, L, "low")
                if ft is not None:
                    if float(day["Low"].min()) <= L - tk + 1e-9:
                        thru += 1
                    else:
                        touch += 1
                trig = math.ceil(O * 1.02 * sf / tick_of(O * 1.02 * sf) - 1e-9) * tick_of(O * 1.02 * sf) / sf
                fb = _first_touch(day, trig, "high")
                if fb is not None:
                    b = fb[0]
                    over_b.append(float(b["High"]) / trig - 1)
                    close_b.append(float(b["Close"]) / trig - 1)
                    gap_b.append(float(b["Open"]) >= trig)
                trs = O * 0.98
                fs = _first_touch(day, trs, "low")
                if fs is not None:
                    b = fs[0]
                    over_s.append(1 - float(b["Low"]) / trs)
                    close_s.append(1 - float(b["Close"]) / trs)
                    gap_s.append(float(b["Open"]) <= trs)
        med = lambda v: _r(float(np.median(v) * 100), 4) if v else None      # noqa: E731
        out[iv] = {"ticker_days": days, "limit_touched": thru + touch, "limit_through_share": _r(thru / (thru + touch), 4) if thru + touch else None,
                   "buy_stop_n": len(over_b), "buy_stop_overshoot_med_pct": med(over_b), "buy_stop_close_vs_trig_med_pct": med(close_b),
                   "buy_stop_gap_share": _r(float(np.mean(gap_b)), 4) if gap_b else None,
                   "sell_stop_n": len(over_s), "sell_stop_overshoot_med_pct": med(over_s), "sell_stop_close_vs_trig_med_pct": med(close_s),
                   "sell_stop_gap_share": _r(float(np.mean(gap_s)), 4) if gap_s else None}
    return out


def desc_b0_split(W: dict, panels: dict, xp: dict, gap_pct: float) -> dict:
    """描述 4：B0 交易（Z / E / J 的 A0 逐信号）的收益拆成隔夜（前收 → 开盘）与日内（开盘 → 收盘）两部分（对数收益的平均，%）。"""
    guard_returns("描述 4")
    fr = a_frames(W)
    out = {}
    for smp in ("Z", "E", "J"):
        on, intr, tot = [], [], []
        for t, k, d in a_signal_list(fr[smp], smp):
            df = fr[smp][t]
            a = ticker_arrays(df, panel_F(panels[smp], t, df.index))
            r = simulate_exits(a, k, xp, "A0", gap_pct)
            if not r.get("entered") or "i_exit" not in r:
                continue
            ie, ix = r["i_entry"], r["i_exit"]
            O, C = a["O"], a["C"]
            o = float(np.sum(np.log(O[ie + 1:ix + 1] / C[ie:ix])))
            i_ = float(np.log(C[ie] / r["entry_px"]) + np.sum(np.log(C[ie + 1:ix] / O[ie + 1:ix])) + np.log(r["exit_px"] / O[ix]))
            on.append(o)
            intr.append(i_)
            tot.append(o + i_)
        if tot:
            out[smp] = {"n": len(tot), "overnight_pct": _r(float(np.mean(on) * 100), 4), "intraday_pct": _r(float(np.mean(intr) * 100), 4),
                        "total_pct": _r(float(np.mean(tot) * 100), 4)}
    return out


def desc_D_overlap_first_touch(m5: dict, tab: dict) -> dict:
    """描述 5：D —— 5m 线上「15:00 / 15:20 选出的最低 5 只」与「按正式收盘选出的 5 只」的重合率；
    B / C —— 只在 5m 有 09:00 那根的日子，第一次碰到限价 / 触发价落在 09:00〜09:05 之内的比例（照实写样本日数）。"""
    guard_returns("描述 5")
    per_day: dict = {}
    first = {"B": [0, 0], "C": [0, 0]}
    n09 = 0
    for t, h in m5.items():
        if t in ETFS or t not in tab:
            continue
        x = tab[t]
        for d, day in day_groups(h).items():
            if d not in x.index or not bool(x.loc[d, "elig"]):
                continue
            r = x.loc[d]
            O = float(r["O"])
            p1500 = day[(day.index.hour < 15)]
            p1520 = day[(day.index.hour < 15) | ((day.index.hour == 15) & (day.index.minute < 20))]
            if len(p1500) and len(p1520):
                per_day.setdefault(d, []).append((t, float(p1500["Close"].iloc[-1]) / O - 1, float(p1520["Close"].iloc[-1]) / O - 1,
                                                  float(r["C"]) / O - 1))
            if len(day) and day.index[0].hour == 9 and day.index[0].minute == 0:
                n09 += 1
                sf = float(r["sf"])
                L = math.floor(O * 0.98 * sf / tick_of(O * 0.98 * sf) + 1e-9) * tick_of(O * 0.98 * sf) / sf
                tk = tick_of(L * sf) / sf
                ft = _first_touch(day, L - tk, "low")
                if ft is not None:
                    first["B"][1] += 1
                    first["B"][0] += int(ft[1] == day.index[0])
                trig = math.ceil(O * 1.02 * sf / tick_of(O * 1.02 * sf) - 1e-9) * tick_of(O * 1.02 * sf) / sf
                fb = _first_touch(day, trig, "high")
                if fb is not None:
                    first["C"][1] += 1
                    first["C"][0] += int(fb[1] == day.index[0])
    ov = {"1500": [], "1520": []}
    for d, v in per_day.items():
        if len(v) < 10:
            continue
        df = pd.DataFrame(v, columns=["t", "r1500", "r1520", "rc"])
        fin = set(df.nsmallest(5, "rc")["t"])
        for k in ("1500", "1520"):
            ov[k].append(len(set(df.nsmallest(5, f"r{k}")["t"]) & fin) / 5)
    return {"D_overlap": {k: {"days": len(v), "mean": _r(float(np.mean(v)), 4) if v else None} for k, v in ov.items()},
            "first_touch_0900_0905": {"days_with_0900_bar": n09,
                                      **{k: {"touched": v[1], "share_in_first_bar": _r(v[0] / v[1], 4) if v[1] else None} for k, v in first.items()}}}


def outage_draws(days: pd.DatetimeIndex, rng: np.random.Generator, p: float = OUTAGE_P) -> set:
    return set(days[rng.random(len(days)) < p])


def desc_outage(W: dict, panels: dict, xp: dict, gap_pct: float, seeds: int = DESC_SEEDS) -> dict:
    """描述 6：A2 的停机情景（信号级）：每个交易日以 2% 的概率执行器没跑（收盘线的寄付卖单顺延一天、新仓不买、逆指値触发价不更新）。
    比较 A0 与 A2 最差一笔的亏损、交易收益最差 5% 的平均（CVaR5）；200 个种子的平均。窗口里没碰到停机日的信号沿用不停机的结果。"""
    guard_returns("描述 6")
    fr = a_frames(W)
    sigs = []
    for smp in SAMPLES:
        for t, k, d in a_signal_list(fr[smp], smp):
            df = fr[smp][t]
            a = ticker_arrays(df, panel_F(panels[smp], t, df.index))
            base = {m: simulate_exits(a, k, xp, m, gap_pct) for m in ("A0", "A2")}
            hi = max(base[m].get("i_exit", len(a["O"]) - 1) for m in base if base[m].get("entered")) if any(
                base[m].get("entered") for m in base) else k + 1
            pos = panels[smp]["days"].get_indexer(a["days"])                 # 这只票的每一行在样本日历上的位置（没有 = −1）
            win = pos[k + 1:min(len(a["O"]), hi + 3)]
            sigs.append((smp, a, k, base, pos, win[win >= 0]))
    fee2 = 2 * fee_pct(NOTIONAL)

    def ret(r):
        return (r["exit_px"] / r["entry_px"] - 1 - fee2) if r.get("entered") and "exit_px" in r else None

    cal = {smp: panels[smp]["days"] for smp in SAMPLES}
    agg = {m: {"worst": [], "cvar5": []} for m in ("A0", "A2")}
    for s in range(seeds):
        rng = np.random.default_rng([SEED, FAMILY_NO["A"], 1000 + s])
        off = {smp: outage_draws(cal[smp], rng) for smp in SAMPLES}
        offa = {smp: np.isin(cal[smp], list(off[smp])) for smp in SAMPLES}
        vals = {"A0": [], "A2": []}
        for smp, a, k, base, pos, win in sigs:
            hit = bool(offa[smp][win].any()) if len(win) else False
            oa = np.where(pos >= 0, offa[smp][np.maximum(pos, 0)], False) if hit else None
            for m in ("A0", "A2"):
                if hit:
                    r = simulate_exits(a, k, xp, m, gap_pct, outage=oa)
                else:
                    r = base[m]
                v = ret(r)
                if v is not None:
                    vals[m].append(v)
        for m in vals:
            v = np.sort(np.asarray(vals[m]))
            if not len(v):
                continue
            q = max(1, int(math.ceil(len(v) * 0.05)))
            agg[m]["worst"].append(float(v[0]))
            agg[m]["cvar5"].append(float(v[:q].mean()))
    return {m: {"seeds": len(agg[m]["worst"]), "worst_mean_pct": _r(float(np.mean(agg[m]["worst"]) * 100), 4) if agg[m]["worst"] else None,
                "cvar5_mean_pct": _r(float(np.mean(agg[m]["cvar5"]) * 100), 4) if agg[m]["cvar5"] else None} for m in agg}


def desc_session(tab: dict) -> dict:
    """描述 7：2024-11-05 交易时段变更前后：最后一段的波动（H1：14:00 → 收盘；H2：15:00 → 收盘）、
    「最后一根连续竞价收盘 vs 正式收盘」的差（H1：14:00 那根；H2：15:00 那根 = 15:00〜15:24）。"""
    guard_returns("描述 7")
    out = {}
    for sess, last_seg, last_bar in (("H1", 13, 14), ("H2", 14, 15)):
        seg, dif = [], []
        for t, x in tab.items():
            if t in ETFS:
                continue
            m = (x["sess"] == sess).to_numpy() & x["elig"].to_numpy(bool)
            with np.errstate(invalid="ignore", divide="ignore"):
                a = (x["C"] / x[f"c{last_seg}"] - 1).to_numpy(float)[m]
                b = (x[f"c{last_bar}"] / x["C"] - 1).to_numpy(float)[m]
            seg.extend(a[np.isfinite(a)].tolist())
            dif.extend(b[np.isfinite(b)].tolist())
        seg, dif = np.asarray(seg), np.asarray(dif)
        out[sess] = {"n": int(len(seg)), "last_segment_std_pct": _r(float(seg.std(ddof=1) * 100), 4) if len(seg) > 1 else None,
                     "last_bar_vs_close_med_abs_bp": _r(float(np.median(np.abs(dif)) * 1e4), 2) if len(dif) else None,
                     "last_bar_eq_close_share": _r(float((np.abs(dif) < 1e-9).mean()), 4) if len(dif) else None}
    return out


def desc_quality(tab: dict, m5: dict) -> dict:
    """描述 8 / 接线核对：Yahoo 盘中数据的质量（取数日重测；只有条数与比例）。
    60m：第一根开盘 = 正式开盘、最后一根收盘 = 正式收盘的比例、盘中量合计 ÷ 日线量（H1 / H2）；5m：缺 09:00〜09:04 的日子、同样两个比例。"""
    out = {}
    for sess in ("H1", "H2", "post"):
        eqo, eqc, vr, n = [], [], [], 0
        for t, x in tab.items():
            if t in ETFS:
                continue
            m = (x["sess"] == sess).to_numpy() & np.isfinite(x["o9"].to_numpy(float))
            if not m.any():
                continue
            xs = x[m]
            n += len(xs)
            eqo.extend((np.abs(xs["o9"] / xs["O"] - 1) < 1e-6).tolist())
            last = xs["c15"].where(np.isfinite(xs["c15"]), xs["c14"])
            eqc.extend((np.abs(last / xs["C"] - 1) < 1e-6).tolist())
            vs = xs[[f"v{h}" for h in HOURS]].sum(axis=1, min_count=1) / xs["V"]
            vr.extend(vs[np.isfinite(vs)].tolist())
        out[f"60m_{sess}"] = {"ticker_days": n, "first_open_eq_share": _r(float(np.mean(eqo)), 4) if eqo else None,
                              "last_close_eq_share": _r(float(np.mean(eqc)), 4) if eqc else None,
                              "vol_ratio_median": _r(float(np.median(vr)), 3) if vr else None}
    miss, eqo, eqc, vr, n = [], [], [], [], 0
    for t, h in m5.items():
        if t in ETFS or t not in tab:
            continue
        x = tab[t]
        for d, day in day_groups(h).items():
            if d not in x.index or not len(day):
                continue
            r = x.loc[d]
            n += 1
            miss.append(not (day.index[0].hour == 9 and day.index[0].minute == 0))
            eqo.append(abs(float(day["Open"].iloc[0]) / float(r["O"]) - 1) < 1e-6)
            eqc.append(abs(float(day["Close"].iloc[-1]) / float(r["C"]) - 1) < 1e-6)
            if r["V"] > 0:
                vr.append(float(day["Volume"].sum()) / float(r["V"]))
    out["5m"] = {"ticker_days": n, "missing_0900_share": _r(float(np.mean(miss)), 4) if miss else None,
                 "first_open_eq_share": _r(float(np.mean(eqo)), 4) if eqo else None,
                 "last_close_eq_share": _r(float(np.mean(eqc)), 4) if eqc else None,
                 "vol_ratio_median": _r(float(np.median(vr)), 3) if vr else None}
    return out

# ───────────────────────── 接线核对的公共部分（--check / --smoke 共用；只有条数 / 比例 / MDE） ─────────────────────────
def t2_counts(tab: dict) -> dict:
    """T2 每只的天数、H1 / H2 天数（有 60m 的日子）。"""
    per, days = [], {"H1": set(), "H2": set(), "post": set()}
    for t, x in tab.items():
        has60 = np.isfinite(x["o9"].to_numpy(float)) | np.isfinite(x["o10"].to_numpy(float))
        per.append(int(has60.sum()))
        for s in days:
            days[s] |= set(x.index[has60 & (x["sess"] == s).to_numpy()])
    return {"tickers": len(tab), "days_per_ticker_min": int(min(per)) if per else 0, "days_per_ticker_median": float(np.median(per)) if per else 0,
            "H1_days": len(days["H1"]), "H2_days": len(days["H2"]), "post_days": len(days["post"])}


def cell_counts(panels: dict) -> dict:
    """接线核对 4：每格每个样本的笔数（只有价格的逐笔，不算收益）与「一手 ≤ ¥125,000」子集的笔数。"""
    out = {}
    for cell in CELL_SPEC:
        fam = CELL_SPEC[cell][0]
        row = {}
        for smp in list(JUDGE[fam]) + list(REFERENCE.get(fam, ())):
            P = panels.get(smp)
            if P is None:
                continue
            b = cell_book(P, cell)
            aff = cell_book(P, cell, afford=True)["rows"] if fam == "D" else affordable(b["rows"])
            row[smp] = {"n": int(len(b["rows"])), "afford_n": int(len(aff)), "fills": b["fills"], "dropped": b["dropped_ex_or_nodata"]}
        out[cell] = row
    return out


def run_counts(books: dict) -> dict:
    """--run 的笔数表，格式同 cell_counts（{格: {样本: {"n": 笔数}}}）：cell_mde 只读 "n"。"""
    return {c: {s: {"n": int(len(b["rows"]))} for s, b in bk.items()} for c, bk in books.items()}


def cell_mde(panels: dict, counts: dict, extra: dict | None = None) -> dict:
    """接线核对 6：每格的 MDE（判定样本合并）与「检验力不足」标记（MDE > 净门槛）。extra = {格: (每天的等权窗口收益表, 笔数)}。"""
    out = {}
    for cell in CELL_SPEC:
        fam = CELL_SPEC[cell][0]
        act, bad, void = judge_family_samples(fam, panels)
        dd = [market_days(panels[s], WINDOW_OF[cell]) for s in act if s in panels]
        n = sum((counts.get(cell, {}).get(s) or {}).get("n", 0) for s in act)
        r = mde_from(pd.concat(dd) if dd else None, n)
        r["n"] = n
        out[cell] = r
    for cell, (days, n) in (extra or {}).items():
        r = mde_from(days, n)
        r["n"] = n
        out[cell] = r
    for cell, r in out.items():
        r["underpowered"] = bool(r.get("mde") is not None and r["mde"] > MDE_NET.get(cell, STAGE1["mean_min"]))
        r["mde"] = _r(r.get("mde"), 4)
        for k in ("per_month", "s_common", "s_idio"):
            r.pop(k, None) if k != "per_month" else r.__setitem__(k, _r(r.get(k), 2))
    return out


def c3_market_days(tab: dict) -> pd.DataFrame:
    """C3 的 MDE 用：H1 / H2 每天全部合格票（日経225）10:00 那根开盘 → 正式收盘的等权收益（不是候选的收益）。"""
    recs = []
    for t, x in tab.items():
        if t in ETFS:
            continue
        m = x["elig"].to_numpy(bool) & np.isin(x["sess"].to_numpy(object), ["H1", "H2"]) & np.isfinite(x["o10"].to_numpy(float))
        with np.errstate(invalid="ignore", divide="ignore"):
            r = (x["C"] / x["o10"] - 1).to_numpy(float)
        recs.append(pd.DataFrame({"date": x.index[m], "r": r[m]}))
    if not recs:
        return pd.DataFrame(columns=["date", "m", "v", "n"])
    df = pd.concat(recs)
    g = df.groupby("date")["r"]
    out = pd.DataFrame({"m": g.mean(), "v": g.var(ddof=1), "n": g.size()}).reset_index()
    return out[out["n"] >= 5]


def check_core(panels: dict, tab: dict, h60: dict, m5: dict, d1: dict, a_counts: dict | None = None,
               a_days: dict | None = None) -> dict:
    """接线核对 1 / 2 / 4 / 5 / 6（不含引擎逐笔核对 3）：只有条数、比例、MDE。"""
    t0 = time.time()
    res = {"panels": {k: v["stats"] for k, v in panels.items()}}
    if "Jx" in panels and "pit" in panels["Jx"]:
        res["jx_pit"] = panels["Jx"]["pit"]
    res["t2"] = t2_counts(tab)
    res["align"] = align_check(h60, m5, d1)
    res["quality"] = desc_quality(tab, m5)
    counts = cell_counts(panels)
    res["counts"] = counts
    c3 = fam_C3({t: x for t, x in tab.items() if t not in ETFS})
    c3r = c3["rows"]
    res["counts"]["C3"] = {s: {"n": int((c3r["sess"] == s).sum()) if len(c3r) else 0,
                               "afford_n": int(((c3r["sess"] == s) & (c3r["lot_yen"] <= AFFORD_CAP)).sum()) if len(c3r) else 0}
                           for s in ("H1", "H2", "post")}
    drt = {}
    for ek in ("open1", "close1"):
        d = fam_D_rt({t: x for t, x in tab.items() if t not in ETFS}, ek)
        drt[ek] = {"valid_ticker_days": d["n_valid"], "rt_n": int(len(d["rt"])), "off_n": int(len(d["off"]))}
    res["drt_counts"] = drt
    extra = {"C3": (c3_market_days(tab), int(c3r["sess"].isin(["H1", "H2"]).sum()) if len(c3r) else 0)}
    for cell in ("A1", "A3"):
        if a_days is not None:
            extra[cell] = (a_days.get(cell), (a_counts or {}).get(cell, {}).get("pooled", 0))
    res["mde"] = cell_mde(panels, counts, extra)
    if a_counts is not None:
        res["counts"]["A"] = a_counts
    res["seconds"] = round(time.time() - t0, 1)
    return res


def a_counts_from(sigs: dict[str, pd.DataFrame]) -> dict:
    """A 的条数：每个样本的信号数、入场数、两种离场都有出场的信号数（配对的样本量；不算收益）。"""
    out = {}
    for cell in ("A1", "A3", "A2"):
        per = {}
        for smp, s in sigs.items():
            if not len(s):
                per[smp] = 0
                continue
            ok = s["A0_in"].fillna(False).astype(bool) & s[f"{cell}_in"].fillna(False).astype(bool)
            ok &= s["A0_exit"].notna() & s[f"{cell}_exit"].notna()
            per[smp] = int(ok.sum())
        out[cell] = {"per_sample": per, "pooled": int(sum(per.values()))}
    out["signals"] = {smp: int(len(s)) for smp, s in sigs.items()}
    return out


def say_check(res: dict) -> None:
    """把接线核对的结果打印成表（只有条数 / 比例 / MDE）。"""
    say("\n## 1. 各样本（「票·日」；只有条数与比例）")
    say("| 样本 | 票数 | 窗口交易日 | 有数据的「票·日」 | 合格 | 矛盾 | 超出制限値幅 | 非成员 | 売買代金不足 | 还原不了不复权价 | 开盘 = 前日收盘 | O = H = L = C | 除权日 | 数据不合格 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, s in res["panels"].items():
        say(f"| {k} | {s['tickers']} | {s['days_in_window']} | {s['ticker_days']:,} | {s['eligible']:,} | {s['excl_inconsistent']:,} | "
            f"{s['excl_over_limit']:,} | {s['excl_member']:,} | {s['excl_turnover']:,} | {s['no_raw_share']} | {s['open_eq_prev_share']} | "
            f"{s['flat_share']} | {s['ex_days']:,} | {'是' if s['bad_data'] else '否'} |")
    if res.get("jx_pit"):
        j = res["jx_pit"]
        say(f"- Jx：{j['names']} 只；窗口内退市 {j['delisted_in_window']} 只、被剔除出 TOPIX 1000 {j['dropped_from_topix1000']} 只"
            + ("" if j["true_pit"] else "（都是 0 → Jx 也不是真正的时点池）"))
    t = res["t2"]
    say(f"- T2：{t['tickers']} 只；每只有 60m 的天数 最少 {t['days_per_ticker_min']}、中位 {t['days_per_ticker_median']:.0f}；"
        f"H1 {t['H1_days']} 天、H2 {t['H2_days']} 天、之后（只描述）{t['post_days']} 天")
    a = res["align"]
    say(f"\n## 2. 60m 与 5m 合成（{a['bars_10_14_compared']:,} 根 10:00〜14:00）")
    say(f"- O / H / L / C 一致率：{a['match_share']}；时间戳 = 整点开始的比例 {a['start_stamp_share']}；H2 09:00 那根量 0 的比例 {a['h2_0900_vol0_share']}")
    say(f"- H1 15:00 那根（{a['h1_1500_bars']:,} 根）：量 0 的比例 {a['h1_1500_vol0_share']}、收盘与正式收盘差 ≤ 0.5% 的比例 {a['h1_1500_close_share']}"
        f" → {'通过' if a['ok'] else '没通过（C3 作废）'}")
    if res.get("engine"):
        say("\n## 3. A0 / A1 逐信号模拟 vs UnifiedEngine 单信号回测（入场价、出场日、出场价到 4 位小数）")
        say("| 样本 | 信号 | A0 笔数 | 一致 | 两边都没成交 | 窗口内没平仓 | intraday 笔数 | 一致 | A1 可比 | A1 = intraday | 入场当天碰到 | 结论 |")
        say("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for k, v in res["engine"].items():
            if not isinstance(v, dict):
                continue
            say(f"| {k} | {v['signals']} | {v['A0_trades']} | {v['A0_match']} | {v['A0_no_entry']} | {v['A0_unclosed']} | {v['INTRA_trades']} | "
                f"{v['INTRA_match']} | {v['A1_comparable']} | {v['A1_same_as_intra']} | {v['A1_entry_touch']} | "
                f"{'一致' if v['ok'] else '不一致：' + '；'.join(v['mismatch_examples'])} |")
    say("\n## 4. 每格的笔数（「一手 ≤ ¥125,000」子集）")
    for cell, row in res["counts"].items():
        if cell == "A":
            for c, v in row.items():
                if c == "signals":
                    say(f"- A 信号数：{v}")
                else:
                    say(f"- {c}：配对样本 {v['per_sample']}，合并 {v['pooled']}")
            continue
        say(f"- {cell}：" + "；".join(f"{s} {v['n']:,}（{v['afford_n']:,}）" for s, v in row.items()))
    for ek, v in res.get("drt_counts", {}).items():
        say(f"- D-rt（{ek}）：合格「票·日」{v['valid_ticker_days']:,}，按 14:00 那根选 {v['rt_n']:,} 笔，按正式收盘选 {v['off_n']:,} 笔")
    q = res["quality"]
    say("\n## 5. Yahoo 盘中数据质量（条数与比例）")
    for k, v in q.items():
        say(f"- {k}：{v}")
    say("\n## 6. MDE（80% 检验力、单边 α = 0.10 / 11；全部合格票等权窗口收益的月均值标准差估；A 是偏保守的上界）")
    say("| 格 | 笔数 | 月数 | 每月笔数 | MDE（%/笔） | 净门槛 | 检验力不足 |")
    say("|---|---|---|---|---|---|---|")
    for cell in CELLS:
        r = res["mde"].get(cell) or {}
        say(f"| {cell} | {r.get('n', 0):,} | {r.get('months', 0)} | {r.get('per_month')} | {r.get('mde')} | {MDE_NET[cell]:.2f} | "
            f"{'是' if r.get('underpowered') else '否'} |")


def strip_returns(o):
    """--check / --smoke 的输出保护：任何像收益的键（mean / median / win / ret / pnl / gross / net / t / p / h1 / h2）一律不许出现。"""
    bad = {"mean", "median", "win", "ret", "pnl", "gross", "net", "t", "p", "h1", "h2", "cagr", "calmar", "dd", "vs_placebo",
           "yen", "yen_per_year", "sum_logret", "sum_log_oc"}
    if isinstance(o, dict):
        for k in o:
            if str(k) in bad:
                raise ReturnGuardError(f"--{MODE['name']} 的输出里出现了收益字段 {k}")
            strip_returns(o[k])
    elif isinstance(o, (list, tuple)):
        for v in o:
            strip_returns(v)
    return o


# ───────────────────────── 合成数据（--smoke 与测试用） ─────────────────────────
def synth_panel(name: str, n_days: int = 320, n_names: int = 30, seed: int = 7, member: bool = False) -> dict:
    rng = np.random.default_rng(seed)
    a, b = WIN[name]
    days = pd.bdate_range(pd.Timestamp(a) - pd.Timedelta(days=60), periods=n_days)
    lr = rng.normal(0, 0.02, (n_days, n_names))
    C = 1000 * np.exp(np.cumsum(lr, axis=0)) * rng.uniform(0.3, 3, n_names)[None, :]
    O = C * np.exp(rng.normal(0, 0.01, C.shape))
    H = np.maximum(O, C) * (1 + np.abs(rng.normal(0, 0.01, C.shape)))
    L = np.minimum(O, C) * (1 - np.abs(rng.normal(0, 0.01, C.shape)))
    V = rng.uniform(1e5, 1e6, C.shape) * 10
    names = [f"{9000 + k}.T" for k in range(n_names)]
    S = np.ones_like(C)
    Dv = np.ones_like(C)
    ex = np.zeros(C.shape, bool)
    ex[n_days // 2, 0] = True
    mem = np.ones(C.shape, bool) if member else None
    return build_panel(name, {"O": O, "H": H, "L": L, "C": C, "V": V}, days, names, S, Dv, ex, member=mem,
                       turnover=name in ("W", "Jx"))


def synth_t2(n_names: int = 8, n_days: int = 40, seed: int = 11) -> tuple[dict, dict, dict, dict]:
    """合成的 60m / 5m / 不复权日线 / 公司行为（H1 一半、H2 一半的日子）。"""
    rng = np.random.default_rng(seed)
    d_h1 = pd.bdate_range("2024-09-02", periods=n_days // 2)
    d_h2 = pd.bdate_range("2025-03-03", periods=n_days - n_days // 2)
    days = d_h1.append(d_h2)
    h60, m5, d1, acts = {}, {}, {}, {}
    for k in range(n_names):
        t = f"{9100 + k}.T" if k < n_names - 1 else ETFS[0]
        px = 1000 * rng.uniform(0.5, 2)
        rows60, rows5, rowsd = [], [], []
        for d in days:
            sess = session(d)
            o = px * np.exp(rng.normal(0, 0.01))
            p = o
            path = [p]
            for _ in range(66):
                p *= np.exp(rng.normal(0, 0.003))
                path.append(p)
            path = np.array(path)
            c = path[-1]
            rowsd.append((d, o, max(path.max(), o), min(path.min(), o), c, c, 1e6))
            hours = [9, 10, 11, 12, 13, 14] + ([15] if True else [])
            seg = np.array_split(path[1:], len(hours))
            for hh, sg in zip(hours, seg):
                ts = pd.Timestamp(d) + pd.Timedelta(hours=hh)
                if sess == "H1" and hh == 15:
                    rows60.append((ts.tz_localize("Asia/Tokyo"), c, c, c, c, 0.0))
                    continue
                rows60.append((ts.tz_localize("Asia/Tokyo"), sg[0], sg.max(), sg.min(), sg[-1], 1e5))
                if sess == "H2":
                    for q, sub in enumerate(np.array_split(sg, 12)):
                        if not len(sub):
                            continue
                        rows5.append(((ts + pd.Timedelta(minutes=5 * q)).tz_localize("Asia/Tokyo"), sub[0], sub.max(), sub.min(), sub[-1], 1e4))
            px = c
        cols = ["Open", "High", "Low", "Close", "Volume"]
        h = pd.DataFrame([r[1:] for r in rows60], index=pd.DatetimeIndex([r[0] for r in rows60]), columns=cols)
        h.attrs["basis"] = "raw"
        h60[t] = h
        f5 = pd.DataFrame([r[1:] for r in rows5], index=pd.DatetimeIndex([r[0] for r in rows5]), columns=cols)
        f5.attrs["basis"] = "raw"
        m5[t] = f5
        dd = pd.DataFrame([r[1:] for r in rowsd], index=pd.DatetimeIndex([r[0] for r in rowsd]),
                          columns=["Open", "High", "Low", "Close", "AdjClose", "Volume"])
        dd.attrs["basis"] = "raw"
        d1[t] = dd
        a = pd.DataFrame({"div": [0.0], "split": [2.0]}, index=pd.DatetimeIndex([days[5]]))
        a.attrs["basis"] = "raw"
        acts[t] = a if k == 0 else pd.DataFrame(columns=["div", "split"])
    return h60, m5, d1, acts


def synth_signals(n: int = 40, seed: int = 5) -> tuple[dict, list]:
    """合成的指标表与买点（逐信号模拟用）。"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2010-01-04", periods=260)
    C = 1000 * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
    O = C * np.exp(rng.normal(0, 0.01, len(days)))
    H = np.maximum(O, C) * 1.01
    L = np.minimum(O, C) * 0.99
    df = pd.DataFrame({"Open": O, "High": H, "Low": L, "Close": C, "atr": C * 0.02, "climax": False, "entry": False}, index=days)
    ks = sorted(rng.choice(np.arange(5, 200), n, replace=False).tolist())
    return {"9999.T": df}, ks


def do_smoke() -> int:
    """--smoke：只用合成数据跑通（价格生成 → 条数 → MDE），不算任何收益；写 var/out/minute_study_partial.{md,json}（已 gitignore）。"""
    set_mode("smoke")
    t0 = time.time()
    LINES.clear()
    say("# 分钟 K 线研究 —— 合成数据冒烟（不算收益）")
    panels = {"Z": synth_panel("Z", seed=1), "E": synth_panel("E", seed=2), "J": synth_panel("J", seed=3),
              "W": synth_panel("W", seed=4), "Jx": synth_panel("Jx", seed=5, member=True)}
    h60, m5, d1, acts = synth_t2()
    tab = t2_table(h60, d1, acts, list(h60))
    frames, ks = synth_signals()
    df = frames["9999.T"]
    a = ticker_arrays(df)
    xp = {"stop": 0.07, "trail": 0.12, "tp": 0.25, "chand": 3.0, "climax": True, "climax_gain": 5.0, "max_hold": 60}
    sig = []
    for k in ks:
        row = {"date": df.index[k]}
        for m in A_MODES:
            r = simulate_exits(a, k, xp, m)
            row[f"{m}_in"] = r["entered"]
            row[f"{m}_exit"] = r.get("exit_px", np.nan) if r["entered"] else np.nan
        sig.append(row)
    sigs = {"Z": pd.DataFrame(sig)}
    res = check_core(panels, tab, h60, m5, d1, a_counts=a_counts_from(sigs))
    res["mode"], res["synthetic"], res["seconds"] = "smoke", True, round(time.time() - t0, 1)
    strip_returns(res)
    say_check(res)
    out_path("json", partial=True).parent.mkdir(parents=True, exist_ok=True)
    out_path("json", partial=True).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    out_path("md", partial=True).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    say(f"\n冒烟完成（{time.time() - t0:.0f}s）→ {out_path('json', partial=True).name}")
    return 0


# ───────────────────────── --check ─────────────────────────
def load_t2(man: dict) -> tuple[dict, dict, dict, dict]:
    fd = man["fetch_date"]
    return load_cache("60m", fd), load_cache("5m", fd), load_cache("1d_raw", fd), load_cache("actions", fd)


def do_check() -> int:
    """--check：接线核对，只打印条数 / 比例 / MDE / 一致性 / 耗时；不算、不写、不打印任何收益。"""
    set_mode("check")
    t0 = time.time()
    LINES.clear()
    say(f"# 分钟 K 线研究 —— 接线核对（{pd.Timestamp.now(tz='Asia/Tokyo'):%Y-%m-%d %H:%M} JST；不算收益）")
    man = read_manifest()
    bad = verify_manifest(man)
    say("- 冻结清单：" + ("一致" if not bad else "；".join(bad)))
    if not man:
        return 2
    for k, v in man["files"].items():
        say(f"  - {v['file']}：{v['rows']:,} 行、{v['tickers']} 只、sha256 {v['sha256'][:16]}…")
    if any(man.get("missing", {}).values()):
        say("  - 拿不到：" + "；".join(f"{k} {'、'.join(lab(t) for t in v)}" for k, v in man["missing"].items() if v))
    h60, m5, d1, acts = load_t2(man)
    tab = t2_table(h60, d1, acts, sorted(set(h60) | set(d1)))
    say(f"- 读缓存 + T2 日表（{time.time() - t0:.0f}s）")
    import loop_common as LC
    W = LC.load()
    say(f"- LC.load（{time.time() - t0:.0f}s）")
    panels = daily_panels(W)
    fp = panel_fingerprint(panels)
    say(f"- 日线宽表指纹 {fp['sha']}（只记录，不拒绝运行）（{time.time() - t0:.0f}s）")
    if man is not None and "daily_fingerprint" not in man:
        man["daily_fingerprint"] = fp
        freeze_path().write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        say("  - 指纹记进冻结清单（只这一次）")
    from qbreak.unified import exec_configs
    gap = exec_configs(("JP",), {"broker": "tachibana"})["JP"].max_entry_gap_pct
    xp = exit_params(W["px"])
    sigs = fam_A_signal(W, panels, xp, gap)
    a_cnt = a_counts_from(sigs)
    a_days = {}
    for cell in ("A1", "A3"):
        parts = [a_market_days(W, panels, sigs[s], s) for s in JUDGE["A"] if s in sigs]
        a_days[cell] = pd.concat(parts) if parts else None
    say(f"- A 逐信号（只有价格）（{time.time() - t0:.0f}s）")
    res = check_core(panels, tab, h60, m5, d1, a_counts=a_cnt, a_days=a_days)
    say(f"- 条数 / MDE（{time.time() - t0:.0f}s）")
    res["engine"] = check_vs_engine(W, W["px"], gap)
    say(f"- 引擎逐笔核对（{time.time() - t0:.0f}s）")
    res["fingerprint"] = fp
    res["seconds"] = round(time.time() - t0, 1)
    strip_returns(res)
    say_check(res)
    say(f"\n接线核对完成（{time.time() - t0:.0f}s）。没有算、没有写、没有打印任何候选收益。")
    return 0


# ───────────────────────── --run（只运行一次） ─────────────────────────
def git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:                                                     # noqa: BLE001
        return None


STUDY_FILES = ("scripts/minute_study.py", "tests/test_minute_study.py", f"var/{FREEZE}")


def git_dirty() -> list[str]:
    """被跟踪文件的未提交改动 + 这项研究自己的文件还没提交（脚本 / 测试 / 冻结清单是未跟踪的 = 登记还没提交）。"""
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout
        new = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", *STUDY_FILES], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    except Exception:                                                     # noqa: BLE001
        return ["git status 失败"]
    return [x for x in out.splitlines() if x.strip()] + [x for x in new.splitlines() if x.startswith("??")]


def run_refusals() -> list[str]:
    """--run 拒绝运行的理由（空 = 可以运行）。"""
    why = []
    fp = out_path("json")
    if fp.exists():
        try:
            if json.loads(fp.read_text(encoding="utf-8")).get("ran"):
                why.append(f"{fp.name} 里已经有 \"ran\": true（只运行一次）")
        except Exception:                                                 # noqa: BLE001
            why.append(f"{fp.name} 读不了")
    hard = hard_mismatch(verify_manifest(read_manifest()))
    why.extend(hard)
    dirty = git_dirty()
    if dirty:
        why.append("工作区有未提交的改动：" + "；".join(dirty[:5]))
    return why


def do_run() -> int:
    """--run：第一关 + A2 + 描述项（+ 第一关幸存者的第二关），只运行一次 → var/out/minute_study.{md,json}。"""
    why = run_refusals()
    if why:
        for w in why:
            print(f"拒绝运行：{w}", file=sys.stderr)
        return 3
    set_mode("run")
    t0 = time.time()
    LINES.clear()
    man = read_manifest()
    res = {"ran": True, "git_head": git_head(), "started": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(timespec="seconds"),
           "freeze": {k: {"sha256": v["sha256"], "rows": v["rows"]} for k, v in man["files"].items()},
           "yfinance_frozen": man.get("yfinance"), "manifest_notes": verify_manifest(man)}
    say(f"# 分钟 K 线 / 日内规则（A〜D）—— 结果（{res['started']}；git {str(res['git_head'])[:10]}）")
    h60, m5, d1, acts = load_t2(man)
    tab = t2_table(h60, d1, acts, sorted(set(h60) | set(d1)))
    stocks = {t: x for t, x in tab.items() if t not in ETFS}
    align = align_check(h60, m5, d1)
    res["align"] = align
    import loop_common as LC
    W = LC.load()
    panels = daily_panels(W)
    fp = panel_fingerprint(panels)
    res["fingerprint"] = {"now": fp["sha"], "frozen": (man.get("daily_fingerprint") or {}).get("sha")}
    from qbreak.unified import exec_configs
    gap = exec_configs(("JP",), {"broker": "tachibana"})["JP"].max_entry_gap_pct
    xp = exit_params(W["px"])
    # A
    sigs = fam_A_signal(W, panels, xp, gap)
    cells = {c: stage1_A(c, sigs) for c in ("A1", "A3")}
    res["A_report"] = a_report(sigs)
    acct = {"A0": {e: LC.run(W, e) for e in ("Z", "E", "J")}, "A2": {}}
    E = minute_engine_class()
    for e in ("Z", "E", "J"):
        acct["A2"][e] = run_A_account(W, e, "A2", E)
    res["A2"] = judge_A2(sigs, acct)
    say(f"- A（{time.time() - t0:.0f}s）")
    # B / C / D
    books = {c: {} for c in CELL_SPEC}
    for cell in CELL_SPEC:
        fam = CELL_SPEC[cell][0]
        for smp in list(JUDGE[fam]) + list(REFERENCE.get(fam, ())):
            books[cell][smp] = cell_book(panels[smp], cell)
    drt = {}
    for cell, ek in (("D1", "open1"), ("D2", "close1")):
        drt[cell] = drt_gate(fam_D_rt(stocks, ek), ek)
        rep = {}
        for nm, cut, ss in (("H2_15:25", 15, ("H2",)), ("H1_14:00", 13, ("H1",))):
            d = fam_D_rt(stocks, ek, cut=cut, sessions=ss)
            r = trade_returns(d["rt"])
            rep[nm] = {"n": int(len(r)), "mean": _r(float(r.mean() * 100), 4) if len(r) else None}
        drt[cell]["report_only"] = rep
    for cell in CELL_SPEC:
        fam = CELL_SPEC[cell][0]
        aff = {s: cell_book(panels[s], cell, afford=True) for s in JUDGE[fam]} if fam == "D" else None
        cells[cell] = stage1_cell(cell, books[cell], panels, aff, drt.get(cell))
    say(f"- B / C / D（{time.time() - t0:.0f}s）")
    c3 = fam_C3(stocks)
    cells["C3"] = stage1_c3(c3, bool(align["ok"]))
    say(f"- C3（{time.time() - t0:.0f}s）")
    bh = apply_bh({c: cells[c].get("p") for c in CELLS})
    for c in CELLS:
        cells[c]["bh"] = bh[c]
        cells[c]["verdict"] = verdict(cells[c], bh)
    res["cells"] = cells
    # 第二关（只对第一关的幸存者）
    st2 = {}
    for c in CELLS:
        if cells[c]["verdict"] != "第一关通过":
            continue
        if c == "C3":
            st2[c] = {"verdict": "作废（定义上的硬伤：Z / E / J 没有分钟线，第二关的账户叠加做不了）"}
        elif c in ("A1", "A3"):
            st2[c] = stage2_A(W, c, sigs)
        else:
            st2[c] = stage2_cell(W, c, panels, cells)
    res["stage2"] = st2
    say(f"- 第二关（{time.time() - t0:.0f}s）")
    # 描述
    m1 = load_cache("1m", man["fetch_date"])
    desc = {"1_etf_momentum": desc_etf_momentum(tab), "2_realism_at": realism_at(d1, tab, m5, W["p"]),
            "3_fill_calib": desc_fill_calib({"5m": m5, "1m": m1}, tab), "4_b0_split": desc_b0_split(W, panels, xp, gap),
            "5_D_overlap_first_touch": desc_D_overlap_first_touch(m5, tab), "6_outage": desc_outage(W, panels, xp, gap),
            "7_session": desc_session(tab), "8_quality": desc_quality(tab, m5)}
    res["desc"] = desc
    say(f"- 描述（{time.time() - t0:.0f}s）")
    res["mde"] = cell_mde(panels, run_counts(books), {"C3": (c3_market_days(tab), int(c3["rows"]["sess"].isin(["H1", "H2"]).sum()))})
    res["seconds"] = round(time.time() - t0, 1)
    write_json(res)                                                       # 先写 JSON（"ran": true）：后面出错也不能再跑第二次
    write_md(res)
    say(f"\n完成（{time.time() - t0:.0f}s）→ {out_path('md').relative_to(ROOT)}、{out_path('json').relative_to(ROOT)}")
    return 0


def _fmt(x, d: int = 3, pct: bool = True) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.{d}f}{'%' if pct else ''}"


def write_md(res: dict) -> None:
    """结果的 Markdown（只有汇总统计）。"""
    L = [f"# 分钟 K 线 / 日内规则（A〜D）—— 结果",
         "",
         f"登记见 var/sim_changes.md 2026-10-15「分钟 K 线 / 日内规则」；git {res.get('git_head')}；只运行一次；税前；非投资建议。",
         "",
         "## 第一关（11 格进 BH，q = 0.10，m = 11）",
         "",
         "| 格 | 合并笔数 | 净均值 | 中位 | 胜率 | 月数 | t | p | BH | 前半 / 后半 | 滑点 ×2 | 随机对照 95 分位 | 买得起子集 | 结论 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in CELLS:
        r = res["cells"][c]
        p = r.get("pooled") or {}
        L.append(f"| {c} | {p.get('n', 0):,} | {_fmt(p.get('mean'))} | {_fmt(p.get('median'))} | {_fmt(p.get('win'), 1, False)} | {p.get('months', 0)} | "
                 f"{_fmt(p.get('t'), 2, False)} | {_fmt(p.get('p'), 4, False)} | {'过' if r.get('bh') else '不过'} | {_fmt(p.get('h1'))} / {_fmt(p.get('h2'))} | "
                 f"{_fmt(r.get('stress_mean'))} | {_fmt((r.get('placebo') or {}).get('q95'))} | "
                 f"{(r.get('afford') or {}).get('n', '—')} 笔 {_fmt((r.get('afford') or {}).get('mean'))} | {r.get('verdict')} |")
    L += ["", "（A1 / A3 的「净均值」= 配对差 Ax − A0；B / C / D 是逐笔净收益；C3 的前半 / 后半 = H1 / H2）", "",
          "## 另报（只报告，不判定）", "",
          "| 格 | 合并毛均值 | 净均值 − 随机对照均值 | 随机对照均值 | ¥/年（分仓 ¥250,000，按样本） |", "|---|---|---|---|---|"]
    for c in CELLS:
        r = res["cells"][c]
        if c in ("A1", "A3"):
            continue
        yen = "；".join(f"{s} ¥{v['yen_per_year']:+,.0f}（{v['n']:,} 笔）" for s, v in (r.get("yen") or {}).items()
                       if v.get("yen_per_year") is not None) or "—"
        L.append(f"| {c} | {_fmt(r.get('gross'))} | {_fmt(r.get('vs_placebo'))} | {_fmt((r.get('placebo') or {}).get('mean'))} | {yen} |")
    L += ["", "（C3 没有 ¥/年：第二关做不了，见登记；¥/年 按第二关的分仓规则、固定 ¥1,000,000 × 25%、一手的实际金额收费）", "", "## 各样本"]
    for c in CELLS:
        r = res["cells"][c]
        for grp in ("per_sample", "reference"):
            for s, v in (r.get(grp) or {}).items():
                L.append(f"- {c} {s}{'（只参考）' if grp == 'reference' else ''}：{v.get('n', 0):,} 笔，净均值 {_fmt(v.get('mean'))}，t {_fmt(v.get('t'), 2, False)}，"
                         f"前半 {_fmt(v.get('h1'))} / 后半 {_fmt(v.get('h2'))}" + (f"，每年 {v['per_year']:.0f} 笔" if v.get("per_year") else ""))
        if r.get("drt"):
            d = r["drt"]
            L.append(f"- {c} D-rt（H2）：{d['n_rt']} 笔 {_fmt(d['mean_rt'])} vs 按正式收盘 {d['n_off']} 笔 {_fmt(d['mean_off'])} → {'过' if d['ok'] else '不过'}；"
                     f"只报告：{d.get('report_only')}")
    a2 = res["A2"]
    L += ["", "## A2（不变差，不进 BH）", f"- 信号级配对差 {_fmt((a2['signal'] or {}).get('mean'))}（{(a2['signal'] or {}).get('n', 0)} 个）→ {'过' if a2['signal_ok'] else '不过'}"]
    for e, v in a2["account"].items():
        L.append(f"- {e}：A0 年化 {_fmt(v['A0']['cagr'], 2)} / 回撤 {_fmt(v['A0']['dd'], 2)} / Calmar {_fmt(v['A0']['calmar'], 3, False)}；"
                 f"A2 {_fmt(v['A2']['cagr'], 2)} / {_fmt(v['A2']['dd'], 2)} / {_fmt(v['A2']['calmar'], 3, False)}；触发 {v.get('hits')} → {'过' if v['ok'] else '不过'}")
    L.append(f"- A2 结论：{'不变差（可以交给用户决定）' if a2['pass'] else '没通过'}")
    L += ["", "## A 另报", *[f"- {m}：{v}" for m, v in res["A_report"].items()]]
    L += ["", "## 第二关"]
    L += [f"- {c}：{v.get('verdict')}" for c, v in res["stage2"].items()] or ["- 没有第一关的幸存者，不做。"]
    L += ["", "## 只描述（不参与判定；由这些描述引出的新规则只能用前向数据检验）"]
    for k, v in res["desc"].items():
        L.append(f"- {k}：{json.dumps(v, ensure_ascii=False, default=str)}")
    L += ["", "## MDE（事先估的检验力）", *[f"- {c}：{v}" for c, v in res["mde"].items()]]
    L += ["", f"接线核对 2：{'通过' if res['align']['ok'] else '没通过（C3 作废）'}；日线指纹 {res['fingerprint']}；耗时 {res['seconds']:.0f}s。", "", "非投资建议。"]
    out_path("md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_json(res: dict) -> None:
    """结果的 JSON（只有汇总；不写逐笔价格）。"""
    out_path("json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")

# ───────────────────────── 入口 ─────────────────────────
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    modes = [m for m in ("--fetch", "--check", "--smoke", "--run") if m in argv]
    if len(modes) != 1:
        print("用法：python scripts/minute_study.py --fetch | --check | --smoke | --run", file=sys.stderr)
        return 2
    mode = modes[0][2:]
    set_mode(mode)
    if mode == "fetch":
        return do_fetch()
    if mode == "check":
        return do_check()
    if mode == "smoke":
        return do_smoke()
    return do_run()


if __name__ == "__main__":
    sys.exit(main())
