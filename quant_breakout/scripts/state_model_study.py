"""state_model_study.py — 三态驱动 × 产业链（产出方 / 直接 / 间接）的行业模型 → 结合现行选股（突破 + W2）看胜率与每笔收益能不能提高
（2026-09-28 事先登记：两次对抗审计 + 一次复审后按意见修正；先提交后运行，结果出来不改规则）。

用户（2026-09-28）：「研究要考虑到类似原材料上涨/下跌/不变 原油上涨/下跌/不变 销售的什么什么等等的横展开 对以后行业的间接影响 /
  依据这些做个模型来结合当前的选股票算法来看能不能提高成功率和收益率」。
来由与已经看过的（照实写；研究总图 var/out/research_map.md）——同一段月份里已经看到过：
  - theme_study：进口一般炭 / 原油 → 卸売業变好（t +3.57 / +5.72）、→ 半导体 / 機械变差（t −3.5〜−7.7）、LNG → 電力反向（+2.07）；
  - transmit_study：间接成本压力 −IND → 之后 3 个月 IC −0.028（方向与事先相反；三分组 t −2.32）；个股 T4 / T5 不成立；
  - cost_sales_study：行业层 S2「销售好时偏间接」成立（+1.23% / 3 个月，t 2.65）、S1 无效；个股 S4 / S5 不成立；
  - fund_study：短観 业况 / 需给 / 价格转嫁都不通过，X2（顾客的短観业况）在前向记录（AUC 0.569）；supply_chain_study：一阶成本 IC +0.012、
    行业动量 IC +0.018〜+0.036 都不通过。
  → 以前都是「一个信号、事先定方向」。这一轮新的是：① 每个驱动分「涨 / 跌 / 不变」三态（涨与跌的影响可以不对称）；② 原油、3 种原材料、汇率、
    销售（自己与顾客）同时放进一个模型，每个驱动经产出方 / 直接 / 间接渠道；③ 方向不事先定，只用当时以前的数据学（walk-forward），只用样本外检验。
  模型可以只靠上面已见的效果过关 → 判定里另要「新证据」三条（去掉任一业种、去掉行业动量、去掉原油后仍成立）；个股层的 E' / J 窗口以前也用过
  （多重比较）→ 门槛不放宽，按固定顺序判定，另加三种随机对照。
一 数据（月末 t 已知的才用）
  驱动（3 个月的对数变化 %）：
    OIL 原油（日元计）= WTI 现货（FRED DCOILWTICO）× 美元日元（FRED DEXJPUS）的月平均（两边同一天都有；只用东京这个月最后一个交易日之前的美国日期
      —— 最后那天的美国行情在东京收盘之后）；FX 汇率 = 美元日元的同样的月平均（上升 = 日元贬值）；
    STEEL 鉄鋼 / NONFER 非鉄金属 / FOOD 食料用农水产物 = 日银企业物价（transmit_study 的 S / N / F；发布滞后 → t 月末只用到 t−1 月）；
    SALES 行业自己的销售 = 短観 大企業 売上高计划强度（qbreak/tankan.sales_strength，cost_sales_study 同一定义与可用日）；
    CUS 顾客的销售 = 产业连关表的销售份额（var/io_links_2020.json 的 cus）加权的顾客 SALES 三态（有值的顾客重新归一）。
  三态：5 个宏观驱动的 3 个月变化先去季节（减去同一月份以前各年的平均、除以同一月份以前各年的标准差；只用 t 之前、同月份 ≥ 8 年
    —— 鉄鋼的价格每年 4 月改定，不去季节 5〜7 月末 90% 以上不是「不变」），再与自己 t 以前（含 t）的全部历史的 1/3、2/3 分位比
    （至少 60 个月）→ 涨 / 不变 / 跌；SALES ≥ +0.43 → 强、≤ −0.43 → 弱、其余与缺值 → 普通（0.43 = 标准正态的三分点；SALES 已按自己历年同一次
    调查标准化）；CUS：顾客三态的加权平均 > 1/3 → 强、< −1/3 → 弱、其余与缺值 → 普通。
  暴露（事先由 2020 年产业连关表定，不看收益；東証业种按对应部门的国内生产额加权）：
    OIL 与 3 种原材料：直接 D、间接 I = var/io_indirect_2020.json（transmit_study 相同；OIL 用能源 E 的份额）；FOOD 的 D 与 I 都 93〜94% 在食料品、
      相关 0.97 → 合成一个 DI（算直接）；产出方 OWN（收入随价格走，= 1）：能源 → 鉱業、石油・石炭製品；鉄鋼 → 鉄鋼；非鉄 → 非鉄金属；
      食料 → 水産・農林業（卸売業不放：theme_study 已见，避免把已见的效果做进模型）。
    FX：直接 EXd = 输出 ÷ 国内生产额；间接 EXi =（输出诱发生产额 − 自己的输出）÷ 国内生产额（经过中间需求被输出带动的部分，含同一业种里的零部件
      与本部门自己的循环；108 部门、输入内生化的逆矩阵 (I − (I − M̂)A)^−1，M̂ = 输入计 ÷ 国内需要合计；总务省「输出诱发」同一算法；
      var/io_export_2020.json 只存导出的份额）；鉱業 的汇率暴露设为 0（表里的鉱業主要是国内采石，東証的鉱業是海外原油・天然气开发，对应不上）。
  横截面：TOPIX 1000 的 927 只按東証业种的月度相对收益（transmit_study 同一口径，2005-10〜2026-08）的 30 个业种，去掉金融 4 个（銀行・証券・
    保険・その他金融：产业连关表同一部门，暴露完全相同、收益主要随利率）→ 26 个；水産・農林業没有短観销售（SALES 普通）；サービス業 /
    情報・通信業 的 SALES 2009-04 起才有；化学 / 医薬品、ゴム製品 / その他製品 共用同一个短観业种；海運業的 SALES 来自運輸・郵便（对应差）。
二 模型（行业层；每个月末 t 预测之后 3 个月的相对收益）
  特征（业种 j、月末 t；不变 / 普通 = 基准）：OIL、STEEL、NONFER 各 6 个 = {涨, 跌} × {D, I, OWN}；FOOD 4 个 = {涨, 跌} × {DI, OWN}；
    FX 4 个 = {涨, 跌} × {EXd, EXi}；SALES 2 个（强、弱）；CUS 2 个（强、弱）→ 共 30 个。每个特征与目标都在同一个月的横截面去均值（只学业种之间的差别）。
  估计：合并面板的岭回归，惩罚 = λ × 各特征在训练集的方差（= 特征标准化后的普通岭回归），λ = 1.0 × 训练样本数（事先写死；另报 ×0.1 / ×10）。
  Walk-forward：每个月末 t 重新估计；训练集 = 信号月 s ≤ t − 3（之后 3 个月的收益在 t 时已全知道）；有目标的训练月不到 60 个 → 不预测
    → 第一个样本外月 2010-12（运行时核对）。样本外分数 ŷ(j, t)。
三 检验（行业层，样本外；信号月 = 第一个样本外月〜2026-05；两段 = 〜2016-12 / 2017-01〜；阈值都用没有四舍五入的值比）
  M1 有效 = 下面全部满足：
    · 每月 ŷ 与之后 3 个月实际相对收益的横截面秩相关 IC：平均 > 0 且 Newey–West t（4 阶）≥ 2.0；两段的平均都 > 0；
      三分组（最好 1/3 − 最差 1/3，每 3 个月不重叠取样，3 种起点的中位）命中率 ≥ 55%；
    · ① 时间错开对照（所有对照的统计量都是 IC 的 NW t）：5 个宏观三态、SALES 与 CUS 三态一起在 2005-10〜2026-08 里循环错开 s 个月（s = 24〜(月数 − 24) 的每一种），整个 walk-forward
      重跑 → 经验 p（单侧）< 0.05；
    · (a) 去掉任何一个业种（不进训练、不进 IC）后重跑，平均 IC 都 > 0；
    · (b) 去掉行业动量：每月把 ŷ 对过去 3 个月的行业相对收益做横截面回归，残差与之后 3 个月收益的秩相关 平均 > 0 且 NW t ≥ 1.645。
  新证据 = M1 有效 且 (c) 去掉 OIL 的 6 个特征后重跑，平均 IC > 0 且 NW t ≥ 1.645；M1 有效但 (c) 不满足 →「只靠能源（theme_study 已见的能源轮动），
    不算新证据」，只记录、不提议。
  来源标签（M1 有效时贴，不改提议；置换各 999 种、固定种子）：①b 只错开 5 个宏观三态（SALES / CUS 不动，全部错法）p ≥ 0.05 →「来自销售 / 顾客销售，
    原材料 / 汇率三态没有增量」；否则 ② 只置换产业连关表导出的暴露（D / I / DI / EXd / EXi）与 CUS（OWN、SALES 不动）p ≥ 0.05 →「三态有增量，
    与产业连关表的分配无关」；否则 ②b 只置换间接（I / EXi / CUS）p ≥ 0.05 →「产业链有增量，来自直接 / 产出方，不是间接传导」；否则 →
    「三态 × 间接（供应链）渠道有增量」（方向与 transmit T1 / cost_sales S2 已见的一致时在结果里注明）。
  另报（不进判定；任何一项过了门槛也不改判定、不提议，要用须另行登记、在新数据上检验）：去掉销售（只有价格 / 汇率）、只有直接渠道（去掉 I / EXi / CUS）、
    去掉 CUS、去掉 OWN、连续版（三态换成去季节后的值）、λ ×0.1 / ×10、h = 1 / 6 个月（NW 阶数 = max(4, h + 1)、三分组每 h 个月取样）、
    行业动量本身的 IC；最新的系数（每个特征 1 个标准差 ≈ 之后 3 个月相对收益 %）、现在的三态与各业种分数（只描述）。
四 检验（个股层：日経225 的突破，现行 = S0C2 + W2；scripts/leap_confirm.py 同一框架）
  窗口：E' = 2011-01-04〜2016-09-30（yfinance、今天的日経225、去掉成交量 0 与休市日的行；组合从 2011-01-04 起算）、J = 2017-01-04〜最新（J-Quants）。
    Z 窗口没有样本外的模型（行业收益 2005-10 才有）→ 不做。信号只算窗口里的（保留比例、抽签都只在窗口内；窗口前一天的信号即使第二天成交
    也不算，各方案相同）；信号日用上个月末的分数；个股层的胜率 / 每笔是框架四舍五入后的值（与对照打平算「≥」，偏保守）。
  M2（避开看淡的行业）：分数在当月 26 个业种里最低 1/3 → 不做；其余照做（金融等不在横截面的业种、没有分数的月份照做）。
  M3（只做看好的行业）：分数在最高 1/2 → 做；其余不做（例外同上）。
  判定顺序（固定，控制总误报）：M1 是「新证据」才给 M2 跑对照、判定；M2 过才给 M3 跑对照、判定；前一个不过，后面只报数字（候选本身与 ① 抽签），
    不跑 ②③④、不判定、不提议。
  M2 / M3 过 = 两个窗口都满足「选股改进」（scripts/leap2_common 的门槛：胜率 ≥ 现行 + 4 pp、每笔 ≥ + 0.5 pp、笔数 ≥ 现行的 30%、
    Calmar ≥ 现行 − 0.02 且回撤不深 2 pp 以上），且两个窗口里胜率与每笔各自对三种对照的经验 p（单侧：(1 + 对照 ≥ 候选的个数) ÷ (1 + 对照数)）
    都 < 0.05：② 驱动三态错开（与 M1 ① 同一批重跑的模型的分数，s = 24〜(月数 − 24) 的每一种；不会用到未来训练的模型）；③ 分数面板的业种标签
    置换 99 种；④ 同月同数抽签：每个月从现行信号里随机去掉与候选当月同样多的信号，99 次（控制「碰巧在坏月份少做」）；
    且两个窗口里，候选与现行各自去掉「每笔净收益之和最高」的那一个日历年后，候选的每笔与胜率仍 ≥ 现行。
  另报：① 股票 × 周抽签（同样比例，30 次）的 95% 分位；名额不够 / 现金不够被跳过的信号数（full / cash / lot）；去掉 CUS 的模型做 M2 / M3
    （J 与 E' 的 2013〜 在 X2 里看过：去掉 CUS 后不过 → 读作「与 X2 一致」）。
五 结论上限：M1 新证据 → 提议日报加「三态行业模型」显示与前向记录（用户确认）；M2 / M3 过 → 提议前向记录（用户确认；模拟盘不改）；都不成立 → 维持现行。
六 事前预期（写死；审计用合成数据估的检出力）：M1 新证据约 8%、M2 过约 2%、M3 过约 2%，全部不成立约 88%。walk-forward 估 30 个系数会把样本外 IC
  稀释到真实 IC 的 1/3〜1/2：真 IC 0.04 时 t ≥ 2 的概率约 15〜20%、0.07 约 50%（以前单个信号的 |IC| 都在 0.03 以内）；个股层现行 E' 约 45〜50 笔、
  J 约 81 笔，M2 要胜率 +4 pp 就得留下的比去掉的高约 12 pp → 即使有作用，两个窗口都过的概率也只有约 5〜10% → 不过读作「个股层检出不了」，
  不是「没有作用」。
七 局限：同一段行情以前用过（已见效果只能靠「新证据」三条挡）；数据指纹里的行业收益只取形状 / 月份 / 业种与全体之和（每次载入最后几位小数有 1e-6 级浮动），
  个股层的行情没有进指纹；2020 年的产业结构套到 2005〜2026；WTI 与汇率用 FRED 的月平均（DEXJPUS 每周公布，
  实时使用要另找实时来源）；企业物价是今天的链接值；短観是大企業；业种与成员是今天的（幸存者偏差）；λ 没有调（事先写死）；
  E' 与 J 都是今天的日経225；输入内生化只用于汇率（原材料的直接 / 间接沿用 transmit_study 的算法，保持可比）；
  三分组命中率每种起点约 62 个值，只算一致性检查。
八 登记前核对（2026-09-28 `--check`：只看结构、覆盖、三态的频率与特征的相关，没算任何收益；数据指纹 3208dabd261f，连续 3 次相同）
  业种 26 个（去掉金融 4 个）；月份 2005-10〜2026-08（251 个）；3 个月变化起点 OIL / FX 1986-04、STEEL / NONFER / FOOD 1990-05；
    去季节 + 60 个月之后的三态起点 OIL / FX 1999-03、STEEL / NONFER / FOOD 2003-04。
  三态频率（2005-10〜，涨 / 不变 / 跌 %）：OIL 29 / 35 / 36；STEEL 22 / 33 / 45；NONFER 31 / 32 / 37；FOOD 34 / 34 / 32；FX 33 / 34 / 33；
    两两同时「涨」7〜20%。去季节后各月份的标准差接近（STEEL 1.57〜1.89；原始 3 个月变化 5〜7 月 3.7、其余 1.9〜2.8），
    「不是不变」的比例按月份 48〜96%（每个月只有 23 个值，抽样误差约 ±10 pp；鉄鋼 5〜7 月 58〜62%，不再偏高）。
  SALES 有值的业种 25 / 26（没有：水産・農林業）：强 / 普通 / 弱 / 缺 36 / 29 / 30 / 5%；CUS 26 个业种都有：38 / 38 / 23%。
  汇率 EXd 最高：海運業 64.6%、電気機器 38.1%、精密機器 37.2%、機械 34.0%、非鉄金属 33.1%；EXi 最高：鉄鋼 37.7%、非鉄金属 28.5%、化学 22.9%、
    海運業 22.0%、輸送用機器 21.6%（鉱業 = 0）。
  特征 30 个，没有全为 0 的；两两相关最高 NONFER_up_D × NONFER_up_I 0.68，|相关| > 0.8 的 0 对。
  有目标的训练月 248 个；第一个样本外月 2010-12-31；样本外信号月到 2026-05 共 186 个；对照 ① / ①b 各 204 种错法，② / ②b 各 999 种置换。
输出：var/out/state_model_study.md / .json（只有统计）；var/io_export_2020.json（只存导出的份额）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import transmit_study as TS                                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak import tankan as TK                                              # noqa: E402

START, END, EVAL_END, SPLIT = "2005-10-31", TS.END, "2026-05-31", "2016-12-31"
MACRO = ["OIL", "STEEL", "NONFER", "FOOD", "FX"]
IO_KEY = {"OIL": "E", "STEEL": "S", "NONFER": "N", "FOOD": "F"}
CHANNELS = {"OIL": ("D", "I", "OWN"), "STEEL": ("D", "I", "OWN"), "NONFER": ("D", "I", "OWN"), "FOOD": ("DI", "OWN"), "FX": ("EXd", "EXi")}
IO_CH, IND_CH = {"D", "I", "DI", "EXd", "EXi"}, {"I", "EXi"}                # 对照 ② / ②b 置换的渠道（FOOD 的 DI 算直接）
OWN = {"OIL": ["鉱業", "石油・石炭製品"], "STEEL": ["鉄鋼"], "NONFER": ["非鉄金属"], "FOOD": ["水産・農林業"]}
FIN = ["銀行業", "証券、商品先物取引業", "保険業", "その他金融業"]
FX_ZERO = ["鉱業"]
SALES_CUT, CUS_CUT = 0.43, 1 / 3
MIN_HIST, MIN_SEAS, MIN_TRAIN, H, LAM, LAGS = 60, 8, 60, 3, 1.0, 4
T_MIN, T_ADD, HIT_MIN, P_MAX, GAP = 2.0, 1.645, 55.0, 0.05, 24
N_PERM, N_PERM_STOCK, N_LOT, N_WEEK = 999, 99, 99, 30
EP_WINDOWS = {"E": ("2011-01-04", "2016-09-30"), "E1": ("2011-01-04", "2013-12-31"), "E2": ("2014-01-01", "2016-09-30")}
EXPORT_FILE = "io_export_2020.json"
EXPORT_METHOD = "108部门・输入内生化 (I − (I − M̂)A)^−1（2026-09-28）"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 汇率暴露（产业连关表；有测试）─────────────────────────
def read_io108_full(xlsx) -> dict:
    """取引基本表 108 部门 → {x 交易额, X 国内生产额, e 输出计, m 输入计（正数）, dd 国内需要合计}。"""
    df = pd.read_excel(xlsx, header=None)
    hdr = [str(v).strip() for v in df.iloc[1].tolist()]
    codes = hdr[2:hdr.index("700")]
    rows = {str(df.iloc[i, 0]).strip(): i for i in range(3, df.shape[0]) if str(df.iloc[i, 0]).strip() not in ("nan", "")}
    col = lambda c: pd.Series([float(df.iloc[rows[r], hdr.index(c)]) for r in codes], index=codes)      # noqa: E731
    x = pd.DataFrame([[float(df.iloc[rows[r], 2 + k]) for k in range(len(codes))] for r in codes], index=codes, columns=codes)
    return {"x": x, "X": col("970"), "e": col("810"), "m": -col("870"), "dd": col("790")}


def export_shares(io: dict) -> tuple[pd.Series, pd.Series]:
    """部门的（直接 = 输出 ÷ 生产额，间接 =（输出诱发生产额 − 输出）÷ 生产额）；输入内生化：B = (I − M̂)A，L = (I − B)^−1。"""
    x, X, e = io["x"], io["X"], io["e"]
    A = (x / X.replace(0, np.nan)).fillna(0.0)
    mh = (io["m"] / io["dd"].where(io["dd"] > 0)).fillna(0.0).clip(0.0, 1.0)
    B = (1.0 - mh.to_numpy(float))[:, None] * A.to_numpy(float)
    L = np.linalg.inv(np.eye(len(A)) - B)
    tot = L @ e.to_numpy(float)
    Xv = X.replace(0, np.nan).to_numpy(float)
    direct = pd.Series(np.nan_to_num(e.to_numpy(float) / Xv), index=X.index)
    indirect = pd.Series(np.nan_to_num((tot - e.to_numpy(float)) / Xv), index=X.index)
    return direct, indirect


def to_tse(sec: pd.Series, X: pd.Series, industries: list[str]) -> dict[str, float]:
    """部门的份额 → 東証业种（TS.tse_of 的对应，按国内生产额加权）。"""
    by: dict[str, list[str]] = {}
    for c in sec.index:
        for t in TS.tse_of(c):
            by.setdefault(t, []).append(c)
    out = {}
    for j in industries:
        J = by.get(j, [])
        if J and X[J].sum() > 0:
            w = X[J] / X[J].sum()
            out[j] = round(float((sec[J] * w).sum()), 6)
    return out


def load_export(industries: list[str], refresh: bool = False) -> dict:
    fp = paths.home() / EXPORT_FILE
    if fp.exists() and not refresh:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        if doc.get("method") == EXPORT_METHOD and set(doc.get("industries", [])) >= set(industries):
            return doc
    xl = paths.sub("cache") / "io" / TS.IO_FILE
    if not xl.exists():                                                      # 只下载原表（不重写 var/io_indirect_2020.json）
        import urllib.request
        xl.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(TS.IO_XLSX, timeout=120) as r:              # noqa: S310
            xl.write_bytes(r.read())
    io = read_io108_full(xl)
    d, n = export_shares(io)
    doc = {"source": "総務省「令和2年（2020年）産業連関表」取引基本表（生産者価格評価、統合中分類 108 部門）；e-Stat statInfId=000040187026",
           "method": EXPORT_METHOD,
           "note": "scripts/state_model_study.py 生成：直接 = 输出 ÷ 国内生产额；间接 = [(L − I)e] ÷ 国内生产额，L = (I − (I − M̂)A)^−1，"
                   "M̂ = 输入计 ÷ 国内需要合计；東証业种按对应部门的国内生产额加权。只存导出的份额，不存原表。",
           "generated": str(pd.Timestamp.today().date()), "industries": list(industries),
           "direct": to_tse(d, io["X"], industries), "indirect": to_tse(n, io["X"], industries)}
    fp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


# ───────────────────────── 驱动与三态（有测试）─────────────────────────
def last_tokyo_day(periods) -> dict:
    """每个月（Period）东京的最后一个交易日。"""
    from qbreak.calendar_jp import is_trading_day
    out = {}
    for p in periods:
        d = p.to_timestamp(how="end").normalize()
        while not is_trading_day(d.date()):
            d -= pd.Timedelta(days=1)
        out[p] = d
    return out


def monthly_mean(s: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    """月平均，只用东京这个月最后一个交易日之前的日期（那天的美国行情在东京收盘之后）。"""
    s = s.dropna()
    per = s.index.to_period("M")
    lt = last_tokyo_day(per.unique())
    keep = np.asarray(s.index < pd.DatetimeIndex([lt[p] for p in per]), bool)
    s, per = s[keep], per[keep]
    m = s.groupby(per).mean()
    m.index = m.index.to_timestamp("M")
    return m.reindex(months)


def log_change(m: pd.Series, w: int = 3) -> pd.Series:
    lv = np.log(m.where(m > 0)) * 100
    return lv - lv.shift(w)


def deseason(x: pd.Series, min_years: int = MIN_SEAS) -> pd.Series:
    """每个 t（月度、连续的月末）：减去同一月份以前各年（t−12, t−24, …）的平均、除以它们的标准差；同月份以前的值不到 min_years 个 → 缺值。"""
    v = x.to_numpy(float)
    out = np.full(len(v), np.nan)
    for i in range(12, len(v)):
        if not np.isfinite(v[i]):
            continue
        prev = v[np.arange(i - 12, -1, -12)]
        prev = prev[np.isfinite(prev)]
        if len(prev) < min_years:
            continue
        sd = prev.std(ddof=1)
        if sd > 0:
            out[i] = (v[i] - prev.mean()) / sd
    return pd.Series(out, index=x.index)


def tercile_state(x: pd.Series, min_hist: int = MIN_HIST) -> pd.Series:
    """每个 t：x_t 与 t 以前（含 t）的全部历史的 1/3、2/3 分位比 → +1（涨）/ 0（不变）/ −1（跌）；有值的历史不到 min_hist 个 → 缺值。"""
    v = x.to_numpy(float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        if not np.isfinite(v[i]):
            continue
        h = v[: i + 1]
        h = h[np.isfinite(h)]
        if len(h) < min_hist:
            continue
        lo, hi = np.quantile(h, [1 / 3, 2 / 3])
        out[i] = 1.0 if v[i] > hi else (-1.0 if v[i] < lo else 0.0)
    return pd.Series(out, index=x.index)


def macro_changes(months: pd.DatetimeIndex, fred=None, cgpi=None) -> pd.DataFrame:
    """月末 × {OIL, STEEL, NONFER, FOOD, FX} 的 3 个月对数变化（%）。fred / cgpi 可换（测试）。"""
    if fred is None:
        from qbreak.factors import fred
    cgpi = cgpi or TS.cgpi
    wti, fx = fred("DCOILWTICO").dropna(), fred("DEXJPUS").dropna()
    both = wti.index.intersection(fx.index)
    oil = (wti.reindex(both) * fx.reindex(both)).dropna()
    P = pd.DataFrame({k: cgpi(TS.SHOCK_CGPI[IO_KEY[k]]) for k in ("STEEL", "NONFER", "FOOD")})
    dP = SC.price_change(P, months, 3)
    return pd.DataFrame({"OIL": log_change(monthly_mean(oil, months)), "STEEL": dP["STEEL"], "NONFER": dP["NONFER"], "FOOD": dP["FOOD"],
                         "FX": log_change(monthly_mean(fx, months))}, index=months)


def macro_states(ch: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(三态, 去季节后的值)。"""
    dz = pd.DataFrame({k: deseason(ch[k]) for k in ch.columns}, index=ch.index)
    return pd.DataFrame({k: tercile_state(dz[k]) for k in ch.columns}, index=ch.index), dz


def sales_states(sales_z: pd.DataFrame) -> pd.DataFrame:
    """SALES（z）→ +1 强 / −1 弱 / 0 普通；缺值 → 缺值（算 CUS 时不算这个顾客；进模型时当普通）。"""
    s = pd.DataFrame(0.0, index=sales_z.index, columns=sales_z.columns)
    s[sales_z >= SALES_CUT] = 1.0
    s[sales_z <= -SALES_CUT] = -1.0
    return s.where(sales_z.notna())


def cus_states(ss: pd.DataFrame, cus: dict[str, dict[str, float]], industries: list[str]) -> pd.DataFrame:
    """顾客 SALES 三态的加权平均（有值的顾客重新归一）→ > 1/3 强、< −1/3 弱、其余普通；没有顾客数据 → 缺值。"""
    cw = TK.customer_weighted(ss, {j: w for j, w in cus.items() if j in industries}).reindex(columns=industries)
    out = pd.DataFrame(0.0, index=cw.index, columns=industries)
    out[cw > CUS_CUT] = 1.0
    out[cw < -CUS_CUT] = -1.0
    return out.where(cw.notna())


# ───────────────────────── 特征与模型（有测试）─────────────────────────
def exposure_arrays(ex: dict, exp: dict, industries: list[str], perm_io=None, perm_ind=None) -> dict:
    """{(渠道, 驱动): 业种向量}。perm_io：产业连关表导出的暴露（D / I / DI / EXd / EXi）按置换重新分给业种（对照 ②；业种 j 拿第 perm[j] 个的）；
    perm_ind：只置换间接（I / EXi；对照 ②b）。OWN 永远不动。"""
    base = {}
    for d, k in IO_KEY.items():
        dd = np.array([ex["direct"][k].get(j, 0.0) for j in industries], float)
        ii = np.array([ex["indirect"][k].get(j, 0.0) for j in industries], float)
        if d == "FOOD":
            base[("DI", d)] = dd + ii
        else:
            base[("D", d)], base[("I", d)] = dd, ii
        base[("OWN", d)] = np.array([1.0 if j in OWN[d] else 0.0 for j in industries], float)
    base[("EXd", "FX")] = np.array([0.0 if j in FX_ZERO else exp["direct"].get(j, 0.0) for j in industries], float)
    base[("EXi", "FX")] = np.array([0.0 if j in FX_ZERO else exp["indirect"].get(j, 0.0) for j in industries], float)
    out = dict(base)
    for (ch, d), v in base.items():
        if perm_io is not None and ch in IO_CH:
            out[(ch, d)] = v[np.asarray(perm_io)]
        if perm_ind is not None and ch in IND_CH:
            out[(ch, d)] = v[np.asarray(perm_ind)]
    return out


def feature_names(drop: tuple[str, ...] = ()) -> list[str]:
    """drop 里可以是驱动（OIL…）、渠道（I、OWN、EXi…）或 SALES / CUS。"""
    names = [f"{d}_{s}_{ch}" for d in MACRO for ch in CHANNELS[d] for s in ("up", "dn")] + ["SALES_up", "SALES_dn", "CUS_up", "CUS_dn"]
    return [n for n in names if not any(tok in drop for tok in (n.split("_")[0], *n.split("_")[2:]))]


def features(ms: pd.DataFrame, ss: pd.DataFrame, cs: pd.DataFrame, expo: dict, names: list[str], continuous: pd.DataFrame | None = None) -> np.ndarray:
    """[月, 业种, 特征]，每个月横截面去均值；宏观三态有缺值的月 → 整月缺值。continuous：给了就用它（去季节后的值）代替涨 / 跌指示（另报的连续版）。"""
    T, J = len(ms), ss.shape[1]
    F = np.full((T, J, len(names)), np.nan)
    ok = ms[MACRO].notna().all(axis=1).to_numpy()
    sv, cv = ss.fillna(0.0).to_numpy(float), cs.fillna(0.0).to_numpy(float)
    for k, nm in enumerate(names):
        parts = nm.split("_")
        d, s = parts[0], parts[1]
        if d in ("SALES", "CUS"):
            v = sv if d == "SALES" else cv
            F[:, :, k] = (v == (1.0 if s == "up" else -1.0)).astype(float)
            continue
        e = expo[(parts[2], d)]
        if continuous is not None:
            g = np.nan_to_num(continuous[d].to_numpy(float)) * (1.0 if s == "up" else 0.0)      # 连续版：up 那一列放值，dn 那一列 = 0
        else:
            g = (ms[d].to_numpy(float) == (1.0 if s == "up" else -1.0)).astype(float)
        F[:, :, k] = g[:, None] * e[None, :]
    F[~ok] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                     # 整月缺值 → 缺值（不是错误）
        return F - np.nanmean(F, axis=1, keepdims=True)


def demean(Y: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return Y - np.nanmean(Y, axis=1, keepdims=True)


def walk_forward(F: np.ndarray, Y: np.ndarray, h: int = H, min_train: int = MIN_TRAIN, lam: float = LAM, min_ind: int = 10,
                 coefs: bool = False):
    """每个月 i：用信号月 s ≤ i − h（目标已全知道）的合并面板估计岭回归（惩罚 = lam × n × 各特征方差），预测 i 的横截面。
    Y 已按月去均值（缺值 = 不算）。返回 [月, 业种] 的预测（coefs=True 时另返回每个月的系数）。"""
    T, J, K = F.shape
    ok_t = np.isfinite(F).all(axis=(1, 2))
    XtX, Xty, S1, S2, N = np.zeros((T, K, K)), np.zeros((T, K)), np.zeros((T, K)), np.zeros((T, K)), np.zeros(T)
    has = np.zeros(T, bool)
    for s in range(T):
        if not ok_t[s]:
            continue
        m = np.isfinite(Y[s])
        if m.sum() < min_ind:
            continue
        X, y = F[s][m], Y[s][m]
        XtX[s], Xty[s], S1[s], S2[s], N[s], has[s] = X.T @ X, X.T @ y, X.sum(0), (X ** 2).sum(0), m.sum(), True
    cX, cy, c1, c2, cN, cM = (np.cumsum(a, axis=0) for a in (XtX, Xty, S1, S2, N, has.astype(int)))
    pred = np.full((T, J), np.nan)
    B = np.full((T, K), np.nan)
    for i in range(T):
        j = i - h
        if j < 0 or not ok_t[i] or cM[j] < min_train:
            continue
        n = cN[j]
        var = c2[j] / n - (c1[j] / n) ** 2
        pen = np.where(var > 1e-12, var, 1.0)
        b = np.linalg.solve(cX[j] + lam * n * np.diag(pen), cy[j])
        pred[i], B[i] = F[i] @ b, b
    return (pred, B) if coefs else pred


# ───────────────────────── 检验（有测试）─────────────────────────
def raw_stats(x: pd.Series, lags: int) -> tuple[float, float, int]:
    """(平均, Newey–West t, 个数)，不四舍五入。"""
    v = x.to_numpy(float)
    v = v[np.isfinite(v)]
    if len(v) < 10:
        return float("nan"), float("nan"), int(len(v))
    se = SC._nw_se(v, lags)
    m = float(v.mean())
    return m, (m / se if se and se > 0 else float("nan")), int(len(v))


def tercile_spreads(X: pd.DataFrame, Y: pd.DataFrame, step: int, offset: int, min_n: int = 9) -> np.ndarray:
    """每 step 个月一次（从第 offset 个月起，不重叠）：分数最高 1/3 − 最低 1/3 的之后收益（%）；并列按列顺序（稳定排序）。"""
    out = []
    for t in X.index[offset::step]:
        if t not in Y.index:
            continue
        x, y = X.loc[t], Y.loc[t]
        m = x.notna() & y.notna()
        if m.sum() < min_n:
            continue
        x, y = x[m], y[m]
        k = len(x) // 3
        o = x.sort_values(kind="mergesort").index
        out.append(float(y[o[-k:]].mean() - y[o[:k]].mean()))
    return np.array(out, float)


def ic_eval(pred: pd.DataFrame, Y: pd.DataFrame, h: int = H) -> dict:
    lags = max(LAGS, h + 1)
    ic = SC.fm_ic(pred, Y, lags)
    m, t, n = raw_stats(ic, lags)
    h1 = raw_stats(ic[ic.index <= pd.Timestamp(SPLIT)], lags)[0]
    h2 = raw_stats(ic[ic.index > pd.Timestamp(SPLIT)], lags)[0]
    hits, spr = [], []
    for ph in range(h):
        a = tercile_spreads(pred, Y, h, ph)
        if len(a):
            hits.append(float((a > 0).mean() * 100))
            spr.append(float(a.mean()))
    return {"ic": m, "t": t, "n": n, "H1": h1, "H2": h2, "hits": hits, "hit": float(np.median(hits)) if hits else float("nan"),
            "spread": float(np.median(spr)) if spr else float("nan"), "_ic": ic}


def ic_t(pred: pd.DataFrame, Y: pd.DataFrame, h: int = H) -> float:
    lags = max(LAGS, h + 1)
    return raw_stats(SC.fm_ic(pred, Y, lags), lags)[1]


def momentum_residual(pred: pd.DataFrame, mom: pd.DataFrame, min_n: int = 8) -> pd.DataFrame:
    """每个月：分数对过去 3 个月的行业相对收益做横截面回归（含常数）→ 残差（去掉行业动量的部分）。"""
    out = pd.DataFrame(np.nan, index=pred.index, columns=pred.columns)
    mm = mom.reindex(index=pred.index, columns=pred.columns)
    for t in pred.index:
        y, x = pred.loc[t], mm.loc[t]
        m = y.notna() & x.notna()
        if m.sum() < min_n:
            continue
        X = np.column_stack([np.ones(int(m.sum())), x[m].to_numpy(float)])
        b, *_ = np.linalg.lstsq(X, y[m].to_numpy(float), rcond=None)
        out.loc[t, m[m].index] = y[m].to_numpy(float) - X @ b
    return out


def m1_fails(r: dict, p_shift, loo_min, resid: dict) -> list[str]:
    f = []
    if not (np.isfinite(r["ic"]) and r["ic"] > 0 and np.isfinite(r["t"]) and r["t"] >= T_MIN):
        f.append(f"IC {r['ic']:+.4f}（t {r['t']:.2f}）不够")
    if not (np.isfinite(r["H1"]) and r["H1"] > 0 and np.isfinite(r["H2"]) and r["H2"] > 0):
        f.append(f"两段 {r['H1']:+.4f} / {r['H2']:+.4f} 不都 > 0")
    if not (np.isfinite(r["hit"]) and r["hit"] >= HIT_MIN):
        f.append(f"命中率 {r['hit']:.1f}% < {HIT_MIN}%")
    if not (p_shift is not None and p_shift < P_MAX):
        f.append(f"① 时间错开对照 p {p_shift}")
    if not (loo_min is not None and np.isfinite(loo_min) and loo_min > 0):
        f.append(f"(a) 去掉某个业种后平均 IC 最低 {loo_min}")
    if not (np.isfinite(resid["ic"]) and resid["ic"] > 0 and np.isfinite(resid["t"]) and resid["t"] >= T_ADD):
        f.append(f"(b) 去掉行业动量后 IC {resid['ic']:+.4f}（t {resid['t']:.2f}）不够")
    return f


def m1_new(r_nooil: dict) -> bool:
    return bool(np.isfinite(r_nooil["ic"]) and r_nooil["ic"] > 0 and np.isfinite(r_nooil["t"]) and r_nooil["t"] >= T_ADD)


def m1_label(p1b, p2, p2b) -> str:
    if not (p1b is not None and p1b < P_MAX):
        return "来自销售 / 顾客销售，原材料 / 汇率三态没有增量"
    if not (p2 is not None and p2 < P_MAX):
        return "三态有增量，与产业连关表的分配无关"
    if not (p2b is not None and p2b < P_MAX):
        return "产业链有增量，来自直接 / 产出方，不是间接传导"
    return "三态 × 间接（供应链）渠道有增量"


def m1_verdict(fails: list[str], new: bool, label: str) -> str:
    if fails:
        return "无效"
    if not new:
        return "有预测力，但只靠能源（theme_study 已见的能源轮动），不算新证据"
    return f"三态 × 产业链模型有预测力（新证据；{label}）"


def roll_window(X: pd.DataFrame, s: int, a, b) -> pd.DataFrame:
    """只在 [a, b] 的月份里循环错开 s 期（其余不动）。"""
    out = X.copy()
    m = (X.index >= pd.Timestamp(a)) & (X.index <= pd.Timestamp(b))
    out.loc[m] = SC.roll(X.loc[m], s).to_numpy()
    return out


def perms(n: int, k: int, seed0: int = 0) -> list[np.ndarray]:
    return [np.random.default_rng(seed0 + i).permutation(n) for i in range(k)]


# ───────────────────────── 个股层（有测试）─────────────────────────
def skip_panel(score: pd.DataFrame, rule: str) -> pd.DataFrame:
    """月末 × 业种：下个月不做（True）。M2：横截面最低 1/3；M3：不在最高 1/2。没有分数 → 照做。"""
    r = score.rank(axis=1, pct=True)
    bad = (r <= 1 / 3) if rule == "M2" else (r <= 1 / 2)
    return bad & score.notna()


def stock_keep(fr: dict, s33: dict, score: pd.DataFrame, rule: str) -> dict[str, np.ndarray]:
    bad = skip_panel(score, rule).astype(float)
    out = {}
    for t, df in fr.items():
        ind = s33.get(t)
        if ind not in bad.columns:
            out[t] = np.ones(len(df), bool)
            continue
        v = TS.daily_from_monthly(bad[ind], df.index).to_numpy(float)
        out[t] = ~(np.nan_to_num(v, nan=0.0) > 0.5)
    return out


def in_window(fr: dict, a, b) -> dict:
    """只留窗口 [a, b] 里的信号（窗口外的本来也不会成交；保留比例与抽签只算窗口里的）。"""
    out = {}
    for t, df in fr.items():
        m = np.asarray(df.index >= pd.Timestamp(a), bool)
        if b:
            m &= np.asarray(df.index <= pd.Timestamp(b), bool)
        out[t] = df.assign(entry=df["entry"].to_numpy(bool) & m)
    return out


def month_lottery(fr: dict, keep: dict, seed: int) -> dict[str, np.ndarray]:
    """对照 ④：每个日历月，从现行信号里随机去掉与候选当月去掉的一样多的信号。"""
    rng = np.random.default_rng(seed)
    allm, removed = defaultdict(list), Counter()
    for t, df in fr.items():
        e = df["entry"].to_numpy(bool)
        k = np.asarray(keep.get(t, np.ones(len(df), bool)), bool)
        for i in np.flatnonzero(e):
            m = df.index[i].to_period("M")
            allm[m].append((t, int(i)))
            if not k[i]:
                removed[m] += 1
    out = {t: np.ones(len(df), bool) for t, df in fr.items()}
    for m in sorted(allm):
        r = removed.get(m, 0)
        if r:
            for q in rng.choice(len(allm[m]), size=r, replace=False):
                t, i = allm[m][q]
                out[t][i] = False
    return out


def emp_p(actual, vals) -> float | None:
    """经验 p（单侧，越大越好）：(1 + 对照 ≥ 实际的个数) ÷ (1 + 对照数)。"""
    a = np.array([v for v in vals if v is not None and np.isfinite(v)], float)
    if actual is None or not np.isfinite(actual) or not len(a):
        return None
    return float((1 + np.sum(a >= actual)) / (1 + len(a)))


def ex_best_sum(tr: pd.DataFrame, a, b) -> dict:
    """窗口内的每笔；去掉「每笔净收益之和」最高的那个日历年后的笔数 / 每笔 / 胜率。"""
    m = (tr["entry_date"] >= pd.Timestamp(a)) & ((tr["entry_date"] <= pd.Timestamp(b)) if b else True)
    x = tr[m]
    if not len(x):
        return {"best_year": None, "n": 0, "mean": None, "win": None}
    y = x["entry_date"].dt.year
    best = int(x.groupby(y)["net"].sum().idxmax())
    z = x[y != best]
    return {"best_year": best, "n": int(len(z)), "mean": float(z["net"].mean()) if len(z) else None,
            "win": float((z["net"] > 0).mean() * 100) if len(z) else None}


def improve2(cand: dict, base: dict, windows=("E", "J")) -> list[str]:
    """leap2_common.improve_fails 的同一门槛，只看 E' 与 J 两个窗口。"""
    import leap2_common as L2
    c_ = lambda x: float(x) if L2.is_finite(x) else float("nan")                  # noqa: E731
    out = []
    for w in windows:
        a, b = cand.get(w) or {}, base.get(w) or {}
        if not c_(a.get("win")) >= c_(b.get("win")) + L2.IMPROVE_WIN_PP:
            out.append(f"{w} 胜率没高 {L2.IMPROVE_WIN_PP:.0f} pp")
        if not c_(a.get("mean")) >= c_(b.get("mean")) + L2.IMPROVE_MEAN_PP:
            out.append(f"{w} 每笔没高 {L2.IMPROVE_MEAN_PP} pp")
        if not c_(a.get("n")) >= L2.MIN_N_FRAC * c_(b.get("n")):
            out.append(f"{w} 笔数不到现行的 {L2.MIN_N_FRAC:.0%}")
        if not (c_(a.get("calmar")) >= c_(b.get("calmar")) - L2.CALMAR_TOL and c_(a.get("dd")) >= c_(b.get("dd")) - L2.DD_TOL_PP):
            out.append(f"{w} 组合变差")
    return out


def stock_fails(cid: str, W: dict) -> list[str]:
    """M2 / M3 的判定（选股改进 + 三种对照的经验 p + 去掉最好一年）。"""
    base = {e: W[e]["res"]["现行"][e] for e in ("E", "J")}
    cand = {e: W[e]["res"][cid][e] for e in ("E", "J")}
    f = improve2(cand, base)
    lab = {"shift": "② 三态错开", "perm": "③ 业种置换", "month": "④ 同月同数"}
    for e in ("E", "J"):
        for k, nm in lab.items():
            q = (W[e]["pl"][cid] or {}).get(k) or {}
            for key, zh in (("win_p", "胜率"), ("mean_p", "每笔")):
                if not (q.get(key) is not None and q[key] < P_MAX):
                    f.append(f"{e} {nm}对照 {zh} p {q.get(key)}")
        bc, b0 = W[e]["best"][cid], W[e]["best"]["现行"]
        ok = (bc.get("mean") is not None and b0.get("mean") is not None and bc["mean"] >= b0["mean"]
              and bc.get("win") is not None and b0.get("win") is not None and bc["win"] >= b0["win"])
        if not ok:
            f.append(f"{e} 去掉最好一年后不比现行好")
    return f


def eprime_context():
    import leap_confirm as LF
    ctx = dict(LF.context("E"))
    ctx["windows"], ctx["start"], ctx["end"] = dict(EP_WINDOWS), EP_WINDOWS["E"][0], EP_WINDOWS["E"][1]
    return ctx


def stock_windows(s33: dict, score: pd.DataFrame, shift_scores: dict[int, pd.DataFrame], side_scores: dict[str, pd.DataFrame],
                  placebo_for: tuple[str, ...] = (), W: dict | None = None) -> dict:
    """W 为空：跑现行 / M2 / M3、① 股票 × 周抽签与另报，再给 placebo_for 里的方案跑 ②③④；W 给了：只给 placebo_for 补跑 ②③④（M2 过了才补 M3）。"""
    import jq_study as JS
    import leap_confirm as LF
    import pit_recheck as PR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    skipped = lambda: {k: int(JS.RealLotEngine.LAST[-1].skipped.get(k, 0)) for k in ("full", "cash", "lot")}   # noqa: E731
    res = W if W is not None else {}
    for era in ("E", "J"):
        t0 = time.time()
        ctx = eprime_context() if era == "E" else LF.context("J")
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        a, b = ctx["windows"][era]
        fw = in_window(LF.with_mask(fa, LF.w2_keep(ctx, fa)), a, b)
        if W is None:
            r = {"现行": LF.run(ctx, run_fn, fw, p)}
            best, sk = {"现行": ex_best_sum(PR.last_trades(), a, b)}, {"现行": skipped()}
            pl, frac = {}, {}
            for cid in ("M2", "M3"):
                keep = stock_keep(fw, s33, score, cid)
                frac[cid] = LF.keep_frac(fw, keep)
                r[cid] = LF.run(ctx, run_fn, LF.with_mask(fw, keep), p)
                best[cid], sk[cid] = ex_best_sum(PR.last_trades(), a, b), skipped()
                q1 = LF.placebo_trades(ctx, run_fn, fw, p, frac[cid], seeds=N_WEEK, q=95)
                pl[cid] = {"week_q95": {"win": q1["win"], "mean": q1["mean"]}}
            side = {}
            for key, sc in side_scores.items():
                for cid in ("M2", "M3"):
                    side[f"{cid}·{key}"] = LF.run(ctx, run_fn, LF.with_mask(fw, stock_keep(fw, s33, sc, cid)), p)[era]
            res[era] = {"res": r, "pl": pl, "frac": frac, "best": best, "skipped": sk, "side": side, "secs": 0}
        for cid in placebo_for:
            keep = stock_keep(fw, s33, score, cid)
            variants = {"shift": (stock_keep(fw, s33, sc, cid) for sc in shift_scores.values()),        # 逐个生成（不全放内存）
                        "perm": (stock_keep(fw, s33, pd.DataFrame(score.to_numpy()[:, pm], index=score.index, columns=score.columns), cid)
                                 for pm in perms(score.shape[1], N_PERM_STOCK, 1000)),
                        "month": (month_lottery(fw, keep, 2000 + i) for i in range(N_LOT))}
            cw, cm = res[era]["res"][cid][era].get("win"), res[era]["res"][cid][era].get("mean")
            for k, kk_iter in variants.items():
                wv, mv = [], []
                for kk in kk_iter:
                    rs = LF.run(ctx, run_fn, LF.with_mask(fw, kk), p)[era]
                    wv.append(rs.get("win"))
                    mv.append(rs.get("mean"))
                fin_w, fin_m = [v for v in wv if v is not None], [v for v in mv if v is not None]
                res[era]["pl"][cid][k] = {"n": len(wv), "win_p": emp_p(cw, wv), "mean_p": emp_p(cm, mv),
                                          "win_q95": float(np.percentile(fin_w, 95)) if fin_w else None,
                                          "mean_q95": float(np.percentile(fin_m, 95)) if fin_m else None}
        res[era]["secs"] += round(time.time() - t0)
    return res


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> str:
    root = str(paths.PROJECT_ROOT)
    try:
        rev = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", "scripts", "qbreak", "var/io_indirect_2020.json",
                                     "var/io_export_2020.json", "var/io_links_2020.json", "var/industry_s33.json", "var/sim.json"],
                                    capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return rev + ("（脏）" if dirty else "")


def data_hash(*objs) -> str:
    h = hashlib.sha256()
    for f in objs:
        if isinstance(f, (pd.DataFrame, pd.Series)):
            h.update(pd.util.hash_pandas_object(f.round(6), index=True).values.tobytes())
        else:
            h.update(json.dumps(f, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:12]


def mret_facts(M: pd.DataFrame) -> dict:
    """行业收益面板里稳定的部分（每次载入最后几位小数会有 1e-6 级的浮动 → 不直接哈希数值）：形状、月份、业种、全体之和（0.1 pp）。"""
    return {"shape": list(M.shape), "index": [str(x.date()) for x in M.index], "columns": list(M.columns),
            "sum": round(float(np.nansum(M.to_numpy(float))), 1)}


def build(inds: list[str], months: pd.DatetimeIndex) -> dict:
    """驱动三态、销售三态、暴露（不看收益）。"""
    long = pd.date_range("1986-01-31", END, freq="ME")
    ch = macro_changes(long)
    ms_l, dz_l = macro_states(ch)
    S = TK.load_sales()
    need = {c for g in inds for c in TK.TSE.get(g, [])} | set(TK.SALES_OLD.values())
    bad = [c for c in TK.MISSING if "102CFY" in c and c[5:9] in need]
    if bad:
        raise SystemExit(f"短観売上高 取不到：{bad}（不跑，防止横截面悄悄变小）")
    sz = TK.to_tse(TK.sales_strength(S, months), inds).reindex(columns=inds)
    ss = sales_states(sz)
    links = json.loads((paths.home() / "io_links_2020.json").read_text(encoding="utf-8"))
    cs = cus_states(ss, links["cus"], inds)
    return {"ch": ch, "ms_long": ms_l, "ms": ms_l.reindex(months), "dz": dz_l.reindex(months), "sz": sz, "ss": ss, "cs": cs,
            "ex": TS.load_exposures(inds), "exp": load_export(inds)}


def run_model(D: dict, inds: list[str], Yd: np.ndarray, ms=None, ss=None, cs=None, perm_io=None, perm_ind=None, drop=(), lam=LAM, h=H,
              continuous=False, sub: list[int] | None = None):
    """sub：只用这些业种（位置）；perm_io / perm_ind：对照 ② / ②b（CUS 跟着同一置换）。"""
    names = feature_names(drop)
    ms_ = D["ms"] if ms is None else ms
    ss_ = D["ss"] if ss is None else ss
    cs_ = D["cs"] if cs is None else cs
    pm = perm_io if perm_io is not None else perm_ind
    assert sub is None or pm is None, "去掉业种与置换不同时用"
    if pm is not None:
        cs_ = pd.DataFrame(cs_.to_numpy()[:, np.asarray(pm)], index=cs_.index, columns=cs_.columns)
    use = list(range(len(inds))) if sub is None else list(sub)
    ind_u = [inds[i] for i in use]
    expo = exposure_arrays(D["ex"], D["exp"], ind_u, perm_io, perm_ind)
    F = features(ms_, ss_.iloc[:, use], cs_.iloc[:, use], expo, names, D["dz"] if continuous else None)
    return walk_forward(F, Yd[:, use], h=h, lam=lam), names, F


def frame(pred: np.ndarray, months, cols) -> pd.DataFrame:
    return pd.DataFrame(pred, index=months, columns=cols)


def fmt(r: dict) -> str:
    return (f"IC {r['ic']:+.4f}（t {r['t']:.2f}，{r['n']} 个月）；两段 {r['H1']:+.4f} / {r['H2']:+.4f}；三分组 最好 − 最差 {r['spread']:+.2f}%，"
            f"命中率 {r['hit']:.1f}%（各起点 {', '.join(f'{v:.1f}' for v in r['hits'])}）")


def check(Mret: pd.DataFrame, inds: list[str], months: pd.DatetimeIndex, D: dict, dh: str) -> int:
    ms = D["ms"]
    print(f"业种 {len(inds)} 个（去掉金融 4 个）；月份 {months[0].date()}〜{months[-1].date()}（{len(months)} 个）；数据指纹 {dh}")
    print("宏观驱动的 3 个月变化起点：" + "、".join(f"{k} {D['ch'][k].first_valid_index().date()}" for k in MACRO)
          + "；三态起点：" + "、".join(f"{k} {D['ms_long'][k].first_valid_index().date()}" for k in MACRO))
    print("三态频率（2005-10〜，涨 / 不变 / 跌 %）：" + "；".join(
        f"{k} {(ms[k] == 1).mean() * 100:.0f} / {(ms[k] == 0).mean() * 100:.0f} / {(ms[k] == -1).mean() * 100:.0f}" for k in MACRO))
    L = D["ms_long"].dropna()
    nf = {k: (L[k] != 0).groupby(L.index.month).mean() * 100 for k in MACRO}
    print("去季节后「不是不变」的比例按月份（全部历史，最低〜最高 %）：" + "；".join(f"{k} {v.min():.0f}〜{v.max():.0f}" for k, v in nf.items()))
    print("三态两两同时为「涨」的比例 %：" + "、".join(f"{x}&{y} {((ms[x] == 1) & (ms[y] == 1)).mean() * 100:.0f}"
                                           for i, x in enumerate(MACRO) for y in MACRO[i + 1:]))
    ss, cs = D["ss"], D["cs"]
    print(f"SALES 有值的业种 {int(ss.notna().any().sum())} / {len(inds)}（没有：{'、'.join(j for j in inds if not ss[j].notna().any())}）；"
          f"强 / 普通 / 弱 / 缺 %：{(ss == 1).mean().mean() * 100:.0f} / {(ss == 0).mean().mean() * 100:.0f} / {(ss == -1).mean().mean() * 100:.0f} / "
          f"{ss.isna().mean().mean() * 100:.0f}")
    print(f"CUS 有值的业种 {int(cs.notna().any().sum())}；强 / 普通 / 弱 / 缺 %：{(cs == 1).mean().mean() * 100:.0f} / {(cs == 0).mean().mean() * 100:.0f} / "
          f"{(cs == -1).mean().mean() * 100:.0f} / {cs.isna().mean().mean() * 100:.0f}")
    ex = exposure_arrays(D["ex"], D["exp"], inds)
    for key in (("EXd", "FX"), ("EXi", "FX")):
        v = pd.Series(ex[key], index=inds).sort_values(ascending=False)
        print(f"汇率 {key[0]} 最高：" + "、".join(f"{j} {x * 100:.1f}%" for j, x in v.head(5).items()))
    names = feature_names()
    F = features(D["ms"], D["ss"], D["cs"], ex, names)
    X = F.reshape(-1, len(names))
    X = X[np.isfinite(X).all(axis=1)]
    sd = X.std(axis=0)
    zero = [n for n, v in zip(names, sd) if v < 1e-12]
    nz = [n for n, v in zip(names, sd) if v >= 1e-12]
    C = np.corrcoef(X[:, sd >= 1e-12].T)
    np.fill_diagonal(C, 0)
    k = np.unravel_index(np.nanargmax(np.abs(C)), C.shape)
    print(f"特征 {len(names)} 个；全为 0 的 {zero}；两两相关最高 {nz[k[0]]} × {nz[k[1]]} {C[k]:.2f}；|相关| > 0.8 的对数 {int((np.abs(C) > 0.8).sum() // 2)}")
    yfin = np.isfinite(SC.ahead(Mret, H).reindex(index=months, columns=inds).to_numpy(float)).sum(axis=1) >= 10
    cm = np.cumsum(yfin)
    first = next((months[i] for i in range(H, len(months)) if cm[i - H] >= MIN_TRAIN), None)
    n_ev = int(((months >= first) & (months <= pd.Timestamp(EVAL_END))).sum()) if first is not None else 0
    print(f"有目标的训练月 {int(yfin.sum())} 个；第一个样本外月 {first.date() if first is not None else '—'}；样本外信号月到 2026-05 共 {n_ev} 个；"
          f"对照 ① / ①b 各 {len(months) - 2 * GAP + 1} 种错法，② / ②b 各 {N_PERM} 种置换")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报结构、覆盖、三态频率与特征相关（不看任何收益）")
    ap.add_argument("--skip-stock", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    Mret, s33 = TS.load_industry_returns()
    inds = [j for j in Mret.columns if j not in FIN]
    months = pd.date_range(START, END, freq="ME")
    D = build(inds, months)
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    dh = data_hash(mret_facts(Mret[inds]), s33, sim, D["ms"], D["ss"].fillna(9), D["cs"].fillna(9),
                   {k: D["ex"][k] for k in ("direct", "indirect")}, {k: D["exp"][k] for k in ("direct", "indirect")})
    if a.check:
        return check(Mret, inds, months, D, dh)
    say(f"# 三态驱动 × 产业链的行业模型 → 结合现行选股（{pd.Timestamp.today().date()}；git {git_info()}；数据指纹 {dh}）")
    say("规则见 scripts/state_model_study.py 开头（先提交后运行）。IC = 模型分数与之后 3 个月行业相对收益的横截面秩相关（26 个业种）。")
    Yraw = SC.ahead(Mret, H).reindex(index=months, columns=inds)
    Yd = demean(Yraw.to_numpy(float))
    pred, names, F = run_model(D, inds, Yd)
    P = frame(pred, months, inds)
    ev = P.index[P.notna().any(axis=1) & (P.index <= pd.Timestamp(EVAL_END))]
    Pe, Ye = P.reindex(ev), Yraw.reindex(ev)
    r1 = ic_eval(Pe, Ye)
    a0, b0 = months[0], months[-1]
    shifts = range(GAP, len(months) - GAP + 1)
    shift_scores, t1, t1b = {}, [], []
    for s in shifts:
        pr, _, _ = run_model(D, inds, Yd, ms=roll_window(D["ms"], s, a0, b0), ss=roll_window(D["ss"], s, a0, b0), cs=roll_window(D["cs"], s, a0, b0))
        shift_scores[s] = frame(pr, months, inds)
        t1.append(ic_t(shift_scores[s].reindex(ev), Ye))
        pr, _, _ = run_model(D, inds, Yd, ms=roll_window(D["ms"], s, a0, b0))
        t1b.append(ic_t(frame(pr, months, inds).reindex(ev), Ye))
    t2, t2b = [], []
    for pm in perms(len(inds), N_PERM):
        pr, _, _ = run_model(D, inds, Yd, perm_io=pm)
        t2.append(ic_t(frame(pr, months, inds).reindex(ev), Ye))
    for pm in perms(len(inds), N_PERM, 5000):
        pr, _, _ = run_model(D, inds, Yd, perm_ind=pm)
        t2b.append(ic_t(frame(pr, months, inds).reindex(ev), Ye))
    pv = {k: SC.placebo_p(r1["t"], np.array(v, float)) for k, v in (("①", t1), ("①b", t1b), ("②", t2), ("②b", t2b))}
    q95 = {k: round(float(np.nanpercentile(np.array(v, float), 95)), 2) for k, v in (("①", t1), ("①b", t1b), ("②", t2), ("②b", t2b))}
    loo = {}
    Yr = Yraw.to_numpy(float)
    for i, j in enumerate(inds):
        sub = [k for k in range(len(inds)) if k != i]
        Ys = np.full_like(Yr, np.nan)
        Ys[:, sub] = demean(Yr[:, sub])                                      # 目标只在剩下的业种里去均值
        pr, _, _ = run_model(D, inds, Ys, sub=sub)
        loo[j] = raw_stats(SC.fm_ic(frame(pr, months, [inds[k] for k in sub]).reindex(ev), Ye, LAGS), LAGS)[0]
    vals = list(loo.values())
    loo_min = float(min(vals)) if all(np.isfinite(v) for v in vals) else float("nan")   # 有一个算不出 → 不满足
    mom = SC.past(Mret, 3).reindex(index=months, columns=inds)
    rres = ic_eval(momentum_residual(Pe, mom.reindex(ev)), Ye)
    pr, _, _ = run_model(D, inds, Yd, drop=("OIL",))
    rno = ic_eval(frame(pr, months, inds).reindex(ev), Ye)
    f1 = m1_fails(r1, pv["①"], loo_min, rres)
    new = m1_new(rno)
    label = m1_label(pv["①b"], pv["②"], pv["②b"])
    v1 = m1_verdict(f1, new, label)
    say(f"\n## M1（主）行业层：样本外 {ev[0].date()}〜{ev[-1].date()}（{len(ev)} 个月）")
    say(f"- 模型：{fmt(r1)}")
    say(f"- ① 时间错开（全部三态，{len(t1)} 种）：t 的 95% 分位 {q95['①']}、经验 p {pv['①']}")
    say(f"- (a) 去掉任何一个业种后的平均 IC：最低 {loo_min:+.4f}"
        + (f"（去掉 {min(loo, key=loo.get)}）" if np.isfinite(loo_min) else "（有算不出的）"))
    say(f"- (b) 去掉行业动量后：{fmt(rres)}")
    say(f"- (c) 去掉 OIL 的 6 个特征：{fmt(rno)}")
    say(f"- 来源对照：①b 只错开宏观三态 95% 分位 {q95['①b']}、p {pv['①b']}；② 置换产业连关表暴露 + CUS（{N_PERM} 种）95% 分位 {q95['②']}、p {pv['②']}；"
        f"②b 只置换间接 95% 分位 {q95['②b']}、p {pv['②b']}")
    say(f"- 判定：{'M1 有效' if not f1 else '不满足：' + '；'.join(f1)} → **{v1}**")
    res = {"git": git_info(), "data_hash": dh, "industries": inds, "first_oos": str(ev[0].date()), "oos_months": int(len(ev)),
           "M1": {**{k: v for k, v in r1.items() if k != "_ic"}, "p": pv, "q95": q95, "loo": loo, "loo_min": loo_min,
                  "resid": {k: v for k, v in rres.items() if k != "_ic"}, "no_oil": {k: v for k, v in rno.items() if k != "_ic"},
                  "fails": f1, "new_evidence": new, "label": label, "verdict": v1}}
    side = {}
    for key, kw in (("去掉销售（只有价格 / 汇率）", {"drop": ("SALES", "CUS")}), ("只有直接渠道", {"drop": ("I", "EXi", "CUS")}),
                    ("去掉 CUS", {"drop": ("CUS",)}), ("去掉 OWN", {"drop": ("OWN",)}), ("连续版", {"continuous": True}),
                    ("λ ×0.1", {"lam": LAM * 0.1}), ("λ ×10", {"lam": LAM * 10})):
        pr, _, _ = run_model(D, inds, Yd, **kw)
        side[key] = ic_eval(frame(pr, months, inds).reindex(ev), Ye)
    for hh in (1, 6):
        Yh = SC.ahead(Mret, hh).reindex(index=months, columns=inds)
        pr, _, _ = run_model(D, inds, demean(Yh.to_numpy(float)), h=hh)
        side[f"h = {hh} 个月"] = ic_eval(frame(pr, months, inds).reindex(ev), Yh.reindex(ev), h=hh)
    side["行业动量本身"] = ic_eval(mom.reindex(ev), Ye)
    say("\n## 另报（不进判定；过了门槛也不改判定、不提议）")
    for k, r in side.items():
        say(f"- {k}：{fmt(r)}")
    _, B = walk_forward(F, Yd, coefs=True)
    last = int(np.where(np.isfinite(B).all(axis=1))[0][-1])
    Xs = F.reshape(-1, len(names))
    sd = np.nanstd(Xs[np.isfinite(Xs).all(axis=1)], axis=0)
    co = pd.Series(B[last] * sd, index=names)
    say(f"- 最新模型（{months[last].date()} 末估计）每个特征 1 个标准差 ≈ 之后 3 个月相对收益 %，绝对值最大的 8 个："
        + "、".join(f"{k} {v:+.2f}" for k, v in co.reindex(co.abs().sort_values(ascending=False).index).head(8).items()))
    now = D["ms"].iloc[-1]
    say(f"- 现在（{months[-1].date()} 末）的三态：" + "、".join(f"{k} {'涨' if v == 1 else '跌' if v == -1 else '不变' if v == 0 else '—'}" for k, v in now.items()))
    sc_now = P.iloc[-1].dropna().sort_values(ascending=False)
    if len(sc_now):
        say(f"- 现在的分数（只描述，不是建议）：最高 {'、'.join(sc_now.index[:5])}；最低 {'、'.join(sc_now.index[-5:])}")
    res.update({"side": {k: {kk: vv for kk, vv in v.items() if kk != "_ic"} for k, v in side.items()},
                "coef_latest": {k: round(float(v), 4) for k, v in co.items()}, "coef_month": str(months[last].date()),
                "states_now": {k: (None if pd.isna(v) else float(v)) for k, v in now.items()},
                "score_now": {k: round(float(v), 4) for k, v in sc_now.items()}})
    write_out(res)
    if not a.skip_stock:
        full = not f1 and new
        pr, _, _ = run_model(D, inds, Yd, drop=("CUS",))
        W = stock_windows(s33, P, shift_scores, {"去掉 CUS": frame(pr, months, inds)}, placebo_for=("M2",) if full else ())
        judged = {}
        if full:
            judged["M2"] = stock_fails("M2", W)
            if not judged["M2"]:                                             # 固定顺序：M2 过了才给 M3 跑对照、判定
                W = stock_windows(s33, P, shift_scores, {}, placebo_for=("M3",), W=W)
                judged["M3"] = stock_fails("M3", W)
        say("\n## M2 / M3（个股：日経225 的突破，现行 = S0C2 + W2；E' = 2011-01〜2016-09 yfinance，J = 2017〜 J-Quants）"
            + ("" if full else "：M1 不是新证据 → 按事先的顺序只报数字，不判定"))
        say("| 窗口 | 方案 | 组合 年化 / 回撤 / Calmar · 个股笔数 每笔 / 胜率 | 保留 | 去掉最好一年（按每笔之和）| 跳过 full / cash / lot |")
        say("|---|---|---|---|---|---|")
        for era in ("E", "J"):
            for k, r in W[era]["res"].items():
                s = r[era]
                bb, kk = W[era]["best"].get(k) or {}, W[era]["skipped"].get(k) or {}
                say(f"| {era}{'′' if era == 'E' else ''} | {k} | {s.get('cagr')}% / {s.get('dd')}% / {s.get('calmar')} · {s.get('n')} 笔 {s.get('mean')}% / {s.get('win')}% | "
                    f"{W[era]['frac'].get(k, 1) * 100:.0f}% | "
                    + (f"去 {bb['best_year']}：{bb['n']} 笔 {bb['mean']:+.2f}% / {bb['win']:.0f}%" if bb.get("n") else "—")
                    + f" | {kk.get('full')} / {kk.get('cash')} / {kk.get('lot')} |")
        for era in ("E", "J"):
            for cid in ("M2", "M3"):
                ent = W[era]["pl"][cid]
                line = f"- {era}{'′' if era == 'E' else ''} {cid} 对照：① 股票 × 周 95% 分位 胜率 {ent['week_q95']['win']:.1f}% / 每笔 {ent['week_q95']['mean']:+.2f}%"
                for k, nm in (("shift", "② 三态错开"), ("perm", "③ 业种置换"), ("month", "④ 同月同数")):
                    if k in ent:
                        q = ent[k]
                        line += f"；{nm}（{q['n']} 次）胜率 p {q['win_p']}、每笔 p {q['mean_p']}"
                say(line)
            for k, s in W[era]["side"].items():
                say(f"- {era}{'′' if era == 'E' else ''} 另报 {k}：{s.get('n')} 笔 {s.get('mean')}% / {s.get('win')}%；Calmar {s.get('calmar')}")
        if full:
            say(f"- M2：{'选股改进成立' if not judged['M2'] else '不成立：' + '；'.join(judged['M2'])}")
            if "M3" in judged:
                say(f"- M3：{'选股改进成立' if not judged['M3'] else '不成立：' + '；'.join(judged['M3'])}")
            else:
                say("- M3：M2 没过 → 按顺序不判定、不跑对照（只报数字）")
        res["stock"] = {"full": full, "judged": judged,
                        "windows": {e: {"res": {k: {w: v for w, v in r.items() if not str(w).startswith("_")} for k, r in W[e]["res"].items()},
                                        "pl": W[e]["pl"], "frac": W[e]["frac"], "best": W[e]["best"], "skipped": W[e]["skipped"],
                                        "side": W[e]["side"], "secs": W[e]["secs"]} for e in W}}
    say("\n## 结论（事先规则）")
    say(f"- 行业层：{v1}" + ("→ 提议日报加「三态行业模型」显示与前向记录（用户确认）" if (not f1 and new) else "") + "。")
    if not a.skip_stock:
        ok = [k for k, f in res["stock"]["judged"].items() if not f]
        say("- 个股层：" + (("、".join(ok) + " 过 → 提议前向记录（用户确认；模拟盘不改）") if ok else
                          ("M2 / M3 不过 → 模拟盘不变（个股层检出力很低，读作「检出不了」）" if res["stock"]["full"] else "没有判定（M1 不是新证据）→ 模拟盘不变")) + "。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "state_model_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
