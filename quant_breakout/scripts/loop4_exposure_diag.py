"""loop4_exposure_diag.py — 只描述的诊断（不是研究循环的做法、不占名额、不参与任何判定）：B1 的日本个股名额实际用了多少
（2026-10-03；先提交脚本与读法、再只运行一次）。

为什么：第四个循环里选股做法的账户差都很小或为负；事后诊断（scripts/loop4_oracle_diag.py）显示即使完美选股，每个年代也只多约 +0.2。想直接量一下
「B1 平时手里有几只日本个股」—— 如果平均不到 1 只（4 个名额 × 25%），选股再准对账户的影响也有限，更大的杠杆在名额 / 仓位结构（另一个题目，要用户同意）。
做法：每个年代跑一次 B1（loop2_common.run），取窗口内买入的日本个股交易（不含核心 ETF；期末未平仓的算到窗口最后一天），在窗口的每个交易日数持有的只数
  （买入日 ≤ d < 卖出日）；另用日経225 收盘与 200 日均线（至少 150 天）分牛（线上）/ 熊（线下），数「牛市里一只日本个股都没拿」的天数比例。
读法（写在运行之前）：
  - 平均持有只数 < 1（= 日本个股平均占权益 < 25%）→ 选股改进对账户的影响天然有限，名额 / 仓位结构是更大的杠杆（另开题目要用户同意）；
  - 牛市里 0 只的天数比例高 → 限制在「信号太少」而不是「挑得不准」。
  - 只描述，不改任何判定、不改循环规则。
运行：python scripts/loop4_exposure_diag.py → var/out/loop4_exposure_diag.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop3_r03_yenexit as X3                                               # noqa: E402

OUT = "loop4_exposure_diag"
SLOTS = 4


def held_counts(tr: pd.DataFrame, days) -> pd.Series:
    """每个交易日持有的日本个股只数（买入日 ≤ d < 卖出日；卖出日缺 → 持有到最后一天）。"""
    days = pd.DatetimeIndex(days)
    cnt = np.zeros(len(days), int)
    for a, b in zip(pd.to_datetime(tr["entry_date"]), pd.to_datetime(tr["exit_date"], errors="coerce")):
        i = int(days.searchsorted(a))
        j = len(days) if pd.isna(b) else int(days.searchsorted(b))
        cnt[i:max(i, j)] += 1
    return pd.Series(cnt, index=days)


def bull_days(close: pd.Series, days) -> np.ndarray:
    """日経225 收盘 ≥ 200 日均线（至少 150 天；算不出 → 不算牛）。"""
    c = close.astype(float).dropna().sort_index()
    ma = c.rolling(200, min_periods=150).mean()
    up = (c >= ma) & ma.notna()
    return up.reindex(pd.DatetimeIndex(days), method="ffill").fillna(False).to_numpy(bool)


def summarize(cnt: pd.Series, bull: np.ndarray) -> dict:
    v = cnt.to_numpy()
    share = {str(k): float((np.minimum(v, SLOTS) == k).mean() * 100) for k in range(SLOTS + 1)}
    return {"days": int(len(v)), "avg_held": float(v.mean()), "avg_expo_pct": float(v.mean() / SLOTS * 100), "share_pct": share,
            "bull_days_pct": float(bull.mean() * 100), "bull_zero_pct": float(((v == 0) & bull).sum() / max(1, bull.sum()) * 100),
            "full_days_pct": float((v >= SLOTS).mean() * 100)}


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    W = L2.load()
    n225 = W["inp"]["n225"]["Close"]
    res = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        L2.run(W, e)
        tr = X3.jp_stock_trades(X3.last_trades(), a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        days = days[(days >= pd.Timestamp(a)) & ((days < pd.Timestamp(b)) if b else True)]
        res[e] = {**summarize(held_counts(tr, days), bull_days(n225, days)), "trades": int(len(tr))}
    L = ["# 只描述的诊断：B1 的日本个股名额实际用了多少（规则见 scripts/loop4_exposure_diag.py 开头）", "",
         "| 年代 | 交易日 | 个股笔数 | 平均持有只数（占权益） | 0 / 1 / 2 / 3 / 4 只的天数 % | 4 个名额全满 % | 日経在 200 日线上的天数 % | 其中 0 只 % |",
         "|---|---|---|---|---|---|---|---|"]
    for e in L2.ERAS:
        x = res[e]
        sh = " / ".join(f"{x['share_pct'][str(k)]:.0f}" for k in range(SLOTS + 1))
        L.append(f"| {e} | {x['days']} | {x['trades']} | {x['avg_held']:.2f} 只（{x['avg_expo_pct']:.0f}%） | {sh} | {x['full_days_pct']:.1f} | "
                 f"{x['bull_days_pct']:.0f} | {x['bull_zero_pct']:.0f} |")
    avg = np.mean([res[e]["avg_held"] for e in L2.ERAS])
    L += ["", f"三个年代平均持有 {avg:.2f} 只 → 按事先写的读法："
          + ("< 1 只 → 选股改进对账户的影响天然有限，名额 / 仓位结构是更大的杠杆" if avg < 1 else "≥ 1 只 → 个股层占的比重不小"),
          f"用时 {time.time() - t0:.0f} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
