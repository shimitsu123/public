"""loop10_r06_riskdisp.py — 第十个研究循环（选股成功率：胜率提高、账户不变差）第 6 轮：
RKB 高风险特征三选二（60 日波动高 / 对日経 β 高 / 与日経 60 日相关高，各取三分之一最高，至少两条成立）不买 /
DSW 横截面分散度高（日経225 成分 20 日收益的横截面离散，三分之一最高）的日子不开新仓 / USR S&P 500 近 63 日下跌的日子不开新仓
（2026-10-05 登记；先提交后只运行一次；用掉 3 个做法 → 17 / 20；新家族「选股·高风险特征（多数决）」「选股·横截面分散」「选股·美股回调」各 1 / 3）。

循环的规则：scripts/research_loop10.py；共用：scripts/loop10_common.py；复用第 2 轮已登记、没改的纯函数（scripts/loop10_r02_diagfeat.py：feature_gate）。
ID 登记前已用 research_loop10.check_new_approaches 核对（RSK / DSP / COR 以前的循环用过 → 不用）。
来历与先验（照实写；三个都算**事后**，V6 = Zx；这三组特征在 Zx 上都没看过）：
  - RKB：低波动 / 低 β 异象（Blitz & van Vliet 2007、Frazzini & Pedersen 2014，日本也有）与「与指数低相关 = 个别驱动」（S7 探索 E / J 同方向；美国横展开 U3 不成立）。
    关联搭配研究里 vol60 三个年代同号为负；S5 探索「对日経 β 低的突破略好」（E / J）。照实写：第四个循环 CWX 的 C 学成「粗的低 β / 低波动过滤」后
    Z 少买 11 / 35 笔（多是赢家）、账户 −0.139 → 单个特征挡三分之一会伤 Z；这里要三条里两条同时成立（信号里约 28.5%）。
    门槛 = 425 个 W2 信号的 2/3 分位（只数个数）：vol60 0.2304 → 0.23、b_n225 0.873 → 0.87、corr60 0.5904 → 0.59（两位小数）；某一条缺值 = 那一条不成立。
  - DSW：Stivers & Sun（2010, JFQA）—— 横截面收益分散度高之后动量收益低；disp20 在关联搭配研究里算过（三个年代不同号）。门槛 = 2/3 分位 0.0760 → 0.076（两位有效数字）。
  - USR：美股回调时日本的突破更容易失败（全球风险偏好）；以前第一个循环 UBG（美股熊市不开日本新仓，B0）不过；看过胜率诊断的逐年结果（2022 年 5 笔 20%）→ 事后。
    门槛 0（S&P 500 近 63 个交易日涨跌为负；信号里约 21%），事先写定的符号门槛。
做法：RKB 按个股挡（kind = stock）；DSW / USR 按日子挡（kind = date：同一天的全部信号同一个值）；成立 → em_tick 0；特征 = 研究面板 A / D 表同名的列（信号日为止已知的值）；缺值不挡。
V4 / V6：W / Jx / Zx 用各自 D 表同名的列。第二关（第一关全过的才做；另行登记）：stock → 逐个信号随机挡；date → 日序列循环平移（种子 [20261004, 10, s]）。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：RKB 很可能像 CWX 一样伤 Z（V3）；DSW / USR 按日子挡在 Z 的伤可能小（第 4 轮 BRD / N3M），但第 4 轮显示 2017 年以后大盘状态的作用变弱（J / Jx）；
  第一关 RKB 约 2%、DSW 约 3%、USR 约 4%；「更好候选」各约 1%。
运行：python scripts/loop10_r06_riskdisp.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop10_r06_riskdisp.md / .json。非投资建议。
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

ROUND = 6
IDS = ("RKB", "DSW", "USR")
FAMILY = {"RKB": "选股·高风险特征（多数决）", "DSW": "选股·横截面分散", "USR": "选股·美股回调"}
KINDS = {"RKB": "stock", "DSW": "date", "USR": "date"}
POSTHOC = {k: True for k in IDS}
RKB_PARTS = (("vol60", ">", 0.23), ("b_n225", ">", 0.87), ("corr60", ">", 0.59))
RKB_MIN = 2
RULES = {"DSW": ("disp20", ">", 0.076), "USR": ("spx_r63", "<", 0.0)}
OUT = "loop10_r06_riskdisp"
feature_gate = R2.feature_gate


# ───────────────────────── 纯函数（tests/test_loop10_r06.py） ─────────────────────────
def vote_gate(X: pd.DataFrame, parts=RKB_PARTS, k: int = RKB_MIN) -> np.ndarray:
    """几条门槛里至少 k 条成立 → True；某一条缺值 / 没有那一列 = 那一条不成立。"""
    n = np.zeros(len(X), int)
    for rule in parts:
        n += feature_gate(X, rule).astype(int)
    return n >= k


def gate_of(k: str, X: pd.DataFrame) -> np.ndarray:
    return vote_gate(X) if k == "RKB" else feature_gate(X, RULES[k])


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
        cons = {k: same_day_consistent(S["date"], g[k][e]) for k in ("DSW", "USR")}
        ok &= same and all(v > 0 for v in n.values()) and all(cons.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items())
              + "；按日子的同一天一致 " + "、".join(f"{k} {'✓' if v else '✗'}" for k, v in cons.items()), flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx / Zx（只数个数）：" + json.dumps(other_scale(W, other_fns()), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C10.git_head("scripts/loop10_r06_riskdisp.py", "scripts/loop10_r02_diagfeat.py", "scripts/loop10_common.py",
                               "scripts/research_loop10.py", "scripts/loop9_r01_market.py")
    W = C10.load()
    g = gates(W)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C10.stage_one(W, g, other_fns(), POSTHOC, log=lambda m: print(m, flush=True))
    reg = R10.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C10.ERAS}
    res = {"loop": 10, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "rules": {"RKB": {"parts": [list(p) for p in RKB_PARTS], "min": RKB_MIN}, **{k: list(v) for k, v in RULES.items()}},
           **r, "drift": drift, "scale": scale(W, g), "pool_counts": C10.pool_counts(W), "seconds": round(time.time() - t0)}
    text = C10.render(res, f"# 第十个研究循环第 {ROUND} 轮：RKB 高风险特征三选二不买 / DSW 横截面分散 > 0.076 / USR S&P 500 近 63 日下跌 的日子不开新仓（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环第 6 轮：RKB / DSW / USR（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
