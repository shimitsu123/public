"""loop5_r06_valrev.py — 第五个研究循环（仓位结构）第 6 轮：按股息率（价值）调仓位 DYV / 按 3 年涨跌（长期反转）调仓位 LTR
（2026-10-03 登记；先提交后只运行一次；新家族「仓位·价值」「仓位·长期反转」）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」。循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - DYV（股息率高的加、低的减）：日本是价值效应最明显的市场之一（Fama & French 1998 / 2012；Asness 2011「Momentum in Japan」—— 日本动量弱、价值强，
    动量与价值搭配在日本有效：Asness, Moskowitz & Pedersen 2013）。突破买入是动量类 → 往「便宜」的那一边倾斜，理论上能对冲动量弱的部分。先验中等。
  - LTR（3 年跌得多的加、涨得多的减）：长期反转（De Bondt & Thaler 1985；Chopra, Lakonishok & Ritter 1992；日本也有报告）—— 过去 3 年的输家之后表现更好；
    输家的突破 = 走出低谷的开始。先验中等偏弱。
    照实写：第 4 轮 ISM 的结果（Z 2005 的赢家多在过去 12 个月偏弱的业种）已经看过；LTR 用的是个股 3 年（跳过最近 1 个月）的涨跌，是另一个时间尺度与层级，但想法有相通之处。
  - 照实写（以前看过的）：「质的飞跃」循环第 1 轮（2026-09-27，只用 2006-10 以后）的逐笔探索里，股息率是唯一两个年代方向一致的新特征
    （最高 1/5 比最低 1/5 每笔多 +0.4〜1.5 pp），3 年涨跌在两个年代方向相反；第 2 轮「股息率 + 3 年跌」每月选股逐笔更好、组合更差；
    第 11 轮按信号质量决定买多少（股息率前一半等买满、其余减半或 1/4）在 E / J 是噪音（E 0.267〜0.315 vs 0.298、J 0.388〜0.417 vs 0.389）。
    → E / J 对这两个特征不是没看过的数据，只有 Z（2001〜2006）没用过；这里的做法（过去 730 天的三分位、两头 1.36 / 0.5）不是那几次的原样重做。
  - 三分位不用「另外两个年代的学习样本」而用「过去 730 个日历日里日経225 的 W2 信号（≥ 30 个）」：股息率的水平在三个年代差别很大
    （研究面板的三分位 Z 约 1.0 / 1.3%、E 1.3 / 2.3%、J 2.2 / 3.3%）→ 用别的年代切会让整个年代一起加或一起减，变成「年代」而不是「便宜 / 贵」；
    3 年涨跌也一样用最近的分布。这是登记前按水平（不看收益）定的。
做法（只改每只的仓位；其余 —— 买点、C、离场、核心、判断层 —— 全部同 B1；参数一次写定、S6 不适用；都不是事后组合、S7 不适用）：
  两个都是 kind = size_trade：每个信号与「信号日之前 730 个日历日里日経225 全部 W2 信号（研究面板，三个年代合起来）」的 1/3、2/3 分位比 →
  DYV：股息率 dy ≥ 2/3 分位 → 每只 34%、≤ 1/3 分位 → 12.5%；LTR：3 年涨跌 r3y ≤ 1/3 分位 → 34%、≥ 2/3 分位 → 12.5%；过去的信号不够 30 个或算不出 → 不变。
  → research_loop5.ticks_from → sizing_kw(1.36, tick_mult=…)。
S5（仓位版）：research_loop5.other_pools（W / Jx 里 B1 会买的信号，每笔超额 = 净收益 − O0 同期）× 倍数（同样与日経225 过去 730 天的信号比）→ research_loop5.s5_sizing。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：倍数在同一年代 B1 会买的信号之间随机打乱（research_loop5.permute_mult，种子 [20261005, 1, s]），400 次，严格大于最大值。
接线核对（登记前，不看候选的收益）：J 年代 ① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的信号数 > 0。
只描述（不参与判定）：倍数的分布、B1 实际成交的倍数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期（照实写，写在看结果之前）：加减各约三分之一 → 差小；第一关各约 8%、第二关约 15% → 「更好候选」各约 1%。
运行：python scripts/loop5_r06_valrev.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 ID [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r06_valrev.md / .json（第二关 loop5_r06_valrev_stage2_ID.md / .json）。非投资建议。
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
import loop5_r01_layer as R1                                                 # noqa: E402
import loop5_r02_volc as R2V                                                 # noqa: E402
import research_loop5 as R5                                                  # noqa: E402

ROUND = 6
IDS = ("DYV", "LTR")
FAMILY = {"DYV": "仓位·价值", "LTR": "仓位·长期反转"}
KIND = {"DYV": "size_trade", "LTR": "size_trade"}
FEAT = {"DYV": "dy", "LTR": "r3y"}
HIGH_GOOD = {"DYV": True, "LTR": False}
POSTHOC = False
M_LO, M_HI = 0.5, 1.36
PAST_DAYS, PAST_MIN = 730, 30
OUT = "loop5_r06_valrev"


# ───────────────────────── 纯函数（tests/test_loop5_r06.py） ─────────────────────────
def past_cuts(ref_dates, ref_vals, dates) -> np.ndarray:
    """每个日期 d：参考信号里日期在 [d − PAST_DAYS 天, d) 的值（≥ PAST_MIN 个）的 1/3、2/3 分位 → (n, 2)；不够 → NaN。"""
    rd = pd.to_datetime(pd.Series(ref_dates)).dt.normalize().to_numpy()
    rv = np.asarray(ref_vals, float)
    ok = np.isfinite(rv)
    rd, rv = rd[ok], rv[ok]
    o = np.argsort(rd, kind="stable")
    rd, rv = rd[o], rv[o]
    out = np.full((len(dates), 2), np.nan)
    for i, d in enumerate(pd.to_datetime(pd.Series(dates)).dt.normalize()):
        lo = np.searchsorted(rd, (d - pd.Timedelta(days=PAST_DAYS)).to_datetime64(), side="left")
        hi = np.searchsorted(rd, d.to_datetime64(), side="left")
        if hi - lo >= PAST_MIN:
            v = rv[lo:hi]
            out[i] = (np.quantile(v, 1 / 3), np.quantile(v, 2 / 3))
    return out


def rank_mult(vals, cuts: np.ndarray, high_good: bool) -> np.ndarray:
    """每个信号：与自己的 (1/3, 2/3) 分位比 → 好的一头 M_HI、坏的一头 M_LO、中间 / 算不出 1。"""
    v = np.asarray(vals, float)
    lo, hi = cuts[:, 0], cuts[:, 1]
    ok = np.isfinite(v) & np.isfinite(lo) & np.isfinite(hi)
    m = np.ones(len(v))
    top, bot = ok & (v >= hi), ok & (v <= lo)
    if high_good:
        m[top] = M_HI
        m[bot & ~top] = M_LO
    else:
        m[bot] = M_HI
        m[top & ~bot] = M_LO
    return m


# ───────────────────────── 输入 ─────────────────────────
def ref_panel(W: dict) -> pd.DataFrame:
    """日経225 三个年代全部 W2 信号（研究面板）合起来；同一只票同一个信号日只留一笔。"""
    P = pd.concat([W["D"][e] for e in L2.ERAS], ignore_index=True)
    return P.assign(_d=pd.to_datetime(P["date"]).dt.normalize()).drop_duplicates(["ticker", "_d"], keep="first").drop(columns="_d").reset_index(drop=True)


def mult_for(X: pd.DataFrame, ref: pd.DataFrame, k: str) -> np.ndarray:
    f = FEAT[k]
    return rank_mult(X[f].to_numpy(float), past_cuts(ref["date"], ref[f].to_numpy(float), X["date"]), HIGH_GOOD[k])


def inputs(W: dict) -> dict:
    ref = ref_panel(W)
    sig = {e: R5.b1_signals(W, e) for e in L2.ERAS}
    return {"ref": ref, "sig": sig, "mult": {k: {e: mult_for(sig[e], ref, k) for e in L2.ERAS} for k in IDS}}


def runs(W: dict, e: str, M: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {k: R2V.csz_kw(M["sig"][e], M["mult"][k][e], days) for k in IDS}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s in ("W", "Jx"):
        X = pools[s]
        for k in IDS:
            out[k][s] = R5.s5_sizing(X["xs"].to_numpy(float), mult_for(X, M["ref"], k))
    return out


# ───────────────────────── 规模（只数个数） ─────────────────────────
def scale(W: dict, M: dict, b1_trades: dict) -> dict:
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])] if len(tr) else []
        S = M["sig"][e]
        row = {"b1_trades": int(len(tr)), "signals": int(len(S))}
        for k in IDS:
            m = M["mult"][k][e]
            key = {(str(t), pd.Timestamp(d).normalize()): x for t, d, x in zip(S["ticker"], pd.to_datetime(S["date"]), m)}
            tm = np.array([key.get((str(t), pd.Timestamp(d).normalize()), np.nan) for t, d in zip(tr["ticker"], sig)]) if len(sig) else np.array([])
            row[k] = {"up": int((m > 1).sum()), "down": int((m < 1).sum()), "trades_matched": int(np.isfinite(tm).sum()),
                      "trades_up": int((tm > 1).sum()), "trades_down": int((tm < 1).sum())}
        out[e] = row
    return out


# ───────────────────────── 运行 ─────────────────────────
_acct = R1._acct
_f = R1._f
NAMES = {"DYV": "股息率高的三分之一 34%、低的三分之一 12.5%", "LTR": "3 年跌得多的三分之一 34%、涨得多的三分之一 12.5%"}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r06_valrev.py", "scripts/loop5_r02_volc.py", "scripts/loop5_r01_layer.py",
                                 "scripts/research_loop5.py", "scripts/combo_all_common.py", "scripts/candle_portfolio.py", "scripts/loop2_common.py",
                                 "scripts/loop_common.py", "qbreak/unified.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


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


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 6 轮：按股息率 DYV / 按 3 年涨跌 LTR 调仓位（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r06_valrev.py 开头）", ""]
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
    L += ["", "规模（不参与判定）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；" + "；".join(
            f"{k} 信号加 {x[k]['up']} / 减 {x[k]['down']}、成交（对上 {x[k]['trades_matched']} 笔）加 {x[k]['trades_up']} / 减 {x[k]['trades_down']}" for k in IDS))
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
    print(json.dumps({"scale": scale(W, M, b1), "ref_signals": int(len(M["ref"]))}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的信号数 > 0（不看收益）。"""
    W = L2.load()
    M = inputs(W)
    days = pd.DatetimeIndex(W["ctx"]["J"]["days"])
    rb = L2.run(W, "J")
    S = M["sig"]["J"]
    r1 = L2.run(W, "J", **R2V.csz_kw(S, np.ones(len(S)), days))
    same = all(rb.get(x) == r1.get(x) for x in R5.WIRING_KEYS)
    n = {k: int((M["mult"][k]["J"] != 1).sum()) for k in IDS}
    print(json.dumps({"ones_same_as_b1": same, "nonunit_J": n}, ensure_ascii=False))
    return 0 if same and all(v > 0 for v in n.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, k, base = _G["W"], _G["M"], _G["k"], _G["base"]
    try:
        tot = 0.0
        for e in L2.ERAS:
            kw = R2V.csz_kw(M["sig"][e], R5.permute_mult(M["mult"][k][e], int(seed)), W["ctx"][e]["days"])
            c = L2.run(W, e, **kw)["calmar"]
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
    _G.update({"W": W, "M": M, "k": k, "base": base})
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
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第五个研究循环第 6 轮 第二关：{k} vs 400 次倍数在信号之间随机打乱（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
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
    ap = argparse.ArgumentParser(description="第五个研究循环第 6 轮：DYV / LTR（仓位：按股息率 / 按 3 年涨跌）")
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
