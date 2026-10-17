"""loop_r05_ratediff.py — 研究循环第 5 轮：利差收窄时对冲闲置资金 RDH / 美股熊时日本个股清仓 SEX（2026-10-01 登记；先提交后只运行一次；用掉 2 个做法 → 8 / 20）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。
为什么挑这两个（都是同一批数据上没做过的）：
  RDH 第 4 轮 FXH「日元急升（价格）之后对冲」第一关全过、第二关差一点（约第 98 百分位）；日元急升背后常见的基本面原因是美日利差快速收窄
    （2007〜08 联储降息、2010、2019〜20、2024 年下半年）。这里换成**利差**本身（不是价格）当信号 —— 不是 FXH 的参数变体：信号的来源与时点都不同
    （利差多半走在汇率前面或同时，FXH 是急升已经发生之后）。照实写：这一题是看到 FXH 的结果之后挑的，算在用掉的做法里。
    以前的利率研究（第 4174 行以前的八项）都是拿利率去择时日経 / 闲置资金的多空，没有拿利差去决定「对冲不对冲」。
  SEX 第 2 轮 UBG「美股熊时不开日本新仓」几乎不变（Z / E 那几段本来就没有新仓）；但美股翻熊时**已经拿着**的日本个股照样按自己的离场规则拿着，
    2008、2015〜16、2020、2022 这类下跌里与闲置资金同向亏。这里加上「美股熊的日子里，拿着的日本个股下一开盘卖掉」。
做法（各自独立判定；参数事先写定 → S6 不适用）：
  RDH 利差 s = 美国 2 年国债（FRED DGS2，取前一个美国交易日）− 日本 2 年国债（财务省，取前一个日本交易日），按美国交易日；
      63 个美国交易日（约 3 个月）的变化 ≤ −0.50 pp → 「利差收窄中」开始；变化回到 ≥ −0.25 pp → 结束（滞后带）。
      收窄中 → 闲置资金拿对冲版纳指 2845（第 4 轮同一个合成价与做法：loop_r04_yensurge.hedged_frame、fxh_over），否则 1545；美股熊市照旧现金。
      不改个股买卖 → S5 不适用。接线：收窄永远不发生时必须与 B0 完全相同。
  SEX 美股牛熊分界 = 熊的日子（同引擎时点：美国 d 日收盘）：① 日本个股不开新仓（= 第 2 轮 UBG）；② 拿着的日本个股在下一开盘卖出
      （引擎的「放量阴线」离场列 climax 在那些日子设为 True；best_params 的 exit_on_climax = True）。闲置资金照旧。
      改变个股交易 → S5 适用：W / Jx 里 B0 会买的信号，按「美股熊那天不买」去掉之后保留 vs 全部（与第 2 轮同一算法；只看买点那一半）。
      接线：熊永远不发生时必须与 B0 完全相同。
第一关：research_loop.stage1（RDH：trade = None；SEX：trade = W / Jx 的差）。
第二关（第一关全过的做法；另行登记（提交）后只运行一次，`--stage2 RDH|SEX`）：把那个做法新加的状态序列整体循环平移 400 次
  （RDH：「利差收窄中」；SEX：用来清仓 / 挡新仓的美股熊；闲置资金自己的牛熊不动），美国交易日 2000-01-03〜2026-09-30，k ∈ [250, N − 250]，
  种子 s = 0〜399：numpy.random.default_rng([20261005, s])；统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值。
只描述：各年代「利差收窄中」的交易日占比与次数；SEX 卖掉的个股笔数（离场原因 climax 的增加）；核心换仓笔数。
事前预期（照实写）：RDH 第一关约 20%（2007〜08、2010 先对冲；2016 年初、2024-08 的日元急升利差信号来得晚或没有）；
  SEX 第一关约 10%（美股熊的日子里拿着日本个股的时候不多，效果多半很小）；第二关各约 25%；「更好候选」RDH 约 5%、SEX 约 2%。
运行：python scripts/loop_r05_ratediff.py（第一关）；python scripts/loop_r05_ratediff.py --stage2 RDH [--workers 3]（第二关）。
输出 var/out/loop_r05_ratediff.md / .json（第二关另写 loop_r05_ratediff_stage2_<做法>.md / .json）。非投资建议。
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

ROUND = 5
IDS = ("RDH", "SEX")
DIFF_N, ON_THR, OFF_THR = 63, -0.50, -0.25
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261005
OUT = "loop_r05_ratediff"


# ───────────────────────── 状态（纯函数，tests/test_loop_r05.py） ─────────────────────────
def spread_us_days(us2: pd.Series, jp2: pd.Series) -> pd.Series:
    """美国交易日 d 的利差 = 美国 2 年（前一个美国交易日）− 日本 2 年（d 之前最后一个日本交易日的前一个值）。"""
    u = us2.dropna().sort_index()
    j = jp2.dropna().sort_index().shift(1).dropna()
    u_lag = u.shift(1)
    jj = j.reindex(u.index.union(j.index)).ffill().reindex(u.index)
    return (u_lag - jj).dropna()


def narrowing_state(s: pd.Series, n: int = DIFF_N, on: float = ON_THR, off: float = OFF_THR) -> pd.Series:
    """n 日变化 ≤ on 开始、≥ off 结束（滞后带）。"""
    d = (s - s.shift(n)).to_numpy(float)
    out = np.zeros(len(s), bool)
    cur = False
    for i, x in enumerate(d):
        if np.isfinite(x):
            if not cur and x <= on + 1e-12:
                cur = True
            elif cur and x >= off - 1e-12:
                cur = False
        out[i] = cur
    return pd.Series(out, index=s.index)


def climax_frames(fr: dict, bear: pd.Series) -> dict:
    """美股熊（向后填）的日子里，日本个股的 climax 列设为 True（下一开盘卖出）；核心 ETF（不在 fr 里）不动。"""
    import loop_r02_bearstate as B
    out = {}
    for t, df in fr.items():
        b = B.bear_at(bear, df.index)
        c = df["climax"].fillna(False).to_numpy(bool) if "climax" in df.columns else np.zeros(len(df), bool)
        out[t] = df.assign(climax=c | b)
    return out


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


# ───────────────────────── 数据与引擎参数 ─────────────────────────
def rdh_state() -> pd.Series:
    from qbreak import factors
    jgb = factors.jgb_curve()["2Y"]
    return narrowing_state(spread_us_days(factors.fred("DGS2"), jgb))


def run_cand(W: dict, e: str, k: str, state: pd.Series, hedged: pd.DataFrame | None) -> dict:
    import loop_r02_bearstate as B
    import loop_r04_yensurge as Y
    if k == "RDH":
        return LCM.run(W, e, **Y.fxh_over(W, W["bear"]["US"], state, hedged))
    days = W["ctx"][e]["days"]
    return LCM.run(W, e, fr=climax_frames(W["fr"][e], state), em_mult=LCM.fill_scale(B.gate_factor(state, days), days))


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def engine_counts(e: str, W: dict) -> dict:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    core: dict = {}
    for x in eng.st.core_trades:
        if x[0] >= a and (b is None or x[0] < b):
            core[x[1]] = core.get(x[1], 0) + 1
    climax = sum(1 for t in eng.st.trades if t.get("reason") == "climax" and a <= str(t.get("exit_date", "")) and (b is None or str(t.get("exit_date", "")) < b))
    return {"core": core, "climax_exits": int(climax)}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r05_ratediff.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py", "scripts/loop_r02_bearstate.py", "scripts/loop_r04_yensurge.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import loop_r02_bearstate as B
    import loop_r04_yensurge as Y
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    rd = rdh_state()
    hedged = Y.hedged_frame(W["inp"])
    bus = W["bear"]["US"]
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, cnt, desc = {}, {k: {} for k in IDS}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        cnt[e] = {"B0": engine_counts(e, W)}
        base[e] = _acct(rb)
        for k in IDS:
            rc = run_cand(W, e, k, rd if k == "RDH" else bus, hedged)
            cnt[e][k] = engine_counts(e, W)
            cand[k][e] = _acct(rc)
        a, b = W["ctx"][e]["windows"][e]
        s = rd[(rd.index >= pd.Timestamp(a)) & ((rd.index < pd.Timestamp(b)) if b else True)]
        desc[e] = {"rdh_pct": round(float(s.mean() * 100), 1) if len(s) else None, "rdh_episodes": episodes(s)}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = B.other_stocks(W, bus)
    s1 = {"RDH": RL.stage1(cand["RDH"], base), "SEX": RL.stage1(cand["SEX"], base, trade=os_)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "other_stocks": os_, "counts": cnt, "describe": desc, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    name = {"RDH": "美日 2 年利差 3 个月收窄 ≥ 0.50 pp 时闲置资金换对冲版纳指", "SEX": "美股熊的日子里日本个股清仓、不开新仓"}
    L = [f"# 研究循环第 5 轮：利差收窄时对冲 / 美股熊时日本个股清仓（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r05_ratediff.py 开头）", ""]
    for k in IDS:
        s1 = res["stage1"][k]
        L.append(f"- **{k} {name[k]}：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；"
                 f"S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5：{('过' if s1['S5'] else '不过') if s1['applies'] else '不适用'}；S6 不适用）")
    L += ["", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | RDH | SEX |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['RDH'][e])}（{_f(res['stage1']['RDH']['d'][e], '{:+.3f}')}） | "
                 f"{cell(res['cand']['SEX'][e])}（{_f(res['stage1']['SEX']['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["counts"][e]
        L.append(f"- {e}：利差收窄中 {_f(d['rdh_pct'], '{:.1f}')}%、{d['rdh_episodes']} 次；核心换仓 B0 {c['B0']['core']} → RDH {c['RDH']['core']}；"
                 f"climax 离场 B0 {c['B0']['climax_exits']} → SEX {c['SEX']['climax_exits']} 笔；个股笔数 {res['base'][e]['n']} → SEX {res['cand']['SEX'][e]['n']}")
    for s, x in res["other_stocks"].items():
        L.append(f"- SEX 别的股票 {s}（只看买点）：B0 会买 {x['n']} 笔，挡掉 {x['gone_n']} 笔（胜率 {_f(x['gone_win'], '{:.1f}')}%、每笔 {_f(x['gone_mean'], '{:+.2f}')}%）；"
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
    W, k, src, hedged, base = _G["W"], _G["k"], _G["src"], _G["hedged"], _G["base"]
    try:
        sh = shifted(src, seed)
        tot = 0.0
        for e in LCM.ERAS:
            c = run_cand(W, e, k, sh, hedged)["calmar"]
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
    src = rdh_state() if k == "RDH" else W["bear"]["US"]
    hedged = Y.hedged_frame(W["inp"])
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = {e: run_cand(W, e, k, src, hedged)["calmar"] for e in LCM.ERAS}
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "k": k, "src": src, "hedged": hedged, "base": base})
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
    L = [f"# 研究循环第 5 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 5 轮：RDH / SEX")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
