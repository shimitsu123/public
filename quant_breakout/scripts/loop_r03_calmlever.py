"""loop_r03_calmlever.py — 研究循环第 3 轮：平静的牛市里加一点杠杆 LV25（2026-10-01 登记；先提交后只运行一次；用掉 1 个做法 → 4 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题：账户几乎全由闲置资金（纳指 1545 + 美股牛熊分界）决定；第 1 轮 VT20「高波动时减仓」让 J 好很多，但在 E 少赚了高波动之后的反弹；
  第 2 轮「多加一把熊的钥匙」三个年代都更差 → 减仓 / 提前转现金这条路在 E 上走不通。反过来的做法 —— 高波动时**不减**（= B0），
  只在「平静的牛市」里多拿一点（2 倍纳指 2869 占闲置资金的 25% → 纳指的有效比例 1.25）—— 在同一批数据上没做过：
  equity_idle_study 的 Q3 是「牛市时 100% 2 倍」（E 0.758 更好、J / Z 更差，回撤深），不分平静与否。
  照实写：设计时已经知道第 1 轮的结果（平静的日子里减仓是不必要的、急跌前比例会先降）；这一点算在「用掉的做法」里，不当成没看过。
做法 LV25（只有一个；参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 平静 = 日元计纳指的 σ20 < 它自己 1986 年起的扩展中位数（与第 1 轮 VT20 同一个 σ20 与目标：loop_r01_voltarget.sigma / target，美国交易日）；
  - 闲置资金 = 1545 占 0.75、2869（2 倍纳指，equity_idle_study 的合成价：每日重置 2 × (纳指总收益 − 美国 3 个月国库券) + 日本拆借 − 0.825%）占 0.25，
    引擎 core_mode = "follow"：2869 只在「美股牛市且平静」时拿；不平静或熊市时 2869 那份并回 1545（= B0 的 100% 纳指），美股熊市两个都不拿（= B0 的现金）。
    → 平静的牛市：纳指有效比例 1.25；不平静的牛市：1.0（= B0）；熊市：0（= B0）。
  - 2869 的费用 / 滑点 / 一手用 qbreak/fees.py 已登记的值（0.05%、1 口）；其余（个股层、W2、C、X6、判断层）全部同 B0。
  - 接线：2869 永远「熊」（从不拿）时必须与 B0 完全相同。
第一关：research_loop.stage1(候选, 同一次运行的 B0)。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2`）：随机改动 = 把「不平静」的状态序列（美国交易日 2000-01-03〜2026-09-30）
  整体循环平移 k 天（k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20261003, s])），再与真实的美股熊合起来当 2869 的开关 ——
  同样多（加杠杆的天数分布不变）、同样形状（每段长短不变），只是与真实的波动率脱钩；统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述：各年代 2869 拿着的交易日占比、核心换仓笔数、各年收益。
事前预期（照实写）：第一关约 25%（平静的上涨年份多赚；风险是急跌从平静开始时前几天多亏 → 回撤可能深 2 pp 以上，S3 不过）；第二关约 30%；
  「更好候选」约 8%。
运行：python scripts/loop_r03_calmlever.py（第一关）；python scripts/loop_r03_calmlever.py --stage2 [--workers 3]（第二关）。
输出 var/out/loop_r03_calmlever.md / .json（第二关另写 loop_r03_calmlever_stage2.md / .json）。非投资建议。
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

ROUND, ID = 3, "LV25"
W_BASE, W_LEV = 0.75, 0.25
LEV_T, LEV_KEY = "2869.T", "US_LV"
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261003
OUT = "loop_r03_calmlever"


# ───────────────────────── 开关（纯函数，tests/test_loop_r03.py） ─────────────────────────
def volatile(sig: pd.Series, tgt: pd.Series) -> pd.Series:
    """不平静 = σ20 ≥ 目标；算不了（σ 或目标缺）= 不平静（不加杠杆）。"""
    t = tgt.reindex(sig.index)
    ok = sig.notna() & t.notna()
    return pd.Series(~(ok & (sig < t)).to_numpy(bool), index=sig.index)


def lever_off(bear: pd.Series, vol: pd.Series) -> pd.Series:
    """2869 的「熊」= 美股熊 或 不平静（各自向后填，没有值 = 熊 / 不平静一侧按 True 处理）。"""
    idx = bear.index.union(vol.index)
    b = bear.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5
    v = vol.astype(float).reindex(idx).ffill().fillna(1.0) > 0.5
    return pd.Series((b | v).to_numpy(bool), index=idx)


def lever_over(W: dict, off: pd.Series) -> dict:
    xc = dict(W["kw"]["Z"]["extra_core"])
    xc[LEV_T] = W["assets"][LEV_T]
    return {"cfg_over": {"core": {"1545.T": W_BASE, LEV_T: W_LEV}, "core_index": {"1545.T": "US", LEV_T: LEV_KEY}, "core_mode": "follow"},
            "extra_core": xc, "extra_bear": {LEV_KEY: off}}


def shift_domain(s: pd.Series, a: str = SHIFT_FROM, b: str = LCM.J_END) -> pd.Series:
    return s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def shifted(s: pd.Series, seed: int) -> pd.Series:
    w = shift_domain(s)
    return pd.Series(np.roll(w.to_numpy(bool), shift_k(seed, len(w))), index=w.index)


def vol_series(inp: dict) -> pd.Series:
    import equity_idle_study as EI
    import loop_r01_voltarget as V
    sg = V.sigma(V.jpy_ndx(EI.ndx_tr(inp), inp["dexjp"]))
    return volatile(sg, V.target(sg))


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


def held_share(W: dict, e: str, off: pd.Series) -> float | None:
    ctx = W["ctx"][e]
    a, b = ctx["windows"][e]
    g = pd.DatetimeIndex(ctx["days"])
    g = g[(g >= pd.Timestamp(a)) & ((g < pd.Timestamp(b)) if b else True)]
    if not len(g):
        return None
    o = off.astype(float).reindex(g.union(off.index)).ffill().reindex(g).fillna(1.0) > 0.5
    return round(float((~o).mean() * 100), 1)


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r03_calmlever.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py", "scripts/loop_r01_voltarget.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    off = lever_off(W["bear"]["US"], vol_series(W["inp"]))
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, held, years = {}, {}, {}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        tb = core_trades(e, W)
        rc = LCM.run(W, e, **lever_over(W, off))
        tc = core_trades(e, W)
        base[e], cand[e] = _acct(rb), _acct(rc)
        ctr[e] = {"B0": tb, ID: tc}
        held[e] = held_share(W, e, off)
        years[e] = {"B0": rb.get("years") or {}, ID: rc.get("years") or {}}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = RL.stage1(cand, base)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "id": ID, "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "core_trades": ctr, "lever_held_pct": held, "years": years, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    s1, base, cand = res["stage1"], res["base"], res["cand"]
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 研究循环第 3 轮：平静的牛市里加一点杠杆 LV25（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r03_calmlever.py 开头）", "",
         f"**第一关：{'全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；"
         f"S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）", "",
         "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | LV25 | Calmar 差 |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(base[e])} | {cell(cand[e])} | {_f(s1['d'][e], '{:+.3f}')} |")
    L += ["", "只描述：2869 拿着的交易日占比；核心换仓笔数（B0 → LV25，按 ETF）："]
    for e in LCM.ERAS:
        L.append(f"- {e}：2869 {_f(res['lever_held_pct'][e], '{:.1f}')}%；{res['core_trades'][e]['B0']} → {res['core_trades'][e][ID]}")
    ys = sorted({y for e in LCM.ERAS for k in ("B0", ID) for y in (res["years"][e].get(k) or {})})
    L += ["", "各年收益（%）：", "| 方案 | " + " | ".join(ys) + " |", "|---|" + "---|" * len(ys)]
    for k in ("B0", ID):
        vals = {}
        for e, (lo, hi) in (("Z", ("0000", "2006")), ("E", ("2007", "2016")), ("J", ("2017", "9999"))):
            vals.update({y: v for y, v in (res["years"][e].get(k) or {}).items() if lo <= y <= hi})
        L.append(f"| {k} | " + " | ".join(_f(vals.get(y), "{:+.1f}") for y in ys) + " |")
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
    W, vol, base = _G["W"], _G["vol"], _G["base"]
    try:
        off = lever_off(W["bear"]["US"], shifted(vol, seed))
        tot = 0.0
        for e in LCM.ERAS:
            c = LCM.run(W, e, **lever_over(W, off))["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(workers: int) -> int:
    import multiprocessing as mp
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"]
    if not s1["ok"]:
        print("第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = LCM.load()
    vol = vol_series(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    off = lever_off(W["bear"]["US"], vol)
    cand = {e: LCM.run(W, e, **lever_over(W, off))["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "vol": vol, "base": base})
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
    res = {"round": ROUND, "id": ID, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {}, "seconds": round(time.time() - t0)}
    L = [f"# 研究循环第 3 轮 第二关：LV25 vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 3 轮：LV25")
    ap.add_argument("--stage2", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
