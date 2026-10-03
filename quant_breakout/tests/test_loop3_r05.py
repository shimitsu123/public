"""第三个研究循环第 5 轮 TOML（scripts/loop3_r05_tomlever.py，2026-10-02 登记）：登记值、月末月初日、拿 2869 的决定日（下一个交易日是月末月初）、
接法（2869 的熊 = 美股熊 或 不在拿的日子；不拿 = B1 的两个键不变）、1987〜2000 的持仓、ID 没用过、命令行。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r05_tomlever as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.KIND) == (5, ("TOML",), "核心·日历杠杆", True, "signal")
    assert (T.LEV_T, T.TOM_LAST, T.TOM_FIRST) == ("2869.T", 1, 3)
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")


def test_tom_days_last_one_and_first_three():
    d = pd.bdate_range("2024-01-24", "2024-02-08")                          # 1/24〜2/8 的工作日
    td = T.tom_days(d)
    assert list(td.strftime("%m-%d")) == ["01-24", "01-25", "01-26", "01-31", "02-01", "02-02", "02-05", "02-08"]   # 数据的最后一天当月末
    full = pd.bdate_range("2024-01-01", "2024-03-31")
    tf = set(T.tom_days(full).strftime("%m-%d"))
    assert {"01-01", "01-02", "01-03", "01-31", "02-01", "02-02", "02-05", "02-29", "03-01", "03-04", "03-05", "03-29"} == tf   # bdate_range 含 1/1


def test_hold_state_is_one_day_ahead():
    full = pd.bdate_range("2024-01-01", "2024-03-31")
    h = T.hold_state(full)
    tom = set(T.tom_days(full))
    nxt = {full[i] for i in range(len(full) - 1) if full[i + 1] in tom}
    assert set(h.index[h.to_numpy()]) == nxt and not h.iloc[-1]
    assert h.loc["2024-01-30"] and h.loc["2024-02-02"] and not h.loc["2024-02-05"]   # 1/31〜2/5 是窗口 → 1/30〜2/2 决定拿


def test_never_holding_keeps_b1_and_lv_key():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([False, True, False, False, False, True], index=idx)
    hold = pd.Series([True, True, False, True, False, True], index=idx)
    W = {"b1": {"extra_core": {"2845.T": "h"}}, "assets": {"2869.T": "lv"}}
    ov = T.toml_over(W, bear, hold)
    assert list(ov["extra_bear"][T.LV_KEY].reindex(idx)) == [False, True, True, False, True, True]
    assert ov["cfg_over"]["core"] == {"1545.T": 1.0, "2845.T": 1.0, "2869.T": 1.0} and ov["cfg_over"]["core_mode"] == "follow"
    assert ov["cfg_over"]["core_index"]["2869.T"] == T.LV_KEY and set(ov["extra_core"]) == {"2845.T", "2869.T"}
    assert Y.UH_KEY not in ov["extra_bear"] and Y.HG_KEY not in ov["extra_bear"]          # B1 的两个键不动（loop2_common 按键合并）
    never = T.toml_over(W, bear, pd.Series(False, index=idx))
    assert never["extra_bear"][T.LV_KEY].reindex(idx).all()


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in src and "posthoc=unseen" in src and "toml_over(W, W[\"bear\"][\"US\"], hold)" in src
    wsrc = inspect.getsource(T.wiring)
    assert "pd.Series(False, index=hold.index)" in wsrc and "n_lev > 0" in wsrc
    osrc = inspect.getsource(T.old_core)
    assert "w[:2] *= 0.5" in osrc and "w[2] = 0.5" in osrc
    with pytest.raises(SystemExit):
        T.main(["--nope"])
    assert np.isfinite(T.TOM_FIRST)
