"""hx_select_study.py — 选股信号的横展开：日本两期都成立的选股信号与它们的事先组合，在以前没用过的美国个股上检验一次
（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-27）：「基于现在所有的研究结果 进行网罗结合进行提高选股概率和收益率的提高 还有提高威胁指数等等 进行横展开的精确度」。
来由（研究总图 var/out/research_map.md）：日本个股层约 40 项登记研究里，两个年代 / 三个窗口方向一致的选股信号只有五类 ——
  ① 周线量比（W2 = 最近完成的一周成交量 ÷ 之前 10 周平均 ≥ 1.0；wvol_study 按组合 Calmar 通过、2026-09-27 启用；逐笔只比全部突破多
    +0.22 pp（2006〜2016）/ +0.14 pp（2017〜2026，胜率反而低 0.3 pp）；日経225 以外 666 只 2006〜2016 保留 +0.72% vs 过滤 +0.69%，无分离）；
  ② 突破日量比：V3「突破日 3 倍量」（不加 W2）逐笔两个年代 +1.63% / +1.30%（被过滤的 +0.37% / +0.23%）；V1（W2 ∧ 3 倍量）2006〜2016 只有
    17 笔 −0.13% → 这一轮复现的是 V3；日経225 以外 666 只 V3 +0.87% vs +0.66%、V1 +0.64% vs +0.71%（vthrust_wide，事后）；
  ③ 低 β：K2 = 突破（不加 W2）∧ vr1 ≥ 2.0 ∧ 对日経 β ≤ 0.70，Z / E / J 三个窗口每笔 +1.2〜1.5 pp、组合 Calmar 都不差，但 Z 胜率只 +3.2 pp、
    随机对照没过 → 前向记录（idio_forward：在全部突破里记 K2 标记）；
  ④ 股息率高（「质的飞跃」第 1 轮：逐笔两期一致，组合几乎不变；中型股里两个年代相反）；
  ⑤ 与指数低相关（S7 探索：日経225 W2 突破里 60 日相关最低 1/3 E 49% / +1.66% vs 最高 1/3 31% / −0.03%，J 57% / +1.67% vs 37% / +0.03%；
    与 ③ 同一原理 =「个别驱动的突破」；只在探索里看过、按各年代的三分位切的，没有登记检验）。
  组合的已知情况：S7 的合成分（量比、低 β、股息率、周线量比的秩平均取上半）E / J 都几乎没有提高（44% / +1.04%、46% / +0.91% vs 对照
  44.1% / +0.93%、44.8% / +0.73%）→ 事先就不看好「简单相加」，这一轮用固定门槛的投票（至少两条）再检验一次。
  日本的 Z / E / J 窗口都已经用来设计或检验过这些信号 → 再在日本上组合只会重复看过的数据。
  美国个股用过的情况（照实写）：早期研究（variant / allocation / beta_tilt / exec_timing / regime_strategy / scorecard / op_mode / unified /
  verify_all 等）用过 qbreak/universes.US_BROAD（纳斯达克 100 + 道指，约 109 只）与 qbreak/config.UNIVERSE_US（20 只）—— 其中 allocation_study
  拿 7 个信号强度指标（含量比）对美股逐笔收益看过、2026-09-24 的筛选复核看过 88 个美股信号的顶部过滤、wvol_us 看过 W2（美股参数：
  2006〜2016 保留 +0.31% vs 过滤 +0.91%，反过来）。→ 这些股票一律不进判定（SEEN = US_BROAD ∪ UNIVERSE_US）；
  主判定 = 今天的 S&P 500 去掉 SEEN（约 400 只），在本项目里从没被任何选股研究用过。
  这一轮只回答：日本得出的选股规则（阈值原样、日本参数的突破）在别的市场是不是也成立；成立的才考虑拿回日本（日本只作「不变差」检查）。

一 数据
  美国（主判定 = SP500U）：今天的 S&P 500 成分（var/us_constituents_2026-09.json，Wikipedia 2026-09-27；GOOG / FOX / NWS 只留一只）去掉 SEEN；
    只算「加入 S&P 500（Date added）满 90 天之后」的信号（之前的上涨是幸存者偏差；加入前后的指数调仓放量会扭曲量比 / 相关）；
    yfinance 35 年调整后日线（qbreak.data.load_universe，日本 E 窗口同一来源与口径；scripts/us_stock_data.py）；未复权收盘 + 每股分红；
    β、相关都对 ^GSPC。
  另报（只描述，不判定）：SEEN 里的 S&P 500 成分；S&P 400（变更表只从 2012 年起、早期很不全 → 一律从 2016-01-01（与加入日 + 90 天取晚的）起）。
  信号窗口：信号日 1995-01-02 〜 2026-06-30；前半 A = 〜2010-12-31、后半 B = 2011-01-03〜。
  登记前的调整（只看了笔数与数据完整性，没看任何收益）：第一次核对（2001〜2026）只有 1,547 笔 → 从 1995 年起、G1 / G2 改成
    「全窗口 + 两半同号」、G5 改成「全窗口 ≥ 150 且每半 ≥ 50」（小样本下每半都要 +0.5 pp 没有检出力）；对抗审计后：SEEN 扩到全部用过的美股、
    复现候选按日本原来的定义（K2 与 V3 不加 W2）、U1 改成方向检验、G4 按月聚类、加入后 90 天才算、S&P 400 不进判定。
  登记前最终核对（只有笔数，没看任何收益）：SP500U 398 只、P 1,708 笔（A 592 / B 1,116；数据检查剔除 1 笔）；保留 U1 866 笔
    （A 286 / B 580；剔除 A 306 / B 536）、U2 242（94 / 148）、U3 331（98 / 233）、U4 204（82 / 122）、U5 454（156 / 298）；
    特征缺值 β 0.4%、股息率 0.2%、其余 0%；日本检查的流程冒烟（候选条件 = 全部保留）Z / E / J 与现行完全一致。
二 基准交易：现行日本突破规则原样（qbreak.trader.load_params(market="JP")，去掉 W2 = score_forward.no_w2_params；阈值、离场都不为美国调整），
  每只票单独、一次一仓（qbreak.engine.run_backtest，美股执行设定：滑点每边 0.05%、跳空 > 3% 不进场，qbreak.fees 的 US 表），
  净收益 = 引擎毛收益 − 来回 0.15%（与日本 ¥25 万一笔的立花手续费同一比例，只为可比）；持仓到数据末尾没平仓的不算；
  数据检查：信号日前 5 天到平仓日之间有单日 |涨跌| > 60% 的（疑似未复权的拆股 / 分拆）剔除并报笔数。P = 剩下的全部交易。
三 信号日特征（只用信号日收盘为止已知的数据）
  w5v 周线量比（qbreak/mtf.weekly_volume_ratio，该股自己的日历；W2 同一定义）；vr1 突破日量比（idio_forward.vr1_series：当天 ÷ 之前 20 日平均）；
  β：104 周周收益（±50% 截断）对 ^GSPC 周收益的回归斜率（leap2_s5_explore.rolling_betas，≥ 69 周；信号日所在周之前的周五为止，
  leap2_s6b_portfolio.daily_from_weekly；K2 在日本同一算法）；dy 股息率（过去 365 日每股分红 ÷ 未复权收盘，leap_data.div_yield 同一算法），
  dy_top = 当天已加入的 S&P 500 全部成分（含 SEEN）里股息率排前 1/3（含不分红的 0）；
  corr60 = 信号日为止 60 个日收益与 ^GSPC 日收益的相关（≥ 40 对；leap2_s7_features 同一定义），corr_low = 当天已加入的 S&P 500 全部成分里
  corr60 排后 1/3（日本是按各年代 W2 交易的三分位切的 → 这里改成当天的横截面，事先不知道将来的分布）；
  缺值 → 该条件不满足（W2 缺值 → 保留，同现行）。
四 候选（P 的保留规则；阈值 = 日本的数字原样）
  U1 W2 复现（方向检验）：w5v ≥ 1.0。基准 = P。
  U2 K2 复现（放量 ∧ 低 β，不加 W2，同日本）：vr1 ≥ 2.0 ∧ β ≤ 0.70。基准 = P。
  U3 低相关（个别驱动）：w5v ≥ 1.0 ∧ corr_low（日本是在 W2 交易里看的）。基准 = W2 保留组（= 现行）。
  U4 V3 复现（突破日 3 倍量，不加 W2，同日本）：vr1 ≥ 3.0。基准 = P。
  U5 网罗组合（事先写定，不拟合）：w5v ≥ 1.0 ∧（vr1 ≥ 2.0、β ≤ 0.70、dy_top、corr_low 四条里至少两条）。基准 = W2 保留组。
五 判定（美国 SP500U；每个候选分别）
  U1（W2 在日本逐笔本来就只多 +0.1〜0.2 pp → 只检验方向）：R1 保留 − 剔除 每笔在 A、B 两半都 > 0；R2 (保留 − 基准) 每笔的按月聚类自助法
    （2,000 次）95% 区间下限 > 0；R3 两半的保留与剔除各 ≥ 50 笔。全过 = W2 在美国也成立。
  U2〜U5：G1 每笔净收益：全窗口 候选 − 基准 ≥ +0.5 pp，且 A、B 两半各自 > 0；G2 胜率：全窗口 ≥ 基准，且两半各自 ≥ 基准；
    G3 全窗口的每笔与胜率都 > 两种抽签对照的 95 分位：基准里按「年 × GICS 业种」分层、按「同一周」分层各随机保留与候选同样的笔数，各 1,000 次；
    G4 (候选 − 基准) 每笔的按月聚类自助法（2,000 次）95% 区间下限 > 0（全窗口）；G5 全窗口 ≥ 150 笔且两半各 ≥ 50 笔。全过 = 美国横展开成立。
  成立的 U2〜U5 才做日本「不变差」检查（Z / E / J 三个窗口，leap_confirm 同一套组合 runner，现行 = W2 · 日経225；U2 = K2 代替 W2、U4 = V3 代替 W2
    （与 S6 / vthrust 同一口径），U3 / U5 = W2 ∧ 条件；日本的 β、相关都对日経225，股息率与相关的排名在当天的日経225 成分里）：Calmar ≥ 现行 − 0.02、最大回撤不比现行深 2 pp 以上、组合里个股每笔 ≥ 现行、
    个股笔数 ≥ 现行的 30%（leap2_common S3 / S4 口径）→ 三个窗口都满足 = 提议（模拟盘 / 执行器用户确认才改）+ 前向记录（用户同意再登记；
    K2 现有的前向记录是在全部突破里记的，正好对应 U2）。
  U1 不成立 → 只记录（W2 已按日本的登记通过、前向记录照常；失效警报按 W2 前向记录自己的规则），不改。
六 另报（只描述，不判定）：U2 / U4 套在 W2 里面的版本（W2 ∧ K2、W2 ∧ 3 倍量 vs W2）；单项（vr1 ≥ 2、vr1 ≥ 3、β ≤ 0.70、dy_top、corr_low）
  在 P 与 W2 保留组里的保留 − 剔除；各特征与「赢」的 AUC、特征之间的秩相关（组合能提高多少的上限）；按年；SEEN 与 S&P 400 同一张表；
  数据检查剔除的笔数。
七 事前预期（写死）：U1 在美国大型股的事后核对已经反过来 → 成立约 15%；U2（约 250 笔）成立约 15%；U3（日本两个年代差 17〜21 pp，但只在探索里）
  成立约 20%；U4（约 200 笔）成立约 20%；U5（日本的秩平均已经没用）成立约 10%；全部不成立约 50%。检出力（审计估算）：保留约 250 笔时
  (候选 − 基准) 的标准误约 0.4 pp（按月聚类更大）→ 只有约 +1 pp 以上的效果有机会过 G4。
八 局限：今天的成分 + 加入 90 天之后（没有被剔除的股票 → 仍有幸存者偏差，候选与基准同样有）；两半的股票构成不同（A 只有很早就在 S&P 500 里、
  到今天还在的股票）；突破规则是为日本调的（只比较保留 vs 基准，不比较美日水平）；美股没有决算日数据 → 不做决算前 2 日不进场；
  股息率用 Yahoo 分红（特别分红也算）；GICS 业种是今天的分类；数据检查可能把真实的暴跌也剔掉（报笔数）。
输出：var/out/hx_select_study.md / .json（只有统计；美国的结果先写，日本检查跑完再补）
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

WIN0, WIN1, HALF_B0 = pd.Timestamp("1995-01-02"), pd.Timestamp("2026-06-30"), pd.Timestamp("2011-01-01")
S400_START = pd.Timestamp("2016-01-01")            # S&P 400 变更表早期不全 → 一律从 2016 年起（只描述）
BURN_IN = pd.Timedelta(days=90)                      # 加入指数满 90 天之后才算信号
RT_PCT = 0.15                                   # 来回成本（%），与日本 ¥25 万一笔的立花手续费同一比例
BAD_MOVE = 0.60                                 # 数据检查：单日 |涨跌| > 60%
W2_CUT, K_VR, K_BETA, V1_VR, DY_TOP = 1.0, 2.0, 0.70, 3.0, 2 / 3
G1_PP, MIN_N_ALL, MIN_N_HALF, LOT_REPS, BOOT_REPS, SEED, Q = 0.5, 150, 50, 1000, 2000, 20260927, 95
JP_CALMAR_TOL, JP_DD_TOL, JP_MIN_FRAC = 0.02, 2.0, 0.30
CANDS = {"U1": "W2 复现（方向检验）：周线量比 ≥ 1.0", "U2": "K2 复现：突破日量比 ≥ 2.0 ∧ β ≤ 0.70（不加 W2，同日本）",
         "U3": "低相关：W2 ∧ 60 日与指数相关排后 1/3", "U4": "V3 复现：突破日量比 ≥ 3.0（不加 W2，同日本）",
         "U5": "网罗组合：W2 ∧（量比 ≥ 2.0、β ≤ 0.70、股息率前 1/3、低相关 至少两条）"}
BASE_OF = {"U1": "P", "U2": "P", "U3": "W2", "U4": "P", "U5": "W2"}
NESTED = {"U2w": ("W2 ∧ K2", "W2"), "U4w": ("W2 ∧ 突破日 3 倍量", "W2")}          # 另报：套在 W2 里面的版本
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
def seen_names() -> set[str]:
    """以前的研究用过的美股（US_BROAD ∪ UNIVERSE_US）：一律不进判定。"""
    from qbreak.config import UNIVERSE_US
    from qbreak.universes import US_BROAD
    return set(US_BROAD) | set(UNIVERSE_US)


def pool_members(pool: str = "sp500u") -> tuple[dict[str, pd.Timestamp], dict[str, pd.Timestamp], dict[str, str]]:
    """({票: 开始算信号的日子}, {票: 加入指数的日子（排名用）}, {票: GICS 业种})。
    pool：sp500u（主判定 = S&P 500 去掉 SEEN）/ sp500seen（S&P 500 ∩ SEEN）/ sp500（全部，排名用）/ sp400（只描述，2016 年起）。"""
    seen = seen_names()
    src = "sp400" if pool == "sp400" else "sp500"
    c = UD.constituents()
    names = set(UD.names(src))
    start, added, sector = {}, {}, {}
    for r in c[src]:
        t = r["ticker"]
        if t not in names or (pool == "sp500u" and t in seen) or (pool == "sp500seen" and t not in seen):
            continue
        da = pd.Timestamp(r["date_added"]) if r.get("date_added") else None
        if src == "sp400":
            da = max(da, S400_START) if da is not None else S400_START
        if da is None:
            continue
        added[t] = da
        start[t] = max(da + BURN_IN, WIN0)
        sector[t] = r["sector"]
    return start, added, sector


def load_pool(pool: str = "sp500u") -> dict:
    start, _, sector = pool_members(pool)
    _, rank_added, _ = pool_members("sp400" if pool == "sp400" else "sp500")
    idx_sym = UD.INDEXES["sp500"]
    data = UD.ohlcv(list(start) + [idx_sym])
    idx = data.pop(idx_sym)["Close"]
    data = {t: df[["Open", "High", "Low", "Close", "Volume"]] for t, df in data.items() if t in start and len(df) >= 300}
    return {"pool": pool, "data": data, "index": idx, "start": {t: start[t] for t in data}, "sector": {t: sector[t] for t in data},
            "rank_start": rank_added}


def base_params():
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    return SF.no_w2_params(load_params(market="JP"))


def us_trades(D: dict, p0) -> pd.DataFrame:
    """每只票单独、一次一仓；交易窗口从该票的开始日起；没平仓的不算；信号日 ≤ WIN1。"""
    from qbreak.config import BacktestConfig
    from qbreak.engine import run_backtest
    from qbreak.strategy import compute_indicators
    bt = BacktestConfig.for_market("US", 35)
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
    T["month"] = T["sig_date"].dt.to_period("M").astype(str)
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
    return {"P": np.ones(len(T), bool), "W2": W2, "U1": W2, "U2": vr2 & lowb, "U3": W2 & clo, "U4": vr3,
            "U5": W2 & (votes >= 2), "U2w": W2 & vr2 & lowb, "U4w": W2 & vr3,
            "vr2": vr2, "vr3": vr3, "lowb": lowb, "dytop": dyt, "corrlow": clo}


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
    """(候选 − 基准) 每笔的按月聚类自助法 2.5% 分位（月 = 信号日所在月；持有期跨周，按周聚类会低估误差）。keep ⊆ base。"""
    wk = T["month"].to_numpy() if "month" in T else T["week"].to_numpy()
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


def gate_u1(T: pd.DataFrame, M: dict) -> dict:
    """U1（W2）方向检验 R1〜R3（头部五）。"""
    base, keep = M["P"], M["U1"]
    halfA = (T["sig_date"] < HALF_B0).to_numpy()
    res = {"base": "P", "all": {"cand": stats(T, keep), "base": stats(T, base), "excl": stats(T, base & ~keep)}}
    for h, hm in (("A", halfA), ("B", ~halfA)):
        res[h] = {"cand": stats(T, keep & hm), "base": stats(T, base & hm), "excl": stats(T, base & ~keep & hm)}
    res["diff_lo"] = boot_diff_lo(T, base, keep)
    nan = float("nan")
    fails = []
    for h in ("A", "B"):
        a, e = res[h]["cand"], res[h]["excl"]
        if not (a["n"] and e["n"] and a["mean"] > e["mean"]):
            fails.append(f"R1 {h} 保留每笔 {a['mean'] if a['n'] else nan:+.2f}% 不高于剔除 {e['mean'] if e['n'] else nan:+.2f}%")
        if not (a["n"] >= MIN_N_HALF and e["n"] >= MIN_N_HALF):
            fails.append(f"R3 {h} 保留 {a['n']} / 剔除 {e['n']} 笔（要各 ≥ {MIN_N_HALF}）")
    if not (res["diff_lo"] is not None and res["diff_lo"] > 0):
        fails.append(f"R2 (保留 − 基准) 按月聚类 95% 下限 {res['diff_lo'] if res['diff_lo'] is not None else nan:+.2f} pp ≤ 0")
    res["fails"] = fails
    res["pass"] = not fails
    return res


def gate(T: pd.DataFrame, M: dict, cid: str) -> dict:
    """U2〜U5 的判定 G1〜G5（头部五）；U1 走 gate_u1。"""
    if cid == "U1":
        return gate_u1(T, M)
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
    c, b = res["all"]["cand"], res["all"]["base"]
    nan = float("nan")
    fails = []
    if not (c["n"] and b["n"] and c["mean"] >= b["mean"] + G1_PP):
        fails.append(f"G1 全窗口每笔 {c['mean'] if c['n'] else nan:+.2f}% < 基准 {b['mean'] if b['n'] else nan:+.2f}% + {G1_PP} pp")
    if not (c["n"] and b["n"] and c["win"] >= b["win"]):
        fails.append(f"G2 全窗口胜率 {c['win'] if c['n'] else nan:.1f}% < 基准 {b['win'] if b['n'] else nan:.1f}%")
    if not c["n"] >= MIN_N_ALL:
        fails.append(f"G5 全窗口笔数 {c['n']} < {MIN_N_ALL}")
    for h in ("A", "B"):
        a, bb = res[h]["cand"], res[h]["base"]
        if not (a["n"] and bb["n"] and a["mean"] > bb["mean"]):
            fails.append(f"G1 {h} 每笔 {a['mean'] if a['n'] else nan:+.2f}% 不高于基准 {bb['mean'] if bb['n'] else nan:+.2f}%")
        if not (a["n"] and bb["n"] and a["win"] >= bb["win"]):
            fails.append(f"G2 {h} 胜率 {a['win'] if a['n'] else nan:.1f}% < 基准 {bb['win'] if bb['n'] else nan:.1f}%")
        if not a["n"] >= MIN_N_HALF:
            fails.append(f"G5 {h} 笔数 {a['n']} < {MIN_N_HALF}")
    for k, q in res["lottery_q"].items():
        if not (c["n"] and c["mean"] > q["mean"]):
            fails.append(f"G3 每笔 ≤ {k}抽签 {Q} 分位 {q['mean']:+.2f}%")
        if not (c["n"] and c["win"] > q["win"]):
            fails.append(f"G3 胜率 ≤ {k}抽签 {Q} 分位 {q['win']:.1f}%")
    if not (res["diff_lo"] is not None and res["diff_lo"] > 0):
        fails.append(f"G4 (候选 − 基准) 按月聚类 95% 下限 {res['diff_lo'] if res['diff_lo'] is not None else nan:+.2f} pp ≤ 0")
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
        dyd = {}
        for t in fa:
            try:
                dyd[t] = div_yield(actions(t), days)
            except Exception:                                                # noqa: BLE001
                dyd[t] = pd.Series(np.nan, index=days)
        DY = pd.DataFrame(dyd).reindex(days)
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
                if dummy:
                    keep[t] = w2[t]                                              # 冒烟测试：= 现行
                else:                                                            # U2 / U4 代替 W2（同 S6 / vthrust），U3 / U5 套在 W2 里
                    keep[t] = {"U2": v2 & lb, "U3": w2[t] & cl, "U4": v3, "U5": w2[t] & (votes >= 2)}[cid]
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


def build(pool: str, p0) -> tuple[dict, pd.DataFrame, dict, dict]:
    t0 = time.time()
    D = load_pool(pool)
    T = us_trades(D, p0)
    bad = bad_move_flags(T, D)
    info = {"pool": pool, "n_names": len(D["data"]), "n_trades_raw": int(len(T)), "n_bad": int(bad.sum())}
    T = attach_features(T[~bad].reset_index(drop=True), D)
    info["secs"] = round(time.time() - t0)
    return D, T, keep_masks(T), info


def describe_pool(T: pd.DataFrame, M: dict) -> dict:
    """只描述：各候选与各自基准（全窗口、两半）。"""
    halfA = (T["sig_date"] < HALF_B0).to_numpy()
    out = {}
    for cid in list(CANDS) + list(NESTED):
        bname = BASE_OF.get(cid) or NESTED[cid][1]
        out[cid] = {"all": stats(T, M[cid]), "base": stats(T, M[bname]), "A": stats(T, M[cid] & halfA), "B": stats(T, M[cid] & ~halfA)}
    return out


def run_main(p0) -> dict:
    D, T, M, info = build("sp500u", p0)
    say(f"\n## SP500U（主判定）：{info['n_names']} 只；交易 {info['n_trades_raw']} 笔，数据检查剔除 {info['n_bad']} 笔 → P {len(T)} 笔；"
        f"W2 保留 {int(M['W2'].sum())}（{M['W2'].mean() * 100:.1f}%）；{info['secs']}s")
    say(f"- P：{_f(stats(T, M['P']))}；W2：{_f(stats(T, M['W2']))}；W2 剔除：{_f(stats(T, ~M['W2']))}")
    out = {**info, "P": stats(T, M["P"]), "W2": stats(T, M["W2"]),
           "keep_frac": {k: round(float(M[k].mean()), 4) for k in list(CANDS) + list(NESTED) + list(SINGLES)}, "gates": {}}
    for cid in CANDS:
        g = gate(T, M, cid)
        out["gates"][cid] = g
        say(f"\n### {cid} {CANDS[cid]}（基准 = {'全部突破 P' if g['base'] == 'P' else 'W2 保留组（现行）'}）")
        say(f"- 全窗口：候选 {_f(g['all']['cand'])}；基准 {_f(g['all']['base'])}；剔除 {_f(g['all']['excl'])}")
        say(f"- A 1995〜2010：候选 {_f(g['A']['cand'])}；基准 {_f(g['A']['base'])}" + (f"；剔除 {_f(g['A']['excl'])}" if "excl" in g["A"] else ""))
        say(f"- B 2011〜2026-06：候选 {_f(g['B']['cand'])}；基准 {_f(g['B']['base'])}" + (f"；剔除 {_f(g['B']['excl'])}" if "excl" in g["B"] else ""))
        if "lottery_q" in g:
            say("- 抽签对照 95 分位：" + "；".join(f"{k} 每笔 {v['mean']:+.2f}% 胜率 {v['win']:.1f}%" for k, v in g["lottery_q"].items()))
        say(f"- (候选 − 基准) 按月聚类 95% 下限 {g['diff_lo'] if g['diff_lo'] is not None else float('nan'):+.2f} pp")
        say(f"- 判定：{'美国横展开成立' if g['pass'] else '不成立：' + '；'.join(g['fails'])}")
    nd = describe_pool(T, M)
    out["nested"] = {k: nd[k] for k in NESTED}
    say("\n套在 W2 里面的版本（只描述）：" + "；".join(f"{NESTED[k][0]} {_f(nd[k]['all'])} vs W2 {_f(nd[k]['base'])}（A {_f(nd[k]['A'])} / B {_f(nd[k]['B'])}）"
                                          for k in NESTED))
    ds = describe(T, M)
    out["describe"] = ds
    say("单项（保留 vs 剔除）：" + "；".join(f"{SINGLES[k.split('|')[0]]}［{k.split('|')[1]}］ {_f(v['keep'])} vs {_f(v['drop'])}"
                                  for k, v in ds["singles"].items()))
    say("特征与「赢」的 AUC：" + "、".join(f"{k} {v:.3f}" if v is not None else f"{k} —" for k, v in ds["auc"].items())
        + "；特征秩相关：" + "、".join(f"{k} {v:+.2f}" for k, v in ds["corr"].items()))
    say("按年（P / W2 / U3 / U5 每笔）：" + "；".join(
        f"{y} {v['P']['n']}笔 " + " / ".join(f"{v[k]['mean'] if v[k]['n'] else 0:+.2f}%" for k in ("P", "W2", "U3", "U5"))
        for y, v in ds["by_year"].items()))
    return out


def run_desc(pool: str, p0, title: str) -> dict:
    D, T, M, info = build(pool, p0)
    say(f"\n## {title}（只描述）：{info['n_names']} 只；P {len(T)} 笔（数据检查剔除 {info['n_bad']}）；{info['secs']}s")
    d = describe_pool(T, M)
    for cid, x in d.items():
        name = CANDS.get(cid) or NESTED[cid][0]
        say(f"- {cid} {name}：{_f(x['all'])} vs 基准 {_f(x['base'])}（A {_f(x['A'])} / B {_f(x['B'])}）")
    return {**info, "desc": d}


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "hx_select_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


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
        D, T, M, info = build("sp500u", p0)
        halfA = (T["sig_date"] < HALF_B0).to_numpy()
        print(f"SP500U：{info['n_names']} 只；交易 {info['n_trades_raw']}，剔除 {info['n_bad']}；P {len(T)}（A {int(halfA.sum())} / B {int((~halfA).sum())}）")
        print("缺值率：" + "、".join(f"{c} {T[c].isna().mean() * 100:.1f}%" for c in ("w5v", "vr1", "beta", "dy", "dy_rank", "corr60", "corr_rank")))
        for k in list(CANDS) + list(NESTED) + list(SINGLES):
            m = M[k]
            extra = f"；剔除 A {int((~m & halfA).sum())} / B {int((~m & ~halfA).sum())}" if k == "U1" else ""
            print(f"  {k}：保留 {int(m.sum())}（{m.mean() * 100:.1f}%；A {int((m & halfA).sum())} / B {int((m & ~halfA).sum())}{extra}）")
        return 0
    say(f"# 选股信号的横展开（美国个股）（{pd.Timestamp.today().date()}；git {gi['rev']}{'（脏）' if gi['dirty'] else ''}）")
    say("规则见 scripts/hx_select_study.py 开头（先提交后运行）。各格：笔数 / 胜率 / 每笔净收益（来回 0.15% 已扣）。")
    res = {"git": gi, "sp500u": run_main(p0)}
    passed = [c for c in CANDS if res["sp500u"]["gates"][c]["pass"]]
    res["passed_us"] = passed
    res["sp500seen"] = run_desc("sp500seen", p0, "SEEN：以前的研究用过的美股里的 S&P 500 成分")
    res["sp400"] = run_desc("sp400", p0, "S&P 400（2016 年起）")
    write_out(res)                                                           # 美国的结果先写（日本检查出错也不丢）
    todo = [c for c in passed if c != "U1"]
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
        say(f"- 美国横展开成立：{', '.join(passed)}" + ("（U1 = 现行 W2 的方向在美国也成立）" if "U1" in passed else ""))
        if todo:
            ok = [c for c in todo if not res.get("jp_check", {}).get("fails", {}).get(c, ["未检查"])]
            say(f"- 日本不变差：{', '.join(ok) if ok else '无'} → " + ("提议给用户确认（模拟盘 / 执行器不自动改）" if ok else "不提议"))
    if "U1" not in passed:
        say("- U1（W2）在美国不成立 → 只记录；W2 已按日本的登记通过、前向记录照常，不改。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
