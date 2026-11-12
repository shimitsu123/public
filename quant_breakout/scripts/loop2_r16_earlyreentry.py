"""loop2_r16_earlyreentry.py — 第二个研究循环第 16 轮：「美股牛熊分界的回到牛用 0% 线（离场仍是 −3%）」ERA（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 16 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；接法：B1 的 fxh_over（第 8 轮 NDRH 同一个：只换「美股熊」那条序列）。
为什么做这个（照实写）：
  - 模拟盘的美股牛熊分界 = 250 日线 ±3%、连续 5 天（var/bullbear.json）。以前的检测器网格只试过对称的带（±b），没试过「回来用 0%、离场仍用 −3%」的不对称带；
    第一个循环的诊断「V 形反弹里回到核心太晚」、NDR / NDRH（纳指自己的检测器先回到牛就早回来）都指向「回来的线太远」。
    这一轮不用纳指、不加新信号：只把 S&P 自己回到牛的那条线从 +3% 降到 0%（= 检测器的同一个均线），离场与确认天数都不变。
  - 看过 NDR / NDRH / 检测器网格之后设计 → 按事后处理：S7 适用。家族「核心·择时（早回来）」3 / 3（用完）。
  - 照实写：这一类（改核心仓位的择时）第二关的随机对照肥尾（NDRH 400 次最大 +0.699），即使第一关过、第二关也很难；选它是因为剩下的题里它第一关的机会最大，
    而且直接回答模拟盘检测器「回来是不是太晚」。
做法 ERA（参数没有新学的：0% = 均线本身；L = 250、离场 −3%、k = 5 照 var/bullbear.json → S6 不适用；不改个股买卖 → S5 不适用）：
  - 美股熊（ERA）= qbreak/bullbear.ma_band 同一写法，只把回到牛的带改成 0%：熊 → 牛 = 收盘 > 250 日线 连续 5 天；牛 → 熊 = 收盘 < 250 日线 × 0.97 连续 5 天
    （起点规则、均线、计数都与 ma_band 相同）。S&P500（^GSPC 美元）上算；美国 d 日收盘 → 日本 d+1 开盘。
  - 核心：B1 的 fxh_over，「美股熊」换成 ERA 的（FJE 对冲中 → 2845，否则 1545；ERA 熊 → 现金）。个股层、判断层、FJE、费用全部同 B1。
  - 接线：带改回 +3% 时（= 现行检测器）必须与 B1 完全相同（登记前核对：三个年代逐项相同、1987〜2000 只有核心相同）。
第一关：research_loop2.stage1（posthoc = 1987〜2000 只有核心 ERA − B1 的 Calmar 差；第 8 轮 old_core 原样）。
第二关（第一关全过才做）：另行登记后只运行一次；形状预定 =「早回来」的日子（ERA 是牛、B1 是熊）在 S&P 熊（B1）的日子串上整体循环平移（NDRH 同一个形状）。
只描述（不参与判定）：各年代早回来的天数与段、核心换仓、每年收益差、1987〜2000 的段。
事前预期（照实写，按一般的市场历史估计）：2003-04、2009-06〜07、2010-09、2012-01、2016-03、2019-02、2020-05、2023-01、2025-05 回来得早几周 → 多赚；
  熊市里的反弹站上均线又跌回（2002 年初、2015-11〜12、2022-12）→ 多亏。第一关约 25%、第二关约 5%（肥尾），「更好候选」约 1%。
运行：python scripts/loop2_r16_earlyreentry.py（第一关）。输出 var/out/loop2_r16_earlyreentry.md / .json。非投资建议。
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

ROUND = 16
IDS = ("ERA",)
FAMILY = "核心·择时（早回来）"
POSTHOC = True
OLD = R5.OLD
B_UP = 0.0                                                                  # 回到牛的带（现行 +3%）
OUT = "loop2_r16_earlyreentry"


# ───────────────────────── 检测器（tests/test_loop2_r16.py） ─────────────────────────
def detector_params() -> dict:
    """模拟盘牛熊分界的检测器参数（var/bullbear.json：kind = ma_band、L、b、k）。"""
    from qbreak.bullbear import load_config
    d = load_config()["detector"]
    assert d["kind"] == "ma_band", d
    return dict(d["params"])


def asym_ma_band(close: pd.Series, L: int, b_dn: float, b_up: float, k: int) -> np.ndarray:
    """qbreak/bullbear.ma_band 同一写法，只是回到牛与转熊用不同的带（b_up = b_dn 时与 ma_band 完全相同）。"""
    from qbreak.bullbear import BEAR, BULL, _sma
    v = close.values.astype(float)
    ma = _sma(v, L)
    st = np.zeros(len(v), dtype=int)
    state, run_dn, run_up = 0, 0, 0
    for i in range(len(v)):
        if np.isnan(ma[i]):
            continue
        dn, upc = v[i] < ma[i] * (1 - b_dn), v[i] > ma[i] * (1 + b_up)
        run_dn = run_dn + 1 if dn else 0
        run_up = run_up + 1 if upc else 0
        if state == 0:
            state = BULL if v[i] >= ma[i] else BEAR
        elif state == BULL and run_dn >= k:
            state = BEAR
        elif state == BEAR and run_up >= k:
            state = BULL
        st[i] = state
    return st


def era_bear(close: pd.Series, b_up: float = B_UP) -> pd.Series:
    """ERA 的美股熊（True = 熊）：检测器参数照 var/bullbear.json，只把回到牛的带换成 b_up。"""
    from qbreak.bullbear import BEAR
    p = detector_params()
    c = close.dropna()
    return pd.Series(asym_ma_band(c, int(p["L"]), float(p["b"]), float(b_up), int(p["k"])) == BEAR, index=c.index)


def era_over(W: dict, bear: pd.Series, uni: pd.Series) -> dict:
    """B1 的接法（fxh_over：对冲中 → 2845，否则 1545）里把「美股熊」换成 ERA 的。"""
    import loop_r04_yensurge as Y
    return Y.fxh_over(W, bear, uni, Y.hedged_frame(W["inp"]))


def early_days(b1_bear: pd.Series, bear: pd.Series) -> pd.Series:
    """早回来 = ERA 是牛、B1 是熊（日期并集上各自向后填）。"""
    s, n, idx = N8.on_union(b1_bear, bear)
    return pd.Series(s & ~n, index=idx)


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r16_earlyreentry.py", "scripts/loop2_r08_ndrhedged.py",
                                 "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py", "scripts/research_loop2.py",
                                 "scripts/candle_portfolio.py", "qbreak/bullbear.py", "var/bullbear.json"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    b1 = W["bear"]["US"]
    eb = era_bear(W["inp"]["spx"]["Close"])
    early = early_days(b1, eb)
    ov = era_over(W, eb, uni)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        a, b = W["ctx"][e]["windows"][e]
        seg = N8.segments(early, a, b or L2.J_END)
        desc[e] = {"early_days": int(sum(n for _, _, n in seg)), "segments": seg, "core_trades": {"B1": nb, "ERA": nc}}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": R8.old_core(W, uni, b1), "ERA": R8.old_core(W, uni, eb), "segments": N8.segments(early, *OLD)}
    unseen = None if old["B1"]["calmar"] is None or old["ERA"]["calmar"] is None else old["ERA"]["calmar"] - old["B1"]["calmar"]
    s1 = {"ERA": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"ERA": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["ERA"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 16 轮：美股牛熊分界回到牛用 0% 线 ERA（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r16_earlyreentry.py 开头）", "",
         f"- **ERA：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | ERA（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['ERA'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in d["segments"]) or "无"
        L.append(f"- {e}：早回来 {d['early_days']} 天（{sg}）；核心换仓 B1 {d['core_trades']['B1']} → ERA {d['core_trades']['ERA']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["ERA"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（ERA − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o["segments"]) or "无"
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；ERA {oc(o['ERA'])}（早回来 {sg}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 16 轮：ERA（美股牛熊分界回到牛用 0% 线）")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
