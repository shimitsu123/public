"""loop6_r02_bondgate.py — 第六个研究循环第二段（基准 B2 = 采用后的模拟盘 B1 + BCU）第 2 轮：BCU 的债券只在「真的在避险」时拿 BCS / BCM / BCF
（2026-10-03 登记；先提交后只运行一次；家族「核心·熊市避险资产」第二段 3 / 3；三个都是事后 → S7 适用）。

用户（2026-10-03）：「采用\\n\\n并且继续第六个研究循环」。循环的规则：scripts/research_loop6.py（第二段 = 开头七与末尾一节）；基准 B2：scripts/loop6_common.py。
为什么先做这个（照实写）：
  - B2 的 BCU 在美股熊市里只看「最近 63 天 S&P500 与 1482 日收益负相关」。负相关有两种：股跌债涨（避险，BCU 想要的）与股涨债跌（反弹里资金从债券回到股票）。
    第 1 轮的每年收益差里差的年份正是后一种：E 2009 −11.2 pp（2009-03 起股市反弹、美债下跌，相关仍为负 → 照样拿）、J 2022 −1.5 pp（2022 熊市里 32 天相关为负，
    多在夏天的反弹里）、E 2012 / 2015 −1.3 / −1.5 pp。→ 看过这些之后设计 → 三个都按事后处理（S7 适用：没看过的 1987〜2000 只有核心，候选 − B2 > 0）。
  - 机制：股债相关为负时国债才是对冲（Campbell, Sunderam & Viceira 2017），但对冲要在股市下跌的那条腿上才有用；反弹里国债往往跌（risk-on 轮动）。
    国债自己的时间序列动量（Moskowitz, Ooi & Pedersen 2012：3〜12 个月的过去收益预测下个月同方向）→ 国债在跌的时候避险作用多半已经结束。
  - 参数不调：窗口与 BCU 同一个 63 个东证交易日（一个季度）、门槛 0（正负）→ S6 不适用；不改个股 → S5 不适用。
做法（只在 B2 拿 1482 的那些日子里加一个条件；条件不成立 → 现金（= B1 / Q1H 在美股熊时的做法）；美股牛、FJE、个股层全部同 B2）：
  - BCS：再加「S&P500 最近 63 天下跌」（东证 d 日用 d 之前最近的美国收盘，与 BCU 的 S&P500 同一个序列）→ 股市还在跌才拿债券。
  - BCM：再加「1482 合成价最近 63 天上涨」（BCU 同一个合成价、同一个对齐）→ 债券自己在涨才拿。
  - BCF：两个都要（股跌且债涨 = 避险确实在发生）。
  接法：loop2_r02_bondrefuge.tbh_over(美股熊, BCU 条件 ∧ 新条件, 1482 K 线) —— 与 B2 同一个函数，只换「可拿」序列（候选的键覆盖 B2 的同名键）。
第一关：research_loop6.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 候选 − B2 的 Calmar 差；只有核心的口径同第 1 轮 old_core，
  美国日期上算同样的 63 天相关与 63 天涨跌、再晚一天用（FRED 第二天才公布））。
第二关（第一关全过的才做；另行登记后只运行一次；代码写在本脚本 --stage2）：BCS / BCM = signal —— 候选自己新加的条件（S&P500 下跌 / 债券上涨的布尔序列）在
  2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)），B2（BCU 的相关条件、美股熊、1482 价格）不动；
  BCF = combo —— 两个条件各自平移、k 由同一个种子依次抽出（research_loop6.combo_ks(n, 2)：先 S&P500、后债券）。候选的 Calmar 差合计要严格大于 400 次的最大值。
接线核对（登记前，不看候选的结果）：J 年代 ① 新条件全为 True → 与 B2 逐项相同；② 全为 False（从不拿债券）→ 与 B1（第 1 轮记录的 J 账户）相同。
只描述（不参与判定）：各年代 B2 拿 1482 的日子里三个条件各留下多少、段数；新条件在 2000〜2026 全部日子里成立的比例；1987〜2000 只有核心的三个数；每年收益差。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r02_bondgate.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 BCS|BCM|BCF [--workers N]（第二关）。
输出 var/out/loop6_r02_bondgate.md / .json（第二关 loop6_r02_bondgate_stage2_<ID>.md / .json）。非投资建议。
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
import loop2_r02_bondrefuge as T2                                            # noqa: E402
import loop2_r04_bondunion as T4                                             # noqa: E402
import loop6_common as L6                                                    # noqa: E402
import loop6_r01_bondcorr as T                                               # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 2
IDS = ("BCS", "BCM", "BCF")
FAMILY = {k: "核心·熊市避险资产" for k in IDS}
KIND = {"BCS": "signal", "BCM": "signal", "BCF": "combo"}
POSTHOC = True
WIN = T.WIN                                                                  # 63：与 BCU 的相关窗口同一个
USE = {"BCS": (True, False), "BCM": (False, True), "BCF": (True, True)}      # (S&P500 下跌, 债券上涨)
OLD = T.OLD
OUT = "loop6_r02_bondgate"


# ───────────────────────── 规则（纯函数，tests/test_loop6_r02.py） ─────────────────────────
def falling(s: pd.Series, win: int = WIN) -> pd.Series:
    """s 自己的日期上：最近 win 天下跌（s / s.shift(win) − 1 < 0）→ True；不到 win 天 → False。"""
    x = s.dropna().astype(float)
    r = x / x.shift(win) - 1
    return pd.Series(np.where(r.to_numpy(float) < 0, True, False), index=x.index)


def rising(s: pd.Series, win: int = WIN) -> pd.Series:
    """s 自己的日期上：最近 win 天上涨（> 0）→ True；不到 win 天 → False。"""
    x = s.dropna().astype(float)
    r = x / x.shift(win) - 1
    return pd.Series(np.where(r.to_numpy(float) > 0, True, False), index=x.index)


def on_idx(s: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """布尔序列 → idx 上（向后填；没有值 = False）。"""
    idx = pd.DatetimeIndex(idx)
    return s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx).fillna(0.0) > 0.5


def gates(M: dict) -> dict[str, pd.Series]:
    """{"spx_down", "bond_up"}：BCU 同一个 S&P500（东证日、前一个美国收盘）与 1482 合成价上的 63 天涨跌，放到 BCU 条件的日子上。"""
    idx = M["on_b"].index
    return {"spx_down": on_idx(falling(M["spx"]), idx), "bond_up": on_idx(rising(M["bc"]), idx)}


def gated(on_b: pd.Series, g: dict[str, pd.Series], use: tuple[bool, bool]) -> pd.Series:
    """BCU 的「可拿」∧ 用到的新条件（use = (S&P500 下跌, 债券上涨)）。"""
    out = on_b.astype(bool).copy()
    if use[0]:
        out &= on_idx(g["spx_down"], out.index)
    if use[1]:
        out &= on_idx(g["bond_up"], out.index)
    return out


def overs(bear_us: pd.Series, fb: pd.DataFrame, on_b: pd.Series, g: dict[str, pd.Series]) -> dict:
    """三个做法的覆盖：B2 同一个 tbh_over，只换「可拿」序列。"""
    return {k: T2.tbh_over(bear_us, gated(on_b, g, USE[k]), fb) for k in IDS}


def keep_stats(bear: pd.Series, on_b: pd.Series, cand: pd.Series, days: pd.DatetimeIndex) -> dict:
    """这段日子里：B2 拿 1482 的日子（美股熊 ∧ BCU 条件）、候选还拿的比例与段数、不拿的年份（只数日子）。"""
    days = pd.DatetimeIndex(days)
    b = on_idx(bear, days)
    hold2 = b & on_idx(on_b, days)
    holdc = b & on_idx(cand, days)
    yrs = hold2.groupby(days.year).sum()
    yc = holdc.groupby(days.year).sum()
    return {"b2_days": int(hold2.sum()), "cand_days": int(holdc.sum()),
            "keep_pct": round(float(holdc.sum() / hold2.sum() * 100), 1) if hold2.any() else None,
            "segments": T2.segments(holdc), "b2_segments": T2.segments(hold2),
            "dropped_by_year": {str(y): int(yrs[y] - yc.get(y, 0)) for y in yrs.index if yrs[y] - yc.get(y, 0) > 0}}


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, uni: pd.Series, use: tuple[bool, bool] | None) -> dict:
    """第 1 轮 old_core（BCU：美国日期上的 63 天相关、再晚一天用）同一个口径；use = None → B2 本身（只有 BCU 条件），
    否则再乘上美国日期上的 63 天 S&P500 下跌 / 债券上涨（同样再晚一天用）。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    import halloween_study as HW
    from qbreak import factors
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    ntr = EI.ndx_tr(inp)
    unh = EI.grow(ntr, -EI.FEE["1545.T"])
    unh = (unh * dex.reindex(unh.index.union(dex.index)).ffill().reindex(unh.index)).dropna()
    hed = FX.hedged_index(EI.grow(ntr, -0.22), factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9))
    bnd = T2.bond_hedged(T2.bond_usd())
    bnd = bnd[bnd.index >= pd.Timestamp(T2.BOND_START)]
    spx = inp["spx"]["Close"].astype(float)
    full = unh.index[unh.index >= pd.Timestamp(T2.BOND_START)]
    ffull = lambda s: s.astype(float).reindex(full.union(s.index)).ffill().reindex(full)      # noqa: E731
    cond = T.corr_on(ffull(spx), ffull(bnd))
    if use is not None:
        if use[0]:
            cond = cond & on_idx(falling(ffull(spx)), full)
        if use[1]:
            cond = cond & on_idx(rising(ffull(bnd)), full)
    on_u = cond.shift(1, fill_value=False)
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, hed, b_px = unh.reindex(idx), ff(hed), ff(bnd)
    bear = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    hdg = ff(uni).fillna(0.0) > 0.5
    off = pd.Series(False, index=idx)
    ou = ff(on_u).fillna(0.0) > 0.5
    w = T4.union_weights(bear, hdg, ou, off).shift(1).fillna(0.0)
    ret = (w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0))
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float((w["b"] > 0).mean() * 100), 1)
    return out


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    """B2 的 BCU 输入（loop6_common.load 已算好，W["bcu"]）+ 两个新条件。"""
    M = dict(W["bcu"])
    M["g"] = gates(M)
    return M


def scale(W: dict, M: dict) -> dict:
    out = {}
    for e in L6.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        days = days[(days >= pd.Timestamp(a)) & ((days < pd.Timestamp(b)) if b else True)]
        out[e] = {k: keep_stats(W["bear"]["US"], M["on_b"], gated(M["on_b"], M["g"], USE[k]), days) for k in IDS}
    w = R6.shift_window(M["g"]["spx_down"])
    out["true_share_2000_2026"] = {g: round(float(R6.shift_window(M["g"][g]).mean() * 100), 1) for g in ("spx_down", "bond_up")}
    out["shift_n"] = len(w)
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None else f.format(v)


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[2]
    try:
        h = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "quant_breakout/scripts", "quant_breakout/qbreak"],
                                    capture_output=True, text=True).stdout.strip())
        return h, dirty
    except Exception:                                                         # noqa: BLE001
        return "?", True


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L6.load()
    import loop2_common as L2
    _, _, uni = L2.fje_states(W)
    M = inputs(W)
    ov = overs(W["bear"]["US"], M["fb"], M["on_b"], M["g"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand = {}, {k: {} for k in IDS}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        for k in IDS:
            rc = L6.run(W, e, **ov[k])
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B2": old_core(W, uni, None), **{k: old_core(W, uni, USE[k]) for k in IDS}}
    s1 = {}
    for k in IDS:
        unseen = None if old["B2"]["calmar"] is None or old[k]["calmar"] is None else old[k]["calmar"] - old["B2"]["calmar"]
        s1[k] = R6.stage1(cand[k], base, posthoc=unseen)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    res = {"loop": 6, "segment": 2, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "scale": scale(W, M), "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第六个研究循环第二段第 2 轮：BCU 的债券只在「真的在避险」时拿 BCS / BCM / BCF（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r02_bondgate.py 开头；基准 B2 = B1 + BCU）", ""]
    for k in IDS:
        s = res["stage1"][k]
        pv = s["posthoc"]
        L.append(f"- **{k}：{'第一关全过 → 另行登记第二关（新条件循环平移）' if s['ok'] else R6.FAIL1}**"
                 f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
                 f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
                 f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）")
    L += ["", "| 年代 | B2 年化 / 最大回撤 / Calmar（前半 / 后半） | " + " | ".join(f"{k}（Calmar 差）" for k in IDS) + " |", "|---|---|" + "---|" * len(IDS)]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + " |")
    L += ["", "规模（不参与判定；只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：B2 拿 1482 {x['BCS']['b2_days']} 天（{x['BCS']['b2_segments']} 段）；" + "、".join(
            f"{k} 留下 {x[k]['cand_days']} 天（{_f(x[k]['keep_pct'], '{:.1f}')}%，{x[k]['segments']} 段）" for k in IDS))
    L.append(f"- 新条件在 2000〜2026 全部日子里成立的比例：S&P500 下跌 {sc['true_share_2000_2026']['spx_down']}%、债券上涨 {sc['true_share_2000_2026']['bond_up']}%")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、拿债券 {_f(o[k].get('bond_days_pct'), '{:.1f}')}% 的日子）"
        for k in ("B2",) + IDS))
    for e in L6.ERAS:
        yb = res["base"][e].get("years") or {}
        parts = []
        for k in IDS:
            yc = res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            parts.append(f"{k} " + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
        L.append(f"- {e} 每年收益差（候选 − B2，pp）：" + "；".join(parts))
    dr = res["drift"]
    L += ["", "B2 与第二段登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B2）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load()
    M = inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 新条件全为 True → 与 B2 逐项相同；② 全为 False（从不拿债券）→ 与 B1（第 1 轮记录的 J 账户）相同。"""
    from qbreak import paths
    W = L6.load()
    M = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    idx = M["on_b"].index
    g1 = {"spx_down": pd.Series(True, index=idx), "bond_up": pd.Series(True, index=idx)}
    g0 = {"spx_down": pd.Series(False, index=idx), "bond_up": pd.Series(False, index=idx)}
    rb = L6.run(W, "J")
    ov1 = overs(W["bear"]["US"], M["fb"], M["on_b"], g1)
    ov0 = overs(W["bear"]["US"], M["fb"], M["on_b"], g0)
    same_b2 = {k: all(rb.get(x) == L6.run(W, "J", **ov1[k]).get(x) for x in keys) for k in IDS}
    b1 = json.loads((paths.out_dir() / f"{T.OUT}.json").read_text(encoding="utf-8"))["base"]["J"]
    same_b1 = {}
    for k in IDS:
        r0 = L6.run(W, "J", **ov0[k])
        same_b1[k] = all(r0.get(x) is not None and b1.get(x) is not None and abs(r0[x] - b1[x]) <= 1e-9 for x in ("calmar", "cagr", "dd"))
    print(json.dumps({"always_same_as_b2": same_b2, "never_same_as_b1": same_b1}, ensure_ascii=False))
    return 0 if all(same_b2.values()) and all(same_b1.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；BCS / BCM = signal、BCF = combo） ─────────────────────────
_G: dict = {}


def shifted_gates(g: dict[str, pd.Series], ks: tuple[int | None, int | None]) -> dict[str, pd.Series]:
    """新条件在 2000-01-04〜J 的最后一天上整体循环平移（ks = (S&P500 下跌的 k, 债券上涨的 k)；None = 不平移），窗外不动。"""
    out = {}
    for name, k in zip(("spx_down", "bond_up"), ks):
        s = g[name].astype(bool).copy()
        if k is not None:
            w = R6.shift_window(s)
            s.loc[w.index] = R6.shift_signal(w, k).to_numpy(bool)
        out[name] = s
    return out


def placebo_ks(k: str, n: int) -> list[tuple[int | None, int | None]]:
    """每个种子的平移量：BCS / BCM = signal（shift_ks(n, 0)），BCF = combo（combo_ks(n, 2)：先 S&P500、后债券）。"""
    if k == "BCS":
        return [(x, None) for x in R6.shift_ks(n, 0)]
    if k == "BCM":
        return [(None, x) for x in R6.shift_ks(n, 0)]
    return [(a, b) for a, b in R6.combo_ks(n, 2)]


def _placebo_one(seed: int):
    W, M, k, base, ks = _G["W"], _G["M"], _G["k"], _G["base"], _G["ks"]
    try:
        g = shifted_gates(M["g"], ks[int(seed)])
        kw = T2.tbh_over(W["bear"]["US"], gated(M["on_b"], g, USE[k]), M["fb"])
        tot = 0.0
        for e in L6.ERAS:
            c = L6.run(W, e, **kw)["calmar"]
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
    W = L6.load()
    M = inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = overs(W["bear"]["US"], M["fb"], M["on_b"], M["g"])[k]
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["g"]["spx_down"]))
    ks = placebo_ks(k, n)
    _G.update({"W": W, "M": M, "k": k, "base": base, "ks": ks})
    seeds = list(range(R6.PLACEBO_N))
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
    s2 = R6.stage2(stat, vals)
    vd = R6.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "kind": KIND[k], "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat,
           "stage1_stat": s1["sum"], "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 2 轮 第二关：{k} vs 400 次新条件循环平移（{KIND[k]}；B2 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B2 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第二段第 2 轮：BCS / BCM / BCF（BCU 的债券只在真的在避险时拿）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
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
