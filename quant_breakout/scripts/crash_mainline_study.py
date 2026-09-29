"""crash_mainline_study.py — 大盘与多数个股一起「脱线」大跌时，跌到什么程度入场最好；暂时大跌后的反弹、暂时顶开始跌时，个股与「时代主线」的关联
（2026-09-29 事先登记：规则先提交再运行一次，结果出来不改规则）。

用户（2026-09-28）：「上述结合接下来的研究结果进行判定 / 时间主线从一年改为3个月一判定，时间主线要标记当前各行业影响占比，
  大盘和个股都在跌的时候 做一个大盘和大部分个股同时脱线跌到什么程度入场最好的研究，然后在暂时大跌后当前反弹个股和时间主线个股关联的反弹力度的研究，
  涨到暂时顶开始跌的时候当前个股和时代主线个股的关联程度」。
「上述」= 上一轮专门的超跌反弹（rebound_study 77539c6 / 结果 4eedd8d）留给你决定的 A 到此为止 / B 另做「暴跌反弹」/ C 只做前向记录
  → 这一轮第四节把「一、二的结果 → A / B / C」事先写定。「时代主线改成 3 个月判定、标记各行业影响占比」是日报与前向记录的改动（另一个提交），
  这里的「时代主线」用同一个规则：某个日子之前最后一个完整的日历季度里，業種等权相对收益之和的前 7 名。
来由：rebound_study 的事后诊断 —— 深跌的逐笔收益 87〜93% 来自 2020 年的暴跌反弹（2008 年接刀每笔 −3.05%、2009 年 +20.91%），
  现有风险层在暴跌时本来就不开新仓 → 这一轮直接问「大盘一起跌到多深才值得进」「反弹时谁更强」「见顶时谁跌得多」。
以前做过的（不重复）：dip_study（a2c6fcd）日経225 指数 RSI(2) 回调买；madev_event（180d597）个股自己的周 / 月线脱线之后的超额；
  rebound_study（77539c6）个股深跌 + 反弹卖法 + 分开的资金；breadth A50（79887d4）宽度用来减仓。这一轮是「指数 × 多数个股」一起的深度、与主线的关联。

一 数据
  日経225 指数：yfinance 1965-01〜2026-09（bullbear_study.load）。
  日本个股（「多数个股」的比例与主线）：Z = 2001-01〜2006-09 日経225（今天的成分，yfinance）；E = 2006-10〜2016-12 日経225（同）；
    J = 2017-01〜2026-09 日経225（J-Quants）；J2 = 同期时点 TOPIX 1000（J-Quants，只算那天是成员的票，无幸存者偏差）；
    W = 另一批股票 668 只 2006-10〜2016-12（yfinance，今天的名单）。業種 = var/industry_s33.json（今天的東証 33 業種），
    其余用 J-Quants 月末上市一览里最近一次的（写法 NFKC 统一）。
  美国（独立市场）：Ken French 日收益 —— 市场 = Mkt-RF + RF（CRSP 全部股票市值加权、含已退市）1926-07〜2026-08；49 行业市值加权；
    S&P 500 今天的成分 500 只 1991〜2026（yfinance 35 年，只用来算「多数个股脱线」的比例；幸存者偏差照实写）。
  波动折算（只看价格波动定，没看任何之后的涨跌）：美国的门槛 = 日本门槛 × k；指数 k = 美国市场日对数收益标准差 ÷ 日経225（1965〜2026）；
    个股 k = S&P 500 成分日波动中位 ÷ 日経225 成分日波动中位（2001〜2026 / 1991〜2026）。
二 线与「脱线」（只用已完成的周线）
  13 周线 = 最近一根已完成周线（ISO 周、这一周最后一个交易日收盘完成；qbreak/mtf.bars）的 13 根周收盘平均；乖离 = 每天收盘 ÷ 13 周线 − 1。
  个股「脱线」= 13 周线乖离 ≤ −15%（你的周线规则 N4 的门槛）；「多数个股」的比例 = 那天是成员、乖离有值的票里脱线的比例（有值 < 50 只 → 不算）。
一 入场深度（S1）
  格子：日経225 13 周线乖离 ≤ d（d = −6 / −9 / −12 / −15 / −20%）× 脱线个股比例 ≥ b（b = 不要求 / 20 / 35 / 50%）= 20 个。
  事件：条件第一次成立的那天（同一段只算第一次；指数回到 13 周线之上（乖离 ≥ 0）才算新的一段）；那天收盘才知道 → 下一个交易日收盘买。
  结果：之后 20 / 60 / 120 个交易日的日経225 涨跌（主 = 60）；超额 = 减同一时期（2001〜06 / 2006〜16 / 2017〜26）全部交易日同样持有期的平均；
    买后还跌 = 60 个交易日内最低收盘 ÷ 买入价 − 1。个股比例用同一时期的日経225 成分（Z / E / J）。
  最好的深度：日本 2001〜2026 里段数 ≥ 8 的格子中，60 日超额平均的 95% 下限（每段一个单位的自助法 2,000 次，种子 20260929）最大的一个
    （同分取浅的 d、再取 b 低的）。
  通过 = 下限 > 0；三个时期里段数 ≥ 2 的各自平均 > 0；独立数据 —— 日経225 1965〜2000（只有指数，用这个格子的 d、不看个股比例）与
    美国市场 1926〜2026（d × k）—— 合并的平均 95% 下限 > 0 且各自平均 > 0；b 不是「不要求」时，另要美国 1991〜2026（d × k、S&P 500 成分比例
    （−15% × 个股 k）≥ b）平均 > 0。
  另报（只描述，不挑选）：2017〜2026 用时点 TOPIX 1000 的比例；成分等权篮子的 60 日涨跌；25 日线版本（日経225 25 日线乖离 ≤ −4〜−15% ×
    25 日线 ≤ −10% 的个股比例 ≥ 不要求 / 30 / 50 / 70%）。
二 暂时大跌后的反弹与时代主线的关联（S2）
  大跌段（固定，不用一的结果）：日経225 13 周线乖离第一次 ≤ −9%（回到线之上才算新的一段）；反弹开始 = 段开始后 60 个交易日内，
    收盘第一次比段开始以来的最低收盘高 5% 的那天（没有 → 这一段不算）。
  时代主线（时点）：段开始日之前最后一个完整的日历季度里，样本内各業種（当天有值的成员 ≥ 3 只、覆盖 ≥ 70% 的日子）等权相对收益
    （日对数收益 − 当天成员等权平均）之和的前 7 名。
  关联度：段开始日之前 126 个交易日，每只票的相对收益与「主线篮子」（主线業種成员等权的相对收益，主线成员算时去掉自己）的相关系数（≥ 100 天）。
  反弹力度：反弹开始日的下一个交易日收盘买，之后 20（主）/ 60 个交易日的涨跌 − 同一批票（那天是成员、两个价都有）的平均。
  每一段：关联度与反弹力度的秩相关（≥ 30 只）；日本合并 = Z、E、W、J2 按段开始日聚类（同一段在 E 与 W 取平均），J 另报。
  通过 = 日本合并平均秩相关 > 0 且 95% 下限 > 0（按段的自助法）、为正的段 ≥ 60%，且美国 49 行业（同一规则：大跌 −9% × k、反弹 +5% × k、
    主线 = 前 10 个行业、关联度对其余行业）平均 > 0 且 95% 下限 > 0。
  另报：大跌段开始当天就买；控制 β（126 天）与跌幅（段开始日比之前 60 天最高收盘）之后的秩偏相关；12-1 个月主线的版本；主线成员 − 其余。
三 暂时顶开始跌与时代主线的关联（S3）
  暂时顶开始跌：近 20 个交易日（含当天）日経225 13 周线乖离最高 ≥ +6% 且当天收盘 ≤ 近 20 个交易日最高收盘 × 0.95 的第一天；
    之后收盘创前 60 个交易日的新高才算新的一段。主线、关联度同二（以这一天为准），下一个交易日收盘起 20（主）/ 60 个交易日的超额。
  通过（「与主线关联越高，暂时顶之后跌得越多」）= 日本合并平均秩相关 < 0 且 95% 上限 < 0、为负的段 ≥ 60%，且美国 49 行业（+6% × k、5% × k）
    平均 < 0 且 95% 上限 < 0。另报：顶部那天与主线篮子的平均相关 vs 各季度初的平均（是不是越到顶越集中在主线）。
四 判定（事先写定）
  一、二都通过 → B：另外登记「暴跌反弹」一轮（在一的深度入场、买与主线关联高的个股、给一部分资金在暴跌时例外开仓；账户检验另登记，
    模拟盘要你确认才改）；只有一个通过 → C：通过的那一部分做成前向记录（只记录、不交易）；都不通过 → A：到此为止。
  三单独：通过 → 提议另外登记卖出侧的检验（暂时顶开始跌时先减与主线关联高的持仓）；不通过 → 不做。模拟盘 / 执行器在这一轮都不变。
五 登记前看过的（只有个数与分布，没有算任何之后的涨跌；python scripts/crash_mainline_study.py --counts）
  日経225 13 周线乖离分位：2001〜2026 1% −15.7 / 5% −9.1 / 10% −6.5%；1965〜2000 1% −14.1 / 5% −8.4 / 10% −5.8%。
  脱线个股比例（13 周线 ≤ −15%）：中位 1〜2%、95 分位 11〜33%、99 分位 43〜67%；指数 ≤ −9% 的日子中位 26〜49%。
  一的段数（2001〜2026 Z / E / J；1965〜2000）：d −6% 不要求 36（9/16/11）旧 40、比例 ≥ 20 / 35 / 50% 23 / 17 / 10；d −9% 21（5/11/5）旧 26、20 / 17 / 10；
    d −12% 15 旧 15、15 / 14 / 9；d −15% 8 旧 9、都 8；d −20% 2 旧 3。美国（k = 0.803）d −6 / −9 / −12 / −15 / −20% × k：122 / 71 / 45 / 34 / 20 段；
    美国 1991〜2026 加 S&P 500 成分比例（个股 k = 0.946）：5〜20 段。
  二：大跌段 Z 5、E 11、J 5（都有反弹开始）；美国 71。三：暂时顶开始跌 Z 10、E 13、J 14；美国 142。業種覆盖 100%。
登记后、运行前的修正（2026-09-29，没看任何结果；规则不变）：核对 J-Quants 業種别指数时发现同一个業種有两种写法
  （industry_s33.json「証券、商品先物取引業」、J-Quants 上市一览「証券・商品先物取引業」）→ 时点 TOPIX 1000 里不在今天名单的证券公司被分成另一个组 →
  業種名统一成「・」（ind_name）；「现在的位置」加上个股比例的日期与「不属于主线業種、但关联最高的 5 只」（只描述）。
  第一次运行在出结果之前停掉，没有看输出。
出结果之后只改了两处（2026-09-29，判定与各表的数字不变）：「现在的位置」的公司名改用 JPX 公开名单（J-Quants 的数据不入库）；
  日経225 去掉盘中还没收盘的当日 K 线（第一次运行在 9/29 盘中，最后一根是盘中价；yfinance 的 ^N225 缺 9/28 → 最后一根完整的是 9/25）
  → 只影响最后几天的之后涨跌：各格子的平均与区间 ±0.01 pp、「现在的位置」的乖离（−0.67% 盘中 → +0.14% 9/25 收盘）；判定不变。
六 局限：日経225 与扩大池用今天的成分（Z / E / W 有幸存者偏差，J2 没有）；业种用今天的分类；大跌 / 见顶的段数少（日本约 20 / 37 段），
  同一时期的段互相不独立；调整后价、不含分红（指数）；这些样本以前做过很多别的检验；税前、不计费用。模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/crash_mainline_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unicodedata
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import mtf                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

# ───────────────────────── 事先写定的常数 ─────────────────────────
LINE_N = 13                                            # 13 周线（最近一根已完成周线的 13 根周收盘平均）
STK_DEV = -15.0                                        # 个股「脱线」= 13 周线乖离 ≤ −15%（你的周线规则 N4 的门槛）
DEPTHS = (-6.0, -9.0, -12.0, -15.0, -20.0)             # 日経225 13 周线乖离 ≤ d
BREADTHS = (0.0, 20.0, 35.0, 50.0)                     # 样本里「脱线」个股的比例 ≥ b（0 = 不要求）
HORIZONS = (20, 60, 120)
H_MAIN = 60
MIN_EP = 8
MIN_BREADTH_N = 50
ERAS = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-12-31"), "J": ("2017-01-04", "2026-09-30")}
OLD = ("1965-01-01", "2000-12-31")                     # 日経225 只有指数的年代（确认用）
US_ALL = ("1926-07-01", "2026-09-30")                  # 美国市场（Ken French，确认用）
US_BREADTH = ("1991-01-01", "2026-09-30")              # 美国 S&P 500 今天的成分（多数个股的比例，确认用）
D25 = (-4.0, -6.0, -8.0, -10.0, -12.0, -15.0)          # 另报：25 日线
B25 = (0.0, 30.0, 50.0, 70.0)
STK_DEV25 = -10.0
CRASH_D = -9.0                                         # 二：大跌段 = 日経225 13 周线乖离第一次 ≤ −9%
REB_UP, REB_WIN = 5.0, 60                              # 反弹开始 = 段内最低收盘之上 +5%（段开始后 60 个交易日内）
TOP_HOT, TOP_PULL, TOP_LOOK, TOP_RESET = 6.0, 5.0, 20, 60   # 三：暂时顶开始跌
ML_TOP = {"JP": 7, "US": 10}
MIN_GROUP = 3
Q_COVER = 0.7
CORR_WIN, CORR_MIN = 126, 100
H_XS = (20, 60)
H_XS_MAIN = 20
MIN_XS = 30
POS_SHARE = 60.0
BOOT_N, SEED = 2000, 20260929
POOL = ("Z", "E", "W", "J2")                           # 日本合并（J 在 J2 的年代里，另报）
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def nfkc(s) -> str:
    return unicodedata.normalize("NFKC", str(s)) if s is not None and str(s) not in ("", "nan", "None") else ""


def ind_name(s) -> str:
    """業種名统一写法：NFKC，且「、」→「・」（industry_s33.json 写「証券、商品先物取引業」、J-Quants 写「証券・商品先物取引業」）。"""
    return nfkc(s).replace("、", "・")


# ───────────────────────── 线、乖离、多数个股的比例（纯函数，有测试）─────────────────────────
def weekly_line(close: pd.Series, days=None, n: int = LINE_N) -> pd.Series:
    """每天的 13 周线：完成日 ≤ 那天的最近一根周线（qbreak/mtf.bars：ISO 周、这一周最后一个交易日收盘完成）的 n 根周收盘平均；
    不够 n 根 → NaN。days = 市场日历（决定一周在哪天完成；缺省 = close 的日期）。"""
    c = close.dropna()
    cal = pd.DatetimeIndex(close.index if days is None else days)
    raw = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 0.0}, index=c.index)
    b = mtf.bars(raw, cal, "W")
    ma = b["Close"].astype(float).rolling(n, min_periods=n).mean()
    return mtf.state_on(ma.to_frame("m"), pd.DatetimeIndex(close.index))["m"]


def line_dev(close: pd.Series, days=None, n: int = LINE_N) -> pd.Series:
    """收盘 ÷ 13 周线 − 1（%）。"""
    return (close / weekly_line(close, days, n) - 1) * 100


def dev25(close: pd.Series) -> pd.Series:
    """另报：收盘 ÷ 最近 25 个交易日收盘平均 − 1（%）。"""
    c = close.dropna()
    return ((c / c.rolling(25, min_periods=25).mean() - 1) * 100).reindex(close.index)


def panel_dev(C: np.ndarray, days: pd.DatetimeIndex, kind: str = "W13") -> np.ndarray:
    """宽表（日期 × 票）的每只票：W13 = 13 周线乖离、D25 = 25 日线乖离（%）；那天没价 → NaN。"""
    out = np.full(C.shape, np.nan)
    for j in range(C.shape[1]):
        ok = np.isfinite(C[:, j]) & (C[:, j] > 0)
        if ok.sum() < 5 * LINE_N + 5:
            continue
        s = pd.Series(C[ok, j], index=days[ok])
        out[ok, j] = (line_dev(s, days) if kind == "W13" else dev25(s)).to_numpy(float)
    return out


def breadth(DEV: np.ndarray, M: np.ndarray, thr: float = STK_DEV, min_n: int = MIN_BREADTH_N) -> np.ndarray:
    """每天：成员里乖离有值的票中，乖离 ≤ thr 的比例（%）；有值的 < min_n 只 → NaN。"""
    ok = np.isfinite(DEV) & np.asarray(M, bool)
    n = ok.sum(axis=1)
    hit = (np.where(ok, DEV, np.inf) <= thr).sum(axis=1)
    return np.where(n >= min_n, hit / np.maximum(n, 1) * 100, np.nan)


def first_cross(cond: np.ndarray, rearm: np.ndarray) -> np.ndarray:
    """同一段只算第一次：cond 第一次成立的那天记一个事件；之后要等 rearm 成立（例：指数回到线之上）才算新的一段。"""
    armed, out = True, []
    for i in range(len(cond)):
        if rearm[i]:
            armed = True
        if armed and cond[i]:
            out.append(i)
            armed = False
    return np.asarray(out, int)


def depth_events(dev_idx: np.ndarray, B: np.ndarray | None, d: float, b: float) -> np.ndarray:
    """一：指数乖离 ≤ d 且（b > 0 时）脱线个股比例 ≥ b 第一次成立的那天；指数乖离回到 ≥ 0 才算新的一段。"""
    v = np.asarray(dev_idx, float)
    with np.errstate(invalid="ignore"):
        cond = v <= d
        if b > 0:
            cond = cond & (np.asarray(B, float) >= b)
        rearm = v >= 0
    return first_cross(cond, rearm)


def rebound_anchor(c: np.ndarray, e: int, up: float = REB_UP, win: int = REB_WIN) -> int | None:
    """二：大跌段开始日 e 之后 win 个交易日内，收盘第一次比 e 以来的最低收盘高 up% 的那天；没有 → None。"""
    lo = np.inf
    for k in range(e, min(len(c), e + win + 1)):
        if np.isfinite(c[k]):
            lo = min(lo, c[k])
            if k > e and c[k] >= lo * (1 + up / 100):
                return k
    return None


def top_events(c: np.ndarray, dev: np.ndarray, hot: float = TOP_HOT, pull: float = TOP_PULL, look: int = TOP_LOOK,
               reset: int = TOP_RESET) -> np.ndarray:
    """三：暂时顶开始跌 = 近 look 个交易日（含今天）13 周线乖离最高 ≥ hot 且今天收盘 ≤ 近 look 个交易日最高收盘 ×（1 − pull%）
    第一次成立的那天；之后收盘创前 reset 个交易日的新高才算新的一段。"""
    c, dev = np.asarray(c, float), np.asarray(dev, float)
    armed, out = True, []
    for i in range(len(c)):
        if not np.isfinite(c[i]):
            continue
        if not armed and i >= reset and c[i] > np.nanmax(c[i - reset:i]):
            armed = True
        lo = max(0, i - look + 1)
        hv = dev[lo:i + 1]
        if armed and np.isfinite(hv).any() and np.nanmax(hv) >= hot and c[i] <= np.nanmax(c[lo:i + 1]) * (1 - pull / 100):
            out.append(i)
            armed = False
    return np.asarray(out, int)


# ───────────────────────── 之后的涨跌 ─────────────────────────
def fwd_all(c: np.ndarray, h: int) -> np.ndarray:
    """R[i] = 第 i + 1 + h 天收盘 ÷ 第 i + 1 天收盘 − 1（%）：事件日 i 收盘才知道 → 下一个交易日收盘买，拿 h 个交易日。"""
    c = np.asarray(c, float)
    out = np.full(len(c), np.nan)
    if len(c) > h + 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            out[:len(c) - h - 1] = (c[h + 1:] / c[1:len(c) - h] - 1) * 100
    return out


def mae(c: np.ndarray, i: int, h: int) -> float:
    """买入（第 i + 1 天收盘）之后 h 个交易日里最低收盘 ÷ 买入价 − 1（%）。"""
    a, z = i + 1, i + 1 + h
    if z >= len(c) or not np.isfinite(c[a]) or c[a] <= 0:
        return np.nan
    return float((np.nanmin(c[a:z + 1]) / c[a] - 1) * 100)


# ───────────────────────── 时代主线（与日报「3 个月判定」同一规则）─────────────────────────
def last_quarter(date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """date 之前最后一个完整的日历季度（季度最后一天 < date）：(第一天, 最后一天)。"""
    p = pd.Timestamp(date).to_period("Q") - 1
    return p.start_time.normalize(), p.end_time.normalize()


def rel_returns(C: np.ndarray, M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(日对数收益 %, 相对收益 = 减当天成员等权平均)；非成员、前一天或当天没价 → NaN。"""
    C = np.asarray(C, float)
    LR = np.full(C.shape, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        LR[1:] = np.log(C[1:] / C[:-1]) * 100
    LR = np.where(np.asarray(M, bool) & np.isfinite(LR), LR, np.nan)
    with np.errstate(invalid="ignore"):
        mkt = np.nanmean(LR, axis=1)
    return LR, LR - mkt[:, None]


def group_scores(REL: np.ndarray, groups: np.ndarray, rows: np.ndarray, min_group: int = MIN_GROUP,
                 cover: float = Q_COVER) -> dict[str, float]:
    """rows 这些日子里各业种的等权相对收益之和（%）：某天有值的成员 < min_group → 那天缺；缺的天 > 1 − cover → 不算这个业种。"""
    out = {}
    R = REL[rows]
    if not len(R):
        return out
    for g in sorted({x for x in groups if x}):
        x = R[:, groups == g]
        cnt = np.isfinite(x).sum(axis=1)
        with np.errstate(invalid="ignore"):
            day = np.where(cnt >= min_group, np.nanmean(x, axis=1), np.nan)
        if np.isfinite(day).mean() >= cover:
            out[g] = float(np.nansum(day))
    return out


def top_k(scores: dict[str, float], k: int) -> list[str]:
    return [g for g, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def mainline_at(REL: np.ndarray, days: pd.DatetimeIndex, groups: np.ndarray, date, k: int,
                min_group: int = MIN_GROUP) -> tuple[list[str], dict[str, float], tuple]:
    """date 之前最后一个完整季度的业种相对收益前 k 名（= 那时的时代主线）。"""
    qa, qb = last_quarter(date)
    rows = np.flatnonzero((days >= qa) & (days <= qb))
    sc = group_scores(REL, groups, rows, min_group)
    return top_k(sc, k), sc, (qa, qb)


def assoc(REL: np.ndarray, groups: np.ndarray, ml, e: int, win: int = CORR_WIN, min_obs: int = CORR_MIN) -> np.ndarray:
    """e 之前 win 个交易日（不含 e），每只票相对收益与「主线篮子」（主线业种成员等权的相对收益，去掉这只票自己）的相关系数；
    成对有值的天 < min_obs → NaN。"""
    R = REL[max(0, e - win):e]
    inml = np.isin(groups, list(ml))
    Rm = R[:, inml]
    S, N = np.nansum(Rm, axis=1), np.isfinite(Rm).sum(axis=1)
    out = np.full(R.shape[1], np.nan)
    for j in range(R.shape[1]):
        x = R[:, j]
        fx = np.isfinite(x)
        if fx.sum() < min_obs:
            continue
        if inml[j]:
            cnt = N - fx
            y = np.where(cnt > 0, (S - np.where(fx, x, 0.0)) / np.maximum(cnt, 1), np.nan)
        else:
            y = np.where(N > 0, S / np.maximum(N, 1), np.nan)
        ok = fx & np.isfinite(y)
        if ok.sum() >= min_obs and x[ok].std() > 0 and y[ok].std() > 0:
            out[j] = float(np.corrcoef(x[ok], y[ok])[0, 1])
    return out


def xs_excess(C: np.ndarray, M: np.ndarray, a: int, h: int) -> np.ndarray:
    """a 下一个交易日收盘买、拿 h 个交易日：每只票涨跌 − 同一批票（a 那天是成员、两个价都有）的平均（%）。"""
    out = np.full(C.shape[1], np.nan)
    s, z = a + 1, a + 1 + h
    if z >= len(C):
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        r = C[z] / C[s] - 1
    ok = np.isfinite(r) & np.asarray(M[a], bool) & (C[s] > 0)
    if ok.sum():
        out[ok] = (r[ok] - r[ok].mean()) * 100
    return out


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return np.nan
    rx, ry = pd.Series(x[ok]).rank().to_numpy(), pd.Series(y[ok]).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def partial_spearman(x: np.ndarray, y: np.ndarray, Z: np.ndarray) -> float:
    """另报：控制 Z（β、跌幅）之后的秩偏相关（秩对秩回归取残差）。"""
    x, y, Z = np.asarray(x, float), np.asarray(y, float), np.asarray(Z, float).reshape(len(x), -1)
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(Z).all(axis=1)
    if ok.sum() < 10:
        return np.nan
    rk = lambda v: pd.Series(v).rank().to_numpy(float)                     # noqa: E731
    A = np.column_stack([np.ones(ok.sum())] + [rk(Z[ok, k]) for k in range(Z.shape[1])])
    rx = rk(x[ok]) - A @ np.linalg.lstsq(A, rk(x[ok]), rcond=None)[0]
    ry = rk(y[ok]) - A @ np.linalg.lstsq(A, rk(y[ok]), rcond=None)[0]
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def boot_ci(x: np.ndarray, n: int = BOOT_N, seed: int = SEED) -> tuple[float, float]:
    """平均的 95% 区间：每个值（= 一段）当一个单位，有放回抽样。"""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    v = x[rng.integers(0, len(x), (n, len(x)))].mean(axis=1)
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def summarize(x) -> dict:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0}
    lo, hi = boot_ci(x)
    return {"n": int(len(x)), "mean": float(x.mean()), "lo": lo, "hi": hi, "pos": float((x > 0).mean() * 100), "neg": float((x < 0).mean() * 100)}


# ───────────────────────── 数据 ─────────────────────────
def s33_map() -> dict[str, str]:
    """票（XXXX.T）→ 東証 33 业种（NFKC 统一写法）：var/industry_s33.json（今天的 TOPIX 1000）优先，其余用 J-Quants 月末上市一览里最近一次的。"""
    out: dict[str, str] = {}
    try:
        import allstock_data as AD
        for _, m in sorted(AD.snapshots().items()):
            for code, nm in zip(m["Code"].astype(str), m["S33Nm"].astype(str)):
                v = ind_name(nm)
                if len(code) == 5 and code.endswith("0") and v not in ("", "その他", "-"):
                    out[code[:4] + ".T"] = v
    except Exception as e:                                                    # noqa: BLE001
        print(f"J-Quants 上市一览读不到（只用 industry_s33.json）：{e}")
    doc = json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))
    for c, v in doc["s33"].items():
        out[f"{c}.T"] = ind_name(v)
    return out


def jp_panels() -> dict[str, dict]:
    """{Z, E, J, J2, W: {C（日期 × 票 收盘）, days, names, M（那天是成员且有价）, win}}。"""
    import candle_data as CD
    import leap_confirm as LF
    import sell_confirm as SCF
    import wvol_wide as WWD
    from qbreak import wide_universe as WU
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    out = {}
    n225 = list(universe("JP", "broad"))
    for tag, (lo, hi) in (("Z", LF.Z_DAYS), ("E", LF.E_DAYS)):
        P, days, nm = LF.yf_panel(n225, lo, hi)
        C = np.asarray(P["C"], float)
        out[tag] = {"C": C, "days": pd.DatetimeIndex(days), "names": list(nm), "M": np.isfinite(C), "win": ERAS[tag]}
    D = CD.load()
    for tag, mem in (("J", "U0"), ("J2", "U2")):
        cols = [j for j in range(len(D["names"])) if D["mem"][mem][:, j].any()]
        C = np.asarray(D["P"]["C"][:, cols], float)
        out[tag] = {"C": C, "days": pd.DatetimeIndex(D["days"]), "names": [str(D["names"][j]) for j in cols],
                    "M": np.asarray(D["mem"][mem][:, cols], bool) & np.isfinite(C), "win": ERAS["J"]}
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
    data = load_universe(WU.tickers(WU.load()), d21)
    P, days, nm = WWD.panel(data, *SCF.W_DATA)
    keep = [j for j in range(len(nm)) if np.isfinite(P["C"][:, j]).sum() >= 80]
    C = np.asarray(P["C"][:, keep], float)
    out["W"] = {"C": C, "days": pd.DatetimeIndex(days), "names": [nm[j] for j in keep], "M": np.isfinite(C), "win": ERAS["E"]}
    return out


def n225() -> pd.Series:
    from bullbear_study import load
    from qbreak.trader import drop_partial_bar
    return drop_partial_bar(load("^N225", OLD[0]), "JP")["Close"].astype(float)          # 盘中运行时去掉还没收盘的当日 K 线


def us_market() -> pd.Series:
    """Ken French 市场（Mkt-RF + RF = CRSP 全部股票市值加权，含已退市）日收益 → 累计指数。"""
    import core_mix_study as CMS
    f = CMS.ff_daily("ff3")
    r = (f["Mkt-RF"] + f["RF"]).dropna()
    return (1 + r).cumprod().rename("US")


def us_ind49() -> pd.DataFrame:
    """Ken French 49 行业市值加权日收益（小数；CRSP，含已退市公司；缺值 NaN）。"""
    import core_mix_study as CMS
    CMS.FF_FILES.setdefault("ind49", ("49_Industry_Portfolios_daily", "Average Value Weighted Returns -- Daily"))
    return CMS.ff_daily("ind49")


def us_sp500_panel() -> dict:
    """S&P 500 今天的成分（var/us_constituents_2026-09.json）的 yfinance 35 年日线 → {C, days, names, M}（幸存者偏差照实写）。"""
    import us_stock_data as USD
    data = USD.ohlcv(USD.names("sp500"))
    nm = sorted(t for t, df in data.items() if df is not None and len(df))
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in nm])))
    days = days[days >= pd.Timestamp(US_BREADTH[0]) - pd.Timedelta(days=200)]
    C = np.column_stack([data[t]["Close"].reindex(days).to_numpy(float) for t in nm])
    return {"C": C, "days": days, "names": nm, "M": np.isfinite(C)}


def daily_sd(C: np.ndarray, days: pd.DatetimeIndex, a: str, b: str) -> float:
    """窗口里每只票日对数收益标准差（%）的中位数。"""
    rows = (days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b))
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(C[1:] / C[:-1])[rows[1:]] * 100
    sd = np.array([np.nanstd(lr[:, j]) for j in range(lr.shape[1]) if np.isfinite(lr[:, j]).sum() >= 250])
    return float(np.median(sd)) if len(sd) else np.nan


def idx_sd(c: pd.Series, a: str, b: str) -> float:
    s = c[(c.index >= pd.Timestamp(a)) & (c.index <= pd.Timestamp(b))]
    return float(np.log(s).diff().std() * 100)


def era_of(d, eras: dict = ERAS) -> str | None:
    d = pd.Timestamp(d)
    for k, (a, b) in eras.items():
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return k
    return None


# ───────────────────────── 登记前的核对（只数个数，不算任何之后的涨跌）─────────────────────────
def counts() -> int:
    t0 = time.time()
    nk = n225()
    dv = line_dev(nk)
    q = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    for lab, (a, b) in (("1965〜2000", OLD), ("2001〜2026", ("2001-01-04", "2026-09-30"))):
        x = dv[(dv.index >= a) & (dv.index <= b)].dropna()
        print(f"日経225 13 周线乖离 {lab}：" + "、".join(f"{p}% {np.percentile(x, p):+.1f}" for p in q))
    P = jp_panels()
    s33 = s33_map()
    for tag, S in P.items():
        cov = np.mean([t in s33 for t in S["names"]]) * 100
        print(f"{tag}：{len(S['names'])} 只、{S['days'][0].date()}〜{S['days'][-1].date()}、有业种 {cov:.0f}%")
    BR = {}
    for tag in ("Z", "E", "J", "J2", "W"):
        S = P[tag]
        DEV = panel_dev(S["C"], S["days"])
        BR[tag] = pd.Series(breadth(DEV, S["M"]), index=S["days"])
        a, b = S["win"]
        x = BR[tag][(BR[tag].index >= a) & (BR[tag].index <= b)].dropna()
        dd = dv.reindex(x.index)
        print(f"{tag} 脱线个股比例（13 周线 ≤ −15%）：" + "、".join(f"{p}% {np.percentile(x, p):.0f}" for p in q)
              + f"｜指数 ≤ −9% 的日子中位 {x[dd <= -9].median():.0f}%（{int((dd <= -9).sum())} 天）")
    Bexp = pd.concat([BR[t][(BR[t].index >= ERAS[t][0]) & (BR[t].index <= ERAS[t][1])] for t in ("Z", "E", "J")]).sort_index()
    Bexp = Bexp[~Bexp.index.duplicated()]
    nd = nk.index
    Bi = Bexp.reindex(nd).to_numpy(float)
    print("一：事件段数（2001〜2026 按时期 Z / E / J；1965〜2000 只有指数）")
    for d in DEPTHS:
        row = []
        for b in BREADTHS:
            ev = depth_events(dv.to_numpy(float), Bi, d, b)
            ed = nd[ev]
            k = {e: int(sum(era_of(x) == e for x in ed)) for e in ERAS}
            old = int(((ed >= OLD[0]) & (ed <= OLD[1])).sum()) if b == 0 else None
            row.append(f"b{b:.0f}: {sum(k.values())}（{k['Z']}/{k['E']}/{k['J']}）" + (f" 旧 {old}" if old is not None else ""))
        print(f"  d {d:+.0f}%：" + "；".join(row))
    e0 = depth_events(dv.to_numpy(float), None, CRASH_D, 0)
    c = nk.to_numpy(float)
    r0 = [rebound_anchor(c, e) for e in e0]
    for k, (a, b) in ERAS.items():
        m = [(nd[e] >= pd.Timestamp(a)) and (nd[e] <= pd.Timestamp(b)) for e in e0]
        print(f"二：{k} 大跌段 {sum(m)}、其中有反弹开始 {sum(1 for mm, r in zip(m, r0) if mm and r is not None)}："
              + "、".join(str(nd[e].date()) for e, mm in zip(e0, m) if mm))
    te = top_events(c, dv.to_numpy(float))
    for k, (a, b) in ERAS.items():
        m = [nd[e] for e in te if pd.Timestamp(a) <= nd[e] <= pd.Timestamp(b)]
        print(f"三：{k} 暂时顶开始跌 {len(m)}：" + "、".join(str(x.date()) for x in m))
    um = us_market()
    k_idx = idx_sd(um, "1965-01-01", "2026-09-30") / idx_sd(nk, "1965-01-01", "2026-09-30")
    ud = line_dev(um)
    ucl = um.to_numpy(float)
    print(f"美国：市场 {um.index[0].date()}〜{um.index[-1].date()}；指数波动比 k = {k_idx:.3f}")
    for d in DEPTHS:
        ev = depth_events(ud.to_numpy(float), None, d * k_idx, 0)
        print(f"  d {d:+.0f}% × k = {d * k_idx:+.1f}%：{len(ev)} 段")
    ue0 = depth_events(ud.to_numpy(float), None, CRASH_D * k_idx, 0)
    ur0 = [rebound_anchor(ucl, e, REB_UP * k_idx) for e in ue0]
    ute = top_events(ucl, ud.to_numpy(float), TOP_HOT * k_idx, TOP_PULL * k_idx)
    print(f"  二：大跌段 {len(ue0)}（有反弹开始 {sum(r is not None for r in ur0)}）；三：暂时顶开始跌 {len(ute)}")
    ind = us_ind49()
    print(f"  49 行业：{ind.index[0].date()}〜{ind.index[-1].date()}，有值的行业数 中位 {int(np.median(ind.notna().sum(axis=1)))}")
    SP = us_sp500_panel()
    jp_sd = np.median([daily_sd(P[t]["C"], P[t]["days"], *ERAS[t]) for t in ("Z", "E", "J")])
    k_stk = daily_sd(SP["C"], SP["days"], *US_BREADTH) / jp_sd
    DEVu = panel_dev(SP["C"], SP["days"])
    Bu = pd.Series(breadth(DEVu, SP["M"], STK_DEV * k_stk), index=SP["days"])
    xu = Bu[Bu.index >= US_BREADTH[0]].dropna()
    print(f"  S&P 500 今天的成分 {len(SP['names'])} 只；个股波动比 k = {k_stk:.3f}；脱线比例（≤ −15% × k）："
          + "、".join(f"{p}% {np.percentile(xu, p):.0f}" for p in q))
    Bui = Bu.reindex(um.index).to_numpy(float)
    for d in DEPTHS:
        row = []
        for b in BREADTHS[1:]:
            ev = depth_events(np.where(um.index >= pd.Timestamp(US_BREADTH[0]), ud.to_numpy(float), np.nan), Bui, d * k_idx, b)
            row.append(f"b{b:.0f}: {len(ev)}")
        print(f"  1991〜2026 d {d:+.0f}% × k：" + "；".join(row))
    print(f"（{round(time.time() - t0)} s；只有个数与分布，没有算任何之后的涨跌）")
    return 0



# ───────────────────────── 判定（纯函数，有测试）─────────────────────────
def pick_best(cells: dict, min_ep: int = MIN_EP):
    """一：段数 ≥ min_ep 的格子里，60 日超额平均的 95% 下限最大的一个；同分取浅的（d 大）、再取个股比例要求低的。"""
    ok = [k for k, v in cells.items() if v.get("n", 0) >= min_ep and np.isfinite(v.get("lo", np.nan))]
    return max(ok, key=lambda k: (cells[k]["lo"], k[0], -k[1])) if ok else None


def s1_verdict(best: dict | None, eras: dict, conf: dict, old: dict, us: dict, us_b: dict | None) -> dict:
    """一的通过：日本 2001〜2026 下限 > 0；各时期（≥ 2 段）平均 > 0；独立数据（日経225 1965〜2000 + 美国）合并下限 > 0 且各自平均 > 0；
    个股比例有要求时，美国 1991〜2026（S&P 500 成分的比例）平均 > 0。"""
    f = []
    if not best or best.get("n", 0) < MIN_EP:
        f.append("没有 ≥ 8 段的格子")
    else:
        if not best["lo"] > 0:
            f.append("日本 2001〜2026 的 95% 下限 ≤ 0")
        f += [f"{k} 时期平均 ≤ 0" for k, v in eras.items() if v.get("n", 0) >= 2 and not v["mean"] > 0]
        if not (conf.get("n", 0) >= 2 and conf["lo"] > 0):
            f.append("独立数据合并的 95% 下限 ≤ 0")
        if not (old.get("n", 0) and old["mean"] > 0):
            f.append("日経225 1965〜2000 平均 ≤ 0")
        if not (us.get("n", 0) and us["mean"] > 0):
            f.append("美国平均 ≤ 0")
        if us_b is not None and not (us_b.get("n", 0) and us_b["mean"] > 0):
            f.append("美国（加个股比例）平均 ≤ 0")
    return {"pass": not f, "fails": f}


def s2_verdict(jp: dict, us: dict) -> dict:
    """二的通过（主线关联越高、反弹越强）：日本合并平均秩相关 > 0 且 95% 下限 > 0、为正的段 ≥ 60%；美国 49 行业平均 > 0 且下限 > 0。"""
    f = []
    if not (jp.get("n", 0) >= 2 and jp["mean"] > 0 and jp["lo"] > 0):
        f.append("日本合并的平均秩相关或 95% 下限 ≤ 0")
    if not jp.get("pos", 0) >= POS_SHARE:
        f.append("日本秩相关为正的段 < 60%")
    if not (us.get("n", 0) >= 2 and us["mean"] > 0 and us["lo"] > 0):
        f.append("美国 49 行业的平均或 95% 下限 ≤ 0")
    return {"pass": not f, "fails": f}


def s3_verdict(jp: dict, us: dict) -> dict:
    """三的通过（主线关联越高、暂时顶之后跌得越多）：日本合并平均秩相关 < 0 且 95% 上限 < 0、为负的段 ≥ 60%；美国平均 < 0 且上限 < 0。"""
    f = []
    if not (jp.get("n", 0) >= 2 and jp["mean"] < 0 and jp["hi"] < 0):
        f.append("日本合并的平均秩相关或 95% 上限 ≥ 0")
    if not jp.get("neg", 0) >= POS_SHARE:
        f.append("日本秩相关为负的段 < 60%")
    if not (us.get("n", 0) >= 2 and us["mean"] < 0 and us["hi"] < 0):
        f.append("美国 49 行业的平均或 95% 上限 ≥ 0")
    return {"pass": not f, "fails": f}


def decide(s1: bool, s2: bool) -> str:
    """上一轮留下的 A / B / C：一、二都通过 → B；只有一个通过 → C；都不通过 → A。"""
    return "B" if (s1 and s2) else ("C" if (s1 or s2) else "A")


# ───────────────────────── 一：入场深度 ─────────────────────────
def uncond(R: dict, dates: pd.DatetimeIndex, eras: dict) -> dict:
    """各时期全部交易日同样持有期的平均（%）：超额的基准。"""
    out = {}
    for k, (a, b) in eras.items():
        m = (dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(b))
        out[k] = {h: float(np.nanmean(R[h][m])) for h in R}
    return out


def event_table(ev: np.ndarray, dates: pd.DatetimeIndex, c: np.ndarray, R: dict, eras: dict, U: dict) -> pd.DataFrame:
    rows = []
    for i in ev:
        e = era_of(dates[i], eras)
        if e is None:
            continue
        row = {"date": dates[i], "era": e, "mae": mae(c, i, H_MAIN)}
        for h in R:
            row[f"r{h}"] = R[h][i]
            row[f"x{h}"] = R[h][i] - U[e][h]
        rows.append(row)
    cols = ["date", "era", "mae"] + [f"{p}{h}" for h in R for p in ("r", "x")]
    return pd.DataFrame(rows, columns=cols)


def cell_stats(T: pd.DataFrame, eras) -> dict:
    x = T[f"x{H_MAIN}"].to_numpy(float) if len(T) else np.array([])
    st = summarize(x)
    if not st.get("n"):
        return {"n": 0, "eras": {}}
    f = np.isfinite(x)
    r = T[f"r{H_MAIN}"].to_numpy(float)[f]
    st.update({"win": float((r > 0).mean() * 100), "r20": float(np.nanmean(T["r20"])), "r60": float(np.nanmean(r)),
               "r120": float(np.nanmean(T["r120"])), "mae": float(np.nanmean(T["mae"].to_numpy(float)[f])),
               "dates": [str(pd.Timestamp(d).date()) for d in T["date"][f]]})
    st["eras"] = {}
    for k in eras:
        xe = T.loc[(T["era"] == k).to_numpy() & f, f"x{H_MAIN}"].to_numpy(float)
        st["eras"][k] = {"n": int(len(xe)), "mean": float(xe.mean()) if len(xe) else np.nan}
    return st


def basket_fwd(S: dict, date, h: int = H_MAIN) -> float:
    """另报：样本成分等权（那天的成员）从 date 下一个交易日收盘拿 h 天的平均涨跌（%）。"""
    days = S["days"]
    a = int(days.searchsorted(pd.Timestamp(date)))
    if a >= len(days) or days[a] != pd.Timestamp(date) or a + 1 + h >= len(days):
        return np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        r = S["C"][a + 1 + h] / S["C"][a + 1] - 1
    ok = np.isfinite(r) & S["M"][a]
    return float(r[ok].mean() * 100) if ok.sum() >= MIN_BREADTH_N else np.nan


def run_s1(nk: pd.Series, dv: pd.Series, Bexp: pd.Series, Bj2: pd.Series, P: dict, um: pd.Series, ud: pd.Series,
           Bus: pd.Series, k_idx: float) -> dict:
    c, dates = nk.to_numpy(float), nk.index
    R = {h: fwd_all(c, h) for h in HORIZONS}
    U = uncond(R, dates, ERAS)
    Bi = Bexp.reindex(dates).to_numpy(float)
    cells, tabs = {}, {}
    for d in DEPTHS:
        for b in BREADTHS:
            T = event_table(depth_events(dv.to_numpy(float), Bi, d, b), dates, c, R, ERAS, U)
            tabs[(d, b)], cells[(d, b)] = T, cell_stats(T, ERAS)
    best = pick_best(cells)
    out = {"cells": {f"{d:+.0f}|{b:.0f}": v for (d, b), v in cells.items()}, "best": list(best) if best else None,
           "uncond": {k: {str(h): v for h, v in u.items()} for k, u in U.items()}}
    say("\n## 一、大盘与多数个股一起脱线：跌到什么程度入场（日経225 13 周线乖离 × 13 周线 ≤ −15% 的个股比例；下一个交易日收盘买）")
    say(f"超额 = 之后 {H_MAIN} 个交易日的日経225 涨跌 − 同一时期全部交易日同样持有期的平均"
        f"（2001〜06 {U['Z'][H_MAIN]:+.2f}% / 2006〜16 {U['E'][H_MAIN]:+.2f}% / 2017〜26 {U['J'][H_MAIN]:+.2f}%）。按段的自助法 95% 区间。")
    say("\n| 指数乖离 ≤ | 个股比例 ≥ | 段数（Z / E / J） | 60 日涨跌 | 60 日超额（95% 区间） | 涨的比例 | 买后还跌（60 日内最低） | 20 / 120 日涨跌 |")
    say("|---|---|---|---|---|---|---|---|")
    for (d, b), v in cells.items():
        if not v.get("n"):
            say(f"| {d:+.0f}% | {'—' if b == 0 else f'{b:.0f}%'} | 0 | — | — | — | — | — |")
            continue
        e = v["eras"]
        mark = " **←**" if best == (d, b) else ""
        say(f"| {d:+.0f}% | {'不要求' if b == 0 else f'{b:.0f}%'} | {v['n']}（{e['Z']['n']} / {e['E']['n']} / {e['J']['n']}） | {v['r60']:+.2f}% | "
            f"{v['mean']:+.2f}%（{v['lo']:+.2f}〜{v['hi']:+.2f}）{mark} | {v['win']:.0f}% | {v['mae']:+.2f}% | {v['r20']:+.2f}% / {v['r120']:+.2f}% |")
    if best is None:
        say("\n**没有 ≥ 8 段的格子** → 一不通过。")
        out["verdict"] = s1_verdict(None, {}, {}, {}, {}, None)
        return out
    d, b = best
    bv = cells[best]
    # 独立数据：日経225 1965〜2000（只有指数）、美国市场 1926〜2026（门槛 × k）、美国 1991〜2026 加 S&P 500 成分的比例
    Uo = uncond(R, dates, {"OLD": OLD})
    old_T = event_table(depth_events(dv.to_numpy(float), None, d, 0), dates, c, R, {"OLD": OLD}, Uo)
    cu, du = um.to_numpy(float), um.index
    Ru = {h: fwd_all(cu, h) for h in HORIZONS}
    Uu = uncond(Ru, du, {"US": US_ALL, "USB": US_BREADTH})
    us_T = event_table(depth_events(ud.to_numpy(float), None, d * k_idx, 0), du, cu, Ru, {"US": US_ALL}, Uu)
    old_s, us_s = cell_stats(old_T, {"OLD": OLD}), cell_stats(us_T, {"US": US_ALL})
    conf = summarize(np.r_[old_T[f"x{H_MAIN}"].to_numpy(float), us_T[f"x{H_MAIN}"].to_numpy(float)])
    usb_s = None
    if b > 0:
        udv = np.where(du >= pd.Timestamp(US_BREADTH[0]), ud.to_numpy(float), np.nan)
        usb_T = event_table(depth_events(udv, Bus.reindex(du).to_numpy(float), d * k_idx, b), du, cu, Ru, {"USB": US_BREADTH}, Uu)
        usb_s = cell_stats(usb_T, {"USB": US_BREADTH})
    v = s1_verdict(bv, bv["eras"], conf, old_s, us_s, usb_s)
    # 另报：2017〜2026 用时点 TOPIX 1000 的比例；成分等权的篮子；25 日线
    j2_T = event_table(depth_events(dv.to_numpy(float), Bj2.reindex(dates).to_numpy(float), d, b), dates, c, R, {"J": ERAS["J"]}, U)
    j2_s = cell_stats(j2_T, {"J": ERAS["J"]})
    bask = [basket_fwd(P[era_of(dd)], dd) for dd in tabs[best]["date"]]
    out.update({"best_stats": bv, "old": old_s, "us": us_s, "conf": conf, "us_breadth": usb_s, "j2": j2_s, "verdict": v,
                "basket60": summarize(bask), "k_idx": k_idx})
    say(f"\n**最好的深度（按规则）：指数乖离 ≤ {d:+.0f}%、个股比例 {'不要求' if b == 0 else f'≥ {b:.0f}%'}** —— {bv['n']} 段，"
        f"60 日超额 {bv['mean']:+.2f}%（{bv['lo']:+.2f}〜{bv['hi']:+.2f}），涨的比例 {bv['win']:.0f}%，买后 60 日内平均还跌 {bv['mae']:+.2f}%；"
        f"成分等权篮子 60 日平均 {out['basket60'].get('mean', np.nan):+.2f}%。")
    say("- 各时期：" + "；".join(f"{k} {x['n']} 段 {x['mean']:+.2f}%" for k, x in bv["eras"].items() if x["n"]))
    say(f"- 独立数据：日経225 1965〜2000（只有指数）{old_s.get('n', 0)} 段 {old_s.get('mean', np.nan):+.2f}%；"
        f"美国市场 1926〜2026（门槛 × {k_idx:.2f} = {d * k_idx:+.1f}%）{us_s.get('n', 0)} 段 {us_s.get('mean', np.nan):+.2f}%；"
        f"合并 {conf.get('n', 0)} 段 {conf.get('mean', np.nan):+.2f}%（{conf.get('lo', np.nan):+.2f}〜{conf.get('hi', np.nan):+.2f}）"
        + (f"；美国 1991〜2026 加 S&P 500 成分比例 {usb_s.get('n', 0)} 段 {usb_s.get('mean', np.nan):+.2f}%" if usb_s is not None else ""))
    say(f"- 另报：2017〜2026 用时点 TOPIX 1000 的比例 {j2_s.get('n', 0)} 段 {j2_s.get('mean', np.nan):+.2f}%。")
    say(f"- **一：{'通过' if v['pass'] else '不通过'}**" + ("" if v["pass"] else "（" + "；".join(v["fails"]) + "）"))
    return out


def run_d25(nk: pd.Series, P: dict) -> dict:
    """另报（只描述，不挑选）：25 日线版本 —— 日経225 25 日线乖离 × 25 日线 ≤ −10% 的个股比例。"""
    c, dates = nk.to_numpy(float), nk.index
    R = {h: fwd_all(c, h) for h in HORIZONS}
    U = uncond(R, dates, ERAS)
    d25 = dev25(nk).to_numpy(float)
    parts = []
    for t in ("Z", "E", "J"):
        S = P[t]
        s = pd.Series(breadth(panel_dev(S["C"], S["days"], "D25"), S["M"], STK_DEV25), index=S["days"])
        parts.append(s[(s.index >= ERAS[t][0]) & (s.index <= ERAS[t][1])])
    B = pd.concat(parts).sort_index()
    B = B[~B.index.duplicated()].reindex(dates).to_numpy(float)
    out = {}
    say("\n另报（只描述，不挑选）：25 日线版本（日経225 25 日线乖离 × 25 日线 ≤ −10% 的个股比例），段数 / 60 日超额 / 涨的比例 / 买后还跌")
    say("| 指数乖离 ≤ | " + " | ".join("不要求" if b == 0 else f"比例 ≥ {b:.0f}%" for b in B25) + " |")
    say("|---|" + "---|" * len(B25))
    for d in D25:
        cells = []
        for b in B25:
            st = cell_stats(event_table(depth_events(d25, B, d, b), dates, c, R, ERAS, U), ERAS)
            out[f"{d:+.0f}|{b:.0f}"] = st
            cells.append("—" if not st.get("n") else f"{st['n']} / {st['mean']:+.2f}% / {st['win']:.0f}% / {st['mae']:+.1f}%")
        say(f"| {d:+.0f}% | " + " | ".join(cells) + " |")
    return out


# ───────────────────────── 二、三：与时代主线的关联 ─────────────────────────
def beta_dd(LR: np.ndarray, C: np.ndarray, e: int, win: int = CORR_WIN) -> tuple[np.ndarray, np.ndarray]:
    """另报的控制：e 之前 win 天对等权平均的 β；e 那天收盘比之前 60 个交易日最高收盘的跌幅（%）。"""
    R = LR[max(0, e - win):e]
    with np.errstate(invalid="ignore"):
        m = np.nanmean(R, axis=1)
    beta = np.full(R.shape[1], np.nan)
    for j in range(R.shape[1]):
        ok = np.isfinite(R[:, j]) & np.isfinite(m)
        if ok.sum() >= CORR_MIN and m[ok].var() > 0:
            beta[j] = np.cov(R[ok, j], m[ok])[0, 1] / m[ok].var(ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        dd = (C[e] / np.nanmax(C[max(0, e - 60):e + 1], axis=0) - 1) * 100
    return beta, dd


def xs_episodes(S: dict, groups: np.ndarray, LR: np.ndarray, REL: np.ndarray, anchors: list, k: int, min_group: int = MIN_GROUP) -> list[dict]:
    """每一段：主线（段开始日之前最后一个完整季度的前 k 名）、关联度（段开始日之前 126 天）、从锚点日下一个交易日收盘起 20 / 60 天的超额；
    秩相关、主线成员 − 其余、控制 β 与跌幅后的秩偏相关；另报 12-1 个月主线的秩相关。anchors = [(段开始日, 锚点日)]。"""
    days, C, M = S["days"], S["C"], S["M"]
    known = groups != ""
    out = []
    for d0, da in anchors:
        e, a = int(days.searchsorted(pd.Timestamp(d0))), int(days.searchsorted(pd.Timestamp(da)))
        if e >= len(days) or a >= len(days) or e < CORR_WIN:
            continue
        ml, _, (qa, _) = mainline_at(REL, days, groups, days[e], k, min_group)
        if len(ml) < k:
            continue
        corr = assoc(REL, groups, ml, e)
        inml = np.isin(groups, ml)
        beta, dd = beta_dd(LR, C, e)
        sc12 = group_scores(REL, groups, np.arange(max(0, e - 252), max(0, e - 21)), min_group)
        ml12 = top_k(sc12, k)
        corr12 = assoc(REL, groups, ml12, e) if len(ml12) == k else np.full(len(groups), np.nan)
        row = {"d0": str(pd.Timestamp(d0).date()), "da": str(pd.Timestamp(da).date()), "ml": ml, "q": f"{qa.year}Q{(qa.month - 1) // 3 + 1}",
               "corr_mean": float(np.nanmean(corr)) if np.isfinite(corr).any() else np.nan}
        for h in H_XS:
            ex = xs_excess(C, M, a, h)
            ok = np.isfinite(corr) & np.isfinite(ex)
            fx = np.isfinite(ex)
            row[f"n{h}"] = int(ok.sum())
            row[f"rho{h}"] = spearman(corr, ex) if ok.sum() >= MIN_XS else np.nan
            row[f"prho{h}"] = partial_spearman(corr, ex, np.column_stack([beta, dd])) if ok.sum() >= MIN_XS else np.nan
            row[f"rho12_{h}"] = spearman(corr12, ex) if (np.isfinite(corr12) & fx).sum() >= MIN_XS else np.nan
            a1, a0 = ex[inml & fx], ex[~inml & known & fx]
            row[f"diff{h}"] = float(a1.mean() - a0.mean()) if len(a1) and len(a0) else np.nan
        out.append(row)
    return out


def pool(rows_by_tag: dict[str, list[dict]], tags, key: str) -> tuple[np.ndarray, list[str]]:
    """按段开始日聚类（同一段在几个样本里 → 取平均）→ 每段一个值。"""
    acc: dict[str, list[float]] = {}
    for t in tags:
        for r in rows_by_tag.get(t, []):
            v = r.get(key)
            if v is not None and np.isfinite(v):
                acc.setdefault(r["d0"], []).append(float(v))
    ks = sorted(acc)
    return np.array([np.mean(acc[k]) for k in ks]), ks


def jp_anchor_lists(nk: pd.Series, dv: pd.Series) -> dict:
    c, dates = nk.to_numpy(float), nk.index
    e0 = depth_events(dv.to_numpy(float), None, CRASH_D, 0)
    crash = []
    for e in e0:
        r = rebound_anchor(c, e)
        crash.append((dates[e], dates[r] if r is not None else None))
    tops = [dates[i] for i in top_events(c, dv.to_numpy(float))]
    return {"crash": crash, "tops": tops}


def in_win(d, win) -> bool:
    return pd.Timestamp(win[0]) <= pd.Timestamp(d) <= pd.Timestamp(win[1])


def run_xs(P: dict, s33: dict, nk: pd.Series, dv: pd.Series, um: pd.Series, ud: pd.Series, ind: pd.DataFrame, k_idx: float) -> dict:
    A = jp_anchor_lists(nk, dv)
    res = {"JP": {}, "US": {}}
    for tag, S in P.items():
        groups = np.array([s33.get(t, "") for t in S["names"]], dtype=object)
        LR, REL = rel_returns(S["C"], S["M"])
        win = S["win"]
        reb = [(d0, dr) for d0, dr in A["crash"] if dr is not None and in_win(d0, win)]
        cr0 = [(d0, d0) for d0, _ in A["crash"] if in_win(d0, win)]
        tp = [(d0, d0) for d0 in A["tops"] if in_win(d0, win)]
        res["JP"][tag] = {"rebound": xs_episodes(S, groups, LR, REL, reb, ML_TOP["JP"]),
                          "crash_day": xs_episodes(S, groups, LR, REL, cr0, ML_TOP["JP"]),
                          "top": xs_episodes(S, groups, LR, REL, tp, ML_TOP["JP"])}
        qe = [d for d in pd.date_range(win[0], win[1], freq="QE")]
        base = xs_episodes(S, groups, LR, REL, [(d + pd.Timedelta(days=1), d + pd.Timedelta(days=1)) for d in qe], ML_TOP["JP"])
        res["JP"][tag]["base_corr"] = float(np.nanmean([r["corr_mean"] for r in base])) if base else np.nan
        print(f"  {tag}：反弹 {len(res['JP'][tag]['rebound'])} 段、大跌当天 {len(res['JP'][tag]['crash_day'])} 段、暂时顶 {len(res['JP'][tag]['top'])} 段", flush=True)
    # 美国 49 行业（每个行业自己一组；主线 = 前 10 名；门槛 × k）
    r = ind.copy()
    first = r.apply(lambda s: s.first_valid_index())
    Cu = (1 + r.fillna(0.0)).cumprod()
    for col in Cu.columns:
        if first[col] is not None:
            Cu.loc[Cu.index < first[col], col] = np.nan
    Cu = Cu.reindex(um.index)
    Su = {"C": Cu.to_numpy(float), "days": pd.DatetimeIndex(Cu.index), "M": np.isfinite(Cu.to_numpy(float)), "names": list(Cu.columns)}
    gu = np.array(Su["names"], dtype=object)
    LRu, RELu = rel_returns(Su["C"], Su["M"])
    cu = um.to_numpy(float)
    e0 = depth_events(ud.to_numpy(float), None, CRASH_D * k_idx, 0)
    reb = []
    for e in e0:
        rr = rebound_anchor(cu, e, REB_UP * k_idx)
        if rr is not None:
            reb.append((um.index[e], um.index[rr]))
    tps = [(um.index[i], um.index[i]) for i in top_events(cu, ud.to_numpy(float), TOP_HOT * k_idx, TOP_PULL * k_idx)]
    res["US"] = {"rebound": xs_episodes(Su, gu, LRu, RELu, reb, ML_TOP["US"], 1),
                 "crash_day": xs_episodes(Su, gu, LRu, RELu, [(d, d) for d, _ in reb], ML_TOP["US"], 1),
                 "top": xs_episodes(Su, gu, LRu, RELu, tps, ML_TOP["US"], 1)}
    print(f"  美国 49 行业：反弹 {len(res['US']['rebound'])} 段、暂时顶 {len(res['US']['top'])} 段", flush=True)
    return res


def fmt(x, f="{:+.3f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def report_xs(res: dict) -> dict:
    out = {}
    h = H_XS_MAIN
    for part, title, key in (("rebound", "二、暂时大跌后的反弹：与时代主线关联越高，反弹越强吗", "rho"),
                             ("top", "三、涨到暂时顶开始跌：与时代主线关联越高，之后跌得越多吗", "rho")):
        rows = {t: res["JP"][t][part] for t in res["JP"]}
        jp_v, jp_k = pool(rows, POOL, f"{key}{h}")
        us_v = np.array([r[f"{key}{h}"] for r in res["US"][part] if np.isfinite(r[f"{key}{h}"])])
        jp_s, us_s = summarize(jp_v), summarize(us_v)
        v = s2_verdict(jp_s, us_s) if part == "rebound" else s3_verdict(jp_s, us_s)
        say(f"\n## {title}")
        if part == "rebound":
            say(f"大跌段 = 日経225 13 周线乖离第一次 ≤ {CRASH_D:+.0f}%（回到线之上才算新的一段）；反弹开始 = 段内最低收盘之上 +{REB_UP:.0f}% 的那天（60 个交易日内）；"
                f"那天的下一个交易日收盘买，看之后 {h} 个交易日的超额（减同一批票的平均）。")
        else:
            say(f"暂时顶开始跌 = 近 {TOP_LOOK} 个交易日指数 13 周线乖离最高 ≥ +{TOP_HOT:.0f}% 且收盘比近 {TOP_LOOK} 天最高收盘低 ≥ {TOP_PULL:.0f}% 的第一天"
                f"（之后创 60 日新高才算新的一段）；下一个交易日收盘起 {h} 个交易日的超额。")
        say("主线 = 段开始之前最后一个完整季度相对收益前 7 的業種（美国前 10 个行业）；关联度 = 段开始之前 126 天与主线篮子（去掉自己）的相关。"
            "秩相关 > 0 = 关联越高、超额越高。")
        say("\n| 样本 | 段数 | 平均秩相关（主，20 日） | 60 日 | 控制 β 与跌幅后 | 12-1 个月主线 | 主线成员 − 其余（20 日） |")
        say("|---|---|---|---|---|---|---|")
        for t in list(P_ORDER) + ["US"]:
            rr = res["US"][part] if t == "US" else rows.get(t, [])
            if not rr:
                continue
            g = lambda k_: np.array([r[k_] for r in rr], float)                    # noqa: E731
            say(f"| {LABEL.get(t, t)} | {len(rr)} | {fmt(np.nanmean(g(f'rho{h}')))} | {fmt(np.nanmean(g('rho60')))} | "
                f"{fmt(np.nanmean(g(f'prho{h}')))} | {fmt(np.nanmean(g(f'rho12_{h}')))} | {fmt(np.nanmean(g(f'diff{h}')), '{:+.2f}')}% |")
        say(f"\n日本合并（{'、'.join(POOL)}；同一段取平均）：{jp_s.get('n', 0)} 段，平均秩相关 {fmt(jp_s.get('mean'))}"
            f"（95% 区间 {fmt(jp_s.get('lo'))}〜{fmt(jp_s.get('hi'))}），为正的段 {fmt(jp_s.get('pos'), '{:.0f}')}%、为负 {fmt(jp_s.get('neg'), '{:.0f}')}%；"
            f"美国 49 行业 {us_s.get('n', 0)} 段 {fmt(us_s.get('mean'))}（{fmt(us_s.get('lo'))}〜{fmt(us_s.get('hi'))}）")
        name = "二" if part == "rebound" else "三"
        say(f"- **{name}：{'通过' if v['pass'] else '不通过'}**" + ("" if v["pass"] else "（" + "；".join(v["fails"]) + "）"))
        eps = []
        for d0 in jp_k:
            vals = [r for t in POOL for r in rows.get(t, []) if r["d0"] == d0]
            if vals:
                eps.append(f"{d0}（{vals[0]['q']} 主线 {'、'.join(vals[0]['ml'][:3])}…）{np.nanmean([x[f'{key}{h}'] for x in vals]):+.2f}")
        say("- 每一段（日本合并）：" + "；".join(eps))
        out[part] = {"jp": jp_s, "us": us_s, "verdict": v, "jp_episodes": dict(zip(jp_k, [float(x) for x in jp_v]))}
    # 另报：大跌当天就买；顶部前的关联度水平
    cdj, _ = pool({t: res["JP"][t]["crash_day"] for t in res["JP"]}, POOL, f"rho{h}")
    out["crash_day"] = {"jp": summarize(cdj), "us": summarize([r[f"rho{h}"] for r in res["US"]["crash_day"]])}
    say(f"\n另报：大跌段开始当天就买（不等反弹）：日本合并平均秩相关 {fmt(out['crash_day']['jp'].get('mean'))}"
        f"（{fmt(out['crash_day']['jp'].get('lo'))}〜{fmt(out['crash_day']['jp'].get('hi'))}）；美国 {fmt(out['crash_day']['us'].get('mean'))}。")
    lv = []
    for t in P_ORDER:
        rr = res["JP"].get(t, {})
        if rr.get("top"):
            lv.append(f"{LABEL[t]} 顶部 {np.nanmean([r['corr_mean'] for r in rr['top']]):+.3f} vs 各季度 {rr.get('base_corr', np.nan):+.3f}")
    say("另报：与主线篮子的平均相关（关联度的水平）：" + "；".join(lv))
    return out


P_ORDER = ("Z", "E", "W", "J", "J2")
LABEL = {"Z": "2001〜06 日経225", "E": "2006〜16 日経225", "W": "2006〜16 另一批 668 只", "J": "2017〜26 日経225",
         "J2": "2017〜26 时点 TOPIX 1000", "US": "美国 49 行业 1926〜2026"}


# ───────────────────────── 现在的位置（只描述）─────────────────────────
def current_state(nk: pd.Series, dv: pd.Series, P: dict, s33: dict, best) -> dict:
    S = P["J2"]
    groups = np.array([s33.get(t, "") for t in S["names"]], dtype=object)
    LR, REL = rel_returns(S["C"], S["M"])
    days = S["days"]
    last = days[-1]
    ml, sc, (qa, qb) = mainline_at(REL, days, groups, last + pd.Timedelta(days=1), ML_TOP["JP"])
    qtd_a = (last.to_period("Q")).start_time
    qtd = group_scores(REL, groups, np.flatnonzero(days >= qtd_a))
    corr = assoc(REL, groups, ml, len(days))
    from qbreak import jpx_list as JL
    names = {f"{c}.T": n for c, n in JL.names().items()}                     # 公司名用 JPX 公开名单（var/jpx_names.json），不用 J-Quants 的
    mem = S["M"][-1]
    rank = [j for j in np.argsort(-np.nan_to_num(corr, nan=-9)) if mem[j] and np.isfinite(corr[j])]
    order, other = rank[:10], [j for j in rank if groups[j] not in ml][:5]
    Bj = breadth(panel_dev(P["J"]["C"], P["J"]["days"]), P["J"]["M"])
    Bj2 = breadth(panel_dev(S["C"], days), S["M"])
    out = {"date": str(nk.index[-1].date()), "bdate": str(days[-1].date()), "dev": float(dv.iloc[-1]), "breadth_n225": float(Bj[-1]),
           "breadth_t1000": float(Bj2[-1]),
           "mainline_q": f"{qa.year}Q{(qa.month - 1) // 3 + 1}", "mainline": ml, "scores": {g: round(sc[g], 2) for g in ml},
           "qtd": top_k(qtd, ML_TOP["JP"]), "top_assoc": [{"ticker": S["names"][j], "name": names.get(S["names"][j], ""),
                                                         "ind": groups[j], "corr": round(float(corr[j]), 3)} for j in order],
           "top_assoc_other": [{"ticker": S["names"][j], "name": names.get(S["names"][j], ""), "ind": groups[j],
                                "corr": round(float(corr[j]), 3)} for j in other]}
    say(f"\n## 现在的位置（数据截至 {out['date']}；只描述）")
    say(f"- 日経225 13 周线乖离 {out['dev']:+.2f}%（{out['date']}）；13 周线 ≤ −15% 的个股比例（{out['bdate']}）：日経225 成分 {out['breadth_n225']:.0f}%、时点 TOPIX 1000 {out['breadth_t1000']:.0f}%"
        + (f"；一的「最好的深度」（≤ {best[0]:+.0f}%、比例 {'不要求' if best[1] == 0 else f'≥ {best[1]:.0f}%'}）现在{'成立' if out['dev'] <= best[0] and (best[1] == 0 or out['breadth_n225'] >= best[1]) else '不成立'}" if best else ""))
    say(f"- 时代主线（{out['mainline_q']} 判定，时点 TOPIX 1000 等权）：" + "、".join(f"{g}（{sc[g]:+.1f}%）" for g in ml)
        + f"；本季到现在（{qtd_a.date()}〜{last.date()}）领先：" + "、".join(out["qtd"]))
    say("- 现在与主线篮子关联最高的 10 只（近 126 个交易日的相关）：" + "、".join(f"{x['ticker'][:4]} {x['name']}（{x['ind']} {x['corr']:+.2f}）" for x in out["top_assoc"]))
    say("- 不属于主线業種、但关联最高的 5 只：" + "、".join(f"{x['ticker'][:4]} {x['name']}（{x['ind']} {x['corr']:+.2f}）" for x in out["top_assoc_other"]))
    return out


def main() -> int:
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 大跌入场的深度 × 时代主线的关联（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/crash_mainline_study.py 开头（运行前写定）。只描述与判定；模拟盘不变；非投资建议。")
    nk = n225()
    dv = line_dev(nk)
    P = jp_panels()
    s33 = s33_map()
    BR = {}
    for tag in ("Z", "E", "J", "J2"):
        S = P[tag]
        BR[tag] = pd.Series(breadth(panel_dev(S["C"], S["days"]), S["M"]), index=S["days"])
    Bexp = pd.concat([BR[t][(BR[t].index >= ERAS[t][0]) & (BR[t].index <= ERAS[t][1])] for t in ("Z", "E", "J")]).sort_index()
    Bexp = Bexp[~Bexp.index.duplicated()]
    Bj2 = BR["J2"][(BR["J2"].index >= ERAS["J"][0])]
    um = us_market()
    ud = line_dev(um)
    k_idx = idx_sd(um, "1965-01-01", "2026-09-30") / idx_sd(nk, "1965-01-01", "2026-09-30")
    SP = us_sp500_panel()
    jp_sd = float(np.median([daily_sd(P[t]["C"], P[t]["days"], *ERAS[t]) for t in ("Z", "E", "J")]))
    k_stk = daily_sd(SP["C"], SP["days"], *US_BREADTH) / jp_sd
    Bus = pd.Series(breadth(panel_dev(SP["C"], SP["days"]), SP["M"], STK_DEV * k_stk), index=SP["days"])
    say(f"数据：日経225 {nk.index[0].date()}〜{nk.index[-1].date()}；日本个股 " + "、".join(f"{LABEL[t]} {len(P[t]['names'])} 只" for t in P_ORDER)
        + f"；美国市场与 49 行业（Ken French）{um.index[0].date()}〜{um.index[-1].date()}；S&P 500 今天的成分 {len(SP['names'])} 只。"
        f"波动折算：指数 k = {k_idx:.3f}、个股 k = {k_stk:.3f}。")
    out = {"code": code, "k_idx": k_idx, "k_stk": k_stk}
    out["s1"] = run_s1(nk, dv, Bexp, Bj2, P, um, ud, Bus, k_idx)
    out["d25"] = run_d25(nk, P)
    print("二、三：逐段计算 …", flush=True)
    xs = run_xs(P, s33, nk, dv, um, ud, us_ind49(), k_idx)
    out["xs"] = report_xs(xs)
    out["xs_rows"] = {"JP": {t: {k: v for k, v in r.items() if k != "base_corr"} for t, r in xs["JP"].items()}, "US": xs["US"]}
    s1p, s2p = out["s1"]["verdict"]["pass"], out["xs"]["rebound"]["verdict"]["pass"]
    s3p = out["xs"]["top"]["verdict"]["pass"]
    dec = decide(s1p, s2p)
    out["decision"] = {"s1": s1p, "s2": s2p, "s3": s3p, "abc": dec}
    say("\n## 四、判定（事先写定）")
    say(f"一 入场深度：{'通过' if s1p else '不通过'}；二 反弹与主线关联：{'通过' if s2p else '不通过'}；三 暂时顶与主线关联：{'通过' if s3p else '不通过'}。")
    say({"B": "→ **B**：另外登记「暴跌反弹」一轮（在一的深度入场、买与主线关联高的个股、给一部分资金在暴跌时例外开仓；账户检验另登记，模拟盘要你确认才改）。",
         "C": "→ **C**：通过的那一部分做成前向记录（只记录、不交易），攒真实数据；不另开「暴跌反弹」。",
         "A": "→ **A**：到此为止，维持现行。"}[dec])
    say("三：" + ("通过 → 提议另外登记卖出侧的检验（暂时顶开始跌时先减与主线关联高的持仓）。" if s3p else "不通过 → 不做卖出侧的改动。"))
    out["now"] = current_state(nk, dv, P, s33, tuple(out["s1"]["best"]) if out["s1"].get("best") else None)
    out["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {out['elapsed_s']} s）。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / "crash_mainline_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(counts() if "--counts" in sys.argv else main())
