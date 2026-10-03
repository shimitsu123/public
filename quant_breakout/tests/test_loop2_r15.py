"""第二个研究循环第 15 轮 RXH（scripts/loop2_r15_rateshockconf.py，2026-10-02 登记）：登记值、k = 牛熊分界的确认天数、去抖的开 / 关、命令行。"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop2_r15_rateshockconf as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD, T.K_CONFIRM) == (
        15, ("RXH",), "核心·指数选择", True, ("1987-01-01", "2000-12-31"), 5)


def test_k_is_the_bullbear_detector_confirmation():
    det = json.loads((ROOT / "var" / "bullbear.json").read_text(encoding="utf-8"))["detector"]
    assert det["kind"] == "ma_band" and det["params"]["k"] == T.K_CONFIRM


def test_confirm_needs_k_days_on_and_off():
    idx = pd.bdate_range("2020-01-01", periods=16)
    x = pd.Series([1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1], index=idx).astype(bool)
    got = T.confirm(x, 5).tolist()
    # 第 1〜4 天只连续 4 天 → 不开；第 6〜10 天连续 5 天 → 第 10 天开；第 11〜15 天连续 5 天不成立 → 第 15 天关
    assert got == [False] * 9 + [True] * 5 + [False, False]


def test_short_flickers_never_switch():
    idx = pd.bdate_range("2020-01-01", periods=12)
    x = pd.Series([1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0], index=idx).astype(bool)
    assert not T.confirm(x, 5).any()


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "RXH"])
