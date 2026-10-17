"""loop_r06_bearcash.py — 研究循环第 6 轮：美股熊市时闲置资金的币种 BXU（2026-10-01 登记；先提交后只运行一次；用掉 1 个做法 → 9 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这个题（同一批数据上没做过的问题；选股以外的层）：
  B0 在美股熊市里把闲置资金放成**日元现金**（利息约 0）。以前做过的相关题都不是这一个：
  ① R10 refuge_study（1fd9ec8）：熊市换黄金 / 美国长债（不看趋势）→ 2008 年日元急升、按日元计反而亏，没通过；
  ② idle_cash_study 的 K3（2026-09-29）：133A 美元趋势当**全部**闲置资金（牛市也拿美元、不拿股票）→ 少赚很多（年化 E −4.5、J −11.1 pp）；
     那次的另报照实看过：K3 2017〜2021 每年 −0.5〜−3.9%、2022 +22.1%（美元日元的大行情）。
  这里只改「美股熊市那一段」：牛市照旧纳指 1545（= B0），熊市里**美元在上升趋势**才拿美元短期国债 ETF 133A，否则照旧日元现金。
  熊市常伴着日元急升（避险），所以必须有趋势开关：凭对历史的一般知识（例：2008-09〜10 美元日元 108 → 98）选了反应快的
  **日线 200 日均线**（最常用的一条，不调参数），没有用 K3 的「月末收盘 vs 10 个月均线」（月末才判定，熊市里的急升躲不开）。这是设计选择，照实写。
做法（参数事先写定 → S6 不适用；不改个股买卖 → S5 不适用）：
  BXU 美元上升趋势 = FRED DEXJPUS（纽约中午）d 日的值 > 截至 d 日的 200 个观测日简单平均（不满 200 个 → 不算上升）；
      美国 d 日的值决定 d+1 开盘成交（与引擎的美股牛熊分界同一个时点）。
      美股牛熊分界 = 熊 且 美元上升趋势 → 闲置资金拿 133A；熊 且 不是上升趋势 → 现金；牛 → 1545（= B0）。
      133A 合成价 = 美国 3 个月国库券（FRED DTB3）逐日计息（前一个观测日的利率 × 天数 / 360，扣年 0.0975% 信託報酬；
      idle_cash_study.accrual 同一做法）× USD/JPY（与 1545 合成价同一个汇率序列），东证交易日 d 用前一个美国值；
      价格水平按 2026-08-31 真实收盘 ¥1,073.75（sim_changes 2026-09-29 记的值）；滑点 / 一手按 qbreak/fees.py 的 133A（0.05%、1 口）。
      引擎：core = 1545 + 133A，core_mode = "follow"（只拿其中一只）；1545 的键 = "US"（B0 原样），133A 的键 = "US_BX"
      （True = 不拿 = 不是「熊且美元上升」）。接线：美元上升永远不成立时必须与 B0 完全相同。
第一关：research_loop.stage1（trade = None、lenses = None）。
第二关（第一关全过才做；另行登记（提交）后只运行一次，`--stage2 BXU`）：把「美元上升趋势」序列（DEXJPUS 的日子，2000-01-03〜2026-09-30）
  整体循环平移 k 天（k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20261006, s])），再与真实的美股熊取「且」——
  同样多（上升趋势的天数不变）、同样形状（每段长短不变），只是与真实的汇率脱钩；统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述：各年代美股熊的交易日占比、熊里美元上升的占比、「熊且上升」的段数；核心换仓笔数（按 ETF）。
事前预期（照实写）：第一关约 35%（Z 的 2001 年、J 的 2022 年拿到美元升值；E 里 2015-08〜2016-01、2018-12 的熊里美元在顶部，
  趋势翻下来之前要亏几个百分点，E 可能低于 −0.02 或回撤加深）；第二关约 12%；「更好候选」约 4%。
运行：python scripts/loop_r06_bearcash.py（第一关）；python scripts/loop_r06_bearcash.py --stage2 BXU [--workers 3]（第二关）。
输出 var/out/loop_r06_bearcash.md / .json（第二关另写 loop_r06_bearcash_stage2_BXU.md / .json）。非投资建议。
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

ROUND = 6
IDS = ("BXU",)
MA_N = 200
T133, T133_FEE, T133_REF, REF_DATE = "133A.T", 0.0975, 1073.75, "2026-08-31"
BX_KEY = "US_BX"
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261006
OUT = "loop_r06_bearcash"


# ───────────────────────── 状态（纯函数，tests/test_loop_r06.py） ─────────────────────────
def usd_up(fx: pd.Series, n: int = MA_N) -> pd.Series:
    """美元上升趋势：d 日的值 > 截至 d 日（含）的 n 个观测日简单平均；不满 n 个 → False。按 fx 的日期返回。"""
    s = fx.dropna().sort_index()
    sma = s.rolling(n, min_periods=n).mean()
    return pd.Series((s > sma).to_numpy(bool), index=s.index)


def and_series(a: pd.Series, b: pd.Series) -> pd.Series:
    """两个布尔序列在日期并集上各自向后填（之前没有值 = False）再取「且」。"""
    idx = a.index.union(b.index)
    aa = a.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5
    bb = b.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5
    return pd.Series((aa & bb).to_numpy(bool), index=idx)


def bx_bear(us_bear: pd.Series, up: pd.Series) -> pd.Series:
    """133A 的「熊」键：True = 不拿 = 不是（美股熊 且 美元上升）。"""
    on = and_series(us_bear, up)
    return pd.Series(~on.to_numpy(bool), index=on.index)


def bxu_over(W: dict, us_bear: pd.Series, up: pd.Series, f133: pd.DataFrame) -> dict:
    xc = dict(W["kw"]["Z"]["extra_core"])
    xc[T133] = f133
    return {"cfg_over": {"core": {"1545.T": 1.0, T133: 1.0}, "core_index": {"1545.T": "US", T133: BX_KEY}, "core_mode": "follow"},
            "extra_core": xc, "extra_bear": {BX_KEY: bx_bear(us_bear, up)}}


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
def frame_133a(inp: dict) -> pd.DataFrame:
    """133A 的东证交易日 K 线（只有收盘）：DTB3 逐日计息（扣费）× USD/JPY，d 日用前一个美国值；按 REF_DATE 定价格水平。"""
    import equity_idle_study as EI
    import idle_cash_study as ICS
    r = inp["dtb3"].dropna()
    acc = ICS.accrual(r[r.index >= pd.Timestamp(EI.START)], T133_FEE)
    days = inp["n225"].index[inp["n225"].index >= pd.Timestamp(EI.START)]
    c = EI.on_jp(acc, inp["fx"], days)
    c = c * (T133_REF / float(c.asof(pd.Timestamp(REF_DATE))))
    return EI.frame_close(c)


def up_series(inp: dict) -> pd.Series:
    return usd_up(inp["dexjp"])


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


def window(s: pd.Series, W: dict, e: str) -> pd.Series:
    a, b = W["ctx"][e]["windows"][e]
    return s[(s.index >= pd.Timestamp(a)) & ((s.index < pd.Timestamp(b)) if b else True)]


def describe(W: dict, e: str, us_bear: pd.Series, up: pd.Series) -> dict:
    """美股熊的美国交易日占比、熊里美元上升的占比、「熊且上升」的段数（都在这个年代的窗口里）。"""
    b = window(us_bear.astype(bool), W, e)
    u = up.astype(float).reindex(b.index.union(up.index)).ffill().fillna(0.0).reindex(b.index) > 0.5
    on = b & u
    return {"bear_pct": round(float(b.mean() * 100), 1) if len(b) else None,
            "up_in_bear_pct": round(float(on.sum() / b.sum() * 100), 1) if int(b.sum()) else None,
            "episodes": episodes(on)}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r06_bearcash.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    up = up_series(W["inp"])
    f133 = frame_133a(W["inp"])
    bus = W["bear"]["US"]
    ov = bxu_over(W, bus, up, f133)
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, ctr, desc = {}, {"BXU": {}}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": core_trades(e, W)}
        base[e] = _acct(rb)
        rc = LCM.run(W, e, **ov)
        ctr[e]["BXU"] = core_trades(e, W)
        cand["BXU"][e] = _acct(rc)
        desc[e] = describe(W, e, bus, up)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = {"BXU": RL.stage1(cand["BXU"], base)}
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
    s1 = res["stage1"]["BXU"]
    L = [f"# 研究循环第 6 轮：美股熊市时闲置资金的币种（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r06_bearcash.py 开头）", "",
         f"- **BXU 美股熊市里美元在 200 日线之上 → 闲置资金拿 133A 美元短期国债：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用）",
         "", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | BXU（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['BXU'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述：美股熊的美国交易日占比、熊里美元上升的占比与段数；核心换仓笔数（按 ETF）："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：熊 {_f(d['bear_pct'], '{:.1f}')}%、其中美元上升 {_f(d['up_in_bear_pct'], '{:.1f}')}%、{d['episodes']} 段；"
                 f"核心换仓 B0 {c['B0']} → BXU {c['BXU']}")
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
    W, up, f133, base = _G["W"], _G["up"], _G["f133"], _G["base"]
    try:
        ov = bxu_over(W, W["bear"]["US"], shifted(up, seed), f133)
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
    up, f133 = up_series(W["inp"]), frame_133a(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    ov = bxu_over(W, W["bear"]["US"], up, f133)
    cand = {e: LCM.run(W, e, **ov)["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "up": up, "f133": f133, "base": base})
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
    L = [f"# 研究循环第 6 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 6 轮：BXU")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
