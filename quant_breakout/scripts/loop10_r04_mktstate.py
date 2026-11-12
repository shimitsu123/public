"""loop10_r04_mktstate.py — 第十个研究循环（选股成功率：胜率提高、账户不变差）第 4 轮：「关联搭配」研究里三个年代都同号的三个大盘状态 →
NVL 日経 20 日波动高（三分之一最高）的日子不开新仓 / BRD 日経225 成分站上 50 日线的比例低（三分之一最低）的日子不开新仓 /
N3M 日経 63 日涨跌低（三分之一最低）的日子不开新仓
（2026-10-05 登记；先提交后只运行一次；用掉 3 个做法 → 11 / 20；新家族「选股·大盘波动」「选股·大盘宽度」「选股·大盘中期趋势」各 1 / 3）。

循环的规则：scripts/research_loop10.py；共用：scripts/loop10_common.py；复用第 2 轮已登记、没改的纯函数（scripts/loop10_r02_diagfeat.py：feature_gate）。
为什么是这三个（照实写）：第 1〜3 轮的读法 = 按个股挡掉约三成信号在 Z（2001〜2006）都伤账户（那几年日本个股的突破整体跑赢核心）；
  按日子挡的话，Z 里大盘不安定的日子主要在 2001〜2003（B3 在 2001〜2002 年没有成交）→ 可能少碰 Z 的成交。
来历（照实写）：三个特征都来自「关联搭配」研究（scripts/combo_all_study.py → 2026-10-01 sim_changes「关联图」：全部 W2 信号的假想单笔，
  Z / E / J 三个年代都同号的 13 个特征里的三个大盘特征：n225_r63 正、breadth50 正、n225_vol20 负）→ 看过 Z / E / J 的结果 = **事后**，V6 适用。
  Zx 上没看过这三个特征；但 BRD / N3M 与第 1 轮看过的 N5D（日経在 50 日线下）相关（WMV 三选二 ≈ N5D，Zx 上看过）、N3M 与 JRC 一族也相关
  → 它们的 V6 不算完全没看过；NVL 与看过的闸门关系较弱。
  证据不一致：以前「选股质的飞跃」S3（scripts/leap2_s3_explore.py，E / J 的 W2 单笔）按行情分段开关「没有一个两个年代同方向」。
  以前的相关做法：宽度 A50（breadth_study：W2 ∧ A50 ≥ 0.6 在 2006〜2016 Calmar 0.217 → 0.268，但没过随机对照）；第九个循环 N5D / NDD；
  B3 已有的量化状态层（qbreak/regime.quant_regime_series：日経跌破 200 日线 / 离一年高点 −12% / 20 日波动 > 35% → 新仓倍数降低）—— NVL 的门槛比它低。
门槛（一次写定；只用 Z / E / J 全部 425 个 W2 信号的特征分布 = 只数个数、没看结果；同第 2〜3 轮「三分之一」的习惯；两位小数）：
  - NVL：n225_vol20 > 0.18（日経日收益 20 日标准差年化；信号里 2/3 分位 = 0.1823）；
  - BRD：breadth50 < 0.53（日経225 成分站上 50 日线的比例；1/3 分位 = 0.5281）；
  - N3M：n225_r63 < 0（日経 63 个交易日涨跌为负；1/3 分位 = +0.0019，取两位小数 = 0.00）。
  特征 = 信号日当天或之前最近一个已知值（combo_all_study.add_features 的 S3.asof_upto，与研究面板 A / D 表同一列）；缺值 → 不挡。其余全部同 B3。
做法：都是按日子挡（kind = "date"：同一天的全部信号同一个值）→ 那天的（票, 信号日）em_tick 0。V4 / V6：W / Jx / Zx 用各自 D 表同名的列（同一组日子）。
第二关（第一关全过的才做；另行登记）：kind = date（每个年代把「挡 / 不挡」的日序列循环平移，research_loop10.shift_days；日序列按同一个特征与门槛另行登记）。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：三个闸门在 Z 碰到的成交应少于第 2〜3 轮的个股闸门 → V3 有机会；但 BRD / N3M 像 N5D（第九个循环 Z −0.035、V4 不过）；
  V1（+2 pp）要看 E / J 挡掉的是不是输家；V6：2003 年中小型股在不安定的日子里大涨 → 有反向风险。第一关各约 5〜8%；「更好候选」各约 1〜2%。
运行：python scripts/loop10_r04_mktstate.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop10_r04_mktstate.md / .json。非投资建议。
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

ROUND = 4
IDS = ("NVL", "BRD", "N3M")
FAMILY = {"NVL": "选股·大盘波动", "BRD": "选股·大盘宽度", "N3M": "选股·大盘中期趋势"}
KINDS = {k: "date" for k in IDS}
POSTHOC = {k: True for k in IDS}
RULES = {"NVL": ("n225_vol20", ">", 0.18), "BRD": ("breadth50", "<", 0.53), "N3M": ("n225_r63", "<", 0.0)}
OUT = "loop10_r04_mktstate"
feature_gate = R2.feature_gate


# ───────────────────────── 纯函数（tests/test_loop10_r04.py） ─────────────────────────
def same_day_consistent(dates, gate) -> bool:
    """按日子挡的核对：同一天的信号要么全挡、要么全不挡。"""
    g = pd.Series(np.asarray(gate, bool), index=pd.to_datetime(np.asarray(dates)))
    return bool(len(g) == 0 or g.groupby(level=0).nunique().max() == 1)


def gated_days(dates, gate) -> int:
    """被挡的不同信号日的个数。"""
    d = pd.to_datetime(np.asarray(dates))[np.asarray(gate, bool)]
    return int(len(pd.unique(d)))


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
        out[e] = {"signals": len(S), "signal_days": int(S["date"].nunique()), "b3_trades": len(pos),
                  **{k: {"signals_blocked": int(np.asarray(g[k][e]).sum()), "days_blocked": gated_days(S["date"], g[k][e]),
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
        cons = {k: same_day_consistent(S["date"], g[k][e]) for k in IDS}
        ok &= same and all(v > 0 for v in n.values()) and all(cons.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items())
              + "；同一天一致 " + "、".join(f"{k} {'✓' if v else '✗'}" for k, v in cons.items()), flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx / Zx（只数个数）：" + json.dumps(other_scale(W, other_fns()), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C10.git_head("scripts/loop10_r04_mktstate.py", "scripts/loop10_r02_diagfeat.py", "scripts/loop10_common.py",
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
    text = C10.render(res, f"# 第十个研究循环第 {ROUND} 轮：NVL 日経 20 日波动 > 0.18 / BRD 站上 50 日线的比例 < 0.53 / N3M 日経 63 日涨跌 < 0 的日子不开新仓（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环第 4 轮：NVL / BRD / N3M（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
