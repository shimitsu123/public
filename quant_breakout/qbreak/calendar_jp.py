"""calendar_jp.py — 東証の営業日・立会時間（取引カレンダー / trading calendar）。

盘中守护进程必须知道"现在是不是开市"，否则会在休市日、午休、盘后疯狂轮询，
既浪费 API 配额又会把"取不到实时价"误判成故障。

自己算日本の祝日（国民の祝日）而不是依赖第三方库：
  • 固定日 + ハッピーマンデー + 春分/秋分（1980~2099 的近似式）
  • 振替休日（祝日が日曜 → 2006 年以前は翌月曜のみ、2007 年以降は次の祝日でない日）
  • 国民の休日（祝日に挟まれた平日：シルバーウィーク）
  • 按年份用当时的规则（2026-09-28 修正：以前所有年份都用现在的规则 → 2019 年以前的 12/23 天皇誕生日、2016 年以前没有的山の日、
    2000 年以前的成人の日 / 体育の日、2002 年以前的海の日 / 敬老の日、2020 / 2021 奥运年挪动的祝日、2019 年即位的休日都错了；
    scripts/data_audit.py 核对：2016-09〜2026-09 与 J-Quants 的交易日完全一致）
東証休場日 = 土日 + 祝日 + 年末年始（12/31, 1/1~1/3）+ 全日休场日（2020-10-01 系统故障终日停止）

立会時間（2024-11-05 以降）:
  前場 09:00–11:30 / 後場 12:30–15:30（クロージング・オークション 15:25–15:30）
如果交易所再次变更时间，改 SESSIONS 即可。
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# (开始, 结束) 本地时间；後場结束即收盘
SESSIONS: list[tuple[dt.time, dt.time]] = [
    (dt.time(9, 0), dt.time(11, 30)),      # 前場（ぜんば）
    (dt.time(12, 30), dt.time(15, 30)),    # 後場（ごば）2024-11-05 から 15:30 まで
]
CLOSING_AUCTION_START = dt.time(15, 25)    # クロージング・オークション


def _nth_monday(year: int, month: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(7 - d.weekday()) % 7)      # 第1月曜
    return d + dt.timedelta(days=7 * (n - 1))


def _equinox(year: int, spring: bool) -> dt.date:
    """春分/秋分の近似式（1980–2099 で実用上一致）。"""
    base = 20.8431 if spring else 23.2488
    day = int(base + 0.242194 * (year - 1980) - (year - 1980) // 4)
    return dt.date(year, 3 if spring else 9, day)


# 一次性的休日（皇室行事等，按当年的特别法）
SPECIAL_HOLIDAYS = {
    dt.date(1989, 2, 24),     # 昭和天皇の大喪の礼
    dt.date(1990, 11, 12),    # 即位礼正殿の儀
    dt.date(1993, 6, 9),      # 皇太子徳仁親王の結婚の儀
    dt.date(2019, 5, 1),      # 天皇の即位の日（4/30・5/2 は国民の休日）
    dt.date(2019, 10, 22),    # 即位礼正殿の儀
}
# 祝日以外で東証が全日休場した日
TSE_CLOSED = {dt.date(2020, 10, 1)}   # 株式売買システム（arrowhead）の障害で終日売買停止


def _base_holidays(year: int) -> set[dt.date]:
    """该年的「国民の祝日」（不含振替休日・国民の休日）；按年份用当时的规则。"""
    h = {dt.date(year, 1, 1), dt.date(year, 2, 11), _equinox(year, True), dt.date(year, 4, 29),   # 4/29：天皇誕生日→みどりの日→昭和の日
         dt.date(year, 5, 3), dt.date(year, 5, 5), _equinox(year, False), dt.date(year, 11, 3), dt.date(year, 11, 23)}
    h.add(dt.date(year, 1, 15) if year <= 1999 else _nth_monday(year, 1, 2))                  # 成人の日
    if 1989 <= year <= 2018:
        h.add(dt.date(year, 12, 23))                                                          # 天皇誕生日（平成）
    elif year >= 2020:
        h.add(dt.date(year, 2, 23))                                                           # 天皇誕生日（令和；2019 年没有）
    if year >= 2007:
        h.add(dt.date(year, 5, 4))                                                            # みどりの日（以前は国民の休日）
    if year == 2020:
        h |= {dt.date(2020, 7, 23), dt.date(2020, 7, 24), dt.date(2020, 8, 10)}              # 海の日・スポーツの日・山の日（五輪特措法）
    elif year == 2021:
        h |= {dt.date(2021, 7, 22), dt.date(2021, 7, 23), dt.date(2021, 8, 8)}               # 同上（8/8 は日曜 → 8/9 振替）
    else:
        if year >= 2003:
            h.add(_nth_monday(year, 7, 3))                                                    # 海の日
        elif year >= 1996:
            h.add(dt.date(year, 7, 20))
        if year >= 2016:
            h.add(dt.date(year, 8, 11))                                                       # 山の日
        h.add(_nth_monday(year, 10, 2) if year >= 2000 else dt.date(year, 10, 10))            # 体育の日 / スポーツの日
    h.add(dt.date(year, 9, 15) if year <= 2002 else _nth_monday(year, 9, 3))                  # 敬老の日
    return h | {d for d in SPECIAL_HOLIDAYS if d.year == year}


@lru_cache(maxsize=256)
def holidays(year: int) -> frozenset[dt.date]:
    """該当年の休日（国民の祝日 + 国民の休日 + 振替休日）。"""
    base = _base_holidays(year) | _base_holidays(year - 1) | _base_holidays(year + 1)          # 年末年始をまたぐ判定用
    h = set(base)
    # 国民の休日：前日と翌日が国民の祝日である平日（例 敬老の日と秋分の日の間、1988〜2006 の 5/4、2019 の 4/30・5/2）
    for d in sorted(base):
        mid = d + dt.timedelta(days=1)
        if d + dt.timedelta(days=2) in base and mid not in base and mid.weekday() != 6:
            h.add(mid)
    # 振替休日：国民の祝日が日曜 → 2006 年以前は翌日、2007 年以降は次の「休日でない日」
    for d in sorted(base):
        if d.weekday() != 6:
            continue
        nxt = d + dt.timedelta(days=1)
        if d.year >= 2007:
            while nxt in h:
                nxt += dt.timedelta(days=1)
        h.add(nxt)
    return frozenset(x for x in h if x.year == year)


def is_market_holiday(d: dt.date) -> bool:
    """東証休場日か。土日 + 祝日 + 年末年始。"""
    if d.weekday() >= 5:
        return True
    if (d.month, d.day) in ((12, 31), (1, 1), (1, 2), (1, 3)):
        return True
    return d in holidays(d.year) or d in TSE_CLOSED


def is_trading_day(d: dt.date) -> bool:
    return not is_market_holiday(d)


def prev_trading_day(d: dt.date) -> dt.date:
    x = d - dt.timedelta(days=1)
    while is_market_holiday(x):
        x -= dt.timedelta(days=1)
    return x


def next_trading_day(d: dt.date) -> dt.date:
    x = d + dt.timedelta(days=1)
    while is_market_holiday(x):
        x += dt.timedelta(days=1)
    return x


def now_jst() -> dt.datetime:
    return dt.datetime.now(JST)


def session_of(ts: dt.datetime | None = None) -> str:
    """返回 closed / pre / morning / lunch / afternoon / closing_auction / post。
    守护进程按这个状态决定该做什么，而不是硬编码时间。"""
    ts = ts or now_jst()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=JST)
    ts = ts.astimezone(JST)
    if is_market_holiday(ts.date()):
        return "closed"
    t = ts.time()
    if t < SESSIONS[0][0]:
        return "pre"
    if t <= SESSIONS[0][1]:
        return "morning"
    if t < SESSIONS[1][0]:
        return "lunch"
    if t >= CLOSING_AUCTION_START and t <= SESSIONS[1][1]:
        return "closing_auction"
    if t <= SESSIONS[1][1]:
        return "afternoon"
    return "post"


def is_open(ts: dt.datetime | None = None) -> bool:
    return session_of(ts) in ("morning", "afternoon", "closing_auction")


def seconds_until_next_event(ts: dt.datetime | None = None) -> float:
    """距离下一个状态切换点还有多少秒 —— 守护进程用它决定睡多久，
    而不是无脑 sleep(60)。休市时直接睡到下一个交易日 9:00。"""
    ts = (ts or now_jst()).astimezone(JST)
    today = ts.date()
    marks: list[dt.datetime] = []
    if is_trading_day(today):
        for a, b in SESSIONS:
            marks += [dt.datetime.combine(today, a, JST), dt.datetime.combine(today, b, JST)]
        marks.append(dt.datetime.combine(today, CLOSING_AUCTION_START, JST))
    nd = next_trading_day(today)
    marks.append(dt.datetime.combine(nd, SESSIONS[0][0], JST))
    future = [m for m in sorted(marks) if m > ts]
    return max((future[0] - ts).total_seconds(), 1.0) if future else 60.0
