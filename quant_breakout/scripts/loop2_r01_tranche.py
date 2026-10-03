"""loop2_r01_tranche.py — 第二个研究循环第 1 轮：「核心分批切换」TR3（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 1 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py。
为什么挑这个题（照实写）：选题前只看过 B1 本身的诊断（scratch，不入库；没有看过任何候选）：
  E 的最大回撤 −19.70%（2010-04〜2012-06）期间 1545 合成价本身 +1.8%，只有核心（不开个股）的账户 2010 −1.5%、2011 −9.2%
  → 主要是美股牛熊分界来回翻转（whipsaw）与换仓的成本；J 的两次最深回撤（2020-02〜03 −27.0%、2025-01〜04 −24.5%）是急跌，翻熊时已近谷底。
  用户把执行层列为优先的层；这一轮不改分界本身、不加新信号，只改「翻转之后怎么换」：分三批换，少一点「全卖在低点、全买在高点」。
  第一个循环没有做过（VT20 是按波动率持续调仓位，CPX / NDA / NDR 改的是翻转条件）；研究总图里也没有分批切换。
做法（参数事先写定、没调 → S6 不适用；不改个股买卖 → S5 不适用；不是事后组合 → S7 不适用）：
  TR3：核心的持仓比例 E（0〜1）跟着 B1 同一个美股牛熊分界（S&P500 250 日线 ±3%、连续 5 天）分三批走 ——
    分界翻转的那个美国交易日 E 向新的目标（牛 = 1、熊 = 0）走 1/3，之后每 5 个美国交易日再走 1/3，到目标为止；
    中途分界又翻回去 → 从当时的 E 向新的目标走，节奏从那一天重新算；
    E = 0 → 核心现金（= B1 的熊）；0 < E < 1 → 核心目标 × E，拿哪一只照 B1（FJE 对冲中 → 2845、否则 1545）。
  接线：一步到位（n = 1）时必须与 B1 完全相同（tests/test_loop2_r01.py；登记前跑过一次「n = 1 vs B1」的接线检查）。
第一关：research_loop2.stage1（trade = None、lenses = None、posthoc = None）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次，「同样多、同样形状的随机改动」在那时写定。
只描述（不参与判定）：各年代分界翻转次数、处在分批中的美国交易日比例、核心换仓笔数；没看过的 1987〜2000 只有核心（日元计纳指，
  FJE 与牛熊分界同一做法，fxhedge_study.core_only 同一个口径：前一天收盘的状态决定当天，每次调整扣 0.1%）B1 开关 vs TR3。
事前预期（照实写）：E 的来回翻转可能少亏几个百分点（回撤变浅）；真熊市（2008、2022）全部离场晚 10 个交易日多亏一点；
  急跌（2020、2025）的最大回撤在翻转之前已经发生 → J 几乎不变；三个年代合计在 ±0.05 以内的可能最大，第一关约 15%，「更好候选」约 2%。
运行：python scripts/loop2_r01_tranche.py（第一关）。输出 var/out/loop2_r01_tranche.md / .json。非投资建议。
"""
from __future__ import annotations

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
import research_loop2 as R2                                                  # noqa: E402

ROUND = 1
IDS = ("TR3",)
FAMILY = "执行·核心分批切换"
N_STEPS, EVERY = 3, 5
OLD = ("1987-01-01", "2000-12-31")
OUT = "loop2_r01_tranche"


# ───────────────────────── 规则（纯函数，tests/test_loop2_r01.py） ─────────────────────────
def tranche(us_bear: pd.Series, n: int = N_STEPS, every: int = EVERY) -> pd.Series:
    """美股熊（True）序列（美国交易日）→ 核心持仓比例 E = k / n（k = 0〜n）：翻转那天走一步，之后每 every 天走一步，到目标为止。"""
    b = us_bear.astype(bool).to_numpy()
    out = np.empty(len(b))
    if not len(b):
        return pd.Series(out, index=us_bear.index)
    tgt = 0 if b[0] else n
    k, last = tgt, 0
    for i in range(len(b)):
        t = 0 if b[i] else n
        if t != tgt:                                                         # 翻转：当天走第一步，节奏从这天算
            tgt, last = t, i
            k += 1 if tgt > k else -1
        elif k != tgt and (i - last) % every == 0:
            k += 1 if tgt > k else -1
        out[i] = k / n
    return pd.Series(out, index=us_bear.index)


def out_of_core(e: pd.Series) -> pd.Series:
    """E = 0 → 核心全现金（当作熊）。"""
    return pd.Series(e.to_numpy(float) <= 1e-9, index=e.index)


def tranche_over(state: pd.Series, e: pd.Series) -> dict:
    """在 B1 上改：FJE 的两个键的「熊」换成「E = 0」，两只的持仓比例都乘 E（loop2_common.run 按键合并 extra_bear）。"""
    import loop_r04_yensurge as Y
    o = out_of_core(e)
    st = state.astype(bool)
    return {"extra_bear": {Y.UH_KEY: Y.or_series(o, st), Y.HG_KEY: Y.or_series(o, ~st)},
            "extra_expo": {Y.UH_KEY: e, Y.HG_KEY: e}}


def flips(us_bear: pd.Series) -> int:
    v = us_bear.astype(bool).to_numpy()
    return int((v[1:] != v[:-1]).sum())


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def core_trades(e: str, W: dict) -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    return int(sum(1 for x in eng.st.core_trades if x[0] >= a and (b is None or x[0] < b)))


def describe(W: dict, e: str, ex: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    bus = W["bear"]["US"]
    m = (bus.index >= pd.Timestamp(a)) & ((bus.index < pd.Timestamp(b)) if b else True)
    x = ex[m]
    return {"flips": flips(bus[m]), "in_transit_pct": round(float(((x > 1e-9) & (x < 1 - 1e-9)).mean() * 100), 2) if len(x) else None}


def old_core(W: dict, state: pd.Series, n: int) -> dict:
    """只描述：1987〜2000 只有核心（日元计纳指；第 15 轮 old_core 同一个合成价），持仓比例 E（n = 1 即 B1 的开关）。
    fxhedge_study.core_only 的口径：前一天收盘的状态决定当天，E 每变一次扣 0.1% × 变的比例。"""
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
    unh, hed = unh.reindex(idx), hed.reindex(idx).ffill()
    ex = tranche(W["bear"]["US"], n=n).reindex(idx, method="ffill").fillna(0.0)
    h = state.astype(float).reindex(idx.union(state.index)).ffill().reindex(idx).fillna(0.0) > 0.5
    exl, hl = ex.shift(1).fillna(0.0), h.shift(1).fillna(False)
    ru, rh = unh.pct_change().fillna(0.0), hed.pct_change().fillna(0.0)
    ret = exl * np.where(hl, rh, ru)
    pos_u, pos_h = exl * (~hl), exl * hl
    turn = (pos_u.diff().abs().fillna(pos_u.abs()) + pos_h.diff().abs().fillna(pos_h.abs()))
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    return EI.curve_stats(eq)


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r01_tranche.py", "scripts/loop2_common.py",
                                 "scripts/research_loop2.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    ex = tranche(W["bear"]["US"])
    ov = tranche_over(uni, ex)
    reg = R2.load_state().get("baseline") or {}
    base, cand, ctr, desc = {}, {"TR3": {}}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        ctr[e] = {"B1": core_trades(e, W)}
        base[e] = _acct(rb)
        rc = L2.run(W, e, **ov)
        ctr[e]["TR3"] = core_trades(e, W)
        cand["TR3"][e] = _acct(rc)
        desc[e] = describe(W, e, ex)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"TR3": R2.stage1(cand["TR3"], base)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    old = {"B1": old_core(W, uni, 1), "TR3": old_core(W, uni, N_STEPS)}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1,
           "drift": drift, "core_trades": ctr, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["TR3"]
    L = [f"# 第二个研究循环第 1 轮：核心分批切换 TR3（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r01_tranche.py 开头）", "",
         f"- **TR3（美股牛熊分界翻转后核心分三批、每 5 个美国交易日走 1/3）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | TR3（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TR3'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：分界翻转 {d['flips']} 次、处在分批中的美国交易日 {_f(d['in_transit_pct'], '{:.1f}')}%；核心换仓 B1 {c['B1']} → TR3 {c['TR3']} 笔")
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心、日元计纳指 + FJE）：B1 的开关 {oc(o['B1'])}；TR3 {oc(o['TR3'])}")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(stage_one())
