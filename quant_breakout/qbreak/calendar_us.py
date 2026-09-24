"""calendar_us.py — NYSE 交易日历（2021–2027 休市日静态表）。
只用于「下一个交易日 / 上一个交易日」判断（事件窗口、T+1 成交日）；不含半日市。"""
from __future__ import annotations

import datetime as dt

# 来源：NYSE 公布的年度休市日（元旦、MLK、总统日、耶稣受难日、阵亡将士纪念日、六月节、独立日、劳动节、感恩节、圣诞节；
# 遇周末按 NYSE 规则顺延/提前；2025-01-09 为卡特前总统国葬休市）
_HOLIDAYS = {
    2021: ["01-01", "01-18", "02-15", "04-02", "05-31", "07-05", "09-06", "11-25", "12-24"],
    2022: ["01-17", "02-21", "04-15", "05-30", "06-20", "07-04", "09-05", "11-24", "12-26"],
    2023: ["01-02", "01-16", "02-20", "04-07", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"],
    2024: ["01-01", "01-15", "02-19", "03-29", "05-27", "06-19", "07-04", "09-02", "11-28", "12-25"],
    2025: ["01-01", "01-09", "01-20", "02-17", "04-18", "05-26", "06-19", "07-04", "09-01", "11-27", "12-25"],
    2026: ["01-01", "01-19", "02-16", "04-03", "05-25", "06-19", "07-03", "09-07", "11-26", "12-25"],
    2027: ["01-01", "01-18", "02-15", "03-26", "05-31", "06-18", "07-05", "09-06", "11-25", "12-24"],
}


def holidays(year: int) -> set[dt.date]:
    return {dt.date.fromisoformat(f"{year}-{md}") for md in _HOLIDAYS.get(year, [])}


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
