"""leap2_s3_explore.py — 「选股本身的质的飞跃」第 S3 轮探索：按行情分段开关个股层（只描述、不登记；E / J，Z 不看；门槛 scripts/leap2_common.py）。

用户选 A「继续按新门槛做下去」。这一轮问：突破好不好，是不是主要看当时的行情？如果有一个信号日就知道的市场状态能把胜率分开 10 pp 以上、
而且两个年代同方向，就只在「好行情」里买突破（坏行情的名额留给核心）→ 组合里个股交易的胜率 / 每笔一起提高。
以前试过、不一致的：市场宽度 A50（breadth_study）、突破自己的近况（ecurve_study）、按行情切换离场（regime_exit_explore）、个股 vs 核心的 7 个条件（第 3 轮）。
这里换成还没按「突破本身的胜率」看过的状态（都只用信号日为止的数据；美国的数据只用信号日之前一天的收盘）：
  n225_r63 / r126 / r252  日経225 3 / 6 / 12 个月涨跌；n225_ma200 离 200 日线；n225_vol20 20 日实现波动（年化）
  vix  VIX；usdjpy_r63  USD/JPY 3 个月变化（日元走弱为正）；spx_r63  S&P500 3 个月涨跌
  breadth50  日経225 成分站上 50 日线的比例；newhigh  创 250 日新高的比例；disp20  成分 20 日涨跌的横截面标准差（分化）
  wave5  最近 5 个交易日全部股票池里的突破信号数（突破扎堆）
逐笔 = 第 1 轮缓存的单独交易（今天的日経225 + 扩大池、现行卖出规则、扣成本）；看 W2 保留的；每个状态按那个年代的三分位分低 / 中 / 高。
输出：var/out/leap2_s3_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap_common as LC                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
FEATS = [("n225_r63", "日経225 3 个月涨跌"), ("n225_r126", "日経225 6 个月涨跌"), ("n225_r252", "日経225 12 个月涨跌"),
         ("n225_ma200", "日経225 离 200 日线"), ("n225_vol20", "日経225 20 日波动"), ("vix", "VIX（前一天美股收盘）"),
         ("usdjpy_r63", "USD/JPY 3 个月变化"), ("spx_r63", "S&P500 3 个月涨跌"), ("breadth50", "站上 50 日线的比例"),
         ("newhigh", "创 250 日新高的比例"), ("disp20", "20 日涨跌的分化"), ("wave5", "最近 5 天的突破信号数")]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def asof_before(s: pd.Series, dates: pd.DatetimeIndex) -> np.ndarray:
    """每个日本日期 d：s 在 d 之前（不含 d）最后一个有值的数（美国收盘在日本收盘之后 → 只能用前一天的）。"""
    s = s.dropna().sort_index()
    k = s.index.searchsorted(dates, side="left") - 1
    v = s.to_numpy(float)
    return np.where(k >= 0, v[np.clip(k, 0, len(v) - 1)], np.nan)


def asof_upto(s: pd.Series, dates: pd.DatetimeIndex) -> np.ndarray:
    """每个日本日期 d：s 在 d 当天为止（含 d）最后一个有值的数。"""
    s = s.dropna().sort_index()
    k = s.index.searchsorted(dates, side="right") - 1
    v = s.to_numpy(float)
    return np.where(k >= 0, v[np.clip(k, 0, len(v) - 1)], np.nan)


def market_frame(n225: pd.Series, vix: pd.Series, usdjpy: pd.Series, spx: pd.Series, closes: pd.DataFrame) -> pd.DataFrame:
    """日本交易日 × 市场状态（都只用那天为止的数据；美国 / 汇率用前一天的）。closes = 日経225 成分的复权收盘（日 × 票）。"""
    d = n225.index
    c = n225.astype(float)
    r = np.log(c).diff()
    out = pd.DataFrame(index=d)
    for k, n in (("n225_r63", 63), ("n225_r126", 126), ("n225_r252", 252)):
        out[k] = c / c.shift(n) - 1
    out["n225_ma200"] = c / c.rolling(200, min_periods=150).mean() - 1
    out["n225_vol20"] = r.rolling(20, min_periods=15).std() * np.sqrt(252)
    out["vix"] = asof_before(vix, d)
    fx = pd.Series(asof_before(usdjpy, d), index=d)
    out["usdjpy_r63"] = fx / fx.shift(63) - 1
    sp = pd.Series(asof_before(spx, d), index=d)
    out["spx_r63"] = sp / sp.shift(63) - 1
    C = closes.reindex(d)
    ok = C.notna()
    out["breadth50"] = (C > C.rolling(50, min_periods=40).mean()).where(ok).mean(axis=1)
    out["newhigh"] = (C >= C.rolling(250, min_periods=200).max()).where(ok).mean(axis=1)
    out["disp20"] = (C / C.shift(20) - 1).std(axis=1)
    return out


def tercile_table(V: pd.DataFrame, f: str) -> dict:
    """这个年代的三分位分低 / 中 / 高 → 每组笔数 / 胜率 / 每笔；高 − 低；每年「高 > 低」的年数。"""
    x = V[f].astype(float)
    ok = x.notna()
    if ok.sum() < 30:
        return {}
    q = pd.qcut(x[ok].rank(method="first"), 3, labels=False)
    g = pd.Series(np.nan, index=V.index)
    g[ok] = q
    out = {}
    for k, lab in enumerate(("low", "mid", "high")):
        y = V.loc[g == k, "net"]
        out[lab] = {"n": int(len(y)), "win": round(float((y > 0).mean() * 100), 1), "mean": round(float(y.mean()), 3)}
    out["d_win"] = round(out["high"]["win"] - out["low"]["win"], 1)
    out["d_mean"] = round(out["high"]["mean"] - out["low"]["mean"], 3)
    yrs = V["sig_date"].dt.year
    pos = tot = 0
    for yv in sorted(yrs.unique()):
        a, b = V.loc[(g == 2) & (yrs == yv), "net"], V.loc[(g == 0) & (yrs == yv), "net"]
        if len(a) >= 3 and len(b) >= 3:
            tot += 1
            pos += int(a.mean() > b.mean())
    out["years"] = [pos, tot]
    return out


def main() -> int:
    import leap_data as LD
    from bullbear_study import load
    from qbreak.config import universe
    t0 = time.time()
    T = pd.read_pickle(paths.sub("cache") / "leap_r1_trades.pkl")
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    LC.assert_explore_dates(T["sig_date"])
    n225n = list(universe("JP", "broad"))
    data = LD.ohlcv(n225n)
    closes = pd.DataFrame({t: data[t]["Close"] for t in n225n if t in data}).sort_index()
    del data
    n225 = load("^N225", "1998-01-01")["Close"]
    mk = market_frame(n225, load("^VIX", "1998-01-01")["Close"], load("JPY=X", "1998-01-01")["Close"].where(lambda s: (s > 60) & (s < 250)),
                      load("^GSPC", "1998-01-01")["Close"], closes)
    sig = T.groupby("sig_date").size()                                            # 全部股票池（日経225 + 扩大池）每天的突破信号数
    wave = sig.reindex(mk.index).fillna(0.0).rolling(5, min_periods=1).sum()
    mk["wave5"] = wave
    X = pd.DataFrame(np.vstack([asof_upto(mk[c], pd.DatetimeIndex(T["sig_date"])) for c in mk.columns]).T, columns=mk.columns, index=T.index)
    T = T.join(X)
    say(f"# 「选股本身的质的飞跃」第 S3 轮探索：按行情分段开关个股层（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s3_explore.py 开头。格子 = 笔数 / 胜率 / 每笔净收益；低 / 中 / 高 = 那个年代 W2 交易按状态三分位；"
        "「高 − 低」为正 = 状态高时突破更好。")
    out = {}
    for era, (a, b) in ERAS.items():
        for uni, U in (("日経225 + 扩大池", T), ("日経225", T[T["n225"]])):
            V = U[(U["sig_date"] >= pd.Timestamp(a)) & (U["sig_date"] < pd.Timestamp(b)) & U["w2"]].copy()
            say(f"\n## {era} · {uni} · W2 保留（{len(V)} 笔：胜率 {(V['net'] > 0).mean() * 100:.1f}%、每笔 {V['net'].mean():+.2f}%）")
            say("| 状态 | 低 | 中 | 高 | 高 − 低：胜率 pp / 每笔 pp | 高 > 低 的年数 |")
            say("|---|---|---|---|---|---|")
            for f, lab in FEATS:
                r = tercile_table(V, f)
                out[f"{era}/{uni}/{f}"] = r
                if not r:
                    continue
                fm = lambda s: f"{s['n']} / {s['win']:.0f}% / {s['mean']:+.2f}%"                                             # noqa: E731
                say(f"| {lab} | {fm(r['low'])} | {fm(r['mid'])} | {fm(r['high'])} | {r['d_win']:+.1f} / {r['d_mean']:+.2f} | "
                    f"{r['years'][0]}/{r['years'][1]} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s3_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
