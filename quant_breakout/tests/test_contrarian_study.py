"""越危险越加仓、越利好越出货（scripts/contrarian_study.py 登记检验）：深跌分数、自身历史百分位只用过去、政策日粒度映射、综合分数跳过缺值、
仓位映射（反向 / 正向 / 缺值中性 / 范围）、窗口内循环平移、作弊分数用未来、成交日生效、五分位表、编码与判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import contrarian_study as CT                                                # noqa: E402
import core_switch_study as CS                                               # noqa: E402


def test_constants():
    assert (CT.LO, CT.HI, CT.SELL_THR, CT.DD_N, CT.DD_FULL, CT.VOL_N, CT.PCT_MIN, CT.ORACLE_N) == (0.5, 1.0, 0.2, 250, 25.0, 20, 250, 60)
    assert tuple(CT.CANDS) == ("C1", "C2", "C3", "C4", "C5", "C6") and set(CT.CAND_D.values()) <= {"A", "D", "M"}
    assert (CT.CAL_UP, CT.DD_TOL, CT.Z_TOL, CT.MIN_TRADES, CT.HARD_TOL, CT.SHIFT_MIN, CT.PLACEBO_SEEDS) == (0.02, 2.0, 0.02, 30, 0.001, 250, 20)


def test_drawdown_score_and_vol_pct_use_only_past():
    d = pd.bdate_range("2019-01-01", periods=600)
    c = pd.Series(100.0, index=d)
    c.iloc[300:] = 100.0 * (1 - 0.30)                                                    # 跌 30% → 满分 1
    c.iloc[301] = 100.0 * (1 - 0.10)                                                     # 一天回到 −10% → 0.4
    s = CT.drawdown_score(c)
    assert s.iloc[100] == 0.0 and abs(s.iloc[300] - 1.0) < 1e-12 and abs(s.iloc[301] - 0.4) < 1e-12
    c2 = c.copy()
    c2.iloc[400:] = 50.0                                                                 # 改未来 → 之前不变
    assert CT.drawdown_score(c2).iloc[:400].equals(s.iloc[:400])
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0, 0.01, 600), index=d)
    r.iloc[500:] *= 5                                                                    # 后段波动大
    px = 100 * np.exp(r.cumsum())
    v = CT.vol_pct(px)
    assert v.iloc[:CT.PCT_MIN + CT.VOL_N - 2].isna().all() and v.iloc[-1] > 0.9 and 0 < v.iloc[300] <= 1
    assert CT.expanding_pct(pd.Series([1.0, 2.0, 3.0, 2.5]), min_hist=2).tolist()[1:] == [1.0, 1.0, 0.75]


def test_policy_daily_and_danger_frame_mean_skips_nan():
    d = pd.bdate_range("2020-01-01", "2020-03-31")
    shock = {CT.PP.mon("2020-01-01"): "neg", CT.PP.mon("2020-02-01"): "pos"}             # 3 月没有 → NaN
    p = CT.policy_daily(d, shock)
    assert p[d.month == 1].eq(1.0).all() and p[d.month == 2].eq(0.0).all() and p[d.month == 3].isna().all()
    n225 = pd.Series(np.linspace(100, 90, len(d)), index=d)
    a0 = pd.Series(80.0, index=d[10:])
    F = CT.danger_frame(d, n225, a0, shock)
    assert list(F.columns) == ["A", "D", "V", "P", "M"] and F["A"].iloc[0] != F["A"].iloc[0] and F["A"].iloc[-1] == 0.8
    assert F["V"].isna().all()                                                           # 历史不满 250 天
    m_last = F["M"].iloc[-1]
    assert abs(m_last - np.nanmean([F["A"].iloc[-1], F["D"].iloc[-1]])) < 1e-12          # P、V 缺 → 跳过
    assert F["M"].notna().all()


def test_exposure_shift_oracle_fill_and_sell():
    d = pd.bdate_range("2021-01-01", periods=10)
    s = pd.Series([0.0, 0.5, 1.0, np.nan, 0.25, 0.75, 0.0, 1.0, 0.5, 0.2], index=d)
    e = CT.exposure(s, +1)
    assert e.iloc[0] == 0.5 and e.iloc[2] == 1.0 and e.iloc[3] == 0.75 and abs(e.iloc[4] - 0.625) < 1e-12
    e2 = CT.exposure(s, -1)
    assert e2.iloc[0] == 1.0 and e2.iloc[2] == 0.5 and e2.iloc[3] == 0.75
    assert (e.min() >= CT.LO) and (e.max() <= CT.HI)
    e6 = CT.exposure(s, +1, lo=0.0, hi=1.0)
    assert e6.iloc[0] == 0.0 and e6.iloc[2] == 1.0 and e6.iloc[3] == 0.5 and e6.iloc[9] == 0.2
    sh = CT.shift_window(s.fillna(0.3), str(d[2].date()), str(d[7].date()), 2)
    assert sh.iloc[0] == s.iloc[0] and sh.iloc[9] == s.iloc[9] and sh.iloc[2] == s.fillna(0.3).iloc[6] and sh.iloc[4] == s.fillna(0.3).iloc[2]
    assert sorted(sh.iloc[2:8].tolist()) == sorted(s.fillna(0.3).iloc[2:8].tolist())
    close = pd.Series(np.r_[np.linspace(100, 120, 5), np.linspace(120, 100, 5)], index=d)
    o = CT.oracle_score(close, d, n=2)
    assert o.iloc[0] == 1.0 and o.iloc[5] == 0.0 and o.iloc[-1] == 0.5
    f = CT.fill_series(e)
    assert f.iloc[0] == 0.75 and f.iloc[1] == e.iloc[0] and f.iloc[3] == e.iloc[2]
    rng = np.random.default_rng(1)
    ks = [CT.shift_amount(rng, 2600) for _ in range(100)]
    assert min(ks) >= 250 and max(ks) <= 2350


def test_quintile_table_and_encode():
    d = pd.bdate_range("2015-01-01", periods=800)
    score = pd.Series(np.linspace(0, 1, 800), index=d)
    close = pd.Series(100 * np.exp(np.linspace(0, 1, 800) ** 2), index=d)               # 分数高的时候之后涨得更多
    qt = CT.quintile_table(score, close, "2015-01-01", None)
    assert set(qt) == {20, 60} and set(qt[20]) == {0, 1, 2, 3, 4}
    assert qt[60][4]["mean"] > qt[60][0]["mean"] and qt[20][4]["n"] >= 100
    assert CT.quintile_table(score.iloc[:30], close, "2015-01-01", None) == {}
    W = pd.DataFrame({"1545.T": pd.Series([1.0, 0.0, 0.7], index=d[:3])})
    cfg_over, bear, expo = CS.encode(W)
    assert cfg_over["core_mode"] == "split" and list(bear) == ["CS:1545.T"] and bear["CS:1545.T"].tolist() == [False, True, False]
    assert expo["CS:1545.T"].tolist() == [1.0, 0.0, 0.7]


def test_engine_class_and_verdict():
    Eng = CT.engine_cls()
    assert Eng.EXPO == {} and Eng.SELL is None and hasattr(Eng, "_check_exits")
    seg = lambda c, dd, n=40: {"calmar": c, "dd": dd, "n": n}                            # noqa: E731
    a0 = {"Z": seg(1.7, -8.0), "E": seg(0.32, -27.5), "J": seg(0.40, -35.0)}
    good = {"Z": seg(1.69, -8.0), "E": seg(0.35, -27.0), "J": seg(0.43, -34.0)}
    assert CT.verdict("C3", good, a0, [0.01, 0.02, 0.03])[0] == "通过"
    assert CT.verdict("C3", good, a0, [0.05, 0.06, 0.07])[0] == "不通过"
    deep = {**good, "E": seg(0.35, -30.0)}
    assert any("回撤" in x for x in CT.verdict("C3", deep, a0, [0.0])[1])
