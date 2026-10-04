"""loop10_r02_diagfeat.py — 第十个研究循环（选股成功率：胜率提高、账户不变差）第 2 轮：诊断里「三个年代都同号」的个股特征 →
MOM 12-1 个月涨幅最高的三分之一不买 / CLW 突破当天收在振幅下部（收盘位置最低的三分之一）不买 / X2G 顾客业种的短観业况变化 ≤ 0 不买
（2026-10-04 登记；先提交后只运行一次；用掉 3 个做法 → 6 / 20；新家族「选股·中期动量过高」「选股·突破日收盘弱」「选股·顾客业种景气」各 1 / 3）。

循环的规则：scripts/research_loop10.py；共用：scripts/loop10_common.py；复用第九个循环的纯函数（scripts/loop9_r01_market.py：b3_trade_keys）。
来历（照实写）：三个特征都来自胜率诊断（scripts/winrate_diag.py → var/out/winrate_diag.md 第六节「赢家与输家的个股特征」：C 保留的假想单笔、
  三个年代都同号且 |ρ| ≥ 0.03）：r12（12-1 个月涨跌）ρ Z −0.116 / E −0.077 / J −0.238、clv（收盘在当天振幅里的位置）+0.094 / +0.050 / +0.075、
  x2（顾客业种的短観业况变化）+0.414 / +0.159 / +0.093 → 是看过 Z / E / J 结果之后设计的 → **事后**，V6 适用（Zx 没看过：诊断只用了日経225 的 Z / E / J，
  第十个循环第 1 轮在 Zx 上看的是大盘闸门，不是这三个特征）。照实写：这三个特征在以前的「关联搭配」研究（scripts/combo_all_study.py）里
  W / Jx 的相关也算过 → V4 的 W / Jx 不算完全没看过；真正没看过的只有 Zx。
  以前做过的相关做法：第三个循环 RMO（残差动量最弱的一半不买，−0.622，方向相反）、第五个循环 H52（按离 52 周高点调仓位）、X2F（按 x2 调仓位，
  第一关不过）、现行的上影线过滤（上影 ≥ 实体 3 倍不买）—— 都不是这三个门槛。
门槛（一次写定；只用 Z / E / J 全部 W2 信号的特征分布 = 只数个数、没看结果；与 C 的「1/3 分位」同一个习惯）：
  - MOM：r12 > +0.12（r12 = log(21 个交易日前收盘 ÷ 252 个交易日前收盘)，对数；0.12 ≈ +12.7%；三个年代 425 个 W2 信号 r12 的 2/3 分位 = +0.119，取整）；
  - CLW：clv < 0.70（clv = (收盘 − 最低) ÷ (最高 − 最低)，信号日；1/3 分位 = 0.700）；
  - X2G：x2 ≤ 0（x2 = 信号日当天或之前最近一次已可用的短観：所在东证业种的顾客业种（按 2020 年产业连关表的销售份额加权）大企業业况 DI 的变化；
    符号；信号里 x2 > 0 的占 58%；顾客权重用 2020 年的表 = 以前 X2 研究同样的做法，对 2001〜2016 是后来的权重）。
  特征缺值 → 不挡。其余全部同 B3。
做法：都按个股挡（kind = "stock"）：（票, 信号日）成立 → em_tick 0。特征 = 研究面板 A / D 表里信号日收盘为止已知的值（combo_all_study.add_features）。
S5 → V4：W / Jx / Zx 用各自 D 表里同名的特征。第二关（第一关全过的才做；另行登记）：kind = stock（逐个信号随机挡同样比例，种子 [20261004, 10, s]）。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：三个都挡约三〜四成信号 → 改动大，钱多进核心；诊断的相关只有 |ρ| 0.05〜0.4 → 胜率 +2 pp 有可能，但 Z 的账户（V3）与 Zx（V6）
  是难关；第一关各约 8%；「更好候选」各约 1〜2%。
运行：python scripts/loop10_r02_diagfeat.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop10_r02_diagfeat.md / .json。非投资建议。
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
import research_loop10 as R10                                                # noqa: E402

ROUND = 2
IDS = ("MOM", "CLW", "X2G")
FAMILY = {"MOM": "选股·中期动量过高", "CLW": "选股·突破日收盘弱", "X2G": "选股·顾客业种景气"}
KINDS = {k: "stock" for k in IDS}
POSTHOC = {k: True for k in IDS}
RULES = {"MOM": ("r12", ">", 0.12), "CLW": ("clv", "<", 0.70), "X2G": ("x2", "<=", 0.0)}
OUT = "loop10_r02_diagfeat"


# ───────────────────────── 纯函数（tests/test_loop10_r02.py） ─────────────────────────
def feature_gate(X: pd.DataFrame, rule: tuple) -> np.ndarray:
    """（特征, 比较, 门槛）→ 成立的信号 True；特征缺值 / 没有这一列 → 不挡。"""
    f, op, thr = rule
    if f not in X.columns:
        return np.zeros(len(X), bool)
    x = X[f].to_numpy(float)
    ok = np.isfinite(x)
    with np.errstate(invalid="ignore"):
        hit = {">": x > thr, "<": x < thr, "<=": x <= thr, ">=": x >= thr}[op]
    return ok & hit


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
    code, dirty = C10.git_head("scripts/loop10_r02_diagfeat.py", "scripts/loop10_common.py", "scripts/research_loop10.py",
                               "scripts/loop9_r01_market.py")
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
    text = C10.render(res, f"# 第十个研究循环第 {ROUND} 轮：MOM 12-1 个月对数涨跌 > 0.12（≈ +12.7%）不买 / CLW 突破日收盘位置 < 0.70 不买 / X2G 顾客业种短観变化 ≤ 0 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环第 2 轮：MOM / CLW / X2G（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
