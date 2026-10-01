"""loop_r08_ndxreentry.py — 研究循环第 8 轮：S&P 熊市里纳指先回到牛就早一点拿回闲置资金 NDR（2026-10-01 登记；先提交后只运行一次；用掉 1 个做法 → 11 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题（照实写：是看了第 7 轮 NDA 的结果与事后描述之后设计的）：
  第 7 轮 NDA「S&P 熊且纳指也熊才转现金」第一关不过；事后描述把它拆成两半 ——「晚走」（S&P 先翻熊、纳指还撑着就继续拿）在 2008-01、2015-08〜2016-01、
  2020-03 大亏；「早回来」（S&P 熊市里纳指已经翻过熊、又先回到牛）在 2009、2020-04〜06、2023 帮忙。这一轮只要「早回来」那一半：
  离场完全照 B0（S&P 翻熊就转现金），只在同一段 S&P 熊市里纳指**已经翻过熊、之后又回到牛**时提前拿回 1545。
  先验的理由：闲置资金拿的是纳指，回来的时点看它自己的趋势（以前的诊断「V 形反弹里回到核心太晚」）；以前更快回补的 T11 / T14 用的是价格形态，
  在多段下跌的熊市里被套 —— 这里要纳指自己的检测器先翻过熊再翻回牛（250 日线 ±3%、连续 5 天），熊市反弹很少够得着。
  因为是看了 NDA 的逐年拆解之后挑的，第一关大概率会过（下面「事前预期」照实写）；真正的检验是第二关（随机放在 S&P 熊的日子里）与
  下面另报的**没看过的年代 1987〜2000**（只有核心、只描述、不参与判定）。
做法（参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  NDR 纳指熊 = 现行牛熊检测器（qbreak/bullbear，= 美股牛熊分界同一个；equity_idle_study.t0_bear）用在 ^NDX（美元）上。
      一段 S&P 熊市（美股牛熊分界连续是熊的日子）里：纳指在这段里（含当天）出现过熊、而当天是牛 → 「早回来」，闲置资金照拿 1545；
      纳指在这段里再翻熊 → 照 B0 现金；S&P 回到牛 → 照 B0。闲置资金 1545 的熊 = S&P 熊 且 不是「早回来」。
      引擎：1545 的 core_index 指向新键 "US_NR"（split、权重 1，与 B0 相同）；美国 d 日收盘决定 d+1 开盘成交（与 B0 同一个时点）。
      接线：纳指永远是熊时（永远没有「早回来」）必须与 B0 完全相同。
第一关：research_loop.stage1（trade = None、lenses = None）。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2 NDR`）：「改动」= 早回来的那些日子。把 2000-01-03〜2026-09-30 里 S&P 熊的
  美国交易日按顺序接成一串，「早回来」标记在这一串上整体循环平移 k 天（k ∈ [250, N − 250]，N = 那一串的天数；种子 s = 0〜399：
  numpy.random.default_rng([20261008, s])）—— 天数与每段长短不变、只落在 S&P 熊的日子里；统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述（不参与判定）：各年代「早回来」的天数与段数；核心换仓笔数；**1987-01〜2000-12 只有核心的长历史**（日元计纳指 1545 合成，
  equity_idle_study.long_history 同一做法：FRED 汇率、每次换仓 0.1%），B0 的开关 vs NDR 的开关的年化 / 最大回撤 / Calmar —— 这个年代 NDR 没看过。
事前预期（照实写）：第一关约 70%（NDA 的事后拆解里早回来的几段 2009、2020-04〜06、2023 都是正的）；第二关约 30%；「更好候选」约 20%；
  即使两关都过，也是看了结果之后设计的，要靠没看过的年代与以后的前向记录确认（这种事件几年才一次）。
运行：python scripts/loop_r08_ndxreentry.py（第一关）；python scripts/loop_r08_ndxreentry.py --stage2 NDR [--workers 3]（第二关）。
输出 var/out/loop_r08_ndxreentry.md / .json（第二关另写 loop_r08_ndxreentry_stage2_NDR.md / .json）。非投资建议。
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

ROUND = 8
IDS = ("NDR",)
NR_KEY = "US_NR"
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261008
OLD = ("1987-01-01", "2000-12-31")
OUT = "loop_r08_ndxreentry"


# ───────────────────────── 状态（纯函数，tests/test_loop_r08.py） ─────────────────────────
def on_union(a: pd.Series, b: pd.Series) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """两个布尔序列在日期并集上各自向后填（之前没有值 = False）。"""
    idx = a.index.union(b.index)
    aa = a.astype(float).reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5
    bb = b.astype(float).reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5
    return aa, bb, idx


def reentry(spx_bear: pd.Series, ndx_bear: pd.Series) -> pd.Series:
    """早回来：S&P 熊的这一段里（含当天）纳指出现过熊，而当天纳指是牛。"""
    s, n, idx = on_union(spx_bear, ndx_bear)
    out = np.zeros(len(idx), bool)
    seen = False
    for i in range(len(idx)):
        if not s[i]:
            seen = False
            continue
        seen = seen or bool(n[i])
        out[i] = seen and not n[i]
    return pd.Series(out, index=idx)


def nr_key(spx_bear: pd.Series, ndx_bear: pd.Series) -> pd.Series:
    """1545 的熊 = S&P 熊 且 不是早回来。"""
    s, _, idx = on_union(spx_bear, ndx_bear)
    return pd.Series(s & ~reentry(spx_bear, ndx_bear).to_numpy(bool), index=idx)


def ndr_over(key: pd.Series) -> dict:
    return {"cfg_over": {"core": {"1545.T": 1.0}, "core_index": {"1545.T": NR_KEY}, "core_mode": "split"},
            "extra_bear": {NR_KEY: key}}


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def placebo_key(spx_bear: pd.Series, ndx_bear: pd.Series, seed: int,
                a: str = SHIFT_FROM, b: str = LCM.J_END) -> pd.Series:
    """第二关的随机改动：S&P 熊的日子接成一串，把「早回来」标记在这一串上循环平移；返回 1545 的键。窗口外照真实的。"""
    s, _, idx = on_union(spx_bear, ndx_bear)
    re = reentry(spx_bear, ndx_bear).to_numpy(bool)
    key = s & ~re
    inw = (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b))
    pos = np.flatnonzero(s & inw)
    rolled = np.roll(re[pos], shift_k(seed, len(pos)))
    key = key.copy()
    key[pos] = ~rolled
    return pd.Series(key, index=idx)


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
def ndx_bear(inp: dict) -> pd.Series:
    import equity_idle_study as EI
    return EI.t0_bear(inp["ndx"])


def old_core(inp: dict, spx: pd.Series, ndx: pd.Series) -> dict:
    """只描述：1987〜2000 只有核心（日元计纳指，long_history 同一做法），B0 的开关 vs NDR 的开关。"""
    import equity_idle_study as EI
    dex = inp["dexjp"].dropna()
    s = EI.grow(EI.ndx_tr(inp), -EI.FEE["1545.T"])
    px = (s * dex.reindex(s.index.union(dex.index)).ffill().reindex(s.index)).dropna()
    px = px[px.index <= pd.Timestamp(OLD[1])]
    return {"B0": EI.curve_stats(EI.core_only(px, spx, OLD[0])), "NDR": EI.curve_stats(EI.core_only(px, nr_key(spx, ndx), OLD[0])),
            "segments": segments(reentry(spx, ndx), *OLD)}


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


def describe(W: dict, e: str, re: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    w = re[(re.index >= pd.Timestamp(a)) & ((re.index < pd.Timestamp(b)) if b else True)]
    return {"days": int(w.sum()), "episodes": episodes(w)}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r08_ndxreentry.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    spx, ndx = W["bear"]["US"], ndx_bear(W["inp"])
    re = reentry(spx, ndx)
    ov = ndr_over(nr_key(spx, ndx))
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, desc = {}, {"NDR": {}}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": core_trades(e, W)}
        base[e] = _acct(rb)
        rc = LCM.run(W, e, **ov)
        ctr[e]["NDR"] = core_trades(e, W)
        cand["NDR"][e] = _acct(rc)
        desc[e] = describe(W, e, re)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"NDR": RL.stage1(cand["NDR"], base)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "core_trades": ctr, "describe": desc, "segments": segments(re, "2001-01-01", LCM.J_END),
           "old": old_core(W["inp"], spx, ndx), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["NDR"]
    L = [f"# 研究循环第 8 轮：S&P 熊市里纳指先回到牛就早一点拿回闲置资金（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r08_ndxreentry.py 开头）", "",
         f"- **NDR 离场照 B0，S&P 熊市里纳指翻过熊又回到牛 → 提前拿回 1545：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）",
         "", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | NDR（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['NDR'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：早回来 {d['days']} 天、{d['episodes']} 段；核心换仓 B0 {c['B0']} → NDR {c['NDR']}")
    L.append("- 早回来的段（2001〜2026）：" + "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in res["segments"]))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心、日元计纳指）：B0 的开关 {oc(o['B0'])} → NDR {oc(o['NDR'])}；"
             "早回来的段：" + ("、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o["segments"]) or "没有"))
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
    W, spx, ndx, base = _G["W"], _G["spx"], _G["ndx"], _G["base"]
    try:
        ov = ndr_over(placebo_key(spx, ndx, seed))
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
    spx, ndx = W["bear"]["US"], ndx_bear(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = {e: LCM.run(W, e, **ndr_over(nr_key(spx, ndx)))["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "spx": spx, "ndx": ndx, "base": base})
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
    L = [f"# 研究循环第 8 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 8 轮：NDR")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
