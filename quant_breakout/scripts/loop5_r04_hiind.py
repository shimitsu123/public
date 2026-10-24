"""loop5_r04_hiind.py — 第五个研究循环（仓位结构）第 4 轮：按离 52 周高点的远近调仓位 H52 / 按业种动量调仓位 ISM
（2026-10-03 登记；先提交后只运行一次；家族「仓位·按信号」3 / 3、新家族「仓位·按业种」1 / 3）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」。循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - H52（离 52 周高点近的加、远的减）：信号日收盘 ÷ 250 日最高（C 的特征 hi52）在学习样本（同一折、全部 W2 信号）的最高三分之一 → 每只 34%（× 1.36）、
    最低三分之一 → 12.5%（× 0.5）、中间不变；算不出 → 不变。文献：George & Hwang（2004, J. Finance「The 52-week high and momentum investing」）——
    接近 52 周高点的股票之后更强（投资者以高点为锚、对好消息反应不足）；国际样本也成立（Liu, Liu & Ma 2011）。B1 的突破是 60 日箱体的突破，
    有的同时在 52 周高点、有的还在高点下方很远（反弹型）→ 这一项在 B1 的信号之间有差别。先验中等。
  - ISM（业种强的加、弱的减）：信号所在业种过去 12-1 个月的强弱（业种之间的百分位，C 的特征 sec）在学习样本的最高三分之一 → 34%、最低三分之一 → 12.5%。
    文献：Moskowitz & Grinblatt（1999, J. Finance「Do industries explain momentum?」）—— 业种动量比个股动量更稳。先验中等偏弱（日本的动量整体偏弱，Asness 2011）。
    以前：第四个循环 STR（业种过去的突破跑不赢核心 → 不买）是「挡」、看的是突破相对核心的成绩；这里是「调仓位」、看的是业种本身的涨跌。
做法（只改每只的仓位；其余 —— 买点、C、离场、核心、判断层 —— 全部同 B1；参数一次写定、S6 不适用；都不是事后组合、S7 不适用）：
  两个都是 kind = size_trade：每个年代 B1 会买的信号 → 倍数（1.36 / 1 / 0.5；三分位用那一折的学习样本 = 另外两个年代的研究面板）→ research_loop5.ticks_from → sizing_kw(1.36, tick_mult=…)。
S5（仓位版）：research_loop5.other_pools（W / Jx 里 B1 会买的信号，每笔超额 = 净收益 − O0 同期）× 倍数（那一折的三分位）→ research_loop5.s5_sizing。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：倍数在同一年代 B1 会买的信号之间随机打乱（research_loop5.permute_mult，种子 [20261005, 1, s]），400 次，严格大于最大值。
接线核对（登记前，不看候选的收益）：J 年代 ① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的信号数 > 0。
只描述（不参与判定）：倍数的分布、B1 实际成交的倍数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期（照实写，写在看结果之前）：加减各约三分之一 → 差小；H52 在 Z 可能变好（2005 年的突破多在高点）；第一关各约 8%、第二关约 15% → 「更好候选」各约 1%。
运行：python scripts/loop5_r04_hiind.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 ID [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r04_hiind.md / .json（第二关 loop5_r04_hiind_stage2_ID.md / .json）。非投资建议。
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

ROUND = 4
IDS = ("H52", "ISM")
FAMILY = {"H52": "仓位·按信号", "ISM": "仓位·按业种"}
KIND = {"H52": "size_trade", "ISM": "size_trade"}
FEAT = {"H52": "hi52", "ISM": "sec"}
POSTHOC = False
M_LO, M_HI = 0.5, 1.36
OUT = "loop5_r04_hiind"


# ───────────────────────── 纯函数（tests/test_loop5_r04.py） ─────────────────────────
def tertile_cuts(trains: list[pd.DataFrame], feat: str) -> tuple[float, float]:
    """学习样本（合起来）这一项的 1/3、2/3 分位（算不出 → NaN）。"""
    x = pd.concat([T[feat] for T in trains], ignore_index=True).to_numpy(float) if trains else np.array([])
    x = x[np.isfinite(x)]
    return (float(np.quantile(x, 1 / 3)), float(np.quantile(x, 2 / 3))) if len(x) else (np.nan, np.nan)


def high_good_mult(X: pd.DataFrame, feat: str, cuts: tuple[float, float]) -> np.ndarray:
    """这一项 ≥ 2/3 分位 → M_HI；≤ 1/3 分位 → M_LO；其余 / 算不出 → 1（数值越高越好）。"""
    v = X[feat].to_numpy(float)
    lo, hi = cuts
    m = np.ones(len(X))
    if np.isfinite(lo) and np.isfinite(hi):
        ok = np.isfinite(v)
        m[ok & (v >= hi)] = M_HI
        m[ok & (v <= lo) & ~(v >= hi)] = M_LO
    return m


# ───────────────────────── 输入 ─────────────────────────
def inputs(W: dict) -> dict:
    cuts = {k: {e: tertile_cuts([W["D"][x] for x in L2.ERAS if x != e], FEAT[k]) for e in L2.ERAS} for k in IDS}
    sig = {e: R5.b1_signals(W, e) for e in L2.ERAS}
    mult = {k: {e: high_good_mult(sig[e], FEAT[k], cuts[k][e]) for e in L2.ERAS} for k in IDS}
    return {"sig": sig, "cuts": cuts, "mult": mult}


def runs(W: dict, e: str, M: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {k: R2V.csz_kw(M["sig"][e], M["mult"][k][e], days) for k in IDS}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = pools[s]
        for k in IDS:
            out[k][s] = R5.s5_sizing(X["xs"].to_numpy(float), high_good_mult(X, FEAT[k], M["cuts"][k][fold]))
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
NAMES = {"H52": "离 52 周高点近的三分之一 34%、远的三分之一 12.5%", "ISM": "业种 12-1 个月最强的三分之一 34%、最弱的三分之一 12.5%"}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r04_hiind.py", "scripts/loop5_r02_volc.py", "scripts/loop5_r01_layer.py",
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
           "scale": scale(W, M, b1_trades), "cuts": M["cuts"], "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 4 轮：按离 52 周高点的远近 H52 / 按业种动量 ISM 调仓位（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r04_hiind.py 开头）", ""]
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
    L += ["", "规模（不参与判定）：" + "；".join(f"{k} 三分位 " + "、".join(f"{e} 折 {_f(c[0], '{:.3f}')} / {_f(c[1], '{:.3f}')}" for e, c in res["cuts"][k].items()) for k in IDS)]
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
    print(json.dumps({"scale": scale(W, M, b1), "cuts": M["cuts"]}, ensure_ascii=False))
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
    L = [f"# 第五个研究循环第 4 轮 第二关：{k} vs 400 次倍数在信号之间随机打乱（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
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
    ap = argparse.ArgumentParser(description="第五个研究循环第 4 轮：H52 / ISM（仓位：按离 52 周高点的远近 / 按业种动量）")
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
