"""整合复核（2026-10-16，事后）：交易页 / 持仓 / 能买卖几次 / 文档几处对不上。
- 撤单时立花回「已经失效 / 被拒」的单（GONE）：交易页收进「已结束」、不算数字；手动买入指令跟着结束；「持仓」不再算它在等成交。
- 立花成交快照里已经全部成交、账本还是 SENT 的单：交易页「已成交（快照）」、没有撤单按钮、不算数字；确认框按已花钱算。
- 核心 ETF「固定口数…」这条路与执行器 fix_prep 同一个判断（今天买进 / 今天已有单只挡闲置资金比例那条路）。
- 已有自己一行的固定口数不再在最上面重复提醒；「…下单照它下单」不重复；模拟账户的「pnl=」写成「已实现约 −¥」。
- 文档：sim_changes / HANDOFF 的几句。"""
import datetime as dt
import json
import re
from pathlib import Path

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak import trade_room as TR
from qbreak.calendar_jp import JST

from test_cancel_group import (BUY, SELL, D, T9, _Gone, _at_exch, _attrs, _btn, _gbook, _no_sleep, _ord,  # noqa: F401
                               _run_req, _tbook, _three)
from test_trade_room import _bk, _o, _room
from test_trade_today import _parts

ROOT = Path(__file__).resolve().parents[1]
T13 = dt.datetime(2026, 10, 15, 13, 0, tzinfo=JST)


def _live(b, now):
    return panel._trade_live(b, MO.unseen("tachibana", b), now, "tachibana")


# ───────────── 立花那边已经失效 / 被拒（GONE） ─────────────
def test_gone_order_moves_to_ended_and_is_not_counted():
    p = _tbook(_three())
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)
    _run_req(p, _Gone("EXPIRED", 0))
    b = json.loads(p.read_text(encoding="utf-8"))
    o = next(x for x in b["orders"] if x["cid"] == BUY)
    assert o["status"] == "SENT" and LO.is_gone(o)
    t1 = T9 + dt.timedelta(minutes=2)
    tl = _live(b, t1)
    assert tl["split"]["orders"][BUY] == "ended" and tl["n"] == 2              # 以前 3（失效的买单照算）
    ol = LO.outlook(b, MO.unseen("tachibana", b), t1, tag="tachibana", halt=False)
    assert ol["orders"][BUY]["state"] == "done"
    assert BUY not in [x["cid"] for x in LO.held_now(b, "tachibana", now=t1)["pending"]]
    top, _later, ended = _parts(panel.render("tachibana", "t" * 40, t1))
    assert "<b>买 1482" not in top and "<b>买 1482" in ended


def test_gone_partial_fill_counts_the_fill_not_the_rest():
    p = _tbook(_three())
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)
    _run_req(p, _Gone("EXPIRED", 100))
    b = json.loads(p.read_text(encoding="utf-8"))
    pj = LO.held_now(b, "tachibana", now=T9 + dt.timedelta(minutes=2))
    assert BUY not in [x["cid"] for x in pj["pending"]]                        # 以前还剩 578 口「在等成交」
    assert [f["qty"] for f in pj["fills"] if f["cid"] == BUY] == [100]


def test_gone_manual_buy_instruction_ends():
    mb, mf = f"U{D}-BUY-7203.T-N1", f"U{D}-SELL-6758.T-N1"
    b = _gbook(sell="FILLED", buy="FILLED")
    b["orders"] += [_ord(mb, "7203.T", "BUY", kind="stock", qty=100, reason="manual_buy", fund_src=[mf], broker_id="B1"),
                    _ord(mf, "6758.T", "SELL", kind="stock", qty=100, reason="manual_fund", status="FILLED", filled_qty=100,
                         filled_px=3000.0)]
    b["state"]["pos"] = {"6758.T": {"shares": 100, "entry_px": 2900.0, "entry_date": "2026-09-01", "stop_px": 2700.0, "last_close": 3000.0}}
    b["manual"]["items"]["M1"] = {"id": "M1", "kind": "buy", "ticker": "7203.T", "status": "placed", "now": True,
                                  "at": "2026-10-15T09:20:00+09:00", "fund": "split"}
    b["manual"]["buys"] = {"7203.T": {"id": "M1"}}
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": mb}, clock=lambda: T9)
    _run_req(p, _Gone("EXPIRED", 0))
    b = json.loads(p.read_text(encoding="utf-8"))
    tl = _live(b, T9 + dt.timedelta(minutes=2))
    assert tl["split"]["orders"][mb] == "ended" and tl["split"]["items"]["M1"] == "ended" and tl["n"] == 0


# ───────────── 立花成交快照里已经成交的单 ─────────────
def _snap(fills):
    paths.out_dir().mkdir(parents=True, exist_ok=True)
    (paths.out_dir() / "broker_snapshot_tachibana.json").write_text(json.dumps({
        "fills_at": "2026-10-15T11:35:00+09:00", "fills_day": "2026-10-15", "fills": fills}), encoding="utf-8")


def _gb_exch():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    _at_exch(b, SELL, "S1")
    return b


def test_snapshot_filled_orders_are_done_without_cancel_buttons():
    b = _gb_exch()
    _snap([{"cid": SELL, "filled_qty": 4110, "avg_px": 243.0}, {"cid": BUY, "filled_qty": 678, "avg_px": 1490.0}])
    _tbook(b)
    html = panel.render("tachibana", "t" * 40, T13)
    top, _later, ended = _parts(html)
    assert f"data-cid='{SELL}'" not in html and f"data-cid='{BUY}'" not in html   # 以前两笔都有「撤单」
    assert ended.count(LO.SNAP_DONE) == 2 and "已下单（等成交）</span>" not in top
    tl = _live(b, T13)
    assert tl["n"] == 0 and set(tl["split"]["orders"].values()) == {"ended"}
    ol = LO.outlook(b, (), T13, tag="tachibana", halt=False, instr=False)
    assert {r["cls"] for r in ol["orders"].values()} == {"snapfill"}
    assert LO.cancel_why(LO.snap_book(b, "tachibana", T13)["orders"][1], b, T13, False) == f"{LO.SNAP_DONE}，不用撤"
    assert LO.cancel_why(b["orders"][1], b, T13, False) is None             # 账本本身（执行器 / 撤单引擎）照旧：自己查立花


def test_snapshot_partial_fill_stays_live_and_counts_as_spent():
    b = _gb_exch()
    _snap([{"cid": BUY, "filled_qty": 300, "avg_px": 1490.0}])
    _tbook(b)
    top, _later, _ended = _parts(panel.render("tachibana", "t" * 40, T13))
    assert f"data-cid='{BUY}'" in top and "成交 300/678（快照，对账前的预计）" in top
    a = _attrs(_btn(top, SELL))
    assert "· 撤：卖 1545" not in a.get("glist", "")                        # 买单已经花了钱：整组撤单不撤卖单
    assert _live(b, T13)["split"]["orders"][BUY] == "today"


def test_paper_book_is_not_touched_by_snap_book():
    b = {"broker": "Paper", "state": {"last_date": D}, "orders": [{"cid": "x", "status": "SENT", "decided_on": D}]}
    assert LO.snap_book(b, "paper", T13) is b


# ───────────── 核心 ETF：固定口数这条路 ─────────────
def test_core_bought_today_can_still_change_by_fixed_units():
    b = _bk(cores={}, orders=[_o("1545.T", "BUY", qty=50, px=2400.0, kind="core")])
    r = _room(b)["per_ticker"]["1545.T"]
    assert r["sell"]["n"] == 1 and r["sell"]["max_qty"] == 50 and r["sell"]["via"].startswith("「固定口数…」")
    assert r["buy"]["n"] == 1 and r["buy"]["via"] == "「固定口数…」"
    assert any(w.startswith("「卖出全部」/「调仓…」（换算成闲置资金比例）今天不行") for w in r["sell"]["why"])


def test_core_with_an_open_order_waits_on_both_routes():
    b = _bk(orders=[_o("1545.T", "SELL", status="SENT", qty=50, px=2400.0, kind="core", filled=0)])
    r = _room(b)["per_ticker"]["1545.T"]
    assert r["sell"]["n"] == 0 and r["sell"]["short"] == "今天已有单"
    assert any("「固定口数…」也先等" in w for w in r["sell"]["why"])


def test_core_bought_and_sold_today_blocks_fixed_units_too():
    b = _bk(orders=[_o("1545.T", "SELL", qty=50, px=2400.0, kind="core", at="09:10"),
                    _o("1545.T", "BUY", qty=50, px=2400.0, kind="core", at="09:40")])
    r = _room(b)["per_ticker"]["1545.T"]
    assert r["buy"]["n"] == 0 and any("今天已经买过也卖过（差金決済）" in w for w in r["buy"]["why"])


# ───────────── 固定口数提醒不重复 / 「照它下单」/ pnl ─────────────
def test_fixed_reminder_not_repeated_when_the_fix_has_its_own_row():
    from test_fund_src import _dict_book
    b = _dict_book(buy_status="CANCELLED")
    b["manual"]["core_fix"] = {"1482.T": 679}
    b["core_rule"]["fix_applied"] = {"1482.T": 678}
    _tbook(b)
    now = dt.datetime(2026, 10, 15, 10, 30, tzinfo=JST)
    tl = _live(b, now)
    assert BUY in tl["fix"] and tl["split"]["orders"][BUY] == "ended"
    assert any(x["ref"] == "fix:1482.T" for _z, x in tl["split"]["extra"])     # 那只固定口数自己有一行
    assert tl["split"]["notes"] == []                                        # 以前同一句又写在最上面
    assert "下单照它下单" not in tl["fix"][BUY]


def test_fix_when_do():
    assert LO.fix_when_do("马上（盘中）按现价下单") == "马上（盘中）按现价下单"
    assert LO.fix_when_do("马上（盘中）按现价下单（模拟账户当场成交）") == "马上（盘中）按现价下单（模拟账户当场成交）"
    assert LO.fix_when_do("今天早上的决策（07:40）读到 → 今天 09:00 开盘（寄付）").endswith("开盘（寄付）")
    assert LO.fix_when_do("10/19 07:40 的决策 → 10/19 09:00 开盘") == "10/19 07:40 的决策 → 10/19 09:00 开盘照它下单"


def test_paper_pnl_note_is_written_in_yen():
    assert panel._pnl_txt("盘中，成交 4,110 @ ¥237.53 · pnl=-18,535") == "盘中，成交 4,110 @ ¥237.53 · 已实现约 −¥18,535"
    assert panel._pnl_txt("pnl=1,200") == "已实现约 ¥1,200"
    b = _dict_book_paper()
    rows, _m = panel._order_rows(b, T13, True, [], tag="paper")
    h = "".join(x for _c, x in rows)
    assert "pnl=" not in h and "已实现约 −¥18,535" in h


def _dict_book_paper():
    from test_fund_src import _dict_book
    b = _dict_book(sell_status="FILLED")
    b["broker"] = "Paper"
    b["orders"][0].update(filled_qty=4110, filled_px=237.53, note="pnl=-18,535")
    return b


# ───────────── 文档 ─────────────
def test_docs_say_what_changed():
    sc = (ROOT / "var" / "sim_changes.md").read_text(encoding="utf-8")
    assert "## 2026-10-16 工程（用户要求；页面的排法 + 执行器对账一处〔复核 8，事后〕）：「交易」只显示今天要成交的单" in sc
    assert "只改页面的排法与几句说明" not in sc
    ho = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
    assert "工程，只改页面的排法，不改规则 / 判断 / 数字的口径" not in ho
    row = next(ln for ln in ho.splitlines() if ln.startswith("| 例行任务今天跑了吗"))
    assert "有没有卡住的运行" in row and "routines/README.md「限制」" in row
    row = next(ln for ln in ho.splitlines() if ln.startswith("| 09:30 自检 / 每天的推送"))
    assert "写了撤单而面板自动下单暂停、单还挂着" in row
