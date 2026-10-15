"""模拟账户当天的开盘撮合（D3；2026-10-15）：成交日 09:25 前后面板叫 --phase open → 按 Yahoo 1 分钟线今天第一根的开盘价撮合排队的寄付单，
再按撮合之后的实际现金下等开盘后的买单（与立花 09:05 同一条路，HALT 等闸门同口径）；第二天早上不再撮合（幂等），只在正式日线开盘价
不同时按它改记（与云端模拟盘一致）；面板不在 / 没叫成 → 第二天早上照旧撮合（后备）。
事故重放（2026-10-15）：撤了凑钱的 1545 卖单之后，1482 的「等开盘后」买单当天就变成「不下」+ 原因 + ★ 交易 推送（以前第二天早上才被拒、不推送）。"""
import datetime as dt
import json
import shutil
from types import SimpleNamespace

import pandas as pd
import pytest

from qbreak import live_ops as LO
from qbreak import panel, paths
from qbreak.brokers.paper import PaperBroker
from qbreak.calendar_jp import JST
from qbreak.live_unified import HALT_WAIT, PAPER_OPEN_WAIT, paper_open_due

from test_core_etf_restore import _morning, _paper2
from test_fund_src import _cur, _fixed_case, _low_cash, _one
from test_manual_now import _at
from test_shell_scripts import _bash, _calls, _run_env


def _feed(r, mult: float | dict = 1.0, drop=(), calls=None):
    """假的 1 分钟线：今天（成交日 = 下一根 K 线）的开盘 = 日线开盘 × mult；drop 里的票还没有分钟线。"""
    eng = r.eng

    def feed(ts, now):
        if calls is not None:
            calls.append((sorted(ts), now))
        out = {}
        for t in ts:
            if t in drop:
                continue
            m = mult.get(t, 1.0) if isinstance(mult, dict) else mult
            op = round(float(eng.A.open[r.k, eng.col[t]]) * m, 1)
            out[t] = {"open": op, "high": op * 1.01, "low": op * 0.99, "first": "09:00", "last": "09:06"}
        return out
    return feed


def _f_orders(r) -> list:
    return [o for o in r.b.state["orders"] if o.get("status") == "FILLED"]


def _snap(r) -> dict:
    st = r.eng.st
    return {"units": {t: int(u) for t, u in st.core_units.items()}, "cash": round(st.cash_jpy, 2), "bcash": round(r.b.cash(), 2),
            "pos": {t: int(p["qty"]) for t, p in r.b.state["positions"].items()},
            "avg": {t: round(float(p["avg_px"]), 4) for t, p in r.b.state["positions"].items()},
            "hist": [o["status"] for h in r.ux.book.get("history") or [] for o in h["orders"]]}


# ══════════════════════════ 09:25 撮合 → 第二天早上幂等，与后备路径（第二天早上撮合）结果相同 ══════════════════════════
def test_settle_at_0925_fills_today_and_next_morning_is_idempotent_and_matches_fallback():
    r = _paper2()
    sell, buy = _fixed_case(r)
    assert sell.note == "已排队：今天 09:25 前后按开盘价撮合"                     # 以前「已排队，次日开盘成交」
    assert buy.status == "DEFERRED" and "今天 09:25 前后按开盘价撮合" in buy.note
    f = r.ux.fill_day()
    assert not paper_open_due(r.ux.book, _at(r, 9, 24)) and paper_open_due(r.ux.book, _at(r, 9, 25))
    r.now["t"] = _at(r, 9, 25)
    res = r.ux.open_phase(feed=_feed(r))
    assert res["done"] and not res["wait"]
    assert sell.status == "FILLED" and sell.filled_qty == 970 and sell.note.startswith(f"{f:%m/%d} 开盘撮合 970 口 @ ¥699.79")
    assert buy.status == "FILLED" and buy.filled_qty == 677 and buy.sent_qty == 678       # 现金按开盘价减了 1 口（与模型相同）
    fo = _f_orders(r)
    assert [(o["client_id"], (o.get("extra") or {}).get("fill_date")) for o in fo if o["client_id"] == sell.cid + "-f"] == [(sell.cid + "-f", f.isoformat())]
    po = r.ux.book["paper_open"]
    assert po["at"].startswith(f.isoformat()) and set(po["fills"]) == {sell.cid, buy.cid} and po["deferred_at"]
    assert not paper_open_due(r.ux.book, _at(r, 9, 31))                         # 一天一次
    assert r.ux.open_phase(feed=_feed(r))["why"].startswith("今天的开盘撮合已经做过")
    saved = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    assert {o["cid"]: o["status"] for o in saved["orders"] if o["cid"] in (sell.cid, buy.cid)} == {sell.cid: "FILLED", buy.cid: "FILLED"}
    n0 = len(r.b.state["orders"])
    _morning(r)                                                                   # 第二天早上：不再撮合，只对账
    assert len([o for o in r.b.state["orders"][:n0 + 2] if o["client_id"] in (sell.cid + "-f", buy.cid)]) == 2   # 没有第二次成交
    assert "paper_open" not in r.ux.book
    r2 = _paper2("p2")                                                            # 后备：面板没叫，第二天早上照旧撮合
    _fixed_case(r2)
    _morning(r2)
    a, b = _snap(r), _snap(r2)
    assert a == b, (a, b)
    assert a["units"]["1482.T"] == 677 and "PARTIAL" in a["hist"]                 # 减了股：对账照旧记成部分成交


def test_missing_minute_feed_waits_then_next_morning_falls_back():
    r = _paper2()
    sell, buy = _fixed_case(r)
    r.now["t"] = _at(r, 9, 25)
    calls = []
    res = r.ux.open_phase(feed=_feed(r, drop={"1482.T"}, calls=calls))          # 1482 还没有今天的分钟线：整批不做
    assert not res["done"] and res["wait"] and PAPER_OPEN_WAIT in res["why"] and "1482 对冲美债" in res["why"]
    assert calls and calls[0][0] == ["1482.T", "1545.T"]
    assert sell.status == "SENT" and buy.status == "DEFERRED" and r.b.pending()   # 什么都没动
    assert r.ux.book["paper_open"]["tries"] == 1 and paper_open_due(r.ux.book, _at(r, 9, 30))
    r.now["t"] = _at(r, 9, 30)
    assert r.ux.open_phase(feed=lambda ts, now: (_ for _ in ()).throw(OSError("yahoo down")))["wait"]   # 取价出错：也是下一轮再试
    assert r.ux.book["paper_open"]["tries"] == 2
    assert not paper_open_due(r.ux.book, _at(r, 11, 30))                         # 到 11:30 还没有 → 留给第二天早上
    r.now["t"] = _at(r, 11, 30)
    assert "09:25〜11:30" in r.ux.open_phase(feed=_feed(r))["why"] and sell.status == "SENT"
    _morning(r)
    r2 = _paper2("p2")
    _fixed_case(r2)
    _morning(r2)
    assert _snap(r) == _snap(r2)


def test_reprice_next_morning_to_the_official_daily_open():
    """1 分钟线的开盘与第二天日线的正式开盘不同 → 第二天早上按正式开盘价改记（股数不变；现金 / 成本 / 已实现盈亏跟着改）→ 与后备路径相同。"""
    r = _paper2()
    sell, buy = _fixed_case(r)
    _low_cash(r, 900_000.0)                                                       # 现金够：股数不受开盘价影响
    r.now["t"] = _at(r, 9, 25)
    res = r.ux.open_phase(feed=_feed(r, {"1545.T": 1.01, "1482.T": 0.99}))
    assert res["done"] and sell.filled_px == pytest.approx(707.0 * (1 - 0.0003)) and buy.filled_px == pytest.approx(990.0 * 1.0005)
    assert buy.filled_qty == 678
    _morning(r)
    ev = [e["msg"] for e in r.ux.book["events"] if "按正式日线开盘价改记" in e["msg"]]
    assert ev and "卖 1545 纳斯达克 100：970 口" in ev[0] and "开盘 ¥707→¥700" in ev[0]
    rec = [o for o in r.b.state["orders"] if o["client_id"] == buy.cid][-1]
    assert rec["filled_px"] == pytest.approx(1000.0 * 1.0005) and rec["extra"]["repriced"]["open"] == 1000.0
    r2 = _paper2("p2")
    _fixed_case(r2)
    _low_cash(r2, 900_000.0)
    _morning(r2)
    a, b = _snap(r), _snap(r2)
    assert a["units"] == b["units"] and a["pos"] == b["pos"] and a["avg"] == b["avg"]
    assert a["cash"] == pytest.approx(b["cash"], abs=0.01) and a["bcash"] == pytest.approx(b["bcash"], abs=0.01)
    assert r.b.state["core_trades"][-1]["exit_px"] == r2.b.state["core_trades"][-1]["exit_px"]


def test_halt_at_settle_fills_the_queued_orders_but_not_the_deferred_buy():
    """HALT（与立花 09:05 同口径）：排队的寄付单 09:00 已经在「交易所」撮合 → 照记；等开盘后的买单这次不下（单保留、说明写原因），
    11:30 之前解除后可以手动再跑；不跑 → 第二天早上对账记为没买（MISSED，原因是 HALT）。"""
    r = _paper2()
    sell, buy = _fixed_case(r)
    paths.halt_file().write_text("测试", encoding="utf-8")
    try:
        assert paper_open_due(r.ux.book, _at(r, 9, 25))                         # HALT 不挡开盘撮合
        r.now["t"] = _at(r, 9, 25)
        res = r.ux.open_phase(feed=_feed(r))
        assert res["done"] and sell.status == "FILLED" and buy.status == "DEFERRED"
        assert buy.note.startswith(f"{HALT_WAIT}（存在 HALT 文件") and res["deferred_why"].startswith("存在 HALT 文件")
        assert not paper_open_due(r.ux.book, _at(r, 9, 31)) and paper_open_due(r.ux.book, _at(r, 9, 31), rerun=True)
        lv = panel._trade_live(r.ux.book, [], _at(r, 9, 31), "paper", halt=True)
        assert lv["orders"][buy.cid][0] == "不会下单（HALT）" and "开盘撮合时 HALT 生效中" in lv["orders"][buy.cid][1]
    finally:
        paths.halt_file().unlink()
    _morning(r)
    h = {o["cid"]: o for o in r.ux.book["history"][-1]["orders"]}
    assert h[buy.cid]["status"] == "MISSED" and h[buy.cid]["note"].startswith(f"{HALT_WAIT}（存在 HALT 文件")
    assert h[sell.cid]["status"] == "FILLED" and int(r.eng.st.core_units.get("1482.T") or 0) == 0


def test_halt_removed_before_1130_then_a_manual_rerun_places_the_deferred_buy():
    r = _paper2()
    sell, buy = _fixed_case(r)
    paths.halt_file().write_text("测试", encoding="utf-8")
    r.now["t"] = _at(r, 9, 25)
    r.ux.open_phase(feed=_feed(r))
    paths.halt_file().unlink()
    r.now["t"] = _at(r, 10, 0)
    res = r.ux.open_phase(feed=_feed(r))
    assert res["done"] and buy.status == "FILLED" and buy.filled_qty == 677 and "deferred_why" not in r.ux.book["paper_open"]
    assert len([o for o in r.b.state["orders"] if o["client_id"] == sell.cid + "-f"]) == 1   # 寄付单不再撮合一次


# ══════════════════════════ 事故重放：撤了凑钱的卖单（旧账本没有 fund_src）→ 买单当天「不下」+ 原因 + ★ 交易 ══════════════════════════
def test_incident_replay_buy_after_cancelled_funding_sell_is_skipped_with_reason_and_pushed():
    r = _paper2()
    sell, buy = _fixed_case(r)
    buy.fund_src = []                                                             # 2026-10-15 的账本：还没有 fund_src（撤单不级联）
    r.now["t"] = _at(r, 8, 5)
    r.ux.cancel_orders([sell.cid], source="面板的撤单指令")
    assert sell.status == "CANCELLED" and buy.status == "DEFERRED" and not r.ux.trade_warns
    r.now["t"] = _at(r, 9, 25)
    res = r.ux.open_phase(feed=_feed(r))
    assert res["done"] and buy.status == "SKIPPED"
    assert buy.note.startswith("凑钱的卖单 卖 1545 纳斯达克 100：970 口 已撤（08:05） → 钱没来：现金 192 円按开盘价 ¥1,000 买不起 1 单元")
    assert r.ux.trade_warns == [f"★ 交易：买 1482 对冲版美国 7〜10 年国债（开盘后）放弃：{buy.note}"]
    assert any(e["level"] == "warn" and "钱没来" in e["msg"] for e in r.ux.book["events"])
    seen = list(r.ux.orders)
    _morning(r)
    assert not [o for o in seen if o.status == "REJECTED"] and not [o for o in r.b.state["orders"] if o["status"] == "REJECTED"]


def test_trade_warn_is_pushed_by_the_open_run(monkeypatch):
    """run.py：--phase open 的运行之后 trade_warns 照样单独推一条 ★ 交易（与 07:40 / 撤单同一个函数）。"""
    import run
    sent = []
    monkeypatch.setattr("qbreak.notify.send", lambda title, body, level="info": sent.append((title, body, level)) or True)
    run._trade_warn_push(["★ 交易：买 1482.T（开盘后）放弃：钱没来"], True)
    assert sent and sent[0][2] == "warn" and "1482 对冲版美国" in sent[0][1]


# ══════════════════════════ 今天不做 / 等一轮 ══════════════════════════
def test_open_outside_the_price_band_or_a_corporate_action_stops_for_today():
    r = _paper2()
    sell, buy = _fixed_case(r)
    r.now["t"] = _at(r, 9, 25)
    res = r.ux.open_phase(feed=_feed(r, {"1545.T": 0.5}))                        # 700 → 350：超出制限値幅（拆股？）
    assert not res["done"] and "超出制限値幅" in res["why"] and r.ux.book["paper_open"]["stop"]
    assert not paper_open_due(r.ux.book, _at(r, 9, 31)) and sell.status == "SENT"
    r = _paper2("p2")
    sell, buy = _fixed_case(r)
    d, f = r.eng.st.last_date, r.ux.fill_day().isoformat()
    corp = SimpleNamespace(actions=lambda t: [{"date": f, "dividend": 5.0, "split": 0.0}] if t == "1545.T" else [])
    r.now["t"] = _at(r, 9, 25)
    res = r.ux.open_phase(feed=_feed(r), corp=corp)
    assert not res["done"] and "今天有公司行为" in res["why"] and "1545 纳斯达克" in res["why"] and d < f


def test_stock_near_the_limit_without_trading_away_waits():
    """个股开在涨跌停附近、到现在价格没动（可能一整天张贴：日线才判断得了）→ 等下一轮，到 11:30 → 第二天早上按日线撮合。"""
    r = _paper2()
    sell, buy = _fixed_case(r)
    eng = r.eng

    def feed(ts, now):
        out = _feed(r)(ts, now)
        prev = float(eng.A.close[r.k - 1, eng.col["1545.T"]])
        out["1545.T"] = {"open": prev + 100, "high": prev + 100, "low": prev + 100, "first": "09:00"}
        return out
    r.now["t"] = _at(r, 9, 25)
    assert r.ux.open_phase(feed=feed)["done"]                                    # 核心 ETF 不看张贴（与 PaperBroker 相同）
    # 个股：A.T 的开盘在涨停价（前日收盘 1,000 円 → 制限値幅 300 円）、到现在没动
    from qbreak.live_unified import ExecOrder
    r = _paper2("p3")
    sell, buy = _fixed_case(r)
    a = ExecOrder(cid="U-x-BUY-A.T", ticker="A.T", side="BUY", kind="stock", qty=100, decided_on=r.eng.st.last_date, limit=1030.0,
                  ref_px=1000.0, reason="entry", phase="open", status="DEFERRED")
    r.ux.orders.append(a)

    def feed2(ts, now):
        out = _feed(r)(ts, now)
        out["A.T"] = {"open": 1300.0, "high": 1300.0, "low": 1300.0, "first": "09:00"}
        return out
    r.now["t"] = _at(r, 9, 25)
    res = r.ux.open_phase(feed=feed2)
    assert res["wait"] and not res["done"] and res["why"].startswith("A 开在涨跌停附近") and paper_open_due(r.ux.book, _at(r, 9, 31))
    assert sell.status == "SENT" and a.status == "DEFERRED"


# ══════════════════════════ paper_open_due / 面板 Trigger ══════════════════════════
def _bk(**kw):
    o = {"cid": "c1", "decided_on": "2026-10-14", "status": "SENT", "phase": "morning", "side": "SELL", "ticker": "1545.T"}
    o.update(kw.pop("o", {}))
    b = {"state": {"last_date": "2026-10-14"}, "orders": [o]}
    b.update(kw)
    return b


def test_paper_open_due_truth_table():
    t = dt.datetime(2026, 10, 15, 9, 25, tzinfo=JST)
    assert paper_open_due(_bk(), t)
    assert not paper_open_due(_bk(), t.replace(hour=9, minute=24)) and not paper_open_due(_bk(), t.replace(hour=11, minute=30))
    assert paper_open_due(_bk(), t.replace(hour=11, minute=29))
    assert not paper_open_due(_bk(), t + dt.timedelta(days=1))                    # 不是成交日
    assert not paper_open_due(_bk(), dt.datetime(2026, 10, 17, 9, 30, tzinfo=JST))   # 周六
    assert paper_open_due(_bk(o={"status": "DEFERRED", "phase": "open", "side": "BUY"}), t)
    assert not paper_open_due(_bk(o={"status": "FILLED"}), t)                     # 没有排队 / 等开盘后的
    assert not paper_open_due(_bk(o={"status": "SENT", "phase": "now"}), t)       # 盘中的手动单：当场成交了
    assert not paper_open_due(_bk(o={"status": "SENDING"}), t)                    # 状态不明：不叫
    assert not paper_open_due(_bk(paper_open={"decided_on": "2026-10-14", "at": "x"}), t)
    assert not paper_open_due(_bk(paper_open={"decided_on": "2026-10-14", "stop": "x"}), t)
    assert paper_open_due(_bk(paper_open={"decided_on": "2026-10-13", "at": "x"}), t)   # 上一次决策的记录：不算
    assert not paper_open_due({}, t) and not paper_open_due(None, t)


def test_trigger_calls_paper_open_once_after_0925_with_fetch_and_backoff(monkeypatch):
    import qbreak.calendar_jp as CJ
    now = {"t": dt.datetime(2026, 10, 15, 9, 20, tzinfo=JST), "m": 1000.0}
    monkeypatch.setattr(CJ, "now_jst", lambda: now["t"])
    calls = []
    book = _bk()
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or SimpleNamespace(poll=lambda: 0),
                        clock=lambda: now["t"], mono=lambda: now["m"], notify=lambda *a: None)

    def step(s):
        now["t"] += dt.timedelta(seconds=s)
        now["m"] += s
    assert trg.check() == [] and calls == []                                     # 09:20：还不到
    step(300)
    assert trg.check() == ["paper"] and calls == ["open"]                         # 09:25：叫开盘撮合
    step(60)
    assert trg.check() == [] and calls == ["open"]                                # 分钟线还没到（执行器什么都没改）：5 分钟之后再叫
    step(240)
    assert trg.check() == ["paper"] and calls == ["open", "open"]
    book["paper_open"] = {"decided_on": "2026-10-14", "at": "2026-10-15T09:30:00+09:00"}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    step(600)
    assert trg.check() == [] and calls == ["open", "open"]                        # 撮合过了：今天不再叫
    assert panel.Trigger._argv("paper", "open")[-2:] == ["--phase", "open"]
    assert panel._pull_mode("paper", "open", book, now["t"]) == "fetch"
    st = trg.export_state()
    t2 = panel.Trigger(run=lambda *a: None, clock=lambda: now["t"], mono=lambda: now["m"])
    t2.import_state(json.loads(json.dumps(st)))
    assert t2.open_last == trg.open_last


def test_trigger_open_mode_fails_back_off_like_the_other_modes(monkeypatch):
    import qbreak.calendar_jp as CJ
    now = {"t": dt.datetime(2026, 10, 15, 9, 25, tzinfo=JST), "m": 1000.0}
    monkeypatch.setattr(CJ, "now_jst", lambda: now["t"])
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(_bk(), ensure_ascii=False), encoding="utf-8")
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or SimpleNamespace(poll=lambda: 1),
                        clock=lambda: now["t"], mono=lambda: now["m"], notify=lambda *a: None)
    for _ in range(80):                                                          # 40 分钟：失败退避 + 连续 3 次失败 → 当天暂停
        trg.check()
        now["t"] += dt.timedelta(seconds=30)
        now["m"] += 30
    assert calls == ["open"] * 3 and "paper" in trg.paused


# ══════════════════════════ 1 分钟线 / PaperBroker.reprice / 文案 ══════════════════════════
def test_intraday_open_takes_todays_first_bar(monkeypatch):
    import yfinance as yf
    from qbreak.data import intraday_open
    idx = pd.DatetimeIndex(["2026-10-14 15:20", "2026-10-15 09:03", "2026-10-15 09:04", "2026-10-15 09:05"]).tz_localize(JST)
    cols = pd.MultiIndex.from_product([["1545.T", "1482.T"], ["Open", "High", "Low", "Close"]])
    data = [[690, 691, 689, 690, 1, 1, 1, 1],
            [700, 702, 699, 701, None, None, None, None],
            [701, 705, 700, 704, 1001, 1002, 1000, 1001],
            [704, 704, 698, 699, 1001, 1003, 999, 1002]]
    raw = pd.DataFrame(data, index=idx, columns=cols, dtype=float)
    monkeypatch.setattr(yf, "download", lambda *a, **k: raw)
    out = intraday_open(["1545.T", "1482.T", "7203.T"], dt.datetime(2026, 10, 15, 9, 26, tzinfo=JST))
    assert out["1545.T"] == {"open": 700.0, "high": 705.0, "low": 698.0, "first": "09:03", "last": "09:05"}
    assert out["1482.T"]["open"] == 1001.0 and out["1482.T"]["first"] == "09:04"   # 09:03 那根是空的（还没寄り付き）
    assert "7203.T" not in out
    monkeypatch.setattr(yf, "download", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert intraday_open(["1545.T"]) == {}


def test_paper_broker_reprice_buy_and_sell():
    b = PaperBroker(state_file=paths.state_dir() / "rp.json", initial_cash=1_000_000)
    b.queue("A.T", "BUY", 100, 1000.0, "2026-10-14", "c-buy", {"lot": 100})
    b.fill_pending({"A.T": 1010.0}, "2026-10-15")
    fee = b.ex.fee
    slip = b.ex.slippage_pct / 100
    c0 = b.cash()
    new = b.reprice("c-buy-f", 1000.0)
    assert new == pytest.approx(1000.0 * (1 + slip))
    old = 1010.0 * (1 + slip)
    assert b.cash() == pytest.approx(c0 + (old * 100 + fee(old * 100)) - (new * 100 + fee(new * 100)))
    assert b.positions()["A.T"].avg_px == pytest.approx(new)
    b.queue("A.T", "SELL", 100, 1000.0, "2026-10-15", "c-sell", None)
    b.fill_pending({"A.T": 1100.0}, "2026-10-16")
    pnl0, c1 = b.state["realized_pnl"], b.cash()
    s_new = b.reprice("c-sell-f", 1090.0)
    s_old = 1100.0 * (1 - slip)
    d = (s_new * 100 - fee(s_new * 100)) - (s_old * 100 - fee(s_old * 100))
    assert b.cash() == pytest.approx(c1 + d) and b.state["realized_pnl"] == pytest.approx(pnl0 + d)
    assert b.state["closed_trades"][-1]["exit_px"] == round(s_new, 4)
    assert b.reprice("nope", 1000.0) is None


def test_texts_cancel_why_how_text_and_order_card():
    o = {"status": "SENT", "phase": "morning", "side": "SELL", "decided_on": "2026-10-14", "ticker": "1545.T"}
    bk = {"state": {"last_date": "2026-10-14"}}
    why = LO.cancel_why(o, bk, dt.datetime(2026, 10, 15, 9, 10, tzinfo=JST), True)
    assert "09:25 前后按开盘价撮合" in why and "第二天早上记账" not in why
    d = {"status": "DEFERRED", "phase": "morning", "side": "BUY"}
    assert LO.how_text(d, True) == "开盘后（09:25 前后按开盘价）" and LO.how_text(d) == "开盘后（当日限り指値）"
    r = _paper2()
    sell, buy = _fixed_case(r)
    r.now["t"] = _at(r, 9, 25)
    r.ux.open_phase(feed=_feed(r))
    r.ux.save(force=True)
    html = panel._orders_card(r.ux.book, _at(r, 9, 26), True, [], tag="paper")
    assert "成交 970 @ ¥699.79" in html and "成交 677/678 @ ¥1,000.50" in html and "次日开盘" not in html


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_paper_open_without_work_is_not_a_failed_run(tmp_path):
    """模拟账户的 --phase open（面板 09:25 前后叫）：分钟线还没到 / 已经做过 → 执行器不写页面、退出码 0 → 不是「运行没有完成」；
    立花的 --phase open 照旧（没写页面就标红）。"""
    env, log = _run_env(tmp_path, 0, QBREAK_NO_HOLD="1")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--phase", "open")
    assert "运行没有完成" not in out and "live-u --notify" in _calls(log) and "--phase open" in _calls(log)
    env, log = _run_env(tmp_path, 0, QBREAK_NO_HOLD="1")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--phase", "open")
    assert "运行没有完成（退出码 0）" in out


def test_run_precheck_for_paper_open(monkeypatch, capsys):
    import run
    bp = paths.state_dir() / "live_unified_paper.json"
    bp.write_text(json.dumps(_bk(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("qbreak.calendar_jp.now_jst", lambda: dt.datetime(2026, 10, 15, 9, 0, tzinfo=JST))
    assert not run._paper_open_work(bp)
    monkeypatch.setattr("qbreak.calendar_jp.now_jst", lambda: dt.datetime(2026, 10, 15, 9, 26, tzinfo=JST))
    assert run._paper_open_work(bp)
