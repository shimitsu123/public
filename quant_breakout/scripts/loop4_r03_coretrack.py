"""loop4_r03_coretrack.py — 第四个研究循环（选股）第 3 轮：个股 / 业种过去的突破「跑不赢核心」就不买 —— CTR（同一只票）/ STR（同一个东証 33 业种）
（2026-10-03 登记；先提交后只运行一次；用掉 2 个做法 → 6 / 20；家族「选股·个股记忆」2 / 3、新家族「选股·行业记忆」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环；选股类第二关的随机挡事先写定）；基准 B1：scripts/loop2_common.py。
为什么这两个（照实写）：
  - 事后诊断（scripts/loop4_oracle_diag.py，只描述，结果 e04b53a）：事后完美挡掉「持有期跑输核心（1545 合成 = 纳指 100 × 日元）」的突破，每个年代约 +0.2；
    完美挡「亏的」只有 +0.393（合计）→ 挡的目标应该是「跑不赢核心」而不是「亏」；C 的 53 个特征里没有一个是相对核心的。
  - 第 1 轮 FBM（同一只票上一次突破亏了 → 挡）在 W / Jx 两个独立池子里逐笔都对（S5 过：Jx 被挡的胜率 32%），但只看一笔、看的是「亏」、账户上挡错了
    关键的几笔。这一轮把「个股记忆」改成「过去几年的突破平均跑不跑得赢核心」（CTR），再加一个用同业种合起来、样本更多的版本（STR）。
    照实写：这一轮是看了 FBM 的结果与事后诊断之后设计的（不是把以前的做法拼起来，所以不算事后组合、S7 不适用；但先验受这两次结果影响）。
  - 文献：个股层面「突破之后跟不跟得上」的持续性没有直接文献（先验弱）；业种层面有行业动量（Moskowitz & Grinblatt 1999，J. Finance），
    但这里比的是「突破之后相对核心的超额」，不是业种涨跌本身。
  - 结构上的性质（写在看结果之前）：核心弱的时候（2001〜2003 纳指大跌）日本突破多半跑赢核心 → 挡得少；核心强的时候（J）挡得多 →
    主要在个股层贡献小的年代起作用（事后诊断：不做日本个股 Z −0.603、E −0.134、J −0.014）。这是想法的一部分，不是事后挑的。
做法（两个都是逐个信号判定（票, 信号日）→ em_tick 0（不开新仓，名额留给下一个候选、钱留在核心）；其余 —— W2 + C 的买点、X6 等离场、核心 FJE、
  判断层 —— 全部同 B1）：
  - 假想单笔表：研究面板 D（combo_all_posthoc；每个 W2 信号一笔，net = X6 离场的净收益 %、hold = 持有交易日）。离场日 = 信号日在那个面板的交易日历上
    往后 hold 个交易日（超出日历 → 日历最后一天）；核心同期 = 1545 合成收盘「离场日 ÷ 信号日 − 1」（各取那天或之前最近的收盘）；超额 = net − 核心同期（pp）。
    日経225 账户：Z / E / J 三个面板合起来（同一只票、同一个信号日只留一笔）；S5 的池子各用自己的面板（W 用 W、Jx 用 Jx）。
  - CTR：对（t, d）：同一只票、离场日 < d 且 ≥ d − 1826 天（5 年）的假想单笔 ≥ 2 笔，且平均超额 < 0 → 挡；不够 2 笔 → 不挡。
  - STR：对（t, d）：同一个东証 33 业种（policy_event_data 的 s33 + extra_pool，与第三个循环第 11 轮 SEC 同一张表；没有业种 → 不挡）、
    离场日 < d 且 ≥ d − 1096 天（3 年）的假想单笔 ≥ 5 笔，且平均超额 < 0 → 挡（包括这只票自己过去的）。
  参数（5 年 / 2 笔、3 年 / 5 笔、0）一次写定，没有学出来（S6 不适用）；改个股买点 → S5 适用。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）按同样的定义挡（各用自己池子的假想单笔），
  保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop4.stage1（= 第三个循环的 stage1；trade = S5，lenses = None，posthoc = None），两个各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状 = research_loop4 事先写定的逐个信号随机挡（random_signal_block：每个候选信号以
  这个做法在那个年代实际挡掉的比例随机挡；种子 numpy.random.default_rng([20261003, s])）。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号与成交、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔。
事前预期（照实写，写在看结果之前）：Z 挡得少、J 挡得多；个股层面过去几笔的平均很吵（先验弱），第一关约 4%；STR 样本多一些，第一关约 5%；
  第二关各约 10% → 「更好候选」约 0.9%。
运行：python scripts/loop4_r03_coretrack.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r03_coretrack.md / .json。非投资建议。
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
import loop3_r12_corediv as R12                                              # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ROUND = 3
IDS = ("CTR", "STR")
FAMILY = {"CTR": "选股·个股记忆", "STR": "选股·行业记忆"}
POSTHOC = False
KIND = "stock"
CTR_DAYS, CTR_MIN = 1826, 2                                                  # 同一只票：5 年以内结束的 ≥ 2 笔
STR_DAYS, STR_MIN = 1096, 5                                                  # 同一个 33 业种：3 年以内结束的 ≥ 5 笔
CORE = "1545.T"
OUT = "loop4_r03_coretrack"


# ───────────────────────── 纯函数（tests/test_loop4_r03.py） ─────────────────────────
def trade_table(panel: pd.DataFrame, days, core: pd.Series) -> pd.DataFrame:
    """假想单笔 → ticker / sig（信号日）/ exit（离场日 = 信号日往后 hold 个交易日，超出日历 → 最后一天）/ excess（net − 核心同期，pp）。
    核心同期 = core 在离场日 ÷ 信号日 − 1（各取那天或之前最近的收盘）；算不出 → 这一笔不要。"""
    days = pd.DatetimeIndex(days)
    if not len(panel) or not len(days):
        return pd.DataFrame({"ticker": pd.Series(dtype=str), "sig": pd.Series(dtype="datetime64[ns]"),
                             "exit": pd.Series(dtype="datetime64[ns]"), "excess": pd.Series(dtype=float)})
    sig = pd.to_datetime(panel["date"]).dt.normalize().to_numpy()
    p = days.searchsorted(sig)
    x = np.minimum(p + panel["hold"].to_numpy(int), len(days) - 1)
    ex = days[x]
    c = core.astype(float).dropna().sort_index()
    c0 = c.reindex(pd.DatetimeIndex(sig), method="ffill").to_numpy(float)
    c1 = c.reindex(ex, method="ffill").to_numpy(float)
    excess = panel["net"].to_numpy(float) - (c1 / c0 - 1.0) * 100.0
    T = pd.DataFrame({"ticker": panel["ticker"].astype(str).to_numpy(), "sig": sig, "exit": ex.to_numpy(), "excess": excess})
    return T[np.isfinite(T["excess"])].reset_index(drop=True)


def merge_tables(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """几个面板合起来；同一只票、同一个信号日只留第一次出现的那一笔。"""
    T = pd.concat([t for t in tables if len(t)], ignore_index=True) if any(len(t) for t in tables) else trade_table(pd.DataFrame(), [], pd.Series(dtype=float))
    return T.drop_duplicates(["ticker", "sig"], keep="first").reset_index(drop=True)


def track_gate(tickers, dates, table: pd.DataFrame, key_of, lookback_days: int, min_n: int) -> np.ndarray:
    """（票, 信号日 d）→ 同一个 key（key_of(票)；None → 不挡）、离场日 < d 且 ≥ d − lookback_days 天的假想单笔 ≥ min_n 笔、平均超额 < 0 → True。"""
    T = table.assign(_k=[key_of(t) for t in table["ticker"]]) if len(table) else table.assign(_k=[])
    by = {k: (pd.DatetimeIndex(g["exit"]).to_numpy(), g["excess"].to_numpy(float))
          for k, g in T[T["_k"].notna()].sort_values("exit", kind="mergesort").groupby("_k")}
    out = np.zeros(len(tickers), bool)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        k = key_of(t)
        if k is None or k not in by:
            continue
        ex, v = by[k]
        d = pd.Timestamp(d).normalize()
        hi = int(np.searchsorted(ex, d.to_datetime64(), side="left"))                 # 离场日 < d
        lo = int(np.searchsorted(ex, (d - pd.Timedelta(days=lookback_days)).to_datetime64(), side="left"))
        w = v[lo:hi]
        out[i] = len(w) >= min_n and float(w.mean()) < 0
    return out


def ctr_gate(tickers, dates, table: pd.DataFrame) -> np.ndarray:
    return track_gate(tickers, dates, table, lambda t: str(t), CTR_DAYS, CTR_MIN)


def str_gate(tickers, dates, table: pd.DataFrame, sec: dict) -> np.ndarray:
    return track_gate(tickers, dates, table, lambda t: sec.get(str(t)), STR_DAYS, STR_MIN)


# ───────────────────────── 输入 ─────────────────────────
def sector_map() -> dict[str, str]:
    import loop3_r11_sector as R11
    return R11.sector_map()


def core_close(W: dict) -> pd.Series:
    return W["assets"][CORE]["Close"].astype(float)


def n225_table(W: dict) -> pd.DataFrame:
    core = core_close(W)
    return merge_tables([trade_table(W["D"][e], W["ctx"][e]["days"], core) for e in L2.ERAS])


def gates_for(tk, dt, table: pd.DataFrame, sec: dict) -> dict:
    return {"CTR": ctr_gate(tk, dt, table), "STR": str_gate(tk, dt, table, sec)}


def ticks(W: dict, sec: dict) -> dict:
    """{年代: {CTR: em_tick, STR: em_tick}}：这个年代全部 W2 信号（A；B1 的候选是它的子集）里被挡的。"""
    T = n225_table(W)
    out = {}
    for e in L2.ERAS:
        tk, dt = W["A"][e]["ticker"].to_numpy(), W["A"][e]["date"].to_numpy()
        g = gates_for(tk, dt, T, sec)
        out[e] = {k: R12.tick_of(tk, dt, g[k]) for k in IDS}
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, sec: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    core = core_close(W)
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        T = trade_table(D[s], W["ctx"][fold]["days"], core)
        gates = gates_for(X["ticker"].to_numpy(), X["date"].to_numpy(), T, sec)
        for k in IDS:
            g = gates[k]
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[k][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def scale(W: dict, b1_trades: dict, sec: dict) -> dict:
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    T = n225_table(W)
    out = {"table": {"n": int(len(T)), "first_exit": str(pd.Timestamp(T["exit"].min()).date()) if len(T) else None,
                     "last_exit": str(pd.Timestamp(T["exit"].max()).date()) if len(T) else None}}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        X = A[e][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != e]), A[e])]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        sig = np.asarray([days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]) if len(tr) else np.array([])
        gx = gates_for(X["ticker"].to_numpy(), X["date"].to_numpy(), T, sec)
        gt = gates_for(tr["ticker"].to_numpy(), sig, T, sec) if len(tr) else {k: np.array([], bool) for k in IDS}
        out[e] = {"signals": int(len(X)), "b1_trades": int(len(tr)),
                  **{k: {"signals_blocked": int(gx[k].sum()), "trades_blocked": int(gt[k].sum())} for k in IDS}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r03_coretrack.py", "scripts/loop3_r12_corediv.py",
                                 "scripts/loop3_r11_sector.py", "scripts/policy_event_data.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def runs(tk: dict, e: str) -> dict:
    return {k: {"em_tick": tk[e][k]} for k in IDS}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    sec = sector_map()
    tk = ticks(W, sec)
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(tk, e).items():
            rc = L2.run(W, e, **over)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, sec)
    s1 = {k: R4.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "ticks": {e: {k: len(tk[e][k]) for k in IDS} for e in L2.ERAS}, "scale": scale(W, b1_trades, sec), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"CTR": "同一只票过去 5 年的假想突破（≥ 2 笔）平均跑输核心 → 不开新仓",
            "STR": "同一个东証 33 业种过去 3 年的假想突破（≥ 5 笔）平均跑输核心 → 不开新仓"}
    L = [f"# 第四个研究循环（选股）第 3 轮：个股 / 业种的突破跑不赢核心 CTR / STR（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r03_coretrack.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | CTR（Calmar 差） | STR（Calmar 差） | 个股笔数 B1 → CTR / STR |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + f" | {t['B1']} → {t['CTR']} / {t['STR']} |")
    sc = res["scale"]
    L += ["", f"规模与被挡的（不参与判定）：假想单笔表 {sc['table']['n']} 笔（离场 {sc['table']['first_exit']}〜{sc['table']['last_exit']}）"]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；全部 W2 信号里挡 "
                 + "、".join(f"{k} {res['ticks'][e][k]} 个" for k in IDS) + "；"
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
    sec = sector_map()
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    tk = ticks(W, sec)
    rng = {s: (str(pd.to_datetime(W["D"][s]["date"]).min().date()), str(pd.to_datetime(W["D"][s]["date"]).max().date()), int(len(W["D"][s])))
           for s in (*L2.ERAS, "W", "Jx")}
    print(json.dumps({"scale": scale(W, b1, sec), "ticks": {e: {k: len(tk[e][k]) for k in IDS} for e in L2.ERAS}, "panels": rng}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 两个账户都与 B1 逐项相同；② em_tick 对数 > 0（不看收益）。"""
    W = L2.load()
    tk = ticks(W, sector_map())
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {"J": {k: {} for k in IDS}}
    same = {k: all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys) for k, over in runs(empty, "J").items()}
    n = {k: len(v["em_tick"]) for k, v in runs(tk, "J").items()}
    print(json.dumps({"empty_same_as_b1": same, "counts_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 3 轮：CTR / STR（选股：个股 / 业种的突破跑不赢核心）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
