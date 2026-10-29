"""idle_mult_study.py — 闲置资金自动买入也受「现在倍率」影响（2026-10-05 登记 = 本提交；之后不改规则、只运行一次）。

用户（2026-10-05）：「进行闲置资金自动买入的时候也受现在倍率影响的研究」。
现在（B3 = 模拟盘 var/sim.json，闲置资金 Q1B）：日报的「明天新仓倍数」= 量化状态层（日経：0 / 0.75 / 1）、宏观层（Brent、美 10 年、VIX、
USD/JPY 的阈值：×0.5 / ×0.75）、前向记录判断层的市场层（×1 / ×0.75 / ×0.5）取最小 —— 只管日本个股新仓；闲置资金（美股牛 → 纳指 1545；
美股熊且股债 63 天负相关 → 对冲版美债 1482；其余现金）不受它影响。2026-10-02 收盘的读数 = ×0.5（宏观：美 10 年 5.28% ≥ 5.2 → ×0.5、
Brent 102 ≥ 100 → ×0.75；判断层 1 分 ×0.75；量化层 ×1）。
以前做过的（照实写，结论不变）：威胁指数 / C_rel 当「预计大跌」的核心开关三次否定（2026-09-30 写定不再这样用）；「加息预期代理高 → 闲置资金空仓」
（hike_gate_study 49c4c8a）不通过；「越危险越加仓」（b36ebca）不通过；按波动减核心 VT20 / VTU / VTX 不通过、VCT 只进前向记录。
这次检验的是「日报上那个倍数原样用在闲置资金上」—— 量化层（日経 200 日线等）与宏观层的阈值用在核心上以前没有检验过；判断层是其中一层。

〇 账户基准 B3（scripts/loop6_common.load3；登记值 Calmar Z 1.194 / E 0.627 / J 0.676；个股层原样，包括它自己的新仓倍数）。
一 倍数（每个东证交易日 d 收盘时已知 → d 收盘后的决策、d+1 开盘成交，与模拟盘同一个时点；纯函数 readings）：
   q(d)   = qbreak.regime.quant_regime_series（日経 ^N225：200 日线、20 日波动、252 日回撤 → 0 / 0.75 / 1；模拟盘与回测同一个函数）；
   mac(d) = qbreak.macro.macro_mult(features_at(宏观序列, d), None, "JP")（同一个函数与阈值；宏观序列 = load_macro_series（yfinance，27 年）；
            「市场风险报告」那一层（overlay）没有历史 → 不算，与以前的回测相同）；
   ma(d)  = 前向记录判断层的市场层（loop_common.ma_factor：fwd_judgment_check.daily_mults 的 MA；A5 K4 不计分）；
   m(d)   = min(q, mac, ma)（模拟盘的取法 = 日报「明天新仓倍数」；个股层的回测照旧是相乘，不改）。
二 候选（两个；kind = signal；倍数的规则都是现成的、没有新参数 → S6 不适用；不改个股 → S5 不适用；不是看了结果之后设计的 → S7 不适用）：
   IM1「全部闲置资金 × 倍数」：引擎 core_expo["US"]（纳指 1545 的目标）与 extra_expo["US_BD"]（对冲版美债 1482 的目标）都再乘 m(d)；减下来的留现金（日元）。
   IM2「只有纳指 × 倍数」：只 core_expo["US"] = m(d)；1482（美股熊时的避险）照 B3。
三 第一关 = research_loop6.stage1（S1 三个年代 Calmar 差合计 ≥ +0.03、S2 每个年代 ≥ −0.02、S3 最大回撤不深 2 pp 以上、S4 前后两半的差合计都 ≥ 0）
   在 B3 上（与同一次运行重算的 B3 比）。
   第二关（第一关全过的候选才做，同一次运行）：m(d) 在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：
   numpy.random.default_rng([20261006, 0, s])，s = 0〜399；窗外不动；B3 与个股层不动）；候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
   两关都过 =「更好候选」→ 向用户提议（模拟盘与执行器在用户说「采用」之前不改）；否则模拟盘不变。
四 只描述（不参与判定、不能据此采用；要用必须另行登记）：各年代 m 的分布（0 / 0.5 / 0.75 / 1 的日子比例）、m < 1 的段数、m < 1 时哪一层是最小的；
   只用其中一层的三个版本（Q / MAC / MA 各自单独 × 全部闲置资金，接法同 IM1）的账户；每年收益差；核心换仓笔数；最新一天的读数。
接线核对（登记前，不看候选的结果；--wiring）：① m ≡ 1 → IM1 / IM2 的接法三个年代与 B3 逐项相同；② B3 的引擎参数里没有别的 core_expo / extra_expo；
   ③ 日报那一天（var/out/report_data.json 的 bar_date）的 q / mac / ma / m 与日报的 quant_mult / 宏观 mult / 判断层 mult / final_mult 相同；
   ④ 1482 那一份真的跟着 extra_expo 走：IM1 的接法里只让美债那份 ≡ 0 → J 年代的核心成交里没有 1482。
规模（登记前，只数日子；--scale）：三个年代 m 的分布、段数、哪一层最常是最小、最新一天的读数。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/idle_mult_study.py [--workers N]（第一关 + 第二关，只运行一次）；--scale；--wiring。
输出 var/out/idle_mult_study.md / .json（第二关同一个文件）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_r02_bondrefuge as T2                                            # noqa: E402
import loop6_common as L6                                                    # noqa: E402
import loop6_r07_volbond as V                                                # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

IDS = ("IM1", "IM2")
DESC = ("Q", "MAC", "MA")                                                    # 只描述：单独一层
KIND = {"IM1": "signal", "IM2": "signal"}
BOND = {"IM1": True, "IM2": False, "Q": True, "MAC": True, "MA": True}       # 1482 那一份是否也乘
LAYER = {"Q": "q", "MAC": "mac", "MA": "ma"}
LEVELS = (0.0, 0.5, 0.75, 1.0)
MACRO_YEARS = 27                                                             # 宏观序列的年数（覆盖 Z 年代；与 Z / E 的回测同一个值）
OUT = "idle_mult_study"
KEYS = ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")


# ───────────────────────── 规则（纯函数，tests/test_idle_mult_study.py） ─────────────────────────
def _on(s: pd.Series, days: pd.DatetimeIndex, fill: float = 1.0) -> pd.Series:
    """数值序列 → days 上（d 日 = d 之前（含 d）最近一个值；没有值 = fill）。"""
    days = pd.DatetimeIndex(days)
    return s.astype(float).reindex(days.union(s.index)).ffill().reindex(days).fillna(fill)


def macro_series(frame: pd.DataFrame | None, days: pd.DatetimeIndex) -> pd.Series:
    """每个 d：macro_mult(features_at(frame, d), None, "JP")（与模拟盘 / 回测同一个函数；frame 空 → 1）。"""
    from qbreak.macro import features_at, macro_mult
    days = pd.DatetimeIndex(days)
    return pd.Series([float(macro_mult(features_at(frame, d), None, "JP")[0]) for d in days], index=days)


def readings(qr: pd.Series, mac: pd.Series, ma: pd.Series, days: pd.DatetimeIndex) -> pd.DataFrame:
    """东证交易日 d（收盘时已知）：q、mac、ma（缺 = 1）与 m = 三者取最小。"""
    days = pd.DatetimeIndex(days)
    q, mc, a = _on(qr, days), _on(mac, days), _on(ma, days)
    m = np.minimum(np.minimum(q.to_numpy(float), mc.to_numpy(float)), a.to_numpy(float))
    return pd.DataFrame({"q": q.to_numpy(float), "mac": mc.to_numpy(float), "ma": a.to_numpy(float), "m": m}, index=days)


def over_for(m: pd.Series, bond: bool) -> dict:
    """B3 上再改一处：纳指 1545（键 US）的目标 × m；bond = True 时对冲版美债 1482（键 US_BD）的目标也 × m。减下来的留现金。"""
    x = m.astype(float).clip(0.0, 1.0)
    ov = {"core_expo": {"US": x}}
    if bond:
        ov["extra_expo"] = {T2.BD_KEY: x}
    return ov


def shifted(m: pd.Series, k: int | None) -> pd.Series:
    """第二关：m 在 2000-01-04〜J 的最后一天上整体循环平移 k（None = 不平移），窗外不动。"""
    s = m.astype(float).copy()
    if k is not None:
        w = R6.shift_window(s)
        s.loc[w.index] = R6.shift_signal(w, k).to_numpy(float)
    return s


def placebo_ks(n: int) -> list[int]:
    return R6.shift_ks(n, 0)


def binding(R: pd.DataFrame) -> dict:
    """m < 1 的日子里，各层「等于 m」（是最小的那一层）的比例（并列都算）。"""
    low = R["m"] < 1.0 - 1e-12
    n = int(low.sum())
    if not n:
        return {"days": 0, "q": None, "mac": None, "ma": None}
    sub = R[low]
    return {"days": n, **{k: round(float((np.abs(sub[k] - sub["m"]) < 1e-12).mean() * 100), 1) for k in ("q", "mac", "ma")}}


def dist(R: pd.DataFrame, days: pd.DatetimeIndex) -> dict:
    """这段日子里 m 的分布（%）、m < 1 的段数、平均 m、哪一层最常是最小。"""
    sub = R.reindex(pd.DatetimeIndex(days)).dropna()
    if not len(sub):
        return {"days": 0}
    out = {"days": int(len(sub)), "mean_m": round(float(sub["m"].mean()), 3),
           "pct": {f"{v:g}": round(float((np.abs(sub["m"] - v) < 1e-12).mean() * 100), 1) for v in LEVELS},
           "segments_lt1": V.segments(sub["m"] < 1.0 - 1e-12), "binding": binding(sub)}
    for k in ("q", "mac", "ma"):
        out[f"{k}_lt1_pct"] = round(float((sub[k] < 1.0 - 1e-12).mean() * 100), 1)
    return out


# ───────────────────────── 输入 ─────────────────────────
def inputs(W: dict) -> dict:
    """{R: 读数表（东证交易日）, days, latest}。q 用 ^N225（与回测的 make_runner 同一个取法）；宏观 27 年；判断层 = B3 已经算好的 W["MA"]。"""
    from bullbear_study import SYM, load
    from qbreak.config import DataConfig
    from qbreak.macro import features_frame, load_macro_series
    from qbreak.regime import quant_regime_series
    n225 = load(*SYM["JP"])
    qr = quant_regime_series(n225)
    days = pd.DatetimeIndex(qr.index[qr.index >= pd.Timestamp("1999-01-01")])
    frame = features_frame(load_macro_series(DataConfig(provider="yfinance", years=MACRO_YEARS, allow_synthetic=False).validate()))
    mac = macro_series(frame, days)
    R = readings(qr, mac, W["MA"]["MA"], days)
    return {"R": R, "days": days, "frame_start": str(frame.index[0].date()) if len(frame) else None}


# ───────────────────────── 规模（只数日子） ─────────────────────────
def scale(W: dict, M: dict) -> dict:
    R = M["R"]
    out = {e: dist(R, V.era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(R["m"])
    out["window"] = dist(R, w.index)
    out["shift_n"] = int(len(w))
    last = R.index[-1]
    out["latest"] = {"date": str(last.date()), **{k: float(R[k].iloc[-1]) for k in ("q", "mac", "ma", "m")}}
    out["macro_frame_start"] = M.get("frame_start")
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in KEYS}


def core_count(e: str, W: dict, ticker: str | None = None) -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    return int(sum(1 for x in eng.st.core_trades if x[0] >= a and (b is None or x[0] < b) and (ticker is None or x[1] == ticker)))


def stage_one(workers: int) -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = V.git_head()
    W = L6.load3()
    M = inputs(W)
    R = M["R"]
    variants = {k: over_for(R["m"], BOND[k]) for k in IDS}
    variants.update({k: over_for(R[LAYER[k]], True) for k in DESC})
    base, cand, trades = {}, {k: {} for k in variants}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        trades[e] = {"B3": core_count(e, W)}
        base[e] = {**_acct(rb), "years": rb.get("years")}
        for k, ov in variants.items():
            rc = L6.run(W, e, **ov)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = core_count(e, W)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {k: R6.stage1(cand[k], base) for k in IDS}
    s1d = {k: R6.stage1(cand[k], base) for k in DESC}
    reg = {"Z": 1.194, "E": 0.627, "J": 0.676}
    drift = {e: (None if base[e]["calmar"] is None else round(base[e]["calmar"] - reg[e], 4)) for e in L6.ERAS}
    res = {"code": code, "dirty": dirty, "ids": list(IDS), "desc": list(DESC), "kind": KIND, "base": base, "cand": cand, "stage1": s1,
           "desc_stage1": s1d, "drift": drift, "scale": scale(W, M), "core_trades": trades, "stage2": {}}
    for k in IDS:
        if s1[k]["ok"]:
            res["stage2"][k] = stage_two(W, M, k, base, cand[k], workers, t0)
    res["verdict"] = {k: R6.verdict(s1[k], res["stage2"].get(k, {}).get("s2")) for k in IDS}
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


_G: dict = {}


def _placebo_one(seed: int):
    W, M, k, base, ks = _G["W"], _G["M"], _G["k"], _G["base"], _G["ks"]
    try:
        ov = over_for(shifted(M["R"]["m"], ks[int(seed)]), BOND[k])
        tot = 0.0
        for e in L6.ERAS:
            c = L6.run(W, e, **ov)["calmar"]
            if c is None or base[e]["calmar"] is None:
                return None
            tot += c - base[e]["calmar"]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(W: dict, M: dict, k: str, base: dict, cand: dict, workers: int, t0: float) -> dict:
    """第二关：m 循环平移 400 次（第一关全过才做；同一次运行）。"""
    import multiprocessing as mp
    stat = round(sum(cand[e]["calmar"] - base[e]["calmar"] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["R"]["m"]))
    ks = placebo_ks(n)
    _G.update({"W": W, "M": M, "k": k, "base": base, "ks": ks})
    seeds = list(range(R6.PLACEBO_N))
    vals = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"{k} 随机平移 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
            if (i + 1) % 40 == 0:
                print(f"{k} 随机平移 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    s2 = R6.stage2(stat, vals)
    v = np.array([x for x in vals if x is not None], float)
    return {"stat": stat, "n": n, "placebo": vals, "s2": s2,
            "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
            "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None}


def write(res: dict) -> None:
    from qbreak import paths
    f = V._f
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    name = {"IM1": "全部闲置资金 × 倍数", "IM2": "只有纳指 × 倍数", "Q": "只用量化层", "MAC": "只用宏观层", "MA": "只用判断层"}
    L = [f"# 闲置资金自动买入也受「现在倍率」影响（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/idle_mult_study.py 开头；基准 B3 = 模拟盘 Q1B）", ""]
    for k in IDS:
        s = res["stage1"][k]
        s2 = (res["stage2"].get(k) or {}).get("s2")
        tail = "" if not s2 else (f"；第二关：候选 {f(res['stage2'][k]['stat'], '{:+.4f}')} vs 400 次平移最大 {f(s2['max'], '{:+.4f}')}"
                                  f"（≥ 候选 {s2['ge_stat']} 次）→ {yn(s2['ok'])}")
        L.append(f"- **{k}（{name[k]}）：{res['verdict'][k]}**（S1 合计 {f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
                 f"S4（{f(s['h1'], '{:+.3f}')} / {f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}{tail}）")
    L += ["", "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | IM1（Calmar 差） | IM2（Calmar 差） |", "|---|---|---|---|"]
    cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])}（{f(x['h1'])} / {f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + " |")
    L += ["", "只描述（不参与判定、不能据此采用）：单独一层 × 全部闲置资金（接法同 IM1）的 Calmar 差 Z / E / J（合计）："]
    for k in DESC:
        s = res["desc_stage1"][k]
        L.append(f"- {k}（{name[k]}）：" + " / ".join(f(s["d"][e], "{:+.3f}") for e in L6.ERAS) + f"（{f(s['sum'], '{:+.3f}')}）")
    sc = res["scale"]
    L += ["", "倍数的分布（只数日子）："]
    for e in (*L6.ERAS, "window"):
        x = sc[e]
        if not x.get("days"):
            continue
        b = x["binding"]
        L.append(f"- {e}：{x['days']} 天，m = 0 / 0.5 / 0.75 / 1 的日子 " + " / ".join(f"{x['pct'][f'{v:g}']}%" for v in LEVELS)
                 + f"，平均 m {x['mean_m']}，m < 1 的段数 {x['segments_lt1']}；各层 < 1 的日子 量化 {x['q_lt1_pct']}% / 宏观 {x['mac_lt1_pct']}% / 判断层 {x['ma_lt1_pct']}%；"
                 + f"m < 1 时是最小的那一层 量化 {b['q']}% / 宏观 {b['mac']}% / 判断层 {b['ma']}%")
    lt = sc["latest"]
    L.append(f"- 最新一天 {lt['date']}：量化 ×{lt['q']:g}、宏观 ×{lt['mac']:g}、判断层 ×{lt['ma']:g} → m = ×{lt['m']:g}")
    for e in L6.ERAS:
        tr = res["core_trades"][e]
        L.append(f"- {e} 核心换仓笔数：B3 {tr['B3']}、" + "、".join(f"{k} {tr[k]}" for k in (*IDS, *DESC)))
        yb = res["base"][e].get("years") or {}
        for k in IDS:
            yc = res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"  - {k} 每年收益差（pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    for k, x in (res.get("stage2") or {}).items():
        L.append(f"- {k} 第二关：400 次平移 中位 {f(x['q'].get(50), '{:+.4f}')}、95 分位 {f(x['q'].get(95), '{:+.4f}')}、99 分位 {f(x['q'].get(99), '{:+.4f}')}；"
                 f"比 B3 好的 {f(x['pos_share'], '{:.1f}')}%")
    dr = res["drift"]
    L += ["", "B3 与登记值的 Calmar 差：" + "、".join(f"{e} {f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load3()
    M = inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False, default=float))
    return 0


def wiring() -> int:
    """登记前用：① m ≡ 1 → B3；② B3 没有别的 core_expo / extra_expo；③ 日报那一天的读数 = 日报；④ 1482 那一份跟着 extra_expo 走。"""
    from qbreak import paths
    W = L6.load3()
    M = inputs(W)
    R = M["R"]
    no_other = {e: all(x not in (W["kw"][e] or {}) and x not in (W.get("b1") or {}) for x in ("core_expo", "extra_expo")) for e in L6.ERAS}
    ones = pd.Series(1.0, index=R.index)
    same_b3 = {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        same_b3[e] = {k: bool(all(rb.get(x) == L6.run(W, e, **over_for(ones, BOND[k])).get(x) for x in KEYS)) for k in IDS}
    rep = json.loads((paths.out_dir() / "report_data.json").read_text(encoding="utf-8"))
    jr = ((rep.get("extras") or {}).get("JP") or {})
    bar = str(rep.get("bar_date") or "")
    got = R.loc[:pd.Timestamp(bar)].iloc[-1] if bar else None
    want = {"q": (jr.get("regime") or {}).get("quant_mult"), "mac": (jr.get("macro") or {}).get("mult"),
            "ma": ((jr.get("regime") or {}).get("fwd_judgment") or {}).get("mult"), "m": (jr.get("regime") or {}).get("final_mult")}
    same_rep = {k: (None if got is None or want[k] is None else bool(abs(float(got[k]) - float(want[k])) < 1e-9)) for k in want}
    ov = {"core_expo": {"US": ones}, "extra_expo": {T2.BD_KEY: pd.Series(0.0, index=R.index)}}
    L6.run(W, "J", **ov)
    bond_j = core_count("J", W, T2.BOND_T)
    L6.run(W, "J")
    bond_b3 = core_count("J", W, T2.BOND_T)
    out = {"no_other_expo": no_other, "ones_same_as_b3": same_b3, "report_date": bar,
           "reading_on_report_date": None if got is None else {k: float(got[k]) for k in ("q", "mac", "ma", "m")},
           "report": want, "same_as_report": same_rep, "bond_trades_J": {"B3": bond_b3, "bond_expo_0": bond_j}}
    print(json.dumps(out, ensure_ascii=False, default=float))
    ok = (all(no_other.values()) and all(all(v.values()) for v in same_b3.values()) and all(v is True for v in same_rep.values())
          and bond_b3 > 0 and bond_j == 0)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="闲置资金自动买入也受现在倍率影响：IM1 / IM2")
    ap.add_argument("--scale", action="store_true")
    ap.add_argument("--wiring", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return stage_one(a.workers)


if __name__ == "__main__":
    raise SystemExit(main())
