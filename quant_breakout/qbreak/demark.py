"""demark.py — DeMark 指标 TD Sequential（Jason Perl《DeMark Indicators》，Bloomberg Press 2008，第 1 章的「推荐设定」）。

用户（2026-10-02）：「jason perl的观点也要进行详细分析加到现在的研究中」。Perl 的方法 = 用 TD Sequential / TD Combo 找「趋势衰竭」：
  TD Setup（9）：价格翻转之后，连续 9 根收盘都低于（买）/ 高于（卖）4 根之前的收盘；
  TD Countdown（13）：setup 完成之后（第 9 根起），收盘 ≤ 2 根之前的最低价（买）/ ≥ 2 根之前的最高价（卖）的 K 线累计到 13 根（不必连续）。
这里只做 TD Sequential（不做 Combo / D-Wave / TD Lines 等）。规则（写定；与书的完整版不同之处照实写在每一条）：
  - 价格翻转：买 setup 的第 1 根 = 收盘 < 4 根前收盘、且前一根收盘 > 它 4 根前的收盘（bearish price flip）；卖 setup 反过来（bullish price flip）。
  - setup：之后每一根都满足同一个条件才继续；断了就清零，要等下一次价格翻转。到第 9 根 = setup 完成（之后条件还成立就接着数 10、11…，不再算新的完成）。
  - 完美（perfection，只描述）：买 = 第 8 或第 9 根的最低价 ≤ 第 6、7 根最低价中较低的那个；卖 = 第 8 或第 9 根的最高价 ≥ 第 6、7 根最高价中较高的那个。
  - TDST：买 setup = 9 根里最高的真实高点（max(最高价, 前一根收盘)）；卖 setup = 9 根里最低的真实低点（min(最低价, 前一根收盘)）。
    setup 的真实区间 = 9 根里最高的真实高点 − 最低的真实低点。
  - countdown：setup 完成的那一根起（第 9 根本身也可以是 countdown 1）。买：收盘 ≤ 2 根前的最低价 → +1；卖：收盘 ≥ 2 根前的最高价 → +1。
    第 13 个要再满足：买 = 这一根的最低价 ≤ countdown 第 8 根的收盘；卖 = 最高价 ≥ 第 8 根的收盘；不满足 → 13 延后（停在 12，等下一根同时满足的）。
  - 取消：① 相反方向的 setup 完成；② 价格整根越过 TDST（买 countdown：真实低点 > 买 setup 的 TDST；卖 countdown：真实高点 < 卖 setup 的 TDST）。
  - 回收（recycle）：countdown 进行中又完成一个同方向的 setup → 新 setup 的真实区间是旧的 1〜1.618 倍 → countdown 从新 setup 重新开始；
    其余情况照常数下去（书里另有「setup 套在 setup 里」等细则，这里没用 → 简化版，照实写）。
  - 13 完成之后这一轮结束；要新的 setup 才有新的 countdown。
时点：第 i 根收盘才知道（只用到 i 和之前的数据）；用在交易上 = 第 i + 1 根开盘。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SETUP_N, CD_N, LOOK_SETUP, LOOK_CD, RECYCLE = 9, 13, 4, 2, (1.0, 1.618)
COLS = ("buy_setup", "sell_setup", "buy9", "sell9", "buy_perfect", "sell_perfect", "buy_cd", "sell_cd", "buy13", "sell13",
        "buy_tdst", "sell_tdst", "buy_setup_tdst", "sell_setup_tdst")


def sequential(df: pd.DataFrame) -> pd.DataFrame:
    """OHLC（列 Open / High / Low / Close，日期索引，缺值的行先去掉）→ 每根 K 线的 TD Sequential 状态：
    buy_setup / sell_setup = 进行中的 setup 计数（0 = 没有）；buy9 / sell9 = setup 在这一根完成；buy_perfect / sell_perfect = 完成且完美；
    buy_cd / sell_cd = countdown 计数（0 = 没有进行中的）；buy13 / sell13 = countdown 13 在这一根完成；buy_tdst / sell_tdst = 进行中 countdown 的 TDST；
    buy_setup_tdst / sell_setup_tdst = 最近一次完成的买 / 卖 setup 的 TDST（与 countdown 无关，到下一次同方向 setup 完成为止；Perl：TDST 之上 = 偏多、之下 = 偏空）。"""
    x = df[["High", "Low", "Close"]].astype(float).dropna()
    h, lo, c = x["High"].to_numpy(), x["Low"].to_numpy(), x["Close"].to_numpy()
    n = len(c)
    out = {k: np.zeros(n, bool) for k in ("buy9", "sell9", "buy_perfect", "sell_perfect", "buy13", "sell13")}
    for k in ("buy_setup", "sell_setup", "buy_cd", "sell_cd"):
        out[k] = np.zeros(n, int)
    for k in ("buy_tdst", "sell_tdst", "buy_setup_tdst", "sell_setup_tdst"):
        out[k] = np.full(n, np.nan)
    last_b = last_s = np.nan
    pc = np.r_[np.nan, c[:-1]]
    th = np.fmax(h, pc)                                                     # 真实高点 / 低点（第一根没有前收盘 → 就是最高 / 最低价）
    tl = np.fmin(lo, pc)
    bs = ss = 0
    bcd = {"on": False, "n": 0, "c8": np.nan, "tdst": np.nan, "rng": np.nan}
    scd = {"on": False, "n": 0, "c8": np.nan, "tdst": np.nan, "rng": np.nan}

    def start(cd: dict, tdst: float, rng: float, recycle_only: bool) -> None:
        if cd["on"] and recycle_only:
            r = rng / cd["rng"] if cd["rng"] > 0 else np.inf
            if not RECYCLE[0] <= r < RECYCLE[1]:
                return                                                      # 不回收：照常数下去
        cd.update(on=True, n=0, c8=np.nan, tdst=tdst, rng=rng)

    for i in range(n):
        b9 = s9 = False
        if i >= LOOK_SETUP:
            if c[i] < c[i - LOOK_SETUP]:
                bs = bs + 1 if bs > 0 else (1 if i >= LOOK_SETUP + 1 and c[i - 1] > c[i - 1 - LOOK_SETUP] else 0)
            else:
                bs = 0
            if c[i] > c[i - LOOK_SETUP]:
                ss = ss + 1 if ss > 0 else (1 if i >= LOOK_SETUP + 1 and c[i - 1] < c[i - 1 - LOOK_SETUP] else 0)
            else:
                ss = 0
            b9, s9 = bs == SETUP_N, ss == SETUP_N
        out["buy_setup"][i], out["sell_setup"][i] = bs, ss
        if b9:
            a = i - SETUP_N + 1
            out["buy9"][i] = True
            out["buy_perfect"][i] = min(lo[i - 1], lo[i]) <= min(lo[i - 3], lo[i - 2])
            tdst, rng = float(np.nanmax(th[a:i + 1])), float(np.nanmax(th[a:i + 1]) - np.nanmin(tl[a:i + 1]))
            last_b = tdst
            scd["on"] = False                                               # 相反方向的 setup 完成 → 取消卖 countdown
            start(bcd, tdst, rng, recycle_only=True)
        if s9:
            a = i - SETUP_N + 1
            out["sell9"][i] = True
            out["sell_perfect"][i] = max(h[i - 1], h[i]) >= max(h[i - 3], h[i - 2])
            tdst, rng = float(np.nanmin(tl[a:i + 1])), float(np.nanmax(th[a:i + 1]) - np.nanmin(tl[a:i + 1]))
            last_s = tdst
            bcd["on"] = False
            start(scd, tdst, rng, recycle_only=True)
        if bcd["on"] and tl[i] > bcd["tdst"]:                               # 整根越过买 setup 的 TDST → 取消
            bcd["on"] = False
        if scd["on"] and th[i] < scd["tdst"]:
            scd["on"] = False
        if bcd["on"] and i >= LOOK_CD and c[i] <= lo[i - LOOK_CD]:
            if bcd["n"] < CD_N - 1:
                bcd["n"] += 1
                if bcd["n"] == 8:
                    bcd["c8"] = c[i]
            elif lo[i] <= bcd["c8"]:
                bcd["n"] = CD_N
                out["buy13"][i] = True
        if scd["on"] and i >= LOOK_CD and c[i] >= h[i - LOOK_CD]:
            if scd["n"] < CD_N - 1:
                scd["n"] += 1
                if scd["n"] == 8:
                    scd["c8"] = c[i]
            elif h[i] >= scd["c8"]:
                scd["n"] = CD_N
                out["sell13"][i] = True
        out["buy_cd"][i] = bcd["n"] if bcd["on"] else 0
        out["sell_cd"][i] = scd["n"] if scd["on"] else 0
        out["buy_tdst"][i] = bcd["tdst"] if bcd["on"] else np.nan
        out["sell_tdst"][i] = scd["tdst"] if scd["on"] else np.nan
        out["buy_setup_tdst"][i], out["sell_setup_tdst"][i] = last_b, last_s
        if bcd["on"] and bcd["n"] == CD_N:
            bcd["on"] = False
        if scd["on"] and scd["n"] == CD_N:
            scd["on"] = False
    return pd.DataFrame({k: out[k] for k in COLS}, index=x.index)


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 OHLC → 周线（周五为一周的结束；开 = 第一天开盘、高 / 低 = 一周的最高 / 最低、收 = 最后一天收盘；索引 = 那一周最后一个交易日）。"""
    x = df[["Open", "High", "Low", "Close"]].astype(float).dropna()
    g = x.groupby(pd.Grouper(freq="W-FRI"))
    w = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(), "Close": g["Close"].last(),
                      "last": g["Close"].apply(lambda s: s.index[-1] if len(s) else pd.NaT)}).dropna()
    return w.set_index("last").rename_axis(None)


def event_days(df: pd.DataFrame, col: str = "sell13") -> pd.DatetimeIndex:
    """sequential() 的某个布尔列为 True 的日子（例：sell13 = 卖 countdown 13 完成的那一根）。"""
    s = sequential(df)
    return pd.DatetimeIndex(s.index[s[col].to_numpy(bool)])
