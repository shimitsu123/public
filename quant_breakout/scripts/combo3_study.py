"""combo3_study.py — 选股第三轮：让关联搭配 C 更稳（2026-10-01 登记；提交后不改规则、只运行一次）。

用户（2026-10-01）：「继续根据现在所有的研究结果优化现在的选股方法」。
来由：第二轮（scripts/combo2_study.py，登记 92e2ef2、结果 8cec269）发现 C 选出哪些特征对「学习样本怎么切」很敏感 ——
  留一年代用 Z、E 两个完整年代学时，考 2017〜2026 每笔 +0.97 pp；换成「只用过去、按日期切两半」学时只剩 +0.13 pp、2021-06 以后 −0.10 pp。
  一份规则的好坏取决于切法 = 方差大；统计上降低这种敏感性的标准做法有两种，这一轮各做一个，并要求「两种检验都过」：
  CB 袋装 C（bagging）：把学习样本的日历年随机分成两组（按信号数尽量各半）50 次，每次按 C 同一做法学一份规则；
     新信号由 50 份规则投票，说「跳过」的 ≥ 一半才跳过（这一格没学出规则的那份 = 保留）。
  CS 稳定选择 C（stability selection）：同样 50 种切法，每个市场格里「两组同号且 |ρ| ≥ 0.05」的次数占比 ≥ 0.6 的特征才入选
     （方向取多数），切点 / 门槛用全部学习样本 → 一份和 C 同样形式的规则（可以直接换进 qbreak/combo_c.py）。
  C 的其余做法不动（市场格 = 日経 200 日线上下 × VIX ≥ 20；每组每格 ≥ 60 笔；特征 = 43 个个股特征；切点三等分；门槛 = 学习样本分数的 1/3 分位），
  函数用 scripts/combo_all_common.py 的同一组；随机切法的种子写定（scripts/combo3_common.py SEED）。
数据与 combo_all_study / combo2_study 完全相同（今天的日経225：Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09 的 W2 信号；
W 扩大池 2006〜2016、Jx 时点 TOPIX 1000 非日経225 2017〜 只检验；X6 单笔结果；账户框架 S0C2 + W2、X6、核心 1655 + 牛熊）。

〇 先决条件：重建的样本里，C（留一年代）的保留数、胜率差、每笔差与登记运行 7f2ca59 一致；不一致 → 停下、只报告。
一、检验甲「留一年代」（与 combo_all_study 同一套判定，对照 = 只有 W2）：每个年代用另外两个年代学（CB / CS 在这两个年代的年份上随机切）；
   W 用 E 那一折、Jx 用 J 那一折。
   D1 每个年代胜率差、每笔差都 ≥ 0；D2 三年代合并胜率差 ≥ +2.0 pp、每笔差 ≥ +0.20 pp 且 > 「股票 × 周」随机 95 分位（200 次）；
   D3 W、Jx 都 ≥ 0；D4a 账户 Z / E / J 各 ≥ 只有 W2 − 0.02、回撤不深 2 pp、合计 ≥ +0.03；D4b 合计 > 随机跳过同样比例（30 次）的 95 分位（D1〜D3 都过才跑）。
二、检验乙「逐年前推」（与 combo2_study N3 同一套判定，对照 = 只有 W2）：每一年 Y 只用信号日 ≤ Y 年 1 月 1 日 − 120 天的信号学，用在 Y 年；
   「有规则的年份」= CB：50 份里至少一半学出规则；CS：学出规则。
   F1 有规则的年份合并胜率差 ≥ +2.0 pp、每笔差 ≥ +0.20 pp 且 > 随机 95 分位；F2 有规则的信号按日期中位数切两半，每笔差都 ≥ 0；
   F3 W、Jx（用同一年只学日経225 的规则）胜率差、每笔差都 ≥ 0；F4 账户 E、J 各 ≥ 只有 W2 − 0.02、回撤不深 2 pp、合计 ≥ +0.02，且 > 随机跳过 95 分位（F1〜F3 都过才跑）。
三、判定：甲、乙都过 = 通过 → 提议用它在 Z + E + J 全部学出的规则代替现在冻结的 C（要用户在对话里确认、记 sim_changes；前向记录第十二节改记新规则的列）；
   CB、CS 都通过 → 提议两种检验账户合计（甲 D4 合计 + 乙 F4 合计）大的那个。只过一种 = 方向一致（只记录）；都不过 = 不通过，C 照旧。
四、只描述（不参与判定）：现在的 C 在两种检验下的同样数字（甲 = 登记运行、乙 = 第二轮 N3）作对照；稳定性表（平静的牛市那一格每个特征的入选占比：
   Z + E + J 全部、每一折、逐年前推的 2016 / 2021 / 2026）；CB / CS 用 Z + E + J 全部学出的规则。
事前预期（照实写）：CB、CS 各约 15% 通过。理由：袋装 / 稳定选择能去掉「切法运气」，但也会把 J 那一折里起作用的 r12、upper、us12 平均掉；
  第二轮逐年前推每年都选到的只有 vexp+、rng−、atrp−。
运行：python scripts/combo3_study.py（约 20〜40 分钟）；QBREAK_SMOKE=1 只用每批十几只票静默跑一遍流程（不打印任何差、不写文件）。
输出 var/out/combo3_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import combo2_common as C2                                                   # noqa: E402
import combo2_study as S2                                                    # noqa: E402
import combo3_common as C3                                                   # noqa: E402
import combo_all_common as CA                                                # noqa: E402
import combo_all_study as CS                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

YEARS = list(range(2002, 2027))
SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
LINES: list[str] = []
QUIET = False
VARIANTS = {"CB": "袋装 C（50 种切法的规则投票）", "CS": "稳定选择 C（入选占比 ≥ 0.6 的特征）"}


def say(s: str = "") -> None:
    if QUIET:
        return
    print(s, flush=True)
    LINES.append(s)


fmt = CS.fmt


def fit(v: str, T: pd.DataFrame):
    if v == "CB":
        return C3.fit_bag(T)
    if v == "CS":
        return C3.fit_stable(T)
    return CA.fit_c([T])                                                       # 不用


def keep_of(v: str, rules, X: pd.DataFrame) -> np.ndarray:
    return C3.apply_bag(rules, X) if v == "CB" else CA.apply_c(rules, X)


def active(v: str, rules) -> bool:
    return C3.bag_active(rules) >= 0.5 if v == "CB" else C2.active(rules)


def rule_text(v: str, rules) -> str:
    if v == "CB":
        return f"{len(rules)} 份规则，学出规则的占 {C3.bag_active(rules):.0%}"
    return C2.rule_features(rules)


def main() -> int:
    import combo_all_posthoc as PH
    import leap_confirm as LF
    import sell_confirm as SCF
    import wvol_placebo as WP
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    global QUIET
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/combo3_study.py", "scripts/combo3_common.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 选股第三轮：让关联搭配 C 更稳（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}{'；冒烟检查' if SMOKE else ''}）")
    say("规则见 scripts/combo3_study.py 开头（先提交后运行）；两种学法 scripts/combo3_common.py；C 的做法 scripts/combo_all_common.py。")
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    px = EXR.apply(p, "X6")
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    n225_today = set(universe("JP", "broad"))
    smoke_names = list(universe("JP", "broad"))[:CS.SMOKE_N] if SMOKE else None
    assert EXR.mode_of(cfg, "JP") == "X6", "现行离场应是 X6（var/sim.json exits）"

    say("\n## 〇、样本与复现")
    SM = CS.load_samples(p0, smoke_names)
    if SMOKE:
        only = set(smoke_names) | set(SM["W"]["fa"]) | set(SM["J2"]["fa"])
        B = CS.feature_base(p0, sorted(only))
        D, A = {}, {}
        for s in CS.SAMPLES:
            a, b = CS.WIN[s]
            src = SM["J2"] if s == "Jx" else SM[s]
            S = CS.signals(src["fa"], src["keep"], src["mem"], a, b, exclude=n225_today if s == "Jx" else None)
            A[s] = CS.add_features(S, src["fa"], B)
            D[s] = CS.outcomes(A[s], src["fa"], p0, bt, rt)
    else:
        D, A, _ = PH.build_panel()
    RC = {e: CA.fit_c([D[x] for x in CA.ERAS if x != e]) for e in CA.ERAS}
    RC_OF = {**RC, "W": RC["E"], "Jx": RC["J"]}
    reg = json.loads((paths.out_dir() / "combo_all_study.json").read_text(encoding="utf-8")) if not SMOKE else None
    ok_rep = True
    for s in CS.SAMPLES:
        dd = CA.delta(D[s]["net"], CA.apply_c(RC_OF[s], D[s]))
        if reg is not None:
            r0 = reg["stats"]["C"]["samples"][s]
            same = dd["kept"] == r0["kept"] and dd["n"] == r0["n"] and abs(dd["dwin"] - r0["dwin"]) < 1e-3 and abs(dd["dmean"] - r0["dmean"]) < 1e-3
            ok_rep &= same
            say(f"- {s}：W2 信号 {len(D[s])} 个（全部 {len(A[s])}）；C 复现 {'一致' if same else '★ 不一致'}")
    if not ok_rep:
        say("\n★ 复现不一致 → 按登记停下，不判定。")
        _write(code)
        return 1
    if SMOKE:
        QUIET = True

    say("\n## 一、账户的对照（只有 W2；研究框架 S0C2 + W2、X6、核心 1655 + 牛熊）")
    CTX, BASE = {}, {}
    for e in CA.ERAS:
        src = SM[e]
        ctx, fa = src["ctx"], src["fa"]
        fr_w2 = LF.with_mask(fa, src["keep"])
        run_fn = LF.runner(ctx, fr_w2)
        BASE[e] = S2.acct_row(LF.run(ctx, run_fn, fr_w2, px), e)
        CTX[e] = (ctx, fa, run_fn, fr_w2)
        say(f"- {e}：{S2.acct_cell(BASE[e])}")

    def acct(e: str, keep_all: np.ndarray) -> dict:
        ctx, fa, run_fn, fr_w2 = CTX[e]
        mk = S2.masks(fa, SM[e]["keep"], S2.pairs(A[e], ~keep_all), [])
        r = S2.acct_row(LF.run(ctx, run_fn, LF.with_mask(fa, mk), px), e)
        r["frac"] = float(np.mean(keep_all)) if len(keep_all) else 1.0
        return r

    def acct_placebo(eras, accs: dict) -> float:
        seeds = 2 if SMOKE else CA.ACCT_SEEDS
        sums = np.zeros(seeds)
        for e in eras:
            ctx, fa, run_fn, fr_w2 = CTX[e]
            for k in range(seeds):
                rr = LF.run(ctx, run_fn, WP.week_lottery(fr_w2, accs[e]["frac"], k), px)
                sums[k] += (rr[e]["calmar"] or 0.0) - BASE[e]["calmar"]
        return float(np.percentile(sums, 95))

    yn = lambda b_: "过" if b_ else "不过"                                      # noqa: E731
    OUT: dict = {"code": code, "base": BASE, "lens1": {}, "lens2": {}, "verdict": {}}

    # ── 检验甲：留一年代 ──
    say("\n## 二、检验甲：留一年代（每个年代用另外两个年代学；对照 = 只有 W2）")
    L1 = {}
    for v in ("C", "CB", "CS"):
        R = RC if v == "C" else {e: fit(v, pd.concat([D[x] for x in CA.ERAS if x != e], ignore_index=True)) for e in CA.ERAS}
        R_OF = {**R, "W": R["E"], "Jx": R["J"]}
        kf = (lambda r, X: CA.apply_c(r, X)) if v == "C" else (lambda r, X, _v=v: keep_of(_v, r, X))
        st = {s: CA.delta(D[s]["net"], kf(R_OF[s], D[s])) for s in CS.SAMPLES}
        pooled = CA.delta(np.concatenate([D[e]["net"].to_numpy(float) for e in CA.ERAS]),
                          np.concatenate([kf(R[e], D[e]) for e in CA.ERAS]))
        pl = CA.pooled_placebo([(D[e]["net"].to_numpy(float), D[e]["ticker"].to_numpy(), D[e]["week"].to_numpy(), st[e]["frac"]) for e in CA.ERAS])
        ACC = {e: acct(e, kf(R[e], A[e])) for e in CA.ERAS}
        ok1, ok2, ok3 = CA.d1({e: st[e] for e in CA.ERAS}), CA.d2(pooled, pl), CA.d3({s: st[s] for s in ("W", "Jx")})
        ok4a = CA.d4a(ACC, BASE)
        q95, ok4b = None, False
        if v != "C" and ok1 and ok2 and ok3:
            q95 = acct_placebo(CA.ERAS, ACC)
            ok4b = CA.calmar_sum(ACC, BASE) > q95
        L1[v] = {"stats": st, "pooled": pooled, "placebo": pl, "acct": ACC, "acct_sum": CA.calmar_sum(ACC, BASE), "acct_q95": q95,
                 "D": [ok1, ok2, ok3, ok4a, ok4b], "rules": {e: rule_text(v if v != "C" else "CS", R[e]) for e in CA.ERAS},
                 "pass": bool(ok1 and ok2 and ok3 and ok4a and ok4b)}
        lab = "现在的 C（对照）" if v == "C" else f"{v} {VARIANTS[v]}"
        say(f"### {lab}")
        for e in CA.ERAS:
            say(f"- 检验 {e}（用 {' + '.join(x for x in CA.ERAS if x != e)} 学）：{L1[v]['rules'][e]}")
        say("| 样本 | 胜率差 / 每笔差（保留 / 信号） |")
        say("|---|---|")
        for s in CS.SAMPLES:
            say(f"| {s} | {S2.dcell(st[s])} |")
        say(f"- 三年代合并 {S2.dcell(pooled)}（随机 95 分位 每笔 {fmt(pl['dmean_q95'])} pp）；账户 " +
            "、".join(f"{e} {S2.acct_cell(ACC[e])}" for e in CA.ERAS) + f"；合计 {L1[v]['acct_sum']:+.3f}")
        if v != "C":
            say(f"- 判定：D1 {yn(ok1)}；D2 {yn(ok2)}；D3 {yn(ok3)}；D4a {yn(ok4a)}；D4b "
                f"{'没跑（D1〜D3 没全过）' if q95 is None else yn(ok4b) + f'（95 分位 {q95:+.3f}）'} → 检验甲 **{'过' if L1[v]['pass'] else '不过'}**")
    OUT["lens1"] = L1

    # ── 检验乙：逐年前推 ──
    say("\n## 三、检验乙：逐年前推（每年只用 1 月 1 日 − 120 天之前的信号学；对照 = 只有 W2）")
    T = pd.concat([D[e] for e in CA.ERAS], ignore_index=True).sort_values("date", kind="mergesort").reset_index(drop=True)
    yrsT = pd.to_datetime(T["date"]).dt.year.to_numpy()
    L2 = {}
    for v in ("C", "CB", "CS"):
        RY, ON = {}, {}
        for y in YEARS:
            tr = T[pd.to_datetime(T["date"]) <= C2.train_cut(y)]
            RY[y] = CA.fit_c(C2.halves(tr)) if v == "C" else fit(v, tr)
            ON[y] = C2.active(RY[y]) if v == "C" else active(v, RY[y])

        def fwd_keep(X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
            keep, on = np.ones(len(X), bool), np.zeros(len(X), bool)
            if not len(X):
                return keep, on
            yr = pd.to_datetime(X["date"]).dt.year.to_numpy()
            for y in np.unique(yr):
                y = int(y)
                if y not in RY or not ON[y]:
                    continue
                m = yr == y
                keep[m] = CA.apply_c(RY[y], X[m]) if v == "C" else keep_of(v, RY[y], X[m])
                on[m] = True
            return keep, on
        k, on = fwd_keep(T)
        per_year, parts = {}, []
        for y in YEARS:
            m = (yrsT == y) & on
            if not m.any():
                continue
            dd = CA.delta(T.loc[m, "net"], k[m])
            per_year[y] = {"rule": rule_text(v if v != "C" else "CS", RY[y]), "n": dd["n"], "kept": dd["kept"], "dwin": dd["dwin"], "dmean": dd["dmean"]}
            parts.append((T.loc[m, "net"].to_numpy(float), T.loc[m, "ticker"].to_numpy(), T.loc[m, "week"].to_numpy(), dd["frac"]))
        pooled = CA.delta(T.loc[on, "net"], k[on])
        pl = CA.pooled_placebo(parts) if parts else {"dmean_q95": np.nan, "dwin_q95": np.nan}
        dts = pd.to_datetime(T.loc[on, "date"])
        med = dts.sort_values().iloc[(len(dts) - 1) // 2] if len(dts) else None
        first = on & (pd.to_datetime(T["date"]) <= med).to_numpy() if med is not None else on
        second = on & ~first
        h1, h2 = CA.delta(T.loc[first, "net"], k[first]), CA.delta(T.loc[second, "net"], k[second])
        oth = {}
        for s in ("W", "Jx"):
            ks, os_ = fwd_keep(D[s])
            oth[s] = CA.delta(D[s].loc[os_, "net"], ks[os_])
        ACC = {}
        for e in ("E", "J"):
            kA, _ = fwd_keep(A[e])
            ACC[e] = acct(e, kA)
        ok1, ok2, ok3 = C2.f1(pooled, pl["dmean_q95"]), C2.f2(h1, h2), C2.f3(oth)
        ok4a = C2.acct_ok(ACC, BASE, ("E", "J"), C2.F4_TOL, C2.F4_DD, C2.F4_SUM)
        q95, ok4b = None, False
        if v != "C" and ok1 and ok2 and ok3:
            q95 = acct_placebo(("E", "J"), ACC)
            ok4b = C2.acct_sum(ACC, BASE, ("E", "J")) > q95
        L2[v] = {"per_year": per_year, "pooled": pooled, "placebo": pl, "halves": [h1, h2], "median": str(med.date()) if med is not None else None,
                 "other": oth, "acct": ACC, "acct_sum": C2.acct_sum(ACC, BASE, ("E", "J")), "acct_q95": q95, "F": [ok1, ok2, ok3, ok4a, ok4b],
                 "pass": bool(ok1 and ok2 and ok3 and ok4a and ok4b)}
        lab = "现在的 C 的做法（对照 = 第二轮 N3）" if v == "C" else f"{v} {VARIANTS[v]}"
        say(f"### {lab}")
        say("| 年 | 规则 | 保留 / 信号 | 胜率差 | 每笔差 |")
        say("|---|---|---|---|---|")
        for y, r in per_year.items():
            say(f"| {y} | {r['rule']} | {r['kept']} / {r['n']} | {fmt(r['dwin'], '{:+.1f}')} | {fmt(r['dmean'])} |")
        say(f"- 有规则的年份合并 {S2.dcell(pooled)}（随机 95 分位 每笔 {fmt(pl['dmean_q95'])} pp）；前一半 {S2.dcell(h1)}、后一半 {S2.dcell(h2)}"
            f"（中位日 {med.date() if med is not None else '—'}）；W {S2.dcell(oth['W'])}、Jx {S2.dcell(oth['Jx'])}")
        say(f"- 账户 E {S2.acct_cell(BASE['E'])} → {S2.acct_cell(ACC['E'])}；J {S2.acct_cell(BASE['J'])} → {S2.acct_cell(ACC['J'])}；合计 {L2[v]['acct_sum']:+.3f}")
        if v != "C":
            say(f"- 判定：F1 {yn(ok1)}；F2 {yn(ok2)}；F3 {yn(ok3)}；F4a {yn(ok4a)}；F4b "
                f"{'没跑（F1〜F3 没全过）' if q95 is None else yn(ok4b) + f'（95 分位 {q95:+.3f}）'} → 检验乙 **{'过' if L2[v]['pass'] else '不过'}**")
    OUT["lens2"] = L2

    say("\n## 四、判定（事先写定：两种检验都过 = 通过）")
    for v in ("CB", "CS"):
        vd = C3.verdict(L1[v]["pass"], L2[v]["pass"])
        OUT["verdict"][v] = vd
        say(f"- {v} {VARIANTS[v]}：检验甲 {'过' if L1[v]['pass'] else '不过'}、检验乙 {'过' if L2[v]['pass'] else '不过'} → **{vd}**")
    passed = [v for v in ("CB", "CS") if OUT["verdict"][v] == "通过"]
    if passed:
        best = max(passed, key=lambda v: L1[v]["acct_sum"] + L2[v]["acct_sum"])
        say(f"- 提议：用 {best} 在 Z + E + J 全部学出的规则代替现在冻结的 C（要你在对话里确认）。")
    else:
        say("- 没有通过的 → C 照旧（不改模拟盘 / 执行器）。")

    say("\n## 五、只描述：稳定性表（平静的牛市那一格，各特征按多数方向入选的占比，前 8 个）")
    TT = pd.concat([D[e] for e in CA.ERAS], ignore_index=True)
    prof = {"Z + E + J 全部": C3.stability(TT)}
    for e in CA.ERAS:
        prof[f"检验 {e} 那一折"] = C3.stability(pd.concat([D[x] for x in CA.ERAS if x != e], ignore_index=True))
    for y in (2016, 2021, 2026):
        prof[f"逐年前推 {y}"] = C3.stability(T[pd.to_datetime(T["date"]) <= C2.train_cut(y)])
    for k_, pr in prof.items():
        say(f"- {k_}：{C3.profile_text(pr)}")
    full_cs = C3.fit_stable(TT)
    full_cb = C3.fit_bag(TT)
    say(f"- 用 Z + E + J 全部学出的规则：CS {C2.rule_features(full_cs)}；CB {rule_text('CB', full_cb)}")
    OUT["stability"] = {k_: {str(c): v_ for c, v_ in pr.items()} for k_, pr in prof.items()}
    OUT["full_cs"] = full_cs
    say(f"\n用时 {round(time.time() - t0)} s。非投资建议。")
    if SMOKE:
        QUIET = False
        say(f"冒烟检查跑完（{round(time.time() - t0)} s；不写文件）")
        return 0
    _write(code, OUT)
    return 0


def _write(code: str, out: dict | None = None) -> None:
    if SMOKE:
        return
    o = paths.out_dir() / "combo3_study"
    Path(f"{o}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{o}.json").write_text(json.dumps(CS._clean(out or {"code": code}), ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
