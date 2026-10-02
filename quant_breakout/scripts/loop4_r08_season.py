"""loop4_r08_season.py — 第四个研究循环（选股）第 8 轮：业种的「同一个月份」历史收益最差的三分之一 → 那个月不开新仓 —— SSN
（2026-10-03 登记；先提交后只运行一次；用掉 1 个做法 → 11 / 20；新家族「选股·季节性」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环；选股类第二关的随机挡事先写定）；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - 文献：Heston & Sadka（2008，JFE）个股的同月季节性；Keloharju, Linnainmaa & Nyberg（2016，J. Finance「Return seasonalities」）—— 业种、国家、各种因子
    都有「同一个日历月份的历史收益高 → 那个月之后也高」的季节性，国际样本也成立；业种层面比个股层面的噪声小。
  - 以前（「质的飞跃」第 12 轮，2026-09-27 探索）只看过**个股**的同月季节性（日経225 两个年代都不显著），没看过**业种**的；C 的 53 个特征里没有季节性。
  - 数据：日本个股的日线从 2000 年起 → 要求至少 10 个往年同月（文献用到 20 年）→ 2010 年以后才有分数：**Z 与 E 的前半段一笔都不碰**（数据限制，照实写；
    这样 Z 2003〜2005 的赢家碰不到 —— 第 1〜7 轮最常见的输法 —— 但这不是挑出来的参数：10 年是写定的最少年数）。先验中偏弱（季节性的幅度比突破单笔的波动小得多）。
做法：每个月末 t：每个东証 33 业种（第 11 轮 SEC 同一张表）的月收益 = 业种成员（那个年代账户的日本个股池；W / Jx 各自的池子）当月收益的等权平均（当月有收益的
  成员 ≥ 3 只才算）；季节分 = 这个业种在「t+1 的那个日历月份」的往年收益平均（只用 t 以前的年份，≥ 10 年才算）；当月横截面（有分数的业种）最低的三分之一 →
  这些业种的票在月 t+1 的信号不开新仓（em_tick 0）；算不出的不挡。其余 —— W2 + C 的买点、X6 等离场、核心 FJE、判断层 —— 全部同 B1。
  参数（10 年、3 只、三分之一）一次写定（S6 不适用）。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）按各自池子的业种季节分挡，保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop4.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：kind = "stock"，形状 = random_month_block（每个月从同一个池子里随机挑与真实同样多的票挡掉；种子 [20261003, s]）。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号与成交、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔；第一个有分数的月份。
事前预期（照实写，写在看结果之前）：只碰 2010 年以后、挡掉三分之一业种的月份 → 差小；第一关约 3%；第二关约 10% → 「更好候选」约 0.3%。
运行：python scripts/loop4_r08_season.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r08_season.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop3_r03_yenexit as X3                                               # noqa: E402
import loop3_r10_resmom as RM                                                # noqa: E402
import loop3_r11_sector as R11                                               # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ROUND = 8
IDS = ("SSN",)
FAMILY = {"SSN": "选股·季节性"}
POSTHOC = False
KIND = "stock"
MIN_YEARS, MIN_MEMBERS = 10, 3
LOW_Q = 1 / 3
OUT = "loop4_r08_season"
CORE = X3.CORE


# ───────────────────────── 纯函数（tests/test_loop4_r08.py） ─────────────────────────
def sector_monthly(R: pd.DataFrame, sec: dict) -> pd.DataFrame:
    """个股月收益（行 = 月，列 = 票）→ 业种月收益（等权；当月有收益的成员 ≥ MIN_MEMBERS 只才算）。"""
    cols = {}
    for s in sorted({sec[t] for t in R.columns if sec.get(t)}):
        X = R[[t for t in R.columns if sec.get(t) == s]]
        n = X.notna().sum(axis=1)
        cols[s] = X.mean(axis=1).where(n >= MIN_MEMBERS)
    return pd.DataFrame(cols, index=R.index)


def season_score(S: pd.DataFrame) -> pd.DataFrame:
    """行 t：每个业种在「t+1 的日历月份」的往年收益平均（只用 t 以前、同一月份的年份；≥ MIN_YEARS 年才算）。"""
    out = pd.DataFrame(np.nan, index=S.index, columns=S.columns)
    for t in S.index:
        nxt = t + 1
        past = S[(S.index.month == nxt.month) & (S.index < nxt)]
        cnt = past.notna().sum()
        out.loc[t] = past.mean().where(cnt >= MIN_YEARS)
    return out


def bottom_third(P: pd.DataFrame) -> pd.DataFrame:
    """每个月：≤ 当月横截面 1/3 分位 → 被挡（True）；NaN → 不挡。"""
    q = P.quantile(LOW_Q, axis=1, numeric_only=True)
    return P.le(q, axis=0) & P.notna()


def ticker_block(Bs: pd.DataFrame, tickers, sec: dict) -> pd.DataFrame:
    """业种的被挡表 → 票的被挡表（没有业种 → 不挡）。"""
    return pd.DataFrame({t: (Bs[sec[t]] if sec.get(t) in Bs.columns else pd.Series(False, index=Bs.index)) for t in tickers}, index=Bs.index)


# ───────────────────────── 输入 ─────────────────────────
def season_table(fa: dict, names, sec: dict, months: pd.PeriodIndex) -> pd.DataFrame:
    keys = [t for t in names if str(t).endswith(".T") and t not in CORE and t in fa]
    R = pd.DataFrame({t: RM.monthly_ret(fa[t]["Close"]).reindex(months) for t in keys}, index=months)
    return ticker_block(bottom_third(season_score(sector_monthly(R, sec))), keys, sec)


def inputs(W: dict) -> dict:
    """{年代 / W / Jx: SSN 被挡表（行 = 月 t，列 = 票；用在月 t+1 的信号上）}。"""
    months = RM.market_m(W).index
    sec = R11.sector_map()
    SM = W["SM"]
    return {key: season_table(fa, names, sec, months)
            for key, fa, names in [(e, SM[e]["fa"], RM.era_names(W, e)) for e in L2.ERAS]
            + [("W", SM["W"]["fa"], list(SM["W"]["fa"])), ("Jx", SM["J2"]["fa"], list(SM["J2"]["fa"]))]}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, G: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {"SSN": {}}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        g = RM.gate_of(G[s], X["ticker"].to_numpy(), X["date"].to_numpy())
        dl = CA.delta(net, ~g)
        gone = net[g]
        out["SSN"][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def scale(W: dict, G: dict, b1_trades: dict) -> dict:
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        X = A[e][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != e]), A[e])]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        sig = np.asarray([days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]) if len(tr) else np.array([])
        gx = RM.gate_of(G[e], X["ticker"].to_numpy(), X["date"].to_numpy())
        gt = RM.gate_of(G[e], tr["ticker"].to_numpy(), sig) if len(tr) else np.array([], bool)
        out[e] = {"signals": int(len(X)), "b1_trades": int(len(tr)), "SSN": {"signals_blocked": int(gx.sum()), "trades_blocked": int(gt.sum())}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r08_season.py", "scripts/loop3_r10_resmom.py", "scripts/loop3_r11_sector.py", "scripts/policy_event_data.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def runs(W: dict, e: str, G: dict) -> dict:
    return {"SSN": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    G = inputs(W)
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(W, e, G).items():
            rc = L2.run(W, e, **over)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, G)
    s1 = {k: R4.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "ticks": {e: len(runs(W, e, G)["SSN"]["em_tick"]) for e in L2.ERAS}, "scale": scale(W, G, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1, o = res["stage1"]["SSN"], res["other_stocks"]["SSN"]
    L = [f"# 第四个研究循环（选股）第 8 轮：业种同月季节性最差的三分之一不买 SSN（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r08_season.py 开头）", "",
         f"- **SSN（业种在这个日历月份的往年收益最差的三分之一 → 这个月不开新仓）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | SSN（Calmar 差） | 个股笔数 B1 → SSN |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['SSN'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {t['B1']} → {t['SSN']} |")
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；em_tick {res['ticks'][e]} 对；SSN 挡信号 {x['SSN']['signals_blocked']} 个、"
                 f"B1 实际成交 {x['SSN']['trades_blocked']} 笔")
    for s in ("W", "Jx"):
        z = o[s]
        L.append(f"- SSN {s}：B1 会买的信号 {z['n']} 个，挡掉 {z['gone_n']} 个（胜率 {_f(z['gone_win'], '{:.1f}')}%、每笔 {_f(z['gone_mean'], '{:+.2f}')}%）；"
                 f"保留 {z['kept']} 个 → 胜率差 {_f(z['dwin'], '{:+.2f}')} pp、每笔差 {_f(z['dmean'], '{:+.2f}')} pp")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["SSN"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- SSN {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R4.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    G = inputs(W)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps({"scale": scale(W, G, b1), "ticks": {e: len(runs(W, e, G)["SSN"]["em_tick"]) for e in L2.ERAS},
                      "blocked_cells": {k: int(v.to_numpy().sum()) for k, v in G.items()},
                      "first_month": {k: (str(v.index[v.any(axis=1).to_numpy()][0]) if v.to_numpy().any() else None) for k, v in G.items()}}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0（不看收益）。"""
    W = L2.load()
    G = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    same = all(rb.get(x) == L2.run(W, "J", em_tick={}).get(x) for x in keys)
    n = len(runs(W, "J", G)["SSN"]["em_tick"])
    print(json.dumps({"empty_same_as_b1": same, "count_J": n}, ensure_ascii=False))
    return 0 if same and n > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 8 轮：SSN（选股：业种同月季节性最差的三分之一不买）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
