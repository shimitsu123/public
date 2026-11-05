"""leap_r10b_explore.py — 第 10 轮的补充探索（只描述、不登记；E / J）：趋势仓位的几个标准变体 + 逐年收益。

第 10 轮（var/out/leap_r10_explore.md）：黄金（+ 纳指）趋势仓位让 J 大幅变好（Calmar 0.389 → 0.60〜0.66、回撤 −35.6% → −24%），
E 全期也好（0.298 → 0.35〜0.36、回撤 −28.8% → −22%），但 E 后半 2011〜2016 变差（0.98 → 0.64〜0.70）。这里只试文献里的标准变体
（不做任意调参）：
  A 10 个月均线（= 第 10 轮）；B 12 个月均线；C 10 个月均线 ∧ 12 个月绝对动量 > 0（Antonacci 的双重条件）；
  D = A 但突破信号优先（ETF 只用突破没用的名额）。都是 黄金 与 黄金 + 纳指 两组。并列出逐年收益。
输出：var/out/leap_r10b_explore.md / .json（只有统计）
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
import leap_r10_explore as R10                                               # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from leap_r2c_sleeve import month_end_flags                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def trend_frame_v(df: pd.DataFrame, months: int, absmom: bool) -> pd.DataFrame:
    c = df["Close"].astype(float)
    me = pd.Series(month_end_flags(df.index), index=df.index)
    mc = c[me.to_numpy()]
    up_m = mc > mc.rolling(months, min_periods=months).mean()
    if absmom:
        up_m = up_m & (mc > mc.shift(12))
    up_d = up_m.reindex(df.index).ffill().fillna(False).astype(bool)
    out = df.copy()
    out["entry"], out["dead_cross"], out["climax"], out["atr"] = up_d.to_numpy(), me.to_numpy() & ~up_d.to_numpy(), False, np.nan
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
    base = R10.etf_trend_frames(jp_days, ["G1540.T", "N1545.T"])
    raw = {k: v[["Open", "High", "Low", "Close", "Volume"]] for k, v in base.items()}
    for t in raw:
        tick.LOT_OVERRIDE[t] = 1
    run_fn = LF.runner({**ctx, "days": ctx["days"].union(jp_days)}, {**fr, **base})
    off = {t: df.assign(entry=False) for t, df in base.items()}
    pt = R10.trend_params(p)
    res = {"现行（W2 突破）": LF.run(ctx, run_fn, {**fr, **off}, p), "只有核心": LF.run(ctx, run_fn, {**LF.no_entries(fr), **off}, p)}
    for vk, months, absmom, brk_first in (("A 10 个月", 10, False, False), ("B 12 个月", 12, False, False),
                                          ("C 10 个月 ∧ 12 个月涨", 10, True, False), ("D 10 个月，突破优先", 10, False, True)):
        tf = {k: trend_frame_v(raw[k], months, absmom) for k in raw}
        for ks, lab in ((["G1540.T"], "黄金"), (["G1540.T", "N1545.T"], "黄金 + 纳指")):
            f2 = {**fr, **{k: (tf[k] if k in ks else off[k]) for k in raw}}
            pb = {k: set(tf[k].index[tf[k]["entry"].to_numpy(bool)]) for k in ks}
            prio = {(k, d): (-1.0 if brk_first else 1e6) for k in ks for d in pb[k]}
            res[f"{vk} · {lab}"] = LF.run(ctx, run_fn, f2, p, pb=pb, hold_pb=10 ** 6, pb_use_dead=True, pb_free=True, priority=prio,
                                          params_t={k: pt for k in ks})
    return {"res": res, "secs": round(time.time() - t0)}


def main() -> int:
    t0 = time.time()
    say(f"# 第 10 轮补充探索：趋势仓位的标准变体 + 逐年收益（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r10b_explore.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股 + ETF 笔数 每笔净收益 / 胜率。")
    out = {}
    for era in ("E", "J"):
        s = setting(era)
        out[era] = {k: {w: v for w, v in r.items()} for k, r in s["res"].items()}
        say(f"\n## {era}（{s['secs']}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|")
        for k, r in s["res"].items():
            say(f"| {k} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
        yrs = sorted({y for r in s["res"].values() for y in (r.get("_years") or {})})
        a, b = LF.WINDOWS[era] if hasattr(LF, "WINDOWS") else (None, None)
        del a, b
        say("\n| 方案 | " + " | ".join(yrs) + " |")
        say("|---|" + "---|" * len(yrs))
        for k, r in s["res"].items():
            yv = r.get("_years") or {}
            say(f"| {k} | " + " | ".join(f"{yv[y]:+.1f}" if y in yv else "—" for y in yrs) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r10b_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
