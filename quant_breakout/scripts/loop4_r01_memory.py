"""loop4_r01_memory.py — 第四个研究循环（选股）第 1 轮：同一只票上一次突破刚失败 FBM、信号前 20 天有「坏消息日」NEV（2026-10-03 登记；
先提交后只运行一次；用掉 2 个做法 → 2 / 20；新家族「选股·个股记忆」1 / 3、「选股·消息冲击」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环；选股类第二关的随机挡事先写定）；基准 B1：scripts/loop2_common.py。
为什么这两个（照实写）：第三个循环第 10〜12 轮的选股过滤都挡掉了「比核心还好」的突破；这一轮找「挡得少、而且有理由更差」的：
  - FBM（个股记忆）：同一只票上一次已经结束的突破（研究面板的假想单笔，X6 离场）亏了、并在 120 个交易日以内结束 → 这一次不开新仓。
    想法：反复假突破的票多半在宽幅震荡里（箱体上沿压力大），下一次突破也容易失败。没有直接的文献（技术分析里「失败的突破」常被当成反向信号，Bulkowski）
    → 先验弱，照实写。
  - NEV（消息冲击）：信号日之前 20 个交易日里有「坏消息日」—— 日收益 < −3 × 之前 60 天的日收益标准差、且成交量 ≥ 2 × 之前 50 天平均 → 不开新仓。
    文献：Chan（2003，J. Financial Economics）有消息的大跌之后股价继续偏弱（消息动量），没消息的大跌之后反弹；放量当作「有消息」的代理（这里没有新闻数据）。
  以前的选股研究没用过「同一只票上一次突破的结果」与「信号前的放量大跌日」→ 新方法、不是事后组合（S7 不适用）；参数（120 天、20 天、3σ、2 倍）是一次写定的
  整数，没有学出来（S6 不适用）；改个股买点 → S5 适用。
登记前的规模核对（只数个数、不看被挡信号自己的收益）：数字写进 sim_changes 的登记节。
做法：两个都是逐个信号判定（票, 信号日）→ em_tick 0（不开新仓，名额留给下一个候选、钱留在核心）；其余 —— W2 + C 的买点、X6 等离场、核心 FJE、判断层 —— 全部同 B1。
  - FBM：这个年代全部 W2 信号的假想单笔（combo_all_posthoc 面板 D：net = X6 离场的净收益 %、hold = 持有交易日）；对（t, d）：同一只票、假想离场日（信号日位置 + hold）
    < d 的位置、且 ≥ d 的位置 − 120 的信号里，离场最晚的那一笔 net < 0 → 挡。
  - NEV：日收益 r、σ = 之前 60 天（至少 40 天）r 的标准差、量均 = 之前 50 天（至少 30 天）平均；坏消息日 = r < −3σ 且 量 ≥ 2 × 量均；（t, d）之前 20 个交易日（不含 d）
    有坏消息日 → 挡。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）按同样的定义挡（FBM 用各自池子的假想单笔），
  保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop4.stage1（= 第三个循环的 stage1；trade = S5，lenses = None，posthoc = None），两个各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状 = research_loop4 事先写定的逐个信号随机挡（random_signal_block：每个候选信号以
  这个做法在那个年代实际挡掉的比例随机挡；种子 numpy.random.default_rng([20261003, s])）。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号与成交、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔。
事前预期（照实写，写在看结果之前）：两个都挡得少（B1 成交里各碰到几笔），差很小；FBM 先验弱、第一关约 3%；NEV 有文献但突破之前刚大跌的票少，第一关约 3%；
  第二关各约 10% → 「更好候选」约 0.6%。
运行：python scripts/loop4_r01_memory.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop4_r01_memory.md / .json。非投资建议。
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

ROUND = 1
IDS = ("FBM", "NEV")
FAMILY = {"FBM": "选股·个股记忆", "NEV": "选股·消息冲击"}
POSTHOC = False
KIND = "stock"
FBM_LOOKBACK = 120                                                           # 上一次突破在 120 个交易日以内结束
NEV_WIN, NEV_SIG, NEV_VOL, SD_N, SD_MIN, VOL_N, VOL_MIN = 20, 3.0, 2.0, 60, 40, 50, 30
OUT = "loop4_r01_memory"


# ───────────────────────── 纯函数（tests/test_loop4_r01.py） ─────────────────────────
def fbm_gate(tickers, dates, panel: pd.DataFrame, days) -> np.ndarray:
    """（票, 信号日）→ 同一只票、在信号日之前 FBM_LOOKBACK 个交易日以内结束的假想单笔里离场最晚的那一笔亏了 → True。
    panel = 研究面板（ticker / date / net / hold；hold = 持有交易日）；days = 交易日历。"""
    days = pd.DatetimeIndex(days)
    P = panel[["ticker", "date", "net", "hold"]].copy()
    P["_p"] = days.searchsorted(pd.to_datetime(P["date"]).dt.normalize())
    P["_x"] = P["_p"] + P["hold"].astype(int)
    by = {t: g.sort_values("_x") for t, g in P.groupby("ticker")}
    out = np.zeros(len(tickers), bool)
    for k, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        g = by.get(t)
        if g is None:
            continue
        p = int(days.searchsorted(pd.Timestamp(d).normalize()))
        done = g[(g["_x"] < p) & (g["_x"] >= p - FBM_LOOKBACK)]
        out[k] = bool(len(done)) and float(done["net"].iloc[-1]) < 0
    return out


def shock_days(df: pd.DataFrame) -> pd.Series:
    """坏消息日：日收益 < −NEV_SIG × 之前 SD_N 天的标准差，且成交量 ≥ NEV_VOL × 之前 VOL_N 天平均（都只用前一天为止的数据）。"""
    c, v = df["Close"].astype(float), df["Volume"].astype(float)
    r = c.pct_change()
    sd = r.rolling(SD_N, min_periods=SD_MIN).std().shift(1)
    va = v.rolling(VOL_N, min_periods=VOL_MIN).mean().shift(1)
    return ((r < -NEV_SIG * sd) & (v >= NEV_VOL * va)).fillna(False)


def nev_gate(tickers, dates, fa: dict, cache: dict | None = None) -> np.ndarray:
    """（票, 信号日 d）→ d 之前 NEV_WIN 个交易日（不含 d）有坏消息日 → True；没有 K 线 → 不挡。"""
    cache = {} if cache is None else cache
    out = np.zeros(len(tickers), bool)
    for k, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        if t not in fa:
            continue
        if t not in cache:
            cache[t] = shock_days(fa[t])
        s = cache[t]
        p = int(s.index.searchsorted(pd.Timestamp(d)))
        out[k] = bool(s.iloc[max(0, p - NEV_WIN):p].any())
    return out


# ───────────────────────── 输入 ─────────────────────────
def ticks(W: dict) -> dict:
    """{年代: {FBM: em_tick, NEV: em_tick}}：这个年代全部 W2 信号（A；B1 的候选是它的子集）里被挡的。"""
    A, D = W["A"], W["D"]
    out = {}
    for e in L2.ERAS:
        tk, dt = A[e]["ticker"].to_numpy(), A[e]["date"].to_numpy()
        days = W["ctx"][e]["days"]
        g = {"FBM": fbm_gate(tk, dt, D[e], days), "NEV": nev_gate(tk, dt, W["SM"][e]["fa"])}
        out[e] = {k: R12.tick_of(tk, dt, g[k]) for k in IDS}
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold, fa in (("W", "E", W["SM"]["W"]["fa"]), ("Jx", "J", W["SM"]["J2"]["fa"])):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        tk, dt = X["ticker"].to_numpy(), X["date"].to_numpy()
        days = W["ctx"][fold]["days"]
        gates = {"FBM": fbm_gate(tk, dt, D[s], days), "NEV": nev_gate(tk, dt, fa)}
        for k in IDS:
            g = gates[k]
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[k][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def scale(W: dict, b1_trades: dict) -> dict:
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
        gx = {"FBM": fbm_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), D[e], days), "NEV": nev_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), fa)}
        gt = {"FBM": fbm_gate(tr["ticker"].to_numpy(), sig, D[e], days) if len(tr) else np.array([], bool),
              "NEV": nev_gate(tr["ticker"].to_numpy(), sig, fa) if len(tr) else np.array([], bool)}
        out[e] = {"signals": int(len(X)), "b1_trades": int(len(tr)),
                  **{k: {"signals_blocked": int(gx[k].sum()), "trades_blocked": int(gt[k].sum())} for k in IDS}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r01_memory.py", "scripts/loop3_r12_corediv.py",
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
    tk = ticks(W)
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
    os_ = other_stocks(W)
    s1 = {k: R4.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "ticks": {e: {k: len(tk[e][k]) for k in IDS} for e in L2.ERAS}, "scale": scale(W, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"FBM": "同一只票上一次突破刚失败（120 个交易日以内结束、亏损）→ 不开新仓", "NEV": "信号前 20 个交易日有放量大跌日（< −3σ、量 ≥ 2 倍）→ 不开新仓"}
    L = [f"# 第四个研究循环（选股）第 1 轮：个股记忆 FBM / 消息冲击 NEV（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r01_memory.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | FBM（Calmar 差） | NEV（Calmar 差） | 个股笔数 B1 → FBM / NEV |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + f" | {t['B1']} → {t['FBM']} / {t['NEV']} |")
    sc = res["scale"]
    L += ["", "规模与被挡的（不参与判定）："]
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
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    tk = ticks(W)
    print(json.dumps({"scale": scale(W, b1), "ticks": {e: {k: len(tk[e][k]) for k in IDS} for e in L2.ERAS}}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 两个账户都与 B1 逐项相同；② em_tick 对数 > 0（不看收益）。"""
    W = L2.load()
    tk = ticks(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {"J": {k: {} for k in IDS}}
    same = {k: all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys) for k, over in runs(empty, "J").items()}
    n = {k: len(v["em_tick"]) for k, v in runs(tk, "J").items()}
    print(json.dumps({"empty_same_as_b1": same, "counts_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 1 轮：FBM / NEV（选股：个股记忆、消息冲击）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
