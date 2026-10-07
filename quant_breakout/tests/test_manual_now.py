"""盘中的手动指令（qbreak/live_unified.py 的 now_phase；2026-10-07 用户：「当天买入卖出的话在交易时间段就直接进行买入卖出
在交易时间之前的话就等交易时间的时候进行交易」）：
① 模拟账户：盘中当场成交，第二天早上的对账与券商一致（持仓核对照常通过）；
② 闸门：现价超过收盘 ×1.03 不买、今天已经有单的票明天开盘、HALT / 不在交易时间 / 早上的运行没做完 → 一会儿再试；
③ 盘中的单撤不了；同一决策里的补单不重复下；④ now_due / 命令行 / 模拟账户的取价。"""
import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd

from qbreak import manual_orders as MO
from qbreak import paths
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.live_unified import UnifiedExecutor, _MemPaper

from test_live_unified import _scenario


def _paper(tag="pn", **kw):
    make, start = _scenario([1000.0] * 30, entry=(10,), **kw)
    eng = make()
    b = _MemPaper(state_file=paths.state_dir() / f"paper_{tag}.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"],
                  market="JP")
    now = {"t": None}
    ux = UnifiedExecutor(eng, b, paths.state_dir() / f"book_{tag}.json", paper=True, check_clock=False,
                         clock=lambda: now["t"], manual_tag=tag)
    r = SimpleNamespace(eng=eng, b=b, now=now, ux=ux, k=int(eng.gidx.searchsorted(start)), tag=tag)
    eng.prime(r.k)
    return r


def _held(r) -> dict:
    return {t: int(p.qty) for t, p in r.b.positions().items()}


def _book_pos(r) -> dict:
    st = r.eng.st
    return {t: int(p.shares) for t, p in st.pos.items()} | {t: int(u) for t, u in st.core_units.items() if int(u)}


def _morning(r, until=None) -> None:
    """第 r.k 根收盘之后、下一交易日 07:40 的早上运行（模拟账户：先按开盘撮合上一次的单 → 对账 → 决策 → 下单）；每天核对持仓。"""
    for _ in range((until or r.k) - r.k + 1):
        r.now["t"] = dt.datetime.combine(next_trading_day(r.eng.gidx[r.k].date()), dt.time(7, 40), tzinfo=JST)
        r.ux.morning([r.k])
        assert not r.ux.blocked
        assert _held(r) == _book_pos(r)                                  # 券商 = 账本
        r.k += 1


def _at(r, hh: int, mm: int, days: int = 0) -> dt.datetime:
    """上一次决策的成交日（今天）hh:mm；days = 再往后几个交易日。"""
    d = next_trading_day(r.eng.gidx[r.k - 1].date())
    for _ in range(days):
        d = next_trading_day(d)
    return dt.datetime.combine(d, dt.time(hh, mm), tzinfo=JST)


def _req(r, **rec) -> dict:
    """直接写一行指令（测试里的票是 A.T / B.T：4 位代码的格式检查在 normalize）。"""
    rec.setdefault("id", f"M-{rec['kind']}-{rec['ticker'].split('.')[0]}")
    rec.setdefault("at", "x")
    rec.setdefault("source", "test")
    with open(MO.requests_path(r.tag), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _quote(px: dict):
    return lambda ts: {t: px[t] for t in ts if t in px}


def _item(r, rid: str) -> dict:
    return r.ux.book["manual"]["items"][rid]


PX = {"A.T": 1010.0, "B.T": 1520.0, "1655.T": 701.0}


# ────────── ① 模拟账户：盘中当场成交 → 第二天早上对账 ──────────
def test_paper_trim_and_buy_fill_at_once_and_reconcile_next_morning():
    r = _paper()
    _morning(r, until=14)
    assert r.eng.st.pos["A.T"].shares == 200
    core0 = r.eng.st.core_units["1655.T"]
    trim = _req(r, kind="trim", ticker="A.T", pct=12.0)                 # 200 股 ≈ 20% → 12%：按单元向下取整 = 100 股
    buy = _req(r, kind="buy", ticker="B.T", unit="rule")                # 没有买入信号的票：你自己的决定
    r.now["t"] = _at(r, 10, 0)
    assert MO.now_due(r.tag, r.ux.book, r.now["t"])
    res = r.ux.now_phase(_quote(PX))
    assert res["placed"] == 2 and res["rejected"] == 0 and res["retry"] == 0 and res["later"] == 0
    t_, b_ = _item(r, trim["id"]), _item(r, buy["id"])
    assert t_["status"] == "placed" and t_["now"] and t_["fill"]["qty"] == 100 and t_["side"] == "SELL"
    assert b_["status"] == "placed" and b_["now"] and b_["fill"]["qty"] == 100 and "先卖核心 ETF 1655.T" in b_["msg"]
    assert "没有买入信号" in b_["msg"] and MO.status_text(b_) == "盘中已成交"
    now_orders = [o for o in r.ux.orders if o.phase == "now"]
    assert {o.reason for o in now_orders} == {"manual_trim", "manual_buy", "manual_fund"}
    assert all(o.status == "FILLED" and o.cid.split("-")[-1].startswith("N") for o in now_orders)
    assert _held(r)["A.T"] == 100 and _held(r)["B.T"] == 100                # 券商那边当场成交
    assert r.eng.st.pos["A.T"].shares == 200 and "B.T" not in r.eng.st.pos  # 账本：明天早上的对账才记
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 30))                 # 都处理完了：面板不再叫
    _morning(r)                                                              # 第二天早上：按实际成交记进账本，持仓核对通过
    st = r.eng.st
    assert st.pos["A.T"].shares == 100 and st.pos["B.T"].shares == 100 and st.core_units["1655.T"] < core0
    assert st.pos["B.T"].entry_date == str(r.eng.gidx[r.k - 1].date())      # 成交日 = 盘中买的那天
    assert _item(r, trim["id"])["status"] == "done" and "盘中" in _item(r, trim["id"])["msg"]
    assert _item(r, buy["id"])["status"] == "done" and "盘中" in _item(r, buy["id"])["msg"]
    assert abs(r.b.cash() - st.cash_jpy) < 1.0                               # 现金也一致
    _morning(r)
    assert not r.ux.blocked


# ────────── ② 闸门 ──────────
def test_buy_above_close_plus_3pct_is_rejected_once():
    r = _paper("pg")
    _morning(r, until=14)
    buy = _req(r, kind="buy", ticker="B.T", unit="rule")
    r.now["t"] = _at(r, 10, 0)
    res = r.ux.now_phase(_quote({**PX, "B.T": 1500.0 * 1.05}))             # 收盘 ¥1,500 → 现价 +5%
    it = _item(r, buy["id"])
    assert res["rejected"] == 1 and it["status"] == "rejected" and "超过 3%" in it["msg"] and "只做一次" in it["msg"]
    assert not any(o.ticker == "B.T" for o in r.ux.orders) and "B.T" not in _held(r)


def test_sell_of_a_stock_bought_at_todays_open_waits_for_tomorrow_open():
    r = _paper("pb")
    _morning(r, until=10)                                                    # 第 10 根的信号 → 第 11 根开盘买 A.T
    assert "A.T" in r.eng.st.plan
    rec = _req(r, kind="sell", ticker="A.T", block_days=0)
    r.now["t"] = _at(r, 10, 0)
    res = r.ux.now_phase(_quote(PX))
    it = _item(r, rec["id"])
    assert res["later"] == 1 and it["status"] == "pending" and it["hold"] == r.now["t"].date().isoformat()
    assert "账本明天早上才记上" in it["msg"] and MO.status_text(it) == "明天开盘"
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 5))                   # 「明天开盘」的：面板不再叫
    assert r.ux.now_phase(_quote(PX))["later"] == 0                          # 再跑一次也不再试
    _morning(r)                                                              # 明天早上：寄付卖出
    it = _item(r, rec["id"])
    assert it["status"] == "placed" and not it.get("now") and "hold" not in it
    _morning(r)
    assert "A.T" not in r.eng.st.pos and _item(r, rec["id"])["status"] == "done"


def test_waits_outside_the_session_under_halt_and_before_the_morning_run():
    r = _paper("pw")
    _morning(r, until=14)
    rec = _req(r, kind="trim", ticker="A.T", pct=12.0)
    for hh, mm, why in ((8, 30, "不是交易时间"), (12, 0, "不是交易时间"), (15, 30, "不是交易时间")):
        r.now["t"] = _at(r, hh, mm)
        res = r.ux.now_phase(_quote(PX))
        assert res["retry"] == 1 and why in _item(r, rec["id"])["msg"] and _item(r, rec["id"])["status"] == "pending"
    paths.halt_file().write_text("测试", encoding="utf-8")
    r.now["t"] = _at(r, 10, 0)
    assert r.ux.now_phase(_quote(PX))["retry"] == 1 and "HALT" in _item(r, rec["id"])["msg"]
    paths.halt_file().unlink()
    r.now["t"] = _at(r, 10, 0, days=1)                                       # 第二天盘中、早上的运行还没做
    assert r.ux.now_phase(_quote(PX))["retry"] == 1 and "早上的运行还没完成" in _item(r, rec["id"])["msg"]
    r.now["t"] = _at(r, 10, 20)
    res = r.ux.now_phase(lambda ts: {})                                      # 取不到现价：一会儿再试
    assert res["retry"] == 1 and "取不到现价" in _item(r, rec["id"])["msg"]
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 25)) and MO.now_due(r.tag, r.ux.book, _at(r, 10, 31))   # 10 分钟后再叫
    assert r.ux.now_phase(_quote(PX))["placed"] == 1 and _item(r, rec["id"])["status"] == "placed"
    assert not any(o.ticker == "A.T" and o.phase == "now" and o.status != "FILLED" for o in r.ux.orders)


# ────────── ③ 撤不了 / 不重复下单 ──────────
def test_now_order_cannot_be_cancelled_and_is_not_placed_again():
    r = _paper("pc")
    _morning(r, until=14)
    rec = _req(r, kind="sell", ticker="A.T", block_days=0)
    r.now["t"] = _at(r, 10, 0)
    assert r.ux.now_phase(_quote(PX))["placed"] == 1
    assert r.eng.st.pending_exit.get("A.T") == "manual" and "A.T" not in _held(r)
    why = MO.check(MO.normalize({"kind": "cancel", "target": rec["id"]}), r.ux.book, r.tag)
    assert why == MO.NOW_NO_CANCEL
    _req(r, kind="cancel", ticker="A.T", target=rec["id"], id="M-cancel-A")  # 绕过页面的检查直接写：执行器也不撤
    r.now["t"] = _at(r, 10, 30)
    r.ux.morning([])                                                          # 同一天再跑一次早上的流程（例如开机后的补跑）
    assert _item(r, "M-cancel-A")["status"] == "rejected" and _item(r, rec["id"])["status"] == "placed"
    sells = [o for o in r.ux.orders if o.ticker == "A.T" and o.side == "SELL"]
    assert len(sells) == 1 and sells[0].phase == "now"                       # 账本里「待卖」的票不再下寄付卖单
    _morning(r)
    assert "A.T" not in r.eng.st.pos and _item(r, rec["id"])["status"] == "done"


# ────────── ④ now_due / 命令行 / 取价 ──────────
def test_now_due_cases():
    at = lambda h, m, d=6: dt.datetime(2026, 10, d, h, m, tzinfo=JST)   # noqa: E731  2026-10-06（火）
    book = {"state": {"last_date": "2026-10-05"}}
    rec = MO.append("nd", {"kind": "sell", "ticker": "7203"}, clock=lambda: at(9, 0))
    assert MO.now_due("nd", book, at(10, 0)) and MO.now_due("nd", book, at(12, 30)) and MO.now_due("nd", book, at(15, 24))
    assert not any(MO.now_due("nd", book, at(h, m)) for h, m in ((8, 59), (11, 30), (12, 0), (15, 25), (16, 0)))
    assert not MO.now_due("nd", {"state": {"last_date": "2026-10-02"}}, at(10, 0))     # 早上的运行还没处理 10-05
    assert not MO.now_due("nd", book, at(10, 0, d=10))                               # 周六
    paths.halt_file().write_text("x", encoding="utf-8")
    assert not MO.now_due("nd", book, at(10, 0))
    paths.halt_file().unlink()
    it = {**rec, "status": "pending"}
    book["manual"] = {"items": {rec["id"]: it}}                                      # 读进账本了
    assert MO.now_due("nd", book, at(10, 0))
    it["hold"] = "2026-10-06"
    assert not MO.now_due("nd", book, at(10, 0))                                     # 「明天开盘」的：今天不再叫
    assert MO.now_due("nd", {**book, "state": {"last_date": "2026-10-06"}}, at(10, 0, d=7))   # 第二天（早上的运行之后）又算
    it.pop("hold")
    it["tried"] = at(9, 55).isoformat()
    assert not MO.now_due("nd", book, at(10, 0)) and MO.now_due("nd", book, at(10, 5))
    it["status"] = "placed"
    assert not MO.now_due("nd", book, at(10, 30))
    MO.append("nd", {"kind": "core", "pct": 50}, clock=lambda: at(10, 40))           # 闲置资金比例：不用盘中跑
    assert not MO.now_due("nd", book, at(10, 45))


def test_live_u_phase_now_without_work_does_not_build_the_engine(monkeypatch, capsys):
    import run

    def boom(*a, **k):
        raise AssertionError("不该建引擎")
    monkeypatch.setattr(run, "_unified_engine", boom)
    assert run.main(["live-u", "--broker", "paper", "--phase", "now"]) == 0
    assert "没有要盘中下的手动指令" in capsys.readouterr().out


def test_intraday_last_takes_only_fresh_bars_of_today(monkeypatch):
    import yfinance as yf
    from qbreak.data import intraday_last
    idx = pd.DatetimeIndex(["2026-10-05 05:59", "2026-10-06 00:20", "2026-10-06 01:11"], tz="UTC")   # 前一天 14:59 / 09:20 / 10:11 JST
    cols = pd.MultiIndex.from_product([["7203.T", "6758.T", "9984.T"], ["Open", "Close"]])
    raw = pd.DataFrame([[1, 2590.0, 1, 3000.0, 1, 9000.0], [1, 2595.0, 1, None, 1, 9010.0], [1, 2600.0, 1, None, 1, None]],
                       index=idx, columns=cols)
    monkeypatch.setattr(yf, "download", lambda *a, **k: raw)
    now = dt.datetime(2026, 10, 6, 10, 30, tzinfo=JST)
    assert intraday_last(["7203.T", "6758.T", "9984.T", "1545.T"], now=now) == {"7203.T": 2600.0}   # 前一天的 / 70 分钟前的 / 没有的不给
    one = pd.DataFrame({"Close": [1999.0]}, index=pd.DatetimeIndex(["2026-10-06 01:20"], tz="UTC"))
    monkeypatch.setattr(yf, "download", lambda *a, **k: one)
    assert intraday_last(["1545.T"], now=now) == {"1545.T": 1999.0}

    def fail(*a, **k):
        raise OSError("network")
    monkeypatch.setattr(yf, "download", fail)
    assert intraday_last(["7203.T"], now=now) == {} and intraday_last([], now=now) == {}
