"""sel_monthly_study.py — 把现行的选股方案拆成「每月」：8 个参数各自按月增 / 减，看每个参数的逐月变化趋势与当月的利率 / 国债收益率 /
成交额等有没有相似处；再做只用过去数据的月度规则（按月重估 / 记忆衰减 / 逐参数增减 / 按国债收益率分档 / 按成交额分档）在三个年代上
一步一步往前走，看能不能优化现有买卖点。登记检验：规则先提交再运行一次，看到结果之后不改规则。
（2026-09-29 用户：「把现在的选股方案拆为每月来看，调整其中参数增加/减少各个参数 来观察每个参数在相隔月之间的变化趋势对比当前月的利率
国债收益率等等看看有没有相似处 看看有没有改善现在的选股优化，然后按照每月调整的衰减/增加度来适应以后的数据，调整到可以优化现有买卖点
因为从过去到现在也可能股票结构发生了变化 或者量变多了导致以前的方法不可用 但是有可能在一些方面还是有迹可循的」）

〇 已经知道的（不重复做）
  - 跟着时代每年 / 每月重选买点阈值（2026-09-26，A1〜A5）：每年重选 20 年 Calmar +0.045（门槛 +0.05）→ 接近但没过；阈值有中等持续性（名次相关 +0.26）。
  - 让策略跟着时代自己更新 V1〜V5（09-27）：W2 门槛每季自己选来回跳 → 追噪音；都不比随机对照好。
  - 9 个买点参数联合调参 168 组（09-28）：三个样本都不差的 0 组，PBO 0.65，每年重调近 10 年更差。
  - 多因子（国债曲线 / 利率 / 油价 / 汇率 / 信用 / VIX）预测个股或大盘（09-24）：样本外几乎没有预测力；在用的宏观层只是新仓倍数。
  - 昨天 B・N・F 拆成每月：按月调参有一点提高，但不比定死、不比随机换参数多。
  这次新的一点：不是用过去的成绩去调参数，而是看「每个参数该增还是该减」与**当月的宏观状态**（利率、国债收益率、成交额）有没有对应关系；
  有的话，按宏观状态分档记忆参数（同一档的历史月份怎么样，这个月就怎么设）。昨天已经试过的「按斜率外推」（A2 型）这里不再重复，
  「衰减」由 C2（记忆衰减）承担。

一 参数与网格（8 个；每个 3 档，中间那档 = 现行）
  买点：箱体天数 range_n ∈ {40, 60, 90}；箱体振幅 range_x ∈ {10, 15, 20}%；放量倍数 vol_mult ∈ {1.2, 1.5, 2.0}；
        出货日上限 max_dist ∈ {4, 6, 不限}；周线量比 W2 ∈ {关, 1.0, 1.5}。
  卖点：止损 stop ∈ {5, 7, 10}%；吊灯 k ∈ {2, 3, 4}（收盘 < 持有以来最高价 − k × ATR14）；最多持有 max_hold ∈ {40, 60, 90} 天。
  其余照现行不变：MACD 12 / 26 / 9 金叉且 |MACD| / 收盘 < 1%、均量 20 日、上影 ≤ 3、止盈 25%、跟踪止损 12%、放量阴线离场（成交量 > 均量 2.5 倍的阴线且浮盈 ≥ 5%）；
  执行照现行（信号日收盘 → 次日寄付、跳空 > 3% 不买、立花手续费）；股票池 = 今天的日経225。有效组合 3^8 = 6,561 组；θ0 = 现行。
  「增 / 减」= 按数值大小（出货日「不限」算最大、W2「关」算最小）。
  快速逐笔：每个信号单独一笔（事件式、允许重叠），下一个交易日开盘买、按止损 / 跟踪 / 止盈 / 放量阴线 / 吊灯 / 到期卖、扣双边滑点与手续费，
  口径与引擎相同（tests 里对照研究引擎 MixEngine）；每笔记在**平仓那个月**（m 月那一列只有在 m 月内已卖出的笔 → 用 < m 的列 = 只用 m−1 月底以前的信息）；
  只用来算「每个参数该增还是该减」与选 θ；账户用引擎重算（同一套 S0C2 + 核心 + 牛熊分界 + 宏观 / 状态层，与现行账户完全相同的框架）。
  现行信号的核对：用这里的机器按 θ0 重建的买点要与 compute_indicators + W2（现行账户用的）逐日逐票完全一致，否则停止不跑。

二 每个参数逐月的增 / 减（描述；三个年代 Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09 都做）
  每个月 m、每个参数 j：其余 7 个参数放在现行值，只动参数 j（一次一个，OAT），用 m−36〜m−1 月内平仓的笔算三档各自的每笔净收益
  （每档 ≥ 20 笔才算）；增减度 g_j(m) = 大档 − 小档（pp / 笔）；「该增 / 该减」= 最好的那档比现行那档好 0.25 pp 以上才换
  （0.25 pp 在抽样误差之内：每笔的离散约 8〜10 pp，20〜100 笔的平均误差约 1〜2 pp → 这条路径按定义会被噪音牵着走，是照用户要求「每月都动一下」的写法）。
  买点参数的三档是嵌套的（松的档多出来的笔才是差别）→ 买点参数的 g_j(m) 只在大档与小档的笔数差 ≥ 10 时才算，卖点参数是同一批笔的配对比较、不受此限；
  每档的笔数都写进 JSON。持续性：按日历年（不重叠）的增减度，相邻两年同号的比例与相邻年的 Spearman（三个年代合并）—— 参数「该往哪边动」有没有延续性。
  另给「联合最好」路径（6,561 组里以 m 为止 36 个月最好的一组，样本内，只描述换了几次）。

三 和当月宏观状态的相似处（描述；m 月用 m−1 月底的值）
  宏观 / 结构序列 14 条：日本国债 10 年 / 2 年（財務省）、日本政策利率（無担保コール，OECD 月平均、发布有时滞 → 用 m−2 月的值，只描述）、
  美债 10 年、美债 2〜10 年利差、联邦基金利率、VIX、美国 Baa 信用利差（FRED）、USD/JPY 及其 12 个月变化（Yahoo）、
  日経225 的 12 个月涨跌与 20 日实现波动（Yahoo）、股票池当月日均売買代金（对数）及其 12 个月变化（面板本身；「量变多了」）。
  相似处 = 每个参数的增减度 g_j(m) 与每条序列的 Spearman 秩相关 ρ（每个年代分别算）；写定的读法：|ρ| ≥ 0.3 且 E、J 同号才算「有对应」，
  Z 作第三段核对。注意 g_j(m) 是 36 个月滚动的统计量，相邻月份重叠 35/36 → 有效样本远小于月数、ρ 的「显著」被高估，
  所以另给一列不重叠的：按日历年（那一年平仓的笔）算每个参数的增减度、对上一年年底的序列值，三个年代合并 ≈ 26 个点的 ρ_year。
  写定的零假设对照：把每条序列在各年代内整体循环平移一个 ≥ 36 个月的随机量（200 次），每次重算全表 → ★ 的个数与 max|ρ| 的零分布；
  只有实际 ★ 数 > 零分布的 95 分位，才说「有对应」；单个 ★ 不说明什么（滚动统计量 + 有持续性的序列，零假设下每对出 |ρ| ≥ 0.3 的概率就有三四成）。
  全部只描述（8 × 14 × 3 = 336 个相关加 8 × 14 个年度相关）。

四 只用过去数据的月度规则（候选 5 个；三个年代都是 walk-forward，m 月的 θ 只用 m−1 月底以前已平仓的笔；起点 θ0）
  C1 每月联合重估：最近 36 个月，6,561 组里每笔平均最好（≥ 30 笔），比上月的 θ 好不到 0.25 pp 不换。
  C2 联合重估 + 记忆衰减：最近 60 个月，权重 0.5^(月龄 / 24)，其余同 C1。
  C3 逐参数增减：每个参数独立地按「二」的规则增 / 减（相对现行值，好 0.25 pp 以上才动），8 个参数各自定 → 拼成这个月的 θ。
  C4 按国债收益率分档记忆：日本国债 10 年（m−1 月底）在它**最近 120 个月**（含当月；不满 24 个月不分档）的三分位里属于低 / 中 / 高哪一档
     （用「从头到当时」的三分位会退化：2001〜2016 年的日本长期利率几乎全在自己历史的最低档 → 只剩一档 = 变成 C1），
     θ(m) = 过去（本年代月表里 < m）同一档的月份里平仓的笔（≥ 30 笔）上最好的一组；不够 → 沿用上一个；同样 0.25 pp 滞回。
  C5 按成交额分档记忆：同 C4，序列换成股票池（该年代交易的那些票）日均売買代金的对数，最近 120 个月的三分位（不满 24 个月不分档 → 沿用）。
  滞回的例外（fit_theta 同一实现）：上个月的 θ 在窗口里不够 30 笔 → 换成最好的（不套滞回）；没有任何组合够 30 笔 → 沿用。
  对照（只描述）：现行 θ0；两种随机路径安慰剂各 20 个种子 —— ①「乱抽」每月从 6,561 组里随机抽一组（大多比现行松、交易多得多）、
  ②「近邻」每月每个参数独立地在现行值上 −1 / 0 / +1 档（各 1/3；与 C3 一样只动一步）；上限（作弊：每月用当月自己的逐笔选，≥ 10 笔，不滞回）。
  账户回测后数一遍：每一笔成交是不是都在 PARAMS_TD 里找到了自己的参数（miss 必须 = 0，否则停止）。

五 判定（全部满足才「通过」；运行前写定）
  a 账户：E、J 各自 Calmar ≥ 现行 + 0.02、最大回撤不比现行深 2 pp 以上；Z Calmar ≥ 现行 − 0.02（不更差）；
  b 账户 J 的 Calmar > 两种随机路径安慰剂 95 分位的较高者（提高要超过「乱换参数」，也要超过「随手动一档」）；
  c E、J 各自 ≥ 30 笔账户交易。
  多个通过：按 min(E, J 的 Calmar 提高) 取 1 个。「通过」也只是提议（先前向记录；进模拟盘 / 执行器要你另外确认）。没通过 → 模拟盘不变。

六 事前预期（运行前写）
  现行信号很少（Z 面板 7 年半 203 只只有 122 个带 W2 的信号，约 17 个 / 年）→ 逐月路径会很吵、很多月份够不到 20 / 30 笔而沿用；
  与利率 / 国债的相关多半 |ρ| < 0.3、E 与 J 不同号（年度的 ρ_year 更接近 0）；★ 数不会超过零分布的 95 分位；「通过」约 10%；
  三个年代开头的窗口都不满（面板 Z 2000-01 / E 2005-09 / J 2016-09 起；36 / 60 个月的窗口要到第 3〜5 年才满）→ 各候选在 J 的 2017〜2019 基本 = θ0，
  b 条实际上由 2020〜2026 的调整决定；C4 / C5 每个年代的头 2〜3 年多半沿用 θ0（同一档的月份不够 30 笔）→ 接近现行；
  最可能出现的是结构性描述：成交额高的时期 W2 / 放量倍数的增减度不同。上限告诉我们按月调参的天花板。

七 另报：θ0 每年的信号数（三个年代）、逐年各参数的最优方向、成交额分档下 W2 的增减度、各候选每月换了几次。
八 局限：只用日线；大型股 = 今天的日経225（幸存者偏差）；调整后价、税前；快速逐笔允许重叠（成交日 = 下一个交易日，那天这只票没有 K 线 → 不算买到，与引擎一致；
  引擎的涨停买不到 / 跌停卖不掉没有模拟）；按平仓月入账会在窗口边上少算还没平仓的笔、持有越长的 θ 少得越多（登记的设计，三个年代一样）；
  E 的月表从 2005-10 起（Z 从 2000-01 起）→ E 头两年的 36 / 60 个月窗口不满、更常沿用 θ0；三个年代的成交量口径不同（Yahoo / J-Quants）→
  成交额只在年代内比较；政策利率是月平均、有发布时滞（只描述不入规则）；C4 / C5 的档是三分位、不是经济意义上的分界；
  「股票结构变了」只用今天的日経225 一个池（时点成员的池 U1 / U2 没用）；快速逐笔没有死叉 / SAR 卖法（现行 X6 模式两者都关，运行前断言）。
  模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/sel_monthly_study.md / .json（只有统计）。  python scripts/sel_monthly_study.py
（QB_SEL_SMOKE=1：只用 12 只票、安慰剂 2 个种子、输出加 _smoke —— 登记前只用来确认程序能跑通，数字没有意义、不看。）
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bnf_adapt_study as A                                                  # noqa: E402  mon / fit_theta / ew_weights / oracle_path / theta_path_insample

ERAS = ("Z", "E", "J")
RANGE_N, RANGE_X, VOL_MULT, MAX_DIST, W2 = (40, 60, 90), (10.0, 15.0, 20.0), (1.2, 1.5, 2.0), (4, 6, 0), (0.0, 1.0, 1.5)
STOP, CHAND, HOLD = (5.0, 7.0, 10.0), (2.0, 3.0, 4.0), (40, 60, 90)
GRIDS = (RANGE_N, RANGE_X, VOL_MULT, MAX_DIST, W2, STOP, CHAND, HOLD)
PNAMES = ("箱体天数", "箱体振幅", "放量倍数", "出货日上限", "W2 周线量比", "止损", "吊灯 k", "最多持有")
PKEYS = ("range_n", "range_x", "vol_mult", "max_dist", "w2", "stop", "chand_k", "max_hold")
ENTRIES = list(itertools.product(RANGE_N, RANGE_X, VOL_MULT, MAX_DIST, W2))         # 243
EXITS = list(itertools.product(STOP, CHAND, HOLD))                                  # 27
THETAS = [e + x for e in ENTRIES for x in EXITS]                                    # 6,561（序号 = 买点序号 × 27 + 卖点序号）
T_INDEX = {th: k for k, th in enumerate(THETAS)}
E_INDEX = {e: i for i, e in enumerate(ENTRIES)}
THETA0 = (60, 15.0, 1.5, 6, 1.0, 7.0, 3.0, 60)
K0 = T_INDEX[THETA0]
UPPER_SHADOW = 3.0
GAP_PCT = 3.0
W_JOINT, W_EW, HALF, W_OAT = 36, 60, 24.0, 36
N_MIN, N_MIN_OAT, HYST = 30, 20, 0.25                                                 # 上限（作弊）的最少笔数 = bnf_adapt_study.ORACLE_MIN（10）
BUCKET_MIN_HIST, BUCKET_WINDOW = 24, 120
PLACEBO_SEEDS, NULL_DRAWS, NULL_SHIFT_MIN, OAT_MARGIN = 20, 200, 36, 10
MIN_TRADES, CAL_UP, DD_TOL, Z_TOL = 30, 0.02, 2.0, 0.02
RHO_MIN = 0.3
CANDS = {"C1": "每月联合重估（36 个月）", "C2": "联合重估 + 记忆衰减（60 个月，半衰期 24）", "C3": "逐参数增减（OAT，36 个月）",
         "C4": "按国债 10 年收益率分档记忆", "C5": "按成交额分档记忆"}
MACRO_KEYS = ("jgb10y", "jgb2y", "jp_rate", "us10y", "us2s10s", "fed", "vix", "baa", "usdjpy", "usdjpy_chg12",
              "n225_ret12", "n225_vol20", "turnover", "turn_chg12")
MACRO_ZH = {"jgb10y": "日本国债 10 年", "jgb2y": "日本国债 2 年", "jp_rate": "日本政策利率", "us10y": "美债 10 年", "us2s10s": "美债 2〜10 年利差",
            "fed": "联邦基金利率", "vix": "VIX", "baa": "Baa 信用利差", "usdjpy": "USD/JPY", "usdjpy_chg12": "USD/JPY 12 个月变化",
            "n225_ret12": "日経 12 个月涨跌", "n225_vol20": "日経 20 日波动", "turnover": "股票池日均売買代金（对数）", "turn_chg12": "売買代金 12 个月变化"}
SMOKE = os.environ.get("QB_SEL_SMOKE") == "1"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


mon, mon_str = A.mon, A.mon_str


# ───────────────────────── 信号的部件（纯函数，有测试）─────────────────────────
def components(ctx: dict, fa: dict, p0) -> dict:
    """每只票：现行信号的部件（金叉且 0 轴附近、上影、放量比、出货日数、周线量比 W5v（与 w2_keep 同一算法）、三种箱体天数 × 三种振幅的横盘判定、预热）。"""
    from qbreak import mtf
    P, days = ctx["P"], pd.DatetimeIndex(ctx["days"])
    col = {t: j for j, t in enumerate(ctx["names"])}
    out = {}
    for t, df in fa.items():
        j = col[t]
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        raw = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                            "Volume": P["V"][ok, j]}, index=days[ok])
        w5v = mtf.daily_frame(raw, days)["W5v"].reindex(df.index).to_numpy(float)
        h, l = df["High"], df["Low"]
        ush = df["upper_shadow_ratio"].to_numpy(float)
        with np.errstate(invalid="ignore"):
            base = df["golden_cross"].to_numpy(bool) & df["near_zero"].to_numpy(bool) & ~(ush > UPPER_SHADOW)
        isr, warm = {}, {}
        for n in RANGE_N:
            hi, lo = h.rolling(n).max(), l.rolling(n).min()
            rp = ((hi - lo) / lo.replace(0, np.nan) * 100).shift(1)
            for x in RANGE_X:
                isr[(n, x)] = (rp < x).fillna(False).to_numpy(bool)
            warm[n] = np.arange(len(df)) >= replace(p0, range_n=n).warmup_bars
        out[t] = {"base": base, "vr": df["vol_ratio"].to_numpy(float), "dd": df["dist_days"].to_numpy(float), "w5v": w5v, "isr": isr, "warm": warm}
    return out


def entry_mask(c: dict, e: tuple) -> np.ndarray:
    """买点组合 e = (range_n, range_x, vol_mult, max_dist, w2) 在每一天是否成立（与 compute_indicators 的 cond 同一逻辑）。"""
    n, x, vm, md, w2 = e
    with np.errstate(invalid="ignore"):
        m = c["base"] & c["isr"][(n, x)] & (c["vr"] > vm) & c["warm"][n]
        if md:
            m &= c["dd"] < md
        if w2:
            m &= ~(c["w5v"] < w2)
    return m


def fwd_rows(fa: dict, comp: dict, slip: float, days: pd.DatetimeIndex | None = None, hmax: int = max(HOLD), gap: float = GAP_PCT) -> dict:
    """快速逐笔的前向表：只保留至少一个买点组合成立的日子（最松的组合的并集）。
    M[行, 买点组合] = 那天那个组合是否成立；entry = 次日开盘 × (1 + 滑点)（跳空 > 3% → NaN；给了 days 时，这只票的下一根 K 线不是下一个交易日 → NaN，与引擎一样不算买到）；
    H / C / At / Cx：成交日之后第 k 天（k = 0..hmax−1）的最高 / 收盘 / ATR14 / 是否放量阴线；O：再下一天的开盘（卖出价）；Xm：那个卖出日的月序号（没有 → −1）。"""
    parts = {k: [] for k in ("tick", "date", "mon", "entry", "M", "H", "C", "At", "Cx", "O", "Xm")}
    pos_of = pd.Series(np.arange(len(days)), index=days) if days is not None else None
    for t, df in fa.items():
        c = comp[t]
        with np.errstate(invalid="ignore"):
            loose = c["base"] & (c["vr"] > min(VOL_MULT)) & c["warm"][min(RANGE_N)]
            loose &= c["isr"][(RANGE_N[0], max(RANGE_X))] | c["isr"][(RANGE_N[1], max(RANGE_X))] | c["isr"][(RANGE_N[2], max(RANGE_X))]
        rows = np.flatnonzero(loose)
        if not len(rows):
            continue
        o, h, cl, at = (df[k].to_numpy(float) for k in ("Open", "High", "Close", "atr"))
        cx = df["climax"].to_numpy(bool)
        n = len(df)
        mo = np.array([mon(x) for x in df.index], int)
        M = np.zeros((len(rows), len(ENTRIES)), bool)
        for i, e in enumerate(ENTRIES):
            M[:, i] = entry_mask(c, e)[rows]
        o1 = np.r_[o[1:], np.nan]
        with np.errstate(invalid="ignore"):
            entry = np.where(o1 <= cl * (1 + gap / 100), o1 * (1 + slip), np.nan)[rows]
        if pos_of is not None:
            pp_ = pos_of.reindex(df.index).to_numpy(float)
            nxt_ok = np.r_[pp_[1:] == pp_[:-1] + 1, False]
            entry = np.where(nxt_ok[rows], entry, np.nan)
        Hm, Cm, Am, Om = (np.full((len(rows), hmax), np.nan) for _ in range(4))
        Cxm = np.zeros((len(rows), hmax), bool)
        Xm = np.full((len(rows), hmax), -1, int)
        for k in range(hmax):
            d = rows + 1 + k
            okd = d < n
            Hm[okd, k], Cm[okd, k], Am[okd, k], Cxm[okd, k] = h[d[okd]], cl[d[okd]], at[d[okd]], cx[d[okd]]
            d2 = d + 1
            ok2 = d2 < n
            Om[ok2, k], Xm[ok2, k] = o[d2[ok2]], mo[d2[ok2]]
        parts["tick"].append(np.full(len(rows), t, dtype=object))
        parts["date"].append(df.index.to_numpy()[rows])
        parts["mon"].append(mo[rows])
        parts["entry"].append(entry)
        parts["M"].append(M)
        parts["H"].append(Hm)
        parts["C"].append(Cm)
        parts["At"].append(Am)
        parts["Cx"].append(Cxm)
        parts["O"].append(Om)
        parts["Xm"].append(Xm)
    if not parts["tick"]:
        return {k: np.zeros((0,) if k in ("tick", "date", "mon", "entry") else (0, len(ENTRIES) if k == "M" else hmax), dtype=(bool if k in ("M", "Cx") else float)) for k in parts}
    return {k: np.concatenate(v) for k, v in parts.items()}


def exit_sim(rows: dict, S: float, kc: float, H: int, slip: float, rt: float, tp: float, trail: float, cx_min: float | None = 5.0) -> tuple[np.ndarray, np.ndarray]:
    """每一行按 (止损 S%, 吊灯 k, 最多 H 天) 卖出 → (净收益 %, 卖出在成交日之后第几天 k)；引擎同一套卖法（都在次日开盘卖，谁先触发不影响价）：
    收盘 ≤ max(止损价, 峰值 × (1 − 跟踪)) / 收盘 ≥ 止盈 / 放量阴线且浮盈 ≥ cx_min%（None = 关）/ 收盘 < 峰值 − k × ATR / 到期；
    峰值 = 买入价与持有以来最高价（含当天）。没买到 / 数据不够 → NaN。"""
    E = rows["entry"]
    n = len(E)
    alive = np.isfinite(E)
    peak = E.copy()
    kx = np.full(n, -1, int)
    for k in range(H):
        h, c, a = rows["H"][:, k], rows["C"][:, k], rows["At"][:, k]
        with np.errstate(invalid="ignore"):
            valid = alive & np.isfinite(c)
            peak = np.where(valid & np.isfinite(h), np.maximum(peak, h), peak)
            hard = np.maximum(E * (1 - S / 100), peak * (1 - trail / 100))
            hit = valid & ((c <= hard) | (c >= E * (1 + tp / 100)) | ((kc > 0) & np.isfinite(a) & (c < peak - kc * a)) | (k == H - 1))
            if cx_min is not None:
                hit |= valid & rows["Cx"][:, k] & ((c / E - 1) * 100 >= cx_min)
        kx[hit] = k
        alive &= ~hit
        if not alive.any():
            break
    sel = kx >= 0
    px = np.full(n, np.nan)
    px[sel] = rows["O"][np.flatnonzero(sel), kx[sel]]
    with np.errstate(invalid="ignore"):
        net = (px * (1 - slip) / E - 1) * 100 - rt
    return net, kx


def month_table(rows: dict, slip: float, rt: float, tp: float, trail: float, cx_min: float | None = 5.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """→ (months[M], S[θ, M], C[θ, M])：6,561 组在每个月的快速逐笔净收益合计与笔数，按平仓月入账。"""
    if not len(rows["entry"]):
        raise ValueError("没有信号")
    months = np.arange(int(rows["mon"].min()), int(max(rows["mon"].max(), rows["Xm"].max())) + 1)
    S = np.zeros((len(THETAS), len(months)))
    C = np.zeros((len(THETAS), len(months)))
    ar = np.arange(len(rows["entry"]))
    for xi, (s, kc, H) in enumerate(EXITS):
        net, k = exit_sim(rows, s, kc, H, slip, rt, tp, trail, cx_min)
        xm = np.where(k >= 0, rows["Xm"][ar, np.maximum(k, 0)], -1)
        ok = np.isfinite(net) & (xm >= 0)
        mi = xm - months[0]
        for ei in range(len(ENTRIES)):
            m = ok & rows["M"][:, ei]
            kk = ei * len(EXITS) + xi
            S[kk] = np.bincount(mi[m], weights=net[m], minlength=len(months))
            C[kk] = np.bincount(mi[m], minlength=len(months))
    return months, S, C


# ───────────────────────── 月度规则 ─────────────────────────
def oat_theta_index(j: int, v) -> int:
    th = list(THETA0)
    th[j] = v
    return T_INDEX[tuple(th)]


def oat_month(S: np.ndarray, C: np.ndarray, cols: np.ndarray) -> tuple[list, list, list, list]:
    """一个窗口：每个参数三档（其余现行）的每笔平均 → (选的值, 增减度 大 − 小, 三档每笔, 三档笔数)。
    买点参数（前 5 个）的三档是嵌套的 → 增减度只在大档与小档的笔数差 ≥ OAT_MARGIN 时才算。"""
    vals, gains, objs, ns = [], [], [], []
    for j, grid in enumerate(GRIDS):
        idx = [oat_theta_index(j, v) for v in grid]
        n = C[idx][:, cols].sum(axis=1) if len(cols) else np.zeros(3)
        s = S[idx][:, cols].sum(axis=1) if len(cols) else np.zeros(3)
        with np.errstate(invalid="ignore", divide="ignore"):
            obj = np.where(n >= N_MIN_OAT, s / np.maximum(n, 1), np.nan)
        j0 = grid.index(THETA0[j])
        v = THETA0[j]
        if np.isfinite(obj[j0]) and np.isfinite(obj).any():
            best = int(np.nanargmax(obj))
            if obj[best] - obj[j0] >= HYST:
                v = grid[best]
        vals.append(v)
        ok_g = np.isfinite(obj[0]) and np.isfinite(obj[2]) and (j >= 5 or abs(n[2] - n[0]) >= OAT_MARGIN)
        gains.append(float(obj[2] - obj[0]) if ok_g else np.nan)
        objs.append([None if not np.isfinite(x) else float(x) for x in obj])
        ns.append([int(x) for x in n])
    return vals, gains, objs, ns


def oat_path(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int) -> tuple[dict[int, int], dict[int, list]]:
    """C3：每个月每个参数独立地对现行值做增 / 减 → 拼成 θ；另返回每月的增减度。"""
    out, gains = {}, {}
    for m in range(a, b + 1):
        cols = np.flatnonzero((months >= m - W_OAT) & (months < m))
        vals, g, _, _ = oat_month(S, C, cols)
        out[m] = T_INDEX[tuple(vals)]
        gains[m] = g
    return out, gains


def yearly_gains(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int) -> dict[int, list]:
    """不重叠的年度增减度：每个日历年（窗口内）那一年平仓的笔 → 每个参数 大档 − 小档（每档 ≥ 20 笔）。"""
    out = {}
    for y in range(a // 12, b // 12 + 1):
        cols = np.flatnonzero((months // 12 == y) & (months >= a) & (months <= b))
        if len(cols):
            out[y] = oat_month(S, C, cols)[1]
    return out


def persistence(YG: dict[str, dict[int, list]]) -> dict[str, dict]:
    """每个参数：相邻两年（同一年代内、不重叠）的年度增减度 → 同号比例 % 与 Spearman（三个年代合并）。"""
    out = {}
    for j, key in enumerate(PKEYS):
        xs, ys = [], []
        for e, yg in YG.items():
            for y in sorted(yg):
                if y + 1 in yg and np.isfinite(yg[y][j]) and np.isfinite(yg[y + 1][j]):
                    xs.append(yg[y][j])
                    ys.append(yg[y + 1][j])
        agree = (float(np.mean(np.sign(xs) == np.sign(ys)) * 100) if xs else None)
        rho, n = spearman(xs, ys)
        out[key] = {"n_pairs": len(xs), "same_sign_pct": agree, "rho": (None if not np.isfinite(rho) else rho)}
    return out


def star_count(GAIN: dict, MAC: dict, keys=MACRO_KEYS, shift: dict | None = None) -> tuple[int, float]:
    """★ 的个数与 max|ρ|（E、J）：shift = {年代: 平移月数}（零假设对照：把序列在年代内整体循环平移）。"""
    n_star, mx = 0, 0.0
    for j in range(8):
        for key in keys:
            rr = {}
            for e in ("E", "J"):
                ms = sorted(GAIN[e])
                x = np.array([MAC[e].get(key, {}).get(m, np.nan) for m in ms], float)
                if shift:
                    x = np.roll(x, shift[e])
                y = [GAIN[e][m][j] for m in ms]
                rr[e] = spearman(x, y)[0]
            rE, rJ = rr["E"], rr["J"]
            if np.isfinite(rE) and np.isfinite(rJ):
                mx = max(mx, abs(rE), abs(rJ))
                if abs(rE) >= RHO_MIN and abs(rJ) >= RHO_MIN and np.sign(rE) == np.sign(rJ):
                    n_star += 1
    return n_star, mx


def null_stars(GAIN: dict, MAC: dict, draws: int = NULL_DRAWS, seed: int = 20260929) -> tuple[list[int], list[float]]:
    """零假设：每条序列在 E、J 各自循环平移一个 ≥ NULL_SHIFT_MIN 个月的随机量 → ★ 数与 max|ρ| 的分布。"""
    rng = np.random.default_rng(seed)
    ns, mxs = [], []
    for _ in range(draws):
        sh = {}
        for e in ("E", "J"):
            n = len(GAIN[e])
            sh[e] = int(rng.integers(NULL_SHIFT_MIN, max(NULL_SHIFT_MIN + 1, n - NULL_SHIFT_MIN))) if n > 2 * NULL_SHIFT_MIN else int(rng.integers(1, max(2, n)))
        k, m = star_count(GAIN, MAC, shift=sh)
        ns.append(k)
        mxs.append(m)
    return ns, mxs


def wf(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, start: int, win: int, half: float | None = None) -> dict[int, int]:
    """C1 / C2：m 月用 m−win〜m−1 月（可加记忆衰减）平仓的笔重选（≥ 30 笔、0.25 pp 滞回）。"""
    out, prev = {}, start
    for m in range(a, b + 1):
        cols = np.flatnonzero((months >= m - win) & (months < m))
        wts = A.ew_weights(m - 1 - months[cols], half=half) if (half and len(cols)) else None
        prev = A.fit_theta(S, C, cols, wts, prev, n_min=N_MIN, hyst=HYST)
        out[m] = prev
    return out


def bucket_labels(series: dict[int, float], min_hist: int = BUCKET_MIN_HIST, window: int = BUCKET_WINDOW) -> dict[int, int | None]:
    """每个月的档（0 低 / 1 中 / 2 高）：用该序列最近 window 个月（含当月）的三分位；历史不满 min_hist 个月 → None。"""
    ks = sorted(series)
    vals = np.array([series[k] for k in ks], float)
    out = {}
    for i, k in enumerate(ks):
        hist = vals[max(0, i + 1 - window): i + 1]
        hist = hist[np.isfinite(hist)]
        if len(hist) < min_hist or not np.isfinite(vals[i]):
            out[k] = None
            continue
        q1, q2 = np.percentile(hist, [100 / 3, 200 / 3])
        out[k] = 0 if vals[i] <= q1 else (2 if vals[i] > q2 else 1)
    return out


def bucket_path(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, labels: dict[int, int | None], start: int) -> dict[int, int]:
    """C4 / C5：θ(m) = 过去（< m）同一档的月份里平仓的笔上最好的一组（≥ 30 笔、0.25 pp 滞回）；这个月没有档 → 沿用。"""
    out, prev = {}, start
    for m in range(a, b + 1):
        lab = labels.get(m)
        if lab is not None:
            cols = np.array([i for i, mm in enumerate(months) if mm < m and labels.get(int(mm)) == lab], int)
            prev = A.fit_theta(S, C, cols, None, prev, n_min=N_MIN, hyst=HYST)
        out[m] = prev
    return out


def random_path(a: int, b: int, seed: int) -> dict[int, int]:
    """安慰剂 ①「乱抽」：每月从全部组合里随机抽一组。"""
    rng = np.random.default_rng(seed)
    return {m: int(rng.integers(0, len(THETAS))) for m in range(a, b + 1)}


def neighbour_path(a: int, b: int, seed: int) -> dict[int, int]:
    """安慰剂 ②「近邻」：每月每个参数独立地在现行值上 −1 / 0 / +1 档（各 1/3）。"""
    rng = np.random.default_rng(10_000 + seed)
    out = {}
    for m in range(a, b + 1):
        th = [grid[1 + int(rng.integers(-1, 2))] for grid in GRIDS]
        out[m] = T_INDEX[tuple(th)]
    return out


def spearman(x, y) -> tuple[float, int]:
    s = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(s) < 12:
        return (np.nan, int(len(s)))
    return (float(s["x"].rank().corr(s["y"].rank())), int(len(s)))


def build(fa: dict, comp: dict, days: pd.DatetimeIndex, path: dict[int, int], px) -> tuple[dict, dict]:
    """θ 路径 → (引擎用的帧（entry 按当天所在月的买点组合）, PARAMS_TD {(票, 成交日): 那一笔的止损 / 吊灯 / 持有天数（按信号月）})。"""
    pos_of = pd.Series(np.arange(len(days)), index=days)
    fr, td = {}, {}
    for t, df in fa.items():
        pos = pos_of.reindex(df.index).to_numpy()
        mo = np.array([mon(x) for x in df.index], int)
        entry = np.zeros(len(df), bool)
        cache: dict[tuple, np.ndarray] = {}
        for m in np.unique(mo):
            k = path.get(int(m))
            if k is None:
                continue
            e = THETAS[k][:5]
            if e not in cache:
                cache[e] = entry_mask(comp[t], e)
            sel = mo == m
            entry[sel] = cache[e][sel]
        fr[t] = df.assign(entry=entry)
        for j in np.flatnonzero(entry):
            kk = int(pos[j]) + 1
            if kk < len(days):
                s, kc, H = THETAS[path[int(mo[j])]][5:]
                td[(t, str(days[kk].date()))] = replace(px, stop_loss_pct=float(s), exit_chandelier_k=float(kc), max_hold_days=int(H))
    return fr, td


def verdict(c: str, acct: dict[str, dict], acct0: dict[str, dict], pl95_j: float | None) -> tuple[str, list[str]]:
    """五 a / b / c → (标签, 没满足的条件)。acct / acct0：{Z/E/J: {calmar, dd, n}}。"""
    f = []
    for t in ("E", "J"):
        x, y = acct.get(t) or {}, acct0.get(t) or {}
        if None in (x.get("calmar"), y.get("calmar"), x.get("dd"), y.get("dd")):
            f.append(f"a {t} 账户没有值")
            continue
        if x["calmar"] < y["calmar"] + CAL_UP:
            f.append(f"a {t} Calmar {x['calmar']:.3f} < 现行 {y['calmar']:.3f} + {CAL_UP}")
        if x["dd"] < y["dd"] - DD_TOL:
            f.append(f"a {t} 回撤 {x['dd']:.2f}% 比现行 {y['dd']:.2f}% 深 {DD_TOL:.0f} pp 以上")
    xz, yz = acct.get("Z") or {}, acct0.get("Z") or {}
    if xz.get("calmar") is None or yz.get("calmar") is None:
        f.append("a Z 账户没有值")
    elif xz["calmar"] < yz["calmar"] - Z_TOL:
        f.append(f"a Z Calmar {xz['calmar']:.3f} < 现行 {yz['calmar']:.3f} − {Z_TOL}")
    xj = (acct.get("J") or {}).get("calmar")
    if pl95_j is None or xj is None:
        f.append("b 安慰剂没有值")
    elif not xj > pl95_j:
        f.append(f"b J Calmar {xj:.3f} ≤ 安慰剂 95 分位 {pl95_j:.3f}")
    for t in ("E", "J"):
        n = (acct.get(t) or {}).get("n") or 0
        if n < MIN_TRADES:
            f.append(f"c {t} 只有 {n} 笔（< {MIN_TRADES}）")
    return ("通过" if not f else "不通过"), f


def path_summary(path: dict[int, int], a: int, b: int) -> dict:
    ks = [path[m] for m in range(a, b + 1) if path.get(m) is not None]
    if not ks:
        return {"changes": 0}
    ths = [THETAS[k] for k in ks]
    out = {"changes": int(sum(1 for x, y in zip(ks[:-1], ks[1:]) if x != y)), "first": ths[0], "last": ths[-1],
           "pct_theta0": round(100 * sum(1 for k in ks if k == K0) / len(ks), 1)}
    for j, key in enumerate(PKEYS):
        vs = [t[j] for t in ths]
        out[key] = [min(vs), max(vs)]
    return out


def th_str(th) -> str:
    if th is None:
        return "—"
    md = "不限" if th[3] == 0 else str(th[3])
    w2 = "关" if th[4] == 0 else f"{th[4]:g}"
    return f"({th[0]} 天 / {th[1]:g}% / ×{th[2]:g} / 出货 {md} / W2 {w2} / 止损 {th[5]:g}% / 吊灯 {th[6]:g} / {th[7]} 天)"


# ───────────────────────── 宏观 / 结构序列 ─────────────────────────
def month_end_map(s: pd.Series, lag_months: int = 1) -> dict[int, float]:
    """日 / 月序列 → {月序号 m: m − lag 月最后一个值}（m 月用的是 m−1 月底的值）。"""
    s = s.dropna()
    if not len(s):
        return {}
    me = s.groupby([s.index.year, s.index.month]).last()
    return {int(y) * 12 + int(mm) - 1 + lag_months: float(v) for (y, mm), v in me.items()}


def macro_monthly(P: dict, days: pd.DatetimeIndex, cols=None) -> dict[str, dict[int, float]]:
    """14 条序列 → {键: {月序号: 值}}；取不到的键跳过（只影响描述表）。cols = 面板里属于这个年代股票池的列（成交额只算它们）。"""
    from qbreak import factors as F
    from qbreak import paths
    out: dict[str, dict[int, float]] = {}
    try:
        j = F.jgb_curve()
        out["jgb10y"], out["jgb2y"] = month_end_map(j["10Y"]), month_end_map(j["2Y"])
    except Exception as e:                                                   # noqa: BLE001
        say(f"- 国债曲线取不到：{e}")
    for key, sid in (("jp_rate", "IRSTCI01JPM156N"), ("us10y", "DGS10"), ("us2y", "DGS2"), ("fed", "DFF"), ("vix", "VIXCLS"), ("baa", "BAA10Y")):
        try:
            out[key] = month_end_map(F.fred(sid), lag_months=2 if key == "jp_rate" else 1)
        except Exception as e:                                               # noqa: BLE001
            say(f"- {key} 取不到：{e}")
    if "us10y" in out and "us2y" in out:
        out["us2s10s"] = {m: out["us10y"][m] - out["us2y"][m] for m in out["us10y"] if m in out["us2y"]}
    try:
        fx = pd.read_csv(paths.PROJECT_ROOT / "var" / "cache" / "JPY=X_27y.csv", index_col=0, parse_dates=True)["Close"].astype(float)
        out["usdjpy"] = month_end_map(fx)
        out["usdjpy_chg12"] = {m: (v / out["usdjpy"][m - 12] - 1) * 100 for m, v in out["usdjpy"].items() if m - 12 in out["usdjpy"]}
    except Exception as e:                                                   # noqa: BLE001
        say(f"- USD/JPY 取不到：{e}")
    try:
        from bullbear_study import SYM, load
        nk = load(*SYM["JP"])["Close"].astype(float)
        me = month_end_map(nk)
        out["n225_ret12"] = {m: (v / me[m - 12] - 1) * 100 for m, v in me.items() if m - 12 in me}
        vol = nk.pct_change().rolling(20).std() * np.sqrt(250) * 100
        out["n225_vol20"] = month_end_map(vol)
    except Exception as e:                                                   # noqa: BLE001
        say(f"- 日経225 取不到：{e}")
    Cc, Vv = (P["C"], P["V"]) if cols is None else (P["C"][:, cols], P["V"][:, cols])
    with np.errstate(invalid="ignore"):
        turn = np.nansum(np.where(np.isfinite(Cc) & np.isfinite(Vv), Cc * Vv, 0.0), axis=1)
    ts = pd.Series(turn, index=days)
    ts = ts[ts > 0]
    mm = ts.groupby([ts.index.year, ts.index.month]).mean()
    out["turnover"] = {int(y) * 12 + int(mo) - 1 + 1: float(np.log10(v)) for (y, mo), v in mm.items()}
    out["turn_chg12"] = {m: v - out["turnover"][m - 12] for m, v in out["turnover"].items() if m - 12 in out["turnover"]}
    return out


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import jq_study as JS
    import leap_confirm as LF
    import sell_confirm as SCF
    from qbreak import exit_rules as EXR
    from qbreak import paths
    from qbreak import score_forward as SF
    from qbreak.config import ExecConfig, universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    assert (px.exit_chandelier_k, px.stop_loss_pct, px.max_hold_days, px.trailing_arm_pct, px.time_stop_days, px.atr_stop_mult) == (CHAND[1], STOP[1], HOLD[1], 0, 0, 0), px
    assert not px.exit_on_macd_dead_cross and not px.exit_sar_flip, px                     # 快速逐笔没有死叉 / SAR 卖法（现行 X6 模式两者都关）
    assert (px.range_n, px.range_x_pct, px.vol_mult, px.max_distribution_days, px.min_weekly_vol_ratio, px.max_upper_shadow_ratio) == (60, 15.0, 1.5, 6, 1.0, UPPER_SHADOW), px
    tp, trail = float(px.take_profit_pct), float(px.trailing_stop_pct)
    cx_min = float(px.climax_min_gain_pct) if px.exit_on_climax else None
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    exc = ExecConfig.for_market("JP", "tachibana")
    slip, gap = exc.slippage_pct / 100, float(exc.max_entry_gap_pct)
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/sel_monthly_study.py", "scripts/candle_portfolio.py", "scripts/bnf_adapt_study.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 现行选股方案拆成每月：各参数逐月增 / 减 × 利率 / 国债 / 成交额 → 月度规则 walk-forward（登记检验，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/sel_monthly_study.py 开头（先提交后只跑一次）。账户 = 现行框架（S0C2 + 核心 + 牛熊分界 + 宏观 / 状态层）里只换买卖点参数；快速逐笔按平仓月入账。")
    say(f"网格 8 参数 × 3 档 = {len(THETAS):,} 组；θ0 = 现行 {th_str(THETA0)}；止盈 {tp:g}%、跟踪 {trail:g}%、放量阴线离场 {'浮盈 ≥ ' + str(cx_min) + '%' if cx_min is not None else '关'}、滑点 {slip * 100:.2f}% × 2、手续费 {rt:.2f}%。")
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    seeds = 2 if SMOKE else PLACEBO_SEEDS

    ctxs, F, COMP, TAB, WIN, MAC, KEEP = {}, {}, {}, {}, {}, {}, {}
    SIGY: dict[str, dict] = {}
    for era in ERAS:
        t1 = time.time()
        ctx = LF.context(era, names=smoke_names) if (SMOKE and era != "J") else LF.context(era)
        if SMOKE and era == "J":
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in set(smoke_names)]
        fa = LF.frames(ctx, p0)
        keep = LF.w2_keep(ctx, fa)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        comp = components(ctx, fa, p0)
        bad = 0
        for t, df in fa.items():
            ref = df["entry"].to_numpy(bool) & np.asarray(keep[t], bool)
            bad += int((entry_mask(comp[t], THETA0[:5]) != ref).sum())
        if bad:
            raise RuntimeError(f"{era}：按 θ0 重建的买点与现行（compute_indicators + W2）有 {bad} 处不一致 → 停止")
        days = pd.DatetimeIndex(ctx["days"])
        rows = fwd_rows(fa, comp, slip, days, gap=gap)
        months, S, C = month_table(rows, slip, rt, tp, trail, cx_min)
        ctxs[era], F[era], COMP[era], TAB[era], WIN[era], KEEP[era] = ctx, fa, comp, (months, S, C), (a, b), keep
        MAC[era] = macro_monthly(ctx["P"], days, list(ctx["cols"]))
        sig0 = rows["M"][:, E_INDEX[THETA0[:5]]]
        yrs = pd.DatetimeIndex(rows["date"][sig0]).year
        SIGY[era] = {int(y): int(n) for y, n in pd.Series(yrs).value_counts().sort_index().items()}
        say(f"- {era}（{a}〜{b}）：{len(fa)} 只；现行买点重建一致；候选行 {len(rows['entry']):,}（其中 θ0 成立 {int(sig0.sum())}）、{len(months)} 个月；{round(time.time() - t1)} s")

    # ── 二 每个参数逐月的增减（OAT）+ 三 与宏观的相似处 ──
    GAIN: dict[str, dict[int, list]] = {}
    OATV: dict[str, dict[int, list]] = {}
    RAW: dict[str, dict] = {}
    YG: dict[str, dict[int, list]] = {}
    OATN: dict[str, dict[int, list]] = {}
    for era in ERAS:
        months, S, C = TAB[era]
        a, b = mon(WIN[era][0]), mon(WIN[era][1])
        g, v, nn = {}, {}, {}
        for m in range(a, b + 1):
            cols = np.flatnonzero((months >= m - W_OAT) & (months < m))
            vals, gains, _, ns = oat_month(S, C, cols)
            g[m], v[m], nn[m] = gains, vals, ns
        GAIN[era], OATV[era], OATN[era] = g, v, nn
        RAW[era] = A.theta_path_insample(months, S, C, a, b, win=W_JOINT, hyst=0.0)
        YG[era] = yearly_gains(months, S, C, a, b)
    say("\n## 一、每个参数逐月的增 / 减（其余 7 个放现行，只动一个；36 个月内平仓的笔，每档 ≥ 20 笔；该动的月份 = 最好那档比现行好 0.25 pp 以上）")
    say("| 参数 | " + " | ".join(f"{e}：增 / 不动 / 减（% 月） · 平均增减度（大 − 小，pp / 笔）" for e in ERAS) + " |")
    say("|---|" + "---|" * len(ERAS))
    DIR: dict[str, dict] = {}
    for j, name in enumerate(PNAMES):
        cells = []
        for era in ERAS:
            vs = np.array([OATV[era][m][j] for m in OATV[era]], float)
            vs = np.where(np.isnan(vs), -1, vs)
            grid = np.array([(np.inf if (j == 3 and g == 0) else g) for g in GRIDS[j]], float)
            cur = grid[1]
            vv = np.array([(np.inf if (j == 3 and x == 0) else x) for x in vs], float)
            up, dn = float((vv > cur).mean() * 100), float((vv < cur).mean() * 100)
            gs = np.array([GAIN[era][m][j] for m in GAIN[era]], float)
            mg = float(np.nanmean(gs)) if np.isfinite(gs).any() else np.nan
            nfin = int(np.isfinite(gs).sum())
            mg_txt = f"{mg:+.2f}" if np.isfinite(mg) else "—"
            cells.append(f"{up:.0f} / {100 - up - dn:.0f} / {dn:.0f} · {mg_txt}（{nfin} 个月有值）")
            DIR.setdefault(era, {})[PKEYS[j]] = {"up": up, "down": dn, "mean_gain": (None if not np.isfinite(mg) else mg), "n_months": nfin}
        say(f"| {name} | " + " | ".join(cells) + " |")
    PERS = persistence(YG)
    fmt_pct = lambda x: "—" if x is None else f"{x:.0f}%"                                 # noqa: E731
    fmt_rho = lambda x: "—" if x is None else f"{x:+.2f}"                                  # noqa: E731
    say("持续性（按日历年、不重叠；相邻两年增减度同号的比例 / Spearman，三个年代合并）：" + "；".join(
        f"{PNAMES[j]} {fmt_pct(PERS[k]['same_sign_pct'])} / {fmt_rho(PERS[k]['rho'])}（{PERS[k]['n_pairs']} 对）" for j, k in enumerate(PKEYS)))
    say("「联合最好」（6,561 组里以 m 为止 36 个月最好的一组，样本内）换的次数：" + "；".join(
        f"{e} {sum(1 for x, y in zip(list(RAW[e].values())[:-1], list(RAW[e].values())[1:]) if x != y)} 次 / {len(RAW[e])} 个月" for e in ERAS))

    say("\n## 二、和当月宏观 / 结构状态的相似处（每个参数的增减度 g_j(m) 与 m−1 月底的序列值的 Spearman ρ；格 = Z / E / J · 年度（三段合并、不重叠）；★ = |ρ| ≥ 0.3 且 E、J 同号）")
    say("（36 个月滚动的增减度相邻月份重叠 35/36 → 月度 ρ 的显著被高估，看「年度」那个数更稳；全部只描述。）")
    say("| 参数 | " + " | ".join(MACRO_ZH[k] for k in MACRO_KEYS) + " |")
    say("|---|" + "---|" * len(MACRO_KEYS))
    RHO: dict = {}
    stars = []
    for j, name in enumerate(PNAMES):
        cells = []
        for key in MACRO_KEYS:
            rr = {}
            for era in ERAS:
                ms = sorted(GAIN[era])
                x = [MAC[era].get(key, {}).get(m, np.nan) for m in ms]
                y = [GAIN[era][m][j] for m in ms]
                rr[era] = spearman(x, y)
            yx = [MAC[e].get(key, {}).get(mon(f"{y}-01-01"), np.nan) for e in ERAS for y in YG[e]]
            yy = [YG[e][y][j] for e in ERAS for y in YG[e]]
            ry = spearman(yx, yy)
            RHO.setdefault(PKEYS[j], {})[key] = {**{e: {"rho": (None if not np.isfinite(rr[e][0]) else round(rr[e][0], 3)), "n": rr[e][1]} for e in ERAS},
                                                 "year": {"rho": (None if not np.isfinite(ry[0]) else round(ry[0], 3)), "n": ry[1]}}
            rE, rJ = rr["E"][0], rr["J"][0]
            star = np.isfinite(rE) and np.isfinite(rJ) and abs(rE) >= RHO_MIN and abs(rJ) >= RHO_MIN and np.sign(rE) == np.sign(rJ)
            if star:
                stars.append((name, MACRO_ZH[key], rr["Z"][0], rE, rJ))
            cells.append(("★" if star else "") + " / ".join(("—" if not np.isfinite(rr[e][0]) else f"{rr[e][0]:+.2f}") for e in ERAS)
                         + " · " + ("—" if not np.isfinite(ry[0]) else f"{ry[0]:+.2f}"))
        say(f"| {name} | " + " | ".join(cells) + " |")
    if stars:
        say("有对应的（E、J 同号且 |ρ| ≥ 0.3）：" + "；".join(f"{a} × {b}：Z {('—' if not np.isfinite(z) else f'{z:+.2f}')} / E {e:+.2f} / J {j:+.2f}" for a, b, z, e, j in stars))
    else:
        say("没有一对参数 × 序列在 E、J 都达到 |ρ| ≥ 0.3 且同号。")
    n_star_act, mx_act = star_count(GAIN, MAC)
    null_n, null_mx = null_stars(GAIN, MAC, draws=(20 if SMOKE else NULL_DRAWS))
    n95, mx95 = float(np.percentile(null_n, 95)), float(np.percentile(null_mx, 95))
    say(f"零假设对照（序列在年代内循环平移 ≥ {NULL_SHIFT_MIN} 个月，{len(null_n)} 次）：★ 数 实际 {n_star_act} vs 零分布中位 {np.median(null_n):.0f} / 95 分位 {n95:.0f}；"
        f"max|ρ| 实际 {mx_act:.2f} vs 零分布 95 分位 {mx95:.2f} → {'实际 ★ 数超过零分布的 95 分位' if n_star_act > n95 else '实际 ★ 数没有超过零分布的 95 分位 → 不算「有对应」'}")
    say(f"（8 参数 × {len(MACRO_KEYS)} 序列 × 3 年代 = {8 * len(MACRO_KEYS) * 3} 个相关；单个 ★ 不说明什么，读法见开头「三」。）")

    say("\n## 三、逐年的最优方向（每个参数逐年最常选的档；只描述）")
    say("| 年 | " + " | ".join(PNAMES) + " |")
    say("|---|" + "---|" * len(PNAMES))
    by_year: dict = {}
    for era in ERAS:
        yrs = sorted({m // 12 for m in OATV[era]})
        for y in yrs:
            ms = [m for m in OATV[era] if m // 12 == y]
            row = []
            for j in range(8):
                vs = [OATV[era][m][j] for m in ms]
                mode = max(set(vs), key=vs.count)
                txt = ("不限" if (j == 3 and mode == 0) else ("关" if (j == 4 and mode == 0) else f"{mode:g}"))
                row.append(txt if mode != THETA0[j] else "=")
                by_year.setdefault(f"{era} {y}", {})[PKEYS[j]] = mode
            say(f"| {era} {y} | " + " | ".join(row) + " |")

    # ── 四 账户 ──
    PATH: dict[str, dict[str, dict[int, int]]] = {c: {} for c in CANDS}
    ACCT: dict[str, dict] = {}
    MISS: dict[str, int] = {}
    PLAC: dict[str, list] = {}
    PLAC2: dict[str, list] = {}
    for era in ERAS:
        t1 = time.time()
        ctx, fa, comp = ctxs[era], F[era], COMP[era]
        months, S, C = TAB[era]
        a, b = WIN[era]
        ma, mb = mon(a), mon(b)
        days = pd.DatetimeIndex(ctx["days"])
        run_fn = LF.runner(ctx, fa)
        r0 = LF.run(ctx, run_fn, LF.with_mask(fa, KEEP[era]), px)
        ACCT[era] = {"现行": r0[era]}

        def acct_of(path: dict[int, int]) -> dict:
            fr, td = build(fa, comp, days, path, px)
            r = LF.run(ctx, run_fn, fr, px, params_td=td)
            tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
            miss = 0
            if len(tr):
                tr = tr[tr["ticker"] != "1655.T"]
                miss = int(sum((t, d) not in td for t, d in zip(tr["ticker"], tr["entry_date"])))
            MISS[era] = MISS.get(era, 0) + miss
            return {**r[era], "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")], "td_miss": miss}

        rk0 = acct_of({m: K0 for m in range(ma, mb + 1)})
        ACCT[era]["θ0 重建"] = rk0
        same = r0[era].get("calmar") is not None and rk0.get("calmar") is not None and abs(r0[era]["calmar"] - rk0["calmar"]) < 1e-9
        say(f"- {era} 现行账户 Calmar {r0[era].get('calmar')} vs θ0 重建 {rk0.get('calmar')} → {'一致' if same else '**不一致（要查）**'}")
        PATH["C1"][era] = wf(months, S, C, ma, mb, K0, W_JOINT)
        PATH["C2"][era] = wf(months, S, C, ma, mb, K0, W_EW, HALF)
        PATH["C3"][era], _ = oat_path(months, S, C, ma, mb)
        lab4 = bucket_labels(MAC[era].get("jgb10y", {}))
        PATH["C4"][era] = bucket_path(months, S, C, ma, mb, lab4, K0)
        lab5 = bucket_labels(MAC[era].get("turnover", {}))
        PATH["C5"][era] = bucket_path(months, S, C, ma, mb, lab5, K0)
        for c in CANDS:
            ACCT[era][c] = acct_of(PATH[c][era])
        ACCT[era]["上限"] = acct_of(A.oracle_path(months, S, C, ma, mb, K0))
        PLAC[era] = [acct_of(random_path(ma, mb, s)).get("calmar") for s in range(seeds)]
        PLAC2[era] = [acct_of(neighbour_path(ma, mb, s)).get("calmar") for s in range(seeds)]
        say(f"- {era} 账户算完：{round(time.time() - t1)} s")

    if any(MISS.values()):
        raise RuntimeError(f"PARAMS_TD miss ≠ 0：{MISS} → 停止")
    for e in ERAS:
        if "jgb10y" not in MAC[e] or "turnover" not in MAC[e]:
            raise RuntimeError(f"{e}：C4 / C5 用的序列取不到 → 停止")
    pl = {e: [v for v in PLAC[e] if v is not None] for e in ERAS}
    pl2 = {e: [v for v in PLAC2[e] if v is not None] for e in ERAS}
    pl95 = {e: (float(np.percentile(pl[e], 95)) if pl[e] else None) for e in ERAS}
    pl95b = {e: (float(np.percentile(pl2[e], 95)) if pl2[e] else None) for e in ERAS}
    plmed = {e: (float(np.median(pl[e])) if pl[e] else None) for e in ERAS}
    plmed2 = {e: (float(np.median(pl2[e])) if pl2[e] else None) for e in ERAS}
    bar_j = (max(pl95["J"], pl95b["J"]) if pl95["J"] is not None and pl95b["J"] is not None else None)
    res = {}
    acct0 = {e: ACCT[e]["现行"] for e in ERAS}
    for c in CANDS:
        acct = {e: ACCT[e][c] for e in ERAS}
        lab, fails = verdict(c, acct, acct0, bar_j)
        g = [acct[e]["calmar"] - acct0[e]["calmar"] for e in ("E", "J") if acct[e].get("calmar") is not None and acct0[e].get("calmar") is not None]
        res[c] = {"label": lab, "fails": fails, "gain": (min(g) if len(g) == 2 else None),
                  "paths": {e: path_summary(PATH[c][e], mon(WIN[e][0]), mon(WIN[e][1])) for e in ERAS}}
    passed = sorted([c for c in CANDS if res[c]["label"] == "通过"], key=lambda c: -res[c]["gain"])
    pick = passed[0] if passed else None
    fmt = lambda x, f="{:+.2f}": ("—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x))  # noqa: E731
    cell = lambda s: f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')} · {s.get('n') or 0} 笔 {fmt(s.get('mean'))}%"  # noqa: E731
    say("\n## 四、整个账户（年化 / 最大回撤 / Calmar · 个股笔数 每笔；现行框架里只换买卖点参数）")
    say("| 做法 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 |")
    say("|---|---|---|---|")
    say("| 现行 θ0 | " + " | ".join(cell(ACCT[e]["现行"]) for e in ERAS) + " |")
    for c in CANDS:
        say(f"| {c} {CANDS[c]} | " + " | ".join(cell(ACCT[e][c]) for e in ERAS) + " |")
    say("| 上限（作弊：每月用当月自己的逐笔选） | " + " | ".join(cell(ACCT[e]["上限"]) for e in ERAS) + " |")
    say(f"| 安慰剂 ① 乱抽（{seeds} 个种子；Calmar 中位 / 95 分位） | " + " | ".join(f"{fmt(plmed[e], '{:.3f}')} / {fmt(pl95[e], '{:.3f}')}" for e in ERAS) + " |")
    say(f"| 安慰剂 ② 近邻（每月每个参数 −1 / 0 / +1 档；{seeds} 个种子） | " + " | ".join(f"{fmt(plmed2[e], '{:.3f}')} / {fmt(pl95b[e], '{:.3f}')}" for e in ERAS) + " |")
    say("\n## 五、判定（事先写定：a E / J Calmar ≥ 现行 + 0.02、回撤不深 2 pp、Z ≥ 现行 − 0.02；b J > 两种安慰剂 95 分位的较高者；c E / J ≥ 30 笔）")
    for c in CANDS:
        r = res[c]
        say(f"- **{c}**：{r['label']}" + ("" if not r["fails"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n**结论：{('按规则选 ' + pick + '（只是提议：先做前向记录，要进模拟盘要你另外确认）') if pick else '没有候选「通过」→ 模拟盘不变'}**")
    say("PARAMS_TD miss（要 = 0）：" + " / ".join(f"{e} {MISS.get(e, 0)}" for e in ERAS))

    say("\n## 六、各候选每月的 θ（换了几次、θ0 的月份占比、范围；只描述）")
    for c in CANDS:
        for e in ERAS:
            ps = res[c]["paths"][e]
            if "first" not in ps:
                continue
            rng_txt = "、".join(f"{PNAMES[j]} {ps[k][0]:g}〜{ps[k][1]:g}" for j, k in enumerate(PKEYS) if ps[k][0] != ps[k][1])
            say(f"- {c} {e}：换 {ps['changes']} 次、θ0 占 {ps['pct_theta0']:.0f}% 的月份；{rng_txt or '全程 = θ0'}；{th_str(ps['first'])} → {th_str(ps['last'])}")
    say("\n## 七、结构（只描述）")
    say("- θ0 每年的信号数（候选行里成立的，未经名额限制）：" + "；".join(f"{e} " + " ".join(f"{y}:{n}" for y, n in SIGY[e].items()) for e in ERAS))
    for e in ERAS:
        tv = [v for m, v in MAC[e].get("turnover", {}).items() if mon(WIN[e][0]) <= m <= mon(WIN[e][1])]
        if tv:
            say(f"- {e} 股票池日均売買代金（対数，中位 / 最低 / 最高）：{np.median(tv):.2f} / {min(tv):.2f} / {max(tv):.2f}（10^x 円）")
    for e in ERAS:
        lab = bucket_labels(MAC[e].get("turnover", {}))
        rows_ = []
        for bkt, nm in ((0, "低"), (1, "中"), (2, "高")):
            gs = [GAIN[e][m][4] for m in GAIN[e] if lab.get(m) == bkt and np.isfinite(GAIN[e][m][4])]
            rows_.append(f"{nm} {np.mean(gs):+.2f}（{len(gs)} 个月）" if gs else f"{nm} —")
        say(f"- {e} 成交额分档下 W2 的增减度（1.5 − 关，pp / 笔）：" + "；".join(rows_))
    out = {"code": code, "dirty": dirty, "pick": pick, "result": res, "account": ACCT, "placebo": PLAC, "placebo_q95": pl95, "placebo_med": plmed,
           "placebo2": PLAC2, "placebo2_q95": pl95b, "placebo2_med": plmed2, "bar_j": bar_j, "persistence": PERS,
           "stars_actual": n_star_act, "max_rho_actual": mx_act, "null_stars": null_n, "null_max_rho": null_mx, "null_q95": {"stars": n95, "max_rho": mx95},
           "oat_n": {e: {mon_str(m): v for m, v in OATN[e].items()} for e in ERAS},
           "theta0": THETA0, "n_thetas": len(THETAS), "direction": DIR, "rho": RHO, "stars": [list(s) for s in stars], "by_year": by_year,
           "signals_theta0": SIGY, "td_miss": MISS,
           "paths": {c: {e: {mon_str(m): THETAS[k] for m, k in PATH[c][e].items() if k is not None} for e in ERAS} for c in CANDS},
           "oat_values": {e: {mon_str(m): v for m, v in OATV[e].items()} for e in ERAS},
           "oat_gain": {e: {mon_str(m): [None if not np.isfinite(x) else x for x in v] for m, v in GAIN[e].items()} for e in ERAS},
           "yearly_gain": {e: {str(y): [None if not np.isfinite(x) else x for x in v] for y, v in YG[e].items()} for e in ERAS},
           "raw_joint": {e: {mon_str(m): (None if k is None else THETAS[k]) for m, k in RAW[e].items()} for e in ERAS},
           "macro": {e: {k: {mon_str(m): v for m, v in s.items() if mon(WIN[e][0]) <= m <= mon(WIN[e][1])} for k, s in MAC[e].items()} for e in ERAS},
           "elapsed_s": round(time.time() - t0)}
    say(f"\n代码版本 {code}{'（有未提交的改动）' if dirty else '（与提交的版本相同）'}；用时 {out['elapsed_s']} s。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / ("sel_monthly_study_smoke" if SMOKE else "sel_monthly_study")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
