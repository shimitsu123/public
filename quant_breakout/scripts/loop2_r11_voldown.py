"""loop2_r11_voldown.py — 第二个研究循环第 11 轮：「核心按美元计纳指的下行波动调节仓位」VTD（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 11 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；VTU：scripts/loop2_r09_voltusd.py（除了波动率的算法，其余照它）。
为什么做这个（照实写）：
  - 第 9 轮 VTU（美元计纳指 σ20 高于自己的历史中位数 → 核心 × 中位数 / σ20）第一关全过（+0.184）、第二关约第 88 百分位；年化少的年份 J 2018 −5.2、
    2021 −5.1、2019 −2.0、2026 −2.0 pp，E 2014 −4.1、2015 −2.5 pp —— 高波动里也有「涨得很猛」的时候（2020-04 以后、2021 年初、2023），总波动率会误减仓。
  - 文献：只按下行波动管理仓位（downside-volatility managed portfolios；Wang & Yan 2021, Journal of Financial Economics）比按总波动更好，
    理由正是不会在上涨的高波动里减仓。这一轮把 VTU 的 σ20 换成 20 日下行半偏差（只算跌的那几天），其余（扩展中位数、0.10 滞后带、回到 1）不变。
  → 看过 VTU 的逐年结果之后定的 → 按事后处理，S7 适用。家族「核心·波动率仓位」2 / 3。
做法 VTD（参数照 VTU / VT20 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 纳指总收益（美元；equity_idle_study.ndx_tr）的美国交易日对数收益 r；下行半偏差 σ⁻20 = √(最近 20 天 min(r, 0)² 的平均) × √252；
    目标 = σ⁻20 自己 1986-01-01 起的扩展中位数（至少 250 个值，之前 = 比例 1）；比例 = min(1, 目标 / σ⁻20)，与上一次的比例差 ≥ 0.10 才换，
    σ⁻20 ≤ 目标时直接回到 1（loop_r01_voltarget.exposure 原样）。
  - 只作用在不是美股熊的日子：B1 的两个核心键 US_UH / US_HG（1545 / 2845，FJE 照旧）的目标 × 比例；美国 d 日收盘 → 日本 d+1 开盘。其余全部同 B1。
  - 接线检查（登记前跑过）：比例全 1 = B1（三个年代与 1987〜2000 只有核心）。
第一关：research_loop2.stage1（posthoc = 1987〜2000 只有核心 VTD − B1；第 9 轮 old_core 同一个口径）。只描述：牛日平均比例、减仓日比例、核心换仓、每年收益差；
  另报同一次运行里 VTU 的 Calmar。
第二关（第一关全过才做）：另行登记（提交）后只运行一次（形状照 VT20 / VTU：比例序列整体循环平移）。
事前预期（照实写）：设计时以为上涨里的高波动不再减仓 → J 2020 下半年、2021 年初、2023 少吃亏；但登记前看的状态序列显示 VTD 减仓的日子反而比 VTU 多
  （牛日平均比例 Z 0.964 / E 0.961 / J 0.886，VTU 0.980 / 0.976 / 0.913；减仓日 21.6% / 17.9% / 37.8%，VTU 14.7 / 11.9 / 31.9）—— 只看跌的日子、20 天里样本少，
  比例更容易跳 → 第一关约 25%（少赚更多）；第二关的右尾与 VTU 同一类 → 约 15%；「更好候选」约 4%。参数是在看状态序列之前写定的，没改。
运行：python scripts/loop2_r11_voldown.py（第一关）。输出 var/out/loop2_r11_voldown.md / .json。非投资建议。
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
import loop2_r09_voltusd as R9                                               # noqa: E402
import loop_r01_voltarget as VT                                              # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 11
IDS = ("VTD",)
FAMILY = R9.FAMILY
POSTHOC = True
OLD = R5.OLD
OUT = "loop2_r11_voldown"


# ───────────────────────── 比例（tests/test_loop2_r11.py） ─────────────────────────
def downside_sigma(px: pd.Series, n: int = VT.WIN_N) -> pd.Series:
    """20 日下行半偏差（年化）：√(最近 n 天 min(r, 0)² 的平均) × √252，r = 对数收益。"""
    r = np.log(px.astype(float)).diff()
    d = r.clip(upper=0.0) ** 2
    return np.sqrt(d.rolling(n, min_periods=n).mean()) * np.sqrt(252)


def ratio_down(ndx_tr: pd.Series) -> pd.Series:
    sd = downside_sigma(ndx_tr.dropna().sort_index())
    return VT.exposure(sd, VT.target(sd))


def describe(W: dict, e: str, x: pd.Series, n_core: tuple[int, int]) -> dict:
    return R9.describe(W, e, x, n_core)


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r11_voldown.py", "scripts/loop2_r09_voltusd.py",
                                 "scripts/loop_r01_voltarget.py", "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py",
                                 "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    ntr = EI.ndx_tr(W["inp"])
    x = ratio_down(ntr)
    xu = R9.ratio_usd(ntr)
    reg = R2.load_state().get("baseline") or {}
    base, cand, side, desc = {}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **R9.vtu_over(x))
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        side[e] = _acct(L2.run(W, e, **R9.vtu_over(xu)))
        desc[e] = describe(W, e, x, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": R9.old_core(W, uni, None), "VTD": R9.old_core(W, uni, x)}
    unseen = None if old["B1"]["calmar"] is None or old["VTD"]["calmar"] is None else old["VTD"]["calmar"] - old["B1"]["calmar"]
    s1 = {"VTD": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"VTD": cand, "VTU": side}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["VTD"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 11 轮：核心按美元计纳指的下行波动调节仓位 VTD（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r11_voldown.py 开头）", "",
         f"- **VTD（VTU 的 σ20 换成 20 日下行半偏差）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | VTD（Calmar 差） | 另报：VTU 的 Calmar |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['VTD'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {_f(res['cand']['VTU'][e]['calmar'])} |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：美股牛的日子里平均比例 {_f(d['mean_ratio_bull'])}、比例 < 1 的日子 {_f(d['cut_pct_of_bull'], '{:.1f}')}%、最低 {_f(d['min_ratio'])}；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → VTD {d['core_trades']['VTU']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["VTD"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VTD − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；VTD {oc(o['VTD'])}（美股牛的日子里平均比例 {o['VTD']['mean_ratio_bull']}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 11 轮：VTD（核心按美元计纳指的下行波动调节仓位）")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
