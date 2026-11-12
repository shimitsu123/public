"""第三个研究循环第 9 轮 ECL（scripts/loop3_r09_entrygap.py，2026-10-02 登记）：登记值、S5 的贪心保留、交易日位置、规模核对的计数、
引擎钩子 MixEngine.ENTRY_GAP（成交日相隔不到 g 个交易日 / 同一天已排日本个股 → 不开；核心 ETF、美股不挡；缺省不变）、run 的传入与复位、接线与命令行。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r09_entrygap as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.GAP) == (9, ("ECL",), False, "stock", 5)
    assert T.FAMILY == {"ECL": "个股层·开仓节奏"}
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")
    st = json.loads((ROOT / "var" / "research_loop3.json").read_text(encoding="utf-8"))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        used = {a["id"] for r in st.get("rounds") or [] for a in r.get("approaches") or []}
        assert not set(T.IDS) & used and R3.family_counts(st).get("个股层·开仓节奏", 0) + 1 <= R3.FAMILY_CAP
        assert R3.used(st) + len(T.IDS) <= R3.CAP


def test_greedy_keep_and_day_pos():
    assert list(T.greedy_keep(np.array([0, 0, 2, 5, 6, 10, 14]), 5)) == [True, False, False, True, False, True, False]
    assert list(T.greedy_keep(np.array([], int), 5)) == []
    days = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-09", "2024-01-10"])     # 1/8 成人の日不在里面
    assert list(T.day_pos(["2024-01-05", "2024-01-08", "2024-01-10"], days)) == [1, 2, 3]   # 不是交易日 → 之后第一个交易日


def test_close_fills_counts():
    days = pd.bdate_range("2024-01-01", periods=30)
    d = [days[0], days[2], days[2], days[9], days[20], days[22]]
    assert T.close_fills(d, days, 5) == {"fills": 6, "within_gap": 3, "same_day_days": 1}   # 0→2、2→2、20→22
    assert T.close_fills([], days, 5) == {"fills": 0, "within_gap": 0, "same_day_days": 0}


def _eng():
    import candle_portfolio as CP
    eng = CP.MixEngine.__new__(CP.MixEngine)                                 # 只测这个方法：不跑完整引擎
    eng.nxt = {"JP": np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, -1]), "US": np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, -1])}
    eng.live_mult, eng.em = {}, {"JP": None, "US": None}
    eng.core_set = {"1655.T"}
    eng.col = {"7203.T": 0, "6758.T": 1, "1655.T": 2, "AAPL": 3}
    eng.mkt = np.array(["JP", "JP", "JP", "US"])
    eng.st = SimpleNamespace(plan={}, pos={})
    eng.skipped = {"macro": 0}
    return CP, eng


def test_entry_gap_hook_blocks_close_and_same_day_jp_entries_only():
    CP, eng = _eng()
    assert CP.MixEngine.ENTRY_GAP is None and eng._entry_mult("7203.T", 5) == 1.0   # 缺省：不变
    try:
        CP.MixEngine.ENTRY_GAP = 5
        assert eng._entry_mult("7203.T", 0) == 1.0                              # 还没开过
        eng._jp_fill = 3
        assert eng._entry_mult("7203.T", 5) == 0.0                              # 成交日 6 − 3 = 3 < 5
        assert eng._entry_mult("7203.T", 7) == 1.0                              # 成交日 8 − 3 = 5
        assert eng._entry_mult("1655.T", 5) == 1.0 and eng._entry_mult("AAPL", 5) == 1.0   # 核心 ETF、美股不挡
        eng.st.plan = {"6758.T": [100.0, 100, "2024-01-01"]}
        assert eng._entry_mult("7203.T", 7) == 0.0                              # 今天已经排了一笔日本个股
        eng.st.plan = {"AAPL": [100.0, 1, "2024-01-01"]}
        assert eng._entry_mult("7203.T", 7) == 1.0                              # 排的是美股 → 不算
        assert eng.skipped["entry_gap"] == 2
    finally:
        CP.MixEngine.ENTRY_GAP = None


def test_open_records_fill_and_run_passes_and_resets():
    import inspect
    import candle_portfolio as CP
    src = inspect.getsource(CP.MixEngine._open)
    assert "self._jp_fill = i" in src and "t in self.st.pos" in src and "MixEngine.ENTRY_GAP" in src
    r = inspect.getsource(CP.make_runner)
    assert "entry_gap: int | None = None" in r and "MixEngine.ENTRY_GAP = entry_gap or None" in r
    assert r.count("MixEngine.ENTRY_GAP = None") == 1


def test_wiring_and_cli():
    import inspect
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, entry_gap=GAP)" in s1
    assert "R3.stage1(cand[\"ECL\"], base, trade=os_, posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "entry_gap=0" in w and "nb > 0" in w
    o = inspect.getsource(T.other_stocks)
    assert "sort_values([\"_d\", \"ticker\"], kind=\"mergesort\")" in o and "greedy_keep(" in o
    with pytest.raises(SystemExit):
        T.main(["--nope"])
    with pytest.raises(SystemExit):
        T.main(["--scale", "--wiring"])
