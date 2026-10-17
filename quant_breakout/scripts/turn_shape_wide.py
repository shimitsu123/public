"""turn_shape_wide.py — 「起涨点 / 起跌点 × 日 / 周 / 月线图形」放宽限制版：去掉流动性下限、新股只要满 60 根，再加 ETF / REIT 等全部品种
（2026-10-05 登记；先提交后运行、只运行一次、结果出来不改规则）。

用户（2026-10-05）：「上述分析是所有类型的股票么，什么限制都不要加的分析结果」→ 选 ③「在 ② 之外再加 ETF / REIT 等 进行研究图形」。
来由：turn_shape_study（登记 d915a9e）只用了东证一般市场的内国普通股，并去掉了 20 日平均売買代金 < ¥1,000 万（平均每天约 892 只、24%）
  与有效日线不满 250 根（约 103 只、3%）的；ETF / REIT / 外国株 / TOKYO PRO MARKET 等都不在内。
  这一轮回答：去掉这些限制之后，「形状看得出、事前用不了」变不变；各品种的形状有什么不同。

数据：scripts/allsec_data.py（J-Quants 东证全部上市品种，2016-09-01〜2026-09-25 = 与原研究同一截止日；cat = 严格早于当天的月末上市一览里的分类）。

三个样本（样本日、起涨 / 起跌点的标注、46 个特征、经典形态、平均形状、模型、判定都与 turn_shape_study 完全相同 —— 直接调用它的函数，只换「哪些行进样本」）：
  U0 原样（对照）：内国普通株（一般市场）∧ 20 日平均売買代金 ≥ ¥1,000 万 ∧ 有效日线 ≥ 250 根（= turn_shape_study.sample_mask，listed = cat 1）。
     用来确认新面板逐行复现原研究（行数、AUC、十组）；不一致 → 报差异，照样继续（不改规则）。
  U1（= ②）：内国普通株（一般市场），不设流动性下限，有效日线 ≥ 60 根。
  U2（= ③）：U1 + 其他全部品种（TOKYO PRO MARKET / 优先株 / 新株予约权、REIT / インフラファンド、国内 ETF、外国 ETF / ETN 等、外国株、出資証券），有效日线 ≥ 60 根。
  共同：样本日当天有收盘价（有成交）。
  U1 / U2 的 60 日波动 σ（定义「涨 / 跌多少才算」的 M，也是特征 sig60）改用向前填补的收盘价算（没有成交的日子收益 = 0，下一次成交那天算累计变化）：
     原定义要 60 天连续有成交，登记前数过 —— 成交少的票 37%、ETF / ETN 25% 的行会因此算不出、没法标注（也是一种限制）；
     每天都有成交的票两种算法完全相同。仍算不出 M 的行（有效日线不满约 60 根）不进样本，按组报个数。U0 保持原定义（逐行复现原研究）。

模型：与原研究相同（L2 逻辑回归、2017-10〜2021-12 学、2022-01〜 检验、每天分十组、20 日超额 = 下一个交易日开盘买、20 日后收盘，减同一天本样本全部行的平均）。
  U1 / U2 只多两条（U0 不用）：① log 时价总额缺（ETF 等没有时价总额）→ 用同一天本样本的中位数补；
  ② 学习只用特征齐全的行（同原研究）；检验时缺的特征在标准化之后补 0（= 学习期平均），所有行都打分；另报「只算特征齐全的行」。
  判定 G1〜G6 与档位（没有用 / 有信息 / 图形有用）原样（turn_shape_study.judge）。

分组（U2 内，确认期；分数用 U2 模型）：
  A 原样本（= U0 的行）；B 内国普通株·成交少（20 日平均売買代金 < ¥1,000 万、≥ 250 根）；C 内国普通株·上市未满约 1 年（60〜249 根）；
  D ETF / ETN（国内 ETF + 外国 ETF / ETN 等）；E REIT / インフラファンド；F 其他（PRO 市场 / 优先株 / 新株予约权 / 外国株 / 出資証券）。
  每组报：起涨 / 起跌点比例、日 / 周 / 月线平均形状（减本组同一天平均）、经典形态倍数前 8（≥ 200 次）、组内 AUC、
  「近 10 日新低 / 新高」里的 AUC（turn_shape_posthoc 的读法）、组内每天分组（平均每天 ≥ 50 行 → 十组；20〜49 → 五组；更少 → 只报 AUC）
  之后 20 日超额（减本组同一天平均）最高 / 最低一组与最高一组的按月聚类 95% 区间。
  内国普通株（U1）另按 20 日平均売買代金分三档（< ¥100 万、¥100〜1,000 万、≥ ¥1,000 万）报同样的组内数字。

读法（事先写定）：
  - 样本：U1 / U2 的 G1〜G6 全过 → 「放宽后有用」；但若只在 B / C / F 或 < ¥1,000 万档成立（成交少、新股、个人难买）→ 记为「纸面上有、交易不了」，只记录。
  - 组：s × (最高 − 最低) ≥ 1 pp 且最高一组区间不含 0（方向按 s：上涨模型要 > 0、下跌模型要 < 0）→ 该组「有信息」；否则「没有」。
  - 结论上限 = 记录 + 提议（任何改动要用户确认、另外登记）；不改模拟盘、执行器、例行任务。
事前预期：形状各组相同（定义带来的：最后约 2 周急跌 / 急涨）；ETF / REIT 波动小、M 多在下限 10% → 起涨 / 起跌点少、集中在全市场急跌前后；
  成交少的票买卖价来回跳 → 纸面上「跌多了就反弹」较强，组内差 ≥ 1 pp 的可能约 40%，但交易不了；U1 / U2 全过 G1〜G6 的可能约 15%，
  其中可交易部分（A、D）成立的可能约 5%。非投资建议。
用法：python scripts/turn_shape_wide.py --counts（登记前只数个数）；python scripts/turn_shape_wide.py --run（只运行一次）
"""
from __future__ import annotations

import argparse
import json
import logging
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
import turn_shape_posthoc as PH                                               # noqa: E402

HIST_WIDE = 60
VA_BUCKETS = (1e6, 1e7)
BIN_RULE = ((50, 10), (20, 5))                                                # 平均每天 ≥ 50 行 → 十组；20〜49 → 五组；更少 → 只报 AUC
INFO_PP = 1.0
GROUPS = {"A": "原样本（内国普通株、≥ ¥1,000 万、≥ 250 根）", "B": "内国普通株·成交少（< ¥1,000 万）", "C": "内国普通株·上市未满约 1 年",
          "D": "ETF / ETN", "E": "REIT / インフラファンド", "F": "其他（PRO 市场 / 优先株 / 外国株 / 出資証券）"}
BUCKETS = {"L1": "< ¥100 万 / 天", "L2": "¥100〜1,000 万 / 天", "L3": "≥ ¥1,000 万 / 天"}
UNIVERSES = {"U0": "原样（对照）", "U1": "② 内国普通株、不设流动性下限、≥ 60 根", "U2": "③ 全部品种、≥ 60 根"}
OUT_MD, OUT_JSON = "turn_shape_wide.md", "turn_shape_wide.json"
KEEP_DROP = ("R20x", "R40x", "mc_rank")


# ───────────────────────── 样本 ─────────────────────────
def day_grid(days: pd.DatetimeIndex) -> np.ndarray:
    """与 turn_shape_study.sample_mask 同一个样本日网格（START 起每 STEP 个交易日；最后 FWD_NEED 天不要）。"""
    T = len(days)
    k0 = int(np.searchsorted(days.to_numpy(dtype="datetime64[ns]"), np.datetime64(pd.Timestamp(S.START))))
    on = np.zeros(T, bool)
    on[k0::S.STEP] = True
    on[max(T - S.FWD_NEED, 0):] = False
    return on


def panel_masks(A: dict, days: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    """union = 进样本表的行（U0 ∪ U1 ∪ U2 的上限）；u0 = 原研究的 sample_mask（listed = cat 1）。"""
    C = A["C"]
    hist = np.cumsum(np.isfinite(C), axis=0)
    union = day_grid(days)[:, None] & (A["cat"] > 0) & np.isfinite(C) & (hist >= HIST_WIDE)
    u0 = S.sample_mask({**A, "listed": A["cat"] == 1}, days)
    return {"union": union | u0, "u0": u0, "hist": hist, "va20": S.rmean(A["VA"].astype(float), S.VA_N)}


LABEL_COLS = ("sig60", "M", "RS", "FS", "U", "D")


def labels_ffill(P: dict) -> dict[str, np.ndarray]:
    """与 turn_shape_study.labels 逐行相同，只有一处不同：σ 用向前填补的收盘价的对数收益（没有成交的日子 = 0）。每天都有成交的票结果完全相同。"""
    O, C = P["O"], P["C"]
    Cf = S.ffill(C)
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.diff(np.log(Cf), axis=0, prepend=np.nan)                     # ← 唯一的不同（原来是 np.log(C)）
    sig = S.rstd(lr, S.SIG_N)
    M = np.clip(S.M_K * sig * np.sqrt(S.H_LAB), S.M_LO, S.M_HI)
    w = 2 * S.EXT_WIN + 1
    lo = pd.DataFrame(C).rolling(w, center=True, min_periods=S.EXT_WIN + 5).min().to_numpy()
    hi = pd.DataFrame(C).rolling(w, center=True, min_periods=S.EXT_WIN + 5).max().to_numpy()
    fin = np.isfinite(C) & np.isfinite(M)
    with np.errstate(invalid="ignore"):
        is_lo, is_hi = fin & (C <= lo), fin & (C >= hi)
    u1, d1 = S.first_pass(Cf, C, 1 + M, 1 - M / 2)
    RS = is_lo & np.isfinite(u1) & (u1 < d1)
    u2, d2 = S.first_pass(Cf, C, 1 + M / 2, 1 - M)
    FS = is_hi & np.isfinite(d2) & (d2 < u2)
    del u1, d1, u2, d2
    O1 = S.fwd(O, 1)
    u3, d3 = S.first_pass(Cf, O1, 1 + M, 1 - M / 2)
    U = np.isfinite(O1) & np.isfinite(u3) & (u3 < d3)
    u4, d4 = S.first_pass(Cf, O1, 1 + M / 2, 1 - M)
    D = np.isfinite(O1) & np.isfinite(d4) & (d4 < u4)
    return {"sig60": sig, "M": M, "RS": RS, "FS": FS, "U": U, "D": D}


def swap_labels(x: pd.DataFrame) -> pd.DataFrame:
    """U1 / U2：标注与 sig60 换成向前填补口径（*_f 列）。"""
    x = x.copy()
    for k in LABEL_COLS:
        x[k] = x[k + "_f"]
    return x


def groups_of(x: pd.DataFrame) -> np.ndarray:
    c, h, va, u0 = x["cat"].to_numpy(), x["hist"].to_numpy(), x["va20"].to_numpy(), x["u0"].to_numpy(bool)
    g = np.full(len(x), "F", dtype=object)
    g[np.isin(c, (4, 5))] = "D"
    g[c == 3] = "E"
    s1 = c == 1
    with np.errstate(invalid="ignore"):
        g[s1 & (h < S.HIST_MIN)] = "C"
        g[s1 & (h >= S.HIST_MIN) & ~(va >= S.VA_MIN)] = "B"
    g[s1 & u0] = "A"
    return g


def buckets_of(x: pd.DataFrame) -> np.ndarray:
    va = x["va20"].to_numpy(float)
    b = np.full(len(x), "L1", dtype=object)
    with np.errstate(invalid="ignore"):
        b[va >= VA_BUCKETS[0]] = "L2"
        b[va >= VA_BUCKETS[1]] = "L3"
    return b


def universe_flags(T: pd.DataFrame) -> dict[str, np.ndarray]:
    fm = np.isfinite(T["M_f"].to_numpy(float))
    c = T["cat"].to_numpy()
    return {"U0": T["u0"].to_numpy(bool), "U1": (c == 1) & fm, "U2": (c > 0) & fm}


# ───────────────────────── 每个样本的计算 ─────────────────────────
def prep(T: pd.DataFrame, m: np.ndarray, names: list[str], n225: set, ffill_sig: bool) -> pd.DataFrame:
    """取样本的行；U1 / U2 换成向前填补口径的标注；超额与时价总额排名按本样本重算（log 时价总额的补值只在模型里做，图集用原值）。"""
    x = T.loc[m, [c for c in T.columns if c not in KEEP_DROP]].reset_index(drop=True)
    if ffill_sig:
        for k in LABEL_COLS:
            x[k] = x[k + "_f"]
    for h in S.H_RET:
        r = x[f"R{h}"]
        x[f"R{h}x"] = (r - r.groupby(x["date"]).transform("mean")).astype(np.float32)
    x["mc_rank"] = x.groupby("date")["lmc"].rank(ascending=False, method="first").astype(np.float32)
    x["n225"] = np.isin(np.array(names, dtype=object)[x["j"].to_numpy()], list(n225))
    x["month"] = x["date"].dt.to_period("M").astype(str)
    return x


def counts_u(x: pd.DataFrame) -> dict:
    w = S.windows(x)
    out = {"rows": int(len(x)), "days": int(x["date"].nunique()), "first": str(x["date"].min().date()), "last": str(x["date"].max().date())}
    for k, m in w.items():
        xx = x[m]
        out[k] = {"rows": int(len(xx)), "days": int(xx["date"].nunique()), "stocks_per_day": round(float(xx.groupby("date").size().mean()), 1),
                  "RS_pct": round(float(xx["RS"].mean()) * 100, 2), "FS_pct": round(float(xx["FS"].mean()) * 100, 2),
                  "U_pct": round(float(xx["U"].mean()) * 100, 2), "D_pct": round(float(xx["D"].mean()) * 100, 2),
                  "M_median_pct": round(float(np.nanmedian(xx["M"])) * 100, 1),
                  "complete_rows_pct": round(float(xx[S.FEATS].notna().all(axis=1).mean()) * 100, 1)}
    return out


def fit_models(x: pd.DataFrame, impute: bool) -> tuple[dict, dict, pd.DataFrame]:
    """与 turn_shape_study.main 的模型部分相同；impute = U1 / U2（检验期缺的特征标准化后补 0、全部行打分，另报只算齐全行）。"""
    w = S.windows(x)
    F = x[S.FEATS].astype(float)
    if impute:                                                               # ① log 时价总额缺（ETF 等）→ 同一天本样本的中位数
        F["lmc"] = F["lmc"].fillna(F["lmc"].groupby(x["date"]).transform("median"))
    comp = F.notna().all(axis=1).to_numpy()
    xi = w["X"] & comp
    ci = w["C"] if impute else (w["C"] & comp)
    Xr = F.loc[xi].to_numpy(float)
    Xs, st = S.winsor_std(Xr, Xr)
    Xc = S.apply_std(F.loc[ci].to_numpy(float), st)
    del F
    if impute:
        Xc = np.where(np.isfinite(Xc), Xc, 0.0)
    bi = [S.FEATS.index(f) for f in S.BASELINE]
    Dc = x[ci].reset_index(drop=True)
    compc = comp[ci]
    out, scores = {}, {}
    for mk, (lab, s) in S.MODELS.items():
        y = x.loc[xi, lab].to_numpy(float)
        wf = S.fit_logit(Xs, y)
        wb = S.fit_logit(Xs[:, bi], y)
        sc, sb = S.predict(wf, Xc), S.predict(wb, Xc[:, bi])
        scores[mk] = sc
        yc = Dc[lab].to_numpy(float)
        a_full, a_base = S.auc(sc, yc), S.auc(sb, yc)
        dec, decb = S.deciles_by_day(sc, Dc["date"].to_numpy()), S.deciles_by_day(sb, Dc["date"].to_numpy())
        ds, dsb = S.dec_stats(Dc, dec), S.dec_stats(Dc, decb)
        topm = dec == S.N_DEC - 1
        ci_top = S.boot_ci(Dc.loc[topm, "R20x"].to_numpy(float), Dc.loc[topm, "month"].to_numpy())
        years = {}
        for yv in sorted(Dc["date"].dt.year.unique()):
            mm = topm & (Dc["date"].dt.year == yv).to_numpy()
            years[int(yv)] = {"n": int(mm.sum()), "R20x": round(float(np.nanmean(Dc.loc[mm, "R20x"])) * 100, 3) if mm.any() else None}
        large = sub_split(sc, Dc, (Dc["mc_rank"] <= S.LARGE_N).to_numpy())
        n225d = sub_split(sc, Dc, Dc["n225"].to_numpy(bool))
        J = S.judge(s, a_full, a_base, ds[S.N_DEC - 1], ds[0], ci_top, dsb[S.N_DEC - 1], years, large)
        coefs = sorted(zip(S.FEATS, wf[1:]), key=lambda kv: -abs(kv[1]))
        r = {"label": lab, "sign": s, "n_train": int(xi.sum()), "n_test": int(ci.sum()), "n_test_complete": int(compc.sum()),
             "train_rate_pct": round(float(y.mean()) * 100, 2), "auc": a_full, "auc_base": a_base, "deciles": ds, "deciles_base": dsb,
             "top_ci_pp": [None if v is None else round(v * 100, 3) for v in ci_top], "years": years, "large": large, "n225": n225d,
             "coef": [{"f": f, "b": round(float(b), 4)} for f, b in coefs[:12]], **J}
        ext = Dc["lo10" if lab == "RS" else "hi10"].to_numpy(bool)
        r["auc_ext"] = S.auc(sc[ext], yc[ext])
        if impute:
            dcc = S.deciles_by_day(sc[compc], Dc.loc[compc, "date"].to_numpy())
            dsc = S.dec_stats(Dc[compc].reset_index(drop=True), dcc)
            tc = Dc[compc].reset_index(drop=True)
            r["complete_only"] = {"auc": S.auc(sc[compc], yc[compc]), "top": dsc.get(S.N_DEC - 1), "bottom": dsc.get(0),
                                  "top_ci_pp": [None if v is None else round(v * 100, 3) for v in
                                                S.boot_ci(tc.loc[dcc == S.N_DEC - 1, "R20x"].to_numpy(float), tc.loc[dcc == S.N_DEC - 1, "month"].to_numpy())]}
        out[mk] = r
    return out, scores, Dc


def sub_split(sc: np.ndarray, Dc: pd.DataFrame, m: np.ndarray) -> dict:
    """子集（大型股 / 日経225）里每天分十组的最高 / 最低一组 R20x（与原研究同一写法）。"""
    if m.sum() <= 100:
        return {}
    d = S.deciles_by_day(sc[m], Dc.loc[m, "date"].to_numpy())
    r = Dc.loc[m, "R20x"].to_numpy(float)
    return {"top": round(float(np.nanmean(r[d == S.N_DEC - 1])) * 100, 3), "bottom": round(float(np.nanmean(r[d == 0])) * 100, 3), "n": int(m.sum())}


def n_bins(per_day: float) -> int:
    for lo, nb in BIN_RULE:
        if per_day >= lo:
            return nb
    return 0


def cell_stats(Dc: pd.DataFrame, scores: dict, m: np.ndarray) -> dict:
    """一个组 / 档（确认期）：比例、组内 AUC、新低 / 新高里的 AUC、组内每天分组之后 20 日超额（减本组同一天平均）。"""
    g = Dc[m].reset_index(drop=True)
    if not len(g):
        return {"rows": 0}
    r20 = g["R20"].to_numpy(float)
    r20g = r20 - pd.Series(r20).groupby(g["date"].to_numpy()).transform("mean").to_numpy()
    per_day = float(g.groupby("date").size().mean())
    nb = n_bins(per_day)
    out = {"rows": int(len(g)), "per_day": round(per_day, 1), "RS_pct": round(float(g["RS"].mean()) * 100, 2), "FS_pct": round(float(g["FS"].mean()) * 100, 2),
           "M_median_pct": round(float(np.nanmedian(g["M"])) * 100, 1), "bins": nb}
    for mk, (lab, s) in S.MODELS.items():
        sc = scores[mk][m]
        y = g[lab].to_numpy(float)
        ext = g["lo10" if lab == "RS" else "hi10"].to_numpy(bool)
        r = {"auc": S.auc(sc, y), "auc_ext": S.auc(sc[ext], y[ext])}
        if nb:
            b = S.deciles_by_day(sc, g["date"].to_numpy(), n=nb)
            top, bot = b == nb - 1, b == 0
            lo, hi = S.boot_ci(r20g[top], g.loc[top, "month"].to_numpy())
            t, bo = float(np.nanmean(r20g[top])) * 100, float(np.nanmean(r20g[bot])) * 100
            ok_ci = lo is not None and ((lo > 0) if s > 0 else (hi < 0))
            r.update({"top_pp": round(t, 3), "bottom_pp": round(bo, 3), "spread_pp": round(s * (t - bo), 3),
                      "top_ci_pp": [None if v is None else round(v * 100, 3) for v in (lo, hi)],
                      "U_top": round(float(g.loc[top, "U"].mean()) * 100, 2), "D_top": round(float(g.loc[top, "D"].mean()) * 100, 2),
                      "info": bool(s * (t - bo) >= INFO_PP and ok_ci)})
        out[mk] = r
    return out


def group_atlas(x: pd.DataFrame, pm: dict, m: np.ndarray) -> dict:
    """组内的平均形状（减本组同一天平均 = 本组 ALL）与经典形态倍数（之后 20 日超额也减本组同一天平均）。"""
    g = x[m].reset_index(drop=True)
    if not len(g):
        return {}
    r20 = g["R20"].to_numpy(float)
    g["R20x"] = (r20 - pd.Series(r20).groupby(g["date"].to_numpy()).transform("mean").to_numpy()).astype(np.float32)
    paths_g = {tf: {o: v[m] for o, v in P_.items()} for tf, P_ in pm.items()}
    return {"patterns": S.pattern_lifts(g),
            "paths": S.mean_paths(g, paths_g, {"RS": g["RS"].to_numpy() > 0.5, "FS": g["FS"].to_numpy() > 0.5, "ALL": np.ones(len(g), bool)})}


def process(T: pd.DataFrame, paths_: dict, uk: str, m: np.ndarray, names: list[str], n225: set, say) -> tuple[dict, pd.DataFrame, dict, pd.DataFrame, dict]:
    impute = uk != "U0"
    x = prep(T, m, names, n225, ffill_sig=impute)
    pm = {tf: {o: v[m] for o, v in P_.items()} for tf, P_ in paths_.items()}
    w = S.windows(x)
    res = {"counts": counts_u(x), "atlas": {}}
    X = x[w["X"]]
    for wk, mm in w.items():
        xx = x[mm]
        res["atlas"][wk] = {"lifts": S.quintile_lifts(xx, X, S.FEATS), "patterns": S.pattern_lifts(xx),
                            "paths": S.mean_paths(xx, {tf: {o: v[mm] for o, v in P_.items()} for tf, P_ in pm.items()},
                                                  {"RS": xx["RS"].to_numpy() > 0.5, "FS": xx["FS"].to_numpy() > 0.5, "ALL": np.ones(len(xx), bool)})}
    say(f"{uk} 图集完成")
    res["models"], scores, Dc = fit_models(x, impute)
    say(f"{uk} 模型：" + "；".join(f"{k} AUC {v['auc']}（基础 {v['auc_base']}）→ {v['tier']}" for k, v in res["models"].items()))
    return res, x, pm, Dc, scores


def reproduce(res_u0: dict, orig: dict | None) -> dict:
    """U0 与 turn_shape_study.json 比：行数、AUC、十组 R20x（逐个差的最大绝对值）。"""
    if not orig:
        return {"available": False}
    c0, co = res_u0["counts"], orig["counts"]
    out = {"available": True, "rows": [c0["rows"], co["rows"]], "rows_X": [c0["X"]["rows"], co["X"]["rows"]], "rows_C": [c0["C"]["rows"], co["C"]["rows"]]}
    for mk in S.MODELS:
        a, b = res_u0["models"][mk], orig["models"][mk]
        dd = [abs(a["deciles"][d]["R20x"] - b["deciles"][str(d)]["R20x"]) for d in range(S.N_DEC)]
        out[mk] = {"auc": [a["auc"], b["auc"]], "max_decile_diff_pp": round(max(dd), 4)}
    out["same"] = (out["rows"][0] == out["rows"][1] and all(out[mk]["auc"][0] == out[mk]["auc"][1] and out[mk]["max_decile_diff_pp"] < 1e-6 for mk in S.MODELS))
    return out


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> dict:
    import subprocess
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/turn_shape_wide.py", "scripts/allsec_data.py", "scripts/turn_shape_study.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def build(A: dict, days: pd.DatetimeIndex, names: list[str], run: bool, say) -> tuple[pd.DataFrame, dict]:
    pmk = panel_masks(A, days)
    orig_mask = S.sample_mask
    S.sample_mask = lambda A_, d_: pmk["union"]                               # 只换「哪些行进样本表」；其余全部是 turn_shape_study 的原函数
    try:
        T, paths_ = S.build_table(A, days, names, with_patterns=run, with_paths=run, say=say)
    finally:
        S.sample_mask = orig_mask
    kk, jj = T["k"].to_numpy(), T["j"].to_numpy()
    T["cat"] = A["cat"][kk, jj].astype(np.int8)
    T["u0"] = pmk["u0"][kk, jj]
    T["hist"] = pmk["hist"][kk, jj].astype(np.int32)
    T["va20"] = pmk["va20"][kk, jj].astype(np.float32)
    lo, hi = PH.back_extreme(A["C"].astype(float))
    T["lo10"], T["hi10"] = lo[kk, jj], hi[kk, jj]
    del lo, hi
    Lf = labels_ffill({"O": A["O"].astype(float), "C": A["C"].astype(float)})
    for k in LABEL_COLS:
        T[k + "_f"] = S.take(Lf[k].astype(float), kk, jj)
    say("向前填补口径的标注完成")
    return T, paths_


def pre_counts(T: pd.DataFrame) -> dict:
    """登记前只数个数：每个样本 / 组的行数、每天只数、标注比例、M 算不出而不进样本的行数、特征齐全的比例（不算任何特征与结果的关系）。"""
    F = universe_flags(T)
    out = {}
    for uk, m in F.items():
        x = T[m]
        out[uk] = counts_u(x if uk == "U0" else swap_labels(x))
    c = T["cat"].to_numpy()
    nm = ~np.isfinite(T["M"].to_numpy(float))
    nmf = ~np.isfinite(T["M_f"].to_numpy(float))
    g = groups_of(T)
    out["groups_all_rows"] = {k: {"rows": int((g == k).sum()), "no_M_rows_strict": int(((g == k) & nm).sum()), "no_M_rows_ffill": int(((g == k) & nmf).sum()),
                                  "per_day": round(float(T[g == k].groupby("date").size().mean()), 1) if (g == k).any() else 0.0}
                              for k in GROUPS}
    out["cat_rows"] = {int(k): int((c == k).sum()) for k in np.unique(c)}
    out["u0_no_M_rows"] = int((T["u0"].to_numpy(bool) & nm).sum())
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if not (a.counts or a.run):
        raise SystemExit("要 --counts 或 --run")
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    t0 = time.time()
    say = lambda s_: print(f"{s_}；{time.time() - t0:.0f}s", flush=True)     # noqa: E731
    import allsec_data as AS
    from qbreak.config import universe
    A = AS.load()
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    n225 = set(universe("JP", "broad"))
    T, paths_ = build(A, days, names, a.run, say)
    del A
    if a.counts:
        print(json.dumps(pre_counts(T), ensure_ascii=False, indent=1))
        return 0
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    F = universe_flags(T)
    res: dict = {"git": git_info(), "pre": pre_counts(T), "universes": {}}
    fo = out_dir / "turn_shape_study.json"
    orig = json.loads(fo.read_text(encoding="utf-8")) if fo.exists() else None
    for uk in ("U0", "U1", "U2"):
        r, x, pm, Dc, scores = process(T, paths_, uk, F[uk], names, n225, say)
        if uk == "U0":
            r["reproduce"] = reproduce(r, orig)
        if uk == "U1":
            b = buckets_of(Dc)
            r["buckets"] = {k: cell_stats(Dc, scores, b == k) for k in BUCKETS}
        if uk == "U2":
            gc = groups_of(Dc)
            r["groups"] = {k: cell_stats(Dc, scores, gc == k) for k in GROUPS}
            wC = S.windows(x)["C"]
            gx = groups_of(x)
            pmC = {tf: {o: v[wC] for o, v in P_.items()} for tf, P_ in pm.items()}
            xc = x[wC].reset_index(drop=True)
            r["group_atlas"] = {k: group_atlas(xc, pmC, gx[wC] == k) for k in GROUPS}
            del pmC, xc
        res["universes"][uk] = r
        del x, pm, Dc, scores
        say(f"{uk} 完成")
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
    U = res["universes"]
    L = [f"# 起涨点 / 起跌点 × 图形：放宽限制 + 全部品种（git {res['git']['rev']}{'（脏）' if res['git'].get('dirty') else ''}；只运行一次）", ""]
    rp = U["U0"].get("reproduce", {})
    if rp.get("available"):
        L.append(f"- U0 复现原研究：行数 {rp['rows'][0]:,} / {rp['rows'][1]:,}；AUC 上涨 {rp['rise']['auc']}、下跌 {rp['fall']['auc']}（新 / 原）；"
                 f"十组 R20x 最大差 {rp['rise']['max_decile_diff_pp']} / {rp['fall']['max_decile_diff_pp']} pp → {'一致' if rp['same'] else '有差异'}")
    L.append("")
    L.append("## 三个样本（确认期 2022-01〜）")
    L.append("")
    L.append("| 样本 | 每天只数 | 起涨 / 起跌点 | M 中位数 | 模型 | AUC（基础） | 新低 / 新高里 AUC | 最高一组 R20x（区间） | 最低一组 | 判定 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for uk, r in U.items():
        c = r["counts"]["C"]
        for mk, mr in r["models"].items():
            t, b = mr["deciles"][S.N_DEC - 1], mr["deciles"][0]
            L.append(f"| {uk} {UNIVERSES[uk]} | {c['stocks_per_day']:,.0f} | {c['RS_pct']}% / {c['FS_pct']}% | {c['M_median_pct']}% | {'上涨' if mk == 'rise' else '下跌'} | "
                     f"{mr['auc']}（{mr['auc_base']}） | {mr['auc_ext']} | {pp(t['R20x'])} pp（{mr['top_ci_pp']}） | {pp(b['R20x'])} pp | "
                     + "、".join(f"{g}{'✓' if ok else '✗'}" for g, ok in mr["gates"].items()) + f" → {mr['tier']} |")
    for uk in ("U1", "U2"):
        for mk, mr in U[uk]["models"].items():
            co = mr.get("complete_only")
            if co:
                L.append(f"- {uk} {'上涨' if mk == 'rise' else '下跌'}模型只算特征齐全的行（{mr['n_test_complete']:,} / {mr['n_test']:,}）：AUC {co['auc']}、"
                         f"最高一组 {pp((co['top'] or {}).get('R20x'))} pp（区间 {co['top_ci_pp']}）、最低一组 {pp((co['bottom'] or {}).get('R20x'))} pp")
    L.append("")
    for title, key, names_ in (("## U2 分组（确认期；组内每天分组，超额减本组同一天平均）", "groups", GROUPS), ("## U1 内国普通株按 20 日平均売買代金分档", "buckets", BUCKETS)):
        L.append(title)
        L.append("")
        L.append("| 组 | 行数 | 每天 | 起涨 / 起跌点 | M 中位数 | 上涨：AUC / 新低里 / 最高 − 最低（最高、区间） | 下跌：AUC / 新高里 / 最高 − 最低（最高、区间） | 有信息 |")
        L.append("|---|---|---|---|---|---|---|---|")
        src = U["U2" if key == "groups" else "U1"][key]
        for k, nm in names_.items():
            g = src.get(k, {})
            if not g.get("rows"):
                L.append(f"| {k} {nm} | 0 | | | | | | |")
                continue
            cells = []
            for mk in S.MODELS:
                r = g[mk]
                s = f"{r['auc']} / {r['auc_ext']}"
                if "spread_pp" in r:
                    s += f" / {r['spread_pp']:+.2f} pp（{r['top_pp']:+.2f}、{r['top_ci_pp']}）"
                cells.append(s)
            info = "、".join(f"{'上涨' if mk == 'rise' else '下跌'}{'✓' if g[mk].get('info') else '✗'}" for mk in S.MODELS) if g["bins"] else "（行太少，只报 AUC）"
            L.append(f"| {k} {nm} | {g['rows']:,} | {g['per_day']} | {g['RS_pct']}% / {g['FS_pct']}% | {g['M_median_pct']}% | {cells[0]} | {cells[1]} | {info} |")
        L.append("")
    L.append("## 平均形状（日线，减本组 / 本样本同一天平均；log × 100）")
    for k, nm in GROUPS.items():
        ga = U["U2"].get("group_atlas", {}).get(k) or {}
        p = (ga.get("paths") or {}).get("d")
        if not p:
            continue
        pick = [o for o in (-60, -20, -10, -5, -1, 1, 5, 20, 40) if p["ALL"].get(o) is not None]
        f = lambda lab: "、".join(f"{o:+d} {p[lab][o] - p['ALL'][o]:+.1f}" for o in pick if p[lab].get(o) is not None)   # noqa: E731
        L.append(f"- {k} {nm}：起涨点 {f('RS')}；起跌点 {f('FS')}")
    L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。读法与档位见脚本开头（登记时写定）。只有汇总统计，没有个股。非投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
