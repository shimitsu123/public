"""「手动卖出后不自动买回」的解除（2026-10-13 审计）：解除 / 「恢复按规则」= 记 lift_from，下一次决策（交易日 07:40）起才不挡、
补跑的旧 K 线不追溯、到期按 K 线；重复的解除拒绝、还没读的可以撤回；按批（同一次提交）解除、设定换了的跳过；
解除之后手动买入不被上一次决策的结果挡；面板 / 命令行的文字说清楚「不会买回、也不马上买」。"""
import datetime as dt
import json
from types import SimpleNamespace

from qbreak import manual_orders as MO
from qbreak import panel, suggest
from qbreak.calendar_jp import JST, next_trading_day

from test_fund_all import _book4, _reqs
from test_manual_buy import _write
from test_manual_orders import TAG, _Run, _sell_req
from test_panel import AT, _book, _card, _sm

D = dt.date


def _blk(until="2026-10-20", bid="M-a", **kw):
    return {"until": until, "since": "2026-10-01", "id": bid, **kw}


def _dict_book(blocks, pos=None, items=None, **man):
    return {"state": {"pos": pos or {}, "pending_exit": {}, "cash_jpy": 500_000.0, "history": [["2026-10-05", 1_000_000.0]]},
            "manual": {"items": items or {}, "blocks": blocks, **man}}


# ────────── ① 日子：从哪一次决策起 / 最早哪天买回 ──────────
def test_lift_day_next_decision_and_rebuy_day():
    assert MO.lift_day("2026-10-06T07:00:00+09:00") == D(2026, 10, 6)         # 交易日 07:40 之前写 → 当天 07:40 的决策
    assert MO.lift_day("2026-10-06T07:40:00+09:00") == D(2026, 10, 7)         # 07:40 之后 → 下一个交易日
    assert MO.lift_day("2026-10-06T08:00:00+09:00") == D(2026, 10, 7)
    assert MO.lift_day("2026-10-10T06:00:00+09:00") == D(2026, 10, 13)        # 周六（周一体育之日）→ 周二
    assert MO.lift_day("2026-10-05T23:10:00+00:00") == D(2026, 10, 7)         # UTC → JST 10/06 08:10
    assert MO.lift_day("坏", clock=lambda: dt.datetime(2026, 10, 6, 7, 0, tzinfo=JST)) == D(2026, 10, 6)
    assert MO.rebuy_day("2026-10-28") == MO.add_trading_days(D(2026, 10, 28), 2) and MO.rebuy_day(None) is None
    assert MO.block_text(_blk("2026-10-28")) == f"到 2026-10-28（最早 {MO.rebuy_day('2026-10-28'):%m/%d} 开盘才可能买回）"
    assert MO.block_text(_blk(None)) == "一直，直到解除"
    assert MO.block_text(_blk(lift_from="2026-10-14")) == "解除中（10/14 07:40 的决策起不挡）"


# ────────── ② 执行器：按 K 线挡、lift_from、手动的口径 ──────────
def test_block_reason_by_bar_lift_from_and_manual_mode():
    m = MO.Manual(_dict_book({"A.T": _blk()}), TAG)
    assert m.block_reason("A.T", D(2026, 10, 20)) == "手动卖出后不自动买回（到 2026-10-20）"   # until 那根 K 线也挡
    assert m.block_reason("A.T", D(2026, 10, 21)) is None
    w = m.block_reason("A.T", D(2026, 10, 20), manual=True)
    assert "规则和手动都不买" in w and "「解除」/「恢复按规则」" in w
    m.m["blocks"]["A.T"]["lift_from"] = "2026-10-14"
    assert m.block_reason("A.T", D(2026, 10, 9)) is not None                  # 10/09 的 K 线在 10/13 成交：还挡（补跑不追溯）
    assert m.block_reason("A.T", D(2026, 10, 13)) is None                     # 10/13 的 K 线在 10/14 成交：不挡
    assert m.block_reason("A.T", D(2026, 10, 9), manual=True) is None         # 手动买入：已经解除就不挡


def test_prune_blocks_by_bar_not_clock():
    m = MO.Manual(_dict_book({"A.T": _blk(), "B.T": _blk(bid="M-b", lift_from="2026-10-14"), "C.T": _blk(None, "M-c")}), TAG)
    assert m.prune_blocks(None) == [] and m.prune_blocks("2026-10-09") == [] and set(m.m["blocks"]) == {"A.T", "B.T", "C.T"}
    ev = m.prune_blocks("2026-10-13")                                         # 下一根 K 线在 10/14 成交 → 解除生效
    assert ev == [("info", "B 的不自动买回已解除（10/14 07:40 的决策起）：之后出买入信号规则可能买")]   # 文字写 label（假代码没名字：只写代码） and "B.T" not in m.m["blocks"]
    assert m.prune_blocks("2026-10-20") == [] and "A.T" in m.m["blocks"]       # until 那根还挡：不去掉
    ev = m.prune_blocks("2026-10-21")
    assert ev == [("info", "A 的不自动买回到期（到 2026-10-20）：之后出买入信号规则可能买回")] and set(m.m["blocks"]) == {"C.T"}


def test_ingest_records_lift_from_not_pop_and_refuses_duplicates_and_stale_ids():
    book = _dict_book({"A.T": _blk(), "B.T": _blk(bid="M-b")})
    _write({"kind": "unblock", "ticker": "A.T", "source": "test", "id": "M-u1", "at": "2026-10-06T08:00:00+09:00"})
    _write({"kind": "unblock", "ticker": "A.T", "source": "test", "id": "M-u2", "at": "2026-10-06T08:01:00+09:00"})
    _write({"kind": "unblock", "ticker": "B.T", "block_id": "M-old", "source": "test", "id": "M-u3", "at": "2026-10-06T08:02:00+09:00"})
    _write({"kind": "unblock", "ticker": "C.T", "source": "test", "id": "M-u4", "at": "2026-10-06T08:03:00+09:00"})
    m = MO.Manual(book, TAG)
    m.ingest()
    it = m.m["items"]
    assert m.m["blocks"]["A.T"]["lift_from"] == "2026-10-07" and m.m["blocks"]["A.T"]["lift_id"] == "M-u1"   # 读到不去掉
    assert it["M-u1"]["status"] == "done" and "10/07 07:40 的决策起不挡（不会买回，也不马上买" in it["M-u1"]["msg"]
    assert it["M-u2"]["status"] == "rejected" and "已经在解除" in it["M-u2"]["msg"]
    assert it["M-u3"]["status"] == "rejected" and "换成别的设定" in it["M-u3"]["msg"] and "lift_from" not in m.m["blocks"]["B.T"]
    assert it["M-u4"]["status"] == "rejected" and "本来就没有" in it["M-u4"]["msg"]
    assert m.block_reason("A.T", D(2026, 10, 5)) is not None and m.block_reason("A.T", D(2026, 10, 6)) is None


def test_executor_unblock_waits_for_next_decision_then_prunes():
    r = _Run([1000.0] * 40, entry=(10, 22), bear_all=True)
    r.until(14)
    _sell_req(r)
    r.day()
    r.day()                                                                   # 卖出成交 → 不买回
    assert "A.T" in r.ux.book["manual"]["blocks"]
    k = r.k
    _write({"kind": "unblock", "ticker": "A.T", "source": "test", "id": "M-unb", "at": r.at(k, 6, 0).isoformat()})
    r.day()                                                                   # 读到：从这次决策起不挡（第 k 根 = 这次的决策）
    it = r.item("M-unb")
    assert it["status"] == "done" and f"{next_trading_day(r.eng.gidx[k].date()):%m/%d} 07:40 的决策起不挡" in it["msg"]
    assert r.ux.manual.block_reason("A.T", r.eng.gidx[k]) is None
    assert r.ux.manual.block_reason("A.T", r.eng.gidx[k - 1]) is not None or "A.T" not in r.ux.book["manual"]["blocks"]
    r.day()
    assert "A.T" not in r.ux.book["manual"]["blocks"]
    assert any("A 的不自动买回已解除" in str(e.get("msg")) for e in r.ux.book.get("events") or [])


# ────────── ③ 写之前的检查：重复 / 过时 / 撤回 ──────────
def test_check_refuses_duplicate_stale_and_lifting_unblock():
    book = _dict_book({"7203.T": _blk(bid="M20261001-080000-sell-7203")})
    n = MO.normalize
    assert MO.check(n({"kind": "unblock", "ticker": "7203"}), book, TAG) is None
    assert "页面过时" in MO.check(n({"kind": "unblock", "ticker": "7203", "block_id": "M-other"}), book, TAG)
    MO.append(TAG, {"kind": "unblock", "ticker": "7203"})
    assert f"已经在解除：等执行器读（{MO.next_decision()}）" in MO.check(n({"kind": "unblock", "ticker": "7203"}), book, TAG)   # 带日期（UI F5，2026-10-16）
    assert MO.lifting(TAG, book) == {"7203.T"}
    book2 = _dict_book({"7203.T": _blk(lift_from="2026-10-07")})
    assert "已经在解除（解除中（10/07 07:40" in MO.check(n({"kind": "unblock", "ticker": "7203"}), book2, TAG)


def test_cancel_unread_unblock_is_honoured_and_uncancel_duplicate_refused():
    book = _dict_book({"7203.T": _blk()})
    u = MO.append(TAG, {"kind": "unblock", "ticker": "7203"}, clock=lambda: AT)
    ok, msg, c = MO.cancel_request(TAG, book, u["id"], now=AT, source="test")
    assert ok, msg
    assert MO.lifting(TAG, book) == set() and MO.check(MO.normalize({"kind": "unblock", "ticker": "7203"}), book, TAG) is None
    MO.append(TAG, {"kind": "unblock", "ticker": "7203"}, clock=lambda: AT)    # 撤回之后又点了一次解除
    assert "已经有别的解除在等执行器读" in MO.check({"kind": "uncancel", "target": c["id"]}, book, TAG, now=AT)
    m = MO.Manual(book, TAG)
    m.ingest()
    assert m.m["items"][u["id"]]["status"] == "cancelled" and m.m["items"][u["id"]]["msg"] == "执行器读到之前就撤回了"
    assert m.m["blocks"]["7203.T"]["lift_id"] != u["id"]                      # 撤回的那条不生效；后来那条生效


# ────────── ④ 按批：同一次提交一批、设定换了的跳过 ──────────
def test_batch_blocks_one_entry_per_batch_with_member_state():
    bl = {"A.T": _blk(bid="M-a", fund_for="X.T", batch_at="2026-10-05T06:00:00+09:00"),
          "B.T": _blk("2026-10-22", bid="M-b", fund_for="X.T", batch_at="2026-10-05T06:00:00+09:00"),
          "C.T": _blk(bid="M-c", fund_for="X.T", batch_at="2026-10-08T06:00:00+09:00"),
          "D.T": _blk(bid="M-d")}
    book = _dict_book(bl, pos={"B.T": {"shares": 100}})
    book["state"]["pending_exit"] = {"B.T": "manual"}
    g = MO.batch_blocks(book)
    assert [(x["x"], x["at"][:10], [m["t"] for m in x["members"]]) for x in g] == [
        ("X.T", "2026-10-05", ["A.T", "B.T"]), ("X.T", "2026-10-08", ["C.T"])]   # 两次换成同一只：分两批
    assert g[0]["until"] == "2026-10-22" and [m["state"] for m in g[0]["members"]] == ["sold", "卖出中"]
    assert [m["id"] for m in g[0]["members"]] == ["M-a", "M-b"]


def test_panel_batch_submit_skips_stale_and_refuses_when_none_match():
    b = _book4()
    b["manual"]["blocks"] = {"7203.T": _blk("2026-11-02", "M-x-a", fund_for="6501.T", batch_at="2026-10-05T06:00:00+09:00"),
                             "6758.T": _blk("2026-11-02", "M-x-b", fund_for="6501.T", batch_at="2026-10-05T06:00:00+09:00")}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    ok, msg, _ = panel.submit({"book": "paper", "kind": "unblock", "tickers": ["7203.T:M-old"]}, AT)
    assert not ok and "换成别的设定" in msg and not _reqs("unblock")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "unblock", "tickers": ["6758.T:M-x-b", "7203.T:M-old", "6758.T:M-x-b"]}, AT)
    assert ok and "解除 6758 ソニーグループ 的不自动买回（不会买回，也不马上买；指令" in msg and "没写：7203 トヨタ自動車 的不自动买回已经换成别的设定" in msg
    assert msg.endswith(f"→ {MO.next_decision(AT)}")
    assert [(r["ticker"], r.get("block_id")) for r in _reqs("unblock")] == [("6758.T", "M-x-b")]
    ok, msg, _ = panel.submit({"book": "paper", "kind": "unblock", "tickers": ["6758.T:M-x-b"]}, AT)
    assert not ok and "已经在解除" in msg                                      # 重复的不写


def test_panel_single_unblock_message_and_block_id():
    _book(manual={"items": {}, "blocks": {"7203.T": _blk("2026-11-02", "M20261005-060000-sell-7203")}})
    _sm()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "unblock", "ticker": "7203", "block_id": "M20261005-060000-sell-7203"}, AT)
    assert ok and rec["block_id"] == "M20261005-060000-sell-7203"
    assert msg == f"已写：解除 7203 トヨタ自動車 的不自动买回（不会买回，也不马上买；指令 {rec['id']}）→ {MO.next_decision(AT)}"
    ok, msg, _ = panel.submit({"book": "paper", "kind": "unblock", "ticker": "7203"}, AT)
    assert not ok and "已经在解除" in msg


# ────────── ⑤ 面板：卡片、确认、等执行器读、撤回 ──────────
def test_panel_blocks_card_confirm_and_waiting_rows():
    b = _book4(core_pct=0.0, core_pause={"since": "2026-10-05"})
    b["manual"]["items"] = {
        "M-x-a": {"id": "M-x-a", "kind": "sell", "ticker": "7203.T", "fund_for": "6501.T", "batch": "all", "status": "done",
                  "at": "2026-10-05T06:00:00+09:00"},
        "M-x-b": {"id": "M-x-b", "kind": "sell", "ticker": "6758.T", "fund_for": "6501.T", "batch": "all", "status": "done",
                  "at": "2026-10-05T06:00:00+09:00"}}
    b["manual"]["blocks"] = {"7203.T": _blk("2026-11-02", "M-x-a"), "6758.T": _blk("2026-11-02", "M-x-b"),
                             "8306.T": _blk("2026-11-01", "M-y")}
    del b["state"]["pos"]["7203.T"]                                           # 7203 已卖出；6758 还拿着（等卖出）
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    html = panel.render("paper", "t" * 40, AT)
    rb = MO.rebuy_day("2026-11-02")
    assert f"到 2026-11-02（最早 {rb:%m/%d} 开盘才可能买回）" in html and "（10/05）卖出的" in html and "ソニーグループ（等卖出）" in html
    i = html.index("data-act='unblock-batch'")
    btn = html[i:html.index(">恢复按规则<", i)]
    assert "data-ids='7203.T:M-x-a,6758.T:M-x-b'" in btn or "data-ids='6758.T:M-x-b,7203.T:M-x-a'" in btn
    for s in ("只解除「全部换成 6501", "（6758 ソニーグループ、7203 トヨタ自動車）。", "不会把它们买回来，也不会马上买。", "下一次决策（交易日 07:40）起生效，规则重新判断",
              "MACD 金叉", "已经判断过的信号不会再用", "现在空 ", "账本现金 ¥", "决算前",
              "闲置资金 ETF 仍停买（0%，要另外点「确认买入」）", "这批取消的固定口数不会恢复", "还没成交的卖出（6758 ソニーグループ）不会撤"):
        assert s in btn, s
    assert "data-act='unblock' data-t='8306.T' data-id='M-y'" in html and "不会把它买回来" in html
    assert "只解除这一批（不买回、也不马上买）；闲置资金 ETF 不跟着恢复（仍停买）" in html
    MO.append("paper", {"kind": "unblock", "ticker": "8306", "block_id": "M-y"}, clock=lambda: AT)
    MO.append("paper", {"kind": "core", "pct": 50}, clock=lambda: AT)
    html = panel.render("paper", "t" * 40, AT)
    assert "data-act='unblock' data-t='8306.T'" not in html and "解除中（下一次决策起）" in html
    assert html.count("<span class='chip'>等执行器读</span>") == 2 and "<span class='chip'>等下单</span>" not in html
    assert "data-act='cancel' data-kind='unblock'" in html and ">撤回</button>" in html
    assert "a==='cancel' && d.kind==='unblock'" in panel._JS and "撤回之后不解除" in panel._JS and "block_id:d.id" in panel._JS


def test_suggest_and_auto_buy_card_for_manual_block():
    _book(pos={}, manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "blocks": {"6501.T": _blk("2026-10-07", "M-h")}})
    row = {"ticker": "6501.T", "code": "6501", "name": "日立", "status": "watch", "signal": False, "close": 3500.0,
           "near": {"where": "below_up", "days": 3}, "rule": {"state": "none"},
           "buy": {"block": "手动卖出后不自动买回（到 2026-10-07）", "block_kind": "manual", "warn": [], "lot": 100, "px": 3500.0,
                   "em": 1.0, "rule_shares": 100}}
    row2 = {**row, "near": {"where": "below_up", "days": 1}}
    _sm([row2])                                                             # 估计 10/06 金叉 ≤ 到期 10/07：自动买那张卡不列 → 在建议的股票里
    html = panel.render("paper", "t" * 40, AT)
    assert "手动卖出后不买回（可在「交易」解除）：到 2026-10-07" in _card(html, "suggest") and "资格检查：手动" not in html
    assert "6501" not in _card(html, "autobuy")
    _sm([row])                                                              # 估计 10/08 金叉 > 到期 10/07：自动买那张卡列（建议的股票不重复列）
    html = panel.render("paper", "t" * 40, AT)
    assert "手动卖出后不买回（可在「交易」解除）：到 2026-10-07" in _card(html, "autobuy") and "6501" not in _card(html, "suggest")
    book = json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())
    h = panel._auto_buy_card({"asof": "2026-10-05", "rows": [row]}, book, "paper", 1_000_000)
    assert "6501" in h and "10/07 解除后" in h                                # 估计 10/08 金叉 > 到期 10/07：还列
    assert "6501" not in panel._auto_buy_card({"asof": "2026-10-05", "rows": [row2]}, book, "paper", 1_000_000)
    assert MO.check(MO.normalize({"kind": "buy", "ticker": "6501"}), book, "paper", sm={"suggest": {"rows": [row]}}).startswith("6501 日立製作所 不能买")
    MO.append("paper", {"kind": "unblock", "ticker": "6501"}, clock=lambda: AT)
    why = MO.check(MO.normalize({"kind": "buy", "ticker": "6501"}), book, "paper", sm={"suggest": {"rows": [row]}})
    assert "不能买" not in str(why)                                           # 在解除：上一次决策的结果不再挡手动买入
    html = panel.render("paper", "t" * 40, AT)                              # 在解除：自动买那张卡列（「解除中」），点开的一行写着
    assert "「不自动买回」在解除：下一次决策（交易日 07:40）起生效（规则出买入信号才买；手动买入可以写）" in _card(html, "autobuy")
    assert "解除中" in panel._auto_buy_card({"asof": "2026-10-05", "rows": [row2]}, book, "paper", 1_000_000)
    assert suggest._why_not(SimpleNamespace(st=None, cfg=None), "6501.T", 0, 1.0, "x", None, gate_kind="manual", until=None) == "手动卖出后不买回（可在「交易」解除）：一直，直到解除"


def test_entry_why_uses_manual_wording_and_lifted_block():
    m = MO.Manual(_dict_book({"A.T": _blk()}), TAG)
    gidx = [dt.datetime(2026, 10, 9)]
    eng = SimpleNamespace(gidx=gidx, entry_block_fn=None, _entry_mult=lambda t, i: 1.0,
                          manual_gate_fn=lambda t, i, manual=False: m.block_reason(t, gidx[i], manual=manual))
    eng.entry_gate_fn = lambda t, i: eng.manual_gate_fn(t, i)
    w = MO.entry_why(eng, "A.T", 0)
    assert "规则和手动都不买" in w and "先在「交易」点「解除」" in w
    m.m["blocks"]["A.T"]["lift_from"] = "2026-10-14"
    assert eng.entry_gate_fn("A.T", 0) is not None and MO.entry_why(eng, "A.T", 0) is None   # 规则这根还挡；手动已经可以买
    eng.entry_gate_fn = lambda t, i: "资格检查不过"
    assert MO.entry_why(eng, "A.T", 0) == "资格检查不过"


def test_cli_list_and_unblock_note(capsys):
    import run
    _book(manual={"items": {}, "blocks": {"7203.T": _blk("2026-11-02", "M-z")}})
    assert run.main(["manual", "unblock", "7203", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert f"不会买回、也不马上买 → {MO.next_decision()}" in out
    assert run.main(["manual", "unblock", "7203", "--broker", "paper"]) == 2
    run.main(["manual", "list", "--broker", "paper"])
    out = capsys.readouterr().out
    assert "解除不买回 7203 トヨタ自動車 → 等执行器读" in out and "→ 等下单" not in out          # 解除不是单（2026-10-13）
