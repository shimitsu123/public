"""loop9_r06_distrev.py — 第九个研究循环（选股成功率）第 6 轮：大盘出货日 MDD、一个月涨幅过大（短期反转）RVS
（2026-10-04 登记；先提交后只运行一次；用掉 2 个做法 → 11 / 20；新家族「选股·大盘出货日」1 / 3、「选股·短期反转」1 / 3）。

循环的规则：scripts/research_loop9.py；共用：scripts/loop9_common.py；复用第 1 轮的纯函数（scripts/loop9_r01_market.py：on_days / n225 / closes_of / b3_trade_keys）。
照实写：这两个是第 4 轮运行时（第 4、5 轮都还没有结果）为了补充「事先能想到的做法」重新查文献想的，不是任何一轮结果的变体；MDD 的作废规则
  （见下）是看了第 4 轮结果（SBW，与大盘出货日无关）之后、第 5 轮结果出来之前、只按个数补上的；
  但提出 RVS 时已经看过第 3 轮 GPT（开盘跳空 +1.5〜3% 不买，只差 S5）的结果 —— RVS 用的是另一个变量（信号日之前 20 个交易日的涨幅在池子里的位置，
  与开盘无关）、另一套文献（短期反转），不是 GPT 的改动；照实写在这里。以前的做法里：C 的特征有 r20（20 日涨跌）但 C 是按格子学的规则，
  没有「20 日涨幅在池子前 10% 就不买」这条；第四个循环 BAS / 本循环去掉的 AGE 是「最近有没有创新高」（形态），不是涨幅大小。先验弱〜中。
为什么：
  - MDD（大盘出货日；O'Neil / IBD 的「市场方向」M）：日経收跌 ≥ 0.2% 且池子里（当天与前一天都有成交量的票）合计成交量比前一天多 = 一个「出货日」；
    最近 25 个交易日里出货日 ≥ 5 个 → 机构在出货、大盘多半在做头 → 不开新仓（kind = date）。
    与以前的不同：第 1 轮 ADH 是涨跌家数、N5D / NDD 是价格趋势、个股层的 max_distribution_days 是个股自己的出货日；这里是指数 + 全池成交量。
    照 IBD 原版：出货日在 25 个交易日后过期，或之后指数收盘曾比那天收盘高 ≥ 5% 就作废（照实写：第一次只数个数时没有用作废规则，闸门天数五〜六成、
    不像「做头」的信号；按原版补上作废规则后再数一次 —— 只看个数、没看任何收益）；学术证据弱（实务经验）。
  - RVS（短期反转；Jegadeesh 1990、Lehmann 1990；日本大型股的短期反转比美国强、动量弱：Asness 2011「Momentum in Japan」、
    Chou, Wei & Chung 2007）：信号日收盘 ÷ 20 个交易日前收盘 − 1 在同一个池子当天全部票里排前 10%（百分位 > 0.9）→ 一个月涨得最多的那批，之后多半回吐 → 不买（kind = stock）。
    诊断：亏损单约一半是「一买就不涨」的假突破。
做法：MDD 按日子挡（那天全部信号 em_tick 0），RVS 按个股挡（（票, 信号日）em_tick 0）；其余全部同 B3。阈值（−0.2%、25 天、5 个；20 天、前 10%）一次写定（S6 不适用）；S5、S8 适用。
  - 成交量与 20 日涨幅都在「那个池子」里算：Z / E / J 用各自账户的日経225 池子，W / Jx 用各自的池子（MDD 的成交量：W 用 E、Jx 用 J 的日経225 池子 —— 大盘层同一个序列）。
    成交量 0 当作没有；都只用信号日收盘以前的数据（信号在收盘后决定、第二天开盘成交）。
S5：W / Jx 里 B3 会买的信号按同样的定义挡。第二关（第一关全过的才做；另行登记）：MDD kind = date（日序列循环平移）、RVS kind = stock（逐个信号随机挡）。
登记前的规模核对与接线核对（只数个数、不看收益；2026-10-04）：MDD 闸门天数 Z 37.2% / E 41.2% / J 43.6%，挡掉 W2 信号 34 / 67 / 89，碰到 B3 成交 11 / 12 / 20；
  W 197 / 438、Jx 357 / 792（不用作废规则时是 54.6% / 61.6% / 60.5%、成交 17 / 22 / 30）。RVS 挡掉 3 / 14 / 15，碰到成交 0 / 1 / 1（B3 的其他条件
  —— 离 20 日线不能太远等 —— 已经挡掉了大部分一个月涨得最多的票）；W 24、Jx 52。三个年代「空集合 = B3」✓。
事前预期（写在看结果之前；按上面的个数改写过一次，照实写）：MDD 挡掉约三成成交、闸门天数约四成 → 像 JRC / N5D 一类（胜率可能升、钱去核心、账户差不多），
  第一关约 3%；RVS 只碰到 2 笔成交 → 账户几乎不变，S1（合计 ≥ +0.03）很难过，第一关约 1%；「更好候选」MDD 约 0.5%、RVS 约 0.1%。
运行：python scripts/loop9_r06_distrev.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop9_r06_distrev.md / .json。非投资建议。
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

ROUND = 6
IDS = ("MDD", "RVS")
FAMILY = {"MDD": "选股·大盘出货日", "RVS": "选股·短期反转"}
KINDS = {"MDD": "date", "RVS": "stock"}
POSTHOC = False
DROP, DIST_N, DIST_K, EXPIRE = -0.002, 25, 5, 0.05
REV_N, REV_TOP = 20, 0.9
OUT = "loop9_r06_distrev"
MDD_POOL = {"Z": "Z", "E": "E", "J": "J", "W": "E", "Jx": "J"}                 # MDD 的成交量用哪个日経225 池子


# ───────────────────────── 纯函数（tests/test_loop9_r06.py） ─────────────────────────
def volumes_of(fa: dict) -> pd.DataFrame:
    """日期 × 票 的成交量（0 → NaN）。"""
    V = pd.DataFrame({t: df["Volume"].astype(float) for t, df in fa.items()}).sort_index()
    return V.where(V > 0)


def vol_up_days(V: pd.DataFrame) -> pd.Series:
    """只用当天与前一天都有成交量的票：当天合计 > 前一天合计。"""
    prev = V.shift(1)
    both = V.notna() & prev.notna()
    today, yday = V.where(both).sum(axis=1), prev.where(both).sum(axis=1)
    return (today > yday) & both.any(axis=1)


def dist_days(close: pd.Series, up_vol: pd.Series, drop: float = DROP) -> pd.Series:
    """出货日：指数收盘对前一个交易日 ≤ drop 且成交量比前一天多（指数的日子为准；成交量没有的日子 = 不是）。"""
    c = close.astype(float).dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    r = c / c.shift(1) - 1
    u = up_vol.reindex(c.index).fillna(False).astype(bool)
    return ((r <= drop) & u).fillna(False)


def dist_gate_days(dd: pd.Series, close: pd.Series | None = None, n: int = DIST_N, k: int = DIST_K, expire: float = EXPIRE) -> pd.Series:
    """最近 n 个交易日（含当天）里「还有效」的出货日 ≥ k（要满 n 天）。IBD 的作废规则：出货日之后指数收盘曾比那天的收盘高 ≥ expire → 那个出货日作废。
    close = None → 不用作废规则。"""
    d = dd.astype(bool)
    if close is None:
        return (d.astype(float).rolling(n).sum() >= k).fillna(False)
    c = close.astype(float)
    c = c[~c.index.duplicated(keep="last")].reindex(d.index)
    cv, dv = c.to_numpy(float), d.to_numpy(bool)
    out = np.zeros(len(dv), bool)
    for i in range(n - 1, len(dv)):
        cnt = 0
        for j in range(i - n + 1, i + 1):
            if dv[j] and np.isfinite(cv[j]):
                later = cv[j + 1:i + 1]
                if not (later.size and np.nanmax(later) >= cv[j] * (1 + expire)):
                    cnt += 1
        out[i] = cnt >= k
    return pd.Series(out, index=d.index)


def ret_pct(closes: pd.DataFrame, n: int = REV_N) -> pd.DataFrame:
    """每一天池子里各票 n 日涨跌的百分位（0〜1；算不出 → NaN）。"""
    r = closes / closes.shift(n) - 1
    return r.rank(axis=1, pct=True)


def rev_gate(tickers, dates, pct: pd.DataFrame, top: float = REV_TOP) -> np.ndarray:
    out = np.zeros(len(tickers), bool)
    cols = set(pct.columns)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        if t not in cols or d not in pct.index:
            continue
        v = pct.at[d, t]
        out[i] = bool(np.isfinite(v) and v > top)
    return out


# ───────────────────────── 输入 ─────────────────────────
def mdd_series(W: dict) -> dict:
    """{池子名: 出货日闸门的日序列}（Z / E / J 各自的日経225 池子）。"""
    n = R1.n225(W)
    return {e: dist_gate_days(dist_days(n, vol_up_days(volumes_of(W["SM"][e]["fa"]))), n) for e in C9.ERAS}


def gates(W: dict, M: dict):
    out, days_on, pct = {k: {} for k in IDS}, {"MDD": {}}, {}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        days = C9.days_of(W, e)
        on = R1.on_days(M[e], days)
        days_on["MDD"][e] = on
        out["MDD"][e] = C9.gate_from_days(S, days, on)
        pct[e] = ret_pct(R1.closes_of(W["SM"][e]["fa"]))
        out["RVS"][e] = rev_gate(S["ticker"].to_numpy(), S["date"].to_numpy(), pct[e])
    return out, days_on


def other_fns(M: dict) -> dict:
    cache: dict = {}

    def mdd(s, X, fa):
        return R1.on_days(M[MDD_POOL[s]], pd.DatetimeIndex(pd.to_datetime(X["date"])))

    def rvs(s, X, fa):
        if s not in cache:
            cache[s] = ret_pct(R1.closes_of(fa))
        return rev_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), cache[s])
    return {"MDD": mdd, "RVS": rvs}


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
    M = mdd_series(W)
    g, days_on = gates(W, M)
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
              + f"；MDD 闸门天数 {np.mean(days_on['MDD'][e]) * 100:.1f}%", flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx（只数个数）：" + json.dumps(other_scale(W, other_fns(M)), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C9.git_head("scripts/loop9_r06_distrev.py", "scripts/loop9_r01_market.py")
    W = C9.load()
    M = mdd_series(W)
    g, days_on = gates(W, M)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C9.stage_one(W, g, other_fns(M), posthoc=None, log=lambda m: print(m, flush=True))
    reg = R9.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C9.ERAS}
    res = {"loop": 9, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g),
           "gate_days_pct": {"MDD": {e: round(float(np.mean(days_on["MDD"][e]) * 100), 1) for e in C9.ERAS}},
           "seconds": round(time.time() - t0)}
    text = C9.render(res, f"# 第九个研究循环第 {ROUND} 轮：MDD 最近 25 天大盘出货日 ≥ 5 个不开新仓 / RVS 20 日涨幅在池子前 10% 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环第 6 轮：MDD / RVS（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
