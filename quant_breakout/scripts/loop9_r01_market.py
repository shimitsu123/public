"""loop9_r01_market.py — 第九个研究循环（选股成功率）第 1 轮：进场时的大盘状态 —— 騰落レシオ过热 ADH、日経在 50 日线下 N5D
（2026-10-04 登记；先提交后只运行一次；用掉 2 个做法 → 2 / 20；新家族「选股·大盘过热（逆向）」1 / 3、「选股·大盘短期趋势（顺向）」1 / 3）。

用户（2026-10-04）：「分析胜率低的原因 继续研究提高选股成功率 一直循环到 比现阶段的更好」。循环的规则：scripts/research_loop9.py；共用：scripts/loop9_common.py。
为什么这两个（照实写）：诊断（scripts/winrate_diag.py，只描述）说决定输赢的最大因素是持有期间日経的方向 —— J 日経涨时胜率 69.7%、跌时 24.1%，
亏损单里 2/3 同期日経也在跌；实际成交全部在日経 200 日线之上（C 与牛熊分界已经管长期方向）。那么在 200 日线之上的「短期状态」能不能分出坏的进场时点？
两个方向相反的假设各试一个（同一轮、各自判定）：
  - ADH（逆向：太热了不追）：騰落レシオ（25 日）≥ 120 的日子不开日本个股新仓。騰落レシオ = 这个年代的日经225 池子里最近 25 个交易日
    上涨家数合计 ÷ 下跌家数合计 × 100（不含平盘）；120 是日本市场通用的「过热」线（证券公司 / 日经的市况解说常用；学术证据弱，照实写）。
  - N5D（顺向：大盘在回调就不买）：日経225 收盘 < 50 日简单均线的日子不开日本个股新仓。O'Neil（CAN SLIM 的 M）「大盘回调时不买突破」；
    Brock, Lakonishok & LeBaron（1992，Journal of Finance）均线规则对道琼斯指数有预测力（之后减弱）。
  以前没做过（盘点）：市场宽度 A50（站上 50 日线的比例，2026-09-27 breadth_study 不过）、ERG（效率比，第一个循环）、YSG（日元急升）、UBG（美股熊）、
  W2T / VTZ（日経 200 日线下加严量能）都试过；騰落レシオ与日経自己的 50 日线没有用来挡过新仓 → 都是新做法、不是事后组合（S7 不适用）；
  阈值（120、50 日）是通用的整数，一次写定、没有学（S6 不适用）；改个股买点 → S5 适用；S8 适用。
做法：两个都是按日子挡（kind = "date"）：信号日收盘时闸门成立 → 那天的全部信号 em_tick 0（不开新仓，名额留着、钱留在核心）；其余全部同 B3。
  - ADH 的騰落レシオ：每个年代用自己账户的日经225 池子（W["SM"][年代]["fa"] 的收盘）；当天没有 K 线的票不算；最近 25 个交易日上涨 / 下跌家数合计（至少 25 天）。
  - N5D：W["inp"]["n225"] 收盘（loop_common 的同一份日経225），50 日简单均线（至少 50 天）。
S5：W（扩大池 2006〜2016，用 E 那一折的 C；騰落レシオ用 E 年代的池子）与 Jx（时点 TOPIX 1000 里非日経225，2017〜，用 J 那一折；騰落レシオ用 J 的池子）
  里 B3 会买的信号按同样的日子挡 → 保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop9.stage1（S1〜S6 + S7 不适用 + S8）；两个各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "date"：每个年代把挡 / 不挡的日序列整体循环平移 k ∈ [250, N − 250]（种子 [20261004, s]，400 次）。
登记前的规模核对（只数个数、不看收益）：騰落レシオ ≥ 120 的日子 Z 15.9% / E 20.5% / J 23.4%；挡掉的 W2 信号 Z 31 / 97、E 39 / 155、J 46 / 173，
  碰到 B3 的实际成交 Z 10 / 35、E 16 / 43、J 22 / 62；W 90 / 438、Jx 210 / 792。
  N5D：日経在 50 日线下的日子（整个日経序列）约 40%；挡掉的 W2 信号 Z 33 / 97、E 41 / 155、J 57 / 173，碰到 B3 的实际成交 Z 8 / 35、E 4 / 43、J 11 / 62；
  W 155 / 438、Jx 266 / 792。
接线核对（登记前，不看候选的收益）：① 挡的集合为空 → 账户与 B3 逐项相同；② 两个做法在三个年代的 em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号与成交笔数、个股笔数、W / Jx 被挡的信号的胜率 / 每笔。
事前预期（照实写，写在看结果之前）：两个都挡得多（ADH 约三成成交），差会比较大但方向不确定；ADH 先验约 50 / 50（宽度过热之后常常还会涨 —— Zweig 的宽度推力），
  N5D 先验略好但 C 与牛熊分界已经管了大方向；第一关各约 5〜8%，第二关（日序列平移、挡的日子成片）各约 15% → 「更好候选」各约 1%。
运行：python scripts/loop9_r01_market.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop9_r01_market.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop9_common as C9                                                    # noqa: E402
import research_loop9 as R9                                                  # noqa: E402

ROUND = 1
IDS = ("ADH", "N5D")
FAMILY = {"ADH": "选股·大盘过热（逆向）", "N5D": "选股·大盘短期趋势（顺向）"}
POSTHOC = False
KIND = "date"
ADR_N, ADR_HOT = 25, 120.0
MA_N = 50
OUT = "loop9_r01_market"


# ───────────────────────── 纯函数（tests/test_loop9_r01.py） ─────────────────────────
def adr_series(closes: pd.DataFrame, n: int = ADR_N) -> pd.Series:
    """騰落レシオ：closes = 日期 × 票 的收盘（没有 K 线 = NaN）→ 最近 n 天上涨家数合计 ÷ 下跌家数合计 × 100（平盘不算；不够 n 天 / 下跌为 0 → NaN）。"""
    ch = closes.astype(float).diff()
    adv = (ch > 0).sum(axis=1).astype(float)
    dec = (ch < 0).sum(axis=1).astype(float)
    adv.iloc[0] = dec.iloc[0] = np.nan                                       # 第一天没有涨跌
    a, d = adv.rolling(n, min_periods=n).sum(), dec.rolling(n, min_periods=n).sum()
    return a / d.replace(0, np.nan) * 100


def hot_days(adr: pd.Series, hot: float = ADR_HOT) -> pd.Series:
    return (adr >= hot).fillna(False)


def below_ma_days(close: pd.Series, n: int = MA_N) -> pd.Series:
    """收盘 < n 日简单均线（不够 n 天 → 不成立）。"""
    c = close.astype(float).dropna()
    ma = c.rolling(n, min_periods=n).mean()
    return (c < ma).fillna(False) & ma.notna()


def on_days(series: pd.Series, days: pd.DatetimeIndex) -> np.ndarray:
    """日期索引的闸门 → 对齐到 days（这个年代的交易日；当天没有值 → 用之前最后一个，最开头 → 不成立）。"""
    s = series[~series.index.duplicated(keep="last")].astype(bool).sort_index()
    v = s.reindex(s.index.union(days)).ffill().reindex(days)
    return v.fillna(False).to_numpy(bool)


# ───────────────────────── 输入 ─────────────────────────
def closes_of(fa: dict) -> pd.DataFrame:
    return pd.DataFrame({t: df["Close"].astype(float) for t, df in fa.items()}).sort_index()


def n225(W: dict) -> pd.Series:
    x = W["inp"]["n225"]
    return (x["Close"] if isinstance(x, pd.DataFrame) else x).astype(float).dropna()


def day_gates(W: dict) -> dict:
    """{做法: {年代 / W / Jx: 日期索引的闸门（bool Series）}}。W 用 E 年代的池子、Jx 用 J 年代的池子算騰落レシオ。"""
    adr = {e: hot_days(adr_series(closes_of(W["SM"][e]["fa"]))) for e in C9.ERAS}
    adr["W"], adr["Jx"] = adr["E"], adr["J"]
    b50 = below_ma_days(n225(W))
    return {"ADH": adr, "N5D": {k: b50 for k in (*C9.ERAS, "W", "Jx")}}


def gates(W: dict, G: dict) -> dict:
    """{做法: {年代: bool 数组（与 signals(W, 年代) 同序）}} + 每个年代的日序列（第二关用）。"""
    out, days_on = {k: {} for k in IDS}, {k: {} for k in IDS}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        days = C9.days_of(W, e)
        for k in IDS:
            on = on_days(G[k][e], days)
            days_on[k][e] = on
            out[k][e] = C9.gate_from_days(S, days, on)
    return out, days_on


def other_fn(G: dict, k: str):
    def fn(s, X, fa):
        d = pd.DatetimeIndex(pd.to_datetime(X["date"]))
        return on_days(G[k][s], d)
    return fn


# ───────────────────────── 规模 / 接线 ─────────────────────────
def b3_trade_keys(W: dict, e: str) -> list:
    """B3 实际成交（窗口内买入、已平仓的日本个股）的（票, 信号日）。"""
    import jq_study as JS
    C9.L6.run(W, e)
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    a, b = W["ctx"][e]["windows"][e]
    tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(["1545.T", "1482.T", "1655.T", "2845.T"]) & (tr["reason"] != "end")]
    ed = pd.to_datetime(tr["entry_date"])
    tr = tr[((ed >= pd.Timestamp(a)) & (ed < pd.Timestamp(b or "2026-10-01"))).to_numpy()]
    days = C9.days_of(W, e)
    return [(str(t), days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)]) for t, d in zip(tr["ticker"], pd.to_datetime(tr["entry_date"]))]


def scale(W: dict, g: dict) -> dict:
    out = {}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        idx = {(str(t), pd.Timestamp(d)): i for i, (t, d) in enumerate(zip(S["ticker"], S["date"]))}
        keys = b3_trade_keys(W, e)
        pos = [idx.get(k) for k in keys]
        out[e] = {"signals": len(S), "b3_trades": len(keys),
                  **{k: {"signals_blocked": int(np.asarray(g[k][e]).sum()),
                         "trades_blocked": int(sum(bool(g[k][e][i]) for i in pos if i is not None))} for k in IDS}}
    return out


def wiring() -> int:
    t0 = time.time()
    W = C9.load()
    G = day_gates(W)
    g, _ = gates(W, G)
    ok = True
    for e in C9.ERAS:
        base = C9.acct(C9.L6.run(W, e))
        empty = C9.acct(C9.run_block(W, e, np.zeros(len(C9.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C9.KEYS)
        n = {k: len(C9.tick_of(C9.signals(W, e)["ticker"], C9.signals(W, e)["date"], g[k][e])) for k in IDS}
        ok &= same and all(v > 0 for v in n.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items()), flush=True)
    sc = scale(W, g)
    print("规模（只数个数）：" + json.dumps(sc, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


# ───────────────────────── 运行 ─────────────────────────
def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop9_r01_market.py", "scripts/loop9_common.py",
                                 "scripts/research_loop9.py", "scripts/loop6_common.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/candle_portfolio.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = C9.load()
    G = day_gates(W)
    g, days_on = gates(W, G)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C9.stage_one(W, g, {k: other_fn(G, k) for k in IDS}, posthoc=None, log=lambda m: print(m, flush=True))
    reg = R9.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C9.ERAS}
    res = {"loop": 9, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g),
           "gate_days_pct": {k: {e: round(float(np.mean(days_on[k][e]) * 100), 1) for e in C9.ERAS} for k in IDS},
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    L = [f"# 第九个研究循环第 {ROUND} 轮：进场时的大盘状态 —— ADH 騰落レシオ ≥ 120 不开新仓 / N5D 日経在 50 日线下不开新仓（第一关；规则见脚本开头）", "",
         f"代码 {res['code']}{'（有未提交的改动！）' if res['dirty'] else ''}；B3 与登记值的差：" + "、".join(f"{e} {_f(v, '{:+.4f}')}" for e, v in res["drift"].items()), "",
         "| 做法 | 年代 | Calmar（B3 → 候选） | 差 | 年化 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 | 闸门天数 | 挡掉的信号 / 成交 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in res["ids"]:
        for e in C9.ERAS:
            b, c = res["base"][e], res["cand"][k][e]
            sc = res["scale"][e][k]
            L.append(f"| {k} | {e} | {_f(b['calmar'])} → {_f(c['calmar'])} | {_f(None if c['calmar'] is None else c['calmar'] - b['calmar'], '{:+.3f}')} | "
                     f"{_f(c['cagr'], '{:+.2f}')}% | {_f(c['dd'], '{:.2f}')}% | {_f(c['h1'])} / {_f(c['h2'])} | {b['n']} → {c['n']} | "
                     f"{_f(b['win'], '{:.1f}')} → {_f(c['win'], '{:.1f}')}% | {_f(b['mean'], '{:+.2f}')} → {_f(c['mean'], '{:+.2f}')}% | "
                     f"{res['gate_days_pct'][k][e]}% | {sc['signals_blocked']} / {sc['trades_blocked']} |")
    L += ["", "## 第一关（S1〜S8）", ""]
    for k in res["ids"]:
        s = res["stage1"][k]
        su = s["success"]
        o = res["other"][k]
        L.append(f"- **{k}**：合计 {_f(s['sum'], '{:+.3f}')}（" + "、".join(f"{e} {_f(s['d'][e], '{:+.3f}')}" for e in C9.ERAS) + "）；"
                 + "、".join(f"{x} {'✓' if s[x] else '✗'}" for x in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"))
                 + f"；两半 {_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}；选股成功率 {_f(su['base']['win'], '{:.2f}')}% → {_f(su['cand']['win'], '{:.2f}')}%、"
                 f"每笔 {_f(su['base']['mean'], '{:+.3f}')} → {_f(su['cand']['mean'], '{:+.3f}')}%；W / Jx：" + "；".join(
                     f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}（被挡的 {_f(o[x]['gone_win'], '{:.1f}')}% / {_f(o[x]['gone_mean'], '{:+.2f}')}%；"
                     f"胜率差 {_f(o[x]['dwin'], '{:+.2f}')} pp、每笔差 {_f(o[x]['dmean'], '{:+.3f}')} pp）" for x in ("W", "Jx"))
                 + f" → **{'第一关全过（要另行登记第二关）' if s['ok'] else R9.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。只描述以外的判定按 scripts/research_loop9.py。非投资建议。"]
    text = "\n".join(L) + "\n"
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环第 1 轮：ADH / N5D（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
