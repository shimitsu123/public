"""deepdip_intl_check.py — 「≤ −15% 深跌」在德国 DAX / 英国 FTSE 100 的历史上是否同方向（2026-09-29 登记；只跑一次，看完不改规则）。

用户：「加 DAX 和 FTSE 100 作对照 / 直接进模拟盘是不是也可以」。日経225 与美国的 ≤ −15%（美国 −12%）是事后描述（登记的研究
crash_mainline_study 没有通过），日本 / 美国的历史都已经看过；DAX / FTSE 100 以前只用于威胁指数（threat_intl_study）与牛熊分界
（timing3_study），没看过「13 周线深跌之后」→ 是还没用过的独立数据。这个核对只判方向，是「要不要再设计账户层检验」的前提，
不是上模拟盘的依据。

一 数据：yfinance ^GDAXI（1987-12-30〜，DAX 是含股息的指数）、^FTSE（1984-01-03〜，价格指数）日收盘，终点固定 2026-09-28。
二 门槛：qbreak/deepdip_forward.py 的 MARKETS（DAX −14.0%、FTSE 100 −11.2%；按波动折算，k 在输出里重算一遍对照）。
三 事件与结果：与前向记录同一套函数（line_dev / events / fwd / mae / base60）：13 周线乖离第一次 ≤ 门槛（回到 ≥ 0 才算新的一段；
   数据最后一天不判）→ 下一个交易日收盘买 → 之后 20 / 60 / 120 个交易日的涨跌、60 天内最低；60 日超额 x60 = 60 日涨跌 − base60
   （事件前 10 年每天买、拿 60 天的平均）。另报（只描述）：减全期平均的超额 xe60（与日本 / 美国的事后描述同一口径）。
四 判定（事先写定）：每个市场有 x60 的事件 ≥ 5 个，否则「样本不足」；两个市场合并的 x60 平均 ≤ 0 →「不一致（欧洲不复现）」；
   DAX 平均 > 0、FTSE 100 平均 > 0、合并 60 日涨的比例 ≥ 60% →「方向一致」；其余「部分一致」。
   另报（只描述）：合并平均的 95% 区间（按大跌段整段重抽 5,000 次，种子 20260929）；独立的大跌段数（两个市场事件日相距 ≤ 90 天
   算同一段）；每个事件前后 90 天内日本（日経225 −15%）/ 美国（S&P 500 −12%）有没有同样的事件。
五 结果怎么用：方向一致 → 日报历史参考加上欧洲的数字；可以提议登记「账户层」检验（资金从哪来、与牛熊分界 T0 的先后、成本；
   要你确认才做，改模拟盘还要再确认）；其余 → 日报写明欧洲没有复现，不据此提议模拟盘。前向记录照常（日本的判定不变）。
输出：var/out/deepdip_intl_check.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import deepdip_forward as DF                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402

END = "2026-09-28"
EU = ("DE", "UK")
REF = {"JP": ("^N225", -15.0), "US": ("^GSPC", -12.0)}                     # 只用来标「同一时期日本 / 美国也有事件」
K_START = {"DE": "1988-01-04", "UK": "1984-01-03"}                           # 两边都有数据的第一年（k 只是对照，门槛以 MARKETS 为准）
MIN_N, WIN_SHARE, N_BOOT, SEED = 5, 60.0, 5000, 20260929


def load_close(sym: str) -> pd.Series:
    from bullbear_study import load
    c = load(sym, "1900-01-01")["Close"].astype(float)
    return c[c.index <= pd.Timestamp(END)]


def k_ratio(c: pd.Series, nk: pd.Series, start: str) -> float:
    def sd(x: pd.Series) -> float:
        x = x[(x.index >= pd.Timestamp(start)) & (x.index <= pd.Timestamp(END))]
        return float(np.log(x).diff().std())
    return sd(c) / sd(nk)


def uncond60(c: pd.Series) -> float:
    """全期每天「下一个交易日收盘买、拿 60 天」的平均（%）：xe60 的基准（与日本 / 美国的事后描述同一口径）。"""
    a = c.dropna().to_numpy(float)
    i = np.arange(0, len(a) - 1 - DF.H_MAIN)
    return float(np.mean(a[i + 1 + DF.H_MAIN] / a[i + 1] - 1) * 100)


def event_rows(mk: str, c: pd.Series, thr: float | None = None) -> list[dict]:
    c = c.dropna()
    thr = DF.MARKETS[mk]["thr"] if thr is None else thr
    dev = DF.line_dev(c)
    u = uncond60(c)
    rows = []
    for d in DF.events(dev.iloc[:-1], thr):                                  # 数据最后一天不判（与前向记录相同）
        r = {"market": mk, "date": str(d.date()), "dev": round(float(dev.loc[d]), 2)}
        for h in DF.HORIZONS:
            r[f"r{h}"] = DF.fwd(c, d, h)
        r["mae60"], r["mae_done"] = DF.mae(c, d)
        r["base60"] = DF.base60(c, d)
        r["x60"] = round(r["r60"] - r["base60"], 2) if r["r60"] is not None and r["base60"] is not None else None
        r["xe60"] = round(r["r60"] - u, 2) if r["r60"] is not None else None
        rows.append(r)
    return rows


def verdict(rows: list[dict]) -> dict:
    done = [r for r in rows if r["x60"] is not None]
    per = {m: [r for r in done if r["market"] == m] for m in EU}
    n = {m: len(v) for m, v in per.items()}
    if min(n.values()) < MIN_N:
        return {"n": n, "label": "样本不足"}
    mean = {m: float(np.mean([r["x60"] for r in v])) for m, v in per.items()}
    pooled = float(np.mean([r["x60"] for r in done]))
    win = float(np.mean([r["r60"] > 0 for r in done]) * 100)
    if pooled <= 0:
        label = "不一致（欧洲不复现）"
    elif all(v > 0 for v in mean.values()) and win >= WIN_SHARE:
        label = "方向一致"
    else:
        label = "部分一致"
    return {"n": n, "mean": {m: round(v, 2) for m, v in mean.items()}, "pooled": round(pooled, 2), "win": round(win, 1), "label": label}


def boot_ci(rows: list[dict], n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """合并 x60 平均的 95% 区间：同一次大跌（两个市场相距 ≤ 90 天）整段一起重抽。"""
    done = [r for r in rows if r["x60"] is not None]
    if not done:
        return {"episodes": 0}
    groups: dict[int, list[float]] = {}
    for r, g in zip(done, DF.episode_labels([r["date"] for r in done])):
        groups.setdefault(g, []).append(r["x60"])
    keys = sorted(groups)
    rng = np.random.default_rng(seed)
    means = [np.mean([v for k in rng.integers(0, len(keys), len(keys)) for v in groups[keys[k]]]) for _ in range(n_boot)]
    return {"episodes": len(keys), "lo": round(float(np.percentile(means, 2.5)), 2), "hi": round(float(np.percentile(means, 97.5)), 2)}


def mark_same_time(rows: list[dict], ref_dates: dict[str, list[pd.Timestamp]], gap: int = DF.EPISODE_GAP) -> None:
    for r in rows:
        d = pd.Timestamp(r["date"])
        r["same_time"] = [m for m, ds in ref_dates.items() if any(abs((x - d).days) <= gap for x in ds)]


def market_stats(rows: list[dict]) -> dict:
    done = [r for r in rows if r["x60"] is not None]
    if not done:
        return {"n": 0}
    f = lambda k: round(float(np.nanmean([np.nan if r[k] is None else r[k] for r in done])), 2)     # noqa: E731
    return {"n": len(done), "x60": f("x60"), "xe60": f("xe60"), "win": round(float(np.mean([r["r60"] > 0 for r in done]) * 100), 1),
            "mae60": f("mae60"), "r20": f("r20"), "r60": f("r60"), "r120": f("r120")}


def main() -> int:
    closes = {m: load_close(DF.MARKETS[m]["symbol"]) for m in EU}
    ref = {m: load_close(sym) for m, (sym, _) in REF.items()}
    k = {m: round(k_ratio(closes[m], ref["JP"], K_START[m]), 3) for m in EU}
    rows = [r for m in EU for r in event_rows(m, closes[m])]
    mark_same_time(rows, {m: list(DF.events(DF.line_dev(ref[m]).iloc[:-1], thr)) for m, (_, thr) in REF.items()})
    v, ci = verdict(rows), boot_ci(rows)
    st = {m: market_stats([r for r in rows if r["market"] == m]) for m in EU}
    fm = lambda x, f="{:+.2f}%": "—" if x is None else f.format(x)                                  # noqa: E731
    L = [f"# 「≤ −15% 深跌」欧洲历史核对（2026-09-29 登记，只跑一次；规则见 scripts/deepdip_intl_check.py 开头；数据截至 {END}）", "",
         f"判定：**{v['label']}**（有 60 日结果的事件：DAX {v['n']['DE']} 个、FTSE 100 {v['n']['UK']} 个）"]
    if v.get("pooled") is not None:
        L.append(f"- 合并 60 日超额（减事件前 10 年平均）平均 {v['pooled']:+.2f}%（95% 区间 {fm(ci.get('lo'))}〜{fm(ci.get('hi'))}，"
                 f"按大跌段整段重抽；独立的大跌段 {ci['episodes']} 个）、60 日涨的比例 {v['win']:.0f}%；DAX {v['mean']['DE']:+.2f}%、FTSE 100 {v['mean']['UK']:+.2f}%")
    L += [f"- 门槛：DAX {DF.MARKETS['DE']['thr']:+.1f}%（k = {k['DE']}）、FTSE 100 {DF.MARKETS['UK']['thr']:+.1f}%（k = {k['UK']}）；"
          "k = 两边都有数据的全部年份的日对数收益标准差 ÷ 日経225 的", "",
          "| 市场 | 事件 | 60 日超额（减前 10 年平均） | 减全期平均 | 60 日涨的比例 | 买后 60 天内最低（平均） | 之后 20 / 60 / 120 天（平均） |",
          "|---|---|---|---|---|---|---|"]
    for m in EU:
        s = st[m]
        if s.get("n"):
            L.append(f"| {DF.MARKETS[m]['name']} | {s['n']} | {s['x60']:+.2f}% | {s['xe60']:+.2f}% | {s['win']:.0f}% | {s['mae60']:+.2f}% | "
                     f"{s['r20']:+.2f} / {s['r60']:+.2f} / {s['r120']:+.2f}% |")
    L += ["", "## 每个事件", "", "| 市场 | 事件日 | 乖离 | 20 天 | 60 天 | 120 天 | 买后最低 | base60 | 60 日超额 | 前后 90 天内日本 / 美国也有 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["date"], r["market"])):
        L.append(f"| {DF.MARKETS[r['market']]['name']} | {r['date']} | {r['dev']:+.2f}% | {fm(r['r20'])} | {fm(r['r60'])} | {fm(r['r120'])} | "
                 f"{fm(r['mae60'])} | {fm(r['base60'], '{:+.3f}%')} | {fm(r['x60'])} | {' / '.join(r['same_time']) or '—'} |")
    L += ["", "对照（事后描述，已看过；口径 = 减全期平均）：日経225 1965〜2000 +3.11%（9 段）、2001〜2026 +4.64%（8 段）、美国 1926〜2026 +1.28%（34 段）。",
          "DAX 是含股息的指数、FTSE 100 是价格指数：两者各自减自己的平均，超额不受影响。", "非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "deepdip_intl_check"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"verdict": v, "ci": ci, "k": k, "stats": st, "events": rows}, ensure_ascii=False, indent=1,
                                             default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
