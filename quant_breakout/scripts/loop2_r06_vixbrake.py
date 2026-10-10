"""loop2_r06_vixbrake.py — 第二个研究循环第 6 轮：「恐慌指数刹车」VXB（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 6 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py。
为什么挑这个题（照实写）：
  - B1 自己的诊断（选题前看过，只有 B1、没有候选；scratch 不入库）：每个年代最深的三次回撤几乎都是「美股牛熊分界还是牛」时核心（纳指）的下跌，
    个股层贡献很小 —— Z 2006-04〜07 −14.71%（美股熊 0%）、E 2010-04〜2012-06 −19.70%（熊 34%）、J 2020-02〜03 −26.97%、2025-01〜04 −24.49%、
    2022-01〜03 −19.34%（熊 0〜7%）。第 5 轮 DDB（账户跌 10% 就减半）在 J 有用（回撤浅 5.5 pp），但 Z / E 的 10% 回调里来回刹车吃亏。
  - 要的是只在「恐慌」时才动的信号：VIX（S&P 500 隐含波动率）收盘 ≥ 30 在 2004〜2006（Z 的牛市）一次都没有，所以 Z 不受影响；
    E / J 的牛市里只在 2007-08 / 11、2010-05〜06、2018-02、2020、2022、2024-08、2025-04 这几段（一般知识，没算过这条规则的结果）。
  - 以前做过的（不重复）：2026-09-25 择时研究 T4「趋势 或 压力态（VIX ≥ 30 且信用利差 20 日 +0.3 pt）→ 全部离场」在 2006〜2026 输在 V 形反弹里踏空
    （1655 核心）。这一轮只看 VIX、只减一半、回落到 25 以下才恢复 —— 看过 T4 与第 5 轮之后设计 → 按事后处理，S7 适用。
    家族「风险层·恐慌指数刹车」1 / 3。
做法 VXB（参数事先写定、是常用的约定值、没调 → S6 不适用；不改个股买卖 → S5 不适用）：
  - VIX：yfinance ^VIX 美国交易日收盘（1990-01 起；之前没有 = 不刹）。收盘 ≥ 30 → 刹车开；收盘 < 25 → 刹车关；之间 → 保持前一天的状态（起点 关）。
  - 刹车开 → 核心 ETF（2845 / 1545，FJE 照旧决定是哪一只）的目标 × 0.5、另一半留现金（引擎 MixEngine.EXTRA_EXPO：B1 的两个键 US_UH / US_HG）；
    与美股牛熊分界同一个时点（美国 d 日收盘 → 日本 d+1 开盘成交）；美股熊时核心本来就是现金（刹车不起作用）。个股层、判断层、费用全部同 B1。
  - 接线检查（登记前跑过，见 sim_changes 登记一节）：刹车永远不开 = B1（三个年代与 1987〜2000 只有核心）。
第一关：research_loop2.stage1（posthoc = 1987〜2000 只有核心 VXB − B1 的 Calmar 差；口径同第 5 轮 old_core：前一天收盘决定当天、换仓扣 0.1% × 换的比例）。
只描述（不参与判定）：每个年代美股牛的日子里刹车的比例、刹车段数与最长几段、核心换仓笔数、每年收益差。
第二关（第一关全过才做）：另行登记（提交）后只运行一次，「同样多、同样形状的随机改动」那时写定。
事前预期（照实写）：Z 不变（0）；J 2020-02〜03 与 2025-04 少亏、2018-02 / 2020-06 / 2020-10 / 2021-01 / 2024-08 这些 V 形里少赚；E 2010-05〜07 少亏、
  2007 年两次少赚 → 第一关约 30%（S4 的两半与 E 最难说）、第二关约 35%，「更好候选」约 10%。
运行：python scripts/loop2_r06_vixbrake.py（第一关）。输出 var/out/loop2_r06_vixbrake.md / .json。非投资建议。
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
import loop2_r05_ddbrake as R5                                               # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 6
IDS = ("VXB",)
FAMILY = "风险层·恐慌指数刹车"
POSTHOC = True
ON, OFF, MULT = 30.0, 25.0, 0.5
VIX_START = "1990-01-01"
OLD = R5.OLD
OUT = "loop2_r06_vixbrake"


# ───────────────────────── 规则（纯函数，tests/test_loop2_r06.py） ─────────────────────────
def load_vix() -> pd.Series:
    from bullbear_study import load
    return load("^VIX", VIX_START)["Close"].dropna()


def brake_state(vix: pd.Series, on: float = ON, off: float = OFF) -> pd.Series:
    """收盘 ≥ on → 开；< off → 关；之间保持前一天（起点 关）。按 vix 的日期（美国交易日）。"""
    v = vix.dropna().to_numpy(float)
    out, s = np.zeros(len(v), dtype=bool), False
    for k, x in enumerate(v):
        if x >= on:
            s = True
        elif x < off:
            s = False
        out[k] = s
    return pd.Series(out, index=vix.dropna().index)


def multiplier(state: pd.Series, mult: float = MULT) -> pd.Series:
    return pd.Series(np.where(state.to_numpy(bool), mult, 1.0), index=state.index, dtype=float)


def vxb_over(state: pd.Series, mult: float = MULT) -> dict:
    """B1 的两个核心键（1545 → US_UH、2845 → US_HG）在刹车开的日子 × mult（引擎 EXTRA_EXPO；没写的日子 = 1）。"""
    import loop_r04_yensurge as Y
    m = multiplier(state, mult)
    return {"extra_expo": {Y.UH_KEY: m, Y.HG_KEY: m}}


def old_core(W: dict, uni: pd.Series, state: pd.Series | None) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第 5 轮 old_core 同一个合成价与口径）；state = 刹车（None = B1），前一天收盘的状态决定当天。"""
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
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    ru = unh.reindex(idx).pct_change().fillna(0.0).to_numpy()
    rh = ff(hed).pct_change().fillna(0.0).to_numpy()
    bear = (ff(W["bear"]["US"]).fillna(0.0) > 0.5).to_numpy()
    hdg = (ff(uni).fillna(0.0) > 0.5).to_numpy()
    on = (ff(state).fillna(0.0) > 0.5).to_numpy() if state is not None else np.zeros(len(idx), dtype=bool)
    n = len(idx)
    eq = np.ones(n)
    pu0 = ph0 = 0.0
    for t in range(1, n):
        x = (0.0 if bear[t - 1] else 1.0) * (MULT if on[t - 1] else 1.0)
        pu, ph = (0.0, x) if hdg[t - 1] else (x, 0.0)
        turn = abs(pu - pu0) + abs(ph - ph0)
        eq[t] = eq[t - 1] * (1 + pu * ru[t] + ph * rh[t] - turn * HW.SWITCH_COST / 100)
        pu0, ph0 = pu, ph
    out = EI.curve_stats(pd.Series(eq, index=idx))
    bull = ~bear
    out["brake_pct_of_bull"] = round(float(on[bull].mean() * 100), 1) if bull.any() else None
    return out


def describe(W: dict, e: str, state: pd.Series, n_core: tuple[int, int]) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    s = state[(state.index >= pd.Timestamp(a)) & ((state.index < pd.Timestamp(b)) if b else True)]
    bus = W["bear"]["US"].astype(float).reindex(s.index.union(W["bear"]["US"].index)).ffill().reindex(s.index).fillna(0.0) > 0.5
    eff = multiplier(s & ~bus)                                                # 起作用的 = 刹车开且美股牛
    seg = R5.segments(eff)
    nb = int((~bus).sum())
    return {"bull_days": nb, "brake_pct_of_bull": round(float((s & ~bus).sum() / nb * 100), 1) if nb else None,
            "n_segments": len(seg), "longest": sorted(seg, key=lambda x: -x[2])[:6], "core_trades": {"B1": n_core[0], "VXB": n_core[1]}}


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r06_vixbrake.py", "scripts/loop2_r05_ddbrake.py",
                                 "scripts/loop2_common.py", "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    state = brake_state(load_vix())
    ov = vxb_over(state)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, state, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, None), "VXB": old_core(W, uni, state)}
    unseen = None if old["B1"]["calmar"] is None or old["VXB"]["calmar"] is None else old["VXB"]["calmar"] - old["B1"]["calmar"]
    s1 = {"VXB": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "rule": {"on": ON, "off": OFF, "mult": MULT},
           "code": code, "dirty": dirty, "base": base, "cand": {"VXB": cand}, "stage1": s1, "drift": drift, "describe": desc,
           "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["VXB"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 6 轮：恐慌指数刹车 VXB（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r06_vixbrake.py 开头）", "",
         f"- **VXB（VIX 收盘 ≥ 30 → 核心 × 0.5，< 25 才恢复）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | VXB（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['VXB'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        lg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in d["longest"]) or "无"
        L.append(f"- {e}：美股牛的日子里刹车 {_f(d['brake_pct_of_bull'], '{:.1f}')}%（{d['n_segments']} 段；最长的几段 {lg}）；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → VXB {d['core_trades']['VXB']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["VXB"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VXB − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心；VIX 1990 年起）：B1 {oc(o['B1'])}；VXB {oc(o['VXB'])}（美股牛的日子里刹车 {o['VXB']['brake_pct_of_bull']}%）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 6 轮：VXB 恐慌指数刹车")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
