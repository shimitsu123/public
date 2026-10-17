"""loop_r12_trendgate.py — 研究循环第 12 轮：「日経在来回震荡时不开新仓」ERG（研究路线图 R7 的买点一侧；2026-10-01 登记；先提交后只运行一次；
用掉 1 个做法 → 15 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题：研究路线图 RESEARCH_PLAN.md 的 R7「行情类型切换（趋势 / 盘整）」状态还是「未开始」；第 1〜11 轮里 9 个做法在核心 / 闲置资金一侧，
  选股以外的个股层只试过 UBG（美股熊时不开新仓）与 SEX（美股熊时卖日本股）。突破买点要靠之后的单边行情，来回震荡时突破多是假突破；
  以前只在离场一侧探索过行情类型（regime_exit_explore：日経 ER60 高的三分之一里快的离场更差，只用 2017〜2026、不登记），
  「市场在来回震荡就不开新仓」没做过。
做法（参数事先写定 → S6 不适用；改变个股交易 → S5 适用）：
  ERG 日経225 收盘的效率比 ER60 = |C_d − C_{d−60}| ÷ 最近 60 个涨跌的绝对值之和（Kaufman efficiency ratio；1 = 单边、0 = 来回）；
      门槛 = 到 d 为止 1250 个交易日（约 5 年，含 d）ER60 的 1/3 分位（只用过去与当天）；ER60_d < 门槛 =「震荡中」
      → 日本个股的新仓倍数 ×0（成交日 = 下一个交易日；与 B0 的判断层倍数相乘）；闲置资金照旧。接线：倍数全 1 时必须与 B0 完全相同。
  S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）在 B0 会买的信号（W2 + C，C 用 E / J 那一折的规则）里，
      震荡日的信号去掉之后，保留的逐笔胜率差、每笔差都要 ≥ 0。
第一关：research_loop.stage1（trade = W / Jx 的差，lenses = None）。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2 ERG`）：把「震荡中」序列（日本交易日 2000-01-04〜2026-09-30）整体循环平移 k 天
  （k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20261012, s])）—— 同样多、同样形状；统计量 = 三个年代 Calmar 差合计，
  要严格大于 400 次的最大值。
只描述：各年代震荡日占比与段数、账户里的个股笔数 B0 → ERG、W / Jx 被挡信号的胜率 / 每笔。
登记前只看过（照实写）：规模检查（没看收益）—— 震荡日占交易日 Z 35.9% / E 33.4% / J 35.4%；W2 + C 买点落在震荡日 Z 19 / 89、E 40 / 116、
  J 51 / 127、W 191 / 438、Jx 302 / 792。
事前预期（照实写）：第一关约 20%（挡掉 1/5〜2/5 的买点 → 闲置资金更多拿纳指：J 多半更好；Z 的个股层最强、E 的日元计纳指弱 → 年代依赖的风险）；
  第二关约 15%；「更好候选」约 3%。
运行：python scripts/loop_r12_trendgate.py（第一关）；python scripts/loop_r12_trendgate.py --stage2 ERG [--workers 3]（第二关）。
输出 var/out/loop_r12_trendgate.md / .json（第二关另写 loop_r12_trendgate_stage2_ERG.md / .json）。非投资建议。
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

ROUND = 12
IDS = ("ERG",)
ER_N, Q_WIN, Q = 60, 1250, 1 / 3
SHIFT_FROM, SHIFT_GAP = "2000-01-04", 250
SEED0 = 20261012
OUT = "loop_r12_trendgate"


# ───────────────────────── 状态（纯函数，tests/test_loop_r12.py） ─────────────────────────
def efficiency_ratio(close: pd.Series, n: int = ER_N) -> pd.Series:
    """|C_d − C_{d−n}| ÷ 最近 n 个涨跌的绝对值之和；前 n 天与分母为 0 → NaN。"""
    c = close.dropna().sort_index().astype(float)
    den = c.diff().abs().rolling(n, min_periods=n).sum()
    return (c - c.shift(n)).abs() / den.where(den > 0)


def chop_state(close: pd.Series, n: int = ER_N, win: int = Q_WIN, q: float = Q) -> pd.Series:
    """震荡中：ER_n < 到当天为止 win 天 ER_n 的 q 分位（不够 win 天 → 不算震荡）。"""
    er = efficiency_ratio(close, n)
    thr = er.rolling(win, min_periods=win).quantile(q)
    return ((er < thr) & thr.notna()).astype(bool)


def gate_factor(chop: pd.Series, days) -> pd.Series:
    """日本信号日 d：那天（向后填）震荡中 → 0，否则 1（成交日的倍数由 LCM.fill_scale 移到下一个交易日）。"""
    days = pd.DatetimeIndex(days)
    c = chop.astype(float).reindex(days.union(chop.index)).ffill().reindex(days).fillna(0.0) > 0.5
    return pd.Series(np.where(c, 0.0, 1.0), index=days)


def chop_at(chop: pd.Series, dates) -> np.ndarray:
    """每个日期（可以重复：同一天几个信号）那天（向后填）是不是震荡中。"""
    d = pd.DatetimeIndex(pd.to_datetime(dates))
    u = d.unique()
    c = chop.astype(float).reindex(u.union(chop.index)).ffill().reindex(u).fillna(0.0) > 0.5
    return c.reindex(d).to_numpy(bool)


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
def nikkei_close(inp: dict) -> pd.Series:
    n = inp["n225"]
    return (n["Close"] if isinstance(n, pd.DataFrame) else n).dropna().sort_index()


def chop_series(inp: dict) -> pd.Series:
    return chop_state(nikkei_close(inp))


def em_mult(W: dict, e: str, chop: pd.Series) -> pd.Series:
    days = W["ctx"][e]["days"]
    return LCM.fill_scale(gate_factor(chop, days), days)


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r12_trendgate.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def other_stocks(W: dict, chop: pd.Series) -> dict:
    """S5：W / Jx 里 B0 会买的信号（W2 + C；C 用 E / J 那一折）去掉震荡日的之后，保留 vs 全部。"""
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in LCM.ERAS if x != e]) for e in LCM.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        net = X["net"].to_numpy(float)[kc]
        keep = ~chop_at(chop, X["date"].to_numpy()[kc])
        dl = CA.delta(net, keep)
        gone = net[~keep]
        out[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"],
                  "gone_n": int(len(gone)), "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                  "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


def describe(W: dict, e: str, chop: pd.Series) -> dict:
    ctx = W["ctx"][e]
    a, b = ctx["windows"][e]
    g = pd.DatetimeIndex(ctx["days"])
    g = g[(g >= pd.Timestamp(a)) & ((g < pd.Timestamp(b)) if b else True)]
    if not len(g):
        return {"chop_pct": None, "episodes": 0}
    c = pd.Series(chop_at(chop, g), index=g)
    return {"chop_pct": round(float(c.mean() * 100), 1), "episodes": episodes(c)}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    chop = chop_series(W["inp"])
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, trades, desc = {}, {"ERG": {}}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        rc = LCM.run(W, e, em_mult=em_mult(W, e, chop))
        base[e], cand["ERG"][e] = _acct(rb), _acct(rc)
        trades[e] = {"B0": rb["n"], "ERG": rc["n"]}
        desc[e] = describe(W, e, chop)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, chop)
    s1 = {"ERG": RL.stage1(cand["ERG"], base, trade=os_)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "other_stocks": os_, "stock_trades": trades, "describe": desc, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["ERG"]
    L = [f"# 研究循环第 12 轮：日経在来回震荡时不开新仓（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r12_trendgate.py 开头）", "",
         f"- **ERG 日経 ER60 < 过去 5 年 1/3 分位 → 日本个股不开新仓：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5：{yn(s1['S5'])}；S6 不适用）",
         "", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | ERG（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['ERG'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（S5 以外不参与判定）："]
    for e in LCM.ERAS:
        d, t = res["describe"][e], res["stock_trades"][e]
        L.append(f"- {e}：震荡日占日本交易日 {_f(d['chop_pct'], '{:.1f}')}%、{d['episodes']} 段；账户里的个股笔数 {t['B0']} → {t['ERG']}")
    for s, x in res["other_stocks"].items():
        L.append(f"- S5 别的股票 {s}：B0 会买 {x['n']} 笔，挡掉 {x['gone_n']} 笔（胜率 {_f(x['gone_win'], '{:.1f}')}%、每笔 {_f(x['gone_mean'], '{:+.2f}')}%）；"
                 f"保留 − 全部 胜率 {_f(x['dwin'], '{:+.1f}')} pp、每笔 {_f(x['dmean'], '{:+.2f}')} pp")
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
    W, chop, base = _G["W"], _G["chop"], _G["base"]
    try:
        sh = shifted(chop, seed)
        tot = 0.0
        for e in LCM.ERAS:
            c = LCM.run(W, e, em_mult=em_mult(W, e, sh))["calmar"]
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
    chop = chop_series(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = {e: LCM.run(W, e, em_mult=em_mult(W, e, chop))["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "chop": chop, "base": base})
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
    L = [f"# 研究循环第 12 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 12 轮：ERG")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
