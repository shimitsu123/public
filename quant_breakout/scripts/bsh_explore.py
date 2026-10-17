"""bsh_explore.py — 「买点 / 卖点 / 持有时间 横展开」第一步：探索（只用 E / J；Z 不碰，留给登记之后的一次确认）。2026-09-28。

用户（2026-09-28）：「类似做可以优化当前选股策略的研究 方向和现在的选股策略差不多就可以 多加几个有特征的买入卖出 持有时间什么的 横展开一下」。
来由：现行突破的钱来自「亏小赚大」（var/out/signal_study.md 逐笔胜率 42.5%、平均赚 +5.80% / 平均亏 −3.07%；var/out/decay_diag.md 出场 92〜97%
  是 MACD 死叉；2026-09-28 的描述性核算：组合里最好的 10% 交易贡献了净收益之和的 2 倍以上，这次探索的「四」会重算）→ 离场 / 持有时间是没怎么动过的杠杆
  （以前的离场研究多是「另外加一个更早的卖点」，都把大赢家卖早了）；买点这边价量指标已经两两搜遍（S6 / S7），这里只加几个「信号结构」。
规则（运行前写定；结果出来不改）：
一 变体：scripts/bsh_common.VARIANTS（B 买点 5 个、X 卖点 10 个、H 持有时间 5 个；每个只改一处，其余与现行相同）。
二 窗口：E = 2006-10〜2016-09（yfinance 今天的日経225）、J = 2017-01〜2026-09（J-Quants 今天的日経225，真实一手）；半段 E1 / E2、J1 / J2；
   组合 = S0C2（var/sim.json）+ W2，scripts/leap_confirm.py 同一框架（与 perf_attrib / layer_study 的「现行」同一口径）。
三 入选规则（E、J 两个年代都满足）：
   a 组合 Calmar ≥ 现行 + 0.03；b 最大回撤不比现行深 2 pp 以上；c 组合里个股交易的每笔平均净收益 ≥ 现行；
   d 4 个半段（E1 / E2 / J1 / J2）里 Calmar 低于现行的最多 1 个。
   排序：min(E 的 Calmar 差, J 的 Calmar 差) 从大到小；同一族（B / X / H）最多 3 个；互补的一对（B1 / B2、B6 / B7）最多 1 个；最多 5 个。
   没有变体入选 → 这一轮不登记、不用 Z（Z 留着）。入选的写进 scripts/bsh_study.py 开头、提交之后才做一次 Z + E + J + 另一批股票的确认。
四 另报（只描述）：每个变体的胜率 / 平均赚亏 / 盈亏比 / 每笔中位 / 持有天数 / 出场原因 / 最好 10% 的占比、只有核心的 Calmar；
   现行交易的「持有时间」形状：固定持有 5 / 10 / 20 / 40 / 60 个交易日的收益（按收盘价、不扣费用）、持有期里最高点出现在第几天、
   最高点到卖出回吐了多少（毛收益）。
输出：var/out/bsh_explore.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bsh_common as BC                                                     # noqa: E402
from qbreak import paths                                                    # noqa: E402

CAL_UP, DD_TOL, MAX_FINAL, MAX_FAM = 0.03, 2.0, 5, 3
HORIZONS = (5, 10, 20, 40, 60)
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 入选规则（有测试）─────────────────────────
def qualifies(c: dict, b: dict) -> list[str]:
    """c / b：{年代: summary}（候选 / 现行）。返回没满足的条件（空 = 入选）。"""
    f = []
    lows = 0
    for era in ("E", "J"):
        x, y = c.get(era) or {}, b.get(era) or {}
        if not (x.get("calmar") is not None and y.get("calmar") is not None and x["calmar"] >= y["calmar"] + CAL_UP):
            f.append(f"{era} Calmar 没高 {CAL_UP}")
        if not (x.get("dd") is not None and y.get("dd") is not None and x["dd"] >= y["dd"] - DD_TOL):
            f.append(f"{era} 回撤深 {DD_TOL:.0f} pp 以上")
        if not (x.get("mean") is not None and y.get("mean") is not None and x["mean"] >= y["mean"]):
            f.append(f"{era} 每笔不如现行")
        for hx, hy in zip(x.get("halves") or [None, None], y.get("halves") or [None, None]):
            if not (hx is not None and hy is not None and hx >= hy):
                lows += 1
    if lows > 1:
        f.append(f"半段低于现行 {lows} 个")
    return f


def pick(res: dict, base: dict) -> list[str]:
    """按规则选 ≤ 5 个：min(E, J 的 Calmar 差) 从大到小；同族 ≤ 3；互补一对 ≤ 1。"""
    ok = [k for k in res if not qualifies(res[k], base)]
    score = {k: min(res[k][e]["calmar"] - base[e]["calmar"] for e in ("E", "J")) for k in ok}
    out: list[str] = []
    fam: dict[str, int] = {}
    for k in sorted(ok, key=lambda x: (-score[x], x)):
        f = BC.VARIANTS[k]["fam"]
        if fam.get(f, 0) >= MAX_FAM or any(k in pr and any(o in out for o in pr if o != k) for pr in BC.PAIRS):
            continue
        out.append(k)
        fam[f] = fam.get(f, 0) + 1
        if len(out) >= MAX_FINAL:
            break
    return out


# ───────────────────────── 持有时间的形状（只描述）─────────────────────────
def hold_shape(ctx: dict, tr: pd.DataFrame) -> dict:
    """现行交易：固定持有 N 个交易日的毛收益（按收盘价）、持有期最高点在第几天、从最高点回吐多少（毛）。"""
    P, days, col = ctx["P"], ctx["days"], {t: j for j, t in enumerate(ctx["names"])}
    di = pd.Index(days)
    fixed = {h: [] for h in HORIZONS}
    peak_day, peak_gain, give = [], [], []
    for r in tr.itertuples():
        j = col.get(r.ticker)
        if j is None:
            continue
        i0, i1 = di.get_indexer([pd.Timestamp(r.entry_date)])[0], di.get_indexer([pd.Timestamp(r.exit_date)])[0]
        if i0 < 0 or i1 < i0:
            continue
        c, h = P["C"][:, j], P["H"][:, j]
        for n in HORIZONS:
            k = i0 + n - 1
            if k < len(days) and np.isfinite(c[k]):
                fixed[n].append((c[k] / r.entry_px - 1) * 100)
        hh = h[i0:i1 + 1]
        if np.isfinite(hh).any():
            m = int(np.nanargmax(hh))
            pg = (hh[m] / r.entry_px - 1) * 100
            peak_day.append(m + 1)
            peak_gain.append(pg)
            give.append(pg - (r.exit_px / r.entry_px - 1) * 100)
    out = {"fixed": {n: {"n": len(v), "mean": float(np.mean(v)) if v else None, "win": float(np.mean(np.array(v) > 0) * 100) if v else None}
                     for n, v in fixed.items()}}
    if peak_day:
        pdy = np.array(peak_day)
        out.update({"peak_day_med": float(np.median(pdy)), "peak_after20": float((pdy > 20).mean() * 100),
                    "peak_gain_mean": float(np.mean(peak_gain)), "give_back_mean": float(np.mean(give)),
                    "give_back_winners": float(np.mean([g for g, pg in zip(give, peak_gain) if pg >= BC.RELAX_GAIN])) if any(
                        pg >= BC.RELAX_GAIN for pg in peak_gain) else None,
                    "reach10": float(np.mean(np.array(peak_gain) >= BC.RELAX_GAIN) * 100)})
    return out


def fmt_line(k: str, s: dict, pr: dict, base: dict | None) -> str:
    d = (lambda e: f"{s[e]['calmar'] - base[e]['calmar']:+.3f}") if base else (lambda e: "—")
    tp = pr.get("E") or {}, pr.get("J") or {}
    return (f"| {k} | {s['E']['calmar']} / {s['J']['calmar']} | {d('E')} / {d('J')} | {s['E']['dd']}% / {s['J']['dd']}% | "
            f"{s['E']['halves'][0]} · {s['E']['halves'][1]} · {s['J']['halves'][0]} · {s['J']['halves'][1]} | "
            f"{s['E']['n']} / {s['J']['n']} 笔 | {s['E']['win']}% / {s['J']['win']}% | {s['E']['mean']}% / {s['J']['mean']}% | "
            + " / ".join(f"{x['payoff']:.2f}" if x.get("payoff") else "—" for x in tp) + " | "
            + " / ".join(f"{x['hold']:.0f}" if x.get("n") else "—" for x in tp) + " |")


def main() -> int:
    import leap_common as LC
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    say(f"# 买点 / 卖点 / 持有时间 横展开：探索（只用 E / J；{pd.Timestamp.today().date()}）")
    say("规则见 scripts/bsh_explore.py 开头（运行前写定）；变体定义 scripts/bsh_common.py。组合 = S0C2 + W2，今天的日経225。")
    res: dict[str, dict] = {}
    prof: dict[str, dict] = {}
    base: dict = {}
    core: dict = {}
    shape: dict = {}
    for era in ("E", "J"):
        t1 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        r0, tr0 = BC.run_variant(ctx, run_fn, fw, p, None)
        LC.assert_explore_dates(tr0["entry_date"])                          # 探索只准用 2006-10 以后（Z 留给确认）
        base[era] = BC.summary(r0, era)
        rn, trn = BC.run_variant(ctx, run_fn, fw, p, "_neutral")            # 引擎核对：研究用离场代码不改规则时必须与现行一模一样
        same = BC.summary(rn, era) == base[era] and len(trn) == len(tr0) and np.allclose(trn["net"].to_numpy(float), tr0["net"].to_numpy(float))
        say(f"- {era} 引擎核对（研究用离场代码、不改规则）：{'与现行完全相同' if same else '★ 不同 —— 停止'}")
        if not same:
            raise SystemExit(f"{era} 引擎核对不一致：{BC.summary(rn, era)} vs {base[era]}")
        prof.setdefault("现行", {})[era] = BC.trade_profile(tr0)
        shape[era] = hold_shape(ctx, tr0)
        core[era] = BC.summary(LF.run(ctx, run_fn, LF.no_entries(fw), p), era)
        for k in BC.VARIANTS:
            r, tr = BC.run_variant(ctx, run_fn, fw, p, k)
            res.setdefault(k, {})[era] = BC.summary(r, era)
            prof.setdefault(k, {})[era] = BC.trade_profile(tr)
        say(f"- {era}：{len(BC.VARIANTS) + 2} 次组合回测，{round(time.time() - t1)} s")
    say("\n## 一、全部变体（E / J；Calmar 差 = 变体 − 现行；半段 = E1 · E2 · J1 · J2 的 Calmar）")
    say("| 变体 | Calmar E / J | 差 E / J | 最大回撤 E / J | 半段 | 笔数 | 胜率 | 每笔 | 盈亏比 | 持有中位（天）|")
    say("|---|---|---|---|---|---|---|---|---|---|")
    say(fmt_line("现行", base, prof["现行"], None))
    say(fmt_line("只有核心", {e: {**core[e], "n": 0, "win": "—", "mean": "—"} for e in core}, {}, base).replace("0 / 0 笔", "—"))
    for k in BC.VARIANTS:
        say(fmt_line(k, res[k], prof[k], base))
    say("\n变体说明：" + "；".join(f"{k} {v['zh']}" for k, v in BC.VARIANTS.items()))
    say("\n## 二、入选规则（运行前写定）")
    rows = {k: qualifies(res[k], base) for k in BC.VARIANTS}
    for k, f in rows.items():
        say(f"- {k}：{'入选' if not f else '不入选：' + '；'.join(f)}")
    fin = pick(res, base)
    say(f"\n**入选（按规则，最多 5 个）：{('、'.join(fin)) if fin else '没有'}**"
        + ("" if fin else " → 这一轮不登记、不用 Z。"))
    say("\n## 三、出场原因与最好 10% 的占比（现行与入选的）")
    for k in ["现行", *fin]:
        for era in ("E", "J"):
            x = prof[k][era]
            if x.get("n"):
                say(f"- {k} {era}：平均赚 {x['avg_win']:+.2f}% / 平均亏 {x['avg_loss']:+.2f}%、每笔中位 {x['median']:+.2f}%、"
                    f"最好 10% 占净收益之和 {x['top10_share']:.0f}%；出场 " + "、".join(f"{a} {b:.0f}%" for a, b in x["reasons"].items()))
    say("\n## 四、现行交易的持有时间形状（只描述；毛收益，按收盘价，不扣费用）")
    for era in ("E", "J"):
        s = shape[era]
        say(f"- {era} 固定持有 N 个交易日：" + "、".join(
            f"{n} 天 {v['mean']:+.2f}%（胜率 {v['win']:.0f}%，{v['n']} 笔）" for n, v in s["fixed"].items() if v["n"]))
        if "peak_day_med" in s:
            say(f"  持有期最高点在第 {s['peak_day_med']:.0f} 天（中位；{s['peak_after20']:.0f}% 在第 20 天以后）、最高点平均 +{s['peak_gain_mean']:.2f}%、"
                f"到卖出平均回吐 {s['give_back_mean']:.2f} pp；到过 +10% 的占 {s['reach10']:.0f}%，这些的回吐 "
                + (f"{s['give_back_winners']:.2f} pp" if s.get("give_back_winners") is not None else "—"))
    res_out = {"base": base, "core": core, "variants": res, "profiles": prof, "shape": shape, "qualify": rows, "finalists": fin,
               "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {res_out['elapsed_s']} s）。探索，只描述；非投资建议。")
    fp = paths.out_dir() / "bsh_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res_out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
