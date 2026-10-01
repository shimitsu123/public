"""loop_r02_bearstate.py — 研究循环第 2 轮：牛熊状态的两处用法（2026-10-01 登记；先提交后只运行一次；用掉 2 个做法）。

循环的规则：scripts/research_loop.py；基准 B0：scripts/loop_common.py。第 1 轮 VT20（按波动率调节闲置资金）第一关不过（年代依赖）。
为什么挑这两个（都是「同一批数据上没做过」的）：
  HBOR 闲置资金拿的是「日元计的纳指」，但它的牛熊分界看的是「美元计的 S&P 500」——2008 年、2011 年、2016 年上半、2025-04 这类
    日元急升 / 纳指单独急跌，S&P 的 250 日线还没破，纳指（日元）已经跌了一大段。以前的牛熊研究（T0〜T15）都只换过检测器的参数、
    用的都是 S&P / 日経；用「实际持有的资产」自己的趋势当第二把钥匙没做过。
  UBG 美股熊市时（闲置资金已经转现金），日本个股层照样开新仓 —— 两层方向相反；2001〜2003、2008、2022 这类年份日本股也在跌。
    以前的「日本牛熊 → 个股新仓 ×0」（candle_portfolio 的 jp_bull_only）、量化状态层、判断层都看日本或威胁读数，
    「美股牛熊分界 = 熊 → 日本个股不开新仓」没做过。
做法（两个，各自独立判定；参数全部沿用现行检测器 var/bullbear.json：250 日线 ±3%、连续 5 天 → S6 不适用）：
  HBOR 闲置资金的熊 = S&P 500 熊 或 日元计纳指熊（纳指总收益 × FRED USD/JPY，美国交易日；与第 1 轮同一个序列，同一个检测器）；
       熊 → 闲置资金那份留现金（其余同 B0）。不改个股买卖 → S5 不适用。
       接线：引擎用另一个键 "US_OR" 给闲置资金当牛熊（scripts/candle_portfolio 的 extra_bear），只放 S&P 的熊时必须与 B0 完全相同。
  UBG  信号日（日本收盘）那天的美股牛熊分界 = 熊（同引擎的时点：美国 d 日收盘）→ 日本个股的新仓倍数 ×0（成交日 = 下一个交易日；
       与 B0 的判断层倍数相乘）；闲置资金照旧。改变个股交易 → S5 适用：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）
       在 B0 会买的信号（W2 + C，C 用 E / J 那一折的规则）里，美股熊那天的信号去掉之后，保留的逐笔胜率差、每笔差都要 ≥ 0。
       接线：倍数全 1 时必须与 B0 完全相同。
第一关：research_loop.stage1（HBOR：trade = None；UBG：trade = W / Jx 的差）。
第二关（只给第一关全过的做法；另行登记（提交）后只运行一次，`--stage2 HBOR|UBG`）：随机改动 = 把那个做法新加的状态序列整体循环平移
  （HBOR：日元计纳指的熊序列；UBG：用来挡新仓的美股熊序列；闲置资金自己的牛熊不动），美国交易日 2000-01-03〜2026-09-30，
  k 在 [250, N − 250] 里均匀抽（种子 s = 0〜399：numpy.random.default_rng([20261002, s])）—— 同样多（熊的天数不变）、同样形状（每段长短不变）；
  每次三个年代都跑，统计量 = Calmar 差合计；要严格大于 400 次里的最大值。
只描述：各年代 HBOR 多出来的熊的交易日占比、核心换仓笔数；UBG 挡掉的个股笔数（账户里）与 W / Jx 被挡信号的胜率 / 每笔。
事前预期（照实写）：HBOR 第一关约 20%（2008 / 2011 / 2025-04 能早一点转现金，但 2004、2006、2010、2016 这种只有纳指或日元在动的
  回调会多来回换）；UBG 第一关约 20%（美股熊市时日本突破本来就少，效果多半很小，合计不到 +0.03）；第二关各约 20%；「更好候选」各约 4%。
运行：python scripts/loop_r02_bearstate.py（第一关）；python scripts/loop_r02_bearstate.py --stage2 HBOR [--workers 3]（第二关）。
输出 var/out/loop_r02_bearstate.md / .json（第二关另写 loop_r02_bearstate_stage2_<做法>.md / .json）。非投资建议。
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

ROUND = 2
IDS = ("HBOR", "UBG")
OR_KEY = "US_OR"
SHIFT_FROM, SHIFT_GAP = "2000-01-03", 250
SEED0 = 20261002
OUT = "loop_r02_bearstate"


# ───────────────────────── 状态序列（纯函数，tests/test_loop_r02.py） ─────────────────────────
def union_bear(a: pd.Series, b: pd.Series) -> pd.Series:
    """两个熊序列（各自的日子）→ 合并的日子上 a 或 b（各自向后填，没有值 = 不是熊）。"""
    idx = a.index.union(b.index)
    aa = a.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5
    bb = b.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5
    return pd.Series((aa | bb).to_numpy(bool), index=idx)


def gate_factor(bear: pd.Series, days) -> pd.Series:
    """日本信号日 d：那天（向后填）的美股熊 → 0，否则 1。"""
    days = pd.DatetimeIndex(days)
    b = bear.astype(float).reindex(days.union(bear.index)).ffill().reindex(days).fillna(0.0) > 0.5
    return pd.Series(np.where(b, 0.0, 1.0), index=days)


def bear_at(bear: pd.Series, dates) -> np.ndarray:
    d = pd.DatetimeIndex(pd.to_datetime(dates))
    b = bear.astype(float).reindex(d.union(bear.index)).ffill().reindex(d).fillna(0.0) > 0.5
    return b.to_numpy(bool)


def shift_domain(s: pd.Series, a: str = SHIFT_FROM, b: str = LCM.J_END) -> pd.Series:
    return s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def shifted(s: pd.Series, seed: int) -> pd.Series:
    w = shift_domain(s)
    return pd.Series(np.roll(w.to_numpy(bool), shift_k(seed, len(w))), index=w.index)


def ndx_jpy_bear(inp: dict) -> pd.Series:
    import equity_idle_study as EI
    import loop_r01_voltarget as V
    return EI.t0_bear(V.jpy_ndx(EI.ndx_tr(inp), inp["dexjp"]))


def hb_over(bear_core: pd.Series) -> dict:
    """闲置资金（1545）改看键 OR_KEY 的牛熊（其余同 B0 的 Q1）。"""
    return {"cfg_over": {"core": {"1545.T": 1.0}, "core_index": {"1545.T": OR_KEY}, "core_mode": "split"},
            "extra_bear": {OR_KEY: bear_core}}


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def core_trades(e: str, W: dict) -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    return int(sum(1 for x in eng.st.core_trades if x[0] >= a and (b is None or x[0] < b)))


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop_r02_bearstate.py", "scripts/loop_common.py",
                                 "scripts/research_loop.py", "scripts/loop_r01_voltarget.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def other_stocks(W: dict, bear_us: pd.Series) -> dict:
    """UBG 的 S5：W / Jx 里 B0 会买的信号（W2 + C；C 用 E / J 那一折）去掉美股熊那天的之后，保留 vs 全部。"""
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in LCM.ERAS if x != e]) for e in LCM.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        net = X["net"].to_numpy(float)[kc]
        keep = ~bear_at(bear_us, X["date"].to_numpy()[kc])
        dl = CA.delta(net, keep)
        gone = net[~keep]
        out[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"],
                  "gone_n": int(len(gone)), "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                  "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


def extra_bear_share(W: dict, e: str, bear_us: pd.Series, bear_or: pd.Series) -> float | None:
    ctx = W["ctx"][e]
    a, b = ctx["windows"][e]
    g = pd.DatetimeIndex(ctx["days"])
    g = g[(g >= pd.Timestamp(a)) & ((g < pd.Timestamp(b)) if b else True)]
    if not len(g):
        return None
    x = bear_at(bear_or, g) & ~bear_at(bear_us, g)
    return round(float(x.mean() * 100), 1)


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    bus = W["bear"]["US"]
    bor = union_bear(bus, ndx_jpy_bear(W["inp"]))
    st = RL.load_state()
    reg = st.get("baseline") or {}
    base, cand, trades, ctr, desc = {}, {k: {} for k in IDS}, {}, {}, {}
    for e in LCM.ERAS:
        days = W["ctx"][e]["days"]
        rb = LCM.run(W, e)
        tb = core_trades(e, W)
        rh = LCM.run(W, e, **hb_over(bor))
        th = core_trades(e, W)
        ru = LCM.run(W, e, em_mult=LCM.fill_scale(gate_factor(bus, days), days))
        base[e] = _acct(rb)
        cand["HBOR"][e], cand["UBG"][e] = _acct(rh), _acct(ru)
        trades[e] = {"B0": rb["n"], "UBG": ru["n"]}
        ctr[e] = {"B0": tb, "HBOR": th}
        desc[e] = {"hbor_extra_bear_pct": extra_bear_share(W, e, bus, bor)}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, bus)
    s1 = {"HBOR": RL.stage1(cand["HBOR"], base), "UBG": RL.stage1(cand["UBG"], base, trade=os_)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in LCM.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "code": code, "dirty": dirty, "base": base, "cand": cand, "stage1": s1, "drift": drift,
           "other_stocks": os_, "stock_trades": trades, "core_trades": ctr, "describe": desc, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    name = {"HBOR": "闲置资金的熊 = S&P 熊 或 日元计纳指熊", "UBG": "美股熊时日本个股不开新仓"}
    L = [f"# 研究循环第 2 轮：牛熊状态的两处用法（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop_r02_bearstate.py 开头）", ""]
    for k in IDS:
        s1 = res["stage1"][k]
        L.append(f"- **{k} {name[k]}：{'第一关全过 → 另行登记第二关' if s1['ok'] else RL.FAIL1}**（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；"
                 f"S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5：{('过' if s1['S5'] else '不过') if s1['applies'] else '不适用'}；S6 不适用）")
    L += ["", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | HBOR | UBG |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['HBOR'][e])}（{_f(res['stage1']['HBOR']['d'][e], '{:+.3f}')}） | "
                 f"{cell(res['cand']['UBG'][e])}（{_f(res['stage1']['UBG']['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述："]
    for e in LCM.ERAS:
        L.append(f"- {e}：HBOR 多出来的熊（日本交易日占比）{_f(res['describe'][e]['hbor_extra_bear_pct'], '{:.1f}')}%、核心换仓 "
                 f"{res['core_trades'][e]['B0']} → {res['core_trades'][e]['HBOR']} 笔；UBG 账户里的个股笔数 {res['stock_trades'][e]['B0']} → {res['stock_trades'][e]['UBG']}")
    for s, x in res["other_stocks"].items():
        L.append(f"- UBG 别的股票 {s}：B0 会买 {x['n']} 笔，挡掉 {x['gone_n']} 笔（胜率 {_f(x['gone_win'], '{:.1f}')}%、每笔 {_f(x['gone_mean'], '{:+.2f}')}%）；"
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


def _cand_runs(W: dict, k: str, extra: pd.Series) -> dict:
    """做法 k 用状态序列 extra（HBOR：日元计纳指的熊；UBG：挡新仓用的美股熊）→ 三个年代的 Calmar。"""
    out = {}
    for e in LCM.ERAS:
        days = W["ctx"][e]["days"]
        if k == "HBOR":
            r = LCM.run(W, e, **hb_over(union_bear(W["bear"]["US"], extra)))
        else:
            r = LCM.run(W, e, em_mult=LCM.fill_scale(gate_factor(extra, days), days))
        out[e] = r["calmar"]
    return out


def _placebo_one(seed: int) -> float | None:
    W, k, src, base = _G["W"], _G["k"], _G["src"], _G["base"]
    try:
        c = _cand_runs(W, k, shifted(src, seed))
        if any(c[e] is None or base[e] is None for e in LCM.ERAS):
            return None
        return round(float(sum(c[e] - base[e] for e in LCM.ERAS)), 6)
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
    src = ndx_jpy_bear(W["inp"]) if k == "HBOR" else W["bear"]["US"]
    base = {e: LCM.run(W, e)["calmar"] for e in LCM.ERAS}
    cand = _cand_runs(W, k, src)
    stat = round(sum(cand[e] - base[e] for e in LCM.ERAS), 6)
    _G.update({"W": W, "k": k, "src": src, "base": base})
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
    L = [f"# 研究循环第 2 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环第 2 轮：HBOR / UBG")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
