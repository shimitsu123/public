"""wvol_us.py — 事后核对（不参与任何判定，2026-09-27）：W2「周线量比 ≥ 1.0 的突破更好」在**美国个股**（完全独立的市场）上是否也成立。
对象：universe("US","broad")（今天的美国大型股 ~109 只，yfinance 21 年，幸存者偏差）、美股参数（load_params(market="US")）的突破信号，
每只票单独的独立交易（扣来回成本），按信号日的周线量比（qbreak/mtf.py，只用已完成的周）分组。
输出：var/out/wvol_us.md / .json（只有统计）
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
import candle_study as CS_                                                   # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import mtf, paths                                                # noqa: E402

LINES: list[str] = []
PER = {"2006〜2016": ("2006-01-01", "2017-01-01"), "2017〜2026": ("2017-01-01", None)}


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.engine import run_backtest
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="US")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
    data = load_universe(universe("US", "broad"), d21)
    bt = BacktestConfig.for_market("US", 21, "rakuten")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    notional = 5000.0
    rt = bt.exec_cfg.fee(notional) * 2 / notional * 100
    rows = []
    for t, df in data.items():
        ind = compute_indicators(df, p, None)
        if not ind["entry"].any():
            continue
        w5 = mtf.daily_frame(df, df.index)["W5v"].reindex(ind.index)
        try:
            r = run_backtest({t: ind}, p, bt, start="2006-01-01")
        except ValueError:
            continue
        tr = r.trades
        if not len(tr):
            continue
        tr = tr[tr["reason"] != "end"].copy()
        if not len(tr):
            continue
        ent = pd.to_datetime(tr["entry_date"])
        tr["sig_date"] = [ind.index[max(0, ind.index.searchsorted(e) - 1)] for e in ent]
        tr["ticker"] = t
        tr["w5v"] = [w5.get(s, np.nan) for s in tr["sig_date"]]
        rows.append(tr)
    T = pd.concat(rows, ignore_index=True)
    T["net"] = T["ret_pct"] - rt
    keep = W.keep_mask(T["w5v"].to_numpy(float), W.CUT2, False)
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {s['pf']:.2f}"   # noqa: E731
    y = pd.DatetimeIndex(T["sig_date"]).year
    out: dict = {}
    say("# 事后核对：W2 在美国个股（不参与任何判定）")
    say(f"美股 {len(data)} 只（今天的大型股，yfinance）、美股参数的突破、每只票单独的独立交易（扣来回成本 {rt:.2f}%）。"
        "每格 = 笔数 / 胜率 / 每笔平均净收益 / 盈亏比。")
    say("| 组 | " + " | ".join(PER) + " | 保留组更好的年数 |")
    say("|---|" + "---|" * len(PER) + "---|")
    for lab, m in (("全部", np.ones(len(T), bool)), ("W2 保留（周线量比 ≥ 1.0）", keep), ("W2 过滤掉", ~keep)):
        cells = []
        for a, b in PER.values():
            mm = m & (T["sig_date"] >= pd.Timestamp(a)).to_numpy() & ((T["sig_date"] < pd.Timestamp(b)).to_numpy() if b else True)
            cells.append(CS_.tstat(T[mm]))
        out[lab] = cells
        better = "—" if lab == "全部" else f"{sum(1 for yy in sorted(set(y)) if T[keep & (y == yy)]['net'].mean() > T[~keep & (y == yy)]['net'].mean())} / {len(set(y))}"
        say(f"| {lab} | " + " | ".join(c4(c) for c in cells) + f" | {better} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "wvol_us"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
