"""loop_r15_fxeunion.py — 研究循环第 15 轮：「FJH 换成参数多数决版」FJE = FXE ∪ JBH（2026-10-01 登记；先提交后只运行一次；用掉 1 个做法 → 18 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题（照实写：看过第 4 / 11 / 13 / 14 轮之后设计的，是第 14 轮 FJH 的稳健性检查）：
  第 14 轮 FJH（FXH ∪ JBH）第一关全过、第二关约第 99 百分位，是到现在证据最强的一个；但第 11 轮已经看到 FXH 那一组参数（10 天 −3%）偏有利
  （9 组相邻参数的多数决 FXE 只有 FXH 的约六成、约第 94 百分位）。这一轮回答「FJH 的强度是不是靠 FXH 碰巧挑中的参数」：
  把 FXH 换成第 11 轮登记的 FXE（9 组参数里 ≥ 5 组在急升中），JBH 不变，其余全同第 14 轮。给「FXH / JBH / FJH 要不要加进前向记录」做参考。
做法（不学参数 → S6 不适用；不改个股买卖 → S5 不适用）：
  FJE 「对冲中」= FXE 的多数决急升中（loop_r11_fxensemble.ensemble_state）或 JBH 的对冲中（loop_r13_jpbearhedge.state_series：日経熊且日元牛）
      —— 各自向后填之后取「或」；对冲中且美股牛 → 闲置资金拿对冲版纳指 2845（第 4 轮同一合成价与接法）；其余 = B0。接线：对冲永远不成立时必须与 B0 完全相同。
第一关：research_loop.stage1（trade = None、lenses = None）。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2 FJE`）：把合并后的「对冲中」序列（日本 / 美国交易日合并，2000-01-03〜2026-09-30）
  整体循环平移 k 天（k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20261015, s])）；统计量 = 三个年代 Calmar 差合计，
  要严格大于 400 次的最大值。
只描述：各年代对冲中占美股牛日子的比例与段数（其中只有 FXE / 只有 JBH / 两个都是）、核心换仓笔数；没看过的 1987〜2000 只有核心的
  B0 开关 / FXE / JBH / FJE 年化 / 最大回撤 / Calmar。
事前预期（照实写）：FXE 比 FXH 弱（Z +0.046 vs +0.099）→ FJE 约 Z +0.0〜+0.05、E 约 +0.1〜+0.15、J 约 +0.1；第一关约 55%（Z 是风险）；
  第二关约 10%；「更好候选」约 5%。
运行：python scripts/loop_r15_fxeunion.py（第一关）；python scripts/loop_r15_fxeunion.py --stage2 FJE [--workers 3]（第二关）。
输出 var/out/loop_r15_fxeunion.md / .json（第二关另写 loop_r15_fxeunion_stage2_FJE.md / .json）。非投资建议。
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
import loop_common as LCM                                                    # noqa: E402
import research_loop as RL                                                   # noqa: E402

ROUND = 15
IDS = ("FJE",)
OLD = ("1987-01-01", "2000-12-31")
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261015
OUT = "loop_r15_fxeunion"


# ───────────────────────── 状态（纯函数，tests/test_loop_r14.py） ─────────────────────────
def union_state(fxh: pd.Series, jbh: pd.Series) -> pd.Series:
    """两个「对冲中」（各自的日子）→ 合并的日子上 fxe（参数名 fxh）或 jbh（各自向后填，没有值 = False）。"""
    import loop_r04_yensurge as Y
    return Y.or_series(fxh, jbh)


def parts(fxh: pd.Series, jbh: pd.Series, idx) -> dict[str, pd.Series]:
    """在 idx 上：只有 FXH / 只有 JBH / 两个都是。"""
    idx = pd.DatetimeIndex(idx)
    f = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx).fillna(0.0) > 0.5   # noqa: E731
    a, b = f(fxh), f(jbh)
    return {"fxh_only": a & ~b, "jbh_only": b & ~a, "both": a & b}


def shift_domain(s: pd.Series, a: str = SHIFT_FROM, b: str = LCM.J_END) -> pd.Series:
    return s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def shifted(s: pd.Series, seed: int) -> pd.Series:
    w = shift_domain(s)
    return pd.Series(np.roll(w.to_numpy(bool), shift_k(seed, len(w))), index=w.index)


def episodes(s: pd.Series) -> int:
    v = s.to_numpy(bool)
    return int(((v[1:]) & (~v[:-1])).sum() + (1 if len(v) and v[0] else 0))


# ───────────────────────── 数据 ─────────────────────────
def states(W: dict) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(FXE 多数决急升中, JBH 对冲中, 合并)。"""
    import loop_r11_fxensemble as X
    import loop_r13_jpbearhedge as J
    fxh = X.ensemble_state(W["inp"]["dexjp"])
    jbh = J.state_series(W)
    return fxh, jbh, union_state(fxh, jbh)


def fje_over(W: dict, state: pd.Series, hedged: pd.DataFrame) -> dict:
    import loop_r04_yensurge as Y
    return Y.fxh_over(W, W["bear"]["US"], state, hedged)


def old_core(inp: dict, bear: pd.Series, hs: dict[str, pd.Series]) -> dict:
    """只描述：1987〜2000 只有核心（日元计纳指不对冲 / 对冲版），B0 的开关与各个「对冲中」（第 11 / 13 轮同一做法）。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    from qbreak import factors
    dex = inp["dexjp"].dropna()
    ntr = EI.ndx_tr(inp)
    unh = EI.grow(ntr, -EI.FEE["1545.T"])
    unh = (unh * dex.reindex(unh.index.union(dex.index)).ffill().reindex(unh.index)).dropna()
    hed = FX.hedged_index(EI.grow(ntr, -0.22), factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9))
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    unh, hed = unh.reindex(idx), hed.reindex(idx).ffill()
    out = {"B0": EI.curve_stats(FX.core_only(unh, hed, bear, pd.Series(False, index=idx)))}
    for k, h in hs.items():
        out[k] = EI.curve_stats(FX.core_only(unh, hed, bear, h))
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def core_trades(e: str, W: dict) -> dict:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    out: dict = {}
    for x in eng.st.core_trades:
        if x[0] >= a and (b is None or x[0] < b):
            out[x[1]] = out.get(x[1], 0) + 1
    return out


def describe(W: dict, e: str, fxh: pd.Series, jbh: pd.Series, uni: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    bus = W["bear"]["US"]
    m = (bus.index >= pd.Timestamp(a)) & ((bus.index < pd.Timestamp(b)) if b else True)
    bull = ~bus[m].astype(bool)
    n = int(bull.sum())
    def on(s):
        return s.astype(float).reindex(bull.index.union(s.index)).ffill().fillna(0.0).reindex(bull.index).gt(0.5) & bull
    u = on(uni)
    p = {k: int((v & bull).sum()) for k, v in parts(fxh, jbh, bull.index).items()}
    pct = lambda x: round(x / n * 100, 1) if n else None                     # noqa: E731
    return {"in_bull_pct": pct(int(u.sum())), "episodes": episodes(u), "fxh_only_pct": pct(p["fxh_only"]),
            "jbh_only_pct": pct(p["jbh_only"]), "both_pct": pct(p["both"])}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r15_fxeunion.py", "scripts/loop_common.py", "scripts/research_loop.py",
                                 "scripts/loop_r04_yensurge.py", "scripts/loop_r11_fxensemble.py", "scripts/loop_r13_jpbearhedge.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import loop_r04_yensurge as Y
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    fxh, jbh, uni = states(W)
    hedged = Y.hedged_frame(W["inp"])
    ov = fje_over(W, uni, hedged)
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, desc = {}, {"FJE": {}}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": core_trades(e, W)}
        base[e] = _acct(rb)
        rc = LCM.run(W, e, **ov)
        ctr[e]["FJE"] = core_trades(e, W)
        cand["FJE"][e] = _acct(rc)
        desc[e] = describe(W, e, fxh, jbh, uni)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"FJE": RL.stage1(cand["FJE"], base)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "core_trades": ctr, "describe": desc, "old": old_core(W["inp"], W["bear"]["US"], {"FXE": fxh, "JBH": jbh, "FJE": uni}),
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["FJE"]
    L = [f"# 研究循环第 15 轮：参数多数决版的合并对冲（FXE ∪ JBH）（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r15_fxeunion.py 开头）", "",
         f"- **FJE（FXE 的多数决急升中 或 JBH 的日経熊且日元牛）且美股牛 → 闲置资金拿对冲版纳指 2845：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）",
         "", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | FJE（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['FJE'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：对冲中 {_f(d['in_bull_pct'], '{:.1f}')}%（占美股牛的日子；只有 FXE {_f(d['fxh_only_pct'], '{:.1f}')}%、只有 JBH {_f(d['jbh_only_pct'], '{:.1f}')}%、"
                 f"两个都是 {_f(d['both_pct'], '{:.1f}')}%）、{d['episodes']} 段；核心换仓 B0 {c['B0']} → FJE {c['FJE']}")
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心、日元计纳指）：B0 的开关 {oc(o['B0'])}；FXE {oc(o['FXE'])}；JBH {oc(o['JBH'])}；FJE {oc(o['FJE'])}")
    dr = res["drift"]
    L += ["", "B0 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in LCM.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= RL.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B0）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


# ───────────────────────── 第二关 ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    W, state, hedged, base = _G["W"], _G["state"], _G["hedged"], _G["base"]
    try:
        ov = fje_over(W, shifted(state, seed), hedged)
        tot = 0.0
        for e in LCM.ERAS:
            c = LCM.run(W, e, **ov)["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(k: str, workers: int) -> int:
    import multiprocessing as mp
    import loop_r04_yensurge as Y
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = LCM.load()
    _, _, state = states(W)
    hedged = Y.hedged_frame(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = {e: LCM.run(W, e, **fje_over(W, state, hedged))["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "state": state, "hedged": hedged, "base": base})
    seeds = list(range(RL.PLACEBO_N))
    vals = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
            if (i + 1) % 40 == 0:
                print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    s2 = RL.stage2(stat, vals)
    vd = RL.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {}, "seconds": round(time.time() - t0)}
    L = [f"# 研究循环第 15 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 15 轮：FJE")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
