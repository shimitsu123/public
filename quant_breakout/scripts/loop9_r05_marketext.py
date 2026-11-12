"""loop9_r05_marketext.py — 第九个研究循环（选股成功率）第 5 轮：日経短期过热 N25U、日経在回调中 NDD
（2026-10-04 登记；先提交后只运行一次；用掉 2 个做法 → 9 / 20；「选股·大盘过热（逆向）」2 / 3、「选股·大盘短期趋势（顺向）」3 / 3（到上限））。

循环的规则：scripts/research_loop9.py；共用：scripts/loop9_common.py；复用第 1 轮的纯函数（scripts/loop9_r01_market.py：on_days / n225 / b3_trade_keys）。
照实写：这两个在第 1 轮运行之前的规模核对（只数个数；scale9b 的 N25UP5 / NDD5）里就列着，不是看了任何一轮结果之后想的 → 不是事后（S7 不适用）。
  同一次核对里还有 N50DN（日経 50 日线 10 天前比现在高 = 均线向下）：与第 1 轮 N5D（日経在 50 日线下）太像（同一条 50 日线），
  而且「大盘短期趋势（顺向）」家族只剩 1 个名额 → 选与 N5D 不同的定义（离 60 日高点的回撤）NDD，N50DN 不登记、不占名额。
为什么：诊断说输赢主要看持有期间日経的方向（日経跌时胜率 J 24.1%）；进场时的大盘状态是能事先看到的。
  - N25U（逆向：短期过热不追）：信号日日経收盘比 25 日简单均线高 ≥ +5%（日本常用的「25 日线乖离率」买われすぎ线）→ 那天不开新仓。
    照实写：学术证据弱（指数的短期反转不稳定）；第 1 轮 ADH（宽度过热不追）在 Z 大幅变差（过热期是突破的好时候）→ 先验弱、方向可能相反。
  - NDD（顺向：回调中不买）：信号日日経收盘比之前 60 个交易日（含当天）的最高收盘低 ≥ 5% → 那天不开新仓（大盘在回调里，个股的突破更容易被拖下去）。
    照实写：与 N5D（+0.010、胜率 +3.0 pp、账户不变）同一家族、信息相近 → 先验弱〜中。
做法：都按日子挡（kind = "date"）：闸门成立 → 那天的全部信号 em_tick 0；其余全部同 B3。阈值（25 日、+5%、60 日、−5%）一次写定（S6 不适用）；S5、S8 适用。
  - 日経 = W["inp"]["n225"] 收盘；均线 / 最高都要满窗口（不够 → 不挡）；信号日收盘就知道（第二天开盘成交）。
S5：W / Jx 里 B3 会买的信号按同样的日子挡。第二关（第一关全过的才做；另行登记）：kind = date（日序列循环平移 400 次，k ∈ [250, N − 250]，种子 [20261004, s]）。
登记前的规模核对（只数个数、不看收益；2026-10-04）：N25U 闸门天数 Z 6.6% / E 8.5% / J 8.3%，挡掉 W2 信号 11 / 9 / 14，碰到 B3 成交 6 / 3 / 8（成交集中在过热的日子）；
  W 30 / 438、Jx 64 / 792。NDD 闸门天数 50.6% / 45.6% / 31.5%，挡掉 29 / 33 / 31，碰到成交 7 / 2 / 7；W 148、Jx 200。准确数字 = 登记节的接线核对。
事前预期（写在看结果之前）：N25U 碰到 17 笔成交（不少），方向多半与 ADH 一样为负，第一关约 3%；NDD 类似 N5D（胜率升、账户差不多），第一关约 4%；「更好候选」各约 0.5〜1%。
运行：python scripts/loop9_r05_marketext.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop9_r05_marketext.md / .json。非投资建议。
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

ROUND = 5
IDS = ("N25U", "NDD")
FAMILY = {"N25U": "选股·大盘过热（逆向）", "NDD": "选股·大盘短期趋势（顺向）"}
KINDS = {"N25U": "date", "NDD": "date"}
POSTHOC = False
MA_N, HOT = 25, 0.05
HI_N, DD = 60, -0.05
OUT = "loop9_r05_marketext"


# ───────────────────────── 纯函数（tests/test_loop9_r05.py） ─────────────────────────
def overheat_days(close: pd.Series, n: int = MA_N, thr: float = HOT) -> pd.Series:
    """收盘 ÷ n 日简单均线 − 1 ≥ thr（均线要满 n 天）。"""
    c = close.astype(float).dropna()
    return (c / c.rolling(n).mean() - 1 >= thr).fillna(False)


def drawdown_days(close: pd.Series, n: int = HI_N, thr: float = DD) -> pd.Series:
    """收盘 ÷ 最近 n 个交易日（含当天）的最高收盘 − 1 ≤ thr（要满 n 天）。"""
    c = close.astype(float).dropna()
    return (c / c.rolling(n).max() - 1 <= thr).fillna(False)


# ───────────────────────── 输入 ─────────────────────────
def day_gates(W: dict) -> dict:
    n = R1.n225(W)
    return {"N25U": overheat_days(n), "NDD": drawdown_days(n)}


def gates(W: dict, G: dict):
    out, days_on = {k: {} for k in IDS}, {k: {} for k in IDS}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        days = C9.days_of(W, e)
        for k in IDS:
            on = R1.on_days(G[k], days)
            days_on[k][e] = on
            out[k][e] = C9.gate_from_days(S, days, on)
    return out, days_on


def other_fn(G: dict, k: str):
    def fn(s, X, fa):
        return R1.on_days(G[k], pd.DatetimeIndex(pd.to_datetime(X["date"])))
    return fn


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


def other_scale(W: dict, G: dict) -> dict:
    import combo_all_common as CA
    out = {}
    for s, fold, _ in C9.OTHER:
        D = W["D"][s]
        X = D[CA.apply_c(W["c_fold"][fold], D)].reset_index(drop=True)
        out[s] = {"n": len(X), **{k: int(np.asarray(other_fn(G, k)(s, X, None)).sum()) for k in IDS}}
    return out


def wiring() -> int:
    t0 = time.time()
    W = C9.load()
    G = day_gates(W)
    g, days_on = gates(W, G)
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
              + "；闸门天数 " + "、".join(f"{k} {np.mean(days_on[k][e]) * 100:.1f}%" for k in IDS), flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx（只数个数）：" + json.dumps(other_scale(W, G), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C9.git_head("scripts/loop9_r05_marketext.py", "scripts/loop9_r01_market.py")
    W = C9.load()
    G = day_gates(W)
    g, days_on = gates(W, G)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C9.stage_one(W, g, {k: other_fn(G, k) for k in IDS}, posthoc=None, log=lambda m: print(m, flush=True))
    reg = R9.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C9.ERAS}
    res = {"loop": 9, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g),
           "gate_days_pct": {k: {e: round(float(np.mean(days_on[k][e]) * 100), 1) for e in C9.ERAS} for k in IDS},
           "seconds": round(time.time() - t0)}
    text = C9.render(res, f"# 第九个研究循环第 {ROUND} 轮：N25U 日経比 25 日线高 ≥ 5% 的日子不开新仓 / NDD 日経比 60 日高点低 ≥ 5% 的日子不开新仓（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环第 5 轮：N25U / NDD（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
