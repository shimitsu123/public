"""sector_leadlag.py — 行业之间的领先滞后：一个行业先涨跌，另一个行业隔一段时间也跟着涨跌？
（scripts/leadlag_study.py；2026-09-26 事先登记）

行业 = 東証 33 业种（剔除航空、陆运、仓储物流后 30 个；var/industry_s33.json，TOPIX 1000 里的 929 只）：
  成员等权的日对数收益 − 全部 929 只的平均（相对收益，%）；收盘→收盘 CC 与 开盘→收盘 OC 两种。
领先方（预测变量，日本交易日 D 收盘后、次日开盘前已知）：
  日本行业 A 过去 w 天的相对收益之和（w = 1 / 5 / 20）；
  美国行业 ETF 相对 SPY 的对数收益、截至美国日期 ≤ D 的最近 w 个美国交易日之和（美国 D 日收盘 = 日本 D+1 早上 5〜6 点，开盘前已知）。
被预测方（可交易：从 D+1 开盘算起）：
  「1」= D+1 开盘→收盘；「1-5」= D+1 开盘 → D+5 收盘；「6-20」= D+5 收盘 → D+20 收盘；Part B 用「1-10」（持有期约 11 天）。
t 值用 Newey–West（重叠窗口的自相关；滞后 = w + 窗口长度 − 1）。只用当时已知的数据。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

WINDOWS = (1, 5, 20)
TARGETS = {"1": (1, 1), "1-5": (1, 5), "6-20": (6, 20)}
B_TARGET = (1, 10)
MIN_MEMBERS, T_KEEP, EMB, MIN_TRAIN = 3, 2.0, 20, 500


# ── 收益 ──
def industry_returns(ohlc: dict[str, pd.DataFrame], s33: dict[str, str], min_members: int = MIN_MEMBERS
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(CC, OC)：日期 × 行业 的相对收益（%）。s33：{票: 業種}；成员 < min_members 的行业不要。"""
    cc = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in ohlc.items() if t in s33})
    oc = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0) / df["Open"].where(df["Open"] > 0)) * 100
                       for t, df in ohlc.items() if t in s33})
    cc, oc = cc.sort_index(), oc.reindex(cc.index)
    groups: dict[str, list[str]] = {}
    for t in cc.columns:
        groups.setdefault(s33[t], []).append(t)
    keep = {g: m for g, m in groups.items() if len(m) >= min_members}
    ucc, uoc = cc.mean(axis=1), oc.mean(axis=1)
    CC = pd.DataFrame({g: cc[m].mean(axis=1) - ucc for g, m in sorted(keep.items())})
    OC = pd.DataFrame({g: oc[m].mean(axis=1) - uoc for g, m in sorted(keep.items())})
    return CC, OC


def target(CC: pd.DataFrame, OC: pd.DataFrame, span: tuple[int, int]) -> pd.DataFrame:
    """D 那一行 = 之后第 a〜b 个交易日的相对收益之和；a = 1 时第一天用开盘→收盘（D+1 开盘成交，隔夜那段拿不到）。"""
    a, b = span
    out = pd.DataFrame(0.0, index=CC.index, columns=CC.columns)
    for k in range(a, b + 1):
        out = out + (OC if (k == 1) else CC).shift(-k)
    return out


def past(R: pd.DataFrame, w: int) -> pd.DataFrame:
    """D 那一行 = D−w+1〜D 的收益之和（D 收盘时已知）。"""
    return R.rolling(w, min_periods=w).sum()


def us_relative(etf: dict[str, pd.Series], spy: pd.Series, jp_days: pd.DatetimeIndex, w: int) -> pd.DataFrame:
    """日本交易日 D × ETF：美国日期 ≤ D 的最近 w 个美国交易日，ETF 相对 SPY 的对数收益之和（%）。"""
    out = {}
    ls = np.log(spy.dropna())
    for sym, s in etf.items():
        s = s.dropna()
        rel = (np.log(s).diff() - ls.diff().reindex(s.index)) * 100
        cum = rel.rolling(w, min_periods=w).sum().dropna()
        out[sym] = cum.reindex(cum.index.union(jp_days)).ffill().reindex(jp_days)
    return pd.DataFrame(out, index=jp_days)


# ── 统计 ──
def _winsor(a: np.ndarray, q: float = 0.01) -> np.ndarray:
    lo, hi = np.nanpercentile(a, [q * 100, 100 - q * 100])
    return np.clip(a, lo, hi)


def nw_t(x: np.ndarray, y: np.ndarray, lags: int) -> tuple[float, float, int]:
    """y ~ a + b·x（两边 1% / 99% 截尾）：斜率、Newey–West t、样本数。"""
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 60:
        return float("nan"), float("nan"), n
    xv, yv = _winsor(x[m]), _winsor(y[m])
    xc = xv - xv.mean()
    sxx = float(np.dot(xc, xc))
    if sxx <= 0:
        return 0.0, 0.0, n
    b = float(np.dot(xc, yv - yv.mean()) / sxx)
    u = (yv - yv.mean() - b * xc) * xc
    s = float(np.dot(u, u))
    for L in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - L / (lags + 1)) * float(np.dot(u[L:], u[:-L]))
    se = math.sqrt(max(s, 1e-300)) / sxx
    return b, b / se, n


def p_two(t: float) -> float:
    return float(math.erfc(abs(t) / math.sqrt(2))) if np.isfinite(t) else float("nan")


def hit_rate(x: np.ndarray, y: np.ndarray) -> float:
    """方向命中率：领先方的涨跌与之后被预测方的相对涨跌同号的比例（x = 0 的日子不算）。"""
    m = np.isfinite(x) & np.isfinite(y) & (x != 0) & (y != 0)
    return float(np.mean(np.sign(x[m]) == np.sign(y[m]))) if m.any() else float("nan")


def scan(family: str, P: dict[int, pd.DataFrame], T: dict[str, pd.DataFrame], halves: dict[str, tuple], own: str = "exclude"
         ) -> pd.DataFrame:
    """P：{w: 日期 × 领先方}；T：{目标名: 日期 × 行业}。own：exclude（领先方 ≠ 被预测方）/ only（只看自己）/ any。"""
    rows = []
    for tname, Tt in T.items():
        h = TARGETS[tname][1] - TARGETS[tname][0] + 1
        for w, Pw in P.items():
            lags = w + h - 1
            for hname, (a, b) in halves.items():
                sel = (Pw.index >= pd.Timestamp(a)) & (Pw.index <= pd.Timestamp(b))
                Xh, Yh = Pw[sel], Tt.reindex(Pw.index)[sel]
                for lead in Xh.columns:
                    x = Xh[lead].to_numpy(float)
                    for tgt in Yh.columns:
                        if (own == "exclude" and lead == tgt) or (own == "only" and lead != tgt):
                            continue
                        y = Yh[tgt].to_numpy(float)
                        bb, t, n = nw_t(x, y, lags)
                        rows.append((family, lead, tgt, w, tname, hname, bb, t, n, p_two(t), hit_rate(x, y)))
    return pd.DataFrame(rows, columns=["family", "lead", "target", "w", "tgt", "half", "slope", "t", "n", "p", "hit"])


def discoveries(S: pd.DataFrame, q: float) -> pd.DataFrame:
    """前半 BH（q）发现 → 后半同号且单侧 p < 0.05 = 复现。"""
    from .lag_factors import bh
    d = S.pivot_table(index=["family", "lead", "target", "w", "tgt"], columns="half", values=["slope", "t", "p", "n", "hit"]).reset_index()
    d.columns = ["_".join(str(c) for c in col).strip("_") for col in d.columns]
    d["found"] = bh(d["p_H1"].to_numpy(float), q)
    d["replicated"] = d["found"] & (np.sign(d["t_H2"]) == np.sign(d["t_H1"])) & (d["p_H2"] / 2 < 0.05)
    return d


# ── Part B：领先分（逐年滚动前推）──
def lead_fit(P: dict[int, pd.DataFrame], Y: pd.DataFrame, cut_pos: int, mode: str) -> dict:
    """训练 = 位置 < cut_pos − EMB（之后 1〜10 天的标签已结束）。每个（领先方, 被预测行业）：w 选训练期 |t| 最大的；|t| ≥ T_KEEP 才保留。
    mode：jp（领先方 = 其他行业）/ own（只用自己）/ us（美国 ETF）。返回 {被预测行业: [(领先方, w, 斜率, 均值, 标准差)]}。"""
    end = max(cut_pos - EMB, 0)
    h = B_TARGET[1] - B_TARGET[0] + 1
    Yt = Y.iloc[:end]
    model: dict[str, list] = {}
    leads = list(next(iter(P.values())).columns)
    for tgt in Y.columns:
        y = Yt[tgt].to_numpy(float)
        for lead in leads:
            if (mode == "jp" and lead == tgt) or (mode == "own" and lead != tgt):
                continue
            best = None
            for w, Pw in P.items():
                x = Pw[lead].iloc[:end].to_numpy(float)
                ok = np.isfinite(x) & np.isfinite(y)
                if ok.sum() < MIN_TRAIN:
                    continue
                mu, sd = float(np.mean(x[ok])), float(np.std(x[ok]))
                if sd <= 0:
                    continue
                b, t, _ = nw_t((x - mu) / sd, y, w + h - 1)
                if np.isfinite(t) and (best is None or abs(t) > abs(best[2]) + 1e-12):
                    best = (w, b, t, mu, sd)
            if best is not None and abs(best[2]) >= T_KEEP:
                model.setdefault(tgt, []).append((lead, best[0], best[1], best[3], best[4]))
    return model


def lead_score(model: dict, P: dict[int, pd.DataFrame], targets: list[str]) -> pd.DataFrame:
    idx = next(iter(P.values())).index
    out = pd.DataFrame(0.0, index=idx, columns=targets)
    for tgt, terms in model.items():
        if tgt not in out.columns:
            continue
        for lead, w, b, mu, sd in terms:
            out[tgt] += b * ((P[w][lead] - mu) / sd).fillna(0.0)
    return out


def lead_walk_forward(P: dict[int, pd.DataFrame], Y: pd.DataFrame, years: list[int], mode: str) -> tuple[pd.DataFrame, dict]:
    idx = Y.index
    P = {w: p.reindex(idx) for w, p in P.items()}             # 领先方与被预测方同一个日期轴（位置 = 训练期的切点）
    out = pd.DataFrame(np.nan, index=idx, columns=Y.columns)
    info = {}
    for y in years:
        cut = int(idx.searchsorted(pd.Timestamp(f"{y}-01-01")))
        sel = (idx >= pd.Timestamp(f"{y}-01-01")) & (idx < pd.Timestamp(f"{y + 1}-01-01"))
        if not sel.any():
            continue
        m = lead_fit(P, Y, cut, mode)
        out.loc[sel] = lead_score(m, P, list(Y.columns)).loc[sel].to_numpy()
        info[y] = {t: [(l, w) for l, w, *_ in v] for t, v in m.items()}
    return out, info
