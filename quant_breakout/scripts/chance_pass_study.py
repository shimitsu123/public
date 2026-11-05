"""chance_pass_study.py — 「碰巧通过」的关联：把第十二〜十四个循环的 36 个选股做法放宽到逐笔判定（HANDOFF〔82〕③），
看「碰巧通过」的有没有共同的东西、在后面的年代还在不在（2026-10-24 登记 = 本提交；之后不改规则、只运行一次）。

用户（2026-10-24）：「会增加「碰巧通过」的假结果也要继续进行研究 分析碰巧通过的是否有一定的关联」。
照实写：36 个做法的结果都已经看过（第一关都不过）→ 整个研究按「事后」；这里不找新做法、不改任何做法的定义，只重新拼它们挡了哪几笔。

〇 做法（36 个；B4 基准，各自脚本的 build(W) 原样重建「挡哪几笔」；作废的 ISS 不算；第九〜十一个循环是 B3 基准、K 线研究的 FB* 要另跑 20 分钟 → 不算）：
   路线 A / B（三个年代 + 三个池子都有）18 个：MXR SSM LOW TOM TWD DXD HOL SQW YRE MON IDX VCP DDS CSE CNQ PRF GAP OVN
   路线 J（只有 2016-10 以后的 J 与 Jx）18 个：PBH ROL NXG PRG FCN MRH EQL SAG OMG PEH FGR SSS PED FYB SRN CHR AGR PAY
   接线核对：重建的挡法跑出来的 Calmar 与当时结果文件里的差 > 0.005 → 照实写（行情缓存更新过），仍用重建的。
一 样本与逐笔效果：样本 = 年代 Z（2001〜06）/ E（2006〜16）/ J（2016-10〜）的日経225 信号（TBF 没挡的、有假想单笔结果的）+ 池子 Zx / W / Jx（B4 会买的）。
   效果 d = 留下的每笔平均 − 全部的每笔平均（pp；假想单笔：每个信号单独买、X6 离场、扣费用；> 0 = 挡掉的那些比平均差）。挡 0 笔的样本不算。
二 A 宽松判定（逐笔）：在它有的每个样本里 d > 0（至少 2 个样本）= 「宽松通过」。随机对照：每个做法每个样本在候选里随机挡同样多笔、
   重复 NULL_N 次 → 36 个里「宽松通过」个数的分布 → 实际个数的 p（≥ 实际的比例）。
三 B 关联：B1 挡的是不是同一批票：宽松通过的两两 Jaccard（各样本的被挡集合拼在一起）÷ 同样多笔随机挡的期望（随机对照的前 KEEP_R = 200 次）；
   B2 共同特征：53 个信号特征里，被挡的 − 留下的（÷ 全部的标准差）在每个宽松通过的做法里同号、平均绝对值 ≥ FEAT_SD 的。
   B3 后面的年代还在不在（主检验）：前段选、后段验 —— 路线 A / B：前段 = Z / E / Zx / W（2001〜2016），后段 = J / Jx；
       路线 J：前段 = J / Jx 里信号日 < SPLIT，后段 = ≥ SPLIT。前段每个样本 d > 0 = 「前段通过」。
       T = 前段通过的后段 d 平均 − 其余的后段 d 平均；随机对照 = 全部做法的挡法一起随机（同上），NULL_N 次 → p = 随机的 T ≥ 实际 T 的比例。
       另：前段通过的路线 A / B 做法的挡法合起来（并集）放进 J 年代的 B4 账户 → J Calmar 差，与同样比例随机挡 PLACEBO_N 次比（严格大于 95% 才算）；
       Jx 的 d 也要 > 0。
四 判定（按顺序取第一个成立的）：
   C0「碰巧通过的有共同的东西、后面的年代还在」：T 的 p < P_MAX 且 合起来的 J Calmar 差 > 随机的 95 分位 且 Jx d > 0
       → 只说明值得以它为中心另登记一个新循环（照常两关），不采用、不改模拟盘；
   C1「有一点关联、但合起来用不上」：T 的 p < P_MAX；
   C2「碰巧通过的挡的是同一类票，但这类票在后面的年代不差」：B1 比值 ≥ OVERLAP_RATIO 或 B2 有共同特征；
   C3「碰巧通过的之间没有关联 = 碰巧」：都不成立。
五 只研究，不改模拟盘 / 执行器 / 策略参数。随机种子 numpy.random.default_rng([20261024, 15, …])。非投资建议。
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402

AB_IDS = ("MXR", "SSM", "LOW", "TOM", "TWD", "DXD", "HOL", "SQW", "YRE", "MON", "IDX", "VCP", "DDS", "CSE", "CNQ", "PRF", "GAP", "OVN")
J_IDS = ("PBH", "ROL", "NXG", "PRG", "FCN", "MRH", "EQL", "SAG", "OMG", "PEH", "FGR", "SSS", "PED", "FYB", "SRN", "CHR", "AGR", "PAY")
ALL_IDS = AB_IDS + J_IDS
SAMPLES = ("Z", "E", "J", "Zx", "W", "Jx")
EARLY_AB, LATE_AB = ("Z", "E", "Zx", "W"), ("J", "Jx")
SPLIT = pd.Timestamp("2021-07-01")
NULL_N, PLACEBO_N, KEEP_R = 2000, 400, 200                                   # KEEP_R：B1 的随机期望用前 200 次
SEED = (20261024, 15)
P_MAX, OVERLAP_RATIO, FEAT_SD, WIRING_TOL = 0.05, 1.5, 0.3, 0.005
VERDICTS = ("C0 碰巧通过的有共同的东西、后面的年代还在（值得另登记新循环）", "C1 有一点关联、但合起来用不上",
            "C2 碰巧通过的挡的是同一类票，但这类票在后面的年代不差", "C3 碰巧通过的之间没有关联 = 碰巧")


# ───────────────────────── 重建 36 个做法的挡法 ─────────────────────────
def _std(era: dict, pool: dict) -> dict:
    return {"era": {e: np.asarray(v, bool) for e, v in era.items()}, "pool": {s: np.asarray(v, bool) for s, v in pool.items()}}


def gates_all(W: dict, say=print) -> dict:
    """{做法: {"era": {年代: bool[]（与 signals(W, e) 同序）}, "pool": {池子: bool[]（与 pool_x(W, s) 同序）}}}。"""
    G = {}
    for m in ("loop12_r01_fund", "loop12_r02_fund2", "loop12_r03_fund3"):
        M = importlib.import_module(m)
        B = M.build(W)
        for k in M.IDS:
            G[k] = _std({"J": B["gJ"][k]}, {"Jx": M.gates_of(B["XP"]["Jx"], B["cut"])[k]})
    M = importlib.import_module("loop12_r04_price")
    B = M.build(W)
    for k in M.IDS:
        fn = M.pool_gate(B, k)
        G[k] = _std({e: B["g"][e][k] for e in LC.ERAS}, {s: fn(s, LC.pool_x(W, s)) for s in ("W", "Jx", "Zx") if s in W["D"]})
    for m, js, ab in (("loop12_r05_mix", ("PEH", "FGR"), "TOM"), ("loop12_r06_flow", ("SSS",), "TWD")):
        B = importlib.import_module(m).build(W)
        for k in js:
            G[k] = _std({"J": B["gJ"][k]}, {"Jx": B["gP"][k]})
        G[ab] = _std(B["gT"], B["gTP"])
    B = importlib.import_module("loop12_r07_cal").build(W)
    G["PED"] = _std(B["g"]["PED"], B["gp"]["PED"])
    for k in ("DXD", "HOL"):
        G[k] = _std(B["g"][k], B["gp"][k])
    for m in ("loop13_ra_cal", "loop13_rb_struct", "loop13_rc_jq", "loop14_ra_price", "loop14_rb_jq"):
        B = importlib.import_module(m).build(W)
        for k, v in B.items():
            if not k.startswith("_") and k != "ISS":
                G[k] = _std(v["era"], v["pool"])
        say(f"重建 {m} 完成")
    missing = set(ALL_IDS) - set(G)
    if missing:
        raise RuntimeError(f"没重建出来：{sorted(missing)}")
    return {k: G[k] for k in ALL_IDS}


# ───────────────────────── 样本（假想单笔结果）与逐笔效果 ─────────────────────────
def samples(W: dict) -> dict:
    """{样本: {"net", "cand"（算不算）, "date", "X"（特征表）}}；年代 = 日経225 信号（TBF 没挡、有结果），池子 = B4 会买的。"""
    out = {}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        D = W["D"][e].assign(date=pd.to_datetime(W["D"][e]["date"]))[["ticker", "date", "net"]].drop_duplicates(["ticker", "date"])
        net = S[["ticker", "date"]].merge(D, on=["ticker", "date"], how="left")["net"].to_numpy(float)
        out[e] = {"net": net, "cand": np.isfinite(net) & ~np.asarray(W["tbf"][e], bool), "date": pd.DatetimeIndex(S["date"]), "X": S}
    for s in ("Zx", "W", "Jx"):
        if s in W["D"]:
            X = LC.pool_x(W, s)
            net = X["net"].to_numpy(float)
            out[s] = {"net": net, "cand": np.isfinite(net), "date": pd.DatetimeIndex(pd.to_datetime(X["date"])), "X": X}
    return out


def gate_of(G1: dict, s: str):
    return G1["era"].get(s) if s in LC.ERAS else G1["pool"].get(s)


def effect(net, cand, g) -> float:
    """留下的每笔平均 − 全部的每笔平均（pp）；候选里挡 0 笔或全挡 → NaN。"""
    net, cand, g = np.asarray(net, float), np.asarray(cand, bool), np.asarray(g, bool)
    b = cand & g
    if not b.any() or b.sum() == cand.sum():
        return np.nan
    return float(net[cand & ~g].mean() - net[cand].mean())


def loose_pass(ds) -> bool:
    ds = [d for d in ds if np.isfinite(d)]
    return len(ds) >= 2 and all(d > 0 for d in ds)


def subsets(SM: dict, kind: str) -> dict:
    """前段 / 后段的样本子集：{名字: (样本, mask)}。kind = "AB" / "J"。"""
    if kind == "AB":
        return {"early": [(s, SM[s]["cand"]) for s in EARLY_AB if s in SM], "late": [(s, SM[s]["cand"]) for s in LATE_AB if s in SM]}
    return {"early": [(s, SM[s]["cand"] & (SM[s]["date"] < SPLIT)) for s in ("J", "Jx")],
            "late": [(s, SM[s]["cand"] & (SM[s]["date"] >= SPLIT)) for s in ("J", "Jx")]}


def shuffle_gate(g, cand, rng) -> np.ndarray:
    """候选里挡同样多笔、换成随机的哪几笔（候选之外的照原样）。"""
    g, cand = np.asarray(g, bool), np.asarray(cand, bool)
    out = g.copy()
    idx = np.flatnonzero(cand)
    k = int((g & cand).sum())
    out[idx] = False
    if k:
        out[rng.choice(idx, k, replace=False)] = True
    return out


def stats_of(G: dict, SM: dict) -> dict:
    """每个做法：各样本 d、宽松通过、前段 / 后段 d、前段通过。"""
    out = {}
    for k in ALL_IDS:
        kind = "AB" if k in AB_IDS else "J"
        d = {s: effect(SM[s]["net"], SM[s]["cand"], gate_of(G[k], s)) for s in SAMPLES if s in SM and gate_of(G[k], s) is not None}
        sub = subsets(SM, kind)
        part = {}
        for nm, lst in sub.items():
            part[nm] = [effect(SM[s]["net"], m, gate_of(G[k], s)) for s, m in lst if gate_of(G[k], s) is not None]
        late = [x for x in part["late"] if np.isfinite(x)]
        out[k] = {"d": d, "loose": loose_pass(d.values()), "early": part["early"], "late": part["late"],
                  "early_pass": loose_pass(part["early"]), "late_mean": float(np.mean(late)) if late else np.nan}
    return out


def t_stat(st: dict) -> float:
    a = [v["late_mean"] for v in st.values() if v["early_pass"] and np.isfinite(v["late_mean"])]
    b = [v["late_mean"] for v in st.values() if not v["early_pass"] and np.isfinite(v["late_mean"])]
    return float(np.mean(a) - np.mean(b)) if a and b else np.nan


def null_runs(G: dict, SM: dict, n: int) -> list[dict]:
    """全部做法的挡法一起随机（每个样本各自在候选里挡同样多笔）→ 每次：宽松通过个数、T。"""
    rng = np.random.default_rng([*SEED, 1])
    out = []
    for i in range(n):
        R = {}
        for k in ALL_IDS:
            R[k] = {"era": {}, "pool": {}}
            for s in SAMPLES:
                g = gate_of(G[k], s)
                if g is not None and s in SM:
                    R[k]["era" if s in LC.ERAS else "pool"][s] = shuffle_gate(g, SM[s]["cand"], rng)
        st = stats_of(R, SM)
        out.append({"loose": sum(v["loose"] for v in st.values()), "T": t_stat(st), "R": R if i < KEEP_R else None})
    return out


# ───────────────────────── B1 / B2 ─────────────────────────
def blocked_key(G1: dict, SM: dict) -> set:
    out = set()
    for s in SAMPLES:
        g = gate_of(G1, s)
        if g is not None and s in SM:
            out |= {(s, int(i)) for i in np.flatnonzero(np.asarray(g, bool) & SM[s]["cand"])}
    return out


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else np.nan


def mean_pair_jaccard(sets: list[set]) -> float:
    v = [jaccard(sets[i], sets[j]) for i in range(len(sets)) for j in range(i + 1, len(sets))]
    v = [x for x in v if np.isfinite(x)]
    return float(np.mean(v)) if v else np.nan


def feat_cols(SM: dict) -> list[str]:
    cols = None
    for s in SM.values():
        c = [x for x in s["X"].columns if x not in ("ticker", "date", "net") and pd.api.types.is_numeric_dtype(s["X"][x])]
        cols = c if cols is None else [x for x in cols if x in c]
    return cols or []


def feat_diff(G1: dict, SM: dict, cols: list[str]) -> dict:
    """每个特征：各样本（被挡 − 留下）÷ 全部的标准差，样本平均。"""
    acc = {c: [] for c in cols}
    for s in SAMPLES:
        g = gate_of(G1, s)
        if g is None or s not in SM:
            continue
        cand, g = SM[s]["cand"], np.asarray(g, bool)
        b, k = cand & g, cand & ~g
        if not b.any() or not k.any():
            continue
        X = SM[s]["X"]
        for c in cols:
            v = pd.to_numeric(X[c], errors="coerce").to_numpy(float)
            sd = np.nanstd(v[cand])
            if np.isfinite(sd) and sd > 0 and np.isfinite(v[b]).any() and np.isfinite(v[k]).any():
                acc[c].append((np.nanmean(v[b]) - np.nanmean(v[k])) / sd)
    return {c: float(np.mean(x)) for c, x in acc.items() if x}


def common_feats(diffs: list[dict]) -> list[tuple[str, float]]:
    if len(diffs) < 2:
        return []
    out = []
    for c in set.intersection(*(set(d) for d in diffs)):
        v = np.array([d[c] for d in diffs])
        if (np.all(v > 0) or np.all(v < 0)) and abs(v.mean()) >= FEAT_SD:
            out.append((c, float(v.mean())))
    return sorted(out, key=lambda x: -abs(x[1]))


# ───────────────────────── 判定 ─────────────────────────
def verdict(p_t: float, cons_ok: bool, overlap_ratio: float, n_common: int) -> str:
    if np.isfinite(p_t) and p_t < P_MAX and cons_ok:
        return VERDICTS[0]
    if np.isfinite(p_t) and p_t < P_MAX:
        return VERDICTS[1]
    if (np.isfinite(overlap_ratio) and overlap_ratio >= OVERLAP_RATIO) or n_common > 0:
        return VERDICTS[2]
    return VERDICTS[3]


def recorded_calmar() -> dict:
    """当时结果文件里的候选 Calmar：{做法: {年代: Calmar}}。"""
    from qbreak import paths
    out = {}
    for f in sorted(paths.out_dir().glob("loop1[234]_*.json")):
        if f.stem.endswith("_nodiv"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for k, c in (d.get("cand") or {}).items():
            if k in ALL_IDS and isinstance(c, dict):
                out[k] = {e: (c[e] or {}).get("calmar") for e in LC.ERAS if isinstance(c.get(e), dict)}
    return out


def run(say=print) -> dict:
    t0 = time.time()
    import loop12_r01_fund as R1
    code, dirty = R1.git_head()
    W = LC.load()
    G = gates_all(W, say)
    SM = samples(W)
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    rec = recorded_calmar()
    acct, wiring = {}, []
    for k in ALL_IDS:
        acct[k] = {}
        for e, g in G[k]["era"].items():
            c = LC.run_b4(W, e, g)
            acct[k][e] = None if c["calmar"] is None or base[e]["calmar"] is None else float(c["calmar"] - base[e]["calmar"])
            r = (rec.get(k) or {}).get(e)
            if r is not None and c["calmar"] is not None and abs(float(c["calmar"]) - float(r)) > WIRING_TOL:
                wiring.append({"id": k, "era": e, "now": float(c["calmar"]), "recorded": float(r)})
    say(f"账户 Calmar 重算完成（{time.time() - t0:.0f}s）；与当时不一样的 {len(wiring)} 处")
    st = stats_of(G, SM)
    say(f"随机对照 {NULL_N} 次 …")
    nulls = null_runs(G, SM, NULL_N)
    n_loose = sum(v["loose"] for v in st.values())
    null_loose = np.array([x["loose"] for x in nulls])
    T = t_stat(st)
    null_T = np.array([x["T"] for x in nulls], float)
    p_loose = float((null_loose >= n_loose).mean())
    p_t = float(np.mean(null_T[np.isfinite(null_T)] >= T)) if np.isfinite(T) else np.nan
    passers = [k for k in ALL_IDS if st[k]["loose"]]
    # B1
    sets = {k: blocked_key(G[k], SM) for k in ALL_IDS}
    obs_j = mean_pair_jaccard([sets[k] for k in passers]) if len(passers) >= 2 else np.nan
    exp_j = float(np.nanmean([mean_pair_jaccard([blocked_key(x["R"][k], SM) for k in passers]) for x in nulls[:KEEP_R]])) if len(passers) >= 2 else np.nan
    ratio = obs_j / exp_j if np.isfinite(obs_j) and np.isfinite(exp_j) and exp_j > 0 else np.nan
    pair = {f"{a}-{b}": jaccard(sets[a], sets[b]) for i, a in enumerate(passers) for b in passers[i + 1:]}
    # B2
    cols = feat_cols(SM)
    diffs = {k: feat_diff(G[k], SM, cols) for k in ALL_IDS}
    common = common_feats([diffs[k] for k in passers])
    common_rest = common_feats([diffs[k] for k in ALL_IDS if k not in passers])
    # B3 合起来
    ep_ab = [k for k in AB_IDS if st[k]["early_pass"]]
    cons = {"ids": ep_ab}
    if ep_ab:
        gJ = np.zeros(len(LC.signals(W, "J")), bool)
        gx = np.zeros(len(SM["Jx"]["net"]), bool)
        for k in ep_ab:
            gJ |= G[k]["era"]["J"]
            gx |= G[k]["pool"].get("Jx", np.zeros(len(gx), bool))
        tbf = np.asarray(W["tbf"]["J"], bool)
        c = LC.run_b4(W, "J", gJ)
        dc = None if c["calmar"] is None else float(c["calmar"] - base["J"]["calmar"])
        frac = float((gJ & ~tbf).mean())
        rng = np.random.default_rng([*SEED, 2])
        pl = []
        for i in range(PLACEBO_N):
            r = LC.run_b4(W, "J", (rng.random(len(gJ)) < frac) & ~tbf)
            pl.append(np.nan if r["calmar"] is None else float(r["calmar"] - base["J"]["calmar"]))
            if (i + 1) % 100 == 0:
                say(f"合起来的随机挡 {i + 1} / {PLACEBO_N}（{time.time() - t0:.0f}s）")
        pl = np.array(pl, float)
        q95 = float(np.nanpercentile(pl, 95))
        djx = effect(SM["Jx"]["net"], SM["Jx"]["cand"], gx)
        cons.update({"frac_J": frac, "dcalmar_J": dc, "q95": q95, "pct": float(np.nanmean(pl < dc)) * 100 if dc is not None else None,
                     "d_Jx": djx, "blocked_J": int((gJ & ~tbf).sum()), "blocked_Jx": int(gx.sum()), "trades": c.get("n"), "win": c.get("win")})
        cons["ok"] = bool(dc is not None and dc > q95 and np.isfinite(djx) and djx > 0)
    else:
        cons["ok"] = False
    v = verdict(p_t, cons["ok"], ratio, len(common))
    res = {"code": code, "dirty": dirty, "base": base, "wiring": wiring, "acct": acct, "stats": st, "n_loose": n_loose, "passers": passers,
           "null_loose": {"mean": float(null_loose.mean()), "q95": float(np.percentile(null_loose, 95)), "p": p_loose,
                          "hist": {int(a): int(b) for a, b in zip(*np.unique(null_loose, return_counts=True))}},
           "T": T, "null_T": {"mean": float(np.nanmean(null_T)), "q95": float(np.nanpercentile(null_T, 95)), "p": p_t},
           "early_pass": [k for k in ALL_IDS if st[k]["early_pass"]], "overlap": {"obs": obs_j, "exp": exp_j, "ratio": ratio, "pairs": pair},
           "common": common, "common_rest": common_rest[:10], "diffs": {k: diffs[k] for k in passers}, "consensus": cons,
           "verdict": v, "seconds": round(time.time() - t0)}
    return res


def _f(x, f="{:+.3f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def report(res: dict) -> str:
    st = res["stats"]
    L = [f"# 「碰巧通过」的关联（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；"
         f"规则 scripts/chance_pass_study.py）", "", f"**判定：{res['verdict']}**", "",
         f"- A 宽松判定（逐笔、每个样本都是挡掉的比平均差）：36 个里 **{res['n_loose']} 个**通过（{'、'.join(res['passers']) or '无'}）；"
         f"随机挡同样多笔：平均 {res['null_loose']['mean']:.1f} 个、95 分位 {res['null_loose']['q95']:.0f} 个 → p = {res['null_loose']['p']:.3f}",
         f"- B1 挡的是不是同一批票：宽松通过的两两 Jaccard 平均 {_f(res['overlap']['obs'], '{:.3f}')}、随机期望 {_f(res['overlap']['exp'], '{:.3f}')}、"
         f"比值 {_f(res['overlap']['ratio'], '{:.2f}')}（≥ {OVERLAP_RATIO} 算同一批）",
         f"- B2 共同特征（被挡的 − 留下的，÷ 标准差，宽松通过的都同号、平均 ≥ {FEAT_SD}）："
         + ("、".join(f"{c} {v:+.2f}" for c, v in res["common"]) or "无")
         + "；其余做法（对照）：" + ("、".join(f"{c} {v:+.2f}" for c, v in res["common_rest"]) or "无"),
         f"- B3 前段选、后段验：前段通过 {len(res['early_pass'])} 个（{'、'.join(res['early_pass']) or '无'}）；"
         f"后段 d 差 T = {_f(res['T'])} pp、随机平均 {_f(res['null_T']['mean'])} / 95 分位 {_f(res['null_T']['q95'])} → p = {_f(res['null_T']['p'], '{:.3f}')}"]
    c = res["consensus"]
    if c["ids"]:
        L.append(f"- 前段通过的路线 A / B 做法合起来（{'、'.join(c['ids'])}）放进 J 年代：多挡 {c['blocked_J']} 笔（{c['frac_J'] * 100:.1f}%）、"
                 f"J Calmar 差 {_f(c['dcalmar_J'])}（随机挡 95 分位 {_f(c['q95'])}、胜过随机的 {_f(c['pct'], '{:.1f}')}%）、"
                 f"Jx 挡 {c['blocked_Jx']} 笔、d {_f(c['d_Jx'])} pp → {'✓' if c['ok'] else '✗'}")
    if res["wiring"]:
        L.append(f"- 接线核对：重算的 Calmar 与当时结果文件差 > {WIRING_TOL} 的 {len(res['wiring'])} 处：" +
                 "、".join(f"{w['id']} {w['era']} {w['recorded']:.3f} → {w['now']:.3f}" for w in res["wiring"]))
    else:
        L.append("- 接线核对：36 个做法重算的 Calmar 与当时的结果文件一致")
    L += ["", "| 做法 | 路线 | " + " | ".join(f"d {s}" for s in SAMPLES) + " | 宽松 | 前段 d | 后段 d | 前段通过 | 账户 Calmar 差 Z / E / J |",
          "|" + "---|" * (len(SAMPLES) + 7)]
    for k in ALL_IDS:
        v = st[k]
        a = res["acct"][k]
        L.append(f"| {k} | {'A / B' if k in AB_IDS else 'J'} | " + " | ".join(_f(v["d"].get(s)) for s in SAMPLES)
                 + f" | {'✓' if v['loose'] else ''} | " + " / ".join(_f(x) for x in v["early"]) + " | " + " / ".join(_f(x) for x in v["late"])
                 + f" | {'✓' if v['early_pass'] else ''} | " + " / ".join(_f(a.get(e)) for e in LC.ERAS) + " |")
    L += ["", "d = 留下的每笔平均 − 全部的每笔平均（pp；假想单笔）；> 0 = 挡掉的比平均差。路线 J 的前段 / 后段 = J、Jx 里信号日在 2021-07-01 之前 / 之后。",
          f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    return "\n".join(L)


def main(argv=None) -> int:
    from qbreak import paths
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true", help="只重建挡法、数每个样本挡几笔（不算效果）")
    a = ap.parse_args(argv)
    if a.wiring:
        W = LC.load()
        G = gates_all(W)
        SM = samples(W)
        bad = [(k, s) for k in ALL_IDS for s in SAMPLES if gate_of(G[k], s) is not None and s in SM and len(gate_of(G[k], s)) != len(SM[s]["net"])]
        print(json.dumps({"n": {s: int(SM[s]["cand"].sum()) for s in SM}, "len_mismatch": bad,
                          "blocked": {k: {s: int((np.asarray(gate_of(G[k], s), bool) & SM[s]["cand"]).sum()) for s in SAMPLES
                                          if gate_of(G[k], s) is not None and s in SM} for k in ALL_IDS}}, ensure_ascii=False))
        return 0 if not bad else 1
    res = run()
    text = report(res)
    print(text)
    (paths.out_dir() / "chance_pass_study.md").write_text(text + "\n", encoding="utf-8")
    slim = {k: v for k, v in res.items()}
    (paths.out_dir() / "chance_pass_study.json").write_text(json.dumps(slim, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
