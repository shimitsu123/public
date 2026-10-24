"""第三个研究循环第 12 轮 CRC / DVC（scripts/loop3_r12_corediv.py，2026-10-03 登记）：登记值、周收益与核心的 104 周相关（不足 52 周 = NaN）、
横截面最高三分之一（NaN 不挡）、分红减少 / 停发的判定（同一期比、10%、半年 / 一年分红、拆股后的数据）、em_tick、接线与命令行。"""
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r12_corediv as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.CORR_W, T.CORR_MIN) == (12, ("CRC", "DVC"), False, "stock", 104, 52)
    assert T.TOP_Q == pytest.approx(2 / 3) and (T.CUT, T.RECENT, T.PREV_LO, T.PREV_HI, T.OMIT_LO, T.OMIT_HI, T.OMIT_GAP) == (0.9, 200, 410, 320, 410, 380, 320)
    assert T.FAMILY == {"CRC": "选股·组合分散", "DVC": "选股·分红变化"}
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")
    st = json.loads((ROOT / "var" / "research_loop3.json").read_text(encoding="utf-8"))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        used = {a["id"] for r in st.get("rounds") or [] for a in r.get("approaches") or []}
        fc = R3.family_counts(st)
        assert not set(T.IDS) & used and fc.get("选股·组合分散", 0) + 1 <= R3.FAMILY_CAP and fc.get("选股·分红变化", 0) + 1 <= R3.FAMILY_CAP
        assert R3.used(st) + len(T.IDS) <= R3.CAP


def test_core_corr_monthly():
    idx = pd.bdate_range("2020-01-01", "2023-12-31")
    rng = np.random.default_rng(1)
    rc = rng.normal(0, 0.01, len(idx))
    core = pd.Series(100 * np.cumprod(1 + rc), index=idx)
    same = pd.Series(50 * np.cumprod(1 + rc), index=idx)                      # 与核心完全同步
    indep = pd.Series(50 * np.cumprod(1 + rng.normal(0, 0.01, len(idx))), index=idx)
    months = pd.period_range("2020-01", "2023-12", freq="M")
    cw = T.weekly_ret(core)
    a = T.core_corr_monthly(same, cw, months)
    b = T.core_corr_monthly(indep, cw, months)
    assert a.loc[pd.Period("2023-06", "M")] == pytest.approx(1.0) and abs(b.loc[pd.Period("2023-06", "M")]) < 0.3
    assert np.isnan(a.loc[pd.Period("2020-06", "M")])                         # 不足 52 周 → NaN
    assert T.core_corr_monthly(same.iloc[:100], cw, months).isna().all()


def test_top_third_blocks_highest_third():
    m = pd.period_range("2024-01", periods=1, freq="M")
    P = pd.DataFrame([[float(v) for v in range(1, 10)] + [np.nan]], index=m, columns=[f"{k}.T" for k in range(10)])
    assert list(T.top_third(P).iloc[0]) == [False] * 6 + [True] * 3 + [False]    # 2/3 分位 ≈ 6.33 → 7、8、9；NaN 不挡


def _div(pairs):
    return pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]))


def test_div_cut_cases():
    semi = _div([("2023-03-30", 10), ("2023-09-28", 10), ("2024-03-28", 10), ("2024-09-27", 10)])
    assert not T.div_cut(semi, "2024-11-01")                                  # 不变
    cut = _div([("2023-03-30", 10), ("2023-09-28", 10), ("2024-03-28", 10), ("2024-09-27", 8)])
    assert T.div_cut(cut, "2024-11-01")                                       # 中期 10 → 8（−20%）
    assert not T.div_cut(_div([("2023-09-28", 10), ("2024-09-27", 9.5)]), "2024-10-15")   # −5% 不算
    assert not T.div_cut(_div([("2023-09-28", 10), ("2024-09-27", 12)]), "2024-10-15")    # 增配
    omit = _div([("2023-03-30", 10), ("2023-09-28", 10), ("2024-03-28", 10)])
    assert T.div_cut(omit, "2024-10-20") and not T.div_cut(omit, "2024-10-01")  # 2023-09-28 那一期 2024 年过期 15 天以上还没有 → 停发；还没到期 → 不算
    annual = _div([("2023-03-30", 20), ("2024-03-28", 20)])
    assert not T.div_cut(annual, "2024-10-16") and not T.div_cut(annual, "2025-01-10")   # 一年一次：中间不算停发
    assert not T.div_cut(None, "2024-01-01") and not T.div_cut(_div([]), "2024-01-01")
    assert not T.div_cut(cut, "2024-09-26")                                   # 只用当天为止已知的分红（8 的落ち日在之后）


def test_tick_of_and_dvc_gate_without_cache(monkeypatch):
    d = pd.to_datetime(["2024-01-04", "2024-01-05"])
    assert T.tick_of(["A.T", "B.T"], d, np.array([True, False])) == {("A.T", pd.Timestamp("2024-01-04")): 0.0}
    monkeypatch.setattr(T, "dividends", lambda t: None)
    assert not T.dvc_gate(["A.T"], d[:1]).any()                               # 查不到分红 → 不挡


def test_runs_wiring_and_cli():
    s = inspect.getsource(T.runs)
    assert '"CRC": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}' in s and '"DVC": {"em_tick": dv[e]}' in s
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R3.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert 'runs(W, "J", empty, {"J": {}})' in w and "all(v > 0 for v in n.values())" in w
    assert "LD.actions" not in inspect.getsource(T.dividends)                  # 登记后的运行只读缓存、不下载
    with pytest.raises(SystemExit):
        T.main(["--nope"])
