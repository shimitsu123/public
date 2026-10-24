"""leap_r13b_required.py — 「质的飞跃」第 13 轮（诊断续，只描述、不登记；只用 E / J，Z 不看）：选股要准到什么程度才够得着门槛。

第 13 轮 A（scripts/leap_r13_oracle.py）：只在 W2 信号里「开天眼」（只做事后赚钱的），E 也到不了门槛。这里放宽两件事：
  ① 信号更多：全部突破（不加 W2）、扩大的股票池（E = 日経225 + 扩大池 yfinance；J = 时点 TOPIX 500，J-Quants）；
  ② 准确度分档：从这些信号里按目标胜率抽「事后赚钱」与「事后亏钱」的信号，总数 = 现行 W2（日経225）的单独交易笔数
     （胜率 45% ≈ 现行、55%、65%、80%、100%；赚钱的不够时全用、亏钱的按胜率少配 → 笔数变少），每档 5 个种子取中位数；
     另报「全部赚钱的都做」（不限笔数）。
事后结果 = 单独交易（candle_posthoc.trades：一只票一次一仓、现行卖出规则、扣成本）；组合 = 同一套 S0C2（scripts/leap_confirm.py）。
回答：同样的交易笔数下，选股胜率要到多少，组合 Calmar 才到「现行 + 0.10」；信号更多（更高的资金占用）能不能到。
输出：var/out/leap_r13b_required.md / .json（只有统计）
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
from leap_r13_oracle import oracle_keep                                      # noqa: E402
from qbreak import paths                                                     # noqa: E402

LEVELS = (0.45, 0.55, 0.65, 0.80, 1.00)
SEEDS = 5
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def mix_keep(fr: dict, label: dict, n_total: int, win: float, seed: int) -> dict[str, np.ndarray]:
    """从有标签的信号里抽 round(n_total × win) 个事后赚钱的 + 按同一胜率配的事后亏钱的（不放回）→ 保留掩码。
    赚钱的不够 → 赚钱的全用、亏钱的按胜率少配（总数少于 n_total，胜率不变）。"""
    rng = np.random.default_rng(seed)
    keys = sorted(label)
    W = [k for k in keys if label[k] > 0]
    L = [k for k in keys if label[k] <= 0]
    nw = min(int(round(n_total * win)), len(W))
    nl = min(int(round(nw * (1 - win) / win)) if win < 1 else 0, len(L))
    pick = set()
    if nw:
        pick |= {W[i] for i in rng.choice(len(W), nw, replace=False)}
    if nl:
        pick |= {L[i] for i in rng.choice(len(L), nl, replace=False)}
    return oracle_keep(fr, {k: 1.0 for k in pick}, lambda v: True)


def signal_set(era: str, wide: bool, w2: bool) -> dict:
    """一个信号集合：ctx、指标表（成员以外的日子没有信号）、runner、单独交易的事后标签。"""
    import candle_posthoc as CPH
    from qbreak import score_forward as SF
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    from qbreak.trader import load_params
    n225 = list(universe("JP", "broad"))
    if era == "E":
        ctx = LF.context("E", n225 if not wide else n225 + [t for t in WU.tickers(WU.load()) if t not in set(n225)])
    else:
        ctx = LF.context("J", jmem="U1" if wide else "U0")
    p = load_params(market="JP")
    pf = p if w2 else SF.no_w2_params(p)
    fr = LF.frames(ctx, pf)
    fr = LF.with_mask(fr, LF.member_mask(ctx, fr))
    run_fn = LF.runner(ctx, fr)
    a, _ = ctx["windows"][era]
    T = CPH.trades(fr, pf, a)
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    T = T[T["sig_date"] >= pd.Timestamp(a)]
    LC.assert_explore_dates(T["sig_date"])
    label = {(t, d): float(v) for t, d, v in zip(T["ticker"], T["sig_date"], T["net"])}
    return {"ctx": ctx, "p": p, "fr": fr, "run_fn": run_fn, "label": label, "n": len(T),
            "win": float((T["net"] > 0).mean() * 100) if len(T) else float("nan")}


def main() -> int:
    t0 = time.time()
    say(f"# 「质的飞跃」第 13 轮（诊断续）：选股要准到什么程度才够得着门槛（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r13b_required.py 开头。格子 = 组合 Calmar（5 个种子的中位数；括号 = 最低〜最高）· 保留的信号数"
        "（最多 = 现行 W2 · 日経225 的单独交易笔数；赚钱的不够时更少）。")
    out = {}
    for era in ("E", "J"):
        te = time.time()
        base = None
        out[era] = {}
        rows = []
        for wide, w2, lab in ((False, True, "W2 · 日経225（现行）"), (False, False, "全部突破 · 日経225"),
                              (True, True, "W2 · 扩大池"), (True, False, "全部突破 · 扩大池")):
            S = signal_set(era, wide, w2)
            ctx, p, fr, run_fn, label = S["ctx"], S["p"], S["fr"], S["run_fn"], S["label"]
            if base is None:
                cur = LF.run(ctx, run_fn, fr, p)
                base = {"n": S["n"], "calmar": cur[era]["calmar"], "bar": cur[era]["calmar"] + LC.CALMAR_UP[era]}
            cells = {}
            for w in LEVELS:
                vals, kept = [], 0
                for s in range(SEEDS):
                    k = mix_keep(fr, label, base["n"], w, s)
                    kept = int(sum(int(x.sum()) for x in k.values()))
                    vals.append(LF.run(ctx, run_fn, LF.with_mask(fr, k), p)[era]["calmar"])
                v = np.array([x for x in vals if x is not None], float)
                cells[w] = {"median": round(float(np.median(v)), 3), "min": round(float(v.min()), 3), "max": round(float(v.max()), 3), "kept": kept}
            allw = LF.run(ctx, run_fn, LF.with_mask(fr, oracle_keep(fr, label, lambda v: v > 0)), p)
            n_win = sum(1 for v in label.values() if v > 0)
            out[era][lab] = {"n_signals": S["n"], "win_pct": round(S["win"], 1), "levels": cells, "all_winners": {
                "calmar": allw[era]["calmar"], "cagr": allw[era]["cagr"], "dd": allw[era]["dd"], "n_winners": n_win,
                "halves": [allw[era + "1"]["calmar"], allw[era + "2"]["calmar"]]}}
            rows.append((lab, S, cells, allw, n_win))
            print(f"  {era} {lab}：{time.time() - te:.0f}s", flush=True)
        out[era]["_base"] = base
        say(f"\n## {era}（现行 Calmar {base['calmar']:.3f} → 门槛 {base['bar']:.3f}；固定笔数 = {base['n']} 笔单独交易；{time.time() - te:.0f}s）")
        say("| 信号集合 | 单独交易笔数 / 胜率 | " + " | ".join(f"胜率 {w * 100:.0f}%" for w in LEVELS) + " | 全部赚钱的都做（不限笔数）：Calmar · 年化 / 回撤 · 半段 |")
        say("|---|---|" + "---|" * len(LEVELS) + "---|")
        for lab, S, cells, allw, n_win in rows:
            cs = " | ".join(("**" if c["median"] >= base["bar"] else "") + f"{c['median']:.3f}" + ("**" if c["median"] >= base["bar"] else "")
                            + f"（{c['min']:.3f}〜{c['max']:.3f}）· {c['kept']}" for c in cells.values())
            a = allw[era]
            say(f"| {lab} | {S['n']} / {S['win']:.1f}% | {cs} | {a['calmar']:.3f} · {a['cagr']:.2f}% / {a['dd']:.2f}% · "
                f"{allw[era + '1']['calmar']:.3f} / {allw[era + '2']['calmar']:.3f}（{n_win} 笔） |")
    say("\n粗体 = 中位数到了门槛。")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r13b_required"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
