"""ml_study.py — 用 10 年的全部数据训练「买哪只之后会涨」（入场）与「什么时候差不多到顶该卖」（出场）的模型，
结合当时已知的全部因子（个股技术面、J-Quants 基本面、利率 / 汇率 / 国债 / 油价的敏感度 × 当时的变化、30 个市场层因子），
参数与因子配比用走动训练（walk-forward）学出来（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

用户：「通过现在 10 年的所有数据训练出一个接下来可以判断哪个股票买后一段时间会涨，哪个时候差不多到顶该卖了等等，要结合当时的所有因子
（利率、换汇、国债收益率等等），调整参数配比什么的进行横展开，要认真分析」。

一、数据与股票池（与 scripts/pit_retrain_study.py 同一套，qbreak/pit_data.py；原始数据只在 var/cache/jquants/，不入库）
  J-Quants 批量日线 2016-09-26〜2026-09-25（拆股调整、一手按当时真实股价）；时点股票池（月末上市一览，严格早于那天的快照）：
  训练 / 排名用 U2 时点 TOPIX 1000（出现过 1,378 只）；交易候选用 U1 时点 TOPIX 500（与上一项研究的「现行」同一口径）。
  基本面：決算短信（予想修正、增益率、当期予想利润）、信用余额、空売り残高報告（qbreak/jq_data.py 的口径：开示日严格早于那天）。
  宏观：scripts/factor_combo_study.market_panels 的日本这一套 30 个市场层因子（各自按日本收盘时已知对齐）。
二、特征（72 个，全部是那天收盘时已知的值；个股特征每天在 U2 成员里做截面百分位，市场层用扩张百分位，缺值 = 中间）
  T 技术面 11：T01〜T05 过去 5 / 20 / 60 / 120 / 250 日收益、T06 / T07 20 / 60 日波动、T08 离一年低点、T09 20 日成交额（对数）、
    T10 市值（对数）、T11 今天是不是现行突破信号
  S 现行买点因子 15：qbreak/signal_score.py 的 15 个（量比、箱体、突破距离、出货日、上影线、相对强度、离 200 日线、离一年高点、
    波动收缩、日経离 200 日线、行业动量 / 广度 / 共振 / 相对行业 / 行业 20 日；行业 = 东证 33 业种）
  F 基本面 6：F1 予想修正、F2 利润增益率、F3 信用买残 ÷ 均量、F4 信用卖残 ÷ 均量、F5 大额空头合计、F6 予想利润 ÷ 市值（利润收益率）
  X 宏观敏感度 10：X1〜X5 过去 250 日对 日経 / USD/JPY / 美 10Y / 日本 10Y / WTI 日变化的 β；X6〜X10 = 各 β × 该因子最近 60 日的变化
    （「现在的利率、汇率、国债、油价走势对这只票是顺风还是逆风」）
  M 市场层 30：Q1〜H1（量化状态层、牛熊、宏观层、利率 / 国债、信用、VIX、就业、威胁指数、能源消费、健康度）
三、目标
  入场：每周最后一个交易日、U2 成员 → 下一交易日开盘买、H 个交易日后开盘的对数收益减当天全部样本的平均（超额收益），H = 20 / 60；
    模型学的是它在当天的截面百分位。退市的票按最后收盘结算。
  出场：U2 上现行规则的独立突破交易（每只票单独、一次一仓），持仓中的每一天 → 「再拿 20 个交易日会不会跌 ≥ 5%」
    （下一交易日开盘 → 20 个交易日后收盘 ≤ −5% = 1）。
四、模型与走动训练（参数候选事先固定，不做无界网格搜索）
  R 岭回归（出场用 L2 逻辑回归），惩罚 α ∈ {0.01, 0.1, 1}（× 行数）；
  G 梯度提升树（qbreak/ml.HistGBM：深度 3、学习率 0.05、32 个分桶、每棵树抽 50% 行 / 80% 特征、叶子最少 max(100, 0.5% 行)、λ = 1），
    树的个数 ∈ {50, 100, 200}。
  每年最后一个交易日重新训练（2018〜2025 共 8 次），用那天为止结果已经完全揭晓的样本（样本日 + 目标期 < 训练日，不偷看）；
  超参数在训练数据的最后 12 个月上挑（内层验证：入场 = 每周秩相关的平均，出场 = AUC），再用全部训练数据重训，预测下一年。
  → 样本外预测 2019-01〜2026-09。验证期 = 2019-01〜2023-09（挑模型与 H），留出期 = 2023-10〜2026-09（两个半段 2025-03 / 2025-04）。
五、评价（描述 + 判定用）
  入场：样本外每周秩相关 IC（预测 vs 实际超额收益）的平均与 95% 区间（按月 / 季重抽样的自助法 2,000 次，种子 20260927）、
    前 1/5 − 后 1/5 的平均超额收益；R / G × H20 / H60 四个组合里验证期平均 IC 最高的 → 交易候选用它。
  出场：样本外 AUC；L / G 里验证期 AUC 高的 → 交易候选用它。
  分析（只描述）：每个个股特征自己的 IC（验证期 / 留出期，两期同号？）；分组置换重要性（T / S / F / X 在同一天内打乱，M 在日期之间打乱，
    看验证期 IC 掉多少）；模型 IC 按宏观状态（日本 10Y / 美 10Y 水平与变化、日元、牛熊）分组。
六、交易候选（S0C2 与模拟盘同一套设定 = var/sim.json：立花、¥100 万、4 名额 × 25%、一手放宽 50%、1655 牛熊择时、各层倍数；U1、现行参数 P0）
  K1 排序：同一天有多个突破信号时，按入场模型分数高的先买（现行是按代码）
  K2 过滤：入场分数低于该次训练样本预测 1/3 分位的突破信号不买
  K3 模型选股（替换突破）：每周最后一个交易日，U1 里分数最高的 5 只作为买点（名额空了才买，分数高的先）；持有 H 个交易日到期卖，
     保留 7% 止损，关掉 MACD 死叉 / 放量阴线 / 止盈 / 跟踪止损
  K4 出场模型：持仓那天收盘时出场模型的「跌 ≥ 5%」概率 ≥ 该次训练样本预测的 90 分位 → 下一交易日开盘卖（其余出场规则照旧）
  K5 组合：K1 / K2 里过了 V 的（两个都过取验证期 Calmar 高的）+ K4（只有 K4 也过了 V 才有）
  2019 以前没有模型分数 → K1 / K2 / K4 与现行完全一样。
  「现行」= P0 + U1 同一套设定。
  V 验证期（2019-01〜2023-09）：Calmar > 现行，且最大回撤不比现行深 2 pp 以上 → 才看留出期；
  H 留出期（2023-10〜）与两个半段各自：Calmar ≥ 现行 + 0.05，且最大回撤不比现行深。
  都满足 → 通过；多个通过 → 提议验证期 Calmar 最高的（一样高取编号小的）。通过也只是提议：模拟盘改不改要用户在对话里确认；
  都不通过 → 维持现行。
七、局限：只有 10 年；日経225 没有时点成分（交易用 TOPIX 500 代替）；调整后价不含分红；截面预测的 IC 通常很小（0.02〜0.05 就算有用），
  4 个名额的组合很难把小的 IC 变成收益；市场层因子在同一天对所有票一样，只能通过和个股特征的交互起作用（树模型）或在出场模型里起作用；
  以前的研究（jq_study、factor_combo_study、pit_retrain_study）在同一段数据上做过很多检验，留出期不是完全没见过的数据；税前。
登记前做过的检查：tests/test_ml.py（排名、岭回归、梯度提升树学得会已知的非线性关系、缺值、分层预测、IC 与 Spearman 一致、自助法）与
  tests/test_ml_study.py（每周样本日、前向收益与退市结算、走动训练的训练 / 测试划分不偷看、空头合计的快速算法与原算法一致、
  利润收益率只用开示日之前的予想、β 的算法、候选的构造与门槛、出场模型下一交易日开盘卖）；合成数据（假的 S0C2）全流程试跑；
  --coverage 只看特征与样本的行数和覆盖率，没有算任何特征与收益的关系。覆盖（2026-09-27）：特征 72 个（个股 42 + 市场层 30）；
  U2 1,378 只、U1 581 只；每周样本日 507 个；入场样本 484,622 行（H20 有目标 479,835、H60 471,405）；出场样本 = 独立突破交易 2,227 笔的
  持仓日 24,514 行（有目标 24,449）；U1 每天的打分行 883,478；覆盖率最低的特征 F2 88%、S09 / T05 92%、S08 / F6 93%，其余 ≥ 94%。
输出：var/out/ml_study.md / .json（只有统计，不含原始数据）
"""
from __future__ import annotations

import json
import multiprocessing as mp
import subprocess
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capital_study as CS                                                   # noqa: E402
import jq_study as JS                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import ml                                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import pit_data as PD                                            # noqa: E402

WINDOW, TRADE_START = PRS.WINDOW, PRS.TRADE_START
VAL, HOLD = ("2019-01-01", "2023-10-01"), ("2023-10-01", None)
H1, H2 = ("2023-10-01", "2025-04-01"), ("2025-04-01", None)
REFIT_YEARS = tuple(range(2018, 2026))
HORIZONS = (20, 60)
EXIT_H, EXIT_DROP = 20, -0.05
ALPHAS = (0.01, 0.1, 1.0)
GBM_KW = {"n_trees": 200, "lr": 0.05, "depth": 3, "n_bins": 32, "subsample": 0.5, "colsample": 0.8, "l2": 1.0}
STAGES = (50, 100, 200)
MIN_LEAF_FRAC, MIN_LEAF_MIN = 0.005, 100
K2_Q, K4_Q, K3_TOP = 1 / 3, 0.90, 5
CALMAR_UP, DD_TOL = 0.05, 2.0
N_BOOT, SEED = 2000, 20260927
CKPT_NAME = "ml_study_ckpt.pkl"
T_FEATS = {"T01": "过去 5 日收益", "T02": "过去 20 日收益", "T03": "过去 60 日收益", "T04": "过去 120 日收益", "T05": "过去 250 日收益",
           "T06": "20 日波动", "T07": "60 日波动", "T08": "离一年低点", "T09": "20 日成交额（对数）", "T10": "市值（对数）",
           "T11": "今天是现行突破信号"}
S_KEYS = ["vol", "tight", "brk", "dist", "shadow", "rs", "trend", "high", "squeeze", "mkt",
          "ind_mom60", "ind_breadth", "ind_cobreak", "rel_ind60", "ind_mom20"]
S_FEATS = {f"S{i:02d}": k for i, k in enumerate(S_KEYS, 1)}
F_FEATS = {"F1": "会社予想修正", "F2": "利润增益率", "F3": "信用买残 ÷ 均量", "F4": "信用卖残 ÷ 均量", "F5": "大额空头合计", "F6": "予想利润 ÷ 市值"}
X_FACT = ("mkt", "fx", "us10y", "jgb", "oil")
X_FEATS = {"X1": "β 日経", "X2": "β USD/JPY", "X3": "β 美 10Y", "X4": "β 日本 10Y", "X5": "β WTI",
           "X6": "β 日経 × 日経 60 日", "X7": "β USD/JPY × USD/JPY 60 日", "X8": "β 美 10Y × 美 10Y 60 日变化",
           "X9": "β 日本 10Y × 日本 10Y 60 日变化", "X10": "β WTI × WTI 60 日"}
GROUPS = {"T": list(T_FEATS), "S": list(S_FEATS), "F": list(F_FEATS), "X": list(X_FEATS)}
LINES: list[str] = []
G: dict = {}                                                                  # 进程池（fork）共享


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ────────────────────────── 可测试的小函数 ──────────────────────────
def week_ends(days: pd.DatetimeIndex, start: str) -> pd.DatetimeIndex:
    """每个 ISO 周的最后一个交易日（start 之后）。"""
    d = pd.DatetimeIndex(days)
    d = d[d >= pd.Timestamp(start)]
    iso = d.isocalendar()
    key = (iso["year"] * 100 + iso["week"]).to_numpy()
    return pd.DatetimeIndex(pd.Series(d, index=d).groupby(key).max().to_numpy())


def fwd_exit_price(o: np.ndarray, cf: np.ndarray) -> np.ndarray:
    """卖出价 = 那天的开盘价；那天没有 K 线（退市 / 停牌）→ 那天为止最后一个收盘（cf = 向前填过的收盘）。"""
    return np.where(np.isfinite(o), o, cf)


def fold_split(t_idx: np.ndarray, end_idx: np.ndarray, dates: pd.DatetimeIndex, refit: pd.Timestamp, next_refit: pd.Timestamp,
               days: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """一次重训：训练 = 目标期结束 ≤ 训练日（结果完全揭晓）；内层 = 训练里「目标期结束 ≤ 训练日前 365 天」的拟合、
    「样本日在最后 365 天」的验证；测试 = 样本日在 (训练日, 下一次训练日]。返回四个布尔掩码。"""
    r = int(days.searchsorted(refit, side="right")) - 1
    r_in = int(days.searchsorted(refit - pd.Timedelta(days=365), side="right")) - 1
    d = pd.DatetimeIndex(dates)
    train = end_idx <= r
    inner_fit = end_idx <= r_in
    inner_val = train & (d > refit - pd.Timedelta(days=365))
    test = (d > refit) & (d <= next_refit)
    return train, inner_fit, inner_val, test


def short_sum_fast(R: pd.DataFrame, dates, keep_days: int = 365) -> np.ndarray:
    """jq_data.short_features 的快速版（同一口径）：各报告者最近一次报告的比例之和 %（开示日 < 那天、≤ keep_days 天、≥ 0.5%）。"""
    D = pd.DatetimeIndex(dates)
    out = np.zeros(len(D))
    if R is None or R.empty:
        return out
    r = R.assign(date=pd.to_datetime(R["DiscDate"]), p=pd.to_numeric(R["ShrtPosToSO"], errors="coerce")).dropna(subset=["p"])
    r = r.sort_values("date", kind="mergesort")
    rd, rn, rp = r["date"].to_numpy("datetime64[ns]"), r["SSName"].astype(str).to_numpy(), r["p"].to_numpy(float)
    order = np.argsort(D.to_numpy("datetime64[ns]"), kind="mergesort")
    latest: dict[str, tuple] = {}
    k = 0
    keep = np.timedelta64(keep_days, "D")
    for i in order:
        s = D.to_numpy("datetime64[ns]")[i]
        while k < len(rd) and rd[k] < s:
            latest[rn[k]] = (rd[k], rp[k])
            k += 1
        tot = sum(p for (dt, p) in latest.values() if dt >= s - keep and p >= 0.005)
        out[i] = tot * 100
    return out


def latest_forecast(ev: pd.DataFrame, dates, stale_days: int = 200) -> np.ndarray:
    """那天之前（开示日严格早于）最近一次有值的予想利润（fins_events 的 fc）；离那天 > stale_days 天 → 缺值。"""
    D = pd.DatetimeIndex(dates)
    if ev is None or ev.empty:
        return np.full(len(D), np.nan)
    e = ev[np.isfinite(ev["fc"].to_numpy(float))].sort_values("date", kind="mergesort")
    t, fc = e["date"].to_numpy("datetime64[ns]"), e["fc"].to_numpy(float)
    k = np.searchsorted(t, D.to_numpy("datetime64[ns]"), side="left") - 1
    out = np.where(k >= 0, fc[np.clip(k, 0, None)], np.nan) if len(t) else np.full(len(D), np.nan)
    if len(t):
        age = D.to_numpy("datetime64[ns]") - t[np.clip(k, 0, None)]
        out = np.where((k >= 0) & (age <= np.timedelta64(stale_days, "D")), out, np.nan)
    return out


def rolling_beta(R: pd.DataFrame, f: pd.Series, win: int = 250, min_n: int = 200) -> pd.DataFrame:
    """各列（个股日收益）对因子日变化 f 的滚动 β = cov / var（当天为止 win 天；两边都有值的日子 ≥ min_n）。"""
    f = f.reindex(R.index)
    ok = R.notna() & f.notna().to_numpy()[:, None]
    Rm = R.where(ok)
    Fm = pd.DataFrame(np.where(ok, f.to_numpy()[:, None], np.nan), index=R.index, columns=R.columns)
    n = ok.astype(float).rolling(win, min_periods=1).sum()
    mr, mf = Rm.rolling(win, min_periods=min_n).mean(), Fm.rolling(win, min_periods=min_n).mean()
    mrf = (Rm * Fm).rolling(win, min_periods=min_n).mean()
    mff = (Fm * Fm).rolling(win, min_periods=min_n).mean()
    var = mff - mf ** 2
    return ((mrf - mr * mf) / var.where(var > 0)).where(n >= min_n)


def cs_rank(W: pd.DataFrame, member: pd.DataFrame) -> pd.DataFrame:
    """每天在成员里的截面百分位 (平均秩 − 0.5) ÷ 个数 − 0.5；非成员 / 缺值 → 缺值。"""
    X = W.where(member.reindex(index=W.index, columns=W.columns).fillna(False).astype(bool))
    r = X.rank(axis=1, method="average")
    n = X.notna().sum(axis=1)
    return (r - 0.5).div(n.where(n > 0), axis=0) - 0.5


def _c(x) -> float:
    return -9.0 if x is None else float(x)


def stats(eq: pd.Series) -> dict:
    return {"all": CS.seg_stats(eq, TRADE_START), "va": CS.seg_stats(eq, *VAL), "ho": CS.seg_stats(eq, HOLD[0]),
            "h1": CS.seg_stats(eq, *H1), "h2": CS.seg_stats(eq, H2[0])}


def v_fails(r: dict, base: dict) -> list[str]:
    f = []
    if not _c(r["va"]["calmar"]) > _c(base["va"]["calmar"]):
        f.append(f"验证期 Calmar {r['va']['calmar']} ≤ 现行 {base['va']['calmar']}")
    if r["va"]["dd"] is None or base["va"]["dd"] is None or r["va"]["dd"] < base["va"]["dd"] - DD_TOL:
        f.append(f"验证期最大回撤 {r['va']['dd']}% 比现行 {base['va']['dd']}% 深 {DD_TOL} pp 以上")
    return f


def h_fails(r: dict, base: dict) -> list[str]:
    f = []
    for k, lab in (("ho", "留出期"), ("h1", "留出期前半"), ("h2", "留出期后半")):
        if _c(r[k]["calmar"]) < _c(base[k]["calmar"]) + CALMAR_UP:
            f.append(f"{lab} Calmar {r[k]['calmar']} < 现行 {base[k]['calmar']} + {CALMAR_UP}")
        if r[k]["dd"] is None or base[k]["dd"] is None or r[k]["dd"] < base[k]["dd"]:
            f.append(f"{lab}最大回撤 {r[k]['dd']}% 比现行 {base[k]['dd']}% 深")
    return f


def choose(passed: dict[str, dict]) -> str | None:
    return max(passed, key=lambda k: (_c(passed[k]["va"]["calmar"]), -int(k[1:]))) if passed else None


def top_k_entries(scores: pd.DataFrame, k: int) -> pd.DataFrame:
    """每一行（日期）分数最高的 k 只 → True（没有分数的不算）。"""
    r = scores.rank(axis=1, ascending=False, method="first")
    return (r <= k) & scores.notna()


# ────────────────────────── 引擎：退市 + 出场模型 ──────────────────────────
class MLEngine(PRS.PitEngine):
    EXIT: dict[str, set] = {}                                                 # 票 → 出场模型触发的日期（收盘时）→ 下一交易日开盘卖

    def _exec_exits(self, m: str, i: int) -> None:
        if i > 0 and MLEngine.EXIT:
            prev = self.gidx[i - 1]
            for t in list(self.st.pos):
                if prev in MLEngine.EXIT.get(t, ()) and t not in self.st.pending_exit:
                    self.st.pending_exit[t] = "ml_exit"
        super()._exec_exits(m, i)


def make_runner(closes_all: pd.DataFrame):
    """S0C2（var/sim.json 同一套设定，经 config_from_sim；一手按真实股价；退市日卖出）。run(ind, p, prio=None, exit_flags=None)。"""
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

    def run(ind: dict, p, prio: dict | None = None, exit_flags: dict | None = None) -> dict:
        names = list(ind)
        key = tuple(names)
        if key not in em_cache:
            g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
            M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")), use_sector=bool(flag("use_sector_tilt")),
                                    use_events=False, closes=closes_all.reindex(index=g, columns=names))
            M = M * qr.reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
            em_cache[key] = pd.DataFrame(M, index=g, columns=names)
        JS.RealLotEngine.RATIO, JS.RealLotEngine.LAST = G.get("ratio", {}), []
        MLEngine.EXIT = exit_flags or {}
        Z._PrioEngine.PRIO = prio
        try:
            eng = MLEngine({**ind, "1655.T": core}, cfg, {"JP": p, "US": us}, ex, cc, fx=fxdf[["Open", "Close"]],
                           entry_mult={"JP": em_cache[key]}, bear=bear)
            r = eng.run(start=TRADE_START)
        finally:
            Z._PrioEngine.PRIO, MLEngine.EXIT = None, {}
        tr = r.trades[r.trades["reason"] != "end"]
        stock = tr[tr["ticker"] != "1655.T"] if "ticker" in tr.columns else tr
        return {**stats(r.equity), "trades": int(len(stock)),
                "ml_exits": int((stock["reason"] == "ml_exit").sum()) if len(stock) and "reason" in stock.columns else 0,
                "win": round(float((stock["pnl"] > 0).mean()) * 100, 1) if len(stock) and "pnl" in stock.columns else None}
    run.cfg = cfg
    return run


# ────────────────────────── 特征面板 ──────────────────────────
def build_features(D: dict, names: list[str], days: pd.DatetimeIndex, ind: dict, ic: pd.Series,
                   member: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict]:
    """个股特征（宽表：日期 × 票，已做截面百分位）+ 市场层（日期 × 30，扩张百分位 − 0.5）+ 行情数组。"""
    import factor_combo_study as FS
    from qbreak import signal_score as SSc
    from qbreak.threat import us_asof_for_jp
    data = D["data"]
    C = pd.DataFrame({t: data[t]["Close"] for t in names}).reindex(days)
    O = pd.DataFrame({t: data[t]["Open"] for t in names}).reindex(days)
    V = pd.DataFrame({t: data[t]["Volume"] for t in names}).reindex(days)
    Cf = C.ffill(limit=5)
    lr = np.log(Cf).diff()
    raw: dict[str, pd.DataFrame] = {}
    for fid, k in zip(("T01", "T02", "T03", "T04", "T05"), (5, 20, 60, 120, 250)):
        raw[fid] = np.log(Cf / Cf.shift(k))
    raw["T06"] = lr.rolling(20, min_periods=15).std() * np.sqrt(252)
    raw["T07"] = lr.rolling(60, min_periods=45).std() * np.sqrt(252)
    raw["T08"] = Cf / Cf.rolling(250, min_periods=200).min() - 1
    raw["T09"] = np.log((C * V).rolling(20, min_periods=15).mean().where(lambda x: x > 0))
    cap = D["mktcap"].reindex(index=days, columns=[t.split(".")[0] + "0" for t in names]).ffill(limit=5)
    cap.columns = names
    raw["T10"] = np.log(cap.where(cap > 0))
    raw["T11"] = pd.DataFrame({t: ind[t]["entry"].astype(float) for t in names}).reindex(days)
    sector = {t: D["s33"].get(t.split(".")[0], "other") for t in names}
    sp = SSc.feature_panel(ind, ic, sector)
    for s, k in S_FEATS.items():
        raw[s] = sp[k].reindex(index=days, columns=names)
    fund = D["fund"]
    for fid in F_FEATS:
        raw[fid] = fund[fid].reindex(index=days.union(fund[fid].index)).ffill(limit=10).reindex(index=days, columns=names)
    # 宏观敏感度：日本交易日对齐（美国的值 = 那天之前最后一个美国收盘；日本 10Y = 前一个营业日）
    ti = D["macro_raw"]
    icd = ic.reindex(days.union(ic.index)).ffill().reindex(days)
    fx = us_asof_for_jp(ti["fx"], days)
    u10 = us_asof_for_jp(ti["dgs10"], days)
    jg = ti["jgb"].shift(1)
    jg = jg.reindex(days.union(jg.index)).ffill().reindex(days)
    oil = us_asof_for_jp(ti["wti"].where(ti["wti"] > 0), days)
    fac_d = {"mkt": np.log(icd).diff(), "fx": np.log(fx).diff(), "us10y": u10.diff(), "jgb": jg.diff(), "oil": np.log(oil).diff()}
    fac_60 = {"mkt": np.log(icd / icd.shift(60)), "fx": np.log(fx / fx.shift(60)), "us10y": u10 - u10.shift(60),
              "jgb": jg - jg.shift(60), "oil": np.log(oil / oil.shift(60))}
    for i, k in enumerate(X_FACT, 1):
        b = rolling_beta(lr, fac_d[k])
        raw[f"X{i}"] = b
        raw[f"X{i + 5}"] = b.mul(fac_60[k], axis=0)
    feats = {fid: cs_rank(W, member).astype("float32") for fid, W in raw.items()}
    Mraw = FS.market_panels()[0]["JP"]
    Mp = FS._pct_panel(Mraw)
    M = (Mp.reindex(Mp.index.union(days)).ffill().reindex(days) - 0.5).astype("float32")
    arrays = {"O": O.to_numpy(float), "C": C.to_numpy(float), "Cf": C.ffill().to_numpy(float)}
    return feats, M, arrays


def load_fundamentals(D: dict, names: list[str], wk: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """每周最后一个交易日 × 票：F1〜F6（J-Quants 批量 CSV，本地缓存；口径 = qbreak/jq_data.py）。"""
    from qbreak import jq_data as JD
    codes = {t.split(".")[0] + "0" for t in names}
    base = JD.bulk_dir()
    fins = JD.read_bulk(sorted((base / "fins" / "summary").rglob("*.csv.gz")), JD.DATASETS["fins"][1], codes)
    marg = JD.read_bulk(sorted((base / "markets" / "margin-interest").rglob("*.csv.gz")), JD.DATASETS["margin"][1], codes)
    shrt = JD.read_bulk(sorted((base / "markets" / "short-sale-report").rglob("*.csv.gz")), JD.DATASETS["short"][1], codes)
    vol = PD.read_bars(PD.bar_files(), codes, ["Date", "Code", "Vo"])
    fb, mb, sb, vb = (dict(tuple(x.groupby("Code"))) for x in (fins, marg, shrt, vol))
    cols = {k: {} for k in F_FEATS}
    capw = D["mktcap"]
    for t in names:
        c5 = t.split(".")[0] + "0"
        ev = JD.fins_events(fb[c5]) if c5 in fb else pd.DataFrame(columns=["date", "fy", "fc", "rev", "yoy"])
        ff = JD.fins_features(ev, wk)
        cols["F1"][t], cols["F2"][t] = ff["g1"].to_numpy(float), ff["g2"].to_numpy(float)
        if c5 in mb and c5 in vb:
            mm = JD.margin_features(mb[c5], vb[c5], wk)
            cols["F3"][t], cols["F4"][t] = mm["m1"].to_numpy(float), mm["m2"].to_numpy(float)
        else:
            cols["F3"][t] = cols["F4"][t] = np.full(len(wk), np.nan)
        cols["F5"][t] = short_sum_fast(sb.get(c5), wk)
        fc = latest_forecast(ev, wk)
        cp = capw[c5].reindex(capw.index.union(wk)).ffill(limit=5).reindex(wk).to_numpy(float) if c5 in capw.columns else np.full(len(wk), np.nan)
        cols["F6"][t] = fc / (cp * 1e6)
    return {k: pd.DataFrame(v, index=wk) for k, v in cols.items()}


def gather(feats: dict[str, pd.DataFrame], M: pd.DataFrame, ri: np.ndarray, ci: np.ndarray) -> np.ndarray:
    """行（日期位置）× 列（票位置）→ 特征矩阵（72 列：个股 42 + 市场层 30）。"""
    X = np.empty((len(ri), len(feats) + M.shape[1]), np.float32)
    for j, W in enumerate(feats.values()):
        X[:, j] = W.to_numpy()[ri, ci]
    X[:, len(feats):] = M.to_numpy()[ri]
    return X


# ────────────────────────── 走动训练（进程池）──────────────────────────
def _fit_predict(args):
    """一次重训：task = entry_H / exit；model = R / G。返回测试行的预测、训练样本预测的分位、内层选的超参数、分组置换重要性。"""
    task, model, y_key, fold = args
    S = G["sets"][task]
    X, y = S["X"], S[y_key]
    tr, fit_in, val_in = S["folds"][fold]["train"], S["folds"][fold]["inner_fit"], S["folds"][fold]["inner_val"]
    tr = tr & np.isfinite(y)
    fit_in, val_in = fit_in & np.isfinite(y), val_in & np.isfinite(y)
    cls = task == "exit"
    dates = S["dates"]

    def score(pred, m):
        if cls:
            from qbreak.factor_combo import auc
            return auc(pred, y[m])[0]
        ic = ml.ic_by_date(pred, y[m], dates[m])
        return float(ic.mean()) if len(ic) else float("nan")
    n_all = int(tr.sum())
    ml_leaf = max(MIN_LEAF_MIN, int(MIN_LEAF_FRAC * max(1, fit_in.sum())))
    if model == "R":
        best = None
        for a in ALPHAS:
            if cls:
                from qbreak.threat import logit_fit
                w = logit_fit(np.nan_to_num(X[fit_in].astype(float)), y[fit_in], l2=a * fit_in.sum(), iters=30)
                pr = ml.sigmoid(w[0] + np.nan_to_num(X[val_in].astype(float)) @ w[1:])
            else:
                w = ml.ridge_fit(X[fit_in], y[fit_in], a)
                pr = ml.ridge_predict(w, X[val_in])
            sc = score(pr, val_in)
            if best is None or (np.isfinite(sc) and sc > best[1]):
                best = (a, sc)
        a = best[0]
        if cls:
            from qbreak.threat import logit_fit
            w = logit_fit(np.nan_to_num(X[tr].astype(float)), y[tr], l2=a * n_all, iters=30)
            predict = lambda Z: ml.sigmoid(w[0] + np.nan_to_num(Z.astype(float)) @ w[1:])     # noqa: E731
        else:
            w = ml.ridge_fit(X[tr], y[tr], a)
            predict = lambda Z: ml.ridge_predict(w, Z)                                       # noqa: E731
        hp = {"alpha": a, "inner": best[1]}
    else:
        loss = "logloss" if cls else "l2"
        g1 = ml.HistGBM(loss=loss, min_leaf=ml_leaf, seed=SEED + fold, **GBM_KW).fit(X[fit_in], y[fit_in])
        st = g1.predict_staged(X[val_in], STAGES)
        scs = {k: score(v, val_in) for k, v in st.items()}
        k_best = max(STAGES, key=lambda k: (scs[k] if np.isfinite(scs[k]) else -9, -k))
        g2 = ml.HistGBM(loss=loss, min_leaf=max(MIN_LEAF_MIN, int(MIN_LEAF_FRAC * n_all)), seed=SEED + 100 + fold,
                        **{**GBM_KW, "n_trees": k_best}).fit(X[tr], y[tr])
        predict = g2.predict
        hp = {"trees": k_best, "inner": scs[k_best]}
    out = {"hp": hp}
    ptr = predict(X[tr])
    out["q"] = {"q33": float(np.quantile(ptr, K2_Q)), "q90": float(np.quantile(ptr, K4_Q))}
    te = S["folds"][fold]["test"]
    out["test_pred"] = predict(X[te]).astype(float)
    for extra in S.get("extra", ()):                                         # 额外要打分的行（突破信号 / 每天的持仓候选）
        E = G["sets"][extra]
        m = E["folds"][fold]["test"]
        out[f"pred_{extra}"] = predict(E["X"][m]).astype(float)
    if not cls:                                                              # 分组置换重要性（测试行；同一天内打乱 / M 在日期之间打乱）
        rng = np.random.default_rng(SEED + fold)
        Xt, yt, dt = X[te], y[te], dates[te]
        base = ml.ic_by_date(out["test_pred"], yt, dt).mean()
        imp = {}
        cols = G["cols"]
        ud, first, inv = np.unique(dt, return_index=True, return_inverse=True)
        for gname, members in {**GROUPS, "M": G["m_cols"]}.items():
            jj = [cols.index(c) for c in members]
            Xp = Xt.copy()
            if gname == "M":                                                 # 市场层同一天相同 → 在日期之间打乱
                perm = rng.permutation(len(ud))
                Xp[:, jj] = Xt[first][:, jj][perm][inv]
            else:                                                            # 个股层 → 同一天之内打乱
                for d_i in range(len(ud)):
                    rows = np.flatnonzero(inv == d_i)
                    Xp[np.ix_(rows, jj)] = Xt[np.ix_(rng.permutation(rows), jj)]
            imp[gname] = float(base - ml.ic_by_date(predict(Xp), yt, dt).mean())
        out["imp"] = imp
    return (task, model, y_key, fold), out


def _pool():
    return ProcessPoolExecutor(max_workers=4, mp_context=mp.get_context("fork"))


# ────────────────────────── 主流程 ──────────────────────────
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true", help="只看特征与样本的行数、覆盖率（登记前用），不算任何特征与收益的关系")
    ap.add_argument("--resume", action="store_true", help="模型的样本外预测从上次的检查点（var/cache，不入库）接着算（中途出错后用）")
    a = ap.parse_args(argv)
    G["resume"] = a.resume
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/ml_study.py", "qbreak/ml.py", "qbreak/pit_data.py",
                            "scripts/pit_retrain_study.py", "scripts/factor_combo_study.py", "qbreak/jq_data.py", "qbreak/signal_score.py",
                            "qbreak/unified.py", "qbreak/engine.py", "qbreak/strategy.py", "var/sim.json", "var/best_params.json",
                            "var/best_params_JP.json"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    from bullbear_study import SYM, load
    from qbreak import factors
    from qbreak import threat as TH
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    D = PRS.load_data()
    days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in D["data"].values()])))
    days = days[(days >= pd.Timestamp(WINDOW[0])) & (days <= pd.Timestamp(WINDOW[1]))]
    names, masks = {}, {}
    for u in ("U1", "U2"):
        names[u], masks[u] = PRS.universe_members(D, u, days)
    delist = PRS.delist_dates({t: D["data"][t] for t in names["U2"]})
    nm = names["U2"]
    member = {u: pd.DataFrame({t: masks[u][t] for t in names[u]}).reindex(index=days).fillna(False).astype(bool) for u in ("U1", "U2")}
    bars = PD.read_bars(PD.bar_files(), {t.split(".")[0] + "0" for t in nm}, ["Date", "Code", "MktCap"])
    bars["MktCap"] = pd.to_numeric(bars["MktCap"], errors="coerce")
    D["mktcap"] = bars.pivot_table(index=pd.to_datetime(bars["Date"]), columns="Code", values="MktCap", aggfunc="last")
    del bars
    wk = week_ends(days, TRADE_START)
    p0 = load_params(market="JP")
    ic = load(*SYM["JP"])["Close"]
    ind = {t: compute_indicators(D["data"][t], p0, ic) for t in nm}
    ind_u2 = {t: PD.mask_entries(ind[t], masks["U2"][t]) for t in nm}
    ti = TH.load_inputs()
    D["macro_raw"] = {"fx": ti["fx"], "dgs10": ti["raw"]["DGS10"], "wti": ti["raw"]["DCOILWTICO"], "jgb": factors.jgb_curve()["10Y"].dropna()}
    D["fund"] = load_fundamentals(D, nm, wk)
    feats, M, arr = build_features(D, nm, days, ind_u2, ic, member["U2"])
    cols = list(feats) + [f"M_{c}" for c in M.columns]
    G.update({"cols": cols, "m_cols": [f"M_{c}" for c in M.columns]})
    col_of = {t: j for j, t in enumerate(nm)}
    di = {d: i for i, d in enumerate(days)}
    # ── 入场样本：每周最后一个交易日 × U2 成员 ──
    O, Cf = arr["O"], arr["Cf"]
    mw = member["U2"].reindex(index=wk, columns=nm).fillna(False).to_numpy(bool)
    wr, ci = np.nonzero(mw)
    ri = np.array([di[d] for d in wk])[wr]
    X_e = gather(feats, M, ri, ci)
    ent = {}
    n = len(days)
    for H in HORIZONS:
        j1, j2 = ri + 1, ri + 1 + H
        ok = j2 < n
        p_in = np.where(ok, O[np.clip(j1, 0, n - 1), ci], np.nan)
        p_out = np.where(ok, fwd_exit_price(O[np.clip(j2, 0, n - 1), ci], Cf[np.clip(j2, 0, n - 1), ci]), np.nan)
        r = np.log(p_out / p_in)
        dts = days[ri]
        ex = r - pd.Series(r).groupby(dts).transform("mean").to_numpy()
        ent[H] = {"ret": ex, "y": ml.rank_by_date(ex, dts), "end": ri + 1 + H}
    # ── 出场样本：U2 独立突破交易的持仓日 ──
    T = PRS.indep_trades(ind_u2, p0, delist)
    xr, xc = [], []
    for tr_ in T.itertuples():
        if tr_.ticker not in col_of:
            continue
        a_, b_ = di.get(pd.Timestamp(tr_.entry_date)), di.get(pd.Timestamp(tr_.exit_date))
        if a_ is None or b_ is None:
            continue
        for k in range(a_, b_):
            xr.append(k)
            xc.append(col_of[tr_.ticker])
    xr, xc = np.array(xr, int), np.array(xc, int)
    X_x = gather(feats, M, xr, xc)
    j1, j2 = xr + 1, xr + EXIT_H
    ok = j2 < n
    p_in = np.where(ok, O[np.clip(j1, 0, n - 1), xc], np.nan)
    p_out = np.where(ok, Cf[np.clip(j2, 0, n - 1), xc], np.nan)
    y_x = np.where(np.isfinite(p_in / p_out), (p_out / p_in - 1 <= EXIT_DROP).astype(float), np.nan)
    # ── 要打分的额外行：U1 成员每天（出场模型 K4）、U1 的突破信号日（K1 / K2）、每周 U1（K3）──
    u1d = member["U1"]
    start_i = int(days.searchsorted(pd.Timestamp(VAL[0])))
    dr, dc = np.nonzero(u1d.to_numpy()[start_i:])
    dr = dr + start_i
    u1cols = [col_of[t] for t in u1d.columns]
    dcc = np.array(u1cols)[dc]
    X_d = gather(feats, M, dr, dcc)
    if a.coverage:
        say(f"特征 {len(cols)} 个（个股 {len(feats)} + 市场层 {M.shape[1]}）；U2 {len(nm)} 只、U1 {len(names['U1'])} 只；每周样本日 {len(wk)} 个")
        say(f"入场样本 {len(ri):,} 行（H20 有目标 {int(np.isfinite(ent[20]['y']).sum()):,}、H60 {int(np.isfinite(ent[60]['y']).sum()):,}）；"
            f"出场样本（独立突破交易 {len(T):,} 笔的持仓日）{len(xr):,} 行（有目标 {int(np.isfinite(y_x).sum()):,}）；U1 每天的打分行 {len(dr):,}")
        cov = {c: float(np.isfinite(X_e[:, j]).mean()) for j, c in enumerate(cols)}
        low = sorted(cov.items(), key=lambda z: z[1])[:12]
        say("覆盖率最低的特征（入场样本里有值的比例）：" + "、".join(f"{c} {v * 100:.0f}%" for c, v in low))
        say(f"用时 {time.time() - t0:.0f}s")
        return 0
    return run_all(D, names, masks, member, days, wk, nm, col_of, feats, M, cols, ri, ci, X_e, ent, T, xr, xc, X_x, y_x,
                   dr, dcc, X_d, ind, p0, delist, head, t0)


def run_all(D, names, masks, member, days, wk, nm, col_of, feats, M, cols, ri, ci, X_e, ent, T, xr, xc, X_x, y_x,
            dr, dcc, X_d, ind, p0, delist, head, t0) -> int:
    say(f"# 全部因子的机器学习：入场（买哪只会涨）与出场（什么时候到顶）（{pd.Timestamp.today().date()}）")
    say("规则见 scripts/ml_study.py 开头（先提交后运行）；原始数据只在 var/cache/jquants/，这里只有统计。")
    refits = [days[days <= pd.Timestamp(f"{y}-12-31")][-1] for y in REFIT_YEARS]
    nexts = refits[1:] + [days[-1]]
    dts_e = days[ri]
    sets = {"entry": {"X": X_e, "dates": np.asarray(dts_e), "folds": []}, "exit": {"X": X_x, "dates": np.asarray(days[xr]), "folds": []},
            "daily": {"X": X_d, "folds": []}}
    for H in HORIZONS:
        sets["entry"][f"y{H}"] = ent[H]["y"]
    sets["exit"]["y"] = y_x
    for k, (rf, nx) in enumerate(zip(refits, nexts)):
        fe = {}
        for H in HORIZONS:
            tr, fi, vi, te = fold_split(ri, ent[H]["end"], dts_e, rf, nx, days)
            fe[H] = {"train": tr, "inner_fit": fi, "inner_val": vi, "test": te}
        sets["entry"]["folds"].append(fe)
        tr, fi, vi, te = fold_split(xr, xr + EXIT_H, days[xr], rf, nx, days)
        sets["exit"]["folds"].append({"train": tr, "inner_fit": fi, "inner_val": vi, "test": te})
        dd = days[dr]
        sets["daily"]["folds"].append({"test": np.asarray((dd > rf) & (dd <= nx))})
    # 入场：每个 H 一套 folds（S["folds"][fold] 要是一个 dict）→ 展开成 entry20 / entry60
    for H in HORIZONS:
        sets[f"entry{H}"] = {"X": X_e, "dates": sets["entry"]["dates"], "y": ent[H]["y"],
                             "folds": [f[H] for f in sets["entry"]["folds"]], "extra": ("daily",)}
    sets["exit"]["extra"] = ("daily",)
    G["sets"] = sets
    jobs = [(f"entry{H}", m, "y", k) for H in HORIZONS for m in ("R", "G") for k in range(len(refits))]
    jobs += [("exit", m, "y", k) for m in ("R", "G") for k in range(len(refits))]
    jobs.sort(key=lambda j: (j[1] != "G", -j[3]))                              # 大的先跑
    import pickle
    ckpt = paths.sub("cache") / CKPT_NAME                                     # 只有预测与统计；var/cache 已 gitignore
    res = pickle.loads(ckpt.read_bytes()) if G.get("resume") and ckpt.exists() else {}
    if res:
        say(f"（模型的样本外预测从检查点恢复：同一份登记规则的上一次运行，{len(res)} 个）")
    else:
        with _pool() as ex:
            for key, out in ex.map(_fit_predict, jobs):
                res[key] = out
                print(key, f"{time.time() - t0:.0f}s", flush=True)
        ckpt.write_bytes(pickle.dumps(res))
    return evaluate(D, names, masks, member, days, wk, nm, col_of, cols, ri, ci, ent, T, xr, y_x, dr, dcc, ind, p0, delist,
                    refits, sets, res, head, t0)


def _assemble(sets, res, task, model, n_rows_key="dates"):
    """把各次重训的测试预测拼回完整的样本外预测（没有预测的行 = 缺值）；同时给 daily 行的预测与每行对应的阈值。"""
    S = sets[task]
    pred = np.full(len(S[n_rows_key]), np.nan)
    daily = np.full(len(sets["daily"]["folds"][0]["test"]), np.nan)
    q33 = np.full(len(pred), np.nan)
    dq = {"q33": np.full(len(daily), np.nan), "q90": np.full(len(daily), np.nan)}
    for k in range(len(S["folds"])):
        o = res[(task, model, "y", k)]
        te = S["folds"][k]["test"]
        pred[te] = o["test_pred"]
        q33[te] = o["q"]["q33"]
        dm = sets["daily"]["folds"][k]["test"]
        daily[dm] = o["pred_daily"]
        dq["q33"][dm], dq["q90"][dm] = o["q"]["q33"], o["q"]["q90"]
    return pred, daily, dq


def evaluate(D, names, masks, member, days, wk, nm, col_of, cols, ri, ci, ent, T, xr, y_x, dr, dcc, ind, p0, delist,
             refits, sets, res, head, t0) -> int:
    from qbreak.factor_combo import auc
    dts = pd.DatetimeIndex(sets["entry"]["dates"])
    va = (dts >= pd.Timestamp(VAL[0])) & (dts < pd.Timestamp(VAL[1]))
    ho = dts >= pd.Timestamp(HOLD[0])
    say("\n## 一、入场模型：样本外预测力（每周秩相关 IC 与前 1/5 − 后 1/5）")
    say("| 模型 | H | 验证期 IC（95% 区间） | 留出期 IC（95% 区间） | 验证期 前−后 1/5 超额 | 留出期 前−后 1/5 | 选的超参数（各年） |")
    say("|---|---|---|---|---|---|---|")
    P, DP, summ = {}, {}, {}
    for H in HORIZONS:
        for m in ("R", "G"):
            pred, daily, dq = _assemble(sets, res, f"entry{H}", m)
            P[(m, H)], DP[(m, H)] = pred, (daily, dq)
            ret = ent[H]["ret"]
            row = {}
            for lab, msk in (("va", va), ("ho", ho)):
                ic = ml.ic_by_date(pred[msk], ret[msk], dts[msk])
                blk = ic.index.to_period("M" if H == 20 else "Q").astype(str)
                mu, lo, hi = ml.block_boot_mean(ic, blk, N_BOOT, SEED)
                ls = _long_short(pred[msk], ret[msk], dts[msk])
                row[lab] = {"ic": mu, "lo": lo, "hi": hi, "n": int(len(ic)), "ls": ls}
            hp = [res[(f"entry{H}", m, "y", k)]["hp"] for k in range(len(refits))]
            summ[(m, H)] = {**row, "hp": hp}
            hps = "、".join(str(h.get("alpha", h.get("trees"))) for h in hp)
            say(f"| {'岭回归 R' if m == 'R' else '提升树 G'} | {H} | {row['va']['ic']:+.4f}（{row['va']['lo']:+.4f}〜{row['va']['hi']:+.4f}） | "
                f"{row['ho']['ic']:+.4f}（{row['ho']['lo']:+.4f}〜{row['ho']['hi']:+.4f}） | {row['va']['ls'] * 100:+.2f}% | "
                f"{row['ho']['ls'] * 100:+.2f}% | {hps} |")
    best = max(summ, key=lambda k: summ[k]["va"]["ic"])
    bm, bh = best
    sig = summ[best]["va"]["lo"] > 0
    say(f"\n验证期平均 IC 最高：{'岭回归' if bm == 'R' else '提升树'} H{bh}（{summ[best]['va']['ic']:+.4f}，95% 区间"
        f"{'不含' if sig else '含'} 0）→ 交易候选 K1〜K3 用它。")
    # 分组置换重要性（验证期各年平均）
    imp = pd.DataFrame([res[(f"entry{bh}", bm, "y", k)]["imp"] for k, rf in enumerate(refits) if rf < pd.Timestamp(VAL[1])])
    say("分组置换重要性（打乱后验证期 IC 掉多少，越大越重要）：" + "、".join(f"{g} {v:+.4f}" for g, v in imp.mean().items()))
    # 单个特征自己的 IC
    say("\n## 二、单个因子自己的预测力（入场，H20 超额收益的每周 IC；只描述）")
    say("| 因子 | 验证期 IC | 留出期 IC | 两期同号 |")
    say("|---|---|---|---|")
    X_e = sets["entry"]["X"]
    single = {}
    labs = {**T_FEATS, **{k: k for k in S_FEATS}, **F_FEATS, **X_FEATS}
    from qbreak.signal_score import LABELS
    for j, c in enumerate(cols):
        if c.startswith("M_"):
            continue
        a1 = ml.ic_by_date(X_e[va, j], ent[20]["ret"][va], dts[va]).mean()
        a2 = ml.ic_by_date(X_e[ho, j], ent[20]["ret"][ho], dts[ho]).mean()
        single[c] = (float(a1), float(a2))
    for c, (a1, a2) in sorted(single.items(), key=lambda z: -abs(z[1][0])):
        lab = LABELS.get(S_FEATS.get(c, ""), labs.get(c, c))
        say(f"| {c} {lab} | {a1:+.4f} | {a2:+.4f} | {'✓' if np.sign(a1) == np.sign(a2) else '✗'} |")
    # 出场模型
    say("\n## 三、出场模型：持仓中「再拿 20 个交易日会跌 ≥ 5%」的样本外 AUC")
    xd = pd.DatetimeIndex(sets["exit"]["dates"])
    xva = (xd >= pd.Timestamp(VAL[0])) & (xd < pd.Timestamp(VAL[1]))
    xho = xd >= pd.Timestamp(HOLD[0])
    ex_summ = {}
    for m in ("R", "G"):
        pred, daily, dq = _assemble(sets, res, "exit", m)
        P[("X", m)], DP[("X", m)] = pred, (daily, dq)
        a1, a2 = auc(pred[xva], y_x[xva])[0], auc(pred[xho], y_x[xho])[0]
        ex_summ[m] = {"va": a1, "ho": a2, "base_va": float(np.nanmean(y_x[xva])), "base_ho": float(np.nanmean(y_x[xho]))}
        say(f"- {'逻辑回归 R' if m == 'R' else '提升树 G'}：验证期 AUC {a1:.3f}、留出期 {a2:.3f}（跌 ≥ 5% 的比例 验证期 "
            f"{ex_summ[m]['base_va'] * 100:.1f}% / 留出期 {ex_summ[m]['base_ho'] * 100:.1f}%）")
    xm = max(ex_summ, key=lambda m: ex_summ[m]["va"])
    say(f"验证期 AUC 高的：{'逻辑回归' if xm == 'R' else '提升树'} → K4 用它。")
    # 模型 IC 按宏观状态
    say("\n## 四、入场模型的 IC 按宏观状态（验证期 / 留出期；只描述）")
    from qbreak import factors
    from qbreak.bullbear import BEAR, Detector, load_config
    from bullbear_study import SYM, load
    ic_n = load(*SYM["JP"])["Close"]
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bull = pd.Series(np.asarray(det.states(ic_n)) != BEAR, index=ic_n.index)
    jd = ic_n.index[(ic_n.index >= pd.Timestamp(WINDOW[0]) - pd.Timedelta(days=200)) & (ic_n.index <= pd.Timestamp(WINDOW[1]))]
    mr = D["macro_raw"]
    ST = PRS.jp_states(jd, mr["jgb"], factors.fred("DGS10"), mr["fx"], bull)
    icw = ml.ic_by_date(P[best], ent[bh]["ret"], dts)
    stw = PRS.states_at(ST, icw.index)
    state_tab = {}
    f4 = lambda v: "—" if not np.isfinite(v) else f"{v:+.4f}"                        # noqa: E731
    for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
        say(f"- {PRS.DIMS[dim]}：" + "；".join(
            f"{b} 验证 {f4(icw[(stw[dim] == b).to_numpy() & (icw.index < pd.Timestamp(VAL[1]))].mean())}"
            f" / 留出 {f4(icw[(stw[dim] == b).to_numpy() & (icw.index >= pd.Timestamp(HOLD[0]))].mean())}"
            f"（{int(((stw[dim] == b).to_numpy()).sum())} 周）"
            for b in sorted(stw[dim].dropna().unique())))
        state_tab[dim] = {str(b): [float(icw[(stw[dim] == b).to_numpy() & (icw.index < pd.Timestamp(VAL[1]))].mean()),
                                   float(icw[(stw[dim] == b).to_numpy() & (icw.index >= pd.Timestamp(HOLD[0]))].mean())]
                          for b in stw[dim].dropna().unique()}
    return trade(D, names, masks, member, days, wk, nm, col_of, dr, dcc, ind, p0, delist, P, DP, best, xm, summ, ex_summ,
                 single, imp, state_tab, refits, head, t0)


def _long_short(pred, ret, dates) -> float:
    """每个日期：预测前 1/5 的平均超额收益 − 后 1/5；再对日期平均。"""
    df = pd.DataFrame({"d": dates, "p": pred, "r": ret}).dropna()
    if df.empty:
        return float("nan")
    q = df.groupby("d")["p"].rank(pct=True)
    top = df[q > 0.8].groupby("d")["r"].mean()
    bot = df[q <= 0.2].groupby("d")["r"].mean()
    return float((top - bot).mean())


def trade(D, names, masks, member, days, wk, nm, col_of, dr, dcc, ind, p0, delist, P, DP, best, xm, summ, ex_summ,
          single, imp, state_tab, refits, head, t0) -> int:
    bm, bh = best
    closes_all = pd.DataFrame({t: D["data"][t]["Close"] for t in names["U1"]})
    PRS.PitEngine.DELIST = delist
    G["ratio"] = D["ratio"]
    run = make_runner(closes_all)
    u1 = names["U1"]
    base_ind = {t: PD.mask_entries(ind[t], masks["U1"][t]) for t in u1}
    daily_e, dq_e = DP[best]
    daily_x, dq_x = DP[("X", xm)]
    dd = days[dr]
    tick = [nm[c] for c in dcc]
    score = pd.Series(daily_e, index=pd.MultiIndex.from_arrays([tick, dd]))
    q33 = pd.Series(dq_e["q33"], index=score.index)
    prio = {k: float(v) for k, v in score.dropna().items()}
    say("\n## 五、交易候选（S0C2 = var/sim.json 同一套设定；U1 时点 TOPIX 500、现行参数；「现行」= 同一设定不加模型）")
    B = run(base_ind, p0)
    R = {}
    R["K1"] = run(base_ind, p0, prio=prio)
    k2 = {}
    for t in u1:
        df = base_ind[t]
        e = df["entry"].to_numpy(bool).copy()
        if e.any():
            sc = score.reindex(pd.MultiIndex.from_arrays([[t] * len(df), df.index])).to_numpy(float)
            th = q33.reindex(pd.MultiIndex.from_arrays([[t] * len(df), df.index])).to_numpy(float)
            e &= ~(np.isfinite(sc) & np.isfinite(th) & (sc < th))
        k2[t] = df.assign(entry=e)
    R["K2"] = run(k2, p0)
    wide = score.unstack(0).reindex(index=wk).reindex(columns=u1)
    wide = wide.where(member["U1"].reindex(index=wk, columns=u1).fillna(False))
    top = top_k_entries(wide, K3_TOP)
    p_rot = replace(p0, max_hold_days=bh, exit_on_macd_dead_cross=False, exit_on_climax=False, take_profit_pct=0.0,
                    trailing_stop_pct=0.0).validate()
    k3 = {}
    for t in u1:
        df = base_ind[t]
        e = top[t].reindex(df.index).fillna(False).to_numpy(bool) if t in top.columns else np.zeros(len(df), bool)
        k3[t] = df.assign(entry=e)
    R["K3"] = run(k3, p_rot, prio=prio)
    xs = pd.Series(daily_x, index=score.index)
    q90 = pd.Series(dq_x["q90"], index=score.index)
    flag = (xs >= q90) & xs.notna() & q90.notna()
    exit_flags = {}
    for (t, d), f in flag.items():
        if f:
            exit_flags.setdefault(t, set()).add(d)
    R["K4"] = run(base_ind, p0, exit_flags=exit_flags)
    passed_v = {k: v for k, v in R.items() if not v_fails(v, B)}
    k12 = [k for k in ("K1", "K2") if k in passed_v]
    if k12 and "K4" in passed_v:
        kbest = max(k12, key=lambda k: _c(R[k]["va"]["calmar"]))
        R["K5"] = run(k2 if kbest == "K2" else base_ind, p0, prio=prio if kbest == "K1" else None, exit_flags=exit_flags)
        R["K5"]["desc_from"] = kbest
    desc = {"K1": f"突破信号按入场模型分数排序（{'岭回归' if bm == 'R' else '提升树'} H{bh}）",
            "K2": "入场分数 < 训练样本 1/3 分位的突破信号不买", "K3": f"模型选股：每周分数最高的 5 只，持有 {bh} 个交易日（+7% 止损）",
            "K4": f"出场模型（{'逻辑回归' if xm == 'R' else '提升树'}）概率 ≥ 训练样本 90 分位 → 下一交易日开盘卖",
            "K5": f"{R.get('K5', {}).get('desc_from', '')} + K4"}
    fa = lambda v, f="{:.2f}": "—" if v is None else f.format(v)                     # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"  # noqa: E731
    say("| 方案 | 全窗口 | 验证期 2019-01〜2023-09 | 留出期 | 留出前半 | 留出后半 | 个股笔数 / 胜率 | V | H |")
    say("|---|---|---|---|---|---|---|---|---|")
    say(f"| 现行 | {cell(B['all'])} | {cell(B['va'])} | {cell(B['ho'])} | {cell(B['h1'])} | {cell(B['h2'])} | {B['trades']} / {fa(B['win'], '{:.1f}')}% | — | — |")
    final = {}
    for k, r in R.items():
        vf = v_fails(r, B)
        hf = h_fails(r, B) if not vf else None
        final[k] = {"desc": desc[k], "v_fails": vf, "h_fails": hf}
        show = not vf
        say(f"| {k} {desc[k]} | {cell(r['all'])} | {cell(r['va'])} | {cell(r['ho']) if show else '—（没过 V，不看）'} | "
            f"{cell(r['h1']) if show else '—'} | {cell(r['h2']) if show else '—'} | {r['trades']} / {fa(r['win'], '{:.1f}')}% | "
            f"{'✓' if not vf else '✗'} | {'—' if hf is None else ('✓' if not hf else '✗')} |")
    for k, v in final.items():
        why = v["v_fails"] or v["h_fails"] or []
        if why:
            say(f"- {k}：" + "；".join(why))
    passed = {k: R[k] for k, v in final.items() if v["h_fails"] == []}
    prop = choose(passed)
    if prop:
        say(f"\n**结论：{prop} {desc[prop]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；改之前记进 sim_changes.md）。**"
            + (f"另外也通过的：{'、'.join(k for k in passed if k != prop)}。" if len(passed) > 1 else ""))
    else:
        say("\n**结论：没有候选通过（V 或 H）→ 维持现行，模拟盘不改。**")
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "ml_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    js = {"code": head, "window": WINDOW, "val": VAL, "hold": HOLD, "refits": [str(r.date()) for r in refits],
          "entry": {f"{m}{H}": summ[(m, H)] for (m, H) in summ}, "entry_best": f"{bm}{bh}", "exit": ex_summ, "exit_best": xm,
          "single_ic": single, "group_importance": imp.mean().to_dict(), "ic_by_state": state_tab,
          "trade": {"base": {k: v for k, v in B.items()}, **{k: {kk: vv for kk, vv in r.items() if kk in ("va", "trades", "win") or not final[k]["v_fails"]}
                                                           for k, r in R.items()}},
          "final": final, "passed": sorted(passed), "proposal": prop}
    Path(f"{fp}.json").write_text(json.dumps(js, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
