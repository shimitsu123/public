"""loop6_common.py — 第六个研究循环第二段（2026-10-03 用户「采用 并且继续第六个研究循环」；规则 scripts/research_loop6.py 的「第二段」一节）的共用部分：
基准 B2 = 采用后的模拟盘（var/sim.json idle_cash.mode = "Q1HB"）在 Z / E / J 历史上能重现的部分
   = 第二〜六个循环的 B1（scripts/loop2_common.py：W2 + C 留一年代 + X6 + 核心 Q1H（FJE）+ 判断层，个股 4 × 25%、立花费用）
   + BCU（第六个循环第 1 轮 scripts/loop6_r01_bondcorr.py 同一个输入与接法：美股熊 且 S&P500 与 1482 合成价（东证 d 日 = 前一个美国收盘）
     最近 63 天日收益相关 < 0 → 闲置资金拿 1482；loop2_r02_bondrefuge.tbh_over）。
先决条件：B2 重算 = 第 1 轮 BCU 的第一关账户（research_loop6.B2_REF）。
run(W, e, **over)：在 B2 上再改一处（cfg_over / extra_core / extra_bear 按键合并，候选给的键覆盖 B2 的；改核心设定的候选要连 1482 / 键 US_BD 一起写）。
"""
from __future__ import annotations

import sys
from pathlib import Path

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
