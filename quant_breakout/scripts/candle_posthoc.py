"""candle_posthoc.py — 事后诊断（不参与任何判定，2026-09-27）：scripts/candle_study.py（登记 1e9bb57）跑完之后——
① 2006〜2016 的逐笔一栏是空的：登记脚本用 pit_retrain_study.indep_trades，它的交易窗口从 2017-01-04 开始 → 2006〜2016 一笔都没有。
   E 门槛这次没有被用到（5 个候选都在 V 就没过，后面的门槛不看），这里把那一栏按原来的意思补上（只描述）。
② 押し目在探索期 +1.52% / 笔，验证期、留出期变成 −0.18% / −0.36% → 每年、以及「量」的单调关系在样本外还在不在。
输出：var/out/candle_posthoc.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candle_data as CD                                                     # noqa: E402
import candle_study as S                                                     # noqa: E402
from qbreak import candles as K                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def trades(ind: dict, p, start: str) -> pd.DataFrame:
    """pit_retrain_study.indep_trades 同一套（每只票单独、扣 ¥25 万一笔的来回手续费），只是交易窗口从 start 开始。"""
    from qbreak.config import BacktestConfig
    from qbreak.engine import run_backtest
    import pit_retrain_study as PRS
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rt = bt.exec_cfg.fee(PRS.NOTIONAL) * 2 / PRS.NOTIONAL * 100
    rows = []
    for t, df in ind.items():
        if not df["entry"].any():
            continue
        try:
            r = run_backtest({t: df}, p, bt, start=start)
        except ValueError:
            continue
        tr = r.trades
        if not len(tr):
            continue
        tr = tr[tr["reason"] != "end"].copy()
        if not len(tr):
            continue
        tr["ticker"] = t
        ent = pd.to_datetime(tr["entry_date"])
        tr["sig_date"] = [df.index[max(0, df.index.searchsorted(e) - 1)] for e in ent]
        rows.append(tr)
    if not rows:
        return pd.DataFrame(columns=["ticker", "sig_date", "net", "hold_days", "ret_pct", "exit_px", "entry_date"])
    T = pd.concat(rows, ignore_index=True)
    T["net"] = T["ret_pct"] - rt
    return T


def main() -> int:
    from qbreak.config import ExecConfig
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    p10 = replace(p0, max_hold_days=S.HOLD_PB)
    slip = ExecConfig.for_market("JP", "tachibana").slippage_pct / 100
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {s['pf']:.2f}"   # noqa: E731
    out: dict = {}
    say("# 事后诊断：K 线图形研究（缩量押し目）（不参与任何判定）")
    # ① 2006〜2016
    E, ed, en = D["E"], D["edays"], D["enames"]
    epb = K.pullback(E) & CD.period_mask(ed, "E0")[:, None]
    with np.errstate(invalid="ignore"):
        eab5 = np.asarray(E["C"] > K.rolling_mean(E["C"], 5), bool)
    fe = S.frames_from(E, ed, en, list(range(len(en))), p0, {"pb": epb, "ab5": eab5})
    TE = {"open": trades({t: df.assign(entry=df["pb"].to_numpy(bool), dead_cross=False) for t, df in fe.items()}, p10, S.E0[0]),
          "sma5": trades({t: df.assign(entry=df["pb"].to_numpy(bool), dead_cross=df["ab5"].to_numpy(bool)) for t, df in fe.items()}, p10, S.E0[0])}
    TE["limit"] = S.limit_adjust(TE["open"], E, ed, en, S.LIMIT_K, slip)
    say("\n## ① 2006-10〜2016-09（yfinance 今天的日経225 213 只）押し目的逐笔（格式 = 笔数 / 胜率 / 每笔平均净收益 / 盈亏比）")
    say("| 买法 / 卖法 | 全部 | 其中 2013 年 | 2013 年以外 |")
    say("|---|---|---|---|")
    for k, lab in (("open", "开盘买、10 日"), ("limit", "指値 收盘 − 0.3 ATR、10 日（近似）"), ("sma5", "开盘买、回到 5 日线就卖")):
        T = TE[k]
        a = S.tstat(T, *S.E0)
        y13 = S.tstat(T, "2013-01-01", "2014-01-01")
        rest = S.tstat(T[(T["sig_date"] < pd.Timestamp("2013-01-01")) | (T["sig_date"] >= pd.Timestamp("2014-01-01"))], *S.E0) if len(T) else {"n": 0}
        out[f"E0|{k}"] = {"all": a, "2013": y13, "rest": rest}
        say(f"| {lab} | {c4(a)} | {c4(y13)} | {c4(rest)} |")
    # ② 每年 与 量的单调关系（J-Quants 时点 TOPIX 1000）
    days, P, names = D["days"], D["P"], D["names"]
    mem2 = D["mem"]["U2"]
    c2 = [j for j in range(len(names)) if mem2[:, j].any()]
    say("\n## ② 时点 TOPIX 1000：押し目（开盘买、10 日）每年的逐笔")
    pbm = K.pullback(P) & mem2
    fr = S.frames_from(P, days, names, c2, p0, {"pb": pbm})
    TJ = trades({t: df.assign(entry=df["pb"].to_numpy(bool), dead_cross=False) for t, df in fr.items()}, p10, "2017-01-04")
    say("| 年 | 笔数 / 胜率 / 每笔平均 / 盈亏比 |")
    say("|---|---|")
    for y in range(2017, 2027):
        s = S.tstat(TJ, f"{y}-01-01", f"{y + 1}-01-01")
        out[f"year|{y}"] = s
        say(f"| {y} | {c4(s)} |")
    say("\n## ③ 「量越缩越好」在样本外还成立吗（跌 ≥ 10%、150 日线、没破 20 日低，只改量的条件；开盘买、10 日）")
    say("| 最近 5 天均量 ÷ 之前 20 天 | 探索期 2017〜2021 | 验证期 2022-01〜2023-09 | 留出期 2023-10〜 |")
    say("|---|---|---|---|")
    for v in (0.75, 0.85, 0.95, 1.05, 9.0):
        pm = K.pullback(P, v5max=v) & mem2
        frv = S.frames_from(P, days, names, c2, p0, {"pb": pm})
        T = trades({t: df.assign(entry=df["pb"].to_numpy(bool), dead_cross=False) for t, df in frv.items()}, p10, "2017-01-04")
        cells = [S.tstat(T, "2017-01-01", "2022-01-01"), S.tstat(T, *S.VAL), S.tstat(T, S.HOLD[0], None)]
        out[f"vol|{v}"] = cells
        say(f"| {'≤ ' + str(v) if v < 9 else '不限'} | " + " | ".join(c4(s) for s in cells) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "candle_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
