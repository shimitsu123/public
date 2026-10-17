"""allstock_data.py — J-Quants 全市场（东证内国普通股，约 4,000 只）2016-09〜2026-09 的日线面板（研究用：「用全部股票训练」）。

- 股票 = 月末上市一览里 ProdCat 011（内国株式）、市场不是 TOKYO PRO MARKET（只限专业投资者，个人买不了）/ その他 的代码；
- 价格 = 拆股调整后的 OHLCV（qbreak/pit_data.adjust，与 pit_retrain_study 同一口径）+ 真实一手比例 + 时价总额 + 売買代金；
- listed[d, j] = 严格早于 d 的最近一个月末快照里是内国普通股、且在东证的一般市场（プライム / スタンダード / グロース 或 旧一部 / 二部 / マザーズ / JASDAQ）。
原始数据与整理结果都只在 var/cache/jquants/（已 gitignore；整理结果 allstock_panels.npz），不入库。
"""
from __future__ import annotations

import gzip
import io
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import pit_data as PD                                            # noqa: E402
from qbreak.jquants import cache_dir, to_yf                                  # noqa: E402

CACHE = cache_dir() / "allstock_panels.npz"                                  # 与批量日线同一个缓存目录（QBREAK_HOME 设了就跟着它）
GENERAL_MKT = {"0101", "0102", "0104", "0106", "0107", "0111", "0112", "0113"}   # 一部 / 二部 / マザーズ / JASDAQ S・G / プライム / スタンダード / グロース
COLS = ["Date", "Code", "O", "H", "L", "C", "Vo", "Va", "AdjFactor", "MktCap"]


def snapshots() -> dict[pd.Timestamp, pd.DataFrame]:
    d = cache_dir() / "master"
    out = {}
    for fp in sorted(d.glob("*.csv")):
        m = pd.read_csv(fp, dtype=str)
        out[pd.Timestamp(fp.stem)] = m
    return out


def eligible(m: pd.DataFrame) -> set[str]:
    """上市一览 → 内国普通股、一般市场的 5 位代码。"""
    ok = (m.get("ProdCat", pd.Series("011", index=m.index)) == "011") & m["Mkt"].isin(GENERAL_MKT)
    return set(m.loc[ok, "Code"].astype(str))


def listed_mask(days: pd.DatetimeIndex, names: list[str], snaps: dict[pd.Timestamp, pd.DataFrame]) -> np.ndarray:
    """listed[d, j]：严格早于 d 的最近一个月末快照里是一般市场的内国普通股（最后一个快照一直用到数据末尾；第一个快照之前 = 否）。"""
    listed = np.zeros((len(days), len(names)), bool)
    col = {t: j for j, t in enumerate(names)}
    snap_days = sorted(snaps)
    for k, sd in enumerate(snap_days):
        nxt = snap_days[k + 1] if k + 1 < len(snap_days) else days[-1] + pd.Timedelta(days=1)
        rows = np.where((days > sd) & (days <= nxt))[0]
        js = [col[y] for y in (to_yf(c) for c in eligible(snaps[sd])) if y in col]
        if len(rows) and js:
            listed[np.ix_(rows, js)] = True
    return listed


def read_numeric(files: list[Path], codes: set[str]) -> pd.DataFrame:
    """批量日线 → 数值表（每个文件读完就转成数值，全市场约 1,100 万行也只占几百 MB）；同一天同一只票重复 → 留后面的文件。"""
    parts = []
    for fp in files:
        with gzip.open(fp, "rb") as fh:
            df = pd.read_csv(io.BytesIO(fh.read()), dtype=str, usecols=lambda c: c in COLS)
        df = df[df["Code"].isin(codes)]
        out = pd.DataFrame({"Date": pd.to_datetime(df["Date"]), "Code": df["Code"].astype(str)})
        for c in COLS[2:]:
            out[c] = pd.to_numeric(df[c], errors="coerce").astype(np.float64)
        parts.append(out)
    b = pd.concat(parts, ignore_index=True)
    return b.drop_duplicates(subset=["Date", "Code"], keep="last")


def build() -> dict:
    t0 = time.time()
    snaps = snapshots()
    codes = set().union(*[eligible(m) for m in snaps.values()])
    bars = read_numeric(PD.bar_files(), codes)
    days = pd.DatetimeIndex(sorted(bars["Date"].unique()))
    names, cols = [], {k: [] for k in ("O", "H", "L", "C", "V", "R", "MC", "VA")}
    for code, g in bars.groupby("Code"):
        yf = to_yf(code)
        if yf is None:
            continue
        df, rt = PD.adjust(g)
        if len(df) < 60:
            continue
        gi = g.drop_duplicates("Date", keep="last").set_index("Date")
        names.append(yf)
        for k, c in (("O", "Open"), ("H", "High"), ("L", "Low"), ("C", "Close"), ("V", "Volume")):
            cols[k].append(df[c].reindex(days).to_numpy(np.float32))
        cols["R"].append(rt.reindex(days).to_numpy(np.float32))
        cols["MC"].append(gi["MktCap"].reindex(days).to_numpy(np.float32))
        cols["VA"].append(gi["Va"].reindex(days).to_numpy(np.float32))
        del df, rt, gi
    P = {k: np.column_stack(v) for k, v in cols.items()}
    del cols, bars
    listed = listed_mask(days, names, snaps)
    np.savez_compressed(CACHE, days=days.to_numpy().astype("datetime64[ns]").astype(np.int64), names=np.array(names), listed=listed, **P)
    return {"days": days, "names": names, "listed": listed, **P, "build_s": round(time.time() - t0, 1)}


def load(rebuild: bool = False) -> dict:
    if CACHE.exists() and not rebuild:
        z = np.load(CACHE, allow_pickle=False)
        out = {k: z[k] for k in z.files}
        out["days"] = pd.DatetimeIndex(z["days"].astype("datetime64[ns]"))
        out["names"] = [str(x) for x in z["names"]]
        return out
    return build()


if __name__ == "__main__":
    D = load(rebuild="--rebuild" in sys.argv)
    print(len(D["days"]), "days,", len(D["names"]), "stocks;", D["days"][0].date(), "→", D["days"][-1].date(),
          "; listed avg", round(float(D["listed"].sum(axis=1).mean()), 0), "; build", D.get("build_s"), "s")
