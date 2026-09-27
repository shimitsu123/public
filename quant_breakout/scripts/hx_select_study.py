"""hx_select_study.py — 选股信号的横展开：日本两期都成立的选股信号与它们的事先组合，在从没用来研究选股的美国个股上检验一次
（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-27）：「基于现在所有的研究结果 进行网罗结合进行提高选股概率和收益率的提高 还有提高威胁指数等等 进行横展开的精确度」。
来由（研究总图 var/out/research_map.md）：日本个股层约 40 项登记研究里，两个年代 / 三个窗口方向一致的选股信号只有四类 ——
  ① 周线量比（W2 = 最近完成的一周成交量 ÷ 之前 10 周平均 ≥ 1.0；wvol_study 通过、2026-09-27 启用）；
  ② 突破日量比（vr1 最高 1/5 两期都更好；「突破日 3 倍量」V1 / V3 逐笔两个年代 +1.3〜+1.6%，vthrust_study）；
  ③ 低 β（S5：对日経 β 低的略好；K2 = vr1 ≥ 2.0 ∧ β ≤ 0.70 三个窗口每笔 +1.2〜1.5 pp，但随机对照没过 → 前向记录）；
  ④ 股息率高（「质的飞跃」第 1 轮：逐笔两期一致，组合几乎不变）；
  ⑤ 与指数低相关（S7 探索：60 日日收益与日経的相关最低 1/3 的突破 E 49% / +1.66% vs 最高 1/3 31% / −0.03%，J 57% / +1.67% vs 37% / +0.03%；
    与 ③ 同一原理 =「个别驱动的突破」；只在探索里看过、没有登记检验）。
  组合的已知情况：S7 的合成分（量比、低 β、股息率、周线量比的秩平均取上半）E / J 都几乎没有提高（44% / +1.04%、46% / +0.91% vs 对照
  44.1% / +0.93%、44.8% / +0.73%）→ 事先就不看好「简单相加」，这一轮用固定门槛的投票（至少两条）再检验一次。
  日本的 Z / E / J 窗口都已经用来设计或检验过这些信号 → 再在日本上组合只会重复看过的数据。美国个股在本项目里只用过两次：
  ① 早期「美股个股层开 / 关」的组合决定（unified_study，没有测选股过滤）；② W2 的事后核对 scripts/wvol_us.py（美国大型股 109 只 =
  qbreak/universes.US_BROAD、美股参数：2006〜2016 保留 +0.31% vs 过滤 +0.91%，反过来，21 年里 8 年更好 → 美股上不成立）。
  → 主判定用「今天的 S&P 500 去掉 US_BROAD 的那 97 只」= 约 400 只从没用来研究任何选股信号的股票；那 97 只另报（W2 已看过）。
  这一轮只回答：日本得出的选股规则（阈值原样、日本参数的突破）在别的市场是不是也成立；成立的才考虑拿回日本（日本只作「不变差」检查）。

一 数据
  美国（主判定 = SP500X）：今天的 S&P 500 成分（var/us_constituents_2026-09.json，Wikipedia 2026-09-27；GOOG / FOX / NWS 只留一只）
    去掉 US_BROAD（W2 事后核对用过的 97 只）；只算「加入 S&P 500 之后」的信号（Date added；之前的上涨是幸存者偏差）；
    yfinance 27 年调整后日线（qbreak.data.load_universe，日本 E 窗口同一来源与口径；scripts/us_stock_data.py）；未复权收盘 + 每股分红；指数 ^GSPC。
  另报（只描述，不判定）：SEEN = S&P 500 里 US_BROAD 那 97 只；S&P 400（加入日已知的从加入日起，不明的从 2012-01-01 起；指数 ^MID）。
  信号窗口：信号日 2001-01-02 〜 2026-06-30；前半 A = 〜2013-12-31、后半 B = 2014-01-02〜。
二 基准交易：现行日本突破规则原样（qbreak.trader.load_params(market="JP")，去掉 W2 = score_forward.no_w2_params；阈值、离场都不为美国调整），
  每只票单独、一次一仓（qbreak.engine.run_backtest，美股执行设定：滑点每边 0.05%、跳空 > 3% 不进场，qbreak.fees 的 US 表），
  净收益 = 引擎毛收益 − 来回 0.15%（与日本 ¥25 万一笔的立花手续费同一比例，只为可比）；持仓到数据末尾没平仓的不算；
  数据检查：信号日前 5 天到平仓日之间有单日 |涨跌| > 60% 的（疑似未复权的拆股 / 合并）剔除并报笔数。P = 剩下的全部交易。
三 信号日特征（只用信号日收盘为止已知的数据）
  w5v 周线量比（qbreak/mtf.weekly_volume_ratio，该股自己的日历；W2 同一定义）；vr1 突破日量比（idio_forward.vr1_series：当天 ÷ 之前 20 日平均）；
  β：104 周周收益（±50% 截断）对 ^GSPC 周收益的回归斜率（leap2_s5_explore.rolling_betas，≥ 69 周；信号日所在周之前的周五为止，
  leap2_s6b_portfolio.daily_from_weekly；K2 在日本同一算法）；dy 股息率（过去 365 日每股分红 ÷ 未复权收盘，leap_data.div_yield 同一算法），
  dy_top = 当天已加入的 S&P 500 全部成分（S&P 400 另报时 = S&P 400 成分）里股息率排前 1/3（含不分红的 0）；
  corr60 = 信号日为止 60 个日收益与指数日收益的相关（≥ 40 对；leap2_s7_features 同一定义），corr_low = 当天已加入的全部成分里 corr60 排后 1/3；
  缺值 → 该条件不满足（W2 缺值 → 保留，同现行）。
四 候选（P 的保留规则；阈值 = 日本的数字原样）
  U1 W2 复现：w5v ≥ 1.0。基准 B = P。
  U2 K2 复现（放量 ∧ 低 β）：w5v ≥ 1.0 ∧ vr1 ≥ 2.0 ∧ β ≤ 0.70。基准 B = W2 保留组（= 现行）。
  U3 低相关（个别驱动）：w5v ≥ 1.0 ∧ corr_low。基准 = W2 保留组。
  U4 V1 复现（突破日 3 倍量）：w5v ≥ 1.0 ∧ vr1 ≥ 3.0。基准 = W2 保留组。
  U5 网罗组合（事先写定，不拟合）：w5v ≥ 1.0 ∧（vr1 ≥ 2.0、β ≤ 0.70、dy_top、corr_low 四条里至少两条）。基准 = W2 保留组。
五 判定（美国 SP500X；每个候选分别）
  G1 每笔净收益 ≥ 基准 + 0.5 pp（A、B 两半都要）；G2 胜率 ≥ 基准（两半都要）；
  G3 全窗口的每笔与胜率都 > 两种抽签对照的 95 分位：基准里按「年 × GICS 业种」分层、按「同一周」分层各随机保留与候选同样的笔数，各 1,000 次；
  G4 (候选 − 基准) 每笔的周聚类自助法（2,000 次）95% 区间下限 > 0（全窗口）；G5 两半的保留笔数都 ≥ 150。
  全过 = 美国横展开成立。
  成立的 U2〜U5 才做日本「不变差」检查（Z / E / J 三个窗口，leap_confirm 同一套组合 runner，现行 = W2 · 日経225）：
    Calmar ≥ 现行 − 0.02、最大回撤不比现行深 2 pp 以上、组合里个股每笔 ≥ 现行、个股笔数 ≥ 现行的 30%（leap2_common S3 / S4 口径）
    → 三个窗口都满足 = 提议（模拟盘 / 执行器用户确认才改）+ 前向记录（K2 已在记录里；其余用户同意再登记）。
  U1 不成立 → 只记录（W2 已按登记通过、前向记录照常；失效警报按 W2 前向记录自己的规则），不改。
六 另报（只描述，不判定）：单项（vr1 ≥ 2、vr1 ≥ 3、β ≤ 0.70、dy_top、corr_low）在 P 与 W2 保留组里的保留 − 剔除；各特征与「赢」的 AUC、
  特征之间的秩相关（组合能提高多少的上限）；按年；SEEN 与 S&P 400 同一张表；日本已知的对应数字（研究总图）。
七 事前预期（写死）：U1（W2）在美国大型股的事后核对已经反过来 → 这一轮成立约 15%；U2 两半都 ≥ 150 笔的可能约 40%（低 β 在美国大盘股里少），
  成立约 15%；U3（低相关，日本两个年代差 17〜21 pp）成立约 25%；U4 每笔更好的可能约 60%，但 G3 同周抽签能过的约 30%、成立约 20%；
  U5（日本的秩平均已经没用）成立约 10%；全部不成立约 50%。
八 局限：今天的成分 + 加入日之后（没有被剔除的股票 → 仍有幸存者偏差，候选与基准同样有）；突破规则是为日本调的（只比较保留 vs 基准，
  不比较美日水平）；美股没有决算日数据 → 不做决算前 2 日不进场；股息率用 Yahoo 分红（特别分红也算）；GICS 业种是今天的分类。
输出：var/out/hx_select_study.md / .json（只有统计）
"""
from __future__ import annotations

import argparse
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
import us_stock_data as UD                                                   # noqa: E402
from qbreak import paths                                                     # noqa: E402

WIN0, WIN1, HALF_B0 = pd.Timestamp("2001-01-02"), pd.Timestamp("2026-06-30"), pd.Timestamp("2014-01-01")
S400_UNKNOWN_START = pd.Timestamp("2012-01-01")
RT_PCT = 0.15                                   # 来回成本（%），与日本 ¥25 万一笔的立花手续费同一比例
BAD_MOVE = 0.60                                 # 数据检查：单日 |涨跌| > 60%
W2_CUT, K_VR, K_BETA, V1_VR, DY_TOP = 1.0, 2.0, 0.70, 3.0, 2 / 3
G1_PP, MIN_N_HALF, LOT_REPS, BOOT_REPS, SEED, Q = 0.5, 150, 1000, 2000, 20260927, 95
JP_CALMAR_TOL, JP_DD_TOL, JP_MIN_FRAC = 0.02, 2.0, 0.30
CANDS = {"U1": "W2 复现：周线量比 ≥ 1.0", "U2": "K2 复现：W2 ∧ 突破日量比 ≥ 2.0 ∧ β ≤ 0.70",
         "U3": "低相关：W2 ∧ 60 日与指数相关排后 1/3", "U4": "V1 复现：W2 ∧ 突破日量比 ≥ 3.0",
         "U5": "网罗组合：W2 ∧（量比 ≥ 2.0、β ≤ 0.70、股息率前 1/3、低相关 至少两条）"}
BASE_OF = {"U1": "P", "U2": "W2", "U3": "W2", "U4": "W2", "U5": "W2"}
SINGLES = {"vr2": "突破日量比 ≥ 2.0", "vr3": "突破日量比 ≥ 3.0", "lowb": "β ≤ 0.70", "dytop": "股息率前 1/3", "corrlow": "低相关后 1/3"}
CORR_LOW, CORR_N, CORR_MIN = 1 / 3, 60, 40
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def _f(s: dict) -> str:
    if not s or not s.get("n"):
        return "n=0"
    return f"n={s['n']} 胜率 {s['win']:.1f}% 每笔 {s['mean']:+.2f}%"


# ───────────────────────── 数据 ─────────────────────────
def pool_members(pool: str) -> tuple[dict[str, pd.Timestamp], dict[str, str]]:
    """{票: 开始算信号的日子}、{票: GICS 业种}。pool：sp500x（主判定 = S&P 500 去掉 US_BROAD）/ sp500seen（US_BROAD 那 97 只）/
    sp500（全部，股息率排名用）/ sp400。S&P 500 = 加入日；S&P 400 = 加入日（已知）或 2012-01-01（不明）。"""
    from qbreak.universes import US_BROAD
    seen = set(US_BROAD)
    src = "sp400" if pool == "sp400" else "sp500"
    c = UD.constituents()
    names = set(UD.names(src))
    start, sector = {}, {}
    for r in c[src]:
        t = r["ticker"]
        if t not in names or (pool == "sp500x" and t in seen) or (pool == "sp500seen" and t not in seen):
            continue
        da = pd.Timestamp(r["date_added"]) if r.get("date_added") else (S400_UNKNOWN_START if src == "sp400" else None)
        if da is None:
            continue
        start[t] = max(da, WIN0)
        sector[t] = r["sector"]
    return start, sector


def load_pool(pool: str) -> dict:
    start, sector = pool_members(pool)
    rank_start, _ = pool_members("sp400" if pool == "sp400" else "sp500")
    idx_sym = UD.INDEXES["sp400" if pool == "sp400" else "sp500"]
    data = UD.ohlcv(list(start) + [idx_sym])
    idx = data.pop(idx_sym)["Close"]
    data = {t: df[["Open", "High", "Low", "Close", "Volume"]] for t, df in data.items() if t in start and len(df) >= 300}
    return {"pool": pool, "data": data, "index": idx, "start": {t: start[t] for t in data}, "sector": {t: sector[t] for t in data},
            "rank_start": rank_start}


def base_params():
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    return SF.no_w2_params(load_params(market="JP"))


def us_trades(D: dict, p0) -> pd.DataFrame:
    """每只票单独、一次一仓；交易窗口从该票的开始日起；没平仓的不算；信号日 ≤ WIN1。"""
    from qbreak.config import BacktestConfig
    from qbreak.engine import run_backtest
    from qbreak.strategy import compute_indicators
    bt = BacktestConfig.for_market("US", 27)
    bt.exec_cfg.commission_pct, bt.exec_cfg.commission_max = 0.0, 0.0                 # 手续费另外按 RT_PCT 扣
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rows = []
    for t, df in D["data"].items():
        ind = compute_indicators(df, p0, None)
        if not ind["entry"].any():
            continue
        try:
            r = run_backtest({t: ind}, p0, bt, start=D["start"][t])
        except ValueError:
            continue
        tr = r.trades
        if not len(tr):
            continue
        tr = tr[tr["reason"] != "end"].copy()
        if not len(tr):
            continue
        tr["ticker"] = t
        ent = pd.to_datetime(tr["entry_date"])
        tr["sig_date"] = [df.index[max(0, df.index.searchsorted(e) - 1)] for e in ent]
        tr["exit_date"] = pd.to_datetime(tr["exit_date"])
        rows.append(tr[["ticker", "sig_date", "entry_date", "exit_date", "ret_pct", "reason"]])
    T = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ticker", "sig_date", "entry_date", "exit_date", "ret_pct", "reason"])
    st = T["ticker"].map(D["start"])
    T = T[(T["sig_date"] >= st) & (T["sig_date"] >= WIN0) & (T["sig_date"] <= WIN1)].reset_index(drop=True)   # 信号日在加入日之后
    T["net"] = T["ret_pct"].astype(float) - RT_PCT
    T["win"] = T["net"] > 0
    return T


def bad_move_flags(T: pd.DataFrame, D: dict) -> np.ndarray:
    """信号日前 5 个交易日到平仓日之间，有没有单日 |收盘涨跌| > BAD_MOVE。"""
    out = np.zeros(len(T), bool)
    for t, g in T.groupby("ticker"):
        c = D["data"][t]["Close"]
        r = c.pct_change().abs().to_numpy(float)
        bad = np.flatnonzero(r > BAD_MOVE)
        if not len(bad):
            continue
        di = c.index
        for i, (s, e) in zip(g.index, zip(g["sig_date"], g["exit_date"])):
            a = max(0, int(di.searchsorted(s)) - 5)
            b = int(di.searchsorted(e, side="right"))
            out[i] = bool(((bad >= a) & (bad < b)).any())
    return out


def corr60_frame(C: pd.DataFrame, mkt_close: pd.Series) -> pd.DataFrame:
    """每只票每天：到当天为止 60 个日收益与指数日收益的相关（≥ 40 对；leap2_s7_features.corr60 同一定义，按该票自己的交易日）。"""
    out = {}
    for t in C.columns:
        c = C[t].dropna()
        r = c.pct_change()
        m = mkt_close.reindex(c.index).pct_change()
        ok = r.notna() & m.notna()
        out[t] = r.where(ok).rolling(CORR_N, min_periods=CORR_MIN).corr(m.where(ok))
    return pd.DataFrame(out)


def corr_panel(D: dict, days: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """corr60（日期 × 票）与它在当天已加入的全部成分里的百分位（排名范围同股息率：D["rank_start"]）。"""
    import us_stock_data as UD2
    rk = D["rank_start"]
    extra = [t for t in rk if t not in D["data"]]
    data = dict(D["data"])
    if extra:
        more = UD2.ohlcv(extra)
        data.update({t: df for t, df in more.items() if len(df)})
    C = pd.DataFrame({t: data[t]["Close"] for t in rk if t in data}).sort_index()
    CR = corr60_frame(C, D["index"]).reindex(days)
    mem = pd.DataFrame({t: days >= rk[t] for t in CR.columns}, index=days)
    return CR, CR.where(mem).rank(axis=1, pct=True)


def attach_features(T: pd.DataFrame, D: dict) -> pd.DataFrame:
    """w5v、vr1、β、dy、dy_rank（当天已加入成分里的百分位）、业种、年、周。"""
    from leap2_s5_explore import rolling_betas, weekly
    from leap2_s6b_portfolio import daily_from_weekly
    from leap_data import div_yield
    from qbreak import idio_forward as IF
    from qbreak import mtf
    T = T.copy()
    names = list(D["data"])
    C = pd.DataFrame({t: D["data"][t]["Close"] for t in names}).sort_index()
    Yw = C.resample("W-FRI").last().pct_change(fill_method=None).clip(-0.5, 0.5)
    X = pd.DataFrame({"mkt": weekly(D["index"]).pct_change()}).reindex(Yw.index)
    Bw = rolling_betas(Yw, X[["mkt"]], None)["mkt"]
    days = C.index
    rk = D["rank_start"]                                                     # 股息率排名的范围 = 当天已加入的全部成分
    dy = {}
    for t in rk:
        try:
            dy[t] = div_yield(UD.actions(t), days)
        except Exception:                                                    # noqa: BLE001
            dy[t] = pd.Series(np.nan, index=days)
    DY = pd.DataFrame(dy).reindex(days)
    mem = pd.DataFrame({t: days >= rk[t] for t in DY.columns}, index=days)
    R = DY.where(mem).rank(axis=1, pct=True)
    CR, CRr = corr_panel(D, days)
    w5v, vr1, beta, dyv, dyr, cv, cr = (np.full(len(T), np.nan) for _ in range(7))
    for t, g in T.groupby("ticker"):
        df = D["data"][t]
        s_w = mtf.weekly_volume_ratio(df, df.index)
        s_v = IF.vr1_series(df)
        b = pd.Series(daily_from_weekly(Bw, t, df.index), index=df.index)
        sd = pd.DatetimeIndex(g["sig_date"])
        w5v[g.index] = s_w.reindex(sd).to_numpy(float)
        vr1[g.index] = s_v.reindex(sd).to_numpy(float)
        beta[g.index] = b.reindex(sd).to_numpy(float)
        dyv[g.index] = DY[t].reindex(sd).to_numpy(float) if t in DY else np.nan
        dyr[g.index] = R[t].reindex(sd).to_numpy(float) if t in R else np.nan
        cv[g.index] = CR[t].reindex(sd).to_numpy(float) if t in CR else np.nan
        cr[g.index] = CRr[t].reindex(sd).to_numpy(float) if t in CRr else np.nan
    T["w5v"], T["vr1"], T["beta"], T["dy"], T["dy_rank"], T["corr60"], T["corr_rank"] = w5v, vr1, beta, dyv, dyr, cv, cr
    T["sector"] = [D["sector"][t] for t in T["ticker"]]
    T["year"] = T["sig_date"].dt.year
    T["week"] = T["sig_date"].dt.to_period("W-FRI").astype(str)
    return T


# ───────────────────────── 保留规则 ─────────────────────────
def keep_masks(T: pd.DataFrame) -> dict[str, np.ndarray]:
    w = T["w5v"].to_numpy(float)
    v = T["vr1"].to_numpy(float)
    b = T["beta"].to_numpy(float)
    r = T["dy_rank"].to_numpy(float)
    cr = T["corr_rank"].to_numpy(float) if "corr_rank" in T else np.full(len(T), np.nan)
    W2 = ~(w < W2_CUT)                                                       # 缺值 → 保留（同现行）
    vr2 = np.nan_to_num(v, nan=-np.inf) >= K_VR
    vr3 = np.nan_to_num(v, nan=-np.inf) >= V1_VR
    lowb = np.nan_to_num(b, nan=np.inf) <= K_BETA
    dyt = np.nan_to_num(r, nan=-np.inf) >= DY_TOP
    clo = np.nan_to_num(cr, nan=np.inf) <= CORR_LOW
    votes = vr2.astype(int) + lowb.astype(int) + dyt.astype(int) + clo.astype(int)
    return {"P": np.ones(len(T), bool), "W2": W2, "U1": W2, "U2": W2 & vr2 & lowb, "U3": W2 & clo, "U4": W2 & vr3,
            "U5": W2 & (votes >= 2), "vr2": vr2, "vr3": vr3, "lowb": lowb, "dytop": dyt, "corrlow": clo}


def stats(T: pd.DataFrame, m: np.ndarray) -> dict:
    x = T["net"].to_numpy(float)[m]
    if not len(x):
        return {"n": 0, "win": None, "mean": None}
    return {"n": int(len(x)), "win": round(float((x > 0).mean() * 100), 2), "mean": round(float(x.mean()), 3)}


def lottery(T: pd.DataFrame, base: np.ndarray, keep: np.ndarray, strata: np.ndarray, reps: int = LOT_REPS, seed: int = SEED) -> dict:
    """基准里按层随机保留与候选同样的笔数（每层 = 候选在该层的保留数）→ 每次的每笔与胜率。"""
    rng = np.random.default_rng(seed)
    bi = np.flatnonzero(base)
    st = strata[bi]
    codes, inv = np.unique(st, return_inverse=True)
    k_per = np.bincount(inv, weights=keep[bi].astype(float), minlength=len(codes)).astype(int)
    net = T["net"].to_numpy(float)[bi]
    order0 = np.argsort(inv, kind="mergesort")
    starts = np.r_[0, np.cumsum(np.bincount(inv, minlength=len(codes)))[:-1]]
    means, wins = np.empty(reps), np.empty(reps)
    for r in range(reps):
        key = rng.random(len(bi))
        o = np.lexsort((key, inv))                                           # 先按层、层内随机
        rank = np.empty(len(bi), int)
        rank[o] = np.arange(len(bi)) - starts[inv[o]]
        sel = rank < k_per[inv]
        x = net[sel]
        means[r], wins[r] = (x.mean(), (x > 0).mean() * 100) if len(x) else (np.nan, np.nan)
    del order0
    return {"mean": means, "win": wins}


def boot_diff_lo(T: pd.DataFrame, base: np.ndarray, keep: np.ndarray, reps: int = BOOT_REPS, seed: int = SEED) -> float | None:
    """(候选 − 基准) 每笔的周聚类自助法 2.5% 分位（周 = 信号日所在周）。"""
    wk = T["week"].to_numpy()
    codes, inv = np.unique(wk[base], return_inverse=True)
    net = T["net"].to_numpy(float)[base]
    kp = keep[base]
    nw = len(codes)
    sb, nb = np.bincount(inv, weights=net, minlength=nw), np.bincount(inv, minlength=nw).astype(float)
    sk, nk = np.bincount(inv, weights=net * kp, minlength=nw), np.bincount(inv, weights=kp.astype(float), minlength=nw)
    rng = np.random.default_rng(seed)
    d = np.full(reps, np.nan)
    for r in range(reps):
        c = np.bincount(rng.integers(0, nw, nw), minlength=nw).astype(float)
        if (c * nk).sum() > 0 and (c * nb).sum() > 0:
            d[r] = (c * sk).sum() / (c * nk).sum() - (c * sb).sum() / (c * nb).sum()
    d = d[np.isfinite(d)]
    return float(np.quantile(d, 0.025)) if len(d) else None


def gate(T: pd.DataFrame, M: dict, cid: str) -> dict:
    base, keep = M[BASE_OF[cid]], M[cid]
    halfA = (T["sig_date"] < HALF_B0).to_numpy()
    res = {"base": BASE_OF[cid], "all": {"cand": stats(T, keep), "base": stats(T, base), "excl": stats(T, base & ~keep)}}
    for h, hm in (("A", halfA), ("B", ~halfA)):
        res[h] = {"cand": stats(T, keep & hm), "base": stats(T, base & hm)}
    ys = (T["year"].astype(str) + "|" + T["sector"]).to_numpy()
    wk = T["week"].to_numpy()
    lot = {"年×业种": lottery(T, base, keep, ys, seed=SEED), "同周": lottery(T, base, keep, wk, seed=SEED + 1)}
    res["lottery_q"] = {k: {"mean": float(np.nanpercentile(v["mean"], Q)), "win": float(np.nanpercentile(v["win"], Q))} for k, v in lot.items()}
    res["diff_lo"] = boot_diff_lo(T, base, keep)
    c = res["all"]["cand"]
    fails = []
    for h in ("A", "B"):
        a, b = res[h]["cand"], res[h]["base"]
        if not (a["n"] and b["n"] and a["mean"] >= b["mean"] + G1_PP):
            fails.append(f"G1 {h} 每笔 {a['mean'] if a['n'] else float('nan'):+.2f}% < 基准 {b['mean'] if b['n'] else float('nan'):+.2f}% + {G1_PP} pp")
        if not (a["n"] and b["n"] and a["win"] >= b["win"]):
            fails.append(f"G2 {h} 胜率 {a['win'] if a['n'] else float('nan'):.1f}% < 基准 {b['win'] if b['n'] else float('nan'):.1f}%")
        if not a["n"] >= MIN_N_HALF:
            fails.append(f"G5 {h} 笔数 {a['n']} < {MIN_N_HALF}")
    for k, q in res["lottery_q"].items():
        if not (c["n"] and c["mean"] > q["mean"]):
            fails.append(f"G3 每笔 ≤ {k}抽签 {Q} 分位 {q['mean']:+.2f}%")
        if not (c["n"] and c["win"] > q["win"]):
            fails.append(f"G3 胜率 ≤ {k}抽签 {Q} 分位 {q['win']:.1f}%")
    if not (res["diff_lo"] is not None and res["diff_lo"] > 0):
        fails.append(f"G4 (候选 − 基准) 区间下限 {res['diff_lo'] if res['diff_lo'] is not None else float('nan'):+.2f} pp ≤ 0")
    res["fails"] = fails
    res["pass"] = not fails
    return res


def auc(score: np.ndarray, y: np.ndarray) -> float | None:
    from qbreak.weights import auc_np
    return auc_np(score, y.astype(float))


def describe(T: pd.DataFrame, M: dict) -> dict:
    """单项的保留 − 剔除（P 与 W2 里）、特征与赢的 AUC、特征秩相关、按年。"""
    out = {"singles": {}, "auc": {}, "corr": {}, "by_year": {}}
    for k in SINGLES:
        for bname in ("P", "W2"):
            b = M[bname]
            out["singles"][f"{k}|{bname}"] = {"keep": stats(T, b & M[k]), "drop": stats(T, b & ~M[k])}
    y = T["win"].to_numpy()
    feats = {"w5v": T["w5v"].to_numpy(float), "vr1": T["vr1"].to_numpy(float), "neg_beta": -T["beta"].to_numpy(float),
             "dy_rank": T["dy_rank"].to_numpy(float), "neg_corr": -T["corr60"].to_numpy(float)}
    for k, v in feats.items():
        out["auc"][k] = auc(v, y)
    fr = pd.DataFrame(feats).rank()
    cm = fr.corr()
    out["corr"] = {f"{a}~{b}": round(float(cm.at[a, b]), 3) for i, a in enumerate(cm.columns) for b in cm.columns[i + 1:]}
    for yr, g in T.groupby("year"):
        idx = g.index.to_numpy()
        m = np.zeros(len(T), bool)
        m[idx] = True
        out["by_year"][int(yr)] = {k: stats(T, m & M[k]) for k in ("P", "W2", "U2", "U3", "U4", "U5")}
    return out


# ───────────────────────── 日本「不变差」检查（只对美国成立的 U2〜U4）─────────────────────────
def jp_check(cids: list[str], dummy: bool = False) -> dict:
    """日本 Z / E / J 三个窗口（leap_confirm 同一套组合 runner，今天的日経225）：现行 = W2；候选 = W2 ∧ 条件。
    dummy=True（只给冒烟测试用）：候选的条件换成「全部保留」（= 现行），只验证流程跑得通、不看任何候选的结果。"""
    import leap_confirm as LF
    from bullbear_study import load as idx_load
    from leap2_s6b_portfolio import daily_from_weekly, weekly_betas
    from leap_data import actions, div_yield
    from leap_r11_explore import vr1
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    p = load_params(market="JP")
    B = weekly_betas(list(universe("JP", "broad")))
    n225 = idx_load("^N225", "1998-01-01")["Close"]
    out = {}
    for era in ("Z", "E", "J"):
        ctx = LF.context(era)
        fa = LF.frames(ctx, SF.no_w2_params(p))
        run_fn = LF.runner(ctx, fa)
        w2 = LF.w2_keep(ctx, fa)
        res = {"现行": LF.run(ctx, run_fn, LF.with_mask(fa, w2), p)}
        vr = {t: vr1(df) for t, df in fa.items()}
        beta = {t: daily_from_weekly(B["b_n225"], t, df.index) for t, df in fa.items()}
        days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in fa.values()])))
        DY = pd.DataFrame({t: div_yield(actions(t), days) for t in fa}).reindex(days)
        R = DY.rank(axis=1, pct=True)
        C = pd.DataFrame({t: df["Close"] for t, df in fa.items()}).reindex(days)
        CRr = corr60_frame(C, n225).reindex(days).rank(axis=1, pct=True)
        for cid in cids:
            keep = {}
            for t, df in fa.items():
                v2 = np.nan_to_num(vr[t], nan=-np.inf) >= K_VR
                v3 = np.nan_to_num(vr[t], nan=-np.inf) >= V1_VR
                lb = np.nan_to_num(beta[t], nan=np.inf) <= K_BETA
                dt = np.nan_to_num(R[t].reindex(df.index).to_numpy(float), nan=-np.inf) >= DY_TOP
                cl = np.nan_to_num(CRr[t].reindex(df.index).to_numpy(float), nan=np.inf) <= CORR_LOW
                votes = v2.astype(int) + lb.astype(int) + dt.astype(int) + cl.astype(int)
                k = {"U2": v2 & lb, "U3": cl, "U4": v3, "U5": votes >= 2}[cid]
                keep[t] = w2[t] & (np.ones(len(df), bool) if dummy else k)
            res[cid] = LF.run(ctx, run_fn, LF.with_mask(fa, keep), p)
        out[era] = res
    verdict = {}
    for cid in cids:
        fails = []
        for era in ("Z", "E", "J"):
            c, b = out[era][cid][era], out[era]["现行"][era]
            cal, cal0 = c.get("calmar"), b.get("calmar")
            if not (cal is not None and cal0 is not None and cal >= cal0 - JP_CALMAR_TOL):
                fails.append(f"{era} Calmar {cal} < 现行 {cal0} − {JP_CALMAR_TOL}")
            if not (c.get("dd") is not None and b.get("dd") is not None and c["dd"] >= b["dd"] - JP_DD_TOL):
                fails.append(f"{era} 回撤 {c.get('dd')} 比现行 {b.get('dd')} 深 {JP_DD_TOL} pp 以上")
            if not (c.get("mean") is not None and b.get("mean") is not None and c["mean"] >= b["mean"]):
                fails.append(f"{era} 个股每笔 {c.get('mean')} < 现行 {b.get('mean')}")
            if not ((c.get("n") or 0) >= JP_MIN_FRAC * (b.get("n") or 0)):
                fails.append(f"{era} 个股笔数 {c.get('n')} < 现行 {b.get('n')} 的 {JP_MIN_FRAC:.0%}")
        verdict[cid] = fails
    return {"windows": {era: {k: {w: v for w, v in r.items() if not str(w).startswith("_")} for k, r in res.items()} for era, res in out.items()},
            "fails": verdict}


def git_info() -> dict:
    root = paths.PROJECT_ROOT
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "scripts", "qbreak"],
                                    capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return {"rev": rev, "dirty": dirty}


def run_pool(pool: str, p0, judge_it: bool) -> dict:
    t0 = time.time()
    D = load_pool(pool)
    T = us_trades(D, p0)
    bad = bad_move_flags(T, D)
    n_all = len(T)
    T = T[~bad].reset_index(drop=True)
    T = attach_features(T, D)
    M = keep_masks(T)
    say(f"\n## {pool.upper()}：{len(D['data'])} 只；交易 {n_all} 笔，数据检查剔除 {int(bad.sum())} 笔 → P {len(T)} 笔；"
        f"W2 保留 {int(M['W2'].sum())}（{M['W2'].mean() * 100:.1f}%）；{time.time() - t0:.0f}s")
    say(f"- P：{_f(stats(T, M['P']))}；W2：{_f(stats(T, M['W2']))}；W2 剔除：{_f(stats(T, ~M['W2']))}")
    out = {"n_names": len(D["data"]), "n_trades_raw": n_all, "n_bad": int(bad.sum()), "P": stats(T, M["P"]), "W2": stats(T, M["W2"]),
           "keep_frac": {k: round(float(M[k].mean()), 4) for k in list(CANDS) + list(SINGLES)}}
    if judge_it:
        out["gates"] = {}
        for cid in CANDS:
            g = gate(T, M, cid)
            out["gates"][cid] = g
            say(f"\n### {cid} {CANDS[cid]}（基准 = {'全部突破 P' if g['base'] == 'P' else 'W2 保留组（现行）'}）")
            say(f"- 全窗口：候选 {_f(g['all']['cand'])}；基准 {_f(g['all']['base'])}；剔除 {_f(g['all']['excl'])}")
            say(f"- A 2001〜2013：候选 {_f(g['A']['cand'])}；基准 {_f(g['A']['base'])}")
            say(f"- B 2014〜2026-06：候选 {_f(g['B']['cand'])}；基准 {_f(g['B']['base'])}")
            say("- 抽签对照 95 分位：" + "；".join(f"{k} 每笔 {v['mean']:+.2f}% 胜率 {v['win']:.1f}%" for k, v in g["lottery_q"].items())
                + f"；(候选 − 基准) 周聚类 95% 下限 {g['diff_lo'] if g['diff_lo'] is not None else float('nan'):+.2f} pp")
            say(f"- 判定：{'美国横展开成立' if g['pass'] else '不成立：' + '；'.join(g['fails'])}")
    else:
        halfA = (T["sig_date"] < HALF_B0).to_numpy()
        out["desc"] = {cid: {"all": stats(T, M[cid]), "base": stats(T, M[BASE_OF[cid]]), "A": stats(T, M[cid] & halfA),
                             "B": stats(T, M[cid] & ~halfA)} for cid in CANDS}
        for cid in CANDS:
            x = out["desc"][cid]
            say(f"- {cid}：候选 {_f(x['all'])}；基准 {_f(x['base'])}；A {_f(x['A'])}；B {_f(x['B'])}")
    ds = describe(T, M)
    out["describe"] = ds
    say("\n单项（保留 vs 剔除）：" + "；".join(f"{SINGLES[k.split('|')[0]]}［{k.split('|')[1]}］ {_f(v['keep'])} vs {_f(v['drop'])}"
                                    for k, v in ds["singles"].items()))
    say("特征与「赢」的 AUC：" + "、".join(f"{k} {v:.3f}" if v is not None else f"{k} —" for k, v in ds["auc"].items())
        + "；特征秩相关：" + "、".join(f"{k} {v:+.2f}" for k, v in ds["corr"].items()))
    say("按年（P / W2 / U3 / U5 每笔）：" + "；".join(
        f"{y} {v['P']['n']}笔 " + " / ".join(f"{v[k]['mean'] if v[k]['n'] else 0:+.2f}%" for k in ("P", "W2", "U3", "U5"))
        for y, v in ds["by_year"].items()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true", help="登记前核对：只报笔数、保留比例与特征缺值（不看收益）")
    ap.add_argument("--skip-jp", action="store_true")
    ap.add_argument("--jp-smoke", action="store_true", help="只验证日本检查的流程（候选条件换成全部保留 = 现行，不看任何候选结果）")
    a = ap.parse_args()
    t0 = time.time()
    gi = git_info()
    p0 = base_params()
    if a.jp_smoke:
        r = jp_check(["U3"], dummy=True)
        for era, res in r["windows"].items():
            a0, a1 = res["现行"][era], res["U3"][era]
            same = all(a0.get(k) == a1.get(k) for k in ("calmar", "dd", "n", "mean"))
            print(f"{era}：现行 n={a0.get('n')} Calmar={a0.get('calmar')}；冒烟（= 现行）{'一致' if same else '不一致！'}")
        return 0
    if a.counts:
        D = load_pool("sp500x")
        T = us_trades(D, p0)
        bad = bad_move_flags(T, D)
        T = attach_features(T[~bad].reset_index(drop=True), D)
        M = keep_masks(T)
        halfA = (T["sig_date"] < HALF_B0).to_numpy()
        print(f"SP500X：{len(D['data'])} 只；交易 {len(bad)}，剔除 {int(bad.sum())}；P {len(T)}（A {int(halfA.sum())} / B {int((~halfA).sum())}）")
        print("缺值率：" + "、".join(f"{c} {T[c].isna().mean() * 100:.1f}%" for c in ("w5v", "vr1", "beta", "dy", "dy_rank", "corr60", "corr_rank")))
        for k in list(CANDS) + list(SINGLES):
            print(f"  {k}：保留 {int(M[k].sum())}（{M[k].mean() * 100:.1f}%；A {int((M[k] & halfA).sum())} / B {int((M[k] & ~halfA).sum())}）")
        return 0
    say(f"# 选股信号的横展开（美国个股）（{pd.Timestamp.today().date()}；git {gi['rev']}{'（脏）' if gi['dirty'] else ''}）")
    say("规则见 scripts/hx_select_study.py 开头（先提交后运行）。各格：笔数 / 胜率 / 每笔净收益（来回 0.15% 已扣）。")
    res = {"git": gi, "sp500x": run_pool("sp500x", p0, True)}
    passed = [c for c in CANDS if res["sp500x"]["gates"][c]["pass"]]
    res["passed_us"] = passed
    say("\n## SEEN = S&P 500 里 W2 事后核对用过的 97 只（只描述）")
    res["sp500seen"] = run_pool("sp500seen", p0, False)
    say("\n## S&P 400（只描述）")
    res["sp400"] = run_pool("sp400", p0, False)
    todo = [c for c in passed if c != "U1"]                                   # U2〜U5
    if todo and not a.skip_jp:
        say(f"\n## 日本「不变差」检查（{', '.join(todo)}；Z / E / J，现行 = W2 · 日経225）")
        jc = jp_check(todo)
        res["jp_check"] = jc
        for cid in todo:
            say(f"- {cid}：{'三个窗口都不变差 → 提议（用户确认才改）+ 前向记录' if not jc['fails'][cid] else '不满足：' + '；'.join(jc['fails'][cid])}")
    say("\n## 结论（事先规则）")
    if not passed:
        say("- 美国：没有候选横展开成立 → 日本规则不变（W2 照旧，前向记录照常）。")
    else:
        say(f"- 美国横展开成立：{', '.join(passed)}" + ("（U1 = 现行 W2 在美国也成立）" if "U1" in passed else ""))
        if todo:
            ok = [c for c in todo if not res.get("jp_check", {}).get("fails", {}).get(c, ["未检查"])]
            say(f"- 日本不变差：{', '.join(ok) if ok else '无'} → " + ("提议给用户确认（模拟盘 / 执行器不自动改）" if ok else "不提议"))
    if "U1" not in passed:
        say("- U1（W2）在美国不成立 → 只记录；W2 已按日本的登记通过、前向记录照常，不改。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    fp = paths.out_dir() / "hx_select_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
