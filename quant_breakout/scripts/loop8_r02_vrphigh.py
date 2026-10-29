"""loop8_r02_vrphigh.py — 第八个研究循环（新的独立信息来源）第 2 轮：期权的波动风险溢价「高的一端」VRB —— 熊市里 VRP 高就先拿回 1/3
（2026-10-04 登记；先提交后只运行一次；来源「期权·波动风险溢价」2 / 3；事后（看过第 1 轮的五分位之后设计）→ S7 适用）。

用户（2026-10-04）：「进行真正提高，需要新的、独立的信息来源的研究」。循环的规则：scripts/research_loop8.py 开头。
为什么做这个（照实写；看过第 1 轮结果之后设计 = 事后）：
  - 第 1 轮（f042dc6）A 信息检查过：VRP 高 → 之后一个季度收益高（合并 IC +0.089、p = 0.070、5 个市场里 4 个同方向）；但信息集中在最高五分位
    （之后 63 天 US +4.88%、EU +2.28%、IN +5.41%、NDX +5.35%），规则 VRN 用的「牛市里 VRP ≤ 0 → 减仓」一端几乎没有信息 → 第一关不过。
  - 账户在美股牛市里已经 100% 拿纳指（不加杠杆就加不上去）→ 高的一端只能用在美股熊市（B3 拿 1482 / 现金）里：熊市里期权市场要的风险补偿高 → 先拿回一部分。
  - 第六个循环 BPR（熊市里「不是急跌」就先拿回 1/3）第一关不过（Z −0.074）：只靠价格分不出熊市里哪段该拿；这一轮换成期权的信息（新的来源）。
A 信息检查：沿用第 1 轮（同一个信号 VRP、同一个统计量、已过；不重跑）。只描述：熊市月末子样本的 IC、有 / 没有旗标的熊市月末之后 63 天的平均收益。
旗标（每个市场自己的数据，第 1 轮的 VRP 原样）：每个已结束的月末收盘，VRP ≥ 这个市场之前 60 个已结束月末（VRP 有值的）的 80 分位（numpy quantile，linear）
  → 旗标 = 真，到下一个月末为止；之前不够 60 个 / 当天 VRP 算不了 → 假。80 分位 = 第 1 轮五分位里「最高的一档」；之前 60 个月末（5 年）= 用最近的历史定「高」
  （登记前只数过日子：从头累计的分位让澳大利亚只有 2 个月末触发 —— VRP 的水平这些年在变 → 改用滚动 60 个；没看任何收益）。
规则 VRB（没有别的新参数；1/3 = BPR 那 1/3）：
  - 账户（B3 上）：美股熊 ∧ 旗标（美国 S&P 500 的 VRP，同第 1 轮；美国日期 ≤ 东证日，同 B3 的美股熊）→ 1545 拿回 1/3：股债负相关时 1545 : 1482 = 1 : 2，
    否则 1545 1/3 + 2/3 现金（= 第六个循环 BPR 的接法原样：loop6_r10_bearpartial.bpr_over，BPR 的「信号」= 这里的「没有旗标」）；
    其余同 B3（美股牛 → 1545 全拿；美股熊 ∧ 没有旗标 → 负相关 1482、否则现金）。
  - 横展开（每个市场）：牛 → 100%；不是牛 ∧ 旗标 → 1/3；其余现金（research_loop7.nav：收盘决定、下一个交易日起生效、换仓扣 0.1% × 换的比例）。
第一关：research_loop6.stage1（S1〜S4 + S7：1987〜2000 只有核心 VRB − B3 > 0；口径 = BPR 的 old_core；VIX 1990 年起、旗标要 60 个月末 → 1987〜2000 里 1995 年以后才可能拿回）。
第二关（横展开，US / EU / AU / IN，2009-01-01〜2026-09-30，同第 1 轮；BR 只描述）：基准 = 自己的牛熊分界（牛 100%、其余现金）；
  随机对照 = 旗标只在窗口内「不是牛」的日子上（每个市场自己的交易日）整体循环平移同一个 k —— 熊市里拿回的天数与段的长短不变，只打乱时点
  （规则只在不是牛的日子起作用；在全部日子上平移会把旗标移到牛的日子、拿回的天数变少，对照不公平）；
  k ∈ [250, N_min − 250]，N_min = 4 个市场窗口内不是牛的日数的最小值；numpy default_rng([20261012, 0, s])，s = 0〜399；
  research_loop7.judge（合并 > 0 且严格大于 400 次最大、Δ > 0 的市场 ≥ 3 / 4、两半的合并都 > 0）。第 1 轮已看过这 4 个市场的五分位（照实写）。
判定：更好候选 = 第一关全过（含 S7）∧ 第二关三条都过；否则第一关不过 / 第二关不过（两关都运行、都报）。
只描述：BR / NDX 的 Δ；各市场旗标的月末比例、窗口内不是牛的日子里有旗标的比例；账户各年代美股熊的日子里拿回 1/3 的比例与段数（分负相关 / 不是）；
  核心换仓笔数；每年收益差；最新一天的状态；熊市月末子样本的 IC 与平均收益。
接线核对（--wiring，不看任何收益）：旗标全假 → 三个年代与 B3 逐项相同、old_core = B3、4 个市场 Δ 全为 0（平移后也是）；B3 没有别的 extra_expo / core_expo。
规模（--scale，只数日子）。运行：python scripts/loop8_r02_vrphigh.py（只运行一次）；--scale；--wiring。输出 var/out/loop8_r02_vrphigh.md / .json。非投资建议。
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
import loop8_r01_vrp as V1                                                   # noqa: E402
import research_loop7 as R7                                                  # noqa: E402
import research_loop8 as RL8                                                 # noqa: E402

ROUND = 2
FAMILY = "期权·波动风险溢价"
IDS = ("VRB",)
POSTHOC = True
Q, HIST = 0.8, 60                                                            # 之前 60 个月末的 80 分位
PART = 1.0 / 3.0                                                             # 熊市里拿回的份额（= BPR 的 1/3）
CROSS = V1.CROSS
DESC_X = ("BR", "NDX")
WINDOW_B = V1.WINDOW_B
SEED_B = 20261012
PLACEBO_N, SHIFT_GAP = 400, 250
OUT = "loop8_r02_vrphigh"
_f = V1._f


# ───────────────────────── 规则（纯函数，tests/test_loop8_r02.py） ─────────────────────────
def flag_me(close: pd.Series, vrp_s: pd.Series, q: float = Q, hist: int = HIST) -> pd.Series:
    """已结束的月末：VRP ≥ 之前 hist 个（VRP 有值的）月末的 q 分位 → 真；不够 hist 个 / 当天算不了 → 假（当天的值不进自己的分位）。"""
    c = close.dropna().sort_index()
    me = RL8.month_ends_done(c)
    v = vrp_s.reindex(me)
    out, past = [], []
    for x in v.to_numpy(float):
        h = past[-hist:]
        out.append(bool(np.isfinite(x) and len(h) >= hist and x >= float(np.quantile(h, q))))
        if np.isfinite(x):
            past.append(float(x))
    return pd.Series(out, index=me, dtype=bool)


def flag_daily(close: pd.Series, f_me: pd.Series) -> pd.Series:
    """每个交易日：最近一个已结束月末（含当天）的旗标；第一个月末之前 = 假。月末当天收盘决定、下一个交易日起生效（nav / 引擎）。"""
    c = close.dropna().sort_index()
    s = f_me.astype(float).reindex(c.index.union(f_me.index)).ffill().reindex(c.index).fillna(0.0)
    return pd.Series(s.to_numpy(float) > 0.5, index=c.index)


def expo_vrb(bull: pd.Series, flag: pd.Series, part: float = PART) -> pd.Series:
    """牛 → 1；不是牛 ∧ 旗标 → part；其余 0（现金）。"""
    b = bull.astype(bool)
    f = flag.reindex(b.index).fillna(False).astype(bool).to_numpy()
    return pd.Series(np.where(b.to_numpy(bool), 1.0, np.where(f, part, 0.0)), index=b.index)


def shift_nonbull(flag: pd.Series, bull: pd.Series, k: int | None, w=WINDOW_B) -> pd.Series:
    """第二关：窗口内「不是牛」的日子上，旗标整体循环平移 k（这些日子里有旗标的天数不变）；牛的日子与窗外不动；None = 不平移。"""
    b = bull.astype(bool)
    f = flag.reindex(b.index).fillna(False).astype(bool).copy()
    if k is None:
        return f
    nb = b.index[(b.index >= pd.Timestamp(w[0])) & (b.index <= pd.Timestamp(w[1])) & ~b.to_numpy(bool)]
    if len(nb):
        f.loc[nb] = np.roll(f.loc[nb].to_numpy(bool), int(k))
    return f


def nonbull_days(bull: pd.Series, w=WINDOW_B) -> int:
    b = bull.astype(bool)
    i = (b.index >= pd.Timestamp(w[0])) & (b.index <= pd.Timestamp(w[1]))
    return int((~b[i]).sum())


def shift_ks(n_min: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    if n_min <= 2 * gap:
        raise ValueError(f"不是牛的日子太少（{n_min} ≤ {2 * gap}）")
    return [int(np.random.default_rng([SEED_B, 0, int(s)]).integers(gap, n_min - gap + 1)) for s in seeds]


def deltas(closes: dict, flags: dict, bulls: dict, k: int | None, w=WINDOW_B) -> dict[str, list[float | None]]:
    """每个市场：窗口 / 前一半 / 后一半的 Calmar（候选 = VRB，旗标按 k 平移）− 基准（牛 100%）。"""
    out = {}
    for m, c in closes.items():
        b = bulls[m].reindex(c.index).fillna(False).astype(bool)
        base = R7.nav(c, b.astype(float))
        cand = R7.nav(c, expo_vrb(b, shift_nonbull(flags[m], b, k, w)))
        row = []
        for a, z in V1.spans_of(c, w):
            cb, cc = R7.calmar(base, a, z), R7.calmar(cand, a, z)
            row.append(None if cb is None or cc is None else cc - cb)
        out[m] = row
    return out


def flags_of(D: dict) -> dict[str, pd.Series]:
    return {m: flag_daily(D[m]["close"], flag_me(D[m]["close"], D[m]["vrp"]["vrp"])) for m in D}


# ───────────────────────── 账户（B3 上，BPR 的接法） ─────────────────────────
def account_inputs(W: dict, flag_us: pd.Series) -> dict:
    """B3 的输入（loop6_r07_volbond.inputs）+ 美国日的「没有旗标」（= BPR 的信号：熊市里照 B3 不拿）与东证日上的同一个。"""
    import loop6_r07_volbond as V
    M = V.inputs(W)
    sig_us = ~flag_us.astype(bool)
    M["sig_us"], M["sig_t"] = sig_us, V.on_idx(sig_us, M["days"])
    return M


def account_scale(W: dict, M: dict) -> dict:
    import loop6_common as L6
    import loop6_r07_volbond as V
    import loop6_r10_bearpartial as BP
    out = {e: BP.state_share(M["bear_t"], M["sig_t"], M["on_b"], V.era_days(W, e)) for e in L6.ERAS}
    old = W["bear"]["US"]
    old = old[(old.index >= pd.Timestamp(V.OLD[0])) & (old.index <= pd.Timestamp(V.OLD[1]))].astype(bool)
    s_old = V.on_idx(M["sig_us"], old.index)
    part = old & ~s_old
    out["old"] = {"bear_days": int(old.sum()), "part_pct": round(float(part.sum() / max(1, int(old.sum())) * 100), 1), "part_segments": V.segments(part)}
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "flag": bool(~M["sig_t"].iloc[-1]), "corr_neg": bool(M["on_b"].iloc[-1])}
    return out


def stage_one(W: dict, M: dict) -> dict:
    import loop2_r05_ddbrake as R5
    import loop6_common as L6
    import loop6_r10_bearpartial as BP
    import research_loop6 as R6
    import loop7_r02_voltarget as P2
    t0 = time.time()
    ov = BP.bpr_over(W, M, M["sig_t"])
    reg = RL8.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**P2._acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**P2._acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VRB": nc}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": BP.old_core(W, None), "VRB": BP.old_core(W, M["sig_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["VRB"]["calmar"] is None else old["VRB"]["calmar"] - old["B3"]["calmar"]
    s1 = R6.stage1(cand, base, posthoc=unseen)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "core_trades": trades, "old": old, "drift": drift,
            "scale": account_scale(W, M), "seconds": round(time.time() - t0)}


# ───────────────────────── 第二关（横展开） ─────────────────────────
def stage_two(D: dict, F: dict) -> dict:
    t0 = time.time()
    closes = {m: D[m]["close"] for m in CROSS}
    bulls = {m: D[m]["bull"] for m in CROSS}
    flags = {m: F[m] for m in CROSS}
    real = deltas(closes, flags, bulls, None)
    n_min = min(nonbull_days(bulls[m].reindex(closes[m].index).fillna(False)) for m in CROSS)
    ks = shift_ks(n_min)
    plac, per = [], {m: [] for m in CROSS}
    for i, k in enumerate(ks):
        r = deltas(closes, flags, bulls, k)
        full = [v[0] for v in r.values()]
        plac.append(None if any(x is None for x in full) else float(np.mean(full)))
        for m in CROSS:
            per[m].append(r[m][0])
        if (i + 1) % 100 == 0:
            print(f"随机 {i + 1} / {len(ks)}（{time.time() - t0:.0f}s）", flush=True)
    jd = R7.judge(real, plac)
    pct = {m: (round(float(np.mean([1.0 if (p is not None and p < real[m][0]) else 0.0 for p in per[m]]) * 100), 1)
               if real[m][0] is not None else None) for m in CROSS}
    extra = deltas({m: D[m]["close"] for m in DESC_X}, {m: F[m] for m in DESC_X}, {m: D[m]["bull"] for m in DESC_X}, None)
    return {"real": real, "own_pctile": pct, "extra": extra, "n_min": int(n_min), "ks": ks, "placebo": plac, "judge": jd,
            "seconds": round(time.time() - t0)}


# ───────────────────────── 只描述 / 规模 ─────────────────────────
def describe(D: dict) -> dict:
    """熊市（月末不是牛）月末子样本：VRP 与之后 63 天收益的 IC；有 / 没有旗标的平均收益（只描述，不参与判定）。"""
    out = {}
    for m in list(CROSS) + list(DESC_X):
        c, v = D[m]["close"], D[m]["vrp"]["vrp"]
        s = V1.samples(c, v)
        fm = flag_me(c, v).reindex(s.index).fillna(False).astype(bool)
        bear = ~D[m]["bull"].reindex(s.index).fillna(False).astype(bool)
        sb = s[bear]
        on, off = sb[fm[bear]], sb[~fm[bear]]
        out[m] = {"n_bear": int(len(sb)), "ic_bear": RL8.spearman(sb["x"], sb["y"]),
                  "flag": {"n": int(len(on)), "mean_pct": round(float(on["y"].mean() * 100), 2) if len(on) else None},
                  "noflag": {"n": int(len(off)), "mean_pct": round(float(off["y"].mean() * 100), 2) if len(off) else None}}
    return out


def scale(D: dict, F: dict) -> dict:
    out = {}
    for m in list(CROSS) + list(DESC_X):
        c = D[m]["close"]
        fm = flag_me(c, D[m]["vrp"]["vrp"])
        valid = D[m]["vrp"]["vrp"].reindex(fm.index).notna()
        act = fm[valid].iloc[HIST:]
        days = R7.window_days(c, WINDOW_B)
        nb = ~D[m]["bull"].reindex(days).fillna(False).astype(bool)
        on = F[m].reindex(days).fillna(False).astype(bool) & nb
        out[m] = {"flags": int(fm.sum()), "flag_pct": round(float(act.mean() * 100), 1) if len(act) else None,
                  "first": str(fm[fm].index[0].date()) if fm.any() else None, "nonbull_days": int(nb.sum()),
                  "nonbull_flag_pct": round(float(on.sum() / max(1, int(nb.sum())) * 100), 1),
                  "segments": int((on.to_numpy()[1:] & ~on.to_numpy()[:-1]).sum() + (1 if len(on) and on.iloc[0] else 0))}
    return out


# ───────────────────────── 运行 ─────────────────────────
def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop8_r02_vrphigh.py", "scripts/loop8_r01_vrp.py",
                                 "scripts/research_loop8.py", "scripts/research_loop7.py", "scripts/loop6_r10_bearpartial.py",
                                 "qbreak/bullbear.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def round1_info() -> dict | None:
    from qbreak import paths
    p = paths.out_dir() / "loop8_r01_vrp.json"
    if not p.exists():
        return None
    j = json.loads(p.read_text(encoding="utf-8"))
    return {"code": j.get("code"), "judge": (j.get("info") or {}).get("judge")}


def run_all() -> int:
    import loop6_common as L6
    t0 = time.time()
    code, dirty = git_head()
    D = V1.inputs()
    F = flags_of(D)
    W = L6.load3()
    M = account_inputs(W, F["US"])
    a = stage_one(W, M)
    b = stage_two(D, F)
    res = {"loop": 8, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty,
           "info": {"reused": round1_info()}, "scale": scale(D, F), "account": a, "cross": b, "describe": describe(D),
           "verdict": R7.FOUND if (a["ok"] and b["judge"]["ok"]) else (R7.FAIL1 if not a["ok"] else R7.FAIL2)}
    res["seconds"] = round(time.time() - t0)
    write(res)
    return 0


def write(res: dict) -> None:
    import loop6_common as L6
    from qbreak import paths
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    a, b, sc, ds = res["account"], res["cross"], res["scale"], res["describe"]
    s, bj = a["stage1"], b["judge"]
    ri = (res["info"].get("reused") or {}).get("judge") or {}
    L = [f"# 第八个研究循环第 2 轮：期权的波动风险溢价「高的一端」VRB —— 熊市里 VRP 高就先拿回 1/3（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop8_r02_vrphigh.py 开头；事后 → S7 适用）", "",
         f"**{res['verdict']}**", "",
         f"A 信息检查：沿用第 1 轮（代码 {(res['info'].get('reused') or {}).get('code')}；合并 IC {_f(ri.get('pooled'))}、p = {_f(ri.get('p'), '{:.3f}')}、"
         f"{ri.get('agree')} / {ri.get('n')} 个市场同方向 → {'过' if ri.get('ok') else '不过'}）", "",
         f"## 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
         f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(s['posthoc'].get('unseen'))}）：{yn(s['S7'])}；S5 / S6 不适用", "",
         "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VRB（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                      f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
    ac = a["scale"]
    L += ["", "只描述：" + "；".join(
        f"{e} 美股熊 {ac[e]['bear_days']} 天里拿回 1/3 {_f(ac[e]['part_pct'], '{:.1f}')}%（{ac[e]['part_segments']} 段；负相关 {_f(ac[e]['part_bond_pct'], '{:.1f}')}%、"
        f"不是 {_f(ac[e]['part_cash_pct'], '{:.1f}')}%）、核心换仓 B3 {a['core_trades'][e]['B3']} → VRB {a['core_trades'][e]['VRB']} 笔" for e in L6.ERAS)]
    o = a["old"]
    L.append("1987〜2000 只有核心（S7 用）：" + "、".join(f"{k} {_f(o[k]['calmar'], '{:.3f}')}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%）"
                                                  for k in ("B3", "VRB")) + f"；美股熊 {ac['old']['bear_days']} 天里拿回 1/3 {ac['old']['part_pct']}%（{ac['old']['part_segments']} 段）")
    for e in L6.ERAS:
        yb, yc = a["base"][e].get("years") or {}, a["cand"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VRB − B3，pp）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    lt = ac["latest"]
    L.append(f"- 最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、旗标 {'是' if lt['flag'] else '否'}、股债负相关 {'是' if lt['corr_neg'] else '否'}")
    dr = a["drift"]
    L.append("B3 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS))
    L += ["", f"## 第二关（横展开，{' / '.join(CROSS)}，{WINDOW_B[0]}〜{WINDOW_B[1]}；旗标只在不是牛的日子上平移）：{'三条都过' if bj.get('ok') else '不过'}",
          f"C1 {yn(bj.get('C1'))}（合并 {_f(bj.get('pooled'))}，400 次随机最大 {_f(bj.get('max'))}、中位 {_f((bj.get('q') or {}).get(50))}、≥ 候选 {bj.get('ge_stat')} 次）；"
          f"C2 {yn(bj.get('C2'))}（{bj.get('positive')} / {bj.get('n')}，要 ≥ {bj.get('need')}）；C3 {yn(bj.get('C3'))}（{_f(bj.get('h1'))} / {_f(bj.get('h2'))}）；N_min {b['n_min']}",
          "各市场 Δ（全窗口 / 前一半 / 后一半；随机百分位）：" + "；".join(
              f"{m} {' / '.join(_f(v) for v in b['real'][m])}（{_f(b['own_pctile'][m], '{:.1f}')}）" for m in CROSS)
          + "；只描述：" + "；".join(f"{m} {' / '.join(_f(v) for v in b['extra'][m])}" for m in b["extra"]),
          "", "## 只描述",
          "旗标：" + "；".join(f"{m} {sc[m]['flags']} 个月末（够 60 个之后 {_f(sc[m]['flag_pct'], '{:.1f}')}%，首次 {sc[m]['first']}）、窗口内不是牛 {sc[m]['nonbull_days']} 天里有旗标 "
                              f"{_f(sc[m]['nonbull_flag_pct'], '{:.1f}')}%（{sc[m]['segments']} 段）" for m in sc),
          "熊市月末子样本（之后 63 天）：" + "；".join(
              f"{m} IC {_f(ds[m]['ic_bear'])}（{ds[m]['n_bear']} 个）、有旗标 {ds[m]['flag']['n']} 次 {_f(ds[m]['flag']['mean_pct'], '{:+.2f}')}% / 没有 {ds[m]['noflag']['n']} 次 "
              f"{_f(ds[m]['noflag']['mean_pct'], '{:+.2f}')}%" for m in ds),
          "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    import loop6_common as L6
    D = V1.inputs()
    F = flags_of(D)
    out = {"markets": scale(D, F)}
    W = L6.load3()
    out["account"] = account_scale(W, account_inputs(W, F["US"]))
    out["n_min"] = min(nonbull_days(D[m]["bull"].reindex(D[m]["close"].index).fillna(False)) for m in CROSS)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    """登记前用（不看任何收益）：旗标全假 → 三个年代与 B3 逐项相同、old_core = B3、4 个市场 Δ 全为 0（平移后也是）；B3 没有别的 extra_expo / core_expo。"""
    import loop6_common as L6
    import loop6_r10_bearpartial as BP
    import loop7_r02_voltarget as P2
    D = V1.inputs()
    W = L6.load3()
    no_other = {e: all(k not in (W["kw"][e] or {}) and k not in (W.get("b1") or {}) for k in ("extra_expo", "core_expo")) for e in L6.ERAS}
    M = account_inputs(W, pd.Series(False, index=D["US"]["close"].index))
    ov = BP.bpr_over(W, M, M["sig_t"])
    same = {e: bool(all(L6.run(W, e).get(x) == L6.run(W, e, **ov).get(x) for x in P2.KEYS)) for e in L6.ERAS}
    o0, o1 = BP.old_core(W, None), BP.old_core(W, M["sig_us"])
    old_same = all(o0.get(k) == o1.get(k) for k in ("cagr", "dd", "calmar"))
    zf = {m: pd.Series(False, index=D[m]["close"].index) for m in CROSS}
    cl, bu = {m: D[m]["close"] for m in CROSS}, {m: D[m]["bull"] for m in CROSS}
    z, zs = deltas(cl, zf, bu, None), deltas(cl, zf, bu, 321)
    zero = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in z.values())
    zero_s = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in zs.values())
    out = {"no_other_expo": no_other, "flag_false_same_as_b3": same, "old_core_same": old_same, "cross_false_zero": zero, "cross_false_shift_zero": zero_s}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if (all(no_other.values()) and all(same.values()) and old_same and zero and zero_s) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第八个研究循环第 2 轮：VRP 高的一端 VRB（熊市里 VRP 高 → 先拿回 1/3）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看任何收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
