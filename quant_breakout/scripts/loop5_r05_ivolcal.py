"""loop5_r05_ivolcal.py — 第五个研究循环（仓位结构）第 5 轮：按特质波动调仓位 IVL / 按季节调仓位 HAL
（2026-10-03 登记；先提交后只运行一次；新家族「仓位·特质波动」「仓位·日历」）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」。循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - IVL（特质波动低的加、高的减）：特质波动 = 60 日波动 × √(1 − 与日経 60 日相关²)（C 的特征 vol60、corr60 合成；扣掉跟大盘一起动的部分）；
    在学习样本（同一折、全部 W2 信号）的最低三分之一 → 每只 34%（× 1.36）、最高三分之一 → 12.5%（× 0.5）、中间不变；算不出 → 不变。
    文献：Ang, Hodrick, Xing & Zhang（2006, J. Finance；2009, JFE「High idiosyncratic volatility and low returns: International and further U.S. evidence」）——
    特质波动高的股票之后收益低，在包括日本的 23 个发达市场都成立。先验中等。
    以前：第三个循环第 11 轮的 IVH（特质波动高 → 挡）规模核对后没登记（碰不到 B1 的成交）；第 3 轮 BTS 看的是系统性风险（β），这里看的是特质风险，文献上是两个不同的异常。
  - HAL（季节）：信号日在 11〜4 月 → 每只 34%，5〜10 月 → 12.5%。文献：Bouman & Jacobsen（2002, AER「The Halloween indicator」）、Jacobsen & Zhang（2018）——
    37 个市场里 11〜4 月的收益明显高于 5〜10 月，日本是最明显的之一。以前只在核心上试过（2026-09-27 H1 / H2：5〜10 月核心 50%，没过）；没在个股层试过。
    先验中等偏弱：核心（纳指）也有同样的季节性 → 个股相对核心不一定有季节差。
做法（只改每只的仓位；其余 —— 买点、C、离场、核心、判断层 —— 全部同 B1；参数一次写定、S6 不适用；都不是事后组合、S7 不适用）：
  - IVL（kind = size_trade）：每个年代 B1 会买的信号 → 倍数（三分位用那一折的学习样本）→ ticks_from → sizing_kw(1.36, tick_mult=…)。
  - HAL（kind = size_time）：每日倍数（信号日的月份）→ fill_day → sizing_kw(1.36, day_mult=…)。
S5（仓位版）：research_loop5.other_pools（W / Jx 里 B1 会买的信号，每笔超额 = 净收益 − O0 同期）× 倍数（IVL = 那一折的三分位；HAL = 信号日的倍数）→ research_loop5.s5_sizing。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：IVL = 倍数在同一年代 B1 会买的信号之间随机打乱（种子 [20261005, 1, s]）；HAL = 每日倍数循环平移（种子 [20261005, s]；平移 = 换一个季节的相位）；400 次。
接线核对（登记前，不看候选的收益）：J 年代 ① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的信号数 / 天数 > 0。
只描述（不参与判定）：倍数的分布、B1 实际成交的倍数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期（照实写，写在看结果之前）：IVL 加减各约三分之一 → 差小；HAL 一半时间加、一半时间减 → Z 的 2005 年下半年的行情会被减（5〜10 月）→ Z 可能变差；
  第一关各约 8%、第二关约 15% → 「更好候选」各约 1%。
运行：python scripts/loop5_r05_ivolcal.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 ID [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r05_ivolcal.md / .json（第二关 loop5_r05_ivolcal_stage2_ID.md / .json）。非投资建议。
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
import loop5_r04_hiind as R4H                                                # noqa: E402
import research_loop5 as R5                                                  # noqa: E402

ROUND = 5
IDS = ("IVL", "HAL")
FAMILY = {"IVL": "仓位·特质波动", "HAL": "仓位·日历"}
KIND = {"IVL": "size_trade", "HAL": "size_time"}
POSTHOC = False
M_LO, M_HI = 0.5, 1.36
WINTER = (11, 12, 1, 2, 3, 4)
OUT = "loop5_r05_ivolcal"


# ───────────────────────── 纯函数（tests/test_loop5_r05.py） ─────────────────────────
def with_ivol(X: pd.DataFrame) -> pd.DataFrame:
    """加一列 ivol = vol60 × √(1 − corr60²)（相关的平方截在 [0, 1]）；其余列不动。"""
    v, c = X["vol60"].to_numpy(float), X["corr60"].to_numpy(float)
    with np.errstate(invalid="ignore"):
        iv = v * np.sqrt(np.clip(1.0 - c ** 2, 0.0, 1.0))
    return X.assign(ivol=iv)


def low_good_mult(X: pd.DataFrame, feat: str, cuts: tuple[float, float]) -> np.ndarray:
    """这一项 ≤ 1/3 分位 → M_HI；≥ 2/3 分位 → M_LO；其余 / 算不出 → 1（数值越低越好）。"""
    v = X[feat].to_numpy(float)
    lo, hi = cuts
    m = np.ones(len(X))
    if np.isfinite(lo) and np.isfinite(hi):
        ok = np.isfinite(v)
        m[ok & (v <= lo)] = M_HI
        m[ok & (v >= hi) & ~(v <= lo)] = M_LO
    return m


def hal_mult(days) -> pd.Series:
    """信号日在 11〜4 月 → M_HI；5〜10 月 → M_LO。"""
    d = pd.DatetimeIndex(days)
    return pd.Series(np.where(np.isin(d.month, WINTER), M_HI, M_LO), index=d)


# ───────────────────────── 输入 ─────────────────────────
def inputs(W: dict) -> dict:
    days = R1.union_days(W)
    cuts = {e: R4H.tertile_cuts([with_ivol(W["D"][x]) for x in L2.ERAS if x != e], "ivol") for e in L2.ERAS}
    sig = {e: with_ivol(R5.b1_signals(W, e)) for e in L2.ERAS}
    return {"days": days, "sig": sig, "cuts": cuts, "IVL": {e: low_good_mult(sig[e], "ivol", cuts[e]) for e in L2.ERAS}, "HAL": hal_mult(days)}


def runs(W: dict, e: str, M: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {"IVL": R2V.csz_kw(M["sig"][e], M["IVL"][e], days), "HAL": R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["HAL"], days))}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = with_ivol(pools[s])
        out["IVL"][s] = R5.s5_sizing(X["xs"].to_numpy(float), low_good_mult(X, "ivol", M["cuts"][fold]))
        out["HAL"][s] = R5.s5_sizing(X["xs"].to_numpy(float), R1.at_dates(M["HAL"], X["date"]))
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
        S, m = M["sig"][e], M["IVL"][e]
        key = {(str(t), pd.Timestamp(d).normalize()): x for t, d, x in zip(S["ticker"], pd.to_datetime(S["date"]), m)}
        ti = np.array([key.get((str(t), pd.Timestamp(d).normalize()), np.nan) for t, d in zip(tr["ticker"], sig)]) if len(sig) else np.array([])
        th = R1.at_dates(M["HAL"], sig) if len(sig) else np.array([])
        mh = R1.at_dates(M["HAL"], win)
        out[e] = {"b1_trades": int(len(tr)), "signals": int(len(S)),
                  "IVL": {"up": int((m > 1).sum()), "down": int((m < 1).sum()), "trades_matched": int(np.isfinite(ti).sum()),
                          "trades_up": int((ti > 1).sum()), "trades_down": int((ti < 1).sum())},
                  "HAL": {"up_days": round(float((mh > 1).mean() * 100), 1), "trades_up": int((th > 1).sum()), "trades_down": int((th < 1).sum())}}
    return out


# ───────────────────────── 运行 ─────────────────────────
_acct = R1._acct
_f = R1._f
NAMES = {"IVL": "特质波动最低三分之一 34%、最高三分之一 12.5%", "HAL": "11〜4 月 34%、5〜10 月 12.5%"}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r05_ivolcal.py", "scripts/loop5_r04_hiind.py", "scripts/loop5_r02_volc.py",
                                 "scripts/loop5_r01_layer.py", "scripts/research_loop5.py", "scripts/combo_all_common.py", "scripts/candle_portfolio.py",
                                 "scripts/loop2_common.py", "scripts/loop_common.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
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
           "scale": scale(W, M, b1_trades), "cuts": M["cuts"], "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 5 轮：按特质波动 IVL / 按季节 HAL 调仓位（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r05_ivolcal.py 开头）", ""]
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
    L += ["", "规模（不参与判定）：IVL 三分位 " + "、".join(f"{e} 折 {_f(c[0], '{:.4f}')} / {_f(c[1], '{:.4f}')}" for e, c in res["cuts"].items())]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；IVL 信号加 {x['IVL']['up']} / 减 {x['IVL']['down']}、成交（对上 {x['IVL']['trades_matched']} 笔）"
                 f"加 {x['IVL']['trades_up']} / 减 {x['IVL']['trades_down']}；HAL 加大的天 {x['HAL']['up_days']}%、成交加 {x['HAL']['trades_up']} / 减 {x['HAL']['trades_down']}")
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
    print(json.dumps({"scale": scale(W, M, b1), "cuts": M["cuts"]}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的信号数 / 天数 > 0（不看收益）。"""
    W = L2.load()
    M = inputs(W)
    days = pd.DatetimeIndex(W["ctx"]["J"]["days"])
    rb = L2.run(W, "J")
    S = M["sig"]["J"]
    r1 = L2.run(W, "J", **R2V.csz_kw(S, np.ones(len(S)), days))
    r2 = L2.run(W, "J", **R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(pd.Series(1.0, index=M["days"]), days)))
    same = {"IVL": all(rb.get(x) == r1.get(x) for x in R5.WIRING_KEYS), "HAL": all(rb.get(x) == r2.get(x) for x in R5.WIRING_KEYS)}
    n = {"IVL": int((M["IVL"]["J"] != 1).sum()), "HAL": int((R1.at_dates(M["HAL"], days) != 1).sum())}
    print(json.dumps({"ones_same_as_b1": same, "nonunit_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, k, base, ks = _G["W"], _G["M"], _G["k"], _G["base"], _G["ks"]
    try:
        tot = 0.0
        for e in L2.ERAS:
            days = W["ctx"][e]["days"]
            if k == "HAL":
                kw = R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(R5.shift_mult(M["HAL"], ks[int(seed)]), days))
            else:
                kw = R2V.csz_kw(M["sig"][e], R5.permute_mult(M["IVL"][e], int(seed)), days)
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
    ks = R5.size_shift_ks(len(M["days"])) if k == "HAL" else None
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
    shape = "每日倍数循环平移" if k == "HAL" else "倍数在信号之间随机打乱"
    L = [f"# 第五个研究循环第 5 轮 第二关：{k} vs 400 次{shape}（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
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
    ap = argparse.ArgumentParser(description="第五个研究循环第 5 轮：IVL / HAL（仓位：按特质波动 / 按季节）")
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
