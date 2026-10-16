"""「交易」只显示今天要成交的单（2026-10-16 用户：「交易里面只显示当天要成交的单」）：
上面「今天要成交的单」（id today）= 今天还会做事的执行器的单 + 今天做事的手动指令；之后才做的收进同一张卡片的「另有 N 条等 10/19（周一）开盘」；
结束了的 / 不是今天的收进最下面「已结束 / 不是今天的（N 条）」（id orders，默认收起）。分块只按 live_ops.outlook + panel._trade_live
（panel._trade_split）；Mac 与手机同一份 HTML；标签上的数字口径不变 = 上面的行（不含撤单中）+「另有」的行。"""
import datetime as dt
import json
import logging
import re

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST
from test_panel import AT15, _book1015, _card, _pane, _tabbtn

D = "2026-10-14"
SELL, BUY = f"U{D}-SELL-1545.T", f"U{D}-BUY-1482.T"
SELL_B, BUY_B = "<b>卖 1545 纳斯达克 100：4,110 口</b>", "<b>买 1482 对冲版美国 7〜10 年国债：678 口</b>"   # 没有「撤单」按钮的行也认得出
NAMES = {"1545": "纳斯达克 100", "1482": "对冲版美国 7〜10 年国债", "7203": "トヨタ自動車"}
REMOTE = {"mode": "remote", "device": {"name": "x", "kind": "ts", "id": "ts"}}
ROW = re.compile(r"<div class='li[ ']")


def _t(y, m, d, hh, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=JST)


def _save(b: dict, tag: str = "paper") -> dict:
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def _want(rec: dict, tag: str = "paper") -> None:
    """面板写的一条手动指令（指令文件里，执行器还没读）。"""
    p = MO.requests_path(tag)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _sell_req(at: dt.datetime) -> dict:
    return {"id": f"M{at:%Y%m%d-%H%M%S}-sell-7203", "kind": "sell", "ticker": "7203.T", "block_days": 20,
            "at": at.isoformat(timespec="seconds")}


def _done_book(last: str, tag: str = "paper") -> dict:
    """上一次决策（last）的单都成交了；拿着 7203.T 200 股。"""
    o = {"cid": f"U{last}-SELL-1545.T", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 100, "decided_on": last,
         "limit": None, "ref_px": 243.7, "phase": "morning", "status": "FILLED", "sent_qty": 100, "filled_qty": 100,
         "filled_px": 244.0, "note": "成交"}
    st = {"last_date": last, "cash_jpy": 500_000.0, "history": [[last, 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {"1545.T": 4010}}
    return _save({"state": st, "orders": [o], "core_rule": {"lot": {"1545.T": 10}}, "manual": {"items": {}}}, tag)


def _parts(html: str) -> tuple[str, str, str]:
    """（上面今天的部分（含说明）, 「另有 …」里的, 「已结束 / 不是今天的」）。"""
    card = _card(html, "today")
    i = card.find("<details class='later'>")
    j = card.find("</details>", i) + len("</details>")
    top, later = (card, "") if i < 0 else (card[:i] + card[j:], card[i:j])
    ended = _card(html, "orders") if "<section class='card' id='orders'>" in html else ""
    return top, later, ended


def _badge_ok(html: str, tag: str, now: dt.datetime, unpaid: int = 0) -> int:
    """标签上的数字 n == 上面的行（不含「撤单中」）+「另有」的行 − unpaid（数字口径不算、但照样显示的行：见 panel._trade_split 的说明）。"""
    b = json.loads((paths.state_dir() / f"live_unified_{tag}.json").read_text(encoding="utf-8"))
    n = panel._trade_live(b, MO.unseen(tag, b), now, tag)["n"]
    top, later, _ = _parts(html)
    flight = top.count("<span class='chip'>撤单中</span>")
    assert n == len(ROW.findall(top)) - flight + len(ROW.findall(later)) - unpaid
    tb = _tabbtn(html, "trade")
    assert (f"<i class='badge'>{n}</i>" in tb) if n else ("class='badge'" not in tb)
    return n


def _row(part: str, head: str) -> str:
    """part 里以 head 开头的那一行（到下一行 / 列表结束）。"""
    i = part.index(head)
    j = [k for k in (part.find("<div class='li", i), part.find("</div></div><div class='tsub'>", i)) if k >= 0]
    return part[i:min(j) if j else len(part)]


def _named(html: str) -> None:
    """看得见的文字里，这几只的代码后面都跟着名字（单号 / 指令 id 里的代码不算）。"""
    txt = re.sub(r"<[^>]+>", " ", _pane(html, "trade"))
    txt = re.sub(r"[UNM][\w:.-]*\d{4}\.T|M\d{8}-\d{6}-[\w-]+", " ", txt)
    for code, name in NAMES.items():
        for m in re.finditer(rf"(?<![\d,.¥]){code}(?:\.T)?(?![\d,])", txt):
            assert txt[m.end():].startswith(" " + name), txt[max(0, m.start() - 30):m.end() + 30]


# ────────── 1. 平常的早上 ──────────
def _morning():
    b = _book1015("paper", sell="SENT", cash=2_000_000.0, fix={},
                  items={"M5-sell": {"id": "M5-sell", "kind": "sell", "ticker": "7203.T", "status": "pending",
                                     "at": "2026-10-15T08:00:00+09:00"}})
    b["state"]["pos"] = {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}}
    b["orders"].append({**b["orders"][1], "cid": f"U{D}-BUY-7203.T", "ticker": "7203.T", "kind": "stock", "qty": 100,
                        "status": "CANCELLED", "note": "你撤了单（08:05）"})
    return _save(b), "paper", AT15


def test_normal_morning_live_on_top_finished_below():
    _morning()
    html = panel.render("paper", "t" * 40, AT15)
    top, later, ended = _parts(html)
    assert "<h2>今天要成交的单</h2>" in top and "<div class='tsub'>执行器的单（成交日 10/15）</div>" in top
    assert f"data-cid='{SELL}'" in top and f"data-cid='{BUY}'" in top and "data-id='M5-sell'" in top
    assert "<div class='tsub'>手动指令</div>" in top and "卖出全部 7203 トヨタ自動車" in top
    assert "今天没有要成交的单了" not in top and later == ""
    assert "<summary>已结束 / 不是今天的（1 条）</summary>" in ended and "<span class='chip'>已撤单</span>" in ended
    assert "<b>买 7203 トヨタ自動車：100 股</b>" in ended and "已撤单" not in top
    assert html.index("id='room'") < html.index("id='today'") < html.index("id='orders'")    # 小卡在最上面，已结束的在最下面
    assert "「撤单」：已经成交的部分撤不了" in top                                       # 撤单说明跟着上面的单
    assert _badge_ok(html, "paper", AT15) == 3
    _named(html)


# ────────── 2. 收盘后写的：明天 / 周五写的 → 下周一 / 连休前 → 连休之后 ──────────
@pytest.mark.parametrize("now,last,day", [
    (_t(2026, 10, 15, 16, 5), "2026-10-14", "10/16（周五）"),
    (_t(2026, 10, 16, 16, 5), "2026-10-15", "10/19（周一）"),         # 周五 → 下周一（不写「明天」）
    (_t(2026, 11, 2, 16, 5), "2026-10-30", "11/04（周三）"),          # 11/03 文化の日
])
def test_after_close_instruction_waits_for_the_next_opening(now, last, day):
    _done_book(last)
    _want(_sell_req(now))
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "<div class='tempty'>今天没有要成交的单了</div>" in top
    assert f"<summary>另有 1 条等 {day}开盘</summary>" in later
    assert "卖出全部 7203 トヨタ自動車" in later and "data-act='cancel'" in later       # 点开：那一行与「撤回」按钮照旧
    assert "<span class='chip'>已成交</span>" in ended and "卖出全部" not in ended
    assert _badge_ok(html, "paper", now) == 1
    _named(html)


# ────────── 3. 休市日 / 今天早上的运行还没跑 ──────────
def test_non_trading_day():
    now = _t(2026, 10, 17, 10, 0)                                            # 周六
    _done_book("2026-10-15")
    _want(_sell_req(now))
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "<div class='tempty'>今天休市，没有要成交的单</div>" in top and "今天没有要成交的单了" not in top
    assert "执行器的单是上一次决策的单（成交日 10/16），不是今天的：今天休市" in top
    assert "<summary>另有 1 条等 10/19（周一）开盘</summary>" in later and "<span class='chip'>已成交</span>" in ended
    assert _badge_ok(html, "paper", now) == 1


def test_stale_morning_follows_outlook_and_says_whose_orders():
    _book1015("tachibana", sell="SENT", cash=2_000_000.0, fix={})            # 上一次决策（成交日 10/15）的单
    now = _t(2026, 10, 16, 8, 0)                                            # 10/16 早上的运行还没跑
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "执行器的单是上一次决策的单（成交日 10/15），不是今天的：今天早上的运行还没跑" in top
    assert "<div class='tempty'>今天没有要成交的单了</div>" in top and "<span class='chip'>已收盘</span>" in ended
    assert "立花 API / Mac 出故障那天" not in html                                  # 上一次决策的单：不给「照没下的行在立花网站下单」
    assert _badge_ok(html, "tachibana", now) == 0
    _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})                 # 模拟账户 07:40 之前：等开盘后的买单今天 07:40 的运行撮合 → 上面
    now = _t(2026, 10, 16, 7, 30)
    html = panel.render("paper", "t" * 40, now)
    top, _later, _ended = _parts(html)
    assert "上一次决策的单（成交日 10/15）" in top and BUY_B in top and "data-act='cancel-order'" not in top   # 上一次决策的单：不给撤单按钮（照旧）
    assert _badge_ok(html, "paper", now) == len(ROW.findall(top))


# ────────── 4. HALT ──────────
def _halt():
    b = _book1015("tachibana", sell="SENT", cash=2_000_000.0, fix={},
                  items={"M5-sell": {"id": "M5-sell", "kind": "sell", "ticker": "7203.T", "status": "pending",
                                     "at": "2026-10-15T08:00:00+09:00"}})
    paths.halt_file().write_text("测试", encoding="utf-8")
    return b, "tachibana", AT15


def test_halt_line_and_held_instructions_wait_for_release():
    _halt()
    html = panel.render("tachibana", "t" * 40, AT15)
    top, later, ended = _parts(html)
    assert "★ HALT 生效中：执行器今天不发新单" in top
    assert SELL_B in top                                                             # 已经在交易所：照样可能成交
    assert "<summary>另有 1 条等 HALT 解除后</summary>" in later and "data-id='M5-sell'" in later
    assert "<span class='chip'>不会下单（HALT）</span>" in _row(ended, BUY_B) and BUY_B not in top
    assert "立花 API / Mac 出故障那天：只照「被挡 / 不下 / 没下」的行" in top
    assert _badge_ok(html, "tachibana", AT15) == 2


# ────────── 5. 撤单中 ──────────
def test_cancel_in_flight_stays_on_top_unsent_cancel_goes_below():
    _save(_book1015("paper", sell="SENT", cash=2_000_000.0, fix={}))
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel_order", "cid": SELL}, AT15)
    assert ok, msg
    html = panel.render("paper", "t" * 40, AT15)
    top, _later, ended = _parts(html)
    assert "<span class='chip'>撤单中</span>" in _row(top, SELL_B)                   # 还挂在交易所：执行器确认之前还可能成交
    assert f"data-cid='{BUY}'" in top and "撤单 1545 纳斯达克 100" in ended               # 撤单指令本身在下面
    assert _badge_ok(html, "paper", AT15) == 1
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel_order", "cid": BUY}, AT15)    # 还没发出的单写了撤单 = 不会再发 → 下面
    assert ok, msg
    html = panel.render("paper", "t" * 40, AT15)
    top, _later, ended = _parts(html)
    assert "<span class='chip'>撤单中</span>" in _row(ended, BUY_B) and BUY_B not in top
    assert _badge_ok(html, "paper", AT15) == 0


# ────────── 6. 固定口数 ──────────
def test_corefix_still_active_note_stays_visible_once():
    _book1015()                                                                # 凑钱的卖单撤了、买单下不成、固定 678 口还有效
    html = panel.render("paper", "t" * 40, AT15)
    top, later, ended = _parts(html)
    assert top.count("1482 对冲版美国 7〜10 年国债 手动固定 678 口仍然有效") == 1 and "10/16 07:40" in top
    assert f"data-cid='{BUY}'" in ended and "<div class='tempty'>今天没有要成交的单了</div>" in top
    assert _badge_ok(html, "paper", AT15) == 0
    _named(html)


def _fixwait(clear: bool = False):
    b = _book1015(fix={} if clear else {"1482.T": 678})
    b["orders"] = []
    b["core_rule"]["fix_applied"] = {"1482.T": 678} if clear else {}      # 执行器读了、还没照它排单（corefix_pending）
    iid = "M20261014-190000-corefix-1482"
    b["manual"]["items"] = {iid: {"id": iid, "kind": "corefix", "ticker": "1482.T", "status": "done", "at": "2026-10-14T19:00:00+09:00",
                                  **({"clear": True} if clear else {"units": 678})}}
    return _save(b), "paper", AT15


@pytest.mark.parametrize("now,where", [(AT15, "top"), (AT15.replace(hour=16), "later")])
def test_corefix_waiting_to_be_applied_follows_outlook(now, where):
    _fixwait()
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert "固定 1482 对冲版美国 7〜10 年国债：678 口" in part and f"<span class='chip'>{MO.FIX_WAIT}</span>" in part
    if where == "later":
        assert "<summary>另有 1 条等 10/16（周五）开盘</summary>" in later
    assert _badge_ok(html, "paper", now, unpaid=1) == 0                       # 例外：指令已经「完成」→ 数字不算（口径不变）
    _fixwait(clear=True)                                                       # 恢复按规则（还没照它调）：没有自己的指令行 → 补一行、没有按钮
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert "1482 对冲版美国 7〜10 年国债 恢复按规则（还没照它调）" in part and "恢复按规则（不按固定口数）" not in part
    assert _badge_ok(html, "paper", now, unpaid=1) == 0


# ────────── 7. 同一组分在两处 ──────────
def test_group_members_split_across_sections_keep_the_group_line():
    b = _book1015("paper", sell="SENT", buy="CANCELLED", cash=2_000_000.0, fix={})
    b["orders"][0]["src"] = "fix_fund"
    b["orders"][1].update(src="core_fix", fund_src=[SELL])
    _save(b)
    html = panel.render("paper", "t" * 40, AT15)
    top, _later, ended = _parts(html)
    assert f"data-cid='{SELL}'" in top and "同一组（一起下的）还有：买 1482 对冲版美国 7〜10 年国债" in top
    assert "<b>买 1482 对冲版美国 7〜10 年国债：678 口</b>" in ended and "同一组（一起下的）还有：卖 1545 纳斯达克 100" in ended
    _named(html)


# ────────── 8. 手机与 Mac 同一份 ──────────
@pytest.mark.parametrize("make", [_morning, _halt, lambda: (_book1015(), "paper", AT15)])
def test_phone_renders_the_same_trade_cards(make):
    try:
        _b, tag, now = make()
        loc = panel.render(tag, "t" * 40, now)
        rem = panel.render(tag, "t" * 40, now, **REMOTE)
        assert _parts(loc) == _parts(rem)
        assert _card(loc, "room") == _card(rem, "room")
    finally:
        if paths.halt_file().exists():
            paths.halt_file().unlink()


# ────────── 9. 标签上的数字 = 上面（不含撤单中）+「另有」 ──────────
def _after_close():
    now = _t(2026, 10, 16, 16, 5)
    _done_book("2026-10-15")
    _want(_sell_req(now))
    return None, "paper", now


@pytest.mark.parametrize("make,unpaid", [(_morning, 0), (_after_close, 0), (_fixwait, 1), (_halt, 0),
                                         (lambda: (_save(_book1015("tachibana", sell="SENT", fix={})), "tachibana", _t(2026, 10, 16, 8, 0)), 0)])
def test_badge_equals_today_rows_plus_later_rows(make, unpaid):
    """普通的早上 / 收盘后写的（下一个交易日开盘）/ 固定口数还没照它调（fix:<票>）/ HALT / 今天早上的运行还没跑。
    固定口数那一行：数字口径不算（指令已经「完成」；panel._trade_split 的说明）→ unpaid = 1。"""
    try:
        _b, tag, now = make()
        html = panel.render(tag, "t" * 40, now)
        _badge_ok(html, tag, now, unpaid)
        sp = panel._trade_split(json.loads((paths.state_dir() / f"live_unified_{tag}.json").read_text(encoding="utf-8")),
                                MO.unseen(tag, None), now, tag)
        assert set(sp["orders"].values()) | set(sp["items"].values()) <= {"today", "later", "ended"}
    finally:
        if paths.halt_file().exists():
            paths.halt_file().unlink()


def test_outlook_failure_keeps_unfinished_on_top(monkeypatch, caplog):
    """outlook 算不成（账本里读不了的数…）→ 分块不下结论：还没结束的单都在上面、结束了的在下面，页面照样打开。"""
    from qbreak import live_ops as LO
    b = _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})
    b["orders"].append({**b["orders"][1], "cid": f"U{D}-BUY-7203.T", "ticker": "7203.T", "kind": "stock", "qty": 100, "status": "CANCELLED"})
    _save(b)
    monkeypatch.setattr(LO, "outlook", lambda *a, **k: 1 / 0)
    with caplog.at_level(logging.WARNING, logger="qbreak"):              # 别的测试设过 qbreak 日志不往上传：直接挂在 qbreak 上
        sp = panel._trade_split(b, [], AT15, "paper", halt=False)
    assert sp["orders"] == {SELL: "today", BUY: "today", f"U{D}-BUY-7203.T": "ended"} and not sp["flight"]
    assert "分块没算成" in caplog.text
