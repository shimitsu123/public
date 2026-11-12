"""allsec_data.py — J-Quants 东证全部上市品种（内国株 + ETF / ETN + REIT / インフラ + 外国株 + PRO 市场 等）的日线面板（研究用，2026-10-05 用户
「③ 在 ② 之外再加 ETF / REIT 等 进行研究图形」；turn_shape_wide.py 用）。

与 allstock_data.py（只有一般市场的内国普通股）的区别只有三处：
- 品种 = 任何一个月末上市一览里出现过的代码（不按 ProdCat / 市场筛）；优先株、新株予约权等（代码第 5 位 ≠ 0）也算，名字用 5 位原码；
- cat[d, j] = 严格早于 d 的最近一个月末快照里这个代码的分类（见 CAT；0 = 当时不在上市一览）—— 与 allstock_data.listed_mask 同一个时点规则；
- 日期截止 END（= turn_shape_study 用的 allstock_panels 的最后一天），方便原样本对照（U0）逐行一致。
价格口径与 allstock_data 相同（qbreak/pit_data.adjust：拆股调整、价格缺 / 非正的日子丢掉；整段不足 60 根的代码不收）。
原始数据与整理结果都只在 var/cache/jquants/（已 gitignore；allsec_panels.npz），不入库。
用法：python scripts/allsec_data.py [--rebuild]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import pit_data as PD                                            # noqa: E402
from qbreak.jquants import cache_dir, to_yf                                  # noqa: E402
import allstock_data as AD                                                   # noqa: E402

END = "2026-09-25"
CACHE = cache_dir() / "allsec_panels.npz"
MIN_BARS = 60
CAT = {0: "当时不在上市一览", 1: "内国普通株（一般市场）", 2: "内国株・其他（TOKYO PRO MARKET / 优先株 / 新株予约权）", 3: "REIT / インフラファンド",
       4: "国内 ETF", 5: "外国 ETF / ETN 等", 6: "外国株", 7: "出資証券", 8: "其他（分类不明）"}
PROD_CAT = {"013": 3, "014": 4, "023": 5, "021": 6, "012": 7}


def category(prod: str, mkt: str, code: str) -> int:
    """月末上市一览的一行 → 分类码（CAT）。"""
    if prod == "011":
        return 1 if (mkt in AD.GENERAL_MKT and str(code).endswith("0")) else 2
    return PROD_CAT.get(prod, 8)


def name_of(code5: str) -> str:
    """一般的 5 位代码 → yfinance 风格（与 allstock_data 的名字一致）；第 5 位 ≠ 0 的 → 原码。"""
    return to_yf(code5) or str(code5)


def cat_matrix(days: pd.DatetimeIndex, codes: list[str], snaps: dict[pd.Timestamp, pd.DataFrame]) -> np.ndarray:
    """cat[d, j]：严格早于 d 的最近一个月末快照里的分类（最后一个快照一直用到数据末尾；第一个快照之前 = 0）。"""
    out = np.zeros((len(days), len(codes)), np.int8)
    col = {c: j for j, c in enumerate(codes)}
    snap_days = sorted(snaps)
    for k, sd in enumerate(snap_days):
        nxt = snap_days[k + 1] if k + 1 < len(snap_days) else days[-1] + pd.Timedelta(days=1)
        rows = np.where((days > sd) & (days <= nxt))[0]
        if not len(rows):
            continue
        m = snaps[sd]
        prod = m["ProdCat"] if "ProdCat" in m else pd.Series("011", index=m.index)
        for code, pc, mk in zip(m["Code"].astype(str), prod.astype(str), m["Mkt"].astype(str)):
            j = col.get(code)
            if j is not None:
                out[rows, j] = category(pc, mk, code)
    return out


def assemble(bars: pd.DataFrame, snaps: dict[pd.Timestamp, pd.DataFrame], end: str = END) -> dict:
    """数值日线（read_numeric 的格式）+ 月末快照 → 面板 dict（days / names / codes / cat / O H L C V R MC VA）。"""
    in_snap = set().union(*[set(m["Code"].astype(str)) for m in snaps.values()]) if snaps else set()
    bars = bars[(bars["Date"] <= pd.Timestamp(end)) & bars["Code"].isin(in_snap)]
    days = pd.DatetimeIndex(sorted(bars["Date"].unique()))
    codes, names, cols = [], [], {k: [] for k in ("O", "H", "L", "C", "V", "R", "MC", "VA")}
    for code, g in bars.groupby("Code"):
        df, rt = PD.adjust(g)
        if len(df) < MIN_BARS:
            continue
        gi = g.drop_duplicates("Date", keep="last").set_index("Date")
        codes.append(str(code))
        names.append(name_of(str(code)))
        for k, c in (("O", "Open"), ("H", "High"), ("L", "Low"), ("C", "Close"), ("V", "Volume")):
            cols[k].append(df[c].reindex(days).to_numpy(np.float32))
        cols["R"].append(rt.reindex(days).to_numpy(np.float32))
        cols["MC"].append(gi["MktCap"].reindex(days).to_numpy(np.float32))
        cols["VA"].append(gi["Va"].reindex(days).to_numpy(np.float32))
    P = {k: (np.column_stack(v) if v else np.zeros((len(days), 0), np.float32)) for k, v in cols.items()}
    return {"days": days, "names": names, "codes": codes, "cat": cat_matrix(days, codes, snaps), **P}


def build() -> dict:
    t0 = time.time()
    snaps = AD.snapshots()
    codes = set().union(*[set(m["Code"].astype(str)) for m in snaps.values()])
    D = assemble(AD.read_numeric(PD.bar_files(), codes), snaps)
    np.savez_compressed(CACHE, days=D["days"].to_numpy().astype("datetime64[ns]").astype(np.int64), names=np.array(D["names"]),
                        codes=np.array(D["codes"]), **{k: D[k] for k in ("cat", "O", "H", "L", "C", "V", "R", "MC", "VA")})
    D["build_s"] = round(time.time() - t0, 1)
    return D


def load(rebuild: bool = False) -> dict:
    if CACHE.exists() and not rebuild:
        z = np.load(CACHE, allow_pickle=False)
        out = {k: z[k] for k in z.files}
        out["days"] = pd.DatetimeIndex(z["days"].astype("datetime64[ns]"))
        out["names"] = [str(x) for x in z["names"]]
        out["codes"] = [str(x) for x in z["codes"]]
        return out
    return build()


if __name__ == "__main__":
    D = load(rebuild="--rebuild" in sys.argv)
    cat = D["cat"]
    print(len(D["days"]), "days,", len(D["names"]), "codes;", D["days"][0].date(), "→", D["days"][-1].date(), "; build", D.get("build_s"), "s")
    ever = {k: int(((cat == k).any(axis=0)).sum()) for k in CAT if k}
    print("每类出现过的代码数：", {CAT[k]: v for k, v in ever.items()})
