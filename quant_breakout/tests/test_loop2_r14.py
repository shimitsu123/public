"""第二个研究循环第 14 轮 YSG（scripts/loop2_r14_yengate.py，2026-10-02 登记）：登记值、急升日的信号 → 下一个交易日的新仓倍数 0、S5 接法、命令行。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r14_yengate as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC) == (14, ("YSG",), "个股层·日元急升闸门", False)


def test_surge_on_signal_day_blocks_next_day_fill():
    days = pd.bdate_range("2020-01-06", periods=6)                              # 日本交易日
    us = pd.Series([False, True, True, False], index=pd.DatetimeIndex(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-10"]))
    m = T.em_mult({"ctx": {"Z": {"days": days}}}, "Z", us)
    # 信号日 1/7、1/8、1/9（向后填 1/8 的急升）→ 成交日 1/8、1/9、1/10 的倍数 0；其余 1
    assert m.tolist() == [1.0, 1.0, 0.0, 0.0, 0.0, 1.0]


def test_no_surge_means_b1():
    days = pd.bdate_range("2020-01-06", periods=5)
    m = T.em_mult({"ctx": {"E": {"days": days}}}, "E", pd.Series(False, index=days))
    assert np.allclose(m.to_numpy(), 1.0)


def test_s5_uses_erg_other_stocks():
    assert T.other_stocks.__doc__ and "ERG" in T.other_stocks.__doc__
    import inspect
    assert "G12.other_stocks" in inspect.getsource(T.other_stocks)


def test_cli_only_scale_option():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "YSG"])
