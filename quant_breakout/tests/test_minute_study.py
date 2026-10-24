"""分钟 K 线 / 日内规则研究（scripts/minute_study.py；2026-10-15 事先登记）：t 分布与 BH、成本模型与立花個別コース、
限价 / 逆指値的成交、锁死顺延、前视保护（选票的那根早于成交、入场当天不查盘中、同一天两边都碰到取不利的）、
复权日线与分钟线不能混用、--check / --smoke 不算收益、冻结清单哈希不一致与「只运行一次」拒绝运行、逐信号模拟 = 引擎单只回测。"""
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import minute_study as MS                                                     # noqa: E402

from qbreak.config import StrategyParams                                      # noqa: E402
from qbreak.fees import FeeSchedule, TACHIBANA_KOBETSU                        # noqa: E402

XP = {"stop": 0.07, "trail": 0.12, "tp": 0.25, "chand": 3.0, "climax": True, "climax_gain": 5.0, "max_hold": 60}


@pytest.fixture(autouse=True)
def _mode():
    MS.set_mode("run")
    yield
    MS.set_mode("run")


# ── 统计 ──
def test_t_sf_known_values():
    assert MS.t_sf(2.0, 30) == pytest.approx(0.02731, abs=2e-5)
    assert MS.t_sf(0.0, 12) == pytest.approx(0.5, abs=1e-12)
    assert MS.t_sf(1.0, 1) == pytest.approx(0.25, abs=1e-9)                  # 自由度 1 = Cauchy
    assert MS.t_sf(-2.0, 30) == pytest.approx(1 - 0.02731, abs=2e-5)
    assert MS.t_sf(1.959964, 1e7) == pytest.approx(0.025, abs=1e-5)          # 自由度很大 → 正态
    assert MS.t_sf(2.0, 5) == pytest.approx(0.05097, abs=2e-5)
    assert MS.t_isf(0.05, 10) == pytest.approx(1.8125, abs=1e-3)
    assert np.isnan(MS.t_sf(float("nan"), 10)) and np.isnan(MS.t_sf(1.0, 0))


def test_bh_m_fixed_eleven_and_undecided_is_one():
    assert MS.BH_M == 11 and len(MS.CELLS) == 11 and "A2" not in MS.CELLS
    r = MS.apply_bh({"A1": 0.001})                                           # 0.001 ≤ 0.10 × 1 / 11
    assert r["A1"] and not any(v for k, v in r.items() if k != "A1")
    r = MS.apply_bh({"A1": 0.01, "C1": None, "D1": float("nan")})            # 0.01 > 0.10 / 11（m = 1 时会过）
    assert not any(r.values())
    r = MS.apply_bh({c: 0.005 for c in MS.CELLS})
    assert all(r.values())


def test_month_t_clusters_by_calendar_month_across_samples():
    d = ["2010-01-05", "2010-01-20", "2010-02-03", "2010-03-03"]
    s = MS.month_t(d, [0.01, 0.03, 0.01, 0.02])
    assert s["months"] == 3 and s["n"] == 4
    assert s["mean"] == pytest.approx(1.75)
    mm = np.array([0.02, 0.01, 0.02])
    t = mm.mean() / (mm.std(ddof=1) / np.sqrt(3))
    assert s["t"] == pytest.approx(t) and s["p"] == pytest.approx(MS.t_sf(t, 2))


def test_halves_w_uses_e_and_jx_uses_j():
    import leap_common as LM
    assert MS.half_bounds("W") == MS.half_bounds("E") == tuple(LM.HALVES["E"])
    (a1, b1), (a2, b2) = MS.half_bounds("Jx")
    assert (a1, b1) == LM.HALVES["J"][0] and b2 == MS.J_END
    h = MS.half_of("Z", ["2002-01-04", "2005-01-04", "2007-01-04"])
    assert list(h) == [1, 2, 0]


# ── 成本 ──
def test_cost_model_matches_tachibana_kobetsu_tiers():
    fee = FeeSchedule(tiers=TACHIBANA_KOBETSU)
    assert MS.fee_pct(250_000) == pytest.approx(187 / 250_000)
    assert MS.rt_cost(250_000) == pytest.approx(0.001496)
    assert MS.fee_pct(125_000) == pytest.approx(99 / 125_000)
    assert MS.rt_cost(125_000, 0.001, 0.001) == pytest.approx(2 * 99 / 125_000 + 0.002)
    for x in (50_000, 100_000, 100_001, 200_000, 500_000, 1_000_000, 3_000_000):
        assert MS.fee_pct(x) == pytest.approx(fee(x) / x)
    assert MS.FEE.tiers == TACHIBANA_KOBETSU
    assert MS.fee_pct_vec(np.array([250_000.0, np.nan]))[0] == pytest.approx(187 / 250_000)


def test_threshold_table_consistent_with_costs():
    assert MS.rt_cost(250_000, 0, 0.001) * 100 == pytest.approx(0.2496, abs=1e-4)          # B ≈ 0.25%
    assert MS.rt_cost(250_000, 0.001, 0.001) * 100 == pytest.approx(0.3496, abs=1e-4)      # C1 / C2 / D ≈ 0.35%
    assert MS.rt_cost(125_000, 0.001, 0.001) * 100 == pytest.approx(0.3584, abs=1e-4)      # C3 ≈ 0.36%


# ── 成交 ──
def test_limit_buy_must_penetrate_one_tick():
    assert MS.limit_buy_fill(1000.0, 1000.0, 1.0) is None                    # 只碰到不算
    assert MS.limit_buy_fill(1000.0, 999.5, 1.0) is None
    assert MS.limit_buy_fill(1000.0, 999.0, 1.0) == 1000.0                   # 穿过 1 tick：按限价、0 滑点
    assert MS.tick_of(2999) == 1 and MS.tick_of(3000) == 1 and MS.tick_of(3001) == 5    # tick 按不复权价
    assert MS.tick_adj(1600.0, 2.0) == pytest.approx(5 / 2)                  # 不复权 3,200 → 5 円 → 复权单位 2.5
    assert MS.tick_adj(1000.0, float("nan")) == pytest.approx(1.0)           # 还原不了 → 价格的 0.1%


def test_stop_fills_gap_and_cap():
    assert MS.stop_sell_fill(100.0, 95.0, 90.0) == 95.0                      # 跳空低开 → 按开盘
    assert MS.stop_sell_fill(100.0, 105.0, 99.0) == 100.0
    assert MS.stop_sell_fill(100.0, 105.0, 101.0) is None
    assert MS.stop_buy_fill(100.0, 103.0, 110.0) == 103.0                    # 跳空高开 → 按开盘
    assert MS.stop_buy_fill(100.0, 98.0, 101.0) == 100.0
    assert MS.stop_buy_fill(100.0, 98.0, 99.0) is None
    assert MS.stop_buy_fill(100.0, 98.0, 120.0, cap=99.0) is None            # 触发价超出涨停价 → 不成交


def test_vectorized_tick_and_limit_match_scalar():
    from qbreak.tick import price_limit_jp, tick_size
    xs = np.array([99, 100, 101, 2999, 3000, 3001, 5000, 5001, 30000, 30001, 50001, 1e6])
    assert list(MS.tick_vec(xs)) == [tick_size(float(x), None, on=MS.TICK_ON) for x in xs]
    assert list(MS.limit_width_vec(xs)) == [price_limit_jp(float(x)) for x in xs]
    assert MS.floor_tick_vec(np.array([3002.7]))[0] == 3000 and MS.ceil_tick_vec(np.array([3000.2]))[0] == 3005


def test_lock_uses_raw_prices_and_todays_base():
    assert MS.lock(1000, 700, 700, 700) == "down"                            # 1,000 円 → 制限値幅 300；≥ 8 成且 H = L
    assert MS.lock(1000, 760, 700, 700) is None                               # 有价差 → 不是锁死
    assert MS.lock(400, 330, 330, 330) == "down"                             # 按复权价查表：400 → 值幅 80，−70 ≥ 64
    assert MS.lock(400, 330, 330, 330, 2.5, 2.5) is None                     # 按不复权价：1,000 → 825 = −175 < 240
    assert MS.lock(1000, 700, 700, 700, 2.0, 1.0) == "down"                  # 拆股当天：基准 = 前日收盘 × 当天系数
    assert MS.limit_band(1000, 2.0, 1.0) == pytest.approx((700, 1300))


def _panel(O, H, L, C, ex=None, name="Z"):
    n, m = np.asarray(C).shape
    days = pd.bdate_range("2003-01-06", periods=n)
    V = np.full((n, m), 1e6)
    P = MS.build_panel(name, {"O": np.asarray(O, float), "H": np.asarray(H, float), "L": np.asarray(L, float), "C": np.asarray(C, float),
                             "V": V}, days, [f"{9000 + j}.T" for j in range(m)], np.ones((n, m)), np.ones((n, m)),
                       np.zeros((n, m), bool) if ex is None else ex)
    return P


def test_b_limit_needs_penetration_and_locked_exit_defers():
    O = [[1000], [1000], [1000], [1000]]
    H = [[1010], [1010], [1000], [1050]]
    L = [[990], [979], [700], [990]]
    C = [[1000], [990], [700], [1000]]                                      # 第 2 行跌停锁死（H = L = C、−300）
    H[2][0] = L[2][0] = C[2][0] = O[2][0] = 700
    P = _panel(O, H, L, C)
    b = MS.fam_B(P, 0.02, "n")
    rows = b["rows"]
    assert list(rows["i"]) == [1]                                             # 限价 980：第 1 行最低 979 = 980 − 1 tick → 成交
    assert rows["entry"].iloc[0] == 980 and rows["si"].iloc[0] == 0
    assert rows["xi"].iloc[0] == 3 and rows["exit"].iloc[0] == 1000          # 次日（第 2 行）跌停锁死 → 顺延到第 3 行寄付
    L2 = [[990], [980], [700], [990]]
    P2 = _panel(O, H, L2, C)
    assert len(MS.fam_B(P2, 0.02, "n")["rows"]) == 0                          # 只碰到限价不算


def test_ex_date_crossing_dropped_for_overnight_holds():
    O = np.full((4, 2), 1000.0)
    C = np.array([[1000, 1000], [950, 950], [1000, 1000], [1000, 1000]], float)
    H, L = np.maximum(O, C) * 1.001, np.minimum(O, C) * 0.999
    ex = np.zeros((4, 2), bool)
    ex[2, 0] = True                                                           # 第 0 只第 2 行除权
    P = _panel(O, H, L, C, ex=ex)
    d = MS.fam_D(P, "close1")
    assert set(zip(d["rows"]["i"], d["rows"]["j"])) & {(1, 0)} == set()       # 持有跨除权 → 剔除（排序之前）
    assert (1, 1) in set(zip(d["rows"]["i"], d["rows"]["j"]))


def test_c_trigger_rounded_up_and_capped():
    O = [[1000], [1000]]
    H = [[1010], [1021]]
    L = [[990], [995]]
    C = [[1000], [1005]]
    P = _panel(O, H, L, C)
    r = MS.fam_C(P, "C1")["rows"]
    assert list(r["entry"]) == [1020.0] and r["si"].iloc[0] == 1 and r["exit"].iloc[0] == 1005
    H2 = [[1010], [1019]]
    assert len(MS.fam_C(_panel(O, H2, L, C), "C1")["rows"]) == 0


# ── 前视保护 ──
def _arr(O, H, L, C, atr=None):
    n = len(C)
    return {"days": pd.bdate_range("2010-01-04", periods=n), "O": np.asarray(O, float), "H": np.asarray(H, float),
            "L": np.asarray(L, float), "C": np.asarray(C, float), "atr": np.full(n, 1.0) if atr is None else np.asarray(atr, float),
            "climax": np.zeros(n, bool), "F": np.full(n, np.nan)}


def test_entry_day_not_checked_intraday_for_a1_a2_a3():
    O = [100, 100, 101, 101, 101, 101]
    H = [101, 101, 102, 102, 102, 102]
    L = [99, 90, 100, 100, 100, 100]                                        # 入场当天（第 1 行）盘中跌破 −7%
    C = [100, 99, 101, 101, 101, 101]
    a = _arr(O, H, L, C)
    intra = MS.simulate_exits(a, 0, XP, "INTRA", gap_pct=3.0)
    assert intra["i_exit"] == 1 and intra["reason"] == "stop"                # 引擎 intraday：入场当天就止损
    for m in ("A1", "A2", "A3"):
        r = MS.simulate_exits(a, 0, XP, m, gap_pct=3.0)
        assert r["entered"] and r.get("i_exit") != 1                           # 入场当天只按收盘判定
        assert r["entry_touch"] is (m != "A2")                                # 记下「入场当天盘中碰到了」（A2 的灾难线 −12% 没碰到）


def test_same_day_stop_and_target_take_the_bad_one():
    O = [100, 100, 101, 101]
    H = [101, 101, 130, 102]                                                  # 第 2 行最高碰到 +25%
    L = [99, 99, 92, 100]                                                     # 同一天最低也碰到 −7%
    C = [100, 100, 101, 101]
    r = MS.simulate_exits(_arr(O, H, L, C), 0, XP, "A1", gap_pct=3.0)
    assert r["i_exit"] == 2 and r["reason"] == "stop"
    assert r["exit_px"] == pytest.approx(100 * 1.001 * 0.93 * (1 - MS.SLIP))


def test_c3_trigger_only_from_ten_oclock_bar_and_stop_in_fill_bar():
    idx = pd.DatetimeIndex([pd.Timestamp("2025-03-03")])
    base = {"O": 1000.0, "H": 1100.0, "L": 950.0, "C": 1000.0, "V": 1e6, "sf": 1.0, "ex": False, "pc": 1000.0, "lim_hi": 1300.0,
            "elig": True, "sess": "H2"}
    bars = {f"{c}{h}": np.nan for h in MS.HOURS for c in "ohlcv"}
    bars.update({"o9": 1000, "h9": 1050, "l9": 990, "c9": 1040, "o10": 1040, "h10": 1045, "l10": 1000, "c10": 1040})
    x = pd.DataFrame([{**base, **bars}], index=idx)
    trig = 1050 + 1
    assert MS.c3_path(x, 0, trig, 990, "H2") is None                         # 09:00 那根（选票的那根）不算成交
    x.loc[idx[0], "h11"], x.loc[idx[0], "o11"], x.loc[idx[0], "l11"], x.loc[idx[0], "c11"] = 1060, 1045, 985, 1000
    e, xpx, hh = MS.c3_path(x, 0, trig, 990, "H2")
    assert (e, xpx, hh) == (1051, 990, 11)                                    # 成交那根里也碰到止损 → 当作已经止损


def test_h1_auction_bar_not_used_for_stops():
    idx = pd.DatetimeIndex([pd.Timestamp("2024-03-04")])
    bars = {f"{c}{h}": np.nan for h in MS.HOURS for c in "ohlcv"}
    bars.update({"o9": 1000, "h9": 1010, "l9": 995, "c9": 1008, "o10": 1008, "h10": 1020, "l10": 1005, "c10": 1015,
                 "o15": 900, "h15": 900, "l15": 900, "c15": 900})                # H1 的 15:00 那根 = 收盘竞价
    base = {"O": 1000.0, "H": 1020.0, "L": 900.0, "C": 900.0, "V": 1e6, "sf": 1.0, "ex": False, "pc": 1000.0, "lim_hi": 1300.0,
            "elig": True, "sess": "H1"}
    x = pd.DataFrame([{**base, **bars}], index=idx)
    e, xpx, hh = MS.c3_path(x, 0, 1011, 995, "H1")
    assert hh == 16 and xpx == 900                                            # 没在 15:00 那根止损，按正式收盘卖


def test_adjusted_daily_cannot_mix_with_minute_bars():
    h = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1.0]},
                     index=pd.DatetimeIndex([pd.Timestamp("2025-03-03 10:00", tz="Asia/Tokyo")]))
    with pytest.raises(ValueError):
        MS.day_groups(h)                                                      # 没有 basis = raw 的标记 → 拒绝
    with pytest.raises(ValueError):
        MS.t2_table({}, {"7203.T": h.tz_localize(None)}, {}, ["7203.T"])
    h.attrs["basis"] = "raw"
    assert len(MS.day_groups(h)) == 1


# ── --check / --smoke 不算收益 ──
GATED = ["trade_returns", "pool_returns", "pool_by_day_returns", "placebo", "a_returns", "stage1_cell", "stage1_c3", "stage1_A",
         "judge_A2", "drt_gate", "run_A_account", "overlay", "stage2_cell", "stage2_A", "teigaku_report", "desc_etf_momentum",
         "realism_at", "desc_fill_calib", "desc_b0_split", "desc_D_overlap_first_touch", "desc_outage", "desc_session",
         "yen_per_year", "b0_series", "core_ret", "eq_metrics", "stage3_check"]


@pytest.mark.parametrize("mode", ["check", "smoke", "fetch"])
def test_return_functions_refuse_in_check_and_smoke(mode):
    MS.set_mode(mode)
    rows = pd.DataFrame({"date": [pd.Timestamp("2010-01-04")], "entry": [100.0], "exit": [101.0], "si": [1], "so": [1],
                         "lot_yen": [1e4], "i": [0]})
    with pytest.raises(MS.ReturnGuardError):
        MS.trade_returns(rows)
    with pytest.raises(MS.ReturnGuardError):
        MS.a_returns(pd.DataFrame())
    with pytest.raises(MS.ReturnGuardError):
        MS.placebo([], 10, [1])
    with pytest.raises(MS.ReturnGuardError):
        MS.pool_returns({"entry": np.ones(1), "exit": np.ones(1), "si": 1, "so": 1})
    for name in GATED:
        src = inspect.getsource(getattr(MS, name))
        assert "guard_returns(" in src, name                                  # 每个算收益的函数都先过 guard


def test_check_and_smoke_paths_call_no_return_function():
    for fn in (MS.do_check, MS.check_core, MS.cell_counts, MS.cell_mde, MS.do_smoke, MS.say_check, MS.a_counts_from):
        src = inspect.getsource(fn)
        for name in GATED:
            assert f"{name}(" not in src, f"{fn.__name__} 调用了 {name}"


def test_smoke_runs_and_writes_no_return_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    assert MS.do_smoke() == 0
    out = json.loads((tmp_path / "out" / "minute_study_partial.json").read_text(encoding="utf-8"))
    MS.set_mode("smoke")
    MS.strip_returns(out)                                                     # 有收益字段会抛 ReturnGuardError
    assert out["mode"] == "smoke" and out["counts"]["B-2c"]
    assert not (tmp_path / "out" / "minute_study.json").exists()
    with pytest.raises(MS.ReturnGuardError):
        MS.strip_returns({"x": {"mean": 0.1}})


# ── 冻结与只运行一次 ──
FROZEN_KINDS = (*MS.INTERVALS, "1m", "1d_raw", "actions")


def _freeze(tmp_path, monkeypatch):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    MS.minute_dir().mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"ticker": ["7203.T"], "ts": [pd.Timestamp("2025-03-03 09:00", tz="Asia/Tokyo")], "Open": [1.0]})
    files = {k: MS.save_cache(k, "2026-10-15", df) for k in FROZEN_KINDS}
    man = {"fetch_date": "2026-10-15", "yfinance": "0", "files": files, "missing": {}}
    MS.freeze_path().write_text(json.dumps(man), encoding="utf-8")
    monkeypatch.setattr(MS, "git_dirty", lambda: [])
    return files["60m"]


def test_hash_mismatch_refuses_run(tmp_path, monkeypatch):
    info = _freeze(tmp_path, monkeypatch)
    assert MS.hard_mismatch(MS.verify_manifest(MS.read_manifest())) == []
    assert MS.run_refusals() == []
    fp = MS.minute_dir() / info["file"]
    pd.DataFrame({"ticker": ["7203.T", "6501.T"], "ts": [pd.Timestamp("2025-03-03 09:00", tz="Asia/Tokyo")] * 2,
                  "Open": [1.0, 2.0]}).to_parquet(fp, index=False)
    why = MS.run_refusals()
    assert any("sha256" in w for w in why)
    assert MS.do_run() == 3


def test_yfinance_version_only_recorded(tmp_path, monkeypatch):
    _freeze(tmp_path, monkeypatch)
    bad = MS.verify_manifest(MS.read_manifest())
    assert any("yfinance" in b for b in bad) and MS.hard_mismatch(bad) == []


def test_run_only_once_and_dirty_tree_refused(tmp_path, monkeypatch):
    _freeze(tmp_path, monkeypatch)
    MS.out_path("json").parent.mkdir(parents=True, exist_ok=True)
    MS.out_path("json").write_text(json.dumps({"ran": True}), encoding="utf-8")
    assert any("只运行一次" in w for w in MS.run_refusals())
    assert MS.do_run() == 3
    MS.out_path("json").unlink()
    monkeypatch.setattr(MS, "git_dirty", lambda: [" M scripts/minute_study.py"])
    assert any("未提交" in w for w in MS.run_refusals())


def test_fetch_refuses_when_frozen(tmp_path, monkeypatch):
    _freeze(tmp_path, monkeypatch)
    assert MS.do_fetch() == 2


def test_manifest_must_list_every_file_under_the_name_that_is_read(tmp_path, monkeypatch):
    """冻结清单删掉一项、或把文件名改成别的文件 → --run 拒绝（读取用 cache_path，清单不能指向别处）。"""
    _freeze(tmp_path, monkeypatch)
    man = MS.read_manifest()
    del man["files"]["1m"]
    MS.freeze_path().write_text(json.dumps(man), encoding="utf-8")
    assert any("少了 1m" in w for w in MS.run_refusals())
    man = MS.read_manifest()
    other = MS.save_cache("1m", "2026-10-16", pd.DataFrame({"ticker": ["7203.T"], "ts": [pd.Timestamp("2025-03-03 09:00")], "Open": [2.0]}))
    man["files"]["1m"] = other                                                 # 哈希与行数都对得上，但不是读取时用的那个文件
    MS.freeze_path().write_text(json.dumps(man), encoding="utf-8")
    assert any("文件名" in w for w in MS.run_refusals())


# ── 逐信号模拟 = 引擎单只回测 ──
def _engine_frame(seed: int = 3, n: int = 400):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2012-01-04", periods=n)
    C = 1000 * np.exp(np.cumsum(rng.normal(0.0005, 0.025, n)))
    O = C * np.exp(rng.normal(0, 0.012, n))
    H = np.maximum(O, C) * (1 + np.abs(rng.normal(0, 0.012, n)))
    L = np.minimum(O, C) * (1 - np.abs(rng.normal(0, 0.012, n)))
    df = pd.DataFrame({"Open": O, "High": H, "Low": L, "Close": C, "Volume": 1e6, "atr": C * 0.03,
                       "climax": rng.random(n) < 0.03, "dead_cross": False}, index=days)
    df["entry"] = False
    df.iloc[sorted(rng.choice(np.arange(10, n - 5), 40, replace=False)), df.columns.get_loc("entry")] = True
    return df


@pytest.mark.parametrize("seed", [3, 8])
def test_a0_and_intraday_simulation_equal_unified_engine(seed):
    from dataclasses import replace

    from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs
    p = StrategyParams(stop_loss_pct=7.0, trailing_stop_pct=12.0, take_profit_pct=25.0, exit_chandelier_k=3.0, exit_on_climax=True,
                       climax_min_gain_pct=5.0, max_hold_days=60, exit_on_macd_dead_cross=False)
    xp = MS.exit_params(p)
    df = _engine_frame(seed)
    ex0 = exec_configs(("JP",), {"broker": "tachibana"})
    gap = ex0["JP"].max_entry_gap_pct
    cfg = UnifiedConfig(capital_jpy=1e12, position_pct=0.5, max_positions=1, max_position_pct=1.0, cash_buffer_pct=0.0,
                        stock_markets=("JP",), core={}, core_index={})
    arr = MS.ticker_arrays(df)
    pos = {d: i for i, d in enumerate(df.index)}
    for mode, ex in (("A0", ex0), ("INTRA", {m: replace(c, stop_fill_mode="intraday") for m, c in ex0.items()})):
        r = UnifiedEngine({"7777.T": df}, cfg, {"JP": p, "US": p}, ex, {}).run()
        tr = r.trades[r.trades["reason"] != "end"]
        assert len(tr) >= 5
        for _, t in tr.iterrows():
            ie = pos[pd.Timestamp(t["entry_date"])]
            s = MS.simulate_exits(arr, ie - 1, xp, mode, gap, raw_lock=False)
            assert str(arr["days"][s["i_exit"]].date()) == t["exit_date"], (mode, t["entry_date"])
            assert round(s["exit_px"], 4) == pytest.approx(float(t["exit_px"]), abs=1.01e-4)
            assert round(s["entry_px"], 4) == pytest.approx(float(t["entry_px"]), abs=1.01e-4)
            if mode == "INTRA" and not s["entry_touch"]:
                a1 = MS.simulate_exits(arr, ie - 1, xp, "A1", gap, raw_lock=False)
                assert a1["i_exit"] == s["i_exit"] and a1["exit_px"] == pytest.approx(s["exit_px"])


def test_exit_params_refuse_unmirrored_branches():
    with pytest.raises(ValueError):
        MS.exit_params(StrategyParams(exit_on_macd_dead_cross=True))
    with pytest.raises(ValueError):
        MS.exit_params(StrategyParams(exit_on_macd_dead_cross=False, time_stop_days=10))


def _hand_frame(rows):
    """手写的几行日线（O, H, L, C）；信号在第 1 行（第 2 行开盘买）。"""
    days = pd.bdate_range("2013-03-04", periods=len(rows))
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=days, dtype=float)
    df["Volume"], df["atr"], df["climax"], df["dead_cross"] = 1e6, 10.0, False, False
    df["entry"] = False
    df.iloc[1, df.columns.get_loc("entry")] = True
    return df


FLAT = [100, 101, 99, 100]
HAND = {
    "cat_stop": [FLAT, FLAT, FLAT, [99, 99.5, 85, 95]] + [FLAT] * 6,           # 第 3 行盘中 −15%：A2 的灾难线、A1 / A3 的止损
    "locked_stop": [FLAT, FLAT, FLAT, [55, 55, 55, 55], [60, 70, 58, 65]] + [[65, 66, 64, 65]] * 5,   # 跌停锁死 → 顺延到下一天寄付
    "gap_down": [FLAT, FLAT, FLAT, [90, 91, 80, 85]] + [[85, 86, 84, 85]] * 6,  # 跳空低开穿过止损
}


@pytest.mark.parametrize("seed", [3, 8])
def test_minute_stop_engine_equals_simulation(seed):
    """MinuteStopEngine（账户级用的 A1 / A2 / A3）与逐信号模拟逐笔一致：随机行情 + 手写的灾难线 / 锁死 / 跳空。"""
    from qbreak.unified import UnifiedConfig, exec_configs
    p = StrategyParams(stop_loss_pct=7.0, trailing_stop_pct=12.0, take_profit_pct=25.0, exit_chandelier_k=3.0, exit_on_climax=True,
                       climax_min_gain_pct=5.0, max_hold_days=60, exit_on_macd_dead_cross=False)
    xp = MS.exit_params(p)
    ex0 = exec_configs(("JP",), {"broker": "tachibana"})
    cfg = UnifiedConfig(capital_jpy=1e12, position_pct=0.5, max_positions=1, max_position_pct=1.0, cash_buffer_pct=0.0,
                        stock_markets=("JP",), core={}, core_index={})
    E = MS.minute_engine_class()
    full = _engine_frame(seed)
    full["entry"] = False
    subs = []
    for k in np.flatnonzero(_engine_frame(seed)["entry"].to_numpy()):
        if k + 101 <= len(full):
            sub = full.iloc[k - 1:k + 101].copy()
            sub.iloc[1, sub.columns.get_loc("entry")] = True
            subs.append(sub)
    subs += [_hand_frame(r) for r in HAND.values()]
    seen = {}
    try:
        for sub in subs:
            arr = MS.ticker_arrays(sub)
            for m in ("A1", "A2", "A3"):
                E.MODE, E.HITS = m, {}
                tr = E({"7777.T": sub}, cfg, {"JP": p, "US": p}, ex0, {}).run().trades
                s = MS.simulate_exits(arr, 1, xp, m, ex0["JP"].max_entry_gap_pct, raw_lock=False)
                if not len(tr):
                    assert not s["entered"]
                    continue
                t = tr.iloc[0]
                if t["reason"] == "end":
                    continue
                assert str(arr["days"][s["i_exit"]].date()) == t["exit_date"], (m, sub.index[1])
                assert round(s["exit_px"], 4) == pytest.approx(float(t["exit_px"]), abs=1.01e-4)
                assert t["reason"] == s["reason"]
                seen.setdefault(m, set()).add(s["reason"])
    finally:
        E.MODE, E.HITS = None, {}
    assert "cat_stop" in seen["A2"] and {"stop", "gap_stop"} <= seen["A1"] and "stop" in seen["A3"]


# ── --run 的计算路径：只用合成数据跑通（合成数据的收益没有任何意义，只查会不会出错、结构对不对） ──
def _synth_sigs_in(smp: str, seed: int) -> pd.DataFrame:
    frames, ks = MS.synth_signals(n=80, seed=seed)
    df = frames["9999.T"].copy()
    step = len(pd.bdate_range(*MS.WIN[smp])) // 210
    df.index = pd.bdate_range(MS.WIN[smp][0], periods=len(df), freq=f"{step}B")  # 摊到这个样本的整个窗口里（两半都有）
    a = MS.ticker_arrays(df)
    return pd.DataFrame([{"sample": smp, "ticker": "9999.T", "date": df.index[k], **MS.a_signal_row(a, k, XP, 3.0)} for k in ks])


def _long_daily(d: pd.DataFrame, n: int = 440, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=d.index[0] - pd.Timedelta(days=1), periods=n)
    C = float(d["Close"].iloc[0]) * np.exp(np.cumsum(rng.normal(0, 0.02, n))[::-1] * -1)
    O = C * np.exp(rng.normal(0, 0.01, n))
    pre = pd.DataFrame({"Open": O, "High": np.maximum(O, C) * 1.01, "Low": np.minimum(O, C) * 0.99, "Close": C, "AdjClose": C,
                        "Volume": rng.uniform(5e5, 2e6, n)}, index=days)
    out = pd.concat([pre, d])
    out.attrs["basis"] = "raw"
    return out


def test_run_stage1_and_desc_paths_on_synthetic_data(tmp_path, monkeypatch):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    MS.set_mode("run")
    panels = {s: MS.synth_panel(s, n_days=500, n_names=40, seed=i + 1, member=(s == "Jx")) for i, s in enumerate(MS.SAMPLES)}
    h60, m5, d1, acts = MS.synth_t2(n_names=12, n_days=60)
    tab = MS.t2_table(h60, d1, acts, list(h60))
    stocks = {t: x for t, x in tab.items() if t not in MS.ETFS}
    cells, drt, all_books = {}, {}, {}
    for cell, ek in (("D1", "open1"), ("D2", "close1")):
        drt[cell] = MS.drt_gate(MS.fam_D_rt(stocks, ek), ek)
        assert set(drt[cell]) >= {"n_rt", "mean_rt", "n_off", "mean_off", "ok"}
    for cell in MS.CELL_SPEC:
        fam = MS.CELL_SPEC[cell][0]
        books = all_books[cell] = {s: MS.cell_book(panels[s], cell) for s in list(MS.JUDGE[fam]) + list(MS.REFERENCE.get(fam, ()))}
        aff = {s: MS.cell_book(panels[s], cell, afford=True) for s in MS.JUDGE[fam]} if fam == "D" else None
        cells[cell] = MS.stage1_cell(cell, books, panels, aff, drt.get(cell))
        r = cells[cell]
        assert r["placebo"]["n"] == MS.STAGE1["placebo_n"] and r["pooled"]["n"] > 0
        assert r["vs_placebo"] == pytest.approx(r["pooled"]["mean"] - r["placebo"]["mean"], abs=2e-4) and r["gross"] is not None
        assert set(r["yen"]) == set(r["judge"]) and all(v["n"] > 0 for v in r["yen"].values())   # ¥/年（只报告）
        assert set(r["gates"]) >= {"G1", "G3", "G4", "G5", "G6", "G8", "G9"} and (fam != "D" or "G7" in r["gates"])
        assert set(r["reference"]) == set(MS.REFERENCE.get(fam, ()))
    c3 = MS.fam_C3(stocks)
    cells["C3"] = MS.stage1_c3(c3, True)
    assert MS.stage1_c3(c3, False)["status"].startswith("作废")
    sigs = {s: _synth_sigs_in(s, 10 + i) for i, s in enumerate(MS.SAMPLES)}
    for c in ("A1", "A3"):
        cells[c] = MS.stage1_A(c, sigs)
        assert cells[c]["pooled"]["n"] > 0 and cells[c]["pooled"]["h1"] is not None and cells[c]["pooled"]["h2"] is not None
    fake = {"cagr": 5.0, "dd": -10.0, "calmar": 0.5, "n": 10}
    a2 = MS.judge_A2(sigs, {"A0": {e: dict(fake) for e in "ZEJ"}, "A2": {e: {**fake, "hits": {}} for e in "ZEJ"}})
    assert a2["account_ok"] and set(a2["account"]) == set("ZEJ")
    bh = MS.apply_bh({c: cells[c].get("p") for c in MS.CELLS})
    for c in MS.CELLS:
        cells[c]["bh"] = bh[c]
        cells[c]["verdict"] = MS.verdict(cells[c], bh)
        assert isinstance(cells[c]["verdict"], str)
    t = sorted(stocks)[1]
    d1l = {**d1, t: _long_daily(d1[t])}
    desc = {"1_etf_momentum": MS.desc_etf_momentum(tab), "2_realism_at": MS.realism_at(d1l, tab, m5, StrategyParams()),
            "3_fill_calib": MS.desc_fill_calib({"5m": m5}, tab), "5_D_overlap_first_touch": MS.desc_D_overlap_first_touch(m5, tab),
            "7_session": MS.desc_session(tab), "8_quality": MS.desc_quality(tab, m5)}
    assert desc["2_realism_at"]["cut13|H1|price"]["days"] > 0 and desc["3_fill_calib"]["5m"]["ticker_days"] > 0
    assert set(desc["7_session"]) == {"H1", "H2"}
    res = {"ran": True, "git_head": "x", "cells": cells, "A2": a2, "A_report": MS.a_report(sigs), "stage2": {}, "desc": desc,
           "mde": MS.cell_mde(panels, MS.run_counts(all_books),                     # 与 do_run 同一个调用（10-15 第一次 --run 在这里崩溃）
                              {"C3": (MS.c3_market_days(tab), int(c3["rows"]["sess"].isin(["H1", "H2"]).sum()))}),
           "align": {"ok": True}, "fingerprint": {"sha": "x"}, "seconds": 1.0}
    MS.out_path("md").parent.mkdir(parents=True, exist_ok=True)
    MS.write_md(res)
    MS.write_json(res)
    md = MS.out_path("md").read_text(encoding="utf-8")
    assert all(f"| {c} |" in md for c in MS.CELLS) and "非投资建议" in md and "¥/年" in md and "随机对照均值" in md
    assert json.loads(MS.out_path("json").read_text(encoding="utf-8"))["ran"] is True


def _toy_ser(P: dict) -> dict:
    g = P["days"]
    n = len(g)
    units = np.zeros(n)
    units[n // 3:] = 100.0
    core = np.linspace(1000, 1100, n)
    hist = pd.DataFrame({"equity": np.full(n, 1_000_000.0), "cash": np.full(n, 600_000.0), "usd": 0.0, "fx": 1.0}, index=g)
    tr = pd.DataFrame({"ticker": [P["names"][0]], "entry_date": [str(g[50].date())], "exit_date": [str(g[60].date())],
                       "entry_px": [1000.0], "exit_px": [1010.0], "shares": [100]})
    return {"base": {}, "hist": hist, "gidx": g, "units": {"1545.T": units}, "core_open": {"1545.T": core}, "core_close": {"1545.T": core},
            "trades": tr}


def test_stage2_overlay_on_toy_account():
    MS.set_mode("run")
    P = MS.synth_panel("Z", n_days=400, n_names=30, seed=3)
    ser = _toy_ser(P)
    busy = MS.b0_busy(ser, P["days"])
    assert P["names"][0] in busy[P["days"][55]]
    assert P["names"][0] in busy[P["days"][50]] and P["names"][0] in busy[P["days"][60]]     # 买入日、卖出日都算
    assert P["names"][0] not in busy.get(P["days"][49], set())                # 信号日不算（B0 的买点收盘后才知道）
    for cell in MS.CELL_SPEC:
        tr = MS.sleeve_trades(P, cell, ser)
        assert tr and all(P["names"][x["j"]] != P["names"][0] or not (50 <= x["i"] <= 60) for x in tr)   # B0 拿着的票分仓不碰
        if MS.CELL_SPEC[cell][0] == "B" and cell.endswith("n"):
            for i in range(len(P["days"])):
                assert sum(1 for x in tr if x["i"] < i <= x["xi"]) <= MS.STAGE2["bn_max_hold"]
        sh = MS.sleeve_trades(P, cell, ser, rng=np.random.default_rng(1), shape=tr)
        assert len(sh) <= len(tr)
        eq = MS.overlay(ser, P, tr)
        assert len(eq) == len(P["days"]) and np.isfinite(eq).all()
        m = MS.era_metrics(eq, "Z")
        assert set(m) >= {"cagr", "dd", "calmar", "h1", "h2"}
    rep = MS.teigaku_report({"Z": ser}, {"Z": P}, {"Z": MS.sleeve_trades(P, "D1", ser)})
    assert rep["Z"]["kobetsu_per_year"] > 0 and rep["Z"]["teigaku_per_year"] >= 0
    # 一笔手算：入场 100、出场 110、一手 ¥100,000、分仓 ¥1,000,000 → 10 手；没拿核心 ETF 的那段 → 机会成本 0
    ser0 = {**ser, "units": {"1545.T": np.zeros(len(P["days"]))}}
    one = [{"i": 10, "xi": 12, "kind": "close0", "slot": 1_000_000.0, "entry": 100.0, "exit": 110.0, "si": 1, "so": 1, "lot_yen": 100_000.0,
            "fam": "B"}]
    eq = MS.overlay(ser0, P, one)
    want = 1_000_000 * (110 * (1 - MS.SLIP) / (100 * (1 + MS.SLIP)) - 1 - 2 * MS.fee_pct(1_000_000))
    assert eq.iloc[12] - 1_000_000 == pytest.approx(want) and eq.iloc[11] == 1_000_000
    assert MS.core_ret(ser, 200, True, 210, False) == pytest.approx(ser["core_close"]["1545.T"][210] / ser["core_open"]["1545.T"][200] - 1)


def test_placebo_matches_candidate_count_and_seed():
    MS.set_mode("run")
    P = MS.synth_panel("Z", n_days=300, n_names=30, seed=5)
    b = MS.cell_book(P, "C1")
    a = MS.placebo([(b["pool"], b["rows"])], 50, [MS.SEED, 3, 6])
    assert len(a) == 50 and np.isfinite(a).all()
    assert np.array_equal(a, MS.placebo([(b["pool"], b["rows"])], 50, [MS.SEED, 3, 6]))      # 同一个种子 → 同一个结果
    assert not np.array_equal(a, MS.placebo([(b["pool"], b["rows"])], 50, [MS.SEED, 3, 7]))


# ── 审查后补的回归测试（前视、口径、--check / --smoke 运行时不算收益） ──
def _c3_row(d, O, nine, ten=None, eleven=None, C=None, sess="H2"):
    bars = {f"{c}{h}": np.nan for h in MS.HOURS for c in "ohlcv"}
    for hh, b in ((9, nine), (10, ten), (11, eleven)):
        if b is not None:
            bars.update({f"o{hh}": b[0], f"h{hh}": b[1], f"l{hh}": b[2], f"c{hh}": b[3], f"v{hh}": 1e5})
    base = {"O": O, "H": 1100.0, "L": 950.0, "C": C or O, "V": 1e6, "sf": 1.0, "ex": False, "pc": O, "lim_hi": O * 1.3,
            "elig": True, "sess": sess}
    return pd.DataFrame([{**base, **bars}], index=pd.DatetimeIndex([pd.Timestamp(d)]))


def test_c3_candidates_do_not_need_the_ten_oclock_bar():
    """10:00 选票时还不知道 10:00 那根有没有：r1 最高的票没有 10:00 那根也要选上（之后的根照常触发）；随机对照的池才要求 10:00 那根。"""
    a = _c3_row("2025-03-03", 1000.0, (1000, 1050, 990, 1045), eleven=(1048, 1060, 1040, 1055), C=1055.0)   # r1 = +4.5%，没有 10:00 那根
    b = _c3_row("2025-03-03", 1000.0, (1000, 1020, 995, 1010), ten=(1010, 1030, 1005, 1025), C=1025.0)      # r1 = +1.0%
    c3 = MS.fam_C3({"9001.T": a, "9002.T": b}, pick=1)
    rows = c3["rows"]
    assert list(rows["ticker"]) == ["9001.T"] and rows["entry"].iloc[0] == 1051 and rows["exit"].iloc[0] == 1055
    (e, x), = [v for v in c3["pool"]["by_day"].values()]
    assert len(e) == 1 and e[0] == 1010                                       # 池里只有 10:00 那根有开盘价的 9002


def test_c2_range_in_todays_units_on_split_day():
    """C2 的「前一天（高 − 低）」换成当天的不复权口径：2:1 拆股当天，前一天还原后的价差 200 円 = 当天口径 100 円。"""
    days = pd.bdate_range("2003-01-06", periods=2)
    O = np.array([[1000.0], [1000.0]])
    H = np.array([[1050.0], [1060.0]])
    L = np.array([[950.0], [990.0]])
    C = np.array([[1000.0], [1000.0]])
    S = np.array([[2.0], [1.0]])                                              # 不复权 = 复权 × S（拆股前是 2 倍）
    ex = np.array([[False], [True]])
    P = MS.build_panel("Z", {"O": O, "H": H, "L": L, "C": C, "V": np.full((2, 1), 1e6)}, days, ["9000.T"], S, np.ones((2, 1)), ex)
    r = MS.fam_C(P, "C2")["rows"]
    assert list(r["entry"]) == [1050.0]                                       # 1,000 + 0.5 × 100；按前一天的口径会是 1,100、不成交


def test_sleeve_size_uses_previous_close_and_b0_buys_first():
    g = pd.bdate_range("2010-01-04", periods=10)
    eq = np.full(10, 1_000_000.0)
    eq[5] = 2_000_000.0
    cash = np.full(10, 600_000.0)
    cash[5] = 450_000.0
    hist = pd.DataFrame({"equity": eq, "cash": cash, "usd": 0.0, "fx": 1.0}, index=g)
    tr = pd.DataFrame({"ticker": ["7203.T"], "entry_date": [str(g[6].date())], "exit_date": [str(g[8].date())],
                       "entry_px": [1000.0], "exit_px": [1000.0], "shares": [100]})
    ser = {"hist": hist, "gidx": g, "units": {"1545.T": np.zeros(10)}, "core_open": {"1545.T": np.full(10, 1000.0)},
           "core_close": {"1545.T": np.full(10, 1000.0)}, "trades": tr}
    buys = MS.b0_buys(ser)
    assert MS.sleeve_size(ser, buys, g[5]) == 250_000                        # 用第 4 天收盘后的账户，不用当天的 2,000,000
    assert MS.sleeve_size(ser, buys, g[6]) == 350_000                        # min(25% × 2,000,000, 450,000 − B0 当天买的 100,000)
    assert MS.sleeve_size(ser, buys, g[0]) == 0.0
    assert MS.sleeve_size(None, {}, g[3]) == 250_000                         # W / Jx：固定 ¥1,000,000 × 25%


def test_stage2_s5_needs_sleeve_trades_on_w_and_jx():
    assert MS.sleeve_s5({"W": {"n": 10, "mean": 0.1}, "Jx": {"n": 5, "mean": 0.2}})
    assert not MS.sleeve_s5({"W": {"n": 0, "mean": None}, "Jx": {"n": 5, "mean": 0.2}})   # 没有交易 ≠ 通过
    assert not MS.sleeve_s5({"W": {"n": 10, "mean": 0.1}})
    assert not MS.sleeve_s5({"W": {"n": 10, "mean": -0.1}, "Jx": {"n": 5, "mean": 0.2}})


def test_a_report_does_not_count_unclosed_as_exits():
    s = pd.DataFrame({"A0_in": [True, True, False], "A0_why": ["stop", "end", None], "A0_gap": [True, False, False],
                      "A0_touch": [False, False, False], "A0_cat": [False, False, False]})
    r = MS.a_report({"Z": s})["A0"]
    assert r["exits"] == 1 and r["gap_through"] == 1 and r["gap_share"] == 1.0


def test_fingerprint_hash_unchanged_but_sums_not_written():
    """指纹的哈希算法不变（冻结清单里的 f68fbefd5409f20c 仍可比），但两个对数收益合计不写出来。"""
    import hashlib
    panels = {"Z": MS.synth_panel("Z", seed=1), "W": MS.synth_panel("W", seed=4)}
    fp = MS.panel_fingerprint(panels)
    assert not any(k.startswith("sum_") for v in fp["samples"].values() for k in v)
    full = {}
    for k, P in panels.items():
        with np.errstate(invalid="ignore", divide="ignore"):
            lr, lo = np.log(P["C"] / MS._prev_row(P["C"])), np.log(P["C"] / P["O"])
        full[k] = {"tickers": len(P["names"]), "days": len(P["days"]), "cells": int(np.isfinite(P["C"]).sum()),
                   "sum_logret": round(float(np.nansum(lr)), 3), "sum_log_oc": round(float(np.nansum(lo)), 3), "eligible": int(P["base"].sum())}
    assert fp["sha"] == hashlib.sha256(json.dumps(full, sort_keys=True).encode()).hexdigest()[:16]
    MS.set_mode("check")
    MS.strip_returns(fp)                                                      # 不含收益字段
    with pytest.raises(MS.ReturnGuardError):
        MS.strip_returns({"samples": {"Z": {"sum_log_oc": 1.0}}})


def _forbid(monkeypatch, names):
    for name in names:
        def boom(*a, _n=name, **k):
            raise AssertionError(f"--check / --smoke 调用了 {_n}")
        monkeypatch.setattr(MS, name, boom)


def test_smoke_never_calls_return_functions_at_runtime(tmp_path, monkeypatch):
    """运行时再查一遍（源码检查之外）：把所有算收益的函数换成一调用就报错的，--smoke 照样跑完。"""
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    _forbid(monkeypatch, GATED)
    assert MS.do_smoke() == 0


def test_check_never_calls_return_functions_at_runtime(tmp_path, monkeypatch):
    """--check 全流程（读缓存、LC.load、日线宽表、A 逐信号、条数 / MDE）用合成数据跑一遍：算收益的函数与 B0 回测一次也不调用，
    写进冻结清单的只有条数与哈希。"""
    import loop_common as LC
    _freeze(tmp_path, monkeypatch)
    _forbid(monkeypatch, GATED + ["sleeve_trades", "b0_busy"])
    p = StrategyParams(stop_loss_pct=7.0, trailing_stop_pct=12.0, take_profit_pct=25.0, exit_chandelier_k=3.0, exit_on_climax=True,
                       climax_min_gain_pct=5.0, max_hold_days=60, exit_on_macd_dead_cross=False)
    W = {"px": p}
    monkeypatch.setattr(LC, "load", lambda *a, **k: W)
    monkeypatch.setattr(LC, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("--check 跑了 B0 的回测")))
    panels = {s: MS.synth_panel(s, n_days=500, n_names=30, seed=i + 1, member=(s == "Jx")) for i, s in enumerate(MS.SAMPLES)}
    monkeypatch.setattr(MS, "load_t2", lambda man: MS.synth_t2(n_names=10, n_days=40))
    monkeypatch.setattr(MS, "daily_panels", lambda W_: panels)
    monkeypatch.setattr(MS, "fam_A_signal", lambda *a, **k: {s: _synth_sigs_in(s, 20 + i) for i, s in enumerate(MS.SAMPLES)})
    monkeypatch.setattr(MS, "check_vs_engine", lambda *a, **k: {"ok": True})
    assert MS.do_check() == 0
    txt = MS.freeze_path().read_text(encoding="utf-8")
    man = json.loads(txt)
    assert man["daily_fingerprint"]["sha"] and "sum_log" not in txt
    assert any("MDE" in x for x in MS.LINES) and not (tmp_path / "out" / "minute_study.json").exists()
