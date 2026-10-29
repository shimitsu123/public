"""decision_table.py — 给用户做决定用的对照表（只描述，不参与任何判定，2026-09-27）：待决的 ㉓ W2（wvol_study 通过的提议）与
㉔ 核心换成纳指（ndx_study N1，按规则只差 1987〜2005 的回撤）单独 / 一起用时，2006〜2016 与 2017〜2026 的组合表现；另列「没有个股」的两种核心作参照。
S0C2 = var/sim.json 同一套设定；纳指 = ^NDX × USD/JPY 合成（不加股息）。
输出：var/out/decision_table.md / .json（只有统计）
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
import layer_study as L                                                      # noqa: E402
import ndx_study as N                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import refuge_study as RF                                                    # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []
ROWS = {"现行": "现行（S0C2：日本个股突破 + 1655）", "W2": "㉓ W2：只做周线量比 ≥ 1.0 的突破", "N1": "㉔ 核心换成纳指",
        "N1+W2": "㉓ + ㉔ 一起", "1655": "参照：没有个股、只有 1655", "NDX": "参照：没有个股、只有纳指"}


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    from bullbear_study import load
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    ndx_df = load("^NDX", "1985-01-01")
    fxy = load("JPY=X", "2000-01-01")
    fxy = fxy[(fxy["Close"] > 60) & (fxy["Close"] < 250)]["Close"]
    res = {}
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols, win, ratio, start, end = list(range(len(names))), L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30"
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: dd for t, dd in last.items() if dd < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end = L.J_WIN, "2017-01-04", None
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
        fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {}), P, days, names)
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        nframe = RF.jpy_frame(ndx_df, fxy, days, 10.0)
        w2 = {t: df.assign(entry=df["entry"].to_numpy(bool) & W.keep_mask(df["w5v"], W.CUT2, False)) for t, df in fr.items()}
        none = {t: df.assign(entry=False) for t, df in fr.items()}
        nq = {"cfg_over": N.CFG["N1"], "extra_core": {N.NQ: nframe}}
        res[era] = {"现行": run(fr, p0), "W2": run(w2, p0), "N1": run(fr, p0, **nq), "N1+W2": run(w2, p0, **nq),
                    "1655": run(none, p0), "NDX": run(none, p0, **nq)}
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("# 给决定用的对照表：㉓ W2、㉔ 纳指核心（只描述，不参与任何判定）")
    say("S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say("| 方案 | 2006-10〜2016-09 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 个股笔数 / 胜率（2017〜2026） |")
    say("|---|---|---|---|---|---|")
    for k, lab in ROWS.items():
        e, j = res["E"][k], res["J"][k]
        say(f"| {lab} | {cell(e['E'])}（{fa(e['E'].get('tot'), '{:+.1f}')}%） | {cell(j['J'])}（{fa(j['J'].get('tot'), '{:+.1f}')}%） | {cell(j['V'])} | {cell(j['H'])} | "
            f"{j['trades']} / {fa(j.get('win'), '{:.1f}%')} |")
    say("\n## 每一年的收益（%）")
    ys = [str(y) for y in range(2006, 2027)]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ROWS:
        vals = {**{y: v for y, v in res["E"][k]["years"].items() if y <= "2016"}, **{y: v for y, v in res["J"][k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "decision_table"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
