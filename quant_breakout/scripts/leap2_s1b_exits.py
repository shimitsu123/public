"""leap2_s1b_exits.py — 「选股本身的质的飞跃」第 S1 轮探索续：卖法（只描述、不登记；只用 E / J，Z 不看；门槛 scripts/leap2_common.py）。

S1 探索（scripts/leap2_s1_explore.py）：只改「买哪些 / 怎么买」，胜率最多 +4 pp（E）、J 反而更差。胜率很大程度由卖法决定
（现行 94% 的离场是日线 MACD 死叉：很多笔先涨了几个 % 又跌回去、按死叉亏着卖）。这里只改出场参数（买点、股票池、名额不变）：
  X1 锁利：涨到 +5% 以后，从最高点回落 5% 就卖（trailing_stop_pct 5、trailing_arm_pct 5；代替现行一直开着的 12% 跟踪止损）
  X2 锁利：涨到 +8% 以后回落 4% 就卖
  X3 止盈 +10%（现行 +25%）
  X4 止盈 +6%
  X5 时间止损：持有 5 天还没到 +1% 就卖
  X6 X1 + X5
股票池：U0（今天的日経225，现行）与 UW（E = 今天的日経225 + T500x；J = 時点 TOPIX 500）。
输出：var/out/leap2_s1b_exits.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap2_common as L2                                                    # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap2_s1_explore import targets                                         # noqa: E402
from leap_r1b_portfolio import cell                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []
VARIANTS = {"X1 涨 5% 后回落 5% 卖": dict(trailing_stop_pct=5.0, trailing_arm_pct=5.0),
            "X2 涨 8% 后回落 4% 卖": dict(trailing_stop_pct=4.0, trailing_arm_pct=8.0),
            "X3 止盈 +10%": dict(take_profit_pct=10.0),
            "X4 止盈 +6%": dict(take_profit_pct=6.0),
            "X5 5 天不到 +1% 就卖": dict(time_stop_days=5, time_stop_min_ret_pct=1.0),
            "X6 X1 + X5": dict(trailing_stop_pct=5.0, trailing_arm_pct=5.0, time_stop_days=5, time_stop_min_ret_pct=1.0)}


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def setting(era: str, uni: str) -> dict:
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    if uni == "U0":
        ctx = LF.context(era)
    else:
        ctx = LF.context("E", L2.uw_names()) if era == "E" else LF.context("J", jmem=L2.J_UW)
    fr = LF.frames(ctx, p)
    fr = LF.with_mask(fr, LF.member_mask(ctx, fr))
    run_fn = LF.runner(ctx, fr)
    res = {"现行卖法": LF.run(ctx, run_fn, fr, p)}
    for k, kw in VARIANTS.items():
        res[k] = LF.run(ctx, run_fn, fr, replace(p, **kw))
    return {"res": res, "secs": round(time.time() - t0), "n": len(fr)}


def main() -> int:
    t0 = time.time()
    say(f"# 「选股本身的质的飞跃」第 S1 轮探索续：卖法（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s1b_exits.py 开头；门槛 scripts/leap2_common.py（对「现行卖法 · 日経225」）。"
        "各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔净收益 / 胜率。")
    out = {}
    for era in ("E", "J"):
        base = None
        for uni in ("U0", "UW"):
            s = setting(era, uni)
            if base is None:
                base = {era: s["res"]["现行卖法"][era]}
                say(f"\n## {era} — {targets(base, era)}")
                say(f"| 股票池 · 卖法 | {era} 全期 | {era} 前半 | {era} 后半 |")
                say("|---|---|---|---|")
            out[f"{era}/{uni}"] = {k: {w: x for w, x in r.items() if not w.startswith("_")} for k, r in s["res"].items()}
            for k, r in s["res"].items():
                ok = not [x for x in L2.s_fails({era: r[era]}, base, {era: {"win": -1e9, "mean": -1e9}}) if x.split(" ")[1] == era]
                lab = "日経225" if uni == "U0" else "扩大池"
                say(f"| {lab} · {k}{'（到门槛 S1〜S4）' if ok else ''} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
            print(f"  {era} {uni}: {s['secs']}s", flush=True)
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s1b_exits"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
