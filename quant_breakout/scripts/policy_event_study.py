"""policy_event_study.py — 政策事件反应库 G1（登记版：分类表、反应口径、候选、对照、判定全部写在这里；提交后不改规则；只展示 + 前向记录，不改交易）。

来由：用户 2026-09-27「G1 政策事件库要做」。设计 = 三份独立提案 + 两位评审 + 综合 + 两份对抗审计（云端设计面板）；本文已按两份审计的「运行前必须修」逐条修正
（反应日的主场 / 时区规则与买点 07:40 门槛、事件表按机械规则重建、verified 只由脚本取回或 Mac 核对、覆面介入只描述、业种名归一与篮子下限、
TOPIX 改用 J-Quants 指数、置换对照 ≥ 1,000 次 + Holm、J5 按子类、J6 按阶段、J7 同长度、P4 的 market_dir 事先写死、去重优先序、事件链聚类、
前向记录的迟录锚点与 PENDING 行）。规则层 qbreak/policy_events.py；数据层 scripts/policy_event_data.py；事件表 var/policy_events.csv（公开事实 + 官方 URL，入库）。

一、问题与结论上限
  问题：「出现 X 类政策 → 之后 5〜20 个交易日 Y 业种相对大盘的反应，能不能被事前写定的分类预测」。
  结论上限（写死）：无论结果如何，产出 = 日报 / 仪表盘展示 + 前向记录；模拟盘、执行器、W2、股票池、宏观阈值一律不改。
  事后知识声明：分类表、F 表与 news.py 冲击向量都写于 2026-09（作者已知 2022〜2025 的市场反应）→ X / C 分开只防本研究内部的参数挑选，不防规则本身的事后性；
  只有 P2（事前 β：截至 r 之前 104 周机械算出的名单）接近事前；因此 P1 通过只能标「历史一致（分类事后写定，非样本外）」，「登记确认」只由前向记录授予。
  事前预期（结果出来不改）：D0 / 隔夜跳空明显但吃不到；W5 / W20 价差平均 0〜+0.5 pp、命中 50〜58%，落在打乱日期对照 95 分位附近；
  最可能的结论 = 「第 0 日可见、5〜20 日不可预测或时代依赖」。主观概率：某个候选在 X 全过约 20%，X + C 都过约 8%。

二、事件表（var/policy_events.csv；列见 qbreak/policy_events.EVENT_COLS）
  纳入 = 官方日期 + 官方 URL（域名白名单）；date = 主场当地官方日期，time_local = 当地时刻（可空），date_jst / time_jst 由 qbreak.policy_events.jst_of 换算；
  excluded = 1 的行保留原文不计入；verified 只能由脚本实际取回（HTTP 200 且页面含事件日期，记 checked_hash / http_status）或用户在 Mac 核对后用 check 子命令填
  （checked_hash = manual）；verified 为空的行只描述、不计入判定（本容器打不开的 meti / kantei 条目就是这样）；更正只新增一行写 supersedes。
  机械规则：日银 = 年表全部会合（2001〜2026），「标题含 Change / Introduction / Enhancement / Expansion / Comprehensive / New Procedures / 声明首段目标
  水平变化」= BOJ_CHANGE，其余 = CTRL_BOJ_NOCHG；子类 tighten / ease 按声明首段方向；方向模糊的会合（qbreak.policy_events.EXCLUDED_BOJ 五个）excluded = 1；
  ETF 类决定同日在 BOJ_ETF 另记一行。FOMC = 年历全部会合：周期第一次加息 / 第一次降息（含紧急会合的周期起点）= FED_TURN，其余 = CTRL_FOMC_OTHER。
  財務省介入：逐日实施日（財務省 CSV）按「相邻实施日间隔 ≥ 10 个交易日 = 新回合」切分，回合第一天为事件；covert = 当日无官方确认（known_on = 月次公表日）→
  只描述、不进判定；2026-07〜08 的干预逐日未公布 → 月次公表录入并 excluded（daily_pending）。关税 / 出口管制：官方公告 / 签署 / 刊登日（生效日 pre_announced = 1 只描述）。
  対照池与事件同一张表（tier = control）。ELECTION 只收日本国政选举（美国选举没有事先的方向规则 → 不收）。

三、反应日与买点（policy_event_data.reaction_and_entry；测试固定 2025-04-02 16:00 ET → r = 04-03、2025-04-09 13:18 ET → r = 04-10、2010-09-15 10:30 → r = 09-15）
  有时刻：JST 日期 d 是交易日且时刻 < 收盘（2024-11-05 前 15:00、之后 15:30）→ r = d；时刻 < 07:40（执行器决策时刻）→ t0 = d 当天开盘、否则 t0 = 下一交易日开盘；
  时刻 ≥ 收盘或 d 非交易日 → r = 之后第一个交易日、t0 = r。无时刻：日本主场 = 当收盘后、美国主场 = JST 夜间 → r = 之后第一个交易日、t0 = r。
  类别默认时刻只给日银决定会合（12:00，time_src = class_default → t0 = r+1）；有官方时刻（年表「Announced at h:mm p.m.」、財務省会見）用官方时刻。

四、分类表（强 / 中 / 弱；名单由 qbreak/policy_events.derive_lists 机械推出，tests 断言与下面一致）
  强（进入合并判定）：BOJ_CHANGE tighten 受益 銀行業・保険業・その他金融業・食料品 / 受损 不動産業・電気・ガス業・情報・通信業・輸送用機器（ease 互换）；
    MOF_FX yen_buy 受益 食料品・小売業・電気・ガス業・空運業 / 受损 輸送用機器・電気機器・機械・精密機器（yen_sell 互换；sign：yen_buy +1 / yen_sell −1）；
    FED_TURN first_hike 受益 銀行業・保険業・輸送用機器・電気機器 / 受损 不動産業・情報・通信業・食料品・小売業（first_cut 互换）；
    TARIFF impose 受损 輸送用機器・電気機器・機械・鉄鋼（news.py 规则）/ 受益（先验）小売業・食料品・陸運業・情報・通信業（relief 互换）；
    SEMI_CTRL control 受损 電気機器・機械・精密機器（news.py 规则）/ 受益 无（relax 互换）；TAX hike 受损（先验）小売業・不動産業・建設業・輸送用機器 / 受益 无（cut_delay 互换）。
  当期不可得的业种（面板成员 < 5 只 → 该业种 NaN）按排序里的下一个替补（derive_lists available；说明标 subst）；一侧可得 < 2 → 该事件缺值。
  市场方向 market_dir（P4 用）事先写死：BOJ tighten −1 / ease +1、MOF yen_buy −1 / yen_sell +1、FED first_hike −1 / first_cut +1、TARIFF impose −1 / relief +1、
    SEMI control −1 / relax +1、TAX hike −1 / cut_delay +1、BOJ_ETF expand +1 / shrink −1；ELECTION 按席位规则（与党 = 选举前的执政联合）。
  中（只描述）：BOJ_ETF（P5 指数价差 日経225 − TOPIX，2016-11 起）、TSE_GOV、TSE_STRUCT、NISA、SEMI_SUB；弱（只报市场层）：ELECTION、PM_CHANGE。
  同日多事件：按 r 去重，优先序 主场 JP > US、BOJ_CHANGE > MOF_FX > FED_TURN > TARIFF > SEMI_CTRL > TAX > 中 > 弱 > 对照；被去掉的事件仍在类别表。

五、数据与年代（只在 var/cache/）
  A 年代 2001-01〜2016-10：yfinance 27 年池（日経225 + 扩大池 + 补充票 var/policy_extra_pool.json：陸運 / 空運 / 倉庫 / 保険 等今天的 TOPIX 成分）按今天的
  33 业种等权（quality = low：幸存者偏差、今日分类；2001〜2003 约 13% 的日子 Open == Close → 开盘口径部分是「以收代开」）；
  B 年代 2016-11〜：全市场面板按严格早于 r 的月末上市一览的时点业种等权（2016-09〜10 没有快照 → 不用）；两个年代成员 ≥ 5 只、个股单日 |收益| > 35% 当缺值。
  基准 = 日経225（^N225；缺 2010-09-15 等个别日 → 当非交易日）；副基准 = TOPIX 指数（J-Quants，2016-09-27 起；不用 yfinance 1306.T：有 −90% 错价）。
  日历 = 日経225 数据日 ∪ 全市场面板日。窗口（交易日）：D0 = [r−1 收 → r 收]；GAP = [r−1 收 → t0 开]（吃不到的部分）；D1 = t0 开 → t0 收；
  W5 = t0 开 → t0+4 收；W20 = t0 开 → t0+19 收；W60 = t0 开 → t0+59 收；PRE 与被比较窗口同长度：W5 用 [r−10 收 → r−6 收]、W20 用 [r−25 收 → r−6 收]。
  样本末尾 END_CUT = 61：r 晚于 数据末尾 − 61 个交易日的事件只报已完整的窗口、不计入判定。
  研究窗口：X = r 在 2001-01-04〜2021-12-30（探索门；内部分 A 2001〜2016-10、B1 2016-11〜2021；--stage explore 只读 X 的事件行）；
  C = 2022-01-04〜（末尾 − 61 日）只跑一次（--stage confirm，只对 CONFIRM_IDS 判定）。
  相邻反向事件（同类别、相反 sign、下一事件 r 落在窗口内）：主分析把窗口截到下一事件 r−1（trunc 标记），全窗口版本作副分析。

六、反应口径与候选（≤ 5，事先写死）
  业种超额 x = 业种窗口收益 − 日経225 同窗口收益（pp）；事件级价差 S = 受益篮子等权 − 受损篮子等权（只有一侧 → 该侧 − 其余业种等权）；命中 = S > 0。
  P1 规则通道（四 的名单）；P2 事前 β 通道（业种超额周收益（− 日経）对 5 因子周变化的 OLS β，截至 r 所在周之前 104 周、至少 60 周；Σβ × 冲击 前 4 / 后 4）；
  P3 = P1 ∩ P2（一侧为空 → 缺值）；P4 市场层（market_dir × 日経窗口收益）；P5 指数价差（BOJ_ETF：sign × (日経225 − TOPIX)，2016-11 起）。
  主检验 = 强类别合并 × W5 × {P2, P1}（两个并列主检验，Holm 5%）；次要 = P1〜P4 × {W5, W20} 其余 + P5 × {W5, W20}（≤ 8 个，Holm 5%）；
  每个检验的 p = C1 打乱日期置换 p（(1 + #{对照均值 ≥ 观测}) / (1 + N)，N = 1,000）。

七、判定（事先写死；类别层 n < 12 一律只描述）
  J1 命中率 ≥ 60% 且 > C1 置换的命中率 95 分位；J2 平均价差 W5 ≥ +0.5 pp（W20 ≥ +1.0 pp）且事件链（相邻 r ≤ 20 个交易日相连）聚类自助法 95% 区间下限 > 0；
  J3 去重后事件数 ≥ 40（X）/ ≥ 25（C）；J4 C1 打乱日期与 C2 随机业种的置换 p 经 Holm（本族）后都 ≤ 0.05；
  J5 子类：有相反子类的类别里，两个子类各自（各按各自名单）平均 S > 0（各 n ≥ 5；不够 → 该类只描述、不判）；
  J6 年代：X 阶段 A / B1 同号、C 阶段 A / B1 / B2 同号（段内 n < 15 的段不计）；J7 事前漂移：S − PRE > 0 且 PRE < S/2（同长度）；
  J8 无信息会合（C4）：BOJ_CHANGE / FED_TURN 事件的平均 S > 对照池（同一名单、按「上一次变更方向」套用）的平均 S。
  读法：X 过 J1〜J8 才把候选写进 CONFIRM_IDS、提交、再跑 C 一次；X 不过 → 不跑 C 的判定，但 C 的类别 × 业种描述表仍进展示库（--stage library），并写明
  「第二阶段个股层没有干净的确认窗口，只能前向」；X、C 都过 = 「历史一致」：P1 标「历史一致（分类事后写定，非样本外）」、P2 标「历史一致（机械 β 名单）」；
  「登记确认」只由前向记录（n ≥ 30 复现）授予。J1〜J5 过而 J6 不过 = 时代依赖。方向与年代重合（円買 ≥ 2022 vs 円売 ≤ 2011、紧缩 2006〜07 与 2022 以后、
  关税 2018〜20 与 2025〜26）→ J5 / J6 实际检验的是「β 通道在两种符号、两个年代下都成立」，按 sign × 年代分表报告。
  检出力（表重建后 X 强类别去重、covert 除外后约 70〜90 条）：80% 检出力只能分辨 W5 ≥ +0.7〜0.9 pp、W20 ≥ +1.5 pp；命中率门槛 60% 对真实 63% 的检出力约 0.7；
  C 约 30〜40 条只能分辨 W20 ≥ 2 pp；命中率是必要条件不是主证据。

八、对照
  C1 打乱日期（1,000 次；同年内随机交易日、离原日 ≥ 5 个交易日，t0 与 r 的关系保持）；C2 随机业种（1,000 次；真实日期，两侧同样个数的随机可得业种）；
  C3 全业种等权篮子（受益 − 全部可得业种等权）；C4 无信息会合（对照池 CTRL_BOJ_NOCHG / CTRL_FOMC_OTHER，套用「上一次变更方向」的名单）；
  C5 事前窗口 PRE（J7）；C6 模糊事件表（EXCLUDED_BOJ 与 covert 介入按名单单独一表，只描述）；
  C7 子集只描述：overlap = 0、crisis = 0、基准换 TOPIX（2016-11〜）、收盘进场（t0 收 → t0+h 收，A 年代开盘不可靠的稳健性）、全窗口 vs 截断。

九、展示与前向记录（qbreak/policy_forward.py、run.py 钩子、report_unified；只追加、云端单一写者）—— 见各模块头部；
  展示钩子只在 var/out/policy_event_lib.json 存在后启用，最近事件只显示 r 晚于库里 c_end 的事件；迟录（late ≥ 1）事件以录入后第一个交易日为新锚点、
  只描述；已过去的日银 / FOMC 日程没有事件行 → 前向记录写 PENDING 行（--review 计为未分类）。--review 复核：强类别 sign ≠ 0、late = 0 的到期事件 ≥ 30 条时判一次：
  W20 命中 ≥ 20 / 30 且平均价差事件链聚类 95% 下限 > 0 → 「历史规律在新数据里复现」（只升级日报标签）；命中 ≤ 45% 或 95% 上限 < 0 → 「没有复现」；其余继续，n ≥ 60 再判。

十、可执行性（描述，不是候选）：B 年代受益业种成员股（时点股票池）t0 开盘 ×1.001 买、第 20 日收盘卖、来回 0.15% + 滑点双边 0.1%、开盘 > r 收盘 ×1.03 放弃 →
  L20 每笔均值、区间、放弃比例；「可交易漂移」标签 = L20 ≥ +0.5 pp 且事件链聚类区间下限 > 0（只触发「提议另写个股层前向记录」，没有确认窗口）。

十一、局限：A 年代幸存者偏差与今日分类、开盘价部分不可靠；A / B 年代「业种」不是同一物（A 只有大盘、B 含 Growth 小盘）；17 ETF 只作交叉核对（2017〜2019
  成交量为 0 的日子过半，不用）；TARIFF / SEMI 几乎全在 2018 以后无法年代复核；日银 2001〜2009 时刻靠类别默认；連発事件（2003〜04 介入、2018〜19 与 2025 关税、
  2020-03）让独立性不成立（事件链聚类 + 截断 + 子集）；1306.T 不含分红的问题因改用指数而不再相关；执行器只下日経225。非投资建议。
用法：python scripts/policy_event_study.py --stage explore|confirm|library [--perm 1000]；复核：--review
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
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402
from qbreak import policy_events as PEV                                       # noqa: E402
import policy_event_data as PD                                                # noqa: E402

WIN_X = ("2001-01-04", "2021-12-30")
WIN_C = ("2022-01-04", "2026-09-25")
ERA_B_START = "2016-11-01"
END_CUT, N_PERM, SEED0, BOOT_N, CHAIN_GAP = 61, 1000, 20260927, 2000, 20
WINDOWS = {"D0": ("close", 0, 0), "D1": ("open", 1), "W5": ("open", 5), "W20": ("open", 20), "W60": ("open", 60)}
PRE = {"W5": (-10, -6), "W20": (-25, -6)}
J1_HIT, J2_MEAN, J3_N, J5_MIN_SUB, J6_MIN_SEG, MIN_DESC = 60.0, {"W5": 0.5, "W20": 1.0}, {"X": 40, "C": 25}, 5, 15, 12
CANDS = {"P1": "规则通道（F 表 × 冲击 × sign；分类事后写定）", "P2": "事前 β 通道（Σβ × 冲击 前 4 / 后 4；机械）", "P3": "P1 ∩ P2",
         "P4": "市场层（market_dir × 日経）", "P5": "指数价差（BOJ_ETF：sign × (日経225 − TOPIX)）"}
MAIN = [("P2", "W5"), ("P1", "W5")]
SECONDARY = [("P1", "W20"), ("P2", "W20"), ("P3", "W5"), ("P3", "W20"), ("P4", "W5"), ("P4", "W20"), ("P5", "W5"), ("P5", "W20")]
CONFIRM_IDS: tuple[str, ...] = ()                   # 探索窗口 J1〜J8 全过的候选（"P1@W5" 形式），探索后填、再提交
OUT_MD, OUT_JSON, LIB_JSON = "policy_event_study.md", "policy_event_study.json", "policy_event_lib.json"
COST_PCT = 0.15 + 0.2                                # L20：来回手续费 0.15% + 滑点双边 0.1%
LABEL = {"P1": "历史一致（分类与 F 表事后写定，非样本外）", "P2": "历史一致（机械 β 名单）", "P3": "历史一致（P1 ∩ P2）", "P4": "市场层历史一致", "P5": "指数价差历史一致"}


# ───────────────────────── 数据 ─────────────────────────
def load_days() -> tuple[pd.DatetimeIndex, pd.DataFrame]:
    """日历 = 日経225 数据日 ∪ 全市场面板日（1999 起）；返回 (days, N225 frame)。"""
    from bullbear_study import SYM, load
    n = load(*SYM["JP"])
    n = n[n.index >= "1999-01-01"]
    days = pd.DatetimeIndex(n.index)
    try:
        import allstock_data as AD
        days = days.union(pd.DatetimeIndex(AD.load()["days"]))
    except Exception:                                                        # noqa: BLE001
        pass
    return days.sort_values(), n


def bench_daily(n225: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    PD.check_series(n225["Close"].astype(float), "N225")
    cc = pd.DataFrame({"N225": n225["Close"].pct_change() * 100})
    oc = pd.DataFrame({"N225": (n225["Close"] / n225["Open"] - 1) * 100})
    return cc, oc


def topix_frames() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    tp = PD.topix_daily()
    if tp is None:
        return None
    return pd.DataFrame({"TOPIX": tp["Close"].pct_change() * 100}), pd.DataFrame({"TOPIX": (tp["Close"] / tp["Open"] - 1) * 100})


def sector_daily(days: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """A 年代（长历史池 + 补充票）+ B 年代（全市场时点分类）拼接的 33 业种等权 (cc, oc)；列名归一到 S33_ALL。"""
    import allstock_data as AD
    import jq_extra_data as X
    cc_a, oc_a = PD.sector_daily_long()
    A = AD.load()
    snaps = X.master_snapshots()
    cc_b, oc_b = PD.sector_daily_pit(A, snaps)
    cut = pd.Timestamp(ERA_B_START)
    cc = pd.concat([cc_a[cc_a.index < cut], cc_b[cc_b.index >= cut]]).reindex(days)
    oc = pd.concat([oc_a[oc_a.index < cut], oc_b[oc_b.index >= cut]]).reindex(days)
    cc = cc.reindex(columns=PEV.S33_ALL)
    oc = oc.reindex(columns=PEV.S33_ALL)
    return cc, oc, {"A": A, "snaps": snaps}


def events_for_study(days: pd.DatetimeIndex, stage: str = "explore") -> pd.DataFrame:
    """事件表 → r / t0 / tier / in_judgment / 去重 / overlap / crisis / era；explore 阶段只读 X 的事件行（r ≤ WIN_X[1]），C 的行不进内存。"""
    E = pd.read_csv(PD.EVENTS_PATH, dtype=str).fillna("")
    for c in PEV.EVENT_COLS:
        if c not in E.columns:
            E[c] = ""
    errs = PEV.validate_table(E)
    if errs:
        raise SystemExit("事件表校验失败：" + "；".join(errs[:10]))
    E["date"] = pd.to_datetime(E["date"])
    for c in ("sign", "market_dir", "excluded", "pre_announced"):
        E[c] = pd.to_numeric(E[c].replace("", "0")).astype(int)
    E["covert"] = pd.to_numeric(E["covert"].replace("", "0")).astype(int)
    E["tier"] = E["category"].map(lambda c: PEV.CATS.get(c, {}).get("tier", "excluded"))
    E["r"], E["t0"] = PD.reaction_and_entry(E, days)
    if stage == "explore":
        E = E[E["r"].isna() | (E["r"] <= pd.Timestamp(WIN_X[1]))].copy()          # 探索阶段不读确认窗口的事件
    E["in_judgment"] = (E["excluded"] == 0) & (E["verified"] != "") & (E["pre_announced"] == 0) & (E["covert"] == 0) & E["r"].notna()
    E["_o"] = [PEV.dedup_rank(c, h) for c, h in zip(E["category"], E["home"])]
    live = E[(E["excluded"] == 0) & E["r"].notna()].sort_values(["r", "_o"])
    dup = live.duplicated(subset=["r"], keep="first")
    E["dedup_drop"] = 0
    E.loc[live.index[dup.to_numpy()], "dedup_drop"] = 1
    E.loc[E["dedup_drop"] == 1, "in_judgment"] = False
    E["overlap"] = 0
    liv = E[E["in_judgment"]]
    if len(liv):
        E.loc[liv.index, "overlap"] = PD.overlap_flags(pd.DatetimeIndex(liv["r"]), days)
    E["crisis"] = [PD.crisis_flag(r) for r in E["r"]]
    E["era"] = np.where(E["r"] < pd.Timestamp(ERA_B_START), "A", np.where(E["r"] <= pd.Timestamp(WIN_X[1]), "B1", "B2"))
    E["chain"] = PD.chain_ids(pd.DatetimeIndex(E["r"]), days, CHAIN_GAP)
    return E.drop(columns=["_o"])


def last_change_subtype(E: pd.DataFrame, cat: str, r: pd.Timestamp) -> str | None:
    """对照池行 → 该类别在 r 之前最近一次（未排除）变更的子类（C4：套用「上一次变更方向」的名单）。"""
    g = E[(E["category"] == cat) & (E["excluded"] == 0) & (E["r"] < r)].sort_values("r")
    return str(g["subtype"].iloc[-1]) if len(g) else None


def lists_for(row: pd.Series, B: pd.DataFrame | None, available: list[str] | None = None, E: pd.DataFrame | None = None) -> dict:
    """事件的 P1 / P2 / P3 名单；对照池行按上一次变更方向套 P1。"""
    cat, sub = row["category"], row["subtype"]
    empty = {"P1": ([], []), "P2": ([], []), "P3": ([], []), "note": ""}
    if cat in PEV.CONTROL_OF:
        if E is None:
            return empty
        base = PEV.CONTROL_OF[cat]
        prev = last_change_subtype(E, base, row["r"])
        if prev is None:
            return empty
        b1, v1, note = PEV.derive_lists(base, prev, available)
        return {"P1": (b1, v1), "P2": ([], []), "P3": ([], []), "note": f"ctrl:{base}/{prev};{note}"}
    if cat not in PEV.CATS or PEV.CATS[cat]["tier"] in ("weak", "control", "excluded"):
        return empty
    b1, v1, note = PEV.derive_lists(cat, sub, available)
    shocks = PEV.shock_vector(cat)
    sign = PEV.CATS[cat]["subtypes"].get(sub, 0)
    if sign < 0:
        shocks = {k: -v for k, v in shocks.items()}
    b2, v2 = PD.beta_lists(B, shocks) if shocks else ([], [])
    b3 = [s for s in b1 if s in b2]
    v3 = [s for s in v1 if s in v2]
    return {"P1": (b1, v1), "P2": (b2, v2), "P3": (b3, v3), "note": note}


# ───────────────────────── 反应（向量化） ─────────────────────────
def masks_for(lists: dict, idxs, cols: list[str], p: str) -> tuple[np.ndarray, np.ndarray]:
    """候选 p 的受益 / 受损掩码（事件 × 业种）。"""
    ci = {c: j for j, c in enumerate(cols)}
    B = np.zeros((len(idxs), len(cols)), bool)
    V = np.zeros((len(idxs), len(cols)), bool)
    for i, ix in enumerate(idxs):
        b, v = lists.get(ix, {}).get(p, ([], []))
        for s_ in b:
            if s_ in ci:
                B[i, ci[s_]] = True
        for s_ in v:
            if s_ in ci:
                V[i, ci[s_]] = True
    return B, V


def spread_matrix(x: np.ndarray, B: np.ndarray, V: np.ndarray, has_b: np.ndarray, has_v: np.ndarray, min_side: int = PD.MIN_SIDE) -> np.ndarray:
    """事件级价差（向量化，与 PD.spread 同一定义）：x (n × m) 业种超额；B / V 掩码；has_b / has_v = 名单里那一侧非空。"""
    fin = np.isfinite(x)
    xz = np.where(fin, x, 0.0)
    nb = (B & fin).sum(1)
    nv = (V & fin).sum(1)
    sb = (xz * (B & fin)).sum(1)
    sv = (xz * (V & fin)).sum(1)
    rest = fin & ~B & ~V
    nr = rest.sum(1)
    sr = (xz * rest).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mb, mv, mr = sb / nb, sv / nv, sr / nr
        out = np.where(has_b & has_v, mb - mv, np.where(has_b, mb - mr, np.where(has_v, mr - mv, np.nan)))
    bad = (~has_b & ~has_v) | (has_b & (nb < min_side)) | (has_v & (nv < min_side)) | (has_b & ~has_v & (nr == 0)) | (has_v & ~has_b & (nr == 0))
    out = out.astype(float)
    out[bad] = np.nan
    return out


def window_x(W: PD.WindowCache, WB: PD.WindowCache, w: str, rs, t0s, h_eff: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """窗口 w 的 (业种超额 x (n × m), 日経窗口收益 (n,))；h_eff 给出时逐事件截断（只对 open 窗口）。"""
    spec = WINDOWS[w]
    if spec[0] == "close":
        X = W.close_windows(rs, spec[1], spec[2])
        b = WB.close_windows(rs, spec[1], spec[2])[:, 0]
    else:
        h = spec[1]
        X = W.open_windows(t0s, h)
        b = WB.open_windows(t0s, h)[:, 0]
        if h_eff is not None:
            for i in np.where(h_eff < h)[0]:
                hi = int(h_eff[i])
                if hi <= 0:
                    X[i, :] = np.nan
                    b[i] = np.nan
                else:
                    X[i, :] = W.open_windows([t0s[i]], hi)[0]
                    b[i] = WB.open_windows([t0s[i]], hi)[0, 0]
    return X - b[:, None], b


def gap_vec(W: PD.WindowCache, WB: PD.WindowCache, rs, t0s) -> tuple[np.ndarray, np.ndarray]:
    """GAP = [r−1 收 → t0 开]（t0 = r 时 = 隔夜跳空；t0 = r+1 时 = D0 + 隔夜）：由 (1+cc)/(1+oc) 在 t0 与 D0 组合。"""
    k = W.pos(t0s)
    kr = W.pos(rs)
    n, m = len(k), len(W.columns)
    out = np.full((n, m), np.nan)
    ob = np.full(n, np.nan)
    C = np.exp(np.diff(W.L, axis=0)) - 1                                     # cc 小数（NaN 当 0）
    CB = np.exp(np.diff(WB.L, axis=0)) - 1
    for i in range(n):
        if k[i] < 0 or kr[i] < 0:
            continue
        g = (1 + C[k[i]]) / (1 + W.O[k[i]]) - 1                                  # open_t0 / close_{t0−1}
        gb = (1 + CB[k[i], 0]) / (1 + WB.O[k[i], 0]) - 1
        if k[i] > kr[i]:                                                        # t0 = r+1：加上 r 当天
            g = (1 + g) * (1 + C[kr[i]]) - 1
            gb = (1 + gb) * (1 + CB[kr[i], 0]) - 1
        out[i] = g * 100
        ob[i] = gb * 100
    return out - ob[:, None], ob


def trunc_h(E: pd.DataFrame, days: pd.DatetimeIndex, idxs, h: int) -> np.ndarray:
    """相邻反向事件截断：同类别、相反 sign、in_judgment 的下一事件 r 落在 [t0, t0+h−1] → h_eff = pos(next r) − pos(t0)。"""
    out = np.full(len(idxs), h, int)
    pos = {d: i for i, d in enumerate(days)}
    J = E[E["in_judgment"] & E["r"].notna()]
    for i, ix in enumerate(idxs):
        e = E.loc[ix]
        if pd.isna(e["t0"]) or e["t0"] not in pos:
            continue
        k0 = pos[e["t0"]]
        nxt = J[(J["category"] == e["category"]) & (J["sign"] == -e["sign"]) & (J["r"] > e["r"])].sort_values("r")
        if len(nxt) and nxt["r"].iloc[0] in pos:
            kn = pos[nxt["r"].iloc[0]]
            if kn - k0 < h:
                out[i] = max(kn - k0, 0)
    return out


# ───────────────────────── 统计 ─────────────────────────
def stats(v: np.ndarray, labels: np.ndarray | None = None) -> dict:
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    if ok.sum() == 0:
        return {"n": 0, "mean": None, "median": None, "hit": None, "lo": None, "hi": None}
    x = v[ok]
    lo, hi = PD.cluster_boot(x, np.asarray(labels)[ok], BOOT_N, SEED0) if labels is not None else (np.nan, np.nan)
    return {"n": int(len(x)), "mean": round(float(x.mean()), 3), "median": round(float(np.median(x)), 3), "hit": round(float((x > 0).mean() * 100), 1),
            "lo": None if np.isnan(lo) else round(lo, 3), "hi": None if np.isnan(hi) else round(hi, 3)}


def perm_p(obs: float | None, null: np.ndarray) -> float | None:
    """置换 p = (1 + #{对照 ≥ 观测}) / (1 + N)。"""
    if obs is None:
        return None
    null = np.asarray(null, float)
    null = null[np.isfinite(null)]
    if len(null) == 0:
        return None
    return round(float((1 + (null >= obs).sum()) / (1 + len(null))), 4)


def holm(pvals: dict[str, float | None], alpha: float = 0.05) -> dict[str, bool]:
    """Holm 逐步校正：按 p 升序，第 k 个（1 起）阈值 alpha / (m − k + 1)，第一次不过之后全部不过；None → 不过。"""
    items = [(k, p) for k, p in pvals.items() if p is not None]
    m = len(items)
    out = {k: False for k in pvals}
    ok = True
    for j, (k, p) in enumerate(sorted(items, key=lambda kv: kv[1])):
        if ok and p <= alpha / (m - j):
            out[k] = True
        else:
            ok = False
    return out


def judge(c: dict, w: str, stage: str, c1_hit95: float | None, holm_ok: dict, subs: dict, eras: dict, pre: dict, ctrl_mean: float | None) -> list[str]:
    """J1〜J8 → 未满足的条件（空 = 全过）。c = stats（含 lo）；holm_ok = {"C1": bool, "C2": bool}；subs = {类别: {子类: (mean, n)}}；eras = {段: mean}；pre = stats(PRE)。"""
    out = []
    m, h = c.get("mean"), c.get("hit")
    if m is None:
        return ["无样本"]
    if not (h >= J1_HIT and (c1_hit95 is None or h > c1_hit95)):
        out.append(f"J1 命中率 {h:.1f}% 未达 {J1_HIT:.0f}% 或未超过 C1 命中 95 分位 {c1_hit95}")
    if not (m >= J2_MEAN.get(w, 0.5) and (c.get("lo") or -1) > 0):
        out.append(f"J2 平均 {m:+.2f} pp（区间下限 {c.get('lo')}）未达 +{J2_MEAN.get(w, 0.5)} pp 且 > 0")
    need = J3_N.get("X" if stage == "explore" else "C", 40)
    if not c["n"] >= need:
        out.append(f"J3 事件数 {c['n']} < {need}")
    for k in ("C1", "C2"):
        if not holm_ok.get(k):
            out.append(f"J4 {k} 置换 p 经 Holm 后不 ≤ 0.05")
    for cat, d in subs.items():
        vals = {s_: v for s_, v in d.items() if v[1] >= J5_MIN_SUB}
        if len(vals) >= 2 and not all(v[0] > 0 for v in vals.values()):
            out.append(f"J5 {cat} 子类不都 > 0：" + "、".join(f"{s_} {v[0]:+.2f}(n{v[1]})" for s_, v in vals.items()))
    segs = {k: v for k, v in eras.items() if v is not None}
    if segs and not (all(v > 0 for v in segs.values()) or all(v < 0 for v in segs.values())):
        out.append("J6 年代分段不同号：" + "、".join(f"{k} {v:+.2f}" for k, v in segs.items()))
    if pre.get("mean") is not None and not (m - pre["mean"] > 0 and pre["mean"] < m / 2):
        out.append(f"J7 事前窗口 PRE {pre['mean']:+.2f} pp 不满足 S − PRE > 0 且 PRE < S/2")
    if ctrl_mean is not None and not m > ctrl_mean:
        out.append(f"J8 未超过无信息会合对照的平均 {ctrl_mean:+.2f} pp")
    return out


# ───────────────────────── 可执行性（描述） ─────────────────────────
def executability(E: pd.DataFrame, lists: dict, A: dict, snaps: dict, days: pd.DatetimeIndex) -> dict:
    """B 年代：受益业种成员股 t0 开盘 ×1.001 买、第 20 日收盘卖、扣成本、跳空 > 3% 放弃 → L20 统计。"""
    maps = PD.s33_map_pit(snaps)
    sd = sorted(maps)
    names = list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    pdays = pd.DatetimeIndex(A["days"])
    pos = pd.Series(np.arange(len(pdays)), index=pdays)
    vals, chains, aband, tot, lot25, lot34 = [], [], 0, 0, [], []
    for i, e in E.iterrows():
        if e["era"] == "A" or not e["in_judgment"] or e["tier"] != "strong":
            continue
        b = lists.get(i, {}).get("P1", ([], []))[0]
        if not b or pd.isna(e["t0"]) or e["t0"] not in pos.index or e["r"] not in pos.index:
            continue
        k0, kr = int(pos[e["t0"]]), int(pos[e["r"]])
        if k0 + 19 >= len(pdays):
            continue
        prev = [d for d in sd if d < e["r"]]
        mp = maps[prev[-1]] if prev else maps[sd[0]]
        for t, g in mp.items():
            j = col.get(t)
            if j is None or g not in b or not A["listed"][k0, j]:
                continue
            o, cr, c20 = A["O"][k0, j], A["C"][kr, j], A["C"][k0 + 19, j]
            if not (np.isfinite(o) and np.isfinite(cr) and np.isfinite(c20) and o > 0 and cr > 0):
                continue
            tot += 1
            if o > cr * 1.03:
                aband += 1
                continue
            ret = (c20 / (o * 1.001) - 1) * 100 - COST_PCT
            vals.append(ret); chains.append(e["chain"])
            lot = cr * A["R"][kr, j] * 100 if np.isfinite(A["R"][kr, j]) else np.nan
            lot25.append(ret if lot <= 250000 else np.nan); lot34.append(ret if lot <= 340000 else np.nan)
    s = stats(np.array(vals), np.array(chains)) if vals else stats(np.array([]))
    return {"L20": s, "abandon_pct": round(aband / tot * 100, 1) if tot else None, "candidates": tot,
            "lot_le_25": stats(np.array(lot25)), "lot_le_34": stats(np.array(lot34)),
            "tradable_drift": bool(s["n"] and s["mean"] is not None and s["mean"] >= 0.5 and (s.get("lo") or -1) > 0)}


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:                                                        # noqa: BLE001
        return "?"


# ───────────────────────── 主流程 ─────────────────────────
def run_study(stage: str, n_perm: int = N_PERM, say=print) -> dict:
    t_start = time.time()
    days, n225 = load_days()
    bcc, boc = bench_daily(n225)
    cc, oc, ctx = sector_daily(days)
    tpx = topix_frames()
    E = events_for_study(days, stage)
    end_cut = days[-1 - END_CUT]
    say(f"事件表 {len(E)} 行（计入判定 {int(E['in_judgment'].sum())}）；业种序列 {cc.shape}；{time.time() - t_start:.0f}s")
    W = PD.WindowCache(cc.reindex(days), oc.reindex(days))
    WB = PD.WindowCache(bcc.reindex(days), boc.reindex(days))
    WT = PD.WindowCache(tpx[0].reindex(days), tpx[1].reindex(days)) if tpx is not None else None
    cols = list(cc.columns)
    # 事前 β（P2）与名单（可得性 = t0 当天该业种有值）
    fac_w = PD.factor_weekly()
    sec_w = PD.weekly_from_daily(cc)
    mkt_w = PD.weekly_from_daily(bcc)["N225"]
    avail_at = {}
    for i, e in E.iterrows():
        if pd.notna(e["t0"]) and e["t0"] in cc.index:
            row = cc.loc[e["t0"]]
            avail_at[i] = [c for c in cols if np.isfinite(row[c])]
        else:
            avail_at[i] = None
    betas = {i: PD.betas_asof(sec_w, fac_w, mkt_w, e["r"]) if pd.notna(e["r"]) else None for i, e in E.iterrows()}
    lists = {i: lists_for(e, betas[i], avail_at[i], E) for i, e in E.iterrows()}
    E["basket"] = [f"{len(lists[i]['P1'][0])}/{len(lists[i]['P1'][1])}" for i in E.index]
    E["subst"] = [int("subst" in lists[i]["note"]) for i in E.index]
    idx_all = list(E.index)
    rs, t0s = pd.DatetimeIndex(E["r"]), pd.DatetimeIndex(E["t0"])
    pos_of = {ix: k for k, ix in enumerate(idx_all)}
    # 各窗口的业种超额矩阵（全窗口 + 截断版）
    X, BENCH, XT = {}, {}, {}
    for w in WINDOWS:
        X[w], BENCH[w] = window_x(W, WB, w, rs, t0s)
        if WINDOWS[w][0] == "open":
            XT[w], _ = window_x(W, WB, w, rs, t0s, trunc_h(E, days, idx_all, WINDOWS[w][1]))
        else:
            XT[w] = X[w]
    GAPX, GAPB = gap_vec(W, WB, rs, t0s)
    PREX = {w: window_x(W, WB, "D0", rs, t0s)[0] * np.nan for w in PRE}
    for w, (lo, hi) in PRE.items():
        PREX[w] = W.close_windows(rs, lo, hi) - WB.close_windows(rs, lo, hi)[:, 0][:, None]
    # 每个候选的价差（全部事件；主分析 = 截断版）
    S = {}
    Sfull = {}
    for p in ("P1", "P2", "P3"):
        B, V = masks_for(lists, idx_all, cols, p)
        has_b, has_v = B.any(1), V.any(1)
        for w in WINDOWS:
            S[(p, w)] = spread_matrix(XT[w], B, V, has_b, has_v)
            Sfull[(p, w)] = spread_matrix(X[w], B, V, has_b, has_v)
        S[(p, "GAP")] = spread_matrix(GAPX, B, V, has_b, has_v)
        S[(p, "PRE_W5")] = spread_matrix(PREX["W5"], B, V, has_b, has_v)
        S[(p, "PRE_W20")] = spread_matrix(PREX["W20"], B, V, has_b, has_v)
    md = np.where(E["category"].to_numpy() == "ELECTION", E["market_dir"].to_numpy(), [PEV.market_dir_of(c, s_) for c, s_ in zip(E["category"], E["subtype"])]).astype(float)
    for w in WINDOWS:
        S[("P4", w)] = np.where(md != 0, md * BENCH[w], np.nan)
        Sfull[("P4", w)] = S[("P4", w)]
        S[("P5", w)] = np.full(len(idx_all), np.nan)
        if WT is not None:
            spec = WINDOWS[w]
            tb = WT.close_windows(rs, spec[1], spec[2])[:, 0] if spec[0] == "close" else WT.open_windows(t0s, spec[1])[:, 0]
            S[("P5", w)] = np.where(E["category"].to_numpy() == "BOJ_ETF", E["sign"].to_numpy() * (BENCH[w] - tb), np.nan)
        Sfull[("P5", w)] = S[("P5", w)]
    # C3：受益篮子 − 全部可得业种等权
    B1, V1 = masks_for(lists, idx_all, cols, "P1")
    for w in ("W5", "W20"):
        fin = np.isfinite(XT[w])
        xz = np.where(fin, XT[w], 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            S[("C3", w)] = np.where(B1.any(1), (xz * (B1 & fin)).sum(1) / np.maximum((B1 & fin).sum(1), 1) - xz.sum(1) / np.maximum(fin.sum(1), 1), np.nan)
    strong = E[(E["tier"] == "strong") & E["in_judgment"] & (E["r"] <= end_cut)]
    ctrl = E[(E["tier"] == "control") & (E["excluded"] == 0) & (E["verified"] != "") & E["r"].notna() & (E["r"] <= end_cut)]
    say(f"强类别计入 {len(strong)} 条、对照池 {len(ctrl)} 条；{time.time() - t_start:.0f}s")
    wins = {"X": WIN_X} if stage == "explore" else {"X": WIN_X, "C": (WIN_C[0], str(end_cut.date()))}
    res = {"stage": stage, "git": git_rev(), "rules_version": PEV.rules_version(), "events_sha256": hashlib.sha256(Path(PD.EVENTS_PATH).read_bytes()).hexdigest()[:16],
           "windows": wins, "n_perm": n_perm, "confirm_ids": list(CONFIRM_IDS), "n_events": int(len(E)), "n_judgment": int(E["in_judgment"].sum()),
           "x_end": WIN_X[1], "c_end": str(end_cut.date()), "era_b_start": ERA_B_START,
           "by_category": {f"{k[0]}/{k[1]}": int(v) for k, v in E[E["excluded"] == 0].groupby(["category", "subtype"]).size().to_dict().items()},
           "tests": {}, "library": {}, "elapsed_s": None}

    def sel(win, idxs):
        m = E.loc[idxs, "r"].between(pd.Timestamp(win[0]), pd.Timestamp(win[1]))
        return [ix for ix, ok in zip(idxs, m) if ok]

    # 置换对照：C1 打乱日期（t0 与 r 的关系保持）、C2 随机业种（真实日期）
    rng = np.random.default_rng(SEED0)
    same_day = (t0s == rs)
    null = {}                                                   # (wname, p, w, "C1"/"C2") → {"mean": [...], "hit": [...]}
    for wname, win in wins.items():
        sidx = sel(win, list(strong.index))
        if not sidx:
            continue
        k = np.array([pos_of[ix] for ix in sidx])
        srs, st0, ssd = rs[k], t0s[k], same_day.to_numpy()[k] if hasattr(same_day, "to_numpy") else np.asarray(same_day)[k]
        masks = {p: masks_for(lists, sidx, cols, p) for p in ("P1", "P2", "P3")}
        for w in ("W5", "W20"):
            h = WINDOWS[w][1]
            xr = XT[w][k]
            for p in ("P1", "P2", "P3"):
                B, V = masks[p]
                has_b, has_v = B.any(1), V.any(1)
                d1 = {"mean": [], "hit": []}
                d2 = {"mean": [], "hit": []}
                nb, nv = B.sum(1), V.sum(1)
                for s in range(n_perm):
                    r2 = PD.shuffle_dates(srs, days, SEED0 + s)
                    t2 = pd.DatetimeIndex([r_ if sd_ else PD._next_after(days, r_) for r_, sd_ in zip(r2, ssd)])
                    x2 = W.open_windows(t2, h) - WB.open_windows(t2, h)[:, 0][:, None]
                    v = spread_matrix(x2, B, V, has_b, has_v)
                    d1["mean"].append(np.nanmean(v) if np.isfinite(v).any() else np.nan)
                    d1["hit"].append(float((v[np.isfinite(v)] > 0).mean() * 100) if np.isfinite(v).any() else np.nan)
                    # C2：同样个数的随机可得业种
                    keys = rng.random(xr.shape)
                    keys[~np.isfinite(xr)] = np.inf
                    order = np.argsort(keys, axis=1)
                    rank = np.argsort(order, axis=1)
                    B2 = rank < nb[:, None]
                    V2 = (rank >= nb[:, None]) & (rank < (nb + nv)[:, None])
                    v2 = spread_matrix(xr, B2, V2, has_b, has_v)
                    d2["mean"].append(np.nanmean(v2) if np.isfinite(v2).any() else np.nan)
                    d2["hit"].append(float((v2[np.isfinite(v2)] > 0).mean() * 100) if np.isfinite(v2).any() else np.nan)
                null[(wname, p, w, "C1")] = d1
                null[(wname, p, w, "C2")] = d2
        say(f"对照 {wname}：{n_perm} 次置换完成；{time.time() - t_start:.0f}s")
    # 判定
    entered = []
    for wname, win in wins.items():
        block = {}
        sidx = sel(win, list(strong.index))
        cidx = sel(win, list(ctrl.index))
        for p in ("P1", "P2", "P3", "P4", "P5"):
            for w in ("W5", "W20"):
                idxs = sel(win, list(E[(E["category"] == "BOJ_ETF") & E["in_judgment"] & (E["r"] <= end_cut)].index)) if p == "P5" else sidx
                k = np.array([pos_of[ix] for ix in idxs], int)
                v = S[(p, w)][k] if len(k) else np.array([])
                lab = E.loc[idxs, "chain"].to_numpy() if len(k) else np.array([])
                st = stats(v, lab)
                n1 = null.get((wname, p, w, "C1"), {})
                n2 = null.get((wname, p, w, "C2"), {})
                p1 = perm_p(st.get("mean"), np.array(n1.get("mean", []))) if n1 else None
                p2 = perm_p(st.get("mean"), np.array(n2.get("mean", []))) if n2 else None
                hit95 = round(float(np.nanpercentile(n1["hit"], 95)), 1) if n1 and np.isfinite(n1["hit"]).any() else None
                eras = {}
                if len(k):
                    for era, g in E.loc[idxs].groupby("era"):
                        if wname == "X" and era == "B2":
                            continue
                        x = S[(p, w)][[pos_of[ix] for ix in g.index]]
                        eras[era] = float(np.nanmean(x)) if np.isfinite(x).sum() >= J6_MIN_SEG else None
                subs = {}
                if p in ("P1", "P2", "P3") and len(k):
                    for cat, g in E.loc[idxs].groupby("category"):
                        if len(PEV.CATS[cat]["subtypes"]) < 2:
                            continue
                        d = {}
                        for sub_, gg in g.groupby("subtype"):
                            x = S[(p, w)][[pos_of[ix] for ix in gg.index]]
                            x = x[np.isfinite(x)]
                            d[sub_] = (float(x.mean()) if len(x) else 0.0, int(len(x)))
                        subs[cat] = d
                pre_st = stats(S[(p, f"PRE_{w}")][k]) if p in ("P1", "P2", "P3") and len(k) else {}
                ctrl_mean = None
                if p == "P1" and len(cidx):
                    kc = np.array([pos_of[ix] for ix in cidx], int)
                    xc = S[(p, w)][kc]
                    ctrl_mean = float(np.nanmean(xc)) if np.isfinite(xc).sum() >= MIN_DESC else None
                block[f"{p}@{w}"] = {"stats": st, "p_C1": p1, "p_C2": p2, "C1_hit95": hit95, "eras": {kk: (None if vv is None else round(vv, 3)) for kk, vv in eras.items()},
                                     "subtypes": {c: {s_: [round(v_[0], 3), v_[1]] for s_, v_ in d.items()} for c, d in subs.items()},
                                     "PRE": pre_st, "ctrl_mean": None if ctrl_mean is None else round(ctrl_mean, 3), "desc": CANDS[p],
                                     "full": stats(Sfull[(p, w)][k], lab) if len(k) else stats(np.array([]))}
        # Holm：主族（MAIN，2 个）与次要族（SECONDARY）分开，C1 / C2 各自校正
        fams = {"main": [f"{p}@{w}" for p, w in MAIN], "secondary": [f"{p}@{w}" for p, w in SECONDARY]}
        for fam, keys in fams.items():
            for ck in ("C1", "C2"):
                hb = holm({kk: block[kk][f"p_{ck}"] for kk in keys if kk in block})
                for kk, ok in hb.items():
                    block[kk][f"holm_{ck}"] = ok
                    block[kk]["family"] = fam
        for kk, b in block.items():
            p_, w_ = kk.split("@")
            holm_ok = {"C1": b.get("holm_C1", False), "C2": b.get("holm_C2", False)} if p_ in ("P1", "P2", "P3") else {"C1": b.get("holm_C1", False), "C2": b.get("holm_C1", False)}
            eras_j = b["eras"]
            subs_j = {c: {s_: (v_[0], v_[1]) for s_, v_ in d.items()} for c, d in b["subtypes"].items()}
            b["fails"] = judge(b["stats"], w_, stage, b["C1_hit95"], holm_ok, subs_j, eras_j, b["PRE"], b["ctrl_mean"]) if b["stats"]["n"] else ["无样本"]
        if wname == "X":
            entered = [kk for kk, b in block.items() if not b["fails"]]
        res["tests"][wname] = block
    res["entered_X"] = entered
    if stage == "confirm":
        for k in CONFIRM_IDS:
            b = res["tests"]["C"].get(k)
            if b:
                p_ = k.split("@")[0]
                b["verdict"] = (LABEL[p_] + "：X、C 都过 → 日报标签，仍只展示 + 前向；「登记确认」只由前向记录授予") if not b["fails"] else \
                    "C 不过 → " + ("时代依赖" if all(f.startswith("J6") for f in b["fails"]) else "不成立")
    # 对照池自身（C4 描述）
    if len(ctrl):
        kc = np.array([pos_of[ix] for ix in ctrl.index], int)
        res["controls"] = {w: {cat: stats(S[("P1", w)][[pos_of[ix] for ix in g.index]], g["chain"].to_numpy()) for cat, g in ctrl.groupby("category")} for w in ("W5", "W20")}
    # 展示库：类别 × 子类 × 业种 × 窗口（描述；explore 阶段只含 X）
    lib = {}
    for (cat, sub_), g in E[(E["excluded"] == 0) & E["r"].notna()].groupby(["category", "subtype"]):
        kk = np.array([pos_of[ix] for ix in g.index], int)
        ent = {"n": int(len(g)), "n_judgment": int(g["in_judgment"].sum()), "windows": {}}
        for w in WINDOWS:
            M = X[w][kk]
            sec = {}
            for j, s_ in enumerate(cols):
                v = M[:, j]
                v = v[np.isfinite(v)]
                if len(v):
                    sec[s_] = {"n": int(len(v)), "mean": round(float(v.mean()), 2), "hit": round(float((v > 0).mean() * 100), 0) if len(v) >= 5 else None}
            ent["windows"][w] = {"sectors": sec, "spread_P1": stats(S[("P1", w)][kk], g["chain"].to_numpy()), "spread_P2": stats(S[("P2", w)][kk], g["chain"].to_numpy()),
                                 "spread_P4": stats(S[("P4", w)][kk], g["chain"].to_numpy()), "bench": stats(BENCH[w][kk])}
        ent["GAP"] = stats(S[("P1", "GAP")][kk])
        ent["benef"], ent["victim"] = (PEV.derive_lists(cat, sub_)[:2] if cat in PEV.CATS and PEV.CATS[cat]["tier"] in ("strong", "mid") else ([], []))
        ent["market_dir"] = PEV.market_dir_of(cat, sub_)
        lib[f"{cat}/{sub_}"] = ent
    res["library"] = lib
    # 模糊事件 / 覆面介入（C6，只描述）
    amb = E[(E["category"] == "BOJ_CHANGE") & (E["excluded"] == 1) & E["date"].dt.strftime("%Y-%m-%d").isin(PEV.EXCLUDED_BOJ)]
    cov = E[(E["category"] == "MOF_FX") & (E["covert"] == 1) & (E["excluded"] == 0)]
    res["ambiguous"] = {"boj": {e["id"]: {w: (None if not np.isfinite(S[("P1", w)][pos_of[i]]) else round(float(S[("P1", w)][pos_of[i]]), 2)) for w in ("D0", "W5", "W20")} for i, e in amb.iterrows()},
                        "mof_covert": {w: stats(S[("P1", w)][[pos_of[i] for i in cov.index]]) for w in ("D0", "W5", "W20")} if len(cov) else {}}
    # 描述：吃不到比例、篮子、子集、可执行性
    ks = np.array([pos_of[ix] for ix in strong.index], int)
    g_abs = np.nanmean(np.abs(S[("P1", "GAP")][ks])) if len(ks) else np.nan
    w20_abs = np.nanmean(np.abs(S[("P1", "W20")][ks])) if len(ks) else np.nan
    sub_desc = {}
    for name, m_ in (("overlap0", strong["overlap"] == 0), ("crisis0", strong["crisis"] == 0), ("no_subst", strong["subst"] == 0)):
        kx = np.array([pos_of[ix] for ix in strong.index[m_.to_numpy()]], int)
        sub_desc[name] = stats(S[("P1", "W5")][kx]) if len(kx) else stats(np.array([]))
    close_entry = {}
    for w in ("W5", "W20"):
        h = WINDOWS[w][1]
        Xc = W.close_windows(t0s, 1, h) - WB.close_windows(t0s, 1, h)[:, 0][:, None]
        vc = spread_matrix(Xc, B1, V1, B1.any(1), V1.any(1))
        close_entry[w] = {era: stats(vc[[pos_of[ix] for ix in g.index]]) for era, g in strong.groupby("era") if not (stage == "explore" and era == "B2")}
    tp_desc = {}
    if WT is not None and len(ks):
        for w in ("W5", "W20"):
            h = WINDOWS[w][1]
            xt = W.open_windows(t0s, h) - WT.open_windows(t0s, h)[:, 0][:, None]
            vt = spread_matrix(xt, B1, V1, B1.any(1), V1.any(1))
            tp_desc[w] = stats(vt[ks])
    res["desc"] = {"gap_abs_mean": None if np.isnan(g_abs) else round(float(g_abs), 3), "w20_abs_mean": None if np.isnan(w20_abs) else round(float(w20_abs), 3),
                   "uneatable_ratio": None if not np.isfinite(g_abs) or not w20_abs else round(float(g_abs / w20_abs), 2),
                   "baskets": strong["basket"].value_counts().to_dict(), "subst_events": int(strong["subst"].sum()),
                   "subsets_W5": sub_desc, "close_entry": close_entry, "topix_bench": tp_desc,
                   "executability_B": executability(E, lists, ctx["A"], ctx["snaps"], days) if stage != "explore" or True else {}}
    res["events"] = [{"id": e["id"], "category": e["category"], "subtype": e["subtype"], "r": str(e["r"].date()) if pd.notna(e["r"]) else None,
                      "t0": str(e["t0"].date()) if pd.notna(e["t0"]) else None, "in_judgment": bool(e["in_judgment"]), "dedup_drop": int(e["dedup_drop"]),
                      "era": e["era"], "basket": e["basket"], "subst": int(e["subst"]), "chain": int(e["chain"]), "note": lists[i]["note"],
                      "S_P1_W5": None if not np.isfinite(S[("P1", "W5")][pos_of[i]]) else round(float(S[("P1", "W5")][pos_of[i]]), 2)}
                     for i, e in E.iterrows() if e["excluded"] == 0]
    res["elapsed_s"] = round(time.time() - t_start)
    return res


def _f(s: dict) -> str:
    if not s or not s.get("n"):
        return "n=0"
    return f"n={s['n']} 均值 {s['mean']:+.2f} pp 中位 {s['median']:+.2f} 命中 {s['hit']:.0f}%" + (f" 区间 [{s['lo']:+.2f}, {s['hi']:+.2f}]" if s.get("lo") is not None else "")


def report(res: dict) -> str:
    L = [f"# 政策事件反应库 G1 —— {res['stage']}（git {res['git']}，规则 {res['rules_version']}，事件表 sha {res['events_sha256']}，置换 {res['n_perm']} 次）", "",
         f"事件表 {res['n_events']} 行，计入判定 {res['n_judgment']}；窗口 {res['windows']}；确认窗口末尾 c_end = {res['c_end']}", "",
         "类别行数：" + "、".join(f"{k} {v}" for k, v in sorted(res["by_category"].items())), ""]
    for wname, block in res["tests"].items():
        L.append(f"## 判定 {wname}")
        L.append("| 检验 | 族 | 统计（截断版） | 全窗口 | p C1 / C2 | C1 命中95 | 年代 | 子类 | PRE | 对照均值 | 未满足 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for k, b in block.items():
            eras = "、".join(f"{kk} {vv:+.2f}" for kk, vv in b["eras"].items() if vv is not None) or "—"
            subs = "；".join(f"{c}:" + "、".join(f"{s_} {v_[0]:+.2f}(n{v_[1]})" for s_, v_ in d.items()) for c, d in b["subtypes"].items()) or "—"
            pre = _f(b["PRE"]) if b.get("PRE") else "—"
            L.append(f"| {k}{'（确认）' if k in res.get('confirm_ids', []) else ''} | {b.get('family', '')} | {_f(b['stats'])} | {_f(b['full'])} | {b['p_C1']} / {b['p_C2']} | {b['C1_hit95']} | {eras} | {subs} | {pre} | {b['ctrl_mean']} | {'；'.join(b['fails']) or '全过'}{('｜' + b['verdict']) if b.get('verdict') else ''} |")
        L.append("")
    L.append(f"探索窗口全过的候选（可写进 CONFIRM_IDS）：{res.get('entered_X') or '无'}")
    L.append("")
    if res.get("controls"):
        L.append("## 无信息会合对照池（C4，按上一次变更方向套名单）")
        for w, d in res["controls"].items():
            L.append(f"- {w}：" + "；".join(f"{c} {_f(s)}" for c, s in d.items()))
        L.append("")
    d = res.get("desc") or {}
    L.append("## 描述")
    L.append(f"- 吃不到的部分：|GAP| 平均 {d.get('gap_abs_mean')} pp，|W20| 平均 {d.get('w20_abs_mean')} pp，比例 {d.get('uneatable_ratio')}")
    L.append(f"- 篮子大小分布（受益/受损）：{d.get('baskets')}；发生替补的事件 {d.get('subst_events')}")
    L.append("- 子集（P1@W5）：" + "；".join(f"{k} {_f(v)}" for k, v in (d.get("subsets_W5") or {}).items()))
    for w, ce in (d.get("close_entry") or {}).items():
        L.append(f"- 收盘进场稳健性 {w}：" + "；".join(f"{era} {_f(s)}" for era, s in ce.items()))
    if d.get("topix_bench"):
        L.append("- 基准换 TOPIX（2016-11〜）：" + "；".join(f"{w} {_f(s)}" for w, s in d["topix_bench"].items()))
    ex = d.get("executability_B") or {}
    if ex:
        L.append(f"- 可执行性 L20（B 年代受益业种成员股）：{_f(ex.get('L20'))}；放弃 {ex.get('abandon_pct')}%（候选 {ex.get('candidates')}）；一手 ≤ ¥25 万 {_f(ex.get('lot_le_25'))}；可交易漂移 = {ex.get('tradable_drift')}")
    L.append("")
    amb = res.get("ambiguous") or {}
    if amb.get("boj"):
        L.append("## 模糊事件（登记排除，只描述；P1 名单按表里的子类）")
        for k, v in amb["boj"].items():
            L.append(f"- {k}：D0 {v.get('D0')} W5 {v.get('W5')} W20 {v.get('W20')}")
    if amb.get("mof_covert"):
        L.append("- 覆面介入（covert = 1，按实施日算，只描述）：" + "；".join(f"{w} {_f(s)}" for w, s in amb["mof_covert"].items()))
    L.append("")
    L.append("## 展示库（类别 / 子类 → P1 价差 W5 / W20，全历史描述）")
    for k, ent in sorted(res["library"].items()):
        w5 = ent["windows"].get("W5", {}).get("spread_P1") or {}
        w20 = ent["windows"].get("W20", {}).get("spread_P1") or {}
        L.append(f"- {k}（n={ent['n']}，判定 {ent['n_judgment']}）：受益 {'、'.join(ent['benef']) or '—'}；受损 {'、'.join(ent['victim']) or '—'}；W5 {_f(w5)}；W20 {_f(w20)}；GAP {_f(ent.get('GAP'))}")
    L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。非投资建议。")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["explore", "confirm", "library"], default="explore")
    ap.add_argument("--perm", type=int, default=N_PERM)
    ap.add_argument("--review", action="store_true", help="前向记录复核（qbreak/policy_forward.review）")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    if a.review:
        from qbreak import policy_forward as PF
        out = PF.review()
        print(out.get("text", ""))
        return 0
    if a.stage == "confirm" and not CONFIRM_IDS:
        raise SystemExit("CONFIRM_IDS 为空：探索窗口没有候选通过，按登记不跑确认窗口的判定（要展示库用 --stage library）")
    res = run_study(a.stage, a.perm)
    out_dir = paths.PROJECT_ROOT / "var" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report(res)
    (out_dir / OUT_MD).write_text(md + "\n", encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if a.stage in ("confirm", "library"):
        lib = {"git": res["git"], "rules_version": res["rules_version"], "events_sha256": res["events_sha256"], "stage": a.stage, "c_end": res["c_end"],
               "library": res["library"], "tests": res["tests"], "controls": res.get("controls"), "note": "第二阶段个股层没有干净的确认窗口，只能前向"}
        (out_dir / LIB_JSON).write_text(json.dumps(lib, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
