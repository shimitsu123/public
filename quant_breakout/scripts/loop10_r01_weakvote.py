"""loop10_r01_weakvote.py — 第十个研究循环（选股成功率：胜率提高、账户不变差）第 1 轮：
WMV 大盘弱势多数决 / MJR 大盘出货日 × 日本落后核心 / JRM 日本落后核心 ≥ 10 pp（宽松版 JRC）
（2026-10-04 登记；先提交后只运行一次；用掉 3 个做法 → 3 / 20；新家族「选股·大盘弱势（多数决）」「选股·出货日 × 相对核心」「选股·日本相对核心（宽松）」各 1 / 3）。

循环的规则：scripts/research_loop10.py；共用：scripts/loop10_common.py；复用第九个循环的纯函数（都已登记、没改）：
  scripts/loop9_r01_market.py（n225 / below_ma_days / on_days / b3_trade_keys）、scripts/loop9_r03_relative.py（core_close / rel_weak_days）、
  scripts/loop9_r05_marketext.py（drawdown_days）、scripts/loop9_r06_distrev.py（mdd_series：大盘出货日，含 IBD 作废规则）。
照实写：三个都是**事后**设计的（看过第九个循环 N5D / NDD / MDD / JRC 的全部结果之后的组合与变体）→ V6 适用：没看过的 Zx（扩大池 2001〜2006）上
  保留的胜率差 > 0、每笔差 ≥ 0 才算过。Zx 与 Z 是同一段时间 → 对按日子挡的做法只是「别的票、同一段时间」的复核（规则开头写过）。
为什么（第九个循环的读法，照实写）：按大盘状态挡能提高胜率（N5D +3.0 pp、NDD +1.7 pp、MDD +4.5 pp、JRC +16.6 pp），但每个都挡得很宽，
  Z（2001〜2006 日本强、核心弱）的账户都变差（−0.03〜−0.23）。三种减少「误挡」的做法：
  - WMV（多数决）：N5D（日経 < 50 日线）、NDD（日経比 60 日最高收盘低 ≥ 5%）、MDD（最近 25 天大盘出货日 ≥ 5 个）三个里至少两个成立 → 不开新仓
    （两种独立的「弱」都确认才挡；多数决的先例：第一个循环的 FJE / FXE）。
  - MJR（出货日 × 落后核心）：MDD ∧ JRC（日経 60 天涨幅 < 核心 1545 合成价 60 天涨幅）→ 不开新仓
    （只在「机构在出货」且「日本正在输给核心」时挡 —— 挡下的钱进核心，核心那时更强 → 直接对着「账户不变差」）。
  - JRM（宽松版 JRC）：日経 60 天涨幅 − 核心 60 天涨幅 ≤ −10 pp → 不开新仓（JRC 是 < 0，挡掉 E / J 八成成交；只挡落后得多的时候）。
    −10 pp 是整数的、事先写定的门槛（没有按结果搜）。
做法：都按日子挡（kind = "date"）：那天的全部信号 em_tick 0；其余全部同 B3。阈值一次写定（V5 不适用）；V4、V6 适用。
  - 日序列：N5D / NDD / JRC / JRM 用日経与核心（同一个序列）；MDD 的成交量按年代用各自的日経225 池子（Z / E / J）。
  - 其他池子用对应年代的日序列：W → E、Jx → J、Zx → Z。
第二关（第一关全过的才做；另行登记）：kind = date（日序列循环平移 400 次，种子 [20261004, 10, s]）→ 合起来的胜率差要大于 400 次里最大的。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：三个都比原来的单个闸门挡得少 → 账户的伤小一些，但胜率的提高也小一些；V1（+2 pp）与 V3（Z ≥ −0.02）同时过不容易；
  Zx 与 Z 同一段时间、Z 年代 N5D / NDD 的胜率是提高的 → V6 不一定是难关。第一关各约 8%；「更好候选」各约 1〜2%。
运行：python scripts/loop10_r01_weakvote.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop10_r01_weakvote.md / .json。非投资建议。
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
import loop10_common as C10                                                  # noqa: E402
import loop9_r01_market as R1                                                # noqa: E402
import loop9_r03_relative as R3                                              # noqa: E402
import loop9_r05_marketext as R5                                             # noqa: E402
import loop9_r06_distrev as R6                                               # noqa: E402
import research_loop10 as R10                                                # noqa: E402

ROUND = 1
IDS = ("WMV", "MJR", "JRM")
FAMILY = {"WMV": "选股·大盘弱势（多数决）", "MJR": "选股·出货日 × 相对核心", "JRM": "选股·日本相对核心（宽松）"}
KINDS = {k: "date" for k in IDS}
POSTHOC = {k: True for k in IDS}
VOTE_K = 2
REL_N, REL_GAP = 60, -0.10
ERA_OF = {"Z": "Z", "E": "E", "J": "J", "W": "E", "Jx": "J", "Zx": "Z"}
OUT = "loop10_r01_weakvote"


# ───────────────────────── 纯函数（tests/test_loop10_r01.py） ─────────────────────────
def vote_days(series: list[pd.Series], k: int = VOTE_K) -> pd.Series:
    """几条日序列（bool）对齐到所有日子的并集（之前最后一个值；没有 → False）→ 成立的条数 ≥ k。"""
    idx = pd.DatetimeIndex(sorted(set().union(*[s.index for s in series])))
    cnt = sum(s[~s.index.duplicated(keep="last")].astype(float).reindex(idx).ffill().fillna(0.0) for s in series)
    return cnt >= k


def both_days(a: pd.Series, b: pd.Series) -> pd.Series:
    return vote_days([a, b], 2)


def rel_gap_days(jp: pd.Series, core: pd.Series, n: int = REL_N, gap: float = REL_GAP) -> pd.Series:
    """日経最近 n 个交易日的涨幅 − 核心同期涨幅 ≤ gap（核心按日経的日子取之前最后一个值；不够 n 天 → False）。"""
    j = jp.astype(float).dropna()
    c = core.astype(float).dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    ca = c.reindex(c.index.union(j.index)).ffill().reindex(j.index)
    d = (j / j.shift(n) - 1) - (ca / ca.shift(n) - 1)
    return (d <= gap).fillna(False)


# ───────────────────────── 输入 ─────────────────────────
def day_series(W: dict) -> dict:
    """{做法: {年代: 日序列}}（Z / E / J；MDD 的成交量按年代）。"""
    n = R1.n225(W)
    core = R3.core_close(W)
    n5d, ndd = R1.below_ma_days(n, 50), R5.drawdown_days(n)
    jrc, jrm = R3.rel_weak_days(n, core), rel_gap_days(n, core)
    mdd = R6.mdd_series(W)
    out = {k: {} for k in IDS}
    for e in C10.ERAS:
        out["WMV"][e] = vote_days([n5d, ndd, mdd[e]])
        out["MJR"][e] = both_days(mdd[e], jrc)
        out["JRM"][e] = jrm
    return out


def gates(W: dict, G: dict):
    out, days_on = {k: {} for k in IDS}, {k: {} for k in IDS}
    for e in C10.ERAS:
        S = C10.signals(W, e)
        days = C10.days_of(W, e)
        for k in IDS:
            on = R1.on_days(G[k][e], days)
            days_on[k][e] = on
            out[k][e] = C10.gate_from_days(S, days, on)
    return out, days_on


def other_fns(G: dict) -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            return R1.on_days(G[k][ERA_OF[s]], pd.DatetimeIndex(pd.to_datetime(X["date"])))
        return fn
    return {k: fn_of(k) for k in IDS}


def scale(W: dict, g: dict) -> dict:
    out = {}
    for e in C10.ERAS:
        S = C10.signals(W, e)
        idx = {(str(t), pd.Timestamp(d)): i for i, (t, d) in enumerate(zip(S["ticker"], S["date"]))}
        pos = [idx.get(k) for k in R1.b3_trade_keys(W, e)]
        out[e] = {"signals": len(S), "b3_trades": len(pos),
                  **{k: {"signals_blocked": int(np.asarray(g[k][e]).sum()),
                         "trades_blocked": int(sum(bool(g[k][e][i]) for i in pos if i is not None))} for k in IDS}}
    return out


def other_scale(W: dict, fns: dict) -> dict:
    out = {}
    for s, fold, sm in C10.OTHER:
        X = C10.kept_pool(W, s, fold)
        out[s] = {"n": len(X), **{k: int(np.asarray(fn(s, X, W["SM"][sm]["fa"])).sum()) for k, fn in fns.items()}}
    return out


def wiring() -> int:
    t0 = time.time()
    W = C10.load()
    G = day_series(W)
    g, days_on = gates(W, G)
    ok = True
    for e in C10.ERAS:
        base = C10.acct(C10.L6.run(W, e))
        empty = C10.acct(C10.run_block(W, e, np.zeros(len(C10.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C10.KEYS)
        S = C10.signals(W, e)
        n = {k: len(C10.tick_of(S["ticker"], S["date"], g[k][e])) for k in IDS}
        ok &= same and all(v > 0 for v in n.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items())
              + "；闸门天数 " + "、".join(f"{k} {np.mean(days_on[k][e]) * 100:.1f}%" for k in IDS), flush=True)
    print("Zx 等池子 B3 会买的信号（只数个数）：" + json.dumps(C10.pool_counts(W), ensure_ascii=False))
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx / Zx（只数个数）：" + json.dumps(other_scale(W, other_fns(G)), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C10.git_head("scripts/loop10_r01_weakvote.py", "scripts/loop10_common.py", "scripts/research_loop10.py",
                               "scripts/loop9_r01_market.py", "scripts/loop9_r03_relative.py", "scripts/loop9_r05_marketext.py",
                               "scripts/loop9_r06_distrev.py")
    W = C10.load()
    G = day_series(W)
    g, days_on = gates(W, G)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C10.stage_one(W, g, other_fns(G), POSTHOC, log=lambda m: print(m, flush=True))
    reg = R10.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C10.ERAS}
    res = {"loop": 10, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g), "pool_counts": C10.pool_counts(W),
           "gate_days_pct": {k: {e: round(float(np.mean(days_on[k][e]) * 100), 1) for e in C10.ERAS} for k in IDS},
           "seconds": round(time.time() - t0)}
    text = C10.render(res, f"# 第十个研究循环第 {ROUND} 轮：WMV 大盘弱势多数决 / MJR 出货日 × 日本落后核心 / JRM 日本落后核心 ≥ 10 pp（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环第 1 轮：WMV / MJR / JRM（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
