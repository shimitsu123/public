"""leap_r6b_sleeve.py — 第 6 轮探索（组合层面）：高成交量溢价的每月仓位放进 S0C2（只描述、不登记；只用 E 2006〜2016 与 J 2017〜2026）。

第 6 轮描述统计（var/out/leap_r6_explore.md）：每月末按「最近完成的一周成交量 ÷ 之前 10 周平均」排前 K 只拿一个月 ——
E 日経225 前 4 只 年化 17.7%（等权 4.8%）；J 时点 TOPIX 500 前 8 只 16.1%（等权 10.2%）；「放量 ∧ 那周上涨」J 两个股票池都很好、E 一般。
这里放进同一个引擎（4 个名额、宏观 / 状态层倍数、止损照旧）：
  每月最后一个交易日收盘按分数排前 8 标为买入候选（分数高的先买，买不起一手的跳过），买入后拿 20 个交易日（到期第二天开盘卖；
  这种仓位不看 MACD 死叉），止损照旧。
  V1 量比最高；V2 量比最高 ∧ 那周上涨；V3 = V1 但只在周线量比 ≥ 1.5；
  M1 现行 W2 突破 + V1 仓位一起（名额共用，同一天突破优先）；M2 现行 W2 突破 + V2 仓位一起。
股票池：E = 今天的日経225；J = 今天的日経225 与时点 TOPIX 500（无幸存者偏差）。
输出：var/out/leap_r6b_sleeve.md / .json（只有统计）
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
import leap_r6_explore as R6                                                 # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from leap_r2c_sleeve import month_end_flags                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

TOP, HOLD = 8, 20
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_picks(fr: dict, score: dict[str, np.ndarray], member: dict[str, np.ndarray], top: int = TOP) -> dict[str, np.ndarray]:
    """月末（按全部票的共同日历）在当天是成员、分数有值的票里排前 top → 那一天标 True。"""
    days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in fr.values()])))
    S = pd.DataFrame({t: pd.Series(np.where(member[t], score[t], np.nan), index=fr[t].index) for t in fr}).reindex(days)
    me = pd.Series(month_end_flags(days), index=days)
    rk = S.rank(axis=1, ascending=False, method="first")
    return {t: (me.reindex(df.index).to_numpy(bool) & (rk[t].reindex(df.index).to_numpy() <= top)) for t, df in fr.items()}


def setting(era: str, jmem: str | None) -> dict:
    from qbreak.trader import load_params
    t0 = time.time()
    ctx = LF.context(era, jmem=jmem or "U0") if era == "J" else LF.context(era)
    p = load_params(market="JP")
    fr = LF.frames(ctx, p)
    mem = LF.member_mask(ctx, fr)
    fr = LF.with_mask(fr, mem)
    run_fn = LF.runner(ctx, fr)
    P, days = ctx["P"], ctx["days"]
    C = np.where(np.isfinite(P["C"]), P["C"], np.nan)
    Rv, Wr = R6.weekly_ratio(P["V"], C, days)
    col = {t: j for j, t in enumerate(ctx["names"])}
    di = pd.Index(days)
    g = lambda A: {t: A[di.get_indexer(fr[t].index), col[t]] for t in fr}                                     # noqa: E731
    s1, s2 = g(Rv), g(np.where(Wr > 0, Rv, np.nan))
    s3 = g(np.where(Rv >= 1.5, Rv, np.nan))
    brk = {t: df["entry"].to_numpy(bool) for t, df in fr.items()}
    res = {"现行（W2 突破）": LF.run(ctx, run_fn, fr, p), "只有核心": LF.run(ctx, run_fn, LF.no_entries(fr), p)}
    for key, sc, mix in (("V1 量比最高（每月、拿 20 天）", s1, False), ("V2 量比最高 ∧ 那周上涨", s2, False),
                         ("V3 量比最高且 ≥ 1.5", s3, False), ("M1 W2 突破 + V1", s1, True), ("M2 W2 突破 + V2", s2, True)):
        pk = month_picks(fr, sc, mem)
        ent = {t: (pk[t] | brk[t]) if mix else pk[t] for t in fr}
        pb = {t: set(fr[t].index[pk[t] & ~brk[t]]) if mix else set(fr[t].index[pk[t]]) for t in fr}
        prio = {(t, d): (1e6 if mix and b else float(v)) for t in fr
                for d, v, e, b in zip(fr[t].index, sc[t], ent[t], brk[t]) if e and (np.isfinite(v) or b)}
        f2 = {t: df.assign(entry=ent[t]) for t, df in fr.items()}
        res[key] = LF.run(ctx, run_fn, f2, p, pb=pb, hold_pb=HOLD, priority=prio)
    return {"res": res, "secs": round(time.time() - t0), "n": len(fr)}


def main() -> int:
    t0 = time.time()
    say(f"# 第 6 轮探索（组合层面）：高成交量溢价的每月仓位（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r6b_sleeve.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股笔数 每笔净收益 / 胜率（组合里的交易）。")
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
    fp = paths.out_dir() / "leap_r6b_sleeve"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
