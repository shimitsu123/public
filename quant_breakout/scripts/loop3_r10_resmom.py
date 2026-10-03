"""loop3_r10_resmom.py — 第三个研究循环第 10 轮（选股）：残差动量 RMO / 路径连续性 FIP —— 日本个股的买点只留「动量质量」好的一半
（2026-10-02 登记；先提交后只运行一次；用掉 2 个做法 → 17 / 20；新家族「选股·动量质量」2 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop3.py（改个股买点 → kind = "stock"，第二关的形状在第一关全过之后另行登记时写定）；基准 B1：scripts/loop2_common.py；
买点的接法 = candle_portfolio.run 的 em_tick（第 6 轮 IBS / 第 7 轮 DMN 同一个钩子：被挡的候选不开新仓，名额留给下一个候选、钱留在核心）。
为什么这两个（照实写）：选题盘点（sim_changes 2026-10-02 23:40 一节）—— 以前的选股研究用过原始动量（20〜250 日、12-1 个月）、52 周高点、业种动量、
  个股相对业种、60 日波动、β 等 53 个特征与 45 个指标，**没用过**：
  - 残差动量（residual momentum；Blitz, Huij & Martens 2011，J. Empirical Finance；Chaves 2016，J. Portfolio Management 的国际样本里日本也成立，
    而原始动量在日本几乎不成立）：去掉大盘 β 之后的 12-1 个月动量，比原始动量稳。
  - 路径连续性（frog-in-the-pan；Da, Gurun & Warachka 2014，Review of Financial Studies）：同样涨幅，由很多小涨日组成（信息连续）的比几次跳涨（信息离散）
    之后更会继续涨。
  → 新方法、新家族，不是事后组合（S7 不适用）；参数全用文献的设定（36 个月回归、12-1 个月形成期、横截面一半），没有学出来的参数（S6 不适用）；改个股买点 → S5 适用。
做法（每个月末 t 算一次；信号日 d 用 d 所在月份之前的那个月末 t 的值 → 只用当时已知的数据；横截面 = 那个年代账户的日本个股池（不含核心 ETF），
  S5 的 W / Jx 用各自的池子）：
  - RMO：月收益对日経225 月收益回归（月末 t 往前 36 个月，至少 24 个月）→ 形成期 t−11〜t−1（11 个月，跳过最近一个月）的残差合计 ÷ 残差标准差；
    信号日用的 RMO 低于当月横截面中位数 → 不开新仓（≥ 中位数的一半照常）；算不出（历史不够）→ 照常（不挡）。
  - FIP：形成期 t−11〜t−1 的日收益：ID = sign(形成期涨跌) × (下跌日比例 − 上涨日比例)（小 = 连续）；ID 高于当月横截面中位数（离散的一半）→ 不开新仓；
    算不出 → 照常。
  其余 —— W2 + C 的买点、X6 等离场、核心 FJE、判断层 —— 全部同 B1。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折），按同一规则（各自池子的横截面）挡掉之后
  保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop3.stage1（trade = S5，lenses = None，posthoc = None），两个做法各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状预定 = 同样强度的随机挡 —— 每个月从池子里随机挑与真实同样多的票挡掉
  （numpy.random.default_rng([20261003, s])，s = 0〜399），细节在那时写定。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② RMO / FIP 的 em_tick 对数 > 0。
规模核对（登记前，只看 B1 的信号与成交、不看收益）：各年代被挡的「票 × 月」比例、B1 会买的信号与 B1 实际的日本个股成交里落在被挡的比例、B1 因名额满跳过的候选数。
只描述（不参与判定）：各年代被挡的信号数、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔；RMO 与原始 12-1 动量的相关。
事前预期（照实写，按文献与一般经验估计，不是这一轮的结果）：突破信号本来就是涨得多的票 → RMO 挡掉的可能不多（多是靠大盘 β 涨上来的）；FIP 挡掉的可能多一些
  （突破常常伴随跳涨）。文献里两者都是「赢家里再挑」有效；日经225 大盘股、加上 W2 + C 之后增量可能很小。第一关 RMO 约 10〜15%、FIP 约 5〜10%，
  第二关各约 10% → 「更好候选」约 2%。
运行：python scripts/loop3_r10_resmom.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop3_r10_resmom.md / .json。非投资建议。
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
import research_loop3 as R3                                                  # noqa: E402

ROUND = 10
IDS = ("RMO", "FIP")
FAMILY = {"RMO": "选股·动量质量", "FIP": "选股·动量质量"}
POSTHOC = False
KIND = "stock"
REG_M, REG_MIN, FORM_M = 36, 24, 11                                           # 36 个月回归（至少 24）；形成期 11 个月（t−11〜t−1）
OUT = "loop3_r10_resmom"
CORE = X3.CORE


# ───────────────────────── 纯函数（tests/test_loop3_r10.py） ─────────────────────────
def month_end_close(close: pd.Series) -> pd.Series:
    c = close.astype(float).dropna()
    return c.groupby(c.index.to_period("M")).last()


def monthly_ret(close: pd.Series) -> pd.Series:
    """月末收盘 → 月收益（索引 = Period[M]）。"""
    return month_end_close(close).pct_change()


def resid_mom(ri: pd.Series, rm: pd.Series) -> pd.Series:
    """每个月 t（Period[M]，rm 的月历）：t−35〜t 的月收益回归 ri = a + b·rm（至少 24 个月）→ 形成期 t−11〜t−1 的残差合计 ÷ 残差标准差。算不出 → NaN。"""
    idx = rm.index
    y, x = ri.reindex(idx).to_numpy(float), rm.to_numpy(float)
    out = np.full(len(idx), np.nan)
    for k in range(FORM_M, len(idx)):
        a0 = max(0, k - REG_M + 1)
        wy, wx = y[a0:k + 1], x[a0:k + 1]
        ok = np.isfinite(wy) & np.isfinite(wx)
        fy, fx = y[k - FORM_M:k], x[k - FORM_M:k]
        if ok.sum() < REG_MIN or not (np.isfinite(fy).all() and np.isfinite(fx).all()):
            continue
        vx = np.var(wx[ok], ddof=1)
        if not vx > 0:
            continue
        b = np.cov(wx[ok], wy[ok], ddof=1)[0, 1] / vx
        a = wy[ok].mean() - b * wx[ok].mean()
        e = fy - a - b * fx
        s = e.std(ddof=1)
        out[k] = e.sum() / s if s > 0 else np.nan
    return pd.Series(out, index=idx)


def info_discreteness(close: pd.Series, months: pd.PeriodIndex) -> pd.Series:
    """每个月 t：形成期 t−11〜t−1 的日收益 → ID = sign(累计涨跌) × (下跌日比例 − 上涨日比例)。11 个月都要有数据，否则 NaN。"""
    c = close.astype(float).dropna()
    r = c.pct_change().dropna()
    per = r.index.to_period("M")
    g = pd.DataFrame({"n": 1.0, "pos": (r > 0).astype(float), "neg": (r < 0).astype(float), "lr": np.log1p(r)}, index=r.index).groupby(per).sum()
    g = g.reindex(months)
    n, pos, neg, lr = (g[k].to_numpy(float) for k in ("n", "pos", "neg", "lr"))
    out = np.full(len(months), np.nan)
    for k in range(FORM_M, len(months)):
        sl = slice(k - FORM_M, k)
        if not (np.isfinite(n[sl]).all() and (n[sl] > 0).all()):
            continue
        tot = n[sl].sum()
        out[k] = np.sign(np.expm1(lr[sl].sum())) * (neg[sl].sum() - pos[sl].sum()) / tot
    return pd.Series(out, index=months)


def scores(fa: dict, names, rm: pd.Series) -> dict[str, pd.DataFrame]:
    """池子里每只日本个股的月度 RMO / FIP（行 = 月 Period，列 = 票）。"""
    keys = [t for t in names if str(t).endswith(".T") and t not in CORE and t in fa]
    rmo, fip = {}, {}
    for t in keys:
        cl = fa[t]["Close"]
        rmo[t] = resid_mom(monthly_ret(cl), rm)
        fip[t] = info_discreteness(cl, rm.index)
    return {"RMO": pd.DataFrame(rmo, index=rm.index), "FIP": pd.DataFrame(fip, index=rm.index)}


def blocked_months(S: pd.DataFrame, kind: str) -> pd.DataFrame:
    """每个月 t 的横截面中位数 → 被挡（True）：RMO 低于中位数 / FIP 高于中位数；NaN → 不挡。行 = 月 t（用在下一个月的信号上）。"""
    med = S.median(axis=1, skipna=True)
    if kind == "RMO":
        b = S.lt(med, axis=0)
    else:
        b = S.gt(med, axis=0)
    return b & S.notna()


def gate_of(B: pd.DataFrame, tickers, dates) -> np.ndarray:
    """每个（票, 信号日 d）→ 是否被挡：用 d 所在月份的前一个月 t 的那一行。"""
    out = np.zeros(len(tickers), bool)
    if B.empty:
        return out
    for k, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        if t not in B.columns:
            continue
        m = pd.Timestamp(d).to_period("M") - 1
        if m in B.index:
            out[k] = bool(B.at[m, t])
    return out


def em_tick_of(B: pd.DataFrame, days) -> dict:
    """被挡的「票 × 月 t」→ em_tick {(票, 信号日): 0.0}：t 的下一个月里引擎的每个交易日。"""
    days = pd.DatetimeIndex(days)
    nxt = days.to_period("M")
    out = {}
    for t in B.columns:
        bm = set(B.index[B[t].to_numpy(bool)] + 1)
        if not bm:
            continue
        for d, p in zip(days, nxt):
            if p in bm:
                out[(t, d)] = 0.0
    return out


# ───────────────────────── 输入 ─────────────────────────
def market_m(W: dict) -> pd.Series:
    return monthly_ret(W["inp"]["n225"]["Close"])


def era_names(W: dict, e: str) -> list[str]:
    ctx = W["ctx"][e]
    return [str(ctx["names"][j]) for j in ctx["cols"]]


def inputs(W: dict) -> dict:
    """{年代 / W / Jx: {"RMO": 被挡表, "FIP": 被挡表, "S": 分数}}。"""
    rm = market_m(W)
    SM = W["SM"]
    out = {}
    for key, fa, names in [(e, SM[e]["fa"], era_names(W, e)) for e in L2.ERAS] + [("W", SM["W"]["fa"], list(SM["W"]["fa"])),
                                                                                 ("Jx", SM["J2"]["fa"], list(SM["J2"]["fa"]))]:
        S = scores(fa, names, rm)
        out[key] = {"S": S, "RMO": blocked_months(S["RMO"], "RMO"), "FIP": blocked_months(S["FIP"], "FIP")}
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, G: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        for k in IDS:
            g = gate_of(G[s][k], X["ticker"].to_numpy(), X["date"].to_numpy())
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[k][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def scale(W: dict, G: dict, b1_trades: dict, b1_full: dict) -> dict:
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        lo, hi = pd.Period(pd.Timestamp(a), "M"), pd.Period(pd.Timestamp(b) if b else pd.Timestamp(L2.J_END), "M")
        X = A[e][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != e]), A[e])]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])] if len(tr) else []
        row = {"signals": int(len(X)), "b1_trades": int(len(tr)), "b1_full_skips": b1_full.get(e)}
        for k in IDS:
            B = G[e][k]
            w = B[(B.index >= lo - 1) & (B.index <= hi)]
            row[k] = {"blocked_pct": round(float(w.to_numpy().mean() * 100), 1) if w.size else None,
                      "signals_blocked": int(gate_of(B, X["ticker"].to_numpy(), X["date"].to_numpy()).sum()),
                      "trades_blocked": int(gate_of(B, tr["ticker"].to_numpy(), np.asarray(sig)).sum()) if len(tr) else 0}
        out[e] = row
    for s in ("W", "Jx"):
        fold = "E" if s == "W" else "J"
        X = D[s][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != fold]), D[s])]
        out[s] = {"signals": int(len(X)), **{k: int(gate_of(G[s][k], X["ticker"].to_numpy(), X["date"].to_numpy()).sum()) for k in IDS}}
    S = G["J"]["S"]
    out["corr_rmo_vs_r12"] = None
    try:
        r12 = pd.DataFrame({t: monthly_ret(W["SM"]["J"]["fa"][t]["Close"]).rolling(FORM_M).apply(lambda v: np.prod(1 + v) - 1, raw=True)
                            .shift(1) for t in S["RMO"].columns}).reindex(S["RMO"].index)
        a, b = S["RMO"].stack().dropna(), r12.stack().dropna()                    # pandas 3 的 stack 不再丢 NaN
        j = a.index.intersection(b.index)
        out["corr_rmo_vs_r12"] = round(float(np.corrcoef(a[j], b[j])[0, 1]), 3) if len(j) > 10 else None
    except Exception:                                                         # noqa: BLE001
        pass
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r10_resmom.py", "scripts/candle_portfolio.py",
                                 "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py", "scripts/research_loop3.py",
                                 "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def full_skips() -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1] if JS.RealLotEngine.LAST else None
    return int((eng.skipped or {}).get("full", 0)) if eng is not None else 0


def runs(W: dict, e: str, G: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {k: {"em_tick": em_tick_of(G[e][k], days)} for k in IDS}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    G = inputs(W)
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R3.load_state().get("baseline") or {}
    base, cand, trades, b1_trades, b1_full = {}, {k: {} for k in IDS}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        b1_full[e] = full_skips()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(W, e, G).items():
            rc = L2.run(W, e, **over)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, G)
    s1 = {k: R3.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "scale": scale(W, G, b1_trades, b1_full), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"RMO": "残差动量低于当月横截面中位数 → 不开新仓", "FIP": "路径离散（ID 高于中位数）→ 不开新仓"}
    L = [f"# 第三个研究循环第 10 轮（选股）：残差动量 RMO / 路径连续性 FIP（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r10_resmom.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R3.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | RMO（Calmar 差） | FIP（Calmar 差） | 个股笔数 B1 → RMO / FIP |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + f" | {t['B1']} → {t['RMO']} / {t['FIP']} |")
    sc = res["scale"]
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔（因名额满跳过的候选 {x['b1_full_skips']} 个）；"
                 + "；".join(f"{k} 挡「票 × 月」{_f(x[k]['blocked_pct'], '{:.1f}')}%、信号 {x[k]['signals_blocked']} 个、B1 实际成交 {x[k]['trades_blocked']} 笔"
                            for k in IDS))
    for k in IDS:
        for s in ("W", "Jx"):
            o = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：B1 会买的信号 {o['n']} 个，挡掉 {o['gone_n']} 个（胜率 {_f(o['gone_win'], '{:.1f}')}%、每笔 {_f(o['gone_mean'], '{:+.2f}')}%）；"
                     f"保留 {o['kept']} 个 → 胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    L.append(f"- J 池子：RMO 与原始 12-1 个月动量的相关 {_f(sc.get('corr_rmo_vs_r12'))}")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数个数（跑 B1、不跑候选、不看收益）。"""
    W = L2.load()
    G = inputs(W)
    b1, full = {}, {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
        full[e] = full_skips()
    print(json.dumps(scale(W, G, b1, full), ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 两个做法的账户都与 B1 逐项相同；② em_tick 对数 > 0（不跑候选本身、不看收益）。"""
    W = L2.load()
    G = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {"J": {k: G["J"][k] & False for k in IDS}}
    same = {k: all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys) for k, over in runs(W, "J", empty).items()}
    n = {k: len(v["em_tick"]) for k, v in runs(W, "J", G).items()}
    print(json.dumps({"empty_same_as_b1": same, "em_tick_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 10 轮：RMO / FIP（残差动量 / 路径连续性 → 选股）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
