"""regime_fit_study.py — 利率 / 油价 / 汇率 / 信用变化利好或利空哪些股票，「宏观顺风度」能不能挑出之后表现更好的票
（事先写定，先提交后运行，结果出来不改规则）。

用户问（2026-09-25）：利率变高影响哪些股票、油价升 / 降分别影响哪些股票，类似情况下哪些股票表现更好，横展开后加到候补队列的优先级里。
方法（qbreak/sensitivity.py）：日経225 成分股（现行名单，幸存者偏差）近 104 周周收益对 日本 10Y、美国 10Y、WTI、美元日元、Baa 利差
  的周变化做多元回归（控制日経）→ 敏感度；宏观顺风度 = Σ 敏感度 × 该因素近 60 个交易日的平均周变化（%/周）。
检验（2008-01～；只用当时已知的数据）：
  ① 月末横截面：顺风度最高 1/5 − 最低 1/5 的之后 20 个交易日超额收益（相对日経），月度均值、t 值、前半 2008–2016 / 后半 2017–；另报秩相关 IC
  ② 突破信号：信号日顺风度 > 0 与 ≤ 0 两组，次日开盘买、第 20 日收盘的收益差（按月聚类 t）
  ③（只报告）板块条件表：各因素近 60 日变化处在历史上 1/3 以上（上升）/ 下 1/3（下降）时，各板块之后 20 日平均超额收益
  ④（只报告）当前：各因素受益 / 受损前 10 名、当前宏观趋势、顺风度前后 10 名
采用规则：
  候补队列：顺风度与说明文字一律加入，并作为同一状态内的第二排序键（顺风 / 中性 / 逆风按当日横截面三分位）——只作参考、不影响交易；
  交易排序（同一执行成本档内按顺风度先买，替代按代码）：①月度五分位差 ≥ +0.5% 且 t ≥ 2.0、两半同号为正，且 ②信号组差 ≥ +1.0pp 且 t ≥ 2.0、
  两半同号为正，且 ③组合 S0C2 20 年 Calmar ≥ 现行 + 0.03、年化 ≥ 现行 − 0.3pp、回撤不深于现行 → 才采用。
  ③ 的组合检验只在 ①② 都通过时运行（规则是「且」，不影响结论）；需要的引擎选项在登记之后实现。
输出 var/out/regime_fit_study.md / .json。
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import sensitivity as SN                                         # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak.config import DataConfig, ExecConfig, universe                   # noqa: E402
from qbreak.data import load_universe                                        # noqa: E402
from qbreak.sectors import sector_cn                                         # noqa: E402
from qbreak.strategy import IndicatorCache                                   # noqa: E402
from qbreak.trader import load_params                                        # noqa: E402

START, MID, H = pd.Timestamp("2008-01-01"), pd.Timestamp("2017-01-01"), 20
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def tstat(x: pd.Series) -> float | None:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else None


def main() -> int:
    t0 = time.time()
    d = TH.load_inputs()
    r = d["raw"]
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data = load_universe(universe("JP", "broad"), d21)
    n225 = d["n225"]
    jp_days = n225.index[n225.index >= "2004-01-01"]
    lv = SN.factor_levels(jp_days, n225, d["jgb"], r["DGS10"], r["DCOILWTICO"], d["fx"], r["BAA10Y"])
    W = SN.weekly_changes(lv)
    X = W[SN.FACTORS + ["mkt"]]
    wk_idx = W.index
    rets = {t: SN.stock_weekly(df["Close"], wk_idx) for t, df in data.items()}
    closes = pd.DataFrame({t: df["Close"] for t, df in data.items()}).reindex(jp_days)
    say(f"# 宏观顺风度：利率 / 油价 / 汇率 / 信用变化利好或利空哪些股票（{pd.Timestamp.today().date()}；{len(data)} 只，"
        f"数据截至 {jp_days[-1].date()}；{time.time() - t0:.0f}s）")

    # ── ① 月末横截面 ──
    me = pd.Series(jp_days, index=jp_days).groupby(jp_days.to_period("M")).max()
    me = [x for x in me if x >= START and jp_days.get_loc(x) + H < len(jp_days)]
    beta_cache: dict = {}
    rows, sector_rows = [], []
    for dte in me:
        tr = SN.trend(lv, dte)
        k = jp_days.get_loc(dte)
        fwd_n = n225.loc[jp_days[k + H]] / n225.loc[dte] - 1
        wend = wk_idx[wk_idx <= dte]
        if len(wend) < SN.MIN_WEEKS:
            continue
        sc = {}
        for t, y in rets.items():
            b = SN.betas(y, X, wend[-1])
            beta_cache[(t, dte)] = b
            s, _ = SN.fit_score(b, tr)
            c0, c1 = closes.at[dte, t], closes.iloc[k + H][t]
            if s is None or not (c0 == c0 and c1 == c1 and c0 > 0):
                continue
            ex = c1 / c0 - 1 - fwd_n
            sc[t] = (s, ex)
            sector_rows.append({"date": dte, "sector": sector_cn(t, "JP"), "ex": ex, **{f: tr[f] for f in SN.FACTORS}})
        if len(sc) < 50:
            continue
        df = pd.DataFrame(sc, index=["fit", "ex"]).T
        q = df["fit"].rank(pct=True)
        spread = df.loc[q > 0.8, "ex"].mean() - df.loc[q <= 0.2, "ex"].mean()
        ic = df["fit"].rank().corr(df["ex"].rank())
        rows.append({"date": dte, "spread": spread, "ic": ic})
    cs = pd.DataFrame(rows).set_index("date")
    h1, h2 = cs[cs.index < MID], cs[cs.index >= MID]
    res1 = {"months": len(cs), "spread_mean": float(cs["spread"].mean() * 100), "spread_t": tstat(cs["spread"]),
            "h1": float(h1["spread"].mean() * 100), "h2": float(h2["spread"].mean() * 100),
            "ic_mean": float(cs["ic"].mean()), "ic_t": tstat(cs["ic"])}
    say(f"\n## ① 月末横截面（{res1['months']} 个月）：顺风度前 1/5 − 后 1/5 的之后 20 日超额收益 {res1['spread_mean']:+.2f}%"
        f"（t {res1['spread_t']:.2f}；前半 {res1['h1']:+.2f}% / 后半 {res1['h2']:+.2f}%）；秩相关 IC {res1['ic_mean']:+.3f}（t {res1['ic_t']:.2f}）")

    # ── ② 突破信号 ──
    p = load_params(market="JP")
    ind = dict(IndicatorCache(data).all(p))
    gap = ExecConfig.for_market("JP", "rakuten").max_entry_gap_pct
    srows = []
    for t, df in ind.items():
        O, C = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
        for i in np.where(df["entry"].to_numpy(bool))[0]:
            dte = df.index[i]
            if dte < START or i + H >= len(df) or O[i + 1] > C[i] * (1 + gap / 100):
                continue
            wend = wk_idx[wk_idx <= dte]
            b = SN.betas(rets[t], X, wend[-1]) if len(wend) else None
            s, why = SN.fit_score(b, SN.trend(lv, dte))
            if s is None:
                continue
            nk = n225.reindex(df.index).ffill()
            srows.append({"date": dte, "ticker": t, "fit": s, "r": C[i + H] / O[i + 1] - 1,
                          "ex": C[i + H] / O[i + 1] - 1 - (nk.iloc[i + H] / nk.iloc[i + 1] - 1)})
    sg = pd.DataFrame(srows)
    pos, neg = sg[sg["fit"] > 0], sg[sg["fit"] <= 0]
    mp = pos.groupby(pos["date"].dt.to_period("M"))["r"].mean()
    mn = neg.groupby(neg["date"].dt.to_period("M"))["r"].mean()
    diff = float(pos["r"].mean() - neg["r"].mean()) * 100
    se = math.sqrt(mp.var(ddof=1) / len(mp) + mn.var(ddof=1) / len(mn)) * 100 if len(mp) > 2 and len(mn) > 2 else float("nan")
    hh = lambda a, b: (a["r"].mean() - b["r"].mean()) * 100                                     # noqa: E731
    res2 = {"n": len(sg), "n_pos": len(pos), "diff": diff, "t": diff / se if se == se and se > 0 else None,
            "h1": float(hh(pos[pos["date"] < MID], neg[neg["date"] < MID])),
            "h2": float(hh(pos[pos["date"] >= MID], neg[neg["date"] >= MID]))}
    say(f"\n## ② 突破信号（{res2['n']} 个，顺风 {res2['n_pos']} 个）：顺风组 − 逆风组 20 日收益差 {res2['diff']:+.2f}pp"
        f"（t {res2['t']:.2f}；前半 {res2['h1']:+.2f} / 后半 {res2['h2']:+.2f}）")

    # ── 判定 ──
    ok1 = res1["spread_mean"] >= 0.5 and (res1["spread_t"] or 0) >= 2.0 and res1["h1"] > 0 and res1["h2"] > 0
    ok2 = res2["diff"] >= 1.0 and (res2["t"] or 0) >= 2.0 and res2["h1"] > 0 and res2["h2"] > 0
    say(f"\n判定（事先规则）：候补队列加入顺风度（只作参考）；交易排序 —— ①{'通过' if ok1 else '未通过'}，②{'通过' if ok2 else '未通过'}"
        f"{'，下一步跑组合检验 ③' if ok1 and ok2 else ' → 不用于交易排序'}")

    # ── ③ 板块条件表 ──
    sr = pd.DataFrame(sector_rows)
    say("\n## ③ 各因素明显上升 / 下降时，各板块之后 20 日的平均超额收益（相对日経；只报告）")
    cond = {}
    for f in SN.FACTORS:
        lo, hi = sr[f].quantile(1 / 3), sr[f].quantile(2 / 3)
        for state, m in (("上升", sr[f] >= hi), ("下降", sr[f] <= lo)):
            g = sr[m].groupby("sector")["ex"].agg(["mean", "size"])
            g = g[g["size"] >= 30].sort_values("mean", ascending=False)
            cond[f"{f}|{state}"] = {"best": [(s, round(v * 100, 2)) for s, v in g["mean"].head(3).items()],
                                    "worst": [(s, round(v * 100, 2)) for s, v in g["mean"].tail(3).items()]}
            say(f"- {SN.LABEL[f]}{state}：表现较好 " + "、".join(f"{s} {v:+.2f}%" for s, v in cond[f'{f}|{state}']['best'])
                + "；较差 " + "、".join(f"{s} {v:+.2f}%" for s, v in cond[f'{f}|{state}']['worst']))

    # ── ④ 当前 ──
    last = jp_days[-1]
    tr = SN.trend(lv, last)
    wend = wk_idx[wk_idx <= last][-1]
    cur = {}
    for t, y in rets.items():
        b = SN.betas(y, X, wend)
        if b is not None:
            s, why = SN.fit_score(b, tr)
            cur[t] = {"sector": sector_cn(t, "JP"), "fit": s, "why": why, **{f: float(b[f]) for f in SN.FACTORS}}
    cdf = pd.DataFrame(cur).T
    say(f"\n## ④ 当前（{last.date()}）近 60 个交易日的宏观趋势（平均每周）：日本 10Y {tr['rate_jp']:+.3f}pt、美国 10Y {tr['rate_us']:+.3f}pt、"
        f"油价 {tr['oil']:+.2f}%、美元日元 {tr['fx']:+.2f}%、信用利差 {tr['credit']:+.3f}pt")
    tops = {}
    for f in SN.FACTORS:
        s = pd.to_numeric(cdf[f], errors="coerce").dropna().sort_values()
        tops[f] = {"up": [(t, cdf.at[t, "sector"]) for t in s.index[::-1][:10]], "down": [(t, cdf.at[t, "sector"]) for t in s.index[:10]]}
        say(f"- {SN.LABEL[f]}上升时受益前 10：" + "、".join(f"{t}({sec})" for t, sec in tops[f]["up"]))
        say(f"  {SN.LABEL[f]}上升时受损前 10：" + "、".join(f"{t}({sec})" for t, sec in tops[f]["down"]))
    fs = pd.to_numeric(cdf["fit"], errors="coerce").dropna().sort_values(ascending=False)
    say("- 当前顺风度前 10：" + "、".join(f"{t}({cdf.at[t, 'sector']}，{cdf.at[t, 'why']})" for t in fs.index[:10]))
    say("- 当前顺风度后 10：" + "、".join(f"{t}({cdf.at[t, 'sector']}，{cdf.at[t, 'why']})" for t in fs.index[-10:]))
    say(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "regime_fit_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"cross_section": res1, "signals": res2, "ok1": bool(ok1), "ok2": bool(ok2),
                                              "trade_candidate": bool(ok1 and ok2), "conditional": cond,
                                              "trend_now": {k: float(v) for k, v in tr.items()}, "tops": tops},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
