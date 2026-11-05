"""leap2_s4b_explore.py — 「选股本身的质的飞跃」第 S4 轮探索续：「美国对应行业弱」的突破放进组合（只描述、不登记；E / J，Z 不看）。

S4（scripts/leap2_s4_explore.py，单独交易）：日経225 的 W2 突破里，所在业种的美国对应行业（Ken French 49 行业）过去 12 个月
相对强弱在最弱的 1/3 时，两个年代胜率都最高（E 54% / +1.58%、J 52% / +1.99%；其余 36〜43%）。
这里放进同一套 S0C2 组合（日経225，逐笔 = 组合里的个股交易），并做门槛 S5 的随机对照（同比例、按「股票 × 周」抽签，30 次）：
  A1 W2 ∧ 美国对应行业 12 个月强弱百分位 ≤ 1/3（固定门槛，不按年代分位；月数据只用到信号日那个月之前第 2 个月）
  A2 W2 ∧ 百分位 ≤ 1/2
  A3 W2 ∧ 百分位 ≥ 2/3（对照：美国对应行业强）
业种 → 美国行业的对应表 = scripts/leap2_s4_explore.py 的 S33_FF49（S4 看结果之前写定）。
输出：var/out/leap2_s4b_explore.md / .json（只有统计）
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
import leap2_common as L2                                                    # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap2_s1_explore import targets                                         # noqa: E402
from leap2_s4_explore import S33_FF49, us_rank_asof                          # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def us_pct_frames(fr: dict, s33: dict[str, str], P: pd.DataFrame) -> dict[str, np.ndarray]:
    """每只票每天：所在业种的美国对应行业在那个月可用的 12 个月强弱百分位（P = us_rank_asof 的结果；对不上 → NaN）。"""
    out = {}
    for t, df in fr.items():
        ff = S33_FF49.get(s33.get(t, ""))
        if ff is None or ff not in P.columns:
            out[t] = np.full(len(df), np.nan)
            continue
        mon = df.index.to_period("M").to_timestamp()
        out[t] = P[ff].reindex(mon).to_numpy(float)
    return out


def main() -> int:
    from qbreak import factors as F
    from qbreak.trader import load_params
    t0 = time.time()
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    P = us_rank_asof(F.ff_industries(49, "vw"))
    say(f"# 「选股本身的质的飞跃」第 S4 轮探索续：「美国对应行业弱」的突破放进组合（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s4b_explore.py 开头；门槛 scripts/leap2_common.py。各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔净收益 / 胜率。")
    out = {}
    for era in ("E", "J"):
        te = time.time()
        p = load_params(market="JP")
        ctx = LF.context(era)
        fr = LF.frames(ctx, p)
        run_fn = LF.runner(ctx, fr)
        u = us_pct_frames(fr, s33, P)
        base = LF.run(ctx, run_fn, fr, p)
        res = {"现行（W2 · 日経225）": base}
        pq = {}
        for key, keep in (("A1 美国对应行业 ≤ 1/3", {t: np.nan_to_num(u[t], nan=1.0) <= 1 / 3 for t in fr}),
                          ("A2 美国对应行业 ≤ 1/2", {t: np.nan_to_num(u[t], nan=1.0) <= 1 / 2 for t in fr}),
                          ("A3 对照：美国对应行业 ≥ 2/3", {t: np.nan_to_num(u[t], nan=0.0) >= 2 / 3 for t in fr})):
            frac = LF.keep_frac(fr, keep)
            res[key] = LF.run(ctx, run_fn, LF.with_mask(fr, keep), p)
            q = LF.placebo_trades(ctx, run_fn, fr, p, frac, seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            pq[key] = {"frac": round(frac, 3), "win_q95": round(q["win"], 1), "mean_q95": round(q["mean"], 3), "calmar_q95": round(q["calmar"], 3)}
        b = {era: base[era]}
        say(f"\n## {era} — {targets(b, era)}（{time.time() - te:.0f}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 | 保留的信号 | 随机对照 95% 分位：胜率 / 每笔 |")
        say("|---|---|---|---|---|---|")
        for k, r in res.items():
            q = pq.get(k)
            qs = f"{q['win_q95']:.1f}% / {q['mean_q95']:+.2f}%" if q else "—"
            fk = f"{q['frac'] * 100:.0f}%" if q else "100%"
            fails = L2.s_fails({era: r[era]}, b, {era: {"win": q["win_q95"], "mean": q["mean_q95"]}} if q else {})
            ok = not [x for x in fails if x.split(" ")[1] == era]
            say(f"| {k}{'（这个年代到门槛 S1〜S5）' if ok and q else ''} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} | {fk} | {qs} |")
        out[era] = {"res": {k: {w: x for w, x in r.items() if not w.startswith("_")} for k, r in res.items()}, "placebo": pq}
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s4b_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
