"""deepdip_forward.py — 「≤ −15% 深跌」的前向记录（2026-09-29 登记；用户「把 ≤ −15% 深跌做成前向记录」；只记录、只展示，不影响交易）。

依据（scripts/crash_mainline_posthoc.py，事后描述；登记的研究 crash_mainline_study a28290b 没有通过）：
  日経225 13 周线乖离第一次 ≤ −15%（回到线之上才算新的一段）→ 下一个交易日收盘买，之后 60 个交易日比同一时期全部交易日的平均多
  1965〜2000 +3.11%（9 段，涨的比例 78%）、2001〜2026 +4.64%（8 段，75%）；美国市场（门槛按波动 × 0.80 = −12.0%）+1.28%（34 段，71%）。
  三段都为正，但段数少、95% 区间都含 0；买进之后 60 天内平均还要再跌 6〜10%。这里只用以后的真实数据慢慢核对。

一 事件（事先写定）
  JP（主）：日経225（^N225）每天收盘 ÷ 13 周线 − 1 ≤ −15% 第一次成立的那天；13 周线 = 完成日 ≤ 那天的最近一根周线（qbreak/mtf.bars：
    ISO 周，这一周最后一个交易日收盘完成；数据里最后一周后面还没有交易日 → 不算完成）的 13 根周收盘平均；乖离回到 ≥ 0 才算新的一段。
  US（对照，让事件攒得快一点）：S&P 500（^GSPC）同一规则，门槛 −12.0%。
  sim-day 每天用近 11 年以上的行情重算：事件日 ≥ 开始日、且这一段还没记过的才追加（同一段只留最早记下的那个；漏跑的日子下次补上，
  事件日由行情决定、与哪天记下无关，logged_on 照实写）。行情用收完盘的 K 线（盘中运行时去掉当天未收盘的 K 线）。
  数据最后一天不判：那天的 13 周线还没定（要等下一个交易日才知道这一周是否已完，例如周五的值要等下周一的行情），
  所以事件一般晚一个交易日记下，事件日不变；日报「现在」一栏显示的最后一天的乖离是暂定值。
二 记录（var/out/deepdip_forward.csv，只追加、不改不补写）：logged_on, market, event_date, dev（%）, close, line, base60（%）, breadth（%）
  base60 = 事件日之前 10 年里每个交易日「下一个交易日收盘买、拿 60 个交易日」的平均涨跌（只用事件日之前已经结束的持有期）；
  breadth（只 JP、只描述）= 那天日経225 成分里 13 周线乖离 ≤ −15% 的比例（sim-day 已载入的成分行情；有值 < 50 只 → 空）。
  2026-10-01 起记。
三 结果（每次运行按记录重算，只读记录）：事件日下一个交易日收盘买 → 之后 20 / 60 / 120 个交易日的涨跌、60 天内最低（买后还跌多少）、
  60 日超额 = 60 日涨跌 − base60。
四 判定（事先写定）：JP 满 5 个事件且都过了 60 个交易日起，每次运行都判：60 日超额平均 > 0 且 60 日涨的比例 ≥ 60% →「前向成立」
  （只升级日报标签；要用到交易，另外登记组合检验、要你确认）；平均 ≤ 0 →「前向不成立」（日报不再标历史参考）；其余「未定」。
  JP + US 合并满 10 个时另报同样的统计（只描述）。预期很慢：历史上日本约 3〜4 年一次、美国约 3 年一次。
五 追加对照（2026-09-29，登记 1c55865 之后、开始日之前，前向还没有任何记录；用户「加 DAX 和 FTSE 100 作对照」）：
  DE：德国 DAX（^GDAXI）门槛 −14.0%；UK：英国 FTSE 100（^FTSE）门槛 −11.2%。与美国同一原则按波动折算：两边都有数据的全部年份
  （DAX 1988〜2026、FTSE 1984〜2026）的日对数收益标准差 ÷ 日経225 同期的 × −15%（k = 0.935 / 0.749）。事件、记录、结果与美国相同
  （对照，只描述）；还没收盘的当天 K 线按当地时间去掉（Xetra 17:45、LSE 16:45 之前算没收盘；JP / US 照旧用交易代码里的函数）。
  JP 的判定不变；四里「JP + US 合并」改为「JP + 对照（US / DE / UK）合并」满 10 个另报（只描述），同时报独立的大跌段数
  （按日期排序，与前一个事件相距 ≤ 90 个日历日的算同一段：同一次全球大跌会在几个市场各记一个事件）。
  欧洲两个指数的历史只看一次：scripts/deepdip_intl_check.py（同一提交登记）。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import mtf

FORWARD_START = "2026-10-01"
LOG_FILE = "deepdip_forward.csv"
COLS = ["logged_on", "market", "event_date", "dev", "close", "line", "base60", "breadth"]
MARKETS = {"JP": {"symbol": "^N225", "thr": -15.0, "session": "JP", "name": "日経225"},
           "US": {"symbol": "^GSPC", "thr": -12.0, "session": "US", "name": "S&P 500"},
           "DE": {"symbol": "^GDAXI", "thr": -14.0, "session": "DE", "name": "DAX"},          # 五：2026-09-29 追加的对照
           "UK": {"symbol": "^FTSE", "thr": -11.2, "session": "UK", "name": "FTSE 100"}}
LINE_N, STK_DEV, MIN_BREADTH_N = 13, -15.0, 50
HORIZONS, H_MAIN, BASE_YEARS = (20, 60, 120), 60, 10
JUDGE_N, POOL_N, WIN_SHARE = 5, 10, 60.0
ACTIVE_DAYS = 120
EPISODE_GAP = 90                                                             # 各市场事件日相距 ≤ 90 个日历日 → 同一次大跌
EU_CLOSE = {"DE": ("Europe/Berlin", 17, 45), "UK": ("Europe/London", 16, 45)}   # Xetra 17:30 / LSE 16:30 收盘（含收盘竞价）后 15 分钟
HIST = {"JP": "日経225 1965〜2000 +3.11%（9 段）、2001〜2026 +4.64%（8 段）",       # 历史参考（只作展示；事后描述）
        "US": "美国（−12%）1926〜2026 +1.28%（34 段）",
        "DE": "DAX（−14%）见 var/out/deepdip_intl_check.md",
        "UK": "FTSE 100（−11.2%）见 var/out/deepdip_intl_check.md"}


def weekly_line(close: pd.Series, days=None, n: int = LINE_N) -> pd.Series:
    """每天的 13 周线（与 scripts/crash_mainline_study.py 同一定义）。days = 市场日历（缺省 = close 的日期）。"""
    c = close.dropna()
    cal = pd.DatetimeIndex(c.index if days is None else days)
    raw = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 0.0}, index=c.index)
    b = mtf.bars(raw, cal, "W")
    ma = b["Close"].astype(float).rolling(n, min_periods=n).mean()
    return mtf.state_on(ma.to_frame("m"), pd.DatetimeIndex(c.index))["m"]


def line_dev(close: pd.Series, days=None, n: int = LINE_N) -> pd.Series:
    """收盘 ÷ 13 周线 − 1（%）。"""
    c = close.dropna()
    return (c / weekly_line(c, days, n) - 1) * 100


def first_cross(cond: np.ndarray, rearm: np.ndarray) -> np.ndarray:
    """同一段只算第一次：cond 第一次成立的那天；之后 rearm 成立才算新的一段。"""
    armed, out = True, []
    for i in range(len(cond)):
        if rearm[i]:
            armed = True
        if armed and cond[i]:
            out.append(i)
            armed = False
    return np.asarray(out, int)


def events(dev: pd.Series, thr: float) -> pd.DatetimeIndex:
    v = dev.to_numpy(float)
    with np.errstate(invalid="ignore"):
        return dev.index[first_cross(v <= thr, v >= 0)]


def episode_ids(dev: pd.Series) -> pd.Series:
    """每天属于第几段（乖离 ≥ 0 的日子段号 +1）：同一段里只记一个事件。"""
    v = dev.to_numpy(float)
    with np.errstate(invalid="ignore"):
        return pd.Series(np.cumsum(v >= 0), index=dev.index)


def _entry(c: pd.Series, date) -> int:
    """事件日之后第一个交易日（买入日）的位置。"""
    return int(c.index.searchsorted(pd.Timestamp(date), side="right"))


def fwd(close: pd.Series, date, h: int) -> float | None:
    """事件日的下一个交易日收盘买、拿 h 个交易日的涨跌（%）；还没到 → None。"""
    c = close.dropna()
    i = _entry(c, date)
    if i + h >= len(c):
        return None
    return round(float((c.iloc[i + h] / c.iloc[i] - 1) * 100), 2)


def mae(close: pd.Series, date, h: int = H_MAIN) -> tuple[float | None, bool]:
    """买入之后 h 个交易日里最低收盘 ÷ 买入价 − 1（%）；没满 h 天 → 到现在为止的最低，第二个值 = 是否已满。"""
    c = close.dropna()
    i = _entry(c, date)
    if i >= len(c):
        return None, False
    seg = c.iloc[i:i + h + 1]
    return round(float((seg.min() / c.iloc[i] - 1) * 100), 2), i + h < len(c)


def base60(close: pd.Series, date, years: int = BASE_YEARS, h: int = H_MAIN) -> float | None:
    """事件日之前 years 年里每天「下一个交易日收盘买、拿 h 天」的平均涨跌（%），只用事件日之前已经结束的持有期；不够 250 个 → None。"""
    c = close.dropna()
    d = pd.Timestamp(date)
    e = int(c.index.searchsorted(d, side="right")) - 1
    lo = int(c.index.searchsorted(d - pd.DateOffset(years=years), side="left"))
    ks = np.arange(lo, e - h - 1)                                            # 持有期 k + 1 … k + 1 + h ≤ e − 1（事件日之前已经结束）
    if len(ks) < 250:
        return None
    a = c.to_numpy(float)
    return round(float(np.nanmean(a[ks + 1 + h] / a[ks + 1] - 1) * 100), 3)


def breadth_at(members: dict[str, pd.Series] | None, date, thr: float = STK_DEV, min_n: int = MIN_BREADTH_N) -> float | None:
    """那天成分里 13 周线乖离 ≤ thr 的比例（%；每只票用自己的交易日定周线）；有值的 < min_n 只 → None。"""
    d = pd.Timestamp(date)
    vals = []
    for s in (members or {}).values():
        s = s.dropna()
        if d not in s.index or len(s) < 5 * LINE_N + 5:
            continue
        v = line_dev(s).get(d)
        if v is not None and np.isfinite(v):
            vals.append(float(v))
    return round(float(np.mean(np.array(vals) <= thr) * 100), 1) if len(vals) >= min_n else None


def drop_partial(df: pd.DataFrame, session: str, now=None) -> pd.DataFrame:
    """去掉还没收盘的当天 K 线：JP / US 用交易代码里同一个函数；DE / UK 按当地时间收盘后 15 分钟之前算没收盘。"""
    if session in ("JP", "US"):
        from .trader import drop_partial_bar
        return drop_partial_bar(df, session, now)
    if df is None or not len(df):
        return df
    import datetime as dt
    from zoneinfo import ZoneInfo
    tz, hh, mm = EU_CLOSE[session]
    n = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(tz))
    return df.iloc[:-1] if df.index[-1].date() == n.date() and n.time() < dt.time(hh, mm) else df


def episode_labels(dates, gap_days: int = EPISODE_GAP) -> list[int]:
    """同一次大跌（跨市场）编同一个号：按日期排序，与前一个事件相距 ≤ gap_days 个日历日的并进同一段；返回与输入同顺序的段号。"""
    ts = [pd.Timestamp(d) for d in dates]
    order = sorted(range(len(ts)), key=lambda i: ts[i])
    lab, cur = [0] * len(ts), -1
    for j, i in enumerate(order):
        if j == 0 or (ts[i] - ts[order[j - 1]]).days > gap_days:
            cur += 1
        lab[i] = cur
    return lab


def load_log(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(path, dtype={"market": str, "event_date": str, "logged_on": str})


def append(path: Path, rows: list[dict]) -> int:
    """只追加；同一个 (market, event_date) 已经有了就不写。返回新增行数。"""
    if not rows:
        return 0
    old = load_log(path)
    seen = set(zip(old["market"], old["event_date"]))
    new = pd.DataFrame([r for r in rows if (r["market"], r["event_date"]) not in seen], columns=COLS)
    if new.empty:
        return 0
    out = pd.concat([old, new], ignore_index=True) if len(old) else new
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return int(len(new))


def detect_new(close: pd.Series, thr: float, logged: pd.DataFrame, market: str, start: str = FORWARD_START) -> list[pd.Timestamp]:
    """事件日 ≥ start、且所在的那一段还没有记过的事件；数据最后一天不判（那天的 13 周线要等下一个交易日才定）。"""
    c = close.dropna()
    dev = line_dev(c)
    ep = episode_ids(dev)
    have: set[int] = set()
    if len(logged):
        ds = pd.to_datetime(logged.loc[logged["market"] == market, "event_date"])
        if len(ds):
            have = set(ep.reindex(pd.DatetimeIndex(ds), method="ffill").dropna().astype(int))
    return [d for d in events(dev.iloc[:-1], thr) if d >= pd.Timestamp(start) and int(ep.loc[d]) not in have]


def years_needed(path: Path, today: str) -> int:
    """要载入几年行情：新事件的 base60 要事件日之前 10 年（→ 11 年）；已记事件的结果要从最早的事件日起。"""
    log = load_log(path)
    if not len(log):
        return BASE_YEARS + 1
    first = pd.to_datetime(log["event_date"]).min()
    return max(BASE_YEARS + 1, math.ceil((pd.Timestamp(today) - first).days / 365.25) + 1)


def judge(done: list[dict], need: int = JUDGE_N) -> dict:
    """done = 已满 60 个交易日的事件（x60、r60 都有值）。"""
    n = len(done)
    if n < need:
        return {"n": n, "label": f"记录中（满 {need} 个且都过了 60 个交易日才判定）"}
    x = np.array([d["x60"] for d in done], float)
    win = float((np.array([d["r60"] for d in done], float) > 0).mean() * 100)
    label = "前向成立" if (x.mean() > 0 and win >= WIN_SHARE) else ("前向不成立" if x.mean() <= 0 else "未定")
    return {"n": n, "mean": round(float(x.mean()), 2), "win": round(win, 1), "label": label}


def review(log: pd.DataFrame, closes: dict[str, pd.Series]) -> dict:
    """每个记下的事件：之后 20 / 60 / 120 天的涨跌、60 天内最低、60 日超额；JP 的判定与 JP + 对照合并（只描述，另报独立的大跌段数）。"""
    rows = []
    for _, r in log.iterrows():
        c = closes.get(r["market"])
        if c is None or not len(c.dropna()):
            continue
        c = c.dropna()
        out = {"market": r["market"], "event_date": r["event_date"], "dev": r["dev"],
               "breadth": None if pd.isna(r.get("breadth")) else float(r["breadth"]),
               "base60": None if pd.isna(r.get("base60")) else float(r["base60"])}
        for h in HORIZONS:
            out[f"r{h}"] = fwd(c, r["event_date"], h)
        out["mae60"], out["mae_done"] = mae(c, r["event_date"])
        out["days"] = max(0, len(c) - 1 - _entry(c, r["event_date"]))
        out["x60"] = round(out["r60"] - out["base60"], 2) if out["r60"] is not None and out["base60"] is not None else None
        rows.append(out)
    done = [x for x in rows if x["x60"] is not None]
    pool = judge(done, POOL_N)
    pool["episodes"] = len(set(episode_labels([x["event_date"] for x in done])))
    return {"events": rows, "jp": judge([x for x in done if x["market"] == "JP"]),
            "pool": {**pool, "label": "只描述：" + pool["label"]}}


def status_of(close: pd.Series, spec: dict) -> dict:
    """现在的位置：最后一天的 13 周线乖离（暂定值）与离触发线还差多少。"""
    dv = line_dev(close.dropna()).dropna()
    return {"name": spec["name"], "date": str(dv.index[-1].date()), "dev": round(float(dv.iloc[-1]), 2), "thr": spec["thr"],
            "gap_pp": round(float(dv.iloc[-1] - spec["thr"]), 2)}


def run_day(path: Path, closes: dict[str, pd.Series], members: dict[str, pd.Series] | None, today: str) -> dict:
    """sim-day 调用：记新事件（只追加）→ 现在的位置 → 已记事件的结果与判定（日报用）。"""
    added = 0
    status = {}
    for mk, spec in MARKETS.items():
        c = closes.get(mk)
        if c is None or not len(c.dropna()):
            status[mk] = {"error": "没有行情"}
            continue
        c = c.dropna()
        if str(today) >= FORWARD_START:
            log = load_log(path)
            dev, ln = line_dev(c), weekly_line(c)
            rows = [{"logged_on": str(today), "market": mk, "event_date": str(d.date()), "dev": round(float(dev.loc[d]), 2),
                     "close": round(float(c.loc[d]), 2), "line": round(float(ln.loc[d]), 2), "base60": base60(c, d),
                     "breadth": breadth_at(members, d) if mk == "JP" else None}
                    for d in detect_new(c, spec["thr"], log, mk)]
            added += append(path, rows)
        status[mk] = status_of(c, spec)
    log = load_log(path)
    rev = review(log, closes)
    active = [e for e in rev["events"] if e["days"] <= ACTIVE_DAYS]
    return {"start": FORWARD_START, "added": added, "n": int(len(log)), "status": status, "review": rev, "active": active}
