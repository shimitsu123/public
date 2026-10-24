"""qbreak/gate_forward.py + scripts/w2_forward_all.py 第十节（HWN / X2G / JRM 的前向检验，2026-10-05 登记）：
三个闸门与第十个循环登记、运行过的函数完全相同；统计、判定（每年一次、样本不够不判定）、只用登记之后的成熟配对。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r01_weakvote as R1W                                            # noqa: E402
import loop10_r02_diagfeat as R2                                             # noqa: E402
import loop10_r07_final as R7                                                # noqa: E402
import loop9_r01_market as L9                                                # noqa: E402
import w2_forward_all as WFA                                                 # noqa: E402

from qbreak import gate_forward as GF                                        # noqa: E402


def test_registered_constants():
    assert GF.IDS == ("HWN", "X2G", "JRM") and GF.FORWARD_START == "2026-10-06"
    assert GF.HWN_MONTHS == R7.HWN_MONTHS == (5, 6, 7, 8, 9, 10)
    assert (GF.JRM_N, GF.JRM_GAP) == (R1W.REL_N, R1W.REL_GAP) == (60, -0.10)
    assert GF.X2G_CUT == 0.0 and GF.CORE_TICKER == "1545.T" and GF.CORE_JUMP == 0.30
    assert GF.JUDGE_DATES == WFA.JUDGE_DATES and (GF.BOOT_N, GF.SEED) == (2000, 20261005) and (GF.MIN_N, GF.MIN_MONTHS) == (10, 3)


def test_hwn_same_as_loop10():
    d = pd.to_datetime(["2026-10-06", "2026-10-30", "2026-11-02", "2027-04-30", "2027-05-06", "2027-12-01"])
    assert GF.hwn_flag(d).tolist() == R7.season_gate(d).astype(int).tolist() == [1, 1, 0, 0, 1, 0]


def test_x2g_same_as_loop10_feature_gate():
    x = np.array([-0.5, 0.0, 1e-9, 2.0, np.nan, -1e-9])
    want = R2.feature_gate(pd.DataFrame({"x2": x}), ("x2", "<=", 0.0)).astype(int)
    assert GF.x2g_flag(x).tolist() == want.tolist() == [1, 1, 0, 0, 0, 1]           # 缺值不挡


def test_jrm_same_as_loop10_rel_gap_days():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2020-01-01", periods=400)
    jp = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.015, len(days)))), index=days)
    cdays = days.delete([5, 77, 200]).union(pd.DatetimeIndex(["2020-03-07"]))          # 核心的日子与日経不完全一样
    core = pd.Series(np.exp(np.cumsum(rng.normal(0.001, 0.012, len(cdays)))), index=cdays)
    got, want = GF.jrm_days(jp, core), R1W.rel_gap_days(jp, core)
    assert got.index.equals(want.index) and (got == want).all() and got.any() and not got.iloc[:60].any()
    sig = pd.to_datetime(["2019-12-31", "2020-06-06", "2020-09-15", "2021-05-03"])     # 最开头之前 / 周六 / 平日 / 数据之后
    assert GF.jrm_flag(sig, got).tolist() == L9.on_days(got, pd.DatetimeIndex(sig)).astype(int).tolist()


def test_clean_core_neutralizes_unadjusted_split_and_spike():
    c = pd.Series([100.0, 101.0, 1.01, 1.0302, 1.01], index=pd.bdate_range("2026-07-01", periods=5))   # 1:100 没调整的分割
    out = GF.clean_core(c)
    assert len(out) == 5 and np.allclose(out.to_numpy(), [100.0, 101.0, 101.0, 103.02, 101.0])
    s = pd.Series([100.0, 250.0, 101.0, 102.0], index=pd.bdate_range("2026-07-01", periods=4))         # 一天的错价
    assert np.allclose(GF.clean_core(s).to_numpy(), [100.0, 100.0, 100.0, 100.0 * 102 / 101])
    c2 = pd.Series([100.0, 101.0, 99.0, 102.0], index=pd.bdate_range("2026-07-01", periods=4))
    assert np.allclose(GF.clean_core(c2).to_numpy(), c2.to_numpy())             # 正常的不动


def _frame(n_months=6, per=8, seed=1, block_bad=True):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_months):
        d0 = pd.Timestamp("2026-11-02") + pd.DateOffset(months=m)
        for i in range(per):
            g = int(i % 2)                                                     # 每个月两组都有
            net = rng.normal(-1.5 if (g and block_bad) else 1.5, 1.0)
            rows.append({"sig_date": d0 + pd.Timedelta(days=i), "g_x2g": g, "net_x6": net})
    return pd.DataFrame(rows)


def test_evaluate_confirm_refute_insufficient():
    U = _frame()
    ev = GF.evaluate(U, "g_x2g")
    assert ev["enough"] and ev["dwin"] > 50 and ev["dwin_lo99"] > 0 and ev["dmean"] > 0
    assert GF.verdict(ev) == "confirmed" and not GF.refuted(ev)
    ev2 = GF.evaluate(U.assign(g_x2g=1 - U["g_x2g"]), "g_x2g")                 # 反过来：挡掉的更好
    assert GF.verdict(ev2) == "refuted"
    ev3 = GF.evaluate(U.iloc[:12], "g_x2g")                                    # 两个月、每组 6 笔
    assert not ev3["enough"] and GF.verdict(ev3) == "insufficient" and not GF.confirmed(ev3)
    ev4 = GF.evaluate(U.assign(g_x2g=np.nan), "g_x2g")                         # 标记全是缺值 → 不算
    assert ev4["n"] == 0 and ev4["missing"] == len(U) and GF.verdict(ev4) == "insufficient"


def test_confirm_needs_mean_not_lower():
    ev = {"enough": True, "dwin_lo99": 1.0, "dwin_hi95": 9.0, "dmean": -0.01, "dmean_hi95": 1.0}
    assert not GF.confirmed(ev) and not GF.refuted(ev) and GF.verdict(ev) == "undecided"
    assert GF.refuted({**ev, "dmean_hi95": -0.1})


def test_review_judges_once_per_year():
    U = _frame().rename(columns={"g_x2g": "g_hwn"})
    U["g_x2g"], U["g_jrm"] = U["g_hwn"], np.nan
    r0 = GF.review(U, None, "2027-06-30")
    assert all(r0[k]["year"] is None for k in GF.IDS)
    r1 = GF.review(U, None, "2027-10-15")
    assert r1["HWN"]["year"] == "2027-09-28" and r1["HWN"]["verdict"] == "confirmed" and r1["JRM"]["verdict"] == "insufficient"
    hist = pd.DataFrame(GF.history_rows(r1, "2027-10-15"))
    assert set(hist["scope"]) == {"all_G10_HWN", "all_G10_X2G", "all_G10_JRM"}
    r2 = GF.review(U, hist, "2028-01-15")
    assert all(r2[k]["year"] is None for k in GF.IDS)                         # 做过的年份不再做
    assert any("只报告进度" in x for x in GF.verdict_lines(r2, today="2028-01-15"))


def test_gate_frame_only_after_registration_and_mature(tmp_path):
    PX = pd.DataFrame({"ticker": ["1111.T", "2222.T", "3333.T", "4444.T", "5555.T"],
                       "sig_date": pd.to_datetime(["2026-10-05", "2026-10-06", "2026-11-04", "2027-05-10", "2027-06-01"]),
                       "w2_keep": [1, 1, 0, 1, 1], "main": [True, True, True, True, False],
                       "status": ["ok", "ok", "ok", "ok", "open"], "mature": [True, True, True, True, True],
                       "net_x6": [1.0, -2.0, 3.0, 0.5, 9.0], "net_cur": [0.0] * 5})
    days = pd.bdate_range("2026-01-01", "2027-07-01")
    n225 = pd.Series(100 * 1.0005 ** np.arange(len(days)), index=days)
    core = pd.Series(100 * 1.003 ** np.arange(len(days)), index=days)         # 核心每 60 天多涨约 17 pp → 日経落后 ≥ 10 pp
    note = []
    G = WFA.gate_frame(PX, lambda tk, ds: np.array([-0.1, 0.2, np.nan]), n225, core, note)
    assert G["ticker"].tolist() == ["2222.T", "3333.T", "4444.T"]             # 10-05 之前的、没平仓的不算
    assert G["g_hwn"].tolist() == [1, 0, 1] and G["g_x2g"].tolist() == [1, 0, 0] and G["g_jrm"].tolist() == [1, 1, 1]
    assert not note
    G2 = WFA.gate_frame(PX, lambda tk, ds: (_ for _ in ()).throw(RuntimeError("BOJ down")), None, None, note)
    assert G2["g_x2g"].isna().all() and G2["g_jrm"].isna().all() and G2["g_hwn"].notna().all()
    assert any("X2G 这次算不了" in x for x in note)
    out = WFA.gate_eval(G, None, "2026-12-01", {"2222.T"})
    assert out["main"]["HWN"]["eval"]["n"] == 2 and out["n_usable"] == 3      # 主 = 主对象 ∧ W2 保留
    assert set(out["side"]) == {"主对象里的日経225 股票池（W2 保留）", "不限成交额（W2 保留）", "主对象里不管 W2 的全部"}
    empty = WFA.gate_eval(WFA.gate_frame(None, lambda tk, ds: None, None, None), None, "2027-10-01", set())
    assert empty["main"]["X2G"]["verdict"] == "insufficient" and empty["n_usable"] == 0


def test_calib_years_needed():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import gate_forward_calib as GC
    y = GC.years_needed(se=2.0, n_ref=900, per_year=450, effect=GC.Z_SUM * 2.0)  # 已经够 → 2 年的量 = 900 笔
    assert abs(y - 2.0) < 1e-9
    assert np.isnan(GC.years_needed(float("nan"), 100, 450, 4.0))
