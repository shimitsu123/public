"""dip_explore.py — 探索（只用 2017-01〜2021-12；1990〜2016 与 2022 年以后都不看）：日経225 指数的短期回调买入（研究路线图 R2b：第二条收益来源）。

来由：个股层（突破 = 买强）20 年整体没有贡献；指数的短期均值回归（急跌后反弹）是和突破方向相反、机制不同的收益来源。
指数数据（^N225，yfinance）从 1965 年就有 → 探索只用 2017〜2021，之后可以用 1990〜2005 当完全独立的年代检验。
规则（都要求收盘 > 200 日均线 = 上升趋势里的回调；信号日收盘判定，下一交易日开盘买）：
  D1 5 日跌 ≥ 4%，持有 5 天；D2 RSI(2) < 10，收盘回到 5 日线之上就卖（最长 10 天）；D3 连跌 3 天，持有 5 天；
  D4 离 20 日高点跌 ≥ 7%，持有 10 天
收益 = 开盘买、开盘卖（D2 = 收盘上穿 5 日线的下一开盘卖），扣 ETF 来回成本 0.15%（1321 / 1329 的立花手续费 + 滑点的大约值）。
输出：var/out/dip_explore.md / .json（只有统计）
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
from qbreak import paths                                                     # noqa: E402

COST = 0.15
RULES = {"D1": "5 日跌 ≥ 4%，持有 5 天", "D2": "RSI(2) < 10，回到 5 日线之上就卖（最长 10 天）", "D3": "连跌 3 天，持有 5 天",
         "D4": "离 20 日高点跌 ≥ 7%，持有 10 天"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def signals(ix: pd.DataFrame) -> dict[str, pd.Series]:
    c = ix["Close"].astype(float)
    up = c > c.rolling(200, min_periods=200).mean()
    return {"D1": up & (c / c.shift(5) - 1 <= -0.04),
            "D2": up & (rsi(c, 2) < 10),
            "D3": up & (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3)),
            "D4": up & (c / c.rolling(20, min_periods=20).max() - 1 <= -0.07)}


def trades(ix: pd.DataFrame, sig: pd.Series, rule: str) -> pd.DataFrame:
    """不重叠：持仓期间的新信号忽略。D2：收盘 > 5 日线的下一开盘卖（最长 10 天）。"""
    o, c = ix["Open"].to_numpy(float), ix["Close"].to_numpy(float)
    ma5 = ix["Close"].rolling(5).mean().to_numpy(float)
    s = sig.fillna(False).to_numpy(bool)
    hold = {"D1": 5, "D3": 5, "D4": 10, "D2": 10}[rule]
    rows, i, n = [], 0, len(ix)
    while i < n - 1:
        if not s[i]:
            i += 1
            continue
        e = i + 1
        x = min(e + hold, n - 1)
        if rule == "D2":
            for k in range(e, min(e + hold, n - 1)):
                if c[k] > ma5[k]:
                    x = k + 1
                    break
        if not (np.isfinite(o[e]) and np.isfinite(o[x]) and o[e] > 0):
            i += 1
            continue
        rows.append({"sig": ix.index[i], "entry": ix.index[e], "exit": ix.index[x], "net": (o[x] / o[e] - 1) * 100 - COST})
        i = x
    return pd.DataFrame(rows)


def main() -> int:
    from bullbear_study import SYM, load
    t0 = time.time()
    ix = load(*SYM["JP"])
    ix = ix[(ix["Open"] > 0) & (ix["Close"] > 0)]
    ix = ix[ix.index < pd.Timestamp("2022-01-01")]                             # 2022 年以后不看
    S = signals(ix)
    res: dict = {}
    say("# 探索：日経225 指数的短期回调买入（只用 2017-01〜2021-12）")
    say(f"都要求收盘 > 200 日均线；下一交易日开盘买；扣来回成本 {COST}%。每格 = 笔数 / 胜率 / 每笔平均净收益 / 平均持有交易日。")
    say("| 规则 | 2017〜2021 全部 | " + " | ".join(str(y) for y in range(2017, 2022)) + " | 正的年数 | 同期指数持有 |")
    say("|---|---|" + "---|" * 5 + "---|---|")
    bh = {y: float(ix["Close"][ix.index.year == y].iloc[-1] / ix["Close"][ix.index.year == y - 1].iloc[-1] - 1) * 100 for y in range(2017, 2022)}
    for r in RULES:
        T = trades(ix, S[r], r)
        T = T[(T["sig"] >= pd.Timestamp("2017-01-01")) & (T["sig"] < pd.Timestamp("2022-01-01"))]
        hd = [len(ix.loc[a:b]) - 1 for a, b in zip(T["entry"], T["exit"])]
        f = lambda d: "—" if not len(d) else f"{len(d)} / {(d['net'] > 0).mean() * 100:.0f}% / {d['net'].mean():+.2f}%"   # noqa: E731
        ys = [T[pd.DatetimeIndex(T["sig"]).year == y] for y in range(2017, 2022)]
        pos = sum(1 for d in ys if len(d) and d["net"].mean() > 0)
        res[r] = {"n": int(len(T)), "win": float((T["net"] > 0).mean() * 100) if len(T) else None, "mean": float(T["net"].mean()) if len(T) else None,
                  "years": {str(y): float(d["net"].mean()) if len(d) else None for y, d in zip(range(2017, 2022), ys)}}
        say(f"| {r} {RULES[r]} | {f(T)} / {np.mean(hd) if hd else float('nan'):.1f} 天 | " + " | ".join(f(d) for d in ys) + f" | {pos} / 5 | "
            + " / ".join(f"{bh[y]:+.0f}%" for y in range(2017, 2022)) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "dip_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
