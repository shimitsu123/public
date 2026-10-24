"""loop2_r12_ndxtospx.py — 第二个研究循环第 12 轮：「纳指自己转熊、S&P 还是牛时，核心换成 S&P500」NSX（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 12 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py。
为什么挑这个题（照实写）：
  - B1 的最深回撤多是美股牛市里（S&P 的牛熊分界还没翻）核心纳指自己的下跌（本循环选题时的 B1 诊断，scratch，不入库）：Z 2006-04-21〜07-24 −14.71%、
    J 2022-01-04〜03-09 −19.34%、2025-01-24〜04-09 −24.49%。第 5〜11 轮「降低仓位」的核心择时第二关都输给随机时点 —— 随机的减仓碰上崩盘就赢得很多
    （安慰剂肥尾）；「仓位不变、换一只同类资产」的改动（第一个循环的 FJE、本循环的 TBJ / TBU）随机对照不肥尾，第二关才有机会。
    汇率对冲家族不再加、熊市避险资产家族 3 / 3 用完 → 剩下的同类改动是「拿哪个指数」：纳指 → S&P500（同样 100% 美国股票、β 低、科技以外的部分多）。
  - 以前做过的（不重复，结果照实写）：2026-09-27 双动量（美 / 日哪个强拿哪个，月度）；2026-09-30 core_switch_study 的 F「择强指数（月末 252 天
    纳指 vs S&P500）」—— 账户（旧基准 Q）Z 0.930 → 1.290、E 0.585 → 0.516、J 0.564 → 0.563，A「一直 S&P500」Z 1.766、E 0.343、J 0.427；
    2026-10-01 风险参数 × 方向 R2（126 日相对动量，含现金）—— 相对强弱的切换「慢半拍」。这一轮不用相对强弱：切换键是纳指**自己的**牛熊
    （模拟盘同一个检测器、同一组参数，= 第 8 轮 NDRH 用的 ndx_bear），只在「纳指自己已转熊、S&P 还没转熊」的那几段换成 S&P500，没有新参数。
  → 设计是在看过上面这些结果（F / A 的 Z 大幅更好、E 变差）与 NDRH 的纳指熊之后做的 → 按事后处理：S7 适用。家族「核心·指数选择」1 / 3。
做法 NSX（没有新参数 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 纳指熊 N = 现行牛熊检测器（var/bullbear.json：250 日线 ±3%、连续 5 天）用在 ^NDX（美元）上（loop_r08_ndxreentry.ndx_bear）；美股熊 B = B1 的（S&P500）。
  - 换指数 S = N 且 不是 B。美国 d 日收盘 → 日本 d+1 开盘（同 B1）。
  - 核心（引擎 core_mode = "follow"，四只里最多一只不是「熊」）：B → 现金（同 B1）；不是 B、也不是 S → 同 B1（FJE 对冲中 → 2845，否则 1545）；
    S → FJE 对冲中 → 2563（S&P500 对冲版），否则 1655（S&P500）。个股层、判断层、FJE 的「对冲中」、费用的口径全部同 B1。
  - 合成价（全程同一做法，东证 d 日 = 前一个美国收盘）：1655 = equity_idle_study 的合成 1655（^SP500TR × USD/JPY − 信託報酬 0.066%）；
    2563 = 2845 同一做法（fxhedge_study.hedged_index：S&P500 本地总收益 + (日本 − 美国 短期利率)/252）− 信託報酬 税込 0.077%（BlackRock 官网，
    2026-10-01 基准）− 跟踪差 0.16%（登记前核对：这样合成的 2563 比真实 2563（复权）在 2021〜2025 逐年平均高 0.16 pp → 扣掉；
    合成 1655 比真实 1655 在 2018〜2025 平均低 0.21 pp → 不调，偏保守），价格水平按 2026-08-31 的真实收盘 ¥406.3（Yahoo）。
  - 费用表：qbreak/fees.py 加 2563.T（一手 10 口：BlackRock 官网；滑点 0.05%：近 60 个交易日立会内日均成交额约 1.1〜1.6 亿円，Yahoo 到 2026-10-01）；
    1655.T 已有（一手 10 口、滑点 0.02%）。只研究用，模拟盘 / 执行器不动。
  - 接线检查（登记前跑过，见 sim_changes 登记一节）：S 永远不成立 = B1（三个年代与 1987〜2000 只有核心的数字一致）。
第一关：research_loop2.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 NSX − B1 的 Calmar 差）。
  1987〜2000 只有核心：第 5 / 8 轮 old_core 同一个口径（日元计、FRED 汇率；前一天收盘的状态决定当天；换仓按换掉的比例扣 0.1%）；四只的合成价：
  纳指 / 纳指对冲（同第 8 轮）、S&P500 = spx_tr（1988 以前 ^GSPC + 年 3.5% 股息）× USD/JPY − 0.066%、S&P500 对冲 = hedged_index(spx_tr − 0.237%)。
第二关（第一关全过才做）：另行登记（提交）后只运行一次；形状预定 =「换指数」标记在 2000-01-03〜2026-09-30 里 S&P 牛的美国交易日串上整体循环平移
  （天数与每段长短不变、只落在 S&P 牛的日子里），细节在那时写定。
只描述（不参与判定）：各年代换指数的天数、段、其中对冲中的比例；每段纳指 / S&P500（合成，日元，不对冲）的涨跌；核心换仓笔数；每年收益差；
  1987〜2000 的换指数段。
事前预期（照实写，按一般的市场历史估计，不是这个项目的结果）：Z 2006-05〜10 纳指自己转熊、S&P 没转 → 少吃纳指 2006 年下跌的后一段，
  Z 回撤可能浅几个 pp；2004 下半年纳指 V 形反弹时拿着 S&P → 少赚；E 2012-11〜2013（苹果领跌）大致持平、2010 / 2011 / 2015〜16 两边差不多同时转熊 → 小；
  J 2018-11、2022-01〜03、2025-03 只有几周、小幅为正；J 最大的回撤 2020-03 两边同时翻 → 不变。1987〜2000：1996-07 纳指 V 形反弹 → 负，
  2000 下半年纳指先转熊 → 正。第一关约 30%（S2 的 E、S4、S7 是关键）、第二关约 30%，「更好候选」约 9%。
运行：python scripts/loop2_r12_ndxtospx.py（第一关）。输出 var/out/loop2_r12_ndxtospx.md / .json。非投资建议。
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
import loop2_r08_ndrhedged as R8                                             # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 12
IDS = ("NSX",)
FAMILY = "核心·指数选择"
POSTHOC = True                                                              # 看过 core_switch_study 的 F / A 与 NDRH 之后设计 → 按事后处理（S7 适用）
OLD = R5.OLD
SPX_T, SPH_T = "1655.T", "2563.T"
SU_KEY, SH_KEY = "US_SU", "US_SH"
SU_FEE = 0.066                                                              # 年 %：1655 信託報酬（equity_idle_study.FEE 同值）
SH_FEE, SH_BASIS = 0.077, 0.16                                              # 年 %：2563 信託報酬（税込）+ 合成相对真实 2563 的跟踪差
REF_DATE, SH_REF = "2026-08-31", 406.3                                      # 2563 的真实收盘（Yahoo）
OUT = "loop2_r12_ndxtospx"


# ───────────────────────── 状态与接法（tests/test_loop2_r12.py） ─────────────────────────
def switch_state(spx_bear: pd.Series, ndx_bear: pd.Series) -> pd.Series:
    """换指数 S = 纳指自己是熊 且 S&P 不是熊（两个序列在日期并集上各自向后填，之前没有值 = False）。"""
    s, n, idx = N8.on_union(spx_bear, ndx_bear)
    return pd.Series(n & ~s, index=idx)


def nsx_keys(bear: pd.Series, uni: pd.Series, sw: pd.Series) -> dict[str, pd.Series]:
    """四只核心的「熊」：1545 = B 或 对冲中 或 S；2845 = B 或 不对冲 或 S；1655 = B 或 对冲中 或 不是 S；2563 = B 或 不对冲 或 不是 S。
    B1 的两个键（fxh_over 同一个 or_series）原样再并上 S → S 永远不成立时 1545 / 2845 与 B1 完全相同、1655 / 2563 永远是熊。"""
    import loop_r04_yensurge as Y
    idx = bear.index.union(uni.index).union(sw.index)
    s = pd.Series(sw.astype(float).reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5, index=idx)
    uh, hg = Y.or_series(bear, uni), Y.or_series(bear, ~uni.astype(bool))
    return {Y.UH_KEY: Y.or_series(uh, s), Y.HG_KEY: Y.or_series(hg, s), SU_KEY: Y.or_series(uh, ~s), SH_KEY: Y.or_series(hg, ~s)}


def hedged_spx_frame(inp: dict) -> pd.DataFrame:
    """对冲版 S&P500 的日本交易日 K 线（只有收盘；loop_r04_yensurge.hedged_frame 同一做法，指数换成 S&P500 总收益、费用换成 2563 的）。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    from qbreak import factors
    us_r, jp_r = factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9)
    h = EI.grow(FX.hedged_index(EI.spx_tr(inp), us_r, jp_r), -(SH_FEE + SH_BASIS))
    days = inp["n225"].index[inp["n225"].index >= EI.START]
    c = EI.on_jp(h, None, days)
    c = c * (SH_REF / float(c.asof(pd.Timestamp(REF_DATE))))
    return EI.frame_close(c)


def nsx_over(W: dict, sw: pd.Series, uni: pd.Series, hspx: pd.DataFrame) -> dict:
    """B1 的接法（fxh_over）加两只 S&P500：core_mode = follow，四只的熊 = nsx_keys。"""
    import loop_r04_yensurge as Y
    xc = {**W["b1"]["extra_core"], SPX_T: W["assets"][SPX_T], SPH_T: hspx}
    return {"cfg_over": {"core": {"1545.T": 1.0, Y.HEDGE_T: 1.0, SPX_T: 1.0, SPH_T: 1.0},
                         "core_index": {"1545.T": Y.UH_KEY, Y.HEDGE_T: Y.HG_KEY, SPX_T: SU_KEY, SPH_T: SH_KEY}, "core_mode": "follow"},
            "extra_core": xc, "extra_bear": nsx_keys(W["bear"]["US"], uni, sw)}


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, uni: pd.Series, bear: pd.Series, sw: pd.Series) -> dict:
    """1987〜2000 只有核心：第 8 轮 old_core 同一个合成价与口径，多两只 S&P500（不对冲 / 对冲）；sw = 换指数（全 False = B1）。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    import halloween_study as HW
    from qbreak import factors
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    us_r, jp_r = factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9)

    def jpy(s: pd.Series) -> pd.Series:
        return (s * dex.reindex(s.index.union(dex.index)).ffill().reindex(s.index)).dropna()
    ntr, sptr = EI.ndx_tr(inp), EI.spx_tr(inp)
    nu = jpy(EI.grow(ntr, -EI.FEE["1545.T"]))
    nh = FX.hedged_index(EI.grow(ntr, -0.22), us_r, jp_r)
    su = jpy(EI.grow(sptr, -SU_FEE))
    sh = FX.hedged_index(EI.grow(sptr, -(SH_FEE + SH_BASIS)), us_r, jp_r)
    idx = nu.index[(nu.index >= pd.Timestamp(OLD[0])) & (nu.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    R = np.column_stack([nu.reindex(idx).pct_change().fillna(0.0).to_numpy(), ff(nh).pct_change().fillna(0.0).to_numpy(),
                         ff(su).pct_change().fillna(0.0).to_numpy(), ff(sh).pct_change().fillna(0.0).to_numpy()])
    b = (ff(bear).fillna(0.0) > 0.5).to_numpy()
    hdg = (ff(uni).fillna(0.0) > 0.5).to_numpy()
    s = (ff(sw).fillna(0.0) > 0.5).to_numpy()
    n = len(idx)
    eq = np.ones(n)
    w0 = np.zeros(4)
    for t in range(1, n):
        w = np.zeros(4)
        if not b[t - 1]:
            w[(2 if s[t - 1] else 0) + (1 if hdg[t - 1] else 0)] = 1.0
        turn = float(np.abs(w - w0).sum())
        eq[t] = eq[t - 1] * (1 + float(w @ R[t]) - turn * HW.SWITCH_COST / 100)
        w0 = w
    return EI.curve_stats(pd.Series(eq, index=idx))


# ───────────────────────── 只描述 ─────────────────────────
def seg_moves(W: dict, segs: list[tuple[str, str, int]]) -> list[dict]:
    """每段（美国日期）纳指 / S&P500 合成价（日元，不对冲）的涨跌 %：从段首的下一个东证日到段尾的下一个东证日（= 实际拿着的那段）。"""
    out = []
    pn, ps = W["assets"]["1545.T"]["Close"], W["assets"][SPX_T]["Close"]
    for a, b, k in segs:
        i0, i1 = pn.index.searchsorted(pd.Timestamp(a), side="right"), pn.index.searchsorted(pd.Timestamp(b), side="right")
        if i0 >= len(pn) or i1 >= len(pn):
            i1 = len(pn) - 1
        d0, d1 = pn.index[min(i0, len(pn) - 1)], pn.index[i1]
        out.append({"from": a, "to": b, "days": k, "ndx": round(float(pn[d1] / pn[d0] - 1) * 100, 1),
                    "spx": round(float(ps.asof(d1) / ps.asof(d0) - 1) * 100, 1)})
    return out


def describe(W: dict, e: str, sw: pd.Series, uni: pd.Series, n_core: tuple[int, int]) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    seg = N8.segments(sw, a, b or L2.J_END)
    m = (sw.index >= pd.Timestamp(a)) & ((sw.index < pd.Timestamp(b)) if b else (sw.index <= pd.Timestamp(L2.J_END)))
    r = sw[m].astype(bool)
    h = uni.astype(float).reindex(r.index.union(uni.index)).ffill().reindex(r.index).fillna(0.0) > 0.5
    return {"switch_days": int(r.sum()), "switch_hedged_pct": round(float(h[r].mean() * 100), 1) if r.any() else None,
            "segments": seg, "moves": seg_moves(W, seg), "core_trades": {"B1": n_core[0], "NSX": n_core[1]}}


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r12_ndxtospx.py", "scripts/loop2_r08_ndrhedged.py",
                                 "scripts/loop_r08_ndxreentry.py", "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py",
                                 "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    sw = switch_state(W["bear"]["US"], N8.ndx_bear(W["inp"]))
    ov = nsx_over(W, sw, uni, hedged_spx_frame(W["inp"]))
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, sw, uni, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": R8.old_core(W, uni, W["bear"]["US"]), "NSX": old_core(W, uni, W["bear"]["US"], sw),
           "segments": N8.segments(sw, *OLD)}
    unseen = None if old["B1"]["calmar"] is None or old["NSX"]["calmar"] is None else old["NSX"]["calmar"] - old["B1"]["calmar"]
    s1 = {"NSX": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"NSX": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["NSX"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 12 轮：纳指自己转熊、S&P 还是牛时核心换成 S&P500 NSX（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r12_ndxtospx.py 开头）", "",
         f"- **NSX：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | NSX（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['NSX'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        sg = "、".join(f"{m['from']}〜{m['to']}（{m['days']} 天；纳指 {m['ndx']:+.1f}% / S&P {m['spx']:+.1f}%）" for m in d["moves"]) or "无"
        L.append(f"- {e}：换指数 {d['switch_days']} 天（其中对冲中 {_f(d['switch_hedged_pct'], '{:.1f}')}%；{sg}）；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → NSX {d['core_trades']['NSX']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["NSX"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（NSX − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o["segments"]) or "无"
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；NSX {oc(o['NSX'])}（换指数 {sg}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 12 轮：NSX（纳指自己转熊、S&P 还是牛时核心换成 S&P500）")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
