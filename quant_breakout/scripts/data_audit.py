"""data_audit.py — 研究与日常运行用到的全部数据：对不对、缺什么（2026-09-28 用户「检查当前进行研究所有数据是否正确 缺失什么的」）。

只读 + 报告（不改数据；发现的问题另行修正并记进 var/sim_changes.md）。每一项 → 状态 OK / 注意 / 问题 / 缺：
  A 行情缓存（yfinance）：日経225 今天的成员与 10/1 之后的成员、扩大池（TOPIX 1000 其余）、指数 / 1655 / 汇率 ——
    有没有、最后日期、交易日历上缺的天、休市日的假行、成交量 0、没有解释的单日 ±35% 以上、重复日期
  A2 交易日历（calendar_jp）对 J-Quants（2016-09〜）与 ^N225（2005〜2016-08）的真实交易日
  B 交叉核对：yfinance vs J-Quants（2016-10〜）—— 同一天涨跌幅差 > 5% 的天数，分成「前后一天合起来一致」（涨跌停 / 日期错一天）与
    「比值从此变了」（拆股 / 分红复权错位；近 2 年的会影响模拟盘）；最后一天的收盘是否一致、两边互缺的交易日
  C J-Quants 缓存：全市场面板的日期与只数、日経225 是否都在、月末上市一览最新一期、キー是否已设置（只看有没有）
  D 日银：企业物价 4 个原材料系列（最后一个月、有没有断档）、短観 売上高计划（成本 × 销售用的系列是否都在、最新一次调查）
  E 宏观：FRED 各系列、财务省 JGB、Ken French、GPR、TPU、Shiller CAPE —— 最后一个值 vs 应有的频率
  F 产业连关表份额（var/io_indirect_2020.json）：方法、业种、份额范围
  G 映射：東証业种、公司名、板块（sectors.py）对日経225（今天 / 10/1 后）与扩大池的覆盖；主题成员与扩大池是否仍上市
  H 近似时点名单（qbreak/n225_history.py）：近年加入 / 剔除的有没有登记；上市晚于 2001 年却当作一直是成员的
  I 事件表：政策事件表的校验、大事件日程往后 12 个月的日银 / FOMC / 短観、指数入替记录的代码是否上市
  J 前向记录：文件、行数、主键重复、应有的交易日有没有缺
  K 已知缺的数据（没有来源 / 要付费 / 以后才有）
输出：var/out/data_audit.md / .json（只有统计与代码，不存第三方原始数据）；末尾一节「和上一次相比」：跑之前读上一次的 data_audit.json，
  按「区 + 项目」逐项比（项目名末尾的全角括号注释不算，例如「^N225（21 年缓存）」= 「^N225」）→ 变重 / 变轻 / 新增 / 消失。
  python scripts/data_audit.py           只读核对（约 2 分钟）
  python scripts/data_audit.py --warm    先用标准取数（qbreak.data.load_universe：缓存新鲜就不下载）补齐 A 区要读的 yfinance 行情缓存，再核对；
                                         只写 var/cache/（已 gitignore）。季度复核在新容器里用（2026-09-28 用户确认 ㉚-2）：不补的话 A 区会把
                                         「没有缓存」（容器的状态，不是数据本身）报成缺 / 问题。Z 窗口（var/cache/leap_yf，只有研究用、重建很慢）不补；
                                         J-Quants 面板由季度复核前面的 w2_forward_all.py --review 补。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from qbreak import paths                                                     # noqa: E402

ROWS: list[dict] = []
ORDER = {"问题": 0, "缺": 1, "注意": 2, "OK": 3}


def add(area: str, item: str, status: str, detail: str, used_by: str = "") -> None:
    ROWS.append({"area": area, "item": item, "status": status, "detail": detail, "used_by": used_by})
    print(f"[{status}] {area} {item}：{detail}", flush=True)


def guarded(area: str):
    def deco(fn):
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as e:                                          # noqa: BLE001
                add(area, fn.__name__, "问题", f"核对本身出错：{type(e).__name__}: {e}"[:300])
        return run
    return deco


# ── 共用 ──
def _today() -> dt.date:
    from qbreak.calendar_jp import now_jst
    return now_jst().date()


def trading_days(a: dt.date, b: dt.date) -> pd.DatetimeIndex:
    from qbreak.calendar_jp import is_trading_day
    return pd.DatetimeIndex([d for d in pd.date_range(a, b) if is_trading_day(d.date())])


def last_complete_jp(today: dt.date) -> dt.date:
    """今天之前最后一个完整的东证交易日（今天盘中 / 收盘前不算今天）。"""
    from qbreak.calendar_jp import prev_trading_day
    return prev_trading_day(today)


def read_px(t: str, years: int) -> pd.DataFrame | None:
    from qbreak.data import _cache_path
    fp = _cache_path(t, years)
    for p in (fp, fp.with_suffix(".csv"), fp.with_suffix(".parquet")):
        if p.exists():
            df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, index_col=0, parse_dates=True)
            df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
            return df
    return None


def px_stats(df: pd.DataFrame, cal: pd.DatetimeIndex, today: dt.date, big: float = 0.35) -> dict:
    """一只票的行情：缺的交易日、休市日的假行、成交量 0、±35% 以上的单日变化、重复日期、最后日期（今天的盘中 K 线不算）。"""
    idx = df.index
    d = df[idx < pd.Timestamp(today)] if len(idx) else df
    idx = d.index
    if not len(idx):
        return {"rows": 0}
    c = cal[(cal >= idx[0]) & (cal <= idx[-1])]
    have, cset = set(idx), set(c)
    miss = [x for x in c if x not in have]
    extra = [x for x in idx if x not in cset]
    v = d["Volume"] if "Volume" in d else pd.Series(np.nan, index=idx)
    r = d["Close"].pct_change()
    return {"rows": int(len(d)), "first": idx[0].date(), "last": idx[-1].date(), "miss": len(miss), "miss_recent": sum(x >= pd.Timestamp(today) - pd.Timedelta(days=365) for x in miss),
            "extra": len(extra), "zero_vol": int((v == 0).sum()), "zero_vol_on_trading": int(((v == 0) & idx.isin(c)).sum()),
            "big": [(str(k.date()), round(float(x) * 100, 1)) for k, x in r[r.abs() > big].items()],
            "dup": int(idx.duplicated().sum()), "nan": int(d[["Open", "High", "Low", "Close"]].isna().any(axis=1).sum()) if {"Open", "High", "Low", "Close"} <= set(d) else 0}


# ── A 行情缓存 ──
IDX = (("^N225", "牛熊（日経）、威胁指数"), ("^GSPC", "1655 的牛熊分界"), ("1655.T", "核心 ETF"), ("1329.T", "研究（核心对照）"),
       ("JPY=X", "汇率"))


def price_lists(today: dt.date) -> list[tuple[str, list[str], int, str]]:
    """A 区要看的三组行情缓存（名字、代码、年数、用在哪里）；--warm 补的也是这三组。"""
    from qbreak import wide_universe as W
    from qbreak.universes import nikkei225
    n_now = nikkei225(exclude=True, today=today)                      # 交易股票池（航空 / 铁路不取行情）
    n_after = nikkei225(exclude=True, today=dt.date(2026, 10, 1))
    n225 = sorted(set(n_now) | set(n_after))
    wide = W.tickers(W.load())
    return [("日経225（今天）21 年", n225, 21, "研究（Z/E/J 以外的 20 年回测、行业收益）"),
            ("日経225（今天）2 年", n225, 2, "模拟盘 / 执行器（sim-day、live-u）"),
            ("扩大池（TOPIX 1000 其余）21 年", sorted(set(wide) - set(n_now)), 21, "行业收益、扩大池前向记录、研究")]


def warm(today: dt.date) -> None:
    """--warm：用标准取数补齐 A 区要读的行情缓存（缓存新鲜就不下载；只写 var/cache/）；取不到的照样往下核对、照实报告。"""
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    jobs = [(name, lst, years) for name, lst, years, _ in price_lists(today)]
    jobs += [("^N225 21 年（交易日历核对用）", ["^N225"], 21), ("指数 / ETF / 汇率 2 年", [t for t, _ in IDX[1:]], 2)]
    for name, lst, years in jobs:
        t0 = time.time()
        try:
            got = load_universe(lst, DataConfig(provider="yfinance", years=years, allow_synthetic=False).validate())
            print(f"[补缓存] {name}：{len(got)} / {len(lst)} 只（{time.time() - t0:.0f}s）", flush=True)
        except Exception as e:                                          # noqa: BLE001
            print(f"[补缓存] {name}：取数失败 {type(e).__name__}: {e}（照样核对、照实报告）"[:300], flush=True)


@guarded("A 行情")
def check_prices(today: dt.date) -> dict:
    from qbreak.universes import nikkei225
    n_now = nikkei225(exclude=True, today=today)                      # 交易股票池（航空 / 铁路不取行情）
    cal = trading_days(dt.date(1999, 1, 1), today)
    want = last_complete_jp(today)
    out = {}
    for name, lst, years, used in price_lists(today):
        stats, missing = {}, []
        for t in lst:
            df = read_px(t, years)
            if df is None:
                missing.append(t)
                continue
            stats[t] = px_stats(df, cal, today)
        old = sorted(t for t, s in stats.items() if s.get("last") and s["last"] < want)
        miss_days = {t: s["miss"] for t, s in stats.items() if s.get("miss", 0) > 0}
        recent = {t: s["miss_recent"] for t, s in stats.items() if s.get("miss_recent", 0) > 0}
        extra = {t: s["extra"] for t, s in stats.items() if s.get("extra", 0) > 0}
        big = {t: s["big"] for t, s in stats.items() if s.get("big")}
        dup = [t for t, s in stats.items() if s.get("dup")]
        nan = {t: s["nan"] for t, s in stats.items() if s.get("nan")}
        zv = {t: s["zero_vol_on_trading"] for t, s in stats.items() if s.get("zero_vol_on_trading", 0) > 5}
        st = "OK"
        notes = [f"{len(stats)} / {len(lst)} 只有缓存"]
        if missing:
            young = {}
            for t in missing:                                            # 新上市 / 再上市：别的年数的缓存里行情不满 400 天
                for yy in (27, 5, 2):
                    df2 = read_px(t, yy)
                    if df2 is not None and len(df2) and df2.index[0] >= pd.Timestamp(today) - pd.Timedelta(days=400):
                        young[t] = str(df2.index[0].date())
                        break
            other = [t for t in missing if t not in young]
            st = "问题" if years == 2 and set(missing) & set(n_now) else ("缺" if other else "注意")
            notes.append(f"没有缓存 {len(missing)} 只" + (f"（{'、'.join(other[:6])}）" if other else "")
                         + ("；其中新上市 / 再上市、行情不满一年的：" + "、".join(f"{t}（{d} 起）" for t, d in young.items()) if young else ""))
        if old:
            st = "注意" if st == "OK" else st
            notes.append(f"最后日期早于 {want} 的 {len(old)} 只（例 {'、'.join(old[:5])}；用到时会重下载）")
        yahoo_gaps = {"2009-09-01", "2010-07-20", "2010-09-15"}
        if recent:
            notes.append(f"近 1 年交易日历上缺天的 {len(recent)} 只（共 {sum(recent.values())} 天；例 "
                         + "、".join(f"{t} {n} 天" for t, n in sorted(recent.items(), key=lambda x: -x[1])[:4]) + "）")
            st = "注意" if st == "OK" else st
        if miss_days:
            notes.append(f"全期缺天的 {len(miss_days)} 只（中位 {int(np.median(list(miss_days.values())))} 天；其中 Yahoo 整天没有的 "
                         f"{'、'.join(sorted(yahoo_gaps))} 所有票都缺）")
        if extra:
            notes.append(f"缓存里休市日的行 {len(extra)} 只共 {sum(extra.values())} 行（Yahoo 的假行；2026-09-28 起载入时去掉）")
        if zv:
            notes.append(f"交易日成交量 0 超过 5 天的 {len(zv)} 只（例 " + "、".join(f"{t} {n}" for t, n in list(zv.items())[:4])
                         + "；多是 Yahoo 在 2015-12-25 / 2016-07-11（日経225 约 200 只）与 2012-05-01 的假平盘：成交量 0、收盘 = 前一天，"
                           "真实涨跌挪到下一天；再就是合并前 / 上市前的几天。leap_confirm 缺省去掉成交量 0 的行）")
        if big:
            notes.append(f"单日 ±35% 以上的 {len(big)} 只（例 " + "；".join(f"{t} {v[0][0]} {v[0][1]:+.0f}%" for t, v in list(big.items())[:4]) + "）")
            st = "注意" if st == "OK" else st
        if dup or nan:
            st = "问题"
            notes.append(f"重复日期 {len(dup)} 只、OHLC 缺值 {len(nan)} 只")
        add("A 行情", name, st, "；".join(notes), used)
        out[name] = {"n": len(lst), "cached": len(stats), "missing": missing, "old": old, "recent_missing_days": recent, "extra": extra,
                     "big": big, "dup": dup, "nan": nan, "zero_vol": zv}
    for t, used in IDX:
        for years in (2, 10, 21):
            df = read_px(t, years)
            if df is not None:
                break
        if df is None:
            add("A 行情", t, "缺", "没有缓存（用到时会下载）", used)
            continue
        s = px_stats(df, cal if t.endswith(".T") or t == "^N225" else pd.DatetimeIndex(pd.bdate_range(df.index[0], today)), today)
        st = "OK" if s["last"] >= want - dt.timedelta(days=4) else "注意"
        add("A 行情", f"{t}（{years} 年缓存）", st, f"{s['first']}〜{s['last']}，{s['rows']} 行；缺天 {s['miss']}；单日 ±35% {len(s['big'])} 次", used)
    return out


# ── A2 Z 窗口（2000〜2006，leap_yf）──
@guarded("A 行情")
def check_leap_yf(today: dt.date) -> None:
    d = paths.sub("cache") / "leap_yf"
    files = sorted(d.glob("*.csv"))
    if not files:
        add("A 行情", "Z 窗口（2000〜2006）", "缺", "var/cache/leap_yf 没有文件（Z 窗口研究要重建）", "Z 窗口研究")
        return
    cal = trading_days(dt.date(1999, 1, 1), dt.date(2007, 12, 31))
    zero = extra = 0
    n = 0
    flat = 0
    for fp in files:
        df = pd.read_csv(fp, index_col=0, parse_dates=True)
        df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        df = df[(df.index >= "2000-01-01") & (df.index <= "2006-12-31")]
        if not len(df):
            continue
        n += 1
        extra += int((~df.index.isin(cal)).sum())
        if "Volume" in df:
            zero += int((df["Volume"] == 0).sum())
        elif "close_raw" in df:
            flat += int((df["close_raw"].diff() == 0).sum())
    add("A 行情", "Z 窗口（2000〜2006，leap_yf：未复权收盘 + 分红）", "OK",
        f"{len(files)} 个文件（2000〜2006 有数据的 {n} 个）：休市日的行 {extra}" + (f"、成交量 0 {zero}" if zero else "")
        + f"；收盘与前一天完全相同的行 {flat}（含停牌 / 假行）。这些文件只用来算股息率（按真实交易日取值，休市日的行用不到）；"
        "Z 窗口的日线另由 load_universe 载入：2026-09-28 起去掉休市日的行，leap_confirm 另去成交量 0 的行",
        "Z 窗口研究")


# ── B / C J-Quants ──
def _jq_panel():
    z = np.load(paths.sub("cache") / "jquants" / "allstock_panels.npz", allow_pickle=False)
    days = pd.DatetimeIndex(z["days"].astype("datetime64[ns]"))
    names = [str(x) for x in z["names"]]
    return days, names, z


@guarded("C J-Quants")
def check_jquants(today: dt.date) -> None:
    from qbreak.universes import nikkei225
    add("C J-Quants", "キー（JQUANTS_API_KEY）", "OK" if os.environ.get("JQUANTS_API_KEY") else "缺",
        "已设置（只检查有没有，不打印）" if os.environ.get("JQUANTS_API_KEY") else "云端没设置：J-Quants 的研究 / 复核取不了新数据", "W2 全市场前向、研究")
    fp = paths.sub("cache") / "jquants" / "allstock_panels.npz"
    if not fp.exists():
        add("C J-Quants", "全市场面板", "缺", "var/cache/jquants/allstock_panels.npz 不在（scripts/allstock_data.py 重建）", "全市场研究")
        return
    days, names, z = _jq_panel()
    listed = z["listed"]
    n225 = set(nikkei225(exclude=False, today=dt.date(2026, 10, 1))) | set(nikkei225(exclude=False, today=today))
    miss = sorted(t for t in n225 if t not in set(names))
    want = last_complete_jp(today)
    st = "OK" if days[-1].date() >= want - dt.timedelta(days=7) else "注意"
    add("C J-Quants", "全市场面板（日线）", st,
        f"{days[0].date()}〜{days[-1].date()}，{len(names)} 只，平均上市 {float(listed.sum(axis=1).mean()):.0f} 只；日経225 不在面板里的 {len(miss)} 只"
        + (f"（{'、'.join(miss[:8])}）" if miss else ""), "全市场研究、W2 全市场前向、近似时点")
    snaps = sorted((paths.sub("cache") / "jquants" / "master").glob("*.csv"))
    if snaps:
        last = snaps[-1].stem
        add("C J-Quants", "月末上市一览（master）", "OK" if last >= (today.replace(day=1) - dt.timedelta(days=40)).isoformat() else "注意",
            f"{snaps[0].stem}〜{last}，{len(snaps)} 期", "近似时点股票池、新上市")


# 两边日收益差很大的那天分 timing / level / other：与每天的交叉核对（qbreak/price_check.py，㉚-1）共用同一个函数
#   timing = 前后一天合起来一致（涨跌停 / 特别气配那天一边没有成交价、日期错一天）—— 持有几天以上的收益不受影响；
#   level = 从这天起两边的比值变了、之后不回来（拆股 / 分红复权错位：yfinance 的 auto_adjust 会把分红也复权，J-Quants 只复权拆股）；
#   other = 都不是。
from qbreak.price_check import classify_mismatch                             # noqa: E402,F401


@guarded("B 交叉核对")
def check_yf_vs_jq(today: dt.date) -> dict:
    from qbreak.calendar_jp import is_trading_day
    from qbreak.universes import nikkei225
    days, names, z = _jq_panel()
    C = z["C"]
    col = {t: j for j, t in enumerate(names)}
    lst = sorted(set(nikkei225(exclude=False, today=today)) | set(nikkei225(exclude=False, today=dt.date(2026, 10, 1))))
    recent = pd.Timestamp(today) - pd.DateOffset(years=2)                 # 模拟盘 / 执行器看的是近 2 年（2 年 / 5 年缓存）
    kinds: dict[str, dict] = {"timing": {}, "level": {}, "other": {}}
    last_bad, only_jq, only_yf, n = {}, {}, {}, 0
    for t in lst:
        if t not in col:
            continue
        df = read_px(t, 21)
        if df is None:
            continue
        jq = pd.Series(C[:, col[t]].astype(float), index=days).dropna()
        jq = jq[jq > 0]
        yf = df["Close"][(df.index >= jq.index[0]) & (df.index < pd.Timestamp(today))].dropna()
        common = jq.index.intersection(yf.index)
        if len(common) < 200:
            continue
        n += 1
        J, Y = jq.reindex(common), yf.reindex(common)
        rj, ry = J.pct_change(), Y.pct_change()
        d = (rj - ry).abs().to_numpy()
        for i in np.where(d > 0.05)[0]:
            kind, shift = classify_mismatch(J, Y, int(i))
            kinds[kind].setdefault(t, []).append((str(common[i].date()), round(float(ry.iloc[i]) * 100, 1)))   # 只留 yfinance 的值（J-Quants 的逐日数据不入库）
        ratio = float(Y.iloc[-1] / J.iloc[-1])
        if abs(ratio - 1) > 0.01:
            last_bad[t] = round(ratio, 4)
        lo = max(jq.index[0], yf.index[0])
        a = set(jq.index[jq.index >= lo]) - set(yf.index)
        b = {x for x in set(yf.index[yf.index >= lo]) - set(jq.index) if is_trading_day(x.date())}    # 休市日的假行另算（A 行情）
        if len(a) > 3:
            only_jq[t] = len(a)
        if len(b) > 3:
            only_yf[t] = len(b)
    fmt = lambda v: f"{v[0]}（yfinance {v[1]:+.1f}%，J-Quants 同一天差 > 5 pp）"               # noqa: E731
    lvl_recent = {t: [v for v in vs if v[0] >= str(recent.date())] for t, vs in kinds["level"].items()}
    lvl_recent = {t: vs for t, vs in lvl_recent.items() if vs}
    tim_recent = {t: [v for v in vs if v[0] >= str(recent.date())] for t, vs in kinds["timing"].items()}
    tim_recent = {t: vs for t, vs in tim_recent.items() if vs}
    st = "问题" if lvl_recent or last_bad else ("注意" if any(kinds.values()) or only_jq or only_yf else "OK")
    cnt = {k: sum(len(v) for v in d_.values()) for k, d_ in kinds.items()}
    add("B 交叉核对", "日経225：yfinance vs J-Quants（2016-10〜）", st,
        f"核对 {n} 只；同一天涨跌幅差 > 5% 共 {sum(cnt.values())} 天：前后一天合起来一致（涨跌停 / 日期错一天）{cnt['timing']} 天 {len(kinds['timing'])} 只、"
        f"比值从此变了（拆股 / 分红复权错位）{cnt['level']} 天 {len(kinds['level'])} 只、其它 {cnt['other']} 天 {len(kinds['other'])} 只"
        + (f"；近 2 年（模拟盘 / 执行器会看到）的复权错位 {len(lvl_recent)} 只："
           + "；".join(f"{t} " + "、".join(fmt(v) for v in vs[:2]) for t, vs in list(lvl_recent.items())[:6]) if lvl_recent else "；近 2 年没有复权错位")
        + (f"；近 2 年日期错位 {len(tim_recent)} 只（例 " + "；".join(f"{t} {fmt(vs[0])}" for t, vs in list(tim_recent.items())[:3]) + "）" if tim_recent else "")
        + ("；更早的复权错位例 " + "；".join(f"{t} {fmt(vs[0])}" for t, vs in list(kinds['level'].items())[:4] if t not in lvl_recent) if kinds["level"] else "")
        + f"；最后一天收盘差 > 1% 的 {len(last_bad)} 只" + (f"（{last_bad}）" if last_bad else "")
        + f"；J-Quants 有、yfinance 没有的交易日 > 3 天的 {len(only_jq)} 只" + (f"（例 {dict(list(only_jq.items())[:4])}）" if only_jq else "")
        + f"；yfinance 有、J-Quants 没有的交易日 > 3 天的 {len(only_yf)} 只" + (f"（例 {dict(list(only_yf.items())[:4])}）" if only_yf else "")
        + "（休市日的假行不算在这里，见 A 行情）",
        "全部用 yfinance 的研究与模拟盘（J 窗口 2017〜 的研究已用 J-Quants）")
    return {"n": n, "counts": cnt, "kinds": kinds, "level_recent": lvl_recent, "timing_recent": tim_recent, "last_mismatch": last_bad,
            "only_jq": only_jq, "only_yf": only_yf}


@guarded("A 行情")
def check_calendar(today: dt.date) -> None:
    """交易日历（qbreak/calendar_jp.py）对真实的交易日：2016-09〜 对 J-Quants（有收盘价的日子），2005〜2016-08 对 ^N225（Yahoo）。"""
    from qbreak.calendar_jp import is_trading_day
    days, names, z = _jq_panel()
    has = ~np.isnan(z["C"]).all(axis=1)
    jd = {d.date() for d, h in zip(days, has) if h}
    a, b = days[0].date(), min(days[-1].date(), last_complete_jp(today))
    cal = {d.date() for d in pd.date_range(a, b) if is_trading_day(d.date())}
    x1, x2 = sorted(jd - cal), sorted(d for d in cal - jd)
    add("A 行情", "交易日历 vs J-Quants（2016-09〜）", "OK" if not x1 and not x2 else "问题",
        f"{a}〜{b}：日历 {len(cal)} 个交易日；J-Quants 有成交、日历却说休市 {len(x1)} 天" + (f"（{x1[:5]}）" if x1 else "")
        + f"；日历说开市、J-Quants 没有 {len(x2)} 天" + (f"（{x2[:5]}）" if x2 else "")
        + "（2020-10-01 东证系统故障全天停止，日历已算休市）", "所有回测、日报、执行器（什么时候开市）")
    n = read_px("^N225", 21)
    if n is None:
        add("A 行情", "交易日历 vs ^N225（2005〜2016-08）", "缺", "没有 ^N225 21 年缓存", "研究")
        return
    n = n[(n.index < pd.Timestamp(a))]
    real = {d.date() for d, v in zip(n.index, n["Volume"].to_numpy()) if v > 0}
    fake = {d.date() for d, v in zip(n.index, n["Volume"].to_numpy()) if not v > 0}
    lo = min(real)
    cal2 = {d.date() for d in pd.date_range(lo, pd.Timestamp(a) - pd.Timedelta(days=1)) if is_trading_day(d.date())}
    y1, y2 = sorted(real - cal2), sorted(cal2 - real)
    yahoo_gaps = {dt.date(2009, 9, 1), dt.date(2010, 7, 20), dt.date(2010, 9, 15)}
    y2x = [d for d in y2 if d not in yahoo_gaps]
    add("A 行情", "交易日历 vs ^N225（2005〜2016-08）", "OK" if not y1 and not y2x else "问题",
        f"{lo}〜{a - dt.timedelta(days=1)}：^N225 有成交量、日历却说休市 {len(y1)} 天" + (f"（{y1[:5]}）" if y1 else "")
        + f"；日历说开市、^N225 没有 {len(y2)} 天（其中 Yahoo 整天没有数据的 {len(set(y2) & yahoo_gaps)} 天：2009-09-01 / 2010-07-20 / 2010-09-15）"
        + (f"；其它 {y2x[:5]}" if y2x else "") + f"；成交量 0 的行 {len(fake)} 行（休市日的假行 / 早年没有成交量）", "Z / E 窗口的研究")


# ── D 日银 ──
@guarded("D 日银")
def check_boj(today: dt.date) -> None:
    import transmit_study as TS
    from qbreak import tankan as TK
    exp = (pd.Timestamp(today) - pd.offsets.MonthBegin(1) - pd.offsets.MonthBegin(1 if today.day >= 15 else 2)).normalize()
    for k, code in TS.SHOCK_CGPI.items():
        s = TS.cgpi(code).dropna()
        m = s.index.to_period("M")
        gaps = int((m[1:] - m[:-1]).map(lambda x: x.n).to_series().gt(1).sum()) if len(m) > 1 else 0
        st = "OK" if s.index[-1] >= exp and not gaps else "注意"
        add("D 日银", f"企业物价 {TS.SHOCKS[k]}（{code}）", st, f"{s.index[0].date()}〜{s.index[-1].strftime('%Y-%m')}（应有 {exp.strftime('%Y-%m')}）；断档 {gaps} 处",
            "transmit / cost_sales 研究、日报「成本 × 销售」")
    S = TK.load_sales()
    import cost_sales_study as CSS
    need = sorted({c for g in CSS.CS for c in TK.TSE.get(g, [])})
    bad = [c for c in TK.MISSING if "102CFY" in c]
    fy = today.year if today >= dt.date(today.year, 4, 5) else today.year - 1
    latest = max((kk for kk, (mm, dd) in TK.SALES_SURVEY.items() if dt.date(fy, mm, dd) <= today), key=lambda kk: TK.SALES_SURVEY[kk])
    have = S[latest].reindex(columns=need)
    miss_now = [c for c in need if fy not in have.index or pd.isna(have.at[fy, c])]
    add("D 日银", "短観 売上高计划（大企業）", "OK" if not bad and not miss_now else "注意",
        f"最新一次可用调查 = {fy} 年度 {dict(zip((5, 4, 3, 2), ('3 月', '6 月', '9 月', '12 月')))[latest]}调查；成本 × 销售用的 {len(need)} 个业种系列里这一次缺 {len(miss_now)} 个"
        + (f"（{miss_now}）" if miss_now else "") + f"；取不到的系列 {len(bad)} 个", "cost_sales 研究、日报「成本 × 销售」、S2 前向记录")
    T = TK.load()
    q = max(df.dropna(how="all").index.max() for k, df in T.items() if not k.endswith("_f"))    # 实绩（_f = 先行き，记在它预测的季度）
    miss = [c for c in TK.MISSING if "102CFY" not in c]
    lab = {v: k for k, v in TK.ITEMS.items()}
    names = [f"{TK.IND.get(c[5:9], c[5:9])} × {dict(biz='业况', dom='国内需给', sell='販売価格', buy='仕入価格').get(lab.get(c[10:12]), c[10:12])}"
             for c in miss]
    add("D 日银", "短観 DI（业况 / 需给 / 价格）", "OK" if q >= pd.Timestamp(today) - pd.Timedelta(days=150) else "注意",
        f"最后一个实绩季度 {pd.Timestamp(q).date()}（下一次：9 月调查 10/1 公布）；取不到的系列 {len(miss)} 个" + (f"（{'、'.join(names)}：这一格日银没有数据）" if miss else ""),
        "X2 前向记录、fund_study、价格转嫁")


# ── E 宏观 ──
@guarded("E 宏观")
def check_macro(today: dt.date) -> None:
    from qbreak import factors as F
    freq = {"DFF": 7, "UNRATE": 65, "BAA10Y": 7, "DCOILBRENTEU": 12, "DCOILWTICO": 10, "SP500": 7, "DEXJPUS": 14}   # DEXJPUS 每周公布（H.10）
    for k, sid in list(F.FRED_SERIES.items()) + [("unrate", "UNRATE"), ("sp500", "SP500")]:
        try:
            s = F.fred(sid).dropna()
        except Exception as e:                                          # noqa: BLE001
            add("E 宏观", f"FRED {sid}", "问题", f"取不到：{e}"[:160], "宏观层 / 威胁指数 / 仪表盘")
            continue
        lag = (pd.Timestamp(today) - s.index[-1]).days
        lim = freq.get(sid, 7)
        add("E 宏观", f"FRED {sid}（{k}）", "OK" if lag <= lim else "注意", f"{s.index[0].date()}〜{s.index[-1].date()}（{lag} 天前；容许 {lim} 天）",
            "宏观层 / 威胁指数 / 仪表盘")
    j = F.jgb_curve()["10Y"].dropna()
    lag = (pd.Timestamp(today) - j.index[-1]).days
    add("E 宏观", "财务省 JGB 10 年", "OK" if lag <= 7 else "注意", f"{j.index[0].date()}〜{j.index[-1].date()}（{lag} 天前）", "威胁指数、宏观")
    ff = F.ff_industries(49, "vw")
    last = pd.Timestamp(ff.index[-1])
    add("E 宏观", "Ken French 美国 49 行业（月）", "OK" if (pd.Timestamp(today) - last).days <= 75 else "注意",
        f"{pd.Timestamp(ff.index[0]).date()}〜{last.strftime('%Y-%m')}", "时代主线（美国）、美国复现研究")
    for name, fn, lim in (("GPR 日度", lambda: F.gpr_daily(), 14), ("TPU 月度", lambda: F.tpu_monthly(), 70),
                          ("Shiller CAPE（只用于因子调查 survey.py；来源 2023-09 起停更）", lambda: F.shiller_cape(), 70)):
        try:
            s = fn()
            s = s.dropna(how="all") if hasattr(s, "dropna") else s
            last = pd.Timestamp(s.index[-1])
            add("E 宏观", name, "OK" if (pd.Timestamp(today) - last).days <= lim else "注意", f"{pd.Timestamp(s.index[0]).date()}〜{last.date()}",
                "威胁指数（观察因素）")
        except Exception as e:                                          # noqa: BLE001
            add("E 宏观", name, "注意", f"取不到：{e}"[:160], "威胁指数（观察因素）")
    td = json.loads((paths.out_dir() / "unified_today.json").read_text(encoding="utf-8")) if (paths.out_dir() / "unified_today.json").exists() else {}
    rows = ((td.get("energy") or {}).get("rows")) or []
    miss = [r.get("name") for r in rows if r.get("value") is None]
    note = ""
    if any("STEO" in str(m) for m in miss):                                  # 日报那一刻没取到 → 现在再取一次，分清暂时性 / 持续
        try:
            from qbreak import energy_now as EN
            v, V = EN.steo_latest(today)
            note = f"；现在重取 STEO：{'成功（' + str(v) + ' 版）→ 暂时性，下次日报会补上' if v is not None and len(V) else '仍取不到'}"
        except Exception as e:                                          # noqa: BLE001
            note = f"；现在重取 STEO 出错：{type(e).__name__}"
    add("E 宏观", "能源消费（18 个来源）", "OK" if rows and not miss else ("注意" if rows else "缺"),
        f"今天的日报取到 {len(rows) - len(miss)} / {len(rows)} 个" + (f"；缺 {miss}" if miss else "") + note
        + "（K4 只用 JODI 的日本成品油需求，不受 STEO 影响）", "日报能源栏、K4 前向记录")


# ── F 产业连关表 ──
@guarded("F 产业连关表")
def check_io(today: dt.date) -> None:
    import cost_sales_study as CSS
    import transmit_study as TS
    doc = json.loads((paths.home() / "io_indirect_2020.json").read_text(encoding="utf-8"))
    probs = []
    if doc.get("method") != TS.METHOD:
        probs.append(f"方法 {doc.get('method')} ≠ {TS.METHOD}")
    inds = set(doc.get("industries") or [])
    if not set(CSS.CS) <= inds:
        probs.append(f"缺业种 {sorted(set(CSS.CS) - inds)}")
    for part in ("direct", "indirect"):
        for k in TS.SHOCKS:
            v = np.array(list((doc.get(part) or {}).get(k, {}).values()), float)
            if len(v) and ((v < -1e-9) | (v > 1 + 1e-9)).any():
                probs.append(f"{part}/{k} 有 0〜1 以外的份额")
    tot = {j: sum((doc["direct"][k].get(j, 0) + doc["indirect"][k].get(j, 0)) for k in TS.SHOCKS) for j in inds}
    hi = sorted(tot.items(), key=lambda x: -x[1])[:3]
    add("F 产业连关表", "直接 / 间接份额（2020 年表 108 部门）", "OK" if not probs else "问题",
        (f"{len(inds)} 个业种；4 种原材料合计份额最高 " + "、".join(f"{j} {v:.2f}" for j, v in hi)) + (f"；{probs}" if probs else "")
        + "；2020 年表是现在最新的一版（下一版 2025 年表预计 2029〜2030 年公布）", "transmit / cost_sales、日报「成本 × 销售」")


# ── G 映射 ──
@guarded("G 映射")
def check_maps(today: dt.date) -> None:
    from qbreak import jpx_list as JL
    from qbreak import sectors as SE
    from qbreak import themes as TH
    from qbreak import wide_universe as W
    from qbreak.universes import JP_EXCLUDED, JP_READDED_S33, nikkei225
    n225 = sorted({t.split(".")[0] for t in nikkei225(exclude=True, today=today)} | {t.split(".")[0] for t in nikkei225(exclude=True, today=dt.date(2026, 10, 1))})
    wide = sorted({t.split(".")[0] for t in W.tickers(W.load())})
    s33 = dict(JP_READDED_S33)                   # 2026-09-30 起加回的航空 / 陆运：30 业种表（industry_s33.json）按登记口径不含
    s33.update((json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8")) or {}).get("s33") or {})
    nm = JL.names()
    excl = {c for v in JP_EXCLUDED.values() for c in v}
    for label, codes in (("日経225 交易股票池（今天 + 10/1 后）", n225), ("扩大池", wide)):
        a = [c for c in codes if c not in s33]
        b = [c for c in codes if c not in nm]
        add("G 映射", f"{label}：東証业种 / 公司名", "OK" if not a and not b else "注意",
            f"{len(codes)} 只；没有東証业种 {len(a)} 只{('（' + '、'.join(a[:8]) + '）') if a else ''}；没有公司名 {len(b)} 只{('（' + '、'.join(b[:8]) + '）') if b else ''}",
            "主题 / 业种面板、行业收益、资格检查的名称")
    other = [c for c in n225 if SE.sector_of(c + ".T", "JP") == "other" and c not in excl]
    add("G 映射", "日経225：板块（sectors.py，板块倾斜用）", "OK" if not other else "问题",
        f"{len(n225)} 只里没有板块的 {len(other)} 只" + (f"（{other}）" if other else ""), "模拟盘的板块倾斜（交易）")
    try:
        L = JL.fetch()
        listed = set(L["code"].astype(str))
        asof = str(L["date"].iloc[0]) if "date" in L and len(L) else "—"
        gone_th = sorted({c for c in TH.members() if c not in listed})
        gone_w = sorted(c for c in wide if c not in listed)
        gone_n = sorted(c for c in n225 if c not in listed)
        add("G 映射", "还在上市吗（JPX 上場銘柄一覧）", "OK" if not (gone_th or gone_w or gone_n) else "注意",
            f"名单 {asof}：日経225 不在名单 {len(gone_n)} 只{gone_n if gone_n else ''}；主题成员 {len(gone_th)} 只{gone_th[:8] if gone_th else ''}；"
            f"扩大池 {len(gone_w)} 只{gone_w[:8] if gone_w else ''}（扩大池名单冻结，不在名单的 = 上市廃止 / 代码变更，前向记录里自然没有信号）",
            "主题面板、扩大池前向记录")
    except Exception as e:                                              # noqa: BLE001
        add("G 映射", "还在上市吗（JPX 上場銘柄一覧）", "注意", f"名单取不到：{e}"[:160])


# ── H 近似时点名单 ──
@guarded("H 近似时点")
def check_pit(today: dt.date) -> None:
    from qbreak import n225_history as H
    from qbreak.universes import index_changes, nikkei225
    after = {t for t in nikkei225(exclude=True, today=dt.date(2026, 10, 1))}                 # 研究股票池（航空 / 铁路不在里面）
    now = {t for t in nikkei225(exclude=True, today=today)}
    probs = []
    for ch in index_changes("JP"):
        y = int(str(ch["effective"])[:4])
        for c in ch.get("add", []):
            if H.ADD_YEAR.get(f"{c}.T") != y:
                probs.append(f"{c} {ch['effective']} 纳入 → ADD_YEAR 没有登记 {y}")
        for c in ch.get("delete", []):
            if f"{c}.T" not in H.REMOVED:
                probs.append(f"{c} {ch['effective']} 剔除 → REMOVED 没有登记")
    late = []
    for t in sorted(now | after):
        if t in H.ADD_YEAR or t in H.OLD_MEMBER_UNTIL or t in H.CONTINUITY:
            continue
        df = read_px(t, 27)
        if df is None:
            continue
        first = df.index[0]
        if first > pd.Timestamp("2001-06-30"):
            late.append(f"{t}（行情从 {first.date()}）")
    add("H 近似时点", "n225_history（近似时点日経225）", "OK" if not probs and not late else "问题",
        ("；".join(probs) if probs else "入替记录都已登记")
        + (f"；上市晚于 2001 年却没有登记加入年份（会被当作 2001 年起就是成员）：{late}" if late else ""),
        "pit_recheck / 以后 Z / E 的近似时点结果")


# ── I 事件表 ──
@guarded("I 事件表")
def check_events(today: dt.date) -> None:
    from qbreak import jpx_list as JL
    from qbreak import policy_events as PEV
    fp = ROOT / "var" / "policy_events.csv"
    E = pd.read_csv(fp, dtype=str).fillna("")
    errs = PEV.validate_table(E, today)
    add("I 事件表", "政策事件表（var/policy_events.csv）", "OK" if not errs else "注意", f"{len(E)} 行；校验问题 {len(errs)} 条" + (f"（例 {errs[:3]}）" if errs else ""),
        "政策事件反应库、G1 前向记录")
    me = json.loads((ROOT / "var" / "macro_events.json").read_text(encoding="utf-8"))
    ev = me.get("events") or []
    hi = (pd.Timestamp(today) + pd.Timedelta(days=183)).date().isoformat()
    cnt = {k: sum(1 for e in ev if e.get("kind") == k and today.isoformat() <= str(e.get("date")) <= hi) for k in ("BOJ", "FOMC", "TANKAN")}
    last = {k: max((str(e.get("date")) for e in ev if e.get("kind") == k), default="—") for k in ("BOJ", "FOMC", "TANKAN")}
    need = {"BOJ": 4, "FOMC": 4, "TANKAN": 2}
    short = {k: v for k, v in cnt.items() if v < need[k]}
    add("I 事件表", "大事件日程（往后 6 个月，季度复核维护的范围）", "OK" if not short else "注意",
        "；".join(f"{k} {cnt[k]} 次（已登记到 {last[k]}）" for k in cnt) + (f" —— 少于半年应有的 {need}（季度复核按官方日期补）" if short else "")
        + f"；未核实（tbd）{len(me.get('tbd') or [])} 条", "日报「接下来的已知大事件」、检查日历、政策事件前向记录的日程")
    try:
        listed = set(JL.fetch()["code"].astype(str))
    except Exception:                                                   # noqa: BLE001
        listed = set()
    from qbreak.universes import index_changes
    bad = [c for ch in index_changes("JP") for c in ch.get("add", []) if listed and c not in listed]
    add("I 事件表", "指数入替记录（var/index_changes.json）", "OK" if not bad else "问题",
        f"{len(index_changes('JP'))} 条；纳入代码不在上市一览 {bad if bad else '0 只'}", "股票池、资格检查")


# ── J 前向记录 ──
@guarded("J 前向记录")
def check_forward(today: dt.date) -> None:
    specs = [("threat_forward.csv", "date", ["date", "market", "variant"], True), ("us_watch_forward.csv", "date", ["date"], True),
             ("jp_watch_forward.csv", "date", ["date"], True), ("threat_weight_forward.csv", "date", None, True),
             ("energy_forward.csv", "date", ["date"], True), ("score_forward.csv", "signal_date", None, False),
             ("score_forward_wide.csv", "signal_date", None, False), ("policy_forward.csv", None, None, False),
             ("era_forward.csv", "asof", ["market", "asof", "group"], False), ("cost_sales_forward.csv", "asof", ["asof", "industry"], False),
             ("shadow_equity.csv", "date", ["date"], True)]
    cal = trading_days(dt.date(2026, 9, 1), last_complete_jp(today))
    for f, dcol, key, daily in specs:
        fp = paths.out_dir() / f
        if not fp.exists():
            add("J 前向记录", f, "OK", "还没有文件（还没到第一次记录 / 还没有信号）", "前向检验")
            continue
        d = pd.read_csv(fp, dtype=str)
        det = f"{len(d)} 行"
        st = "OK"
        if key and set(key) <= set(d.columns):
            dup = int(d.duplicated(key).sum())
            if dup:
                st = "问题"
                det += f"；主键 {key} 重复 {dup} 行"
        if dcol and dcol in d.columns and len(d):
            dd = pd.to_datetime(d[dcol], errors="coerce").dropna()
            det += f"；{dd.min().date()}〜{dd.max().date()}"
            if daily:
                have = set(dd.dt.normalize())
                miss = [x.date() for x in cal if dd.min() <= x <= dd.max() and x not in have]
                if miss:
                    st = "注意" if st == "OK" else st
                    det += f"；期间缺 {len(miss)} 个交易日（例 {miss[:4]}）"
        add("J 前向记录", f, st, det, "前向检验（只追加）")


# ── K 已知缺的数据 ──
def known_gaps() -> None:
    for item, det, used in (
        ("TOB / MBO 公布（TDnet）", "没有接适時開示：TOB 公布到被指定为整理銘柄之间的几周，资格检查查不到", "资格检查"),
        ("日経官方成分名单", "indexes.nikkei.co.jp 有 Cloudflare 验证，程序取不到 → 用日文 Wikipedia（主）+ JPX 指定（独立）", "资格检查"),
        ("被剔除后退市的旧日経成员行情", "42 只旧成员里约 13 只（倒闭 / 被收购）没有行情 → 近似时点仍有少量幸存者偏差", "近似时点研究"),
        ("J-Quants 2016-09 以前（无幸存者偏差）", "Standard 只有 10 年；20 年要 Premium（¥16,500/月，2008-05 起；2026-09-26 官方页面）", "无幸存者偏差回测"),
        ("金融业的销售计划", "短観 売上高计划没有銀行・証券・保険 → 成本 × 销售只有 18 个业种", "成本 × 销售"),
        ("新的产业连关表", "2020 年表是最新；2025 年表预计 2029〜2030 年公布", "直接 / 间接份额"),
        ("盘中 / 分钟数据", "只有日线；开盘后补单的盘中价格按始値近似", "执行器演练"),
        ("日経225 历史入替的精确日期", "近似时点名单只按年份（进出那一年两边都不算）", "近似时点研究"),
    ):
        add("K 已知缺", item, "缺", det, used)


def _key(r: dict) -> tuple[str, str]:
    """逐项对齐用：区 + 项目名（末尾的全角括号注释不算：「^N225（21 年缓存）」=「^N225」、「全市场面板（日线）」=「全市场面板」）。"""
    return r["area"], re.sub(r"（[^（）]*）$", "", r["item"]).strip()


CACHE_HINT = ("没有缓存", "没有文件", "不在（", "没有 ^N225")                     # 细节里有这些 → 多半是这台机器 / 容器没有缓存，不是数据本身


def compare(prev: dict | None, rows: list[dict]) -> dict:
    """和上一次的体检比：变重 / 变轻（状态按 问题 > 缺 > 注意 > OK）、新增、消失；同一个键出现多次取最重的。"""
    if not prev or not prev.get("rows"):
        return {"prev_date": None}

    def worst(rs):
        out = {}
        for r in rs:
            k = _key(r)
            if k not in out or ORDER.get(r["status"], 9) < ORDER.get(out[k]["status"], 9):
                out[k] = r
        return out
    old, cur = worst(prev["rows"]), worst(rows)

    def item(k, a, b):
        r = b or a
        return {"area": k[0], "item": r["item"], "old": a["status"] if a else None, "new": b["status"] if b else None,
                "detail": (b or a)["detail"][:240],
                "cache": bool(b) and any(h in b["detail"] for h in CACHE_HINT) and "重复日期" not in b["detail"]}
    worse = [item(k, old[k], cur[k]) for k in cur if k in old and ORDER.get(cur[k]["status"], 9) < ORDER.get(old[k]["status"], 9)]
    better = [item(k, old[k], cur[k]) for k in cur if k in old and ORDER.get(cur[k]["status"], 9) > ORDER.get(old[k]["status"], 9)]
    new = [item(k, None, cur[k]) for k in cur if k not in old]
    gone = [item(k, old[k], None) for k in old if k not in cur]
    still = [item(k, old[k], cur[k]) for k in cur if k in old and cur[k]["status"] == old[k]["status"] == "问题"]
    return {"prev_date": prev.get("date"), "prev_counts": prev.get("counts"), "worse": worse, "better": better, "new": new, "gone": gone,
            "still_problem": still,
            "new_problems": [x for x in worse + new if x["new"] == "问题" and not x["cache"]]}


def write(extra: dict, cmp: dict | None = None) -> None:
    rows = sorted(ROWS, key=lambda r: (r["area"], ORDER.get(r["status"], 9)))
    cnt = {k: sum(r["status"] == k for r in ROWS) for k in ("问题", "缺", "注意", "OK")}
    L = [f"# 数据核对（{_today()}；scripts/data_audit.py）", "",
         f"共 {len(ROWS)} 项：问题 {cnt['问题']}、缺 {cnt['缺']}、注意 {cnt['注意']}、OK {cnt['OK']}。只读核对；修正另记 var/sim_changes.md。", "",
         "| 区 | 项目 | 状态 | 细节 | 用在哪里 |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['area']} | {r['item']} | **{r['status']}** | {r['detail'].replace('|', '/')} | {r['used_by']} |")
    cmp = cmp or {"prev_date": None}
    L += ["", "## 和上一次相比", ""]
    if not cmp.get("prev_date"):
        L.append("没有上一次的结果（第一次运行，或 var/out/data_audit.json 不在）。")
    else:
        pc = cmp.get("prev_counts") or {}
        L.append(f"上一次 {cmp['prev_date']}：问题 {pc.get('问题', '—')}、缺 {pc.get('缺', '—')}、注意 {pc.get('注意', '—')}、OK {pc.get('OK', '—')} 项 → "
                 f"这次 问题 {cnt['问题']}、缺 {cnt['缺']}、注意 {cnt['注意']}、OK {cnt['OK']} 项。"
                 f"新出现 / 变重的「问题」（不算缓存不在的）{len(cmp['new_problems'])} 项；变重 {len(cmp['worse'])} 项、变轻 {len(cmp['better'])} 项、"
                 f"新增 {len(cmp['new'])} 项、消失 {len(cmp['gone'])} 项；一直是「问题」的 {len(cmp['still_problem'])} 项。")
        ch = [("变重", x) for x in cmp["worse"]] + [("新增", x) for x in cmp["new"]] + [("变轻", x) for x in cmp["better"]] + [("消失", x) for x in cmp["gone"]]
        if ch:
            L += ["", "| 变化 | 区 | 项目 | 上一次 → 这次 | 细节 | 缓存不在？ |", "|---|---|---|---|---|---|"]
            for tag, x in ch:
                L.append(f"| {tag} | {x['area']} | {x['item']} | {x['old'] or '—'} → {x['new'] or '—'} | {x['detail'].replace('|', '/')} | "
                         f"{'是（多半是这台机器没有缓存，不是数据本身）' if x['cache'] else ''} |")
    L += ["", "非投资建议。"]
    (paths.out_dir() / "data_audit.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "data_audit.json").write_text(json.dumps({"date": str(_today()), "counts": cnt, "rows": rows, "detail": extra, "vs_prev": cmp},
                                                                ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def main() -> int:
    t0 = time.time()
    today = _today()
    fp = paths.out_dir() / "data_audit.json"
    try:
        prev = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None          # 覆盖之前先读上一次的结果
    except (OSError, ValueError):
        prev = None
    if "--warm" in sys.argv:
        warm(today)
    extra = {}
    extra["prices"] = check_prices(today)
    check_leap_yf(today)
    check_jquants(today)
    check_calendar(today)
    extra["yf_vs_jq"] = check_yf_vs_jq(today)
    check_boj(today)
    check_macro(today)
    check_io(today)
    check_maps(today)
    check_pit(today)
    check_events(today)
    check_forward(today)
    known_gaps()
    write(extra, compare(prev, ROWS))
    print(f"\n用时 {time.time() - t0:.0f}s → var/out/data_audit.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
