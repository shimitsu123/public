"""wvol_posthoc.py — 事后核对（不参与任何判定，2026-09-27）：wvol_study（登记 9990cba）通过的 W2「只做周线量比 ≥ 1.0 的突破」
在没有幸存者偏差的时点股票池（J-Quants U1 时点 TOPIX 500、U2 时点 TOPIX 1000，2017-01〜2026-09）上是否也更好。
输出：var/out/wvol_posthoc.md / .json（只有统计）
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
import candle_portfolio as CP                                                # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    P, days, names = D["P"], D["days"], D["names"]
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])}"   # noqa: E731
    out = {}
    say("# 事后核对：W2「只做周线量比 ≥ 1.0 的突破」在时点股票池（不参与任何判定）")
    say("S0C2 = var/sim.json 同一套设定；J-Quants 行情、一手按当时真实股价；突破只在成员的日子；各格 = 年化 / 最大回撤 / Calmar。")
    say("| 股票池 | 方案 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 个股笔数 / 胜率 | 逐笔 保留 / 过滤掉（笔数 / 胜率 / 每笔 / 盈亏比） |")
    say("|---|---|---|---|---|---|---|")
    for u in ("U1", "U2"):
        mem = D["mem"][u]
        cols = [j for j in range(len(names)) if mem[:, j].any()]
        fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {"m": mem}), P, days, names)
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in fr.items()}
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days),
                             {t: pd.Series(D["ratio"][:, names.index(t)], index=days) for t in fr}, L.J_WIN)
        k2 = {t: W.keep_mask(df["w5v"], W.CUT2, False) for t, df in fr.items()}
        r0 = run(fr, p0)
        r2 = run({t: df.assign(entry=df["entry"].to_numpy(bool) & k2[t]) for t, df in fr.items()}, p0)
        T = CPH.trades(fr, p0, "2017-01-04")
        wv = np.array([fr[t]["w5v"].get(d, np.nan) for t, d in zip(T["ticker"], T["sig_date"])], float) if len(T) else np.array([])
        keep = W.keep_mask(wv, W.CUT2, False) if len(T) else np.array([], bool)
        tk, tf = (CS_.tstat(T[keep]), CS_.tstat(T[~keep])) if len(T) else ({}, {})
        out[u] = {"现行": r0, "W2": r2, "trades_keep": tk, "trades_filt": tf}
        lab = "时点 TOPIX 500" if u == "U1" else "时点 TOPIX 1000"
        say(f"| {lab} | 现行 | {cell(r0['J'])} | {cell(r0['V'])} | {cell(r0['H'])} | {r0['trades']} / {fa(r0.get('win'), '{:.1f}%')} | — |")
        say(f"| {lab} | W2 | {cell(r2['J'])} | {cell(r2['V'])} | {cell(r2['H'])} | {r2['trades']} / {fa(r2.get('win'), '{:.1f}%')} | {c4(tk)} / {c4(tf)} |")
    say("\n## 门槛附近（今天的日経225；2006〜2016 yfinance / 2017〜2026 J-Quants；Calmar，只描述）")
    say("| 周线量比门槛 | 2006-10〜2016-09 | 2017-01〜2026-09 |")
    say("|---|---|---|")
    E, ed, en = D["E"], D["edays"], D["enames"]
    PRS.PitEngine.DELIST = {}
    fe = W.with_w5v(CS_.frames_from(E, ed, en, list(range(len(en))), p0, {}), E, ed, en)
    rune = CP.make_runner(pd.DataFrame({t: fe[t]["Close"] for t in fe}).reindex(ed), {}, L.E_WIN, end="2016-09-30", start=L.E_WIN["E"][0])
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    c0 = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
    fj = W.with_w5v(CS_.frames_from(P, days, names, c0, p0, {}), P, days, names)
    runj = CP.make_runner(pd.DataFrame({t: fj[t]["Close"] for t in fj}).reindex(days),
                          {t: pd.Series(D["ratio"][:, names.index(t)], index=days) for t in fj}, L.J_WIN)
    out["sweep"] = {}
    for cut in (0.0, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5):
        PRS.PitEngine.DELIST = {}
        re_ = rune({t: df.assign(entry=df["entry"].to_numpy(bool) & W.keep_mask(df["w5v"], cut, False)) for t, df in fe.items()}, p0)
        PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
        rj_ = runj({t: df.assign(entry=df["entry"].to_numpy(bool) & W.keep_mask(df["w5v"], cut, False)) for t, df in fj.items()}, p0)
        out["sweep"][str(cut)] = {"E": re_["E"], "J": rj_["J"]}
        say(f"| {'不过滤（现行）' if cut == 0 else '≥ ' + str(cut)} | {fa(re_['E']['calmar'], '{:.3f}')}（{re_['trades']} 笔） | {fa(rj_['J']['calmar'], '{:.3f}')}（{rj_['trades']} 笔） |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "wvol_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
