"""核心 ETF 固定口数（manual corefix；2026-10-11 用户「持仓里面的纳斯达克 ETF 和对冲版美国 7-10 年国债也要可以进行买入」）：
引擎（固定的 ETF 正好调到这个口数、不看牛熊 / 再平衡带；其余闲置资金照规则分）、指令的格式 / 检查 / 读入、面板按钮、命令行。"""
import json

import pytest

from qbreak import manual_orders as MO
from qbreak import panel

from test_live_unified import _scenario
from test_manual_core import _cbook


def test_engine_fixed_units_exact_and_rest_follows_rule():
    make, start = _scenario([1000.0] * 30, entry=())
    e0, e1 = make(), make()
    lo = int(e0.gidx.searchsorted(start))
    for e in (e0, e1):
        e.prime(lo)
        for i in range(lo, lo + 8):
            e.step(i)
    u = e0.st.core_units["1655.T"]
    want = (u // 2 // 10) * 10                                             # 固定成一半左右（单元 10 口的倍数也行）
    e1.core_fix = {"1655.T": want}
    e0.step(lo + 8)
    e1.step(lo + 8)
    assert "1655.T" not in e0.st.core_plan                                 # 照规则：不动
    side, n = e1.st.core_plan["1655.T"]
    assert side == "SELL" and u - n == want and e1.core_t100["1655.T"] == want   # 正好调到固定口数（不看再平衡带）


def test_normalize_check_and_ingest(tmp_path):
    r = MO.normalize({"kind": "corefix", "ticker": "1655", "units": 500})
    assert r == {"kind": "corefix", "ticker": "1655.T", "units": 500, "source": "cli"}
    assert MO.normalize({"kind": "corefix", "ticker": "1655", "clear": True})["clear"] is True
    with pytest.raises(ValueError):
        MO.normalize({"kind": "corefix", "ticker": "1655"})
    b = _cbook()
    assert MO.check(MO.normalize({"kind": "corefix", "ticker": "7203", "units": 100}), b) .startswith("7203.T 不是核心 ETF")
    assert "倍数" in MO.check(MO.normalize({"kind": "corefix", "ticker": "1655", "units": 105}), b)
    assert "超过总权益" in MO.check(MO.normalize({"kind": "corefix", "ticker": "1655", "units": 5000}), b)
    assert MO.check(MO.normalize({"kind": "corefix", "ticker": "1655", "units": 500}), b) is None
    assert "本来就是按规则" in MO.check(MO.normalize({"kind": "corefix", "ticker": "1655", "clear": True}), b)
    assert MO.describe({"kind": "corefix", "ticker": "1482.T", "units": 300}) == "固定 1482.T 300 口（不按规则自动调）"


def test_panel_shows_buy_and_fix_buttons():
    import datetime as dt
    from qbreak.calendar_jp import JST
    from test_panel import _book
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core_fix": {"1655.T": 100}})
    h = panel.render("paper", "t" * 40, dt.datetime(2026, 10, 11, 12, 0, tzinfo=JST))
    assert "data-act='corefix'" in h and "a==='corefix'" in panel._JS
