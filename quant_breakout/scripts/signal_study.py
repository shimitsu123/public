"""signal_study.py — 日本个股「即将上涨（买点）」与「顶（卖点）」的成功率：5 个候选（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

研究问题（用户原话「股票判断顶底和即将上涨的逻辑要继续进行研究让成功率更高」，优化后）：
  在 S0C2 的日本个股部分（日経225 股票池），能不能在不降低每笔期望、不恶化组合收益回撤的前提下，
  把 ① 买点（横盘后 MACD 金叉突破）的成功率（扣费后赚钱的比例）提高 ≥ 3 个百分点，
  ② 卖点更接近顶部（离场后价格回落的比例更高），③ 候补队列「即将触发」的命中率更高？
  成功率单独看会骗人（例如收紧止盈就能抬高胜率、但每笔期望下降），所以胜率与每笔期望、组合的 Calmar / 回撤一起判断。

一、现行规则的逐笔诊断（登记前只看了现行规则，没有算任何候选；2006-10〜2026-09，213 只，638 笔，来回手续费 0.15%）
  - 买点：胜率 42.5%，平均赚 +5.80% / 平均亏 −3.07%，每笔期望 +0.70%，持有中位 11 个交易日；
    两个半段 2006-10〜2015：胜率 39.6%、期望 +0.69%（240 笔）；2016〜：44.2%、+0.70%（398 笔）。靠赔率赚钱，不靠命中率。
  - 卖点：95.9% 的离场是 MACD 死叉；死叉卖出后 20 个交易日价格比卖价低的只有 46.2%（之后 20 日中位还涨 +0.81%）→ 卖点接近掷硬币。
  - 即将触发（候补队列）：7,027 次里 5 个交易日内真的出信号的只有 8.7%；之后 20 日上涨的比例 53.6%（中位 +0.53%）。

二、候选（qbreak/signal_filters.py；参数全部事先固定，取常用值，不做网格搜索）
  E1 长期趋势对齐：收盘在 200 日线上 且 200 日线比 20 个交易日前高（Minervini 趋势模板；下降趋势里的突破多失败）
  E2 接近 52 周高点：收盘 ≥ 52 周最高收盘 × 0.75（George & Hwang 2004 的 52 周高点效应；Minervini「离高点 25% 以内」）
  E3 波动收缩（蓄势充分）：前一天的布林带宽（20 日 ±2σ）在过去 250 天里处于最低 25%（突破前的波动收敛）
  E4 真突破箱顶：收盘 > 过去 60 日最高（不含当天）—— 现行四个条件里没有任何一条要求价格真的突破（原版的 require_breakout 开关）
  X1 死叉离场要确认（卖点）：MACD 在信号线下 且 收在 20 日线下，两者同时成立的第一天才离场（替换死叉离场；止损 7%、止盈 25%、
     跟踪 12%、最长 60 天、高位放量阴线离场都不变）
  买点候选只把现行的 entry 再收紧；E1〜E3 同样加到「即将触发」上看命中率（E4 在触发前不可能成立，不适用）。

三、评价
  1) 逐笔（每只票单独用回测引擎、一次只持一仓 —— 出场规则与模拟盘完全相同；次日开盘成交，含跳空与涨跌停规则、滑点）：
     净收益 = 引擎的价格收益 − S0C2 一个名额（约 ¥25 万）的来回手续费；
     胜率（净收益 > 0 的比例）、平均赚 / 平均亏、盈亏比、每笔期望、持有中位；两个半段 2006-10〜2015 / 2016〜。
     买点候选另报「被剔除的那些交易」的胜率与期望（应当更差）。
  2) 不确定性：按月聚类的自助法（按入场月份整月重抽，2,000 次，种子 20260926），候选 − 现行 的胜率差与期望差的 95% 区间。
  3) 滚动：4 个 5 年窗口（2006-10〜2010、2011〜2015、2016〜2020、2021〜）的胜率差与期望差。
  4) 卖点：非止损离场之后 20 个交易日价格比卖价低的比例（「卖对了」）与之后 20 日的中位涨跌。
  5) 即将触发：5 个交易日内真的出信号的比例、之后 20 日上涨的比例与中位。
  6) S0C2 组合：统一引擎、现行立花费用、1655 用现行 T0 择时，只换日本个股的信号；20 年（2006-10〜）/ 5 年（2021-09〜）。
  幸存者偏差：股票池是现在的成分股 → 绝对水平偏乐观；候选与现行用同一个股票池，比较的是差。

四、采用门槛（全部满足才算「通过」，否则维持现行）
  ① 胜率：两个半段都比现行高 ≥ 3 个百分点
  ② 每笔期望：两个半段都不低于现行
  ③ 统计：全期胜率差的 95% 自助区间下限 > 0
  ④ S0C2 组合 20 年：Calmar 不低于现行，且最大回撤不比现行深
  另报（不改判定，醒目标出）：4 个 5 年窗口里胜率差 < 0 的窗口 ≥ 2 个；S0C2 20 年年化 < 现行 − 0.3 pp；S0C2 5 年回撤 < −30%；
  买点候选保留的交易 < 现行的 40%；「即将触发」加同一条件后命中率没有提高。
  5 个候选一起检验：③ 用 95% 区间（单个候选的误判率约 2.5%，5 个合计约 12%），再加 ① 两个半段都要达标，降低碰巧通过的机会。

五、之后
  - 不改模拟盘的交易规则，除非候选通过门槛、并且用户在对话里确认。
  - 通过的候选：前向观察一个季度（每个真实信号记下「候选会不会做 / 结果如何」），之后的季度复核再决定；多个通过时按
    全期胜率差排序。季度复核：`python scripts/signal_study.py --review --only BASE,<通过的候选>`（同一套规则，只加数据）。
  登记前做过的检查：tests/test_signal_filters.py（只收紧 entry / 只改离场事件、无前视）；合成行情上全流程跑通；
  真实数据只跑了现行规则（上面「一」的数字）。

输出：var/out/signal_study.md / .json / .csv
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_filters as F                                       # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                      # noqa: E402
from qbreak.config import BacktestConfig, DataConfig, universe               # noqa: E402
from qbreak.core import core_frame                                           # noqa: E402
from qbreak.data import load_universe                                        # noqa: E402
from qbreak.engine import run_backtest                                       # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                               # noqa: E402
from qbreak.strategy import IndicatorCache                                   # noqa: E402
from qbreak.trader import load_params                                        # noqa: E402
from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs, imminent_flags  # noqa: E402

START = "2006-10-01"
HALVES = {"H1": (START, "2015-12-31"), "H2": ("2016-01-01", None)}
WINDOWS = [(START, "2010-12-31"), ("2011-01-01", "2015-12-31"), ("2016-01-01", "2020-12-31"), ("2021-01-01", None)]
NOTIONAL = 250_000                                   # S0C2 一个名额约 ¥25 万（手续费按这个金额算）
WIN_PP, BOOT_N, SEED, KEEP_MIN = 3.0, 2000, 20260926, 0.40
W20, W5 = "2006-10-01", "2021-09-24"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 1) 逐笔 ──
def trades(ind: dict, p, bt) -> pd.DataFrame:
    fee = bt.exec_cfg.fee
    rt = (fee(NOTIONAL) * 2) / NOTIONAL * 100
    rows = []
    for t, df in ind.items():
        try:
            r = run_backtest({t: df}, p, bt, start=START)
        except ValueError:
            continue
        tr = r.trades[r.trades["reason"] != "end"].copy()
        if len(tr):
            tr["ticker"] = t
            rows.append(tr)
    if not rows:
        return pd.DataFrame(columns=["ticker", "entry_date", "exit_date", "ret_pct", "net", "win", "reason", "hold_days", "exit_px"])
    T = pd.concat(rows, ignore_index=True)
    T["entry_date"], T["exit_date"] = pd.to_datetime(T["entry_date"]), pd.to_datetime(T["exit_date"])
    T["net"] = T["ret_pct"] - rt
    T["win"] = T["net"] > 0
    return T


def in_window(T: pd.DataFrame, w) -> pd.DataFrame:
    m = T["entry_date"] >= pd.Timestamp(w[0])
    if w[1]:
        m &= T["entry_date"] <= pd.Timestamp(w[1])
    return T[m]


def stats(T: pd.DataFrame) -> dict:
    if not len(T):
        return {"n": 0}
    w, lo = T.net[T.net > 0], T.net[T.net <= 0]
    return {"n": int(len(T)), "win": round(float(T.win.mean()) * 100, 2), "avg_win": round(float(w.mean()), 2) if len(w) else None,
            "avg_loss": round(float(lo.mean()), 2) if len(lo) else None,
            "payoff": round(float(w.mean() / -lo.mean()), 2) if len(w) and len(lo) and lo.mean() < 0 else None,
            "exp": round(float(T.net.mean()), 3), "hold_med": float(T.hold_days.median())}


def excluded(base: pd.DataFrame, cand: pd.DataFrame) -> pd.DataFrame:
    k = set(zip(cand.ticker, cand.entry_date))
    return base[[x not in k for x in zip(base.ticker, base.entry_date)]]


# ── 2) 按月聚类的自助法 ──
def boot(base: pd.DataFrame, cand: pd.DataFrame, seed: int) -> dict:
    mb, mc = base.entry_date.dt.to_period("M"), cand.entry_date.dt.to_period("M")
    months = np.array(sorted(set(mb) | set(mc)))
    gb = {m: g for m, g in base.groupby(mb)}
    gc = {m: g for m, g in cand.groupby(mc)}
    agg = lambda g: (len(g), float(g.win.sum()), float(g.net.sum()))                 # noqa: E731
    B = np.array([agg(gb[m]) if m in gb else (0, 0.0, 0.0) for m in months])
    C = np.array([agg(gc[m]) if m in gc else (0, 0.0, 0.0) for m in months])
    rng = np.random.default_rng(seed)
    s = rng.integers(0, len(months), (BOOT_N, len(months)))
    sb, sc = B[s].sum(axis=1), C[s].sum(axis=1)
    ok = (sb[:, 0] > 0) & (sc[:, 0] > 0)
    dwin = (sc[ok, 1] / sc[ok, 0] - sb[ok, 1] / sb[ok, 0]) * 100
    dexp = sc[ok, 2] / sc[ok, 0] - sb[ok, 2] / sb[ok, 0]
    q = lambda x, a: round(float(np.percentile(x, a)), 3)                             # noqa: E731
    return {"dwin_lo": q(dwin, 2.5), "dwin_hi": q(dwin, 97.5), "dexp_lo": q(dexp, 2.5), "dexp_hi": q(dexp, 97.5)}


# ── 4) 卖点质量 / 5) 即将触发 ──
def exit_quality(T: pd.DataFrame, ind: dict) -> dict:
    after = []
    for x in T[~T.reason.isin(["stop", "gap_stop"])].itertuples():
        c = ind[x.ticker]["Close"]
        i = c.index.searchsorted(x.exit_date)
        if i + 20 < len(c):
            after.append(float(c.iloc[i + 20] / x.exit_px - 1))
    a = np.array(after)
    return {"n": int(len(a)), "right_pct": round(float((a < 0).mean()) * 100, 1) if len(a) else None,
            "after20_med": round(float(np.median(a)) * 100, 2) if len(a) else None}


def imminent_precision(ind: dict, key: str) -> dict | None:
    if key != "BASE" and F.entry_condition(next(iter(ind.values())), key) is None:
        return None
    n = hit = 0
    fwd = []
    for df in ind.values():
        imm = imminent_flags(df) & ~df["entry"].astype(bool)
        if key != "BASE":
            imm &= F.entry_condition(df, key)
        imm = imm & (df.index >= pd.Timestamp(START))
        ent, c = df["entry"].to_numpy(bool), df["Close"].to_numpy(float)
        for i in np.where(imm.to_numpy())[0]:
            if i + 21 >= len(df):
                continue
            n += 1
            hit += bool(ent[i + 1:i + 6].any())
            fwd.append(c[i + 20] / c[i] - 1)
    f = np.array(fwd)
    return {"n": n, "hit5_pct": round(hit / max(1, n) * 100, 1), "up20_pct": round(float((f > 0).mean()) * 100, 1) if n else None,
            "fwd20_med": round(float(np.median(f)) * 100, 2) if n else None}


# ── 6) S0C2 组合 ──
def s0c2_builder(data: dict, p) -> callable:
    from bullbear_study import SYM, load
    from unified_study import spx_jpy_on_jp_days
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    broker = (sim.get("unified") or {}).get("broker", "tachibana")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    params = {"JP": p, "US": load_params(market="US")}
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    core = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    names = list(data)
    cfgd = load_config()
    det = Detector(cfgd["detector"]["kind"], cfgd["detector"]["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = exec_configs(("JP",), {"broker": broker})
    cc = {"1655.T": etf_cost(broker, "1655.T", "JP")}
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                        stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"}, core_mode="split")
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    closes = pd.DataFrame({t: data[t]["Close"] for t in names})
    cache: dict = {}

    def run(ind: dict) -> dict:
        if "em" not in cache:                              # 入场倍数只取决于日期与股票（候选不改），算一次
            g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
            M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")),
                                    use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
            M = M * quant_regime_series(idx["JP"]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
            cache["em"] = {"JP": pd.DataFrame(M, index=g, columns=names)}
        em = cache["em"]
        row = {"broker": broker}
        for wn, st in (("w20", W20), ("w5", W5)):
            r = UnifiedEngine({**ind, "1655.T": core}, cfg, params, ex, cc, fx=fxdf[["Open", "Close"]], entry_mult=em,
                              bear=bear).run(start=st)
            dd = float((r.equity / r.equity.cummax() - 1).min() * 100)
            tr = r.trades[r.trades["reason"] != "end"]
            row.update({f"{wn}_cagr": r.metrics.get("cagr_pct"), f"{wn}_dd_exact": dd, f"{wn}_calmar_exact":
                        (r.metrics.get("cagr_pct") or 0) / abs(dd) if dd < 0 else None, f"{wn}_trades": int(len(tr))})
        return row
    return run


# ── 判定（事先规则）──
def decide(R: dict, keys) -> dict:
    per = {}
    b = R["BASE"]
    for k in keys:
        if k == "BASE":
            continue
        r, fails, warns = R[k], [], []
        for h in HALVES:
            dw = r["halves"][h]["win"] - b["halves"][h]["win"]
            if dw < WIN_PP:
                fails.append(f"{h} 胜率 {r['halves'][h]['win']}% − 现行 {b['halves'][h]['win']}% = {dw:+.2f} pp < +{WIN_PP}")
            if r["halves"][h]["exp"] < b["halves"][h]["exp"]:
                fails.append(f"{h} 每笔期望 {r['halves'][h]['exp']:+.3f}% < 现行 {b['halves'][h]['exp']:+.3f}%")
        if not r["boot"]["dwin_lo"] > 0:
            fails.append(f"全期胜率差 95% 区间 {r['boot']['dwin_lo']:+.2f}〜{r['boot']['dwin_hi']:+.2f} pp，下限不大于 0")
        s, s0 = r["s0c2"], b["s0c2"]
        if s["w20_calmar_exact"] is None or s0["w20_calmar_exact"] is None or s["w20_calmar_exact"] < s0["w20_calmar_exact"]:
            fails.append(f"S0C2 20 年 Calmar {s['w20_calmar_exact']:.3f} < 现行 {s0['w20_calmar_exact']:.3f}")
        if s["w20_dd_exact"] < s0["w20_dd_exact"]:
            fails.append(f"S0C2 20 年回撤 {s['w20_dd_exact']:.2f}% 深于现行 {s0['w20_dd_exact']:.2f}%")
        neg = sum(1 for x, y in zip(r["windows"], b["windows"]) if x.get("n") and y.get("n") and x["win"] < y["win"])
        if neg >= 2:
            warns.append(f"4 个 5 年窗口里 {neg} 个胜率低于现行")
        if s["w20_cagr"] < s0["w20_cagr"] - 0.3:
            warns.append(f"S0C2 20 年年化 {s['w20_cagr']}% < 现行 {s0['w20_cagr']}% − 0.3")
        if s["w5_dd_exact"] < -30.0:
            warns.append(f"S0C2 5 年回撤 {s['w5_dd_exact']:.2f}% < −30%")
        if k in F.ENTRY_FILTERS and r["all"]["n"] < KEEP_MIN * b["all"]["n"]:
            warns.append(f"只保留了现行交易的 {r['all']['n'] / b['all']['n'] * 100:.0f}%（< {KEEP_MIN * 100:.0f}%）")
        imm, imm0 = r.get("imminent"), b.get("imminent")
        if imm and imm0 and imm["hit5_pct"] <= imm0["hit5_pct"]:
            warns.append(f"「即将触发」命中率 {imm['hit5_pct']}% 没有高于现行 {imm0['hit5_pct']}%")
        per[k] = {"pass": not fails, "fails": fails, "warnings": warns,
                  "dwin_all": round(r["all"]["win"] - b["all"]["win"], 2)}
    passed = sorted([k for k in per if per[k]["pass"]], key=lambda k: -per[k]["dwin_all"])
    return {"per": per, "passed": passed}


def evaluate(ind0: dict, p, bt, keys, s0c2_run) -> dict:
    R = {}
    for k in keys:
        t1 = time.time()
        ind = {t: F.apply(df, k) for t, df in ind0.items()}
        T = trades(ind, p, bt)
        r = {"all": stats(T), "halves": {h: stats(in_window(T, w)) for h, w in HALVES.items()},
             "windows": [stats(in_window(T, w)) for w in WINDOWS], "exit": exit_quality(T, ind),
             "reasons": {why: stats(d) for why, d in T.groupby("reason")}, "imminent": imminent_precision(ind0, k)}
        R[k] = r
        R[k]["_T"] = T
        R[k]["s0c2"] = s0c2_run(ind)
        print(k, r["all"], f"{time.time() - t1:.0f}s", flush=True)
    for k in keys:
        if k != "BASE":
            R[k]["excluded"] = stats(excluded(R["BASE"]["_T"], R[k]["_T"])) if k in F.ENTRY_FILTERS else None
            R[k]["boot"] = boot(R["BASE"]["_T"], R[k]["_T"], SEED)
    return R


def report(R: dict, V: dict, keys, head: str, n_tickers: int, t0: float, review: bool) -> None:
    lab = F.LABELS
    say(f"# 日本个股「即将上涨（买点）」与「顶（卖点）」的成功率：现行 vs 5 个候选（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say(f"股票池 {n_tickers} 只（日経225 broad，现在的成分股 → 有幸存者偏差），{START}〜；净收益扣 S0C2 一个名额（¥25 万）的来回手续费。"
        "规则见 scripts/signal_study.py 开头（先提交后运行）。" + ("季度复核模式。" if review else ""))
    say("\n## 1) 逐笔成功率（每只票单独、一次一仓，出场规则与模拟盘相同）")
    say("| 方案 | 笔数 | 胜率 全期 / 前半 / 后半 | 平均赚 / 平均亏 | 盈亏比 | 每笔期望 全期 / 前半 / 后半 | 持有中位 |")
    say("|---|---|---|---|---|---|---|")
    for k in keys:
        a, h1, h2 = R[k]["all"], R[k]["halves"]["H1"], R[k]["halves"]["H2"]
        say(f"| {k} {lab[k]} | {a['n']} 笔（{h1['n']} / {h2['n']}） | {a['win']}% / {h1['win']}% / {h2['win']}% | "
            f"{a['avg_win']:+.2f}% / {a['avg_loss']:+.2f}% | {a['payoff']} | {a['exp']:+.2f}% / {h1['exp']:+.2f}% / {h2['exp']:+.2f}% | "
            f"{a['hold_med']:.0f} 天 |")
    say("\n被剔除的交易（买点候选剔掉的那些，应当更差）：")
    for k in keys:
        x = R[k].get("excluded")
        if x and x.get("n"):
            say(f"- {k}：{x['n']} 笔，胜率 {x['win']}%，每笔期望 {x['exp']:+.2f}%")
    say("\n## 2) 不确定性（按月聚类自助 2,000 次；候选 − 现行 的 95% 区间）")
    say("| 候选 | 胜率差 全期 | 95% 区间 | 每笔期望差 95% 区间 |")
    say("|---|---|---|---|")
    for k in keys:
        if k == "BASE":
            continue
        bt_ = R[k]["boot"]
        say(f"| {k} | {R[k]['all']['win'] - R['BASE']['all']['win']:+.2f} pp | {bt_['dwin_lo']:+.2f}〜{bt_['dwin_hi']:+.2f} pp | "
            f"{bt_['dexp_lo']:+.3f}〜{bt_['dexp_hi']:+.3f} pp |")
    say("\n## 3) 4 个 5 年窗口的胜率 / 每笔期望")
    say("| 方案 | " + " | ".join(f"{w[0][:4]}–{(w[1] or 'now')[:4]}" for w in WINDOWS) + " |")
    say("|---|" + "---|" * len(WINDOWS))
    for k in keys:
        say(f"| {k} | " + " | ".join(f"{x['win']}% / {x['exp']:+.2f}%（{x['n']}）" if x.get("n") else "—" for x in R[k]["windows"]) + " |")
    say("\n## 4) 卖点：离场后 20 个交易日价格比卖价低的比例（卖对了）")
    for k in keys:
        e = R[k]["exit"]
        say(f"- {k}：卖对了 {e['right_pct']}%（{e['n']} 笔），离场后 20 日中位 {e['after20_med']:+.2f}%；"
            + "；".join(f"{why} {d['n']} 笔 胜率 {d['win']}%" for why, d in R[k]["reasons"].items()))
    say("\n## 5) 「即将触发」的命中率（5 个交易日内真的出信号 / 之后 20 日上涨）")
    for k in keys:
        im = R[k]["imminent"]
        say(f"- {k}：" + (f"{im['n']} 次，5 日内触发 {im['hit5_pct']}%，20 日后上涨 {im['up20_pct']}%（中位 {im['fwd20_med']:+.2f}%）"
                         if im else "不适用"))
    say(f"\n## 6) S0C2 组合（统一引擎，{R['BASE']['s0c2']['broker']} 费用，1655 用现行 T0；只换日本个股的信号）")
    say("| 方案 | 20 年年化 / 回撤 / Calmar | 5 年年化 / 回撤 | 20 年个股交易笔数 |")
    say("|---|---|---|---|")
    for k in keys:
        s = R[k]["s0c2"]
        say(f"| {k} | {s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} | {s['w5_cagr']}% / "
            f"{s['w5_dd_exact']:.2f}% | {s['w20_trades']} 笔 |")
    say("\n## 判定（事先规则：① 两个半段胜率都 +3 pp 以上；② 两个半段每笔期望都不低于现行；③ 全期胜率差 95% 区间下限 > 0；"
        "④ S0C2 20 年 Calmar 不低于现行、回撤不更深）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）")
            + (f"。另报：{'；'.join(r['warnings'])}" if r["warnings"] else ""))
    say(f"\n通过：{'、'.join(V['passed'])} → 前向观察一个季度再决定；模拟盘规则不变（改需用户确认）。" if V["passed"]
        else "\n没有候选通过 → 维持现行（模拟盘规则不变）。")
    say(f"\n代码版本 {head}")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只比较这些（逗号分隔，须含 BASE）")
    ap.add_argument("--review", action="store_true", help="季度复核：输出带日期的文件并追加历史")
    args = ap.parse_args(argv)
    keys = args.only.split(",") if args.only else F.KEYS
    if "BASE" not in keys or any(k not in F.KEYS for k in keys):
        raise SystemExit(f"--only 必须包含 BASE，且只能是 {F.KEYS}")
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/signal_study.py", "qbreak/signal_filters.py",
                            "qbreak/engine.py", "qbreak/unified.py", "qbreak/strategy.py"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data = load_universe(universe("JP", "broad"), d21)
    ind0 = dict(IndicatorCache(data).all(p))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    R = evaluate(ind0, p, bt, keys, s0c2_builder(data, p))
    V = decide(R, keys)
    report(R, V, keys, head, len(ind0), t0, args.review)
    fp = paths.out_dir() / ("signal_study" if not args.review else f"signal_review_{pd.Timestamp.today().date()}")
    if args.review:
        hist = paths.out_dir() / "signal_review_history.csv"
        row = {"run": str(pd.Timestamp.today().date()), "passed": "|".join(V["passed"])}
        for k in keys:
            row.update({f"{k}_win": R[k]["all"]["win"], f"{k}_exp": R[k]["all"]["exp"], f"{k}_n": R[k]["all"]["n"],
                        f"{k}_s0c2_calmar": round(R[k]["s0c2"]["w20_calmar_exact"], 3)})
        old = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
        pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(hist, index=False)
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "decision": V,
                                              "results": {k: {q: v for q, v in R[k].items() if q != "_T"} for k in keys}},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    rows = [{"cand": k, "label": F.LABELS[k], "pass": V["per"].get(k, {}).get("pass"),
             **{f"all_{q}": R[k]["all"].get(q) for q in ("n", "win", "exp", "payoff")},
             **{f"{h}_{q}": R[k]["halves"][h].get(q) for h in HALVES for q in ("n", "win", "exp")},
             **{f"s0c2_{q}": R[k]["s0c2"].get(q) for q in ("w20_cagr", "w20_dd_exact", "w20_calmar_exact", "w5_cagr", "w5_dd_exact")}}
            for k in keys]
    pd.DataFrame(rows).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
