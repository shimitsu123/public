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


# ── X2（2026-09-26 追加登记，scripts/score_forward.py 第七节）──
ROOT = Path(__file__).resolve().parents[1]


def _fake_boj(seed=5):
    """所有短観业种 × 项目 的假季度序列（1974〜2026-06；机械细分 2010 起），像 factors.tankan 一样按代码返回。"""
    from qbreak import tankan as TK
    rng = np.random.default_rng(seed)
    q_all = pd.date_range("1974-03-31", "2026-06-30", freq="QE")
    vals = {}
    for ind in TK.IND:
        q = q_all[q_all >= pd.Timestamp("2010-03-31")] if ind in ("1141", "1142", "1143") else q_all
        for item in TK.ITEMS:
            vals[TK.code(ind, item)] = pd.Series(np.round(np.cumsum(rng.normal(0, 4, len(q))), 0), index=q)
        vals[TK.code(ind, "biz", True)] = pd.Series(np.round(np.cumsum(rng.normal(0, 4, len(q))), 0), index=q)
    return lambda c: vals[c]


def test_x2_matches_fund_study_algorithm():
    """前向记录的 X2 = fund_study 的 X2（同一份短観、同一份产业连关表、同一个信号日 → 同一个值）。"""
    import json
    from qbreak import tankan as TK
    import supply_chain_study as SCS
    fetch = _fake_boj()
    links = json.loads((ROOT / "var" / "io_links_2020.json").read_text(encoding="utf-8"))
    s33 = {f"{c}.T": v for c, v in json.loads((ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    tse = sorted(set(s33.values()))
    # fund_study 的写法（main + part_b）
    s1 = TK.to_groups(TK.signals(TK.load(fetch))["S1"], list(TK.TSE))
    s5 = TK.customer_weighted(s1[[c for c in s1.columns if c in tse]], links["cus"])
    q = s5.index[s5.index >= pd.Timestamp("2006-09-30")]
    F = s5.reindex(q).reindex(columns=tse)
    F.index = pd.DatetimeIndex([TK.available(x) for x in q])
    rng = np.random.default_rng(1)
    tickers = list(rng.choice(sorted(s33), 400))
    dates = pd.Series(pd.to_datetime(rng.choice(pd.bdate_range("2007-01-05", "2026-09-30"), 400)))
    want = SCS.daily_lookup(F, dates, [s33[t] for t in tickers])
    x2 = SF.x2_load(s33, fetch=fetch, links=links)
    got, svy = SF.x2_lookup(x2, dates, tickers)
    assert np.isfinite(want).mean() > 0.95
    assert np.allclose(got, np.round(want, 6), equal_nan=True, atol=1e-6)
    assert x2["latest"] == "2026-06-30"
    # 用到的调查季度：6 月调查 7/5 之后才用（保守），之前用 3 月调查；12 月调查 12/20 起
    one = lambda d: SF.x2_lookup(x2, [pd.Timestamp(d)], ["4004.T"])[1][0]                     # noqa: E731
    assert one("2026-07-03") == "2026-03-31" and one("2026-07-06") == "2026-06-30" and one("2026-07-05") == "2026-06-30"
    assert one("2025-12-19") == "2025-09-30" and one("2025-12-22") == "2025-12-31"
    v, s = SF.x2_lookup(x2, [pd.Timestamp("2026-07-06")], ["9999.T"])                          # 没有业种 → 空
    assert np.isnan(v[0]) and s == [""]


def test_x2_table_fails_loudly_when_boj_is_down():
    def down(c):
        raise RuntimeError("HTTP 503")
    with pytest.raises(RuntimeError, match="短観"):
        SF.x2_table({"化学", "銀行業"}, fetch=down, links={"cus": {"化学": {"銀行業": 1.0}}})


def test_run_daily_logs_x2_columns(tmp_path, monkeypatch):
    ind, idx = _ind()
    models, rows = _models(ind, idx)
    mp, lp, lp2 = tmp_path / "m.json", tmp_path / "log.csv", tmp_path / "log2.csv"
    SF.save_model(models, {"id": "t1"}, mp)
    days = list(ind[TICKERS[0]].index[-40:])
    monkeypatch.setattr(SF, "FORWARD_START", str(days[10].date()))
    mid = days[25]
    tab = pd.DataFrame({"化学": [1.0, 2.5], "銀行業": [-1.0, 0.5]}, index=[days[0] - pd.Timedelta(days=90), mid])
    x2 = {"tab": tab, "svy": pd.Series(["2026-03-31", "2026-06-30"], index=tab.index),
          "s33": {"4004.T": "化学", "4005.T": "化学", "4021.T": "化学", "8306.T": "銀行業", "8316.T": "銀行業", "8411.T": "銀行業"}}
    SF.run_daily(ind, idx, TICKERS, days, None, mp, lp, "2026-10-01", x2=x2)
    got = pd.read_csv(lp, dtype={"x2_survey": str})
    assert len(got) > 0 and {"x2", "x2_survey"} <= set(got.columns)
    d = pd.to_datetime(got["date"])
    chem, bank, auto = got["ticker"].isin(["4004.T", "4005.T", "4021.T"]), got["ticker"].str.startswith("83"), got["ticker"] == "7203.T"
    assert (got.loc[chem & (d >= mid), "x2"] == 2.5).all() and (got.loc[chem & (d < mid), "x2"] == 1.0).all()
    assert (got.loc[bank & (d >= mid), "x2_survey"] == "2026-06-30").all() and (got.loc[bank & (d < mid), "x2"] == -1.0).all()
    assert got.loc[auto, "x2"].isna().all()                                 # 业种表里没有 → 空
    SF.run_daily(ind, idx, TICKERS, days, None, mp, lp2, "2026-10-01", x2=None)
    g2 = pd.read_csv(lp2)
    assert g2["x2"].isna().all() and g2["x2_survey"].isna().all()           # 短観取不到 → 空（不补写）


def test_x2_evaluate_clusters_by_survey_and_decide():
    rng = np.random.default_rng(7)
    n = 300
    svy = rng.choice([f"20{y}-{m}" for y in range(27, 30) for m in ("03-31", "06-30", "09-30", "12-31")], n)
    x = rng.normal(0, 1, n)
    win = (x + rng.normal(0, 1, n) > 0.3).astype(float)
    C = pd.DataFrame({"date": pd.to_datetime(rng.choice(pd.bdate_range("2027-01-01", "2029-12-31"), n)), "win": win,
                      "net": np.where(win > 0, 3.0, -2.0), "vol": rng.normal(0, 1, n), "x2": x, "x2_survey": svy})
    C.loc[:9, "x2"] = np.nan                                                # 取不到的不算
    ev = SFR.evaluate(C, {"closed": n})
    assert ev["x2"] == {"n": n - 10, "clusters": 12} and ev["auc"]["x2"]["lo99"] > 0.5
    v = SFR.decide(ev, None, SFR.CHECKPOINTS_WIDE, "combined", {"x2": 0.6, "vol": 0.5})
    assert v["checkpoint"] == 200 and v["results"]["x2"]["ok"] and v["results"]["x2"]["judged"]
    assert not SFR.decide(ev, None, SFR.CHECKPOINTS_WIDE, "combined", {"x2": 0.45})["results"]["x2"]["ok"]   # 大中型股方向不对
    ev["x2"]["clusters"] = 5                                                # 调查季度不够 8 个 → 这个时点不判定
    r = SFR.decide(ev, None, SFR.CHECKPOINTS_WIDE, "combined", {"x2": 0.6})["results"]["x2"]
    assert r["judged"] is False and not r["ok"] and "不判定" in r["note"]
