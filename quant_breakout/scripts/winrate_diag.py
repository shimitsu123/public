"""winrate_diag.py — 诊断：现在的规则（B3）里日本个股的胜率为什么低（只描述、事后；不改规则、不提候选、不占任何研究循环的名额；
2026-10-04 用户「分析胜率低的原因 继续研究提高选股成功率 一直循环到 比现阶段的更好」的前一半）。

B3 = 模拟盘 / 执行器在用的那一套（W2 + C + X6 + 判断层 + 闲置资金 Q1B）；scripts/loop6_common.load3 + run（与 b3_trades_summary 同一个入口；
¥100 万起、立花费用、一手按当时真实股价）。三个年代 Z（2001-01〜2006-09）/ E（2006-10〜2016-09）/ J（2017-01〜2026-09）。
个股 = 买入日在年代窗口内、已经卖出的日本个股（不含期末未平仓、不含核心 ETF）。读法写在运行之前（先提交脚本，再只运行一次）：
一 盈亏结构：胜率（扣费用后 > 0）、平均赚 / 平均亏（每笔净收益 %）、盈亏比、保本胜率 = 平均亏 ÷（平均赚 + 平均亏）、每笔期望、胜率的 95% 区间（Wilson）。
   读法：实际胜率 > 保本胜率 → 「胜率低」是突破 + 吊灯止损这种买卖法（小亏多、大赚少）的结构，不是亏钱的原因。
二 亏损单的类型（持有期间 = 买入日〜卖出前一天的最高 / 最低价，相对买入价）：
   L1 一买就不涨：最高价从没到过买入价 +2%；L2 小涨过又跌回：到过 +2%〜+5%；L3 大涨过又跌回：到过 ≥ +5%；
   费用吃掉：价格涨跌 ≥ 0 但扣费用后 ≤ 0；另：离场原因、持有天数（5 / 10 个交易日以内卖出的比例）、赢家的最大不利。
   读法：L1 多 → 问题在「选股 / 买点」（假突破）；L3 多 → 问题在「卖法」（吊灯止损把涨过的还回去）。
三 大盘与核心：持有期间日経225（买入日收盘 → 卖出日收盘）涨 / 跌时的胜率；核心 1545 合成价（纳指 100 × 日元）同期涨跌 → 「跑赢核心」的比例
   （账户层面：挡掉一笔 = 这笔的钱留在核心，所以「跑不赢核心」才是真正拖后腿的；第四个循环的事后上限诊断同一个口径）。
四 进场时的状态：C 的四格（日経在 200 日线上 / 下 × VIX ≥ 20）、美股牛 / 熊；每格的笔数、胜率、每笔。
五 信号池 vs 实际成交：这个年代全部 W2 信号的假想单笔（研究面板 D：每个信号单独买、X6 离场、扣费用）→ C 保留 / C 挡掉（留一年代）→ B3 实际成交。
六 赢家与输家的个股特征：研究面板 D 的 C 保留部分，C 用的 46 个个股特征各自与每笔净收益的 Spearman 秩相关；三个年代都同号且 |ρ| ≥ 0.03 的列出来。
七 每个日历年的笔数与胜率（三个年代连起来）。
八 本金 ¥200 万多出来的交易：¥200 万的成交里 ¥100 万没有的（按 票 + 买入日）→ 笔数、胜率、每笔、一手金额中位。
只写汇总 → var/out/winrate_diag.md / .json；没有逐笔价格；原始行情只在内存。
用法：python scripts/winrate_diag.py（load3 约 5 分钟 + 运行约 1 分钟）。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

ERAS = ("Z", "E", "J")
OUT = ROOT / "var" / "out" / "winrate_diag"
CORE = ("1655.T", "1545.T", "1482.T", "2845.T")
MFE_LO, MFE_HI = 2.0, 5.0                                                    # 亏损单分类：最高到过 +2% / +5%
CAP2 = 2_000_000
RHO_MIN = 0.03


# ───────────────────────── 纯函数（tests/test_winrate_diag.py） ─────────────────────────
def stock_trades(trades: list[dict], a: str, b: str) -> pd.DataFrame:
    """引擎 st.trades → 窗口 [a, b) 里买入、已经卖出的日本个股（不含核心 ETF / 期末未平仓）；加 net（扣费用后 %）、fee_pp、win。"""
    tr = pd.DataFrame(trades)
    if not len(tr):
        return pd.DataFrame(columns=["ticker", "entry_date", "exit_date", "net", "gross", "fee_pp", "win"])
    tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(CORE) & (tr["reason"] != "end")]
    ed = pd.to_datetime(tr["entry_date"])
    tr = tr[((ed >= pd.Timestamp(a)) & (ed < pd.Timestamp(b))).to_numpy()].copy()
    cost = tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)
    tr["net"] = tr["pnl"].to_numpy(float) / cost * 100
    tr["gross"] = tr["ret_pct"].to_numpy(float)
    tr["fee_pp"] = tr["gross"] - tr["net"]
    tr["win"] = tr["pnl"].to_numpy(float) > 0
    tr["lot_yen"] = cost
    return tr.reset_index(drop=True)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """胜率的 95% 区间（%）。"""
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round((c - h) * 100, 1), round((c + h) * 100, 1)


def payoff(net) -> dict:
    """胜率、平均赚 / 平均亏、盈亏比、保本胜率、每笔期望（net = 每笔净收益 %；> 0 = 赚）。"""
    x = np.asarray(net, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if not n:
        return {"n": 0}
    w, l_ = x[x > 0], x[x <= 0]
    aw = float(w.mean()) if len(w) else None
    al = float(-l_.mean()) if len(l_) else None
    be = al / (aw + al) * 100 if aw is not None and al is not None and (aw + al) > 0 else None
    return {"n": n, "wins": int(len(w)), "win": round(len(w) / n * 100, 1), "ci": wilson(len(w), n), "mean": round(float(x.mean()), 2),
            "median": round(float(np.median(x)), 2), "avg_win": None if aw is None else round(aw, 2), "avg_loss": None if al is None else round(al, 2),
            "ratio": None if not aw or not al else round(aw / al, 2), "breakeven": None if be is None else round(be, 1),
            "best": round(float(x.max()), 2), "worst": round(float(x.min()), 2),
            "top5_share": round(float(np.sort(x)[::-1][:5].sum() / x.sum() * 100), 1) if x.sum() > 0 else None}


def path_extremes(df: pd.DataFrame, entry_date, exit_date, entry_px: float) -> tuple[float, float]:
    """持有期间（买入日〜卖出前一天）的最高 / 最低价相对买入价（%）；没有 K 线 → (nan, nan)。"""
    if df is None or not len(df):
        return float("nan"), float("nan")
    a, b = pd.Timestamp(entry_date), pd.Timestamp(exit_date)
    seg = df[(df.index >= a) & (df.index < b)]
    if not len(seg):
        seg = df[(df.index >= a) & (df.index <= b)]
    if not len(seg) or not entry_px:
        return float("nan"), float("nan")
    return (float(seg["High"].max()) / entry_px - 1) * 100, (float(seg["Low"].min()) / entry_px - 1) * 100


def loser_types(tr: pd.DataFrame) -> dict:
    """亏损单（扣费用后 ≤ 0）按持有期间最高到过多少分类；费用吃掉 = 价格涨跌 ≥ 0 但扣费用后 ≤ 0。"""
    lo = tr[~tr["win"].astype(bool)]
    n = len(lo)
    mfe = lo["mfe"].to_numpy(float) if "mfe" in lo else np.full(n, np.nan)
    ok = np.isfinite(mfe)
    l1 = int((ok & (mfe < MFE_LO)).sum())
    l2 = int((ok & (mfe >= MFE_LO) & (mfe < MFE_HI)).sum())
    l3 = int((ok & (mfe >= MFE_HI)).sum())
    fee = int(((lo["gross"].to_numpy(float) >= 0)).sum()) if n else 0
    hold = lo["hold_days"].to_numpy(float) if n else np.array([])
    pct = (lambda k: round(k / n * 100, 1) if n else None)
    return {"n": n, "L1": l1, "L2": l2, "L3": l3, "L1_pct": pct(l1), "L2_pct": pct(l2), "L3_pct": pct(l3), "fee_eaten": fee, "fee_eaten_pct": pct(fee),
            "unknown": int((~ok).sum()), "hold_median": float(np.median(hold)) if n else None,
            "within5_pct": pct(int((hold <= 5).sum())), "within10_pct": pct(int((hold <= 10).sum())),
            "loss_L1": round(float(lo["net"].to_numpy(float)[ok & (mfe < MFE_LO)].mean()), 2) if l1 else None,
            "loss_L3": round(float(lo["net"].to_numpy(float)[ok & (mfe >= MFE_HI)].mean()), 2) if l3 else None}


def group_stats(tr: pd.DataFrame, key: str) -> dict:
    out = {}
    for k, g in tr.groupby(key):
        p = payoff(g["net"])
        out[str(k)] = {"n": p["n"], "win": p.get("win"), "mean": p.get("mean")}
    return out


def ret_between(s: pd.Series, a, b) -> float:
    """收盘对收盘：a 当天（或之前最后一天）→ b 当天（或之前最后一天）的涨跌（%）。"""
    c = s.dropna()
    ia, ib = c.index.searchsorted(pd.Timestamp(a), "right") - 1, c.index.searchsorted(pd.Timestamp(b), "right") - 1
    if ia < 0 or ib < 0:
        return float("nan")
    return float((c.iloc[ib] / c.iloc[ia] - 1) * 100)


def consistent_features(D: dict, keeps: dict, feats: list[str], rho_min: float = RHO_MIN) -> list[dict]:
    """每个特征在每个年代（C 保留的假想单笔）与 net 的 Spearman；三个年代同号且 |ρ| 都 ≥ rho_min → 列出（按最小 |ρ| 排序）。"""
    import combo_all_common as CA
    rows = []
    for f in feats:
        rh = {}
        for e in ERAS:
            X = D[e][keeps[e]]
            if f not in X:
                rh[e] = None
                continue
            r = CA.spearman(X[f].to_numpy(float), X["net"].to_numpy(float))
            rh[e] = None if r is None or not np.isfinite(r) else float(r)
        v = [rh[e] for e in ERAS]
        if any(x is None for x in v):
            continue
        if (all(x > 0 for x in v) or all(x < 0 for x in v)) and min(abs(x) for x in v) >= rho_min:
            rows.append({"feature": f, "zh": CA.FEATURES[f][1], "rho": {e: round(rh[e], 3) for e in ERAS}, "min_abs": round(min(abs(x) for x in v), 3)})
    return sorted(rows, key=lambda r: -r["min_abs"])


# ───────────────────────── 计算 ─────────────────────────
def _series(x) -> pd.Series:
    return x["Close"].astype(float) if isinstance(x, pd.DataFrame) else pd.Series(x).astype(float)


def _signal_days(entry_dates, days) -> list[pd.Timestamp]:
    days = pd.DatetimeIndex(days)
    return [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(entry_dates)]


def era_window(W: dict, e: str) -> tuple[str, str]:
    a, b = W["ctx"][e]["windows"][e]
    return a, (b or str(pd.Timestamp(W["ctx"][e]["end"]) + pd.Timedelta(days=1))[:10])


def compute() -> dict:
    import combo_all_common as CA
    import jq_study as JS
    import loop6_common as L6
    t0 = time.time()
    W = L6.load3()
    n225 = _series(W["inp"]["n225"])
    core = W["assets"]["1545.T"]["Close"].astype(float)
    bear_us = W["bear"]["US"].astype(bool)
    res: dict = {"eras": {}, "years": {}}
    alltr = []
    keeps = {e: CA.apply_c(CA.fit_c([W["D"][x] for x in ERAS if x != e]), W["D"][e]) for e in ERAS}
    for e in ERAS:
        a, b = era_window(W, e)
        acct = L6.run(W, e)
        tr = stock_trades(JS.RealLotEngine.LAST[-1].st.trades, a, b)
        acct2 = L6.run(W, e, cfg_over={"capital_jpy": CAP2})
        tr2 = stock_trades(JS.RealLotEngine.LAST[-1].st.trades, a, b)
        fa = W["SM"][e]["fa"]
        ext = [path_extremes(fa.get(t), d0, d1, px) for t, d0, d1, px in zip(tr["ticker"], tr["entry_date"], tr["exit_date"], tr["entry_px"])]
        tr["mfe"] = [x[0] for x in ext]
        tr["mae"] = [x[1] for x in ext]
        tr["mkt"] = [ret_between(n225, d0, d1) for d0, d1 in zip(tr["entry_date"], tr["exit_date"])]
        tr["core"] = [ret_between(core, d0, d1) for d0, d1 in zip(tr["entry_date"], tr["exit_date"])]
        sig = _signal_days(tr["entry_date"], W["ctx"][e]["days"])
        A = W["A"][e].assign(date=pd.to_datetime(W["A"][e]["date"]))
        feat = A.set_index(["ticker", "date"])[["n225_ma200", "vix"]]
        key = list(zip(tr["ticker"], sig))
        m200 = np.array([feat["n225_ma200"].get(k, np.nan) if k in feat.index else np.nan for k in key], float)
        vix = np.array([feat["vix"].get(k, np.nan) if k in feat.index else np.nan for k in key], float)
        with np.errstate(invalid="ignore"):
            lab_ = np.char.add(np.where(m200 >= 0, "日経在 200 日线上", "日経在 200 日线下"), np.where(vix >= CA.C_VIX, "·VIX ≥ 20", "·VIX < 20"))
        cell = np.where(np.isfinite(m200) & np.isfinite(vix), lab_, "（不在信号面板）")
        tr["cell"] = cell
        bu = bear_us.reindex(pd.DatetimeIndex(sig), method="ffill")
        tr["us"] = np.where(bu.fillna(False).to_numpy(bool), "美股熊", "美股牛")
        win_m = tr[tr["mkt"].to_numpy(float) >= 0]
        los_m = tr[tr["mkt"].to_numpy(float) < 0]
        beat = tr["net"].to_numpy(float) > tr["core"].to_numpy(float)
        okc = np.isfinite(tr["core"].to_numpy(float))
        wins = tr[tr["win"]]
        Dd = W["D"][e]
        dd = pd.to_datetime(Dd["date"])
        inw = ((dd >= pd.Timestamp(a)) & (dd < pd.Timestamp(b))).to_numpy()
        k_ = np.asarray(keeps[e], bool)
        pool = {"all_w2": payoff(Dd["net"].to_numpy(float)[inw]), "c_keep": payoff(Dd["net"].to_numpy(float)[inw & k_]),
                "c_skip": payoff(Dd["net"].to_numpy(float)[inw & ~k_]), "executed": payoff(tr["net"])}
        new = tr2.merge(tr[["ticker", "entry_date"]], on=["ticker", "entry_date"], how="left", indicator=True)
        new = new[new["_merge"] == "left_only"]
        gone = tr.merge(tr2[["ticker", "entry_date"]], on=["ticker", "entry_date"], how="left", indicator=True)
        gone = gone[gone["_merge"] == "left_only"]
        res["eras"][e] = {
            "window": [a, b], "account": {k: acct.get(k) for k in ("cagr", "dd", "calmar")},
            "payoff": payoff(tr["net"]), "gross_mean": round(float(tr["gross"].mean()), 2) if len(tr) else None,
            "fee_mean_pp": round(float(tr["fee_pp"].mean()), 3) if len(tr) else None,
            "losers": loser_types(tr), "exit_reasons": {"all": dict(Counter(tr["reason"])), "losers": dict(Counter(tr.loc[~tr["win"], "reason"])),
                                                         "winners": dict(Counter(tr.loc[tr["win"], "reason"]))},
            "winner_mae_median": round(float(np.nanmedian(wins["mae"])), 2) if len(wins) else None,
            "winner_hold_median": float(np.median(wins["hold_days"])) if len(wins) else None,
            "market": {"up": payoff(win_m["net"]), "down": payoff(los_m["net"]),
                       "losers_market_down_pct": round(float((tr.loc[~tr["win"], "mkt"] < 0).mean() * 100), 1) if (~tr["win"]).any() else None},
            "core": {"beat_pct": round(float(beat[okc].mean() * 100), 1) if okc.any() else None,
                     "mean_minus_core": round(float((tr["net"] - tr["core"])[okc].mean()), 2) if okc.any() else None,
                     "winners_but_lag_core_pct": round(float(((tr["win"]) & ~beat & okc).sum() / max(1, int(tr["win"].sum())) * 100), 1)},
            "cells": group_stats(tr, "cell"), "us": group_stats(tr, "us"), "pool": pool,
            "cap2": {"account": {k: acct2.get(k) for k in ("cagr", "dd", "calmar")}, "n": int(len(tr2)), "payoff": payoff(tr2["net"]),
                     "new": {**payoff(new["net"]), "lot_median": round(float(new["lot_yen"].median())) if len(new) else None},
                     "gone": payoff(gone["net"]), "common_lot_median": round(float(tr["lot_yen"].median())) if len(tr) else None}}
        alltr.append(tr.assign(era=e))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    T = pd.concat(alltr, ignore_index=True)
    T["year"] = pd.to_datetime(T["entry_date"]).dt.year
    res["years"] = {str(y): {"n": int(len(g)), "win": round(float(g["win"].mean() * 100), 1), "mean": round(float(g["net"].mean()), 2)}
                    for y, g in T.groupby("year")}
    res["all"] = {"payoff": payoff(T["net"]), "losers": loser_types(T)}
    inwin = {}
    for e in ERAS:
        a, b = era_window(W, e)
        dd = pd.to_datetime(W["D"][e]["date"])
        inwin[e] = np.asarray(keeps[e], bool) & ((dd >= pd.Timestamp(a)) & (dd < pd.Timestamp(b))).to_numpy()
    res["features"] = consistent_features(W["D"], inwin, list(CA.STOCK_FEATS))
    res["exit_params"] = {k: getattr(W["px"], k) for k in ("stop_loss_pct", "atr_stop_mult", "take_profit_pct", "trailing_stop_pct", "exit_on_macd_dead_cross",
                                                         "exit_chandelier_k", "exit_on_climax", "max_hold_days", "time_stop_days") if hasattr(W["px"], k)}
    res["_seconds"] = round(time.time() - t0)
    return res


# ───────────────────────── 输出 ─────────────────────────
def _f(x, fmt="{:+.2f}", unit="%"):
    return "—" if x is None else fmt.format(x) + unit


def write(res: dict) -> str:
    lab = {"Z": "Z（2001-01〜2006-09）", "E": "E（2006-10〜2016-09）", "J": "J（2017-01〜2026-09）"}
    E = res["eras"]
    L = ["# 诊断：现在的规则（B3）里日本个股的胜率为什么低（只描述、事后；scripts/winrate_diag.py；读法写在脚本开头）", "",
         "B3 = 模拟盘 / 执行器在用的那一套；¥100 万起、立花费用、一手按当时真实股价；个股 = 买入日在年代窗口内、已经卖出的日本个股。", "",
         "## 一 盈亏结构（每笔净收益 = 扣立花费用后，% of 买入金额）", "",
         "| 年代 | 笔数 | 胜率（95% 区间） | 平均赚 | 平均亏 | 盈亏比 | 保本胜率 | 每笔期望 | 中位 | 最好 / 最差 | 最好 5 笔占总盈利 | 每笔费用 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in ERAS:
        p, r = E[e]["payoff"], E[e]
        ci = p.get("ci") or (None, None)
        L.append(f"| {lab[e]} | {p['n']} 笔 | {p['win']}%（{ci[0]}〜{ci[1]}%） | {_f(p['avg_win'])} | {_f(-p['avg_loss'] if p['avg_loss'] is not None else None)} | "
                 f"{p['ratio']} 倍 | {p['breakeven']}% | {_f(p['mean'])} | {_f(p['median'])} | {_f(p['best'])} / {_f(p['worst'])} | "
                 f"{_f(p['top5_share'], '{:.1f}')} | {_f(r['fee_mean_pp'], '{:.3f}', ' pp')} |")
    a = res["all"]["payoff"]
    L += ["", f"三个年代合计：{a['n']} 笔、胜率 {a['win']}%、平均赚 {_f(a['avg_win'])} / 平均亏 {_f(-a['avg_loss'])}、盈亏比 {a['ratio']} 倍、"
          f"保本胜率 {a['breakeven']}%、每笔 {_f(a['mean'])}。", "",
          "## 二 亏损单的类型（持有期间最高价相对买入价）", "",
          "| 年代 | 亏损笔数 | L1 一买就不涨（< +2%） | L2 小涨过又跌回（+2〜+5%） | L3 大涨过又跌回（≥ +5%） | 费用吃掉（价格 ≥ 0） | 亏损单持有中位 | 5 / 10 天内卖出 | L1 / L3 平均亏 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in ERAS:
        x = E[e]["losers"]
        L.append(f"| {lab[e]} | {x['n']} 笔 | {x['L1']} 笔（{x['L1_pct']}%） | {x['L2']} 笔（{x['L2_pct']}%） | {x['L3']} 笔（{x['L3_pct']}%） | "
                 f"{x['fee_eaten']} 笔（{x['fee_eaten_pct']}%） | {x['hold_median']} 个交易日 | {x['within5_pct']}% / {x['within10_pct']}% | "
                 f"{_f(x['loss_L1'])} / {_f(x['loss_L3'])} |")
    x = res["all"]["losers"]
    L += ["", f"合计：亏损 {x['n']} 笔 = L1 {x['L1_pct']}% + L2 {x['L2_pct']}% + L3 {x['L3_pct']}%；费用吃掉 {x['fee_eaten_pct']}%。", "",
          "离场原因（笔）：" + "；".join(f"{e} 赢 " + "、".join(f"{k} {v}" for k, v in sorted(E[e]['exit_reasons']['winners'].items(), key=lambda kv: -kv[1]))
                                   + " / 亏 " + "、".join(f"{k} {v}" for k, v in sorted(E[e]['exit_reasons']['losers'].items(), key=lambda kv: -kv[1])) for e in ERAS),
          "赢家持有中位 / 赢家持有期间最大不利中位：" + "；".join(f"{e} {E[e]['winner_hold_median']} 个交易日 / {_f(E[e]['winner_mae_median'])}" for e in ERAS),
          "卖法参数：" + "、".join(f"{k} = {v}" for k, v in res["exit_params"].items()), "",
          "## 三 大盘与核心（持有期间，收盘对收盘）", "",
          "| 年代 | 日経涨时：笔数 / 胜率 / 每笔 | 日経跌时：笔数 / 胜率 / 每笔 | 亏损单里日経也跌的比例 | 跑赢核心（1545）的比例 | 每笔 − 核心同期 | 赚了但跑不赢核心 |",
          "|---|---|---|---|---|---|---|"]
    for e in ERAS:
        m, c = E[e]["market"], E[e]["core"]
        L.append(f"| {lab[e]} | {m['up'].get('n', 0)} 笔 / {m['up'].get('win', '—')}% / {_f(m['up'].get('mean'))} | "
                 f"{m['down'].get('n', 0)} 笔 / {m['down'].get('win', '—')}% / {_f(m['down'].get('mean'))} | {m['losers_market_down_pct']}% | "
                 f"{c['beat_pct']}% | {_f(c['mean_minus_core'], unit=' pp')} | {c['winners_but_lag_core_pct']}%（占赚的笔数） |")
    L += ["", "## 四 进场时的状态（信号日）", ""]
    for e in ERAS:
        L.append(f"- {lab[e]}：" + "；".join(f"{k} {v['n']} 笔 {v['win']}% / {_f(v['mean'])}" for k, v in E[e]["cells"].items())
                 + "｜" + "；".join(f"{k} {v['n']} 笔 {v['win']}% / {_f(v['mean'])}" for k, v in E[e]["us"].items()))
    L += ["", "## 五 信号池 vs 实际成交（假想单笔 = 每个信号单独买、X6 离场、扣费用）", "",
          "| 年代 | 全部 W2 信号 | C 保留 | C 挡掉 | B3 实际成交 |", "|---|---|---|---|---|"]
    for e in ERAS:
        P = E[e]["pool"]
        g = lambda q: f"{q.get('n', 0)} 笔 {q.get('win', '—')}% / {_f(q.get('mean'))}（盈亏比 {q.get('ratio', '—')}）"   # noqa: E731
        L.append(f"| {lab[e]} | {g(P['all_w2'])} | {g(P['c_keep'])} | {g(P['c_skip'])} | {g(P['executed'])} |")
    L += ["", f"## 六 赢家与输家的个股特征（C 保留的假想单笔；三个年代都同号且 |ρ| ≥ {RHO_MIN}）", ""]
    if res["features"]:
        L += ["| 特征 | 说明 | ρ Z | ρ E | ρ J |", "|---|---|---|---|---|"]
        L += [f"| {r['feature']} | {r['zh']} | {r['rho']['Z']:+.3f} | {r['rho']['E']:+.3f} | {r['rho']['J']:+.3f} |" for r in res["features"]]
    else:
        L.append("没有一个特征三个年代都同号且 |ρ| ≥ 0.03。")
    L += ["", "## 七 每个日历年（个股笔数 / 胜率 / 每笔）", "",
          "、".join(f"{y} {v['n']} 笔 {v['win']}% {_f(v['mean'])}" for y, v in res["years"].items()), "",
          f"## 八 本金 ¥{CAP2:,} 多出来的交易（按 票 + 买入日 与 ¥100 万比）", "",
          "| 年代 | ¥200 万 个股 | 多出来的 | ¥100 万有、¥200 万没有的 | 一手金额中位（多出来的 / ¥100 万全部） | 账户 Calmar（¥100 万 → ¥200 万） |",
          "|---|---|---|---|---|---|"]
    for e in ERAS:
        c2 = E[e]["cap2"]
        nw, gn = c2["new"], c2["gone"]
        L.append(f"| {lab[e]} | {c2['n']} 笔 {c2['payoff'].get('win', '—')}% / {_f(c2['payoff'].get('mean'))} | "
                 f"{nw.get('n', 0)} 笔 {nw.get('win', '—')}% / {_f(nw.get('mean'))} | {gn.get('n', 0)} 笔 {gn.get('win', '—')}% / {_f(gn.get('mean'))} | "
                 f"¥{nw.get('lot_median') or 0:,} / ¥{c2['common_lot_median'] or 0:,} | "
                 f"{E[e]['account']['calmar']:.3f} → {c2['account']['calmar']:.3f} |")
    L += ["", f"用时 {res['_seconds']} s。只描述、事后；回测不是预测。非投资建议。"]
    text = "\n".join(L) + "\n"
    OUT.with_suffix(".md").write_text(text, encoding="utf-8")
    OUT.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return text


if __name__ == "__main__":
    print(write(compute()))
