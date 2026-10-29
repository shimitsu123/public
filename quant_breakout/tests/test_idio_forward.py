"""K2 / USW 前向记录（qbreak/idio_forward.py，2026-09-27 登记）：登记值、与研究脚本同一算法、只用信号日之前的数据、每年只判定一次。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import idio_forward as IF  # noqa: E402
from qbreak import w2_forward as W2F  # noqa: E402


def test_registered_constants_and_columns():
    assert (IF.K2_VR, IF.K2_BETA) == (2.0, 0.70) and np.isclose(IF.USW_Q, 1 / 3)
    assert (IF.BETA_WEEKS, IF.BETA_MIN_WEEKS, IF.US_LAG_MONTHS) == (104, 69, 2)
    assert IF.COLS == ("vr1", "b_n225", "k2_keep", "us12", "usw_keep") and IF.JUDGE_DATES == W2F.JUDGE_DATES
    import leap2_s4_explore as S4
    import leap2_s6_study as ST
    assert IF.S33_FF49 == S4.S33_FF49 and len(IF.S33_FF49) == 33                    # 对应表 = 研究里看结果之前写定的那份
    assert [ST.CANDS["K2"][1], ST.CANDS["K2"][2]] == [IF.K2_VR, IF.K2_BETA]          # 登记检验里的 K2 同一阈值


def test_us_rank_matches_research_and_lags_two_months():
    import leap2_s4_explore as S4
    rng = np.random.default_rng(0)
    idx = pd.date_range("2000-01-01", periods=30, freq="MS")
    R = pd.DataFrame(rng.normal(0, 5, (30, 4)), index=idx, columns=list("ABCD"))
    P = IF.us_rank_asof(R)
    assert P.loc[R.index].equals(S4.us_rank_asof(R))                                 # 数据覆盖的月份与研究脚本完全相同
    assert len(P) == len(R) + 2 and P.index[-1] == R.index[-1] + pd.DateOffset(months=2)   # 再往后延 2 个月（当月的信号也查得到）
    assert (P.iloc[-1].to_numpy(float) == IF.us_rank_asof(R, 0).iloc[-1].to_numpy(float)).all()   # 延出去的最后一行 = 数据最后一个月的排名
    assert (P.iloc[-2].to_numpy(float) == IF.us_rank_asof(R, 0).iloc[-2].to_numpy(float)).all()
    R2 = R.copy()
    R2.iloc[-1] = 500.0                                                              # 最新一个月改了 → 只影响两个月后
    assert P.loc[R.index].iloc[-1].equals(IF.us_rank_asof(R2).loc[R.index].iloc[-1])
    assert np.isnan(P.iloc[12]).all() and not np.isnan(P.iloc[13]).any()


def test_beta_asof_matches_research_rolling_betas_and_never_looks_ahead():
    import leap2_s5_explore as S5
    rng = np.random.default_rng(1)
    wk = pd.date_range("2019-01-04", periods=200, freq="W-FRI")
    m = pd.Series(rng.normal(0, 0.02, 200), index=wk)
    y = pd.DataFrame({"A": 1.3 * m + rng.normal(0, 0.01, 200)}, index=wk)
    B = S5.rolling_betas(y, pd.DataFrame({"n225": m}), None, weeks=104)["n225"]["A"]
    k = 150
    asof = wk[k] + pd.Timedelta(days=3)                                              # 第 k 周之后那一周的周一 → 用到第 k 周为止
    assert np.isclose(IF.beta_asof(y["A"], m, asof), B.iloc[k])
    y2 = y.copy()
    y2.iloc[k + 1:] = 9.0                                                            # 信号周及以后的周收益改了 → 不变
    assert np.isclose(IF.beta_asof(y2["A"], m, asof), B.iloc[k])
    assert np.isclose(IF.beta_asof(y["A"], m, wk[k]), B.iloc[k - 1])                 # 信号日 = 周五本身 → 只用上一周为止
    assert np.isnan(IF.beta_asof(y["A"].iloc[:60], m, asof))                         # 不到 69 周
    assert abs(IF.beta_asof(y["A"], m, wk[-1] + pd.Timedelta(days=7)) - 1.3) < 0.1


def test_flags_treat_missing_as_registered():
    assert IF.k2_flag([2.0, 2.5, 1.9, np.nan, 3.0], [0.7, 0.71, 0.5, 0.5, np.nan]).tolist() == [1, 0, 0, 0, 0]
    u = IF.usw_flag([0.2, 1 / 3, 0.34, np.nan])
    assert u[:3].tolist() == [1.0, 1.0, 0.0] and np.isnan(u[3])


def test_fields_use_research_definitions():
    from leap_r11_explore import vr1
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2023-01-02", periods=760)
    mkt = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 760)), index=idx)
    ind = {}
    for t, b in (("A.T", 0.4), ("B.T", 1.5)):
        r = b * mkt.pct_change().fillna(0) + rng.normal(0, 0.005, 760)
        c = 100 * np.cumprod(1 + r.to_numpy())
        v = np.full(760, 1000.0)
        v[-1] = 2500.0
        ind[t] = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": v}, index=idx)
    d = idx[-1]
    P = pd.DataFrame({"Chips": [0.2, 0.9]}, index=[d.to_period("M").to_timestamp(), d.to_period("M").to_timestamp() + pd.DateOffset(months=1)])
    f = IF.fields(ind, [d, d], ["A.T", "B.T"], mkt, P, {"A.T": "電気機器", "B.T": "謎"})
    assert np.isclose(f["vr1"][0], vr1(ind["A.T"])[-1], atol=1e-4) and f["vr1"][0] == 2.5
    assert f["b_n225"][0] < 0.7 < f["b_n225"][1] and f["k2_keep"] == [1, 0]
    assert f["us12"][0] == 0.2 and f["usw_keep"][0] == 1.0 and np.isnan(f["us12"][1]) and np.isnan(f["usw_keep"][1])
    g = IF.fields(ind, [d], ["A.T"], None, None, None)                                # 没有指数 / 行业 → β、us12 为空，K2 = 0
    assert np.isnan(g["b_n225"][0]) and g["k2_keep"] == [0] and np.isnan(g["us12"][0])


def _sample(n=900, k2_eff=2.0, usw_eff=2.0, seed=5):
    rng = np.random.default_rng(seed)
    k2 = (rng.random(n) < 0.2).astype(int)
    w2 = (rng.random(n) < 0.5).astype(int)
    usw = np.where(rng.random(n) < 0.9, (rng.random(n) < 1 / 3).astype(float), np.nan)
    net = rng.normal(0, 5.9, n) + k2_eff * k2 + usw_eff * np.nan_to_num(usw) * w2
    return pd.DataFrame({"date": pd.to_datetime(rng.choice(pd.bdate_range("2026-10-01", "2028-09-29"), n)), "k2_keep": k2,
                         "w2_keep": w2, "usw_keep": usw, "net": net, "segment": rng.choice(["N225", "T500x", "S1x"], n)})


def test_review_pair_decides_once_per_year(tmp_path):
    C = _sample()
    rev = IF.review_pair(C, None, pd.Timestamp("2027-10-02"))
    assert set(rev) == {"K2", "USW"} and rev["K2"]["year"] == "2027-09-28" and rev["K2"]["confirmed"] is True
    assert rev["USW"]["eval"]["n"] == int(((C["w2_keep"] == 1) & C["usw_keep"].notna()).sum())   # USW 只看 W2 保留、有值的
    assert rev["USW"]["confirmed"] is True and rev["K2"]["alarm"] is False
    assert set(rev["K2"]["segments"]) == {"N225", "T500x", "S1x"}
    rows = IF.history_rows(rev, "2027-10-02", "", {"logged": 900})
    hist = pd.DataFrame(rows)
    fp = tmp_path / "h.csv"
    hist.to_csv(fp, index=False)
    rev2 = IF.review_pair(C, pd.read_csv(fp), pd.Timestamp("2027-12-20"))
    assert rev2["K2"]["year"] is None and rev2["USW"]["year"] is None and rev2["K2"]["alarm"] is None
    bad = IF.review_pair(_sample(k2_eff=-3.0), None, pd.Timestamp("2027-10-02"))
    assert bad["K2"]["alarm"] is True and bad["K2"]["confirmed"] is False
    lines = IF.say_lines(rev, today=pd.Timestamp("2027-10-02"))
    assert any("K2" in x for x in lines) and any("USW" in x for x in lines)
    assert IF.review_pair(C.iloc[0:0], None, pd.Timestamp("2027-10-02"))["USW"]["eval"]["n"] == 0
