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


def _row(code, date, time, doc, per, fyst, fyen, nxt="", disc_no="1", **kw):
    base = dict(Code=code, DiscDate=date, DiscTime=time, DiscNo=disc_no, DocType=doc, CurPerType=per, CurFYSt=fyst, CurFYEn=fyen, NxtFYEn=nxt,
                OP="", OdP="", NP="", FOP="", FOdP="", FNP="", NxFOP="", NxFOdP="", NxFNp="", RetroRst="false", ChgAcEst="false",
                MatChgSub="false", SigChgInC="false", FDivAnn="")
    base.update(kw)
    return base


def _fins_full():
    FS = "{}FinancialStatements_Consolidated_JP"
    rows = [
        # 甲（12340，3 月决算）：2019 年 1Q 实绩 20 → 2020 年 3Q 予想 95 → FY 实绩 90、下期予想 100 → 1Q 重申 100（实绩 30、yoy +50%）
        # → 周六的上修 130（+30%）与同日重复行（订正）→ 1Q 短信的订正（同键第二次）→ 13 个月的过渡期决算
        _row("12340", "2019-08-05", "15:00", FS.format("1Q"), "1Q", "2019-04-01", "2020-03-31", OP="20", FOP="80", FDivAnn="10"),
        _row("12340", "2020-02-05", "11:30", FS.format("3Q"), "3Q", "2019-04-01", "2020-03-31", OP="70", FOP="95", FDivAnn="12"),
        _row("12340", "2020-05-10", "15:00", FS.format("FY"), "FY", "2019-04-01", "2020-03-31", nxt="2021-03-31", OP="90", NxFOP="100", NxFNp="60"),
        _row("12340", "2020-08-05", "15:30", FS.format("1Q"), "1Q", "2020-04-01", "2021-03-31", OP="30", FOP="100", FNP="60", FDivAnn="12"),
        _row("12340", "2020-09-19", "", "EarnForecastRevision", "FY", "2020-04-01", "2021-03-31", disc_no="5", FOP="130", FNP="66", FDivAnn="15"),
        _row("12340", "2020-09-19", "", "EarnForecastRevision", "FY", "2020-04-01", "2021-03-31", disc_no="9", FOP="130", FNP="66"),
        _row("12340", "2020-09-01", "15:00", FS.format("1Q"), "1Q", "2020-04-01", "2021-03-31", disc_no="7", OP="31", FOP="100"),
        _row("12340", "2021-08-10", "15:00", FS.format("1Q"), "1Q", "2021-04-01", "2022-06-30", OP="40", FOP="150"),
        # 乙（56780，银行）：没有营业利润 → 经常利润档；2024-11-06 15:10 开示 = 延长后的盘中；2024-11-01 15:10 = 旧制度的盘后
        _row("56780", "2024-11-01", "15:10", FS.format("2Q"), "2Q", "2024-04-01", "2025-03-31", OdP="50", FOdP="80"),
        _row("56780", "2024-11-06", "15:10", "EarnForecastRevision", "2Q", "2024-04-01", "2025-03-31", FOdP="96"),
        # 不算：REIT、股息修正、优先股代码、遡及修正
        _row("12340", "2020-11-10", "15:00", "DividendForecastRevision", "2Q", "2020-04-01", "2021-03-31", FDivAnn="20"),
        _row("34560", "2020-11-10", "15:00", "FYFinancialStatements_Consolidated_REIT", "FY", "2019-11-01", "2020-10-31", OP="5"),
        _row("99991", "2020-11-10", "15:00", FS.format("2Q"), "2Q", "2020-04-01", "2021-03-31", OP="5", FOP="10"),
        _row("12340", "2020-11-11", "15:00", FS.format("2Q"), "2Q", "2020-04-01", "2021-03-31", OP="60", FOP="140", RetroRst="true"),
    ]
    return pd.DataFrame(rows)


def test_events_full_levels_revisions_corrections_and_timing():
    days = pd.bdate_range("2019-01-01", "2025-01-31")
    E = FE.events_full(_fins_full(), days)
    assert set(E["ticker"]) == {"1234.T", "5678.T"} and "FYFinancialStatements_Consolidated_REIT" not in set(E["doc"])
    assert "DividendForecastRevision" not in set(E["doc"])
    a = E[E["ticker"] == "1234.T"].sort_values(["date", "disc_no"]).reset_index(drop=True)
    assert a["level"].tolist()[:5] == ["OP"] * 5
    fy = a[a["per"] == "FY"].iloc[0]
    assert fy["fy"] == "2021-03-31" and fy["fc"] == 100 and np.isnan(fy["rev"]) and not fy["pos"]                # 新 FY 第一次予想：rev 缺值
    assert np.isclose(fy["g_next"], (100 / 90 - 1) * 100) and np.isclose(fy["beat"], (90 - 95) / 95 * 100)    # 下期予想 ÷ 实绩、实绩对最后予想
    q1 = a[(a["per"] == "1Q") & (a["date"] == "2020-08-05")].iloc[0]
    assert np.isclose(q1["rev"], 0.0) and q1["pos"] and np.isclose(q1["yoy"], 50.0) and q1["first"] and np.isclose(q1["fc_prev"], 100)
    assert np.isclose(q1["rev_np"], 0.0)                                                                       # 净利润予想 60 → 60
    assert bool(q1["after_close"]) and q1["sig_day"] == pd.Timestamp("2020-08-05") and q1["t0"] == pd.Timestamp("2020-08-06") and q1["r"] == q1["t0"]
    corr = a[(a["per"] == "1Q") & (a["date"] == "2020-09-01")].iloc[0]
    assert not corr["first"] and np.isclose(corr["rev"], 0.0)                                                # 同键第二次开示 = 订正
    rv = a[a["doc"] == "EarnForecastRevision"].reset_index(drop=True)
    assert len(rv) == 2 and rv.iloc[0]["first"] and not rv.iloc[1]["first"]
    assert np.isclose(rv.iloc[0]["rev"], 30.0) and rv.iloc[0]["pos"] and np.isclose(rv.iloc[0]["rev_np"], 10.0) and np.isclose(rv.iloc[1]["rev"], 0.0)
    assert np.isclose(rv.iloc[0]["div_rev"], 25.0)                                                             # 股息予想 12 → 15
    assert rv.iloc[0]["sig_day"] == pd.Timestamp("2020-09-18") and rv.iloc[0]["t0"] == pd.Timestamp("2020-09-21") and rv.iloc[0]["r"] == pd.Timestamp("2020-09-21")
    assert bool(rv.iloc[0]["after_close"])                                                                     # 周六、没有时刻 → 当盘后
    q3 = a[a["per"] == "3Q"].iloc[0]
    assert not bool(q3["after_close"]) and q3["r"] == pd.Timestamp("2020-02-05") and q3["t0"] == pd.Timestamp("2020-02-06")   # 盘中开示：反应日 = 当天
    assert np.isclose(q3["rev"], (95 - 80) / 80 * 100) and np.isnan(q3["yoy"])                                # 上年 3Q 没有 → yoy 缺值
    tr = a[a["date"] == "2021-08-10"].iloc[0]
    assert not tr["fy12"]                                                                                      # 15 个月的过渡期
    retro = a[a["date"] == "2020-11-11"].iloc[0]
    assert retro["retro"] and retro["first"]
    b = E[E["ticker"] == "5678.T"].sort_values("date").reset_index(drop=True)
    assert b["level"].tolist() == ["OdP", "OdP"] and np.isclose(b.iloc[1]["rev"], 20.0) and b.iloc[1]["pos"]
    assert bool(b.iloc[0]["after_close"]) and not bool(b.iloc[1]["after_close"])                             # 15:10：2024-11-05 前盘后、之后盘中
    assert b.iloc[1]["r"] == pd.Timestamp("2024-11-06") and b.iloc[0]["r"] == pd.Timestamp("2024-11-04")
    assert FE.events_full(_fins_full().iloc[0:0], days).empty


def test_describe_events_full_reaction_gap_and_split():
    n = 300
    days = pd.bdate_range("2020-01-06", periods=n)
    c = np.full((n, 2), 1000.0)
    i = _fri(days)                                                       # 周五盘后开示 → t0 = r = 下周一
    c[i + 1:, 0] = 1050.0                                                # 周一收 1050（反应 +5%）
    O = c.copy(); O[i + 1, 0] = 1020.0                                   # 周一开 1020（跳空 +2%）、收阳
    V = np.full((n, 2), 1e5); V[i + 1, 0] = 4e5
    R = np.full((n, 2), 0.5); R[i + 1:, 1] = 0.25                         # 第二只票在 t0 拆股（t0+1 才拆的不算：不用进场后的信息）
    A = {"days": days, "names": ["1234.T", "5678.T"], "O": O, "H": c * 1.01, "L": c * 0.99, "C": c, "V": V, "R": R, "VA": np.full((n, 2), 5e8),
         "MC": np.full((n, 2), 1e10), "listed": np.ones((n, 2), bool)}
    E = pd.DataFrame({"ticker": ["1234.T", "5678.T"], "sig_day": [days[i], days[i]], "t0": [days[i + 1], days[i + 1]], "r": [days[i + 1], days[i + 1]]})
    D = FE.describe_events(A, E)
    a, b = D.iloc[0], D.iloc[1]
    assert np.isclose(a["lot_yen"], 1000 * 0.5 * 100) and np.isclose(a["gap_t0"], 2.0) and np.isclose(a["react"], 5.0) and np.isclose(a["react_d"], 5.0)
    assert np.isclose(a["vr_r"], 4.0) and a["up_r"] == 1.0 and a["listed_t0"] == 1.0 and a["split_near"] == 0.0 and np.isclose(a["mc"], 1e10)
    assert b["split_near"] == 1.0 and np.isclose(b["react"], 0.0)
