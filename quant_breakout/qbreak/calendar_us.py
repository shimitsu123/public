"""calendar_us.py — NYSE 交易日历（规则计算，任何年份都有；不含半日市）。
只用于「下一个交易日 / 上一个交易日」判断（事件窗口、T+1 成交日、决算前 N 个交易日）。

2026-09-29 改成按规则计算（以前是 2021–2027 的静态表：2028 年起、2020 年以前都会把美国假日当成交易日）：
  元旦（周六 → 不补休；周日 → 次周一）、MLK 日（1 月第 3 个周一，1998 起）、总统日（2 月第 3 个周一）、耶稣受难日（复活节前的周五）、
  阵亡将士纪念日（5 月最后一个周一）、六月节（6/19，2022 起）、独立日（7/4）、劳动节（9 月第 1 个周一）、
  感恩节（11 月第 4 个周四）、圣诞节（12/25）；六月节 / 独立日 / 圣诞节 周六 → 前一个周五、周日 → 次周一。
  另加临时休市（SPECIAL_CLOSED）。核对：与 NYSE 公布的 2021–2027 休市日完全一致（PUBLISHED_2021_2027），
  与 ^GSPC 2000〜2026 的 K 线日期一致（tests/test_calendar_us.py）。
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

# NYSE 公布的年度休市日（2026-09 以前的静态表，留作核对）
PUBLISHED_2021_2027 = {
    2021: ["01-01", "01-18", "02-15", "04-02", "05-31", "07-05", "09-06", "11-25", "12-24"],
    2022: ["01-17", "02-21", "04-15", "05-30", "06-20", "07-04", "09-05", "11-24", "12-26"],
    2023: ["01-02", "01-16", "02-20", "04-07", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"],
    2024: ["01-01", "01-15", "02-19", "03-29", "05-27", "06-19", "07-04", "09-02", "11-28", "12-25"],
    2025: ["01-01", "01-09", "01-20", "02-17", "04-18", "05-26", "06-19", "07-04", "09-01", "11-27", "12-25"],
    2026: ["01-01", "01-19", "02-16", "04-03", "05-25", "06-19", "07-03", "09-07", "11-26", "12-25"],
    2027: ["01-01", "01-18", "02-15", "03-26", "05-31", "06-18", "07-05", "09-06", "11-25", "12-24"],
}

# 规则以外的全日休市（国葬、灾害、9/11）
SPECIAL_CLOSED = {
    dt.date(1994, 4, 27),                                          # 尼克松国葬
    dt.date(2001, 9, 11), dt.date(2001, 9, 12), dt.date(2001, 9, 13), dt.date(2001, 9, 14),   # 9/11
    dt.date(2004, 6, 11),                                          # 里根国葬
    dt.date(2007, 1, 2),                                           # 福特国葬
    dt.date(2012, 10, 29), dt.date(2012, 10, 30),                  # 飓风桑迪
    dt.date(2018, 12, 5),                                          # 老布什国葬
    dt.date(2025, 1, 9),                                           # 卡特国葬
}


def _easter(year: int) -> dt.date:
    """公历复活节（Anonymous Gregorian algorithm）。"""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = (h + ll - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(days=7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: dt.date) -> dt.date:
    """周六 → 前一个周五，周日 → 次周一。"""
    return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d


@lru_cache(maxsize=256)
def holidays(year: int) -> frozenset[dt.date]:
    h = set()
    ny = dt.date(year, 1, 1)
    if ny.weekday() != 5:                                          # 元旦是周六：前一年 12/31 照常开市
        h.add(_observed(ny))
    if year >= 1998:
        h.add(_nth_weekday(year, 1, 0, 3))                         # MLK 日
    h.add(_nth_weekday(year, 2, 0, 3))                             # 总统日
    h.add(_easter(year) - dt.timedelta(days=2))                    # 耶稣受难日
    h.add(_last_weekday(year, 5, 0))                               # 阵亡将士纪念日
    if year >= 2022:
        h.add(_observed(dt.date(year, 6, 19)))                     # 六月节
    h.add(_observed(dt.date(year, 7, 4)))                          # 独立日
    h.add(_nth_weekday(year, 9, 0, 1))                             # 劳动节
    h.add(_nth_weekday(year, 11, 3, 4))                            # 感恩节
    h.add(_observed(dt.date(year, 12, 25)))                        # 圣诞节
    h |= {d for d in SPECIAL_CLOSED if d.year == year}
    return frozenset(x for x in h if x.year == year)


def is_trading_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def next_trading_day(d: dt.date) -> dt.date:
    x = d + dt.timedelta(days=1)
    while not is_trading_day(x):
        x += dt.timedelta(days=1)
    return x


def prev_trading_day(d: dt.date) -> dt.date:
    x = d - dt.timedelta(days=1)
    while not is_trading_day(x):
        x -= dt.timedelta(days=1)
    return x
