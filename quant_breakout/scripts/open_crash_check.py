"""open_crash_check.py — 开盘时按分钟看日経有没有必要：「买得更便宜」与「开盘急跌时保护自己」各值多少（只描述；2026-10-04 先提交读法、再只运行一次）。

用户（2026-10-04）：「分钟检测有必要么，如果必要的话，以下或者其他方向哪个比较好 买得更便宜，还是开盘急跌时保护自己」。
性质（照实写）：只描述、只回答这个问题 —— 不是研究循环、不提候选、不改模拟盘 / 执行器 / 任何规则（用户〔53〕①「暂停找新规则」）。
  已经知道的（不在这里重算）：执行时点研究（2026-09-25，登记 cfb3cbc）—— 信号次日晚点买没有改善（全天分批 +0.009%、t 0.20）、
  开盘后各时段收盘的中位数比开盘高 0.1〜0.3%；研究循环 CPX（2026-10-01）与以前的 T7 —— 按日线急跌时卖，大多卖在最坏的那几天。
  登记前看过的（照实写）：数据质量（1321 的 Yahoo 行情 2009-02-06 以前有 255 根非正价格被数据层丢弃；^N225 没有平的 K 线）；
  上一次回答里举过一个例子（^N225 2024-08-05 开盘 −1.84%、收盘 −12.40%，次日收盘 +10.23%）—— 这一天在样本里，方向事先知道；其余没算任何收益。
数据：1321.T（NEXT FUNDS 日経225連動型上場投信）日线（Yahoo、按分红复权，开 / 高 / 低 / 收同一个系数 → 除息日的跳空不算；2009-02-06〜2026-09-30）、
  股票池（日経225 现在的成分股，universe("JP", "broad")；有幸存者偏差，只描述）个股日线同期。
  为什么不用 ^N225 指数的「始値」：指数开盘值在 9:00 算出时很多成分股还没开盘（大跌时尤其多），开盘值偏向前一天收盘 → 会夸大「开盘之后续跌」；
  1321 与个股的开盘价都是真实成交价（寄付单就按它成交）。
定义（两半 = 2009-02〜2016-12 / 2017-01〜2026-09）：
  跳空 g_t = 1321 开盘 / 前一个东证交易日收盘 − 1（前一行不是前一个交易日的那天不算）；「急跌开盘日」= g_t ≤ −1% / −2% / −3%（三档，主档 −2%）。
  a) 开盘就卖（或开盘不买）有没有用：急跌开盘日 1321 的 收盘 / 开盘 − 1（oc）与 次日收盘 / 开盘 − 1（on）—— < 0 = 开盘之后还在跌（开盘卖有用、晚点买更便宜）；
     > 0 = 开盘之后反弹（开盘卖卖在低处、开盘买反而便宜）。个股版：同一批日子里股票池每只开了盘的个股 oc / on 先按天等权平均、再对日子平均。
  b) 盘中从开盘跌 s 就卖（s = 1% / 2% / 3%，任何日子，主档 2%）：最低价 ≤ 开盘 ×(1 − s) 的日子按 开盘 ×(1 − s) 理想成交（不计滑点）；
     x0 = 收盘 / 卖价 − 1、x1 = 次日收盘 / 卖价 − 1 —— < 0 = 止损之后还在跌（止损有用）；> 0 = 卖低了。个股版：每只个股自己的开盘 / 最低，按天平均。
  c) 「买得更便宜」的上限（全部交易日；1321 与个股按天平均）：1 − 最低 / 开盘（假如每次都正好买在当天最低价 —— 做不到，只是天花板）；对照：收盘 / 开盘 − 1。
  d) 规模：账户每年约 62 / 9.75 ≈ 6.4 笔个股新仓（B3 的 J 2017-01〜2026-09 个股层 62 笔）、每笔约 25%、本金 ¥1,000,000（模拟盘）。
统计：平均、中位数、> 0 的比例、日数、每年几天；平均的 95% 区间 = 按「年」整块重抽的自助法 2,000 次（种子 20261019 起，每个量 +1）。
读法（事先写定）：
  R1「开盘急跌时卖 / 不买」：主档 −2% 的 1321 oc 与 on 平均都 < 0、95% 区间上限都 < 0、两半平均都 < 0，且个股版 oc / on 的平均与 1321 同号 →「有用」；
     1321 两个平均都 > 0 且区间下限都 > 0，且个股版同号 →「有害」；其余 →「分不出」。
  R2「盘中跌 2% 就卖」：主档 s = 2% 的 x0 / x1 用 R1 同一个判法（「有用」= 止损之后还在跌）。
  R3「买得更便宜」：只报上限 c) × 每年 6.4 笔 × 25% × ¥1,000,000 = 每年最多能省多少（做不到的天花板），与登记研究 cfb3cbc 的结论放在一起看。
  R4 用法：只用来回答「分钟监测有没有必要、哪个方向好」；任何一条要变成交易规则，都要另行登记、用没看过的数据（别的市场 / 别的年代）检验并由用户同意；
     按〔53〕① 现在不做。
运行：python scripts/open_crash_check.py（只运行一次）→ var/out/open_crash_check.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import calendar_jp as CAL                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

ETF = "1321.T"
START, MID, END = "2009-02-06", "2017-01-01", "2026-09-30"
GAPS = (-0.01, -0.02, -0.03)
STOPS = (0.01, 0.02, 0.03)
MAIN_GAP, MAIN_STOP = -0.02, 0.02
SEED, REPS = 20261019, 2000
TRADES_PER_YEAR = 62 / 9.75                                                  # B3 的 J（2017-01〜2026-09）个股层 62 笔
SLOT, CAPITAL = 0.25, 1_000_000
OUT = "open_crash_check"


def ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """统一成 open / high / low / close（价格都 > 0 的行），按日期排序。"""
    m = {str(c).lower(): c for c in df.columns}
    out = pd.DataFrame({k: pd.to_numeric(df[m[k]], errors="coerce") for k in ("open", "high", "low", "close")},
                       index=pd.DatetimeIndex(df.index).tz_localize(None) if getattr(df.index, "tz", None) else pd.DatetimeIndex(df.index))
    return out[(out > 0).all(axis=1)].sort_index()


def consecutive(idx: pd.DatetimeIndex) -> np.ndarray:
    """第 i 行的前一行正好是前一个东证交易日（中间缺行的不算）。"""
    ok = np.zeros(len(idx), dtype=bool)
    for i in range(1, len(idx)):
        ok[i] = idx[i - 1].date() == CAL.prev_trading_day(idx[i].date())
    return ok


def day_table(e: pd.DataFrame) -> pd.DataFrame:
    """每一天：g 跳空、oc 开盘→收盘、on 开盘→次日收盘（次日也要连续）、lo 开盘→最低。"""
    ok = consecutive(e.index)
    nxt = np.r_[ok[1:], False]
    g = (e["open"] / e["close"].shift(1) - 1).where(ok)
    on = (e["close"].shift(-1) / e["open"] - 1).where(nxt)
    return pd.DataFrame({"g": g, "oc": e["close"] / e["open"] - 1, "on": on, "lo": e["low"] / e["open"] - 1}, index=e.index)


def stop_table(e: pd.DataFrame, s: float) -> pd.DataFrame:
    """盘中从开盘跌 s 就卖（理想成交在 开盘 ×(1 − s)）：触发的日子 x0 = 收盘 / 卖价 − 1、x1 = 次日收盘 / 卖价 − 1。"""
    nxt = np.r_[consecutive(e.index)[1:], False]
    px = e["open"] * (1 - s)
    hit = e["low"] <= px
    x1 = (e["close"].shift(-1) / px - 1).where(nxt)
    return pd.DataFrame({"x0": (e["close"] / px - 1)[hit], "x1": x1[hit]})


def panel(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """个股 → 宽表（行 = 东证交易日的并集，列 = 个股）；nxt 标出下一行是不是下一个交易日。"""
    P = {k: pd.DataFrame({t: f[k] for t, f in frames.items()}).sort_index() for k in ("open", "high", "low", "close")}
    idx = P["open"].index
    P["nxt"] = pd.Series(np.r_[consecutive(idx)[1:], False], index=idx)
    return P


def stock_gap_means(P: dict, days: pd.DatetimeIndex) -> pd.DataFrame:
    """给定的日子里，开了盘的个股 oc / on 先按天等权平均。"""
    o, c = P["open"], P["close"]
    oc = (c / o - 1)
    on = (c.shift(-1) / o - 1).where(P["nxt"], axis=0)
    d = days.intersection(o.index)
    return pd.DataFrame({"oc": oc.loc[d].mean(axis=1), "on": on.loc[d].mean(axis=1)})


def stock_stop_means(P: dict, s: float) -> pd.DataFrame:
    """每只个股自己的「盘中从开盘跌 s 就卖」：触发的个股 x0 / x1 先按天平均（没有触发的日子不算）。"""
    o, lo, c = P["open"], P["low"], P["close"]
    px = o * (1 - s)
    hit = lo <= px
    x0 = (c / px - 1).where(hit)
    x1 = (c.shift(-1) / px - 1).where(hit).where(P["nxt"], axis=0)
    out = pd.DataFrame({"x0": x0.mean(axis=1), "x1": x1.mean(axis=1)})
    return out[hit.any(axis=1)]


def year_block_ci(x: pd.Series, seed: int, reps: int = REPS) -> list[float]:
    groups = [g.to_numpy() for _, g in x.groupby(x.index.year)]
    if len(groups) < 2:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    k = len(groups)
    means = np.empty(reps)
    for r in range(reps):
        means[r] = np.concatenate([groups[i] for i in rng.integers(0, k, k)]).mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [float(lo), float(hi)]


def years_span(a: str = START, b: str = END) -> float:
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25


def summarize(x: pd.Series, seed: int) -> dict:
    x = pd.Series(x).dropna()
    if x.empty:
        return {"n": 0}
    h1, h2 = x[x.index < pd.Timestamp(MID)], x[x.index >= pd.Timestamp(MID)]
    return {"n": int(len(x)), "per_year": float(len(x) / years_span()), "mean": float(x.mean()), "median": float(x.median()),
            "pos": float((x > 0).mean()), "ci": year_block_ci(x, seed),
            "h1": float(h1.mean()) if len(h1) else float("nan"), "h2": float(h2.mean()) if len(h2) else float("nan"),
            "n1": int(len(h1)), "n2": int(len(h2))}


def judge(a: dict, b: dict, sa: dict | None = None, sb: dict | None = None) -> str:
    """R1 / R2 的判法：a / b = 1321 的当天 / 到次日（< 0 = 之后还在跌）；sa / sb = 个股版（只看与 1321 同不同号）。"""
    if not a.get("n") or not b.get("n"):
        return "分不出"
    same = sa is None or sb is None or (np.sign(sa.get("mean", np.nan)) == np.sign(a["mean"]) and np.sign(sb.get("mean", np.nan)) == np.sign(b["mean"]))
    neg = all(x["mean"] < 0 and x["ci"][1] < 0 and x["h1"] < 0 and x["h2"] < 0 for x in (a, b))
    pos = all(x["mean"] > 0 and x["ci"][0] > 0 for x in (a, b))
    if neg and same:
        return "有用"
    if pos and same:
        return "有害"
    return "分不出"


def run_all() -> dict:
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    e = ohlc(load_universe([ETF], DataConfig(provider="yfinance", years=27, allow_synthetic=False).validate())[ETF]).loc[START:END]
    raw = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    P = panel({t: ohlc(df).loc[START:END] for t, df in raw.items() if t != ETF})
    D = day_table(e)
    n_days = int(D["g"].notna().sum())
    res: dict = {"meta": {"etf": ETF, "start": str(e.index[0].date()), "end": str(e.index[-1].date()), "days": n_days,
                          "stocks": int(P["open"].shape[1]), "years": years_span(), "mid": MID}, "gap": {}, "stop": {}}
    k = 0
    for thr in GAPS:
        days = D.index[D["g"] <= thr]
        sm = stock_gap_means(P, days)
        r = {"etf_oc": summarize(D.loc[days, "oc"], SEED + k), "etf_on": summarize(D.loc[days, "on"], SEED + k + 1),
             "etf_lo": summarize(D.loc[days, "lo"], SEED + k + 2),
             "stk_oc": summarize(sm["oc"], SEED + k + 3), "stk_on": summarize(sm["on"], SEED + k + 4)}
        k += 5
        r["verdict"] = judge(r["etf_oc"], r["etf_on"], r["stk_oc"], r["stk_on"]) if thr == MAIN_GAP else None
        res["gap"][f"{thr:+.0%}"] = r
    for s in STOPS:
        T, S = stop_table(e, s), stock_stop_means(P, s)
        r = {"etf_x0": summarize(T["x0"], SEED + k), "etf_x1": summarize(T["x1"], SEED + k + 1),
             "stk_x0": summarize(S["x0"], SEED + k + 2), "stk_x1": summarize(S["x1"], SEED + k + 3)}
        k += 4
        r["verdict"] = judge(r["etf_x0"], r["etf_x1"], r["stk_x0"], r["stk_x1"]) if s == MAIN_STOP else None
        res["stop"][f"{s:.0%}"] = r
    o, lo, c = P["open"], P["low"], P["close"]
    res["ceiling"] = {"etf_low": summarize(1 - e["low"] / e["open"], SEED + k), "etf_close": summarize(e["close"] / e["open"] - 1, SEED + k + 1),
                      "stk_low": summarize((1 - lo / o).mean(axis=1), SEED + k + 2), "stk_close": summarize((c / o - 1).mean(axis=1), SEED + k + 3)}
    g2 = res["gap"][f"{MAIN_GAP:+.0%}"]
    share = g2["etf_oc"].get("n", 0) / max(n_days, 1)
    res["scale"] = {"trades_per_year": TRADES_PER_YEAR, "gap_share": share, "entries_hit_per_year": TRADES_PER_YEAR * share,
                    "yen_entries_per_year": TRADES_PER_YEAR * share * SLOT * CAPITAL * abs(g2["stk_oc"].get("mean", 0.0)),
                    "yen_full_exposure_per_year": g2["etf_oc"].get("per_year", 0.0) * CAPITAL * abs(g2["etf_oc"].get("mean", 0.0)),
                    "yen_ceiling_buy_per_year": TRADES_PER_YEAR * SLOT * CAPITAL * res["ceiling"]["stk_low"].get("mean", 0.0)}
    res["R1"], res["R2"] = g2["verdict"], res["stop"][f"{MAIN_STOP:.0%}"]["verdict"]
    return res


def _pct(x: float | None, nd: int = 2) -> str:
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x * 100:+.{nd}f}%"


def _row(name: str, s: dict) -> str:
    if not s.get("n"):
        return f"| {name} | 0 | — | — | — | — | — | — | — |"
    return (f"| {name} | {s['n']:,} | {s['per_year']:.1f} | {_pct(s['mean'])} | {_pct(s['median'])} | {s['pos'] * 100:.0f}% | "
            f"{_pct(s['ci'][0])} 〜 {_pct(s['ci'][1])} | {_pct(s['h1'])} | {_pct(s['h2'])} |")


HEAD = "| 量 | 日数 | 每年 | 平均 | 中位数 | > 0 | 95% 区间（按年重抽） | 前一半 2009〜2016 | 后一半 2017〜 |\n|---|---|---|---|---|---|---|---|---|"


def write(res: dict) -> None:
    m, sc = res["meta"], res["scale"]
    L = [f"# 开盘时按分钟看日経有没有必要（只描述；`scripts/open_crash_check.py`，2026-10-04 先提交读法、再只运行一次）", "",
         f"数据：{m['etf']} 日线 {m['start']}〜{m['end']}（{m['days']:,} 个连续交易日，约 {m['years']:.1f} 年）+ 股票池 {m['stocks']} 只个股同期（Yahoo 复权）。"
         "不是交易规则；不改模拟盘 / 执行器。", "",
         f"**R1「开盘急跌（1321 跳空 ≤ −2%）时卖 / 不买」：{res['R1']}**　　**R2「盘中从开盘跌 2% 就卖」：{res['R2']}**", "",
         "## 一 急跌开盘日：开盘之后还在跌吗（< 0 = 还在跌 → 开盘卖有用、晚点买更便宜；> 0 = 反弹 → 开盘卖卖在低处）", ""]
    for key, r in res["gap"].items():
        L += [f"### 跳空 ≤ {key}" + ("（主档）" if r["verdict"] is not None else ""), "", HEAD,
              _row("1321 开盘→收盘", r["etf_oc"]), _row("1321 开盘→次日收盘", r["etf_on"]), _row("1321 开盘→当天最低", r["etf_lo"]),
              _row("个股（按天平均）开盘→收盘", r["stk_oc"]), _row("个股 开盘→次日收盘", r["stk_on"]), ""]
    L += ["## 二 盘中从开盘跌 s 就卖（理想成交在 开盘 ×(1 − s)；< 0 = 卖了之后还在跌 → 有用；> 0 = 卖低了）", ""]
    for key, r in res["stop"].items():
        L += [f"### s = {key}" + ("（主档）" if r["verdict"] is not None else ""), "", HEAD,
              _row("1321 卖价→收盘", r["etf_x0"]), _row("1321 卖价→次日收盘", r["etf_x1"]),
              _row("个股（按天平均）卖价→收盘", r["stk_x0"]), _row("个股 卖价→次日收盘", r["stk_x1"]), ""]
    ce = res["ceiling"]
    L += ["## 三 「买得更便宜」的天花板（全部交易日）", "", HEAD,
          _row("1321 正好买在最低（1 − 最低/开盘）", ce["etf_low"]), _row("1321 收盘买（收盘/开盘 − 1）", ce["etf_close"]),
          _row("个股 正好买在最低（按天平均）", ce["stk_low"]), _row("个股 收盘买（按天平均）", ce["stk_close"]), "",
          "## 四 规模（账户：每年约 6.4 笔个股新仓、每笔 25%、本金 ¥1,000,000）", "",
          f"- 急跌开盘日（1321 跳空 ≤ −2%）占交易日 {sc['gap_share'] * 100:.2f}% → 每年会碰上的新仓约 {sc['entries_hit_per_year']:.2f} 笔；"
          f"按个股开盘→收盘的平均算，每年差约 ¥{sc['yen_entries_per_year']:,.0f}",
          f"- 假如全部资金（¥1,000,000）都在日本股票、每个急跌开盘日开盘全卖：按 1321 开盘→收盘的平均，每年差约 ¥{sc['yen_full_exposure_per_year']:,.0f}（上限的量级）",
          f"- 「买得更便宜」：每次都正好买在当天最低（做不到）每年最多省约 ¥{sc['yen_ceiling_buy_per_year']:,.0f}；"
          "以前的登记研究（cfb3cbc）：晚点买实际没有改善（全天分批 +0.009%、t 0.20）", "",
          "## 读法（事先写定）", "",
          "- R1 / R2：主档的 1321 当天与到次日两个平均都 < 0、95% 区间上限都 < 0、两半都 < 0，且个股版同号 →「有用」；两个平均都 > 0 且区间下限都 > 0、个股同号 →「有害」；其余「分不出」",
          "- R3：只报天花板，与 cfb3cbc 一起看；R4：只回答问题，任何一条要变成规则都要另行登记、用没看过的数据检验、用户同意（按〔53〕① 现在不做）", "",
          "非投资建议。"]
    (paths.out_dir() / f"{OUT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def main() -> int:
    res = run_all()
    write(res)
    print(f"R1 {res['R1']} / R2 {res['R2']}；见 var/out/{OUT}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
