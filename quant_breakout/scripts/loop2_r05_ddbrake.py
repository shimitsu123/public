"""loop2_r05_ddbrake.py — 第二个研究循环第 5 轮：「账户回撤刹车」DDB（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 5 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py。
为什么挑这个题（照实写）：
  - 循环规则要优先闲置资金以外的层（离场、仓位、执行、风险层）。选题前核对过 var/sim_changes.md 与研究总图：核心的择时（波动率 VT20、
    急跌熔断 CPX、纳指自己的牛熊 HBOR / NDA / NDR、分批切换 TR3、晚卖守卫）、熊市里的币种 / 避险资产（BXU、R10、TBH / TBJ / TBU）、
    威胁指数当开关（三次否定）、汇率对冲都做过；「按账户自己的回撤减仓」没做过（qbreak/risk.py 只有 45% 回撤 HALT，回测里没有）。
  - B1 的 Calmar 由每个年代最深的一次回撤决定（Z −14.71%、E −19.70%、J −26.97%）；牛熊分界反应慢，牛市里的急跌只能等它翻熊。
    以前「更快离场」的做法（T7〜T15、VT20、CPX）输在 V 形反弹里回来太晚、来回换。
  - 这一轮的设计不预测，只看账户自己跌了多少：跌破那条线就把核心减一半，**回到同一条线就恢复**（没有滞后带）→ 线下面继续跌的那段少亏一半、
    涨回那条线的那段也少赚一半，一来一回大致抵消（V 形反弹不吃亏）；一直跌到牛熊分界翻熊则少亏一半 → 预期回撤变浅、收益几乎不变。
    代价：在线附近来回时每次换一半核心的手续费 + 滑点、第二天开盘成交的跳空。
  → 不是事后组合（不是把看过的结果拼起来；两个参数是常见的约定值、没调）→ S7 不适用；1987〜2000 只有核心的结果只描述。
    家族「风险层·账户回撤刹车」1 / 3。
做法 DDB（参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 高点 P：这一段美股牛（B1 的美股牛熊分界）里每天收盘的账户权益的最高值；美股熊的日子清空，熊转牛那天的收盘重新起算
    （熊市里 B1 的核心本来就是现金；不重新起算的话，转牛之后会一直半仓、错过熊市之后的反弹）。
  - 收盘权益 < (1 − 0.10) × P → 第二天开盘起，核心 ETF（2845 / 1545，FJE 照旧决定拿哪一只）的目标 × 0.5（另一半留现金）；
    收盘权益 ≥ 0.90 × P → × 1（= B1）。个股层、判断层、费用全部同 B1（个股仓位按权益的 25%，只随权益间接变化）。
  - 实现：scripts/candle_portfolio.py 的 DDBrake 与 MixEngine.DD_BRAKE（缺省 None = 不变；模拟盘用的 qbreak/unified.py 不动），
    逐日的倍数记在引擎实例的 ddb_log。
  - 接线检查（登记前跑过，见 sim_changes 登记一节）：level = 1（永远不刹）三个年代都与 B1 完全相同；1987〜2000 只有核心不刹 = B1 的 0.454。
第一关：research_loop2.stage1（trade = None、lenses = None、posthoc = None）。
只描述（不参与判定）：每个年代美股牛的日子里刹车的比例、刹车段数与最长几段、核心换仓笔数、每年收益差；
  1987〜2000 只有核心（日元计纳指 + FJE + 同一个刹车；fxhedge_study.core_only 的口径：前一天收盘决定当天，换仓扣 0.1% × 换的比例）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次，「同样多、同样形状的随机改动」那时写定。
事前预期（照实写）：J 的 2020-02〜03 与 2025-02〜04、Z 的回撤段如果在一段牛里面，回撤会浅几个 pp；E 的最深回撤（2010〜2012）跨了几段牛熊，
  刹车每段重新起算、可能帮不上；在线附近来回的成本难估 → 第一关约 35%、第二关约 35%，「更好候选」约 12%。
运行：python scripts/loop2_r05_ddbrake.py（第一关）。输出 var/out/loop2_r05_ddbrake.md / .json。非投资建议。
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
import research_loop2 as R2                                                  # noqa: E402

ROUND = 5
IDS = ("DDB",)
FAMILY = "风险层·账户回撤刹车"
POSTHOC = False
LEVEL, MULT = 0.10, 0.5
BRAKE = {"level": LEVEL, "mult": MULT}
OLD = ("1987-01-01", "2000-12-31")
OUT = "loop2_r05_ddbrake"


# ───────────────────────── 规则与描述（纯函数，tests/test_loop2_r05.py） ─────────────────────────
def brake_series(eng) -> pd.Series:
    """引擎实例逐日的刹车倍数（日期 → 倍数；没开刹车 → 空）。"""
    log = getattr(eng, "ddb_log", None) or []
    return pd.Series([m for _, m in log], index=pd.DatetimeIndex([d for d, _ in log]), dtype=float)


def segments(mult: pd.Series) -> list[tuple[str, str, int]]:
    """倍数 < 1 的连续段：[(起, 止, 天数)]（按日期顺序）。"""
    on = (mult < 1.0 - 1e-9).to_numpy()
    out, k = [], 0
    while k < len(on):
        if on[k]:
            j = k
            while j + 1 < len(on) and on[j + 1]:
                j += 1
            out.append((str(mult.index[k].date()), str(mult.index[j].date()), j - k + 1))
            k = j + 1
        else:
            k += 1
    return out


def describe(W: dict, e: str, mult: pd.Series, n_core: tuple[int, int]) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    m = mult[(mult.index >= pd.Timestamp(a)) & ((mult.index < pd.Timestamp(b)) if b else True)]
    bus = W["bear"]["US"].astype(float).reindex(m.index.union(W["bear"]["US"].index)).ffill().reindex(m.index).fillna(0.0) > 0.5
    bull = m[~bus.to_numpy()]
    seg = segments(m)
    return {"bull_days": int(len(bull)), "brake_pct_of_bull": round(float((bull < 1.0 - 1e-9).mean() * 100), 1) if len(bull) else None,
            "n_segments": len(seg), "longest": sorted(seg, key=lambda x: -x[2])[:6], "core_trades": {"B1": n_core[0], "DDB": n_core[1]}}


def core_trades(e: str, W: dict) -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    return int(sum(1 for x in eng.st.core_trades if x[0] >= a and (b is None or x[0] < b)))


def old_core(W: dict, uni: pd.Series, brake: dict | None) -> dict:
    """只描述：1987〜2000 只有核心（日元计纳指；对冲中 → 对冲版；美股熊 → 现金），前一天收盘决定当天、换仓扣 0.1% × 换的比例
    （第 1 轮 old_core 同一个合成价与口径）；brake = 同一个 DDBrake 用在这条净值上（None = B1）。"""
    import candle_portfolio as CP
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
    bk = CP.DDBrake(brake["level"], brake["mult"]) if brake else None
    n = len(idx)
    eq, braked = np.ones(n), np.zeros(n, dtype=bool)
    pu0 = ph0 = 0.0
    m = bk.update(1.0, bool(bear[0])) if bk else 1.0
    for t in range(1, n):
        x = (0.0 if bear[t - 1] else 1.0) * m                               # 前一天收盘决定当天的比例
        pu, ph = (0.0, x) if hdg[t - 1] else (x, 0.0)
        turn = abs(pu - pu0) + abs(ph - ph0)
        eq[t] = eq[t - 1] * (1 + pu * ru[t] + ph * rh[t] - turn * HW.SWITCH_COST / 100)
        pu0, ph0 = pu, ph
        m = bk.update(eq[t], bool(bear[t])) if bk else 1.0
        braked[t] = m < 1.0
    out = EI.curve_stats(pd.Series(eq, index=idx))
    bull = ~bear
    out["brake_pct_of_bull"] = round(float(braked[bull].mean() * 100), 1) if bull.any() else None
    return out


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py",
                                 "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import jq_study as JS
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, dd_brake=dict(BRAKE))
        nc = core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, brake_series(JS.RealLotEngine.LAST[-1]), (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, None), "DDB": old_core(W, uni, dict(BRAKE))}
    s1 = {"DDB": R2.stage1(cand, base)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "brake": BRAKE, "code": code, "dirty": dirty,
           "base": base, "cand": {"DDB": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old,
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["DDB"]
    L = [f"# 第二个研究循环第 5 轮：账户回撤刹车 DDB（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r05_ddbrake.py 开头）", "",
         f"- **DDB（这一段美股牛里账户离高点 ≥ 10% → 核心 × 0.5，回到线上恢复）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | DDB（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['DDB'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        lg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in d["longest"]) or "无"
        L.append(f"- {e}：美股牛的日子里刹车 {_f(d['brake_pct_of_bull'], '{:.1f}')}%（{d['n_segments']} 段；最长的几段 {lg}）；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → DDB {d['core_trades']['DDB']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["DDB"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（DDB − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心，只描述）：B1 {oc(o['B1'])}；DDB {oc(o['DDB'])}（美股牛的日子里刹车 {o['DDB']['brake_pct_of_bull']}%）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 5 轮：DDB 账户回撤刹车")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
