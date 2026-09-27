"""jq_extra_data.py — J-Quants Standard 里还没用过的数据的加载与「可用日」对齐（数据层；不含任何研究规则、阈值）。

数据（全部只在 var/cache/jquants/bulk/，不入库）：
  信用残高 markets/margin-interest：每周申込日 Date（周五）、Code、LongVol 买残、ShrtVol 卖残（株）、IssType；JPX 在次周第 2 营业日（通常周二）16:30 公布
    → 公布日 pub = Date + 4 天以后第一个交易日、可用日 avail = pub 之后第一个交易日（公布在收盘后，公布日本身不用）。
  空売り残高報告 markets/short-sale-report：每个 ≥ 0.5% 的空卖方一行（DiscDate 开示日、CalcDate 计算日、Code、SSName、ShrtPosToSO 比例）；
    同一空卖方之后再报 → 覆盖，报到 < 0.5% → 从合计里去掉 → 每只票每个开示日的「已报空头合计比例」与空卖方数；可用日 = DiscDate 之后第一个交易日。
  投資部門別売買状況 markets/investor-types.csv：每周（PubDate 通常周四）、Section（TokyoNagoya = 东京 + 名古屋合计、TSEPrime / TSEStandard / TSEGrowth…）、
    各主体 Sell / Buy / Tot / Bal（円）→ 比例 = 该主体差引 Bal ÷ 全体买卖合计 TotTot；可用日 = PubDate 之后第一个交易日。
  決算短信 fins/summary 的扩展字段：EqAR 自有资本比率、CFO / CFI / CFF 现金流（FY 全年、2Q 半年；1Q / 3Q 多为空）、TrShFY 期末自社株、ShOutFY 期末发行股数、
    BPS、DivAnn / FDivAnn 年度股息实绩 / 予想、ROE、Eq、TA、EPS、Sales、FSales；派生：tr_ratio 自社株比例、tr_chg 与上一次开示相比的自社株比例变化（pp，回购）、
    fcf = CFO + CFI、cfo_ta = CFO ÷ TA；可用日 = 开示日之后第一个交易日（与 fins_event_data 的 t0 一致，偏保守）。
  上市一览 master/：每月末快照 Mkt 市场区分（0101 一部 / 0102 二部 / 0104 マザーズ / 0106 JASDAQ-S / 0107 JASDAQ-G / 0111 プライム / 0112 スタンダード / 0113 グロース）、
    ScaleCat 规模档 → segment_mask（严格早于那天的最近一份快照，与 allstock_data.listed_mask 同一口径）。
通用：asof_matrix(long, days, names, col) 把「可用日 × 票」的长表变成 交易日 × 票 的矩阵（可用日起向前填充；之前 = NaN）。
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import jq_data as JD                                             # noqa: E402
from qbreak import jquants as JQ                                             # noqa: E402

MARGIN_PUB_LAG_DAYS = 4                                   # 周五申込 → 次周周二公布
SHORT_MIN = 0.005                                         # 报告门槛 0.5%
GROWTH_MKT = {"0104", "0107", "0113"}
PRIME_MKT = {"0101", "0111"}
STANDARD_MKT = {"0102", "0106", "0112"}
FINS_EXTRA = ["EqAR", "CFO", "CFI", "CFF", "TrShFY", "ShOutFY", "BPS", "DivAnn", "FDivAnn", "ROE", "Eq", "TA", "EPS", "Sales", "FSales"]


def bulk_files(sub: str) -> list[Path]:
    d = JD.bulk_dir() / sub
    return [Path(p) for p in sorted(glob.glob(str(d / "historical/*/*.csv.gz"))) + sorted(glob.glob(str(d / "historical/*.csv.gz")))
            + sorted(glob.glob(str(d / "live/*.csv.gz")))]


def next_days(dates, days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """日期 → 之后第一个交易日；数据末尾之后 → NaT。"""
    d = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    k = days.searchsorted(d.to_numpy(), side="right")
    out = days.to_numpy()[np.clip(k, 0, len(days) - 1)]
    return pd.DatetimeIndex(np.where(k < len(days), out, np.datetime64("NaT")))


def on_or_after(dates, days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """日期 → 当天或之后第一个交易日。"""
    d = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    k = days.searchsorted(d.to_numpy(), side="left")
    out = days.to_numpy()[np.clip(k, 0, len(days) - 1)]
    return pd.DatetimeIndex(np.where(k < len(days), out, np.datetime64("NaT")))


def _tickers(codes: pd.Series) -> pd.Series:
    return codes.astype(str).map(lambda c: JQ.to_yf(c))


# ───────────────────────── 信用残高 ─────────────────────────
def margin_weekly(days: pd.DatetimeIndex, M: pd.DataFrame | None = None) -> pd.DataFrame:
    """→ 长表：ticker, date（申込日）, pub, avail, long_vol, short_vol, ratio（买残 ÷ 卖残；卖残 0 → NaN）。"""
    if M is None:
        M = JD.read_bulk(bulk_files("markets/margin-interest"), ["Date", "Code", "LongVol", "ShrtVol"])
    out = pd.DataFrame({"ticker": _tickers(M["Code"]), "date": pd.to_datetime(M["Date"]),
                        "long_vol": pd.to_numeric(M["LongVol"], errors="coerce"), "short_vol": pd.to_numeric(M["ShrtVol"], errors="coerce")})
    out = out.dropna(subset=["ticker"]).copy()
    out["pub"] = on_or_after(out["date"] + pd.Timedelta(days=MARGIN_PUB_LAG_DAYS), days)
    out["avail"] = next_days(out["pub"], days)
    out["ratio"] = np.where(out["short_vol"] > 0, out["long_vol"] / out["short_vol"].replace(0, np.nan), np.nan)
    return out.dropna(subset=["avail"]).sort_values(["ticker", "date"]).reset_index(drop=True)


# ───────────────────────── 空売り残高 ─────────────────────────
def short_positions(days: pd.DatetimeIndex, S: pd.DataFrame | None = None) -> pd.DataFrame:
    """→ 长表（每只票每个有报告的开示日一行）：ticker, disc, avail, total（已报空头合计比例，0〜1）, holders（空卖方数）。
    算法：每个 (票, 空卖方) 的最新比例（< 0.5% 当 0 = 退出）；合计 = 按开示日累计 Δ（向量化，不逐行循环）。"""
    if S is None:
        S = JD.read_bulk(bulk_files("markets/short-sale-report"), ["DiscDate", "CalcDate", "Code", "SSName", "ShrtPosToSO"])
    S = S.assign(ticker=_tickers(S["Code"]), disc=pd.to_datetime(S["DiscDate"]), calc=pd.to_datetime(S["CalcDate"]),
                 r=pd.to_numeric(S["ShrtPosToSO"], errors="coerce"), name=S["SSName"].astype(str)).dropna(subset=["ticker", "r"])
    if not len(S):
        return pd.DataFrame(columns=["ticker", "disc", "avail", "total", "holders"])
    S = S.sort_values(["ticker", "disc", "calc"], kind="mergesort").reset_index(drop=True)
    S["cur"] = np.where(S["r"] >= SHORT_MIN, S["r"], 0.0)
    S["prev"] = S.groupby(["ticker", "name"], sort=False)["cur"].shift(1).fillna(0.0)
    S["d"] = S["cur"] - S["prev"]
    S["dh"] = (S["cur"] > 0).astype(int) - (S["prev"] > 0).astype(int)
    by = S.groupby(["ticker", "disc"], sort=True)[["d", "dh"]].sum().reset_index()
    by["total"] = by.groupby("ticker")["d"].cumsum().clip(lower=0.0)
    by["holders"] = by.groupby("ticker")["dh"].cumsum().clip(lower=0).astype(int)
    out = by[["ticker", "disc", "total", "holders"]].copy()
    out["avail"] = next_days(out["disc"], days)
    return out.dropna(subset=["avail"]).reset_index(drop=True)


# ───────────────────────── 投資部門別 ─────────────────────────
def investor_flows(days: pd.DatetimeIndex, section: str = "TokyoNagoya", I: pd.DataFrame | None = None) -> pd.DataFrame:
    """→ 每周一行（按 PubDate）：pub, avail, 各主体的比例 ratio_<主体> = Bal ÷ TotTot（正 = 净买）；主体名 = 列名去掉 Bal。"""
    if I is None:
        I = pd.read_csv(JD.bulk_dir() / "markets/investor-types.csv", dtype=str)
    x = I[I["Section"] == section].copy()
    bal_cols = [c for c in x.columns if c.endswith("Bal") and c != "TotBal"]
    x["pub"] = pd.to_datetime(x["PubDate"])
    tot = pd.to_numeric(x["TotTot"], errors="coerce")
    out = pd.DataFrame({"pub": x["pub"], "st": pd.to_datetime(x["StDate"]), "en": pd.to_datetime(x["EnDate"]), "tot": tot})
    for c in bal_cols:
        out["ratio_" + c[:-3]] = pd.to_numeric(x[c], errors="coerce") / tot.replace(0, np.nan)
    out["avail"] = next_days(out["pub"], days)
    return out.dropna(subset=["avail"]).sort_values("pub").drop_duplicates(subset=["pub"], keep="last").reset_index(drop=True)


# ───────────────────────── 決算短信扩展字段 ─────────────────────────
def fins_extended(days: pd.DatetimeIndex, F: pd.DataFrame | None = None) -> pd.DataFrame:
    """→ 长表（每条決算短信一行；不含予想修正文档）：ticker, date, time, per, doc, avail + FINS_EXTRA 数值 + tr_ratio / tr_chg / fcf / cfo_ta。"""
    if F is None:
        F = JD.read_bulk(bulk_files("fins/summary"), ["DiscDate", "DiscTime", "Code", "DocType", "CurPerType"] + FINS_EXTRA)
    fs = F[F["DocType"].fillna("").astype(str).str.contains("FinancialStatements") & ~F["DocType"].fillna("").astype(str).str.contains("REIT")].copy()
    out = pd.DataFrame({"ticker": _tickers(fs["Code"]), "date": pd.to_datetime(fs["DiscDate"]), "time": fs.get("DiscTime", "").fillna("").astype(str),
                        "per": fs["CurPerType"].fillna("").astype(str), "doc": fs["DocType"].astype(str)})
    for c in FINS_EXTRA:
        out[c] = pd.to_numeric(fs[c], errors="coerce") if c in fs.columns else np.nan
    out = out.dropna(subset=["ticker"]).sort_values(["ticker", "date", "time"], kind="mergesort").reset_index(drop=True)
    out["tr_ratio"] = np.where(out["ShOutFY"] > 0, out["TrShFY"] / out["ShOutFY"].replace(0, np.nan), np.nan)
    out["tr_chg"] = out.groupby("ticker")["tr_ratio"].diff() * 100
    out["fcf"] = out["CFO"] + out["CFI"]
    out["cfo_ta"] = np.where(out["TA"] > 0, out["CFO"] / out["TA"].replace(0, np.nan), np.nan)
    out["avail"] = next_days(out["date"], days)
    return out.dropna(subset=["avail"]).reset_index(drop=True)


# ───────────────────────── 上市一览 ─────────────────────────
def master_snapshots() -> dict[pd.Timestamp, pd.DataFrame]:
    from qbreak import pit_data as PD
    files = PD.master_files()
    return {pd.Timestamp(d): pd.read_csv(fp, dtype=str) for d, fp in sorted(files.items())}


def segment_mask(days: pd.DatetimeIndex, names: list[str], snaps: dict[pd.Timestamp, pd.DataFrame], group: set[str]) -> np.ndarray:
    """mask[d, j]：严格早于 d 的最近一份快照里那只票的市场区分 ∈ group。"""
    col = {t: j for j, t in enumerate(names)}
    out = np.zeros((len(days), len(names)), bool)
    sd = sorted(snaps)
    for k, s in enumerate(sd):
        nxt = sd[k + 1] if k + 1 < len(sd) else days[-1] + pd.Timedelta(days=1)
        rows = np.where((days > s) & (days <= nxt))[0]
        m = snaps[s]
        js = [col[y] for y in (JQ.to_yf(c) for c in m.loc[m["Mkt"].astype(str).isin(group), "Code"].astype(str)) if y in col]
        if len(rows) and js:
            out[np.ix_(rows, js)] = True
    return out


def scale_matrix(days: pd.DatetimeIndex, names: list[str], snaps: dict[pd.Timestamp, pd.DataFrame]) -> np.ndarray:
    """规模档：0 = 不在 TOPIX 规模档（-）、1 = Small 2、2 = Small 1、3 = Mid400、4 = Large70、5 = Core30（严格早于那天的快照）。"""
    order = {"TOPIX Small 2": 1, "TOPIX Small 1": 2, "TOPIX Mid400": 3, "TOPIX Large70": 4, "TOPIX Core30": 5}
    col = {t: j for j, t in enumerate(names)}
    out = np.zeros((len(days), len(names)), np.int8)
    sd = sorted(snaps)
    for k, s in enumerate(sd):
        nxt = sd[k + 1] if k + 1 < len(sd) else days[-1] + pd.Timedelta(days=1)
        rows = np.where((days > s) & (days <= nxt))[0]
        if not len(rows):
            continue
        m = snaps[s]
        if "ScaleCat" not in m.columns:
            continue
        for c, sc in zip(m["Code"].astype(str), m["ScaleCat"].astype(str)):
            j = col.get(JQ.to_yf(c))
            if j is not None:
                out[rows, j] = order.get(sc, 0)
    return out


# ───────────────────────── 对齐 ─────────────────────────
def asof_matrix(long: pd.DataFrame, days: pd.DatetimeIndex, names: list[str], col: str, avail_col: str = "avail",
                ticker_col: str = "ticker") -> np.ndarray:
    """长表（可用日 × 票 × 值）→ 交易日 × 票 的矩阵，可用日起向前填充；之前 NaN。同一票同一可用日多条 → 最后一条。"""
    x = long[[ticker_col, avail_col, col]].dropna(subset=[avail_col])
    x = x[x[ticker_col].isin(names)]
    if not len(x):
        return np.full((len(days), len(names)), np.nan)
    piv = x.sort_values([ticker_col, avail_col]).drop_duplicates(subset=[ticker_col, avail_col], keep="last") \
           .pivot(index=avail_col, columns=ticker_col, values=col)
    piv = piv.reindex(index=days.union(piv.index)).sort_index().ffill().reindex(days)
    return piv.reindex(columns=names).to_numpy(float)


def asof_series(weekly: pd.DataFrame, days: pd.DatetimeIndex, col: str, avail_col: str = "avail") -> pd.Series:
    """每周表 → 按交易日向前填充的序列（可用日起）。"""
    s = weekly.dropna(subset=[avail_col]).sort_values(avail_col).drop_duplicates(subset=[avail_col], keep="last").set_index(avail_col)[col]
    return s.reindex(days.union(s.index)).sort_index().ffill().reindex(days)
