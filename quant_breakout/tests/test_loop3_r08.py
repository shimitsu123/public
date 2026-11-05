"""第三个研究循环第 8 轮 RTX / NZS（scripts/loop3_r08_ratiospx.py，2026-10-02 登记）：登记值、比值 = 同一个美国交易日的纳指 ÷ S&P500、
比值的牛熊 = 现行检测器、RTX = 比值熊且分界不是熊、NZS = 警戒区且比值熊、接法 = NSX 原样、ID 没用过、命令行。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r08_ratiospx as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.KIND) == (8, ("RTX", "NZS"), "核心·指数选择", True, "signal")
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")
    st = json.loads((ROOT / "var" / "research_loop3.json").read_text(encoding="utf-8"))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        used = {a["id"] for r in st.get("rounds") or [] for a in r.get("approaches") or []}
        assert not set(T.IDS) & used and R3.family_counts(st).get(T.FAMILY, 0) + 2 <= R3.FAMILY_CAP
        assert R3.used(st) + len(T.IDS) <= R3.CAP


def test_ratio_uses_common_us_days():
    a = pd.Series([100.0, 110.0, 121.0, np.nan], index=pd.bdate_range("2024-01-01", periods=4))
    b = pd.Series([50.0, 50.0, 55.0, 60.0, 70.0], index=pd.bdate_range("2024-01-02", periods=5))
    r = T.ratio(a, b)
    assert list(r.index.strftime("%m-%d")) == ["01-02", "01-03"]                  # 两边都有收盘的日子（NaN 去掉）
    assert list(r.round(6)) == [2.2, 2.42]                                       # 110 ÷ 50、121 ÷ 50


def test_ratio_bear_is_current_detector_on_the_ratio(monkeypatch):
    import inspect
    assert "EI.t0_bear(ratio(ndx, spx))" in inspect.getsource(T.ratio_bear)
    from qbreak import bullbear as BB
    d = json.loads((ROOT / "var" / "bullbear.json").read_text(encoding="utf-8"))   # 测试在临时 QBREAK_HOME 下 → 用仓库的设定
    monkeypatch.setattr(BB, "load_config", lambda: d)
    idx = pd.bdate_range("2020-01-01", periods=400)
    spx = pd.Series(100.0, index=idx)
    ndx = pd.Series(np.r_[np.full(300, 200.0), np.full(100, 150.0)], index=idx)    # 第 300 天起纳指相对跌 25%
    rb = T.ratio_bear(ndx, spx)
    assert not rb.iloc[:300].any() and rb.iloc[310:].all()                       # 连续 5 天在 250 日线 −3% 之下才转熊
    assert not rb.iloc[300:304].any() and rb.iloc[304]


def test_states_rtx_and_nzs():
    idx = pd.bdate_range("2020-01-01", periods=6)
    rb = pd.Series([False, True, True, True, False, True], index=idx)
    ub = pd.Series([False, False, True, False, False, False], index=idx)
    zone = pd.Series([True, True, False, False, True, False], index=idx)
    assert list(T.rtx_state(rb, ub)) == [False, True, False, True, False, True]   # 比值熊、分界不是熊
    assert list(T.nzs_state(zone, rb)) == [False, True, False, False, False, False]
    late = pd.Series([True], index=pd.DatetimeIndex(["2020-01-03"]))               # 并集上向后填，之前没有值 = False
    assert list(T.nzs_state(zone, late)) == [False, False, False, False, True, False]


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in src and "posthoc=unseen" in src and "NS.nsx_over(W, st[k], uni, hspx)" in src
    assert "R8.old_core(W, uni, W[\"bear\"][\"US\"])" in src and "NS.old_core(W, uni, W[\"bear\"][\"US\"], st[k])" in src
    w = inspect.getsource(T.wiring)
    assert "pd.Series(False, index=st[\"RTX\"].index)" in w and "all(v > 0 for v in n_spx.values())" in w
    s = inspect.getsource(T.states)
    assert "ZS.zone_state(ZS.zone_bear(inp[\"spx\"][\"Close\"]), W[\"bear\"][\"US\"])" in s
    with pytest.raises(SystemExit):
        T.main(["--nope"])
