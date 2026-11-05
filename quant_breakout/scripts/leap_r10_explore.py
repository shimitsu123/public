"""leap_r10_explore.py — 「质的飞跃」第 10 轮探索：ETF 的趋势仓位（时间序列动量）占个股名额（只描述、不登记；只用 E / J）。

第 9 轮：ETF 按突破规则买，很快就被 MACD / 跟踪止损卖掉，抓不住黄金、纳指的多年趋势。这里换成趋势仓位（Faber 10 个月均线 ——
时间序列动量在 100 多年、各类资产都成立，Moskowitz-Ooi-Pedersen 2012；现行核心的牛熊择时本身就是同一个思路）：
  每个月末：合成日元价（美国收盘 × 早上的 USD/JPY）> 过去 10 个月末收盘的平均 → 「趋势向上」；
  趋势向上的整个月里每天都是买入候选（优先于突破，占一个名额，按 S0C2 的 25%），趋势转下的那个月末卖（第二天开盘）；
  这种仓位不用跟踪止损 / 止盈 / 最长持有 / MACD，止损只留 −30% 的灾难止损；新仓倍数固定 1（不受日本的宏观 / 状态层影响）。
  T1 黄金；T2 黄金 + 纳指；T3 黄金 + 白银 + 原油；T4 黄金 + 纳指 + TOPIX（1306）；T5 黄金，但只在美国熊市（核心空仓）时。
输出：var/out/leap_r10_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap_confirm as LF                                                    # noqa: E402
import leap_r9_explore as R9                                                 # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from leap_r2c_sleeve import month_end_flags                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

TREND = {**R9.ETFS, "T1306.T": ("^N225", "TOPIX 代用：日経225")}
MA_MONTHS = 10
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def trend_frame(df: pd.DataFrame, months: int = MA_MONTHS) -> pd.DataFrame:
    """合成行情 → 引擎用的指标表：entry = 上一个月末判定「趋势向上」的整个月（含月末当天之后），dead_cross = 判定转下的那个月末；
    atr = NaN（止损按固定比例）。月末判定只用那天为止的月末收盘。"""
    c = df["Close"].astype(float)
    me = pd.Series(month_end_flags(df.index), index=df.index)
    mc = c[me.to_numpy()]
    up_m = mc > mc.rolling(months, min_periods=months).mean()
    up_d = up_m.reindex(df.index).ffill().fillna(False).astype(bool)          # 月末判定 → 那天收盘起生效到下一个月末
    down_at_me = me.to_numpy() & ~up_d.to_numpy()
    out = df.copy()
    out["entry"] = up_d.to_numpy()
    out["dead_cross"] = down_at_me
    out["climax"] = False
    out["atr"] = np.nan
    return out


def etf_trend_frames(jp_days: pd.DatetimeIndex, keys) -> dict[str, pd.DataFrame]:
    from bullbear_study import load
    fx = load("JPY=X", "1996-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    out = {}
    for t in keys:
        sym = TREND[t][0]
        if sym == "^N225":
            n = load(sym, "1985-01-01")
            c = n["Close"].reindex(jp_days).ffill().dropna()
            c = c / c.iloc[0] * 1000.0
            df = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6}, index=c.index)
        else:
            df = R9.synth_jpy(load(sym, "1985-01-01"), fx, jp_days)
        out[t] = trend_frame(df)
    return out


def etf_stats(ctx: dict) -> dict:
    import jq_study as JS
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    out = {}
    if not len(tr):
        return out
    a, b = ctx["windows"][ctx["era"]]
    for t, (_, name) in TREND.items():
        s = LF.trade_stats(tr[(tr["ticker"] == t) & (tr["reason"] != "end")], a, b)
        if s["n"]:
            hold = tr[(tr["ticker"] == t)]["hold_days"].mean()
            out[name] = {**s, "hold": round(float(hold), 1)}
    return out


def trend_params(p):
    return replace(p, trailing_stop_pct=0.0, take_profit_pct=0.0, max_hold_days=0, time_stop_days=0, atr_stop_mult=0.0,
                   stop_loss_pct=30.0, exit_on_macd_dead_cross=True, exit_on_climax=False)


def setting(era: str) -> dict:
    from bullbear_study import SYM, load
    from qbreak import tick
    from qbreak.trader import load_params
    t0 = time.time()
    ctx = LF.context(era)
    p = load_params(market="JP")
    fr = LF.frames(ctx, p)
    jp_days = load(*SYM["JP"]).index
    jp_days = jp_days[jp_days >= pd.Timestamp("2000-01-01")]
    ex = etf_trend_frames(jp_days, list(TREND))
    for t in ex:
        tick.LOT_OVERRIDE[t] = 1
    run_fn = LF.runner({**ctx, "days": ctx["days"].union(jp_days)}, {**fr, **ex})
    off = {t: df.assign(entry=False) for t, df in ex.items()}
    pt = trend_params(p)
    res = {"现行（W2 突破）": LF.run(ctx, run_fn, {**fr, **off}, p), "只有核心": LF.run(ctx, run_fn, {**LF.no_entries(fr), **off}, p)}
    us_bear = None
    for key, ks, only_us_bear in (("T1 + 黄金趋势", ["G1540.T"], False), ("T2 + 黄金 + 纳指趋势", ["G1540.T", "N1545.T"], False),
                                  ("T3 + 黄金 + 白银 + 原油趋势", ["G1540.T", "S1542.T", "O1699.T"], False),
                                  ("T4 + 黄金 + 纳指 + 日本指数趋势", ["G1540.T", "N1545.T", "T1306.T"], False),
                                  ("T5 黄金趋势，只在美国熊市", ["G1540.T"], True)):
        use = {}
        for k in ks:
            df = ex[k]
            if only_us_bear:
                if us_bear is None:
                    from qbreak.bullbear import BEAR, Detector, load_config
                    det = load_config()["detector"]
                    det = Detector(det["kind"], det["params"])
                    us = load(*SYM["US"])
                    us_bear = pd.Series(np.asarray(det.states(us["Close"])) == BEAR, index=us.index)
                ub = us_bear.reindex(df.index.union(us_bear.index)).ffill().reindex(df.index).fillna(False).to_numpy(bool)
                df = df.assign(entry=df["entry"].to_numpy(bool) & ub, dead_cross=df["dead_cross"].to_numpy(bool) | ~ub)
            use[k] = df
        f2 = {**fr, **{k: use.get(k, off[k]) for k in ex}}
        pb = {k: set(use[k].index[use[k]["entry"].to_numpy(bool)]) for k in use}
        prio = {(k, d): 1e6 for k in use for d in pb[k]}
        res[key] = LF.run(ctx, run_fn, f2, p, pb=pb, hold_pb=10 ** 6, pb_use_dead=True, pb_free=True, priority=prio,
                          params_t={k: pt for k in use})
        res[key]["_etf"] = etf_stats(ctx)
    return {"res": res, "secs": round(time.time() - t0), "n": len(fr)}


def main() -> int:
    t0 = time.time()
    say(f"# 「质的飞跃」第 10 轮探索：ETF 趋势仓位占个股名额（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r10_explore.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股 + ETF 笔数 每笔净收益 / 胜率（组合里的交易）。")
    out = {}
    for era, lab in (("E", "E 2006-10〜2016-09 · 日経225 + ETF 趋势"), ("J", "J 2017-01〜2026-09 · 日経225（J-Quants）+ ETF 趋势")):
        s = setting(era)
        out[era] = {k: {w: v for w, v in r.items() if not w.startswith("_")} for k, r in s["res"].items()}
        say(f"\n## {lab}（{s['n']} 只；{s['secs']}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|")
        for k, r in s["res"].items():
            say(f"| {k} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
        for k, r in s["res"].items():
            if r.get("_etf"):
                say(f"- {k} 里的 ETF 交易：" + "；".join(f"{n} {v['n']} 笔 {v['mean']:+.2f}% / {v['win']:.0f}%（平均拿 {v['hold']:.0f} 天）" for n, v in r["_etf"].items()))
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r10_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
