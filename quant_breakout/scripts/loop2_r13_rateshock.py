"""loop2_r13_rateshock.py — 第二个研究循环第 13 轮：「美国利率急升、且纳指近 3 个月已落后 S&P 时，核心换成 S&P500」RXC（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 13 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；接法：第 12 轮 scripts/loop2_r12_ndxtospx.py（四只核心、follow，原样）。
为什么挑这个题（照实写）：
  - 第 12 轮 NSX（纳指自己的检测器转熊 → S&P500）第一关不过：价格趋势翻熊时下跌多半已过、之后纳指 V 形反弹更快（「慢半拍」）。
    「仓位不变、只换指数」的随机对照不肥尾这一点没变 → 换一个**领先**的切换键：利率急升。纳指（成长股、久期长）对利率上升比 S&P 更敏感
    （文献：equity duration —— Dechow, Sloan & Soliman 2004、Weber 2018、Gormsen & Lazarus 2023；利率变化有时间序列动量 —— Moskowitz, Ooi & Pedersen 2012）；
    再加「纳指近 63 天已经跑输 S&P」作确认，避免在纳指领涨的加息期（1999、2003 下半年、2007、2018 年初、2023）换出去（风格动量：Barberis & Shleifer 2003）。
  - 以前做过的（不重复）：NSX（纳指自己的牛熊）、core_switch_study 的 F（252 天相对强弱，月度）、风险参数 × 方向 R1 / R2（10 年利率的**水平**进压力数、可转现金）、
    加息预期代理 G1〜G3（2 年 − 联邦基金 → 空仓）、威胁指数的 rates 因素（只在威胁指数里、当核心开关已三次否定）—— 没有「利率**变化**急升 → 同样仓位换 S&P」。
  - 这一轮的选题来自本会话里另一个只读的检查（不跑回测，只读代码与记录），是在看过 NSX、F、R2 的结果之后设计的 → 按事后处理：S7 适用。
    家族「核心·指数选择」2 / 3。参数都是仓库里已有的约定（不新学）：利率 60 日变化、前一天的值 = qbreak/threat.raw_features 的 rates；
    百分位 = threat.expanding_pct（1962 起扩展、至少 750 个值）；80 分位 = 威胁指数 / 判断层的警戒线；63 天 = 选股特征 spx_r63 的窗口。
做法 RXC（没有学参数 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 美国交易日 d（S&P500 的交易日）：利率急升 = 10 年国债（FRED DGS10，用前一天的值）60 个交易日的变化 在 1962 年起的扩展百分位 ≥ 0.80；
    纳指落后 = 纳指总收益 63 天涨跌 < S&P500 总收益 63 天涨跌（equity_idle_study.ndx_tr / spx_tr，美元）；
    换指数 S = 利率急升 且 纳指落后 且 S&P 不是熊。美国 d 日收盘 → 日本 d+1 开盘（同 B1）。
  - 核心：与第 12 轮完全相同的接法（loop2_r12_ndxtospx.nsx_over：美股熊 → 现金；不是 S → 同 B1；S → FJE 对冲中 → 2563，否则 1655；合成价、费用同第 12 轮）。
  - 接线：S 永远不成立 = B1（第 12 轮登记前已用同一个 nsx_over 核对过三个年代与 1987〜2000；本轮 tests/test_loop2_r13.py 查状态与接法）。
第一关：research_loop2.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 RXC − B1 的 Calmar 差；第 12 轮 old_core 原样）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次；形状预定 =「换指数」标记在 2000-01-03〜2026-09-30 里 S&P 牛的美国交易日串上整体循环平移，细节在那时写定。
只描述（不参与判定）：各年代利率急升的日子比例（S&P 牛的日子里）、换指数的天数 / 段 / 其中对冲中的比例、每段纳指与 S&P500（合成、日元、不对冲）的涨跌、
  核心换仓、每年收益差、1987〜2000 的段。
事前预期（照实写，按一般的市场历史估计，不是这个项目的结果）：Z 2004 春与 2006 春（利率急升、纳指先落后）多半为正；E 2013 年缩减恐慌（纳指因苹果落后）
  可能为负、2016-11〜12 为正；J 2018 秋、2021 年 2〜3 月、2022 年初为正，2024 春持平；1987〜2000 的 1994 为正、1996 不确定、1999 纳指领先不换。
  确认条件本身是 63 天的价格比较 → 仍可能慢半拍。
  登记前只看过信号本身（天数与段数，没算收益）：换指数 Z 66 天 5 段、E 37 天 7 段、J 200 天 30 段、1987〜2000 200 天 35 段 ——
  J 的 63 天比较来回翻（平均一段约 7 天）→ 换仓成本与来回吃亏；规则是在看信号之前写定的，看过之后没改，只把事前预期下调：
  第一关约 15%、第二关约 12%，「更好候选」约 2%。
运行：python scripts/loop2_r13_rateshock.py（第一关）。输出 var/out/loop2_r13_rateshock.md / .json。非投资建议。
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
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 13
IDS = ("RXC",)
FAMILY = "核心·指数选择"
POSTHOC = True                                                              # 看过 NSX、F、R2 之后设计 → 按事后处理（S7 适用）
OLD = R5.OLD
CHG_N, PCT_TH, REL_N = 60, 0.80, 63                                         # threat 的 rates 窗口、警戒分位、spx_r63 的窗口
OUT = "loop2_r13_rateshock"


# ───────────────────────── 状态（tests/test_loop2_r13.py） ─────────────────────────
def rate_change(dgs10: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """10 年利率 60 个交易日的变化（前一天的值）= qbreak/threat.raw_features 的 rates 同一段算法。"""
    from qbreak import threat as TH
    r10 = TH._daily(dgs10, days, 1)
    return r10 - r10.shift(CHG_N)


def rate_shock(dgs10: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """利率急升：60 日变化在扩展百分位（threat.expanding_pct，1962 起、至少 750 个值）≥ 0.80；算不出 = False。"""
    from qbreak import threat as TH
    p = TH.expanding_pct(rate_change(dgs10, days))
    return pd.Series((p >= PCT_TH - 1e-12).to_numpy() & p.notna().to_numpy(), index=days)


def ndx_lag(ndx_tr: pd.Series, spx_tr: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """纳指落后：两边总收益（向前填到 days）63 个交易日的涨跌，纳指 < S&P；算不出 = False。"""
    n = ndx_tr.dropna().reindex(days.union(ndx_tr.dropna().index)).ffill().reindex(days)
    s = spx_tr.dropna().reindex(days.union(spx_tr.dropna().index)).ffill().reindex(days)
    rn, rs = n / n.shift(REL_N) - 1, s / s.shift(REL_N) - 1
    return pd.Series(((rn < rs) & rn.notna() & rs.notna()).to_numpy(), index=days)


def switch_state(spx_bear: pd.Series, shock: pd.Series, lag: pd.Series) -> pd.Series:
    """换指数 S = 利率急升 且 纳指落后 且 S&P 不是熊（日期并集上向后填，之前没有值 = False）。"""
    idx = spx_bear.index.union(shock.index).union(lag.index)
    f = lambda s: s.astype(float).reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5   # noqa: E731
    return pd.Series(f(shock) & f(lag) & ~f(spx_bear), index=idx)


def states(W: dict) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(利率急升, 纳指落后, 换指数) —— 美国交易日 = S&P500 的交易日。"""
    import equity_idle_study as EI
    from qbreak import factors
    inp = W["inp"]
    days = inp["spx"].index
    shock = rate_shock(factors.fred("DGS10", max_age_h=1e9), days)
    lag = ndx_lag(EI.ndx_tr(inp), EI.spx_tr(inp), days)
    return shock, lag, switch_state(W["bear"]["US"], shock, lag)


def rxc_over(W: dict, sw: pd.Series, uni: pd.Series, hspx: pd.DataFrame) -> dict:
    """第 12 轮的接法原样（四只核心、follow）：S → S&P500（对冲中 2563，否则 1655）。"""
    return R12.nsx_over(W, sw, uni, hspx)


# ───────────────────────── 只描述 ─────────────────────────
def describe(W: dict, e: str, shock: pd.Series, sw: pd.Series, uni: pd.Series, n_core: tuple[int, int]) -> dict:
    d = R12.describe(W, e, sw, uni, n_core)
    a, b = W["ctx"][e]["windows"][e]
    bull = ~W["bear"]["US"].astype(bool)
    m = (bull.index >= pd.Timestamp(a)) & (bull.index < pd.Timestamp(b))
    bd = bull[m]
    sh = shock.reindex(bd.index).fillna(False).astype(bool)
    d["shock_pct_of_bull"] = round(float(sh[bd.to_numpy()].mean() * 100), 1) if bd.any() else None
    d["core_trades"] = {"B1": n_core[0], "RXC": n_core[1]}
    return d


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r13_rateshock.py", "scripts/loop2_r12_ndxtospx.py",
                                 "scripts/loop2_r08_ndrhedged.py", "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py",
                                 "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py", "qbreak/threat.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    shock, lag, sw = states(W)
    ov = rxc_over(W, sw, uni, R12.hedged_spx_frame(W["inp"]))
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, shock, sw, uni, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": R8.old_core(W, uni, W["bear"]["US"]), "RXC": R12.old_core(W, uni, W["bear"]["US"], sw),
           "segments": N8.segments(sw, *OLD)}
    unseen = None if old["B1"]["calmar"] is None or old["RXC"]["calmar"] is None else old["RXC"]["calmar"] - old["B1"]["calmar"]
    s1 = {"RXC": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"RXC": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["RXC"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 13 轮：美国利率急升且纳指已落后时核心换成 S&P500 RXC（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r13_rateshock.py 开头）", "",
         f"- **RXC：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | RXC（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['RXC'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        sg = "、".join(f"{m['from']}〜{m['to']}（{m['days']} 天；纳指 {m['ndx']:+.1f}% / S&P {m['spx']:+.1f}%）" for m in d["moves"]) or "无"
        L.append(f"- {e}：S&P 牛的日子里利率急升 {_f(d['shock_pct_of_bull'], '{:.1f}')}%；换指数 {d['switch_days']} 天"
                 f"（其中对冲中 {_f(d['switch_hedged_pct'], '{:.1f}')}%；{sg}）；核心换仓 B1 {d['core_trades']['B1']} → RXC {d['core_trades']['RXC']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["RXC"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（RXC − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o["segments"]) or "无"
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；RXC {oc(o['RXC'])}（换指数 {sg}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 13 轮：RXC（美国利率急升且纳指已落后时核心换成 S&P500）")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
