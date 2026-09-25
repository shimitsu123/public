"""因子调查（qbreak/survey.py）：每种变换只用截止日时已公布的数据；方向与停更判断。"""
import numpy as np
import pandas as pd

from qbreak import survey as SV


def _freq(kind: str, src: str) -> str:
    if kind == "c_ma30":
        return "D"
    if kind.startswith("d_"):
        return "B"
    if kind.startswith("w_"):
        return "W-WED"
    if kind.startswith("m_"):
        return "MS"
    return "QE" if src.startswith("tankan") else "QS"


def _raw(rng, start="2008-01-01", end="2014-12-31"):
    raw = {}
    for _, _, _, kind, srcs, _, _, _ in SV.SPECS:
        for s in srcs:
            if s in raw:
                continue
            idx = pd.date_range(start, end, freq=_freq(kind, s))
            raw[s] = pd.Series(np.abs(100 + np.cumsum(rng.normal(0, 1, len(idx)))) + 5, index=idx)
    return raw


def test_survey_features_no_lookahead():
    rng = np.random.default_rng(21)
    raw = _raw(rng)
    days = pd.bdate_range("2011-01-03", "2014-06-30")
    cut = days[600]
    for jp in (False, True):
        f = SV.features(days, raw, jp_market=jp)
        bad = {}                                                   # 各数据源在截止日还没公布的部分（按各自的时滞）
        for _, _, _, kind, srcs, lag, _, country in SV.SPECS:
            for s in srcs:
                x = raw[s]
                if kind.startswith("d_"):
                    same_day_ok = (not jp) and (country in ("JP", "CN") or lag == 0)
                    b = (x.index > cut) if same_day_ok else (x.index >= cut)
                else:
                    b = x.index + pd.Timedelta(days=lag + (1 if (jp and country == "US") else 0)) > cut
                bad[s] = np.asarray(b) if s not in bad else (bad[s] & np.asarray(b))
        raw2 = {s: x.where(~bad[s], x * 1.5 + 7) for s, x in raw.items()}
        f2 = SV.features(days, raw2, jp_market=jp)
        assert f.loc[:cut].equals(f2.loc[:cut]), jp
        assert not f.loc[cut + pd.Timedelta(days=120):].equals(f2.loc[cut + pd.Timedelta(days=120):])


def test_survey_directions_and_stale():
    days = pd.bdate_range("2012-01-02", periods=300)
    up = pd.Series(np.linspace(100, 200, 300), index=days)
    raw = {"yf:^SOX": up, "yf:^GSPC": pd.Series(100.0, index=days), "yf:^OVX": up}
    f = SV.features(days, raw, jp_market=False)
    assert (f["semis_rel"].dropna() < 0).all()                    # 半导体跑赢大盘 → 危险度为负（方向 −1）
    assert (f["oil_vol"].dropna() > 0).all() and "breadth" not in f   # 没有数据的因素不出现
    st = SV.stale({"fred:WALCL": pd.Series([1.0], index=[pd.Timestamp("2023-01-04")])}, pd.Timestamp("2026-09-25"))
    assert st.get("fed_bs") == "2023-01-04" and st.get("m2_us") == "取不到"
