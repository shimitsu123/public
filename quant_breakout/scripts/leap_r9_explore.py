"""leap_r9_explore.py — 「质的飞跃」第 9 轮探索：把立花能买的 ETF（黄金 / 白银 / 原油 / 纳斯达克 100 / 费城半导体）也放进突破候选
（只描述、不登记；只用 E 2006〜2016 与 J 2017〜2026）。

来由：第 1〜8 轮 —— 日本个股怎么选都卡在「2017〜2026 核心更强、2006〜2011 个股回撤更深」；而黄金、纳指等的大趋势正好落在
日本个股低迷的年份（黄金 2001〜2011、2019〜；纳指 2009〜）。以前只试过「核心换成纳指」（ndx_study，㉔ 待定）与「熊市换黄金 / 常配黄金」
（refuge_study），没试过「用同一套突破规则，让个股名额也能买这些 ETF」。
合成行情（ETF 上市前也有）：美国收盘价（期货连续 GC=F / SI=F / CL=F，指数 ^NDX / ^SOX）× 那天早上的 USD/JPY，东证交易日历，
起点缩放成 ¥1,000（只影响一手的粒度）；一手 = 1 口（ETF）；ETF 用同一套突破规则但不看成交量（放量条件与 W2 都不用：
合成行情没有可靠的量 —— 期货换月时量会跳、半导体指数没有量）；手续费 / 滑点按日本个股。
候选（S0C2 = var/sim.json 同一套，个股名额 4 个共用）：X1 + 黄金；X2 + 纳指；X3 + 黄金 + 纳指；X4 + 五种全部；X5 = X3，ETF 信号优先。
注意：纳指在 2000〜2005 的走势在 ndx_study（主判定 1987〜2005）里看过 → 以后若登记，Z 年代对纳指类候选不是完全没看过的数据（黄金没看过）。
输出：var/out/leap_r9_explore.md / .json（只有统计）
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
import leap_confirm as LF                                                    # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

ETFS = {"G1540.T": ("GC=F", "黄金"), "S1542.T": ("SI=F", "白银"), "O1699.T": ("CL=F", "原油"),
        "N1545.T": ("^NDX", "纳斯达克 100"), "X2243.T": ("^SOX", "费城半导体")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def synth_jpy(under: pd.DataFrame, fx: pd.Series, jp_days: pd.DatetimeIndex, base: float = 1000.0) -> pd.DataFrame:
    """东证交易日 d 的合成价 = 前一个美国收盘 × d 日早上的 USD/JPY（前一日收盘）；OHLC 同值；从第一天缩放到 base。"""
    u = under["Close"].astype(float)
    us_prev = u.reindex(jp_days.union(u.index)).ffill().shift(1).reindex(jp_days)
    fxp = fx.reindex(jp_days.union(fx.index)).ffill().shift(1).reindex(jp_days)
    c = (us_prev * fxp).dropna()
    c = c[c > 0]
    c = c / c.iloc[0] * base
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6}, index=c.index)


def etf_frames(p, jp_days: pd.DatetimeIndex, keys) -> dict[str, pd.DataFrame]:
    from bullbear_study import load
    from qbreak.strategy import compute_indicators
    fx = load("JPY=X", "1996-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    from dataclasses import replace
    pe = replace(p, vol_mult=0.0, min_weekly_vol_ratio=0.0)                     # ETF：同一套突破规则，但不看成交量（合成行情没有可靠的量）
    out = {}
    for t in keys:
        sym = ETFS[t][0]
        df = synth_jpy(load(sym, "1985-01-01"), fx, jp_days)
        out[t] = compute_indicators(df, pe, None)
    return out


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
    ex = etf_frames(p, jp_days, list(ETFS))
    for t in ex:
        tick.LOT_OVERRIDE[t] = 1
    fr_all = {**fr, **ex}
    run_fn = LF.runner({**ctx, "days": ctx["days"].union(jp_days)}, fr_all)
    only = lambda ks: {**fr, **{k: ex[k] for k in ks}}                                                          # noqa: E731
    noetf = {t: df.assign(entry=False) for t, df in ex.items()}
    etf_trades = {}
    res = {"现行（W2 突破，日経225）": LF.run(ctx, run_fn, {**fr, **noetf}, p),
           "只有核心": LF.run(ctx, run_fn, {**LF.no_entries(fr), **noetf}, p)}
    for key, ks, pri in (("X1 + 黄金", ["G1540.T"], False), ("X2 + 纳指", ["N1545.T"], False), ("X3 + 黄金 + 纳指", ["G1540.T", "N1545.T"], False),
                         ("X4 + 五种 ETF", list(ETFS), False), ("X5 = X3，ETF 优先", ["G1540.T", "N1545.T"], True)):
        f2 = {**only(ks), **{k: noetf[k] for k in ETFS if k not in ks}}
        prio = {(k, d): 1.0 for k in ks for d in ex[k].index[ex[k]["entry"].to_numpy(bool)]} if pri else None
        res[key] = LF.run(ctx, run_fn, f2, p, priority=prio)
        etf_trades[key] = etf_stats(ctx)
    return {"res": res, "secs": round(time.time() - t0), "n": len(fr), "etf_trades": etf_trades}


def etf_stats(ctx: dict) -> dict:
    """刚跑完的那次回测里，ETF 的交易（买入日在窗口内）：每种的笔数 / 每笔净收益 / 胜率。"""
    import jq_study as JS
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    out = {}
    if not len(tr):
        return out
    a, b = ctx["windows"][ctx["era"]]
    for t in ETFS:
        x = tr[(tr["ticker"] == t) & (tr["reason"] != "end")]
        s = LF.trade_stats(x, a, b)
        if s["n"]:
            out[ETFS[t][1]] = s
    return out


def main() -> int:
    t0 = time.time()
    say(f"# 「质的飞跃」第 9 轮探索：突破候选加进立花能买的 ETF（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r9_explore.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股 + ETF 笔数 每笔净收益 / 胜率（组合里的交易）。")
    out = {}
    for era, lab in (("E", "E 2006-10〜2016-09 · 日経225 + ETF"), ("J", "J 2017-01〜2026-09 · 日経225（J-Quants）+ ETF")):
        s = setting(era)
        out[era] = {k: {w: v for w, v in r.items() if not w.startswith("_")} for k, r in s["res"].items()}
        say(f"\n## {lab}（{s['n']} 只 + {len(ETFS)} 种 ETF；{s['secs']}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|")
        for k, r in s["res"].items():
            say(f"| {k} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
        for k, st in s["etf_trades"].items():
            say(f"- {k} 里的 ETF 交易：" + "；".join(f"{n} {v['n']} 笔 {v['mean']:+.2f}% / {v['win']:.0f}%" for n, v in st.items()))
        out[era + "_etf"] = s["etf_trades"]
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r9_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
