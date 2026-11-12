"""loop9_r03_relative.py — 第九个研究循环（选股成功率）第 3 轮：日本相对核心的趋势 JRC、开盘追高 GPT
（2026-10-04 登记；先提交后只运行一次；用掉 2 个做法 → 6 / 20；新家族「选股·日本相对核心」1 / 3、「选股·开盘追高」1 / 3）。

循环的规则：scripts/research_loop9.py；共用：scripts/loop9_common.py；复用第 1 轮的纯函数（scripts/loop9_r01_market.py：on_days / n225 / b3_trade_keys）。
照实写：这两个做法在第 1 轮运行时（还没看到第 1 轮结果）就列进了后续计划（JRC、GPT、AGE、N25U），本轮只是按计划取其中两个 → 不是事后（S7 不适用）。
为什么：诊断说账户层面真正的对手是核心（J 只有 43.5% 的个股交易跑赢 1545），而诊断第一轮的「胜率提高 ≠ 账户变好」也说明要按「跑赢核心」想。
  - JRC（日本相对核心）：信号日之前 60 个交易日，日経225（日元）的涨幅 < 核心（1545 合成价 = 纳指 100 × 美元日元）的涨幅 → 不开新仓（日本整体在输给核心时，
    新开的日本个股也多半跑不赢核心）。文献：国家指数之间的相对动量（Asness, Liew & Stevens 1997；Moskowitz, Ooi & Pedersen 2012 的跨资产动量）。
    照实写：以前的 dualmom_study（核心在美 / 日之间按相对强弱切换）不过、「相对强弱切换总是慢半拍」→ 先验中偏弱；这里只管个股新仓，不切换核心。
  - GPT（开盘追高）：信号日之后第一个交易日开盘价比信号日收盘高 > +1.5% → 不买（现在的寄付指値是收盘 × 1.03，> +3% 本来就不成交 → GPT 只多挡 +1.5%〜+3% 那一段）。
    文献：Berkman, Koch, Tuttle & Zhang（2012，JFQA「Paying attention: overnight returns and the hidden cost of buying at the open」）——
    受关注的股票（大涨、放量之后）开盘被散户追高，开盘价偏高、之后日内与几天内回吐；突破日正是「受关注」的日子。实盘的做法 = 寄付指値改成收盘 × 1.015。
    照实写：回测里用 em_tick 在信号日挡（与开盘时限价不成交等价；差别只是真实情况下那天可能已经卖了一部分核心、钱闲一天 —— 约 5% 的信号、影响很小，偏向 GPT）。
做法：JRC 按日子挡（kind = "date"），GPT 按个股挡（kind = "stock"）；其余全部同 B3。阈值（60 天、+1.5%）一次写定（S6 不适用）；S5、S8 适用。
  - JRC：日経 = W["inp"]["n225"] 收盘；核心 = W["assets"]["1545.T"] 收盘（日本交易日；之前最后一个值）；两者都要有 60 个交易日前的值（不够 → 不挡）。
  - GPT：每只票自己的 K 线（W["SM"][年代]["fa"]；W / Jx 用各自池子的 K 线）：信号日的下一根 K 线开盘 ÷ 信号日收盘 − 1，在 (+1.5%, +3%] 之间 → 挡。
S5：W / Jx 里 B3 会买的信号按同样的定义挡。第二关（第一关全过的才做；另行登记）：JRC kind = date（日序列平移）、GPT kind = stock（逐个信号随机挡）。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：JRC 挡得多（日本输给纳指的时候很多），第一关约 5%；GPT 挡得少（三个年代成交只碰到几笔），第一关约 3%；「更好候选」各约 1%。
运行：python scripts/loop9_r03_relative.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop9_r03_relative.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop9_common as C9                                                    # noqa: E402
import loop9_r01_market as R1                                                # noqa: E402
import research_loop9 as R9                                                  # noqa: E402

ROUND = 3
IDS = ("JRC", "GPT")
FAMILY = {"JRC": "选股·日本相对核心", "GPT": "选股·开盘追高"}
KINDS = {"JRC": "date", "GPT": "stock"}
POSTHOC = False
REL_N = 60
GAP_LO, GAP_HI = 0.015, 0.03
OUT = "loop9_r03_relative"


# ───────────────────────── 纯函数（tests/test_loop9_r03.py） ─────────────────────────
def rel_weak_days(jp: pd.Series, core: pd.Series, n: int = REL_N) -> pd.Series:
    """日本的每个交易日：日経最近 n 个交易日的涨幅 < 核心同期涨幅（核心按日経的日子取之前最后一个值）→ True；不够 n 天 → False。"""
    j = jp.astype(float).dropna()
    c = core.astype(float).dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    ca = c.reindex(c.index.union(j.index)).ffill().reindex(j.index)
    rj = j / j.shift(n) - 1
    rc = ca / ca.shift(n) - 1
    return ((rj < rc) & rj.notna() & rc.notna()).fillna(False)


def open_gap(df: pd.DataFrame | None, d) -> float:
    """信号日 d 的下一根 K 线开盘 ÷ d 的收盘 − 1；没有 → NaN。"""
    if df is None:
        return float("nan")
    d = pd.Timestamp(d)
    if d not in df.index:
        return float("nan")
    p = int(df.index.get_loc(d))
    if p + 1 >= len(df):
        return float("nan")
    c = float(df["Close"].iloc[p])
    o = float(df["Open"].iloc[p + 1])
    return o / c - 1 if c > 0 else float("nan")


def gap_gate(tickers, dates, fa: dict, lo: float = GAP_LO, hi: float = GAP_HI) -> np.ndarray:
    g = np.array([open_gap(fa.get(t), d) for t, d in zip(tickers, pd.to_datetime(np.asarray(dates)))], float)
    with np.errstate(invalid="ignore"):
        return np.isfinite(g) & (g > lo) & (g <= hi)


# ───────────────────────── 输入 ─────────────────────────
def core_close(W: dict) -> pd.Series:
    return W["assets"]["1545.T"]["Close"].astype(float)


def gates(W: dict):
    rel = rel_weak_days(R1.n225(W), core_close(W))
    out, days_on = {k: {} for k in IDS}, {"JRC": {}}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        days = C9.days_of(W, e)
        on = R1.on_days(rel, days)
        days_on["JRC"][e] = on
        out["JRC"][e] = C9.gate_from_days(S, days, on)
        out["GPT"][e] = gap_gate(S["ticker"].to_numpy(), S["date"].to_numpy(), W["SM"][e]["fa"])
    return out, days_on, rel


def other_fns(rel: pd.Series) -> dict:
    def jrc(s, X, fa):
        return R1.on_days(rel, pd.DatetimeIndex(pd.to_datetime(X["date"])))

    def gpt(s, X, fa):
        return gap_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), fa)
    return {"JRC": jrc, "GPT": gpt}


def scale(W: dict, g: dict) -> dict:
    out = {}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        idx = {(str(t), pd.Timestamp(d)): i for i, (t, d) in enumerate(zip(S["ticker"], S["date"]))}
        pos = [idx.get(k) for k in R1.b3_trade_keys(W, e)]
        out[e] = {"signals": len(S), "b3_trades": len(pos),
                  **{k: {"signals_blocked": int(np.asarray(g[k][e]).sum()),
                         "trades_blocked": int(sum(bool(g[k][e][i]) for i in pos if i is not None))} for k in IDS}}
    return out


def other_scale(W: dict, fns: dict) -> dict:
    import combo_all_common as CA
    out = {}
    for s, fold, sm in C9.OTHER:
        D = W["D"][s]
        X = D[CA.apply_c(W["c_fold"][fold], D)].reset_index(drop=True)
        out[s] = {"n": len(X), **{k: int(np.asarray(fn(s, X, W["SM"][sm]["fa"])).sum()) for k, fn in fns.items()}}
    return out


def wiring() -> int:
    t0 = time.time()
    W = C9.load()
    g, days_on, rel = gates(W)
    ok = True
    for e in C9.ERAS:
        base = C9.acct(C9.L6.run(W, e))
        empty = C9.acct(C9.run_block(W, e, np.zeros(len(C9.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C9.KEYS)
        S = C9.signals(W, e)
        n = {k: len(C9.tick_of(S["ticker"], S["date"], g[k][e])) for k in IDS}
        ok &= same and all(v > 0 for v in n.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items())
              + f"；JRC 闸门天数 {np.mean(days_on['JRC'][e]) * 100:.1f}%", flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx（只数个数）：" + json.dumps(other_scale(W, other_fns(rel)), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C9.git_head("scripts/loop9_r03_relative.py", "scripts/loop9_r01_market.py")
    W = C9.load()
    g, days_on, rel = gates(W)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C9.stage_one(W, g, other_fns(rel), posthoc=None, log=lambda m: print(m, flush=True))
    reg = R9.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C9.ERAS}
    res = {"loop": 9, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g),
           "gate_days_pct": {"JRC": {e: round(float(np.mean(days_on["JRC"][e]) * 100), 1) for e in C9.ERAS}},
           "seconds": round(time.time() - t0)}
    text = C9.render(res, f"# 第九个研究循环第 {ROUND} 轮：JRC 日本 60 天输给核心时不开新仓 / GPT 开盘高开 > +1.5% 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环第 3 轮：JRC / GPT（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
