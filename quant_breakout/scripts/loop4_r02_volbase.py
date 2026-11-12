"""loop4_r02_volbase.py — 第四个研究循环（选股）第 2 轮：「成交量生命周期」晚期的票不买 VLC、刚创过新高没整理就突破的不买 BAS
（2026-10-03 登记；先提交后只运行一次；用掉 2 个做法 → 4 / 20；新家族「选股·量的生命周期」1 / 3、「选股·整理形态」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环；选股类第二关的随机挡事先写定）；基准 B1：scripts/loop2_common.py。
为什么这两个（照实写）：
  - VLC（Lee & Swaminathan 2000，J. Finance「Price momentum and trading volume」）：过去涨得好的票里，成交量已经很大的（「魅力股」、动量生命周期的晚期）
    之后更差、更早反转；成交量还小的继续涨。这里没有流通股数 → 用「最近 126 个交易日平均成交量 ÷ 最近 504 个交易日平均成交量」（量在变大多少）当代理：
    每个月末 t 在当月横截面（那个年代账户的日本个股池）最高的三分之一 → 月 t+1 的信号不开新仓（算不出的不挡）。
    与以前的量比研究（W2 周线量比、突破日量比、月线量比）不同：那些是「突破前后几天 / 几周」的量，这里是「半年对两年」的量的趋势。
  - BAS（整理形态）：信号日之前 20 个交易日里（不含当天）已经创过 252 日收盘新高 → 没有整理就再突破（延伸型）→ 不开新仓。
    想法来自「突破要从整理（base）里出来」的经验（O'Neil / Minervini，没有学术文献，先验弱）；照实写：以前的 E2（2026-09-26）发现
    离 52 周高点远的突破反而好，与 BAS 同方向，但 BAS 的定义（最近 20 天有没有创新高）不同，不是事后组合。
  参数（126 / 504 天、三分之一、20 天、252 天）一次写定（S6 不适用）；不是事后组合（S7 不适用）；改个股买点 → S5 适用。
登记前的规模核对（只数个数、不看被挡信号自己的收益）：数字写进 sim_changes 的登记节。
做法：VLC 按月横截面挡（em_tick，同第三个循环第 10 / 12 轮）；BAS 逐个信号判定（票, 信号日）→ em_tick 0。其余全部同 B1。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）按同样的定义挡（VLC 用各自池子的横截面），
  保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop4.stage1（trade = S5，lenses = None，posthoc = None），两个各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状 = research_loop4 事先写定的随机挡（VLC：random_month_block 每个月同样多的票；
  BAS：random_signal_block 同样比例；种子 numpy.random.default_rng([20261003, s])）。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号与成交、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔。
事前预期（照实写，写在看结果之前）：VLC 挡掉三分之一左右的「量在放大」的票，突破本来就常伴随放量 → 可能挡得多、方向不明，第一关约 4%；
  BAS 挡得少（B1 成交 1 / 1 / 4 笔），第一关约 3%；第二关各约 10% → 「更好候选」约 0.7%。
运行：python scripts/loop4_r02_volbase.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r02_volbase.md / .json。非投资建议。
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
import loop3_r12_corediv as R12                                              # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ROUND = 2
IDS = ("VLC", "BAS")
FAMILY = {"VLC": "选股·量的生命周期", "BAS": "选股·整理形态"}
POSTHOC = False
KIND = "stock"
VS, VS_MIN, VL, VL_MIN, TOP_Q = 126, 100, 504, 400, 2 / 3
HI_N, HI_MIN, BAS_WIN = 252, 200, 20
OUT = "loop4_r02_volbase"
CORE = X3.CORE


# ───────────────────────── 纯函数（tests/test_loop4_r02.py） ─────────────────────────
def vol_trend_monthly(volume: pd.Series, months: pd.PeriodIndex) -> pd.Series:
    """每个月末：最近 VS 个交易日平均成交量 ÷ 最近 VL 个交易日平均成交量（成交量 0 当缺值；不够 → NaN）。"""
    v = volume.astype(float).replace(0, np.nan)
    r = v.rolling(VS, min_periods=VS_MIN).mean() / v.rolling(VL, min_periods=VL_MIN).mean()
    return r.groupby(r.index.to_period("M")).last().reindex(months)


def top_third(P: pd.DataFrame) -> pd.DataFrame:
    return R12.top_third(P)


def new_high_days(close: pd.Series) -> pd.Series:
    """收盘 ≥ 过去 HI_N 个交易日（含当天、至少 HI_MIN 天）的最高收盘 → True。"""
    c = close.astype(float)
    hh = c.rolling(HI_N, min_periods=HI_MIN).max()
    return ((c >= hh) & hh.notna()).fillna(False)


def bas_gate(tickers, dates, fa: dict, cache: dict | None = None) -> np.ndarray:
    """（票, 信号日 d）→ d 之前 BAS_WIN 个交易日（不含 d）创过 HI_N 日收盘新高 → True；没有 K 线 → 不挡。"""
    cache = {} if cache is None else cache
    out = np.zeros(len(tickers), bool)
    for k, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        if t not in fa:
            continue
        if t not in cache:
            cache[t] = new_high_days(fa[t]["Close"])
        s = cache[t]
        p = int(s.index.searchsorted(pd.Timestamp(d)))
        out[k] = bool(s.iloc[max(0, p - BAS_WIN):p].any())
    return out


# ───────────────────────── 输入 ─────────────────────────
def vlc_table(fa: dict, names, months: pd.PeriodIndex) -> pd.DataFrame:
    keys = [t for t in names if str(t).endswith(".T") and t not in CORE and t in fa]
    P = pd.DataFrame({t: vol_trend_monthly(fa[t]["Volume"], months) for t in keys}, index=months)
    return top_third(P)


def inputs(W: dict) -> dict:
    """{年代 / W / Jx: VLC 被挡表}。"""
    months = RM.market_m(W).index
    SM = W["SM"]
    return {key: vlc_table(fa, names, months)
            for key, fa, names in [(e, SM[e]["fa"], RM.era_names(W, e)) for e in L2.ERAS]
            + [("W", SM["W"]["fa"], list(SM["W"]["fa"])), ("Jx", SM["J2"]["fa"], list(SM["J2"]["fa"]))]}


def bas_ticks(W: dict) -> dict:
    A = W["A"]
    out = {}
    for e in L2.ERAS:
        tk, dt = A[e]["ticker"].to_numpy(), A[e]["date"].to_numpy()
        out[e] = R12.tick_of(tk, dt, bas_gate(tk, dt, W["SM"][e]["fa"]))
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, G: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold, fa in (("W", "E", W["SM"]["W"]["fa"]), ("Jx", "J", W["SM"]["J2"]["fa"])):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        tk, dt = X["ticker"].to_numpy(), X["date"].to_numpy()
        gates = {"VLC": RM.gate_of(G[s], tk, dt), "BAS": bas_gate(tk, dt, fa)}
        for k in IDS:
            g = gates[k]
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[k][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None}
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
        fa = W["SM"][e]["fa"]
        tk, dt = X["ticker"].to_numpy(), X["date"].to_numpy()
        gx = {"VLC": RM.gate_of(G[e], tk, dt), "BAS": bas_gate(tk, dt, fa)}
        gt = {"VLC": RM.gate_of(G[e], tr["ticker"].to_numpy(), sig) if len(tr) else np.array([], bool),
              "BAS": bas_gate(tr["ticker"].to_numpy(), sig, fa) if len(tr) else np.array([], bool)}
        out[e] = {"signals": int(len(X)), "b1_trades": int(len(tr)),
                  **{k: {"signals_blocked": int(gx[k].sum()), "trades_blocked": int(gt[k].sum())} for k in IDS}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r02_volbase.py", "scripts/loop3_r12_corediv.py",
                                 "scripts/loop3_r10_resmom.py", "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py",
                                 "scripts/loop_common.py", "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py",
                                 "qbreak/unified.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def runs(W: dict, e: str, G: dict, bt: dict) -> dict:
    return {"VLC": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}, "BAS": {"em_tick": bt[e]}}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    G = inputs(W)
    bt = bas_ticks(W)
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(W, e, G, bt).items():
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
           "bas_ticks": {e: len(bt[e]) for e in L2.ERAS}, "scale": scale(W, G, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"VLC": "半年 ÷ 两年的平均成交量在横截面最高的三分之一 → 下个月不开新仓", "BAS": "信号前 20 个交易日创过 252 日新高（没整理）→ 不开新仓"}
    L = [f"# 第四个研究循环（选股）第 2 轮：量的生命周期 VLC / 整理形态 BAS（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r02_volbase.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | VLC（Calmar 差） | BAS（Calmar 差） | 个股笔数 B1 → VLC / BAS |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + f" | {t['B1']} → {t['VLC']} / {t['BAS']} |")
    sc = res["scale"]
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；全部 W2 信号里 BAS 挡 {res['bas_ticks'][e]} 个；"
                 + "；".join(f"{k} 挡信号 {x[k]['signals_blocked']} 个、B1 实际成交 {x[k]['trades_blocked']} 笔" for k in IDS))
    for k in IDS:
        for s in ("W", "Jx"):
            o = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：B1 会买的信号 {o['n']} 个，挡掉 {o['gone_n']} 个（胜率 {_f(o['gone_win'], '{:.1f}')}%、每笔 {_f(o['gone_mean'], '{:+.2f}')}%）；"
                     f"保留 {o['kept']} 个 → 胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
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
    bt = bas_ticks(W)
    print(json.dumps({"scale": scale(W, G, b1), "bas_ticks": {e: len(bt[e]) for e in L2.ERAS}}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 两个账户都与 B1 逐项相同；② em_tick 对数 > 0（不看收益）。"""
    W = L2.load()
    G = inputs(W)
    bt = bas_ticks(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {"J": G["J"] & False}
    same = {k: all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys) for k, over in runs(W, "J", empty, {"J": {}}).items()}
    n = {k: len(v["em_tick"]) for k, v in runs(W, "J", G, bt).items()}
    print(json.dumps({"empty_same_as_b1": same, "counts_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 2 轮：VLC / BAS（选股：量的生命周期、整理形态）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
