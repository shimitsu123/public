"""trendline_select_study.py — 趋势线的「质地」特征能不能优化选股（全部股票：横截面 + 结合现在的选股方法 B4）
（登记版：规则、代码与登记前个数一起提交，之后不改、只运行一次）。

来由：用户 2026-10-06「要分析现在所有股票上述生成的K线来研究趋势线优化选股算法」。
上一轮（scripts/trendline_study.py，登记 2f8b450 → 结果 4be1dca）：固定参数的趋势线，通道方向 / 破线事件对之后 20 日没有预测力；5 个手写的 B4 做法
（TLB1 周线下降通道不买、TLB2 上方周线压力太近不买、TLS1〜3 加卖点）都第一关不过（最接近 TLB2：胜率 +2.30 pp、每笔 +0.87 pp，但 2001〜2006 账户 −0.182）。
这一轮不重复那 5 个做法：换成**系统地**看趋势线在「信号日」的质地特征 —— 离线多远、线多强（碰了几次）、多陡、在通道的哪个位置、刚破线没有 ——
能不能把现行方法（B4）的信号分成好坏（= 优化选股）；并先在全部股票上看这些特征的横截面有没有信息。设计稿经三路独立审查（统计 / 泄漏 / 仓库规范）后修订再登记。

〇 定义
- 趋势线 = qbreak/trendline.py（冻结：k / L / gap / R 日 5 / 250 / 10 / 60、周 3 / 156 / 6 / 26，容差 0.3 × ATR14；不改参数）。月K：各窗口不满 L = 120 根、绝大多数信号日没有月线 → 不用。
- 特征都在第 t 天收盘为止算：日线用 t 为止的 K 线（scan 第 t 根的线）；周线用「上一根已经走完的周K（不含 t 这一周；周五也不含当周 = 保守）」的线往后延长一根（同上一轮；
  与面板 TL.summary 在周五的画法不同 —— 若任何做法以后被采用，接线要用研究的这个定义）。
- 18 个特征（FEATS；kind = cont 连续 / int 小整数 / bool）。没有特征行（这只票不到 60 根等）→ 一律 G0 不挡（bool 也是）；连续 / 整数特征没有线 → NaN = G0。
  日线 F01 d_res_atr = (压力线 − 收盘) ÷ ATR14（负 = 收盘在线上方的容差带内，最低 −0.3）；F02 d_sup_atr = (收盘 − 支撑线) ÷ ATR14；
       F03 d_pos = (收盘 − 支撑) ÷ (压力 − 支撑)（压力 ≤ 支撑 → NaN；不截断，容差带内可能 < 0 或 > 1）；F04 d_sup_slope（每根 %）；F05 d_res_slope；
       F06 d_sup_touch（碰到几次，≥ 2；int）；F07 d_res_touch（int）；F08 d_sup_len（第一个锚点到 t 几根）；F09 d_res_len；
       F10 d_rb5 = 最近 5 根（含 t）里 scan 的「收盘突破压力线」旗子有没有为真（与 t 当天有没有线无关；bool）；F11 d_sb20 = 最近 20 根里「收盘跌破支撑线」（bool）。
  周线 F12 w_res_atr = (周线压力 − 收盘) ÷ 周线 ATR14；F13 w_sup_atr；F14 w_pos；F15 w_sup_slope；F16 w_res_slope；F17 w_sup_touch（int）；F18 w_res_touch（int）。
- 分组：连续特征按 BOUNDS（--prep 从探索样本 W ∪ Jx 里 B4 会买的信号算出的三分位 [q1, q2]，写进本文件 → 冻结；--run 重算不等（atol 1e-9）→ 停）：
  G1 ≤ q1 < G2 ≤ q2 < G3，NaN = G0；q1 == q2 的连续特征没有候选、只描述。整数特征（碰到次数）事先写死：G1 = {2}、G2 = {3}、G3 = {≥ 4}。bool：1 = 否、2 = 是。
- 与上一轮（2f8b450 → 4be1dca）的重叠（照实写）：F12 / F14 = TLB2「上方周线压力线不到 1 × 周线 ATR 不买」的变体（F14 给定 F13 是 F12 的单调变换），TLB2 在 W / Jx / Zx 与
  Z / E / J 账户的结果都已公开 → 对它们没有未看过的样本 → **F12 / F14 只进 一（横截面）与 三（只描述），不算入围、不确认**；F04 / F05 / F15 / F16 的斜率三分位 = A1「通道方向」
  （两条斜率的符号组合；合起来 −0.11 pp 没用）与 TLB1 的连续版；F10 = A2 TU「突破压力」放宽到 5 根（+0.01 pp 没用）、F11 = A3 TD「跌破支撑」放宽到 20 根（−0.07 pp 没用）
  —— 这些保留为候选 / 描述但标注「上一轮横截面已判没用，此处只是换成 B4 信号过滤」。真正新的：F01 / F02 / F13（ATR 倍距离）、F03（日线通道位置）、F06 / F07 / F17 / F18
  （碰到次数 = 线的强度）、F08 / F09（线长）、系统化分组 + 秩相关、探索 → 入围 → 确认结构、同日 ≥ 2 信号的规模、Zx 自助法区间、J-Quants 全市场面板 U0。
- 族（入围用）：① 离压力 / 通道上沿 {F01, F03, F10（F12 / F14 归此族但不进候选）}；② 离支撑 / 通道下沿 {F02, F11, F13}；③ 线的方向 {F04, F05, F15, F16}；
  ④ 线的强度 / 长度 {F06, F07, F08, F09, F17, F18}。
一 全部股票横截面（只回答「这些特征在全部股票上有没有选股信息」；不改交易）
- 样本 6 个同上一轮：日経225 Z（2001-01〜2006-09）/ E（2006-10〜2016-09）/ J（2017-01〜2026-09）+ 池子 W（E 窗口）/ Jx（J 窗口，J2 行情里不在日経225 的票）/ Zx（Z 窗口）。
  「现在所有股票」在这里 = 这 6 个样本（覆盖 2001〜2026 三个时期、每期两组不同的票；今天的成员有幸存者偏差）+ 第 7 个样本 U0 = J-Quants 全市场时点面板
  （scripts/allstock_data：东证一般市場内国普通股约 4,400 只、2016-09〜2026-09、时点上市掩码、无幸存者偏差；只描述：与 J / Jx 同期、只加广度不加独立时期，
  二 的 B4 流水线只有前 6 个样本有）。U0 的样本日 = J 窗口（2017-01-04 起）每 5 个交易日一天；超额对同一天 U0 自己的等权平均。
- 之后的收益 = 第 t + 1 天开盘买、第 t + 20 天收盘（%；「天」= 这只票自己有收盘的 K 线，停牌 / 缺行的票日期上会略长 —— 同上一轮）；超额 = 减去同一天同一样本全部票（算得出的）的等权平均。
  每 5 个交易日取一天（同一批样本日也用于秩相关）。--prep 的 rows / sample_rows / have_pct 含之后收益算不出的最后 20 根（U0 除外）；--run 的面板不含 → 略小。
- 每个特征每一天：连续 → 当天有值的票按名次三分位，差 = 高组平均超额 − 低组平均超额；整数 → {≥ 4} − {2}；bool → 是 − 否（两组各 ≥ 5 只）。
- 标准误按月聚类（CR0）；「有信息」= 6 个样本的差同号、合起来 95% 区间不含 0、|平均| ≥ 0.3 pp（与上一轮同一门槛；方向不事先定 → 双侧）。U0 另列（同号与否只描述）。
- 照实写：Z 与 Zx、E 与 W、J 与 Jx 两两同一批月份 → 「6 个样本同号」读作「3 个窗口 × 2 个样本」；零假设下 18 个特征按「3 个独立窗口同号 × 区间不含 0」估，
  期望约 0.5〜0.7 个被标「有信息」（|平均| ≥ 0.3 pp 会再筛掉大半）。只描述：每个样本日的 Spearman 秩相关的平均；各特征的有值比例。
二 结合 B4 选股（探索 → 入围 → 确认；标准运行前写死）
- 基准 B4 = B3 + TBF（模拟盘现在的规则）；先决条件同上一轮：规则指纹 1241753c8f2529c6、B4 重算 = turn_shape_combo 的 TBF 账户（trendline_study.same_b4）、接线核对 + BOUNDS 核对。
- 做法 = 「某一组信号不开新仓」（em_tick 0；名额留给下一个候选、钱留在核心；TBF 挡的照旧不买）。候选 = F12 / F14 以外的 16 个特征各一个做法 TQ01〜TQ18（ID 以前没用过；TQ12 / TQ14 不用）：
  做法 = 挡 G1 与 G3 里 Jx 上平均净收益低的那一端（G2 与 G0 永远不挡；G0 = 「缺值 → 保留」；与 一 的「高 − 低」同一口径）；bool：挡 是 / 否 里低的一边。
  —— 组的选择用到了 Jx 的结果 → 这些做法都算「看了数据设计的」→ posthoc = True（V6 Zx 必须同方向）。
- 探索样本：池子 W（E 窗口；B4 会买的信号）与 Jx（J 窗口）的假想单笔（每个信号单独买、X6 离场、扣费用；同上一轮 pool_stats 买点）：保留的 vs 全部。
  只对 W / Jx 算分组表与差；Zx 与日経225 账户在确认之前不算、不看。
- 入围（全部满足；按 Jx 每笔差从大到小最多 3 个、同一族最多 1 个）：
  a 挡掉的比例 = 被挡 ÷ 该池子 B4 会买的全部信号（含 G0），Jx 与 W 都在 10〜70%；
  b Jx：胜率差 ≥ +2.0 pp 且每笔差 ≥ +0.20 pp（选择本身在零假设下约给 +0.2 pp → b 只是下限，主判定是 d）；
  c W：胜率差 > 0 且每笔差 ≥ 0；
  d Jx：每笔差 > 随机对照 200 次的 95 分位。随机对照 = 把 Jx 有值信号的组标签随机重排（G1 / G2 / G3 各组个数不变、G0 不动；bool = 是 / 否 个数不变），
    按与候选同一条规则挡「重排后 Jx 平均净收益低的那一端」、算保留 vs 全部的每笔差；第 s 次的种子 numpy.random.default_rng([20261006, 12, i, s])（i = 特征序号 0〜17，s = 0〜199）。
    这个对照重复了「看 Jx 结果挑组」的选择步骤。
- 确认（只对入围的）：Z / E / J 的 B4 账户挡掉同一组（界线、组冻结）→ research_loop11.stage1(cand, base, other = {W, Jx, Zx}, posthoc = True)：
  路线 A 账户（A1 Calmar 差合计 ≥ +0.03、A2 每个年代 ≥ −0.02 / 回撤不深 2 pp / 两半 ≥ −0.02、A3 胜率差 ≥ −2 pp）或 路线 B 成功率（B1 合起来胜率差 ≥ +2 pp 且每笔差 ≥ 0、
  B2 每个年代 ≥ −2 pp、B3 账户不变差）任一条 + V4（W / Jx 同方向 —— 照实写：探索用过的样本，对入围者自动通过）+ V6（Zx 没看过：路线 B 胜率差 > 0 且每笔差 ≥ 0；路线 A 每笔差 > 0）。
  另两条事先写死（在 stage1 之外）：规模 = 被挡组在每个年代 TBF 没挡的日経225 W2 信号里占比 ≥ 10%，否则那个年代「规模不足」；跨时期 = Z 年代胜率差 ≥ 0 且 Zx 每笔差 > 0。
  「候选（第一关）」= stage1 过 且 三个年代规模够 且 跨时期成立 → 第二关（随机挡 400 次）另行登记后只运行一次；两关都过也只是候选，进模拟盘要用户决定。
  只描述：Zx 每笔差的 95% 区间（按信号月聚类的自助法 2,000 次，种子 20261006；半宽预期约 0.6〜0.7 pp，几乎必然含 0 → V6 只是符号检验）；
  探索样本两半（Jx 2017〜2021 / 2022〜2026、W 2006-10〜2011-09 / 2011-10〜2016-09）各自的每笔差。
- 没有入围 → 这一轮到此为止（Zx 与日経225 账户不用）。
三 只描述（不判定）：W / Jx 全部特征 × 组的个数 / 胜率 / 每笔（探索全表）；Zx 的分组 / 每笔差 / 区间与 B4 实际成交（Z / E / J）信号日的分组只对入围者算；
   同一天 ≥ 2 个 B4 会买的信号的日子有多少（排名问题的规模；假想单笔检验不了排名）。
四 事前预期（运行前写）：16 个候选按 d 在零假设下预期假入围约 0.3〜0.5 个 → 「入围 0〜1 个」与零假设无法区分，入围 ≠ 证据；真正的证据只看确认（Z 账户 + Zx 的符号）。
   入围者「候选（第一关）」的机会 < 10%。横截面：没有一个特征到 0.3 pp（上一轮事件 / 通道都只 ±0.1 pp）。
   本设计的结论上限 = 「候选 → 前向记录」，不是「更好」：探索（W / Jx）与确认（E / J）同期，V4 对入围者自动通过；跨时期的只有 Z（28 笔，一笔 = 3.6 pp 胜率）与 Zx 的符号。
五 局限：同上一轮（幸存者偏差、调整后价、重叠样本）+ 探索与确认的窗口重叠；候选的组选择看了 Jx 的结果（以重排对照 + posthoc 处理）；多重检验 18 个特征；
   信号样本小。模拟盘 / 执行器不因这次研究改。非投资建议。
用法：python scripts/trendline_select_study.py --prep（算特征 + 先决条件 + 三分位界线 + 只数个数；缓存 var/cache/trendline_select_flags.pkl / _u0.pkl，不入库）；
      python scripts/trendline_select_study.py --run（只运行一次：一 + 二 + 三）。
输出：var/out/trendline_select_study.md / .json（只有汇总统计，没有个股名单）。非投资建议。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pickle
import subprocess
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qbreak import kline as K                                               # noqa: E402
from qbreak import trendline as TL                                          # noqa: E402
import trendline_study as TS                                                # noqa: E402

# 特征：ID → (列名, 说明, kind)；kind = cont / int / bool
FEATS = {
    "F01": ("d_res_atr", "离日线压力线（ATR 倍）", "cont"),
    "F02": ("d_sup_atr", "离日线支撑线（ATR 倍）", "cont"),
    "F03": ("d_pos", "在日线通道的位置（0 = 支撑、1 = 压力）", "cont"),
    "F04": ("d_sup_slope", "日线支撑线斜率（%/根）", "cont"),
    "F05": ("d_res_slope", "日线压力线斜率（%/根）", "cont"),
    "F06": ("d_sup_touch", "日线支撑线碰到几次", "int"),
    "F07": ("d_res_touch", "日线压力线碰到几次", "int"),
    "F08": ("d_sup_len", "日线支撑线有多长（根）", "cont"),
    "F09": ("d_res_len", "日线压力线有多长（根）", "cont"),
    "F10": ("d_rb5", "最近 5 根里突破过日线压力线", "bool"),
    "F11": ("d_sb20", "最近 20 根里跌破过日线支撑线", "bool"),
    "F12": ("w_res_atr", "离周线压力线（周线 ATR 倍）", "cont"),
    "F13": ("w_sup_atr", "离周线支撑线（周线 ATR 倍）", "cont"),
    "F14": ("w_pos", "在周线通道的位置", "cont"),
    "F15": ("w_sup_slope", "周线支撑线斜率（%/根）", "cont"),
    "F16": ("w_res_slope", "周线压力线斜率（%/根）", "cont"),
    "F17": ("w_sup_touch", "周线支撑线碰到几次", "int"),
    "F18": ("w_res_touch", "周线压力线碰到几次", "int"),
}
FIDS = tuple(FEATS)
COLS = [FEATS[f][0] for f in FIDS]
NO_CAND = ("F12", "F14")                                                     # 上一轮 TLB2 的变体：Zx 与账户结果已见过 → 只进横截面与只描述
CAND_IDS = tuple(f for f in FIDS if f not in NO_CAND)
CAND = {f: "TQ" + f[1:] for f in FIDS}                                      # F01 → TQ01（做法 ID；TQ12 / TQ14 不用）
FAMILY = {"① 离压力 / 通道上沿": ("F01", "F03", "F10", "F12", "F14"), "② 离支撑 / 通道下沿": ("F02", "F11", "F13"),
          "③ 线的方向": ("F04", "F05", "F15", "F16"), "④ 线的强度 / 长度": ("F06", "F07", "F08", "F09", "F17", "F18")}   # F12 / F14 只是归类，不进候选
FAM_OF = {f: name for name, fs in FAMILY.items() for f in fs}
INT_CUTS = (2, 3)                                                            # 整数特征：G1 = {2}、G2 = {3}、G3 = {≥ 4}
SAMPLES, SM_KEY, WIN_ERA, FOLD = TS.SAMPLES, TS.SM_KEY, TS.WIN_ERA, TS.FOLD
N225_ERAS, POOLS = TS.N225_ERAS, TS.POOLS
EXPLORE = ("W", "Jx")                                                        # 探索样本（二）
UNSEEN = "Zx"                                                                # 没看过的池子（V6）
U0 = "U0"                                                                    # 一 的第 7 个样本：J-Quants 全市场时点面板（只描述）
U0_START = "2017-01-04"
H, EVERY, MIN_GROUP, MIN_PP = TS.H, TS.EVERY, TS.MIN_GROUP, TS.MIN_PP
RB_N, SB_N = 5, 20                                                           # F10 / F11 回看几根
BLOCK_LO, BLOCK_HI = 0.10, 0.70                                              # a：挡掉的比例（分母 = 该池子 B4 会买的全部信号，含 G0）
WIN_MIN, MEAN_MIN = 2.0, 0.20                                                # b：Jx 胜率差 / 每笔差
PLACEBO_N, PLACEBO_SEED = 200, (20261006, 12)                                # d：组标签重排 → 挑最差一端
BOOT_N, BOOT_SEED = 2000, 20261006                                           # Zx 每笔差的区间（只描述）
MAX_FINAL, FAM_CAP = 3, 1
SCALE_MIN = 0.10                                                             # 规模：被挡组在该年代 TBF 没挡的日経225 信号里占比
HALVES = {"Jx": ("2017-01-01", "2022-01-01", "2026-10-01"), "W": ("2006-10-01", "2011-10-01", "2016-10-01")}   # 探索样本两半（只描述）
GROUP_NAMES = {0: "G0 没有线", 1: "G1 低", 2: "G2 中", 3: "G3 高"}
INT_NAMES = {0: "G0 没有线", 1: "G1 碰 2 次", 2: "G2 碰 3 次", 3: "G3 碰 ≥ 4 次"}
BOOL_NAMES = {0: "G0 没有特征行", 1: "否", 2: "是"}
FP, B4_TOL = TS.FP, TS.B4_TOL
FLAGS_CACHE, U0_CACHE = "trendline_select_flags.pkl", "trendline_select_u0.pkl"
OUT_MD, OUT_JSON = "trendline_select_study.md", "trendline_select_study.json"
STOCK_SKIP = TS.STOCK_SKIP
# 连续特征的三分位界线 [q1, q2]（--prep 2026-10-06 从 W ∪ Jx 里 B4 会买的信号（303 + 606 个）算出 → 冻结；--run 重算不等 → 停）。
BOUNDS: dict[str, list[float]] = {
    "F01": [0.29703471064567566, 1.667015552520752], "F02": [2.3390119075775146, 3.649840831756592],
    "F03": [0.6249657869338989, 0.9215810894966125], "F04": [-0.012178996577858925, 0.058199863880872726],
    "F05": [-0.0431085042655468, 0.03924954682588577], "F08": [75.0, 129.0], "F09": [68.0, 123.0],
    "F12": [0.14666905502478275, 1.3336836099624627], "F13": [1.0587513844172156, 2.2746685345967608],
    "F14": [0.5093240141868591, 0.9500097632408142], "F15": [0.0011319669235187158, 0.2760010659694671],
    "F16": [-0.2396311114231746, 0.061868431667486824],
}


def names_of(fid: str) -> dict:
    return {"cont": GROUP_NAMES, "int": INT_NAMES, "bool": BOOL_NAMES}[FEATS[fid][2]]


# ───────────────────────── 一只票的特征（只用到当天为止的 K 线） ─────────────────────────
def _ratio(num, den) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(np.isfinite(den) & (den > 0), num / den, np.nan)
    return out


def _recent(flags, n: int) -> np.ndarray:
    """最近 n 根（含 t）里有没有事件。"""
    return pd.Series(np.asarray(flags, bool)).rolling(n, min_periods=1).max().fillna(0).astype(bool).to_numpy()


def ticker_features(df: pd.DataFrame) -> pd.DataFrame | None:
    """一只票的日线 → 逐日 18 个特征 + 之后 20 日收益（见文件开头〇）。"""
    d = df[["Open", "High", "Low", "Close"]].astype(float)
    d = d[d["Close"].notna()]
    n = len(d)
    if n < 60:
        return None
    s = TL.scan(d, "D")
    c, o = d["Close"].to_numpy(), d["Open"].to_numpy()
    atr = s["tol"] / TL.TOL_ATR
    out = pd.DataFrame(index=d.index)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["fwd"] = ((np.r_[c[H:], np.full(H, np.nan)] / np.r_[o[1:], np.nan] - 1) * 100).astype(np.float32)
    sup, res = s["sup"], s["res"]
    idx = np.arange(n)
    out["d_res_atr"] = _ratio(res - c, atr).astype(np.float32)
    out["d_sup_atr"] = _ratio(c - sup, atr).astype(np.float32)
    out["d_pos"] = _ratio(c - sup, res - sup).astype(np.float32)
    out["d_sup_slope"] = np.asarray(s["sup_slope"], np.float32)
    out["d_res_slope"] = np.asarray(s["res_slope"], np.float32)
    out["d_sup_touch"] = np.where(np.isfinite(sup), s["sup_touch"], np.nan).astype(np.float32)
    out["d_res_touch"] = np.where(np.isfinite(res), s["res_touch"], np.nan).astype(np.float32)
    out["d_sup_len"] = np.where(s["sup_a1"] >= 0, idx - s["sup_a1"], np.nan).astype(np.float32)
    out["d_res_len"] = np.where(s["res_a1"] >= 0, idx - s["res_a1"], np.nan).astype(np.float32)
    out["d_rb5"] = _recent(s["res_break"], RB_N)
    out["d_sb20"] = _recent(s["sup_break"], SB_N)
    for col in ("w_res_atr", "w_sup_atr", "w_pos", "w_sup_slope", "w_res_slope", "w_sup_touch", "w_res_touch"):
        out[col] = np.float32(np.nan)
    wb = K.bars(d, "W")
    if len(wb) >= 2 * TL.PARAMS["W"][0] + 2:
        ws = TL.scan(wb, "W")
        wk = wb.index.searchsorted(d.index, side="left")                     # t 所在那一周的周K
        prev = wk - 1
        okp = prev >= 0
        pi = np.where(okp, prev, 0)
        nan = np.full(n, np.nan)
        w_res = np.where(okp, ws["res"][pi] + ws["res_b"][pi], nan)            # 上一根走完的周K 的线往后延长一根
        w_sup = np.where(okp, ws["sup"][pi] + ws["sup_b"][pi], nan)
        watr = np.where(okp, ws["tol"][pi] / TL.TOL_ATR, nan)
        out["w_res_atr"] = _ratio(w_res - c, watr).astype(np.float32)
        out["w_sup_atr"] = _ratio(c - w_sup, watr).astype(np.float32)
        out["w_pos"] = _ratio(c - w_sup, w_res - w_sup).astype(np.float32)
        out["w_sup_slope"] = np.where(okp, ws["sup_slope"][pi], nan).astype(np.float32)
        out["w_res_slope"] = np.where(okp, ws["res_slope"][pi], nan).astype(np.float32)
        out["w_sup_touch"] = np.where(okp & np.isfinite(w_sup), ws["sup_touch"][pi], nan).astype(np.float32)
        out["w_res_touch"] = np.where(okp & np.isfinite(w_res), ws["res_touch"][pi], nan).astype(np.float32)
    return out


def _job(item):
    t, df = item
    try:
        return t, ticker_features(df)
    except Exception as ex:                                                   # noqa: BLE001
        return t, repr(ex)


def _run_jobs(items, workers: int, label: str) -> dict:
    res, bad = {}, []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for t, r in ex.map(_job, items, chunksize=8):
            if isinstance(r, str):
                bad.append((t, r))
            elif r is not None:
                res[t] = r
    if bad:
        raise SystemExit(f"{label}：{len(bad)} 只票算不出特征（例：{bad[:2]}）→ 停")
    return res


def build_features(W: dict, say=print, workers: int = 4) -> dict:
    """6 个样本的每只票特征（并行；Jx = J2 行情里不在日経225（J）的票）。"""
    t0 = time.time()
    out: dict = {}
    n225_j = set(W["SM"]["J"]["fa"])
    for s in SAMPLES:
        fa = W["SM"][SM_KEY[s]]["fa"]
        items = [(t, fa[t][["Open", "High", "Low", "Close"]]) for t in sorted(fa)
                 if t.endswith(".T") and t not in STOCK_SKIP and not (s == "Jx" and t in n225_j)]
        out[s] = _run_jobs(items, workers, s)
        say(f"{s}：{len(out[s])} 只票的特征；{time.time() - t0:.0f}s")
    return out


def u0_frame(A: dict, j: int) -> pd.DataFrame:
    """全市场面板第 j 只票 → 日线表（有收盘的日子）；不在时点名单上的日子 fwd = NaN（样本里不算，特征照算）。"""
    days = A["days"]
    df = pd.DataFrame({"Open": A["O"][:, j], "High": A["H"][:, j], "Low": A["L"][:, j], "Close": A["C"][:, j],
                       "listed": A["listed"][:, j]}, index=days)
    return df[np.isfinite(df["Close"].to_numpy(float))]


def _u0_job(item):
    t, df = item
    try:
        f = ticker_features(df)
        if f is not None:
            f.loc[~df.loc[f.index, "listed"].astype(bool), "fwd"] = np.nan
        return t, f
    except Exception as ex:                                                   # noqa: BLE001
        return t, repr(ex)


def build_u0(say=print, workers: int = 4) -> dict:
    """U0：J-Quants 全市场时点面板的每只票特征（只描述用）。"""
    import allstock_data as AD
    t0 = time.time()
    A = AD.load()
    items = [(t, u0_frame(A, j)) for j, t in enumerate(A["names"])]
    res, bad = {}, []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for t, r in ex.map(_u0_job, items, chunksize=8):
            if isinstance(r, str):
                bad.append((t, r))
            elif r is not None:
                res[t] = r
    if bad:
        raise SystemExit(f"U0：{len(bad)} 只票算不出特征（例：{bad[:2]}）→ 停")
    say(f"U0：名单 {len(A['names'])} 只、有特征 {len(res)} 只；{time.time() - t0:.0f}s")
    return res


def values_at(FL: dict, tickers, dates, cols=COLS) -> pd.DataFrame:
    """（票, 日期）的特征（找不到 → NaN；_has = 找得到这只票这一天的特征行）。"""
    rows = np.full((len(tickers), len(cols)), np.nan)
    has = np.zeros(len(tickers), bool)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        f = FL.get(str(t))
        if f is None:
            continue
        k = f.index.get_indexer([pd.Timestamp(d)])[0]
        if k >= 0:
            rows[i] = f[cols].iloc[k].to_numpy(float)
            has[i] = True
    V = pd.DataFrame(rows, columns=cols)
    V["_has"] = has
    return V


# ───────────────────────── 分组 ─────────────────────────
def tercile_bounds(V: pd.DataFrame) -> dict:
    """连续特征的三分位界线 {F: [q1, q2]} 与各自的有值个数（探索样本 W ∪ Jx 合起来、有值的信号）。"""
    out, n = {}, {}
    for f in FIDS:
        col, _, kind = FEATS[f]
        if kind != "cont":
            continue
        v = V[col].to_numpy(float)
        v = v[np.isfinite(v)]
        out[f] = [float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))] if len(v) else [np.nan, np.nan]
        n[f] = int(len(v))
    return {"bounds": out, "n": n}


def degenerate(fid: str, bounds: dict) -> bool:
    """连续特征 q1 == q2 → 没有候选、只描述。"""
    if FEATS[fid][2] != "cont":
        return False
    q1, q2 = bounds[fid]
    return not (np.isfinite(q1) and np.isfinite(q2) and q2 > q1)


def groups_of(values, fid: str, bounds: dict, has=None) -> np.ndarray:
    """特征值 → 组。连续：0 = 没有值、1 ≤ q1 < 2 ≤ q2 < 3；整数：0 = 没有值、1 = {2}、2 = {3}、3 = {≥ 4}；bool：0 = 没有特征行、1 = 否、2 = 是。"""
    kind = FEATS[fid][2]
    v = np.asarray(values, float)
    out = np.zeros(len(v), np.int8)
    if kind == "bool":
        ok = np.ones(len(v), bool) if has is None else np.asarray(has, bool)
        out[ok] = np.where(v[ok] > 0.5, 2, 1)
        return out
    ok = np.isfinite(v)
    if kind == "int":
        out[ok & (v <= INT_CUTS[0])] = 1
        out[ok & (v > INT_CUTS[0]) & (v <= INT_CUTS[1])] = 2
        out[ok & (v > INT_CUTS[1])] = 3
        return out
    q1, q2 = bounds[fid]
    out[ok & (v <= q1)] = 1
    out[ok & (v > q1) & (v <= q2)] = 2
    out[ok & (v > q2)] = 3
    return out


def ends_of(fid: str) -> tuple[int, int]:
    """可以被挡的两端：连续 / 整数 = (G1, G3)；bool = (否, 是)。"""
    return (1, 2) if FEATS[fid][2] == "bool" else (1, 3)


def group_table(net: np.ndarray, g: np.ndarray) -> dict:
    out = {}
    for k in sorted(set(int(x) for x in g)):
        m = g == k
        out[int(k)] = {"n": int(m.sum()), "win": round(float((net[m] > 0).mean() * 100), 2), "mean": round(float(net[m].mean()), 3)}
    return out


def choose_group(net: np.ndarray, g: np.ndarray, fid: str) -> int | None:
    """挡哪一端：两端里平均净收益低的（两端都要有信号；一样低取编号小的）。"""
    a, b = ends_of(fid)
    ma, mb = g == a, g == b
    if not ma.any() or not mb.any():
        return None
    return a if float(net[ma].mean()) <= float(net[mb].mean()) else b


def placebo_pct(net: np.ndarray, g: np.ndarray, fid: str, i: int, dmean: float) -> dict:
    """d：组标签随机重排（G0 不动、各组个数不变）→ 按同一条规则挑最差一端 → 每笔差；200 次 → 95 分位与候选的分位。"""
    import combo_all_common as CA
    net, g = np.asarray(net, float), np.asarray(g, np.int8)
    pos = np.flatnonzero(g != 0)
    vals = []
    for s in range(PLACEBO_N):
        rng = np.random.default_rng([*PLACEBO_SEED, int(i), int(s)])
        gp = g.copy()
        gp[pos] = g[pos][rng.permutation(len(pos))]
        k = choose_group(net, gp, fid)
        if k is None:
            continue
        vals.append(float(CA.delta(net, gp != k)["dmean"]))
    if not vals:
        return {"p95": None, "pct": None, "n": 0}
    vals = np.asarray(vals)
    return {"p95": float(np.quantile(vals, 0.95)), "pct": round(float((vals < dmean).mean() * 100), 1), "n": int(len(vals))}


# ───────────────────────── 一：全部股票横截面 ─────────────────────────
def _corr_by_date(X: pd.DataFrame, a: str, b: str) -> pd.Series:
    """每一天 a 与 b 的 Pearson 相关（a / b 已是当天的名次或 0 / 1）。"""
    g = X.assign(aa=X[a].astype(float), bb=X[b].astype(float))
    g["ab"], g["a2"], g["b2"] = g["aa"] * g["bb"], g["aa"] ** 2, g["bb"] ** 2
    S = g.groupby("date").agg(n=("aa", "size"), sa=("aa", "sum"), sb=("bb", "sum"), sab=("ab", "sum"), sa2=("a2", "sum"), sb2=("b2", "sum"))
    cov = S["sab"] / S["n"] - (S["sa"] / S["n"]) * (S["sb"] / S["n"])
    va = S["sa2"] / S["n"] - (S["sa"] / S["n"]) ** 2
    vb = S["sb2"] / S["n"] - (S["sb"] / S["n"]) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        r = cov / np.sqrt(va * vb)
    return r.replace([np.inf, -np.inf], np.nan)


def xsec(P: pd.DataFrame, days: pd.DatetimeIndex, fid: str) -> pd.DataFrame:
    """一个样本一个特征：每 5 个交易日一天 → 高组 − 低组的平均超额（连续 = 当天名次三分位；整数 = {≥ 4} − {2}；bool = 是 − 否；两组各 ≥ 5 只）+ 当天的秩相关。"""
    col, _, kind = FEATS[fid]
    X = P[P["date"].isin(set(days[::EVERY]))]
    if kind == "bool":
        v = X[col].astype(bool)
        X = X.assign(hi=v, lo=~v, rk=v.astype(float))
    else:
        X = X[np.isfinite(X[col].to_numpy(float))]
        if kind == "int":
            v = X[col].to_numpy(float)
            X = X.assign(hi=v > INT_CUTS[1], lo=v <= INT_CUTS[0], rk=X.groupby("date")[col].rank())
        else:
            r = X.groupby("date")[col].rank(pct=True)
            X = X.assign(hi=r > 2 / 3 + 1e-9, lo=r <= 1 / 3 + 1e-9, rk=X.groupby("date")[col].rank())
    if not len(X):
        return pd.DataFrame(columns=["date", "spread", "n_hi", "n_lo", "rho"])
    S = X.groupby("date").agg(n_hi=("hi", "sum"), n_lo=("lo", "sum"))
    S["m_hi"] = X[X["hi"]].groupby("date")["ex"].mean()
    S["m_lo"] = X[X["lo"]].groupby("date")["ex"].mean()
    X = X.assign(re=X.groupby("date")["ex"].rank())
    S["rho"] = _corr_by_date(X, "rk", "re")
    S = S[(S["n_hi"] >= MIN_GROUP) & (S["n_lo"] >= MIN_GROUP)]
    return pd.DataFrame({"date": S.index, "spread": (S["m_hi"] - S["m_lo"]).to_numpy(float), "n_hi": S["n_hi"].to_numpy(int),
                         "n_lo": S["n_lo"].to_numpy(int), "rho": S["rho"].to_numpy(float)})


def u0_days(FU: dict) -> pd.DatetimeIndex:
    """U0 面板自己的交易日（全部票的日期并集）。"""
    return pd.DatetimeIndex(np.unique(np.concatenate([f.index.to_numpy() for f in FU.values()])))


def sample_days(W: dict, s: str, U0_days: pd.DatetimeIndex | None = None) -> tuple[tuple, pd.DatetimeIndex]:
    """样本的窗口与交易日（U0：J 窗口起点 2017-01-04、面板自己的交易日）。"""
    if s == U0:
        if U0_days is None:
            raise ValueError("U0 需要面板自己的交易日 U0_days")
        a, b = pd.Timestamp(U0_START), pd.Timestamp("2026-10-01")
        d = U0_days[(U0_days >= a) & (U0_days < b)]
        return (a, b), d
    e = WIN_ERA[s]
    win = TS._win(*W["ctx"][e]["windows"][e])
    days = pd.DatetimeIndex(W["ctx"][e]["days"])
    return win, days[(days >= win[0]) & (days < win[1])]


def sample_panel(FL: dict, win, days: pd.DatetimeIndex) -> pd.DataFrame:
    """样本日（每 5 个交易日一天）的长表：日期、票、超额 + 18 个特征（只取样本日 → 与 trendline_study.sample_panel 在这些日子上相同；U0 才放得下）。"""
    a, b = win
    pick = pd.DatetimeIndex(days[::EVERY])
    parts = []
    for t, f in FL.items():
        x = f.loc[f.index.isin(pick) & (f.index >= a) & (f.index < b), ["fwd"] + COLS]
        if len(x):
            parts.append(x.assign(ticker=t))
    if not parts:
        return pd.DataFrame(columns=["date", "ticker", "fwd", "ex", "month"] + COLS)
    P = pd.concat(parts).rename_axis("date").reset_index()
    P = P[np.isfinite(P["fwd"].to_numpy(float))]
    P["ex"] = P["fwd"] - P.groupby("date")["fwd"].transform("mean")
    P["month"] = P["date"].dt.strftime("%Y-%m")
    return P


def _one_sample(FL: dict, win, days, say, s: str) -> tuple[dict, dict, dict, dict]:
    P = sample_panel(FL, win, days)
    on = P
    cov = {f: round(float(np.isfinite(on[FEATS[f][0]].to_numpy(float)).mean() * 100), 1) if FEATS[f][2] != "bool"
           else round(float(on[FEATS[f][0]].astype(bool).mean() * 100), 1) for f in FIDS}
    by, parts = {}, {}
    for f in FIDS:
        X = xsec(P, days, f)
        mon = X["date"].dt.strftime("%Y-%m").to_numpy() if len(X) else np.array([])
        r = TS.cluster_mean(X["spread"], mon) if len(X) else {"n": 0, "mean": None, "se": None, "lo": None, "hi": None, "clusters": 0}
        r["days"] = int(len(X))
        r["rho"] = round(float(np.nanmean(X["rho"])), 4) if len(X) and np.isfinite(X["rho"]).any() else None
        r["n_hi"] = round(float(X["n_hi"].mean()), 1) if len(X) else None
        r["n_lo"] = round(float(X["n_lo"].mean()), 1) if len(X) else None
        by[f] = r
        if len(X):
            parts[f] = pd.DataFrame({"v": X["spread"].to_numpy(), "m": mon})
    raw = {"sample_rows": int(len(P)), "tickers": int(P["ticker"].nunique()), "sample_days": int(len(days[::EVERY]))}
    say(f"一 {s}：样本日 {len(P)} 票次、{P['ticker'].nunique()} 只票")
    return by, cov, raw, parts


def part_a(FLS: dict, W: dict, FU: dict | None, say=print) -> dict:
    out: dict = {"by": {f: {} for f in FIDS}, "pooled": {}, "coverage": {}, "raw": {}}
    pooled = {f: [] for f in FIDS}
    for s in SAMPLES:
        win, days = sample_days(W, s)
        by, cov, raw, parts = _one_sample(FLS[s], win, days, say, s)
        out["coverage"][s], out["raw"][s] = cov, raw
        for f in FIDS:
            out["by"][f][s] = by[f]
            if f in parts:
                pooled[f].append(parts[f])
    for f in FIDS:
        if pooled[f]:
            X = pd.concat(pooled[f])
            out["pooled"][f] = TS.cluster_mean(X["v"], X["m"])
    out["judge"] = judge_a(out)
    if FU:
        win, days = sample_days(W, U0, u0_days(FU))
        by, cov, raw, _ = _one_sample(FU, win, days, say, U0)
        out["coverage"][U0], out["raw"][U0] = cov, raw
        for f in FIDS:
            out["by"][f][U0] = by[f]
            p = out["pooled"].get(f) or {}
            m, pm = by[f].get("mean"), p.get("mean")
            out["judge"][f]["u0_same_sign"] = None if m is None or pm is None else bool(m * pm > 0)
    return out


def judge_a(a: dict) -> dict:
    """一的判定：6 个样本的差同号、合起来 95% 区间不含 0、|平均| ≥ 0.3 pp（U0 不参与判定）。"""
    j = {}
    for f in FIDS:
        vals = [((a["by"].get(f) or {}).get(s) or {}).get("mean") for s in SAMPLES]
        p = a["pooled"].get(f) or {}
        pos = all(v is not None and v > 0 for v in vals)
        neg = all(v is not None and v < 0 for v in vals)
        ok = ((pos or neg) and p.get("lo") is not None and (p["lo"] > 0 or p["hi"] < 0) and abs(p["mean"]) >= MIN_PP)
        j[f] = {"info": bool(ok), "each": vals, "sign": "+" if pos else "−" if neg else "±"}
    return j


# ───────────────────────── 二：探索（W / Jx）→ 入围 → 确认（Z / E / J 账户 + Zx） ─────────────────────────
def pool_xv(W: dict, FLS: dict, tbf_pool: dict, s: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    X = TS.pool_x(W, s)[~tbf_pool[s]].reset_index(drop=True)
    return X, values_at(FLS[s], X["ticker"], X["date"])


def _delta(net: np.ndarray, blk: np.ndarray) -> dict:
    """保留 vs 全部（门槛比较用没有四舍五入的值；报告时才格式化）。"""
    import combo_all_common as CA
    dl = CA.delta(net, ~blk)
    return {"n": int(dl["n"]), "kept": int(dl["kept"]), "changed": int(blk.sum()), "frac": float(blk.mean()) if len(blk) else None,
            "dwin": None if not np.isfinite(dl["dwin"]) else float(dl["dwin"]),
            "dmean": None if not np.isfinite(dl["dmean"]) else float(dl["dmean"])}


def gates(dj: dict, dw: dict, placebo: dict | None) -> dict:
    """入围 a〜d（纯函数；门槛见文件开头二）。"""
    a = bool(dj.get("frac") is not None and dw.get("frac") is not None and BLOCK_LO <= dj["frac"] <= BLOCK_HI and BLOCK_LO <= dw["frac"] <= BLOCK_HI)
    b = bool(dj.get("dwin") is not None and dj.get("dmean") is not None and dj["dwin"] >= WIN_MIN - 1e-9 and dj["dmean"] >= MEAN_MIN - 1e-9)
    c = bool(dw.get("dwin") is not None and dw.get("dmean") is not None and dw["dwin"] > 1e-9 and dw["dmean"] >= -1e-9)
    d = bool(placebo is not None and placebo.get("p95") is not None and dj.get("dmean") is not None and dj["dmean"] > placebo["p95"] + 1e-9)
    return {"a": a, "b": b, "c": c, "d": d}


def halves(X: pd.DataFrame, blk: np.ndarray, s: str) -> dict:
    """只描述：探索样本前后两半各自的保留 − 全部每笔差。"""
    a, m, b = (pd.Timestamp(x) for x in HALVES[s])
    d = pd.to_datetime(X["date"])
    net = X["net"].to_numpy(float)
    out = {}
    for name, sel in (("前一半", (d >= a) & (d < m)), ("后一半", (d >= m) & (d < b))):
        sel = sel.to_numpy()
        out[name] = _delta(net[sel], blk[sel]) if sel.any() else None
    return out


def explore(W: dict, FLS: dict, tbf_pool: dict, bounds: dict, say=print) -> tuple[dict, dict]:
    """探索：只用 W / Jx 池子里 B4 会买的信号 → 每个特征的分组表、挡哪一端、保留 vs 全部、重排对照、入围 a〜d。Zx 不碰。"""
    XV = {s: pool_xv(W, FLS, tbf_pool, s) for s in EXPLORE}
    res: dict = {}
    for i, f in enumerate(FIDS):
        col = FEATS[f][0]
        g = {s: groups_of(XV[s][1][col].to_numpy(), f, bounds, XV[s][1]["_has"].to_numpy()) for s in EXPLORE}
        net = {s: XV[s][0]["net"].to_numpy(float) for s in EXPLORE}
        tab = {s: group_table(net[s], g[s]) for s in EXPLORE}
        r = {"id": CAND[f], "col": col, "family": FAM_OF[f], "cand": f in CAND_IDS and not degenerate(f, bounds), "tables": tab, "delta": {}, "halves": {}}
        grp = choose_group(net["Jx"], g["Jx"], f) if r["cand"] else None
        r["group"], r["group_name"] = grp, names_of(f).get(grp)
        if grp is not None:
            for s in EXPLORE:
                blk = g[s] == grp
                r["delta"][s] = _delta(net[s], blk)
                r["halves"][s] = halves(XV[s][0], blk, s)
            dj, dw = r["delta"]["Jx"], r["delta"]["W"]
            r["placebo"] = placebo_pct(net["Jx"], g["Jx"], f, i, dj["dmean"] if dj["dmean"] is not None else -np.inf)
            r.update(gates(dj, dw, r["placebo"]))
        else:
            r.update({"placebo": None, "a": False, "b": False, "c": False, "d": False})
        r["selected"] = bool(r["cand"] and r["a"] and r["b"] and r["c"] and r["d"])
        res[f] = r
        say(f"探索 {f} {CAND[f]}：{'不是候选' if not r['cand'] else '挡 ' + str(r['group_name'])}；{'入围' if r['selected'] else '不入围'}"
            f"（a{'✓' if r['a'] else '✗'} b{'✓' if r['b'] else '✗'} c{'✓' if r['c'] else '✗'} d{'✓' if r['d'] else '✗'}）")
    extra = {"n_pool": {s: int(len(XV[s][0])) for s in EXPLORE}, "competition": {s: slot_competition(XV[s][0]) for s in EXPLORE}}
    return res, extra


def finalists(expl: dict) -> list[str]:
    """入围：a〜d 全部满足，按 Jx 每笔差从大到小，同一族最多 1 个，最多 3 个。"""
    ok = [f for f in FIDS if expl[f]["selected"]]
    ok.sort(key=lambda f: -(expl[f]["delta"]["Jx"]["dmean"] if expl[f]["delta"]["Jx"]["dmean"] is not None else -np.inf))
    out, fam = [], {}
    for f in ok:
        if fam.get(FAM_OF[f], 0) >= FAM_CAP:
            continue
        out.append(f)
        fam[FAM_OF[f]] = fam.get(FAM_OF[f], 0) + 1
        if len(out) >= MAX_FINAL:
            break
    return out


def slot_competition(X: pd.DataFrame) -> dict:
    """只描述：同一天 ≥ 2 个 B4 会买的信号的日子有多少（排名问题的规模）。"""
    g = X.groupby(pd.to_datetime(X["date"]).dt.normalize()).size()
    return {"days": int(len(g)), "days_ge2": int((g >= 2).sum()), "signals_on_ge2": int(g[g >= 2].sum())}


def era_groups(W: dict, e: str, f: str, bounds: dict, tbf: np.ndarray, FL: dict) -> tuple[np.ndarray, np.ndarray]:
    """日経225 年代 e 的 W2 信号 → (这个特征的组, TBF 挡)。"""
    import loop9_common as C9
    S = C9.signals(W, e)
    V = values_at(FL, S["ticker"], S["date"], [FEATS[f][0]])
    return groups_of(V[FEATS[f][0]].to_numpy(), f, bounds, V["_has"].to_numpy()), np.asarray(tbf, bool)


def boot_ci(net: np.ndarray, blocked: np.ndarray, months: np.ndarray) -> dict:
    """Zx 每笔差（保留 − 全部）的 95% 区间：按信号月聚类的自助法（只描述）。"""
    net, blocked, months = np.asarray(net, float), np.asarray(blocked, bool), np.asarray(months)
    if not len(net):
        return {"lo": None, "hi": None, "n": 0}
    um = np.unique(months)
    idx = {m: np.flatnonzero(months == m) for m in um}
    rng = np.random.default_rng(BOOT_SEED)
    vals = []
    for _ in range(BOOT_N):
        pick = rng.choice(len(um), len(um), replace=True)
        ii = np.concatenate([idx[um[p]] for p in pick])
        kept = ~blocked[ii]
        if kept.any():
            vals.append(float(net[ii][kept].mean() - net[ii].mean()))
    if not vals:
        return {"lo": None, "hi": None, "n": 0}
    return {"lo": round(float(np.quantile(vals, 0.025)), 4), "hi": round(float(np.quantile(vals, 0.975)), 4), "n": int(len(vals))}


def confirm(W: dict, FLS: dict, tbf: dict, tbf_pool: dict, base: dict, final: list[str], expl: dict, bounds: dict, say=print) -> dict:
    """确认：入围的每个做法 → Z / E / J 账户（挡同一组）+ 池子 W / Jx / Zx → research_loop11.stage1(posthoc = True) + 规模 + 跨时期 + Zx 区间。"""
    import loop9_common as C9
    import research_loop11 as R11
    out = {}
    Xz, Vz = pool_xv(W, FLS, tbf_pool, UNSEEN)
    for f in final:
        grp = expl[f]["group"]
        cand, scale = {}, {}
        for e in N225_ERAS:
            g, tg = era_groups(W, e, f, bounds, tbf[e], FLS[e])
            gate = tg | (g == grp)
            cand[e] = C9.acct(C9.run_block(W, e, gate))
            n_blk, n_all = int(((g == grp) & ~tg).sum()), int((~tg).sum())
            cand[e]["blocked"] = n_blk
            scale[e] = {"blocked": n_blk, "signals": n_all, "share": round(n_blk / n_all, 4) if n_all else None, "ok": bool(n_all and n_blk / n_all >= SCALE_MIN - 1e-9)}
        gz = groups_of(Vz[FEATS[f][0]].to_numpy(), f, bounds, Vz["_has"].to_numpy()) == grp
        other = {s: dict(expl[f]["delta"][s]) for s in EXPLORE}
        other[UNSEEN] = _delta(Xz["net"].to_numpy(float), gz)
        s1 = R11.stage1(cand, base, other, lenses=None, posthoc=True)
        ci = boot_ci(Xz["net"].to_numpy(float), gz, pd.to_datetime(Xz["date"]).dt.strftime("%Y-%m").to_numpy())
        dwin_z = None if cand["Z"].get("win") is None or base["Z"].get("win") is None else float(cand["Z"]["win"]) - float(base["Z"]["win"])
        cross = bool(dwin_z is not None and dwin_z >= -1e-9 and other[UNSEEN]["dmean"] is not None and other[UNSEEN]["dmean"] > 1e-9)
        ok = bool(s1["ok"] and all(v["ok"] for v in scale.values()) and cross)
        out[f] = {"id": CAND[f], "group": grp, "cand": cand, "other": other, "stage1": s1, "scale": scale, "cross": {"z_dwin": dwin_z, "zx_dmean": other[UNSEEN]["dmean"], "ok": cross},
                  "zx_ci": ci, "zx_table": group_table(Xz["net"].to_numpy(float), groups_of(Vz[FEATS[f][0]].to_numpy(), f, bounds, Vz["_has"].to_numpy())),
                  "candidate": ok}
        say(f"确认 {f} {CAND[f]}：stage1 {'过' if s1['ok'] else '不过'}（路线 {s1['ok_routes'] or '—'}）、规模 {'够' if all(v['ok'] for v in scale.values()) else '不足'}、"
            f"跨时期 {'成立' if cross else '不成立'} → {'候选（第一关）' if ok else '不是候选'}")
    return out


# ───────────────────────── 三：只描述 ─────────────────────────
def b4_trades(W: dict, e: str, tbf: np.ndarray) -> pd.DataFrame:
    """B4 实际成交（窗口内买入、已平仓的日本个股）：票、成交日、信号日、净收益 %。"""
    import jq_study as JS
    import loop9_common as C9
    C9.run_block(W, e, tbf)
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    a, b = TS._win(*W["ctx"][e]["windows"][e])
    tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(STOCK_SKIP) & (tr["reason"] != "end")]
    ed = pd.to_datetime(tr["entry_date"])
    tr = tr[((ed >= a) & (ed < b)).to_numpy()].reset_index(drop=True)
    days = pd.DatetimeIndex(W["ctx"][e]["days"])
    sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]
    net = tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100
    return pd.DataFrame({"ticker": tr["ticker"].astype(str), "fill": pd.to_datetime(tr["entry_date"]), "sig": pd.DatetimeIndex(sig), "net": net})


def describe_b4(FLS: dict, b4tr: dict, bounds: dict, final: list[str]) -> dict:
    """只描述：B4 实际成交在信号日的分组 → 个数 / 胜率 / 每笔（只对入围的特征）。"""
    out = {}
    for e, tr in b4tr.items():
        r = {"n": int(len(tr))}
        if final:
            V = values_at(FLS[e], tr["ticker"], tr["sig"])
            for f in final:
                r[f] = group_table(tr["net"].to_numpy(float), groups_of(V[FEATS[f][0]].to_numpy(), f, bounds, V["_has"].to_numpy()))
        out[e] = r
    return out


def _group_counts(g: np.ndarray) -> dict:
    return {int(k): int(v) for k, v in zip(*np.unique(g, return_counts=True))}


def counts(W: dict, FLS: dict, FU: dict | None, tbf: dict, tbf_pool: dict, tb: dict, b4tr: dict | None = None) -> dict:
    """登记前只数个数：每个样本的票数 / 行数、特征的有值比例；池子 / 日経225 信号在每个特征每一组的个数；B4 成交数；排名问题的规模。不算任何收益。"""
    import loop9_common as C9
    bounds = tb["bounds"]
    out: dict = {"A": {}, "pools": {}, "n225": {}, "bounds": bounds, "bounds_n": tb["n"], "degenerate": [f for f in FIDS if degenerate(f, bounds)]}
    samples = {s: FLS[s] for s in SAMPLES}
    if FU:
        samples[U0] = FU
    for s, FL in samples.items():
        if s == U0:
            (a, b), days = sample_days(W, U0, u0_days(FL))
        else:
            (a, b), days = sample_days(W, s)
        pick = set(days[::EVERY])
        rows = on_n = 0
        have = {f: 0 for f in FIDS}
        for fr in FL.values():
            x = fr[(fr.index >= a) & (fr.index < b)]
            if s == U0:
                x = x[np.isfinite(x["fwd"].to_numpy(float))]                 # U0：只数在时点名单上、算得出之后收益的票日
            rows += len(x)
            o = x[x.index.isin(pick)]
            on_n += len(o)
            for f in FIDS:
                col, _, kind = FEATS[f]
                have[f] += int(o[col].astype(bool).sum()) if kind == "bool" else int(np.isfinite(o[col].to_numpy(float)).sum())
        out["A"][s] = {"tickers": len(FL), "rows": rows, "sample_days": len(pick), "sample_rows": on_n,
                       "have_pct": {f: round(have[f] / on_n * 100, 1) if on_n else None for f in FIDS}}
    for s in POOLS:
        X, V = pool_xv(W, FLS, tbf_pool, s)
        out["pools"][s] = {"b4_buy": int(len(X)), "groups": {f: _group_counts(groups_of(V[FEATS[f][0]].to_numpy(), f, bounds, V["_has"].to_numpy())) for f in FIDS},
                           **slot_competition(X)}
    for e in N225_ERAS:
        S = C9.signals(W, e)
        g = np.asarray(tbf[e], bool)
        Sk = S[~g]
        V = values_at(FLS[e], Sk["ticker"], Sk["date"])
        tr = (b4tr or {}).get(e)
        if tr is None:
            tr = b4_trades(W, e, tbf[e])
        out["n225"][e] = {"signals": int(len(S)), "not_tbf": int(len(Sk)), "b4_trades": int(len(tr)),
                          "groups": {f: _group_counts(groups_of(V[FEATS[f][0]].to_numpy(), f, bounds, V["_has"].to_numpy())) for f in FIDS},
                          **slot_competition(Sk)}
    return out


def _sha(fp: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(fp, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 22), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def git_info() -> dict:
    from qbreak import paths
    root = str(paths.PROJECT_ROOT)
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=root).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/trendline_select_study.py", "scripts/trendline_study.py",
                                     "qbreak/trendline.py", "qbreak/kline.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", None
    cp, cu = paths.sub("cache") / FLAGS_CACHE, paths.sub("cache") / U0_CACHE
    return {"rev": rev, "dirty": dirty, "cache": {"size": cp.stat().st_size if cp.exists() else None, "sha256_16": _sha(cp)},
            "cache_u0": {"size": cu.stat().st_size if cu.exists() else None, "sha256_16": _sha(cu)}}


def load_all(say=print, with_u0: bool = True) -> tuple[dict, dict, dict | None, dict, dict]:
    import loop10_common as C10
    from qbreak import paths
    t0 = time.time()
    W = C10.load()
    say(f"载入 B3 + Zx：{time.time() - t0:.0f}s")
    tbf, tbf_pool = TS.tbf_gates(W, say)
    cp = paths.sub("cache") / FLAGS_CACHE
    if cp.exists():
        with open(cp, "rb") as f:
            FLS = pickle.load(f)
        say("趋势线特征：用 --prep 的缓存（同一份）")
    else:
        FLS = build_features(W, say)
        with open(cp, "wb") as f:
            pickle.dump(FLS, f)
    FU = None
    if with_u0:
        cu = paths.sub("cache") / U0_CACHE
        if cu.exists():
            with open(cu, "rb") as f:
                FU = pickle.load(f)
            say("U0 特征：用 --prep 的缓存（同一份）")
        else:
            FU = build_u0(say)
            with open(cu, "wb") as f:
                pickle.dump(FU, f)
    return W, FLS, FU, tbf, tbf_pool


def prep_bounds(W: dict, FLS: dict, tbf_pool: dict) -> dict:
    """三分位界线（只用特征分布，不看收益）：W ∪ Jx 里 B4 会买的信号。"""
    V = pd.concat([pool_xv(W, FLS, tbf_pool, s)[1] for s in EXPLORE], ignore_index=True)
    return tercile_bounds(V)


def check_bounds(tb: dict) -> None:
    """--run：重算的界线必须与登记时写进本文件的 BOUNDS 相同。"""
    if not BOUNDS:
        raise SystemExit("BOUNDS 还没登记（--prep 之后把界线写进脚本再提交）→ 停")
    b = tb["bounds"]
    if set(b) != set(BOUNDS):
        raise SystemExit(f"界线的特征集合不同：{sorted(b)} vs {sorted(BOUNDS)} → 停")
    for f in b:
        if not np.allclose(b[f], BOUNDS[f], rtol=0, atol=1e-9, equal_nan=True):
            raise SystemExit(f"{f} 的界线 {b[f]} 与登记的 {BOUNDS[f]} 不同 → 停")


def run(say=print) -> dict:
    import research_loop10 as R10
    t0 = time.time()
    W, FLS, FU, tbf, tbf_pool = load_all(say)
    pre = TS.prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit(f"先决条件不满足：{pre} → 停")
    tb = prep_bounds(W, FLS, tbf_pool)
    check_bounds(tb)
    say("界线核对：与登记的 BOUNDS 相同")
    base = pre["base"]
    res: dict = {"git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}, "base": base, "bounds": tb["bounds"], "bounds_n": tb["n"]}
    res["A"] = part_a(FLS, W, FU, say)
    say(f"一 横截面完成；{time.time() - t0:.0f}s")
    expl, extra = explore(W, FLS, tbf_pool, tb["bounds"], say)
    res["explore"], res["explore_extra"] = expl, extra
    res["finalists"] = finalists(expl)
    say(f"二 探索完成：入围 {res['finalists'] or '无'}；{time.time() - t0:.0f}s")
    res["confirm"] = confirm(W, FLS, tbf, tbf_pool, base, res["finalists"], expl, tb["bounds"], say) if res["finalists"] else {}
    b4tr = {e: b4_trades(W, e, tbf[e]) for e in N225_ERAS}
    res["describe"] = describe_b4(FLS, b4tr, tb["bounds"], res["finalists"])
    res["counts"] = counts(W, FLS, FU, tbf, tbf_pool, tb, b4tr)
    res["success_base"] = R10.pooled_trades(base)
    res["elapsed_s"] = round(time.time() - t0)
    return res


# ───────────────────────── 输出 ─────────────────────────
_f, _ci = TS._f, TS._ci


def report(res: dict) -> str:
    A = res["A"]
    j = A["judge"]
    has_u0 = U0 in A["coverage"]
    cols = list(SAMPLES) + ([U0] if has_u0 else [])
    L = ["# 趋势线的质地特征能不能优化选股（全部股票横截面 + 结合 B4；scripts/trendline_select_study.py；只运行一次）", "",
         f"代码 {res['git']['rev']}{'（有未提交的改动！）' if res['git'].get('dirty') else ''}；先决条件：规则指纹 {res['prereq'].get('fingerprint')}、"
         "B4 重算 = turn_shape_combo 的 TBF、接线核对一致、界线与登记的 BOUNDS 相同。判定按文件开头（登记版）。", "",
         "## 一 全部股票横截面（高组 − 低组之后 20 日超额，pp；括号 = 95% 区间（按月聚类）与样本日数；U0 = J-Quants 全市场时点面板，只描述）", "",
         "| 特征 | " + " | ".join(cols) + " | 合起来（6 个样本） | 秩相关（平均） | 判定 |", "|---|" + "---|" * (len(cols) + 3)]
    for f in FIDS:
        rhos = [A["by"][f][s].get("rho") for s in SAMPLES if A["by"][f].get(s)]
        rho = np.nanmean([r for r in rhos if r is not None]) if any(r is not None for r in rhos) else None
        u = ""
        if has_u0:
            same = j[f].get("u0_same_sign")
            u = "" if same is None else ("（同号）" if same else "（反号）")
        L.append(f"| {f} {FEATS[f][1]} | " + " | ".join(_ci(A["by"][f].get(s)) + (u if s == U0 else "") for s in cols) + f" | {_ci(A['pooled'].get(f))} | {_f(rho, '{:+.3f}')} | "
                 f"**{'有信息' if j[f]['info'] else '没有'}**（{j[f]['sign']}） |")
    n_info = sum(1 for f in FIDS if j[f]["info"])
    L += ["", f"- 「有信息」= 6 个样本同号（读作 3 个窗口 × 2 个样本）+ 合起来 95% 区间不含 0 + |平均| ≥ {MIN_PP} pp → {n_info} / {len(FIDS)} 个特征"
          "（零假设下期望约 0.5〜0.7 个）。",
          "- 有值比例（样本日里有线的票次 %，F01〜F18；F10 / F11 是「是」的比例）：" + "；".join(f"{s} " + "/".join(str(A['coverage'][s][f]) for f in FIDS) for s in cols), "",
          "## 二 结合 B4：探索（W / Jx 池子里 B4 会买的信号；保留 − 全部）→ 入围 → 确认", "",
          "三分位界线（W ∪ Jx 合起来，登记时冻结；有值个数）：" + "；".join(f"{f} {_f(b[0], '{:.4f}')} / {_f(b[1], '{:.4f}')}（{res['bounds_n'][f]}）" for f, b in res["bounds"].items()), "",
          "| 做法 | 特征 | 族 | 挡哪一端 | Jx 挡 / 全部 | Jx 胜率差 | Jx 每笔差 | 重排对照 95 分位 | W 挡 / 全部 | W 胜率差 | W 每笔差 | a b c d | 入围 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in FIDS:
        r = res["explore"][f]
        if not r["cand"]:
            L.append(f"| {r['id']} | {f} {FEATS[f][1]} | {r['family'][:1]} | —（{'上一轮 TLB2 的变体，不进候选' if f in NO_CAND else '界线退化'}） | | | | | | | | | — |")
            continue
        dj, dw = r["delta"].get("Jx") or {}, r["delta"].get("W") or {}
        pl = r.get("placebo") or {}
        L.append(f"| {r['id']} | {f} {FEATS[f][1]} | {r['family'][:1]} | {r['group_name'] or '—'} | {dj.get('changed', 0)} / {dj.get('n', 0)} | {_f(dj.get('dwin'), '{:+.2f}')} pp | "
                 f"{_f(dj.get('dmean'), '{:+.3f}')} pp | {_f(pl.get('p95'), '{:+.3f}')}（{_f(pl.get('pct'), '{:.0f}')} 分位） | {dw.get('changed', 0)} / {dw.get('n', 0)} | "
                 f"{_f(dw.get('dwin'), '{:+.2f}')} pp | {_f(dw.get('dmean'), '{:+.3f}')} pp | "
                 + " ".join("✓" if r[k] else "✗" for k in "abcd") + f" | {'**入围**' if r['selected'] else '—'} |")
    fin = res["finalists"]
    L += ["", f"- 入围（a 挡掉 10〜70%、b Jx 胜率差 ≥ +{WIN_MIN} pp 且每笔差 ≥ +{MEAN_MIN} pp、c W 胜率差 > 0 且每笔差 ≥ 0、d 高于「重排组标签 → 挑最差一端」{PLACEBO_N} 次的 95 分位；"
          f"最多 {MAX_FINAL} 个、同族 ≤ {FAM_CAP}）：" + ("、".join(f"{CAND[f]}（{f}）" for f in fin) if fin else "**没有** → Zx 与日経225 账户不用")]
    L.append("- 探索样本两半（只描述；每笔差 pp）：" + "；".join(
        f"{CAND[f]} Jx {_f((res['explore'][f]['halves']['Jx']['前一半'] or {}).get('dmean'), '{:+.2f}')} / {_f((res['explore'][f]['halves']['Jx']['后一半'] or {}).get('dmean'), '{:+.2f}')}，"
        f"W {_f((res['explore'][f]['halves']['W']['前一半'] or {}).get('dmean'), '{:+.2f}')} / {_f((res['explore'][f]['halves']['W']['后一半'] or {}).get('dmean'), '{:+.2f}')}"
        for f in FIDS if res["explore"][f]["group"] is not None))
    if fin:
        base = res["base"]
        L += ["", "### 确认（Z / E / J 的 B4 账户挡同一组；posthoc = True → V6 Zx 必须同方向；另加规模与跨时期两条）", "",
              "| 做法 | 年代 | Calmar | 差 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 | 挡掉的信号 / TBF 没挡的 | 规模 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for f in fin:
            c = res["confirm"][f]
            for e in N225_ERAS:
                b, x, sc = base[e], c["cand"][e], c["scale"][e]
                L.append(f"| {CAND[f]} | {e} | {_f(b['calmar'], '{:.3f}')} → {_f(x['calmar'], '{:.3f}')} | "
                         f"{_f(None if x['calmar'] is None or b['calmar'] is None else x['calmar'] - b['calmar'])} | {_f(b['dd'], '{:.2f}')} → {_f(x['dd'], '{:.2f}')}% | "
                         f"{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}（B4 {_f(b['h1'], '{:.3f}')} / {_f(b['h2'], '{:.3f}')}） | {b['n']} → {x['n']} | "
                         f"{_f(b['win'], '{:.1f}')} → {_f(x['win'], '{:.1f}')}% | {_f(b['mean'], '{:+.2f}')} → {_f(x['mean'], '{:+.2f}')}% | {sc['blocked']} / {sc['signals']} | "
                         f"{'够' if sc['ok'] else '不足'} |")
        L.append("")
        for f in fin:
            c = res["confirm"][f]
            s = c["stage1"]
            ra, rb = s["routes"]["A"], s["routes"]["B"]
            o = c["other"]
            L.append(f"- **{CAND[f]}「{FEATS[f][1]}：挡 {res['explore'][f]['group_name']}」**：路线 A " + " ".join(f"{x}{'✓' if ra[x] else '✗'}" for x in ("A1", "A2", "A3", "V4", "V6"))
                     + "；路线 B " + " ".join(f"{x}{'✓' if rb[x] else '✗'}" for x in ("B1", "B2", "B3", "V4", "V6"))
                     + "；Calmar 差 " + "、".join(f"{e} {_f(ra['d'].get(e))}" for e in N225_ERAS) + f"（合计 {_f(ra['sum'])}）；合起来胜率差 {_f(rb['dwin'], '{:+.2f}')} pp、"
                     f"每笔差 {_f(rb['dmean'], '{:+.3f}')} pp；池子 " + "；".join(f"{q} 挡 {o[q]['changed']} / {o[q]['n']}（胜率差 {_f(o[q]['dwin'], '{:+.2f}')} pp、每笔差 {_f(o[q]['dmean'], '{:+.3f}')} pp）" for q in POOLS)
                     + f"；Zx 每笔差 95% 区间 {_f(c['zx_ci']['lo'], '{:+.3f}')}〜{_f(c['zx_ci']['hi'], '{:+.3f}')} pp（自助法 {c['zx_ci']['n']} 次）"
                     + f"；跨时期（Z 胜率差 {_f(c['cross']['z_dwin'], '{:+.1f}')} pp ≥ 0 且 Zx 每笔差 > 0）{'成立' if c['cross']['ok'] else '不成立'}"
                     + f" → **{'候选（第一关；要另行登记第二关）' if c['candidate'] else '不是候选'}**")
    L += ["", "## 三 只描述", ""]
    ex = res["explore_extra"]
    L.append("- 排名问题的规模（同一天 ≥ 2 个 B4 会买的信号）：" + "；".join(f"{s} {ex['competition'][s]['days_ge2']} / {ex['competition'][s]['days']} 天（{ex['competition'][s]['signals_on_ge2']} 个信号）" for s in EXPLORE)
             + "；日経225（TBF 没挡的 W2 信号）" + "；".join(f"{e} {res['counts']['n225'][e]['days_ge2']} / {res['counts']['n225'][e]['days']} 天" for e in N225_ERAS))
    if fin:
        for e, r in res["describe"].items():
            parts = []
            for f in fin:
                names = names_of(f)
                parts.append(f"{f} " + " / ".join(f"{names.get(k, f'G{k}')[:4]} {v['n']} 笔 {v['win']:.0f}% {v['mean']:+.1f}%" for k, v in r[f].items()))
            L.append(f"- B4 成交 {e}（{r['n']} 笔）信号日的分组（只列入围的）：" + "；".join(parts))
        for f in fin:
            names = names_of(f)
            L.append(f"- Zx 分组 {CAND[f]}：" + " / ".join(f"{names.get(k, f'G{k}')[:4]} {v['n']} {v['win']:.0f}% {v['mean']:+.2f}%" for k, v in res["confirm"][f]["zx_table"].items()))
    L.append("- 探索全表（W / Jx；每组 个数 / 胜率 / 每笔；Zx 与日経225 的逐特征表只对入围者算）：")
    for s in EXPLORE:
        parts = []
        for f in FIDS:
            names = names_of(f)
            parts.append(f"{f} " + " / ".join(f"{names.get(k, f'G{k}')[:4]} {v['n']} {v['win']:.0f}% {v['mean']:+.2f}%" for k, v in res["explore"][f]["tables"][s].items()))
        L.append(f"  - {s}：" + "；".join(parts))
    L += ["", f"用时 {res['elapsed_s']} s。只有汇总统计。非投资建议。"]
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
        W, FLS, FU, tbf, tbf_pool = load_all(say)
        pre = TS.prereq(W, tbf, say)
        tb = prep_bounds(W, FLS, tbf_pool)
        out = {"git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}, "counts": counts(W, FLS, FU, tbf, tbf_pool, tb)}
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return 0
    res = run(say)
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")   # 先存结果，再写报告
    try:
        md = report(res)
    except Exception:                                                        # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"报告没写出来；结果已存 {out_dir / OUT_JSON}（报告可以从它重新生成）")
        return 0
    (out_dir / OUT_MD).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
