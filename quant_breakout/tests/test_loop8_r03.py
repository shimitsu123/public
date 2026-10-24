"""第八个研究循环第 3 轮 MLV（scripts/loop8_r03_margin.py，2026-10-04 登记）：登记的常数与判定的接线、FINRA / JPX 表的解析、
美国滞后一个月 / 日本滞后 14 天（不偷看）、只用之前 60 个的 z 值、月度比例只在月末之后变、第二关的平移量。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop8_r03_margin as V  # noqa: E402
import research_loop8 as L8  # noqa: E402


def test_registered_constants_and_judgment():
    assert (V.ROUND, V.IDS, V.FAMILY, V.POSTHOC, V.Z_WIN, V.Z_ON, V.US_LAG_MONTHS, V.JP_LAG_DAYS) == (3, ("MLV",), "杠杆·融资余额", False, 60, 1.0, 1, 14)
    assert V.KEEP == pytest.approx(2 / 3) and V.FAMILY in L8.SOURCES and tuple(V.MARKETS) == ("US", "JP")
    assert (V.POST, V.H_SHORT, V.SEED_INFO, V.SEED_S2, V.PLACEBO_N, V.SHIFT_GAP) == ("2017-01-01", 21, 20261013, 20261014, 400, 250)
    ra, ic, s1, s2 = (inspect.getsource(f) for f in (V.run_all, V.info_check, V.stage_one, V.stage_two))
    assert "RL8.info_judge(ics, post, boot, sign=-1)" in ic and "RL8.joint_bootstrap(S, seed=SEED_INFO)" in ic
    assert "if not A[\"judge\"][\"ok\"]:" in ra and "RL8.FAIL_INFO" in ra and "if a[\"ok\"]:" in ra and "R7.FOUND if b[\"stage2\"][\"ok\"] else R7.FAIL2" in ra
    assert "R6.stage1(cand, base, posthoc=None)" in s1 and "P2.vtx_over(M[\"ratio_t\"])" in s1
    assert "RL.stage2(stat, vals)" in s2 and "shift_ks(n)" in s2


def test_parse_finra_and_jpx():
    df = pd.DataFrame({"Year-Month": ["2026-08", "2026-07", "1997-01"], "Debit": [1453832, 1417225, 103337],
                       "CashCredit": [207641, 205132, 68856], "MarginCredit": [217499, 217305, np.nan]})
    f = V.parse_finra_df(df)
    assert list(f.index) == [pd.Timestamp("1997-01-31"), pd.Timestamp("2026-07-31"), pd.Timestamp("2026-08-31")]
    assert f["debit"].iloc[-1] == 1453832 and np.isnan(f["credit_margin"].iloc[0])
    raw = pd.DataFrame([["信用取引現在高"] + [None] * 12, [None] * 13, [None] * 13, ["月日", "委託"] + [None] * 11,
                        [pd.Timestamp("2002-08-02"), 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 1568928 + 100],
                        [pd.Timestamp("2002-08-09"), 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 1512872],
                        [pd.Timestamp("2002-08-09"), 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 1512999],     # 重复的日期 → 留最后一个
                        ["注:"] + [None] * 12])
    j = V.parse_jpx_df(raw)
    assert list(j.index) == [pd.Timestamp("2002-08-02"), pd.Timestamp("2002-08-09")] and j.iloc[1] == 1512999


def test_levels_use_only_published_data():
    idx = pd.bdate_range("2024-01-01", "2024-04-30")
    close = pd.Series(np.linspace(100, 110, len(idx)), index=idx)
    debit = pd.Series([1000.0, 2000.0, 3000.0], index=pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31"]))
    t = pd.DatetimeIndex([pd.Timestamp("2024-03-29")])
    lv = V.level_us(debit, close, t)
    assert lv.iloc[0] == pytest.approx(np.log(2000.0) - np.log(close.loc["2024-02-29"]))   # 3 月末只用 2 月的余额（4 月中旬才公布 3 月的）
    buy = pd.Series([10.0, 20.0, 30.0], index=pd.to_datetime(["2024-03-08", "2024-03-15", "2024-03-22"]))
    lj = V.level_jp(buy, close, t)
    assert lj.iloc[0] == pytest.approx(np.log(20.0) - np.log(close.loc["2024-03-15"]))      # 3-29 − 14 天 = 3-15（含）
    assert np.isnan(V.level_jp(buy, close, pd.DatetimeIndex([pd.Timestamp("2024-03-15")])).iloc[0])


def test_zscore_uses_previous_window_only():
    lv = pd.Series(np.arange(80, dtype=float), index=pd.date_range("2000-01-31", periods=80, freq="ME"))
    lv.iloc[70] = np.nan
    z = V.zscore_prev(lv)
    assert z.iloc[:60].isna().all() and np.isnan(z.iloc[70])
    h = np.arange(0, 60, dtype=float)
    assert z.iloc[60] == pytest.approx((60 - h.mean()) / h.std(ddof=1))
    h2 = np.r_[np.arange(12, 70), np.arange(71, 73)].astype(float)                           # 第 73 个之前有值的最近 60 个（第 70 个空 → 跳过）
    assert z.iloc[73] == pytest.approx((73 - h2.mean()) / h2.std(ddof=1))


def test_ratio_changes_only_after_month_ends():
    idx = pd.bdate_range("2024-01-01", "2024-04-10")
    c = pd.Series(100.0, index=idx)
    me = L8.month_ends_done(c)
    x = pd.Series([1.5, np.nan], index=me[:2])
    r = V.ratio_mlv(c, x)
    assert (r[r.index < me[0]] == 1.0).all() and np.allclose(r[(r.index >= me[0]) & (r.index < me[1])], 2 / 3)
    assert (r[r.index >= me[1]] == 1.0).all() and r.index.equals(c.index)
    x2 = pd.Series([0.99, 1.0], index=me[:2])
    r2 = V.ratio_mlv(c, x2)
    assert r2.loc[me[0]] == 1.0 and r2.loc[me[1]] == pytest.approx(2 / 3)


def test_samples_and_shift_ks():
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    c = pd.Series(np.exp(np.arange(len(idx)) * 0.001), index=idx)
    x = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    s = V.samples(c, x, h=21)
    assert s.index.isin(L8.month_ends_done(c)).all() and np.allclose(s["y"], 0.021)
    ks = V.shift_ks(6000)
    assert len(ks) == 400 and min(ks) >= 250 and max(ks) <= 5750 and ks == V.shift_ks(6000)
    with pytest.raises(ValueError):
        V.shift_ks(500)
