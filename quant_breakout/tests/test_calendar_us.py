"""NYSE 交易日历（qbreak/calendar_us.py，2026-09-29 改成规则计算）：与 NYSE 公布的 2021–2027 休市日完全一致；
补休规则（周六 → 周五、周日 → 周一；元旦周六不补）、复活节、MLK（1998 起）、六月节（2022 起）、临时休市；2028 年以后也有。
另：scripts/data_audit.py 对 ^GSPC 2005〜2026 的交易日逐日核对（开发时 1995〜2026 共 8,280 个工作日 0 天不一致）。"""
import datetime as dt

import pytest

from qbreak import calendar_us as U


@pytest.mark.parametrize("year", sorted(U.PUBLISHED_2021_2027))
def test_rules_match_published_nyse_holidays(year):
    pub = {dt.date.fromisoformat(f"{year}-{md}") for md in U.PUBLISHED_2021_2027[year]}
    assert set(U.holidays(year)) == pub


def test_easter_and_observed_rules():
    assert [U._easter(y) for y in (2008, 2019, 2024, 2025, 2027, 2038)] == [
        dt.date(2008, 3, 23), dt.date(2019, 4, 21), dt.date(2024, 3, 31), dt.date(2025, 4, 20), dt.date(2027, 3, 28), dt.date(2038, 4, 25)]
    assert not U.is_trading_day(dt.date(2027, 12, 24))                      # 圣诞节是周六 → 周五休
    assert U.is_trading_day(dt.date(2021, 12, 31))                           # 2022 元旦是周六：前一年 12/31 照常开市
    assert not U.is_trading_day(dt.date(2023, 1, 2))                         # 元旦是周日 → 周一休
    assert U.is_trading_day(dt.date(1997, 1, 20))                            # MLK 1998 年起才休市
    assert not U.is_trading_day(dt.date(1998, 1, 19))
    assert U.is_trading_day(dt.date(2021, 6, 18))                            # 六月节 2022 年起
    assert not U.is_trading_day(dt.date(2022, 6, 20))


def test_special_closures_and_future_years():
    for d in (dt.date(2001, 9, 11), dt.date(2001, 9, 14), dt.date(2012, 10, 29), dt.date(2018, 12, 5), dt.date(2025, 1, 9)):
        assert not U.is_trading_day(d)
    assert U.next_trading_day(dt.date(2001, 9, 10)) == dt.date(2001, 9, 17)
    # 以前的静态表只到 2027：2028 年的感恩节、独立日（周二）都要是休市
    assert not U.is_trading_day(dt.date(2028, 11, 23)) and not U.is_trading_day(dt.date(2028, 7, 4))
    assert U.prev_trading_day(dt.date(2028, 11, 24)) == dt.date(2028, 11, 22)
    assert len(U.holidays(2030)) == 10
