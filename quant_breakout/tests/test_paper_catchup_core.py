"""模拟账户补跑多天时，这次才读到的闲置资金比例 / 固定口数不追溯到成交日已经过了的旧 K 线（2026-10-14；unblock-7 的 core 部分）。"""
import datetime as dt

from qbreak import manual_orders as MO
from qbreak import paths
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.live_unified import UnifiedExecutor, _MemPaper

from test_live_unified import _scenario


def _setup():
    make, start = _scenario([1000.0] * 50, entry=(), n=50)
    eng = make()
    b = _MemPaper(state_file=paths.state_dir() / "paper.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"], market="JP")
    now = {"t": None}
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book_p.json", paper=True, respect_halt=False, check_clock=False,
                         clock=lambda: now["t"], manual_tag="p")
    k0 = int(eng.gidx.searchsorted(start))
    eng.prime(k0)

    def morning(idxs):
        now["t"] = dt.datetime.combine(next_trading_day(eng.gidx[idxs[-1]].date()), dt.time(7, 40), tzinfo=JST)
        ux.morning(idxs)
    for k in range(k0, 16):
        morning([k])
    return eng, ux, morning


def test_catchup_core_pct_not_applied_to_past_bars():
    eng, ux, morning = _setup()
    u0 = eng.st.core_units.get("1655.T", 0)
    assert u0 > 0
    MO.append("p", {"kind": "core", "pct": 0}, clock=lambda: dt.datetime.combine(eng.gidx[18].date(), dt.time(20, 0), tzinfo=JST))
    morning([16, 17, 18])                                   # Mac 睡了两天：一次补跑 3 根，比例 0% 是最后一天晚上写的
    assert eng.st.core_units.get("1655.T", 0) == u0         # 旧 K 线照 100%：没有在过去的开盘卖
    assert eng.st.core_plan.get("1655.T", [None])[0] == "SELL"   # 这次的决策（今天开盘）才按 0% 卖
    assert ux.manual.core_pct == 0


def test_daily_run_core_pct_applies_at_once():
    eng, ux, morning = _setup()
    MO.append("p", {"kind": "core", "pct": 0}, clock=lambda: dt.datetime.combine(eng.gidx[16].date(), dt.time(20, 0), tzinfo=JST))
    morning([16])
    assert eng.st.core_plan.get("1655.T", [None])[0] == "SELL"
