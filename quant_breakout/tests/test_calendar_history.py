"""qbreak/calendar_jp.py 的历年规则（2026-09-28 数据核对修正：以前只按今天的祝日法算，历年的研究用错了几十天）。

历年规则：成人の日 1999 年以前 1/15；天皇誕生日 1989〜2018 是 12/23、2019 年没有、2020 年起 2/23；海の日 1996〜2002 是 7/20；
山の日 2016 年起；体育の日 1999 年以前 10/10；敬老の日 2002 年以前 9/15；みどりの日（5/4）2007 年起；
2020 / 2021 年奥运特例；即位 / 大喪等特别休日；振替休日 2007 年起顺延到下一个非祝日；东证全日停止（2020-10-01）。
另：validate_ohlcv 对东证的票去掉休市日的行（Yahoo 的假行），QB_KEEP_HOLIDAY_ROWS=1 保留（重现以前的研究）。
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from qbreak.calendar_jp import holidays, is_market_holiday, is_trading_day
from qbreak.config import DataConfig
from qbreak.data import drop_jp_holiday_rows, validate_ohlcv

D = dt.date


@pytest.mark.parametrize("d,why", [
    (D(1989, 2, 24), "大喪の礼"), (D(1990, 11, 12), "即位礼正殿の儀"), (D(1993, 6, 9), "皇太子結婚の儀"),
    (D(1999, 1, 15), "成人の日（1999 年以前 1/15）"), (D(2000, 1, 10), "成人の日（2000 年起 1 月第 2 月曜）"),
    (D(1999, 10, 11), "体育の日 10/10 是周日 → 振替"), (D(2000, 10, 9), "体育の日（2000 年起 10 月第 2 月曜）"),
    (D(2001, 7, 20), "海の日（1996〜2002 是 7/20）"), (D(2003, 7, 21), "海の日（2003 年起 7 月第 3 月曜）"),
    (D(2001, 12, 24), "天皇誕生日 12/23 是周日 → 振替（2007 年以前也有振替）"),
    (D(2002, 9, 16), "敬老の日 9/15 是周日 → 振替"), (D(2003, 9, 15), "敬老の日（2003 年起 9 月第 3 月曜）"),
    (D(2008, 5, 6), "5/4（みどりの日）是周日 → 2007 年起振替顺延到 5/6"),
    (D(2009, 9, 22), "国民の休日（敬老の日与秋分の日之间）"), (D(2015, 9, 22), "国民の休日"),
    (D(2016, 8, 11), "山の日（2016 年起）"), (D(2016, 12, 23), "天皇誕生日（1989〜2018 是 12/23）"),
    (D(2018, 12, 24), "天皇誕生日 12/23 是周日 → 振替"),
    (D(2019, 4, 30), "国民の休日（昭和の日与即位の日之间）"), (D(2019, 5, 1), "即位の日"), (D(2019, 5, 2), "国民の休日"),
    (D(2019, 10, 22), "即位礼正殿の儀"), (D(2020, 2, 24), "天皇誕生日 2/23 是周日 → 振替（2020 年起 2/23）"),
    (D(2020, 7, 23), "2020 奥运特例：海の日"), (D(2020, 7, 24), "2020 奥运特例：スポーツの日"), (D(2020, 8, 10), "2020 奥运特例：山の日"),
    (D(2021, 7, 22), "2021 奥运特例：海の日"), (D(2021, 7, 23), "2021 奥运特例：スポーツの日"),
    (D(2021, 8, 9), "2021 奥运特例：山の日 8/8 是周日 → 振替"),
])
def test_historical_holidays(d, why):
    assert d in holidays(d.year), why
    assert is_market_holiday(d) and not is_trading_day(d), why


@pytest.mark.parametrize("d,why", [
    (D(1995, 7, 20), "海の日 1996 年起"), (D(2006, 2, 23), "天皇誕生日 2/23 是 2020 年起"), (D(2015, 8, 11), "山の日 2016 年起"),
    (D(2019, 12, 23), "2019 年没有天皇誕生日"), (D(2020, 7, 20), "2020 年海の日移到 7/23"), (D(2020, 10, 12), "2020 年スポーツの日移到 7/24"),
    (D(2021, 7, 19), "2021 年海の日移到 7/22"), (D(2021, 10, 11), "2021 年スポーツの日移到 7/23"), (D(2021, 8, 11), "2021 年山の日移到 8/8"),
    (D(2000, 1, 14), "2000 年起成人の日是第 2 月曜（1/10）"), (D(2002, 7, 22), "2002 年海の日还是 7/20（周六）"),
])
def test_historical_trading_days(d, why):
    assert d not in holidays(d.year), why
    assert is_trading_day(d), why


def test_tse_full_day_outage_is_closed_but_not_a_holiday():
    d = D(2020, 10, 1)                                                           # 东证系统故障，全天停止交易
    assert d not in holidays(2020) and is_market_holiday(d) and not is_trading_day(d)


def test_trading_day_count_matches_jquants_2017_2025():
    """每年的交易日数 = J-Quants 实际有成交的天数（2026-09-28 核对，2016-09〜2026-09 逐日一致；2020 年不含 10/1 停止）。"""
    want = {2017: 247, 2018: 245, 2019: 241, 2020: 242, 2021: 245, 2022: 244, 2023: 246, 2024: 245, 2025: 243}
    got = {y: sum(is_trading_day(D(y, 1, 1) + dt.timedelta(days=i)) for i in range(366) if (D(y, 1, 1) + dt.timedelta(days=i)).year == y)
           for y in want}
    assert got == want


def _bars(days):
    idx = pd.DatetimeIndex(days)
    k = len(idx)
    return pd.DataFrame({"Open": np.full(k, 100.0), "High": np.full(k, 101.0), "Low": np.full(k, 99.0),
                         "Close": np.full(k, 100.0), "Volume": np.full(k, 1000.0)}, index=idx)


def test_drop_jp_holiday_rows_and_env_toggle(monkeypatch):
    df = _bars(["2019-04-26", "2019-04-30", "2019-05-01", "2019-05-07", "2020-10-01", "2020-10-02"])
    out = drop_jp_holiday_rows("7203.T", df)
    assert [str(x.date()) for x in out.index] == ["2019-04-26", "2019-05-07", "2020-10-02"]
    monkeypatch.setenv("QB_KEEP_HOLIDAY_ROWS", "1")
    assert len(drop_jp_holiday_rows("7203.T", df)) == 6


def test_validate_ohlcv_drops_holiday_rows_only_for_tse_tickers():
    days = [d for d in pd.bdate_range("2018-12-03", "2019-12-27")]           # 平日，包括 12/24 振替、GW、10/22 等休市日
    cfg = DataConfig(min_bars=100)
    jp = validate_ohlcv("7203.T", _bars(days), cfg)
    us = validate_ohlcv("AAPL", _bars(days), cfg)
    assert len(us) == len(days)
    assert all(is_trading_day(x.date()) for x in jp.index)
    assert pd.Timestamp("2018-12-24") not in jp.index and pd.Timestamp("2019-10-22") not in jp.index
    assert len(jp) == sum(is_trading_day(x.date()) for x in days)
