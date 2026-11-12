"""watch_prob_study.py — 「观察中」的股票按「之后 10 个交易日内出买入信号的历史比例」排序：比现在的顺序准不准、比例本身准不准
（只排序与展示，不改交易；登记版：规则与代码一起提交，之后不改、只运行一次）。

来由：2026-10-07 用户「观察的股票要进行买入优先级排序 比如最上面的最大概率会买入」。
现在的顺序（2026-10-07 第 7 轮加的，没检验过）：「快要出」一组在前、「观察中」在后，组内 qbreak/suggest.near_key
（闸门 → 还差的条件数 → 估计几天金叉 → 量比 → 就绪度）。

〇 定义（都用 qbreak/ 里现成的函数，与面板逐个相同）
- 股票池 = 日経225（universe("JP", "broad")，225 只；今天的成员 → 有幸存者偏差：这里问的是「什么状态下会出信号」，不是收益，偏差影响小，照实写）。
- 行情 = yfinance 21 年缓存（2005-10〜），截到 2026-10-06（登记前一天，全部已收盘）；指标 = strategy.compute_indicators
  （参数 = load_params(None, "JP")，与模拟盘 / 执行器同一组：W2 / 出货日 / 长上影都在）。
- 每只票每个交易日 t（这只票到 t 为止至少 预热 + 2 根，与 scan 相同）：状态按 qbreak/scan.py（triggered / imminent / watch / far）；
  样本 = imminent ∪ watch（面板上「快要出」「观察中」两组）。
- 结果 y = 之后 H = 10 根 K 线（t+1〜t+10，这只票自己的交易日）里 entry 为真（= 出了买入信号；之后的闸门不算）。之后不满 10 根的行不用。
- 「情况」= qbreak/watch_prob.cell_of（① MACD 在哪 10 类 × ② 还差的条件数 3 类 × ③ 今天的量比 2 类 = 60 个）：proximity 直接调用面板用的
  suggest.proximity（同一个函数）、macd_gap_pct / vol_ratio / 就绪度按 scan 的算法与取整（保留 3 / 2 / 1 位；就绪度不含「买不起 ×0.5」）。
- 比例 = watch_prob.fit（三层收缩 m = 50：情况 → ①×② → ① → 全部）。
一 拟合 / 留出
- 拟合期 F：t ≥ 2006-01-01、且 t+10 那根 ≤ 2019-12-31（不跨进留出期）。留出期 O：t ≥ 2020-01-01、t+10 那根 ≤ 2026-10-06。
- 比较的顺序（每个交易日、只在当天的样本里排；闸门历史上没有 → 两边都不含，页面上照旧闸门最先）：
  P（新）= 比例高的在前，同比例按 near_key 的其余部分（还差的条件数 → 估计几天金叉 → 量比高的先 → 就绪度高的先）；
  S（现在页面的顺序）= 「快要出」在前、「观察中」在后，组内 near_key 的其余部分；
  另报（不判定）：N = 只按 near_key（不分组）。随机排序 = 0.5。
- 排序准不准 = 当天成对比较的一致率 C（concordance）：同一天「之后 10 天出了信号」的一只 vs「没出」的一只，前者排在前面 = 1、同名次 = 0.5；
  所有交易日的对数合计（= 按对数加权的每日 AUC）。ΔC = C(P) − C(S)；区间（只描述）：按月自助法 1,000 次（种子 20261007）。
- 比例准不准 = 留出期每个情况「拟合期给的比例」与「留出期实际的比例」之差的绝对值，按留出期行数加权平均（MAD，pp）。
二 判定（事先写死；只运行一次）
- A：ΔC ≥ −0.010 且 MAD ≤ 5.0 pp → 用全部期间（t ≥ 2006-01-01、t+10 那根 ≤ 2026-10-06）重新拟合，写 var/watch_prob.json（show_pct = true）：
     面板把「快要出」「观察中」合成一组，按 闸门 → 比例 → near_key 排，每只写「之后 10 个交易日内出买入信号：历史上约 X%（同样情况 N 次）」。
- B：ΔC ≥ −0.010 但 MAD > 5.0 pp → 同样重新拟合并写文件（show_pct = false）：按比例排、页面不写百分比（比例在期间之间不稳）。
- C：ΔC < −0.010 → 不写文件，面板照旧（「快要出」「观察中」分组 + near_key）。
三 只描述（不判定）：各窗口的行数 / 天数 / 出信号的比例；60 个情况的个数与比例（全部期间）；留出期每年的 C(P) / C(S) / C(N)；
   每天排前 1 / 3 / 5 只里之后 10 天出了信号的比例（P / S / N）；按拟合比例十分位的校准表；H = 5 / 20 同样的 ΔC 与 MAD；按状态的比例。
四 事前预期（运行前写）：出信号要「金叉那天正好放量 1.5 倍」，量比是最大的不确定 → 估计 10 天内出信号的比例全部平均约 5〜10%；
   「估计 1〜2 天后金叉」的情况最高（约 15〜30%）、「在线上离得远」最低（< 3%）。P 的排序多半与 S 差不多（S 也按估计几天金叉排），
   ΔC 估计在 −0.01〜+0.03 之间；比例在两个期间之间可能漂移（W2 / 出货日过滤让信号变少的年份不同）→ MAD 有可能超过 5 pp。
五 局限：今天的日経225 成员（幸存者偏差）；同一只票连续几天都在样本里（行之间高度相关 → 「N 次」不是独立的 N 次）；
   出了信号还要过闸门（资格检查 / 新仓倍数 / 决算前 / 名额 / 钱），这里不管 → 页面照旧先按闸门分；只是排序与展示，不改交易。
用法：python scripts/watch_prob_study.py --count（只数个数：各窗口的行数、天数、各情况的行数；不算结果）
      python scripts/watch_prob_study.py --run（只运行一次：一〜三；判定 A / B 时写 var/watch_prob.json）
输出：var/out/watch_prob_study.md / .json（只有汇总统计，没有个股名单）。非投资建议。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qbreak import watch_prob as WP  # noqa: E402
from qbreak.suggest import MAX_DAYS, proximity  # noqa: E402

END = pd.Timestamp("2026-10-06")
FIT_FROM = pd.Timestamp("2006-01-01")
FIT_TO = pd.Timestamp("2019-12-31")
HOLD_FROM = pd.Timestamp("2020-01-01")
HS = (5, 10, 20)
H = WP.H
SEED = 20261007
NBOOT = 1000
DC_MIN = -0.010
MAD_MAX = 0.05
OUT_MD = ROOT / "var" / "out" / "watch_prob_study.md"
OUT_JSON = ROOT / "var" / "out" / "watch_prob_study.json"
log = logging.getLogger("watch_prob_study")


# ───────────────────────── 一行的特征（与面板同一个算法）─────────────────────────
def _scan_row(r, r1, p) -> tuple[str, float, float, float]:
    """scan.py 的状态 / macd_gap_pct / vol_ratio / 就绪度（同一套式子与取整；就绪度不含「买不起 ×0.5」）。"""
    close = float(r["Close"])
    range_pct = float(r["range_pct"]) if np.isfinite(r["range_pct"]) else np.nan
    is_range = bool(r["is_range"])
    near_zero = bool(r["near_zero"])
    gap = float((r["macd"] - r["macd_sig"]) / close * 100)
    hist_up = bool(r["macd_hist"] > r1["macd_hist"])
    vol_ratio = float(r["vol_ratio"]) if np.isfinite(r["vol_ratio"]) else 0.0
    s_range = 1.0 if is_range else float(np.clip(1 - (range_pct - p.range_x_pct) / p.range_x_pct, 0, 1)) if np.isfinite(range_pct) else 0.0
    s_zero = 1.0 if near_zero else float(np.clip(1 - (abs(float(r["macd"])) / close * 100 - p.macd_zero_band_pct) / p.macd_zero_band_pct, 0, 1))
    if gap > 0:
        s_cross = 0.6 if bool(r["golden_cross"]) else 0.3
    else:
        s_cross = float(np.clip(1 - abs(gap) / 0.5, 0, 1)) * (1.0 if hist_up else 0.7)
    s_vol = float(np.clip(vol_ratio / p.vol_mult, 0, 1))
    score = 100 * (0.30 * s_range + 0.25 * s_zero + 0.30 * s_cross + 0.15 * s_vol)
    if bool(r["entry"]):
        status = "triggered"
    elif is_range and near_zero and gap < 0 and abs(gap) < 0.15 and vol_ratio >= 1.0:
        status = "imminent"
    elif is_range and near_zero:
        status = "watch"
    else:
        status = "far"
    return status, round(gap, 3), round(vol_ratio, 2), round(score, 1)


def ticker_rows(ind: pd.DataFrame, p, hs=HS) -> pd.DataFrame:
    """一只票的指标表 → 样本行（imminent / watch）：date、status、wb / mb / vb、near_key 的其余部分（n_miss、dkey、vol2、score1）、
    y{h} / d{h}（之后 h 根里出没出信号 / 第 t+h 根的日期；不满 h 根 → y 缺）。"""
    n = len(ind)
    cols = ["date", "status", "wb", "mb", "vb", "n_miss", "dkey", "vol2", "score1"] + [f"y{h}" for h in hs] + [f"d{h}" for h in hs]
    if n < p.warmup_bars + 2:
        return pd.DataFrame(columns=cols)
    c = ind["Close"].to_numpy(float)
    isr = ind["is_range"].to_numpy(bool)
    nz = ind["near_zero"].to_numpy(bool)
    ent = ind["entry"].to_numpy(bool)
    cand = np.where(isr & nz & ~ent & np.isfinite(c) & (c > 0))[0]
    cand = cand[cand >= p.warmup_bars + 1]                     # 到 t 为止 t+1 根 ≥ 预热 + 2（scan 的门槛）
    cs = np.concatenate([[0], np.cumsum(ent.astype(np.int64))])
    idx = ind.index
    out = []
    for t in cand:
        r, r1 = ind.iloc[t], ind.iloc[t - 1]
        status, gap3, vol2, score1 = _scan_row(r, r1, p)
        if status not in ("imminent", "watch"):
            continue
        nr = proximity(ind.iloc[t - 1:t + 1], p)               # 面板用的同一个函数（只看最后两行）
        wb, mb, vb = WP.cell_of(nr, gap3, vol2)
        w = nr.get("where")
        dkey = int(nr.get("days") or MAX_DAYS) if w == "below_up" else {"below_down": MAX_DAYS + 1, "above": MAX_DAYS + 2}.get(w, MAX_DAYS + 3)
        row = {"date": idx[t], "status": status, "wb": wb, "mb": mb, "vb": vb, "n_miss": len(nr.get("miss") or []), "dkey": dkey,
               "vol2": vol2, "score1": score1}
        for h in hs:
            ok = t + h <= n - 1
            row[f"y{h}"] = float(cs[t + h + 1] - cs[t + 1] > 0) if ok else np.nan
            row[f"d{h}"] = idx[t + h] if ok else pd.NaT
        out.append(row)
    return pd.DataFrame(out, columns=cols)


# ───────────────────────── 评估 ─────────────────────────
def dense_key(cols: list) -> np.ndarray:
    """字典序（第一个最重要；小的排在前）→ 整数名次（全部键相同 = 同名次）。"""
    cols = [np.asarray(x) for x in cols]
    order = np.lexsort(tuple(cols[::-1]))
    K = np.column_stack([x[order] for x in cols])
    chg = np.r_[False, np.any(K[1:] != K[:-1], axis=1)] if len(order) else np.array([], bool)
    dense = np.empty(len(order), dtype=np.int64)
    dense[order] = np.cumsum(chg)
    return dense


def day_pairs(day, key, y) -> pd.DataFrame:
    """每天：n、n1、对数（出了 × 没出）、一致的对数（出了的排在前 = 1、同名次 = 0.5）。key 小 = 排在前。"""
    df = pd.DataFrame({"d": np.asarray(day), "k": np.asarray(key), "y": np.asarray(y).astype(int)})
    df["r"] = df.groupby("d")["k"].rank(method="average")
    df["ry"] = df["r"] * df["y"]
    g = df.groupby("d").agg(n=("y", "size"), n1=("y", "sum"), R1=("ry", "sum"))
    g["pairs"] = g["n1"] * (g["n"] - g["n1"])
    g["conc"] = g["pairs"] - (g["R1"] - g["n1"] * (g["n1"] + 1) / 2)
    return g[["n", "n1", "pairs", "conc"]]


def conc_of(g: pd.DataFrame) -> float | None:
    s = float(g["pairs"].sum())
    return float(g["conc"].sum()) / s if s > 0 else None


def top_k(day, key, tie, y, k: int) -> float | None:
    """每天按 key（同名次按 tie）排，前 k 只里之后出了信号的比例；只算当天 ≥ k 只的日子，按天平均。"""
    df = pd.DataFrame({"d": np.asarray(day), "k": np.asarray(key), "t": np.asarray(tie), "y": np.asarray(y).astype(float)})
    df = df.sort_values(["d", "k", "t"], kind="mergesort")
    df["i"] = df.groupby("d").cumcount()
    sz = df.groupby("d")["y"].size()
    ok = sz[sz >= k].index
    top = df[(df["i"] < k) & df["d"].isin(ok)]
    return float(top.groupby("d")["y"].mean().mean()) if len(top) else None


def keys(rows: pd.DataFrame, p_col: str | None) -> dict:
    """三种顺序的整数名次：P（比例 → near_key 其余）、S（快要出在前 → near_key 其余）、N（只 near_key 其余）。"""
    rest = [rows["n_miss"].to_numpy(), rows["dkey"].to_numpy(), -rows["vol2"].to_numpy(float), -rows["score1"].to_numpy(float)]
    st = (rows["status"] != "imminent").to_numpy(int)
    out = {"S": dense_key([st] + rest), "N": dense_key(rest)}
    if p_col:
        out["P"] = dense_key([-rows[p_col].to_numpy(float)] + rest)
    return out


def p_of(rows: pd.DataFrame, table: dict) -> np.ndarray:
    cache = {}
    out = np.empty(len(rows))
    for i, (wb, mb, vb) in enumerate(zip(rows["wb"], rows["mb"], rows["vb"])):
        k = (wb, mb, vb)
        if k not in cache:
            cache[k] = WP.prob(table, wb, mb, vb)["p"]
        out[i] = cache[k]
    return out


def mad_of(rows: pd.DataFrame, ycol: str) -> tuple[float, list]:
    """按情况：拟合的比例 vs 留出期实际 → 按行数加权的 |差|（0〜1）与明细。"""
    g = rows.groupby(["wb", "mb", "vb"]).agg(n=(ycol, "size"), obs=(ycol, "mean"), pred=("p", "first")).reset_index()
    g["ad"] = (g["pred"] - g["obs"]).abs()
    mad = float((g["ad"] * g["n"]).sum() / g["n"].sum())
    return mad, g.sort_values("n", ascending=False).to_dict("records")


def boot_dc(day, gP: pd.DataFrame, gS: pd.DataFrame, n: int = NBOOT, seed: int = SEED) -> tuple[float, float]:
    """按月自助法：ΔC = C(P) − C(S) 的 95% 区间（两种顺序同一批行 → 同一批对数）。"""
    m = pd.Index(pd.to_datetime(gP.index)).to_period("M")
    a = pd.DataFrame({"m": m, "cP": gP["conc"].to_numpy(), "cS": gS.loc[gP.index, "conc"].to_numpy(),
                      "pr": gP["pairs"].to_numpy()}).groupby("m").sum()
    rng = np.random.default_rng(seed)
    k = len(a)
    ix = rng.integers(0, k, size=(n, k))
    cP, cS, pr = a["cP"].to_numpy()[ix].sum(1), a["cS"].to_numpy()[ix].sum(1), a["pr"].to_numpy()[ix].sum(1)
    d = (cP - cS) / np.where(pr > 0, pr, np.nan)
    lo, hi = np.nanpercentile(d, [2.5, 97.5])
    return float(lo), float(hi)


def decide(dc: float, mad: float) -> str:
    """二 判定：A（排 + 写百分比）/ B（只排）/ C（照旧）。"""
    if not dc >= DC_MIN:
        return "C"
    return "A" if mad <= MAD_MAX else "B"


def windows(rows: pd.DataFrame, h: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """F（拟合）/ O（留出）/ ALL（重新拟合用）：都要 y{h} 有值。"""
    y, d = rows[f"y{h}"], rows[f"d{h}"]
    ok = y.notna() & (rows["date"] >= FIT_FROM) & (d <= END)
    F = rows[ok & (d <= FIT_TO)]
    O = rows[ok & (rows["date"] >= HOLD_FROM)]
    return F, O, rows[ok]


def evaluate(rows: pd.DataFrame, h: int) -> dict:
    """一个 H：拟合 F → 留出 O 上的 C(P) / C(S) / C(N)、ΔC、MAD（与明细）。"""
    F, O, _ = windows(rows, h)
    yc = f"y{h}"
    tab = WP.fit(zip(F["wb"], F["mb"], F["vb"], F[yc].astype(int)), h=h)
    O = O.copy()
    O["p"] = p_of(O, tab)
    k = keys(O, "p")
    g = {nm: day_pairs(O["date"], k[nm], O[yc]) for nm in ("P", "S", "N")}
    C = {nm: conc_of(g[nm]) for nm in g}
    mad, cells = mad_of(O, yc)
    res = {"h": h, "F_rows": int(len(F)), "O_rows": int(len(O)), "F_rate": float(F[yc].mean()), "O_rate": float(O[yc].mean()),
           "C": C, "dC": C["P"] - C["S"], "mad": mad, "table_fit": tab, "_O": O, "_g": g, "_k": k, "cells_O": cells}
    return res


# ───────────────────────── 数据 ─────────────────────────
def load_rows(progress: bool = True) -> tuple[pd.DataFrame, dict]:
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    p = load_params(None, "JP")
    uni = universe("JP", "broad")
    data = load_universe(uni, DataConfig(provider="yfinance", years=21, allow_synthetic=False,
                                         cache_ttl_hours=72.0).validate())    # 登记当天刷新过的缓存（运行时不再重下载 → 与登记前个数同一份行情）
    frames, meta = [], {"tickers": 0, "first": None, "last": None}
    t0 = time.time()
    for i, t in enumerate(sorted(data)):
        df = data[t]
        df = df[df.index <= END]
        if len(df) < p.warmup_bars + 2:
            continue
        ind = compute_indicators(df, p)
        r = ticker_rows(ind, p)
        meta["tickers"] += 1
        meta["first"] = min(meta["first"] or df.index[0], df.index[0])
        meta["last"] = max(meta["last"] or df.index[-1], df.index[-1])
        if len(r):
            frames.append(r)
        if progress and (i + 1) % 25 == 0:
            log.info("%d / %d 只（%.0f 秒）", i + 1, len(data), time.time() - t0)
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    ph = hashlib.sha256(json.dumps(p.to_dict(), sort_keys=True).encode()).hexdigest()[:16]
    meta.update({"universe": len(uni), "loaded": len(data), "params_sha16": ph, "first": str(meta["first"])[:10],
                 "last": str(meta["last"])[:10], "seconds": round(time.time() - t0, 1)})
    return rows, meta


def git_state() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/watch_prob_study.py", "qbreak/watch_prob.py",
                                     "qbreak/suggest.py", "qbreak/scan.py", "qbreak/strategy.py"],
                                    capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip())
    except Exception:                                          # noqa: BLE001
        rev, dirty = "?", None
    return {"rev": rev, "dirty": dirty}


# ───────────────────────── 运行 ─────────────────────────
def count() -> dict:
    """只数个数（不看 y）。"""
    rows, meta = load_rows()
    F, O, A = windows(rows, H)
    out = {"meta": meta, "rows_all": int(len(rows))}
    for nm, w in (("F", F), ("O", O), ("ALL", A)):
        per_day = w.groupby("date").size()
        out[nm] = {"rows": int(len(w)), "imminent": int((w["status"] == "imminent").sum()), "days": int(per_day.size),
                   "per_day_mean": round(float(per_day.mean()), 1) if len(per_day) else None,
                   "per_day_median": float(per_day.median()) if len(per_day) else None,
                   "wb": {k: int(v) for k, v in w["wb"].value_counts().sort_index().items()},
                   "mb": {k: int(v) for k, v in w["mb"].value_counts().sort_index().items()},
                   "vb": {k: int(v) for k, v in w["vb"].value_counts().sort_index().items()},
                   "cells": int(w.groupby(["wb", "mb", "vb"]).ngroups), "cells_lt50": int((w.groupby(["wb", "mb", "vb"]).size() < 50).sum())}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return out


def run() -> dict:
    t0 = time.time()
    rows, meta = load_rows()
    res = {"git": git_state(), "meta": meta, "registered": {"END": str(END.date()), "FIT": [str(FIT_FROM.date()), str(FIT_TO.date())],
           "HOLD_FROM": str(HOLD_FROM.date()), "H": H, "M": WP.M, "DC_MIN": DC_MIN, "MAD_MAX": MAD_MAX, "NBOOT": NBOOT, "SEED": SEED}}
    ev = {h: evaluate(rows, h) for h in HS}
    e = ev[H]
    O, g, k = e["_O"], e["_g"], e["_k"]
    lo, hi = boot_dc(O["date"], g["P"], g["S"])
    verdict = decide(e["dC"], e["mad"])
    res["main"] = {"C": e["C"], "dC": e["dC"], "dC_ci95": [lo, hi], "mad_pp": e["mad"] * 100, "verdict": verdict,
                   "F_rows": e["F_rows"], "O_rows": e["O_rows"], "F_rate": e["F_rate"], "O_rate": e["O_rate"],
                   "F_days": int(windows(rows, H)[0]["date"].nunique()), "O_days": int(O["date"].nunique()),
                   "O_days_with_pairs": int((g["P"]["pairs"] > 0).sum())}
    # 三 只描述
    yr = O["date"].dt.year.to_numpy()
    res["by_year"] = []
    for y in sorted(set(yr)):
        m = yr == y
        sub = O[m]
        kk = keys(sub, "p")
        res["by_year"].append({"year": int(y), "rows": int(m.sum()), "rate": float(sub[f"y{H}"].mean()),
                               **{f"C_{nm}": conc_of(day_pairs(sub["date"], kk[nm], sub[f"y{H}"])) for nm in ("P", "S", "N")}})
    tie = O.index.to_numpy()                                    # 同名次的先后：行号（与股票代码顺序一致，确定性）
    res["top_k"] = {nm: {f"top{kk_}": top_k(O["date"], k[nm], tie, O[f"y{H}"], kk_) for kk_ in (1, 3, 5)} for nm in ("P", "S", "N")}
    O2 = O.copy()
    O2["dec"] = pd.qcut(O2["p"].rank(method="first"), 10, labels=False)
    res["calib_deciles"] = [{"decile": int(d), "rows": int(len(s)), "pred": float(s["p"].mean()), "obs": float(s[f"y{H}"].mean())}
                            for d, s in O2.groupby("dec")]
    res["cells_O"] = [{kk_: (round(v, 6) if isinstance(v, float) else v) for kk_, v in c.items()} for c in e["cells_O"]]
    res["by_status_O"] = {s: {"rows": int((O["status"] == s).sum()), "rate": float(O.loc[O["status"] == s, f"y{H}"].mean())}
                          for s in ("imminent", "watch")}
    res["other_h"] = {h: {"C": ev[h]["C"], "dC": ev[h]["dC"], "mad_pp": ev[h]["mad"] * 100, "F_rate": ev[h]["F_rate"],
                          "O_rate": ev[h]["O_rate"], "verdict_if_used": decide(ev[h]["dC"], ev[h]["mad"])} for h in HS if h != H}
    # 全部期间的表（判定 A / B 才写进 var/watch_prob.json）
    _, _, A = windows(rows, H)
    full = WP.fit(zip(A["wb"], A["mb"], A["vb"], A[f"y{H}"].astype(int)), h=H,
                  extra={"show_pct": verdict == "A", "verdict": verdict, "rows": int(len(A)), "fit_from": str(A["date"].min().date()),
                         "fit_to": str(A["date"].max().date()), "end": str(END.date()), "params_sha16": meta["params_sha16"],
                         "study": "scripts/watch_prob_study.py", "registered": res["git"]["rev"]})
    res["table_full"] = full
    res["table_fit"] = e["table_fit"]
    res["written"] = None
    if verdict in ("A", "B"):
        WP.FILE.write_text(json.dumps(full, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        res["written"] = str(WP.FILE.relative_to(ROOT))
    res["seconds"] = round(time.time() - t0, 1)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    OUT_MD.write_text(render(res), encoding="utf-8")
    return res


def _pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def render(res: dict) -> str:
    m = res["main"]
    L = ["# 观察中的买入优先级（之后 10 个交易日内出买入信号的历史比例）", "",
         f"代码 {res['git']['rev']}{'（有未提交的改动！）' if res['git'].get('dirty') else ''}；参数指纹 {res['meta']['params_sha16']}；"
         f"日経225 {res['meta']['tickers']} 只，行情 {res['meta']['first']}〜{res['meta']['last']}；用时 {res['seconds']} 秒。", "",
         f"## 判定：{m['verdict']}（A = 按比例排并写百分比 / B = 只按比例排 / C = 照旧）", "",
         f"- 留出期（2020-01〜，{m['O_rows']:,} 行、{m['O_days']:,} 天）：C(P 新) = {m['C']['P']:.4f}、C(S 现在) = {m['C']['S']:.4f}、"
         f"C(N 不分组) = {m['C']['N']:.4f} → ΔC = {m['dC']:+.4f}（按月自助法 95% 区间 {m['dC_ci95'][0]:+.4f}〜{m['dC_ci95'][1]:+.4f}；门槛 ≥ {DC_MIN:+.3f}）",
         f"- 比例准不准：MAD = {m['mad_pp']:.2f} pp（门槛 ≤ {MAD_MAX * 100:.1f} pp）",
         f"- 出信号的比例：拟合期 {_pct(m['F_rate'])}（{m['F_rows']:,} 行）、留出期 {_pct(m['O_rate'])}",
         f"- 写入：{res['written'] or '没有（照旧的顺序）'}", "", "## 每天排前几只里之后 10 天出了信号的比例（留出期）", "",
         "| 顺序 | 前 1 | 前 3 | 前 5 |", "|---|---|---|---|"]
    for nm, lab in (("P", "P 新（比例）"), ("S", "S 现在（快要出 → 观察中）"), ("N", "N 不分组 near_key")):
        t = res["top_k"][nm]
        L.append(f"| {lab} | {_pct(t['top1'])} | {_pct(t['top3'])} | {_pct(t['top5'])} |")
    L += ["", "## 留出期每年", "", "| 年 | 行 | 出信号 | C(P) | C(S) | C(N) |", "|---|---|---|---|---|---|"]
    for r in res["by_year"]:
        f4 = lambda x: "—" if x is None else f"{x:.4f}"            # noqa: E731
        L.append(f"| {r['year']} | {r['rows']:,} | {_pct(r['rate'])} | {f4(r['C_P'])} | {f4(r['C_S'])} | {f4(r['C_N'])} |")
    L += ["", "## 校准（留出期，按拟合比例十分位）", "", "| 十分位 | 行 | 拟合的比例 | 实际 |", "|---|---|---|---|"]
    for r in res["calib_deciles"]:
        L.append(f"| {r['decile'] + 1} | {r['rows']:,} | {_pct(r['pred'])} | {_pct(r['obs'])} |")
    L += ["", "## 全部期间的表（① MACD 在哪 × ② 还差的条件数；③ 量比合起来）", "", "| ① | ② | 行 | 出信号 | 比例（收缩后） |", "|---|---|---|---|---|"]
    t = res["table_full"]
    for key_, v in sorted(t["l2"].items(), key=lambda kv: -kv[1]["p"]):
        wb, mb = key_.split("|")
        L.append(f"| {WP.WB_TEXT.get(wb, wb)} | {mb} | {v['n']:,} | {v['y']:,} | {_pct(v['p'])} |")
    L += ["", "## 按状态（留出期）", ""]
    for s, v in res["by_status_O"].items():
        L.append(f"- {s}：{v['rows']:,} 行、出信号 {_pct(v['rate'])}")
    L += ["", "## 其他 H（只描述）", ""]
    for h, v in res["other_h"].items():
        L.append(f"- H = {h}：C(P) {v['C']['P']:.4f} / C(S) {v['C']['S']:.4f} → ΔC {v['dC']:+.4f}；MAD {v['mad_pp']:.2f} pp；"
                 f"出信号 拟合期 {_pct(v['F_rate'])} / 留出期 {_pct(v['O_rate'])}（若用它判定：{v['verdict_if_used']}）")
    L += ["", "只排序与展示，不改交易（出了信号还要过闸门 / 名额 / 钱）。非投资建议。", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--count", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if a.count:
        count()
    else:
        res = run()
        print(OUT_MD.read_text(encoding="utf-8"))
        print(json.dumps({"verdict": res["main"]["verdict"], "written": res["written"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
