"""wvol_size.py — 事后核对（不参与任何判定，2026-09-27）：W2（周线量比 ≥ 1.0）的逐笔差和股票大小有没有关系。

来由：wvol_wide（日経225 以外 666 只，2006〜2016）逐笔没有差别，而日経225（两个年代）与时点 TOPIX 500 / 1000（2017〜2026）都有 →
是「中小型股上不管用」还是「那个年代 / 那批票碰巧」？用 2017〜2026 的时点数据分开看：
  大型 = 信号日是时点 TOPIX 500 成员（U1）；中型 = 时点 TOPIX 1000 成员但不在 TOPIX 500（U2 − U1）。
另把 wvol_wide 的 666 只按 2006〜2016 的平均成交额分两半（只描述）。
输出：var/out/wvol_size.md / .json（只有统计）
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
import candle_data as CD                                                     # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import wvol_study as W                                                       # noqa: E402
import wvol_wide as WW                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []
PER = {"2017-01〜2021-12": ("2017-01-01", "2022-01-01"), "2022-01〜2023-09": ("2022-01-01", "2023-10-01"), "2023-10〜": ("2023-10-01", None)}


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def split_stats(T: pd.DataFrame, keep: np.ndarray, per: dict) -> list[tuple[dict, dict]]:
    out = []
    for a, b in per.values():
        m = (T["sig_date"] >= pd.Timestamp(a)).to_numpy() & ((T["sig_date"] < pd.Timestamp(b)).to_numpy() if b else True)
        out.append((CS_.tstat(T[m & keep]), CS_.tstat(T[m & ~keep])))
    return out


def main() -> int:
    from qbreak import wide_universe as WU
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    P, days, names = D["P"], D["days"], D["names"]
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    m1, m2 = D["mem"]["U1"], D["mem"]["U2"]
    cols = [j for j in range(len(names)) if m2[:, j].any()]
    fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {"m1": m1, "m2": m2}), P, days, names)
    fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m2"].to_numpy(bool)) for t, df in fr.items()}
    T = CPH.trades(fr, p0, "2017-01-04")
    big = np.array([bool(fr[t]["m1"].get(d, False)) for t, d in zip(T["ticker"], T["sig_date"])])
    wv = np.array([fr[t]["w5v"].get(d, np.nan) for t, d in zip(T["ticker"], T["sig_date"])], float)
    keep = W.keep_mask(wv, W.CUT2, False)
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}%"   # noqa: E731
    out: dict = {}
    say("# 事后核对：W2 的逐笔差和股票大小（不参与任何判定）")
    say("每格 = W2 保留组 → 过滤掉的组（笔数 / 胜率 / 每笔平均净收益）。")
    say("\n## 2017〜2026 时点股票池（J-Quants）")
    say("| 组 | " + " | ".join(PER) + " | 全部 |")
    say("|---|" + "---|" * (len(PER) + 1))
    for lab, g in (("大型（时点 TOPIX 500）", big), ("中型（TOPIX 1000 − 500）", ~big)):
        Tg, kg = T[g], keep[g]
        cells = split_stats(Tg, kg, PER) + [(CS_.tstat(Tg[kg]), CS_.tstat(Tg[~kg]))]
        out[lab] = cells
        say(f"| {lab} | " + " | ".join(f"{c4(a)} → {c4(b)}" for a, b in cells) + " |")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
    data = load_universe(WU.tickers(WU.load()), d21)
    Pw, dw, nw = WW.panel(data, "2005-09-01", "2016-11-30")
    PRS.PitEngine.DELIST = {}
    fw = W.with_w5v(CS_.frames_from(Pw, dw, nw, list(range(len(nw))), p0, {}), Pw, dw, nw)
    Tw = CPH.trades(fw, p0, "2006-10-02")
    Tw = Tw[(Tw["sig_date"] >= pd.Timestamp("2006-10-02")) & (Tw["sig_date"] <= pd.Timestamp("2016-09-30"))]
    adv = {t: float((df["Close"] * df["Volume"]).loc["2006-10-01":"2016-09-30"].mean()) for t, df in fw.items()}
    med = float(np.nanmedian(list(adv.values())))
    wv2 = np.array([fw[t]["w5v"].get(d, np.nan) for t, d in zip(Tw["ticker"], Tw["sig_date"])], float)
    k2 = W.keep_mask(wv2, W.CUT2, False)
    hi = np.array([adv.get(t, np.nan) >= med for t in Tw["ticker"]])
    say("\n## 日経225 以外 666 只（2006-10〜2016-09，yfinance）按平均成交额分两半")
    say("| 组 | W2 保留 → 过滤掉 |")
    say("|---|---|")
    for lab, g in (("成交额大的一半", hi), ("成交额小的一半", ~hi)):
        a, b = CS_.tstat(Tw[g & k2]), CS_.tstat(Tw[g & ~k2])
        out["wide|" + lab] = (a, b)
        say(f"| {lab} | {c4(a)} → {c4(b)} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "wvol_size"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
