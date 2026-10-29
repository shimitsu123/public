"""shape_rotation_study.py — 图形轮动：上个月表现好的那类 K 线形状，下个月是不是还好（2026-10-11 登记；先提交后只运行一次）。

用户（2026-10-11）：「根据现在所有的日経225 的股票图形，按照一段时间的 K 线，每个月差异的演变进行分析，可以更加完善现在的选股算法么」→「做图形轮动研究」。
以前做过、都没通过的（不重复）：起涨 / 起跌点 × 图形（日 / 周 / 月线，全部品种）、选股参数按月重估、按局面选模型（KNN / HMM / 模型动量）、
月K 往上 + 日K / 周K 往下、多周期上涨特征、缩量押し目、周 / 月线脱离均线。没测过的：**形状类型的月度惯性**（哪一类形状正在走强）。

一、形状（每个月末、每只票，只用那天为止的日线；规则事先定、不调；按顺序第一个符合的）：
  S1 急跌后反弹：收盘离 60 日最高 ≤ −15% 且 近 10 日涨幅 > +5%
  S2 上升通道：60 日涨幅 > +10% 且 收盘 > 20 日线 > 60 日线
  S3 下降：60 日涨幅 < −10% 且 收盘 < 20 日线 < 60 日线
  S4 高位整理：收盘离 250 日最高 ≥ −5%（且不是 S2）
  S5 横盘：60 日（最高 ÷ 最低 − 1）< 15%
  S0 其他
二、收益：月末收盘 → 下一个月末收盘（不复权差异按各自数据源的调整后价格）；超额 = 减去当月全部票的等权平均。
  一类在那个月的表现 = 月初（上个月末）属于这一类的票这个月超额的平均（≥ 5 只才算，否则这一类那个月缺）。
三、信息检验（主判定）：每个月 t，各类「上个月的表现」（t−1 月末分类、t−1→t 的超额）vs「下个月的表现」（t 月末分类、t→t+1 的超额）
  → 这个月的秩相关（Spearman = 名次的 Pearson，≥ 4 类有数才算）；IC = 各月的平均。
  样本：E = 2006-10〜2016-09（yfinance，今天的日経225）、J = 2017-01〜2026-09（J-Quants，今天的日経225 U0）。
  **有信息** = E 的 IC > 0 且 J 的 IC > 0 且 J 前后两半（2017-01〜2021-12 / 2022-01〜2026-09）都 > 0 且 E + J 合起来的各月 IC 的 t 检验 p < 0.10（单侧，IC > 0；月数约 230 → p 用正态近似）。
  否则「没有信息」→ 停，不做规则检验（记下结论，不再在这个方向上找）。
四、有信息时（另行登记、只运行一次；这里只写定形状）：只在「信号日所在月初、上个月表现排前一半的形状类」里买突破信号（现行 B3 上加过滤），
  按第六个循环的两关（研究循环规则）判定。
只描述（不参与判定）：各类的平均月数、平均只数、各类下个月超额的平均（看哪类整体好 / 差）、IC 的分布。
事前预期：形状类型的惯性与行业动量 / 模型动量相近（都没通过）→ 大概率「没有信息」。
运行：python scripts/shape_rotation_study.py → var/out/shape_rotation_study.md / .json（只有汇总数字）。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = "shape_rotation_study"
SHAPES = ("S1", "S2", "S3", "S4", "S5", "S0")
NAME = {"S1": "急跌后反弹", "S2": "上升通道", "S3": "下降", "S4": "高位整理", "S5": "横盘", "S0": "其他"}
MIN_N, MIN_CLS = 5, 4
E_WIN, J_WIN = ("2006-10-01", "2016-09-30"), ("2017-01-01", "2026-09-30")
J_HALVES = (("2017-01-01", "2021-12-31"), ("2022-01-01", "2026-09-30"))
P_MAX = 0.10


# ───────────────────────── 规则（纯函数，tests/test_shape_rotation_study.py） ─────────────────────────
def classify(c: np.ndarray) -> str | None:
    """一只票到某天为止的收盘（升序、≥ 250 根有效）→ 形状。"""
    c = c[np.isfinite(c)]
    if len(c) < 250:
        return None
    last = c[-1]
    w60, w250 = c[-60:], c[-250:]
    r60 = last / c[-61] - 1 if len(c) > 60 else np.nan
    r10 = last / c[-11] - 1
    ma20, ma60 = c[-20:].mean(), w60.mean()
    if last / w60.max() - 1 <= -0.15 and r10 > 0.05:
        return "S1"
    if r60 > 0.10 and last > ma20 > ma60:
        return "S2"
    if r60 < -0.10 and last < ma20 < ma60:
        return "S3"
    if last / w250.max() - 1 >= -0.05:
        return "S4"
    if w60.max() / w60.min() - 1 < 0.15:
        return "S5"
    return "S0"


def month_ends(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(days, index=days)
    return pd.DatetimeIndex(s.groupby(days.to_period("M")).max().values)


def panel_stats(C: np.ndarray, days: pd.DatetimeIndex, a: str, b: str) -> pd.DataFrame:
    """C = 收盘宽表（日 × 票）→ 每个月末 t：各类在 t→t+1 的超额平均 perf[t, 类]（t 月末分类），只数 ≥ MIN_N 的类。"""
    me = month_ends(days)
    me = me[(me >= pd.Timestamp(a) - pd.offsets.MonthEnd(2)) & (me <= pd.Timestamp(b))]
    pos = days.get_indexer(me)
    rows = []
    for k in range(len(me) - 1):
        i, i2 = pos[k], pos[k + 1]
        cls = [classify(C[: i + 1, j]) for j in range(C.shape[1])]
        r = C[i2] / C[i] - 1
        ok = np.isfinite(r) & np.array([x is not None for x in cls])
        if ok.sum() < 20:
            continue
        ex = r - np.nanmean(r[ok])
        row = {"month": me[k], "next": me[k + 1]}
        for s in SHAPES:
            m = ok & np.array([x == s for x in cls])
            row[s] = float(np.mean(ex[m])) if m.sum() >= MIN_N else np.nan
            row[f"n_{s}"] = int(m.sum())
        rows.append(row)
    return pd.DataFrame(rows).set_index("month")


def monthly_ic(perf: pd.DataFrame) -> pd.Series:
    """t：上个月的表现（行 t−1：t−1 月末分类、t−1→t）vs 这个月起的表现（行 t：t 月末分类、t→t+1）的秩相关。"""
    out = {}
    P = perf[list(SHAPES)]
    for k in range(1, len(P)):
        prev, nxt = P.iloc[k - 1], P.iloc[k]
        m = prev.notna() & nxt.notna()
        if m.sum() >= MIN_CLS:
            out[P.index[k]] = float(prev[m].rank().corr(nxt[m].rank()))
    return pd.Series(out, dtype=float)


def verdict(ic_e: pd.Series, ic_j: pd.Series) -> dict:
    import math
    h1 = ic_j[(ic_j.index >= pd.Timestamp(J_HALVES[0][0])) & (ic_j.index <= pd.Timestamp(J_HALVES[0][1]))]
    h2 = ic_j[(ic_j.index >= pd.Timestamp(J_HALVES[1][0])) & (ic_j.index <= pd.Timestamp(J_HALVES[1][1]))]
    allv = pd.concat([ic_e, ic_j]).dropna()
    if len(allv) > 2 and allv.std(ddof=1) > 0:                               # 单侧 t 检验；月数多（约 230）→ 用正态近似算 p（不用 scipy）
        tv = allv.mean() / (allv.std(ddof=1) / math.sqrt(len(allv)))
        p = 0.5 * math.erfc(tv / math.sqrt(2))
    else:
        p = None
    m = {"E": ic_e.mean(), "J": ic_j.mean(), "J1": h1.mean(), "J2": h2.mean()}
    ok = all(np.isfinite(v) and v > 0 for v in m.values()) and p is not None and p < P_MAX
    return {"ic": {k: round(float(v), 4) for k, v in m.items()}, "n": {"E": len(ic_e), "J": len(ic_j), "J1": len(h1), "J2": len(h2)},
            "p": None if p is None else round(p, 4), "info": bool(ok)}


# ───────────────────────── 数据 ─────────────────────────
def closes_e() -> tuple[np.ndarray, pd.DatetimeIndex]:
    import leap_confirm as LF
    from qbreak.config import universe
    P, days, nm = LF.yf_panel(list(universe("JP", "broad")), "2004-06-01", E_WIN[1])
    return P["C"], days


def closes_j() -> tuple[np.ndarray, pd.DatetimeIndex]:
    import leap_confirm as LF
    ctx = LF.context("J")
    return ctx["P"]["C"][:, ctx["cols"]], ctx["days"]


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    res = {"study": OUT}
    ic = {}
    for tag, (fn, win) in {"E": (closes_e, E_WIN), "J": (closes_j, J_WIN)}.items():
        C, days = fn()
        perf = panel_stats(C, days, *win)
        perf = perf[(perf.index >= pd.Timestamp(win[0]) - pd.offsets.MonthEnd(1)) & (perf.index <= pd.Timestamp(win[1]))]
        ic[tag] = monthly_ic(perf)
        ic[tag] = ic[tag][(ic[tag].index >= pd.Timestamp(win[0])) & (ic[tag].index <= pd.Timestamp(win[1]))]
        res[tag] = {"months": len(perf), "stocks": int(C.shape[1]),
                    "avg_n": {s: round(float(perf[f"n_{s}"].mean()), 1) for s in SHAPES},
                    "avg_next_excess_pp": {s: round(float(perf[s].mean() * 100), 3) for s in SHAPES},
                    "ic_q": {q: round(float(np.nanpercentile(ic[tag], q)), 3) for q in (25, 50, 75)} if len(ic[tag]) else {}}
        print(f"{tag} 完成（{time.time() - t0:.0f}s）", flush=True)
    res["verdict"] = verdict(ic["E"], ic["J"])
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    v = res["verdict"]
    L = [f"# 图形轮动：上个月表现好的形状类，下个月还好吗（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/shape_rotation_study.py 开头）", "",
         f"**{'有信息 → 另行登记规则检验' if v['info'] else '没有信息 → 停（不做规则检验）'}**：月度 IC 平均 E {v['ic']['E']:+.4f}（{v['n']['E']} 个月）、"
         f"J {v['ic']['J']:+.4f}（{v['n']['J']}）、J 前半 {v['ic']['J1']:+.4f} / 后半 {v['ic']['J2']:+.4f}；E + J 合起来 p = {v['p']}（单侧，要 < {P_MAX}；四个 IC 都要 > 0）", "",
         "只描述：", "", "| 形状 | E 平均只数 | E 下个月超额（pp） | J 平均只数 | J 下个月超额（pp） |", "|---|---|---|---|---|"]
    for s in SHAPES:
        L.append(f"| {s} {NAME[s]} | {res['E']['avg_n'][s]} | {res['E']['avg_next_excess_pp'][s]:+.3f} | {res['J']['avg_n'][s]} | {res['J']['avg_next_excess_pp'][s]:+.3f} |")
    L += ["", f"IC 的四分位：E {res['E']['ic_q']}、J {res['J']['ic_q']}。只研究，不改模拟盘 / 执行器。用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
