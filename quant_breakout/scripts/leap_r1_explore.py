"""leap_r1_explore.py — 「质的飞跃」第 1 轮探索（只描述、不登记；只统计信号日 ≥ 2006-10-01 的交易，Z 年代的结果不看）。

问题：以前的研究没用过、文献里证据强的个股特征，能不能把突破分得更开（胜率 / 每笔净收益）——
  股息率（价值）、2 / 3 / 5 年长期涨跌（长期反转 = 价值的价格版）、所在東証业种的 12-1 个月强弱（行业动量，era_study）、
  个股相对所在业种的 12-1 个月强弱；对照：突破日量比 vr1、周线量比 w5v（已知有效）、离 250 日高点、60 日波动、成交额。
数据：yfinance 27 年（今天的日経225 + 扩大池，scripts/leap_data.py）；信号 = 现行突破去掉 W2；
  每只票单独、一次一仓、现行卖出规则、扣立花 ¥25 万一笔的来回成本（candle_posthoc.trades，与 allstock / wvol 研究同一套）。
年代：E 2006-10〜2016-09、J 2017-01〜2026-09 分开统计，另看每年是否同方向。特征都只用信号日收盘为止的数据。
输出：var/out/leap_r1_explore.md / .json（只有统计）
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
import leap_data as LD                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
FEATS = [("dy", "股息率（过去 1 年分红 ÷ 收盘，%）", +1), ("r2y", "2 年涨跌（跳过最近 1 个月，对数）", -1),
         ("r3y", "3 年涨跌（同上）", -1), ("r5y", "5 年涨跌（同上）", -1), ("r12", "12-1 个月涨跌", +1),
         ("sec", "所在业种 12-1 个月强弱（业种间百分位）", +1), ("rsec", "个股 − 所在业种 12-1 个月", +1),
         ("vr1", "突破日量比", +1), ("w5v", "周线量比", +1), ("hi52", "收盘 ÷ 250 日高点", +1),
         ("vol60", "60 日年化波动", -1), ("lturn", "log10(20 日平均成交额)", +1)]
COMPOSITE = ("dy", "r3y", "sec", "vr1", "w5v")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 特征（有测试）──
def lag_rows(A: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(A, np.nan, dtype=float)
    if k < len(A):
        out[k:] = A[:len(A) - k]
    return out


def long_returns(C: np.ndarray, skip: int = 21) -> dict[str, np.ndarray]:
    """日 × 票的复权收盘 → 跳过最近 skip 个交易日的 1 / 2 / 3 / 5 年对数涨跌（只用当天为止）。"""
    L = np.log(np.where(C > 0, C, np.nan))
    a = lag_rows(L, skip)
    return {"r12": a - lag_rows(L, 252), "r2y": a - lag_rows(L, 504), "r3y": a - lag_rows(L, 756), "r5y": a - lag_rows(L, 1260)}


def sector_strength(C: np.ndarray, sectors: list[str | None], win: int = 252, skip: int = 21, min_members: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """業種 12-1 个月强弱：业种日收益 = 成员对数收益的等权平均（成员 < min_members 的日子缺值）；
    返回（每只票所在业种在业种之间的百分位 0〜1，个股 12-1 − 业种 12-1）。"""
    L = np.log(np.where(C > 0, C, np.nan))
    R = np.vstack([np.full((1, C.shape[1]), np.nan), np.diff(L, axis=0)])
    secs = sorted({s for s in sectors if s})
    S = np.full((len(C), len(secs)), np.nan)
    for k, s in enumerate(secs):
        m = np.array([x == s for x in sectors])
        x = R[:, m]
        cnt = np.isfinite(x).sum(axis=1)
        S[:, k] = np.where(cnt >= min_members, np.nanmean(np.where(np.isfinite(x), x, np.nan), axis=1), np.nan)
    cum = np.nancumsum(np.where(np.isfinite(S), S, 0.0), axis=0)
    ok = np.cumsum(np.isfinite(S), axis=0)
    m12 = lag_rows(cum, skip) - lag_rows(cum, win)
    cover = lag_rows(ok, skip) - lag_rows(ok, win)
    m12 = np.where(cover >= 0.7 * (win - skip), m12, np.nan)
    pct = pd.DataFrame(m12).rank(axis=1, pct=True).to_numpy()
    col = {s: k for k, s in enumerate(secs)}
    stock_pct = np.full(C.shape, np.nan)
    stock_sec = np.full(C.shape, np.nan)
    for j, s in enumerate(sectors):
        if s in col:
            stock_pct[:, j] = pct[:, col[s]]
            stock_sec[:, j] = m12[:, col[s]]
    r12 = long_returns(C, skip)["r12"]
    return stock_pct, r12 - stock_sec


def quintiles(x: pd.Series) -> pd.Series:
    """按这一组的分位数分 5 组（1 = 最低）；缺值 → NaN。"""
    v = x.astype(float)
    ok = v.notna()
    out = pd.Series(np.nan, index=x.index)
    if ok.sum() >= 25:
        out[ok] = pd.qcut(v[ok].rank(method="first"), 5, labels=False) + 1
    return out


def tstat(a: pd.Series) -> dict:
    a = a.dropna()
    return {"n": int(len(a)), "win": round(float((a > 0).mean() * 100), 1) if len(a) else None,
            "mean": round(float(a.mean()), 3) if len(a) else None, "med": round(float(a.median()), 3) if len(a) else None}


def feature_table(T: pd.DataFrame, f: str) -> dict:
    q = quintiles(T[f])
    rows = {int(k): tstat(T.loc[q == k, "net"]) for k in range(1, 6)}
    hi, lo = T.loc[q == 5, "net"], T.loc[q == 1, "net"]
    yrs = T["sig_date"].dt.year
    better = n_y = 0
    for y in sorted(yrs.unique()):
        a, b = T.loc[(q == 5) & (yrs == y), "net"], T.loc[(q == 1) & (yrs == y), "net"]
        if len(a) >= 5 and len(b) >= 5:
            n_y += 1
            better += int(a.mean() > b.mean())
    se = np.sqrt(hi.var(ddof=1) / max(len(hi), 1) + lo.var(ddof=1) / max(len(lo), 1)) if len(hi) > 1 and len(lo) > 1 else np.nan
    ic = T[[f, "net"]].dropna()
    return {"q": rows, "d51": round(float(hi.mean() - lo.mean()), 3) if len(hi) and len(lo) else None,
            "t51": round(float((hi.mean() - lo.mean()) / se), 2) if se and np.isfinite(se) and se > 0 else None,
            "years_5gt1": [better, n_y], "ic": round(float(ic[f].rank().corr(ic["net"].rank())), 4) if len(ic) > 30 else None,
            "cover": round(float(T[f].notna().mean() * 100), 1)}


def composite(T: pd.DataFrame, feats=COMPOSITE) -> pd.Series:
    sign = {k: s for k, _, s in FEATS}
    ranks = [T[f].rank(pct=True) if sign[f] > 0 else (1 - T[f].rank(pct=True)) for f in feats]
    R = pd.concat(ranks, axis=1)
    return R.mean(axis=1, skipna=True).where(R.notna().sum(axis=1) >= 3)


def main() -> int:
    import candle_posthoc as CPH
    import candle_study as CS_
    import allstock_study as S
    from bullbear_study import load
    from qbreak import candles as K
    from qbreak import score_forward as SF
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    names = LD.names()
    data = LD.ohlcv(names)
    names = [t for t in names if t in data and len(data[t])]
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in names])))
    days = days[days >= pd.Timestamp(LC.Z_WARMUP_START)]
    P = K.panel(data, days, names)
    del data
    n225 = set(universe("JP", "broad"))
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    for seg, xs in WU.load()["segments"].items():
        for x in xs:
            s33.setdefault(f"{x['code']}.T", x.get("s33"))
    sectors = [s33.get(t) for t in names]
    LR = long_returns(P["C"])
    SP, RS = sector_strength(P["C"], sectors)
    say(f"# 「质的飞跃」第 1 轮探索（只描述，{pd.Timestamp.today().date()}）")
    say(f"股票 {len(names)} 只（日経225 {sum(t in n225 for t in names)} + 扩大池 {sum(t not in n225 for t in names)}）；行情 {days[0].date()}〜{days[-1].date()}")
    p0 = SF.no_w2_params(load_params(market="JP"))
    fr = CS_.frames_from(P, days, names, list(range(len(names))), p0, {})
    T = CPH.trades(fr, p0, "2006-10-02")
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    T = T[T["sig_date"] >= pd.Timestamp(LC.EXPLORE_MIN_DATE)].reset_index(drop=True)
    LC.assert_explore_dates(T["sig_date"])
    say(f"独立交易（信号日 ≥ {LC.EXPLORE_MIN_DATE}）：{len(T)} 笔；用时 {time.time() - t0:.0f}s")
    mk = S.market_frame(load("^N225", "1990-01-01")["Close"])
    feats = S.frames_features({t: fr[t] for t in T["ticker"].unique()}, mk)
    col = {t: j for j, t in enumerate(names)}
    di = {d: i for i, d in enumerate(days)}
    rows = []
    for t, g in T.groupby("ticker"):
        f = feats.get(t)
        j = col[t]
        act = LD.actions(t)
        dy = LD.div_yield(act, pd.DatetimeIndex(g["sig_date"]))
        for k, (idx, r) in enumerate(g.iterrows()):
            i = di[r["sig_date"]]
            x = {"i": idx, "dy": float(dy.iloc[k]) if np.isfinite(dy.iloc[k]) else np.nan,
                 **{n: LR[n][i, j] for n in ("r12", "r2y", "r3y", "r5y")}, "sec": SP[i, j], "rsec": RS[i, j]}
            if f is not None and r["sig_date"] in f.index:
                fx = f.loc[r["sig_date"]]
                fx = fx.iloc[-1] if isinstance(fx, pd.DataFrame) else fx
                for n in ("vr1", "w5v", "hi52", "vol60", "lturn"):
                    x[n] = float(fx[n]) if n in fx and np.isfinite(fx[n]) else np.nan
            rows.append(x)
    X = pd.DataFrame(rows).set_index("i")
    T = T.join(X)
    T["n225"] = T["ticker"].isin(n225)
    T["w2"] = (T["w5v"].isna() | (T["w5v"] >= 1.0))
    say(f"特征对上：{len(X)} 笔；用时 {time.time() - t0:.0f}s")
    out = {"n_names": len(names), "trades": int(len(T)), "eras": {}}
    for era, (a, b) in ERAS.items():
        E = T[(T["sig_date"] >= pd.Timestamp(a)) & (T["sig_date"] < pd.Timestamp(b))].copy()
        out["eras"][era] = {}
        say(f"\n## {era} {a[:7]}〜{b[:7]}：{len(E)} 笔（日経225 {int(E['n225'].sum())}）；全部 {tstat(E['net'])}；W2 保留 {tstat(E.loc[E['w2'], 'net'])}")
        for uni, U in (("all", E), ("n225", E[E["n225"]]), ("wide", E[~E["n225"]])):
            for sub, V in (("all", U), ("w2", U[U["w2"]])):
                V = V.copy()
                V["comp"] = composite(V)
                key = f"{uni}/{sub}"
                res = {f: feature_table(V, f) for f, _, _ in FEATS + [("comp", "", 1)]}
                out["eras"][era][key] = res
                say(f"### {era} · {'全部' if uni == 'all' else ('日経225' if uni == 'n225' else '扩大池')} · {'全部突破' if sub == 'all' else 'W2 保留'}（{len(V)} 笔）")
                say("| 特征 | 覆盖 | Q1 每笔 / 胜率 | Q3 | Q5 每笔 / 胜率 | Q5−Q1 pp（t） | Q5>Q1 的年数 | 秩相关 |")
                say("|---|---|---|---|---|---|---|---|")
                for f, lab, _ in FEATS + [("comp", "合成（股息率 + 3 年反转 + 业种强弱 + 突破日量 + 周线量）", 1)]:
                    r = res[f]
                    q1, q3, q5 = r["q"][1], r["q"][3], r["q"][5]
                    fm = lambda s: "—" if s["mean"] is None else f"{s['mean']:+.2f}% / {s['win']:.0f}%"                  # noqa: E731
                    d51 = "—" if r["d51"] is None else f"{r['d51']:+.2f}"
                    t51 = "—" if r["t51"] is None else f"{r['t51']}"
                    ic = "—" if r["ic"] is None else f"{r['ic']}"
                    say(f"| {f} {lab} | {r['cover']:.0f}% | {fm(q1)} | {fm(q3)} | {fm(q5)} | {d51}（{t51}） | "
                        f"{r['years_5gt1'][0]}/{r['years_5gt1'][1]} | {ic} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r1_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    T.drop(columns=[c for c in T.columns if c not in ("ticker", "sig_date", "net", "hold_days", "n225", "w2") + tuple(f for f, _, _ in FEATS)]) \
        .to_pickle(paths.sub("cache") / "leap_r1_trades.pkl")                                           # 下一步组合检验用（缓存，不入库）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
