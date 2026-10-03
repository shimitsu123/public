"""loop_r11_fxensemble.py — 研究循环第 11 轮：日元急升对冲的「参数多数决」版 FXE（2026-10-01 登记；先提交后只运行一次；用掉 1 个做法 → 14 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题（照实写：FXH 家族、看了第 4 轮 FXH 的结果之后设计的）：
  到第 10 轮为止，三个年代都变好的只有第 4 轮 FXH（10 天 −3% 起、收在 20 日线上止 → 对冲版纳指；Z +0.099、E +0.012、J +0.090，第二关约第 98 百分位）；
  其余的核心择时都是「两个年代好、一个年代坏」。FXH 是否加进前向记录要用户决定 —— 这一轮回答「FXH 的结果是不是碰巧挑中了一组参数」：
  不挑参数，9 组相邻参数（起点窗口 5 / 10 / 20 个美国交易日 × 跌幅 −2% / −3% / −4%，结束都照 FXH「收在 20 日线之上」）各自一条急升状态，
  **9 条里 ≥ 5 条在急升中** 才对冲（多数决）。另报（只描述、不参与判定）没看过的 1987〜2000 只有核心的长历史：B0 的开关 / FXH / FXE。
做法（参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  FXE USD/JPY = FRED DEXJPUS；每组参数用第 4 轮同一个状态机（loop_r04_yensurge.surge_state）；多数决的「急升中」且美股牛 → 闲置资金拿对冲版纳指 2845
      （第 4 轮同一合成价与接法：hedged_frame / fxh_over）；其余 = B0。美国 d 日的值决定 d+1 开盘成交。接线：急升永远不成立时必须与 B0 完全相同。
第一关：research_loop.stage1（trade = None、lenses = None）。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2 FXE`）：把多数决的「急升中」序列（美国交易日 2000-01-03〜2026-09-30）整体循环平移 k 天
  （k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20261011, s])）；统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述：各年代多数决急升中占美股牛日子的比例与段数、与 FXH 的状态重合度；核心换仓笔数；1987〜2000 只有核心（日元计纳指不对冲 / 对冲版，
  fxhedge_study.core_only：前一天收盘的状态决定当天、每次换仓 0.1%）的 B0 开关 / FXH / FXE 年化 / 最大回撤 / Calmar。
事前预期（照实写）：第一关约 60%（多数决多半与 FXH 很像）；第二关约 5%（FXH 约第 98 百分位）；「更好候选」约 3%。
  这一轮主要的用处是看 FXH 的结果对参数稳不稳、在没看过的年代是不是同一个方向（给「FXH 要不要加进前向记录」做参考）。
运行：python scripts/loop_r11_fxensemble.py（第一关）；python scripts/loop_r11_fxensemble.py --stage2 FXE [--workers 3]（第二关）。
输出 var/out/loop_r11_fxensemble.md / .json（第二关另写 loop_r11_fxensemble_stage2_FXE.md / .json）。非投资建议。
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

ROUND = 11
IDS = ("FXE",)
WINS, THRS, MA_N, MAJ = (5, 10, 20), (-0.02, -0.03, -0.04), 20, 5
OLD = ("1987-01-01", "2000-12-31")
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261011
OUT = "loop_r11_fxensemble"


# ───────────────────────── 状态（纯函数，tests/test_loop_r11.py） ─────────────────────────
def variants() -> list[tuple[int, float]]:
    return [(n, t) for n in WINS for t in THRS]


def ensemble_state(fx: pd.Series, maj: int = MAJ) -> pd.Series:
    """9 组参数各自一条急升状态（第 4 轮的状态机），≥ maj 条在急升中 → True。"""
    import loop_r04_yensurge as Y
    s = fx.dropna().sort_index()
    votes = np.zeros(len(s), int)
    for n, t in variants():
        votes += Y.surge_state(s, n, t, MA_N).reindex(s.index).fillna(False).to_numpy(bool).astype(int)
    return pd.Series(votes >= maj, index=s.index)


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
def fxe_over(W: dict, state: pd.Series, hedged: pd.DataFrame) -> dict:
    import loop_r04_yensurge as Y
    return Y.fxh_over(W, W["bear"]["US"], state, hedged)


def old_core(inp: dict, bear: pd.Series, fxh: pd.Series, fxe: pd.Series) -> dict:
    """只描述：1987〜2000 只有核心（日元计纳指不对冲 / 对冲版），B0 的开关 / FXH / FXE。"""
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
    never = pd.Series(False, index=idx)
    out = {}
    for k, h in (("B0", never), ("FXH", fxh), ("FXE", fxe)):
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


def describe(W: dict, e: str, fxe: pd.Series, fxh: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    bus = W["bear"]["US"]
    m = (bus.index >= pd.Timestamp(a)) & ((bus.index < pd.Timestamp(b)) if b else True)
    bull = ~bus[m].astype(bool)
    def on(s):
        return s.astype(float).reindex(bull.index.union(s.index)).ffill().fillna(0.0).reindex(bull.index).gt(0.5) & bull
    e_on, h_on = on(fxe), on(fxh)
    both, either = int((e_on & h_on).sum()), int((e_on | h_on).sum())
    return {"in_bull_pct": round(float(e_on.sum() / bull.sum() * 100), 1) if int(bull.sum()) else None, "episodes": episodes(e_on),
            "overlap_with_fxh": round(both / either, 3) if either else None}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r11_fxensemble.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py", "scripts/loop_r04_yensurge.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import loop_r04_yensurge as Y
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    fx = W["inp"]["dexjp"]
    fxe, fxh = ensemble_state(fx), Y.surge_state(fx.dropna())
    hedged = Y.hedged_frame(W["inp"])
    ov = fxe_over(W, fxe, hedged)
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, desc = {}, {"FXE": {}}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": core_trades(e, W)}
        base[e] = _acct(rb)
        rc = LCM.run(W, e, **ov)
        ctr[e]["FXE"] = core_trades(e, W)
        cand["FXE"][e] = _acct(rc)
        desc[e] = describe(W, e, fxe, fxh)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"FXE": RL.stage1(cand["FXE"], base)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "core_trades": ctr, "describe": desc, "old": old_core(W["inp"], W["bear"]["US"], fxh, fxe), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["FXE"]
    L = [f"# 研究循环第 11 轮：日元急升对冲的参数多数决版（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r11_fxensemble.py 开头）", "",
         f"- **FXE 9 组相邻参数里 ≥ 5 组在急升中且美股牛 → 闲置资金拿对冲版纳指 2845：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）",
         "", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | FXE（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['FXE'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：多数决急升中 {_f(d['in_bull_pct'], '{:.1f}')}%（占美股牛的日子）、{d['episodes']} 段；与 FXH 的重合度 {_f(d['overlap_with_fxh'])}；"
                 f"核心换仓 B0 {c['B0']} → FXE {c['FXE']}")
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心、日元计纳指）：B0 的开关 {oc(o['B0'])}；FXH {oc(o['FXH'])}；FXE {oc(o['FXE'])}")
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
        ov = fxe_over(W, shifted(state, seed), hedged)
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
    state, hedged = ensemble_state(W["inp"]["dexjp"]), Y.hedged_frame(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = {e: LCM.run(W, e, **fxe_over(W, state, hedged))["calmar"] for e in LCM.ERAS}
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
    L = [f"# 研究循环第 11 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 11 轮：FXE")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
