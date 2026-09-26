"""conftest.py — 所有测试都在临时 QBREAK_HOME 下运行，绝不碰你的真实状态文件。"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 必须在 import qbreak 之前设置：日志/状态目录在首次 import 时就会被创建
_TMP = tempfile.mkdtemp(prefix="qbreak_test_")
os.environ["QBREAK_HOME"] = _TMP

import pandas as pd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    yield tmp_path


def make_frame(rows, start="2024-01-01"):
    """rows: [(open, high, low, close, volume), ...] → 带日期索引的 OHLCV。"""
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


def make_indicator_frame(rows, entries=None, deads=None, atr=None, start="2024-01-01"):
    """直接构造引擎需要的列，跳过指标计算 —— 让成交逻辑的测试完全确定。"""
    df = make_frame(rows, start)
    n = len(df)
    df["entry"] = [bool(entries and i in entries) for i in range(n)]
    df["dead_cross"] = [bool(deads and i in deads) for i in range(n)]
    df["atr"] = atr if atr is not None else df["Close"] * 0.02
    return df
