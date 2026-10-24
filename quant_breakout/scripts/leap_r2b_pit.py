"""leap_r2b_pit.py — 第 2 轮探索的幸存者偏差核对（只描述、不登记；只用 2017〜2026）。

leap_r2_explore 的股票池是「今天的日経225」→ 动量类组合会因为「今天的成分 = 过去的大赢家」而被高估。
这里用 J-Quants 的时点股票池（U1 = 时点 TOPIX 500、U2 = 时点 TOPIX 1000，含之后退市的；candle_data）重做每月选股组合：
每月末在当时的成员里按分数选前 K 只，等权拿到下个月末（中途退市 → 按最后一个收盘算），扣来回 0.25%。
对照：同一股票池等权；今天的日経225（U0，有偏差）同样做一遍看偏差有多大。
输出：var/out/leap_r2b_pit.md / .json（只有统计）
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
import leap_r1_explore as R1                                                 # noqa: E402
import leap_r2_explore as R2                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    import candle_data as CD
    t0 = time.time()
    D = CD.load()
    days, names, P = D["days"], D["names"], D["P"]
    C = pd.DataFrame(P["C"]).ffill().to_numpy(float)                          # 退市后沿用最后收盘（拿到月末 = 按最后价卖）
    LR = R1.long_returns(np.where(np.isfinite(P["C"]), P["C"], np.nan))
    L = np.log(np.where(P["C"] > 0, P["C"], np.nan))
    vol60 = pd.DataFrame(np.vstack([np.full((1, L.shape[1]), np.nan), np.diff(L, axis=0)])).rolling(60, min_periods=45).std().to_numpy()
    rows = R2.month_end_rows(days)
    me = days[rows[:-1]]
    msk = me >= pd.Timestamp("2017-01-01")
    LC.assert_explore_dates(me[msk])
    out = {}
    say(f"# 第 2 轮探索的幸存者偏差核对（J-Quants 时点股票池，只描述，{pd.Timestamp.today().date()}）")
    for u, lab in (("U1", "时点 TOPIX 500"), ("U2", "时点 TOPIX 1000"), ("U0", "今天的日経225（有幸存者偏差）")):
        ok = D["mem"][u] & np.isfinite(P["C"])
        scores = {"MOM 12-1 个月最强": LR["r12"], "LVOL 60 日波动最低": -vol60, "LTR 3 年跌得最多": -LR["r3y"]}
        for k in (4, 8, 20):
            R = R2.sleeve_returns(C, rows, scores, k, ok)
            ew = pd.Series(R["EW"], index=me)[msk]
            say(f"\n## {lab}，K = {k}（2017-01〜2026-09，{int(msk.sum())} 个月）")
            say("| 组合 | 年化 | 波动 | 最大回撤 | Calmar | 比等权好的月份 | 比等权好的年份 |")
            say("|---|---|---|---|---|---|---|")
            for n in ["EW"] + list(scores):
                s = pd.Series(R[n], index=me)[msk]
                p = R2.perf(s)
                yb = s.groupby(s.index.year).sum() > ew.groupby(ew.index.year).sum()
                beat = None if n == "EW" else float((s > ew).mean() * 100)
                out[f"{u}/K{k}/{n}"] = {**p, "beat_m": beat, "beat_y": [int(yb.sum()), int(len(yb))]}
                say(f"| {'等权' if n == 'EW' else n} | {p.get('cagr')}% | {p.get('vol')}% | {p.get('dd')}% | {p.get('calmar')} | "
                    f"{'—' if beat is None else f'{beat:.0f}%'} | {'—' if n == 'EW' else f'{int(yb.sum())}/{len(yb)}'} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r2b_pit"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
