"""扩大池（qbreak/wide_universe.py）：对照表覆盖 33 业种、名单的剔除与分段、行业因子 = 日経225 同组成员的平均、
扩大池的前向记录只追加；合并样本的判定与「没用过的股票」检验的判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import score_forward as SF
from qbreak import signal_score as S
from qbreak import wide_universe as W
from qbreak.config import StrategyParams
from qbreak.strategy import compute_indicators

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import heldout_study as HS                                                   # noqa: E402
import score_forward as SFR                                                  # noqa: E402

P = StrategyParams(range_x_pct=40.0, vol_mult=1.0)


def test_mapping_covers_all_33_industries():
    assert len(set(W.S33_GROUP) | W.EXCL_33) == 33 and not (set(W.S33_GROUP) & W.EXCL_33)
    assert set(W.S33_GROUP.values()) <= set(__import__("qbreak.sectors", fromlist=["SECTOR_JP"]).SECTOR_JP.values()) | {"consumer"}


def test_build_from_jpx(tmp_path):
    df = pd.DataFrame({"日付": "20260831", "コード": ["1111", "2222", "3333", "4444", "5555", "6666"],
                       "市場・商品区分": ["プライム（内国株式）"] * 5 + ["スタンダード（内国株式）"],
                       "33業種区分": ["化学", "陸運業", "銀行業", "化学", "食料品", "化学"],
                       "規模区分": ["TOPIX Mid400", "TOPIX Mid400", "TOPIX Small 1", "TOPIX Core30", "TOPIX Small 2", "TOPIX Mid400"]})
    fp = tmp_path / "d.xlsx"
    df.to_excel(fp, index=False)
    doc = W.build_from_jpx(fp, {"4444"}, "test")
    assert [x["code"] for x in doc["segments"]["T500x"]] == ["1111"]              # 陸運剔除、日経225 成员剔除、スタンダード剔除
    assert [(x["code"], x["group"]) for x in doc["segments"]["S1x"]] == [("3333", "bank")]
    assert W.tickers(doc) == ["1111.T", "3333.T"] and W.segment_of(doc)["3333.T"] == "S1x" and W.group_of(doc)["1111.T"] == "chemical"


def test_industry_factors_use_n225_group_members():
    days = pd.bdate_range("2020-01-01", periods=130)
    base = pd.DataFrame({"4004.T": np.linspace(100, 130, 130), "4005.T": np.linspace(100, 110, 130),
                         "8306.T": np.linspace(100, 90, 130), "3861.T": np.linspace(100, 100, 130)}, index=days)
    ent = pd.DataFrame(False, index=days, columns=base.columns)
    ent.loc[days[-2], "4005.T"] = True
    extra = pd.DataFrame({"9999.T": np.linspace(100, 150, 130), "8888.T": np.linspace(100, 120, 130)}, index=days)
    f = W.industry_panel_vs(extra, base, ent, {"9999.T": "chemical", "8888.T": "bank"})
    last = days[-1]
    r60 = base.iloc[-1] / base.iloc[-61] - 1
    univ = r60.mean()
    chem = (r60["4004.T"] + r60["4005.T"]) / 2
    assert f["ind_mom60"].loc[last, "9999.T"] == pytest.approx(chem - univ)
    assert f["rel_ind60"].loc[last, "9999.T"] == pytest.approx(extra["9999.T"].iloc[-1] / extra["9999.T"].iloc[-61] - 1 - chem)
    assert f["ind_cobreak"].loc[last, "9999.T"] == pytest.approx(0.5)
    assert np.isnan(f["ind_mom60"].loc[last, "8888.T"])                          # 银行在日経225 里只有 1 只 → 不足 2 只


def _synth(tickers, n=700, seed=5):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=n)
    out = {}
    for t in tickers:
        c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
        o = c * (1 + rng.normal(0, 0.004, n))
        out[t] = compute_indicators(pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99,
                                                  "Close": c, "Volume": rng.integers(50_000, 400_000, n).astype(float)},
                                                 index=days), P)
    return out, pd.Series(30000 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n))), index=days)


def test_run_daily_wide_logs_segment_and_is_append_only(tmp_path, monkeypatch):
    base, idx = _synth(["4004.T", "4005.T", "4021.T", "8306.T", "8316.T"])
    extra, _ = _synth(["9001X.T", "9002X.T", "9003X.T"], seed=9)
    doc = {"segments": {"T500x": [{"code": "9001X", "group": "chemical"}, {"code": "9002X", "group": "bank"}],
                        "S1x": [{"code": "9003X", "group": "chemical"}]}}
    rows = S.signal_rows(S.feature_panel(base, idx), base)
    rng = np.random.default_rng(0)
    tr = rows.assign(win=(rng.random(len(rows)) < 0.45).astype(float), net=rng.normal(0.5, 5, len(rows)), pos=np.arange(len(rows)))
    mp, lp = tmp_path / "m.json", tmp_path / "w.csv"
    SF.save_model({"F2": S.fit("lr", S.ALL, tr), "F1": S.fit("ew", S.ALL, tr)}, {"id": "t"}, mp)
    days = list(extra["9001X.T"].index[-60:])
    monkeypatch.setattr(SF, "FORWARD_START", str(days[0].date()))
    r = SF.run_daily_wide(base, extra, idx, doc, days, mp, lp, "2026-10-01")
    got = pd.read_csv(lp) if lp.exists() else pd.DataFrame()
    assert r["logged"] == len(got) > 0 and r["tickers"] == 3
    assert set(got["segment"]) <= {"T500x", "S1x"} and got["planned"].isna().all()
    assert (got.loc[got.ticker == "9003X.T", "segment"] == "S1x").all()
    assert (got.loc[got.ticker == "9002X.T", "sector"] == "bank").all()
    assert SF.run_daily_wide(base, extra, idx, doc, days, mp, lp, "2026-10-02")["logged"] == 0


def test_combined_decision_needs_large_mid_direction():
    ev = {"count": {"closed": 250}, "exp": 0.5, "auc": {"vol": {"auc": 0.6, "lo99": 0.53, "hi99": 0.67, "lo95": 0.55, "hi95": 0.65}}}
    v = SFR.decide(ev, None, SFR.CHECKPOINTS_WIDE, "combined", {"vol": 0.48})
    assert v["checkpoint"] == 200 and not v["results"]["vol"]["ok"] and "大中型" in v["results"]["vol"]["note"]
    assert SFR.decide(ev, None, SFR.CHECKPOINTS_WIDE, "combined", {"vol": 0.56})["results"]["vol"]["ok"]
    h = pd.DataFrame({"scope": ["N225", "combined"], "checkpoint": [None, 200.0]})
    assert SFR.decide(ev, h, SFR.CHECKPOINTS_WIDE, "combined", {"vol": 0.56})["checkpoint"] is None
    assert SFR.decide(ev, h, SFR.CHECKPOINTS, "N225")["checkpoint"] == 200


def test_heldout_decision_rules():
    def seg(auc, lo99, hi99, h1, h2, lo95=None, hi95=None):
        return {"auc": {"vol": {"auc": auc, "lo99": lo99, "hi99": hi99, "lo95": lo95 or lo99, "hi95": hi95 or hi99},
                        "ind_mom20": {"auc": 0.45, "lo95": 0.41, "hi95": 0.49, "lo99": 0.40, "hi99": 0.51}},
                "halves": {"O1": {"vol": h1, "ind_mom20": 0.45}, "O2": {"vol": h2, "ind_mom20": 0.46}}, "exp": 0.5}
    E = {"T500x": seg(0.58, 0.52, 0.64, 0.57, 0.59), "S1x": seg(0.55, 0.5, 0.6, 0.5, 0.6)}
    V = HS.decide(E)
    assert V["vol"]["ok"] and V["ind_mom20"]["ok"]
    E["T500x"]["halves"]["O2"]["vol"] = 0.49
    assert not HS.decide(E)["vol"]["ok"]
    E = {"T500x": seg(0.58, 0.52, 0.64, 0.57, 0.59), "S1x": seg(0.48, 0.45, 0.52, 0.5, 0.5)}
    assert "S1x 点估计不在事先方向" in HS.decide(E)["vol"]["fails"]


def test_score_by_year_uses_that_years_model():
    class M:
        def __init__(self, v):
            self.v, self.thr = v, v / 10

        def score(self, df):
            return np.full(len(df), self.v)
    rows = pd.DataFrame({"date": pd.to_datetime(["2014-05-01", "2015-05-01", "2016-05-01"]), "ticker": ["A", "B", "C"]})
    out = HS.score_by_year(rows, {"F2": {2014: M(1.0), 2015: M(2.0)}})
    assert out["F2"].tolist()[:2] == [1.0, 2.0] and np.isnan(out["F2"].iloc[2]) and out["F2_thr"].iloc[1] == pytest.approx(0.2)
