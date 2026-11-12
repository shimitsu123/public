"""loop2_r07_tomcore.py — 第二个研究循环第 7 轮：「美股熊市里只在月末月初拿核心」TOMB（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 7 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py。
为什么挑这个题（照实写）：
  - 第 5 / 6 轮（DDB、VXB）与以前的 T4、CPX、VT20 都说明「跌了 / 恐慌了就减仓」在 V 形反弹里吃亏；核心的择时、熊市里的避险资产（家族已用完）、
    汇率对冲（不再加）都做过。B1 在美股熊市（Z 41% / E 30% / J 16% 的日子）里闲置资金全是现金，「熊市里什么时候拿一点核心」只做过
    NDA（纳指自己还牛就照拿，不过）、NDR（纳指先转牛就早拿回，不过）、深跌加仓（日経 1321，前向记录中）—— 都是看价格，没有看日历。
  - 月末月初效应（Turn-of-the-Month：每月最后 1 个交易日 + 下个月头 3 个交易日，美股收益集中在这几天；Ariel 1987、Lakonishok & Smidt 1988、
    McConnell & Xu 2008 —— 后者报告在跌市里也存在）是文献里长期稳定的日历规律；这个项目没测过（以前的日历研究只有季节性 H1 / 万圣节）。
  → 不是事后组合（不是把看过的结果拼起来；窗口是文献的标准定义、没调）→ S7 不适用；1987〜2000 只有核心的结果只描述。家族「核心·熊市日历」1 / 3。
做法 TOMB（参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 美国交易日（B1 美股牛熊分界的日期）里，每个月的「最后一个交易日 L」与「下个月第 1〜3 个交易日 F1〜F3」= 月末月初窗口。
    要拿到这四天的收益，持仓在 L 的前一天收盘决定、F3 收盘后放掉 → 「月末月初」标记 = {L−1、L、F1、F2} 这四个美国交易日的收盘
    （引擎：美国 d 日收盘的状态 → 日本 d+1 开盘成交；东证的核心合成价 = 前一个美国收盘 × 汇率）。
  - 美股熊 且 是标记日 → 核心照美股牛时的做法拿（FJE 照旧：对冲中 → 2845，否则 1545）；美股熊的其余日子 → 现金（= B1）；美股牛 → 同 B1。
    实现：B1 的两个核心键 US_UH / US_HG 用「美股熊 且 不是标记日」代替「美股熊」（loop_r04_yensurge.fxh_over 同一个接法）。
  - 个股层、判断层、费用全部同 B1。一次窗口来回约 4 次核心换仓（买 / 卖 × 2845 或 1545），按立花費用与滑点算。
  - 接线检查（登记前跑过，见 sim_changes 登记一节）：标记永远是假 = B1（三个年代与 1987〜2000 只有核心）。
第一关：research_loop2.stage1（posthoc = None）。只描述：每个年代美股熊里用到的窗口数、拿核心的美国交易日、核心换仓笔数、每年收益差；
  1987〜2000 只有核心（第 5 轮 old_core 同一个合成价与口径；前一天收盘的状态决定当天）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次，「同样多、同样形状的随机改动」那时写定。
事前预期（照实写）：每个窗口毛收益若有文献的 +0.5% 左右，扣掉来回约 0.15〜0.3% 的成本后剩不多；熊市里的大跌窗口（例 2008-12-01 −9%）会加深回撤
  → 第一关约 20%、第二关约 35%，「更好候选」约 7%。
运行：python scripts/loop2_r07_tomcore.py（第一关）。输出 var/out/loop2_r07_tomcore.md / .json。非投资建议。
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

ROUND = 7
IDS = ("TOMB",)
FAMILY = "核心·熊市日历"
POSTHOC = False
OLD = R5.OLD
OUT = "loop2_r07_tomcore"


# ───────────────────────── 规则（纯函数，tests/test_loop2_r07.py） ─────────────────────────
def tom_flags(days: pd.DatetimeIndex) -> pd.Series:
    """美国交易日 → 是不是「月末月初」的决定日：每个月最后一个交易日 L 的前一天与 L、下个月第 1、2 个交易日（持有 L、F1、F2、F3 四天的收益）。
    最后一个月（还没有下个月的日子）只标到已有的日子。"""
    d = pd.DatetimeIndex(days).sort_values().unique()
    ym = d.year * 12 + d.month
    first = np.r_[True, ym[1:] != ym[:-1]]                                    # 每个月第 1 个交易日
    last = np.r_[ym[1:] != ym[:-1], True]                                     # 每个月最后一个交易日
    n = len(d)
    out = np.zeros(n, dtype=bool)
    for k in np.flatnonzero(last):
        for j in (k - 1, k):
            if 0 <= j < n:
                out[j] = True
    for k in np.flatnonzero(first):
        if k == 0:
            continue                                                         # 第一个月的月初没有前一个月末
        for j in (k, k + 1):
            if j < n:
                out[j] = True
    return pd.Series(out, index=d)


def bear_eff(bear: pd.Series, flags: pd.Series) -> pd.Series:
    """核心用的「熊」= 美股熊 且 不是标记日（按 bear 的日期；标记缺的日子 = 假）。"""
    b = bear.astype(bool)
    f = flags.astype(float).reindex(b.index).fillna(0.0) > 0.5
    return pd.Series(b.to_numpy() & ~f.to_numpy(), index=b.index)


def tomb_over(W: dict, flags: pd.Series, uni: pd.Series) -> dict:
    """B1 的接法（loop_r04_yensurge.fxh_over：对冲中 → 2845，否则 1545）里把「美股熊」换成 bear_eff。"""
    import loop_r04_yensurge as Y
    return Y.fxh_over(W, bear_eff(W["bear"]["US"], flags), uni, Y.hedged_frame(W["inp"]))


def old_core(W: dict, uni: pd.Series, flags: pd.Series | None) -> dict:
    """只描述：1987〜2000 只有核心（第 5 轮 old_core 同一个合成价与口径）；flags = 月末月初标记（None = B1），前一天收盘的状态决定当天。"""
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
    tom = (flags.astype(float).reindex(idx).fillna(0.0) > 0.5).to_numpy() if flags is not None else np.zeros(len(idx), dtype=bool)
    n = len(idx)
    eq = np.ones(n)
    pu0 = ph0 = 0.0
    held_bear = 0
    for t in range(1, n):
        x = 0.0 if (bear[t - 1] and not tom[t - 1]) else 1.0
        held_bear += int(bear[t - 1] and tom[t - 1])
        pu, ph = (0.0, x) if hdg[t - 1] else (x, 0.0)
        turn = abs(pu - pu0) + abs(ph - ph0)
        eq[t] = eq[t - 1] * (1 + pu * ru[t] + ph * rh[t] - turn * HW.SWITCH_COST / 100)
        pu0, ph0 = pu, ph
    out = EI.curve_stats(pd.Series(eq, index=idx))
    out["bear_days_held"] = held_bear
    return out


def describe(W: dict, e: str, flags: pd.Series, n_core: tuple[int, int]) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    bus = W["bear"]["US"].astype(bool)
    m = (bus.index >= pd.Timestamp(a)) & ((bus.index < pd.Timestamp(b)) if b else True)
    bb = bus[m]
    f = flags.astype(float).reindex(bb.index).fillna(0.0) > 0.5
    use = bb & f
    months = sorted({(d.year, d.month) for d in use.index[use.to_numpy()]})
    return {"bear_days": int(bb.sum()), "flag_days_in_bear": int(use.sum()), "months_touched": len(months),
            "core_trades": {"B1": n_core[0], "TOMB": n_core[1]}}


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r07_tomcore.py", "scripts/loop2_r05_ddbrake.py",
                                 "scripts/loop2_common.py", "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    flags = tom_flags(W["bear"]["US"].index)
    ov = tomb_over(W, flags, uni)
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
    old = {"B1": old_core(W, uni, None), "TOMB": old_core(W, uni, flags)}
    s1 = {"TOMB": R2.stage1(cand, base)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"TOMB": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["TOMB"]
    L = [f"# 第二个研究循环第 7 轮：美股熊市里只在月末月初拿核心 TOMB（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r07_tomcore.py 开头）", "",
         f"- **TOMB（美股熊时，每月最后 1 个 + 头 3 个美国交易日拿核心，其余现金）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | TOMB（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TOMB'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：美股熊的美国交易日 {d['bear_days']} 天，其中标记日 {d['flag_days_in_bear']} 天（{d['months_touched']} 个月）；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → TOMB {d['core_trades']['TOMB']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["TOMB"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（TOMB − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心，只描述）：B1 {oc(o['B1'])}；TOMB {oc(o['TOMB'])}（美股熊里拿核心 {o['TOMB']['bear_days_held']} 天）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 7 轮：TOMB 美股熊市里只在月末月初拿核心")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
