"""mid_vthrust_study.py — 中型股的突破日量比：在没看过的两个样本上检验一次（2026-09-28 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-28）：「中型股的突破日量比 登记并检验」。
来由：H1（scripts/hx_select_study.py，登记 cdda851）的另报（只描述、不判定）里，美国 S&P 400 中型股（2016 年起）
  「突破日 3 倍量」64 笔 每笔 +1.51% vs 全部突破 +0.56%、「W2 ∧ 3 倍量」39 笔 +2.22% vs W2 +0.52% —— 方向与日本日経225 的 V3 一致，
  但笔数少、没做抽签对照，而且是看过结果才注意到的 → 只能在没看过的样本上检验。
  已知的相关结果（照实写）：日経225 V3（突破日 3 倍量、不加 W2）两个年代每笔 +1.63% / +1.30%（vthrust，登记 09d859a）；
  日経225 以外 666 只 2006〜2016 V3 +0.87% vs 过滤掉 +0.66%（vthrust_wide，事后）；美国 S&P 500 没用过的 398 只 V3 +0.57% vs +0.37%、
  后半 2011〜 +0.07% vs +0.12%（H1，不成立）；日本時点 TOPIX 500 的 2017〜2026 在 S1 / S7 探索里看过量比类特征 → 不再用。
  M2 的已知反面：日経225 的 V1（W2 ∧ 3 倍量）2006〜2016 只有 17 笔 −0.13%；S&P 500（H1）W2 ∧ 3 倍量 103 笔 +0.04%。

一 样本（两个都没用来看过突破日量比）
  A 主判定：美国 S&P 400 今天的成分（var/us_constituents_2026-09.json；去掉以前研究用过的美股 SEEN = US_BROAD ∪ UNIVERSE_US），
    信号日 1995-01-02〜2015-12-31（H1 只算了 2016 年以后）；半段 A1 = 1995〜2005、A2 = 2006〜2015。
    成分与业种是今天的 → **幸存者偏差比 H1 大得多**：400 只里有加入日的 300 只中 283 只是 2016 年以后才加入（240 只 2019 年以后），
    1995 年就有行情的只有 160 只（2006 年 251 只、2015 年 328 只）→ A 大部分是「后来成功、被选进指数的公司」在加入之前的历史
    （H1 用「加入 + 90 天」排除的正是这一段）；变更表 2012 年以前不全、没法按加入日截断。候选与基准同样有这个偏差，
    但「放量急涨后失败、退市」的票不在样本里 → 对 V3 偏乐观；B 也是今天的成分 →「A 过 ∧ B 同号」分不开偏差与真效果 →
    G3 另加「同一只票里抽签」（控制「哪些票」的选择效应）。SEEN 在 S&P 400 里去掉 0 只。
  B 同号检查：日本 T500x（TOPIX 500 里日経225 以外、已剔除航空 / 陆运 / 仓储物流；var/universe_wide.json，今天的成分，yfinance 27 年），
    Z 窗口 信号日 2001-01-04〜2006-09-30（Z 只用过日経225 的组合确认，扩大池从没在 Z 用过；日経225 的 K2 在 Z 看过 →「放量」在 Z
    有效是已知的，照实写）；半段 2001〜2003 / 2004〜2006-09。
  另报（只描述）：日本 S1x（TOPIX Small 1 里日経225 以外）同一 Z 窗口。
  数据清洗（审计发现，登记前）：Yahoo 的日本个股 2001〜2006 有「休市日 / 缺数据日」的假行（成交量 0、开高低收 = 前一天收盘；
    Z 各年占 T500x 行数的 4.8〜7.5%，2007〜2016 ≤ 0.8%）→ 会让 20 日均量偏小（vr1 虚高）、在假行上按旧收盘成交（绕过 3% 跳空过滤）。
    → 两个样本都把「成交量 ≤ 0」的行整行去掉（美国也有少量）；不用 qbreak/calendar_jp（它按今天的祝日规则，2001〜2006 的天皇诞生日、
    海の日、敬老の日、山の日都不对）。去掉的行数照报。
  登记前核对（只有笔数，没看任何收益；去掉成交量 ≤ 0 的行之后）：A 399 只、窗口内去掉 6,377 / 1,297,516 行（0.5%）、P 1,131 笔
    （A1 617 / A2 514；数据检查剔除 0）；W2 527、M1 250（149 / 101）、M2 133（74 / 59）、M3 610（352 / 258）；
    B 247 只、窗口内去掉 17,057 / 277,683 行（6.1%）、P 275 笔（90 / 185；去掉假行之前是 390 笔 → 假行造出了约 115 笔交易）；
    W2 133、M1 47（17 / 30）、M2 22（9 / 13）、M3 142（50 / 92）；vr1、w5v 缺值 0%。
    → G5 的门槛（全窗口 ≥ 100、每半 ≥ 30；B ≥ 20）按第一次核对写定，去掉假行后仍都满足（B 的 M2 只剩 22 笔）。
二 交易：同 H1 —— 现行日本突破规则原样去掉 W2（score_forward.no_w2_params(load_params(market="JP"))），每只票单独、一次一仓
  （qbreak.engine.run_backtest；A 用美股执行设定、B 用日股执行设定；手续费清零后按来回 0.15% 扣，只为可比；
  引擎的毛收益已含滑点（美股每边 0.05%、日股每边 0.10%）→ 来回合计约 0.25% / 0.35%；A、B 都没有决算日 → 不做决算前不进场）；
  持仓到数据末尾没平仓的不算；信号日前 5 天到平仓日有单日 |涨跌| > 60% 的剔除（hx_select_study.bad_move_flags；用到了之后的价格路径 →
  候选与基准各剔除几笔分开报）。P = 剩下的全部。
  行情一直算到今天，但只统计信号日落在上面窗口里的交易（窗口之后的交易不输出、不看）。
三 特征（信号日收盘为止已知）：vr1 突破日量比 = 当天成交量 ÷ 之前 20 天平均（idio_forward.vr1_series，同 H1 / K2）；
  w5v 周线量比（mtf.weekly_volume_ratio，W2 同一定义；缺值 → W2 保留，同现行）；vr1 缺值 → 条件不满足。
四 候选（阈值 = 日本 / H1 原样）
  M1 突破日 3 倍量：vr1 ≥ 3.0（不加 W2）。基准 = P。
  M2 W2 ∧ 突破日 3 倍量：w5v ≥ 1.0 ∧ vr1 ≥ 3.0。基准 = W2 保留组（= 现行规则）。
  M3 突破日 2 倍量：vr1 ≥ 2.0（不加 W2）。基准 = P。
五 判定（每个候选分别）
  A（主）：G1 每笔净收益 全窗口 候选 − 基准 ≥ +0.5 pp，且 A1、A2 各自 > 0；G2 胜率 全窗口与两半都 ≥ 基准；
    G3 全窗口的每笔与胜率都 > 三种抽签对照的 95 分位（基准里按「年 × GICS 业种」「同一周」「同一只票」分层随机保留与候选同样的笔数，
    各 1,000 次；每种另报「整层都是候选、每次必被抽中」的候选占比）；
    G4 (候选 − 基准) 每笔按季度聚类的自助法（2,000 次；持有最长约 60 个交易日，按月聚类会低估误差）95% 区间下限 > 0；
    G5 笔数：全窗口 ≥ 100、每半 ≥ 30。
  B（同号）：全窗口 候选 − 基准 每笔 > 0 且 胜率 ≥ 基准，且候选 ≥ 20 笔。
  成立 = A 全过 ∧ B 同号。成立 → 提议（用户确认才改任何东西）：① 中型股的突破日量比前向记录（只记录不交易，用户同意再登记）；
  ② 要真的交易中型股，执行器要扩大股票池（行情、一手金额、下单）——是另一个决定，先要做组合层的检验（S0C2 + 中型股）。
  不成立 → 只记录；模拟盘 / 执行器 / W2 / 股票池都不变。
六 另报（只描述）：两半与按年的每笔；vr1 与「赢」的 AUC；vr1 分档（< 1.5、1.5〜2、2〜3、≥ 3）的每笔；B 的 S1x。
七 事前预期（写死）：A 上 M1 全过约 12%（H1 大型股同一规则 +0.20 pp、后半消失；S&P 400 的 +0.95 pp 是事后看到的，一般会缩水；
  同一只票抽签更难过）；
  M2 约 10%（笔数最少）；M3 约 10%（日本与 H1 的 2 倍量都只有 +0.1 pp 左右）；B 同号约 60%（日経225 的放量在 Z 有效）；
  三个都不成立约 78%。检出力：M1 约 250 笔、每笔标准差约 7% 时 (候选 − 基准) 的标准误约 0.4〜0.45 pp（按季度聚类更大）→ 约 +1 pp 以上的效果才有机会过 G4；
  M2 约 130 笔 → 约 +1.3 pp；B 的同号检查（M1 47 笔、M2 22 笔）只看方向，偶然同号的概率接近一半。
八 局限：今天的成分（幸存者偏差，见一）；GICS / 東証 33 业种是今天的分类；突破规则是为日本调的；美股没有决算日数据 → 不做决算前不进场；
  B 的 yfinance 2001〜2006 日本中型股数据有假行（已去掉，见一）与其他缺漏；单只单独交易 ≠ 组合里的交易（名额、资金不受限）。
  顺带发现（不属于这一轮）：以前 Z 窗口的研究（例 S6 的 K2 在日経225 的 Z 确认）用的同一份 yfinance 行情也有这些假行 → 量比类的 Z 结果
  可能偏乐观，记在 sim_changes.md，另行核对。
输出：var/out/mid_vthrust_study.md / .json（只有统计）
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
import hx_select_study as HX                                                 # noqa: E402
import us_stock_data as UD                                                   # noqa: E402
from qbreak import paths                                                     # noqa: E402

WIN = {"A": (pd.Timestamp("1995-01-02"), pd.Timestamp("2015-12-31"), pd.Timestamp("2006-01-01")),
       "B": (pd.Timestamp("2001-01-04"), pd.Timestamp("2006-09-30"), pd.Timestamp("2004-01-01")),
       "S1x": (pd.Timestamp("2001-01-04"), pd.Timestamp("2006-09-30"), pd.Timestamp("2004-01-01"))}
HALF_NAME = {"A": ("A1 1995〜2005", "A2 2006〜2015"), "B": ("2001〜2003", "2004〜2006-09"), "S1x": ("2001〜2003", "2004〜2006-09")}
RT_PCT = HX.RT_PCT
W2_CUT, V3_VR, V2_VR = 1.0, 3.0, 2.0
G1_PP, MIN_A, MIN_HALF, MIN_B = 0.5, 100, 30, 20
Q = 95
CANDS = {"M1": "突破日 3 倍量（vr1 ≥ 3.0，不加 W2）", "M2": "W2 ∧ 突破日 3 倍量", "M3": "突破日 2 倍量（vr1 ≥ 2.0，不加 W2）"}
BASE_OF = {"M1": "P", "M2": "W2", "M3": "P"}
VR_BINS = [(-np.inf, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, np.inf)]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def _f(s: dict) -> str:
    return HX._f(s)


# ───────────────────────── 数据 ─────────────────────────
def clean(raw: dict[str, pd.DataFrame], sector: dict[str, str], key: str) -> tuple[dict[str, pd.DataFrame], dict]:
    """去掉成交量 ≤ 0（或缺值）的行（Yahoo 的休市假行 / 停牌，头部一）；返回 (行情, {窗口内的行数, 去掉的行数})。"""
    w0, w1, _ = WIN[key]
    data, rows, dropped = {}, 0, 0
    for t, df in raw.items():
        if t not in sector:
            continue
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        ok = (df["Volume"] > 0).to_numpy()
        inw = ((df.index >= w0) & (df.index <= w1))
        rows += int(inw.sum())
        dropped += int((inw & ~ok).sum())
        df = df[ok]
        if len(df) >= 300:
            data[t] = df
    return data, {"rows_window": rows, "dropped_window": dropped}


def us_pool() -> dict:
    """A：今天的 S&P 400 去掉 SEEN → {data, sector, market, clean}。"""
    seen = HX.seen_names()
    c = UD.constituents()
    names = [t for t in UD.names("sp400") if t not in seen]
    sector = {r["ticker"]: r["sector"] for r in c["sp400"]}
    data, cl = clean(UD.ohlcv(names), sector, "A")
    return {"data": data, "sector": {t: sector[t] for t in data}, "market": "US", "years": UD.YEARS, "clean": cl,
            "n_seen_removed": sum(1 for t in UD.names("sp400") if t in seen)}


def jp_pool(seg: str = "T500x") -> dict:
    """B：日本 T500x（或 S1x）今天的成分 → {data, sector, market, clean}。"""
    import leap_data as LD
    from qbreak import wide_universe as WU
    doc = WU.load()
    s33 = {f"{x['code']}.T": x["s33"] for x in doc["segments"][seg]}
    data, cl = clean(LD.ohlcv(list(s33)), s33, "B" if seg == "T500x" else "S1x")
    return {"data": data, "sector": {t: s33[t] for t in data}, "market": "JP", "years": LD.YEARS, "clean": cl}


def base_params():
    return HX.base_params()


def trades(D: dict, p0, w0: pd.Timestamp, w1: pd.Timestamp) -> pd.DataFrame:
    """每只票单独、一次一仓；只留信号日在 [w0, w1] 的已平仓交易。"""
    from qbreak.config import BacktestConfig
    from qbreak.engine import run_backtest
    from qbreak.strategy import compute_indicators
    bt = BacktestConfig.for_market(D["market"], D["years"])
    ex = bt.exec_cfg
    ex.commission_pct, ex.commission_min, ex.commission_max, ex.commission_tiers = 0.0, 0.0, 0.0, ()   # 手续费另外按 RT_PCT 扣
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    cols = ["ticker", "sig_date", "entry_date", "exit_date", "ret_pct", "reason"]
    rows = []
    for t, df in D["data"].items():
        ind = compute_indicators(df, p0, None)
        if not ind["entry"].any():
            continue
        try:
            r = run_backtest({t: ind}, p0, bt, start=w0)
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
        rows.append(tr[cols])
    T = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)
    T = T[(T["sig_date"] >= w0) & (T["sig_date"] <= w1)].reset_index(drop=True)
    T["net"] = T["ret_pct"].astype(float) - RT_PCT
    T["win"] = T["net"] > 0
    return T


def attach(T: pd.DataFrame, D: dict) -> pd.DataFrame:
    """vr1、w5v、业种、年、周、月。"""
    from qbreak import idio_forward as IF
    from qbreak import mtf
    T = T.copy()
    vr1, w5v = np.full(len(T), np.nan), np.full(len(T), np.nan)
    for t, g in T.groupby("ticker"):
        df = D["data"][t]
        sd = pd.DatetimeIndex(g["sig_date"])
        vr1[g.index] = IF.vr1_series(df).reindex(sd).to_numpy(float)
        w5v[g.index] = mtf.weekly_volume_ratio(df, df.index).reindex(sd).to_numpy(float)
    T["vr1"], T["w5v"] = vr1, w5v
    T["sector"] = [D["sector"][t] for t in T["ticker"]]
    T["year"] = T["sig_date"].dt.year
    T["week"] = T["sig_date"].dt.to_period("W-FRI").astype(str)
    T["month"] = T["sig_date"].dt.to_period("M").astype(str)
    return T


def keep_masks(T: pd.DataFrame) -> dict[str, np.ndarray]:
    v = np.nan_to_num(T["vr1"].to_numpy(float), nan=-np.inf)
    W2 = ~(T["w5v"].to_numpy(float) < W2_CUT)                                   # 缺值 → 保留（同现行）
    return {"P": np.ones(len(T), bool), "W2": W2, "M1": v >= V3_VR, "M2": W2 & (v >= V3_VR), "M3": v >= V2_VR}


def build(D: dict, p0, key: str) -> tuple[pd.DataFrame, dict, dict]:
    t0 = time.time()
    w0, w1, _ = WIN[key]
    T = attach(trades(D, p0, w0, w1), D)
    bad = HX.bad_move_flags(T, D)
    M0 = keep_masks(T)
    info = {"sample": key, "n_names": len(D["data"]), "n_trades_raw": int(len(T)), "n_bad": int(bad.sum()),
            "n_bad_by": {k: int((bad & M0[k]).sum()) for k in ("P", "W2") + tuple(CANDS)}, **D.get("clean", {})}
    T = T[~bad].reset_index(drop=True)
    info["secs"] = round(time.time() - t0)
    return T, keep_masks(T), info


# ───────────────────────── 判定 ─────────────────────────
def always_drawn(base: np.ndarray, keep: np.ndarray, strata: np.ndarray) -> float | None:
    """候选里有多少落在「整层都是候选」的层（抽签时每次必被抽中）。"""
    bi = np.flatnonzero(base)
    kp = keep[bi]
    if not kp.any():
        return None
    _, inv = np.unique(strata[bi], return_inverse=True)
    nb, nk = np.bincount(inv), np.bincount(inv, weights=kp.astype(float))
    full = (nk == nb) & (nk > 0)
    return round(float(kp[full[inv]].sum() / kp.sum()), 3)


def boot_q(T: pd.DataFrame, base: np.ndarray, keep: np.ndarray) -> float | None:
    """(候选 − 基准) 每笔、按信号日所在季度聚类的自助法 2.5% 分位（hx_select_study.boot_diff_lo，聚类键换成季度）。"""
    Tq = pd.DataFrame({"net": T["net"].to_numpy(float), "month": T["sig_date"].dt.to_period("Q").astype(str).to_numpy()})
    return HX.boot_diff_lo(Tq, base, keep)


def gate_a(T: pd.DataFrame, M: dict, cid: str) -> dict:
    """主判定 G1〜G5（头部五）。"""
    base, keep = M[BASE_OF[cid]], M[cid]
    h1 = (T["sig_date"] < WIN["A"][2]).to_numpy()
    res = {"base": BASE_OF[cid], "all": {"cand": HX.stats(T, keep), "base": HX.stats(T, base), "excl": HX.stats(T, base & ~keep)}}
    for h, hm in (("h1", h1), ("h2", ~h1)):
        res[h] = {"cand": HX.stats(T, keep & hm), "base": HX.stats(T, base & hm)}
    strata = {"年×业种": (T["year"].astype(str) + "|" + T["sector"]).to_numpy(), "同周": T["week"].to_numpy(), "同一只票": T["ticker"].to_numpy()}
    lot = {k: HX.lottery(T, base, keep, st, seed=HX.SEED + i) for i, (k, st) in enumerate(strata.items())}
    res["lottery_q"] = {k: {"mean": float(np.nanpercentile(v["mean"], Q)), "win": float(np.nanpercentile(v["win"], Q))} for k, v in lot.items()}
    res["always_drawn"] = {k: always_drawn(base, keep, st) for k, st in strata.items()}
    res["diff_lo"] = boot_q(T, base, keep)
    c, b = res["all"]["cand"], res["all"]["base"]
    nan = float("nan")
    fails = []
    if not (c["n"] and b["n"] and c["mean"] >= b["mean"] + G1_PP):
        fails.append(f"G1 全窗口每笔 {c['mean'] if c['n'] else nan:+.2f}% < 基准 {b['mean'] if b['n'] else nan:+.2f}% + {G1_PP} pp")
    if not (c["n"] and b["n"] and c["win"] >= b["win"]):
        fails.append(f"G2 全窗口胜率 {c['win'] if c['n'] else nan:.1f}% < 基准 {b['win'] if b['n'] else nan:.1f}%")
    if not c["n"] >= MIN_A:
        fails.append(f"G5 全窗口笔数 {c['n']} < {MIN_A}")
    for h, nm in zip(("h1", "h2"), HALF_NAME["A"]):
        a, bb = res[h]["cand"], res[h]["base"]
        if not (a["n"] and bb["n"] and a["mean"] > bb["mean"]):
            fails.append(f"G1 {nm} 每笔 {a['mean'] if a['n'] else nan:+.2f}% 不高于基准 {bb['mean'] if bb['n'] else nan:+.2f}%")
        if not (a["n"] and bb["n"] and a["win"] >= bb["win"]):
            fails.append(f"G2 {nm} 胜率 {a['win'] if a['n'] else nan:.1f}% < 基准 {bb['win'] if bb['n'] else nan:.1f}%")
        if not a["n"] >= MIN_HALF:
            fails.append(f"G5 {nm} 笔数 {a['n']} < {MIN_HALF}")
    for k, q in res["lottery_q"].items():
        if not (c["n"] and c["mean"] > q["mean"]):
            fails.append(f"G3 每笔 ≤ {k}抽签 {Q} 分位 {q['mean']:+.2f}%")
        if not (c["n"] and c["win"] > q["win"]):
            fails.append(f"G3 胜率 ≤ {k}抽签 {Q} 分位 {q['win']:.1f}%")
    if not (res["diff_lo"] is not None and res["diff_lo"] > 0):
        fails.append(f"G4 (候选 − 基准) 按季度聚类 95% 下限 {res['diff_lo'] if res['diff_lo'] is not None else nan:+.2f} pp ≤ 0")
    res["fails"] = fails
    res["pass"] = not fails
    return res


def sign_b(T: pd.DataFrame, M: dict, cid: str, key: str = "B") -> dict:
    """同号检查（头部五 B）。"""
    base, keep = M[BASE_OF[cid]], M[cid]
    h1 = (T["sig_date"] < WIN[key][2]).to_numpy()
    c, b = HX.stats(T, keep), HX.stats(T, base)
    res = {"base": BASE_OF[cid], "all": {"cand": c, "base": b, "excl": HX.stats(T, base & ~keep)},
           "h1": {"cand": HX.stats(T, keep & h1), "base": HX.stats(T, base & h1)},
           "h2": {"cand": HX.stats(T, keep & ~h1), "base": HX.stats(T, base & ~h1)}}
    fails = []
    if not (c["n"] >= MIN_B):
        fails.append(f"笔数 {c['n']} < {MIN_B}")
    if not (c["n"] and b["n"] and c["mean"] > b["mean"]):
        fails.append(f"每笔 {c['mean'] if c['n'] else float('nan'):+.2f}% 不高于基准 {b['mean'] if b['n'] else float('nan'):+.2f}%")
    if not (c["n"] and b["n"] and c["win"] >= b["win"]):
        fails.append(f"胜率 {c['win'] if c['n'] else float('nan'):.1f}% < 基准 {b['win'] if b['n'] else float('nan'):.1f}%")
    res["fails"] = fails
    res["pass"] = not fails
    return res


def describe(T: pd.DataFrame, M: dict) -> dict:
    """vr1 分档、vr1 与赢的 AUC、按年（P / W2 / M1 / M2 每笔）。"""
    v = T["vr1"].to_numpy(float)
    out = {"bins": {}, "auc_vr1": HX.auc(v, T["win"].to_numpy()), "by_year": {}}
    for lo, hi in VR_BINS:
        m = (v >= lo) & (v < hi)
        out["bins"][f"{lo:g}〜{hi:g}"] = {"P": HX.stats(T, m), "W2": HX.stats(T, m & M["W2"])}
    for yr, g in T.groupby("year"):
        m = np.zeros(len(T), bool)
        m[g.index.to_numpy()] = True
        out["by_year"][int(yr)] = {k: HX.stats(T, m & M[k]) for k in ("P", "W2", "M1", "M2")}
    return out


def git_info() -> dict:
    root = paths.PROJECT_ROOT
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "scripts", "qbreak"],
                                    capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return {"rev": rev, "dirty": dirty}


def counts(T: pd.DataFrame, M: dict, key: str, info: dict) -> None:
    """登记前核对：只报笔数与缺值（不看收益）。"""
    h1 = (T["sig_date"] < WIN[key][2]).to_numpy()
    print(f"{key}：{info['n_names']} 只；窗口内 {info.get('rows_window')} 行、去掉成交量 ≤ 0 的 {info.get('dropped_window')} 行；交易 {info['n_trades_raw']}，"
          f"剔除 {info['n_bad']}（{info['n_bad_by']}）；P {len(T)}（{HALF_NAME[key][0]} {int(h1.sum())} / "
          f"{HALF_NAME[key][1]} {int((~h1).sum())}）；缺值 vr1 {T['vr1'].isna().mean() * 100:.1f}%、w5v {T['w5v'].isna().mean() * 100:.1f}%")
    for k in ("W2",) + tuple(CANDS):
        m = M[k]
        print(f"  {k}：保留 {int(m.sum())}（{m.mean() * 100:.1f}%；{int((m & h1).sum())} / {int((m & ~h1).sum())}）")


def show_block(title: str, g: dict, halves: tuple[str, str]) -> None:
    say(f"- 全窗口：候选 {_f(g['all']['cand'])}；基准 {_f(g['all']['base'])}；剔除 {_f(g['all']['excl'])}")
    say(f"- {halves[0]}：候选 {_f(g['h1']['cand'])}；基准 {_f(g['h1']['base'])}")
    say(f"- {halves[1]}：候选 {_f(g['h2']['cand'])}；基准 {_f(g['h2']['base'])}")
    if "lottery_q" in g:
        say("- 抽签对照 95 分位：" + "；".join(f"{k} 每笔 {v['mean']:+.2f}% 胜率 {v['win']:.1f}%" for k, v in g["lottery_q"].items())
            + "（候选里每次必被抽中的比例：" + "、".join(f"{k} {v * 100:.0f}%" if v is not None else f"{k} —" for k, v in g["always_drawn"].items()) + "）")
        say(f"- (候选 − 基准) 按季度聚类 95% 下限 {g['diff_lo'] if g['diff_lo'] is not None else float('nan'):+.2f} pp")
    say(f"- {title}：{'过' if g['pass'] else '不过：' + '；'.join(g['fails'])}")


def show_describe(ds: dict) -> None:
    say("突破日量比分档（P / W2 保留组）：" + "；".join(f"{k} {_f(v['P'])} / {_f(v['W2'])}" for k, v in ds["bins"].items()))
    say(f"vr1 与「赢」的 AUC：{ds['auc_vr1']:.3f}" if ds["auc_vr1"] is not None else "vr1 与「赢」的 AUC：—")
    say("按年（P / W2 / M1 / M2 每笔）：" + "；".join(
        f"{y} {v['P']['n']}笔 " + " / ".join(f"{v[k]['mean'] if v[k]['n'] else 0:+.2f}%" for k in ("P", "W2", "M1", "M2"))
        for y, v in ds["by_year"].items()))


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "mid_vthrust_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true", help="登记前核对：只报笔数、保留比例与缺值（不看收益）")
    a = ap.parse_args()
    t0 = time.time()
    gi = git_info()
    p0 = base_params()
    DA, DB = us_pool(), jp_pool("T500x")
    TA, MA, IA = build(DA, p0, "A")
    TB, MB, IB = build(DB, p0, "B")
    if a.counts:
        counts(TA, MA, "A", IA)
        counts(TB, MB, "B", IB)
        return 0
    say(f"# 中型股的突破日量比（{pd.Timestamp.today().date()}；git {gi['rev']}{'（脏）' if gi['dirty'] else ''}）")
    say("规则见 scripts/mid_vthrust_study.py 开头（先提交后运行）。各格：笔数 / 胜率 / 每笔净收益（来回 0.15% 已扣）。")
    say(f"\n## A 主判定：美国 S&P 400（去掉 SEEN {DA['n_seen_removed']} 只）{IA['n_names']} 只，信号日 1995〜2015：窗口内去掉成交量 ≤ 0 的 "
        f"{IA['dropped_window']} / {IA['rows_window']} 行；交易 {IA['n_trades_raw']} 笔，数据检查剔除 {IA['n_bad']}（{IA['n_bad_by']}）→ P {len(TA)} 笔；{IA['secs']}s")
    say(f"- P：{_f(HX.stats(TA, MA['P']))}；W2：{_f(HX.stats(TA, MA['W2']))}")
    say(f"\n## B 同号检查：日本 T500x {IB['n_names']} 只，Z 窗口 2001-01〜2006-09：窗口内去掉成交量 ≤ 0 的 {IB['dropped_window']} / {IB['rows_window']} 行；"
        f"交易 {IB['n_trades_raw']} 笔，数据检查剔除 {IB['n_bad']}（{IB['n_bad_by']}）→ P {len(TB)} 笔；{IB['secs']}s")
    say(f"- P：{_f(HX.stats(TB, MB['P']))}；W2：{_f(HX.stats(TB, MB['W2']))}")
    res = {"git": gi, "A": {**IA, "gates": {}}, "B": {**IB, "signs": {}}}
    for cid in CANDS:
        ga, sb = gate_a(TA, MA, cid), sign_b(TB, MB, cid)
        res["A"]["gates"][cid], res["B"]["signs"][cid] = ga, sb
        ok = ga["pass"] and sb["pass"]
        res.setdefault("verdict", {})[cid] = ok
        say(f"\n### {cid} {CANDS[cid]}（基准 = {'全部突破 P' if BASE_OF[cid] == 'P' else 'W2 保留组（现行）'}）")
        say("A 美国 S&P 400 1995〜2015：")
        show_block("A 判定 G1〜G5", ga, HALF_NAME["A"])
        say("B 日本 T500x Z 2001〜2006：")
        show_block("B 同号", sb, HALF_NAME["B"])
        say(f"- **{cid}：{'成立（A 全过 ∧ B 同号）' if ok else '不成立'}**")
    write_out(res)                                                           # 判定先写（另报出错也不丢）
    res["A"]["describe"], res["B"]["describe"] = describe(TA, MA), describe(TB, MB)
    say("\n## 另报（只描述）")
    say("A 美国 S&P 400 1995〜2015：")
    show_describe(res["A"]["describe"])
    say("B 日本 T500x Z：")
    show_describe(res["B"]["describe"])
    DS = jp_pool("S1x")
    TS, MS, IS = build(DS, p0, "S1x")
    res["S1x"] = {**IS, "cands": {cid: {"cand": HX.stats(TS, MS[cid]), "base": HX.stats(TS, MS[BASE_OF[cid]])} for cid in CANDS}}
    say(f"日本 S1x（TOPIX Small 1 里日経225 以外）{IS['n_names']} 只，Z：P {len(TS)} 笔 " + "；".join(
        f"{cid} {_f(v['cand'])} vs 基准 {_f(v['base'])}" for cid, v in res["S1x"]["cands"].items()))
    passed = [c for c in CANDS if res["verdict"][c]]
    say("\n## 结论（事先规则）")
    if passed:
        say(f"- 成立：{', '.join(passed)} → 提议（用户确认才做）：中型股的突破日量比前向记录（只记录不交易）；要交易中型股先做组合层检验并扩大执行器股票池。")
    else:
        say("- 没有候选成立 → 只记录；模拟盘 / 执行器 / W2 / 股票池都不变。")
    res["passed"] = passed
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
