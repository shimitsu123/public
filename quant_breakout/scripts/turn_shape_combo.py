"""turn_shape_combo.py — 「上述日 / 周 / 月线（起涨 / 起跌点模型）结合现在模型（B3）的买卖点会更好么」（登记版：规则、代码与登记前个数一起提交，
之后不改、只运行一次）。

来由：用户 2026-10-05「上述日周月线结合现在模型的买卖点会更好么」—— 接〔67〕的三个研究（scripts/turn_shape_study.py、turn_shape_wide.py、
turn_shape_mtf.py：「像起涨点 / 像起跌点」的分数在全市场的横截面上事前用不了，周 / 月线的上涨模型方向还相反）。那三个研究比的是
「全部股票、每 5 天一个样本日」，**没有放到现在的买卖点上（日経225 的 W2 突破 + C、X6 离场、4 个名额）比过** → 这次直接比。
以前相关的（结论都是不改）：多周期 R1（scripts/mtf_study.py：周线 Stage 2 / 周 RSI / 三周期共振当买点过滤两期方向相反，周 / 月线见顶特征当卖点
几乎不改变结果）、当天的分钟 / 周 / 月线过滤（exec_timing_study）、周 / 月线乖离卖点（madev_study）、K 线形态（candle_*）、
W2 × 日 / 周 / 月线的量 59 种（w2mtf_study）、第九〜十一个研究循环（选股闸门 / 卖法 51 个做法都没过）。

〇 基准 B3（同第九〜十一个循环：模拟盘 / 执行器现在的规则；scripts/loop6_common.load3 + run；¥100 万、立花费用、一手按当时真实股价；
   日経225 突破 + W2 + C（留一年代）、4 × 25%；离场 X6 = 收盘 < 持有以来最高价 − 3 × ATR14，另有止损 / 跟踪 / 止盈 / 放量阴线 / 最长 60 天；
   闲置资金 Q1B；Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09-30）。
   先决条件：模拟盘规则指纹 = 3b2e8757be7b4a74；重算的 B3 与第十个循环登记的基准（var/research_loop10.json baseline）逐个年代 Calmar 差 ≤ 0.0005。

一 评分模型（冻结，不重新挑）：日线尺度 = turn_shape_wide 的 U2 模型（登记 2757571）、周线 / 月线尺度 = turn_shape_mtf 的模型（登记 de4b60c）
   —— 就是用户看的「三种尺度」那一页。参数没有存在结果文件里（只存了前 12 个系数）→ 用登记的代码在同一份缓存上重拟合（同一段代码、确定性的），
   先决条件：重拟合的前 12 个系数与结果文件逐个相同（4 位小数）、拟合用的行数相同；另核对「宽表打分」与「样本表打分」在样本行上相同（接线核对）。
   分数 = 46 个特征（同 turn_shape_study：日线 18 / 周线 14 / 月线 11 / σ / log 时价总额 / 12-1 动量）按探索期 1% / 99% 截尾 + 标准化
   × 系数 + 截距（σ 用向前填补口径，同 U2 / 周 / 月线模型）。**log 时价总额一律当缺值（标准化后 = 0）**：日経225（Z / E）、扩大池的 yfinance
   行情没有时价总额，各样本同一口径 → 分数只来自图形、波动与动量。**只在 45 个特征（除 log 时价总额）都算得出的票、日子上打分**
   （J / Jx 的行情 2016-09 起 → 月线特征约 2017-12 之后才齐；Z 2001 年初、E 2006 年底前也有几个月不齐 → 那些日子不挡、不卖 = 照 B3）。
   「最像」= 那一天在本样本可交易的票（分数算得出的）里按分数排百分位 > 90%（最像的 1 / 10；同 turn_shape 研究的「最高一组」）：
     日経225（Z / E / J）= 今天的日経225（同 B3 的股票池）；W = 扩大池 714 只；Jx = 那一天的时点 TOPIX 1000 成员里非日経225；
     Zx = 扩大池里非日経225（Z 年代）。
   照实写：评分模型的训练期是 2017-10〜2021-12（全市场，标注用了之后的价格）→ J 的前一半（2017〜2021）与 Jx 的同一段对评分模型是样本内；
   Z / E / W / Zx 与 J 的后一半（2022-01〜）是评分模型没见过的。

二 四个做法（ID 以前没用过；都是看过〔67〕三个研究的结果之后设计 → 都按「事后」处理，V6 适用）：
   买点（「不开新仓」：那个（票, 信号日）em_tick 0，名额留给下一个候选、钱留在核心；同第九 / 十个循环的挡法）：
   - TBF「像起跌点就不买」：信号日日 / 周 / 月线三个尺度的下跌模型里，至少两个是「最像」。
   - TBR「周 / 月线像起涨点（大周期还在跌）就不买」：信号日周线或月线尺度的上涨模型是「最像」（〔67〕周 / 月线结果「最像起涨点的票之后反而跑输」）。
   卖点（在 X6 之上再加一个离场：拿着的日本个股在「事件日」收盘后 → 第二天开盘卖；candle_portfolio.run 的 exit_tick；
        事件日 = 条件今天成立、前一个交易日不成立 =「变得像」，所以买进时已经像的不会一买就卖）：
   - TXF「变得像起跌点就卖」：条件同 TBF（三个尺度里至少两个「最像」）。
   - TXR「周 / 月线变得像起涨点就卖」：条件同 TBR。
   条件的写法（两个尺度以上 / 周或月）在数个数之前写定，没有按个数改。

三 第一关（同第十一个循环 scripts/research_loop11.stage1：两条路线，过任一条就算；posthoc = True）：
   路线 A「账户」：A1 三个年代 Calmar 差合计 ≥ +0.03；A2 每个年代 ≥ −0.02、最大回撤不深 2 pp 以上、前一半 / 后一半的差合计都 ≥ −0.02；A3 合起来胜率差 ≥ −2.0 pp。
   路线 B「成功率」：B1 合起来胜率差 ≥ +2.0 pp 且每笔不降；B2 每个年代胜率差 ≥ −2.0 pp；B3 账户不变差（每个年代 ≥ −0.02、合计 ≥ 0、回撤、两半）。
   V4 池子同方向：W（2006〜2016，E 那一折的 C）与 Jx（**只用 2022-01 之后的信号**：评分模型没见过）里 B3 会买的信号的假想单笔（每个信号单独买、
      X6 离场、扣费用）：买点做法 = 保留的 vs 全部；卖点做法 = 同一个信号「X6 + 事件离场」vs「X6」配对。路线 B：胜率差 > 0 且每笔差 ≥ 0；路线 A：每笔差 > 0；
      两个池子都要（一个信号都没被挡 / 没换卖点 → 不过）。
   V5 不适用（没有从 B3 的结果学参数）。V6 Zx（2001〜2006，扩大池里非日経225）也要同方向（同 V4 那条路线的标准）。
   V7（本研究加的）评分模型没见过的部分不变差：J 的后一半（2022-01〜）Calmar 差 ≥ −0.02。
   第一关 = （路线 A 或 B 全过）∧ V7。
四 第二关（第一关过了才做；另行登记（提交）后只运行一次）：买点 = 每个年代按实际挡掉的比例随机挡 400 次（research_loop10.random_signal_block）；
   卖点 = 每只票的事件日在自己的日序列上循环平移 400 次（同样的个数）；统计量同第十一个循环（路线 A = Calmar 差合计、路线 B = 合起来胜率差），
   候选严格大于 400 次里最大的才过。两关都过 =「更好候选」→ 报告给用户，要不要加进前向记录 / 模拟盘由用户决定（不自动改）。
五 只描述（不参与判定）：① B3 实际买点（信号日）在六个分数上的百分位分布（中位数、落在「最像」的比例）——「现在的买点像不像起涨 / 起跌点」；
   ② B3 实际卖点（离场前一天收盘）同样；③ B3 的成交按买点的下跌 / 上涨分数三等分 → 胜率 / 每笔；④ 日経225 全部 W2 信号的假想单笔（每个年代）同样比；
   ⑤ Jx 2017〜2021（评分模型样本内）单独报。
登记前只数个数（--prep，2026-10-06；不算任何结果）：评分模型重拟合 = 结果文件（日 / 周 / 月线训练 554,975 / 597,505 / 108,042 行、前 12 个系数逐个相同；
   宽表打分 vs 样本表打分最大差 ≤ 2e-6）。日経225 全部 W2 信号 Z 97 / E 155 / J 173 个（打得了分 74 / 144 / 146），B3 成交 35 / 43 / 62 笔（打得了分 35 / 41 / 55）；
   碰到的 B3 成交：TBF 8 / 9 / 12 笔（合计 29 / 140 = 21%）、TBR 7 / 7 / 12（26 = 19%）；成交后 60 天里有事件日：TXF 30 / 34 / 47、TXR 21 / 28 / 35
   （「最像」每天按排名，进出频繁 → 事件日多：Z / E / J 各约 6,000 / 13,700 / 13,600 个（TXF））。池子（B3 会买的信号；Jx 只算 2022-01〜）：
   W 438 个（打得了分 414）：TBF 135、TBR 61、60 天里有 TXF / TXR 事件 353 / 250；Jx 467（464）：117、38、365 / 262；Zx 381（227）：47、35、220 / 163。
六 事前预期（照实写，写在运行之前）：〔67〕全市场「最像起跌点」的一组之后不跑输（周 −0.32 / 月 +0.55 pp）→ TBF / TXF 多半挡掉 / 提前卖掉
   不差的突破（突破本来就在高点附近、像起跌点）→ 账户变差的可能大；TBR 方向有〔67〕的结果支持，但 B3 买的是突破，周 / 月线还像底部的突破应该很少
   → 碰到的笔数少、账户几乎不变；TXR 多半在 X6 之后才出现 → 几乎不触发。每个做法第一关约 2〜5%、两关都过约 1%。
   （数完个数之后补一句，照实写：TBR 碰到的 B3 成交比预想的多（26 / 140）；「最像」每天按排名、进出频繁 → TXF / TXR 的事件日也比预想的多，
   卖点做法会提前卖掉很多笔 —— 条件写法没有因此改。）
   多重检验（照实写）：4 个做法；第二关 1 / 401。
用法：python scripts/turn_shape_combo.py --prep（重拟合 + 接线核对 + 只数个数；不算任何结果）；--run（只运行一次：第一关 + 只描述）。
输出：var/out/turn_shape_combo.md / .json（只有汇总统计，没有个股名单）；缓存（不入库）：var/cache/turn_shape_combo_*.pkl。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import turn_shape_study as S                                                 # noqa: E402

SCALES3 = ("D", "W", "M")
MODELS = ("rise", "fall")
TOP = 0.90                                                                   # 当天百分位 > 0.90 =「最像」（最像的 1 / 10）
IDS = ("TBF", "TBR", "TXF", "TXR")
KIND = {"TBF": "buy", "TBR": "buy", "TXF": "sell", "TXR": "sell"}
COND = {"TBF": "fall2", "TBR": "rise_wm", "TXF": "fall2", "TXR": "rise_wm"}
NAMES = {"TBF": "像起跌点就不买", "TBR": "周 / 月线像起涨点就不买", "TXF": "变得像起跌点就卖", "TXR": "周 / 月线变得像起涨点就卖"}
POSTHOC = {k: True for k in IDS}
SRC = {"D": ("turn_shape_wide.json", ("universes", "U2", "models")), "W": ("turn_shape_mtf.json", ("scales", "W", "models")),
       "M": ("turn_shape_mtf.json", ("scales", "M", "models"))}
SRC_REV = {"D": "2757571", "W": "de4b60c", "M": "de4b60c"}
FEATS_SCORED = [f for f in S.FEATS if f != "lmc"]                            # 「算得出」= 这 45 个都有值
OOS_FROM = "2022-01-01"                                                      # 评分模型训练期 2017-10〜2021-12 之后
J2_TOL = -0.02                                                               # V7：J 后一半 Calmar 差至少 −0.02
FP = "3b2e8757be7b4a74"
N225_ERAS = ("Z", "E", "J")
POOLS = ("W", "Jx", "Zx")
EVENT_WINDOW = 60                                                            # 只数个数：成交日之后 60 个交易日（= 最长持有）里有没有事件日
MODEL_CACHE, FLAG_CACHE = "turn_shape_combo_models.pkl", "turn_shape_combo_flags.pkl"
OUT_MD, OUT_JSON = "turn_shape_combo.md", "turn_shape_combo.json"


# ───────────────────────── 纯函数（tests/test_turn_shape_combo.py） ─────────────────────────
def fresh(c: np.ndarray) -> np.ndarray:
    """事件日：条件今天成立、前一个交易日（上一行）不成立（第一行 = 前一天当不成立）。"""
    c = np.asarray(c, bool)
    prev = np.vstack([np.zeros((1, c.shape[1]), bool), c[:-1]])
    return c & ~prev


def top_flags(score: np.ndarray, ok: np.ndarray, top: float = TOP) -> np.ndarray:
    """每一天（行）在 ok 的票里按分数排百分位（平均名次 ÷ 个数）；> top =「最像」。不在 ok 里的格 = False。"""
    s = np.where(np.asarray(ok, bool) & np.isfinite(score), score, np.nan)
    r = pd.DataFrame(s).rank(axis=1, pct=True).to_numpy()
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(r, nan=0.0) > top


def pct_rank(score: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """同 top_flags 的百分位（0〜1；不在 ok 里 = NaN），只描述用。"""
    s = np.where(np.asarray(ok, bool) & np.isfinite(score), score, np.nan)
    return pd.DataFrame(s).rank(axis=1, pct=True).to_numpy()


def conditions(fl: dict) -> dict[str, np.ndarray]:
    """fl = {(尺度, 模型): 「最像」的 bool 宽表} → 两种条件：fall2 = 三个尺度的下跌模型至少两个；rise_wm = 周线或月线的上涨模型。"""
    n = sum(np.asarray(fl[(sc, "fall")], int) for sc in SCALES3)
    return {"fall2": n >= 2, "rise_wm": np.asarray(fl[("W", "rise")], bool) | np.asarray(fl[("M", "rise")], bool)}


def rule_arrays(cond: dict) -> dict[str, np.ndarray]:
    """四个做法的宽表：买点 = 条件（信号日收盘）；卖点 = 事件日（条件变得成立的那天）。"""
    return {k: (cond[COND[k]] if KIND[k] == "buy" else fresh(cond[COND[k]])) for k in IDS}


def lookup(arr: np.ndarray, days: pd.DatetimeIndex, names: list[str], tickers, dates) -> np.ndarray:
    """宽表在（票, 日期）上的值（找不到 → False）。"""
    col = {t: j for j, t in enumerate(names)}
    pos = days.get_indexer(pd.DatetimeIndex(pd.to_datetime(np.asarray(dates))))
    out = np.zeros(len(pos), bool)
    for i, (t, k) in enumerate(zip(tickers, pos)):
        j = col.get(t)
        if j is not None and k >= 0:
            out[i] = bool(arr[k, j])
    return out


def exit_tick(ev: np.ndarray, days: pd.DatetimeIndex, names: list[str], only: set | None = None) -> dict[str, frozenset]:
    """事件日宽表 → candle_portfolio.run 的 exit_tick {票: {收盘日, …}}（那天收盘还拿着 → 第二天开盘卖）。"""
    out = {}
    for j, t in enumerate(names):
        if only is not None and t not in only:
            continue
        k = np.flatnonzero(ev[:, j])
        if len(k):
            out[t] = frozenset(pd.Timestamp(d).normalize() for d in days[k])
    return out


def coef_match(w: np.ndarray, stored: list[dict], n: int = 12) -> dict:
    """重拟合的系数（去掉截距）按绝对值排的前 n 个 vs 结果文件里存的（4 位小数）。"""
    top = sorted(zip(S.FEATS, w[1:]), key=lambda kv: -abs(kv[1]))[:n]
    got = [{"f": f, "b": round(float(b), 4)} for f, b in top]
    diff = [abs(a["b"] - b["b"]) for a, b in zip(got, stored)] if len(stored) == len(got) else [np.inf]
    same = len(stored) == len(got) and all(a["f"] == b["f"] for a, b in zip(got, stored)) and max(diff) < 1e-9
    return {"same": bool(same), "max_diff": float(max(diff)) if diff else None}


# ───────────────────────── 评分模型（冻结：登记的代码重拟合） ─────────────────────────
def _fit(x: pd.DataFrame) -> dict:
    """turn_shape_wide.fit_models（impute）/ turn_shape_mtf.fit_scale 的拟合部分（同一段代码）。"""
    w = S.windows(x)
    F = x[S.FEATS].astype(float)
    F["lmc"] = F["lmc"].fillna(F["lmc"].groupby(x["date"]).transform("median"))
    comp = F.notna().all(axis=1).to_numpy()
    xi = w["X"] & comp
    Xr = F.loc[xi].to_numpy(float)
    Xs, st = S.winsor_std(Xr, Xr)
    return {"st": st, "w": {mk: S.fit_logit(Xs, x.loc[xi, lab].to_numpy(float)) for mk, (lab, _) in S.MODELS.items()}, "n_train": int(xi.sum())}


def table_scores(x: pd.DataFrame, fit: dict, rows: np.ndarray) -> dict[str, np.ndarray]:
    """样本表的行 → 分数（log 时价总额当缺值；缺 → 0）—— 接线核对用。"""
    F = x.loc[rows, S.FEATS].astype(float).copy()
    F["lmc"] = np.nan
    X = S.apply_std(F.to_numpy(float), fit["st"])
    X = np.where(np.isfinite(X), X, 0.0)
    return {mk: S.predict(fit["w"][mk], X) for mk in MODELS}


def score_panel(P: dict, days: pd.DatetimeIndex, fits: dict) -> tuple[dict, np.ndarray]:
    """行情宽表（O / H / L / C / V，days × 票）→ ({(尺度, 模型): 线性分数}, 45 个特征都有值的格)。同 turn_shape_study 的特征函数；
    σ = 向前填补口径；log 时价总额当缺值（→ 0）。分数 = clip(截距 + Σ 系数 × 标准化特征, ±30)（= turn_shape_study.predict）。"""
    P = {k: np.asarray(P[k], float) for k in ("O", "H", "L", "C", "V")}
    shape = P["C"].shape
    idx = {f: i for i, f in enumerate(S.FEATS)}
    acc = {(sc, mk): np.full(shape, float(fits[sc]["w"][mk][0])) for sc in fits for mk in MODELS}
    complete = np.ones(shape, bool)
    seen: list[str] = []

    def add(name: str, arr: np.ndarray) -> None:
        nonlocal complete
        i = idx[name]
        seen.append(name)
        if name != "lmc":
            complete &= np.isfinite(arr)
        for sc, ft in fits.items():
            st = ft["st"]
            with np.errstate(invalid="ignore"):
                z = (np.clip(arr, st["lo"][i], st["hi"][i]) - st["mu"][i]) / st["sd"][i]
            z = np.where(np.isfinite(z), z, 0.0)
            for mk in MODELS:
                acc[(sc, mk)] += float(ft["w"][mk][1 + i]) * z

    with np.errstate(invalid="ignore", divide="ignore"):
        for name, arr in S.daily_features(P, np.full(shape, np.nan)):
            add(name, arr)
        Cf = S.ffill(P["C"])
        add("sig60", S.rstd(np.diff(np.log(Cf), axis=0, prepend=np.nan), S.SIG_N))
        for freq, prefix in (("W", "w"), ("M", "m")):
            B, _, pos = S.bar_panels(P, days, freq)
            for name, arr in S.bar_features(B, prefix).items():
                add(name, S.on_days(arr, pos))
    if sorted(seen) != sorted(S.FEATS):
        raise AssertionError(f"特征不齐：{sorted(set(S.FEATS) ^ set(seen))}")
    fin = np.isfinite(P["C"])
    out = {k: np.where(fin, np.clip(v, -30, 30), np.nan).astype(np.float32) for k, v in acc.items()}
    return out, complete & fin


def refit_models(say=print) -> dict:
    """用登记的代码（turn_shape_wide.build / prep、turn_shape_mtf.build_scale / prep_scale）在同一份 J-Quants 缓存上重拟合三个尺度的模型，
    并核对：前 12 个系数与结果文件相同、训练行数相同；宽表打分 = 样本表打分（随机 400 只票的样本行）。"""
    import allsec_data as AS
    import turn_shape_mtf as MT
    import turn_shape_wide as W
    from qbreak import paths
    from qbreak.config import universe
    A = AS.load()
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    n225 = set(universe("JP", "broad"))
    out: dict = {"fits": {}, "check": {}}
    rng = np.random.default_rng(20261006)
    cols = np.sort(rng.choice(len(names), size=min(400, len(names)), replace=False))
    Psub = {k: A[k][:, cols].astype(float) for k in ("O", "H", "L", "C", "V")}
    for sc in SCALES3:
        if sc == "D":
            T, _ = W.build(A, days, names, False, say)
            x = W.prep(T, W.universe_flags(T)["U2"], names, n225, ffill_sig=True)
        else:
            T, _, _ = MT.build_scale(A, days, names, sc, False, say)
            x = MT.prep_scale(T, names, n225, MT.SCALES[sc]["cluster"])
        del T
        fit = _fit(x)
        fn, path_ = SRC[sc]
        stored = json.loads((paths.PROJECT_ROOT / "var" / "out" / fn).read_text(encoding="utf-8"))
        for p_ in path_:
            stored = stored[p_]
        chk = {mk: coef_match(fit["w"][mk], stored[mk]["coef"]) for mk in MODELS}
        chk["n_train"] = [fit["n_train"], int(stored["rise"]["n_train"])]
        sp, _ = score_panel(Psub, days, {sc: fit})
        inset = np.isin(x["j"].to_numpy(), cols)
        rows = np.flatnonzero(inset)
        ts = table_scores(x, fit, rows)
        jmap = {int(c): i for i, c in enumerate(cols)}
        kk = x["k"].to_numpy()[rows]
        jj = np.array([jmap[int(j)] for j in x["j"].to_numpy()[rows]])
        chk["wiring"] = {mk: float(np.nanmax(np.abs(sp[(sc, mk)][kk, jj] - ts[mk]))) if len(rows) else None for mk in MODELS}
        chk["wiring_rows"] = int(len(rows))
        out["fits"][sc], out["check"][sc] = fit, chk
        say(f"{sc} 重拟合：训练 {fit['n_train']} 行（结果文件 {chk['n_train'][1]}）；系数 " + "、".join(
            f"{mk} {'相同' if chk[mk]['same'] else '不同'}" for mk in MODELS) + f"；宽表 vs 样本表最大差 {chk['wiring']}")
        del x
    out["ok"] = all(out["check"][sc][mk]["same"] for sc in SCALES3 for mk in MODELS) and all(
        out["check"][sc]["n_train"][0] == out["check"][sc]["n_train"][1] for sc in SCALES3) and all(
        (out["check"][sc]["wiring"][mk] or 0.0) < 1e-3 for sc in SCALES3 for mk in MODELS)
    return out


def load_models(say=print) -> dict:
    from qbreak import paths
    fp = paths.sub("cache") / MODEL_CACHE
    if fp.exists():
        with open(fp, "rb") as f:
            return pickle.load(f)
    m = refit_models(say)
    with open(fp, "wb") as f:
        pickle.dump(m, f)
    return m


# ───────────────────────── 每个样本的分数与「最像」 ─────────────────────────
def sample_panels(W: dict) -> dict:
    """{样本: {P, days, names, ok（可交易 = 排名参照）}}；Z / E / J（今天的日経225）+ W / Jx / Zx。J / Jx 共用 candle_data 一张表。"""
    import leap_confirm as LF
    import loop10_common as C10
    from qbreak.config import universe
    n225 = set(universe("JP", "broad"))
    out = {}
    for e in ("Z", "E"):
        c = W["ctx"][e]
        out[e] = {"P": c["P"], "days": pd.DatetimeIndex(c["days"]), "names": list(c["names"]), "ref": None}
    c2 = W["SM"]["J2"]["ctx"]
    D = c2["D"]
    names = list(D["names"])
    days = pd.DatetimeIndex(D["days"])
    u0 = np.array([t in n225 for t in names])
    jn = set(W["ctx"]["J"]["names"][j] for j in W["ctx"]["J"]["cols"])
    jcol = np.array([t in jn for t in names])
    out["J"] = {"P": D["P"], "days": days, "names": names, "ref": np.broadcast_to(jcol, (len(days), len(names)))}
    out["Jx"] = {"P": D["P"], "days": days, "names": names, "ref": np.asarray(D["mem"]["U2"], bool) & ~u0[None, :]}
    cw = W["SM"]["W"]["ctx"]
    out["W"] = {"P": cw["P"], "days": pd.DatetimeIndex(cw["days"]), "names": list(cw["names"]), "ref": None}
    cz = LF.context("Z", names=C10.zx_names())
    out["Zx"] = {"P": cz["P"], "days": pd.DatetimeIndex(cz["days"]), "names": list(cz["names"]), "ref": None}
    return out


def flags_of(panels: dict, fits: dict, say=print) -> dict:
    """每个样本：六个分数的「最像」宽表 + 百分位（只描述用）+ 四个做法的宽表。J / Jx 只算一次分数。"""
    out = {}
    cache: dict = {}
    for s, pn in panels.items():
        key = id(pn["P"])
        if key not in cache:
            cache[key] = score_panel(pn["P"], pn["days"], fits)
        sc_, comp = cache[key]
        ok = comp if pn["ref"] is None else (comp & pn["ref"])
        fl = {k: top_flags(v, ok) for k, v in sc_.items()}
        pr = {k: pct_rank(v, ok).astype(np.float32) for k, v in sc_.items()}
        out[s] = {"days": pn["days"], "names": pn["names"], "ok": ok, "top": fl, "pct": pr, "rules": rule_arrays(conditions(fl))}
        say(f"{s}：{len(pn['names'])} 只 × {len(pn['days'])} 天；可打分的格 {int(ok.sum())}")
    return out


def load_flags(W: dict, fits: dict, say=print) -> dict:
    from qbreak import paths
    fp = paths.sub("cache") / FLAG_CACHE
    if fp.exists():
        with open(fp, "rb") as f:
            return pickle.load(f)
    fl = flags_of(sample_panels(W), fits, say)
    with open(fp, "wb") as f:
        pickle.dump(fl, f)
    return fl


# ───────────────────────── 只数个数（登记前） ─────────────────────────
def pool_signals(W: dict, s: str) -> pd.DataFrame:
    """池子里 B3 会买的信号（W2 + 那一折的 C；有结果的）—— loop10_common.kept_pool。"""
    import loop10_common as C10
    fold = {p: f for p, f, _ in C10.OTHER}[s]
    return C10.kept_pool(W, s, fold)


def window_has(ev: np.ndarray, days: pd.DatetimeIndex, names: list[str], tickers, fills, n: int = EVENT_WINDOW) -> np.ndarray:
    """（票, 成交日）之后 n 个交易日（含成交日收盘）里有没有事件日（只数个数用）。"""
    col = {t: j for j, t in enumerate(names)}
    pos = days.searchsorted(pd.DatetimeIndex(pd.to_datetime(np.asarray(fills))))
    out = np.zeros(len(pos), bool)
    for i, (t, k) in enumerate(zip(tickers, pos)):
        j = col.get(t)
        if j is not None and 0 <= k < len(days):
            out[i] = bool(ev[k:k + n, j].any())
    return out


def next_day(days: pd.DatetimeIndex, dates) -> pd.DatetimeIndex:
    """信号日 → 成交日（这个样本交易日历里的下一天）。"""
    p = days.searchsorted(pd.DatetimeIndex(pd.to_datetime(np.asarray(dates))), side="right")
    return days[np.clip(p, 0, len(days) - 1)]


def counts(W: dict, F: dict) -> dict:
    """每个做法碰到多少：日経225 全部 W2 信号 / B3 实际成交（买点 = 信号日；卖点 = 成交后 60 天里有事件日）；池子里 B3 会买的信号同样。"""
    import loop11_common as LC
    out: dict = {"n225": {}, "pools": {}}
    for e in N225_ERAS:
        f = F[e]
        Sg = LC.signals(W, e)
        tr = LC.b3_trades(W, e)
        r = {"signals": int(len(Sg)), "b3_trades": int(len(tr)),
             "scorable_signals": int(lookup(f["ok"], f["days"], f["names"], Sg["ticker"], Sg["date"]).sum()),
             "scorable_trades": int(lookup(f["ok"], f["days"], f["names"], tr["ticker"], tr["sig"]).sum())}
        for k in IDS:
            if KIND[k] == "buy":
                r[k] = {"signals": int(lookup(f["rules"][k], f["days"], f["names"], Sg["ticker"], Sg["date"]).sum()),
                        "b3_trades": int(lookup(f["rules"][k], f["days"], f["names"], tr["ticker"], tr["sig"]).sum())}
            else:
                fills_s = next_day(f["days"], Sg["date"])
                r[k] = {"signals": int(window_has(f["rules"][k], f["days"], f["names"], Sg["ticker"], fills_s).sum()),
                        "b3_trades": int(window_has(f["rules"][k], f["days"], f["names"], tr["ticker"], tr["fill"]).sum()),
                        "event_days": int(f["rules"][k].sum())}
        out["n225"][e] = r
    for s in POOLS:
        f = F[s]
        X = pool_signals(W, s)
        if s == "Jx":
            X = X[pd.to_datetime(X["date"]) >= pd.Timestamp(OOS_FROM)].reset_index(drop=True)
        r = {"signals": int(len(X)), "scorable": int(lookup(f["ok"], f["days"], f["names"], X["ticker"], X["date"]).sum())}
        for k in IDS:
            if KIND[k] == "buy":
                r[k] = int(lookup(f["rules"][k], f["days"], f["names"], X["ticker"], X["date"]).sum())
            else:
                r[k] = int(window_has(f["rules"][k], f["days"], f["names"], X["ticker"], next_day(f["days"], X["date"])).sum())
        out["pools"][s] = r
    return out


# ───────────────────────── 运行（只一次） ─────────────────────────
def gates_of(W: dict, F: dict, k: str) -> dict[str, np.ndarray]:
    """买点做法：每个年代全部 W2 信号（与 loop9_common.signals 同序）要不要挡。"""
    import loop9_common as C9
    out = {}
    for e in N225_ERAS:
        Sg = C9.signals(W, e)
        f = F[e]
        out[e] = lookup(f["rules"][k], f["days"], f["names"], Sg["ticker"], Sg["date"])
    return out


def ticks_of(F: dict, k: str) -> dict[str, dict]:
    """卖点做法：每个年代的 exit_tick。"""
    return {e: exit_tick(F[e]["rules"][k], F[e]["days"], F[e]["names"]) for e in N225_ERAS}


def run_account(W: dict, e: str, k: str, gates: dict | None, ticks: dict | None) -> dict:
    import loop9_common as C9
    import loop6_common as L6
    if KIND[k] == "buy":
        return C9.acct(C9.run_block(W, e, gates[e]))
    tk = ticks[e]
    return C9.acct(L6.run(W, e, exit_tick=tk) if tk else L6.run(W, e))


def single_with_events(t: str, df: pd.DataFrame, d, p0, bt, rt: float, ev_dates: frozenset | None, end_bars: int = 130) -> tuple[float, float]:
    """一个信号的假想单笔：X6（combo_all_study.outcomes 同一做法）与「X6 + 事件日离场」各一次；没买到 / 还没卖 → NaN。
    事件日离场 = 成交日起（含成交日收盘）那天收盘还拿着 → 第二天开盘卖（同账户的 exit_tick），与吊灯止损的旗子合在一起（dead_cross 列）。"""
    from qbreak import exit_forward as XF
    d = pd.Timestamp(d)
    if d not in df.index:
        return float("nan"), float("nan")
    pos = int(df.index.get_loc(d))
    end = df.index[min(len(df) - 1, pos + end_bars)]
    f = df.copy()
    f["entry"] = np.asarray(df.index == d)
    try:
        a = XF._one(t, f, p0, bt, d, end)
    except ValueError:
        return float("nan"), float("nan")
    if a is None:
        return float("nan"), float("nan")
    kk = int(f.index.get_loc(pd.Timestamp(a["entry_date"])))
    px = float(f["Open"].to_numpy(float)[kk]) * (1 + bt.exec_cfg.slippage_pct / 100)
    ch = np.asarray(XF.chandelier_flags(f, kk, px, k=3.0), bool)
    pv = replace(p0, max_hold_days=60)                                       # 同 loop11_common.single_net（B3：k 3、60 天）
    b = XF._one(t, f.assign(dead_cross=ch), pv, bt, d, end)
    nb = float("nan") if (b is None or b["reason"] == "end" or b["entry_date"] != a["entry_date"]) else float(b["ret_pct"]) - rt
    if not ev_dates:
        return nb, nb
    evf = np.isin(f.index.normalize(), pd.DatetimeIndex(sorted(ev_dates)))
    evf[:kk] = False
    if not evf.any():
        return nb, nb
    v = XF._one(t, f.assign(dead_cross=ch | evf), pv, bt, d, end)
    nv = float("nan") if (v is None or v["reason"] == "end" or v["entry_date"] != a["entry_date"]) else float(v["ret_pct"]) - rt
    return nb, nv


def pool_stats(W: dict, F: dict, k: str, s: str, only_from: str | None = None, until: str | None = None) -> dict:
    """池子 s 的假想单笔：买点 = 保留的 vs 全部（net = X6，同 loop10_common.other_stocks）；卖点 = 配对（X6 + 事件 vs X6）。"""
    import combo_all_common as CA
    import loop11_common as LC
    X = pool_signals(W, s)
    dd = pd.to_datetime(X["date"])
    m = np.ones(len(X), bool)
    if only_from:
        m &= (dd >= pd.Timestamp(only_from)).to_numpy()
    if until:
        m &= (dd < pd.Timestamp(until)).to_numpy()
    X = X[m].reset_index(drop=True)
    f = F[s]
    if KIND[k] == "buy":
        g = lookup(f["rules"][k], f["days"], f["names"], X["ticker"], X["date"])
        net = X["net"].to_numpy(float)
        dl = CA.delta(net, ~g)
        gone = net[g]
        return {"n": int(dl["n"]), "kept": int(dl["kept"]), "changed": int(g.sum()), "dwin": dl["dwin"], "dmean": dl["dmean"],
                "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
    import loop10_common as C10
    p0 = W["p0"]
    bt, rt = LC.bt_rt()
    sm = {p: x for p, _, x in C10.OTHER}[s]
    fa = W["SM"][sm]["fa"]
    ticks = exit_tick(f["rules"][k], f["days"], f["names"], only=set(X["ticker"]))
    nb, nv = [], []
    for t, d in zip(X["ticker"], pd.to_datetime(X["date"])):
        df = fa.get(t)
        if df is None:
            nb.append(np.nan)
            nv.append(np.nan)
            continue
        a, b = single_with_events(t, df, d, p0, bt, rt, ticks.get(t))
        nb.append(a)
        nv.append(b)
    nb, nv = np.asarray(nb, float), np.asarray(nv, float)
    changed = np.isfinite(nb) & np.isfinite(nv) & ~np.isclose(nb, nv, atol=1e-9)
    st = LC.pair_stats(nb, nv, changed)
    st["base_match"] = int(np.sum(np.isclose(nb, X["net"].to_numpy(float), atol=1e-6)))
    return st


def n225_singles(W: dict, F: dict, k: str) -> dict:
    """只描述：每个年代全部日経225 W2 信号的假想单笔（买点 = 挡掉的 vs 保留的；卖点 = 配对）。"""
    import combo_all_common as CA
    import loop11_common as LC
    out = {}
    for e in N225_ERAS:
        Dn = W["D"][e].reset_index(drop=True)
        f = F[e]
        if KIND[k] == "buy":
            g = lookup(f["rules"][k], f["days"], f["names"], Dn["ticker"], Dn["date"])
            net = Dn["net"].to_numpy(float)
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[e] = {"n": int(dl["n"]), "changed": int(g.sum()), "dwin": dl["dwin"], "dmean": dl["dmean"],
                      "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
            continue
        p0 = W["p0"]
        bt, rt = LC.bt_rt()
        fa = W["SM"][e]["fa"]
        ticks = exit_tick(f["rules"][k], f["days"], f["names"], only=set(Dn["ticker"]))
        nb, nv = [], []
        for t, d in zip(Dn["ticker"], pd.to_datetime(Dn["date"])):
            df = fa.get(t)
            a, b = (np.nan, np.nan) if df is None else single_with_events(t, df, d, p0, bt, rt, ticks.get(t))
            nb.append(a)
            nv.append(b)
        nb, nv = np.asarray(nb, float), np.asarray(nv, float)
        out[e] = LC.pair_stats(nb, nv, np.isfinite(nb) & np.isfinite(nv) & ~np.isclose(nb, nv, atol=1e-9))
    return out


def describe_b3(W: dict, F: dict) -> dict:
    """只描述：B3 实际买点（信号日）/ 卖点（离场前一天收盘）在六个分数上的百分位；按买点的分数三等分 → 胜率 / 每笔。"""
    import jq_study as JS
    import loop6_common as L6
    out = {}
    for e in N225_ERAS:
        L6.run(W, e)
        tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
        a, b = W["ctx"][e]["windows"][e]
        tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(["1545.T", "1482.T", "1655.T", "2845.T"]) & (tr["reason"] != "end")]
        ed = pd.to_datetime(tr["entry_date"])
        tr = tr[((ed >= pd.Timestamp(a)) & (ed < pd.Timestamp(b or "2026-10-01"))).to_numpy()].reset_index(drop=True)
        f = F[e]
        days = f["days"]
        sig = days[np.clip(days.searchsorted(pd.to_datetime(tr["entry_date"])) - 1, 0, len(days) - 1)]
        xd = days[np.clip(days.searchsorted(pd.to_datetime(tr["exit_date"])) - 1, 0, len(days) - 1)]
        col = {t: j for j, t in enumerate(f["names"])}
        jj = np.array([col.get(t, -1) for t in tr["ticker"]])
        ks, kx = days.get_indexer(sig), days.get_indexer(xd)
        ret = pd.to_numeric(tr.get("ret_pct", tr.get("pnl_pct")), errors="coerce").to_numpy(float)
        r = {"n": int(len(tr))}
        for (sc, mk), arr in f["pct"].items():
            pin = np.array([arr[k, j] if (j >= 0 and k >= 0) else np.nan for k, j in zip(ks, jj)], float)
            pout = np.array([arr[k, j] if (j >= 0 and k >= 0) else np.nan for k, j in zip(kx, jj)], float)
            fin = np.isfinite(pin)
            row = {"n_scored": int(fin.sum()), "entry_median": float(np.nanmedian(pin)) if fin.any() else None,
                   "entry_top_share": float(np.mean(pin[fin] > TOP) * 100) if fin.any() else None,
                   "exit_median": float(np.nanmedian(pout)) if np.isfinite(pout).any() else None,
                   "exit_top_share": float(np.mean(pout[np.isfinite(pout)] > TOP) * 100) if np.isfinite(pout).any() else None, "terciles": {}}
            if fin.sum() >= 9:
                q = np.nanquantile(pin, [1 / 3, 2 / 3])
                for name, mm in (("low", pin <= q[0]), ("mid", (pin > q[0]) & (pin <= q[1])), ("high", pin > q[1])):
                    mm = mm & fin & np.isfinite(ret)
                    row["terciles"][name] = {"n": int(mm.sum()), "win": float(np.mean(ret[mm] > 0) * 100) if mm.any() else None,
                                             "mean": float(np.mean(ret[mm])) if mm.any() else None}
            r[f"{sc}_{mk}"] = row
        out[e] = r
    return out


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/turn_shape_combo.py", "scripts/turn_shape_study.py",
                                     "scripts/turn_shape_wide.py", "scripts/turn_shape_mtf.py", "scripts/loop11_common.py", "scripts/candle_portfolio.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def judge(cand: dict, base: dict, other: dict, posthoc: bool) -> dict:
    """第一关 = research_loop11.stage1（两条路线 + V4 W / Jx + V6 Zx；V5 不适用）∧ V7（J 后一半 Calmar 差 ≥ −0.02）。"""
    import research_loop11 as R11
    s1 = R11.stage1(cand, base, other, lenses=None, posthoc=posthoc)
    cj, bj = (cand.get("J") or {}).get("h2"), (base.get("J") or {}).get("h2")
    d7 = None if cj is None or bj is None else float(cj) - float(bj)
    v7 = d7 is not None and d7 >= J2_TOL - 1e-12
    return {**s1, "V7": bool(v7), "d_j2": d7, "ok": bool(s1["ok"] and v7)}


def run(say=print) -> dict:
    import loop10_common as C10
    import research_loop10 as R10
    import research_loop11 as R11
    t0 = time.time()
    M = load_models(say)
    if not M["ok"]:
        raise SystemExit("先决条件不满足：重拟合的评分模型与登记的结果不同 / 接线核对不过 → 停")
    W = C10.load()
    F = load_flags(W, M["fits"], say)
    base = {e: C10.acct(C10.L6.run(W, e)) for e in N225_ERAS}
    pre = R10.prereq({e: {k: v for k, v in base[e].items()} for e in N225_ERAS}, R11.b3_reference(), R11.rules_fingerprint())
    if not pre["ok"]:
        raise SystemExit(f"先决条件不满足（B3 重算 / 模拟盘规则指纹）：{pre}")
    say(f"B3 重算一致、指纹 {pre.get('fingerprint')}；{time.time() - t0:.0f}s")
    res: dict = {"git": git_info(), "prereq": pre, "models_check": M["check"], "base": base, "cand": {}, "other": {}, "stage1": {}, "singles": {},
                 "jx_insample": {}, "counts": counts(W, F)}
    for k in IDS:
        gates = gates_of(W, F, k) if KIND[k] == "buy" else None
        ticks = ticks_of(F, k) if KIND[k] == "sell" else None
        res["cand"][k] = {e: run_account(W, e, k, gates, ticks) for e in N225_ERAS}
        say(f"{k} 账户完成；{time.time() - t0:.0f}s")
        res["other"][k] = {"W": pool_stats(W, F, k, "W"), "Jx": pool_stats(W, F, k, "Jx", only_from=OOS_FROM), "Zx": pool_stats(W, F, k, "Zx")}
        res["jx_insample"][k] = pool_stats(W, F, k, "Jx", until=OOS_FROM)
        say(f"{k} 池子完成；{time.time() - t0:.0f}s")
        res["stage1"][k] = judge(res["cand"][k], base, res["other"][k], POSTHOC[k])
        res["singles"][k] = n225_singles(W, F, k)
    res["describe"] = describe_b3(W, F)
    res["success_base"] = R10.pooled_trades(base)
    res["elapsed_s"] = round(time.time() - t0)
    return res


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def report(res: dict) -> str:
    L = ["# 「上述日 / 周 / 月线结合现在模型（B3）的买卖点」检验（scripts/turn_shape_combo.py；只运行一次）", "",
         f"代码 {res['git']['rev']}{'（有未提交的改动！）' if res['git'].get('dirty') else ''}；先决条件：B3 重算一致、模拟盘规则指纹 {res['prereq'].get('fingerprint')}；"
         "评分模型重拟合 = 登记的结果（" + "、".join(f"{sc} 训练 {res['models_check'][sc]['n_train'][0]} 行" for sc in SCALES3) + "）。", "",
         "## 账户（B3 → 候选）", "",
         "| 做法 | 年代 | Calmar | 差 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for k in IDS:
        for e in N225_ERAS:
            b, c = res["base"][e], res["cand"][k][e]
            L.append(f"| {k} {NAMES[k]} | {e} | {_f(b['calmar'], '{:.3f}')} → {_f(c['calmar'], '{:.3f}')} | "
                     f"{_f(None if c['calmar'] is None or b['calmar'] is None else c['calmar'] - b['calmar'])} | {_f(b['dd'], '{:.2f}')} → {_f(c['dd'], '{:.2f}')}% | "
                     f"{_f(c['h1'], '{:.3f}')} / {_f(c['h2'], '{:.3f}')}（B3 {_f(b['h1'], '{:.3f}')} / {_f(b['h2'], '{:.3f}')}） | {b['n']} → {c['n']} | "
                     f"{_f(b['win'], '{:.1f}')} → {_f(c['win'], '{:.1f}')}% | {_f(b['mean'], '{:+.2f}')} → {_f(c['mean'], '{:+.2f}')}% |")
    L += ["", "## 第一关（路线 A / B + V4 W・Jx(2022〜) + V6 Zx + V7 J 后一半）", ""]
    for k in IDS:
        s = res["stage1"][k]
        ra, rb = s["routes"]["A"], s["routes"]["B"]
        o = res["other"][k]
        pools = "；".join(f"{p} {o[p].get('changed', 0)} / {o[p].get('n', 0)} 个信号{'被挡' if KIND[k] == 'buy' else '换了卖点'}"
                          f"（胜率差 {_f(o[p].get('dwin'), '{:+.2f}')} pp、每笔差 {_f(o[p].get('dmean'), '{:+.3f}')} pp）" for p in POOLS)
        L.append(f"- **{k}「{NAMES[k]}」**：路线 A " + " ".join(f"{x}{'✓' if ra[x] else '✗'}" for x in ("A1", "A2", "A3", "V4", "V6"))
                 + "；路线 B " + " ".join(f"{x}{'✓' if rb[x] else '✗'}" for x in ("B1", "B2", "B3", "V4", "V6"))
                 + f"；V7 {'✓' if s['V7'] else '✗'}（J 后一半差 {_f(s['d_j2'])}）；Calmar 差 " + "、".join(f"{e} {_f(ra['d'].get(e))}" for e in N225_ERAS)
                 + f"（合计 {_f(ra['sum'])}）；胜率差 {_f(rb['dwin'], '{:+.2f}')} pp、每笔差 {_f(rb['dmean'], '{:+.3f}')} pp；{pools}"
                 + f" → **{'第一关通过（要另行登记第二关）' if s['ok'] else '第一关不过'}**")
    L += ["", "## 只描述", "", "### 日経225 全部 W2 信号的假想单笔（每个年代）", ""]
    for k in IDS:
        L.append(f"- {k}：" + "；".join(f"{e} {v.get('changed', 0)} / {v.get('n', 0)}（胜率差 {_f(v.get('dwin'), '{:+.2f}')} pp、每笔差 {_f(v.get('dmean'), '{:+.3f}')} pp"
                                        + (f"；被挡的胜率 {_f(v.get('gone_win'), '{:.1f}')}%、每笔 {_f(v.get('gone_mean'), '{:+.2f}')}%" if KIND[k] == "buy" else "") + "）"
                                        for e, v in res["singles"][k].items()))
    L += ["", "### Jx 2017〜2021（评分模型的训练期 = 样本内，只报告）", ""]
    for k in IDS:
        v = res["jx_insample"][k]
        L.append(f"- {k}：{v.get('changed', 0)} / {v.get('n', 0)}（胜率差 {_f(v.get('dwin'), '{:+.2f}')} pp、每笔差 {_f(v.get('dmean'), '{:+.3f}')} pp）")
    L += ["", "### B3 实际买点 / 卖点在六个分数上的位置（当天本样本里的百分位；> 90% =「最像」）", "",
          "| 年代 | 分数 | 买点中位数 | 买点里「最像」的比例 | 卖点（离场前一天）中位数 | 卖点里「最像」 | 买点分数三等分：胜率 / 每笔（引擎的 ret_pct，未扣费用；低 · 中 · 高） |",
          "|---|---|---|---|---|---|---|"]
    for e, r in res["describe"].items():
        for sc in SCALES3:
            for mk in MODELS:
                x = r[f"{sc}_{mk}"]
                t = x["terciles"]
                tt = " · ".join(f"{_f((t.get(n) or {}).get('win'), '{:.0f}')}% / {_f((t.get(n) or {}).get('mean'), '{:+.1f}')}%" for n in ("low", "mid", "high")) if t else "—"
                L.append(f"| {e}（{r['n']} 笔） | {sc}·{'上涨' if mk == 'rise' else '下跌'} | {_f(x['entry_median'], '{:.2f}')} | {_f(x['entry_top_share'], '{:.0f}')}% | "
                         f"{_f(x['exit_median'], '{:.2f}')} | {_f(x['exit_top_share'], '{:.0f}')}% | {tt} |")
    L += ["", f"用时 {res['elapsed_s']} s。判定按本文件开头（登记版）。只有汇总统计。非投资建议。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prep", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if not (a.prep or a.run):
        raise SystemExit("要 --prep 或 --run")
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    t0 = time.time()
    say = lambda s_: print(f"{s_}；{time.time() - t0:.0f}s", flush=True)     # noqa: E731
    from qbreak import paths
    if a.prep:
        import loop10_common as C10
        M = load_models(say)
        say("评分模型核对：" + ("全部一致" if M["ok"] else "★ 不一致"))
        W = C10.load()
        F = load_flags(W, M["fits"], say)
        print(json.dumps({"models_check": M["check"], "models_ok": M["ok"], "counts": counts(W, F)}, ensure_ascii=False, indent=1, default=str))
        return 0
    res = run(say)
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report(res)
    (out_dir / OUT_MD).write_text(md, encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
