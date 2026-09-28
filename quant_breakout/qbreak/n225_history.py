"""n225_history.py — 日経225 的历史成员（按年；只用于研究的「近似时点股票池」，不影响交易）。

来源：Wikipedia「日経平均株価」的「構成銘柄除外および採用の歴史」（只有年份；2026-09-28 取得）；只收今天的成员里 2001 年以后才被选进的，
和 2001 年以后被剔除、今天仍上市的旧成员（空运 / 陆运 / 仓储不在研究股票池里，不收）。合并带来的改名 / 换代码按连续成员处理；
进出的那一年两边都不算（member_then → None）。倒闭 / 被收购而退市的旧成员没有行情，仍缺（残余的幸存者偏差）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 今天的成员里 2001 年以后才（非合并）被选进日経225 的：票 → 被选进的年份（Wikipedia「構成銘柄除外および採用の歴史」，2026-09-28 取得）
ADD_YEAR = {"8253.T": 2001, "8233.T": 2001, "1928.T": 2001, "8830.T": 2001, "6367.T": 2001, "8331.T": 2002, "1721.T": 2002, "4704.T": 2002,
            "7733.T": 2002, "3099.T": 2002, "8309.T": 2002, "1963.T": 2003, "9766.T": 2003, "9984.T": 2004, "4324.T": 2004, "2282.T": 2004,
            "4519.T": 2005, "4689.T": 2005, "4183.T": 2005, "9983.T": 2005, "8795.T": 2005, "9602.T": 2006, "3289.T": 2006, "3086.T": 2007,
            "3436.T": 2007, "8354.T": 2008, "6305.T": 2008, "5214.T": 2010, "8804.T": 2010, "6506.T": 2011, "7735.T": 2011, "8750.T": 2011,
            "8304.T": 2011, "6113.T": 2011, "4043.T": 2012, "6988.T": 2013, "2432.T": 2015, "1808.T": 2015, "7272.T": 2016, "4755.T": 2016,
            "4578.T": 2017, "6724.T": 2017, "6098.T": 2017, "6178.T": 2017, "4751.T": 2018, "6645.T": 2019, "7832.T": 2019, "2413.T": 2019,
            "8697.T": 2020, "9434.T": 2020, "3659.T": 2020, "6753.T": 2020, "6861.T": 2021, "6981.T": 2021, "7974.T": 2021, "8591.T": 2022,
            "6594.T": 2022, "7741.T": 2022, "6273.T": 2022, "4661.T": 2023, "6723.T": 2023, "4385.T": 2023, "6920.T": 2023, "9843.T": 2023,
            "3092.T": 2024, "6146.T": 2024, "6526.T": 2024, "4307.T": 2024, "7453.T": 2024, "6532.T": 2025, "6963.T": 2025, "3697.T": 2025,
            "285A.T": 2026, "7532.T": 2026}
OLD_MEMBER_UNTIL = {"6753.T": 2016}                                          # シャープ：2016 年降到二部被剔除，2020 年再选进
# 2001 年以后被剔除、今天仍上市（行情可取）的旧成员：票 → (成员起始年，None = 2000 年以前；剔除年)；空运 / 陆运 / 仓储不在股票池里，不加
REMOVED = {"6310.T": (None, 2001), "1301.T": (None, 2002), "1805.T": (None, 2002), "1885.T": (None, 2003), "6474.T": (None, 2004),
           "7102.T": (None, 2004), "2201.T": (None, 2005), "9605.T": (None, 2006), "2001.T": (None, 2006), "2602.T": (None, 2007),
           "7231.T": (None, 2007), "1861.T": (None, 2008), "4045.T": (None, 2008), "3864.T": (None, 2013), "8803.T": (None, 2015),
           "3110.T": (None, 2015), "4041.T": (None, 2016), "3865.T": (None, 2017), "6508.T": (None, 2017), "5715.T": (None, 2018),
           "6366.T": (None, 2019), "3105.T": (None, 2021), "5901.T": (None, 2021), "9412.T": (2005, 2021), "8303.T": (2005, 2022),
           "3103.T": (None, 2022), "6703.T": (None, 2022), "1333.T": (None, 2022), "3101.T": (None, 2023), "5703.T": (None, 2023),
           "5707.T": (None, 2023), "5202.T": (None, 2023), "7003.T": (None, 2023), "8628.T": (2008, 2023), "2531.T": (None, 2024),
           "5232.T": (None, 2024), "5541.T": (2008, 2024), "3863.T": (None, 2024), "4631.T": (2018, 2024), "7762.T": (None, 2025),
           "6674.T": (None, 2026), "6952.T": (None, 2026)}


def member_then(t: str, year: int) -> bool | None:
    """这只票在 year 年是不是日経225 成员（按年；进出的那一年 → None 不算）。今天的成员：ADD_YEAR / OLD_MEMBER_UNTIL；旧成员：REMOVED。"""
    if t in REMOVED:
        a, b = REMOVED[t]
        if year == b or (a is not None and year == a):
            return None
        return (a is None or year > a) and year < b
    if t in OLD_MEMBER_UNTIL:
        if year < OLD_MEMBER_UNTIL[t]:
            return True
        return None if year in (OLD_MEMBER_UNTIL[t], ADD_YEAR.get(t)) else year > ADD_YEAR.get(t, 9999)
    a = ADD_YEAR.get(t)
    if a is None:
        return True
    return None if year == a else year > a


def pit_names(today: list[str]) -> list[str]:
    """近似时点股票池要取行情的票：今天的成员 + 2001 年以后被剔除的旧成员。"""
    return list(dict.fromkeys(list(today) + sorted(REMOVED)))


def member_mask(fr: dict[str, pd.DataFrame], strict: bool = True) -> dict[str, np.ndarray]:
    """每只票每个交易日：那一年是不是成员（True 才允许开新仓）。strict：进出的那一年（None）当作不是。"""
    out = {}
    for t, df in fr.items():
        yrs = pd.DatetimeIndex(df.index).year
        cache = {y: member_then(t, int(y)) for y in set(yrs)}
        out[t] = np.array([bool(cache[y]) if cache[y] is not None else (not strict) for y in yrs], bool)
    return out
