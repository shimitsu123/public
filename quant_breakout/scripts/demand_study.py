"""demand_study.py — 「需給・回購・決算日程・現金利益 × 全市場 W2 突破」研究（登记版：候选、资格池、对照、探索门、判定、读法全部写在这里；提交后不改规则）。

来由：用户 2026-09-27「现在下载后的所有数据中还有哪些没有用到的有用的要训练的 结合之前的研究 相互关系进行研究 让选股更加精准」。
设计 = 三份独立提案（基本面质量 / 需给流向 / 持有者结构与日程）+ 两位评审 + 综合稿 + 一份对抗审计（云端设计面板）；本文已按审计的「运行前必须修」逐条修正：
  N4 只用 12 个月口径（FY 行）并排除金融四业种；N3 的预计开示日估计器改为「所有 < d 的 FS 行 + 364 里第一个 > d」、P-cal 改为不含预计开示日的中性窗口；
  每个候选定义「资格池」（特征可算且不缺值），B / 剔除组 / 全部抽签对照都在资格池内做，全池 B 只另报；N2 的 P-match 加同规模带；PL-S 按年 × 规模带分层；
  S4 用标签矩阵当组合引擎的进场掩码（基准与候选同一套引擎信号）；N1 的必要条件改为制度信用单独同号 > 0、抽签分层加 lturn 三分位；
  信用残高公布日改为「下一周第 2 営業日」；洁净度表改口（B 的 C 逐年数字已公布：var/out/allstock_posthoc.md）；bulk_sha 加信用残高文件。
目标 = 让个股层的选股更准（胜率 / 每笔），不是新买点：五个候选都是「全市场 W2 突破信号的保留规则」（W2 池的子集）；探索 X（2017-01-04〜2021-12-30）→ 确认 C（2022-01-04〜数据末尾 − 61 个交易日）只跑一次。
不改交易规则：模拟盘、执行器（只下日経225）、W2 门槛、earnings_blackout_days 都不动；结论上限 = 「提议 + 前向记录」（用户确认才改）。
样板：scripts/fins_event_study.py（逐笔机制、对照、判定）；特征层 scripts/demand_features.py（只算「信号日已知」的特征）。

一 数据盘点（已下载、全部在 var/cache/，不入库；用 / 没用过 / 本次）
  equities/bars 全市场面板（O/H/L/C/V 复权、R = 未调整 ÷ 复权、MC、VA、listed）：本次 = 基准与拆股检查、一手 / 成交额 / PBR 分段；
  fins/summary（191k 行、111 列）：用过 OP / NP 予想、修正 %、yoy、g_next / beat（全部不过）；没用过 TrShFY / ShOutFY（自社株）、CFO / NP / TA（应计）、CashEq / ShEq、DiscDate 日程规律 → N2 / N3 / N4；
  markets/margin-interest 信用残高（2,078,595 行；Date 周五 96.7%；IssType 1 / 2 / 3；ShrtNegVol / LongNegVol / ShrtStdVol / LongStdVol 100% 有值、Neg + Std = Long）：
    用过 买残 / 卖残 ÷ 均量 的水平（jq_study M1 0.460 / M2 0.452，方向相反）；没用过 4 周变化量、制度 / 一般拆分 → N1 / N5；
  markets/short-sale-report 空売り残高：只作「有 / 无大额空头」分段（28 天内有报告的信号只 5〜11% → 到不了 S3）；
  markets/investor-types 投資部門別：只作「海外 4 周净买 > 0」分段（市场层；X 被 flow_explore 看过；事業法人 C 期 89〜94% 的周为正）；
  master/ 月末上市一览：规模带 {非 TOPIX, TOPIX Small, TOPIX 500}、Prime / Standard / Growth、33 业种（金融四业种排除）作分层 / 分段；
  var/cache/factors、leap_yf、candle_panels、earnings_hist：不用或只借（U1 成员掩码、日程核对）。事件类没有可回测的历史表 → G1 另行登记（已登记 a68af78）。

二 信号池、逐笔机制与基准
  信号池 P = allstock_train.pkl（东证一般市场、时点上市掩码、现行突破规则）里 w5v ≥ 1.0 或缺值 的信号（fins_event_study.baseline_entries 同一定义）：全期 6,511 笔。
  逐笔 = fins_event_study.build_frames + run_trades：每只票一次一仓、信号日下一开盘 ×1.001 买、开盘 > 信号日收盘 ×1.03 放弃、现行卖法、扣 ¥25 万一笔来回成本 + 滑点、退市按最后收盘、期末未平仓不算。
  资格池 E_c（每个候选）= P ∧ 特征可算且不缺值（N1 / N5：信用可用日 ≤ d 且 d − avail ≤ 15 个交易日、往前第 4 条申込日相隔 26〜36 天、L_4 ≥ 10,000 株、无拆股、IssType ∈ {1, 2}；
    N2：最近一份 FS 行 ∈ [d − 140, d) 且 b 可算、无拆股；N3：since 与 to_exp 可算；N4：FY 行 ∈ [d − 400, d) 的 NP / CFO / TA 可算、非金融四业种）。
  基准 B_c = 资格池全部信号的逐笔（候选是它的子集；只取候选「第一笔到最后一笔信号日」范围 eff_range）；全池 B（P 全部）只另报；剔除组 = E_c ∧ ¬候选；报告同时给「保留 − 剔除」与「候选 − B_c」。
  B 的 C 逐年数字已公布（var/out/allstock_posthoc.md：2022 800 笔 / 2023 955 / 2024 686 / 2025 753 / 2026 379）—— 候选特征与保留 / 剔除的收益没看过。

三 特征（demand_features.py；可用日 = 公布后第一个交易日 ≤ d；决算短信 = DiscDate 严格早于 d）
  信用残高：L_now = avail ≤ d 的最新一条（d − avail ≤ 15 个交易日）、L_4 = 再往前第 4 条（申込日相隔 26〜36 天）；ΔL% = (L_now − L_4) ÷ L_4；制度 / 一般各自同法；[L_4 申込日, d] 内 R 跳变 > 1% → 缺值。
  自社株：FS 行（连结优先、同键第一次开示）b = (ΔTrShFY − min(0, ΔShOutFY)) ÷ ShOutFY_前一份（消却加回；两份相隔 ≤ 200 天、|ΔShOutFY| ≤ 50%、之间无 R 跳变）；取最近一份 ∈ [d − 140, d)。
  日程：since = d 离最近一次任何开示（含订正）的交易日数；to_exp = d 离「所有 DiscDate < d 的 FS 行 + 364 天里第一个 > d」的交易日数。
  应计：最近一条 FY 行（< d、≤ 400 天）accrual = (NP − CFO) ÷ TA、CFO > 0；金融四业种（銀行 / 証券・商品先物 / 保険 / その他金融，时点分类）排除。
  分段 / 分层：规模带、Prime / Standard / Growth、IssType、有 / 无大额空头、海外 4 周净买、lturn 三分位（全池）、r20 五分位（全池）、一手、成交额、时点 TOPIX 500、PBR < 1、
  ROE ≥ 8% ∧ EqAR ≥ 40%、净现金、7 日内有開示、最近一次开示是短信 / 修正、年。缺值 → 不在资格池。

四 候选（≤ 5；阈值写死、不做网格）
  N1 信用買い残の減少：E_N1 ∧ ΔL% ≤ −10%。方向 = 保留组更好（买残 = 6 个月内必须了结的卖压；4 周在减少 = 供给已被消化）。诚实：jq_study 的「水平」方向相反 → 50/50；
    百分比不用 ÷ 均量（后者是小盘股代理）；ΔL% 与 r20 秩相关 −0.09、与 lturn +0.06（温和的动量 / 流动性倾斜）→ 抽签分层加 lturn 三分位、另报同 r20 五分位内 保留 vs 剔除。
    必要条件（C）：制度信用 LongStdVol 单独重算（ΔL_std% ≤ −10%）的「保留 − 剔除」> 0；一般信用版只描述。方向对照（描述）：ΔL% ≥ +10%。
  N2 自社株買い進行中：E_N2 ∧ 0.25% ≤ b ≤ 20%。方向 = 保留组更好（公司自己的持续买盘 + 低估信号；是状态不是事件）。诚实：滞后 1〜4 个月的标签；保留率随规模上升 → 分层 + P-match 同规模带。
    必要条件：P-match（同周 ±1 周 ∧ 同规模带 ∧ 短信年龄相差 ≤ 15 天 ∧ b ≤ 0 ∧ |tr_chg| < 0.1 pp 的随机另一个资格池信号，30 个种子；抽不到 → 该信号缺值并报比例）→ 每笔 ≥ P-match 均值 + 0.5 pp 且胜率 ≥ +4 pp。
    另报：b ≥ 0.5%、反向 b ≤ −0.25%。
  N3 決算日程位置：E_N3 ∧ since ≥ 10 ∧ 10 ≤ to_exp ≤ 40（交易日）。方向 = 保留组更好（fins_event_study：开示后普遍为负、开示前为正；现行只避开决算前 2 日）。
    诚实：这些事实来自同一个 X → N3 的 X 只作方向门、C 是唯一检验；保留 ≥ 40% → 只能争「方向成立」档。必要条件：P-cal（中性窗口 since ≥ 10 ∧ 40 ≤ to_exp ≤ 70，确定性；报告窗口内实际开示的比例）
    → 每笔 ≥ P-cal + 0.5 pp；「保留 vs 开示后 0〜9 日」的差在最近一次开示是短信 / 是修正两类里同号。S5 只用 PL-W；P-S 作机制读法（过 = 公司自身日程位置有信息；不过 = 市场层日历成分），两种读法都不改规则。
  N4 低応計：E_N4 ∧ accrual ≤ −0.05 ∧ CFO > 0（FY 行、12 个月口径）。方向 = 保留组更好（Sloan 1996 应计异象）。阈值 −5% 在看过进场前分布后取整写死（没看收益）。
    必要条件：反面（accrual ≥ +0.05，资格池内）每笔 < N4 每笔。S5 = PL-W ∧ PL-S ∧ P-S 三个对照的上限都要超过。
  N5 N1 ∧ 突破日量比 vr1 ≥ 2.0（阈值 = qbreak/idio_forward.K2_VR 已登记的 2.0；只登记这一个交互）。方向 = 保留组更好且比「vr1 ≥ 2.0 单独」更好。必要条件 P-vol：资格池内 vr1 ≥ 2.0 单独
    → 每笔 ≥ P-vol + 0.5 pp 且胜率 ≥ P-vol + 4 pp。读法：N1 与 N5 都过 = 需给效应；N5 过 N1 不过 = 交互只记录。
  不作候选：卖残类（方向事后化、IssType 变更 29.7% 造假增）、K-E、F1 / F5（东证改革叙事）、F3 净现金（只分段）、F4（被 b 替代）、D5 海外净买（市场层、X 已看过）。

五 对照（引擎精确重跑；30 个种子从 20260927 起；X 用 95 分位、C 用参数化上限 均值 + t(0.99, 29) × 标准差）
  PL-W 分层周抽签（S5 主对照，全部候选）：资格池内「股票 × 周」一起留或去，保留概率 = 候选在该信号的「年 × 规模带 × lturn 三分位」层的保留比例；未分层版另报。
  PL-S 年 × 规模带分层股票抽签（N2、N4）：每层随机保留整只股票，概率 = 候选当年该层保留的股票比例。
  P-S 同周换票（N1、N4、N5 作 S5；N3 只作机制读法）：每个信号周在资格池里随机抽与候选该周保留数相同的信号。
  必要条件对照：P-match（N2）、P-cal（N3）、P-vol（N5）；方向 / 分解对照只描述：N1 反向、N1 一般信用版、N2 反向、N3 开示后 0〜9 日、N4 反面。
  区间：按事件周（W-FRI）聚类的自助法 2,000 次，种子 20260927。

六 窗口、探索门、确认判定、读法（事先写死）
  --stage explore 只算 X；--stage confirm 只跑 CONFIRM_IDS、只跑一次；结果出来不改阈值、不换字段。
  探索门（X；资格池版本为准）：标准 = 每笔 ≥ B_c + 0.5 pp ∧ 胜率 ≥ B_c ∧ 每笔 > 适用抽签（PL-W；N4 还要 PL-S 与 P-S；N1 / N5 还要 P-S）的 95 分位 ∧ 笔数 ≥ 150 ∧（N5：每笔 > P-vol）。
    N2 例外（X 约 150〜200 笔）：每笔 > B_c ∧ 每笔 > P-match 均值 ∧ 笔数 ≥ 150；N3 例外（X in-sample）：每笔 > B_c ∧ 每笔 > P-cal 均值 ∧ 每笔 > PL-W 95 分位。
  确认判定（C）：S1 胜率 ≥ B_c + 8 pp；S2 每笔 ≥ B_c + 1.0 pp 且 (候选 − B_c) 周聚类 95% 区间下限 > 0；S3 笔数 ≥ 300；S4 组合不变差 = S0C2 在时点 TOPIX 500 池（U1）里
    「W2 ∧ 候选标签」替换现行 W2 进场（标签 = 交易日 × 票的掩码；标签未知的信号日当不保留、报比例），C 窗口 Calmar ≥ 现行 − 0.02 ∧ 回撤不深 2 pp ∧ 个股笔数 ≥ 现行 30%；
    S5 胜率与每笔都 > 全部适用对照的参数化 99% 上限；必要条件；X 与 C 的「候选 − B_c」同号。
  档位：全过 = 「选股成立（单窗口）」→ 提议 + 登记前向记录（用户确认）；S1 不过但 胜率 ≥ B_c + 4 pp ∧ 每笔 ≥ B_c + 0.5 pp ∧ S2 区间 ∧ S3 ∧ S5 ∧ 必要条件 = 「选股改进」只记录；
    「方向成立」= 每笔 ≥ B_c + 0.5 pp ∧ S2 区间下限 > 0 ∧ S3 ∧ S5 ∧ 必要条件（胜率不要求）→ 只写进 sim_changes（N3 到此档 → 只提议另做 blackout 改法的登记研究）；其余 = 不成立。
  零假设下各档通过概率（C 标准误：每笔 ≈ 6.04 × 1.5 ÷ √n pp，胜率 ≈ 47 × 1.5 ÷ √n pp）：「方向成立」对 N2（n≈345，se 0.49）≈ 15%、N1（n≈680，se 0.35）≈ 8%、N3（se 0.23）≈ 2%；
    「改进」≤ 5%；全过 ≤ 1%；5 个候选 × 3 档的家族偶然率约 30% → C 的置信只靠参数化 99% 上限 + X / C 同号 + 必要条件。
  读法：N1 / N4 / N5：X 过 C 过 = 跨 2022 前后成立；X 过 C 不过 = 时代依赖 / 已失效。N2 / N3：X 只是方向门 → C 不过 = 不成立。S4 只差个股笔数 → 「单独交易层成立、组合层不可用」。

七 前视与数据质量（事先声明）：信用残高 pub = 下一周第 2 営業日、avail = 其后第一个交易日（节假日周自动顺延）；决算短信 DiscDate < d；上市一览严格早于 d；
  缓存是「今天看到的」数值（订正覆盖）；B 池含决算前 2 日的信号（执行器不买）→ 另报套 blackout 的 B；10,000 株下限在 2018-10 単元统一前后意义不同 → 资格池 X / C 不同、读法加注；
  全市场 W2 池 91〜92% 是非 TOPIX / Small 小型股 → 滑点偏乐观；决算季同日集中 → 周聚类区间；输出只有统计（var/out/demand_study.md / .json）。

八 诚实的预期：最可能 N1 / N4 / N5 里 0〜1 个过 X 门（约 40%）；N2 / N3 因方向门宽松更容易进 C；C 里 0 个过 S1（约 90%）；到「方向成立」档约 25%；全过 ≤ 5%。
  不论结果，把「信用残高变化 / 自社株 / 决算日程 / 现金流应计」四类数据在干净的 C 上一次性关掉。非投资建议。
用法：python scripts/demand_study.py --stage explore|confirm [--seeds 30] [--procs 4] [--no-portfolio]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402
import demand_features as DF                                                  # noqa: E402
import fins_event_study as FS                                                 # noqa: E402

WIN_X = ("2017-01-04", "2021-12-30")
WIN_C = ("2022-01-04", "2026-09-25")
END_CUT, SEEDS, SEED0, Q_X, Q_C = 61, 30, 20260927, 95.0, 99.0
GATE_MEAN_PP, MIN_N_X, MIN_N_C = 0.5, 150, 300
WIN_UP_PP, MEAN_UP_PP, IMPROVE_WIN_PP, IMPROVE_MEAN_PP, DIR_MEAN_PP = 8.0, 1.0, 4.0, 0.5, 0.5
CALMAR_TOL, DD_TOL_PP, MIN_N_FRAC_PORT = 0.02, 2.0, 0.30
MATCH_WEEKS, MATCH_AGE_DAYS, MATCH_B_MAX, MATCH_TR_MAX = 1, 15, 0.0, 0.1
CAL_LO, CAL_HI, POST_HI, ACC_OPP = 40, 70, 9, 0.05
CANDS = {"N1": "信用買い残 4 周 ≤ −10%（资格池：可用 ≤ 15 日、相隔 26〜36 天、L_4 ≥ 1 万株、无拆股、IssType 1/2）", "N2": "自社株 b ∈ [0.25%, 20%]（最近 FS 行 ≤ 140 天）",
         "N3": "決算日程：since ≥ 10 ∧ 10 ≤ to_exp ≤ 40", "N4": "低应计 (NP − CFO) ÷ TA ≤ −0.05 ∧ CFO > 0（FY 行、非金融）", "N5": "N1 ∧ vr1 ≥ 2.0"}
CONTROLS_S5 = {"N1": ("PLW", "PS"), "N2": ("PLW", "PLS"), "N3": ("PLW",), "N4": ("PLW", "PLS", "PS"), "N5": ("PLW", "PS")}
CONFIRM_IDS: tuple[str, ...] = ()                   # 探索门通过的候选 id，探索后填、再提交；确认阶段只跑这些
OUT_MD, OUT_JSON = "demand_study.md", "demand_study.json"


# ───────────────────────── 数据 ─────────────────────────
def load_features() -> pd.DataFrame:
    fp = DF.out_dir() / DF.OUT_PKL
    if not fp.exists():
        raise SystemExit(f"缺特征表 {fp}：先运行 scripts/demand_features.py --rebuild")
    F = pd.read_pickle(fp).reset_index(drop=True)
    F["sig_date"] = pd.to_datetime(F["sig_date"])
    return F


def entries(F: pd.DataFrame, mask: np.ndarray) -> dict[str, list]:
    x = F[np.asarray(mask, bool)]
    return {t: sorted(set(g["sig_date"])) for t, g in x.groupby("ticker")}


ATTACH = ["band", "lturn_ter", "r20_q", "u1", "lot_yen", "va20", "fin", "mkt", "iss_type", "short_flag", "frgn4", "pbr", "roe_eqar", "net_cash", "disc7", "last_rev", "since",
          "dL_pct", "dL_std_pct", "dL_neg_pct", "b", "accrual", "vr1", "year", "week", "stratum"]


def trades(F: pd.DataFrame, mask: np.ndarray, p, procs: int) -> pd.DataFrame:
    T = FS.run_trades(entries(F, mask), p, procs)
    if not len(T):
        return T
    key = F.drop_duplicates(subset=["ticker", "sig_date"]).set_index(["ticker", "sig_date"])[ATTACH]
    J = key.reindex(pd.MultiIndex.from_arrays([T["ticker"], T["sig_date"]]))
    for c in ATTACH:
        T["f_" + c] = J[c].to_numpy()
    return T


def win_range(F: pd.DataFrame, mask: np.ndarray, win: tuple[str, str]) -> tuple[str, str] | None:
    """候选在窗口内第一笔到最后一笔信号日（基准 / 对照只取这一段）。"""
    x = F[np.asarray(mask, bool) & FS.in_window(F["sig_date"], win)]
    if not len(x):
        return None
    return (str(x["sig_date"].min().date()), str(x["sig_date"].max().date()))


# ───────────────────────── 对照（掩码层面；逐笔用引擎重跑） ─────────────────────────
def plw_mask(F: pd.DataFrame, E: np.ndarray, K: np.ndarray, seed: int, strat: str | None = "stratum") -> np.ndarray:
    """分层周抽签：资格池内「股票 × 周」一起留或去，概率 = 候选在该层的保留比例（strat = None → 全池同一比例）。"""
    rng = np.random.default_rng(seed)
    E, K = np.asarray(E, bool), np.asarray(K, bool)
    x = F[E]
    if strat:
        rate = (pd.Series(K[E], index=x.index).groupby(x[strat]).mean())
        p_row = x[strat].map(rate).to_numpy(float)
    else:
        p_row = np.full(len(x), K[E].mean())
    grp = pd.factorize(x["ticker"].astype(str) + "|" + x["week"].astype(str))[0]
    u = rng.random(grp.max() + 1 if len(grp) else 0)
    keep = u[grp] < p_row                                                     # 同一组用同一个 u、组内第一行的层概率
    out = np.zeros(len(F), bool)
    out[np.where(E)[0]] = keep
    return out


def pls_mask(F: pd.DataFrame, E: np.ndarray, K: np.ndarray, seed: int) -> np.ndarray:
    """年 × 规模带分层股票抽签：每层随机保留整只股票，概率 = 候选当年该层保留的股票比例。"""
    rng = np.random.default_rng(seed)
    E, K = np.asarray(E, bool), np.asarray(K, bool)
    x = F[E].copy()
    x["k"] = K[E]
    x["layer"] = x["year"].astype(str) + "|" + x["band"].astype(str)
    out = np.zeros(len(F), bool)
    for layer, g in x.groupby("layer"):
        tick = g.groupby("ticker")["k"].any()
        frac = float(tick.mean()) if len(tick) else 0.0
        keep_t = set(tick.index[rng.random(len(tick)) < frac])
        out[g.index[g["ticker"].isin(keep_t)]] = True
    return out


def ps_mask(F: pd.DataFrame, E: np.ndarray, K: np.ndarray, seed: int) -> np.ndarray:
    """同周换票：每个信号周在资格池里随机抽与候选该周保留数相同的信号。"""
    rng = np.random.default_rng(seed)
    E, K = np.asarray(E, bool), np.asarray(K, bool)
    out = np.zeros(len(F), bool)
    x = F[E]
    kw = pd.Series(K[E], index=x.index).groupby(x["week"]).sum()
    for w, g in x.groupby("week"):
        n = int(kw.get(w, 0))
        if n:
            out[rng.choice(g.index.to_numpy(), size=min(n, len(g)), replace=False)] = True
    return out


def match_mask(F: pd.DataFrame, E: np.ndarray, K: np.ndarray, seed: int) -> tuple[np.ndarray, float]:
    """N2 的 P-match：同周 ±1 周 ∧ 同规模带 ∧ 短信年龄相差 ≤ 15 天 ∧ b ≤ 0 ∧ |tr_chg| < 0.1 pp 的随机另一个资格池信号；抽不到 → 缺值。→ (掩码, 抽不到的比例)。"""
    rng = np.random.default_rng(seed)
    E, K = np.asarray(E, bool), np.asarray(K, bool)
    pool = F[E & ~K & (F["b"] <= MATCH_B_MAX) & (F["tr_chg"].abs() < MATCH_TR_MAX)]
    pw = pool["sig_date"].dt.to_period("W-FRI").astype(int).to_numpy()
    out = np.zeros(len(F), bool)
    miss = 0
    for i in np.where(K)[0]:
        w = int(F.at[i, "sig_date"].to_period("W-FRI").ordinal)
        m = (np.abs(pw - w) <= MATCH_WEEKS) & (pool["band"].to_numpy() == F.at[i, "band"]) & (np.abs(pool["fs_age"].to_numpy(float) - float(F.at[i, "fs_age"])) <= MATCH_AGE_DAYS)
        idx = pool.index.to_numpy()[m]
        idx = idx[idx != i]
        if len(idx):
            out[int(rng.choice(idx))] = True
        else:
            miss += 1
    return out, round(miss / max(K.sum(), 1) * 100, 1)


def stats_win(T: pd.DataFrame, win: tuple[str, str] | None) -> dict:
    return FS.stats(T, win) if win else FS.stats(pd.DataFrame(columns=T.columns))


def q_ctrl(runs: list[dict], param: bool) -> dict:
    return FS.quantiles(runs, Q_C if param else Q_X, parametric=param)


def _c(x) -> float:
    return float("nan") if x is None else float(x)


# ───────────────────────── 判定 ─────────────────────────
def gate_x(cid: str, c: dict, base: dict, ctrl_q: dict[str, dict], need: dict) -> tuple[bool, list[str]]:
    """探索门（X，资格池版本）。ctrl_q = {"PLW": 95 分位, "PLS": …, "PS": …}；need = {"pmatch": mean, "pcal": mean, "pvol": mean}。"""
    m, w, n = _c(c.get("mean")), _c(c.get("win")), _c(c.get("n"))
    fails = []
    if n < MIN_N_X:
        fails.append(f"笔数 {int(n) if np.isfinite(n) else 0} < {MIN_N_X}")
    if cid == "N2":
        if not m > _c(base.get("mean")):
            fails.append("每笔 ≤ B_c")
        if not m > _c(need.get("pmatch")):
            fails.append("每笔 ≤ P-match 均值")
        return not fails, fails
    if cid == "N3":
        if not m > _c(base.get("mean")):
            fails.append("每笔 ≤ B_c")
        if not m > _c(need.get("pcal")):
            fails.append("每笔 ≤ P-cal 均值")
        if not m > _c(ctrl_q.get("PLW", {}).get("mean")):
            fails.append("每笔 ≤ PL-W 95 分位")
        return not fails, fails
    if not m >= _c(base.get("mean")) + GATE_MEAN_PP:
        fails.append(f"每笔 {m:+.2f}% < B_c {_c(base.get('mean')):+.2f}% + {GATE_MEAN_PP}")
    if not w >= _c(base.get("win")):
        fails.append("胜率 < B_c")
    for k in CONTROLS_S5[cid]:
        if not m > _c(ctrl_q.get(k, {}).get("mean")):
            fails.append(f"每笔 ≤ {k} 95 分位")
    if cid == "N5" and not m > _c(need.get("pvol")):
        fails.append("每笔 ≤ P-vol")
    return not fails, fails


def necessary(cid: str, c: dict, need: dict) -> list[str]:
    """C 的必要条件（未满足的列表）。need：N1 {"std_keep": stats, "std_drop": stats}；N2 {"pmatch": stats}；N3 {"pcal": stats, "post_fs": diff, "post_rev": diff}；
    N4 {"opp": stats}；N5 {"pvol": stats}。"""
    out = []
    m, w = _c(c.get("mean")), _c(c.get("win"))
    if cid == "N1":
        d = _c(need.get("std_keep", {}).get("mean")) - _c(need.get("std_drop", {}).get("mean"))
        if not d > 0:
            out.append(f"制度信用单独的『保留 − 剔除』{d:+.2f} pp ≤ 0")
    elif cid == "N2":
        pm = need.get("pmatch", {})
        if not (m >= _c(pm.get("mean")) + 0.5 and w >= _c(pm.get("win")) + 4.0):
            out.append(f"未超过 P-match（每笔 {_c(pm.get('mean')):+.2f}% + 0.5、胜率 {_c(pm.get('win')):.1f}% + 4）")
    elif cid == "N3":
        pc = need.get("pcal", {})
        if not m >= _c(pc.get("mean")) + 0.5:
            out.append(f"每笔未超过 P-cal {_c(pc.get('mean')):+.2f}% + 0.5")
        a, b = need.get("post_fs"), need.get("post_rev")
        if a is not None and b is not None and not (np.sign(a) == np.sign(b) and a != 0):
            out.append(f"「保留 vs 开示后 0〜9 日」在短信 / 修正两类不同号（{a:+.2f} / {b:+.2f}）")
    elif cid == "N4":
        if not _c(need.get("opp", {}).get("mean")) < m:
            out.append(f"反面（应计 ≥ +0.05）每笔 {_c(need.get('opp', {}).get('mean')):+.2f}% 不 < 候选")
    elif cid == "N5":
        pv = need.get("pvol", {})
        if not (m >= _c(pv.get("mean")) + 0.5 and w >= _c(pv.get("win")) + 4.0):
            out.append(f"未超过 P-vol（每笔 {_c(pv.get('mean')):+.2f}% + 0.5、胜率 {_c(pv.get('win')):.1f}% + 4）")
    return out


def s_fails(cid: str, c: dict, base: dict, ctrl_q: dict[str, dict], diff_lo: float | None, port: dict | None, port_base: dict | None, need: dict,
            sign_x: float | None) -> list[str]:
    m, w, n = _c(c.get("mean")), _c(c.get("win")), _c(c.get("n"))
    out = []
    if not w >= _c(base.get("win")) + WIN_UP_PP:
        out.append(f"S1 胜率 {w:.1f}% < B_c {_c(base.get('win')):.1f}% + {WIN_UP_PP:.0f} pp")
    if not m >= _c(base.get("mean")) + MEAN_UP_PP:
        out.append(f"S2 每笔 {m:+.2f}% < B_c {_c(base.get('mean')):+.2f}% + {MEAN_UP_PP:.1f} pp")
    if diff_lo is not None and not diff_lo > 0:
        out.append(f"S2 (候选 − B_c) 周聚类区间下限 {diff_lo:+.2f} pp ≤ 0")
    if not n >= MIN_N_C:
        out.append(f"S3 笔数 {int(n) if np.isfinite(n) else 0} < {MIN_N_C}")
    if port is not None and port_base is not None:
        if not _c(port.get("calmar")) >= _c(port_base.get("calmar")) - CALMAR_TOL:
            out.append(f"S4 组合 Calmar {_c(port.get('calmar')):.3f} < 现行 {_c(port_base.get('calmar')):.3f} − {CALMAR_TOL}")
        if not _c(port.get("dd")) >= _c(port_base.get("dd")) - DD_TOL_PP:
            out.append(f"S4 组合回撤 {_c(port.get('dd')):.2f}% 比现行 {_c(port_base.get('dd')):.2f}% 深 {DD_TOL_PP:.0f} pp 以上")
        if not _c(port.get("n")) >= MIN_N_FRAC_PORT * _c(port_base.get("n")):
            out.append(f"S4 组合个股笔数 {port.get('n')} < 现行 {port_base.get('n')} 的 {MIN_N_FRAC_PORT:.0%}")
    for k in CONTROLS_S5[cid]:
        q = ctrl_q.get(k, {})
        if not w > _c(q.get("win")):
            out.append(f"S5 胜率 {w:.1f}% ≤ {k} 上限 {_c(q.get('win')):.1f}%")
        if not m > _c(q.get("mean")):
            out.append(f"S5 每笔 {m:+.2f}% ≤ {k} 上限 {_c(q.get('mean')):+.2f}%")
    out += ["必要条件：" + x for x in necessary(cid, c, need)]
    if sign_x is not None and not np.sign(m - _c(base.get("mean"))) == np.sign(sign_x):
        out.append("X 与 C 的「候选 − B_c」不同号")
    return out


def tier(cid: str, c: dict, base: dict, fails: list[str], diff_lo: float | None) -> str:
    """成立 / 改进 / 方向成立 / 不成立（读法写死）。"""
    if not fails:
        return "选股成立（单窗口）→ 提议 + 登记前向记录（用户确认）"
    m, w = _c(c.get("mean")), _c(c.get("win"))
    others = [f for f in fails if not f.startswith(("S1", "S2 每笔", "S4"))]
    if w >= _c(base.get("win")) + IMPROVE_WIN_PP and m >= _c(base.get("mean")) + IMPROVE_MEAN_PP and not others:
        return "选股改进（只记录）"
    if m >= _c(base.get("mean")) + DIR_MEAN_PP and diff_lo is not None and diff_lo > 0 and not others:
        return "方向成立（只记录）" + ("；N3 → 只提议另做 blackout 改法的登记研究" if cid == "N3" else "")
    return "不成立"


# ───────────────────────── 组合（S4，确认阶段） ─────────────────────────
def portfolio(F: pd.DataFrame, cids: list[str], p, jmem: str = "U1") -> dict:
    """S0C2 现行（W2）vs 「W2 ∧ 候选标签」（标签 = 交易日 × 票 掩码；未知 → 不保留）；每个窗口 {cagr, dd, calmar, n, mean, win}。"""
    import leap_confirm as LC
    ctx = LC.context("J", jmem=jmem)
    fr0 = LC.frames(ctx, p)
    run_fn = LC.runner(ctx, fr0)
    w2 = LC.w2_keep(ctx, fr0)
    base_fr = LC.with_mask(fr0, w2)
    out = {"base": LC.run(ctx, run_fn, base_fr, p), "jmem": jmem}
    for cid in cids:
        K = DF.keep(F, cid)
        lab = {t: set(g["sig_date"]) for t, g in F[K].groupby("ticker")}
        known = {t: set(g["sig_date"]) for t, g in F.groupby("ticker")}
        mask = {t: (df.index.isin(list(lab.get(t, ()))) if t in lab else np.zeros(len(df), bool)) for t, df in base_fr.items()}
        n_ent = sum(int(df["entry"].to_numpy(bool).sum()) for df in base_fr.values())
        n_known = sum(int((df["entry"].to_numpy(bool) & df.index.isin(list(known.get(t, ())))).sum()) for t, df in base_fr.items())
        res = LC.run(ctx, run_fn, LC.with_mask(base_fr, mask), p)
        res["label_known_pct"] = round(n_known / max(n_ent, 1) * 100, 1)
        out[cid] = res
    return out


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/demand_study.py", "scripts/demand_features.py", "scripts/jq_extra_data.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def bulk_sha(limit: int = 500) -> dict:
    from qbreak import jq_data as JD
    out = {}
    for sub in ("fins/summary", "markets/margin-interest"):
        d = JD.bulk_dir() / sub
        for fp in sorted(d.glob("**/*.csv.gz"))[:limit]:
            out[f"{sub}/{fp.relative_to(d)}"] = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
    return out


# ───────────────────────── 主流程 ─────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["explore", "confirm"], required=True)
    ap.add_argument("--seeds", type=int, default=SEEDS)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--no-portfolio", action="store_true")
    ap.add_argument("--out-dir", default=None, help="输出目录（缺省 var/out；试跑时指向仓库外）")
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    t_start = time.time()
    import allstock_data as AD
    from qbreak.trader import load_params
    stage = a.stage
    if stage == "confirm" and not CONFIRM_IDS:
        raise SystemExit("确认阶段要先把探索门通过的候选写进 CONFIRM_IDS 并提交")
    ids = list(CANDS) if stage == "explore" else [c for c in CANDS if c in CONFIRM_IDS]
    say = lambda s_: print(s_, flush=True)                                   # noqa: E731
    A = AD.load()
    days = pd.DatetimeIndex(A["days"])
    c_end = min(pd.Timestamp(WIN_C[1]), days[-1 - END_CUT])
    wins = {"X": WIN_X} if stage == "explore" else {"X": WIN_X, "C": (WIN_C[0], str(c_end.date()))}
    F = load_features()
    if stage == "explore":
        F = F[FS.in_window(F["sig_date"], WIN_X)].reset_index(drop=True)      # 探索阶段只读 X
    else:
        F = F[FS.in_window(F["sig_date"], (WIN_X[0], wins["C"][1]))].reset_index(drop=True)
    P = F["P"].to_numpy(bool)
    say(f"特征表 {len(F)} 行（P {int(P.sum())}）；{stage}；候选 {ids}；窗口 {wins}；{time.time() - t_start:.0f}s")
    p = load_params(market="JP")
    FS.build_frames(A, p)
    say(f"指标表 {len(FS._FR)} 只；{time.time() - t_start:.0f}s")
    T_full = trades(F, P, p, a.procs)
    say(f"全池 B：" + "、".join(f"{w} {FS.stats(T_full, win)}" for w, win in wins.items()) + f"；{time.time() - t_start:.0f}s")
    res: dict = {"stage": stage, "git": git_info(), "windows": wins, "seeds": a.seeds, "confirm_ids": list(CONFIRM_IDS), "n_features": int(len(F)), "n_pool": int(P.sum()),
                 "base_full": {w: FS.stats(T_full, win) for w, win in wins.items()}, "cands": {}, "counts": DF.counts(F, wins), "bulk_sha": bulk_sha()}
    T_blk = T_full[T_full["f_since"].isna() | (T_full["f_since"] >= 0)]        # 占位：blackout 版另报见下
    entered = []
    port_cands: dict[str, pd.DataFrame] = {}
    for cid in ids:
        E = DF.eligible(F, cid)
        K = DF.keep(F, cid)
        T_c = trades(F, K, p, a.procs)
        T_b = trades(F, E, p, a.procs)
        T_x = trades(F, E & ~K, p, a.procs)
        rec = {"desc": CANDS[cid], "n_keep": int(K.sum()), "n_elig": int(E.sum()), "windows": {}}
        say(f"{cid}：保留 {int(K.sum())} / 资格 {int(E.sum())}；逐笔 {len(T_c)}；{time.time() - t_start:.0f}s")
        need_mask = {}
        if cid == "N1":
            Ks = E & (F["dL_std_pct"].to_numpy(float) <= DF.DL_MIN)
            Kn = E & (F["dL_neg_pct"].to_numpy(float) <= DF.DL_MIN)
            need_mask = {"std_keep": Ks, "std_drop": E & ~Ks, "neg_keep": Kn, "neg_drop": E & ~Kn, "reverse": E & (F["dL_pct"].to_numpy(float) >= 10.0)}
        elif cid == "N2":
            need_mask = {"reverse": E & (F["b"].to_numpy(float) <= -0.25), "b05": E & (F["b"].to_numpy(float) >= 0.5) & (F["b"].to_numpy(float) <= DF.B_MAX)}
        elif cid == "N3":
            need_mask = {"pcal": E & (F["since"].to_numpy(float) >= DF.SINCE_MIN) & (F["to_exp"].to_numpy(float) >= CAL_LO) & (F["to_exp"].to_numpy(float) <= CAL_HI),
                         "post": E & (F["since"].to_numpy(float) <= POST_HI)}
        elif cid == "N4":
            need_mask = {"opp": E & (F["accrual"].to_numpy(float) >= ACC_OPP)}
        elif cid == "N5":
            need_mask = {"pvol": E & (F["vr1"].to_numpy(float) >= DF.VR_MIN), "rev_vol": E & (F["vr1"].to_numpy(float) >= DF.VR_MIN) & (F["dL_pct"].to_numpy(float) >= 10.0)}
        T_need = {k: trades(F, m, p, a.procs) for k, m in need_mask.items()}
        # 抽签对照（每个种子引擎重跑）
        ctrl_runs: dict[str, dict[str, list]] = {k: {w: [] for w in wins} for k in ("PLW", "PLW0", "PLS", "PS", "PM")}
        pm_miss = []
        for s in range(a.seeds):
            seed = SEED0 + s
            masks = {"PLW": plw_mask(F, E, K, seed), "PLW0": plw_mask(F, E, K, seed + 500, None)}
            if "PLS" in CONTROLS_S5[cid]:
                masks["PLS"] = pls_mask(F, E, K, seed + 1000)
            if "PS" in CONTROLS_S5[cid] or cid == "N3":
                masks["PS"] = ps_mask(F, E, K, seed + 2000)
            if cid == "N2":
                masks["PM"], miss = match_mask(F, E, K, seed + 3000)
                pm_miss.append(miss)
            for k, m in masks.items():
                Tm = trades(F, m, p, a.procs)
                for w, win in wins.items():
                    rng_ = win_range(F, K, win)
                    ctrl_runs[k][w].append(stats_win(Tm, rng_))
            if s in (0, 9, 19, 29):
                say(f"  {cid} 对照种子 {s + 1}/{a.seeds}；{time.time() - t_start:.0f}s")
        for w, win in wins.items():
            rng_ = win_range(F, K, win)
            c = stats_win(T_c, rng_)
            base = stats_win(T_b, rng_)
            excl = stats_win(T_x, rng_)
            full = stats_win(T_full, rng_)
            param = w == "C"
            ctrl_q = {k: q_ctrl(v[w], param) for k, v in ctrl_runs.items() if v[w]}
            need = {}
            for k, Tn in T_need.items():
                need[k] = stats_win(Tn, rng_)
            if cid == "N2" and ctrl_runs["PM"][w]:
                need["pmatch"] = {"mean": float(np.mean([r["mean"] for r in ctrl_runs["PM"][w] if r.get("mean") is not None] or [np.nan])),
                                  "win": float(np.mean([r["win"] for r in ctrl_runs["PM"][w] if r.get("win") is not None] or [np.nan])), "miss_pct": float(np.mean(pm_miss))}
            if cid == "N3":
                for lab, val in (("post_fs", 0.0), ("post_rev", 1.0)):
                    ck = T_c[T_c["f_last_rev"] == val]; pk = T_need["post"][T_need["post"]["f_last_rev"] == val]
                    sc, sp = stats_win(ck, rng_), stats_win(pk, rng_)
                    need[lab] = None if sc.get("mean") is None or sp.get("mean") is None else round(sc["mean"] - sp["mean"], 3)
                need["pcal_actual_disc_pct"] = None
            if cid == "N4":
                need["opp"] = need.get("opp", {})
            boot = FS.cluster_boot(T_c, rng_) if rng_ else {}
            diff_lo = FS.diff_lower(T_c, T_b, rng_) if rng_ else None
            block = {"cand": c, "base_elig": base, "excluded": excl, "base_full": full, "keep_minus_excl": None if c.get("mean") is None or excl.get("mean") is None else round(c["mean"] - excl["mean"], 3),
                     "boot": boot, "diff_lower": diff_lo, "controls": ctrl_q, "need": need, "eff_range": rng_,
                     "segments": {k: FS.stats(T_c[m.to_numpy(bool)], rng_) for k, m in (("band0", T_c["f_band"] == 0), ("band1", T_c["f_band"] == 1), ("band2", T_c["f_band"] == 2),
                                                                                       ("lturn0", T_c["f_lturn_ter"] == 0), ("lturn2", T_c["f_lturn_ter"] == 2), ("u1", T_c["f_u1"] == 1),
                                                                                       ("lot25", T_c["f_lot_yen"] <= 250000), ("va5000", T_c["f_va20"] >= 5e7), ("short", T_c["f_short_flag"] == True),   # noqa: E712
                                                                                       ("frgn_pos", T_c["f_frgn4"] > 0), ("pbr1", T_c["f_pbr"] < 1), ("roe_eqar", T_c["f_roe_eqar"] == True),           # noqa: E712
                                                                                       ("net_cash", T_c["f_net_cash"] == True), ("disc7", T_c["f_disc7"] == 1))} if len(T_c) else {},
                     "by_year": {str(y): FS.stats(g) for y, g in T_c.groupby("f_year")} if len(T_c) else {},
                     "excl_by_band": {str(b_): FS.stats(T_x[(T_x["f_band"] == b_).to_numpy(bool)], rng_) for b_ in (0, 1, 2)} if len(T_x) else {},
                     "r20q_keep_vs_excl": {str(q): {"keep": FS.stats(T_c[(T_c["f_r20_q"] == q).to_numpy(bool)], rng_), "excl": FS.stats(T_x[(T_x["f_r20_q"] == q).to_numpy(bool)], rng_)}
                                           for q in range(5)} if cid in ("N1", "N5") and len(T_c) else {}}
            if w == "X":
                ok, fails = gate_x(cid, c, base, ctrl_q, {"pmatch": need.get("pmatch", {}).get("mean"), "pcal": need.get("pcal", {}).get("mean"), "pvol": need.get("pvol", {}).get("mean")})
                block["gate_x"] = ok
                block["gate_fails"] = fails
                block["sign_x"] = None if c.get("mean") is None or base.get("mean") is None else float(np.sign(c["mean"] - base["mean"]))
                if ok:
                    entered.append(cid)
            rec["windows"][w] = block
        res["cands"][cid] = rec
        if stage == "confirm":
            port_cands[cid] = T_c
    if stage == "confirm":
        port = None if a.no_portfolio else portfolio(F, ids, p, "U1")
        port0 = None if a.no_portfolio else portfolio(F, ids, p, "U0")
        res["portfolio"] = {"U1": port, "U0": port0}
        for cid in ids:
            bx = res["cands"][cid]["windows"]["X"]
            bc = res["cands"][cid]["windows"]["C"]
            jw = None
            if port:
                jw = next((k for k in port["base"] if not k.startswith("_") and str(port["base"][k].get("cagr")) != "None" and k.endswith("2")), None)
            pc = port[cid][jw] if (port and jw) else None
            pb = port["base"][jw] if (port and jw) else None
            fails = s_fails(cid, bc["cand"], bc["base_elig"], bc["controls"], bc["diff_lower"], pc, pb, bc["need"], bx.get("sign_x"))
            bc["fails"] = fails
            bc["tier"] = tier(cid, bc["cand"], bc["base_elig"], fails, bc["diff_lower"])
    res["entered_X"] = entered
    res["elapsed_s"] = round(time.time() - t_start)
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report(res)
    (out_dir / OUT_MD).write_text(md + "\n", encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md)
    return 0


def _f(s: dict) -> str:
    if not s or not s.get("n"):
        return "n=0"
    return f"n={s['n']} 胜率 {s['win']:.1f}% 每笔 {s['mean']:+.2f}%"


def report(res: dict) -> str:
    L = [f"# 需給・回購・決算日程・現金利益 × 全市場 W2 突破 —— {res['stage']}（git {res['git']['rev']}{'（脏）' if res['git'].get('dirty') else ''}，种子 {res['seeds']}）", "",
         f"特征表 {res['n_features']} 行、P {res['n_pool']}；窗口 {res['windows']}；全池 B：" + "；".join(f"{w} {_f(s)}" for w, s in res["base_full"].items()), ""]
    for cid, rec in res["cands"].items():
        L.append(f"## {cid} {rec['desc']}（保留 {rec['n_keep']} / 资格 {rec['n_elig']}）")
        for w, b in rec["windows"].items():
            L.append(f"- {w}（{b['eff_range']}）：候选 {_f(b['cand'])}；B_c {_f(b['base_elig'])}；剔除 {_f(b['excluded'])}；保留 − 剔除 {b['keep_minus_excl']} pp；全池 B {_f(b['base_full'])}；"
                     f"周聚类区间 {b['boot']}；(候选 − B_c) 下限 {b['diff_lower']}")
            L.append("  对照上限：" + "；".join(f"{k} 胜率 {v.get('win')} 每笔 {v.get('mean')}（{v.get('kind')} {v.get('seeds')} 种子）" for k, v in b["controls"].items()))
            nd = {k: (v if not isinstance(v, dict) else _f(v) if "n" in v else v) for k, v in b["need"].items()}
            L.append(f"  必要条件 / 分解：{nd}")
            if w == "X":
                L.append(f"  探索门：{'通过' if b.get('gate_x') else '不过'}{'：' + '；'.join(b.get('gate_fails') or []) if not b.get('gate_x') else ''}")
            if "fails" in b:
                L.append(f"  确认判定：{'全过' if not b['fails'] else '；'.join(b['fails'])} → {b['tier']}")
            L.append("  分段：" + "；".join(f"{k} {_f(v)}" for k, v in b["segments"].items()))
            L.append("  按年：" + "；".join(f"{k} {_f(v)}" for k, v in b["by_year"].items()))
            if b.get("r20q_keep_vs_excl"):
                L.append("  同 r20 五分位内 保留 vs 剔除：" + "；".join(f"q{k} {_f(v['keep'])} vs {_f(v['excl'])}" for k, v in b["r20q_keep_vs_excl"].items()))
        L.append("")
    L.append(f"探索门通过（可写进 CONFIRM_IDS）：{res.get('entered_X') or '无'}")
    if res.get("portfolio"):
        L.append("")
        L.append("## S4 组合（U1 时点 TOPIX 500 / U0 今天的日経225；W2 ∧ 候选标签 替换现行 W2）")
        for jm, pt in res["portfolio"].items():
            if not pt:
                continue
            L.append(f"- {jm} 现行：{pt['base']}")
            for cid in res["cands"]:
                if cid in pt:
                    L.append(f"- {jm} {cid}：{pt[cid]}")
    L.append("")
    L.append(f"进场前分布（登记前核对）：{json.dumps(res['counts'], ensure_ascii=False)[:3000]}")
    L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。非投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
