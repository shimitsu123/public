"""equity_idle_study.py — 闲置资金换成比 1655 收益更高的股票类 ETF（A 段）+ 预计下跌时拿反向 ETF（B 段）
（2026-09-29 登记；先提交后只跑一次，看完不改规则）。

用户（2026-09-29）：「闲置资金改为比1655收益更高的股票类别进行研究 / 预计会下跌的时候要选择反向型的股票进行研究」。
背景：模拟盘的闲置资金 2026-09-30 起是 K3（133A 美元趋势；scripts/idle_cash_study.py 选中：比原规则稳，但年化 E / J 少 4.54 / 11.10 pp）；
  个股层平均只占 5〜7% 的资金（leap_r12 C 部分）→ 账户的收益与回撤几乎全由闲置资金决定。
已经看过的（照实写 —— 本研究对它们不是「没看过的检验」）：
  ① 纳指当核心（ndx_study，登记 ed1f43c）：E / J 两段组合都比 1655 好（旧设定 S0C2：Calmar E 0.386 vs 0.217、J 0.511 vs 0.372），
     但登记的主判定 1987〜2005（只有核心）最大回撤深 7.1 pp → 不通过；1929〜1986 的科技代理更差（core_mix_study）；
     用户 ㉔（2026-09-28）：核心现在不换纳指，2026-12-24 和模拟期总结一起定。这次用户明确要「比 1655 收益更高」→ 按这次的要求做。
  ② 美股熊市买 S&P500 反向 2238、牛市现金（idle_cash_study K5）：E / J 年化 −1.12% / −3.78%（熊市段拿反向是亏的）。
  ③ 美股熊市换黄金 / 美国长债（refuge_study）：不通过（对拿日元的人，危机时日元本身是避险资产）。
立花 ｅ支店能买的（东证上市 ETF 现物；2026-09-29 查 JPX「ETF 一覧」「レバレッジ型・インバース型 ETF 一覧」与 2026-06〜08 売買代金，
仅对检索时点有效；信託報酬写的是 JPX 一览的数，按税抜 × 1.1 算税込）：
  Q1 纳斯达克 100 1545（NEXT FUNDS、不对冲、0.20% 以内、2010-08 上市、一手 10 口、2026-08 立会内日均约 7.9 億円）
  Q2 美国半导体 SOX 2243（Global X、费城半导体指数・配当込み・円換算、不对冲、0.375% 以内、2023-04、1 口、约 11.2 億円）
  Q3 纳指 2 倍 2869（iFreeETF NASDAQ100 レバレッジ、先物型、0.75% 以内、2022-11、1 口、约 4.1 億円）
  Q4 日经 225 1321（NEXT FUNDS、日経平均トータルリターン、0.0817%、2001-07、1 口、约 178 億円）
  Q5 日经 2 倍 1570（NEXT FUNDS 日経レバレッジ、先物型、0.8% 以内、2012-04、1 口、约 1,696 億円）
  Q6 印度 Nifty 50 1678（NEXT FUNDS、税引後配当込み、不对冲、0.95%、2009-11、10 口、约 1.35 億円）
  反向：2238 S&P500（0.73% 以内、约 0.45 億円）、2842 纳指（0.75% 以内、约 0.93 億円）、1571 日经（0.8% 以内、约 2.27 億円）；
    东证没有 SOX 反向 → SOX 用纳指反向 2842；没有印度反向 → Q6 不做 B 段。都用 −1 倍（−2 倍的每日重置损耗更大，不试）。
  不放进来：FANG+ 316A（2025-01 上市）、US テック・トップ20 2244（2023-04）、日经半导体 200A（2024-06）、日本半导体 2644（2021-09）
    —— 指数的公开历史够不到 E 段；S&P500 2 倍 2239（2023-03，立会内日均约 0.28 億円，太薄）；MAXIS 纳指 2631（与 1545 同一指数，一口 3 万円多）。
零 对照：K0 原规则（1655：2017-09-26 以后真实价、以前 = 回测框架的代理 ^GSPC × 前一天汇率 + 年 1.3% 股息估计；+ 美股牛熊分界；
   回测框架缺省）；S0 同一做法合成的 1655（S&P500 总收益 × USD/JPY − 0.066%）；
   K3 模拟盘现在（与 idle_cash_study 同一段代码）。
一 账户：与 idle_cash_study 相同（S0C2 + W2：日経225 突破 4 个名额 × 25%、离场 X6、新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜、
   立花个别コース、当时真实的一手）；只换闲置资金。前向记录判断层与 HALT 没有历史，不在里面。
   窗口 E 2006-10〜2016-09、J 2017-01〜（判定）；Z 2001〜2006-09 只描述。
二 资产的日元价（全程合成，东证交易日 d；最后按 2026-08-31 的真实收盘定价格水平 → 一手的粒度与现在一致）：
   美国指数的 = 前一个美国收盘 × d 日早上的 USD/JPY（与 1655 上市前的合成、idle_cash_study 同一做法）：
     ★ 2026-10-03 起（用户 ㊼ ①；scripts/fx_timing_audit.py）：「d 日早上的 USD/JPY」= d 当天（含）以前最近的 Yahoo「JPY=X」值
       （它标成 d 日的值 ≈ d 日东京早上、开盘前；fx_on）。以前的代码用的是 d 之前（不含 d）的值 ≈ d − 1 日早上，比这里写的旧约一天
       → 用纽约中午 DEXJPUS 做信号的汇率择时在回测里会提前看到汇率变动。环境变量 QB_FX_ALIGN=prev 可以重现以前的结果。
     S0 1655 = ^SP500TR − 年 0.066%；Q1 1545 = 纳指总收益 − 0.22%，纳指总收益 = QQQ 复权价加回它的年 0.20% 费用；
     Q2 2243 = ^SOX × 年 0.8% 股息估计（SOXX 2001〜2026 分配的平均）− 0.4125%；
     Q3 2869 = 每日重置 2 × (纳指总收益 − 美国 3 个月国库券) + 日本无担保拆借（担保金的利息）− 0.825%，不乘汇率
       （先物型：汇率只作用在当天盈亏上；实测 2869 周收益对 USD/JPY 的系数 0.18）；
     反向 2238 / 2842 = −1 × (S&P500 / 纳指 总收益 − 美国 3 个月国库券) + 日本拆借 − 0.803% / 0.825%，不乘汇率。
   日经的 = 当天的日经（开盘价也用日经的开盘）：Q4 1321 = ^N225 × 年 1.6% 股息估计（与 1329 的合成同一个数）− 0.0817%；
     Q5 1570 = 每日重置 2 × 日经总收益 − 日本拆借 − 0.88%；1571 = −1 × 日经总收益 + 2 × 日本拆借 − 0.88%；
     开盘价 = 前一天收盘 × (1 + 倍数 × (日经开盘 ÷ 日经前一天收盘 − 1))。
   Q6 1678 = Nifty 50（2007-09-17 以前用 SENSEX 按那天接上）× 年 1.1% 税后股息估计 × JPY/INR（USD/JPY ÷ FRED DEXINUS）− 1.045%，
     取前一个印度收盘（印度 15:30 IST = 日本 19:00 收盘）。
   USD/JPY = Yahoo JPY=X；「单日动 > 3% 然后反方向 > 3%」且与同一天 FRED DEXJPUS 差 > 4% 的错价换成 FRED 的值
     （2008-04-08 / 05-08 / 10-08 / 12-08 四天；回测框架里 K0 的 1655 上市前合成不改 —— 这四天美股都是熊、K0 空仓）。
   反向 ETF（2238 / 2842 / 1571）的价格水平按窗口定：每个窗口第一天的价 = 它 2026-08-31 的真实收盘（真实的反向 ETF 会合并受益权；
     按 2026-08 定水平的话 2842 在 2006〜2016 一口要 11〜82 万円，¥100 万的账户最多买一口）。股票类 / 两倍照上面按 2026-08-31 定。
   利率：美国 FRED DTB3（按 360 天）；日本 FRED IRSTCI01JPM156N 无担保翌日物（月度平均，按那个月当月计息，1985-07 以前当 0；
     只影响合成价的净值，不进任何判断，差别 < 0.01 pp / 年）。
   滑点 / 一手（登记进 qbreak/fees.py；半个呼値 + 按成交额的冲击）：1545 0.03% / 10 口、2243 0.06% / 1、2869 0.05% / 1、1321 0.08% / 1、
     1570 0.08% / 1、1678 0.05% / 10、2842 0.10% / 1、1571 0.20% / 1、2238 0.20% / 1（上一轮已登记）。
   登记前的数据核对（只核对合成价本身，没有算任何账户结果；yfinance 的 ETF 行情有没调整的分割，去掉那几行）：
     合成 − 真实 的年化差：1655 −0.11 pp（9.0 年）、1545 +0.93（16.1 年）、2243 +1.14（3.5 年）、2869 +1.61（3.9 年）、1321 +0.19（17.7 年）、
     1570 +0.61（14.5 年）、1678 +1.13（16.8 年）、2238 +0.03（3.7 年）、2842 −0.98（4.7 年）、1571 +0.37（14.5 年）；月收益相关 0.92〜0.998。
     → 股票类的合成价比真实 ETF 乐观约 0〜1.6 pp / 年，S0 与真实 1655 几乎一样 → A 段的收益门槛 = max(1.0, 该候选的「合成 − 真实」)：
     Q1 1.0、Q2 1.14、Q3 1.61、Q4 1.0、Q5 1.0、Q6 1.13 pp（运行时会再报一次核对，门槛不随之改）；2842 的合成比真实悲观 0.98 pp / 年
     → 对 Q1〜Q3 上的 B 段略不利（照实写）。
三 牛熊（不加新参数）：美国指数的 Q1〜Q3 → 美股牛熊分界（S&P500，现行）；日经的 Q4 / Q5 → 日本牛熊分界（日经 225，现行）；
   印度 Q6 → 同一个检测器、同一组参数用在印度指数（卢比计）上（键 T0:IN）。熊 → 那部分留现金（与原规则相同）。
四 A 段「比 1655 收益更高」的选择（事先写定）：
   入围（E、J 两段都要）：(a) 年化 ≥ max(K0, S0) + 该候选的门槛（二）；(b) 最大回撤比 max(K0, S0)（两者较浅的那个）深不超过 2 pp
   （恰好 2.00 pp 算过）
   （2 pp = 以前核心研究 ndx_study / dualmom_study 的同一个门槛）。
   入围的里面 min(E 的 Calmar, J 的 Calmar) 最大的入选；与最大的相差 < 0.02 → E、J 年化平均高的，再编号小的。都不入围 → A 段没有。
五 B 段「预计下跌 → 反向 ETF」（qbreak/idle_cash.py 的 overlay_on / overlay_keys，同一次提交写定）：
   底 = A 段入选的；A 段没有 → S0（合成 1655 + 2238；1655 与 2238 用同一个 S&P500 总收益，口径一致）。S0 上的四个另外都跑
   （底不是 S0 时只描述）。
   那天收盘时（美国的读数 = 那天的美国收盘，东证第二天开盘前已知，与现行美股牛熊分界同一个时点）：
     P1 底的牛熊分界 = 熊 → 反向；P2 威胁指数 A0（qbreak/threat.py v1；美国的底用美国、日经的底用日经）在自身历史的百分位 ≥ 80 → 反向
     （牛市也换）；P3 C_rel（威胁高 + 压力已释放，qbreak/fwd_judgment.crel_series）百分位 ≥ 80 → 反向；
     P4 熊 且（A0 或 C_rel ≥ 80）→ 反向（熊但没有警示 → 现金）。其余 = 底（牛 → 股票 ETF、熊 → 现金）。第二天开盘换，每天判断。
   采用（E、J 两段都要，与底比）：年化不低、Calmar 高 ≥ 0.02、最大回撤深不超过 2 pp；几个都过 → min(E, J 的 Calmar 提高) 最大的，
   相差 < 0.02（不四舍五入）→ 编号小的。
六 模拟盘怎么改（按用户这次的要求，事先写定；基准账户照旧原规则 = K0、死叉、不加判断层）：
   A 段有入选 → 闲置资金 = 入选的（+ B 段采用的反向规则），结果推送后的下一个决策日起；现在的 133A 下一次决策全部卖掉。
   A 段没有、B 段在 S0 上有采用、而且那个方式 E、J 的年化都 ≥ max(K0, S0) + 1.0 pp → 闲置资金 = 1655 + 那个反向规则
   （只是「不低于」而没有高 1 pp → 不换，只报告）。
   都没有 → 模拟盘不变（K3），汇报「历史上股票类里没有收益高 1 pp 以上且回撤不更深的」，回到 K0 或选别的由用户决定。
   Q6（印度指数）与 P2〜P4（每天的威胁指数 / C_rel）要在 sim-day 与执行器里另接数据：入选后先实现、测试、演练，之前模拟盘不变
   （美国 A0 用的 FRED VIX 当天的值 06:57 JST 还没公布 → 实时会晚一天，实现时处理）。
七 另报（只描述，不参与选择）：Z 窗口；各方式拿股票 / 反向 / 现金的交易日比例、B 段每年换仓次数；各年收益；
   只有核心的长历史（日元、牛熊同上、熊市现金、每次换仓 0.1%）：S&P500 / 纳指 / 纳指 2 倍 / 日经 / 日经 2 倍 1987〜、SOX 1995〜、印度 1998〜
   的年化、最大回撤、Calmar、最差 10 年年化、最差一年（汇率用 FRED DEXJPUS / DEXINUS；1999-03 以前纳指 = ^NDX + 年 0.6% 股息估计，
   1988 以前 S&P500 = ^GSPC + 年 3.5%）；合成价 vs 真实 ETF 的核对；现在（最新收盘）的牛熊、A0 / C_rel 读数与各方式现在会拿什么。
八 事前预期（照实写：① 让纳指的 E / J 结果大致已知）：A 段 Q1 纳指入选约 60%；Q2 SOX 回撤条件不过约 70%；Q3 / Q5 两倍回撤不过约 95%；
   Q4 日经、Q6 印度 年化条件不过各约 85%；A 段都没有约 30%。B 段：P1 不过约 85%（② 已知熊市段拿反向亏钱）；P2 / P3 不过约 80%；
   P4 不过约 75%；B 段都不采用约 70%。
九 照实写：这 20 年是美国科技股的大行情（纳指 / 半导体领先依赖时代：1929〜1986 的代理与 2000〜2002 是反例）；合成价比真实 ETF 乐观
   约 0〜1.6 pp / 年（门槛 +1.0 pp 已考虑）；只有两个判定窗口、几段熊市，样本小；杠杆 / 反向 ETF 每日重置，横盘时有损耗（已按日重置算）；
   A0 / C_rel 的百分位从 1990 年代中期起才有；美国 / 印度的合成价开盘 = 收盘 = 前一个外国收盘（与回测框架的做法相同），成交价就是
   触发信号的那个收盘，日经系按日经开盘成交 → 对美国 / 印度的候选略有利（A 段有同一做法的 S0 对照）；税前。非投资建议。
补正（2026-09-29，登记 c4ce05e 之后、运行之前；独立审计只读代码、核对数据，没有运行任何账户回测）：反向 ETF 的价格水平按窗口定、
USD/JPY 四个错价换成 FRED、A 段门槛按各候选的合成乐观度、B 段的底从 K0 改成 S0 且「A 段没有时换成 1655 + 反向」要年化高 1 pp 以上、
回撤「深不超过 2 pp」写明含等号、B 段同分比较不四舍五入、每个窗口重设退市表（以前只在建 runner 时设）、K0 的说明。
输出：var/out/equity_idle_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import exit_rules as EXR                                         # noqa: E402
from qbreak import idle_cash as IC                                           # noqa: E402
from qbreak import paths                                                     # noqa: E402

TAGS = ("E", "J", "Z")
JUDGE = ("E", "J")
QS = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")
PS = ("P1", "P2", "P3", "P4")
MARGIN, DD_TOL, TIE, GAIN = 1.0, 2.0, 0.02, 0.02
MARGIN_Q = {"Q1": 1.0, "Q2": 1.14, "Q3": 1.61, "Q4": 1.0, "Q5": 1.0, "Q6": 1.13}   # max(1.0, 合成 − 真实 的年化差)（二）
INV_T = ("2238.T", "2842.T", "1571.T")                                   # 价格水平按窗口定的反向 ETF
START = "2000-01-01"
REF_DATE = "2026-08-31"                                                      # 按这天的真实收盘定合成价的水平（JPX 2026-08 売買代金）
REF_PX = {"1655.T": 886.1, "1545.T": 237.0, "2243.T": 4382.0, "2869.T": 2940.0, "1321.T": 68630.0, "1570.T": 69690.0,
          "1678.T": 310.5, "2238.T": 5234.0, "2842.T": 12200.0, "1571.T": 296.0}
FEE = {"1655.T": 0.066, "1545.T": 0.22, "2243.T": 0.4125, "2869.T": 0.825, "1321.T": 0.0817, "1570.T": 0.88, "1678.T": 1.045,
       "2238.T": 0.803, "2842.T": 0.825, "1571.T": 0.88}                      # 年 %（税込）
QQQ_ER, SOX_DIV, N225_DIV, IN_DIV, NDX_DIV_PRE, SPX_DIV_PRE = 0.20, 0.8, 1.6, 1.1, 0.6, 3.5   # 年 %
SWITCH_COST = 0.1                                                            # 长历史（只有核心）每次换仓 %（与 ndx_study 同）
DESC = {"K0": "原规则 1655（2017-09 起真实价）+ 美股牛熊分界", "S0": "合成 1655（同一做法）+ 美股牛熊分界", "K3": "模拟盘现在：133A 美元趋势"}


# ───────────────────────── 合成的日元价格 ─────────────────────────
def prev_on(days: pd.DatetimeIndex, s: pd.Series) -> pd.Series:
    """东证交易日 d 的值 = d 之前最近的一个值（美国 / 印度的收盘在日本时间 d 的开盘前已知；d 当天的不用）。"""
    s = s.dropna().sort_index()
    return s.reindex(days.union(s.index)).ffill().shift(1).reindex(days)


def rate_on(idx: pd.DatetimeIndex, s: pd.Series | None) -> pd.Series:
    """年 % 的利率 → 每个日期（向前填；更早没有 = 0）。"""
    if s is None or not len(s.dropna()):
        return pd.Series(0.0, index=idx)
    s = s.dropna().sort_index()
    return s.reindex(idx.union(s.index)).ffill().reindex(idx).fillna(0.0)


def grow(s: pd.Series, pct: float) -> pd.Series:
    """× exp(pct% × 年数)：股息估计（+）、加回费用（+）、扣费用（−）。"""
    s = s.dropna().sort_index()
    yrs = (s.index - s.index[0]).days.to_numpy(float) / 365.25
    return s * np.exp(pct / 100 * yrs)


def lev(tr: pd.Series, mult: float, fin: pd.Series | None, cash: pd.Series | None, fee_pct: float,
        fin_basis: float = 360.0) -> pd.Series:
    """每日重置的先物型：r = 倍数 × (总收益日收益 − 融资利率 × 天数 / fin_basis) + 担保金利率 × 天数 / 365 − 费用 × 天数 / 365。
    利率用前一个观测日的（当天的不用）；净值不会小于 0。"""
    tr = tr.dropna().sort_index()
    r = tr.pct_change().fillna(0.0).to_numpy(float)
    dt = tr.index.to_series().diff().dt.days.fillna(0).to_numpy(float)
    f = rate_on(tr.index, fin).shift(1).fillna(0.0).to_numpy(float) / 100 * dt / fin_basis
    c = rate_on(tr.index, cash).shift(1).fillna(0.0).to_numpy(float) / 100 * dt / 365
    g = 1 + mult * (r - f) + c - fee_pct / 100 * dt / 365
    return pd.Series(np.cumprod(np.maximum(g, 0.0)), index=tr.index)


def jp_product(n225: pd.DataFrame, mult: float, fin: pd.Series | None, cash: pd.Series | None, fee_pct: float,
               div_pct: float = N225_DIV) -> pd.DataFrame:
    """日经系（1321 / 1570 / 1571）：收盘 = 日经总收益（年 div_pct% 股息估计）的每日重置 × 倍数（融资 / 担保金 = 日本拆借，按 365 天）；
    开盘 = 前一天合成收盘 × (1 + 倍数 × (日经开盘 ÷ 日经前一天收盘 − 1))（开盘没有值 → 当收盘）。"""
    c = n225["Close"].dropna()
    close = lev(grow(c, div_pct), mult, fin, cash, fee_pct, fin_basis=365.0)
    o = n225["Open"].reindex(c.index)
    gap = (o / c.shift(1) - 1).where(o > 0)
    open_ = (close.shift(1) * (1 + mult * gap)).fillna(close)
    return pd.DataFrame({"Open": open_, "Close": close}, index=c.index)


def scale(s: pd.Series | pd.DataFrame, ticker: str) -> pd.Series | pd.DataFrame:
    """按 REF_DATE（没有那天 → 之前最后一天）的真实收盘定价格水平。"""
    c = s["Close"] if isinstance(s, pd.DataFrame) else s
    c = c.dropna()
    ref = float(c[c.index <= pd.Timestamp(REF_DATE)].iloc[-1])
    return s * (REF_PX[ticker] / ref)


def frame_close(s: pd.Series) -> pd.DataFrame:
    """只有收盘的合成价 → 引擎用的 K 线（开盘 = 收盘；美国 / 印度的：东证 d 日开盘时已知的就是前一个收盘）。"""
    from qbreak.core import core_frame
    s = s.dropna()
    return core_frame(pd.DataFrame({"Open": s, "High": s, "Low": s, "Close": s, "Volume": 1e9}, index=s.index))


def frame_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    from qbreak.core import core_frame
    d = df.dropna(subset=["Close"]).copy()
    d["Open"] = d["Open"].fillna(d["Close"])
    d["High"], d["Low"], d["Volume"] = d[["Open", "Close"]].max(axis=1), d[["Open", "Close"]].min(axis=1), 1e9
    return core_frame(d[["Open", "High", "Low", "Close", "Volume"]])


# ───────────────────────── 数据 ─────────────────────────
def load_inputs() -> dict:
    from bullbear_study import SYM, load
    from qbreak import factors
    fx = load("JPY=X", START)["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    dexjp = factors.fred("DEXJPUS")
    fx, fixed = clean_fx(fx, dexjp)
    return {"fx": fx, "fx_fixed": fixed, "qqq": load("QQQ", "1999-01-01")["Close"], "ndx": load("^NDX", "1985-01-01")["Close"],
            "sox": load("^SOX", "1994-01-01")["Close"], "sptr": load("^SP500TR", "1988-01-01")["Close"],
            "spx": load(*SYM["US"]), "n225": load(*SYM["JP"]),
            "nse": load("^NSEI", "2007-01-01")["Close"], "bse": load("^BSESN", "1997-01-01")["Close"],
            "dtb3": factors.fred("DTB3"), "cjp": factors.fred("IRSTCI01JPM156N"),
            "dexjp": dexjp, "dexin": factors.fred("DEXINUS")}


def clean_fx(fx: pd.Series, ref: pd.Series, spike_pct: float = 3.0, gap_pct: float = 4.0) -> tuple[pd.Series, list[str]]:
    """Yahoo JPY=X 的错价：单日动 > spike_pct% 然后反方向 > spike_pct%，且与同一天 FRED DEXJPUS 差 > gap_pct% → 换成 FRED 那天的值。"""
    fx = fx.dropna().sort_index()
    r = ref.dropna().reindex(fx.index)
    ret = fx.pct_change() * 100
    nxt = ret.shift(-1)
    spike = (ret.abs() > spike_pct) & (nxt.abs() > spike_pct) & (np.sign(ret) != np.sign(nxt))
    bad = spike & r.notna() & ((fx / r - 1).abs() * 100 > gap_pct)
    out = fx.copy()
    out[bad] = r[bad]
    return out, [str(d.date()) for d in fx.index[bad.to_numpy(bool)]]


def chain(early: pd.Series, late: pd.Series) -> pd.Series:
    """late 从它的第一天起；之前用 early，按 late 首日（early 那天或之前最后一个值）接上。"""
    early, late = early.dropna().sort_index(), late.dropna().sort_index()
    first = late.index[0]
    pre = early[early.index < first]
    if not len(pre):
        return late
    k = float(late.iloc[0]) / float(early[early.index <= first].iloc[-1])
    return pd.concat([pre * k, late])


def ndx_tr(inp: dict) -> pd.Series:
    """纳指总收益：QQQ 复权价加回年 0.20% 费用；QQQ 以前（只有长历史用）= ^NDX + 年 0.6% 股息估计。"""
    return chain(grow(inp["ndx"], NDX_DIV_PRE), grow(inp["qqq"], QQQ_ER))


def spx_tr(inp: dict) -> pd.Series:
    """S&P500 总收益：^SP500TR；1988 以前（只有长历史用）= ^GSPC + 年 3.5% 股息估计。"""
    return chain(grow(inp["spx"]["Close"], SPX_DIV_PRE), inp["sptr"])


def india_index(inp: dict) -> pd.Series:
    """Nifty 50（卢比）；2007-09-17 以前用 SENSEX 按那天接上。"""
    return chain(inp["bse"], inp["nse"])


def jpy_per(fx_usdjpy: pd.Series, per_usd: pd.Series) -> pd.Series:
    """1 单位外币的日元价 = USD/JPY ÷（外币 / USD）；两边各自向前填。"""
    idx = fx_usdjpy.dropna().index.union(per_usd.dropna().index)
    return (fx_usdjpy.dropna().reindex(idx).ffill() / per_usd.dropna().reindex(idx).ffill()).dropna()


FX_ALIGN_ENV = "QB_FX_ALIGN"                                                 # "prev" = 2026-10-03 以前的口径（只为重现以前的结果）


def fx_align() -> str:
    """换汇的时点：「same」（缺省，2026-10-03 起）/「prev」（以前的口径）。"""
    return "prev" if os.environ.get(FX_ALIGN_ENV, "").strip().lower() == "prev" else "same"


def fx_on(days: pd.DatetimeIndex, fx: pd.Series) -> pd.Series:
    """东证交易日 d 换汇用的 USD/JPY = d 当天（含）以前最近的 Yahoo「JPY=X」值（它标成 d 日的值 ≈ d 日东京早上、开盘前）。
    2026-10-03 用户 ㊼ ① 起的研究口径（scripts/fx_timing_audit.py）；QB_FX_ALIGN=prev → 以前的口径（d 之前、不含 d，比实际旧约一天）。"""
    if fx_align() == "prev":
        return prev_on(days, fx)
    f = fx.dropna().sort_index()
    days = pd.DatetimeIndex(days)
    return f.reindex(days.union(f.index)).ffill().reindex(days)


def inr_on(days: pd.DatetimeIndex, fx: pd.Series, dexin: pd.Series) -> pd.Series:
    """东证交易日 d 的 1 卢比日元价：USD/JPY 用 fx_on（d 日早上）、USD/INR（FRED DEXINUS = 纽约中午）用 d 之前最近的。
    QB_FX_ALIGN=prev → 以前的口径（两者合成之后取 d 之前的）。"""
    if fx_align() == "prev":
        return prev_on(days, jpy_per(fx, dexin))
    return fx_on(days, fx) / prev_on(days, dexin)


def on_jp(s: pd.Series, fx: pd.Series | None, days: pd.DatetimeIndex) -> pd.Series:
    """东证交易日 d 的日元价 = 前一个（美国 / 印度）收盘 × 东证 d 日开盘前的 USD/JPY（fx_on；2026-10-03 起）。"""
    v = prev_on(days, s)
    if fx is not None:
        v = v * fx_on(days, fx)
    return v.dropna()


def asset_closes(inp: dict) -> dict[str, pd.Series | pd.DataFrame]:
    """东证交易日上的合成价（未定水平）：美国 / 印度的 = 收盘序列；日经系 = DataFrame(Open, Close)。"""
    n225 = inp["n225"]
    days = n225.index[n225.index >= START]
    fx, dtb3, cjp = inp["fx"], inp["dtb3"], inp["cjp"]
    ntr, sptr = ndx_tr(inp), inp["sptr"]
    out: dict = {
        "1655.T": on_jp(grow(sptr, -FEE["1655.T"]), fx, days),
        "1545.T": on_jp(grow(ntr, -FEE["1545.T"]), fx, days),
        "2243.T": on_jp(grow(grow(inp["sox"], SOX_DIV), -FEE["2243.T"]), fx, days),
        "2869.T": on_jp(lev(ntr, 2.0, dtb3, cjp, FEE["2869.T"]), None, days),
        "2238.T": on_jp(lev(sptr, -1.0, dtb3, cjp, FEE["2238.T"]), None, days),
        "2842.T": on_jp(lev(ntr, -1.0, dtb3, cjp, FEE["2842.T"]), None, days),
        "1678.T": (prev_on(days, grow(grow(india_index(inp), IN_DIV), -FEE["1678.T"]))
                   * inr_on(days, fx, inp["dexin"])).dropna(),
    }
    for t, m in (("1321.T", 1.0), ("1570.T", 2.0), ("1571.T", -1.0)):
        f = jp_product(n225, m, None if m == 1.0 else cjp, None if m == 1.0 else cjp, FEE[t])
        out[t] = f[f.index >= START]
    return out


def assets(inp: dict) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series]]:
    """({票: 引擎用的 K 线}, {票: 定好水平的收盘})。"""
    raw = asset_closes(inp)
    fr, cl = {}, {}
    for t, s in raw.items():
        s = scale(s, t)
        fr[t] = frame_ohlc(s) if isinstance(s, pd.DataFrame) else frame_close(s)
        cl[t] = fr[t]["Close"]
    return fr, cl


# ───────────────────────── 信号 ─────────────────────────
def t0_bear(close: pd.Series) -> pd.Series:
    """现行牛熊分界（qbreak/bullbear 的检测器与参数，同回测框架）：True = 熊。"""
    from qbreak.bullbear import BEAR, Detector, load_config
    d = load_config()["detector"]
    c = close.dropna()
    return pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(c)) == BEAR, index=c.index)


def bears(inp: dict) -> dict[str, pd.Series]:
    return {"US": t0_bear(inp["spx"]["Close"]), "JP": t0_bear(inp["n225"]["Close"]), "IN": t0_bear(india_index(inp))}


def warnings_hist() -> dict[str, dict[str, pd.Series]]:
    """{"US" / "JP": {"a0_pct", "crel_pct"}}：威胁指数 v1 与 C_rel 在自身历史里的百分位（前向记录 / 日报同一套函数）。"""
    from qbreak import fwd_judgment as FJ
    from qbreak import threat as TH
    d = TH.load_inputs()
    B = TH.build(d)
    out = {}
    for m, close in (("US", d["spx"]), ("JP", d["n225"])):
        a0 = B[m][0]
        cr = FJ.crel_series(close, a0)
        out[m] = {"a0_pct": FJ.own_pct(a0).dropna(), "crel_pct": cr["C_rel_pct"].dropna()}
    return out


# ───────────────────────── 方式 → 回测框架的参数 ─────────────────────────
def spec_a(k: str, fr: dict, bear: dict) -> dict:
    """K0 = 缺省（真实 1655）；S0 = 合成 1655 换掉真实的；Q1〜Q6 = qbreak/idle_cash.py 的设定 + 合成价。"""
    if k == "K0":
        return {}
    if k == "S0":
        return {"cfg_over": {"core": {"1655.T": 1.0}, "core_index": {"1655.T": "US"}, "core_mode": "split"},
                "extra_core": {"1655.T": fr["1655.T"]}}
    m = IC.MODES[k]
    t = next(iter(m["core"]))
    return {"cfg_over": {"core": dict(m["core"]), "core_index": dict(m["core_index"]), "core_mode": m["core_mode"]},
            "extra_core": {t: fr[t]}, "extra_bear": ({"T0:IN": bear["IN"]} if k == "Q6" else {})}


def spec_k3() -> dict:
    """模拟盘现在的 K3：与 idle_cash_study 同一段代码（133A 合成价 + 10 个月线开关）。"""
    import idle_cash_study as ICS
    return ICS.spec("K3", ICS.assets(ICS.load_inputs()), {})


def spec_b(base: str, variant: str, fr: dict, bear: dict, warn: dict) -> dict:
    """底 + 反向规则：follow 模式，键 EQ / IV（qbreak/idle_cash.overlay_keys）。底 = S0 → 合成 1655 + 2238（实时 = K0 的 1655 + 2238）。"""
    mode = "K0" if base == "S0" else base
    cfg = IC.overlay_cfg(mode)
    eq, inv = list(cfg["core"])
    m = IC.EQ_MARKET[mode]
    w = warn.get(m) or {}
    keys = IC.overlay_keys(variant, bear[m], w.get("a0_pct"), w.get("crel_pct"))
    return {"cfg_over": cfg, "extra_core": {eq: fr[eq], inv: fr[inv]}, "extra_bear": keys}


def level_at(sp: dict, start: str) -> dict:
    """反向 ETF 的价格水平按窗口定：窗口第一天（或之前最后一天）的价 = REF_PX（二）；其余不动。"""
    xc = sp.get("extra_core") or {}
    if not any(t in xc for t in INV_T):
        return sp
    xc2 = dict(xc)
    for t in INV_T:
        if t in xc2:
            df = xc2[t]
            k = REF_PX[t] / float(df["Close"].asof(pd.Timestamp(start)))
            xc2[t] = df.assign(**{c: df[c] * k for c in ("Open", "High", "Low", "Close")})
    return {**sp, "extra_core": xc2}


def _key_series(key: str, bear: dict, extra: dict) -> pd.Series | None:
    if key in extra:
        return extra[key]
    if key in ("US", "JP"):
        return bear[key]
    if key == "XR":
        return ~bear["US"]
    return None


def held_share(sp: dict, bear: dict, days: pd.DatetimeIndex, a: str, b: str | None) -> dict[str, float]:
    """窗口里各 ETF「开着」（引擎目标 > 0）的交易日比例（%）；其余 = 现金。K0 = 美股不是熊的日子。"""
    w = days[(days >= pd.Timestamp(a)) & ((days <= pd.Timestamp(b)) if b else True)]
    if not len(w):
        return {}
    co = (sp.get("cfg_over") or {"core": {"1655.T": 1.0}, "core_index": {"1655.T": "US"}})
    out = {}
    for t, key in co["core_index"].items():
        if not co["core"].get(t):
            continue
        s = _key_series(key, bear, sp.get("extra_bear") or {})
        if s is None:
            out[t] = 0.0
            continue
        f = s.astype(float).reindex(w.union(s.index)).ffill().reindex(w).fillna(0.0) > 0.5   # 没有值 = 引擎的做法（不算熊）
        out[t] = round(float((~f).mean() * 100), 1)
    return out


def switches_per_year(sp: dict, days: pd.DatetimeIndex, a: str, b: str | None) -> float | None:
    """B 段：每天的状态（股票 / 反向 / 现金）一年变几次。"""
    xb = sp.get("extra_bear") or {}
    if "EQ" not in xb or "IV" not in xb:
        return None
    w = days[(days >= pd.Timestamp(a)) & ((days <= pd.Timestamp(b)) if b else True)]
    if len(w) < 2:
        return None
    eq = xb["EQ"].astype(float).reindex(w.union(xb["EQ"].index)).ffill().reindex(w).fillna(0.0) > 0.5
    iv = xb["IV"].astype(float).reindex(w.union(xb["IV"].index)).ffill().reindex(w).fillna(0.0) > 0.5
    state = np.where(~iv, 2, np.where(~eq, 1, 0))
    yrs = (w[-1] - w[0]).days / 365.25
    return round(float((np.diff(state) != 0).sum() / yrs), 1) if yrs > 0 else None


# ───────────────────────── 选择（事先写定） ─────────────────────────
def _ok(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and bool(np.isfinite(v))


def qualifies(acct: dict, k: str) -> tuple[bool, list[str]]:
    """A 段入围：E、J 都要 年化 ≥ max(K0, S0) + 该候选的门槛（MARGIN_Q），最大回撤比 max(K0, S0) 深不超过 2 pp。返回 (是否入围, 不过的条件)。"""
    why, mg = [], MARGIN_Q.get(k, MARGIN)
    for t in JUDGE:
        v, r0, s0 = acct[t].get(k, {}), acct[t]["K0"], acct[t]["S0"]
        if not all(_ok(x) for x in (v.get("cagr"), v.get("dd"), r0["cagr"], s0["cagr"], r0["dd"], s0["dd"])):
            why.append(f"{t} 没有值")
            continue
        if v["cagr"] < max(r0["cagr"], s0["cagr"]) + mg - 1e-9:
            why.append(f"{t} 年化")
        if v["dd"] < max(r0["dd"], s0["dd"]) - DD_TOL - 1e-9:
            why.append(f"{t} 回撤")
    return not why, why


def pick_a(acct: dict) -> tuple[str | None, dict]:
    """入围的里面 min(E, J 的 Calmar) 最大；相差 < 0.02 → E、J 年化平均高的，再编号小的。"""
    q = {k: qualifies(acct, k) for k in QS if all(k in acct[t] for t in JUDGE)}
    ok = [k for k in QS if k in q and q[k][0] and all(_ok(acct[t][k].get("calmar")) for t in JUDGE)]
    if not ok:
        return None, q
    score = {k: min(acct[t][k]["calmar"] for t in JUDGE) for k in ok}
    best = max(score.values())
    near = [k for k in ok if best - score[k] < TIE - 1e-12]
    near.sort(key=lambda k: (-float(np.mean([acct[t][k]["cagr"] for t in JUDGE])), QS.index(k)))
    return near[0], q


def pick_b(acct: dict, base: str) -> tuple[str | None, dict]:
    """B 段采用：E、J 都要 年化不低于底、Calmar 高 ≥ 0.02、最大回撤不深 2 pp 以上；几个都过 → min(Calmar 提高) 最大，相差 < 0.02 → 编号小的。
    返回 (采用的 P?, {P?: {"ok", "d_calmar", "why"}})。"""
    res: dict = {}
    for v in PS:
        k, why, d = f"{base}+{v}", [], []
        for t in JUDGE:
            a, b = acct[t].get(k) or {}, acct[t].get(base) or {}
            if not all(_ok(x) for x in (a.get("cagr"), a.get("dd"), a.get("calmar"), b.get("cagr"), b.get("dd"), b.get("calmar"))):
                why.append(f"{t} 没有值")
                continue
            dc = a["calmar"] - b["calmar"]
            d.append(dc)
            if a["cagr"] < b["cagr"] - 1e-9:
                why.append(f"{t} 年化")
            if dc < GAIN - 1e-9:
                why.append(f"{t} Calmar")
            if a["dd"] < b["dd"] - DD_TOL - 1e-9:
                why.append(f"{t} 回撤")
        if not any(k in acct[t] for t in JUDGE):
            continue
        res[v] = {"ok": not why, "d_calmar": round(min(d), 3) if len(d) == len(JUDGE) else None, "why": why,
                  "_d": min(d) if len(d) == len(JUDGE) else None}
    ok = [v for v in PS if v in res and res[v]["ok"]]
    if not ok:
        return None, res
    best = max(res[v]["_d"] for v in ok)
    near = [v for v in ok if best - res[v]["_d"] < TIE - 1e-12]
    return near[0], res


def fallback_ok(acct: dict, k: str) -> bool:
    """A 段没有时「1655 + 反向」要换进模拟盘：E、J 的年化都 ≥ max(K0, S0) + 1.0 pp（六）。"""
    for t in JUDGE:
        v, r0, s0 = acct[t].get(k) or {}, acct[t]["K0"], acct[t]["S0"]
        if not all(_ok(x) for x in (v.get("cagr"), r0["cagr"], s0["cagr"])) or v["cagr"] < max(r0["cagr"], s0["cagr"]) + MARGIN - 1e-9:
            return False
    return True


def decision(win: str | None, adopt: str | None, adopt_s0: str | None, s0_ok: bool = False) -> dict:
    """第六节：模拟盘的闲置资金改成什么（mode / overlay；None = 不变）。adopt_s0 只有 s0_ok（年化高 1 pp 以上）才换进去。"""
    if win:
        return {"mode": win, "overlay": adopt, "change": True}
    if adopt_s0 and s0_ok:
        return {"mode": "K0", "overlay": adopt_s0, "change": True}
    return {"mode": None, "overlay": None, "change": False}


# ───────────────────────── 另报（只描述） ─────────────────────────
def core_only(px: pd.Series, bear: pd.Series, start: str) -> pd.Series:
    """只有核心的净值：前一天收盘不是熊 → 当天拿；每次持仓变化扣 SWITCH_COST%（与 ndx_study.core_mix 同一做法）。"""
    px = px.dropna().sort_index()
    px = px[px.index >= pd.Timestamp(start)]
    b = bear.astype(float).reindex(px.index.union(bear.index)).ffill().reindex(px.index).fillna(1.0) > 0.5
    pos = (~b).astype(float).shift(1).fillna(0.0)
    r = px.pct_change().fillna(0.0)
    turn = pos.diff().abs().fillna(pos.abs())
    return (1 + pos * r - turn * SWITCH_COST / 100).cumprod()


def curve_stats(eq: pd.Series) -> dict:
    """年化 / 最大回撤 / Calmar / 最差 10 年年化（每个月末起算）/ 最差一年。"""
    e = eq.dropna()
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = ((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100
    dd = float((e / e.cummax() - 1).min() * 100)
    me = e.resample("ME").last().dropna()
    w10 = []
    for i, d in enumerate(me.index):
        j = me.index.searchsorted(d + pd.DateOffset(years=10))
        if j < len(me):
            w10.append(((me.iloc[j] / me.iloc[i]) ** (1 / 10) - 1) * 100)
    ye = e.resample("YE").last()
    yr = (ye / ye.shift(1) - 1).dropna() * 100
    return {"start": str(e.index[0].date()), "cagr": round(cagr, 2), "dd": round(dd, 2),
            "calmar": round(cagr / abs(dd), 3) if dd < 0 else None, "worst10": round(min(w10), 2) if w10 else None,
            "worst_year": (str(yr.idxmin().year), round(float(yr.min()), 1)) if len(yr) else None}


def long_history(inp: dict, bear: dict) -> dict[str, dict]:
    """只有核心的长历史（日元；汇率 FRED，同一天）：S&P500 / 纳指 / 纳指 2 倍 / 日经 / 日经 2 倍 1987〜、SOX 1995〜、印度 1998〜。"""
    dex = inp["dexjp"].dropna()
    dtb3, cjp = inp["dtb3"], inp["cjp"]
    ntr = ndx_tr(inp)

    def jpy(s: pd.Series) -> pd.Series:
        return (s * dex.reindex(s.index.union(dex.index)).ffill().reindex(s.index)).dropna()
    n225 = inp["n225"]
    L = {"S0": (jpy(grow(spx_tr(inp), -FEE["1655.T"])), "US", "1987-01-01"),
         "Q1": (jpy(grow(ntr, -FEE["1545.T"])), "US", "1987-01-01"),
         "Q2": (jpy(grow(grow(inp["sox"], SOX_DIV), -FEE["2243.T"])), "US", "1995-06-01"),
         "Q3": (lev(ntr, 2.0, dtb3, cjp, FEE["2869.T"]), "US", "1987-01-01"),
         "Q4": (jp_product(n225, 1.0, None, None, FEE["1321.T"])["Close"], "JP", "1987-01-01"),
         "Q5": (jp_product(n225, 2.0, cjp, cjp, FEE["1570.T"])["Close"], "JP", "1987-01-01"),
         "Q6": ((grow(grow(india_index(inp), IN_DIV), -FEE["1678.T"])
                 * jpy_per(dex, inp["dexin"]).reindex(india_index(inp).index).ffill()).dropna(), "IN", "1998-07-01")}
    return {k: curve_stats(core_only(px, bear[m], a)) for k, (px, m, a) in L.items()}


def tracking(cl: dict[str, pd.Series]) -> dict[str, dict]:
    """合成价 vs 真实 ETF（yfinance；|日收益| > 30% 且与合成差 > 20 pp 的行 = 没调整的分割 / 上市首日错行 → 那天用合成的收益）。"""
    from bullbear_study import load
    out = {}
    for t, s in cl.items():
        try:
            real = load(t, START)["Close"]
        except Exception as e:                                               # noqa: BLE001
            out[t] = {"err": type(e).__name__}
            continue
        both = pd.concat([s.rename("s"), real.rename("r")], axis=1).dropna()
        if len(both) < 60:
            continue
        rr, rs = both["r"].pct_change(), both["s"].pct_change()
        art = (rr.abs() > 0.30) & ((rr - rs).abs() > 0.20)
        rr = rr.where(~art, rs).fillna(0.0)
        real_c = (1 + rr).cumprod()
        syn_c = both["s"] / both["s"].iloc[0]
        m = pd.concat([syn_c.rename("s"), real_c.rename("r")], axis=1).resample("ME").last().pct_change().dropna()
        yrs = (both.index[-1] - both.index[0]).days / 365.25
        cs, cr = syn_c.iloc[-1] ** (1 / yrs) - 1, real_c.iloc[-1] ** (1 / yrs) - 1
        out[t] = {"from": str(both.index[0].date()), "years": round(yrs, 1), "corr": round(float(m["s"].corr(m["r"])), 3),
                  "te": round(float((m["s"] - m["r"]).std() * np.sqrt(12) * 100), 2), "diff_pp": round((cs - cr) * 100, 2),
                  "fixed_rows": [str(d.date()) for d in art[art].index]}
    return out


def latest(bear: dict, warn: dict) -> dict:
    """最新收盘的读数：各市场牛熊、A0 / C_rel 百分位；各方式现在会拿什么（仅对这个时点有效）。"""
    out: dict = {}
    for m, b in bear.items():
        b = b.dropna()
        out[f"bear_{m}"] = {"date": str(b.index[-1].date()), "bear": bool(b.iloc[-1])}
    for m, w in warn.items():
        for k in ("a0_pct", "crel_pct"):
            s = w[k].dropna()
            out[f"{k}_{m}"] = {"date": str(s.index[-1].date()), "value": round(float(s.iloc[-1]), 1)} if len(s) else None
    now = {}
    for k in ("K0", *QS):
        m = IC.EQ_MARKET[k]
        t = next(iter(IC.MODES[k]["core"]))
        now[k] = "现金" if out[f"bear_{m}"]["bear"] else IC.NAMES.get(t, t)
        if IC.INVERSE.get(k):
            w = warn.get(m) or {}
            for v in PS:
                on = IC.overlay_on(v, bear[m], w.get("a0_pct"), w.get("crel_pct"))
                now[f"{k}+{v}"] = IC.NAMES.get(IC.INVERSE[k], IC.INVERSE[k]) if bool(on.iloc[-1]) else now[k]
    out["now"] = now
    return out


# ───────────────────────── 运行 ─────────────────────────
def main() -> int:
    import leap_confirm as LF
    import pit_retrain_study as PRS
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    inp = load_inputs()
    fr, cl = assets(inp)
    bear = bears(inp)
    warn = warnings_hist()
    k3 = spec_k3()
    days = inp["n225"].index[inp["n225"].index >= START]
    print(f"数据准备好（{time.time() - t0:.0f}s）", flush=True)
    p = load_params(market="JP")
    p0, px6 = SF.no_w2_params(p), EXR.apply(p, "X6")
    ctxs: dict = {}
    acct: dict = {t: {} for t in TAGS}
    years: dict = {t: {} for t in TAGS}
    share: dict = {t: {} for t in TAGS}
    sw: dict = {t: {} for t in TAGS}

    def run_all(ks: list[tuple[str, dict]]) -> None:
        for tag in TAGS:
            if tag not in ctxs:
                ctx = LF.context(tag)
                fa = LF.frames(ctx, p0)
                ctxs[tag] = (ctx, LF.runner(ctx, fa), LF.with_mask(fa, LF.w2_keep(ctx, fa)))
            ctx, run_fn, fw = ctxs[tag]
            PRS.PitEngine.DELIST = ctx["delist"]                             # runner 是缓存的 → 每个窗口重设（leap_confirm.runner 只在建的时候设）
            a, b = ctx["windows"][tag]
            for k, sp in ks:
                r = LF.run(ctx, run_fn, fw, px6, **level_at(sp, ctx["start"]))
                acct[tag][k] = {x: r[tag][x] for x in ("cagr", "dd", "calmar", "tot")}
                acct[tag][k].update({f"{tag}{h}": r[f"{tag}{h}"]["calmar"] for h in ("1", "2")})
                years[tag][k] = r.get("_years") or {}
                share[tag][k] = held_share(sp, bear, days, a, b)
                sw[tag][k] = switches_per_year(sp, days, a, b)
            print(f"{tag} 完成（{time.time() - t0:.0f}s）：" + "、".join(
                f"{k} {acct[tag][k]['calmar']}" for k, _ in ks), flush=True)

    run_all([("K0", {}), ("S0", spec_a("S0", fr, bear)), ("K3", k3)] + [(q, spec_a(q, fr, bear)) for q in QS])
    win, qual = pick_a(acct)
    base = win or "S0"
    blist = []
    if base != "S0" and IC.INVERSE.get(base):
        blist += [(f"{base}+{v}", spec_b(base, v, fr, bear, warn)) for v in PS]
    blist += [(f"S0+{v}", spec_b("S0", v, fr, bear, warn)) for v in PS]
    run_all(blist)
    adopt, bres = (pick_b(acct, base) if base == "S0" or IC.INVERSE.get(base) else (None, {}))
    adopt_s0, bres_s0 = pick_b(acct, "S0")
    s0_ok = bool(adopt_s0) and fallback_ok(acct, f"S0+{adopt_s0}")
    dec = decision(win, adopt if win else None, None if win else adopt_s0, s0_ok)
    lh = long_history(inp, bear)
    trk = tracking(cl)
    now = latest(bear, warn)
    write_report(acct, years, share, sw, qual, win, base, adopt, bres, adopt_s0, bres_s0, s0_ok, dec, lh, trk, now, inp["fx_fixed"])
    print(f"完成（{time.time() - t0:.0f}s）", flush=True)
    return 0


def _f(v, f="{:.2f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def label(k: str) -> str:
    if k in DESC:
        return DESC[k]
    if "+" in k:
        b, v = k.split("+")
        inv = IC.INVERSE["K0" if b == "S0" else b]
        return f"{label(b)}；{IC.OVERLAYS[v]}（{IC.NAMES.get(inv, inv)}）"
    return IC.LABELS.get(k, k)


def write_report(acct, years, share, sw, qual, win, base, adopt, bres, adopt_s0, bres_s0, s0_ok, dec, lh, trk, now, fx_fixed) -> None:
    L = ["# 闲置资金：比 1655 收益更高的股票类 + 预计下跌时拿反向（2026-09-29 登记，只跑一次；规则见本脚本开头）", ""]
    if dec["change"]:
        m = dec["mode"]
        L.append(f"**按登记的规则：模拟盘闲置资金改成 {m} {label(m)}" + (f" + {dec['overlay']} {IC.OVERLAYS[dec['overlay']]}" if dec["overlay"] else "")
                 + "**（基准账户照旧原规则）")
    else:
        L.append("**按登记的规则：没有入选 → 模拟盘不变（K3）**；回到 K0 或选别的由你决定")
    L += [f"A 段入选：{win or '没有'}；B 段的底：{base}；B 段采用：{adopt or '没有'}；S0 上的 B 段：{adopt_s0 or '没有'}"
          + (f"（年化高 1 pp 以上：{'是' if s0_ok else '否'}）" if adopt_s0 and not win else ""), ""]
    ks = [k for k in acct["E"]]
    L += ["| 方式 | " + " | ".join(f"{t} 年化 / 最大回撤 / Calmar（前半 / 后半）" for t in TAGS) + " |", "|---|" + "---|" * len(TAGS)]
    for k in ks:
        cells = []
        for t in TAGS:
            v = acct[t].get(k, {})
            cells.append(f"{_f(v.get('cagr'), '{:+.2f}')}% / {_f(v.get('dd'))}% / {_f(v.get('calmar'), '{:.3f}')}"
                         f"（{_f(v.get(t + '1'), '{:.3f}')} / {_f(v.get(t + '2'), '{:.3f}')}）")
        L.append(f"| {k} {label(k)} | " + " | ".join(cells) + " |")
    L += ["", "A 段入围（E、J：年化 ≥ max(K0, S0) + 1.0 pp，回撤不深 2 pp 以上）："]
    for k in QS:
        ok, why = qual.get(k, (False, ["没跑"]))
        L.append(f"- {k} {IC.LABELS[k]}：{'入围' if ok else '不入围（' + '、'.join(why) + '）'}")
    for nm, res in (("B 段（底 " + base + "）", bres), ("S0 上的 B 段（只描述）", bres_s0 if base != "S0" else {})):
        if res:
            L += ["", f"{nm}（E、J：年化不低、Calmar +0.02 以上、回撤不深 2 pp 以上）："]
            for v, r in res.items():
                L.append(f"- {v} {IC.OVERLAYS[v]}：{'通过' if r['ok'] else '不通过（' + '、'.join(r['why']) + '）'}；"
                         f"Calmar 提高 min(E, J) {_f(r['d_calmar'], '{:+.3f}')}")
    L += ["", "拿各 ETF 的交易日比例（%；其余 = 现金）/ B 段每年换仓次数："]
    for k in ks:
        L.append(f"- {k}：" + "；".join(f"{t} " + ("、".join(f"{IC.NAMES.get(x, x)} {v:.0f}%" for x, v in share[t].get(k, {}).items()) or "全部现金")
                                     + (f"（换仓 {sw[t][k]} 次/年）" if sw[t].get(k) is not None else "") for t in TAGS))
    L += ["", "各年收益（%；2006 以前 = Z、2007〜2016 = E、2017〜 = J）："]
    ys = sorted({y for t in TAGS for k in ks for y in (years[t].get(k) or {})})
    L += ["| 方式 | " + " | ".join(ys) + " |", "|---|" + "---|" * len(ys)]
    for k in ks:
        vals = {}
        for t, (lo, hi) in (("Z", ("0000", "2006")), ("E", ("2007", "2016")), ("J", ("2017", "9999"))):
            vals.update({y: v for y, v in (years[t].get(k) or {}).items() if lo <= y <= hi})
        L.append(f"| {k} | " + " | ".join(_f(vals.get(y), "{:+.1f}") for y in ys) + " |")
    L += ["", "只有核心的长历史（日元、牛熊同上、熊市现金、换仓 0.1%；只描述）：",
          "| 方式 | 起点 | 年化 | 最大回撤 | Calmar | 最差 10 年年化 | 最差一年 |", "|---|---|---|---|---|---|---|"]
    for k, s in lh.items():
        wy = s.get("worst_year")
        L.append(f"| {k} {label(k)} | {s['start']} | {_f(s['cagr'], '{:+.2f}')}% | {_f(s['dd'])}% | {_f(s['calmar'], '{:.3f}')} | "
                 f"{_f(s['worst10'], '{:+.2f}')}% | {wy[0] + ' ' + _f(wy[1], '{:+.1f}') + '%' if wy else '—'} |")
    L += ["", "USD/JPY 换成 FRED 的错价：" + ("、".join(fx_fixed) or "没有")]
    L += ["", "合成价 vs 真实 ETF（年化差 = 合成 − 真实；只核对数据）："]
    for t, r in trk.items():
        L.append(f"- {IC.NAMES.get(t, t)}：" + (r["err"] if "err" in r else
                 f"{r['from']} 起 {r['years']} 年，月收益相关 {r['corr']}，跟踪误差 {r['te']}%/年，年化差 {r['diff_pp']:+.2f} pp"
                 + (f"（修正了 {len(r['fixed_rows'])} 行）" if r["fixed_rows"] else "")))
    L += ["", "最新读数（仅对这个时点有效）：" + "；".join(
        f"{m} 牛熊 {now[f'bear_{m}']['date']} {'熊' if now[f'bear_{m}']['bear'] else '牛'}" for m in ("US", "JP", "IN"))
          + "；" + "；".join(f"{k} {now[k]['date']} {now[k]['value']}" for k in ("a0_pct_US", "crel_pct_US", "a0_pct_JP", "crel_pct_JP") if now.get(k)),
          "现在会拿：" + "；".join(f"{k} {v}" for k, v in now["now"].items())]
    L += ["", "照实写：这 20 年是美国科技股的大行情；合成价比真实 ETF 乐观约 0〜1.6 pp/年（门槛 +1.0 pp 已考虑）；两个判定窗口、几段熊市，样本小；"
          "纳指 1987〜2005 与 1929〜1986 的代理是反例（ndx_study / core_mix_study）；税前。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "equity_idle_study"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"decision": dec, "a_winner": win, "base": base, "b_adopt": adopt, "b_results": bres,
                                              "s0_adopt": adopt_s0, "s0_results": bres_s0, "s0_fallback_ok": s0_ok, "fx_fixed": fx_fixed,
                                              "qualify": {k: {"ok": v[0], "why": v[1]} for k, v in qual.items()},
                                              "accounts": acct, "years": years, "share": share, "switches": sw,
                                              "long_history": lh, "tracking": trk, "latest": now},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
