"""wvol_wide.py — 事后核对（不参与任何判定，2026-09-27）：W2「只做周线量比 ≥ 1.0 的突破」（wvol_study，登记 9990cba）
在**另一批股票**（扩大池：TOPIX 1000 里日経225 以外的 714 只，var/universe_wide.json，yfinance 调整后行情）的 2006-10〜2016-09 是否也更好。
这批股票和年代都没有参与 W2 的想法与判定（W2 来自 2017〜2026 的时点股票池，判定用 2006〜2016 的日経225）。
逐笔（每只票单独、扣成本）保留组 / 过滤掉的组；S0C2 组合（同一套设定，股票池换成这 714 只）现行 vs W2 vs 随机少做同样比例（种子 0〜19）。
局限：今天的成分 → 幸存者偏差；一手按调整后价格。
输出：var/out/wvol_wide.md / .json（只有统计）
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
import wvol_placebo as WP                                                    # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

SEEDS = 20
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def panel(data: dict[str, pd.DataFrame], start: str, end: str) -> tuple[dict, pd.DatetimeIndex, list[str]]:
    names = sorted(data)
    days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in data.values()])))
    days = days[(days >= pd.Timestamp(start)) & (days <= pd.Timestamp(end))]
    P = {k: np.column_stack([data[t][c].reindex(days).to_numpy(float) for t in names])
         for k, c in (("O", "Open"), ("H", "High"), ("L", "Low"), ("C", "Close"), ("V", "Volume"))}
    return P, days, names


def main() -> int:
    from qbreak import wide_universe as WU
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak.trader import load_params
    t0 = time.time()
    p0 = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
    data = load_universe(WU.tickers(WU.load()), d21)
    P, days, names = panel(data, "2005-09-01", "2016-11-30")
    PRS.PitEngine.DELIST = {}
    start, end = L.E_WIN["E"][0], "2016-09-30"
    fr = W.with_w5v(CS_.frames_from(P, days, names, list(range(len(names))), p0, {}), P, days, names)
    k2 = {t: W.keep_mask(df["w5v"], W.CUT2, False) for t, df in fr.items()}
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])}"   # noqa: E731
    say("# 事后核对：W2 在日経225 以外的 714 只（2006-10〜2016-09，yfinance）（不参与任何判定）")
    say(f"股票 {len(fr)} 只（数据足够的）；S0C2 = var/sim.json 同一套设定，股票池换成这批票；各格 = 年化 / 最大回撤 / Calmar。")
    T = CPH.trades(fr, p0, start)
    T = T[(T["sig_date"] >= pd.Timestamp(start)) & (T["sig_date"] <= pd.Timestamp(end))]
    wv = np.array([fr[t]["w5v"].get(d, np.nan) for t, d in zip(T["ticker"], T["sig_date"])], float)
    keep = W.keep_mask(wv, W.CUT2, False)
    y = pd.DatetimeIndex(T["sig_date"]).year
    better = sum(1 for yy in sorted(set(y)) if T[keep & (y == yy)]["net"].mean() > T[~keep & (y == yy)]["net"].mean())
    out = {"trades": {"all": CS_.tstat(T), "keep": CS_.tstat(T[keep]), "filtered": CS_.tstat(T[~keep]), "years_better": better,
                      "years": len(set(y))}}
    say("\n## 逐笔（每只票单独、扣成本；笔数 / 胜率 / 每笔平均净收益 / 盈亏比）")
    say("| 组 | 2006-10〜2016-09 | 前半 2006-10〜2011-09 | 后半 2011-10〜2016-09 |")
    say("|---|---|---|---|")
    h = [(start, "2011-10-01"), ("2011-10-01", "2016-10-01")]
    for lab, m in (("全部", np.ones(len(T), bool)), ("W2 保留（周线量比 ≥ 1.0）", keep), ("W2 过滤掉", ~keep)):
        say(f"| {lab} | {c4(CS_.tstat(T[m]))} | " + " | ".join(c4(CS_.tstat(T[m], a, b)) for a, b in h) + " |")
    say(f"保留组每笔平均比过滤掉的组好的年数：{better} / {len(set(y))}")
    run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), {}, L.E_WIN, end=end, start=start)
    r0 = run(fr, p0)
    r2 = run({t: df.assign(entry=df["entry"].to_numpy(bool) & k2[t]) for t, df in fr.items()}, p0)
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    n_all = sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool)).sum()) for df in fr.values())
    n_k = sum(int(((df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool) & k2[t]).sum()) for t, df in fr.items())
    frac = n_k / max(n_all, 1)
    rnd = [run(WP.week_lottery(fr, frac, s), p0)["E"]["calmar"] for s in range(SEEDS)]
    c = np.array([L.MS._c(x) for x in rnd], float)
    out.update({"port": {"现行": r0, "W2": r2}, "frac": frac, "random": rnd})
    say("\n## S0C2 组合（股票池 = 这 714 只）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 个股笔数 / 胜率 |")
    say("|---|---|---|---|---|")
    for k, r in (("现行", r0), ("W2", r2)):
        say(f"| {k} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} |")
    say(f"随机少做同样比例（保留 {frac * 100:.1f}% 的信号，{SEEDS} 次）：Calmar 平均 {c.mean():.3f}（5%〜95% {np.quantile(c, 0.05):.3f}〜{np.quantile(c, 0.95):.3f}），"
        f"≥ W2 的次数 {int((c >= L.MS._c(r2['E']['calmar'])).sum())} / {SEEDS}")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "wvol_wide"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
