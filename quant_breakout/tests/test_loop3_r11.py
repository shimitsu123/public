"""第三个研究循环第 11 轮 MXR / IVH / SEC（scripts/loop3_r11_lottery.py，2026-10-03 登记）：登记值、月 MAX 与特质波动（不足 15 天 = NaN）、
横截面最高一成（NaN 不挡）、S5 的同业种贪心、引擎钩子 MixEngine.SECTOR_CAP（同业种持有 / 今天已排 → 不开；明天要卖的不算；核心 ETF、美股、查不到业种的不挡）、
run 的传入与复位、接线与命令行。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r11_lottery as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.TOP_Q, T.MIN_DAYS) == (11, ("MXR", "IVH", "SEC"), False, "stock", 0.90, 15)
    assert T.FAMILY == {"MXR": "选股·彩票型", "IVH": "选股·彩票型", "SEC": "选股·组合分散"}
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")
    st = json.loads((ROOT / "var" / "research_loop3.json").read_text(encoding="utf-8"))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        used = {a["id"] for r in st.get("rounds") or [] for a in r.get("approaches") or []}
        fc = R3.family_counts(st)
        assert not set(T.IDS) & used and fc.get("选股·彩票型", 0) + 2 <= R3.FAMILY_CAP and fc.get("选股·组合分散", 0) + 1 <= R3.FAMILY_CAP
        assert R3.used(st) + len(T.IDS) <= R3.CAP


def test_month_stats_max_and_ivol():
    idx = pd.bdate_range("2024-01-01", "2024-02-29")
    rng = np.random.default_rng(5)
    rm = rng.normal(0, 0.01, len(idx))
    e = rng.normal(0, 0.02, len(idx))
    mkt = pd.Series(100 * np.cumprod(1 + rm), index=idx)
    stock = pd.Series(50 * np.cumprod(1 + 1.0 * rm + e), index=idx)
    months = pd.period_range("2024-01", "2024-02", freq="M")
    S = T.month_stats(stock, mkt, months)
    r = stock.pct_change()
    feb = r[r.index.month == 2]
    assert S.at[months[1], "MAX"] == pytest.approx(feb.max())
    assert S.at[months[1], "IVOL"] == pytest.approx(0.02, abs=0.006)            # 残差标准差 ≈ 特质波动
    assert np.isnan(S.at[months[0], "MAX"]) or len(r[r.index.month == 1].dropna()) >= T.MIN_DAYS
    short = T.month_stats(stock.iloc[:10], mkt.iloc[:10], months)
    assert short.isna().all().all()                                          # 不足 15 个交易日 → NaN


def test_top_decile_blocks_only_highest_tenth():
    m = pd.period_range("2024-01", periods=1, freq="M")
    S = pd.DataFrame([[float(v) for v in range(1, 11)] + [np.nan]], index=m, columns=[f"{k}.T" for k in range(11)])
    b = T.top_decile(S)
    assert list(b.iloc[0]) == [False] * 9 + [True, False]                    # 90 分位 = 9.1 → 只有 10；NaN 不挡


def test_sector_greedy_overlap_only():
    days = pd.bdate_range("2024-01-01", periods=40)
    sec = {"A.T": "電気機器", "B.T": "電気機器", "C.T": "銀行業"}
    tk = ["A.T", "C.T", "B.T", "B.T"]
    d = [days[0], days[1], days[3], days[12]]
    h = [10, 5, 5, 5]
    assert list(T.sector_greedy(tk, d, h, sec, days)) == [False, False, True, False]   # B 在 A 的持有期里 → 去掉；A 卖掉之后 → 保留
    assert list(T.sector_greedy(["Z.T"], [days[0]], [5], sec, days)) == [False]       # 查不到业种 → 不挡


def _eng():
    import candle_portfolio as CP
    eng = CP.MixEngine.__new__(CP.MixEngine)                                 # 只测这个方法：不跑完整引擎
    eng.nxt = {"JP": np.arange(1, 11), "US": np.arange(1, 11)}
    eng.live_mult, eng.em = {}, {"JP": None, "US": None}
    eng.core_set = {"1655.T"}
    eng.col = {"7203.T": 0, "7201.T": 1, "8306.T": 2, "1655.T": 3, "AAPL": 4, "9999.T": 5}
    eng.mkt = np.array(["JP", "JP", "JP", "JP", "US", "JP"])
    eng.st = SimpleNamespace(plan={}, pos={}, pending_exit={})
    eng.skipped = {"macro": 0}
    return CP, eng


def test_sector_cap_hook():
    CP, eng = _eng()
    sec = {"7203.T": "輸送用機器", "7201.T": "輸送用機器", "8306.T": "銀行業", "1655.T": "ETF"}
    assert CP.MixEngine.SECTOR_CAP is None
    try:
        CP.MixEngine.SECTOR_CAP = sec
        assert eng._entry_mult("7203.T", 0) == 1.0                              # 没有持仓
        eng.st.pos = {"7201.T": object()}
        assert eng._entry_mult("7203.T", 0) == 0.0                              # 同业种持有中
        assert eng._entry_mult("8306.T", 0) == 1.0                              # 别的业种
        assert eng._entry_mult("9999.T", 0) == 1.0 and eng._entry_mult("AAPL", 0) == 1.0   # 查不到业种 / 美股不挡
        eng.st.pending_exit = {"7201.T": "x6"}
        assert eng._entry_mult("7203.T", 0) == 1.0                              # 明天要卖的不算
        eng.st.pos, eng.st.pending_exit, eng.st.plan = {}, {}, {"7201.T": [1.0, 100, "2024-01-01"]}
        assert eng._entry_mult("7203.T", 0) == 0.0                              # 今天已排同业种
        assert eng.skipped["sector_cap"] == 2
    finally:
        CP.MixEngine.SECTOR_CAP = None


def test_run_passes_and_resets_sector_cap_and_wiring_cli():
    import inspect
    import candle_portfolio as CP
    r = inspect.getsource(CP.make_runner)
    assert "sector_cap: dict | None = None" in r and "MixEngine.SECTOR_CAP = sector_cap or None" in r
    assert r.count("MixEngine.SECTOR_CAP = None") == 1
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R3.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    ru = inspect.getsource(T.runs)
    assert '"SEC": {"sector_cap": sec}' in ru and 'RM.em_tick_of(G[e]["MXR"], days)' in ru
    w = inspect.getsource(T.wiring)
    assert "runs(W, \"J\", empty, {})" in w and "all(v > 0 for v in n.values())" in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
