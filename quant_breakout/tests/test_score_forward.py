"""买点质量分的前向记录（qbreak/score_forward.py、scripts/score_forward.py）：冻结的配比存取一致、只追加（同一日期 × 票保留最早）、
只记登记之后的日子、复核的对账与判定时点。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import score_forward as SF
from qbreak import signal_score as S
from qbreak.config import StrategyParams
from qbreak.strategy import compute_indicators

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import score_forward as SFR                                                  # noqa: E402

P = StrategyParams(range_x_pct=40.0, vol_mult=1.0)
TICKERS = ["4004.T", "4005.T", "4021.T", "8306.T", "8316.T", "8411.T", "7203.T"]


def _ind(n=700, seed=2):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=n)
    out = {}
    for t in TICKERS:
        c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
        o = c * (1 + rng.normal(0, 0.004, n))
        df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99, "Close": c,
                           "Volume": rng.integers(50_000, 400_000, n).astype(float)}, index=days)
        out[t] = compute_indicators(df, P)
    idx = pd.Series(30000 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n))), index=days)
    return out, idx


def _models(ind, idx):
    rows = S.signal_rows(S.feature_panel(ind, idx), ind)
    rng = np.random.default_rng(0)
    tr = rows.assign(win=(rng.random(len(rows)) < 0.45).astype(float), net=rng.normal(0.5, 5, len(rows)),
                     pos=np.arange(len(rows)) * 3)
    return {"F1": S.fit("ew", S.ALL, tr), "F2": S.fit("lr", S.ALL, tr), "F4": S.fit("ew", S.INDUSTRY, tr)}, rows


def test_model_roundtrip(tmp_path):
    ind, idx = _ind()
    models, rows = _models(ind, idx)
    fp = tmp_path / "m.json"
    SF.save_model(models, {"id": "t1"}, fp)
    back, meta = SF.load_model(fp)
    assert meta["id"] == "t1"
    for k, m in models.items():
        assert np.allclose(back[k].score(rows), m.score(rows)) and back[k].thr == pytest.approx(m.thr)


def test_append_keeps_first_record(tmp_path):
    fp = tmp_path / "log.csv"
    a = pd.DataFrame({"date": ["2026-09-28", "2026-09-28"], "ticker": ["A.T", "B.T"], "F1": [0.1, 0.2]})
    assert SF.append_log(a, fp) == 2
    b = pd.DataFrame({"date": ["2026-09-28", "2026-09-29"], "ticker": ["A.T", "A.T"], "F1": [9.9, 0.3]})
    assert SF.append_log(b, fp) == 1
    got = pd.read_csv(fp)
    assert got.loc[(got.date == "2026-09-28") & (got.ticker == "A.T"), "F1"].item() == 0.1   # 旧值不改
    assert len(got) == 3 and SF.append_log(b, fp) == 0


def test_run_daily_logs_only_forward_signals_with_frozen_scores(tmp_path, monkeypatch):
    ind, idx = _ind()
    models, rows = _models(ind, idx)
    mp, lp = tmp_path / "m.json", tmp_path / "log.csv"
    SF.save_model(models, {"id": "t1"}, mp)
    days = list(ind[TICKERS[0]].index[-40:])
    monkeypatch.setattr(SF, "FORWARD_START", str(days[10].date()))
    sig = rows[rows["date"].isin(days[10:])]
    assert len(sig) > 0
    d0 = str(sig["date"].iloc[0].date())
    planned = {d0: [sig["ticker"].iloc[0]]}
    r = SF.run_daily(ind, idx, TICKERS, days, planned, mp, lp, "2026-10-01")
    got = pd.read_csv(lp)
    assert r["logged"] == len(sig) == len(got) and (pd.to_datetime(got["date"]) >= days[10]).all()
    first = got[(got.date == d0) & (got.ticker == sig["ticker"].iloc[0])].iloc[0]
    sec = {"4004": "chemical", "4005": "chemical", "4021": "chemical", "8306": "bank", "8316": "bank", "8411": "bank", "7203": "auto"}
    assert first["planned"] == 1 and first["model"] == "t1"
    assert (got["sector"] == got["ticker"].str[:4].map(sec)).all()
    other = got[got.date != d0]
    assert other["planned"].isna().all()                                   # 本次没处理的日子：不知道 → 空
    exp = models["F2"].score(sig.reset_index(drop=True))
    assert np.allclose(got["F2"].to_numpy(), np.round(exp, 6), atol=1e-6)
    assert set(got["F2_keep"]) <= {0, 1} and "F3" not in got.columns
    assert SF.run_daily(ind, idx, TICKERS, days, planned, mp, lp, "2026-10-02")["logged"] == 0    # 再跑一次不重复
    monkeypatch.setattr(SF, "FORWARD_START", "2099-01-01")
    assert SF.run_daily(ind, idx, TICKERS, days, planned, mp, tmp_path / "x.csv", "2026-10-01")["logged"] == 0


def test_review_match_and_checkpoints():
    log = pd.DataFrame({"date": ["2026-10-01", "2026-10-02", "2026-10-05"], "ticker": ["A.T", "B.T", "C.T"], "F2": [0.1, 0.2, 0.3]})
    T = pd.DataFrame({"ticker": ["A.T", "B.T"], "sig_date": pd.to_datetime(["2026-10-01", "2026-10-02"]),
                      "exit_date": pd.to_datetime(["2026-10-20", "2026-12-30"]), "net": [1.0, -2.0], "win": [1.0, 0.0],
                      "reason": ["dead_cross", "end"]})
    C, cnt = SFR.match(log, T)
    assert cnt == {"logged": 3, "matched": 2, "open": 1, "unmatched": 1, "closed": 1} and C["ticker"].tolist() == ["A.T"]
    ev = {"count": {"closed": 120}, "exp": 0.5, "auc": {"F2": {"auc": 0.6, "lo99": 0.51, "hi99": 0.7, "lo95": 0.53, "hi95": 0.68},
                                                        "ind_mom20": {"auc": 0.45, "lo95": 0.38, "hi95": 0.52, "lo99": 0.36, "hi99": 0.54}}}
    v = SFR.decide(ev)
    assert v["checkpoint"] == 100 and v["results"]["F2"]["ok"] and not v["results"]["ind_mom20"]["ok"]
    assert SFR.decide(ev, pd.DataFrame({"checkpoint": [100.0]}))["checkpoint"] is None         # 100 笔已判定过 → 只报告进度
    ev["count"]["closed"] = 450
    assert SFR.decide(ev, pd.DataFrame({"checkpoint": [100.0, 200.0]}))["checkpoint"] == 400
