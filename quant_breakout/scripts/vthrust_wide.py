"""vthrust_wide.py — 事后核对（不参与任何判定，2026-09-27）：vthrust_study（登记 09d859a）里通过对现行门槛的 V1 / V3、以及 W2，
在**另一批股票**（日経225 以外的扩大池 714 只，2006-10〜2016-09，yfinance）上逐笔与组合是否也更好。
来由：W2 在这批票上逐笔没有差别（wvol_wide）；V3「突破日量比 ≥ 3」在日経225 两个年代逐笔都明显更好 → 看它换一批票还成不成立，帮用户在 W2 / V3 之间选。
输出：var/out/vthrust_wide.md / .json（只有统计）
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
import candle_portfolio as CP                                                # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import vthrust_study as V                                                    # noqa: E402
import wvol_placebo as WP                                                    # noqa: E402
import wvol_study as W                                                       # noqa: E402
import wvol_wide as WW                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

SEEDS = 20
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    from qbreak import wide_universe as WU
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak.trader import load_params
    t0 = time.time()
    p0 = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
    P, days, names = WW.panel(load_universe(WU.tickers(WU.load()), d21), "2005-09-01", "2016-11-30")
    PRS.PitEngine.DELIST = {}
    start, end = L.E_WIN["E"][0], "2016-09-30"
    fr = V.with_vol(W.with_w5v(CS_.frames_from(P, days, names, list(range(len(names))), p0, {}), P, days, names), P, days, names)
    M = {t: V.masks(df) for t, df in fr.items()}
    keys = ("W2", "V1", "V3")
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])}"   # noqa: E731
    T = CPH.trades(fr, p0, start)
    T = T[(T["sig_date"] >= pd.Timestamp(start)) & (T["sig_date"] <= pd.Timestamp(end))]
    km = {k: np.array([bool(M[t][k][fr[t].index.get_loc(d)]) for t, d in zip(T["ticker"], T["sig_date"])]) for k in keys}
    y = pd.DatetimeIndex(T["sig_date"]).year
    out: dict = {"trades": {}}
    say("# 事后核对：V1 / V3 / W2 在日経225 以外的扩大池（2006-10〜2016-09，yfinance）（不参与任何判定）")
    say(f"股票 {len(fr)} 只；V3 = 突破日量比 ≥ 3、V1 = W2 ∧ V3、W2 = 周线量比 ≥ 1.0（定义同 vthrust_study / wvol_study）。")
    say("\n## 逐笔（每只票单独、扣成本；笔数 / 胜率 / 每笔平均净收益 / 盈亏比）")
    say("| 规则 | 保留 | 过滤掉 | 保留组更好的年数 |")
    say("|---|---|---|---|")
    for k in keys:
        better = sum(1 for yy in sorted(set(y)) if T[km[k] & (y == yy)]["net"].mean() > T[~km[k] & (y == yy)]["net"].mean())
        a, b = CS_.tstat(T[km[k]]), CS_.tstat(T[~km[k]])
        out["trades"][k] = {"keep": a, "filtered": b, "years_better": better}
        say(f"| {k} | {c4(a)} | {c4(b)} | {better} / {len(set(y))} |")
    run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), {}, L.E_WIN, end=end, start=start)
    r0 = run(fr, p0)
    out["port"] = {"现行": r0}
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    n_all = sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool)).sum()) for df in fr.values())
    say("\n## S0C2 组合（股票池 = 这批票）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 个股笔数 / 胜率 | 随机少做同样比例 平均（5%〜95%）/ ≥ 它的次数 |")
    say("|---|---|---|---|---|---|")
    say(f"| 现行 | {cell(r0['E'])} | {cell(r0['E1'])} | {cell(r0['E2'])} | {r0['trades']} / {fa(r0.get('win'), '{:.1f}%')} | — |")
    for k in keys:
        r = run({t: df.assign(entry=df["entry"].to_numpy(bool) & M[t][k]) for t, df in fr.items()}, p0)
        frac = sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool) & M[t][k]).sum()) for t, df in fr.items()) / max(n_all, 1)
        c = np.array([L.MS._c(run(WP.week_lottery(fr, frac, s), p0)["E"]["calmar"]) for s in range(SEEDS)], float)
        ge = int((c >= L.MS._c(r["E"]["calmar"])).sum())
        out["port"][k] = {**r, "frac": frac, "random": c.tolist()}
        say(f"| {k} | {cell(r['E'])} | {cell(r['E1'])} | {cell(r['E2'])} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} | "
            f"{c.mean():.3f}（{np.quantile(c, 0.05):.3f}〜{np.quantile(c, 0.95):.3f}）/ {ge} / {SEEDS}（保留 {frac * 100:.1f}%） |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "vthrust_wide"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
