"""signal_score.py — 日本个股买点的「质量分」：个股 / 大盘 / 行业因子 → 配比 → 分数（scripts/score_study.py；2026-09-26 事先登记）。

一个信号（某只票某天收盘时 entry 成立）的 15 个因子，全部只用当天收盘为止的数据：
  个股 / 大盘（10）：量比、箱体幅度、突破距离、出货日、上影线、相对强度、离 200 日线、离一年高点、波动收缩、日経离 200 日线
  行业（5）：行业 60 日动量、行业广度、板块共振、个股相对行业强度、行业 20 日动量（行业 = qbreak/sectors.py 的分组，
             同行业「其他」成员的平均，不含自己；其他成员不到 2 只 → 缺值）
配比（权重）的几种方式都在「训练样本」上定：每个因子先换成它在训练样本里的百分位 − 0.5（缺值 = 0，中性），
  ew = 等权 × 事先定的方向；lr = L2 逻辑回归（目标：扣费后赚钱）；ic = 各因子与每笔净收益的秩相关作权重。
分数越高越好；门槛 thr = 训练样本分数的 1/3 分位（低于它 = 最差的三分之一）。

另有候补队列「就绪度」的向量化版本（readiness_components：与 qbreak/scan.py 的逐行计算相同），研究它的配比用。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .sectors import SECTOR_JP
from .signal_filters import bb_width
from .weights import L2_GRID, cv_pick, fit_newton

MOM_N, SHORT_N, BREADTH_MA, CO_WIN, MIN_OTHERS = 60, 20, 50, 10, 2
TREND_MA, HI_WIN, BB_RANK_WIN = 200, 252, 250
DROP_Q = 1 / 3                                   # 分数低于训练样本 1/3 分位 = 最差的三分之一

STOCK = ["vol", "tight", "brk", "dist", "shadow", "rs", "trend", "high", "squeeze", "mkt"]
INDUSTRY = ["ind_mom60", "ind_breadth", "ind_cobreak", "rel_ind60", "ind_mom20"]
ALL = STOCK + INDUSTRY
# 事先定的方向（+1 = 越大越好）；依据见 scripts/score_study.py 开头
SIGN = {"vol": 1, "tight": -1, "brk": 1, "dist": -1, "shadow": -1, "rs": 1, "trend": 1, "high": 1, "squeeze": -1,
        "mkt": 1, "ind_mom60": 1, "ind_breadth": 1, "ind_cobreak": 1, "rel_ind60": 1, "ind_mom20": 1}
LABELS = {"vol": "量比（对数）", "tight": "箱体幅度（前一天）", "brk": "突破距离（收盘 / 箱顶 − 1）", "dist": "出货日（20 日内）",
          "shadow": "上影线 / 实体", "rs": "相对强度（60 日，对日経）", "trend": "离 200 日线", "high": "离一年高点（收盘 / 252 日最高）",
          "squeeze": "波动收缩（前一天布林带宽的一年百分位）", "mkt": "日経离 200 日线",
          "ind_mom60": "行业 60 日动量（其他成员 − 全池）", "ind_breadth": "行业广度（其他成员收在 50 日线上的比例）",
          "ind_cobreak": "板块共振（10 个交易日内其他成员出过信号的比例）", "rel_ind60": "个股相对行业（60 日）",
          "ind_mom20": "行业 20 日动量（其他成员 − 全池）"}


# ═══════════ 因子 ═══════════
def stock_panel(ind: dict[str, pd.DataFrame], index_close: pd.Series | None) -> dict[str, pd.DataFrame]:
    """{因子: DataFrame(日期 × 票)}；ind = compute_indicators 的结果（有 OHLCV 与 vol_ratio / range_pct / box_top / dist_days /
    upper_shadow_ratio）。index_close = 日経平均收盘（没有 → rs、mkt 缺值）。"""
    cols: dict[str, dict[str, pd.Series]] = {k: {} for k in STOCK}
    for t, df in ind.items():
        c = df["Close"].astype(float)
        vr = df["vol_ratio"].astype(float)
        cols["vol"][t] = np.log(vr.where(vr > 0))
        cols["tight"][t] = df["range_pct"].astype(float).shift(1)
        cols["brk"][t] = c / df["box_top"].astype(float) - 1
        cols["dist"][t] = df["dist_days"].astype(float)
        cols["shadow"][t] = df["upper_shadow_ratio"].astype(float)
        cols["trend"][t] = c / c.rolling(TREND_MA, min_periods=TREND_MA).mean() - 1
        cols["high"][t] = c / c.rolling(HI_WIN, min_periods=HI_WIN).max()
        cols["squeeze"][t] = bb_width(c).rolling(BB_RANK_WIN, min_periods=BB_RANK_WIN).rank(pct=True).shift(1)
        if index_close is not None:
            ic = index_close.reindex(c.index.union(index_close.index)).ffill().reindex(c.index)
            cols["rs"][t] = (c / c.shift(MOM_N) - 1) - (ic / ic.shift(MOM_N) - 1)
            m = index_close.rolling(TREND_MA, min_periods=TREND_MA).mean()
            cols["mkt"][t] = (index_close / m - 1).reindex(c.index.union(index_close.index)).ffill().reindex(c.index)
        else:
            cols["rs"][t] = cols["mkt"][t] = pd.Series(np.nan, index=c.index)
    return {k: pd.DataFrame(v).sort_index() for k, v in cols.items()}


def _others_mean(x: pd.DataFrame, groups: dict[str, list[str]]) -> pd.DataFrame:
    """同一分组里「其他」成员的平均（不含自己；有数据的其他成员 < MIN_OTHERS → 缺值）。"""
    out = pd.DataFrame(np.nan, index=x.index, columns=x.columns)
    for members in groups.values():
        sub = x[members]
        s, n = sub.sum(axis=1, skipna=True), sub.notna().sum(axis=1)
        for t in members:
            own, has = sub[t].fillna(0.0), sub[t].notna().astype(int)
            k = n - has
            out[t] = ((s - own) / k).where(k >= MIN_OTHERS)
    return out


def industry_panel(closes: pd.DataFrame, entries: pd.DataFrame, sector: dict[str, str] | None = None) -> dict[str, pd.DataFrame]:
    """closes / entries：DataFrame(日期 × 票)（entries = 当天收盘 entry 是否成立）。sector：{票: 分组}（缺省按 SECTOR_JP）。"""
    sector = sector or {t: SECTOR_JP.get(t.split(".")[0], "other") for t in closes.columns}
    groups: dict[str, list[str]] = {}
    for t in closes.columns:
        groups.setdefault(sector.get(t, "other"), []).append(t)
    r60 = closes / closes.shift(MOM_N) - 1
    r20 = closes / closes.shift(SHORT_N) - 1
    ma = closes.rolling(BREADTH_MA, min_periods=BREADTH_MA).mean()
    above = (closes > ma).astype(float).where(ma.notna() & closes.notna())
    e = entries.reindex(index=closes.index, columns=closes.columns).fillna(False).astype(float)
    co = e.rolling(CO_WIN, min_periods=1).max().where(closes.notna())
    o60, o20 = _others_mean(r60, groups), _others_mean(r20, groups)
    return {"ind_mom60": o60.sub(r60.mean(axis=1), axis=0), "ind_breadth": _others_mean(above, groups),
            "ind_cobreak": _others_mean(co, groups), "rel_ind60": r60 - o60,
            "ind_mom20": o20.sub(r20.mean(axis=1), axis=0)}


def feature_panel(ind: dict[str, pd.DataFrame], index_close: pd.Series | None,
                  sector: dict[str, str] | None = None) -> dict[str, pd.DataFrame]:
    sp = stock_panel(ind, index_close)
    idx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    closes = pd.DataFrame({t: df["Close"] for t, df in ind.items()}).reindex(idx)
    entries = pd.DataFrame({t: df["entry"].astype(bool) for t, df in ind.items()}).reindex(idx)
    return {**{k: v.reindex(index=idx, columns=closes.columns) for k, v in sp.items()},
            **industry_panel(closes, entries, sector)}


def signal_rows(panel: dict[str, pd.DataFrame], ind: dict[str, pd.DataFrame], start: str | None = None) -> pd.DataFrame:
    """每个信号（票 × entry 成立的那天）一行：date、ticker 与 15 个因子。"""
    rows = []
    for t, df in ind.items():
        d = df.index[df["entry"].astype(bool).to_numpy()]
        if start is not None:
            d = d[d >= pd.Timestamp(start)]
        if len(d):
            rows.append(pd.DataFrame({"date": d, "ticker": t}))
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", *ALL])
    R = pd.concat(rows, ignore_index=True).sort_values(["date", "ticker"], ignore_index=True)
    for k in ALL:
        P = panel[k]
        ci = P.columns.get_indexer(R["ticker"])
        ri = P.index.get_indexer(R["date"])
        R[k] = P.to_numpy(float)[ri, ci]
    return R


# ═══════════ 配比 ═══════════
def pct_x(v: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """v 在参考样本 ref 里的百分位（平局取中）− 0.5；缺值 → 0（中性）。"""
    ref = np.sort(np.asarray(ref, float)[np.isfinite(ref)])
    v = np.asarray(v, float)
    out = np.zeros(len(v))
    if not len(ref):
        return out
    m = np.isfinite(v)
    lo, hi = np.searchsorted(ref, v[m], "left"), np.searchsorted(ref, v[m], "right")
    out[m] = (lo + hi) / 2 / len(ref) - 0.5
    return out


def _rank(a: np.ndarray) -> np.ndarray:
    return pd.Series(a).rank(method="average").to_numpy(float)


def rank_corr(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = _rank(x), _rank(y)
    if np.ptp(rx) == 0 or np.ptp(ry) == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


@dataclass
class Model:
    kind: str
    cols: list[str]
    refs: dict[str, np.ndarray]
    w: np.ndarray
    b0: float = 0.0
    thr: float = float("nan")
    info: dict = field(default_factory=dict)

    def X(self, raw: pd.DataFrame) -> np.ndarray:
        return np.column_stack([pct_x(raw[c].to_numpy(float), self.refs[c]) for c in self.cols])

    def score(self, raw: pd.DataFrame) -> np.ndarray:
        return self.b0 + self.X(raw) @ self.w


def fit(kind: str, cols: list[str], train: pd.DataFrame) -> Model:
    """train：训练样本（因子原值 + win（0/1）+ net（每笔净收益 %）+ pos（信号日的交易日序号，交叉验证的隔离用））。"""
    refs = {c: train[c].to_numpy(float) for c in cols}
    m = Model(kind, list(cols), refs, np.zeros(len(cols)))
    X = m.X(train)
    if kind == "ew":
        m.w = np.array([SIGN[c] for c in cols], float) / len(cols)
    elif kind == "lr":
        y = train["win"].to_numpy(float)
        pos = train["pos"].to_numpy(int)
        o = np.argsort(pos, kind="mergesort")
        lam, cv = cv_pick(lambda A, b, g: fit_newton(A, b, g), L2_GRID, X[o], y[o], pos[o])
        wb = fit_newton(X, y, lam)
        m.b0, m.w = float(wb[0]), wb[1:]
        m.info.update(lam=lam, cv=cv)
    elif kind == "ic":
        net = train["net"].to_numpy(float)
        m.w = np.array([rank_corr(X[:, j], net) for j in range(len(cols))])
    else:
        raise KeyError(kind)
    m.thr = float(np.quantile(m.score(train), DROP_Q)) if len(train) else float("nan")
    return m


def walk_forward(rows: pd.DataFrame, trades: pd.DataFrame, kind: str, cols: list[str], years: list[int]) -> tuple[pd.DataFrame, dict]:
    """每年年初用「信号日与平仓日都在这之前」的交易重新定配比，给这一年的信号打分。
    rows：全部信号（date、ticker、因子）；trades：有结果的交易（sig_date、exit_date、win、net、pos、因子）。
    返回 (rows 加 score / thr 两列（没打分的年份为缺值）, {年: Model})。"""
    out = rows.copy()
    out["score"], out["thr"] = np.nan, np.nan
    models = {}
    for y in years:
        cut = pd.Timestamp(f"{y}-01-01")
        tr = trades[(trades["sig_date"] < cut) & (trades["exit_date"] < cut)]
        sel = (out["date"] >= cut) & (out["date"] < pd.Timestamp(f"{y + 1}-01-01"))
        if not len(tr) or not sel.any():
            continue
        m = fit(kind, cols, tr)
        models[y] = m
        out.loc[sel, "score"] = m.score(out[sel])
        out.loc[sel, "thr"] = m.thr
    return out, models


# ═══════════ 候补队列「就绪度」（向量化；与 qbreak/scan.py 的逐行计算相同）═══════════
READY_W = (0.30, 0.25, 0.30, 0.15)              # 现行配比：横盘 / 0 轴附近 / MACD 距金叉 / 量比


def readiness_components(df: pd.DataFrame, p) -> pd.DataFrame:
    c = df["Close"].astype(float)
    rp = df["range_pct"].astype(float)
    is_range = df["is_range"].fillna(False).astype(bool)
    near_zero = df["near_zero"].fillna(False).astype(bool)
    gap = (df["macd"] - df["macd_sig"]) / c * 100
    hist_up = df["macd_hist"] > df["macd_hist"].shift(1)
    vr = df["vol_ratio"].astype(float).where(np.isfinite(df["vol_ratio"].astype(float)), 0.0).fillna(0.0)
    s_range = np.where(is_range, 1.0, np.where(np.isfinite(rp), np.clip(1 - (rp - p.range_x_pct) / p.range_x_pct, 0, 1), 0.0))
    s_zero = np.where(near_zero, 1.0, np.clip(1 - ((df["macd"].abs() / c * 100) - p.macd_zero_band_pct) / p.macd_zero_band_pct, 0, 1))
    s_cross = np.where(gap > 0, np.where(df["golden_cross"].fillna(False).astype(bool), 0.6, 0.3),
                       np.clip(1 - gap.abs() / 0.5, 0, 1) * np.where(hist_up, 1.0, 0.7))
    s_vol = np.clip(vr / p.vol_mult, 0, 1)
    return pd.DataFrame({"s_range": s_range, "s_zero": s_zero, "s_cross": s_cross, "s_vol": s_vol}, index=df.index)


def readiness_score(comp: pd.DataFrame, w=READY_W) -> pd.Series:
    return 100 * (w[0] * comp["s_range"] + w[1] * comp["s_zero"] + w[2] * comp["s_cross"] + w[3] * comp["s_vol"])
