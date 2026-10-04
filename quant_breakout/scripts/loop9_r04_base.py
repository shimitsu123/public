"""loop9_r04_base.py — 第九个研究循环（选股成功率）第 4 轮：业种宽度太弱 SBW
（2026-10-04 登记；先提交后只运行一次；用掉 1 个做法 → 7 / 20；新家族「选股·业种宽度」1 / 3）。

循环的规则：scripts/research_loop9.py；共用：scripts/loop9_common.py；复用第 1 轮的纯函数（scripts/loop9_r01_market.py：closes_of / b3_trade_keys）。
照实写：SBW 在第 1 轮运行之前的规模核对（只数个数；scale9 的 SEC33）里就列着，不是看了任何一轮结果之后想的 → 不是事后（S7 不适用）。
照实写（本轮去掉的一个）：同一次规模核对里还列着 AGE（信号前 60 天的最高价是最近 10 天才创的 → 不买）。登记前核对以前的做法时发现，它与
  第四个循环第 2 轮 BAS（信号前 20 天创过 252 日新高 → 不买；合计 +0.019，W 被挡的更好、Jx 被挡的更差）是同一个想法（「没整理就再突破」）的另一个定义；
  按规则四「改了的变体 = 新 ID、按事后处理、S7 适用」，而选股没有登记时写得定的「没看过的数据」（W / Jx 在 BAS 的 S5 里已经看过）→ AGE 不登记、不运行、不占名额。
  （只数过个数：AGE 挡 W2 信号 Z 12 / E 23 / J 21，碰到 B3 成交 3 / 6 / 7；没看任何收益。）
为什么 SBW：诊断里亏损单约一半是「一买就不涨」的假突破（E / J 平均亏 −5.5% / −5.7%，是亏得最多的一类）。业种整体还在弱势时单独一只突破，
  更可能是假突破（业种动量：Moskowitz & Grinblatt 1999；个股的动量很大一部分来自业种）。
  规则：同一个东证 33 业种（同一个池子里、有 50 日线的票至少 3 只）收在自己 50 日线之上的比例 < 1/3 → 不开新仓。
  以前没做过这个定义：第三个循环 SEC（同业种不重复持有）是分散，第四个循环 STR（业种过去的突破跑不赢核心）是记忆，第四个循环 SSN 是季节性，
  第五个循环 ISM（按业种 12 个月动量调仓位）是仓位层、用 12 个月动量；C 的 sec（业种 12-1 个月强弱）在 E 那一折是负号 —— 这里用的是「最近的业种宽度」。
  先验弱〜中（照实写）。
做法：按个股挡（kind = "stock"）：（票, 信号日）成立 → em_tick 0；其余全部同 B3。阈值（50 日线、至少 40 天、1/3、至少 3 只）一次写定（S6 不适用）；S5、S8 适用。
  - 业种：var/industry_s33.json（TOPIX 1000 的东证 33 业种）；查不到的票不挡。宽度在「那个池子」里算：Z / E / J 用各自账户的日经225 池子，W / Jx 用各自的池子
    （信号日收盘时就知道，不用未来数据：信号在收盘后决定、第二天开盘成交）。
S5：W / Jx 里 B3 会买的信号按同样的定义挡。第二关（第一关全过的才做；另行登记）：kind = stock（逐个信号随机挡，同样比例；种子 [20261004, s]）。
登记前的规模核对与接线核对（只数个数、不看收益；2026-10-04）：SBW 挡掉 W2 信号 Z 10 / 97、E 11 / 155、J 21 / 173，碰到 B3 成交 0 / 2 / 3；W 80 / 438、Jx 70 / 792；
  三个年代「空集合 = B3」✓、em_tick 对数 10 / 11 / 21。
事前预期（写在看结果之前）：挡得很少（成交只碰到 5 笔）→ 账户的差很小，S1（合计 ≥ +0.03）很难过，第一关约 2%；「更好候选」约 0.3%。
运行：python scripts/loop9_r04_base.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop9_r04_base.md / .json。非投资建议。
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

ROUND = 4
IDS = ("SBW",)
FAMILY = {"SBW": "选股·业种宽度"}
KINDS = {"SBW": "stock"}
POSTHOC = False
MA_N, MA_MIN, WEAK, MIN_PEERS = 50, 40, 1.0 / 3.0, 3
OUT = "loop9_r04_base"
ROOT = Path(__file__).resolve().parents[1]


# ───────────────────────── 纯函数（tests/test_loop9_r04.py） ─────────────────────────
def sector_breadth(closes: pd.DataFrame, sector_of: dict, n: int = MA_N, min_n: int = MA_MIN, min_peers: int = MIN_PEERS) -> dict:
    """{业种: 日序列（收在 n 日线之上的比例；有均线的票 < min_peers → NaN）}。closes = 日期 × 票。"""
    ma = closes.rolling(n, min_periods=min_n).mean()
    above, have = (closes > ma), ma.notna() & closes.notna()
    out = {}
    for s in sorted({v for v in sector_of.values() if v}):
        cols = [t for t in closes.columns if sector_of.get(t) == s]
        if not cols:
            continue
        a, h = above[cols].sum(axis=1).astype(float), have[cols].sum(axis=1).astype(float)
        out[s] = (a / h.replace(0, np.nan)).where(h >= min_peers)
    return out


def sec_gate(tickers, dates, breadth: dict, sector_of: dict, weak: float = WEAK) -> np.ndarray:
    out = np.zeros(len(tickers), bool)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        s = sector_of.get(t)
        b = breadth.get(s)
        if b is None or d not in b.index:
            continue
        v = b.loc[d]
        v = float(v.iloc[-1]) if isinstance(v, pd.Series) else float(v)
        out[i] = np.isfinite(v) and v < weak
    return out


# ───────────────────────── 输入 ─────────────────────────
def s33_map(tickers) -> dict:
    s33 = json.loads((ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8")).get("s33") or {}
    return {t: s33.get(str(t).split(".")[0]) for t in tickers}


def pool_inputs(fa: dict) -> tuple[dict, dict]:
    sec_of = s33_map(list(fa))
    return sector_breadth(R1.closes_of(fa), sec_of), sec_of


def gates(W: dict):
    out, inp = {k: {} for k in IDS}, {}
    for e in C9.ERAS:
        fa = W["SM"][e]["fa"]
        S = C9.signals(W, e)
        tk, dt = S["ticker"].to_numpy(), S["date"].to_numpy()
        br, sec_of = pool_inputs(fa)
        inp[e] = (br, sec_of)
        out["SBW"][e] = sec_gate(tk, dt, br, sec_of)
    return out, inp


def other_fns() -> dict:
    cache: dict = {}

    def sec(s, X, fa):
        if s not in cache:
            cache[s] = pool_inputs(fa)
        br, sec_of = cache[s]
        return sec_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), br, sec_of)
    return {"SBW": sec}


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


def other_scale(W: dict, fns: dict) -> dict:
    import combo_all_common as CA
    out = {}
    for s, fold, sm in C9.OTHER:
        D = W["D"][s]
        X = D[CA.apply_c(W["c_fold"][fold], D)].reset_index(drop=True)
        out[s] = {"n": len(X), **{k: int(np.asarray(fn(s, X, W["SM"][sm]["fa"])).sum()) for k, fn in fns.items()}}
    return out


def wiring() -> int:
    t0 = time.time()
    W = C9.load()
    g, _ = gates(W)
    ok = True
    for e in C9.ERAS:
        base = C9.acct(C9.L6.run(W, e))
        empty = C9.acct(C9.run_block(W, e, np.zeros(len(C9.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C9.KEYS)
        S = C9.signals(W, e)
        n = {k: len(C9.tick_of(S["ticker"], S["date"], g[k][e])) for k in IDS}
        ok &= same and all(v > 0 for v in n.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items()), flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx（只数个数）：" + json.dumps(other_scale(W, other_fns()), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C9.git_head("scripts/loop9_r04_base.py", "scripts/loop9_r01_market.py")
    W = C9.load()
    g, _ = gates(W)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C9.stage_one(W, g, other_fns(), posthoc=None, log=lambda m: print(m, flush=True))
    reg = R9.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C9.ERAS}
    res = {"loop": 9, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g), "seconds": round(time.time() - t0)}
    text = C9.render(res, f"# 第九个研究循环第 {ROUND} 轮：SBW 同业种在 50 日线之上的比例 < 1/3 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环第 4 轮：SBW（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
