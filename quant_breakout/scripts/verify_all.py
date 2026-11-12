"""verify_all.py — 用真实数据逐项验证算法是否准确，输出 var/out/verification.md。

  V1 指标公式：用逐日循环重写的独立实现对照 compute_indicators（MACD / Wilder RSI / ATR / 箱体 / 量比 / 出货日 / 上影 / climax / entry）
  V2 无前视：截断到任一天重算，结果必须与全量计算在该天完全相同（指标、宏观特征、利率 beta、牛熊检测器、量化状态层）
  V3 回测引擎：与独立参考回测器（tests/reference_engine.py）逐笔对照，含/不含宏观倍数
  V4 实盘流水线：run_once + PaperBroker 按真实数据逐日回放，与回测引擎同窗口逐笔对照
  V5 公司行为：真实拆股 / 除息事件（yfinance actions）在模拟券商上的处理
用法：QBREAK_HOME 会被改到临时目录，不碰真实状态。python scripts/verify_all.py [--quick]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_HOME = ROOT / "var"
TMP = tempfile.mkdtemp(prefix="qbreak_verify_")
for sub in ("cache",):                                  # 复用真实行情缓存，状态写到临时目录
    if (REAL_HOME / sub).exists():
        shutil.copytree(REAL_HOME / sub, Path(TMP) / sub)
for f in ("best_params.json", "best_params_JP.json", "best_params_US.json", "bullbear.json", "sim.json"):
    if (REAL_HOME / f).exists():
        shutil.copy(REAL_HOME / f, Path(TMP) / f)
os.environ["QBREAK_HOME"] = TMP
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np                                        # noqa: E402
import pandas as pd                                       # noqa: E402

from qbreak.bullbear import Detector, hmm_filter, load_config  # noqa: E402
from qbreak.config import (BENCHMARK, BacktestConfig, DataConfig, ExecConfig, RiskConfig,  # noqa: E402
                           SizingConfig, universe)
from qbreak.data import load_universe                     # noqa: E402
from qbreak.engine import run_backtest                    # noqa: E402
from qbreak.macro import build_entry_mult, features_at, features_frame, load_macro_series, rate_beta_rank  # noqa: E402
from qbreak.regime import quant_regime, quant_regime_series  # noqa: E402
from qbreak.strategy import compute_indicators            # noqa: E402
from qbreak.tick import lot_size                          # noqa: E402
from qbreak.trader import load_params                     # noqa: E402
from reference_engine import reference_backtest           # noqa: E402

QUICK = "--quick" in sys.argv
ONLY = next((a.split("=", 1)[1].upper().split(",") for a in sys.argv if a.startswith("--only=")), None)      # 例：--only=V4
MARKETS = next((a.split("=", 1)[1].upper().split(",") for a in sys.argv if a.startswith("--markets=")), ["JP", "US"])


def want(v: str) -> bool:
    return ONLY is None or v.upper() in ONLY
RESULTS: list[dict] = []


def record(check: str, ok: bool, detail: str):
    RESULTS.append({"check": check, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + check + " — " + detail, flush=True)


# ─────────────────────────── V1 指标公式 ───────────────────────────
def ref_ema(x: np.ndarray, n: int) -> np.ndarray:
    a, out = 2 / (n + 1), np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def ref_wilder(x: np.ndarray, n: int) -> np.ndarray:
    """教科书 Wilder 平滑：前 n 个的简单平均作种子，之后 (prev×(n−1)+x)/n。"""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    out[n] = np.mean(x[1:n + 1])
    for i in range(n + 1, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def ref_indicators(df: pd.DataFrame, p) -> dict[str, np.ndarray]:
    o, h, l, c, v = (df[k].values.astype(float) for k in ("Open", "High", "Low", "Close", "Volume"))
    N = len(c)
    line = ref_ema(c, p.macd_fast) - ref_ema(c, p.macd_slow)
    sig = ref_ema(line, p.macd_signal)
    rng = np.full(N, np.nan)
    for i in range(p.range_n - 1, N):
        hi, lo = h[i - p.range_n + 1:i + 1].max(), l[i - p.range_n + 1:i + 1].min()
        rng[i] = (hi - lo) / lo * 100
    volma = np.full(N, np.nan)
    for i in range(p.vol_ma_n - 1, N):
        volma[i] = v[i - p.vol_ma_n + 1:i + 1].mean()
    d = np.r_[np.nan, np.diff(c)]
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ru, rd = ref_wilder(up, p.rsi_n), ref_wilder(dn, p.rsi_n)
    rsi = np.where(rd == 0, 100.0, 100 - 100 / (1 + ru / np.where(rd == 0, np.nan, rd)))
    tr = np.r_[h[0] - l[0], np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])]
    atr = ref_wilder(np.r_[np.nan, tr[1:]], p.atr_n)
    dist = np.full(N, np.nan)
    down_vol = np.r_[False, (c[1:] / c[:-1] - 1 < -0.002) & (v[1:] > v[:-1])]
    for i in range(p.distribution_lookback - 1, N):
        dist[i] = down_vol[i - p.distribution_lookback + 1:i + 1].sum()
    body = np.abs(c - o)
    shadow = np.where(body > 0, (h - np.maximum(c, o)) / np.where(body > 0, body, 1), np.nan)
    climax = (v > volma * p.climax_vol_mult) & (c < o)
    golden = np.r_[False, (line[1:] > sig[1:]) & (line[:-1] <= sig[:-1])]
    dead = np.r_[False, (line[1:] < sig[1:]) & (line[:-1] >= sig[:-1])]
    is_range = np.r_[False, rng[:-1] < p.range_x_pct]
    entry = is_range & golden & (np.abs(line) / c * 100 < p.macd_zero_band_pct) & (v / volma > p.vol_mult)
    if p.max_distribution_days:
        entry &= dist < p.max_distribution_days
    if p.max_upper_shadow_ratio:
        entry &= ~(shadow > p.max_upper_shadow_ratio)
    return {"macd": line, "macd_sig": sig, "range_pct": rng, "vol_ratio": v / volma, "rsi": rsi, "atr": atr,
            "dist_days": dist, "upper_shadow_ratio": shadow, "climax": climax, "golden_cross": golden,
            "dead_cross": dead, "entry": entry}


def v1_formulas(data: dict, market: str, p):
    burn = 250                                   # Wilder 种子不同（pandas 以首值为种子）→ 250 根之后应收敛
    worst, mism, n = {}, 0, 0
    for t, df in list(data.items())[: (15 if QUICK else 60)]:
        got = compute_indicators(df, p)
        ref = ref_indicators(df, p)
        for k, rv in ref.items():
            gv = got[k].values
            if k in ("climax", "golden_cross", "dead_cross", "entry"):
                a, b = np.asarray(gv[burn:], bool), np.asarray(rv[burn:], bool)
                mism += int((a != b).sum()); n += len(a)
            else:
                a, b = np.asarray(gv[burn:], float), np.asarray(rv[burn:], float)
                both = np.isfinite(a) & np.isfinite(b)
                rel = np.abs(a[both] - b[both]) / np.maximum(np.abs(b[both]), 1e-9)
                nanmis = int((np.isfinite(a) != np.isfinite(b)).sum())
                worst[k] = max(worst.get(k, 0.0), float(rel.max()) if len(rel) else 0.0, 1.0 if nanmis else 0.0)
    ok = mism == 0 and all(v < 1e-6 for v in worst.values())
    record(f"V1 指标公式 {market}", ok, f"布尔列不一致 {mism}/{n}；连续列最大相对误差 " +
           ", ".join(f"{k} {v:.1e}" for k, v in worst.items()))


# ─────────────────────────── V2 无前视 ───────────────────────────
def same(a, b) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return bool(np.all((a == b) | (np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= 1e-9 * np.maximum(1, np.abs(b)))))


def v2_causality(data: dict, market: str, p, idx_df: pd.DataFrame, frame: pd.DataFrame, series: dict):
    rng = np.random.default_rng(7)
    bad = 0
    tick = list(data)[: (8 if QUICK else 25)]
    for t in tick:
        df = data[t]
        full = compute_indicators(df, p, idx_df["Close"])
        for k in rng.integers(300, len(df) - 1, size=12):
            part = compute_indicators(df.iloc[:k + 1], p, idx_df["Close"].loc[:df.index[k]])
            a, b = part.iloc[-1], full.iloc[k]
            for col in full.columns:
                if not same([float(a[col])] if not isinstance(a[col], (bool, np.bool_)) else [float(a[col])],
                            [float(b[col])] if not isinstance(b[col], (bool, np.bool_)) else [float(b[col])]):
                    bad += 1
    record(f"V2 指标无前视 {market}", bad == 0, f"{len(tick)} 只 × 12 个截断点，不一致 {bad} 处")
    # 宏观特征 / 倍数矩阵
    bad = 0
    dates = frame.index
    for k in rng.integers(300, len(dates) - 1, size=10):
        cut = dates[k]
        fr2 = features_frame({kk: s.loc[:cut] for kk, s in series.items()})
        f1, f2 = features_at(frame, cut), features_at(fr2, cut)
        if f1.to_dict() != f2.to_dict():
            bad += 1
    record(f"V2 宏观特征无前视 {market}", bad == 0, f"10 个截断点，不一致 {bad}")
    closes = pd.DataFrame({t: data[t]["Close"] for t in list(data)[:40]})
    r_full = rate_beta_rank(closes, frame["us10y"], market)
    bad = 0
    for k in rng.integers(400, len(closes) - 1, size=8):
        cut = closes.index[k]
        r_part = rate_beta_rank(closes.loc[:cut], frame["us10y"].loc[:cut], market)
        if not same(r_part.iloc[-1].values, r_full.loc[cut].values):
            bad += 1
    record(f"V2 利率 beta 无前视 {market}", bad == 0, f"8 个截断点，不一致 {bad}")


def v2_detectors(market: str, idx_full: pd.DataFrame):
    cfg = load_config()
    c = idx_full["Close"]
    dets = [Detector(cfg["detector"]["kind"], cfg["detector"]["params"]), Detector("dd_rally", {"x": 0.1, "y": 0.15}),
            Detector("hybrid", {"L": 200, "b": 0.02, "x": 0.08, "y": 0.15}), Detector("cross", {"fast": 50, "slow": 200})]
    rng = np.random.default_rng(3)
    bad = 0
    for det in dets:
        full = det.states(c)
        for k in rng.integers(300, len(c) - 1, size=15):
            part = det.states(c.iloc[:k + 1])
            if not np.array_equal(part, full[:k + 1]):
                bad += 1
    from qbreak.bullbear import hmm_fit
    r = c.pct_change().fillna(0).values * 100
    prm = hmm_fit(r[:3000], iters=60)
    pf = hmm_filter(r, prm)
    for k in rng.integers(3000, len(r) - 1, size=10):
        if not np.allclose(hmm_filter(r[:k + 1], prm), pf[:k + 1]):
            bad += 1
    record(f"V2 牛熊检测器无前视 {market}", bad == 0, f"4 类检测器 × 15 截断 + HMM 滤波 × 10，不一致 {bad}")
    qs = quant_regime_series(idx_full)
    bad = 0
    for k in rng.integers(260, len(idx_full) - 1, size=15):
        live = quant_regime(idx_full.iloc[:k + 1], market)
        if abs(live.quant_mult - qs.iloc[k]) > 1e-12:
            bad += 1
    record(f"V2 量化状态层 实盘函数 = 回测序列 {market}", bad == 0, f"15 个日期，不一致 {bad}")


# ─────────────────────────── V3 引擎 vs 参考实现 ───────────────────────────
def compare(eng, ref_tr, ref_eq, label):
    key = lambda df: df.sort_values(["entry_date", "ticker"]).reset_index(drop=True)  # noqa: E731
    et, rt = key(eng.trades), key(ref_tr)
    ok = len(et) == len(rt)
    detail = f"引擎 {len(et)} 笔 / 参考 {len(rt)} 笔"
    if ok:
        ok &= all((et[c].values == rt[c].values).all() for c in ("ticker", "shares", "reason"))
        ok &= bool((pd.to_datetime(et["entry_date"]).values == pd.to_datetime(rt["entry_date"]).values).all())
        ok &= bool((pd.to_datetime(et["exit_date"]).values == pd.to_datetime(rt["exit_date"]).values).all())
        pe = float(max(np.abs(et["entry_px"] - rt["entry_px"]).max(), np.abs(et["exit_px"] - rt["exit_px"]).max()))
        ed = float(np.nanmax(np.abs(eng.equity.values - ref_eq.reindex(eng.equity.index).values)))
        ok &= pe < 1e-3 and ed < 1e-3 * max(1.0, float(eng.equity.iloc[-1]))
        detail += f"；价格最大差 {pe:.1e}；权益最大差 {ed:.2e}"
    record(label, ok, detail)


def v3_engine(data: dict, market: str, p, frame: pd.DataFrame):
    ind = {t: compute_indicators(df, p) for t, df in data.items()}
    s = {"JP": (0.34, 3), "US": (0.20, 5)}[market]
    bt = BacktestConfig.for_market(market, 5)
    bt.sizing.position_pct, bt.sizing.max_positions = s
    bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, s[0])
    eng = run_backtest(ind, p, bt)
    rt, req = reference_backtest(ind, p, bt, lot_of=lambda t: lot_size(t, market))
    compare(eng, rt, req, f"V3 引擎 = 参考实现 {market}（无宏观层）")
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    closes = pd.DataFrame({t: df["Close"] for t, df in data.items()})
    M, _ = build_entry_mult(gidx, list(ind), market, frame, use_macro=True, use_sector=True, use_events=False, closes=closes)
    eng2 = run_backtest(ind, p, bt, entry_mult=M)
    rt2, req2 = reference_backtest(ind, p, bt, entry_mult=M, lot_of=lambda t: lot_size(t, market))
    compare(eng2, rt2, req2, f"V3 引擎 = 参考实现 {market}（宏观倍数 + 板块倾斜）")
    return ind, bt


# ─────────────────────────── V4 实盘流水线回放 ───────────────────────────
def v4_replay(data: dict, market: str, p, ind: dict, bt, days: int):
    import qbreak.trader as trader_mod
    from qbreak.brokers import PaperBroker
    from qbreak.trader import run_once
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    window = gidx[-(days + 5):-5]                    # 避开最近几天（可能含未收盘 K 线）
    d0 = window[0]
    home = Path(os.environ["QBREAK_HOME"])
    for f in home.glob("state/*"):
        f.unlink()
    orig = trader_mod.load_universe
    cur = {"d": None}
    trader_mod.load_universe = lambda tickers, cfg=None, use_cache=True: {
        t: data[t].loc[:cur["d"]] for t in tickers if t in data and len(data[t].loc[:cur["d"]]) >= 100}
    try:
        ex = ExecConfig.for_market(market)
        broker = PaperBroker(initial_cash=bt.sizing.initial_cash, exec_cfg=ex, market=market)
        risk = RiskConfig(daily_max_loss_pct=100, max_drawdown_pct=100, max_consecutive_losses=0,
                          max_new_positions_per_day=bt.sizing.max_positions, max_order_value=1e12,
                          max_positions=bt.sizing.max_positions, require_arm=False)
        sizing = SizingConfig(initial_cash=bt.sizing.initial_cash, position_pct=bt.sizing.position_pct,
                              max_positions=bt.sizing.max_positions, max_position_pct=bt.sizing.max_position_pct)
        eq_live = {}
        for d in window:
            cur["d"] = d
            run_once(list(data), broker, p, risk, sizing, DataConfig(provider="csv", years=5, min_bars=100),
                     market=market, today=d.date(), exec_cfg=ex, allow_stale=True)
            eq_live[d] = broker.equity()
    finally:
        trader_mod.load_universe = orig
    eng = run_backtest(ind, p, bt, start=d0, end=window[-1])
    st = json.loads((home / "state" / f"paper_state_{market}.json").read_text(encoding="utf-8"))
    live_tr = pd.DataFrame(st["closed_trades"])
    eng_tr = eng.trades[eng.trades["reason"] != "end"]
    # 逐笔对照（实盘的 entry/exit_date 是成交 K 线日期，与引擎同口径）
    key = ["entry_date", "ticker"]
    a = live_tr.assign(entry_date=live_tr["entry_date"].astype(str).str[:10]) if len(live_tr) else pd.DataFrame(columns=key)
    b = eng_tr.assign(entry_date=pd.to_datetime(eng_tr["entry_date"]).dt.strftime("%Y-%m-%d")) if len(eng_tr) else pd.DataFrame(columns=key)
    m = a.merge(b, on=key, how="outer", suffixes=("_live", "_eng"), indicator="match")
    cols = [c for c in ["entry_date", "ticker", "shares_live", "shares_eng", "entry_px_live", "entry_px_eng",
                        "exit_date_live", "exit_date_eng", "exit_px_live", "exit_px_eng", "pnl_live", "pnl_eng",
                        "reason", "match"] if c in m.columns]
    m = m[cols].sort_values(key)
    m.to_csv(REAL_HOME / "out" / f"verification_v4_{market}.csv", index=False)
    both = m[m["match"] == "both"]
    bad = both[(both["shares_live"] != both["shares_eng"]) | ((both["exit_px_live"] - both["exit_px_eng"]).abs() > 1e-3)]
    n_ok = len(live_tr) == len(eng_tr) and (m["match"] == "both").all() and bad.empty
    le = pd.Series(eq_live)
    diff = float(np.nanmax(np.abs(le.values - eng.equity.reindex(le.index).values)))
    ok = n_ok and diff < 1e-3 * float(le.iloc[-1])
    first = ""
    if not ok:
        odd = m[(m["match"] != "both")]
        rows = pd.concat([odd, bad]).sort_values(key).head(3)
        first = "；首个差异 " + " / ".join(
            f"{r.entry_date} {r.ticker} {r.match} 股数 {getattr(r, 'shares_live', '')}/{getattr(r, 'shares_eng', '')}"
            for r in rows.itertuples())
    record(f"V4 实盘流水线回放 = 回测 {market}", ok,
           f"{window[0].date()}～{window[-1].date()} {len(window)} 个交易日；已平仓 实盘 {len(live_tr)} / 回测 {len(eng_tr)} 笔；"
           f"权益最大差 {diff:,.4f}；持仓 实盘 {sorted(json.loads((home / 'state' / f'paper_state_{market}.json').read_text())['positions'])} "
           f"/ 回测期末 {sorted(eng.trades[eng.trades['reason'] == 'end']['ticker'])}{first}")


# ─────────────────────────── V5 公司行为（真实事件）───────────────────────────
def v5_corp_actions():
    import yfinance as yf
    from qbreak.brokers import PaperBroker
    from qbreak.corpactions import DIV_NET, YFinanceActions, due
    from qbreak.trader import PositionBook, _apply_corp_actions, DayResult
    cases = [("NVDA", "US", "2024-06-07", "2024-06-10"), ("8058.T", "JP", "2023-12-27", "2023-12-28"),
             ("7203.T", "JP", "2025-09-26", "2025-09-29")]
    prov = YFinanceActions()
    for t, m, before, on in cases:
        acts = due(prov, t, before, on)
        h = yf.Ticker(t).history(start="2023-06-01", end="2025-12-31", auto_adjust=False)
        h.index = h.index.tz_localize(None).normalize()
        split0 = next((a["split"] for a in acts if a.get("split")), 0)
        # yfinance 的 history 即使 auto_adjust=False 也按拆股复权 → 拆股前的真实价格要乘回拆股比例
        raw_before = float(h.loc[before, "Close"]) * (split0 or 1)
        raw_on = float(h.loc[on, "Open"])
        home = Path(os.environ["QBREAK_HOME"])
        for f in home.glob("state/*"):
            f.unlink()
        ex = ExecConfig(market=m, commission_pct=0, slippage_pct=0)
        b = PaperBroker(initial_cash=10_000_000, exec_cfg=ex, market=m)
        qty = 100 if m == "JP" else 10
        b.state["positions"][t] = {"qty": qty, "avg_px": raw_before, "peak": raw_before, "stop_px": raw_before * 0.93,
                                   "entry_date": before, "hold_bars": 1, "last_bar": before}
        b._save()
        book = PositionBook()
        book.book[t] = {"peak": raw_before, "stop_px": raw_before * 0.93, "entry_date": before, "hold_bars": 1,
                        "last_bar": before, "last_close": raw_before}
        book.save()
        cash0 = b.cash()
        res = DayResult()
        _apply_corp_actions(prov, b, book, {}, on, m, res)
        pos = b.positions()[t]
        split = next((a["split"] for a in acts if a.get("split")), 0)
        div = next((a["dividend"] for a in acts if a.get("dividend")), 0)
        exp_qty = int(qty * split) if split else qty
        exp_cash = cash0 + (div * qty * DIV_NET[m] if div else 0)
        stop_new = float(PositionBook().book[t]["stop_px"])
        exp_stop = raw_before * 0.93 / split if split else raw_before * 0.93 - div
        value_before, value_after = qty * raw_before, pos.qty * raw_on + (b.cash() - cash0)
        ok = (pos.qty == exp_qty and abs(b.cash() - exp_cash) < 0.01 and abs(stop_new - exp_stop) < 1e-6
              and abs(value_after / value_before - 1) < 0.08)          # 只差一夜的价格变动
        record(f"V5 公司行为 {t} {on}", ok,
               f"yfinance 事件 {acts}；股数 {qty}→{pos.qty}；止损 {raw_before*0.93:,.2f}→{stop_new:,.2f}；"
               f"入账 {b.cash()-cash0:,.2f}；除权前市值 {value_before:,.0f} vs 除权日开盘市值+分红 {value_after:,.0f}")


def main():
    t0 = time.time()
    for market in MARKETS:
        dcfg = DataConfig(provider="yfinance", years=5, allow_synthetic=False).validate()
        data = load_universe(universe(market, "broad"), dcfg)
        p = load_params(market=market)
        idx_df = load_universe([BENCHMARK[market]], DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())[BENCHMARK[market]]
        series = load_macro_series(dcfg)
        frame = features_frame(series)
        if want("V1"):
            v1_formulas(data, market, p)
        if want("V2"):
            v2_causality(data, market, p, idx_df, frame, series)
            v2_detectors(market, idx_df)
        if want("V3") or want("V4"):
            ind, bt = v3_engine(data, market, p, frame)
        if want("V4"):
            v4_replay(data, market, p, ind, bt, days=(60 if QUICK else 250))
    if want("V5"):
        v5_corp_actions()
    ok = all(r["ok"] for r in RESULTS)
    lines = [f"# 算法验证报告（{dt.date.today()}，{'快速' if QUICK else '完整'}模式，用时 {time.time()-t0:.0f}s）", "",
             f"结论：{'全部通过' if ok else '存在未通过项'}（{sum(r['ok'] for r in RESULTS)}/{len(RESULTS)}）", "",
             "| 检查 | 结果 | 细节 |", "|---|---|---|"]
    lines += [f"| {r['check']} | {'通过' if r['ok'] else '**未通过**'} | {r['detail']} |" for r in RESULTS]
    out = REAL_HOME / "out" / ("verification.md" if ONLY is None and MARKETS == ["JP", "US"] else "verification_partial.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{'ALL PASS' if ok else 'SOME FAIL'} → {out}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
