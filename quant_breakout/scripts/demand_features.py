"""demand_features.py — 「需給・回購・決算日程・現金利益 × 全市場 W2 突破」研究的特征层（只算「信号日已知」的特征与进场前分布，不算任何买入后的收益）。

对 var/cache/jquants/allstock_train.pkl 里的每个突破信号（ticker × sig_date；P = w5v ≥ 1.0 或缺值）算：
  信用残高（jq_extra_data.margin_weekly；可用日 avail ≤ d，且 d − avail ≤ 15 个交易日）：L_now / L_4（再往前第 4 条、申込日相隔 26〜36 天）→ dL_pct、dL_std_pct、dL_neg_pct、
    L_4、iss_type、split（[L_4 申込日, d] 内面板 R 相邻跳变 > 1%）；
  自社株（jq_extra_data.fins_fs_rows + buyback_b）：最近一份 FS 行（DiscDate ∈ [d − 140, d)）的 b、fs_age、tr_chg、两份之间的 R 跳变 → split_fs；
  日程（var/cache/jquants/out/fins_events_full.pkl：全部开示含订正）：since = d 离最近一次开示的交易日数；to_exp = d 离「预计下一次短信」的交易日数
    （预计 = 所有 DiscDate < d 的 FS 行 + 364 天里第一个 > d；没有 → 缺值）；
  应计（FY 行、DiscDate ∈ [d − 400, d)）：accrual = (NP − CFO) ÷ TA、cfo_pos；fin = 时点 33 业种 ∈ 金融四业种；
  分段：规模带 band（0 非 TOPIX / 1 TOPIX Small / 2 TOPIX 500，严格早于 d 的快照）、mkt（P / S / G）、u1 时点 TOPIX 500、short_flag、frgn4（海外 4 周净买 > 0）、
    lot_yen、va20、pbr、roe_eqar、net_cash、disc7、year、lturn 三分位（全池）、r20 五分位（全池）、vr1（信号表）。
可用日规则：avail ≤ d（公布后第一个交易日；决算短信 = DiscDate 严格早于 d）；缺值 → NaN（候选一律「不保留」，由 demand_study 处理）。
输出：var/cache/jquants/out/demand_features.pkl（不入库）；--counts 打印进场前分布（保留比例、资格率、缺值率、规模构成、ΔL% 与 18 特征的秩相关）。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import jquants as JQ                                              # noqa: E402

MARGIN_MAX_AGE, MARGIN_GAP_LO, MARGIN_GAP_HI, MARGIN_MIN_L4 = 15, 26, 36, 10_000
BB_MAX_AGE_DAYS, ACC_MAX_AGE_DAYS, EXP_DAYS = 140, 400, 364
FIN_S33 = {"銀行業", "証券、商品先物取引業", "保険業", "その他金融業"}
OUT_PKL = "demand_features.pkl"
FEATS18 = ["w5v", "vr1", "vexp", "dist", "rng", "brk", "r20", "r60", "r120", "hi52", "atrp", "vol60", "clv", "ush", "gap", "lturn", "mkt200", "mkt20"]


def out_dir() -> Path:
    d = JQ.cache_dir() / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def signals() -> pd.DataFrame:
    fp = JQ.cache_dir() / "allstock_train.pkl"
    T = pd.read_pickle(fp)
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    T["P"] = (T["w5v"] >= 1.0) | ~np.isfinite(T["w5v"])
    return T.drop_duplicates(subset=["ticker", "sig_date"]).sort_values(["ticker", "sig_date"]).reset_index(drop=True)


def r_jump_flags(A: dict) -> np.ndarray:
    """面板 R（未调整 ÷ 复权）相邻日 |变化| > 1% → 那天 True（拆股 / 併合）。"""
    R = A["R"].astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        j = np.abs(R[1:] / R[:-1] - 1) > 0.01
    out = np.zeros(R.shape, bool)
    out[1:] = np.where(np.isfinite(R[1:]) & np.isfinite(R[:-1]), j, False)
    return out


def _cum_jumps(J: np.ndarray) -> np.ndarray:
    return np.cumsum(J, axis=0)


def margin_features(T: pd.DataFrame, M: pd.DataFrame, days: pd.DatetimeIndex, pos: pd.Series, cumj: np.ndarray, col: dict) -> pd.DataFrame:
    """每个信号的信用残高特征（按票分组、按可用日 searchsorted）。"""
    out = {k: np.full(len(T), np.nan) for k in ("dL_pct", "dL_std_pct", "dL_neg_pct", "L_4", "L_now", "margin_age", "margin_gap")}
    iss = np.array([""] * len(T), dtype=object)
    split = np.zeros(len(T), bool)
    has = np.zeros(len(T), bool)
    groups = {t: g for t, g in M.groupby("ticker", sort=False)}
    for t, g in T.groupby("ticker", sort=False):
        m = groups.get(t)
        if m is None:
            continue
        m = m.sort_values("date")
        av = m["avail"].to_numpy()
        dt_ = m["date"].to_numpy()
        L = m["long_vol"].to_numpy(float); Ls = m["long_std"].to_numpy(float); Ln = m["long_neg"].to_numpy(float)
        it = m["iss_type"].to_numpy()
        j = col.get(t)
        for i, d in zip(g.index, g["sig_date"].to_numpy()):
            k = np.searchsorted(av, d, side="right") - 1
            if k < 0:
                continue
            has[i] = True
            kd = pos.get(pd.Timestamp(d), None)
            ka = pos.get(pd.Timestamp(av[k]), None)
            if kd is None or ka is None or kd - ka > MARGIN_MAX_AGE:
                out["margin_age"][i] = np.nan if kd is None or ka is None else kd - ka
                continue
            out["margin_age"][i] = kd - ka
            out["L_now"][i] = L[k]
            iss[i] = it[k]
            if k - 4 < 0:
                continue
            gap = (dt_[k] - dt_[k - 4]).astype("timedelta64[D]").astype(int)
            out["margin_gap"][i] = gap
            if not (MARGIN_GAP_LO <= gap <= MARGIN_GAP_HI):
                continue
            out["L_4"][i] = L[k - 4]
            if L[k - 4] > 0:
                out["dL_pct"][i] = (L[k] - L[k - 4]) / L[k - 4] * 100
            if Ls[k - 4] > 0:
                out["dL_std_pct"][i] = (Ls[k] - Ls[k - 4]) / Ls[k - 4] * 100
            if Ln[k - 4] > 0:
                out["dL_neg_pct"][i] = (Ln[k] - Ln[k - 4]) / Ln[k - 4] * 100
            if j is not None:
                k4 = pos.get(pd.Timestamp(dt_[k - 4]), None)
                if k4 is None:
                    k4 = int(days.searchsorted(pd.Timestamp(dt_[k - 4])))
                split[i] = (cumj[kd, j] - cumj[max(k4, 0), j]) > 0
    F = pd.DataFrame(out, index=T.index)
    F["iss_type"] = iss
    F["split"] = split
    F["margin_has"] = has
    return F


def fins_features(T: pd.DataFrame, BB: pd.DataFrame, EV: pd.DataFrame, days: pd.DatetimeIndex, pos: pd.Series, cumj: np.ndarray, col: dict) -> pd.DataFrame:
    """自社株 b / 日程 since / to_exp / 应计 / 分段用的 PBR、ROE、净现金。"""
    n = len(T)
    o = {k: np.full(n, np.nan) for k in ("b", "fs_age", "tr_chg", "since", "to_exp", "accrual", "cfo", "acc_age", "pbr_sheq", "roe", "eqar", "cash", "ta", "eq", "disc7", "last_rev")}
    split_fs = np.zeros(n, bool)
    bbg = {t: g.sort_values("date") for t, g in BB.groupby("ticker", sort=False)}
    EVs = EV.sort_values(["ticker", "date"], kind="mergesort")
    evg = {t: g["date"].to_numpy() for t, g in EVs.groupby("ticker", sort=False)}
    evr = {t: g["rev"].to_numpy() for t, g in EVs.groupby("ticker", sort=False)}
    for t, g in T.groupby("ticker", sort=False):
        b = bbg.get(t)
        ev = evg.get(t)
        j = col.get(t)
        for i, d in zip(g.index, g["sig_date"].to_numpy()):
            d = pd.Timestamp(d)
            kd = pos.get(d, None)
            if ev is not None and len(ev):
                k = np.searchsorted(ev, np.datetime64(d), side="left") - 1                          # 最近一次开示 < d
                if k >= 0:
                    kp = pos.get(pd.Timestamp(ev[k]), None)
                    if kp is None:
                        kp = int(days.searchsorted(pd.Timestamp(ev[k])))
                    o["since"][i] = (kd - kp) if kd is not None else np.nan
                    o["disc7"][i] = float((d - pd.Timestamp(ev[k])).days <= 7)
                    o["last_rev"][i] = float(evr[t][k])                                                  # 最近一次开示是予想修正（1）还是短信（0）
            if b is None or not len(b):
                continue
            bd = b["date"].to_numpy()
            k = np.searchsorted(bd, np.datetime64(d), side="left") - 1                              # 最近一份 FS 行 < d
            if k < 0:
                continue
            row = b.iloc[k]
            age = (d - pd.Timestamp(bd[k])).days
            # 预计下一次短信：所有 < d 的 FS 行 + 364 天里第一个 > d
            exp_ = bd[:k + 1] + np.timedelta64(EXP_DAYS, "D")
            cand = exp_[exp_ > np.datetime64(d)]
            if len(cand):
                e0 = pd.Timestamp(cand.min())
                ke = int(days.searchsorted(e0))
                if kd is not None and ke < len(days):
                    o["to_exp"][i] = ke - kd
            if age <= BB_MAX_AGE_DAYS:
                o["b"][i] = row["b"] * 100 if np.isfinite(row["b"]) else np.nan
                o["fs_age"][i] = age
                o["tr_chg"][i] = row["tr_chg"]
                if j is not None and pd.notna(row["prev_date"]) and kd is not None:
                    kp = int(days.searchsorted(pd.Timestamp(row["prev_date"])))
                    split_fs[i] = (cumj[kd, j] - cumj[max(kp, 0), j]) > 0
            o["pbr_sheq"][i] = row["ShEq"]
            o["cash"][i], o["ta"][i], o["eq"][i] = row["CashEq"], row["TA"], row["Eq"]
            # 应计：最近一条 FY 行（< d、≤ 400 天）
            fy = b.iloc[:k + 1]
            fy = fy[fy["per"] == "FY"]
            if len(fy):
                r = fy.iloc[-1]
                age_fy = (d - pd.Timestamp(r["date"])).days
                if age_fy <= ACC_MAX_AGE_DAYS and np.isfinite(r["NP"]) and np.isfinite(r["CFO"]) and np.isfinite(r["TA"]) and r["TA"] > 0:
                    o["accrual"][i] = (r["NP"] - r["CFO"]) / r["TA"]
                    o["cfo"][i] = r["CFO"]
                    o["acc_age"][i] = age_fy
                o["roe"][i], o["eqar"][i] = r["ROE"], r["EqAR"]
    F = pd.DataFrame(o, index=T.index)
    F["split_fs"] = split_fs
    return F


def build(say=print) -> pd.DataFrame:
    import allstock_data as AD
    import jq_extra_data as X
    import policy_event_data as PD
    t0 = time.time()
    T = signals()
    A = AD.load()
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    pos = pd.Series(np.arange(len(days)), index=days)
    col = {t: j for j, t in enumerate(names)}
    cumj = _cum_jumps(r_jump_flags(A))
    say(f"信号 {len(T)}（P {int(T['P'].sum())}）；面板 {len(days)} 天 × {len(names)} 只；{time.time() - t0:.0f}s")
    M = X.margin_weekly(days)
    say(f"信用残高 {len(M)} 行；{time.time() - t0:.0f}s")
    FM = margin_features(T, M, days, pos, cumj, col)
    say(f"信用特征完成；{time.time() - t0:.0f}s")
    fs = X.fins_fs_rows()
    BB = X.buyback_b(fs)
    EV = pd.read_pickle(JQ.cache_dir() / "out" / "fins_events_full.pkl")[["ticker", "date", "doc"]]
    EV["date"] = pd.to_datetime(EV["date"])
    EV["rev"] = (EV["doc"].astype(str) == "EarnForecastRevision").astype(int)
    FF = fins_features(T, BB, EV, days, pos, cumj, col)
    say(f"決算特征完成（FS 行 {len(fs)}）；{time.time() - t0:.0f}s")
    # 分段变量
    snaps = X.master_snapshots()
    scale = X.scale_matrix(days, names, snaps)
    growth = X.segment_mask(days, names, snaps, X.GROWTH_MKT)
    prime = X.segment_mask(days, names, snaps, X.PRIME_MKT)
    maps = PD.s33_map_pit(snaps)
    sd = sorted(maps)
    ki = np.array([pos.get(d, -1) for d in T["sig_date"]])
    ji = np.array([col.get(t, -1) for t in T["ticker"]])
    ok = (ki >= 0) & (ji >= 0)
    sc = np.where(ok, scale[ki.clip(0), ji.clip(0)], -1)
    band = np.where(sc <= 0, 0, np.where(sc <= 2, 1, 2))
    band = np.where(ok, band, -1)
    mkt = np.where(ok & growth[ki.clip(0), ji.clip(0)], "G", np.where(ok & prime[ki.clip(0), ji.clip(0)], "P", "S"))
    fin = np.zeros(len(T), bool)
    for i, (t, d) in enumerate(zip(T["ticker"], T["sig_date"])):
        prev = [s for s in sd if s < d]
        mp = maps[prev[-1]] if prev else (maps[sd[0]] if sd else {})
        fin[i] = mp.get(t, "") in FIN_S33
    C, R, MC, VA = A["C"], A["R"], A["MC"], A["VA"]
    lot = np.where(ok, C[ki.clip(0), ji.clip(0)] * R[ki.clip(0), ji.clip(0)] * 100, np.nan)
    va20 = np.full(len(T), np.nan)
    for n_, (k, j) in enumerate(zip(ki, ji)):
        if k >= 19 and j >= 0:
            va20[n_] = np.nanmean(VA[k - 19:k + 1, j])
    mc = np.where(ok, MC[ki.clip(0), ji.clip(0)], np.nan)
    # 空売り / 海外 / U1
    S = X.short_positions(days)
    sflag = np.zeros(len(T), bool)
    sg = {t: g.sort_values("avail") for t, g in S.groupby("ticker", sort=False)}
    for t, g in T.groupby("ticker", sort=False):
        s_ = sg.get(t)
        if s_ is None:
            continue
        av = s_["avail"].to_numpy(); tot = s_["total"].to_numpy(float)
        for i, d in zip(g.index, g["sig_date"].to_numpy()):
            k = np.searchsorted(av, d, side="right") - 1
            if k >= 0 and (pd.Timestamp(d) - pd.Timestamp(av[k])).days <= 365:
                sflag[i] = tot[k] > 0
    try:
        FL = X.investor_flows(days)
        fr = X.asof_series(FL.assign(f4=FL["ratio_Frgn"].rolling(4, min_periods=4).sum()), days, "f4")
        frgn4 = np.where(ok, fr.to_numpy()[ki.clip(0)], np.nan)
    except Exception:                                                        # noqa: BLE001
        frgn4 = np.full(len(T), np.nan)
    u1 = np.full(len(T), np.nan)
    try:
        import candle_data as CD
        D = CD.load()
        cpos = pd.Series(np.arange(len(D["days"])), index=pd.DatetimeIndex(D["days"]))
        ccol = {t: j for j, t in enumerate(D["names"])}
        mem = D["mem"]["U1"]
        for i, (t, d) in enumerate(zip(T["ticker"], T["sig_date"])):
            j, k = ccol.get(t), cpos.get(d)
            if j is not None and k is not None:
                u1[i] = float(mem[int(k), j])
    except Exception:                                                        # noqa: BLE001
        pass
    F = pd.concat([T[["ticker", "sig_date", "P", "net", "w5v", "vr1", "lturn", "r20"] + [c for c in FEATS18 if c not in ("w5v", "vr1", "lturn", "r20")]], FM, FF], axis=1)
    F["band"] = band; F["mkt"] = mkt; F["fin"] = fin; F["lot_yen"] = lot; F["va20"] = va20; F["mc"] = mc
    F["short_flag"] = sflag; F["frgn4"] = frgn4; F["u1"] = u1
    F["year"] = F["sig_date"].dt.year
    with np.errstate(invalid="ignore", divide="ignore"):
        F["pbr"] = F["mc"] * 1e6 / F["pbr_sheq"].replace(0, np.nan)
    F["roe_eqar"] = (F["roe"] >= 0.08) & (F["eqar"] >= 0.40)
    F["net_cash"] = F["cash"] >= (F["ta"] - F["eq"])
    P = F["P"].to_numpy(bool)
    F["lturn_ter"] = np.nan; F["r20_q"] = np.nan
    F.loc[P, "lturn_ter"] = pd.qcut(F.loc[P, "lturn"].rank(method="first"), 3, labels=False)
    F.loc[P, "r20_q"] = pd.qcut(F.loc[P, "r20"].rank(method="first"), 5, labels=False)
    F["stratum"] = F["year"].astype(str) + "|" + F["band"].astype(str) + "|" + F["lturn_ter"].fillna(-1).astype(int).astype(str)
    F["week"] = F["sig_date"].dt.to_period("W-FRI").astype(str)
    say(f"特征表 {F.shape}；{time.time() - t0:.0f}s")
    return F


# ───────────────────────── 候选（与 demand_study 共用；阈值写死） ─────────────────────────
DL_MIN, B_MIN, B_MAX, SINCE_MIN, TOEXP_LO, TOEXP_HI, ACC_MAX, VR_MIN = -10.0, 0.25, 20.0, 10, 10, 40, -0.05, 2.0


def eligible(F: pd.DataFrame, cid: str) -> np.ndarray:
    """资格池：特征可算且不缺值（缺值的信号既不算候选也不算剔除组）。"""
    P = F["P"].to_numpy(bool)
    if cid in ("N1", "N5"):
        e = P & np.isfinite(F["dL_pct"].to_numpy(float)) & np.isfinite(F["L_4"].to_numpy(float)) & (F["L_4"].to_numpy(float) >= MARGIN_MIN_L4) \
            & ~F["split"].to_numpy(bool) & F["iss_type"].isin(["1", "2"]).to_numpy()
        return e & np.isfinite(F["vr1"].to_numpy(float)) if cid == "N5" else e
    if cid == "N2":
        return P & np.isfinite(F["b"].to_numpy(float)) & ~F["split_fs"].to_numpy(bool)
    if cid == "N3":
        return P & np.isfinite(F["since"].to_numpy(float)) & np.isfinite(F["to_exp"].to_numpy(float))
    if cid == "N4":
        return P & np.isfinite(F["accrual"].to_numpy(float)) & np.isfinite(F["cfo"].to_numpy(float)) & ~F["fin"].to_numpy(bool)
    raise KeyError(cid)


def keep(F: pd.DataFrame, cid: str) -> np.ndarray:
    """候选保留（资格池内）。"""
    e = eligible(F, cid)
    if cid == "N1":
        return e & (F["dL_pct"].to_numpy(float) <= DL_MIN)
    if cid == "N5":
        return e & (F["dL_pct"].to_numpy(float) <= DL_MIN) & (F["vr1"].to_numpy(float) >= VR_MIN)
    if cid == "N2":
        b = F["b"].to_numpy(float)
        return e & (b >= B_MIN) & (b <= B_MAX)
    if cid == "N3":
        return e & (F["since"].to_numpy(float) >= SINCE_MIN) & (F["to_exp"].to_numpy(float) >= TOEXP_LO) & (F["to_exp"].to_numpy(float) <= TOEXP_HI)
    if cid == "N4":
        return e & (F["accrual"].to_numpy(float) <= ACC_MAX) & (F["cfo"].to_numpy(float) > 0)
    raise KeyError(cid)


def counts(F: pd.DataFrame, wins: dict) -> dict:
    """进场前分布：各候选在各窗口的资格率 / 保留率（全池与资格池）、规模带构成、ΔL% 与 18 特征的秩相关。"""
    out = {}
    for w, (a, b) in wins.items():
        m = F["P"].to_numpy(bool) & (F["sig_date"] >= pd.Timestamp(a)).to_numpy() & (F["sig_date"] <= pd.Timestamp(b)).to_numpy()
        row = {"P": int(m.sum())}
        for cid in ("N1", "N2", "N3", "N4", "N5"):
            e, k = eligible(F, cid) & m, keep(F, cid) & m
            row[cid] = {"eligible": int(e.sum()), "eligible_pct": round(float(e.sum() / max(m.sum(), 1) * 100), 1), "keep": int(k.sum()),
                        "keep_pct_pool": round(float(k.sum() / max(m.sum(), 1) * 100), 1), "keep_pct_elig": round(float(k.sum() / max(e.sum(), 1) * 100), 1),
                        "by_band": {int(bd): {"eligible": int((e & (F["band"] == bd)).sum()), "keep": int((k & (F["band"] == bd)).sum()), "pool": int((m & (F["band"] == bd)).sum())}
                                    for bd in (0, 1, 2)}}
        out[w] = row
    P = F[F["P"]]
    x = P["dL_pct"]
    out["rank_corr_dL"] = {}
    for c in FEATS18:
        if c in P.columns:
            m = x.notna() & P[c].notna()
            if m.sum() > 100:
                out["rank_corr_dL"][c] = round(float(x[m].rank().corr(P.loc[m, c].rank())), 3)     # 秩相关（不依赖 scipy）
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args(argv)
    fp = out_dir() / OUT_PKL
    if fp.exists() and not a.rebuild:
        F = pd.read_pickle(fp)
    else:
        F = build()
        F.to_pickle(fp)
        print(f"→ {fp}")
    if a.counts:
        import json
        wins = {"X": ("2017-01-04", "2021-12-30"), "C": ("2022-01-04", "2026-06-25")}
        print(json.dumps(counts(F, wins), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
