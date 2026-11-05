"""trendline_study.py — 趋势线（连波谷的支撑线 / 连波峰的压力线）能不能预测买卖点和之后的走势、结合现在的选股方法（B4）会不会更好
（登记版：规则、代码与登记前个数一起提交，之后不改、只运行一次）。

来由：用户 2026-10-06「根据现在的K线和现在的选股方法 K线上面比如画一个直线 直线上面每次都可以到波谷的那个线 再画一个线每次都可以波峰
然后预测买卖点和未来走势 结合现在的选股方法 来预测行不行」。
以前相关的（结论都是不改）：现行方法本身就是「水平的线」—— 60 日箱体的箱顶（压力）突破买入；真突破箱顶 E4（signal_study：胜率升、
笔数少 74%、组合更差）；多周期 R1（mtf_study：周线 Stage 2 / 三周期共振当买点过滤两期方向相反）；DeMark TDST 支撑 / 阻力（第三个循环
第 7 轮）；起涨 / 起跌点图形（turn_shape_*：TXF「变得像起跌点就卖」= 早卖，胜率 +11 pp、每笔 −1.3 pp）；止盈 / 分批止盈（TPX、
pyramid_study）都不过。**斜的趋势线（波谷连线 / 波峰连线）、通道、破线没有检验过** → 新。

〇 定义（qbreak/trendline.py，登记时冻结；操作面板画的是同一份）：
   波谷 / 波峰 = 比前 k 根都低（高）、不高（低）于后 k 根（第 p + k 根收盘才确认）；支撑线 = 过两个已确认、相隔 ≥ gap 根、在最近 L 根里的波谷，
   从第一个波谷到当天每根收盘都不低于「线 − 0.3 × ATR14」，最近 R 根里碰到过；碰到最多的那条（一样多取离现价近的）；压力线对称。
   k / L / gap / R：日K 5 / 250 / 10 / 60、周K 3 / 156 / 6 / 26。事件都用前一根时有效的线：跌破支撑 / 突破压力 = 收盘越过「线 ∓ 容差」；
   回踩支撑 = 最低价碰到「线 + 容差」以内、收盘没跌破；碰压力 = 最高价碰到「线 − 容差」以内、收盘没突破。
   通道 = 两条线的斜率（每根 %，|斜率| ≤ ε 算平；ε 日K 0.02、周K 0.1）：上升通道 / 下降通道 / 横盘通道 / 对称三角 / 上升三角 / 下降三角 / 扩散。
   日线：每只票自己的日线逐日扫（研究同一份行情：日経225 = 各年代 W["SM"][e]["fa"]、池子 = W["SM"]["W" / "J2" / "Zx"]["fa"]；调整后价）。
   周线：qbreak.kline.bars(…, "W")（周五结束、实际交易日聚合）上扫；第 t 天用「上一根已经走完的周K（不含 t 这一周）」的线往后延长一根
   = 这一周的线值（同一周里每天一样，没有用到这一周还没走完的部分）；周线的破线事件记在那一周最后一个交易日。
一 预测准确度（全部股票，不只是规则的信号；只用于回答「能不能预测」，不改交易）
   样本 6 个：日経225 Z（2001-01〜2006-09）/ E（2006-10〜2016-09）/ J（2017-01〜2026-09）（各年代那份行情里的票）+ 池子 W（E 的窗口）/
   Jx（J 的窗口；J2 行情里不在日経225 的票，不按当时的成员筛）/ Zx（Z 的窗口）。
   之后的收益 = 第 t + 1 天开盘买、第 t + 20 天收盘（20 个交易日，%）；超额 = 减去同一天同一个样本里全部票（算得出的）的等权平均。
   标准误按月聚类（同一个月的样本算一组；合起来时 6 个样本的同一个月也算一组）；95% 区间 = 平均 ± 1.96 × 标准误。
   A1「通道方向 → 之后 20 日」：年代交易日里每 5 天取一天；上升通道的票平均超额 − 下降通道的票平均超额（两组各 ≥ 5 只的日子）。
      对照 = 均线趋势标签（qbreak/kline.trend 的定义：收盘对 MA20、MA20 比 3 根前、MA5 对 MA20 → 上升 / 下降），同一天同一批票同样的差。
      ①「能预测」：6 个样本每个差 > 0，且合起来 95% 下限 > 0、平均 ≥ +0.3 pp；
      ②「比均线标签好」：（趋势线的差 − 均线的差，同一天配对）6 个样本里 ≥ 5 个 > 0，且合起来 95% 下限 > 0。
   A2 买点事件（日线；前 5 根里有同样的事件不算 = 连续破线只算第一次）：TU 突破压力；TR 回踩支撑（支撑线向上 > ε 时）。
      「有用」：6 个样本每个平均超额 > 0，且合起来 95% 下限 > 0、平均 ≥ +0.3 pp。
   A3 卖点事件（日线，同样去重）：TD 跌破支撑；TF 碰压力回落（压力线向下 < −ε 时）。
      「有用」：6 个样本每个平均超额 < 0，且合起来 95% 上限 < 0、平均 ≤ −0.3 pp。
   周线版（周K收盘那天突破压力 / 跌破支撑，之后 20 个交易日）只描述。
二 结合现在的选股方法：基准 B4 = 模拟盘现在的规则 = B3 + TBF（loop10_common.load + turn_shape_combo 的 TBF 旗子；同 policy_allin_study）。
   先决条件：模拟盘规则指纹 = 1241753c8f2529c6；B4 重算 = turn_shape_combo 结果文件里 TBF 的账户（nisa_tax_study.same_b4：个股笔数与胜率相同、
   Calmar 差 ≤ 0.005 —— 登记前 --prep 看到 E 0.628 vs 0.627：缓存刷新后的很小漂移，与 2026-10-06 税后研究运行前修正 8ce9655 同一个原因与同一个改法）；
   接线核对：加一个从来没拿过的票的事件日 → 账户与 B4 完全相同。五个做法（ID 以前没用过；看到任何趋势线结果之前设计 → posthoc = False）：
   买点（「不开新仓」：那个（票, 信号日）em_tick 0，名额留给下一个候选、钱留在核心；TBF 挡的照旧不买）：
   - TLB1「周线下降通道里的突破不买」：信号日用的周线（〇 的口径）是下降通道，且收盘在这一周的压力线之下。
   - TLB2「上方周线压力线太近不买」：周线压力线在、收盘在它之下、离线不到 1 × 周线 ATR14（占收盘的 %）。
   卖点（在 X6 之上再加一个离场：拿着的日本个股在事件日收盘后 → 第二天开盘卖；candle_portfolio.run 的 exit_tick）：
   - TLS1「收盘跌破日线支撑线就卖」：事件 = 日线跌破支撑（每一次都算）。
   - TLS2「周线收盘跌破周线支撑线就卖」：事件日 = 那一周最后一个交易日。
   - TLS3「碰到周线压力线就卖（止盈）」：事件 = 那天最高价 ≥ 这一周的周线压力 − 周线容差 且 收盘 ≤ 线 + 周线容差。
   第一关 = research_loop11.stage1（两条路线：A 账户 / B 成功率；V4 池子 W / Jx 同方向；posthoc = False → V6 Zx 只描述）；
   池子 = B4 会买的信号（W2 + 那一折的 C 保留、TBF 没挡；Jx 用全部 2017〜）的假想单笔：买点 = 保留的 vs 全部；卖点 = 「X6 + 事件」vs「X6」配对。
   第二关（第一关过了才做；另行登记（提交）后只运行一次）：同 turn_shape_combo 的第二关（买点按实际挡掉的比例随机挡 400 次；卖点事件日在每只票
   自己的日序列上循环平移 400 次），候选严格大于 400 次里最大的才过。两关都过 =「更好候选」→ 报告给用户；进模拟盘 / 执行器要用户决定（不自动改）。
三 只描述：B4 实际成交在信号日的日线 / 周线通道分布、各通道的胜率 / 每笔；离周线压力线的距离三等分；各事件 / 各通道的个数；A1 / A2 / A3 的胜率与原始收益。
四 事前预期（运行前写，照实）：技术分析的「形态 / 趋势线」在学术上样本外的预测力弱、扣成本后多半没有（例：Lo, Mamaysky & Wang 2000 只找到很小的信息量）。
   A1：上升通道多半略强于下降通道（中短期动量），差约 +0.1〜0.3 pp / 20 日，与均线标签高度重叠 → ① 可能有的样本 > 0 但合起来不到 0.3 pp，② 多半不过；
   A2：突破压力约 +0.1〜0.3 pp（与现行箱顶突破同一类），回踩支撑接近 0；A3：跌破支撑约 −0.1〜−0.3 pp → 都不到 0.3 pp 的门槛；
   B：TLB1 / TLB2 碰到的 B4 成交少（突破日多半已经在周线压力之上），账户几乎不变；TLS1 = 早卖（像 TXF：胜率升、每笔降、账户变差）；
   TLS2 多半在 X6 之后才出现 → 几乎不触发；TLS3 = 早止盈（现行靠赔率赚钱 → 变差）。每个做法第一关约 2〜5%，两关都过约 1%。
五 局限：日経225 用今天的成员（幸存者偏差）；Jx 不按当时的成员筛；调整后价；之后 20 日的超额是「同一天同一样本的等权平均」为基准（不是指数）；
   事件与样本日在时间上重叠（按月聚类只部分处理）；趋势线的参数（k / L / gap / R / 0.3 ATR / ε）是看了几张图的画法定的（只看图形，没看任何收益），
   换参数结论可能不同；多重检验：A 部分 2 + 2 + 2 + 1 个判断、B 部分 5 个做法。模拟盘 / 执行器不因这次研究改。非投资建议。
登记前只数个数（--prep，2026-10-06；不算任何结果）：见 var/sim_changes.md 的登记节（个数写在那里，与本文件同一次提交）。
用法：python scripts/trendline_study.py --prep（算趋势线旗子 + 先决条件 + 只数个数；缓存 var/cache/trendline_study_flags.pkl，不入库）；
      python scripts/trendline_study.py --run（只运行一次：A + B 第一关 + 只描述）。
输出：var/out/trendline_study.md / .json（只有汇总统计，没有个股名单）。非投资建议。
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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qbreak import kline as K                                               # noqa: E402
from qbreak import trendline as TL                                          # noqa: E402

IDS = ("TLB1", "TLB2", "TLS1", "TLS2", "TLS3")
KIND = {"TLB1": "buy", "TLB2": "buy", "TLS1": "sell", "TLS2": "sell", "TLS3": "sell"}
COL = {"TLB1": "w_down_below", "TLB2": "w_near_res", "TLS1": "d_sb", "TLS2": "w_sb_evt", "TLS3": "w_res_touch"}
NAMES = {"TLB1": "周线下降通道里的突破不买", "TLB2": "上方周线压力线太近不买", "TLS1": "收盘跌破日线支撑线就卖",
         "TLS2": "周线收盘跌破周线支撑线就卖", "TLS3": "碰到周线压力线就卖（止盈）"}
POSTHOC = {k: False for k in IDS}
N225_ERAS = ("Z", "E", "J")
POOLS = ("W", "Jx", "Zx")
SAMPLES = ("Z", "E", "J", "W", "Jx", "Zx")
SM_KEY = {"Z": "Z", "E": "E", "J": "J", "W": "W", "Jx": "J2", "Zx": "Zx"}      # 行情在 W["SM"] 的哪个键
WIN_ERA = {"Z": "Z", "E": "E", "J": "J", "W": "E", "Jx": "J", "Zx": "Z"}       # 用哪个年代的窗口 / 交易日
FOLD = {"W": "E", "Jx": "J", "Zx": "Z"}                                       # 池子用哪一折的 C
H = 20                                                                        # 之后 20 个交易日
EVERY = 5                                                                     # A1：每 5 个交易日取一天
MIN_GROUP = 5
MIN_PP = 0.3
NEAR_ATR = 1.0
CH_CODE = {name: i + 1 for i, name in enumerate(TL.CHANNELS)}                 # 0 = 没有（两条线缺一条）
UP, DOWN = CH_CODE["上升通道"], CH_CODE["下降通道"]
EVENTS_BUY = {"TU": ("d_rb_new", "突破压力"), "TR": ("d_sh_up_new", "回踩支撑（支撑线向上）")}
EVENTS_SELL = {"TD": ("d_sb_new", "跌破支撑"), "TF": ("d_rh_dn_new", "碰压力回落（压力线向下）")}
EVENTS_WEEK = {"WU": ("w_rb_evt_new", "周线突破压力"), "WD": ("w_sb_evt_new", "周线跌破支撑")}
FP = "1241753c8f2529c6"                                                       # B4 = B3 + TBF 的模拟盘规则指纹
B4_TOL = 0.005                                                                # 同 nisa_tax_study.same_b4（笔数、胜率相同，Calmar 差 ≤ 0.005）
FLAGS_CACHE = "trendline_study_flags.pkl"
OUT_MD, OUT_JSON = "trendline_study.md", "trendline_study.json"
STOCK_SKIP = ("1545.T", "1482.T", "1655.T", "2845.T")


# ───────────────────────── 一只票的旗子（只用到当天为止的 K 线） ─────────────────────────
def _codes(sup_slope: np.ndarray, res_slope: np.ndarray, tf: str) -> np.ndarray:
    e = TL.EPS[tf]
    out = np.zeros(len(sup_slope), np.int8)
    ok = np.isfinite(sup_slope) & np.isfinite(res_slope)
    s = np.where(sup_slope > e, 1, np.where(sup_slope < -e, -1, 0))
    r = np.where(res_slope > e, 1, np.where(res_slope < -e, -1, 0))
    for (a, b), name in {(1, 1): "上升通道", (-1, -1): "下降通道", (0, 0): "横盘通道", (1, -1): "对称三角", (1, 0): "上升三角",
                         (0, -1): "下降三角"}.items():
        out[ok & (s == a) & (r == b)] = CH_CODE[name]
    out[ok & (out == 0)] = CH_CODE["扩散"]
    return out


def ma_label(c: pd.Series) -> np.ndarray:
    """qbreak/kline.trend 的定义逐日算：1 上升、−1 下降、0 震荡 / 不够。"""
    ma5, ma20 = c.rolling(5).mean(), c.rolling(20).mean()
    slope = ma20 / ma20.shift(K.SLOPE_BARS) - 1
    up = (c > ma20) & (slope > 0) & (ma5 > ma20)
    dn = (c < ma20) & (slope < 0) & (ma5 < ma20)
    return np.where(up, 1, np.where(dn, -1, 0)).astype(np.int8)


def ticker_flags(df: pd.DataFrame) -> pd.DataFrame | None:
    """一只票的日线 → 逐日旗子（见文件开头〇）。"""
    d = df[["Open", "High", "Low", "Close"]].astype(float)
    d = d[d["Close"].notna()]
    if len(d) < 60:
        return None
    k = TL.PARAMS["D"][0]
    s = TL.scan(d, "D")
    c, o, hi = d["Close"].to_numpy(), d["Open"].to_numpy(), d["High"].to_numpy()
    out = pd.DataFrame(index=d.index)
    with np.errstate(invalid="ignore", divide="ignore"):
        fwd = (np.r_[c[H:], np.full(H, np.nan)] / np.r_[o[1:], np.nan] - 1) * 100
    out["fwd"] = fwd.astype(np.float32)
    out["d_ch"] = _codes(s["sup_slope"], s["res_slope"], "D")
    out["ma"] = ma_label(d["Close"])
    out["d_sb"] = s["sup_break"]
    out["d_rb_new"] = TL.first_events(s["res_break"], k)
    out["d_sb_new"] = TL.first_events(s["sup_break"], k)
    out["d_sh_up_new"] = TL.first_events(s["sup_hit"] & (np.nan_to_num(s["sup_slope"], nan=0) > TL.EPS["D"]), k)
    out["d_rh_dn_new"] = TL.first_events(s["res_hit"] & (np.nan_to_num(s["res_slope"], nan=0) < -TL.EPS["D"]), k)
    # 周线：第 t 天用上一根已经走完的周K（不含这一周）的线，往后延长一根 = 这一周的线值
    wb = K.bars(d, "W")
    out["w_ch"] = np.int8(0)
    for col in ("w_down_below", "w_near_res", "w_sb_evt", "w_sb_evt_new", "w_rb_evt_new", "w_res_touch"):
        out[col] = False
    out["w_res_dist"] = np.float32(np.nan)
    if len(wb) >= 2 * TL.PARAMS["W"][0] + 2:
        ws = TL.scan(wb, "W")
        wk = wb.index.searchsorted(d.index, side="left")                     # t 所在那一周的周K
        prev = wk - 1
        okp = prev >= 0
        pi = np.where(okp, prev, 0)
        w_res = np.where(okp, ws["res"][pi] + ws["res_b"][pi], np.nan)
        w_tol = np.where(okp, ws["tol"][pi], np.nan)
        w_ch = np.where(okp, _codes(ws["sup_slope"][pi], ws["res_slope"][pi], "W"), 0).astype(np.int8)
        out["w_ch"] = w_ch
        with np.errstate(invalid="ignore", divide="ignore"):
            out["w_res_dist"] = ((w_res / c - 1) * 100).astype(np.float32)
            watr = w_tol / TL.TOL_ATR                                         # 周线 ATR14
            below = c < w_res
            out["w_down_below"] = (w_ch == DOWN) & below
            out["w_near_res"] = np.isfinite(w_res) & below & ((w_res - c) < NEAR_ATR * watr)
            out["w_res_touch"] = np.isfinite(w_res) & (hi >= w_res - w_tol) & (c <= w_res + w_tol)
        last = np.zeros(len(d), bool)                                        # 那一周的最后一个交易日
        okw = wk < len(wb)
        last[okw] = wb.index[wk[okw]] == d.index[okw]
        wkc = np.where(okw, wk, 0)
        kw = TL.PARAMS["W"][0]
        sbw, rbw = TL.first_events(ws["sup_break"], kw), TL.first_events(ws["res_break"], kw)
        out["w_sb_evt"] = last & okw & ws["sup_break"][wkc]
        out["w_sb_evt_new"] = last & okw & sbw[wkc]
        out["w_rb_evt_new"] = last & okw & rbw[wkc]
    return out


def _flags_job(item):
    t, df = item
    try:
        return t, ticker_flags(df)
    except Exception as ex:                                                   # noqa: BLE001
        return t, repr(ex)


def build_flags(W: dict, say=print, workers: int = 4) -> dict:
    """6 个样本（日経225 三个年代 + 三个池子）的每只票旗子（并行）。Jx = J2 行情里不在日経225（J）的票。"""
    t0 = time.time()
    out: dict = {}
    n225_j = set(W["SM"]["J"]["fa"])
    for s in SAMPLES:
        fa = W["SM"][SM_KEY[s]]["fa"]
        items = [(t, fa[t][["Open", "High", "Low", "Close"]]) for t in sorted(fa)
                 if t.endswith(".T") and t not in STOCK_SKIP and not (s == "Jx" and t in n225_j)]
        res, bad = {}, []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for t, r in ex.map(_flags_job, items, chunksize=8):
                if isinstance(r, str):
                    bad.append((t, r))
                elif r is not None:
                    res[t] = r
        if bad:
            raise SystemExit(f"{s}：{len(bad)} 只票算不出旗子（例：{bad[:2]}）→ 停")
        out[s] = res
        say(f"{s}：{len(res)} 只票的旗子；{time.time() - t0:.0f}s")
    return out


# ───────────────────────── 查表 ─────────────────────────
def lookup(FL: dict, col: str, tickers, dates) -> np.ndarray:
    """（票, 日期）的旗子（找不到 → False）。"""
    out = np.zeros(len(tickers), bool)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        f = FL.get(str(t))
        if f is None:
            continue
        k = f.index.get_indexer([pd.Timestamp(d)])[0]
        if k >= 0:
            out[i] = bool(f[col].iloc[k])
    return out


def value_at(FL: dict, col: str, tickers, dates) -> np.ndarray:
    out = np.full(len(tickers), np.nan)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        f = FL.get(str(t))
        if f is None:
            continue
        k = f.index.get_indexer([pd.Timestamp(d)])[0]
        if k >= 0:
            out[i] = float(f[col].iloc[k])
    return out


def event_ticks(FL: dict, col: str, only: set | None = None) -> dict[str, frozenset]:
    """事件日 → candle_portfolio.run 的 exit_tick {票: {收盘日, …}}（那天收盘还拿着 → 第二天开盘卖）。"""
    out = {}
    for t, f in FL.items():
        if only is not None and t not in only:
            continue
        v = f[col].to_numpy(bool)
        if v.any():
            out[t] = frozenset(pd.DatetimeIndex(f.index[v]).normalize())
    return out


# ───────────────────────── 统计（按月聚类） ─────────────────────────
def cluster_mean(x, months) -> dict:
    """平均 + 按月聚类的稳健标准误（CR0）→ 95% 区间。"""
    x = np.asarray(x, float)
    m = np.asarray(months)
    ok = np.isfinite(x)
    x, m = x[ok], m[ok]
    n = len(x)
    if n < 2:
        return {"n": int(n), "mean": float(x.mean()) if n else None, "se": None, "lo": None, "hi": None, "clusters": int(len(set(m)))}
    mu = float(x.mean())
    g = pd.Series(x - mu).groupby(pd.Series(m)).sum().to_numpy()
    se = float(np.sqrt((g ** 2).sum()) / n)
    return {"n": int(n), "mean": round(mu, 4), "se": round(se, 4), "lo": round(mu - 1.96 * se, 4), "hi": round(mu + 1.96 * se, 4),
            "clusters": int(len(g))}


def _win(lo: str, hi: str | None):
    return pd.Timestamp(lo), pd.Timestamp(hi) if hi else pd.Timestamp("2026-10-01")


def sample_panel(FL: dict, window, cols: list[str]) -> pd.DataFrame:
    """一个样本在窗口内的长表（日期、票、超额 + 要的列）；超额 = 之后 20 日收益 − 同一天全部票（算得出的）的等权平均。"""
    a, b = window
    parts = []
    for t, f in FL.items():
        x = f.loc[(f.index >= a) & (f.index < b), ["fwd"] + cols]
        if len(x):
            parts.append(x.assign(ticker=t))
    P = pd.concat(parts).rename_axis("date").reset_index()
    P = P[np.isfinite(P["fwd"].to_numpy(float))]
    P["ex"] = P["fwd"] - P.groupby("date")["fwd"].transform("mean")
    P["month"] = P["date"].dt.strftime("%Y-%m")
    return P


def a1_spreads(P: pd.DataFrame, days: pd.DatetimeIndex, col: str, up, down) -> pd.DataFrame:
    """每 5 个交易日一天：上升组平均超额 − 下降组平均超额（两组各 ≥ 5 只）。"""
    pick = set(days[::EVERY])
    X = P[P["date"].isin(pick)]
    g = X.assign(u=X[col] == up, d=X[col] == down)
    rows = []
    for d, x in g.groupby("date"):
        u, dn = x.loc[x["u"], "ex"], x.loc[x["d"], "ex"]
        if len(u) >= MIN_GROUP and len(dn) >= MIN_GROUP:
            rows.append({"date": d, "spread": float(u.mean() - dn.mean()), "n_up": len(u), "n_dn": len(dn),
                         "hit_up": float((u > 0).mean()), "hit_dn": float((dn < 0).mean())})
    return pd.DataFrame(rows)


def part_a(FLS: dict, W: dict, say=print) -> dict:
    out: dict = {"A1": {}, "A2": {}, "A3": {}, "AW": {}, "raw": {}}
    pooled = {"tl": [], "ma": [], "diff": [], **{k: [] for k in (*EVENTS_BUY, *EVENTS_SELL, *EVENTS_WEEK)}}
    for s in SAMPLES:
        e = WIN_ERA[s]
        win = _win(*W["ctx"][e]["windows"][e])
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        days = days[(days >= win[0]) & (days < win[1])]
        cols = ["d_ch", "ma"] + [v[0] for v in (*EVENTS_BUY.values(), *EVENTS_SELL.values(), *EVENTS_WEEK.values())]
        P = sample_panel(FLS[s], win, cols)
        tl = a1_spreads(P, days, "d_ch", UP, DOWN)
        ma = a1_spreads(P, days, "ma", 1, -1)
        both = tl.merge(ma, on="date", suffixes=("_tl", "_ma"))
        mon = lambda X: X["date"].dt.strftime("%Y-%m").to_numpy()            # noqa: E731
        r = {"days": int(len(tl)), "tl": cluster_mean(tl["spread"], mon(tl)) if len(tl) else None,
             "ma": cluster_mean(ma["spread"], mon(ma)) if len(ma) else None,
             "diff": cluster_mean(both["spread_tl"] - both["spread_ma"], mon(both)) if len(both) else None,
             "hit_tl": [round(float(tl["hit_up"].mean() * 100), 2), round(float(tl["hit_dn"].mean() * 100), 2)] if len(tl) else None,
             "hit_ma": [round(float(ma["hit_up"].mean() * 100), 2), round(float(ma["hit_dn"].mean() * 100), 2)] if len(ma) else None,
             "n_up_mean": round(float(tl["n_up"].mean()), 1) if len(tl) else None, "n_dn_mean": round(float(tl["n_dn"].mean()), 1) if len(tl) else None}
        out["A1"][s] = r
        for key, X in (("tl", tl), ("ma", ma)):
            if len(X):
                pooled[key].append(pd.DataFrame({"v": X["spread"].to_numpy(), "m": mon(X)}))
        if len(both):
            pooled["diff"].append(pd.DataFrame({"v": (both["spread_tl"] - both["spread_ma"]).to_numpy(), "m": mon(both)}))
        for grp, evs in (("A2", EVENTS_BUY), ("A3", EVENTS_SELL), ("AW", EVENTS_WEEK)):
            out[grp][s] = {}
            for k, (col, _) in evs.items():
                x = P[P[col].astype(bool)]
                st = cluster_mean(x["ex"], x["month"])
                st["win"] = round(float((x["ex"] > 0).mean() * 100), 2) if len(x) else None
                st["raw"] = round(float(x["fwd"].mean()), 4) if len(x) else None
                out[grp][s][k] = st
                pooled[k].append(pd.DataFrame({"v": x["ex"].to_numpy(), "m": x["month"].to_numpy()}))
        out["raw"][s] = {"rows": int(len(P)), "tickers": int(P["ticker"].nunique()), "mean_fwd": round(float(P["fwd"].mean()), 4)}
        say(f"A {s}：{len(P)} 行、{P['ticker'].nunique()} 只票")
    out["pooled"] = {}
    for k, parts in pooled.items():
        if parts:
            X = pd.concat(parts)
            out["pooled"][k] = cluster_mean(X["v"], X["m"])
    out["judge"] = judge_a(out)
    return out


def judge_a(a: dict) -> dict:
    """一的判定（见文件开头）。"""
    def means(grp: str, key: str) -> list:
        return [((a[grp].get(s) or {}).get(key) or {}).get("mean") for s in SAMPLES]
    p = a["pooled"]
    tl_vals = means("A1", "tl")
    tl_all = all(v is not None and v > 0 for v in tl_vals)
    j = {"A1_predict": bool(tl_all and (p.get("tl") or {}).get("lo") is not None and p["tl"]["lo"] > 0 and p["tl"]["mean"] >= MIN_PP),
         "A1_tl_each": tl_vals}
    dvals = means("A1", "diff")
    j["A1_beats_ma"] = bool(sum(1 for v in dvals if v is not None and v > 0) >= 5 and (p.get("diff") or {}).get("lo") is not None
                            and p["diff"]["lo"] > 0)
    j["A1_diff_each"] = dvals
    for grp, evs, sign in (("A2", EVENTS_BUY, 1), ("A3", EVENTS_SELL, -1)):
        for k in evs:
            vals = means(grp, k)
            q = p.get(k) or {}
            ok_each = all(v is not None and v * sign > 0 for v in vals)
            if sign > 0:
                ok = ok_each and q.get("lo") is not None and q["lo"] > 0 and q["mean"] >= MIN_PP
            else:
                ok = ok_each and q.get("hi") is not None and q["hi"] < 0 and q["mean"] <= -MIN_PP
            j[k] = bool(ok)
            j[f"{k}_each"] = vals
    return j


# ───────────────────────── 二：结合 B4 ─────────────────────────
def tbf_gates(W: dict, say=print) -> tuple[dict, dict]:
    """TBF 旗子（turn_shape_combo 的缓存）：日経225 每个年代的 W2 信号要不要挡 + 池子信号的 TBF。"""
    import turn_shape_combo as TC
    F = TC.load_flags(W, TC.load_models(say)["fits"], say)
    g = TC.gates_of(W, F, "TBF")
    pools = {}
    for s in POOLS:
        X = pool_x(W, s)
        f = F[s]
        pools[s] = TC.lookup(f["rules"]["TBF"], f["days"], f["names"], X["ticker"], X["date"])
    return {e: np.asarray(g[e], bool) for e in N225_ERAS}, pools


def pool_x(W: dict, s: str) -> pd.DataFrame:
    import loop10_common as C10
    return C10.kept_pool(W, s, FOLD[s])


def b4_trades(W: dict, e: str, tbf: np.ndarray, FL: dict) -> pd.DataFrame:
    """B4 实际成交（窗口内买入、已平仓的日本个股）+ 信号日的通道 / 离周线压力（只描述用）。"""
    import jq_study as JS
    import loop9_common as C9
    C9.run_block(W, e, tbf)
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    a, b = _win(*W["ctx"][e]["windows"][e])
    tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(STOCK_SKIP) & (tr["reason"] != "end")]
    ed = pd.to_datetime(tr["entry_date"])
    tr = tr[((ed >= a) & (ed < b)).to_numpy()].reset_index(drop=True)
    days = pd.DatetimeIndex(W["ctx"][e]["days"])
    sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]
    net = tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100
    return pd.DataFrame({"ticker": tr["ticker"].astype(str), "fill": pd.to_datetime(tr["entry_date"]), "sig": pd.DatetimeIndex(sig), "net": net,
                         "d_ch": value_at(FL, "d_ch", tr["ticker"], sig), "w_ch": value_at(FL, "w_ch", tr["ticker"], sig),
                         "w_res_dist": value_at(FL, "w_res_dist", tr["ticker"], sig)})


def window_has(FL: dict, col: str, tickers, fills, n: int = 60) -> np.ndarray:
    """（票, 成交日）之后 n 个交易日（含成交日收盘）里有没有事件日（只数个数用）。"""
    out = np.zeros(len(tickers), bool)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(fills)))):
        f = FL.get(str(t))
        if f is None:
            continue
        k = int(f.index.searchsorted(pd.Timestamp(d)))
        out[i] = bool(f[col].to_numpy(bool)[k:k + n].any())
    return out


def counts(W: dict, FLS: dict, tbf: dict, tbf_pool: dict, b4tr: dict | None) -> dict:
    """登记前只数个数：每个做法碰到多少（日経225 W2 信号 / B4 成交 / 池子里 B4 会买的信号）、A 部分各样本的样本日 / 事件个数。"""
    import loop9_common as C9
    out: dict = {"n225": {}, "pools": {}, "A": {}}
    for e in N225_ERAS:
        S = C9.signals(W, e)
        g = tbf[e]
        r = {"signals": int(len(S)), "not_tbf": int((~g).sum())}
        tr = (b4tr or {}).get(e)
        if tr is not None:
            r["b4_trades"] = int(len(tr))
        for k in IDS:
            if KIND[k] == "buy":
                hit = lookup(FLS[e], COL[k], S["ticker"], S["date"]) & ~g
                r[k] = {"signals": int(hit.sum())}
                if tr is not None:
                    r[k]["b4_trades"] = int(lookup(FLS[e], COL[k], tr["ticker"], tr["sig"]).sum())
            else:
                r[k] = {"event_days": int(sum(int(f[COL[k]].sum()) for f in FLS[e].values()))}
                if tr is not None:
                    r[k]["b4_trades_60d"] = int(window_has(FLS[e], COL[k], tr["ticker"], tr["fill"]).sum())
        out["n225"][e] = r
    for s in POOLS:
        X = pool_x(W, s)
        keep = ~tbf_pool[s]
        Xk = X[keep]
        r = {"signals": int(len(X)), "b4_buy": int(keep.sum())}
        for k in IDS:
            if KIND[k] == "buy":
                r[k] = int(lookup(FLS[s], COL[k], Xk["ticker"], Xk["date"]).sum())
            else:
                nxt = [pd.Timestamp(d) + pd.Timedelta(days=1) for d in pd.to_datetime(Xk["date"])]
                r[k] = int(window_has(FLS[s], COL[k], Xk["ticker"], nxt).sum())
        out["pools"][s] = r
    for s in SAMPLES:
        e = WIN_ERA[s]
        a, b = _win(*W["ctx"][e]["windows"][e])
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        pick = set(days[(days >= a) & (days < b)][::EVERY])
        n_up = n_dn = n_ma_up = n_ma_dn = rows = 0
        ev = {k: 0 for k in (*EVENTS_BUY, *EVENTS_SELL, *EVENTS_WEEK)}
        for f in FLS[s].values():
            x = f[(f.index >= a) & (f.index < b)]
            rows += len(x)
            on = x.index.isin(pick)
            n_up += int((x["d_ch"].to_numpy()[on] == UP).sum())
            n_dn += int((x["d_ch"].to_numpy()[on] == DOWN).sum())
            n_ma_up += int((x["ma"].to_numpy()[on] == 1).sum())
            n_ma_dn += int((x["ma"].to_numpy()[on] == -1).sum())
            for kk, (col, _) in (*EVENTS_BUY.items(), *EVENTS_SELL.items(), *EVENTS_WEEK.items()):
                ev[kk] += int(x[col].sum())
        out["A"][s] = {"tickers": len(FLS[s]), "rows": rows, "sample_days": len(pick), "up": n_up, "down": n_dn, "ma_up": n_ma_up,
                       "ma_down": n_ma_dn, **ev}
    return out


def run_cand(W: dict, e: str, k: str, tbf: np.ndarray, FL: dict) -> dict:
    import loop6_common as L6
    import loop9_common as C9
    S = C9.signals(W, e)
    if KIND[k] == "buy":
        g = tbf | lookup(FL, COL[k], S["ticker"], S["date"])
        return C9.acct(C9.run_block(W, e, g))
    tick = C9.tick_of(S["ticker"], S["date"], tbf)
    tk = event_ticks(FL, COL[k])
    return C9.acct(L6.run(W, e, em_tick=tick, exit_tick=tk) if tk else L6.run(W, e, em_tick=tick))


def pool_stats(W: dict, FL: dict, k: str, s: str, tbf_pool: np.ndarray) -> dict:
    """池子 s 里 B4 会买的信号的假想单笔：买点 = 保留的 vs 全部；卖点 = 「X6 + 事件」vs「X6」配对（turn_shape_combo.single_with_events）。"""
    import combo_all_common as CA
    import loop11_common as LC
    import turn_shape_combo as TC
    X = pool_x(W, s)[~tbf_pool].reset_index(drop=True)
    if KIND[k] == "buy":
        g = lookup(FL, COL[k], X["ticker"], X["date"])
        net = X["net"].to_numpy(float)
        dl = CA.delta(net, ~g)
        gone = net[g]
        return {"n": int(dl["n"]), "kept": int(dl["kept"]), "changed": int(g.sum()), "dwin": dl["dwin"], "dmean": dl["dmean"],
                "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
    p0 = W["p0"]
    bt, rt = LC.bt_rt()
    fa = W["SM"][SM_KEY[s]]["fa"]
    ticks = event_ticks(FL, COL[k], only=set(X["ticker"]))
    nb, nv = [], []
    for t, d in zip(X["ticker"], pd.to_datetime(X["date"])):
        df = fa.get(t)
        a, b = (np.nan, np.nan) if df is None else TC.single_with_events(t, df, d, p0, bt, rt, ticks.get(t))
        nb.append(a)
        nv.append(b)
    nb, nv = np.asarray(nb, float), np.asarray(nv, float)
    st = LC.pair_stats(nb, nv, np.isfinite(nb) & np.isfinite(nv) & ~np.isclose(nb, nv, atol=1e-9))
    st["base_match"] = int(np.sum(np.isclose(nb, X["net"].to_numpy(float), atol=1e-6)))
    return st


def describe_b4(b4tr: dict) -> dict:
    """只描述：B4 实际成交按信号日的日线 / 周线通道、离周线压力（三等分）→ 胜率 / 每笔（成交的净 %，引擎的 pnl ÷ 成本）。"""
    inv = {v: k for k, v in CH_CODE.items()}
    out = {}
    for e, tr in b4tr.items():
        r = {"n": int(len(tr)), "d_ch": {}, "w_ch": {}, "w_res_dist": {}}
        for col in ("d_ch", "w_ch"):
            for code, x in tr.groupby(tr[col].fillna(0).astype(int)):
                r[col][inv.get(code, "（缺一条线）")] = {"n": int(len(x)), "win": round(float((x["net"] > 0).mean() * 100), 1),
                                                       "mean": round(float(x["net"].mean()), 2)}
        dist = tr["w_res_dist"].to_numpy(float)
        ok = np.isfinite(dist) & (dist > 0)
        r["w_res_dist"]["没有压力线或已在线上"] = {"n": int((~ok).sum()), "win": round(float((tr["net"][~ok] > 0).mean() * 100), 1) if (~ok).any() else None,
                                              "mean": round(float(tr["net"][~ok].mean()), 2) if (~ok).any() else None}
        if ok.sum() >= 9:
            q1, q2 = np.quantile(dist[ok], [1 / 3, 2 / 3])
            for lab, m in (("近", ok & (dist <= q1)), ("中", ok & (dist > q1) & (dist <= q2)), ("远", ok & (dist > q2))):
                r["w_res_dist"][lab] = {"n": int(m.sum()), "win": round(float((tr["net"][m] > 0).mean() * 100), 1),
                                       "mean": round(float(tr["net"][m].mean()), 2), "dist_max": round(float(dist[m].max()), 2)}
        out[e] = r
    return out


def same_b4(now: dict, ref: dict) -> bool:
    """B4 重算与参照是同一套规则（nisa_tax_study.same_b4 同一个判断）：个股笔数与胜率相同、Calmar 差 ≤ B4_TOL。"""
    try:
        return (int(now["n"]) == int(ref["n"]) and abs(float(now["win"]) - float(ref["win"])) < 1e-9
                and abs(float(now["calmar"]) - float(ref["calmar"])) <= B4_TOL + 1e-12)
    except (KeyError, TypeError, ValueError):
        return False


def prereq(W: dict, tbf: dict, say=print) -> dict:
    """规则指纹、B4 重算 = turn_shape_combo 的 TBF、接线核对（从来没拿过的票的事件日 → 账户不变）。"""
    import loop6_common as L6
    import loop9_common as C9
    import research_loop as RL
    from qbreak import paths
    fp_now = RL.rules_fingerprint(paths.PROJECT_ROOT / "var")
    ref = json.loads((paths.PROJECT_ROOT / "var" / "out" / "turn_shape_combo.json").read_text(encoding="utf-8"))["cand"]["TBF"]
    out = {"fingerprint": fp_now, "fp_ok": fp_now == FP, "base": {}, "ok": True}
    for e in N225_ERAS:
        S = C9.signals(W, e)
        g = tbf[e]
        if len(g) != len(S):
            raise SystemExit("TBF 旗子与信号对不上 → 停")
        b4 = C9.acct(C9.run_block(W, e, g))
        same_ref = same_b4(b4, ref[e])
        tick = C9.tick_of(S["ticker"], S["date"], g)
        fake = C9.acct(L6.run(W, e, em_tick=tick, exit_tick={"0000.T": frozenset([pd.Timestamp(W["ctx"][e]["days"][100]).normalize()])}))
        wired = all(fake.get(x) == b4.get(x) for x in ("calmar", "n", "cagr", "dd", "win", "mean"))
        out["base"][e] = b4
        out[e] = {"same_ref": bool(same_ref), "ref_calmar": ref[e]["calmar"], "wired": bool(wired)}
        out["ok"] &= bool(same_ref and wired)
        say(f"{e}：B4 Calmar {b4['calmar']}（参照 {ref[e]['calmar']}）、笔数 {b4['n']}（参照 {ref[e]['n']}）、胜率 {b4['win']}（参照 {ref[e]['win']}）"
            f"{'一致' if same_ref else '★ 不一致'}；接线核对 {'一致' if wired else '★ 不一致'}")
    out["ok"] &= out["fp_ok"]
    return out


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/trendline_study.py", "qbreak/trendline.py", "qbreak/kline.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def load_all(say=print) -> tuple[dict, dict, dict, dict]:
    import loop10_common as C10
    from qbreak import paths
    t0 = time.time()
    W = C10.load()
    say(f"载入 B3 + Zx：{time.time() - t0:.0f}s")
    tbf, tbf_pool = tbf_gates(W, say)
    cp = paths.sub("cache") / FLAGS_CACHE
    if cp.exists():
        with open(cp, "rb") as f:
            FLS = pickle.load(f)
        say("趋势线旗子：用 --prep 的缓存（同一份）")
    else:
        FLS = build_flags(W, say)
        with open(cp, "wb") as f:
            pickle.dump(FLS, f)
    return W, FLS, tbf, tbf_pool


def run(say=print) -> dict:
    import research_loop10 as R10
    import research_loop11 as R11
    t0 = time.time()
    W, FLS, tbf, tbf_pool = load_all(say)
    pre = prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit(f"先决条件不满足：{pre} → 停")
    base = pre["base"]
    res: dict = {"git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}, "base": base, "cand": {}, "other": {}, "stage1": {}}
    res["A"] = part_a(FLS, W, say)
    say(f"一 预测准确度完成；{time.time() - t0:.0f}s")
    for k in IDS:
        res["cand"][k] = {e: run_cand(W, e, k, tbf[e], FLS[e]) for e in N225_ERAS}
        res["other"][k] = {s: pool_stats(W, FLS[s], k, s, tbf_pool[s]) for s in POOLS}
        res["stage1"][k] = R11.stage1(res["cand"][k], base, res["other"][k], lenses=None, posthoc=POSTHOC[k])
        say(f"{k} 完成（第一关 {'过' if res['stage1'][k]['ok'] else '不过'}）；{time.time() - t0:.0f}s")
    b4tr = {e: b4_trades(W, e, tbf[e], FLS[e]) for e in N225_ERAS}
    res["describe"] = describe_b4(b4tr)
    res["counts"] = counts(W, FLS, tbf, tbf_pool, b4tr)
    res["success_base"] = R10.pooled_trades(base)
    res["elapsed_s"] = round(time.time() - t0)
    return res


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def _ci(x: dict | None, nd="{:+.2f}") -> str:
    if not x or x.get("mean") is None:
        return "—"
    return f"{_f(x['mean'], nd)}（{_f(x.get('lo'), nd)}〜{_f(x.get('hi'), nd)}，{x['n']:,}）"


def report(res: dict) -> str:
    A = res["A"]
    j = A["judge"]
    L = ["# 趋势线（连波谷 / 连波峰）能不能预测买卖点与走势、结合现在的选股方法（B4）会不会更好（scripts/trendline_study.py；只运行一次）", "",
         f"代码 {res['git']['rev']}{'（有未提交的改动！）' if res['git'].get('dirty') else ''}；先决条件：规则指纹 {res['prereq'].get('fingerprint')}、"
         "B4 重算 = turn_shape_combo 的 TBF、接线核对一致。判定按文件开头（登记版）。", "",
         "## 一 预测准确度（全部股票；之后 20 个交易日、相对同一天同一样本的等权平均，pp；括号 = 95% 区间（按月聚类）与个数）", "",
         "### A1 通道方向 → 之后 20 日（上升通道 − 下降通道；对照 = 均线趋势标签）", "",
         "| 样本 | 样本日 | 趋势线的差 | 均线标签的差 | 趋势线 − 均线 | 命中率（上升 / 下降，趋势线） | 命中率（均线） |", "|---|---|---|---|---|---|---|"]
    def hits(h):
        return "—" if not h else f"{h[0]:.1f}% / {h[1]:.1f}%"
    for s in SAMPLES:
        r = A["A1"][s]
        L.append(f"| {s} | {r['days']} | {_ci(r['tl'])} | {_ci(r['ma'])} | {_ci(r['diff'])} | {hits(r['hit_tl'])} | {hits(r['hit_ma'])} |")
    p = A["pooled"]
    L += [f"| 合起来 | — | {_ci(p.get('tl'))} | {_ci(p.get('ma'))} | {_ci(p.get('diff'))} | — | — |", "",
          f"- ①「能预测」：**{'过' if j['A1_predict'] else '不过'}**（6 个样本每个 > 0、合起来 95% 下限 > 0、平均 ≥ +{MIN_PP} pp）",
          f"- ②「比均线标签好」：**{'过' if j['A1_beats_ma'] else '不过'}**（≥ 5 个样本 > 0、合起来 95% 下限 > 0）", "",
          "### A2 买点事件 / A3 卖点事件（日线；之后 20 日超额，pp）", "",
          "| 事件 | " + " | ".join(SAMPLES) + " | 合起来 | 判定 |", "|---|" + "---|" * (len(SAMPLES) + 2)]
    for grp, evs in (("A2", EVENTS_BUY), ("A3", EVENTS_SELL)):
        for k, (_, lab) in evs.items():
            L.append(f"| {k} {lab} | " + " | ".join(_ci(A[grp][s][k]) for s in SAMPLES) + f" | {_ci(p.get(k))} | **{'有用' if j[k] else '没用'}** |")
    L += ["", "### 周线事件（只描述）", "", "| 事件 | " + " | ".join(SAMPLES) + " | 合起来 |", "|---|" + "---|" * (len(SAMPLES) + 1)]
    for k, (_, lab) in EVENTS_WEEK.items():
        L.append(f"| {k} {lab} | " + " | ".join(_ci(A["AW"][s][k]) for s in SAMPLES) + f" | {_ci(p.get(k))} |")
    L += ["", "## 二 结合现在的选股方法（B4 → 候选；第一关 = research_loop11.stage1，posthoc = False）", "",
          "| 做法 | 年代 | Calmar | 差 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    base = res["base"]
    for k in IDS:
        for e in N225_ERAS:
            b, c = base[e], res["cand"][k][e]
            L.append(f"| {k} {NAMES[k]} | {e} | {_f(b['calmar'], '{:.3f}')} → {_f(c['calmar'], '{:.3f}')} | "
                     f"{_f(None if c['calmar'] is None or b['calmar'] is None else c['calmar'] - b['calmar'])} | {_f(b['dd'], '{:.2f}')} → {_f(c['dd'], '{:.2f}')}% | "
                     f"{_f(c['h1'], '{:.3f}')} / {_f(c['h2'], '{:.3f}')}（B4 {_f(b['h1'], '{:.3f}')} / {_f(b['h2'], '{:.3f}')}） | {b['n']} → {c['n']} | "
                     f"{_f(b['win'], '{:.1f}')} → {_f(c['win'], '{:.1f}')}% | {_f(b['mean'], '{:+.2f}')} → {_f(c['mean'], '{:+.2f}')}% |")
    L += [""]
    for k in IDS:
        s = res["stage1"][k]
        ra, rb = s["routes"]["A"], s["routes"]["B"]
        o = res["other"][k]
        pools = "；".join(f"{q} {o[q].get('changed', 0)} / {o[q].get('n', 0)} 个信号{'被挡' if KIND[k] == 'buy' else '换了卖点'}"
                          f"（胜率差 {_f(o[q].get('dwin'), '{:+.2f}')} pp、每笔差 {_f(o[q].get('dmean'), '{:+.3f}')} pp）" for q in POOLS)
        L.append(f"- **{k}「{NAMES[k]}」**：路线 A " + " ".join(f"{x}{'✓' if ra[x] else '✗'}" for x in ("A1", "A2", "A3", "V4"))
                 + "；路线 B " + " ".join(f"{x}{'✓' if rb[x] else '✗'}" for x in ("B1", "B2", "B3", "V4"))
                 + "；Calmar 差 " + "、".join(f"{e} {_f(ra['d'].get(e))}" for e in N225_ERAS)
                 + f"（合计 {_f(ra['sum'])}）；胜率差 {_f(rb['dwin'], '{:+.2f}')} pp、每笔差 {_f(rb['dmean'], '{:+.3f}')} pp；{pools}（Zx 只描述）"
                 + f" → **{'第一关通过（要另行登记第二关）' if s['ok'] else '第一关不过'}**")
    L += ["", "## 三 只描述：B4 实际成交在信号日的通道（胜率 / 每笔，成交的净 %）", ""]
    for e, r in res["describe"].items():
        L.append(f"- {e}（{r['n']} 笔）日线：" + "；".join(f"{k} {v['n']} 笔 {v['win']}% / {v['mean']:+.2f}%" for k, v in r["d_ch"].items()))
        L.append("  周线：" + "；".join(f"{k} {v['n']} 笔 {v['win']}% / {v['mean']:+.2f}%" for k, v in r["w_ch"].items()))
        L.append("  离周线压力：" + "；".join(f"{k} {v['n']} 笔 {_f(v.get('win'), '{:.1f}')}% / {_f(v.get('mean'), '{:+.2f}')}%" for k, v in r["w_res_dist"].items()))
    L += ["", f"用时 {res['elapsed_s']} s。只有汇总统计。非投资建议。"]
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
        W, FLS, tbf, tbf_pool = load_all(say)
        pre = prereq(W, tbf, say)
        b4tr = {e: b4_trades(W, e, tbf[e], FLS[e]) for e in N225_ERAS}
        out = {"prereq": {k: v for k, v in pre.items() if k != "base"}, "counts": counts(W, FLS, tbf, tbf_pool, b4tr)}
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
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
