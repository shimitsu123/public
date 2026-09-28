"""size_oracle.py — 事后上限（只描述，2026-09-28）：假如事先完全知道每笔交易的结果，按结果给仓位（0.64 / 1.0 / 1.36，与
scripts/size_explore.py 同一个范围与引擎），账户最多能好多少。不能做到、不是规则、不参与任何判定。
做法：现行（S0C2 + W2）组合里每笔交易 → 找到它的信号日 → O1：实际净收益最好 1/3 → 1.36、最差 1/3 → 0.64、其余 1.0；
O2：赚的 → 1.36、亏的 → 0.64。其它信号 1.0。仓位变了以后组合路径会变（有的交易会多出来 / 少掉），所以是近似的上限。
输出：var/out/size_oracle.md / .json。
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import size_common as SZ                                                    # noqa: E402
from qbreak import paths                                                    # noqa: E402


def oracle_weights(tr: pd.DataFrame, days: pd.DatetimeIndex, fw: dict, kind: str) -> dict:
    """{(票, 信号日): 权重}：信号日 = 买入日之前最后一个有信号的日子。"""
    out = {}
    net = tr["net"].to_numpy(float)
    lo, hi = np.nanpercentile(net, 100 / 3), np.nanpercentile(net, 200 / 3)
    for r, x in zip(tr.itertuples(), net):
        df = fw.get(r.ticker)
        if df is None:
            continue
        e = df["entry"].to_numpy(bool) & np.asarray(df.index < pd.Timestamp(r.entry_date))
        pos = np.flatnonzero(e)
        if not len(pos):
            continue
        d = df.index[pos[-1]]
        if kind == "O1":
            w = SZ.W_HI if x > hi else (SZ.W_LO if x <= lo else 1.0)
        else:
            w = SZ.W_HI if x > 0 else SZ.W_LO
        out[(r.ticker, pd.Timestamp(d))] = w
    return out


def main() -> int:
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    L = [f"# 仓位分配的事后上限（只描述；{pd.Timestamp.today().date()}）",
         "假如事先完全知道每笔结果，按结果给 0.64 / 1.0 / 1.36 倍仓位（与 size_explore 同一范围与引擎）。做不到，只用来看「仓位分配最多能帮多少」。",
         "", "| 年代 | 现行 Calmar / 年化 | O1 结果最好 1/3 加码、最差 1/3 减码 | O2 赚的加码、亏的减码 |", "|---|---|---|---|"]
    out = {}
    for era in ("E", "J"):
        ctx = LF.context(era)
        fa = LF.frames(ctx, SF.no_w2_params(p))
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        r0, tr0 = SZ.run_weighted(ctx, run_fn, fw, p, None)
        res = {}
        for k in ("O1", "O2"):
            r, _ = SZ.run_weighted(ctx, run_fn, fw, p, oracle_weights(tr0, ctx["days"], fw, k))
            res[k] = {"calmar": r[era]["calmar"], "cagr": r[era]["cagr"], "dd": r[era]["dd"]}
        out[era] = {"base": {"calmar": r0[era]["calmar"], "cagr": r0[era]["cagr"], "dd": r0[era]["dd"]}, **res}
        b = out[era]["base"]
        L.append(f"| {era} | {b['calmar']} / {b['cagr']}% | {res['O1']['calmar']} / {res['O1']['cagr']}%（{res['O1']['calmar'] - b['calmar']:+.3f}） | "
                 f"{res['O2']['calmar']} / {res['O2']['cagr']}%（{res['O2']['calmar'] - b['calmar']:+.3f}） |")
    L += ["", f"（耗时 {round(time.time() - t0)} s）。事后上限，只描述；非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "size_oracle"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
