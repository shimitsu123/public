"""exit_forward.py — 卖法 X6「吊灯止损」的前向记录：逐信号配对模拟与统计（2026-09-28 登记；用户「㉛ 选 ① 走前向记录」）。

登记内容与判定规则：scripts/score_forward.py 第十节（每日记录：日経225 + 扩大池）、scripts/w2_forward_all.py 第八节（全市场）。
来由：scripts/bsh_explore.py（da9c1dc）里 X6「持有以来最高价 − 3 × ATR14，收盘跌破就卖（代替 MACD 死叉）」每笔明显变好
（组合里 E +0.60 → +2.10%、J +0.61 → +1.35%），但账户 Calmar 只 +0.02、没过入选规则；它是看过 E / J 之后挑出来的
→ 只能靠登记之后才发生的信号检验。

做法（每个信号一对，只有卖法不同）：
  只留这一个买入信号，用回测引擎 qbreak/engine.run_backtest（一只票；现行成交假设：信号日收盘定、次日开盘 ×(1 + 滑点) 买，
  跳空超过上限 / 涨停张贴不买；止损 / 跟踪 / 止盈按收盘判定、次日开盘卖）跑两次：
    现行：原样（MACD 死叉、止损 −7%、跟踪 12%、止盈 +25%、放量阴线、最长 60 天）；
    X6：只把「死叉」那一条换成「收盘 < 持有以来最高价（买入价与买入日起每天最高价里最大的）− 3 × ATR14」，其余不变
        （与 scripts/bsh_common.py 的 X6 同一定义：最高价从买入价起算、ATR 用当天的 Wilder ATR14）。
  两边买入完全相同（同一天、同一价格）→ 配对差 = X6 − 现行 的净收益（pp；来回手续费两边相同）。
  成熟：信号日之后至少有 MATURE_BARS 根 K 线（最长持有 60 天 + 次日开盘 + 余量）→ 两边都应已平仓。只用成熟的配对：
  否则「X6 拿得久、还没卖的多半是赚的」会让早期结果偏向现行。
只作记录，不影响交易。

R4「抛物线 SAR 翻转代替死叉」（2026-09-28 追加登记；scripts/score_forward.py 第十一节、scripts/w2_forward_all.py 第九节）：
  同一个配对再多跑一边：只把「死叉」那一条换成「抛物线 SAR（0.02 / 0.02 / 0.2，Wilder）从价格下方翻到上方的那天收盘」（其余卖法不变；
  与 scripts/sell_common.py 的 sar_flip 同一定义，psar 只在这里写一份）。来由：卖出判定的确认（scripts/sell_confirm.py，c9149d1）里
  事后看到它胜率 +4.2 pp、每笔 −0.03 pp（没看过的数据），但探索用的 2006〜2016 日経225 不一致 → 只能用登记之后的数据检验。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import w2_forward as W2F

CHANDELIER_K = 3.0                     # 与 scripts/bsh_common.CHANDELIER_K 相同（登记时写定）
MATURE_BARS = 65                       # 信号日之后至少这么多根 K 线才算成熟
BOOT_N, SEED = 2000, 20260928
CHECKPOINTS = (100, 200, 400)          # 每日记录：合并样本、W2 保留、成熟配对第一次达到 → 判定
JUDGE_DATES = W2F.JUDGE_DATES          # 全市场：每年一次（与 W2 / K2 / USW 同一组日期）
MIN_CI = 10                            # 配对少于这个数不算区间
R4_MARGIN = 0.30                       # R4：每笔不能差过 0.30 pp（非劣效的界限，登记时写定）
SAR_STEP, SAR_MAX = 0.02, 0.2


def chandelier_flags(df: pd.DataFrame, k_fill: int, px: float, k: float = CHANDELIER_K) -> np.ndarray:
    """买入日（位置 k_fill、成交价 px）起每天收盘：收盘 < max(px, 买入日起的最高价) − k × ATR → True；买入日之前全是 False。
    与引擎的峰值同一个算法（qbreak/engine.py：峰值从买入价起、每个持有日取 max(峰值, 当天最高价)）。"""
    n = len(df)
    out = np.zeros(n, bool)
    if not 0 <= k_fill < n:
        return out
    h = df["High"].to_numpy(float)[k_fill:]
    c = df["Close"].to_numpy(float)[k_fill:]
    a = df["atr"].to_numpy(float)[k_fill:]
    peak = np.maximum(np.maximum.accumulate(np.where(np.isfinite(h), h, -np.inf)), px)
    lvl = peak - k * a
    out[k_fill:] = np.isfinite(lvl) & (c < lvl)
    return out


def psar(h, lo, step: float = SAR_STEP, mx: float = SAR_MAX) -> tuple[np.ndarray, np.ndarray]:
    """抛物线 SAR（Wilder）。返回 (SAR, up)：up = True 表示上升趋势（SAR 在价格下方）。第一天按「第二天高点 ≥ 第一天 → 上升」起算。"""
    h, lo = np.asarray(h, float), np.asarray(lo, float)
    n = len(h)
    sar, up = np.full(n, np.nan), np.zeros(n, bool)
    if n < 2:
        return sar, up
    trend = h[1] >= h[0]
    ep = h[0] if trend else lo[0]
    s = lo[0] if trend else h[0]
    af = step
    for i in range(1, n):
        s = s + af * (ep - s)
        if trend:
            s = min(s, lo[i - 1], lo[i - 2] if i >= 2 else lo[i - 1])
            if lo[i] < s:                                                    # 跌破 → 翻成下降
                trend, s, ep, af = False, ep, lo[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, mx)
        else:
            s = max(s, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > s:                                                     # 突破 → 翻成上升
                trend, s, ep, af = True, ep, h[i], step
            elif lo[i] < ep:
                ep, af = lo[i], min(af + step, mx)
        sar[i], up[i] = s, trend
    return sar, up


def sar_flip(df: pd.DataFrame) -> np.ndarray:
    """SAR 从价格下方翻到上方的那天（收盘时成立 → 次日开盘卖）。"""
    if not len(df):
        return np.zeros(0, bool)
    _, up = psar(df["High"].to_numpy(float), df["Low"].to_numpy(float))
    return np.r_[False, up[:-1] & ~up[1:]]


def _one(t: str, f: pd.DataFrame, p, bt, start, end) -> dict | None:
    from .engine import run_backtest
    r = run_backtest({t: f}, p, bt, start=start, end=end)
    return r.trades.iloc[0].to_dict() if len(r.trades) else None


def pair(t: str, df: pd.DataFrame, sig_date, p, bt, end=None) -> dict | None:
    """一个信号 → {"cur": 现行的那笔, "x6": X6 的那笔}（run_backtest 的交易行）。df = compute_indicators 的结果
    （entry 列会被换成只有这一天）。信号日不在行情里 / 是最后一根 K 线 / 没买到（跳空、涨停）→ None。"""
    if not p.exit_on_macd_dead_cross:
        raise ValueError("参数里没有死叉离场 → 「只把死叉换成吊灯止损」无从谈起")
    d = pd.Timestamp(sig_date)
    if d not in df.index:
        return None
    f = df.copy()
    f["entry"] = np.asarray(df.index == d)
    try:
        a = _one(t, f, p, bt, d, end)
    except ValueError:                                  # 交易窗口太短（信号日是最后一根 K 线）
        return None
    if a is None:
        return None
    k = int(f.index.get_loc(pd.Timestamp(a["entry_date"])))
    px = float(f["Open"].to_numpy(float)[k]) * (1 + bt.exec_cfg.slippage_pct / 100)       # 与引擎的买入价同一个算式
    b = _one(t, f.assign(dead_cross=chandelier_flags(f, k, px)), p, bt, d, end)
    if b is None or b["entry_date"] != a["entry_date"] or b["entry_px"] != a["entry_px"]:
        raise AssertionError(f"{t} {d.date()}：两边的买入应完全相同")
    if b["reason"] == "dead_cross":
        b["reason"] = "chandelier"
    c = _one(t, f.assign(dead_cross=sar_flip(f)), p, bt, d, end)                    # R4（第十一节）
    if c is None or c["entry_date"] != a["entry_date"] or c["entry_px"] != a["entry_px"]:
        raise AssertionError(f"{t} {d.date()}：R4 的买入应与现行完全相同")
    if c["reason"] == "dead_cross":
        c["reason"] = "sar_flip"
    return {"cur": a, "x6": b, "r4": c}


def pairs_frame(ind: dict[str, pd.DataFrame], sigs: pd.DataFrame, p, bt, rt: float, date_col: str = "date",
                end_bars: int | None = None) -> pd.DataFrame:
    """sigs（ticker、date_col = 信号日，其余列原样带上）→ 每个信号一行：status（ok 两边已平仓 / open 还有一边持有中 /
    no_fill 没买到 / no_data 行情里没有）、mature、两边的卖出日 / 原因 / 持有天数 / 净收益（ret − rt）与配对差 d = X6 − 现行。
    end_bars：只算到信号日之后这么多根 K 线（历史校准用来省时间；None = 到行情最后一天）。"""
    rows = []
    for r in sigs.to_dict("records"):
        t, d = r["ticker"], pd.Timestamp(r[date_col])
        df = ind.get(t)
        if df is None or d not in df.index:
            rows.append({**r, "status": "no_data", "mature": False})
            continue
        pos = int(df.index.get_loc(d))
        mature = len(df) - 1 - pos >= MATURE_BARS
        end = df.index[min(len(df) - 1, pos + end_bars)] if end_bars else None
        pr = pair(t, df, d, p, bt, end=end)
        if pr is None:
            rows.append({**r, "status": "no_fill", "mature": mature})
            continue
        a, b, c = pr["cur"], pr["x6"], pr["r4"]
        rows.append({**r, "status": "ok" if a["reason"] != "end" and b["reason"] != "end" else "open", "mature": mature,
                     "entry_date": a["entry_date"], "exit_cur": a["exit_date"], "exit_x6": b["exit_date"],
                     "reason_cur": a["reason"], "reason_x6": b["reason"], "hold_cur": int(a["hold_days"]), "hold_x6": int(b["hold_days"]),
                     "net_cur": round(float(a["ret_pct"]) - rt, 4), "net_x6": round(float(b["ret_pct"]) - rt, 4),
                     "status_r4": "ok" if a["reason"] != "end" and c["reason"] != "end" else "open", "exit_r4": c["exit_date"],
                     "reason_r4": c["reason"], "hold_r4": int(c["hold_days"]), "net_r4": round(float(c["ret_pct"]) - rt, 4)})
    P = pd.DataFrame(rows)
    if len(P) and "net_cur" in P.columns:
        P["d"] = (P["net_x6"] - P["net_cur"]).round(4)
        P["d_r4"] = (P["net_r4"] - P["net_cur"]).round(4)
    return P


def usable(P: pd.DataFrame) -> pd.DataFrame:
    """成熟、两边都已平仓的配对（统计只用这些）。"""
    if not len(P) or "status" not in P.columns:
        return pd.DataFrame(columns=list(P.columns) + ["d"])
    return P[(P["status"] == "ok") & P["mature"].astype(bool)].reset_index(drop=True)


def boot_mean(d, dates, n: int = BOOT_N, seed: int = SEED) -> np.ndarray:
    """按信号月聚类的自助法：每次有放回地抽月份 → 配对差的平均。"""
    d = np.asarray(d, float)
    if not len(d):
        return np.full(n, np.nan)
    mon = pd.to_datetime(pd.Series(dates)).dt.to_period("M").to_numpy()
    groups = [np.flatnonzero(mon == m) for m in pd.unique(mon)]
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for b in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        out[b] = d[idx].mean()
    return out


def evaluate(P: pd.DataFrame, date_col: str = "date", n: int = BOOT_N, seed: int = SEED) -> dict:
    """配对表 → 笔数（按 status / 成熟）、两边的胜率 / 每笔 / 持有中位、配对差与区间（95% / 99%）、X6 的出场原因。"""
    st = P["status"].value_counts().to_dict() if len(P) and "status" in P.columns else {}
    imm = int(((P["status"] == "ok") & ~P["mature"].astype(bool)).sum()) if st else 0
    U = usable(P)
    out = {"n": int(len(U)), "counts": {"signals": int(len(P)), "no_data": int(st.get("no_data", 0)), "no_fill": int(st.get("no_fill", 0)),
                                        "open": int(st.get("open", 0)), "immature": imm},
           "cur": W2F.stat(U["net_cur"]) if len(U) else {"n": 0}, "x6": W2F.stat(U["net_x6"]) if len(U) else {"n": 0}}
    if not len(U):
        return out
    d = U["d"].to_numpy(float)
    out.update({"diff": round(float(d.mean()), 3), "sd": round(float(d.std(ddof=1)), 3) if len(d) > 1 else None,
                "dwin": round(out["x6"]["win"] - out["cur"]["win"], 2),
                "hold_cur": float(np.median(U["hold_cur"])), "hold_x6": float(np.median(U["hold_x6"])),
                "x6_better": round(float((d > 0).mean() * 100), 2),
                "reasons_x6": {k: round(v * 100, 1) for k, v in U["reason_x6"].value_counts(normalize=True).items()},
                "months": int(pd.to_datetime(U[date_col]).dt.to_period("M").nunique())})
    if len(U) >= MIN_CI:
        B = boot_mean(d, U[date_col], n, seed)
        q = lambda p_: round(float(np.percentile(B, p_)), 3)                                     # noqa: E731
        out.update({"lo95": q(2.5), "hi95": q(97.5), "lo99": q(0.5), "hi99": q(99.5)})
    return out


def confirmed(ev: dict) -> bool:
    """证实：X6 − 现行 的 99% 区间下限 > 0。"""
    return ev.get("lo99") is not None and ev["lo99"] > 0


def refuted(ev: dict) -> bool:
    """否定：X6 − 现行 的 95% 区间上限 < 0（X6 每笔反而更差）。"""
    return ev.get("hi95") is not None and ev["hi95"] < 0


def verdict_lines(ev: dict, when: str | None) -> list[str]:
    """when = 这次判定的名目（例「成熟配对第一次达到 100 笔」「2027-09-28 这一年」）；None = 这次不判定。"""
    if not when:
        return []
    if "lo95" not in ev:
        return [f"判定（{when}）：成熟配对只有 {ev.get('n', 0)} 笔、算不出区间 → 证实 / 否定都不成立"]
    if confirmed(ev):
        v = "**证实成立 = 新数据证实「同一个信号用 X6 卖，每笔比现行好」**（要改模拟盘还要另写一份登记的组合研究，并经用户确认）"
    elif refuted(ev):
        v = "**否定成立 = 新数据里 X6 每笔反而更差** → 结束跟踪（记录照留）"
    else:
        v = "证实 / 否定都不成立（未定）"
    return [f"判定（{when}）：{v}；X6 − 现行 {ev['diff']:+.2f} pp，95% 区间 {ev['lo95']:+.2f}〜{ev['hi95']:+.2f}，"
            f"99% 区间 {ev['lo99']:+.2f}〜{ev['hi99']:+.2f}（{ev.get('months', 0)} 个月）"]


def summary_line(ev: dict) -> str:
    c = ev.get("counts") or {}
    if not ev.get("n"):
        return (f"还没有成熟的配对（信号 {c.get('signals', 0)} 个：未成熟 {c.get('immature', 0)}、持有中 {c.get('open', 0)}、"
                f"没买到 {c.get('no_fill', 0)}、没行情 {c.get('no_data', 0)}）")
    f = lambda s, h: f"胜率 {s['win']:.1f}% / 每笔 {s['mean']:+.2f}% / 持有中位 {h:g} 天"                    # noqa: E731
    ci = f"（95% 区间 {ev['lo95']:+.2f}〜{ev['hi95']:+.2f}）" if "lo95" in ev else ""
    return (f"成熟配对 {ev['n']} 笔（{ev.get('months', 0)} 个月）：现行 {f(ev['cur'], ev['hold_cur'])}；X6 {f(ev['x6'], ev['hold_x6'])}；"
            f"X6 − 现行 {ev['diff']:+.2f} pp{ci}、X6 更好的占 {ev['x6_better']:.0f}%"
            f"（另有未成熟 {c.get('immature', 0)}、持有中 {c.get('open', 0)}、没买到 {c.get('no_fill', 0)}、没行情 {c.get('no_data', 0)}）")


def history_row(ev: dict, run: str, scope: str, key: str, when, extra: dict | None = None) -> dict:
    """复核历史的一行：key = checkpoint（每日记录）/ x6_year（全市场）；判定过的下次不再判定。"""
    judged = when is not None
    return {"run": run, "scope": scope, "closed": ev.get("n", 0), key: when, "x6_diff": ev.get("diff"), "x6_lo95": ev.get("lo95"),
            "x6_hi95": ev.get("hi95"), "x6_lo99": ev.get("lo99"), "x6_hi99": ev.get("hi99"),
            "x6_confirmed": confirmed(ev) if judged else None, "x6_refuted": refuted(ev) if judged else None, **(extra or {})}


# ───────────────────────── R4：胜率升、每笔不降（第十一节 / 第九节）─────────────────────────
def usable_r4(P: pd.DataFrame) -> pd.DataFrame:
    """成熟、现行与 R4 两边都已平仓的配对。"""
    if not len(P) or "status_r4" not in P.columns:
        return pd.DataFrame(columns=list(P.columns))
    return P[(P["status_r4"] == "ok") & P["mature"].astype(bool)].reset_index(drop=True)


def boot_win_mean(cur, var, dates, n: int = BOOT_N, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    """按信号月聚类的自助法：胜率差（pp）与每笔差（pp）。"""
    cur, var = np.asarray(cur, float), np.asarray(var, float)
    mon = pd.to_datetime(pd.Series(dates)).dt.to_period("M").to_numpy()
    groups = [np.flatnonzero(mon == m) for m in pd.unique(mon)]
    rng = np.random.default_rng(seed)
    dw, dm = np.empty(n), np.empty(n)
    for b in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        dw[b] = ((var[idx] > 0).mean() - (cur[idx] > 0).mean()) * 100
        dm[b] = var[idx].mean() - cur[idx].mean()
    return dw, dm


def evaluate_r4(P: pd.DataFrame, date_col: str = "date", n: int = BOOT_N, seed: int = SEED) -> dict:
    U = usable_r4(P)
    out = {"n": int(len(U)), "cur": W2F.stat(U["net_cur"]) if len(U) else {"n": 0}, "r4": W2F.stat(U["net_r4"]) if len(U) else {"n": 0}}
    if not len(U):
        return out
    c, v = U["net_cur"].to_numpy(float), U["net_r4"].to_numpy(float)
    out.update({"dwin": round(((v > 0).mean() - (c > 0).mean()) * 100, 2), "dmean": round(float(v.mean() - c.mean()), 3),
                "hold_cur": float(np.median(U["hold_cur"])), "hold_r4": float(np.median(U["hold_r4"])),
                "months": int(pd.to_datetime(U[date_col]).dt.to_period("M").nunique())})
    if len(U) >= MIN_CI:
        dw, dm = boot_win_mean(c, v, U[date_col], n, seed)
        q = lambda a, p_: round(float(np.percentile(a, p_)), 3)                                      # noqa: E731
        out.update({"dwin_lo95": q(dw, 2.5), "dwin_hi95": q(dw, 97.5), "dwin_lo99": q(dw, 0.5), "dwin_hi99": q(dw, 99.5),
                    "dmean_lo95": q(dm, 2.5), "dmean_hi95": q(dm, 97.5)})
    return out


def r4_confirmed(ev: dict) -> bool:
    """证实：胜率差 99% 下限 > 0，且每笔差 95% 下限 > −R4_MARGIN（胜率升、每笔不差过 0.30 pp）。"""
    return ev.get("dwin_lo99") is not None and ev["dwin_lo99"] > 0 and ev["dmean_lo95"] > -R4_MARGIN


def r4_refuted(ev: dict) -> bool:
    """否定：胜率差 95% 上限 < 0，或每笔差 95% 上限 < −R4_MARGIN。"""
    return ev.get("dwin_hi95") is not None and (ev["dwin_hi95"] < 0 or ev["dmean_hi95"] < -R4_MARGIN)


def r4_verdict_lines(ev: dict, when: str | None) -> list[str]:
    if not when:
        return []
    if "dwin_lo95" not in ev:
        return [f"判定（{when}）：成熟配对只有 {ev.get('n', 0)} 笔、算不出区间 → 证实 / 否定都不成立"]
    if r4_confirmed(ev):
        v = "**证实成立 = 新数据证实「R4 胜率更高、每笔不差」**（要改模拟盘还要另写一份登记的组合研究，并经用户确认）"
    elif r4_refuted(ev):
        v = "**否定成立** → 结束跟踪（记录照留）"
    else:
        v = "证实 / 否定都不成立（未定）"
    return [f"判定（{when}）：{v}；胜率差 {ev['dwin']:+.1f} pp（99% 区间 {ev['dwin_lo99']:+.1f}〜{ev['dwin_hi99']:+.1f}），"
            f"每笔差 {ev['dmean']:+.2f} pp（95% 区间 {ev['dmean_lo95']:+.2f}〜{ev['dmean_hi95']:+.2f}，界限 −{R4_MARGIN:.2f}）"]


def r4_summary_line(ev: dict) -> str:
    if not ev.get("n"):
        return "还没有成熟的配对"
    f = lambda s, h: f"胜率 {s['win']:.1f}% / 每笔 {s['mean']:+.2f}% / 持有中位 {h:g} 天"                     # noqa: E731
    ci = (f"（胜率差 95% 区间 {ev['dwin_lo95']:+.1f}〜{ev['dwin_hi95']:+.1f}、每笔差 95% 区间 {ev['dmean_lo95']:+.2f}〜{ev['dmean_hi95']:+.2f}）"
          if "dwin_lo95" in ev else "")
    return (f"成熟配对 {ev['n']} 笔（{ev.get('months', 0)} 个月）：现行 {f(ev['cur'], ev['hold_cur'])}；R4 {f(ev['r4'], ev['hold_r4'])}；"
            f"胜率差 {ev['dwin']:+.1f} pp、每笔差 {ev['dmean']:+.2f} pp{ci}")


def r4_history_row(ev: dict, run: str, scope: str, key: str, when, extra: dict | None = None) -> dict:
    judged = when is not None
    return {"run": run, "scope": scope, "closed": ev.get("n", 0), key: when, "r4_dwin": ev.get("dwin"), "r4_dwin_lo99": ev.get("dwin_lo99"),
            "r4_dwin_hi95": ev.get("dwin_hi95"), "r4_dmean": ev.get("dmean"), "r4_dmean_lo95": ev.get("dmean_lo95"),
            "r4_dmean_hi95": ev.get("dmean_hi95"), "r4_confirmed": r4_confirmed(ev) if judged else None,
            "r4_refuted": r4_refuted(ev) if judged else None, **(extra or {})}
