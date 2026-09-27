"""fins_event_data.py — 決算 / 会社予想修正的「开示事件」表，和「开示本身当买点」的逐笔回测（数据层；候选与判定在 scripts/fins_event_study.py）。

数据：J-Quants Standard 決算短信サマリー批量文件（qbreak/jq_data.py DATASETS["fins"]，全市场 2016-09 起；原始数据只在缓存、不入库）
  + 全市场日线面板（scripts/allstock_data.py：调整后 OHLCV、R = 未调整收盘 ÷ 调整后收盘、VA 成交额、上市掩码）。
事件表（每条开示一行）：code / ticker、date 开示日、time 开示时刻、doc 文件类型、per 期间、fy 予想对应的决算期末、fc 予想值、
  rev 与同一决算期上一次予想相比的修正 %（第一次出现的予想 → 缺值；qbreak/jq_data.fins_events 同一算法，利润档 = 营业 → 经常 → 净利润）、
  yoy 累计实绩对上年同期 %、after_close 开示时刻 ≥ 15:00（缺时刻当 True）、sig_day 信号日 = 开示日当天或之前最后一个交易日
  （不管盘中还是盘后开示，都在 sig_day 的下一个交易日开盘买 → 偏保守）；lot_yen 信号日一手（100 股）的真实金额、va20 信号日前 20 日平均成交额
  （只作描述 / 分段，不作过滤：用户 2026-09-27「取消小盘股受一手金额和流动性限制」）。
逐笔：event_trades —— 事件所在的票按现行参数算指标表（compute_indicators：MACD 死叉等出场用），entry 改成「sig_day = 事件」，
  每只票单独、一次一仓、现行卖出规则、扣立花 ¥25 万一笔的来回成本（scripts/candle_posthoc.trades 同一套）；返回每笔 + 对应事件的字段。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import jq_data as JD                                             # noqa: E402
from qbreak import jquants as JQ                                             # noqa: E402

EVENT_COLS = ["code", "ticker", "date", "time", "doc", "per", "fy", "fc", "rev", "yoy", "after_close", "sig_day"]
AFTER_CLOSE = "15:00"


def load_fins(refresh: bool = False) -> pd.DataFrame:
    path, cols = JD.DATASETS["fins"]
    if refresh:
        files = JD.bulk_download(JQ.JQuants(), path, log=lambda s: print(s, file=sys.stderr, flush=True))
    else:
        d = JD.bulk_dir() / path.strip("/")
        files = sorted(d.glob("historical/*/*.csv.gz")) + sorted(d.glob("historical/*.csv.gz")) + sorted(d.glob("live/*.csv.gz"))
    return JD.read_bulk(files, cols)


def signal_days(dates, days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """开示日 → 当天或之前最后一个交易日（days 升序）；早于第一个交易日 → NaT。"""
    d = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    k = days.searchsorted(d.to_numpy(), side="right") - 1
    out = days.to_numpy()[np.clip(k, 0, len(days) - 1)]
    return pd.DatetimeIndex(np.where(k >= 0, out, np.datetime64("NaT")))


def events_table(F: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """決算短信全表 → 事件表（EVENT_COLS）。fins_events 的行序 = 按 (DiscDate, DiscTime) 稳定排序后的 F 行序，据此对回文件类型与时刻。"""
    rows = []
    sort_cols = ["DiscDate", "DiscTime"] if "DiscTime" in F.columns else ["DiscDate"]
    for code, g in F.groupby("Code"):
        t = JQ.to_yf(code)
        if t is None:
            continue
        gs = g.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
        ev = JD.fins_events(gs)
        if ev.empty or len(ev) != len(gs):
            continue
        tm = gs["DiscTime"].fillna("").astype(str) if "DiscTime" in gs.columns else pd.Series("", index=gs.index)
        for k in range(len(gs)):
            r = ev.iloc[k]
            rows.append((str(code), t, pd.Timestamp(r["date"]), tm.iat[k], str(gs.at[k, "DocType"] or ""), str(gs.at[k, "CurPerType"] or ""),
                         r["fy"], r["fc"], r["rev"], r["yoy"]))
    E = pd.DataFrame(rows, columns=EVENT_COLS[:10])
    if not len(E):
        return pd.DataFrame(columns=EVENT_COLS)
    tm = E["time"].astype(str)
    E["after_close"] = (tm == "") | (tm >= AFTER_CLOSE)
    E["sig_day"] = signal_days(E["date"], days)
    return E.dropna(subset=["sig_day"]).reset_index(drop=True)


def describe_events(A: dict, E: pd.DataFrame) -> pd.DataFrame:
    """事件表 + 面板 → 加 lot_yen（信号日一手真实金额 = 调整后收盘 × R × 100）、va20（信号日前 20 日平均成交额，円）；对不上的缺值。"""
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    di = pd.Index(days)
    C, R = A["C"], A["R"]
    VA = pd.DataFrame(A["VA"], index=days, columns=names).rolling(20, min_periods=10).mean().shift(1).to_numpy()
    lot, va = np.full(len(E), np.nan), np.full(len(E), np.nan)
    for k, (t, d) in enumerate(zip(E["ticker"], E["sig_day"])):
        j = col.get(t)
        i = di.get_loc(d) if (j is not None and d in di) else None
        if i is None:
            continue
        c, r = float(C[i, j]), float(R[i, j])
        if np.isfinite(c) and np.isfinite(r) and r > 0:
            lot[k] = c * r * 100
        va[k] = float(VA[i, j])
    out = E.copy()
    out["lot_yen"], out["va20"] = lot, va
    return out


def event_frames(A: dict, ev_sel: pd.DataFrame, p) -> dict[str, pd.DataFrame]:
    """ev_sel（事件表的子集）→ {票: 指标表}，entry = 那只票的 sig_day（面板里有行情的日子才算）。"""
    from qbreak.strategy import compute_indicators
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    out = {}
    for t, g in ev_sel.groupby("ticker"):
        j = col.get(t)
        if j is None:
            continue
        ok = np.isfinite(A["C"][:, j]) & np.isfinite(A["O"][:, j])
        if ok.sum() < 80:
            continue
        df = pd.DataFrame({"Open": A["O"][ok, j], "High": A["H"][ok, j], "Low": A["L"][ok, j], "Close": A["C"][ok, j],
                           "Volume": A["V"][ok, j]}, index=days[ok]).astype(float)
        ind = compute_indicators(df, p)
        ind["entry"] = ind.index.isin(pd.DatetimeIndex(g["sig_day"]))
        if ind["entry"].any():
            out[t] = ind
    return out


def event_trades(A: dict, ev_sel: pd.DataFrame, p, start: str) -> pd.DataFrame:
    """事件当买点的逐笔（candle_posthoc.trades：一次一仓、现行卖出、扣成本）+ 对应事件的字段（同一票同一天多条开示 → 取第一条）。"""
    import candle_posthoc as CPH
    fr = event_frames(A, ev_sel, p)
    if not fr:
        return pd.DataFrame(columns=["ticker", "sig_date", "net", "hold_days", "entry_date"])
    T = CPH.trades(fr, p, start)
    if not len(T):
        return T
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    key = ev_sel.drop_duplicates(subset=["ticker", "sig_day"]).set_index(["ticker", "sig_day"])
    keep = [c for c in ("date", "time", "doc", "per", "rev", "yoy", "after_close", "lot_yen", "va20") if c in key.columns]
    J = key[keep].reindex(pd.MultiIndex.from_arrays([T["ticker"], T["sig_date"]]))
    for c in keep:
        T[f"ev_{c}"] = J[c].to_numpy()
    return T.reset_index(drop=True)
