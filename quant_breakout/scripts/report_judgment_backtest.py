"""report_judgment_backtest.py — 市场风险报告的判断（行动四选一：观望 / 减仓观察 / 避险 / 加仓观察；24h 崩盘概率）放到过去的指数里，
按当时的情况重现每天会给出的判断，看之后一段时间（次日 / 5 / 20 / 60 个交易日）是否准确（登记检验）。
（2026-10-06 用户：「进行现在的市场分析日报里面的维持避险等等的判断放到过去的指数中结合当时的情况来看在过去的未来一段时间是否准确」）
规则先提交（登记）再运行一次；看到结果之后不改规则。

〇 已经知道的（照实写；不重复做）
  2026-10-01「市场风险报告参数 × 方向」（scripts/risk_param_direction_study.py，登记 20e0b46）只检验了报告显示的参数，当时写明
  「报告的『行动四选一』与『崩盘概率』只有一周记录 → 检验不了」。参数本身：利率 / 加息预期 / 油价 / 日元弱 越高 → 之后 60 日收益越低；
  VIX 高 / 信用差宽 → 之后收益反而更高（与报告把它们当「避险」理由的方向相反）。这次检验的是**判断本身**：把报告的红线 → 行动的规则
  机械化，在 1990〜2026 每天重现，看判断之后的走势；另外核对报告写的「24h 崩盘概率」与历史上同样情况下的实际频率。

一 报告的判断规则（从报告原文整理；artifact 7yUZBHV5FjcL4EV6HFEPMK，2026-10-06 08:02 早报第 3、6 节与 9/16〜10/6 的存档）
  美股红线：① 10 年国债收盘 > 5.20%（= 2007 年以来新高）② VIX > 22 且单日 +20% ③ HY 利差 > 330bp（从 266bp 扩大上来）④ SOX 单日 −5%
  ⑤ S&P 成分股 > 50 日线 < 25% ⑥ Brent > 115 或霍尔木兹受限。日本红线：① USD/JPY > 158（干预线；或 < 152 急升值）② JGB10Y > 3.20%
  ③ 日经 < 64,000（约 −8.5%）④ Advantest / 东京电子 / 软银G 同日都 −3% ⑤ Prime 下跌 > 70%（且外资周净卖 > 5,000 亿円）。
  行动的实际用法：没有红线 → 观望（9/16〜9/23）；接近 / 触发一条 → 减仓观察（9/24〜9/28）；利率红线 + 广度 / 信用红线同时 → 避险（9/29〜）。

二 换成「当时的相对阈值」的红线（每天收盘判定；只用当时已知的数据 → 没有前视）
  报告的阈值是按 2026 年的水平写的绝对数（10 年 5.20% 在 1990 年代是低利率）→ 换成它在当时的意思。
  红线都在各数据自己的日子上、用它自己的全部历史算好（1990 年初窗口就满），再取到判断日（日期 ≤ 判断日的最后一个值；比判断日早 10 天以上的旧值不用）。
  盘中还没收盘的当日 K 线不用；Yahoo 指数日线中间漏掉的最近几天（例 ^N225 2026-10-05）用那天的 5 分钟线合成补上（记进输出）。
  U1 利率：美 10 年（FRED DGS10）最近 10 个交易日内创过 52 周（252 日）收盘新高。
  U2 VIX：VIX ≥ 22 且单日 +20%（原样），最近 5 个交易日内发生过。
  U3 信用：Baa − 10 年（FRED BAA10Y，HY 利差的代理；免费的 HY OAS 只有 2023-10 起）比 63 日最低扩大的幅度，≥ 它自己过去 756 日的 90 分位。
  U4 半导体：SOX 单日 ≤ −5%（原样），最近 5 个交易日内（SOX 1994-05 起，之前不算）。
  U5 广度：Ken French 49 行业（日收益，CRSP）里收盘在自己 50 日均线之上的比例 < 25%（S&P 成分股比例的代理；数据到 2026-08，之后不算）。
  U6 原油：Brent（FRED DCOILBRENTEU）63 日涨幅 ≥ +25%。
  J1 汇率：USD/JPY（FRED DEXJPUS，东证日 t 只用 ≤ t−1 的值）最近 10 个交易日内创过 52 周新高（日元弱的极端），或 20 日变化 ≤ −4%（日元急升）。
  J2 日债：JGB10Y（财务省）最近 10 个交易日内创过 52 周新高。
  J3 指数：日经 ≤ 自己 63 日收盘最高的 92%。
  J4 半导体：6857 / 8035 / 9984 同一天都 ≤ −3%，最近 5 个交易日内（2000 起）。
  J5 广度 + 外资大卖：日経225 成分股（今天的名单）当天下跌的比例 ≥ 70%（≥ 100 只有值）且同一天日经 5 日收益 ≤ 它自己过去 756 日
     （不含今天，至少 252 个）的 10 分位（报告的「且外资周净卖 > 5,000 亿円」的价格代理：外资周度数据没有长历史），最近 5 个交易日内（2000 起）。
     （J5 在看个数之后改过一次——只看了各红线亮的比例，没看任何结果：原来只有「5 日内有一天 ≥ 70% 下跌」，1990〜 亮 50.4% 的日子，
     比报告带「且外资周净卖」的红线宽得多 → 加上「大卖周」条件后亮 13.0%（2000 年以后各年代 16〜20%）。）
三 行动（每个市场每天；核心红线 = 报告「避险」的推手：美国 U1 利率 / U3 信用，日本 J1 汇率 / J2 日债）
  避险 = 红线 ≥ 2 条且其中有核心红线；减仓观察 = 其余有红线的；加仓观察 = 没有红线且指数比 252 日最高跌了 ≥ 10%（跌出来的机会）；观望 = 其余。
  另报（只描述）：报告的总行动 = 东证日 t 的日本状态与它之前最后一个美国交易日的美国状态取更严的（加仓观察 < 观望 < 减仓观察 < 避险）。
四 结果（判断日 t 收盘之后）：美国 = S&P500（^GSPC，另报纳指 ^IXIC），日本 = 日经225（^N225）
  次日崩盘 = 下一交易日 盘中最低 或 收盘 比 t 日收盘 ≤ −3%（报告的定义「宽基单日或盘中 −3%」）；另报只看收盘的版本。
  5 / 20 / 60 日收益（%）；20 日内收盘最低比 t 日 ≤ −5%（「20 日内跌 5%」）；60 日内 ≤ −10%（「60 日内跌 10%」）。
  年代：A 1990〜2000、Z 2001〜2006-09、E 2006-10〜2016-09、J 2017〜最新。
五 判定（事先写定；每个市场分别判；「能判的年代」= 该年代避险 ≥ 60 天且观望 ≥ 60 天）
  V1 方向准（避险之后真的更差）：20 日收益 避险 − 观望 ≤ −1.0 pp 的年代 ≥ 3 个（能判的年代 ≥ 3 个才判）且全期差的 95% 区间上限 < 0
     （按月整块重抽 2,000 次）。
  V2 风险准（避险之后更容易跌）：「20 日内跌 5%」的比例 避险 ÷ 观望 ≥ 1.5 的年代 ≥ 3 个且全期比值的 95% 区间下限 > 1。
  V3 照着做有用：每天按状态拿指数（观望 / 加仓观察 100%、减仓观察 50%、避险 0%；t 日收盘的状态从 t+1 日起生效；换仓每单位扣 0.05%；
     美国 = S&P500 总收益 ^SP500TR、现金拿联邦基金利率 DFF；日本 = 日经 + 年 1.6% 股息、现金 0%）比一直拿着：Calmar 高 ≥ 0.05 的年代 ≥ 3 个，
     且全期 Calmar 超过状态序列循环平移（≥ 252 日、200 个种子）的 95 分位。
  V4 崩盘概率的校准：报告 27 期按它自己的行动分组的平均「24h 崩盘概率」vs 历史上同一状态（本研究的重现）的次日崩盘频率（全期、95% 区间按月重抽）：
     报告的平均 > 区间上限 →「过高」；< 下限 →「过低」；其余「大致合理」（历史同一状态不到 60 天 →「样本不够」）。
  综合读法只是描述：V1〜V3 各自「准 / 不准 / 样本不够」，V4 各行动「过高 / 合理 / 过低」。都不改模拟盘（判断层用的是报告的行动；要改要用户另外决定）。
六 另报（只描述）：① 报告这 27 期（2026-09-16 晚报〜10-06 早报）的下一个交易时段有没有崩盘、之后 5 个交易日的涨跌、同一时点本研究重现的状态与报告是否一致；
  ② 现在（数据最后一天）的红线与状态；③ 历史上与现在相似的局面：美国 = U1 利率红线亮 + S&P 在 252 日最高的 3% 以内 + VIX < 20；
  日本 = J1 日元弱的一边 + 日经在 252 日最高的 3% 以内 → 每段的第一天（相隔 ≥ 20 个交易日算新的一段）与之后 20 / 60 日；④ 历史上的避险段（≥ 5 天）。
七 事前预期（运行前写）：V1 约 25%（以前的研究：VIX 高 / 信用宽之后收益更高）；V2 约 65%（波动会聚集）；V3 约 15%（择时规则少有赢一直拿着的）；
  V4：报告写的 6〜20% 比历史频率「过高」约 85%（S&P 次日 −3% 在平静时期远低于 5%）。27 期里实际崩盘 0〜1 次。
八 局限：报告是每天人工 / AI 综合判断，这里是把它的红线机械化的近似（规则从报告原文来，不按结果调）；信用用 Baa − 10 年代替 HY OAS、广度用 49 行业
  代替成分股、日本没有外资周度数据；USD/JPY 用前一个美国交易日的纽约中午价（保守）；日経225 成分股用今天的名单（幸存者偏差）；
  早年的 Yahoo 盘中最低价可能不全（另报只看收盘的版本）；价格指数不含股息（V3 用总收益 / 股息近似）；税前；
  J4 / J5 2000 年以前没有数据 → A 年代（1990〜2000）的日本只看 J1〜J3；U5（49 行业）数据到 2026-08 → 报告这 27 期美国广度红线不会亮。非投资建议。
输出：var/out/report_judgment_backtest.md / .json（只有统计）。
  python scripts/report_judgment_backtest.py --prep   （只数个数：各年代各状态的天数，不算任何结果）
  python scripts/report_judgment_backtest.py --run    （登记之后只运行一次）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

START = "1990-01-01"
ERAS = {"A": ("1990-01-01", "2000-12-31"), "Z": ("2001-01-01", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-01", "2099-12-31")}
ERA_LABEL = {"A": "A 1990〜2000", "Z": "Z 2001〜2006-09", "E": "E 2006-10〜2016-09", "J": "J 2017〜最新"}
STATES = ("加仓观察", "观望", "减仓观察", "避险")
SEV = {"加仓观察": 0, "观望": 1, "减仓观察": 2, "避险": 3}
EXPO = {"加仓观察": 1.0, "观望": 1.0, "减仓观察": 0.5, "避险": 0.0}
US_LINES = ("U1", "U2", "U3", "U4", "U5", "U6")
JP_LINES = ("J1", "J2", "J3", "J4", "J5")
LINE_LABEL = {"U1": "利率", "U2": "VIX", "U3": "信用", "U4": "半导体", "U5": "广度", "U6": "原油",
              "J1": "汇率", "J2": "日债", "J3": "指数", "J4": "半导体", "J5": "广度"}
CORE = {"US": ("U1", "U3"), "JP": ("J1", "J2")}
NH_WIN, NH_RECENT = 252, 10
VIX_LVL, VIX_JUMP, EVENT_DAYS = 22.0, 0.20, 5
CR_WIN, CR_REF, CR_REF_MIN, CR_Q = 63, 756, 252, 0.90
SOX_DROP = -0.05
BREADTH_MA, BREADTH_TH = 50, 25.0
OIL_WIN, OIL_UP = 63, 0.25
FX_DOWN_WIN, FX_DOWN = 20, -0.04
N225_WIN, N225_DD = 63, 0.92
JP_SEMI = ("6857.T", "8035.T", "9984.T")
JP_SEMI_DROP = -0.03
JP_BREADTH_DOWN, JP_BREADTH_MIN = 70.0, 100
WEEK_WIN, WEEK_REF, WEEK_REF_MIN, WEEK_Q = 5, 756, 252, 0.10
ADD_DD, DD_WIN = 0.10, 252
CRASH = -0.03
HS = (5, 20, 60)
DD20, DD60 = -0.05, -0.10
COST = 0.0005
N225_DIV = 1.6
PLACEBO_SEEDS, PLACEBO_MIN_SHIFT, SEED = 200, 252, 20261006
BOOT = 2000
MIN_DAYS_ERA = 60
V1_GAP, V2_RATIO, V3_CAL, ERAS_NEED = -1.0, 1.5, 0.05, 3
ANALOG_NEAR_HIGH, ANALOG_VIX, ANALOG_GAP = 0.97, 20.0, 20
EPISODE_MIN = 5
STALE_DAYS = 10
OUT_MD, OUT_JSON = "report_judgment_backtest.md", "report_judgment_backtest.json"

# 报告的 27 期（artifact 存档 2026-09-16 晚报〜10-06 早报；与页面逐期核对过）：时间 JST、早 / 晚报、行动、
# 美股 崩盘% 暴跌 入场 退场 逆向、日本 崩盘% 暴跌 入场 退场 逆向
REPORTS = [
    ("2026-09-16 22:30", "晚报", "观望", 12, 3, 2, 3, 1, 8, 2, 3, 2, 2),
    ("2026-09-17 07:40", "早报", "观望", 11, 3, 2, 3, 1, 8, 2, 3, 2, 2),
    ("2026-09-17 22:19", "晚报", "观望", 10, 3, 2, 3, 1, 9, 2, 3, 3, 2),
    ("2026-09-18 07:53", "早报", "观望", 8, 2, 2, 2, 1, 9, 2, 3, 3, 2),
    ("2026-09-18 22:25", "晚报", "观望", 9, 2, 2, 2, 1, 12, 3, 2, 3, 2),
    ("2026-09-21 07:40", "早报", "观望", 8, 2, 2, 2, 1, 10, 3, 2, 3, 2),
    ("2026-09-21 22:22", "晚报", "观望", 7, 2, 2, 2, 1, 10, 3, 2, 3, 2),
    ("2026-09-22 07:56", "早报", "观望", 6, 2, 2, 2, 1, 9, 3, 2, 3, 2),
    ("2026-09-22 22:29", "晚报", "观望", 6, 2, 2, 2, 1, 10, 3, 2, 3, 2),
    ("2026-09-23 22:16", "晚报", "观望", 6, 2, 2, 2, 1, 10, 3, 2, 3, 2),
    ("2026-09-24 08:02", "早报", "减仓观察", 11, 3, 2, 3, 1, 12, 3, 2, 4, 2),
    ("2026-09-24 22:28", "晚报", "减仓观察", 15, 4, 2, 4, 1, 15, 4, 2, 4, 2),
    ("2026-09-25 08:03", "早报", "减仓观察", 15, 4, 2, 4, 1, 14, 4, 2, 4, 2),
    ("2026-09-25 22:37", "晚报", "减仓观察", 13, 4, 2, 4, 1, 12, 3, 2, 3, 2),
    ("2026-09-28 07:40", "早报", "减仓观察", 14, 4, 2, 4, 1, 11, 3, 2, 3, 2),
    ("2026-09-28 22:34", "晚报", "减仓观察", 17, 4, 1, 4, 1, 13, 3, 2, 3, 2),
    ("2026-09-29 08:02", "早报", "避险", 20, 4, 1, 5, 0, 12, 3, 2, 3, 2),
    ("2026-09-29 22:27", "晚报", "避险", 19, 4, 1, 5, 0, 16, 4, 2, 4, 1),
    ("2026-09-30 07:40", "早报", "避险", 20, 4, 1, 5, 0, 13, 4, 2, 4, 1),
    ("2026-09-30 22:22", "晚报", "避险", 16, 4, 2, 4, 1, 11, 3, 2, 3, 2),
    ("2026-10-01 08:17", "早报", "避险", 18, 4, 1, 5, 1, 10, 3, 2, 3, 2),
    ("2026-10-01 22:30", "晚报", "避险", 19, 4, 1, 5, 1, 14, 4, 1, 4, 1),
    ("2026-10-02 08:06", "早报", "避险", 18, 4, 1, 5, 1, 12, 4, 1, 4, 1),
    ("2026-10-02 22:25", "晚报", "避险", 14, 3, 1, 4, 2, 13, 4, 1, 4, 1),
    ("2026-10-05 07:40", "早报", "避险", 13, 3, 1, 4, 2, 11, 4, 1, 4, 1),
    ("2026-10-05 22:45", "晚报", "避险", 14, 3, 1, 4, 2, 12, 4, 1, 4, 1),
    ("2026-10-06 08:02", "早报", "避险", 13, 3, 1, 4, 2, 11, 4, 1, 4, 1),
]


# ───────────────────────── 红线（纯函数，有测试） ─────────────────────────
def asof(s: pd.Series, days: pd.DatetimeIndex, lag_days: int = 0, stale: int = STALE_DAYS) -> pd.Series:
    """每个 day 取「日期 ≤ day − lag_days」的最后一个值；比那天早 stale 天以上的不用（NaN）。"""
    s = s.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    want = days - pd.Timedelta(days=lag_days)
    pos = s.index.searchsorted(want, side="right") - 1
    ok = pos >= 0
    vals = np.full(len(days), np.nan)
    vals[ok] = s.values[pos[ok]]
    when = pd.Series(pd.NaT, index=days)
    when[ok] = s.index[pos[ok]]
    too_old = (want - pd.DatetimeIndex(when.values)) > pd.Timedelta(days=stale)
    vals[np.asarray(too_old, bool)] = np.nan
    return pd.Series(vals, index=days)


def new_high_recent(s: pd.Series, win: int = NH_WIN, recent: int = NH_RECENT) -> pd.Series:
    """最近 recent 个交易日内，有一天收盘 ≥ 它之前 win − 1 天的最高（52 周新高）。"""
    prev = s.shift(1).rolling(win - 1, min_periods=200).max()
    nh = ((s >= prev) & prev.notna() & s.notna()).astype(float)
    return nh.rolling(recent, min_periods=1).max().fillna(0).astype(bool)


def recent(ev: pd.Series, days: int = EVENT_DAYS) -> pd.Series:
    return ev.fillna(False).astype(float).rolling(days, min_periods=1).max().fillna(0).astype(bool)


def vix_spike(v: pd.Series) -> pd.Series:
    return (v >= VIX_LVL) & ((v / v.shift(1) - 1) >= VIX_JUMP)


def credit_widening(sp: pd.Series) -> pd.Series:
    """比 63 日最低扩大的幅度 ≥ 过去 756 日（不含今天）同一统计量的 90 分位。"""
    w = sp - sp.rolling(CR_WIN, min_periods=CR_WIN).min()
    thr = w.shift(1).rolling(CR_REF, min_periods=CR_REF_MIN).quantile(CR_Q)
    return ((w >= thr) & (w > 0) & thr.notna()).fillna(False)


def breadth_above_ma(ret_pct: pd.DataFrame, ma: int = BREADTH_MA) -> pd.Series:
    """各组合（日收益 %）的累计指数在自己 ma 日均线之上的比例 %（有值的组合里）。"""
    r = ret_pct / 100.0
    px = (1 + r.fillna(0)).cumprod().where(r.notna())
    m = px.rolling(ma, min_periods=ma).mean()
    valid = m.notna() & px.notna()
    above = (px > m) & valid
    n = valid.sum(axis=1)
    return (100.0 * above.sum(axis=1) / n.replace(0, np.nan))


def oil_spike(b: pd.Series) -> pd.Series:
    return ((b / b.shift(OIL_WIN) - 1) >= OIL_UP).fillna(False)


def fx_line(fx: pd.Series) -> pd.Series:
    weak = new_high_recent(fx)
    strong = ((fx / fx.shift(FX_DOWN_WIN) - 1) <= FX_DOWN).fillna(False)
    return weak | strong


def index_break(c: pd.Series) -> pd.Series:
    return (c <= N225_DD * c.rolling(N225_WIN, min_periods=N225_WIN).max()).fillna(False)


def semis_all_down(rets: pd.DataFrame) -> pd.Series:
    ok = rets.notna().all(axis=1)
    return ((rets <= JP_SEMI_DROP).all(axis=1) & ok)


def breadth_down(rets: pd.DataFrame) -> pd.Series:
    valid = rets.notna().sum(axis=1)
    pct = 100.0 * (rets < 0).sum(axis=1) / valid.replace(0, np.nan)
    return ((pct >= JP_BREADTH_DOWN) & (valid >= JP_BREADTH_MIN)).fillna(False)


def heavy_week(c: pd.Series) -> pd.Series:
    """5 日收益 ≤ 它自己过去 756 日（不含今天，至少 252 个）的 10 分位（外资大卖周的价格代理）。"""
    r = c / c.shift(WEEK_WIN) - 1
    thr = r.shift(1).rolling(WEEK_REF, min_periods=WEEK_REF_MIN).quantile(WEEK_Q)
    return ((r <= thr) & thr.notna()).fillna(False)


def drawdown(c: pd.Series, win: int = DD_WIN) -> pd.Series:
    return c / c.rolling(win, min_periods=60).max() - 1


def action(red: pd.DataFrame, core: tuple, dd: pd.Series) -> pd.Series:
    """三 的映射：避险 = ≥ 2 条且有核心；减仓观察 = 其余有红线；加仓观察 = 没有红线且跌了 ≥ 10%；观望 = 其余。"""
    n = red.sum(axis=1)
    c = red[list(core)].any(axis=1)
    out = np.where((n >= 2) & c, "避险", np.where(n >= 1, "减仓观察", np.where(dd.fillna(0) <= -ADD_DD, "加仓观察", "观望")))
    return pd.Series(out, index=red.index)


def worse(a: str, b: str) -> str:
    return a if SEV[a] >= SEV[b] else b


# ───────────────────────── 结果（判断日 t 收盘之后） ─────────────────────────
def outcomes(ohlc: pd.DataFrame) -> pd.DataFrame:
    c, lo = ohlc["Close"].astype(float), ohlc["Low"].astype(float)
    lo = lo.where(lo > 0)                                                   # 坏的盘中最低（≤ 0）→ 那天只看收盘
    o = pd.DataFrame(index=c.index)
    nc = c.shift(-1) / c - 1
    nl = lo.shift(-1) / c - 1
    has = c.shift(-1).notna()
    o["crash1"] = ((nl <= CRASH) | (nc <= CRASH)).astype(float).where(has)
    o["crash1c"] = (nc <= CRASH).astype(float).where(has)
    for h in HS:
        o[f"r{h}"] = (c.shift(-h) / c - 1) * 100
    for h, th, col in ((20, DD20, "dd20"), (60, DD60, "dd60")):
        fmin = c.shift(-1)[::-1].rolling(h, min_periods=h).min()[::-1]
        o[col] = ((fmin / c - 1) <= th).astype(float).where(fmin.notna())
        o[f"mdd{h}"] = ((fmin / c - 1) * 100).where(fmin.notna())
    return o


# ───────────────────────── 统计 ─────────────────────────
def in_era(idx: pd.DatetimeIndex, era: str | None) -> np.ndarray:
    if era is None:
        return np.ones(len(idx), bool)
    a, b = ERAS[era]
    return np.asarray((idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b)), bool)


def state_table(state: pd.Series, out: pd.DataFrame, mask: np.ndarray) -> dict:
    t = {}
    for s in STATES:
        m = mask & (state.values == s)
        x = out[m]
        d = {"n": int(m.sum())}
        if d["n"]:
            for col in ("crash1", "crash1c", "dd20", "dd60"):
                v = x[col].dropna()
                d[col] = (round(float(v.mean() * 100), 2) if len(v) else None)
            for h in HS:
                v = x[f"r{h}"].dropna()
                d[f"r{h}"] = (round(float(v.mean()), 2) if len(v) else None)
                d[f"r{h}_med"] = (round(float(v.median()), 2) if len(v) else None)
                d[f"r{h}_pos"] = (round(float((v > 0).mean() * 100), 1) if len(v) else None)
        t[s] = d
    return t


def boot_compare(state: pd.Series, val: pd.Series, mask: np.ndarray, a: str, b: str, kind: str,
                 n: int = BOOT, seed: int = SEED) -> dict:
    """a vs b：kind = "diff"（均值差）或 "ratio"（均值比）；按月整块重抽。"""
    df = pd.DataFrame({"s": state.values, "v": val.values}, index=state.index)[mask]
    df = df[df["s"].isin([a, b]) & df["v"].notna()]
    if df.empty or (df["s"] == a).sum() == 0 or (df["s"] == b).sum() == 0:
        return {"est": None, "lo": None, "hi": None}
    mon = df.index.to_period("M")
    g = df.groupby([mon, df["s"]])["v"].agg(["sum", "count"]).unstack("s").fillna(0)
    S = {k: g[("sum", k)].to_numpy() if ("sum", k) in g.columns else np.zeros(len(g)) for k in (a, b)}
    C = {k: g[("count", k)].to_numpy() if ("count", k) in g.columns else np.zeros(len(g)) for k in (a, b)}

    def stat(ix):
        ma = S[a][ix].sum() / max(C[a][ix].sum(), 1e-12)
        mb = S[b][ix].sum() / max(C[b][ix].sum(), 1e-12)
        if C[a][ix].sum() == 0 or C[b][ix].sum() == 0:
            return np.nan
        return (ma - mb) if kind == "diff" else (ma / mb if mb > 0 else np.nan)
    est = stat(np.arange(len(g)))
    rng = np.random.default_rng(seed)
    bs = np.array([stat(rng.integers(0, len(g), len(g))) for _ in range(n)])
    bs = bs[np.isfinite(bs)]
    return {"est": (round(float(est), 3) if np.isfinite(est) else None),
            "lo": (round(float(np.percentile(bs, 2.5)), 3) if len(bs) else None),
            "hi": (round(float(np.percentile(bs, 97.5)), 3) if len(bs) else None)}


def boot_rate(val: pd.Series, mask: np.ndarray, n: int = BOOT, seed: int = SEED) -> dict:
    v = val[mask].dropna()
    if v.empty:
        return {"est": None, "lo": None, "hi": None, "n": 0}
    mon = v.index.to_period("M")
    g = v.groupby(mon).agg(["sum", "count"])
    s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n):
        ix = rng.integers(0, len(g), len(g))
        bs.append(s[ix].sum() / c[ix].sum())
    return {"est": round(float(v.mean() * 100), 2), "lo": round(float(np.percentile(bs, 2.5) * 100), 2),
            "hi": round(float(np.percentile(bs, 97.5) * 100), 2), "n": int(len(v))}


def strategy_returns(state: pd.Series, r_in: pd.Series, r_cash: pd.Series) -> pd.Series:
    expo = state.map(EXPO).astype(float).shift(1).fillna(1.0)
    turn = expo.diff().abs().fillna(0.0)
    return expo * r_in.fillna(0) + (1 - expo) * r_cash.fillna(0) - COST * turn


def curve_stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 60:
        return {"cagr": None, "mdd": None, "calmar": None}
    eq = (1 + r).cumprod()
    yrs = max((r.index[-1] - r.index[0]).days / 365.25, 1e-9)
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    mdd = float((eq / eq.cummax() - 1).min())
    return {"cagr": round(cagr * 100, 2), "mdd": round(mdd * 100, 2), "calmar": (round(cagr / abs(mdd), 3) if mdd < 0 else None)}


def placebo_calmar(state: pd.Series, r_in: pd.Series, r_cash: pd.Series, seeds: int = PLACEBO_SEEDS,
                   min_shift: int = PLACEBO_MIN_SHIFT, seed: int = SEED) -> list[float]:
    vals = state.to_numpy()
    n = len(vals)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(seeds):
        k = int(rng.integers(min_shift, n - min_shift))
        sh = pd.Series(np.roll(vals, k), index=state.index)
        c = curve_stats(strategy_returns(sh, r_in, r_cash))["calmar"]
        if c is not None:
            out.append(c)
    return out


def verdict_market(by_era: dict, full: dict, strat: dict, pl95: float | None) -> dict:
    """五 V1〜V3（每个市场）。by_era = {年代: {state_table, diff20, ratio20}}；full = 全期的 diff20 / ratio20 区间。"""
    ok_eras = [e for e, d in by_era.items() if (d["tab"]["避险"]["n"] >= MIN_DAYS_ERA and d["tab"]["观望"]["n"] >= MIN_DAYS_ERA)]
    res = {"eras": ok_eras}
    if len(ok_eras) < ERAS_NEED:
        res["V1"] = res["V2"] = "样本不够"
    else:
        c1 = [e for e in ok_eras if by_era[e]["diff20"]["est"] is not None and by_era[e]["diff20"]["est"] <= V1_GAP]
        c2 = [e for e in ok_eras if by_era[e]["ratio20"]["est"] is not None and by_era[e]["ratio20"]["est"] >= V2_RATIO]
        res["V1_eras"], res["V2_eras"] = c1, c2
        res["V1"] = "准" if (len(c1) >= ERAS_NEED and full["diff20"]["hi"] is not None and full["diff20"]["hi"] < 0) else "不准"
        res["V2"] = "准" if (len(c2) >= ERAS_NEED and full["ratio20"]["lo"] is not None and full["ratio20"]["lo"] > 1) else "不准"
    c3 = [e for e in ERAS if e in strat and strat[e]["E1"]["calmar"] is not None and strat[e]["BH"]["calmar"] is not None
          and strat[e]["E1"]["calmar"] >= strat[e]["BH"]["calmar"] + V3_CAL]
    fc = strat.get("FULL", {}).get("E1", {}).get("calmar")
    res["V3_eras"] = c3
    res["V3"] = "有用" if (len(c3) >= ERAS_NEED and fc is not None and pl95 is not None and fc > pl95) else "没用"
    return res


def calib(report_mean: float | None, ci: dict) -> str | None:
    if report_mean is None or ci.get("lo") is None:
        return None
    if ci.get("n", MIN_DAYS_ERA) < MIN_DAYS_ERA:
        return "样本不够"
    if report_mean > ci["hi"]:
        return "过高"
    if report_mean < ci["lo"]:
        return "过低"
    return "大致合理"


# ───────────────────────── 报告的 27 期 ─────────────────────────
def report_sessions(when: pd.Timestamp, kind: str, us_days: pd.DatetimeIndex, jp_days: pd.DatetimeIndex) -> dict:
    """报告之后的下一个交易时段（美国 = 美国日期 ≥ JST 日期 d 的第一个；日本 = 早报 ≥ d、晚报 > d 的第一个）与之前最后一个收盘。"""
    d = when.normalize()
    ui = int(us_days.searchsorted(d, side="left"))
    ji = int(jp_days.searchsorted(d, side="left" if kind == "早报" else "right"))
    return {"us_next": ui if ui < len(us_days) else None, "us_prev": ui - 1,
            "jp_next": ji if ji < len(jp_days) else None, "jp_prev": ji - 1}


def report_rows(us: pd.DataFrame, jp: pd.DataFrame, st_us: pd.Series, st_jp: pd.Series) -> list[dict]:
    rows = []
    for r in REPORTS:
        when = pd.Timestamp(r[0])
        ss = report_sessions(when, r[1], us.index, jp.index)
        row = {"when": r[0], "kind": r[1], "act": r[2], "us_p": r[3], "jp_p": r[8]}
        for m, df, nx, pv, st in (("us", us, ss["us_next"], ss["us_prev"], st_us), ("jp", jp, ss["jp_next"], ss["jp_prev"], st_jp)):
            if nx is None or pv < 0:
                row[m + "_crash"] = row[m + "_r5"] = None
            else:
                base = float(df["Close"].iloc[pv])
                lo, cl = float(df["Low"].iloc[nx]), float(df["Close"].iloc[nx])
                lo = lo if lo > 0 else cl
                row[m + "_date"] = str(df.index[nx].date())
                row[m + "_crash"] = int(min(lo, cl) / base - 1 <= CRASH)
                row[m + "_next"] = round((cl / base - 1) * 100, 2)
                j5 = nx + 4
                row[m + "_r5"] = (round((float(df["Close"].iloc[j5]) / base - 1) * 100, 2) if j5 < len(df) else None)
            row[m + "_proxy"] = (str(st.iloc[pv]) if pv >= 0 else None)
        row["proxy"] = (worse(row["us_proxy"], row["jp_proxy"]) if row.get("us_proxy") and row.get("jp_proxy") else None)
        rows.append(row)
    return rows


# ───────────────────────── 输入 ─────────────────────────
def ff49_daily(fp: Path | None = None) -> pd.DataFrame:
    from qbreak import paths
    fp = fp or paths.sub("cache") / "ff_daily" / "49_Industry_Portfolios_daily.csv"
    return parse_ff_daily(Path(fp).read_text(encoding="latin-1"))


def parse_ff_daily(text: str, table: str = "Average Value Weighted Returns -- Daily") -> pd.DataFrame:
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if table in l)
    head = [h.strip() for h in lines[i + 1].split(",")][1:]
    idx, rows = [], []
    for l in lines[i + 2:]:
        p = [x.strip() for x in l.split(",")]
        if len(p[0]) != 8 or not p[0].isdigit():
            break
        idx.append(pd.Timestamp(p[0][:4] + "-" + p[0][4:6] + "-" + p[0][6:]))
        rows.append([float(x) for x in p[1:len(head) + 1]])
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=head)
    return df.where(df > -99.0)


def synth_days(df: pd.DataFrame, bars: pd.DataFrame, today, today_closed: bool, min_bars: int = 30) -> tuple[pd.DataFrame, list[str]]:
    """5 分钟线（索引 = 当地时间）里有、日线里没有、已收盘、根数够的日子 → 合成日线（开 = 第一根、高 / 低 = 极值、收 = 最后一根）补进去。"""
    if bars is None or not len(bars) or not len(df):
        return df, []
    ix = pd.DatetimeIndex(bars.index)
    ix = ix.tz_localize(None) if ix.tz is not None else ix
    have = set(pd.DatetimeIndex(df.index).normalize())
    rows = {}
    for day, g in bars.dropna(subset=["Close"]).groupby(ix[bars["Close"].notna().to_numpy()].normalize()):
        day = pd.Timestamp(day)
        if day in have or len(g) < min_bars or day < df.index[0] or day.date() > today or (day.date() == today and not today_closed):
            continue
        rows[day] = {"Open": float(g["Open"].iloc[0]), "High": float(g["High"].max()), "Low": float(g["Low"].min()),
                     "Close": float(g["Close"].iloc[-1]),
                     "Volume": (float(pd.to_numeric(g["Volume"], errors="coerce").fillna(0).sum()) if "Volume" in g.columns else 0.0)}
    if not rows:
        return df, []
    add = pd.DataFrame.from_dict(rows, orient="index")
    out = pd.concat([df, add[[c for c in df.columns if c in add.columns]]]).sort_index()
    return out[~out.index.duplicated(keep="first")], [str(d.date()) for d in sorted(rows)]


def fill_index_gaps(t: str, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    from zoneinfo import ZoneInfo

    from qbreak.calendar_jp import JST
    from qbreak.data import FILL_MIN_BARS, _market_of, _yf_intraday
    from qbreak.trader import market_session_closed
    m = _market_of(t) or "US"
    tz = JST if m == "JP" else ZoneInfo("America/New_York")
    try:
        bars = _yf_intraday(t)
    except Exception:                                                        # noqa: BLE001
        return df, []
    if bars is None or not len(bars) or "Close" not in bars.columns:
        return df, []
    ix = pd.DatetimeIndex(bars.index)
    bars = bars.copy()
    bars.index = ix.tz_localize("UTC").tz_convert(tz) if ix.tz is None else ix.tz_convert(tz)
    today, closed = market_session_closed(m)
    return synth_days(df, bars, today, closed, FILL_MIN_BARS)


def load_inputs(say=print) -> dict:
    from qbreak import factors, universes
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak.data import _market_of
    from qbreak.trader import drop_partial_bar
    t0 = time.time()
    idx = load_universe(["^GSPC", "^IXIC", "^SP500TR", "^N225", "^SOX", "^VIX"] + list(JP_SEMI), DataConfig(years=37))
    idx = {t: drop_partial_bar(df, _market_of(t) or "US") for t, df in idx.items()}      # 盘中还没收盘的当日 K 线不用
    filled = {}
    for t in [t for t in idx if t.startswith("^")]:                         # 日线中间漏掉的最近几天 → 5 分钟线合成
        idx[t], add = fill_index_gaps(t, idx[t])
        if add:
            filled[t] = add
    say(f"指数 / 半导体：{len(idx)} 个；5 分钟线补的日子 {filled or '无'}；{time.time() - t0:.0f}s")
    fred = {k: factors.fred(v) for k, v in {"us10y": "DGS10", "baa": "BAA10Y", "brent": "DCOILBRENTEU", "dff": "DFF", "usdjpy": "DEXJPUS"}.items()}
    jgb = factors.jgb_curve()["10Y"].dropna()
    ff = ff49_daily()
    mem = {t: drop_partial_bar(df, "JP") for t, df in load_universe(universes.nikkei225(), DataConfig(years=27)).items()}
    say(f"FRED / 财务省 / 49 行业 / 日経225 成分 {len(mem)} 只；{time.time() - t0:.0f}s")
    return {"idx": idx, "fred": fred, "jgb": jgb, "ff": ff, "mem": mem, "filled": filled}


def on_days(flag: pd.Series, days: pd.DatetimeIndex, lag_days: int = 0) -> pd.Series:
    """在源数据自己的日子上算好的红线 → 目标交易日（取日期 ≤ day − lag_days 的最后一个；数据过旧 = 不亮）。"""
    return asof(flag.astype(float), days, lag_days) > 0.5


def build(inp: dict) -> dict:
    """两个市场每天的红线、状态与结果（只用当时已知的数据）。红线在各数据自己的全部历史上算（1990 年初窗口就满），评估从 START 起。"""
    idx = inp["idx"]
    usf = idx["^GSPC"]
    ufd = usf.index
    U = pd.DataFrame(index=ufd)
    U["U1"] = on_days(new_high_recent(inp["fred"]["us10y"]), ufd)
    vixf = idx["^VIX"]["Close"].reindex(ufd)
    U["U2"] = recent(vix_spike(vixf))
    U["U3"] = on_days(credit_widening(inp["fred"]["baa"]), ufd)
    sox = idx["^SOX"]["Close"].reindex(ufd)
    U["U4"] = recent((sox.pct_change(fill_method=None) <= SOX_DROP).fillna(False))
    brf = breadth_above_ma(inp["ff"]).reindex(ufd)
    U["U5"] = (brf < BREADTH_TH).fillna(False)
    U["U6"] = on_days(oil_spike(inp["fred"]["brent"]), ufd)
    st_usf = action(U[list(US_LINES)], CORE["US"], drawdown(usf["Close"]))

    jpf = idx["^N225"]
    jfd = jpf.index
    J = pd.DataFrame(index=jfd)
    J["J1"] = on_days(fx_line(inp["fred"]["usdjpy"]), jfd, lag_days=1)
    J["J2"] = on_days(new_high_recent(inp["jgb"]), jfd)
    J["J3"] = index_break(jpf["Close"])
    semi = pd.DataFrame({t: idx[t]["Close"] for t in JP_SEMI if t in idx}).reindex(jfd).pct_change(fill_method=None)
    J["J4"] = recent(semis_all_down(semi)) if len(semi.columns) == len(JP_SEMI) else False
    memc = pd.DataFrame({t: df["Close"] for t, df in inp["mem"].items()}).reindex(jfd)
    J["J5"] = recent(breadth_down(memc.pct_change(fill_method=None)) & heavy_week(jpf["Close"]))
    st_jpf = action(J[list(JP_LINES)], CORE["JP"], drawdown(jpf["Close"]))

    # 报告的总行动（东证日 t：日本 t + 它之前最后一个美国交易日）
    upos = ufd.searchsorted(jfd, side="left") - 1
    us_prev = pd.Series([st_usf.iloc[i] if i >= 0 else "观望" for i in upos], index=jfd)
    st_allf = pd.Series([worse(a, b) for a, b in zip(st_jpf.values, us_prev.values)], index=jfd)

    us, jp = usf.loc[START:], jpf.loc[START:]
    ud, jd = us.index, jp.index
    r_us_in = idx["^SP500TR"]["Close"].reindex(ud).pct_change(fill_method=None)
    r_us_cash = asof(inp["fred"]["dff"], ud) / 100 / 252
    r_jp_in = jp["Close"].pct_change(fill_method=None) + N225_DIV / 100 / 252
    r_jp_cash = pd.Series(0.0, index=jd)
    return {"us": us, "jp": jp, "U": U.loc[START:], "J": J.loc[START:], "st_us": st_usf.loc[START:], "st_jp": st_jpf.loc[START:],
            "st_all": st_allf.loc[START:], "o_us": outcomes(usf).loc[START:], "o_jp": outcomes(jpf).loc[START:],
            "o_ndx": outcomes(idx["^IXIC"].reindex(ufd)).loc[START:], "breadth": brf.loc[START:], "vix": vixf.loc[START:],
            "r_us": (r_us_in, r_us_cash), "r_jp": (r_jp_in, r_jp_cash), "_fx": inp["fred"]["usdjpy"],
            "ends": {"us10y": str(inp["fred"]["us10y"].dropna().index[-1].date()), "baa": str(inp["fred"]["baa"].dropna().index[-1].date()),
                     "brent": str(inp["fred"]["brent"].dropna().index[-1].date()), "usdjpy": str(inp["fred"]["usdjpy"].dropna().index[-1].date()),
                     "jgb10y": str(inp["jgb"].index[-1].date()), "ff49": str(inp["ff"].dropna(how="all").index[-1].date()),
                     "gspc": str(ud[-1].date()), "n225": str(jd[-1].date())}, "filled": inp.get("filled", {})}


def counts(B: dict) -> dict:
    out = {}
    for m, st in (("US", B["st_us"]), ("JP", B["st_jp"]), ("ALL", B["st_all"])):
        out[m] = {e: {s: int(((st.values == s) & in_era(st.index, e)).sum()) for s in STATES} for e in ERAS}
    out["lines"] = {m: {k: round(float(df[k].mean() * 100), 1) for k in df.columns} for m, df in (("US", B["U"]), ("JP", B["J"]))}
    return out


# ───────────────────────── 运行 ─────────────────────────
def episodes(state: pd.Series, target: str, min_len: int = EPISODE_MIN) -> list[tuple[int, int]]:
    v = (state.values == target)
    out, i = [], 0
    while i < len(v):
        if v[i]:
            j = i
            while j + 1 < len(v) and v[j + 1]:
                j += 1
            if j - i + 1 >= min_len:
                out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def analog_starts(flag: pd.Series, gap: int = ANALOG_GAP) -> list[int]:
    starts, last = [], -10 ** 9
    for i, f in enumerate(flag.values):
        if f and i - last > gap:
            starts.append(i)
        if f:
            last = i
    return starts


def run(say=print, inp: dict | None = None) -> dict:
    t0 = time.time()
    B = build(inp if inp is not None else load_inputs(say))
    res = {"git": git_info(), "counts": counts(B), "ends": B["ends"], "filled": B["filled"], "markets": {}}
    for m, st, o, (rin, rc) in (("US", B["st_us"], B["o_us"], B["r_us"]), ("JP", B["st_jp"], B["o_jp"], B["r_jp"])):
        by_era, strat = {}, {}
        for e in list(ERAS) + [None]:
            mask = in_era(st.index, e)
            tab = state_table(st, o, mask)
            d20 = boot_compare(st, o["r20"], mask, "避险", "观望", "diff")
            r20 = boot_compare(st, o["dd20"], mask, "避险", "观望", "ratio")
            key = e or "FULL"
            sub = st.index[mask]
            if len(sub):
                rr = strategy_returns(st, rin, rc).loc[sub[0]:sub[-1]]
                bh = strategy_returns(pd.Series("观望", index=st.index), rin, rc).loc[sub[0]:sub[-1]]
                strat[key] = {"E1": curve_stats(rr), "BH": curve_stats(bh),
                              "share": {s: round(float((st[mask] == s).mean() * 100), 1) for s in STATES}}
            if e:
                by_era[e] = {"tab": tab, "diff20": d20, "ratio20": r20}
            else:
                full = {"tab": tab, "diff20": d20, "ratio20": r20,
                        "crash_ci": {s: boot_rate(o["crash1"], mask & (st.values == s)) for s in STATES}}
        pl = placebo_calmar(st, rin, rc)
        pl95 = (float(np.percentile(pl, 95)) if pl else None)
        res["markets"][m] = {"by_era": by_era, "full": full, "strat": strat, "pl95": pl95, "pl_med": (float(np.median(pl)) if pl else None),
                             "verdict": verdict_market(by_era, full, strat, pl95)}
        say(f"{m}：判定 {res['markets'][m]['verdict']}；{time.time() - t0:.0f}s")
    # 纳指（美国状态，只描述）
    res["ndx"] = state_table(B["st_us"], B["o_ndx"], in_era(B["st_us"].index, None))
    # 总行动（东证日历，只描述）：日经结果
    res["all_jp"] = state_table(B["st_all"], B["o_jp"], in_era(B["st_all"].index, None))
    # V4 校准
    rows = report_rows(B["us"], B["jp"], B["st_us"], B["st_jp"])
    res["reports"] = rows
    cal = {}
    for m, key in (("US", "us_p"), ("JP", "jp_p")):
        cal[m] = {}
        for s in ("观望", "减仓观察", "避险"):
            ps = [r[key] for r in rows if r["act"] == s]
            mean = (round(float(np.mean(ps)), 2) if ps else None)
            ci = res["markets"][m]["full"]["crash_ci"][s]
            cal[m][s] = {"report_mean": mean, "n_reports": len(ps), "hist": ci, "verdict": calib(mean, ci)}
    res["calib"] = cal
    agree = [r for r in rows if r.get("proxy")]
    res["fidelity"] = {"n": len(agree), "same": int(sum(r["proxy"] == r["act"] for r in agree))}
    # 现在与相似局面
    res["now"] = now_reading(B)
    res["analog"] = analogs(B)
    res["episodes"] = {m: episode_rows(st, o, L, lines) for m, st, o, L, lines in
                       (("US", B["st_us"], B["o_us"], B["U"], US_LINES), ("JP", B["st_jp"], B["o_jp"], B["J"], JP_LINES))}
    res["elapsed_s"] = round(time.time() - t0)
    return res


def now_reading(B: dict) -> dict:
    out = {}
    for m, L, st, lines in (("US", B["U"], B["st_us"], US_LINES), ("JP", B["J"], B["st_jp"], JP_LINES)):
        i = len(st) - 1
        out[m] = {"date": str(st.index[i].date()), "state": str(st.iloc[i]), "lines": {k: bool(L[k].iloc[i]) for k in lines}}
    out["US"]["breadth_last"] = (round(float(B["breadth"].dropna().iloc[-1]), 1) if B["breadth"].notna().any() else None)
    out["US"]["breadth_date"] = (str(B["breadth"].dropna().index[-1].date()) if B["breadth"].notna().any() else None)
    out["ALL"] = {"date": str(B["st_all"].index[-1].date()), "state": str(B["st_all"].iloc[-1])}
    return out


def analogs(B: dict) -> dict:
    us, jp = B["us"]["Close"], B["jp"]["Close"]
    near_us = us >= ANALOG_NEAR_HIGH * us.rolling(DD_WIN, min_periods=60).max()
    f_us = B["U"]["U1"] & near_us & (B["vix"] < ANALOG_VIX)
    weak = on_days(new_high_recent(B["_fx"]), jp.index, lag_days=1)              # 只要日元弱的一边（不含急升值）
    near_jp = jp >= ANALOG_NEAR_HIGH * jp.rolling(DD_WIN, min_periods=60).max()
    f_jp = weak & near_jp
    out = {}
    for m, f, o, idx in (("US", f_us, B["o_us"], us.index), ("JP", f_jp, B["o_jp"], jp.index)):
        st = analog_starts(f)
        rows = [{"date": str(idx[i].date()), "r20": _num(o["r20"].iloc[i]), "r60": _num(o["r60"].iloc[i]), "mdd60": _num(o["mdd60"].iloc[i])} for i in st]
        done = [r for r in rows if r["r60"] is not None]
        out[m] = {"n_days": int(f.sum()), "n_episodes": len(rows), "rows": rows,
                  "r20_mean": (round(float(np.mean([r["r20"] for r in rows if r["r20"] is not None])), 2) if rows else None),
                  "r60_mean": (round(float(np.mean([r["r60"] for r in done])), 2) if done else None),
                  "r60_pos": (round(float(np.mean([r["r60"] > 0 for r in done]) * 100), 1) if done else None),
                  "mdd60_le10": (round(float(np.mean([r["mdd60"] <= -10 for r in done]) * 100), 1) if done else None)}
    return out


def episode_rows(st: pd.Series, o: pd.DataFrame, L: pd.DataFrame, lines: tuple) -> dict:
    eps = episodes(st, "避险")
    rows = []
    for a, b in eps:
        on = [LINE_LABEL[k] for k in lines if bool(L[k].iloc[a])]
        rows.append({"start": str(st.index[a].date()), "end": str(st.index[b].date()), "days": b - a + 1, "lines": on,
                     "r20": _num(o["r20"].iloc[a]), "r60": _num(o["r60"].iloc[a]), "mdd60": _num(o["mdd60"].iloc[a])})
    done = [r for r in rows if r["r60"] is not None]
    return {"n": len(rows), "rows": rows,
            "r60_mean": (round(float(np.mean([r["r60"] for r in done])), 2) if done else None),
            "r60_pos": (round(float(np.mean([r["r60"] > 0 for r in done]) * 100), 1) if done else None),
            "mdd60_le10": (round(float(np.mean([r["mdd60"] <= -10 for r in done]) * 100), 1) if done else None)}


def _num(v) -> float | None:
    return (round(float(v), 2) if v is not None and np.isfinite(v) else None)


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/report_judgment_backtest.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:+.2f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def report(res: dict) -> str:
    MK = {"US": "美股（S&P500）", "JP": "日本（日经225）"}
    L = [f"# 市场风险报告的判断放到过去的指数里（登记检验；代码 {res['git']['rev']}{' + 未提交的改动' if res['git']['dirty'] else ''}）",
         "规则见 scripts/report_judgment_backtest.py 开头（先提交、只运行一次）。把报告的红线换成「当时的相对阈值」，每天重现「行动四选一」，看之后的走势。"
         "数据到：" + "、".join(f"{k} {v}" for k, v in res["ends"].items()) + "；Yahoo 日线漏掉、用 5 分钟线补的日子："
         + (json.dumps(res.get("filled"), ensure_ascii=False) if res.get("filled") else "无") + "。非投资建议。", ""]
    L += ["## 一、判定（事先写定）", ""]
    for m in ("US", "JP"):
        v = res["markets"][m]["verdict"]
        L.append(f"- **{MK[m]}**：V1 方向（避险之后 20 日更差）{v['V1']}（满足的年代 {('、'.join(v.get('V1_eras') or []) or '无')}）；"
                 f"V2 风险（20 日内跌 5% 更常见）{v['V2']}（{('、'.join(v.get('V2_eras') or []) or '无')}）；"
                 f"V3 照着做（避险 0% / 减仓 50%）{v['V3']}（Calmar 高 0.05 以上的年代 {('、'.join(v.get('V3_eras') or []) or '无')}）；能判的年代 {('、'.join(v['eras']) or '无')}")
    L.append("")
    for m in ("US", "JP"):
        L.append(f"- 24h 崩盘概率（{MK[m]}）：" + "；".join(
            f"{s} 报告平均 {_f(c['report_mean'], '{:.1f}')}%（{c['n_reports']} 期）vs 历史同一状态 {_f(c['hist']['est'], '{:.2f}')}%"
            f"（95% 区间 {_f(c['hist']['lo'], '{:.2f}')}〜{_f(c['hist']['hi'], '{:.2f}')}%，{c['hist']['n']} 天）→ {c['verdict'] or '—'}"
            for s, c in res["calib"][m].items()))
    L += ["", "## 二、各状态之后的走势（全期与各年代；次日崩盘 = 次日盘中或收盘 ≤ −3%）", ""]
    for m in ("US", "JP"):
        L += [f"### {MK[m]}", "", "| 年代 | 状态 | 天数 | 次日崩盘 % | 5 日 % | 20 日 %（中位 / >0 %） | 60 日 % | 20 日内跌 5% | 60 日内跌 10% |", "|---|---|---|---|---|---|---|---|---|"]
        rows = [("全期", res["markets"][m]["full"]["tab"])] + [(ERA_LABEL[e], res["markets"][m]["by_era"][e]["tab"]) for e in ERAS]
        for nm, tab in rows:
            for s in STATES:
                d = tab[s]
                if not d["n"]:
                    continue
                L.append(f"| {nm} | {s} | {d['n']} | {_f(d.get('crash1'), '{:.2f}')} | {_f(d.get('r5'))} | {_f(d.get('r20'))}（{_f(d.get('r20_med'))} / {_f(d.get('r20_pos'), '{:.0f}')}）"
                         f" | {_f(d.get('r60'))} | {_f(d.get('dd20'), '{:.1f}')}% | {_f(d.get('dd60'), '{:.1f}')}% |")
        f = res["markets"][m]["full"]
        L += ["", f"全期 避险 − 观望：20 日收益差 {_f(f['diff20']['est'])} pp（95% 区间 {_f(f['diff20']['lo'])}〜{_f(f['diff20']['hi'])}）；"
              f"「20 日内跌 5%」比值 {_f(f['ratio20']['est'], '{:.2f}')} 倍（{_f(f['ratio20']['lo'], '{:.2f}')}〜{_f(f['ratio20']['hi'], '{:.2f}')}）。各年代："
              + "；".join(f"{e} {_f(res['markets'][m]['by_era'][e]['diff20']['est'])} pp / {_f(res['markets'][m]['by_era'][e]['ratio20']['est'], '{:.2f}')} 倍" for e in ERAS), ""]
    L += ["## 三、照着做（避险 0%、减仓观察 50%、其余 100%）vs 一直拿着（年化 % / 最大回撤 % / Calmar）", "",
          "| 市场 | 年代 | 照着做 | 一直拿着 | 避险 / 减仓观察 占的天数 % |", "|---|---|---|---|---|"]
    for m in ("US", "JP"):
        for k in list(ERAS) + ["FULL"]:
            s = res["markets"][m]["strat"].get(k)
            if not s:
                continue
            c = lambda x: f"{_f(x['cagr'], '{:.2f}')} / {_f(x['mdd'], '{:.1f}')} / {_f(x['calmar'], '{:.3f}')}"  # noqa: E731
            L.append(f"| {MK[m]} | {ERA_LABEL.get(k, '全期')} | {c(s['E1'])} | {c(s['BH'])} | {s['share']['避险']} / {s['share']['减仓观察']} |")
        L.append(f"| {MK[m]} | 安慰剂（状态循环平移 {PLACEBO_SEEDS} 次）| Calmar 中位 {_f(res['markets'][m]['pl_med'], '{:.3f}')} / 95 分位 {_f(res['markets'][m]['pl95'], '{:.3f}')} | | |")
    L += ["", "## 四、报告这 27 期的实际结果（下一个交易时段有没有 −3%；之后 5 个交易日；本研究同一时点的重现状态）", "",
          "| 报告 | 行动 | 美股崩盘概率 → 实际 | 日本崩盘概率 → 实际 | S&P 5 日 % | 日经 5 日 % | 重现（美 / 日 → 总） |", "|---|---|---|---|---|---|---|"]
    for r in res["reports"]:
        L.append(f"| {r['when'][5:]} {r['kind']} | {r['act']} | {r['us_p']}% → {('是' if r.get('us_crash') else '否') if r.get('us_crash') is not None else '—'}"
                 f"（{_f(r.get('us_next'))}%） | {r['jp_p']}% → {('是' if r.get('jp_crash') else '否') if r.get('jp_crash') is not None else '—'}（{_f(r.get('jp_next'))}%）"
                 f" | {_f(r.get('us_r5'))} | {_f(r.get('jp_r5'))} | {r.get('us_proxy') or '—'} / {r.get('jp_proxy') or '—'} → {r.get('proxy') or '—'} |")
    fi = res["fidelity"]
    uc = [r for r in res["reports"] if r.get("us_crash") is not None]
    jc = [r for r in res["reports"] if r.get("jp_crash") is not None]
    L += ["", f"合计：美股 报告概率之和 {sum(r['us_p'] for r in uc) / 100:.2f} 次 vs 实际 {sum(r['us_crash'] for r in uc)} 次（{len(uc)} 期）；"
          f"日本 {sum(r['jp_p'] for r in jc) / 100:.2f} 次 vs 实际 {sum(r['jp_crash'] for r in jc)} 次（{len(jc)} 期）。"
          f"（早报与晚报常指向同一个交易时段 → 不是独立的 27 次。）重现的总行动与报告一致 {fi['same']} / {fi['n']} 期。", ""]
    nw = res["now"]
    L += ["## 五、现在（数据最后一天）与历史上相似的局面（只描述）", "",
          f"- 美股 {nw['US']['date']}：重现 = {nw['US']['state']}；红线 " + "、".join(f"{LINE_LABEL[k]}{'●' if v else '○'}" for k, v in nw['US']['lines'].items())
          + f"（广度数据到 {nw['US'].get('breadth_date')}：{_f(nw['US'].get('breadth_last'), '{:.1f}')}%）",
          f"- 日本 {nw['JP']['date']}：重现 = {nw['JP']['state']}；红线 " + "、".join(f"{LINE_LABEL[k]}{'●' if v else '○'}" for k, v in nw['JP']['lines'].items()),
          f"- 总行动（东证 {nw['ALL']['date']}）：{nw['ALL']['state']}", ""]
    for m, txt in (("US", "利率红线亮 + S&P 在 252 日最高的 3% 以内 + VIX < 20"), ("JP", "日元在 52 周最弱附近 + 日经在 252 日最高的 3% 以内")):
        a = res["analog"][m]
        L.append(f"- 相似局面（{MK[m]}：{txt}）：{a['n_days']} 天、{a['n_episodes']} 段；每段第一天之后 20 日平均 {_f(a['r20_mean'])}%、"
                 f"60 日平均 {_f(a['r60_mean'])}%（> 0 的 {_f(a['r60_pos'], '{:.0f}')}%）、60 日内跌 10% 的 {_f(a['mdd60_le10'], '{:.0f}')}%")
        if a["rows"]:
            L.append("  - " + "；".join(f"{r['date']} {_f(r['r20'])} / {_f(r['r60'])}%" for r in a["rows"][-40:])
                     + ("（只列最近 40 段，全部在 JSON）" if len(a["rows"]) > 40 else ""))
    L += ["", "## 六、历史上的避险段（≥ 5 天；第一天之后 20 / 60 日 %、60 日内最深 %；只描述）", ""]
    for m in ("US", "JP"):
        ep = res["episodes"][m]
        L.append(f"- {MK[m]}：{ep['n']} 段；60 日平均 {_f(ep['r60_mean'])}%（> 0 的 {_f(ep['r60_pos'], '{:.0f}')}%）、60 日内跌 10% 的 {_f(ep['mdd60_le10'], '{:.0f}')}%")
        if ep["rows"]:
            L.append("  - " + "；".join(f"{r['start']}〜{r['end']}（{r['days']} 天，{'+'.join(r['lines'])}）{_f(r['r20'])} / {_f(r['r60'])} / {_f(r['mdd60'], '{:.1f}')}"
                                         for r in ep["rows"][-40:]) + ("（只列最近 40 段，全部在 JSON）" if ep["n"] > 40 else ""))
    L += ["", f"另报：纳指（美国状态）避险之后 20 日 {_f(res['ndx']['避险'].get('r20'))}% vs 观望 {_f(res['ndx']['观望'].get('r20'))}%；"
          f"总行动（东证日历）日经 避险 20 日 {_f(res['all_jp']['避险'].get('r20'))}% vs 观望 {_f(res['all_jp']['观望'].get('r20'))}%。",
          "", "登记前个数（各年代各状态天数）：" + json.dumps(res["counts"], ensure_ascii=False), "", f"用时 {res.get('elapsed_s')} s。非投资建议。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prep", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from qbreak import paths
    if a.prep:
        B = build(load_inputs())
        c = counts(B)
        print(json.dumps(c, ensure_ascii=False, indent=1))
        print(json.dumps(B["ends"], ensure_ascii=False), json.dumps(B["filled"], ensure_ascii=False))
        return 0
    res = run()
    out = paths.PROJECT_ROOT / "var" / "out"
    (out / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")   # 先存数字
    (out / OUT_MD).write_text(report(res), encoding="utf-8")
    print(f"→ {out / OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
