"""mtf_study.py — 多周期（日 / 周 / 月线）：上涨股票的特征与卖顶的特征（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

用户：「继续研究 结合日 周 月线来找出上涨股票和卖顶的特征 根据现在的所有研究方向 因子搭配，错峰等等 制定一个可以稳定增长胜率和收益率的
研究方向进行继续研究 不限于现在的研究方向 可以开发出另外的研究方向」。研究路线图见 RESEARCH_PLAN.md（这是其中 R1）。

为什么这样做（以前的结论）：买点过滤几乎都不成立（因子组合、机器学习、质量分、错峰）；周 / 月线趋势过滤在日経225 20 年 647 笔上不显著
（exec_timing_study）；现行出场几乎都是日线 MACD 死叉（param_study：止盈 / 跟踪止损 / 最长持有几乎不起作用，关掉死叉则交易少一半、组合更差）
→ 这次重点是卖出一侧（「强势股会不会被日线的小回调卖掉」「周 / 月线的见顶特征能不能卖在顶附近」），买入一侧用更大的样本
（时点 TOPIX 1000，约 2,000 笔以上）重新看周 / 月线特征，另外试一个新的买点来源（周线突破系统）。

一、数据与股票池（与 ml_study / pit_retrain_study 同一套，qbreak/pit_data.py；原始数据只在 var/cache/jquants/，不入库）
  J-Quants 批量日线 2016-09-26〜2026-09-25（拆股调整；一手按当时真实股价）。U2 = 时点 TOPIX 1000（逐笔描述与挑选）、
  U1 = 时点 TOPIX 500（组合判定 V / H）、U0 = 今天的日経225（J-Quants 行情，= 实盘股票池；稳健性判定 R）。
  组合 = S0C2，var/sim.json 同一套设定（2026-09-27 撤回一手放宽之后：一手放宽关）；现行参数 P0（var/best_params*.json）。
二、周线 / 月线（qbreak/mtf.py；只用已经完成的 K 线）
  周 = ISO 周、月 = 日历月；一根 K 线在市场日历里这一周 / 这个月最后一个交易日收盘时完成；状态从完成日起有效到下一根完成，
  事件只在完成日（这只票那天没有 K 线 → 之后第一根）。历史不够 → 缺值（NaN）。
  状态（买点特征）：W1 周线 Stage 2（收盘 > 30 周均线且均线比 4 周前高）、W2 周线 MACD(12,26,9) 柱 > 0、W3 周线 RSI(14) ≥ 50、
    W4v 26 周箱体振幅、W5v 周线量比（这周 / 前 10 周平均）、W6v 收盘 / 52 周最高；
    M1 月线收盘 > 10 个月均线、M2v 12-1 个月动量、M3 月线 MACD 柱 > 0、M4v 收盘 / 36 个月最高（至少 24 个月）、M5v 收盘 / 10 个月均线 − 1。
  事件（见顶特征）：X1 周线收盘 < 10 周均线、X2 周线 MACD 死叉、X3 周线高潮（周量比 ≥ 2、收在周振幅下 1/3、这周创 52 周新高）、
    X4 月线 RSI(14) ≥ 80、X5 周线收盘跌破上一周最低、X6 连涨 ≥ 5 周后第一根下跌周；B26 周线突破（收盘 > 前 26 周最高且周量比 ≥ 1.5）。
三、描述（只描述，不参与判定）
  A 所有股票：每周最后一个交易日、U2 成员，按「日线收盘 > 20 日均线 / 周线 W1 / 月线 M1」8 种组合 → 下一交易日开盘买、20 个交易日后
    开盘卖的超额收益（减当天全部样本平均）：每周平均的均值（按月聚类自助法 95% 区间）与超额 > 0 的比例；验证期 / 留出期。
  B 现行买点（U2 独立突破交易：每只票单独、一次一仓，出场规则与模拟盘相同，扣一笔 ¥25 万的来回手续费）：
    E1〜E12 每条规则「保留 / 过滤」两组的胜率与每笔平均净收益（验证期 / 留出期；差的按月聚类 95% 区间；10 个年份里保留组更好的年数）；
    连续特征（W4v、W5v、W6v、M2v、M4v、M5v）按全部交易的三分位分三档。
  C 卖点（U2 独立交易）：现行、加上 X1〜X6 各一个见顶离场、C1、C2、C5 → 笔数、胜率、每笔平均 / 中位净收益、盈亏比、平均持有天数。
四、交易候选（S0C2；只改 entry / dead_cross 两列，其余出场 7% 止损、25% 止盈、12% 跟踪止损、60 日最长持有不变）
  C1 条件出场（强势放长）：周线 W1 且 W2（最近完成的周）→ 日线死叉不卖，改为 X1 周线收盘 < 10 周均线时卖；
     不强势的日子 → 日线 MACD 在信号线下就卖（= 现行的死叉离场）
  C2 周线出场替换：日线死叉离场全部换成 X1
  C3 见顶离场：现行 + X1〜X6 里的一个（B 部分的验证期挑：每笔平均净收益 > 现行且胜率不低于现行，取每笔平均最高的；没有 → 不跑）
  C4 多周期买点过滤：E1〜E12 里的一条（验证期挑：保留 ≥ 50% 的交易、保留组胜率与每笔平均都高于被过滤组，取差最大的；没有 → 不跑）；
     规则的特征缺值 → 不过滤
     E1 W1、E2 W2、E3 W3、E4 W4v ≤ 验证期现行交易的中位数（长底更紧）、E5 W5v ≥ 1.5、E6 W6v ≥ 0.95（52 周高点 5% 以内）、
     E7 M1、E8 M2v > 0、E9 M3、E10 M4v ≥ 0.90（36 个月高点 10% 以内）、E11 M5v ≤ 0.20（没有过热）、E12 W1 且 M1（三周期共振）
  C5 周线突破系统（新的买点来源，替换日线买点）：B26 且 M1 → 下一交易日开盘买；出场 = X1（其余同上）
五、判定（与 ml_study 同一套 V / H，另加 R；「现行」= 同一设定不改）
  V U1 验证期（2019-01〜2023-09）：Calmar > 现行，且最大回撤不比现行深 2 pp 以上
  H U1 留出期（2023-10〜）与两个半段（2025-04 分）各自：Calmar ≥ 现行 + 0.05，且最大回撤不比现行深
  R U0（今天的日経225）全窗口 2017-01〜：Calmar ≥ 现行、最大回撤不比现行深 2 pp 以上、个股胜率不比现行低 2 pp 以上
  都满足 → 通过；多个通过 → 提议验证期 Calmar 最高的（一样取编号小的）。通过也只是提议：模拟盘改不改要用户在对话里确认；
  都不通过 → 维持现行。另报 U1 每年的收益（只描述）。
六、局限：只有 10 年；月线特征要 10〜36 个月历史 → 2017〜2019 年初缺值多（缺值 = 不过滤 / 不强势）；日経225 没有时点成分
  （U1 代替）；调整后价不含分红；以前的研究在同一段数据上做过很多检验，留出期不是完全没见过的数据；C3 / C4 在验证期挑，
  所以验证期的判定偏乐观，留出期才是真正的检验；税前。
登记前做过的检查：tests/test_mtf.py（完成日、聚合、停牌、状态 / 事件的日期、截断数据不改变之前的任何值、手算的特征）、
  tests/test_mtf_study.py（候选的构造、规则缺值不过滤、挑选规则、R 门槛）；--coverage 只看股票只数、信号与交易笔数、特征覆盖率，
  没有算任何特征与收益的关系。覆盖（2026-09-27）：U0 213、U1 581、U2 1,378 只，市场日 2,441 天，退市 178 只；U2 现行独立交易
  2,227 笔（验证期 979、留出期 696），周 / 月线特征有值的比例 验证期 98〜100%、留出期 100%（全期 75〜100%，月线 MACD / 36 个月高点最少）；
  C5 周线突破买点 7,461 个（现行日线买点 2,290 个，U2 成员日）。
输出：var/out/mtf_study.md / .json（只有统计，不含原始数据）
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
import jq_study as JS                                                        # noqa: E402
import ml_study as MS                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import ml                                                        # noqa: E402
from qbreak import mtf                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import pit_data as PD                                            # noqa: E402

WINDOW, TRADE_START = PRS.WINDOW, PRS.TRADE_START
VAL, HOLD, H1, H2 = MS.VAL, MS.HOLD, MS.H1, MS.H2
CALMAR_UP, DD_TOL, WIN_TOL = MS.CALMAR_UP, MS.DD_TOL, 2.0
KEEP_MIN = 0.5
FWD_H = 20
N_BOOT, SEED = 2000, 20260927
TOPS = ("X1", "X2", "X3", "X4", "X5", "X6")
RULES = {"E1": "W1 周线 Stage 2", "E2": "W2 周线 MACD 柱 > 0", "E3": "W3 周线 RSI ≥ 50", "E4": "W4v 26 周箱体 ≤ 验证期中位数（长底更紧）",
         "E5": "W5v 周线量比 ≥ 1.5", "E6": "W6v 52 周高点 5% 以内", "E7": "M1 月线 > 10 个月均线", "E8": "M2v 12-1 个月动量 > 0",
         "E9": "M3 月线 MACD 柱 > 0", "E10": "M4v 36 个月高点 10% 以内", "E11": "M5v 离 10 个月均线 ≤ 20%", "E12": "W1 且 M1（三周期共振）"}
CANDS = {"C1": "条件出场：周线强势时日线死叉不卖、改用周线收盘 < 10 周均线", "C2": "周线出场替换：日线死叉 → 周线收盘 < 10 周均线",
         "C3": "见顶离场：现行 + 验证期挑出的周 / 月线见顶特征", "C4": "多周期买点过滤：验证期挑出的一条周 / 月线规则",
         "C5": "周线突破系统：周线突破 + 月线向上买、周线收盘 < 10 周均线卖"}
CONT = ("W4v", "W5v", "W6v", "M2v", "M4v", "M5v")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ────────────────────────── 候选的构造（只改 entry / dead_cross） ──────────────────────────
def rule_keep(rule: str, f: pd.DataFrame, e4_cut: float | None = None) -> np.ndarray:
    """规则 → 保留（True）；规则用到的特征缺值 → 保留（不过滤）。"""
    def ge(col, x):
        v = f[col].to_numpy(float)
        return ~np.isfinite(v) | (v >= x)

    def le(col, x):
        v = f[col].to_numpy(float)
        return ~np.isfinite(v) | (v <= x)
    table = {"E1": lambda: ge("W1", 1), "E2": lambda: ge("W2", 1), "E3": lambda: ge("W3", 1),
             "E4": lambda: le("W4v", e4_cut if e4_cut is not None else np.inf), "E5": lambda: ge("W5v", 1.5),
             "E6": lambda: ge("W6v", 0.95), "E7": lambda: ge("M1", 1), "E8": lambda: ~np.isfinite(f["M2v"].to_numpy(float)) | (f["M2v"].to_numpy(float) > 0),
             "E9": lambda: ge("M3", 1), "E10": lambda: ge("M4v", 0.90), "E11": lambda: le("M5v", 0.20),
             "E12": lambda: ge("W1", 1) & ge("M1", 1)}
    return np.asarray(table[rule](), bool)


def variant(df: pd.DataFrame, f: pd.DataFrame, cand: str, *, top: str | None = None, rule: str | None = None,
            e4_cut: float | None = None, member: pd.Series | None = None, masked: bool = False) -> pd.DataFrame:
    """一只票的指标表 → 候选（C1〜C5）；f = mtf.daily_frame（同一个日期索引）。C5 的买点按 member 掩码（masked=True 时）。"""
    out = df.copy(deep=False)
    if cand == "C1":
        strong = (f["W1"].to_numpy(float) == 1.0) & (f["W2"].to_numpy(float) == 1.0)
        below = (df["macd"] < df["macd_sig"]).to_numpy(bool)
        out["dead_cross"] = np.where(strong, f["E_X1"].to_numpy(bool), below)
    elif cand == "C2":
        out["dead_cross"] = f["E_X1"].to_numpy(bool)
    elif cand == "C3":
        out["dead_cross"] = df["dead_cross"].to_numpy(bool) | f[f"E_{top}"].to_numpy(bool)
    elif cand == "C4":
        out["entry"] = df["entry"].to_numpy(bool) & rule_keep(rule, f, e4_cut)
    elif cand == "C5":
        out["entry"] = f["E_B26"].to_numpy(bool) & (f["M1"].to_numpy(float) == 1.0)
        out["dead_cross"] = f["E_X1"].to_numpy(bool)
        if masked:
            out = PD.mask_entries(out, member)
    else:
        raise ValueError(cand)
    return out


# ────────────────────────── 逐笔统计与挑选 ──────────────────────────
def period(T: pd.DataFrame, a: str | None, b: str | None) -> pd.DataFrame:
    m = np.ones(len(T), bool)
    if a:
        m &= (T["sig_date"] >= pd.Timestamp(a)).to_numpy()
    if b:
        m &= (T["sig_date"] < pd.Timestamp(b)).to_numpy()
    return T[m]


def tstats(T: pd.DataFrame) -> dict:
    net = T["net"].to_numpy(float) if len(T) else np.array([])
    if not len(net):
        return {"n": 0, "win": None, "mean": None, "med": None, "pf": None, "hold": None}
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    return {"n": int(len(net)), "win": round(float((net > 0).mean() * 100), 2), "mean": round(float(net.mean()), 3),
            "med": round(float(np.median(net)), 3), "pf": round(float(pos / neg), 3) if neg > 0 else None,
            "hold": round(float(T["hold_days"].mean()), 1) if "hold_days" in T.columns else None}


def pick_top(rows: dict[str, dict], base: dict) -> str | None:
    """C3：验证期每笔平均 > 现行且胜率 ≥ 现行，取每笔平均最高的（一样取编号小的）。rows[k] / base = tstats（验证期）。"""
    ok = {k: r for k, r in rows.items() if r["n"] and r["mean"] is not None and base["mean"] is not None
          and r["mean"] > base["mean"] and r["win"] >= base["win"]}
    return max(ok, key=lambda k: (ok[k]["mean"], -int(k[1:]))) if ok else None


def pick_rule(rows: dict[str, dict]) -> str | None:
    """C4：保留 ≥ 50%、保留组胜率与每笔平均都高于被过滤组，取每笔平均差最大的（一样取编号小的）。rows[k] = {keep, kept, filt}（验证期）。"""
    ok = {}
    for k, r in rows.items():
        a, b = r["kept"], r["filt"]
        if r["keep"] >= KEEP_MIN and a["n"] and b["n"] and a["win"] > b["win"] and a["mean"] > b["mean"]:
            ok[k] = a["mean"] - b["mean"]
    return max(ok, key=lambda k: (ok[k], -int(k[1:]))) if ok else None


def r_fails(r: dict, base: dict) -> list[str]:
    """R：U0 全窗口 Calmar ≥ 现行、最大回撤不深 2 pp 以上、个股胜率不低 2 pp 以上。"""
    f = []
    a, b = r["all"], base["all"]
    if MS._c(a["calmar"]) < MS._c(b["calmar"]):
        f.append(f"U0 全窗口 Calmar {a['calmar']} < 现行 {b['calmar']}")
    if a["dd"] is None or b["dd"] is None or a["dd"] < b["dd"] - DD_TOL:
        f.append(f"U0 全窗口最大回撤 {a['dd']}% 比现行 {b['dd']}% 深 {DD_TOL} pp 以上")
    if r.get("win") is None or base.get("win") is None or r["win"] < base["win"] - WIN_TOL:
        f.append(f"U0 个股胜率 {r.get('win')}% 比现行 {base.get('win')}% 低 {WIN_TOL} pp 以上")
    return f


def yearly(eq: pd.Series, start: str = TRADE_START) -> dict[str, float]:
    e = eq.dropna()
    e = e[e.index >= pd.Timestamp(start)]
    if not len(e):
        return {}
    ye = e.groupby(e.index.year).last()
    prev = pd.concat([pd.Series([e.iloc[0]], index=[ye.index[0] - 1]), ye.iloc[:-1]])
    return {str(y): round(float(ye[y] / prev.iloc[k] - 1) * 100, 2) for k, y in enumerate(ye.index)}


# ────────────────────────── 组合（S0C2） ──────────────────────────
def make_runner(closes_all: pd.DataFrame, ratio: dict):
    """ml_study.make_runner 同一套 S0C2（var/sim.json → config_from_sim；一手按真实股价；退市日卖出），另外返回分期胜率与每年收益。"""
    from bullbear_study import SYM, load
    from unified_study import spx_jpy_on_jp_days
    import score_study as Z
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.config import DataConfig
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    from qbreak.fees import etf_cost
    from qbreak.macro import build_entry_mult, features_frame, load_macro_series
    from qbreak.regime import quant_regime_series
    from qbreak.trader import load_params
    from qbreak.unified import config_from_sim, exec_configs
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    cfg = config_from_sim(sim)
    broker = (sim.get("unified") or {}).get("broker", "tachibana")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    us = load_params(market="US")
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    core = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = exec_configs(("JP",), {"broker": broker})
    cc = {"1655.T": etf_cost(broker, "1655.T", "JP")}
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    qr = quant_regime_series(idx["JP"])
    em_cache: dict = {}

    def run(ind: dict, p) -> dict:
        names = list(ind)
        key = tuple(names)
        if key not in em_cache:
            g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
            M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")), use_sector=bool(flag("use_sector_tilt")),
                                    use_events=False, closes=closes_all.reindex(index=g, columns=names))
            M = M * qr.reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
            em_cache[key] = pd.DataFrame(M, index=g, columns=names)
        JS.RealLotEngine.RATIO, JS.RealLotEngine.LAST = ratio, []
        MS.MLEngine.EXIT = {}
        Z._PrioEngine.PRIO = None
        eng = MS.MLEngine({**ind, "1655.T": core}, cfg, {"JP": p, "US": us}, ex, cc, fx=fxdf[["Open", "Close"]],
                          entry_mult={"JP": em_cache[key]}, bear=bear)
        r = eng.run(start=TRADE_START)
        tr = r.trades[r.trades["reason"] != "end"]
        st = tr[tr["ticker"] != "1655.T"] if len(tr) else tr
        out = {**MS.stats(r.equity), "trades": int(len(st)), "years": yearly(r.equity)}
        if len(st):
            ed = pd.to_datetime(st["entry_date"])
            w = (st["pnl"] > 0).to_numpy()
            out["win"] = round(float(w.mean() * 100), 1)
            for k, (a, b) in (("win_va", VAL), ("win_ho", HOLD)):
                m = (ed >= pd.Timestamp(a)).to_numpy() & ((ed < pd.Timestamp(b)).to_numpy() if b else True)
                out[k] = round(float(w[m].mean() * 100), 1) if m.any() else None
            out["reasons"] = {str(k): int(v) for k, v in st["reason"].value_counts().items()}
            out["hold"] = round(float(st["hold_days"].mean()), 1)
        else:
            out.update({"win": None, "win_va": None, "win_ho": None, "reasons": {}, "hold": None})
        return out
    return run


# ────────────────────────── 主流程 ──────────────────────────
def load_all():
    from bullbear_study import SYM, load
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    D = PRS.load_data()
    cal = pd.DatetimeIndex(sorted(set().union(*[df.index for df in D["data"].values()])))
    days = cal[(cal >= pd.Timestamp(WINDOW[0])) & (cal <= pd.Timestamp(WINDOW[1]))]
    names, masks = {}, {}
    for u in ("U0", "U1", "U2"):
        names[u], masks[u] = PRS.universe_members(D, u, days)
    allt = sorted(set(names["U0"]) | set(names["U1"]) | set(names["U2"]))
    delist = PRS.delist_dates({t: D["data"][t] for t in allt})
    PRS.PitEngine.DELIST = delist
    p0 = load_params(market="JP")
    ic = load(*SYM["JP"])["Close"]
    ind = {t: compute_indicators(D["data"][t], p0, ic) for t in allt}
    mf = {t: mtf.daily_frame(D["data"][t], cal) for t in allt}
    return D, days, names, masks, delist, p0, ind, mf


def ind_for(ind: dict, names: dict, masks: dict, u: str) -> dict:
    return {t: (ind[t] if u == "U0" else PD.mask_entries(ind[t], masks[u][t])) for t in names[u]}


def build(ind_u: dict, mf: dict, cand: str, masks_u: dict | None, **kw) -> dict:
    return {t: variant(df, mf[t], cand, member=(masks_u or {}).get(t), masked=masks_u is not None, **kw) for t, df in ind_u.items()}


def attach(T: pd.DataFrame, mf: dict) -> pd.DataFrame:
    """每笔交易的信号日 → 那天收盘时已知的周 / 月线状态。"""
    cols = list(mtf.W_STATE) + list(mtf.M_STATE)
    vals = np.full((len(T), len(cols)), np.nan)
    for k, (t, d) in enumerate(zip(T["ticker"], T["sig_date"])):
        f = mf.get(t)
        if f is not None and d in f.index:
            vals[k] = f.loc[d, cols].to_numpy(float)
    return pd.concat([T.reset_index(drop=True), pd.DataFrame(vals, columns=cols)], axis=1)


def coverage(D, days, names, masks, delist, p0, ind, mf, t0) -> int:
    say(f"# 覆盖检查（登记前；不算任何特征与收益的关系）  用时 {time.time() - t0:.0f}s")
    say(f"股票：U0 {len(names['U0'])}、U1 {len(names['U1'])}、U2 {len(names['U2'])} 只；市场日 {len(days)} 天；退市 {len(delist)} 只")
    iu2 = ind_for(ind, names, masks, "U2")
    T = attach(PRS.indep_trades(iu2, p0, delist), mf)
    for lab, (a, b) in (("全期", (TRADE_START, None)), ("验证期", VAL), ("留出期", HOLD)):
        x = period(T, a, b)
        say(f"- U2 现行独立交易 {lab}：{len(x)} 笔；特征有值的比例 " + "、".join(
            f"{c} {np.isfinite(x[c].to_numpy(float)).mean() * 100:.0f}%" for c in list(mtf.W_STATE) + list(mtf.M_STATE)))
    ev = {k: int(sum(mf[t][f"E_{k}"].sum() for t in names["U2"])) for k in list(mtf.W_EVENT) + list(mtf.M_EVENT)}
    say("- U2 事件次数（全部日子，不看收益）：" + "、".join(f"{k} {v:,}" for k, v in ev.items()))
    c5 = build(iu2, mf, "C5", masks["U2"])
    say(f"- C5 周线突破买点（U2、成员日）：{int(sum(df['entry'].sum() for df in c5.values())):,} 个；现行日线买点 {int(sum(df['entry'].sum() for df in iu2.values())):,} 个")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true", help="只看股票只数、信号与交易笔数、特征覆盖率（登记前用）")
    a = ap.parse_args(argv)
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/mtf_study.py", "qbreak/mtf.py"],
                                capture_output=True, text=True).stdout.strip())
    D, days, names, masks, delist, p0, ind, mf = load_all()
    if a.coverage:
        return coverage(D, days, names, masks, delist, p0, ind, mf, t0)
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    out: dict = {"code": code, "dirty": dirty}
    say("# 多周期（日 / 周 / 月线）：上涨股票的特征与卖顶的特征（2026-09-27）")
    say("规则见 scripts/mtf_study.py 开头（先提交后运行）；原始数据只在 var/cache/jquants/，这里只有统计。研究路线图：RESEARCH_PLAN.md（R1）。")
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731

    # ── A 所有股票：日 × 周 × 月 状态 → 之后 20 日超额 ──
    nm = names["U2"]
    col = {t: j for j, t in enumerate(nm)}
    O = pd.DataFrame({t: D["data"][t]["Open"] for t in nm}).reindex(days).to_numpy(float)
    C = pd.DataFrame({t: D["data"][t]["Close"] for t in nm}).reindex(days)
    Cf = C.ffill(limit=5).to_numpy(float)
    dstate = (C > C.rolling(20, min_periods=20).mean()).where(C.rolling(20, min_periods=20).mean().notna())
    W1 = pd.DataFrame({t: mf[t]["W1"] for t in nm}).reindex(days)
    M1 = pd.DataFrame({t: mf[t]["M1"] for t in nm}).reindex(days)
    mem = pd.DataFrame({t: masks["U2"][t] for t in nm}).reindex(index=days).fillna(False).astype(bool)
    wk = MS.week_ends(days, TRADE_START)
    di = {d: i for i, d in enumerate(days)}
    n = len(days)
    rows_i, rows_c = np.nonzero(mem.reindex(index=wk).to_numpy(bool))
    ri = np.array([di[d] for d in wk])[rows_i]
    j1, j2 = ri + 1, ri + 1 + FWD_H
    ok = j2 < n
    p_in = np.where(ok, O[np.clip(j1, 0, n - 1), rows_c], np.nan)
    p_out = np.where(ok, MS.fwd_exit_price(O[np.clip(j2, 0, n - 1), rows_c], Cf[np.clip(j2, 0, n - 1), rows_c]), np.nan)
    r = np.log(p_out / p_in)
    dts = days[ri]
    fin = np.isfinite(r)
    ex = r - pd.Series(np.where(fin, r, np.nan)).groupby(dts).transform("mean").to_numpy()
    ds = dstate.to_numpy(float)[ri, rows_c]
    ws = W1.to_numpy(float)[ri, rows_c]
    ms = M1.to_numpy(float)[ri, rows_c]
    say("\n## A 所有股票：日 / 周 / 月三个周期的状态 → 之后 20 个交易日的超额收益（U2 成员，每周最后一个交易日；只描述）")
    say("| 日线 > 20 日线 | 周线 Stage 2 | 月线 > 10 月线 | 验证期 平均超额（95% 区间） | 验证期 超额 > 0 | 留出期 平均超额（95% 区间） | 留出期 超额 > 0 | 样本（验证 / 留出） |")
    say("|---|---|---|---|---|---|---|---|")
    out["A"] = {}
    for dv in (1.0, 0.0):
        for wv in (1.0, 0.0):
            for mv in (1.0, 0.0):
                sel = (ds == dv) & (ws == wv) & (ms == mv) & np.isfinite(ex)
                cells, rec = [], {}
                for lab, (a_, b_) in (("va", VAL), ("ho", HOLD)):
                    pm = sel & (dts >= pd.Timestamp(a_)) & ((dts < pd.Timestamp(b_)) if b_ else True)
                    if pm.sum() < 50:
                        cells += ["—", "—"]
                        rec[lab] = None
                        continue
                    s = pd.Series(ex[pm]).groupby(dts[pm]).mean()
                    mm, lo, hi = ml.block_boot_mean(s * 100, s.index.to_period("M").astype(str), n=N_BOOT, seed=SEED)
                    hit = float((ex[pm] > 0).mean() * 100)
                    cells += [f"{mm:+.2f}%（{lo:+.2f}〜{hi:+.2f}）", f"{hit:.1f}%"]
                    rec[lab] = {"mean": round(mm, 3), "lo": round(lo, 3), "hi": round(hi, 3), "hit": round(hit, 1), "n": int(pm.sum())}
                nva = rec["va"]["n"] if rec.get("va") else 0
                nho = rec["ho"]["n"] if rec.get("ho") else 0
                say(f"| {'↑' if dv else '↓'} | {'✓' if wv else '✗'} | {'✓' if mv else '✗'} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {nva:,} / {nho:,} |")
                out["A"][f"{int(dv)}{int(wv)}{int(mv)}"] = rec

    # ── B 现行买点：周 / 月线规则 ──
    iu2 = ind_for(ind, names, masks, "U2")
    T0 = attach(PRS.indep_trades(iu2, p0, delist), mf)
    Tva = period(T0, *VAL)
    e4_cut = float(np.nanmedian(Tva["W4v"].to_numpy(float)))
    out["e4_cut"] = round(e4_cut, 4)
    say(f"\n## B 现行买点（U2 独立突破交易 {len(T0):,} 笔：验证期 {len(Tva):,}、留出期 {len(period(T0, *HOLD)):,}）按周 / 月线规则分两组（只描述；C4 在验证期挑）")
    say(f"E4 的门槛 = 验证期现行交易 W4v 的中位数 {e4_cut:.3f}。每格 = 保留组 / 被过滤组；差 = 保留 − 过滤的每笔平均净收益（按信号月聚类 95% 区间）。")
    say("| 规则 | 保留比例（验证期） | 验证期 胜率 | 验证期 每笔平均 | 验证期 差（95% 区间） | 留出期 胜率 | 留出期 每笔平均 | 留出期 差（95% 区间） | 保留组更好的年数 |")
    say("|---|---|---|---|---|---|---|---|---|")
    out["B"] = {}
    brows = {}
    for k, lab in RULES.items():
        keep = rule_keep(k, T0, e4_cut)
        rec = {}
        cells = []
        for pl, (a_, b_) in (("va", VAL), ("ho", HOLD)):
            m = (T0["sig_date"] >= pd.Timestamp(a_)).to_numpy() & ((T0["sig_date"] < pd.Timestamp(b_)).to_numpy() if b_ else True)
            kept, filt = tstats(T0[m & keep]), tstats(T0[m & ~keep])
            d, lo, hi = PRS.month_boot(T0["net"].to_numpy(float)[m], keep[m], T0["month"].to_numpy()[m], n=N_BOOT, seed=SEED)
            rec[pl] = {"keep": round(float(keep[m].mean()), 3) if m.any() else None, "kept": kept, "filt": filt,
                       "diff": None if not np.isfinite(d) else round(d, 3), "lo": None if not np.isfinite(lo) else round(lo, 3),
                       "hi": None if not np.isfinite(hi) else round(hi, 3)}
            cells.append(rec[pl])
        yrs = 0
        ny = 0
        for y in range(2017, 2027):
            m = (T0["sig_date"].dt.year == y).to_numpy()
            a1, b1 = T0["net"].to_numpy(float)[m & keep], T0["net"].to_numpy(float)[m & ~keep]
            if len(a1) and len(b1):
                ny += 1
                yrs += int(a1.mean() > b1.mean())
        rec["years"] = f"{yrs} / {ny}"
        out["B"][k] = rec
        brows[k] = {"keep": rec["va"]["keep"] or 0.0, "kept": rec["va"]["kept"], "filt": rec["va"]["filt"]}
        va, ho = rec["va"], rec["ho"]
        say(f"| {k} {lab} | {fa(va['keep'] * 100 if va['keep'] is not None else None, '{:.0f}%')} | "
            f"{fa(va['kept']['win'], '{:.1f}%')} / {fa(va['filt']['win'], '{:.1f}%')} | {fa(va['kept']['mean'], '{:+.2f}%')} / {fa(va['filt']['mean'], '{:+.2f}%')} | "
            f"{fa(va['diff'], '{:+.2f}')}（{fa(va['lo'], '{:+.2f}')}〜{fa(va['hi'], '{:+.2f}')}） | "
            f"{fa(ho['kept']['win'], '{:.1f}%')} / {fa(ho['filt']['win'], '{:.1f}%')} | {fa(ho['kept']['mean'], '{:+.2f}%')} / {fa(ho['filt']['mean'], '{:+.2f}%')} | "
            f"{fa(ho['diff'], '{:+.2f}')}（{fa(ho['lo'], '{:+.2f}')}〜{fa(ho['hi'], '{:+.2f}')}） | {rec['years']} |")
    rule = pick_rule(brows)
    out["C4_rule"] = rule
    say(f"\n→ C4 用：{rule + ' ' + RULES[rule] if rule else '没有规则满足挑选条件 → C4 不跑'}")
    say("\n连续特征三分位（全部现行交易的三分位点；每格 = 胜率 / 每笔平均净收益）")
    say("| 特征 | 档 | 验证期 | 留出期 |")
    say("|---|---|---|---|")
    out["B_terc"] = {}
    names_c = {**mtf.W_STATE, **mtf.M_STATE}
    for c in CONT:
        v = T0[c].to_numpy(float)
        q = np.nanpercentile(v, [100 / 3, 200 / 3]) if np.isfinite(v).sum() >= 30 else None
        if q is None:
            continue
        for lab, m_ in (("低", v <= q[0]), ("中", (v > q[0]) & (v <= q[1])), ("高", v > q[1])):
            cell = {}
            for pl, (a_, b_) in (("va", VAL), ("ho", HOLD)):
                m = m_ & (T0["sig_date"] >= pd.Timestamp(a_)).to_numpy() & ((T0["sig_date"] < pd.Timestamp(b_)).to_numpy() if b_ else True)
                cell[pl] = tstats(T0[m])
            out["B_terc"][f"{c}|{lab}"] = {**cell, "cut": [round(float(q[0]), 4), round(float(q[1]), 4)]}
            say(f"| {c} {names_c[c]} | {lab}（{q[0]:.3f} / {q[1]:.3f}） | {fa(cell['va']['win'], '{:.1f}%')} / {fa(cell['va']['mean'], '{:+.2f}%')}（{cell['va']['n']}） | "
                f"{fa(cell['ho']['win'], '{:.1f}%')} / {fa(cell['ho']['mean'], '{:+.2f}%')}（{cell['ho']['n']}） |")

    # ── C 卖点：逐笔 ──
    say("\n## C 卖点（U2 独立交易；只描述，C3 在验证期挑）")
    say("| 出场 | 验证期 笔数 / 胜率 / 每笔平均 / 中位 / 盈亏比 / 平均持有 | 留出期 同左 |")
    say("|---|---|---|")
    out["C"] = {}
    cell = lambda s: f"{s['n']} / {fa(s['win'], '{:.1f}%')} / {fa(s['mean'], '{:+.2f}%')} / {fa(s['med'], '{:+.2f}%')} / {fa(s['pf'])} / {fa(s['hold'], '{:.1f}')} 天"   # noqa: E731
    base_va = tstats(Tva)
    xrows = {}
    exit_sets = [("现行", None)] + [(k, ("C3", {"top": k})) for k in TOPS] + [("C1", ("C1", {})), ("C2", ("C2", {})), ("C5", ("C5", {}))]
    for lab, spec in exit_sets:
        if spec is None:
            T = T0
        else:
            cand, kw = spec
            T = PRS.indep_trades(build(iu2, mf, cand, masks["U2"], **kw), p0, delist)
        sv, sh = tstats(period(T, *VAL)), tstats(period(T, *HOLD))
        out["C"][lab] = {"va": sv, "ho": sh}
        if lab in TOPS:
            xrows[lab] = sv
        name = {"现行": "现行（日线死叉等）", "C1": "C1 " + CANDS["C1"], "C2": "C2 " + CANDS["C2"], "C5": "C5 " + CANDS["C5"]}.get(
            lab, f"现行 + {lab} {({**mtf.W_EVENT, **mtf.M_EVENT})[lab]} 就卖")
        say(f"| {name} | {cell(sv)} | {cell(sh)} |")
    top = pick_top(xrows, base_va)
    out["C3_top"] = top
    say(f"\n→ C3 用：{top + ' ' + ({**mtf.W_EVENT, **mtf.M_EVENT})[top] if top else '没有见顶特征满足挑选条件 → C3 不跑'}")

    # ── 组合：U1（V / H）与 U0（R） ──
    runs = {}
    for u in ("U1", "U0"):
        closes = pd.DataFrame({t: D["data"][t]["Close"] for t in names[u]})
        run = make_runner(closes, D["ratio"])
        iu = ind_for(ind, names, masks, u)
        mk = masks[u] if u != "U0" else None
        res = {"现行": run(iu, p0)}
        for c in CANDS:
            if c == "C3" and not top:
                continue
            if c == "C4" and not rule:
                continue
            kw = {"top": top} if c == "C3" else ({"rule": rule, "e4_cut": e4_cut} if c == "C4" else {})
            res[c] = run(build(iu, mf, c, mk, **kw), p0)
        runs[u] = res
    out["U1"], out["U0"] = runs["U1"], runs["U0"]
    base1, base0 = runs["U1"]["现行"], runs["U0"]["现行"]
    fcell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"   # noqa: E731
    say("\n## 组合（S0C2 = var/sim.json 同一套设定、一手放宽关；各格 = 年化 / 最大回撤 / Calmar）")
    say("| 方案 | U1 全窗口 | U1 验证期 | U1 留出期 | 留出前半 | 留出后半 | U1 笔数 / 胜率（验证 / 留出） / 平均持有 | U0 全窗口 | U0 笔数 / 胜率 | V | H | R |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|")
    fails, passed = {}, {}
    for k in runs["U1"]:
        r1, r0 = runs["U1"][k], runs["U0"].get(k)
        if k == "现行":
            gv = gh = gr = "—"
        else:
            vf = MS.v_fails(r1, base1)
            hf = MS.h_fails(r1, base1) if not vf else None
            rf = r_fails(r0, base0) if (not vf and not hf) else None
            fails[k] = vf + (hf or []) + (rf or [])
            gv = "✗" if vf else "✓"
            gh = "—" if hf is None else ("✗" if hf else "✓")
            gr = "—" if rf is None else ("✗" if rf else "✓")
            if not vf and not hf and not rf:
                passed[k] = r1
        lab = k if k == "现行" else f"{k} {CANDS[k]}"
        say(f"| {lab} | {fcell(r1['all'])} | {fcell(r1['va'])} | {fcell(r1['ho'])} | {fcell(r1['h1'])} | {fcell(r1['h2'])} | "
            f"{r1['trades']} / {fa(r1.get('win_va'), '{:.1f}%')} / {fa(r1.get('win_ho'), '{:.1f}%')} / {fa(r1.get('hold'), '{:.1f}')} 天 | "
            f"{fcell(r0['all'])} | {r0['trades']} / {fa(r0.get('win'), '{:.1f}%')} | {gv} | {gh} | {gr} |")
    for k, f in fails.items():
        if f:
            say(f"- {k}：" + "；".join(f))
    say("\nU1 每年的收益（%，只描述）")
    yrs_all = sorted(set().union(*[set(r["years"]) for r in runs["U1"].values()]))
    say("| 方案 | " + " | ".join(yrs_all) + " | 比现行好的年数 |")
    say("|---|" + "---|" * (len(yrs_all) + 1))
    for k, r1 in runs["U1"].items():
        better = sum(1 for y in yrs_all if y in r1["years"] and y in base1["years"] and r1["years"][y] > base1["years"][y])
        say(f"| {k} | " + " | ".join(fa(r1["years"].get(y), "{:+.1f}") for y in yrs_all) + f" | {'—' if k == '现行' else f'{better} / {len(yrs_all)}'} |")
    best = MS.choose(passed) if passed else None
    out["passed"], out["proposal"] = list(passed), best
    if best:
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；改之前记进 sim_changes.md）。**"
            + (f"另外也通过的：{'、'.join(k for k in passed if k != best)}。" if len(passed) > 1 else ""))
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "mtf_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
