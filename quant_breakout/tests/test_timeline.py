"""买卖时间线（qbreak/timeline.py）：价位与日期必须和真实规则一致 ——
卖出：情景推算的「哪天卖、为什么卖」与真实引擎（UnifiedEngine._check_exits → 次日开盘卖）在同一段假设 K 线上逐条相同；
      卖出线：收在线下一点点 → 引擎当天判卖（次日开盘卖）、线上一点点 → 不因这条卖；
买入：买点区间的上下沿、成交量门槛（放量 / 周五凑够周线量比）用 compute_indicators 逐个核对；
另有组装（名额、挡住的理由、日历）与页面渲染的冒烟测试。"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import exit_rules as EXR                                         # noqa: E402
from qbreak import timeline as TL                                             # noqa: E402
from qbreak.config import StrategyParams                                     # noqa: E402
from qbreak.mtf import live_calendar, weekly_volume_ratio                    # noqa: E402
from qbreak.strategy import compute_indicators                               # noqa: E402
from qbreak.unified import UnifiedEngine                                      # noqa: E402

from test_live_unified import CC, CFG, EX                                    # noqa: E402

REV = {v: k for k, v in TL.REASON.items()}
W2 = dict(min_weekly_vol_ratio=1.0, max_distribution_days=6, max_upper_shadow_ratio=3.0, earnings_blackout_days=2)


def _walk(seed, n=320, drift=0.0005, vol=0.018, p0=1000.0):
    rng = np.random.default_rng(seed)
    c = p0 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    o = np.r_[p0, c[:-1]] * np.exp(rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n)))
    v = rng.lognormal(np.log(1e6), 0.35, n)
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": v}, index=pd.bdate_range("2025-01-06", periods=n))


def _core(idx):
    d = pd.DataFrame({"Open": 700.0, "High": 700.0, "Low": 700.0, "Close": 700.0, "Volume": 1e6}, index=idx)
    d["entry"], d["dead_cross"], d["atr"], d["climax"] = False, False, 14.0, False
    return d


def _engine(frame, p, sig_i):
    """同一只票只在 sig_i 那天出信号（次日开盘买），引擎逐日走完 frame（不调 result()，持仓留着）。"""
    ind = compute_indicators(frame, p)
    ind["entry"] = False
    ind.iloc[sig_i, ind.columns.get_loc("entry")] = True
    e = UnifiedEngine({"A.T": ind, "1655.T": _core(frame.index)}, CFG, {"JP": p, "US": p}, EX, CC,
                      bear={"US": pd.Series(False, index=frame.index)})
    e.prime(5)
    for i in range(5, len(frame.index)):
        e.step(i)
    return e


def _pos(ps):
    return {"entry_px": ps.entry_px, "entry_date": ps.entry_date, "stop_px": ps.stop_px, "peak": ps.peak, "hold": ps.hold,
            "armed": ps.armed, "shares": ps.shares}


def _days(base, n):
    return [d.date() for d in pd.bdate_range(base.index[-1] + pd.Timedelta(days=1), periods=n)]


def _open_position(seed, p, off):
    base = _walk(seed)
    sig = len(base) - off
    e = _engine(base, p, sig)
    ps = e.st.pos.get("A.T")
    assert ps is not None and not e.st.pending_exit, "样本选错了：持仓在数据日之前已经卖了"
    return base, sig, _pos(ps)


def _engine_exit(base, p, sig, days, closes, vol):
    e = _engine(TL.with_bars(base, days[:len(closes)], closes, [vol] * len(closes)), p, sig)
    tr = [t for t in e.st.trades if t["ticker"] == "A.T"]
    return (tr[-1]["exit_date"], tr[-1]["reason"]) if tr else None


# ───────────────────────── 闭式解 ─────────────────────────
def test_min_volume_and_cross_level_are_exact():
    p = StrategyParams()
    base = _walk(5, n=300, drift=0.0, vol=0.007)
    s1 = _days(base, 1)[0]
    c = float(base["Close"].iloc[-1])
    v = TL.min_volume(base, p.vol_ma_n, p.vol_mult)

    def row(x, vol):
        return compute_indicators(TL.with_bars(base, [s1], [x], [vol]), p).iloc[-1]
    assert bool(row(c, v)["vol_surge"]) and not bool(row(c, v - 1)["vol_surge"])        # 量比 > 1.5 的最小整数股数
    m, s, x = TL.cross_level(base["Close"], p)
    assert m <= s                                                                     # 这个样本：MACD 在信号线下方
    up, dn = row(x * (1 + 1e-6), v), row(x * (1 - 1e-6), v)
    assert up["macd"] > up["macd_sig"] and bool(up["golden_cross"])                   # 收在临界价之上 → 金叉
    assert dn["macd"] < dn["macd_sig"] and not bool(dn["golden_cross"])


def test_sessions_after_skip_tse_holidays():
    assert TL.sessions_after(dt.date(2026, 9, 18), 3) == [dt.date(2026, 9, 24), dt.date(2026, 9, 25), dt.date(2026, 9, 28)]
    assert TL.sessions_after(dt.date(2026, 12, 29), 2) == [dt.date(2026, 12, 30), dt.date(2027, 1, 4)]


# ───────────────────────── 卖出：与真实引擎逐条核对 ─────────────────────────
EXIT_CASES = [  # (离场方式, 最长持有, 随机种子, 数据日时已持有约几天, 情景每天涨跌, 期待的引擎理由)
    ("DC", 60, 9, 8, -0.03, "trail"),
    ("DC", 60, 7, 8, -0.01, "stop"),
    ("DC", 60, 3, 8, -0.01, "dead_cross"),
    ("DC", 60, 3, 8, 0.03, "take_profit"),
    ("DC", 60, 3, 8, 0.0, None),
    ("X6", 60, 3, 15, -0.01, "chandelier"),
    ("X6", 60, 3, 8, -0.03, "stop"),
    ("X6", 60, 6, 8, 0.03, "take_profit"),
    ("X6", 20, 3, 15, 0.0, "max_hold"),
    ("R4", 20, 3, 8, -0.01, "sar_flip"),
    ("R4", 20, 3, 15, 0.01, "max_hold"),
    ("ALL", 60, 14, 8, -0.01, "chandelier"),
]


@pytest.mark.parametrize("mode,mh,seed,off,rate,want", EXIT_CASES)
def test_scenario_exit_matches_engine(mode, mh, seed, off, rate, want):
    p = EXR.apply(StrategyParams(exit_on_climax=True, max_hold_days=mh), mode)
    base, sig, pos = _open_position(seed, p, off)
    days = _days(base, 12)
    sc = TL.scenario_exit(base, p, pos, days, rate)
    c0, n = float(base["Close"].iloc[-1]), len(days) - 1
    closes = [c0 * (1 + rate) ** (k + 1) for k in range(n + 1)]                       # 多接一根：最后一天判卖也能在引擎里成交
    eng = _engine_exit(base, p, sig, days, closes, float(base["Volume"].tail(p.vol_ma_n).mean()))
    mine = (sc["sell_day"], REV[sc["reason"]]) if sc else None
    assert mine == eng
    assert (eng[1] if eng else None) == want


LEVEL_CASES = [("DC", 3, 8, "dead_cross"), ("DC", 7, 8, "stop"), ("DC", 9, 8, "trail"), ("X6", 3, 15, "chandelier"),
               ("X6", 6, 8, "chandelier")]


@pytest.mark.parametrize("mode,seed,off,want", LEVEL_CASES)
def test_sell_levels_match_engine(mode, seed, off, want):
    p = EXR.apply(StrategyParams(exit_on_climax=True), mode)
    base, sig, pos = _open_position(seed, p, off)
    days = _days(base, 70)
    sl = TL.sell_levels(base, p, pos, days)
    s2 = days[1].isoformat()
    vol = float(base["Volume"].tail(p.vol_ma_n).mean())
    fd = sl["first_down"]
    assert REV[fd["rule"].split("（持有以来")[0]] == want and fd["px"] == max(x["px"] for x in sl["levels"] if x["side"] == "down")
    below = _engine_exit(base, p, sig, days, [fd["px"] * (1 - 2e-4)] * 2, vol)
    above = _engine_exit(base, p, sig, days, [fd["px"] * (1 + 2e-4)] * 2, vol)
    assert below == (s2, want)                                                        # 收在线下 → s1 收盘判卖、s2 开盘卖
    assert above is None or above[0] != s2 or above[1] not in ("stop", "trail", "chandelier", "dead_cross")
    tp = [x for x in sl["levels"] if x["side"] == "up"][0]
    assert _engine_exit(base, p, sig, days, [tp["px"] * (1 + 2e-4)] * 2, vol) == (s2, "take_profit")
    dn = _engine_exit(base, p, sig, days, [tp["px"] * (1 - 2e-4)] * 2, vol)
    assert dn is None or dn[1] != "take_profit"
    mh = sl["max_hold"]                                                               # 满 60 天：第 60 − 已持有 个交易日收盘判、再下一天卖
    assert mh["k"] == p.max_hold_days - pos["hold"] and mh["sell_day"] == days[mh["k"]].isoformat()


def test_queued_and_expired_max_hold():
    p = EXR.apply(StrategyParams(), "X6")
    base, _, pos = _open_position(3, p, 15)
    days = _days(base, 70)
    old = TL.sell_levels(base, p, {**pos, "hold": 60}, days)["max_hold"]
    assert old == {"close_day": None, "sell_day": days[0].isoformat(), "k": 0}


# ───────────────────────── 买入：买点区间的上下沿与成交量门槛 ─────────────────────────
def _entry(base, p, s1, x, v):
    return bool(compute_indicators(TL.with_bars(base, [s1], [x], [v]), p).iloc[-1]["entry"])


@pytest.mark.parametrize("seed,w2", [(5, False), (6, False), (9, True), (11, True)])
def test_buy_trigger_band_edges(seed, w2):
    p = StrategyParams(**W2) if w2 else StrategyParams()
    base = _walk(seed, n=300 if not w2 else 299, drift=0.0, vol=0.007)
    s1 = _days(base, 1)[0]
    bt = TL.buy_trigger(base, p, s1)
    assert bt["lo"] and bt["hi"] and not bt["why"]
    lo, hi, v = bt["lo"], bt["hi"], bt["v_need"]
    assert _entry(base, p, s1, lo * (1 + 1e-4), v) and _entry(base, p, s1, (lo + hi) / 2, v)
    assert not _entry(base, p, s1, lo * (1 - 1e-3), v)
    assert bt["hi_open"] or not _entry(base, p, s1, hi * (1 + 1e-3), v)
    assert not _entry(base, p, s1, (lo + hi) / 2, v - 1)                              # 少一股就不算放量
    assert lo >= bt["x_gc"] - 0.01                                                    # 下沿不会低于金叉的临界价


@pytest.mark.parametrize("seed", [6, 16])
def test_buy_trigger_friday_needs_weekly_volume(seed):
    """s1 是周五：那天的成交量算进 W2 的周线量比 → 成交量够大 W2 也能过（区间照样给出，成交量门槛取两者较大）。"""
    p = StrategyParams(**W2)
    base = _walk(seed, n=299, drift=0.0, vol=0.007)
    s1 = _days(base, 1)[0]
    assert s1.weekday() == 4
    bt = TL.buy_trigger(base, p, s1)
    assert bt["lo"] and bt["v_w2"] and bt["v_need"] == bt["v_w2"] > bt["v_min"]
    x = bt["lo"] * 1.001

    def w5(v):
        fr = TL.with_bars(base, [s1], [x], [v])
        return float(weekly_volume_ratio(fr, live_calendar(fr.index)).iloc[-1])
    assert w5(bt["v_w2"]) >= 1.0 > w5(bt["v_w2"] - 1)                                # 线性闭式解：刚好凑够
    assert _entry(base, p, s1, x, bt["v_need"]) and not _entry(base, p, s1, x, bt["v_need"] - 1)
    assert not _entry(base, p, s1, x, bt["v_min"])                                    # 只放量不够：W2 挡住


def test_w2_min_volume_none_midweek():
    p = StrategyParams(**W2)
    base = _walk(6, n=300, drift=0.0, vol=0.007)                                     # 数据日周五 → s1 周一：不完成一周
    s1 = _days(base, 1)[0]
    assert s1.weekday() == 0 and TL.w2_min_volume(base, p, s1) is None
    assert TL.w2_min_volume(base, StrategyParams(), s1) is None                       # 没开 W2


def test_buy_trigger_reasons_when_no_band():
    p = StrategyParams()
    for seed, head in ((1, "MACD 已在信号线之上"), (2, "横盘不成立")):
        base = _walk(seed, n=300, drift=0.0, vol=0.007)
        bt = TL.buy_trigger(base, p, _days(base, 1)[0])
        assert bt["lo"] is None and bt["why"][0].startswith(head)


def test_scenario_entry_is_a_real_signal():
    """情景给出的那一天：按返回的成交量接上假设 K 线，完整的买入条件成立；少一股就不成立（放量或 W2 卡在刚好）。"""
    p = StrategyParams(**W2)
    n_hit = 0
    for seed in (5, 6, 16, 18, 22):
        base = _walk(seed, n=300, drift=0.0, vol=0.007)
        days = _days(base, TL.SCEN_DAYS + 1)
        c0, vol = float(base["Close"].iloc[-1]), float(base["Volume"].tail(20).mean())
        for _, r in TL.SCEN:
            h = TL.scenario_entry(base, p, days, r)
            if not h:
                continue
            n_hit += 1
            k = h["k"]
            closes = [c0 * (1 + r) ** (j + 1) for j in range(k)]
            assert h["signal_day"] == days[k - 1].isoformat() and h["buy_day"] == days[k].isoformat()
            assert _entry_path(base, p, days[:k], closes, [vol] * (k - 1) + [h["vol"]])
            assert not _entry_path(base, p, days[:k], closes, [vol] * (k - 1) + [h["vol"] - 1])
    assert n_hit >= 5


def _entry_path(base, p, days, closes, vols):
    return bool(compute_indicators(TL.with_bars(base, days, closes, vols), p)["entry"].iloc[-1])


def _tse_walk(seed, end=dt.date(2026, 9, 29), start=dt.date(2025, 7, 1)):
    """按东证日历（含 2026-09-21〜23 的连休：那一周只有 9/24、9/25 两个交易日）的横盘随机游走。"""
    from qbreak.calendar_jp import next_trading_day
    idx, x = [], start
    while x < end:
        x = next_trading_day(x)
        idx.append(pd.Timestamp(x))
    rng = np.random.default_rng(seed)
    n = len(idx)
    c = 1000 * np.exp(np.cumsum(rng.normal(0, 0.007, n)))
    o = np.r_[1000, c[:-1]] * np.exp(rng.normal(0, 0.003, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": rng.lognormal(np.log(1e6), 0.3, n)},
                        index=pd.DatetimeIndex(idx))


def test_week_end_and_holiday_week_w2():
    """连休只有 2 个交易日的那一周 → 周线量比 ≈ 0.4，W2 挡住；这一周（9/28〜10/2）在 10/2 收盘完成之前，时间线不会给出买点。"""
    assert TL.week_end(dt.date(2026, 9, 29)) == dt.date(2026, 10, 2) and TL.week_end(dt.date(2026, 9, 21)) == dt.date(2026, 9, 25)
    assert TL.week_end(dt.date(2026, 12, 28)) == dt.date(2026, 12, 30)
    p = StrategyParams(**W2)
    firsts = []
    for seed in (5, 16, 22, 24):
        base = _tse_walk(seed)
        assert compute_indicators(base, p)["w5v"].iloc[-1] < 0.7
        days = TL.sessions_after(base.index[-1].date(), TL.SCEN_DAYS + 1)
        bt = TL.buy_trigger(base, p, days[0])
        assert bt["lo"] is None and "10-02 收盘完成后才换成新的一周" in bt["why"][0]
        firsts += [v["signal_day"] for v in (TL.scenario_entry(base, p, days, r) for _, r in TL.SCEN) if v]
    assert firsts and min(firsts) >= "2026-10-02"                                     # 9/30、10/1 收盘都不会出买点


# ───────────────────────── 组装与渲染 ─────────────────────────
def test_hold_estimate_uses_remaining_quantiles():
    days = [dt.date(2026, 10, 1) + dt.timedelta(days=i) for i in range(30)]
    st = {"remaining": {"10": {"n": 80, "p25": 4.0, "p50": 9.0, "p75": 20.0}, "59": {"n": 5, "p25": 1.0, "p50": 1.0, "p75": 1.0}}}
    e = TL.hold_estimate(st, 10, days)
    assert e["date"] == days[9].isoformat() and e["n"] == 80                         # 剩 9 个收盘 → 第 9 个收盘判、再下一天卖
    assert TL.hold_estimate(st, 75, days)["n"] == 5                                   # 超过 59 天按 59 天那一档
    assert TL.hold_estimate(st, 3, days) is None and TL.hold_estimate(None, 3, days) is None


def test_build_and_html():
    p_in = StrategyParams(**W2)
    p_out = EXR.apply(StrategyParams(exit_on_climax=True), "X6")
    base_pos, _, pos = _open_position(3, p_out, 15)
    bar = base_pos.index[-1].date()
    idx = base_pos.index
    frames = {"P.T": base_pos}
    for t, seed in (("C1.T", 5), ("C2.T", 6), ("C3.T", 9)):
        fr = _walk(seed, n=len(idx), drift=0.0, vol=0.007)
        fr.index = idx
        frames[t] = fr
    s = TL.sessions_after(bar, 2)
    watch = [{"ticker": "C1.T", "status": "等待", "sector": "电气机器"}, {"ticker": "C2.T"}, {"ticker": "C3.T"}]
    tl = TL.build(frames, p_in, p_out, bar_date=bar, positions={"P.T": {**pos, "shares": 100}}, pending={}, plan={},
                  todo={"JP": [{"side": "SELL", "ticker": "1655.T", "qty": 3, "type": "寄付成行"}]}, watch=watch,
                  pool=["C1.T", "C2.T", "C3.T", "P.T"], equity=3_000_000, position_pct=0.25, max_positions=4,
                  em={"C2.T": 0.0}, earn={"C3.T": s[1].isoformat()}, blocked={"C1.T": "被踢出日経225"},
                  stats={"remaining": {str(pos["hold"]): {"n": 50, "p25": 3.0, "p50": 8.0, "p75": 15.0}}}, core={"1655.T"},
                  bullbear_us={"state": "bull", "flip_to": "bear", "level": 6000.0, "close": 6500.0, "distance_pct": -7.7,
                               "need_days": 5, "asof": str(bar)}, idle={"mode": "S0", "label": "S&P 500"})
    assert tl["s1"] == s[0].isoformat() and tl["s2"] == s[1].isoformat()
    assert tl["orders"] == [{"side": "SELL", "ticker": "1655.T", "qty": 3, "type": "寄付成行", "unit": "口"}]
    h = tl["holdings"][0]
    assert h["ticker"] == "P.T" and h["est"]["n"] == 50 and set(h["scen"]) == {nm for nm, _ in TL.SCEN}
    assert tl["slots"] == {"max": 4, "held": 1, "selling": 0, "buying": 0, "free": 3}
    cs = {c["ticker"]: c for c in tl["candidates"]}
    assert any(b.startswith("资格检查") for b in cs["C1.T"]["blocks"])
    assert any(b.startswith("新仓倍数 0") for b in cs["C2.T"]["blocks"])
    assert any("决算" in b for b in cs["C3.T"]["blocks"])                               # s2 当天决算 → 0 个交易日 ≤ 2
    assert tl["sweep_n"] == 3 and all(r["ticker"] != "P.T" for r in tl["sweep"])       # 持仓不进横展开
    items = [x for c in tl["calendar"] for x in c["items"]]
    assert any("周线完成" in x for x in items) and any("C3.T 决算" in x for x in items)
    TL.attach_states(tl, {"P.T": {"state": "T2", "label": "扭亏为盈", "effect": "+", "disc": "2026-08-07"}})
    assert tl["holdings"][0]["state"]["label"] == "扭亏为盈"
    from qbreak.earn_state import tag_html
    page = TL.html(tl, tag_html)
    for k in ("① ", "② 持仓", "③ 候补", "④ 横展开", "⑤ 闲置资金", "⑥ 日历", "非投资建议", "扭亏为盈", "被踢出日経225", "3 口"):
        assert k in page, k
    assert "这次没算出来" in TL.html({"error": "boom"}) and TL.html({}) == ""


def test_run_timeline_panel_wiring():
    """run.py 的 _timeline_panel：用模拟盘的 ctx / state / 候补队列拼起来（属性名、资格检查的理由、决算形态没有キー时只报原因）。"""
    from types import SimpleNamespace

    import run
    from qbreak.unified import UPos
    p = StrategyParams(**W2)
    ind = {t: compute_indicators(_tse_walk(seed), p) for t, seed in (("7203.T", 5), ("6758.T", 16), ("9984.T", 22))}
    c = float(ind["7203.T"]["Close"].iloc[-1])
    state = SimpleNamespace(last_date="2026-09-29", pending_exit={}, plan={},
                            pos={"7203.T": UPos("7203.T", "JP", 100, c * 0.98, "2026-09-10", c * 0.98 * 0.93, c * 1.02, c, hold=13)})
    ctx = SimpleNamespace(ind=ind, u={}, params={"JP": p}, xmode="X6",
                          ucfg=SimpleNamespace(core={"1655.T": 1.0}, position_pct=0.25, max_positions=4),
                          icmode="Q1", ic_status={"mode": "Q1", "label": "纳斯达克 100 1545 + 美股牛熊分界"})
    extras = {"JP": {"watchlist": [{"ticker": "6758.T", "status": "watch"}, {"ticker": "9984.T", "gate": "被踢出日経225"}]},
              "US": {"regime": {"bullbear": {"state": "bull", "flip_to": "bear", "level": 6000.0, "close": 6500.0,
                                             "distance_pct": -7.7, "need_days": 5, "asof": "2026-09-28"}}}}
    todo = {"JP": [{"side": "SELL", "ticker": "1655.T", "qty": 1130, "type": "寄付成行", "reason": "核心 ETF 调整"}]}
    out = run._timeline_panel(ctx, SimpleNamespace(_entry_mult=lambda t, i: 0.5), state, todo, extras, {"blocked": []},
                              1_000_000.0, dt.date(2026, 9, 30), 0, "csv")
    tl = out["timeline"]
    assert "error" not in tl and tl["s1"] == "2026-09-30" and tl["s2"] == "2026-10-01"
    assert [h["ticker"] for h in tl["holdings"]] == ["7203.T"] and tl["holdings"][0]["max_hold"]["k"] == 60 - 13
    cs = {x["ticker"]: x for x in tl["candidates"]}
    assert set(cs) == {"6758.T", "9984.T"} and "资格检查：被踢出日経225" in cs["9984.T"]["blocks"]
    assert cs["6758.T"]["mult"] == 0.5 and tl["orders"][0]["unit"] == "口" and tl["idle"]["label"].startswith("纳斯达克")
    assert tl["sweep_n"] == 2                                                        # 股票池里有行情、不在持仓的
    assert out["earn_state"]["note"].startswith("没有 JQUANTS_API_KEY")               # 测试不连 J-Quants：只报原因
