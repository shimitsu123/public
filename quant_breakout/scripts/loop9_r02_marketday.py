"""loop9_r02_marketday.py — 第九个研究循环（选股成功率）第 2 轮：大盘带动的突破 BXT、美股在 50 日线下 S5D
（2026-10-04 登记；先提交后只运行一次；用掉 2 个做法 → 4 / 20；新家族「选股·假突破（大盘带动）」1 / 3；「选股·大盘短期趋势（顺向）」2 / 3）。

循环的规则：scripts/research_loop9.py；共用：scripts/loop9_common.py；第 1 轮：scripts/loop9_r01_market.py（本轮复用它的纯函数 on_days / below_ma_days）。
照实写：本轮的两个做法在第 1 轮运行之前就定下（同一份诊断的两条线：「假突破」与「进场时的大盘状态」），不是看了第 1 轮的结果之后改的 → 都不是事后（S7 不适用）。
为什么这两个：
  - BXT（假突破：大盘带动）：信号日日経225 涨 ≥ +1.5% 的日子不开新仓。那天很多票是跟着大盘一起「突破」的（β 带动，不是这只票自己的消息），
    诊断里亏损单一半是「一买就不涨」的假突破；Chan（2003，JFE）「有消息的变动会延续、没消息的会反转」—— 大盘普涨日的个股突破多半是没有个股消息的。
    先验弱〜中（照实写）。
  - S5D（顺向：美股在回调就不买）：前一个美国收盘时 S&P 500 < 50 日简单均线 → 不开新仓。日本股票夜里跟着美股走、核心又是纳指；
    诊断说输赢主要看持有期间大盘方向。和第 1 轮 N5D 同一家族（大盘短期趋势），只是换成美国的指数（另一个信号来源）。先验同 N5D、略弱（日本自己的趋势更直接）。
  以前没做过：UBG（美股熊 = T0 牛熊分界才挡）、ERG、YSG 都不是这两个；量比 / 突破日涨幅（day_ret、sec_ex）是个股自己的，不是「大盘那天涨了多少」。
做法：都按日子挡（kind = "date"）：闸门成立 → 那天的全部信号 em_tick 0；其余全部同 B3。阈值（+1.5%、50 日）一次写定（S6 不适用）；S5、S8 适用。
  - BXT：W["inp"]["n225"] 收盘的日涨跌（信号日收盘 ÷ 前一个交易日收盘 − 1）≥ +1.5%。
  - S5D：W["inp"]["spx"] 收盘、50 日简单均线（至少 50 天）；日本的信号日 d 用「日期 < d 的最后一个美国收盘」的判定（与判断层的美股项同一个取法）。
S5：W / Jx 里 B3 会买的信号按同样的日子挡。第二关（第一关全过的才做；另行登记）：kind = date（日序列循环平移 400 次）。
登记前的规模核对与接线核对（只数个数、不看收益）写进 sim_changes 的登记节。
事前预期（写在看结果之前）：BXT 第一关约 5%、S5D 约 5%；「更好候选」各约 1%。
运行：python scripts/loop9_r02_marketday.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop9_r02_marketday.md / .json。非投资建议。
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
import loop9_common as C9                                                    # noqa: E402
import loop9_r01_market as R1                                                # noqa: E402
import research_loop9 as R9                                                  # noqa: E402

ROUND = 2
IDS = ("BXT", "S5D")
FAMILY = {"BXT": "选股·假突破（大盘带动）", "S5D": "选股·大盘短期趋势（顺向）"}
POSTHOC = False
KIND = "date"
BIG_DAY = 0.015
MA_N = 50
OUT = "loop9_r02_marketday"


# ───────────────────────── 纯函数（tests/test_loop9_r02.py） ─────────────────────────
def big_up_days(close: pd.Series, thr: float = BIG_DAY) -> pd.Series:
    """收盘对前一个交易日收盘的涨幅 ≥ thr。"""
    c = close.astype(float).dropna()
    return (c / c.shift(1) - 1 >= thr).fillna(False)


def prev_close_gate(us_gate: pd.Series, days: pd.DatetimeIndex) -> np.ndarray:
    """美国的日序列闸门 → 日本的每个交易日 d 取「日期 < d 的最后一个美国交易日」的值（没有 → 不成立）。"""
    s = us_gate[~us_gate.index.duplicated(keep="last")].astype(bool).sort_index()
    idx = s.index.searchsorted(pd.DatetimeIndex(days), side="left") - 1
    v = s.to_numpy(bool)
    return np.where(idx >= 0, v[np.clip(idx, 0, max(0, len(v) - 1))] if len(v) else False, False)


# ───────────────────────── 输入 ─────────────────────────
def spx(W: dict) -> pd.Series:
    x = W["inp"]["spx"]
    return (x["Close"] if isinstance(x, pd.DataFrame) else x).astype(float).dropna()


def day_gates(W: dict) -> dict:
    """{做法: 日序列的取法}：BXT 是日経自己的日子（同一天）；S5D 是美国的日子（取日本日期之前的最后一个）。"""
    return {"BXT": ("jp", big_up_days(R1.n225(W))), "S5D": ("us", R1.below_ma_days(spx(W), MA_N))}


def align(kind_series: tuple, days: pd.DatetimeIndex) -> np.ndarray:
    kind, s = kind_series
    return R1.on_days(s, days) if kind == "jp" else prev_close_gate(s, days)


def gates(W: dict, G: dict):
    out, days_on = {k: {} for k in IDS}, {k: {} for k in IDS}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        days = C9.days_of(W, e)
        for k in IDS:
            on = align(G[k], days)
            days_on[k][e] = on
            out[k][e] = C9.gate_from_days(S, days, on)
    return out, days_on


def other_fn(G: dict, k: str):
    def fn(s, X, fa):
        return align(G[k], pd.DatetimeIndex(pd.to_datetime(X["date"])))
    return fn


# ───────────────────────── 规模 / 接线 / 运行（同第 1 轮的写法） ─────────────────────────
def scale(W: dict, g: dict) -> dict:
    out = {}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        idx = {(str(t), pd.Timestamp(d)): i for i, (t, d) in enumerate(zip(S["ticker"], S["date"]))}
        pos = [idx.get(k) for k in R1.b3_trade_keys(W, e)]
        out[e] = {"signals": len(S), "b3_trades": len(pos),
                  **{k: {"signals_blocked": int(np.asarray(g[k][e]).sum()),
                         "trades_blocked": int(sum(bool(g[k][e][i]) for i in pos if i is not None))} for k in IDS}}
    return out


def other_scale(W: dict, G: dict) -> dict:
    import combo_all_common as CA
    out = {}
    for s, fold, _ in C9.OTHER:
        D = W["D"][s]
        X = D[CA.apply_c(W["c_fold"][fold], D)].reset_index(drop=True)
        out[s] = {"n": len(X), **{k: int(np.asarray(other_fn(G, k)(s, X, None)).sum()) for k in IDS}}
    return out


def wiring() -> int:
    t0 = time.time()
    W = C9.load()
    G = day_gates(W)
    g, days_on = gates(W, G)
    ok = True
    for e in C9.ERAS:
        base = C9.acct(C9.L6.run(W, e))
        empty = C9.acct(C9.run_block(W, e, np.zeros(len(C9.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C9.KEYS)
        S = C9.signals(W, e)
        n = {k: len(C9.tick_of(S["ticker"], S["date"], g[k][e])) for k in IDS}
        ok &= same and all(v > 0 for v in n.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items())
              + "；闸门天数 " + "、".join(f"{k} {np.mean(days_on[k][e]) * 100:.1f}%" for k in IDS), flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx（只数个数）：" + json.dumps(other_scale(W, G), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = R1.git_head()
    W = C9.load()
    G = day_gates(W)
    g, days_on = gates(W, G)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C9.stage_one(W, g, {k: other_fn(G, k) for k in IDS}, posthoc=None, log=lambda m: print(m, flush=True))
    reg = R9.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C9.ERAS}
    res = {"loop": 9, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g),
           "gate_days_pct": {k: {e: round(float(np.mean(days_on[k][e]) * 100), 1) for e in C9.ERAS} for k in IDS},
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    text = C9.render(res, f"# 第九个研究循环第 {ROUND} 轮：BXT 日経涨 ≥ +1.5% 的日子不开新仓 / S5D S&P 500 在 50 日线下不开新仓（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环第 2 轮：BXT / S5D（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
