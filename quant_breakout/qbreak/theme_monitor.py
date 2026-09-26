"""theme_monitor.py — 日报用：主题 / 東証业种的近 1 / 3 个月强弱、影响度（与日経225 的同步程度）、新出现的联动
（只作展示，不改交易；2026-09-26 用户要求「日报加主题标签和近 3 个月强弱」「新出现的行业都要和现有行业做关联对比」
「随着时间和科技的发展，每个行业的影响度也要考虑」）。

口径（与 theme_study / supply_chain_study 相同）：日对数收益（%）；组 = 東証 30 业种（var/industry_s33.json）+ 12 个主题（qbreak/themes.py），
组的日收益 = 成员等权平均（有行情的成员 < 3 只的日子缺值）；相对收益 = 组 − TOPIX 1000 929 只的平均。
  - 强弱：近 21 / 63 个交易日相对收益之和（约 1 / 3 个月，%）；主题之间、业种之间分别排名。
  - 影响度：组的日收益与日経225 日收益的相关系数平方（R²，近 250 个交易日；「日経每天的涨跌有多少和这一组同步」）。
    历年的值由 scripts/theme_influence.py 算好存在 var/theme_influence.json（每年更新一次）。
  - 新出现的联动（近 126 个交易日 vs 之前 250 个交易日，股票用相对收益）：
      ① 每只股票现在最像的「不是自己所属」的业种 / 主题：相关系数 ≥ 0.50、且比之前高 ≥ 0.25；
      ② 至少和一只股票「新连上」（两两相关现在 ≥ 0.55、之前 < 0.30）的股票，按现在的相关做平均连接聚类（群内平均相关 ≥ 0.55），
         ≥ 4 只、且之前的群内平均相关 < 0.30 的群 → 候选新主题（平均连接不会像「连通块」那样被大盘风格轮动串成几百只的大群）；
         同时列出这个群和现有业种 / 主题的相关（最像哪几个）与成员分布 = 「和现有行业的关联对比」。
这些都是描述，不是预测：2026-09-26 的研究（theme_study 4576e61 / 6711770）里，主题动量用来挑买点没有通过。
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from . import themes as TH

WIN = {"r1m": 21, "r3m": 63}
MIN_FRAC = 0.7
INF_WIN = 250
RECENT, PRIOR = 126, 250
LINK_MIN, LINK_RISE = 0.50, 0.25
PAIR_NEW, PAIR_OLD, MIN_CLUSTER = 0.55, 0.30, 4
TOP_LINKS, TOP_CLUSTERS, TOP_MEMBERS = 15, 5, 12


def log_returns(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """{票: OHLCV} → 日期 × 票 的日对数收益（%）。"""
    return pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in data.items()}).sort_index()


def group_members(s33: dict[str, str], tickers) -> dict[str, list[str]]:
    """{组: [票]}：東証业种（组名 = 业种名）+ 主题（T1…）；只保留有行情的票。s33 的键 = 「1234.T」。"""
    have = set(tickers)
    out: dict[str, list[str]] = {}
    for t, g in s33.items():
        if t in have:
            out.setdefault(g, []).append(t)
    for code, k in TH.members().items():
        if f"{code}.T" in have:
            out.setdefault(k, []).append(f"{code}.T")
    return out


def group_panel(lr: pd.DataFrame, s33: dict[str, str], min_members: int = TH.MIN_MEMBERS) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """(组的日收益, 组的日相对收益, 市场平均)。市场平均 = s33 里的票（TOPIX 1000）等权。"""
    mkt = lr[[t for t in s33 if t in lr.columns]].mean(axis=1)
    raw = {}
    for g, ts in group_members(s33, lr.columns).items():
        sub = lr[ts]
        raw[g] = sub.mean(axis=1).where(sub.notna().sum(axis=1) >= min_members)
    raw = pd.DataFrame(raw)
    return raw, raw.sub(mkt, axis=0), mkt


def strength(rel: pd.DataFrame) -> dict[str, dict]:
    """{组: {r1m, r3m, rank3m, of}}：近 21 / 63 个交易日的相对收益之和（%）；主题、业种分别按 r3m 排名。"""
    out: dict[str, dict] = {}
    for g in rel.columns:
        s = rel[g]
        out[g] = {}
        for k, n in WIN.items():
            tail = s.iloc[-n:]
            out[g][k] = round(float(tail.sum()), 2) if tail.notna().sum() >= MIN_FRAC * n else None
    for keys in ([g for g in out if g in TH.THEMES], [g for g in out if g not in TH.THEMES]):
        ranked = sorted([g for g in keys if out[g]["r3m"] is not None], key=lambda g: -out[g]["r3m"])
        for i, g in enumerate(ranked, 1):
            out[g]["rank3m"], out[g]["of"] = i, len(ranked)
    return out


def _r2(a: pd.Series, b: pd.Series, need: int) -> float | None:
    x = pd.concat([a, b], axis=1).dropna()
    if len(x) < need or x.iloc[:, 0].std() == 0 or x.iloc[:, 1].std() == 0:
        return None
    return round(float(x.corr().iloc[0, 1] ** 2), 3)


def influence(raw: pd.DataFrame, idx_ret: pd.Series, window: int = INF_WIN) -> dict[str, float | None]:
    """{组: R²}：近 window 个交易日，组的日收益与指数日收益的相关系数平方。"""
    y = idx_ret.reindex(raw.index)
    return {g: _r2(raw[g].iloc[-window:], y.iloc[-window:], int(0.8 * window)) for g in raw.columns}


def influence_by_year(raw: pd.DataFrame, idx_ret: pd.Series, min_days: int = 200) -> dict[str, dict[str, float]]:
    """{组: {年: R²}}：每个日历年单独算（该年有效交易日 ≥ min_days）。"""
    y = idx_ret.reindex(raw.index)
    out: dict[str, dict[str, float]] = {}
    for g in raw.columns:
        for yr, idx in raw.groupby(raw.index.year).groups.items():
            v = _r2(raw.loc[idx, g], y.loc[idx], min_days)
            if v is not None:
                out.setdefault(g, {})[str(yr)] = v
    return out


def _z(M: np.ndarray) -> np.ndarray:
    """列标准化（缺值当 0，即当作平均值）。"""
    mu = np.nanmean(M, axis=0)
    sd = np.nanstd(M, axis=0, ddof=1)
    Z = (M - mu) / np.where(sd > 0, sd, np.nan)
    return np.nan_to_num(Z, nan=0.0)


def _corr_xy(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """A（天 × p）与 B（天 × q）的列间相关（p × q）。"""
    n = A.shape[0]
    return _z(A).T @ _z(B) / max(n - 1, 1)


def avg_linkage(S: np.ndarray, stop: float) -> list[list[int]]:
    """平均连接的层次聚类（UPGMA）：每次合并平均相关最高的两群，直到最高的也 < stop → 群内平均相关都 ≥ stop（不会连成一长串）。"""
    n = len(S)
    S = np.array(S, float, copy=True)
    np.fill_diagonal(S, -np.inf)
    size = np.ones(n)
    members = [[i] for i in range(n)]
    alive = np.ones(n, bool)
    while alive.sum() > 1:
        k = int(np.argmax(S))
        i, j = divmod(k, n)
        if not np.isfinite(S[i, j]) or S[i, j] < stop:
            break
        row = (S[i] * size[i] + S[j] * size[j]) / (size[i] + size[j])
        S[i], S[:, i] = row, row
        S[i, i] = -np.inf
        S[j], S[:, j] = -np.inf, -np.inf
        size[i] += size[j]
        members[i] += members[j]
        alive[j] = False
    return sorted([members[i] for i in range(n) if alive[i]], key=len, reverse=True)


def emerging(lr: pd.DataFrame, s33: dict[str, str], rel: pd.DataFrame, mkt: pd.Series,
             recent: int = RECENT, prior: int = PRIOR) -> dict:
    """新出现的联动：① 每只股票「最像的非所属组」相关上升；② 新形成的股票群（候选新主题）+ 和现有组的关联对比。"""
    mem = TH.members()
    tick = [t for t in lr.columns if t in s33 or t.split(".")[0] in mem]
    R = lr[tick].sub(mkt, axis=0)
    if len(R) < recent + prior:
        return {"note": f"行情只有 {len(R)} 个交易日，不够 {recent + prior} 个"}
    R1, R0 = R.iloc[-recent:], R.iloc[-(recent + prior):-recent]
    keep = [t for t in tick if R1[t].notna().mean() >= 0.9 and R0[t].notna().mean() >= 0.9]
    G1, G0 = rel.iloc[-recent:], rel.iloc[-(recent + prior):-recent]
    gk = [g for g in rel.columns if G1[g].notna().mean() >= 0.9 and G0[g].notna().mean() >= 0.9]
    A1, A0 = R1[keep].to_numpy(float), R0[keep].to_numpy(float)
    CG1, CG0 = _corr_xy(A1, G1[gk].to_numpy(float)), _corr_xy(A0, G0[gk].to_numpy(float))
    links = []
    for i, t in enumerate(keep):
        own = {s33.get(t), mem.get(t.split(".")[0])}
        cand = [j for j, g in enumerate(gk) if g not in own]
        if not cand:
            continue
        j = max(cand, key=lambda q: CG1[i, q])                    # 现在最像的非所属组
        c1, c0 = CG1[i, j], CG0[i, j]
        if c1 >= LINK_MIN and c1 - c0 >= LINK_RISE:
            links.append({"ticker": t, "group": gk[j], "own_ind": s33.get(t), "own_theme": mem.get(t.split(".")[0]),
                          "corr_now": round(float(c1), 2), "corr_before": round(float(c0), 2)})
    links.sort(key=lambda x: -(x["corr_now"] - x["corr_before"]))
    C1, C0 = _corr_xy(A1, A1), _corr_xy(A0, A0)
    new_edge = (C1 >= PAIR_NEW) & (C0 < PAIR_OLD)
    np.fill_diagonal(new_edge, False)
    nodes = np.flatnonzero(new_edge.any(axis=1))                  # 至少有一条「新连上」的边的股票
    clusters = []
    for comp in avg_linkage(C1[np.ix_(nodes, nodes)], PAIR_NEW) if len(nodes) else []:
        if len(comp) < MIN_CLUSTER or len(clusters) >= TOP_CLUSTERS:
            continue
        idx = nodes[comp]
        tri = np.triu_indices(len(idx), 1)
        c_now, c_before = float(C1[np.ix_(idx, idx)][tri].mean()), float(C0[np.ix_(idx, idx)][tri].mean())
        if c_before >= PAIR_OLD:                                  # 以前就在一起动的，不算新
            continue
        ts = [keep[i] for i in idx]
        basket1 = R1[ts].mean(axis=1).to_numpy(float)[:, None]
        cg = _corr_xy(basket1, G1[gk].to_numpy(float))[0]
        near = sorted(zip(gk, cg), key=lambda x: -x[1])[:3]
        inds = Counter(s33.get(t, "（不在 TOPIX 1000）") for t in ts)
        ths = Counter(mem.get(t.split(".")[0]) for t in ts if mem.get(t.split(".")[0]))
        n_top = inds.most_common(1)[0][1]
        clusters.append({"n": len(ts), "members": ts[:TOP_MEMBERS], "all_members": ts, "corr_now": round(c_now, 2), "corr_before": round(c_before, 2),
                         "industries": dict(inds.most_common()), "themes": dict(ths.most_common()),
                         "similar": [(g, round(float(c), 2)) for g, c in near],
                         "kind": "同一业种内部的新联动" if n_top >= 0.6 * len(ts) else "跨业种的新联动群（候选新主题）"})
    return {"window": [str(R1.index[0].date()), str(R1.index[-1].date())], "before": [str(R0.index[0].date()), str(R0.index[-1].date())],
            "n_stocks": len(keep), "links": links[:TOP_LINKS], "n_links": len(links), "clusters": clusters,
            "n_new_pairs": int(new_edge.sum() // 2)}


def panel(data: dict[str, pd.DataFrame], s33: dict[str, str], idx_close: pd.Series, history: dict | None = None) -> dict:
    """日报用的一整块（写进 unified_today.json 的 themes）。history = var/theme_influence.json（历年影响度）。"""
    lr = log_returns(data)
    raw, rel, mkt = group_panel(lr, s33)
    idx_ret = np.log(idx_close.where(idx_close > 0)).diff() * 100
    st = strength(rel)
    inf = influence(raw, idx_ret)
    hist = (history or {}).get("groups") or {}
    last = rel.dropna(how="all").index[-1] if len(rel.dropna(how="all")) else None
    gm = group_members(s33, lr.columns)
    groups = {}
    for g in rel.columns:
        h = hist.get(g) or {}
        groups[g] = {**st.get(g, {}), "r2_now": inf.get(g), "n": len(gm.get(g, [])), "r2_hist": {y: h[y] for y in sorted(h)[-11:]}}
    return {"asof": str(last.date()) if last is not None else None, "index": "^N225", "groups": groups,
            "themes": {k: {"name": v[0], "ja": v[1]} for k, v in TH.THEMES.items()},
            "emerging": emerging(lr, s33, rel, mkt)}
