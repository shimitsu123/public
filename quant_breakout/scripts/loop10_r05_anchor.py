"""loop10_r05_anchor.py — 第十个研究循环（选股成功率：胜率提高、账户不变差）第 5 轮：价格锚点与箱体 →
CGO 收盘低于一年成交量加权均价（套牢盘：浮亏为主）不买 / H52 收盘离 250 日最高价超过 15% 不买 / RNG 之前 60 日箱体太宽（三分之一最宽）不买
（2026-10-05 登记；先提交后只运行一次；用掉 3 个做法 → 14 / 20；新家族「选股·价格锚点」2 / 3、「选股·箱体宽松」1 / 3）。

循环的规则：scripts/research_loop10.py；共用：scripts/loop10_common.py；复用第 2 轮已登记、没改的纯函数（scripts/loop10_r02_diagfeat.py：feature_gate）。
来历与先验（照实写）：
  - CGO（不是事后）：Grinblatt & Han（2005, JFE「Prospect theory, mental accounting, and momentum」）—— 处置效应让「多数持有人浮盈」（capital gains overhang 高）
    的票之后更容易继续涨，浮亏多的票上涨时有解套卖压。这里用简化的参照价 = 信号日为止 260 个交易日的成交量加权平均收盘价（一年平均成本；
    论文用换手率衰减加权，没有发行股数的历史 → 用成交量加权近似）；CGO = 收盘 ÷ 参照价 − 1；门槛 0 = 「平均持有人浮亏」，事先写定、没有按数据选。
    这个特征以前没有在本项目里算过（研究面板 53 个特征里没有），没在 Z / E / J / W / Jx / Zx 上看过 → 不是事后，V6 不适用（Zx 只报告）。
    照实写：CGO 与 r12（12-1 个月涨跌）相关；胜率诊断里 r12 是「涨得多的反而差」（第 2 轮 MOM）→ 「挡掉浮亏的」与那个方向相反，先验和本项目的数据有冲突。
  - H52（按保守算事后）：George & Hwang（2004, JF「The 52-week high and momentum investing」）—— 接近 52 周高点的票之后更好；突破时离 250 日最高价还远
    （收盘 < 0.85 × 250 日最高）= 下跌趋势里的反弹，不买。0.85 是事先取的整数（信号里 hi52 的 1/3 分位 0.8965、1/10 分位 0.809 → 约挡两成）。
    hi52 在胜率诊断与关联搭配研究里算过（三个年代不同号，所以没列出）→ 保守地算事后，V6 适用（Zx 上没看过 hi52）。
  - RNG（事后）：关联搭配研究里 rng（之前 60 日箱体宽度）Z / E / J 都同号为负（箱体越宽越差）；C 只在「日経在 200 日线上 · VIX < 20」那一格用过 rng →
    这里在全部情况下挡三分之一最宽的：rng > 0.13（信号里 2/3 分位 0.1289）。看过 Z / E / J = 事后，V6 适用（Zx 上没看过 rng）。
门槛（一次写定）：CGO < 0；hi52 < 0.85；rng > 0.13。特征缺值（参照价不到 200 天等）→ 不挡。其余全部同 B3。
做法：都按个股挡（kind = "stock"）：（票, 信号日）成立 → em_tick 0。CGO 从各自的行情表算（Z / E / J = W["SM"][年代]["fa"]，W / Jx / Zx = 各池子的 fa；
  只用信号日收盘为止的数据）；hi52 / rng = 研究面板 A / D 表同名的列。第二关（第一关全过的才做；另行登记）：kind = stock（种子 [20261004, 10, s]）。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：CGO / H52 在 Z 会挡掉 2003〜2004 年从低位起来的突破（那时多数票浮亏、离一年高点远）→ V3 风险大；CGO 与诊断方向冲突 → V1 也不乐观；
  RNG 与第 2〜3 轮的个股闸门一样挡三分之一 → V3 风险大。第一关 CGO 约 3%、H52 约 3%、RNG 约 4%；「更好候选」各约 1%。
运行：python scripts/loop10_r05_anchor.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop10_r05_anchor.md / .json。非投资建议。
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

ROUND = 5
IDS = ("CGO", "H52", "RNG")
FAMILY = {"CGO": "选股·价格锚点", "H52": "选股·价格锚点", "RNG": "选股·箱体宽松"}
KINDS = {k: "stock" for k in IDS}
POSTHOC = {"CGO": False, "H52": True, "RNG": True}
RULES = {"CGO": ("cgo", "<", 0.0), "H52": ("hi52", "<", 0.85), "RNG": ("rng", ">", 0.13)}
CGO_N, CGO_MIN = 260, 200
OUT = "loop10_r05_anchor"
feature_gate = R2.feature_gate


# ───────────────────────── 纯函数（tests/test_loop10_r05.py） ─────────────────────────
def cgo_series(df: pd.DataFrame, n: int = CGO_N, min_n: int = CGO_MIN) -> pd.Series:
    """收盘 ÷（到当天为止 n 个交易日的成交量加权平均收盘）− 1；成交量合计 0 或不到 min_n 天 → 缺值。"""
    c = df["Close"].astype(float)
    v = df["Volume"].astype(float).clip(lower=0.0)
    pv = (c * v).rolling(n, min_periods=min_n).sum()
    vv = v.rolling(n, min_periods=min_n).sum()
    ref = pv / vv.where(vv > 0)
    return c / ref - 1.0


def cgo_feature(tickers, dates, fa: dict, n: int = CGO_N, min_n: int = CGO_MIN) -> np.ndarray:
    """（票, 信号日）→ 信号日当天的 CGO（行情表里没有那一天 / 没有那只票 → 缺值）。"""
    t_arr = np.asarray(tickers, dtype=object)
    d_arr = pd.to_datetime(np.asarray(dates))
    out = np.full(len(t_arr), np.nan)
    for t in pd.unique(t_arr):
        df = fa.get(t)
        if df is None or not len(df):
            continue
        s = cgo_series(df, n, min_n)
        m = t_arr == t
        out[m] = s.reindex(d_arr[m]).to_numpy(float)
    return out


def with_cgo(X: pd.DataFrame, fa: dict) -> pd.DataFrame:
    return X.assign(cgo=cgo_feature(X["ticker"], X["date"], fa))


# ───────────────────────── 输入 ─────────────────────────
def gates(W: dict) -> dict:
    out = {k: {} for k in IDS}
    for e in C10.ERAS:
        S = with_cgo(C10.signals(W, e), W["SM"][e]["fa"])
        for k in IDS:
            out[k][e] = feature_gate(S, RULES[k])
    return out


def other_fns() -> dict:
    cache: dict = {}

    def fn_of(k):
        def fn(s, X, fa):
            key = (s, len(X))
            if key not in cache:
                cache[key] = with_cgo(X, fa)
            return feature_gate(cache[key], RULES[k])
        return fn
    return {k: fn_of(k) for k in IDS}


def coverage(W: dict) -> dict:
    """只数个数：CGO 算得出的比例。"""
    out = {}
    for e in C10.ERAS:
        S = with_cgo(C10.signals(W, e), W["SM"][e]["fa"])
        out[e] = round(float(np.isfinite(S["cgo"].to_numpy(float)).mean()), 3)
    for s, fold, sm in C10.OTHER:
        X = with_cgo(C10.kept_pool(W, s, fold), W["SM"][sm]["fa"])
        out[s] = round(float(np.isfinite(X["cgo"].to_numpy(float)).mean()), 3)
    return out


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
    print("CGO 覆盖（只数个数）：" + json.dumps(coverage(W), ensure_ascii=False))
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx / Zx（只数个数）：" + json.dumps(other_scale(W, other_fns()), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C10.git_head("scripts/loop10_r05_anchor.py", "scripts/loop10_r02_diagfeat.py", "scripts/loop10_common.py",
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
           "cgo_coverage": coverage(W), "seconds": round(time.time() - t0)}
    text = C10.render(res, f"# 第十个研究循环第 {ROUND} 轮：CGO 收盘低于一年成交量加权均价 / H52 离 250 日最高 > 15% / RNG 60 日箱体宽 > 13% 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环第 5 轮：CGO / H52 / RNG（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
