"""loop6_common.py — 第六个研究循环第二段（2026-10-03 用户「采用 并且继续第六个研究循环」；规则 scripts/research_loop6.py 的「第二段」一节）的共用部分：
基准 B2 = 采用后的模拟盘（var/sim.json idle_cash.mode = "Q1HB"）在 Z / E / J 历史上能重现的部分
   = 第二〜六个循环的 B1（scripts/loop2_common.py：W2 + C 留一年代 + X6 + 核心 Q1H（FJE）+ 判断层，个股 4 × 25%、立花费用）
   + BCU（第六个循环第 1 轮 scripts/loop6_r01_bondcorr.py 同一个输入与接法：美股熊 且 S&P500 与 1482 合成价（东证 d 日 = 前一个美国收盘）
     最近 63 天日收益相关 < 0 → 闲置资金拿 1482；loop2_r02_bondrefuge.tbh_over）。
先决条件：B2 重算 = 第 1 轮 BCU 的第一关账户（research_loop6.B2_REF）。
run(W, e, **over)：在 B2 上再改一处（cfg_over / extra_core / extra_bear 按键合并，候选给的键覆盖 B2 的；改核心设定的候选要连 1482 / 键 US_BD 一起写）。
第三段（2026-10-03 用户 ㊼ ①；research_loop6.py 开头「九」）：基准 B3 = 撤掉 FJE 之后的模拟盘（Q1B）在修正口径下 —— load3()；run 同上（在 B3 上再改）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop2_r02_bondrefuge as T2                                            # noqa: E402
import loop6_r01_bondcorr as T                                               # noqa: E402

ERAS = L2.ERAS
J_END = L2.J_END
run = L2.run
merge_over = L2.merge_over


def bcu_over(W: dict) -> tuple[dict, dict]:
    """B1 → B2 的改动（BCU）：第 1 轮同一个输入（loop6_r01_bondcorr.inputs）与接法（tbh_over）。返回 (改动, 输入)。"""
    M = T.inputs(W)
    return T2.tbh_over(W["bear"]["US"], M["on_b"], M["fb"]), M


def load(smoke_names: list[str] | None = None) -> dict:
    """B2 的全部输入 = loop2_common.load() + BCU 的改动合并进 W["b1"]（之后 run(W, e, **over) 都在 B2 上再改）；
    W["b1_q1h"] = 原来的 B1 改动，W["bcu"] = BCU 的输入（1482 合成价、相关条件）。"""
    W = L2.load(smoke_names)
    ov, M = bcu_over(W)
    W["b1_q1h"] = W["b1"]
    W["b1"] = merge_over(W["b1"], ov)
    W["bcu"] = M
    return W


def baseline(W: dict) -> dict[str, dict]:
    return {e: run(W, e) for e in ERAS}


# ───────────────────────── 第三段（2026-10-03 用户 ㊼ ①：研究口径改成修正口径、撤掉 FJE；规则 scripts/research_loop6.py 开头「九」） ─────────────────────────
def b3_over(W: dict) -> tuple[dict, dict]:
    """B0 → B3 的改动 = 撤掉 FJE 之后的模拟盘（var/sim.json idle_cash.mode = "Q1B"）：美股牛 → 1545（键 US，同 B0）、
    美股熊且 S&P500 与 1482 合成价 63 天负相关 → 1482（BCU：第 1 轮同一个输入 loop6_r01_bondcorr.inputs 与条件 tbh_over 的键）、其余现金；follow。
    与 qbreak/idle_cash.MODES["Q1B"] 同一结构（键名不同：研究 US_BD = 生产 BR:BD）。返回 (改动, 输入)。"""
    import loop_r04_yensurge as Y
    M = T.inputs(W)
    xc = dict(W["kw"]["Z"]["extra_core"])                                    # B0 的 1545 合成价
    xc[T2.BOND_T] = M["fb"]
    return ({"cfg_over": {"core": {"1545.T": 1.0, T2.BOND_T: 1.0}, "core_index": {"1545.T": "US", T2.BOND_T: T2.BD_KEY}, "core_mode": "follow"},
             "extra_core": xc,
             "extra_bear": {T2.BD_KEY: Y.or_series(~W["bear"]["US"].astype(bool), ~M["on_b"].astype(bool))}}, M)


def b3_alt_over(W: dict) -> dict:
    """接线检查用：B2 的接法（第 15 轮 fje_over + 第 1 轮 tbh_over）里 FJE 的「对冲中」永远不成立 —— 必须与 b3_over 的账户完全相同。"""
    import loop_r04_yensurge as Y
    import loop_r15_fxeunion as U
    _, _, uni = L2.fje_states(W)
    never = pd.Series(False, index=uni.index)
    M = T.inputs(W)
    return L2.merge_over(U.fje_over(W, never, Y.hedged_frame(W["inp"])), T2.tbh_over(W["bear"]["US"], M["on_b"], M["fb"]))


def load3(smoke_names: list[str] | None = None) -> dict:
    """B3 的全部输入 = loop_common.load()（第一个循环的 B0，修正口径）+ W["b1"] = b3_over（之后 run(W, e, **over) 都在 B3 上再改）；W["bcu"] = BCU 的输入。"""
    import loop_common as LCM_
    W = LCM_.load(smoke_names)
    ov, M = b3_over(W)
    W["b1"] = ov
    W["bcu"] = M
    return W
