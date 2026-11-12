"""dip_study.py — 日経225 指数的短期回调买入（研究路线图 R2b：第二条收益来源）（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：scripts/dip_explore.py（只用 2017-01〜2021-12；var/out/dip_explore.md）：上升趋势中（收盘 > 200 日线）
  R1 = RSI(2) < 10 买、收盘回到 5 日线之上的下一开盘卖（最长 10 天）：43 笔、胜率 72%、每笔 +0.34%（扣 0.15% 成本）、平均持有 3.3 天；
  R2 = 连跌 3 天买、持有 5 天：44 笔、52%、+0.06%。
  突破是「买强」、这是「牛市里买指数的急跌」→ 方向相反、可能是低相关的第二条收益来源。用户这一轮：「…考虑没有考虑过的方法…」。
指数（^N225，yfinance）从 1965 年就有 → **主判定放在完全没看过的 1990-01〜2005-12**（泡沫破灭后的长期下跌 / 横盘，对「牛市里买急跌」是严格的年代）。

一、规则（与探索相同；信号日收盘判定，下一交易日开盘买，不重叠）
  R1 RSI(2)（Wilder 平滑）< 10 且 收盘 > 200 日均线；卖 = 收盘 > 5 日均线的下一开盘（最长 10 个交易日后开盘）
  R2 连跌 3 天 且 收盘 > 200 日均线；持有 5 个交易日（开盘买 → 5 天后开盘卖）
  净收益 = 开盘到开盘 − 0.15%（ETF 来回成本的大约值）。
二、判定（逐笔，都要满足才通过）
  P 主：1990-01〜2005-12：每笔平均净收益 > 0 且 t 值（平均 ÷ 标准误）≥ 2.0，胜率 ≥ 55%
  E 次：2006-10〜2016-09：每笔平均 > 0
  H 次：2022-01〜2026-09（探索没用过）：每笔平均 > 0
  通过 → 提议下一步做「放进组合」的登记检验（用 1321 / 1329 占一个个股名额）；这次不改模拟盘。
三、另报（只描述）：每个年代的笔数 / 胜率 / 每笔 / 年均笔数；1990〜2005 按年的每笔平均；1965〜1989（泡沫前的上升期）。
四、局限：指数不能直接买（用 ETF 1321 / 1329 近似，2001 年以前没有 ETF）；开盘价是指数的开盘（ETF 的开盘会有小的偏离）；税前。
登记前做过的检查：tests/test_dip_study.py（信号只用当天收盘为止、不重叠、卖出规则）。
输出：var/out/dip_study.md / .json（只有统计）
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
import dip_explore as X                                                      # noqa: E402
from qbreak import paths                                                     # noqa: E402

CANDS = {"R1": ("D2", "RSI(2) < 10，回到 5 日线之上就卖"), "R2": ("D3", "连跌 3 天，持有 5 天")}
ERAS = {"P": ("1990-01-01", "2006-01-01", "1990-01〜2005-12（主）"), "E": ("2006-10-01", "2016-10-01", "2006-10〜2016-09"),
        "H": ("2022-01-01", None, "2022-01〜2026-09"), "O": ("1965-01-01", "1990-01-01", "1965〜1989（只描述）"),
        "T": ("2017-01-01", "2022-01-01", "2017〜2021（探索期）")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def stats(T: pd.DataFrame, a: str, b: str | None) -> dict:
    m = (T["sig"] >= pd.Timestamp(a)) & ((T["sig"] < pd.Timestamp(b)) if b else True)
    d = T.loc[m, "net"].to_numpy(float)
    if not len(d):
        return {"n": 0}
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else np.nan
    yrs = (pd.Timestamp(b) if b else T["sig"].max()) - pd.Timestamp(a)
    return {"n": int(len(d)), "win": float((d > 0).mean() * 100), "mean": float(d.mean()), "t": float(d.mean() / se) if se and np.isfinite(se) and se > 0 else None,
            "per_year": float(len(d) / max(yrs.days / 365.25, 1e-9))}


def fails(s: dict) -> list[str]:
    f = []
    p = s["P"]
    if not p.get("n") or p["mean"] <= 0 or (p.get("t") or 0) < 2.0 or p["win"] < 55.0:
        f.append(f"1990〜2005：{p.get('n', 0)} 笔 胜率 {p.get('win', 0):.1f}% 每笔 {p.get('mean', 0):+.2f}% t {p.get('t') or 0:.2f}（要 > 0、t ≥ 2、胜率 ≥ 55%）")
    for k, lab in (("E", "2006〜2016"), ("H", "2022〜2026")):
        if not s[k].get("n") or s[k]["mean"] <= 0:
            f.append(f"{lab}：每笔 {s[k].get('mean', 0):+.2f}%（要 > 0）")
    return f


def main() -> int:
    from bullbear_study import SYM, load
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/dip_study.py", "scripts/dip_explore.py"],
                                capture_output=True, text=True).stdout.strip())
    ix = load(*SYM["JP"])
    ix = ix[(ix["Open"] > 0) & (ix["Close"] > 0)]
    S = X.signals(ix)
    res, dec = {}, {}
    say("# 日経225 指数的短期回调买入（登记检验，2026-09-27）")
    say(f"规则见 scripts/dip_study.py 开头（先提交后运行）。下一交易日开盘买、不重叠、扣 {X.COST}% 来回成本；每格 = 笔数 / 胜率 / 每笔平均净收益 / t 值 / 每年笔数。")
    say("| 规则 | " + " | ".join(v[2] for v in ERAS.values()) + " | 判定 |")
    say("|---|" + "---|" * len(ERAS) + "---|")
    for c, (rule, lab) in CANDS.items():
        T = X.trades(ix, S[rule], rule)
        s = {k: stats(T, a, b) for k, (a, b, _) in ERAS.items()}
        f = fails(s)
        res[c] = {"eras": s, "by_year_P": {str(y): float(T[pd.DatetimeIndex(T["sig"]).year == y]["net"].mean())
                                           for y in range(1990, 2006) if (pd.DatetimeIndex(T["sig"]).year == y).any()}}
        dec[c] = f
        cell = lambda d: "—" if not d.get("n") else f"{d['n']} / {d['win']:.0f}% / {d['mean']:+.2f}% / {d['t'] if d['t'] is not None else float('nan'):.2f} / {d['per_year']:.1f}"   # noqa: E731
        say(f"| {c} {lab} | " + " | ".join(cell(s[k]) for k in ERAS) + f" | {'✓' if not f else '✗'} |")
    for c, f in dec.items():
        if f:
            say(f"- {c}：" + "；".join(f))
    say("\n## 1990〜2005 每年的每笔平均（%，只描述）")
    ys = [str(y) for y in range(1990, 2006)]
    say("| 规则 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for c in CANDS:
        say(f"| {c} | " + " | ".join(f"{res[c]['by_year_P'][y]:+.2f}" if y in res[c]["by_year_P"] else "—" for y in ys) + " |")
    passed = [c for c, f in dec.items() if not f]
    if passed:
        say(f"\n**结论：{'、'.join(passed)} 通过全部门槛 → 提议下一步登记「放进组合」的检验（用 1321 / 1329 占一个个股名额）；这次不改模拟盘。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 不做「放进组合」的检验。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "results": res, "fails": dec, "passed": passed}
    fp = paths.out_dir() / "dip_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
