"""kline_series.py — 操作面板的 K 线趋势标签（qbreak/kline.trend）按「每个交易日收盘之后面板上看到的样子」整段算出来（向量化）。

研究用（scripts/month_up_dip_study.py「月K 往上走时日K / 周K 往下走：买卖点成功率与收益率」，2026-10-08 登记）；以后面板也可以复用。
只算标签，不算任何收益。不改 qbreak/kline.py，复用它的 ohlcv / bars / trend / SLOPE_BARS。

一 标签（和面板同一个函数、同一口径）：kline.trend，SLOPE_BARS = 3。一个周期的 K 线收盘序列 c：
   MA5 / MA20 = 最近 5 / 20 根收盘的平均（含最后一根）；prev20 = 往前数第 3 根那时的 MA20；slope = (MA20 ÷ prev20 − 1) × 100（prev20 ≤ 0 → 0）。
   上升（面板「往上走」，记 +1）= 最后收盘 > MA20 且 slope > 0 且 MA5 > MA20；下降（「往下走」，记 −1）= 三条都反过来；其余震荡（「横着走」，记 0）。
   K 线不到 23 根没有标签 → NA（int8 存 −128）。「在跌」= 下降；「没在跌」= 上升或震荡；NA 不算「没在跌」。
二 K 线聚合与 kline.bars 相同：日K = 这只票自己的每一行；周K = to_period("W-FRI")；月K = 日历月；每根的收盘 = 这一周 / 月最后一行的收盘；
   整周 / 整月没有行就没有这根 K 线（面板也是这样）。
三 主口径 = 面板口径（as-of）：第 t 行（这只票第 t 个交易日收盘之后）
   D_t = kline.trend(rows[:t+1])；W_t / M_t = kline.trend(kline.bars(rows[:t+1], "W" / "M"))，最后一根是本周 / 本月到 t 为止的部分 K 线（收盘 = c_t）。
   向量化（只用到 t 为止的数据）：g = t 所在周期的序号，B_j = 周期 j 最后一行的收盘；
     MA20_t = (B_{g−19} + … + B_{g−1} + c_t) / 20，MA5_t = (B_{g−4} + … + B_{g−1} + c_t) / 5，
     prev20_t = 已完成第 g−3 根的 MA20 = B.rolling(20).mean().shift(3)（pandas 的滚动平均从左往右算，和截断后重算逐位相同）；g < 22 → NA。
   近平局回退：margin = min(|c/MA20 − 1|, |MA20/prev20 − 1|, |MA5/MA20 − 1|) < TIE_EPS（1e−9）或 NaN → 这一行改用原函数
     kline.trend(kline.bars(rows[:t+1], tf))，并标 fragile（fW / fM）。日K 本身就是从左往右的滚动计算，和截断后重算逐位相同，不回退，
     但 margin 同样小的行同样标 fragile（fD）。
   时点：t 收盘后算出的标签 = 从 t 收盘后到 t+1 开盘前面板上看到的标签（盘外 drop_partial_bar）→ 最早 t+1 开盘成交；
     盘中 kline.with_live 并进去的「今天这一根」不在范围内。
   不偷看：只用到 t 为止的行；禁止把整根周 / 月K 的最终标签铺回这一周 / 月的每一天（groupby(period).transform('last')、resample().last() 回填、
     按周期键 merge）、用 searchsorted(side='left') 对到整根 K 线、用全部票日期的并集当日历（tests/test_kline_series.py 证明）。
四 「月线一段时间上涨」MUB（N = 3）：M_t = 上升，且本月之前最近 N 根已完成的月K（g−1 … g−N）都是上升；每一根已完成月K 的标签 = 它那个月
   最后一行收盘时的月K 标签 = kline.trend(kline.bars(截到那一行, "M"))（month_done）。M_t 或那 N 根里任何一根是 NA → NA（未知）；
   已知且都成立 → 1，否则 0。热身：至少 N + 23 根月K（含本月）。本月之前的月份一定已经走完，不需要市场日历。
   mubc = 只用已完成的那 N 根（MUC3），不看本月此刻的标签。已完成标签按月K 的绝对序号 asof_M 放（_done_by_bar）：
   给的是切过的表（不从第一行开始）时，切点之前的月份记 NA → 用到它们的行记为未知（不偷看、不报错；tests 证明）。
五 对照口径「只用已完成 K 线」（labels_completed，只描述）：周 / 月用 mtf.completion_days + mtf.bars（日历 jpx_calendar：
   calendar_jp.is_trading_day 生成，延长到数据最后一天之后 1 个交易日）；放回日线 = 完成日 ≤ t 的最后一根（on_days：side='right' 再 −1），
   完成日收盘起生效；日历最后一个周期不算已完成（数据最后一天不是那个周期的最后一个交易日 → 数据最后一个周期不算已完成）。
六 用哪些行（clean_rows）：只用 Close 有值且 Volume > 0 的行（QB_DROP_ZERO_VOL=1 同一规则）；断言日期递增、没有重复、没有周六 / 周日；
   再删掉不是 JPX 交易日的行（calendar_jp）并数个数。
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from . import calendar_jp as CAL
from . import kline as K
from . import mtf as MTF

CODE = {"上升": 1, "震荡": 0, "下降": -1}
NAME = {v: k for k, v in CODE.items()}
NA = -128                                   # int8：K 线不够（kline.trend → None）/ 未知
SB = K.SLOPE_BARS                           # 3
NEED = 20 + SB                              # 23 根才有标签
TIE_EPS = 1e-9                              # 近平局：相对差小于它（或 NaN）→ 回退到原函数并标 fragile
FREQ = {"W": "W-FRI", "M": "M"}             # 同 kline.bars
COLS = ("D", "W", "M", "fD", "fW", "fM", "asof_W", "asof_M")
STAT_KEYS = ("rows", "fragile_D", "fragile_W", "fragile_M", "fallback_W", "fallback_M", "flip_W", "flip_M")


# ───────────────────────── 基础 ─────────────────────────
def code_of(tr: dict | None) -> int:
    """kline.trend 的结果 → 代码（上升 1 / 震荡 0 / 下降 −1；None → NA）。"""
    return NA if tr is None else CODE[tr["label"]]


def ref_code(rows: pd.DataFrame, tf: str) -> int:
    """原函数（面板）：这一段行情最后一行收盘时 tf 周期的标签代码 = kline.trend(kline.bars(rows, tf))。"""
    return code_of(K.trend(K.bars(rows, tf)))


def _lag(x: np.ndarray, k: int) -> np.ndarray:
    """往后挪 k 格（前面补 NaN）。"""
    out = np.full(len(x), np.nan)
    if len(x) > k:
        out[k:] = x[:len(x) - k]
    return out


def _rule(c, m5, m20, prev20) -> tuple[np.ndarray, np.ndarray]:
    """kline.trend 的三条比较（同一个 slope 写法）→ (标签代码 int8, margin)。
    margin 用 np.minimum（会传 NaN）：三个相对差里任何一个是 NaN（例：收盘与 MA20 都是 0 → 0/0）→ margin = NaN → 回退并标 fragile
    （np.fmin 会把 NaN 吞掉，只有三个全是 NaN 才回退，和「或为 NaN」的字面不符）。"""
    c, m5, m20, prev20 = (np.asarray(v, float) for v in (c, m5, m20, prev20))
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = np.where(prev20 > 0, (m20 / prev20 - 1) * 100, 0.0)
        up = (c > m20) & (slope > 0) & (m5 > m20)
        dn = (c < m20) & (slope < 0) & (m5 < m20)
        lab = np.where(up, 1, np.where(dn, -1, 0)).astype(np.int8)
        mar = np.minimum(np.minimum(np.abs(c / m20 - 1), np.abs(m20 / prev20 - 1)), np.abs(m5 / m20 - 1))
    return lab, mar


def _bar_ids(index: pd.DatetimeIndex, tf: str) -> np.ndarray:
    """每一行所在周 / 月K 的序号（这只票自己的第几根，从 0 起；行已按日期排好 → 同一周期的行连在一起）。"""
    n = len(index)
    if n == 0:
        return np.zeros(0, np.int32)
    per = index.to_period(FREQ[tf])
    return np.r_[0, np.cumsum(per[1:] != per[:-1])].astype(np.int32)


def _last_rows(g: np.ndarray) -> np.ndarray:
    """每一根 K 线最后一行的位置。"""
    if not len(g):
        return np.zeros(0, int)
    return np.r_[np.flatnonzero(np.diff(g)), len(g) - 1]


def _empty_labels(index=None) -> pd.DataFrame:
    index = pd.DatetimeIndex([] if index is None else index)
    out = pd.DataFrame(index=index)
    for k in ("D", "W", "M"):
        out[k] = np.full(len(index), NA, np.int8)
    for k in ("fD", "fW", "fM"):
        out[k] = np.zeros(len(index), bool)
    for k in ("asof_W", "asof_M"):
        out[k] = np.zeros(len(index), np.int32)
    return out


def _add(stats: dict | None, key: str, v: int) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + int(v)


# ───────────────────────── 主口径：as-of 标签 ─────────────────────────
def labels_partial(df: pd.DataFrame, fallback: bool = True, stats: dict | None = None) -> pd.DataFrame:
    """一只票的日线 → 每一行（kline.ohlcv 之后、收盘有值的行）收盘时面板上的日K / 周K / 月K 标签。

    返回 DataFrame（index = 这些行的日期）：
      D / W / M（int8：1 上升、0 震荡、−1 下降、NA = −128 K 线不到 23 根）= kline.trend(kline.bars(rows[:t+1], tf)) 逐行相同；
      fD / fW / fM（bool）= fragile：margin < TIE_EPS 或 NaN（W / M 这些行已改用原函数）；
      asof_W / asof_M（int32）= 这一行所在周 / 月K 的序号 g（这只票自己的第几根，从 0 起；as-of 口径下这一根是到 t 为止的部分 K 线）。
    fallback=False 只给诊断用（近平局行留快速算法的结果，仍标 fragile）。stats（dict）累加 STAT_KEYS 的个数：
      fragile_* = fragile 行数，fallback_* = 回退调用原函数的次数，flip_* = 回退后标签和快速算法不同的行数。"""
    d = K.ohlcv(df)
    if not (d.index.is_monotonic_increasing and d.index.is_unique):
        raise ValueError("日期必须递增且没有重复")
    n = len(d)
    for k in STAT_KEYS if stats is not None else ():
        stats.setdefault(k, 0)
    _add(stats, "rows", n)
    if n == 0:
        return _empty_labels()
    c = d["Close"].to_numpy(float)
    s = pd.Series(c)
    out = pd.DataFrame(index=d.index)
    ok = np.arange(n) >= NEED - 1
    m20 = s.rolling(20).mean().to_numpy()
    lab, mar = _rule(c, s.rolling(5).mean().to_numpy(), m20, _lag(m20, SB))       # 从左往右的滚动 = 截断后重算（逐位相同）
    lab[~ok] = NA
    frag = ok & ~(mar >= TIE_EPS)
    _add(stats, "fragile_D", frag.sum())
    out["D"] = lab
    fl = {"D": frag}
    for tf in ("W", "M"):
        g = _bar_ids(d.index, tf)
        B = pd.Series(c[_last_rows(g)])                                             # 每根 K 线最后一行的收盘（g 之前的都已走完）
        S19 = B.rolling(19).sum().shift(1).to_numpy()                               # B[j−19 … j−1]
        S4 = B.rolling(4).sum().shift(1).to_numpy()                                 # B[j−4 … j−1]
        P20 = _lag(B.rolling(20).mean().to_numpy(), SB)                             # 已完成第 j−3 根的 MA20（和原函数逐位相同）
        lab, mar = _rule(c, (S4[g] + c) / 5.0, (S19[g] + c) / 20.0, P20[g])
        okg = g >= NEED - 1
        lab[~okg] = NA
        near = np.flatnonzero(okg & ~(mar >= TIE_EPS))                               # 含 NaN
        _add(stats, f"fragile_{tf}", len(near))
        if fallback:
            for i in near:
                r = ref_code(d.iloc[:i + 1], tf)
                _add(stats, f"flip_{tf}", r != lab[i])
                lab[i] = r
            _add(stats, f"fallback_{tf}", len(near))
        f = np.zeros(n, bool)
        f[near] = True
        out[tf], fl[tf] = lab, f
        out[f"asof_{tf}"] = g
    for k in ("D", "W", "M"):
        out[f"f{k}"] = fl[k]
    return out[list(COLS)]


def _as_lab(x: pd.DataFrame) -> pd.DataFrame:
    """labels_partial 的结果原样用；给的是日线 → 先算。"""
    if isinstance(x, pd.DataFrame) and {"M", "asof_M"} <= set(x.columns):
        return x
    return labels_partial(x)


def done_labels(lab: pd.DataFrame, tf: str = "M") -> pd.Series:
    """每一根周 / 月K 走完时（这只票在那个周期最后一行收盘时）的 tf 标签：index = 那一行的日期（= kline.bars 的 K 线日期），
    第 j 个值 = C_tf(j) = kline.trend(kline.bars(截到那一行, tf))。数据最后一根也列出（可能还没走完；用前 N 根的函数不会用到它）。"""
    lab = _as_lab(lab)
    if tf not in FREQ:
        raise ValueError(f"tf 只能是 W / M：{tf}")
    last = _last_rows(lab[f"asof_{tf}"].to_numpy())
    return pd.Series(lab[tf].to_numpy(np.int8)[last], index=lab.index[last], name=tf)


def month_done(lab: pd.DataFrame) -> pd.Series:
    """已完成月标签 C_M(j)（见 done_labels）。"""
    return done_labels(lab, "M")


def _done_by_bar(lab: pd.DataFrame, tf: str) -> np.ndarray:
    """按 K 线序号 g 放的已完成标签：C[g] = 第 g 根 K 线走完时（这只票在那个周期最后一行收盘时）的 tf 标签。
    下标是 asof_tf 的绝对序号（不是 lab 里第几根）：lab 被切过（从第一行之后才开始）时，切点之前的 K 线不在 lab 里 → NA
    （用到它们的行记为未知，不会拿本周期走完时的标签顶替 → 不偷看）。lab 必须是 labels_partial 结果里连续的一段行。"""
    g = lab[f"asof_{tf}"].to_numpy().astype(np.int64)
    if len(g) and (np.diff(g) < 0).any():
        raise ValueError(f"asof_{tf} 必须不减（lab 要按日期排好、连续的一段）")
    C = np.full(int(g.max()) + 1 if len(g) else 0, NA, np.int8)
    last = _last_rows(g)
    C[g[last]] = lab[tf].to_numpy(np.int8)[last]
    return C


def _prev_done(C: np.ndarray, g: np.ndarray, k: int) -> np.ndarray:
    """每一行：本月之前第 k 根月K（g − k）的已完成标签 C[g − k]（C 按绝对序号放，见 _done_by_bar）；没有那一根 → NA。"""
    j = g.astype(np.int64) - k
    out = np.full(len(j), NA, np.int8)
    ok = (j >= 0) & (j < len(C))
    out[ok] = C[j[ok]]
    return out


def _all_up(lab: pd.DataFrame, n: int, known: np.ndarray, good: np.ndarray) -> np.ndarray:
    """known / good 再并上 g−1 … g−n 这 n 根已完成月K（都已知 / 都是上升）→ int8（1 / 0 / NA）。"""
    C = _done_by_bar(lab, "M")
    g = lab["asof_M"].to_numpy()
    for k in range(1, int(n) + 1):
        v = _prev_done(C, g, k)
        known &= v != NA
        good &= v == 1
    return np.where(known, good.astype(np.int8), NA).astype(np.int8)


def mub(lab: pd.DataFrame, n: int = 3) -> pd.Series:
    """「月线一段时间上涨」：M_t = 上升，且 g−1 … g−n 这 n 根已完成月K 都是上升 → 1；任何一个 NA → NA；其余 0（int8）。
    n = 0 → 只看面板此刻的月K。lab = labels_partial 的结果（给日线也行，现算）。"""
    lab = _as_lab(lab)
    M = lab["M"].to_numpy(np.int8)
    return pd.Series(_all_up(lab, n, M != NA, M == 1), index=lab.index, name=f"MUB{int(n)}")


def mubc(lab: pd.DataFrame, n: int = 3) -> pd.Series:
    """「只用已完成」（MUC3）：g−1 … g−n 这 n 根已完成月K 都是上升 → 1；任何一个 NA → NA；其余 0；不看本月此刻的标签。"""
    lab = _as_lab(lab)
    if int(n) < 1:
        raise ValueError("mubc 至少看 1 根已完成月K")
    one = np.ones(len(lab), bool)
    return pd.Series(_all_up(lab, n, one, one.copy()), index=lab.index, name=f"MUC{int(n)}")


def done_streak(lab: pd.DataFrame, tf: str = "M") -> pd.Series:
    """每一行：本周期之前连着几根已完成的 tf K 线是上升（g−1、g−2 … 往前数到第一根不是上升 / NA 为止；只给登记前个数用）。
    lab 被切过时，切点之前的 K 线算 NA（只数到切点为止）。"""
    lab = _as_lab(lab)
    if tf not in FREQ:
        raise ValueError(f"tf 只能是 W / M：{tf}")
    C = _done_by_bar(lab, tf)
    up = (C == 1).astype(np.int64)
    cs = np.cumsum(up)
    run = cs - np.maximum.accumulate(np.where(up == 0, cs, 0))                     # 到第 j 根为止连着上升的根数
    g = lab[f"asof_{tf}"].to_numpy().astype(np.int64)
    out = np.zeros(len(g), np.int32)
    ok = g >= 1
    out[ok] = run[g[ok] - 1]
    return pd.Series(out, index=lab.index, name=f"streak_{tf}")


# ───────────────────────── 对照口径：只用已完成 K 线 ─────────────────────────
def jpx_calendar(first, last) -> pd.DatetimeIndex:
    """first〜last 的 JPX 交易日（calendar_jp.is_trading_day）+ last 之后的下一个交易日（让「last 正好是周期最后一个交易日」时
    这个周期在 last 收盘就算走完；节假日事先知道）。"""
    a, b = pd.Timestamp(first).normalize(), pd.Timestamp(last).normalize()
    days = [x for x in pd.bdate_range(a, b) if CAL.is_trading_day(x.date())]
    days.append(pd.Timestamp(CAL.next_trading_day(b.date())))
    return pd.DatetimeIndex(days)


def on_days(lab, idx, fill=NA):
    """按日期查：idx 的每一天取「日期 ≤ 这一天」的最后一个值（searchsorted side='right' 再 −1）；之前没有 → fill。
    lab = Series（或 DataFrame：每列各查；bool 列补 False、浮点列补 NaN）。lab 的 index 必须递增。"""
    idx = pd.DatetimeIndex(idx)
    ix = pd.DatetimeIndex(lab.index)
    if not ix.is_monotonic_increasing:
        raise ValueError("lab 的日期必须递增")
    if isinstance(lab, pd.DataFrame):
        return pd.DataFrame({k: on_days(lab[k], idx, _fill_for(lab[k], fill)) for k in lab.columns}, index=idx)
    pos = ix.searchsorted(idx, side="right") - 1
    vals = lab.to_numpy()
    out = np.full(len(idx), fill, dtype=vals.dtype if vals.dtype != object else object)
    ok = pos >= 0
    out[ok] = vals[pos[ok]]
    return pd.Series(out, index=idx, name=lab.name)


def _fill_for(s: pd.Series, fill):
    if s.dtype == bool:
        return False
    if np.issubdtype(s.dtype, np.floating):
        return np.nan
    return fill


def labels_completed(df: pd.DataFrame, cal, tf: str) -> pd.Series:
    """只用已完成的周 / 月K（mtf.completion_days + mtf.bars；cal = 市场日历，用 jpx_calendar，必须覆盖数据第一天、包含每一行）：
    每根已完成 K 线按 kline.trend 的规则算标签（K 线序列从左往右滚动 = 截断重算），放回这只票的行：完成日 ≤ t 的最后一根，
    完成日收盘起生效；还没有已完成的 → NA。返回 int8 Series（index = kline.ohlcv 之后的行）。
    = 部分口径在每个周期最后一行的标签往后延用、从完成日起生效（tests 证明）；日历最后一个周期不算已完成。"""
    if tf not in FREQ:
        raise ValueError(f"tf 只能是 W / M：{tf}")
    d = K.ohlcv(df)
    cal = pd.DatetimeIndex(cal)
    if len(d) and (not len(cal) or cal[0] > d.index[0]):
        raise ValueError("日历必须覆盖数据第一天")
    if not d.index.isin(cal).all():
        raise ValueError("数据行必须都是日历里的交易日（先 clean_rows）")
    b = MTF.bars(d, cal, tf)
    cb = b["Close"].astype(float)
    m20 = cb.rolling(20).mean().to_numpy()
    lab, _ = _rule(cb.to_numpy(), cb.rolling(5).mean().to_numpy(), m20, _lag(m20, SB))
    lab[np.arange(len(cb)) < NEED - 1] = NA
    return on_days(pd.Series(lab, index=pd.DatetimeIndex(b.index), name=tf), d.index).astype(np.int8)


# ───────────────────────── 用哪些行 ─────────────────────────
@lru_cache(maxsize=None)
def _closed_weekdays(year: int) -> frozenset:
    """这一年里东证休市的工作日（祝日、年末年始、全日休场）。"""
    return frozenset(x for x in pd.bdate_range(f"{year}-01-01", f"{year}-12-31") if not CAL.is_trading_day(x.date()))


def clean_rows(df: pd.DataFrame, drop_zero_vol: bool = True) -> tuple[pd.DataFrame, dict]:
    """标签用的行：Close 有值且 Volume > 0（drop_zero_vol）；断言日期递增、没有重复、没有周六 / 周日（违反 → ValueError）；
    再删掉不是 JPX 交易日的行。返回 (行, 个数 {rows_in, nan_close, zero_vol, non_jpx, rows})。"""
    c = pd.to_numeric(df["Close"], errors="coerce").to_numpy(float)
    keep = np.isfinite(c)
    info = {"rows_in": int(len(df)), "nan_close": int((~keep).sum()), "zero_vol": 0, "non_jpx": 0}
    if drop_zero_vol:
        v = (pd.to_numeric(df["Volume"], errors="coerce").to_numpy(float) if "Volume" in df.columns
             else np.full(len(df), np.nan))
        with np.errstate(invalid="ignore"):
            pos = v > 0
        info["zero_vol"] = int((keep & ~pos).sum())
        keep &= pos
    d = df.loc[keep]
    ix = pd.DatetimeIndex(d.index)
    if not ix.is_monotonic_increasing:
        raise ValueError("日期没有递增")
    if not ix.is_unique:
        raise ValueError("日期有重复")
    if len(ix) and (ix.dayofweek >= 5).any():
        raise ValueError(f"有周六 / 周日的行：{ix[ix.dayofweek >= 5][0].date()}")
    closed: set = set()
    for y in (sorted(set(ix.year)) if len(ix) else []):
        closed |= _closed_weekdays(int(y))
    bad = ix.normalize().isin(pd.DatetimeIndex(sorted(closed))) if closed else np.zeros(len(ix), bool)
    info["non_jpx"] = int(np.sum(bad))
    d = d.loc[~np.asarray(bad)]
    info["rows"] = int(len(d))
    return d, info


__all__ = ["CODE", "NAME", "NA", "NEED", "TIE_EPS", "COLS", "STAT_KEYS", "code_of", "ref_code", "labels_partial", "done_labels",
           "month_done", "mub", "mubc", "done_streak", "jpx_calendar", "on_days", "labels_completed", "clean_rows"]
