"""leap_r13_oracle.py — 「质的飞跃」第 13 轮（诊断，只描述、不登记；只用 E / J，Z 不看）：「开天眼」的上限。

问题：第 12 轮算出个股层平均只占 5〜7% 的资金。那么即使事先完全知道哪些 W2 突破会赚钱（现实里做不到），只做那些，组合 Calmar 能到多少？
  到不了「现行 + 0.10」→ 对 W2 信号的任何过滤 / 挑选都不可能过「质的飞跃」的组合门槛（L1），要换别的结构（更高占用、别的收益来源）。
做法：同一套 S0C2 回测（scripts/leap_confirm.py）；每个 W2 信号用「单独交易」标出事后结果
  （candle_posthoc.trades：一只票一次一仓、现行卖出规则、扣成本；与组合里同一个信号的那一笔是同一个进出场）；
  O1 只做事后赚钱的（净收益 > 0）；O2 只做事后净收益 ≥ +5% 的；O3 只做事后亏钱的（下限）；
  R 随机保留与 O1 同样比例（leap_confirm.placebo_q：按「股票 × 周」抽签，30 个种子的中位数与 95% 分位）。
  没有单独交易的信号（同一只票上一笔还没卖、或在窗口开始前）→ 不做。
输出：var/out/leap_r13_oracle.md / .json（只有统计）
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
import leap_common as LC                                                     # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def oracle_keep(fr: dict, label: dict, rule) -> dict[str, np.ndarray]:
    """{(票, 信号日): 单独交易的净收益 %} → 每只票每天：entry 且 rule(净收益) 才保留（没有标签 → 不保留）。"""
    out = {}
    for t, df in fr.items():
        ent = df["entry"].to_numpy(bool)
        k = np.zeros(len(df), bool)
        for i in np.flatnonzero(ent):
            v = label.get((t, df.index[i]))
            k[i] = v is not None and bool(rule(v))
        out[t] = k
    return out


def main() -> int:
    import candle_posthoc as CPH
    from qbreak.trader import load_params
    t0 = time.time()
    say(f"# 「质的飞跃」第 13 轮（诊断）：事先知道哪些 W2 突破会赚钱，组合最多能好多少（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r13_oracle.py 开头。各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔净收益 / 胜率。「门槛」= 现行 Calmar + 0.10。")
    out = {}
    rules = {"O1 只做事后赚钱的": lambda v: v > 0, "O2 只做事后 ≥ +5% 的": lambda v: v >= 5.0, "O3 只做事后亏钱的（下限）": lambda v: v <= 0}
    for era in ("E", "J"):
        te = time.time()
        ctx = LF.context(era)
        p = load_params(market="JP")
        fr = LF.frames(ctx, p)
        run_fn = LF.runner(ctx, fr)
        a, _ = ctx["windows"][era]
        T = CPH.trades(fr, p, a)
        T["sig_date"] = pd.to_datetime(T["sig_date"])
        T = T[T["sig_date"] >= pd.Timestamp(a)]
        LC.assert_explore_dates(T["sig_date"])
        label = {(t, d): float(v) for t, d, v in zip(T["ticker"], T["sig_date"], T["net"])}
        res = {"现行（W2）": LF.run(ctx, run_fn, fr, p), "只有核心": LF.run(ctx, run_fn, LF.no_entries(fr), p)}
        frac = {}
        for k, f in rules.items():
            keep = oracle_keep(fr, label, f)
            frac[k] = LF.keep_frac(fr, keep)
            res[k] = LF.run(ctx, run_fn, LF.with_mask(fr, keep), p)
        q95, vals = LF.placebo_q(ctx, run_fn, fr, p, frac["O1 只做事后赚钱的"])
        v = np.array([x for x in vals if x is not None], float)
        bar = res["现行（W2）"][era]["calmar"] + LC.CALMAR_UP[era]
        out[era] = {"res": {k: {w: x for w, x in r.items() if not w.startswith("_")} for k, r in res.items()}, "keep_frac": frac,
                    "placebo": {"median": round(float(np.median(v)), 3), "q95": round(q95, 3), "vals": vals}, "bar": round(bar, 3),
                    "standalone": {"n": int(len(T)), "win": round(float((T["net"] > 0).mean() * 100), 1), "mean": round(float(T["net"].mean()), 3)}}
        say(f"\n## {era}（单独交易 {len(T)} 笔：胜率 {out[era]['standalone']['win']:.1f}%、每笔 {out[era]['standalone']['mean']:+.2f}%；{time.time() - te:.0f}s）")
        say(f"| 方案 | 保留的信号 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|---|")
        for k, r in res.items():
            fk = "100%" if k == "现行（W2）" else ("0%" if k == "只有核心" else f"{frac[k] * 100:.0f}%")
            say(f"| {k} | {fk} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
        say(f"- 门槛（现行 + {LC.CALMAR_UP[era]:.2f}）：Calmar {bar:.3f}；随机保留同样比例（{frac['O1 只做事后赚钱的'] * 100:.0f}%）30 次："
            f"中位数 {np.median(v):.3f}、95% 分位 {q95:.3f}")
        o1 = res["O1 只做事后赚钱的"][era]["calmar"]
        say(f"- 「开天眼」O1 {'到了' if o1 >= bar else '到不了'}门槛（{o1:.3f} vs {bar:.3f}）")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r13_oracle"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
