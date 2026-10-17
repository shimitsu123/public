"""qbreak/check_calendar.py：检查日历 —— 每月第一个交易日、大事件里会引出检查的种类、指数入替的公布 / 生效、季度复核、事先写定的判定日、日报块。"""
import datetime as dt

from qbreak import check_calendar as CK

EV = [{"date": "2026-10-01", "kind": "TANKAN", "home": "JP", "name": "9 月调查（08:50 发布）"},
      {"date": "2026-10-14", "kind": "CPI", "home": "US", "name": "9月CPI"},                        # 只提示的种类：日历里不列
      {"date": "2026-10-30", "kind": "BOJ", "home": "JP", "name": "含展望报告"},
      {"date": "2026-09-30", "kind": "INDEX", "home": "JP", "name": "日経225 定期入替（9/30 收盘调仓、10/1 生效）"},
      {"date": "2026-10-07", "kind": "INDEX", "home": "JP", "name": "新 TOPIX 首次定期入替：公布构成股"},  # 不是日経225：不列
      {"date": "2027-03-01", "kind": "BOJ", "home": "JP", "name": "远"}]                            # 超出 45 天
CH = [{"announced": "2026-09-04", "effective": "2026-10-01", "add": ["5016"], "delete": ["543A"]}]


def test_first_trading_days_skip_weekends_and_holidays():
    d = CK.first_trading_days(dt.date(2026, 9, 28), dt.date(2027, 1, 31))
    assert d == [dt.date(2026, 10, 1), dt.date(2026, 11, 2), dt.date(2026, 12, 1), dt.date(2027, 1, 4)]


def test_items_pick_checks_from_events_changes_rules_and_milestones():
    it = CK.items(dt.date(2026, 9, 28), events=EV, changes=CH)
    whats = [x["what"] for x in it]
    assert [x["date"] for x in it] == sorted(x["date"] for x in it)
    assert any(w.startswith("日银短観") for w in whats) and any(w.startswith("日银会合") for w in whats)
    assert not any("CPI" in w or "TOPIX" in w or "远" in w for w in whats)
    assert any(w.startswith("日経225 入替：日経225 定期入替") for w in whats)
    assert any("生效" in w and "+5016" in w and "−543A" in w for w in whats)                       # 公布日 9/4 在今天之前：不列
    assert not any("公布（" in w for w in whats)
    assert sum(w.startswith("月度记录") for w in whats) == 2                                      # 10/1、11/2
    assert any(x["date"] == "2026-10-12" and x["what"].startswith("季度复核") for x in it)
    assert all({"date", "what", "check", "who", "src"} <= set(x) for x in it)


def test_milestones_and_report_block():
    near = CK.items(dt.date(2026, 12, 1), events=[], changes=[])
    assert any(x["date"] == "2026-12-24" for x in near) and any(x["date"] == "2026-12-25" for x in near)
    far = CK.upcoming_milestones(dt.date(2026, 12, 26), 2)
    assert [x["date"] for x in far] == ["2027-09-28", "2028-09-28"]
    from qbreak.report_unified import _calendar_html
    h = _calendar_html({"horizon_days": 45, "items": CK.items(dt.date(2026, 9, 28), events=EV, changes=CH),
                        "milestones": CK.upcoming_milestones(dt.date(2026, 9, 28))})
    assert "检查日历" in h and "2026-10-01（四）" in h and "CHECK_TIMELINE.md" in h and "2026-12-24" in h
    assert _calendar_html({"error": "x"}) == ""
