"""lowvol_explore.py — 探索（2026-09-27；只用 J-Quants 2016-10〜2026-09 的**日経225 以外**的全部股票；日経225 的 2006〜2016 与 2019〜2026 都不看，
留给登记后的判定）：allstock_posthoc 里每年方向差不多都一致的特征，按固定分界分组后，**在 W2 保留的突破里**每笔净收益是不是每年都更好。

特征（allstock_study 同一个函数、只用信号日收盘为止）：atrp = ATR(14) ÷ 收盘、vol60 = 60 天年化波动、dist = 20 天内出货日数、
rng = 60 天箱体振幅、hi52 = 收盘 ÷ 250 天最高、r20 = 20 天涨幅、vr1 = 突破日量比、lturn = log10(20 天平均成交额)。
分界 = 这批探索数据（日経225 以外、W2 保留、全部年份）的三分位（固定数字，之后登记用同一个数）。
数据：allstock_study.train_all（登记 1024de5 的同一套训练数据；整理结果缓存在 var/cache/jquants/allstock_train.pkl，不入库）。
输出：var/out/lowvol_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import allstock_data as AD                                                   # noqa: E402
import allstock_study as S                                                   # noqa: E402
import candle_data as CD                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402

CACHE = AD.CACHE.parent / "allstock_train.pkl"
FEATS = {"atrp": "ATR(14) ÷ 收盘", "vol60": "60 天年化波动", "dist": "20 天内出货日数", "rng": "60 天箱体振幅", "hi52": "收盘 ÷ 250 天最高",
         "r20": "20 天涨幅", "vr1": "突破日量比", "lturn": "log10(20 天平均成交额)"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def train_table() -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_pickle(CACHE)
    from bullbear_study import SYM, load
    from qbreak.trader import load_params
    pb = replace(load_params(market="JP"), min_weekly_vol_ratio=0.0)
    T, _ = S.train_all(AD.load(), pb, S.market_frame(load(*SYM["JP"])["Close"]))
    T.to_pickle(CACHE)
    return T


def st(x: pd.DataFrame) -> dict:
    net = x["net"].to_numpy(float)
    if not len(net):
        return {"n": 0}
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    return {"n": int(len(net)), "win": float((net > 0).mean() * 100), "mean": float(net.mean()),
            "pf": float(pos / neg) if neg > 0 else float("nan")}


def main() -> int:
    t0 = time.time()
    T = train_table()
    D = CD.load()
    n225 = {D["names"][j] for j in range(len(D["names"])) if D["mem"]["U0"][:, j].any()}
    X = T[~T["ticker"].isin(n225) & ~(T["w5v"] < 1.0)].copy()                # 日経225 以外、W2 保留
    X["year"] = pd.DatetimeIndex(X["sig_date"]).year
    years = sorted(X["year"].unique())
    out: dict = {"n": int(len(X)), "cuts": {}, "feat": {}}
    fa = lambda v, f="{:+.2f}%": "—" if v is None or not np.isfinite(v) else f.format(v)   # noqa: E731
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'], '{:.2f}')}"   # noqa: E731
    say("# 探索：全部股票（日経225 以外）里 W2 保留的突破，按特征三等分的每笔净收益（2016-10〜2026-09）")
    say(f"{len(X)} 笔（每只票单独、扣成本）。各格 = 笔数 / 胜率 / 每笔 / 盈亏比；分界 = 这批数据的三分位（固定数字）。日経225 的数据完全没用。")
    for f, lab in FEATS.items():
        ok = X[f].notna()
        q1, q2 = (float(v) for v in np.quantile(X.loc[ok, f], [1 / 3, 2 / 3]))
        out["cuts"][f] = [q1, q2]
        lo, mid, hi = X[ok & (X[f] <= q1)], X[ok & (X[f] > q1) & (X[f] <= q2)], X[ok & (X[f] > q2)]
        say(f"\n## {f}（{lab}）：分界 {q1:.4g} / {q2:.4g}")
        say("| 年 | 低 1/3 | 中 1/3 | 高 1/3 | 低 − 高（每笔） |")
        say("|---|---|---|---|---|")
        rows = {}
        for y in years:
            a, b, c = st(lo[lo["year"] == y]), st(mid[mid["year"] == y]), st(hi[hi["year"] == y])
            d = a["mean"] - c["mean"] if a["n"] and c["n"] else float("nan")
            rows[int(y)] = {"lo": a, "mid": b, "hi": c, "diff": d}
            say(f"| {y} | {c4(a)} | {c4(b)} | {c4(c)} | {fa(d, '{:+.2f} pp')} |")
        a, b, c = st(lo), st(mid), st(hi)
        d = a["mean"] - c["mean"]
        npos = sum(1 for r in rows.values() if np.isfinite(r["diff"]) and r["diff"] > 0)
        nval = sum(1 for r in rows.values() if np.isfinite(r["diff"]))
        say(f"| 全期 | {c4(a)} | {c4(b)} | {c4(c)} | {fa(d, '{:+.2f} pp')} |")
        say(f"低 1/3 比高 1/3 好的年份：{npos} / {nval}")
        out["feat"][f] = {"years": rows, "all": {"lo": a, "mid": b, "hi": c, "diff": d}, "lo_better_years": npos, "years_n": nval}
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "lowvol_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
