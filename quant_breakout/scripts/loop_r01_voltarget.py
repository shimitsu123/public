"""loop_r01_voltarget.py — 研究循环第 1 轮：闲置资金（纳指 1545）按波动率调节仓位 VT20（2026-10-01 登记；先提交后只运行一次）。

循环的规则：scripts/research_loop.py（第一关 S1〜S6、第二关 400 次随机改动、上限 20 个做法）；基准 B0：scripts/loop_common.py。
为什么挑这个题：账户的收益与回撤几乎全由闲置资金决定（个股层平均只占约 5〜7% 的资金，leap_r12）→「比现在更好」最可能来自闲置资金这一层。
  B0 的闲置资金 Q1（纳指 1545 + 美股牛熊分界）在牛市里一直满仓，牛市里的急跌（2011-08、2015-08、2018-02、2018 年末、2020-03、2025-04 等）
  只靠 250 日线 ±3%、连续 5 天的牛熊分界，反应慢；纳指的波动又比 S&P 500 大。
已经看过的（照实写，所以这不是「没看过的检验」）：scripts/vol_target_study.py（2026-09-24，只有 S&P 500 指数、2006〜2026）里
  「牛熊择时 × 波动率管理」V2 的 Calmar 0.636 vs 现行择时 0.384、前后两半都更好，但年化低 1.45 pp → 按那次的规则（年化不能低 0.5 pp 以上）不采用。
  「回撤变浅 → Calmar 提高」在美国指数上大致已知；这一轮是在 B0 的整个账户（纳指、日元、个股层、判断层）上，按循环的规则
  （看 Calmar、不看年化、要超过 400 次随机改动的最大值）检验。
做法（只有一个 = 用掉 1 个做法）：VT20
  - 波动率：纳指总收益（scripts/equity_idle_study.ndx_tr，QQQ 复权价加回费用；1999 年以前 = ^NDX + 年 0.6% 股息估计）× USD/JPY
    （FRED DEXJPUS，向前填）= 日元计的纳指；美国交易日的对数收益，最近 20 个美国交易日的标准差 × √252 = σ20。
  - 目标：σ20 自己的历史中位数（1986-01-01 起到当天的扩展窗口，至少 250 个值；之前 = 比例 1）。
  - 比例 = min(1, 目标 / σ20)；与上一次的比例差 ≥ 0.10 才换（滞后带），σ20 ≤ 目标时直接回到 1；起点 1。
    （登记前只看过比例序列本身、没看任何结果：滞后带会让平静时期停在 0.9 附近，所以加了「回到 1」；接线检查 = 比例全 1 时与 B0 完全相同、全 0.5 时不同。）
  - 只作用在不是熊市的日子（熊市照旧现金）：引擎的 core_expo["US"]（非熊市时核心目标再乘这个比例），按美国收盘日给、引擎向后填到日本交易日
    （与美股牛熊分界同一个时点：美国 d 日收盘 → 日本 d+1 开盘成交）；核心的换仓仍按引擎的带宽（权益的 10%）。
  - 其余（个股层、W2、C、X6、判断层、费用）全部同 B0。参数（20 日、中位数、0.10）事先写定，不从 2001 年以后的数据学 → S6 不适用；
    不改个股的买卖 → S5 不适用（个股仓位按权益的 25%，只随权益间接变化）。
第一关：research_loop.stage1(候选, 同一次运行的 B0)。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2`）：随机改动 = 把 VT20 的比例序列（2000-01-03〜2026-09-30 的美国交易日，
  N 天）整体循环平移 k 天，k 在 [250, N − 250] 里均匀抽（种子 s = 0〜399：numpy.random.default_rng([20261001, s])）——
  同样多（比例的分布不变）、同样形状（每段减仓的长短、换仓次数不变），只是时点和真实的波动率脱钩。每次三个年代都跑，
  统计量 = 三个年代 Calmar 差合计（对同一次运行的 B0）；候选要严格大于 400 次里最大的那个（research_loop.stage2）。
只描述（不判定）：各年代不是熊市的日子里的平均比例、比例 < 1 的日子占比、核心换仓笔数、各年收益（B0 与 VT20）。
事前预期（照实写）：第一关约 45%（回撤多半变浅；Z 2003〜2006 低波动期几乎不动；E 的 2009〜2010 高波动反弹会少赚）；
  第二关约 20%（循环平移里偶然把减仓放到几次大跌上的情况不少，严格超过 400 次里的最大值很难）；「更好候选」合计约 10%。
运行：python scripts/loop_r01_voltarget.py（第一关）；python scripts/loop_r01_voltarget.py --stage2 [--workers 3]（第二关）。
输出 var/out/loop_r01_voltarget.md / .json（第二关另写 loop_r01_voltarget_stage2.md / .json）。非投资建议。
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

ROUND, ID = 1, "VT20"
WIN_N = 20
TGT_START, TGT_MIN = "1986-01-01", 250
BAND = 0.10
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261001
OUT = "loop_r01_voltarget"


# ───────────────────────── 比例序列（纯函数，tests/test_loop_r01.py） ─────────────────────────
def jpy_ndx(tr: pd.Series, fx: pd.Series) -> pd.Series:
    """日元计的纳指（美国交易日）= 纳指总收益 × USD/JPY（向前填）。"""
    tr = tr.dropna().sort_index()
    f = fx.dropna().sort_index()
    f = f.reindex(tr.index.union(f.index)).ffill().reindex(tr.index)
    return (tr * f).dropna()


def sigma(px: pd.Series, n: int = WIN_N) -> pd.Series:
    r = np.log(px.astype(float)).diff()
    return r.rolling(n, min_periods=n).std() * np.sqrt(252)


def target(sig: pd.Series, start: str = TGT_START, min_n: int = TGT_MIN) -> pd.Series:
    s = sig[sig.index >= pd.Timestamp(start)].dropna()
    return s.expanding(min_periods=min_n).median()


def exposure(sig: pd.Series, tgt: pd.Series, band: float = BAND) -> pd.Series:
    """min(1, 目标 / σ)，滞后带 band（差 ≥ band 才换；σ ≤ 目标 → 直接回到 1），起点 1；算不了的日子 = 1。"""
    idx = sig.index
    raw = (tgt.reindex(idx) / sig).clip(upper=1.0).fillna(1.0).to_numpy(float)
    out = np.empty(len(raw))
    cur = 1.0
    for i, v in enumerate(raw):
        if v >= 1.0 - 1e-12 or abs(v - cur) >= band - 1e-12:
            cur = float(v)
        out[i] = cur
    return pd.Series(out, index=idx)


def shift_domain(e: pd.Series, a: str = SHIFT_FROM, b: str = LCM.J_END) -> pd.Series:
    return e[(e.index >= pd.Timestamp(a)) & (e.index <= pd.Timestamp(b))]


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def shifted(e: pd.Series, seed: int) -> pd.Series:
    w = shift_domain(e)
    return pd.Series(np.roll(w.to_numpy(float), shift_k(seed, len(w))), index=w.index)


def vt_series(inp: dict) -> pd.Series:
    import equity_idle_study as EI
    px = jpy_ndx(EI.ndx_tr(inp), inp["dexjp"])
    sg = sigma(px)
    return exposure(sg, target(sg))


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def core_trades(e: str, W: dict) -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    d = [x[0] for x in eng.st.core_trades]
    return int(sum(1 for x in d if x >= a and (b is None or x < b)))


def describe(e: str, W: dict, ex: pd.Series) -> dict:
    """不是熊市的日本交易日里的平均比例、比例 < 1 的占比（%）。"""
    ctx = W["ctx"][e]
    a, b = ctx["windows"][e]
    g = pd.DatetimeIndex(ctx["days"])
    g = g[(g >= pd.Timestamp(a)) & ((g < pd.Timestamp(b)) if b else True)]
    bear = W["bear"]["US"]
    bj = bear.reindex(g.union(bear.index)).ffill().reindex(g).fillna(False).to_numpy(bool)
    x = ex.reindex(g.union(ex.index)).ffill().reindex(g).fillna(1.0).to_numpy(float)
    on = ~bj
    return {"mean_expo": round(float(x[on].mean()), 3) if on.any() else None,
            "lt1_pct": round(float((x[on] < 1 - 1e-9).mean() * 100), 1) if on.any() else None,
            "bull_pct": round(float(on.mean() * 100), 1)}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r01_voltarget.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    ex = vt_series(W["inp"])
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, desc, trades, years = {}, {}, {}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        tb = core_trades(e, W)
        rc = LCM.run(W, e, core_expo={"US": ex})
        tc = core_trades(e, W)
        base[e], cand[e] = _acct(rb), _acct(rc)
        trades[e] = {"B0": tb, ID: tc}
        years[e] = {"B0": rb.get("years") or {}, ID: rc.get("years") or {}}
        desc[e] = describe(e, W, ex)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    s1 = RL.stage1(cand, base)
    res = {"round": ROUND, "id": ID, "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "describe": desc, "core_trades": trades, "years": years, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    s1, base, cand = res["stage1"], res["base"], res["cand"]
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 研究循环第 1 轮：闲置资金按波动率调节仓位 VT20（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r01_voltarget.py 开头）", "",
         f"**第一关：{'全过 → 另行登记第二关' if s1['ok'] else '不过 → ' + RL.FAIL1}**（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；"
         f"S2 每个年代 ≥ −0.02：{yn(s1['S2'])}；S3 回撤不深 2 pp：{yn(s1['S3'])}；S4 前后两半（{_f(s1['h1'], '{:+.3f}')} / "
         f"{_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 不适用；S6 不适用）", "",
         "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | VT20 | Calmar 差 |", "|---|---|---|---|"]
    for e in LCM.ERAS:
        b, c = base[e], cand[e]
        cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
                          f"（{_f(x['h1'])} / {_f(x['h2'])}）")
        L.append(f"| {e} | {cell(b)} | {cell(c)} | {_f(s1['d'][e], '{:+.3f}')} |")
    L += ["", "只描述：不是熊市的日子里 VT20 的平均比例 / 比例 < 1 的日子占比 / 不是熊市的日子占比；核心换仓笔数（B0 → VT20）："]
    for e in LCM.ERAS:
        d, t = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：平均 {_f(d['mean_expo'])}、< 1 占 {_f(d['lt1_pct'], '{:.1f}')}%、牛市日 {_f(d['bull_pct'], '{:.1f}')}%；"
                 f"核心换仓 {t['B0']} → {t[ID]} 笔")
    ys = sorted({y for e in LCM.ERAS for k in ("B0", ID) for y in (res["years"][e].get(k) or {})})
    L += ["", "各年收益（%）：", "| 方案 | " + " | ".join(ys) + " |", "|---|" + "---|" * len(ys)]
    for k in ("B0", ID):
        vals = {}
        for e, (lo, hi) in (("Z", ("0000", "2006")), ("E", ("2007", "2016")), ("J", ("2017", "9999"))):
            vals.update({y: v for y, v in (res["years"][e].get(k) or {}).items() if lo <= y <= hi})
        L.append(f"| {k} | " + " | ".join(_f(vals.get(y), "{:+.1f}") for y in ys) + " |")
    dr = res["drift"]
    L += ["", "B0 与登记值（var/research_loop.json）的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in LCM.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= RL.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B0）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


# ───────────────────────── 第二关 ─────────────────────────
_W: dict = {}


def _placebo_one(seed: int) -> float | None:
    W, ex, base = _W["W"], _W["ex"], _W["base"]
    try:
        sh = shifted(ex, seed)
        tot = 0.0
        for e in LCM.ERAS:
            c = LCM.run(W, e, core_expo={"US": sh})["calmar"]
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
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))
    if not s1["stage1"]["ok"]:
        print("第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = LCM.load()
    ex = vt_series(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = {e: LCM.run(W, e, core_expo={"US": ex})["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _W.update({"W": W, "ex": ex, "base": base})
    seeds = list(range(RL.PLACEBO_N))
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            vals = []
            for k, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (k + 1) % 20 == 0:
                    print(f"随机改动 {k + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        vals = []
        for k in seeds:
            vals.append(_placebo_one(k))
            if (k + 1) % 20 == 0:
                print(f"随机改动 {k + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    s2 = RL.stage2(stat, vals)
    vd = RL.verdict(s1["stage1"], s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"round": ROUND, "id": ID, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["stage1"]["sum"],
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {}, "seconds": round(time.time() - t0)}
    L = [f"# 研究循环第 1 轮 第二关：VT20 vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['stage1']['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 1 轮：VT20")
    ap.add_argument("--stage2", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
