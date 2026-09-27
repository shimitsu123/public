"""rw2_explore.py — 探索（2026-09-27；只用 2016-10〜2021-12、日経225 以外、20 天平均成交额 ≥ ¥500 万的突破交易；
2022〜2026 与日経225 完全不看，留给登记后的确认）：W2 看「这只票这周的量 ÷ 它之前 10 周的平均」；整个市场一起放量的周（SQ、暴跌、
指数入替…）这个比值会普遍变高 → 试「相对市场的周量比」RW = 个股周量比 ÷ 全市场周量比（全市场 = 东证一般市场全部股票的売買代金合计，
同一个「最近完成的一周 ÷ 之前 10 周平均」），看它是不是比 W2 更能分出好坏。

数据：allstock_study.train_all 的训练数据（缓存 var/cache/jquants/allstock_train.pkl，不入库）+ 全市场每天的売買代金合计（J-Quants）。
比较：W2（个股周量比 ≥ 1.0）与 RW（门槛取「在探索期保留比例与 W2 相同」的那个值，另报 RW ≥ 1.0）各自保留 / 挡掉的每笔净收益、差，按年。
输出：var/out/rw2_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import allstock_data as AD                                                   # noqa: E402
import lowvol_explore as LX                                                  # noqa: E402
from qbreak import mtf, paths                                                # noqa: E402

LIQ = math.log10(5e6)
EXPLORE = ("2016-10-01", "2021-12-31")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def market_w5v(A: dict) -> pd.Series:
    """全市场（一般市场、当天上市的内国普通股）每天的売買代金合计 → 周量比（最近完成的一周 ÷ 之前 10 周平均；实盘 W2 同一个做法）。"""
    va = np.where(A["listed"] & np.isfinite(A["VA"]), A["VA"], 0.0).sum(axis=1)
    days = A["days"]
    df = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": va}, index=days)
    return mtf.weekly_volume_ratio(df, mtf.live_calendar(days))


def split(T: pd.DataFrame, keep: np.ndarray) -> dict:
    k, d = T[keep], T[~keep]
    st = lambda x: {"n": int(len(x)), "win": float((x["net"] > 0).mean() * 100) if len(x) else None,          # noqa: E731
                    "mean": float(x["net"].mean()) if len(x) else None}
    a, b = st(k), st(d)
    return {"keep": a, "drop": b, "diff": (a["mean"] - b["mean"]) if a["n"] and b["n"] else None, "frac": float(keep.mean()) if len(keep) else None}


def main() -> int:
    import candle_data as CD
    t0 = time.time()
    T = LX.train_table()
    A = AD.load()
    mw = market_w5v(A)
    D = CD.load()
    n225 = {D["names"][j] for j in range(len(D["names"])) if D["mem"]["U0"][:, j].any()}
    X = T[(~T["ticker"].isin(n225)) & (T["lturn"] >= LIQ)].copy()
    X["sig_date"] = pd.to_datetime(X["sig_date"])
    X = X[(X["sig_date"] >= EXPLORE[0]) & (X["sig_date"] <= EXPLORE[1])]
    X["mw"] = mw.reindex(X["sig_date"]).to_numpy()
    X["rw"] = X["w5v"] / X["mw"]
    X["year"] = X["sig_date"].dt.year
    w2 = ~(X["w5v"] < 1.0).to_numpy()
    frac = float(w2.mean())
    cut = float(np.nanquantile(X["rw"], 1 - frac))                           # 保留比例与 W2 相同的 RW 门槛
    rw = ~(X["rw"] < cut).to_numpy()
    rw1 = ~(X["rw"] < 1.0).to_numpy()
    out = {"n": int(len(X)), "frac_w2": frac, "rw_cut": cut, "all": {"W2": split(X, w2), "RW": split(X, rw), "RW1": split(X, rw1)}, "years": {}}
    fa = lambda v, f="{:+.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    say("# 探索：相对市场的周量比（RW）vs W2（2016-10〜2021-12，日経225 以外、成交额 ≥ ¥500 万）")
    say(f"{len(X)} 笔；W2 保留 {frac:.0%}；保留比例相同的 RW 门槛 = {cut:.3f}（另报 RW ≥ 1.0）。全市场周量比的中位数 {float(np.nanmedian(X['mw'])):.2f}。")
    say("\n| 年 | W2 保留 − 挡掉（每笔 pp） | RW（同比例）保留 − 挡掉 | RW ≥ 1.0 保留 − 挡掉 | RW 同比例保留的每笔 − W2 保留的每笔 |")
    say("|---|---|---|---|---|")
    better = 0
    for y, g in X.groupby("year"):
        a = split(g, ~(g["w5v"] < 1.0).to_numpy())
        b = split(g, ~(g["rw"] < cut).to_numpy())
        c = split(g, ~(g["rw"] < 1.0).to_numpy())
        gap = (b["keep"]["mean"] - a["keep"]["mean"]) if b["keep"]["n"] and a["keep"]["n"] else None
        better += int(gap is not None and gap > 0)
        out["years"][int(y)] = {"W2": a, "RW": b, "RW1": c, "gap": gap}
        say(f"| {y} | {fa(a['diff'])} | {fa(b['diff'])} | {fa(c['diff'])} | {fa(gap)} |")
    al = out["all"]
    say(f"| 全期 | {fa(al['W2']['diff'])} | {fa(al['RW']['diff'])} | {fa(al['RW1']['diff'])} | "
        f"{fa((al['RW']['keep']['mean'] or 0) - (al['W2']['keep']['mean'] or 0))} |")
    say(f"\nRW 保留的每笔比 W2 保留的好的年份：{better} / {len(out['years'])}")
    say(f"W2 保留：{al['W2']['keep']['n']} 笔 / 胜率 {fa(al['W2']['keep']['win'], '{:.1f}')}% / 每笔 {fa(al['W2']['keep']['mean'])}%；"
        f"RW 保留：{al['RW']['keep']['n']} 笔 / {fa(al['RW']['keep']['win'], '{:.1f}')}% / {fa(al['RW']['keep']['mean'])}%")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "rw2_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
