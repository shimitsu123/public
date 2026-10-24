"""loop_r09_crashbreak.py — 研究循环第 9 轮：美股急跌熔断 CPX（2026-10-01 登记；先提交后只运行一次；用掉 1 个做法 → 12 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题：
  B0 的拆解（只看基准）：J 的最大回撤 2020-02-21〜03-13（−29.0%）发生在美股牛熊分界翻熊之前 —— 现行检测器要「250 日线 −3%、连续 5 天」才翻，
  急跌（几天内 −10% 以上）时总是晚。以前「快一点离场」的 T7（跌破 250 日线且距高点 −10%、连续 2 天）/ T8（信用加速）在牛熊研究里没通过
  （误报多、来回换），第 1 轮 VT20（按波动率连续调仓）E 少赚。这里只处理「几天之内的急跌」：触发少、回来也快（站回 20 日线就回来），
  其余照 B0。照实写：设计时知道 2020-02〜03、2018-02、2025-04 有过这种急跌（一般知识），没算过这条规则的任何结果。
做法（参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  CPX 美股（S&P 500 ^GSPC 收盘，美元，与美股牛熊分界同一个序列）d 日收盘 ≤ 最近 10 个美国交易日（含 d）最高收盘 × 0.90 → 「急跌中」开始；
      之后 S&P 收盘 > 20 日简单平均 → 结束（同一天两个条件都看：开始优先）。急跌中 → 闲置资金 1545 转现金（不管牛熊分界是牛还是熊）；
      结束后照 B0（牛熊分界仍是熊就继续现金）。引擎：1545 的 core_index 指向新键 "US_CX" = 美股牛熊分界熊 或 急跌中（split、权重 1）。
      美国 d 日收盘决定 d+1 开盘成交（与 B0 同一个时点）。接线：急跌永远不发生时必须与 B0 完全相同。
第一关：research_loop.stage1（trade = None、lenses = None）。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2 CPX`）：把「急跌中」序列（美国交易日 2000-01-03〜2026-09-30）整体循环平移 k 天
  （k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20261009, s])）—— 同样多、同样形状、与真实的行情脱钩；
  统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述：各年代「急跌中」的日子数与段数（其中牛熊分界还是牛的）；核心换仓笔数。
事前预期（照实写）：第一关约 25%（J 的 2020-02〜03 少亏、2018-02 与 2025-04 卖在低点附近；E / Z 几乎没有急跌发生在牛熊分界还是牛的时候）；
  第二关约 10%（账户 Calmar 主要由每个年代最大的一次急跌决定，随机平移碰上 2020-03 的也会很好看）；「更好候选」约 3%。
运行：python scripts/loop_r09_crashbreak.py（第一关）；python scripts/loop_r09_crashbreak.py --stage2 CPX [--workers 3]（第二关）。
输出 var/out/loop_r09_crashbreak.md / .json（第二关另写 loop_r09_crashbreak_stage2_CPX.md / .json）。非投资建议。
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

ROUND = 9
IDS = ("CPX",)
HI_N, DROP, MA_N = 10, 0.10, 20
CX_KEY = "US_CX"
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261009
OUT = "loop_r09_crashbreak"


# ───────────────────────── 状态（纯函数，tests/test_loop_r09.py） ─────────────────────────
def crash_state(close: pd.Series, hi_n: int = HI_N, drop: float = DROP, ma_n: int = MA_N) -> pd.Series:
    """急跌中：收盘 ≤ 最近 hi_n 天（含当天）最高收盘 × (1 − drop) 时开始；收盘 > ma_n 日均线时结束（开始优先）。"""
    s = close.dropna().sort_index()
    hi = s.rolling(hi_n, min_periods=1).max()
    ma = s.rolling(ma_n, min_periods=ma_n).mean()
    on = np.zeros(len(s), bool)
    cur = False
    for i in range(len(s)):
        p, h, m = s.iloc[i], hi.iloc[i], ma.iloc[i]
        if p <= h * (1 - drop):
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


def cpx_over(us_bear: pd.Series, crash: pd.Series) -> dict:
    return {"cfg_over": {"core": {"1545.T": 1.0}, "core_index": {"1545.T": CX_KEY}, "core_mode": "split"},
            "extra_bear": {CX_KEY: or_series(us_bear, crash)}}


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


def segments(s: pd.Series, a: str, b: str) -> list[tuple[str, str, int]]:
    w = s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]
    v, ix, out, i = w.to_numpy(bool), w.index, [], 0
    while i < len(v):
        if v[i]:
            j = i
            while j + 1 < len(v) and v[j + 1]:
                j += 1
            out.append((str(ix[i].date()), str(ix[j].date()), j - i + 1))
            i = j + 1
        else:
            i += 1
    return out


# ───────────────────────── 数据 ─────────────────────────
def crash_series(inp: dict) -> pd.Series:
    return crash_state(inp["spx"]["Close"])


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


def describe(W: dict, e: str, crash: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    bus = W["bear"]["US"]
    w = crash[(crash.index >= pd.Timestamp(a)) & ((crash.index < pd.Timestamp(b)) if b else True)]
    bull = ~bus.astype(float).reindex(w.index.union(bus.index)).ffill().fillna(0.0).reindex(w.index).gt(0.5)
    extra = w & bull
    return {"days": int(w.sum()), "episodes": episodes(w), "in_bull_days": int(extra.sum()), "in_bull_episodes": episodes(extra)}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r09_crashbreak.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    crash = crash_series(W["inp"])
    ov = cpx_over(W["bear"]["US"], crash)
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, desc = {}, {"CPX": {}}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": core_trades(e, W)}
        base[e] = _acct(rb)
        rc = LCM.run(W, e, **ov)
        ctr[e]["CPX"] = core_trades(e, W)
        cand["CPX"][e] = _acct(rc)
        desc[e] = describe(W, e, crash)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"CPX": RL.stage1(cand["CPX"], base)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "core_trades": ctr, "describe": desc, "segments": segments(crash, "2001-01-01", LCM.J_END), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["CPX"]
    L = [f"# 研究循环第 9 轮：美股急跌熔断（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r09_crashbreak.py 开头）", "",
         f"- **CPX S&P 收盘比 10 日最高低 10% → 闲置资金转现金、站回 20 日线才回来：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）",
         "", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | CPX（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['CPX'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述：「急跌中」的日子与段数（其中牛熊分界还是牛的）；核心换仓笔数："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：急跌中 {d['days']} 天、{d['episodes']} 段（牛熊分界还是牛的 {d['in_bull_days']} 天、{d['in_bull_episodes']} 段）；"
                 f"核心换仓 B0 {c['B0']} → CPX {c['CPX']}")
    L.append("- 急跌中的段（2001〜2026）：" + "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in res["segments"]))
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
    W, crash, base = _G["W"], _G["crash"], _G["base"]
    try:
        ov = cpx_over(W["bear"]["US"], shifted(crash, seed))
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
    crash = crash_series(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = {e: LCM.run(W, e, **cpx_over(W["bear"]["US"], crash))["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "crash": crash, "base": base})
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
    L = [f"# 研究循环第 9 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 9 轮：CPX")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
