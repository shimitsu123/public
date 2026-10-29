"""jq_vs_yf_study.py — 日本个股日线：J-Quants vs Yahoo（yfinance）比较研究（2026-10-11 登记；先提交后只运行一次）。

用户（2026-10-11）：「日线的比较研究」（在「决算日程换 J-Quants 为主」之后；是否把模拟盘 / 执行器的日本日线换成 J-Quants 的判断材料）。
现状：模拟盘 / 执行器的日本日线 = yfinance（auto_adjust：拆股 + 分红都调整）；J-Quants 每天交叉核对（只报警）。
      研究的 J 年代（2017-01〜2026-09）本来就用 J-Quants（拆股调整、不含分红调整、当时真实的一手）。
做法（同一套规则、同一批票、同一段日子，只换日线的来源）：
  - 票 = 今天的日経225（J 年代的 U0：leap_confirm.context("J")）；日子 = 那个 context 的日子；窗口 = J（2017-01〜2026-09-30）与前后两半。
  - JQ：context 原样（J-Quants 批量日线）。YF：同一批票的 yfinance 日线（leap_confirm.yf_panel，去掉成交量 0 的假行）对齐到同样的日子与票；
    「当时真实的一手」比例两边都用 J-Quants 的（只比较价格 / 成交量带来的差别）。
  - 规则 = 现行个股层能在历史上重现的部分：突破买点（p0 = 去掉 W2 的现行参数）∧ W2（周线量比 ≥ 1）、离场 X6、4 个名额、立花费用、
    闲置资金 Q1（纳指 1545 + 美股牛熊分界；loop_common.q1_spec）。不含 C 关联搭配、判断层（两边相同地不含，只为比较数据源）。
比较（全部只描述；不选「回测更好的那个」）：
  ① 买入信号（entry ∧ W2）：两边各有多少个（票, 日）、一致的比例（交集 ÷ 并集）、只在一边的个数；
  ② 实际成交：两边的个股交易（买入日、票）一致的比例；
  ③ 账户：J 与前后两半的年化 / 最大回撤 / Calmar、交易笔数；
  ④ 价格本身：每只票每天收盘涨跌幅之差 > 1 pp 的天数（分红调整、缺天、复权错位），列出最多的 10 只。
事先写定的读法（看结果之前）：
  - 选数据源看「哪个更准」（J-Quants = 交易所官方），**不看哪个回测更好**（那是挑结果）。
  - 「差异小」= ① 一致 ≥ 95% 且 ② 一致 ≥ 90% 且 J 的 Calmar 差的绝对值 ≤ 0.05 → 换不换主要看稳健性（Yahoo 偶尔出错 vs J-Quants 要一直付费 / 多一个停摆点）。
  - 否则「差异大」→ 先看 ④ 差在哪里（分红调整 / 缺天 / 复权错位）再决定；换源之前还要并行观察（影子）几周、用户确认。
  - 不管哪种，本研究不改模拟盘 / 执行器。
运行：python scripts/jq_vs_yf_study.py → var/out/jq_vs_yf_study.md / .json（只有汇总数字，不含 J-Quants 原始数据）。非投资建议。
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
import leap_confirm as LF                                                    # noqa: E402
import loop_common as LC                                                     # noqa: E402

OUT = "jq_vs_yf_study"
DIFF_PP = 1.0
SMALL = {"signal": 95.0, "trade": 90.0, "calmar": 0.05}


def yf_context(ctx: dict) -> dict:
    """J 的 context → 同一批票、同样的日子，日线换成 yfinance（缺的格子 = NaN）；一手比例 / 窗口 / 退市照旧。"""
    names = [ctx["names"][j] for j in ctx["cols"]]
    days = ctx["days"]
    P, dy, nm = LF.yf_panel(names, str(days[0].date()), str(days[-1].date()))
    pos = {t: j for j, t in enumerate(nm)}
    rows = pd.Index(dy).get_indexer(days)
    out = {}
    for k, v in ctx["P"].items():
        a = np.full(v.shape, np.nan)
        if k in P:
            for j in ctx["cols"]:
                t = ctx["names"][j]
                if t in pos:
                    col = P[k][:, pos[t]]
                    a[:, j] = np.where(rows >= 0, col[np.clip(rows, 0, None)], np.nan)
        out[k] = a
    cols = [j for j in ctx["cols"] if np.isfinite(out["C"][:, j]).sum() >= 80]
    return {**ctx, "P": out, "cols": cols}


def entries(fr: dict) -> set[tuple[str, str]]:
    return {(t, str(d.date())) for t, df in fr.items() for d in df.index[df["entry"].to_numpy(bool)]}


def overlap(a: set, b: set) -> dict:
    u, i = a | b, a & b
    return {"a": len(a), "b": len(b), "both": len(i), "only_a": len(a - b), "only_b": len(b - a),
            "agree_pct": round(len(i) / len(u) * 100, 1) if u else None}


def price_diff(ctxj: dict, ctxy: dict, names: list[str]) -> dict:
    """每只票：两边都有收盘的日子里，日涨跌幅之差 > DIFF_PP 的天数；J 窗口内。"""
    days = ctxj["days"]
    a, b = pd.Timestamp(ctxj["start"]), pd.Timestamp(ctxj["end"])
    m = (days >= a) & (days <= b)
    col = {t: j for j, t in enumerate(ctxj["names"])}
    per, tot, n = {}, 0, 0
    for t in names:
        j = col[t]
        cj, cy = ctxj["P"]["C"][m, j], ctxy["P"]["C"][m, j]
        rj, ry = np.diff(cj) / cj[:-1] * 100, np.diff(cy) / cy[:-1] * 100
        ok = np.isfinite(rj) & np.isfinite(ry)
        k = int((np.abs(rj - ry)[ok] > DIFF_PP).sum())
        per[t] = {"days": int(ok.sum()), "diff_days": k}
        tot += k
        n += int(ok.sum())
    top = sorted(per.items(), key=lambda kv: -kv[1]["diff_days"])[:10]
    return {"total_days": n, "diff_days": tot, "diff_pct": round(tot / n * 100, 3) if n else None, "top": top}


def account(ctx: dict, fr: dict, px, kw: dict) -> tuple[dict, set]:
    import jq_study as JS
    r = LF.run(ctx, LF.runner(ctx, fr), fr, px, **kw)
    eng = JS.RealLotEngine.LAST[-1]
    tr = pd.DataFrame(eng.st.trades)
    trades = set()
    if len(tr):
        tr = tr[(tr["ticker"] != "1655.T") & tr["ticker"].astype(str).str.endswith(".T")]
        trades = {(str(x.ticker), str(x.entry_date)[:10]) for x in tr.itertuples()}
    keys = ("cagr", "dd", "calmar", "n", "mean", "win")
    return {w: {k: (r.get(w) or {}).get(k) for k in keys} for w in ctx["windows"]}, trades


def main() -> int:
    from qbreak import exit_rules as EXR
    from qbreak import paths
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, "X6")
    kw = LC.q1_spec()[0]
    ctxj = LC.fix_j_end(LF.context("J"))
    ctxy = yf_context(ctxj)
    common = [ctxj["names"][j] for j in ctxy["cols"]]
    ctxj = {**ctxj, "cols": [j for j in ctxj["cols"] if ctxj["names"][j] in set(common)]}
    res = {"study": OUT, "names": len(common), "window": [ctxj["start"], ctxj["end"]]}
    fr, acc, tr = {}, {}, {}
    for tag, ctx in (("JQ", ctxj), ("YF", ctxy)):
        fa = LF.frames(ctx, p0)
        fr[tag] = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        acc[tag], tr[tag] = account(ctx, fr[tag], px, kw)
        print(f"{tag} 完成（{time.time() - t0:.0f}s）", flush=True)
    a, b = pd.Timestamp(ctxj["start"]), pd.Timestamp(ctxj["end"])
    inwin = lambda s: {x for x in s if a <= pd.Timestamp(x[1]) <= b}             # noqa: E731
    res["signals"] = overlap(inwin(entries(fr["JQ"])), inwin(entries(fr["YF"])))
    res["trades"] = overlap(tr["JQ"], tr["YF"])
    res["account"] = acc
    res["price"] = price_diff(ctxj, ctxy, common)
    dc = None if acc["JQ"]["J"]["calmar"] is None or acc["YF"]["J"]["calmar"] is None else acc["JQ"]["J"]["calmar"] - acc["YF"]["J"]["calmar"]
    small = (res["signals"]["agree_pct"] or 0) >= SMALL["signal"] and (res["trades"]["agree_pct"] or 0) >= SMALL["trade"] \
        and dc is not None and abs(dc) <= SMALL["calmar"]
    res["calmar_diff_jq_minus_yf"] = None if dc is None else round(dc, 3)
    res["reading"] = "差异小" if small else "差异大"
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    f = lambda v, s="{:.3f}": "—" if v is None else s.format(v)                 # noqa: E731
    s, t, pr = res["signals"], res["trades"], res["price"]
    L = [f"# 日本个股日线：J-Quants vs Yahoo（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/jq_vs_yf_study.py 开头）", "",
         f"**读法（事先写定）：{res['reading']}**（信号一致 ≥ 95%、成交一致 ≥ 90%、J 的 Calmar 差 ≤ 0.05 才算「差异小」）", "",
         f"- 票：今天的日経225 里两边都有数据的 {res['names']} 只；窗口 {res['window'][0]}〜{res['window'][1]}",
         f"- ① 买入信号（突破 ∧ W2）：J-Quants {s['a']} 个、Yahoo {s['b']} 个、两边都有 {s['both']}（只在 J-Quants {s['only_a']} / 只在 Yahoo {s['only_b']}）→ 一致 {f(s['agree_pct'], '{:.1f}')}%",
         f"- ② 实际成交（票, 买入日）：J-Quants {t['a']} 笔、Yahoo {t['b']} 笔、相同 {t['both']} → 一致 {f(t['agree_pct'], '{:.1f}')}%",
         f"- ④ 日涨跌幅之差 > {DIFF_PP:g} pp 的天数：{pr['diff_days']:,} / {pr['total_days']:,}（{f(pr['diff_pct'], '{:.3f}')}%）；最多的："
         + "、".join(f"{k} {v['diff_days']} 天" for k, v in pr["top"]), "",
         "| 窗口 | J-Quants 年化 / 最大回撤 / Calmar / 笔数 | Yahoo 年化 / 最大回撤 / Calmar / 笔数 |", "|---|---|---|"]
    for w in res["account"]["JQ"]:
        x, y = res["account"]["JQ"][w], res["account"]["YF"][w]
        cell = lambda z: f"{f(z['cagr'], '{:+.2f}')}% / {f(z['dd'], '{:.2f}')}% / {f(z['calmar'])} / {z['n']}"   # noqa: E731
        L.append(f"| {w} | {cell(x)} | {cell(y)} |")
    L += ["", f"J 的 Calmar 差（J-Quants − Yahoo）{f(res['calmar_diff_jq_minus_yf'], '{:+.3f}')}。只描述；选数据源看准不准、不看哪个回测更好；"
          f"本研究不改模拟盘 / 执行器。用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
