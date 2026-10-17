"""leap_r2c_sleeve.py — 第 2 轮探索（组合层面）：每月选股仓位代替突破（只描述、不登记；只用 E 2006〜2016 与 J 2017〜2026）。

第 2 轮的描述统计（var/out/leap_r2_explore.md、leap_r2b_pit.md）：动量选股的高收益主要是幸存者偏差（时点 TOPIX 500 上 Calmar ≈ 等权）；
「3 年跌得最多」（长期反转）在时点 TOPIX 500 上 年化 15.7% vs 等权 10.2%（K = 8）。这里放进 S0C2（同一个引擎、同样 4 个名额、
同样的宏观 / 状态层倍数、止损照旧）：
  每月最后一个交易日收盘：按分数在当天股票池里排前 8 的票标为「买入候选」（同一天按分数高的先买，买不起一手的跳过）；
  持仓里跌出前 8 的 → 那天标为卖出（第二天开盘卖）；还在前 8 的继续拿。MACD 死叉不再用来卖（这个仓位不看突破）。
  S1 3 年跌得最多（跳过最近 1 个月）；S2 股息率最高；S3 两者的百分位平均（「便宜」）；S4 = S3 但只在 W2 周线量比 ≥ 1.0 时买。
股票池：E = 今天的日経225；J = 今天的日経225 与时点 TOPIX 500（无幸存者偏差）。
输出：var/out/leap_r2c_sleeve.md / .json（只有统计）
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
import leap_data as LD                                                       # noqa: E402
import leap_r1_explore as R1                                                 # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

TOP = 8
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_end_flags(idx: pd.DatetimeIndex) -> np.ndarray:
    """这个交易日是不是当月最后一个交易日（按这只票自己的日历）。"""
    p = idx.to_period("M")
    return np.r_[p[1:] != p[:-1], True]


def sleeve_frames(fr: dict, score: dict[str, np.ndarray], member: dict[str, np.ndarray], top: int = TOP,
                  extra_keep: dict[str, np.ndarray] | None = None) -> tuple[dict, dict]:
    """月末按分数排前 top → entry（候选）；跌出前 top → dead_cross（卖）。返回（新指标表, 优先级 {(票, 日): 分数}）。
    排名只在当天是成员、分数有值的票之间比（同一天所有票一起排）。"""
    days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in fr.values()])))
    S = pd.DataFrame({t: pd.Series(np.where(member[t], score[t], np.nan), index=fr[t].index) for t in fr}).reindex(days)
    me = pd.Series(month_end_flags(days), index=days)
    rk = S.rank(axis=1, ascending=False, method="first")
    out, prio = {}, {}
    for t, df in fr.items():
        r = rk[t].reindex(df.index)
        m = me.reindex(df.index).to_numpy(bool)
        sel = m & (r.to_numpy() <= top)
        drop = m & ~(r.to_numpy() <= top)
        ent = sel & (np.asarray(extra_keep[t], bool) if extra_keep and t in extra_keep else True)
        out[t] = df.assign(entry=ent, dead_cross=drop)
        for d, v in zip(df.index[ent], S[t].reindex(df.index).to_numpy()[ent]):
            prio[(t, d)] = float(v)
    return out, prio


def setting(era: str, jmem: str | None) -> dict:
    from qbreak.trader import load_params
    t0 = time.time()
    ctx = LF.context(era, jmem=jmem or "U0") if era == "J" else LF.context(era)
    p = load_params(market="JP")
    fr = LF.frames(ctx, p)
    mem = LF.member_mask(ctx, fr)
    fr = LF.with_mask(fr, mem)
    run_fn = LF.runner(ctx, fr)
    days, names = ctx["days"], list(fr)
    col = {t: j for j, t in enumerate(ctx["names"])}
    C = ctx["P"]["C"]
    LR = R1.long_returns(np.where(np.isfinite(C), C, np.nan))
    di = pd.Index(days)
    ltr = {t: -LR["r3y"][di.get_indexer(fr[t].index), col[t]] for t in names}
    dy = {t: LD.div_yield(LD.actions(t), fr[t].index).to_numpy() for t in names}
    D = pd.DataFrame({t: pd.Series(dy[t], index=fr[t].index) for t in names}).reindex(days)
    Lt = pd.DataFrame({t: pd.Series(ltr[t], index=fr[t].index) for t in names}).reindex(days)
    Mm = pd.DataFrame({t: pd.Series(mem[t], index=fr[t].index) for t in names}).reindex(days).fillna(False).astype(bool)
    comp = (D.where(Mm).rank(axis=1, pct=True) + Lt.where(Mm).rank(axis=1, pct=True)) / 2
    val = {t: comp[t].reindex(fr[t].index).to_numpy(float) for t in names}
    wk = LF.w2_keep(ctx, fr)                                                           # 周线量比 ≥ 1.0（W2 同一定义）
    res = {"现行（W2 突破）": LF.run(ctx, run_fn, fr, p), "只有核心": LF.run(ctx, run_fn, LF.no_entries(fr), p)}
    for key, sc, extra in (("S1 3 年跌得最多", ltr, None), ("S2 股息率最高", dy, None), ("S3 便宜（股息率 + 3 年跌）", val, None),
                           ("S4 S3 ∧ 周线量比 ≥ 1.0", val, wk)):
        f2, pr = sleeve_frames(fr, sc, mem, TOP, extra)
        res[key] = LF.run(ctx, run_fn, f2, p, priority=pr)
    return {"res": res, "secs": round(time.time() - t0), "n": len(names)}


def main() -> int:
    t0 = time.time()
    say(f"# 第 2 轮探索（组合层面）：每月选股仓位代替突破（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r2c_sleeve.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股笔数 每笔净收益 / 胜率（组合里的交易）。")
    out = {}
    for era, jm, lab in (("E", None, "E 2006-10〜2016-09 · 今天的日経225"), ("J", "U0", "J 2017-01〜2026-09 · 今天的日経225"),
                         ("J", "U1", "J · 时点 TOPIX 500（无幸存者偏差）")):
        s = setting(era, jm)
        out[f"{era}/{jm}"] = {k: {w: v for w, v in r.items() if not w.startswith("_")} for k, r in s["res"].items()}
        say(f"\n## {lab}（{s['n']} 只；{s['secs']}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|")
        for k, r in s["res"].items():
            say(f"| {k} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r2c_sleeve"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
