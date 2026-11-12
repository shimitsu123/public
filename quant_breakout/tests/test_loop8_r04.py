"""第八个研究循环第 4 轮 FFL（scripts/loop8_r04_foreign.py，2026-10-04 登记）：登记的常数与判定的接线、周度数据只用已公布的（PubDate ≤ 决定日）、
13 周的净买入占比、月度「被挡」只在月末之后变且 2017 年以前不挡、第二关的平移（窗外不动、天数不变）。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop8_r04_foreign as V  # noqa: E402
import research_loop8 as L8  # noqa: E402


def test_registered_constants_and_judgment():
    assert (V.ROUND, V.IDS, V.FAMILY, V.POSTHOC, V.WEEKS, V.SECTION) == (4, ("FFL",), "资金流·投资部门别", False, 13, "TokyoNagoya")
    assert V.FAMILY in L8.SOURCES and (V.GATE_FROM, V.SHIFT_FROM, V.SEED_INFO, V.SEED_S2, V.PLACEBO_N, V.SHIFT_GAP) == (
        "2017-01-01", "2017-01-01", 20261015, 20261016, 400, 250)
    ra, ic, s1, s2 = (inspect.getsource(f) for f in (V.run_all, V.info_check, V.stage_one, V.stage_two))
    assert "RL8.info_judge({\"JP\": ic}, {\"JP\": ic}, boot, sign=+1, halves=h)" in ic and "seed=SEED_INFO" in ic
    assert "if not A[\"judge\"][\"ok\"]:" in ra and "RL8.FAIL_INFO" in ra and "R7.FOUND if b[\"stage2\"][\"ok\"] else R7.FAIL2" in ra
    assert "R6.stage1(cand, base, trade=os_, posthoc=None)" in s1 and "G12.other_stocks(W, flags)" in s1
    assert "RL.stage2(stat, vals)" in s2 and "shift_ks(n)" in s2


def _raw():
    rows = []
    ends = pd.date_range("2016-10-07", periods=20, freq="W-FRI")
    for i, e in enumerate(ends):
        pub = e + pd.Timedelta(days=6)
        rows.append({"PubDate": str(pub.date()), "StDate": str((e - pd.Timedelta(days=4)).date()), "EnDate": str(e.date()),
                     "Section": "TokyoNagoya", "FrgnBal": float(i + 1), "TotTot": 100.0, "IndBal": -1.0, "TrstBnkBal": 0.0})
        rows.append({"PubDate": str(pub.date()), "StDate": "x", "EnDate": str(e.date()), "Section": "TSE1st", "FrgnBal": 999.0,
                     "TotTot": 1.0, "IndBal": 0.0, "TrstBnkBal": 0.0})
    rows.append({**rows[0], "PubDate": str((ends[0] + pd.Timedelta(days=13)).date()), "FrgnBal": 2.0})   # 同一周的更正 → 留最后公布的
    return pd.DataFrame(rows), ends


def test_weekly_and_flow_share_use_only_published_weeks():
    raw, ends = _raw()
    w = V.weekly(raw)
    assert len(w) == 21 and (w["tot"] == 100.0).all()                          # 第 1 周的原版与更正版都留着
    t = ends[12] + pd.Timedelta(days=6)                                          # 第 13 周公布的那天
    fx = V.flow_share(w, pd.DatetimeIndex([t, t - pd.Timedelta(days=1)]))
    assert fx.iloc[0] == pytest.approx((2.0 + sum(range(2, 14))) / 1300.0)     # 最近 13 周（第 1 周用 t 以前公布的更正版 2）
    assert np.isnan(fx.iloc[1])                                                 # 前一天第 13 周还没公布 → 不够 13 周
    t0 = ends[0] + pd.Timedelta(days=6)
    assert np.isnan(V.flow_share(w, pd.DatetimeIndex([t0])).iloc[0])           # 只有 1 周 → 空
    early = V.flow_share(w.assign(tot=1.0), pd.DatetimeIndex([ends[12] + pd.Timedelta(days=6)]), weeks=1)
    assert early.iloc[0] == pytest.approx(13.0)
    first = w[w["end"] == ends[0]].sort_values("pub")
    assert first["net"].tolist() == [1.0, 2.0]                                  # 原版 1、更正 2
    t_mid = ends[0] + pd.Timedelta(days=8)                                       # 更正公布之前 → 用原版
    x = V.flow_share(w.assign(tot=1.0), pd.DatetimeIndex([t_mid]), weeks=1)
    assert x.iloc[0] == pytest.approx(1.0)                                      # 更正版 t 以后才公布 → 用原版 1（不偷看）


def test_gate_flags_monthly_and_from_2017():
    idx = pd.bdate_range("2016-11-01", "2017-04-10")
    c = pd.Series(100.0, index=idx)
    me = L8.month_ends_done(c)
    fx = pd.Series([-0.01, -0.02, 0.01, np.nan, -0.03], index=me[:5])
    g = V.gate_flags(c, fx)
    assert not g[g.index < pd.Timestamp("2017-01-01")].any()                   # 2016-11 / 12 月末是负的，但 2017 年以前不挡
    jan = g[(g.index >= "2017-01-01") & (g.index < me[2])]
    assert jan.all()                                                            # 2016-12 月末 −0.02 → 2017-01 挡
    feb = g[(g.index >= me[2]) & (g.index < me[3])]
    assert not feb.any()                                                        # 2017-01 月末 +0.01 → 不挡
    assert not g[(g.index >= me[3]) & (g.index < me[4])].any()                  # 空 → 不挡
    assert g.loc[me[4]] and g.index.equals(c.index)


def test_shifted_keeps_count_and_outside_window():
    idx = pd.bdate_range("2015-01-01", "2026-09-30")
    f = pd.Series((np.arange(len(idx)) // 30) % 3 == 0, index=idx)
    s = V.shifted(f, 77, "2017-01-01", "2026-09-30")
    win = (idx >= pd.Timestamp("2017-01-01"))
    assert int(s[win].sum()) == int(f[win].sum()) and s[~win].equals(f[~win]) and not s[win].equals(f[win])
    assert V.shifted(f, None).equals(f)
    ks = V.shift_ks(2400)
    assert len(ks) == 400 and min(ks) >= 250 and max(ks) <= 2150 and ks == V.shift_ks(2400)
    with pytest.raises(ValueError):
        V.shift_ks(500)


def test_halves_ic():
    idx = pd.date_range("2017-01-31", periods=100, freq="ME")
    x = np.arange(100, dtype=float)
    s = pd.DataFrame({"x": x, "y": np.r_[x[:50], -x[50:]]}, index=idx)
    h1, h2 = V.halves_ic(s)
    assert h1 == pytest.approx(1.0) and h2 == pytest.approx(-1.0)
