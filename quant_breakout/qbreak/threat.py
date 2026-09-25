"""threat.py — 「大事件威胁指数」：把历史上大跌之前常见的因素做成 0–100 的综合分（只用当时已公布的数据）。

每个因素换成「扩张窗口百分位」（在它自己过去全部历史里排第几；至少 3 年历史才开始用），等权平均 → 0–100。
不拟合任何系数（避免过度拟合）。因素（方向：越高越危险）：
  vix      VIX 水平                           vix_d20  VIX 20 日变化
  credit   Baa−10Y 利差 60 日变化（走阔）       curve    −(10Y−3M)（越倒挂越高）
  rates    美 10Y 利率 60 日变化（急升）         oil      WTI 60 日涨幅（油价冲击）
  jobs     失业率 3 个月均值 − 过去 12 个月最低（Sahm 型；按公布时滞）
  rvol     指数 20 日实现波动（年化）
  （日経另加）yen  −(USD/JPY 20 日变化，%)（日元急升）   jgb  日本 10Y 60 日变化
时滞：VIX / 指数 / 汇率当天收盘可用；Baa、美债、WTI 滞后 1 个营业日；失业率次月 10 日起可用；日本 10Y 当天（財務省）。
研究与是否用于交易见 scripts/threat_index_study.py；日报展示当前值与历史同档位后的大跌频率。
"""
from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from .timing import monthly_available

US_COLS = ["vix", "vix_d20", "credit", "curve", "rates", "oil", "jobs", "rvol"]
JP_COLS = US_COLS + ["yen", "jgb"]
LABELS = {"vix": "VIX 水平", "vix_d20": "VIX 20 日变化", "credit": "信用利差走阔", "curve": "利率曲线倒挂",
          "rates": "美债利率急升", "oil": "油价冲击", "jobs": "失业率上升", "rvol": "指数波动", "yen": "日元急升",
          "jgb": "日债利率急升"}
MIN_N = 750


def _daily(s: pd.Series, days: pd.DatetimeIndex, lag: int = 0) -> pd.Series:
    s = s.dropna()
    return s.reindex(days.union(s.index)).ffill().reindex(days).shift(lag)


def raw_features(days: pd.DatetimeIndex, close: pd.Series, vix: pd.Series, baa: pd.Series, dgs10: pd.Series,
                 dgs3m: pd.Series, wti: pd.Series, unrate: pd.Series, usdjpy: pd.Series | None = None,
                 jgb10: pd.Series | None = None) -> pd.DataFrame:
    """days：该市场的交易日；close：该市场指数收盘（与 days 对齐）。美国因素对日本交易日用「前一个美国收盘」的值
    （调用方把 days 传成日本交易日时，先把美国序列错开一天：见 us_asof_for_jp）。"""
    f = pd.DataFrame(index=days)
    v = _daily(vix, days)
    f["vix"] = v
    f["vix_d20"] = v - v.shift(20)
    b = _daily(baa, days, 1)
    f["credit"] = b - b.shift(60)
    f["curve"] = -(_daily(dgs10, days, 1) - _daily(dgs3m, days, 1))
    r10 = _daily(dgs10, days, 1)
    f["rates"] = r10 - r10.shift(60)
    w = _daily(wti.where(wti > 0), days, 1)
    f["oil"] = w / w.shift(60) - 1
    un = unrate.dropna()
    sahm = un.rolling(3).mean() - un.rolling(3).mean().rolling(12).min()
    f["jobs"] = monthly_available(sahm, days)
    c = close.reindex(days)
    f["rvol"] = np.log(c).diff().rolling(20).std() * np.sqrt(252)
    if usdjpy is not None:
        fx = _daily(usdjpy, days)
        f["yen"] = -(fx / fx.shift(20) - 1) * 100
    if jgb10 is not None:
        j = _daily(jgb10, days)
        f["jgb"] = j - j.shift(60)
    return f


def expanding_pct(x: pd.Series, min_n: int = MIN_N) -> pd.Series:
    """x_t 在 x_0..x_t（有效值）里的百分位（0–1，含自己；平局取中位）。历史不足 min_n 个有效值时为 NaN。"""
    out = np.full(len(x), np.nan)
    hist: list[float] = []
    for i, v in enumerate(x.to_numpy(float)):
        if not np.isfinite(v):
            continue
        bisect.insort(hist, v)
        n = len(hist)
        if n >= min_n:
            lo, hi = bisect.bisect_left(hist, v), bisect.bisect_right(hist, v)
            out[i] = (lo + hi) / 2 / n
    return pd.Series(out, index=x.index)


def threat_index(raw: pd.DataFrame, cols: list[str], min_n: int = MIN_N) -> tuple[pd.Series, pd.DataFrame]:
    """等权平均各因素的扩张百分位 → 0–100；至少一半因素可用才给值。返回 (指数, 各因素百分位)。"""
    pct = pd.DataFrame({c: expanding_pct(raw[c], min_n) for c in cols if c in raw})
    ok = pct.notna().sum(axis=1) >= max(1, len(cols) // 2)
    idx = (pct.mean(axis=1) * 100).where(ok)
    return idx, pct


def us_asof_for_jp(s: pd.Series, jp_days: pd.DatetimeIndex) -> pd.Series:
    """美国的日序列 → 日本交易日 D 早上已知的值（D 之前最后一个美国收盘）。"""
    s = s.dropna()
    prev = jp_days - pd.Timedelta(days=1)
    v = s.reindex(s.index.union(prev)).ffill().reindex(prev)
    return pd.Series(v.to_numpy(float), index=jp_days)


def forward_drawdown(close: pd.Series, n: int = 60) -> pd.Series:
    """今天收盘之后 n 个交易日内的最低收盘相对今天的跌幅（负数；最后 n 天为 NaN）。"""
    c = close.to_numpy(float)
    out = np.full(len(c), np.nan)
    for i in range(len(c) - n):
        out[i] = c[i + 1:i + 1 + n].min() / c[i] - 1
    return pd.Series(out, index=close.index)


def auc(score: pd.Series, event: pd.Series) -> float | None:
    """ROC AUC（Mann–Whitney），只用两者都有值的日子。"""
    d = pd.DataFrame({"s": score, "e": event}).dropna()
    pos, neg = d[d["e"] > 0.5]["s"], d[d["e"] <= 0.5]["s"]
    if len(pos) == 0 or len(neg) == 0:
        return None
    r = d["s"].rank()
    return float((r[d["e"] > 0.5].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


# ══════════════════════════ 日报用：最新读数 ══════════════════════════
def _yf_close(sym: str) -> pd.Series:
    import logging
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    h = yf.Ticker(sym).history(period="max", auto_adjust=True)
    h.index = h.index.tz_localize(None).normalize()
    return h[~h.index.duplicated(keep="last")]["Close"]


def load_inputs() -> dict:
    """指数（yfinance 全历史）+ FRED + 財務省日本 10Y。与 scripts/threat_index_study.py 同一口径。"""
    from . import factors
    from .calendar_jp import now_jst
    spx = _yf_close("^GSPC")
    spx = spx[spx.index < pd.Timestamp(now_jst().date())]                  # 日本早上：美国前一日收盘已确定
    n225 = _yf_close("^N225")
    n = now_jst()
    if n.hour < 16 and len(n225) and n225.index[-1].date() == n.date():   # 当天未收盘的日経 K 线不用
        n225 = n225.iloc[:-1]
    fx = factors.fred("DEXJPUS").dropna()
    try:
        jpyx = _yf_close("JPY=X")
        jpyx = jpyx[(jpyx > 60) & (jpyx < 250) & (jpyx.index > fx.index[-1])]
        fx = pd.concat([fx, jpyx]).sort_index()
        fx = fx[~fx.index.duplicated(keep="first")]
    except Exception:                                                     # noqa: BLE001
        pass
    raw = {k: factors.fred(k) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO", "UNRATE")}
    return {"spx": spx, "n225": n225, "fx": fx, "raw": raw, "jgb": factors.jgb_curve()["10Y"].dropna()}


def build(d: dict) -> dict:
    """{"US": (指数, 百分位表), "JP": (…)}；日経用美国因素时取「前一个美国收盘」。"""
    r = d["raw"]
    us_days = d["spx"].index[d["spx"].index >= "1990-01-01"]
    raw_us = raw_features(us_days, d["spx"], r["VIXCLS"], r["BAA10Y"], r["DGS10"], r["DGS3MO"], r["DCOILWTICO"], r["UNRATE"])
    jp_days = d["n225"].index[d["n225"].index >= "1990-01-01"]
    m = {k: us_asof_for_jp(r[k], jp_days) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")}
    raw_jp = raw_features(jp_days, d["n225"], m["VIXCLS"], m["BAA10Y"], m["DGS10"], m["DGS3MO"], m["DCOILWTICO"],
                          r["UNRATE"], usdjpy=us_asof_for_jp(d["fx"], jp_days), jgb10=d["jgb"].shift(1))
    return {"US": threat_index(raw_us, US_COLS), "JP": threat_index(raw_jp, JP_COLS)}


def snapshot(built: dict | None = None, table: dict | None = None, events: list | None = None,
             today=None, horizon_days: int = 60, readings: dict | None = None) -> dict:
    """最新读数 + 同档位的历史频率（var/threat_index.json）+ 接下来的已知大事件日程（var/macro_events.json）。只展示。"""
    from . import paths
    from .utils import read_json
    built = built if built is not None else build(load_inputs())
    table = table if table is not None else (read_json(paths.home() / "threat_index.json", {}) or {})
    out = {"note": "只展示，不参与交易（2026-09-25 事先登记研究：美股 AUC 0.66、日経 0.58，不足以预测时间段）",
           "event_def": table.get("event", "之后 60 个交易日内最低收盘比当天跌 ≥10%")}
    for m in ("US", "JP"):
        idx, pct = built[m]
        s = idx.dropna()
        if s.empty:
            continue
        v = float(s.iloc[-1])
        t = table.get(m) or {}
        dec = next((b for b in t.get("deciles", []) if b["lo"] <= v < b["hi"]), None)
        top = pct.loc[s.index[-1]].dropna().sort_values(ascending=False)
        out[m] = {"date": str(s.index[-1].date()), "value": round(v, 1), "prev20": round(float(s.iloc[-21]), 1) if len(s) > 20 else None,
                  "band": f"{dec['lo']}–{dec['hi']}" if dec else None, "band_freq": dec["freq"] if dec else None,
                  "base_rate": t.get("base_rate"), "auc": [t.get("auc_h1"), t.get("auc_h2")],
                  "hit80": t.get("episodes_hit80"),
                  "top": [{"k": k, "label": LABELS[k], "pct": round(float(p) * 100)} for k, p in top.head(3).items()]}
    for m in ("US", "JP"):                                     # v3 新因素的当前百分位（只观察，不计入指数）
        if readings and m in out and (readings.get(m) or {}).get("obs"):
            out[m]["obs"] = readings[m]["obs"]
    ev = events if events is not None else (read_json(paths.home() / "macro_events.json", {}) or {})
    ev = ev.get("events", ev) if isinstance(ev, dict) else ev
    d0 = pd.Timestamp(today or pd.Timestamp.today().normalize())
    out["events"] = [e for e in (ev or []) if d0 <= pd.Timestamp(e.get("date", "1900-01-01")) <= d0 + pd.Timedelta(days=horizon_days)]
    out["events"].sort(key=lambda e: e["date"])
    return out


# ══════════════════════════ v2：更多直接因素 + 四种合成方式（研究见 scripts/threat_index_v2_study.py）══════════════════════════
V2_EXTRA = ["nfci", "stlfsi", "claims", "curve2", "rates2", "dollar", "skew", "dd52", "trend", "mom20", "vix_term",
            "move", "cu_au", "fed"]
US_V2 = US_COLS + V2_EXTRA
JP_V2 = JP_COLS + V2_EXTRA + ["yen_vol", "boj"]
LABELS.update({"nfci": "金融条件收紧（NFCI）", "stlfsi": "金融压力（STLFSI）", "claims": "初请失业金上升",
               "curve2": "10Y−2Y 倒挂", "rates2": "2 年美债急升", "dollar": "美元急升", "skew": "尾部风险定价（SKEW）",
               "dd52": "离一年高点的跌幅", "trend": "跌破 200 日线", "mom20": "近 20 日下跌", "vix_term": "VIX 期限倒挂",
               "move": "债券波动（MOVE）", "cu_au": "铜金比下降", "fed": "美联储一年加息幅度", "yen_vol": "日元波动",
               "boj": "日银一年加息幅度"})


def weekly_available(s: pd.Series, days: pd.DatetimeIndex, lag_days: int) -> pd.Series:
    """周度序列（索引 = 参考周的日期）在 lag_days 天后才公布 → 每个交易日已公布的最新值。"""
    s = s.dropna()
    a = pd.Series(s.to_numpy(float), index=s.index + pd.Timedelta(days=lag_days))
    return a.reindex(days.union(a.index)).ffill().reindex(days)


def raw_features_v2(base: pd.DataFrame, days: pd.DatetimeIndex, close: pd.Series, x: dict,
                    usdjpy: pd.Series | None = None, jp: bool = False) -> pd.DataFrame:
    """base：raw_features 的结果；x：{"NFCI","STLFSI4","ICSA","T10Y2Y","DGS2","DFF","DXY","SKEW","VIX3M","VIX","MOVE",
    "HG","GC","JPCALL"} 原始序列（美国的日序列对日本交易日要先用 us_asof_for_jp 对齐）。"""
    f = base.copy()
    f["nfci"] = weekly_available(x["NFCI"], days, 6)
    f["stlfsi"] = weekly_available(x["STLFSI4"], days, 7)
    cl = x["ICSA"].dropna().rolling(4).mean()
    f["claims"] = weekly_available(cl / cl.shift(13) - 1, days, 6)
    f["curve2"] = -_daily(x["T10Y2Y"], days, 1)
    r2 = _daily(x["DGS2"], days, 1)
    f["rates2"] = r2 - r2.shift(60)
    ff = _daily(x["DFF"], days, 1)
    f["fed"] = ff - ff.shift(250)
    dx = _daily(x["DXY"], days)
    f["dollar"] = dx / dx.shift(60) - 1
    f["skew"] = _daily(x["SKEW"], days)
    f["vix_term"] = _daily(x["VIX"], days) / _daily(x["VIX3M"], days)
    f["move"] = _daily(x["MOVE"], days)
    cg = _daily(x["HG"], days) / _daily(x["GC"], days)
    f["cu_au"] = -(cg / cg.shift(60) - 1)
    c = close.reindex(days)
    f["dd52"] = 1 - c / c.rolling(252, min_periods=200).max()
    f["trend"] = -(c / c.rolling(200).mean() - 1)
    f["mom20"] = -(c / c.shift(20) - 1)
    if jp:
        fx = _daily(usdjpy, days)
        f["yen_vol"] = np.log(fx).diff().rolling(20).std() * np.sqrt(252)
        call = x["JPCALL"].dropna()
        call = pd.Series(call.to_numpy(float), index=call.index + pd.offsets.MonthBegin(1))   # 月度，再晚一个月才用
        f["boj"] = monthly_available(call - call.shift(12), days, 1)
    return f


def tail_share(pct: pd.DataFrame, q: float = 0.8) -> pd.Series:
    """处在各自历史 80 分位以上的因素占比（0–100）；至少一半因素可用才给值。"""
    ok = pct.notna().sum(axis=1) >= max(1, pct.shape[1] // 2)
    return ((pct >= q).sum(axis=1) / pct.notna().sum(axis=1).replace(0, np.nan) * 100).where(ok)


def logit_fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 50) -> np.ndarray:
    """L2 正则逻辑回归（牛顿法）；X 不含常数列，返回 [截距, 系数...]。"""
    Xb = np.c_[np.ones(len(X)), X]
    w = np.zeros(Xb.shape[1])
    reg = np.full(Xb.shape[1], l2)
    reg[0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Xb @ w, -30, 30)))
        g = Xb.T @ (p - y) + reg * w
        H = (Xb * (p * (1 - p))[:, None]).T @ Xb + np.diag(reg)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def walkforward_logit(pct: pd.DataFrame, event: pd.Series, start: str = "1995-01-01", first: str = "2000-01-01",
                      horizon: int = 60, l2: float = 1.0) -> pd.Series:
    """每年第一个交易日重估一次：只用「答案已经知道」的样本（该日之前 horizon 个交易日以前、start 以后），
    缺失因素按 0.5（中性）；输出 0–100 的预测概率。"""
    X = pct.fillna(0.5).to_numpy(float) - 0.5
    y = event.to_numpy(float)
    idx = pct.index
    out = np.full(len(idx), np.nan)
    years = sorted({d.year for d in idx if d >= pd.Timestamp(first)})
    for yr in years:
        pos = np.flatnonzero((idx >= pd.Timestamp(f"{yr}-01-01")) & (idx < pd.Timestamp(f"{yr + 1}-01-01")))
        if not len(pos):
            continue
        k0 = pos[0]
        train = np.flatnonzero((idx >= pd.Timestamp(start)) & (np.arange(len(idx)) <= k0 - horizon - 1) & np.isfinite(y))
        if len(train) < 250 or len(np.unique(y[train])) < 2:
            continue
        w = logit_fit(X[train], y[train], l2)
        out[pos] = 100 / (1 + np.exp(-np.clip(np.c_[np.ones(len(pos)), X[pos]] @ w, -30, 30)))
    return pd.Series(out, index=idx)


# ═══════════ v3：贵金属 / 铜 / 天然气 / 粮食 / 商品综合 / 银行信贷（破产的代理）/ 地缘风险（研究见 scripts/threat_index_v3_study.py）═══════════
# 破产件数：美国 FRED 没有、日本 TSR / 帝国数据库只公开年表或近月报告 → 没有可回测的长期序列，
# 用在破产增加之前或同时恶化的银行信贷指标代替（美国 SLOOS 贷款标准、企业贷款拖欠率 / 核销率；日本短观贷款态度 / 资金周转）。
V3_EXTRA = ["gold", "gold_silver", "copper", "natgas", "grains", "commod", "commod_vol", "sloos", "delinq", "chargeoff",
            "gpr", "gpr_jump", "epu"]
JP_V3_ONLY = ["tankan_lend", "tankan_cash", "jp_lng", "gpr_jp"]
US_V3 = US_V2 + V3_EXTRA
JP_V3 = JP_V2 + V3_EXTRA + JP_V3_ONLY
LABELS.update({"gold": "黄金急涨（避险）", "gold_silver": "金银比上升", "copper": "铜价下跌", "natgas": "天然气急涨",
               "grains": "粮食价格急涨", "commod": "商品综合急涨", "commod_vol": "商品波动",
               "sloos": "银行收紧企业贷款（SLOOS）", "delinq": "企业贷款拖欠率上升", "chargeoff": "企业贷款核销率上升",
               "gpr": "地缘政治风险（GPR）", "gpr_jump": "地缘风险急升", "epu": "政策不确定性（EPU）",
               "tankan_lend": "短观：银行贷款态度收紧", "tankan_cash": "短观：企业资金周转恶化", "jp_lng": "日本 LNG 价格急涨",
               "gpr_jp": "涉日地缘风险"})
CATEGORY = {"波动": ["vix", "vix_d20", "rvol", "vix_term", "move", "skew", "yen_vol"],
            "信用 / 破产代理": ["credit", "nfci", "stlfsi", "sloos", "delinq", "chargeoff", "tankan_lend", "tankan_cash"],
            "利率": ["curve", "curve2", "rates", "rates2", "fed", "jgb", "boj"],
            "商品": ["oil", "cu_au", "gold", "gold_silver", "copper", "natgas", "grains", "commod", "commod_vol", "jp_lng"],
            "就业": ["jobs", "claims"],
            "趋势": ["dd52", "trend", "mom20"],
            "汇率": ["dollar", "yen"],
            "地缘 / 不确定性": ["gpr", "gpr_jump", "epu", "gpr_jp"]}
V3_YF = {"GC": "GC=F", "SI": "SI=F", "HG": "HG=F", "NG": "NG=F", "ZW": "ZW=F", "ZC": "ZC=F", "ZS": "ZS=F", "GSCI": "^SPGSCI"}
V3_FRED = {"SLOOS": "DRTSCILM", "DELINQ": "DRBLACBS", "CHARGEOFF": "CORBLACBS", "EPU": "USEPUINDXD", "JPLNG": "PNGASJPUSDM"}
V3_TANKAN = {"TK_LEND": "TK99F0000612GCQ00000", "TK_CASH": "TK99F0000609GCQ00000"}   # 全规模・全产业 实绩 DI


def gpr_available(s: pd.Series, days: pd.DatetimeIndex, extra_days: int = 1) -> pd.Series:
    """GPR 日度每周一更新（含当天为止）→ 日期 d 的值在 d 之后（含）第一个周一再过 extra_days 天可用。"""
    s = s.dropna()
    monday = s.index + pd.to_timedelta((7 - s.index.weekday) % 7, unit="D")
    a = pd.Series(s.to_numpy(float), index=monday + pd.Timedelta(days=extra_days)).groupby(level=0).last()
    return a.reindex(days.union(a.index)).ffill().reindex(days)


def raw_features_v3(base: pd.DataFrame, days: pd.DatetimeIndex, x: dict, jp: bool = False) -> pd.DataFrame:
    """base：raw_features_v2 的结果。x：V3_YF 的日序列（日本交易日要先用 us_asof_for_jp 对齐）+ V3_FRED / V3_TANKAN /
    "GPRD"（日度）/ "GPRC_JPN"（月度）原始序列。按日历日计的发布时滞，日本再多等 1 天。"""
    f = base.copy()
    lagd = 1 if jp else 0
    px = {k: _daily(x[k], days) for k in V3_YF}
    ch60 = {k: v / v.shift(60) - 1 for k, v in px.items()}
    f["gold"] = ch60["GC"]
    gs = px["GC"] / px["SI"]
    f["gold_silver"] = gs / gs.shift(60) - 1
    f["copper"] = -ch60["HG"]
    f["natgas"] = ch60["NG"]
    f["grains"] = pd.concat([ch60["ZW"], ch60["ZC"], ch60["ZS"]], axis=1).mean(axis=1, skipna=False)
    f["commod"] = ch60["GSCI"]
    f["commod_vol"] = np.log(px["GSCI"]).diff().rolling(20).std() * np.sqrt(252)
    f["sloos"] = weekly_available(x["SLOOS"], days, 45 + lagd)                         # 季度调查，约 5 周后公布
    for k, col in (("DELINQ", "delinq"), ("CHARGEOFF", "chargeoff")):                 # 季度，季末约 2 个月后公布
        q = x[k].dropna()
        f[col] = weekly_available(q - q.shift(4), days, 160 + lagd)
    gd = x["GPRD"].dropna()
    g30 = gd.rolling(30).mean()
    f["gpr"] = gpr_available(g30, days, 1 + lagd)
    f["gpr_jump"] = gpr_available(g30 / gd.rolling(365, min_periods=300).mean() - 1, days, 1 + lagd)
    f["epu"] = weekly_available(x["EPU"].dropna().rolling(30, min_periods=20).mean(), days, 2 + lagd)
    if jp:
        for k, col in (("TK_LEND", "tankan_lend"), ("TK_CASH", "tankan_cash")):       # 索引 = 调查季末；约 1～5 天后公布
            q = x[k].dropna()
            f[col] = weekly_available(-(q - q.shift(4)), days, 5)
        lng = x["JPLNG"].dropna()
        yoy = lng / lng.shift(12) - 1                                                 # IMF 月度，约 2 个月后才有
        f["jp_lng"] = weekly_available(pd.Series(yoy.to_numpy(float), index=yoy.index + pd.DateOffset(months=3)), days, 0)
        f["gpr_jp"] = monthly_available(x["GPRC_JPN"].dropna().rolling(3).mean(), days, 5)
    return f


def category_mean(pct: pd.DataFrame) -> pd.Series:
    """先在 CATEGORY 各类内部平均，再对有值的类别等权平均（0–100）；至少一半类别有值才给值。"""
    cats = {c: [k for k in ks if k in pct] for c, ks in CATEGORY.items()}
    cm = pd.DataFrame({c: pct[ks].mean(axis=1) for c, ks in cats.items() if ks})
    ok = cm.notna().sum(axis=1) >= max(1, cm.shape[1] // 2)
    return (cm.mean(axis=1) * 100).where(ok)


def load_extra_all() -> dict:
    """v2 + v3 需要的全部原始序列（FRED / yfinance / 日銀 API / GPR）。"""
    from . import factors
    x = {k: factors.fred(k) for k in ("NFCI", "STLFSI4", "ICSA", "T10Y2Y", "DGS2", "DFF")}
    x["JPCALL"] = factors.fred("IRSTCI01JPM156N")
    x["VIX"] = factors.fred("VIXCLS")
    for k, sym in (("DXY", "DX-Y.NYB"), ("SKEW", "^SKEW"), ("VIX3M", "^VIX3M"), ("MOVE", "^MOVE")):
        x[k] = factors.yf_close(sym)
    for k, sym in V3_YF.items():
        x[k] = factors.despike(factors.yf_close(sym))
    for k, sid in V3_FRED.items():
        x[k] = factors.fred(sid)
    for k, code in V3_TANKAN.items():
        x[k] = factors.tankan(code)
    x["GPRD"] = factors.gpr_daily()["GPRD"]
    x["GPRC_JPN"] = factors.gpr_monthly()["GPRC_JPN"]
    return x


US_DAILY_V2 = ("T10Y2Y", "DGS2", "DFF", "DXY", "SKEW", "VIX", "VIX3M", "MOVE", "HG", "GC")


def build_all(d: dict, x: dict) -> dict:
    """v1 + v2 + v3 全部因素的原始值：{"US": (特征表, 指数收盘), "JP": (…)}。日本交易日用前一个美国收盘。"""
    r = d["raw"]
    us_days = d["spx"].index[d["spx"].index >= "1990-01-01"]
    base_us = raw_features(us_days, d["spx"], r["VIXCLS"], r["BAA10Y"], r["DGS10"], r["DGS3MO"], r["DCOILWTICO"], r["UNRATE"])
    f_us = raw_features_v3(raw_features_v2(base_us, us_days, d["spx"], x), us_days, x)
    jp_days = d["n225"].index[d["n225"].index >= "1990-01-01"]
    m = {k: us_asof_for_jp(r[k], jp_days) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")}
    fxj = us_asof_for_jp(d["fx"], jp_days)
    base_jp = raw_features(jp_days, d["n225"], m["VIXCLS"], m["BAA10Y"], m["DGS10"], m["DGS3MO"], m["DCOILWTICO"],
                           r["UNRATE"], usdjpy=fxj, jgb10=d["jgb"].shift(1))
    xj = dict(x)
    for k in set(US_DAILY_V2) | set(V3_YF):
        xj[k] = us_asof_for_jp(x[k], jp_days)
    f_jp = raw_features_v3(raw_features_v2(base_jp, jp_days, d["n225"], xj, usdjpy=fxj, jp=True), jp_days, xj, jp=True)
    return {"US": (f_us, d["spx"].reindex(us_days)), "JP": (f_jp, d["n225"].reindex(jp_days))}


def _eq(p: pd.DataFrame) -> pd.Series:
    if p.shape[1] == 0:
        return pd.Series(np.nan, index=p.index)
    return (p.mean(axis=1) * 100).where(p.notna().sum(axis=1) >= max(1, p.shape[1] // 2))


def v3_selection() -> dict:
    """v3 研究在训练期（1995–2010）选入的因素（B2 / B4 用）：{"US": [...], "JP": [...]}；没有研究结果时为空。"""
    from . import paths
    from .utils import read_json
    r = read_json(paths.out_dir() / "threat_index_v3_study.json", {}) or {}
    return {m: (r.get(m) or {}).get("selected_v3") or [] for m in ("US", "JP")}


def v3_readings(F: dict, sel: dict | None = None) -> dict:
    """最新一天：A0 与 B1～B4 的读数（前瞻记录用）+ 新因素的当前百分位（日报「其他观察因子」）。F = build_all(...)。"""
    sel = sel or {}
    out = {}
    for m in ("US", "JP"):
        raw, _ = F[m]
        v1, v3 = (US_COLS, US_V3) if m == "US" else (JP_COLS, JP_V3)
        pct = pd.DataFrame({c: expanding_pct(raw[c]) for c in v3})
        s = [c for c in sel.get(m, []) if c in pct]
        idx = {"A0": _eq(pct[v1]), "B1": _eq(pct[v3]), "B2": _eq(pct[s]) if s else None,
               "B3": category_mean(pct[v3]), "B4": category_mean(pct[s]) if s else None}
        last = pct.index[-1]
        new = V3_EXTRA + (JP_V3_ONLY if m == "JP" else [])
        obs = [{"k": c, "label": LABELS[c], "pct": round(float(pct.at[last, c]) * 100)} for c in new if pct.at[last, c] == pct.at[last, c]]
        out[m] = {"date": str(last.date()),
                  "idx": {k: (round(float(v.iloc[-1]), 1) if v is not None and v.iloc[-1] == v.iloc[-1] else None) for k, v in idx.items()},
                  "obs": sorted(obs, key=lambda o: -o["pct"])}
    return out


def log_forward(readings: dict, path) -> None:
    """每天追加 A0 与 B1～B4 的读数（同一数据日重复运行只保留最后一次），用于以后做真正的样本外比较。"""
    rows = pd.DataFrame([{"date": r["date"], "market": m, **r["idx"]} for m, r in readings.items()])
    if path.exists():
        rows = pd.concat([pd.read_csv(path), rows]).drop_duplicates(["date", "market"], keep="last")
    rows.sort_values(["date", "market"]).to_csv(path, index=False)
