"""leap_r4_explore.py — 「质的飞跃」第 4 轮探索：短期反转（只描述、不登记；只用 2006-10 以后）。

文献：日本大型股的短期反转（上周 / 上个月跌得最多的之后反弹）比美国强。以前的研究只做过日経225 指数的回调买入（R2b，没通过），
没做过个股之间的反转。这里：每周最后一个交易日（或每月末）收盘，在股票池里按过去 5 / 21 个交易日的涨跌排序，
买跌得最多的 K 只（可选：只在 200 日线之上 = 上升趋势里的回调），等权拿到下一个周末 / 月末，扣来回 0.25%。
股票池：今天的日経225（有幸存者偏差）与 J-Quants 时点 TOPIX 500（2017〜，无偏差）。对照：同一股票池等权、核心（S&P500 × USD/JPY）。
输出：var/out/leap_r4_explore.md / .json（只有统计）
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
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def week_end_rows(days: pd.DatetimeIndex) -> np.ndarray:
    s = pd.Series(np.arange(len(days)), index=days)
    return s.groupby(days.to_period("W-FRI")).last().to_numpy()


def perf_w(m: pd.Series, per_year: float) -> dict:
    m = m.dropna()
    if not len(m):
        return {}
    eq = (1 + m / 100).cumprod()
    yrs = len(m) / per_year
    cagr = (eq.iloc[-1] ** (1 / yrs) - 1) * 100
    dd = float((eq / eq.cummax() - 1).min() * 100)
    return {"cagr": round(float(cagr), 2), "dd": round(dd, 2), "calmar": round(float(cagr / abs(dd)), 3) if dd < 0 else None,
            "hit": round(float((m > 0).mean() * 100), 1)}


def run_block(C: np.ndarray, days: pd.DatetimeIndex, ok: np.ndarray, core: pd.Series, lab: str, out: dict) -> None:
    L = np.log(np.where(C > 0, C, np.nan))
    ma200 = pd.DataFrame(C).rolling(200, min_periods=150).mean().to_numpy()
    up = C > ma200
    for freq, rows, look, per in (("周", week_end_rows(days), 5, 52.0), ("月", R2.month_end_rows(days), 21, 12.0)):
        past = np.full_like(C, np.nan)
        past[look:] = L[look:] - L[:-look]
        scores = {f"REV 过去 {look} 天跌得最多": -past, f"REVUP 同上，只在 200 日线之上": np.where(up, -past, np.nan)}
        me = days[rows[:-1]]
        cm = core.reindex(days[rows], method="ffill").to_numpy()
        corem = pd.Series((cm[1:] / cm[:-1] - 1) * 100, index=me)
        for k in (4, 8):
            R = R2.sleeve_returns(C, rows, scores, k, ok)
            for era, (a, b) in ERAS.items():
                msk = (me >= pd.Timestamp(a)) & (me < pd.Timestamp(b))
                if not msk.any() or pd.Series(R["EW"], index=me)[msk].notna().sum() < 20:
                    continue
                LC.assert_explore_dates(me[msk])
                ew = pd.Series(R["EW"], index=me)[msk]
                say(f"\n## {lab} · 每{freq} · K = {k} · {era}（{int(msk.sum())} 期）")
                say("| 组合 | 年化 | 最大回撤 | Calmar | 上涨期比例 | 比等权好的期 | 比核心好的期 |")
                say("|---|---|---|---|---|---|---|")
                for n in ["EW"] + list(scores):
                    s = pd.Series(R[n], index=me)[msk]
                    p = perf_w(s, per)
                    be = None if n == "EW" else float((s > ew).mean() * 100)
                    bc = float((s > corem[msk]).mean() * 100)
                    out[f"{lab}/{freq}/K{k}/{era}/{n}"] = {**p, "beat_ew": be, "beat_core": bc}
                    say(f"| {'等权' if n == 'EW' else n} | {p.get('cagr')}% | {p.get('dd')}% | {p.get('calmar')} | {p.get('hit')}% | "
                        f"{'—' if be is None else f'{be:.0f}%'} | {bc:.0f}% |")
                pc = perf_w(corem[msk], per)
                say(f"| 核心（不择时） | {pc.get('cagr')}% | {pc.get('dd')}% | {pc.get('calmar')} | {pc.get('hit')}% | — | — |")


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
    say(f"# 「质的飞跃」第 4 轮探索：短期反转（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r4_explore.py 开头。收益都扣来回 0.25%；核心 = S&P500 × USD/JPY（不含择时与股息）。")
    out = {}
    n225 = list(universe("JP", "broad"))
    data = LD.ohlcv(n225)
    nm = [t for t in n225 if t in data and len(data[t])]
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in nm])))
    days = days[days >= pd.Timestamp(LC.Z_WARMUP_START)]
    C = pd.DataFrame({t: data[t]["Close"] for t in nm}).reindex(days).ffill(limit=5).to_numpy(float)
    run_block(C, days, np.isfinite(C), core, "今天的日経225", out)
    D = CD.load()
    CJ = pd.DataFrame(D["P"]["C"]).ffill().to_numpy(float)
    okJ = D["mem"]["U1"] & np.isfinite(D["P"]["C"])
    run_block(CJ, D["days"], okJ, core, "时点 TOPIX 500", out)
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r4_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
