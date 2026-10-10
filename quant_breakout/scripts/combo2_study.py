"""combo2_study.py — 选股第二轮：在关联搭配 C 的基础上继续提高选股（2026-10-01 登记；提交后不改规则、只运行一次）。

用户（2026-10-01）：「加进模拟盘并记录 / 然后结合所有研究继续提高现在的选股能力」。C（scripts/combo_all_study.py 登记 7f2ca59 五条全过，
2026-10-01 收盘的决策起在用）之后，留下的三个最直接的问题：
  ① C 的证据主要来自 2017〜2026，而且「留一年代」检验 2001〜2016 时学习用到了 2017〜2026（未来的数据）——
     只用过去的数据、每年重学一次，C 的做法还能不能前推成立？（N3）
  ② 个股层信号很少（今天的日経225 + W2 每年约 17 个，2026-02 以后一个也没有），资金多半闲着；W2 挡掉约一半突破，而时点名单上的核对
     （scripts/pit_recheck2.py，2026-09-30）显示 W2 在 2017〜2026 只等于随机 —— 让 C 把 W2 挡掉的好信号补回来（N1），
     或者干脆不要 W2、让 C 在全部突破上学（N2），能不能多做到好交易？
数据与做法和 combo_all_study 完全相同（同一套信号、53 个特征、X6 单笔结果、账户框架 S0C2 + W2、X6、核心 1655 + 牛熊；
样本 Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09 = 今天的日経225，W = 扩大池 714 只 2006〜2016、
Jx = 时点 TOPIX 1000 里不是日経225 的票 2017〜，只检验不学）。新算的只有「W2 挡掉的突破」的特征与结果（同一组函数）。
C 的做法（选特征：两个学习段秩相关同号且 |ρ| ≥ 0.05；切点 = 学习样本三等分；门槛 = 学习样本分数的 1/3 分位；
市场格 = 日経 200 日线上下 × VIX ≥ 20；每段每格 ≥ 60 笔才有规则）一律用 scripts/combo_all_common.py 的同一组函数，参数不动。

〇 复现（先决条件）：重建 C 的留一年代（用 W2 信号学、考第三个年代）→ 保留比例、胜率差、每笔差要与 var/out/combo_all_study.json 完全一致，
  账户 Z / E / J Calmar 1.849 / 0.312 / 0.440 也要一致；不一致 → 停下、只报告原因（不判定）。

一、N3「C 逐年前推」（只用过去学）
  - 样本 = Z + E + J 的 W2 信号接成一条 2001〜2026 的时间线（有结果的）。
  - 每一年 Y（2002〜2026）：学习样本 = 信号日 ≤ Y 年 1 月 1 日 − 120 天的信号（X6 最长持有 60 个交易日 → 结果当时都已知道）；
    按信号日中位数切成前后两半 = C 的「两个学习年代」；用 C 同一做法学四格规则 → 只用在 Y 年的信号上。哪一格都学不出规则的年份 = 不动。
  - 检验：有规则的年份里 保留 vs 全部（胜率差、每笔差）；随机对照 = 每一年按「股票 × 周」随机保留同样比例，合并 200 次的 95 分位；
    前后两半（有规则的信号按日期中位数切开）；W / Jx 用同一年学出的规则（只用日経225 学）；账户 E / J（Z 几乎没有规则）。
  - 判定（全部成立才「通过」）：
    F1 合并：胜率差 ≥ +2.0 pp、每笔差 ≥ +0.20 pp、每笔差 > 随机 95 分位；
    F2 前后两半：每笔差都 ≥ 0；
    F3 别的股票：W、Jx 的胜率差、每笔差都 ≥ 0；
    F4 账户：E、J 的 Calmar 各 ≥ 现行（W2，不加 C）− 0.02、回撤不深 2 pp 以上、两段合计 ≥ +0.02，且合计 > 随机跳过同样比例（30 次）的 95 分位
       （随机对照只在 F1〜F3 都过时才跑）。
  - 通过 → C 的做法前推也成立 → 继续用 C，并提议「每年 1 月用到上一年底的全部数据按同一做法重学一次」（要用户在对话里确认、记 sim_changes）；
    不通过 → C 照旧（用户已决定），在日报 / 页面注明「只用过去学时前推不成立」，要不要关掉由用户决定；不自动改模拟盘。

二、N1「W2 挡掉的、C 分高的也买」
  - 每个年代用 C 的那一折规则（另外两个年代的 W2 信号学的，= combo_all_study 的 C），给这个年代 W2 挡掉的突破打分；
    分数 ≥ +2（有利的票比不利的多 2 票以上）且那一格有规则 → 也买（补回）。W 用 E 那一折、Jx 用 J 那一折。
  - 买的 = 现行（W2 + C）∪ 补回。
  - 判定：G1 每个年代补回的那几笔每笔 > 0（没有补回的年代 = 不变，算过）；
          G2 合并：补回的每笔 ≥ 现行买的每笔 − 0.30 pp，且 > 随机补回同样多（同一年代、有规则的格子里按「股票 × 周」抽签，200 次）的 95 分位；
          G3 W、Jx：补回的每笔 ≥ 0（没有补回 = 过）；
          G4 账户：Z / E / J 各 ≥ 现行（W2 + C）− 0.02、回撤不深 2 pp 以上，三个年代合计 ≥ +0.03，
             且合计 > 随机补回同样多（30 次）的 95 分位（G1〜G3 都过才跑）。
三、N2「不要 W2，C 在全部突破上学」
  - 每个年代：用另外两个年代的全部突破（W2 保留 + 挡掉）按 C 同一做法学 → 用在这个年代的全部突破上；不再看 W2。W / Jx 同样对应。
  - 判定：G1 每个年代 买的那一组 每笔 ≥ 现行（W2 + C）− 0.30 pp、胜率 ≥ 现行 − 3.0 pp；
          G2 合并：C2 保留 − 全部突破 的每笔差 ≥ +0.20 pp 且 > 随机保留同样比例（200 次）的 95 分位（C2 本身要有用）；
          G3 W、Jx：买的那一组每笔 ≥ 现行（W2 + C）− 0.30 pp；
          G4 账户：同 N1（对照 = 现行 W2 + C；随机对照 = 不要 W2、全部突破随机保留同样比例，30 次）。
  - N1 / N2 全过 = 通过 → 提议改模拟盘（N1：加「补回」；N2：去掉 W2、换成全部突破上学的 C）；两个都过 → 提议账户合计大的那个；要用户确认。
    只过信号层（G1〜G3）= 方向一致（只记录）；其余 = 不通过。

四、只描述（不参与判定）：N3 每一年学到的规则与保留 / 跳过的每笔；W2 挡掉的突破按 C 分数（≤ −2 / −1〜+1 / ≥ +2）的胜率与每笔；
  N1 / N2 在死叉离场下的同样比较。
事前预期（照实写）：N3 通过约 30%（C 的效果集中在 2017〜2026，只用过去学时 2013〜2016 的规则多半学自 2001〜2012、那时 C 的特征并不明显）；
  N1 约 20%（W2 挡掉的信号整体更差，分数高的那一小撮未必够好）；N2 约 10%（2001〜2016 W2 的帮助大，去掉多半变差）。
多重比较：三个候选、各自几条门槛；同时都成立的偶然机会很小，但「方向一致」不作为改规则的依据。
运行：python scripts/combo2_study.py（约 40〜60 分钟）；QBREAK_SMOKE=1 只用每批十几只票静默跑一遍流程（不打印任何差、不写文件）。
输出 var/out/combo2_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import os
import pickle
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
import combo_all_common as CA                                                # noqa: E402
import combo_all_study as CS                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

YEARS = list(range(2002, 2027))
CACHE_NW = "combo2_nonw2.pkl"
SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
LINES: list[str] = []
QUIET = False


def say(s: str = "") -> None:
    if QUIET:
        return
    print(s, flush=True)
    LINES.append(s)


fmt = CS.fmt


# ───────────────────────── 样本 ─────────────────────────
def nonw2_signals(SM: dict, B: dict, p0, bt, rt: float, n225_today: set) -> tuple[dict, dict]:
    """W2 挡掉的突破（entry ∧ ¬W2）：特征与结果用 combo_all_study 的同一组函数。→ (有结果 Dn, 全部 An)。"""
    Dn, An = {}, {}
    for s in CS.SAMPLES:
        a, b = CS.WIN[s]
        src = SM["J2"] if s == "Jx" else SM[s]
        inv = {t: ~np.asarray(k, bool) for t, k in src["keep"].items()}
        S = CS.signals(src["fa"], inv, src["mem"], a, b, exclude=n225_today if s == "Jx" else None)
        S = CS.add_features(S, src["fa"], B)
        An[s] = S
        Dn[s] = CS.outcomes(S, src["fa"], p0, bt, rt)
    return Dn, An


def fold_rules(trains: list[pd.DataFrame]) -> dict:
    return CA.fit_c(trains)


def masks(fa: dict, base: dict | None, off, on) -> dict[str, np.ndarray]:
    """每只票每天能不能买：从 base（None = 全部）开始，off 里的 (票, 日) 设 False，on 里的设 True。"""
    out = {t: (np.asarray(base[t], bool).copy() if base is not None else np.ones(len(df), bool)) for t, df in fa.items()}
    for t, d in off:
        if t in out:
            out[t][fa[t].index.get_loc(pd.Timestamp(d))] = False
    for t, d in on:
        if t in out:
            out[t][fa[t].index.get_loc(pd.Timestamp(d))] = True
    return out


def pairs(X: pd.DataFrame, m) -> list:
    m = np.asarray(m, bool)
    return list(zip(X["ticker"].to_numpy()[m], pd.to_datetime(X["date"]).to_numpy()[m]))


def acct_row(r: dict, e: str) -> dict:
    return {k: r[e][k] for k in ("cagr", "dd", "calmar", "n", "mean", "win")}


def acct_cell(a: dict) -> str:
    return f"{fmt(a['calmar'], '{:.3f}')}（{fmt(a['dd'])}%；{a['n']} 笔 · {fmt(a['win'], '{:.1f}')}%）"


def dcell(x: dict) -> str:
    return (f"{fmt(x['dwin'], '{:+.1f}')} pp / {fmt(x['dmean'])} pp（{x['kept']} / {x['n']}）" if x.get("n") else "—")


def scell(x: dict) -> str:
    return f"{x['n']} 笔 · {fmt(x['win'], '{:.1f}')}% · {fmt(x['mean'])}%" if x.get("n") else "0 笔"


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
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/combo2_study.py", "scripts/combo2_common.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 选股第二轮：在关联搭配 C 的基础上（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}"
        f"{'；冒烟检查' if SMOKE else ''}）")
    say("规则见 scripts/combo2_study.py 开头（先提交后运行）；统计与判定 scripts/combo2_common.py；C 的做法 scripts/combo_all_common.py。")
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
        Dn, An = nonw2_signals(SM, B, p0, bt, rt, n225_today)
    else:
        D, A, _ = PH.build_panel()                                          # 登记运行同一套代码（有缓存就用缓存）
        fp = paths.sub("cache") / CACHE_NW
        if fp.exists():
            with open(fp, "rb") as f:
                Dn, An = pickle.load(f)
        else:
            B = CS.feature_base(p0, None)
            Dn, An = nonw2_signals(SM, B, p0, bt, rt, n225_today)
            with open(fp, "wb") as f:
                pickle.dump((Dn, An), f)
    for s in CS.SAMPLES:
        say(f"- {s}：W2 保留 {len(A[s])} 个（有结果 {len(D[s])}）；W2 挡掉 {len(An[s])} 个（有结果 {len(Dn[s])}）")
    if SMOKE:
        QUIET = True

    # 现行（W2 + C，留一年代）—— 复现
    R1 = {e: fold_rules([D[x] for x in CA.ERAS if x != e]) for e in CA.ERAS}
    RULE_OF = {**{e: R1[e] for e in CA.ERAS}, "W": R1["E"], "Jx": R1["J"]}
    keepC = {s: CA.apply_c(RULE_OF[s], D[s]) for s in CS.SAMPLES}
    keepC_all = {s: CA.apply_c(RULE_OF[s], A[s]) for s in CS.SAMPLES}
    reg = json.loads((paths.out_dir() / "combo_all_study.json").read_text(encoding="utf-8")) if not SMOKE else None
    rep_ok = True
    for s in CS.SAMPLES:
        dd = CA.delta(D[s]["net"], keepC[s])
        if reg is not None:
            r0 = reg["stats"]["C"]["samples"][s]
            same = (dd["kept"] == r0["kept"] and dd["n"] == r0["n"] and abs(dd["dwin"] - r0["dwin"]) < 1e-3
                    and abs(dd["dmean"] - r0["dmean"]) < 1e-3)                # JSON 里取 4 位小数
            rep_ok &= same
            say(f"- 复现 C（{s}）：保留 {dd['kept']} / {dd['n']}、胜率差 {fmt(dd['dwin'], '{:+.2f}')} pp、每笔差 {fmt(dd['dmean'])} pp → "
                f"{'与登记运行一致' if same else '★ 不一致（登记 ' + str(r0['kept']) + ' / ' + str(r0['n']) + '）'}")
    if not rep_ok:
        say("\n★ 复现不一致 → 按登记停下，不判定。")
        _write(code)
        return 1

    say("\n## 一、账户的现行（研究框架：S0C2 + W2、X6、核心 1655 + 牛熊）")
    CTX, BASE_W2, BASE_C = {}, {}, {}
    for e in CA.ERAS:
        src = SM[e]
        ctx, fa = src["ctx"], src["fa"]
        fr_w2 = LF.with_mask(fa, src["keep"])
        run_fn = LF.runner(ctx, fr_w2)
        BASE_W2[e] = acct_row(LF.run(ctx, run_fn, fr_w2, px), e)
        mkC = masks(fa, src["keep"], pairs(A[e], ~keepC_all[e]), [])
        BASE_C[e] = acct_row(LF.run(ctx, run_fn, LF.with_mask(fa, mkC), px), e)
        CTX[e] = (ctx, fa, run_fn, fr_w2, mkC)
        say(f"- {e}：只有 W2 {acct_cell(BASE_W2[e])}；W2 + C（现行）{acct_cell(BASE_C[e])}")
    if reg is not None:
        acc0 = reg["acct"]["C"]
        same = all(abs(BASE_C[e]["calmar"] - acc0[e]["calmar"]) < 1.5e-3 for e in CA.ERAS)   # JSON 里取 3 位小数
        say(f"- 复现账户（W2 + C）：{'与登记运行一致' if same else '★ 不一致'}")
        if not same:
            say("\n★ 复现不一致 → 按登记停下，不判定。")
            _write(code)
            return 1

    OUT: dict = {"code": code, "n": {s: {"w2": len(D[s]), "nonw2": len(Dn[s])} for s in CS.SAMPLES},
                 "base_w2": BASE_W2, "base_c": BASE_C}

    # ── N3 逐年前推 ──
    say("\n## 二、N3「C 逐年前推」（每年只用 1 月 1 日 − 120 天之前的信号学）")
    T = pd.concat([D[e] for e in CA.ERAS], ignore_index=True).sort_values("date", kind="mergesort").reset_index(drop=True)
    RY = C2.forward_rules(T, YEARS)
    k3, on3 = C2.apply_forward(RY, T)
    yrs = pd.to_datetime(T["date"]).dt.year.to_numpy()
    say("| 年 | 学到的规则 | 信号 | 保留 | 胜率差 | 每笔差 | 跳过的每笔 / 保留的每笔 |")
    say("|---|---|---|---|---|---|---|")
    per_year, parts = {}, []
    for y in YEARS:
        m = yrs == y
        if not m.any():
            continue
        dd = CA.delta(T.loc[m, "net"], k3[m])
        x = T.loc[m, "net"].to_numpy(float)
        sk = x[~k3[m]]
        per_year[y] = {"rule": C2.rule_features(RY[y]), "n": int(m.sum()), "kept": dd["kept"], "dwin": dd["dwin"], "dmean": dd["dmean"],
                       "skip_mean": float(sk.mean()) if len(sk) else None, "keep_mean": dd["mean"]}
        if C2.active(RY[y]):
            parts.append((x, T.loc[m, "ticker"].to_numpy(), T.loc[m, "week"].to_numpy(), dd["frac"]))
        say(f"| {y} | {per_year[y]['rule']} | {dd['n']} | {dd['kept']} | {fmt(dd['dwin'], '{:+.1f}')} | {fmt(dd['dmean'])} | "
            f"{fmt(per_year[y]['skip_mean'])} / {fmt(dd['mean'])} |")
    pooled3 = CA.delta(T.loc[on3, "net"], k3[on3])
    pl3 = CA.pooled_placebo(parts)
    dts = pd.to_datetime(T.loc[on3, "date"])
    med = dts.sort_values().iloc[(len(dts) - 1) // 2] if len(dts) else None
    first = on3 & (pd.to_datetime(T["date"]) <= med).to_numpy() if med is not None else on3
    second = on3 & ~first
    h1, h2 = CA.delta(T.loc[first, "net"], k3[first]), CA.delta(T.loc[second, "net"], k3[second])
    oth3 = {}
    for s in ("W", "Jx"):
        ks, os_ = C2.apply_forward(RY, D[s])
        oth3[s] = CA.delta(D[s].loc[os_, "net"], ks[os_])
    say(f"\n- 有规则的年份合并：{dcell(pooled3)}（随机 95 分位 每笔 {fmt(pl3['dmean_q95'])} pp）；前一半 {dcell(h1)}、后一半 {dcell(h2)}"
        f"（中位日 {med.date() if med is not None else '—'}）")
    say(f"- 别的股票（用同一年只学日経225 的规则）：W {dcell(oth3['W'])}；Jx {dcell(oth3['Jx'])}")
    ok31, ok32, ok33 = C2.f1(pooled3, pl3["dmean_q95"]), C2.f2(h1, h2), C2.f3(oth3)
    ACC3 = {}
    for e in ("E", "J"):
        ctx, fa, run_fn, fr_w2, _ = CTX[e]
        kA, _ = C2.apply_forward(RY, A[e])
        mk = masks(fa, SM[e]["keep"], pairs(A[e], ~kA), [])
        ACC3[e] = acct_row(LF.run(ctx, run_fn, LF.with_mask(fa, mk), px), e)
        ACC3[e]["frac"] = float(kA.mean()) if len(kA) else 1.0
        say(f"- 账户 {e}：只有 W2 {acct_cell(BASE_W2[e])} → N3 {acct_cell(ACC3[e])}")
    ok34a = C2.acct_ok(ACC3, BASE_W2, ("E", "J"), C2.F4_TOL, C2.F4_DD, C2.F4_SUM)
    q3 = None
    ok34b = False
    if ok31 and ok32 and ok33:
        seeds = 2 if SMOKE else C2.ACCT_SEEDS
        sums = np.zeros(seeds)
        for e in ("E", "J"):
            ctx, fa, run_fn, fr_w2, _ = CTX[e]
            for k in range(seeds):
                rr = LF.run(ctx, run_fn, WP.week_lottery(fr_w2, ACC3[e]["frac"], k), px)
                sums[k] += (rr[e]["calmar"] or 0.0) - BASE_W2[e]["calmar"]
        q3 = float(np.percentile(sums, 95))
        ok34b = C2.acct_sum(ACC3, BASE_W2, ("E", "J")) > q3
    v3 = C2.verdict([ok31, ok32, ok33], ok34a, ok34b)
    yn = lambda b_: "过" if b_ else "不过"                                      # noqa: E731
    say(f"- 判定：F1 {yn(ok31)}；F2 {yn(ok32)}；F3 {yn(ok33)}；F4 账户 {yn(ok34a)}（合计 {C2.acct_sum(ACC3, BASE_W2, ('E', 'J')):+.3f}）；"
        f"随机对照 {'没跑（F1〜F3 没全过）' if q3 is None else yn(ok34b) + f'（95 分位 {q3:+.3f}）'} → **{v3}**")
    OUT["N3"] = {"per_year": per_year, "pooled": pooled3, "placebo": pl3, "halves": [h1, h2], "median": str(med.date()) if med is not None else None,
                 "other": oth3, "acct": ACC3, "acct_q95": q3, "F": [ok31, ok32, ok33, ok34a, ok34b], "verdict": v3}

    # ── N1 补回 ──
    say("\n## 三、N1「W2 挡掉的、C 分 ≥ +2 的也买」（C 的那一折规则）")
    per1, base1, rparts = {}, {}, []
    for s in CS.SAMPLES:
        rs = C2.rescue(RULE_OF[s], Dn[s])
        per1[s] = C2.stat(Dn[s].loc[rs, "net"])
        base1[s] = C2.stat(D[s].loc[keepC[s], "net"])
        sc, has = C2.c_score(RULE_OF[s], Dn[s])
        if s in CA.ERAS:
            rparts.append((Dn[s].loc[has, "net"].to_numpy(float), Dn[s].loc[has, "ticker"].to_numpy(), Dn[s].loc[has, "week"].to_numpy(),
                           int(rs.sum())))
        say(f"- {s}：现行买的 {scell(base1[s])}；补回 {scell(per1[s])}（W2 挡掉的 {len(Dn[s])} 个里、有规则的格子 {int(has.sum())} 个）")
    pr = C2.stat(np.concatenate([Dn[e].loc[C2.rescue(RULE_OF[e], Dn[e]), "net"].to_numpy(float) for e in CA.ERAS]))
    pb = C2.stat(np.concatenate([D[e].loc[keepC[e], "net"].to_numpy(float) for e in CA.ERAS]))
    q1 = C2.rescue_placebo(rparts)
    ok11, ok12, ok13 = C2.g1_rescue({e: per1[e] for e in CA.ERAS}), C2.g2_rescue(pr, pb, q1), C2.g3_rescue({s: per1[s] for s in ("W", "Jx")})
    say(f"- 合并（Z + E + J）：补回 {scell(pr)}；现行买的 {scell(pb)}；随机补回同样多的每笔 95 分位 {fmt(q1)}%")
    ACC1 = {}
    for e in CA.ERAS:
        ctx, fa, run_fn, fr_w2, mkC = CTX[e]
        rsA = C2.rescue(RULE_OF[e], An[e])
        mk = masks(fa, mkC, [], pairs(An[e], rsA))
        ACC1[e] = acct_row(LF.run(ctx, run_fn, LF.with_mask(fa, mk), px), e)
        ACC1[e]["added"] = int(rsA.sum())
        say(f"- 账户 {e}：现行（W2 + C）{acct_cell(BASE_C[e])} → N1 {acct_cell(ACC1[e])}（补回 {int(rsA.sum())} 个信号）")
    ok14a = C2.acct_ok(ACC1, BASE_C, CA.ERAS, C2.F4_TOL, C2.F4_DD, C2.G_SUM)
    q14, ok14b = None, False
    if ok11 and ok12 and ok13:
        seeds = 2 if SMOKE else C2.ACCT_SEEDS
        sums = np.zeros(seeds)
        rng = np.random.default_rng(C2.SEED)
        for e in CA.ERAS:
            ctx, fa, run_fn, fr_w2, mkC = CTX[e]
            sc, has = C2.c_score(RULE_OF[e], An[e])
            cand = An[e][has]
            for k in range(seeds):
                pick = C2.random_pick(cand["ticker"].to_numpy(), pd.to_datetime(cand["date"]).dt.to_period("W").astype(str).to_numpy(),
                                      ACC1[e]["added"], rng)
                mk = masks(fa, mkC, [], pairs(cand, pick))
                rr = LF.run(ctx, run_fn, LF.with_mask(fa, mk), px)
                sums[k] += (rr[e]["calmar"] or 0.0) - BASE_C[e]["calmar"]
        q14 = float(np.percentile(sums, 95))
        ok14b = C2.acct_sum(ACC1, BASE_C, CA.ERAS) > q14
    v1 = C2.verdict([ok11, ok12, ok13], ok14a, ok14b)
    say(f"- 判定：G1 {yn(ok11)}；G2 {yn(ok12)}；G3 {yn(ok13)}；G4 账户 {yn(ok14a)}（合计 {C2.acct_sum(ACC1, BASE_C, CA.ERAS):+.3f}）；"
        f"随机对照 {'没跑（G1〜G3 没全过）' if q14 is None else yn(ok14b) + f'（95 分位 {q14:+.3f}）'} → **{v1}**")
    OUT["N1"] = {"rescued": per1, "base": base1, "pooled": pr, "pooled_base": pb, "placebo_q95": q1, "acct": ACC1, "acct_q95": q14,
                 "G": [ok11, ok12, ok13, ok14a, ok14b], "verdict": v1}

    # ── N2 不要 W2 ──
    say("\n## 四、N2「不要 W2，C 在全部突破上学」")
    ALLD = {s: pd.concat([D[s], Dn[s]], ignore_index=True) for s in CS.SAMPLES}
    ALLA = {s: pd.concat([A[s], An[s]], ignore_index=True) for s in CS.SAMPLES}
    R2 = {e: fold_rules([ALLD[x] for x in CA.ERAS if x != e]) for e in CA.ERAS}
    RULE2 = {**R2, "W": R2["E"], "Jx": R2["J"]}
    per2, dl2, parts2 = {}, {}, []
    for s in CS.SAMPLES:
        k2 = CA.apply_c(RULE2[s], ALLD[s])
        per2[s] = C2.stat(ALLD[s].loc[k2, "net"])
        dl2[s] = CA.delta(ALLD[s]["net"], k2)
        if s in CA.ERAS:
            parts2.append((ALLD[s]["net"].to_numpy(float), ALLD[s]["ticker"].to_numpy(), ALLD[s]["week"].to_numpy(), dl2[s]["frac"]))
        say(f"- {s}：规则 {C2.rule_features(RULE2[s])}；买的 {scell(per2[s])}（全部突破 {dl2[s]['n']} 个）；现行（W2 + C）{scell(base1[s])}")
    pooled2 = CA.delta(np.concatenate([ALLD[e]["net"].to_numpy(float) for e in CA.ERAS]),
                       np.concatenate([CA.apply_c(RULE2[e], ALLD[e]) for e in CA.ERAS]))
    pl2 = CA.pooled_placebo(parts2)
    ok21 = C2.g1_replace({e: per2[e] for e in CA.ERAS}, {e: base1[e] for e in CA.ERAS})
    ok22 = C2.g2_replace(pooled2, pl2["dmean_q95"])
    ok23 = C2.g3_replace({s: per2[s] for s in ("W", "Jx")}, {s: base1[s] for s in ("W", "Jx")})
    say(f"- 合并：C2 保留 − 全部突破 {dcell(pooled2)}（随机 95 分位 每笔 {fmt(pl2['dmean_q95'])} pp）")
    ACC2 = {}
    for e in CA.ERAS:
        ctx, fa, run_fn, fr_w2, _ = CTX[e]
        k2A = CA.apply_c(RULE2[e], ALLA[e])
        mk = masks(fa, None, pairs(ALLA[e], ~k2A), [])
        ACC2[e] = acct_row(LF.run(ctx, run_fn, LF.with_mask(fa, mk), px), e)
        ACC2[e]["frac"] = float(k2A.mean()) if len(k2A) else 1.0
        say(f"- 账户 {e}：现行（W2 + C）{acct_cell(BASE_C[e])} → N2 {acct_cell(ACC2[e])}")
    ok24a = C2.acct_ok(ACC2, BASE_C, CA.ERAS, C2.F4_TOL, C2.F4_DD, C2.G_SUM)
    q24, ok24b = None, False
    if ok21 and ok22 and ok23:
        seeds = 2 if SMOKE else C2.ACCT_SEEDS
        sums = np.zeros(seeds)
        for e in CA.ERAS:
            ctx, fa, run_fn, fr_w2, _ = CTX[e]
            for k in range(seeds):
                rr = LF.run(ctx, run_fn, WP.week_lottery(fa, ACC2[e]["frac"], k), px)
                sums[k] += (rr[e]["calmar"] or 0.0) - BASE_C[e]["calmar"]
        q24 = float(np.percentile(sums, 95))
        ok24b = C2.acct_sum(ACC2, BASE_C, CA.ERAS) > q24
    v2 = C2.verdict([ok21, ok22, ok23], ok24a, ok24b)
    say(f"- 判定：G1 {yn(ok21)}；G2 {yn(ok22)}；G3 {yn(ok23)}；G4 账户 {yn(ok24a)}（合计 {C2.acct_sum(ACC2, BASE_C, CA.ERAS):+.3f}）；"
        f"随机对照 {'没跑（G1〜G3 没全过）' if q24 is None else yn(ok24b) + f'（95 分位 {q24:+.3f}）'} → **{v2}**")
    OUT["N2"] = {"rules": {s: C2.rule_features(RULE2[s]) for s in CS.SAMPLES}, "bought": per2, "delta": dl2, "pooled": pooled2, "placebo": pl2,
                 "acct": ACC2, "acct_q95": q24, "G": [ok21, ok22, ok23, ok24a, ok24b], "verdict": v2}

    # ── 只描述 ──
    say("\n## 五、只描述：W2 挡掉的突破按 C 分数（那一折规则；只算有规则的格子）")
    desc = {}
    for s in CS.SAMPLES:
        sc, has = C2.c_score(RULE_OF[s], Dn[s])
        x = Dn[s]["net"].to_numpy(float)
        cells = []
        for lo_, hi_, lab in ((-99, -2, "≤ −2"), (-1, 1, "−1〜+1"), (2, 99, "≥ +2")):
            with np.errstate(invalid="ignore"):
                m = has & (sc >= lo_) & (sc <= hi_)
            st = C2.stat(x[m])
            desc.setdefault(s, {})[lab] = st
            cells.append(f"{lab}：{scell(st)}")
        say(f"- {s}：" + "；".join(cells) + f"；不在有规则的格子 {scell(C2.stat(x[~has]))}")
    OUT["desc"] = desc
    say("\n## 六、读法")
    say(f"- N3 {v3}；N1 {v1}；N2 {v2}。通过的才提议改模拟盘（要你确认）；方向一致只记录；不通过的不动。")
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
    o = paths.out_dir() / "combo2_study"
    Path(f"{o}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{o}.json").write_text(json.dumps(CS._clean(out or {"code": code}), ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
