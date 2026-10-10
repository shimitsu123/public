"""w2_forward.py — W2 前向记录的统计与判定（2026-09-27 登记：scripts/score_forward.py 第八节、scripts/w2_forward_all.py）。

两份检验共用：已平仓的信号按「W2 保留 / 挡掉」分两组 → 笔数 / 胜率 / 每笔；差 = 保留 − 挡掉的每笔平均净收益（pp），
区间 = 按信号月聚类的自助法；失效警报 =「挡掉 − 保留」的 95% 区间下限 > 0（= 保留 − 挡掉的 95% 区间上限 < 0）；
证实 =「保留 − 挡掉」的 99% 区间下限 > 0。判定时点（每年的日期 / 已平仓笔数）由调用方给，做过的不再做。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

W2_CUT = 1.0                                      # 门槛在登记时写定，不跟着参数变
BOOT_N, SEED = 2000, 20260927
JUDGE_DATES = ("2027-09-28", "2028-09-28", "2029-09-28", "2030-09-28", "2031-09-28")


def keep_flag(w5v) -> np.ndarray:
    """周线量比 → W2 是否保留：< 门槛 → 0；≥ 门槛或缺值 → 1（与实盘 compute_indicators 相同：缺值不过滤）。"""
    v = np.asarray(w5v, float)
    return np.where(np.isfinite(v) & (v < W2_CUT), 0, 1).astype(int)


def stat(net) -> dict:
    x = np.asarray(net, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0}
    pos, neg = x[x > 0].sum(), -x[x < 0].sum()
    return {"n": int(len(x)), "win": round(float((x > 0).mean() * 100), 2), "mean": round(float(x.mean()), 3),
            "pf": round(float(pos / neg), 3) if neg > 0 else None}


def boot_diff(C: pd.DataFrame, keep_col: str = "w2_keep", net_col: str = "net", date_col: str = "date",
              n: int = BOOT_N, seed: int = SEED) -> np.ndarray:
    """按信号月聚类的自助法：每次抽月份（有放回）→ 保留组平均 − 挡掉组平均；某一组抽空 → NaN。"""
    if not len(C):
        return np.full(n, np.nan)
    mon = pd.to_datetime(C[date_col]).dt.to_period("M").to_numpy()
    groups = [np.flatnonzero(mon == m) for m in pd.unique(mon)]
    k = C[keep_col].to_numpy(float)
    y = C[net_col].to_numpy(float)
    rng = np.random.default_rng(seed)
    out = np.full(n, np.nan)
    for b in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        kk, yy = k[idx], y[idx]
        a, d = yy[kk == 1], yy[kk == 0]
        if len(a) and len(d):
            out[b] = a.mean() - d.mean()
    return out


def evaluate(C: pd.DataFrame, keep_col: str = "w2_keep", net_col: str = "net", date_col: str = "date",
             n: int = BOOT_N, seed: int = SEED) -> dict:
    """已平仓的信号（有 keep_col 的）→ 两组统计、差与区间。"""
    C = C[np.isfinite(pd.to_numeric(C[keep_col], errors="coerce").to_numpy(float))] if keep_col in C.columns else C.iloc[0:0]
    kv = C[keep_col].to_numpy(float) if len(C) else np.array([])
    keep, drop = stat(C.loc[kv == 1, net_col]) if len(C) else {"n": 0}, stat(C.loc[kv == 0, net_col]) if len(C) else {"n": 0}
    out = {"n": int(len(C)), "keep": keep, "drop": drop,
           "diff": round(keep["mean"] - drop["mean"], 3) if keep["n"] and drop["n"] else None, "months": 0}
    if keep["n"] and drop["n"]:
        B = boot_diff(C, keep_col, net_col, date_col, n, seed)
        ok = B[np.isfinite(B)]
        if len(ok):
            q = lambda p: round(float(np.percentile(ok, p)), 3)                                       # noqa: E731
            out.update({"lo95": q(2.5), "hi95": q(97.5), "lo99": q(0.5), "hi99": q(99.5)})
        out["months"] = int(pd.to_datetime(C[date_col]).dt.to_period("M").nunique())
    return out


def alarm(ev: dict) -> bool:
    """失效警报：挡掉 − 保留的 95% 区间下限 > 0（= 保留 − 挡掉的 95% 区间上限 < 0）。"""
    return ev.get("hi95") is not None and ev["hi95"] < 0


def confirmed(ev: dict) -> bool:
    """证实：保留 − 挡掉的 99% 区间下限 > 0。"""
    return ev.get("lo99") is not None and ev["lo99"] > 0


def due_date(today, judge_dates=JUDGE_DATES, done: set[str] | None = None) -> str | None:
    """每年一次的判定：今天已经到达、还没判定过的最晚的那个日期（错过的早年份不补判）；没有 → None。"""
    t = pd.Timestamp(today)
    reached = [d for d in judge_dates if pd.Timestamp(d) <= t]
    if not reached:
        return None
    d = reached[-1]
    return None if done and d in done else d


def due_checkpoint(closed: int, checkpoints, done: set[int] | None = None) -> int | None:
    """已平仓笔数第一次达到的判定时点（取已达到的最大那个；做过的不再做）。"""
    cp = max([c for c in checkpoints if closed >= c], default=None)
    return None if cp is None or (done and cp in done) else cp


def history_done(hist: pd.DataFrame, scope: str, col: str) -> set:
    """历史记录里某个 scope 已判定过的值（例：w2_year / checkpoint）。"""
    if hist is None or hist.empty or col not in hist.columns or "scope" not in hist.columns:
        return set()
    v = hist.loc[hist["scope"] == scope, col].dropna()
    return {int(x) if col == "checkpoint" else str(x) for x in v}


def verdict_lines(ev: dict, alarm_for: str | None, confirm_for: str | None) -> list[str]:
    """判定的文字：alarm_for / confirm_for = 这次判定的名目（例「2027-09-28 这一年」「已平仓第一次达到 400 笔」）；None = 这次不判定。"""
    out = []
    no_ci = "lo95" not in ev
    if alarm_for:
        out.append(f"失效警报（{alarm_for}）：" + ("算不出区间（有一组没有已平仓的信号）→ 不成立" if no_ci else
                                               "**成立 → 提议关掉 W2**（用户在对话里确认才改）" if alarm(ev) else
                                               f"不成立（保留 − 挡掉的 95% 区间 {ev['lo95']:+.2f}〜{ev['hi95']:+.2f} pp）"))
    if confirm_for:
        out.append(f"证实（{confirm_for}）：" + ("算不出区间（有一组没有已平仓的信号）→ 不成立" if no_ci else
                                            "**成立 = 新数据证实 W2**" if confirmed(ev) else
                                            f"不成立（保留 − 挡掉的 99% 区间 {ev['lo99']:+.2f}〜{ev['hi99']:+.2f} pp）"))
    return out


def summary_line(ev: dict) -> str:
    """一行进度：保留 / 挡掉的笔数、胜率、每笔与差。"""
    k, d = ev.get("keep") or {"n": 0}, ev.get("drop") or {"n": 0}
    f = lambda s: "0 笔" if not s.get("n") else f"{s['n']} 笔 / 胜率 {s['win']:.1f}% / 每笔 {s['mean']:+.2f}%"   # noqa: E731
    diff = "" if ev.get("diff") is None else f"；差 {ev['diff']:+.2f} pp" + (
        f"（95% 区间 {ev['lo95']:+.2f}〜{ev['hi95']:+.2f}，{ev.get('months', 0)} 个月）" if "lo95" in ev else "")
    return f"W2 保留 {f(k)}；挡掉 {f(d)}{diff}"
