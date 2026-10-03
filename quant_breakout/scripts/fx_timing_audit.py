"""fx_timing_audit.py — 事后审计（2026-10-03 第六个研究循环第二段第 6 轮 CRW 两关都过之后、做事后描述时发现；不是登记的研究，不改任何登记过的判定，只描述）：
研究引擎里汇率的时点。

发现（照实写）：
  - Yahoo「JPY=X」日线标成 d 日的 Close，实际上是 d 日东京早上（约 00:00 GMT）左右的价；FRED DEXJPUS 的 d 日 = 纽约 d 日中午。证据（本脚本 A 部分）：
    2010-09-15 日本单独干预（10:30 JST）、2011-03-18 G7 干预（东京早上）、2016-01-29 日银负利率（12:40 JST）、2022-09-22 干预（17:00 JST 左右）、
    2024-07-11 美国 CPI（21:30 JST）—— Yahoo 的 d 日值都还是事件前的，DEXJPUS 的 d 日值已经是事件后的；Yahoo d 日值在水平上更接近 DEXJPUS 的 d − 1 日。
  - 研究的合成价（scripts/equity_idle_study.on_jp）：1545 在东证 d 日的日元价 = 前一个美国收盘 × 「d 之前（不含 d）最近的 Yahoo 值」≈ d − 1 日东京早上的汇率
    （比东证 d 日开盘时的真实汇率旧约 1 天）。
  - 汇率择时的信号（FXH / FXE / JBH / FJE / CRW 等）用 DEXJPUS 的美国 d 日（纽约中午 ≈ 17:00 GMT），东证 d + 1 开盘按「d 日东京早上的汇率」成交
    → 信号比成交价多知道约 17 小时的汇率变动（引起信号的那一段日元急升 / 回落），回测里会把它当成对冲的收益 = 偏乐观。
  - 修正口径（本脚本 B 部分）：只把 1545（及其它要换汇的合成价）的汇率改成「东证 d 日当天（含）以前最近的 Yahoo 值」（≈ d 日东京开盘前），
    其余（美国收盘、信号、费用、个股）全部不动 → 信号（d 日纽约中午）在成交价的汇率（d + 1 日东京早上）之前，不再提前看到。
    实盘不受影响（执行器用真实的 1545 / 2845 价格成交）；受影响的是「汇率择时」的回测好处有多大。
B 部分重算：B0（Q1：1545 + 美股牛熊）、B1（+ FJE）、B2（+ BCU，第六个循环第二段的基准）、CRW（第 6 轮）在原口径 / 修正口径下的 Z / E / J 账户。
运行：python scripts/fx_timing_audit.py（两种口径各加载一次，约 8 分钟）→ var/out/fx_timing_audit.md / .json。非投资建议。
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

EVENTS = (("2010-09-15", "日本单独干预（10:30 JST 左右）"), ("2011-03-18", "G7 协调干预（东京早上）"),
          ("2016-01-29", "日银负利率（12:40 JST 公布）"), ("2022-09-22", "日本干预（17:00 JST 左右）"),
          ("2024-07-11", "美国 CPI（21:30 JST）后日元急升"))
OUT = "fx_timing_audit"


def on_jp_same_day(s: pd.Series, fx: pd.Series | None, days: pd.DatetimeIndex) -> pd.Series:
    """修正口径：美国收盘 = d 之前（不含 d）最近的（同原口径）；汇率 = d 当天（含）以前最近的 Yahoo 值（≈ d 日东京开盘前）。"""
    import equity_idle_study as EI
    v = EI.prev_on(days, s)
    if fx is not None:
        f = fx.dropna().sort_index()
        v = v * f.reindex(pd.DatetimeIndex(days).union(f.index)).ffill().reindex(days)
    return v.dropna()


def stamp_evidence(yahoo: pd.Series, dex: pd.Series) -> dict:
    """A：Yahoo JPY=X 与 DEXJPUS 的时点（事件日的值、日变化的相关、水平最接近的是哪一天）。"""
    idx = yahoo.dropna().index.intersection(dex.dropna().index)
    idx = idx[idx >= pd.Timestamp("2003-01-01")]
    ly, ld = np.log(yahoo.reindex(idx)), np.log(dex.reindex(idx))
    dy, dd = ly.diff(), ld.diff()
    out = {"corr": {f"dYahoo_t~dDEX_t{lag:+d}": round(float(dy.corr(dd.shift(-lag))), 3) for lag in (-1, 0, 1)},
           "mean_abs_level_gap_pct": {f"Yahoo_t~DEX_t{lag:+d}": round(float((ly - ld.shift(-lag)).abs().mean() * 100), 3) for lag in (-1, 0, 1)},
           "events": []}
    for d, what in EVENTS:
        t = pd.Timestamp(d)
        prev = dex[dex.index < t]
        out["events"].append({"date": d, "what": what, "yahoo": round(float(yahoo.get(t, np.nan)), 2), "dex": round(float(dex.get(t, np.nan)), 2),
                              "dex_prev": round(float(prev.iloc[-1]), 2) if len(prev) else None})
    return out


def accounts(mode: str) -> dict:
    """B：一种口径下 B0 / B1 / B2 / CRW 的 Z / E / J 账户。"""
    import equity_idle_study as EI
    orig = EI.on_jp
    if mode == "fixed":
        EI.on_jp = on_jp_same_day
    try:
        import loop_common as LCM
        import loop6_common as L6
        import loop6_r06_cotcrowd as C
        W = L6.load()
        M = C.inputs(W)
        ov = C.over(W, W["bear"]["US"], M["uni_c"], M["hf"], M["on_b"], M["fb"])
        out = {}
        for e in L6.ERAS:
            rows = (("B0", LCM.run(W, e)), ("B1", LCM.run(W, e, **W["b1_q1h"])), ("B2", L6.run(W, e)), ("CRW", L6.run(W, e, **ov)))
            out[e] = {k: {x: r.get(x) for x in ("cagr", "dd", "calmar")} for k, r in rows}
            print(mode, e, json.dumps(out[e], ensure_ascii=False), flush=True)
        return out
    finally:
        EI.on_jp = orig


def effects(acc: dict) -> dict:
    """各一步的 Calmar 差：FJE = B1 − B0、BCU = B2 − B1、CRW = CRW − B2（每个年代与合计）。"""
    def d(a, b):
        v = {e: round(acc[e][a]["calmar"] - acc[e][b]["calmar"], 3) for e in acc}
        v["sum"] = round(sum(v.values()), 3)
        return v
    return {"FJE（B1 − B0）": d("B1", "B0"), "BCU（B2 − B1）": d("B2", "B1"), "CRW（CRW − B2）": d("CRW", "B2")}


def write(res: dict) -> None:
    from qbreak import paths
    ev = res["evidence"]
    L = ["# 事后审计：研究引擎里汇率的时点（scripts/fx_timing_audit.py；不是登记的研究，不改任何登记过的判定，只描述）", "",
         "## A. Yahoo JPY=X 的「d 日收盘」是什么时候的价", "",
         "| 日子 | 事件 | Yahoo d 日 | DEXJPUS d 日（纽约中午） | DEXJPUS 前一天 |", "|---|---|---|---|---|"]
    for x in ev["events"]:
        L.append(f"| {x['date']} | {x['what']} | {x['yahoo']} | {x['dex']} | {x['dex_prev']} |")
    L += ["", "日变化的相关：" + "、".join(f"{k} {v}" for k, v in ev["corr"].items()) + "；水平的平均差（%）：" + "、".join(f"{k} {v}" for k, v in ev["mean_abs_level_gap_pct"].items()),
          "→ Yahoo 的 d 日值 ≈ d 日东京早上（事件前），比 DEXJPUS 的 d 日（纽约中午）早约 17 小时。", "",
          "## B. 原口径 vs 修正口径（只把合成价的汇率改成东证当天（含）以前最近的 Yahoo 值）", "",
          "| 账户 Calmar | Z 原 → 修正 | E 原 → 修正 | J 原 → 修正 |", "|---|---|---|---|"]
    for k in ("B0", "B1", "B2", "CRW"):
        L.append(f"| {k} | " + " | ".join(f"{res['orig'][e][k]['calmar']:.3f} → {res['fixed'][e][k]['calmar']:.3f}" for e in ("Z", "E", "J")) + " |")
    L += ["", "| 每一步的 Calmar 差 | 原口径 Z / E / J（合计） | 修正口径 Z / E / J（合计） |", "|---|---|---|"]
    for k in res["effects"]["orig"]:
        a, b = res["effects"]["orig"][k], res["effects"]["fixed"][k]
        L.append(f"| {k} | {a['Z']:+.3f} / {a['E']:+.3f} / {a['J']:+.3f}（{a['sum']:+.3f}） | {b['Z']:+.3f} / {b['E']:+.3f} / {b['J']:+.3f}（{b['sum']:+.3f}） |")
    L += ["", f"用时 {res['seconds']} s。只描述；要不要改研究口径、模拟盘的 FJE 要不要撤，由用户决定。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import equity_idle_study as EI
    from qbreak import factors
    t0 = time.time()
    inp = EI.load_inputs()
    ev = stamp_evidence(inp["fx"], factors.fred("DEXJPUS", max_age_h=1e9))
    orig = accounts("orig")
    fixed = accounts("fixed")
    res = {"evidence": ev, "orig": orig, "fixed": fixed, "effects": {"orig": effects(orig), "fixed": effects(fixed)},
           "seconds": round(time.time() - t0)}
    write(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
