"""exec_timing_study.py — 当天什么时候买 / 卖：结合分钟线（小时线）、日线、周线、月线（事先写定，先提交后运行，结果出来不改规则）。

用户问：当天买卖时结合分钟线、日线、周线、月线判断入手的最佳时间段。
能用的数据（2026-09-25 实测）：yfinance 1 分钟线约 9 个交易日、5 分钟线约 3 个月、60 分钟线约 3 年；日线 20 年以上；
周线 / 月线由日线合成。J-Quants 分钟线要 Light 以上 + 附加套餐（¥5,500/月，过去 2 年），现在是 Free → 不用。
所以：决定用的检验放在 20 年日线（开盘 / 收盘 / 全天均价三个时点都有）；小时线（3 年）描述日内规律，并检验「收盘前估算信号」可不可行。

第一部分 买入时点（日本个股信号，2006-10～；美股信号另报，不参与决定）
  E0 现行：信号次日 9:00 寄付（开盘 > 信号日收盘 ×(1+跳空上限) 放弃；开盘即涨停张贴放弃）
  E1 信号当日 15:25～15:30 收盘竞价（引成；信号在 15:00 前后用盘中价估算）；信号日收盘涨停（≥ 制限值幅 8 成）放弃
  E2 信号次日收盘竞价（看一天再买）；次日收盘 > 信号日收盘 ×(1+跳空上限) 放弃（不追高）；收盘涨停放弃
  E3 信号次日全天分批（成交价 ≈ (开+高+低+收)/4，TWAP 近似）；跳空 / 涨停规则同 E0
  主检验（配对）：同一信号、同一出场价（信号后第 20 个交易日收盘），比较两种买法的收益差（两者都能成交的信号）
  辅助：各自的简化交易（按收盘判断：止损 7% / 止盈 25% / 死叉，次日开盘出场；最长 60 日）的每笔期望
第二部分 卖出时点：上述简化交易（E0 买入）里「按收盘判断的离场」，X0 次日 9:00 寄付（现行） vs X1 当日收盘竞价；
  配对优势 = 当日收盘 / 次日开盘 − 1
第三部分 周线 / 月线过滤（只做与大周期同向的日线信号）：
  F1 周线收盘 > 30 周均线（Weinstein 第二阶段）  F2 月线收盘 > 10 个月均线（Faber 2007）
  F3 周线 MACD(12,26,9) 柱 > 0（Elder 三重滤网的第一层）  F4 = F1 且 F2
  当周 / 当月未完结时，用信号日收盘当作本周 / 本月收盘（只用到信号日为止的数据）
  检验：E0 交易（20 日持有）里「保留」组与「被过滤」组的收益差
第四部分（只描述，不参与决定）：60 分钟线 —— 日本个股全部交易日、信号次日、1655.T：当天最高 / 最低价落在哪个时段、
  开盘后各时段收盘相对开盘的平均涨跌；1655.T 日线 2017～：开盘 vs 全天均价 vs 收盘的平均差。
第五部分（只在 E1 / X1 通过第一 / 二部分时运行）：用 60 分钟线在 15:00 估算信号（价格 = 14 时段收盘，高低 = 9～14 时段，
  成交量 = 9～14 时段合计 ÷ 全样本中位占比），与收盘后的最终信号比较精确率 / 召回率。

采用规则（全部满足才改）：
  买入 / 卖出时点：配对收益差均值 ≥ +0.20%/笔 且 按月聚类 t ≥ 2.0，前半（2006-10～2016-06）与后半同号；
    买入另需：该方案自己的简化交易每笔期望 ≥ E0；
    E1 / X1 另需：第五部分的精确率、召回率都 ≥ 80%；
    最后：统一引擎 S0C2 组合 20 年年化 ≥ 现行 − 0.3pp、最大回撤不比现行深 1pp 以上。多个满足取配对收益差最大者。
  周 / 月线过滤：保留组 − 被过滤组 ≥ +1.0pp 且 t ≥ 2.0、两半同号；组合 S0C2 20 年 Calmar ≥ 现行 + 0.03、年化 ≥ 现行 − 0.5pp。
    多个满足取组合 Calmar 最高者。
  组合层只对通过前面各项的方案运行（规则是「且」，不影响结论）；需要的引擎执行方式在登记之后实现。
输出 var/out/exec_timing_study.md / .json。
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                   # noqa: E402
from qbreak.config import DataConfig, ExecConfig, universe                 # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.strategy import IndicatorCache, compute_indicators             # noqa: E402
from qbreak.tick import limit_lock, price_limit_jp                         # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402

START, MID = pd.Timestamp("2006-10-01"), pd.Timestamp("2016-07-01")
H = 20
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def clustered(df: pd.DataFrame, col: str) -> dict:
    """按信号月份聚类：均值、t 值、样本数；前后两半的均值。"""
    d = df.dropna(subset=[col])
    if d.empty:
        return {"n": 0}
    mm = d.groupby(d["date"].dt.to_period("M"))[col].mean()
    se = mm.std(ddof=1) / math.sqrt(len(mm)) if len(mm) > 1 else float("nan")
    h1, h2 = d[d["date"] < MID][col], d[d["date"] >= MID][col]
    return {"n": int(len(d)), "mean": float(d[col].mean() * 100), "t": float(mm.mean() / se) if se and se > 0 else None,
            "h1": float(h1.mean() * 100) if len(h1) else None, "h2": float(h2.mean() * 100) if len(h2) else None}


def at_limit_up(prev: float, px: float, market: str) -> bool:
    return market == "JP" and prev > 0 and px >= prev + 0.8 * price_limit_jp(prev)


def simple_trade(C, O, dead, i_sig, entry, first, stop, tp, use_dead, last):
    """按收盘判断：止损 / 止盈 / 死叉 → 次日开盘出场（同时记下当日收盘，供卖出时点比较）；到期按收盘。"""
    for k in range(first, last + 1):
        why = None
        if C[k] <= entry * (1 - stop):
            why = "stop"
        elif tp and C[k] >= entry * (1 + tp):
            why = "tp"
        elif use_dead and dead[k] and k > i_sig + 1:
            why = "dead"
        if why and k + 1 < len(O):
            return O[k + 1] / entry - 1, why, C[k], O[k + 1]
    return C[last] / entry - 1, "time", None, None


def signal_level(ind: dict, market: str, p, gap_pct: float) -> pd.DataFrame:
    rows = []
    stop, tp = p.stop_loss_pct / 100, p.take_profit_pct / 100
    for t, df in ind.items():
        O, Hh, L, C = (df[c].to_numpy(float) for c in ("Open", "High", "Low", "Close"))
        dead = df["dead_cross"].to_numpy(bool)
        idx = df.index
        for i in np.where(df["entry"].to_numpy(bool))[0]:
            if idx[i] < START or i < 1 or i + max(H, 60) >= len(df):
                continue
            gap_ok = O[i + 1] <= C[i] * (1 + gap_pct / 100)
            lock = limit_lock(C[i], Hh[i + 1], L[i + 1], C[i + 1], market) == "up"
            e = {"E0": O[i + 1] if gap_ok and not lock else np.nan,
                 "E1": C[i] if not at_limit_up(C[i - 1], C[i], market) else np.nan,
                 "E2": C[i + 1] if C[i + 1] <= C[i] * (1 + gap_pct / 100) and not at_limit_up(C[i], C[i + 1], market)
                 else np.nan,
                 "E3": (O[i + 1] + Hh[i + 1] + L[i + 1] + C[i + 1]) / 4 if gap_ok and not lock else np.nan}
            first = {"E0": i + 1, "E1": i + 1, "E2": i + 2, "E3": i + 1}
            row = {"ticker": t, "date": idx[i], "exit20": C[i + H]}
            for k, px in e.items():
                row[k] = px
                row[f"{k}_r20"] = C[i + H] / px - 1 if px == px else np.nan
                if px == px:
                    r, why, c_k, o_k1 = simple_trade(C, O, dead, i, px, first[k], stop, tp, p.exit_on_macd_dead_cross,
                                                     i + 60)
                    row[f"{k}_trade"] = r
                    if k == "E0":
                        row["exit_why"] = why
                        row["x1_adv"] = (c_k / o_k1 - 1) if c_k is not None and o_k1 else np.nan
                else:
                    row[f"{k}_trade"] = np.nan
            c_hist = pd.Series(C[: i + 1], index=idx[: i + 1])
            row.update(mtf_flags(c_hist))
            rows.append(row)
    return pd.DataFrame(rows)


def mtf_flags(c: pd.Series) -> dict:
    """信号日为止的周线 / 月线（本周 / 本月用信号日收盘）。"""
    wk = c.resample("W-FRI").last().dropna()
    mo = c.resample("ME").last().dropna()
    last = float(c.iloc[-1])
    f1 = len(wk) >= 30 and last > wk.tail(30).mean()
    f2 = len(mo) >= 10 and last > mo.tail(10).mean()
    macd = wk.ewm(span=12, adjust=False).mean() - wk.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    f3 = len(wk) >= 35 and float(hist.iloc[-1]) > 0
    return {"F1": bool(f1), "F2": bool(f2), "F3": bool(f3), "F4": bool(f1 and f2)}


def filter_test(df: pd.DataFrame, f: str) -> dict:
    d = df.dropna(subset=["E0_r20"]).copy()
    keep, drop = d[d[f]], d[~d[f]]
    k, r = clustered(keep, "E0_r20"), clustered(drop, "E0_r20")
    mk = keep.groupby(keep["date"].dt.to_period("M"))["E0_r20"].mean()
    md = drop.groupby(drop["date"].dt.to_period("M"))["E0_r20"].mean()
    se = math.sqrt((mk.var(ddof=1) / len(mk) if len(mk) > 1 else 0) + (md.var(ddof=1) / len(md) if len(md) > 1 else 0))
    diff = (k.get("mean", 0) - r.get("mean", 0))
    return {"keep": k, "drop": r, "diff": diff, "t": diff / 100 / se if se > 0 else None,
            "h1": (k.get("h1") or 0) - (r.get("h1") or 0), "h2": (k.get("h2") or 0) - (r.get("h2") or 0),
            "share_kept": round(len(keep) / max(1, len(d)) * 100, 1)}


def hourly(tickers: list[str]) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    out = {}
    for k in range(0, len(tickers), 40):
        batch = tickers[k:k + 40]
        raw = yf.download(batch, period="730d", interval="60m", auto_adjust=False, progress=False,
                          group_by="ticker", threads=False)
        for t in batch:
            try:
                h = raw[t].dropna(how="all") if len(batch) > 1 else raw.dropna(how="all")
            except KeyError:
                continue
            if h.empty:
                continue
            h = h.copy()
            h.index = h.index.tz_convert("Asia/Tokyo") if h.index.tz is not None else h.index
            out[t] = h[["Open", "High", "Low", "Close", "Volume"]]
    return out


def intraday_profile(hb: dict[str, pd.DataFrame], days: dict[str, set] | None = None) -> dict:
    """当天最高 / 最低出现在哪个时段（按时段开始的钟点），各时段收盘相对当日开盘的平均涨跌。"""
    hi_cnt, lo_cnt, path = {}, {}, {}
    n = 0
    for t, h in hb.items():
        g = h.groupby(h.index.date)
        for d, x in g:
            if days is not None and pd.Timestamp(d) not in days.get(t, set()):
                continue
            if len(x) < 5 or not (x["Open"].iloc[0] > 0):
                continue
            n += 1
            hrs = x.index.hour
            hi_cnt[hrs[int(np.argmax(x["High"].to_numpy()))]] = hi_cnt.get(hrs[int(np.argmax(x["High"].to_numpy()))], 0) + 1
            lo_cnt[hrs[int(np.argmin(x["Low"].to_numpy()))]] = lo_cnt.get(hrs[int(np.argmin(x["Low"].to_numpy()))], 0) + 1
            o = float(x["Open"].iloc[0])
            for hh, c in zip(hrs, x["Close"].to_numpy(float)):
                path.setdefault(int(hh), []).append(c / o - 1)
    if not n:
        return {"n": 0}
    return {"n": n, "high_at": {int(k): round(v / n * 100, 1) for k, v in sorted(hi_cnt.items())},
            "low_at": {int(k): round(v / n * 100, 1) for k, v in sorted(lo_cnt.items())},
            "path_mean_pct": {k: round(float(np.mean(v)) * 100, 3) for k, v in sorted(path.items())},
            "path_median_pct": {k: round(float(np.median(v)) * 100, 3) for k, v in sorted(path.items())}}


def realism(raw: dict[str, pd.DataFrame], hb: dict[str, pd.DataFrame], p) -> dict:
    """第五部分：15:00 用盘中数据估算的信号 vs 收盘后的最终信号（60 分钟线覆盖的日子）。"""
    frac = []
    for h in hb.values():
        for _, x in h.groupby(h.index.date):
            tot = x["Volume"].sum()
            if tot > 0 and len(x) >= 6:
                frac.append(x.loc[x.index.hour < 15, "Volume"].sum() / tot)
    fr = float(np.median(frac)) if frac else 0.85
    tp = fp = fn = checked = 0
    for t, h in hb.items():
        df = raw.get(t)
        if df is None or len(df) < 400:
            continue
        full = compute_indicators(df, p)
        m, s = full["macd"].to_numpy(float), full["macd_sig"].to_numpy(float)
        isr = full["is_range"].to_numpy(bool)
        pos = {d: k for k, d in enumerate(df.index)}
        for d, x in h.groupby(h.index.date):
            k = pos.get(pd.Timestamp(d))
            if k is None or k < 300 or len(x) < 6:
                continue
            final = bool(full["entry"].iloc[k])
            if not (isr[k] and m[k - 1] <= s[k - 1]) and not final:
                continue                                        # 金叉 / 横盘的必要条件（只看历史）都不满足：估算也不可能成立
            pre = x[x.index.hour < 15]
            if pre.empty:
                continue
            tail = df.iloc[k - 300:k + 1].copy()
            tail.iloc[-1, tail.columns.get_loc("High")] = float(pre["High"].max())
            tail.iloc[-1, tail.columns.get_loc("Low")] = float(pre["Low"].min())
            tail.iloc[-1, tail.columns.get_loc("Close")] = float(pre["Close"].iloc[-1])
            tail.iloc[-1, tail.columns.get_loc("Volume")] = float(pre["Volume"].sum()) / fr
            est = bool(compute_indicators(tail, p)["entry"].iloc[-1])
            checked += 1
            tp += est and final
            fp += est and not final
            fn += final and not est
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"vol_frac_before_15": round(fr, 3), "checked": checked, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 3) if prec is not None else None, "recall": round(rec, 3) if rec is not None else None}


def fmt(x, d=2, pct=True):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:+.{d}f}{'%' if pct else ''}"


def main() -> int:
    t0 = time.time()
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    out = {}
    say(f"# 当天什么时候买 / 卖：分钟线（小时线）· 日线 · 周线 · 月线（{pd.Timestamp.today().date()}）")
    res = {}
    for m in ("JP", "US"):
        p = load_params(market=m)
        data = load_universe(universe(m, "broad"), d21)
        ind = dict(IndicatorCache(data).all(p))
        gap = ExecConfig.for_market(m, "rakuten").max_entry_gap_pct
        df = signal_level(ind, m, p, gap)
        res[m] = (df, data, p)
        say(f"\n## {m}：{len(df)} 个信号（{df['date'].min().date()}～{df['date'].max().date()}），跳空上限 {gap}%（{time.time() - t0:.0f}s）")
        say("### 第一部分 买入时点（配对：同一信号、同一出场价 = 信号后第 20 日收盘）")
        say("| 买法 | 可成交信号 | 与 E0 都成交 | 收益差均值（vs E0） | t | 前半 / 后半 | 简化交易每笔期望 |")
        say("|---|---|---|---|---|---|---|")
        base = clustered(df, "E0_trade")
        say(f"| E0 次日 9:00 寄付（现行） | {int(df['E0'].notna().sum())} | — | — | — | — | {fmt(base.get('mean'))} |")
        out[m] = {"n": len(df), "E0_trade": base}
        for k, lab in (("E1", "信号当日收盘竞价"), ("E2", "次日收盘竞价"), ("E3", "次日全天分批（≈均价）")):
            both = df.dropna(subset=["E0_r20", f"{k}_r20"]).copy()
            both["d"] = both[f"{k}_r20"] - both["E0_r20"]
            c = clustered(both, "d")
            tr = clustered(df, f"{k}_trade")
            out[m][k] = {"paired": c, "trade": tr, "fillable": int(df[k].notna().sum())}
            say(f"| {k} {lab} | {int(df[k].notna().sum())} | {c['n']} | {fmt(c.get('mean'), 3)} | "
                f"{fmt(c.get('t'), 2, False)} | {fmt(c.get('h1'), 3)} / {fmt(c.get('h2'), 3)} | {fmt(tr.get('mean'))} |")
        ex = df[df["exit_why"].isin(["stop", "tp", "dead"])].copy()
        cx = clustered(ex, "x1_adv")
        out[m]["X1"] = cx
        say("### 第二部分 卖出时点（按收盘判断的离场：止损 / 止盈 / 死叉）")
        say(f"X1 当日收盘竞价 vs X0 次日 9:00 寄付：{cx['n']} 次离场，收益差均值 {fmt(cx.get('mean'), 3)}（t {fmt(cx.get('t'), 2, False)}；"
            f"前半 {fmt(cx.get('h1'), 3)} / 后半 {fmt(cx.get('h2'), 3)}）")
        say("### 第三部分 周线 / 月线过滤（E0 交易，20 日持有）")
        say("| 过滤 | 保留比例 | 保留组 | 被过滤组 | 差 | t | 前半 / 后半差 |")
        say("|---|---|---|---|---|---|---|")
        out[m]["filters"] = {}
        for f, lab in (("F1", "周线 > 30 周均线"), ("F2", "月线 > 10 个月均线"), ("F3", "周线 MACD 柱 > 0"), ("F4", "F1 且 F2")):
            ft = filter_test(df, f)
            out[m]["filters"][f] = ft
            say(f"| {f} {lab} | {ft['share_kept']}% | {fmt(ft['keep'].get('mean'))} | {fmt(ft['drop'].get('mean'))} | "
                f"{fmt(ft['diff'])} | {fmt(ft['t'], 2, False)} | {fmt(ft['h1'])} / {fmt(ft['h2'])} |")

    # ── 判定（日本；组合层与第五部分只对通过的方案运行）──
    jp = out["JP"]
    passing_exec = []
    for k in ("E1", "E2", "E3"):
        c, tr = jp[k]["paired"], jp[k]["trade"]
        ok = (c.get("mean", -9) >= 0.20 and (c.get("t") or 0) >= 2.0 and (c.get("h1") or 0) > 0 and (c.get("h2") or 0) > 0
              and (tr.get("mean") or -9) >= (jp["E0_trade"].get("mean") or 9))
        jp[k]["pass_signal_level"] = bool(ok)
        if ok:
            passing_exec.append(k)
    cx = jp["X1"]
    x1_ok = cx.get("mean", -9) >= 0.20 and (cx.get("t") or 0) >= 2.0 and (cx.get("h1") or 0) > 0 and (cx.get("h2") or 0) > 0
    jp["X1"]["pass_signal_level"] = bool(x1_ok)
    passing_f = [f for f, ft in jp["filters"].items()
                 if ft["diff"] >= 1.0 and (ft["t"] or 0) >= 2.0 and ft["h1"] > 0 and ft["h2"] > 0]
    say("\n## 判定（日本个股，事先规则）")
    say(f"买入时点通过逐笔检验：{passing_exec or '无'}；卖出时点 X1：{'通过' if x1_ok else '未通过'}；周 / 月线过滤：{passing_f or '无'}")
    out["passing"] = {"exec": passing_exec, "x1": bool(x1_ok), "filters": passing_f}

    # ── 第四部分：日内规律（60 分钟线）──
    df_jp, data_jp, p_jp = res["JP"]
    tick_jp = list(data_jp)
    hb = hourly(tick_jp + ["1655.T"])
    sig_days: dict[str, set] = {}
    for _, r in df_jp[df_jp["E0"].notna()].iterrows():
        nxt = data_jp[r["ticker"]].index
        k = nxt.searchsorted(r["date"]) + 1
        if k < len(nxt):
            sig_days.setdefault(r["ticker"], set()).add(nxt[k])
    prof_all = intraday_profile({t: h for t, h in hb.items() if t != "1655.T"})
    prof_sig = intraday_profile({t: h for t, h in hb.items() if t != "1655.T"}, sig_days)
    prof_etf = intraday_profile({"1655.T": hb["1655.T"]} if "1655.T" in hb else {})
    out["intraday"] = {"all": prof_all, "signal_next_day": prof_sig, "1655": prof_etf}
    span = [min(h.index.min() for h in hb.values()).date(), max(h.index.max() for h in hb.values()).date()] if hb else []
    say(f"\n## 第四部分 日内规律（60 分钟线 {span[0] if span else '—'}～{span[1] if span else '—'}，只描述）")
    say("时段按开始钟点：9 = 9:00–10:00，10 = 10:00–11:00，11 = 11:00–11:30，12 = 12:30–13:00，13、14 = 各一小时，15 = 15:00–15:30（含收盘竞价）")
    for lab, pr in (("日本个股全部交易日", prof_all), ("信号次日（E0 买入日）", prof_sig), ("1655.T", prof_etf)):
        if not pr.get("n"):
            say(f"- {lab}：无数据")
            continue
        say(f"- {lab}（{pr['n']} 个交易日）：最低价出现在 {pr['low_at']}（%）；最高价出现在 {pr['high_at']}（%）；"
            f"各时段收盘相对开盘 均值 {pr['path_mean_pct']} / 中位 {pr['path_median_pct']}（%）")
    etf = load_universe(["1655.T"], d21).get("1655.T")
    if etf is not None:
        e = etf[etf.index >= "2017-11-01"]
        typ = (e["Open"] + e["High"] + e["Low"] + e["Close"]) / 4
        o2c, o2t = float((e["Close"] / e["Open"] - 1).mean() * 100), float((typ / e["Open"] - 1).mean() * 100)
        out["1655_daily"] = {"days": len(e), "open_to_close_pct": o2c, "open_to_typical_pct": o2t}
        say(f"- 1655.T 日线（{len(e)} 天，2017-11～）：收盘相对开盘平均 {o2c:+.3f}%，全天均价相对开盘平均 {o2t:+.3f}%")

    # ── 第五部分：只在 E1 / X1 通过时运行 ──
    if "E1" in passing_exec or x1_ok:
        rl = realism(data_jp, {t: h for t, h in hb.items() if t != "1655.T"}, p_jp)
        out["realism"] = rl
        say(f"\n## 第五部分 15:00 估算信号 vs 最终信号：{rl}")
        ok_r = (rl.get("precision") or 0) >= 0.8 and (rl.get("recall") or 0) >= 0.8
        say(f"估算可行（精确率、召回率都 ≥ 80%）：{'是' if ok_r else '否'}")
        out["realism_ok"] = bool(ok_r)
    else:
        say("\n第五部分：E1 / X1 未通过逐笔检验，不运行。")
    say(f"\n（组合层 S0C2 检验只对仍然通过的方案运行；耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "exec_timing_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
