"""一个账户的实盘执行器（qbreak/live_unified.py）：
① 执行器 + 模拟券商逐日走「对账 → 决策 → 下单 → 开盘撮合」，与回测引擎逐笔一致（真实的立花适配器 + 模拟交易所也一致）；
② 真实下单的情形：卖单没成交（ストップ安）→ 顺延重下；买单没成交 → 作废；部分成交；
③ 安全闸：HALT、持仓不一致、状态不明的单、时间窗口；同一个早上重跑不重复下单；现金以券商为准。"""
import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from qbreak import paths
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST
from qbreak.config import StrategyParams
from qbreak.fees import etf_cost
from qbreak.live_unified import ExecOrder, ExecutorError, UnifiedExecutor, _np, rehearse, resolve_order
from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs

from test_plan_alignment import _synthetic

P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0,
                   stop_loss_pct=7.0)
EX = exec_configs(("JP",), {"broker": "tachibana"})
CC = {"1655.T": etf_cost("tachibana", "1655.T", "JP")}
CFG = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                    stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"})
NEW = "CLMKabuNewOrder"


def _maker(ind, bear):
    return lambda: UnifiedEngine(ind, CFG, {"JP": P, "US": P}, EX, CC, bear={"US": bear})


def _synth(seed):
    ind, core_df, bear = _synthetic("JP", seed=seed, n=260)
    return _maker({**ind, "1655.T": core_df}, pd.Series(bear, index=core_df.index)), core_df.index[60]


def _frame(close, opens=None, entry=(), dead=(), lock=(), start="2026-01-05"):
    """手工 K 线：lock 里的日子一整天张贴在当天的价（高 = 低 = 收 = 开）。"""
    idx = pd.bdate_range(start, periods=len(close))
    c = np.asarray(close, float)
    o = np.asarray(opens if opens is not None else close, float)
    h, lo = np.maximum(o, c) * 1.004, np.minimum(o, c) * 0.996
    for i in lock:
        h[i] = lo[i] = o[i] = c[i]
    df = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1e6}, index=idx)
    df["entry"], df["dead_cross"] = df.index.isin(idx[list(entry)]), df.index.isin(idx[list(dead)])
    df["atr"], df["climax"] = c * 0.02, False
    return df


def _scenario(a_close, a_open=None, entry=(10,), dead=(), lock=(), bear_all=False, n=30):
    a = _frame(a_close, a_open, entry=entry, dead=dead, lock=lock)
    b = _frame([1500.0] * n)
    core = _frame([700.0] * n)
    core["entry"] = False
    bear = pd.Series(bool(bear_all), index=core.index)
    return _maker({"A.T": a, "B.T": b, "1655.T": core}, bear), core.index[5]


def _split_fees(r) -> float:
    """核心买单拆成「寄付 + 开盘后余数」时多付的手续费（每拆一次多一笔；这里的金额档都是 77 円）+ 浮点余量。"""
    n = sum(1 for h in r["ux"].book["history"] for o in h["orders"] if o["cid"].endswith("-2") and o["filled_qty"] > 0)
    return 77.0 * n + 1e-6


# ────────── ① 与回测引擎逐笔一致 ──────────
@pytest.mark.parametrize("seed", [7, 11, 23])
def test_paper_account_equals_engine_exactly(seed):
    make, start = _synth(seed)
    r = rehearse(make, start, kind="paper")
    assert r["max_abs_diff"] == 0.0 and r["same_trades"] and r["same_core"] and not r["errors"]
    assert r["stats"]["deferred"] > 0                      # 两段式买入（开盘前余力不够 → 开盘后）确实走到了


@pytest.mark.parametrize("seed", [7, 23])
def test_real_tachibana_adapter_on_sim_exchange_equals_engine(seed):
    """真实的立花适配器（发单字段、約定照会、持仓、余力）+ 模拟交易所：约束不起作用的数据上与引擎逐笔一致。"""
    make, start = _synth(seed)
    r = rehearse(make, start, kind="tachibana-sim")
    assert r["max_abs_diff"] < 1.0 and r["same_trades"] and r["same_core"] and not r["errors"]
    assert r["calls"][NEW] > 10 and r["calls"]["CLMOrderListDetail"] > 10


def test_split_core_buy_costs_only_the_extra_commission():
    """核心 ETF 买单开盘前余力只放得下一部分：先下寄付，余数开盘后再下 —— 与模型的差只是多一笔手续费（77 円）。"""
    make, start = _synth(11)
    r = rehearse(make, start, kind="tachibana-sim")
    assert r["same_trades"] and -200 < r["final_diff"] <= 0
    hist = [o for h in r["ux"].book["history"] for o in h["orders"]]
    assert any(o["cid"].endswith("-2") and o["kind"] == "core" for o in hist)


# ────────── ② 真实下单的情形 ──────────
def test_unfilled_sell_on_limit_down_is_carried_and_replaced():
    n = 30
    a = [1000.0] * 20 + [700.0] * (n - 20)                    # 第 20 天一整天ストップ安（1000 → 700）
    make, start = _scenario(a, entry=(10,), dead=(19,), lock=(20,))
    r = rehearse(make, start, kind="tachibana-sim")
    assert r["same_trades"] and r["max_abs_diff"] <= _split_fees(r)   # 引擎同样：张贴那天卖不掉，第二天开盘卖出
    assert r["stats"]["unfilled_sell"] == 1
    sells = [o for h in r["ux"].book["history"] for o in h["orders"] if o["ticker"] == "A.T" and o["side"] == "SELL"]
    assert [o["status"] for o in sells] == ["UNFILLED", "FILLED"]
    t = r["executor"].trades
    assert list(t[t["reason"] != "end"]["ticker"]) == ["A.T"]


def test_unfilled_opening_buy_is_dropped_not_retried():
    """寄付指値（信号日收盘 ×1.03）够不着：作废，不追（模型的跳空过滤同样放弃）。"""
    n = 30
    a = [1000.0] * n
    op = list(a)
    op[11] = 1050.0                                           # 第 11 天开盘 +5%
    make, start = _scenario(a, op, entry=(10,), bear_all=True)   # 熊市：核心为 0，现金够 → 开盘前就下寄付指値
    r = rehearse(make, start, kind="tachibana-sim")
    assert r["same_trades"] and r["max_abs_diff"] <= _split_fees(r)
    buys = [o for h in r["ux"].book["history"] for o in h["orders"] if o["ticker"] == "A.T"]
    assert len(buys) == 1 and buys[0]["status"] == "UNFILLED" and buys[0]["phase"] == "morning"
    assert r["stats"]["model_diff"] == 0 and len(r["executor"].trades) == 0


class _HalfSell(SimExchange):
    """第一次卖 A.T 只成交一半（比例配分）。"""
    done = False

    def _fill(self, o, op):
        if o["side"] == "SELL" and o["ticker"] == "A.T" and not self.done:
            self.done = True
            o["qty"] = int(o["qty"]) // 2
        super()._fill(o, op)


def test_partial_sell_keeps_the_rest_pending_and_resells():
    n = 30
    make, start = _scenario([1000.0] * n, entry=(10,), dead=(15,))
    r = rehearse(make, start, kind="tachibana-sim", exchange_cls=_HalfSell)
    sells = [o for h in r["ux"].book["history"] for o in h["orders"] if o["ticker"] == "A.T" and o["side"] == "SELL"]
    assert [o["status"] for o in sells] == ["PARTIAL", "FILLED"]
    assert sells[1]["qty"] == sells[0]["qty"] - sells[0]["filled_qty"]
    assert "A.T" not in r["ux"].eng.st.pos and not r["errors"] and not r["ux"].blocked
    assert list(r["executor"].trades["reason"]) == ["dead_cross（部分成交）", "dead_cross"]


# ────────── ③ 安全闸与幂等 ──────────
def test_rerun_same_morning_sends_nothing_new(tmp_path):
    make, start = _synth(7)
    r = rehearse(make, start, kind="tachibana-sim", workdir=tmp_path)
    ux, exch = r["ux"], r["exchange"]
    n0 = exch.calls[NEW]
    ux.morning([])                                            # 同一个早上再跑一次（没有新交易日）
    ux2 = UnifiedExecutor(ux.eng, ux.b, r["book"], paper=False, respect_halt=False, check_clock=False)
    ux2.morning([])                                           # 进程重启后从账本读回
    assert exch.calls[NEW] == n0


def test_halt_blocks_orders_and_rerun_after_removal_sends_them():
    make, start = _scenario([1000.0] * 30, entry=(10,), bear_all=True)
    eng = make()
    exch = SimExchange(eng, cash=eng.st.cash_jpy)
    from qbreak.brokers.tachibana import TachibanaBroker
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book.json", paper=False, check_clock=False)
    lo = int(eng.gidx.searchsorted(start))
    eng.prime(lo)
    for k in range(lo, 11):
        exch.open(k)
        ux.open_phase()
        exch.close_day()
        exch.set_day(k + 1)
        if k == 10:
            paths.halt_file().write_text("stop", encoding="utf-8")
        ux.run_bar(k)
    o = [x for x in ux.orders if x.ticker == "A.T"][0]
    assert o.status == "BLOCKED" and "HALT" in o.note and exch.calls.get(NEW, 0) == 0
    paths.halt_file().unlink()
    ux.blocked = None
    ux.morning([])
    assert o.status == "SENT" and exch.calls[NEW] == 1


def test_holdings_mismatch_blocks_orders():
    make, start = _synth(7)
    seen = {}

    def tamper(k, ux, exch):
        if not seen and ux.eng.st.core_units.get("1655.T"):
            exch.pos["C.T"] = 100                             # 券商那边多出一只执行器管的票（人工买的？）
            seen["k"] = k
    r = rehearse(make, start, kind="tachibana-sim", before_bar=tamper)
    ux = r["ux"]
    assert "持仓与券商不一致" in (ux.blocked or "") and "C.T" in ux.blocked
    assert all(o.status == "BLOCKED" for o in ux.orders if o.decided_on == ux.eng.st.last_date and o.status != "DEFERRED")


class _NetDown(SimExchange):
    """指定时刻起，下一笔新规注文遇到网络错误（服务器那边没收到）。"""
    fail = False

    def get_json(self, url, payload):
        if self.fail and payload.get(self.spec.f_clmid) == NEW:
            self.fail = False
            raise ConnectionError("回线断了")
        return super().get_json(url, payload)


def test_unknown_order_stops_next_morning_until_resolved():
    make, start = _scenario([1000.0] * 30, entry=(10,), bear_all=True)
    eng = make()
    exch = _NetDown(eng, cash=eng.st.cash_jpy)
    from qbreak.brokers.tachibana import TachibanaBroker
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    book = paths.state_dir() / "book.json"
    ux = UnifiedExecutor(eng, b, book, paper=False, check_clock=False)
    lo = int(eng.gidx.searchsorted(start))
    eng.prime(lo)

    def day(k, x):
        exch.open(k)
        x.open_phase()
        exch.close_day()
        exch.set_day(k + 1)
        x.run_bar(k)
    for k in range(lo, 10):
        day(k, ux)
    exch.fail = True
    day(10, ux)                                               # 第 10 天收盘后下 A.T 的买单 → 网络错误
    o = [x for x in ux.orders if x.ticker == "A.T"][0]
    assert o.status == "ERROR" and "状态不明" in o.note
    with pytest.raises(ExecutorError, match="状态不明"):
        day(11, ux)                                           # 第二天早上：不猜，停下
    resolve_order(book, o.cid, 0, 0.0)                        # 人工在注文一覧确认：没受理
    ux2 = UnifiedExecutor(eng, b, book, paper=False, check_clock=False)
    ux2.run_bar(11)
    assert eng.st.last_date == str(eng.gidx[11].date()) and "A.T" not in eng.st.pos


def test_cash_drift_is_synced_to_broker_and_logged():
    make, start = _synth(7)
    hit = {}

    def tax(k, ux, exch):
        if not hit and k > 100:
            exch.cash -= 1234.0                                  # 例如源泉徴収された譲渡益税
            hit["k"] = k
    r = rehearse(make, start, kind="tachibana-sim", before_bar=tax)
    ux, exch = r["ux"], r["exchange"]
    assert ux.stats["cash_sync"] == 1
    assert any("现金差 -1,234 円" in e["msg"] for e in ux.book["events"])
    assert abs(ux.eng.st.cash_jpy - exch.cash) < 1e-6


def test_time_windows():
    make, _ = _synth(7)
    eng = make()
    eng.st.last_date = "2026-09-25"                           # 周五收盘后的决策 → 成交日 9/28（周一）
    now = {"t": None}
    ux = UnifiedExecutor(eng, None, paths.state_dir() / "b.json", paper=False, clock=lambda: now["t"])

    def at(d, hh, mm=0):
        now["t"] = dt.datetime(2026, 9, d, hh, mm, tzinfo=JST)
    at(26, 10)
    assert ux._gate("morning") is None                        # 周六：给周一的寄付单
    at(28, 8, 50)
    assert ux._gate("morning") is None and "09:00" in ux._gate("open")
    at(28, 9, 0)
    assert "寄付注文来不及" in ux._gate("morning") and ux._gate("open") is None
    at(28, 15, 30)
    assert ux._gate("open")
    at(29, 9, 5)
    assert "不是成交日" in ux._gate("open")
    paths.halt_file().write_text("x", encoding="utf-8")
    at(28, 8, 0)
    assert "HALT" in ux._gate("morning")


def test_fit_limit_stays_on_tick_grid_and_within_buying_power():
    make, _ = _synth(7)
    eng = make()
    ux = UnifiedExecutor(eng, None, paths.state_dir() / "b.json", paper=False, check_clock=False)
    o = ExecOrder("c", "A.T", "BUY", "stock", 100, "2026-01-01", limit=1030.0, ref_px=1000.0)
    fee = eng.fees["JP"]
    bp = 100 * 1012 + fee(100 * 1012)
    lim = ux._fit_limit(o, 100, bp)
    assert lim == 1012.0 and ux._reserve(o, 100, lim) <= bp
    assert ux._fit_limit(o, 100, 10_000_000) == 1030.0
    assert ux._fit_qty(o, 100 * 1030 + fee(100 * 1030) - 1) == 0


def test_book_json_keeps_numpy_ints_as_ints(tmp_path):
    fp = tmp_path / "x.json"
    fp.write_text(json.dumps({"q": np.int64(300), "p": np.float64(1.5)}, default=_np), encoding="utf-8")
    d = json.loads(fp.read_text(encoding="utf-8"))
    assert d == {"q": 300, "p": 1.5} and isinstance(d["q"], int)


def test_executor_refuses_us_stocks():
    make, _ = _synth(7)
    eng = make()
    eng.cfg = UnifiedConfig(stock_markets=("JP", "US"), core={"1655.T": 1.0})
    with pytest.raises(ValueError, match="美股"):
        UnifiedExecutor(eng, None, paths.state_dir() / "b.json")


def test_missed_open_phase_is_flagged_as_divergence():
    """09:05 的开盘后补单没有跑：第二天对账时这些买单记为 MISSED 并报警（与模拟盘出现差异），不会静默消失。"""
    make, start = _scenario([1000.0] * 30, entry=())          # 1655 = 700 円：100 万全买 1420 口，限价 ×1.02 预留放不下 → 余数留到开盘后
    eng = make()
    exch = SimExchange(eng, cash=eng.st.cash_jpy)
    from qbreak.brokers.tachibana import TachibanaBroker
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book.json", paper=False, respect_halt=False, check_clock=False)
    lo = int(eng.gidx.searchsorted(start))
    eng.prime(lo)
    for k in range(lo, lo + 3):                               # 这里不跑开盘后那段（ux.open_phase）
        exch.open(k)
        exch.close_day()
        exch.set_day(k + 1)
        ux.run_bar(k)
    missed = [o for h in ux.book["history"] for o in h["orders"] if o["status"] == "MISSED"]
    assert missed and ux.stats["model_diff"] >= 1
    assert any("开盘后补单没有运行" in e["msg"] for e in ux.book["events"] + ux.events)


# ────────── Mac 模拟操盘：与云端模拟盘比较、汇报文字 ──────────
def test_compare_with_sim_only_on_same_day_and_names_differences():
    from qbreak.live_unified import compare_with_sim
    from qbreak.unified import UPos, UState
    a = UState(cash_jpy=100.0, last_date="2026-09-29", history=[["2026-09-29", 1000.0, 100.0, 0.0, 150.0]])
    b = UState(cash_jpy=100.0, last_date="2026-09-28", history=[["2026-09-28", 1000.0, 100.0, 0.0, 150.0]])
    r = compare_with_sim(a, b)
    assert r["comparable"] is False and "不是同一天" in r["text"]
    assert compare_with_sim(a, None)["comparable"] is False
    b.last_date = "2026-09-29"
    assert compare_with_sim(a, b)["same"] is True
    a.pos["7203.T"] = UPos("7203.T", "JP", 100, 3000.0, "2026-09-29", 2800.0, 3000.0, 3000.0)
    a.history[-1][1] = 1300.0
    r = compare_with_sim(a, b)
    assert r["same"] is False and "7203.T" in r["text"] and "权益差 +300 円" in r["text"]


def test_daily_text_has_units_and_flags():
    from qbreak.live_unified import daily_text
    from qbreak.unified import UState
    st = UState(cash_jpy=5000.0, last_date="2026-09-29", core_units={"1655.T": 1100},
                history=[["2026-09-28", 1_000_000.0, 0, 0, 150], ["2026-09-29", 1_003_000.0, 0, 0, 150]])
    sm = {"decided_on": "2026-09-29", "fill_day": "2026-09-30", "equity_jpy": 1_003_000, "blocked": None, "events": [],
          "reconciled": [{"bar": "2026-09-29", "side": "BUY", "ticker": "1655.T", "qty": 1100, "px": 880.5, "kind": "core"}],
          "orders": [{"side": "BUY", "ticker": "7203.T", "kind": "stock", "qty": 100, "sent_qty": 0, "limit": 3090.0,
                      "phase": "open", "status": "DEFERRED", "note": ""}]}
    title, short, body = daily_text(sm, st, {"comparable": True, "same": True, "text": "与云端模拟盘一致"}, True, 1_000_000)
    assert "模拟操盘" in title and "权益 ¥1,003,000（当日 +3,000 円，累计 +0.30%）" in short and "与云端一致" in short
    assert "1655.T 1,100 口" in body and "@ ¥880.50" in body and "7203.T 100 股（开盘后指値 ≤ ¥3,090）" in body


def test_demo_order_test_runs_the_whole_order_cycle(capsys):
    """tachibana-probe --demo --order-test 的流程（这里对着模拟交易所）：指値买 → 約定照会字段 → 余力 / 持仓变化 → 寄付卖 → 撤单。"""
    import run
    from qbreak.brokers.tachibana import TachibanaBroker
    make, _ = _scenario([1000.0] * 30)
    eng = make()
    exch = SimExchange(eng, cash=1_000_000)
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), dry_run=True, require_arm=True,
                        confirm_timeout_s=0.0)
    exch.set_day(10)
    exch.open(10)                                             # デモ的约定时间内
    assert run._tachibana_order_test(b, exch.spec) is True
    out = capsys.readouterr().out
    assert "約定照会的字段" in out and "sYakuzyouSuryou" in out and "已撤" in out
    assert exch.pos.get("1655.T") == 10 and [o["status"] for o in exch.orders.values()] == ["10", "7"]


# ────────── ④ Mac 上的页面（账本 + 日志）──────────
def test_desktop_page_before_start_links_the_trial_page():
    from qbreak import desktop_page
    html = desktop_page.render("paper", 1_000_000, "2026-09-28")
    assert "还没有开始" in html and "2026-09-28" in html and "trial_page.html" not in html
    (paths.out_dir() / "trial_page.html").write_text("x", encoding="utf-8")
    html = desktop_page.render("paper", 1_000_000, "2026-09-28", alert="运行没有完成（退出码 1）", note="这是试跑")
    assert "href='trial_page.html'" in html and "★ 运行没有完成（退出码 1）" in html and "这是试跑" in html
    assert "id='stale'" in html and "getUTCDay" in html and "非投资建议" in html
    assert desktop_page.default_path("paper") == paths.out_dir() / "page_paper.html"


def test_desktop_page_shows_book_orders_fills_market_and_journal(tmp_path):
    from qbreak import desktop_page
    from qbreak.live_unified import append_journal
    make, start = _synth(7)
    r = rehearse(make, start, kind="paper", workdir=tmp_path)
    book = json.loads(open(r["book"], encoding="utf-8").read())
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    st = book["state"]
    mk = {"JP": {"state": "bull", "since": "2025-05-01", "days": 330, "asof": "2026-09-24", "phase_label": "牛市·稳固",
                 "phase_text": "比 250 日均线高 15.3%", "flip_line": 40123.45},
          "US": {"state": "bear", "since": "2026-08-01", "days": 40, "asof": "2026-09-24", "phase_label": "熊市·回升（在往牛的方向走）",
                 "phase_text": "比 250 日均线低 2.0%", "flip_line": 6000.0}}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(
        {"fill_day": "2026-09-29", "blocked": None, "market": mk,
         "compare": {"comparable": True, "same": False, "text": "★ 与云端模拟盘不一致"}}, ensure_ascii=False), encoding="utf-8")
    jp = paths.out_dir() / "live_unified_paper_journal.md"
    for d in ("09-28", "09-29"):
        append_journal(jp, f"2026-{d} 07:45 JST", f"qbreak 模拟操盘 2026-{d}", f"- 决策日 2026-{d}\n- 下一开盘：没有单")
    p = desktop_page.write(desktop_page.default_path("paper"), "paper", 1_000_000, "2026-09-28")
    html = p.read_text(encoding="utf-8")
    eq = float(st["history"][-1][1])
    assert f"¥{eq:,.0f}" in html and "起始 ¥1,000,000" in html and "★ 与云端模拟盘不一致" in html
    assert "牛市·稳固" in html and "熊市·回升" in html and "40,123.45 円" in html and "6,000.00 pt" in html
    assert "<h2>持仓</h2>" in html and "<h2>下一开盘的单</h2>" in html and "<h2>最近成交</h2>" in html
    fills = [o for h in book["history"] for o in h["orders"] if o["filled_qty"] > 0]
    assert fills and ("口</td>" in html or "股</td>" in html)
    assert html.index("2026-09-29 07:45 JST") < html.index("2026-09-28 07:45 JST")      # 日志：新的在上
    for t, u in (st.get("core_units") or {}).items():
        if int(u):
            assert f"{int(u):,} 口" in html


def test_desktop_link_is_a_symlink_and_never_replaces_a_real_file(tmp_path):
    from qbreak import desktop_page
    desk = tmp_path / "Desktop"
    lk = desktop_page.link("paper", desk)
    assert lk.name == "qbreak模拟操盘.html" and lk.is_symlink() and lk.resolve() == desktop_page.default_path("paper").resolve()
    assert desktop_page.link("paper", desk) == lk                          # 重建：替换旧链接
    real = desk / desktop_page.desktop_name("tachibana")
    real.write_text("mine", encoding="utf-8")
    with pytest.raises(FileExistsError):
        desktop_page.link("tachibana", desk)
    assert real.read_text(encoding="utf-8") == "mine"


def test_daily_text_shows_bull_bear_phase():
    from qbreak.live_unified import daily_text
    from qbreak.unified import UState
    st = UState(cash_jpy=1_000_000.0, last_date="2026-09-29", history=[["2026-09-29", 1_000_000.0, 0, 0, 150]])
    sm = {"decided_on": "2026-09-29", "orders": [], "events": [], "blocked": None,
          "market": {"JP": {"state": "bull", "phase_label": "牛市·稳固", "phase_text": "比 250 日均线高 15.3%"},
                     "US": {"state": "unknown"}}}
    _, _, body = daily_text(sm, st, None, True, 1_000_000)
    assert "- 牛熊（日経平均）：牛市·稳固：比 250 日均线高 15.3%" in body and "S&P500" not in body
