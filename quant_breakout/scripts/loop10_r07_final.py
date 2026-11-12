"""loop10_r07_final.py — 第十个研究循环（选股成功率：胜率提高、账户不变差）第 7 轮（最后 3 个做法）：
HWN 5〜10 月不开新仓（Halloween 效应）/ VEX 20 日均量没有放大（20 日均量 ÷ 之前 60 日均量在三分之一最低）不买 / DYL 股息率低（三分之一最低）不买
（2026-10-05 登记；先提交后只运行一次；用掉 3 个做法 → 20 / 20；新家族「选股·季节」「选股·量能扩张」「选股·股息」各 1 / 3）。

循环的规则：scripts/research_loop10.py；共用：scripts/loop10_common.py；复用第 2 轮已登记、没改的纯函数（scripts/loop10_r02_diagfeat.py：feature_gate）。
ID 登记前已用 research_loop10.check_new_approaches 核对。
来历与先验（照实写）：
  - HWN（不是事后）：Bouman & Jacobsen（2002, AER「The Halloween Indicator, 'Sell in May and Go Away'」）—— 37 个市场里 36 个 5〜10 月的收益低于 11〜4 月，日本是明显的一个。
    这里只用在「日本个股的新仓」：信号日在 5〜10 月 → 不买（已有持仓照旧、闲置资金照旧）。以前的 Halloween 研究（2026-09-27，核心仓位 5〜10 月减半、美国 1950〜2005）
    是另一个用法（核心、美股），不是日本个股的突破；本项目没看过按月份分的突破结果（胜率诊断只有按年）→ 不是事后，V6 不适用（Zx 只报告）。
    门槛 = 日历（5 月 1 日〜10 月 31 日），事先写定。
  - VEX（事后）：关联搭配研究里 vexp（20 日均量 ÷ 之前 60 日均量）Z / E / J 都同号为正；以前 vthrust_study 的「W2 ∧ VEXP ≥ 1」在 2006〜2016 组合 Calmar 0.254 < W2 0.286（没过）
    → 已知「挡掉不放量的」会少买、伤组合。门槛 = 425 个 W2 信号的 1/3 分位 0.9371 → 0.94。V6 适用（Zx 上没看过 vexp）。
  - DYL（事后）：质的飞跃第 1 轮（leap_r1）里股息率是「两个年代、各子样本方向都一致」的特征（秩相关 +0.05〜+0.12），但组合更差（E）；美国横展开 AUC 约 0.49。
    门槛 = 1/3 分位 1.3292% → 1.33%（股息率 < 1.33% 不买；缺值不挡）。V6 适用（Zx 上没看过 dy）。
做法：HWN 按日子挡（kind = date）；VEX / DYL 按个股挡（kind = stock）；成立 → em_tick 0；特征 = 研究面板 A / D 表同名的列；缺值不挡。V4 / V6：W / Jx / Zx 同一个函数。
第二关（第一关全过的才做；另行登记）：stock → 逐个信号随机挡；date → 日序列循环平移（种子 [20261004, 10, s]）。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：HWN 挡掉约一半的信号 → 少买很多，Z（2003 / 2005 年下半年的大行情）的账户风险大；VEX / DYL 已知会伤组合（E）→ V3 不乐观；
  第一关 HWN 约 2%、VEX 约 2%、DYL 约 2%；「更好候选」各约 1%。
运行：python scripts/loop10_r07_final.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop10_r07_final.md / .json。非投资建议。
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
import loop10_r02_diagfeat as R2                                             # noqa: E402
import loop9_r01_market as R1                                                # noqa: E402
import research_loop10 as R10                                                # noqa: E402

ROUND = 7
IDS = ("HWN", "VEX", "DYL")
FAMILY = {"HWN": "选股·季节", "VEX": "选股·量能扩张", "DYL": "选股·股息"}
KINDS = {"HWN": "date", "VEX": "stock", "DYL": "stock"}
POSTHOC = {"HWN": False, "VEX": True, "DYL": True}
HWN_MONTHS = (5, 6, 7, 8, 9, 10)
RULES = {"VEX": ("vexp", "<", 0.94), "DYL": ("dy", "<", 1.33)}
OUT = "loop10_r07_final"
feature_gate = R2.feature_gate


# ───────────────────────── 纯函数（tests/test_loop10_r07.py） ─────────────────────────
def season_gate(dates, months=HWN_MONTHS) -> np.ndarray:
    """信号日的月份在 months 里 → True。"""
    d = pd.to_datetime(np.asarray(dates))
    return np.isin(np.asarray(d.month), np.asarray(months))


def gate_of(k: str, X: pd.DataFrame) -> np.ndarray:
    return season_gate(X["date"]) if k == "HWN" else feature_gate(X, RULES[k])


def same_day_consistent(dates, gate) -> bool:
    g = pd.Series(np.asarray(gate, bool), index=pd.to_datetime(np.asarray(dates)))
    return bool(len(g) == 0 or g.groupby(level=0).nunique().max() == 1)


# ───────────────────────── 输入 ─────────────────────────
def gates(W: dict) -> dict:
    out = {k: {} for k in IDS}
    for e in C10.ERAS:
        S = C10.signals(W, e)
        for k in IDS:
            out[k][e] = gate_of(k, S)
    return out


def other_fns() -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            return gate_of(k, X)
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
    st = R10.load_state()
    R10.check_new_approaches(st, [{"id": k, "family": FAMILY[k], "kind": KINDS[k], "posthoc": POSTHOC[k], "verdict": R10.FAIL1} for k in IDS],
                             R10.previous_ids(Path(__file__).resolve().parents[1] / "var"))
    W = C10.load()
    g = gates(W)
    ok = True
    for e in C10.ERAS:
        base = C10.acct(C10.L6.run(W, e))
        empty = C10.acct(C10.run_block(W, e, np.zeros(len(C10.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C10.KEYS)
        S = C10.signals(W, e)
        n = {k: len(C10.tick_of(S["ticker"], S["date"], g[k][e])) for k in IDS}
        cons = same_day_consistent(S["date"], g["HWN"][e])
        ok &= same and all(v > 0 for v in n.values()) and cons
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items())
              + f"；HWN 同一天一致 {'✓' if cons else '✗'}", flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx / Zx（只数个数）：" + json.dumps(other_scale(W, other_fns()), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C10.git_head("scripts/loop10_r07_final.py", "scripts/loop10_r02_diagfeat.py", "scripts/loop10_common.py",
                               "scripts/research_loop10.py", "scripts/loop9_r01_market.py")
    W = C10.load()
    g = gates(W)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C10.stage_one(W, g, other_fns(), POSTHOC, log=lambda m: print(m, flush=True))
    reg = R10.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C10.ERAS}
    res = {"loop": 10, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "rules": {"HWN": {"months": list(HWN_MONTHS)}, **{k: list(v) for k, v in RULES.items()}},
           **r, "drift": drift, "scale": scale(W, g), "pool_counts": C10.pool_counts(W), "seconds": round(time.time() - t0)}
    text = C10.render(res, f"# 第十个研究循环第 {ROUND} 轮：HWN 5〜10 月不开新仓 / VEX 20 日均量放大 < 0.94 不买 / DYL 股息率 < 1.33% 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环第 7 轮：HWN / VEX / DYL（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
