"""loop5_r01_layer.py — 第五个研究循环（仓位结构）第 1 轮：个股层与核心之间按日期 / 状态切分仓位 —— CSH / SMO / RSM
（2026-10-03 登记；先提交后只运行一次；新家族「仓位·层间切分」「仓位·策略动量」）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」。循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - 第四个循环的诊断（只描述）：个股层的贡献（B1 − O0，O0 = 不开日本个股）Calmar Z +0.603 / E +0.134 / J +0.014 —— 核心（纳指 × 日元；美股熊拿现金）
    弱的年代个股层最值钱、强的年代几乎没有贡献。加大个股仓位对账户的一阶效果 = 加的那部分 ×（个股 − 同期核心）→ 应在「个股比核心好」时加、「比核心差」时减。
  - 以前「全部加大」在 2006〜2026 吃亏（2026-09-30 自由分配：随机仓位的中位数 E / J 都低于现行；2026-09-28 探索 P0 全部加码 J 更差）→ 这一轮三个做法的倍数都只看日期，
    而且都有「不加」或「减」的时候。
  - CSH（核心拿现金时加大）：美股熊（T0 判熊）→ Q1H 的核心拿现金，个股的机会成本 = 0 → 那段时间的日本个股每只 34%（× 1.36），其余不变。
    先验：机会成本的算术（强）；但 B1 的日本个股全部在日経 200 日线上买，美股熊而日経牛的日子可能很少（规模核对只数个数）。
  - SMO（突破策略的动量）：日経225 三个年代全部 W2 信号的假想单笔（研究面板 D，X6 离场的净收益）里，离场后已过 2 个交易日、离场在最近 252 个交易日内的 ≥ 10 笔，
    每笔超额（净收益 − 同期 1545 合成 = 纳指 100 × 日元）平均 > 0 → 每只 34%（× 1.36）；≤ 0 → 12.5%（× 0.5）；不够 10 笔 → 不变。
    文献：因子动量（Ehsani & Linnainmaa 2022, J. Finance；Gupta & Kelly 2019）—— 因子过去 12 个月的收益预测之后的收益；这里把「W2 突破相对核心」当作一个因子。先验中等。
    以前没做过「策略层面」的仓位：第四个循环 CTR / STR 是个股 / 业种层面的挡；2026-09 的影子账户近期表现只是探索、没登记。
  - RSM（日本对美国的相对动量）：日経225 过去 252 个交易日的涨幅 > 1545 合成的同期涨幅 → 每只 34%；否则 12.5%；算不出 → 不变。
    文献：国家指数的动量（Richards 1997；Asness, Moskowitz & Pedersen 2013）、双动量（Antonacci 2014）。先验中等偏弱（两个市场的强弱常反转）。
做法（三个都只改每只的仓位、倍数只看日期 → kind = size_time）：每日倍数 m（信号日收盘时已知）→ research_loop5.fill_day 对到成交日 →
  research_loop5.sizing_kw(1.36, …)（position_pct 34%、全部新仓倍数 ÷ 1.36、再 × m）；其余 —— 买点、C、离场、核心、判断层 —— 全部同 B1。
  美国的状态（T0 熊）只用 JP 信号日之前的日历日已经收盘的美国交易日（美国日期 + 1 天起才可用）；1545 合成是东证的价格，用当天收盘。
  参数（1.36 / 0.5、252 天、10 笔、2 天）一次写定（S6 不适用）；不是事后组合（S7 不适用）。
S5（仓位版）：research_loop5.other_pools（W / Jx 里 B1 会买的信号，每笔超额 = 净收益 − O0 同期）× 那个信号日的 m → research_loop5.s5_sizing。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：kind = size_time —— 三个年代交易日合起来的每日倍数序列整体循环平移 k（research_loop5.size_shift_ks，
  种子 [20261005, s]，s = 0〜399；三个年代同一个 k）；候选的 Calmar 差合计要严格大于 400 次里的最大值。
接线核对（登记前，不看候选的收益）：J 年代 ① m 全为 1（同一条代码路径）→ 与 B1 逐项相同；② 每个做法 m ≠ 1 的天数 > 0。
只描述（不参与判定）：各年代 m = 1.36 / 0.5 的天数比例、B1 实际成交落在各状态的笔数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期（照实写，写在看结果之前）：CSH 碰到的成交很少 → 差很小；SMO / RSM 在日本强的年代（Z）加、纳指强的年代（J）减 → Z 变好、J 小变、E 不确定；
  第一关各约 10%、第二关各约 15% → 「更好候选」各约 1.5%。
运行：python scripts/loop5_r01_layer.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 ID [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r01_layer.md / .json（第二关 loop5_r01_layer_stage2_ID.md / .json）。非投资建议。
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
import research_loop5 as R5                                                  # noqa: E402

ROUND = 1
IDS = ("CSH", "SMO", "RSM")
FAMILY = {"CSH": "仓位·层间切分", "SMO": "仓位·策略动量", "RSM": "仓位·层间切分"}
POSTHOC = False
KIND = "size_time"
M_UP, M_DOWN = 1.36, 0.5
LOOKBACK, MIN_N, KNOWN_LAG = 252, 10, 2
CORE = "1545.T"
OUT = "loop5_r01_layer"


# ───────────────────────── 纯函数（tests/test_loop5_r01.py） ─────────────────────────
def us_known(s_us: pd.Series, jp_days) -> pd.Series:
    """美国日期的序列 → JP 交易日 t 收盘时已知的值（只用日历日早于 t 的美国交易日；之前没有 → NaN）。"""
    jp = pd.DatetimeIndex(jp_days)
    s = s_us.copy()
    s.index = pd.DatetimeIndex(s.index).normalize() + pd.Timedelta(days=1)
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(s.index.union(jp)).ffill().reindex(jp)


def csh_mult(bear_known: pd.Series) -> pd.Series:
    """美股熊（核心拿现金）→ M_UP；牛或算不出 → 1。"""
    b = pd.to_numeric(bear_known, errors="coerce").fillna(0.0).to_numpy(float)
    return pd.Series(np.where(b > 0.5, M_UP, 1.0), index=bear_known.index)


def smo_state(exit_pos, xs, n_days: int) -> tuple[np.ndarray, np.ndarray]:
    """每个交易日位置 i：可用位置 a = 离场位置 + KNOWN_LAG 满足 i − LOOKBACK < a ≤ i 的单笔 → (平均超额, 笔数)；超额是 NaN 的不用。"""
    ep, x = np.asarray(exit_pos, float), np.asarray(xs, float)
    ok = np.isfinite(ep) & np.isfinite(x) & (ep >= 0)
    a, v = ep[ok] + KNOWN_LAG, x[ok]
    o = np.argsort(a, kind="stable")
    a, v = a[o], v[o]
    cs = np.concatenate([[0.0], np.cumsum(v)])
    i = np.arange(int(n_days), dtype=float)
    hi = np.searchsorted(a, i, side="right")
    lo = np.searchsorted(a, i - LOOKBACK, side="right")
    cnt = (hi - lo).astype(int)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(cnt > 0, (cs[hi] - cs[lo]) / np.maximum(cnt, 1), np.nan)
    return mean, cnt


def smo_mult(mean, cnt, index) -> pd.Series:
    """≥ MIN_N 笔：平均超额 > 0 → M_UP、≤ 0 → M_DOWN；不够 → 1。"""
    mean, cnt = np.asarray(mean, float), np.asarray(cnt, int)
    m = np.where(cnt >= MIN_N, np.where(mean > 0, M_UP, M_DOWN), 1.0)
    return pd.Series(m, index=index)


def rsm_mult(jp_close: pd.Series, us_close: pd.Series, days) -> pd.Series:
    """日経过去 LOOKBACK 个交易日的涨幅 > 1545 合成同期涨幅 → M_UP；否则 M_DOWN；算不出 → 1。"""
    d = pd.DatetimeIndex(days)
    jp_close = jp_close[~jp_close.index.duplicated(keep="last")]
    us_close = us_close[~us_close.index.duplicated(keep="last")]
    a = jp_close.astype(float).reindex(d.union(jp_close.index)).ffill().reindex(d)
    b = us_close.astype(float).reindex(d.union(us_close.index)).ffill().reindex(d)
    ra, rb = a / a.shift(LOOKBACK) - 1, b / b.shift(LOOKBACK) - 1
    ok = (ra.notna() & rb.notna()).to_numpy()
    return pd.Series(np.where(ok, np.where((ra > rb).to_numpy(), M_UP, M_DOWN), 1.0), index=d)


# ───────────────────────── 输入 ─────────────────────────
def union_days(W: dict) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(sorted(set().union(*[set(pd.DatetimeIndex(W["ctx"][e]["days"])) for e in L2.ERAS])))


def panel_xs(W: dict, days) -> pd.DataFrame:
    """日経225 三个年代的研究面板（全部 W2 信号的假想单笔）合起来（同一只票同一个信号日只留一笔）+ 离场日 / 每笔超额（vs 1545 合成）。"""
    import loop4_r04_xsmodel as XS
    P = pd.concat([W["D"][e] for e in L2.ERAS], ignore_index=True)
    P = P.assign(_d=pd.to_datetime(P["date"]).dt.normalize()).drop_duplicates(["ticker", "_d"], keep="first").drop(columns="_d")
    return XS.with_xs(P.reset_index(drop=True), days, W["assets"][CORE]["Close"].astype(float))


def inputs(W: dict) -> dict:
    """{"days": 三个年代交易日合起来, CSH / SMO / RSM: 每日倍数（信号日收盘时已知）, "smo_n": SMO 窗口里的笔数}。"""
    days = union_days(W)
    bear = us_known(W["bear"]["US"].astype(float), days)
    P = panel_xs(W, days)
    ep = days.searchsorted(pd.to_datetime(P["exit"]).to_numpy())
    mean, cnt = smo_state(ep, P["xs"].to_numpy(float), len(days))
    return {"days": days, "CSH": csh_mult(bear), "SMO": smo_mult(mean, cnt, days),
            "RSM": rsm_mult(W["inp"]["n225"]["Close"], W["assets"][CORE]["Close"], days), "smo_n": pd.Series(cnt, index=days)}


def at_dates(m: pd.Series, dates) -> np.ndarray:
    """每日倍数 → 那些信号日的值（没有 → 1）。"""
    d = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates)).dt.normalize())
    s = m.reindex(m.index.union(d.unique())).ffill()                         # 同一天可能有几个信号 → 先用不重复的日子对齐
    return s.reindex(d).fillna(1.0).to_numpy(float)


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s, X in pools.items():
        for k in IDS:
            out[k][s] = R5.s5_sizing(X["xs"].to_numpy(float), at_dates(M[k], X["date"]))
    return out


# ───────────────────────── 规模（只数个数） ─────────────────────────
def scale(W: dict, M: dict, b1_trades: dict) -> dict:
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        win = days[(days >= pd.Timestamp(a)) & ((days < pd.Timestamp(b)) if b else True)]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])] if len(tr) else []
        row = {"days": int(len(win)), "b1_trades": int(len(tr))}
        for k in IDS:
            mw, mt = at_dates(M[k], win), at_dates(M[k], sig) if len(sig) else np.array([])
            row[k] = {"up_days": round(float((mw > 1).mean() * 100), 1), "down_days": round(float((mw < 1).mean() * 100), 1),
                      "trades_up": int((mt > 1).sum()), "trades_down": int((mt < 1).sum())}
        out[e] = row
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r01_layer.py", "scripts/research_loop5.py", "scripts/loop4_r04_xsmodel.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def runs(W: dict, e: str, M: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {k: R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M[k], days)) for k in IDS}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    M = inputs(W)
    print(f"倍数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R5.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, kw in runs(W, e, M).items():
            rc = L2.run(W, e, **kw)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, M)
    s1 = {k: R5.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 5, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "scale": scale(W, M, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


NAMES = {"CSH": "核心拿现金（美股熊）时每只 34%", "SMO": "突破策略最近 12 个月跑赢核心 → 34%、跑输 → 12.5%",
         "RSM": "日経最近 12 个月跑赢纳指（日元）→ 34%、否则 12.5%"}


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 1 轮：个股层与核心按状态切分 CSH / SMO / RSM（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r01_layer.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{NAMES[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R5.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W dmean {_f(o['W']['dmean'], '{:+.3f}')} pp / dwin {_f(o['W']['dwin'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dmean'], '{:+.3f}')} / {_f(o['Jx']['dwin'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | " + " | ".join(f"{k}（Calmar 差）" for k in IDS) + " | 个股笔数 B1 → " + " / ".join(IDS) + " |",
          "|---|---|" + "---|" * len(IDS) + "---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS)
                 + f" | {t['B1']} → " + " / ".join(str(t[k]) for k in IDS) + " |")
    L += ["", "规模（不参与判定；m = 每只仓位的倍数，1.36 = 34%、0.5 = 12.5%）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：窗口 {x['days']} 个交易日、B1 的日本个股 {x['b1_trades']} 笔；" + "；".join(
            f"{k} 加大的天 {x[k]['up_days']}% / 减小的天 {x[k]['down_days']}%、成交落在加大 {x[k]['trades_up']} 笔 / 减小 {x[k]['trades_down']} 笔" for k in IDS))
    for k in IDS:
        for s in ("W", "Jx"):
            z = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：B1 会买的信号 {z['n']} 个（每笔超额平均 {_f(z.get('mean_x'), '{:+.2f}')} pp、跑赢核心 {_f(z.get('beat'), '{:.1f}')}%、"
                     f"倍数平均 {_f(z.get('m_mean'), '{:.3f}')}）→ dmean {_f(z['dmean'], '{:+.3f}')} pp、dwin {_f(z['dwin'], '{:+.2f}')} pp")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R5.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    M = inputs(W)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    sm = M["smo_n"]
    print(json.dumps({"scale": scale(W, M, b1), "smo_n_median": float(sm[sm > 0].median()) if (sm > 0).any() else None,
                      "first_nonunit": {k: (str(M[k].index[(M[k] != 1).to_numpy()][0].date()) if (M[k] != 1).any() else None) for k in IDS}},
                     ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① m 全为 1（同一条代码路径）→ 与 B1 逐项相同；② 每个做法 m ≠ 1 的天数 > 0（不看收益）。"""
    W = L2.load()
    M = inputs(W)
    days = pd.DatetimeIndex(W["ctx"]["J"]["days"])
    rb = L2.run(W, "J")
    rc = L2.run(W, "J", **R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(pd.Series(1.0, index=M["days"]), days)))
    same = all(rb.get(x) == rc.get(x) for x in R5.WIRING_KEYS)
    n = {k: int((at_dates(M[k], days) != 1).sum()) for k in IDS}
    print(json.dumps({"ones_same_as_b1": same, "days_m_not_1_J": n}, ensure_ascii=False))
    return 0 if same and all(v > 0 for v in n.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, k, base, ks = _G["W"], _G["M"], _G["k"], _G["base"], _G["ks"]
    try:
        m = R5.shift_mult(M[k], ks[int(seed)])
        tot = 0.0
        for e in L2.ERAS:
            c = L2.run(W, e, **R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(m, W["ctx"][e]["days"])))["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(k: str, workers: int) -> int:
    import multiprocessing as mp
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = L2.load()
    M = inputs(W)
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    cand = {e: L2.run(W, e, **runs(W, e, M)[k])["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    ks = R5.size_shift_ks(len(M["days"]))
    _G.update({"W": W, "M": M, "k": k, "base": base, "ks": ks})
    seeds = list(range(R5.PLACEBO_N))
    vals = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
            if (i + 1) % 40 == 0:
                print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    s2 = R5.stage2(stat, vals)
    vd = R5.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 5, "round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "ks": ks, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第五个研究循环第 1 轮 第二关：{k} vs 400 次每日倍数循环平移（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B1 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第五个研究循环第 1 轮：CSH / SMO / RSM（仓位：个股层与核心按状态切分）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    g.add_argument("--stage2", choices=IDS, help="第二关（第一关全过才做）")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    if a.stage2:
        return stage_two(a.stage2, a.workers)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
