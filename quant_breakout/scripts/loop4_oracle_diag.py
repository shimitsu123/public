"""loop4_oracle_diag.py — 事后诊断（只描述；不是研究循环的做法、不占名额、不参与任何判定）：「完美选股」最多能让 B1 好多少？
（2026-10-03；先提交脚本与读法、再只运行一次）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。第三 / 第四个循环里选股过滤一再「逐笔有效、账户无效」
（FIP、DVC、FBM），原因看起来是：B1 的个股层名额几乎从不满、核心（纳指 × 日元）很强 → 挡掉的突破只是把钱还给核心。这个诊断用「事后才知道的结果」
（不能实际使用）去挡 B1 自己的日本个股交易，量一下任何「挡」类选股算法的天花板。
做法（每个年代 Z / E / J；账户 = B1，只改 em_tick）：
  - O0 不做日本个股：这个年代全部 W2 信号都不开（= 核心 + 判断层，个股层关掉）。
  - O1 完美挡输家：B1 的日本个股交易里事后亏的（ret_pct < 0）在信号日不开；挡掉之后会出现新的交易 → 再看一遍新的亏的、一起挡，最多 3 遍。
  - O2 完美挡跑输核心的：同上，但挡的是「持有期里收益 < 核心（1545 合成价 = 纳指 100 × 日元）同期收益」的交易，最多 3 遍。
  信号日 = 成交日的前一个交易日；核心同期收益 = 1545 合成收盘从买入日到卖出日的涨跌（不含 FJE 对冲与熊市现金，只是近似）。
读法（写在运行之前）：
  - O2 每个年代的 Calmar 差 = 「挡」类选股的近似上限。O2 合计 < +0.3 → 选股过滤（只挡、不加）几乎没有空间，继续找挡的规则意义不大；
    O2 合计 ≥ +0.3 → 空间在，问题是现有的特征分不出来。
  - O0 与 B1 的差 = 个股层现在的贡献（正 = 个股层有用）。
  - 这些都是「事后诊断」（用到未来的结果），只描述，不能当做法、不进前向记录。
运行：python scripts/loop4_oracle_diag.py → var/out/loop4_oracle_diag.md / .json。非投资建议。
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

ITER = 3
OUT = "loop4_oracle_diag"


def signal_days(tr: pd.DataFrame, days) -> list[pd.Timestamp]:
    days = pd.DatetimeIndex(days)
    return [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]


def core_ret(core: pd.Series, a, b) -> float:
    """核心从买入日到卖出日的涨跌（%；收盘对收盘，找不到 → NaN）。"""
    c = core.dropna()
    i, j = c.index.searchsorted(pd.Timestamp(a)), c.index.searchsorted(pd.Timestamp(b))
    if i >= len(c) or j >= len(c):
        return float("nan")
    return float((c.iloc[j] / c.iloc[i] - 1) * 100)


def bad_mask(tr: pd.DataFrame, core: pd.Series, kind: str) -> np.ndarray:
    r = tr["ret_pct"].to_numpy(float)
    if kind == "O1":
        return r < 0
    cr = np.array([core_ret(core, a, b) for a, b in zip(tr["entry_date"], tr["exit_date"])])
    return np.isfinite(cr) & (r < cr)


def oracle(W: dict, e: str, core: pd.Series, kind: str) -> tuple[dict, int]:
    a, b = W["ctx"][e]["windows"][e]
    days = W["ctx"][e]["days"]
    tick: dict = {}
    r = L2.run(W, e)
    for _ in range(ITER):
        tr = X3.jp_stock_trades(X3.last_trades(), a, b)
        if not len(tr):
            break
        m = bad_mask(tr, core, kind)
        new = {(str(t), d): 0.0 for t, d, k in zip(tr["ticker"], signal_days(tr, days), m) if k and (str(t), d) not in tick}
        if not new:
            break
        tick.update(new)
        r = L2.run(W, e, em_tick=dict(tick))
    return r, len(tick)


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    W = L2.load()
    core = W["assets"]["1545.T"]["Close"].astype(float)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win")
    res = {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        A = W["A"][e]
        all_tick = {(str(t), pd.Timestamp(d)): 0.0 for t, d in zip(A["ticker"], pd.to_datetime(A["date"]))}
        r0 = L2.run(W, e, em_tick=all_tick)
        r1, n1 = oracle(W, e, core, "O1")
        r2, n2 = oracle(W, e, core, "O2")
        res[e] = {"B1": {k: rb.get(k) for k in keys}, "O0": {k: r0.get(k) for k in keys},
                  "O1": {**{k: r1.get(k) for k in keys}, "blocked": n1}, "O2": {**{k: r2.get(k) for k in keys}, "blocked": n2}}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    L = ["# 事后诊断：「完美选股」最多能让 B1 好多少（只描述；用到未来的结果，不能当做法；规则见 scripts/loop4_oracle_diag.py 开头）", "",
         "| 年代 | B1 Calmar（年化 / 回撤 / 个股笔数） | O0 不做日本个股 | O1 完美挡输家 | O2 完美挡跑输核心的 |", "|---|---|---|---|---|"]
    f = lambda x: f"{x['calmar']:.3f}（{x['cagr']:+.2f}% / {x['dd']:.2f}% / {x['n']}）"   # noqa: E731
    for e in L2.ERAS:
        x = res[e]
        L.append(f"| {e} | {f(x['B1'])} | {f(x['O0'])}（{x['O0']['calmar'] - x['B1']['calmar']:+.3f}） | "
                 f"{f(x['O1'])}（{x['O1']['calmar'] - x['B1']['calmar']:+.3f}；挡 {x['O1']['blocked']} 笔） | "
                 f"{f(x['O2'])}（{x['O2']['calmar'] - x['B1']['calmar']:+.3f}；挡 {x['O2']['blocked']} 笔） |")
    tot = {k: round(sum(res[e][k]["calmar"] - res[e]["B1"]["calmar"] for e in L2.ERAS), 3) for k in ("O0", "O1", "O2")}
    L += ["", f"三个年代 Calmar 差合计：O0 {tot['O0']:+.3f}、O1 {tot['O1']:+.3f}、O2 {tot['O2']:+.3f}"
          f" → 按事先写的读法：O2 合计 {'< +0.3 → 「挡」类选股几乎没有空间' if tot['O2'] < 0.3 else '≥ +0.3 → 空间在，现有特征分不出来'}。",
          f"用时 {time.time() - t0:.0f} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps({"eras": res, "total": tot}, ensure_ascii=False, indent=1, default=float) + "\n",
                                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
