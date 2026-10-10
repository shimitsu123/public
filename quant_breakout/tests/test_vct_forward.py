"""VCT 前向记录（qbreak/vct_forward.py，2026-10-04 登记）：信号与研究（第六个循环第 9 轮）逐项相同、配置 = 研究的 core_weights、
东证日的对齐、只追加、B3 状态的来源、影子账户的生效日与换仓成本、判定条件、sim-day / 日报的接线。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from qbreak import vct_forward as VF  # noqa: E402


def _walk(start, end, seed, vol=0.012, drift=0.0004):
    idx = pd.bdate_range(start, end)
    r = np.random.default_rng(seed).normal(drift, vol, len(idx))
    r[len(idx) // 3: len(idx) // 3 + 40] -= 0.01                          # 一段急跌（让信号有成立的日子）
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def test_registered_constants():
    assert VF.FORWARD_START == "2026-10-05" and VF.LOG_FILE == "vct_forward.csv" and VF.DEADLINE == "2031-10-04"
    assert (VF.WIN_N, VF.TGT_START, VF.TGT_MIN, VF.BAND, VF.TREND_N) == (20, "1986-01-01", 250, 0.10, 50)
    assert VF.KEEP == pytest.approx(2 / 3) and (VF.NDX_DIV_PRE, VF.QQQ_ER, VF.SWITCH_COST) == (0.6, 0.20, 0.1)
    assert VF.JUDGE == {"min_days": 365, "min_differ": 40, "min_segments": 2, "seg_min": 5, "dd_need": -10.0, "dd_gain_pp": 1.0,
                        "calmar_tol": 0.05}


def test_signal_identical_to_research():
    import equity_idle_study as EI
    import loop6_r07_volbond as V
    import loop6_r08_voltrend as X
    import loop_r01_voltarget as VT
    assert (VT.WIN_N, VT.TGT_START, VT.TGT_MIN, VT.BAND, X.TREND_N) == (VF.WIN_N, VF.TGT_START, VF.TGT_MIN, VF.BAND, VF.TREND_N)
    assert (EI.NDX_DIV_PRE, EI.QQQ_ER) == (VF.NDX_DIV_PRE, VF.QQQ_ER)
    ndx = _walk("1985-10-01", "2026-10-02", 1)
    qqq = _walk("1999-03-10", "2026-10-02", 2) * 0.3
    tr = EI.ndx_tr({"ndx": ndx, "qqq": qqq})
    ratio = V.vt_ratio(tr)
    sig = X.signal(ratio, X.trend_down(tr))
    us = VF.series(ndx, qqq)
    assert np.allclose(us["ndx_tr"].to_numpy(), tr.reindex(us.index).to_numpy())
    assert np.allclose(us["vt_ratio"].to_numpy(), ratio.reindex(us.index).to_numpy())
    assert us["signal"].to_numpy().tolist() == sig.reindex(us.index).astype(bool).to_numpy().tolist()
    assert us["signal"].any() and not us["signal"].all()
    cut = us.index[len(us) // 2]                                          # 截到某一天再算 = 全历史里那一天（没有偷看）
    us2 = VF.series(ndx[ndx.index <= cut], qqq[qqq.index <= cut])
    assert bool(us2["signal"].iloc[-1]) == bool(us.loc[cut, "signal"]) and us2["vt_ratio"].iloc[-1] == pytest.approx(us.loc[cut, "vt_ratio"])


def test_allocation_equals_research_core_weights():
    import loop6_r09_volcash as C
    combos = [(b, s, o) for b in (False, True) for s in (False, True) for o in (False, True)]
    idx = pd.bdate_range("2026-01-05", periods=len(combos))
    bear = pd.Series([c[0] for c in combos], index=idx)
    sig = pd.Series([c[1] for c in combos], index=idx)
    on = pd.Series([c[2] for c in combos], index=idx)
    w = C.core_weights(bear, sig, on)
    w0 = C.core_weights(bear, pd.Series(False, index=idx), on)            # 信号永远不成立 = B3
    for i, (b, s, o) in enumerate(combos):
        a = VF.allocation(b, o, s)
        assert (a["vct_1545"], a["vct_1482"]) == pytest.approx((w["u"].iloc[i], w["b"].iloc[i]))
        assert (a["b3_1545"], a["b3_1482"]) == pytest.approx((w0["u"].iloc[i], w0["b"].iloc[i]))
    assert VF.allocation(False, True, None) == VF.allocation(False, True, False)   # 算不了 → B3


def test_asof_alignment_matches_on_idx():
    import loop6_r03_earlyreturn as N3
    us_idx = pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"])
    df = pd.DataFrame({"signal": [False, True, False]}, index=us_idx)
    for d in ("2026-10-02", "2026-10-03", "2026-10-04"):
        ud, r = VF.asof_row(df, d)
        assert str(ud.date()) == "2026-10-02" and bool(r["signal"]) is True
        assert bool(N3.on_idx(df["signal"], pd.DatetimeIndex([d])).iloc[0]) is True
    assert VF.asof_row(df, "2026-09-30") == (None, None)


def test_b3_inputs():
    assert VF.b3_inputs({"mode": "Q1HB"})[0] is None
    assert VF.b3_inputs({"mode": "Q1B", "bond_refuge": {"us_bear": None, "on": True}})[:2] == (None, None)
    assert VF.b3_inputs({"mode": "Q1B", "bond_refuge": {"us_bear": False, "on": None}})[:2] == (False, None)
    assert VF.b3_inputs({"mode": "Q1B", "bond_refuge": {"us_bear": True, "on": True}}) == (True, True, "")


def test_run_day_appends_once(tmp_path):
    ndx = _walk("1985-10-01", "2026-10-02", 3)
    qqq = _walk("1999-03-10", "2026-10-02", 4)
    ic = {"mode": "Q1B", "bond_refuge": {"us_bear": False, "on": False}}
    fp = tmp_path / VF.LOG_FILE
    r0 = VF.run_day(fp, "2026-10-02", "2026-10-04", ic, ndx, qqq)        # 开始日之前：不记
    assert not r0["logged"] and not fp.exists()
    r1 = VF.run_day(fp, "2026-10-02", "2026-10-05", ic, ndx, qqq)
    r2 = VF.run_day(fp, "2026-10-02", "2026-10-05", ic, ndx, qqq)        # 同一个决策日：不重复
    assert r1["logged"] and not r2["logged"]
    log = VF.load_log(fp)
    assert list(log.columns) == VF.COLS and len(log) == 1 and log["us_date"].iloc[0] == "2026-10-02"
    r3 = VF.run_day(fp, "2026-10-05", "2026-10-06", {"mode": "Q1B", "bond_refuge": {"us_bear": None}}, ndx, qqq)
    assert r3["logged"] and "美股牛熊取不到" in r3["row"]["note"] and r3["row"].get("vct_1545") is None
    r4 = VF.run_day(fp, "2026-10-06", "2026-10-07", ic, ndx.iloc[:0], qqq.iloc[:0])   # 行情取不到 → 照样记一行、信号空
    assert r4["logged"] and "信号算不了" in r4["row"]["note"] and r4["row"].get("signal") is None
    assert VF.status(fp)["rows"] == 3


def _log(rows):
    return pd.DataFrame([{**{c: None for c in VF.COLS}, **r} for r in rows], columns=VF.COLS)


def test_shadow_effective_next_open_and_costs():
    days = pd.bdate_range("2026-10-05", periods=6)
    o1545 = pd.Series([100, 110, 99, 99, 108.9, 108.9], index=days, dtype=float)
    o1482 = pd.Series([100.0] * 6, index=days)
    log = _log([{"decision_date": "2026-10-02", "signal": 0, "b3_1545": 1, "b3_1482": 0, "vct_1545": 1, "vct_1482": 0, "differ": 0},
                {"decision_date": "2026-10-05", "signal": 1, "b3_1545": 1, "b3_1482": 0, "vct_1545": 2 / 3, "vct_1482": 0, "differ": 1},
                {"decision_date": "2026-10-06", "signal": 0, "b3_1545": 1, "b3_1482": 0, "vct_1545": 1, "vct_1482": 0, "differ": 0}])
    w = VF.weights(log)
    nb = VF.shadow(w, {"1545.T": o1545, "1482.T": o1482}, "b3")
    nv = VF.shadow(w, {"1545.T": o1545, "1482.T": o1482}, "vct")
    c = VF.SWITCH_COST / 100
    assert nb.iloc[0] == pytest.approx(1 - c)                              # 10-05 开盘买进（决策 10-02）
    assert nb.iloc[-1] == pytest.approx((1 - c) * 1.089)
    # VCT：10-06 开盘起 2/3（决策 10-05）、10-07 开盘起回到 1（决策 10-06）；10-05→10-06 的 +10% 全额拿到
    exp = (1 - c) * 1.10 * (1 - c / 3) * (1 + 2 / 3 * (99 / 110 - 1)) * (1 - c / 3) * 1.0 * 1.10 * 1.0
    assert nv.iloc[-1] == pytest.approx(exp)
    seg = VF.segments(log, {"1545.T": o1545})
    assert seg == [{"from": "2026-10-05", "to": "2026-10-05", "days": 1, "r1545": pytest.approx(-10.0)}]
    nosig = _log([{"decision_date": "2026-10-02", "signal": None, "b3_1545": 1, "b3_1482": 0, "vct_1545": 2 / 3, "vct_1482": 0}])
    assert VF.weights(nosig)["vct_1545"].iloc[0] == 1.0                   # 信号空 → VCT = B3


def test_judge_rules():
    days = pd.bdate_range("2026-10-02", periods=60)
    rows = [{"decision_date": str(d.date()), "differ": int(10 <= i < 35 or 40 <= i < 58)} for i, d in enumerate(days)]
    log = _log(rows)
    j = VF.judge(log, {"calmar": 0.5, "dd": -15.0}, {"calmar": 0.6, "dd": -12.0}, -15.0, "2027-01-01")
    assert not j["eligible"] and j["need"]["days"] is False and j["need"]["differ"] and j["need"]["segments"] and j["need"]["dd"]
    j = VF.judge(log, {"calmar": 0.5, "dd": -15.0}, {"calmar": 0.6, "dd": -12.0}, -15.0, "2027-10-05")
    assert j["eligible"] and j["label"].startswith("前向支持")
    j = VF.judge(log, {"calmar": 0.5, "dd": -15.0}, {"calmar": 0.6, "dd": -14.5}, -15.0, "2027-10-05")
    assert j["label"] == "未定"                                            # 回撤只浅 0.5 pp
    j = VF.judge(log, {"calmar": 0.5, "dd": -15.0}, {"calmar": 0.44, "dd": -12.0}, -15.0, "2027-10-05")
    assert j["label"].startswith("前向不支持")
    j = VF.judge(log, {"calmar": 0.5, "dd": -8.0}, {"calmar": 0.6, "dd": -6.0}, -8.0, "2031-10-04")
    assert not j["eligible"] and j["label"].startswith("5 年内")              # B3 没跌到 −10% → 判不了


def test_wired_into_sim_day_and_report():
    import run
    from qbreak import report_unified as RU
    assert "VF.run_day(paths.out_dir() / VF.LOG_FILE, str(ctx.bar_date), str(today), ctx.ic_status)" in inspect.getsource(run._vct_forward_log)
    assert 'out["vct_forward"] = _vct_forward_log(ctx, today)' in inspect.getsource(run)
    html = RU._vct_html({"date": "2026-10-02", "us_date": "2026-10-02", "signal": True, "high": True, "down": True, "vt_ratio": 0.8,
                         "ndx_tr": 95.0, "sma50": 100.0, "us_bear": False, "vct_1545": 2 / 3, "vct_1482": 0.0, "differ": True,
                         "rows": 3, "differ_days": 1, "start": VF.FORWARD_START})
    assert "急跌信号 成立" in html and "现金 33%" in html and "与模拟盘 B3 不同" in html and "-5.0%（对 50 日线）" in html
    assert RU._vct_html({}) == "" and "没算出" in RU._vct_html({"error": "x"})
    assert "{vct}" in inspect.getsource(RU)
