"""sector_influence.py — 「各行业影响占比」：東証 33 業種在 TOPIX 每天涨跌里的份额（日报「时代主线」一栏用；只作展示，不改交易）。
2026-09-28 用户：「时间主线从一年改为3个月一判定，时间主线要标记当前各行业影响占比」。

口径（近 N 个交易日，缺省 63 ≈ 3 个月）：
  r_i = 業種别指数的日收益，r_T = TOPIX 的日收益。TOPIX = 各業種按时价总额加权 → r_T ≈ Σ w_i · r_i。
  w = 用这 N 天回归估计的时价总额比重（系数和 = 1；负的去掉后重算）；拟合 R² 应接近 1（写在输出里，作为核对）。
  影响占比_i = w_i · cov(r_i, r_T) ÷ var(r_T)（全部業種加起来 = 100%）=「这 N 天 TOPIX 的涨跌里有多少来自这个業種」：
    比重大、又和大盘同涨同跌的業種占比高；比重大但走自己路的業種占比低。另给 w（时价总额比重）与这 N 天相对 TOPIX 的涨跌。
数据：J-Quants /indices/bars/daily（Standard 档；0000 = TOPIX、0040〜0060 = 東証 33 業種別指数）。2026-09-29 核对代码对应：
  每个代码的日收益与同名業種成员（J-Quants 时点 TOPIX 1000）等权收益的相关最高（0.53〜0.97；その他製品 0.57 排第二、与情報・通信 0.59 接近）。
  原始指数值只缓存在 var/cache/jquants/indices/（已 gitignore，J-Quants 规约不许再分发）；日报 / 前向记录只放算好的占比。
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

TOPIX = "0000"
S33_CODES: dict[str, str] = {
    "0040": "水産・農林業", "0041": "鉱業", "0042": "建設業", "0043": "食料品", "0044": "繊維製品", "0045": "パルプ・紙",
    "0046": "化学", "0047": "医薬品", "0048": "石油・石炭製品", "0049": "ゴム製品", "004A": "ガラス・土石製品", "004B": "鉄鋼",
    "004C": "非鉄金属", "004D": "金属製品", "004E": "機械", "004F": "電気機器", "0050": "輸送用機器", "0051": "精密機器",
    "0052": "その他製品", "0053": "電気・ガス業", "0054": "陸運業", "0055": "海運業", "0056": "空運業", "0057": "倉庫・運輸関連業",
    "0058": "情報・通信業", "0059": "卸売業", "005A": "小売業", "005B": "銀行業", "005C": "証券、商品先物取引業", "005D": "保険業",
    "005E": "その他金融業", "005F": "不動産業", "0060": "サービス業"}
WINDOW = 63
MIN_DAYS = 40


def fetch(client, frm: str, cache_dir=None, today: str | None = None) -> pd.DataFrame:
    """TOPIX + 33 業種别指数的收盘（日期 × 業種名，另一列 TOPIX）。同一天已经取过 → 读缓存（cache_dir/indices_<today>.csv）。"""
    today = today or dt.date.today().isoformat()
    fp = None
    if cache_dir is not None:
        fp = cache_dir / f"indices_{today}.csv"
        if fp.exists():
            return pd.read_csv(fp, index_col=0, parse_dates=True)
    cols = {}
    for code in [TOPIX] + list(S33_CODES):
        rows = client.get("/indices/bars/daily", code=code, **{"from": frm})
        if not rows:
            continue
        df = pd.DataFrame(rows)
        cols["TOPIX" if code == TOPIX else S33_CODES[code]] = pd.Series(pd.to_numeric(df["C"], errors="coerce").to_numpy(float),
                                                                         index=pd.to_datetime(df["Date"]))
    C = pd.DataFrame(cols).sort_index()
    if fp is not None and len(C):
        fp.parent.mkdir(parents=True, exist_ok=True)
        C.to_csv(fp)
    return C


def weights(R: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """min ‖y − R w‖² 且 Σ w = 1、w ≥ 0（负的去掉后在其余業種上重算，直到没有负的）；返回 (w, 拟合 R²)。"""
    n = R.shape[1]
    act = np.ones(n, bool)
    w = np.zeros(n)
    for _ in range(n):
        A = R[:, act]
        k = A.shape[1]
        K = np.zeros((k + 1, k + 1))
        K[:k, :k] = 2 * A.T @ A
        K[:k, k] = 1.0
        K[k, :k] = 1.0
        sol = np.linalg.lstsq(K, np.r_[2 * A.T @ y, 1.0], rcond=None)[0][:k]
        w = np.zeros(n)
        w[act] = sol
        if (sol >= 0).all():
            break
        act[np.flatnonzero(act)[sol < 0]] = False
    w = np.clip(w, 0, None)
    w = w / w.sum() if w.sum() > 0 else w
    resid = y - R @ w
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else np.nan
    return w, float(r2)


def shares(C: pd.DataFrame, window: int = WINDOW, start=None, end=None) -> dict:
    """C = fetch() 的收盘。窗口 = [start, end] 的交易日（给了 start 时）或最近 window 个交易日（到 end 为止）。
    返回 {window: [首日, 末日], n_days, r2, rows: {業種: {share, weight, rel}}}（share / weight / rel 都是 %；rel = 窗口里相对 TOPIX 的涨跌）。"""
    if "TOPIX" not in C.columns:
        return {"error": "没有 TOPIX"}
    X = C.sort_index()
    if end is not None:
        X = X[X.index <= pd.Timestamp(end)]
    R = X.pct_change().iloc[1:]
    if start is not None:
        R = R[R.index >= pd.Timestamp(start)]
    else:
        R = R.iloc[-window:]
    names = [c for c in R.columns if c != "TOPIX"]
    R = R.dropna(subset=["TOPIX"])
    R = R[R[names].notna().all(axis=1)]
    if len(R) < MIN_DAYS:
        return {"error": f"只有 {len(R)} 个交易日（< {MIN_DAYS}）"}
    Rs, y = R[names].to_numpy(float), R["TOPIX"].to_numpy(float)
    w, r2 = weights(Rs, y)
    cov = np.array([np.cov(Rs[:, j], y)[0, 1] for j in range(len(names))])
    contrib = w * cov / y.var(ddof=1)
    share = contrib / contrib.sum() * 100 if contrib.sum() > 0 else contrib * np.nan
    cum = (1 + R).prod() - 1
    rows = {g: {"share": round(float(share[j]), 2), "weight": round(float(w[j] * 100), 2),
                "rel": round(float((cum[g] - cum["TOPIX"]) * 100), 2)} for j, g in enumerate(names)}
    return {"window": [str(R.index[0].date()), str(R.index[-1].date())], "n_days": int(len(R)), "r2": round(r2, 5),
            "rows": dict(sorted(rows.items(), key=lambda kv: -kv[1]["share"]))}
