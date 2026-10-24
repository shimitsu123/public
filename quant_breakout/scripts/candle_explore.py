"""candle_explore.py — K 线形态的探索（2026-09-27；只用探索期 2017-01〜2021-12，不是登记的检验）。

用户：「按照这个类似图形的特点，从过去十年的数据里面分析出第二天以后会涨一段时间的图形还有快到顶该卖了的转换点图形…
持续研究 6 个小时左右…一直推敲 进步 让预测更准确 不同的搭配…考虑没有考虑过的方法」。
做法：J-Quants 时点 TOPIX 1000 的宽表在 2021-12-31 之后全部切掉（之后的行根本不进内存 → 目标在 2021 年底之后自动缺值），
可以随便反复试；最后挑出来的候选另外登记（scripts/candle_study.py），才看 2022〜2026 与 2006〜2016。
探索期分两半 T1 = 2017〜2019、T2 = 2020〜2021：「两半同号」是挑选的必要条件；另用打乱对照（同一天里随机换成别的票）估计偶然通过的个数。
每一轮的输出：var/out/candle_explore_<轮>.md（只有探索期的统计）。
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candle_data as CD                                                     # noqa: E402
from qbreak import candles as K                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

T_END = "2021-12-31"
T1, T2 = ("2017-01-01", "2020-01-01"), ("2020-01-01", "2022-01-01")
COST = 0.0035                                                                # 来回：滑点 0.10% × 2 + 立花 ¥187 × 2 / ¥25 万
N_BOOT, SEED = 1000, 7
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def load_t() -> dict:
    """缓存 → 只留 2021-12-31 为止的行（探索期之后的数据不进内存）。"""
    D = CD.load()
    keep = np.asarray(D["days"] <= pd.Timestamp(T_END))
    days = D["days"][keep]
    P = {k: v[keep] for k, v in D["P"].items()}
    mem = {u: v[keep] for u, v in D["mem"].items()}
    return {"days": days, "names": D["names"], "P": P, "mem": mem, "ratio": None if D.get("ratio") is None else D["ratio"][keep]}


def rsi_n(C: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(C, axis=0, prepend=np.nan)
    up = pd.DataFrame(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    dn = pd.DataFrame(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        r = 100 - 100 / (1 + up / dn)
    return np.where((dn == 0) & np.isfinite(up), 100.0, r)


def features(P: dict) -> tuple[dict, dict, dict, dict]:
    g = K.geometry(P)
    x = K.context(P, g)
    pat = K.patterns(P, g, x)
    C, V = P["C"], P["V"]
    sma150 = K.rolling_mean(C, 150)
    sma200 = K.rolling_mean(C, 200)
    sma25 = K.rolling_mean(C, 25)
    with np.errstate(invalid="ignore"):
        x["lt_up"] = (C > sma150) & (sma150 > K.sh(sma150, 20))
        x["above200"] = C > sma200
        x["lowvol"] = x["vr"] <= 0.7
        r2 = rsi_n(C, 2)
        dn3 = (C < K.sh(C, 1)) & (K.sh(C, 1) < K.sh(C, 2)) & (K.sh(C, 2) < K.sh(C, 3))
        extra = {
            "NOSUP": g["bear"] & (g["size"] <= 0.7) & (x["vr"] <= 0.7) & (C > sma25),
            "STOPV": (g["bear"] | (g["lo_r"] >= 0.4)) & (x["vr"] >= 2.0) & (x["ret5"] <= -0.05),
            "UPTHR": x["hi20_poke"] & (g["clv"] <= -0.33) & (x["vr"] >= 1.5),
            "BCLX": g["bull"] & (g["body_r"] >= 0.6) & (g["size"] >= 1.5) & (x["vr"] >= 2.5) & (x["ret5"] >= 0.08),
            "SCLX": g["bear"] & (g["size"] >= 1.5) & (x["vr"] >= 2.5) & (x["ret5"] <= -0.08),
            "DROP5": (x["ret5"] <= -0.10) & x["lt_up"],
            "DROP5H": (x["ret5"] <= -0.10) & x["lt_up"] & ((g["lo_r"] >= 0.4) | pat["HAM"] | pat["ENGB"]),
            "RSI2": (r2 <= 5) & x["above200"],
            "DN3UP": dn3 & x["lt_up"],
        }
    for k, v in extra.items():
        pat[k] = np.asarray(v, bool) & g["ok"]
    return g, x, pat, {"rsi2": r2}


CTX = {"ALL": None, "DN": "dn_tr", "UP": "up_tr", "VS": "vsurge", "LV": "lowvol", "LOW20": "lo20_poke", "HI20": "hi20_close", "LTUP": "lt_up"}


def month_boot_mean(v: np.ndarray, m: np.ndarray, n: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float, float]:
    """平均、按月聚类的 95% 区间、双侧 p（自助分布跨过 0 的比例 × 2）。"""
    if len(v) < 30:
        return float("nan"), float("nan"), float("nan"), float("nan")
    um, inv = np.unique(m, return_inverse=True)
    k = len(um)
    s, c = np.bincount(inv, v, k), np.bincount(inv, minlength=k).astype(float)
    pick = np.random.default_rng(seed).integers(0, k, size=(n, k))
    b = s[pick].sum(1) / np.maximum(c[pick].sum(1), 1)
    lo, hi = np.percentile(b, [2.5, 97.5])
    p = 2 * min((b <= 0).mean(), (b >= 0).mean())
    return float(v.mean()), float(lo), float(hi), float(max(p, 1 / n))


def bh(p: np.ndarray, q: float = 0.10) -> np.ndarray:
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), bool)
    if not ok.any():
        return out
    idx = np.where(ok)[0]
    ps = p[idx]
    o = np.argsort(ps)
    m = len(ps)
    thr = q * (np.arange(1, m + 1) / m)
    passed = ps[o] <= thr
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        out[idx[o[:kmax + 1]]] = True
    return out


def placebo(mask: np.ndarray, valid: np.ndarray, rng) -> np.ndarray:
    """同一天里把事件随机换到别的有效的票上（每天的事件数不变 → 保留市场层的影响）。"""
    out = np.zeros_like(mask)
    for i in np.where(mask.any(axis=1))[0]:
        cand = np.where(valid[i])[0]
        k = int(mask[i].sum())
        if len(cand) >= k > 0:
            out[i, rng.choice(cand, k, replace=False)] = True
    return out


# ────────────────────────── 第 1 轮：形态 × 情境 的扫描 ──────────────────────────
def scan(masks: dict[str, np.ndarray], X: dict[str, np.ndarray], R10: np.ndarray, mids: np.ndarray, days: pd.DatetimeIndex,
         base: np.ndarray) -> pd.DataFrame:
    """每个事件掩码：探索期全部 / T1 / T2 的 5 / 10 / 20 日超额平均、10 日净胜率（原始收益 > 来回成本）、按月聚类 p。"""
    r1 = np.asarray((days >= pd.Timestamp(T1[0])) & (days < pd.Timestamp(T1[1])))[:, None]
    r2 = np.asarray((days >= pd.Timestamp(T2[0])) & (days < pd.Timestamp(T2[1])))[:, None]
    M = np.broadcast_to(mids[:, None], base.shape)
    rows = []
    for name, mk in masks.items():
        ev = mk & base
        rec = {"name": name}
        for h in ("x5", "x10", "x20"):
            Y = X[h]
            fin = np.isfinite(Y)
            a = ev & fin
            v, m = Y[a], M[a]
            mean, lo, hi, p = month_boot_mean(v, m)
            rec.update({f"{h}": mean, f"{h}_lo": lo, f"{h}_hi": hi, f"{h}_p": p, f"{h}_n": int(a.sum()),
                        f"{h}_t1": float(np.nanmean(Y[a & r1])) if (a & r1).any() else np.nan,
                        f"{h}_t2": float(np.nanmean(Y[a & r2])) if (a & r2).any() else np.nan})
        a = ev & np.isfinite(R10)
        rec["win10"] = float((R10[a] > COST).mean()) if a.any() else np.nan
        rec["net10"] = float((R10[a] - COST).mean()) if a.any() else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def pick(df: pd.DataFrame, h: str = "x10", min_n: int = 200, min_eff: float = 0.005) -> pd.Series:
    """挑选：n ≥ 200、两半同号、|平均| ≥ 0.5%、BH（q = 0.10，对这一张表）。"""
    same = np.sign(df[f"{h}_t1"]) == np.sign(df[f"{h}_t2"])
    big = df[h].abs() >= min_eff
    ok_n = df[f"{h}_n"] >= min_n
    q = bh(df[f"{h}_p"].to_numpy())
    return same & big & ok_n & q


def round1() -> int:
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, _ = features(P)
    t = K.targets(P, horizons=(5, 10, 20))
    base = g["ok"] & mem & np.asarray(days >= pd.Timestamp(T1[0]))[:, None]
    X = {f"x{h}": K.excess(t[f"f{h}"], mem & g["ok"]) for h in (5, 10, 20)}
    mids = (days.year * 100 + days.month).to_numpy()
    masks = {}
    for pn, pm in pat.items():
        for cn, ck in CTX.items():
            m = pm if ck is None else (pm & x[ck])
            if (m & base).sum() >= 100:
                masks[f"{pn}|{cn}"] = m
    df = scan(masks, X, t["f10"], mids, days, base)
    df["sel"] = pick(df)
    say("# K 线形态探索 第 1 轮：形态 × 情境（只用探索期 2017〜2021；不是登记的检验）")
    say(f"时点 TOPIX 1000 成员；{len(masks)} 个「形态 × 情境」（出现 ≥ 100 次）；超额 = 第二天开盘买、H 个交易日后开盘卖，减同一天全部成员平均；"
        f"净胜率 = 10 日原始收益 > 来回成本 {COST * 100:.2f}% 的比例。")
    say(f"挑选条件：出现 ≥ 200 次、T1（2017〜2019）与 T2（2020〜2021）10 日超额同号、|10 日超额| ≥ 0.5%、BH q ≤ 0.10（按月聚类 p）。通过 {int(df['sel'].sum())} 个。")
    rng = np.random.default_rng(11)
    valid = base & np.isfinite(X["x10"])
    nplace = []
    for rep in range(3):
        pm = {k: placebo(v & base, valid, rng) for k, v in masks.items()}
        dp = scan(pm, X, t["f10"], mids, days, base)
        nplace.append(int(pick(dp).sum()))
    say(f"打乱对照（同一天随机换票，3 次）通过个数：{nplace} → 偶然水平约 {np.mean(nplace):.1f} 个")
    cols = ["name", "x10_n", "x5", "x10", "x10_lo", "x10_hi", "x10_t1", "x10_t2", "x20", "win10", "net10"]
    f = lambda v: "—" if not np.isfinite(v) else f"{v * 100:+.2f}%"                                 # noqa: E731
    for title, sub in (("看涨（10 日超额 > 0）", df[df["sel"] & (df["x10"] > 0)].sort_values("x10", ascending=False)),
                       ("看跌 / 该卖（10 日超额 < 0）", df[df["sel"] & (df["x10"] < 0)].sort_values("x10"))):
        say(f"\n## 通过的：{title}（{len(sub)} 个）")
        say("| 形态 | 情境 | 次数 | 5 日超额 | 10 日超额（95% 区间） | T1 / T2 | 20 日超额 | 10 日净胜率 | 10 日平均净收益 |")
        say("|---|---|---|---|---|---|---|---|---|")
        for r in sub[cols].itertuples(index=False):
            pn, cn = r.name.split("|")
            say(f"| {pn} {K.PATTERNS.get(pn, ('', 0))[0][:18] if pn in K.PATTERNS else pn} | {cn} | {r.x10_n:,} | {f(r.x5)} | {f(r.x10)}（{f(r.x10_lo)}〜{f(r.x10_hi)}） | "
                f"{f(r.x10_t1)} / {f(r.x10_t2)} | {f(r.x20)} | {r.win10 * 100:.1f}% | {f(r.net10)} |")
    say("\n## 参考：经典形态（不分情境）的 10 日超额，传统方向 vs 数据")
    say("| 形态 | 传统方向 | 次数 | 10 日超额 | T1 / T2 | 与传统一致？ |")
    say("|---|---|---|---|---|---|")
    for pn, (lab, sgn) in K.PATTERNS.items():
        r = df[df["name"] == f"{pn}|ALL"]
        if not len(r):
            continue
        r = r.iloc[0]
        agree = "—" if sgn == 0 else ("✓" if np.sign(r["x10"]) == sgn and np.sign(r["x10_t1"]) == np.sign(r["x10_t2"]) else "✗")
        say(f"| {pn} {lab[:24]} | {'涨' if sgn > 0 else ('跌' if sgn < 0 else '中性')} | {int(r['x10_n']):,} | {f(r['x10'])} | {f(r['x10_t1'])} / {f(r['x10_t2'])} | {agree} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    df.to_csv(paths.sub("cache") / "candle_explore_1.csv", index=False)
    (paths.out_dir() / "candle_explore_1.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 2 轮：连续的 K 线特征分十档（反转有多大、稳不稳） ──────────────────────────
def cont_features(P: dict, g: dict, x: dict, extra: dict) -> dict[str, np.ndarray]:
    C, H, L, O = P["C"], P["H"], P["L"], P["O"]
    with np.errstate(invalid="ignore", divide="ignore"):
        f = {"ret1": C / K.sh(C, 1) - 1, "ret5": x["ret5"], "ret20": C / K.sh(C, 20) - 1, "gap": g["gap"],
             "clv": g["clv"], "up_r": g["up_r"], "lo_r": g["lo_r"], "body_s": (C - O) / g["rng"], "size": g["size"],
             "vr": x["vr"], "ma25": x["ma25_pos"], "rsi2": extra["rsi2"],
             "hi20d": C / K.sh(K.rolling_max(H, 20), 1) - 1, "lo20d": C / K.sh(K.rolling_min(L, 20), 1) - 1,
             "ret5_atr": (C / K.sh(C, 5) - 1) / (g["atr1"] / C)}
    return f


def decile_table(F: np.ndarray, Y: np.ndarray, base: np.ndarray, rows: np.ndarray) -> tuple[np.ndarray, float]:
    """每天在成员里按 F 分十档（1 = 最低）→ 各档 Y 的平均；另返回每天秩相关的平均（IC）。"""
    Fm = np.where(base & rows[:, None] & np.isfinite(F) & np.isfinite(Y), F, np.nan)
    r = pd.DataFrame(Fm).rank(axis=1, pct=True).to_numpy()
    d = np.ceil(r * 10).clip(1, 10)
    out = np.full(10, np.nan)
    for k in range(1, 11):
        m = d == k
        if m.any():
            out[k - 1] = float(np.nanmean(Y[m]))
    ry = pd.DataFrame(np.where(np.isfinite(Fm), Y, np.nan)).rank(axis=1, pct=True).to_numpy()
    ic = pd.DataFrame(r).T.corrwith(pd.DataFrame(ry).T).to_numpy() if False else _row_corr(r, ry)
    return out, float(np.nanmean(ic))


def _row_corr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ok = np.isfinite(a) & np.isfinite(b)
    n = ok.sum(1)
    a0 = np.where(ok, a, 0.0)
    b0 = np.where(ok, b, 0.0)
    ma, mb = a0.sum(1) / np.maximum(n, 1), b0.sum(1) / np.maximum(n, 1)
    da, db = np.where(ok, a - ma[:, None], 0.0), np.where(ok, b - mb[:, None], 0.0)
    num = (da * db).sum(1)
    den = np.sqrt((da ** 2).sum(1) * (db ** 2).sum(1))
    with np.errstate(invalid="ignore", divide="ignore"):
        c = num / den
    return np.where(n >= 30, c, np.nan)


def round2() -> int:
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    t = K.targets(P, horizons=(1, 5, 10))
    base = g["ok"] & mem & np.asarray(days >= pd.Timestamp(T1[0]))[:, None]
    X = {f"x{h}": K.excess(t[f"f{h}"], mem & g["ok"]) for h in (1, 5, 10)}
    F = cont_features(P, g, x, extra)
    r1 = np.asarray((days >= pd.Timestamp(T1[0])) & (days < pd.Timestamp(T1[1])))
    r2 = np.asarray((days >= pd.Timestamp(T2[0])) & (days < pd.Timestamp(T2[1])))
    say("# K 线形态探索 第 2 轮：连续 K 线特征分十档（只用探索期；不是登记的检验）")
    say("每天在时点 TOPIX 1000 成员里按特征分十档（1 = 最低、10 = 最高）；Y = 第二天开盘买、H 日后开盘卖的超额；IC = 每天秩相关的平均。")
    for h in ("x5", "x10"):
        say(f"\n## {h[1:]} 日超额：最低档 / 最高档 / 高 − 低（T1 2017〜2019 | T2 2020〜2021）与 IC")
        say("| 特征 | T1 低 | T1 高 | T1 高−低 | T1 IC | T2 低 | T2 高 | T2 高−低 | T2 IC | 两半同号 |")
        say("|---|---|---|---|---|---|---|---|---|---|")
        for k, v in F.items():
            a1, ic1 = decile_table(v, X[h], base, r1)
            a2, ic2 = decile_table(v, X[h], base, r2)
            s1, s2 = a1[9] - a1[0], a2[9] - a2[0]
            same = "✓" if np.sign(s1) == np.sign(s2) and np.sign(ic1) == np.sign(ic2) else "✗"
            say(f"| {k} | {a1[0] * 100:+.2f}% | {a1[9] * 100:+.2f}% | {s1 * 100:+.2f} | {ic1:+.4f} | {a2[0] * 100:+.2f}% | {a2[9] * 100:+.2f}% | "
                f"{s2 * 100:+.2f} | {ic2:+.4f} | {same} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_2.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 3 轮：上升趋势中的缩量急跌（押し目）展开 ──────────────────────────
def pullback_grid(P: dict, g: dict, x: dict) -> dict[str, np.ndarray]:
    """下跌幅度 × 下跌时的量 × 趋势 × 是否跌破 20 日最低 → 事件掩码（名字 = 各条件）。"""
    C, V = P["C"], P["V"]
    sma150, sma200 = K.rolling_mean(C, 150), K.rolling_mean(C, 200)
    with np.errstate(invalid="ignore", divide="ignore"):
        vr5 = K.rolling_mean(V, 5) / K.sh(K.rolling_mean(V, 20), 5)        # 最近 5 天的量 ÷ 之前 20 天
        trends = {"T150": (C > sma150) & (sma150 > K.sh(sma150, 20)), "T200": K.sh(C, 5) > K.sh(sma200, 5),
                  "ANY": np.ones_like(C, bool)}
        vols = {"v5≤0.7": vr5 <= 0.7, "v5≤0.85": vr5 <= 0.85, "v1≤0.7": x["vr"] <= 0.7, "v5>1.2": vr5 > 1.2, "any": np.ones_like(C, bool)}
        drops = {f"d≤{d}%": x["ret5"] <= -d / 100 for d in (6, 8, 10, 12)}
        lows = {"破20低": x["lo20_poke"], "没破": ~x["lo20_poke"], "any": np.ones_like(C, bool)}
    out = {}
    for dn, dm in drops.items():
        for vn, vm in vols.items():
            for tn, tm in trends.items():
                for ln, lm in lows.items():
                    out[f"{dn}|{vn}|{tn}|{ln}"] = np.asarray(dm & vm & tm & lm, bool) & g["ok"]
    return out


def round3() -> int:
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    t = K.targets(P, horizons=(5, 10, 20))
    base = g["ok"] & mem & np.asarray(days >= pd.Timestamp(T1[0]))[:, None]
    X = {f"x{h}": K.excess(t[f"f{h}"], mem & g["ok"]) for h in (5, 10, 20)}
    mids = (days.year * 100 + days.month).to_numpy()
    masks = {k: v for k, v in pullback_grid(P, g, x).items() if (v & base).sum() >= 100}
    df = scan(masks, X, t["f10"], mids, days, base)
    df["sel"] = pick(df)
    say("# K 线形态探索 第 3 轮：上升趋势中的缩量急跌（押し目）（只用探索期；不是登记的检验）")
    say(f"{len(masks)} 个组合（5 日跌幅 × 下跌时的量 × 趋势 × 是否跌破 20 日最低；出现 ≥ 100 次）。v5 = 最近 5 天均量 ÷ 之前 20 天均量；"
        "v1 = 当天量比；T150 = 收盘在上升的 150 日线上；T200 = 5 天前收盘在 200 日线上。挑选条件同第 1 轮。"
        f"通过 {int(df['sel'].sum())} 个。")
    f = lambda v: "—" if not np.isfinite(v) else f"{v * 100:+.2f}%"                                 # noqa: E731
    say("\n## 10 日超额最高的 25 个（不管是否通过）")
    say("| 组合 | 次数 | 5 日超额 | 10 日超额（95% 区间） | T1 / T2 | 20 日超额 | 10 日净胜率 | 10 日平均净收益 | 通过 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for r in df.sort_values("x10", ascending=False).head(25).itertuples(index=False):
        say(f"| {r.name} | {r.x10_n:,} | {f(r.x5)} | {f(r.x10)}（{f(r.x10_lo)}〜{f(r.x10_hi)}） | {f(r.x10_t1)} / {f(r.x10_t2)} | {f(r.x20)} | "
            f"{r.win10 * 100:.1f}% | {f(r.net10)} | {'✓' if r.sel else ''} |")
    say("\n## 量的影响（5 日跌 ≥ 10%、T150、任意 20 日低点）")
    say("| 下跌时的量 | 次数 | 10 日超额 | T1 / T2 | 10 日净胜率 |")
    say("|---|---|---|---|---|")
    for vn in ("v5≤0.7", "v5≤0.85", "v1≤0.7", "any", "v5>1.2"):
        r = df[df["name"] == f"d≤10%|{vn}|T150|any"]
        if len(r):
            r = r.iloc[0]
            say(f"| {vn} | {int(r['x10_n']):,} | {f(r['x10'])} | {f(r['x10_t1'])} / {f(r['x10_t2'])} | {r['win10'] * 100:.1f}% |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    df.to_csv(paths.sub("cache") / "candle_explore_3.csv", index=False)
    (paths.out_dir() / "candle_explore_3.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 4 轮：押し目买入的逐笔交易（每只票单独、扣成本） ──────────────────────────
def frames(D: dict, entry: np.ndarray, dead: np.ndarray, mem: np.ndarray, names_idx) -> dict[str, pd.DataFrame]:
    """缓存的宽表 → 每只票的指标表（qbreak.engine.run_backtest 需要的列）；entry 只在成员日。"""
    P, days = D["P"], D["days"]
    a = K.atr(P["H"], P["L"], P["C"])
    out = {}
    for j in names_idx:
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        if ok.sum() < 60 or not (entry[:, j] & mem[:, j] & ok).any():
            continue
        df = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                           "Volume": P["V"][ok, j], "atr": a[ok, j], "entry": (entry[:, j] & mem[:, j])[ok],
                           "dead_cross": dead[ok, j], "climax": False}, index=days[ok])
        out[D["names"][j]] = df
    return out


def trades_of(ind: dict, p) -> pd.DataFrame:
    import pit_retrain_study as PRS
    return PRS.indep_trades(ind, p, {})


def tstat(T: pd.DataFrame, a=None, b=None) -> dict:
    x = T
    if a is not None:
        x = x[(x["sig_date"] >= pd.Timestamp(a)) & (x["sig_date"] < pd.Timestamp(b))]
    net = x["net"].to_numpy(float)
    if not len(net):
        return {"n": 0}
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    return {"n": len(net), "win": (net > 0).mean() * 100, "mean": net.mean(), "med": float(np.median(net)),
            "pf": pos / neg if neg > 0 else np.nan, "hold": x["hold_days"].mean()}


def round4() -> int:
    from dataclasses import replace
    from qbreak.trader import load_params
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    grid = pullback_grid(P, g, x)
    ents = {"PB_A 跌≥10%·缩量v5≤0.85·T150·没破20低": grid["d≤10%|v5≤0.85|T150|没破"],
            "PB_B 跌≥10%·缩量v5≤0.85·T150": grid["d≤10%|v5≤0.85|T150|any"],
            "PB_C 跌≥8%·缩量v5≤0.85·T150·没破20低": grid["d≤8%|v5≤0.85|T150|没破"],
            "PB_D 跌≥10%·当天量比≤0.7·T150": grid["d≤10%|v1≤0.7|T150|any"]}
    C = P["C"]
    sma5 = K.rolling_mean(C, 5)
    with np.errstate(invalid="ignore"):
        above5 = np.asarray(C > sma5, bool)
    p0 = load_params(market="JP")
    exits = {"固定 5 日": (np.zeros_like(C, bool), replace(p0, max_hold_days=5)),
             "固定 10 日": (np.zeros_like(C, bool), replace(p0, max_hold_days=10)),
             "固定 20 日": (np.zeros_like(C, bool), replace(p0, max_hold_days=20)),
             "收盘回到 5 日线上就卖（最多 10 日）": (above5, replace(p0, max_hold_days=10)),
             "现行出场（MACD 死叉等）": (None, p0)}
    idx = [j for j in range(len(D["names"])) if mem[:, j].any()]
    say("# K 线形态探索 第 4 轮：押し目买入的逐笔交易（只用探索期；不是登记的检验）")
    say("每只票单独、一次一仓；第二天开盘买；7% 止损 / 25% 止盈 / 12% 跟踪止损照现行；扣滑点与立花 ¥25 万一笔的来回手续费；"
        "「现行出场」= 日线 MACD 死叉等（dead_cross 用现行的）。")
    say("| 买点 | 出场 | T1 笔数 / 胜率 / 每笔平均 / 盈亏比 / 持有 | T2 同左 | 全部 |")
    say("|---|---|---|---|---|")
    from qbreak.strategy import macd
    Cdf = pd.DataFrame(C)
    m_, s_, _ = macd(Cdf, 12, 26, 9)
    dead_cur = np.asarray((m_ < s_) & (m_.shift(1) >= s_.shift(1)), bool)
    res = {}
    for en, em in ents.items():
        for xn, (dx, pp) in exits.items():
            dd = dead_cur if dx is None else dx
            ind = frames(D, em, dd, mem, idx)
            T = trades_of(ind, pp)
            a1, a2, aa = tstat(T, *T1), tstat(T, *T2), tstat(T)
            res[(en, xn)] = (a1, a2, aa)
            c = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {s['pf']:.2f} / {s['hold']:.1f} 天"   # noqa: E731
            say(f"| {en} | {xn} | {c(a1)} | {c(a2)} | {c(aa)} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_4.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 5 轮：现行突破持仓 + 见顶 K 线离场（卖顶转换点） ──────────────────────────
def breakout_frames(D: dict, mem: np.ndarray, p0) -> dict[str, pd.DataFrame]:
    """缓存宽表 → compute_indicators（现行参数；相对强度过滤是关的，所以不需要指数）→ entry 只在成员日。"""
    from qbreak.strategy import compute_indicators
    P, days = D["P"], D["days"]
    out = {}
    for j, t in enumerate(D["names"]):
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        if ok.sum() < 80 or not mem[:, j].any():
            continue
        df = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                           "Volume": P["V"][ok, j]}, index=days[ok])
        ind = compute_indicators(df, p0, None)
        ind["entry"] = ind["entry"].to_numpy(bool) & mem[ok, j]
        out[t] = ind
    return out


def round5() -> int:
    from dataclasses import replace
    from qbreak.trader import load_params
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    p0 = load_params(market="JP")
    base = breakout_frames(D, mem, p0)
    col = {t: j for j, t in enumerate(D["names"])}
    tops = ["ENGR", "DARK", "ESTAR", "STAR", "GRAVE", "LUR", "B3", "GAP3U", "UPTHR", "BCLX", "BIGR", "HARR", "TWT"]
    say("# K 线形态探索 第 5 轮：现行突破持仓 + 见顶 K 线离场（只用探索期；不是登记的检验）")
    say("现行突破信号（时点 TOPIX 1000 成员）、每只票单独；见顶 K 线出现（且浮盈 ≥ 门槛）→ 下一交易日开盘卖，其余出场照现行（含现行的放量阴线离场）。")
    say("| 离场 | 浮盈门槛 | T1 笔数 / 胜率 / 每笔平均 / 盈亏比 / 持有 | T2 同左 | 全部 |")
    say("|---|---|---|---|---|")
    c = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {s['pf']:.2f} / {s['hold']:.1f} 天"   # noqa: E731
    T = trades_of(base, p0)
    say(f"| 现行 | — | {c(tstat(T, *T1))} | {c(tstat(T, *T2))} | {c(tstat(T))} |")
    for k in tops:
        for gain in (0.0, 5.0):
            ind = {}
            for t, df in base.items():
                j = col[t]
                flag = pd.Series(pat[k][:, j], index=days).reindex(df.index).fillna(False).to_numpy(bool)
                ind[t] = df.assign(climax=df["climax"].to_numpy(bool) | flag) if gain == 0 else df.assign(climax=flag)
            if gain == 0:
                pp = replace(p0, climax_min_gain_pct=-100.0)
                lab = "不限"
            else:
                pp = p0
                lab = "≥ 5%"
            if gain != 0:                                        # 现行的放量阴线离场也保留（门槛 5%）
                ind = {t: df.assign(climax=df["climax"].to_numpy(bool) | base[t]["climax"].to_numpy(bool)) for t, df in ind.items()}
            T = trades_of(ind, pp)
            say(f"| + {k} {K.PATTERNS.get(k, (k,))[0][:14] if k in K.PATTERNS else k} | {lab} | {c(tstat(T, *T1))} | {c(tstat(T, *T2))} | {c(tstat(T))} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_5.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 6 轮：新方法 —— 相似 K 线检索（kNN）与 K 线提升树（T1 学、T2 测） ──────────────────────────
def shape_vectors(P: dict, g: dict, L: int = 10) -> np.ndarray:
    """最近 L 根 K 线：开 / 高 / 低 / 收 ÷ 今天收盘 − 1，再 ÷ ATR%（形状与波动无关），加上 log 量比 → (days, names, 5L)。"""
    C, a1 = P["C"], g["atr1"]
    with np.errstate(invalid="ignore", divide="ignore"):
        unit = a1 / C
        vma = K.sh(K.rolling_mean(P["V"], 20), 1)
        parts = []
        for k in range(L):
            for key in ("O", "H", "L", "C"):
                parts.append((K.sh(P[key], k) / C - 1) / unit)
            parts.append(np.log(np.clip(K.sh(P["V"], k) / vma, 0.05, 20)))
    return np.stack(parts, axis=-1)


def knn_forecast(lib_x: np.ndarray, lib_y: np.ndarray, q: np.ndarray, k: int = 200, chunk: int = 400) -> np.ndarray:
    """欧氏距离最近的 k 个历史形状 → 它们之后的超额平均。"""
    lx = lib_x.astype(np.float32)
    ln = (lx ** 2).sum(1)
    out = np.empty(len(q))
    for i in range(0, len(q), chunk):
        qq = q[i:i + chunk].astype(np.float32)
        d = ln[None, :] - 2 * qq @ lx.T
        idx = np.argpartition(d, k, axis=1)[:, :k]
        out[i:i + chunk] = lib_y[idx].mean(1)
    return out


def round6() -> int:
    from qbreak import ml
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    t = K.targets(P, horizons=(5, 10))
    X10 = K.excess(t["f10"], mem & g["ok"])
    base = g["ok"] & mem & np.isfinite(X10)
    r1 = np.asarray((days >= pd.Timestamp(T1[0])) & (days < pd.Timestamp(T1[1])))[:, None]
    r2 = np.asarray((days >= pd.Timestamp(T2[0])) & (days < pd.Timestamp(T2[1])))[:, None]
    rng = np.random.default_rng(3)
    say("# K 线形态探索 第 6 轮：新方法（只用探索期：T1 2017〜2019 学、T2 2020〜2021 测；不是登记的检验）")
    # ── 相似 K 线（kNN） ──
    V = shape_vectors(P, g)
    okv = base & np.isfinite(V).all(-1)
    li = np.argwhere(okv & r1)
    li = li[rng.choice(len(li), min(150_000, len(li)), replace=False)]
    qi = np.argwhere(okv & r2)
    qi = qi[rng.choice(len(qi), min(60_000, len(qi)), replace=False)]
    lib_x, lib_y = V[li[:, 0], li[:, 1]], X10[li[:, 0], li[:, 1]]
    mu, sd = lib_x.mean(0), lib_x.std(0) + 1e-9
    fc = knn_forecast((lib_x - mu) / sd, lib_y, (V[qi[:, 0], qi[:, 1]] - mu) / sd)
    real = X10[qi[:, 0], qi[:, 1]]
    ic = ml.ic_by_date(fc, real, qi[:, 0])
    dec = pd.qcut(pd.Series(fc).rank(method="first"), 10, labels=False)
    say(f"\n## 相似 K 线检索（最近 10 根 K 线 + 量，15 万个 T1 历史形状，每个查询取最像的 200 个）")
    say(f"T2 抽 6 万个（票 × 日）：每天秩相关 IC 平均 {ic.mean():+.4f}（天数 {len(ic)}）；预测最低 / 最高十分之一的实际 10 日超额 "
        f"{real[dec == 0].mean() * 100:+.2f}% / {real[dec == 9].mean() * 100:+.2f}%")
    # ── K 线提升树 ──
    F = cont_features(P, g, x, extra)
    names_f = list(F) + [f"P_{k}" for k in pat] + ["lt_up", "above200"]
    def mat(ix):
        cols = [F[k][ix[:, 0], ix[:, 1]] for k in F] + [pat[k][ix[:, 0], ix[:, 1]].astype(float) for k in pat]
        cols += [x["lt_up"][ix[:, 0], ix[:, 1]].astype(float), x["above200"][ix[:, 0], ix[:, 1]].astype(float)]
        return np.column_stack(cols)
    tr = np.argwhere(base & r1)
    tr = tr[rng.choice(len(tr), min(300_000, len(tr)), replace=False)]
    te = np.argwhere(base & r2)
    Xtr, ytr = mat(tr), ml.rank_by_date(X10[tr[:, 0], tr[:, 1]], tr[:, 0])
    m = ml.HistGBM(n_trees=200, lr=0.05, depth=3, min_leaf=500, seed=1).fit(Xtr, ytr)
    pte = m.predict(mat(te))
    rte = X10[te[:, 0], te[:, 1]]
    ic2 = ml.ic_by_date(pte, rte, te[:, 0])
    dfp = pd.DataFrame({"d": te[:, 0], "p": pte, "y": rte, "raw": t["f10"][te[:, 0], te[:, 1]]})
    top5 = dfp.sort_values("p", ascending=False).groupby("d").head(5)
    dec2 = pd.qcut(dfp["p"].rank(method="first"), 10, labels=False)
    say(f"\n## K 线提升树（{len(names_f)} 个特征：15 个连续 K 线特征 + {len(pat)} 个形态 + 趋势；T1 抽 30 万行学，T2 全部测）")
    say(f"T2 每天秩相关 IC 平均 {ic2.mean():+.4f}；最低 / 最高十分之一的 10 日超额 {dfp['y'][dec2 == 0].mean() * 100:+.2f}% / "
        f"{dfp['y'][dec2 == 9].mean() * 100:+.2f}%；每天分数最高的 5 只：10 日超额 {top5['y'].mean() * 100:+.2f}%、"
        f"原始收益 − 成本 {((top5['raw'] - COST).mean()) * 100:+.2f}%、净胜率 {(top5['raw'] > COST).mean() * 100:.1f}%")
    imp = []
    for j, nm in enumerate(names_f):
        Xp = mat(te[: 200_000]).copy()
        base_ic = ml.ic_by_date(m.predict(Xp), rte[:200_000], te[:200_000, 0]).mean()
        Xp[:, j] = rng.permutation(Xp[:, j])
        imp.append((nm, base_ic - ml.ic_by_date(m.predict(Xp), rte[:200_000], te[:200_000, 0]).mean()))
        if j >= 20:
            break
    say("置换重要性（前 21 个特征，打乱后 T2 IC 掉多少）：" + "、".join(f"{a} {b:+.4f}" for a, b in sorted(imp, key=lambda z: -z[1])[:10]))
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_6.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 7 轮：押し目的稳健性（参数附近、每年、扎堆）与指値买入 ──────────────────────────
def pb_mask(P: dict, g: dict, x: dict, drop: float = 0.10, v5max: float = 0.85, sma_n: int = 150, no_new_low: bool = True) -> np.ndarray:
    """押し目：5 日跌 ≥ drop、最近 5 天均量 ≤ 之前 20 天的 v5max 倍、收盘在上升的 sma_n 日线上（20 天前比较）、（可选）没跌破前 20 天最低。"""
    C, V = P["C"], P["V"]
    sma = K.rolling_mean(C, sma_n)
    with np.errstate(invalid="ignore", divide="ignore"):
        vr5 = K.rolling_mean(V, 5) / K.sh(K.rolling_mean(V, 20), 5)
        m = (x["ret5"] <= -drop) & (vr5 <= v5max) & (C > sma) & (sma > K.sh(sma, 20))
        if no_new_low:
            m &= ~x["lo20_poke"]
    return np.asarray(m, bool) & g["ok"]


def round7() -> int:
    from dataclasses import replace
    from qbreak.trader import load_params
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    p10 = replace(load_params(market="JP"), max_hold_days=10)
    idx = [j for j in range(len(D["names"])) if mem[:, j].any()]
    none = np.zeros_like(P["C"], bool)
    c = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {s['pf']:.2f}"   # noqa: E731
    say("# K 线形态探索 第 7 轮：押し目的稳健性与指値买入（只用探索期；不是登记的检验）")
    say("逐笔：每只票单独、第二天开盘买、持有 10 个交易日（7% 止损等照现行）、扣成本。格式 = 笔数 / 胜率 / 每笔平均净收益 / 盈亏比。")
    say("\n## 参数附近（中心 = 跌 ≥ 10%、v5 ≤ 0.85、150 日线、没破 20 日低）")
    say("| 变化 | T1 | T2 |")
    say("|---|---|---|")
    grid = [("中心", {}), ("跌 ≥ 9%", {"drop": 0.09}), ("跌 ≥ 11%", {"drop": 0.11}), ("跌 ≥ 12%", {"drop": 0.12}),
            ("v5 ≤ 0.75", {"v5max": 0.75}), ("v5 ≤ 0.95", {"v5max": 0.95}), ("v5 ≤ 1.05（几乎不限量）", {"v5max": 1.05}),
            ("120 日线", {"sma_n": 120}), ("200 日线", {"sma_n": 200}), ("不要求没破 20 日低", {"no_new_low": False})]
    keep = {}
    for lab, kw in grid:
        em = pb_mask(P, g, x, **kw)
        T = trades_of(frames(D, em, none, mem, idx), p10)
        keep[lab] = T
        say(f"| {lab} | {c(tstat(T, *T1))} | {c(tstat(T, *T2))} |")
    T = keep["中心"]
    say("\n## 中心定义的每年（信号年份）")
    say("| 年 | 笔数 / 胜率 / 每笔平均 / 盈亏比 |")
    say("|---|---|")
    for y in range(2017, 2022):
        say(f"| {y} | {c(tstat(T, f'{y}-01-01', f'{y + 1}-01-01'))} |")
    em = pb_mask(P, g, x)
    per_day = (em & mem).sum(1)
    nz = per_day[per_day > 0]
    say(f"\n扎堆：有信号的日子 {len(nz)} 天，平均每天 {nz.mean():.1f} 个，最多 {nz.max()} 个；信号最多的 5 天占全部信号的 "
        f"{np.sort(nz)[-5:].sum() / nz.sum() * 100:.1f}%")
    # ── 指値买入（近似）：第二天以 今天收盘 × (1 − k × ATR%) 挂买单，最低价碰到才成交（成交价 = min(开盘, 指値)），之后同一个卖出 ──
    say("\n## 指値买入（近似：只改买入价，卖出日与卖出价不变；没成交的这笔不做）")
    say("| 买点 | 挂单 | T1 成交率 / 胜率 / 每笔平均 | T2 同左 |")
    say("|---|---|---|---|")
    a1 = K.atr(P["H"], P["L"], P["C"])
    col = {t: j for j, t in enumerate(D["names"])}
    di = {d: i for i, d in enumerate(days)}
    from qbreak.config import ExecConfig
    slip = ExecConfig.for_market("JP", "tachibana").slippage_pct / 100
    base_tr = {"押し目（中心）": keep["中心"], "现行突破": trades_of(breakout_frames(D, mem, load_params(market="JP")), load_params(market="JP"))}
    for bn, T in base_tr.items():
        for k in (0.0, 0.3, 0.6):
            rows = {"T1": [], "T2": []}
            for r in T.itertuples(index=False):
                j, i = col[r.ticker], di.get(pd.Timestamp(r.entry_date))
                if i is None or i < 1:
                    continue
                cl, at = P["C"][i - 1, j], a1[i - 1, j]
                lim = cl * (1 - k * at / cl) if k > 0 else np.inf
                o, lo_ = P["O"][i, j], P["L"][i, j]
                if k > 0 and not (lo_ <= lim):
                    fill = None
                else:
                    fill = min(o, lim) if k > 0 else o
                key = "T1" if pd.Timestamp(r.sig_date) < pd.Timestamp(T2[0]) else "T2"
                if fill is None:
                    rows[key].append(np.nan)
                else:
                    ex_px = r.exit_px if hasattr(r, "exit_px") else np.nan
                    rows[key].append((ex_px / (fill * (1 + slip)) - 1) * 100 - (r.ret_pct - r.net) if np.isfinite(ex_px) else r.net)
            cells = []
            for key in ("T1", "T2"):
                v = np.array(rows[key], float)
                f_ = np.isfinite(v)
                cells.append(f"{f_.mean() * 100:.0f}% / {(v[f_] > 0).mean() * 100:.1f}% / {v[f_].mean():+.2f}%" if f_.any() else "—")
            say(f"| {bn} | {'开盘（现行）' if k == 0 else f'收盘 − {k} ATR'} | {cells[0]} | {cells[1]} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_7.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 8 轮：放进组合（S0C2、时点 TOPIX 500，只跑到 2021-12-31） ──────────────────────────
def round8() -> int:
    from dataclasses import replace
    from qbreak.trader import load_params
    import candle_portfolio as CP
    t0 = time.time()
    D = load_t()
    days, P, names = D["days"], D["P"], D["names"]
    mem1 = D["mem"]["U1"]
    g, x, pat, extra = features(P)
    p0 = load_params(market="JP")
    bo = breakout_frames(D, mem1, p0)
    col = {t: j for j, t in enumerate(names)}
    pbm = pb_mask(P, g, x)
    u1 = [col[t] for t in bo]
    closes = pd.DataFrame(P["C"][:, u1], index=days, columns=list(bo))
    ratio = {t: pd.Series(D["ratio"][:, col[t]], index=days) for t in bo}
    windows = {"T": (TRADE_START_T, "2022-01-01"), "T1": ("2017-01-01", "2020-01-01"), "T2": ("2020-01-01", "2022-01-01")}
    run = CP.make_runner(closes, ratio, windows, end=T_END)
    flag = lambda k, t, df: pd.Series(k[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool)   # noqa: E731
    pbf = {t: flag(pbm, t, df) & pd.Series(mem1[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool) for t, df in bo.items()}
    var = {}
    var["现行（突破）"] = (bo, p0, None)
    var["只做押し目（持有 10 日）"] = ({t: df.assign(entry=pbf[t], dead_cross=False) for t, df in bo.items()}, replace(p0, max_hold_days=10), None)
    mix = {t: df.assign(entry=df["entry"].to_numpy(bool) | pbf[t]) for t, df in bo.items()}
    pbset = {t: set(df.index[pbf[t] & ~bo[t]["entry"].to_numpy(bool)]) for t, df in bo.items()}
    var["突破 + 押し目（押し目仓位持有 10 日）"] = (mix, p0, pbset)
    gr = {t: df.assign(climax=df["climax"].to_numpy(bool) | flag(pat["GRAVE"], t, df) | flag(pat["ENGR"], t, df)) for t, df in bo.items()}
    var["突破 + 塔婆 / 陰の包み線 离场"] = (gr, replace(p0, climax_min_gain_pct=-100.0), None)
    var["只有 1655（个股不买）"] = ({t: df.assign(entry=False) for t, df in bo.items()}, p0, None)
    say("# K 线形态探索 第 8 轮：放进组合（S0C2 = var/sim.json 同一套设定；时点 TOPIX 500；只跑到 2021-12-31；不是登记的检验）")
    say("| 方案 | 2017〜2021 年化 / 回撤 / Calmar | T1 Calmar | T2 Calmar | 个股笔数 / 胜率 / 平均持有 |")
    say("|---|---|---|---|---|")
    fc = lambda s: f"{s['cagr']}% / {s['dd']}% / {s['calmar']}"                                          # noqa: E731
    for lab, (ind, pp, pbs) in var.items():
        r = run(ind, pp, pb=pbs)
        say(f"| {lab} | {fc(r['T'])} | {r['T1']['calmar']} | {r['T2']['calmar']} | {r['trades']} / {r.get('win')}% / {r.get('hold')} 天 |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_8.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


TRADE_START_T = "2017-01-04"


def round12() -> int:
    """搭配：只做押し目 / 突破 + 押し目（押し目不受新仓倍数限制）× 开盘买 / 指値（收盘 − 0.3 ATR）（只跑到 2021-12-31）。"""
    from dataclasses import replace
    from qbreak.trader import load_params
    import candle_portfolio as CP
    t0 = time.time()
    D = load_t()
    days, P, names = D["days"], D["P"], D["names"]
    mem1, mem2 = D["mem"]["U1"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    p0 = load_params(market="JP")
    bo2 = breakout_frames(D, mem2, p0)
    col = {t: j for j, t in enumerate(names)}
    ser = lambda a, t, df: pd.Series(a[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool)   # noqa: E731
    in1 = {t: ser(mem1, t, df) for t, df in bo2.items()}
    in2 = {t: ser(mem2, t, df) for t, df in bo2.items()}
    pbm = pb_mask(P, g, x)
    pbf = {t: ser(pbm, t, df) & in2[t] for t, df in bo2.items()}
    brk1 = {t: df["entry"].to_numpy(bool) & in1[t] for t, df in bo2.items()}
    u2 = [col[t] for t in bo2]
    closes = pd.DataFrame(P["C"][:, u2], index=days, columns=list(bo2))
    ratio = {t: pd.Series(D["ratio"][:, col[t]], index=days) for t in bo2}
    windows = {"T": (TRADE_START_T, "2022-01-01"), "T1": ("2017-01-01", "2020-01-01"), "T2": ("2020-01-01", "2022-01-01")}
    run = CP.make_runner(closes, ratio, windows, end=T_END)
    pb_all = {t: set(df.index[pbf[t]]) for t, df in bo2.items()}
    pb_mix = {t: set(df.index[pbf[t] & ~brk1[t]]) for t, df in bo2.items()}
    only = {t: df.assign(entry=pbf[t], dead_cross=False) for t, df in bo2.items()}
    mix = {t: df.assign(entry=brk1[t] | pbf[t]) for t, df in bo2.items()}
    say("# K 线形态探索 第 12 轮：搭配与指値（S0C2；只跑到 2021-12-31；不是登记的检验）")
    say("| 方案 | 2017〜2021 年化 / 回撤 / Calmar | T1 Calmar | T2 Calmar | 个股笔数 / 胜率 / 平均持有 | 指値没碰到 |")
    say("|---|---|---|---|---|---|")
    fc = lambda s: f"{s['cagr']}% / {s['dd']}% / {s['calmar']}"                                          # noqa: E731
    for lab, ind, pb, kw in (("只做押し目、开盘买", only, pb_all, {"pb_free": True}),
                             ("只做押し目、指値 收盘 − 0.3 ATR", only, pb_all, {"pb_free": True, "limit_k": 0.3}),
                             ("突破 + 押し目（押し目不受倍数限制）、开盘买", mix, pb_mix, {"pb_free": True}),
                             ("突破 + 押し目（押し目不受倍数限制）、押し目指値 0.3 ATR", mix, pb_mix, {"pb_free": True, "limit_k": 0.3})):
        r = run(ind, p0, pb=pb, hold_pb=10, **kw)
        say(f"| {lab} | {fc(r['T'])} | {r['T1']['calmar']} | {r['T2']['calmar']} | {r['trades']} / {r.get('win')}% / {r.get('hold')} 天 | "
            f"{r['skipped'].get('limit_miss', 0)} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_12.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


# ────────────────────────── 第 11 轮：多根 K 线的「图形」（二番底 / 逆三尊 买、三尊天井 / 二重天井 卖） ──────────────────────────
def swings(H: np.ndarray, L: np.ndarray, m: int = 5) -> tuple[list, list]:
    """一只票的波段高低点：第 k 天是前后各 m 天里最高（低）→ 波段高（低）点；要到第 k + m 天收盘才确认（不偷看）。"""
    n = len(H)
    hi, lo = [], []
    for k in range(m, n - m):
        wh, wl = H[k - m:k + m + 1], L[k - m:k + m + 1]
        if np.isfinite(H[k]) and H[k] == np.nanmax(wh) and np.nanargmax(wh) == m:
            hi.append(k)
        if np.isfinite(L[k]) and L[k] == np.nanmin(wl) and np.nanargmin(wl) == m:
            lo.append(k)
    return hi, lo


def chart_patterns(P: dict, m: int = 5, look: int = 20) -> dict[str, np.ndarray]:
    """图形的触发日（突破 / 跌破颈线的第一天，而且在最后一个波段点确认之后 look 天之内）：
    DB 二番底：相邻两个波段低点相距 10〜60 天、低点相差 ≤ 3%、中间最高 ≥ 低点 × 1.08 → 收盘突破中间最高（颈线）
    IHS 逆三尊：相邻三个波段低点、中间最低、两肩相差 ≤ 5% → 收盘突破两段反弹高点中较高的（颈线）
    HS 三尊天井：相邻三个波段高点、中间最高、两肩相差 ≤ 5% → 收盘跌破两段回落低点中较低的（颈线）
    DT 二重天井：相邻两个波段高点相距 10〜60 天、相差 ≤ 3%、中间最低 ≤ 高点 × 0.92 → 收盘跌破中间最低（颈线）"""
    H, L, C = P["H"], P["L"], P["C"]
    n, nm = C.shape
    out = {k: np.zeros((n, nm), bool) for k in ("DB", "IHS", "HS", "DT")}

    def trigger(name, j, start, level, up):
        for t in range(start, min(n, start + look)):
            c, c1 = C[t, j], C[t - 1, j]
            if not np.isfinite(c):
                continue
            if (up and c > level and not (c1 > level)) or (not up and c < level and not (c1 < level)):
                out[name][t, j] = True
                return
    for j in range(nm):
        h, l_ = H[:, j], L[:, j]
        if np.isfinite(C[:, j]).sum() < 100:
            continue
        hi, lo = swings(h, l_, m)
        for a, b in zip(lo, lo[1:]):
            if 10 <= b - a <= 60 and abs(l_[b] / l_[a] - 1) <= 0.03:
                neck = np.nanmax(h[a:b + 1])
                if neck >= max(l_[a], l_[b]) * 1.08:
                    trigger("DB", j, b + m, neck, True)
        for a, b, c_ in zip(lo, lo[1:], lo[2:]):
            if l_[b] < l_[a] and l_[b] < l_[c_] and abs(l_[c_] / l_[a] - 1) <= 0.05 and c_ - a <= 120:
                neck = max(np.nanmax(h[a:b + 1]), np.nanmax(h[b:c_ + 1]))
                trigger("IHS", j, c_ + m, neck, True)
        for a, b, c_ in zip(hi, hi[1:], hi[2:]):
            if h[b] > h[a] and h[b] > h[c_] and abs(h[c_] / h[a] - 1) <= 0.05 and c_ - a <= 120:
                neck = min(np.nanmin(l_[a:b + 1]), np.nanmin(l_[b:c_ + 1]))
                trigger("HS", j, c_ + m, neck, False)
        for a, b in zip(hi, hi[1:]):
            if 10 <= b - a <= 60 and abs(h[b] / h[a] - 1) <= 0.03:
                neck = np.nanmin(l_[a:b + 1])
                if neck <= min(h[a], h[b]) * 0.92:
                    trigger("DT", j, b + m, neck, False)
    return out


def round11() -> int:
    t0 = time.time()
    D = load_t()
    days, P, mem = D["days"], D["P"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    t = K.targets(P, horizons=(5, 10, 20))
    base = g["ok"] & mem & np.asarray(days >= pd.Timestamp(T1[0]))[:, None]
    X = {f"x{h}": K.excess(t[f"f{h}"], mem & g["ok"]) for h in (5, 10, 20)}
    mids = (days.year * 100 + days.month).to_numpy()
    cp = chart_patterns(P)
    masks = {}
    for k, v in cp.items():
        masks[f"{k}|ALL"] = v
        masks[f"{k}|VS"] = v & x["vsurge"]
        masks[f"{k}|LTUP"] = v & x["lt_up"]
    df = scan(masks, X, t["f10"], mids, days, base)
    df["sel"] = pick(df, min_n=100)
    lab = {"DB": "二番底（W 底）→ 突破颈线（传统：买）", "IHS": "逆三尊 → 突破颈线（传统：买）", "HS": "三尊天井 → 跌破颈线（传统：卖）",
           "DT": "二重天井 → 跌破颈线（传统：卖）"}
    say("# K 线形态探索 第 11 轮：多根 K 线的图形（只用探索期；不是登记的检验）")
    say("波段高低点 = 前后各 5 天里最高 / 最低（第 5 天才确认，不偷看）；触发 = 确认后 20 天内第一次收盘突破 / 跌破颈线；情境 VS = 当天放量 ≥ 1.5 倍、"
        "LTUP = 在上升的 150 日线上。挑选条件同第 1 轮（次数门槛 100）。")
    say("| 图形 | 情境 | 次数 | 5 日超额 | 10 日超额（95% 区间） | T1 / T2 | 20 日超额 | 10 日净胜率 | 通过 |")
    say("|---|---|---|---|---|---|---|---|---|")
    f = lambda v: "—" if not np.isfinite(v) else f"{v * 100:+.2f}%"                                 # noqa: E731
    for r in df.itertuples(index=False):
        pn, cn = r.name.split("|")
        say(f"| {lab[pn]} | {cn} | {r.x10_n:,} | {f(r.x5)} | {f(r.x10)}（{f(r.x10_lo)}〜{f(r.x10_hi)}） | {f(r.x10_t1)} / {f(r.x10_t2)} | "
            f"{f(r.x20)} | {r.win10 * 100:.1f}% | {'✓' if r.sel else ''} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_11.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    np.savez(paths.sub("cache") / "candle_chart_patterns_T.npz", **cp)
    return 0


def round10() -> int:
    """只做押し目（TOPIX 1000、不受新仓倍数限制）的卖法：持有 5 / 10 / 20 日、反弹到 5 日线（最多 10 日）（只跑到 2021-12-31）。"""
    from dataclasses import replace
    from qbreak.trader import load_params
    import candle_portfolio as CP
    t0 = time.time()
    D = load_t()
    days, P, names = D["days"], D["P"], D["names"]
    mem2 = D["mem"]["U2"]
    g, x, pat, extra = features(P)
    p0 = load_params(market="JP")
    bo2 = breakout_frames(D, mem2, p0)
    col = {t: j for j, t in enumerate(names)}
    in2 = {t: pd.Series(mem2[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool) for t, df in bo2.items()}
    pbm = pb_mask(P, g, x)
    pbf = {t: pd.Series(pbm[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool) & in2[t] for t, df in bo2.items()}
    with np.errstate(invalid="ignore"):
        ab5 = np.asarray(P["C"] > K.rolling_mean(P["C"], 5), bool)
    a5 = {t: pd.Series(ab5[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool) for t, df in bo2.items()}
    u2 = [col[t] for t in bo2]
    closes = pd.DataFrame(P["C"][:, u2], index=days, columns=list(bo2))
    ratio = {t: pd.Series(D["ratio"][:, col[t]], index=days) for t in bo2}
    windows = {"T": (TRADE_START_T, "2022-01-01"), "T1": ("2017-01-01", "2020-01-01"), "T2": ("2020-01-01", "2022-01-01")}
    run = CP.make_runner(closes, ratio, windows, end=T_END)
    say("# K 线形态探索 第 10 轮：只做押し目（TOPIX 1000、不受新仓倍数限制）的卖法（只跑到 2021-12-31；不是登记的检验）")
    say("| 卖法 | 2017〜2021 年化 / 回撤 / Calmar | T1 Calmar | T2 Calmar | 个股笔数 / 胜率 / 平均持有 |")
    say("|---|---|---|---|---|")
    fc = lambda s: f"{s['cagr']}% / {s['dd']}% / {s['calmar']}"                                          # noqa: E731
    for lab, dead, hold in (("持有 5 日", False, 5), ("持有 10 日", False, 10), ("持有 20 日", False, 20), ("反弹到 5 日线就卖（最多 10 日）", True, 10)):
        ind = {t: df.assign(entry=pbf[t], dead_cross=(a5[t] if dead else False)) for t, df in bo2.items()}
        r = run(ind, replace(p0, max_hold_days=hold), mult=False)
        say(f"| {lab} | {fc(r['T'])} | {r['T1']['calmar']} | {r['T2']['calmar']} | {r['trades']} / {r.get('win')}% / {r.get('hold')} 天 |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_10.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


def round9() -> int:
    """押し目放到时点 TOPIX 1000（中型股才有足够的信号）：几种搭配（只跑到 2021-12-31）。"""
    from dataclasses import replace
    from qbreak.trader import load_params
    import candle_portfolio as CP
    t0 = time.time()
    D = load_t()
    days, P, names = D["days"], D["P"], D["names"]
    mem1, mem2 = D["mem"]["U1"], D["mem"]["U2"]
    g, x, pat, extra = features(P)
    p0 = load_params(market="JP")
    bo2 = breakout_frames(D, mem2, p0)                                     # U2 全部的指标表（entry 先按 U2 成员）
    col = {t: j for j, t in enumerate(names)}
    in1 = {t: pd.Series(mem1[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool) for t, df in bo2.items()}
    in2 = {t: pd.Series(mem2[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool) for t, df in bo2.items()}
    pbm = pb_mask(P, g, x)
    pbf = {t: pd.Series(pbm[:, col[t]], index=days).reindex(df.index).fillna(False).to_numpy(bool) & in2[t] for t, df in bo2.items()}
    brk1 = {t: df["entry"].to_numpy(bool) & in1[t] for t, df in bo2.items()}           # 突破只在 U1 成员
    u2 = [col[t] for t in bo2]
    closes = pd.DataFrame(P["C"][:, u2], index=days, columns=list(bo2))
    ratio = {t: pd.Series(D["ratio"][:, col[t]], index=days) for t in bo2}
    windows = {"T": (TRADE_START_T, "2022-01-01"), "T1": ("2017-01-01", "2020-01-01"), "T2": ("2020-01-01", "2022-01-01")}
    run = CP.make_runner(closes, ratio, windows, end=T_END)
    p10 = replace(p0, max_hold_days=10)
    pbset = {t: set(df.index[pbf[t] & ~brk1[t]]) for t, df in bo2.items()}
    var = {
        "现行突破（TOPIX 500 成员）": ({t: df.assign(entry=brk1[t]) for t, df in bo2.items()}, p0, None, True),
        "只做押し目（TOPIX 1000）": ({t: df.assign(entry=pbf[t], dead_cross=False) for t, df in bo2.items()}, p10, None, True),
        "只做押し目（TOPIX 1000，不受新仓倍数限制）": ({t: df.assign(entry=pbf[t], dead_cross=False) for t, df in bo2.items()}, p10, None, False),
        "突破（TOPIX 500）+ 押し目（TOPIX 1000）": ({t: df.assign(entry=brk1[t] | pbf[t]) for t, df in bo2.items()}, p0, pbset, True),
        "只有 1655": ({t: df.assign(entry=False) for t, df in bo2.items()}, p0, None, True),
    }
    say("# K 线形态探索 第 9 轮：押し目放到时点 TOPIX 1000（S0C2；只跑到 2021-12-31；不是登记的检验）")
    say("| 方案 | 2017〜2021 年化 / 回撤 / Calmar | T1 Calmar | T2 Calmar | 个股笔数 / 胜率 / 平均持有 | 每年 |")
    say("|---|---|---|---|---|---|")
    fc = lambda s: f"{s['cagr']}% / {s['dd']}% / {s['calmar']}"                                          # noqa: E731
    for lab, (ind, pp, pbs, mu) in var.items():
        r = run(ind, pp, pb=pbs, mult=mu)
        say(f"| {lab} | {fc(r['T'])} | {r['T1']['calmar']} | {r['T2']['calmar']} | {r['trades']} / {r.get('win')}% / {r.get('hold')} 天 | "
            + "、".join(f"{y} {v:+.1f}" for y, v in r["years"].items()) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    (paths.out_dir() / "candle_explore_9.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "1"
    raise SystemExit({"1": round1, "2": round2, "3": round3, "4": round4, "5": round5, "6": round6, "7": round7, "8": round8, "9": round9, "10": round10, "11": round11, "12": round12}[which]())
