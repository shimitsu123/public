"""timeline_stats.py — 买卖时间线的「预计卖出」统计参考（只描述；qbreak/timeline.hold_estimate 读）。

现行规则（日経225 股票池、突破 + W2、离场 X6 = 吊灯止损代替死叉；var/sim.json exits）在研究框架（scripts/leap_confirm）的
E 2006-10〜2016-09 与 J 2017-01〜 两个窗口里的全部个股交易 → 持有天数（引擎的 hold_days：买入当天收盘算第 1 天，
触发卖出的那天收盘为止）的分布，以及「已经持有 h 天的交易，剩下还持有几天」的 25 / 50 / 75 分位（h = 0〜59）。
规则或股票池改了就重跑一次：python scripts/timeline_stats.py → var/timeline_stats.json。非投资建议。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def remaining_table(hold: np.ndarray, max_h: int = 60) -> dict:
    """已经持有 h 天（还没卖）的交易 → 剩下的持有天数分位。hold = 每笔的总持有天数。"""
    out = {}
    for h in range(max_h):
        r = hold[hold > h] - h
        if len(r):
            q = np.percentile(r, [25, 50, 75])
            out[str(h)] = {"n": int(len(r)), "p25": round(float(q[0]), 1), "p50": round(float(q[1]), 1), "p75": round(float(q[2]), 1)}
    return out


def main() -> int:
    import jq_study as JS
    import leap_confirm as LF
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    cfg = read_json(Path(__file__).resolve().parents[1] / "var" / "sim.json", {}) or {}
    mode = EXR.mode_of(cfg, "JP")
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, mode)
    rows = []
    for tag in ("E", "J"):
        ctx = LF.context(tag)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        LF.run(ctx, run_fn, fw, px)
        tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
        a, b = ctx["windows"][tag]
        tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")]
        ed = pd.to_datetime(tr["entry_date"])
        tr = tr[((ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)).to_numpy()]
        rows.append(tr.assign(window=tag))
    T = pd.concat(rows, ignore_index=True)
    hold = T["hold_days"].astype(int).to_numpy()
    q = np.percentile(hold, [10, 25, 50, 75, 90])
    by = {str(k): {"n": int(len(g)), "p50": float(np.median(g["hold_days"]))} for k, g in T.groupby("reason")}
    out = {"generated": dt.date.today().isoformat(), "exit_mode": mode, "windows": "E 2006-10〜2016-09 + J 2017-01〜",
           "n": int(len(T)), "hold": {k: round(float(v), 1) for k, v in zip(("p10", "p25", "p50", "p75", "p90"), q)},
           "by_reason": by, "remaining": remaining_table(hold),
           "note": "现行规则（突破 + W2、离场按 var/sim.json exits）的历史个股交易；只作「预计卖出」的统计参考，不是预测"}
    fp = Path(__file__).resolve().parents[1] / "var" / "timeline_stats.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("n", "hold", "by_reason")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
