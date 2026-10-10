"""pit_data.py — J-Quants 批量日线 → 拆股调整后的 OHLCV 与「当时真实的一手」比例；每月末上市一览 → 时点股票池
（研究用：scripts/pit_retrain_study.py；原始数据只在 var/cache/jquants/（已 gitignore），J-Quants 规约禁止再分发 → 绝不入库）。

日线（/equities/bars/daily 的批量 CSV）：未调整的 O / H / L / C / Vo + 调整系数 AdjFactor（拆股 / 合并的权利落ち日那天 = 分割比率的倒数，
  例 1 拆 5 → 0.2；其余日子 1）。调整后价 = 未调整价 × 之后各日 AdjFactor 的连乘（权利落ち日当天已经是拆股后的价格）；成交量反过来除。
  不含分红调整。真实一手比例 = 未调整收盘 ÷ 调整后收盘（scripts/jq_study.py 的 RealLotEngine 同一口径）。
时点股票池（每个月末的上市一览 /equities/master?date=）：
  t500 = ScaleCat 为 TOPIX Core30 / Large70 / Mid400；t1000 = t500 + TOPIX Small 1。
  J-Quants 的上市一览 2018-09 以前没有 Small 1 标签（小型股全部标成 Small 2）→ 那些月末用「TOPIX Small 里当天市值最大的 500 只」代替。
  都剔除 空運業 / 陸運業 / 倉庫・運輸関連業（与现行股票池同一偏好）。
  某天是不是成员 = 严格早于那天的最近一个月末快照（月末当天用上一个月末的快照；第一个快照之前全都不是）。
"""
from __future__ import annotations

import gzip
import io
from pathlib import Path

import numpy as np
import pandas as pd

from .jquants import cache_dir

BAR_COLS = ["Date", "Code", "O", "H", "L", "C", "Vo", "AdjFactor", "MktCap"]
T500 = ("TOPIX Core30", "TOPIX Large70", "TOPIX Mid400")
SMALL1 = "TOPIX Small 1"
SMALL = ("TOPIX Small 1", "TOPIX Small 2")
EXCLUDE_S33 = ("空運", "陸運", "倉庫")
N_SMALL1 = 500


# ────────────────────────── 日线 ──────────────────────────
def bar_files() -> list[Path]:
    """批量日线文件：月度（historical）+ 最近的日度（live）。"""
    d = cache_dir() / "bulk" / "equities" / "bars" / "daily"
    return sorted((d / "historical").glob("*/*.csv.gz")) + sorted((d / "live").glob("*.csv.gz"))


def read_bars(files: list[Path], codes: set[str] | None = None, cols: list[str] = BAR_COLS) -> pd.DataFrame:
    """把批量 CSV.gz 读成一张表（只留 cols；codes = 5 位代码集合时只留这些）；同一天同一只票重复 → 留后面的文件。"""
    parts = []
    for fp in files:
        with gzip.open(fp, "rb") as fh:
            df = pd.read_csv(io.BytesIO(fh.read()), dtype=str, usecols=lambda c: c in cols)
        if codes is not None:
            df = df[df["Code"].isin(codes)]
        parts.append(df)
    if not parts:
        return pd.DataFrame(columns=cols)
    return pd.concat(parts, ignore_index=True).drop_duplicates(subset=["Date", "Code"], keep="last")


def adjust(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """一只票的原始日线 → (调整后 OHLCV, 真实一手比例)。价格缺值 / 非正、High < Low 的日子丢掉；High / Low 包住开收盘。"""
    d = raw.assign(Date=pd.to_datetime(raw["Date"])).sort_values("Date").drop_duplicates("Date", keep="last").set_index("Date")
    v = {k: pd.to_numeric(d[k], errors="coerce") for k in ("O", "H", "L", "C", "Vo", "AdjFactor")}
    f = v["AdjFactor"].where(v["AdjFactor"] > 0).fillna(1.0)
    after = f.iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1.0)     # 之后各日（不含当天）的连乘
    out = pd.DataFrame({"Open": v["O"] * after, "High": v["H"] * after, "Low": v["L"] * after, "Close": v["C"] * after,
                        "Volume": (v["Vo"] / after).fillna(0.0)}, index=d.index)
    px = out[["Open", "High", "Low", "Close"]]
    ok = px.notna().all(axis=1) & (px > 0).all(axis=1) & (out["High"] >= out["Low"])
    out = out[ok].copy()
    out["High"] = out[["High", "Open", "Close"]].max(axis=1)
    out["Low"] = out[["Low", "Open", "Close"]].min(axis=1)
    return out, (1.0 / after)[ok]


def market_caps(bars: pd.DataFrame, dates) -> dict[pd.Timestamp, pd.Series]:
    """{日期: 代码 → 当天市值}（只取给定的日期；缺值不算）。"""
    want = {str(pd.Timestamp(d).date()) for d in dates}
    b = bars[bars["Date"].isin(want)]
    out = {}
    for d, g in b.groupby("Date"):
        s = pd.to_numeric(g.set_index("Code")["MktCap"], errors="coerce").dropna()
        out[pd.Timestamp(d)] = s[~s.index.duplicated(keep="last")]
    return out


# ────────────────────────── 时点股票池 ──────────────────────────
def master_files() -> dict[pd.Timestamp, Path]:
    """缓存里的月末上市一览：{日期: 文件}。"""
    return {pd.Timestamp(fp.stem): fp for fp in sorted((cache_dir() / "master").glob("*.csv"))}


def members(m: pd.DataFrame, kind: str, mcap: pd.Series | None = None) -> set[str]:
    """一个月末快照 → 成员（5 位代码）。kind = "t500" / "t1000"。"""
    sc, s33 = m["ScaleCat"].astype(str), m["S33Nm"].astype(str)
    keep = ~s33.apply(lambda x: any(k in x for k in EXCLUDE_S33))
    code = m["Code"].astype(str)
    t500 = set(code[sc.isin(T500) & keep])
    if kind == "t500":
        return t500
    if kind != "t1000":
        raise ValueError(kind)
    if (sc == SMALL1).any():
        s1 = set(code[(sc == SMALL1) & keep])
    else:                                                                   # 2018-09 以前：Small 里市值最大的 500 只代替 Small 1
        small = pd.Index(code[sc.isin(SMALL)])
        cap = (mcap if mcap is not None else pd.Series(dtype=float)).reindex(small).dropna().sort_values(ascending=False, kind="mergesort")
        s1 = set(cap.index[:N_SMALL1]) & set(code[keep])                    # 先按全部小型股排（与官方 Small 1 同口径），再剔除业种
    return t500 | s1


def member_matrix(snaps: dict[pd.Timestamp, set[str]], days: pd.DatetimeIndex) -> pd.DataFrame:
    """交易日 × 代码：严格早于那天的最近一个月末快照里是成员 → True；第一个快照之前全是 False。"""
    dates = sorted(snaps)
    codes = sorted(set().union(*snaps.values())) if snaps else []
    S = np.zeros((len(dates), len(codes)), bool)
    col = {c: j for j, c in enumerate(codes)}
    for i, d in enumerate(dates):
        for c in snaps[d]:
            S[i, col[c]] = True
    pos = np.searchsorted(pd.DatetimeIndex(dates).values, pd.DatetimeIndex(days).values, side="left") - 1
    M = np.zeros((len(days), len(codes)), bool)
    ok = pos >= 0
    M[ok] = S[pos[ok]]
    return pd.DataFrame(M, index=pd.DatetimeIndex(days), columns=codes)


def label_asof(snaps: dict[pd.Timestamp, pd.Series], code: str, day) -> str | None:
    """严格早于 day 的最近一个快照里这只票的标签（例 TOPIX-17 业种）；没有 → None。"""
    ds = sorted(d for d in snaps if d < pd.Timestamp(day))
    for d in reversed(ds):
        v = snaps[d].get(code)
        if v is not None and v == v:
            return str(v)
    return None


def mask_entries(ind: pd.DataFrame, member: pd.Series | None) -> pd.DataFrame:
    """entry 只在成员的日子成立（member = 日期 → bool；None = 从来不是成员 → 全部不开仓）。只换 entry 这一列。"""
    m = np.zeros(len(ind), bool) if member is None else member.reindex(ind.index).fillna(False).to_numpy(dtype=bool)
    out = ind.copy(deep=False)
    out["entry"] = ind["entry"].to_numpy(dtype=bool) & m
    return out
