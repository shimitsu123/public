"""loop3_r11_lottery.py — 第三个研究循环第 11 轮（选股，最后 3 个做法）：彩票型股票不买 MXR / IVH、同一业种不重复持有 SEC
（2026-10-03 登记；先提交后只运行一次；用掉 3 个做法 → 20 / 20；新家族「选股·彩票型」2 / 3、「选股·组合分散」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop3.py（改个股买点 → kind = "stock"，第二关的形状在第一关全过之后另行登记时写定）；基准 B1：scripts/loop2_common.py。
为什么这三个（照实写）：第 10 轮发现 B1 的个股层名额几乎从不满（名额满跳过的候选每个年代只有 1〜2 个），挡掉一半信号（RMO / FIP）会直接减少日本股票的仓位、
  钱回到核心，Z 2005 年少赚 20 pp 以上 → 这一轮只挡「少数、按文献最差的」（横截面最高的一成），或只在已经持有同业种时才挡，仓位减少得少。
  - MXR（彩票型：Bali, Cakici & Whitelaw 2011，J. Financial Economics）：上个月单日最大涨幅（MAX）在横截面最高的一成的股票，之后收益偏低。
  - IVH（特质波动：Ang, Hodrick, Xing & Zhang 2006 / 2009，国际样本含日本）：上个月特质波动（日收益对日経225 回归的残差标准差）在横截面最高的一成，之后收益偏低。
  - SEC（组合分散）：已经持有（或今天已排）同一个東証 33 业种的日本个股 → 这个候选不开新仓（4 个名额不集中在同一个业种）。
  以前的选股研究用过 60 日总波动、ATR、单日涨跌、业种动量、同业种 10 日内别的突破数等，没用过 MAX、特质波动、按持仓的业种上限 → 新方法、新家族，
  不是事后组合（S7 不适用）；阈值用文献的「最高一成」、业种上限 1 只 —— 没有学出来的参数（S6 不适用）；改个股买点 → S5 适用。
做法（MXR / IVH：每个月末 t 算一次，信号日用前一个月末 t 的值；横截面 = 那个年代账户的日本个股池（不含核心 ETF），S5 的 W / Jx 用各自的池子）：
  - MXR：月 t 里单日涨幅的最大值 ≥ 当月横截面 90 分位 → 下一个月这只票的信号不开新仓（那个月不足 15 个交易日 → 算不出 → 不挡）。
  - IVH：月 t 里日收益对日経225 日收益回归（至少 15 个交易日）的残差标准差 ≥ 当月横截面 90 分位 → 下一个月不开新仓。
  - SEC：引擎钩子 candle_portfolio.MixEngine.SECTOR_CAP（本轮加，缺省 None = B1 不变）：第 i 天收盘决策时，这只票的东証业种（今天的分类：
    var/industry_s33.json + var/policy_extra_pool.json；查不到业种 → 不挡）与正在持有（不含明天要卖的）或今天已排的日本个股相同 → 0（不开）。
  接法：MXR / IVH = em_tick（同第 6 / 7 / 10 轮）；SEC = 引擎钩子。其余 —— W2 + C 的买点、X6 等离场、核心 FJE、判断层 —— 全部同 B1。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）：MXR / IVH 按各自池子的横截面挡掉之后
  保留的 vs 全部；SEC 按（信号日、代码）的顺序贪心：同业种已保留的信号还在持有期里（信号日 ≤ d < 信号日 + 持有天数，交易日）→ 去掉；胜率差、每笔差都要 ≥ 0。
第一关：research_loop3.stage1（trade = S5，lenses = None，posthoc = None），三个做法各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状预定 = 同样强度的随机挡（MXR / IVH：每个月随机挑与真实同样多的票；
  SEC：每个日本个股候选以 SEC 在那个年代实际挡掉的比例随机不开；种子 numpy.random.default_rng([20261003, s])），细节在那时写定。
接线核对（登记前，不看候选的收益）：J 年代 ① MXR / IVH 挡的集合为空、SEC 的业种表为空 → 账户与 B1 逐项相同；② MXR / IVH 的 em_tick 对数 > 0、SEC 挡掉的候选 > 0。
规模核对（登记前，只看 B1 的信号与成交、不看收益）：各年代被挡的「票 × 月」比例、B1 会买的信号与 B1 实际成交里落在被挡的个数；B1 同时持有同业种的天数。
只描述（不参与判定）：各年代被挡的信号数、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔。
事前预期（照实写，按文献与一般经验估计）：日经225 大盘股里「彩票型」少、突破当月本来就常有大涨日 → MXR 挡到的突破可能偏好的（大涨是突破的一部分）→ 可能为负；
  IVH 类似但稍好；SEC 挡得少（4 个名额同业种的时候不多），回撤可能浅一点。第一关 MXR 约 5%、IVH 约 8%、SEC 约 8%，第二关各约 10% → 「更好候选」约 2%。
运行：python scripts/loop3_r11_lottery.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop3_r11_lottery.md / .json。非投资建议。
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

ROUND = 11
IDS = ("MXR", "IVH", "SEC")
FAMILY = {"MXR": "选股·彩票型", "IVH": "选股·彩票型", "SEC": "选股·组合分散"}
POSTHOC = False
KIND = "stock"
TOP_Q, MIN_DAYS = 0.90, 15                                                    # 横截面最高的一成；一个月至少 15 个交易日
OUT = "loop3_r11_lottery"
CORE = X3.CORE


# ───────────────────────── 纯函数（tests/test_loop3_r11.py） ─────────────────────────
def month_stats(close: pd.Series, mkt: pd.Series, months: pd.PeriodIndex) -> pd.DataFrame:
    """每个月：MAX = 单日涨幅最大值；IVOL = 日收益对大盘日收益回归的残差标准差（同一天两边都有的日子，至少 MIN_DAYS 个）。不够 → NaN。"""
    r = close.astype(float).dropna().pct_change().dropna()
    m = mkt.astype(float).dropna().pct_change().dropna()
    j = r.index.intersection(m.index)
    x = pd.DataFrame({"r": r.reindex(j), "m": m.reindex(j)})
    out = pd.DataFrame(np.nan, index=months, columns=["MAX", "IVOL"])
    for p, g in x.groupby(x.index.to_period("M")):
        if p not in out.index or len(g) < MIN_DAYS:
            continue
        rv, mv = g["r"].to_numpy(float), g["m"].to_numpy(float)
        out.at[p, "MAX"] = float(rv.max())
        vm = mv.var(ddof=1)
        if vm > 0:
            b = np.cov(mv, rv, ddof=1)[0, 1] / vm
            a = rv.mean() - b * mv.mean()
            out.at[p, "IVOL"] = float((rv - a - b * mv).std(ddof=1))
    return out


def top_decile(S: pd.DataFrame) -> pd.DataFrame:
    """每个月：≥ 当月横截面 90 分位 → 被挡（True）；NaN → 不挡。"""
    q = S.quantile(TOP_Q, axis=1, numeric_only=True)
    return S.ge(q, axis=0) & S.notna()


def panels(fa: dict, names, mkt: pd.Series, months: pd.PeriodIndex) -> dict[str, pd.DataFrame]:
    keys = [t for t in names if str(t).endswith(".T") and t not in CORE and t in fa]
    st = {t: month_stats(fa[t]["Close"], mkt, months) for t in keys}
    return {k: pd.DataFrame({t: st[t][k] for t in keys}, index=months) for k in ("MAX", "IVOL")}


def sector_greedy(tickers, dates, holds, sec: dict, days) -> np.ndarray:
    """S5 的 SEC：按（信号日、代码）排好的信号 → 同业种已保留的信号还在持有期里（交易日位置 p0 ≤ p < p0 + 持有天数）→ 去掉（True = 去掉）。"""
    pos = day_pos(dates, days)
    gone = np.zeros(len(pos), bool)
    live: dict[str, list[int]] = {}
    for k, (t, p, h) in enumerate(zip(tickers, pos, holds)):
        s = sec.get(str(t))
        if s is None:
            continue
        ends = [e for e in live.get(s, []) if e > p]
        if ends:
            gone[k] = True
            live[s] = ends
            continue
        live[s] = ends + [p + max(1, int(h))]
    return gone


def day_pos(dates, days) -> np.ndarray:
    return np.asarray(pd.DatetimeIndex(days).searchsorted(pd.to_datetime(np.asarray(dates)).normalize()), int)


def sector_map() -> dict[str, str]:
    import policy_event_data as PD
    return {str(t): s for t, s in {**PD.s33_map(), **PD.extra_pool()}.items() if s}


# ───────────────────────── 输入 ─────────────────────────
def inputs(W: dict) -> dict:
    """{年代 / W / Jx: {"MXR": 被挡表, "IVH": 被挡表}}。"""
    mkt = W["inp"]["n225"]["Close"]
    months = RM.market_m(W).index
    SM = W["SM"]
    out = {}
    for key, fa, names in [(e, SM[e]["fa"], RM.era_names(W, e)) for e in L2.ERAS] + [("W", SM["W"]["fa"], list(SM["W"]["fa"])),
                                                                                    ("Jx", SM["J2"]["fa"], list(SM["J2"]["fa"]))]:
        P = panels(fa, names, mkt, months)
        out[key] = {"MXR": top_decile(P["MAX"]), "IVH": top_decile(P["IVOL"])}
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, G: dict, sec: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])].copy()
        X = X.assign(_d=pd.to_datetime(X["date"]).dt.normalize()).sort_values(["_d", "ticker"], kind="mergesort")
        net = X["net"].to_numpy(float)
        gates = {k: RM.gate_of(G[s][k], X["ticker"].to_numpy(), X["date"].to_numpy()) for k in ("MXR", "IVH")}
        gates["SEC"] = sector_greedy(X["ticker"].to_numpy(), X["_d"].to_numpy(), X["hold"].to_numpy(), sec, W["ctx"][fold]["days"])
        for k in IDS:
            g = gates[k]
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[k][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def same_sector_days(tr: pd.DataFrame, sec: dict, a: str, b: str | None, days) -> int:
    """B1 的日本个股持仓里，有两只以上同业种同时持有的交易日数。"""
    x = X3.jp_stock_trades(tr, a, b)
    days = pd.DatetimeIndex(days)
    cnt: dict[tuple, int] = {}
    for t, d0, d1 in zip(x["ticker"], pd.to_datetime(x["entry_date"]), pd.to_datetime(x["exit_date"])):
        s = sec.get(str(t))
        if s is None:
            continue
        for d in days[(days >= d0) & (days < d1)]:
            cnt[(d, s)] = cnt.get((d, s), 0) + 1
    return len({d for (d, s), n in cnt.items() if n >= 2})


def scale(W: dict, G: dict, sec: dict, b1_trades: dict) -> dict:
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
        row = {"signals": int(len(X)), "b1_trades": int(len(tr)), "same_sector_days": same_sector_days(b1_trades[e], sec, a, b, days),
               "no_sector": int(sum(1 for t in tr["ticker"] if str(t) not in sec)) if len(tr) else 0}
        for k in ("MXR", "IVH"):
            B = G[e][k]
            w = B[(B.index >= lo - 1) & (B.index <= hi)]
            row[k] = {"blocked_pct": round(float(w.to_numpy().mean() * 100), 1) if w.size else None,
                      "signals_blocked": int(RM.gate_of(B, X["ticker"].to_numpy(), X["date"].to_numpy()).sum()),
                      "trades_blocked": int(RM.gate_of(B, tr["ticker"].to_numpy(), np.asarray(sig)).sum()) if len(tr) else 0}
        out[e] = row
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r11_lottery.py", "scripts/loop3_r10_resmom.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def sector_blocked() -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1] if JS.RealLotEngine.LAST else None
    return int((eng.skipped or {}).get("sector_cap", 0)) if eng is not None else 0


def runs(W: dict, e: str, G: dict, sec: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {"MXR": {"em_tick": RM.em_tick_of(G[e]["MXR"], days)}, "IVH": {"em_tick": RM.em_tick_of(G[e]["IVH"], days)},
            "SEC": {"sector_cap": sec}}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    G = inputs(W)
    sec = sector_map()
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R3.load_state().get("baseline") or {}
    base, cand, trades, b1_trades, blocked = {}, {k: {} for k in IDS}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(W, e, G, sec).items():
            rc = L2.run(W, e, **over)
            if k == "SEC":
                blocked[e] = sector_blocked()
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, G, sec)
    s1 = {k: R3.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades, "sec_blocked": blocked,
           "scale": scale(W, G, sec, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"MXR": "上个月单日最大涨幅在横截面最高一成 → 不开新仓", "IVH": "上个月特质波动在横截面最高一成 → 不开新仓",
            "SEC": "同一个東証业种已经持有 / 今天已排 → 不开新仓"}
    L = [f"# 第三个研究循环第 11 轮（选股）：彩票型 MXR / IVH、同业种不重复持有 SEC（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r11_lottery.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R3.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | MXR（Calmar 差） | IVH（Calmar 差） | SEC（Calmar 差） | 个股笔数 B1 → MXR / IVH / SEC |",
          "|---|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS)
            + f" | {t['B1']} → {t['MXR']} / {t['IVH']} / {t['SEC']} |")
    sc = res["scale"]
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔（查不到业种的 {x['no_sector']} 笔）；B1 同时持有两只以上同业种的日子 "
                 f"{x['same_sector_days']} 天；SEC 在账户里挡掉的候选 {res['sec_blocked'].get(e, '—')} 个；"
                 + "；".join(f"{k} 挡「票 × 月」{_f(x[k]['blocked_pct'], '{:.1f}')}%、信号 {x[k]['signals_blocked']} 个、B1 实际成交 {x[k]['trades_blocked']} 笔"
                            for k in ("MXR", "IVH")))
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
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    G = inputs(W)
    sec = sector_map()
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps(scale(W, G, sec, b1), ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 / 业种表为空 → 三个账户都与 B1 逐项相同；② em_tick 对数 > 0、SEC 挡掉的候选 > 0（不看收益）。"""
    W = L2.load()
    G = inputs(W)
    sec = sector_map()
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {"J": {k: G["J"][k] & False for k in ("MXR", "IVH")}}
    same = {}
    for k, over in runs(W, "J", empty, {}).items():
        same[k] = all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys)
    n = {k: len(runs(W, "J", G, sec)[k]["em_tick"]) for k in ("MXR", "IVH")}
    L2.run(W, "J", sector_cap=sec)
    n["SEC"] = sector_blocked()
    print(json.dumps({"empty_same_as_b1": same, "counts_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 11 轮：MXR / IVH / SEC（选股：彩票型、同业种不重复）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
