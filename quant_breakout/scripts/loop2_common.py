"""loop2_common.py — 第二个研究循环（2026-10-02 登记，规则 scripts/research_loop2.py）的共用部分：基准 B1 与账户回测接口。

B1 = 今天（2026-10-02）模拟盘的规则（var/sim.json：idle_cash.mode = "Q1H"）在 Z / E / J 历史上能重现的部分
   = 第一个循环的 B0（scripts/loop_common.py：W2 + C 留一年代 + X6 + 闲置资金 + 判断层市场层，个股 4 × 25%、立花费用）
   + 闲置资金 Q1H（2026-10-02 用户「采用」的 FJE；研究循环第 15 轮 scripts/loop_r15_fxeunion.py 同一个「对冲中」与接法：
     FXE（USD/JPY 9 组急升多数决）或 JBH（日経熊且日元牛）→ 美股牛时对冲版纳指 2845、否则 1545；美股熊 → 现金），
   费用按 qbreak/fees.py 现在的表（2845 一手 1 口、滑点 0.10%；第一个循环的研究按缺省 0.03%）。
历史上的汇率用 FRED DEXJPUS（研究同一个；实盘用 Yahoo JPY=X，2017〜2026「对冲中」判定一致 95.4%，sim_changes 2026-10-02 配置变更）。
窗口、前后两半、J 的终点同 loop_common（Z 2001-01〜2006-09、E 2006-10〜2016-09、J 2017-01〜2026-09-30）。
run(W, e, **over)：在 B1 上再改一处 —— cfg_over / extra_core / extra_bear 按键合并（候选给的键覆盖 B1 的），其余参数与 loop_common.run 相同
（候选给的覆盖 B1 的；em_mult 与 B1 的新仓倍数相乘）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop_common as LCM                                                    # noqa: E402

ERAS = LCM.ERAS
J_END = LCM.J_END
MERGE_KEYS = ("cfg_over", "extra_core", "extra_bear")


def fje_states(W: dict):
    """(FXE 多数决急升中, JBH 对冲中, 合并的「对冲中」) —— 第 15 轮同一段代码。"""
    import loop_r15_fxeunion as U
    return U.states(W)


def b1_over(W: dict) -> dict:
    """B0 → B1 的改动（闲置资金 Q1H）：第 15 轮 fje_over 同一个接法。"""
    import loop_r04_yensurge as Y
    import loop_r15_fxeunion as U
    _, _, uni = fje_states(W)
    return U.fje_over(W, uni, Y.hedged_frame(W["inp"]))


def load(smoke_names: list[str] | None = None) -> dict:
    """B1 的全部输入 = loop_common.load() + W["b1"]（Q1H 的改动）。"""
    W = LCM.load(smoke_names)
    W["b1"] = b1_over(W)
    return W


def merge_over(b1: dict, over: dict) -> dict:
    """B1 的改动 + 候选的改动：cfg_over / extra_core / extra_bear 按键合并，其余由候选覆盖。"""
    out = dict(b1)
    for k, v in over.items():
        if k in MERGE_KEYS and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def run(W: dict, e: str, fr: dict | None = None, em_mult=None, **over) -> dict:
    """B1（或在它上面改一处）在年代 e 的账户：{cagr, dd, calmar, n, mean, win, h1, h2, years}。"""
    return LCM.run(W, e, fr=fr, em_mult=em_mult, **merge_over(W["b1"], over))


def baseline(W: dict) -> dict[str, dict]:
    return {e: run(W, e) for e in ERAS}
