"""leap_r7_explore.py — 「质的飞跃」第 7 轮探索：核心 + 最多一半资金的日本个股仓位（分散），只在日本牛市买（只描述、不登记；E / J）。

第 1〜6 轮：日本个股仓位（不管怎么选）占用 4 个名额时挤掉了更强的核心；描述统计里一些仓位本身的风险收益和核心差不多、
与核心的月收益相关只有 0.3〜0.6 → 如果只用一半资金，可能靠分散把回撤降下来（Calmar 提高）。这里：
  名额 2 个（每个 25% → 个股最多 50%），日本熊市（现行牛熊分界，收盘时判定）第二天不开新仓；其余照 S0C2。
  H1 3 年跌得最多（月末前 8 候选、跌出前 8 卖）；H2 股息率最高（同）；H3 便宜 = 股息率 + 3 年跌（同）；
  H4 量比 ≥ 1.5 的放量（月末前 8 候选、拿 20 天）；H5 现行 W2 突破但只用 2 个名额（对照：只是少做个股）。
股票池：E = 今天的日経225；J = 今天的日経225 与时点 TOPIX 500。
输出：var/out/leap_r7_explore.md / .json（只有统计）
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
import leap_r6_explore as R6                                                 # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from leap_r2c_sleeve import sleeve_frames                                    # noqa: E402
from leap_r6b_sleeve import HOLD, month_picks                                # noqa: E402
from qbreak import paths                                                     # noqa: E402

SLOTS = {"max_positions": 2}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


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
    col = {t: j for j, t in enumerate(ctx["names"])}
    di = pd.Index(days)
    g = lambda A: {t: A[di.get_indexer(fr[t].index), col[t]] for t in fr}                                     # noqa: E731
    LR = R1.long_returns(C)
    ltr = g(-LR["r3y"])
    dy = {t: LD.div_yield(LD.actions(t), fr[t].index).to_numpy() for t in fr}
    D = pd.DataFrame({t: pd.Series(dy[t], index=fr[t].index) for t in fr}).reindex(days)
    Lt = pd.DataFrame({t: pd.Series(ltr[t], index=fr[t].index) for t in fr}).reindex(days)
    Mm = pd.DataFrame({t: pd.Series(mem[t], index=fr[t].index) for t in fr}).reindex(days).fillna(False).astype(bool)
    comp = (D.where(Mm).rank(axis=1, pct=True) + Lt.where(Mm).rank(axis=1, pct=True)) / 2
    val = {t: comp[t].reindex(fr[t].index).to_numpy(float) for t in fr}
    Rv, _ = R6.weekly_ratio(P["V"], C, days)
    v3 = g(np.where(Rv >= 1.5, Rv, np.nan))
    kw = {"cfg_over": SLOTS, "jp_bull_only": True}
    res = {"现行（W2 突破，4 名额）": LF.run(ctx, run_fn, fr, p), "只有核心": LF.run(ctx, run_fn, LF.no_entries(fr), p)}
    for key, sc in (("H1 3 年跌得最多", ltr), ("H2 股息率最高", dy), ("H3 便宜（股息率 + 3 年跌）", val)):
        f2, pr = sleeve_frames(fr, sc, mem)
        res[key] = LF.run(ctx, run_fn, f2, p, priority=pr, **kw)
    pk = month_picks(fr, v3, mem)
    prio = {(t, d): float(v) for t in fr for d, v, e in zip(fr[t].index, v3[t], pk[t]) if e}
    res["H4 放量（量比 ≥ 1.5，拿 20 天）"] = LF.run(ctx, run_fn, {t: df.assign(entry=pk[t]) for t, df in fr.items()}, p,
                                           pb={t: set(fr[t].index[pk[t]]) for t in fr}, hold_pb=HOLD, priority=prio, **kw)
    res["H5 W2 突破只用 2 名额（对照）"] = LF.run(ctx, run_fn, fr, p, **kw)
    return {"res": res, "secs": round(time.time() - t0), "n": len(fr)}


def main() -> int:
    t0 = time.time()
    say(f"# 「质的飞跃」第 7 轮探索：核心 + 最多一半资金的个股仓位（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r7_explore.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股笔数 每笔净收益 / 胜率（组合里的交易）。")
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
    fp = paths.out_dir() / "leap_r7_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
