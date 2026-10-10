"""earn_traj_data.py — 季度决算的轨迹（单季利润的形态）数据层；研究与判定规则在 scripts/earn_traj_study.py。

日本（主）：J-Quants 決算短信サマリー（全市场 2016-09 起；原始数据只在 var/cache/jquants/，不入库）
  → 每家公司每个单季的营业利润 OP 与销售额：同一会计年度（12 个月决算期）里 本期累计 − 上一期累计（1Q = 1Q 累计）；
  每个 (决算期末, 期间) 只用第一次开示的数字（之后的订正不改「当时知道的」）；连结与单体都有的公司只用连结；
  没有营业利润的公司（银行 / 保险等只报经常利润）不算。事件日 = 这一季累计数字第一次开示的日子（DiscDate）。
美国（横展开）：Yahoo 决算日历（qbreak/earnings_hist.py；现 S&P 500 成员；原始数据只在 var/cache/earnings_hist/）
  → 每季的 Reported EPS（本身就是单季；Yahoo 的口径多为调整后 EPS）；事件日 = 发表日（日本日期）。
连续性：日本按期末（CurPerEn）月份相隔 3 个月；美国按发表日相隔 45〜135 天；断开就重新数。
形态（事先写死；q0 = 这一季，q1 = 上一季 … q4 = 去年同一季，q5 = 去年同一季的上一季；6 季都连续且有值才算）：
  T1 亏损收窄（前两季亏、这一季还亏但亏损不到前两季最差的一半，且比去年同季好）：q1 < 0 ∧ q2 < 0 ∧ q0 < 0 ∧ q0 ≥ 0.5 × min(q1, q2) ∧ q0 > q4
  T2 扭亏为盈（前两季亏、这一季赚）：q1 < 0 ∧ q2 < 0 ∧ q0 > 0
  T3 盈转亏（前两季赚、这一季亏）：q1 > 0 ∧ q2 > 0 ∧ q0 < 0
  T4 亏损扩大（上一季亏、这一季亏得更多，且比去年同季差）：q1 < 0 ∧ q0 < 0 ∧ q0 < q1 ∧ q0 < q4
  T5 盈利恶化（连续两季同比减少 ≥ 20%）：q0, q1, q4, q5 > 0 ∧ q0 ≤ 0.8 × q4 ∧ q1 ≤ 0.8 × q5
  T6 盈利加速（同比增速这一季 ≥ +20% 且比上一季快）：q0, q1, q4, q5 > 0 ∧ q0 ÷ q4 ≥ 1.2 ∧ q0 ÷ q4 > q1 ÷ q5 > 1
  N  其余（6 季都有值、但不属于以上任何一种）；T1〜T6 互不重叠（T1 / T4 与 T2 / T3 的条件互斥，T5 / T6 都要求全部为正且方向相反）。
非投资建议。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

FS_RE = re.compile(r"^(1Q|2Q|3Q|FY)FinancialStatements_(Consolidated|NonConsolidated)_(JP|IFRS|US)$")
PER_N = {"1Q": 1, "2Q": 2, "3Q": 3, "FY": 4}
COLS = ["DiscDate", "DiscTime", "Code", "DocType", "CurPerType", "CurPerSt", "CurPerEn", "CurFYSt", "CurFYEn", "Sales", "OP"]
STATES = ("T1", "T2", "T3", "T4", "T5", "T6")
LABELS = {"T1": "亏损收窄（大亏 → 亏损变小）", "T2": "扭亏为盈", "T3": "盈转亏（赚 → 亏）", "T4": "亏损扩大",
          "T5": "盈利连续两季同比 −20% 以上", "T6": "盈利加速（同比 ≥ +20% 且加快）", "N": "其余（6 季都有值）"}
EXPECT = {"T1": +1, "T2": +1, "T3": -1, "T4": -1, "T5": -1, "T6": +1}      # 事先的方向：+ = 之后跑赢大盘
NARROW, DETER, ACCEL = 0.5, 0.8, 1.2


# ───────────────────────── 日本：J-Quants → 单季营业利润 ─────────────────────────
def load_jp_fins() -> pd.DataFrame:
    from qbreak import jq_data as JD
    path, _ = JD.DATASETS["fins"]
    d = JD.bulk_dir() / path.strip("/")
    files = sorted(d.glob("historical/*/*.csv.gz")) + sorted(d.glob("historical/*.csv.gz")) + sorted(d.glob("live/*.csv.gz"))
    return JD.read_bulk(files, COLS)


def _months(a: pd.Series, b: pd.Series) -> pd.Series:
    st, en = pd.to_datetime(a, errors="coerce"), pd.to_datetime(b, errors="coerce")
    return (en.dt.year - st.dt.year) * 12 + (en.dt.month - st.dt.month) + 1


def jp_quarters(F: pd.DataFrame) -> pd.DataFrame:
    """決算短信 → 每家公司每个单季一行：code, ticker, fye, per (1〜4), q_end, disc, op, sales（单季）。"""
    from qbreak import jquants as JQ
    F = F.copy()
    doc = F["DocType"].fillna("").astype(str)
    F = F[doc.str.match(FS_RE) & F["CurPerType"].isin(tuple(PER_N))].copy()
    F["disc"] = pd.to_datetime(F["DiscDate"], errors="coerce")
    F["per"] = F["CurPerType"].map(PER_N).astype(int)
    F["fy12"] = _months(F["CurFYSt"], F["CurFYEn"]).eq(12)
    for c in ("OP", "Sales"):
        F[c] = pd.to_numeric(F[c], errors="coerce")
    F = F[F["fy12"] & F["disc"].notna()]
    out = []
    for code, g in F.groupby("Code"):
        t = JQ.to_yf(code)
        if t is None:
            continue
        dts = g["DocType"].astype(str)
        if dts.str.contains("_Consolidated_").any():
            g = g[~dts.str.contains("_NonConsolidated_")]
        g = g.sort_values(["disc", "DiscTime"], kind="mergesort").drop_duplicates(["CurFYEn", "per"], keep="first")
        if g["OP"].isna().all():
            continue
        cum = {(r.CurFYEn, r.per): (r.OP, r.Sales, r.disc, r.CurPerEn) for r in g.itertuples(index=False)}
        for (fye, per), (op, sa, disc, pen) in cum.items():
            if per == 1:
                q_op, q_sa = op, sa
            else:
                prev = cum.get((fye, per - 1))
                if prev is None:
                    continue
                q_op = op - prev[0] if pd.notna(op) and pd.notna(prev[0]) else np.nan
                q_sa = sa - prev[1] if pd.notna(sa) and pd.notna(prev[1]) else np.nan
            out.append((str(code), t, str(fye), int(per), pd.to_datetime(pen, errors="coerce"), disc, q_op, q_sa))
    Q = pd.DataFrame(out, columns=["code", "ticker", "fye", "per", "q_end", "disc", "v", "sales"])
    Q = Q.dropna(subset=["q_end"]).sort_values(["ticker", "q_end"]).reset_index(drop=True)
    Q["ord"] = Q["q_end"].dt.year * 12 + Q["q_end"].dt.month
    return Q


# ───────────────────────── 美国：Yahoo → 每季 EPS ─────────────────────────
def us_quarters(E: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for t, df in E.items():
        if df is None or not len(df):
            continue
        d = df.dropna(subset=["eps_rep"]).sort_values("date")
        for r in d.itertuples(index=False):
            rows.append((t, pd.Timestamp(r.date), float(r.eps_rep)))
    Q = pd.DataFrame(rows, columns=["ticker", "disc", "v"]).drop_duplicates(["ticker", "disc"])
    return Q.sort_values(["ticker", "disc"]).reset_index(drop=True)


# ───────────────────────── 形态 ─────────────────────────
def _consecutive(Q: pd.DataFrame, market: str) -> np.ndarray:
    """这一行与同一只票的上一行是不是相邻的一季。"""
    same = Q["ticker"].eq(Q["ticker"].shift(1)).to_numpy()
    if market == "JP":
        gap = (Q["ord"] - Q["ord"].shift(1)).to_numpy()
        return same & (gap == 3)
    gap = (Q["disc"] - Q["disc"].shift(1)).dt.days.to_numpy()
    return same & (gap >= 45) & (gap <= 135)


def classify(q: np.ndarray) -> str | None:
    """q = [q0, q1, q2, q3, q4, q5]（这一季在前）→ 形态（T1〜T6 / N），有缺值 → None。"""
    if q.shape[0] < 6 or not np.all(np.isfinite(q)):
        return None
    q0, q1, q2, _q3, q4, q5 = q
    if q1 < 0 and q2 < 0 and q0 < 0 and q0 >= NARROW * min(q1, q2) and q0 > q4:
        return "T1"
    if q1 < 0 and q2 < 0 and q0 > 0:
        return "T2"
    if q1 > 0 and q2 > 0 and q0 < 0:
        return "T3"
    if q1 < 0 and q0 < 0 and q0 < q1 and q0 < q4:
        return "T4"
    if min(q0, q1, q4, q5) > 0:
        if q0 <= DETER * q4 and q1 <= DETER * q5:
            return "T5"
        g0, g1 = q0 / q4, q1 / q5
        if g0 >= ACCEL and g0 > g1 > 1:
            return "T6"
    return "N"


def states(Q: pd.DataFrame, market: str) -> pd.DataFrame:
    """每一季（事件）的形态：ticker, disc, state（T1〜T6 / N；6 季不连续或缺值 → 不出行）。"""
    Q = Q.reset_index(drop=True)
    cons = _consecutive(Q, market)
    v = Q["v"].to_numpy(float)
    run = np.zeros(len(Q), int)                                               # 连续了几季（含这一季）
    for i in range(len(Q)):
        run[i] = run[i - 1] + 1 if i and cons[i] else 1
    rows = []
    for i in np.where(run >= 6)[0]:
        st = classify(v[i - 5:i + 1][::-1])
        if st is not None:
            rows.append((Q.at[i, "ticker"], Q.at[i, "disc"], st))
    S = pd.DataFrame(rows, columns=["ticker", "disc", "state"])
    return S.sort_values(["disc", "ticker"]).reset_index(drop=True)


def latest_state(S: pd.DataFrame, sig: pd.DataFrame, max_age_days: int = 100) -> pd.Series:
    """信号表（ticker, sig_date）→ 信号日之前（严格早于）最近一次开示的形态；超过 max_age_days 天或没有 → 缺值。"""
    out = pd.Series(np.nan, index=sig.index, dtype=object)
    if not len(S):
        return out
    by = {t: g.sort_values("disc") for t, g in S.groupby("ticker")}
    for t, g in sig.groupby("ticker"):
        h = by.get(t)
        if h is None:
            continue
        d = h["disc"].to_numpy("datetime64[ns]")
        s = pd.to_datetime(g["sig_date"]).to_numpy("datetime64[ns]")
        k = np.searchsorted(d, s, side="left") - 1                             # 严格早于信号日
        ok = k >= 0
        age = np.where(ok, (s - d[np.clip(k, 0, None)]).astype("timedelta64[D]").astype(int), 10 ** 6)
        val = np.where(ok & (age <= max_age_days), h["state"].to_numpy(object)[np.clip(k, 0, None)], np.nan)
        out.loc[g.index] = val
    return out
