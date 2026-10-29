"""lvs_study.py — 「大量保有報告書 × 全市場 W2 突破」研究（登记版：候选、标签、对照、判定、读法全部写在这里；提交后不改规则、只运行一次）。

运行前修正（2026-10-05，登记 6826c2b 之后、只数了个数、没算任何收益）：--counts 显示 2021-09-01〜2026-06-25 的 3,729 个 W2 信号里
  L1 / L2 / L3 只有 71 / 98 / 28 个（1.9% / 2.6% / 0.8%；今天的日経225 0 / 17 / 2 个）→ 逐笔 ≤ 信号数 < 300 = S3 必定不过 → 不运行 --run；
  结论按登记 = 三个都「不成立（覆盖太少）」。改问「报告本身有没有信息」→ scripts/lvs_event_study.py（另行登记、只运行一次）。

来由：用户 2026-10-05「回到〔63〕的选股方向（TDnet 适时开示 / 大量保有報告書）。」→ TDnet 要 J-Quants 附加包（现在的 API 键调 /v2/td/list 返回 403
「This API is not available on your subscription」，✋ 等用户决定买不买），先做 Standard 已含的大量保有報告書。
目标 = 让个股层的选股更准（胜率 / 每笔）：候选都是「全市場 W2 突破信号的保留 / 否决规则」（W2 池的子集），不是新买点；不改交易规则
（模拟盘、执行器只下日経225、W2 门槛都不动）；结论上限 = 「提议 + 前向记录」（用户确认才改）。
照实先说：B3 只买日経225，大型股的 5% 报告大多是机构投资者的例行（特例）报告 → 就算全市场成立，直接用到 B3 的空间也有限；本研究回答的是
「大量保有这类信息有没有选股价值」，用到 B3 要另行登记账户检验。样板：scripts/demand_study.py（同一个信号池、逐笔机制、对照与档位）。

一 数据（scripts/lvs_data.py；原始记录含个人的姓名、住址、借款对象 → 只在已 gitignore 的 var/cache/jquants/edinet_lvs/，绝不入库；仓库里只放汇总数字）
  J-Quants /v2/edinet/large-volume-shareholders（Standard 已含，提出日 2021-07-01 起）：书类 350（大量保有報告書・変更報告書）与 360（訂正）。
  每份报告：提出日 SubDate、报告义务发生日 RptOblgDate、大量保有書類種別 LargeHldgTypeCode（1 大量保有報告書 / 2 変更報告書 / 3 変更報告書（短期大量譲渡）/
  4 大量保有報告書（特例対象株券等）/ 5 変更報告書（特例対象株券等）/ 6 訂正 / 0 不明）、株券等保有割合与上次、提出者区分、保有目的、重要提案行為等、
  最近 60 日的取得 / 处分（市場内外、取得 / 処分）。只用 350（360 订正不用：当时市场看到的是原报告；订正以另一个书类号发布、不覆盖原报告）；
  报告义务发生日 = 2026-05-01 的报告不用（2026-05-01 施行的法令修改改了保有割合算法、共同保有者范围与格式，J-Quants 说明这一天的差分不能当买卖）。

二 信号池、逐笔、基准（与 demand_study 同一套）
  池 P = var/cache/jquants/allstock_train.pkl（东证一般市場、时点上市掩码、现行突破规则）里 w5v ≥ 1.0 或缺值的突破信号（scripts/demand_features.py 的特征表）。
  逐笔 = fins_event_study.run_trades：每只票一次一仓、信号日下一开盘 ×1.001 买、开盘 > 信号日收盘 ×1.03 放弃、现行卖法、扣 ¥25 万一笔来回成本 + 滑点、
  退市按最后收盘、期末未平仓不算。
  窗口（一次判定，不分探索 / 确认：候选只有 3 个、都是事先按文献与制度写定，没有用这批数据挑过）：信号日 2021-09-01〜min(2026-09-25, 数据末尾 − 61 个交易日)
  （今天的面板到 2026-09-25 → 2026-06-25）；前一半 H1 2021-09-01〜2023-12-29、后一半 H2 2024-01-04〜末尾（必要条件 (c) 要两半同号）。
  资格池 E = 窗口内全部 P（标签对每个信号都能算：窗口里没有报告 = 不标记）；基准 B_c = E 在候选「第一笔到最后一笔信号日」范围内的全部逐笔；
  剔除组 = E ∧ ¬候选（只描述「保留 − 剔除」）。

三 标签（信号日 d 收盘后决定、d+1 开盘成交；J-Quants 平日 8:00〜17:59 更新，晚于模拟盘 06:57 的决策 → 只用提出日严格早于 d 的报告）
  报告 f 落在信号 (票, d) 的窗口 ⇔ d − 60 天 ≤ SubDate(f) ≤ d − 1 天（日历日；60 天 = 制度上「最近 60 日取得处分」的长度）。
  新进 / 增持 up = 种别 1 / 4，或 种别 2 / 3 / 5 且 保有割合 > 上次；减持 down = 种别 2 / 3 / 5 且 保有割合 < 上次；
  市场内取得 buy = 任一提出者的最近 60 日表里有「市場内 ∧ 取得」；市场内处分 sell = 「市場内 ∧ 処分」；一般报告 gen = 种别 1 / 2 / 3；特例报告 spc = 种别 4 / 5。

四 候选（3 个；阈值写死、不做网格；方向 s 事先写定）
  L1 一般报告的买进：窗口内有 gen ∧ up ∧ buy 的报告。方向 = 保留组更好（s = +1）。
    理由：特例报告只有机构投资者能用、且不能以重要提案行為等为目的 → 一般报告 = 事业公司、个人、积极股东、不用特例的基金；在市场里买到 5% 以上（或再加）
    = 有信息、有持续性的需求（欧美 13D 与日本 5% 规则的研究：公告前后有正的超额收益，积极股东 / 投资基金较明显）。
    诚实：报告在义务发生后 5 个营业日内才提出，买盘可能已经买完；公告当天的跳涨可能就是那个突破 → 必要条件 (a)；TOB 前的建仓（之后股价钉在 TOB 价）会拉低 L1。
  L2 特例报告的增持（机构投资者）：窗口内有 spc ∧ up 的报告。方向 = 保留组更好（s = +1）。诚实：多是被动 / 指数资金或比例被动变化 → 先验偏低。
  L3 减持卖出（否决）：窗口内有 down ∧ sell 的报告（任何种别）。方向 = 被标记的组更差（s = −1）→ 规则 = 不买被标记的信号。
    注：特例报告没有「最近 60 日取得处分」表（登记前数结构：种别 4 / 5 的报告几乎都没有这张表，个数见 sim_changes 的登记记录）→ L3 实际上只来自一般报告；L2 也不看这张表。
    理由：大股东正在市场里减持 = 持续的供给，突破后更容易被卖压压回。
  只描述（不判定）：窗口内有任何报告、180 天内有重要提案行為等、L1 ∧ L3、按规模带 / 时点 TOPIX 500 / 今天的日経225 / 年 / 公告到信号的天数（1〜6 天 vs 7〜60 天）。

五 对照（引擎精确重跑；30 个种子从 20261005 起；参数化 99% 界 = 均值 ± t(0.99, 29) × 标准差：s = +1 用上界、s = −1 用下界）
  PL-W 分层周抽签：资格池内「票 × 周」一起留或去，概率 = 候选在该信号所在层（年 × 规模带 × lturn 三分位）的保留比例（demand_study.plw_mask，种子 SEED0 + s）；
  P-S 同周换票：每个信号周在资格池里随机抽与候选该周同样多的信号（demand_study.ps_mask，种子 SEED0 + 2000 + s）。
  区间：按事件周（W-FRI）聚类的自助法 2,000 次（fins_event_study.boot_samples）；(候选 − B_c) 两边独立重抽，取 s × 差 的 2.5 分位。

六 判定（全部写死；s × 差 = 往预期方向的改善）
  S1 s × (胜率 − B_c) ≥ 8 pp；S2 s × (每笔 − B_c) ≥ 1.0 pp 且 s × (候选 − B_c) 的周聚类 95% 区间下限 > 0；S3 笔数 ≥ 300；
  S4 组合不变差（demand_study 同一个组合：S0C2、时点 TOPIX 500（U1），看 J2 = 2022-01〜）：L1 / L2 用「W2 ∧ 标签」、L3 用「W2 ∧ 非标签」替换现行 W2 进场
    （2021-09-01 以前标签未知 → 照现行）：Calmar ≥ 现行 − 0.02 ∧ 回撤不深 2 pp ∧ 个股笔数 ≥ 现行 30%（今天的日経225（U0）只描述）；
  S5 胜率与每笔都往预期方向超过 PL-W 与 P-S 的参数化 99% 界；
  必要条件：(a) 只用提出日 ≤ d − 7 天的报告重算标签 → s × (每笔 − B_c) > 0（不只是公告当天的跳涨）；
    (b) 方向对照：同窗口内「有同类报告、但不是这个候选」的信号（L1：有一般报告；L2：有特例报告；L3：有任何报告）→ s × (候选每笔 − 对照每笔) > 0
       （是买卖方向，不只是「有大股东」）；对照组笔数 < 30 → 不可判定 = 不满足；
    (c) 前后两半 s × (每笔 − B_c) 都 > 0。
  档位：全过 = 「选股成立」→ 提议：加进全市场前向记录（只记录、不交易）+ 另行登记 B3 账户检验（用户确认）；
    只有 S1 / S2 每笔门槛 / S4 不过、且 s × 胜率差 ≥ 4 pp ∧ s × 每笔差 ≥ 0.5 pp ∧ 区间下限 > 0 ∧ S3 ∧ S5 ∧ 必要条件 = 「选股改进（只记录）」；
    s × 每笔差 ≥ 0.5 pp ∧ 区间下限 > 0 ∧ S3 ∧ S5 的每笔 ∧ 必要条件（胜率不要求：S1 与 S5 的胜率都不看）= 「方向成立（只记录）」；其余 = 不成立。
  零假设下（每笔标准误 ≈ 6.0 × 1.5 ÷ √n pp，n ≈ 400 → 0.45 pp）：每个候选到「方向成立」约 1〜2.5%，3 个合起来约 5%；全过 ≤ 1%。

七 前视与数据质量（事先声明）：只用提出日 < d 的报告；J-Quants 是「今天看到的」报告集合（本研究不用订正）；2026-05-01 制度变更
  （那一天的报告不用；之后的报告格式变了 → 2026-05〜06 的标签口径不完全一致，报告的月份分布另报）；全市場 W2 池多是小型股 → 滑点偏乐观；
  决算季同日集中 → 周聚类区间；输出只有统计（var/out/lvs_study.md / .json），没有个别报告、提出者或个股名单。

八 诚实的预期：L1 约 20%、L2 约 10%、L3 约 15% 到「方向成立」以上；全过各 ≤ 5%；3 个都不成立的可能最大（约 60%）。
  不论结果，大量保有这一类信息在这 5 年上一次性判定；L1 / L2 是保留规则（保留比例小）→ S4 的个股笔数条件大概率不过，最多到「选股改进」。非投资建议。

用法：python scripts/lvs_study.py --counts（登记前只数个数，不算任何收益）；python scripts/lvs_study.py --run [--seeds 30] [--procs 4] [--no-portfolio]
"""
from __future__ import annotations

import argparse
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
import demand_study as DS                                                     # noqa: E402
import fins_event_study as FS                                                 # noqa: E402
import lvs_data as LD                                                         # noqa: E402

WIN = ("2021-09-01", "2026-09-25")                  # 末端运行时截到 数据末尾 − END_CUT 个交易日
H1_END, H2_START = "2023-12-29", "2024-01-04"
LOOKBACK_DAYS, ANN_GAP_DAYS, IMP_DAYS = 60, 7, 180
TRANSITION = "2026-05-01"                           # 报告义务发生日 = 这一天的报告不用（制度变更）
END_CUT, SEEDS, SEED0, Q = 61, 30, 20261005, 99.0
MIN_N, MIN_N_OTHER = 300, 30
WIN_UP_PP, MEAN_UP_PP, IMPROVE_WIN_PP, IMPROVE_MEAN_PP, DIR_MEAN_PP = 8.0, 1.0, 4.0, 0.5, 0.5
CALMAR_TOL, DD_TOL_PP, MIN_N_FRAC_PORT = 0.02, 2.0, 0.30
NEW, CHG, GEN, SPC = ("1", "4"), ("2", "3", "5"), ("1", "2", "3"), ("4", "5")
CANDS = {"L1": "一般报告（种别 1 / 2 / 3）的新进或增持 ∧ 最近 60 日有市场内取得", "L2": "特例报告（种别 4 / 5）的新进或增持",
         "L3": "减持 ∧ 最近 60 日有市场内处分（任何种别）→ 否决"}
SIGN = {"L1": 1, "L2": 1, "L3": -1}
OTHER = {"L1": "gen", "L2": "spc", "L3": "any"}     # 必要条件 (b)：同窗口内有这一类报告、但不是这个候选
FLAG_KEYS = ("L1", "L2", "L3", "gen", "spc", "any")
CONTROLS = ("PLW", "PS")
OUT_MD, OUT_JSON = "lvs_study.md", "lvs_study.json"


# ───────────────────────── 报告 → 分类 ─────────────────────────
def classify(T: pd.DataFrame) -> pd.DataFrame:
    """lvs_data 整理后的表 → 只留 350、去掉报告义务发生日 = 2026-05-01 的，加上 up / down / gen / spc / L1〜L3。"""
    o = T[(T["doc_type"] == "350") & (T["rpt_date"].astype(str) != TRANSITION) & T["ticker"].notna()].copy()
    lh = o["lh_type"].astype(str)
    d = o["ratio"].astype(float) - o["ratio_last"].astype(float)
    o["up"] = lh.isin(NEW) | (lh.isin(CHG) & (d > 0))
    o["down"] = lh.isin(CHG) & (d < 0)
    o["gen"] = lh.isin(GEN)
    o["spc"] = lh.isin(SPC)
    o["any"] = True
    o["L1"] = o["gen"] & o["up"] & o["buy_mkt"].astype(bool)
    o["L2"] = o["spc"] & o["up"]
    o["L3"] = o["down"] & o["sell_mkt"].astype(bool)
    o["imp"] = o["imp"].astype(bool)
    o["sub_date"] = pd.to_datetime(o["sub_date"]).dt.normalize()
    return o.sort_values(["ticker", "sub_date"]).reset_index(drop=True)


def window_hits(sub_dates, days, lo_days: int, hi_days: int) -> np.ndarray:
    """每个 d：提出日 ∈ [d − lo_days 天, d − hi_days 天] 的报告个数（sub_dates 升序）。"""
    dd = pd.DatetimeIndex(pd.to_datetime(np.asarray(days)))
    sd = np.sort(np.asarray(pd.to_datetime(np.asarray(sub_dates)), dtype="datetime64[ns]"))
    lo = (dd - pd.Timedelta(days=lo_days)).to_numpy(dtype="datetime64[ns]")
    hi = (dd - pd.Timedelta(days=hi_days)).to_numpy(dtype="datetime64[ns]")
    return np.searchsorted(sd, hi, side="right") - np.searchsorted(sd, lo, side="left")


def signal_flags(F: pd.DataFrame, o: pd.DataFrame) -> pd.DataFrame:
    """F 的每个信号 (票, d) → 标签：[d − 60, d − 1] 内有没有某类报告；后缀 _a = 只用 [d − 60, d − 7]（必要条件 (a)）；
    imp180 = [d − 180, d − 1] 内有重要提案行為等（只描述）。F 要是 RangeIndex。"""
    out = {}
    for k in FLAG_KEYS:
        out[k] = np.zeros(len(F), bool)
        out[k + "_a"] = np.zeros(len(F), bool)
    out["imp180"] = np.zeros(len(F), bool)
    groups = {t: g for t, g in o.groupby("ticker", sort=False)}
    for t, g in F.groupby("ticker", sort=False):
        x = groups.get(t)
        if x is None:
            continue
        days = g["sig_date"].to_numpy()
        idx = g.index.to_numpy()
        for k in FLAG_KEYS:
            sd = x.loc[x[k].to_numpy(bool), "sub_date"].to_numpy()
            if len(sd):
                out[k][idx] = window_hits(sd, days, LOOKBACK_DAYS, 1) > 0
                out[k + "_a"][idx] = window_hits(sd, days, LOOKBACK_DAYS, ANN_GAP_DAYS) > 0
        sd = x.loc[x["imp"].to_numpy(bool), "sub_date"].to_numpy()
        if len(sd):
            out["imp180"][idx] = window_hits(sd, days, IMP_DAYS, 1) > 0
    return pd.DataFrame(out, index=F.index)


def add_flags(F: pd.DataFrame, o: pd.DataFrame) -> pd.DataFrame:
    G = signal_flags(F, o)
    for k in G.columns:
        F["lv_" + k] = G[k].to_numpy(bool)
    return F


def keep(F: pd.DataFrame, cid: str, suffix: str = "") -> np.ndarray:
    """候选标记的信号（资格池内）；suffix = "_a" → 必要条件 (a) 的版本。"""
    return F["P"].to_numpy(bool) & F["lv_" + cid + suffix].to_numpy(bool)


def other(F: pd.DataFrame, cid: str) -> np.ndarray:
    """必要条件 (b) 的对照：同窗口内有同一类报告、但不是这个候选。"""
    return F["P"].to_numpy(bool) & F["lv_" + OTHER[cid]].to_numpy(bool) & ~F["lv_" + cid].to_numpy(bool)


# ───────────────────────── 统计与判定 ─────────────────────────
def _c(x) -> float:
    return float("nan") if x is None else float(x)


def bound(runs: list[dict], s: int, q: float = Q) -> dict:
    """对照各种子的 {win, mean} → 参数化界：s = +1 均值 + t × sd（上界）、s = −1 均值 − t × sd（下界）。"""
    ws = [r["win"] for r in runs if r.get("win") is not None]
    ms = [r["mean"] for r in runs if r.get("mean") is not None]
    if len(ws) < 3 or len(ms) < 3:
        return {"win": None, "mean": None, "seeds": len(ws)}
    k = FS.t_quantile(q / 100, len(ws) - 1)
    return {"win": round(float(np.mean(ws) + s * k * np.std(ws, ddof=1)), 2), "mean": round(float(np.mean(ms) + s * k * np.std(ms, ddof=1)), 3),
            "seeds": len(ws), "q": q, "side": "上界" if s > 0 else "下界"}


def diff_lo(T_c: pd.DataFrame, T_b: pd.DataFrame, win, s: int) -> float | None:
    """s × (候选 − B_c) 每笔均值的周聚类自助法 2.5 分位（两边独立重抽）。"""
    if win is None:
        return None
    a, _ = FS.boot_samples(T_c, win)
    b, _ = FS.boot_samples(T_b, win, seed=FS.SEED0 + 1)
    if not len(a) or not len(b):
        return None
    return round(float(np.percentile(s * (a - b), 2.5)), 3)


def necessary(cid: str, c: dict, base: dict, need: dict) -> list[str]:
    """必要条件 (a)(b)(c)（未满足的列表）。need = {"ann": stats, "other": stats, "halves": {H1: {cand, base}, H2: {cand, base}}}。"""
    s = SIGN[cid]
    out = []
    a = need.get("ann") or {}
    if not s * (_c(a.get("mean")) - _c(base.get("mean"))) > 0:
        out.append(f"(a) 只用提出日 ≤ d − {ANN_GAP_DAYS} 天：每笔 {_c(a.get('mean')):+.2f}% 对 B_c {_c(base.get('mean')):+.2f}% 不往预期方向")
    o = need.get("other") or {}
    if not (o.get("n") or 0) >= MIN_N_OTHER:
        out.append(f"(b) 方向对照笔数 {o.get('n') or 0} < {MIN_N_OTHER}（不可判定）")
    elif not s * (_c(c.get("mean")) - _c(o.get("mean"))) > 0:
        out.append(f"(b) 方向对照（有{OTHER[cid]}报告但不是 {cid}）每笔 {_c(o.get('mean')):+.2f}% 对候选 {_c(c.get('mean')):+.2f}% 不往预期方向")
    for h, v in (need.get("halves") or {}).items():
        if not s * (_c(v["cand"].get("mean")) - _c(v["base"].get("mean"))) > 0:
            out.append(f"(c) {h} 每笔 {_c(v['cand'].get('mean')):+.2f}% 对 B {_c(v['base'].get('mean')):+.2f}% 不往预期方向")
    return out


def s_fails(cid: str, c: dict, base: dict, ctrl_b: dict[str, dict], lo: float | None, port: dict | None, port_base: dict | None, need: dict) -> list[str]:
    s = SIGN[cid]
    m, w, n = _c(c.get("mean")), _c(c.get("win")), _c(c.get("n"))
    dm, dw = s * (m - _c(base.get("mean"))), s * (w - _c(base.get("win")))
    out = []
    if not dw >= WIN_UP_PP:
        out.append(f"S1 往预期方向的胜率差 {dw:+.1f} pp < {WIN_UP_PP:.0f} pp")
    if not dm >= MEAN_UP_PP:
        out.append(f"S2 每笔 往预期方向的差 {dm:+.2f} pp < {MEAN_UP_PP:.1f} pp")
    if lo is None or not lo > 0:
        out.append(f"S2 区间 往预期方向的差 周聚类区间下限 {lo} ≤ 0")
    if not n >= MIN_N:
        out.append(f"S3 笔数 {int(n) if np.isfinite(n) else 0} < {MIN_N}")
    if port is not None and port_base is not None:
        if not _c(port.get("calmar")) >= _c(port_base.get("calmar")) - CALMAR_TOL:
            out.append(f"S4 组合 Calmar {_c(port.get('calmar')):.3f} < 现行 {_c(port_base.get('calmar')):.3f} − {CALMAR_TOL}")
        if not _c(port.get("dd")) >= _c(port_base.get("dd")) - DD_TOL_PP:
            out.append(f"S4 组合回撤 {_c(port.get('dd')):.2f}% 比现行 {_c(port_base.get('dd')):.2f}% 深 {DD_TOL_PP:.0f} pp 以上")
        if not _c(port.get("n")) >= MIN_N_FRAC_PORT * _c(port_base.get("n")):
            out.append(f"S4 组合个股笔数 {port.get('n')} < 现行 {port_base.get('n')} 的 {MIN_N_FRAC_PORT:.0%}")
    for k in CONTROLS:
        q = ctrl_b.get(k) or {}
        if not s * (w - _c(q.get("win"))) > 0:
            out.append(f"S5 胜率 {w:.1f}% 没有超过 {k} 的 99% {q.get('side', '')} {_c(q.get('win')):.1f}%")
        if not s * (m - _c(q.get("mean"))) > 0:
            out.append(f"S5 每笔 {m:+.2f}% 没有超过 {k} 的 99% {q.get('side', '')} {_c(q.get('mean')):+.2f}%")
    out += ["必要条件 " + x for x in necessary(cid, c, base, need)]
    return out


def tier(cid: str, c: dict, base: dict, fails: list[str]) -> str:
    """成立 / 改进 / 方向成立 / 不成立（读法写死；S2 区间、S3、S5、必要条件三档都要；方向成立档的 S5 只看每笔）。"""
    if not fails:
        return "选股成立 → 提议：加进全市场前向记录（只记录）+ 另行登记 B3 账户检验（用户确认）"
    s = SIGN[cid]
    dm, dw = s * (_c(c.get("mean")) - _c(base.get("mean"))), s * (_c(c.get("win")) - _c(base.get("win")))
    others = [f for f in fails if not f.startswith(("S1", "S2 每笔", "S4"))]
    if dw >= IMPROVE_WIN_PP and dm >= IMPROVE_MEAN_PP and not others:
        return "选股改进（只记录）"
    if dm >= DIR_MEAN_PP and not [f for f in others if not f.startswith("S5 胜率")]:      # 方向成立：胜率不要求（S1 与 S5 的胜率都不看）
        return "方向成立（只记录）"
    return "不成立"


# ───────────────────────── 组合（S4） ─────────────────────────
def label_days(sub_dates, days) -> np.ndarray:
    return window_hits(sub_dates, days, LOOKBACK_DAYS, 1) > 0 if sub_dates is not None and len(sub_dates) else np.zeros(len(days), bool)


def port_mask(frames: dict, o: pd.DataFrame, cid: str) -> dict[str, np.ndarray]:
    """组合的进场掩码：s = +1 → 标签、s = −1 → 非标签；2021-09-01 以前（标签未知）→ 照现行（True）。"""
    s = SIGN[cid]
    sd = {t: g.loc[g[cid].to_numpy(bool), "sub_date"].to_numpy() for t, g in o.groupby("ticker", sort=False)}
    start = pd.Timestamp(WIN[0])
    out = {}
    for t, df in frames.items():
        lab = label_days(sd.get(t), df.index.to_numpy())
        rule = lab if s > 0 else ~lab
        out[t] = np.where(df.index >= start, rule, True)
    return out


def portfolio(o: pd.DataFrame, cids: list[str], p, jmem: str = "U1") -> dict:
    """S0C2（demand_study 同一个组合）现行 W2 vs 换成候选规则 → 每个窗口 {cagr, dd, calmar, n, mean, win}。"""
    import leap_confirm as LC
    ctx = LC.context("J", jmem=jmem)
    fr0 = LC.frames(ctx, p)
    run_fn = LC.runner(ctx, fr0)
    base_fr = LC.with_mask(fr0, LC.w2_keep(ctx, fr0))
    out = {"base": LC.run(ctx, run_fn, base_fr, p), "jmem": jmem}
    for cid in cids:
        mask = port_mask(base_fr, o, cid)
        n_ent = sum(int(df["entry"].to_numpy(bool).sum()) for df in base_fr.values())
        n_kept = sum(int((df["entry"].to_numpy(bool) & mask[t]).sum()) for t, df in base_fr.items())
        res = LC.run(ctx, run_fn, LC.with_mask(base_fr, mask), p)
        res["kept_entry_pct"] = round(n_kept / max(n_ent, 1) * 100, 1)
        out[cid] = res
    return out


# ───────────────────────── 登记前：只数个数 ─────────────────────────
def counts(F: pd.DataFrame, o: pd.DataFrame, win: tuple[str, str], halves: dict, n225: set) -> dict:
    """进场前分布（不算任何收益）：各标签在全窗口 / 两半的信号数与比例、规模带、时点 TOPIX 500、今天的日経225、必要条件组的个数、报告的月份分布。"""
    P = F["P"].to_numpy(bool)
    out = {"window": win, "halves": halves}
    for w, (a, b) in {"ALL": win, **halves}.items():
        m = P & FS.in_window(F["sig_date"], (a, b))
        row = {"P": int(m.sum())}
        for k in FLAG_KEYS + tuple(k + "_a" for k in FLAG_KEYS) + ("imp180",):
            x = m & F["lv_" + k].to_numpy(bool)
            row[k] = {"n": int(x.sum()), "pct": round(float(x.sum() / max(m.sum(), 1) * 100), 1)}
        for cid in CANDS:
            k = m & F["lv_" + cid].to_numpy(bool)
            row[cid]["by_band"] = {int(bd): int((k & (F["band"] == bd).to_numpy()).sum()) for bd in (0, 1, 2)}
            row[cid]["u1"] = int((k & (F["u1"] == 1).to_numpy()).sum())
            row[cid]["n225_today"] = int((k & F["ticker"].isin(n225).to_numpy()).sum())
            row[cid]["tickers"] = int(F.loc[k, "ticker"].nunique())
            row[cid]["other_b"] = int((m & other(F, cid)).sum())
        row["L1_and_L3"] = int((m & F["lv_L1"].to_numpy(bool) & F["lv_L3"].to_numpy(bool)).sum())
        row["n225_today_P"] = int((m & F["ticker"].isin(n225).to_numpy()).sum())
        out[w] = row
    oo = o.copy()
    oo["ym"] = oo["sub_date"].dt.strftime("%Y-%m")
    out["filings_by_month_2026"] = {ym: {"n": int(len(g)), "L1": int(g["L1"].sum()), "L2": int(g["L2"].sum()), "L3": int(g["L3"].sum())}
                                    for ym, g in oo[oo["sub_date"] >= "2025-10-01"].groupby("ym")}
    out["filings_by_year"] = {int(y): {"n": int(len(g)), "L1": int(g["L1"].sum()), "L2": int(g["L2"].sum()), "L3": int(g["L3"].sum()),
                                       "gen": int(g["gen"].sum()), "spc": int(g["spc"].sum()), "imp": int(g["imp"].sum())}
                              for y, g in oo.groupby(oo["sub_date"].dt.year)}
    return out


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/lvs_study.py", "scripts/lvs_data.py", "scripts/demand_study.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def n225_today() -> set:
    from qbreak.config import universe
    return set(universe("JP", "broad"))


def _attach(T: pd.DataFrame, F: pd.DataFrame) -> pd.DataFrame:
    """逐笔 → 加上信号的 lv_* 标签（按 票 × 信号日）。"""
    if not len(T):
        return T
    cols = [c for c in F.columns if c.startswith("lv_")]
    key = F.drop_duplicates(subset=["ticker", "sig_date"]).set_index(["ticker", "sig_date"])[cols]
    J = key.reindex(pd.MultiIndex.from_arrays([T["ticker"], T["sig_date"]]))
    for c in cols:
        T[c] = J[c].fillna(False).to_numpy(bool)
    return T


def segments(T: pd.DataFrame, rng_, n225: set) -> dict:
    if not len(T):
        return {}
    seg = {"band0": T["f_band"] == 0, "band1": T["f_band"] == 1, "band2": T["f_band"] == 2, "u1": T["f_u1"] == 1, "n225_today": T["ticker"].isin(n225)}
    return {k: FS.stats(T[v.to_numpy(bool)], rng_) for k, v in seg.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="大量保有報告書 × 全市場 W2 突破（登记版）")
    ap.add_argument("--counts", action="store_true", help="登记前只数个数（不算收益）")
    ap.add_argument("--run", action="store_true", help="正式运行（只运行一次）")
    ap.add_argument("--seeds", type=int, default=SEEDS)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--no-portfolio", action="store_true")
    ap.add_argument("--out-dir", default=None, help="输出目录（缺省 var/out）")
    a = ap.parse_args(argv)
    if not (a.counts or a.run):
        raise SystemExit("要 --counts 或 --run")
    logging.disable(logging.CRITICAL)
    t0 = time.time()
    say = lambda s_: print(s_, flush=True)                                   # noqa: E731
    import allstock_data as AD
    A = AD.load()
    days = pd.DatetimeIndex(A["days"])
    c_end = min(pd.Timestamp(WIN[1]), days[-1 - END_CUT])
    win = (WIN[0], str(c_end.date()))
    halves = {"H1": (WIN[0], H1_END), "H2": (H2_START, win[1])}
    o = classify(LD.load())
    F = DS.load_features()
    F = F[FS.in_window(F["sig_date"], win)].reset_index(drop=True)
    F = add_flags(F, o)
    n225 = n225_today()
    if a.counts:
        print(json.dumps(counts(F, o, win, halves, n225), ensure_ascii=False, indent=1, default=str))
        return 0
    from qbreak.trader import load_params
    P = F["P"].to_numpy(bool)
    say(f"信号 {len(F)}（P {int(P.sum())}）；窗口 {win}；报告 {len(o)}；{time.time() - t0:.0f}s")
    p = load_params(market="JP")
    FS.build_frames(A, p)
    T_full = _attach(DS.trades(F, P, p, a.procs), F)
    say(f"全池 B：{FS.stats(T_full, win)}；{time.time() - t0:.0f}s")
    res: dict = {"git": git_info(), "window": win, "halves": halves, "seeds": a.seeds, "n_signals": int(len(F)), "n_pool": int(P.sum()), "n_filings": int(len(o)),
                 "base_full": FS.stats(T_full, win), "base_halves": {h: FS.stats(T_full, hw) for h, hw in halves.items()}, "cands": {},
                 "counts": counts(F, o, win, halves, n225)}
    for cid in CANDS:
        s = SIGN[cid]
        K = keep(F, cid)
        T_c = _attach(DS.trades(F, K, p, a.procs), F)
        T_x = DS.trades(F, P & ~K, p, a.procs)
        T_a = DS.trades(F, keep(F, cid, "_a"), p, a.procs)
        T_o = DS.trades(F, other(F, cid), p, a.procs)
        rng_ = DS.win_range(F, K, win)
        say(f"{cid}：标记 {int(K.sum())} / P {int(P.sum())}；逐笔 {len(T_c)}；范围 {rng_}；{time.time() - t0:.0f}s")
        runs = {k: [] for k in CONTROLS}
        for i in range(a.seeds):
            masks = {"PLW": DS.plw_mask(F, P, K, SEED0 + i), "PS": DS.ps_mask(F, P, K, SEED0 + 2000 + i)}
            for k, m in masks.items():
                runs[k].append(DS.stats_win(DS.trades(F, m, p, a.procs), rng_))
            if i in (0, 9, 19, a.seeds - 1):
                say(f"  {cid} 对照种子 {i + 1}/{a.seeds}；{time.time() - t0:.0f}s")
        c = DS.stats_win(T_c, rng_)
        base = DS.stats_win(T_full, rng_)
        excl = DS.stats_win(T_x, rng_)
        ctrl_b = {k: bound(v, s) for k, v in runs.items()}
        lo = diff_lo(T_c, T_full, rng_, s)
        need = {"ann": DS.stats_win(T_a, rng_), "other": DS.stats_win(T_o, rng_),
                "halves": {h: {"cand": FS.stats(T_c, hw), "base": FS.stats(T_full, hw)} for h, hw in halves.items()}}
        lag_new = T_c[~T_c["lv_" + cid + "_a"].to_numpy(bool)] if len(T_c) else T_c
        lag_old = T_c[T_c["lv_" + cid + "_a"].to_numpy(bool)] if len(T_c) else T_c
        res["cands"][cid] = {
            "desc": CANDS[cid], "sign": s, "n_flag": int(K.sum()), "eff_range": rng_, "cand": c, "base": base, "excluded": excl,
            "keep_minus_excl": None if c.get("mean") is None or excl.get("mean") is None else round(c["mean"] - excl["mean"], 3),
            "boot": FS.cluster_boot(T_c, rng_) if rng_ else {}, "diff_lower_s": lo, "controls": ctrl_b,
            "control_means": {k: {"win": round(float(np.mean([r["win"] for r in v if r.get("win") is not None] or [np.nan])), 2),
                                  "mean": round(float(np.mean([r["mean"] for r in v if r.get("mean") is not None] or [np.nan])), 3)} for k, v in runs.items()},
            "need": need,
            "segments": {**segments(T_c, rng_, n225), "ann_1_6d": FS.stats(lag_new, rng_), "ann_7_60d": FS.stats(lag_old, rng_),
                         "imp180": FS.stats(T_c[T_c["lv_imp180"].to_numpy(bool)], rng_) if len(T_c) else {"n": 0}},
            "base_segments": segments(T_full, rng_, n225),
            "by_year": {str(y): FS.stats(g) for y, g in T_c.groupby(T_c["sig_date"].dt.year)} if len(T_c) else {},
            "base_by_year": {str(y): FS.stats(g) for y, g in T_full.groupby(T_full["sig_date"].dt.year)} if len(T_full) else {}}
    # 只描述：任何报告、重要提案、L1 ∧ L3
    desc = {}
    for k, m in (("any", F["lv_any"].to_numpy(bool)), ("imp180", F["lv_imp180"].to_numpy(bool)),
                 ("L1_and_L3", F["lv_L1"].to_numpy(bool) & F["lv_L3"].to_numpy(bool))):
        T_d = DS.trades(F, P & m, p, a.procs)
        desc[k] = {"flag": FS.stats(T_d, win), "rest": FS.stats(DS.trades(F, P & ~m, p, a.procs), win)}
    res["describe"] = desc
    if not a.no_portfolio:
        say(f"组合 S4（U1 / U0）；{time.time() - t0:.0f}s")
        res["portfolio"] = {"U1": portfolio(o, list(CANDS), p, "U1"), "U0": portfolio(o, list(CANDS), p, "U0")}
    for cid, rec in res["cands"].items():
        pt = (res.get("portfolio") or {}).get("U1")
        pc = pt[cid]["J2"] if pt else None
        pb = pt["base"]["J2"] if pt else None
        rec["fails"] = s_fails(cid, rec["cand"], rec["base"], rec["controls"], rec["diff_lower_s"], pc, pb, rec["need"])
        rec["tier"] = tier(cid, rec["cand"], rec["base"], rec["fails"])
    res["elapsed_s"] = round(time.time() - t0)
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report(res)
    (out_dir / OUT_MD).write_text(md + "\n", encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md)
    return 0


def _f(s: dict | None) -> str:
    if not s or not s.get("n"):
        return "n=0"
    return f"n={s['n']} 胜率 {s['win']:.1f}% 每笔 {s['mean']:+.2f}%"


def report(res: dict) -> str:
    L = [f"# 大量保有報告書 × 全市場 W2 突破（git {res['git']['rev']}{'（脏）' if res['git'].get('dirty') else ''}；种子 {res['seeds']}；只运行一次）", "",
         f"窗口 {res['window']}（H1 {res['halves']['H1']}、H2 {res['halves']['H2']}）；信号 {res['n_signals']}、P {res['n_pool']}；报告（350、不含 2026-05-01）{res['n_filings']} 份",
         f"全池 B：{_f(res['base_full'])}；H1 {_f(res['base_halves']['H1'])}；H2 {_f(res['base_halves']['H2'])}", ""]
    for cid, r in res["cands"].items():
        L.append(f"## {cid} {r['desc']}（方向 {'保留组更好' if r['sign'] > 0 else '被标记的更差 → 否决'}；标记 {r['n_flag']} 个信号）")
        L.append(f"- 范围 {r['eff_range']}：候选 {_f(r['cand'])}；B_c {_f(r['base'])}；剔除 {_f(r['excluded'])}；保留 − 剔除 {r['keep_minus_excl']} pp")
        L.append(f"- 周聚类区间 {r['boot']}；往预期方向的 (候选 − B_c) 下限 {r['diff_lower_s']} pp")
        L.append("- 对照 99% 界：" + "；".join(f"{k} 胜率 {v.get('win')} 每笔 {v.get('mean')}（{v.get('side', '')}，{v.get('seeds')} 种子；均值 胜率 {r['control_means'][k]['win']} 每笔 {r['control_means'][k]['mean']}）"
                                              for k, v in r["controls"].items()))
        nd = r["need"]
        L.append(f"- 必要条件：(a) {_f(nd['ann'])}；(b) 方向对照 {_f(nd['other'])}；(c) " +
                 "；".join(f"{h} 候选 {_f(v['cand'])} vs B {_f(v['base'])}" for h, v in nd["halves"].items()))
        L.append(f"- 判定：{'全过' if not r['fails'] else '；'.join(r['fails'])} → **{r['tier']}**")
        L.append("- 分段（候选）：" + "；".join(f"{k} {_f(v)}" for k, v in r["segments"].items()))
        L.append("- 分段（B）：" + "；".join(f"{k} {_f(v)}" for k, v in r["base_segments"].items()))
        L.append("- 按年（候选 / B）：" + "；".join(f"{y} {_f(v)} / {_f(r['base_by_year'].get(y))}" for y, v in r["by_year"].items()))
        L.append("")
    L.append("## 只描述（不判定）")
    for k, v in res.get("describe", {}).items():
        L.append(f"- {k}：标记 {_f(v['flag'])}；其余 {_f(v['rest'])}")
    if res.get("portfolio"):
        L.append("")
        L.append("## S4 组合（S0C2；U1 时点 TOPIX 500 判定看 J2、U0 今天的日経225 只描述；L1 / L2 = W2 ∧ 标签、L3 = W2 ∧ 非标签；2021-09 以前照现行）")
        for jm, pt in res["portfolio"].items():
            L.append(f"- {jm} 现行 J2：{pt['base'].get('J2')}")
            for cid in res["cands"]:
                if cid in pt:
                    L.append(f"- {jm} {cid} J2：{pt[cid].get('J2')}（保留的 W2 进场 {pt[cid].get('kept_entry_pct')}%）")
    L.append("")
    L.append(f"进场前分布：{json.dumps(res['counts'], ensure_ascii=False)[:4000]}")
    L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。读法与档位见脚本开头（登记时写定）。非投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
