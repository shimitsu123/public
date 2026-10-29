"""loop10_r03_relfx.py — 第十个研究循环（选股成功率：胜率提高、账户不变差）第 3 轮：胜率诊断里「三个年代都同号」、还没在 Zx 上看过的最后两个个股特征 →
RSB 比自己业种涨得多（个股 12-1 − 业种 12-1 在三分之一最高）不买 / BFX 对美元日元的 β（控制日経）在三分之一最高不买
（2026-10-04 登记；先提交后只运行一次；用掉 2 个做法 → 8 / 20；新家族「选股·相对业种过热」「选股·汇率敏感」各 1 / 3）。

循环的规则：scripts/research_loop10.py；共用：scripts/loop10_common.py；复用第 2 轮已登记、没改的纯函数（scripts/loop10_r02_diagfeat.py：feature_gate、scale 的写法）。
来历（照实写）：两个特征都来自胜率诊断（scripts/winrate_diag.py → var/out/winrate_diag.md 第六节：C 保留的假想单笔、三个年代都同号且 |ρ| ≥ 0.03）：
  rsec（个股 12-1 − 业种 12-1）ρ Z −0.209 / E −0.078 / J −0.102、b_fx（对美元日元的 β，控制日経）−0.078 / −0.060 / −0.071 → 看过 Z / E / J 的结果之后设计
  = **事后**，V6 适用（Zx 没看过：第 1 轮在 Zx 上看的是大盘闸门、第 2 轮是 r12 / clv / x2，不是这两个特征）。照实写：rsec 与第 2 轮的 r12 相关（都是 12-1 个月），
  r12 在 Zx 上已经看过（MOM：Zx 被挡的反而更好）→ RSB 的 V6 不算完全没看过的数据；b_fx 与看过的特征无直接关系。
  这两个特征在以前的「关联搭配」研究（scripts/combo_all_study.py）里 W / Jx 的相关也算过 → V4 的 W / Jx 不算完全没看过。
  第一〜九个循环与本循环第 1〜2 轮没有用这两个特征做门槛（第五个循环 X2F / H52 是调仓位；S6 的 K2 用的是对日経的 β，不是汇率 β）。
  照实写（证据不一致）：以前「选股质的飞跃」S5 探索（scripts/leap2_s5_explore.py，E / J）里汇率 β 两个年代方向相反；关联搭配研究（全部 W2 信号）
  与胜率诊断（C 保留）里 Z / E / J 都为负 → BFX 的先验弱。rsec 在关联搭配研究里也是三个年代同号为负。
门槛（一次写定；只用 Z / E / J 全部 425 个 W2 信号的特征分布 = 只数个数、没看结果；同第 2 轮「三分之一」的习惯）：
  - RSB：rsec > 0.03（rsec = 个股 12-1 对数涨跌 − 所在东证业种 12-1（成员对数收益等权）；2/3 分位 = +0.0342，取两位小数）；
  - BFX：b_fx > 0.12（b_fx = 信号日所在周之前 104 周周收益对「上周美元日元变化 + 当周日経」回归里美元日元的系数；2/3 分位 = +0.1179，取两位小数）。
  特征缺值 → 不挡。其余全部同 B3。
做法：都按个股挡（kind = "stock"）：（票, 信号日）成立 → em_tick 0。特征 = 研究面板 A / D 表里信号日收盘为止已知的值（combo_all_study.add_features）。
V4 / V6：W / Jx / Zx 用各自 D 表里同名的特征（同一个函数）。第二关（第一关全过的才做；另行登记）：kind = stock（种子 [20261004, 10, s]）。
设计前只数个数的核对（不看收益；var/out 不存）：同一天按代码倒序排候选 → 三个年代各只有 1 笔成交不同 → 「同一天多个候选时换一个买」（排序）改变不了什么，
  所以本轮仍是挡；J-Quants 的财务数据只从 2016 年起 → 不能做 E / W 的检验，不用。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：第 2 轮读法 = 挡掉约三成信号在 Z 都伤账户 → 两个都很可能 V3 不过；两个特征的相关都比 x2 弱（|ρ| 0.06〜0.21）→ V1（+2 pp）也不一定过；
  第一关各约 4%；「更好候选」各约 1%。
运行：python scripts/loop10_r03_relfx.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop10_r03_relfx.md / .json。非投资建议。
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

ROUND = 3
IDS = ("RSB", "BFX")
FAMILY = {"RSB": "选股·相对业种过热", "BFX": "选股·汇率敏感"}
KINDS = {k: "stock" for k in IDS}
POSTHOC = {k: True for k in IDS}
RULES = {"RSB": ("rsec", ">", 0.03), "BFX": ("b_fx", ">", 0.12)}
OUT = "loop10_r03_relfx"
feature_gate = R2.feature_gate


# ───────────────────────── 输入 ─────────────────────────
def gates(W: dict) -> dict:
    out = {k: {} for k in IDS}
    for e in C10.ERAS:
        S = C10.signals(W, e)
        for k in IDS:
            out[k][e] = feature_gate(S, RULES[k])
    return out


def other_fns() -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            return feature_gate(X, RULES[k])
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
    g = gates(W)
    ok = True
    for e in C10.ERAS:
        base = C10.acct(C10.L6.run(W, e))
        empty = C10.acct(C10.run_block(W, e, np.zeros(len(C10.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C10.KEYS)
        S = C10.signals(W, e)
        n = {k: len(C10.tick_of(S["ticker"], S["date"], g[k][e])) for k in IDS}
        ok &= same and all(v > 0 for v in n.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items()), flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx / Zx（只数个数）：" + json.dumps(other_scale(W, other_fns()), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C10.git_head("scripts/loop10_r03_relfx.py", "scripts/loop10_r02_diagfeat.py", "scripts/loop10_common.py",
                               "scripts/research_loop10.py", "scripts/loop9_r01_market.py")
    W = C10.load()
    g = gates(W)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C10.stage_one(W, g, other_fns(), POSTHOC, log=lambda m: print(m, flush=True))
    reg = R10.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C10.ERAS}
    res = {"loop": 10, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "rules": {k: list(v) for k, v in RULES.items()}, **r, "drift": drift, "scale": scale(W, g), "pool_counts": C10.pool_counts(W),
           "seconds": round(time.time() - t0)}
    text = C10.render(res, f"# 第十个研究循环第 {ROUND} 轮：RSB 个股 12-1 − 业种 12-1 > 0.03 不买 / BFX 对美元日元的 β（控制日経）> 0.12 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环第 3 轮：RSB / BFX（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
