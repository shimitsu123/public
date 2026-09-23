"""calendar_jp.py — 東証の営業日・立会時間（取引カレンダー / trading calendar）。

盘中守护进程必须知道"现在是不是开市"，否则会在休市日、午休、盘后疯狂轮询，
既浪费 API 配额又会把"取不到实时价"误判成故障。

自己算日本の祝日（国民の祝日）而不是依赖第三方库：
  • 固定日 + ハッピーマンデー + 春分/秋分（1980~2099 的近似式）
  • 振替休日（祝日が日曜 → 翌平日）
  • 国民の休日（祝日に挟まれた平日：シルバーウィーク）
東証休場日 = 土日 + 祝日 + 年末年始（12/31, 1/1~1/3）

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


@lru_cache(maxsize=256)
def holidays(year: int) -> frozenset[dt.date]:
    """該当年の国民の祝日（振替休日・国民の休日を含む）。"""
    h: set[dt.date] = {
        dt.date(year, 1, 1),                       # 元日
        _nth_monday(year, 1, 2),                   # 成人の日
        dt.date(year, 2, 11),                      # 建国記念の日
        dt.date(year, 2, 23),                      # 天皇誕生日（2020年～）
        _equinox(year, True),                      # 春分の日
        dt.date(year, 4, 29),                      # 昭和の日
        dt.date(year, 5, 3),                       # 憲法記念日
        dt.date(year, 5, 4),                       # みどりの日
        dt.date(year, 5, 5),                       # こどもの日
        _nth_monday(year, 7, 3),                   # 海の日
        dt.date(year, 8, 11),                      # 山の日
        _nth_monday(year, 9, 3),                   # 敬老の日
        _equinox(year, False),                     # 秋分の日
        _nth_monday(year, 10, 2),                  # スポーツの日
        dt.date(year, 11, 3),                      # 文化の日
        dt.date(year, 11, 23),                     # 勤労感謝の日
    }
    # 振替休日：祝日が日曜 → 次の平日まで送る
    for d in sorted(h):
        if d.weekday() == 6:
            nxt = d + dt.timedelta(days=1)
            while nxt in h:
                nxt += dt.timedelta(days=1)
            h.add(nxt)
    # 国民の休日：前後を祝日に挟まれた平日（例 敬老の日と秋分の日の間）
    for d in sorted(h):
        cand = d + dt.timedelta(days=2)
        mid = d + dt.timedelta(days=1)
        if cand in h and mid not in h and mid.weekday() < 5:
            h.add(mid)
    return frozenset(h)


def is_market_holiday(d: dt.date) -> bool:
    """東証休場日か。土日 + 祝日 + 年末年始。"""
    if d.weekday() >= 5:
        return True
    if (d.month, d.day) in ((12, 31), (1, 1), (1, 2), (1, 3)):
        return True
    return d in holidays(d.year)


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
