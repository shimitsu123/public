"""combo3_common.py — 「选股第三轮：让 C 更稳」的两种学法与判定（2026-10-01 登记；规则写在 scripts/combo3_study.py 开头，
提交后不改、只运行一次）。这里只有不碰数据的部分（tests/test_combo3_study.py）：

  切法：把学习样本的日历年随机分成两组（按信号数尽量各半），重复 B 次 = B 种「两个学习年代」；
  CB 袋装 C：每种切法按 C 同一做法学一份规则（scripts/combo_all_common.fit_c），新信号由 B 份规则投票，过半数说跳过才跳过；
  CS 稳定选择 C：每个市场格里，B 种切法中「两组同号且 |ρ| ≥ 0.05」的次数占比 ≥ 0.6 的特征才入选（方向取多数），
     切点 / 门槛用全部学习样本，得到一份和 C 同样形式的规则（可以直接换进 qbreak/combo_c.py）。
  C 的其余做法（市场格、每组每格 ≥ 60 笔、切点三等分、门槛 = 学习样本分数的 1/3 分位）一律不动。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import combo_all_common as CA

SEED = 20261004
B_SPLITS = 50                  # 随机切法的次数
VOTE = 0.5                     # CB：B 份规则里说「跳过」的占比 ≥ 这个 → 跳过
PI_MIN = 0.6                   # CS：入选的次数占比门槛（稳定选择）


def year_splits(dates, n: int = B_SPLITS, seed: int = SEED) -> list[np.ndarray]:
    """日历年随机排序后依次放进信号较少的那一组（信号数尽量各半）→ n 个 0 / 1 数组（1 = 第一组）。"""
    yrs = pd.to_datetime(pd.Series(dates)).dt.year.to_numpy()
    if not len(yrs):
        return [np.zeros(0, int) for _ in range(n)]
    uy, cnt = np.unique(yrs, return_counts=True)
    cnt_of = dict(zip(uy, cnt))
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        a = b = 0
        ga = set()
        for y in rng.permutation(uy):
            if a < b or (a == b and rng.random() < 0.5):
                ga.add(y)
                a += cnt_of[y]
            else:
                b += cnt_of[y]
        out.append(np.isin(yrs, list(ga)).astype(int))
    return out


def _groups(T: pd.DataFrame, g: np.ndarray) -> list[pd.DataFrame]:
    return [T[g == 1], T[g == 0]]


# ───────────────────────── CB 袋装 C ─────────────────────────
def fit_bag(T: pd.DataFrame, n: int = B_SPLITS, seed: int = SEED) -> list[dict]:
    return [CA.fit_c(_groups(T, g)) for g in year_splits(T["date"], n, seed)] if len(T) else []


def bag_active(rules: list[dict]) -> float:
    """B 份规则里，至少有一格学出规则的占比。"""
    if not rules:
        return 0.0
    return float(np.mean([any(r is not None for r in rs.values()) for rs in rules]))


def apply_bag(rules: list[dict], X: pd.DataFrame, vote: float = VOTE) -> np.ndarray:
    """B 份规则各自判定（这一格没有规则 = 保留），说跳过的占比 ≥ vote → 跳过。"""
    if not len(X) or not rules:
        return np.ones(len(X), bool)
    skip = np.mean([~CA.apply_c(rs, X) for rs in rules], axis=0)
    return ~(skip >= vote)


# ───────────────────────── CS 稳定选择 C ─────────────────────────
def stability(T: pd.DataFrame, n: int = B_SPLITS, seed: int = SEED, feats=None) -> dict[int, dict[str, tuple[float, int]]]:
    """每个市场格：{特征: (按多数方向入选的次数占比, 多数方向)}（这一格某次切法里一组不到 60 笔 → 那一次算没入选）。"""
    feats = list(feats or CA.STOCK_FEATS)
    out: dict[int, dict[str, tuple[float, int]]] = {}
    if not len(T):
        return {k: {} for k in range(4)}
    cell = CA.cell_of(T)
    splits = year_splits(T["date"], n, seed)
    for k in range(4):
        pos = {f: 0 for f in feats}
        neg = {f: 0 for f in feats}
        m = cell == k
        for g in splits:
            a, b = T[m & (g == 1)], T[m & (g == 0)]
            if min(len(a), len(b)) < CA.CELL_MIN_N:
                continue
            for f, s in CA.select([a, b], feats, CA.MIN_RHO_C).items():
                (pos if s > 0 else neg)[f] += 1
        out[k] = {f: ((max(pos[f], neg[f]) / n), (1 if pos[f] >= neg[f] else -1)) for f in feats if pos[f] or neg[f]}
    return out


def fit_stable(T: pd.DataFrame, n: int = B_SPLITS, seed: int = SEED, pi: float = PI_MIN) -> dict:
    """稳定选择出的特征 → 和 C 同样形式的四格规则 {格: {sel, cut, thr} | None}。"""
    prof = stability(T, n, seed)
    rules: dict = {}
    cell = CA.cell_of(T) if len(T) else np.zeros(0, int)
    for k in range(4):
        sel = {f: s for f, (p, s) in (prof.get(k) or {}).items() if p >= pi}
        Tk = T[cell == k] if len(T) else T
        if not sel or len(Tk) < 2 * CA.CELL_MIN_N:
            rules[k] = None
            continue
        cut = CA.cuts(Tk, list(sel))
        rules[k] = {"sel": sel, "cut": cut, "thr": CA.threshold(CA.score(Tk, sel, cut)), "n": int(len(Tk))}
    return rules


def profile_text(prof: dict, k: int = 2, top: int = 8) -> str:
    items = sorted((prof.get(k) or {}).items(), key=lambda kv: -kv[1][0])[:top]
    return "、".join(f"{f}{'+' if s > 0 else '−'} {p:.0%}" for f, (p, s) in items) or "—"


# ───────────────────────── 判定（事先写定）─────────────────────────
def verdict(lens1: bool, lens2: bool) -> str:
    """两种检验（留一年代 D1〜D4b、逐年前推 F1〜F4）都过 = 通过；只过一种 = 方向一致（只记录）。"""
    if lens1 and lens2:
        return "通过"
    if lens1 or lens2:
        return "方向一致"
    return "不通过"
