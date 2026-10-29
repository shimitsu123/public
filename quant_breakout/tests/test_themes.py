"""日本细分主题（qbreak/themes.py、scripts/theme_study.py）：成员唯一、主题相对收益、成员不足时缺值、成员过半的東証业种、
「错峰」的对齐、晚到的关系只在对应的错峰格被发现、复现表按错峰分开、登记的列表前后一致。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import supply_chain as SC
from qbreak import themes as TH

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import theme_study as TS                                                    # noqa: E402


def test_members_unique_and_ai_chain():
    codes = [c for v in TH.THEMES.values() for c in v[2]]
    assert len(codes) == len(set(codes)) == len(TH.members()) == 88                 # 一只股票只属于一个主题
    assert all(len(c) == 4 for c in codes)
    assert set(TH.AI_CHAIN) <= set(TH.THEMES) and "T1" not in TH.AI_CHAIN


def test_theme_returns_relative_and_min_members():
    days = pd.bdate_range("2020-01-01", periods=4)
    px = lambda v: pd.DataFrame({"Close": np.array(v, float)}, index=days)        # noqa: E731
    ohlc = {"9501.T": px([100, 110, 110, 110]), "9502.T": px([100, 100, 121, 121]), "9503.T": px([100, 100, 100, 90])}
    univ = pd.Series([np.nan, 1.0, 0.0, 0.0], index=days)
    R = TH.theme_returns(ohlc, univ)
    r1 = (np.log(1.1) * 100 + 0 + 0) / 3 - 1.0
    assert R.loc[days[1], "T1"] == pytest.approx(r1)
    assert R["T2"].isna().all()                                                    # 燃气的成员一个也没有 → 缺值
    R2 = TH.theme_returns({k: v for k, v in ohlc.items() if k != "9503.T"}, univ)
    assert R2["T1"].isna().all()                                                   # 只有 2 只 < 3 只 → 缺值


def test_parent_overlap():
    s33 = {"9501": "電気・ガス業", "9502": "電気・ガス業", "8035": "電気機器", "6146": "機械", "6857": "電気機器", "6920": "電気機器",
           "7735": "電気機器", "6525": "電気機器", "6323": "機械", "6315": "機械", "7729": "精密機器", "6871": "電気機器"}
    par = TH.parent_overlap(s33)
    assert par["T9"] == {"電気機器"}                                               # 10 只里 6 只 → 过半
    assert "機械" not in par["T9"] and par["T3"] == set()                           # 没有业种信息 → 空


def test_ahead_lag_alignment():
    M = pd.DataFrame({"a": np.arange(1, 21, dtype=float)}, index=pd.date_range("2020-01-31", periods=20, freq="ME"))
    assert TH.ahead_lag(M, 3, 0)["a"].iloc[0] == 2 + 3 + 4
    assert TH.ahead_lag(M, 3, 3)["a"].iloc[0] == 5 + 6 + 7                         # 隔 3 个月再算之后 3 个月
    assert TH.ahead_lag(M, 1, 6)["a"].iloc[0] == 8
    assert np.isnan(TH.ahead_lag(M, 3, 6)["a"].iloc[11])


def test_scan_lag_finds_late_effect_only_at_matching_lag():
    rng = np.random.default_rng(5)
    n = 300
    months = pd.date_range("2000-01-31", periods=n, freq="ME")
    x = rng.normal(0, 1, n)
    y = rng.normal(0, 1, n)
    y[4:] += -0.8 * x[:-4]                                                         # t 月的信号 → t+4 月（L = 3、h = 1 的格）
    X = {1: pd.DataFrame({"s": x}, index=months)}
    M = pd.DataFrame({"a": y}, index=months)
    Y = {(1, L): TH.ahead_lag(M, 1, L) for L in (0, 3, 6)}
    mon = months[12:]
    spans = {"H1": (mon[0], mon[len(mon) // 2 - 1]), "H2": (mon[len(mon) // 2], mon[-1])}
    S_ = TH.scan_lag(X, Y, [("s", "a")], mon, spans, 0, "f")
    t = S_.set_index(["L", "half"])["t"]
    assert t[(3, "H1")] < -5 and t[(3, "H2")] < -5
    assert abs(t[(0, "H1")]) < 3 and abs(t[(6, "H2")]) < 3
    D = TH.replicate_lag(S_, 0.10)
    assert len(D) == 3 and D.set_index("L").loc[3, "rep"] and not D.set_index("L").loc[0, "rep"]   # 不同 L 不会被平均到一起
    Sp = TH.scan_lag(X, Y, [("s", "a")], mon, spans, 100, "f")                    # 错开 100 个月的对照 → 没有
    assert Sp["t"].abs().max() < 3.5


def test_registered_lists_are_consistent():
    assert len(TS.TA_LIST) == 38
    for code, src, tgt, sg, l3 in TS.TA_LIST:
        kind, _, key = src.partition(":")
        assert (kind == "jp" and key in TS.JP_PRICE) or (kind == "us" and key in TS.US_SRC) or (kind == "th" and key in TH.THEMES)
        assert sg in (-1, 1) and (tgt in TH.THEMES or tgt in {"化学", "鉄鋼", "非鉄金属", "パルプ・紙", "ガラス・土石製品"})
        assert l3 == (code in ("P1", "P4a"))
    assert TS.lab("jp:lng") == "进口 LNG 价格" and TS.lab("T9").startswith("T9 ") and TS.lab("us:Chips").startswith("美国 Chips")


def test_build_sources_prefixes_and_lags():
    months = pd.date_range("2019-01-31", periods=24, freq="ME")
    P = pd.DataFrame({k: 100 * np.exp(np.linspace(0, 0.2, 30)) for k in TS.JP_PRICE}, index=pd.date_range("2018-07-01", periods=30, freq="MS"))
    Mus = pd.DataFrame({k: 1.0 for k in TS.US_SRC}, index=months)
    Mj = pd.DataFrame({k: 2.0 for k in TH.THEMES}, index=months)
    X = TS.build_sources(P, Mus, Mj, months)
    assert set(X) == set(SC.WINDOWS)
    cols = set(X[3].columns)
    assert {"jp:lng", "us:Chips", "th:T9"} <= cols and len(cols) == len(TS.JP_PRICE) + len(TS.US_SRC) + len(TH.THEMES)
    assert X[3]["us:Chips"].iloc[5] == 3.0 and X[3]["th:T1"].iloc[5] == 6.0
    ch = SC.price_change(P, months, 3)
    assert X[3]["jp:lng"].iloc[10] == pytest.approx(ch["lng"].iloc[10])            # 价格 = 发布滞后 1 个月的对数变化
