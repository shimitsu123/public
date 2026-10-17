"""hike_gate_study.py — 「加息预期代理 ≥ 80 分位 → 闲置资金空仓」（2026-10-01 登记；先提交后只跑一次，看完不改规则）。

用户（2026-10-01）：「把加息预期 ≥ 80 分位 → 闲置资金空仓 登记做研究」。
来由：risk_param_direction_study（登记 20e0b46、结果 a5ee5f7）的 A 段描述：加息预期代理 = 美 2 年国债 − 联邦基金利率（FRED DGS2 − DFF；市场风险报告
  fed_hike_prob 的长历史代理）在自己过去 10 年的 80〜100 分位时，之后 60 个东证日纳指 1545（合成日元价）在 E / J 两段都为负（−5.03% / −0.93%），
  是 66 组里唯一两段都为负的「不该买」档；2026-09-29 它在 93 分位。那次它不在 B 段的规则里 → 这次单独登记做账户级检验。
照实写（事前）：这个信号是在同一份数据、同两个窗口上**看结果之后**挑出来的（A 段的 11 参数 × 5 档 × 3 方向 = 165 个档里挑最差的一个）→
  本研究不是「没看过的检验」，只是把它放进真实账户框架（个股层 + 费用 + 一手）并用安慰剂（循环平移）看它是否超过随机；
  E / J 两段都要过，E 的高档几乎都是 2006〜07、J 的高档主要是 2022〜23 与 2025〜26 → 各只有一两段独立样本。
零 信号：hike = DGS2 − DFF（日期 = 数据的日期）；百分位 = 在自己过去 10 年（2520 个观测、至少 1260）里的位置（rolling rank，只用过去）；东证日 t 用
   「日期 ≤ 前一个东证日」的值（DFF 在美国次日上午才公布 → 比引擎里美股牛熊分界的时点再保守一天；实时实现同一取法）。
一 账户：与 equity_idle_study 相同（近似时点日経225 突破 4 × 25%、W2、离场 X6、新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜、立花个别コース、当时的一手；
   判断层与 HALT 没有历史不在里面）；闲置资金 = Q1（合成 1545 + 美股牛熊分界 = equity_idle_study 的 spec_a("Q1")）= 基准 G0。
   窗口 E 2006-10〜2016-09、J 2017-01〜（判定）；Z 2001〜2006-09 只描述。
二 候选（闲置资金那份 = 熊 或 闸门开 → 现金；个股层不动；引擎里 = 1545 的 core_index 指向另外的牛熊键 = 美股熊 ∨ 闸门）：
   G1 每天：百分位 ≥ 80 → 闸门开；< 80 → 关。
   G2 带滞回：≥ 80 开、< 70 才关（减少来回）。
   G3 月度：每月第一个东证日看前一日的百分位 ≥ 80 → 整月开。
   硬检查（运行时先做，不过就停止）：用同一份合成价重算「hike 80〜100 分位 → 60 日纳指前向均值」E / J = −5.03 / −0.93（与 a5ee5f7 记的相差 ≤ 0.05 pp），
   保证数据与上次一致；接线检查：闸门全关时经新键跑出的 Calmar 与 G0 相差 ≤ 0.002（否则停止）。
三 判定（事先写定；E、J 两段都要，与 G0 比；四条全过才通过）：(a) Calmar ≥ G0 + 0.03；(b) 最大回撤比 G0 深不超过 2 pp（恰好 2.00 算过）；
   (c) 年化 ≥ G0 − 1.0 pp（不能靠多空仓赢 Calmar）；(d) 安慰剂：把该候选的闸门日序列（2000-01 起）循环平移 ≥ 252 个东证日（30 个种子、账户级同一框架）→
   候选的 Calmar 在 E、J 都 > 安慰剂 95 分位。几个都过 → min(E, J 的 Calmar) 最大的，相差 < 0.02 → 编号小的。
四 通过 → 向用户**提议**把闲置资金规则改成「Q1 + 该闸门」（模拟盘不自动改：要用户在对话里确认；实现 = qbreak/idle_cash 加一个牛熊键「美股熊 ∨ 加息闸门」、
   sim-day 与执行器每天取 FRED DGS2 / DFF、测试、演练之后生效）；不过 → 模拟盘不变，只汇报。
五 另报（只描述）：闸门开着的交易日比例（E / J / Z）、每年开关次数、开着 / 关着时 1545 的日元日收益年化（各窗口）、各年收益差（候选 − G0）、
   闸门开着的连续区间（起止）、现在的读数（值、百分位、闸门状态）。
六 事前预期（照实写）：信号是事后挑的 → 账户级两段都过约 40%（G1）/ 40%（G2）/ 35%（G3），至少一个通过约 50%；最可能卡在 (d)（E 段高档集中在 2006〜07，
   平移到别的两年也可能「躲过」2008 前的一段）与 (c)（J 段闸门开着时纳指也涨的年份）。
七 照实写：只有两个判定窗口、各一两段独立样本；信号事后挑的；合成 1545 比真实乐观约 1 pp / 年（G0 与候选同一做法，比较不受影响）；DGS2 − DFF 是
   fed_hike_prob 的代理不是它本身；税前。非投资建议。
登记前的检查：tests/test_hike_gate_study.py（闸门三种构造、循环平移保持开着的天数、判定四条与入选、硬检查函数）。
输出：var/out/hike_gate_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

START = "2000-01-01"
TAGS = ("E", "J", "Z")
JUDGE = ("E", "J")
GATES = ("G1", "G2", "G3")
GLABEL = {"G0": "Q1 现行（1545 + 美股牛熊）", "G1": "Q1 + 闸门（每天 ≥ 80）", "G2": "Q1 + 闸门（≥ 80 开 / < 70 关）", "G3": "Q1 + 闸门（月度 ≥ 80）"}
ON, OFF = 80.0, 70.0
CALMAR_UP, DD_TOL, CAGR_TOL, TIE = 0.03, 2.0, 1.0, 0.02
SEEDS, SHIFT_MIN = 30, 252
CHECK = {"E": -5.03, "J": -0.93}
CHECK_TOL = 0.05
KEY = "USHG"                                                                  # 引擎里的牛熊键：美股熊 ∨ 加息闸门


# ────────────────────────── 信号 ──────────────────────────
def hike_series() -> pd.Series:
    from qbreak import factors
    return (factors.fred("DGS2") - factors.fred("DFF")).dropna().sort_index()


def hike_pct(days: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """(东证日上的百分位（前一日）, 原始序列)。"""
    import risk_param_direction_study as R
    h = hike_series()
    return R.align_prev(R.pct_rank(h), days), h


def month_starts(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(days, index=days)
    return pd.DatetimeIndex(s.groupby([days.year, days.month]).first().values)


def gate(kind: str, pct: pd.Series) -> pd.Series:
    """闸门（True = 开 = 闲置资金留现金）；百分位缺 → 关。"""
    p = pct.copy()
    if kind == "G1":
        return (p >= ON).fillna(False).astype(bool)
    if kind == "G2":
        out = np.zeros(len(p), bool)
        on = False
        v = p.to_numpy(float)
        for i, x in enumerate(v):
            if np.isnan(x):
                out[i] = on
                continue
            if not on and x >= ON:
                on = True
            elif on and x < OFF:
                on = False
            out[i] = on
        return pd.Series(out, index=p.index)
    if kind == "G3":
        ms = month_starts(p.index)
        g = pd.Series(np.nan, index=p.index, dtype=object)
        g[ms] = (p.reindex(ms) >= ON).fillna(False).to_numpy(bool)
        return g.ffill().fillna(False).astype(bool)
    raise KeyError(kind)


def combined_bear(us_bear: pd.Series, g: pd.Series) -> pd.Series:
    """美股熊（引擎的时点：日期 ≤ t）∨ 闸门（前一日）→ 东证日上的布尔序列。"""
    b = us_bear.astype(float).reindex(us_bear.index.union(g.index)).ffill().reindex(g.index).fillna(1.0) > 0.5
    return (b | g).astype(bool)


def circular_shift(g: pd.Series, k: int) -> pd.Series:
    return pd.Series(np.roll(g.to_numpy(bool), k), index=g.index)


# ────────────────────────── 硬检查 ──────────────────────────
def hard_check(inp: dict, pct: pd.Series) -> dict:
    """同一份合成价：hike 80〜100 分位 → 60 日纳指前向均值（E / J）与登记值比。"""
    import risk_param_direction_study as R
    px = R.direction_prices(inp)
    fr = (px["N"].shift(-60) / px["N"] - 1) * 100
    p = pct.reindex(px.index)
    out = {}
    for t in JUDGE:
        m = R.in_win(px.index, t) & (p >= 80) & fr.notna()
        out[t] = round(float(fr[m].mean()), 2)
    out["ok"] = all(abs(out[t] - CHECK[t]) <= CHECK_TOL for t in JUDGE)
    return out


# ────────────────────────── 账户级 ──────────────────────────
def spec(fr: dict, bear_key: pd.Series) -> dict:
    return {"cfg_over": {"core": {"1545.T": 1.0}, "core_index": {"1545.T": KEY}, "core_mode": "split"},
            "extra_core": {"1545.T": fr["1545.T"]}, "extra_bear": {KEY: bear_key}}


def verdict(acct: dict, k: str) -> tuple[bool, list[str]]:
    fails = []
    for t in JUDGE:
        a, b = acct[t][k], acct[t]["G0"]
        if a["calmar"] is None or b["calmar"] is None or a["calmar"] < b["calmar"] + CALMAR_UP - 1e-12:
            fails.append(f"a:{t}")
        if a["dd"] < b["dd"] - DD_TOL - 1e-9:
            fails.append(f"b:{t}")
        if a["cagr"] < b["cagr"] - CAGR_TOL - 1e-9:
            fails.append(f"c:{t}")
        p95 = a.get("placebo95")
        if p95 is not None and a["calmar"] is not None and a["calmar"] <= p95:
            fails.append(f"d:{t}")
    return (not fails), fails


def pick(acct: dict) -> tuple[str | None, dict]:
    res, passed = {}, []
    for k in GATES:
        ok, fails = verdict(acct, k)
        res[k] = {"pass": ok, "fails": fails}
        if ok:
            passed.append(k)
    if not passed:
        return None, res
    key = {k: min(acct[t][k]["calmar"] for t in JUDGE) for k in passed}
    best = max(key.values())
    return sorted([k for k in passed if best - key[k] < TIE], key=lambda k: int(k[1:]))[0], res


def on_share(g: pd.Series, a: str, b: str | None) -> float:
    m = (g.index >= pd.Timestamp(a)) & ((g.index <= pd.Timestamp(b)) if b else True)
    return round(float(g[m].mean() * 100), 1)


def switches_py(g: pd.Series, a: str, b: str | None) -> float:
    m = (g.index >= pd.Timestamp(a)) & ((g.index <= pd.Timestamp(b)) if b else True)
    x = g[m].astype(int)
    yrs = (x.index[-1] - x.index[0]).days / 365.25
    return round(float(x.diff().abs().sum() / yrs), 2)


def on_off_ret(px_n: pd.Series, g: pd.Series, a: str, b: str | None) -> dict:
    """闸门开着 / 关着的日子 1545 的日元日收益年化（%）。"""
    r = px_n.pct_change()
    m = (r.index >= pd.Timestamp(a)) & ((r.index <= pd.Timestamp(b)) if b else True)
    r, gg = r[m], g.reindex(r.index)[m].fillna(False)
    out = {}
    for lab, mm in (("on", gg), ("off", ~gg)):
        x = r[mm].dropna()
        out[lab] = round(float(x.mean() * 252 * 100), 2) if len(x) >= 20 else None
        out[f"n_{lab}"] = int(len(x))
    return out


def on_spans(g: pd.Series) -> list[tuple[str, str]]:
    x = g.astype(int)
    d = x.diff().fillna(x.iloc[0])
    starts = list(x.index[d == 1])
    ends = list(x.index[d == -1])
    if len(ends) < len(starts):
        ends.append(x.index[-1])
    return [(str(s.date()), str(e.date())) for s, e in zip(starts, ends)]


def main() -> int:
    import equity_idle_study as EI
    import leap_confirm as LF
    import pit_retrain_study as PRS
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    inp = EI.load_inputs()
    fr, _cl = EI.assets(inp)
    bear = EI.bears(inp)
    n225 = inp["n225"]
    days = n225.index[n225.index >= START]
    pct, raw = hike_pct(days)
    hc = hard_check(inp, pct)
    print(f"硬检查 {hc}", flush=True)
    if not hc["ok"]:
        print("硬检查不过：数据与登记时不一致 → 停止", flush=True)
        (paths.out_dir() / "hike_gate_study.json").write_text(json.dumps({"hard_check": hc, "stopped": True}, ensure_ascii=False), encoding="utf-8")
        return 2
    gates = {k: gate(k, pct) for k in GATES}
    p = load_params(market="JP")
    p0, px6 = SF.no_w2_params(p), EXR.apply(p, "X6")
    acct: dict = {t: {} for t in TAGS}
    years: dict = {t: {} for t in TAGS}
    wiring: dict = {}
    rng = np.random.default_rng(0)
    for tag in TAGS:
        ctx = LF.context(tag)
        fa = LF.frames(ctx, p0)
        run_fn, fw = LF.runner(ctx, fa), LF.with_mask(fa, LF.w2_keep(ctx, fa))
        PRS.PitEngine.DELIST = ctx["delist"]
        r = LF.run(ctx, run_fn, fw, px6, **EI.spec_a("Q1", fr, bear))
        acct[tag]["G0"] = {x: r[tag][x] for x in ("cagr", "dd", "calmar")}
        years[tag]["G0"] = r.get("_years") or {}
        rk = LF.run(ctx, run_fn, fw, px6, **spec(fr, combined_bear(bear["US"], pd.Series(False, index=days))))   # 接线检查：闸门全关 = G0
        wiring[tag] = {"G0": acct[tag]["G0"]["calmar"], "G0k": rk[tag]["calmar"]}
        if rk[tag]["calmar"] is None or acct[tag]["G0"]["calmar"] is None or abs(float(rk[tag]["calmar"]) - float(acct[tag]["G0"]["calmar"])) > 0.002:
            print(f"接线检查不过 {tag}：{wiring[tag]} → 停止", flush=True)
            (paths.out_dir() / "hike_gate_study.json").write_text(json.dumps({"hard_check": hc, "wiring": wiring, "stopped": True}, ensure_ascii=False, default=str), encoding="utf-8")
            return 2
        for k in GATES:
            r = LF.run(ctx, run_fn, fw, px6, **spec(fr, combined_bear(bear["US"], gates[k])))
            acct[tag][k] = {x: r[tag][x] for x in ("cagr", "dd", "calmar")}
            years[tag][k] = r.get("_years") or {}
            if tag in JUDGE:
                vals = []
                n = len(gates[k])
                for _ in range(SEEDS):
                    sh = int(rng.integers(SHIFT_MIN, n - SHIFT_MIN))
                    rr = LF.run(ctx, run_fn, fw, px6, **spec(fr, combined_bear(bear["US"], circular_shift(gates[k], sh))))
                    c = rr[tag]["calmar"]
                    vals.append(float(c) if c is not None else 99.0)
                acct[tag][k]["placebo95"] = round(float(np.percentile(vals, 95)), 3)
                acct[tag][k]["placebo_med"] = round(float(np.median(vals)), 3)
        print(f"{tag} 完成（{time.time() - t0:.0f}s）：" + "、".join(f"{k} {acct[tag][k]['calmar']}" for k in ("G0",) + GATES), flush=True)
    win, res = pick(acct)
    ctxw = {t: LF.context(t)["windows"][t] for t in TAGS}
    px_n = fr["1545.T"]["Close"]
    desc = {k: {t: {"on_share": on_share(gates[k], *ctxw[t]), "switch_py": switches_py(gates[k], *ctxw[t]),
                    **on_off_ret(px_n, gates[k], *ctxw[t])} for t in TAGS} for k in GATES}
    spans = {k: on_spans(gates[k]) for k in GATES}
    ydiff = {k: {t: {y: round(float(years[t][k][y]) - float(years[t]["G0"][y]), 2) for y in years[t][k] if y in years[t]["G0"]} for t in JUDGE} for k in GATES}
    now = {"date": str(raw.index[-1].date()), "hike": round(float(raw.iloc[-1]), 3), "pct10y": round(float(pct.dropna().iloc[-1]), 1),
           "tse_day": str(pct.dropna().index[-1].date()), "gate": {k: bool(gates[k].iloc[-1]) for k in GATES},
           "us_bear": bool(bear["US"].iloc[-1])}
    out = {"as_of": str(days[-1].date()), "hard_check": hc, "wiring": wiring, "accounts": acct, "verdicts": res, "winner": win, "desc": desc, "spans": spans,
           "year_diff": ydiff, "now": now, "windows": ctxw}
    od = paths.out_dir()
    od.mkdir(parents=True, exist_ok=True)
    (od / "hike_gate_study.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_report(out, od / "hike_gate_study.md")
    print(f"winner={win}  now={now}  （{time.time() - t0:.0f}s）", flush=True)
    return 0


def _f(v, f="{:.2f}") -> str:
    return "—" if v is None else f.format(v)


def write_report(o: dict, path: Path) -> None:
    win, now = o["winner"], o["now"]
    L = [f"# 「加息预期代理 ≥ 80 分位 → 闲置资金空仓」研究（数据到 {o['as_of']}）", "",
         "登记见 scripts/hike_gate_study.py 的说明与 var/sim_changes.md；只运行一次。**非投资建议。**", "",
         "## 结论",
         f"- {'**通过并入选 ' + win + '**（' + GLABEL[win] + '）→ 向用户提议（模拟盘不自动改）' if win else '**没有一个通过**（四条判定见下）→ 模拟盘不变（闲置资金仍是 Q1）'}",
         f"- 硬检查：hike 80〜100 分位 → 60 日纳指前向均值 E {o['hard_check']['E']}% / J {o['hard_check']['J']}%（登记值 −5.03 / −0.93）→ {'一致' if o['hard_check']['ok'] else '不一致'}；"
         f"接线检查（闸门全关 = G0 的 Calmar）：{o['wiring']}",
         f"- 现在（{now['date']} 的值、{now['tse_day']} 的东证日读数）：2 年 − 联邦基金 = {now['hike']} pp、10 年百分位 {now['pct10y']}；闸门 " +
         "、".join(f"{k} {'开' if v else '关'}" for k, v in now["gate"].items()) + f"；美股牛熊分界 {'熊' if now['us_bear'] else '牛'}", "",
         "## 账户级（同一框架；年化 % / 最大回撤 % / Calmar；Z 只描述）", "",
         "| 候选 | E 年化 | E 回撤 | E Calmar | J 年化 | J 回撤 | J Calmar | Z Calmar | 安慰剂95 E / J（中位） | 判定 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k in ("G0",) + GATES:
        a = {t: o["accounts"][t][k] for t in TAGS}
        v = o["verdicts"].get(k)
        vs = ("**通过**" if v["pass"] else "不过 " + ",".join(v["fails"])) if v else "基准"
        pl = " / ".join(f"{_f(a[t].get('placebo95'), '{:.3f}')}（{_f(a[t].get('placebo_med'), '{:.3f}')}）" for t in JUDGE) if k != "G0" else "—"
        L.append(f"| {k} {GLABEL[k]} | {_f(a['E']['cagr'])} | {_f(a['E']['dd'])} | {_f(a['E']['calmar'], '{:.3f}')} | {_f(a['J']['cagr'])} | {_f(a['J']['dd'])} | "
                 f"{_f(a['J']['calmar'], '{:.3f}')} | {_f(a['Z']['calmar'], '{:.3f}')} | {pl} | {vs} |")
    L += ["", "判定：a Calmar ≥ G0 + 0.03；b 回撤不比 G0 深 2 pp；c 年化 ≥ G0 − 1 pp；d Calmar > 闸门循环平移（≥ 252 日、30 种子）安慰剂 95 分位；E、J 都要。", "",
          "## 闸门的描述（开着的交易日 %、每年开关次数、开 / 关时 1545 日元收益年化 %）", "",
          "| 候选 | 窗口 | 开着 % | 开关/年 | 开着时年化 (n) | 关着时年化 (n) |", "|---|---|---|---|---|---|"]
    for k in GATES:
        for t in TAGS:
            d = o["desc"][k][t]
            L.append(f"| {k} | {t} | {d['on_share']} | {d['switch_py']} | {_f(d['on'])} ({d['n_on']}) | {_f(d['off'])} ({d['n_off']}) |")
    L += ["", "## 闸门开着的区间（G1）", "", "、".join(f"{a}〜{b}" for a, b in o["spans"]["G1"]) or "（无）", "",
          "## 各年收益差（候选 − G0，pp）", ""]
    for k in GATES:
        for t in JUDGE:
            yd = o["year_diff"][k][t]
            L.append(f"- {k} {t}：" + "、".join(f"{y} {v:+.1f}" for y, v in yd.items()))
    L += ["", "照实写：信号是在同一份数据上看结果之后挑的（165 个档里最差的一个），本研究只是账户级 + 安慰剂的确认，不是没看过的检验；E 段高档集中在 2006〜07、"
          "J 段在 2022〜23 与 2025〜26；DGS2 − DFF 是 fed_hike_prob 的代理；合成 1545；税前。非投资建议。"]
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
