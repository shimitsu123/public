"""tankan.py — 日银短観（大企業）的业种数据 → 東証业种 / 主题的「景气」信号（scripts/fund_study.py；2026-09-26 事先登记）。

数据（BOJ 時系列統計 API，db=CO；qbreak/factors.py tankan）：業況 / 国内需給 / 販売価格 / 仕入価格 判断 DI（実績、予測）。
代码 = TK99F{业种 4 位}6{项目 2 位}GCQ{0 実績 / 1 予測}1000（最后的 1 = 大企業）。
日期：実績挂在调查季度（例 2026-06-30 = 6 月调查），予測挂在下一季度（6 月调查对 9 月的预测挂 2026-09-30）。
公布（保守）：3 / 6 / 9 月调查 → 下个月 5 日之后可用（实际是 1 日前后 8:50）；12 月调查 → 12 月 20 日之后（实际 12 月 10〜17 日）。
设备投资计划的修正率（年度，db=CO，TK99G{业种}1092FY{k}1000）：k = 4 6 月调查（对 3 月计划）、3 9 月、2 12 月、1 实绩见込（翌年 3 月）。
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

# 短観业种代码（大企業）
IND = {"1010": "食料品", "1020": "繊維", "1050": "紙・パルプ", "1060": "化学", "1070": "石油・石炭製品", "1100": "窯業・土石製品",
       "1110": "鉄鋼", "1120": "非鉄金属", "1130": "金属製品", "1141": "はん用機械", "1142": "生産用機械", "1143": "業務用機械",
       "1149": "はん用・生産用・業務用機械", "1150": "電気機械", "1160": "輸送用機械", "1185": "造船・重機等", "1500": "その他製造業",
       "2011": "建設", "2012": "不動産", "2090": "物品賃貸", "2021": "卸売", "2024": "小売", "2040": "運輸・郵便", "2059": "情報通信",
       "2051": "情報サービス", "2060": "電気・ガス", "2081": "対事業所サービス", "2082": "対個人サービス", "2500": "鉱業等"}
ITEMS = {"biz": "01", "dom": "02", "sell": "14", "buy": "15"}          # 業況、国内需給、販売価格、仕入価格
# 東証业种 / 主题 ← 短観业种（几个短観业种就取平均；機械・精密機器・T5・T9 的短観分类 2010 年才有）
TSE = {"鉱業": ["2500"], "建設業": ["2011"], "食料品": ["1010"], "繊維製品": ["1020"], "パルプ・紙": ["1050"], "化学": ["1060"],
       "医薬品": ["1060"], "石油・石炭製品": ["1070"], "ゴム製品": ["1500"], "ガラス・土石製品": ["1100"], "鉄鋼": ["1110"],
       "非鉄金属": ["1120"], "金属製品": ["1130"], "機械": ["1149"], "電気機器": ["1150"], "輸送用機器": ["1160"], "精密機器": ["1143"],
       "その他製品": ["1500"], "電気・ガス業": ["2060"], "海運業": ["2040"], "情報・通信業": ["2059"], "卸売業": ["2021"],
       "小売業": ["2024"], "その他金融業": ["2090"], "不動産業": ["2012"], "サービス業": ["2081", "2082"],
       "T1": ["2060"], "T2": ["2060"], "T3": ["1120"], "T4": ["1150"], "T5": ["1141"], "T6": ["2011"], "T7": ["2051"], "T8": ["2051"],
       "T9": ["1142"], "T10": ["1060"], "T11": ["1150"], "T13": ["1185"]}
CAPEX_IND = {"0000": "全産業", "1000": "製造業", "1150": "電気機械", "2059": "情報通信"}
CAPEX_SURVEY = {4: (7, 5), 3: (10, 5), 2: (12, 20), 1: (4, 5)}      # k → 可用日（月, 日）；k = 1 是翌年 4 月


def code(ind: str, item: str, forecast: bool = False) -> str:
    return f"TK99F{ind}6{ITEMS[item]}GCQ{1 if forecast else 0}1000"


def capex_code(ind: str, k: int) -> str:
    return f"TK99G{ind}1092FY{k}1000"


def available(q_end: pd.Timestamp) -> pd.Timestamp:
    """调查季度末 → 保守的可用日（这一天收盘后才用；交易从下一个交易日开始）。"""
    q_end = pd.Timestamp(q_end)
    if q_end.month == 12:
        return pd.Timestamp(q_end.year, 12, 20)
    nxt = q_end + pd.offsets.MonthBegin(1)
    return pd.Timestamp(nxt.year, nxt.month, 5)


MISSING: list[str] = []                                              # 取不到的系列（例 物品賃貸 没有仕入価格 DI）


def _get_series(fetch, c: str) -> pd.Series:
    try:
        return fetch(c)
    except Exception:                                                  # noqa: BLE001  短観里没有这个组合 → 缺值（研究输出会列出）
        MISSING.append(c)
        return pd.Series(dtype=float)


def load(fetch=None) -> dict[str, pd.DataFrame]:
    """{项目[_f]: 季度末 × 短観业种}（biz / biz_f / dom / sell / buy）。fetch = factors.tankan（测试时可换）。"""
    if fetch is None:
        from .factors import tankan as fetch
    out = {}
    for item in ITEMS:
        out[item] = pd.DataFrame({i: _get_series(fetch, code(i, item)) for i in IND})
    out["biz_f"] = pd.DataFrame({i: _get_series(fetch, code(i, "biz", True)) for i in IND})
    return out


def signals(T: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """调查季度 × 短観业种 的信号（该次调查公布时已知）：
    S1 业况变化 = 実績 − 上次実績；S2 预期 = 予測（下季）− 実績；S3 利润差变化 = Δ(販売 − 仕入)；S4 国内需给变化。"""
    biz = T["biz"].sort_index()
    q = biz.index
    fut = T["biz_f"].sort_index().shift(-1).reindex(q)                     # 下季的予測挂回本次调查
    spread = (T["sell"] - T["buy"]).reindex(q)
    return {"S1": biz.diff(), "S2": fut - biz, "S3": spread.diff(), "S4": T["dom"].reindex(q).diff()}


def to_groups(sig: pd.DataFrame, groups: list[str] | None = None) -> pd.DataFrame:
    """短観业种的信号 → 東証业种 / 主题（对照 TSE，几个短観业种取平均）。"""
    out = {}
    for g in groups or list(TSE):
        cols = [c for c in TSE.get(g, []) if c in sig.columns]
        if cols:
            out[g] = sig[cols].mean(axis=1, skipna=False)
    return pd.DataFrame(out, index=sig.index)


def customer_weighted(sig_g: pd.DataFrame, cus: dict[str, dict[str, float]]) -> pd.DataFrame:
    """顾客业种的信号（产业连关表的销售份额加权；有信号的顾客重新归一）= 「下游景气」。"""
    out = {}
    for j, w in cus.items():
        ks = [k for k in w if k in sig_g.columns]
        if not ks:
            continue
        W = pd.DataFrame({k: w[k] * sig_g[k].notna() for k in ks})
        num = sum(w[k] * sig_g[k].fillna(0.0) for k in ks)
        den = W.sum(axis=1)
        out[j] = (num / den).where(den > 0)
    return pd.DataFrame(out, index=sig_g.index)


def load_capex(fetch_annual=None) -> pd.DataFrame:
    """设备投资计划修正率（%）→ 可用日 × 行业（全産業 / 製造業 / 電気機械 / 情報通信）。"""
    if fetch_annual is None:
        fetch_annual = boj_annual
    rows = {}
    for ind, name in CAPEX_IND.items():
        vals = {}
        for k, (m, d) in CAPEX_SURVEY.items():
            s = _get_series(fetch_annual, capex_code(ind, k))
            for fy, v in s.items():
                y = int(fy) + (1 if k == 1 else 0)
                vals[pd.Timestamp(y, m, d)] = float(v)
        rows[name] = pd.Series(vals).sort_index()
    return pd.DataFrame(rows).sort_index()


def boj_annual(series_code: str) -> pd.Series:
    """BOJ API 的年度系列（例 设备投资计划修正率）：索引 = 年度（整数）。"""
    from .factors import BOJ_API, _cached, _get

    def fetch():
        url = f"{BOJ_API}?format=json&lang=jp&db=CO&code={series_code}&startDate=1990&endDate={dt.date.today().year + 1}"
        out = {}
        for r in json.loads(_get(url)).get("RESULTSET") or []:
            v = r.get("VALUES") or {}
            for y, val in zip(v.get("SURVEY_DATES") or [], v.get("VALUES") or []):
                if val is not None:
                    out[int(str(y)[:4])] = float(val)
        return pd.Series(out, name=series_code).sort_index()
    s = _cached(f"boj_COA_{series_code}", fetch)
    s.index = [int(pd.Timestamp(i).year) if not isinstance(i, (int, np.integer)) else int(i) for i in s.index]
    return s


def seasonal_adjust(C: pd.DataFrame, min_years: int = 5) -> pd.DataFrame:
    """设备投资修正率有强季节性（6 月调查通常大幅上修）→ 减去「同一调查月、之前各年」的平均（只用当时已有的年份，≥ min_years 年）。"""
    out = C.copy() * np.nan
    for col in C.columns:
        s = C[col].dropna()
        for m in sorted(set(s.index.month)):
            sm = s[s.index.month == m]
            prior = sm.shift(1).expanding(min_periods=min_years).mean()
            out.loc[sm.index, col] = sm - prior
    return out


def release_targets(D: pd.DataFrame, dates, n_days: int) -> pd.DataFrame:
    """公布日 × 组：公布日之后第一个交易日起 n_days 个交易日的相对收益之和（%；不够 n_days 天 → 缺值）。
    D = 日期 × 组 的日相对收益。公布日当天收盘后才用，所以从下一个交易日算起。"""
    idx = D.index
    V = D.to_numpy(float)
    csum = np.vstack([np.zeros((1, V.shape[1])), np.nancumsum(V, axis=0)])
    cnt = np.vstack([np.zeros((1, V.shape[1])), np.cumsum(np.isfinite(V), axis=0)])
    rows = []
    for d in dates:
        a = int(idx.searchsorted(pd.Timestamp(d), side="right"))          # 公布日之后的第一个交易日
        b = a + n_days
        if b > len(idx):
            rows.append(np.full(V.shape[1], np.nan))
            continue
        tot, n = csum[b] - csum[a], cnt[b] - cnt[a]
        rows.append(np.where(n >= 0.9 * n_days, tot, np.nan))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates), columns=D.columns)
