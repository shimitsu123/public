"""sensitivity.py — 个股对宏观因素的敏感度与「宏观顺风度」（只用当时已知的数据）。

因素（日本交易日；美国的量取「前一个美国收盘」之后的变化 —— 美国夜里的变化在日本第二天反映）：
  rate_jp  日本 10Y 利率变化（pt）            rate_us  美国 10Y 利率变化（pt）
  oil      WTI 涨跌（%）                      fx       美元日元涨跌（%，正 = 日元贬值）
  credit   Baa−10Y 利差变化（pt）             mkt      日経225 涨跌（控制大盘）
敏感度：每只票近 104 周（约 2 年）的周收益对以上因素的多元回归系数（周五到周五；至少 60 周）。
宏观顺风度：Σ 敏感度 × 该因素近 60 个交易日的平均周变化（不含大盘项）= 「近期宏观趋势若延续，每周多赚 / 少赚多少」（%/周）。
说明文字：贡献最大的两个因素，例「利率↑ 受益」「油价↑ 受损」。
研究见 scripts/regime_fit_study.py；候补队列按顺风度作第二排序键（只作参考），是否用于交易排序看研究结论。

商品（粮食 / 金属 / 贵金属 / 能源 ETF 与期货，COMMODS；研究见 scripts/commodity_fit_study.py）：
  同周联动 = 控制大盘后，商品涨 1% 时个股 / 行业同周多涨几 %（pair_beta）；
  扩展顺风度 = 在上面 5 个因素外再加 农产品综合 DBA / 工业金属 DBB / 黄金 GLD / 天然气 UNG（EXT）一起回归。
  美国挂牌的商品价格对日本交易日同样取「前一个美国收盘」。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FACTORS = ["rate_jp", "rate_us", "oil", "fx", "credit"]
LABEL = {"rate_jp": "日本利率", "rate_us": "美国利率", "oil": "油价", "fx": "日元贬值", "credit": "信用利差"}
WEEKS, MIN_WEEKS, TREND_DAYS = 104, 60, 60
COMMODS = {  # 键: (代码, 中文名, 类别)；=F 为期货连续合约（换月时有跳空，结果噪音较大）
    "agri": ("DBA", "农产品综合", "粮食"), "corn": ("CORN", "玉米", "粮食"), "wheat": ("WEAT", "小麦", "粮食"),
    "soy": ("SOYB", "大豆", "粮食"), "sugar": ("CANE", "糖", "粮食"), "coffee": ("KC=F", "咖啡", "粮食"),
    "cocoa": ("CC=F", "可可", "粮食"),
    "metals": ("DBB", "工业金属", "金属"), "copper": ("CPER", "铜", "金属"), "alum": ("ALI=F", "铝", "金属"),
    "iron": ("TIO=F", "铁矿石", "金属"),
    "gold": ("GLD", "黄金", "贵金属"), "silver": ("SLV", "白银", "贵金属"), "plat": ("PPLT", "铂", "贵金属"),
    "pall": ("PALL", "钯", "贵金属"),
    "natgas": ("UNG", "天然气", "能源"), "eugas": ("TTF=F", "欧洲天然气", "能源"), "gasoline": ("UGA", "汽油", "能源"),
    "broad": ("DBC", "商品综合", "综合"),
}
EXT = ["agri", "metals", "gold", "natgas"]            # 扩展顺风度多加的 4 个大类
FACTORS_EXT = FACTORS + EXT
LOG_COLS = {"oil", "fx", "mkt"} | set(COMMODS)        # 这些列是对数水平，变化 ×100 = %
LABEL.update({k: v[1] for k, v in COMMODS.items()})


def _asof(s: pd.Series, when: pd.DatetimeIndex) -> np.ndarray:
    s = s.dropna()
    return s.reindex(s.index.union(when)).ffill().reindex(when).to_numpy(float)


def factor_levels(jp_days: pd.DatetimeIndex, n225: pd.Series, jgb10: pd.Series, dgs10: pd.Series, wti: pd.Series,
                  usdjpy: pd.Series, baa: pd.Series, extra: dict | None = None, same_day: bool = False) -> pd.DataFrame:
    """日本交易日 D 收盘时已知的各因素水平（美国量 = D 之前最后一个美国收盘；日本 10Y = D 当天）。
    extra：{商品键: 价格序列}（美国挂牌，同样取前一个美国收盘）。same_day=True：days 是美国交易日、n225 换成美国指数，
    美国量取当天收盘（美国资产用）。"""
    prev = jp_days if same_day else jp_days - pd.Timedelta(days=1)
    lv = pd.DataFrame(index=jp_days)
    lv["rate_jp"] = _asof(jgb10, jp_days)
    lv["rate_us"] = _asof(dgs10, prev)
    lv["oil"] = np.log(np.clip(_asof(wti.where(wti > 0), prev), 1e-6, None))
    lv["fx"] = np.log(_asof(usdjpy, prev))
    lv["credit"] = _asof(baa, prev)
    for k, px in (extra or {}).items():
        lv[k] = np.log(np.clip(_asof(px.where(px > 0), prev), 1e-6, None))
    lv["mkt"] = np.log(_asof(n225, jp_days))
    return lv


def weekly_changes(lv: pd.DataFrame) -> pd.DataFrame:
    """周五（该周最后一个交易日）水平 → 周变化；对数量乘 100 变成 %。"""
    wk = lv.groupby(lv.index.to_period("W-FRI")).tail(1)
    ch = wk.diff()
    for c in LOG_COLS & set(ch.columns):
        ch[c] *= 100
    return ch.iloc[1:]


def stock_weekly(close: pd.Series, weeks_index: pd.DatetimeIndex) -> pd.Series:
    """个股周收益（%，对数），按因素周表的日期对齐（该周最后一个交易日）。"""
    c = close.dropna()
    wk = np.log(c.groupby(c.index.to_period("W-FRI")).tail(1))
    r = wk.diff() * 100
    r.index = r.index.to_period("W-FRI")
    out = pd.Series(np.nan, index=weeks_index)
    per = weeks_index.to_period("W-FRI")
    m = per.isin(r.index)
    out[m] = r.reindex(per[m]).to_numpy(float)
    return out


def betas(y: pd.Series, X: pd.DataFrame, end: pd.Timestamp) -> pd.Series | None:
    """截至 end（含）最近 WEEKS 周的 OLS 系数（含大盘项）；样本不足返回 None。"""
    d = pd.concat([y.rename("y"), X], axis=1).loc[:end].dropna().tail(WEEKS)
    if len(d) < MIN_WEEKS:
        return None
    A = np.c_[np.ones(len(d)), d[X.columns].to_numpy(float)]
    coef, *_ = np.linalg.lstsq(A, d["y"].to_numpy(float), rcond=None)
    return pd.Series(coef[1:], index=X.columns)


def trend(lv: pd.DataFrame, at: pd.Timestamp, days: int = TREND_DAYS, factors: list[str] | None = None) -> pd.Series:
    """近 days 个交易日各因素的平均周变化（与回归同单位）。"""
    factors = factors or [c for c in lv.columns if c != "mkt"]
    x = lv.loc[:at].tail(days + 1)
    if len(x) < days + 1:
        return pd.Series(np.nan, index=factors)
    ch = x.iloc[-1] - x.iloc[0]
    for c in LOG_COLS & set(ch.index):
        ch[c] *= 100
    return ch[factors] / (days / 5)


def pair_beta(y: pd.Series, x: pd.Series, m: pd.Series, end: pd.Timestamp,
              weeks: int = WEEKS) -> tuple[float, float] | None:
    """控制大盘后的单因素敏感度：截至 end 最近 weeks 周，y ~ 1 + 大盘 + x 的 x 系数与 t 值；样本不足返回 None。"""
    d = pd.concat([y.rename("y"), m.rename("m"), x.rename("x")], axis=1).loc[:end].dropna().tail(weeks)
    if len(d) < MIN_WEEKS:
        return None
    A = np.c_[np.ones(len(d)), d["m"].to_numpy(float), d["x"].to_numpy(float)]
    yy = d["y"].to_numpy(float)
    coef, *_ = np.linalg.lstsq(A, yy, rcond=None)
    resid = yy - A @ coef
    s2 = resid @ resid / (len(d) - 3)
    cov = s2 * np.linalg.pinv(A.T @ A)
    se = float(np.sqrt(max(cov[2, 2], 0)))
    return float(coef[2]), (float(coef[2]) / se if se > 0 else float("nan"))


def fit_score(b: pd.Series | None, tr: pd.Series, factors: list[str] | None = None) -> tuple[float | None, str]:
    """顺风度（%/周）与说明文字（贡献最大的两项）。factors 默认 = 5 个宏观因素。"""
    factors = factors or FACTORS
    if b is None or tr[factors].isna().any():
        return None, ""
    contrib = b[factors] * tr[factors]
    score = float(contrib.sum())
    top = contrib.abs().sort_values(ascending=False).head(2).index
    parts = [f"{LABEL[f]}{'↑' if tr[f] > 0 else '↓'} {'受益' if contrib[f] > 0 else '受损'}" for f in top if abs(contrib[f]) > 1e-9]
    return score, "；".join(parts)


def load_ext_prices() -> dict[str, pd.Series]:
    """扩展顺风度用的 4 个商品 ETF 收盘（去错价）：{"agri","metals","gold","natgas"}。"""
    from . import factors as F
    return {k: F.despike(F.yf_close(COMMODS[k][0])) for k in EXT}


def current_fit(closes: dict[str, pd.Series], inputs: dict, factors: list[str] | None = None) -> dict[str, dict]:
    """候补队列用：每只日本票当前的顺风度（%/周）、说明、当日横截面三分位档（顺风 / 中性 / 逆风）。
    inputs = qbreak.threat.load_inputs() 的结果（与威胁指数共用一次下载）；inputs["commod"] 有商品价格时
    用扩展版（FACTORS_EXT 中能取到的因素）。只作参考，不参与交易。"""
    r, n225 = inputs["raw"], inputs["n225"]
    extra = {k: v for k, v in (inputs.get("commod") or {}).items() if k in EXT}
    factors = factors or (FACTORS + [k for k in EXT if k in extra])
    jp_days = n225.index[n225.index >= n225.index[-1] - pd.Timedelta(days=365 * 3)]
    lv = factor_levels(jp_days, n225, inputs["jgb"], r["DGS10"], r["DCOILWTICO"], inputs["fx"], r["BAA10Y"],
                       extra={k: extra[k] for k in factors if k in extra})
    W = weekly_changes(lv)
    X = W[factors + ["mkt"]]
    tr = trend(lv, jp_days[-1], factors=factors)
    out = {}
    for t, c in closes.items():
        s, why = fit_score(betas(stock_weekly(c, W.index), X, W.index[-1]), tr, factors)
        if s is not None:
            out[t] = {"fit": round(s, 3), "fit_why": why}
    if out:
        q = pd.Series({t: o["fit"] for t, o in out.items()}).rank(pct=True)
        for t in out:
            out[t]["fit_tier"] = "顺风" if q[t] > 2 / 3 else ("逆风" if q[t] <= 1 / 3 else "中性")
    return out
