"""leap_r8_explore.py — 「质的飞跃」第 8 轮探索：按公司业绩（会社予想修正 / 利润增速）每月选股（只描述、不登记；只有 2017〜2026）。

以前（jq_study、ml_study）把会社予想修正 g1、利润增益率 g2 当「突破的过滤条件」→ 不通过；没做过「每月直接按业绩挑股票」。
文献：日本的会社予想上修之后股价继续走强（修正后漂移），是最有名的基本面异象之一。
做法：J-Quants 決算短信（qbreak/jq_data.py 的 fins_events / fins_features，开示日严格早于月末），每月末在时点 TOPIX 500 / 今天的日経225 里：
  REV 最近 90 天里最近一次会社予想修正率最高（上修）；GRO 最近一次累计利润增益率最高；RG 两者的百分位平均；
  RG_NODN = RG 但排除最近 90 天下修过的；前 K 只等权拿一个月，扣来回 0.25%。只看 2017〜2021（挑）与 2022〜2026（核对）两段。
这类数据 2016 年以前没有 → 按「质的飞跃」的判定（要 2001〜2006 年代确认）不能直接通过，只能当前向记录的候选（要用户同意再登记）。
输出：var/out/leap_r8_explore.md / .json（只有统计）
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
import leap_r2_explore as R2                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

SEGS = {"T": ("2017-01-01", "2022-01-01"), "H": ("2022-01-01", "2026-10-01")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    import candle_data as CD
    from bullbear_study import SYM, load
    from qbreak import jq_data as JD
    from unified_study import spx_jpy_on_jp_days
    t0 = time.time()
    D = CD.load()
    days, names = D["days"], D["names"]
    rows = R2.month_end_rows(days)
    me_all = days[rows]
    keep = [j for j in range(len(names)) if D["mem"]["U1"][:, j].any() or D["mem"]["U0"][:, j].any()]
    codes = {names[j].split(".")[0] + "0" for j in keep}
    base = JD.bulk_dir()
    fins = JD.read_bulk(sorted((base / "fins" / "summary").rglob("*.csv.gz")), JD.DATASETS["fins"][1], codes)
    fb = dict(tuple(fins.groupby("Code")))
    G1 = np.full((len(me_all), len(names)), np.nan)
    G2 = np.full((len(me_all), len(names)), np.nan)
    DN = np.zeros((len(me_all), len(names)), bool)
    for j in keep:
        c5 = names[j].split(".")[0] + "0"
        if c5 not in fb:
            continue
        ev = JD.fins_events(fb[c5])
        ff = JD.fins_features(ev, me_all)
        G1[:, j], G2[:, j] = ff["g1"].to_numpy(float), ff["g2"].to_numpy(float)
        DN[:, j] = ff["g1"].to_numpy(float) < 0
    say(f"# 「质的飞跃」第 8 轮探索：按公司业绩每月选股（只描述，{pd.Timestamp.today().date()}；決算数据 {len(fb)} 家）")
    fx = load("JPY=X", "2000-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    jp = load(*SYM["JP"])
    core = spx_jpy_on_jp_days(load(*SYM["US"]), fx, jp.index)["Close"]
    C = pd.DataFrame(D["P"]["C"]).ffill().to_numpy(float)
    out = {}
    full = lambda A: pd.DataFrame(A, index=me_all).reindex(days).to_numpy(float)                            # 只在月末有值   # noqa: E731
    for u, lab in (("U1", "时点 TOPIX 500"), ("U0", "今天的日経225（有幸存者偏差）")):
        ok = D["mem"][u] & np.isfinite(D["P"]["C"])
        pct = lambda A: pd.DataFrame(np.where(ok[rows], A, np.nan)).rank(axis=1, pct=True).to_numpy()          # noqa: E731
        rg = (pct(G1) + pct(G2)) / 2
        scores = {"REV 会社予想上修最多": full(np.where(G1 > 0, G1, np.nan)), "GRO 利润增速最高": full(G2),
                  "RG 上修 + 增速": full(rg), "RG_NODN 同上，排除最近下修": full(np.where(DN, np.nan, rg))}
        me = days[rows[:-1]]
        cm = core.reindex(days[rows], method="ffill").to_numpy()
        corem = pd.Series((cm[1:] / cm[:-1] - 1) * 100, index=me)
        for k in (4, 8, 20):
            R = R2.sleeve_returns(C, rows, scores, k, ok)
            for seg, (a, b) in SEGS.items():
                msk = (me >= pd.Timestamp(a)) & (me < pd.Timestamp(b))
                LC.assert_explore_dates(me[msk])
                ew = pd.Series(R["EW"], index=me)[msk]
                say(f"\n## {lab} · K = {k} · {'2017〜2021（挑）' if seg == 'T' else '2022〜2026（核对）'}")
                say("| 组合 | 年化 | 最大回撤 | Calmar | 比等权好的月份 / 年份 | 比核心好的月份 |")
                say("|---|---|---|---|---|---|")
                for n in ["EW"] + list(scores):
                    s = pd.Series(R[n], index=me)[msk]
                    p = R2.perf(s)
                    yb = s.groupby(s.index.year).sum() > ew.groupby(ew.index.year).sum()
                    out[f"{u}/K{k}/{seg}/{n}"] = {**p, "beat_y": [int(yb.sum()), int(len(yb))]}
                    say(f"| {'等权' if n == 'EW' else n} | {p.get('cagr')}% | {p.get('dd')}% | {p.get('calmar')} | "
                        f"{'—' if n == 'EW' else f'{(s > ew).mean() * 100:.0f}% / {int(yb.sum())}/{len(yb)}'} | {(s > corem[msk]).mean() * 100:.0f}% |")
                pc = R2.perf(corem[msk])
                say(f"| 核心（不择时） | {pc.get('cagr')}% | {pc.get('dd')}% | {pc.get('calmar')} | — | — |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r8_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
