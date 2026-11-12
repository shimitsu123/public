"""leap2_s2_explore.py — 「选股本身的质的飞跃」第 S2 轮探索：价量里的「事件」特征能不能把突破分得很开（只描述、不登记；E / J，Z 不看）。

S1（scripts/leap2_s1_explore.py、leap2_s1b_exits.py）：扩大池、量比 / 股息率挑选、回踩买、6 种卖法 → 胜率最多 +4 pp，离门槛（+8 pp 且每笔 +1 pp）很远。
这里筛以前没用过的、有文献 / 实务依据的价量特征（逐笔 = 第 1 轮缓存的单独交易，今天的日経225 + T500x，现行卖出规则、扣成本）：
  gap   突破当天跳空高开 ≥ 2%（开盘 ÷ 前一天收盘；消息驱动）
  earn  信号日在决算季（1/25〜2/15、4/25〜5/20、7/25〜8/15、10/25〜11/15）
  pead  gap ∧ earn ∧ 突破日量比 ≥ 2（决算后跳空放量 = 业绩惊喜的价量代理，Post-Earnings-Announcement Drift）
  hi3y / hi5y  收盘创 3 年 / 5 年新高（上方没有套牢盘；George & Hwang 2004 的高点效应）
  base  距上一次 250 日新高 ≥ 60 个交易日（长时间整理后的第一次新高）
每个特征：有 / 没有 两组的笔数、胜率、每笔；E / J 各自、全部突破与 W2 保留；另看每年同向的年数。
门槛参照（现行 = W2 · 日経225 的组合交易）：E 胜率 44% / 每笔 +0.93%、J 42% / +0.61% → 要 +8 pp、+1 pp。
输出：var/out/leap2_s2_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap2_common as L2                                                    # noqa: E402
import leap_common as LC                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
EARN = ((1, 25, 2, 15), (4, 25, 5, 20), (7, 25, 8, 15), (10, 25, 11, 15))
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def in_earn(d: pd.Timestamp) -> bool:
    """决算季（月 / 日区间，含两端）。"""
    md = (d.month, d.day)
    return any((m1, d1) <= md <= (m2, d2) for m1, d1, m2, d2 in EARN)


def event_features(df: pd.DataFrame, sig: pd.Timestamp) -> dict:
    """一只票的日线（复权 OHLCV）+ 信号日 → 只用信号日为止的价量特征。"""
    i = int(df.index.searchsorted(sig))
    if i >= len(df) or df.index[i] != sig or i < 21:
        return {}
    o, c, v = df["Open"].to_numpy(float), df["Close"].to_numpy(float), df["Volume"].to_numpy(float)
    gap = o[i] / c[i - 1] - 1 if c[i - 1] > 0 else np.nan
    vavg = np.nanmean(v[max(0, i - 20):i])
    vr = v[i] / vavg if vavg > 0 else np.nan
    out = {"gap": gap, "vr": vr, "earn": in_earn(sig)}
    for k, n in (("hi3y", 750), ("hi5y", 1250)):
        out[k] = bool(c[i] >= np.nanmax(c[i - n:i])) if i >= n else np.nan
    if i >= 250:
        h = pd.Series(c).rolling(250, min_periods=250).max().to_numpy()
        prev = np.flatnonzero(c[:i] >= h[:i] - 1e-12)
        out["base"] = (i - int(prev[-1])) if len(prev) else np.nan
    else:
        out["base"] = np.nan
    return out


def split_stats(T: pd.DataFrame, mask: pd.Series) -> dict:
    """有 / 没有 两组：笔数、胜率、每笔；每年 有 − 没有 的每笔差为正的年数。"""
    def st(x):
        return {"n": int(len(x)), "win": round(float((x > 0).mean() * 100), 1) if len(x) else None,
                "mean": round(float(x.mean()), 3) if len(x) else None}
    m = mask.fillna(False).astype(bool)
    yrs = T["sig_date"].dt.year
    pos = tot = 0
    for y in sorted(yrs.unique()):
        a, b = T.loc[m & (yrs == y), "net"], T.loc[~m & (yrs == y), "net"]
        if len(a) >= 3 and len(b) >= 3:
            tot += 1
            pos += int(a.mean() > b.mean())
    return {"yes": st(T.loc[m, "net"]), "no": st(T.loc[~m, "net"]), "years": [pos, tot]}


def main() -> int:
    import leap_data as LD
    t0 = time.time()
    fp_tr = paths.sub("cache") / "leap_r1_trades.pkl"
    T = pd.read_pickle(fp_tr)
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    LC.assert_explore_dates(T["sig_date"])
    uw = set(L2.uw_names())
    T = T[T["ticker"].isin(uw)].reset_index(drop=True)
    data = LD.ohlcv(sorted(T["ticker"].unique()))
    rows = []
    for idx, r in T.iterrows():
        df = data.get(r["ticker"])
        rows.append({"i": idx, **(event_features(df, r["sig_date"]) if df is not None else {})})
    F = pd.DataFrame(rows).set_index("i")
    T = T.join(F)
    T["gap2"] = T["gap"] >= 0.02
    T["vr2"] = T["vr"] >= 2
    T["pead"] = T["gap2"] & T["earn"].astype(bool) & T["vr2"]
    T["base60"] = T["base"] >= 60
    feats = [("gap2", "突破当天跳空 ≥ 2%"), ("earn", "决算季"), ("pead", "决算季 ∧ 跳空 ≥ 2% ∧ 量比 ≥ 2"), ("hi3y", "3 年新高"),
             ("hi5y", "5 年新高"), ("base60", "距上次 250 日新高 ≥ 60 天"), ("vr2", "对照：突破日量比 ≥ 2")]
    say(f"# 「选股本身的质的飞跃」第 S2 轮探索：价量里的「事件」特征（只描述，{pd.Timestamp.today().date()}）")
    say(f"规则见 scripts/leap2_s2_explore.py 开头。单独交易 = 第 1 轮缓存里今天的日経225 + T500x（{len(T)} 笔）；格子 = 笔数 / 胜率 / 每笔净收益。")
    out = {}
    for era, (a, b) in ERAS.items():
        E = T[(T["sig_date"] >= pd.Timestamp(a)) & (T["sig_date"] < pd.Timestamp(b))]
        for sub, V in (("全部突破", E), ("W2 保留", E[E["w2"]])):
            say(f"\n## {era} · {sub}（{len(V)} 笔：胜率 {(V['net'] > 0).mean() * 100:.1f}%、每笔 {V['net'].mean():+.2f}%）")
            say("| 特征 | 有 | 没有 | 有 − 没有：胜率 pp / 每笔 pp | 有 > 没有 的年数 |")
            say("|---|---|---|---|---|")
            for f, lab in feats:
                V2 = V[V[f].notna()] if V[f].dtype == object else V
                s = split_stats(V2, V2[f].astype("boolean"))
                out[f"{era}/{sub}/{f}"] = s
                y, n = s["yes"], s["no"]
                fm = lambda x: "—" if x["mean"] is None else f"{x['n']} / {x['win']:.0f}% / {x['mean']:+.2f}%"            # noqa: E731
                dw = "—" if y["win"] is None or n["win"] is None else f"{y['win'] - n['win']:+.1f} / {y['mean'] - n['mean']:+.2f}"
                say(f"| {lab} | {fm(y)} | {fm(n)} | {dw} | {s['years'][0]}/{s['years'][1]} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s2_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
