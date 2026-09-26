"""jq_data.py — J-Quants 付费档（Standard：2016-09-26 起 10 年）的批量数据与「当时已知」的个股特征（研究用：scripts/jq_study.py）。

批量下载：/bulk/list?endpoint=… 列出月度（historical）与日度（live）CSV.gz → /bulk/get?key=… 给一个临时下载地址。
原始文件只放 var/cache/jquants/bulk/（var/cache 已 gitignore）：J-Quants 规约只许个人使用、禁止再分发 → 绝不入库。
数据集（字段名是 J-Quants V2 的缩写）：
  fins/summary（決算短信サマリー）：DiscDate / DiscTime 开示日时、DocType、CurPerType（1Q/2Q/3Q/FY）、CurFYEn 当期决算期末、
      OP 营业利润 / OdP 经常利润 / NP 净利润（累计实绩）、FOP / FOdP / FNP 当期会社予想、NxFOP / NxFOdP / NxFNp 下期会社予想（FY 决算时）
  markets/margin-interest（信用取引週末残高，周五时点）：LongVol 买残（股）、ShrtVol 卖残（股）；第 2 个营业日 16:30 左右公布
  markets/short-sale-report（空売り残高報告，≥ 0.5%）：DiscDate、SSName 报告者、ShrtPosToSO 占发行股数比例
  equities/bars/daily（日线）：C 未调整收盘（当时的真实价格）、Vo 未调整成交量、AdjC 调整后收盘
「当时已知」的约定（都偏保守）：开示日 D 的信息只用于 D 之后的信号日（D < 信号日）；信用余额用公布日（周五之后第 3 个营业日）起；
离最近一次数据太久（缺数据）→ 缺值，不向前乱填。
"""
from __future__ import annotations

import gzip
import io
from pathlib import Path

import numpy as np
import pandas as pd

from .jquants import JQuants, cache_dir

DATASETS = {
    "fins": ("/fins/summary", ["DiscDate", "DiscTime", "Code", "DocType", "CurPerType", "CurFYSt", "CurFYEn", "NxtFYEn",
                               "OP", "OdP", "NP", "FOP", "FOdP", "FNP", "NxFOP", "NxFOdP", "NxFNp"]),
    "margin": ("/markets/margin-interest", ["Date", "Code", "LongVol", "ShrtVol"]),
    "short": ("/markets/short-sale-report", ["DiscDate", "CalcDate", "Code", "SSName", "ShrtPosToSO"]),
    "daily": ("/equities/bars/daily", ["Date", "Code", "C", "Vo", "AdjC"]),
}


def bulk_dir() -> Path:
    d = cache_dir() / "bulk"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bulk_download(client: JQuants, endpoint: str, http_get=None, log=print) -> list[Path]:
    """某个数据集的全部 CSV.gz（已下载且大小一致的跳过）。返回本地文件列表（按 key 排序）。"""
    if http_get is None:
        from curl_cffi import requests as cr
        http_get = lambda url: cr.get(url, timeout=180).content                    # noqa: E731
    keys = client.get("/bulk/list", endpoint=endpoint)
    meta_fp = bulk_dir() / "_last_modified.json"
    try:
        import json as _json
        meta = _json.loads(meta_fp.read_text(encoding="utf-8")) if meta_fp.exists() else {}
    except ValueError:
        meta = {}
    out = []
    for k in sorted(keys, key=lambda r: r["Key"]):
        fp = bulk_dir() / k["Key"]
        size = int(float(k.get("Size") or 0))
        lm = str(k.get("LastModified") or "")
        same = not lm or meta.get(k["Key"]) in (None, lm)                    # 订正会覆盖同一个 Key：LastModified 变了就重下
        if fp.exists() and same and (not size or fp.stat().st_size == size):
            out.append(fp)
            if lm and k["Key"] not in meta:
                meta[k["Key"]] = lm
            continue
        for tries in range(6):                                           # 429（限速）→ 等一分钟再试
            st, body = client._once("/bulk/get", {"key": k["Key"]})
            if st != 429:
                break
            client._sleep(60)
        if st != 200 or "url" not in body:
            raise RuntimeError(f"/bulk/get {k['Key']} HTTP {st}")
        blob = http_get(body["url"])
        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(fp.suffix + ".part")
        tmp.write_bytes(blob)
        tmp.replace(fp)
        out.append(fp)
        if lm:
            meta[k["Key"]] = lm
        log(f"  {k['Key']} {len(blob) / 1e6:.1f} MB")
    if meta:
        import json as _json
        meta_fp.write_text(_json.dumps(meta, ensure_ascii=False, indent=0), encoding="utf-8")
    return out


def read_bulk(files: list[Path], cols: list[str], codes: set[str] | None = None) -> pd.DataFrame:
    """把 CSV.gz 读成一张表（只留 cols；codes = 5 位代码集合时只留这些）。"""
    parts = []
    for fp in files:
        with gzip.open(fp, "rb") as fh:
            raw = fh.read()
        df = pd.read_csv(io.BytesIO(raw), dtype=str, usecols=lambda c: c in cols)
        if codes is not None and "Code" in df.columns:
            df = df[df["Code"].isin(codes)]
        parts.append(df)
    if not parts:
        return pd.DataFrame(columns=cols)
    return pd.concat(parts, ignore_index=True).drop_duplicates()


def code5(ticker: str) -> str:
    """'7203.T' → '72030'；'285A.T' → '285A0'。"""
    return ticker.split(".")[0] + "0"


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


# ── 价格：当时真实的一手价格 ──
def real_ratio(daily: pd.DataFrame, adj_close: pd.Series) -> pd.Series:
    """日期 → 当时真实收盘（J-Quants 未调整 C）÷ 回测用的调整后收盘（yfinance，含分红调整）。
    回测里的「一手」= 100 × 这个比例（调整后的股数）；没有 J-Quants 数据的日子 → 缺值（调用方按 1 处理）。"""
    d = daily.assign(Date=pd.to_datetime(daily["Date"]), C=num(daily["C"])).dropna(subset=["C"])
    c = d.set_index("Date")["C"].sort_index()
    c = c[~c.index.duplicated(keep="last")]
    a = adj_close.reindex(c.index)
    return (c / a).where((c > 0) & (a > 0))


# ── 決算短信：会社予想修正、增益率 ──
def profit_level(F: pd.DataFrame) -> tuple[str, str, str]:
    """这家公司用哪一档利润：有营业利润（OP / FOP）就用它；没有（银行 / 保险）→ 经常利润（OdP）→ 净利润（NP）。
    返回 (累计实绩列, 当期予想列, 下期予想列)。"""
    for a, f, nx in (("OP", "FOP", "NxFOP"), ("OdP", "FOdP", "NxFOdP"), ("NP", "FNP", "NxFNp")):
        if any(c in F.columns and num(F[c]).notna().any() for c in (a, f)):
            return a, f, nx
    return "OP", "FOP", "NxFOP"


def fins_events(F: pd.DataFrame) -> pd.DataFrame:
    """一家公司的決算短信 → 每条开示一行：date（开示日）、fy（这个予想对应的决算期末）、fc（予想值）、
    rev（与同一决算期上一次予想相比的修正率；第一次出现的予想 → 缺值）、yoy（累计实绩对上年同期的增益率）。"""
    if F.empty:
        return pd.DataFrame(columns=["date", "fy", "fc", "rev", "yoy"])
    F = F.copy()
    for c in ("OP", "OdP", "NP", "FOP", "FOdP", "FNP", "NxFOP", "NxFOdP", "NxFNp"):
        F[c] = num(F[c]) if c in F.columns else np.nan
    F["date"] = pd.to_datetime(F["DiscDate"])
    F = F.sort_values(["date", "DiscTime"] if "DiscTime" in F.columns else ["date"], kind="mergesort").reset_index(drop=True)
    a0, f0, nx0 = profit_level(F)
    rows, last_fc = [], {}
    actual: dict[tuple[str, str], float] = {}                       # (期末, 期间类型) → 累计实绩
    for r in F.itertuples(index=False):
        rd = r._asdict()
        is_fy = str(rd.get("CurPerType") or "") == "FY" and str(rd.get("DocType") or "").startswith("FY")
        fy, fc = (rd.get("NxtFYEn"), rd.get(nx0)) if is_fy else (rd.get("CurFYEn"), rd.get(f0))
        rev = np.nan
        if pd.notna(fc) and fy in last_fc and pd.notna(last_fc[fy]) and last_fc[fy] != 0:
            rev = (fc - last_fc[fy]) / abs(last_fc[fy]) * 100
        if pd.notna(fc):
            last_fc[fy] = fc
        yoy = np.nan
        per, fye, act = rd.get("CurPerType"), rd.get("CurFYEn"), rd.get(a0)
        if pd.notna(act) and fye and per and str(rd.get("DocType") or "").find("Financial") >= 0:
            prev_fye = str(int(str(fye)[:4]) - 1) + str(fye)[4:]
            ly = actual.get((prev_fye, per))
            if ly is not None and ly != 0:
                yoy = (act - ly) / abs(ly) * 100
            actual[(str(fye), per)] = act
        rows.append((rd["date"], fy, fc, rev, yoy))
    return pd.DataFrame(rows, columns=["date", "fy", "fc", "rev", "yoy"])


def fins_features(ev: pd.DataFrame, dates, window_days: int = 90, stale_days: int = 200) -> pd.DataFrame:
    """信号日 → g1（最近 window_days 天里最近一次「会社予想修正」的修正率 %；这段时间没有改过予想 → 0）、
    g2（最近一次有增益率的开示的累计利润增益率 %）。开示日必须早于信号日；最近一次开示离信号日 > stale_days 天 → 两个都缺值。"""
    D = pd.DatetimeIndex(dates)
    if ev.empty:
        return pd.DataFrame({"g1": np.nan, "g2": np.nan}, index=D)
    ev = ev.sort_values("date", kind="mergesort")
    t = ev["date"].to_numpy("datetime64[ns]")
    rev, yoy = ev["rev"].to_numpy(float), ev["yoy"].to_numpy(float)
    out = []
    for s in D.to_numpy("datetime64[ns]"):
        k = int(np.searchsorted(t, s, side="left")) - 1               # 最后一条 D < s
        if k < 0 or (s - t[k]) > np.timedelta64(stale_days, "D"):
            out.append((np.nan, np.nan))
            continue
        lo = int(np.searchsorted(t, s - np.timedelta64(window_days, "D"), side="left"))
        r = rev[lo:k + 1]
        r = r[np.isfinite(r) & (r != 0)]                               # 最近一次真的改了予想的开示（只是重申 = 0 不算）
        g1 = float(r[-1]) if len(r) else 0.0
        y = yoy[:k + 1]
        yi = np.flatnonzero(np.isfinite(y))
        g2 = float(y[yi[-1]]) if len(yi) and (s - t[yi[-1]]) <= np.timedelta64(stale_days, "D") else np.nan
        out.append((g1, g2))
    return pd.DataFrame(out, index=D, columns=["g1", "g2"])


# ── 信用余额：买残 / 卖残 ÷ 20 日平均成交量（未调整股数，与余额同一口径）──
def margin_features(M: pd.DataFrame, daily: pd.DataFrame, dates, lag_bdays: int = 3, stale_bdays: int = 15) -> pd.DataFrame:
    """信号日 → m1（买残 ÷ 20 日均量，天数）、m2（卖残 ÷ 20 日均量）。余额（周五时点）从之后第 lag_bdays 个交易日起才用；
    最近一次可用的余额离信号日 > stale_bdays 个交易日 → 缺值。均量 = 信号日为止 20 个交易日的未调整成交量平均。"""
    D = pd.DatetimeIndex(dates)
    d = daily.assign(Date=pd.to_datetime(daily["Date"]), Vo=num(daily["Vo"])).dropna(subset=["Vo"]).sort_values("Date")
    d = d[~d["Date"].duplicated(keep="last")]
    if d.empty or M.empty:
        return pd.DataFrame({"m1": np.nan, "m2": np.nan}, index=D)
    days = pd.DatetimeIndex(d["Date"])
    adv = pd.Series(d["Vo"].to_numpy(float), index=days).rolling(20, min_periods=15).mean()
    m = M.assign(Date=pd.to_datetime(M["Date"]), L=num(M["LongVol"]), S=num(M["ShrtVol"])).sort_values("Date")
    avail_pos = days.searchsorted(pd.DatetimeIndex(m["Date"]), side="right") - 1 + lag_bdays   # 周五（或之前最后一个交易日）+ lag
    L, S = m["L"].to_numpy(float), m["S"].to_numpy(float)
    out = []
    for s in D:
        si = int(days.searchsorted(s, side="left"))
        if si >= len(days) or days[si] != s:
            out.append((np.nan, np.nan))
            continue
        ok = np.flatnonzero(avail_pos <= si)
        if not len(ok) or si - avail_pos[ok[-1]] > stale_bdays:
            out.append((np.nan, np.nan))
            continue
        a = float(adv.iloc[si])
        j = ok[-1]
        out.append((L[j] / a if a > 0 else np.nan, S[j] / a if a > 0 else np.nan))
    return pd.DataFrame(out, index=D, columns=["m1", "m2"])


# ── 空売り残高報告：≥ 0.5% 的大额空头合计 ──
def short_features(R: pd.DataFrame, dates, keep_days: int = 365) -> pd.DataFrame:
    """信号日 → s1 = 各报告者最近一次报告的比例之和（%；只算开示日早于信号日、离信号日 ≤ keep_days 天、比例 ≥ 0.5% 的）。
    这只票从来没有报告 → 0（没有大额空头）。"""
    D = pd.DatetimeIndex(dates)
    if R.empty:
        return pd.DataFrame({"s1": 0.0}, index=D)
    r = R.assign(date=pd.to_datetime(R["DiscDate"]), p=num(R["ShrtPosToSO"])).dropna(subset=["p"]).sort_values("date")
    out = []
    for s in D:
        w = r[(r["date"] < s) & (r["date"] >= s - pd.Timedelta(days=keep_days))]
        if w.empty:
            out.append(0.0)
            continue
        last = w.groupby("SSName")["p"].last()
        out.append(float(last[last >= 0.005].sum() * 100))
    return pd.DataFrame({"s1": out}, index=D)
