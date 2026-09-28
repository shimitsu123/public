"""cost_sales_study.py — 成本 × 销售：原材料涨价时，销售特别好的行业能不能盖过成本；销售好的时候选间接影响的、不选直接冲击的
（2026-09-28 事先登记：先提交后运行，结果出来不改规则；对抗审计 1 次后修正）。

用户（2026-09-28）：「上面的研究不能只考虑成本的冲击 也要考虑到销售的部分 如果销售特别好 盖过了成本上升的因素没有考虑
  销售特别好的时候也不要选择直接冲击要选择间接的选择」。
来由与已经看过的（照实写；研究总图 var/out/research_map.md）：
  - transmit_study（登记 5e3c11a，结果 6b1b28a）只看成本：T1 −IND（间接成本压力）→ 之后 3 个月 IC −0.028（t −1.55），三分组 最好 − 最差 −1.02%
    （t −2.32）—— 方向与事先相反：间接成本压力大的业种之后反而略好；T2 的 IND 在公布后第 1 个月的系数 +0.150（每 1 个标准差 %）；
    T3 无效；个股 T4 / T5 不成立（T5 Z / E 胜率 +5.2 / +6.8 pp、J −2.3 pp）。事后猜「原材料涨 = 景气好」的需求面盖过了成本面 —— 就是用户这次的假设，
    但它是看过 T1 之后提出的 → 行业层这里用的是同一段数据（2006-10〜2026-08），只能算「加上销售、条件更细的再检验」，不是独立样本；
    新的部分是「销售」数据（短観 売上高計画，以前从没用过），所以每个检验都另要求「销售这一条件本身有增量」（见下）才算新证据。
  - fund_study（短観，2026-09-26）：业况变化 IC +0.036（t 1.53，最接近）、利润空间变化 −0.017、国内需给变化 +0.022 → 都不通过；
    X2（顾客业种的业况变化）在前向记录。
一 数据
  成本：2020 产业连关表 108 部门、4 种原材料行外生 → 直接 / 间接份额（var/io_indirect_2020.json，与 transmit_study 相同）；日银企业物价
    （发布滞后 1 个月）的 3 个月对数变化 dP_k。这里只算「上涨的部分」（审计：成本冲击 = 原材料涨价，跌的不抵消）：
    DIR3⁺_j = Σ_k 直接_kj × max(dP_k, 0)、IND3⁺_j = Σ_k 间接_kj × max(dP_k, 0)、COST3⁺ = DIR3⁺ + IND3⁺（占产出额 %）；
    「成本压力大」= COST3⁺ ≥ 0.1 且在横截面最高 1/3；「偏直接」= DIR3⁺ > IND3⁺；「间接占比」= IND3⁺ ÷ COST3⁺。
    「成本上升的月份」= 横截面 COST3（涨跌都算的净值，transmit_study 的 DIR + IND）平均 > 0。
  销售（新）：日银短観 大企業「売上高 前年比・年度」（BOJ 時系列 db=CO，TK99G{业种}102CFY{k}1000；1990 年度起；qbreak/tankan）。
    月末 t 用当时已公布的最新一次调查（有值的那一次）对「本年度」（4 月〜翌年 3 月）的计划：4〜6 月末 = 3 月调查、7〜9 月末 = 6 月调查、
    10〜11 月末 = 9 月调查、12〜3 月末 = 12 月调查（保守按 4/5、7/5、10/5、12/20 之后才用）。
    「销售特别好」按行业自己、同一次调查比（审计：计划普遍比实绩保守、各业种有惯常偏差 → 不能和实绩比）：
    SALES_j = (计划 − 之前 10 个年度同一次调查计划的中位) ÷ (1.4826 × MAD，MAD 至少 0.5 个百分点)，之前不到 5 个年度 → 缺值；再在横截面排名。
    短観业种 → 東証业种：qbreak/tankan.TSE（機械 / 精密機器 2009 年度以前用旧分类 一般機械 1140 / 精密機械 1200）。
  横截面：去掉 6 个收入受益业种、短観没有的業種（銀行・証券・保険），再去掉和别的业种共用短観业种或对应很差的 3 个（医薬品 = 化学 1060、
    ゴム製品 = その他製品 1500、海運業 ← 運輸・郵便）→ 18 个（登记名单见 CS，运行时核对）。
  行业收益：与 transmit_study 相同（TOPIX 1000 的 927 只按東証业种、月度相对收益，2005-10〜2026-08）。
二 检验（行业层；信号月 2006-10〜2026-08；两半 2006-10〜2016-08 / 2016-09〜）
  S1（主，「销售盖过成本」）：每个月末 t，「成本压力大」的业种按 SALES 的秩分成上半 / 下半（正好在中间的、并列跨过中线的不算）→
    之后 3 个月的相对收益 上半平均 − 下半平均（每月一个值；少于 4 个业种的月份不算）。
    对照组 S1c：成本压力不大（有 SALES）的业种里同样分 → 每月的配对差 S1 − S1c。
  S2（主，「销售好时选间接」）：成本上升的月份里，销售好 = SALES 在横截面前一半、且 COST3⁺ ≥ 0.1 的业种（「特别好」= 前 1/3 时每月只剩 3〜5 个，
    检出力不够 → 用前一半，另报前 1/3）；按「间接占比」分上半（偏间接）/ 下半（偏直接）→ 之后 3 个月 上半 − 下半。
    基准 S2b：同样的月份、COST3⁺ ≥ 0.1 的全部业种（不看销售）同样分 → 每月的配对差 S2 − S2b。
  有效（S1、S2 各自）= 月度差的平均 > 0 且 Newey–West t（4 阶）≥ 2.0、两半都 > 0、每 3 个月不重叠取样的命中率 ≥ 55%（3 种起点都报，
    判定用 3 种的中位）、去掉任何一个业种后平均都 > 0、时间错开对照（只把 SALES 面板循环错开 24〜(月数 − 24) 的每一种）的经验 p
    经 Holm（S1、S2 两个一起，5%）后仍过。事先方向：S1 > 0、S2 > 0。
  读法：S1 有效且配对差 S1 − S1c 的 NW t ≥ 1.645 →「销售能盖过成本压力」；S1 有效但配对差不够 →「销售好本身有预测力（不只是盖过成本）」；
    S2 有效且配对差 S2 − S2b 的 NW t ≥ 1.645 →「销售好时偏间接的更好（销售这一条件起作用）」；S2 有效但配对差不够 →
    「偏间接的本来就略好（与 T1 已见的一致，不算新证据）」。只有行业层有效才提议日报显示（用户确认）。
  另报（不进判定）：Fama–MacBeth 连续版（z(DIR3⁺)、z(IND3⁺)、z(SALES) 与两个交叉项）；SALES 换成价格转嫁（短観 販売価格 DI − 仕入価格 DI）
    或売上高修正率（qbreak/tankan.sales_revision）；S2 用 SALES 前 1/3。
三 检验（个股层：日経225 的突破，现行 = S0C2 + W2；Z / E / J，Z / E 去掉 Yahoo 休市假行；与 transmit_study T4 / T5 同一框架）
  S4（用户的规则）：上个月末所在业种「成本压力大」时：偏直接 → 不做；偏间接但 SALES 不在横截面前 1/3（「特别好」才能盖过成本）→ 不做；其余照做
    （不在横截面的业种、缺值照做）。
  S5（只看销售）：成本压力大且 SALES 不在前 1/3 → 不做；其余照做。
  判定 =「选股改进」（scripts/leap2_common.improve_fails：胜率 ≥ 现行 + 4 pp、每笔 ≥ + 0.5 pp、笔数 ≥ 30%、Calmar ≥ 现行 − 0.02 且回撤不深 2 pp 以上）
    且三个窗口的胜率与每笔都 > 三种随机对照的 95% 分位：① 现行的信号按「股票 × 周」随机保留同样比例 30 次；② 月度面板（DIR3⁺、IND3⁺、SALES）
    在有数据的区间（SALES 有值 ≥ 80% 起）里一起循环错开 24 + 13i 个月（i = 0〜19）；③ 只错开 SALES（成本面板不动）——
    S4 / S5 与 T5 去掉的业种月重叠很多（审计：约 6〜8 成），③ 检验的是「销售」有没有增量。
  另报（不进判定）：近似时点日経225（qbreak/n225_history，scripts/pit_recheck.py 同一口径）下的现行 / S4 / S5；去掉最好一年的每笔；
    各种错开的保留比例。
四 结论上限：行业层有效 → 提议日报加「成本 × 销售」显示（用户确认）；S4 / S5 过 → 提议前向记录（用户确认；模拟盘不改）；都不成立 → 维持现行。
五 事前预期（写死）：S1 有效约 10%、S2 约 10%（其中「新证据」各约一半）、S4 / S5 各约 5%；全部不成立约 70%。
  检出力低：每月约 6 个业种分两半，3 个月差的标准误约 1〜1.5 pp；两个主检验不校正时总误报约 10% → 用 Holm。
六 局限：行业层与 transmit_study 用同一段数据；短観是大企業、年度计划（BOJ 的值是最新版，不是当时的速报；影响很小）；2004 / 2010 年分类变更
  （旧分类拼接）；サービス業 / 情報・通信業 的 SALES 2009 年以后才有；電気・ガス業 很常落在成本压力大的一组（去掉任何一个业种的稳健性已进判定）；
  Z / E 是今天的日経225（另报近似时点；旧成员 42 只里 9 只没有东证业种 → 照做）；成本部分的局限同 transmit_study。
七 登记前核对（2026-09-28 `--check`：只看结构 / 覆盖，没算任何收益；数据指纹 3196547bcaee）
  横截面 18 个（CS）；SALES 1995-04 起（サービス業 / 情報・通信業 2009-04 起）；信号月 239 个里 SALES 缺值的业种月 60。
  S1：成本压力大的业种每月中位 6 个（≥ 4 个的月 177）；对照组中位 12。S2：成本上升月 146；销售好且成本上涨的业种中位 7 个（≥ 4 的月 128）；基准组中位 15。
  成本压力大最常见：輸送用機器 60%、金属製品 60%、電気・ガス業 55%、食料品 53%、化学 48%、電気機器 46%（信号月比例）。
  SALES 前 1/3 的频率 18〜52%（不動産業 52% 最高，精密機器 18% 最低）→ 不是固定标签（审计前的定义里輸送用機器 80% 的月份在最低 1/3）。
  横截面秩相关中位：COST3⁺ 与 SALES −0.09、SALES 与价格转嫁 −0.08、与売上高修正率 +0.43。
  个股层：S4 每月不做的业种平均 4.0 个、S5 3.1 个（2001〜2026）；与 T5 去掉的业种月重叠 S4 65%、S5 69%；错开对照的有效区间从 1995-04 起。
输出：var/out/cost_sales_study.md / .json（只有统计）
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

START, END = TS.START, TS.END
EXCLUDE = ["医薬品", "ゴム製品", "海運業"]
CS = ["その他製品", "その他金融業", "ガラス・土石製品", "サービス業", "パルプ・紙", "不動産業", "化学", "小売業", "建設業", "情報・通信業", "機械",
      "精密機器", "繊維製品", "輸送用機器", "金属製品", "電気・ガス業", "電気機器", "食料品"]
COST_FLOOR, MIN_SET, T_MIN, T_PAIR, HIT_MIN, P_MAX, LAGS, GAP = 0.1, 4, 2.0, 1.645, 55.0, 0.05, 4, 24
VALID_FRAC = 0.8
SHIFT_STOCK = TS.SHIFT_STOCK
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 信号（有测试）─────────────────────────
def pos_signals(P: pd.DataFrame, ex: dict, months: pd.DatetimeIndex, inds: list[str], w: int = 3) -> dict[str, pd.DataFrame]:
    """月末 × 业种：D3p / I3p（只算原材料上涨的部分）与 D3 / I3（涨跌都算，= transmit_study 的 DIR / IND）。"""
    dP = SC.price_change(P, months, w)
    dPp = dP.clip(lower=0)
    out = {k: pd.DataFrame(0.0, index=months, columns=inds) for k in ("D3p", "I3p", "D3", "I3")}
    for k in TS.SHOCKS:
        dk, nk = ex["direct"][k], ex["indirect"][k]
        for j in inds:
            out["D3p"][j] += dk.get(j, 0.0) * dPp[k]
            out["I3p"][j] += nk.get(j, 0.0) * dPp[k]
            out["D3"][j] += dk.get(j, 0.0) * dP[k]
            out["I3"][j] += nk.get(j, 0.0) * dP[k]
    ok = dP[list(TS.SHOCKS)].notna().all(axis=1)
    return {k: v.where(ok, np.nan, axis=0) for k, v in out.items()}


def rank_pct(X: pd.DataFrame) -> pd.DataFrame:
    return X.rank(axis=1, pct=True)


def costly(D3p: pd.DataFrame, I3p: pd.DataFrame) -> pd.DataFrame:
    """成本压力大：COST3⁺ ≥ COST_FLOOR 且在横截面最高 1/3。"""
    C = D3p + I3p
    return (C >= COST_FLOOR) & (rank_pct(C) > 2 / 3)


def row_mask(up: pd.Series, like: pd.DataFrame) -> pd.DataFrame:
    """月度布尔（例 成本上升的月份）扩成与 like 同形的布尔表（缺的月份 = False）。"""
    u = up.reindex(like.index).fillna(False).astype(bool).to_numpy()
    return pd.DataFrame(np.repeat(u[:, None], like.shape[1], axis=1), index=like.index, columns=like.columns)


def split_spread(Y: pd.DataFrame, sel: pd.DataFrame, key: pd.DataFrame, min_n: int = MIN_SET, drop: str | None = None) -> pd.Series:
    """每月：sel 为真、key 与 Y 有值的业种按 key 的秩分上半 / 下半（秩正好在中线的 —— 奇数个的中间、并列跨过中线的 —— 不算）
    → 上半的 Y 平均 − 下半的 Y 平均；少于 min_n 个业种 → 不算。drop：去掉这个业种（稳健性）。"""
    out = {}
    for t in sel.index:
        if t not in key.index or t not in Y.index:
            continue
        m = sel.loc[t].fillna(False).astype(bool)
        if drop is not None and drop in m.index:
            m[drop] = False
        k = key.loc[t][m]
        y = Y.loc[t].reindex(k.index)
        k = k[k.notna() & y.notna()]
        if len(k) < min_n:
            continue
        r = k.rank(method="average")
        mid = (len(k) + 1) / 2
        hi, lo = r[r > mid].index, r[r < mid].index
        if not len(hi) or not len(lo):
            continue
        out[t] = float(Y.loc[t, hi].mean() - Y.loc[t, lo].mean())
    return pd.Series(out, dtype=float)


def s1_sets(D3p, I3p, SALES) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(成本压力大的业种, 成本压力不大但有 SALES 的业种)。"""
    C = costly(D3p, I3p)
    return C, ~C & SALES.notna()


def s2_sets(D3p, I3p, D3, I3, SALES, top: float = 0.5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """成本上升的月份里：(销售好（SALES 秩 > top）且 COST3⁺ ≥ 0.1, 同样月份 COST3⁺ ≥ 0.1 的全部业种)。"""
    up = row_mask((D3 + I3).mean(axis=1) > 0, D3p)
    hit = (D3p + I3p) >= COST_FLOOR
    return up & hit & (rank_pct(SALES) > top), up & hit


def indirect_share(D3p, I3p) -> pd.DataFrame:
    C = D3p + I3p
    return (I3p / C.where(C > 0)).astype(float)


# ───────────────────────── 检验汇总（有测试）─────────────────────────
def spread_test(x: pd.Series, placebo: list[pd.Series] | None = None) -> dict:
    """月度差：平均、NW t、两半、每 3 个月不重叠取样的命中率（3 种起点与中位）、时间错开对照的经验 p（单侧，平均越大越好）。"""
    st = SC.ic_stats(x, LAGS)
    hs = {k: SC.ic_stats(x[(x.index >= a) & (x.index <= b)], LAGS)["ic"] for k, (a, b) in TS.halves().items()}
    hits = [round(float((x.iloc[ph::3] > 0).mean() * 100), 1) for ph in range(3) if len(x.iloc[ph::3])]
    out = {"mean": st["ic"], "t": st["t"], "n": st["n"], "H1": hs["H1"], "H2": hs["H2"], "hits": hits,
           "hit": float(np.median(hits)) if hits else None}
    if placebo is not None:
        pt = np.array([SC.ic_stats(p, LAGS)["t"] if len(p) else np.nan for p in placebo], dtype=float)   # t 为 None → nan
        out.update({"placebo_n": int(np.isfinite(pt).sum()), "placebo_t95": round(float(np.nanpercentile(pt, 95)), 2) if np.isfinite(pt).any() else None,
                    "placebo_p": SC.placebo_p(st["t"] if st["t"] is not None else np.nan, pt)})
    return out


def paired(a: pd.Series, b: pd.Series) -> dict:
    d = (a - b).dropna()
    st = SC.ic_stats(d, LAGS)
    return {"diff": st["ic"], "t": st["t"], "n": st["n"]}


def holm(ps: dict[str, float | None], alpha: float = P_MAX) -> dict[str, bool]:
    """Holm 逐步：p 从小到大，第 i 个（0 起）要 < alpha / (m − i)；前面有一个不过，后面都不过。None → 不过。"""
    items = sorted(ps.items(), key=lambda kv: (kv[1] is None, kv[1] if kv[1] is not None else 1.0))
    m, ok, still = len(items), {}, True
    for i, (k, p) in enumerate(items):
        still = still and p is not None and p < alpha / (m - i)
        ok[k] = still
    return ok


def effective(r: dict, loo: float | None, holm_ok: bool) -> list[str]:
    f = []
    if not (r["mean"] is not None and r["mean"] > 0 and r["t"] is not None and r["t"] >= T_MIN):
        f.append(f"平均 {r['mean']}（t {r['t']}）不够")
    if not (r["H1"] is not None and r["H1"] > 0 and r["H2"] is not None and r["H2"] > 0):
        f.append(f"两半 {r['H1']} / {r['H2']} 不都 > 0")
    if not (r["hit"] is not None and r["hit"] >= HIT_MIN):
        f.append(f"命中率 {r['hit']}% < {HIT_MIN}%")
    if not (loo is not None and loo > 0):
        f.append(f"去掉某一个业种后平均最低 {loo} ≤ 0")
    if not holm_ok:
        f.append(f"对照经验 p {r.get('placebo_p')}（Holm 后）不够")
    return f


def loo_min(Y, sel, key, cols) -> float | None:
    vals = [split_spread(Y, sel, key, drop=c).mean() for c in cols]
    vals = [v for v in vals if np.isfinite(v)]
    return round(float(min(vals)), 4) if vals else None


def fm_interaction(Y, D3p, I3p, SALES, min_n: int = 12) -> dict:
    """每月横截面 OLS：Y ~ 1 + z(DIR3⁺) + z(IND3⁺) + z(SALES) + z(DIR3⁺)·z(SALES) + z(IND3⁺)·z(SALES) → 各系数的平均与 NW t（另报）。"""
    names = ["dir", "ind", "sales", "dir_x_sales", "ind_x_sales"]
    rows = {}
    for t in Y.index:
        if t not in D3p.index or t not in SALES.index:
            continue
        zd, zi, zs, y = TS._z(D3p.loc[t].to_numpy(float)), TS._z(I3p.loc[t].to_numpy(float)), TS._z(SALES.loc[t].to_numpy(float)), Y.loc[t].to_numpy(float)
        m = np.isfinite(zd) & np.isfinite(zi) & np.isfinite(zs) & np.isfinite(y)
        if m.sum() < min_n:
            continue
        Xm = np.column_stack([np.ones(m.sum()), zd[m], zi[m], zs[m], zd[m] * zs[m], zi[m] * zs[m]])
        b, *_ = np.linalg.lstsq(Xm, y[m], rcond=None)
        rows[t] = b[1:]
    B = pd.DataFrame.from_dict(rows, orient="index", columns=names)
    return {c: SC.ic_stats(B[c], LAGS) for c in names} | {"months": int(len(B))}


# ───────────────────────── 个股层（有测试）─────────────────────────
def skip_panel(D3p, I3p, SALES, rule: str) -> pd.DataFrame:
    """月末 × 业种：下个月不做的布尔表。S4：成本压力大且（偏直接 或 SALES 不在前 1/3）；S5：成本压力大且 SALES 不在前 1/3。"""
    C = costly(D3p, I3p)
    top = (rank_pct(SALES) > 2 / 3).reindex(index=C.index, columns=C.columns).fillna(False)
    direct = D3p > I3p
    return C & (direct | ~top) if rule == "S4" else C & ~top


def stock_keep(fr: dict, s33: dict, D3p, I3p, SALES, rule: str) -> dict[str, np.ndarray]:
    bad = skip_panel(D3p, I3p, SALES, rule).astype(float)
    out = {}
    for t, df in fr.items():
        ind = s33.get(t)
        if ind not in bad.columns:
            out[t] = np.ones(len(df), bool)
            continue
        v = TS.daily_from_monthly(bad[ind], df.index).to_numpy(float)
        out[t] = ~(np.nan_to_num(v, nan=0.0) > 0.5)
    return out


def valid_start(SALES: pd.DataFrame, D3p: pd.DataFrame, frac: float = VALID_FRAC) -> pd.Timestamp:
    """SALES 有值的业种 ≥ frac 且成本面板有值的第一个月末（错开对照只在这之后循环）。"""
    ok = (SALES.notna().mean(axis=1) >= frac) & D3p.notna().all(axis=1)
    return ok[ok].index[0]


def roll_block(X: pd.DataFrame, s: int, start) -> pd.DataFrame:
    """只在 start 之后的月份里循环错开 s 期（之前的月份不动）→ 不把开头的缺值块错进检验窗口。"""
    out = X.copy()
    m = X.index >= pd.Timestamp(start)
    out.loc[m] = SC.roll(X.loc[m], s).to_numpy()
    return out


def stock_windows(s33, D3p, I3p, SALES) -> dict:
    import leap2_common as L2
    import leap_confirm as LF
    import pit_recheck as PR
    from qbreak import n225_history as H
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    vs = valid_start(SALES, D3p)
    rules = ("S4", "S5")
    res = {}
    for era in ("Z", "E", "J"):
        t0 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        a, b = ctx["windows"][era]
        r = {"现行": LF.run(ctx, run_fn, fw, p)}
        exb = {"现行": PR.ex_best_year(PR.last_trades(), a, b)}
        pq, pt, ps, frac, shift_frac = {}, {}, {}, {}, {}
        for cid in rules:
            keep = stock_keep(fw, s33, D3p, I3p, SALES, cid)
            frac[cid] = LF.keep_frac(fw, keep)
            r[cid] = LF.run(ctx, run_fn, LF.with_mask(fw, keep), p)
            exb[cid] = PR.ex_best_year(PR.last_trades(), a, b)
            q = LF.placebo_trades(ctx, run_fn, fw, p, frac[cid], seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            pq[cid] = {"win": q["win"], "mean": q["mean"]}
            for tag, sink in (("all", pt), ("sales", ps)):
                vals, fr_list = {"win": [], "mean": []}, []
                for s in SHIFT_STOCK:
                    if tag == "all":
                        kk = stock_keep(fw, s33, roll_block(D3p, s, vs), roll_block(I3p, s, vs), roll_block(SALES, s, vs), cid)
                    else:
                        kk = stock_keep(fw, s33, D3p, I3p, roll_block(SALES, s, vs), cid)
                    fr_list.append(LF.keep_frac(fw, kk))
                    rs = LF.run(ctx, run_fn, LF.with_mask(fw, kk), p)[era]
                    for k in vals:
                        if rs.get(k) is not None:
                            vals[k].append(rs[k])
                sink[cid] = {k: (float(np.percentile(v, L2.PLACEBO_Q)) if v else float("nan")) for k, v in vals.items()}
                shift_frac[f"{cid}_{tag}"] = {"min": round(float(min(fr_list)), 3), "mean": round(float(np.mean(fr_list)), 3),
                                              "max": round(float(max(fr_list)), 3)}
        today = list(universe("JP", "broad"))
        cp = LF.context(era, names=H.pit_names(today)) if era in ("Z", "E") else PR.j_pit_context(ctx)
        fap = LF.frames(cp, p0)
        mem = H.member_mask(fap)
        rfp = LF.runner(cp, fap)
        kw = LF.w2_keep(cp, fap)
        fwp = LF.with_mask(fap, {t: kw[t] & mem[t] for t in fap})
        pit = {"现行": LF.run(cp, rfp, fwp, p)[era]}
        for cid in rules:
            pit[cid] = LF.run(cp, rfp, LF.with_mask(fwp, stock_keep(fwp, s33, D3p, I3p, SALES, cid)), p)[era]
        res[era] = {"res": r, "pq": pq, "pt": pt, "ps": ps, "frac": frac, "shift_frac": shift_frac, "ex_best": exb, "pit": pit,
                    "valid_start": str(vs.date()), "secs": round(time.time() - t0)}
    return res


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> str:
    root = str(paths.PROJECT_ROOT)
    try:
        rev = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", "scripts", "qbreak", "var/io_indirect_2020.json",
                                     "var/industry_s33.json"], capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return rev + ("（脏）" if dirty else "")


def data_hash(*frames: pd.DataFrame) -> str:
    """面板的指纹（BOJ 缓存 12 小时会重取、数值可能被修订 → 登记前核对与运行各记一次）。"""
    h = hashlib.sha256()
    for f in frames:
        h.update(pd.util.hash_pandas_object(f.round(6), index=True).values.tobytes())
    return h.hexdigest()[:12]


def panels(months: pd.DatetimeIndex, inds: list[str]) -> dict:
    ex = TS.load_exposures(inds)
    P = pd.DataFrame({k: TS.cgpi(c) for k, c in TS.SHOCK_CGPI.items()})
    sig = pos_signals(P, ex, months, inds, 3)
    S = TK.load_sales()
    need = {c for g in CS for c in TK.TSE.get(g, [])}
    bad = [c for c in TK.MISSING if "102CFY" in c and c[5:9] in need]
    if bad:
        raise SystemExit(f"短観売上高 取不到：{bad}（不跑，防止横截面悄悄变小）")
    SALES = TK.to_tse(TK.sales_strength(S, months), inds)
    REV = TK.to_tse(TK.sales_revision(TK.load_sales_rev(), months), inds)
    PT = TK.to_tse(TK.pass_through(TK.load(), months), inds)
    return {**sig, "SALES": SALES, "REV": REV, "PT": PT}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报结构与覆盖（不看任何收益）")
    ap.add_argument("--skip-stock", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    Mret, s33 = TS.load_industry_returns()
    inds = list(Mret.columns)
    mz = pd.date_range("1990-01-31", END, freq="ME")
    X = panels(mz, inds)
    cs = [j for j in inds if j not in TS.BENEFIT and j not in EXCLUDE and j in X["SALES"].columns]
    if sorted(cs) != sorted(CS):
        raise SystemExit(f"横截面与登记的不一致：{sorted(set(cs) ^ set(CS))}")
    D3p, I3p, D3, I3, SALES, REV, PT = (X[k].reindex(columns=CS) for k in ("D3p", "I3p", "D3", "I3", "SALES", "REV", "PT"))
    dh = data_hash(D3p, I3p, SALES)
    mon = Mret.index[Mret.index >= pd.Timestamp(START)]
    if a.check:
        C1, C1c = s1_sets(D3p.reindex(mon), I3p.reindex(mon), SALES.reindex(mon))
        S2, S2b = s2_sets(*(Z.reindex(mon) for Z in (D3p, I3p, D3, I3, SALES)))
        print(f"横截面 {len(CS)} 个：{'、'.join(CS)}；数据指纹 {dh}")
        print("SALES 的第一个有值月：" + "、".join(f"{j} {SALES[j].first_valid_index().date() if SALES[j].notna().any() else '—'}" for j in CS))
        print(f"信号月 {len(mon)} 个；SALES 缺值的业种月 {int(SALES.reindex(mon).isna().sum().sum())}")
        n1 = C1.sum(axis=1)
        print(f"S1：成本压力大的业种数 每月中位 {int(n1.median())}（≥ {MIN_SET} 的月 {int((n1 >= MIN_SET).sum())}）；对照组中位 {int(C1c.sum(axis=1).median())}")
        n2, n2b = S2.sum(axis=1), S2b.sum(axis=1)
        print(f"S2：成本上升月 {int(((D3 + I3).mean(axis=1) > 0).reindex(mon).sum())}；销售好且 COST3⁺ ≥ {COST_FLOOR} 的业种数 中位 {int(n2[n2 > 0].median())}"
              f"（≥ {MIN_SET} 的月 {int((n2 >= MIN_SET).sum())}）；基准组中位 {int(n2b[n2b > 0].median())}")
        freq = C1.mean().sort_values(ascending=False)
        print("成本压力大的业种出现频率（信号月 %）：" + "、".join(f"{j} {v * 100:.0f}" for j, v in freq.head(6).items()))
        top_sh = (rank_pct(SALES.reindex(mon)) > 2 / 3).mean().sort_values(ascending=False)
        print("SALES 前 1/3 的频率（%）：" + "、".join(f"{j} {v * 100:.0f}" for j, v in top_sh.head(5).items()) + " … 最低 "
              + "、".join(f"{j} {v * 100:.0f}" for j, v in top_sh.tail(3).items()))
        rc = lambda A, B: np.nanmedian([A.loc[t].rank().corr(B.loc[t].rank()) for t in mon])      # noqa: E731  秩相关（没有 scipy）
        print(f"COST3⁺ 与 SALES 的横截面秩相关 中位 {rc(D3p + I3p, SALES):.2f}；SALES 与 PT {rc(SALES, PT):.2f}、与修正率 {rc(SALES, REV):.2f}")
        mzz = mz[(mz >= pd.Timestamp("2000-12-31")) & (mz <= pd.Timestamp(END))]
        k4, k5 = (skip_panel(D3p, I3p, SALES, r).reindex(mzz) for r in ("S4", "S5"))
        IND3 = TS.signals(pd.DataFrame(0.0, index=mz, columns=inds), pd.DataFrame({k: TS.cgpi(c) for k, c in TS.SHOCK_CGPI.items()}),
                          TS.load_exposures(inds), 3)["IND"][[j for j in inds if j not in TS.BENEFIT]]
        t5 = ((IND3.rank(axis=1, pct=True) > 2 / 3) & (IND3 > 0)).reindex(index=mzz, columns=CS).fillna(False)
        ov = lambda A: float((A & t5).sum().sum() / max(1, A.sum().sum()) * 100)                     # noqa: E731
        print(f"个股层：S4 每月不做的业种数 平均 {k4.sum(axis=1).mean():.1f}、S5 {k5.sum(axis=1).mean():.1f}（2001〜2026）；"
              f"与 T5 去掉的业种月重叠 S4 {ov(k4):.0f}%、S5 {ov(k5):.0f}%；错开对照的有效区间起点 {valid_start(SALES, D3p).date()}")
        return 0
    say(f"# 成本 × 销售：销售特别好能不能盖过原材料成本、销售好时选间接（{pd.Timestamp.today().date()}；git {git_info()}；数据指纹 {dh}）")
    say(f"规则见 scripts/cost_sales_study.py 开头（先提交后运行）。横截面 = {len(CS)} 个业种。各差 = 之后 3 个月的相对收益 %（上半平均 − 下半平均）。")
    Y = SC.ahead(Mret, 3).reindex(mon)[CS]
    Dp, Ip, Dn, In, S_, R_, P_ = (Z.reindex(mon) for Z in (D3p, I3p, D3, I3, SALES, REV, PT))
    shifts = range(GAP, len(mon) - GAP + 1)
    C1, C1c = s1_sets(Dp, Ip, S_)
    x1, x1c = split_spread(Y, C1, S_), split_spread(Y, C1c, S_)
    pl1 = []
    for s in shifts:
        Sr = SC.roll(S_, s)
        pl1.append(split_spread(Y, s1_sets(Dp, Ip, Sr)[0], Sr))
    r1 = spread_test(x1, pl1)
    S2, S2b = s2_sets(Dp, Ip, Dn, In, S_)
    key = indirect_share(Dp, Ip)
    x2, x2b = split_spread(Y, S2, key), split_spread(Y, S2b, key)
    pl2 = []
    for s in shifts:
        Sr = SC.roll(S_, s)
        pl2.append(split_spread(Y, s2_sets(Dp, Ip, Dn, In, Sr)[0], key))
    r2 = spread_test(x2, pl2)
    hk = holm({"S1": r1.get("placebo_p"), "S2": r2.get("placebo_p")})
    lo1, lo2 = loo_min(Y, C1, S_, CS), loo_min(Y, S2, key, CS)
    f1, f2 = effective(r1, lo1, hk["S1"]), effective(r2, lo2, hk["S2"])
    pp1, pp2 = paired(x1, x1c), paired(x2, x2b)
    new1 = pp1["t"] is not None and pp1["diff"] is not None and pp1["diff"] > 0 and pp1["t"] >= T_PAIR
    new2 = pp2["t"] is not None and pp2["diff"] is not None and pp2["diff"] > 0 and pp2["t"] >= T_PAIR
    v1 = ("销售能盖过成本压力" if (not f1 and new1) else "销售好本身有预测力（不只是盖过成本）" if not f1 else "无效")
    v2 = ("销售好时偏间接的更好（销售这一条件起作用）" if (not f2 and new2) else "偏间接的本来就略好（与 T1 已见的一致，不算新证据）" if not f2 else "无效")
    fmt = lambda r: (f"平均 {r['mean']:+.3f}%（t {r['t']}，{r['n']} 个月）；两半 {r['H1']} / {r['H2']}；命中率 {r['hit']}%（3 种起点 {r['hits']}）"      # noqa: E731
                     + (f"；对照 t 的 95% 分位 {r['placebo_t95']}、经验 p {r['placebo_p']}" if "placebo_p" in r else ""))
    say("\n## S1（主）「销售盖过成本」：成本压力大的业种里，销售强的一半 − 弱的一半")
    say(f"- {fmt(r1)}；去掉任何一个业种后平均最低 {lo1}")
    say(f"- 对照组（成本压力不大的业种里同样分）：{fmt(spread_test(x1c))}；配对差 S1 − 对照 = {pp1['diff']}（t {pp1['t']}）")
    say(f"- 判定：{'有效' if not f1 else '无效：' + '；'.join(f1)} → **{v1}**")
    say("\n## S2（主）「销售好时选间接」：成本上升的月份、销售好（前一半）且成本上涨的业种里，间接占比高的一半 − 低的一半")
    say(f"- {fmt(r2)}；去掉任何一个业种后平均最低 {lo2}")
    say(f"- 基准（同样月份、不看销售的全部成本上涨业种）：{fmt(spread_test(x2b))}；配对差 S2 − 基准 = {pp2['diff']}（t {pp2['t']}）")
    say(f"- 判定：{'有效' if not f2 else '无效：' + '；'.join(f2)} → **{v2}**")
    fm = fm_interaction(Y, Dp, Ip, S_)
    side = {"S1_PT": spread_test(split_spread(Y, s1_sets(Dp, Ip, P_)[0], P_)), "S1_REV": spread_test(split_spread(Y, s1_sets(Dp, Ip, R_)[0], R_)),
            "S2_PT": spread_test(split_spread(Y, s2_sets(Dp, Ip, Dn, In, P_)[0], key)),
            "S2_top3": spread_test(split_spread(Y, s2_sets(Dp, Ip, Dn, In, S_, top=2 / 3)[0], key))}
    say("\n## 另报（不进判定）")
    say(f"- Fama–MacBeth（{fm['months']} 个月；每 1 个标准差、之后 3 个月 %）：" + "、".join(
        f"{k} {fm[k]['ic']:+.3f}（t {fm[k]['t']}）" for k in ("dir", "ind", "sales", "dir_x_sales", "ind_x_sales")))
    for k, lab in (("S1_PT", "S1 用价格转嫁（販売 − 仕入 DI）"), ("S1_REV", "S1 用売上高修正率"), ("S2_PT", "S2 用价格转嫁选「销售好」"),
                   ("S2_top3", "S2 用 SALES 前 1/3")):
        say(f"- {lab}：{fmt(side[k])}")
    res = {"git": git_info(), "data_hash": dh, "cs": CS, "S1": {**r1, "loo_min": lo1, "fails": f1, "paired": pp1, "verdict": v1},
           "S2": {**r2, "loo_min": lo2, "fails": f2, "paired": pp2, "verdict": v2}, "holm": hk, "FM": fm, "side": side}
    write_out(res)
    if not a.skip_stock:
        import leap2_common as L2
        W = stock_windows(s33, D3p, I3p, SALES)
        say(f"\n## S4 / S5（个股：日経225 的突破，现行 = S0C2 + W2；Z / E 去掉休市假行；错开对照的有效区间从 {W['Z']['valid_start']} 起）")
        say("| 窗口 | 方案 | 组合 年化 / 回撤 / Calmar · 个股笔数 每笔 / 胜率 | 保留 | 对照 95% 分位：股票 × 周 | 全部错开 | 只错开销售 | 去掉最好一年 | 近似时点名单 |")
        say("|---|---|---|---|---|---|---|---|---|")
        qf = lambda q: f"{q['win']:.1f}% / {q['mean']:+.2f}%" if q else "—"                       # noqa: E731
        for era in ("Z", "E", "J"):
            for k, r in W[era]["res"].items():
                s = r[era]
                xb, pp = W[era]["ex_best"].get(k), W[era]["pit"].get(k)
                say(f"| {era} | {k} | {s.get('cagr')}% / {s.get('dd')}% / {s.get('calmar')} · {s.get('n')} 笔 {s.get('mean')}% / {s.get('win')}% | "
                    f"{W[era]['frac'].get(k, 1) * 100:.0f}% | {qf(W[era]['pq'].get(k))} | {qf(W[era]['pt'].get(k))} | {qf(W[era]['ps'].get(k))} | "
                    + (f"去 {xb['best_year']}：{xb['n']} 笔 {xb['mean']:+.2f}% / {xb['win']:.0f}%" if xb and xb.get("n") else "—") + " | "
                    + (f"{pp.get('n')} 笔 {pp.get('mean')}% / {pp.get('win')}%；Calmar {pp.get('calmar')}" if pp else "—") + " |")
        say("- 错开对照的保留比例（最低 / 平均 / 最高）：" + "；".join(f"{e} " + "、".join(f"{k} {v['min']}/{v['mean']}/{v['max']}" for k, v in W[e]["shift_frac"].items())
                                                         for e in ("Z", "E", "J")))
        base = {e: W[e]["res"]["现行"][e] for e in ("Z", "E", "J")}
        for cid in ("S4", "S5"):
            cand = {e: W[e]["res"][cid][e] for e in ("Z", "E", "J")}
            fi = L2.improve_fails(cand, base)
            fp = []
            for e in ("Z", "E", "J"):
                for nm, q in (("股票 × 周", W[e]["pq"][cid]), ("全部错开", W[e]["pt"][cid]), ("只错开销售", W[e]["ps"][cid])):
                    if not (L2.is_finite(cand[e].get("win")) and cand[e]["win"] > q["win"] and L2.is_finite(cand[e].get("mean")) and cand[e]["mean"] > q["mean"]):
                        fp.append(f"{e} {nm}对照没过")
            res[cid] = {"improve_fails": fi, "placebo_fails": fp, "frac": {e: W[e]["frac"][cid] for e in W},
                        "windows": {e: {k: {w: v for w, v in r.items() if not str(w).startswith("_")} for k, r in W[e]["res"].items()} for e in W},
                        "placebo": {e: {"lottery": W[e]["pq"][cid], "shift_all": W[e]["pt"][cid], "shift_sales": W[e]["ps"][cid]} for e in W},
                        "shift_frac": {e: W[e]["shift_frac"] for e in W}, "ex_best": {e: W[e]["ex_best"] for e in W}, "pit": {e: W[e]["pit"] for e in W}}
            say(f"- {cid}：{'选股改进成立' if not (fi or fp) else '不成立：' + '；'.join(fi + fp)}")
    say("\n## 结论（事先规则）")
    say(f"- 行业层：S1 {res['S1']['verdict']}；S2 {res['S2']['verdict']}"
        + ("→ 提议日报加「成本 × 销售」显示（用户确认）" if (not f1 or not f2) else "") + "。")
    if not a.skip_stock:
        ok = [k for k in ("S4", "S5") if not (res[k]["improve_fails"] or res[k]["placebo_fails"])]
        say(f"- 个股层：{('、'.join(ok) + ' 过 → 提议前向记录（用户确认）') if ok else 'S4 / S5 都不过 → 模拟盘不变'}。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "cost_sales_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
