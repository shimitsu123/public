"""rebound_study.py — 专门的「超跌反弹」：个股周 / 月线严重向下脱离 → 买，专门的卖法，账户里单独一部分资金；探索 → 挑选 → 确认
（2026-09-28 事先登记：规则先提交再运行一次，结果出来不改规则）。

用户（2026-09-28）：「做一套专门的「超跌反弹」」。
来由（madev_event 180d597 / c8458f0）：个股 13 周线 ≤ −15%、下一个交易日仍 ≤ −15% 之后 20 个交易日平均跑赢等权大盘 +0.77%（五段都为正），
  12 个月线 −25% 之后 60 日 +1.74%，越深越强；但用「现行卖法 + 和突破共用 4 个名额」去买，逐笔每笔 +1.23%、组合 Calmar 三段都变差
  （扎堆在全市场大跌的日子、止损多、挤掉核心 1655）。这一轮针对这三点专门设计：只买个别股票自己的大跌、反弹用的卖法、和突破分开的资金。
以前做过的（不重复）：dip_study（a2c6fcd）日経225 **指数**的 RSI(2) 回调买 → 1990〜2005 不赚；leap_r4 每周 / 每月反转组合 → 两个年代不一致。

一 买点（事件定义与 madev_event 完全相同：只用已完成的周 / 月线、同一段只算第一次；事件日收盘成立 → 次日开盘买）
  E1 = N4：13 周线 ≤ −15%、下一个交易日仍 ≤ −15%（你的规则·周线）；持有上限 H = 20 个交易日
  E2 = N6：13 周线 ≤ −25%、下一个交易日仍 ≤ −25%（更深）；H = 20
  E3 = N5：12 个月线 ≤ −25%、下一个交易日仍 ≤ −25%（你的规则·月线）；H = 60
二 大盘过滤（只买个别股票自己的大跌）
  M0 不过滤；M1 事件日日経225 指数最近一根已完成周线的 13 周线乖离 > −6%（只看指数价格分布定：E∪J 1,041 周的 10 分位 −5.8% 取整；
  E / J 各自 10 分位 −7.4 / −3.9%）→ 大盘自己在大跌的日子不买。
三 卖法（专门为反弹设计；都是 −15% 止损 + 最多拿 H 个交易日；不用 MACD 死叉、跟踪止损、止盈、放量阴线）
  XA 到期卖：拿满 H 个交易日；
  XB 回到对应的线就卖：收盘 ≥ 这只票最近一根已完成 K 线的 13 周线（E1 / E2）/ 12 个月线（E3）→ 次日开盘卖，否则 H 天到期；
  XC 回到 25 日线就卖：收盘 ≥ 25 日均线 → 次日开盘卖，否则 H 天到期。
  （「现行卖法」上一轮已做 → 只作参照，不参选。）候选 18 个 = 3 × 2 × 3。
四 资金（和突破分开）：账户 75% 照现行（S0C2 + W2），25% 专门做超跌反弹（同一套 S0C2 框架：4 个名额 × 25%、闲置资金拿 1655 + 牛熊分界、
  新仓倍数照旧；同一天多个候选按代码顺序 = 现行做法）；两部分每个月第一个交易日再平衡回 75 / 25（回测里不另扣再平衡的费用）。
  另报 50 / 50 与只有超跌反弹（只描述）。
五 数据：探索 = E（2006-10〜2016-09 日経225，yfinance）、J（2017-01〜2026-09 日経225，J-Quants）、J2（同期时点 TOPIX 1000，只做逐笔）；
  确认 = Z（2001-01〜2006-09 日経225）+ W（另一批股票 714 只 2006-10〜2016-09），只用于入选的候选。
  照实写：Z / W 在 madev_event 里已经看过这三种超跌事件之后的超额收益、以及「现行卖法」的逐笔；这一轮新加的大盘过滤、反弹卖法、独立资金在 Z / W 上没看过。
六 探索的入选规则（E / J / J2；运行前写定）
  a 逐笔（每个事件单独一笔，扣 ¥25 万来回手续费）：E、J 各 ≥ 30 笔、J2 ≥ 50 笔；三段每段 每笔 > 0、胜率 ≥ 同一段现行突破的胜率、
    每笔 ≥ 同一段现行突破的每笔（现行突破 = 每个 W2 保留的突破单独一笔、现行卖法，同一做法）；
  b 账户（75 / 25）：E、J 各自 Calmar ≥ 现行 + 0.02、最大回撤不比现行深 2 pp 以上；
  排序 = min(E, J 的 Calmar 提高) 从大到小；同一种买点最多 1 个；最多 2 个入选。没有入选 → 这一轮到此为止，不看 Z / W。
七 确认（Z + W，只对入选的；运行前写定）
  c 逐笔合并 Z + W：每笔平均的 95% 下限 > 0（按信号所在日历月聚类的自助法 2,000 次，种子 20260928）、胜率 ≥ 合并的现行突破胜率、
    每笔 ≥ 合并的现行突破每笔；Z、W 各自每笔 > 0；
  d 账户 Z（75 / 25）：Calmar ≥ 现行、最大回撤不比现行深 2 pp 以上；
  c 与 d 都满足 →「通过」（结论上限：提议在模拟盘加一个 25% 的超跌反弹部分 —— 执行器也要改，要你另外确认，先做前向记录）；
  c 的点估计都满足、但 95% 下限或 d 没过 →「方向一致」；其余「不通过」。
八 另报（只描述）：每个候选逐笔的胜率、每笔、平均赚 / 亏、持有中位、出场原因；账户（75 / 25、50 / 50、只有超跌反弹）的年化 / 回撤 / Calmar；
  现行卖法（上一轮 D1〜D3）的逐笔作参照。
九 局限：只用收盘；日経225 与扩大池用今天的成分（Z / E / J / W 有幸存者偏差，J2 没有）；各段以前做过很多别的检验；调整后价；
  再平衡不计费用；税前。模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/rebound_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import madev_event as ME                                                     # noqa: E402
import madev_study as MD                                                     # noqa: E402
from qbreak import mtf                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

ENTRIES: dict[str, dict] = {"E1": {"ev": "N4", "hold": 20, "zh": "13 周线 ≤ −15%、下一个交易日仍 ≤ −15%（你的规则·周线）"},
                            "E2": {"ev": "N6", "hold": 20, "zh": "13 周线 ≤ −25%、下一个交易日仍 ≤ −25%"},
                            "E3": {"ev": "N5", "hold": 60, "zh": "12 个月线 ≤ −25%、下一个交易日仍 ≤ −25%（你的规则·月线）"}}
MFILTERS: dict[str, float | None] = {"M0": None, "M1": -6.0}
EXITS: dict[str, str] = {"XA": "到期卖", "XB": "回到对应的线就卖", "XC": "回到 25 日线就卖"}
STOP_PCT = 15.0
W_DIP = 0.25
EXPLORE, CONFIRM = ("E", "J", "J2"), ("Z", "W")
PORT_EXPLORE = ("E", "J")
MIN_N = {"E": 30, "J": 30, "J2": 50}
CAL_UP, DD_TOL = 0.02, 2.0
MAX_FINAL = 2
BOOT_N, SEED = 2000, 20260928
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def candidates() -> list[str]:
    return [f"{e}{m}{x}" for e in ENTRIES for m in MFILTERS for x in EXITS]


def parts(key: str) -> tuple[str, str, str]:
    return key[:2], key[2:4], key[4:6]


# ───────────────────────── 规则（纯函数，有测试）─────────────────────────
def dip_params(p, hold: int):
    """反弹用的卖法：−15% 止损、最多拿 hold 个交易日；死叉列另给（XB / XC 的「回到线」、XA 全 False）；不用跟踪 / 止盈 / 放量阴线。"""
    return replace(p, stop_loss_pct=STOP_PCT, atr_stop_mult=0.0, take_profit_pct=0.0, trailing_stop_pct=0.0, trailing_arm_pct=0.0,
                   max_hold_days=int(hold), exit_on_macd_dead_cross=True, exit_on_climax=False, time_stop_days=0, exit_before_earnings=False)


def exit_col(raw: pd.DataFrame, days: pd.DatetimeIndex, idx: pd.DatetimeIndex, kind: str, freq: str, n: int,
             bars: pd.DataFrame | None = None) -> np.ndarray:
    """卖出判定列（对齐 idx）：XA 全 False；XB 收盘 ≥ 最近一根已完成周 / 月线的 n 根均线；XC 收盘 ≥ 25 日均线。"""
    idx = pd.DatetimeIndex(idx)
    c = raw["Close"].astype(float).reindex(idx).to_numpy()
    if kind == "XA":
        return np.zeros(len(idx), bool)
    if kind == "XB":
        b = mtf.bars(raw, days, freq) if bars is None else bars
        ma = b["Close"].astype(float).rolling(n, min_periods=n).mean()
        line = mtf.state_on(pd.DataFrame({"m": ma}), idx)["m"].to_numpy(float)
        with np.errstate(invalid="ignore"):
            return np.isfinite(line) & (c >= line)
    if kind == "XC":
        m25 = raw["Close"].astype(float).rolling(25, min_periods=25).mean().reindex(idx).to_numpy()
        with np.errstate(invalid="ignore"):
            return np.isfinite(m25) & (c >= m25)
    raise ValueError(kind)


def index_dev_state(nk: pd.DataFrame, n: int = 13) -> pd.Series:
    """日経225 指数：每一天「最近一根已完成周线」的 13 周线乖离（%）；周线完成日用指数自己的交易日。"""
    raw = nk[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    b = mtf.bars(raw, raw.index, "W")
    dev = MD.dev_of(b, n) * 100
    return mtf.state_on(pd.DataFrame({"d": dev}), raw.index)["d"]


def market_ok(dates, state: pd.Series, thr: float | None) -> np.ndarray:
    """thr = None → 全部 True；否则事件日（取 ≤ 那天的最后一个值）的指数乖离 > thr；没有值 → True（不挡）。"""
    dates = pd.DatetimeIndex(dates)
    if thr is None:
        return np.ones(len(dates), bool)
    pos = state.index.searchsorted(dates, side="right") - 1
    v = np.where(pos >= 0, state.to_numpy(float)[np.clip(pos, 0, None)], np.nan)
    return ~np.isfinite(v) | (v > thr)


def blend(a: pd.Series, b: pd.Series, w: float) -> pd.Series:
    """两部分资金：(1 − w) 跟 a、w 跟 b；每个月第一个交易日（当天收益之前）再平衡回原比例；返回合起来的净值（起点 1）。"""
    idx = a.index.intersection(b.index)
    ra = a.reindex(idx).pct_change().fillna(0.0).to_numpy()
    rb = b.reindex(idx).pct_change().fillna(0.0).to_numpy()
    mon = pd.DatetimeIndex(idx).to_period("M")
    va, vb = 1.0 - w, w
    out = np.empty(len(idx))
    for i in range(len(idx)):
        if i and mon[i] != mon[i - 1]:
            tot = va + vb
            va, vb = tot * (1.0 - w), tot * w
        va *= 1.0 + ra[i]
        vb *= 1.0 + rb[i]
        out[i] = va + vb
    return pd.Series(out, index=idx)


def trade_stats(T: pd.DataFrame, ci: bool = False) -> dict:
    return ME.trade_summary(T, ci=ci) if len(T) else {"n": 0}


def qualifies(tr: dict[str, dict], base: dict[str, dict], acct: dict[str, dict], acct0: dict[str, dict]) -> list[str]:
    """探索的入选条件（六 a / b）；返回没满足的条件（空 = 入选）。tr / base：{段: {n, win, mean}}；acct / acct0：{段: {calmar, dd}}。"""
    f = []
    for t in EXPLORE:
        x, y = tr.get(t) or {}, base.get(t) or {}
        if x.get("n", 0) < MIN_N[t]:
            f.append(f"{t} 笔数 < {MIN_N[t]}")
            continue
        if not x["mean"] > 0:
            f.append(f"{t} 每笔 ≤ 0")
        if y.get("n") and x["win"] < y["win"]:
            f.append(f"{t} 胜率低于现行突破")
        if y.get("n") and x["mean"] < y["mean"]:
            f.append(f"{t} 每笔低于现行突破")
    for t in PORT_EXPLORE:
        x, y = acct.get(t) or {}, acct0.get(t) or {}
        if None in (x.get("calmar"), y.get("calmar"), x.get("dd"), y.get("dd")):
            f.append(f"{t} 账户没有值")
            continue
        if x["calmar"] < y["calmar"] + CAL_UP:
            f.append(f"{t} 账户 Calmar 没高 {CAL_UP}")
        if x["dd"] < y["dd"] - DD_TOL:
            f.append(f"{t} 账户回撤深 {DD_TOL:.0f} pp 以上")
    return f


def pick(fails: dict[str, list], gain: dict[str, float]) -> list[str]:
    """入选的按 gain（min(E, J 的 Calmar 提高)）从大到小；同一种买点最多 1 个；最多 2 个。"""
    ok = sorted([k for k, f in fails.items() if not f], key=lambda k: (-gain[k], k))
    out, used = [], set()
    for k in ok:
        e = parts(k)[0]
        if e in used:
            continue
        out.append(k)
        used.add(e)
        if len(out) >= MAX_FINAL:
            break
    return out


def confirm_verdict(pool: dict, per: dict[str, dict], base_pool: dict, acct_z: dict, acct_z0: dict) -> dict:
    """七 c / d：pool = Z + W 合并逐笔 {n, win, mean, lo}；per：{Z, W: {mean}}；base_pool：合并现行突破 {win, mean}。"""
    c_point = (pool.get("n", 0) > 0 and pool["win"] >= base_pool.get("win", np.inf) and pool["mean"] >= base_pool.get("mean", np.inf)
               and all((per.get(t) or {}).get("mean", -1) > 0 for t in CONFIRM))
    c = c_point and pool.get("lo", -1) > 0
    d = (None not in (acct_z.get("calmar"), acct_z0.get("calmar"), acct_z.get("dd"), acct_z0.get("dd"))
         and acct_z["calmar"] >= acct_z0["calmar"] and acct_z["dd"] >= acct_z0["dd"] - DD_TOL)
    label = "通过" if c and d else ("方向一致" if c_point else "不通过")
    return {"c": bool(c), "c_point": bool(c_point), "d": bool(d), "label": label}


# ───────────────────────── 计算 ─────────────────────────
def events_of(S: dict, ev_keys) -> tuple[dict[str, pd.DataFrame], dict[str, dict]]:
    """{事件: 窗口里的事件表（ticker, date）}，{事件: {票: 全部事件日}}（成员日；与 madev_event.event_study 同一口径）。"""
    ctx, cols, M = S["ctx"], S["cols"], S["M"]
    P, days = ctx["P"], pd.DatetimeIndex(ctx["days"])
    a, b = pd.Timestamp(S["a"]), pd.Timestamp(S["b"])
    win: dict[str, list] = {k: [] for k in ev_keys}
    alld: dict[str, dict] = {k: {} for k in ev_keys}
    for jj, j in enumerate(cols):
        t = ctx["names"][j]
        raw = MD.raw_of(P, days, j)
        if len(raw) < 30:
            continue
        bars = {fq: mtf.bars(raw, days, fq) for fq in ("W", "M")}
        for k in ev_keys:
            ev = ME.EVENTS[k]
            ed = ME.event_days(raw, days, ev, bars[ev["freq"]])
            if not len(ed):
                continue
            e = days.get_indexer(ed)
            ok = (e >= 0) & M[np.clip(e, 0, None), jj]
            alld[k][t] = ed[ok]
            win[k] += [{"ticker": t, "date": d} for d in ed[ok] if a <= d <= b]
    return {k: pd.DataFrame(v, columns=["ticker", "date"]) for k, v in win.items()}, alld


def exit_cols(S: dict, tickers, kind: str, freq: str, n: int) -> dict[str, np.ndarray]:
    ctx, days = S["ctx"], pd.DatetimeIndex(S["ctx"]["days"])
    col = {t: j for j, t in enumerate(ctx["names"])}
    out = {}
    for t in tickers:
        df = S["fa"].get(t)
        if df is None:
            continue
        out[t] = exit_col(MD.raw_of(ctx["P"], days, col[t]), days, df.index, kind, freq, n)
    return out


def dip_trades(S: dict, ev: pd.DataFrame, ecol: dict[str, np.ndarray], pd_, bt, rt: float, end_bars: int = 90) -> pd.DataFrame:
    """每个事件单独一笔（反弹卖法）：ticker / date / net / hold / reason。"""
    import sell_confirm as SCF
    rows = []
    for r in ev.to_dict("records"):
        t, d = r["ticker"], pd.Timestamp(r["date"])
        df = S["fa"].get(t)
        if df is None or d not in df.index or t not in ecol:
            continue
        pos = int(df.index.get_loc(d))
        end = df.index[min(len(df) - 1, pos + end_bars)]
        f = df.assign(entry=np.asarray(df.index == d), dead_cross=ecol[t])
        x = SCF.one_trade(t, f, d, pd_, bt, end)
        if x is None or x["reason"] == "end":
            continue
        rows.append({"ticker": t, "date": d, "net": float(x["ret_pct"]) - rt, "hold": int(x["hold_days"]), "reason": x["reason"]})
    return pd.DataFrame(rows, columns=["ticker", "date", "net", "hold", "reason"])


def last_equity() -> pd.Series:
    import jq_study as JS
    h = JS.RealLotEngine.LAST[-1].st.history
    return pd.Series([x[1] for x in h], index=pd.DatetimeIndex([pd.Timestamp(x[0]) for x in h])).astype(float)


def acct_stats(eq: pd.Series, a: str, b: str | None) -> dict:
    import capital_study as CS
    return CS.seg_stats(eq, a, b)


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def main() -> int:
    import leap_confirm as LF
    import sell_confirm as SCF
    from bullbear_study import SYM, load
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 专门的「超跌反弹」：探索 → 挑选 → 确认（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/rebound_study.py 开头（运行前写定）。")
    nk_state = index_dev_state(load(*SYM["JP"]))
    evk = sorted({v["ev"] for v in ENTRIES.values()})
    TR: dict[str, dict] = {}                                                 # 候选 → 段 → 逐笔表
    BASE: dict[str, dict] = {}                                               # 段 → 现行突破逐笔统计
    ACCT: dict[str, dict] = {}                                               # 段 → {"现行": 统计, 候选: {75/25, 50/50, only}}
    SAMP: dict[str, dict] = {}

    def run_sample(tag: str, keys) -> None:
        t1 = time.time()
        S = ME.load_sample(tag, p0)
        EV, alld = events_of(S, evk)
        keepm = {t: np.asarray(S["keep"][t], bool) & np.asarray(S["member"][t], bool) for t in S["fa"]}
        Tb = ME.signal_trades(S["fa"], SCF.signals_of(S["fa"], keepm, S["a"], S["b"]), p0, bt, rt)
        BASE[tag] = {**trade_stats(Tb), "_T": Tb}
        ecache: dict[tuple, dict] = {}
        tcache: dict[tuple, pd.DataFrame] = {}                               # (买点, 卖法) → 不过滤的全部逐笔；M1 只是其中大盘不在大跌的那些
        allt = sorted({t for d in alld.values() for t in d})
        for k in keys:
            e, m, x = parts(k)
            freq, n = ("M", 12) if ENTRIES[e]["ev"] == "N5" else ("W", 13)
            if (x, freq, n) not in ecache:
                ecache[(x, freq, n)] = exit_cols(S, allt, x, freq, n)
            if (e, x) not in tcache:
                tcache[(e, x)] = dip_trades(S, EV[ENTRIES[e]["ev"]], ecache[(x, freq, n)], dip_params(p0, ENTRIES[e]["hold"]), bt, rt)
            T = tcache[(e, x)]
            T = T[market_ok(T["date"], nk_state, MFILTERS[m])].copy() if len(T) else T.copy()
            T["set"] = tag
            TR.setdefault(k, {})[tag] = T
        if tag in ("E", "J", "Z"):
            ctx, fa = S["ctx"], S["fa"]
            run_fn = LF.runner(ctx, fa)
            fw = LF.with_mask(fa, S["keep"])
            LF.run(ctx, run_fn, fw, p)
            eq0 = last_equity()
            wa, wb = ctx["windows"][tag]
            ACCT.setdefault(tag, {})["现行"] = acct_stats(eq0, wa, wb)
            for k in keys:
                e, m, x = parts(k)
                ok_dates = {}
                for t, ds in alld[ENTRIES[e]["ev"]].items():
                    ok_dates[t] = ds[market_ok(ds, nk_state, MFILTERS[m])]
                freq, n = ("M", 12) if ENTRIES[e]["ev"] == "N5" else ("W", 13)
                ecol = ecache[(x, freq, n)]
                fdip = {t: df.assign(entry=np.isin(df.index, ok_dates.get(t, pd.DatetimeIndex([]))),
                                     dead_cross=ecol.get(t, np.zeros(len(df), bool))) for t, df in fa.items()}
                LF.run(ctx, run_fn, fdip, dip_params(p, ENTRIES[e]["hold"]))
                eqd = last_equity()
                ACCT[tag][k] = {"75/25": acct_stats(blend(eq0, eqd, W_DIP), wa, wb), "50/50": acct_stats(blend(eq0, eqd, 0.5), wa, wb),
                                "only": acct_stats(eqd, wa, wb)}
        SAMP[tag] = {"a": S["a"], "b": S["b"]}
        say(f"- {tag}（{S['a']}〜{S['b']}）：现行突破 {BASE[tag].get('n', 0)} 笔；超跌事件 " + " / ".join(f"{k} {len(EV[k])}" for k in evk)
            + f"；{len(keys)} 个候选；{round(time.time() - t1)} s")

    for tag in EXPLORE:
        run_sample(tag, candidates())
    fails, gain = {}, {}
    for k in candidates():
        tr = {t: trade_stats(TR[k][t]) for t in EXPLORE}
        base = {t: BASE[t] for t in EXPLORE}
        acct = {t: ACCT[t][k]["75/25"] for t in PORT_EXPLORE}
        acct0 = {t: ACCT[t]["现行"] for t in PORT_EXPLORE}
        fails[k] = qualifies(tr, base, acct, acct0)
        g = [acct[t]["calmar"] - acct0[t]["calmar"] for t in PORT_EXPLORE if acct[t].get("calmar") is not None and acct0[t].get("calmar") is not None]
        gain[k] = min(g) if len(g) == len(PORT_EXPLORE) else -np.inf
    fin = pick(fails, gain)

    say("\n## 一、探索（E / J / J2；逐笔 = 每个事件单独一笔；账户 = 75% 现行 + 25% 超跌反弹，每月再平衡）")
    say("现行突破（同一做法）：" + "；".join(f"{t} {BASE[t]['n']} 笔 胜率 {fmt(BASE[t].get('win'), '{:.1f}')}%、每笔 {fmt(BASE[t].get('mean'))}%" for t in EXPLORE))
    say("账户现行：" + "；".join(f"{t} 年化 {fmt(ACCT[t]['现行'].get('cagr'), '{:.2f}')}% / 回撤 {fmt(ACCT[t]['现行'].get('dd'), '{:.2f}')}% / "
                               f"Calmar {fmt(ACCT[t]['现行'].get('calmar'), '{:.3f}')}" for t in PORT_EXPLORE))
    say("\n| 候选 | 逐笔 E（笔 / 胜率 / 每笔） | 逐笔 J | 逐笔 J2 | 账户 75/25 Calmar E / J（现行 → 候选） | 入选 |")
    say("|---|---|---|---|---|---|")
    for k in candidates():
        cells = []
        for t in EXPLORE:
            x = trade_stats(TR[k][t])
            cells.append("—" if not x.get("n") else f"{x['n']} / {x['win']:.1f}% / {x['mean']:+.2f}%")
        a_ = " / ".join(f"{fmt(ACCT[t]['现行'].get('calmar'), '{:.3f}')}→{fmt(ACCT[t][k]['75/25'].get('calmar'), '{:.3f}')}" for t in PORT_EXPLORE)
        say(f"| {k} | " + " | ".join(cells) + f" | {a_} | {'**入选**' if k in fin else '；'.join(fails[k][:3])} |")
    say(f"\n**入选（按规则，最多 2 个）：{'、'.join(fin) if fin else '没有'}**" + ("" if fin else " → 这一轮到此为止，不看 Z / W。"))
    say("\n候选编号 = 买点（E1 / E2 / E3）+ 大盘过滤（M0 不过滤 / M1 大盘不在大跌）+ 卖法（XA 到期 / XB 回到对应的线 / XC 回到 25 日线）。"
        + "买点：" + "；".join(f"{k} {v['zh']}（最多拿 {v['hold']} 个交易日）" for k, v in ENTRIES.items()))

    CONF = {}
    if fin:
        for tag in CONFIRM:
            run_sample(tag, fin)
        bpool = trade_stats(pd.concat([BASE[t]["_T"] for t in CONFIRM], ignore_index=True))
        for k in fin:
            pool = trade_stats(pd.concat([TR[k][t] for t in CONFIRM], ignore_index=True), ci=True)
            per = {t: trade_stats(TR[k][t]) for t in CONFIRM}
            CONF[k] = {"pool": pool, "per": per, "base_pool": bpool,
                       "verdict": confirm_verdict(pool, per, bpool, ACCT["Z"][k]["75/25"], ACCT["Z"]["现行"])}
        say("\n## 二、确认（Z + W；运行前写定）")
        for k in fin:
            v, x, bp = CONF[k]["verdict"], CONF[k]["pool"], CONF[k]["base_pool"]
            say(f"- **{k}**：逐笔合并 {x.get('n', 0)} 笔 胜率 {fmt(x.get('win'), '{:.1f}')}%（现行突破 {fmt(bp.get('win'), '{:.1f}')}%）、每笔 {fmt(x.get('mean'))}%"
                f"（95% 区间 {fmt(x.get('lo'))}〜{fmt(x.get('hi'))}；现行突破 {fmt(bp.get('mean'))}%）；Z {fmt(CONF[k]['per']['Z'].get('mean'))}% / "
                f"W {fmt(CONF[k]['per']['W'].get('mean'))}%；账户 Z Calmar {fmt(ACCT['Z']['现行'].get('calmar'), '{:.3f}')} → "
                f"{fmt(ACCT['Z'][k]['75/25'].get('calmar'), '{:.3f}')}、回撤 {fmt(ACCT['Z']['现行'].get('dd'), '{:.2f}')}% → "
                f"{fmt(ACCT['Z'][k]['75/25'].get('dd'), '{:.2f}')}% → **{v['label']}**")

    say("\n## 三、账户（年化 / 最大回撤 / Calmar；75 / 25、50 / 50、只有超跌反弹）")
    say("| 候选 | 段 | 75 / 25 | 50 / 50 | 只有超跌反弹 |")
    say("|---|---|---|---|---|")
    shown = fin if fin else sorted(candidates(), key=lambda c: -gain[c])[:4]
    for k in shown:
        for t in [x for x in ("E", "J", "Z") if x in ACCT and k in ACCT[x]]:
            r = ACCT[t][k]
            cell = lambda s: f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')}"  # noqa: E731
            say(f"| {k} | {t} | {cell(r['75/25'])} | {cell(r['50/50'])} | {cell(r['only'])} |")
    say("\n## 四、逐笔的形状（入选的，或探索里账户最好的 4 个；E / J / J2 / Z / W）")
    say("| 候选 | 段 | 笔数 | 胜率 | 每笔 | 平均赚 / 亏 | 持有中位 | 出场（止损 / 到期 / 回到线） |")
    say("|---|---|---|---|---|---|---|---|")
    for k in shown:
        for t, T in TR[k].items():
            x = trade_stats(T)
            if not x.get("n"):
                continue
            rs = T["reason"].value_counts(normalize=True).mul(100)
            say(f"| {k} | {t} | {x['n']} | {x['win']:.1f}% | {x['mean']:+.2f}% | {fmt(x.get('avg_win'))}% / {fmt(x.get('avg_loss'))}% | {x['hold']:.0f} 天 | "
                f"{rs.get('stop', 0) + rs.get('gap_stop', 0):.0f}% / {rs.get('max_hold', 0):.0f}% / {rs.get('dead_cross', 0):.0f}% |")
    out = {"code": code, "fails": fails, "gain": {k: (None if not np.isfinite(v) else v) for k, v in gain.items()}, "finalists": fin,
           "trades": {k: {t: trade_stats(T) for t, T in v.items()} for k, v in TR.items()},
           "base": {t: {kk: vv for kk, vv in b.items() if kk != "_T"} for t, b in BASE.items()}, "account": ACCT,
           "confirm": {k: {"pool": v["pool"], "per": v["per"], "base_pool": v["base_pool"], "verdict": v["verdict"]} for k, v in CONF.items()},
           "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {out['elapsed_s']} s）。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / "rebound_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
