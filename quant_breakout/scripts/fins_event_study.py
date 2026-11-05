"""fins_event_study.py — 「決算 / 会社予想修正的开示本身当买点」研究（登记版：规则、阈值、对照、窗口、判定全部写在这里，提交后不改）。

来由：用户 2026-09-27「上述你更建议怎么做比较好 → 取得现在所有个股的决算、业绩修正」→「继续 设计结果出来后登记并运行；
  取消小盘股受一手金额（¥25 万）和流动性限制」。以前三次把决算信息当突破的过滤 / 月度排序（jq_study G1 AUC 0.499、G2 0.528、leap_r8
  时代依赖、leap2_s2 价量 PEAD 代理为零）都没过；这次第一次把「开示这件事」当买点（PEAD = Post-Earnings-Announcement Drift，公告后漂移；
  日本的对应物是会社予想修正后的ドリフト）。设计经三份独立提案 + 两位评审 + 综合 + 两份对抗审计（2026-09-27）；审计里不依赖结果的修正
  在运行前并入（d8f6891 之后的「登记修订」提交），以最后一次运行前的提交为准。

一、数据（全部只在 var/cache/jquants/，不入库）
  決算短信サマリー（J-Quants Standard fins/summary，全市场 2016-09〜）→ scripts/fins_event_data.events_full：
  只留季度 / 年度決算短信（Consolidated / NonConsolidated × JP / IFRS / US）与 EarnForecastRevision；不要 REIT、股息修正、外国、其他期间；
  同一公司连结与单体都有 → 只用连结。日线 = scripts/allstock_data 面板（复权 OHLCV、R 真实价比例、VA 成交额、时点上市掩码 listed）。
  事件池 E0（每条开示一行，全部条件事先写定）：
    ① first：同键第一次开示（決算短信 (文件类型, 决算期末, 期间)；予想修正 (决算期末, 开示日)）；之后同键 = 订正，不作事件
       （上一次予想链由每一行更新，避免与变更前的予想比较产生虚假大幅 rev）
    ② fy12：当期决算期 = 12 个月；③ 不是遡及修正 / 会计估计变更 / 连结子公司异动 / 连结范围变更（RetroRst / ChgAcEst / MatChgSub / SigChgInC）
    ④ t0（开示日之后第一个交易日）存在，且 t0 那天在时点股票池（严格早于 t0 的月末上市一览里是一般市场的内国普通股）
    ⑤ 不设一手金额、成交额、市值、价格下限（用户 2026-09-27）；一手 ≤ ¥25 万 / ≤ ¥34 万、20 日成交额 ≥ ¥500 万 / ≥ ¥5,000 万、时点 TOPIX 500
       只作分段另报（分段表只描述，任何子集都不构成结论、不能作为下一次登记的候选来源）
    ⑥ split_near = 0（[信号日−1, t0] 内真实价比例跳变 > 1% 的拆股 / 并股当周不做）；⑦ t0 之前那只票 ≥ 120 个交易日有行情（MACD 预热）
  利润档按这一行有值的列（营业利润 → 经常利润 → 净利润）；rev = 与同一决算期上一次予想相比的修正 %，要求新旧予想都 > 0（pos）且 rev ≤ +300%
  （予想接近 0 的极端值）；新决算期第一次予想 rev 缺值 = 不是上修事件；yoy = 同一开示的累计实绩对上年同期 %（上年 > 0 且也是 12 个月）。
  同一只票同一个信号日多条开示 → 取 rev 最大的那条代表当天。

二、买点与成交（与引擎 / 执行器同一约定）
  信号日 = 开示日 D 当天或之前最后一个交易日（sig_day）；成交 = 信号日的下一个交易日（= t0）开盘 × (1 + 0.1%)；
  开盘 > 信号日收盘 × 1.03 → 放弃（引擎 max_entry_gap_pct = 3.0，执行器的寄付指値上限；登记前计数：上修事件约 40% 因此被放弃，
  留下的偏「反应温和」的一半 —— 本研究检验的就是执行器真能买到的那部分；放宽到 8% 只在探索窗口描述、不判定）。
  C3 用反应日 r（盘中开示且当天是交易日 → 当天；盘后 / 非交易日 → t0；收盘时刻 2024-11-05 起 15:30、之前 15:00）当信号日 → r+1 开盘买。
  同一只票：一次一仓（引擎）；上一个被选中的事件之后 20 个交易日内的事件不再作事件（同一季度先短信后修正只算一次）。
  数据可得性：只有 2026-09 的 live 文件能证明「当天开示次日 00:30 JST 前入文件」（bulk/_last_modified.json）；历史窗口的可得时刻与数值
  （订正覆盖）是假设，写进局限；「取数晚于 07:05 → 顺延」只对前向记录生效、历史回测一律 t0。ストップ高判断用的是复权价（引擎现状、与基准同）。

三、卖法
  现行 var/best_params*.json：止损 7%（收盘触发、次日开盘卖；跳空越过按开盘）、止盈 25%、跟踪 12%、最长 60 个交易日、MACD 死叉、出货日。
  事件专用卖法（C4、P1 与「20 日卖法对照」用，事先写定）：max_hold_days = 20、take_profit_pct = 0、trailing_stop_pct = 0、不用 MACD 死叉、不用出货日
  → 固定第 20 个交易日后开盘卖，期间只有 7% 止损。成本：立花 ¥25 万一笔来回 ¥374 = 0.15% + 滑点双边 0.1%；退市中途按最后收盘结算；
  样本末尾：确认窗口的信号日截止 = 数据末尾往前 61 个交易日（未平仓的交易不算 → 末尾按出场类型删失，所以候选、基准、对照一律同一截止）。

四、候选（≤ 5；阈值全部事先写死，不做网格、不在探索期挑选：rev +10% / yoy +10% / 反应 +2% ∧ 量比 2.0（leap2_s2 登记过的原值）/ 事件卖法 20 日 / g_next +10%）
  C1 上修：E0 ∧ pos ∧ +10% ≤ rev ≤ +300% → t0 开盘买、现行卖法
  C2 上修 ∧ 实绩印证：C1 ∧ 同一決算短信行 累计实绩 yoy ≥ +10% ∧ 净利润予想 rev_np ≥ 0（修正文档没有实绩 → 不满足）
  C3 上修 ∧ 反应日确认：C1 ∧ react（r 收盘对前一交易日，一天口径）≥ +2% ∧ vr_r（r 日量 ÷ 前 20 日均量）≥ 2.0 ∧ r 日收阳 → r+1 开盘买、现行卖法
  C4 C1 的事件 + 事件专用卖法；判定免 S1（卖法维度，事先声明只看每笔），基准用同一卖法的 B20
  C5 期初指引：FY 決算短信 ∧ g_next（下期予想 ÷ 当期实绩 − 1，两者 > 0）≥ +10% ∧ beat（当期实绩对最后一次予想）≥ 0 ∧ 当期 FY yoy ≥ 0 → t0 开盘买、现行卖法
  读法（事先写定）：C2 / C3 / C4 是 C1 的子集或同事件 —— 只有 C1 也通过时它们的通过才读作「事件效应的子集」，C1 不过而子集过 = 「子集挑选」只记录；
  C3 对照 C1'（C1 同一事件、无条件在 r+1 开盘买）：C3 > C1' 才算「市场确认」有价值；C5 与 C1 是两类开示。

五、基准与对照（单独交易 = 每只票一次一仓的逐笔，同一流水线、同一股票池、同一卖法与退市口径）
  基准 B：全市场 W2 突破的信号日（scripts/allstock_study.train_all 的表 var/cache/jquants/allstock_train.pkl 里 周线量比 w5v ≥ 1.0 或缺值）
    在本脚本里按同一逐笔机制重算（现行卖法 = B；事件卖法 = B20，C4 用）；不加一手 / 流动性过滤。
    每个候选的 B 只取该候选「第一笔到最后一笔信号日」范围内的突破（C2 / C5 因 yoy 从 2018 年才有；不让基准含候选没有的年份）。
  P0 同日换票（S5 用）：每个事件换成同一天、时点股票池里、≥ 120 日行情、且信号日之前 10 个交易日内（含当天）没有任何开示的随机另一只票，
    同样买卖（只用当时可知的信息）；30 个种子 → X 用 95 分位；C 用参数化上限 均值 + t(0.99, 29) × 标准差（30 个值的 99 分位就是最大值，不用）。
  PL-B 匹配放量日（只对 C3）：同一只票、信号日前后 60 个交易日内、之前 10 个交易日内没有开示、且同样「收盘 ≥ +2% ∧ 量比 ≥ 2 ∧ 收阳」的随机一天；30 个种子、同上。
  P1 事前安慰剂（必要条件）：同一只票在信号日前 [45, 30] 个交易日里随机一天买入、事件专用卖法（持仓最晚在信号日前 10 日结束）、
    且 [买入日−5, 买入日+25] 内该公司没有任何开示（有界持仓、不跨上一次开示；这里用到了「之后没有开示」这个事后信息，目的是造纯净对照）；
    30 个种子 → 候选在事件专用卖法下的每笔（C4 本身；其余候选另算一份 20 日卖法）− P1 各种子每笔的均值 ≥ +1.0 pp，
    且候选（20 日卖法）每笔的周聚类自助法 95% 区间下限 > P1 均值；不满足 → 判为个股 / 时代动量。
  P3 信息对照（必要条件；与候选同买点、同卖法）：按「公司 × 开示日」定义的予想重申 = 該公司当天所有行 |rev| = 0 且 净利润予想没改 且 |yoy| < 10% 的決算短信行；
    P3(C1 / C2) 同 t0 买、现行卖法；P3(C3) = 重申 ∧ 同样反应条件 → r+1 买；P3(C4) = 重申、事件卖法；P3(C5) = FY 行 |g_next| < 5% ∧ |beat| < 5% ∧ |yoy| < 10%
    → 候选胜率 ≥ P3 + 4 pp（C4 免）且每笔 ≥ P3 + 0.5 pp，否则 = 决算后的时点效应、不是上修的信息。
  方向对照 P2（只描述）：pos ∧ rev ≤ −10% 同样做多。区间：按事件周（W-FRI）聚类的自助法 2,000 次、种子 20260927。

六、窗口与流程
  探索 X = 信号日 2017-01-04〜2021-12-30（--stage explore：脚本只保留 X 内的事件与基准；看方向、写描述表；不改任何阈值）
  确认 C = 信号日 2022-01-04〜（数据末尾 − 61 个交易日）（--stage confirm：只跑 CONFIRM_IDS 里的候选，一次；X 的数字一并重报）
  探索门（方案乙 + 最低效应，事先写定）：每笔 ≥ 基准 + 0.5 pp 且 胜率 ≥ 基准 且 每笔 > P0 95 分位 且 20 日卖法每笔 > P1 均值 且 每笔 > P3 每笔 → 进入确认；
  进入的候选 id 写进 CONFIRM_IDS 再提交；X 一个都不过 → 不跑 C。
  登记前已经看过的 C 窗口统计（都是进场前的分布 / 计数，没有任何买入后收益）：事件按年计数（rev ≥ 10 且 pos：2022〜2026 各 1,463 / 1,388 / 1,279 / 1,235 / 989）、
  t0 跳空 > 3% 占 40%、反应日 ≥ +3% ∧ 量比 ≥ 2 占 42%、一手 ≤ ¥25 万 70%、盘后开示 81%；2022〜2026 对上修类信号还被 leap_r8 / jq_study 看过 →
  本研究任何结果的结论上限 = 前向记录（七）。

七、判定（确认窗口；leap2_common 的 S1〜S5 从「组合层、Z / E / J」适配到「全市场单独交易层、X / C」—— 基本面只有 2016-09 起、
  组合层现行 J2 只有 47 笔、+8 pp 在 47 笔上标准误约 8 pp 没有检出力；这一适配记进 sim_changes.md。S1 / S2 是点估计门槛：真实效应恰为门槛时通过率约 50%）
  S1 胜率 ≥ 基准 + 8 pp（C4 免）；S2 每笔 ≥ 基准 + 1.0 pp 且 (候选 − 基准) 的周聚类自助法 95% 区间下限 > 0；S3 笔数 ≥ 300（绝对下限；相对 30% 只在组合层）；
  S5 胜率（C4 免）与每笔都 > P0 的参数化上限（C3 还要 > PL-B）；P1、P3 必要条件（五）；
  S4 组合不变差：S0C2（var/sim.json 同一套：核心 1655 牛熊择时、宏观倍数、4 × 25%、单只 ≤ 34%、真实一手）里 P-mix = 现行突破（W2）+ 该候选的事件
    共用 4 个名额（同日先突破、再事件按 rev / g_next 降序）；股票池 = 时点 TOPIX 500（leap2_common 的 U1；候选事件只算池内的票）；
    C 窗口（J2）Calmar ≥ 现行 − 0.02 且回撤不深 2 pp 以上 且个股笔数 ≥ 现行的 30%（C4 用 P-event = 事件替换突破、事件卖法对全部个股仓位）；
    另报 P-event、今天的日経225 池（U0）。全市场事件并进组合引擎是另一件工程，本次不做（记进局限）。
  全过 = 「事件买点成立（J 单窗口）」→ 只能进前向记录、由用户决定是否改模拟盘 / 执行器（2022〜2026 对上修类信号已被 leap_r8 看过，
    且达不到 leap2_common 正式要求的 Z / E / J 三窗口）；S1 不过但 胜率 ≥ 基准 + 4 pp ∧ 每笔 ≥ 基准 + 0.5 pp ∧ S5 ∧ P1 ∧ P3 = 「选股改进」只记录；
  其余 = 不成立。结果出来不改任何规则。

八、局限（事先声明）：缓存是 2026-08 批量重下的「今天看到的」数值（同键 ≥ 2 个开示日的键 4.7%，first 规则只留第一行；TDnet 原文核对云端做不了）；
  同日集中（决算季单日最多 1,266 家）让逐笔独立性不成立、设计效应可能远大于 2，正式区间只用事件周聚类自助法；0.1% 滑点对小型股偏乐观（分段另报）；
  P0 在决算季只能抽到非 3 月决算的公司（行业 / 规模构成与事件票不同）；ストップ高判断用复权价（与基准同一偏差）；
  执行器目前只下日経225 —— 就算成立，扩池与「07:05 取 fins → 寄付」的事件层是另一件要用户确认的事。
  输出：var/out/fins_event_study.md / .json（只有统计；含 git 版本、所用批量文件 sha256）；逐笔与事件表只在 var/cache/jquants/out/。
用法：python scripts/fins_event_study.py --stage explore|confirm [--seeds 30] [--procs 4] [--no-portfolio] [--rebuild]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402

WIN_X = ("2017-01-04", "2021-12-30")
WIN_C = ("2022-01-04", "2026-09-25")                # 确认窗口的末端在运行时截到 数据末尾 − END_CUT 个交易日
TRADE_START = "2017-01-04"
SEEDS, SEED0, Q_X, Q_C = 30, 20260927, 95.0, 99.0  # C 用参数化上限 均值 + t(Q_C, n−1)·sd
BOOT_N = 2000
REV_MIN, GNEXT_MIN, REV_CAP, YOY_MIN, REACT_MIN, VR_MIN, REENTRY_GAP, HIST_MIN = 10.0, 10.0, 300.0, 10.0, 2.0, 2.0, 20, 120
NEUTRAL_G, NEUTRAL_B, NEUTRAL_YOY, DOWN_MIN = 5.0, 5.0, 10.0, 10.0
PRE_LO, PRE_HI, PRE_BACK, PRE_FWD, QUIET, MATCH_WIN, END_CUT = 45, 30, 5, 25, 10, 60, 61
WIN_UP_PP, MEAN_UP_PP, MIN_N_ABS, MIN_N_FRAC_PORT, CALMAR_TOL, DD_TOL_PP = 8.0, 1.0, 300, 0.30, 0.02, 2.0
IMPROVE_WIN_PP, IMPROVE_MEAN_PP, P3_WIN_PP, P3_MEAN_PP, P1_MEAN_PP, GATE_MEAN_PP = 4.0, 0.5, 4.0, 0.5, 1.0, 0.5
GAP_RELAX = 8.0
EVENT_EXIT = dict(max_hold_days=20, take_profit_pct=0.0, trailing_stop_pct=0.0, exit_on_macd_dead_cross=False, exit_on_climax=False)
CANDS = {"C1": "上修 +10% ≤ rev ≤ +300% → t0 开盘买、现行卖法", "C2": "C1 ∧ 同一決算短信 yoy ≥ +10% ∧ rev_np ≥ 0",
         "C3": "C1 ∧ 反应日 r：对前一日 ≥ +2% ∧ 量比 ≥ 2 ∧ 收阳 → r+1 开盘买", "C4": "C1 的事件 + 事件专用卖法（20 日固定、只有 7% 止损）",
         "C5": "FY 決算短信：g_next ≥ +10% ∧ beat ≥ 0 ∧ FY yoy ≥ 0 → t0 开盘买"}
NO_S1 = ("C4",)
CONFIRM_IDS: tuple[str, ...] = ()                   # 探索门通过的候选 id，探索后填、再提交；确认阶段只跑这些
OUT_MD, OUT_JSON = "fins_event_study.md", "fins_event_study.json"
_FR: dict[str, pd.DataFrame] = {}                   # 每只票的指标表（fork 后子进程共享）
_DELIST: set[str] = set()


# ───────────────────────── 数据 ─────────────────────────
def cache_out() -> Path:
    from qbreak import jquants as JQ
    d = JQ.cache_dir() / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_events(A: dict, rebuild: bool = False) -> pd.DataFrame:
    import fins_event_data as FE
    fp = cache_out() / "fins_events_full.pkl"
    if fp.exists() and not rebuild:
        return pd.read_pickle(fp)
    F = FE.load_fins(extra=True)
    D = FE.describe_events(A, FE.events_full(F, pd.DatetimeIndex(A["days"])))
    D.to_pickle(fp)
    return D


def hist_matrix(A: dict) -> np.ndarray:
    """hist[d, j]：到 d 为止（含）那只票有收盘的交易日数。"""
    return np.cumsum(np.isfinite(A["C"]), axis=0)


def hist_days(A: dict, E: pd.DataFrame, hist: np.ndarray | None = None) -> np.ndarray:
    """每条事件：t0 之前那只票有行情的交易日数。"""
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    pos = pd.Series(np.arange(len(days)), index=days)
    cum = hist if hist is not None else hist_matrix(A)
    out = np.zeros(len(E))
    for k, (t, d) in enumerate(zip(E["ticker"], E["t0"])):
        j, i = col.get(t), pos.get(d)
        if j is not None and i is not None and int(i) > 0:
            out[k] = cum[int(i) - 1, j]
    return out


def pool(D: pd.DataFrame, A: dict | None = None) -> pd.DataFrame:
    """事件池 E0（一 ①〜⑦；A 缺省时不查行情天数）。"""
    ok = (D["first"] & D["fy12"] & ~D["retro"] & ~D["chg_acc"] & ~D["chg_sub"] & ~D["chg_scope"] & D["t0"].notna() & (D["listed_t0"] == 1))
    if "split_near" in D.columns:
        ok &= D["split_near"].fillna(0) == 0
    E = D[ok.to_numpy(bool)].reset_index(drop=True)
    if A is not None and len(E):
        E = E[hist_days(A, E) >= HIST_MIN].reset_index(drop=True)
    return E


def in_window(d: pd.Series, win: tuple[str, str]) -> np.ndarray:
    d = pd.to_datetime(d)
    return ((d >= pd.Timestamp(win[0])) & (d <= pd.Timestamp(win[1]))).to_numpy()


def select(E: pd.DataFrame, cid: str) -> pd.DataFrame:
    """候选 → 事件子集，加 buy_sig（当信号日的那天：C3 = r，其余 = sig_day）与 prio（组合里的优先级分数：rev / g_next 封顶 100）。
    同一只票同一个 buy_sig 多条 → 取 rev（C5 取 g_next）最大的那条。"""
    up = E["pos"] & (E["rev"] <= REV_CAP) & (E["rev"] >= REV_MIN)
    is_fs = E["doc"].str.contains("FinancialStatements")
    if cid in ("C1", "C4"):
        m = up
    elif cid == "C2":
        m = up & is_fs & (E["yoy"] >= YOY_MIN) & (E["rev_np"] >= 0)
    elif cid == "C3":
        m = up & (E["react"] >= REACT_MIN) & (E["vr_r"] >= VR_MIN) & (E["up_r"] == 1) & E["r"].notna()
    elif cid == "C5":
        m = (E["per"] == "FY") & E["doc"].str.startswith("FY") & (E["g_next"] >= GNEXT_MIN) & (E["beat"] >= 0) & (E["yoy"] >= 0)
    else:
        raise ValueError(cid)
    S = E[m.fillna(False).to_numpy(bool)].copy()
    S["buy_sig"] = S["r"] if cid == "C3" else S["sig_day"]
    S["prio"] = np.minimum(S["g_next"] if cid == "C5" else S["rev"], 100.0)
    S = S.sort_values(["buy_sig", "ticker", "prio"], ascending=[True, True, False]).drop_duplicates(subset=["ticker", "buy_sig"])
    return S.reset_index(drop=True)


def dedupe(S: pd.DataFrame, days: pd.DatetimeIndex, gap: int = REENTRY_GAP) -> pd.DataFrame:
    """同一只票：上一个被选中的事件之后 gap 个交易日内的事件不算。"""
    pos = pd.Series(np.arange(len(days)), index=days)
    keep, last = [], {}
    for r in S.sort_values(["ticker", "buy_sig"]).itertuples():
        k = int(pos.get(r.buy_sig, -1))
        if k < 0:
            keep.append(False)
            continue
        ok = (r.ticker not in last) or (k - last[r.ticker] > gap)
        keep.append(ok)
        if ok:
            last[r.ticker] = k
    out = S.sort_values(["ticker", "buy_sig"])[keep]
    return out.sort_values(["buy_sig", "ticker"]).reset_index(drop=True)


# ───────────────────────── 逐笔 ─────────────────────────
def build_frames(A: dict, p, tickers=None) -> dict[str, pd.DataFrame]:
    from qbreak.strategy import compute_indicators
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    last = pd.Timestamp(days[-1]) - pd.Timedelta(days=10)
    want = set(tickers) if tickers is not None else set(names)
    for j, t in enumerate(names):
        if t not in want or t in _FR:
            continue
        ok = np.isfinite(A["C"][:, j]) & np.isfinite(A["O"][:, j])
        if ok.sum() < 80:
            continue
        df = pd.DataFrame({"Open": A["O"][ok, j], "High": A["H"][ok, j], "Low": A["L"][ok, j], "Close": A["C"][ok, j],
                           "Volume": A["V"][ok, j]}, index=days[ok]).astype(float)
        _FR[t] = compute_indicators(df, p)
        if df.index[-1] < last:
            _DELIST.add(t)
    return _FR


def _bt(gap: float | None = None):
    from qbreak.config import BacktestConfig
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    if gap is not None:
        bt.exec_cfg.max_entry_gap_pct = gap
    return bt


def _one(args):
    t, sig_days, p, gap = args
    from qbreak.engine import run_backtest
    df = _FR[t]
    df = df.assign(entry=df.index.isin(pd.DatetimeIndex(sig_days)))
    if not df["entry"].any():
        return None
    try:
        r = run_backtest({t: df}, p, _bt(gap), start=TRADE_START)
    except ValueError:
        return None
    tr = r.trades
    if not len(tr):
        return None
    tr = tr[(tr["reason"] != "end") | (t in _DELIST)].copy()
    if not len(tr):
        return None
    tr["ticker"] = t
    ent = pd.to_datetime(tr["entry_date"])
    tr["sig_date"] = [df.index[max(0, df.index.searchsorted(e) - 1)] for e in ent]
    return tr


def run_trades(entries: dict[str, list], p, procs: int = 1, gap: float | None = None) -> pd.DataFrame:
    """{票: [信号日]} → 逐笔（一次一仓、现行 / 指定卖法、扣 ¥25 万一笔来回成本、退市按最后收盘）；gap 只在描述「放宽跳空」时用。"""
    cols = ["ticker", "sig_date", "entry_date", "exit_date", "net", "ret_pct", "hold_days", "reason"]
    jobs = [(t, ds, p, gap) for t, ds in sorted(entries.items()) if t in _FR and len(ds)]
    if not jobs:
        return pd.DataFrame(columns=cols)
    if procs > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(procs) as pl:
            rows = pl.map(_one, jobs, chunksize=8)
    else:
        rows = [_one(j) for j in jobs]
    rows = [r for r in rows if r is not None]
    if not rows:
        return pd.DataFrame(columns=cols)
    T = pd.concat(rows, ignore_index=True)
    bt = _bt()
    rt = bt.exec_cfg.fee(250000) * 2 / 250000 * 100
    T["net"] = T["ret_pct"] - rt
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    T["entry_date"] = pd.to_datetime(T["entry_date"])
    return T


def entries_of(S: pd.DataFrame) -> dict[str, list]:
    return {t: sorted(set(g["buy_sig"])) for t, g in S.groupby("ticker")}


def attach(T: pd.DataFrame, S: pd.DataFrame) -> pd.DataFrame:
    """逐笔 + 事件字段（按 票 × 信号日；同一天多条取第一条）。"""
    if not len(T):
        return T
    key = S.drop_duplicates(subset=["ticker", "buy_sig"]).set_index(["ticker", "buy_sig"])
    keep = [c for c in ("date", "doc", "per", "rev", "yoy", "g_next", "after_close", "lot_yen", "va20", "mc", "gap_t0", "react", "vr_r", "prio")
            if c in key.columns]
    J = key[keep].reindex(pd.MultiIndex.from_arrays([T["ticker"], T["sig_date"]]))
    T = T.copy()
    for c in keep:
        T[f"ev_{c}"] = J[c].to_numpy()
    return T


# ───────────────────────── 对照 ─────────────────────────
def quiet_matrix(D_all: pd.DataFrame, days: pd.DatetimeIndex, names: list[str], back: int = QUIET, fwd: int = 0) -> np.ndarray:
    """quiet[d, j]：那只票在 [d − back, d + fwd] 个交易日内没有任何开示（fwd = 0 → 只用过去信息）。"""
    col = {t: j for j, t in enumerate(names)}
    pos = pd.Series(np.arange(len(days)), index=days)
    busy = np.zeros((len(days), len(names)), bool)
    for t, d in zip(D_all["ticker"], D_all["sig_day"]):
        j, k = col.get(t), pos.get(d)
        if j is None or k is None:
            continue
        busy[max(0, int(k) - fwd):int(k) + back + 1, j] = True                 # 开示在 k → [k − fwd, k + back] 这些天都不安静
    return ~busy


def placebo_sameday(S: pd.DataFrame, A: dict, quiet: np.ndarray, seed: int, hist: np.ndarray | None = None) -> dict[str, list]:
    """P0：每个事件换成同一天、时点股票池里、≥ 120 日行情、之前 10 个交易日内没有开示的随机另一只票。"""
    rng = np.random.default_rng(seed)
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    pos = pd.Series(np.arange(len(days)), index=days)
    fin = np.isfinite(A["C"])
    out: dict[str, list] = {}
    cache: dict[int, np.ndarray] = {}
    for d in S["buy_sig"]:
        k = pos.get(d)
        if k is None:
            continue
        k = int(k)
        if k not in cache:
            ok = A["listed"][k] & fin[k] & quiet[k]
            if hist is not None and k > 0:
                ok &= hist[k - 1] >= HIST_MIN
            cache[k] = np.where(ok)[0]
        cand = cache[k]
        if not len(cand):
            continue
        j = int(rng.choice(cand))
        out.setdefault(names[j], []).append(d)
    return {t: sorted(set(v)) for t, v in out.items()}


def placebo_pre(S: pd.DataFrame, A: dict, seed: int, busy1: np.ndarray | None = None) -> dict[str, list]:
    """P1：同一只票在信号日前 [PRE_LO, PRE_HI] 个交易日里随机一天；busy1[d, j] = [d − PRE_BACK, d + PRE_FWD] 内有开示（不用那天）。"""
    rng = np.random.default_rng(seed)
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    pos = pd.Series(np.arange(len(days)), index=days)
    fin = np.isfinite(A["C"])
    out: dict[str, list] = {}
    for t, d in zip(S["ticker"], S["buy_sig"]):
        k, j = pos.get(d), col.get(t)
        if k is None or j is None:
            continue
        lo, hi = int(k) - PRE_LO, int(k) - PRE_HI
        if lo < 0:
            continue
        cand = [i for i in range(lo, hi + 1) if fin[i, j] and (busy1 is None or not busy1[i, j])]
        if not cand:
            continue
        out.setdefault(t, []).append(days[int(rng.choice(cand))])
    return {t: sorted(set(v)) for t, v in out.items()}


def day_features(A: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """每只票每天：收盘对前一日 %、量 ÷ 前 20 日均量、收阳（收 ≥ 开）。"""
    C = pd.DataFrame(A["C"]); V = pd.DataFrame(A["V"])
    ret = (C / C.shift(1) - 1).to_numpy() * 100
    vr = (V / V.rolling(20, min_periods=10).mean().shift(1)).to_numpy()
    up = (A["C"] >= A["O"])
    return ret, vr, up


def placebo_matched(S: pd.DataFrame, A: dict, quiet: np.ndarray, feats: tuple, seed: int) -> tuple[dict[str, list], int]:
    """PL-B（C3 用）：同一只票、信号日前后 MATCH_WIN 个交易日内、之前 10 日没有开示、且同样「收盘 ≥ +2% ∧ 量比 ≥ 2 ∧ 收阳」的随机一天；找不到的事件数一并返回。"""
    rng = np.random.default_rng(seed)
    ret, vr, upd = feats
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    pos = pd.Series(np.arange(len(days)), index=days)
    out: dict[str, list] = {}
    miss = 0
    for t, d in zip(S["ticker"], S["buy_sig"]):
        k, j = pos.get(d), col.get(t)
        if k is None or j is None:
            miss += 1
            continue
        lo, hi = max(0, int(k) - MATCH_WIN), min(len(days) - 1, int(k) + MATCH_WIN)
        seg = np.arange(lo, hi + 1)
        ok = quiet[lo:hi + 1, j] & (ret[lo:hi + 1, j] >= REACT_MIN) & (vr[lo:hi + 1, j] >= VR_MIN) & upd[lo:hi + 1, j]
        cand = seg[np.nan_to_num(ok.astype(float)) > 0]
        if not len(cand):
            miss += 1
            continue
        out.setdefault(t, []).append(days[int(rng.choice(cand))])
    return {t: sorted(set(v)) for t, v in out.items()}, miss


def neutral(E: pd.DataFrame, kind: str = "base") -> pd.DataFrame:
    """P3 信息对照（按「公司 × 开示日」）：予想重申 = 当天所有行 |rev| = 0（有定义的）、净利润予想没改、|yoy| < 10% 的決算短信行；
    kind = "C3" → 再加同样的反应条件、buy_sig = r；kind = "C5" → FY 行 |g_next| < 5% ∧ |beat| < 5% ∧ |yoy| < 10%。"""
    is_fs = E["doc"].str.contains("FinancialStatements")
    if kind == "C5":
        m = (E["per"] == "FY") & E["doc"].str.startswith("FY") & (E["g_next"].abs() < NEUTRAL_G) & (E["beat"].abs() < NEUTRAL_B) & (E["yoy"].abs() < NEUTRAL_YOY)
    else:
        moved = E.assign(_mv=((E["rev"].abs() > 0) | (E["rev_np"].abs() > 0)).fillna(False)).groupby(["ticker", "sig_day"])["_mv"].transform("any")
        m = E["pos"] & (E["rev"] == 0) & is_fs & (E["rev_np"].fillna(0) == 0) & (E["yoy"].abs() < NEUTRAL_YOY) & ~moved
        if kind == "C3":
            m &= (E["react"] >= REACT_MIN) & (E["vr_r"] >= VR_MIN) & (E["up_r"] == 1) & E["r"].notna()
    S = E[m.fillna(False).to_numpy(bool)].copy()
    S["buy_sig"] = S["r"] if kind == "C3" else S["sig_day"]
    S["prio"] = 0.0
    S = S.sort_values(["buy_sig", "ticker"]).drop_duplicates(subset=["ticker", "buy_sig"])
    return S.reset_index(drop=True)


def down(E: pd.DataFrame, th: float = DOWN_MIN) -> pd.DataFrame:
    """方向对照：下修同样做多（只描述）。"""
    m = E["pos"] & (E["rev"] <= -th)
    S = E[m.fillna(False).to_numpy(bool)].copy()
    S["buy_sig"], S["prio"] = S["sig_day"], 0.0
    return S.sort_values(["buy_sig", "ticker"]).drop_duplicates(subset=["ticker", "buy_sig"]).reset_index(drop=True)


# ───────────────────────── 统计与判定 ─────────────────────────
def stats(T: pd.DataFrame, win: tuple[str, str] | None = None) -> dict:
    if not len(T):
        return {"n": 0, "win": None, "mean": None, "sd": None, "hold": None}
    x = T[in_window(T["sig_date"], win)] if win else T
    if not len(x):
        return {"n": 0, "win": None, "mean": None, "sd": None, "hold": None}
    return {"n": int(len(x)), "win": round(float((x["net"] > 0).mean() * 100), 2), "mean": round(float(x["net"].mean()), 3),
            "sd": round(float(x["net"].std(ddof=0)), 2), "hold": round(float(x["hold_days"].mean()), 1)}


def boot_samples(T: pd.DataFrame, win: tuple[str, str], n: int = BOOT_N, seed: int = SEED0) -> tuple[np.ndarray, np.ndarray]:
    """按事件周（W-FRI）聚类的自助法样本：每笔均值、胜率（各 n 个）；样本太少 → 空。"""
    x = T[in_window(T["sig_date"], win)] if len(T) else T
    if len(x) < 10:
        return np.zeros(0), np.zeros(0)
    wk = pd.to_datetime(x["sig_date"]).dt.to_period("W-FRI")
    codes, uniq = pd.factorize(wk)
    net = x["net"].to_numpy(float)
    sums = np.bincount(codes, weights=net, minlength=len(uniq))
    wins = np.bincount(codes, weights=(net > 0).astype(float), minlength=len(uniq))
    cnt = np.bincount(codes, minlength=len(uniq)).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uniq), size=(n, len(uniq)))
    return sums[idx].sum(1) / cnt[idx].sum(1), wins[idx].sum(1) / cnt[idx].sum(1) * 100


def cluster_boot(T: pd.DataFrame, win: tuple[str, str], n: int = BOOT_N, seed: int = SEED0) -> dict:
    """周聚类自助法：每笔均值与胜率的 2.5 / 97.5 分位。"""
    m, w = boot_samples(T, win, n, seed)
    if not len(m):
        return {"mean_lo": None, "mean_hi": None, "win_lo": None, "win_hi": None}
    return {"mean_lo": round(float(np.percentile(m, 2.5)), 3), "mean_hi": round(float(np.percentile(m, 97.5)), 3),
            "win_lo": round(float(np.percentile(w, 2.5)), 2), "win_hi": round(float(np.percentile(w, 97.5)), 2)}


def diff_lower(T: pd.DataFrame, B: pd.DataFrame, win: tuple[str, str]) -> float | None:
    """(候选 − 基准) 每笔均值的周聚类自助法 2.5 分位（两边独立重抽）。"""
    a, _ = boot_samples(T, win)
    b, _ = boot_samples(B, win, seed=SEED0 + 1)
    if not len(a) or not len(b):
        return None
    return round(float(np.percentile(a - b, 2.5)), 3)


def quantiles(runs: list[dict], q: float, parametric: bool = False) -> dict:
    """对照各种子的 {win, mean} → q 分位；parametric = True → 均值 + t(q, n−1) × 标准差。"""
    ws = [r["win"] for r in runs if r.get("win") is not None]
    ms = [r["mean"] for r in runs if r.get("mean") is not None]
    if not ws:
        return {"win": None, "mean": None, "seeds": 0}
    if parametric and len(ws) >= 3:
        k = t_quantile(q / 100, len(ws) - 1)
        return {"win": round(float(np.mean(ws) + k * np.std(ws, ddof=1)), 2), "mean": round(float(np.mean(ms) + k * np.std(ms, ddof=1)), 3),
                "seeds": len(ws), "q": q, "kind": "param"}
    return {"win": round(float(np.percentile(ws, q)), 2), "mean": round(float(np.percentile(ms, q)), 3), "seeds": len(ws), "q": q, "kind": "pct"}


_T99 = {2: 6.965, 4: 3.747, 9: 2.821, 14: 2.624, 19: 2.539, 29: 2.462, 49: 2.405, 99: 2.365, 199: 2.345}


def t_quantile(q: float, df: int) -> float:
    """t 分布的 q 分位（只需 0.99；按自由度查表、之间线性插值；不依赖 scipy）。"""
    if abs(q - 0.99) > 1e-9:
        raise ValueError("只写了 0.99 的表")
    ks = sorted(_T99)
    if df <= ks[0]:
        return _T99[ks[0]]
    if df >= ks[-1]:
        return _T99[ks[-1]]
    lo = max(k for k in ks if k <= df)
    hi = min(k for k in ks if k >= df)
    if lo == hi:
        return _T99[lo]
    return _T99[lo] + (_T99[hi] - _T99[lo]) * (df - lo) / (hi - lo)


def _c(x) -> float:
    return float("nan") if x is None else float(x)


def gate_x(c: dict, base: dict, p0q: dict, c20: dict, p1_mean: float | None, p3: dict) -> bool:
    """探索门（方案乙 + 最低效应）：每笔 ≥ 基准 + 0.5 pp 且 胜率 ≥ 基准 且 每笔 > P0 95 分位 且 20 日卖法每笔 > P1 均值 且 每笔 > P3 每笔。"""
    m = _c(c.get("mean"))
    return bool(m >= _c(base.get("mean")) + GATE_MEAN_PP and _c(c.get("win")) >= _c(base.get("win")) and m > _c(p0q.get("mean"))
                and _c(c20.get("mean")) > _c(p1_mean) and m > _c(p3.get("mean")))


def p1_fails(c20: dict, boot20: dict, p1_mean: float | None) -> list[str]:
    """P1 必要条件：候选（20 日卖法）每笔 − P1 均值 ≥ +1.0 pp 且候选（20 日卖法）每笔的周聚类 95% 区间下限 > P1 均值。"""
    out = []
    if not _c(c20.get("mean")) - _c(p1_mean) >= P1_MEAN_PP:
        out.append(f"P1 20 日卖法每笔 {_c(c20.get('mean')):+.2f}% − 事前安慰剂 {_c(p1_mean):+.2f}% < {P1_MEAN_PP:.1f} pp")
    if not _c(boot20.get("mean_lo")) > _c(p1_mean):
        out.append(f"P1 20 日卖法每笔区间下限 {_c(boot20.get('mean_lo')):+.2f}% ≤ 事前安慰剂 {_c(p1_mean):+.2f}%")
    return out


def s_fails(c: dict, base: dict, ctrls: dict[str, dict], p3: dict | None, port: dict | None, port_base: dict | None,
            no_s1: bool = False, diff_lo: float | None = None) -> list[str]:
    """确认窗口判定；返回没满足的条件（空 = 成立）。ctrls = {"P0": 上限, ("PL-B": ...)}；no_s1 = C4 免胜率类条件。"""
    out = []
    if not no_s1 and not _c(c.get("win")) >= _c(base.get("win")) + WIN_UP_PP:
        out.append(f"S1 胜率 {_c(c.get('win')):.1f}% < 基准 {_c(base.get('win')):.1f}% + {WIN_UP_PP:.0f} pp")
    if not _c(c.get("mean")) >= _c(base.get("mean")) + MEAN_UP_PP:
        out.append(f"S2 每笔 {_c(c.get('mean')):+.2f}% < 基准 {_c(base.get('mean')):+.2f}% + {MEAN_UP_PP:.1f} pp")
    if diff_lo is not None and not diff_lo > 0:
        out.append(f"S2 (候选 − 基准) 周聚类区间下限 {diff_lo:+.2f} pp ≤ 0")
    if not _c(c.get("n")) >= MIN_N_ABS:
        out.append(f"S3 笔数 {c.get('n')} < {MIN_N_ABS}")
    for k, q in ctrls.items():
        if not no_s1 and not _c(c.get("win")) > _c(q.get("win")):
            out.append(f"S5 胜率 {_c(c.get('win')):.1f}% ≤ {k} 上限 {_c(q.get('win')):.1f}%")
        if not _c(c.get("mean")) > _c(q.get("mean")):
            out.append(f"S5 每笔 {_c(c.get('mean')):+.2f}% ≤ {k} 上限 {_c(q.get('mean')):+.2f}%")
    if p3 is not None:
        if not no_s1 and not _c(c.get("win")) >= _c(p3.get("win")) + P3_WIN_PP:
            out.append(f"P3 胜率 {_c(c.get('win')):.1f}% < 信息对照 {_c(p3.get('win')):.1f}% + {P3_WIN_PP:.0f} pp")
        if not _c(c.get("mean")) >= _c(p3.get("mean")) + P3_MEAN_PP:
            out.append(f"P3 每笔 {_c(c.get('mean')):+.2f}% < 信息对照 {_c(p3.get('mean')):+.2f}% + {P3_MEAN_PP:.1f} pp")
    if port is not None and port_base is not None:
        if not _c(port.get("calmar")) >= _c(port_base.get("calmar")) - CALMAR_TOL:
            out.append(f"S4 组合 Calmar {_c(port.get('calmar')):.3f} < 现行 {_c(port_base.get('calmar')):.3f} − {CALMAR_TOL}")
        if not _c(port.get("dd")) >= _c(port_base.get("dd")) - DD_TOL_PP:
            out.append(f"S4 组合回撤 {_c(port.get('dd')):.2f}% 比现行 {_c(port_base.get('dd')):.2f}% 深 {DD_TOL_PP:.0f} pp 以上")
        if not _c(port.get("n")) >= MIN_N_FRAC_PORT * _c(port_base.get("n")):
            out.append(f"S4 组合个股笔数 {port.get('n')} < 现行 {port_base.get('n')} 的 {MIN_N_FRAC_PORT:.0%}")
    return out


def improve_ok(c: dict, base: dict, ctrls: dict[str, dict], p3: dict | None, p1: list[str]) -> bool:
    """「选股改进」：胜率 ≥ 基准 + 4 pp ∧ 每笔 ≥ 基准 + 0.5 pp ∧ S5 ∧ P1 ∧ P3。"""
    if not (_c(c.get("win")) >= _c(base.get("win")) + IMPROVE_WIN_PP and _c(c.get("mean")) >= _c(base.get("mean")) + IMPROVE_MEAN_PP):
        return False
    rest = s_fails(c, base, ctrls, p3, None, None)
    return not p1 and not any(r.startswith(("S5", "P3")) for r in rest)


def baseline_entries() -> dict[str, list]:
    """基准 B 的信号日：allstock_train.pkl 里 W2 保留（w5v ≥ 1.0 或缺值）的突破。"""
    from qbreak import jquants as JQ
    fp = JQ.cache_dir() / "allstock_train.pkl"
    if not fp.exists():
        raise SystemExit(f"缺基准表 {fp}：先运行 scripts/allstock_study.py")
    T = pd.read_pickle(fp)
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    W = T[(T["w5v"] >= 1.0) | ~np.isfinite(T["w5v"])]
    return {t: sorted(set(g["sig_date"])) for t, g in W.groupby("ticker")}


def eff_range(T: pd.DataFrame, win: tuple[str, str]) -> tuple[str, str] | None:
    """候选在窗口内「第一笔到最后一笔信号日」的范围（基准 / 对照只取这一段）。"""
    if not len(T):
        return None
    x = T[in_window(T["sig_date"], win)]
    if not len(x):
        return None
    return (str(x["sig_date"].min().date()), str(x["sig_date"].max().date()))


def segments(T: pd.DataFrame, win: tuple[str, str]) -> dict:
    """描述性分段（只报不判定）。"""
    x = T[in_window(T["sig_date"], win)] if len(T) else T
    out = {}
    if not len(x):
        return out
    seg = {"一手 ≤ ¥25 万": x["ev_lot_yen"] <= 250000, "一手 ≤ ¥34 万": x["ev_lot_yen"] <= 340000, "一手 > ¥34 万": x["ev_lot_yen"] > 340000,
           "20 日成交额 ≥ ¥500 万": x["ev_va20"] >= 5e6, "20 日成交额 ≥ ¥5,000 万": x["ev_va20"] >= 5e7, "20 日成交额 < ¥5,000 万": x["ev_va20"] < 5e7,
           "可行子集（一手 ≤ ¥34 万 ∧ 成交额 ≥ ¥500 万）": (x["ev_lot_yen"] <= 340000) & (x["ev_va20"] >= 5e6),
           "盘后开示": x["ev_after_close"] == True, "盘中开示": x["ev_after_close"] == False,          # noqa: E712
           "修正文档": x["ev_doc"] == "EarnForecastRevision", "決算短信内": x["ev_doc"] != "EarnForecastRevision"}
    if "ev_topix500" in x.columns:
        seg["时点 TOPIX 500 内"] = x["ev_topix500"] == 1
        seg["时点 TOPIX 500 外"] = x["ev_topix500"] != 1
    for k, m in seg.items():
        out[k] = stats(x[m.fillna(False).to_numpy(bool)])
    for y, g in x.groupby(pd.to_datetime(x["sig_date"]).dt.year):
        out[f"年 {y}"] = stats(g)
    return out


def top4_per_day(S: pd.DataFrame) -> pd.DataFrame:
    """组合只能吃到的部分：每个买入信号日按优先级前 4 条。"""
    return S.sort_values(["buy_sig", "prio", "ticker"], ascending=[True, False, True]).groupby("buy_sig").head(4).reset_index(drop=True)


# ───────────────────────── 组合（S4） ─────────────────────────
def portfolio(cands_ev: dict[str, pd.DataFrame], p, jmem: str = "U1") -> dict:
    """S0C2（现行）vs 加事件（P-mix：同日先突破、再事件按 rev 降序）/ 事件替换突破（P-event）；每个窗口 {cagr, dd, calmar, n, mean, win}。"""
    import leap_confirm as LC
    ctx = LC.context("J", jmem=jmem)
    fr0 = LC.frames(ctx, p)
    run_fn = LC.runner(ctx, fr0)
    out = {"base": LC.run(ctx, run_fn, fr0, p)}
    for cid, S in cands_ev.items():
        ev = {t: set(g["buy_sig"]) for t, g in S.groupby("ticker") if t in fr0}
        pr = {(r.ticker, pd.Timestamp(r.buy_sig)): -1000.0 + float(r.prio) for r in S.itertuples() if r.ticker in fr0}   # 突破（0 分）先、事件按 rev 降序
        p_use = replace(p, **EVENT_EXIT) if cid == "C4" else p
        mix = {t: df.assign(entry=df["entry"].to_numpy(bool) | df.index.isin(list(ev.get(t, ())))) for t, df in fr0.items()}
        only = {t: df.assign(entry=df.index.isin(list(ev.get(t, ())))) for t, df in fr0.items()}
        res = {"events_in_pool": int(sum(len(v) for v in ev.values()))}
        if cid != "C4":
            res["mix"] = LC.run(ctx, run_fn, mix, p_use, priority=pr)
        res["event"] = LC.run(ctx, run_fn, only, p_use, priority=pr)
        out[cid] = res
    return out


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/fins_event_study.py", "scripts/fins_event_data.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def bulk_sha(limit: int = 400) -> dict:
    from qbreak import jq_data as JD
    d = JD.bulk_dir() / "fins/summary"
    out = {}
    for fp in sorted(d.glob("**/*.csv.gz"))[:limit]:
        out[str(fp.relative_to(d))] = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
    return out


def topix500_flag(S: pd.DataFrame) -> np.ndarray:
    try:
        import candle_data as CD
        D = CD.load()
        col = {t: j for j, t in enumerate(D["names"])}
        pos = pd.Series(np.arange(len(D["days"])), index=pd.DatetimeIndex(D["days"]))
        m = D["mem"]["U1"]
        out = np.full(len(S), np.nan)
        for k, (t, d) in enumerate(zip(S["ticker"], S["buy_sig"])):
            j, i = col.get(t), pos.get(d)
            if j is not None and i is not None:
                out[k] = float(m[int(i), j])
        return out
    except Exception:                                                        # noqa: BLE001
        return np.full(len(S), np.nan)


def last_modified_summary() -> dict:
    """bulk/_last_modified.json 里 fins 文件的 LastModified 时刻（UTC）分布（只有 live 文件能证明当天开示次日凌晨可取）。"""
    from qbreak import jq_data as JD
    fp = JD.bulk_dir() / "_last_modified.json"
    if not fp.exists():
        return {}
    d = json.loads(fp.read_text(encoding="utf-8"))
    ts = [v for k, v in d.items() if "fins/summary" in k]
    hours = pd.Series([str(v)[11:16] for v in ts])
    return {"files": len(ts), "utc_time_counts": hours.value_counts().head(5).to_dict(), "max": max(ts) if ts else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["explore", "confirm"], required=True)
    ap.add_argument("--seeds", type=int, default=SEEDS)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--no-portfolio", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    t_start = time.time()
    import allstock_data as AD
    from qbreak.trader import load_params
    stage = a.stage
    if stage == "confirm" and not CONFIRM_IDS:
        raise SystemExit("确认阶段要先把探索门通过的候选写进 CONFIRM_IDS 并提交")
    ids = tuple(CANDS) if stage == "explore" else tuple(c for c in CANDS if c in CONFIRM_IDS)
    say = lambda s_: print(s_, flush=True)                                   # noqa: E731
    A = AD.load()
    days = pd.DatetimeIndex(A["days"])
    c_end = min(pd.Timestamp(WIN_C[1]), days[-1 - END_CUT])
    wins = {"X": WIN_X} if stage == "explore" else {"X": WIN_X, "C": (WIN_C[0], str(c_end.date()))}
    D_all = load_events(A, a.rebuild)
    E = pool(D_all, A)
    if stage == "explore":
        E = E[in_window(E["sig_day"], WIN_X)].reset_index(drop=True)          # 探索阶段只看 X
        assert (pd.to_datetime(E["sig_day"]) <= pd.Timestamp(WIN_X[1])).all()
    else:
        E = E[in_window(E["sig_day"], (WIN_X[0], wins["C"][1]))].reset_index(drop=True)
    say(f"事件池 {len(E)} 条（全部开示 {len(D_all)}）；{stage}；候选 {ids}；窗口 {wins}；用时 {time.time() - t_start:.0f}s")
    p = load_params(market="JP")
    p_ev = replace(p, **EVENT_EXIT)
    build_frames(A, p)
    say(f"指标表 {len(_FR)} 只（退市 {len(_DELIST)}）；{time.time() - t_start:.0f}s")
    hist = hist_matrix(A)
    quiet = quiet_matrix(D_all, days, list(A["names"]))                        # 只看过去 10 日
    busy1 = ~quiet_matrix(D_all, days, list(A["names"]), back=PRE_BACK, fwd=PRE_FWD)   # P1：[买入日−5, 买入日+25] 内有开示 → 开示 k 让 [k−25, k+5] 都不能当买入日
    feats = day_features(A)
    b_ent = baseline_entries()
    TB = run_trades(b_ent, p, a.procs)
    TB20 = run_trades(b_ent, p_ev, a.procs)
    say(f"基准 B {stats(TB)}、B20 {stats(TB20)}；{time.time() - t_start:.0f}s")
    res: dict = {"stage": stage, "git": git_info(), "windows": wins, "seeds": a.seeds, "confirm_ids": list(CONFIRM_IDS),
                 "base_full": {w: {"B": stats(TB, win), "B20": stats(TB20, win)} for w, win in wins.items()},
                 "pool_n": int(len(E)), "cands": {}, "controls": {}, "last_modified": last_modified_summary()}
    trades: dict[str, pd.DataFrame] = {}
    trades20: dict[str, pd.DataFrame] = {}
    evs: dict[str, pd.DataFrame] = {}
    for cid in ids:
        S = dedupe(select(E, cid), days)
        T = attach(run_trades(entries_of(S), p_ev if cid == "C4" else p, a.procs), S)
        T20 = T if cid == "C4" else attach(run_trades(entries_of(S), p_ev, a.procs), S)
        trades[cid], trades20[cid], evs[cid] = T, T20, S
        res["cands"][cid] = {"desc": CANDS[cid], "n_events": int(len(S))}
        say(f"{cid}：事件 {len(S)}、" + "、".join(f"{w} {stats(T, win)}" for w, win in wins.items()) + f"；{time.time() - t_start:.0f}s")
    # 对照（一次）
    ctrl_ev = {"P3": neutral(E), "P3_C3": neutral(E, "C3"), "P3_C5": neutral(E, "C5"), "down": down(E)}
    ctrl_tr = {"P3": run_trades(entries_of(ctrl_ev["P3"]), p, a.procs), "P3_C4": run_trades(entries_of(ctrl_ev["P3"]), p_ev, a.procs),
               "P3_C3": run_trades(entries_of(ctrl_ev["P3_C3"]), p, a.procs), "P3_C5": run_trades(entries_of(ctrl_ev["P3_C5"]), p, a.procs),
               "down": run_trades(entries_of(ctrl_ev["down"]), p, a.procs)}
    if "C1" in ids:
        S1r = evs["C1"].copy()
        S1r["buy_sig"] = S1r["r"]
        S1r = S1r.dropna(subset=["buy_sig"]).drop_duplicates(subset=["ticker", "buy_sig"])
        ctrl_tr["C1_r"] = run_trades(entries_of(S1r), p, a.procs)
        if stage == "explore":
            ctrl_tr["C1_gap8"] = run_trades(entries_of(evs["C1"]), p, a.procs, gap=GAP_RELAX)
    for k, T in ctrl_tr.items():
        res["controls"][k] = {**{w: stats(T, win) for w, win in wins.items()}, "n_events": int(len(ctrl_ev.get(k.replace("_C4", ""), pd.DataFrame())))}
    say("对照：" + "；".join(f"{k} {res['controls'][k]['X']}" for k in ctrl_tr) + f"；{time.time() - t_start:.0f}s")
    p3_key = lambda cid: {"C3": "P3_C3", "C4": "P3_C4", "C5": "P3_C5"}.get(cid, "P3")   # noqa: E731
    # 随机对照（种子）
    pl: dict[str, dict[str, list]] = {}
    for cid in ids:
        S = evs[cid]
        p_use = p_ev if cid == "C4" else p
        pl[cid] = {"P0": [], "P1": []}
        if cid == "C3":
            pl[cid]["PL-B"] = []
        for k in range(a.seeds):
            seed = SEED0 + k
            T = run_trades(placebo_sameday(S, A, quiet, seed, hist), p_use, a.procs)
            pl[cid]["P0"].append({w: stats(T, win) for w, win in wins.items()})
            T = run_trades(placebo_pre(S, A, seed, busy1), p_ev, a.procs)          # P1 一律事件卖法
            pl[cid]["P1"].append({w: stats(T, win) for w, win in wins.items()})
            if cid == "C3":
                ent, miss = placebo_matched(S, A, quiet, feats, seed)
                T = run_trades(ent, p_use, a.procs)
                pl[cid]["PL-B"].append({**{w: stats(T, win) for w, win in wins.items()}, "miss": miss})
        say(f"{cid} 对照 {a.seeds} 种子完成；{time.time() - t_start:.0f}s")
    # 汇总
    def p1_mean(cid, w):
        v = [r[w]["mean"] for r in pl[cid]["P1"] if r[w].get("mean") is not None]
        return round(float(np.mean(v)), 3) if v else None
    entered = {}
    for cid in ids:
        T, T20, S = trades[cid], trades20[cid], evs[cid]
        B_use = TB20 if cid == "C4" else TB
        rng = {w: (eff_range(T, win) or win) for w, win in wins.items()}
        c = {w: stats(T, rng[w]) for w in wins}
        c20 = {w: stats(T20, rng[w]) for w in wins}
        base = {w: stats(B_use, rng[w]) for w in wins}
        boot = {w: cluster_boot(T, rng[w]) for w in wins}
        boot20 = {w: cluster_boot(T20, rng[w]) for w in wins}
        dlo = {w: diff_lower(T, B_use, rng[w]) for w in wins}
        p3 = {w: stats(ctrl_tr[p3_key(cid)], rng[w]) for w in wins}
        q_x = {k: quantiles([r["X"] for r in runs], Q_X) for k, runs in pl[cid].items() if k != "P1"}
        p1m = {w: p1_mean(cid, w) for w in wins}
        entered[cid] = gate_x(c["X"], base["X"], q_x["P0"], c20["X"], p1m["X"], p3["X"])
        Sx = S.assign(topix500=topix500_flag(S))
        Tx = T.copy()
        if len(Tx):
            key = Sx.drop_duplicates(subset=["ticker", "buy_sig"]).set_index(["ticker", "buy_sig"])["topix500"]
            Tx["ev_topix500"] = key.reindex(pd.MultiIndex.from_arrays([Tx["ticker"], Tx["sig_date"]])).to_numpy()
        top4 = top4_per_day(S)
        key4 = set(zip(top4["ticker"], top4["buy_sig"]))
        m4 = np.array([(t, d) in key4 for t, d in zip(T["ticker"], T["sig_date"])], bool) if len(T) else np.zeros(0, bool)
        res["cands"][cid].update({
            "range": rng, "stats": c, "stats20": c20, "base": base, "boot": boot, "boot20": boot20, "diff_lo": dlo, "p3": p3,
            "ctrl_X": q_x, "p1_mean": p1m, "entered": bool(entered[cid]), "p1_fails_X": p1_fails(c20["X"], boot20["X"], p1m["X"]),
            "gap_abandon_pct": round(float((S["gap_t0"] > 3).mean() * 100), 1) if len(S) else None,
            "events_per_day": {k: round(float(v), 1) for k, v in S.groupby("buy_sig").size().describe(percentiles=[.5, .9]).items()} if len(S) else {},
            "top4_share": round(float(len(top4) / max(1, len(S)) * 100), 1),
            "top4_stats": {w: stats(T[m4], rng[w]) for w in wins} if len(T) else {},
            "segments": {w: segments(Tx, rng[w]) for w in wins},
            "reasons": {w: T[in_window(T["sig_date"], rng[w])]["reason"].value_counts().to_dict() for w in wins} if len(T) else {},
            "pl_b_miss": [r.get("miss") for r in pl[cid].get("PL-B", [])][:3]})
    res["entered"] = [cid for cid in ids if entered[cid]]
    if stage == "confirm":
        port = None
        if not a.no_portfolio:
            for jm, key in (("U1", "portfolio_U1"), ("U0", "portfolio_U0")):
                try:
                    res[key] = portfolio({cid: evs[cid] for cid in ids}, p, jm)
                except Exception as e:                                           # noqa: BLE001
                    res[key] = {"error": str(e)[:300]}
            port = res.get("portfolio_U1") if "error" not in (res.get("portfolio_U1") or {"error": 1}) else None
        for cid in ids:
            r_ = res["cands"][cid]
            c, c20, base, boot20 = r_["stats"]["C"], r_["stats20"]["C"], r_["base"]["C"], r_["boot20"]["C"]
            q_c = {k: quantiles([r["C"] for r in runs], Q_C, parametric=True) for k, runs in pl[cid].items() if k != "P1"}
            r_["ctrl_C"] = q_c
            pb = port["base"]["J2"] if port else None
            pc = (port[cid].get("mix") or port[cid]["event"])["J2"] if (port and cid in port) else None
            p1f = p1_fails(c20, boot20, r_["p1_mean"]["C"])
            fails = s_fails(c, base, q_c, r_["p3"]["C"], pc, pb, no_s1=cid in NO_S1, diff_lo=r_["diff_lo"]["C"]) + p1f
            imp = improve_ok(c, base, q_c, r_["p3"]["C"], p1f)
            r_["fails_C"] = fails
            r_["verdict"] = "成立（J 单窗口）→ 前向记录、用户决定" if not fails else ("选股改进（只记录）" if imp else "不成立")
        if "C1" in ids and res["cands"]["C1"].get("fails_C"):
            for cid in ("C2", "C3", "C4"):
                if cid in res["cands"] and not res["cands"][cid].get("fails_C"):
                    res["cands"][cid]["verdict"] += "（C1 未通过 → 读作「子集挑选」，只记录）"
    res["elapsed_s"] = round(time.time() - t_start)
    res["bulk_sha256_16"] = bulk_sha()
    out = Path(paths.home()) / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / OUT_MD).write_text(report(res), encoding="utf-8")
    for cid, T in trades.items():
        T.to_pickle(cache_out() / f"fins_event_trades_{cid}_{stage}.pkl")
    say(report(res))
    say(f"用时 {res['elapsed_s']}s；输出 {out / OUT_MD}")
    return 0


def _fmt(s: dict) -> str:
    if not s or s.get("n") in (None, 0):
        return "0 笔"
    return f"{s['n']} 笔 胜率 {s['win']:.1f}% 每笔 {s['mean']:+.2f}%"


def report(res: dict) -> str:
    L = [f"# 決算 / 予想修正「开示当买点」研究 —— {res['stage']}（git {res['git'].get('rev')}{' 未提交' if res['git'].get('dirty') else ''}）", ""]
    L.append(f"事件池 {res['pool_n']} 条；窗口 {res['windows']}；对照种子 {res['seeds']}；确认候选 {res.get('confirm_ids')}；探索门通过 {res.get('entered')}")
    for w, b in res["base_full"].items():
        L.append(f"基准 {w}（整个窗口）：全市场 W2 突破 B {_fmt(b['B'])}；B20（事件卖法） {_fmt(b['B20'])}")
    C = res["controls"]
    for k, lab in (("P3", "P3 信息对照（予想重申的決算短信、现行卖法）"), ("P3_C4", "P3 同上、事件卖法（C4 用）"), ("P3_C3", "P3 重申 ∧ 反应条件 → r+1（C3 用）"),
                   ("P3_C5", "P3 FY 对照（|g_next| < 5% ∧ |beat| < 5% ∧ |yoy| < 10%，C5 用）"), ("down", "方向对照（下修同样做多）"),
                   ("C1_r", "C1'（C1 同一事件、无条件在 r+1 开盘买；C3 的对照）"), ("C1_gap8", "C1 跳空放宽到 8%（只描述、只在探索）")):
        if k in C:
            L.append(f"{lab}：" + "；".join(f"{w} {_fmt(C[k][w])}" for w in res["windows"]) + f"（事件 {C[k].get('n_events')}）")
    L.append("")
    for cid, c in res["cands"].items():
        L.append(f"## {cid} {c['desc']}（事件 {c.get('n_events')}；跳空 > 3% 放弃 {c.get('gap_abandon_pct')}%；"
                 f"每日事件数中位 {c.get('events_per_day', {}).get('50%')} / 90 分位 {c.get('events_per_day', {}).get('90%')}；前 4 占 {c.get('top4_share')}%）")
        for w in res["windows"]:
            s_, b, bs, b20 = c["stats"][w], c["boot"][w], c["base"][w], c["stats20"][w]
            L.append(f"  {w} {c['range'][w]}：{_fmt(s_)}（sd {s_.get('sd')} pp、持仓 {s_.get('hold')} 日；周聚类区间 每笔 [{b.get('mean_lo')}, {b.get('mean_hi')}] "
                     f"胜率 [{b.get('win_lo')}, {b.get('win_hi')}]）；同区间基准 {_fmt(bs)}；(候选 − 基准) 区间下限 {c['diff_lo'][w]} pp；"
                     f"20 日卖法 {_fmt(b20)}；P1 事前安慰剂均值 {c.get('p1_mean', {}).get(w)}；P3 同区间 {_fmt(c['p3'][w])}；前 4 子集 {_fmt(c.get('top4_stats', {}).get(w, {}))}")
        L.append("  对照 X（95 分位）：" + "；".join(f"{k} 胜率 {q.get('win')} 每笔 {q.get('mean')}" for k, q in c["ctrl_X"].items())
                 + f"；P1 条件 {'过' if not c.get('p1_fails_X') else '；'.join(c['p1_fails_X'])}；探索门 {'过' if c.get('entered') else '不过'}")
        if "ctrl_C" in c:
            L.append("  对照 C（参数化 99% 上限）：" + "；".join(f"{k} 胜率 {q.get('win')} 每笔 {q.get('mean')}" for k, q in c["ctrl_C"].items()))
            L.append(f"  判定：{c.get('verdict')}" + (f"；未满足：{'；'.join(c['fails_C'])}" if c.get("fails_C") else ""))
        for w in res["windows"]:
            seg = c["segments"].get(w) or {}
            if seg:
                L.append(f"  分段 {w}（只描述）：" + "；".join(f"{k} {_fmt(v)}" for k, v in seg.items()))
        if c.get("reasons"):
            L.append("  出场：" + "；".join(f"{w} {v}" for w, v in c["reasons"].items()))
        L.append("")
    for key in ("portfolio_U1", "portfolio_U0"):
        P = res.get(key)
        if not P or "error" in P:
            if P:
                L.append(f"## 组合 {key[-2:]}：{P['error']}")
            continue
        L.append(f"## 组合 {key[-2:]}（S0C2 现行 vs P-mix / P-event；{'主判定' if key.endswith('U1') else '另报'}）")
        for w in ("J1", "J2"):
            b = P["base"].get(w) or {}
            L.append(f"  {w} 现行：Calmar {b.get('calmar')} 回撤 {b.get('dd')} 个股 {b.get('n')} 笔 胜率 {b.get('win')} 每笔 {b.get('mean')}")
            for cid in res["cands"]:
                r = P.get(cid) or {}
                for kind in ("mix", "event"):
                    if kind in r:
                        s_ = r[kind].get(w) or {}
                        L.append(f"    {cid} {kind}：Calmar {s_.get('calmar')} 回撤 {s_.get('dd')} 个股 {s_.get('n')} 笔 胜率 {s_.get('win')} 每笔 {s_.get('mean')}（池内事件 {r.get('events_in_pool')}）")
        L.append("")
    L.append("非投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
