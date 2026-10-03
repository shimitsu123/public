"""loop2_r15_rateshockconf.py — 第二个研究循环第 15 轮：RXC 加「连续 5 天才翻」RXH（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 15 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；RXC：第 13 轮 scripts/loop2_r13_rateshock.py；接法：第 12 轮 nsx_over 原样。
为什么做这个（照实写，看过 RXC 的结果之后设计 → 事后、S7 适用；是 RXC 换一个参数重跑 → 按规则算一个新做法；家族「核心·指数选择」3 / 3，用完）：
  - RXC（利率急升且纳指 63 天已落后 → 核心换 S&P500）合计 +0.199（Z +0.243），利率急升里纳指先落后的那几段确实换对了（2006 春、2021 春、2022 春），
    但第一关输在 E −0.048、前一半 −0.056、1987〜2000 −0.011；事后描述：63 天的比较来回翻，J 30 段里约 20 段只有 1〜4 天、E 7 段里 5 段 ≤ 5 天，
    1987〜2000 35 段 —— 换仓成本与来回吃亏。
  - 这一轮只加一个去抖：换指数的原始条件（利率急升 且 纳指落后）要**连续 5 个美国交易日**成立才打开、连续 5 天不成立才关掉 ——
    5 天 = 模拟盘牛熊分界检测器的确认天数（var/bullbear.json 的 k = 5，qbreak/bullbear.ma_band 同一个写法），不是新学的数。其余与 RXC 完全相同。
  - 照实写会留下的问题：2017-01（22 天、纳指 +0.2% / S&P −2.9%，日元计）这种「换出去之后纳指马上领先」的长段去抖去不掉 → 前一半（S4）仍是关键。
做法 RXH（没有学参数 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 原始条件 x_d = RXC 的利率急升 且 纳指落后（loop2_r13_rateshock.rate_shock / ndx_lag 原样）；
    状态：关着时 x 连续 5 天成立 → 打开；开着时 x 连续 5 天不成立 → 关掉；否则不变（ma_band 的 run 计数同一写法）。
  - 换指数 S = 状态开着 且 S&P 不是熊 → 核心换 S&P500（FJE 对冲中 2563，否则 1655）；不是 S → 同 B1；美股熊 → 现金。美国 d 日收盘 → 日本 d+1 开盘。
  - 接线：S 永远不成立 = B1（第 12 轮登记前核对过同一个 nsx_over）。
第一关：research_loop2.stage1（posthoc = 1987〜2000 只有核心 RXH − B1 的 Calmar 差；第 12 轮 old_core 原样）。
第二关（第一关全过才做）：另行登记后只运行一次；形状预定同第 12 / 13 轮（换指数标记在 S&P 牛的日子串上整体循环平移）。
只描述（不参与判定）：同第 13 轮（S&P 牛里利率急升比例、换指数的天数 / 段 / 对冲中比例、每段纳指与 S&P500 的涨跌、核心换仓、每年收益差、1987〜2000 的段）。
事前预期（照实写）：短段去掉 → E 的 2013 那几段与 J 的 2018 / 2022-02 那些 1〜4 天的段没有了，换仓成本少；长段（2006 春、2017-01、2021 春、2022 春）延后 5 天开、延后 5 天关。
  Z 仍为正；E 接近 0；J 小幅为正；前一半（2017-01、2011-02）仍可能为负 → 第一关约 12%、第二关约 12%，「更好候选」约 1.5%。
运行：python scripts/loop2_r15_rateshockconf.py（第一关）。输出 var/out/loop2_r15_rateshockconf.md / .json。非投资建议。
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
import loop2_r12_ndxtospx as R12                                             # noqa: E402
import loop2_r13_rateshock as R13                                            # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 15
IDS = ("RXH",)
FAMILY = "核心·指数选择"
POSTHOC = True
OLD = R5.OLD
K_CONFIRM = 5                                                               # = var/bullbear.json 的 k（牛熊分界检测器的确认天数）
OUT = "loop2_r15_rateshockconf"


# ───────────────────────── 状态（tests/test_loop2_r15.py） ─────────────────────────
def confirm(x: pd.Series, k: int = K_CONFIRM) -> pd.Series:
    """去抖：关着时 x 连续 k 天成立 → 打开；开着时 x 连续 k 天不成立 → 关掉（qbreak/bullbear.ma_band 的 run 计数同一写法）。"""
    v = x.fillna(False).to_numpy(bool)
    out = np.zeros(len(v), bool)
    state, run_on, run_off = False, 0, 0
    for i in range(len(v)):
        run_on = run_on + 1 if v[i] else 0
        run_off = run_off + 1 if not v[i] else 0
        if not state and run_on >= k:
            state = True
        elif state and run_off >= k:
            state = False
        out[i] = state
    return pd.Series(out, index=x.index)


def states(W: dict) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(利率急升, 去抖后的原始条件, 换指数) —— 美国交易日 = S&P500 的交易日；原始条件 = RXC 的「急升 且 纳指落后」。"""
    shock, lag, _ = R13.states(W)
    raw = pd.Series(shock.to_numpy(bool) & lag.reindex(shock.index).fillna(False).to_numpy(bool), index=shock.index)
    on = confirm(raw)
    bear = W["bear"]["US"]
    idx = bear.index.union(on.index)
    f = lambda s: s.astype(float).reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5   # noqa: E731
    return shock, on, pd.Series(f(on) & ~f(bear), index=idx)


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r15_rateshockconf.py", "scripts/loop2_r13_rateshock.py",
                                 "scripts/loop2_r12_ndxtospx.py", "scripts/loop2_r08_ndrhedged.py", "scripts/loop2_r05_ddbrake.py",
                                 "scripts/loop2_common.py", "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py",
                                 "qbreak/threat.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    shock, _, sw = states(W)
    ov = R12.nsx_over(W, sw, uni, R12.hedged_spx_frame(W["inp"]))
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = R13.describe(W, e, shock, sw, uni, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": R8.old_core(W, uni, W["bear"]["US"]), "RXH": R12.old_core(W, uni, W["bear"]["US"], sw),
           "segments": N8.segments(sw, *OLD)}
    unseen = None if old["B1"]["calmar"] is None or old["RXH"]["calmar"] is None else old["RXH"]["calmar"] - old["B1"]["calmar"]
    s1 = {"RXH": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"RXH": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["RXH"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 15 轮：RXC 加「连续 5 天才翻」RXH（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r15_rateshockconf.py 开头）", "",
         f"- **RXH：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | RXH（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['RXH'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        sg = "、".join(f"{m['from']}〜{m['to']}（{m['days']} 天；纳指 {m['ndx']:+.1f}% / S&P {m['spx']:+.1f}%）" for m in d["moves"]) or "无"
        L.append(f"- {e}：S&P 牛的日子里利率急升 {_f(d['shock_pct_of_bull'], '{:.1f}')}%；换指数 {d['switch_days']} 天"
                 f"（其中对冲中 {_f(d['switch_hedged_pct'], '{:.1f}')}%；{sg}）；核心换仓 B1 {d['core_trades']['B1']} → RXH {d['core_trades']['RXC']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["RXH"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（RXH − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o["segments"]) or "无"
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；RXH {oc(o['RXH'])}（换指数 {sg}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 15 轮：RXH（RXC 加连续 5 天才翻）")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
