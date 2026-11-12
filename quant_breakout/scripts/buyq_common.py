"""buyq_common.py — 买点信号质量「新角度」一轮的特征、统计与判定（2026-09-28 登记；规则写在 scripts/buyq_study.py 开头）。

特征都只用信号日收盘为止的数据（与现行一样：信号日收盘后决定、次日开盘买）；缺值（历史不够、业种不明）→ 不过滤（与 W2 缺值同一处理）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEED, BOOT_N, PLACEBO_N = 20260928, 2000, 200

VARIANTS = {
    "Q1": {"fam": "A", "col": "vr10", "op": ">=", "th": 1.0,
           "zh": "趋势性：过去 250 日的方差比 VR(10) ≥ 1（这只票的涨跌有惯性、不是来回震荡）"},
    "Q2": {"fam": "A", "col": "follow", "op": ">=", "th": 0.0,
           "zh": "放量上涨后的跟进：过去 250 日「量比 ≥ 1.5 且涨 ≥ 1%」的日子之后 10 日相对大盘的平均 ≥ 0"},
    "Q3": {"fam": "A", "col": "downrel", "op": ">=", "th": 0.0,
           "zh": "大盘跌日抗跌：过去 120 日里大盘跌 ≥ 1% 的日子，平均跑赢大盘"},
    "Q4": {"fam": "B", "col": "hlow", "op": ">", "th": 0.0,
           "zh": "箱体低点抬高：信号日前 20 日的最低 > 再之前 40 日的最低"},
    "Q5": {"fam": "B", "col": "touch", "op": ">=", "th": 2.0,
           "zh": "箱顶测试 ≥ 2 次：信号日前 60 日里最高价 ≥ 箱顶 × 0.98 的次数（相隔 ≥ 5 日算另一次）"},
    "Q6": {"fam": "B", "col": "upper", "op": ">=", "th": 0.6,
           "zh": "贴着箱顶：信号日前 20 日的收盘在 60 日箱体上半部的比例 ≥ 60%"},
    "Q7": {"fam": "C", "col": "vpct", "op": ">=", "th": 0.9,
           "zh": "少见的放量：信号日量比 ≥ 这只票过去 250 日量比的 90 分位"},
    "Q8": {"fam": "D", "col": "peers", "op": "<=", "th": 0.0,
           "zh": "孤立突破：同业种（東証 33 业种）10 个交易日内（含当天）没有别的突破信号"},
}
FAMILY = {"A": "个股性格", "B": "箱体结构", "C": "信号日放量", "D": "业种"}
FEATURES = [v["col"] for v in VARIANTS.values()]

VR_K, VR_N, VR_MIN = 10, 250, 200                       # Q1
FT_N, FT_H, FT_VR, FT_UP, FT_MIN = 250, 10, 1.5, 0.01, 6  # Q2
DN_N, DN_TH, DN_MIN = 120, -0.01, 5                     # Q3
BOX_N, BOX_RECENT, TOUCH_TOL, TOUCH_GAP, UP_N = 60, 20, 0.98, 5, 20   # Q4〜Q6
VP_N, VP_MIN = 250, 120                                 # Q7
PEER_DAYS = 10                                          # Q8

# 入选（探索）与确认的门槛（scripts/buyq_study.py 开头 三 / 四）
FRAC_LO, FRAC_HI = 0.30, 0.90
DWIN_MIN, DMEAN_MIN = 2.0, 0.20
CAL_TOL, DD_TOL = 0.02, 2.0
MAX_FINAL, MAX_FAM = 3, 2
CONF_DWIN = 1.0


# ───────────────────────── 特征（每只票、信号日 i；有测试）─────────────────────────
def variance_ratio(c: np.ndarray, k: int = VR_K) -> float:
    """c：收盘价（最后一个 = 信号日）。k 日重叠对数收益的方差 ÷ (k × 日对数收益的方差)；日收益 < VR_MIN 个 → NaN。"""
    c = np.asarray(c, float)
    c = c[np.isfinite(c) & (c > 0)]
    lr = np.diff(np.log(c))
    if len(lr) < max(VR_MIN, k + 2):
        return np.nan
    v1 = lr.var(ddof=1)
    if not v1 > 0:
        return np.nan
    cs = np.concatenate([[0.0], np.cumsum(lr)])
    rk = cs[k:] - cs[:-k]
    return float(rk.var(ddof=1) / (k * v1))


def follow_through(c: np.ndarray, vr: np.ndarray, mcum: np.ndarray, i: int) -> float:
    """事件 e ∈ [i − 250, i − 10]（之后 10 根 K 线到信号日为止都已知）：量比 vr[e] ≥ 1.5 且当天涨 ≥ 1%
    → c[e+10] / c[e] − 1 − 大盘同期（mcum = 大盘累计指数，对齐到这只票的日期）；≥ 6 个事件 → 平均（小数），否则 NaN。"""
    lo, hi = max(1, i - FT_N), i - FT_H
    if hi < lo:
        return np.nan
    e = np.arange(lo, hi + 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r1 = c[e] / c[e - 1] - 1
        ok = (vr[e] >= FT_VR) & (r1 >= FT_UP) & np.isfinite(c[e + FT_H]) & np.isfinite(mcum[e]) & np.isfinite(mcum[e + FT_H])
    e = e[ok]
    if len(e) < FT_MIN:
        return np.nan
    fwd = c[e + FT_H] / c[e] - 1 - (mcum[e + FT_H] / mcum[e] - 1)
    return float(np.mean(fwd))


def down_rel(r: np.ndarray, rm: np.ndarray, i: int) -> float:
    """过去 120 根 K 线（含信号日）里大盘日收益 ≤ −1% 的日子：这只票日收益 − 大盘日收益 的平均（小数）；< 5 天 → NaN。"""
    lo = max(1, i - DN_N + 1)
    rs, mm = r[lo:i + 1], rm[lo:i + 1]
    with np.errstate(invalid="ignore"):
        d = np.isfinite(rs) & np.isfinite(mm) & (mm <= DN_TH)
    if d.sum() < DN_MIN:
        return np.nan
    return float(np.mean(rs[d] - mm[d]))


def box_features(h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int) -> dict:  # noqa: E741
    """信号日之前 60 根 K 线（不含信号日，与现行箱体 range_pct.shift(1) 同一段）：hlow / touch / upper。"""
    if i < BOX_N:
        return {"hlow": np.nan, "touch": np.nan, "upper": np.nan}
    H, L, C = h[i - BOX_N:i], l[i - BOX_N:i], c[i - BOX_N:i]
    top, bot = np.nanmax(H), np.nanmin(L)
    lo_r, lo_p = np.nanmin(L[-BOX_RECENT:]), np.nanmin(L[:-BOX_RECENT])
    hlow = lo_r / lo_p - 1 if lo_p > 0 else np.nan
    idx = np.flatnonzero(H >= top * TOUCH_TOL)
    touch = float(1 + int(np.sum(np.diff(idx) >= TOUCH_GAP))) if len(idx) else np.nan
    mid = (top + bot) / 2
    upper = float(np.mean(C[-UP_N:] >= mid))
    return {"hlow": float(hlow), "touch": touch, "upper": upper}


def vol_pct(vr: np.ndarray, i: int) -> float:
    """信号日量比在这只票过去 250 根 K 线（不含信号日）量比里的位置（比它小的比例）；有效值 < 120 个 → NaN。"""
    past = vr[max(0, i - VP_N):i]
    past = past[np.isfinite(past)]
    if len(past) < VP_MIN or not np.isfinite(vr[i]):
        return np.nan
    return float(np.mean(past < vr[i]))


def stock_features(df: pd.DataFrame, i: int, mret: np.ndarray, mcum: np.ndarray) -> dict:
    """一只票的指标表（compute_indicators 的输出，含 vol_ratio）+ 信号日位置 i；mret / mcum = 大盘日收益 / 累计指数（对齐到 df.index）。"""
    c, h, l = (df[k].to_numpy(float) for k in ("Close", "High", "Low"))  # noqa: E741
    vr = df["vol_ratio"].to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.r_[np.nan, c[1:] / c[:-1] - 1]
    return {"vr10": variance_ratio(c[max(0, i - VR_N):i + 1]), "follow": follow_through(c, vr, mcum, i), "downrel": down_rel(r, mret, i),
            **box_features(h, l, c, i), "vpct": vol_pct(vr, i)}


def market_proxy(C: np.ndarray, days: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """等权大盘：宽表收盘（日期 × 票）里前后两天都有收盘的票的日收益平均 → (日收益, 累计指数)。"""
    with np.errstate(divide="ignore", invalid="ignore"):
        R = C[1:] / C[:-1] - 1
    R[~np.isfinite(R)] = np.nan
    cnt = np.isfinite(R).sum(axis=1)
    m = np.where(cnt > 0, np.nansum(R, axis=1) / np.maximum(cnt, 1), np.nan)
    ret = pd.Series(np.r_[np.nan, m], index=days)
    cum = (1 + ret.fillna(0.0)).cumprod()
    return ret, cum


def sector_code(ticker: str) -> str:
    return str(ticker).split(".")[0]


def peer_counts(sigs: pd.DataFrame, days: pd.DatetimeIndex, sector: dict[str, str], window: int = PEER_DAYS) -> np.ndarray:
    """sigs（ticker、date）→ 每个信号：同业种的其它票、信号日在 [当天往前 window − 1 个交易日, 当天] 的信号个数（业种不明 → NaN）。"""
    n = len(sigs)
    out = np.full(n, np.nan)
    if not n:
        return out
    pos = pd.DatetimeIndex(days).get_indexer(pd.to_datetime(sigs["date"]))
    tk = sigs["ticker"].astype(str).to_numpy()
    sec = np.array([sector.get(sector_code(t)) for t in tk], dtype=object)
    for s in pd.unique(sec[pd.notna(sec)]):
        idx = np.flatnonzero(sec == s)
        p, t = pos[idx], tk[idx]
        for a_i, a in enumerate(idx):
            d = p[a_i] - p
            out[a] = float(np.sum((d >= 0) & (d <= window - 1) & (t != t[a_i])))
    return out


def keep_of(F: pd.DataFrame, key: str) -> np.ndarray:
    """变体 key 的保留掩码（缺值 → 保留）。"""
    v = VARIANTS[key]
    x = F[v["col"]].to_numpy(float)
    with np.errstate(invalid="ignore"):
        hit = {">=": x >= v["th"], ">": x > v["th"], "<=": x <= v["th"]}[v["op"]]
    return ~np.isfinite(x) | hit


# ───────────────────────── 逐信号统计（有测试）─────────────────────────
def _st(x: np.ndarray) -> dict:
    if not len(x):
        return {"n": 0, "win": np.nan, "mean": np.nan, "avg_win": np.nan, "avg_loss": np.nan}
    w, lo = x[x > 0], x[x <= 0]
    return {"n": int(len(x)), "win": float((x > 0).mean() * 100), "mean": float(x.mean()),
            "avg_win": float(w.mean()) if len(w) else np.nan, "avg_loss": float(lo.mean()) if len(lo) else np.nan}


def delta(net: np.ndarray, keep: np.ndarray) -> dict:
    """保留 vs 全部（= 现行）：胜率差 pp、每笔差 pp；另给去掉组。"""
    net, keep = np.asarray(net, float), np.asarray(keep, bool)
    a, k, r = _st(net), _st(net[keep]), _st(net[~keep])
    return {"n": a["n"], "kept": k["n"], "frac": (k["n"] / a["n"]) if a["n"] else np.nan,
            "win_all": a["win"], "mean_all": a["mean"], "win": k["win"], "mean": k["mean"], "avg_win": k["avg_win"], "avg_loss": k["avg_loss"],
            "avg_win_all": a["avg_win"], "avg_loss_all": a["avg_loss"], "win_rm": r["win"], "mean_rm": r["mean"],
            "dwin": k["win"] - a["win"], "dmean": k["mean"] - a["mean"]}


def boot_delta(net: np.ndarray, keep: np.ndarray, months: np.ndarray, n: int = BOOT_N, seed: int = SEED) -> dict:
    """按信号月聚类的自助法：胜率差（pp）与每笔差（pp）的 95% 区间。"""
    net, keep, months = np.asarray(net, float), np.asarray(keep, bool), np.asarray(months)
    groups = [np.flatnonzero(months == m) for m in pd.unique(months)]
    rng = np.random.default_rng(seed)
    dw, dm = np.full(n, np.nan), np.full(n, np.nan)
    for b in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        x, k = net[idx], keep[idx]
        if k.sum() == 0:
            continue
        dw[b] = ((x[k] > 0).mean() - (x > 0).mean()) * 100
        dm[b] = x[k].mean() - x.mean()
    q = lambda a, p_: round(float(np.nanpercentile(a, p_)), 3)                                        # noqa: E731
    return {"dwin_lo": q(dw, 2.5), "dwin_hi": q(dw, 97.5), "dmean_lo": q(dm, 2.5), "dmean_hi": q(dm, 97.5)}


def placebo(net: np.ndarray, tickers: np.ndarray, weeks: np.ndarray, frac: float, n: int = PLACEBO_N, seed: int = SEED) -> dict:
    """随机对照：按「股票 × 周」随机保留 frac 的信号，n 次 → 每笔差 / 胜率差的 95 分位。"""
    net = np.asarray(net, float)
    keys = pd.factorize(pd.Series(np.asarray(tickers, str)) + "|" + pd.Series(np.asarray(weeks, str)))[0]
    rng = np.random.default_rng(seed)
    dm, dw = np.full(n, np.nan), np.full(n, np.nan)
    base_m, base_w = net.mean(), (net > 0).mean()
    for b in range(n):
        k = rng.random(keys.max() + 1)[keys] < frac
        if not k.any():
            continue
        dm[b] = net[k].mean() - base_m
        dw[b] = ((net[k] > 0).mean() - base_w) * 100
    return {"dmean_q95": float(np.nanpercentile(dm, 95)), "dwin_q95": float(np.nanpercentile(dw, 95))}


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return np.nan
    return float(pd.Series(x[ok]).rank().corr(pd.Series(y[ok]).rank()))


# ───────────────────────── 入选与确认（有测试）─────────────────────────
def _f(d: dict, k: str) -> float:
    v = (d or {}).get(k)
    return float(v) if v is not None else np.nan


def qualifies(j2: dict, e: dict, port: dict, base: dict) -> list[str]:
    """j2 / e：delta（j2 另加 dmean_q95）；port / base：{"E": {calmar, dd}, "J": {...}}（候选 / 现行组合）。返回没满足的条件（空 = 入选）。"""
    f = []
    for tag, x in (("J2", j2), ("E", e)):
        fr = _f(x, "frac")
        if not (FRAC_LO <= fr <= FRAC_HI):
            f.append(f"{tag} 保留比例不在 {FRAC_LO:.0%}〜{FRAC_HI:.0%}")
    if not _f(j2, "dwin") >= DWIN_MIN:
        f.append(f"J2 胜率没高 {DWIN_MIN:.0f} pp")
    if not _f(j2, "dmean") >= DMEAN_MIN:
        f.append(f"J2 每笔没高 {DMEAN_MIN:.2f} pp")
    if not _f(j2, "dmean") > _f(j2, "dmean_q95"):
        f.append("J2 每笔差没超过随机 95 分位")
    if not (_f(e, "dwin") >= 0 and _f(e, "dmean") >= 0):
        f.append("E 方向不一致")
    for era in ("E", "J"):
        x, y = (port or {}).get(era) or {}, (base or {}).get(era) or {}
        if not _f(x, "calmar") >= _f(y, "calmar") - CAL_TOL:
            f.append(f"组合 {era} Calmar 低 {CAL_TOL} 以上")
        if not _f(x, "dd") >= _f(y, "dd") - DD_TOL:
            f.append(f"组合 {era} 回撤深 {DD_TOL:.0f} pp 以上")
    return f


def pick(res: dict) -> list[str]:
    """res：{key: {"fails": [...], "j2": {...}}} → 入选（≤ 3，同一族 ≤ 2），按 J2 每笔差从大到小（同分按名字）。"""
    ok = [k for k in res if not res[k]["fails"]]
    out: list[str] = []
    fam: dict[str, int] = {}
    for k in sorted(ok, key=lambda x: (-_f(res[x]["j2"], "dmean"), x)):
        f = VARIANTS[k]["fam"]
        if fam.get(f, 0) >= MAX_FAM:
            continue
        out.append(k)
        fam[f] = fam.get(f, 0) + 1
        if len(out) >= MAX_FINAL:
            break
    return out


def verdict(c: dict, z: dict, w: dict) -> str:
    """c = Z + W 合起来（delta + boot_delta）；z、w 各自（delta）。"""
    if _f(c, "dmean_lo") > 0 and _f(c, "dwin") >= CONF_DWIN and _f(z, "dmean") >= 0 and _f(w, "dmean") >= 0:
        return "确认"
    if _f(c, "dmean") > 0 and _f(c, "dwin") > 0:
        return "方向一致"
    return "不通过"
