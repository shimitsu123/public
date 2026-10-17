"""household_spend_study.py — 家庭消费（米、酒类、啤酒、外食…按品目）的变化 → 之后对应个股的收益（2026-10-11 登记；先提交后只运行一次）。

用户（2026-10-11）：「根据最近的各式各样的原材料消费，比如酒消费、大米消费等等横展开，对一段时间以后的哪些对应的股市有冲击进行研究」。
以前做过、没通过的（不重复）：每月石油 / 能源消费（O1/O2、K1〜K5）、原材料 / 上下游股价 → 1〜6 个月、原材料企业物价 × 产业链。
这次新的：总务省「家計調査」（二人以上の世帯、品目分类、1 世帯当たり支出金額，e-Stat 0004023601，2000-01〜；qbreak/household_spend.py）。

一、信号（每个品目 i、每个月末 T，只用 T 以前已经公布的）：
  能用的最新调查月 m = T 所在月 − 2（qbreak/household_spend.available_from：调查月 + 2 个月的月末才算拿到，保守）；
  g_i = 品目 i 支出的 3 个月移动平均（m−2〜m）÷ 一年前同期 − 1；s_i = g_i − g_消費支出（比整体消费多涨 / 多跌了多少）。
二、对应的股票：var/household_items.json 的 companies（等权篮子；没有对应公司的品目不算）；月末收盘（yfinance 调整后）。
三、主判定（信息检验）：每个 T，跨品目的秩相关 IC_T = corr(rank s_i, rank 篮子 i 在 T → T+3 个月的收益)（≥ 10 个品目有数才算）。
  **有信息** = 前半（T ≤ 2013-12）与后半（T ≥ 2014-01）的平均 IC 都 > 0，且只用不重叠的季度样本（T 在 3 / 6 / 9 / 12 月末）的 IC 做单侧 t 检验 p < 0.10
  （个数约 100 → 正态近似）。否则「没有信息」→ 停（记下结论，这个方向不再找）。
  有信息 → 另行登记怎么用（例：对应个股的新仓倍数 / 展示），本研究不改模拟盘 / 执行器。
四、只描述（不参与判定）：1 个月 / 6 个月后的 IC；每个品目单独的时间序列相关（s_i vs 篮子之后 3 个月相对全部篮子的超额，月度、重叠）前后 5 名；
  信号最新一期（2026-08 调查月）的前后 5 名。注意（照实写）：2018-01 家計簿改版（支出偏高）、2019-10 增税、2020〜2022 疫情；
  减去消費支出的增速能去掉大部分共同的冲击；啤酒和酒类等对应同一批公司 → 品目之间不独立。
事前预期：股价通常先于（或同时）反映消费变化，家計調査又晚约 40 天 → 大概率没有信息；即使有，多半只在个别品目。
运行：python scripts/household_spend_study.py → var/out/household_spend_study.md / .json（只有汇总数字）。非投资建议。
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = "household_spend_study"
TOTAL = "消費支出"
H_MAIN, H_DESC = 3, (1, 6)
MIN_ITEMS = 10
SPLIT = "2013-12-31"
P_MAX = 0.10


# ───────────────────────── 规则（纯函数，tests/test_household_spend_study.py） ─────────────────────────
def growth(w: pd.DataFrame) -> pd.DataFrame:
    """宽表（index 调查月 'YYYY-MM'）→ 3 个月移动平均的同比增速。"""
    w = w.copy()
    w.index = pd.PeriodIndex(w.index, freq="M")
    ma = w.rolling(3, min_periods=3).mean()
    return ma / ma.shift(12) - 1


def signals(w: pd.DataFrame, ends: pd.DatetimeIndex) -> pd.DataFrame:
    """每个月末 T：能用的最新调查月 = T 的月份 − 2 → s_i = g_i − g_消費支出。index = T，列 = 品目。"""
    g = growth(w)
    rel = g.sub(g[TOTAL], axis=0).drop(columns=[TOTAL])
    rows = {}
    for T in ends:
        m = pd.Period(T, freq="M") - 2
        if m in rel.index:
            rows[T] = rel.loc[m]
    return pd.DataFrame(rows).T


def basket_returns(px: pd.DataFrame, baskets: dict[str, list[str]], ends: pd.DatetimeIndex, h: int) -> pd.DataFrame:
    """月末收盘宽表（index 月末）→ 每个 T、每个品目：篮子（等权）T → T+h 个月的收益。"""
    r = px.shift(-h) / px - 1
    out = {}
    for it, ts in baskets.items():
        cols = [t for t in ts if t in r.columns]
        if cols:
            out[it] = r[cols].mean(axis=1, skipna=True)
    return pd.DataFrame(out).reindex(ends)


def ic_series(sig: pd.DataFrame, ret: pd.DataFrame) -> pd.Series:
    out = {}
    for T in sig.index.intersection(ret.index):
        a, b = sig.loc[T], ret.loc[T]
        m = a.notna() & b.notna()
        if m.sum() >= MIN_ITEMS:
            out[T] = float(a[m].rank().corr(b[m].rank()))
    return pd.Series(out, dtype=float)


def verdict(ic: pd.Series) -> dict:
    h1, h2 = ic[ic.index <= pd.Timestamp(SPLIT)], ic[ic.index > pd.Timestamp(SPLIT)]
    q = ic[ic.index.month.isin([3, 6, 9, 12])].dropna()
    p = None
    if len(q) > 2 and q.std(ddof=1) > 0:
        tv = q.mean() / (q.std(ddof=1) / math.sqrt(len(q)))
        p = 0.5 * math.erfc(tv / math.sqrt(2))
    ok = bool(len(h1) and len(h2) and h1.mean() > 0 and h2.mean() > 0 and p is not None and p < P_MAX)
    return {"ic": round(float(ic.mean()), 4), "ic_h1": round(float(h1.mean()), 4), "ic_h2": round(float(h2.mean()), 4),
            "n": len(ic), "n_q": len(q), "p": None if p is None else round(p, 4), "info": ok}


# ───────────────────────── 数据 ─────────────────────────
def load_all() -> tuple[pd.DataFrame, dict[str, list[str]], pd.DataFrame]:
    from qbreak import household_spend as HS
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    w = HS.load("yen")
    mp = HS.item_map()["items"]
    baskets = {it: [f"{c['code']}.T" for c in v.get("companies") or []] for it, v in mp.items() if v.get("companies") and it in w.columns}
    ticks = sorted({t for ts in baskets.values() for t in ts})
    data = load_universe(ticks, DataConfig(provider="yfinance", years=27, allow_synthetic=False, min_bars=60).validate())
    px = pd.DataFrame({t: df["Close"].astype(float) for t, df in data.items()})
    px = px.groupby(px.index.to_period("M")).last()
    px.index = px.index.to_timestamp(how="end").normalize()
    return w, baskets, px


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    w, baskets, px = load_all()
    ends = px.index[(px.index >= pd.Timestamp("2001-01-01")) & (px.index <= pd.Timestamp("2026-09-30"))]
    sig = signals(w, ends)
    res = {"study": OUT, "items": len(baskets), "tickers": int(px.shape[1]), "months": len(sig)}
    ics = {}
    for h in (H_MAIN,) + H_DESC:
        ics[h] = ic_series(sig, basket_returns(px, baskets, ends, h))
    res["verdict"] = verdict(ics[H_MAIN])
    res["desc_ic"] = {h: round(float(ics[h].mean()), 4) for h in H_DESC}
    r3 = basket_returns(px, baskets, ends, H_MAIN)
    ex = r3.sub(r3.mean(axis=1), axis=0)
    per = {}
    for it in sig.columns.intersection(ex.columns):
        m = sig[it].notna() & ex[it].notna()
        if m.sum() >= 60:
            per[it] = round(float(sig[it][m].corr(ex[it][m])), 3)
    s = pd.Series(per).sort_values()
    res["per_item_top"] = s.tail(5)[::-1].to_dict()
    res["per_item_bottom"] = s.head(5).to_dict()
    last = sig.dropna(how="all").iloc[-1].dropna().sort_values()
    res["latest"] = {"asof": str(sig.dropna(how="all").index[-1].date()), "survey_month": str(pd.Period(sig.dropna(how="all").index[-1], freq="M") - 2),
                     "top": {k: round(float(v) * 100, 1) for k, v in last.tail(5)[::-1].items()},
                     "bottom": {k: round(float(v) * 100, 1) for k, v in last.head(5).items()}}
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    v = res["verdict"]
    L = [f"# 家庭消费（按品目）→ 之后对应个股的收益（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/household_spend_study.py 开头）", "",
         f"**{'有信息 → 另行登记怎么用' if v['info'] else '没有信息 → 停'}**：3 个月后的 IC 平均 {v['ic']:+.4f}（{v['n']} 个月）、前半 {v['ic_h1']:+.4f} / 后半 {v['ic_h2']:+.4f}；"
         f"不重叠季度样本 {v['n_q']} 个、单侧 p = {v['p']}（要 < {P_MAX}，两半都 > 0）", "",
         f"- 品目 {res['items']} 个（有对应公司的）、股票 {res['tickers']} 只、月数 {res['months']}",
         f"- 只描述：1 个月后 IC {res['desc_ic'][1]:+.4f}、6 个月后 IC {res['desc_ic'][6]:+.4f}",
         "- 只描述：单个品目的时间序列相关（信号 vs 之后 3 个月相对全部篮子的超额；月度重叠、不做检验）"
         f"最高 {res['per_item_top']}、最低 {res['per_item_bottom']}",
         f"- 最新（{res['latest']['asof']} 时点 = {res['latest']['survey_month']} 调查月）比整体消费多涨（pp）：{res['latest']['top']}；多跌：{res['latest']['bottom']}",
         "", f"只研究，不改模拟盘 / 执行器。用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
