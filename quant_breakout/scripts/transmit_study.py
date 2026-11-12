"""transmit_study.py — 间接影响的传导时间：原材料涨跌「直接」影响的行业 vs 经过供应链「间接」影响的行业
（2026-09-28 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-28）：「选股票想进行去掉直接影响因素的股票 选择间接影响的股票 这样会有传导时间 胜率和收益有可能更稳定一些
  例如原材料上升直接影响了哪些行业 但是相关的间接行业还没有被影响 进行这类的研究 结合现在所有的研究成果和数据」「继续，审计完登记并运行」。
来由与已经看过的（照实写；研究总图 var/out/research_map.md）：
  - supply_chain_study（登记 4534945）：一阶的原材料成本压力 C（直接投入份额 × 企业物价 20 类）→ 之后 1〜6 个月的行业相对收益 IC +0.012（t 0.57）无效；
    A2 / A3 看到「化学製品 / 石油・石炭製品 → 機械・電気機器・半導体」（日本两半都在），美国 1970〜1998 没有（us_replication_study，时代现象）；
    上游股价 S（IC −0.004）、下游股价 K 都没有带动；买点 V1（成本）/ V6（原材料顺风）不通过。
  - theme_study（登记 4576e61）TB：进口一般炭 / LNG / 原油 → 30 业种（错峰 0 / 3 / 6 个月）已经看过：之后 1〜6 个月 機械 / 精密 / 半导体相关变差、
    卸売業变好（t +3.57 / +5.72），「有效果时 0〜3 个月内就到」。
  - leadlag_study：日本行业之间没有稳定的领先；lag_study（错峰）：外部因子当天 / 隔夜就反映；S5：个股对原油的 β 两个年代方向相反。
  → 以前的都是「一阶」渠道，或直接拿能源价格对行业；这一轮新的是「只经过供应链二阶以上」的暴露（例：原油 → 石油製品 → 化学 → 塑料 → 电机）
    与「直接 vs 间接谁先反应」。审计（登记前）指出：间接信号几乎就是能源那一项（IND 与能源部分 IND_E 的横截面相关中位 0.94；原材料价格的
    月度波动 2006-10〜2026-08：能源 6.8%，鉄鋼 1.4%、非鉄 2.6%、食料 2.1%）→ 事先写定：若 T1 / T2 只靠能源部分成立（其余三种的部分 ≤ 0 或同号不成立），
    读作「与 theme_study 已见的能源轮动一致」，不算新证据。PROP 与 supply_chain_study 的 S（上游股价，IC −0.004）相近，T5 与 V1 / V6（不通过）相近。

一 数据
  产业连关表：令和 2 年（2020）取引基本表 生产者价格 统合中分类 108 部门（e-Stat statInfId=000040187026；原表只在 var/cache/io/，不入库；
    108 部门按上两位 = 37 部门汇总与 37 部门表一致，最大差 0.4 / 平均格 339，四舍五入）。投入系数 A = 交易额 ÷ 国内生产额。
  原材料冲击 4 种（价格 = 日银企业物价 PR01，M 月末只用到已公布的 M−1 月；1990 年起）：
    E 能源 = 部门 061 石炭・原油・天然ガス（输入物价 石油・石炭・天然ガス，円ベース）；S 鉄鋼 = 261 / 262 / 263 / 269（国内 鉄鋼）；
    N 非鉄金属 = 271 / 272（国内 非鉄金属）；F 食料用农水产物 = 011 耕種農業 / 012 畜産 / 017 漁業（输入物价 飲食料品・食料用農水産物；
    国内的農林水産物以大米为主、1 月平均 −2.9% 的季节性 → 不用）。
  直接 / 间接：这些原材料的价格是观测到的 → 在 A 里把 4 种原材料的全部行设为 0（外生），L_S = (I − A_S)^−1；
    原材料行 r 对部门 s：直接 = A[r, s]，间接 = [A[r, :](L_S − I)][s]（只经过其他部门的二阶以上路径；原材料自己的循环，例 钢 → 钢 → 金属製品，
    已经包含在观测到的价格里，不再重复算）。
  部门 → 東証业种：按上两位对应 qbreak/supply_chain.IO_TSE（191 印刷、231 皮革 → 39 その他製品），另外细分：207 医薬品 → 医薬品（其余 20x → 化学）；
    221 塑料製品 → 化学、222 ゴム製品 → ゴム製品；163 / 164 → パルプ・紙、161 木材 / 162 家具 → その他製品；574 水運 → 海運業（其他运输不对应）；
    553 帰属家賃 不对应。业种的暴露 = 对应部门按国内生产额加权。导出的份额存 var/io_indirect_2020.json（只存份额）。
  横截面：30 业种里去掉原材料涨价时自己收入也涨的 6 个（鉱業、石油・石炭製品、鉄鋼、非鉄金属、水産・農林業、卸売業）→ 24 个「使用方」业种。
  行业月度相对收益：TOPIX 1000 的 927 只、東証业种（supply_chain_study 同一口径，yfinance 21 年），2005-10〜2026-08；两半 2006-10〜2016-08 / 2016-09〜。
二 信号（月末 t 已知；w 个月；单位 %）
  DIR_j = Σ_k 直接_kj × Δlog p_k；IND_j = Σ_k 间接_kj × Δlog p_k；另拆成 IND_E（只有能源）与 IND_O（其余三种）只作另报。事先方向：成本上升 → 之后更差（−）。
  PROP_j = Σ_k 间接_kj × R_k，R_k = 直接受 k 影响的使用方业种（直接_kj ≥ 1%，不含 j 自己）按直接份额加权的过去 w 个月相对收益（方向 +）。
三 检验
  T1（主）：−IND（w = 3）→ 之后 3 个月：24 业种的月度横截面秩相关 IC、Newey–West t（4 阶）、两半、三分组命中率、时间错开对照
    （信号面板循环错开 24〜(月数 − 24) 的每一种）。有效 = t ≥ 2.0、两半 IC > 0、命中率 ≥ 55%、对照经验 p < 0.05。
    「强于直接」= 同月的 IC(−IND) − IC(−DIR) 的均值 > 0 且 Newey–West t ≥ 1.645。
    读法：有效 ∧ 强于直接 ∧ IND_O 的 IC > 0 → 间接传导成立；有效 ∧ 强于直接 但 IND_O ≤ 0 → 只靠能源、与已见的能源轮动一致（不算新证据）；
    有效但不强于直接 → 原材料信号有预测力，但不是「间接更慢」。
  T2（传导时间）：每个月横截面回归 第 h 个月的相对收益 ~ 常数 + 标准化 DIR + 标准化 IND（w = 1，24 业种），Fama–MacBeth；
    h = −1（价格变动那个月）、0（公布那个月）、1〜6 都报；登记的统计量 = IND 在 h = 2〜6 的系数之和（h = 1 是公布后的第一个月，
    与 T1 重叠，「更晚」定义为第 2 个月以后）；Newey–West 5 阶。
    成立 = 和 < 0 且 t ≤ −2.0、两半都 < 0（前半只用到 2016-02，避免跨半）、时间错开对照（全部错法）经验 p < 0.05、
    且同月的（IND 和 − DIR 和）均值 < 0、t ≤ −1.645。另报（不进判定）：IND 换成只有其余三种的 IND_O 再回归一次的 h = 2〜6 之和；
    T2 成立但 IND_O 的和 ≥ 0 → 同 T1 读作「只靠能源」。
  T3（次）：PROP（w = 3）→ 之后 3 个月，门槛同 T1 的「有效」；只有 T1 有效时才一起作为行业层面的结论。
  T4（个股，去掉直接受影响的）：原材料 k 上个月的变化 z =（变化 − 同月份的历史平均）÷ 历史标准差（都只用到之前，≥ 24 个月）；
    上个月末 |z| ≥ 1.28 时，k 的产出业种与直接份额 ≥ 5% 的使用方业种的突破 → 不做（这些业种写在下面「登记前核对」）；其余照现行。
  T5（个股，避开间接成本上升最多的）：业种的 IND（w = 3）在上个月末 24 业种里最高的 1/3 且 > 0 → 不做；其余（含 6 个收入受益业种）照现行。
  T4 / T5 的判定：Z / E / J 三个窗口（scripts/leap_confirm.py，日経225，现行 = S0C2 + W2；Z / E 已去掉 Yahoo 的休市假行）：
    「选股改进」（scripts/leap2_common.improve_fails：胜率 ≥ 现行 + 4 pp、每笔 ≥ + 0.5 pp、笔数 ≥ 30%、Calmar ≥ 现行 − 0.02 且回撤不深 2 pp 以上）
    且两种随机对照：① 现行的信号按「股票 × 周」随机保留同样比例 30 次；② 月度信号面板（z 或 IND）循环错开 24 + 13i 个月（i = 0〜19，20 种）
    后同样过滤（整月 × 整个业种一起去掉，与候选同样的聚集方式）→ 候选的胜率与每笔都要 > 两种对照的 95% 分位。
四 结论：行业层面「间接传导成立」→ 提议日报加「间接成本压力」显示（用户确认）；T2 成立 → 写明传导要几个月；
  T4 / T5 过 → 提议前向记录（用户确认才登记，模拟盘不改）；都不成立 → 维持现行，写明「间接影响也没有可利用的时间差」。
五 事前预期（写死；审计后下调）：T1 有效约 10%（其中「间接传导成立」约 5%）；T2 约 10%；T3 约 5%；T4 约 5%；T5 约 5%；全部不成立约 75%。
  检出力：一阶 C 的 IC 标准误约 0.021 → T1 要 IC 约 0.04 以上才过 t 2.0；T4 在 Z 只有约 43 笔现行、若去掉约 12% 还要胜率 +4 pp，
  被去掉的那些要比其余差约 30 pp，很难。
六 局限：2020 年的结构（新冠低油价的年份、2011 年后的燃料结构）套到 2001〜2026（2015 / 2005 年表的稳健性没做）；竞争输入型的表会高估国内的再定价；
  企业物价是今天的 2020 年基准链接值（不是当时公布的速报值）；企业物价是月度、发布滞后，市场价格是实时的；业种是今天的分类、成员是今天的（幸存者偏差）；
  Z / E 是今天的日経225；T4 / T5 要三个窗口都过（样本小时很难）；产业连关表的中间投入不含设备投资与出口需求；
  F 的 011 耕種農業含天然ゴム（ゴム製品 直接 3.9%），价格却用食料用 → ゴム製品 的 F 暴露有偏差（份额小，不改）；
  T4 用「同月份平均」去季节、标准差不分月份 → 价格按年度改定的鉄鋼集中在 5 月末触发（见下）。
七 登记前核对（2026-09-28 `--check`：只看结构与物价，没有算任何收益）
  业种 30 个（横截面 24 个）；月度 2005-10〜2026-08（251 个月）；物价 1990-01〜2026-08，缺月 0。
  直接份额最大：E 石油・石炭製品 48.0%、電気・ガス業 20.7%（其余 ≤ 1.0%）；S 金属製品 19.4%、機械 8.5%、輸送用機器 5.2%、電気機器 2.4%；
    N 電気機器 5.5%、金属製品 5.3%、精密機器 4.5%、機械 2.3%；F 食料品 19.0%、ゴム製品 3.9%。
  间接份额最大：E 化学 9.1%、海運業 5.5%、電気・ガス業 4.6%、パルプ・紙 4.2%、ガラス・土石製品 3.8%；S 輸送用機器 4.7%、機械 2.9%、建設業 2.6%；
    N 輸送用機器 3.8%、電気機器 2.8%；F 食料品 5.7%（其余 ≤ 0.8%）。
  T4 的「直接受影响」业种：E 鉱業・石油・石炭製品・電気・ガス業；S 鉄鋼・金属製品・機械・輸送用機器（5.2%，刚过 5%）；
    N 非鉄金属・金属製品・電気機器（5.5%，刚过 5%）；F 水産・農林業・食料品 → 日経225（213 只有业种）里 91 只属于其中之一。
  信号：DIR 与 IND 的横截面相关中位 0.30（w = 1 与 3 相同）；IND 与 IND_E 0.94。
  |z| ≥ 1.28 的月份（2001〜2026）：E 19%、S 23%、N 24%、F 15%，任一种 54%；鉄鋼在 5 月末（= 4 月的价格变动）63% 的年份触发，
    N 在 2 月末 38%、E 在 3 月末 31%、F 在 11 月末 29%。
输出：var/out/transmit_study.md / .json（只有统计）；var/io_indirect_2020.json（只存导出的份额）
"""
from __future__ import annotations

import argparse
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
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")                              # Z / E 去掉 Yahoo 的休市假行（scripts/leap_confirm.py 缺省也是）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402

IO_XLSX = "https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040187026&fileKind=0"
IO_FILE = "io2020_108.xlsx"
METHOD = "108部门・4 种原材料行外生（2026-09-28 审计后）"
SHOCKS = {"E": "能源（石炭・原油・天然ガス）", "S": "鉄鋼", "N": "非鉄金属", "F": "食料用农水产物"}
SHOCK_ROWS = {"E": ["061"], "S": ["261", "262", "263", "269"], "N": ["271", "272"], "F": ["011", "012", "017"]}
SHOCK_CGPI = {"E": "PRCG20_2600520001", "S": "PRCG20_2200920001", "N": "PRCG20_2201020001", "F": "PRCG20_2600120001"}
SRC = {"E": ["鉱業"], "S": ["鉄鋼"], "N": ["非鉄金属"], "F": ["水産・農林業"]}
BENEFIT = ["鉱業", "石油・石炭製品", "鉄鋼", "非鉄金属", "水産・農林業", "卸売業"]
PARENT_FIX = {"191": "39", "231": "39"}
MAP_OVERRIDE = {"207": ["医薬品"], "201": ["化学"], "202": ["化学"], "203": ["化学"], "204": ["化学"], "205": ["化学"], "206": ["化学"],
                "208": ["化学"], "221": ["化学"], "222": ["ゴム製品"], "161": ["その他製品"], "162": ["その他製品"], "163": ["パルプ・紙"],
                "164": ["パルプ・紙"], "553": [], "571": [], "572": [], "573": [], "574": ["海運業"], "575": [], "576": [], "577": [],
                "578": [], "579": []}
GAP = 24
DIRECT_USER, PROP_MIN = 0.05, 0.01
Z_BIG, Z_MIN_HIST = 1.28, 24
T_MIN, HIT_MIN, P_MAX, T_PAIR = 2.0, 55.0, 0.05, 1.645
T2_H, T2_SUM = (-1, 0, 1, 2, 3, 4, 5, 6), (2, 3, 4, 5, 6)
START, END, H1_END, H1_END_T2 = "2006-10-01", "2026-08-31", "2016-08-31", "2016-02-29"
PRICE_START = "199001"
SHIFT_STOCK = [24 + 13 * i for i in range(20)]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 产业连关表 → 直接 / 间接暴露 ─────────────────────────
def read_io108(xlsx) -> tuple[pd.DataFrame, pd.Series]:
    """取引基本表（统合中分类 108 部门）→ (x：供给部门 × 使用部门 的交易额，X：各部门国内生产额)。"""
    df = pd.read_excel(xlsx, header=None)
    hdr = [str(v).strip() for v in df.iloc[1].tolist()]
    codes = hdr[2:hdr.index("700")]
    rows = {str(df.iloc[i, 0]).strip(): i for i in range(3, df.shape[0]) if str(df.iloc[i, 0]).strip() not in ("nan", "")}
    x = pd.DataFrame([[float(df.iloc[rows[r], 2 + k]) for k in range(len(codes))] for r in codes], index=codes, columns=codes)
    X = pd.Series([float(df.iloc[rows[r], hdr.index("970")]) for r in codes], index=codes)
    return x, X


def tse_of(code: str) -> list[str]:
    """108 部门 → 東証业种（头部一的对照）。"""
    if code in MAP_OVERRIDE:
        return MAP_OVERRIDE[code]
    return SC.IO_TSE.get(PARENT_FIX.get(code, code[:2]), [])


def io_matrices(x: pd.DataFrame, X: pd.Series, exo_rows: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(A 投入系数, M = L_S − I)；L_S = (I − A_S)^−1，A_S = A 把观测到价格的原材料行设为 0。间接_r = A[r, :] @ M。"""
    A = (x / X.replace(0, np.nan)).fillna(0.0)
    As = A.copy()
    As.loc[[r for r in exo_rows if r in As.index], :] = 0.0
    L = np.linalg.inv(np.eye(len(A)) - As.to_numpy(float))
    return A, pd.DataFrame(L - np.eye(len(A)), index=A.index, columns=A.columns)


def exposures(A: pd.DataFrame, M: pd.DataFrame, X: pd.Series, industries: list[str]) -> dict:
    """{"direct": {k: {业种: 份额}}, "indirect": {...}}：業種 = 对应部门按国内生产额加权；k 的产出业种对 k 不算。"""
    by_tse: dict[str, list[str]] = {}
    for c in A.columns:
        for t in tse_of(c):
            by_tse.setdefault(t, []).append(c)
    out = {"direct": {}, "indirect": {}}
    for k, rows in SHOCK_ROWS.items():
        dr = A.loc[rows].sum(axis=0)
        nr = (A.loc[rows].to_numpy(float) @ M.to_numpy(float)).sum(axis=0)
        nr = pd.Series(nr, index=A.columns)
        d, n = {}, {}
        for j in industries:
            J = by_tse.get(j, [])
            if not J or j in SRC[k]:
                continue
            wts = X[J] / X[J].sum()
            d[j] = round(float((dr[J] * wts).sum()), 6)
            n[j] = round(float((nr[J] * wts).sum()), 6)
        out["direct"][k], out["indirect"][k] = d, n
    return out


def load_exposures(industries: list[str], refresh: bool = False) -> dict:
    fp = paths.home() / "io_indirect_2020.json"
    if fp.exists() and not refresh:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        if doc.get("method") == METHOD and set(doc.get("industries", [])) >= set(industries):
            return doc
    xl = paths.sub("cache") / "io" / IO_FILE
    if not xl.exists():
        import urllib.request
        xl.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(IO_XLSX, timeout=120) as r:                  # noqa: S310
            xl.write_bytes(r.read())
    x, X = read_io108(xl)
    A, M = io_matrices(x, X, [r for rows in SHOCK_ROWS.values() for r in rows])
    doc = {"source": "総務省「令和2年（2020年）産業連関表」取引基本表（生産者価格評価、統合中分類 108 部門）；e-Stat statInfId=000040187026",
           "method": METHOD,
           "note": "scripts/transmit_study.py 生成：直接 = 投入系数 A 的原材料行；间接 = A[r, :](L_S − I)，L_S 把 4 种原材料的行设为 0（价格是观测到的）；"
                   "東証业种按对应部门的国内生产额加权；产出业种对自己那一种不算。只存导出的份额，不存原表。",
           "generated": str(pd.Timestamp.today().date()), "industries": list(industries), **exposures(A, M, X, industries)}
    fp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def hit_sets(ex: dict) -> dict[str, list[str]]:
    """T4：每种原材料「直接受影响」的业种 = 产出业种 + 直接份额 ≥ DIRECT_USER 的使用方。"""
    return {k: sorted(set(SRC[k]) | {j for j, v in ex["direct"][k].items() if v >= DIRECT_USER}) for k in SHOCKS}


# ───────────────────────── 价格与信号 ─────────────────────────
def cgpi(code: str) -> pd.Series:
    """日银企业物价（月度，1990 年起；factors 的缓存不看起始日 → 起始日晚于 1990-02 的旧缓存先删掉再取）。"""
    from qbreak import factors
    s = factors.boj_monthly("PR01", code, start=PRICE_START)
    if len(s) and s.index.min() > pd.Timestamp("1990-02-01"):
        fp = factors._dir() / f"boj_PR01_{code}.csv"
        if fp.exists():
            fp.unlink()
        s = factors.boj_monthly("PR01", code, start=PRICE_START)
    return s


def signals(Mret: pd.DataFrame, P: pd.DataFrame, ex: dict, w: int) -> dict[str, pd.DataFrame]:
    """月末 × 业种 的 DIR / IND / IND_E / IND_O / PROP（w 个月）。P：列 = SHOCKS 的键，索引 = 月初。"""
    months, inds = Mret.index, list(Mret.columns)
    dP = SC.price_change(P, months, w)
    O = SC.past(Mret, w)
    zero = lambda: pd.DataFrame(0.0, index=months, columns=inds)             # noqa: E731
    DIR, IND, INDE, INDO, PROP = zero(), zero(), zero(), zero(), zero()
    for k in SHOCKS:
        dk, nk = ex["direct"][k], ex["indirect"][k]
        users = {i: v for i, v in dk.items() if v >= PROP_MIN and i in O.columns and i not in BENEFIT}
        for j in inds:
            DIR[j] += dk.get(j, 0.0) * dP[k]
            part = nk.get(j, 0.0) * dP[k]
            IND[j] += part
            (INDE if k == "E" else INDO)[j] += part
            u = {i: v for i, v in users.items() if i != j}
            if u and nk.get(j, 0.0) > 0:
                PROP[j] += nk[j] * (sum(v * O[i] for i, v in u.items()) / sum(u.values()))
    ok = dP[list(SHOCKS)].notna().all(axis=1)
    return {k: v.where(ok, np.nan, axis=0) for k, v in (("DIR", DIR), ("IND", IND), ("IND_E", INDE), ("IND_O", INDO), ("PROP", PROP))} | {"O": O}


def shock_z(P: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """月末 t：各原材料上个月（已公布）的对数变化 →（变化 − 同月份的历史平均）÷ 历史标准差；平均与标准差都只用到 t 之前，≥ Z_MIN_HIST 个月。"""
    d1 = SC.price_change(P, months, 1)
    sd = d1.expanding(min_periods=Z_MIN_HIST).std().shift(1)
    mon = pd.Series(d1.index.month, index=d1.index)
    mu = d1.groupby(mon.values).transform(lambda s: s.expanding().mean().shift(1)).fillna(0.0)
    return (d1 - mu) / sd


# ───────────────────────── 行业层面的检验 ─────────────────────────
def halves(end_h1: str = H1_END) -> dict:
    return {"H1": (pd.Timestamp(START), pd.Timestamp(end_h1)), "H2": (pd.Timestamp("2016-09-01"), pd.Timestamp(END))}


def ic_test(X: pd.DataFrame, Y: pd.DataFrame, w: int, h: int, placebo: bool = True) -> dict:
    """T1 / T3 的门槛（supply_chain_study A1 同一套）。X 已乘好事先方向。"""
    lags = w + h - 2
    ic = SC.fm_ic(X, Y, lags)
    full = SC.ic_stats(ic, lags)
    hs = {k: SC.ic_stats(ic[(ic.index >= a) & (ic.index <= b)], lags) for k, (a, b) in halves().items()}
    tc = SC.tercile(X, Y, 1, h)
    out = {"ic": full["ic"], "t": full["t"], "n": full["n"], "ic_H1": hs["H1"]["ic"], "ic_H2": hs["H2"]["ic"],
           "hit": tc["hit"], "spread": tc["spread"], "spread_t": tc["t"], "_series": ic}
    if placebo:
        pt = [SC.ic_stats(SC.fm_ic(SC.roll(X, s), Y, lags), lags)["t"] for s in range(GAP, len(X) - GAP + 1)]
        pt = np.array([np.nan if v is None else v for v in pt], float)
        out.update({"placebo_n": int(np.isfinite(pt).sum()), "placebo_t95": round(float(np.nanpercentile(pt, 95)), 2),
                    "placebo_p": SC.placebo_p(full["t"] if full["t"] is not None else np.nan, pt)})
    return out


def ic_effective(r: dict) -> list[str]:
    f = []
    if not (r["t"] is not None and r["t"] >= T_MIN):
        f.append(f"t {r['t']} < {T_MIN}")
    if not (r["ic_H1"] is not None and r["ic_H1"] > 0 and r["ic_H2"] is not None and r["ic_H2"] > 0):
        f.append(f"两半 IC {r['ic_H1']} / {r['ic_H2']} 不都 > 0")
    if not (r["hit"] is not None and r["hit"] >= HIT_MIN):
        f.append(f"三分组命中率 {r['hit']}% < {HIT_MIN}%")
    if not (r.get("placebo_p") is not None and r["placebo_p"] < P_MAX):
        f.append(f"对照经验 p {r.get('placebo_p')} ≥ {P_MAX}")
    return f


def paired(a: pd.Series, b: pd.Series, lags: int) -> dict:
    """同月配对差 a − b 的均值与 Newey–West t。"""
    d = (a - b).dropna()
    st = SC.ic_stats(d, lags)
    return {"diff": st["ic"], "t": st["t"], "n": st["n"]}


def _z(row: np.ndarray) -> np.ndarray:
    m = np.isfinite(row)
    out = np.full(len(row), np.nan)
    if m.sum() >= 3 and np.nanstd(row[m]) > 0:
        out[m] = (row[m] - row[m].mean()) / row[m].std()
    return out


def fm_lag_coefs(D: pd.DataFrame, I: pd.DataFrame, Mret: pd.DataFrame, hs=T2_H, min_n: int = 15) -> dict[int, pd.DataFrame]:
    """每个月 t、每个 h：r_{j, t+h} ~ 1 + z(DIR_j) + z(IND_j) 的横截面 OLS 系数 → {h: DataFrame[月, (dir, ind)]}。"""
    R = Mret.reindex(index=D.index, columns=D.columns).to_numpy(float)
    dv, iv = D.to_numpy(float), I.to_numpy(float)
    n = len(R)
    out = {}
    for h in hs:
        Rh = np.full_like(R, np.nan)
        if h >= 0:
            Rh[: n - h] = R[h:]
        else:
            Rh[-h:] = R[: n + h]
        rows = {}
        for k, t in enumerate(D.index):
            zd, zi, y = _z(dv[k]), _z(iv[k]), Rh[k]
            m = np.isfinite(zd) & np.isfinite(zi) & np.isfinite(y)
            if m.sum() < min_n:
                continue
            b, *_ = np.linalg.lstsq(np.column_stack([np.ones(m.sum()), zd[m], zi[m]]), y[m], rcond=None)
            rows[t] = {"dir": b[1], "ind": b[2]}
        out[h] = pd.DataFrame.from_dict(rows, orient="index", columns=["dir", "ind"])
    return out


def sums(coefs: dict[int, pd.DataFrame]) -> dict[str, pd.Series]:
    return {c: sum(coefs[h][c] for h in T2_SUM).dropna() for c in ("dir", "ind")}


def t2_stat(coefs: dict[int, pd.DataFrame], start: pd.Timestamp) -> dict:
    """IND / DIR 在 h = 2〜6 的系数之和（每个月一个值）：均值、Newey–West t（5 阶）、两半（前半只到 2016-02）、同月配对差。"""
    S = {c: s[s.index >= start] for c, s in sums(coefs).items()}
    out = {}
    for c, s in S.items():
        st = SC.ic_stats(s, 5)
        hs = {k: SC.ic_stats(s[(s.index >= a) & (s.index <= b)], 5) for k, (a, b) in halves(H1_END_T2).items()}
        out[c] = {"sum": st["ic"], "t": st["t"], "n": st["n"], "H1": hs["H1"]["ic"], "H2": hs["H2"]["ic"]}
    out["pair"] = paired(S["ind"], S["dir"], 5)
    out["profile"] = {c: {h: round(float(coefs[h][c][coefs[h].index >= start].mean()), 4) for h in T2_H} for c in ("dir", "ind")}
    return out


def t2_placebo(D: pd.DataFrame, I: pd.DataFrame, Mret: pd.DataFrame, start: pd.Timestamp, actual_t: float | None) -> dict:
    """DIR 与 IND 的信号面板一起循环错开 s 个月（s = 24〜(月数 − 24) 的每一种）→ IND 和的 t。"""
    ts = []
    for s in range(GAP, len(D) - GAP + 1):
        c = fm_lag_coefs(SC.roll(D, s), SC.roll(I, s), Mret, hs=T2_SUM)
        x = sums(c)["ind"]
        st = SC.ic_stats(x[x.index >= start], 5)
        ts.append(np.nan if st["t"] is None else st["t"])
    a = np.array(ts, float)
    return {"n": int(np.isfinite(a).sum()), "t05": round(float(np.nanpercentile(a, 5)), 2) if np.isfinite(a).any() else None,
            "p": SC.placebo_p(actual_t if actual_t is not None else np.nan, a, sign=-1)}


# ───────────────────────── 个股（突破）层面 ─────────────────────────
def daily_from_monthly(M, days: pd.DatetimeIndex):
    """交易日 d → 上个月末的值（月末 t 的信号在 t+1 月的交易日才用）。"""
    return M.reindex((days.to_period("M") - 1).to_timestamp("M"))


def t4_keep(fr: dict, s33: dict[str, str], Z: pd.DataFrame, hits: dict[str, list[str]]) -> dict[str, np.ndarray]:
    """不做：上个月末原材料 k 的 |z| ≥ Z_BIG 且这只票的业种在 k 的「直接受影响」业种里。"""
    out = {}
    for t, df in fr.items():
        ind = s33.get(t)
        z = daily_from_monthly(Z, df.index)
        bad = np.zeros(len(df), bool)
        for k in SHOCKS:
            if k in z.columns and ind in hits[k]:
                bad |= np.abs(np.nan_to_num(z[k].to_numpy(float), nan=0.0)) >= Z_BIG
        out[t] = ~bad
    return out


def t5_keep(fr: dict, s33: dict[str, str], IND3: pd.DataFrame) -> dict[str, np.ndarray]:
    """不做：业种的 IND（w = 3）在上个月末的使用方业种里最高的 1/3 且 > 0。"""
    q = IND3.rank(axis=1, pct=True)
    out = {}
    for t, df in fr.items():
        ind = s33.get(t)
        if ind not in q.columns:
            out[t] = np.ones(len(df), bool)
            continue
        r = daily_from_monthly(q[ind], df.index).to_numpy(float)
        v = daily_from_monthly(IND3[ind], df.index).to_numpy(float)
        out[t] = ~((np.nan_to_num(r, nan=0.0) > 2 / 3) & (np.nan_to_num(v, nan=0.0) > 0))
    return out


def stock_windows(s33: dict[str, str], Zs: pd.DataFrame, IND3: pd.DataFrame, hits: dict) -> dict:
    import leap2_common as L2
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    p = load_params(market="JP")
    make = {"T4": lambda Zp, Ip, fr: t4_keep(fr, s33, Zp, hits), "T5": lambda Zp, Ip, fr: t5_keep(fr, s33, Ip)}
    res = {}
    for era in ("Z", "E", "J"):
        t0 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, SF.no_w2_params(p))
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        r = {"现行": LF.run(ctx, run_fn, fw, p)}
        pq, pt, frac = {}, {}, {}
        for cid, fn in make.items():
            keep = fn(Zs, IND3, fw)
            frac[cid] = LF.keep_frac(fw, keep)
            r[cid] = LF.run(ctx, run_fn, LF.with_mask(fw, keep), p)
            q = LF.placebo_trades(ctx, run_fn, fw, p, frac[cid], seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            pq[cid] = {"win": q["win"], "mean": q["mean"]}
            vals = {"win": [], "mean": []}
            for s in SHIFT_STOCK:                                                # 月度信号面板整体错开 → 同样按整月 × 整个业种过滤
                rs = LF.run(ctx, run_fn, LF.with_mask(fw, fn(SC.roll(Zs, s), SC.roll(IND3, s), fw)), p)[era]
                for k in vals:
                    if rs.get(k) is not None:
                        vals[k].append(rs[k])
            pt[cid] = {k: (float(np.percentile(v, L2.PLACEBO_Q)) if v else float("nan")) for k, v in vals.items()}
        res[era] = {"res": r, "pq": pq, "pt": pt, "frac": frac, "secs": round(time.time() - t0)}
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


def load_industry_returns() -> tuple[pd.DataFrame, dict[str, str]]:
    """TOPIX 1000 的 927 只 → 東証业种的月度相对收益（supply_chain_study 同一口径），2005-10〜END；{票: 业种}。"""
    from qbreak import sector_leadlag as SL
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    allo = {**load_universe(universe("JP", "broad"), d21), **load_universe(W.tickers(W.load()), d21)}
    CC, _ = SL.industry_returns(allo, s33)
    M = SC.monthly(CC)
    return M[(M.index >= pd.Timestamp("2005-10-31")) & (M.index <= pd.Timestamp(END))], s33


def fmt_ic(r: dict) -> str:
    s = (f"IC {r['ic']:+.3f}（t {r['t']}）；两半 {r['ic_H1']:+.3f} / {r['ic_H2']:+.3f}；三分组 最好 − 最差 {r['spread']}%（t {r['spread_t']}），命中率 {r['hit']}%")
    if "placebo_p" in r:
        s += f"；对照 t 的 95% 分位 {r['placebo_t95']}、经验 p {r['placebo_p']}"
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报结构（暴露）、物价覆盖与信号的相关（不看任何收益）")
    ap.add_argument("--skip-stock", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    Mret, s33 = load_industry_returns()
    inds = list(Mret.columns)
    cs = [j for j in inds if j not in BENEFIT]
    ex = load_exposures(inds)
    hits = hit_sets(ex)
    P = pd.DataFrame({k: cgpi(c) for k, c in SHOCK_CGPI.items()})
    sig = {w: signals(Mret, P, ex, w) for w in (1, 3)}
    if a.check:
        print(f"业种 {len(inds)} 个（横截面 {len(cs)} 个：去掉 {'、'.join(b for b in BENEFIT if b in inds)}）；月度 {Mret.index[0].date()}〜{Mret.index[-1].date()}"
              f"（{len(Mret)} 个月）；物价 {P.index.min().date()}〜{P.index.max().date()}，缺月 {int(P.isna().sum().sum())}")
        for k in SHOCKS:
            d = pd.Series(ex["direct"][k]).sort_values(ascending=False).head(6)
            n = pd.Series(ex["indirect"][k]).sort_values(ascending=False).head(6)
            print(f"  {k} {SHOCKS[k]}：直接 " + "、".join(f"{i} {v * 100:.1f}%" for i, v in d.items()) + "｜间接 " + "、".join(f"{i} {v * 100:.1f}%" for i, v in n.items()))
            print(f"     T4 直接受影响的业种：{'、'.join(hits[k])}")
        from qbreak.config import universe
        n225 = [t for t in s33 if t in set(universe("JP", "broad"))]
        hit_all = set().union(*hits.values())
        print(f"  日経225 里 T4 可能去掉的票（任一种原材料的直接受影响业种）：{sum(1 for t in n225 if s33[t] in hit_all)} / {len(n225)}")
        for w in (1, 3):
            D, I, IE = sig[w]["DIR"][cs], sig[w]["IND"][cs], sig[w]["IND_E"][cs]
            c = [np.corrcoef(D.loc[t], I.loc[t])[0, 1] for t in D.index if D.loc[t].notna().all() and D.loc[t].std() > 0 and I.loc[t].std() > 0]
            ce = [np.corrcoef(I.loc[t], IE.loc[t])[0, 1] for t in I.index if I.loc[t].notna().all() and I.loc[t].std() > 0 and IE.loc[t].std() > 0]
            print(f"  w={w}：DIR 与 IND 的横截面相关 中位 {np.nanmedian(c):.2f}；IND 与能源部分 IND_E 的相关 中位 {np.nanmedian(ce):.2f}")
        Zs = shock_z(P, pd.date_range("1990-01-31", END, freq="ME"))
        big = (Zs.abs() >= Z_BIG).where(Zs.notna())
        print("  |z| ≥ 1.28 的月份比例（1992〜）：" + "、".join(f"{k} {big[k].mean() * 100:.0f}%" for k in SHOCKS)
              + "；按月份最多的：" + "、".join(f"{k} {int(big[k].groupby(big.index.month).mean().idxmax())} 月 {big[k].groupby(big.index.month).mean().max() * 100:.0f}%" for k in SHOCKS))
        return 0
    say(f"# 间接影响的传导时间：直接 vs 间接受原材料影响的行业（{pd.Timestamp.today().date()}；git {git_info()}）")
    say("规则见 scripts/transmit_study.py 开头（先提交后运行）。横截面 = 24 个使用方业种。")
    start = pd.Timestamp(START)
    mon = Mret.index[Mret.index >= start]
    Y3 = SC.ahead(Mret, 3).reindex(mon)[cs]
    res = {"git": git_info(), "hits": hits}
    # T1
    r1 = ic_test((-sig[3]["IND"]).reindex(mon)[cs], Y3, 3, 3)
    r1d = ic_test((-sig[3]["DIR"]).reindex(mon)[cs], Y3, 3, 3, placebo=False)
    r1e = ic_test((-sig[3]["IND_E"]).reindex(mon)[cs], Y3, 3, 3, placebo=False)
    r1o = ic_test((-sig[3]["IND_O"]).reindex(mon)[cs], Y3, 3, 3, placebo=False)
    pr1 = paired(r1["_series"], r1d["_series"], 4)
    f1 = ic_effective(r1)
    stronger = pr1["diff"] is not None and pr1["diff"] > 0 and pr1["t"] is not None and pr1["t"] >= T_PAIR
    other_pos = r1o["ic"] is not None and r1o["ic"] > 0
    verdict1 = ("间接传导成立" if (not f1 and stronger and other_pos) else
                "只靠能源部分：与 theme_study 已见的能源轮动一致（不算新证据）" if (not f1 and stronger) else
                "原材料信号有预测力，但间接不比直接慢" if not f1 else "无效")
    res["T1"] = {"ind": {k: v for k, v in r1.items() if k != "_series"}, "dir": {k: v for k, v in r1d.items() if k != "_series"},
                 "ind_e": {k: v for k, v in r1e.items() if k != "_series"}, "ind_o": {k: v for k, v in r1o.items() if k != "_series"},
                 "pair": pr1, "fails": f1, "verdict": verdict1}
    say("\n## T1（主）：−IND（w = 3）→ 之后 3 个月的行业相对收益（24 业种）")
    say(f"- −IND：{fmt_ic(r1)}")
    say(f"- −DIR（直接，同一检验）：{fmt_ic(r1d)}；配对差 IC(−IND) − IC(−DIR) = {pr1['diff']}（t {pr1['t']}）")
    say(f"- 拆开：只有能源 −IND_E {fmt_ic(r1e)}；其余三种 −IND_O {fmt_ic(r1o)}")
    say(f"- 判定：{'有效' if not f1 else '无效：' + '；'.join(f1)} → **{verdict1}**")
    # T2
    D1, I1 = sig[1]["DIR"].reindex(Mret.index)[cs], sig[1]["IND"].reindex(Mret.index)[cs]
    c2 = fm_lag_coefs(D1, I1, Mret[cs])
    s2 = t2_stat(c2, start)
    pl = t2_placebo(D1, I1, Mret[cs], start, s2["ind"]["t"])
    f2 = []
    if not (s2["ind"]["t"] is not None and s2["ind"]["t"] <= -T_MIN and s2["ind"]["sum"] < 0):
        f2.append(f"IND 之和 {s2['ind']['sum']}（t {s2['ind']['t']}）不够负")
    if not (s2["ind"]["H1"] is not None and s2["ind"]["H1"] < 0 and s2["ind"]["H2"] is not None and s2["ind"]["H2"] < 0):
        f2.append(f"两半 {s2['ind']['H1']} / {s2['ind']['H2']} 不都 < 0")
    if not (pl["p"] is not None and pl["p"] < P_MAX):
        f2.append(f"对照经验 p {pl['p']} ≥ {P_MAX}")
    if not (s2["pair"]["diff"] is not None and s2["pair"]["diff"] < 0 and s2["pair"]["t"] is not None and s2["pair"]["t"] <= -T_PAIR):
        f2.append(f"不比 DIR 更负（配对差 {s2['pair']['diff']}，t {s2['pair']['t']}）")
    res["T2"] = {**s2, "placebo": pl, "fails": f2}
    say("\n## T2（传导时间）：第 h 个月的相对收益 ~ 标准化 DIR + IND（w = 1），Fama–MacBeth（系数 = 每 1 个标准差的 %；h = −1 价格变动月、0 公布月）")
    say("| h（月） | " + " | ".join(str(h) for h in T2_H) + " |")
    say("|---|" + "---|" * len(T2_H))
    for cc in ("dir", "ind"):
        say(f"| {cc.upper()} | " + " | ".join(f"{s2['profile'][cc][h]:+.3f}" for h in T2_H) + " |")
    say(f"- h = 2〜6 之和：IND {s2['ind']['sum']:+.3f}（t {s2['ind']['t']}；两半 {s2['ind']['H1']} / {s2['ind']['H2']}）；DIR {s2['dir']['sum']:+.3f}（t {s2['dir']['t']}）；"
        f"配对差 {s2['pair']['diff']}（t {s2['pair']['t']}）；对照（{pl['n']} 种错开）t 的 5% 分位 {pl['t05']}、经验 p {pl['p']}")
    O1 = sig[1]["IND_O"].reindex(Mret.index)[cs]
    so = sums(fm_lag_coefs(D1, O1, Mret[cs], hs=T2_SUM))["ind"]
    so = SC.ic_stats(so[so.index >= start], 5)
    energy_only2 = not f2 and not (so["ic"] is not None and so["ic"] < 0)
    verdict2 = ("只靠能源部分：与 theme_study 已见的能源轮动一致（不算新证据）" if energy_only2 else
                "间接行业反应更晚（成立）" if not f2 else "不成立")
    res["T2"].update({"ind_o_sum": so, "verdict": verdict2})
    say(f"- 另报：IND 换成只有其余三种的 IND_O：h = 2〜6 之和 {so['ic']}（t {so['t']}）")
    say(f"- 判定：{verdict2}" + ("" if not f2 else "：" + "；".join(f2)))
    # T3
    r3 = ic_test(sig[3]["PROP"].reindex(mon)[cs], Y3, 3, 3)
    f3 = ic_effective(r3)
    res["T3"] = {"prop": {k: v for k, v in r3.items() if k != "_series"}, "fails": f3}
    say("\n## T3（次）：PROP（直接受影响行业过去 3 个月的反应 × 间接暴露）→ 之后 3 个月")
    say(f"- {fmt_ic(r3)}")
    say(f"- 判定：{'有效' if not f3 else '无效：' + '；'.join(f3)}（只有 T1 有效时才一起算行业层面的结论）")
    write_out(res)
    # T4 / T5
    if not a.skip_stock:
        import leap2_common as L2
        mz = pd.date_range("1990-01-31", END, freq="ME")
        Zs = shock_z(P, mz)
        IND3 = signals(pd.DataFrame(0.0, index=mz, columns=inds), P, ex, 3)["IND"][cs]
        W = stock_windows(s33, Zs, IND3, hits)
        say("\n## T4 / T5（个股：日経225 的突破，现行 = S0C2 + W2；Z / E 去掉休市假行）")
        say("| 窗口 | 方案 | 组合 年化 / 回撤 / Calmar · 个股笔数 每笔 / 胜率 | 保留的信号 | 对照 95% 分位：股票 × 周（胜率 / 每笔） | 时间错开（胜率 / 每笔） |")
        say("|---|---|---|---|---|---|")
        for era in ("Z", "E", "J"):
            for k, r in W[era]["res"].items():
                s = r[era]
                q, qt = W[era]["pq"].get(k), W[era]["pt"].get(k)
                say(f"| {era} | {k} | {s.get('cagr')}% / {s.get('dd')}% / {s.get('calmar')} · {s.get('n')} 笔 {s.get('mean')}% / {s.get('win')}% | "
                    f"{W[era]['frac'].get(k, 1) * 100:.0f}% | " + (f"{q['win']:.1f}% / {q['mean']:+.2f}%" if q else "—") + " | "
                    + (f"{qt['win']:.1f}% / {qt['mean']:+.2f}%" if qt else "—") + " |")
        base = {e: W[e]["res"]["现行"][e] for e in ("Z", "E", "J")}
        for cid in ("T4", "T5"):
            cand = {e: W[e]["res"][cid][e] for e in ("Z", "E", "J")}
            fi = L2.improve_fails(cand, base)
            fp = []
            for e in ("Z", "E", "J"):
                for nm, q in (("股票 × 周", W[e]["pq"][cid]), ("时间错开", W[e]["pt"][cid])):
                    if not (L2.is_finite(cand[e].get("win")) and cand[e]["win"] > q["win"] and L2.is_finite(cand[e].get("mean")) and cand[e]["mean"] > q["mean"]):
                        fp.append(f"{e} {nm}对照没过")
            res[cid] = {"improve_fails": fi, "placebo_fails": fp,
                        "windows": {e: {k: {w: v for w, v in r.items() if not str(w).startswith("_")} for k, r in W[e]["res"].items()} for e in W},
                        "placebo": {e: {"lottery": W[e]["pq"][cid], "shift": W[e]["pt"][cid]} for e in W}, "frac": {e: W[e]["frac"][cid] for e in W}}
            say(f"- {cid}：{'选股改进成立' if not (fi or fp) else '不成立：' + '；'.join(fi + fp)}")
    say("\n## 结论（事先规则）")
    ind_level = res["T1"]["verdict"]
    t3_note = "；T3 也有效" if (not res["T1"]["fails"] and not res["T3"]["fails"]) else ""
    say(f"- 行业层面：{ind_level}{t3_note}；T2 {res['T2']['verdict']}"
        + ("→ 提议日报加「间接成本压力」显示（用户确认）" if ind_level == "间接传导成立" else "") + "。")
    if not a.skip_stock:
        ok = [k for k in ("T4", "T5") if not (res[k]["improve_fails"] or res[k]["placebo_fails"])]
        say(f"- 个股层面：{('、'.join(ok) + ' 过 → 提议前向记录（用户确认）') if ok else 'T4 / T5 都不过 → 模拟盘不变'}。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "transmit_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
