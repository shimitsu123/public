"""pressure_study.py — 股市「压力指数」：每涨一次加压、每跌一次释放，越涨压力越大；再加国债 / 利率 / 信用 / 波动 / 宽度
（2026-09-29 登记；只跑一次，看完不改规则）。

用户：「在上涨 / 下跌的时候每次下跌 / 上涨等于释放 / 增加压力，越上涨压力越大，越下跌压力越小；结合当前所有研究出来的结果、国债、利率、
股市宽度等等各式各样的因子，做一个现在股市的压力指数研究」。
以前知道的（var/sim_changes.md）：威胁指数一类（跌破 200 日线、VIX、信用利差扩大）是「正在跌」的同步信号，美国 60 天内跌 ≥ 10% 的
AUC 0.61〜0.81；反过来说，离 200 日线越远、越接近新高，之后 60 天越不容易跌（美国），日本不稳定。「涨了多少 / 多久没回调」当作
压力从来没有检验过，估值（CAPE、市值 / GDP）在 60 天没有预测力。压力是慢慢积累的 → 主判定看 1 年（250 个交易日），60 / 120 / 500 天另报。

一 指数（每个月最后一个交易日算，只用那天能知道的数据）。7 个分项，方向事先定为「上涨行情里它通常往哪边走 = 加压」：
   1 涨幅（用户的机制）：log(收盘 ÷ 过去 500 个交易日的最低收盘)——每涨一天加压、每跌一天释放，跌回两年低点 = 0
   2 长期乖离：log(收盘 ÷ 250 日均线)
   3 利率上升：10 年国债利回り 12 个月的变化（美国 GS10 月均，用上个月的；日本 财务省 10 年，用前一天的）
   4 曲线变平 / 倒挂：−(10 年 − 短期)（美国 GS10 − TB3MS，上个月；日本 10 年 − 1 年，前一天）
   5 信用利差收窄（自满）：−(BAA − GS10)（上个月；日本没有长期的信用利差，用同一个美国值当全球信用环境）
   6 波动低（平静）：−过去 60 个交易日日收益的年化标准差
   7 宽度：美国 = Ken French 49 行业里（累计收益指数）在 200 日线之上的比例；日本 = 现在的日経225 成分（Yahoo，2000 年起，
     有幸存者偏差）在 200 日线之上的比例（有值的 < 100 只 → 空）
   每个分项 → 分位 0〜100 = 这个月末的值在过去 120 个月末（含本月）里的位置（≤ 它的比例），至少 60 个月才算。
   价格压力 P_price = 平均(1, 2)（用户的机制本身）；综合压力 P_all = 平均(1〜7 里有值的，至少 4 个)。
   分项（只描述）：利率 = 平均(3, 4)、自满 = 平均(5, 6)、宽度 = 7。
二 目标：月末 t 之后 H 个交易日内最低收盘 ÷ t 收盘 − 1 ≤ −10%（主 H = 250「一年内跌 ≥ 10%」；另报 60 / 120 / 500），另报之后 H 天的涨跌。
   美国 = S&P 500（^GSPC）1960-01〜；日本 = 日経225（^N225）从 1〜6 的分位都有值的第一个月末起（10 年国债 1986-07〜 → 约 1992 年）。
   德国 DAX / 英国 FTSE 100 只算 P_price（只描述）。
三 判定（事先写定；P_price 与 P_all 各判一次；AUC > 0.5 = 压力越高越容易一年内跌 ≥ 10%）：
   AUC 的 95% 区间 = 按 24 个月一段整段重抽 2,000 次（种子 20260929）。
   「有预警力」：美国 AUC ≥ 0.60 且区间下限 > 0.50、美国前后两半（1960〜1992 / 1993〜）都 > 0.50、日本 AUC ≥ 0.55；
   「方向相反」：美国 AUC ≤ 0.40 且区间上限 < 0.50（越涨越不容易跌）；其余「没有预警力」。
四 另报（只描述，不参与判定）：五分位（最高 1/5 与最低 1/5 的「一年内跌 ≥ 10%」比例、之后一年涨跌）；只看牛熊分界 = 牛的月末
   （美国用 S&P 500 的 T0，日本用日経225 自己的同一规则）；现在的读数（最新一天：各分项分位、近 3 个月在加压还是释放、
   历史上同一五分位之后一年跌 ≥ 10% 的比例）。
五 结果怎么用：「有预警力」→ 提议日报加一栏（只展示；要用到交易另外登记账户层检验、要你确认）；
   「方向相反」/「没有预警力」→ 不进日报，只报现在的读数与历史上同一档之后的情况。
输出：var/out/pressure_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

HS, H_MAIN, DROP = (60, 120, 250, 500), 250, -10.0
RUNUP_D, MA_D, VOL_D, BR_MA = 500, 250, 60, 200
WIN_M, MIN_M, MIN_COMP, BR_MIN_N = 120, 60, 4, 100
BLOCK_M, N_BOOT, SEED = 24, 2000, 20260929
US_START, US_SPLIT = "1960-01-01", "1993-01-01"
COMP = ["runup", "ma", "rate", "curve", "credit", "calm", "breadth"]
LABEL = {"runup": "涨幅（离两年低点）", "ma": "长期乖离（250 日线）", "rate": "利率上升（12 个月）", "curve": "曲线变平 / 倒挂",
         "credit": "信用利差收窄", "calm": "波动低（平静）", "breadth": "宽度（200 日线之上的比例）"}


# ─────────────── 分项（每天或每月的原始值；方向 = 高是加压） ───────────────
def price_parts(c: pd.Series) -> pd.DataFrame:
    c = c.dropna().astype(float)
    lr = np.log(c).diff()
    return pd.DataFrame({"runup": np.log(c / c.rolling(RUNUP_D, min_periods=RUNUP_D).min()),
                         "ma": np.log(c / c.rolling(MA_D, min_periods=MA_D).mean()),
                         "calm": -lr.rolling(VOL_D, min_periods=VOL_D).std() * np.sqrt(252) * 100}, index=c.index)


def month_lag1(s: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """月度序列（FRED 的日期 = 那个月 1 日，值 = 那个月的平均）→ 每个日期用「上个月」的值。"""
    s = s.dropna().copy()
    s.index = pd.DatetimeIndex(s.index).to_period("M")
    prev = pd.DatetimeIndex(dates).to_period("M") - 1
    return pd.Series(s.reindex(prev).to_numpy(float), index=dates)


def day_lag1(s: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """每日序列 → 每个日期用「前一天（严格早于）」最后一个值。"""
    s = s.dropna().sort_index()
    pos = s.index.searchsorted(pd.DatetimeIndex(dates), side="left") - 1
    v = np.where(pos >= 0, s.to_numpy(float)[np.clip(pos, 0, None)], np.nan)
    return pd.Series(v, index=dates)


def asof(s: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """每个日期用「当天或之前」最后一个值。"""
    s = s.dropna().sort_index()
    pos = s.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    v = np.where(pos >= 0, s.to_numpy(float)[np.clip(pos, 0, None)], np.nan)
    return pd.Series(v, index=dates)


def breadth_share(closes: pd.DataFrame, ma: int = BR_MA, min_n: int = 1) -> pd.Series:
    """每天在 ma 日线之上的比例（%；只数有均线的）；有值的 < min_n → 空。"""
    m = closes.rolling(ma, min_periods=ma).mean()
    ok = m.notna() & closes.notna()
    n = ok.sum(axis=1)
    share = ((closes > m) & ok).sum(axis=1) / n.where(n > 0) * 100
    return share.where(n >= min_n)


def month_ends(c: pd.Series) -> pd.DatetimeIndex:
    c = c.dropna()
    return pd.DatetimeIndex(c.groupby(c.index.to_period("M")).tail(1).index)


def rolling_pct(x: pd.Series, win: int = WIN_M, min_n: int = MIN_M) -> pd.Series:
    """月末序列 → 本月的值在过去 win 个月末（含本月）里的分位（≤ 它的比例 × 100）；有值的 < min_n → 空。"""
    v = x.to_numpy(float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        if not np.isfinite(v[i]):
            continue
        w = v[max(0, i - win + 1):i + 1]
        w = w[np.isfinite(w)]
        if len(w) >= min_n:
            out[i] = float((w <= v[i]).mean() * 100)
    return pd.Series(out, index=x.index)


def scores(raw: pd.DataFrame) -> pd.DataFrame:
    """月末的原始分项 → 各分项分位 + P_price / P_all / 分项平均。"""
    pct = pd.DataFrame({k: rolling_pct(raw[k]) if k in raw else np.nan for k in COMP}, index=raw.index)
    out = pct.add_prefix("p_")
    out["P_price"] = pct[["runup", "ma"]].mean(axis=1, skipna=False)
    n = pct.notna().sum(axis=1)
    out["P_all"] = pct.mean(axis=1).where(n >= MIN_COMP)
    out["P_rate"] = pct[["rate", "curve"]].mean(axis=1, skipna=False)
    out["P_calm"] = pct[["credit", "calm"]].mean(axis=1, skipna=False)
    out["P_breadth"] = pct["breadth"]
    return out


def targets(c: pd.Series, dates: pd.DatetimeIndex, hs=HS) -> pd.DataFrame:
    """月末 t 之后 H 个交易日：最低 ÷ t 收盘 − 1（%）、事件（≤ −10%）、H 天后的涨跌（%）；不够 H 天 → 空。"""
    c = c.dropna()
    a = c.to_numpy(float)
    k = c.index.get_indexer(pd.DatetimeIndex(dates))
    out = {}
    for h in hs:
        mn, rt = np.full(len(k), np.nan), np.full(len(k), np.nan)
        for j, i in enumerate(k):
            if i >= 0 and i + h < len(a):
                mn[j] = (a[i + 1:i + h + 1].min() / a[i] - 1) * 100
                rt[j] = (a[i + h] / a[i] - 1) * 100
        out[f"min{h}"], out[f"ret{h}"] = mn, rt
        out[f"ev{h}"] = np.where(np.isfinite(mn), (mn <= DROP).astype(float), np.nan)
    return pd.DataFrame(out, index=dates)


# ─────────────── 统计 ───────────────
def auc(score: pd.Series, event: pd.Series) -> float | None:
    from qbreak.threat import auc as _auc
    return _auc(score, event)


def boot_auc(score: pd.Series, event: pd.Series, block: int = BLOCK_M, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float] | None:
    """按时间顺序的月末样本，24 个月一段（环形）整段重抽 → AUC 的 2.5% / 97.5% 分位。"""
    d = pd.DataFrame({"s": score, "e": event}).dropna()
    n = len(d)
    if n < 2 * block or d["e"].nunique() < 2:
        return None
    s, e = d["s"].to_numpy(float), d["e"].to_numpy(float)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        starts = rng.integers(0, n, int(np.ceil(n / block)))
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        a = auc(pd.Series(s[idx]), pd.Series(e[idx]))
        if a is not None:
            vals.append(a)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def verdict(us: dict, jp: dict) -> str:
    """us = {auc, lo, hi, half1, half2}；jp = {auc}。"""
    a, lo, hi = us.get("auc"), us.get("lo"), us.get("hi")
    if a is None or lo is None:
        return "样本不足"
    if a >= 0.60 and lo > 0.50 and (us.get("half1") or 0) > 0.50 and (us.get("half2") or 0) > 0.50 and (jp.get("auc") or 0) >= 0.55:
        return "有预警力"
    if a <= 0.40 and hi < 0.50:
        return "方向相反"
    return "没有预警力"


def quintiles(score: pd.Series, T: pd.DataFrame, h: int = H_MAIN) -> list[dict]:
    d = pd.DataFrame({"s": score, "ev": T[f"ev{h}"], "ret": T[f"ret{h}"]}).dropna()
    if len(d) < 25:
        return []
    q = pd.qcut(d["s"].rank(method="first"), 5, labels=False)
    return [{"q": int(i) + 1, "n": int((q == i).sum()), "lo": round(float(d["s"][q == i].min()), 1), "hi": round(float(d["s"][q == i].max()), 1),
             "event": round(float(d["ev"][q == i].mean() * 100), 1), "ret": round(float(d["ret"][q == i].mean()), 2)} for i in range(5)]


def t0_bear(c: pd.Series) -> pd.Series:
    from qbreak.bullbear import BEAR, Detector, load_config
    d = load_config()["detector"]
    c = c.dropna()
    return pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(c)) == BEAR, index=c.index)


# ─────────────── 数据 ───────────────
def index_close(sym: str, session: str | None = None) -> pd.Series:
    from bullbear_study import load
    from qbreak.trader import drop_partial_bar
    df = load(sym, "1900-01-01")
    if session:
        df = drop_partial_bar(df, session)
    return df["Close"].astype(float)


def us_raw(c: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    import crash_mainline_study as CM
    from qbreak import factors as F
    pp = price_parts(c).reindex(dates)
    y10, y3, baa = F.fred("GS10"), F.fred("TB3MS"), F.fred("BAA")
    y10l = month_lag1(y10, dates)
    y10l13 = month_lag1(y10.shift(12), dates)                                # shift 在月度序列上：12 个月前的月均
    ind = CM.us_ind49()
    idx = (1 + ind.clip(lower=-0.99)).cumprod().where(ind.notna())
    br = breadth_share(idx, min_n=20)
    return pd.DataFrame({"runup": pp["runup"], "ma": pp["ma"], "rate": y10l - y10l13, "curve": -(y10l - month_lag1(y3, dates)),
                         "credit": -(month_lag1(baa, dates) - y10l), "calm": pp["calm"], "breadth": asof(br, dates)}, index=dates)


def jp_raw(c: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    import leap_data as LD
    from qbreak import factors as F
    from qbreak.config import universe
    pp = price_parts(c).reindex(dates)
    j = F.jgb_curve()
    y10, y1 = j["10Y"].dropna(), j["1Y"].dropna()
    y10d = day_lag1(y10, dates)
    y10y = day_lag1(y10, pd.DatetimeIndex(dates) - pd.DateOffset(years=1))
    y10y.index = dates
    y10g, baa = F.fred("GS10"), F.fred("BAA")
    m = LD.ohlcv(sorted(universe("JP", "broad")))
    C = pd.DataFrame({t: df["Close"] for t, df in m.items() if df is not None and len(df)}).sort_index()
    br = breadth_share(C, min_n=BR_MIN_N)
    return pd.DataFrame({"runup": pp["runup"], "ma": pp["ma"], "rate": y10d - y10y, "curve": -(y10d - day_lag1(y1, dates)),
                         "credit": -(month_lag1(baa, dates) - month_lag1(y10g, dates)), "calm": pp["calm"], "breadth": asof(br, dates)},
                        index=dates)


def evaluate(S: pd.DataFrame, T: pd.DataFrame, start: str | None = None, split: str | None = None, bear: pd.Series | None = None) -> dict:
    out = {}
    for sc in ("P_price", "P_all", "P_rate", "P_calm", "P_breadth"):
        s = S[sc] if start is None else S[sc][S.index >= pd.Timestamp(start)]
        r = {}
        for h in HS:
            a = auc(s, T[f"ev{h}"])
            r[f"auc{h}"] = None if a is None else round(a, 3)
        ci = boot_auc(s, T[f"ev{H_MAIN}"])
        r["lo"], r["hi"] = (None, None) if ci is None else (round(ci[0], 3), round(ci[1], 3))
        if split:
            for nm, m in (("half1", s.index < pd.Timestamp(split)), ("half2", s.index >= pd.Timestamp(split))):
                a = auc(s[m], T[f"ev{H_MAIN}"])
                r[nm] = None if a is None else round(a, 3)
        if bear is not None:
            b = bear.reindex(s.index).fillna(False).astype(bool)
            a = auc(s[~b], T[f"ev{H_MAIN}"])
            r["auc_bull"] = None if a is None else round(a, 3)
        d = pd.DataFrame({"s": s, "e": T[f"ev{H_MAIN}"]}).dropna()
        r["n"], r["base"] = int(len(d)), (round(float(d["e"].mean() * 100), 1) if len(d) else None)
        r["q"] = quintiles(s, T)
        out[sc] = r
    return out


def now_reading(raw: pd.DataFrame, cur: pd.Series, S: pd.DataFrame, T: pd.DataFrame) -> dict:
    """最新一天：cur = 当天的原始分项；分位 = 在过去 119 个月末 + 当天里的位置。"""
    pct = {}
    for k in COMP:
        v = cur.get(k)
        hist = raw[k].dropna().iloc[-(WIN_M - 1):]
        if v is None or not np.isfinite(v) or len(hist) + 1 < MIN_M:
            pct[k] = None
            continue
        w = np.append(hist.to_numpy(float), v)
        pct[k] = round(float((w <= v).mean() * 100), 1)
    have = [v for v in pct.values() if v is not None]
    p_price = None if pct["runup"] is None or pct["ma"] is None else round((pct["runup"] + pct["ma"]) / 2, 1)
    p_all = round(float(np.mean(have)), 1) if len(have) >= MIN_COMP else None
    out = {"pct": pct, "P_price": p_price, "P_all": p_all, "raw": {k: (None if not np.isfinite(cur.get(k, np.nan)) else round(float(cur[k]), 4)) for k in COMP}}
    last3 = S["P_all"].dropna()
    if len(last3) >= 3 and p_all is not None:
        out["chg3m"] = round(p_all - float(last3.iloc[-3]), 1)
    for sc, v in (("P_price", p_price), ("P_all", p_all)):
        d = pd.DataFrame({"s": S[sc], "e": T[f"ev{H_MAIN}"], "r": T[f"ret{H_MAIN}"]}).dropna()
        if v is None or len(d) < 25:
            continue
        qs = d["s"].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
        qi = int(np.searchsorted(qs, v, side="right"))
        lo, hi = ([-np.inf] + list(qs))[qi], (list(qs) + [np.inf])[qi]
        m = (d["s"] > lo) & (d["s"] <= hi) if qi else d["s"] <= hi
        out[f"{sc}_q"] = {"q": qi + 1, "n": int(m.sum()), "event": round(float(d["e"][m].mean() * 100), 1), "ret": round(float(d["r"][m].mean()), 2),
                          "base": round(float(d["e"].mean() * 100), 1)}
    return out


def build(mkt: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    sym, sess = {"US": ("^GSPC", "US"), "JP": ("^N225", "JP")}[mkt]
    c = index_close(sym, sess)
    dates = month_ends(c)[:-1]                                              # 最后一个月还没结束
    raw = (us_raw if mkt == "US" else jp_raw)(c, dates)
    S = scores(raw)
    T = targets(c, dates)
    last = pd.DatetimeIndex([c.index[-1]])
    cur = (us_raw if mkt == "US" else jp_raw)(c, last).iloc[0]
    return raw, S, T, cur, c


def main() -> int:
    res, now, meta = {}, {}, {}
    for mkt in ("US", "JP"):
        raw, S, T, cur, c = build(mkt)
        if mkt == "US":
            start = US_START
        else:
            need = S[["p_runup", "p_ma", "p_rate", "p_curve", "p_credit", "p_calm"]].notna().all(axis=1)
            start = str(need[need].index[0].date())
        m = S.index >= pd.Timestamp(start)
        S, T = S[m], T[m]
        res[mkt] = evaluate(S, T, split=US_SPLIT if mkt == "US" else None, bear=t0_bear(c).reindex(S.index, method="ffill"))
        now[mkt] = now_reading(raw, cur, S, T)
        meta[mkt] = {"start": start, "end_eval": str(T[f"ev{H_MAIN}"].dropna().index[-1].date()), "last_day": str(c.index[-1].date())}
    eu = {}
    for nm, sym in (("DAX", "^GDAXI"), ("FTSE 100", "^FTSE")):
        c = index_close(sym)
        dates = month_ends(c)[:-1]
        pp = price_parts(c).reindex(dates)
        s = pd.DataFrame({"runup": rolling_pct(pp["runup"]), "ma": rolling_pct(pp["ma"])}).mean(axis=1, skipna=False)
        T = targets(c, dates)
        a = auc(s, T[f"ev{H_MAIN}"])
        eu[nm] = {"auc250": None if a is None else round(a, 3), "n": int(pd.DataFrame({"s": s, "e": T[f"ev{H_MAIN}"]}).dropna().shape[0])}
    ver = {sc: verdict({"auc": res["US"][sc][f"auc{H_MAIN}"], "lo": res["US"][sc]["lo"], "hi": res["US"][sc]["hi"],
                        "half1": res["US"][sc].get("half1"), "half2": res["US"][sc].get("half2")},
                       {"auc": res["JP"][sc][f"auc{H_MAIN}"]}) for sc in ("P_price", "P_all")}
    fm = lambda x, f="{:.3f}": "—" if x is None else f.format(x)                                    # noqa: E731
    L = ["# 股市压力指数（2026-09-29 登记，只跑一次；规则见 scripts/pressure_study.py 开头）", "",
         f"判定（一年内跌 ≥ 10%，AUC > 0.5 = 压力越高越容易跌）：价格压力（用户的机制）**{ver['P_price']}**；综合压力 **{ver['P_all']}**", "",
         f"样本：美国 {meta['US']['start']}〜{meta['US']['end_eval']} 的月末；日本 {meta['JP']['start']}〜{meta['JP']['end_eval']}", "",
         "| 市场 | 指数 | AUC 60 天 | 120 天 | **250 天**（95% 区间） | 500 天 | 前半 / 后半 | 只看牛市 | 月末数 / 一年内跌 ≥ 10% 的比例 |",
         "|---|---|---|---|---|---|---|---|---|"]
    nm = {"P_price": "价格压力", "P_all": "综合压力", "P_rate": "利率分项", "P_calm": "自满分项", "P_breadth": "宽度分项"}
    for mkt in ("US", "JP"):
        for sc, r in res[mkt].items():
            L.append(f"| {mkt} | {nm[sc]} | {fm(r['auc60'])} | {fm(r['auc120'])} | **{fm(r['auc250'])}**（{fm(r['lo'])}〜{fm(r['hi'])}） | "
                     f"{fm(r['auc500'])} | {fm(r.get('half1'))} / {fm(r.get('half2'))} | {fm(r.get('auc_bull'))} | {r['n']} / {fm(r['base'], '{:.0f}%')} |")
    L += ["", "独立市场（只看价格压力，250 天）：" + "；".join(f"{k} AUC {fm(v['auc250'])}（{v['n']} 个月末）" for k, v in eu.items()), "",
          "## 五分位（一年内跌 ≥ 10% 的比例 / 之后一年涨跌）", ""]
    for mkt in ("US", "JP"):
        for sc in ("P_price", "P_all"):
            q = res[mkt][sc]["q"]
            L.append(f"- {mkt} {nm[sc]}：" + "；".join(f"第 {x['q']} 档（{x['lo']:.0f}〜{x['hi']:.0f}）{x['event']:.0f}% / {x['ret']:+.1f}%" for x in q))
    L += ["", "## 现在（最新一天；分位 = 在过去 10 年月末里的位置）", ""]
    for mkt in ("US", "JP"):
        n = now[mkt]
        L.append(f"- {mkt}（{meta[mkt]['last_day']}）：价格压力 {fm(n['P_price'], '{:.0f}')}、综合压力 {fm(n['P_all'], '{:.0f}')}"
                 + (f"（近 3 个月 {n['chg3m']:+.0f}）" if n.get("chg3m") is not None else "") + "；"
                 + "、".join(f"{LABEL[k]} {fm(v, '{:.0f}')}" for k, v in n["pct"].items()))
        for sc in ("P_price", "P_all"):
            q = n.get(f"{sc}_q")
            if q:
                L.append(f"  - {nm[sc]}在第 {q['q']} 档：历史上同一档之后一年跌 ≥ 10% 的比例 {q['event']:.0f}%（全部 {q['base']:.0f}%），之后一年平均 {q['ret']:+.1f}%")
    L += ["", "美国宽度 = Ken French 49 行业（数据到上个月底）；日本宽度 = 现在的日経225 成分（有幸存者偏差）；估值没有长期数据，没有放进来。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "pressure_study"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"verdict": ver, "results": res, "now": now, "meta": meta, "europe": eu}, ensure_ascii=False,
                                             indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
