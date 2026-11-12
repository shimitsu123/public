"""supply_chain.py — 跨行业（上下游）的影响：原材料价格、上游 / 下游行业的股价，能不能预测之后 1〜6 个月各行业的相对表现？
（scripts/supply_chain_study.py；2026-09-26 事先登记）

结构（事先定、不看收益）：令和 2 年（2020 年）产业连关表 取引基本表（生产者价格，统合大分类 37 部门；総務省，e-Stat）→
  各東証业种「从哪些产业买投入品（投入份额）」「卖给哪些产业（中间需求的销售份额）」（IO_TSE：37 部门 ↔ 東証 33 业种的对照）。
价格（日银 企业物价指数 2020 年基准，月度；CGPI）：各商品产业的国内企业物价（類別），矿业用进口物价（石油・石炭・天然ガス，円ベース）。
  发布滞后：M 月的物价在 M+1 月中旬公布 → M 月末只用到 M−1 月的物价。
四种信号（M 月末已知；w = 过去 1 / 3 / 6 个月）：
  C 原材料成本压力 = Σ 投入份额 × 投入品价格的对数变化（只算有物价的商品投入；= 占产出额的成本变化 %）；越高 = 成本上升 → 事先方向 −
    （「原材料下降利好下游」）
  Mg 利润空间 = 自己产品价格的对数变化 − C（只有商品产业有）；事先方向 +
  S 上游股价 = Σ 投入份额（上游是上市行业的部分，归一）× 上游行业过去 w 个月的相对收益；事先方向 +（Menzly-Ozbas 2010）
  K 下游股价 = Σ 销售份额（下游是上市行业的部分，归一）× 下游行业过去 w 个月的相对收益；事先方向 +（Cohen-Frazzini 2008）
  O 自己过去 w 个月的相对收益（行业动量，参照）
被预测：之后 h 个月（1 / 3 / 6）的行业相对收益（成员等权 − 全部平均，对数，%）。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# 37 部门 → 東証 33 业种（剔除航空 / 陆运 / 仓储后的 30 个里用得到的）
IO_TSE = {"01": ["水産・農林業"], "06": ["鉱業"], "11": ["食料品"], "15": ["繊維製品"], "16": ["パルプ・紙"],
          "20": ["化学", "医薬品"], "21": ["石油・石炭製品"], "22": ["ゴム製品"], "25": ["ガラス・土石製品"], "26": ["鉄鋼"],
          "27": ["非鉄金属"], "28": ["金属製品"], "29": ["機械"], "30": ["機械"], "31": ["精密機器"], "32": ["電気機器"],
          "33": ["電気機器"], "34": ["電気機器"], "35": ["輸送用機器"], "39": ["その他製品"], "41": ["建設業"],
          "46": ["電気・ガス業"], "51": ["卸売業", "小売業"], "53": ["銀行業", "証券、商品先物取引業", "保険業", "その他金融業"],
          "55": ["不動産業"], "57": ["海運業"], "59": ["情報・通信業"], "66": ["サービス業"], "67": ["サービス業"]}
# 商品产业的价格（日银 PR01）：国内企业物价 類別；矿业用进口物价（石油・石炭・天然ガス）
CGPI = {"01": "PRCG20_2202020001", "06": "PRCG20_2600520001", "11": "PRCG20_2200120001", "15": "PRCG20_2200220001",
        "16": "PRCG20_2200420001", "20": "PRCG20_2200520001", "21": "PRCG20_2200620001", "22": "PRCG20_2200720001",
        "25": "PRCG20_2200820001", "26": "PRCG20_2200920001", "27": "PRCG20_2201020001", "28": "PRCG20_2201120001",
        "29": "PRCG20_2201220001", "30": "PRCG20_2201320001", "31": "PRCG20_2201420001", "32": "PRCG20_2201520001",
        "33": "PRCG20_2201620001", "34": "PRCG20_2201720001", "35": "PRCG20_2201820001", "39": "PRCG20_2201920001",
        "46": "PRCG20_2202220001"}
SEMI = "半導体（日経225 半导体组）"                      # Part A 另加的一个「行业」：用户举的例子（半导体材料 → 半导体）
SEMI_IO = ["32"]
WINDOWS, HORIZONS = (1, 3, 6), (1, 3, 6)
SIGN = {"C": -1, "Mg": 1, "S": 1, "K": 1, "O": 1}


# ── 产业连关表 ──
def _code(v) -> str:
    """部门代码 → 两位字符串（表里是文字「01」；读成数字 1 / 1.0 时也一样）。"""
    if isinstance(v, (int, float, np.integer, np.floating)) and not pd.isna(v) and float(v).is_integer():
        return f"{int(v):02d}"
    return str(v).strip().zfill(2)


def read_io(xlsx) -> tuple[pd.DataFrame, pd.Series]:
    """取引基本表（37 部门）→ (x：供给部门 × 使用部门 的交易额，X：各部门国内生产额)。"""
    df = pd.read_excel(xlsx, header=None)
    codes = [_code(c) for c in df.iloc[1, 2:39]]
    rows = {_code(df.iloc[i, 0]): i for i in range(3, df.shape[0]) if pd.notna(df.iloc[i, 0])}
    x = pd.DataFrame([[float(df.iloc[rows[r], 2 + k]) for k in range(len(codes))] for r in codes], index=codes, columns=codes)
    Xcol = [c for c in range(df.shape[1]) if pd.notna(df.iloc[1, c]) and _code(df.iloc[1, c]) == "97"][0]
    X = pd.Series([float(df.iloc[rows[r], Xcol]) for r in codes], index=codes)
    return x, X


PARTNER_EXCLUDE = {"57"}                                   # 运输・邮政大半是陆运 / 邮政（股票池里没有）→ 不当作上下游伙伴（海运业自己的投入照算）


def tse_links(x: pd.DataFrame, X: pd.Series, industries: list[str], extra: dict[str, list[str]] | None = None) -> dict:
    """東証业种之间的投入份额 / 销售份额（事先由产业连关表定，不看收益）。
    ins[j][i] = j 的国内生产额里、来自 37 部门 i 的投入额所占比例（j 对应多个部门就合并）—— 成本渠道用；
    sup[j][U] = 上游上市行业 U 的权重（U 的部门投入份额之和；同一部门被几个业种共用时平分）；
    cus[j][K] = 下游上市行业 K 的权重（j 的部门卖给 K 的部门的中间需求份额，同上平分）。
    上下游都不含自己、也不含与自己共用部门的业种（例 化学 / 医薬品、卸売 / 小売），归一。
    extra（例 半导体组）只算成本渠道，不当作别人的上下游、也没有 sup / cus。"""
    tse_io: dict[str, list[str]] = {}
    for io, ts in IO_TSE.items():
        for t in ts:
            tse_io.setdefault(t, []).append(io)
    base = [t for t in industries if t in tse_io]
    share = {io: 1 / len(ts) for io, ts in IO_TSE.items()}
    out = {"ins": {}, "sup": {}, "cus": {}, "tse_io": {}}
    for j in base + [t for t in (extra or {}) if t in industries]:
        J = (extra or {}).get(j) or tse_io[j]
        prod = float(X[J].sum())
        ins = (x[J].sum(axis=1) / prod).to_dict()
        out["ins"][j] = {i: v for i, v in ins.items() if v > 0}
        out["tse_io"][j] = list(J)
        if j not in base:
            out["sup"][j], out["cus"][j] = {}, {}
            continue
        sib = {U for U in base if set(tse_io[U]) & set(J)}                  # 自己与共用部门的业种
        sales = (x.loc[J].sum(axis=0) / prod).to_dict()
        for key, src in (("sup", ins), ("cus", sales)):
            d = {U: sum(src.get(i, 0.0) * share[i] for i in tse_io[U] if i not in PARTNER_EXCLUDE) for U in base if U not in sib}
            tot = sum(v for v in d.values() if v > 0)
            out[key][j] = {k: v / tot for k, v in d.items() if v > 0} if tot > 0 else {}
    return out


# ── 月度收益与信号 ──
def monthly(R_daily: pd.DataFrame) -> pd.DataFrame:
    """日相对收益（%）→ 月度相对收益（%，月末日期）。"""
    return R_daily.groupby(R_daily.index.to_period("M")).sum(min_count=1).to_timestamp("M")


def past(M: pd.DataFrame, w: int) -> pd.DataFrame:
    return M.rolling(w, min_periods=w).sum()


def ahead(M: pd.DataFrame, h: int) -> pd.DataFrame:
    """月末 t 那一行 = t+1〜t+h 个月的相对收益之和。"""
    return M[::-1].rolling(h, min_periods=h).sum()[::-1].shift(-1)


def price_change(P: pd.DataFrame, months: pd.DatetimeIndex, w: int, lag: int = 1) -> pd.DataFrame:
    """月末 t：部门物价在（t − lag − w, t − lag] 的对数变化（%）；lag = 1 = 只用已公布的上个月。P 的索引 = 月初。"""
    lp = np.log(P.where(P > 0)) * 100
    ch = lp - lp.shift(w)
    ch.index = ch.index.to_period("M").to_timestamp("M")
    return ch.shift(lag).reindex(months)


def signals(Mret: pd.DataFrame, P: pd.DataFrame, links: dict, w: int) -> dict[str, pd.DataFrame]:
    """月末 × 行业 的 C / Mg / S / K / O（w 个月）。"""
    months = Mret.index
    O = past(Mret, w)
    dP = price_change(P, months, w)
    inds = list(Mret.columns)
    C = pd.DataFrame(np.nan, index=months, columns=inds)
    Mg = pd.DataFrame(np.nan, index=months, columns=inds)
    S = pd.DataFrame(np.nan, index=months, columns=inds)
    K = pd.DataFrame(np.nan, index=months, columns=inds)
    for j in inds:
        ins = {i: v for i, v in links["ins"].get(j, {}).items() if i in dP.columns}
        if ins:                                                             # 占产出额的成本变化（%）：商品投入少的行业自然接近 0
            C[j] = sum(v * dP[i] for i, v in ins.items())
            own = [i for i in links["tse_io"].get(j, []) if i in dP.columns]
            if own:
                Mg[j] = dP[own].mean(axis=1) - C[j]
        for key, frame in (("sup", S), ("cus", K)):
            wts = {u: v for u, v in links[key].get(j, {}).items() if u in O.columns}
            if wts:
                tot = sum(wts.values())
                frame[j] = sum(v * O[u] for u, v in wts.items()) / tot
    return {"C": C, "Mg": Mg, "S": S, "K": K, "O": O}


# ── 检验 ──
def _nw_se(x: np.ndarray, lags: int) -> float:
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 10:
        return float("nan")
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - L / (lags + 1)) * float(np.dot(u[L:], u[:-L])) / n
    return math.sqrt(max(s, 0) / n)


def _avg_rank(a: np.ndarray) -> np.ndarray:
    """秩（1 起；相同的值取平均秩，与 pandas rank() 相同）。"""
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    return (np.cumsum(cnt) - (cnt - 1) / 2.0)[inv]


def fm_ic(X: pd.DataFrame, Y: pd.DataFrame, lags: int, min_n: int = 8) -> pd.Series:
    """每个月的横截面秩相关（信号 vs 之后的相对收益）；两边都有值的行业 ≥ min_n 才算。"""
    xv = X.to_numpy(float)
    yv = Y.reindex(index=X.index, columns=X.columns).to_numpy(float)
    out = {}
    for k, t in enumerate(X.index):
        m = np.isfinite(xv[k]) & np.isfinite(yv[k])
        if m.sum() >= min_n:
            rx, ry = _avg_rank(xv[k][m]), _avg_rank(yv[k][m])
            rx, ry = rx - rx.mean(), ry - ry.mean()
            d = math.sqrt(float(np.dot(rx, rx)) * float(np.dot(ry, ry)))
            out[t] = float(np.dot(rx, ry)) / d if d > 0 else float("nan")
    return pd.Series(out, dtype=float)


def roll(F, s: int):
    """时间错开的对照：沿时间轴循环错开 s 期（日期不变，值错开）→ 保留各自的自相关，拆掉真实的先后关系。"""
    v = np.roll(F.to_numpy(float), s, axis=0)
    return (pd.DataFrame(v, index=F.index, columns=F.columns) if isinstance(F, pd.DataFrame)
            else pd.Series(v, index=F.index, name=F.name))


def placebo_p(actual: float, placebo: np.ndarray, sign: int = 1) -> float | None:
    """经验 p（单侧、事先方向）：对照里 ≥ 实际（sign = −1 时 ≤）的比例，(1 + 个数) / (1 + 对照数)。"""
    a = np.asarray(placebo, float)
    a = a[np.isfinite(a)]
    if not np.isfinite(actual) or not len(a):
        return None
    return round(float((1 + np.sum(a * sign >= actual * sign)) / (1 + len(a))), 4)


def ic_stats(ic: pd.Series, lags: int) -> dict:
    v = ic.to_numpy(float)
    se = _nw_se(v, lags)
    m = float(np.nanmean(v)) if len(v) else float("nan")
    return {"n": int(np.isfinite(v).sum()), "ic": round(m, 4), "t": round(m / se, 2) if se and se > 0 else None}


def tercile(X: pd.DataFrame, Y: pd.DataFrame, sign: int, step: int, min_n: int = 9) -> dict:
    """每 step 个月一次（不重叠）：事先方向上最好的 1/3 行业 − 最差 1/3 的之后收益（%）；命中率 = 差 > 0 的比例。"""
    sp = []
    for t in X.index[::step]:
        if t not in Y.index:
            continue
        x, y = X.loc[t] * sign, Y.loc[t]
        m = x.notna() & y.notna()
        if m.sum() < min_n:
            continue
        x, y = x[m], y[m]
        k = len(x) // 3
        o = x.sort_values().index
        sp.append(float(y[o[-k:]].mean() - y[o[:k]].mean()))
    a = np.array(sp)
    return {"n": int(len(a)), "spread": round(float(a.mean()), 3) if len(a) else None,
            "hit": round(float((a > 0).mean()) * 100, 1) if len(a) else None,
            "t": round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 2) if len(a) > 2 and a.std(ddof=1) > 0 else None}
