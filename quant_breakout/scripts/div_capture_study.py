"""div_capture_study.py — 分红前买入、持有过除权拿分红再卖，能不能赚钱（2026-10-12 登记；先提交后只运行一次）。

用户（2026-10-12）：「当有股票过几天会分红的话就提前入手，第二天可以吃到分红后再卖出的话会挣钱的研究」。
以前：探索（不登记，2026-09-27，scripts/div_explore.py）只看了「除权前买、权利付最终日卖（不拿分红）」2017〜2021 的 10 次 → 扣成本就没了；
「持有过除权、拿分红」从来没测过。
数据：今天的日経225（照实写：有幸存者偏差，对三种做法相同）；yfinance 的未复权收盘（只做拆股调整）与每股分红（按除权日 x）——scripts/leap_data.actions；
      日経225 指数（^N225）当大盘。期间 2006-01〜2026-09（除权日）。权利付最终日 = x 之前的那个交易日。
三种做法（每次除权一笔；收益 = 卖价 + 拿到的分红 × (1 − 20.315%) 之后 ÷ 买价 − 1 − 来回成本 0.30%；超额 = 减去同一段日経225 指数的涨跌）：
  DC5：x 之前第 5 个交易日收盘买 → x（除权日）收盘卖，拿分红（= 用户说的做法）。
  RU5：x 之前第 5 个交易日收盘买 → 权利付最终日（x − 1）收盘卖，不拿分红（只吃除权前的上涨；以前的探索换成更长期间与日経225）。
  ON1：权利付最终日收盘买 → x 收盘卖，拿分红（只隔一夜吃分红）。
判定（每种做法单独）：「能赚钱」= 超额收益（扣成本、税后）平均 > 0，按除权日聚类的 95% 区间下限 > 0，且 2006〜2015 与 2016〜2026 两半都 > 0。
只描述：按当时已知的股息率（过去 1 年分红 ÷ 买入日收盘）分五组；除权日的下跌 ÷ 分红（「除权下跌了分红的几成」）。
事前预期：除权日股价大体按分红下跌，税后只拿回约 80% → DC5 / ON1 多半亏；RU5 以前扣成本就没了。只研究，不改模拟盘 / 执行器。非投资建议。
运行：python scripts/div_capture_study.py → var/out/div_capture_study.md / .json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TAX, COST = 0.20315, 0.30
START, END, SPLIT = "2006-01-01", "2026-09-30", "2016-01-01"


def events(t: str, act: pd.DataFrame, n2: pd.Series) -> list[dict]:
    c = act["close_raw"].dropna()
    c = c[c > 0]
    out = []
    for x, d in act["div"].dropna().items():
        if d <= 0 or not (pd.Timestamp(START) <= x <= pd.Timestamp(END)) or x not in c.index:
            continue
        k = c.index.get_loc(x)
        if k < 6:
            continue
        p5, p1, px = float(c.iloc[k - 5]), float(c.iloc[k - 1]), float(c.iloc[k])
        net_d = float(d) * (1 - TAX)

        def mk(a, b):
            i, j = n2.index.searchsorted(a), n2.index.searchsorted(b)
            return (n2.iloc[min(j, len(n2) - 1)] / n2.iloc[min(i, len(n2) - 1)] - 1) * 100
        dc5 = ((px + net_d) / p5 - 1) * 100 - COST - mk(c.index[k - 5], x)
        ru5 = (p1 / p5 - 1) * 100 - COST - mk(c.index[k - 5], c.index[k - 1])
        on1 = ((px + net_d) / p1 - 1) * 100 - COST - mk(c.index[k - 1], x)
        yld = float(act["div"].loc[x - pd.Timedelta(days=365):x].sum() / p5 * 100)
        drop = (p1 - px) / float(d)
        out.append({"t": t, "x": x, "DC5": dc5, "RU5": ru5, "ON1": on1, "yld": yld, "drop": drop})
    return out


def ci(v: pd.Series, g: pd.Series) -> tuple[float, float, float]:
    """平均与按除权日聚类的 95% 区间（同一天的除权算一组）。"""
    m = v.groupby(g).mean()
    s = m.std(ddof=1) / np.sqrt(len(m)) if len(m) > 1 else np.nan
    mu = float(v.mean())
    return mu, mu - 1.96 * s, mu + 1.96 * s


def main() -> int:
    import leap_data as LD
    from qbreak import paths
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    n2 = load_universe(["^N225"], DataConfig(provider="yfinance", years=27, allow_synthetic=False, min_bars=60).validate())["^N225"]["Close"].astype(float)
    rows = []
    for t in universe("JP", "broad"):
        try:
            rows += events(t, LD.actions(t), n2)
        except Exception:                                          # noqa: BLE001
            continue
    E = pd.DataFrame(rows)
    res = {"events": int(len(E)), "tickers": int(E["t"].nunique()), "ways": {}}
    L = [f"# 分红前买入、持有过除权拿分红再卖：能不能赚钱（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/div_capture_study.py 开头）", "",
         f"日経225（今天的成分）{res['tickers']} 只、除权 {res['events']} 次（{START[:4]}〜{END[:7]}）；收益已扣来回成本 {COST}%、分红按税后 {1 - TAX:.5f} 计、减去同期日経225。", "",
         "| 做法 | 全期 平均超额（95% 区间） | 2006〜2015 | 2016〜2026 | 赚钱的比例 | 判定 |", "|---|---|---|---|---|---|"]
    for k, nm in (("DC5", "除权前 5 天买 → 除权日卖（拿分红）"), ("RU5", "除权前 5 天买 → 最终日卖（不拿分红）"), ("ON1", "最终日买 → 除权日卖（只隔一夜）")):
        a = ci(E[k], E["x"])
        h1 = E[E["x"] < SPLIT]
        h2 = E[E["x"] >= SPLIT]
        m1, m2 = float(h1[k].mean()), float(h2[k].mean())
        ok = a[1] > 0 and m1 > 0 and m2 > 0
        res["ways"][k] = {"mean": a[0], "lo": a[1], "hi": a[2], "h1": m1, "h2": m2, "win": float((E[k] > 0).mean() * 100), "ok": bool(ok)}
        L.append(f"| {k} {nm} | {a[0]:+.2f}%（{a[1]:+.2f}〜{a[2]:+.2f}） | {m1:+.2f}% | {m2:+.2f}% | {(E[k] > 0).mean() * 100:.0f}% | **{'能赚钱' if ok else '不能'}** |")
    E["q"] = pd.qcut(E["yld"].rank(method="first"), 5, labels=["低", "2", "3", "4", "高"])
    L += ["", "只描述：按股息率分五组的平均超额（%）", "", "| 股息率组 | 股息率中位 | DC5 | RU5 | ON1 |", "|---|---|---|---|---|"]
    for q, g in E.groupby("q", observed=True):
        L.append(f"| {q} | {g['yld'].median():.2f}% | {g['DC5'].mean():+.2f} | {g['RU5'].mean():+.2f} | {g['ON1'].mean():+.2f} |")
    dr = E["drop"].replace([np.inf, -np.inf], np.nan).dropna()
    res["drop_median"] = float(dr.median())
    L += ["", f"只描述：除权日（最终日收盘 → 除权日收盘）的下跌约等于分红的 {dr.median():.2f} 倍（中位；税后只拿回 {1 - TAX:.2f} 倍 → 下跌超过 {1 - TAX:.2f} 倍就是亏）。",
          "", "只研究，不改模拟盘 / 执行器。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / "div_capture_study.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / "div_capture_study.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
