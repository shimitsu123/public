"""第二个研究循环第 17 轮 OCX（scripts/loop2_r17_oppcost.py，2026-10-02 登记）：登记值、跑输核心的判定、单笔模拟的旗标、引擎钩子缺省关、命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP  # noqa: E402
import loop2_r17_oppcost as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC) == (17, ("OCX",), "个股层·机会成本离场", False)
    assert T.OPP == {"ref": "1545.T", "hold": 10, "gap": 0.05}


def test_opp_cost_hit():
    assert CP.opp_cost_hit(-0.02, 0.03, 10, 10, 0.05)                         # 恰好少涨 5 pp、第 10 天 → 卖
    assert not CP.opp_cost_hit(-0.02, 0.029, 10, 10, 0.05)                    # 少涨不到 5 pp
    assert not CP.opp_cost_hit(-0.20, 0.00, 9, 10, 0.05)                      # 不到 10 天
    assert not CP.opp_cost_hit(float("nan"), 0.0, 20, 10, 0.05)


def test_ocx_flags_hold_and_gap():
    n = 20
    close = np.full(n, 100.0)
    core = np.r_[np.full(5, 1000.0), np.linspace(1000, 1100, 15)]            # 核心第 5 天起涨到 +10%
    f = T.ocx_flags(close, 3, 100.0, core)
    hold = np.arange(n) - 3 + 1
    rel = -(core / core[3] - 1)
    want = (np.arange(n) >= 3) & (hold >= 10) & (rel <= -0.05 + 1e-12)
    assert np.array_equal(f, want) and f.any() and not f[:12].any()


def test_engine_hook_off_by_default():
    assert CP.MixEngine.OPP_EXIT is None
    assert callable(getattr(CP.MixEngine, "_opp_exit", None))
    assert "opp_exit" in inspect.signature(CP.make_runner).parameters or "opp_exit: dict | None = None" in inspect.getsource(CP)
    src = inspect.getsource(CP)
    assert "MixEngine.OPP_EXIT = opp_exit or None" in src and "MixEngine.OPP_EXIT = None" in src


def test_engine_calls_opp_exit_and_has_one_check_exits():
    """登记的运行里钩子没生效：MixEngine 里另有一个同名的 _check_exits 在后面把它覆盖了 → 只能有一个定义，而且它要调用 _opp_exit。"""
    import re
    src = inspect.getsource(CP.MixEngine)
    assert len(re.findall(r"\n    def _check_exits\(", src)) == 1
    assert "self._opp_exit(i, ox)" in inspect.getsource(CP.MixEngine._check_exits)


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "OCX"])
