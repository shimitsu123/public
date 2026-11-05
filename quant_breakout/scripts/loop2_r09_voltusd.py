"""loop2_r09_voltusd.py — 第二个研究循环第 9 轮：「核心按美元计纳指的波动率调节仓位」VTU（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 9 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；VT20：第一个循环第 1 轮 scripts/loop_r01_voltarget.py（机制与参数照搬）。
为什么做这个（照实写）：
  - 第一个循环第 1 轮 VT20（B0 上：日元计纳指 20 日波动 σ20 高于自己的历史中位数时，核心按 中位数 / σ20 减仓）合计 +0.203、J +0.275（回撤浅 8 pp），
    只输在 S2（E −0.053）；E 少赚的年份（pp）2007 −6.2、2013 −2.3、2014 −3.9、2015 −2.8、2016 −3.7，好几年是日元大波动的年份（2013〜2014 日元急贬、
    2016 日元急升）。当时写过「同一想法换参数再试要另算做法（不打算为了 E 去调，那等于拿检验数据调参）」。
  - 这一轮不调任何参数（20 日、1986 年起的扩展中位数、0.10 的滞后带、σ ≤ 中位数就回到 1 全部照 VT20），只把波动率的计价从日元换成美元：
    理由是基准变了 —— B1 有 FJE（日元走强时换对冲版 2845），汇率风险已经另外处理，再用日元计的波动率等于把汇率风险算两次；按美元计只管股价本身的风险。
    这与第 8 轮 NDRH（NDR 原样接到有 FJE 的 B1 上）是同一个思路，但仍是看过 VT20 的结果之后定的 → 按事后处理，S7 适用。
  - 选题时用过一个只读的子任务通读研究总图找没做过的题（它推荐了这一条）；它看过（照实写）：QQQ 美元计 vs 日元计 σ20 每年「减仓日」的比例（只是状态，
    没有算收益）、S&P 500 的月末月初与 RSI(2) 描述统计（与本轮无关）。
  → 家族「核心·波动率仓位」1 / 3（与第 6 轮 VXB「恐慌指数刹车」不同：那是隐含波动率的门槛刹车，这里是已实现波动率的连续调节）。
做法 VTU（参数照 VT20 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 纳指总收益（equity_idle_study.ndx_tr，美元；1999 年以前 ^NDX + 0.6% 股息估计）的美国交易日对数收益，最近 20 天标准差 × √252 = σ20；
    目标 = σ20 自己 1986-01-01 起的扩展中位数（至少 250 个值，之前 = 比例 1）；比例 = min(1, 目标 / σ20)，与上一次的比例差 ≥ 0.10 才换，σ20 ≤ 目标时直接回到 1。
  - 只作用在不是美股熊的日子：B1 的两个核心键 US_UH / US_HG（1545 / 2845，FJE 照旧）的目标 × 比例（引擎 EXTRA_EXPO），美国 d 日收盘 → 日本 d+1 开盘。
  - 个股层、判断层、费用全部同 B1。接线检查（登记前跑过）：比例全 1 = B1（三个年代与 1987〜2000 只有核心）。
第一关：research_loop2.stage1（posthoc = 1987〜2000 只有核心 VTU − B1 的 Calmar 差；第 5 轮 old_core 同一个合成价与口径，比例按前一天收盘、只在不是熊的日子乘）。
只描述（不参与判定）：各年代美股牛的日子里平均比例、比例 < 1 的日子比例、核心换仓笔数、每年收益差。
第二关（第一关全过才做）：另行登记（提交）后只运行一次（形状照 VT20 登记时写的：比例序列整体循环平移）。
事前预期（照实写）：E 里日元大波动的年份不再误减仓，但 2007、2010、2015 的高波动之后反弹少赚还在；J 的 2020 / 2022 / 2025 减仓仍有，
  2021 / 2026 的上涨里美元波动也偏高、会少赚 → 第一关约 35%、第二关约 40%，「更好候选」约 14%（子任务的估计，照录）。
运行：python scripts/loop2_r09_voltusd.py（第一关）。输出 var/out/loop2_r09_voltusd.md / .json。非投资建议。

第二关（2026-10-02 第一关全过之后另行登记；登记 = 加这一段的那次提交，之后不改、只运行一次，`--stage2 VTU --workers 3`）：
  VT20 登记时写定的形状 —— 比例序列（2000-01-03〜2026-09-30 的美国交易日，N 天）整体循环平移 k 天（k ∈ [250, N − 250]，种子 s = 0〜399：
  numpy.random.default_rng([20262009, s])）→ 比例的分布、每段减仓的长短、换仓次数都不变，只是时点与真实的波动脱钩；窗口外（2000 年以前）= 1；
  FJE 与 B1 的其余部分都不动。统计量 = 三个年代 Calmar 差合计（对同一次运行的 B1），要严格大于 400 次的最大值（research_loop2.stage2；有算不出的 = 不过）。
  事前预期（照实写）：减仓的日子不少（J 牛日 31.9%），随机放在上涨里多半少赚 → 随机的多半比 B1 差；但碰上 2020-02〜03、2022、2025-02〜04 的几次会很好看
  （VT20 登记时也写过「循环平移里偶然把减仓放到几次大跌上的情况不少」）→ 约 35%。输出 var/out/loop2_r09_voltusd_stage2_VTU.md / .json。
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
import loop_r01_voltarget as VT                                              # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 9
IDS = ("VTU",)
FAMILY = "核心·波动率仓位"
POSTHOC = True
OLD = R5.OLD
OUT = "loop2_r09_voltusd"
SHIFT_FROM, SHIFT_GAP, SEED0 = VT.SHIFT_FROM, VT.SHIFT_GAP, 20262009  # 第二关（另行登记）：VT20 同一个形状，种子换成本轮的


# ───────────────────────── 比例与接法（tests/test_loop2_r09.py） ─────────────────────────
def ratio_usd(ndx_tr: pd.Series) -> pd.Series:
    """VT20 的机制原样，输入换成美元计的纳指总收益。"""
    sg = VT.sigma(ndx_tr.dropna().sort_index())
    return VT.exposure(sg, VT.target(sg))


def vtu_over(x: pd.Series) -> dict:
    """B1 的两个核心键（1545 → US_UH、2845 → US_HG）× 比例（引擎 EXTRA_EXPO；美股熊时核心本来就是 0）。"""
    import loop_r04_yensurge as Y
    x = x.astype(float).clip(0.0, 1.0)
    return {"extra_expo": {Y.UH_KEY: x, Y.HG_KEY: x}}


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def shifted(x: pd.Series, seed: int, a: str = SHIFT_FROM, b: str = L2.J_END) -> pd.Series:
    """第二关的随机改动：窗口里的比例序列整体循环平移；窗口外不给（引擎按 1）。"""
    w = x[(x.index >= pd.Timestamp(a)) & (x.index <= pd.Timestamp(b))]
    return pd.Series(np.roll(w.to_numpy(float), shift_k(seed, len(w))), index=w.index)


def old_core(W: dict, uni: pd.Series, x: pd.Series | None) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第 5 轮 old_core 同一个合成价与口径）；x = 比例（None = B1），前一天收盘的比例决定当天、只在不是熊的日子乘。"""
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
    xx = ff(x).fillna(1.0).to_numpy() if x is not None else np.ones(len(idx))
    n = len(idx)
    eq = np.ones(n)
    pu0 = ph0 = 0.0
    for t in range(1, n):
        e = 0.0 if bear[t - 1] else float(xx[t - 1])
        pu, ph = (0.0, e) if hdg[t - 1] else (e, 0.0)
        turn = abs(pu - pu0) + abs(ph - ph0)
        eq[t] = eq[t - 1] * (1 + pu * ru[t] + ph * rh[t] - turn * HW.SWITCH_COST / 100)
        pu0, ph0 = pu, ph
    out = EI.curve_stats(pd.Series(eq, index=idx))
    bull = ~bear
    out["mean_ratio_bull"] = round(float(xx[bull].mean()), 3) if bull.any() else None
    return out


def describe(W: dict, e: str, x: pd.Series, n_core: tuple[int, int]) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    s = x[(x.index >= pd.Timestamp(a)) & ((x.index < pd.Timestamp(b)) if b else True)]
    bus = W["bear"]["US"].astype(float).reindex(s.index.union(W["bear"]["US"].index)).ffill().reindex(s.index).fillna(0.0) > 0.5
    bull = s[~bus.to_numpy()]
    return {"bull_days": int(len(bull)), "mean_ratio_bull": round(float(bull.mean()), 3) if len(bull) else None,
            "cut_pct_of_bull": round(float((bull < 1.0 - 1e-9).mean() * 100), 1) if len(bull) else None,
            "min_ratio": round(float(bull.min()), 3) if len(bull) else None, "core_trades": {"B1": n_core[0], "VTU": n_core[1]}}


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r09_voltusd.py", "scripts/loop_r01_voltarget.py",
                                 "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py", "scripts/research_loop2.py",
                                 "scripts/candle_portfolio.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    x = ratio_usd(EI.ndx_tr(W["inp"]))
    ov = vtu_over(x)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, x, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, None), "VTU": old_core(W, uni, x)}
    unseen = None if old["B1"]["calmar"] is None or old["VTU"]["calmar"] is None else old["VTU"]["calmar"] - old["B1"]["calmar"]
    s1 = {"VTU": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"VTU": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["VTU"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 9 轮：核心按美元计纳指的波动率调节仓位 VTU（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r09_voltusd.py 开头）", "",
         f"- **VTU（VT20 原样，波动率改按美元计）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | VTU（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['VTU'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：美股牛的日子里平均比例 {_f(d['mean_ratio_bull'])}、比例 < 1 的日子 {_f(d['cut_pct_of_bull'], '{:.1f}')}%、最低 {_f(d['min_ratio'])}；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → VTU {d['core_trades']['VTU']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["VTU"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VTU − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；VTU {oc(o['VTU'])}（美股牛的日子里平均比例 {o['VTU']['mean_ratio_bull']}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    W, x, base = _G["W"], _G["x"], _G["base"]
    try:
        ov = vtu_over(shifted(x, seed))
        tot = 0.0
        for e in L2.ERAS:
            c = L2.run(W, e, **ov)["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(k: str, workers: int) -> int:
    import multiprocessing as mp
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = L2.load()
    x = ratio_usd(EI.ndx_tr(W["inp"]))
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    cand = {e: L2.run(W, e, **vtu_over(x))["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    _G.update({"W": W, "x": x, "base": base})
    seeds = list(range(R2.PLACEBO_N))
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
    s2 = R2.stage2(stat, vals)
    vd = R2.verdict(s1, s2)
    v = np.array([z for z in vals if z is not None], float)
    res = {"round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第二个研究循环第 9 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B1 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 9 轮：VTU（核心按美元计纳指的波动率调节仓位）")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
