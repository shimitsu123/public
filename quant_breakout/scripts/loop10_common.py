"""loop10_common.py — 第十个研究循环（选股成功率：胜率提高、账户不变差；规则 scripts/research_loop10.py）的共用部分。

跑法同第九个循环（scripts/loop9_common.py）：B3 = scripts/loop6_common.load3 + run；候选 = 同一个 B3，只是某些（票, 信号日）不开新仓
（em_tick 0：名额留给下一个候选、钱留在核心）。判定换成 research_loop10.stage1（V1〜V6）。
池子：V4 = W（扩大池 2006〜2016，E 那一折的 C）、Jx（时点 TOPIX 1000 里非日経225，2017〜，J 那一折的 C）；
      V6 = Zx（扩大池里非日経225，Z 年代 2001-01〜2006-09，Z 那一折的 C；没看过的数据，只用于事后设计的做法）。
Zx 的做法（登记时写定）：名单 = qbreak.wide_universe（var/universe_wide.json）去掉今天的日経225；行情 = scripts/leap_confirm.context("Z", names)
（yfinance 27 年、去掉成交量 0 的假行，同 Z）；指标 / W2 = leap_confirm.frames / w2_keep；信号 = combo_all_study.signals（信号日 2001-01-04〜2006-09-30）；
特征 = combo_all_study.add_features（feature_base 同第九个循环的面板）；结果 = combo_all_study.outcomes（每个信号单独买、X6 离场、扣费用）。
建好之后存 var/cache/loop10_zx.pkl（不入库）；建的时候只打印个数，不打印任何胜率 / 收益。
第二关：每个年代随机挡（stock）或日序列平移（date）→ 三个年代合起来的胜率差（pp）。非投资建议。
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop9_common as C9                                                    # noqa: E402
import research_loop10 as R10                                                # noqa: E402

ERAS = C9.ERAS
KEYS = C9.KEYS
OTHER = (("W", "E", "W"), ("Jx", "J", "J2"), ("Zx", "Z", "Zx"))              # (池子, 用哪一折的 C, 行情在 W["SM"] 的哪个键)
ZX_CACHE = "loop10_zx.pkl"

acct, tick_of, signals, run_block, blocked_frac = C9.acct, C9.tick_of, C9.signals, C9.run_block, C9.blocked_frac
days_of, gate_from_days, _f = C9.days_of, C9.gate_from_days, C9._f
L6 = C9.L6


# ───────────────────────── Zx（没看过的数据） ─────────────────────────
def zx_names() -> list[str]:
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    n225 = set(universe("JP", "broad"))
    return [t for t in WU.tickers(WU.load()) if t not in n225]


def build_zx(log=print) -> dict:
    """Zx 的行情 / 全部 W2 信号（A）/ 有结果的（D）。有缓存就直接读。只打印个数。"""
    from qbreak import paths
    fp = paths.sub("cache") / ZX_CACHE
    if fp.exists():
        with open(fp, "rb") as f:
            return pickle.load(f)
    import combo_all_study as CS
    import leap_confirm as LF
    import sell_confirm as SCF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p0 = SF.no_w2_params(load_params(market="JP"))
    names = zx_names()
    ctx = LF.context("Z", names=names)
    fa = LF.frames(ctx, p0)
    keep = LF.w2_keep(ctx, fa)
    a, b = CS.WIN["Z"]
    S = CS.signals(fa, keep, {}, a, b)
    log(f"Zx：名单 {len(names)} 只、有行情 {len(fa)} 只、W2 信号 {len(S)} 个（{time.time() - t0:.0f}s）")
    B = CS.feature_base(p0, None)
    S = CS.add_features(S, fa, B)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    D = CS.outcomes(S, fa, p0, bt, rt)
    out = {"fa": fa, "A": S, "D": D, "names": names,
           "counts": {"names": len(names), "with_data": len(fa), "signals": int(len(S)), "with_outcome": int(len(D))}}
    with open(fp, "wb") as f:
        pickle.dump(out, f)
    log(f"Zx：有结果的信号 {len(D)} 个（{time.time() - t0:.0f}s；存 var/cache/{ZX_CACHE}）")
    return out


def load(with_zx: bool = True) -> dict:
    """第九个循环的全部输入（loop9_common.load）+ Zx（W["SM"]["Zx"]、W["D"]["Zx"]、W["A"]["Zx"]）。"""
    W = C9.load()
    if with_zx:
        Z = build_zx()
        W["SM"]["Zx"] = {"fa": Z["fa"]}
        W["D"]["Zx"] = Z["D"]
        W["A"]["Zx"] = Z["A"]
        W["zx_counts"] = Z["counts"]
    return W


def kept_pool(W: dict, s: str, fold: str) -> pd.DataFrame:
    """池子 s 里 B3 会买的信号（W2 + 那一折的 C 保留；有结果的）。"""
    import combo_all_common as CA
    D = W["D"][s]
    return D[CA.apply_c(W["c_fold"][fold], D)].reset_index(drop=True)


def pool_counts(W: dict) -> dict:
    """只数个数（登记时核对用）：每个池子 B3 会买的信号有多少。"""
    return {s: int(len(kept_pool(W, s, fold))) for s, fold, _ in OTHER if s in W["D"]}


def other_stocks(W: dict, gate_fn) -> dict:
    """V4 / V6：gate_fn(池子名, X, fa) → 要挡的（bool，与 X 同序）→ 保留的 vs 全部（假想单笔）。"""
    import combo_all_common as CA
    out = {}
    for s, fold, sm in OTHER:
        if s not in W["D"]:
            continue
        X = kept_pool(W, s, fold)
        g = np.asarray(gate_fn(s, X, W["SM"][sm]["fa"]), bool)
        net = X["net"].to_numpy(float)
        dl = CA.delta(net, ~g)
        gone = net[g]
        out[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                  "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


def stage_one(W: dict, gates: dict, other_fn: dict, posthoc: dict, log=print) -> dict:
    """gates = {做法: {年代: bool 数组（与 signals 同序）}}；other_fn = {做法: gate_fn}；posthoc = {做法: True / False}。"""
    t0 = time.time()
    base, cand, frac, blocked = {}, {k: {} for k in gates}, {k: {} for k in gates}, {k: {} for k in gates}
    for e in ERAS:
        base[e] = acct(L6.run(W, e))
        for k, g in gates.items():
            cand[k][e] = acct(run_block(W, e, g[e]))
            frac[k][e] = blocked_frac(g[e])
            blocked[k][e] = int(np.asarray(g[e], bool).sum())
        log(f"{e} 完成（{time.time() - t0:.0f}s）")
    other = {k: other_stocks(W, fn) for k, fn in other_fn.items()}
    s1 = {k: R10.stage1(cand[k], base, other.get(k), posthoc=bool(posthoc[k])) for k in gates}
    return {"base": base, "cand": cand, "stage1": s1, "other": other, "frac": frac, "blocked": blocked, "seconds": round(time.time() - t0)}


# ───────────────────────── 第二关（胜率差 vs 400 次随机） ─────────────────────────
def pooled_dwin(cand: dict, base: dict) -> float | None:
    c, b = R10.pooled_trades(cand), R10.pooled_trades(base)
    return None if c["win"] is None or b["win"] is None else float(c["win"] - b["win"])


def placebo_win(W: dict, frac: dict, base: dict, n: int = R10.PLACEBO_N, log=print) -> list:
    """kind = stock：种子 s，每个年代按 frac[年代] 逐个信号随机挡 → 三个年代合起来的胜率差。"""
    out, t0 = [], time.time()
    sizes = {e: len(signals(W, e)) for e in ERAS}
    for s in range(n):
        cand = {e: acct(run_block(W, e, R10.random_signal_block(sizes[e], frac[e], s))) for e in ERAS}
        out.append(pooled_dwin(cand, base))
        if (s + 1) % 50 == 0:
            log(f"随机挡 {s + 1} / {n}（{time.time() - t0:.0f}s）")
    return out


def placebo_win_date(W: dict, on_by_era: dict, base: dict, n: int = R10.PLACEBO_N, log=print) -> list:
    """kind = date：每个年代把日序列循环平移 k（R10.shift_ks）→ 三个年代合起来的胜率差。"""
    out, t0 = [], time.time()
    ks = {e: R10.shift_ks(len(days_of(W, e)), range(n)) for e in ERAS}
    S = {e: signals(W, e) for e in ERAS}
    for s in range(n):
        cand = {e: acct(run_block(W, e, gate_from_days(S[e], days_of(W, e), R10.shift_days(on_by_era[e], ks[e][s])))) for e in ERAS}
        out.append(pooled_dwin(cand, base))
        if (s + 1) % 50 == 0:
            log(f"日序列平移 {s + 1} / {n}（{time.time() - t0:.0f}s）")
    return out


# ───────────────────────── 输出 ─────────────────────────
def render(res: dict, title: str) -> str:
    """一轮第一关的结果表（V1〜V6）。"""
    L = [title, "",
         f"代码 {res['code']}{'（有未提交的改动！）' if res['dirty'] else ''}；B3 与登记值的差：" + "、".join(f"{e} {_f(v, '{:+.4f}')}" for e, v in res["drift"].items()), "",
         "| 做法 | 年代 | Calmar（B3 → 候选） | 差 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 | 挡掉的信号 / 成交 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for k in res["ids"]:
        for e in ERAS:
            b, c = res["base"][e], res["cand"][k][e]
            sc = res["scale"][e][k]
            L.append(f"| {k} | {e} | {_f(b['calmar'])} → {_f(c['calmar'])} | {_f(None if c['calmar'] is None else c['calmar'] - b['calmar'], '{:+.3f}')} | "
                     f"{_f(b['dd'], '{:.2f}')} → {_f(c['dd'], '{:.2f}')}% | {_f(c['h1'])} / {_f(c['h2'])} | {b['n']} → {c['n']} | "
                     f"{_f(b['win'], '{:.1f}')} → {_f(c['win'], '{:.1f}')}% | {_f(b['mean'], '{:+.2f}')} → {_f(c['mean'], '{:+.2f}')}% | "
                     f"{sc['signals_blocked']} / {sc['trades_blocked']} |")
    L += ["", "## 第一关（V1〜V6）", ""]
    for k in res["ids"]:
        s = res["stage1"][k]
        su, a = s["success"], s["account"]
        o = res["other"][k]
        pools = "；".join(f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}（被挡的 {_f(o[x]['gone_win'], '{:.1f}')}% / {_f(o[x]['gone_mean'], '{:+.2f}')}%；"
                         f"保留的胜率差 {_f(o[x]['dwin'], '{:+.2f}')} pp、每笔差 {_f(o[x]['dmean'], '{:+.3f}')} pp）" for x in ("W", "Jx", "Zx") if x in o)
        L.append(f"- **{k}**{'（事后，V6 适用）' if s['posthoc'] else ''}：" + "、".join(f"{x} {'✓' if s[x] else '✗'}" for x in R10.CHECKS)
                 + f"；选股成功率 {_f(su['base']['win'], '{:.2f}')}% → {_f(su['cand']['win'], '{:.2f}')}%（{_f(su['dwin'], '{:+.2f}')} pp）、"
                 f"每笔 {_f(su['base']['mean'], '{:+.3f}')} → {_f(su['cand']['mean'], '{:+.3f}')}%；每个年代胜率差 "
                 + "、".join(f"{e} {_f(su['era_dwin'][e], '{:+.1f}')}" for e in ERAS)
                 + f" pp；账户 Calmar 差 " + "、".join(f"{e} {_f(a['d'][e], '{:+.3f}')}" for e in ERAS)
                 + f"（合计 {_f(a['sum'], '{:+.3f}')}；两半 {_f(a['h1'], '{:+.3f}')} / {_f(a['h2'], '{:+.3f}')}）；{pools}"
                 + f" → **{'第一关全过（要另行登记第二关）' if s['ok'] else R10.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。判定按 scripts/research_loop10.py。非投资建议。"]
    return "\n".join(L) + "\n"


git_head = C9.git_head
