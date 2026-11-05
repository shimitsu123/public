"""leap2_s6_study.py — 「选股本身的质的飞跃」第 S6 轮（登记检验）：放量 ∧ 低 β 的突破（2026-09-27 事先登记：先提交后运行，登记后不改）。

来由（用户：「继续找新方向 各个分析指数互相搭配 调整阈值进行研究」）：
  S6 搜索（scripts/leap2_s6_combo.py：日経225 的全部突破 × 130 条规则两两搭配 ≈ 8,500 个组合，只用 E / J）过筛选 2 个
  （打乱结果的偶然基线平均 0.1 个、最多 2 个）；放进组合（leap2_s6b_portfolio.py）只有 C2「突破日量比高 ∧ 对日経 β 低」两个年代都站得住；
  阈值网格（leap2_s6c_grid.py）：E 要 β 更低才有够多的好交易，J 在 β 0.78〜0.90 最好 → 没有一格在 E、J 都过 S1〜S5。
  机制：放量突破 + 平时不跟大盘走的票 = 个别消息驱动（业绩、订单、再编），比跟着大盘涨的突破更持久（假说）。
  这一轮用 Z（2001-01〜2006-09，从没用来研究选股）确认这一族到底是规律还是 E / J 的巧合；「质的飞跃」按门槛要三个窗口都过 S1〜S5
  （E、J 在探索里已经知道过不了全部 → 这一轮主要看 Z 与「选股改进」）。

候选（日経225、今天的成分；买点 = 现行突破（不加 W2）∧ 下面的条件；卖法、名额、核心、宏观 / 状态层都照现行）：
  K1 突破日量比 ≥ 2.184 ∧ 对日経 β ≤ 0.78（S6 搜索原样）
  K2 突破日量比 ≥ 2.0 ∧ 对日経 β ≤ 0.70（网格里 E、J 都过 S1〜S4 的唯一一格）
  K3 突破日量比 ≥ 2.0 ∧ 对日経 β ≤ 0.78（中间）
  突破日量比 = 信号日成交量 ÷ 之前 20 日平均（leap_r11_explore.vr1）；对日経 β = 信号日所在周之前一周为止 104 周的周收益回归
  （yfinance 复权收盘，leap2_s6b_portfolio.weekly_betas / daily_from_weekly；没有 104 周历史 → 不买）。
判定：scripts/leap2_common.py（s_fails：S1〜S5；improve_fails：「选股改进」）；S5 随机对照 = 全部突破按「股票 × 周」
  随机保留与候选同样的比例、30 次（leap_confirm.placebo_trades）。现行 = W2 · 日経225（同一个 runner）。
局限：Z 的 β 从 2002 年起才有（2000-01 起的行情 + 104 周）→ 2001 年的信号都不买；Z / E 是今天的成分（幸存者偏差，候选与现行同样有）；
  Z 的宏观层没有 Brent；E、J 在探索里用过（这一轮的 E、J 结果只是复现）。
输出：var/out/leap2_s6_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap2_common as L2                                                    # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

CANDS = {"K1": ("突破日量比 ≥ 2.184 ∧ 对日経 β ≤ 0.78", 2.184, 0.78), "K2": ("突破日量比 ≥ 2.0 ∧ 对日経 β ≤ 0.70", 2.0, 0.70),
         "K3": ("突破日量比 ≥ 2.0 ∧ 对日経 β ≤ 0.78", 2.0, 0.78)}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def candidate_keep(fa: dict, vr: dict[str, np.ndarray], beta: dict[str, np.ndarray], v_min: float, b_max: float) -> dict[str, np.ndarray]:
    """每只票每天：突破日量比 ≥ v_min 且 对日経 β ≤ b_max（缺值 → 不满足）。"""
    return {t: (np.nan_to_num(vr[t], nan=-np.inf) >= v_min) & (np.nan_to_num(beta[t], nan=np.inf) <= b_max) for t in fa}


def window(era: str, B: dict) -> dict:
    from leap2_s6b_portfolio import daily_from_weekly
    from leap_r11_explore import vr1
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    ctx = LF.context(era)
    fa = LF.frames(ctx, SF.no_w2_params(p))
    run_fn = LF.runner(ctx, fa)
    fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
    res = {"现行": LF.run(ctx, run_fn, fw, p), "只有核心": LF.run(ctx, run_fn, LF.no_entries(fa), p)}
    vr = {t: vr1(df) for t, df in fa.items()}
    beta = {t: daily_from_weekly(B["b_n225"], t, df.index) for t, df in fa.items()}
    pq, frac = {}, {}
    for k, (_, v, b) in CANDS.items():
        keep = candidate_keep(fa, vr, beta, v, b)
        frac[k] = LF.keep_frac(fa, keep)
        res[k] = LF.run(ctx, run_fn, LF.with_mask(fa, keep), p)
        q = LF.placebo_trades(ctx, run_fn, fa, p, frac[k], seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
        pq[k] = {"win": q["win"], "mean": q["mean"], "calmar": q["calmar"]}
    return {"res": res, "pq": pq, "frac": frac, "secs": round(time.time() - t0)}


def main() -> int:
    from leap2_s6b_portfolio import weekly_betas
    from qbreak.config import universe
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/leap2_s6_study.py"], capture_output=True, text=True).stdout.strip())
    B = weekly_betas(list(universe("JP", "broad")))
    W = {era: window(era, B) for era in ("Z", "E", "J")}
    say(f"# 「选股本身的质的飞跃」第 S6 轮（登记检验）：放量 ∧ 低 β 的突破（{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s6_study.py 开头（先提交后运行）；判定 scripts/leap2_common.py。"
        "各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔净收益 / 胜率。")
    lab = {"Z": "Z 2001-01〜2006-09（确认用，从没用来研究选股）", "E": "E 2006-10〜2016-09（探索里用过）", "J": "J 2017-01〜2026-09（J-Quants，探索里用过）"}
    for era in ("Z", "E", "J"):
        w = W[era]
        say(f"\n## {lab[era]}（{w['secs']}s）")
        say("| 方案 | 全期 | 前半 | 后半 | 保留的信号 | 随机对照 95% 分位：胜率 / 每笔 |")
        say("|---|---|---|---|---|---|")
        for k, r in w["res"].items():
            name = f"{k} {CANDS[k][0]}" if k in CANDS else k
            q = w["pq"].get(k)
            qs = f"{q['win']:.1f}% / {q['mean']:+.2f}%" if q else "—"
            fk = f"{w['frac'][k] * 100:.0f}%" if k in w["frac"] else "—"
            say(f"| {name} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} | {fk} | {qs} |")
    say("\n## 判定")
    out = {"code": code, "dirty": dirty, "windows": {}}
    base = {era: W[era]["res"]["现行"][era] for era in ("Z", "E", "J")}
    for k in CANDS:
        c = {era: W[era]["res"][k][era] for era in ("Z", "E", "J")}
        pq = {era: {"win": W[era]["pq"][k]["win"], "mean": W[era]["pq"][k]["mean"]} for era in ("Z", "E", "J")}
        f, fi = L2.s_fails(c, base, pq), L2.improve_fails(c, base)
        say(f"- {k} {CANDS[k][0]}：选股本身的质的飞跃 {'✓' if not f else '✗'}；选股改进 {'✓' if not fi else '✗'}")
        for x in f:
            say(f"  - {x}")
        if fi:
            say("  - 选股改进：" + "；".join(fi))
        out[k] = {"leap_fails": f, "improve_fails": fi}
    for era in ("Z", "E", "J"):
        out["windows"][era] = {k: {w: v for w, v in r.items() if not w.startswith("_")} for k, r in W[era]["res"].items()}
        out["windows"][era]["_placebo"] = W[era]["pq"]
        out["windows"][era]["_frac"] = W[era]["frac"]
    say(f"\n代码版本 {code}{'（有未提交的改动！）' if dirty else '（与提交的版本相同）'}；用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s6_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
