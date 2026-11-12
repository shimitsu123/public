"""去掉每只 25% 上限、资金自由分配（scripts/free_alloc_study.py 登记检验）：信号与每天的候选数、σ 只用到当天、f 的规则（候选数 / 波动 / 半凯利 / 混合）、
凯利只用过去 36 个月已平仓的笔、em_tick 覆盖每一个信号、安慰剂与上限的映射、资金占用、判定与「收益率优先」读法、
研究引擎里「position_pct = 1.0 + em_tick 0.25」与现行「position_pct = 0.25」买到同样的股数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import free_alloc_study as FA                                                # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.strategy import compute_indicators                              # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}


def _fr(n=120, seed=0, start="2024-01-04", entries=()):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    c = 1000.0 * np.cumprod(1 + rng.normal(0, 0.01, n))
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)
    df["entry"] = False
    for i in entries:
        df.iloc[i, df.columns.get_loc("entry")] = True
    return df


def test_signals_and_k_per_day():
    fr = {"A.T": _fr(entries=(30, 50)), "B.T": _fr(seed=1, entries=(30,)), "C.T": _fr(seed=2)}
    sigs, k = FA.signals(fr)
    d30, d50 = fr["A.T"].index[30], fr["A.T"].index[50]
    assert len(sigs) == 3 and k[d30] == 2 and k[d50] == 1
    assert FA.f_count(1) == 1.0 and FA.f_count(2) == 0.5 and abs(FA.f_count(3) - 1 / 3) < 1e-9 and FA.f_count(7) == 1 / 7


def test_sigma_uses_only_past_and_f_rules_clip():
    df = _fr(n=60)
    s = FA.sigma_ann(df)
    assert np.isnan(s.iloc[10]) and np.isfinite(s.iloc[-1])
    df2 = df.copy()
    df2.iloc[-1, df2.columns.get_loc("Close")] *= 1.5                                       # 改最后一天 → 之前的 σ 不变
    assert abs(FA.sigma_ann(df2).iloc[-2] - s.iloc[-2]) < 1e-12 and FA.sigma_ann(df2).iloc[-1] != s.iloc[-1]
    assert abs(FA.f_vol(0.30) - 0.25) < 1e-9 and abs(FA.f_vol(0.15) - 0.5) < 1e-9
    assert FA.f_vol(0.05) == FA.F2_HI and FA.f_vol(2.0) == FA.F2_LO and FA.f_vol(np.nan) == FA.F_NOW and FA.f_vol(0.0) == FA.F_NOW
    assert abs(FA.f_hybrid(1, 0.30) - 1.0) < 1e-9 and abs(FA.f_hybrid(2, 0.30) - 0.5) < 1e-9 and abs(FA.f_hybrid(2, 0.15) - 1.0) < 1e-9
    assert FA.f_hybrid(4, 2.0) == FA.F4_LO and abs(FA.f_hybrid(3, np.nan) - 1 / 3) < 1e-9


def test_kelly_formula_and_walk_forward_window():
    p, b, f = FA.kelly_f([10, 10, -5, -5])                                                     # p 0.5、b 2 → 凯利 0.25 → 半凯利 0.125
    assert abs(p - 0.5) < 1e-9 and abs(b - 2.0) < 1e-9 and abs(f - 0.125) < 1e-9
    assert FA.kelly_f([-1, -2])[2] == FA.KELLY_LO and FA.kelly_f([5, 6])[2] == 0.5              # 全亏 → 下限；全赚 → 凯利 1 的一半
    assert FA.kelly_f([1, -3])[2] == FA.KELLY_LO                                                # 负凯利 → 下限
    rows = []
    for i in range(40):
        d = pd.Timestamp("2020-01-15") + pd.DateOffset(months=i)
        rows.append({"ticker": "A.T", "entry_date": str(d.date()), "exit_date": str((d + pd.Timedelta(days=10)).date()),
                     "shares": 100, "entry_px": 100.0, "pnl": 1000.0 if i % 2 == 0 else -500.0})
    tr = pd.DataFrame(rows)
    km = FA.kelly_by_month(tr, "2020-01-01", "2023-12-31")
    m0 = FA.mon("2020-06-01")
    assert km[m0]["f"] == FA.KELLY_DEFAULT and km[m0]["n"] < FA.KELLY_MIN                        # 头几个月不满 30 笔 → 25%
    m1 = FA.mon("2023-06-01")
    x = km[m1]
    assert x["n"] >= FA.KELLY_MIN and 0.45 < x["p"] < 0.55 and abs(x["b"] - 2.0) < 1e-9                  # 窗口里 35 笔：17 赚 / 18 亏
    assert abs(x["f"] - 0.5 * (17 / 35 - (18 / 35) / 2.0)) < 1e-9                                # p 用精确值算（记录的 p 是 3 位小数）
    # 窗口只用 exit_date < 月初的笔：把 2023-05 之后的都改成大亏，2023-06 的 f 不变
    tr2 = tr.copy()
    late = pd.to_datetime(tr2["exit_date"]) >= pd.Timestamp("2023-06-01")
    tr2.loc[late, "pnl"] = -9000.0
    assert abs(FA.kelly_by_month(tr2, "2020-01-01", "2023-12-31")[m1]["f"] - km[m1]["f"]) < 1e-12
    assert FA.kelly_by_month(tr.iloc[:0], "2020-01-01", "2020-03-31")[FA.mon("2020-02-01")]["f"] == FA.KELLY_DEFAULT


def test_em_tick_covers_every_signal_and_maps_placebo_oracle():
    fr = {"A.T": _fr(entries=(30, 50)), "B.T": _fr(seed=1, entries=(30,))}
    sigs, k = FA.signals(fr)
    days = fr["A.T"].index
    sig = {t: FA.sigma_ann(df) for t, df in fr.items()}
    for kind in ("F0", "F1", "F2", "F4", "F5"):
        em = FA.em_tick_for(kind, sigs, k, sig, days)
        assert set(em) == {(t, str(d.date())) for t, d in sigs} and all(0 < v <= 1 for v in em.values())
    em1 = FA.em_tick_for("F1", sigs, k, sig, days)
    d30, d50 = str(days[30].date()), str(days[50].date())
    assert em1[("A.T", d30)] == 0.5 and em1[("B.T", d30)] == 0.5 and em1[("A.T", d50)] == 1.0
    assert all(v == 0.25 for v in FA.em_tick_for("F0", sigs, k, sig, days).values())
    assert all(v == 1.0 for v in FA.em_tick_for("F5", sigs, k, sig, days).values())
    kel = {FA.mon(days[30]): {"f": 0.11}, FA.mon(days[50]): {"f": 0.07}}
    em3 = FA.em_tick_for("F3", sigs, k, sig, days, kelly=kel)
    assert em3[("A.T", d30)] == 0.11 and em3[("A.T", d50)] == 0.07
    pa, pb = FA.em_tick_for("placebo", sigs, k, sig, days, seed=1), FA.em_tick_for("placebo", sigs, k, sig, days, seed=1)
    assert pa == pb and all(v in FA.PLACEBO_CHOICES for v in pa.values())
    fill30 = str(days[31].date())
    outc = {("A.T", fill30): True, ("B.T", fill30): False}
    eo = FA.em_tick_for("oracle", sigs, k, sig, days, outcome=outc)
    assert eo[("A.T", d30)] == FA.ORACLE_WIN and eo[("B.T", d30)] == FA.ORACLE_LOSE and eo[("A.T", d50)] == FA.ORACLE_NA
    assert FA.next_day(days, days[-1]) is None and FA.next_day(days, days[3]) == str(days[4].date())


def test_occupancy_and_verdicts():
    hist = [[str(d.date()), 1_000_000.0, 0, 0, 150.0] for d in pd.bdate_range("2024-01-04", periods=10)]
    tr = pd.DataFrame([{"ticker": "A.T", "entry_date": "2024-01-08", "exit_date": "2024-01-12", "shares": 100, "entry_px": 2500.0, "pnl": 0.0}])
    occ = FA.occupancy(tr, hist, "2024-01-04", "2024-01-17")                                    # 4 天持有 25 万 / 100 万 → 平均 10%
    assert abs(occ - 10.0) < 1e-6
    a0 = {"Z": {"calmar": 1.7, "cagr": 13.0, "dd": -7.5, "n": 37}, "E": {"calmar": 0.32, "cagr": 8.8, "dd": -27.5, "n": 65},
          "J": {"calmar": 0.40, "cagr": 14.0, "dd": -35.0, "n": 85}}
    ok = {"Z": {"calmar": 1.69, "cagr": 12.5, "dd": -7.5, "n": 37}, "E": {"calmar": 0.35, "cagr": 11.0, "dd": -28.0, "n": 60},
          "J": {"calmar": 0.45, "cagr": 17.0, "dd": -36.0, "n": 80}}
    assert FA.verdict(ok, a0, 0.44) == ("通过", []) and FA.ret_verdict(ok, a0) == ("收益率优先通过", [])
    bad = {**ok, "E": {"calmar": 0.33, "cagr": 9.5, "dd": -33.0, "n": 25}}
    lab, fails = FA.verdict(bad, a0, 0.46)
    assert lab == "不通过" and any(f.startswith("a E Calmar") for f in fails) and any("深 2 pp" in f for f in fails) and any(f.startswith("c E") for f in fails)
    assert any(f.startswith("b J") for f in fails)
    rl, rf = FA.ret_verdict(bad, a0)
    assert rl == "收益率优先不通过" and any("E 年化" in f for f in rf) and any("深 5 pp" in f for f in rf)
    assert FA.f_summary({("a", "d"): 0.5, ("b", "d"): 1.0})["median"] == 0.75 and FA.f_summary({}) == {"n": 0}


def test_engine_full_budget_with_em_tick_quarter_equals_current_sizing():
    """研究引擎：position_pct = 1.0 + 那个信号的 em_tick 0.25 → 与现行 position_pct = 0.25 买到同样的股数；em_tick 1.0 → 买到约 4 倍。"""
    rng = np.random.default_rng(5)
    n = 260
    idx = pd.bdate_range("2021-01-04", periods=n)
    c = 3000.0 * np.cumprod(1 + rng.normal(0.0002, 0.008, n))
    raw = pd.DataFrame({"Open": c, "High": c * 1.005, "Low": c * 0.995, "Close": c, "Volume": 1e6}, index=idx)
    ind = compute_indicators(raw, StrategyParams())
    ind["entry"] = False
    day = idx[120]
    ind.loc[day, "entry"] = True
    ind["dead_cross"] = False
    pp = StrategyParams(max_distribution_days=6, max_upper_shadow_ratio=3.0, exit_on_macd_dead_cross=False, exit_chandelier_k=3.0)

    def run(cfg, em):
        eng = CP.MixEngine({"A.T": ind}, cfg, {"JP": pp, "US": pp}, EX, {}, entry_mult=({"JP": em} if em is not None else None))
        eng.run(start=idx[100])
        tr = [t for t in eng.st.trades if t["ticker"] == "A.T"]
        return tr[0]["shares"] if tr else 0
    base = UnifiedConfig(capital_jpy=10_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34, stock_markets=("JP",), core={}, core_index={})
    free = UnifiedConfig(capital_jpy=10_000_000, position_pct=1.0, max_positions=4, max_position_pct=1.0, stock_markets=("JP",), core={}, core_index={})
    em25 = pd.DataFrame(1.0, index=idx, columns=["A.T"])
    em25.iloc[121, 0] = 0.25                                                                    # 成交日 = 信号日的下一个交易日
    s_base, s_free25, s_free100 = run(base, None), run(free, em25), run(free, pd.DataFrame(1.0, index=idx, columns=["A.T"]))
    assert s_base > 0 and s_free25 == s_base
    assert s_free100 >= 3.5 * s_base                                                            # 去掉上限后一只票可以到权益的 100%（一手取整）
