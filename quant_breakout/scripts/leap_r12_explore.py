"""leap_r12_explore.py — 「质的飞跃」第 12 轮探索：个股的同月季节性（只描述、不登记；只看 2006-10 以后）。

文献：Heston & Sadka（2008 JFE；2010 JFQA 国际版）、Keloharju, Linnainmaa & Nyberg（2016 JF）：个股在某个日历月相对市场的超额收益，
过去 1〜20 年同一个月好的，今年同一个月也倾向于好（与动量 / 反转不同；日本也有）；日本还有决算月 / 权利确定月 / 优待月这些每年固定的资金流。
第 1〜11 轮没用过「同一个日历月」这种信息（用过：股息率、长期涨跌、业种、量、动量、反转、基本面、ETF、仓位）。
日経225 成分纳入（事件）本来想做，但公告日取不到（日経的网站拒绝程序访问，维基百科只有年份）→ 不能不偷看地回测，换成这个方向。
A 横截面：每个月末按「过去 k 年同一个月的超额收益平均」给股票排序 → 下个月前 4 / 前 10 / 前 1/5 / 后 1/5 的超额收益（相对全部等权）；
  k = 5 / 10 / 20 年（有几年用几年，至少 3 年）；另看「同月 − 其他月」（去掉个股本身的长期强弱）。
B 突破逐笔（第 1 轮缓存的独立交易）：买入那个月的同月季节分 → 五档每笔 / 胜率 / 秩相关（全部突破与 W2 保留，E / J 分开，每年同向的年数）。
数据：yfinance 27 年（复权 = 含分红），月末收盘；月收益 > +200% 或 < −90% 当数据错误去掉；股票 = 今天的日経225 + 扩大池（有幸存者偏差）。
C 门槛的算术（E / J，只有现行与只有核心，不看 Z）：个股层平均占用多少资金（每天：持有个股的买入金额 ÷ 当天权益），
  「Calmar + 0.10、回撤不变」要多多少年化 → 个股层占用的那部分资金每年要比核心多赚多少。
输出：var/out/leap_r12_explore.md / .json（只有统计）
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

ERAS = {"E": ("2006-11", "2016-09"), "J": ("2017-01", "2026-08")}            # 目标月（月末排序 → 下个月）；E 的第一个排序日 = 2006-10-31
SCORES = {"k5": (5, False), "k10": (10, False), "k20": (20, False), "k10o": (10, True)}
SCORE_LAB = {"k5": "过去 5 年同月", "k10": "过去 10 年同月", "k20": "过去 20 年同月", "k10o": "10 年同月 − 其他月", "vol": "对照：过去 60 个月波动"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 有测试的部分 ──
def month_end_close(close: pd.DataFrame) -> pd.DataFrame:
    """日 × 票 → 月（Period）× 票：每个月最后一个有值的收盘。"""
    return close.groupby(close.index.to_period("M")).last()


def monthly_excess(me: pd.DataFrame, hi: float = 2.0, lo: float = -0.9) -> tuple[pd.DataFrame, pd.DataFrame]:
    """月末收盘 → （月收益, 相对当月全部等权的超额）；> hi 或 < lo 的月收益当数据错误 → NaN。"""
    r = me.pct_change(fill_method=None)
    r = r.where((r <= hi) & (r >= lo))
    return r, r.sub(r.mean(axis=1), axis=0)


def seasonal_score(X: pd.DataFrame, k: int, min_n: int = 3, other: bool = False) -> pd.DataFrame:
    """目标月 T 的季节分 = X[T−12], X[T−24] … X[T−12k] 的平均（有值的 ≥ min_n 个才算）；other = True → 再减去同样 k 年里其他月的平均。
    只用 T−1 月为止的数据（月末排序、下个月持有）。X 的行必须是连续的月。"""
    A = X.to_numpy(float)
    n = len(A)

    def lag(m: int) -> np.ndarray:
        out = np.full_like(A, np.nan)
        if m < n:
            out[m:] = A[:n - m]
        return out

    s = np.zeros_like(A)
    c = np.zeros_like(A)
    for j in range(1, k + 1):
        v = lag(12 * j)
        ok = np.isfinite(v)
        s += np.where(ok, v, 0.0)
        c += ok
    S = np.where(c >= min_n, s / np.maximum(c, 1), np.nan)
    if other:
        so = np.zeros_like(A)
        co = np.zeros_like(A)
        for m in range(1, 12 * k + 1):
            if m % 12 == 0:
                continue
            v = lag(m)
            ok = np.isfinite(v)
            so += np.where(ok, v, 0.0)
            co += ok
        S = np.where(co >= 11 * min_n, S - so / np.maximum(co, 1), np.nan)
    return pd.DataFrame(S, index=X.index, columns=X.columns)


def rank_buckets(score: pd.Series, nxt: pd.Series, ks=(4, 10), q: int = 5) -> dict | None:
    """一个月：季节分与下个月超额都有值的票 → 前 k 名 / 后 10 名 / 前 1/q / 后 1/q 的下个月平均超额（小数）。"""
    d = pd.DataFrame({"s": score, "x": nxt}).dropna()
    if len(d) < max(max(ks), 2 * q):
        return None
    d = d.sort_values("s", ascending=False)
    m = len(d) // q
    out = {f"top{k}": float(d["x"].iloc[:k].mean()) for k in ks}
    out["bot10"] = float(d["x"].iloc[-10:].mean())
    out["q5"] = float(d["x"].iloc[:m].mean())
    out["q1"] = float(d["x"].iloc[-m:].mean())
    out["ic"] = float(d["s"].rank().corr(d["x"].rank()))
    return out


def summarize(rows: pd.DataFrame) -> dict:
    """每月一行（top4 / top10 / q5 / q1 / ic）→ 平均（%/月）、t、Q5 − Q1 为正的月份比例、每年同向的年数。"""
    out = {}
    for c in [c for c in ("top4", "top10", "bot10", "q5", "q1", "ic") if c in rows]:
        v = rows[c].dropna()
        f = 1.0 if c == "ic" else 100.0
        out[c] = {"mean": round(float(v.mean() * f), 3), "t": round(float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))), 2) if len(v) > 2 else None}
    d = (rows["q5"] - rows["q1"]).dropna()
    out["d51"] = {"mean": round(float(d.mean() * 100), 3), "t": round(float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))), 2) if len(d) > 2 else None,
                  "hit": round(float((d > 0).mean() * 100), 1)}
    yrs = d.groupby(d.index.year).mean()
    t4 = rows["top4"].dropna().groupby(rows["top4"].dropna().index.year).mean()
    out["years_d51"] = [int((yrs > 0).sum()), int(len(yrs))]
    out["years_top4"] = [int((t4 > 0).sum()), int(len(t4))]
    out["months"] = int(len(d))
    return out


def utilization(trades: pd.DataFrame, history: list, a: str, b: str | None) -> float:
    """[a, b) 里每天：持有中的个股（不含 1655）买入金额合计 ÷ 当天权益 → 平均。history = 引擎的 [[日期, 权益, …], …]。"""
    eq = pd.Series({pd.Timestamp(h[0]): float(h[1]) for h in history}).sort_index()
    eq = eq[(eq.index >= pd.Timestamp(a)) & ((eq.index < pd.Timestamp(b)) if b else True)]
    if not len(eq):
        return float("nan")
    held = pd.Series(0.0, index=eq.index)
    tr = trades[trades["ticker"] != "1655.T"]
    for _, r in tr.iterrows():
        m = (held.index >= pd.Timestamp(r["entry_date"])) & (held.index < pd.Timestamp(r["exit_date"]))
        held[m] += float(r["shares"]) * float(r["entry_px"])
    return float((held / eq).mean())


def budget() -> dict:
    """C：E / J 的现行与只有核心 → 个股层占用、要多赚多少（只描述）。"""
    import jq_study as JS
    import leap_confirm as LF
    from qbreak.trader import load_params
    out = {}
    say("\n## C 门槛的算术（E / J；现行 = W2，只有核心 = 个股一个都不买）")
    say("| 窗口 | 现行 年化 / 回撤 / Calmar | 只有核心 年化 | 个股层平均占用资金 | Calmar + 0.10（回撤不变）要的年化 | 要多赚（年化 pp） | 折合个股层占用部分每年要比现在多赚 |")
    say("|---|---|---|---|---|---|---|")
    for era in ("E", "J"):
        ctx = LF.context(era)
        p = load_params(market="JP")
        fr = LF.frames(ctx, p)
        run_fn = LF.runner(ctx, fr)
        cur = LF.run(ctx, run_fn, fr, p)
        eng = JS.RealLotEngine.LAST[-1]
        a, b = ctx["windows"][era]
        u = utilization(pd.DataFrame(eng.st.trades), eng.st.history, a, b)
        core = LF.run(ctx, run_fn, LF.no_entries(fr), p)
        c = cur[era]
        need = (c["calmar"] + 0.10) * abs(c["dd"])
        extra = need - c["cagr"]
        out[era] = {"cagr": c["cagr"], "dd": c["dd"], "calmar": c["calmar"], "core_cagr": core[era]["cagr"], "util": round(u * 100, 1),
                    "need_cagr": round(need, 2), "extra_pp": round(extra, 2), "extra_on_used_pp": round(extra / u, 1) if u > 0 else None}
        o = out[era]
        say(f"| {era} | {c['cagr']:.2f}% / {c['dd']:.2f}% / {c['calmar']:.3f} | {o['core_cagr']:.2f}% | {o['util']:.1f}% | {need:.2f}% | "
            f"+{extra:.2f} | +{o['extra_on_used_pp']:.0f} pp / 年 |")
    return out


def main() -> int:
    import leap_data as LD
    from leap_r1_explore import feature_table, tstat
    from qbreak.config import universe
    t0 = time.time()
    names = LD.names()
    data = LD.ohlcv(names)
    names = [t for t in names if t in data and len(data[t])]
    close = pd.DataFrame({t: data[t]["Close"] for t in names}).sort_index()
    del data
    n225 = [t for t in universe("JP", "broad") if t in close.columns]
    me = month_end_close(close)
    MR, X = monthly_excess(me)
    say(f"# 「质的飞跃」第 12 轮探索：个股的同月季节性（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r12_explore.py 开头。超额 = 相对当月全部股票等权；「前 4」= 季节分最高的 4 只下个月的平均超额（%/月）。")
    say(f"股票 {len(names)} 只（日経225 {len(n225)}）；月末收盘 {me.index[0]}〜{me.index[-1]}；用时 {time.time() - t0:.0f}s")
    out = {"A": {}, "B": {}}
    SS = {k: seasonal_score(X, kk, 3, o) for k, (kk, o) in SCORES.items()}
    SS["vol"] = X.shift(1).rolling(60, min_periods=36).std()                  # 对照：过去 60 个月超额的波动（不是季节性；看「前 10」是不是只是高波动 + 幸存者偏差）
    # ── A 横截面 ──
    for uni, cols in (("n225", n225), ("all", list(close.columns))):
        Xu = X[cols].sub(X[cols].mean(axis=1), axis=0)                        # 超额按这个股票池重算
        for era, (a, b) in ERAS.items():
            tgt = [T for T in X.index if pd.Period(a) <= T <= pd.Period(b)]
            LC.assert_explore_dates([(T - 1).end_time.normalize() for T in tgt])
            say(f"\n## A {era}（目标月 {a}〜{b}）· {'日経225' if uni == 'n225' else '日経225 + 扩大池'}")
            say("| 季节分 | 月数 | 前 4 超额（t） | 前 10（t） | 后 10（t） | 前 1/5 | 后 1/5 | 前 − 后（t） | 前 − 后 为正的月 | 为正的年 | 前 4 为正的年 | 秩相关（t） |")
            say("|---|---|---|---|---|---|---|---|---|---|---|---|")
            for sk in list(SCORES) + ["vol"]:
                S = SS[sk][cols]
                rows = {}
                for T in tgt:
                    r = rank_buckets(S.loc[T], Xu.loc[T])
                    if r:
                        rows[T.to_timestamp()] = r
                R = pd.DataFrame(rows).T
                s = summarize(R)
                out["A"][f"{era}/{uni}/{sk}"] = s
                say(f"| {SCORE_LAB[sk]} | {s['months']} | {s['top4']['mean']:+.2f}%（{s['top4']['t']}） | {s['top10']['mean']:+.2f}%（{s['top10']['t']}） | "
                    f"{s['bot10']['mean']:+.2f}%（{s['bot10']['t']}） | "
                    f"{s['q5']['mean']:+.2f}% | {s['q1']['mean']:+.2f}% | {s['d51']['mean']:+.2f}%（{s['d51']['t']}） | {s['d51']['hit']:.0f}% | "
                    f"{s['years_d51'][0]}/{s['years_d51'][1]} | {s['years_top4'][0]}/{s['years_top4'][1]} | {s['ic']['mean']:+.3f}（{s['ic']['t']}） |")
    # ── B 突破逐笔 ──
    fp_tr = paths.sub("cache") / "leap_r1_trades.pkl"
    if fp_tr.exists():
        T = pd.read_pickle(fp_tr)
        T["sig_date"] = pd.to_datetime(T["sig_date"])
        LC.assert_explore_dates(T["sig_date"])
        days = close.index
        nxt = days[np.minimum(days.searchsorted(T["sig_date"].to_numpy(), side="right"), len(days) - 1)]
        T["em"] = pd.DatetimeIndex(nxt).to_period("M")
        for sk in SCORES:
            S = SS[sk]
            T[sk] = [S.at[m, t] if (m in S.index and t in S.columns) else np.nan for m, t in zip(T["em"], T["ticker"])]
        say(f"\n## B 突破逐笔（第 1 轮缓存的独立交易 {len(T)} 笔：日経225 + 扩大池，现行卖出规则，扣成本；季节分 = 买入那个月）")
        for era, (a, b) in (("E", ("2006-10-01", "2016-10-01")), ("J", ("2017-01-01", "2026-10-01"))):
            E = T[(T["sig_date"] >= pd.Timestamp(a)) & (T["sig_date"] < pd.Timestamp(b))]
            for sub, V in (("全部突破", E), ("W2 保留", E[E["w2"]]), ("日経225 · W2", E[E["w2"] & E["n225"]])):
                say(f"### {era} · {sub}（{len(V)} 笔；全部 {tstat(V['net'])}）")
                say("| 季节分 | 覆盖 | Q1 每笔 / 胜率 | Q3 | Q5 每笔 / 胜率 | Q5−Q1 pp（t） | Q5>Q1 的年数 | 秩相关 |")
                say("|---|---|---|---|---|---|---|---|")
                for sk in SCORES:
                    r = feature_table(V, sk)
                    out["B"][f"{era}/{sub}/{sk}"] = r
                    fm = lambda s: "—" if s["mean"] is None else f"{s['mean']:+.2f}% / {s['win']:.0f}%"                  # noqa: E731
                    d51 = "—" if r["d51"] is None else f"{r['d51']:+.2f}"
                    say(f"| {SCORE_LAB[sk]} | {r['cover']:.0f}% | {fm(r['q'][1])} | {fm(r['q'][3])} | {fm(r['q'][5])} | "
                        f"{d51}（{r['t51']}） | {r['years_5gt1'][0]}/{r['years_5gt1'][1]} | {r['ic']} |")
    else:
        say("\n（第 1 轮的逐笔缓存不在 → B 跳过；先跑 scripts/leap_r1_explore.py）")
    out["C"] = budget()
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r12_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
