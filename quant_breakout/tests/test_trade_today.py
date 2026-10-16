"""「交易」只显示今天要成交的单（2026-10-16 用户：「交易里面只显示当天要成交的单」）：
上面「今天要成交的单」（id today）= 今天还会做事的执行器的单 + 今天做事的手动指令；之后才做的收进同一张卡片的「另有 N 条等 10/19（周一）开盘」；
结束了的 / 不是今天的收进最下面「已结束 / 不是今天的（N 条）」（id orders，默认收起）。分块只按 live_ops.outlook + panel._trade_live
（panel._trade_split）；Mac 与手机同一份 HTML；标签上的数字 = 上面的行（不含撤单中）+「另有」的行，按同一份分块数（panel._split_n），
没有例外（复核 2，2026-10-16）。"""
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
NAMES = {"1545": "纳斯达克 100", "1482": "对冲版美国 7〜10 年国债", "7203": "トヨタ自動車", "6758": "ソニーグループ"}
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


def _badge_ok(html: str, tag: str, now: dt.datetime) -> int:
    """标签上的数字 n == 上面的行（不含「撤单中」）+「另有」的行 —— 没有例外（复核 2，2026-10-16：以前状态不明的单、固定口数还没照它调
    的那一行在上面却不算，没买到的手动买入 / 加仓收在「已结束」却照算）。/api/status 的 pending 同一个数。"""
    b = json.loads((paths.state_dir() / f"live_unified_{tag}.json").read_text(encoding="utf-8"))
    tl = panel._trade_live(b, MO.unseen(tag, b), now, tag)
    n = tl["n"]
    top, later, _ = _parts(html)
    flight = top.count("<span class='chip'>撤单中</span>")
    iflight = top.count("<div class='li'><div class='grow'><b>撤单")   # 跟着那笔单放在上面的撤单指令本身不算（复核 8）
    assert iflight == len(tl["split"].get("iflight") or ())
    flight += iflight
    assert n == len(ROW.findall(top)) - flight + len(ROW.findall(later))
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
    assert "执行器的单是上一次决策的单" not in top and "今天休市" not in top.replace("今天休市，没有要成交的单", "")   # 只说一次（复核 8）
    assert "<summary>另有 1 条等 10/19（周一）开盘</summary>" in later and "<span class='chip'>已成交</span>" in ended
    assert _badge_ok(html, "paper", now) == 1


def test_stale_morning_follows_outlook_and_says_whose_orders():
    _book1015("tachibana", sell="SENT", cash=2_000_000.0, fix={})            # 上一次决策（成交日 10/15）的单
    now = _t(2026, 10, 16, 8, 0)                                            # 10/16 早上的运行还没跑
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "执行器的单是上一次决策的单（成交日 10/15），不是今天的</div>" in top           # 为什么写在下面的空行里（不重复）
    assert ("<div class='tempty'>今天的单还没排出来：今天早上的运行还没跑完（跑完之后这里才有今天的单）</div>" in top   # 复核 2026-10-16：
            and "今天没有要成交的单了" not in top and "<span class='chip'>已收盘</span>" in ended)   # 以前写「今天没有要成交的单了」
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
    assert f"data-cid='{BUY}'" in top and "撤单 1545 纳斯达克 100" in top and "撤单 1545" not in ended   # 撤单指令跟着那笔单在上面、
    #                                                                                 不算数字（复核 8：以前收进「已结束」，单还挂着）
    assert _badge_ok(html, "paper", AT15) == 1
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel_order", "cid": BUY}, AT15)    # 还没发出的单写了撤单 = 不会再发 → 下面
    assert ok, msg
    html = panel.render("paper", "t" * 40, AT15)
    top, _later, ended = _parts(html)
    assert "<span class='chip'>撤单中</span>" in _row(ended, BUY_B) and BUY_B not in top
    assert "撤单 1482 对冲版美国 7〜10 年国债" in ended and "撤单 1482" not in top       # 那笔单在下面 → 它的撤单指令也在下面
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
    assert _badge_ok(html, "paper", now) == 1                                 # 执行器之后照它调 → 算（复核 2：以前「指令已经完成」不算）
    _fixwait(clear=True)                                                       # 恢复按规则（还没照它调）：没有自己的指令行 → 补一行、没有按钮
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert "1482 对冲版美国 7〜10 年国债 恢复按规则（还没照它调）" in part and "恢复按规则（不按固定口数）" not in part
    assert _badge_ok(html, "paper", now) == 1


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


@pytest.mark.parametrize("make", [_morning, _after_close, _fixwait, _halt,
                                  lambda: (_save(_book1015("tachibana", sell="SENT", fix={})), "tachibana", _t(2026, 10, 16, 8, 0))])
def test_badge_equals_today_rows_plus_later_rows(make):
    """普通的早上 / 收盘后写的（下一个交易日开盘）/ 固定口数还没照它调（fix:<票>）/ HALT / 今天早上的运行还没跑：
    数字 = 上面（不含撤单中）+「另有」，没有例外（复核 2，2026-10-16：固定口数那一行以前不算）。"""
    try:
        _b, tag, now = make()
        html = panel.render(tag, "t" * 40, now)
        _badge_ok(html, tag, now)
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


# ────────── 复核（2026-10-16）──────────
def _mbook(tag: str, last: str, orders: list, items: dict, keys: dict | None = None, pos: bool = True) -> dict:
    """手动指令的账本：上一次决策 last 的单 orders、指令 items、manual.trims / buys / adds（keys）；拿着 7203.T 200 股。"""
    st = {"last_date": last, "cash_jpy": 2_000_000.0, "history": [[last, 3_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0,
                             "last_close": 2600.0}} if pos else {},
          "pending_exit": {}, "core_units": {}}
    man = {"items": items, "trims": {}, "buys": {}, "adds": {}, **(keys or {})}
    return _save({"state": st, "orders": orders, "core_rule": {"lot": {}}, "manual": man}, tag)


def _morder(last: str, side: str, t: str, reason: str, status: str, note: str = "", **kw) -> dict:
    return {"cid": f"U{last}-{side}-{t}", "ticker": t, "side": side, "kind": "stock", "qty": 100, "decided_on": last,
            "limit": 2700.0 if side == "BUY" else None, "ref_px": 2600.0, "phase": "morning", "status": status,
            "sent_qty": 100, "filled_qty": 0, "note": note, "reason": reason, **kw}


BUY_ID = "M20261014-190000-buy-6758"


def _buy_book(tag: str, status: str, note: str = "", unsent: dict | None = None, **kw) -> dict:
    """10/14 晚上写的「买入 6758」，10/15 开盘的单（status）—— 没成交、指令还是「已下单」（明早对账才结束 / 留到下一次决策）。"""
    it = {"id": BUY_ID, "kind": "buy", "ticker": "6758.T", "unit": "rule", "status": "placed", "decided_on": D,
          "fill_day": "2026-10-15", "shares": 100, "side": "BUY", "msg": "10/15 开盘买入 100 股", "at": "2026-10-14T19:00:00+09:00",
          **({"unsent": unsent} if unsent else {})}
    return _mbook(tag, D, [_morder(D, "BUY", "6758.T", "manual_buy", status, note, **kw)], {BUY_ID: it},
                  {"buys": {"6758.T": {"id": BUY_ID}}})


GAP = "开盘 3100 比信号日收盘 2900 高 +6.9%，超过 5% —— 与模型相同"


@pytest.mark.parametrize("tag,status,note,unsent,now", [
    ("tachibana", "REJECTED", "立花：余力不足（sOrderStatusCode=7）", None, _t(2026, 10, 15, 8, 30)),
    ("tachibana", "REJECTED", "立花：余力不足（sOrderStatusCode=7）", None, _t(2026, 10, 15, 10, 30)),
    ("tachibana", "REJECTED", "立花：余力不足", {"last": "2026-10-15", "why": "被拒", "retry": False}, _t(2026, 10, 15, 8, 40)),
    ("tachibana", "BLOCKED", "上場廃止日 2026-11-01（30 天以内）→ 不下买单", None, _t(2026, 10, 15, 10, 0)),
    ("paper", "SKIPPED", GAP, None, _t(2026, 10, 15, 10, 0)),
    ("tachibana", "SKIPPED", GAP, None, _t(2026, 10, 15, 16, 0)),
])
def test_one_time_buy_that_did_not_buy_is_ended_not_next_opening(tag, status, note, unsent, now):
    """手动买入只做一次：单被拒 / 这只买不了 / 跳空不下 → 明早对账结束（live_unified 的 _reconcile：不是系统原因 → on_fill(0) / on_not_sent(final)）。
    以前分块按「单都结束了 → 下一次开盘」：08:30 写在「今天要成交的单」里、10:30 写「另有 1 条等 10/16（周五）开盘」（复核 2026-10-16）。"""
    _buy_book(tag, status, note, unsent)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    assert "买入 6758 ソニーグループ" not in top and later == "" and "买入 6758 ソニーグループ" in ended
    row = _row(ended, "<b>买入 6758 ソニーグループ")
    if unsent:                                                                   # 「没发出（只做一次）」已经说了：不再加一句
        assert "<span class='chip'>没发出（只做一次）</span>" in row
    else:
        assert "（没买到：只做一次，不再买；10/16 07:40 的对账之后结束）</span>" in row
    assert "今天没有要成交的单了" in top
    assert _badge_ok(html, tag, now) == 0                                        # 不会再买 → 不算（复核 2：以前等明早对账结束、照算）
    _named(html)


def test_one_time_buy_cancelled_after_a_partial_fill_says_the_rest_is_not_bought():
    _buy_book("tachibana", "CANCELLED", "立花：取消済", filled_qty=30, filled_px=2650.0, broker_id="B9")   # 在立花网站撤了、之前成交 30 股
    now = _t(2026, 10, 15, 10, 30)
    html = panel.render("tachibana", "t" * 40, now)
    _top, later, ended = _parts(html)
    assert "（单已结束：没成交的部分不会再买；10/16 07:40 的对账之后结束）</span>" in _row(ended, "<b>买入 6758 ソニーグループ")
    assert later == "" and "没买到" not in ended
    assert _badge_ok(html, "tachibana", now) == 0


def test_one_time_buy_rejected_under_halt_is_not_waiting_for_halt():
    _buy_book("tachibana", "REJECTED", "立花：余力不足")
    paths.halt_file().write_text("测试", encoding="utf-8")
    try:
        now = _t(2026, 10, 15, 10, 30)
        html = panel.render("tachibana", "t" * 40, now)
        top, later, ended = _parts(html)
        assert "等 HALT 解除后" not in html and "买入 6758 ソニーグループ" in ended and later == ""
        assert _badge_ok(html, "tachibana", now) == 0
    finally:
        paths.halt_file().unlink()


@pytest.mark.parametrize("tag,status,note,now,where,when", [
    ("tachibana", "MISSED", "开盘后补单没有运行（--phase open），没买 —— 与模拟盘出现差异", _t(2026, 10, 15, 10, 30), "later",
     "等下一次决策（10/16 07:40）"),
    ("tachibana", "DEFERRED", "开盘前余力不足 → 开盘后按始値检查", _t(2026, 10, 15, 10, 30), "later", "等下一次决策（10/16 07:40）"),
    ("tachibana", "BLOCKED", "异常熔断：这次决策的规则单 30 笔", _t(2026, 10, 16, 7, 0), "top", ""),   # 今天 07:40 的运行对账后马上重新处理
    ("paper", "PLANNED", "", _t(2026, 10, 16, 16, 0), "later", "等下一次决策（10/19 07:40）"),
])
def test_system_missed_buy_waits_for_the_next_decision(tag, status, note, now, where, when):
    """系统原因没下（开盘后补单没跑 / 异常熔断 / 单没发出）→ 对账时留到那次决策重新处理（requeue）：
    下一次决策的单今天开盘（今天早上的运行还没跑完）→ 上面，否则「另有 … 等下一次决策（MM/DD 07:40）」。"""
    _buy_book(tag, status, note)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert "买入 6758 ソニーグループ" in part and "买入 6758 ソニーグループ" not in ended
    if when:
        assert f"<summary>另有 1 条{when}</summary>" in later
    assert _badge_ok(html, tag, now) == 1                                        # 系统原因：之后还会买 → 算


@pytest.mark.parametrize("now,where,when", [
    (_t(2026, 10, 15, 8, 57), "later", "等 10/16（周五）开盘"),                 # 08:55 之后被挡：今天不会再发 → 下一次决策（明天开盘）
    (_t(2026, 10, 15, 16, 0), "later", "等 10/16（周五）开盘"),
    (_t(2026, 10, 16, 7, 0), "top", ""),                                         # 今天 07:40 的运行还没跑：那次决策重新下 → 今天开盘
    (_t(2026, 10, 16, 9, 30), "later", "等 10/19（周一）开盘"),                 # 立花 08:55 之后不自动补跑 → 下一个交易日（周五 → 周一）
])
def test_blocked_manual_sell_goes_to_the_next_decisions_opening(now, where, when):
    it = {"id": "M1-sell", "kind": "sell", "ticker": "7203.T", "status": "placed", "decided_on": D, "fill_day": "2026-10-15",
          "shares": 200, "side": "SELL", "msg": "10/15 开盘卖出全部 200 股", "at": "2026-10-14T19:00:00+09:00"}
    _mbook("tachibana", D, [_morder(D, "SELL", "7203.T", "manual", "BLOCKED", "闸门：异常熔断", qty=200, sent_qty=200)], {"M1-sell": it})
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "<b>卖 7203 トヨタ自動車：200 股</b>" in ended                            # 那笔单今天不会再发 / 已收盘：收在下面
    part = top if where == "top" else later
    assert "卖出全部 7203 トヨタ自動車" in part and "卖出全部 7203 トヨタ自動車" not in (later if where == "top" else top)
    if when:
        assert f"<summary>另有 1 条{when}</summary>" in later
    _badge_ok(html, "tachibana", now)
    _named(html)


def _prev_book(last: str = D, status: str = "SENT") -> dict:
    """已下单的减仓 7203（M3，开盘的卖单 status）+ 等它成交的调仓 7203（M4，wait=prev）。"""
    f = "2026-10-15" if last == D else "2026-10-16"
    m3 = {"id": "M3-trim", "kind": "trim", "ticker": "7203.T", "pct": 50, "status": "placed", "decided_on": last, "fill_day": f,
          "shares": 100, "side": "SELL", "msg": f"{f[5:].replace('-', '/')} 开盘卖出 100 股", "at": "2026-10-14T19:00:00+09:00"}
    m4 = {"id": "M4-adj", "kind": "adjust", "ticker": "7203.T", "unit": "shares", "value": 300, "status": "pending", "wait": "prev",
          "msg": "等 7203 トヨタ自動車 的上一笔成交（最早 10/16 早上的决策）", "at": "2026-10-14T20:00:00+09:00"}
    return _mbook("tachibana", last, [_morder(last, "SELL", "7203.T", "manual_trim", status, broker_id="B1")],
                  {"M3-trim": m3, "M4-adj": m4}, {"trims": {"7203.T": {"id": "M3-trim"}}})


@pytest.mark.parametrize("last,now,trim,adj,summary", [
    (D, _t(2026, 10, 15, 10, 30), "top", "later", "另有 1 条等下一次决策（10/16 07:40）"),
    (D, _t(2026, 10, 15, 16, 0), "later", "later", "另有 2 条之后才下：1 条等 10/16（周五）开盘、1 条等下一次决策（10/16 07:40）"),
    (D, _t(2026, 10, 16, 7, 0), "top", "top", ""),                               # 今天 07:40 的运行先对账 10/15 的卖单，再处理调仓
    ("2026-10-15", _t(2026, 10, 17, 10, 0), "later", "later",                   # 周六
     "另有 2 条之后才下：1 条等 10/19（周一）开盘、1 条等下一次决策（10/19 07:40）"),
])
def test_waiting_for_the_previous_order_is_not_today(last, now, trim, adj, summary):
    """「等上一笔成交」（wait=prev）：outlook 是「会」、没有时刻 —— 那笔要第二天早上对账之后才处理（复核 2026-10-16：以前一律放在
    「今天要成交的单」里，16:00 / 周六也是，周六还因此不写「今天休市」）。"""
    _prev_book(last)
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    for what, z in (("<b>减仓 7203 トヨタ自動車", trim), ("<b>调仓 7203 トヨタ自動車", adj)):
        assert what in (top if z == "top" else later), (what, z)
        assert what not in (later if z == "top" else top), (what, z)
    if summary:
        assert f"<summary>{summary}</summary>" in later and "<div class='tsub'>手动指令</div>" in later
    if now.weekday() == 5:
        assert "<div class='tempty'>今天休市，没有要成交的单</div>" in top
    _badge_ok(html, "tachibana", now)
    _named(html)


@pytest.mark.parametrize("tag,now,orders,text", [
    ("paper", _t(2026, 10, 16, 6, 50), True, "今天的单还没排出来：今天早上 07:40 的运行还没跑（跑完之后这里才有今天的单）"),
    ("paper", _t(2026, 10, 16, 7, 30), False, "今天的单还没排出来：今天早上 07:40 的运行还没跑（跑完之后这里才有今天的单）"),
    ("tachibana", _t(2026, 10, 16, 7, 0), False, "今天的单还没排出来：今天早上 07:40 的运行还没跑（跑完之后这里才有今天的单）"),
    ("paper", _t(2026, 10, 16, 10, 0), True, "今天的单还没排出来：今天早上的运行还没跑完（跑完之后这里才有今天的单）"),
    ("paper", _t(2026, 10, 16, 12, 0), True, "今天的单还没排出来：今天早上的运行还没跑完（过了 11:30：补跑之后排的单今天不再撮合，"
                                              "等 10/19（周一）07:40 的运行按今天的开盘价记）"),   # 复核 5：过了今天的开盘撮合
    ("tachibana", _t(2026, 10, 16, 9, 30), False, "今天早上的运行没跑成（立花 08:55 之后不自动补跑）：补跑了这里才有今天的单"),
    ("tachibana", _t(2026, 10, 16, 16, 0), True, "今天没有要成交的单了"),     # 收盘后：今天确实不会再有
])
def test_empty_before_the_morning_run_does_not_say_nothing_today(tag, now, orders, text):
    """交易日、今天早上的运行还没跑完（成交日不是今天）：今天的单还没排出来 —— 不写「今天没有要成交的单了」（复核 2026-10-16：
    上一次决策没有单时连「上一次决策的单」那一行也没有，看起来像今天什么都不会下）。"""
    b = _done_book("2026-10-14", tag)
    if not orders:
        b["orders"] = []
        _save(b, tag)
    html = panel.render(tag, "t" * 40, now)
    top, _later, _ended = _parts(html)
    assert f"<div class='tempty'>{text}</div>" in top
    if text != "今天没有要成交的单了":
        assert "今天没有要成交的单了" not in top
    if orders:
        assert "执行器的单是上一次决策的单（成交日 10/15），不是今天的" in top
    _badge_ok(html, tag, now)


def test_registered_corefix_points_at_the_block_it_is_in():
    """ETF 下面「已登记：恢复按规则（…要撤回在 …）」指着那条指令真正在的那一块（复核 2026-10-16：以前写「「交易」→「手动指令」」，
    「手动指令」卡片拆开之后，收盘后写的在收起的「另有 …」里，页面上没有「手动指令」这几个字）。"""
    now = _t(2026, 10, 16, 19, 0)
    b = _done_book("2026-10-15")
    b["manual"]["core_fix"] = {"1482.T": 678}
    b["core_rule"]["lot"]["1482.T"] = 1
    _save(b)
    kl = {"items": {"1482.T": {"kind": "core", "name": "1482.T"}, "1545.T": {"kind": "core", "name": "1545.T"}}}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"kline": kl}), encoding="utf-8")
    MO.append("paper", {"kind": "corefix", "ticker": "1482", "clear": True}, clock=lambda: now)
    html = panel.render("paper", "t" * 40, now)
    top, later, _ended = _parts(html)
    assert "要撤回在「交易」→ 点开「另有 …」的「手动指令」" in html and "要撤回在「交易」→「手动指令」" not in html
    assert "1482 对冲版美国 7〜10 年国债 恢复按规则" in later and "<div class='tsub'>手动指令</div>" in later
    assert "<summary>另有 1 条等 10/19（周一）开盘</summary>" in later


def test_system_miss_is_one_function_for_orders_and_book_rows():
    """live_unified.system_miss：执行器对账（ExecOrder）与面板分块（账本里的 dict）同一个判断；requeue_next 加上对账时
    DEFERRED → MISSED / 凑钱的卖单都没成交 → SKIPPED「钱没来」。"""
    from qbreak.live_unified import ExecOrder, UnifiedExecutor, requeue_next, system_miss
    for st, note, kw in (("MISSED", "开盘后补单没有运行（--phase open），没买", {}), ("BLOCKED", "异常熔断：x", {}),
                         ("REJECTED", "余力不足", {}), ("SKIPPED", GAP, {}), ("PLANNED", "", {}), ("BLOCKED", "未 ARM：x", {}),
                         ("MISSED", "x", {"broker_id": "S1"}), ("BLOCKED", "异常熔断", {"phase": "now"})):
        o = ExecOrder("c", "B.T", "BUY", "stock", 100, D, status=st, note=note, **kw)
        d = {"cid": "c", "ticker": "B.T", "side": "BUY", "kind": "stock", "qty": 100, "decided_on": D, "status": st, "note": note, **kw}
        assert UnifiedExecutor._system_miss(o) == system_miss(d), (st, note, kw)
    now = _t(2026, 10, 15, 10, 30)
    f = dt.date(2026, 10, 15)
    sell = {"cid": "S", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 100, "status": "CANCELLED", "decided_on": D}
    buy = {"cid": "B", "ticker": "1482.T", "side": "BUY", "kind": "core", "status": "DEFERRED", "decided_on": D, "note": "x"}
    assert requeue_next(buy, [sell, buy], now, f)                                 # 开盘后补单没跑 → MISSED（系统原因）
    assert not requeue_next({**buy, "fund_src": ["S"]}, [sell, buy], now, f)      # 凑钱的卖单撤了 → 钱没来（不是系统原因）
    assert not requeue_next({**buy, "status": "REJECTED"}, [buy], now, f)


# ────────── 复核 2（2026-10-16）：标签上的数字没有例外 ──────────
def test_badge_does_not_count_a_one_time_buy_that_will_not_buy(monkeypatch):
    """用户 2026-10-15「撤单后 / 没有执行下单等等的话交易处的数字不显示」：手动买入只做一次，单被拒（不是系统原因）→ 不会再买 →
    收在「已结束」、数字也不算（以前指令还是「已下单」、等明早对账才结束 → 数字照算）。判断就是 _trade_split 的那一个
    （live_unified.requeue_next）：系统原因没下（开盘后补单没跑）→ 之后还会买 → 在「另有」、算。
    数字 = 上面（不含撤单中）+「另有」：/api/status 的 pending 同一个数。"""
    now = _t(2026, 10, 15, 10, 30)
    b = _prev_book()                                                             # 减仓 7203（卖单挂着）+ 等它成交的调仓 7203
    b["orders"].append(_morder(D, "BUY", "6758.T", "manual_buy", "REJECTED", "立花：余力不足（sOrderStatusCode=7）"))
    b["manual"]["items"][BUY_ID] = _buy_book("tachibana", "REJECTED")["manual"]["items"][BUY_ID]
    b["manual"]["buys"] = {"6758.T": {"id": BUY_ID}}
    _save(b, "tachibana")
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "<b>买入 6758 ソニーグループ" in ended and "买入 6758" not in top + later
    assert "<b>卖 7203 トヨタ自動車：100 股</b>" in top and "<b>减仓 7203 トヨタ自動車" in top and "<b>调仓 7203 トヨタ自動車" in later
    assert _badge_ok(html, "tachibana", now) == 3                                # 卖单 + 减仓指令 + 调仓（另有）；买入不算
    lv = panel._trade_live(b, [], now, "tachibana", halt=False)
    assert lv["n"] == 3 and lv["split"]["items"][BUY_ID] == "ended"
    monkeypatch.setattr(panel, "now_jst", lambda: now)
    assert panel.status_json("tachibana")[1]["pending"] == 3
    _named(html)
    b["orders"][-1].update(status="MISSED", note="开盘后补单没有运行（--phase open），没买 —— 与模拟盘出现差异")   # 系统原因
    _save(b, "tachibana")
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "<b>买入 6758 ソニーグループ" in later and "<summary>另有 2 条等下一次决策（10/16 07:40）</summary>" in later
    assert _badge_ok(html, "tachibana", now) == 4


@pytest.mark.parametrize("now", [_t(2026, 10, 15, 10, 30), _t(2026, 10, 15, 16, 0)])
def test_badge_counts_an_unknown_status_order_until_it_is_registered(now):
    """状态不明（ERROR）的单：在上面就算（复核 2：以前在上面却不算，与发送中 SENDING 不一样）。收盘后也一样（复核 3，有意改的期望：
    以前收盘后当成「已收盘：这笔没下，明早对账记账」收进「已结束」、不算 —— 可它可能已经成交，执行器登记之前每次运行都停下）。"""
    from qbreak import live_ops as LO
    _book1015("tachibana", sell="ERROR", cash=2_000_000.0, fix={})
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    assert SELL_B in top and SELL_B not in ended
    assert "<span class='chip'>状态不明</span>" in _row(top, SELL_B)
    if now.hour >= 16:
        assert LO.UNK_CLOSED in _row(top, SELL_B) and "<span class='chip'>已收盘</span>" not in _row(top, SELL_B)
    assert _badge_ok(html, "tachibana", now) == 1


def test_badge_same_before_and_after_the_executor_reads_a_corefix():
    """固定口数：执行器还没读（指令文件里）与读了、还没照它调（「生效中 · 还没照它调」）都是之后要照它买卖的同一件事 → 数字一样
    （复核 2：以前读了之后数字少 1，什么都没成交）。"""
    b = _book1015(fix={})
    b["orders"] = []
    _save(b)
    _want({"id": "M20261014-190000-corefix-1482", "kind": "corefix", "ticker": "1482.T", "units": 678, "at": "2026-10-14T19:00:00+09:00"})
    html = panel.render("paper", "t" * 40, AT15)
    assert "固定 1482 对冲版美国 7〜10 年国债：678 口" in _parts(html)[0]
    before = _badge_ok(html, "paper", AT15)
    MO.requests_path("paper").unlink()
    _fixwait()
    html = panel.render("paper", "t" * 40, AT15)
    assert f"<span class='chip'>{MO.FIX_WAIT}</span>" in _parts(html)[0]
    assert _badge_ok(html, "paper", AT15) == before == 1


# ────────── 复核 3（2026-10-16）──────────
def _etf_book(tag: str) -> dict:
    """10/15 的决策之后（成交日 10/16）：拿着 1545.T 4,010 口，规则目标额是 10/15 的决策算的、闲置资金比例 100% 已照它调过、没有固定口数。"""
    b = _done_book("2026-10-15", tag)
    b["core_rule"] = {"lot": {"1545.T": 10, "1482.T": 1}, "units100": {"1545.T": 4010}, "decided_on": "2026-10-15",
                      "applied": 100.0, "pct": 100.0, "px": {"1545.T": 244.0}, "fix_applied": {}}
    b["manual"]["core_pct"] = 100.0
    return _save(b, tag)


ETF_REC = {"core": ({"kind": "core", "ticker": "1545.T", "pct": 0.0, "target": 0}, "<b>卖出全部 1545 纳斯达克 100（之后停买闲置资金 ETF）</b>"),
           "corefix": ({"kind": "corefix", "ticker": "1482.T", "units": 678}, "<b>固定 1482 对冲版美国 7〜10 年国债：678 口（不按规则自动调）</b>")}


@pytest.mark.parametrize("kind", ["core", "corefix"])
def test_etf_instruction_counts_the_same_before_and_after_the_read_and_after_halt(kind):
    """HALT 中写的闲置资金比例 / 固定口数：执行器还没读（等 HALT 解除后）、09:05 的运行读了（读到就生效、HALT 中不下单）、HALT 解除之后
    （面板马上叫执行器照它买卖：now_due）—— 都是之后要照它买卖 ETF 的同一件事 → 每次都在上面 /「另有」、数字一样（复核 3：
    以前比例读了之后指令「完成」→「已结束」、数字 0，HALT 解除后面板照样马上卖 1545；固定口数早就有「生效中 · 还没照它调」那一行）。"""
    tag = "tachibana"
    paths.halt_file().write_text("测试", encoding="utf-8")
    b = _etf_book(tag)
    rid = f"M20261016-080000-{kind}"
    rec, head = ETF_REC[kind]
    _want({"id": rid, **rec, "at": "2026-10-16T08:00:00+09:00"}, tag)
    now = _t(2026, 10, 16, 8, 30)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    assert "<summary>另有 1 条等 HALT 解除后</summary>" in later and f"data-id='{rid}'" in later
    before = _badge_ok(html, tag, now)
    assert before == 1
    run = _t(2026, 10, 16, 9, 5)                                               # 09:05 开盘后的运行：读指令（HALT 中读到就生效、不下单）
    man = MO.Manual(b, tag, clock=lambda: run)
    man.ingest()
    man.halt_mark(True)
    _save(b, tag)
    assert b["manual"]["items"][rid]["status"] == "done" and b["manual"]["items"][rid]["halt"]
    now = _t(2026, 10, 16, 10, 30)
    assert not MO.now_due(tag, b, now)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    assert "<summary>另有 1 条等 HALT 解除后</summary>" in later and head in later and head not in top + ended
    assert f"<span class='chip'>{MO.FIX_WAIT}</span>" in _row(later, head)
    assert _badge_ok(html, tag, now) == before
    paths.halt_file().unlink()                                                 # 你在 Mac 上解除 HALT：盘中 → 面板马上叫执行器照它买卖
    assert MO.now_due(tag, b, now)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    assert head in top and later == "" and head not in ended
    assert f"<span class='chip'>{MO.FIX_WAIT}</span>" in _row(top, head)
    assert _badge_ok(html, tag, now) == before
    _named(html)


CORE50 = "<b>调仓 1545 纳斯达克 100 → 约 2,000 口（闲置资金比例 50%）</b>"


@pytest.mark.parametrize("cr,now,where,summary", [
    ({"tried": "2026-10-16T10:01:00+09:00"}, _t(2026, 10, 16, 10, 3), "top", None),       # 盘中没调成：10 分钟内面板再叫 → 今天
    ({"defer": "2026-10-16"}, _t(2026, 10, 16, 10, 3), "later", "另有 1 条等 10/19（周一）开盘"),   # 执行器说了下一次决策再调
    ({}, _t(2026, 10, 16, 16, 0), "later", "另有 1 条等 10/19（周一）开盘"),                    # 收盘后：下一次决策（周五 → 下周一）
])
def test_core_ratio_read_but_not_applied_follows_the_executor(cr, now, where, summary):
    """闲置资金比例读了、还没照它调（manual.core_pct ≠ core_rule.applied：与执行器 _core_pending / now_due 同一个判断 MO.core_pending）
    → 那条指令「生效中 · 还没照它调」、跟 outlook 的 core: 那一行放（一会儿再试 = 今天；今天说了下一次决策再调 / 收盘后 = 下一次决策那天开盘）、
    算进数字；持仓 ETF 下面「还没照它调完，见 …」指着那一块。照它调完（applied = 50）→ 完成、收进「已结束」、不算。"""
    from qbreak import live_ops as LO
    tag = "paper"
    b = _etf_book(tag)
    rid = "M20261016-100000-core"
    b["manual"]["core_pct"] = 50.0
    b["manual"]["items"][rid] = {"id": rid, "kind": "core", "ticker": "1545.T", "pct": 50.0, "target": 2000, "status": "done",
                                 "at": "2026-10-16T10:00:00+09:00", "msg": "闲置资金比例设为 50%（1545 纳斯达克 100 约 2,000 口）"}
    b["core_rule"].update(cr)
    _save(b, tag)
    assert MO.core_pending(b) == 50.0                                          # 下一次决策会照新比例调
    assert (MO.core_pending(b, now) is None) == ("defer" in cr)                # 盘中那条路（面板 now_due 同一个判断）：今天说了下一次决策再调 → 不调
    x = LO.outlook(b, [], now, tag=tag, halt=False)["items"]["core:"]
    assert x["iid"] == rid and x["state"] == ("will" if where == "top" else "later")
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert CORE50 in part and CORE50 not in ended and f"<span class='chip'>{MO.FIX_WAIT}</span>" in _row(part, CORE50)
    if summary:
        assert f"<summary>{summary}</summary>" in later
    assert _badge_ok(html, tag, now) == 1
    pane = ("「交易」→「今天要成交的单」的「手动指令」" if where == "top" else "「交易」→ 点开「另有 …」的「手动指令」")
    assert f"闲置资金比例 50%（还没照它调完，见{pane}）" in html
    _named(html)
    b["core_rule"]["applied"] = 50.0                                           # 照它调完了
    _save(b, tag)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    assert CORE50 in ended and "<span class='chip'>完成</span>" in _row(ended, CORE50) and CORE50 not in top + later
    assert "还没照它调完" not in html and _badge_ok(html, tag, now) == 0


def test_core_ratio_without_its_instruction_row_gets_one_line():
    """比例还没照它调、账本里却没有那条比例指令（整理账本时删掉了 / 旧账本）→ 补一行（没有按钮），照样算。"""
    tag = "paper"
    b = _etf_book(tag)
    b["manual"]["core_pct"] = 50.0
    _save(b, tag)
    now = _t(2026, 10, 16, 10, 3)
    html = panel.render(tag, "t" * 40, now)
    top, _later, _ended = _parts(html)
    assert "<b>闲置资金比例 50%（还没照它调）</b>" in top and f"<span class='chip'>{MO.FIX_WAIT}</span>" in top
    assert _badge_ok(html, tag, now) == 1
    assert "闲置资金比例 50%（还没照它调完，见「交易」→「今天要成交的单」的「手动指令」）" in html


@pytest.mark.parametrize("status", ["ERROR", "SENDING"])
def test_unknown_status_order_after_close_waits_for_registration_not_ended(status):
    """立花状态不明（结果不明 ERROR / 发送中 SENDING）的单：收盘后不是「已收盘：这笔没下 / 已失效，明早对账记账（之后什么都不会再发生）」——
    它可能已经成交，执行器每次运行（07:40 的决策、开盘后、盘中）登记之前都停下（_raise_if_unknown）。复核 3：单留在上面、写清要核对登记；
    靠它的手动指令（卖出全部 7203）不是「等 MM/DD 开盘」，是「等登记状态不明的单」（MO.UNK_LATER）。收盘前照旧（还可能成交）。"""
    from qbreak import live_ops as LO
    tag = "tachibana"
    it = {"id": "M1-sell", "kind": "sell", "ticker": "7203.T", "status": "placed", "decided_on": D, "fill_day": "2026-10-15",
          "shares": 200, "side": "SELL", "msg": "10/15 开盘卖出全部 200 股", "at": "2026-10-14T19:00:00+09:00"}
    _mbook(tag, D, [_morder(D, "SELL", "7203.T", "manual", status, "发送超时", qty=200, sent_qty=200,
                            sent_at="2026-10-15T08:00:00+09:00")], {"M1-sell": it})
    head, item = "<b>卖 7203 トヨタ自動車：200 股</b>", "<b>卖出全部 7203 トヨタ自動車</b>"
    for now, closed in ((_t(2026, 10, 15, 10, 30), False), (_t(2026, 10, 15, 16, 0), True), (_t(2026, 10, 16, 7, 0), True),
                        (_t(2026, 10, 16, 10, 0), True)):
        html = panel.render(tag, "t" * 40, now)
        top, later, ended = _parts(html)
        assert head in top and head not in ended, now
        row = _row(top, head)
        assert "这笔没下" not in html and "明早对账记账" not in html and "<span class='chip'>已收盘</span>" not in row
        assert "状态不明的单：去立花网站的注文一覧核对" in html                     # 最上面的提醒照旧
        if closed:
            assert "<span class='chip'>状态不明</span>" in row and LO.UNK_CLOSED in row
            assert "<summary>另有 1 条等登记状态不明的单</summary>" in later and item in later and item not in top
            assert MO.UNK_LATER in _row(later, item) and "开盘</summary>" not in later
        else:
            assert f"<span class='chip'>{LO.STATUS_TEXT[status]}</span>" in row and item in top and later == ""
        assert _badge_ok(html, tag, now) == 2                                  # 单 + 靠它的指令：收盘前后一样
        _named(html)


@pytest.mark.parametrize("now,where", [(_t(2026, 10, 15, 10, 0), "top"), (_t(2026, 10, 15, 12, 0), "later"),
                                       (_t(2026, 10, 15, 16, 0), "later")])
def test_paper_open_matching_orders_move_together_after_the_window(now, where):
    """模拟账户成交日 09:25〜11:30 的开盘撮合：排队的寄付单（SENT）与等开盘后的买单（DEFERRED）一起撮合；到 11:30 没做成 → 都是第二天早上
    07:40 的运行按日线撮合（执行器 _paper_settle 的 queued + dfr）。复核 3：以前只有买单去「另有 … 07:40 的运行」，寄付单还写在「今天要成交的单」。"""
    from qbreak import live_ops as LO
    b = _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert SELL_B in part and BUY_B in part
    ol = LO.outlook(b, [], now, tag="paper", halt=False)
    if where == "later":
        assert "<summary>另有 2 条等 10/16（周五）07:40 的运行</summary>" in later and SELL_B not in top
        assert ol["orders"][SELL]["state"] == ol["orders"][BUY]["state"] == "later"
        assert ol["orders"][SELL]["act_at"] == ol["orders"][BUY]["act_at"] == _t(2026, 10, 16, 7, 40)
        assert ol["orders"][SELL]["reason"] == ("成交日 10/15 的开盘撮合（09:25〜11:30）没做成 → 10/16 07:40 的运行按 10/15 的正式开盘价"
                                                "照旧撮合")
    assert _badge_ok(html, "paper", now) == 2


# ────────── 复核 4（2026-10-16）──────────
@pytest.mark.parametrize("now,where,run", [
    (_t(2026, 10, 16, 7, 30), "top", "今天 07:40 的运行"),                         # 07:40 之前：今天 07:40 的运行撮合
    (_t(2026, 10, 16, 8, 0), "top", "今天早上的运行（还没完成：面板会自动补跑）"),     # 早上的运行没完成：面板补跑（07:45〜15:30）
    (_t(2026, 10, 16, 10, 30), "top", "今天早上的运行（还没完成：面板会自动补跑）"),
    (_t(2026, 10, 16, 14, 0), "top", "今天早上的运行（还没完成：面板会自动补跑）"),
    (_t(2026, 10, 16, 16, 0), "later", "10/19 07:40 的运行"),                     # 15:30 之后不补跑：下一个交易日（周五 → 周一）
])
def test_paper_stale_morning_queued_orders_are_matched_by_todays_catch_up(monkeypatch, now, where, run):
    """模拟账户成交日（10/15）的开盘撮合没做成、第二天（10/16）早上的运行也还没完成：排队的寄付单（SENT）与等开盘后的买单（DEFERRED）
    由今天早上的运行（07:40 / 面板 07:45〜15:30 的补跑：run_bar 的 _paper_open）按成交日 10/15 的开盘价撮合 → 在「今天要成交的单」。
    复核 4：以前 07:40 之后写「另有 2 条等 10/19（周一）07:40 的运行」（补跑却在今天撮合了），买单还写「今天的开盘撮合没下成」（是 10/15 的）。"""
    from qbreak import live_ops as LO
    b = _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})
    assert MO.morning_behind(b, now)
    ol = LO.outlook(b, [], now, tag="paper", halt=False)
    s, y = ol["orders"][SELL], ol["orders"][BUY]
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    if where == "top":
        assert s["state"] == y["state"] == "will" and s["act_at"].date() == y["act_at"].date() == now.date()
        assert s["act_at"] == (_t(2026, 10, 16, 7, 40) if now.hour < 8 else now) == y["act_at"]
        assert SELL_B in top and BUY_B in top and later == ""
    else:
        assert s["state"] == y["state"] == "later" and s["act_at"] == y["act_at"] == _t(2026, 10, 19, 7, 40)
        assert "<summary>另有 2 条等 10/19（周一）07:40 的运行</summary>" in later and SELL_B not in top
    assert s["reason"] == f"成交日 10/15 的开盘撮合（09:25〜11:30）没做成 → {run}按 10/15 的正式开盘价照旧撮合"
    assert y["reason"] == f"成交日 10/15 的开盘撮合（09:25〜11:30）没下成 → {run}按 10/15 的开盘价照旧撮合（钱够才买）"
    part = top if where == "top" else later                                      # 行里写这句，不写 07:40 存下的「次日开盘成交」/「减股再下」
    assert s["reason"] in _row(part, SELL_B) and y["reason"] in _row(part, BUY_B)
    assert "已排队，次日开盘成交" not in part and "减股再下" not in part
    assert _badge_ok(html, "paper", now) == 2
    _named(html)
    if now.hour in (10, 14):                                                     # 说的「面板会自动补跑」就是 Trigger 的那条路
        ag = paths.launch_agents()
        ag.mkdir(parents=True, exist_ok=True)
        (ag / f"{paths.PAPER_AGENT}.plist").write_text("x", encoding="utf-8")
        m = [1000.0]
        trg = panel.Trigger(run=lambda tag, mode="retry": None, clock=lambda: now, mono=lambda: m[0], notify=lambda *a: None)
        assert not trg._catchup_due("paper", b, now)                             # 第一次看到：先等 2 分钟
        m[0] += panel.CATCHUP_GRACE_S
        assert trg._catchup_due("paper", b, now)


def test_paper_queued_orders_under_halt_or_on_the_fill_day_wait_for_the_next_run():
    """HALT 中面板不补跑 → 下一个交易日 07:40（等开盘后的买单 HALT 时照旧「不会下单（HALT）」）；成交日当天 11:30 之后 → 明早 07:40，
    买单的说明按成交日的开盘价（以前写「按那天的开盘价」= 那次运行那天的，撮合按的是成交日的）。"""
    from qbreak import live_ops as LO
    b = _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})
    now = _t(2026, 10, 16, 10, 30)
    ol = LO.outlook(b, [], now, tag="paper", halt=True)
    assert ol["orders"][SELL]["state"] == "later" and ol["orders"][SELL]["act_at"] == _t(2026, 10, 19, 7, 40)
    assert ol["orders"][SELL]["reason"].startswith("成交日 10/15 的开盘撮合（09:25〜11:30）没做成 → 10/19 07:40 的运行")
    assert ol["orders"][BUY]["state"] == "wont" and ol["orders"][BUY]["cls"] == "halt"
    for hm in ((12, 0), (16, 0)):
        now = _t(2026, 10, 15, *hm)
        ol = LO.outlook(b, [], now, tag="paper", halt=False)
        assert ol["orders"][SELL]["state"] == ol["orders"][BUY]["state"] == "later"
        assert ol["orders"][BUY]["act_at"] == _t(2026, 10, 16, 7, 40)
        assert ol["orders"][BUY]["reason"] == ("今天的开盘撮合（09:25〜11:30）没下成 → 10/16 07:40 的运行按 10/15 的开盘价照旧撮合"
                                               "（钱够才买）")


FIX500 = "M20261015-075500-corefix-1482"


@pytest.mark.parametrize("tag", ["paper", "tachibana"])
@pytest.mark.parametrize("now", [_t(2026, 10, 15, 8, 0), _t(2026, 10, 15, 10, 30)])
def test_withdrawn_unread_corefix_does_not_hide_the_fix_still_to_apply(tag, now):
    """读了、还没照它调的固定口数（1482 678 口）+ 又写了一条还没读的固定 500 口、马上撤回（都还在指令文件里）：撤回的那条不算
    （与 MO.core_fixed / corefix_pending 同一个过滤）→ 678 口那一行照旧今天（09:00 开盘后 / 盘中马上），执行器也照它下（now_due）。
    复核 4：以前撤回的那条把 fix:1482 那一行藏掉，678 口去了「另有 1 条等下一次决策」。"""
    from qbreak import live_ops as LO
    b, _, _ = _fixwait()
    _save(b, tag)
    _want({"id": FIX500, "kind": "corefix", "ticker": "1482.T", "units": 500, "at": "2026-10-15T07:55:00+09:00"}, tag)
    _want({"id": "M20261015-075600-cancel", "kind": "cancel", "target": FIX500, "at": "2026-10-15T07:56:00+09:00"}, tag)
    ol = LO.outlook(b, MO.unseen(tag, b), now, tag=tag, halt=False)
    x = ol["items"]["fix:1482.T"]
    assert x["state"] == "will" and x["act_at"].date() == now.date() and FIX500 not in ol["items"]
    assert MO.now_due(tag, b, now) == (now.hour >= 9)                          # 盘中：面板马上叫执行器照 678 口下
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    head = "<b>固定 1482 对冲版美国 7〜10 年国债：678 口"
    assert head in top and later == "" and head not in ended
    assert f"<span class='chip'>{MO.FIX_WAIT}</span>" in _row(top, head)
    assert "500 口" not in top + later                                          # 撤回了的那条：收在「已结束」
    assert _badge_ok(html, tag, now) == 1
    _named(html)


def test_fix_wait_without_its_outlook_row_follows_the_fix_timing():
    """还没照它调的固定口数、outlook 没给 fix:<票> 那一行：今天说了「下一次决策再调」（core_rule.fix_defer）→「等下一次决策」（复核 4）。
    又写了一条还没读的同样口数（outlook 那一行就是新的那条）→ 读了的旧的那条收进「已结束」（「已被新写的那条取代」），只算新的那一行；
    执行器读了之后新的那条「生效中 · 还没照它调」→ 数字读之前读之后一样（复核 5，2026-10-16：以前两行都在上面、都算，读了之后数字少 1）。"""
    now = _t(2026, 10, 15, 10, 30)
    b, _, _ = _fixwait()
    old, new = "M20261014-190000-corefix-1482", "M20261015-102500-corefix-1482"
    _want({"id": new, "kind": "corefix", "ticker": "1482.T", "units": 678, "at": "2026-10-15T10:25:00+09:00"})
    sp = panel._trade_split(b, MO.unseen("paper", b), now, "paper", False)
    assert sp["items"][old] == "ended" and sp["items"][new] == "today" and not sp["extra"]
    assert sp["itxt"][old] == "（已被新写的那条取代：执行器读到之后照新的调）"
    assert MO.fix_status_text(b["manual"]["items"][old], list(b["manual"]["items"].values()), b, "paper") is None
    head = "<b>固定 1482 对冲版美国 7〜10 年国债：678 口（不按规则自动调）</b>"
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    assert top.count(head) == 1 and head not in later and f"data-id='{new}'" in top
    assert "<span class='chip'>完成（已被新写的那条取代：执行器读到之后照新的调）</span>" in _row(ended, head)
    before = _badge_ok(html, "paper", now)
    assert before == 1
    man = MO.Manual(b, "paper", clock=lambda: now)                            # 执行器读了新的那条（还没照它调）
    man.ingest()
    _save(b)
    assert b["manual"]["items"][new]["status"] == "done" and not MO.unseen("paper", b)
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    assert top.count(head) == 1 and f"<span class='chip'>{MO.FIX_WAIT}</span>" in _row(top, head) and later == ""
    assert "<span class='chip'>完成</span>" in _row(ended, head)
    assert _badge_ok(html, "paper", now) == before
    _named(html)
    MO.requests_path("paper").unlink()
    b, _, _ = _fixwait()
    b["core_rule"]["fix_defer"] = {"1482.T": {"day": "2026-10-15", "units": 678}}
    _save(b)
    sp = panel._trade_split(b, [], now, "paper", False)
    assert sp["items"][old] == "later" and sp["when"][old][-1] == "等下一次决策（10/16 07:40）"
    html = panel.render("paper", "t" * 40, now)
    assert _badge_ok(html, "paper", now) == 1


@pytest.mark.parametrize("now", [_t(2026, 10, 15, 16, 0), _t(2026, 10, 16, 10, 0)])
def test_closed_unknown_order_holds_every_instruction_until_registered(now):
    """立花收盘后状态不明的单（买 6758 结果不明）：登记之前执行器每次运行开头都停下（_raise_if_unknown）→ 不只靠它的那条买入，
    旁边别的还没结束的指令（卖出全部 7203、还没读的固定口数）也都「等登记状态不明的单」，不是「等 MM/DD 开盘」；数字不变（复核 4）。
    买入只做一次：登记 0 股 → 指令结束 → 写 MO.UNK_LATER_BUY（不是「登记之后的下一次决策处理」）；卖出照旧 MO.UNK_LATER。"""
    tag = "tachibana"
    b = _buy_book(tag, "ERROR", "发送超时", sent_at="2026-10-15T08:00:00+09:00")
    b["manual"]["items"]["M5-sell"] = {"id": "M5-sell", "kind": "sell", "ticker": "7203.T", "status": "pending",
                                       "at": "2026-10-15T08:30:00+09:00"}
    b["core_rule"] = {"lot": {"1482.T": 1, "1545.T": 10}, "fix_applied": {}}
    _save(b, tag)
    _want({"id": "M20261015-160500-corefix-1482", "kind": "corefix", "ticker": "1482.T", "units": 678,
           "at": "2026-10-15T16:05:00+09:00"}, tag)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    order = "<b>买 6758 ソニーグループ：100 股</b>"
    assert order in top and "<span class='chip'>状态不明</span>" in _row(top, order)
    assert "<summary>另有 3 条等登记状态不明的单</summary>" in later and "开盘</summary>" not in later
    buy, sell, fix = "<b>买入 6758 ソニーグループ", "<b>卖出全部 7203 トヨタ自動車", "<b>固定 1482 对冲版美国 7〜10 年国债：678 口"
    assert MO.UNK_LATER_BUY in _row(later, buy) and MO.UNK_LATER not in _row(later, buy)
    assert MO.UNK_LATER in _row(later, sell) and MO.UNK_LATER in _row(later, fix)
    assert all(x not in top + ended for x in (buy, sell, fix))
    assert "· 10/16 开盘" not in later and "· 10/19 开盘" not in later           # 还没读的那条不再写平常的「什么时候」
    assert _badge_ok(html, tag, now) == 4                                       # 单 + 3 条指令：与收盘前一样都算
    _named(html)


# ────────── 复核 5（2026-10-16）──────────
CORE50_M = "<b>调仓 1545 纳斯达克 100 → 约 2,000 口（闲置资金比例 50%）</b>"
FIX_M = "<b>固定 1482 对冲版美国 7〜10 年国债：678 口（不按规则自动调）</b>"
SELL_M, SONY_M = "<b>卖出全部 7203 トヨタ自動車", "<b>卖出全部 6758 ソニーグループ"
LATE = "补跑之后等 10/19（周一）07:40 的运行（过了 11:30：补跑排的单今天不再撮合，按 10/16 的开盘价记）"


def _late_book() -> dict:
    """模拟账户 10/16（周五），今天早上的运行还没完成（上一次决策 10/14、成交日 10/15）：
    卖出全部 7203（10/15 开盘的单被挡 → 下一次决策再卖）、闲置资金比例 50% 读了还没照它调、还没读的固定 1482 678 口、还没读的卖出全部 6758。"""
    it = {"id": "M1-sell", "kind": "sell", "ticker": "7203.T", "status": "placed", "decided_on": D, "fill_day": "2026-10-15",
          "shares": 200, "side": "SELL", "msg": "10/15 开盘卖出全部 200 股", "at": "2026-10-14T19:00:00+09:00"}
    core = {"id": "M20261014-190500-core", "kind": "core", "ticker": "1545.T", "pct": 50.0, "target": 2000, "status": "done",
            "at": "2026-10-14T19:05:00+09:00", "msg": "闲置资金比例设为 50%（1545 纳斯达克 100 约 2,000 口）"}
    b = _mbook("paper", D, [_morder(D, "SELL", "7203.T", "manual", "BLOCKED", "闸门：异常熔断", qty=200, sent_qty=200)],
               {"M1-sell": it, core["id"]: core})
    b["state"]["pos"]["6758.T"] = {"shares": 100, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}
    b["state"]["core_units"] = {"1545.T": 4010}
    b["core_rule"] = {"lot": {"1545.T": 10, "1482.T": 1}, "units100": {"1545.T": 4010}, "decided_on": D, "applied": 100.0,
                      "pct": 100.0, "px": {"1545.T": 244.0}, "fix_applied": {}}
    b["manual"]["core_pct"] = 50.0
    _save(b)
    _want({"id": "M20261015-200000-corefix-1482", "kind": "corefix", "ticker": "1482.T", "units": 678, "at": "2026-10-15T20:00:00+09:00"})
    _want({"id": "M20261015-200500-sell-6758", "kind": "sell", "ticker": "6758.T", "block_days": 20, "at": "2026-10-15T20:05:00+09:00"})
    return b


@pytest.mark.parametrize("now,where", [(_t(2026, 10, 16, 10, 30), "top"), (_t(2026, 10, 16, 12, 0), "later")])
def test_paper_catch_up_after_the_open_window_is_matched_at_the_next_run(now, where):
    """模拟账户今天早上的运行没完成、面板会补跑：补跑那次决策排的单（闲置资金比例 / 固定口数调的核心 ETF、没卖完的手动卖出）都是开盘撮合的单，
    今天的开盘撮合（09:25〜11:30）之内补跑 → 今天撮合；过了 11:30 → 下一个交易日 07:40 的运行按今天的开盘价撮合（LO.paper_late_catchup：
    补跑之后那些单的「等 10/19（周一）07:40 的运行」同一个结论）→ 补跑之前就写「另有 … 等 10/19（周一）07:40 的运行」（复核 5：以前补跑之前在上面，
    补跑之后同一件事去了「另有」）。还没读的手动卖出不在其列：补跑过了 08:55 不排进那次决策（寄付来不及 → 开盘后马上下），今天按现价卖 → 照旧在上面。
    数字照算（之后还会做）。"""
    from qbreak import live_ops as LO
    b = _late_book()
    assert MO.morning_behind(b, now)
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    assert SONY_M in top and SONY_M not in later + ended                             # 还没读的卖出：补跑之后盘中马上卖（今天）
    for head in (SELL_M, CORE50_M, FIX_M):
        assert head in (top if where == "top" else later) and head not in ended
    if where == "later":
        assert "<summary>另有 3 条等 10/19（周一）07:40 的运行</summary>" in later
        for head in (SELL_M, CORE50_M, FIX_M):
            assert LATE in _row(later, head)
        assert LATE not in top
    else:
        assert later == "" and LATE not in top
    ol = LO.outlook(b, MO.unseen("paper", b), now, tag="paper", halt=False)
    late = [x for x in ol["items"].values() if x.get("cls") == "catchup"]
    assert len(late) == (2 if where == "later" else 0)                               # 比例那一行与没读的固定口数（09:30 自检 / 推送同一个判断）
    assert all(x["state"] == "later" and x["act_at"] == _t(2026, 10, 19, 7, 40) for x in late)
    assert _badge_ok(html, "paper", now) == 4
    _named(html)
    paths.halt_file().write_text("测试", encoding="utf-8")                          # HALT 中不补跑：照旧「等 HALT 解除后」
    html = panel.render("paper", "t" * 40, now)
    assert LATE not in html
    paths.halt_file().unlink()


@pytest.mark.parametrize("now,where", [(_t(2026, 10, 16, 10, 30), "top"), (_t(2026, 10, 16, 12, 0), "later")])
def test_paper_catch_up_orders_say_the_same_after_the_catch_up(now, where):
    """补跑之后（10/15 的 K 线的决策、成交日 10/16）：卖 7203、卖 1545 都是开盘撮合的单 → 与补跑之前那几行同一块、同一句「等 10/19（周一）07:40 的运行」。"""
    last = "2026-10-15"
    it = {"id": "M1-sell", "kind": "sell", "ticker": "7203.T", "status": "placed", "decided_on": last, "fill_day": "2026-10-16",
          "shares": 200, "side": "SELL", "msg": "10/16 开盘卖出全部 200 股", "at": "2026-10-14T19:00:00+09:00"}
    core = {"cid": f"U{last}-SELL-1545.T", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 2010, "decided_on": last,
            "limit": None, "ref_px": 244.0, "phase": "morning", "status": "SENT", "sent_qty": 2010, "filled_qty": 0,
            "note": "已排队，次日开盘成交"}
    b = _mbook("paper", last, [_morder(last, "SELL", "7203.T", "manual", "SENT", "已排队，次日开盘成交", qty=200, sent_qty=200), core],
               {"M1-sell": it})
    b["core_rule"] = {"lot": {"1545.T": 10}}
    _save(b)
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert SELL_M in part and "<b>卖 7203 トヨタ自動車：200 股</b>" in part and "<b>卖 1545 纳斯达克 100：2,010 口</b>" in part
    if where == "later":
        assert "<summary>另有 3 条等 10/19（周一）07:40 的运行</summary>" in later
    _badge_ok(html, "paper", now)
    _named(html)


def test_panel_auto_trigger_paused_waits_for_the_next_decision_or_try_again():
    """面板自动叫执行器今天暂停了（连续失败；run_status.trigger_paused）：盘中写的指令今天不会再自动下 →「另有 … 等下一次决策
    （10/19 07:40；面板自动下单今天暂停了）」、状态后面写「修好之后也可以在 Mac 对话里说「再试一次」」，照算（之后还会做）。
    以前照写「马上（盘中）」在上面（09:30 自检已经说今天不会下：outlook 的 paused）。暂停之后又写了新的指令 → 面板下一轮就恢复 → 都回到上面。"""
    from qbreak import live_ops as LO
    from qbreak import run_status as RS
    now = _t(2026, 10, 16, 10, 30)
    b = _done_book("2026-10-15")
    b["state"]["pos"]["6758.T"] = {"shares": 100, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}
    _save(b)
    rid = "M20261016-100000-sell-7203"
    _want({**_sell_req(_t(2026, 10, 16, 10, 0)), "id": rid})
    (paths.state_dir() / RS.TRIGGER_FILE).write_text(json.dumps({"paper": {"day": "2026-10-16", "why": "连续 3 次没跑成", "ids": [rid],
                                                                           "at": "2026-10-16T10:10:00+09:00"}}), encoding="utf-8")
    assert LO.outlook(b, MO.unseen("paper", b), now, tag="paper", halt=False, paused=True)["items"][rid]["cls"] == "paused"
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    assert SELL_M in later and SELL_M not in top + ended and "马上（盘中）" not in later
    assert "<summary>另有 1 条等下一次决策（10/19 07:40；面板自动下单今天暂停了）</summary>" in later
    assert "面板自动下单今天暂停了：等下一次决策（10/19 07:40）；修好之后也可以在 Mac 对话里说「再试一次」" in _row(later, SELL_M)
    assert _badge_ok(html, "paper", now) == 1
    _named(html)
    _want({"id": "M20261016-103000-sell-6758", "kind": "sell", "ticker": "6758.T", "block_days": 20, "at": "2026-10-16T10:30:00+09:00"})
    html = panel.render("paper", "t" * 40, now)                                     # 新的指令：面板下一轮恢复（Trigger._still_paused）
    top, later, ended = _parts(html)
    assert SELL_M in top and SONY_M in top and later == "" and "暂停" not in top
    assert _badge_ok(html, "paper", now) == 2
    html = panel.render("paper", "t" * 40, now.replace(day=19))                     # 第二天：暂停作废
    assert "面板自动下单今天暂停了" not in html


def test_unknown_order_before_close_holds_the_other_instructions_on_top():
    """立花收盘前（10:30）有状态不明的单（卖 7203 盘中发出、结果不明）：登记之前执行器每次运行开头都停下（_raise_if_unknown）、面板也不叫它
    → 旁边还没读的卖出全部 6758 不是「马上（盘中）」，写「等登记状态不明的单（卖 7203 トヨタ自動車）之后才下」；仍在上面、照算
    （登记了就马上下；复核 5：以前照写「马上（盘中）」）。"""
    tag, last, now = "tachibana", "2026-10-15", _t(2026, 10, 16, 10, 30)
    it = {"id": "M1-sell", "kind": "sell", "ticker": "7203.T", "status": "placed", "decided_on": last, "fill_day": "2026-10-16",
          "shares": 200, "side": "SELL", "now": True, "msg": "盘中卖出 200 股：下单结果不明", "at": "2026-10-16T09:58:00+09:00"}
    o = _morder(last, "SELL", "7203.T", "manual", "ERROR", "状态不明", qty=200, sent_qty=200, phase="now", sent_at="2026-10-16T10:00:00+09:00")
    o["cid"] = f"U{last}-SELL-7203.T-N100000"
    b = _mbook(tag, last, [o], {"M1-sell": it})
    b["state"]["pos"]["6758.T"] = {"shares": 100, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}
    _save(b, tag)
    _want({"id": "M20261016-102000-sell-6758", "kind": "sell", "ticker": "6758.T", "block_days": 20, "at": "2026-10-16T10:20:00+09:00"}, tag)
    assert panel._unknown_open(b)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    row = _row(top, SONY_M)
    assert "等登记状态不明的单（卖 7203 トヨタ自動車）之后才下" in row and "马上（盘中）" not in row
    assert "<b>卖 7203 トヨタ自動車：200 股</b>" in top and later == ""
    assert _badge_ok(html, tag, now) == 3                                            # 单 + 两条指令：之后都会做 → 都算
    _named(html)
    o["status"], o["filled_qty"], o["filled_px"] = "FILLED", 200, 2600.0           # 登记了（成交）→ 6758 照常「马上（盘中）」
    it["status"] = "done"
    _save(b, tag)
    html = panel.render(tag, "t" * 40, now)
    assert "等登记状态不明的单" not in html


# ────────── 复核 6（2026-10-16）──────────
PAUSED_SUMMARY = "<summary>另有 1 条等下一次决策（10/19 07:40；面板自动下单今天暂停了）</summary>"
PAUSED_ROW = "面板自动下单今天暂停了：等下一次决策（10/19 07:40）；修好之后也可以在 Mac 对话里说「再试一次」"


def _pause(tag: str, ids, at: dt.datetime) -> None:
    """面板自动叫执行器今天暂停了（连续 3 次没跑成；Trigger 记在状态目录 panel_trigger.json）。"""
    from qbreak import run_status as RS
    (paths.state_dir() / RS.TRIGGER_FILE).write_text(json.dumps({tag: {"day": at.date().isoformat(), "why": "连续 3 次没跑成",
                                                                       "ids": list(ids), "at": at.isoformat()}}), encoding="utf-8")


def test_remote_halt_push_points_to_the_renamed_section(monkeypatch):
    """远程停止的推送、--phase cancel 的说明、撤单 / 人工代下登记的说明指向面板「今天要成交的单」（2026-10-16 起的标题；
    以前「今天的单」—— 面板上已经没有这一块，手机上照着找不到撤单按钮）。"""
    from pathlib import Path
    import run
    from qbreak import notify
    sent = []
    monkeypatch.setattr(notify, "send", lambda t, m, lvl="info", **k: sent.append((t, m, lvl)))
    p = paths.home() / "HALT_REMOTE_test"
    p.write_text("id=r6-1\nreason=测试\n", encoding="utf-8")
    run._apply_remote_halt(p, paper=True, notify_=True)
    assert len(sent) == 1 and sent[0][2] == "warn"
    assert "面板「今天要成交的单」的「撤单」" in sent[0][1] and "「今天的单」" not in sent[0][1]
    assert paths.halt_file().exists()
    src = Path(run.__file__).read_text(encoding="utf-8")
    assert "面板「今天的单」" not in src and "照「今天的单」" not in src
    assert "面板「今天要成交的单」" in run._live_cancel.__doc__ and "照「今天要成交的单」" in run.cmd_live_adopt.__doc__


@pytest.mark.parametrize("hh,mm", [(11, 20), (12, 0), (12, 40), (8, 30), (8, 57), (9, 1)])
def test_paused_trigger_holds_at_lunch_and_before_the_open(hh, mm):
    """面板自动叫执行器今天暂停了：盘中写的 / 开盘前写的卖出（模拟账户）在午休（11:30〜12:30）与今天早上的决策之后的开盘前
    （07:45〜09:00）也一样「另有 … 等下一次决策（…；面板自动下单今天暂停了）」—— Trigger.check 暂停时什么都不叫
    （下一个来下它的就是面板：live_ops.panel_next）。复核 6：以前只在盘中看暂停，11:20 / 12:40 在「另有」、12:00 跳回上面写
    「12:30 后场开盘」；08:30 / 08:57 在上面写「09:00 开盘」、09:01 又去「另有」。数字不变（之后还会做 → 照算）。"""
    from qbreak import live_ops as LO
    lunch = hh >= 11
    w = _t(2026, 10, 16, 11, 0) if lunch else _t(2026, 10, 16, 8, 0)
    now = _t(2026, 10, 16, hh, mm)
    rid = f"M{w:%Y%m%d-%H%M%S}-sell-7203"
    _done_book("2026-10-15")
    _want({**_sell_req(w), "id": rid})
    html = panel.render("paper", "t" * 40, now)                                     # 对照：没暂停 → 今天（上面）
    top, later, _ = _parts(html)
    assert SELL_M in top and later == "" and _badge_ok(html, "paper", now) == 1
    _pause("paper", [rid], w.replace(minute=5))
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    x = LO.outlook(b, MO.unseen("paper", b), now, tag="paper", halt=False, paused=True)["items"][rid]
    assert x["state"] == "wont" and x["cls"] == "paused"                            # 09:30 自检 / ★ 交易 推送同一个判断
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    assert SELL_M in later and SELL_M not in top + ended and PAUSED_SUMMARY in later
    assert PAUSED_ROW in _row(later, SELL_M) and "12:30 后场开盘" not in later and "09:00 开盘" not in later
    assert _badge_ok(html, "paper", now) == 1
    _named(html)
    calls = []
    trg = panel.Trigger(run=lambda tag, mode: calls.append((tag, mode)), clock=lambda: now, mono=lambda: 1e6,
                        notify=lambda *a, **k: None)
    assert trg.check() == [] and calls == []                                         # 暂停中：面板确实什么都不叫


@pytest.mark.parametrize("kind,hh,mm,pend,agent,where", [
    ("sell", 8, 0, False, True, "top"),      # 08:35 的重试（有要加进寄付单的卖出）/ 09:05 的开盘后运行还会跑：跑成了面板就恢复 → 照旧今天
    ("buy", 8, 0, False, True, "top"),       # 只有买入：08:35 的重试什么都不跑，但 09:05 的开盘后运行每个交易日都跑 → 照旧今天
    ("sell", 8, 40, False, True, "top"),     # 08:35 过了：09:05 的开盘后运行还会跑 → 照旧今天
    ("sell", 9, 1, False, True, "top"),      # 盘中、09:05 之前：同上
    ("sell", 9, 10, False, True, "later"),   # 09:05 过了、没有开盘后的买单：09:20 的重试什么都不跑 → 下一个来下它的是面板 → 暂停中今天不会下
    ("sell", 9, 10, True, True, "top"),      # 还有开盘后的买单（DEFERRED）：09:20 的重试会跑 → 照旧今天
    ("sell", 9, 25, True, True, "later"),    # 09:20 也过了 → 暂停中今天不会下
    ("sell", 8, 0, False, False, "later"),   # 没装立花的定时任务（有模拟操盘的 plist）：没有定时运行 → 与模拟账户一样
])
def test_paused_trigger_tachibana_scheduled_runs(kind, hh, mm, pend, agent, where):
    """立花本番：今天还有定时运行要来（08:35 的重试 / 09:05 的开盘后运行 / 有开盘后的买单时 09:20 的重试；跑成了一次面板就恢复：
    Trigger._still_paused）→ 照旧在上面；之后（或没装定时任务）下一个来下它的就是面板 → 与模拟账户一样「另有 … 面板自动下单今天暂停了」。
    数字一样（标签 = 上面 + 另有）。"""
    tag = "tachibana"
    w, now = _t(2026, 10, 16, 7, 50), _t(2026, 10, 16, hh, mm)
    b = _done_book("2026-10-15", tag)
    if pend:                                                                         # 早上的决策留到开盘后的买单（09:05 / 09:20 下）
        b["orders"].append({"cid": "U2026-10-15-BUY-6758.T", "ticker": "6758.T", "side": "BUY", "kind": "stock", "qty": 100,
                            "decided_on": "2026-10-15", "limit": 2678.0, "ref_px": 2600.0, "phase": "open", "status": "DEFERRED",
                            "note": "开盘后再下"})
        _save(b, tag)
    if not agent:
        ag = paths.launch_agents()
        ag.mkdir(parents=True, exist_ok=True)
        (ag / f"{paths.PAPER_AGENT}.plist").write_text("<plist/>", encoding="utf-8")
    assert paths.live_installed() is agent
    if kind == "sell":
        rid, head = f"M{w:%Y%m%d-%H%M%S}-sell-7203", SELL_M
        _want({**_sell_req(w), "id": rid}, tag)
    else:
        rid, head = f"M{w:%Y%m%d-%H%M%S}-buy-6758", "<b>买入 6758 ソニーグループ"
        _want({"id": rid, "kind": "buy", "ticker": "6758.T", "unit": "rule", "at": w.isoformat(timespec="seconds")}, tag)
    _pause(tag, [rid], w.replace(minute=55))
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    assert head in (top if where == "top" else later) and head not in ended
    if where == "later":
        assert PAUSED_SUMMARY in later and head not in top and PAUSED_ROW in _row(later, head)
    else:
        assert PAUSED_SUMMARY not in later and "暂停" not in top
    assert _badge_ok(html, tag, now) == (2 if pend else 1)
    _named(html)


@pytest.mark.parametrize("paused", [True, False])
def test_paused_trigger_waiting_buy_after_the_open_is_not_today(paused):
    """执行器读了、等 09:00 开盘后马上下的买入（wait=True，「09:00 开盘后马上下单（盘中）」：面板叫的盘中运行下）：
    面板自动下单今天暂停了 → 今天不会下 →「另有 … 面板自动下单今天暂停了」（复核 6：以前 outlook 在看暂停之前就返回「会」，
    留在「今天要成交的单」）。等上一笔成交（wait=prev）的不受影响；没暂停 → 照旧在上面。数字一样。"""
    from qbreak import live_ops as LO
    now = _t(2026, 10, 16, 10, 30)
    b = _done_book("2026-10-15")
    it = {"id": "M20261016-080000-buy-6758", "kind": "buy", "ticker": "6758.T", "unit": "rule", "status": "pending", "wait": True,
          "at": "2026-10-16T08:00:00+09:00", "msg": "09:00 开盘后马上下单（盘中）"}
    b["manual"]["items"][it["id"]] = it
    _save(b)
    if paused:
        _pause("paper", [], _t(2026, 10, 16, 10, 10))
    x = LO.outlook(b, [], now, tag="paper", halt=False, paused=paused)["items"][it["id"]]
    assert (x["state"], x["cls"]) == (("wont", "paused") if paused else ("will", ""))
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    head = "<b>买入 6758 ソニーグループ"
    if paused:
        assert head in later and head not in top + ended and PAUSED_SUMMARY in later and PAUSED_ROW in _row(later, head)
    else:
        assert head in top and later == ""
    assert _badge_ok(html, "paper", now) == 1
    _named(html)
    it["wait"] = "prev"                                                              # 等上一笔成交：路径是下一次早上的对账，不看暂停
    assert LO.outlook(b, [], now, tag="paper", halt=False, paused=True)["items"][it["id"]]["cls"] != "paused"


@pytest.mark.parametrize("last,hold,now,where,chip,summary", [
    ("2026-10-14", "2026-10-15", _t(2026, 10, 16, 7, 0), "top", "今天开盘", ""),         # 昨天 hold、今天早上的运行之前 → 今天开盘
    ("2026-10-15", "2026-10-16", _t(2026, 10, 16, 16, 0), "later", "10/19（周一）开盘", "10/19（周一）开盘"),  # 周五 hold、周五收盘后 → 下周一
    ("2026-10-15", "2026-10-16", _t(2026, 10, 17, 10, 0), "later", "10/19（周一）开盘", "10/19（周一）开盘"),  # 周六
    ("2026-10-14", "2026-10-15", _t(2026, 10, 15, 16, 0), "later", "明天开盘", "10/16（周五）开盘"),       # 周四收盘后 → 明天（周五）开盘
])
def test_hold_chip_says_the_real_opening_day(last, hold, now, where, chip, summary):
    """「这只今天已经有单：明天开盘再处理」（hold）的状态按日子写（MO.hold_text；与「另有 … 等 10/19（周一）开盘」同一个写法）：
    复核 6：以前一律「明天开盘」—— 昨天 hold 的在今天 07:00 的「今天要成交的单」里写「明天开盘」，周五 hold 的在
    「另有 1 条等 10/19（周一）开盘」里也写「明天开盘」。不给 now（执行器的事件 / 汇总）照旧「明天开盘」。"""
    b = _done_book(last)
    it = {"id": "M20261015-100000-sell-7203", "kind": "sell", "ticker": "7203.T", "status": "pending", "hold": hold,
          "at": f"{hold}T10:00:00+09:00", "msg": "这只今天已经有单：明天开盘再处理"}
    b["manual"]["items"][it["id"]] = it
    _save(b)
    assert MO.status_text(it, now) == chip and MO.status_text(it) == "明天开盘"
    html = panel.render("paper", "t" * 40, now)
    top, later, ended = _parts(html)
    part = top if where == "top" else later
    assert f"<span class='chip'>{chip}</span>" in _row(part, SELL_M) and SELL_M not in ended
    if where == "later":
        assert f"<summary>另有 1 条等 {summary}</summary>" in later and SELL_M not in top
    else:
        assert later == ""
    assert _badge_ok(html, "paper", now) == 1
    _named(html)


@pytest.mark.parametrize("hold,now,want", [
    ("2026-10-15", _t(2026, 10, 16, 8, 54), "今天开盘"),          # 今天早上的运行 / 08:35 的重试还会把它排进今天开盘的单
    ("2026-10-15", _t(2026, 10, 16, 10, 0), "等下单"),            # 过了 08:55 还是昨天的 hold = 今天早上的运行没完成：分块与说明写什么时候
    ("2026-10-14", _t(2026, 10, 14, 10, 0), "明天开盘"),          # 周三 hold → 周四
    ("2026-11-02", _t(2026, 11, 2, 10, 0), "11/04（周三）开盘"),  # 周一 hold、11/03 文化の日 → 不是明天
])
def test_hold_text_dates_and_halt(hold, now, want):
    """MO.hold_text：「明天开盘」只在下一个交易日正好是明天时写；HALT 中 →「等下单」（解除后照原样执行，行的说明写着）。"""
    it = {"id": "M1", "kind": "sell", "ticker": "7203.T", "status": "pending", "hold": hold, "msg": "这只今天已经有单：明天开盘再处理"}
    assert MO.status_text(it, now) == want and MO.status_text(it) == "明天开盘"
    paths.halt_file().write_text("test", encoding="utf-8")
    assert MO.status_text(it, now) == "等下单"


# ────────── 复核 7（2026-10-16）──────────
def _trg_calls(now: dt.datetime) -> list:
    calls = []
    trg = panel.Trigger(run=lambda tag, mode: calls.append((tag, mode)), clock=lambda: now, mono=lambda: 1e6, notify=lambda *a, **k: None)
    trg.check()
    return calls


def test_paper_paused_open_matching_waits_for_the_next_morning_run():
    """模拟账户成交日 09:40、面板自动下单今天暂停：开盘撮合只有面板叫（Trigger._open_due 在暂停之后）→ 今天不做 →
    排队的寄付卖单与等开盘后的买单不在「今天要成交的单」，在「另有 … 等 10/16（周五）07:40 的运行」、照算（复核 7：以前写「09:25 前后按开盘价」）。"""
    from qbreak import live_ops as LO
    now = _t(2026, 10, 15, 9, 40)
    b = _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})
    assert _trg_calls(now) == [("paper", "open")]                               # 没暂停：面板叫开盘撮合 → 今天
    html = panel.render("paper", "t" * 40, now)
    top, later, _ = _parts(html)
    assert SELL_B in top and BUY_B in top and later == ""
    _pause("paper", [], _t(2026, 10, 15, 8, 50))
    assert _trg_calls(now) == []
    html = panel.render("paper", "t" * 40, now)
    top, later, _ = _parts(html)
    assert SELL_B not in top and BUY_B not in top and SELL_B in later and BUY_B in later
    assert "<summary>另有 2 条等 10/16（周五）07:40 的运行</summary>" in later
    assert "面板自动下单今天暂停了：今天的开盘撮合不会做 → 10/16（周五）07:40 的运行按今天的正式开盘价撮合" in _row(later, SELL_B)
    assert _badge_ok(html, "paper", now) == 2
    rows = LO.outlook(b, [], now, tag="paper", halt=False, paused=True)["orders"]
    assert {r["state"] for r in rows.values()} == {"later"}
    assert all(r["act_at"] == _t(2026, 10, 16, 7, 40) for r in rows.values())


def test_tachibana_cancel_not_processed_while_paused_stays_counted():
    """立花：写了撤单、面板自动下单今天暂停（撤单只有面板叫）→ 单还挂着、可能成交：照旧在上面、照算，写「挂着（撤单暂停中）」，
    不写「撤单中」（复核 7：以前「撤单中」、不算，标签 0、单却没人去撤）。没暂停 → 照旧「撤单中」、不算。"""
    from qbreak import live_ops as LO
    tag, last = "tachibana", "2026-10-15"
    now = _t(2026, 10, 16, 10, 30)
    o = _morder(last, "SELL", "7203.T", "rule", "SENT", "已下单", broker_id="B1", sent_at="2026-10-16T08:30:00+09:00")
    b = _mbook(tag, last, [o], {})
    rid = "M20261016-101500-cancel_order"
    _want({"id": rid, "kind": "cancel_order", "cid": o["cid"], "at": "2026-10-16T10:15:00+09:00"}, tag)
    head = "<b>卖 7203 トヨタ自動車：100 股</b>"
    assert _trg_calls(now) == [(tag, "cancel")]
    html = panel.render(tag, "t" * 40, now)
    top, _, _ = _parts(html)
    assert "<span class='chip'>撤单中</span>" in _row(top, head) and _badge_ok(html, tag, now) == 0
    _pause(tag, [rid], _t(2026, 10, 16, 10, 20))
    assert _trg_calls(now) == []
    html = panel.render(tag, "t" * 40, now)
    top, later, _ = _parts(html)
    row = _row(top, head)
    assert f"<span class='chip'>{LO.STUCK_CHIP}</span>" in row and "撤单中" not in row and "撤单今天不会自动处理" in row
    assert _badge_ok(html, tag, now) == 1
    r = LO.outlook(b, MO.unseen(tag, b), now, tag=tag, halt=False, paused=True)["orders"][o["cid"]]
    assert r["state"] == "will" and r["cls"] == "stuck"


def test_paper_morning_not_done_and_paused_does_not_promise_a_catchup():
    """模拟账户今天早上的运行没完成、面板自动下单今天暂停（补跑也是面板叫的）→ 盘中写的卖出不写「补跑早上的运行之后」在上面，
    在「另有 … 等下一次决策（10/19 07:40；面板自动下单今天暂停了）」；空的上面写不会自动补跑（复核 7）。没暂停 → 照旧补跑之后今天。"""
    now = _t(2026, 10, 16, 10, 30)
    _done_book("2026-10-14")
    ag = paths.launch_agents()
    ag.mkdir(parents=True, exist_ok=True)
    (ag / f"{paths.PAPER_AGENT}.plist").write_text("<plist/>", encoding="utf-8")
    rid = "M20261016-100000-sell-7203"
    _want({**_sell_req(_t(2026, 10, 16, 10, 0)), "id": rid})
    head = "<b>卖出全部 7203 トヨタ自動車"
    html = panel.render("paper", "t" * 40, now)
    top, later, _ = _parts(html)
    assert head in top and "补跑早上的运行之后" in top
    _pause("paper", [rid], _t(2026, 10, 16, 10, 5))
    html = panel.render("paper", "t" * 40, now)
    top, later, _ = _parts(html)
    assert head not in top and head in later and "补跑早上的运行之后" not in top
    assert "<summary>另有 1 条等下一次决策（10/19 07:40；面板自动下单今天暂停了）</summary>" in later
    assert "面板自动下单今天暂停了、不会自动补跑（等 10/19（周一）07:40 的运行" in top
    assert _badge_ok(html, "paper", now) == 1


def test_waiting_core_and_fix_rows_do_not_leak_internal_keys_into_pushes():
    """「还没照它调」的比例 / 固定口数那一行进 09:30 自检 / HALT 推送（watchdog._orow → live_ops.row_text）：括号里写那条指令的 id，
    没有就不写 —— 不写内部键「core:」「fix:<票>」（复核 7）。"""
    from qbreak import live_ops as LO
    from qbreak import watchdog
    assert LO.row_text({"kind": "instr", "ref": "core:", "what": "闲置资金比例 50%（还没照它调）", "reason": "x"}) == "闲置资金比例 50%（还没照它调）：x"
    assert LO.row_text({"kind": "instr", "ref": "core:", "iid": "M1-core", "what": "闲置资金比例 50%（还没照它调）"}) == "闲置资金比例 50%（还没照它调）（M1-core）"
    tag = "paper"
    b = _etf_book(tag)
    b["manual"]["core_pct"] = 50.0                                             # 没有那条比例指令的行
    _save(b, tag)
    paths.halt_file().write_text("HALT 2026-10-16 测试\n", encoding="utf-8")
    now = _t(2026, 10, 16, 10, 3)
    ol = LO.outlook(b, [], now, tag=tag)
    txt = "\n".join(watchdog._orow(r, now) for r in ol["rows"])
    assert "闲置资金比例 50%（还没照它调）" in txt and "core:" not in txt
    rec = watchdog.evaluate(tag, now)
    assert "闲置资金比例 50%（还没照它调）" in "\n".join(rec.get("halt_wait") or []) and "core:" not in json.dumps(rec, ensure_ascii=False)
    b, tag, now = _fixwait()                                                   # 固定口数（读了、还没照它调）：括号里是那条指令的 id
    txt = "\n".join(watchdog._orow(r, now) for r in LO.outlook(b, [], now, tag=tag, halt=True)["rows"])
    assert "678 口（还没照它调）（M20261014-190000-corefix-1482）：HALT 中" in txt and "fix:" not in txt
    b, tag, now = _fixwait(clear=True)                                         # 恢复按规则：没有可写的 id → 不写括号
    txt = "\n".join(watchdog._orow(r, now) for r in LO.outlook(b, [], now, tag=tag, halt=True)["rows"])
    assert "1482 对冲版美国 7〜10 年国债 恢复按规则（还没照它调）：HALT 中" in txt and "fix:" not in txt


def test_fixed_units_note_dropped_when_the_same_decision_already_filled_it():
    """固定口数排的核心单撤了、同一次决策同一只的另一笔已经成交（真实数据 10/15：679 口撤了、650 口成交）→ 不再写「仍然有效：
    下一次决策还会再排同样的单」（复核 7）；没有别的单时照写、说「照它调（差多少补多少）」，不说「同样的单」；那一行不重复写（上面已经写了）。"""
    b = _book1015(fix={"1482.T": 655})
    now = _t(2026, 10, 16, 10, 30)
    b["state"]["last_date"] = "2026-10-15"
    for o in b["orders"]:
        o["decided_on"] = "2026-10-15"
    buy = b["orders"][1]
    buy.update(cid="U2026-10-15-BUY-1482.T", status="CANCELLED", qty=679, sent_qty=679, note="你撤了单")
    b["orders"][0].update(cid="U2026-10-15-SELL-1545.T", status="FILLED", filled_qty=4110, note="成交")
    _save(b)
    lv = panel._trade_live(b, [], now, "paper", halt=False)
    note = lv["fix"].get(buy["cid"]) or ""
    assert "手动固定 655 口仍然有效：下一次决策（10/19 07:40）还会照它调（差多少补多少）" in note and "同样的单" not in note
    html = panel.render("paper", "t" * 40, now)
    top, _, ended = _parts(html)
    assert note in top and note not in ended                                   # 上面写了，那一行不重复
    b["orders"].append({**buy, "cid": "U2026-10-15-BUY-1482.T-N094306", "qty": 650, "sent_qty": 650, "filled_qty": 650,
                        "status": "FILLED", "reason": "core_fix", "note": "成交"})
    _save(b)
    assert not panel._trade_live(b, [], now, "paper", halt=False)["fix"]
    assert "仍然有效" not in panel.render("paper", "t" * 40, now)


def test_hold_and_block_pointers_say_where_the_row_is():
    """持仓的「有一条手动指令在处理（见 …）」指着那条指令真正在的那一块（收盘后写的在收起的「另有 …」里）；
    「手动卖出后不买回」的「解除」在最下面收起的「已结束 / 不是今天的」里 —— 说明写清、那一块的标题写「含手动卖出后不自动买回 N 条」（复核 7）。"""
    now = _t(2026, 10, 16, 16, 5)
    _done_book("2026-10-16")
    _want(_sell_req(now))
    html = panel.render("paper", "t" * 40, now)
    assert "有一条手动指令在处理（见「交易」→ 点开「另有 …」的「手动指令」）" in html
    assert "见「交易」的「手动指令」" not in html
    assert MO.BLOCK_WHERE.startswith("「交易」→ 点开最下面的「已结束 / 不是今天的」")
    b = _done_book("2026-10-16")
    MO.requests_path("paper").unlink()
    b["manual"]["blocks"] = {"7203.T": {"until": "2026-11-12", "id": "M20261016-100000-sell-7203"}}
    _save(b)
    html = panel.render("paper", "t" * 40, _t(2026, 10, 16, 10, 30))
    _, _, ended = _parts(html)
    assert "；含手动卖出后不自动买回 1 条）</summary>" in ended
