"""手动「调整持仓」（qbreak/manual_orders.py 的 adjust；2026-10-06 用户：「也可以调节现在个股的持仓和金额」）：
① 格式（股数 / 金额 / %）、按账本的预览与检查、加仓最早哪个开盘；
② 执行器（立花适配器 + 模拟交易所）：加仓 → 统一决策先留钱（卖核心补）→ 寄付指値 / 开盘后补单 → 成交并进原持仓
   （成本加权平均、止损 / 峰值 / 持有天数不变）→ 第二天持仓核对照常；减仓方向 = 减仓；
③ 闸门：同一决策补单不加仓（等下一次决策）、单只上限 34%、资格检查 / 新仓倍数 0 不加、跳空只做一次、撤回（含留到开盘后的）；
④ 模拟账户（PaperBroker）与引擎（回测撮合 _exec_adds）逐笔一致。"""
import datetime as dt
import json

import pandas as pd
import pytest

from qbreak import manual_orders as MO
from qbreak import paths
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.live_unified import UnifiedExecutor, _MemPaper

from test_live_unified import _scenario
from test_manual_orders import TAG, _Run


def _req(r, **kw):
    """直接写一行指令（测试的票是 A.T；4 位代码的格式检查在 normalize）。"""
    rec = {"kind": "adjust", "ticker": "A.T", "source": "test", **kw}
    rec.setdefault("id", f"M{r.at(r.k - 1, 6):%Y%m%d-%H%M%S}-adjust-A")
    rec.setdefault("at", r.at(r.k - 1, 6).isoformat())
    with open(MO.requests_path(TAG), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ────────── ① 格式、预览、检查 ──────────
def test_normalize_adjust_units():
    n = MO.normalize
    assert n({"kind": "adjust", "ticker": "7203", "unit": "shares", "value": "300"})["value"] == 300
    assert n({"kind": "adjust", "ticker": "7203", "unit": "yen", "value": 512345.6})["value"] == 512346
    assert n({"kind": "adjust", "ticker": "7203", "unit": "PCT", "value": 12.345}) == {
        "kind": "adjust", "ticker": "7203.T", "unit": "pct", "value": 12.35, "source": "cli"}
    for bad, msg in [({"unit": "lots", "value": 1}, "单位"), ({"unit": "shares"}, "目标值"), ({"unit": "shares", "value": 1.5}, "整数"),
                     ({"unit": "pct", "value": 101}, "0〜100"), ({"unit": "yen", "value": -1}, "负数"),
                     ({"unit": "yen", "value": "inf"}, "负数")]:
        with pytest.raises(ValueError, match=msg):
            n({"kind": "adjust", "ticker": "7203", **bad})


def test_target_shares_plan_and_check():
    st = {"pos": {"7203.T": {"shares": 300, "last_close": 1000.0, "entry_px": 900.0}}, "pending_exit": {},
          "history": [["2026-10-05", 1_000_000.0]]}
    assert MO.target_shares("shares", 250, 1e6, 1000.0) == 200
    assert MO.target_shares("yen", 499_999, 1e6, 1000.0) == 400 and MO.target_shares("pct", 25, 1e6, 1000.0) == 200
    a = MO.adjust_plan({"ticker": "7203.T", "unit": "pct", "value": 50}, st)
    assert a["want"] == 500 and a["target"] == 300 and a["capped"] and a["delta"] == 0          # 上限 34% = 300 股
    a = MO.adjust_plan({"ticker": "7203.T", "unit": "yen", "value": 100_000}, st)
    assert a["target"] == 100 and a["delta"] == -200 and a["new_pct"] == 10.0
    book = {"state": st, "manual": {"items": {}, "blocks": {}}}
    n = MO.normalize
    assert "不用调" in MO.check(n({"kind": "adjust", "ticker": "7203", "unit": "shares", "value": 399}), book)
    assert "不能再加" in MO.check(n({"kind": "adjust", "ticker": "7203", "unit": "pct", "value": 40}), book)
    book["manual"]["cap_pct"] = 40.0                                     # 执行器写进账本的上限
    assert MO.check(n({"kind": "adjust", "ticker": "7203", "unit": "pct", "value": 40}), book) is None
    assert MO.check(n({"kind": "adjust", "ticker": "7203", "unit": "shares", "value": 100}), book) is None
    assert "没有 6758.T" in MO.check(n({"kind": "adjust", "ticker": "6758", "unit": "shares", "value": 100}), book)
    MO.append(TAG, {"kind": "adjust", "ticker": "7203", "unit": "shares", "value": 100})
    assert "没处理完" in MO.check(n({"kind": "sell", "ticker": "7203"}), book, tag=TAG)
    assert MO.describe({"kind": "adjust", "ticker": "7203.T", "unit": "yen", "value": 500000}) == "调仓 7203.T → ¥500,000"


# ────────── ② 执行器：加仓 / 减仓 ──────────
def test_add_reserves_cash_sells_core_and_merges_into_the_position():
    r = _Run([1000.0] * 30, entry=(10,))                                 # 牛市：闲置资金全在 1655
    r.until(14)
    ps0 = r.eng.st.pos["A.T"]
    sh0, stop0, ent0, hold0 = ps0.shares, ps0.stop_px, ps0.entry_date, ps0.hold
    assert sh0 == 200 and r.eng.st.core_units["1655.T"] > 0
    rec = _req(r, unit="shares", value=300)
    r.day()                                                              # 第 15 根：决策之前变成加仓计划
    it = r.item(rec["id"])
    assert it["status"] == "placed" and it["shares"] == 100 and it["side"] == "BUY" and it["limit"] == 1030
    assert r.eng.st.add_plan["A.T"][:2] == [1000.0, 100] and r.ux.book["manual"]["adds"]["A.T"]["shares"] == 100
    assert r.eng.st.core_plan["1655.T"][0] == "SELL"                     # 钱不够 → 同一个开盘先卖核心 ETF
    o = [x for x in r.ux.orders if x.reason == "manual_add"][0]
    assert o.cid.endswith("-BUY-A.T-M") and o.side == "BUY" and o.status == "DEFERRED"   # 开盘前余力不够 → 开盘后再下
    assert r.ux.book["manual"]["cap_pct"] == 34.0
    r.day()                                                              # 第 16 根开盘：卖核心 → 开盘后补单 → 早上对账
    ps = r.eng.st.pos["A.T"]
    assert ps.shares == 300 and ps.stop_px == stop0 and ps.entry_date == ent0 and ps.hold == hold0 + 2
    assert abs(ps.entry_px - (200 * ent_px(r, ent0) + 100 * 1000.0) / 300) < 1.0
    assert r.item(rec["id"])["status"] == "done" and r.item(rec["id"])["fill"]["qty"] == 100
    assert not r.eng.st.add_plan and not r.ux.book["manual"]["adds"] and r.exch.pos["A.T"] == 300
    r.day()                                                              # 持仓核对照常通过
    assert not r.ux.blocked and r.eng.st.pos["A.T"].shares == 300
    sm = r.ux.summary()["manual"]
    assert sm["active"] == 0 and MO.active(sm)                          # 做过加仓 → 与云端不同是预期的


def ent_px(r, entry_date) -> float:
    return float(r.eng.A.open[int(r.eng.gidx.searchsorted(pd.Timestamp(entry_date))), r.eng.col["A.T"]])


def test_adjust_down_by_amount_is_a_trim():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    rec = _req(r, unit="yen", value=150_000)                            # 200 股 → ¥15 万 = 100 股（单元向下取整）
    r.day()
    it = r.item(rec["id"])
    assert it["status"] == "placed" and it["side"] == "SELL" and r.ux.book["manual"]["trims"]["A.T"]["shares"] == 100
    o = [x for x in r.ux.orders if x.ticker == "A.T"][0]
    assert o.reason == "manual_trim" and o.qty == 100
    r.day()
    assert r.eng.st.pos["A.T"].shares == 100 and r.item(rec["id"])["status"] == "done"


def test_same_decision_retry_does_not_add_but_waits_for_the_open():
    """07:40 的运行之后点的加仓：08:35 的重试不加（不改寄付单）→ 09:00 开盘后盘中马上下（2026-10-07 起）。"""
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    rec = _req(r, unit="shares", value=300)
    r.now["t"] = r.at(r.k - 1, 8, 35)                                   # 07:40 的运行之后
    r.ux.morning([])
    it = r.item(rec["id"])
    assert it["status"] == "pending" and it["wait"] and it["msg"] == "09:00 开盘后马上下单（盘中）"
    assert not r.eng.st.add_plan and not any(o.reason == "manual_add" for o in r.ux.orders)
    assert not MO.due(TAG, r.ux.book, r.now["t"])                       # 不会一直叫重试
    assert MO.now_due(TAG, r.ux.book, r.at(r.k - 1, 10, 0))             # 盘中：面板叫执行器
    res = r.session(10, 0)
    it = r.item(rec["id"])
    assert res["placed"] == 1 and it["status"] == "placed" and it["now"] and "wait" not in it and it["side"] == "BUY"
    o = [x for x in r.ux.orders if x.reason == "manual_add"][0]
    assert o.phase == "now" and o.status == "FILLED" and o.qty == 100
    r.day()                                                              # 第二天早上的对账：并进原来的持仓
    assert r.eng.st.pos["A.T"].shares == 300 and r.item(rec["id"])["status"] == "done" and "盘中买入" in r.item(rec["id"])["msg"]
    r.day()
    assert not r.ux.blocked


def test_add_is_capped_at_the_single_position_limit():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    rec = _req(r, unit="pct", value=60)
    r.day()
    it = r.item(rec["id"])
    assert it["status"] == "placed" and it["shares"] == 100 and "单只上限 34%" in it["msg"]       # 34% ≈ 300 股


def test_add_rejected_when_already_near_the_limit():
    r2 = _Run([1000.0] * 30, entry=(10,))
    r2.until(14)
    r2.eng.st.pos["A.T"].shares = 300                                   # 已经约 30%：再加一个单元就超过 34%
    r2.exch.pos["A.T"] = 300
    r2.exch.cash -= 100_000
    r2.eng.st.cash_jpy -= 100_000
    rec2 = _req(r2, unit="shares", value=400, id="M-cap-2")
    r2.day()
    assert r2.item(rec2["id"])["status"] == "rejected" and "不能再加" in r2.item(rec2["id"])["msg"]


def test_gates_block_adds_but_not_trims():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    base = r.eng.entry_gate_fn
    r.eng.entry_gate_fn = lambda t, i: "被踢出日経225" if t == "A.T" else base(t, i)
    rec = _req(r, unit="shares", value=300)
    r.day()
    assert r.item(rec["id"])["status"] == "rejected" and "不加仓：被踢出日経225" in r.item(rec["id"])["msg"]
    assert not r.eng.st.add_plan
    r.eng.entry_gate_fn = base
    r.eng.em["JP"] = pd.DataFrame(0.0, index=r.eng.gidx, columns=["A.T"])    # 规则现在不开新仓（倍数 0）
    rec2 = _req(r, unit="shares", value=300, id="M-add-2")
    r.day()
    assert r.item(rec2["id"])["status"] == "rejected" and "新仓倍数是 0" in r.item(rec2["id"])["msg"]
    rec3 = _req(r, unit="shares", value=100, id="M-trim-3")             # 减仓照常
    r.day()
    assert r.item(rec3["id"])["status"] == "placed"


def test_add_is_one_shot_when_the_open_gaps_up():
    a = [1000.0] * 30
    op = list(a)
    op[16] = 1050.0                                                      # 第 16 天开盘 +5% > 限价（收盘 ×1.03）
    r = _Run(a, a_open=op, entry=(10,))
    r.until(14)
    rec = _req(r, unit="shares", value=300)
    r.day()
    r.day()
    it = r.item(rec["id"])
    assert it["status"] == "rejected" and "没买到" in it["msg"] and r.eng.st.pos["A.T"].shares == 200
    r.until(r.k + 2)
    assert not any(o.reason == "manual_add" for o in r.ux.orders) and not r.ux.blocked


def test_cancel_a_deferred_add_before_the_open():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    rec = _req(r, unit="shares", value=300)
    r.day()
    o = [x for x in r.ux.orders if x.reason == "manual_add"][0]
    assert o.status == "DEFERRED"
    MO.append(TAG, {"kind": "cancel", "target": rec["id"]}, clock=lambda: r.at(r.k - 1, 8, 40))
    r.now["t"] = r.at(r.k - 1, 8, 40)
    r.ux.morning([])                                                     # 页面的重试：撤回中的先处理
    assert r.item(rec["id"])["status"] == "cancelled" and o.status == "SKIPPED"
    assert not r.eng.st.add_plan and not r.ux.book["manual"]["adds"]
    r.day()
    r.day()
    assert r.eng.st.pos["A.T"].shares == 200 and not r.ux.blocked


def test_cancel_read_at_the_open_phase_still_stops_a_deferred_add():
    """08:50 之后点的撤回：09:05 的开盘后运行先读撤回，再下留到开盘后的单。"""
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    rec = _req(r, unit="shares", value=300)
    r.day()
    MO.append(TAG, {"kind": "cancel", "target": rec["id"]}, clock=lambda: r.at(r.k - 1, 9, 0))
    r.day()
    assert r.item(rec["id"])["status"] == "cancelled" and r.eng.st.pos["A.T"].shares == 200
    assert not [x for h in r.ux.book["history"] for x in h["orders"] if x["reason"] == "manual_add" and x["filled_qty"]]


# ────────── ④ 模拟账户 = 引擎 ──────────
def test_paper_account_add_equals_engine_add():
    make, start = _scenario([1000.0] * 30, entry=(10,))
    eng = make()
    b = _MemPaper(state_file=paths.state_dir() / "paper_add.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"], market="JP")
    now = {"t": None}
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book_add.json", paper=True, respect_halt=False, check_clock=False,
                         clock=lambda: now["t"], manual_tag="pa")
    k0 = int(eng.gidx.searchsorted(start))
    eng.prime(k0)
    k_add = 15
    for k in range(k0, 22):
        if k == k_add:
            with open(MO.requests_path("pa"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 300, "id": "M-add",
                                    "at": "x"}) + "\n")
        now["t"] = dt.datetime.combine(next_trading_day(eng.gidx[k].date()), dt.time(7, 40), tzinfo=JST)
        ux.morning([k])
        assert not ux.blocked
        assert {t: int(p.qty) for t, p in b.positions().items()} == {
            t: int(p.shares) for t, p in eng.st.pos.items()} | {t: int(u) for t, u in eng.st.core_units.items() if u}
    assert ux.book["manual"]["items"]["M-add"]["status"] == "done" and eng.st.pos["A.T"].shares == 300
    ref = make()                                                         # 引擎：同一个决策日放进同一笔加仓计划
    ref.prime(k0)

    def inject(i):
        if i == k_add:
            ref.st.add_plan["A.T"] = [float(ref.A.close[i, ref.col["A.T"]]), 100, str(ref.gidx[i].date()), "M-add"]
    ref.pre_decide_fn = inject
    for k in range(k0, 22):
        ref.step(k)
    assert ref.st.pos["A.T"].shares == 300 and abs(ref.st.pos["A.T"].entry_px - eng.st.pos["A.T"].entry_px) < 1e-9
    assert ref.st.core_units == eng.st.core_units and abs(ref.st.cash_jpy - eng.st.cash_jpy) < 1e-6
    assert ref.st.core_trades == eng.st.core_trades


@pytest.mark.parametrize("seed", [7, 11, 23])
def test_paper_executor_with_periodic_adds_equals_engine(seed):
    """260 天的合成行情：每 15 天给拿着的第一只票加 1 个单元 —— 模拟账户执行器与引擎（同一决策日放进同样的加仓计划）逐日权益完全相同。"""
    from test_live_unified import _synth
    make, start = _synth(seed)
    eng = make()
    eng.st.cash_jpy = 5_000_000.0                                        # ¥100 万时多一个单元就超过单只上限 34%（加仓全被挡）→ 用 ¥500 万
    b = _MemPaper(state_file=paths.state_dir() / f"pp{seed}.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"], market="JP")
    now = {"t": None}
    ux = UnifiedExecutor(eng, b, paths.state_dir() / f"bp{seed}.json", paper=True, respect_halt=False, check_clock=False,
                         clock=lambda: now["t"], manual_tag=f"s{seed}", persist=False)
    k0 = int(eng.gidx.searchsorted(start))
    eng.prime(k0)
    planned, n_req = {}, 0
    for k in range(k0, len(eng.gidx)):
        held = [t for t in eng.st.pos if t not in eng.st.pending_exit]
        if (k - k0) % 15 == 7 and held:
            t = held[0]
            with open(MO.requests_path(f"s{seed}"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"kind": "adjust", "ticker": t, "unit": "shares", "value": eng.st.pos[t].shares + 100,
                                    "id": f"M-{seed}-{k}", "at": str(k)}) + "\n")
            n_req += 1
        now["t"] = dt.datetime.combine(next_trading_day(eng.gidx[k].date()), dt.time(7, 40), tzinfo=JST)
        ux.morning([k])
        assert not ux.blocked
        if eng.st.add_plan:
            planned[k] = {t: list(v) for t, v in eng.st.add_plan.items()}
    done = [it for it in ux.book["manual"]["items"].values() if it.get("status") == "done"]
    assert n_req >= 10 and len(planned) >= 3 and done                       # 真的加过仓（有的被上限 / 现金挡掉是正常的）
    ref = make()
    ref.st.cash_jpy = 5_000_000.0
    ref.prime(k0)
    ref.pre_decide_fn = lambda i: ref.st.add_plan.update({t: list(v) for t, v in planned.get(i, {}).items()})
    for k in range(k0, len(ref.gidx)):
        ref.step(k)
    ex = [h[1] for h in eng.st.history]
    rf = [h[1] for h in ref.st.history]
    assert len(ex) == len(rf) and max(abs(a - c) for a, c in zip(ex, rf)) == 0.0
    assert eng.st.trades == ref.st.trades and eng.st.core_trades == ref.st.core_trades
