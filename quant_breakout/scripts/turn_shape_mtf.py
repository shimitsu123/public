"""turn_shape_mtf.py — 「起涨点 / 起跌点 × 图形」的周线 / 月线尺度：起点本身也按周线、月线来定义，再一起看日 / 周 / 月线特征
（2026-10-05 登记；先提交后运行、只运行一次、结果出来不改规则）。

用户（2026-10-05）：「上述不管分析日线 也要加上分析周线和月线一起进行分析研究特征」。
来由：turn_shape_study / turn_shape_wide 的特征与平均形状已经有日 / 周 / 月线，但「起涨点 / 起跌点」只按日线定义
  （前后 10 个交易日最低 / 最高、40 个交易日内先到 M）。这一轮把起点也放到周线、月线的尺度上：几周到半年的起涨 / 起跌（周线）、
  几个月到一年的起涨 / 起跌（月线），日线尺度的结果直接引用 turn_shape_wide（U2，登记 2757571），三种尺度并排比较。

样本（与 turn_shape_wide 的 U2 同一范围：东证全部上市品种、不设流动性下限）：每个已完成的周（月）的最后一个交易日 × 当时在上市一览里的品种，
  要求这一周（月）有成交、有效日线 ≥ 60 根、M 算得出；起点要看之后 h 根 K 线，最后 h 根不进样本。
起涨点（周 / 月线尺度）= 这一根的收盘是前后 ext 根里最低，且之后 h 根内收盘先涨到 +M、没有先跌到 −M ÷ 2；起跌点相反
  （与日线定义同一写法：qbreak 的 bar 规则只用已完成的 K 线；σ = 向前填补的周 / 月收盘的对数收益的标准差）：
  - 周线 W：ext ±8 周、h 26 周、σ 用 52 周、M = 2σ√26，限 18〜72%；
  - 月线 M：ext ±6 个月、h 12 个月、σ 用 24 个月、M = 2σ√12，限 25〜100%；
  （上下限 = 日线的 10〜40% × √(期限交易日数 ÷ 40)：周 26 × 5 = 130 日、月 12 × 21 = 252 日。）
特征：与原研究相同的 46 个日 / 周 / 月线特征（在起点那天收盘时已知；周 / 月线只用已完成的 K 线）+ 30 种经典形态 × 3 周期；平均形状 = 日 / 周 / 月线。
模型与判定：L2 逻辑回归，2017-10〜2021-12 学、2022-01〜 检验；log 时价总额缺 → 同一天中位数，检验时缺的特征标准化后补 0（同 U2）。
  之后的超额 = 下一个交易日开盘买、h_ret 个交易日后收盘（周 65 日 ≈ 13 周、月 126 日 ≈ 6 个月 = 定义期限的一半，与日线 40 → 20 同比例），
  减同一天全部样本平均；每个样本日分十组；最像一组的 95% 区间按簇自助（周 = 季度、月 = 半年，簇长 ≈ 持有期，避免重叠持有期算得太窄）。
  G1〜G6 同原研究，金额门槛按持有期等比放大（每天的优势与日线门槛相同）：周 ×3.25（最高 − 最低 ≥ 3.25 pp、比基础多 ≥ 1.63 pp），
  月 ×6.3（≥ 6.3 pp、≥ 3.15 pp）；G5 = 有数据的年份里最多一年方向不对（日线 5 年要 4 年 = 原规则）。
  另报「近 ext 根新低 / 新高」（当天已知）里的 AUC（turn_shape_posthoc 的读法）。
分组（确认期，同 turn_shape_wide）：A 原样本条件 / B 成交少的普通股 / C 上市未满约 1 年 / D ETF・ETN / E REIT・インフラ / F 其他；
  组内每天分组（平均每天 ≥ 50 行十组、20〜49 五组、更少只报 AUC），超额减本组同一天平均；「有信息」= 按方向的最像 − 最不像 ≥ 门槛（周 3.25 pp、月 6.3 pp）
  且最像一组区间不含 0。注意：周 / 月线的 σ 要 52 周 / 24 个月 → 上市不满约 1 / 2 年的 C 组基本没有样本（定义需要）。
读法（事先写定）：任一尺度的上涨 / 下跌模型 G1〜G6 全过 → 「该尺度图形有用」→ 提议另外登记策略检验（用户确认）；只过 G3、G5 →「有信息」（只记录）；
  其余「没有用」。结论上限 = 记录 + 提议；不改模拟盘、执行器、例行任务。
事前预期：周 / 月线的起点同样是「本周期的最后一段急跌 / 急涨」（定义带来的）；模型 AUC 仍高（0.8 以上）但主要认出新低 / 新高（其中约 0.6）；
  月线尺度可能借 12-1 动量 / 长期反转看到一点东西，但持有期长、样本月少（确认期约 44 个月）→ 全过 G1〜G6 约 10%，「有信息」约 20%。非投资建议。
用法：python scripts/turn_shape_mtf.py --counts（登记前只数个数）；python scripts/turn_shape_mtf.py --run（只运行一次）
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402
import turn_shape_study as S                                                  # noqa: E402
import turn_shape_wide as W                                                   # noqa: E402

BAR_DAYS = {"W": 5, "M": 21}
SCALES = {"W": {"freq": "W", "ext": 8, "h": 26, "sig_n": 52, "h_ret": 65, "cluster": "Q"},
          "M": {"freq": "M", "ext": 6, "h": 12, "sig_n": 24, "h_ret": 126, "cluster": "H"}}
NAMES = {"W": "周线尺度", "M": "月线尺度"}
OUT_MD, OUT_JSON = "turn_shape_mtf.md", "turn_shape_mtf.json"


def m_bounds(sc: str) -> tuple[float, float]:
    """M 的上下限 = 日线的 [10%, 40%] × √(期限交易日数 ÷ 40)。"""
    f = np.sqrt(SCALES[sc]["h"] * BAR_DAYS[sc] / S.H_LAB)
    return round(S.M_LO * f, 2), round(S.M_HI * f, 2)


def scale_factor(sc: str) -> float:
    """金额门槛的放大倍数 = 持有期 ÷ 日线的 20 日。"""
    return SCALES[sc]["h_ret"] / S.H_RET[0]


# ───────────────────────── 标注（K 线层面） ─────────────────────────
def swing_labels(Cb: np.ndarray, ext: int, h: int, sig_n: int, m_lo: float, m_hi: float) -> dict[str, np.ndarray]:
    """K 线收盘 → σ、M、起涨点 RS、起跌点 FS（与 turn_shape_study.labels 同一写法，单位换成 K 线；σ 用向前填补的收盘）。"""
    Cf = S.ffill(Cb)
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.diff(np.log(Cf), axis=0, prepend=np.nan)
    sig = S.rstd(lr, sig_n)
    M = np.clip(S.M_K * sig * np.sqrt(h), m_lo, m_hi)
    w = 2 * ext + 1
    lo = pd.DataFrame(Cb).rolling(w, center=True, min_periods=ext + ext // 2).min().to_numpy()
    hi = pd.DataFrame(Cb).rolling(w, center=True, min_periods=ext + ext // 2).max().to_numpy()
    fin = np.isfinite(Cb) & np.isfinite(M)
    with np.errstate(invalid="ignore"):
        is_lo, is_hi = fin & (Cb <= lo), fin & (Cb >= hi)
    u1, d1 = S.first_pass(Cf, Cb, 1 + M, 1 - M / 2, h=h)
    RS = is_lo & np.isfinite(u1) & (u1 < d1)
    u2, d2 = S.first_pass(Cf, Cb, 1 + M / 2, 1 - M, h=h)
    FS = is_hi & np.isfinite(d2) & (d2 < u2)
    return {"sig": sig, "M": M, "RS": RS, "FS": FS}


def take_bar(arr: np.ndarray, pos: np.ndarray, kk: np.ndarray, jj: np.ndarray) -> np.ndarray:
    """K 线层面的值 → 样本行（第 k 天当天已完成的最近一根）。"""
    b = pos[kk]
    out = np.full(len(kk), np.nan)
    ok = b >= 0
    out[ok] = np.asarray(arr, float)[b[ok], jj[ok]]
    return out


# ───────────────────────── 样本 ─────────────────────────
def bar_end_rows(days: pd.DatetimeIndex, cdays: pd.DatetimeIndex, n_bars: int, h: int, h_ret: int) -> np.ndarray:
    """可以当样本日的 K 线完成日的位置：START 之后、之后还有 h 根 K 线（看得到起点是否成立）、还有 h_ret + 1 个交易日（看得到结果）。"""
    kpos = np.searchsorted(days.to_numpy(dtype="datetime64[ns]"), cdays.to_numpy(dtype="datetime64[ns]"))
    b = np.arange(len(cdays))
    ok = (cdays >= pd.Timestamp(S.START)) & (b + h <= n_bars - 1) & (kpos + h_ret + 1 <= len(days) - 1)
    return kpos[ok]


def group_codes(cat: np.ndarray, hist: np.ndarray, va20: np.ndarray) -> np.ndarray:
    """面板层面的组（A〜F，同 turn_shape_wide.groups_of；A = 原研究的样本条件）。"""
    g = np.full(cat.shape, "F", dtype=object)
    g[np.isin(cat, (4, 5))] = "D"
    g[cat == 3] = "E"
    s1 = cat == 1
    with np.errstate(invalid="ignore"):
        g[s1 & (hist < S.HIST_MIN)] = "C"
        g[s1 & (hist >= S.HIST_MIN) & ~(va20 >= S.VA_MIN)] = "B"
        g[s1 & (hist >= S.HIST_MIN) & (va20 >= S.VA_MIN)] = "A"
    return g


def scale_masks(A: dict, days: pd.DatetimeIndex, sc: str) -> dict:
    """周 / 月线尺度：K 线、标注、样本（面板 T × N）与登记前要数的「M 算不出」个数。"""
    cfg = SCALES[sc]
    P = {k: A[k].astype(float) for k in ("O", "H", "L", "C", "V")}
    B, cdays, pos = S.bar_panels(P, days, cfg["freq"])
    lo_m, hi_m = m_bounds(sc)
    L = swing_labels(B["C"], cfg["ext"], cfg["h"], cfg["sig_n"], lo_m, hi_m)
    rows = bar_end_rows(days, cdays, len(cdays), cfg["h"], cfg["h_ret"])
    hist = np.cumsum(np.isfinite(A["C"]), axis=0)
    base = np.zeros(A["C"].shape, bool)
    bidx = pos[rows]
    base[rows] = (A["cat"][rows] > 0) & np.isfinite(B["C"][bidx]) & (hist[rows] >= W.HIST_WIDE)
    mfin = np.zeros(A["C"].shape, bool)
    mfin[rows] = np.isfinite(L["M"][bidx])
    return {"B": B, "cdays": cdays, "pos": pos, "L": L, "mask": base & mfin, "base": base, "hist": hist}


# ───────────────────────── 计算 ─────────────────────────
def judge_scaled(s: int, g1_auc, auc_base, top: dict, bottom: dict, top_ci: tuple, top_base: dict, years: dict, large: dict, scale: float) -> dict:
    """turn_shape_study.judge，金额门槛 × scale；G5 = 有数据的年份里最多一年方向不对。"""
    g = {}
    g["G1"] = g1_auc is not None and g1_auc >= S.AUC_MIN
    g["G2"] = g1_auc is not None and auc_base is not None and g1_auc - auc_base >= S.AUC_INC
    lo, hi = top_ci
    s_lo = None if lo is None else (lo * 100 if s > 0 else -hi * 100)
    g["G3"] = (s * top["R20x"] > 0) and s_lo is not None and s_lo > 0 and s * (top["R20x"] - bottom["R20x"]) >= S.SPREAD_PP * scale
    g["G4"] = s * (top["R20x"] - top_base["R20x"]) >= S.TOP_INC_PP * scale
    yrs = [v for v in years.values() if v.get("n")]
    g["G5"] = sum(1 for v in yrs if s * v["R20x"] > 0) >= max(1, len(yrs) - 1)
    g["G6"] = bool(large) and s * (large.get("top", np.nan) - large.get("bottom", np.nan)) > 0
    if all(g.values()):
        tier = "图形有用 → 提议另外登记策略检验（用户确认）"
    elif g["G3"] and g["G5"]:
        tier = "有信息、但不比常用因子多 / 只在小型股（只记录）"
    else:
        tier = "没有用"
    return {"gates": g, "tier": tier, "s_ci_lo_pp": None if s_lo is None else round(s_lo, 3)}


def cluster_of(d: pd.Series, how: str) -> np.ndarray:
    if how == "Q":
        return d.dt.to_period("Q").astype(str).to_numpy()
    if how == "H":
        return (d.dt.year.astype(str) + "H" + np.where(d.dt.month <= 6, "1", "2")).to_numpy()
    return d.dt.to_period("M").astype(str).to_numpy()


def prep_scale(T: pd.DataFrame, names: list[str], n225: set, cluster: str) -> pd.DataFrame:
    x = T.loc[:, [c for c in T.columns if c not in W.KEEP_DROP]].reset_index(drop=True)
    r = x["R20"]
    x["R20x"] = (r - r.groupby(x["date"]).transform("mean")).astype(np.float32)
    x["mc_rank"] = x.groupby("date")["lmc"].rank(ascending=False, method="first").astype(np.float32)
    x["n225"] = np.isin(np.array(names, dtype=object)[x["j"].to_numpy()], list(n225))
    x["clu"] = cluster_of(x["date"], cluster)
    return x


def counts_scale(x: pd.DataFrame) -> dict:
    w = S.windows(x)
    out = {"rows": int(len(x)), "days": int(x["date"].nunique()), "first": str(x["date"].min().date()), "last": str(x["date"].max().date())}
    for k, m in w.items():
        xx = x[m]
        out[k] = {"rows": int(len(xx)), "days": int(xx["date"].nunique()), "per_day": round(float(xx.groupby("date").size().mean()), 1),
                  "RS_pct": round(float(xx["RS"].mean()) * 100, 2), "FS_pct": round(float(xx["FS"].mean()) * 100, 2),
                  "M_median_pct": round(float(np.nanmedian(xx["M"])) * 100, 1),
                  "complete_rows_pct": round(float(xx[S.FEATS].notna().all(axis=1).mean()) * 100, 1)}
    return out


def fit_scale(x: pd.DataFrame, scale: float) -> tuple[dict, dict, pd.DataFrame]:
    """模型（同 U2：补 log 时价总额、检验期缺的特征补 0）；判定用放大后的门槛、簇 = clu。"""
    w = S.windows(x)
    F = x[S.FEATS].astype(float)
    F["lmc"] = F["lmc"].fillna(F["lmc"].groupby(x["date"]).transform("median"))
    comp = F.notna().all(axis=1).to_numpy()
    xi, ci = w["X"] & comp, w["C"]
    Xr = F.loc[xi].to_numpy(float)
    Xs, st = S.winsor_std(Xr, Xr)
    Xc = S.apply_std(F.loc[ci].to_numpy(float), st)
    del F
    Xc = np.where(np.isfinite(Xc), Xc, 0.0)
    bi = [S.FEATS.index(f) for f in S.BASELINE]
    Dc = x[ci].reset_index(drop=True)
    out, scores = {}, {}
    for mk, (lab, s) in S.MODELS.items():
        y = x.loc[xi, lab].to_numpy(float)
        wf, wb = S.fit_logit(Xs, y), S.fit_logit(Xs[:, bi], y)
        sc, sb = S.predict(wf, Xc), S.predict(wb, Xc[:, bi])
        scores[mk] = sc
        yc = Dc[lab].to_numpy(float)
        dec, decb = S.deciles_by_day(sc, Dc["date"].to_numpy()), S.deciles_by_day(sb, Dc["date"].to_numpy())
        ds, dsb = dec_stats(Dc, dec), dec_stats(Dc, decb)
        topm = dec == S.N_DEC - 1
        ci_top = S.boot_ci(Dc.loc[topm, "R20x"].to_numpy(float), Dc.loc[topm, "clu"].to_numpy())
        years = {}
        for yv in sorted(Dc["date"].dt.year.unique()):
            mm = topm & (Dc["date"].dt.year == yv).to_numpy()
            years[int(yv)] = {"n": int(mm.sum()), "R20x": round(float(np.nanmean(Dc.loc[mm, "R20x"])) * 100, 3) if mm.any() else None}
        large = W.sub_split(sc, Dc, (Dc["mc_rank"] <= S.LARGE_N).to_numpy())
        n225d = W.sub_split(sc, Dc, Dc["n225"].to_numpy(bool))
        a_full, a_base = S.auc(sc, yc), S.auc(sb, yc)
        J = judge_scaled(s, a_full, a_base, ds[S.N_DEC - 1], ds[0], ci_top, dsb[S.N_DEC - 1], years, large, scale)
        ext = Dc["lo10" if lab == "RS" else "hi10"].to_numpy(bool)
        coefs = sorted(zip(S.FEATS, wf[1:]), key=lambda kv: -abs(kv[1]))
        out[mk] = {"label": lab, "sign": s, "n_train": int(xi.sum()), "n_test": int(ci.sum()), "train_rate_pct": round(float(y.mean()) * 100, 2),
                   "auc": a_full, "auc_base": a_base, "auc_ext": S.auc(sc[ext], yc[ext]), "deciles": ds, "deciles_base": dsb,
                   "top_ci_pp": [None if v is None else round(v * 100, 3) for v in ci_top], "years": years, "large": large, "n225": n225d,
                   "coef": [{"f": f, "b": round(float(b), 4)} for f, b in coefs[:12]], **J}
    return out, scores, Dc


def dec_stats(D: pd.DataFrame, dec: np.ndarray) -> dict:
    out = {}
    for d in range(S.N_DEC):
        x = D[dec == d]
        if len(x):
            out[d] = {"n": int(len(x)), "R20x": round(float(np.nanmean(x["R20x"])) * 100, 3),
                      "RS": round(float(np.nanmean(x["RS"])) * 100, 2), "FS": round(float(np.nanmean(x["FS"])) * 100, 2)}
    return out


def cell_scaled(Dc: pd.DataFrame, scores: dict, m: np.ndarray, info_pp: float) -> dict:
    """一个组（确认期）：比例、组内 AUC、新低 / 新高里的 AUC、组内每天分组之后的超额（减本组同一天平均）；门槛 info_pp。"""
    g = Dc[m].reset_index(drop=True)
    if not len(g):
        return {"rows": 0}
    r = g["R20"].to_numpy(float)
    rg = r - pd.Series(r).groupby(g["date"].to_numpy()).transform("mean").to_numpy()
    per_day = float(g.groupby("date").size().mean())
    nb = W.n_bins(per_day)
    out = {"rows": int(len(g)), "per_day": round(per_day, 1), "RS_pct": round(float(g["RS"].mean()) * 100, 2), "FS_pct": round(float(g["FS"].mean()) * 100, 2),
           "M_median_pct": round(float(np.nanmedian(g["M"])) * 100, 1), "bins": nb}
    for mk, (lab, s) in S.MODELS.items():
        sc = scores[mk][m]
        y = g[lab].to_numpy(float)
        ext = g["lo10" if lab == "RS" else "hi10"].to_numpy(bool)
        res = {"auc": S.auc(sc, y), "auc_ext": S.auc(sc[ext], y[ext])}
        if nb:
            b = S.deciles_by_day(sc, g["date"].to_numpy(), n=nb)
            top, bot = b == nb - 1, b == 0
            lo, hi = S.boot_ci(rg[top], g.loc[top, "clu"].to_numpy())
            t, bo = float(np.nanmean(rg[top])) * 100, float(np.nanmean(rg[bot])) * 100
            ok_ci = lo is not None and ((lo > 0) if s > 0 else (hi < 0))
            res.update({"top_pp": round(t, 3), "bottom_pp": round(bo, 3), "spread_pp": round(s * (t - bo), 3),
                        "top_ci_pp": [None if v is None else round(v * 100, 3) for v in (lo, hi)], "info": bool(s * (t - bo) >= info_pp and ok_ci)})
        out[mk] = res
    return out


def build_scale(A: dict, days: pd.DatetimeIndex, names: list[str], sc: str, run: bool, say) -> tuple[pd.DataFrame, dict, dict]:
    """样本表：特征 / 形态 / 平均形状用 turn_shape_study.build_table（只换样本行），再换上本尺度的标注与结果。"""
    cfg = SCALES[sc]
    mk = scale_masks(A, days, sc)
    orig = S.sample_mask
    S.sample_mask = lambda A_, d_: mk["mask"]
    try:
        T, paths_ = S.build_table(A, days, names, with_patterns=run, with_paths=run, say=say)
    finally:
        S.sample_mask = orig
    kk, jj = T["k"].to_numpy(), T["j"].to_numpy()
    pos, L = mk["pos"], mk["L"]
    lo, hi = S.rmin(mk["B"]["C"], cfg["ext"] + 1), S.rmax(mk["B"]["C"], cfg["ext"] + 1)
    with np.errstate(invalid="ignore"):
        lo_b, hi_b = mk["B"]["C"] <= lo, mk["B"]["C"] >= hi
    Cf = S.ffill(A["C"].astype(float))
    R = S.ratio(S.fwd(Cf, cfg["h_ret"]), S.fwd(A["O"].astype(float), 1)) - 1
    with np.errstate(invalid="ignore", divide="ignore"):
        sig60f = S.rstd(np.diff(np.log(Cf), axis=0, prepend=np.nan), S.SIG_N)   # 特征 sig60 同 U2：向前填补口径
    va20 = S.rmean(A["VA"].astype(float), S.VA_N)
    new = {"RS": take_bar(L["RS"], pos, kk, jj) > 0.5, "FS": take_bar(L["FS"], pos, kk, jj) > 0.5, "M": take_bar(L["M"], pos, kk, jj),
           "sig_bar": take_bar(L["sig"], pos, kk, jj), "lo10": take_bar(lo_b, pos, kk, jj) > 0.5, "hi10": take_bar(hi_b, pos, kk, jj) > 0.5,
           "R20": R[kk, jj], "sig60": sig60f[kk, jj], "cat": A["cat"][kk, jj].astype(np.int8), "hist": mk["hist"][kk, jj].astype(np.int32), "va20": va20[kk, jj].astype(np.float32)}
    T = T.drop(columns=[c for c in ("RS", "FS", "M", "U", "D", "R20", "R40", "R20x", "R40x", "sig60") if c in T.columns]).assign(**new)
    T["group"] = group_codes(T["cat"].to_numpy(), T["hist"].to_numpy(), T["va20"].to_numpy())
    gp = group_codes(A["cat"], mk["hist"], va20)
    pre = {k: {"rows_before_M": int((mk["base"] & (gp == k)).sum()), "rows": int((mk["mask"] & (gp == k)).sum())} for k in W.GROUPS}
    return T, paths_, pre


def run_scale(T: pd.DataFrame, paths_: dict, names: list[str], n225: set, sc: str, say) -> dict:
    cfg = SCALES[sc]
    x = prep_scale(T, names, n225, cfg["cluster"])
    w = S.windows(x)
    res = {"counts": counts_scale(x), "atlas": {}, "m_bounds": list(m_bounds(sc)), "scale": scale_factor(sc)}
    X = x[w["X"]]
    for wk, mm in w.items():
        xx = x[mm]
        res["atlas"][wk] = {"lifts": S.quintile_lifts(xx, X, S.FEATS), "patterns": S.pattern_lifts(xx),
                            "paths": S.mean_paths(xx, {tf: {o: v[mm] for o, v in P_.items()} for tf, P_ in paths_.items()},
                                                  {"RS": xx["RS"].to_numpy() > 0.5, "FS": xx["FS"].to_numpy() > 0.5, "ALL": np.ones(len(xx), bool)})}
    say(f"{sc} 图集完成")
    res["models"], scores, Dc = fit_scale(x, scale_factor(sc))
    say(f"{sc} 模型：" + "；".join(f"{k} AUC {v['auc']}（基础 {v['auc_base']}）→ {v['tier']}" for k, v in res["models"].items()))
    info_pp = S.SPREAD_PP * scale_factor(sc)
    gD = Dc["group"].to_numpy()
    res["groups"] = {k: cell_scaled(Dc, scores, gD == k, info_pp) for k in W.GROUPS}
    wC = w["C"]
    gx = x["group"].to_numpy()
    pmC = {tf: {o: v[wC] for o, v in P_.items()} for tf, P_ in paths_.items()}
    xc = x[wC].reset_index(drop=True)
    res["group_atlas"] = {k: W.group_atlas(xc, pmC, gx[wC] == k) for k in W.GROUPS}
    return res


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/turn_shape_mtf.py", "scripts/turn_shape_wide.py", "scripts/turn_shape_study.py",
                                     "scripts/allsec_data.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if not (a.counts or a.run):
        raise SystemExit("要 --counts 或 --run")
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    t0 = time.time()
    say = lambda s_: print(f"{s_}；{time.time() - t0:.0f}s", flush=True)     # noqa: E731
    import allsec_data as AS
    from qbreak.config import universe
    A = AS.load()
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    n225 = set(universe("JP", "broad"))
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    res: dict = {"git": git_info(), "scales": {}}
    for sc in SCALES:
        T, paths_, pre = build_scale(A, days, names, sc, a.run, say)
        if a.counts:
            x = prep_scale(T, names, n225, SCALES[sc]["cluster"])
            res["scales"][sc] = {"counts": counts_scale(x), "groups_pre": pre, "m_bounds": list(m_bounds(sc)), "scale": scale_factor(sc),
                                 "group_per_day_C": {k: round(float(x[(x["group"] == k) & S.windows(x)["C"]].groupby("date").size().mean()), 1)
                                                     if ((x["group"] == k) & S.windows(x)["C"]).any() else 0.0 for k in W.GROUPS}}
        else:
            res["scales"][sc] = run_scale(T, paths_, names, n225, sc, say) | {"groups_pre": pre}
        del T, paths_
        say(f"{sc} 完成")
    if a.counts:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    fw = out_dir / W.OUT_JSON
    if fw.exists():
        u2 = json.loads(fw.read_text(encoding="utf-8"))["universes"]["U2"]
        res["daily_ref"] = {k: u2[k] for k in ("counts", "models", "groups")}
    res["elapsed_s"] = round(time.time() - t0)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report(res)
    (out_dir / OUT_MD).write_text(md + "\n", encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md)
    return 0


def pp(v) -> str:
    return "—" if v is None else f"{v:+.2f}"


def report(res: dict) -> str:
    L = [f"# 起涨点 / 起跌点 × 图形：周线 / 月线尺度（git {res['git']['rev']}{'（脏）' if res['git'].get('dirty') else ''}；只运行一次）", ""]
    L.append("| 尺度 | 每个样本日 | 起涨 / 起跌点 | M 中位数 | 模型 | AUC（基础） | 新低 / 新高里 | 最像一组超额（区间） | 最不像 | 判定 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    d = res.get("daily_ref")
    if d:
        c = d["counts"]["C"]
        for mk, m in d["models"].items():
            L.append(f"| 日线（20 日；引用 turn_shape_wide U2） | {c['stocks_per_day']:,.0f} | {c['RS_pct']}% / {c['FS_pct']}% | {c['M_median_pct']}% | {'上涨' if mk == 'rise' else '下跌'} | "
                     f"{m['auc']}（{m['auc_base']}） | {m['auc_ext']} | {pp(m['deciles']['9']['R20x'])} pp（{m['top_ci_pp']}） | {pp(m['deciles']['0']['R20x'])} pp | {m['tier']} |")
    for sc, r in res["scales"].items():
        c = r["counts"]["C"]
        for mk, m in r["models"].items():
            L.append(f"| {NAMES[sc]}（{SCALES[sc]['h_ret']} 日） | {c['per_day']:,.0f} | {c['RS_pct']}% / {c['FS_pct']}% | {c['M_median_pct']}% | {'上涨' if mk == 'rise' else '下跌'} | "
                     f"{m['auc']}（{m['auc_base']}） | {m['auc_ext']} | {pp(m['deciles'][S.N_DEC - 1]['R20x'])} pp（{m['top_ci_pp']}） | {pp(m['deciles'][0]['R20x'])} pp | "
                     + "、".join(f"{g}{'✓' if ok else '✗'}" for g, ok in m["gates"].items()) + f" → {m['tier']} |")
    L.append("")
    for sc, r in res["scales"].items():
        L.append(f"## {NAMES[sc]}：分组（确认期；组内超额减本组同一天平均；「有信息」门槛 {S.SPREAD_PP * r['scale']:.2f} pp）")
        L.append("")
        L.append("| 组 | 行数 | 每天 | 起涨 / 起跌点 | 上涨：AUC / 新低里 / 差（最像、区间） | 下跌：AUC / 新高里 / 差（最像、区间） | 有信息 |")
        L.append("|---|---|---|---|---|---|---|")
        for k, nm in W.GROUPS.items():
            g = r["groups"].get(k, {})
            if not g.get("rows"):
                L.append(f"| {k} {nm} | 0 | | | | | |")
                continue
            cells = []
            for mk in S.MODELS:
                x = g[mk]
                s = f"{x['auc']} / {x['auc_ext']}"
                if "spread_pp" in x:
                    s += f" / {x['spread_pp']:+.2f} pp（{x['top_pp']:+.2f}、{x['top_ci_pp']}）"
                cells.append(s)
            info = "、".join(f"{'上涨' if mk == 'rise' else '下跌'}{'✓' if g[mk].get('info') else '✗'}" for mk in S.MODELS) if g["bins"] else "（行太少，只报 AUC）"
            L.append(f"| {k} {nm} | {g['rows']:,} | {g['per_day']} | {g['RS_pct']}% / {g['FS_pct']}% | {cells[0]} | {cells[1]} | {info} |")
        L.append("")
        for tf, nm in (("d", "日线"), ("w", "周线"), ("m", "月线")):
            p = r["atlas"]["C"]["paths"][tf]
            offs = sorted(p["ALL"])
            pick = [o for o in offs if o in (-60, -26, -24, -20, -13, -12, -10, -8, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 8, 10, 20, 40)]
            f = lambda lab: "、".join(f"{o:+d} {p[lab][o] - p['ALL'][o]:+.1f}" for o in pick if p[lab][o] is not None and p['ALL'][o] is not None)  # noqa: E731
            L.append(f"- {NAMES[sc]} 起点的{nm}平均形状（确认期，减全部样本）起涨点：{f('RS')}；起跌点：{f('FS')}")
        L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。读法与档位见脚本开头（登记时写定）。只有汇总统计，没有个股。非投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
