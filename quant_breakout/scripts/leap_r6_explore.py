"""leap_r6_explore.py — 「质的飞跃」第 6 轮探索：高成交量溢价（只描述、不登记；只统计 2006-10 以后）。

研究里唯一两个年代都成立的个股特征是「量」（W2 周线量比、V3 突破日 3 倍量）。文献（Gervais-Kaniel-Mingelgrin 2001；
Kaniel-Ozoguz-Starks 2012：包括日本在内多数国家都有）：成交量异常放大的股票之后跑赢（被更多人注意到）。
这里不等突破：每月末按「最近完成的一周成交量 ÷ 之前 10 周平均」（W2 同一个量比，按周重算）排序，买前 K 只拿一个月；
  VOL 量比最高；VOLUP 量比最高且那一周上涨；VOLDN 量比最高且那一周下跌（对照）；VOLUP200 = VOLUP 且在 200 日线之上。
股票池：今天的日経225（E、J）与 J-Quants 时点 TOPIX 500（J，无偏差）。扣来回 0.25%。
输出：var/out/leap_r6_explore.md / .json（只有统计）
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
import leap_data as LD                                                       # noqa: E402
import leap_r2_explore as R2                                                 # noqa: E402
import leap_r4_explore as R4                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def weekly_ratio(V: np.ndarray, C: np.ndarray, days: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """每个交易日：最近一个「已经结束的周」（到这一天为止最后一个完整周五周）的成交量合计 ÷ 之前 10 周平均，以及那一周的涨跌。
    只用这一天为止的数据：本周还没结束 → 用上一周。"""
    wk = days.to_period("W-FRI")
    Vd = pd.DataFrame(V, index=days)
    Cd = pd.DataFrame(C, index=days)
    wv = Vd.groupby(wk).sum(min_count=1)
    wc = Cd.groupby(wk).last()
    ratio = wv / wv.shift(1).rolling(10, min_periods=8).mean()
    wret = wc / wc.shift(1) - 1
    last_day = pd.Series(days, index=days).groupby(wk).last()
    done = pd.Series(days == last_day.reindex(wk).to_numpy(), index=days)       # 这一天是那一周最后一个交易日 → 那一周已结束
    use = np.where(done.to_numpy(), np.arange(len(wk)), -1)
    k_week = pd.Series(pd.factorize(wk)[0], index=days)
    idx = np.where(done.to_numpy(), k_week.to_numpy(), k_week.to_numpy() - 1)
    R = ratio.to_numpy()[np.clip(idx, 0, None)]
    W = wret.to_numpy()[np.clip(idx, 0, None)]
    R[idx < 0] = np.nan
    W[idx < 0] = np.nan
    del use
    return R, W


def block(C, V, days, ok, core, lab, out):
    Rv, Wr = weekly_ratio(V, C, days)
    ma200 = pd.DataFrame(C).rolling(200, min_periods=150).mean().to_numpy()
    scores = {"VOL 量比最高": Rv, "VOLUP 量比最高 ∧ 那周上涨": np.where(Wr > 0, Rv, np.nan),
              "VOLDN 量比最高 ∧ 那周下跌（对照）": np.where(Wr < 0, Rv, np.nan),
              "VOLUP200 VOLUP ∧ 200 日线之上": np.where((Wr > 0) & (C > ma200), Rv, np.nan)}
    rows = R2.month_end_rows(days)
    me = days[rows[:-1]]
    cm = core.reindex(days[rows], method="ffill").to_numpy()
    corem = pd.Series((cm[1:] / cm[:-1] - 1) * 100, index=me)
    for k in (4, 8):
        R = R2.sleeve_returns(C, rows, scores, k, ok)
        for era, (a, b) in ERAS.items():
            msk = (me >= pd.Timestamp(a)) & (me < pd.Timestamp(b))
            if pd.Series(R["EW"], index=me)[msk].notna().sum() < 20:
                continue
            LC.assert_explore_dates(me[msk])
            ew = pd.Series(R["EW"], index=me)[msk]
            say(f"\n## {lab} · K = {k} · {era}")
            say("| 组合 | 年化 | 最大回撤 | Calmar | 比等权好的月份 / 年份 | 比核心好的月份 |")
            say("|---|---|---|---|---|---|")
            for n in ["EW"] + list(scores):
                s = pd.Series(R[n], index=me)[msk]
                p = R2.perf(s)
                yb = s.groupby(s.index.year).sum() > ew.groupby(ew.index.year).sum()
                out[f"{lab}/K{k}/{era}/{n}"] = {**p, "beat_y": [int(yb.sum()), int(len(yb))]}
                say(f"| {'等权' if n == 'EW' else n} | {p.get('cagr')}% | {p.get('dd')}% | {p.get('calmar')} | "
                    f"{'—' if n == 'EW' else f'{(s > ew).mean() * 100:.0f}% / {int(yb.sum())}/{len(yb)}'} | {(s > corem[msk]).mean() * 100:.0f}% |")
            pc = R2.perf(corem[msk])
            say(f"| 核心（不择时） | {pc.get('cagr')}% | {pc.get('dd')}% | {pc.get('calmar')} | — | — |")


def main() -> int:
    import candle_data as CD
    from bullbear_study import SYM, load
    from qbreak.config import universe
    from unified_study import spx_jpy_on_jp_days
    t0 = time.time()
    fx = load("JPY=X", "2000-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    jp = load(*SYM["JP"])
    core = spx_jpy_on_jp_days(load(*SYM["US"]), fx, jp.index)["Close"]
    say(f"# 「质的飞跃」第 6 轮探索：高成交量溢价（只描述，{pd.Timestamp.today().date()}）")
    out = {}
    n225 = list(universe("JP", "broad"))
    data = LD.ohlcv(n225)
    nm = [t for t in n225 if t in data and len(data[t])]
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in nm])))
    days = days[days >= pd.Timestamp(LC.Z_WARMUP_START)]
    C = pd.DataFrame({t: data[t]["Close"] for t in nm}).reindex(days).ffill(limit=5).to_numpy(float)
    V = pd.DataFrame({t: data[t]["Volume"] for t in nm}).reindex(days).to_numpy(float)
    block(C, V, days, np.isfinite(C), core, "今天的日経225", out)
    D = CD.load()
    CJ = pd.DataFrame(D["P"]["C"]).ffill().to_numpy(float)
    block(CJ, D["P"]["V"], D["days"], D["mem"]["U1"] & np.isfinite(D["P"]["C"]), core, "时点 TOPIX 500", out)
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r6_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
