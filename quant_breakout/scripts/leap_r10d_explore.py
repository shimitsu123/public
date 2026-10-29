"""leap_r10d_explore.py — 第 10 轮补充探索（只描述、不登记；E / J）：只用纳指、或「一次只拿最强的一个 ETF」。

第 10 轮补充（leap_r10b / r10c）：黄金 + 纳指 趋势仓位 E 全期、J 都大幅变好，但 E 后半（2011〜2016）都不如现行；
相对动量能改善 E 后半但削弱其他。这里：
  N1 只有纳指趋势（10 个月均线）；N2 纳指（10 个月均线 ∧ 12 个月涨）；
  O1 黄金 / 纳指 里只拿一个：两个都趋势向上时拿 12 个月涨幅大的那个（月末换）；O2 = O1 再要求 12 个月涨幅 > 核心。
注意：纳指在 2000〜2005 的走势在 ndx_study 里看过（主判定 1987〜2005）；「核心换纳指」（㉔）仍待用户决定 —— 纳指趋势仓位是它的局部版。
输出：var/out/leap_r10d_explore.md / .json（只有统计）
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
from leap_r10b_explore import trend_frame_v                                  # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from leap_r2c_sleeve import month_end_flags                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def one_of(raw: dict[str, pd.DataFrame], core: pd.Series | None, months: int = 10, vs_core: bool = False) -> dict[str, pd.DataFrame]:
    """每个月末：各自「收盘 > months 个月均线」的里面，12 个月涨幅最大的那一个（可选：还要 > 核心的 12 个月涨幅）→ 下个月拿它；
    其余月末卖。只用月末为止的数据。"""
    idx = raw[next(iter(raw))].index
    for df in raw.values():
        idx = idx.intersection(df.index)
    me = pd.Series(month_end_flags(idx), index=idx)
    mdays = idx[me.to_numpy()]
    score = {}
    for k, df in raw.items():
        mc = df["Close"].reindex(mdays).astype(float)
        up = mc > mc.rolling(months, min_periods=months).mean()
        r12 = mc / mc.shift(12) - 1
        s = r12.where(up)
        if vs_core and core is not None:
            cc = core.reindex(core.index.union(mdays)).ffill().reindex(mdays)
            s = s.where(r12 > cc / cc.shift(12) - 1)
        score[k] = s
    S = pd.DataFrame(score)
    best = S.fillna(-np.inf).idxmax(axis=1).where(S.notna().any(axis=1))           # 全部缺值的月份 → 不拿
    out = {}
    for k, df in raw.items():
        pick_m = (best == k).reindex(idx).ffill().fillna(False).astype(bool).reindex(df.index).fillna(False).astype(bool)
        mef = pd.Series(month_end_flags(df.index), index=df.index).to_numpy()
        o = df.copy()
        o["entry"], o["dead_cross"], o["climax"], o["atr"] = pick_m.to_numpy(), mef & ~pick_m.to_numpy(), False, np.nan
        out[k] = o
    return out


def setting(era: str) -> dict:
    from bullbear_study import SYM, load
    from qbreak import tick
    from qbreak.trader import load_params
    from unified_study import spx_jpy_on_jp_days
    t0 = time.time()
    ctx = LF.context(era)
    p = load_params(market="JP")
    fr = LF.frames(ctx, p)
    jp_days = load(*SYM["JP"]).index
    jp_days = jp_days[jp_days >= pd.Timestamp("2000-01-01")]
    fx = load("JPY=X", "1996-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    core = spx_jpy_on_jp_days(load(*SYM["US"]), fx, jp_days)["Close"]
    base = R10.etf_trend_frames(jp_days, ["G1540.T", "N1545.T"])
    raw = {k: v[["Open", "High", "Low", "Close", "Volume"]] for k, v in base.items()}
    for t in raw:
        tick.LOT_OVERRIDE[t] = 1
    run_fn = LF.runner({**ctx, "days": ctx["days"].union(jp_days)}, {**fr, **base})
    off = {t: df.assign(entry=False) for t, df in base.items()}
    pt = R10.trend_params(p)
    res = {"现行（W2 突破）": LF.run(ctx, run_fn, {**fr, **off}, p), "只有核心": LF.run(ctx, run_fn, {**LF.no_entries(fr), **off}, p)}
    variants = {"N1 纳指趋势（10 个月）": {"N1545.T": trend_frame_v(raw["N1545.T"], 10, False)},
                "N2 纳指（10 个月 ∧ 12 个月涨）": {"N1545.T": trend_frame_v(raw["N1545.T"], 10, True)},
                "O1 黄金 / 纳指只拿最强的一个": one_of(raw, None),
                "O2 O1 且比核心强": one_of(raw, core, vs_core=True)}
    for key, tf in variants.items():
        ks = list(tf)
        f2 = {**fr, **{k: (tf[k] if k in tf else off[k]) for k in raw}}
        pb = {k: set(tf[k].index[tf[k]["entry"].to_numpy(bool)]) for k in ks}
        prio = {(k, d): 1e6 for k in ks for d in pb[k]}
        res[key] = LF.run(ctx, run_fn, f2, p, pb=pb, hold_pb=10 ** 6, pb_use_dead=True, pb_free=True, priority=prio,
                          params_t={k: pt for k in ks})
    return {"res": res, "secs": round(time.time() - t0)}


def main() -> int:
    t0 = time.time()
    say(f"# 第 10 轮补充探索：只用纳指 / 一次只拿最强的一个 ETF（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r10d_explore.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股 + ETF 笔数 每笔净收益 / 胜率。")
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
        say("\n| 方案 | " + " | ".join(yrs) + " |")
        say("|---|" + "---|" * len(yrs))
        for k, r in s["res"].items():
            yv = r.get("_years") or {}
            say(f"| {k} | " + " | ".join(f"{yv[y]:+.1f}" if y in yv else "—" for y in yrs) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r10d_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
