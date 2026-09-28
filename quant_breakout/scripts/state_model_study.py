"""state_model_study.py — 三态驱动 × 产业链（产出方 / 直接 / 间接）的行业模型 → 结合现行选股（突破 + W2）看胜率与每笔收益能不能提高
（2026-09-28 草稿（未登记、未运行）：对抗审计后修正、提交登记，之后才运行；结果出来不改规则）。

用户（2026-09-28）：「研究要考虑到类似原材料上涨/下跌/不变 原油上涨/下跌/不变 销售的什么什么等等的横展开 对以后行业的间接影响 /
  依据这些做个模型来结合当前的选股票算法来看能不能提高成功率和收益率」。
来由与已经看过的（照实写；研究总图 var/out/research_map.md）：
  - transmit_study：间接成本压力 −IND → 之后 3 个月 IC −0.028（t −1.55，方向与事先相反）；个股 T4 / T5 不成立。
  - cost_sales_study：行业层 S2「销售好时偏间接」成立（+1.23% / 3 个月，t 2.65）、S1 无效；个股 S4 / S5 不成立 → S2 只做日报显示与前向记录。
  - fund_study（短観 业况 / 需给 / 价格转嫁）都不通过，X2（顾客业况）在前向记录；supply_chain_study 一阶成本 IC +0.012 无效；
    theme_study：能源价格 → 機械 / 精密 / 半导体相关变差、卸売業变好（0〜3 个月内）。
  → 以前都是「一个信号、事先定方向」。这一轮新的是：① 每个驱动分「涨 / 跌 / 不变」三态（涨与跌的影响可以不对称）；
    ② 原油、3 种原材料、汇率、销售（自己与顾客）同时放进一个模型，每个驱动经三种渠道（产出方 / 直接使用方 / 经过供应链的间接使用方）；
    ③ 方向不事先定，由模型只用当时以前的数据学（walk-forward），只用样本外的预测检验。
  与以前的研究是同一段行情（2005-10〜2026-08）→ 行业层只算「样本外的再检验」，不是独立样本；个股层的 E' / J 窗口以前也用过（多重比较）
  → 门槛不放宽，另加三种随机对照。
一 数据（月末 t 已知的才用）
  驱动（5 个宏观 + 2 个销售；3 个月的对数变化 %）：
    OIL 原油（日元计）= WTI 现货（FRED DCOILWTICO）× 美元日元（FRED DEXJPUS）的月平均（同一天两边都有才算）；
    STEEL 鉄鋼 / NONFER 非鉄金属 / FOOD 食料用农水产物 = 日银企业物价（transmit_study 的 S / N / F，发布滞后 → t 月末只用到 t−1 月）；
    FX 汇率 = 美元日元的月平均（上升 = 日元贬值）；
    SALES 行业自己的销售 = 短観 大企業 売上高计划强度（qbreak/tankan.sales_strength，cost_sales_study 同一定义与可用日）；
    CUS 顾客的销售 = 产业连关表的销售份额（var/io_links_2020.json 的 cus）加权的顾客 SALES 三态（有值的顾客重新归一）。
  三态：OIL / STEEL / NONFER / FOOD / FX 的 3 个月变化，与自己 t 以前（含 t）的全部历史的 1/3、2/3 分位比（至少 60 个月）→ 涨 / 不变 / 跌；
    SALES ≥ +0.43 → 强、≤ −0.43 → 弱、其余与缺值 → 普通（0.43 = 标准正态的三分点；SALES 已按自己历年同一次调查标准化）；
    CUS：顾客三态（+1 / 0 / −1）的加权平均 > 1/3 → 强、< −1/3 → 弱、其余与缺值 → 普通。
  暴露（事先由 2020 年产业连关表定，不看收益；東証业种按对应部门的国内生产额加权）：
    OIL 与 3 种原材料：直接 D、间接 I = var/io_indirect_2020.json（transmit_study 完全相同；OIL 用能源 E 的份额）；
      产出方 OWN（收入随价格走，= 1）：能源 → 鉱業、石油・石炭製品、卸売業（総合商社的资源权益：先验，与 theme_study 已见的一致，不算新证据）；
      鉄鋼 → 鉄鋼、卸売業；非鉄 → 非鉄金属、卸売業；食料 → 水産・農林業。
    FX：直接 EXd = 输出 ÷ 国内生产额；间接 EXi =（输出诱发生产额 − 自己的输出）÷ 国内生产额 = 经过中间需求被别人的输出带动的部分
      （含同一业种里的零部件，例 自動車部品 → 乗用車 → 输出；108 部门，输入内生化的逆矩阵 (I − (I − M̂)A)^−1，M̂ = 输入计 ÷ 国内需要合计；
      总务省「输出诱发」同一算法；只存导出的份额 → var/io_export_2020.json）。
  行业收益：TOPIX 1000 的 927 只按東証业种的月度相对收益（transmit_study 同一口径，2005-10〜2026-08）；30 个业种都进横截面
    （收入受益的业种靠 OWN 区分；銀行・証券・保険 没有短観销售 → SALES 普通）。
二 模型（行业层；每个月末 t 预测之后 3 个月的相对收益）
  特征（业种 j、月末 t；不变 / 普通 = 基准）：OIL、STEEL、NONFER、FOOD 各 6 个 = {涨, 跌} × {D, I, OWN}；FX 4 个 = {涨, 跌} × {EXd, EXi}；
    SALES 2 个（强、弱）；CUS 2 个（强、弱）→ 共 32 个。每个特征与目标都在同一个月的横截面去均值（只学业种之间的差别）。
  估计：合并面板的岭回归，惩罚 = λ × 各特征在训练集的方差（= 特征标准化后的普通岭回归），λ = 0.1 × 训练样本数（事先写死；另报 ×0.1 / ×10）。
  Walk-forward：每个月末 t 重新估计；训练集 = 信号月 s ≤ t − 3（之后 3 个月的收益在 t 时已全知道）；有目标的训练月不到 60 个 → 不预测
    → 第一个样本外月约 2010-12（运行时核对）。样本外分数 ŷ(j, t)。
三 检验（行业层，样本外；信号月 = 第一个样本外月〜2026-05；两段 = 〜2016-12 / 2017-01〜）
  M1（主）：每月 ŷ 与之后 3 个月实际相对收益的横截面秩相关 IC → 平均、Newey–West t（4 阶）。
    有效 = 平均 IC > 0 且 t ≥ 2.0、两段都 > 0、三分组（最好 1/3 − 最差 1/3，每 3 个月不重叠取样，3 种起点的中位）命中率 ≥ 55%、
    且两种随机对照的经验 p（单侧）都 < 0.05：
      ① 时间错开：5 个宏观三态、SALES 与 CUS 三态一起在 2005-10〜2026-08 里循环错开 s 个月（s = 24〜(月数 − 24) 的每一种），整个 walk-forward 重跑；
      ② 产业链打乱：30 个业种的暴露（D / I / OWN / EXd / EXi）与 CUS 按固定的 40 种随机置换重新分给业种（SALES 不动），整个 walk-forward 重跑。
    读法：全部满足 →「三态 × 产业链模型有预测力」；只差 ② →「有预测力，但来自行业自己的销售等，产业链结构没有增量」；其余 → 无效。
  另报（不进判定）：去掉销售（只有价格 / 汇率）、只有直接渠道（去掉 I / EXi / CUS）、连续版（三态换成 3 个月变化的 z 值）、λ ×0.1 / ×10、
    h = 1 / 6 个月、行业动量（过去 3 个月相对收益）的 IC 与「模型 − 动量」的配对差；最新的系数（每个特征 1 个标准差 ≈ 3 个月相对收益 %）、
    现在的三态与各业种分数（只描述）。
四 检验（个股层：日経225 的突破，现行 = S0C2 + W2；scripts/leap_confirm.py 同一框架）
  窗口：E' = 2011-01-04〜2016-09-30（yfinance、今天的日経225、去掉成交量 0 与休市日的行；组合从 2011-01-04 起算）、J = 2017-01-04〜最新（J-Quants）。
    Z 窗口没有样本外的模型（行业收益 2005-10 才有）→ 不做。信号日用上个月末的分数（与以前相同）。
  M2（避开看淡的行业）：分数在当月横截面最低 1/3 → 不做；其余照做（不在横截面的业种、没有分数的月份照做）。
  M3（只做看好的行业）：分数在最高 1/2 → 做；其余不做（例外同上）。
  判定 =「选股改进」两个窗口都满足（scripts/leap2_common 的门槛：胜率 ≥ 现行 + 4 pp、每笔 ≥ + 0.5 pp、笔数 ≥ 现行的 30%、
    Calmar ≥ 现行 − 0.02 且回撤不深 2 pp 以上），且两个窗口的胜率与每笔都 > 三种随机对照的 95% 分位：
    ① 现行的信号按「股票 × 周」随机保留同样比例（30 次）；② 分数面板在样本外区间里循环错开 24 + 13i 个月（i = 0〜10，整月 × 整个业种）；
    ③ 分数面板的业种标签随机置换（20 种）。另报：去掉最好一年的每笔；同一天名额不够（被挤掉）的信号数。
五 结论上限：M1 有效 → 提议日报加「三态行业模型」显示与前向记录（用户确认）；M2 / M3 过 → 提议前向记录（用户确认；模拟盘不改）；都不成立 → 维持现行。
六 事前预期（写死）：M1 有效约 10%；M2 / M3 各约 5%；全部不成立约 80%。检出力：30 个业种、约 185 个月重叠的 3 个月 IC，标准误约 0.02〜0.03
  → IC 要约 0.05 以上才过 t 2.0；以前单个信号的 IC 都在 ±0.03 以内。个股层现行的 E' 约 60〜80 笔、J 约 100 笔 → 胜率 +4 pp 很难。
七 局限：同一段行情以前用过；2020 年的产业结构套到 2005〜2026；WTI 与汇率用 FRED 的月平均（DEXJPUS 每周公布，实时使用时月末最后几天可能还没有）；
  企业物价是今天的链接值；短観是大企業；业种与成员是今天的（幸存者偏差）；λ 没有调（事先写死）；卸売業 的 OWN 是先验；
  E' 与 J 都是今天的日経225；输入内生化只用于汇率（原材料的直接 / 间接沿用 transmit_study 的算法，保持可比）。
八 登记前核对（2026-09-28 `--check`：只看结构、覆盖、三态的频率与特征的相关，没算任何收益；数据指纹 4750f1092147）
  业种 30 个；月份 2005-10〜2026-08（251 个）；3 个月变化起点 OIL / FX 1986-04、STEEL / NONFER / FOOD 1990-05（三态要 60 个月的历史）。
  三态频率（2005-10〜，涨 / 不变 / 跌 %）：OIL 36 / 32 / 32；STEEL 42 / 25 / 32；NONFER 49 / 24 / 28；FOOD 38 / 37 / 25；FX 37 / 39 / 25
    （分位用 1986 / 1990 年起的全部历史 → 2005 年以后不一定各占 1/3）。两两同时「涨」16〜28%。
  SALES 有值的业种 26 / 30（銀行・証券・保険・その他金融以外；缺值 14%）：强 / 普通 / 弱 33 / 26 / 27%；CUS 30 个业种都有：39 / 38 / 22%。
  汇率 直接最高：海運業 64.6%、電気機器 38.1%、精密機器 37.2%、機械 34.0%、非鉄金属 33.1%、輸送用機器 30.8%；
    间接最高：鉱業 47.3%、鉄鋼 37.7%、非鉄金属 28.5%、化学 22.9%、海運業 22.0%、輸送用機器 21.6%。
  特征 32 个，没有全为 0 的；两两相关最高 FOOD_dn_D × FOOD_dn_I 0.97（食料的直接 / 间接都集中在食料品），|相关| > 0.8 的 2 对（岭回归处理）。
  有目标的训练月 248 个；第一个样本外月 2010-12-31；样本外信号月到 2026-05 共 186 个。
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

START, END = "2005-10-31", TS.END
MACRO = ["OIL", "STEEL", "NONFER", "FOOD", "FX"]
IO_KEY = {"OIL": "E", "STEEL": "S", "NONFER": "N", "FOOD": "F"}
OWN = {"OIL": ["鉱業", "石油・石炭製品", "卸売業"], "STEEL": ["鉄鋼", "卸売業"], "NONFER": ["非鉄金属", "卸売業"], "FOOD": ["水産・農林業"]}
SALES_CUT, CUS_CUT = 0.43, 1 / 3
MIN_HIST, MIN_TRAIN, H, LAM, LAGS = 60, 60, 3, 0.1, 4
T_MIN, HIT_MIN, P_MAX, N_PERM, N_PERM_STOCK, GAP = 2.0, 55.0, 0.05, 40, 20, 24
SPLIT = "2016-12-31"
SHIFT_STOCK = [24 + 13 * i for i in range(11)]
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
    """部门的（直接 = 输出 ÷ 生产额，间接 = 输出诱发生产额里经过其他部门的部分 ÷ 生产额）；输入内生化：B = (I − M̂)A，L = (I − B)^−1。"""
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
    if not xl.exists():
        TS.load_exposures(industries, refresh=True)                           # 顺便把原表下载到 var/cache/io/
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
def monthly_mean(s: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    s = s.dropna()
    m = s.groupby(s.index.to_period("M")).mean()
    m.index = m.index.to_timestamp("M")
    return m.reindex(months)


def log_change(m: pd.Series, w: int = 3) -> pd.Series:
    lv = np.log(m.where(m > 0)) * 100
    return lv - lv.shift(w)


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


def macro_states(ch: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({k: tercile_state(ch[k]) for k in ch.columns}, index=ch.index)


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
def exposure_arrays(ex: dict, exp: dict, industries: list[str], perm: np.ndarray | None = None) -> dict:
    """{("D"|"I"|"OWN", 驱动): 业种向量, ("EXd"|"EXi", "FX"): 向量}；perm：业种 j 拿第 perm[j] 个业种的暴露（产业链打乱的对照）。"""
    J = len(industries)
    idx = np.arange(J) if perm is None else np.asarray(perm)
    src = [industries[i] for i in idx]
    out = {}
    for d, k in IO_KEY.items():
        out[("D", d)] = np.array([ex["direct"][k].get(j, 0.0) for j in src], float)
        out[("I", d)] = np.array([ex["indirect"][k].get(j, 0.0) for j in src], float)
        out[("OWN", d)] = np.array([1.0 if j in OWN[d] else 0.0 for j in src], float)
    out[("EXd", "FX")] = np.array([exp["direct"].get(j, 0.0) for j in src], float)
    out[("EXi", "FX")] = np.array([exp["indirect"].get(j, 0.0) for j in src], float)
    return out


def feature_names(drop: tuple[str, ...] = ()) -> list[str]:
    names = []
    for d in IO_KEY:
        for ch in ("D", "I", "OWN"):
            for s in ("up", "dn"):
                names.append(f"{d}_{s}_{ch}")
    for ch in ("EXd", "EXi"):
        for s in ("up", "dn"):
            names.append(f"FX_{s}_{ch}")
    names += ["SALES_up", "SALES_dn", "CUS_up", "CUS_dn"]
    return [n for n in names if not any(tok in n.split("_") for tok in drop) and n.split("_")[0] not in drop]


def features(ms: pd.DataFrame, ss: pd.DataFrame, cs: pd.DataFrame, expo: dict, names: list[str], continuous: pd.DataFrame | None = None) -> np.ndarray:
    """[月, 业种, 特征]，每个月横截面去均值；宏观三态有缺值的月 → 整月缺值。continuous：给了就用它（z 值）代替 涨 / 跌 的指示（另报的连续版）。"""
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
        ch = parts[2]
        e = expo[(ch, d)]
        if continuous is not None:
            g = continuous[d].to_numpy(float) * (1.0 if s == "up" else 0.0)            # 连续版：只用 up 那一列放 z 值，dn 那一列 = 0
        else:
            st = ms[d].to_numpy(float)
            g = (st == (1.0 if s == "up" else -1.0)).astype(float)
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
def ic_eval(pred: pd.DataFrame, Y: pd.DataFrame, placebo_t: list[float] | None = None) -> dict:
    ic = SC.fm_ic(pred, Y, LAGS)
    st = SC.ic_stats(ic, LAGS)
    h1 = SC.ic_stats(ic[ic.index <= pd.Timestamp(SPLIT)], LAGS)["ic"]
    h2 = SC.ic_stats(ic[ic.index > pd.Timestamp(SPLIT)], LAGS)["ic"]
    hits, spreads = [], []
    for ph in range(3):
        tc = SC.tercile(pred.iloc[ph:], Y, 1, 3)
        if tc["hit"] is not None:
            hits.append(tc["hit"])
            spreads.append(tc["spread"])
    out = {"ic": st["ic"], "t": st["t"], "n": st["n"], "H1": h1, "H2": h2, "hits": hits, "hit": float(np.median(hits)) if hits else None,
           "spread": float(np.median(spreads)) if spreads else None, "_ic": ic}
    if placebo_t is not None:
        a = np.array([np.nan if v is None else v for v in placebo_t], float)
        out.update({"placebo_n": int(np.isfinite(a).sum()), "placebo_t95": round(float(np.nanpercentile(a, 95)), 2) if np.isfinite(a).any() else None,
                    "placebo_p": SC.placebo_p(st["t"] if st["t"] is not None else np.nan, a)})
    return out


def m1_fails(r: dict, p_shift: float | None, p_perm: float | None) -> list[str]:
    f = []
    if not (r["ic"] is not None and r["ic"] > 0 and r["t"] is not None and r["t"] >= T_MIN):
        f.append(f"IC {r['ic']}（t {r['t']}）不够")
    if not (r["H1"] is not None and r["H1"] > 0 and r["H2"] is not None and r["H2"] > 0):
        f.append(f"两段 {r['H1']} / {r['H2']} 不都 > 0")
    if not (r["hit"] is not None and r["hit"] >= HIT_MIN):
        f.append(f"命中率 {r['hit']}% < {HIT_MIN}%")
    if not (p_shift is not None and p_shift < P_MAX):
        f.append(f"时间错开对照 p {p_shift}")
    if not (p_perm is not None and p_perm < P_MAX):
        f.append(f"产业链打乱对照 p {p_perm}")
    return f


def m1_verdict(fails: list[str]) -> str:
    if not fails:
        return "三态 × 产业链模型有预测力"
    if len(fails) == 1 and fails[0].startswith("产业链打乱"):
        return "有预测力，但来自行业自己的销售等，产业链结构没有增量"
    return "无效"


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


def eprime_context():
    import leap_confirm as LF
    ctx = LF.context("E")
    ctx = dict(ctx)
    ctx["windows"], ctx["start"], ctx["end"] = dict(EP_WINDOWS), EP_WINDOWS["E"][0], EP_WINDOWS["E"][1]
    return ctx


def stock_windows(s33: dict, score: pd.DataFrame) -> dict:
    import leap2_common as L2
    import leap_confirm as LF
    import pit_recheck as PR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    have = score.dropna(how="all")
    a0, b0 = have.index[0], have.index[-1]
    res = {}
    for era in ("E", "J"):
        t0 = time.time()
        ctx = eprime_context() if era == "E" else LF.context("J")
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        a, b = ctx["windows"][era]
        r = {"现行": LF.run(ctx, run_fn, fw, p)}
        full = {"现行": dict(__import__("jq_study").RealLotEngine.LAST[-1].skipped) if __import__("jq_study").RealLotEngine.LAST else {}}
        exb = {"现行": PR.ex_best_year(PR.last_trades(), a, b)}
        pq, ps, pp, frac, sfrac = {}, {}, {}, {}, {}
        for cid in ("M2", "M3"):
            keep = stock_keep(fw, s33, score, cid)
            frac[cid] = LF.keep_frac(fw, keep)
            r[cid] = LF.run(ctx, run_fn, LF.with_mask(fw, keep), p)
            exb[cid] = PR.ex_best_year(PR.last_trades(), a, b)
            q = LF.placebo_trades(ctx, run_fn, fw, p, frac[cid], seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            pq[cid] = {"win": q["win"], "mean": q["mean"]}
            for tag, sink, variants in (("shift", ps, [roll_window(score, s, a0, b0) for s in SHIFT_STOCK]),
                                        ("perm", pp, [pd.DataFrame(score.to_numpy()[:, pm], index=score.index, columns=score.columns)
                                                      for pm in perms(score.shape[1], N_PERM_STOCK, 1000)])):
                vals, fl = {"win": [], "mean": []}, []
                for sc in variants:
                    kk = stock_keep(fw, s33, sc, cid)
                    fl.append(LF.keep_frac(fw, kk))
                    rs = LF.run(ctx, run_fn, LF.with_mask(fw, kk), p)[era]
                    for k in vals:
                        if rs.get(k) is not None:
                            vals[k].append(rs[k])
                sink[cid] = {k: (float(np.percentile(v, L2.PLACEBO_Q)) if v else float("nan")) for k, v in vals.items()}
                sfrac[f"{cid}_{tag}"] = {"min": round(float(min(fl)), 3), "mean": round(float(np.mean(fl)), 3), "max": round(float(max(fl)), 3)}
        res[era] = {"res": r, "pq": pq, "ps": ps, "pp": pp, "frac": frac, "shift_frac": sfrac, "ex_best": exb, "skipped": full,
                    "secs": round(time.time() - t0)}
    return res


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> str:
    root = str(paths.PROJECT_ROOT)
    try:
        rev = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", "scripts", "qbreak", "var/io_indirect_2020.json",
                                     "var/io_export_2020.json", "var/io_links_2020.json", "var/industry_s33.json"],
                                    capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return rev + ("（脏）" if dirty else "")


def data_hash(*frames) -> str:
    h = hashlib.sha256()
    for f in frames:
        if isinstance(f, (pd.DataFrame, pd.Series)):
            h.update(pd.util.hash_pandas_object(f.round(6), index=True).values.tobytes())
        else:
            h.update(json.dumps(f, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:12]


def build(inds: list[str], months: pd.DatetimeIndex) -> dict:
    """驱动三态、销售三态、暴露（不看收益）。"""
    long = pd.date_range("1986-01-31", END, freq="ME")
    ch = macro_changes(long)
    ms = macro_states(ch).reindex(months)
    chz = ((ch - ch.expanding(MIN_HIST).mean()) / ch.expanding(MIN_HIST).std()).reindex(months)      # 连续版（另报）：只用到 t 为止
    S = TK.load_sales()
    need = {c for g in inds for c in TK.TSE.get(g, [])} | set(TK.SALES_OLD.values())
    bad = [c for c in TK.MISSING if "102CFY" in c and c[5:9] in need]
    if bad:
        raise SystemExit(f"短観売上高 取不到：{bad}（不跑，防止横截面悄悄变小）")
    sz = TK.to_tse(TK.sales_strength(S, months), inds).reindex(columns=inds)
    ss = sales_states(sz)
    links = json.loads((paths.home() / "io_links_2020.json").read_text(encoding="utf-8"))
    cs = cus_states(ss, links["cus"], inds)
    ex = TS.load_exposures(inds)
    exp = load_export(inds)
    return {"ch": ch, "ms": ms, "chz": chz, "sz": sz, "ss": ss, "cs": cs, "ex": ex, "exp": exp}


def run_model(D: dict, inds: list[str], Yd: np.ndarray, perm=None, ms=None, ss=None, cs=None, drop=(), lam=LAM, h=H, continuous=False):
    names = feature_names(drop)
    expo = exposure_arrays(D["ex"], D["exp"], inds, perm)
    cs_ = D["cs"] if cs is None else cs
    if perm is not None:
        cs_ = pd.DataFrame(cs_.to_numpy()[:, perm], index=cs_.index, columns=cs_.columns)
    F = features(D["ms"] if ms is None else ms, D["ss"] if ss is None else ss, cs_, expo, names, D["chz"] if continuous else None)
    return walk_forward(F, Yd, h=h, lam=lam), names, F


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报结构、覆盖、三态频率与特征相关（不看任何收益）")
    ap.add_argument("--skip-stock", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    Mret, s33 = TS.load_industry_returns()
    inds = list(Mret.columns)
    months = pd.date_range(START, END, freq="ME")
    D = build(inds, months)
    dh = data_hash(D["ms"], D["ss"].fillna(9), D["cs"].fillna(9), D["ex"], D["exp"])
    if a.check:
        ms = D["ms"]
        print(f"业种 {len(inds)} 个；月份 {months[0].date()}〜{months[-1].date()}（{len(months)} 个）；数据指纹 {dh}")
        print("宏观驱动的 3 个月变化起点：" + "、".join(f"{k} {D['ch'][k].first_valid_index().date()}" for k in MACRO))
        print("三态频率（2005-10〜，涨 / 不变 / 跌 %）：" + "；".join(
            f"{k} {(ms[k] == 1).mean() * 100:.0f} / {(ms[k] == 0).mean() * 100:.0f} / {(ms[k] == -1).mean() * 100:.0f}" for k in MACRO))
        print("三态两两同时为「涨」的比例 %：" + "、".join(f"{x}&{y} {((ms[x] == 1) & (ms[y] == 1)).mean() * 100:.0f}"
                                               for i, x in enumerate(MACRO) for y in MACRO[i + 1:]))
        ss, cs = D["ss"], D["cs"]
        print(f"SALES 有值的业种 {int(ss.notna().any().sum())} / {len(inds)}；强 / 普通 / 弱 / 缺 %："
              f"{(ss == 1).mean().mean() * 100:.0f} / {(ss == 0).mean().mean() * 100:.0f} / {(ss == -1).mean().mean() * 100:.0f} / {ss.isna().mean().mean() * 100:.0f}")
        print(f"CUS 有值的业种 {int(cs.notna().any().sum())}；强 / 普通 / 弱 / 缺 %："
              f"{(cs == 1).mean().mean() * 100:.0f} / {(cs == 0).mean().mean() * 100:.0f} / {(cs == -1).mean().mean() * 100:.0f} / {cs.isna().mean().mean() * 100:.0f}")
        ed, ei = pd.Series(D["exp"]["direct"]).sort_values(ascending=False), pd.Series(D["exp"]["indirect"]).sort_values(ascending=False)
        print("汇率 直接（输出 ÷ 生产额）最高：" + "、".join(f"{j} {v * 100:.1f}%" for j, v in ed.head(6).items()))
        print("汇率 间接（经过其他部门）最高：" + "、".join(f"{j} {v * 100:.1f}%" for j, v in ei.head(6).items()))
        print("OWN：" + "；".join(f"{d} {'・'.join(v)}" for d, v in OWN.items()))
        names = feature_names()
        F = features(D["ms"], D["ss"], D["cs"], exposure_arrays(D["ex"], D["exp"], inds), names)
        X = F.reshape(-1, len(names))
        X = X[np.isfinite(X).all(axis=1)]
        sd = X.std(axis=0)
        zero = [n for n, v in zip(names, sd) if v < 1e-12]
        C = np.corrcoef(X[:, sd > 1e-12].T)
        np.fill_diagonal(C, 0)
        nz = [n for n, v in zip(names, sd) if v >= 1e-12]
        k = np.unravel_index(np.nanargmax(np.abs(C)), C.shape)
        print(f"特征 {len(names)} 个；全为 0 的 {zero}；两两相关最高 {nz[k[0]]} × {nz[k[1]]} {C[k]:.2f}；|相关| > 0.8 的对数 {int((np.abs(C) > 0.8).sum() // 2)}")
        yfin = np.isfinite(SC.ahead(Mret, H).reindex(index=months, columns=inds).to_numpy(float)).sum(axis=1) >= 10
        cm = np.cumsum(yfin)
        first = next((months[i] for i in range(H, len(months)) if cm[i - H] >= MIN_TRAIN), None)
        print(f"有目标的训练月：{int(yfin.sum())} 个；第一个样本外月 {first.date() if first is not None else '—'}；"
              f"样本外信号月到 2026-05 共 {int(((months >= first) & (months <= pd.Timestamp('2026-05-31'))).sum()) if first is not None else 0} 个")
        return 0
    say(f"# 三态驱动 × 产业链的行业模型 → 结合现行选股（{pd.Timestamp.today().date()}；git {git_info()}；数据指纹 {dh}）")
    say("规则见 scripts/state_model_study.py 开头（先提交后运行）。IC = 模型分数与之后 3 个月行业相对收益的横截面秩相关。")
    Yraw = SC.ahead(Mret, H).reindex(index=months, columns=inds)
    Yd = demean(Yraw.to_numpy(float))
    pred, names, F = run_model(D, inds, Yd)
    P = pd.DataFrame(pred, index=months, columns=inds)
    ev = P.index[P.notna().any(axis=1) & (P.index <= pd.Timestamp("2026-05-31"))]
    first = ev[0]
    Pe, Ye = P.reindex(ev), Yraw.reindex(ev)
    # ① 时间错开
    a0, b0 = months[0], months[-1]
    n_m = len(months)
    tsh = []
    for s in range(GAP, n_m - GAP + 1):
        pr, _, _ = run_model(D, inds, Yd, ms=roll_window(D["ms"], s, a0, b0), ss=roll_window(D["ss"], s, a0, b0), cs=roll_window(D["cs"], s, a0, b0))
        tsh.append(SC.ic_stats(SC.fm_ic(pd.DataFrame(pr, index=months, columns=inds).reindex(ev), Ye, LAGS), LAGS)["t"])
    # ② 产业链打乱
    tpm = []
    for pm in perms(len(inds), N_PERM):
        pr, _, _ = run_model(D, inds, Yd, perm=pm)
        tpm.append(SC.ic_stats(SC.fm_ic(pd.DataFrame(pr, index=months, columns=inds).reindex(ev), Ye, LAGS), LAGS)["t"])
    r1 = ic_eval(Pe, Ye)
    ps, pm_ = ic_eval(Pe, Ye, tsh), ic_eval(Pe, Ye, tpm)
    f1 = m1_fails(r1, ps["placebo_p"], pm_["placebo_p"])
    v1 = m1_verdict(f1)
    res = {"git": git_info(), "data_hash": dh, "industries": inds, "first_oos": str(first.date()), "oos_months": int(len(ev)),
           "M1": {**{k: v for k, v in r1.items() if k != "_ic"}, "placebo_shift": {k: ps[k] for k in ("placebo_n", "placebo_t95", "placebo_p")},
                  "placebo_perm": {k: pm_[k] for k in ("placebo_n", "placebo_t95", "placebo_p")}, "fails": f1, "verdict": v1}}
    fmt = lambda r: (f"IC {r['ic']:+.4f}（t {r['t']}，{r['n']} 个月）；两段 {r['H1']} / {r['H2']}；三分组 最好 − 最差 {r['spread']}%，"      # noqa: E731
                     f"命中率 {r['hit']}%（3 种起点 {r['hits']}）")
    say(f"\n## M1（主）行业层：样本外 {first.date()}〜2026-05（{len(ev)} 个月）")
    say(f"- 模型：{fmt(r1)}")
    say(f"- 对照 ① 时间错开（{ps['placebo_n']} 种）：t 的 95% 分位 {ps['placebo_t95']}、经验 p {ps['placebo_p']}；"
        f"② 产业链打乱（{pm_['placebo_n']} 种）：95% 分位 {pm_['placebo_t95']}、经验 p {pm_['placebo_p']}")
    say(f"- 判定：{'有效' if not f1 else '不满足：' + '；'.join(f1)} → **{v1}**")
    # 另报
    side = {}
    for key, kw in (("无销售", {"drop": ("SALES", "CUS")}), ("只有直接", {"drop": ("I", "EXi", "CUS")}), ("连续版", {"continuous": True}),
                    ("λ×0.1", {"lam": LAM * 0.1}), ("λ×10", {"lam": LAM * 10})):
        pr, _, _ = run_model(D, inds, Yd, **kw)
        side[key] = ic_eval(pd.DataFrame(pr, index=months, columns=inds).reindex(ev), Ye)
    for hh in (1, 6):
        Yh = SC.ahead(Mret, hh).reindex(index=months, columns=inds)
        pr, _, _ = run_model(D, inds, demean(Yh.to_numpy(float)), h=hh)
        side[f"h={hh}"] = ic_eval(pd.DataFrame(pr, index=months, columns=inds).reindex(ev), Yh.reindex(ev))
    mom = SC.past(Mret, 3).reindex(index=months, columns=inds).reindex(ev)
    side["行业动量"] = ic_eval(mom, Ye)
    d_ic = (r1["_ic"] - side["行业动量"]["_ic"]).dropna()
    pair = SC.ic_stats(d_ic, LAGS)
    say("\n## 另报（不进判定）")
    for k, r in side.items():
        say(f"- {k}：{fmt(r)}")
    say(f"- 模型 − 行业动量 的 IC 配对差：{pair['ic']}（t {pair['t']}）")
    _, B = walk_forward(F, Yd, coefs=True)
    last = int(np.where(np.isfinite(B).all(axis=1))[0][-1])
    Xs = F.reshape(-1, len(names))
    sd = np.nanstd(Xs[np.isfinite(Xs).all(axis=1)], axis=0)
    co = pd.Series(B[last] * sd, index=names).round(3)
    say(f"- 最新模型（{months[last].date()} 末估计）每个特征 1 个标准差 ≈ 之后 3 个月相对收益 %：绝对值最大的 8 个 "
        + "、".join(f"{k} {v:+.2f}" for k, v in co.reindex(co.abs().sort_values(ascending=False).index).head(8).items()))
    now = D["ms"].iloc[-1]
    say(f"- 现在（{months[-1].date()} 末）的三态：" + "、".join(f"{k} {'涨' if v == 1 else '跌' if v == -1 else '不变' if v == 0 else '—'}" for k, v in now.items()))
    sc_now = P.iloc[-1].dropna().sort_values(ascending=False)
    if len(sc_now):
        say(f"- 现在的分数（只描述）：最高 {'、'.join(sc_now.index[:5])}；最低 {'、'.join(sc_now.index[-5:])}")
    res.update({"side": {k: {kk: vv for kk, vv in v.items() if kk != "_ic"} for k, v in side.items()}, "vs_momentum": pair,
                "coef_latest": co.to_dict(), "coef_month": str(months[last].date()), "states_now": now.to_dict(),
                "score_now": {k: round(float(v), 4) for k, v in sc_now.items()}})
    write_out(res)
    if not a.skip_stock:
        W = stock_windows(s33, P)
        say("\n## M2 / M3（个股：日経225 的突破，现行 = S0C2 + W2；E' = 2011-01〜2016-09 yfinance，J = 2017〜 J-Quants）")
        say("| 窗口 | 方案 | 组合 年化 / 回撤 / Calmar · 个股笔数 每笔 / 胜率 | 保留 | 对照 95% 分位：股票 × 周 | 时间错开 | 业种打乱 | 去掉最好一年 |")
        say("|---|---|---|---|---|---|---|---|")
        qf = lambda q: f"{q['win']:.1f}% / {q['mean']:+.2f}%" if q else "—"                       # noqa: E731
        for era in ("E", "J"):
            for k, r in W[era]["res"].items():
                s = r[era]
                xb = W[era]["ex_best"].get(k)
                say(f"| {era}{'′' if era == 'E' else ''} | {k} | {s.get('cagr')}% / {s.get('dd')}% / {s.get('calmar')} · {s.get('n')} 笔 {s.get('mean')}% / {s.get('win')}% | "
                    f"{W[era]['frac'].get(k, 1) * 100:.0f}% | {qf(W[era]['pq'].get(k))} | {qf(W[era]['ps'].get(k))} | {qf(W[era]['pp'].get(k))} | "
                    + (f"去 {xb['best_year']}：{xb['n']} 笔 {xb['mean']:+.2f}% / {xb['win']:.0f}%" if xb and xb.get("n") else "—") + " |")
        say("- 现行被名额挤掉的信号（skipped）：" + "；".join(f"{e}′ {W[e]['skipped'].get('现行')}" if e == "E" else f"{e} {W[e]['skipped'].get('现行')}" for e in ("E", "J")))
        base = {e: W[e]["res"]["现行"][e] for e in ("E", "J")}
        import leap2_common as L2
        for cid in ("M2", "M3"):
            cand = {e: W[e]["res"][cid][e] for e in ("E", "J")}
            fi = improve2(cand, base)
            fp = []
            for e in ("E", "J"):
                for nm, q in (("股票 × 周", W[e]["pq"][cid]), ("时间错开", W[e]["ps"][cid]), ("业种打乱", W[e]["pp"][cid])):
                    if not (L2.is_finite(cand[e].get("win")) and cand[e]["win"] > q["win"] and L2.is_finite(cand[e].get("mean")) and cand[e]["mean"] > q["mean"]):
                        fp.append(f"{e} {nm}对照没过")
            res[cid] = {"improve_fails": fi, "placebo_fails": fp, "frac": {e: W[e]["frac"][cid] for e in W},
                        "windows": {e: {k: {w: v for w, v in r.items() if not str(w).startswith("_")} for k, r in W[e]["res"].items()} for e in W},
                        "placebo": {e: {"lottery": W[e]["pq"][cid], "shift": W[e]["ps"][cid], "perm": W[e]["pp"][cid]} for e in W},
                        "shift_frac": {e: W[e]["shift_frac"] for e in W}, "ex_best": {e: W[e]["ex_best"] for e in W}}
            say(f"- {cid}：{'选股改进成立' if not (fi or fp) else '不成立：' + '；'.join(fi + fp)}")
        res["skipped"] = {e: W[e]["skipped"] for e in W}
    say("\n## 结论（事先规则）")
    say(f"- 行业层：{v1}" + ("→ 提议日报加「三态行业模型」显示与前向记录（用户确认）" if not f1 else "") + "。")
    if not a.skip_stock:
        ok = [k for k in ("M2", "M3") if not (res[k]["improve_fails"] or res[k]["placebo_fails"])]
        say(f"- 个股层：{('、'.join(ok) + ' 过 → 提议前向记录（用户确认）') if ok else 'M2 / M3 都不过 → 模拟盘不变'}。")
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
