"""combo2_common.py — 「选股第二轮：在 C 的基础上」的规则、统计与判定（2026-10-01 登记；规则写在 scripts/combo2_study.py 开头，
提交后不改、只运行一次）。这里只有不碰数据的部分（tests/test_combo2_study.py）：

  N3 逐年前推：每年只用「那一年 1 月 1 日之前 120 天为止」的信号、按 C 同一做法学（两个学习段 = 按日期切成前后两半）→ 用在那一年；
  N1 补回：W2 挡掉的突破里，同一折 C 规则分数 ≥ +2 的也买；
  N2 换掉：不要 W2，C 在全部突破上学（同一做法）；
  判定 F1〜F4（N3）、G1〜G4（N1 / N2）。C 的做法本身（选特征、切点、门槛、市场格）用 scripts/combo_all_common.py 的同一组函数。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import combo_all_common as CA

SEED = 20261003
GAP_DAYS = 120                 # N3：学习只用信号日 ≤ 那一年 1 月 1 日 − 120 天的信号（X6 最长持有 60 个交易日 → 结果都已知道）
RESCUE_MIN = 2                 # N1：W2 挡掉的突破，C 分数 ≥ +2（有利的票比不利的多 2 票以上）→ 也买
PLACEBO_N, ACCT_SEEDS = CA.PLACEBO_N, CA.ACCT_SEEDS

# 判定（事先写定）
F1_WIN, F1_MEAN = 2.0, 0.20    # N3 合并（有规则的年份）：胜率差 ≥ +2.0 pp、每笔差 ≥ +0.20 pp、且 > 随机 95 分位
F4_TOL, F4_DD, F4_SUM = 0.02, 2.0, 0.02   # N3 账户（E / J）：各 ≥ 现行 − 0.02、回撤不深 2 pp、两段合计 ≥ +0.02
G_DILUTE, G_WIN_DILUTE = 0.30, 3.0        # N1 / N2：每笔最多比现行低 0.30 pp、胜率最多低 3.0 pp
G_SUM = 0.03                              # N1 / N2 账户：三个年代合计 ≥ +0.03（各年代 ≥ 现行 − 0.02、回撤不深 2 pp）


# ───────────────────────── N3：逐年前推 ─────────────────────────
def halves(T: pd.DataFrame) -> list[pd.DataFrame]:
    """按信号日切成前后两半（中位数那天归前一半）= C 的「两个学习年代」。"""
    if not len(T):
        return [T, T]
    d = pd.to_datetime(T["date"])
    med = d.sort_values().iloc[(len(d) - 1) // 2]
    return [T[d <= med], T[d > med]]


def train_cut(year: int, gap_days: int = GAP_DAYS) -> pd.Timestamp:
    return pd.Timestamp(f"{year}-01-01") - pd.Timedelta(days=gap_days)


def forward_rules(T: pd.DataFrame, years, gap_days: int = GAP_DAYS) -> dict[int, dict]:
    """T = 有结果的信号（date、net、特征、n225_ma200、vix）→ {年: C 的四格规则}（只用 train_cut 之前的信号）。"""
    out = {}
    d = pd.to_datetime(T["date"])
    for y in years:
        tr = T[d <= train_cut(y, gap_days)]
        out[int(y)] = CA.fit_c(halves(tr))
    return out


def active(rules: dict | None) -> bool:
    return bool(rules) and any(r is not None for r in rules.values())


def apply_forward(rules_by_year: dict[int, dict], X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """每个信号用它那一年的规则 → (保留, 那一年有没有规则)。没有规则的年份 = 全部保留。"""
    keep = np.ones(len(X), bool)
    on = np.zeros(len(X), bool)
    if not len(X):
        return keep, on
    yr = pd.to_datetime(X["date"]).dt.year.to_numpy()
    for y in np.unique(yr):
        r = rules_by_year.get(int(y))
        if not active(r):
            continue
        m = yr == y
        keep[m] = CA.apply_c(r, X[m])
        on[m] = True
    return keep, on


def rule_features(rules: dict | None) -> str:
    if not active(rules):
        return "—"
    out = []
    for k, r in rules.items():
        if r is not None:
            out.append(f"格{k}：" + "、".join(f"{f}{'+' if s > 0 else '−'}" for f, s in r["sel"].items()) + (f"（门槛 {r['thr']:+.0f}）" if np.isfinite(r["thr"]) else ""))
    return "；".join(out)


# ───────────────────────── N1：补回 ─────────────────────────
def c_score(rules: dict, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """C 的分数与「这一格有没有规则」（没有 → 分数 NaN）。"""
    sc = np.full(len(X), np.nan)
    has = np.zeros(len(X), bool)
    if not len(X):
        return sc, has
    cell = CA.cell_of(X)
    for k, r in (rules or {}).items():
        m = cell == k
        if r is None or not m.any():
            continue
        sc[m] = CA.score(X[m], r["sel"], r["cut"])
        has[m] = True
    return sc, has


def rescue(rules: dict, X: pd.DataFrame, min_score: int = RESCUE_MIN) -> np.ndarray:
    sc, has = c_score(rules, X)
    with np.errstate(invalid="ignore"):
        return has & (sc >= min_score)


# ───────────────────────── 统计 ─────────────────────────
def stat(net) -> dict:
    x = np.asarray(net, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0, "win": np.nan, "mean": np.nan}
    return {"n": int(len(x)), "win": float((x > 0).mean() * 100), "mean": float(x.mean())}


def random_pick(tickers, weeks, k: int, rng) -> np.ndarray:
    """从候选里按「股票 × 周」抽签随机挑约 k 个（同一只票同一周一起进出）。"""
    n = len(tickers)
    if not n or k <= 0:
        return np.zeros(n, bool)
    return CA.lottery(tickers, weeks, min(1.0, k / n), rng)


def rescue_placebo(parts: list[tuple], n: int = PLACEBO_N, seed: int = SEED) -> float:
    """parts = [(候选的 net, tickers, weeks, 要挑的个数), …]（每个年代）→ 随机补回同样多的合并每笔的 95 分位。"""
    rng = np.random.default_rng(seed)
    out = np.full(n, np.nan)
    for b in range(n):
        xs = [np.asarray(net, float)[random_pick(tk, wk, k, rng)] for net, tk, wk, k in parts]
        x = np.concatenate(xs) if xs else np.zeros(0)
        if len(x):
            out[b] = x.mean()
    return float(np.nanpercentile(out, 95)) if np.isfinite(out).any() else np.nan


# ───────────────────────── 判定（事先写定）─────────────────────────
def _fin(x) -> bool:
    return x is not None and np.isfinite(x)


def f1(pooled: dict, q95: float) -> bool:
    return (_fin(pooled.get("dwin")) and pooled["dwin"] >= F1_WIN and _fin(pooled.get("dmean")) and pooled["dmean"] >= F1_MEAN
            and _fin(q95) and pooled["dmean"] > q95)


def f2(h1: dict, h2: dict) -> bool:
    return _fin(h1.get("dmean")) and _fin(h2.get("dmean")) and h1["dmean"] >= 0 and h2["dmean"] >= 0


def f3(other: dict) -> bool:
    return all(_fin(other[s].get("dmean")) and _fin(other[s].get("dwin")) and other[s]["dmean"] >= 0 and other[s]["dwin"] >= 0
               for s in ("W", "Jx"))


def acct_ok(acct: dict, base: dict, eras, tol: float, dd: float, need: float) -> bool:
    tot = 0.0
    for e in eras:
        a, b = acct.get(e) or {}, base.get(e) or {}
        if a.get("calmar") is None or b.get("calmar") is None:
            return False
        if a["calmar"] < b["calmar"] - tol or a["dd"] < b["dd"] - dd:
            return False
        tot += a["calmar"] - b["calmar"]
    return tot >= need


def acct_sum(acct: dict, base: dict, eras) -> float:
    return float(sum(acct[e]["calmar"] - base[e]["calmar"] for e in eras))


def g1_rescue(per_era: dict) -> bool:
    """N1 每个年代：补回的那几笔每笔 > 0（这个年代没有补回 → 不变，算过）。"""
    return all(per_era[e]["n"] == 0 or (_fin(per_era[e]["mean"]) and per_era[e]["mean"] > 0) for e in CA.ERAS)


def g2_rescue(pooled_r: dict, pooled_b: dict, q95: float) -> bool:
    """N1 合并：补回的每笔 ≥ 现行买的每笔 − 0.30 pp，且 > 随机补回同样多的 95 分位。"""
    return (pooled_r["n"] > 0 and _fin(pooled_r["mean"]) and _fin(pooled_b["mean"]) and pooled_r["mean"] >= pooled_b["mean"] - G_DILUTE
            and _fin(q95) and pooled_r["mean"] > q95)


def g3_rescue(other: dict) -> bool:
    return all(other[s]["n"] == 0 or (_fin(other[s]["mean"]) and other[s]["mean"] >= 0) for s in ("W", "Jx"))


def g1_replace(per_era_t: dict, per_era_b: dict) -> bool:
    """N2 每个年代：买的那一组每笔 ≥ 现行 − 0.30 pp、胜率 ≥ 现行 − 3.0 pp。"""
    for e in CA.ERAS:
        t, b = per_era_t[e], per_era_b[e]
        if not (_fin(t["mean"]) and _fin(b["mean"]) and t["mean"] >= b["mean"] - G_DILUTE and t["win"] >= b["win"] - G_WIN_DILUTE):
            return False
    return True


def g2_replace(pooled: dict, q95: float) -> bool:
    """N2 合并：C2 保留 − 全部突破 的每笔差 ≥ +0.20 pp 且 > 随机 95 分位（C2 本身要有用）。"""
    return _fin(pooled.get("dmean")) and pooled["dmean"] >= F1_MEAN and _fin(q95) and pooled["dmean"] > q95


def g3_replace(other_t: dict, other_b: dict) -> bool:
    return all(_fin(other_t[s]["mean"]) and _fin(other_b[s]["mean"]) and other_t[s]["mean"] >= other_b[s]["mean"] - G_DILUTE
               for s in ("W", "Jx"))


def verdict(sig_ok: list[bool], acct_a: bool, acct_b: bool) -> str:
    if all(sig_ok) and acct_a and acct_b:
        return "通过"
    if all(sig_ok):
        return "方向一致"
    return "不通过"
