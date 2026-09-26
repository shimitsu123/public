"""ndx_posthoc.py — 事后核对（不参与任何判定，2026-09-27）：ndx_study（登记 ed1f43c）按规则只差回撤一条的 N1「核心换成纳指（牛熊按 S&P500）」，
1987〜2026 全期只有核心时的收益与最深的几次回撤（日元计 / 美元计），给用户做取舍用。
输出：var/out/ndx_posthoc.md / .json（只有统计）
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
import halloween_study as HW                                                 # noqa: E402
import ndx_study as N                                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def drawdowns(eq: pd.Series, k: int = 3) -> list[dict]:
    """不重叠的最深 k 次回撤：高点日、低点日、深度 %、回到高点的日子（没回到 = None）。"""
    e = eq.dropna()
    out, used = [], np.zeros(len(e), bool)
    v = e.to_numpy(float)
    peak = np.maximum.accumulate(v)
    dd = v / peak - 1
    for _ in range(k):
        ddm = np.where(used, 0.0, dd)
        t = int(np.argmin(ddm))
        if ddm[t] >= 0:
            break
        p = int(np.where(v[:t + 1] == peak[t])[0][-1])
        rec = np.where(v[t:] >= peak[t])[0]
        r = t + int(rec[0]) if len(rec) else len(v) - 1
        used[p:r + 1] = True
        out.append({"peak": str(e.index[p].date()), "trough": str(e.index[t].date()), "depth": round(float(dd[t]) * 100, 1),
                    "recovered": str(e.index[r].date()) if len(rec) else None})
    return out


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak import factors
    from qbreak.bullbear import BEAR, Detector, load_config
    t0 = time.time()
    spx = load(*SYM["US"])["Close"]
    ndx = load("^NDX", "1985-01-01")["Close"]
    d = load_config()["detector"]
    bear_s = pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(spx)) == BEAR, index=spx.index)
    fx = factors.fred("DEXJPUS", max_age_h=1e9)
    idx = ndx.index
    fxs = fx.reindex(idx.union(fx.index)).ffill().reindex(idx)
    su = spx.reindex(idx.union(spx.index)).ffill().reindex(idx)
    out: dict = {}
    say("# 事后核对：核心拿纳指（N1）1987〜2026 全期只有核心（不参与任何判定）")
    say("前一天收盘的美股牛熊（S&P500 判定）决定当天持仓；熊 → 现金；每次调整扣 0.1%；指数不含股息。各格 = 年化 / 最大回撤 / Calmar。")
    for cur, lab in (("JPY", "日元计"), ("USD", "美元计")):
        f = fxs if cur == "JPY" else pd.Series(1.0, index=idx)
        S, Nq = (su * f).dropna(), (ndx * f).dropna()
        c = S.index.intersection(Nq.index)
        S, Nq = S.reindex(c), Nq.reindex(c)
        eqs = {"现行 S&P500": N.core_mix({"S": S}, {"S": 1.0}, {"S": bear_s}),
               "N1 纳指": N.core_mix({"N": Nq}, {"N": 1.0}, {"N": bear_s}),
               "N3 各半": N.core_mix({"S": S, "N": Nq}, {"S": 0.5, "N": 0.5}, {"S": bear_s, "N": bear_s})}
        say(f"\n## {lab}")
        say("| 方案 | 1987〜2026 | 1987〜2005 | 2006〜2026 | 最深的 3 次回撤（高点 → 低点：深度） |")
        say("|---|---|---|---|---|")
        out[cur] = {}
        for k, e in eqs.items():
            e = e[e.index >= pd.Timestamp("1987-01-01")]
            w = {w: HW.seg(e, a, b) for w, (a, b) in {"all": ("1987-01-01", "2027-01-01"), "old": ("1987-01-01", "2006-01-01"),
                                                       "new": ("2006-01-01", "2027-01-01")}.items()}
            dds = drawdowns(e)
            out[cur][k] = {"seg": w, "dd": dds}
            cell = lambda s: f"{s['cagr']:.2f}% / {s['dd']:.2f}% / {s['calmar']:.3f}"   # noqa: E731
            say(f"| {k} | {cell(w['all'])} | {cell(w['old'])} | {cell(w['new'])} | "
                + "；".join(f"{x['peak']} → {x['trough']}：{x['depth']:+.1f}%" for x in dds) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "ndx_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
