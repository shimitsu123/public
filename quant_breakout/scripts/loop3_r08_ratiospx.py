"""loop3_r08_ratiospx.py — 第三个研究循环第 8 轮：纳指 / S&P500 比值转熊时核心换成 S&P500 —— RTX（只看比值）/ NZS（ZSP 的警戒区 ∩ 比值转熊）
（2026-10-02 登记；先提交后只运行一次；用掉 2 个做法 → 14 / 20；家族「核心·指数选择」本循环 2 / 3、3 / 3）。

循环的规则：scripts/research_loop3.py（第二关按类别；本轮两个都是 kind = "signal"）；基准 B1：scripts/loop2_common.py；
换指数的接法：第二个循环第 12 轮 NSX（scripts/loop2_r12_ndxtospx.nsx_over）原样，只把「换指数」的状态换掉（第 4 轮 ZSP 同一做法）。
题从哪里来（照实写）：第 6 轮之后同一会话另一个只读检查（只看 B1 的状态、不跑候选）列出的剩下的题；用户 2026-10-02「然后再继续现在提出的观点」。
  它的估计：两关都过的机会 NZS 约 1%（剩下的题里最好）、RTX ≤ 0.5%。
  - RTX：纳指相对 S&P500 转弱（比值自己的牛熊 = 熊）、S&P 还是牛 → 核心换成 S&P500。以前做过的相对强弱切换（照实写）：2026-09-30 core_switch_study 的 F
    「择强指数（月末 252 天纳指 vs S&P500）」账户（旧基准 Q）Z 0.930 → 1.290、E 0.585 → 0.516、J 0.564 → 0.563；第二个循环 NSX（纳指自己转熊）第一关不过
    （S1 +0.030、S2 E −0.021、S4、S7 −0.046）。本轮的切换键 = 比值自己的牛熊（现行检测器同一组参数），不是月末的 252 天比较。
  - NZS：第 4 轮 ZSP（S&P 跌破 250 日线、还没到熊的警戒区 → S&P500）第一关全过（+0.141，几乎全部来自 Z 2006 纳指单独下跌）、第二关第 96.8 百分位不过；
    NZS 只在警戒区里比值也转熊（纳指比 S&P 弱）时才换 → 看过 ZSP 的结果之后的改版 → 事后、方法上最不干净（照实写）。
  → 两个都是看过上面这些结果之后设计的 → 按事后处理：S7 适用。ID 是新的（第一 / 第二个循环、本循环第 1〜7 轮没用过）。
做法（没有新参数：比值用现行牛熊检测器同一组参数 —— var/bullbear.json 的 250 日线 ±3%、连续 5 天；S6 不适用；不改个股买卖 → S5 不适用）：
  - 比值 R = ^NDX 收盘 ÷ ^GSPC 收盘（同一个美国交易日，美元；1985-10 起）；R 熊 = equity_idle_study.t0_bear(R)（= B1 分界同一个检测器、同一组参数）。
  - RTX：换指数 = R 熊 且 B1 的分界不是熊（两个序列在日期并集上各自向后填）。
  - NZS：换指数 = ZSP 的警戒区（loop3_r04_zonespx.zone_state 原样）且 R 熊。
  - 换法：nsx_over 原样 —— 换指数时 FJE 对冲中 → 2563（S&P500 对冲版），否则 1655（S&P500）；不换时同 B1；美国 d 日收盘 → 日本 d+1 开盘；
    个股层、判断层、FJE、费用全部同 B1。
第一关：research_loop3.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 候选 − B1 的 Calmar 差；口径 = NSX / ZSP 的 old_core，
  B1 = 第二个循环第 8 轮 R8.old_core）。两个做法各自判定。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "signal"，形状预定 = ZSP 第二关同一形状 —— 换指数标记在 2000-01-03〜2026-09-30 里
  S&P 牛（B1 分界）的美国交易日串上整体循环平移 k（research_loop3.shift_ks 同一组种子；天数与每段长短不变），细节在那时写定。
接线核对（登记前，不看候选的收益）：① 换指数全程 False → J 的账户与 B1 逐项相同；② RTX / NZS 在 J 里 1655 / 2563 的买卖笔数 > 0（只数笔数）。
规模核对（登记前，只看状态）：各年代换指数的天数、占牛市日子的比例、段数；1987〜2000 的天数与段数（--scale）。
只描述（不参与判定）：同 ZSP —— 各年代换指数的天数、段与其中对冲中的比例；每段纳指 / S&P500（合成、日元、不对冲）的涨跌；核心换仓笔数；每年收益差；
  1987〜2000 只有核心的段。
事前预期（照实写，按一般的市场历史与上面那些结果估计，不是这一轮的结果）：
  - RTX：纳指相对转弱的段长（几个月到一两年）→ 与 F 类似，Z（2004〜2006 纳指落后）为正、E（2010〜2016 纳指领先居多，转弱的几段之后又 V 形）可能为负、
    J 2021-11〜2022、2024-07〜2025 有正有负 → S2（E ≥ −0.02）是难点；第一关约 10%、第二关约 20%。
  - NZS：ZSP 警戒区里的一部分 → Z 2006 的那一段（纳指比 S&P 弱）大概率保留，纳指领先的 V 形反弹段去掉 → 第一关约 30%；第二关的随机平移对少数几段很敏感
    （ZSP 是第 96.8 百分位）→ 约 5〜10%。两个合起来「更好候选」约 1〜3%；即使通过也是事后 → 只提议（前向记录 / 采用由用户决定），不改模拟盘。
运行：python scripts/loop3_r08_ratiospx.py（第一关）；--scale（只数状态）；--wiring（登记前的接线核对）。输出 var/out/loop3_r08_ratiospx.md / .json。
非投资建议。
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
import loop3_r04_zonespx as ZS                                               # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop3 as R3                                                  # noqa: E402

ROUND = 8
IDS = ("RTX", "NZS")
FAMILY = NS.FAMILY
POSTHOC = True
KIND = "signal"
OLD = NS.OLD
OUT = "loop3_r08_ratiospx"


# ───────────────────────── 状态（纯函数，tests/test_loop3_r08.py） ─────────────────────────
def ratio(ndx: pd.Series, spx: pd.Series) -> pd.Series:
    """纳指 ÷ S&P500（同一个美国交易日都有收盘的日子；美元）。"""
    a, b = ndx.astype(float).dropna(), spx.astype(float).dropna()
    idx = a.index.intersection(b.index)
    return (a.reindex(idx) / b.reindex(idx)).dropna()


def ratio_bear(ndx: pd.Series, spx: pd.Series) -> pd.Series:
    """比值自己的牛熊（现行检测器同一组参数）：True = 熊 = 纳指相对 S&P500 转弱。"""
    import equity_idle_study as EI
    return EI.t0_bear(ratio(ndx, spx))


def and_union(a: pd.Series, b: pd.Series) -> pd.Series:
    x, y, idx = N8.on_union(a, b)
    return pd.Series(x & y, index=idx)


def rtx_state(rbear: pd.Series, us_bear: pd.Series) -> pd.Series:
    """RTX：比值熊 且 B1 的分界不是熊。"""
    x, b, idx = N8.on_union(rbear, us_bear)
    return pd.Series(x & ~b, index=idx)


def nzs_state(zone: pd.Series, rbear: pd.Series) -> pd.Series:
    """NZS：ZSP 的警戒区（已经不含 B1 的熊）且 比值熊。"""
    return and_union(zone, rbear)


def states(W: dict) -> dict[str, pd.Series]:
    inp = W["inp"]
    rb = ratio_bear(inp["ndx"], inp["spx"]["Close"])
    zone = ZS.zone_state(ZS.zone_bear(inp["spx"]["Close"]), W["bear"]["US"])
    return {"RTX": rtx_state(rb, W["bear"]["US"]), "NZS": nzs_state(zone, rb), "_rbear": rb, "_zone": zone}


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r08_ratiospx.py", "scripts/loop3_r04_zonespx.py",
                                 "scripts/loop2_r12_ndxtospx.py", "scripts/loop2_r08_ndrhedged.py", "scripts/loop_r08_ndxreentry.py",
                                 "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py", "scripts/research_loop3.py", "scripts/candle_portfolio.py",
                                 "scripts/equity_idle_study.py", "qbreak/fees.py", "qbreak/bullbear.py", "scripts/loop2_r02_bondrefuge.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def inputs(W: dict):
    _, _, uni = L2.fje_states(W)
    return uni, states(W)


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    uni, st = inputs(W)
    hspx = NS.hedged_spx_frame(W["inp"])
    reg = R3.load_state().get("baseline") or {}
    base, cand, desc = {}, {k: {} for k in IDS}, {k: {} for k in IDS}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        for k in IDS:
            rc = L2.run(W, e, **NS.nsx_over(W, st[k], uni, hspx))
            nc = R5.core_trades(e, W)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            desc[k][e] = ZS.describe(W, e, st[k], uni, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": R8.old_core(W, uni, W["bear"]["US"])}
    s1 = {}
    for k in IDS:
        old[k] = NS.old_core(W, uni, W["bear"]["US"], st[k])
        old[f"{k}_segments"] = N8.segments(st[k], *OLD)
        unseen = None if old["B1"]["calmar"] is None or old[k]["calmar"] is None else old[k]["calmar"] - old["B1"]["calmar"]
        s1[k] = R3.stage1(cand[k], base, posthoc=unseen)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty, "base": base,
           "cand": cand, "stage1": s1, "drift": drift, "describe": desc, "old": old, "scale": scale(W, st), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"RTX": "纳指 / S&P500 比值转熊、S&P 还是牛 → 核心换成 S&P500", "NZS": "ZSP 的警戒区里比值也转熊 → 核心换成 S&P500"}
    L = [f"# 第三个研究循环第 8 轮：纳指 / S&P500 比值转熊时核心换成 S&P500 RTX / NZS（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r08_ratiospx.py 开头）", ""]
    for k in IDS:
        s1 = res["stage1"][k]
        ph = s1["posthoc"]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关（换指数标记在 S&P 牛的日子上循环平移）' if s1['ok'] else R3.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
                 f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | RTX（Calmar 差） | NZS（Calmar 差） |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + " |")
    L += ["", "只描述（不参与判定）："]
    for k in IDS:
        for e in L2.ERAS:
            d = res["describe"][k][e]
            sg = "、".join(f"{m['from']}〜{m['to']}（{m['days']} 天；纳指 {m['ndx']:+.1f}% / S&P {m['spx']:+.1f}%）" for m in d["moves"]) or "无"
            L.append(f"- {k} {e}：换指数 {d['switch_days']} 天（牛市日子的 {_f(d['zone_pct_of_bull'], '{:.1f}')}%；其中对冲中 "
                     f"{_f(d['switch_hedged_pct'], '{:.1f}')}%；{sg}）；核心换仓 B1 {d['core_trades']['B1']} → {k} {d['core_trades']['ZSP']} 笔")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    for k in IDS:
        sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o[f"{k}_segments"]) or "无"
        L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；{k} {oc(o[k])}（换指数 {sg}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。数据仅对本次取数时点有效。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale(W: dict, st: dict) -> dict:
    """各年代换指数的天数、占牛市的比例、段数（ZSP 的 scale 原样）+ 比值熊本身占美国交易日的比例。"""
    out = {k: ZS.scale(W, st[k]) for k in IDS}
    rb = st["_rbear"].astype(bool)
    out["ratio_bear_pct"] = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        m = (rb.index >= pd.Timestamp(a)) & ((rb.index < pd.Timestamp(b)) if b else (rb.index <= pd.Timestamp(L2.J_END)))
        out["ratio_bear_pct"][e] = round(float(rb[m].mean() * 100), 1) if m.any() else None
    return out


def scale_only() -> int:
    """登记前用：只数状态（不跑候选、不看收益）。"""
    W = L2.load()
    _, st = inputs(W)
    print(json.dumps(scale(W, st), ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 换指数全程 False → 账户与 B1 逐项相同；② RTX / NZS 的 1655 / 2563 买卖笔数 > 0（只数笔数，不看收益）。"""
    import loop2_r02_bondrefuge as T2
    W = L2.load()
    uni, st = inputs(W)
    hspx = NS.hedged_spx_frame(W["inp"])
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    rn = L2.run(W, "J", **NS.nsx_over(W, pd.Series(False, index=st["RTX"].index), uni, hspx))
    same = all(rb.get(x) == rn.get(x) for x in keys)
    n_spx = {}
    for k in IDS:
        L2.run(W, "J", **NS.nsx_over(W, st[k], uni, hspx))
        ct = T2.core_trades("J", W)
        n_spx[k] = int(ct.get(NS.SPX_T, 0) + ct.get(NS.SPH_T, 0))
    print(json.dumps({"never_same_as_b1": same, "spx_trades_J": n_spx}, ensure_ascii=False))
    return 0 if same and all(v > 0 for v in n_spx.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 8 轮：RTX / NZS（纳指 / S&P500 比值转熊 → 核心换成 S&P500）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数状态（不跑候选）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
