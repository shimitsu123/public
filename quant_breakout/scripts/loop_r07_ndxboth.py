"""loop_r07_ndxboth.py — 研究循环第 7 轮：纳指自己还是牛就不转现金 NDA（2026-10-01 登记；先提交后只运行一次；用掉 1 个做法 → 10 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题：
  B0 的拆解（只看基准，scratch）：账户的起落几乎都来自闲置资金纳指 1545；以前的诊断写过「V 形反弹里 T0 回到核心太晚」（stack_study）。
  闲置资金拿的是纳指，转现金却只看 S&P 500 自己的牛熊。第 2 轮 HBOR 试过「S&P 熊 **或** 日元计纳指熊」（多转现金 → 来回换，大幅更差）；
  反过来「S&P 熊 **且** 纳指（美元）也熊才转现金」没做过 —— 纳指先回到牛市的复苏（纳指带头）里早一点拿回来，S&P 先翻熊而纳指还撑着时晚一点走。
  以前更快回补的规则（T11 / T14：自低点 +20%、站上 50 日线）都用价格形态、在多段下跌的熊市里被套；这里用的是同一个现行检测器在核心资产自己身上的判断。
  照实写（登记前看过的）：B0 的逐年拆解；本轮先设计过 GBH（21 个外国市场多数翻熊、美股还是牛 → 纳指减半），只看了状态序列
  （美股牛且全球转弱 Z 1.5% / E 2.1% / J 5.1%，多在美股先回升的时候：2003-05、2012-01、2016-06、2020-06〜08、2023-11）就放弃 ——
  没登记、没跑任何结果、不算做法；以及本轮的状态序列（下面「只描述」那几项：S&P 熊而纳指牛的段）。
做法（参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  NDA 纳指熊 = 现行牛熊检测器（qbreak/bullbear 的检测器与参数，= 美股牛熊分界同一个；equity_idle_study.t0_bear）用在纳斯达克 100 指数
      （yfinance ^NDX 收盘，美元）上；闲置资金 1545 的熊 = 美股牛熊分界（S&P 500）熊 **且** 纳指熊（两边各自按自己的日子向后填）；
      其余不变。引擎：1545 的 core_index 指向新键 "US_ND"（split 模式、权重 1，与 B0 相同）。美国 d 日收盘决定 d+1 开盘成交（与 B0 同一个时点）。
      接线：纳指永远是熊时（键 = S&P 熊）必须与 B0 完全相同。
第一关：research_loop.stage1（trade = None、lenses = None）。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2 NDA`）：「改动」= S&P 熊的日子里因为纳指还是牛而照拿 1545 的那些日子。
  把 2000-01-03〜2026-09-30 里 S&P 熊的美国交易日按顺序接成一串，「照拿」标记在这一串上整体循环平移 k 天
  （k ∈ [250, N − 250]，N = 那一串的天数；种子 s = 0〜399：numpy.random.default_rng([20261007, s])）—— 同样多（照拿的天数不变）、
  同样形状（每段长短不变）、只在 S&P 熊的日子里，但与纳指真实的牛熊脱钩；统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述：各年代 S&P 熊的日子里纳指还是牛（= 照拿）的比例与段数；核心换仓笔数。
事前预期（照实写）：第一关约 35%（E 的 2009-06〜07、2010-07〜10，J 的 2020-04〜06、2023-03〜04 早回来；风险：2020-03-13〜19、
  2008-01 纳指还没翻熊的那几天，2015-08〜2016-01 纳指来回、日元升值）；第二关约 30%；「更好候选」约 10%。
运行：python scripts/loop_r07_ndxboth.py（第一关）；python scripts/loop_r07_ndxboth.py --stage2 NDA [--workers 3]（第二关）。
输出 var/out/loop_r07_ndxboth.md / .json（第二关另写 loop_r07_ndxboth_stage2_NDA.md / .json）。非投资建议。
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

ROUND = 7
IDS = ("NDA",)
ND_KEY = "US_ND"
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261007
OUT = "loop_r07_ndxboth"


# ───────────────────────── 状态（纯函数，tests/test_loop_r07.py） ─────────────────────────
def on_union(a: pd.Series, b: pd.Series) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """两个布尔序列在日期并集上各自向后填（之前没有值 = False）。"""
    idx = a.index.union(b.index)
    aa = a.astype(float).reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5
    bb = b.astype(float).reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5
    return aa, bb, idx


def both_bear(spx_bear: pd.Series, ndx_bear: pd.Series) -> pd.Series:
    """1545 的熊 = S&P 熊 且 纳指熊。"""
    s, n, idx = on_union(spx_bear, ndx_bear)
    return pd.Series(s & n, index=idx)


def hold_days(spx_bear: pd.Series, ndx_bear: pd.Series) -> pd.Series:
    """「照拿」= S&P 熊 而 纳指牛。"""
    s, n, idx = on_union(spx_bear, ndx_bear)
    return pd.Series(s & ~n, index=idx)


def nda_over(key: pd.Series) -> dict:
    return {"cfg_over": {"core": {"1545.T": 1.0}, "core_index": {"1545.T": ND_KEY}, "core_mode": "split"},
            "extra_bear": {ND_KEY: key}}


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def placebo_key(spx_bear: pd.Series, ndx_bear: pd.Series, seed: int,
                a: str = SHIFT_FROM, b: str = LCM.J_END) -> pd.Series:
    """第二关的随机改动：S&P 熊的日子接成一串，把「照拿」标记在这一串上循环平移；返回 1545 的键（熊 且 没被照拿）。
    窗口外的日子照真实的「两个都熊」。"""
    s, n, idx = on_union(spx_bear, ndx_bear)
    key = s & n
    inw = (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b))
    pos = np.flatnonzero(s & inw)
    hold = (~n)[pos]
    rolled = np.roll(hold, shift_k(seed, len(pos)))
    key = key.copy()
    key[pos] = ~rolled
    return pd.Series(key, index=idx)


def episodes(s: pd.Series) -> int:
    v = s.to_numpy(bool)
    return int(((v[1:]) & (~v[:-1])).sum() + (1 if len(v) and v[0] else 0))


# ───────────────────────── 数据 ─────────────────────────
def ndx_bear(inp: dict) -> pd.Series:
    import equity_idle_study as EI
    return EI.t0_bear(inp["ndx"])


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


def describe(W: dict, e: str, spx: pd.Series, ndx: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    s, n, idx = on_union(spx, ndx)
    m = (idx >= pd.Timestamp(a)) & ((idx < pd.Timestamp(b)) if b else True)
    hold = pd.Series(s[m] & ~n[m], index=idx[m])
    nb = int(s[m].sum())
    return {"spx_bear_pct": round(float(s[m].mean() * 100), 1) if m.any() else None,
            "hold_in_bear_pct": round(float(hold.sum() / nb * 100), 1) if nb else None, "episodes": episodes(hold)}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r07_ndxboth.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    spx, ndx = W["bear"]["US"], ndx_bear(W["inp"])
    ov = nda_over(both_bear(spx, ndx))
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, desc = {}, {"NDA": {}}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": core_trades(e, W)}
        base[e] = _acct(rb)
        rc = LCM.run(W, e, **ov)
        ctr[e]["NDA"] = core_trades(e, W)
        cand["NDA"][e] = _acct(rc)
        desc[e] = describe(W, e, spx, ndx)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"NDA": RL.stage1(cand["NDA"], base)}
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
    s1 = res["stage1"]["NDA"]
    L = [f"# 研究循环第 7 轮：纳指自己还是牛就不转现金（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r07_ndxboth.py 开头）", "",
         f"- **NDA 闲置资金 1545 的熊 = S&P 熊 且 纳指（美元）熊：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）",
         "", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | NDA（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['NDA'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述：S&P 熊的美国交易日占比、其中纳指还是牛（照拿）的比例与段数；核心换仓笔数："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：S&P 熊 {_f(d['spx_bear_pct'], '{:.1f}')}%、其中照拿 {_f(d['hold_in_bear_pct'], '{:.1f}')}%、{d['episodes']} 段；"
                 f"核心换仓 B0 {c['B0']} → NDA {c['NDA']}")
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
        ov = nda_over(placebo_key(spx, ndx, seed))
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
    cand = {e: LCM.run(W, e, **nda_over(both_bear(spx, ndx)))["calmar"] for e in LCM.ERAS}
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
    L = [f"# 研究循环第 7 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 7 轮：NDA")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
