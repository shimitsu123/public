"""loop5_r10_regime.py — 第五个研究循环（仓位结构）第 10 轮：去掉量化状态层（日経跌破 200 日线 / 离一年高点 −12% / 波动 > 35% → 新仓 0 倍；其余不稳 → 0.75 倍）RGX
（2026-10-03 登记；先提交后只运行一次；新家族「仓位·状态层」；kind = struct）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」→ ㊹ ②「继续第五个循环 并找到接下来研究成功率最大的方向 没有时间限制 一直找到比现在算法更好的」。
循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - B1 的新仓倍数 = 量化状态层（qbreak/regime.quant_regime_series：risk_off 0 / neutral 0.75 / risk_on 1）× 宏观层 × 板块倾斜 × 判断层市场层。
    量化状态层是「什么时候放多少（按市场状态）」的一部分 → 在第五个循环的题目范围里（不改买哪只、不改核心、不改离场）。
  - 以前的证据（照实写，都看过）：2026-09-26「各层怎么搭配」的事后描述 —— 日経225 的独立交易里，量化状态层挡掉的突破两半都比 1 倍时好
    （46.0% / +1.62% vs 32.8% / −0.31%；50.9% / +0.97% vs 42.7% / +0.67%），消融「去掉这一层」S0C2 20 年 Calmar 0.363 → 0.376（近 5 年 1.273 → 1.356）；
    同日登记的确认（日経225 以外 714 只，逐笔）没有确认（前半 −0.28 pp、后半 +0.27 pp）→ 维持现行。那时的系统是 S0C2（核心 1655、没有 C / X6 / 判断层）；
    现在的 B1 加了 C（按日経 200 日线上下 × VIX 分四格的选股）、X6、Q1H 核心与判断层 → 这一层在 B1 上有没有用没有检验过。
    道理：趋势过滤（跌破 200 日线不买）的代价是错过反弹初段的突破；第二个循环 NDRH（核心「早回来」）第一关全过，是同一类道理在核心上的版本。
    先验中等偏弱：E / J（2006〜2026）对这一层不是没看过的数据（上面的消融），Z（2001〜2006）没看过。
做法（只改量化状态层；其余 —— 买点、C、离场、核心、宏观层、板块倾斜、判断层 —— 全部同 B1；不是事后组合、S7 不适用）：
  研究引擎 scripts/candle_portfolio.run 的 regime_floor（研究用，缺省 None = B1）：状态层倍数 → max(倍数, regime_floor)。
  RGX = regime_floor 1.0（= 去掉这一层：risk_off 0 → 1、neutral 0.75 → 1）。
S5（仓位版；倍数由市场状态决定 → 登记时写明 W / Jx 每笔的权重）：W / Jx 里 B1 会买的信号，B1 的权重 = 信号日的状态层倍数（0 / 0.75 / 1，
  与引擎同一个函数、同一个错一天），候选的权重 = max(倍数, 1.0) = 1；每笔超额 x = 净收益 − O0 同期；
  dmean = 平均[(候选权重 − B1 权重) × x] ≥ 0、dwin = 按候选权重加权的跑赢核心比例 − 按 B1 权重加权的 ≥ 0（B1 权重全为 1 时 = research_loop5.s5_sizing）。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次；kind = struct）：① 相邻参数值 regime_floor 0.75、0.5 也要过 S1 与 S2；
  ② 400 次配对重抽：每个年代随机去掉 20% 的 B1 会买的信号（research_loop5.drop_mask，种子 [20261005, 2, s, 年代序号]），B1 与 RGX 用同一批，
  三个年代 Calmar 差合计 400 次全部 > 0（research_loop5.stage2_struct）。
接线核对（登记前，不看候选的收益）：J 年代 ① regime_floor 0.0（同一条代码路径、倍数不变）→ 与 B1 逐项相同；② J 里状态层倍数 < 1 的天数 > 0；
  ③ B1 的日本个股成交，信号日的状态层倍数都 > 0（这里算的状态层与引擎对得上）。
只描述（不参与判定）：各年代按状态分的 B1 会买的信号数与 B1 成交数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop5_r10_regime.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 RGX [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r10_regime.md / .json（第二关 loop5_r10_regime_stage2_RGX.md / .json）。非投资建议。
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
import candle_portfolio as CP                                                # noqa: E402
import leap_confirm as LF                                                    # noqa: E402

ROUND = 10
IDS = ("RGX",)
FAMILY = {"RGX": "仓位·状态层"}
KIND = {"RGX": "struct"}
POSTHOC = False
FLOOR = {"RGX": 1.0}
NEIGHBORS = (0.75, 0.5)
OUT = "loop5_r10_regime"




# ───────────────────────── 纯函数（tests/test_loop5_r10.py） ─────────────────────────
def s5_weights(x, wb, wc) -> dict:
    """候选与 B1 的每笔权重都可能不是 1：dmean = 平均[(wc − wb) × x]；dwin = 按 wc 加权的跑赢核心比例 − 按 wb 加权的（pp）。
    wb 全为 1 时与 research_loop5.s5_sizing(x, wc) 相同。"""
    x, wb, wc = np.asarray(x, float), np.asarray(wb, float), np.asarray(wc, float)
    ok = np.isfinite(x) & np.isfinite(wb) & np.isfinite(wc)
    x, wb, wc = x[ok], wb[ok], wc[ok]
    if not len(x):
        return {"n": 0, "dwin": None, "dmean": None}
    beat = (x > 0).astype(float)
    wr = lambda w: float((w * beat).sum() / w.sum()) * 100 if w.sum() > 0 else None   # noqa: E731
    a, b = wr(wc), wr(wb)
    return {"n": int(len(x)), "dwin": (a - b) if a is not None and b is not None else None, "dmean": float(((wc - wb) * x).mean()),
            "mean_x": float(x.mean()), "beat": float(beat.mean() * 100), "m_mean": float(wc.mean()), "wb_mean": float(wb.mean())}


def state_of(q) -> np.ndarray:
    """状态层倍数 → 状态名（0 → risk_off、0.75 → neutral、1 → risk_on）。"""
    q = np.asarray(q, float)
    return np.where(q <= 0.0, "risk_off", np.where(q < 1.0, "neutral", "risk_on"))


# ───────────────────────── 输入 ─────────────────────────
def regime_series(W: dict) -> pd.Series:
    """引擎同一个函数（qbreak/regime.quant_regime_series）在日経收盘上的逐日倍数（信号日收盘时已知）。"""
    from qbreak.regime import quant_regime_series
    n = W["inp"]["n225"]
    n = n[~n.index.duplicated(keep="last")]
    return quant_regime_series(n)


def inputs(W: dict) -> dict:
    qr = regime_series(W)
    sig = {e: R5.b1_signals(W, e) for e in L2.ERAS}
    return {"qr": qr, "sig": sig, "sig_q": {e: R1.at_dates(qr, sig[e]["date"]) for e in L2.ERAS}}


def runs(W: dict, e: str, M: dict) -> dict:
    return {k: {"regime_floor": FLOOR[k]} for k in IDS}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s in ("W", "Jx"):
        X = pools[s]
        wb = R1.at_dates(M["qr"], X["date"])
        for k in IDS:
            wc = R1.at_dates(CP.regime_with_floor(M["qr"], FLOOR[k]), X["date"])
            out[k][s] = s5_weights(X["xs"].to_numpy(float), wb, wc)
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
        qs, qt, qd = state_of(M["sig_q"][e]), state_of(R1.at_dates(M["qr"], sig)) if len(sig) else np.array([]), state_of(R1.at_dates(M["qr"], win))
        cnt = lambda arr: {s: int((arr == s).sum()) for s in ("risk_off", "neutral", "risk_on")}   # noqa: E731
        out[e] = {"b1_trades": int(len(tr)), "signals": int(len(M["sig"][e])), "signals_by_state": cnt(qs), "trades_by_state": cnt(qt),
                  "days_by_state_pct": {s: round(float((qd == s).mean() * 100), 1) for s in ("risk_off", "neutral", "risk_on")}}
    return out


def pool_scale(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    return {s: {"n": int(len(pools[s])), **{st: int((state_of(R1.at_dates(M["qr"], pools[s]["date"])) == st).sum()) for st in ("risk_off", "neutral", "risk_on")}}
            for s in ("W", "Jx")}


# ───────────────────────── 运行 ─────────────────────────
_acct = R1._acct
_f = R1._f
NAMES = {"RGX": "去掉量化状态层（risk_off 0 → 1、neutral 0.75 → 1）"}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r10_regime.py", "qbreak/regime.py", "scripts/loop5_r02_volc.py",
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
           "scale": scale(W, M, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 10 轮：去掉量化状态层 RGX（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r10_regime.py 开头）", ""]
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
    L += ["", "规模（不参与判定；状态 = 信号日收盘的量化状态层）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个（risk_off {x['signals_by_state']['risk_off']} / neutral {x['signals_by_state']['neutral']} / "
                 f"risk_on {x['signals_by_state']['risk_on']}）；B1 的日本个股 {x['b1_trades']} 笔（risk_off {x['trades_by_state']['risk_off']} / "
                 f"neutral {x['trades_by_state']['neutral']} / risk_on {x['trades_by_state']['risk_on']}）；天数 risk_off {x['days_by_state_pct']['risk_off']}% / "
                 f"neutral {x['days_by_state_pct']['neutral']}% / risk_on {x['days_by_state_pct']['risk_on']}%")
    for k in IDS:
        for s in ("W", "Jx"):
            z = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：B1 会买的信号 {z['n']} 个（每笔超额平均 {_f(z.get('mean_x'), '{:+.2f}')} pp、跑赢核心 {_f(z.get('beat'), '{:.1f}')}%、"
                     f"B1 权重平均 {_f(z.get('wb_mean'), '{:.3f}')} → 候选 {_f(z.get('m_mean'), '{:.3f}')}）→ dmean {_f(z['dmean'], '{:+.3f}')} pp、dwin {_f(z['dwin'], '{:+.2f}')} pp")
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
    print(json.dumps({"scale": scale(W, M, b1), "pools": pool_scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① regime_floor 0.0（同一条代码路径、倍数不变）→ 与 B1 逐项相同；② J 里状态层倍数 < 1 的天数 > 0；
    ③ B1 三个年代的日本个股成交，信号日的状态层倍数都 > 0（这里算的与引擎对得上）。不看候选的收益。"""
    W = L2.load()
    M = inputs(W)
    rb = L2.run(W, "J")
    r0 = L2.run(W, "J", regime_floor=0.0)
    same = all(rb.get(x) == r0.get(x) for x in R5.WIRING_KEYS)
    days = pd.DatetimeIndex(W["ctx"]["J"]["days"])
    n = {"RGX": int((R1.at_dates(M["qr"], days) < 1.0).sum())}
    off = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        L2.run(W, e)
        tr = X3.jp_stock_trades(X3.last_trades(), a, b)
        dd = pd.DatetimeIndex(W["ctx"][e]["days"])
        sig = [dd[max(0, int(dd.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])] if len(tr) else []
        off[e] = int((R1.at_dates(M["qr"], sig) <= 0).sum()) if len(sig) else 0
    print(json.dumps({"floor0_same_as_b1": same, "nonunit_days_J": n, "b1_trades_on_risk_off": off}, ensure_ascii=False))
    return 0 if same and all(v > 0 for v in n.values()) and not any(off.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；kind = struct） ─────────────────────────
_G: dict = {}


def drop_fr(W: dict, e: str, S: pd.DataFrame, seed: int, era_idx: int) -> dict:
    """这个年代 B1 会买的信号随机去掉 20%（research_loop5.drop_mask）→ 买点掩码再关掉这些（B1 与候选用同一份）。"""
    drop = R5.drop_mask(len(S), int(seed), int(era_idx))
    fa = W["SM"][e]["fa"]
    keep: dict = {}
    for t, d in zip(S["ticker"].to_numpy()[drop], pd.to_datetime(S["date"]).to_numpy()[drop]):
        if t in fa:
            keep.setdefault(t, np.ones(len(fa[t]), bool))[fa[t].index.get_loc(pd.Timestamp(d))] = False
    return LF.with_mask(W["fr"][e], keep)


def _placebo_one(seed: int):
    W, M, k = _G["W"], _G["M"], _G["k"]
    try:
        tot = 0.0
        for i, e in enumerate(L2.ERAS):
            fr = drop_fr(W, e, M["sig"][e], int(seed), i)
            b = L2.run(W, e, fr=fr)["calmar"]
            c = L2.run(W, e, fr=fr, regime_floor=FLOOR[k])["calmar"]
            if b is None or c is None:
                return None
            tot += c - b
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
    nb = {}
    for f in NEIGHBORS:
        d = {e: None if base[e] is None else (lambda c: None if c is None else round(c - base[e], 6))(L2.run(W, e, regime_floor=f)["calmar"]) for e in L2.ERAS}
        ok = all(v is not None for v in d.values())
        nb[str(f)] = {"d": d, "sum": round(sum(d.values()), 6) if ok else None,
                      "S1": bool(ok and sum(d.values()) >= R5.SUM_MIN), "S2": bool(ok and all(v >= -R5.ERA_TOL for v in d.values()))}
    neighbors_ok = all(v["S1"] and v["S2"] for v in nb.values())
    _G.update({"W": W, "M": M, "k": k})
    seeds = list(range(R5.PLACEBO_N))
    vals = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"配对重抽 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
            if (i + 1) % 40 == 0:
                print(f"配对重抽 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    s2 = R5.stage2_struct(vals, neighbors_ok)
    vd = R5.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 5, "round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "neighbors": nb, "neighbors_ok": neighbors_ok,
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (1, 5, 50)} if len(v) else {}, "seconds": round(time.time() - t0)}
    L = [f"# 第五个研究循环第 10 轮 第二关：{k}（struct）相邻参数 + 400 次配对重抽（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：相邻参数 " + "、".join(f"regime_floor {f}：合计 {_f(x['sum'], '{:+.3f}')}（S1 {'过' if x['S1'] else '不过'}、S2 {'过' if x['S2'] else '不过'}）" for f, x in nb.items())
         + f"；配对重抽 400 次里最小 {_f(s2['min'], '{:+.4f}')}、≤ 0 的 {s2['le0']} 次、算出 {s2['valid']} / {s2['n']} 次；1 / 5 / 50 分位 "
         f"{_f(res['q'].get(1), '{:+.4f}')} / {_f(res['q'].get(5), '{:+.4f}')} / {_f(res['q'].get(50), '{:+.4f}')}",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第五个研究循环第 10 轮：RGX（仓位：去掉量化状态层）")
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
