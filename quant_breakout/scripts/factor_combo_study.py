"""factor_combo_study.py — 全部因子的组合网罗（单个 / 两两 / 三个）× 横展开的预测目标
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「把现有全部因子（量化状态层、宏观层各项、国债 / 利率、信用利差、VIX、失业率、威胁指数各分项、能源消费 K1〜K5、行业倾斜等）做组合网罗：
单个、两两、三个……横展开预测目标：①日経225 个股突破信号的后续收益 ②S&P500 / 日経 的牛熊转折 ③威胁指数「之后 60 日跌 ≥10%」」。

一、因子清单（编号；全部按「当时已公布」取值，再换成当时为止的扩张百分位 0〜1：日度因子至少 750 个交易日的历史，个股层至少 100 个之前的信号）
  市场层 30 个（日経 / 美股各一套：Q、B 用各自的指数；每个因子取「那天该市场收盘时已知」的值：美国的日序列在美国的日子用当天美国收盘的值、
    在日本的日子用那天之前最后一个美国收盘（threat.us_asof_for_jp，与威胁指数同一口径）；日本 10Y 两边都用前一个营业日；①用信号日的日本这一套）：
  Q 量化状态层：Q1 新仓倍数（0 / 0.75 / 1，qbreak/regime.quant_regime_series）、Q2 离 200 日线 %、Q3 离一年高点 %、Q4 20 日实现波动（= 威胁 rvol）
  B 牛熊：B1 牛熊状态（牛 = 1）、B2 离翻转价位 %（scripts/combo_study.flip_distance）
  M 宏观层（qbreak/macro.py 触发用的序列；长历史用 FRED 的同一经济序列）：M1 Brent（DCOILBRENTEU）、M2 Brent 20 日涨幅、M3 美 10Y（DGS10）、
    M4 VIX（VIXCLS）、M5 USD/JPY、M6 宏观层新仓倍数（macro_mult，日本 / 美国各自的规则）
  R 利率 / 国债：R1 美 10Y 60 日变化（威胁 rates）、R2 曲线倒挂 −(10Y−3M)（威胁 curve）、R3 日本 10Y（財務省）、R4 日本 10Y 60 日变化（威胁 jgb）、
    R5 美国 10 年实际利率（DFII10，2003 起）
  C 信用：C1 Baa−10Y 利差（BAA10Y，滞后 1 天）、C2 Baa−10Y 60 日变化（威胁 credit）
  V 波动：V1 VIX 20 日变化（威胁 vix_d20）
  U 就业：U1 Sahm 型失业率指标（威胁 jobs，次月 10 日起）、U2 初次申请失业金 4 周平均的同比（ICSA 周度，美国 5 天后、日本 6 天后可用）
  T 威胁指数：T1 威胁指数 A0（该市场，现行 v1）、T2 油价冲击 WTI 60 日涨幅（威胁 oil）、T3 日元急升 −USD/JPY 20 日变化（威胁 yen）
  E 能源消费：E1 世界（K1，STEO 当时版）、E2 美国（K2，EIA 周度）、E3 中国（K3）、E4 日本（K4，JODI）（3 个月同比，月末时已公布的值）
  H 健康度：H1 市场健康度（qbreak/macro_now.health_series；美股宽度没有历史不含）
  个股层 17 个（只用于①）：S01〜S15 = qbreak/signal_score.py 的 15 个（量比、箱体幅度、突破距离、出货日、上影线、相对强度、离 200 日线、离一年高点、
    波动收缩、日経离 200 日线、行业 60 日动量、行业广度、板块共振、个股相对行业、行业 20 日动量）、E5 行业能源顺风分（K5，energy_study.industry_scores；
    只有事先写了能源联动的业种有值，其余缺值 → 含 E5 的组合只在这些业种的信号上评价）、S16 板块倾斜倍数（macro.sector_mult，行业倾斜层）
  直接 / 间接：①的个股层 = 直接、市场层 = 间接；②③的 Q / B / T1 / V1 / M4 = 直接（同一市场的价格与波动）、其余 = 间接。
  （威胁指数 v2 / v3 调查过的另外约 90 个因素已在 scripts/threat_weight_study.py 检验过，不在这里再网罗。）
二、组合：单个、两两、三个（上限 3 个）；组合分数 = 各因子（方向在发现期按单因子 AUC 定：< 0.5 就用 1 − 百分位）百分位的等权平均，不拟合系数；
  任一因子缺值的行没有分数。总组合数（运行时核对）：① 47 个因子 → 47 + 1,081 + 16,215 = 17,343；② 29 个（去掉 B1，它就是条件）→
  29 + 406 + 3,654 = 4,089 × 4 个目标 = 16,356；③ 30 个 → 30 + 435 + 4,060 = 4,525 × 2 个目标 = 9,050；合计 42,749。
三、预测目标（7 个）
  ① 日経225 成分股各自独立的突破交易（现行参数；scripts/earnings_study.outcomes）：扣费后赚钱（win）。
  ② 牛熊转折（现行分界 var/bullbear.json：ma_band 250 日 ±3%、连续 5 天）：日経 / S&P500 × 顶（牛市的日子里、之后 60 个交易日内转熊）/
     底（熊市的日子里、之后 60 个交易日内转牛）= 4 个。
  ③ 之后 60 个交易日内的最低收盘比今天跌 ≥ 10%（qbreak/threat.forward_drawdown）：日経 / S&P500 = 2 个。
四、时段：① 发现期 2006-10〜2015-12、验证期 2016-01〜2023-09；②③ 发现期 1995-01〜2012-12、验证期 2013-01〜2023-09；
  最后留出期 2023-10〜（最近 3 年：前三道门槛之前不看，只对通过 G1〜G3 的组合和现行各算一次）。结果窗口跨进下一个时段的样本剔除（不偷看）。
五、指标：AUC（主）、平衡准确率（判为「正」的门槛 = 发现期正例比例对应的分位）；S0C2 20 年年化 / 回撤 / Calmar 与验证期 / 留出期 Calmar
  （只对通过 G1〜G4 的组合跑：①跳过组合分数低于发现期 1/3 分位的买点（分数缺值的照常）；②顶与③：分数 ≥ 发现期 80 分位的日子日本个股新仓 ×0.5，
  下一交易日成交；②底不跑）。S0C2 = scripts/adaptive_study.make_runner（现行设定、¥100 万 × 4 名额、20 年 = 2006-10〜）。
六、多重检验与「纯随机因子」对照：对照 = 全部因子一起按同一个随机偏移循环错开（日度 ≥ 500 个交易日，①≥ 20% 的信号；种子 20260926）
  = 与目标无关、但自身的持续性与因子之间的相关都和真实因子一样的随机因子；同一套流程（含发现期定方向）重跑 20 次。
  真实组合验证期 AUC 的经验 p 值 = 对照里（同一目标、全部组合）验证期 AUC ≥ 它的比例；每个目标内做 Benjamini–Hochberg（q = 0.05）。「偶然会出现几个」= 把每一次对照当作真实数据（p 值对其余 19 次的对照算，分辨率略粗、稍偏保守）
  走同样的门槛，报告平均与最多。组合在某一时段正例或负例 < 20 → 那一时段的 AUC 记缺值（p = 1）。
七、采用门槛（全部满足才进前向观察名单；模拟盘不改）：
  G1 BH 校正后显著；G2 两个半段同号（发现期与验证期 AUC 都 > 0.5）；
  G3 比现行好 ≥ 事先定的幅度：① 验证期 AUC ≥ 0.55；② 验证期 AUC ≥ 0.60 且平衡准确率 ≥ 0.55；③ 验证期 AUC ≥ 现行 A0（T1）+ 0.03 且平衡准确率 ≥ A0；
  G4 留出期不变差：留出期 AUC ≥ max(0.5, 现行在留出期的 AUC)（①② 现行 = 0.5；③ 现行 = A0）；留出期没有正例或负例（算不出 AUC）→ 不通过；
  G5（①、②顶、③）S0C2：验证期 Calmar ≥ 现行 + 0.05，20 年与留出期 Calmar 都不低于现行，20 年最大回撤不比现行深 2 pp 以上。
  全部通过的写进 var/out/factor_combo_watchlist.json，另行登记前向记录（要用户确认）；模拟盘不改。
八、局限：②的转折一个市场 30 年只有十几次、③的大跌也只有二十几段，验证期 AUC 的经验 p 值天然很粗；同一段历史上已做过很多研究；
  ①日経225 20 年只有 662 个信号 / 636 笔独立交易（--coverage；个股层前 100 个信号是预热），E5 只有 241 个信号有值；
  股票池是现在的成分；长历史的宏观序列用 FRED（与实盘用的 Yahoo 同一经济序列，数值略有差异）；E1 / E3（STEO）2007-10 才开始、R5 2003 才开始，
  ②③的发现期里它们的样本很少（正负例 < 20 → AUC 缺值 → G2 不过）；因子之间高度相关，4 万多个组合远不是独立的检验。
登记前做过的检查：tests/test_factor_combo.py（组合个数、AUC 与平局、平衡准确率、方向只在发现期定、经验 p 值、BH、同偏移的对照、剔除跨时段的样本、
  门槛、合成数据的「真实 + 对照」全流程）；
  只看过各因子的覆盖（起止、个数：--coverage），没有算任何因子与目标的关系。
输出：var/out/factor_combo_study.md / .json（通过 G1〜G3 的全部组合与留出期、S0C2）/ .csv（全部组合的发现期 / 验证期指标与门槛）、
  var/out/factor_combo_watchlist.json（全部门槛都通过的）
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
from qbreak import factor_combo as FC                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

KMAX, N_PLACEBO, SEED, Q_FDR, H = 3, 20, 20260926, 0.05, 60
MIN_DAILY, MIN_SIG, MIN_SHIFT_D, MIN_SHIFT_FRAC = 750, 100, 500, 0.2
P1 = {"disc": ("2006-10-01", "2015-12-31"), "val": ("2016-01-01", "2023-09-30"), "hold": ("2023-10-01", "2100-01-01")}
P23 = {"disc": ("1995-01-01", "2012-12-31"), "val": ("2013-01-01", "2023-09-30"), "hold": ("2023-10-01", "2100-01-01")}
V_START, V_END, HOLD = "2016-01-01", "2023-10-01", "2023-10-01"
CALMAR_UP, DD_TOL, SKIP_Q, HOT_Q, HALF = 0.05, 2.0, 1 / 3, 0.80, 0.5
MARKET = {"Q1": "量化状态层新仓倍数", "Q2": "离 200 日线 %", "Q3": "离一年高点 %", "Q4": "20 日实现波动", "B1": "牛熊状态（牛 = 1）",
          "B2": "离翻转价位 %", "M1": "Brent", "M2": "Brent 20 日涨幅", "M3": "美 10Y", "M4": "VIX", "M5": "USD/JPY", "M6": "宏观层新仓倍数",
          "R1": "美 10Y 60 日变化", "R2": "曲线倒挂 −(10Y−3M)", "R3": "日本 10Y", "R4": "日本 10Y 60 日变化", "R5": "美国实际利率 10Y",
          "C1": "Baa−10Y 利差", "C2": "Baa−10Y 60 日变化", "V1": "VIX 20 日变化", "U1": "Sahm 型失业率指标", "U2": "初次申请失业金同比",
          "T1": "威胁指数 A0", "T2": "油价冲击（WTI 60 日）", "T3": "日元急升（−USD/JPY 20 日）", "E1": "世界石油消费（K1）",
          "E2": "美国成品油消费（K2）", "E3": "中国石油消费（K3）", "E4": "日本成品油需求（K4）", "H1": "市场健康度"}
STOCK_KEYS = ["vol", "tight", "brk", "dist", "shadow", "rs", "trend", "high", "squeeze", "mkt",
              "ind_mom60", "ind_breadth", "ind_cobreak", "rel_ind60", "ind_mom20"]
STOCK = {f"S{i:02d}": k for i, k in enumerate(STOCK_KEYS, 1)}
EXTRA = {"E5": "行业能源顺风分（K5）", "S16": "板块倾斜倍数"}
TARGETS = {"T1_breakout": "① 日経225 突破交易 赚钱", "T2_JP_top": "② 日経 牛→熊（60 日内）", "T2_JP_bottom": "② 日経 熊→牛（60 日内）",
           "T2_US_top": "② S&P500 牛→熊（60 日内）", "T2_US_bottom": "② S&P500 熊→牛（60 日内）",
           "T3_JP": "③ 日経 60 日内跌 ≥10%", "T3_US": "③ S&P500 60 日内跌 ≥10%"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def label_of(k: str) -> str:
    if k in MARKET:
        return f"{k} {MARKET[k]}"
    if k in STOCK:
        from qbreak.signal_score import LABELS
        return f"{k} {LABELS[STOCK[k]]}"
    return f"{k} {EXTRA.get(k, k)}"


# ────────────────────────── 因子面板（原始值，当时已知）──────────────────────────
def _asof(s: pd.Series, days: pd.DatetimeIndex, lag: int = 0) -> pd.Series:
    s = s.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(days.union(s.index)).ffill().reindex(days).shift(lag)


def market_panels() -> tuple[dict, dict]:
    """{"JP": 天 × 30 个因子（原始值，那天该市场收盘时已知）, "US": …}，以及目标要用的指数收盘。
    美国的日序列：美国的日子用当天美国收盘的值，日本的日子用「那天之前最后一个美国收盘」（threat.us_asof_for_jp，与威胁指数同一口径）；
    日本 10Y 两边都用前一个营业日的值（財務省当天傍晚才公布）。"""
    from bullbear_study import SYM, load
    import combo_study as CB
    from qbreak import energy_demand as E
    from qbreak import factors as F
    from qbreak import macro as MC
    from qbreak import macro_now as MN
    from qbreak import threat as TH
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.regime import quant_regime_series
    ti = TH.load_inputs()
    r = ti["raw"]
    days = {"US": ti["spx"].index[ti["spx"].index >= "1990-01-01"], "JP": ti["n225"].index[ti["n225"].index >= "1990-01-01"]}
    jgb = ti["jgb"].shift(1)                                                  # 前一个营业日（日本收盘时已知）
    al = {"US": lambda s: _asof(s, days["US"]), "JP": lambda s: TH.us_asof_for_jp(s, days["JP"])}
    raw = {mk: TH.raw_features(days[mk], ti["spx"] if mk == "US" else ti["n225"],
                               *[al[mk](r[k]) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")], r["UNRATE"],
                               usdjpy=al[mk](ti["fx"]), jgb10=jgb) for mk in ("US", "JP")}
    a0 = {mk: TH.threat_index(raw[mk], TH.US_COLS if mk == "US" else TH.JP_COLS)[0] for mk in ("US", "JP")}
    brent, dfii, icsa = F.fred("DCOILBRENTEU"), F.fred("DFII10"), F.fred("ICSA")
    b = brent.dropna()
    b = b[b > 0]
    ic4 = icsa.dropna().rolling(4).mean()
    icy = (ic4 / ic4.shift(52) - 1) * 100
    us_daily = {"brent": b, "brent_chg20_pct": (b / b.shift(20) - 1) * 100, "us10y": r["DGS10"], "vix": r["VIXCLS"],
                "usdjpy": ti["fx"], "dfii": dfii}
    X3 = E.signals(E.load_all(), pd.date_range("2000-01-31", pd.Timestamp.today(), freq="ME"), windows=(3,))[3]
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    closes = {"US": load(*SYM["US"])["Close"], "JP": load(*SYM["JP"])["Close"]}
    panels = {}
    for mk in ("US", "JP"):
        dd, rw = days[mk], raw[mk]
        fd = pd.DataFrame({k: al[mk](v) for k, v in us_daily.items()}, index=dd)
        other = "JP" if mk == "US" else "US"
        a0_other = _asof(a0["JP"], dd) if mk == "US" else TH.us_asof_for_jp(a0["US"], dd)   # 日経的 A0 在美国收盘时已知
        hs = MN.health_series(fd[["brent", "brent_chg20_pct", "us10y", "vix", "usdjpy"]], ti["n225"], jgb, None,
                              {mk: a0[mk], other: a0_other})["score"]
        st = pd.Series(np.asarray(det.states(closes[mk])), index=closes[mk].index)
        bear = st == BEAR
        c = closes[mk]
        f = pd.DataFrame(index=dd)
        f["Q1"] = _asof(quant_regime_series(pd.DataFrame({"Close": c})), dd)
        f["Q2"] = _asof((c / c.rolling(200).mean() - 1) * 100, dd)
        f["Q3"] = _asof((c / c.rolling(252, min_periods=1).max() - 1) * 100, dd)
        f["Q4"] = rw["rvol"]
        f["B1"] = _asof((~bear).astype(float), dd)
        f["B2"] = _asof(CB.flip_distance(c, bear), dd)
        f["M1"], f["M2"], f["M3"], f["M4"], f["M5"] = fd["brent"], fd["brent_chg20_pct"], fd["us10y"], fd["vix"], fd["usdjpy"]
        g = lambda v: float(v) if np.isfinite(v) else None                                        # noqa: E731
        f["M6"] = [MC.macro_mult(MC.MacroFeatures(brent=g(x.brent), brent_chg20_pct=g(x.brent_chg20_pct), us10y=g(x.us10y),
                                                  vix=g(x.vix), usdjpy=g(x.usdjpy)), None, mk)[0] for x in fd.itertuples()]
        f["R1"], f["R2"] = rw["rates"], rw["curve"]
        f["R3"] = _asof(jgb, dd)
        f["R4"] = rw["jgb"]
        f["R5"] = fd["dfii"]
        f["C1"] = al[mk](r["BAA10Y"]).shift(1)                                                     # Baa 滞后 1 天（与威胁 credit 同）
        f["C2"], f["V1"], f["U1"] = rw["credit"], rw["vix_d20"], rw["jobs"]
        f["U2"] = TH.weekly_available(icy, dd, 5 if mk == "US" else 6)                              # 周四美国早上公布（日本是周五）
        f["T1"], f["T2"], f["T3"] = a0[mk].reindex(dd), rw["oil"], rw["yen"]
        for k, src in (("E1", "world"), ("E2", "us_total"), ("E3", "china"), ("E4", "jp_total")):
            f[k] = _asof(X3[src], dd)
        f["H1"] = _asof(hs, dd)
        panels[mk] = f[list(MARKET)]
    return panels, closes


def signal_panel(p) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """①：日経225 每个 entry 信号一行（个股层 17 个因子的原始值）+ 各自独立的交易（ES.outcomes）+ 指标表。"""
    import earnings_study as ES
    import energy_study as ENS
    from qbreak import energy_demand as E
    from qbreak import macro as MC
    from qbreak import signal_score as SSc
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.sectors import sector_of
    from qbreak.strategy import IndicatorCache
    from bullbear_study import SYM, load
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    ind = dict(IndicatorCache(data_n).all(p))
    rows = SSc.signal_rows(SSc.feature_panel(ind, load(*SYM["JP"])["Close"]), ind, start="2005-01-01")
    for s, k in STOCK.items():
        rows[s] = rows[k]
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    X3 = E.signals(E.load_all(), pd.date_range("2000-01-31", pd.Timestamp.today(), freq="ME"), windows=(3,))[3]
    S_ind = ENS.industry_scores(X3.apply(ENS.expanding_z), ENS.PAIRS, set(s33.values()))
    e5 = np.full(len(rows), np.nan)                                           # K5：信号日所属业种的能源顺风分（月末时已公布）
    grp = rows["ticker"].map(s33)
    for gname, ix in rows.groupby(grp).groups.items():
        if gname in S_ind:
            e5[np.asarray(ix)] = ENS.asof_month(S_ind[gname], rows.loc[ix, "date"])
    rows["E5"] = e5
    frame = MC.features_frame(MC.load_macro_series(d21))
    fa = {d: MC.features_at(frame, d) for d in pd.DatetimeIndex(pd.unique(rows["date"]))}        # 信号日收盘时已知的宏观（模拟盘同一来源）
    rows["S16"] = [MC.sector_mult(sector_of(t, "JP"), fa[d])[0] for t, d in zip(rows["ticker"], rows["date"])]
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    T = ES.outcomes(ind, p, bt)
    return rows, T, {"ind": ind, "data_n": data_n}


# ────────────────────────── 目标 ──────────────────────────
def turn_labels(close: pd.Series, days: pd.DatetimeIndex) -> dict[str, pd.Series]:
    """②：牛市日「之后 H 个交易日内转熊」、熊市日「之后 H 个交易日内转牛」（不是那个状态的日子 = NaN）。"""
    from qbreak.bullbear import BEAR, BULL, Detector, load_config
    det = load_config()["detector"]
    st = pd.Series(np.asarray(Detector(det["kind"], det["params"]).states(close)), index=close.index).reindex(days).ffill()
    v = st.to_numpy(float)
    n = len(v)
    top, bot = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n - H):
        fut = v[i + 1:i + 1 + H]
        if v[i] == BULL:
            top[i] = float((fut == BEAR).any())
        elif v[i] == BEAR:
            bot[i] = float((fut == BULL).any())
    return {"top": pd.Series(top, index=days), "bottom": pd.Series(bot, index=days)}


def horizon_end(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    ends = list(days[H:]) + [pd.NaT] * H
    return pd.DatetimeIndex(ends[:len(days)])


# ────────────────────────── 一个目标的网罗（真实 + 对照）──────────────────────────
def run_search(Pm: np.ndarray, y: np.ndarray, masks: dict, cols: list[str], combos: list, shift: int = 0) -> pd.DataFrame:
    A0 = FC.shift_rows(Pm, shift) if shift else Pm
    Pdf = pd.DataFrame(A0, columns=cols)
    sign = FC.directions(Pdf, pd.Series(y), masks["disc"])
    A = FC.signed(Pdf, sign)
    R = FC.search(A, y, {"disc": masks["disc"], "val": masks["val"]}, combos)
    R["signs"] = [tuple(sign[cols[j]] for j in c) for c in R["combo"]]
    return R


def _combo_label(cols: list[str], combo: tuple, signs: tuple) -> str:
    return " + ".join(("" if sg > 0 else "反向 ") + label_of(cols[j]) for j, sg in zip(combo, signs))


def _row(R: pd.DataFrame, combo: tuple) -> pd.DataFrame:
    return R[[c == combo for c in R["combo"]]]


def _placebo_job(args):
    Pm, y, masks, cols, combos, shift = args
    R = run_search(Pm, y, masks, cols, combos, shift)
    return R[["disc_auc", "val_auc", "val_ba"]].to_numpy(float)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true", help="只看各因子的覆盖（起止、个数），不算和目标的关系（登记前用）")
    ap.add_argument("--placebo", type=int, default=N_PLACEBO)
    args = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/factor_combo_study.py", "qbreak/factor_combo.py",
                            "qbreak/threat.py", "qbreak/macro.py", "qbreak/macro_now.py", "qbreak/regime.py", "qbreak/bullbear.py",
                            "qbreak/signal_score.py", "qbreak/energy_demand.py", "scripts/energy_study.py", "scripts/combo_study.py",
                            "scripts/adaptive_study.py", "scripts/earnings_study.py"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    from qbreak.trader import load_params
    p = load_params(market="JP")
    panels, closes = market_panels()
    rows, T, ctx = signal_panel(p)
    if args.coverage:
        for mk, f in panels.items():
            print(f"## 市场层 {mk}（{f.index[0].date()}〜{f.index[-1].date()}，{len(f)} 天）")
            for c in f.columns:
                s = f[c].dropna()
                print(f"  {label_of(c)}：{s.index.min().date() if len(s) else '—'}〜{s.index.max().date() if len(s) else '—'}，{len(s)} 个")
        print(f"## 个股层（{len(rows)} 个信号，{rows['date'].min().date()}〜{rows['date'].max().date()}；独立交易 {len(T)} 笔）")
        for c in list(STOCK) + list(EXTRA):
            print(f"  {label_of(c)}：有值 {int(rows[c].notna().sum())} 个")
        for name, n in (("①", 30 + 17), ("②", 29), ("③", 30)):
            cnt = FC.n_combos(n, KMAX)
            print(f"{name} {n} 个因子 → " + " + ".join(f"{v:,}" for v in cnt.values()) + f" = {sum(cnt.values()):,}")
        return 0
    return run_all(panels, closes, rows, T, ctx, p, head, t0, args.placebo)


def _pct_panel(f: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({c: FC.expanding_pct(f[c], MIN_DAILY) for c in f.columns}, index=f.index)


def build_targets(panels: dict, closes: dict, rows: pd.DataFrame, T: pd.DataFrame) -> dict:
    """每个目标：{"P": 行 × 因子（百分位，未定方向）, "cols", "y", "dates", "masks", "hold": 留出期掩码}。"""
    from qbreak import threat as TH
    out = {}
    pct = {mk: _pct_panel(f) for mk, f in panels.items()}
    # ①：信号行（按日期）→ 市场层取信号日那天的百分位、个股层按之前的信号算扩张百分位 → 交易取它那一行
    R = rows.sort_values(["date", "ticker"], ignore_index=True)
    u = pd.DatetimeIndex(pd.unique(R["date"]))
    mkt = pct["JP"].reindex(pct["JP"].index.union(u)).ffill().reindex(pd.DatetimeIndex(R["date"]))
    sp = pd.DataFrame({c: FC.expanding_pct(R[c], MIN_SIG) for c in list(STOCK) + list(EXTRA)})
    SIG = pd.concat([mkt.reset_index(drop=True), sp], axis=1)
    key = {(t, d): i for i, (t, d) in enumerate(zip(R["ticker"], R["date"]))}
    T = T.sort_values("sig_date", ignore_index=True)
    ix = [key.get((t, d)) for t, d in zip(T["ticker"], T["sig_date"])]
    ok = np.array([i is not None for i in ix])
    T = T[ok].reset_index(drop=True)
    P1m = SIG.iloc[[i for i in ix if i is not None]].reset_index(drop=True)
    d1, e1 = pd.DatetimeIndex(T["sig_date"]), pd.DatetimeIndex(T["exit_date"])
    out["T1_breakout"] = {"P": P1m, "cols": list(P1m.columns), "y": T["win"].astype(float).to_numpy(), "dates": d1,
                          "masks": {k: FC.purge_mask(d1, a, b, e1) for k, (a, b) in P1.items()},
                          "sig_all": SIG, "sig_rows": R, "trades": T}
    for mk in ("JP", "US"):
        days = panels[mk].index
        he = horizon_end(days)
        lab = turn_labels(closes[mk], days)
        cols2 = [c for c in MARKET if c != "B1"]
        for side in ("top", "bottom"):
            y = lab[side].to_numpy(float)
            out[f"T2_{mk}_{side}"] = {"P": pct[mk][cols2].reset_index(drop=True), "cols": cols2, "y": y, "dates": days,
                                      "masks": {k: FC.purge_mask(days, a, b, he) & np.isfinite(y) for k, (a, b) in P23.items()}}
        cl = closes[mk].reindex(closes[mk].index.union(days)).ffill().reindex(days)
        fd = TH.forward_drawdown(cl, H).to_numpy(float)
        y3 = np.where(np.isfinite(fd), (fd <= -0.10).astype(float), np.nan)
        out[f"T3_{mk}"] = {"P": pct[mk][list(MARKET)].reset_index(drop=True), "cols": list(MARKET), "y": y3, "dates": days,
                           "masks": {k: FC.purge_mask(days, a, b, he) & np.isfinite(y3) for k, (a, b) in P23.items()}}
    return out


def run_all(panels, closes, rows, T, ctx, p, head, t0, n_placebo) -> int:
    from concurrent.futures import ProcessPoolExecutor
    tg = build_targets(panels, closes, rows, T)
    rng = np.random.default_rng(SEED)
    say(f"# 全部因子的组合网罗（单个 / 两两 / 三个）× 7 个预测目标（{pd.Timestamp.today().date()}）")
    say("规则见 scripts/factor_combo_study.py 开头（先提交后运行）。")
    results, summary = {}, {}
    total = 0
    for name, d in tg.items():
        t1 = time.time()
        cols, P = d["cols"], d["P"].to_numpy(float)
        y, masks = np.asarray(d["y"], float), d["masks"]
        combos = FC.enumerate_combos(len(cols), KMAX)
        total += len(combos)
        R = run_search(P, y, masks, cols, combos)
        n = len(P)
        lo = max(1, int(n * MIN_SHIFT_FRAC)) if name == "T1_breakout" else MIN_SHIFT_D
        shifts = [int(rng.integers(lo, n - lo)) for _ in range(n_placebo)]
        with ProcessPoolExecutor(max_workers=4) as ex:
            nulls = list(ex.map(_placebo_job, [(P, y, masks, cols, combos, s) for s in shifts]))
        null_val = np.concatenate([z[:, 1] for z in nulls])
        R["p"] = FC.empirical_p(R["val_auc"].to_numpy(float), null_val)
        bench_val, bench_ba = 0.5, None
        if name.startswith("T3"):
            b = _row(R, (cols.index("T1"),)).iloc[0]
            bench_val, bench_ba = float(b["val_auc"]), float(b["val_ba"])
        margin, min_auc, ba_min = {"T1": (0.05, 0.55, None), "T2": (0.10, 0.60, 0.55), "T3": (0.03, None, bench_ba)}[name[:2]]
        R = FC.gate_stats(R, bench_val, margin, min_auc, ba_min, Q_FDR)
        # 对照当作真实数据走同样的门槛（p 对其余对照算）
        pc = []
        for i, z in enumerate(nulls):
            other = np.concatenate([nulls[k][:, 1] for k in range(len(nulls)) if k != i])
            Z = pd.DataFrame({"disc_auc": z[:, 0], "val_auc": z[:, 1], "val_ba": z[:, 2]})
            Z["p"] = FC.empirical_p(Z["val_auc"].to_numpy(float), other)
            Z = FC.gate_stats(Z, bench_val, margin, min_auc, ba_min, Q_FDR)
            pc.append((int(Z["g1"].sum()), int(Z["g123"].sum())))
        results[name] = R
        summary[name] = {"n_factors": len(cols), "n_combos": len(combos), "bench_val_auc": bench_val, "bench_val_ba": bench_ba,
                         "g1": int(R["g1"].sum()), "g123": int(R["g123"].sum()),
                         "placebo_g1": [a for a, _ in pc], "placebo_g123": [b for _, b in pc], "shifts": shifts,
                         "best": R.sort_values("val_auc", ascending=False).head(10)}
        print(f"{name}: {len(combos)} 个组合，G1 {int(R['g1'].sum())}、G1〜G3 {int(R['g123'].sum())}；对照 G1〜G3 平均 "
              f"{np.mean([b for _, b in pc]):.1f}；{time.time() - t1:.0f}s", flush=True)
    return report(tg, results, summary, total, ctx, p, head, t0)


def _hold_eval(d: dict, R: pd.DataFrame) -> pd.DataFrame:
    """G4：只对通过 G1〜G3 的组合（和现行）算留出期（方向与平衡准确率的门槛都用发现期定的）。"""
    P, y = d["P"].reset_index(drop=True), np.asarray(d["y"], float)
    dm, m = d["masks"]["disc"], d["masks"]["hold"]
    A = FC.signed(P, FC.directions(P, pd.Series(y), dm))
    out = R.copy()
    ha, hba, hn = [], [], []
    for c in out["combo"]:
        s = FC.combo_score(A, c)
        a, n1, n0 = FC.auc(s[m], y[m])
        ha.append(a)
        hn.append((n1, n0))
        thr = FC.ba_threshold(s[dm], y[dm])
        hba.append(FC.balanced_accuracy(s[m], y[m], thr) if np.isfinite(thr) else float("nan"))
    out["hold_auc"], out["hold_ba"], out["hold_n"] = ha, hba, hn
    return out


def report(tg, results, summary, total, ctx, p, head, t0) -> int:
    say(f"\n总组合数 {total:,}（组合上限 3 个因子）。随机对照 {len(next(iter(summary.values()))['shifts'])} 次（全部因子同一偏移循环错开）。")
    say("\n| 目标 | 因子 | 组合 | 现行的验证期 AUC | 验证期 AUC 最高的组合 | BH 显著（G1） | G1〜G3 | 随机对照 G1〜G3 平均 / 最多 |")
    say("|---|---|---|---|---|---|---|---|")
    wl, out_json, csv_rows = [], {}, []
    for name, R in results.items():
        s = summary[name]
        d = tg[name]
        cols = d["cols"]
        best = s["best"].iloc[0]
        say(f"| {TARGETS[name]} | {s['n_factors']} | {s['n_combos']:,} | {s['bench_val_auc']:.3f} | "
            f"{' + '.join(('' if sg > 0 else '−') + cols[j] for j, sg in zip(best['combo'], best['signs']))}：{best['val_auc']:.3f}（p {best['p']:.4f}） | {s['g1']} | {s['g123']} | "
            f"{np.mean(s['placebo_g123']):.1f} / {max(s['placebo_g123'])} |")
        for r in R.itertuples():
            csv_rows.append({"target": name, "combo": " + ".join(cols[j] for j in r.combo), "k": r.k,
                             "signs": "".join("+" if x > 0 else "−" for x in r.signs), "disc_auc": r.disc_auc, "val_auc": r.val_auc,
                             "val_ba": r.val_ba, "p": r.p, "g1": r.g1, "g2": r.g2, "g3": r.g3})
    say("\n读法：「随机对照」= 因子与目标的时间关系被打乱之后，同样的流程偶然能过 G1〜G3 的组合个数。真实数据的个数要明显超过它才有意义。")
    import adaptive_study as AD
    import capital_study as CS
    import combo_study as CB
    run = base = None
    for name, R in results.items():
        d = tg[name]
        cols = d["cols"]
        surv = R[R["g123"]]
        say(f"\n## {TARGETS[name]}")
        top = R.sort_values("val_auc", ascending=False).head(8)
        say("| 组合（方向） | 发现期 AUC | 验证期 AUC / 平衡准确率 | 经验 p | G1 / G2 / G3 |")
        say("|---|---|---|---|---|")
        for r in top.itertuples():
            say(f"| {_combo_label(cols, r.combo, r.signs)} | {r.disc_auc:.3f} | "
                f"{r.val_auc:.3f} / {r.val_ba:.3f} | {r.p:.4f} | {'✓' if r.g1 else '✗'} / {'✓' if r.g2 else '✗'} / {'✓' if r.g3 else '✗'} |")
        info = {"summary": {k: v for k, v in summary[name].items() if k != "best"}, "survivors": []}
        if len(surv):
            H4 = _hold_eval(d, surv)
            bench_h = 0.5
            if name.startswith("T3"):
                bench_h = float(_hold_eval(d, _row(R, (cols.index("T1"),)))["hold_auc"].iloc[0])
            H4["g4"] = H4["hold_auc"] >= max(0.5, bench_h)
            H4 = H4.sort_values("val_auc", ascending=False)
            say(f"G1〜G3 通过 {len(surv)} 个 → 留出期（现行 {bench_h:.3f}）：G4 通过 {int(H4['g4'].sum())} 个"
                + ("（下面只列验证期 AUC 最高的 30 个；全部见 json）" if len(H4) > 30 else ""))
            for i, r in enumerate(H4.itertuples()):
                g5 = None
                if r.g4 and (name == "T1_breakout" or name.endswith("top") or name.startswith("T3")):
                    if run is None:
                        run = AD.make_runner(ctx["data_n"])
                        B = run(ctx["ind"], p)
                        base = _summ(B["equity"], CS)
                    g5 = _s0c2(name, d, r.combo, run, ctx, p, base, CS, CB)
                ok = bool(r.g4) and (g5 is None or not g5["fails"])
                item = {"target": name, "combo": [cols[j] for j in r.combo], "signs": list(r.signs), "label": _combo_label(cols, r.combo, r.signs),
                        "disc_auc": r.disc_auc, "val_auc": r.val_auc, "val_ba": r.val_ba, "p": r.p, "hold_auc": r.hold_auc,
                        "hold_ba": r.hold_ba, "hold_n": list(r.hold_n), "g4": bool(r.g4), "s0c2": g5, "pass": ok}
                info["survivors"].append(item)
                if i < 30:
                    say(f"- {item['label']}：验证期 AUC {r.val_auc:.3f}、留出期 {r.hold_auc:.3f}（正 / 负 {r.hold_n[0]} / {r.hold_n[1]}）"
                        + ("" if r.g4 else " → G4 不通过") + (f"；S0C2 {g5['text']}" if g5 else "")
                        + (" → **进前向观察名单**" if ok else (" → G5 不通过" if r.g4 else "")))
                if ok:
                    wl.append(item)
        else:
            say("没有组合通过 G1〜G3（留出期没有打开）。")
        out_json[name] = info
    say(f"\n**进前向观察名单的组合：{len(wl)} 个**" + ("（另行登记前向记录，要用户确认；模拟盘不改）" if wl else "（没有 → 维持现行）"))
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "factor_combo_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "total": total, "targets": out_json}, ensure_ascii=False, indent=1,
                                             default=_js), encoding="utf-8")
    pd.DataFrame(csv_rows).round(4).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    (paths.out_dir() / "factor_combo_watchlist.json").write_text(json.dumps({"code": head, "watch": wl}, ensure_ascii=False, indent=1,
                                                                            default=_js), encoding="utf-8")
    return 0


def _js(o):
    return o.item() if hasattr(o, "item") else str(o)


def _summ(eq: pd.Series, CS) -> dict:
    return {"all": CS.seg_stats(eq), "val": CS.seg_stats(eq, V_START, V_END), "hold": CS.seg_stats(eq, HOLD)}


def _s0c2(name, d, combo, run, ctx, p, base, CS, CB) -> dict:
    """G5：①跳过分数低于发现期 1/3 分位的买点；②顶 / ③ 分数 ≥ 发现期 80 分位 → 日本个股新仓 ×0.5。"""
    cols = d["cols"]
    if name == "T1_breakout":
        SIG, rows = d["sig_all"], d["sig_rows"]
        sign = FC.directions(d["P"], pd.Series(np.asarray(d["y"], float)), d["masks"]["disc"])
        A = FC.signed(SIG[cols], sign)
        s = FC.combo_score(A, combo)
        dm = FC.purge_mask(pd.DatetimeIndex(rows["date"]), *P1["disc"])
        thr = float(np.nanquantile(s[dm], SKIP_Q))
        drop = {(t, dd) for t, dd, v in zip(rows["ticker"], rows["date"], s) if np.isfinite(v) and v < thr}
        ind2 = {}
        for t, df in ctx["ind"].items():
            bad = df.index.isin([dd for (tt, dd) in drop if tt == t]) & df["entry"].astype(bool).to_numpy()
            if bad.any():
                df = df.copy()
                df.loc[bad, "entry"] = False
            ind2[t] = df
        r = run(ind2, p)
    else:
        sign = FC.directions(d["P"], pd.Series(np.asarray(d["y"], float)), d["masks"]["disc"])
        A = FC.signed(d["P"], sign)
        s = pd.Series(FC.combo_score(A, combo), index=d["dates"])
        thr = float(np.nanquantile(s.to_numpy()[d["masks"]["disc"]], HOT_Q))
        g = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ctx["ind"].values()])))
        v = s.reindex(s.index.union(g)).ffill().reindex(g)
        fac = pd.Series(np.where(v.to_numpy() >= thr, HALF, 1.0), index=g)
        r = run(ctx["ind"], p, scale=CB.fill_scale(fac, g))
    x = _summ(r["equity"], CS)
    c = lambda z: -9.0 if z is None else float(z)                                                   # noqa: E731
    f = []
    if c(x["val"]["calmar"]) < c(base["val"]["calmar"]) + CALMAR_UP:
        f.append(f"验证期 Calmar {x['val']['calmar']} < 现行 {base['val']['calmar']} + {CALMAR_UP}")
    for k, lab in (("all", "20 年"), ("hold", "留出期")):
        if c(x[k]["calmar"]) < c(base[k]["calmar"]):
            f.append(f"{lab} Calmar {x[k]['calmar']} < 现行 {base[k]['calmar']}")
    if x["all"]["dd"] is None or base["all"]["dd"] is None or x["all"]["dd"] < base["all"]["dd"] - DD_TOL:
        f.append(f"20 年回撤 {x['all']['dd']}% 比现行 {base['all']['dd']}% 深 {DD_TOL} pp 以上")
    return {"stats": x, "base": base, "fails": f,
            "text": f"20 年 {x['all']['cagr']}% / {x['all']['dd']}% / Calmar {x['all']['calmar']}（现行 {base['all']['calmar']}）；"
                    f"验证期 Calmar {x['val']['calmar']}（现行 {base['val']['calmar']}）；留出期 {x['hold']['calmar']}（现行 {base['hold']['calmar']}）"
                    + ("" if not f else "；✗ " + "；".join(f))}


if __name__ == "__main__":
    raise SystemExit(main())
