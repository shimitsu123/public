"""loop3_r12_corediv.py — 第三个研究循环第 12 轮（选股，最后 2 个做法）：与核心高相关的票不买 CRC、分红刚减少 / 停发的票不买 DVC
（2026-10-03 登记；先提交后只运行一次；用掉 2 个做法 → 20 / 20；家族「选股·组合分散」2 / 3、新家族「选股·分红变化」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop3.py（改个股买点 → kind = "stock"，第二关的形状在第一关全过之后另行登记时写定）；基准 B1：scripts/loop2_common.py。
为什么这两个（照实写）：第 10 / 11 轮知道了 B1 的个股层名额几乎从不满、被挡的候选的钱回到核心（纳指 × 日元）→ 选股过滤只有在「被挡的那些在持有期里
  不如核心」时才会让账户变好。两个按这个想法、又有文献或机制的题：
  - CRC（核心相关）：日本个股的周收益与核心（纳指 100 × USD/JPY）过去 104 周的相关在当月横截面最高的三分之一 → 下一个月不开新仓。
    想法：和核心高度同涨同跌的日本个股只是「带个股噪音的核心」，挡掉之后钱直接拿核心（同样的方向、少了个股风险和买卖成本）；与核心低相关的票才是
    账户真正的分散（Markowitz 1952 的组合分散；这里只用来定「哪些票不值得占名额」）。周收益（周五收盘）避开日美交易时间不同步。
  - DVC（分红变化）：最近一次分红比一年前同一期少 10% 以上，或一年前同一期有分红而这一期过了 15 天还没有（停发）→ 不开新仓。
    文献：Michaely, Thaler & Womack（1995，J. Finance）减配 / 停发之后约一年股价偏弱；Healy & Palepu（1988）。分红 = Yahoo 的每股分红（按拆股调整，
    权利落ち日；var/cache/leap_yf/，与第一轮跃迁循环的股息率同一来源）；查不到 → 不挡。
  以前的选股研究用过 β / 与指数（日経）低相关（只在探索里）、股息率（高低），没用过「与核心的相关」和「分红的变化」→ 新方法、不是事后组合（S7 不适用）；
  阈值用最简单的定法（横截面三分之一、10%）—— 没有学出来的参数（S6 不适用）；改个股买点 → S5 适用。
登记前的规模核对（只数个数、不看被挡信号自己的收益；scratch 脚本，数字写进 sim_changes 的登记节）：B1 实际的日本个股成交 Z 35 / E 43 / J 63 笔里
  CRC 碰到 5 / 7 / 14 笔、DVC 1 / 3 / 6 笔。
做法：
  - CRC：每个月末 t：周收益（W-FRI）与核心周收益过去 104 周（至少 52 周）的相关；≥ 当月横截面（那个年代账户的日本个股池，不含核心 ETF）2/3 分位 → 月 t+1 的
    信号不开新仓；算不出的不挡。接法 = em_tick（同第 6 / 7 / 10 轮）。
  - DVC：信号日 d：最近一次分红 L（权利落ち日 ≤ d、在 200 天以内）与它一年前同一期的分红（落ち日在 L − 410〜L − 320 天）比，L < 0.9 × 一年前 → 挡；
    或一年前同一期有分红 q（落ち日在 d − 410〜d − 380 天）而 q + 320 天之后到 d 还没有分红 → 挡（停发）。接法 = em_tick（被挡的信号日 → 0）。
  其余 —— W2 + C 的买点、X6 等离场、核心 FJE、判断层 —— 全部同 B1。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）：CRC 按各自池子的横截面挡、DVC 按各自的分红挡，
  保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop3.stage1（trade = S5，lenses = None，posthoc = None），两个各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状预定 = 同样强度的随机挡（CRC：每个月从有值的票里随机挑与真实同样多的票；
  DVC：每个候选信号以 DVC 在那个年代实际挡掉的比例随机挡；种子 numpy.random.default_rng([20261003, s])），细节在那时写定。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② CRC / DVC 的 em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号数与成交、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔；DVC 查不到分红的票数。
事前预期（照实写，写在看结果之前）：CRC 挡掉 B1 成交的 14〜22%，钱回核心 —— Z（日本大涨、纳指平）可能吃亏（但 Z 只碰到 5 笔）；J 里高相关的多是半导体 /
  电子，2023〜2024 涨得多 → 可能为负；第一关约 5%。DVC 挡得少（1 / 3 / 6 笔），差很小；第一关约 3%。第二关各约 10% → 「更好候选」约 1%。
运行：python scripts/loop3_r12_corediv.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop3_r12_corediv.md / .json。非投资建议。
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
import research_loop3 as R3                                                  # noqa: E402

ROUND = 12
IDS = ("CRC", "DVC")
FAMILY = {"CRC": "选股·组合分散", "DVC": "选股·分红变化"}
POSTHOC = False
KIND = "stock"
CORR_W, CORR_MIN, TOP_Q = 104, 52, 2 / 3                                      # 104 周相关、至少 52 周；横截面最高的三分之一
CUT, RECENT, PREV_LO, PREV_HI, OMIT_LO, OMIT_HI, OMIT_GAP = 0.9, 200, 410, 320, 410, 380, 320
OUT = "loop3_r12_corediv"
CORE = X3.CORE


# ───────────────────────── 纯函数（tests/test_loop3_r12.py） ─────────────────────────
def weekly_ret(close: pd.Series) -> pd.Series:
    c = close.astype(float).dropna()
    return c.resample("W-FRI").last().dropna().pct_change().dropna()


def core_corr_monthly(close: pd.Series, core_w: pd.Series, months: pd.PeriodIndex) -> pd.Series:
    """每个月末：股票周收益与核心周收益过去 CORR_W 周（至少 CORR_MIN 周）的相关（那个月最后一周的值；月中没有周 → NaN）。"""
    x = pd.concat([weekly_ret(close), core_w], axis=1, keys=["s", "c"]).dropna()
    if len(x) < CORR_MIN:
        return pd.Series(np.nan, index=months)
    r = x["s"].rolling(CORR_W, min_periods=CORR_MIN).corr(x["c"])
    m = r.groupby(r.index.to_period("M")).last()
    return m.reindex(months)


def top_third(P: pd.DataFrame) -> pd.DataFrame:
    """每个月：≥ 当月横截面 2/3 分位 → 被挡（True）；NaN → 不挡。"""
    q = P.quantile(TOP_Q, axis=1, numeric_only=True)
    return P.ge(q, axis=0) & P.notna()


def div_cut(div: pd.Series | None, d) -> bool:
    """信号日 d：最近一次分红比一年前同一期少 10% 以上，或一年前同一期有分红而这一期过期还没有（停发）→ True。div = 每股分红（落ち日为索引，>0 才算）。"""
    if div is None or not len(div):
        return False
    d = pd.Timestamp(d).normalize()
    v = div[(div > 0) & (div.index <= d)]
    if not len(v):
        return False
    last_d, last_v = v.index[-1], float(v.iloc[-1])
    if (d - last_d).days <= RECENT:
        prev = v[(v.index >= last_d - pd.Timedelta(days=PREV_LO)) & (v.index <= last_d - pd.Timedelta(days=PREV_HI))]
        if len(prev) and last_v < CUT * float(prev.iloc[-1]):
            return True
    q = v[(v.index >= d - pd.Timedelta(days=OMIT_LO)) & (v.index <= d - pd.Timedelta(days=OMIT_HI))]
    for qd in q.index:                                                       # 一年前同一期有分红、它之后 320 天到 d 都没有新的 → 停发
        if not len(v[(v.index > qd + pd.Timedelta(days=OMIT_GAP)) & (v.index <= d)]):
            return True
    return False


def dividends(t: str) -> pd.Series | None:
    """只读缓存（var/cache/leap_yf/；登记后的运行不再下载）；没有 → None（不挡）。"""
    import leap_data as LD
    p = LD._act_path(t)
    if not p.exists():
        return None
    a = pd.read_csv(p, index_col=0, parse_dates=True)
    if "div" not in a or not len(a):
        return None
    s = a["div"].astype(float).fillna(0.0)
    s.index = pd.DatetimeIndex(s.index).normalize()
    return s


def dvc_gate(tickers, dates, cache: dict | None = None) -> np.ndarray:
    cache = {} if cache is None else cache
    out = np.zeros(len(tickers), bool)
    for k, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        t = str(t)
        if t not in cache:
            cache[t] = dividends(t)
        out[k] = div_cut(cache[t], d)
    return out


def tick_of(tickers, dates, gate: np.ndarray) -> dict:
    """被挡的（票, 信号日）→ em_tick {(票, 信号日): 0.0}。"""
    return {(str(t), pd.Timestamp(d)): 0.0 for t, d, g in zip(tickers, pd.to_datetime(np.asarray(dates)), gate) if g}


# ───────────────────────── 输入 ─────────────────────────
def core_weekly(W: dict) -> pd.Series:
    inp = W["inp"]
    ndx = inp["ndx"].astype(float).dropna()
    fx = inp["fx"].astype(float).reindex(ndx.index).ffill()
    return weekly_ret((ndx * fx).dropna())


def crc_table(fa: dict, names, core_w: pd.Series, months: pd.PeriodIndex) -> pd.DataFrame:
    keys = [t for t in names if str(t).endswith(".T") and t not in CORE and t in fa]
    P = pd.DataFrame({t: core_corr_monthly(fa[t]["Close"], core_w, months) for t in keys}, index=months)
    return top_third(P)


def inputs(W: dict) -> dict:
    """{年代 / W / Jx: CRC 被挡表}。"""
    cw = core_weekly(W)
    months = RM.market_m(W).index
    SM = W["SM"]
    out = {}
    for key, fa, names in [(e, SM[e]["fa"], RM.era_names(W, e)) for e in L2.ERAS] + [("W", SM["W"]["fa"], list(SM["W"]["fa"])),
                                                                                    ("Jx", SM["J2"]["fa"], list(SM["J2"]["fa"]))]:
        out[key] = crc_table(fa, names, cw, months)
    return out


def dvc_ticks(W: dict, cache: dict) -> dict:
    """{年代: em_tick}：这个年代全部 W2 信号（A；B1 的候选是它的子集）里分红刚减少 / 停发的。"""
    A = W["A"]
    return {e: tick_of(A[e]["ticker"].to_numpy(), A[e]["date"].to_numpy(),
                       dvc_gate(A[e]["ticker"].to_numpy(), A[e]["date"].to_numpy(), cache)) for e in L2.ERAS}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, G: dict, cache: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        gates = {"CRC": RM.gate_of(G[s], X["ticker"].to_numpy(), X["date"].to_numpy()),
                 "DVC": dvc_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), cache)}
        nodiv = int(sum(1 for t in set(X["ticker"]) if cache.get(str(t)) is None))
        for k in IDS:
            g = gates[k]
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[k][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None, **({"no_div_tickers": nodiv} if k == "DVC" else {})}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def scale(W: dict, G: dict, cache: dict, b1_trades: dict) -> dict:
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        X = A[e][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != e]), A[e])]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])] if len(tr) else []
        out[e] = {"signals": int(len(X)), "b1_trades": int(len(tr)),
                  "CRC": {"signals_blocked": int(RM.gate_of(G[e], X["ticker"].to_numpy(), X["date"].to_numpy()).sum()),
                          "trades_blocked": int(RM.gate_of(G[e], tr["ticker"].to_numpy(), np.asarray(sig)).sum()) if len(tr) else 0},
                  "DVC": {"signals_blocked": int(dvc_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), cache).sum()),
                          "trades_blocked": int(dvc_gate(tr["ticker"].to_numpy(), np.asarray(sig), cache).sum()) if len(tr) else 0}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r12_corediv.py", "scripts/loop3_r10_resmom.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def runs(W: dict, e: str, G: dict, dv: dict) -> dict:
    return {"CRC": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}, "DVC": {"em_tick": dv[e]}}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    G = inputs(W)
    cache: dict = {}
    dv = dvc_ticks(W, cache)
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R3.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(W, e, G, dv).items():
            rc = L2.run(W, e, **over)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, G, cache)
    s1 = {k: R3.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "dvc_ticks": {e: len(dv[e]) for e in L2.ERAS}, "scale": scale(W, G, cache, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"CRC": "与核心（纳指 × 日元）104 周相关在横截面最高的三分之一 → 不开新仓", "DVC": "分红比一年前同一期少 10% 以上 / 停发 → 不开新仓"}
    L = [f"# 第三个研究循环第 12 轮（选股）：与核心高相关 CRC / 分红减少 DVC（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r12_corediv.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R3.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | CRC（Calmar 差） | DVC（Calmar 差） | 个股笔数 B1 → CRC / DVC |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + f" | {t['B1']} → {t['CRC']} / {t['DVC']} |")
    sc = res["scale"]
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；DVC 在全部 W2 信号里挡 {res['dvc_ticks'][e]} 个；"
                 + "；".join(f"{k} 挡信号 {x[k]['signals_blocked']} 个、B1 实际成交 {x[k]['trades_blocked']} 笔" for k in IDS))
    for k in IDS:
        for s in ("W", "Jx"):
            o = res["other_stocks"][k][s]
            extra = f"（查不到分红的票 {o['no_div_tickers']} 只 → 不挡）" if "no_div_tickers" in o else ""
            L.append(f"- {k} {s}：B1 会买的信号 {o['n']} 个，挡掉 {o['gone_n']} 个（胜率 {_f(o['gone_win'], '{:.1f}')}%、每笔 {_f(o['gone_mean'], '{:+.2f}')}%）；"
                     f"保留 {o['kept']} 个 → 胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp{extra}")
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


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 两个账户都与 B1 逐项相同；② em_tick 对数 > 0（不看收益）。"""
    W = L2.load()
    G = inputs(W)
    cache: dict = {}
    dv = dvc_ticks(W, cache)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {"J": G["J"] & False}
    same = {k: all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys) for k, over in runs(W, "J", empty, {"J": {}}).items()}
    n = {k: len(v["em_tick"]) for k, v in runs(W, "J", G, dv).items()}
    print(json.dumps({"empty_same_as_b1": same, "counts_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 12 轮：CRC / DVC（选股：与核心高相关、分红减少）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
