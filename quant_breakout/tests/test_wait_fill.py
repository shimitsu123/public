"""盘中等成交的单转圈 + 票名闪烁（2026-10-17 用户：「盘中下单后没有成交的话要一直显示加载等等的提示 比如对应下单的股票闪烁
出现 loading 图标等等 盘后的话不用」）：panel._wait_fill / _order_rows 的 wfill + spin、/api/status 的 busy（页面每 10 秒问一次）。"""
import datetime as dt

import pytest

from qbreak import panel
from qbreak.calendar_jp import JST

from test_core_etf_restore import _paper2
from test_fund_src import _fixed_case
from test_manual_now import _at
from test_paper_open_settle import _feed


def _html(r, t):
    return "".join(h for _cid, h in panel._order_rows(r.ux.book, t, True, [], tag="paper")[0])


@pytest.mark.parametrize("hh, mm, spin", [
    (8, 50, False),      # 开盘前（寄付单还没到交易所的撮合时间）
    (9, 10, True),       # 前場：寄付卖单等 09:25 前后的开盘撮合
    (11, 45, False),     # 午休
    (14, 0, True),       # 後場
    (15, 27, True),      # 引け（15:25〜15:30）
    (15, 40, False),     # 收盘后
])
def test_spinner_only_while_the_market_is_in_session(hh, mm, spin):
    r = _paper2("wf")
    sell, buy = _fixed_case(r)
    assert sell.status == "SENT" and buy.status == "DEFERRED"
    html = _html(r, _at(r, hh, mm))
    assert ("wfill" in html and "class='spin'" in html and "盘中还没成交" in html) is spin
    if spin:                                                          # 只有已经发出的卖单转圈；还没发出的买单（等开盘后）不转
        assert html.count("class='spin'") == 1 and html.count("wfill") == 1


def test_filled_order_stops_spinning_and_status_busy_counts_waiting_orders():
    r = _paper2("wf2")
    _fixed_case(r)
    t = _at(r, 9, 10)
    assert panel._trade_live(r.ux.book, [], t, "wf2")["busy"] >= 1  # 等成交 → 页面每 10 秒问一次
    lunch = panel._trade_live(r.ux.book, [], _at(r, 11, 45), "wf2")["busy"]
    assert panel._trade_live(r.ux.book, [], t, "wf2")["busy"] == lunch + 1
    r.now["t"] = _at(r, 9, 25)
    r.ux.open_phase(feed=_feed(r))
    r.ux.save(force=True)
    html = _html(r, _at(r, 9, 26))
    assert "成交 970 @" in html and "wfill" not in html and "class='spin'" not in html


def test_wait_fill_rules():
    now = dt.datetime(2026, 10, 19, 10, 0, tzinfo=JST)                # 周一 前場
    o = {"status": "SENT", "qty": 100}
    assert panel._wait_fill(o, now, now.date())
    assert not panel._wait_fill(o, now, dt.date(2026, 10, 16))       # 上一个成交日的单（今天早上的运行还没跑）
    assert panel._wait_fill({"status": "PARTIAL", "qty": 100, "filled_qty": 40}, now, now.date())
    assert not panel._wait_fill({"status": "PARTIAL", "qty": 100, "snap_q": 100}, now, now.date())   # 快照里已经全部成交
    for s in ("FILLED", "CANCELLED", "PLANNED", "DEFERRED", "EXPIRED", "ERROR", "SENDING"):   # 发送中 / 结果不明 = 状态不明
        assert not panel._wait_fill({"status": s, "qty": 100}, now, now.date())
    sat = dt.datetime(2026, 10, 17, 10, 0, tzinfo=JST)
    assert not panel._wait_fill(o, sat, sat.date())                    # 休市日


def test_css_has_the_animation_and_respects_reduced_motion():
    css = (panel.Path(panel.__file__).parent / "static" / "panel.css").read_text(encoding="utf-8")
    assert ".li.wfill .grow>b:first-child{animation:qbblink" in css and ".spin{" in css and "@keyframes qbblink" in css
    rm = css[css.rindex("prefers-reduced-motion"):]
    assert ".spin{animation:none}" in rm
