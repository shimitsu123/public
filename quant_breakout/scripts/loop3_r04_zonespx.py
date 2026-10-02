"""loop3_r04_zonespx.py — 第三个研究循环第 4 轮：「S&P 跌破 250 日线（还没到熊）的警戒区里，核心换成 S&P500」ZSP
（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 6 / 20）。

循环的规则：scripts/research_loop3.py（第二关按类别；本轮 kind = "signal"）；基准 B1：scripts/loop2_common.py；
换指数的接法：第二个循环第 12 轮 scripts/loop2_r12_ndxtospx.py（NSX）原样，只把「换指数」的状态换掉。
为什么做这个（照实写）：
  - 第 1〜3 轮（核心换资产 ×2、个股层离场）第一关都不过。B1 的最深回撤多在「美股牛熊分界还没翻熊」时（本会话另一个只读检查，只看 B1 的状态）：
    J 2020-02〜03、2024-12〜2025-04 分界都是到底才翻；Z 2006 纳指单独的下跌。B1 的分界 = S&P500 250 日线 ±3%、连续 5 天（var/bullbear.json）：
    跌破 250 日线但还没到 −3% 的这段「警戒区」里，B1 照样 100% 拿纳指（β 比 S&P 高约 1.2〜1.3 倍）。
  - ZSP：警戒区里核心换成 S&P500（仓位不变、只换同类资产；纳指 → S&P = 同样 100% 美国股票、β 低）。
    第二个循环 NSX（纳指自己转熊、S&P 还是牛 → S&P）第一关不过（S1 恰好 +0.030、S2 E −0.021、S4、S7 −0.046）；本轮的切换键不同：
    S&P 自己跌破 250 日线（还没到熊）。选题来自本会话另一个只读检查（它的整体判断：剩下的题都是小概率，这一个约 6%）。
  - 看过 NSX / RXC / RXH、core_switch_study 的 F、2026-09 时点研究 T10（同一个警戒区里减半）之后设计 → 事后，S7 适用。
    家族「核心·指数选择」本循环 1 / 3。ID 是新的（第一 / 第二个循环没用过）。
做法 ZSP（参数沿用分界本身：250 日、连续 5 天，只把 ±3% 换成 0% → 没有学出来的参数，S6 不适用；不改个股买卖 → S5 不适用）：
  - 警戒区 Z = 现行检测器 qbreak.bullbear.ma_band 用 L = 250、b = 0、k = 5 套在同一条 S&P500 收盘（美国日期）上是「熊」，且 B1 的分界（b = 3%）不是熊
    （= 连续 5 天收在 250 日线下面开始、连续 5 天收在上面结束；分界翻熊之后同 B1 = 现金）。美国 d 日收盘 → 日本 d+1 开盘（同 B1）。
  - 核心：Z → FJE 对冲中拿 2563（S&P500 对冲版），否则 1655（S&P500）；其余同 B1（loop2_r12_ndxtospx.nsx_over 原样，四只 follow、最多一只不是熊）。
    1655 / 2563 的合成价、费用沿用 NSX（已登记、已核对；qbreak/fees.py 已有两只）。
第一关：research_loop3.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 ZSP − B1 的 Calmar 差；
  口径 = NSX 的 old_core（日元计、FRED 汇率、前一天收盘的状态决定当天、换仓按换掉的比例扣 0.1%），B1 = 第 8 轮 R8.old_core）。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "signal"，形状预定 = NSX 登记时的同一形状 ——「换指数」标记在 2000-01-03〜2026-09-30 里
  S&P 牛（B1 分界）的美国交易日串上整体循环平移 k（k ∈ [250, N − 250]，research_loop3.shift_ks 同一组种子；天数与每段长短不变），细节在那时写定。
接线核对（登记前，不看 ZSP 的收益）：① 警戒区全程 = False → J 的账户与 B1 逐项相同；② ZSP 在 J 里 1655 / 2563 的买卖笔数 > 0（只数笔数）。
规模核对（登记前，只看 B1 的状态）：见 sim_changes 的登记一节（--scale）。
只描述（不参与判定）：各年代警戒区的天数、段与其中对冲中的比例；每段纳指 / S&P500（合成、日元、不对冲）的涨跌；核心换仓笔数；每年收益差；1987〜2000 的段。
事前预期（照实写）：警戒区之后多半是 V 形反弹（2010-07、2012-06、2016-02、2018-12 之后、2019-06）→ 纳指涨得多 → 少赚；
  之后转熊的（2000-10、2008-01、2011-08、2015-08、2022-01、2025-03）→ S&P 跌得少 → 回撤浅一点；天数只占牛市的 2〜5% → 账户的差小，S1（+0.03）是难点。
  第一关约 15%、第二关约 25%。
运行：python scripts/loop3_r04_zonespx.py（第一关）；--scale（只数 B1 的状态）；--wiring（登记前的接线核对）。输出 var/out/loop3_r04_zonespx.md / .json。非投资建议。
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
import loop2_r12_ndxtospx as NS                                              # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop3 as R3                                                  # noqa: E402

ROUND = 4
IDS = ("ZSP",)
FAMILY = NS.FAMILY
POSTHOC = True
KIND = "signal"
ZONE = {"L": 250, "b": 0.0, "k": 5}                                          # 分界本身的 250 日 / 连续 5 天，±3% → 0%
OLD = NS.OLD
OUT = "loop3_r04_zonespx"


# ───────────────────────── 警戒区（纯函数，tests/test_loop3_r04.py） ─────────────────────────
def zone_bear(close: pd.Series, params: dict | None = None) -> pd.Series:
    """同一个检测器（qbreak.bullbear.ma_band）用 L = 250、b = 0、k = 5：True = 熊（连续 5 天收在 250 日线下）。"""
    from qbreak.bullbear import BEAR, Detector
    c = close.dropna()
    return pd.Series(np.asarray(Detector("ma_band", dict(params or ZONE)).states(c)) == BEAR, index=c.index)


def zone_state(zbear: pd.Series, us_bear: pd.Series) -> pd.Series:
    """警戒区 = 0% 线是熊 且 B1 的分界不是熊（两个序列在日期并集上各自向后填，之前没有值 = False）。"""
    z, b, idx = N8.on_union(zbear, us_bear)
    return pd.Series(z & ~b, index=idx)


# ───────────────────────── 只描述 ─────────────────────────
def describe(W: dict, e: str, sw: pd.Series, uni: pd.Series, n_core: tuple[int, int]) -> dict:
    d = NS.describe(W, e, sw, uni, n_core)
    a, b = W["ctx"][e]["windows"][e]
    bull = ~W["bear"]["US"].astype(bool)
    m = (bull.index >= pd.Timestamp(a)) & ((bull.index < pd.Timestamp(b)) if b else (bull.index <= pd.Timestamp(L2.J_END)))
    nb = int(bull[m].sum())
    d["bull_days"] = nb
    d["zone_pct_of_bull"] = round(d["switch_days"] / nb * 100, 1) if nb else None
    d["core_trades"] = {"B1": n_core[0], "ZSP": n_core[1]}
    return d


def scale(W: dict, sw: pd.Series) -> dict:
    out = {}
    bull = ~W["bear"]["US"].astype(bool)
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        m = (sw.index >= pd.Timestamp(a)) & ((sw.index < pd.Timestamp(b)) if b else (sw.index <= pd.Timestamp(L2.J_END)))
        mb = (bull.index >= pd.Timestamp(a)) & ((bull.index < pd.Timestamp(b)) if b else (bull.index <= pd.Timestamp(L2.J_END)))
        nz, nb = int(sw[m].astype(bool).sum()), int(bull[mb].sum())
        out[e] = {"zone_days": nz, "bull_days": nb, "pct_of_bull": round(nz / nb * 100, 1) if nb else None,
                  "segments": len(N8.segments(sw, a, b or L2.J_END))}
    m = (sw.index >= pd.Timestamp(OLD[0])) & (sw.index <= pd.Timestamp(OLD[1]))
    out["1987-2000"] = {"zone_days": int(sw[m].astype(bool).sum()), "segments": len(N8.segments(sw, *OLD))}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r04_zonespx.py", "scripts/loop2_r12_ndxtospx.py",
                                 "scripts/loop2_r08_ndrhedged.py", "scripts/loop_r08_ndxreentry.py", "scripts/loop2_r05_ddbrake.py",
                                 "scripts/loop2_common.py", "scripts/research_loop3.py", "scripts/candle_portfolio.py", "qbreak/fees.py",
                                 "qbreak/bullbear.py", "scripts/loop2_r02_bondrefuge.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def inputs(W: dict):
    _, _, uni = L2.fje_states(W)
    sw = zone_state(zone_bear(W["inp"]["spx"]["Close"]), W["bear"]["US"])
    return uni, sw


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    uni, sw = inputs(W)
    ov = NS.nsx_over(W, sw, uni, NS.hedged_spx_frame(W["inp"]))
    reg = R3.load_state().get("baseline") or {}
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
    old = {"B1": R8.old_core(W, uni, W["bear"]["US"]), "ZSP": NS.old_core(W, uni, W["bear"]["US"], sw),
           "segments": N8.segments(sw, *OLD)}
    unseen = None if old["B1"]["calmar"] is None or old["ZSP"]["calmar"] is None else old["ZSP"]["calmar"] - old["B1"]["calmar"]
    s1 = {"ZSP": R3.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty, "base": base,
           "cand": {"ZSP": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["ZSP"]
    ph = s1["posthoc"]
    L = [f"# 第三个研究循环第 4 轮：S&P 跌破 250 日线（还没到熊）的警戒区里核心换成 S&P500 ZSP（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r04_zonespx.py 开头）", "",
         f"- **ZSP：{'第一关全过 → 另行登记第二关（警戒区标记在 S&P 牛的日子上循环平移）' if s1['ok'] else R3.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | ZSP（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['ZSP'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        sg = "、".join(f"{m['from']}〜{m['to']}（{m['days']} 天；纳指 {m['ndx']:+.1f}% / S&P {m['spx']:+.1f}%）" for m in d["moves"]) or "无"
        L.append(f"- {e}：警戒区 {d['switch_days']} 天（牛市日子的 {_f(d['zone_pct_of_bull'], '{:.1f}')}%；其中对冲中 "
                 f"{_f(d['switch_hedged_pct'], '{:.1f}')}%；{sg}）；核心换仓 B1 {d['core_trades']['B1']} → ZSP {d['core_trades']['ZSP']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["ZSP"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（ZSP − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o["segments"]) or "无"
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；ZSP {oc(o['ZSP'])}（警戒区 {sg}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数 B1 的状态（警戒区的天数、占牛市的比例、段数；不跑 ZSP、不看收益）。"""
    W = L2.load()
    _, sw = inputs(W)
    print(json.dumps(scale(W, sw), ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 警戒区全程 = False → 账户与 B1 逐项相同；② ZSP 的 1655 / 2563 买卖笔数 > 0（只数笔数，不看收益）。"""
    W = L2.load()
    uni, sw = inputs(W)
    hspx = NS.hedged_spx_frame(W["inp"])
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    rn = L2.run(W, "J", **NS.nsx_over(W, pd.Series(False, index=sw.index), uni, hspx))
    same = all(rb.get(x) == rn.get(x) for x in keys)
    L2.run(W, "J", **NS.nsx_over(W, sw, uni, hspx))
    import loop2_r02_bondrefuge as T2
    ct = T2.core_trades("J", W)                                              # 按 ETF 分的核心换仓笔数
    n_spx = int(ct.get(NS.SPX_T, 0) + ct.get(NS.SPH_T, 0))
    print(json.dumps({"never_same_as_b1": same, "zsp_spx_trades_J": n_spx}, ensure_ascii=False))
    return 0 if same and n_spx > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 4 轮：ZSP（警戒区里核心换成 S&P500）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数 B1 的状态（不跑 ZSP）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看 ZSP 的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
