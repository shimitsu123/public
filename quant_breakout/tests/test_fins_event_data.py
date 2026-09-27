"""scripts/fins_event_data.py：事件表（信号日 = 开示日当天或之前的交易日、盘后标记）、描述字段、事件当买点 = 信号日的下一个开盘。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fins_event_data as FE  # noqa: E402


def _panel(n=300, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-06", periods=n)
    c = 1000 * np.cumprod(1 + rng.normal(0, 0.01, (n, 2)), axis=0)
    A = {"days": days, "names": ["1234.T", "5678.T"], "O": c * 0.999, "H": c * 1.01, "L": c * 0.99, "C": c, "V": np.full((n, 2), 1e5),
         "R": np.full((n, 2), 0.5), "VA": np.full((n, 2), 5e8), "MC": np.full((n, 2), 1e10), "listed": np.ones((n, 2), bool)}
    return A


def _fri(days):
    return next(i for i in range(200, len(days)) if days[i].weekday() == 4)          # 第 200 天之后的第一个周五


def _fins(days):
    i = _fri(days)
    d_fri, d_sat = days[i], days[i] + pd.Timedelta(days=1)                         # 周五盘后、周六（非交易日）
    assert d_sat.weekday() == 5
    rows = [dict(Code="12340", DiscDate=str(d_fri.date()), DiscTime="15:30", DocType="1QFinancialStatements_Consolidated_JP", CurPerType="1Q",
                 CurFYSt="2020-04-01", CurFYEn="2021-03-31", NxtFYEn="", OP="10", OdP="", NP="", FOP="100", FOdP="", FNP="", NxFOP="", NxFOdP="", NxFNp=""),
            dict(Code="12340", DiscDate=str(d_sat.date()), DiscTime="", DocType="EarnForecastRevision", CurPerType="",
                 CurFYSt="2020-04-01", CurFYEn="2021-03-31", NxtFYEn="", OP="", OdP="", NP="", FOP="130", FOdP="", FNP="", NxFOP="", NxFOdP="", NxFNp=""),
            dict(Code="56780", DiscDate=str(days[150].date()), DiscTime="11:30", DocType="2QFinancialStatements_Consolidated_JP", CurPerType="2Q",
                 CurFYSt="2020-01-01", CurFYEn="2020-12-31", NxtFYEn="", OP="50", OdP="", NP="", FOP="80", FOdP="", FNP="", NxFOP="", NxFOdP="", NxFNp=""),
            dict(Code="99991", DiscDate=str(days[150].date()), DiscTime="15:00", DocType="FYFinancialStatements_Consolidated_JP", CurPerType="FY",
                 CurFYSt="2019-01-01", CurFYEn="2019-12-31", NxtFYEn="2020-12-31", OP="1", OdP="", NP="", FOP="", FOdP="", FNP="", NxFOP="2", NxFOdP="", NxFNp="")]
    return pd.DataFrame(rows)


def test_events_table_signal_day_and_flags():
    A = _panel()
    E = FE.events_table(_fins(A["days"]), A["days"])
    assert set(E["ticker"]) == {"1234.T", "5678.T"}                                  # 优先股代码 99991 → 不算
    a, fri = E[E["ticker"] == "1234.T"].sort_values("date"), _fri(A["days"])
    assert a.iloc[0]["sig_day"] == A["days"][fri] and bool(a.iloc[0]["after_close"])   # 周五 15:30 → 信号日 = 周五
    assert a.iloc[1]["sig_day"] == A["days"][fri] and bool(a.iloc[1]["after_close"])   # 周六开示、没有时刻 → 信号日 = 周五、当盘后
    assert np.isclose(a.iloc[1]["rev"], 30.0) and a.iloc[1]["doc"] == "EarnForecastRevision"
    b = E[E["ticker"] == "5678.T"].iloc[0]
    assert b["sig_day"] == A["days"][150] and not bool(b["after_close"]) and b["per"] == "2Q"
    D = FE.describe_events(A, E)
    assert np.isclose(D["lot_yen"].iloc[0], A["C"][fri, 0] * 0.5 * 100) and np.isclose(D["va20"].iloc[0], 5e8)
    assert FE.events_table(_fins(A["days"]).iloc[0:0], A["days"]).empty


def test_event_trades_enter_next_open_only_on_events():
    from qbreak.trader import load_params
    A = _panel()
    E = FE.events_table(_fins(A["days"]), A["days"])
    p = load_params(market="JP")
    fr = FE.event_frames(A, E, p)
    assert set(fr) == {"1234.T", "5678.T"} and fr["1234.T"]["entry"].sum() == 1 and fr["5678.T"]["entry"].sum() == 1
    T = FE.event_trades(A, E, p, str(A["days"][0].date()))
    assert len(T) == 2 and set(T["ticker"]) == {"1234.T", "5678.T"}
    for r in T.itertuples():
        sig = pd.Timestamp(r.sig_date)
        assert sig in set(E.loc[E["ticker"] == r.ticker, "sig_day"])
        assert pd.Timestamp(r.entry_date) == A["days"][A["days"].get_loc(sig) + 1]      # 信号日的下一个交易日成交
    assert "ev_rev" in T.columns and np.isfinite(T["net"]).all()
