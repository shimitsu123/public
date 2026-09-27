"""scripts/w2_forward_all.py（W2 的全市场前向检验，2026-09-27 登记）：要补的月末上市一览、只算登记之后的信号、主对象（成交额 ≥ ¥500 万）、
W2 标记与实盘同一规则（缺值 = 保留）、每年只判定一次、补数据只调用 J-Quants 的日线批量与新的月末一览。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import w2_forward_all as WFA                                                 # noqa: E402

from qbreak import w2_forward as W2F                                         # noqa: E402


def test_registered_constants():
    assert WFA.FORWARD_START == "2026-09-28" and WFA.W2_CUT == 1.0 and WFA.LIQ_MIN_YEN == 5_000_000
    assert WFA.JUDGE_DATES == ("2027-09-28", "2028-09-28", "2029-09-28", "2030-09-28", "2031-09-28")
    assert abs(10 ** WFA.LIQ_LOG - 5e6) < 1e-3


def test_month_ends_are_last_tse_trading_days():
    got = WFA.month_ends("2026-09-25", "2026-12-31")
    assert got == ["2026-09-30", "2026-10-30", "2026-11-30", "2026-12-30"]   # 10-31 周六、12-31 休市
    assert WFA.month_ends("2026-09-30", "2026-10-15") == []                  # 十月还没到月末
    assert WFA.month_ends("2026-08-31", "2026-09-30") == ["2026-09-30"]


def test_forward_trades_window_flags_and_main():
    T = pd.DataFrame({"ticker": ["A.T", "B.T", "C.T", "D.T", "E.T"],
                      "sig_date": pd.to_datetime(["2026-09-25", "2026-09-28", "2026-10-05", "2026-10-06", "2026-11-02"]),
                      "net": [1.0, 2.0, -1.0, 0.5, 3.0], "w5v": [0.5, 0.99, np.nan, 1.0, 2.0],
                      "lturn": [7.0, 6.0, 7.2, np.nan, 6.7]})
    F = WFA.forward_trades(T)
    assert F["ticker"].tolist() == ["B.T", "C.T", "D.T", "E.T"]              # 登记之后才发生的信号
    assert F["w2_keep"].tolist() == [0, 1, 1, 1]                              # < 1.0 才挡；缺值 = 保留
    assert F["main"].tolist() == [False, True, False, True]                   # ≥ log10(500 万) ≈ 6.699；缺值不算
    assert WFA.forward_trades(T.iloc[0:0]).empty


def test_decide_once_per_year(tmp_path):
    rng = np.random.default_rng(1)
    n = 1500
    keep = (rng.random(n) < 0.45).astype(int)
    C = pd.DataFrame({"sig_date": pd.to_datetime(rng.choice(pd.bdate_range("2026-09-28", "2027-09-24"), n)), "w2_keep": keep,
                      "net": rng.normal(0, 5.9, n) - 2.0 * keep})
    ev = W2F.evaluate(C, date_col="sig_date")
    assert WFA.decide(ev, None, pd.Timestamp("2027-09-27")) == {"year": None, "alarm": None, "confirmed": None}
    v = WFA.decide(ev, None, pd.Timestamp("2027-10-01"))
    assert v == {"year": "2027-09-28", "alarm": True, "confirmed": False}
    fp = tmp_path / "h.csv"
    pd.DataFrame([{"run": "2027-10-01", "scope": "all", "w2_year": "2027-09-28"}]).to_csv(fp, index=False)
    assert WFA.decide(ev, pd.read_csv(fp), pd.Timestamp("2028-01-10"))["year"] is None
    assert WFA.decide(ev, pd.read_csv(fp), pd.Timestamp("2028-10-01"))["year"] == "2028-09-28"


def test_refresh_only_fetches_daily_bulk_and_new_month_ends(monkeypatch):
    from qbreak import jq_data as JD
    from qbreak import jquants as JQ
    from qbreak import pit_data as PD
    calls = {"bulk": [], "master": []}
    monkeypatch.setattr(JQ, "JQuants", lambda *a, **k: object())
    monkeypatch.setattr(JD, "bulk_download", lambda c, ep, log=print: calls["bulk"].append(ep) or [Path("x.csv.gz")])
    monkeypatch.setattr(JQ, "master_cached", lambda c, d: calls["master"].append(d))
    monkeypatch.setattr(PD, "master_files", lambda: {pd.Timestamp("2026-08-31"): Path("a"), pd.Timestamp("2026-09-25"): Path("b")})
    info = WFA.refresh(log=lambda s: None, today="2026-11-05")
    assert calls["bulk"] == ["/equities/bars/daily"] and calls["master"] == ["2026-09-30", "2026-10-30"]
    assert info == {"bar_files": 1, "new_snapshots": ["2026-09-30", "2026-10-30"]}
