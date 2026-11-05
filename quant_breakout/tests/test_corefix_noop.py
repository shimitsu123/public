"""固定的口数 = 已经拿着的口数 → 写「不下单」（2026-10-17 用户：已经买了 650 口 1482，点「不补了」写的「固定 650 口」显示「等下单」，
以为又要下 650 口）。只是展示：执行器照旧按「目标口数 − 现在口数」下单（差 0 = 不下）。"""
import datetime as dt

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak.calendar_jp import JST

NOW = dt.datetime(2026, 10, 17, 22, 30, tzinfo=JST)
BOOK = {"state": {"last_date": "2026-10-15", "core_units": {"1482.T": 650}}}


def _held(monkeypatch, n=650):
    monkeypatch.setattr(LO, "held_now", lambda book, tag=None, now=None, snap=None:
                        {"core_units": {"1482.T": n}, "head": "含 10/16（周五）已成交"})


def test_fix_equal_to_holding_says_no_order(monkeypatch):
    _held(monkeypatch)
    r = {"kind": "corefix", "ticker": "1482.T", "units": 650}
    assert MO.corefix_noop(r, BOOK, None, NOW) == (650, "含 10/16（周五）已成交")
    assert MO.wait_word(r, BOOK, None, NOW) == "不下单"
    t = MO.wait_text(r, NOW, BOOK, None)
    assert t.startswith("不下单：已经拿着 650 口（含 10/16（周五）已成交）") and "不买也不卖" in t and "等下单" not in t
    assert MO.wait_word(r) == "等下单"                                  # 不给账本：照旧（撤回中的那行等）


def test_fix_that_buys_or_sells_still_waits_for_an_order(monkeypatch):
    _held(monkeypatch)
    for r in ({"kind": "corefix", "ticker": "1482.T", "units": 655},
              {"kind": "corefix", "ticker": "1482.T", "clear": True},
              {"kind": "corefix", "ticker": "1545.T", "units": 650}):
        assert MO.corefix_noop(r, BOOK, None, NOW) is None
        assert MO.wait_word(r, BOOK, None, NOW) == "等下单"


def test_noop_check_never_breaks_the_page(monkeypatch):
    monkeypatch.setattr(LO, "held_now", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("坏账本")))
    r = {"kind": "corefix", "ticker": "1482.T", "units": 650}
    assert MO.corefix_noop(r, BOOK, None, NOW) is None and MO.wait_word(r, BOOK, None, NOW) == "等下单"


def test_confirm_dialog_is_not_called_an_order_when_nothing_changes(monkeypatch):
    plan = {"t": "1482.T", "clear": False, "cur": 650, "target": 650, "old_fix": 655, "moves": [], "cash": 10020, "short": 0,
            "eq": 973970.0, "pct": 100.0, "hold": []}
    monkeypatch.setattr(MO, "corefix_plan", lambda *a, **k: dict(plan))
    p = MO.corefix_preview(BOOK, None, {"kind": "corefix", "ticker": "1482.T", "units": 650}, NOW)
    assert p["noop"] is True and p["title"].startswith("确认：") and "不下单" in p["title"]
    plan.update(target=655)
    p2 = MO.corefix_preview(BOOK, None, {"kind": "corefix", "ticker": "1482.T", "units": 655}, NOW)
    assert p2["noop"] is False and p2["title"].startswith("确认下单：")


def test_panel_uses_the_book_for_the_status_word_and_the_button():
    from pathlib import Path
    from qbreak import panel
    src = Path(panel.__file__).read_text(encoding="utf-8")
    assert "MO.wait_word(r, book, tag, now)" in src and '"noop": bool(pv.get("noop"))' in src
    js = (Path(panel.__file__).parent / "static" / "trade.js").read_text(encoding="utf-8")
    assert "c.noop ? '确认（不下单）' : '确认下单'" in js


def test_outlook_row_for_a_noop_fix_is_done_not_an_order(monkeypatch):
    """交易页（2026-10-17 用户「不下单的话没必要在交易里面标记下单了」）：outlook 的那一行 = done（收进「已结束」、不算标签上的数字、
    自检不当成该下的单）；HALT 中也一样（不下单就没有「等 HALT 解除」）。"""
    _held(monkeypatch)
    r = {"id": "M1", "kind": "corefix", "ticker": "1482.T", "units": 650, "at": "2026-10-17T22:24:56+09:00"}
    for halt in (False, True):
        x = LO._instr_row(r, BOOK, NOW, "paper", halt, False, False)
        assert x["state"] == "done" and x["cls"] == "noop" and x["reason"].startswith("不下单：")
    x2 = LO._instr_row({**r, "units": 655}, BOOK, NOW, "paper", False, False, False)
    assert x2["state"] != "done" and x2["cls"] != "noop"


def test_withdraw_button_for_fix_and_ratio_is_not_called_an_order():
    from pathlib import Path
    from qbreak import panel
    src = Path(panel.__file__).read_text(encoding="utf-8")
    assert "{'撤回' if nb else '撤单'}</button>" in src and "（现在也是 {held:,} 口：不下单）" in src
    assert "and int(fixed[t]) != int(cu_now.get(t) or 0)" in src           # 撤了的单下面不再写「还没照它调：… 照它下单」
    js = (Path(panel.__file__).parent / "static" / "trade.js").read_text(encoding="utf-8")
    assert "d.ctx ? '确认撤回？' : '确认撤单？'" in js and "d.ctx ? '确认撤回' : '确认撤单'" in js
