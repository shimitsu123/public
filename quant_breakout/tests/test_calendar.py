"""取引カレンダー测试。祝日算错 = 守护进程在休市日空转或在开市日不工作。"""
import datetime as dt

import pytest

from qbreak.calendar_jp import (JST, holidays, is_market_holiday, is_open,
                                is_trading_day, next_trading_day, prev_trading_day,
                                seconds_until_next_event, session_of)


@pytest.mark.parametrize("d,name", [
    (dt.date(2026, 1, 1), "元日"),
    (dt.date(2026, 1, 12), "成人の日(1月第2月曜)"),
    (dt.date(2026, 2, 11), "建国記念の日"),
    (dt.date(2026, 2, 23), "天皇誕生日"),
    (dt.date(2026, 4, 29), "昭和の日"),
    (dt.date(2026, 5, 3), "憲法記念日"),
    (dt.date(2026, 5, 5), "こどもの日"),
    (dt.date(2026, 8, 11), "山の日"),
    (dt.date(2026, 11, 3), "文化の日"),
    (dt.date(2026, 11, 23), "勤労感謝の日"),
])
def test_known_holidays(d, name):
    assert d in holidays(d.year), name


def test_equinox_2026():
    assert dt.date(2026, 3, 20) in holidays(2026)      # 春分の日
    assert dt.date(2026, 9, 23) in holidays(2026)      # 秋分の日


def test_substitute_holiday():
    """2026-05-03（憲法記念日）は日曜 → 振替休日が発生する。"""
    assert dt.date(2026, 5, 3).weekday() == 6
    assert dt.date(2026, 5, 6) in holidays(2026)


def test_year_end_market_closure():
    for d in [dt.date(2025, 12, 31), dt.date(2026, 1, 2)]:
        assert is_market_holiday(d)


def test_weekends_closed():
    assert is_market_holiday(dt.date(2026, 9, 26))     # 土
    assert is_market_holiday(dt.date(2026, 9, 27))     # 日
    assert is_trading_day(dt.date(2026, 9, 25))        # 金


def test_prev_next_trading_day_skip_holidays():
    assert next_trading_day(dt.date(2026, 9, 25)) == dt.date(2026, 9, 28)
    assert prev_trading_day(dt.date(2026, 9, 28)) == dt.date(2026, 9, 25)
    # 2026-01-01~03 は休場、1/1 の前営業日は 12/30
    assert prev_trading_day(dt.date(2026, 1, 5)) == dt.date(2025, 12, 30)


@pytest.mark.parametrize("hhmm,want", [
    ((8, 30), "pre"), ((9, 0), "morning"), ((11, 30), "morning"),
    ((12, 0), "lunch"), ((12, 30), "afternoon"), ((15, 24), "afternoon"),
    ((15, 25), "closing_auction"), ((15, 30), "closing_auction"), ((16, 0), "post"),
])
def test_session_boundaries(hhmm, want):
    ts = dt.datetime(2026, 9, 24, *hhmm, tzinfo=JST)   # 木曜・平日
    assert session_of(ts) == want


def test_is_open_only_during_sessions():
    assert is_open(dt.datetime(2026, 9, 24, 10, 0, tzinfo=JST))
    assert not is_open(dt.datetime(2026, 9, 24, 12, 0, tzinfo=JST))   # 昼休み
    assert not is_open(dt.datetime(2026, 9, 24, 16, 0, tzinfo=JST))
    assert not is_open(dt.datetime(2026, 9, 27, 10, 0, tzinfo=JST))   # 日曜


def test_sleep_until_next_event_is_bounded():
    # 休市日の深夜 → 次の営業日 9:00 まで一気に寝る（無駄な轮询をしない）
    s = seconds_until_next_event(dt.datetime(2026, 9, 27, 2, 0, tzinfo=JST))
    assert 3600 * 24 < s < 3600 * 40
    # 开市中 → 下一个切换点在数小时内
    s2 = seconds_until_next_event(dt.datetime(2026, 9, 24, 10, 0, tzinfo=JST))
    assert 0 < s2 <= 3600 * 2


def test_naive_datetime_treated_as_jst():
    assert session_of(dt.datetime(2026, 9, 24, 10, 0)) == "morning"
