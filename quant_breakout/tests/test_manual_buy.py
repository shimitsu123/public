"""手动买入（qbreak/manual_orders.py 的 buy；2026-10-06 用户：「根据趋势等等建议的股票也要加到里面 可以一键买的」）：
① 格式（按规则的仓位 / 股数 / 金额 / %）、页面 / 命令行的检查（已持有 / 核心 ETF / 重复 / 名额）；
② 执行器（立花适配器 + 模拟交易所）：新收盘的决策里放进统一决策的 plan → 统一决策先留钱（卖核心补）→ 寄付指値 / 开盘后补单
   → 成交后就是普通持仓（止损按 ATR、规则离场）；
③ 闸门：同一决策补单不买（等下一次决策）、资格检查 / 新仓倍数 0 / 决算前 / 名额满 / 单只上限、跳空只做一次、撤回、
   同一次决策里先卖出一只再买入；
④ 模拟账户（PaperBroker）与引擎（同一决策日放进同样的 plan）逐笔一致。"""
import dataclasses
import datetime as dt
import json

import pytest

from qbreak import manual_orders as MO
from qbreak import paths
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.live_unified import UnifiedExecutor, _MemPaper

from test_manual_orders import TAG, _Run


def _buy(r, t="B.T", **kw):
    """直接写一行买入指令（测试的票是 A.T / B.T；4 位代码的格式检查在 normalize）。"""
    rec = {"kind": "buy", "ticker": t, "unit": "rule", "source": "test", **kw}
    rec.setdefault("id", f"M{r.at(r.k - 1, 6):%Y%m%d-%H%M%S}-buy-{t.split('.')[0]}")
    rec.setdefault("at", r.at(r.k - 1, 6).isoformat())
    with open(MO.requests_path(TAG), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _write(rec: dict, tag: str = TAG) -> None:
    with open(MO.requests_path(tag), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ────────── ① 格式、检查 ──────────
def test_normalize_and_describe_buy():
    n = MO.normalize
    assert n({"kind": "buy", "ticker": "6501"}) == {"kind": "buy", "ticker": "6501.T", "unit": "rule", "source": "cli"}
    assert n({"kind": "buy", "ticker": "6501", "unit": "yen", "value": 500000.4})["value"] == 500000
    assert n({"kind": "buy", "ticker": "6501", "unit": "pct", "value": 20})["value"] == 20.0
    for bad, msg in [({"unit": "lots"}, "买入的单位"), ({"unit": "shares", "value": 0}, "大于 0"), ({"unit": "shares"}, "目标值"),
                     ({"unit": "pct", "value": 120}, "0〜100")]:
        with pytest.raises(ValueError, match=msg):
            n({"kind": "buy", "ticker": "6501", **bad})
    assert MO.describe({"kind": "buy", "ticker": "6501.T", "unit": "rule"}) == "买入 6501.T（按规则的仓位）"
    assert MO.describe({"kind": "buy", "ticker": "6501.T", "unit": "shares", "value": 300}) == "买入 6501.T → 300 股"
    assert MO.REASON_TEXT["manual_buy"] == "手动买入" and "buy" in MO.ORDER_KINDS and "buy" not in MO.POS_KINDS


def _bk(pos=("7203.T",), pend=(), plan=(), items=None, mx=4):
    st = {"last_date": "2026-10-05", "history": [["2026-10-05", 1_000_000.0]], "core_units": {"1655.T": 100},
          "pos": {t: {"shares": 100, "last_close": 1000.0, "entry_px": 1000.0} for t in pos},
          "pending_exit": {t: "dead_cross" for t in pend}, "plan": {t: [1000.0, 100, "2026-10-05"] for t in plan}}
    return {"state": st, "manual": {"items": items or {}, "blocks": {}, "max_positions": mx, "core": ["1655.T", "1545.T"]}}


def test_check_buy_held_core_duplicate_and_slots():
    n = MO.normalize
    b = _bk()
    assert MO.check(n({"kind": "buy", "ticker": "6501"}), b) is None
    assert "已经持有" in MO.check(n({"kind": "buy", "ticker": "7203"}), b)
    assert "核心 ETF" in MO.check(n({"kind": "buy", "ticker": "1545"}), b)
    assert "已经排在开盘买入" in MO.check(n({"kind": "buy", "ticker": "6501"}), _bk(plan=("6501.T",)))
    full = _bk(pos=("7203.T", "6758.T", "8035.T"), plan=("9984.T",))
    assert MO.slots(full) == {"held": 3, "buys": 1, "used": 4, "max": 4, "free": 0}
    assert "名额已满" in MO.check(n({"kind": "buy", "ticker": "6501"}), full)
    assert MO.check(n({"kind": "buy", "ticker": "6501"}), _bk(pos=("7203.T", "6758.T", "8035.T", "9984.T"),
                                                                pend=("9984.T",))) is None   # 排在开盘卖出的不占名额
    MO.append(TAG, {"kind": "sell", "ticker": "8035"})                    # 先写「卖出全部」：同一次决策里先卖 → 名额空出来
    assert MO.slots(full, TAG)["free"] == 1 and MO.check(n({"kind": "buy", "ticker": "6501"}), full, tag=TAG) is None
    MO.append(TAG, {"kind": "buy", "ticker": "6501"})
    assert "没处理完" in MO.check(n({"kind": "buy", "ticker": "6501"}), full, tag=TAG)
    assert "名额已满" in MO.check(n({"kind": "buy", "ticker": "6502"}), full, tag=TAG)
    sm = {"suggest": {"rows": [{"ticker": "6502.T", "buy": {"block": "JPX 市場区分「ETF」不是…"}}]}}
    assert "不能买：JPX" in MO.check(n({"kind": "buy", "ticker": "6502"}), _bk(), sm=sm)


# ────────── ② 执行器：买入 ──────────
def test_buy_reserves_cash_sells_core_and_opens_like_a_rule_entry():
    r = _Run([1000.0] * 30, entry=(10,))                                 # 牛市：闲置资金全在 1655
    r.until(14)
    assert set(r.eng.st.pos) == {"A.T"} and r.eng.st.core_units["1655.T"] > 0
    rec = _buy(r)
    r.day()                                                              # 第 15 根：决策之前放进 plan
    it = r.item(rec["id"])
    assert it["status"] == "placed" and it["side"] == "BUY" and it["shares"] == 100 and it["limit"] == 1545
    assert "没有买入信号" in it["msg"] and "按规则的仓位" in it["msg"]
    assert r.eng.st.plan["B.T"] == [1500.0, 100, str(r.eng.gidx[15].date())]
    assert r.ux.book["manual"]["buys"]["B.T"]["shares"] == 100 and r.ux.book["manual"]["max_positions"] == 4
    assert r.eng.st.core_plan["1655.T"][0] == "SELL"                     # 钱不够 → 同一个开盘先卖核心 ETF
    o = [x for x in r.ux.orders if x.ticker == "B.T"][0]
    assert o.reason == "manual_buy" and o.cid.endswith("-BUY-B.T-M") and o.limit == 1545
    r.day()                                                              # 第 16 根开盘：卖核心 → 买入 → 早上对账
    ps = r.eng.st.pos["B.T"]
    assert ps.shares == 100 and ps.entry_date == str(r.eng.gidx[16].date()) and ps.stop_px < ps.entry_px   # 止损按 ATR（与规则的新仓相同）
    it = r.item(rec["id"])
    assert it["status"] == "done" and it["fill"]["qty"] == 100 and "新仓" in it["msg"]
    assert not r.ux.book["manual"]["buys"] and r.exch.pos["B.T"] == 100
    r.day()                                                              # 持仓核对照常通过
    assert not r.ux.blocked and r.eng.st.pos["B.T"].shares == 100
    sm = r.ux.summary()["manual"]
    assert sm["active"] == 0 and MO.active(sm)                          # 做过买入 → 与云端不同是预期的


def test_same_decision_retry_waits_for_the_open_then_buys_in_session():
    """07:40 的运行之后点的买入：08:35 的重试不买 → 09:00 开盘后盘中马上买（钱不够先卖核心 ETF）。"""
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    u0 = r.eng.st.core_units["1655.T"]
    rec = _buy(r)
    r.now["t"] = r.at(r.k - 1, 8, 35)                                   # 07:40 的运行之后
    r.ux.morning([])
    it = r.item(rec["id"])
    assert it["status"] == "pending" and it["wait"] and it["msg"] == "09:00 开盘后马上下单（盘中）"
    assert "B.T" not in r.eng.st.plan and not MO.due(TAG, r.ux.book, r.now["t"])
    res = r.session(9, 30)
    it = r.item(rec["id"])
    assert res["placed"] == 1 and it["status"] == "placed" and it["now"] and it["fill"]["qty"] == 100
    assert "先卖核心 ETF 1655.T" in it["msg"] and "没有买入信号" in it["msg"]
    fund = [o for o in r.ux.orders if o.reason == "manual_fund"]
    assert len(fund) == 1 and fund[0].kind == "core" and fund[0].phase == "now" and fund[0].status == "FILLED"
    r.day()                                                              # 第二天早上：对账记进账本，持仓核对照常
    ps = r.eng.st.pos["B.T"]
    assert ps.shares == 100 and ps.entry_date == str(r.eng.gidx[15].date()) and r.item(rec["id"])["status"] == "done"
    assert r.eng.st.core_units["1655.T"] < u0 and r.exch.pos["B.T"] == 100 and not r.ux.blocked


def test_buy_gates_reject_like_rule_entries():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    base = r.eng.entry_gate_fn
    r.eng.entry_gate_fn = lambda t, i: "测试：资格检查挡" if t == "B.T" else (base(t, i) if base else None)
    a = _buy(r)
    held = _buy(r, t="A.T", id="M-held")
    core = _buy(r, t="1655.T", id="M-core")
    r.day()
    assert r.item(a["id"])["status"] == "rejected" and "资格检查挡" in r.item(a["id"])["msg"]
    assert r.item(held["id"])["status"] == "rejected" and "已经持有" in r.item(held["id"])["msg"]
    assert r.item(core["id"])["status"] == "rejected" and "核心 ETF" in r.item(core["id"])["msg"]
    r.eng.entry_gate_fn = base
    r.eng._entry_mult = lambda t, i: 0.0                                 # 规则现在不开新仓
    b = _buy(r, id="M-em0")
    r.day()
    assert r.item(b["id"])["status"] == "rejected" and "新仓倍数是 0" in r.item(b["id"])["msg"]
    assert "B.T" not in r.eng.st.plan and not any(o.ticker == "B.T" for o in r.ux.orders)


def test_slots_full_and_sell_first_in_the_same_decision():
    r = _Run([1000.0] * 30, entry=(10,))
    r.eng.cfg = dataclasses.replace(r.eng.cfg, max_positions=1)          # 名额 1 只：A.T 拿着就满了
    r.until(14)
    b = _buy(r, id="M-full")
    r.day()
    assert r.item(b["id"])["status"] == "rejected" and "名额已满" in r.item(b["id"])["msg"]
    sell = {"kind": "sell", "ticker": "A.T", "block_days": 0, "source": "test", "id": "M-z-sell", "at": r.at(r.k - 1, 7).isoformat()}
    buy = {"kind": "buy", "ticker": "B.T", "unit": "rule", "source": "test", "id": "M-a-buy", "at": r.at(r.k - 1, 6).isoformat()}
    _write(buy)                                                          # 买入写得更早：执行器仍先处理卖出
    _write(sell)
    r.day()
    assert r.item("M-z-sell")["status"] == "placed" and r.item("M-a-buy")["status"] == "placed"
    assert r.eng.st.pending_exit.get("A.T") == "manual" and "B.T" in r.eng.st.plan
    r.day()
    assert set(r.eng.st.pos) == {"B.T"} and r.item("M-a-buy")["status"] == "done"


def test_buy_capped_at_single_position_limit_and_by_cash():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    rec = _buy(r, unit="pct", value=60)
    r.day()
    it = r.item(rec["id"])
    eq = r.eng.equity(15)
    assert it["status"] == "placed" and "单只上限 34%" in it["msg"]
    assert it["shares"] * 1500 <= eq * 0.34 + 1e-6 and (it["shares"] + 100) * 1500 > eq * 0.34


def test_buy_is_one_shot_when_the_open_gaps_up():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    b_open = r.eng.A.open.copy()
    j = r.eng.col["B.T"]
    b_open[16, j] = 1600.0                                               # 第 16 根开盘 1600 > 限价 1545
    r.eng.A.open[:] = b_open
    rec = _buy(r)
    r.day()
    r.day()
    it = r.item(rec["id"])
    assert "B.T" not in r.eng.st.pos and it["status"] == "rejected" and "开盘没买到" in it["msg"] and "只做一次" in it["msg"]
    assert not r.ux.book["manual"]["buys"]
    r.day()                                                              # 之后不再自动重下
    assert "B.T" not in r.eng.st.pos and not any(o.ticker == "B.T" for o in r.ux.orders)


def test_cancel_a_deferred_buy_before_the_open():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    rec = _buy(r)
    r.day()
    o = [x for x in r.ux.orders if x.ticker == "B.T"][0]
    assert o.status == "DEFERRED"                                        # 开盘前余力不够 → 留到开盘后
    MO.append(TAG, {"kind": "cancel", "target": rec["id"]}, clock=lambda: r.at(r.k - 1, 8, 0))
    r.now["t"] = r.at(r.k - 1, 8, 10)
    r.ux.morning([])                                                     # 同一决策补单的运行：撤回中的先处理
    it = r.item(rec["id"])
    assert it["status"] == "cancelled" and "这笔买入不下" in it["msg"]
    assert "B.T" not in r.eng.st.plan and o.status == "SKIPPED"
    r.day()
    assert "B.T" not in r.eng.st.pos


# ────────── ④ 模拟账户 = 引擎 ──────────
@pytest.mark.parametrize("seed", [7, 11, 23])
def test_paper_executor_with_periodic_buys_equals_engine(seed):
    """260 天的合成行情：每 15 天手动买一只还没拿的票（按规则的仓位）—— 模拟账户执行器与引擎（同一决策日放进同样的 plan）
    逐日权益、成交完全相同。"""
    from test_live_unified import _synth
    make, start = _synth(seed)
    eng = make()
    tag = f"b{seed}"
    b = _MemPaper(state_file=paths.state_dir() / f"pb{seed}.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"], market="JP")
    now = {"t": None}
    ux = UnifiedExecutor(eng, b, paths.state_dir() / f"bb{seed}.json", paper=True, respect_halt=False, check_clock=False,
                         clock=lambda: now["t"], manual_tag=tag, persist=False)
    k0 = int(eng.gidx.searchsorted(start))
    eng.prime(k0)
    planned, n_req = {}, 0
    stocks = sorted(t for t in eng.col if t not in eng.core_set)
    for k in range(k0, len(eng.gidx)):
        if (k - k0) % 15 == 7:
            cand = [t for t in stocks if t not in eng.st.pos and t not in eng.st.plan and eng.A.has[k, eng.col[t]]]
            if cand:
                _write({"kind": "buy", "ticker": cand[(k // 15) % len(cand)], "unit": "rule", "id": f"M-{seed}-{k}",
                        "at": str(k)}, tag)
                n_req += 1
        now["t"] = dt.datetime.combine(next_trading_day(eng.gidx[k].date()), dt.time(7, 40), tzinfo=JST)
        ux.morning([k])
        assert not ux.blocked
        d = str(eng.gidx[k].date())
        mine = {t: list(eng.st.plan[t]) for t, x in ux.book["manual"]["buys"].items() if x.get("decided_on") == d and t in eng.st.plan}
        if mine:
            planned[k] = mine
    done = [it for it in ux.book["manual"]["items"].values() if it.get("kind") == "buy" and it.get("status") == "done"]
    assert n_req >= 10 and len(planned) >= 3 and done                      # 真的买过（有的被名额 / 跳空挡掉是正常的）
    ref = make()
    ref.prime(k0)
    ref.pre_decide_fn = lambda i: ref.st.plan.update({t: list(v) for t, v in planned.get(i, {}).items()})
    for k in range(k0, len(ref.gidx)):
        ref.step(k)
    ex = [h[1] for h in eng.st.history]
    rf = [h[1] for h in ref.st.history]
    assert len(ex) == len(rf) and max(abs(a - c) for a, c in zip(ex, rf)) == 0.0
    assert eng.st.trades == ref.st.trades and eng.st.core_trades == ref.st.core_trades
