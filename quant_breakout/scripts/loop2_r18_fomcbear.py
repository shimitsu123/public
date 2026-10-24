"""loop2_r18_fomcbear.py — 第二个研究循环第 18 轮：「美股熊市里只在定期 FOMC 公布那一天拿核心」FMB（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 18 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；接法：第 7 轮 TOMB 原样（只换标记日）。
为什么挑这个题（照实写）：
  - 文献：FOMC 公布之前的漂移（pre-FOMC drift；Lucca & Moench 2015，1994〜2011 年 S&P500 在定期公布前 24 小时平均约 +0.5%，占同期股票超额收益的大头；
    Cieslak, Morse & Vissing-Jorgensen 2019 的 FOMC 周期）。B1 在美股熊市里全是现金；如果这个漂移在熊市里也有，只在这一天拿核心就是「多一点收益、少一点风险」。
  - 以前做过的：第 7 轮 TOMB（熊市里只在月末月初 4 天拿核心）合计 −1.056（2002、2008 的熊市窗口大跌）；政策事件反应库 G1（只描述日本 / 美国政策公布的反应，
    不当规则）。FOMC 日的熊市持仓没有做过。选题来自本会话里另一个只读检查（它的估计照实写：约 1%，随机对照肥尾）。
  - 不是事后组合（不是已看过规则的组合）→ S7 不适用；家族「核心·熊市日历」2 / 3。
做法 FMB（日期来自官方日程，没有参数 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 定期 FOMC 公布日 = var/policy_events.csv 里 FOMC statement 的日期（美国日期），去掉临时会议（description 写 unscheduled 的）与 excluded = 1 的。
  - 标记日 = 每个定期公布日的前一个美国交易日（美国 d−1 日收盘的状态 → 日本 d 日开盘买 → 持有到日本 d+1 日开盘 = 拿到美国 d 日（公布日）收盘的涨跌）。
  - 核心用的「熊」= 美股熊 且 不是标记日（loop2_r07_tomcore.bear_eff 原样）；B1 的 fxh_over（FJE 照旧）。个股层、判断层、费用全部同 B1。
  - 接线：没有标记日时 = B1（第 7 轮登记前核对过同一个接法）。
第一关：research_loop2.stage1（posthoc = None）。第二关（第一关全过才做）：另行登记；形状预定 = 标记日在美股熊的日子串上整体循环平移（TOMB 同一个形状）。
只描述（不参与判定）：各年代美股熊里的标记日个数、核心换仓、每年收益差、各标记日纳指（合成、日元、不对冲）那一天的涨跌合计。
事前预期（照实写）：熊市里 FOMC 公布日常有大涨（2001、2008、2022 的几次），但也有大跌；一共只有约 50〜60 天、每天 ±2〜5% → 结果主要是噪声；
  漂移在 2015 年以后变弱（文献）。第一关约 15%、第二关约 3%（肥尾），「更好候选」约 0.5%。
运行：python scripts/loop2_r18_fomcbear.py（第一关）。输出 var/out/loop2_r18_fomcbear.md / .json。非投资建议。
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
import loop2_r07_tomcore as R7                                               # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 18
IDS = ("FMB",)
FAMILY = "核心·熊市日历"
POSTHOC = False
EVENTS = "policy_events.csv"
OUT = "loop2_r18_fomcbear"


# ───────────────────────── 日期与标记（tests/test_loop2_r18.py） ─────────────────────────
def fomc_dates(ev: pd.DataFrame) -> pd.DatetimeIndex:
    """定期 FOMC 公布日（美国日期）：FOMC statement、不是临时会议（description 含 unscheduled）、excluded = 0；同一天去重。"""
    name = ev["name_en"].astype(str)
    desc = ev["description"].astype(str).str.lower()
    exc = pd.to_numeric(ev.get("excluded", 0), errors="coerce").fillna(0).astype(int)
    m = name.str.contains("FOMC statement", regex=False) & ~desc.str.contains("unscheduled", regex=False) & (exc == 0)
    return pd.DatetimeIndex(sorted(set(pd.to_datetime(ev.loc[m, "date"]))))


def load_fomc() -> pd.DatetimeIndex:
    from qbreak import paths
    return fomc_dates(pd.read_csv(paths.PROJECT_ROOT / "var" / EVENTS))


def fmb_flags(us_days: pd.DatetimeIndex, fomc: pd.DatetimeIndex) -> pd.Series:
    """标记日 = 每个定期公布日的前一个美国交易日（公布日不是美国交易日的跳过）。"""
    days = pd.DatetimeIndex(us_days)
    out = np.zeros(len(days), bool)
    for d in fomc:
        k = days.get_indexer([d])[0]
        if k > 0:
            out[k - 1] = True
    return pd.Series(out, index=days)


def fmb_over(W: dict, flags: pd.Series, uni: pd.Series) -> dict:
    """第 7 轮 TOMB 的接法原样：核心用的熊 = 美股熊 且 不是标记日。"""
    return R7.tomb_over(W, flags, uni)


# ───────────────────────── 只描述 ─────────────────────────
def describe(W: dict, e: str, flags: pd.Series, n_core: tuple[int, int]) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    bear = W["bear"]["US"].astype(bool)
    f = flags.reindex(bear.index).fillna(False).astype(bool)
    m = (bear.index >= pd.Timestamp(a)) & (bear.index < pd.Timestamp(b))
    hit = bear.index[m & bear.to_numpy() & f.to_numpy()]
    px = W["assets"]["1545.T"]["Close"]
    moves = []
    for d in hit:                                                            # 日本 d+1 开盘买 → d+2 开盘卖 ≈ 合成价 d+1 → d+2
        i = px.index.searchsorted(d, side="right")
        if i + 1 < len(px):
            moves.append(float(px.iloc[i + 1] / px.iloc[i] - 1) * 100)
    return {"flag_days_in_bear": int(len(hit)), "ndx_move_sum": round(float(np.sum(moves)), 1) if moves else 0.0,
            "ndx_move_mean": round(float(np.mean(moves)), 2) if moves else None, "core_trades": {"B1": n_core[0], "FMB": n_core[1]}}


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r18_fomcbear.py", "scripts/loop2_r07_tomcore.py",
                                 "scripts/loop2_common.py", "scripts/research_loop2.py", "scripts/candle_portfolio.py", "var/policy_events.csv"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    flags = fmb_flags(W["bear"]["US"].index, load_fomc())
    ov = fmb_over(W, flags, uni)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, flags, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"FMB": R2.stage1(cand, base, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"FMB": cand}, "stage1": s1, "drift": drift, "describe": desc, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["FMB"]
    L = [f"# 第二个研究循环第 18 轮：美股熊市里只在定期 FOMC 公布那一天拿核心 FMB（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r18_fomcbear.py 开头）", "",
         f"- **FMB：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | FMB（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['FMB'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：美股熊里的公布日 {d['flag_days_in_bear']} 个；那几天纳指（合成、日元）合计 {d['ndx_move_sum']:+.1f}%（平均 {_f(d['ndx_move_mean'], '{:+.2f}')}%）；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → FMB {d['core_trades']['FMB']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["FMB"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（FMB − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 18 轮：FMB（美股熊市里只在定期 FOMC 公布那一天拿核心）")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
