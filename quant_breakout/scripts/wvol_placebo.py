"""wvol_placebo.py — 事后核对（不参与任何判定，2026-09-27）：W2「只做周线量比 ≥ 1.0 的突破」（wvol_study，登记 9990cba）的好处
是不是只因为「少做个股」（2017〜2026 只有 1655 比现行好）。

做法：同一套 S0C2 设定，把现行突破信号按「股票 × 周」抽签保留（保留比例 = W2 在该年代保留的信号比例；同一周同一只票一起留或一起去，
和 W2 的周线结构一样），种子 0〜29 各跑一次 → W2 的 Calmar 在 30 个随机过滤里排第几。
输出：var/out/wvol_placebo.md / .json（只有统计）
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
import pit_retrain_study as PRS                                              # noqa: E402
import wvol_study as W                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

SEEDS = 30
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def week_lottery(fr: dict, frac: float, seed: int) -> dict:
    """每只票每周抽一次签（概率 frac 保留），那一周的信号一起留或一起去。"""
    rng = np.random.default_rng(seed)
    out = {}
    for t in sorted(fr):
        df = fr[t]
        wk = df.index.to_period("W-FRI")
        codes, uniq = pd.factorize(wk)
        keep = rng.random(len(uniq)) < frac
        out[t] = df.assign(entry=df["entry"].to_numpy(bool) & keep[codes])
    return out


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    D = CD.load()
    p0 = load_params(market="JP")
    out: dict = {}
    say("# 事后核对：W2（周线量比 ≥ 1.0）是不是只因为少做个股（随机过滤对照；不参与任何判定）")
    say("同一套 S0C2；随机过滤 = 现行突破信号按「股票 × 周」抽签，保留比例与 W2 相同；种子 0〜29。各格 = Calmar。")
    say("\n| 年代 | 现行 | W2 | W2 保留的信号比例 | 随机过滤 平均（5%〜95%） | 随机过滤里比 W2 好的次数 |")
    say("|---|---|---|---|---|---|")
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols, win, ratio, start, end, key = list(range(len(names))), L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30", "E"
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end, key = L.J_WIN, "2017-01-04", None, "J"
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
        fr = W.with_w5v(CS_.frames_from(P, days, names, cols, p0, {}), P, days, names)
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        lo, hi = pd.Timestamp(start), (pd.Timestamp(end) if end else days[-1])
        n_all = n_keep = 0
        k2 = {}
        for t, df in fr.items():
            m = (df.index >= lo) & (df.index <= hi) & df["entry"].to_numpy(bool)
            k2[t] = W.keep_mask(df["w5v"], W.CUT2, False)
            n_all += int(m.sum())
            n_keep += int((m & k2[t]).sum())
        frac = n_keep / max(n_all, 1)
        base = run(fr, p0)[key]["calmar"]
        w2 = run({t: df.assign(entry=df["entry"].to_numpy(bool) & k2[t]) for t, df in fr.items()}, p0)[key]["calmar"]
        cal = []
        for s in range(SEEDS):
            cal.append(run(week_lottery(fr, frac, s), p0)[key]["calmar"])
        c = np.array([L.MS._c(x) for x in cal], float)
        better = int((c >= L.MS._c(w2)).sum())
        out[era] = {"base": base, "w2": w2, "frac": frac, "random": cal, "better_or_equal": better}
        lab = "2006-10〜2016-09" if era == "E" else "2017-01〜2026-09"
        say(f"| {lab} | {base:.3f} | {w2:.3f} | {frac * 100:.1f}% | {np.mean(c):.3f}（{np.quantile(c, 0.05):.3f}〜{np.quantile(c, 0.95):.3f}） | {better} / {SEEDS} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "wvol_placebo"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
