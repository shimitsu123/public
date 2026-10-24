"""loop_r04_yensurge.py — 研究循环第 4 轮：日元急升时的闲置资金 FXH / FXC（2026-10-01 登记；先提交后只运行一次；用掉 2 个做法 → 6 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题（基准 B0 的回撤诊断，只看 B0、没看任何候选；scratch 计算，数字照实写）：
  J 的三次最大回撤都在美股牛市里、牛熊分界还没翻（2020-02-21〜03-13 −29.0%、2025-01-24〜04-09 −22.3%、2024-07-11〜08-08 −21.9%），
  E 的 2007-11-01〜2008-01-09 −20.4% 也是；其中 2024-08（USD/JPY 161 → 142）、2025-04、2007-11、2010〜2011 都伴着日元急升 ——
  闲置资金拿的是不对冲的纳指，避险时日元升值让它「双重下跌」。以前做过的是慢的版本：「日元走强趋势（USD/JPY < 200 日线）→ 对冲版」
  （fxhedge_study、core_switch_study 的 C）：日元走强的年代好、2017 年以后差（年代依赖）。只在**急升的几周**里处理、之后马上回来 —— 同一批数据上没做过。
状态（两个做法共用，参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  USD/JPY = FRED DEXJPUS（纽约中午的值，美国 d 日 → 日本 d+1 早上已知；与引擎的美股牛熊同一个时点：d 日的值决定 d+1 开盘成交），缺的日子向前填。
  急升开始：10 个美国交易日的变化 ≤ −3%；急升结束：USD/JPY 收在 20 日均线之上；其间 = 急升中。
做法（各自独立判定）：
  FXH 急升中闲置资金拿「对冲版纳指」2845（合成：纳指总收益的美元本地收益 + (日本 − 美国 短期利率)/252，fxhedge_study.hedged_index 同一做法，
      年费 0.22%，取前一个美国收盘；价格水平按 2026-08-31 = ¥2,000、一手 1 口；费用 / 滑点 qbreak/fees.py 没登记 → etf_cost 的缺省），
      急升结束换回 1545；美股熊市照旧现金。引擎 core_mode = "follow"（1545 与 2845 只拿其中一个）。接线：急升永远不发生时必须与 B0 完全相同。
  FXC 急升中闲置资金转现金，急升结束买回 1545；美股熊市照旧现金。接线同上。
第一关：research_loop.stage1（两个都 trade = None、lenses = None）。
第二关（第一关全过的做法；另行登记（提交）后只运行一次，`--stage2 FXH|FXC`）：把「急升中」状态序列（美国交易日 2000-01-03〜2026-09-30）
  整体循环平移 k 天（k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20261004, s])）—— 同样多（急升中的天数不变）、同样形状（每段长短不变），
  只是与真实的汇率脱钩；统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述：各年代急升中的交易日占比、急升次数、核心换仓笔数。
事前预期（照实写）：FXH 第一关约 25%（2024-08、2025-04、2007-11、2010〜2011 少亏日元那一段；2020-03 是日元先升后贬、对冲在反转点附近 → 吃亏）；
  FXC 第一关约 15%（同时躲开纳指的下跌，但「快速离场」一类以前多半被来回换拖累）；第二关各约 25%；「更好候选」FXH 约 6%、FXC 约 4%。
运行：python scripts/loop_r04_yensurge.py（第一关）；python scripts/loop_r04_yensurge.py --stage2 FXH [--workers 3]（第二关）。
输出 var/out/loop_r04_yensurge.md / .json（第二关另写 loop_r04_yensurge_stage2_<做法>.md / .json）。非投资建议。
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

ROUND = 4
IDS = ("FXH", "FXC")
CHG_N, CHG_THR, MA_N = 10, -0.03, 20
HEDGE_T, HEDGE_FEE, HEDGE_REF, REF_DATE = "2845.T", 0.22, 2000.0, "2026-08-31"
UH_KEY, HG_KEY, CASH_KEY = "US_UH", "US_HG", "US_FX"
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261004
OUT = "loop_r04_yensurge"


# ───────────────────────── 状态（纯函数，tests/test_loop_r04.py） ─────────────────────────
def surge_state(fx: pd.Series, n: int = CHG_N, thr: float = CHG_THR, ma_n: int = MA_N) -> pd.Series:
    """急升中：n 日变化 ≤ thr 时开始，收在 ma_n 日均线之上时结束（同一天两个条件都看：开始优先）。"""
    s = fx.dropna().sort_index()
    chg = s / s.shift(n) - 1
    ma = s.rolling(ma_n, min_periods=ma_n).mean()
    on = np.zeros(len(s), bool)
    cur = False
    for i in range(len(s)):
        c, m, p = chg.iloc[i], ma.iloc[i], s.iloc[i]
        if not cur and np.isfinite(c) and c <= thr:
            cur = True
        elif cur and np.isfinite(m) and p > m:
            cur = False
        on[i] = cur
    return pd.Series(on, index=s.index)


def or_series(a: pd.Series, b: pd.Series) -> pd.Series:
    idx = a.index.union(b.index)
    aa = a.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5
    bb = b.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5
    return pd.Series((aa | bb).to_numpy(bool), index=idx)


def fxh_over(W: dict, bear: pd.Series, surge: pd.Series, hedged: pd.DataFrame) -> dict:
    xc = dict(W["kw"]["Z"]["extra_core"])
    xc[HEDGE_T] = hedged
    return {"cfg_over": {"core": {"1545.T": 1.0, HEDGE_T: 1.0}, "core_index": {"1545.T": UH_KEY, HEDGE_T: HG_KEY}, "core_mode": "follow"},
            "extra_core": xc, "extra_bear": {UH_KEY: or_series(bear, surge), HG_KEY: or_series(bear, ~surge.astype(bool))}}


def fxc_over(bear: pd.Series, surge: pd.Series) -> dict:
    return {"cfg_over": {"core": {"1545.T": 1.0}, "core_index": {"1545.T": CASH_KEY}, "core_mode": "split"},
            "extra_bear": {CASH_KEY: or_series(bear, surge)}}


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
def hedged_frame(inp: dict) -> pd.DataFrame:
    """对冲版纳指的日本交易日 K 线（只有收盘；fxhedge_study.hedged_index 同一做法；按 REF_DATE 定价格水平）。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    from qbreak import factors
    us_r, jp_r = factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9)
    h = EI.grow(FX.hedged_index(EI.ndx_tr(inp), us_r, jp_r), -HEDGE_FEE)
    days = inp["n225"].index[inp["n225"].index >= EI.START]
    c = EI.on_jp(h, None, days)
    c = c * (HEDGE_REF / float(c.asof(pd.Timestamp(REF_DATE))))
    return EI.frame_close(c)


def surge_series(inp: dict) -> pd.Series:
    return surge_state(inp["dexjp"].dropna())


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


def surge_share(W: dict, e: str, surge: pd.Series) -> tuple[float | None, int]:
    ctx = W["ctx"][e]
    a, b = ctx["windows"][e]
    s = surge[(surge.index >= pd.Timestamp(a)) & ((surge.index < pd.Timestamp(b)) if b else True)]
    return (round(float(s.mean() * 100), 1) if len(s) else None), episodes(s)


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r04_yensurge.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def _overs(W: dict, k: str, surge: pd.Series, hedged: pd.DataFrame) -> dict:
    bus = W["bear"]["US"]
    return fxh_over(W, bus, surge, hedged) if k == "FXH" else fxc_over(bus, surge)


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    surge = surge_series(W["inp"])
    hedged = hedged_frame(W["inp"])
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, desc = {}, {k: {} for k in IDS}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": core_trades(e, W)}
        base[e] = _acct(rb)
        for k in IDS:
            rc = LCM.run(W, e, **_overs(W, k, surge, hedged))
            ctr[e][k] = core_trades(e, W)
            cand[k][e] = _acct(rc)
        sh, ne = surge_share(W, e, surge)
        desc[e] = {"surge_pct": sh, "episodes": ne}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {k: RL.stage1(cand[k], base) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "core_trades": ctr, "describe": desc, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    name = {"FXH": "日元急升中闲置资金换对冲版纳指", "FXC": "日元急升中闲置资金转现金"}
    L = [f"# 研究循环第 4 轮：日元急升时的闲置资金（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r04_yensurge.py 开头）", ""]
    for k in IDS:
        s1 = res["stage1"][k]
        L.append(f"- **{k} {name[k]}：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；"
                 f"S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）")
    L += ["", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | FXH | FXC |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['FXH'][e])}（{_f(res['stage1']['FXH']['d'][e], '{:+.3f}')}） | "
                 f"{cell(res['cand']['FXC'][e])}（{_f(res['stage1']['FXC']['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述：急升中的美国交易日占比与次数；核心换仓笔数（按 ETF）："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：急升中 {_f(d['surge_pct'], '{:.1f}')}%、{d['episodes']} 次；B0 {c['B0']} → FXH {c['FXH']}、FXC {c['FXC']}")
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
    W, k, surge, hedged, base = _G["W"], _G["k"], _G["surge"], _G["hedged"], _G["base"]
    try:
        ov = _overs(W, k, shifted(surge, seed), hedged)
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
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = LCM.load()
    surge, hedged = surge_series(W["inp"]), hedged_frame(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    ov = _overs(W, k, surge, hedged)
    cand = {e: LCM.run(W, e, **ov)["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "k": k, "surge": surge, "hedged": hedged, "base": base})
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
    L = [f"# 研究循环第 4 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 4 轮：FXH / FXC")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
