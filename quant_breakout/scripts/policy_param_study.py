"""policy_param_study.py — 结合已实施的政策来调整以后的模型参数：先把政策事件表变成「每月的政策状态」（日银方向 / Fed 周期方向 /
最近的政策冲击方向），看现行方案的逐笔与各参数「该增还是该减」在不同政策状态下有没有稳定差别；再做只用过去数据的月度规则
（政策后手写防守 / 进攻、按政策冲击方向记忆卖点、按日银 × Fed 状态逐参数增减）在三个年代上一步一步往前走。
登记检验：规则先提交再运行一次，看到结果之后不改规则。（2026-09-30 用户：「进行结合对应的实施政策来优化以后的模型参数的研究」）

〇 已经知道的（不重复做）
  - 09-27 政策事件反应库 G1：强类别事件之后 5〜20 天受益 / 受损业种的价差 ≈ 0（W20 命中 47〜57%）、事先写死的市场方向 W20 命中 47%
    → 政策事件对「之后 20 天大盘 / 业种的方向」没有可预测的信息；只展示 + 前向记录。
  - 09-29 现行选股方案拆成每月 × 利率 / 国债 / 成交额：各参数增减度与宏观序列的相似处不超过循环平移的零分布；五个月度规则都不通过；
    「每笔平均」当目标会选出松的组合（笔数翻倍、回撤深），连偷看当月的上限都不如现行。
  - 09-26 / 09-27 跟时代调阈值、策略自己更新；09-28 联合调参 168 组：都不比定死、不比随机对照。
  这次新的一点：条件不是连续的宏观变量，而是「已经实施的政策」这种离散状态（日银在紧缩还是宽松、Fed 在加息周期还是降息周期、
  最近 120 天有没有负面 / 正面的政策冲击）；规则分两类：手写（政策方向 → 事先写死的防守 / 进攻参数，不学习）与学习（同一政策状态下
  过去的笔 → 参数；只学卖点或只动一档，避开 09-29 发现的「松组合」陷阱）。

一 政策状态（每月 m 用 m−1 月末以前已公开的事件：政策事件表 var/policy_events.csv 的 known_on ≤ m−1 月末；excluded = 1 的行不用；
  verified 为空的行也用 —— 日期都是官方日期，只是本容器没能取回页面）
  b(m) 日银方向 ∈ {tighten, ease}：最近一次 BOJ_CHANGE 的子类（2001 年以前没有事件 → ease；表里 2022-12 的 YCC 放宽按登记分类算 tighten）。
  f(m) Fed 周期 ∈ {hiking, easing}：最近一次 FED_TURN（first_hike → hiking、first_cut → easing；2001-01-03 以前 → hiking）。
  k(m) 政策冲击 ∈ {neg, pos, none}：强类别（BOJ_CHANGE / FED_TURN / TARIFF / SEMI_CTRL / TAX / MOF_FX）里 market_dir ≠ 0 的事件，
    known_on 在 m−1 月末之前 120 个日历日内（known_on > 月末 − 120 天 且 ≤ 月末）→ 最近一件的方向（−1 neg / +1 pos）；没有 → none。
    market_dir 是 G1 登记时事先写死的（日银紧缩 / Fed 首次加息 / 加关税 / 出口管制 / 增税 / 买日元介入 = −1，反向 = +1）。
  状态格 cell(m) = b × f（4 格）。安慰剂用的平移：同一年代内把标签序列整体循环平移 ≥ 24 个月（每个状态的月数不变、只换时点）。
二 参数、逐笔与账户（全部沿用 sel_monthly_study：8 参数 × 3 档 = 6,561 组、θ0 = 现行；快速逐笔按平仓月入账；账户 = 现行框架
  （S0C2 + 核心 + 牛熊分界 + 宏观 / 状态层）里只换买卖点参数，PARAMS_TD miss 必须 = 0；θ0 重建的买点必须与现行逐日逐票一致、
  θ0 重建账户必须与现行账户一致，否则停止）。
三 描述（三个年代；只描述）：每个状态变量（b / f / k）的每个状态：θ0 的笔数与每笔平均（年代内、样本内）、各参数 OAT 增减度
  （大档 − 小档；每档 ≥ 20 笔、买点参数笔数差 ≥ 10，与 sel_monthly 相同）；状态间的差 = 增减度的 max − min；
  零假设：标签在年代内循环平移 ≥ 24 个月（200 次）→ 每个参数「状态间差」的零分布；写定的读法：实际差 > 各自零分布 95 分位的参数个数，
  要 > 零分布里同样数出来的个数的 95 分位，才算「政策状态对参数方向有信息」。
四 候选（walk-forward：m 月的 θ 只用 m−1 月末以前的信息；起点 θ0）
  R1 手写·负面政策后防守：k(m) = neg → θ_def = 现行但 放量 ×2.0、W2 1.5、止损 5%、吊灯 k 2、最多 40 天；否则 θ0。
  R2 手写·正面政策后进攻：k(m) = pos → θ_att = 现行但 放量 ×1.2、止损 10%、吊灯 k 4、最多 90 天；否则 θ0。
  R3 手写·双向：neg → θ_def、pos → θ_att、none → θ0。
  R4 学习·按政策冲击方向记忆卖点：买点 = θ0；卖点在 27 组（止损 × 吊灯 × 持有）里选：过去（本年代月表里 < m）同一 k 状态的月份里
    平仓的笔（≥ 30 笔）每笔平均最好的一组，比上月的好不到 0.25 pp 不换（上月的组不够 30 笔 → 换成最好的；没有够的 → 沿用）。
    同一批买点 → 配对比较、不会选出松组合。
  R5 学习·按日银 × Fed 状态逐参数增减：过去（月表里 < m）同一 cell 的月份里平仓的笔 → 8 个参数各自 OAT（每档 ≥ 20 笔、
    买点参数笔数差 ≥ 10、最好那档比现行好 0.25 pp 以上才动）→ 拼成 θ；算不出 → 现行值。
五 对照：现行 θ0；每个候选的安慰剂 = 政策标签循环平移（≥ 24 个月，20 个种子；R1〜R4 平移 k、R5 平移 cell；只在 E、J 上跑）；
  上限 O1（作弊）= 每个 cell 用本年代全部月份（含未来）的样本内 OAT。
六 判定（全部满足才「通过」；运行前写定）
  a E、J 各自 Calmar ≥ 现行 + 0.02、最大回撤不比现行深 2 pp；Z ≥ 现行 − 0.02；
  b E + J 的 Calmar 差合计 > 该候选自己的平移安慰剂 20 个种子的差合计的 95 分位（政策标签的时点必须比随便平移的好）；
  c E、J 各自 ≥ 30 笔账户交易；PARAMS_TD miss = 0。
  多个通过：按 min(E, J 的 Calmar 提高) 取 1 个；「通过」= 提议（先前向记录；进模拟盘要用户另外确认）。没通过 → 模拟盘不变。
七 事前预期（运行前写）：G1 已说明政策事件对之后 20 天的方向没有信息 → R1〜R3 的差别主要来自参数本身而不是时点：R1 在 J
  （2018〜2019、2025 关税期）会少买、E 几乎不动；进攻参数（止损 10 / 吊灯 4 / 90 天）在 09-28 的横展开里单独都不比现行好；
  R4 / R5 的 bin 稀疏（E 的 tighten 只有 2006-10〜2008-10、J 的 neg 集中在关税期）→ 多数月份沿用 θ0 或追噪音；
  描述里状态间的参数方向差多半在平移零分布之内。通过约 5〜10%；最可能的结论 = 「政策状态下现行方案的逐笔有差别（描述），但变不成可用的参数规则」。
八 另报（只描述）：今天的政策状态与各候选下个月会用的 θ；每个年代各状态的月数与强类别事件数；各候选换了几次 / θ0 占比。
九 局限：只用日线、今天的日経225（幸存者偏差）、税前；月度粒度（月中的事件下个月才生效）；政策分类与 market_dir 写于 2026-09
  （事后知识，G1 已声明）；120 天窗口与 θ_def / θ_att 的档都是事先写死的一种取法，没有网格搜索；三个年代的政策事件数不同
  （关税只有 2018 年以后）；bin 里的笔数少 → 学习类候选大多沿用 θ0。
登记前的检查：tests/test_policy_param_study.py；QB_POL_SMOKE=1 只跑接线检查。输出 var/out/policy_param_study.md / .json。非投资建议。
"""
from __future__ import annotations

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
import bnf_adapt_study as A                                                  # noqa: E402  mon / mon_str
import sel_monthly_study as SM                                               # noqa: E402  网格 / 快速逐笔 / OAT / build
from qbreak import paths                                                     # noqa: E402

ERAS = SM.ERAS
STRONG = ("BOJ_CHANGE", "FED_TURN", "TARIFF", "SEMI_CTRL", "TAX", "MOF_FX")
SHOCK_DAYS = 120
BOJ0, FED0 = "ease", "hiking"
THETA_DEF = (60, 15.0, 2.0, 6, 1.5, 5.0, 2.0, 40)
THETA_ATT = (60, 15.0, 1.2, 6, 1.0, 10.0, 4.0, 90)
K0, K_DEF, K_ATT = SM.K0, SM.T_INDEX[THETA_DEF], SM.T_INDEX[THETA_ATT]
EXIT_IDX = np.array([SM.E_INDEX[SM.THETA0[:5]] * len(SM.EXITS) + xi for xi in range(len(SM.EXITS))])   # 买点 = θ0 的 27 组卖点
CANDS = {"R1": "手写：负面政策后 120 天用防守参数", "R2": "手写：正面政策后 120 天用进攻参数", "R3": "手写：双向",
         "R4": "学习：按政策冲击方向记忆卖点（27 组）", "R5": "学习：按日银 × Fed 状态逐参数增减（OAT）"}
LABEL_OF = {"R1": "shock", "R2": "shock", "R3": "shock", "R4": "shock", "R5": "cell"}
PLACEBO_SEEDS, SHIFT_MIN, NULL_DRAWS = 20, 24, 200
NULL_SEED_OF = {"boj": 1, "fed": 2, "shock": 3}
N_MIN, HYST = SM.N_MIN, SM.HYST
CAL_UP, DD_TOL, Z_TOL, MIN_TRADES = 0.02, 2.0, 0.02, 30
STATE_ZH = {"boj": "日银方向", "fed": "Fed 周期", "shock": "最近 120 天的政策冲击", "cell": "日银 × Fed"}
LAB_ZH = {"tighten": "紧缩", "ease": "宽松", "hiking": "加息周期", "easing": "降息周期", "neg": "负面", "pos": "正面", "none": "无"}
SMOKE = os.environ.get("QB_POL_SMOKE") == "1"
LINES: list[str] = []
mon, mon_str = A.mon, A.mon_str


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def lab_zh(lab: str) -> str:
    return " × ".join(LAB_ZH.get(x, x) for x in str(lab).split("/"))


# ───────────────────────── 政策状态（纯函数，有测试）─────────────────────────
def month_end(m: int) -> pd.Timestamp:
    return pd.Timestamp(year=m // 12, month=m % 12 + 1, day=1) + pd.offsets.MonthEnd(0)


def load_events(fp: Path | None = None) -> pd.DataFrame:
    """政策事件表 → excluded = 0 的行；known = known_on（空 → date_jst → date）；dir = market_dir（空 → 0）。"""
    fp = fp or (paths.PROJECT_ROOT / "var" / "policy_events.csv")
    df = pd.read_csv(fp, dtype=str, keep_default_na=False)
    df["excluded"] = pd.to_numeric(df["excluded"], errors="coerce").fillna(0).astype(int)
    df = df[df["excluded"] == 0].copy()
    known = df["known_on"].where(df["known_on"].str.len() > 0, df["date_jst"])
    known = known.where(known.str.len() > 0, df["date"])
    df["known"] = pd.to_datetime(known, errors="coerce")
    df["dir"] = pd.to_numeric(df["market_dir"], errors="coerce").fillna(0).astype(int)
    df["covert"] = pd.to_numeric(df["covert"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["known"]).sort_values(["known", "date", "id"], kind="stable").reset_index(drop=True)
    return df[["id", "category", "subtype", "dir", "known", "date", "covert"]]


def _cut(m: int) -> np.datetime64:
    return month_end(m - 1).to_datetime64()


def last_state(ev: pd.DataFrame, months, mapping: dict[str, str], initial: str) -> dict[int, str]:
    """每个月 m：known ≤ m−1 月末的最近一件事件的子类 → 状态；没有 → initial。"""
    ev = ev[ev["subtype"].isin(mapping)].sort_values("known", kind="stable")
    ks = ev["known"].to_numpy(dtype="datetime64[ns]")
    st = [mapping[s] for s in ev["subtype"]]
    out = {}
    for m in months:
        i = int(np.searchsorted(ks, _cut(int(m)), side="right"))
        out[int(m)] = st[i - 1] if i > 0 else initial
    return out


def boj_state(E: pd.DataFrame, months) -> dict[int, str]:
    return last_state(E[E["category"] == "BOJ_CHANGE"], months, {"tighten": "tighten", "ease": "ease"}, BOJ0)


def fed_state(E: pd.DataFrame, months) -> dict[int, str]:
    return last_state(E[E["category"] == "FED_TURN"], months, {"first_hike": "hiking", "first_cut": "easing"}, FED0)


def shock_state(E: pd.DataFrame, months, days: int = SHOCK_DAYS) -> dict[int, str]:
    """强类别里 market_dir ≠ 0 的事件：known 在 (m−1 月末 − days, m−1 月末] 内 → 最近一件的方向；没有 → none。"""
    ev = E[E["category"].isin(STRONG) & (E["dir"] != 0)].sort_values("known", kind="stable")
    ks = ev["known"].to_numpy(dtype="datetime64[ns]")
    ds = ev["dir"].to_numpy()
    out = {}
    for m in months:
        cut = _cut(int(m))
        hi = int(np.searchsorted(ks, cut, side="right"))
        lo = int(np.searchsorted(ks, cut - np.timedelta64(days, "D"), side="right"))
        out[int(m)] = "none" if hi <= lo else ("neg" if ds[hi - 1] < 0 else "pos")
    return out


def cell_state(boj: dict[int, str], fed: dict[int, str]) -> dict[int, str]:
    return {m: f"{boj[m]}/{fed[m]}" for m in boj if m in fed}


def all_states(E: pd.DataFrame, months) -> dict[str, dict[int, str]]:
    b, f = boj_state(E, months), fed_state(E, months)
    return {"boj": b, "fed": f, "shock": shock_state(E, months), "cell": cell_state(b, f)}


def shift_labels(labels: dict[int, str], a: int, b: int, k: int) -> dict[int, str]:
    """[a, b] 内的标签整体循环平移 k 个月（每个状态的月数不变）；[a, b] 外的不动。"""
    ms = list(range(a, b + 1))
    vals = [labels[m] for m in ms]
    k = k % len(ms) if ms else 0
    rolled = vals[-k:] + vals[:-k] if k else vals
    return {**labels, **dict(zip(ms, rolled))}


def shift_amount(rng: np.random.Generator, n: int) -> int:
    return int(rng.integers(SHIFT_MIN, n - SHIFT_MIN + 1)) if n > 2 * SHIFT_MIN else int(rng.integers(1, max(2, n)))


# ───────────────────────── 月度规则 ─────────────────────────
def hand_path(a: int, b: int, shock: dict[int, str], mode: str) -> dict[int, int]:
    """R1 def / R2 att / R3 both：k(m) → θ_def / θ_att / θ0。"""
    out = {}
    for m in range(a, b + 1):
        s = shock.get(m, "none")
        if s == "neg" and mode in ("def", "both"):
            out[m] = K_DEF
        elif s == "pos" and mode in ("att", "both"):
            out[m] = K_ATT
        else:
            out[m] = K0
    return out


def label_cols(months: np.ndarray, labels: dict[int, str], m: int, lab: str | None) -> np.ndarray:
    """月表里 < m 且标签 = lab 的列。"""
    return np.array([i for i, mm in enumerate(months) if mm < m and labels.get(int(mm)) == lab], int)


def fit_exit(S: np.ndarray, C: np.ndarray, cols: np.ndarray, prev: int, n_min: int = N_MIN, hyst: float = HYST) -> int:
    """R4：买点 = θ0，27 组卖点里每笔平均最好的（≥ n_min 笔）；prev 不够 n_min → 换成最好的（不套滞回）；没有够的 → prev；好不到 hyst → prev。"""
    if len(cols) == 0:
        return prev
    n = C[EXIT_IDX][:, cols].sum(axis=1)
    s = S[EXIT_IDX][:, cols].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        obj = np.where(n >= n_min, s / np.maximum(n, 1), -np.inf)
    if not np.isfinite(obj).any():
        return prev
    best = int(np.argmax(obj))
    pi = np.flatnonzero(EXIT_IDX == prev)
    if len(pi) and np.isfinite(obj[pi[0]]) and obj[best] - obj[pi[0]] < hyst:
        return prev
    return int(EXIT_IDX[best])


def exit_memory_path(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, labels: dict[int, str], start: int = K0) -> dict[int, int]:
    out, prev = {}, start
    for m in range(a, b + 1):
        prev = fit_exit(S, C, label_cols(months, labels, m, labels.get(m)), prev)
        out[m] = prev
    return out


def cell_oat_path(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, labels: dict[int, str]) -> dict[int, int]:
    """R5：过去同一 cell 的月份 → 8 个参数各自 OAT（sel_monthly.oat_month 同一规则）→ θ。"""
    out = {}
    for m in range(a, b + 1):
        vals = SM.oat_month(S, C, label_cols(months, labels, m, labels.get(m)))[0]
        out[m] = SM.T_INDEX[tuple(vals)]
    return out


def era_cols(months: np.ndarray, labels: dict[int, str], a: int, b: int, lab: str | None) -> np.ndarray:
    return np.array([i for i, mm in enumerate(months) if a <= mm <= b and labels.get(int(mm)) == lab], int)


def oracle_cell_path(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, labels: dict[int, str]) -> dict[int, int]:
    """上限（作弊）：每个 cell 用本年代 [a, b] 全部月份（含未来）的样本内 OAT。"""
    out, cache = {}, {}
    for m in range(a, b + 1):
        lab = labels.get(m)
        if lab not in cache:
            cache[lab] = SM.T_INDEX[tuple(SM.oat_month(S, C, era_cols(months, labels, a, b, lab))[0])]
        out[m] = cache[lab]
    return out


# ───────────────────────── 描述：状态下的逐笔与参数方向 ─────────────────────────
def state_table(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, labels: dict[int, str]) -> dict[str, dict]:
    """每个状态：月数、θ0 的笔数与每笔平均（样本内）、8 个参数的 OAT 增减度。"""
    out = {}
    labs = sorted({labels.get(int(mm)) for mm in months if a <= mm <= b} | {labels.get(m) for m in range(a, b + 1)}, key=str)
    for lab in labs:
        cols = era_cols(months, labels, a, b, lab)
        n0, s0 = float(C[K0, cols].sum()), float(S[K0, cols].sum())
        gains = SM.oat_month(S, C, cols)[1]
        out[str(lab)] = {"months": int(sum(1 for m in range(a, b + 1) if labels.get(m) == lab)), "n": int(n0),
                         "mean": (None if n0 < 1 else round(s0 / n0, 3)), "gains": [None if not np.isfinite(g) else round(float(g), 3) for g in gains]}
    return out


def state_gap(tab: dict[str, dict]) -> list[float]:
    """每个参数：状态间增减度的 max − min（有值的状态 < 2 个 → nan）。"""
    gaps = []
    for j in range(8):
        v = [t["gains"][j] for t in tab.values() if t["gains"][j] is not None]
        gaps.append(float(max(v) - min(v)) if len(v) >= 2 else np.nan)
    return gaps


def null_gaps(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, labels: dict[int, str], draws: int, seed: int) -> list[list[float]]:
    rng = np.random.default_rng(seed)
    n = b - a + 1
    return [state_gap(state_table(months, S, C, a, b, shift_labels(labels, a, b, shift_amount(rng, n)))) for _ in range(draws)]


def gap_test(actual: list[float], null: list[list[float]]) -> dict:
    """实际差 > 各自零分布 95 分位的参数个数 vs 零分布里同样数出来的个数的 95 分位。"""
    N = np.array(null, float)
    q95 = np.array([np.nanpercentile(N[:, j], 95) if np.isfinite(N[:, j]).any() else np.nan for j in range(8)])
    act = np.array(actual, float)
    n_act = int(np.sum(np.isfinite(act) & np.isfinite(q95) & (act > q95)))
    n_null = [int(np.sum(np.isfinite(row) & np.isfinite(q95) & (row > q95))) for row in N]
    n95 = float(np.percentile(n_null, 95)) if n_null else np.nan
    return {"n_params": n_act, "null_q95_count": n95, "q95": [None if not np.isfinite(x) else round(float(x), 3) for x in q95],
            "info": bool(np.isfinite(n95) and n_act > n95)}


# ───────────────────────── 判定 ─────────────────────────
def verdict(c: str, acct: dict[str, dict], acct0: dict[str, dict], pl_sums: list) -> tuple[str, list[str]]:
    f = []
    gain = 0.0
    for t in ("E", "J"):
        x, y = acct.get(t) or {}, acct0.get(t) or {}
        if None in (x.get("calmar"), y.get("calmar"), x.get("dd"), y.get("dd")):
            f.append(f"a {t} 账户没有值")
            continue
        if x["calmar"] < y["calmar"] + CAL_UP:
            f.append(f"a {t} Calmar {x['calmar']:.3f} < 现行 {y['calmar']:.3f} + {CAL_UP}")
        if x["dd"] < y["dd"] - DD_TOL:
            f.append(f"a {t} 回撤 {x['dd']:.2f}% 比现行 {y['dd']:.2f}% 深 {DD_TOL:.0f} pp 以上")
        gain += x["calmar"] - y["calmar"]
    xz, yz = acct.get("Z") or {}, acct0.get("Z") or {}
    if xz.get("calmar") is None or yz.get("calmar") is None:
        f.append("a Z 账户没有值")
    elif xz["calmar"] < yz["calmar"] - Z_TOL:
        f.append(f"a Z Calmar {xz['calmar']:.3f} < 现行 {yz['calmar']:.3f} − {Z_TOL}")
    sums = [v for v in pl_sums if v is not None and np.isfinite(v)]
    if not sums:
        f.append("b 安慰剂没有值")
    else:
        q95 = float(np.percentile(sums, 95))
        if not gain > q95:
            f.append(f"b E + J Calmar 差合计 {gain:+.3f} ≤ 平移安慰剂 95 分位 {q95:+.3f}")
    for t in ("E", "J"):
        n = (acct.get(t) or {}).get("n") or 0
        if n < MIN_TRADES:
            f.append(f"c {t} 只有 {n} 笔（< {MIN_TRADES}）")
    return ("通过" if not f else "不通过"), f


def cand_path(c: str, months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, states: dict[str, dict[int, str]]) -> dict[int, int]:
    if c == "R1":
        return hand_path(a, b, states["shock"], "def")
    if c == "R2":
        return hand_path(a, b, states["shock"], "att")
    if c == "R3":
        return hand_path(a, b, states["shock"], "both")
    if c == "R4":
        return exit_memory_path(months, S, C, a, b, states["shock"], K0)
    if c == "R5":
        return cell_oat_path(months, S, C, a, b, states["cell"])
    raise KeyError(c)


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import jq_study as JS
    import leap_confirm as LF
    import sell_confirm as SCF
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.config import ExecConfig, universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    assert (px.exit_chandelier_k, px.stop_loss_pct, px.max_hold_days, px.trailing_arm_pct, px.time_stop_days, px.atr_stop_mult) == (SM.CHAND[1], SM.STOP[1], SM.HOLD[1], 0, 0, 0), px
    assert not px.exit_on_macd_dead_cross and not px.exit_sar_flip, px
    assert (px.range_n, px.range_x_pct, px.vol_mult, px.max_distribution_days, px.min_weekly_vol_ratio, px.max_upper_shadow_ratio) == (60, 15.0, 1.5, 6, 1.0, SM.UPPER_SHADOW), px
    tp, trail = float(px.take_profit_pct), float(px.trailing_stop_pct)
    cx_min = float(px.climax_min_gain_pct) if px.exit_on_climax else None
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    exc = ExecConfig.for_market("JP", "tachibana")
    slip, gap = exc.slippage_pct / 100, float(exc.max_entry_gap_pct)
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/policy_param_study.py", "scripts/sel_monthly_study.py", "scripts/candle_portfolio.py",
                                 "qbreak/unified.py", "var/policy_events.csv"], capture_output=True, text=True, cwd=root).stdout.strip())
    today = pd.Timestamp.today().normalize()
    say(f"# 结合已实施的政策来调整以后的模型参数（登记检验，{today.date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/policy_param_study.py 开头（先提交后只跑一次）。政策状态来自 var/policy_events.csv（known_on ≤ 上月末）；参数网格、快速逐笔、账户机器沿用 sel_monthly_study。")
    say(f"θ0 = 现行 {SM.th_str(SM.THETA0)}；θ_def = {SM.th_str(THETA_DEF)}；θ_att = {SM.th_str(THETA_ATT)}；止盈 {tp:g}%、跟踪 {trail:g}%、"
        f"放量阴线离场 {'浮盈 ≥ ' + str(cx_min) + '%' if cx_min is not None else '关'}、滑点 {slip * 100:.2f}% × 2、手续费 {rt:.2f}%。")
    E = load_events()
    say(f"政策事件表：{len(E)} 行（excluded = 0）；强类别 market_dir ≠ 0 的事件 {int((E['category'].isin(STRONG) & (E['dir'] != 0)).sum())} 件"
        f"（负面 {int((E['category'].isin(STRONG) & (E['dir'] < 0)).sum())} / 正面 {int((E['category'].isin(STRONG) & (E['dir'] > 0)).sum())}）；"
        f"最近一件 known_on {E['known'].max().date()}。")
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    seeds = 2 if SMOKE else PLACEBO_SEEDS
    draws = 20 if SMOKE else NULL_DRAWS

    ctxs, F, COMP, TAB, WIN, KEEP, STATES = {}, {}, {}, {}, {}, {}, {}
    for era in ERAS:
        t1 = time.time()
        ctx = LF.context(era, names=smoke_names) if (SMOKE and era != "J") else LF.context(era)
        if SMOKE and era == "J":
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in set(smoke_names)]
        fa = LF.frames(ctx, p0)
        keep = LF.w2_keep(ctx, fa)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        comp = SM.components(ctx, fa, p0)
        bad = 0
        for t, df in fa.items():
            ref = df["entry"].to_numpy(bool) & np.asarray(keep[t], bool)
            bad += int((SM.entry_mask(comp[t], SM.THETA0[:5]) != ref).sum())
        if bad:
            raise RuntimeError(f"{era}：按 θ0 重建的买点与现行有 {bad} 处不一致 → 停止")
        days = pd.DatetimeIndex(ctx["days"])
        rows = SM.fwd_rows(fa, comp, slip, days, gap=gap)
        months, S, C = SM.month_table(rows, slip, rt, tp, trail, cx_min)
        ma, mb = mon(a), mon(b)
        all_m = sorted(set(int(x) for x in months) | set(range(ma, mb + 2)))
        STATES[era] = all_states(E, all_m)
        ctxs[era], F[era], COMP[era], TAB[era], WIN[era], KEEP[era] = ctx, fa, comp, (months, S, C), (a, b), keep
        say(f"- {era}（{a}〜{b}）：{len(fa)} 只；现行买点重建一致；候选行 {len(rows['entry']):,}、月表 {len(months)} 个月；{round(time.time() - t1)} s")

    # ── 一 年代 × 政策状态的月数 ──
    say("\n## 一、每个年代各政策状态的月数（m 月的状态 = m−1 月末已公开的事件）")
    say("| 年代 | 日银方向 | Fed 周期 | 最近 120 天的政策冲击 | 日银 × Fed |")
    say("|---|---|---|---|---|")
    MONTHS_BY: dict = {}
    for era in ERAS:
        ma, mb = mon(WIN[era][0]), mon(WIN[era][1])
        cells = []
        for key in ("boj", "fed", "shock", "cell"):
            cnt = pd.Series([STATES[era][key][m] for m in range(ma, mb + 1)]).value_counts()
            MONTHS_BY.setdefault(era, {})[key] = {str(k): int(v) for k, v in cnt.items()}
            cells.append("、".join(f"{lab_zh(k)} {v}" for k, v in cnt.items()))
        say(f"| {era} | " + " | ".join(cells) + " |")

    # ── 二 描述：状态下的逐笔与参数方向 ──
    say("\n## 二、政策状态下现行方案的逐笔与各参数的方向（样本内、只描述；增减度 = 大档 − 小档，pp / 笔；每档 ≥ 20 笔、买点参数笔数差 ≥ 10）")
    say("| 年代 · 状态变量 | 状态 | 月数 | θ0 笔数 / 每笔 | " + " | ".join(SM.PNAMES) + " |")
    say("|---|---|---|---|" + "---|" * 8)
    STAB: dict = {}
    GAPT: dict = {}
    for era in ERAS:
        months, S, C = TAB[era]
        ma, mb = mon(WIN[era][0]), mon(WIN[era][1])
        for key in ("boj", "fed", "shock"):
            tab = state_table(months, S, C, ma, mb, STATES[era][key])
            STAB.setdefault(era, {})[key] = tab
            for lab, t in tab.items():
                mean_txt = "—" if t["mean"] is None else f"{t['mean']:+.2f}"
                say(f"| {era} · {STATE_ZH[key]} | {lab_zh(lab)} | {t['months']} | {t['n']} / {mean_txt} | "
                    + " | ".join("—" if g is None else f"{g:+.2f}" for g in t["gains"]) + " |")
            gaps = state_gap(tab)
            nul = null_gaps(months, S, C, ma, mb, STATES[era][key], draws, seed=20260930 + NULL_SEED_OF[key])
            GAPT.setdefault(era, {})[key] = {"actual": [None if not np.isfinite(x) else round(x, 3) for x in gaps], **gap_test(gaps, nul)}
    say("零假设对照（标签在年代内循环平移 ≥ 24 个月，" + str(draws) + " 次）：实际「状态间差」超过各自零分布 95 分位的参数个数 vs 零分布里数出来的个数的 95 分位：")
    for era in ERAS:
        say(f"- {era}：" + "；".join(f"{STATE_ZH[key]} {GAPT[era][key]['n_params']} 个 vs {GAPT[era][key]['null_q95_count']:.0f}（{'有信息' if GAPT[era][key]['info'] else '不算'}）"
                                   for key in ("boj", "fed", "shock")))

    # ── 三 账户 ──
    PATH: dict[str, dict[str, dict[int, int]]] = {c: {} for c in CANDS}
    ACCT: dict[str, dict] = {}
    MISS: dict[str, int] = {}
    PL: dict[str, dict[str, list]] = {c: {} for c in CANDS}
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
            fr, td = SM.build(fa, comp, days, path, px)
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
        say(f"- {era} 现行账户 Calmar {r0[era].get('calmar')} vs θ0 重建 {rk0.get('calmar')} → {'一致' if same else '**不一致**'}")
        if not same and not SMOKE:
            raise RuntimeError(f"{era}：θ0 重建账户与现行不一致 → 停止")
        for c in CANDS:
            PATH[c][era] = cand_path(c, months, S, C, ma, mb + 1, STATES[era])       # 多算一个月 = 下个月会用的 θ（账户只用到 mb）
            ACCT[era][c] = acct_of({m: k for m, k in PATH[c][era].items() if m <= mb})
        ACCT[era]["上限"] = acct_of(oracle_cell_path(months, S, C, ma, mb, STATES[era]["cell"]))
        if era in ("E", "J"):
            rng = np.random.default_rng(20260930)
            for c in CANDS:
                PL[c][era] = []
                for s in range(seeds):
                    k = shift_amount(rng, mb - ma + 1)
                    st2 = dict(STATES[era])
                    st2[LABEL_OF[c]] = shift_labels(STATES[era][LABEL_OF[c]], ma, mb, k)
                    PL[c][era].append(acct_of(cand_path(c, months, S, C, ma, mb, st2)).get("calmar"))
        say(f"- {era} 账户算完：{round(time.time() - t1)} s")
    if any(MISS.values()):
        raise RuntimeError(f"PARAMS_TD miss ≠ 0：{MISS} → 停止")

    acct0 = {e: ACCT[e]["现行"] for e in ERAS}
    PLS: dict[str, list] = {}
    for c in CANDS:
        n = min(len(PL[c].get("E", [])), len(PL[c].get("J", [])))
        PLS[c] = [(PL[c]["E"][s] - acct0["E"]["calmar"] + PL[c]["J"][s] - acct0["J"]["calmar"]) if (PL[c]["E"][s] is not None and PL[c]["J"][s] is not None) else None
                  for s in range(n)]
    res = {}
    for c in CANDS:
        acct = {e: ACCT[e][c] for e in ERAS}
        lab, fails = verdict(c, acct, acct0, PLS[c])
        g = [acct[e]["calmar"] - acct0[e]["calmar"] for e in ("E", "J") if acct[e].get("calmar") is not None and acct0[e].get("calmar") is not None]
        res[c] = {"label": lab, "fails": fails, "gain": (min(g) if len(g) == 2 else None), "gain_sum": (sum(g) if len(g) == 2 else None),
                  "paths": {e: SM.path_summary(PATH[c][e], mon(WIN[e][0]), mon(WIN[e][1])) for e in ERAS}}
    passed = sorted([c for c in CANDS if res[c]["label"] == "通过"], key=lambda c: -res[c]["gain"])
    pick = passed[0] if passed else None
    fmt = lambda x, f="{:+.2f}": ("—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x))  # noqa: E731
    cell = lambda s: f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')} · {s.get('n') or 0} 笔 {fmt(s.get('mean'))}%"  # noqa: E731
    say("\n## 三、整个账户（年化 / 最大回撤 / Calmar · 个股笔数 每笔；现行框架里只换买卖点参数）")
    say("| 做法 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 | E + J Calmar 差合计 | 平移安慰剂差合计 中位 / 95 分位 |")
    say("|---|---|---|---|---|---|")
    say("| 现行 θ0 | " + " | ".join(cell(ACCT[e]["现行"]) for e in ERAS) + " | — | — |")
    for c in CANDS:
        v = [x for x in PLS[c] if x is not None]
        say(f"| {c} {CANDS[c]} | " + " | ".join(cell(ACCT[e][c]) for e in ERAS) + f" | {fmt(res[c]['gain_sum'], '{:+.3f}')} | "
            + (f"{np.median(v):+.3f} / {np.percentile(v, 95):+.3f}" if v else "—") + " |")
    say("| 上限（作弊：每个日银 × Fed 格用本年代全部月份的样本内 OAT） | " + " | ".join(cell(ACCT[e]["上限"]) for e in ERAS) + " | "
        + fmt(sum(ACCT[e]["上限"]["calmar"] - acct0[e]["calmar"] for e in ("E", "J")), "{:+.3f}") + " | — |")
    say("\n## 四、判定（事先写定：a E / J Calmar ≥ 现行 + 0.02、回撤不深 2 pp、Z ≥ 现行 − 0.02；b E + J 差合计 > 自己的平移安慰剂 95 分位；c E / J ≥ 30 笔）")
    for c in CANDS:
        r = res[c]
        say(f"- **{c} {CANDS[c]}**：{r['label']}" + ("" if not r["fails"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n**结论：{('按规则选 ' + pick + '（只是提议：先做前向记录，要进模拟盘要你另外确认）') if pick else '没有候选「通过」→ 模拟盘不变'}**")
    say("PARAMS_TD miss（要 = 0）：" + " / ".join(f"{e} {MISS.get(e, 0)}" for e in ERAS))

    say("\n## 五、各候选每月的 θ（换了几次、θ0 的月份占比、范围；只描述）")
    for c in CANDS:
        for e in ERAS:
            ps = res[c]["paths"][e]
            if "first" not in ps:
                continue
            rng_txt = "、".join(f"{SM.PNAMES[j]} {ps[k][0]:g}〜{ps[k][1]:g}" for j, k in enumerate(SM.PKEYS) if ps[k][0] != ps[k][1])
            say(f"- {c} {e}：换 {ps['changes']} 次、θ0 占 {ps['pct_theta0']:.0f}% 的月份；{rng_txt or '全程 = θ0'}")

    m_next = mon(today) + 1
    st_now = {key: STATES["J"][key].get(m_next) for key in ("boj", "fed", "shock", "cell")}
    say(f"\n## 六、今天（{today.date()}）的政策状态与下个月（{mon_str(m_next)}）各候选会用的 θ（只描述，不改模拟盘）")
    say("- 状态：" + "；".join(f"{STATE_ZH[k]} = {lab_zh(v) if v else '—'}" for k, v in st_now.items()))
    recent = E[(E["category"].isin(STRONG)) & (E["dir"] != 0) & (E["known"] > today - pd.Timedelta(days=SHOCK_DAYS)) & (E["known"] <= today)]
    say("- 最近 120 天的强类别事件：" + ("、".join(f"{r.id}（{'负面' if r.dir < 0 else '正面'}，公开 {r.known.date()}）" for r in recent.itertuples()) or "无"))
    NEXT = {}
    for c in CANDS:
        k = PATH[c]["J"].get(m_next)
        NEXT[c] = None if k is None else SM.THETAS[k]
        say(f"- {c}：{SM.th_str(NEXT[c])}" + ("（= 现行）" if k == K0 else ""))
    out = {"code": code, "dirty": dirty, "pick": pick, "result": res, "account": ACCT, "placebo": PL, "placebo_sum": PLS, "td_miss": MISS,
           "months_by_state": MONTHS_BY, "state_tables": STAB, "gap_test": GAPT, "theta_def": THETA_DEF, "theta_att": THETA_ATT, "theta0": SM.THETA0,
           "states": {e: {k: {mon_str(m): v for m, v in STATES[e][k].items() if mon(WIN[e][0]) <= m <= mon(WIN[e][1]) + 1} for k in STATES[e]} for e in ERAS},
           "paths": {c: {e: {mon_str(m): SM.THETAS[k] for m, k in PATH[c][e].items() if k is not None} for e in ERAS} for c in CANDS},
           "today": {"date": str(today.date()), "next_month": mon_str(m_next), "state": st_now, "recent": list(recent["id"]), "theta_next": NEXT},
           "n_events": int(len(E)), "elapsed_s": round(time.time() - t0)}
    say(f"\n代码版本 {code}{'（有未提交的改动）' if dirty else '（与提交的版本相同）'}；用时 {out['elapsed_s']} s。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / ("policy_param_study_smoke" if SMOKE else "policy_param_study")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
