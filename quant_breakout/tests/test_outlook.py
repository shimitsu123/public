"""「今天会发生什么」只有一处判断（live_ops.outlook；D5）+ 核心单的来源标记（D7）；2026-10-15。
事故（模拟账户，真实状态）：07:40 照「固定 1482 678 口」排了「卖 1545 4,110 口（寄付）→ 买 1482 678 口（现金 191.68 円不够 → 等开盘后）」，
08:05 撤了卖单 → 买单开盘时一定买不起，可 09:30 自检照样「✓ 通过」、07:41 的推送照写「开盘后按始値检查、减股再下」、
08:48 写的固定 679 口整天没人读也没人说；推送里也看不出那组换仓来自你写的固定口数。
现在：交易页角标 / 行、自检（两个账本）、执行器汇总、撤单推送、面板的 U4（过了该下的时刻 10 分钟没有执行路径）与 15:25 之后的汇总
都照同一个 outlook；交易问题的推送标题以「★ 交易」开头、warn、去重键不含金额；核心单带来源（rule / core_fix / fix_fund / manual_core）。"""
import datetime as dt
import json
from types import SimpleNamespace

import pytest

import run
from qbreak import live_ops as LO
from qbreak import live_unified as LU
from qbreak import manual_orders as MO
from qbreak import notify, panel, paths, watchdog
from qbreak.calendar_jp import JST
from qbreak.live_unified import daily_text, order_tail, trade_wont

from test_core_etf_restore import _morning, _paper2, _w
from test_corefix_now import KINDS, TIMES, _at0, _base, _close_day, _disk, _open_day
from test_fund_src import _low_cash, _one, _tachi2, _tday
from test_panel import _book1015

BUY, SELL = "U2026-10-14-BUY-1482.T", "U2026-10-14-SELL-1545.T"
D15 = dt.date(2026, 10, 15)                                 # 木曜：成交日（决策日 10/14）
LAB_BUY = "买 1482 对冲版美国 7〜10 年国债：678 口"


def _t(hh: int, mm: int = 0, d: dt.date = D15) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(hh, mm), tzinfo=JST)


def _incident(tag: str, **kw) -> dict:
    """2026-10-15 的账本（现金 191.68 円、1545 ×4,110、卖 1545 已撤、买 1482 678 口 DEFERRED）+ 08:48 写的固定 679 口（还没读）。"""
    b = _book1015(tag, cash=191.68, **kw)
    MO.append(tag, {"kind": "corefix", "ticker": "1482.T", "units": 679, "source": "panel"}, clock=lambda: _t(8, 48))
    return b


class _Rec:
    def __init__(self):
        self.sent = []

    def send(self, title, text, level="info", resend=False):
        self.sent.append((title, text, level))
        return {"webhook": True}

    def beat(self, ok, msg=""):
        return True

    def mac(self, title, text):
        return True


# ══════════════════════════ outlook 本身 ══════════════════════════
@pytest.mark.parametrize("tag", ["paper", "tachibana"])
def test_outlook_judges_the_incident_book(tag):
    b = _incident(tag)
    ol = LO.outlook(b, MO.unseen(tag, b), _t(8, 15), tag=tag, halt=False)
    row = ol["orders"][BUY]
    assert row["state"] == "wont" and row["cls"] == "fund" and "资金来源的卖单已撤" in row["reason"] and "¥192" in row["reason"]
    assert ol["orders"][SELL]["state"] == "done"
    fx = [r for r in ol["rows"] if r["kind"] == "instr" and r.get("ikind") == "corefix"]
    assert len(fx) == 1 and fx[0]["state"] == "will" and fx[0]["act_at"] == _t(9, 0)   # 还没读的固定 679 口：今天 09:00 开盘后
    assert LO.row_text(row).startswith(LAB_BUY + "：")
    ok = _book1015(tag, sell="SENT", cash=191.68)                       # 卖单还在：买单开盘后下（立花 09:05 / 模拟账户 09:25）
    r2 = LO.outlook(ok, (), _t(8, 15), tag=tag, halt=False)["orders"][BUY]
    assert r2["state"] == "will" and r2["act_at"] == _t(9, 5 if tag == "tachibana" else 25)
    assert LO.outlook(ok, (), _t(8, 15), tag=tag, halt=True)["orders"][BUY]["cls"] == "halt"


def test_outlook_new_wont_and_trade_key_without_amounts():
    before = LO.outlook(_book1015("tachibana", sell="SENT", cash=191.68), (), _t(8, 5), tag="tachibana", halt=False)
    after = LO.outlook(_book1015("tachibana", cash=191.68), (), _t(8, 5), tag="tachibana", halt=False)
    nw = LO.new_wont(before, after)
    assert [r["ref"] for r in nw] == [BUY] and not LO.new_wont(before, after, skip=[BUY])
    r = dict(nw[0])
    k = LO.trade_key(r, _t(8, 5), "U4")
    r.update(qty=5, reason="别的金额 ¥1")
    assert LO.trade_key(r, _t(10, 0), "U4") == k and "678" not in k and "¥" not in k


def test_tachibana_deferred_after_0930_is_wont_and_closed_after_1530():
    b = _book1015("tachibana", sell="FILLED", cash=2_000_000.0)
    assert LO.outlook(b, (), _t(9, 10), tag="tachibana", halt=False)["orders"][BUY]["state"] == "will"
    r = LO.outlook(b, (), _t(9, 40), tag="tachibana", halt=False)["orders"][BUY]
    assert r["state"] == "wont" and r["cls"] == "open_missed"
    assert LO.outlook(b, (), _t(15, 40), tag="tachibana", halt=False)["orders"][BUY]["cls"] == "closed"


# ══════════════════════════ 09:30 自检：重放（两个账本）══════════════════════════
@pytest.mark.parametrize("tag", ["paper", "tachibana"])
def test_incident_replay_watchdog_does_not_pass_and_push_has_the_reason(tag, tmp_path):
    _incident(tag)
    rec = watchdog.evaluate(tag, _t(9, 30))
    assert rec["ok"] is False                                   # 以前：模拟账户「✓ 09:30 自检通过」
    wont = [x for x in rec["reasons"] if x.startswith("今天不会下的单 1 笔：")]
    assert len(wont) == 1 and LAB_BUY in wont[0] and "资金来源的卖单已撤" in wont[0]
    late = [x for x in rec["reasons"] if "手动指令到现在还没下" in x]   # 08:48 写的固定 679 口没人读
    assert late and "固定" in late[0] and "10/15 08:48 写" in late[0] and "该在 10/15 09:00 下" in late[0]
    a = tmp_path / "agents"
    a.mkdir()
    (a / f"{watchdog.LIVE_PLIST if tag == 'tachibana' else watchdog.PAPER_PLIST}.plist").write_text("x", encoding="utf-8")
    r = _Rec()
    watchdog.run(a, _t(9, 30), send=r.send, beat=r.beat, mac=r.mac, out=lambda *_: None, sleep=lambda *_: None)
    title, text, level = r.sent[0]
    assert title.startswith("★ 交易：qbreak ") and title.endswith(" ★ 09:30 自检没通过") and level == "warn"
    assert "今天不会下的单 1 笔" in text and "1482 对冲版美国" in text


def test_watchdog_passes_and_lists_what_comes_later(tmp_path):
    """凑钱的卖单成交了、买单 09:26 撮合成交；明天开盘才处理的指令（同一只今天已经有执行器的单）→ 通过，「之后才下」写进当天的推送。"""
    item = {"id": "M-later", "kind": "sell", "ticker": "1545.T", "status": "pending", "at": "2026-10-15T09:10:00+09:00",
            "source": "panel", "hold": "2026-10-15", "msg": "x"}
    _book1015("paper", sell="FILLED", buy="FILLED", cash=500_000.0, items={"M-later": item})
    rec = watchdog.evaluate("paper", _t(9, 30))
    assert rec["ok"] is True and len(rec["later"]) == 1 and rec["later"][0].startswith("10/16 09:00 ")
    a = tmp_path / "agents"
    a.mkdir()
    (a / f"{watchdog.PAPER_PLIST}.plist").write_text("x", encoding="utf-8")
    r = _Rec()
    watchdog.run(a, _t(9, 30), send=r.send, beat=r.beat, mac=r.mac, out=lambda *_: None, sleep=lambda *_: None)
    assert r.sent[0][2] == "info" and "之后才下 1 条：10/16 09:00 " in r.sent[0][1] and "1545 纳斯达克 100" in r.sent[0][1]


# ══════════════════════════ 执行器：来源标记 + 汇总 ══════════════════════════
def test_rule_only_core_orders_are_tagged_rule():
    r = _paper2()
    _morning(r)                                                 # 第一次决策：照规则买 1545
    core = [o for o in r.ux.orders if o.kind == "core"]
    assert core and all(o.src == "rule" and o.src_txt == "规则再平衡" for o in core)
    assert all(o.reason == "核心 ETF 调整" for o in core)        # reason 本身不变（只加 src；now_phase / 对账照 reason 判断）
    assert r.ux.summary()["fix_note"] == "" and LO.src_line(core[0].__dict__) == "规则再平衡"


def _fixed(r):
    _morning(r, 8)
    _low_cash(r)
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=678, at="2026-10-14T19:21:00+09:00")
    _morning(r)
    return _one(r, "SELL", "1545.T"), _one(r, "BUY", "1482.T")


def test_fixed_units_tag_the_switch_and_the_summary_says_it_is_yours():
    r = _paper2()
    sell, buy = _fixed(r)
    assert sell.src == "fix_fund" and buy.src == "core_fix"
    assert sell.src_txt == "为你的『固定 1482 对冲版美国 7〜10 年国债 678 口』凑钱（10/14 19:21 写）"
    assert buy.src_txt == "照你的『固定 1482 对冲版美国 7〜10 年国债 678 口』调（10/14 19:21 写）"
    sm = r.ux.summary()
    assert sm["fix_note"].startswith("★ 固定 1482 对冲版美国 7〜10 年国债 678 口 生效：今天的换仓来自你写的固定口数，不是规则的判断")
    assert sm["outlook"][buy.cid]["state"] in ("will", "later") and not trade_wont(sm)
    _, short, body = daily_text(sm, r.eng.st, None, True, 1_000_000)
    assert "★ 交易" not in short and "为你的『固定 1482 对冲版美国 7〜10 年国债 678 口』凑钱" in body
    assert "- 闲置资金：★ 固定 1482 对冲版美国 7〜10 年国债 678 口 生效" in body or "；★ 固定 1482" in body


def test_summary_order_lines_say_wont_instead_of_the_stale_0740_note():
    """卖单在执行器之外撤了（旧版本没有撤单级联）→ 汇总推送的那一行写「→ 不会下：<原因>」，不再写「开盘后按始値检查、减股再下」。"""
    r = _paper2()
    sell, buy = _fixed(r)
    r.b.cancel_pending(sell.cid)
    sell.status = "CANCELLED"
    sm = r.ux.summary()
    assert sm["outlook"][buy.cid]["state"] == "wont"
    assert [o["cid"] for o in trade_wont(sm)] == [buy.cid]
    o = next(x for x in sm["orders"] if x["cid"] == buy.cid)
    assert order_tail(o, sm).startswith("→ 不会下：") and "减股再下" not in order_tail(o, sm)
    _, short, body = daily_text(sm, r.eng.st, None, True, 1_000_000)
    assert "★ 交易：今天不会下 1 笔" in short
    ln = next(x for x in body.split("\n") if "1482 对冲版美国" in x and "不会下" in x)
    assert "照你的『固定 1482" in ln and "→ 不会下：" in ln


def test_tachibana_fixed_units_tags_and_summary():
    r = _tachi2()
    for _ in range(9):
        _tday(r)
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=678, at="2026-10-14T19:21:00+09:00")
    _tday(r)
    sell = _one(r, "SELL", "1545.T")
    rest = _one(r, "BUY", "1482.T", "-2")
    assert sell.src == "fix_fund" and rest.src == "core_fix" and "凑钱（10/14 19:21 写）" in sell.src_txt
    sm = r.ux.summary()
    assert sm["outlook"][rest.cid]["state"] == "will" and not trade_wont(sm)   # 卖单在：开盘后 09:05 下
    sell.status = "CANCELLED"                                   # 执行器之外撤了（不经过级联）
    r.eng.st.cash_jpy = 191.68                                  # 与 2026-10-15 的账本一样：现金 191.68 円
    (paths.out_dir() / "broker_snapshot_tachibana.json").unlink(missing_ok=True)   # 模拟交易所的余力快照不算（只看账本现金）
    sm = r.ux.summary()
    assert sm["outlook"][rest.cid]["state"] == "wont" and [o["cid"] for o in trade_wont(sm)] == [rest.cid]
    assert "★ 交易：今天不会下 1 笔" in daily_text(sm, r.eng.st, None, False, 1_000_000)[1]


# ══════════════════════════ 撤单推送：撤之后新出现的「不会下」══════════════════════════
def test_cancel_push_lists_buys_that_now_cannot_be_paid(monkeypatch):
    """旧账本（没有 fund_src）：撤了还没发出的卖单 → 级联不知道买单靠它 → 撤单推送照 outlook 前后对比补一行「★ 买 …」、标题「★ 交易」、warn。"""
    _book1015("tachibana", sell="PLANNED", cash=191.68)
    monkeypatch.setattr(LO, "now_jst", lambda: _t(8, 5))
    monkeypatch.setattr(run, "_refresh_after_book_change", lambda tag: None)
    monkeypatch.setattr(LU, "mac_notify", lambda *a, **k: True)
    sent = []
    monkeypatch.setattr(notify, "send", lambda title, text, level="info", **k: sent.append((title, text, level)))
    a = SimpleNamespace(cancel=[SELL], notify=True, demo=False, dry_run=False)
    rc = run._live_cancel(a, "tachibana", paths.state_dir() / "live_unified_tachibana.json", False)
    assert rc == 0 and len(sent) == 1
    title, text, level = sent[0]
    assert title.startswith("★ 交易：") and level == "warn"
    assert f"★ {LAB_BUY}" in text and "资金来源的卖单已撤" in text


# ══════════════════════════ 面板：U4 / 15:25 之后的汇总 ══════════════════════════
def _paper_open_done(**kw) -> dict:
    """凑钱的卖单成交了、钱够、买单还 DEFERRED，但今天的开盘撮合已经做过了（没人会再下它）。"""
    b = _book1015("paper", sell="FILLED", cash=2_000_000.0, **kw)
    b["orders"][1]["fund_src"] = [SELL]
    b["paper_open"] = {"decided_on": "2026-10-14", "at": "2026-10-15T09:26:00+09:00"}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def _trigger(monkeypatch, t, sent):
    monkeypatch.setattr(panel, "books", lambda: ["paper"])
    return panel.Trigger(run=lambda *a: None, clock=lambda: t, mono=lambda: 0.0,
                         notify=lambda tag, title, text, level="warn": sent.append((title, text, level)))


def test_u4_no_execution_path_is_pushed_once(monkeypatch):
    _paper_open_done()
    sent = []
    _trigger(monkeypatch, _t(9, 30), sent).check()             # 09:25 + 10 分钟还没到
    assert sent == []
    _trigger(monkeypatch, _t(10, 30), sent).check()
    assert len(sent) == 1
    title, text, level = sent[0]
    assert title == "★ 交易：qbreak 模拟账户 今天该下但没有执行路径" and level == "warn"
    assert LAB_BUY in text and "（该在 今天 09:25 下）" in text
    _trigger(monkeypatch, _t(11, 0), sent).check()             # 同一笔同一天只推一次
    assert len(sent) == 1


def test_u4_not_when_a_path_exists(monkeypatch):
    b = _paper_open_done()
    b.pop("paper_open")                                         # 开盘撮合还没做：面板会叫 → 有路
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    sent = []
    tr = _trigger(monkeypatch, _t(10, 0), sent)                 # 同一个实例：_no_path 只往它的 outbox 里放（审查 tests F4，2026-10-16）
    tr._no_path("paper", b, _t(10, 0), "2026-10-15")
    assert tr.outbox == [] and sent == []
    ctl = _paper_open_done()                                    # 对照：开盘撮合已经做过（没有路）→ 同一个调用真的会放进 outbox
    tr = _trigger(monkeypatch, _t(10, 0), sent)
    tr._no_path("paper", ctl, _t(10, 0), "2026-10-15")
    assert len(tr.outbox) == 1 and "今天该下但没有执行路径" in tr.outbox[0][1]


def test_u4_quiet_and_later_when_settle_stopped(monkeypatch):
    """开盘撮合被停下（公司行为 / 开盘价超出制限値幅：paper_open.stop）→ 等开盘后的买单 = 明早 07:40 照旧撮合（later），
    不推「今天该下但没有执行路径」（审查 paper F3 / promise F2，2026-10-16）。"""
    b = _paper_open_done()
    b["paper_open"]["stop"] = "7203 トヨタ自動車 今天有公司行为"
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    ol = LO.outlook(b, [], _t(10, 0), tag="paper")
    row = next(r for r in ol["rows"] if r.get("ref") == b["orders"][1]["cid"])
    assert row["state"] == "later" and "今天不做开盘撮合" in row["reason"] and row["act_at"].date() == dt.date(2026, 10, 16)
    sent = []
    tr = _trigger(monkeypatch, _t(10, 30), sent)
    tr._no_path("paper", b, _t(10, 30), "2026-10-15")
    assert tr.outbox == []


def test_after_1525_not_today_summary(monkeypatch):
    _paper_open_done()
    sent = []
    _trigger(monkeypatch, _t(15, 27), sent).check()
    w = [s for s in sent if s[0].startswith("★ 交易：qbreak 模拟账户 今天没下成 / 不会下")]
    assert len(w) == 1 and w[0][2] == "warn" and LAB_BUY in w[0][1]
    assert "今天的开盘撮合（09:25〜11:30）没下成 → 10/16 07:40" in w[0][1] and "减股再下" not in w[0][1]   # 不写 07:40 的旧说明


def test_halt_rows_are_not_in_the_not_today_summary():
    b = _incident("paper")
    paths.halt_file().write_text("x", encoding="utf-8")
    ol = LO.outlook(b, MO.unseen("paper", b), _t(15, 30), tag="paper")
    assert not [r for r in LO.not_today(ol, _t(15, 30)) if r["cls"] == "halt"]


# ══════════════════════════ 种类 × 时段 × 账本：outlook 与面板 / 说明一致 ══════════════════════════
@pytest.mark.parametrize("book", ["paper", "tachibana"])
@pytest.mark.parametrize("kind", list(KINDS))
@pytest.mark.parametrize("when", list(TIMES))
def test_outlook_agrees_with_trigger_and_text(book, kind, when):
    r = _base(book)
    (dd, hh, mm), path = TIMES[when]
    rec, _ = KINDS[kind]
    T = _at0(r, hh, mm, dd)
    if path == "decision":
        _close_day(r)
    elif T >= _at0(r, 9, 0):
        _open_day(r)
    w = _w(r.tag, f"M-{kind}", **rec)
    b = _disk(r)
    ol = LO.outlook(b, MO.unseen(r.tag, b), T, tag=r.tag, halt=False)
    row = ol["items"][f"M-{kind}"]
    assert row["reason"] == MO.wait_text(w, T, b, r.tag)              # 说明：与面板 / 命令行同一句
    if path == "next":
        assert row["state"] == "later" and row["act_at"].date() > T.date()
    else:
        assert row["state"] == "will"
        assert row["act_at"] is None or row["act_at"].date() == T.date()
    if path == "now":
        assert MO.now_due(r.tag, b, T) and row["act_at"] <= T          # 面板马上叫
    elif path == "lunch":
        assert row["act_at"] == T.replace(hour=12, minute=30)
    elif path == "open" and kind != "sell":
        assert row["act_at"] == T.replace(hour=9, minute=0)


def test_when_text_between_cutoff_and_open():
    assert MO.when_text(_t(8, 57)) == "今天 09:00 开盘后马上（按现价，不是寄付）"
    assert MO.when_text(_t(8, 50)) == "今天 09:00 开盘"


def test_trade_tab_and_cancel_confirm_show_the_source_with_the_write_time():
    from test_panel import AT15, _card
    b = _book1015("paper", sell="SENT")
    txt = "为你的『固定 1482 对冲版美国 7〜10 年国债 678 口』凑钱（10/14 19:21 写）"
    b["orders"][0].update(src="fix_fund", src_txt=txt)
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    assert f"<div class='small'>{txt}</div>" in card                   # 交易页：单下面一行
    assert f"data-hint='{txt}。" in card                                 # 撤单确认框：先写这笔从哪来
