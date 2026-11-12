"""split_explore.py — 探索（只用生效日在 2017-01〜2021-12 的拆股；2022 年以后不看）：株式分割（拆股）生效日前后的超额收益（研究路线图 R4）。

机制：拆股（生效日在公告时就确定）→ 一手的金额变小 → 个人投资者买得起 → 买盘；生效日是事先知道的，可以当交易日历。
拆股 = J-Quants 调整系数（真实一手比例的宽表 ratio）在某天变大（1 股 → k 股，k ≥ 1.5）；时点 TOPIX 1000 成员。
看：生效日之前 20 天、生效日前一天收盘 → 之后 5 / 20 / 60 天的收益减去同一天全体成员的等权平均（超额）。
原始数据只在 var/cache/jquants/（已 gitignore），这里只有统计。
输出：var/out/split_explore.md / .json（只有统计）
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
from qbreak import paths                                                     # noqa: E402

END = pd.Timestamp("2022-01-01")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def split_events(ratio: np.ndarray, min_k: float = 1.5) -> list[tuple[int, int, float]]:
    """ratio = 真实价格 ÷ 调整后价格（日期 × 票；生效日之前 = k、之后 = 1）；拆股生效日 i：ratio[i−1] / ratio[i] ≥ min_k（1 股 → k 股）。
    返回 (日, 票, k)。例：NTT 2023 年 1 → 25，2023-06-28 为 25、06-29 为 1。"""
    r = np.asarray(ratio, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        k = r[:-1] / r[1:]
    ii, jj = np.where(np.isfinite(k) & (k >= min_k))
    return [(int(i + 1), int(j), float(k[i, j])) for i, j in zip(ii, jj)]


def excess(C: np.ndarray, mem: np.ndarray, i0: int, i1: int, j: int) -> float:
    """收盘 i0 → 收盘 i1 的收益 − 同期成员等权平均（%）。"""
    if i1 >= C.shape[0] or i0 < 0:
        return np.nan
    r = C[i1] / C[i0] - 1
    m = mem[i0] & np.isfinite(r)
    if not np.isfinite(r[j]) or not m.any():
        return np.nan
    return float((r[j] - np.nanmean(r[m])) * 100)


def main() -> int:
    t0 = time.time()
    import candle_data as CD
    D = CD.load()
    P, days, mem, ratio = D["P"], D["days"], D["mem"]["U2"], D["ratio"]
    ev = [(i, j, k) for i, j, k in split_events(ratio) if mem[i, j] and days[i] >= pd.Timestamp("2017-01-01") and days[i] < END]
    rows = []
    for i, j, k in ev:
        rows.append({"date": days[i], "k": k, "pre20": excess(P["C"], mem, i - 21, i - 1, j),
                     "post5": excess(P["C"], mem, i - 1, i + 4, j), "post20": excess(P["C"], mem, i - 1, i + 19, j),
                     "post60": excess(P["C"], mem, i - 1, i + 59, j)})
    T = pd.DataFrame(rows)
    res: dict = {"n": int(len(T))}
    say("# 探索：株式分割（拆股）生效日前后的超额收益（只用生效日在 2017〜2021 的拆股；时点 TOPIX 1000）")
    say(f"拆股 {len(T)} 次（1 股 → k 股，k ≥ 1.5）。超额 = 该股收益 − 同期成员等权平均（%，未扣成本）。")
    say("| 窗口 | 平均 | 中位数 | 为正的比例 | t 值 |")
    say("|---|---|---|---|---|")
    for c, lab in (("pre20", "生效日前 20 天（事后看）"), ("post5", "生效日前一天收盘 → 之后 5 天"), ("post20", "→ 之后 20 天"), ("post60", "→ 之后 60 天")):
        x = T[c].dropna().to_numpy(float)
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan
        res[c] = {"mean": float(x.mean()), "median": float(np.median(x)), "pos": float((x > 0).mean()), "t": float(t), "n": int(len(x))}
        say(f"| {lab} | {x.mean():+.2f}% | {np.median(x):+.2f}% | {(x > 0).mean() * 100:.0f}% | {t:.2f} |")
    say("\n按年（之后 20 天的平均超额 %）：" + "、".join(f"{y} {T[T['date'].dt.year == y]['post20'].mean():+.2f}（{int((T['date'].dt.year == y).sum())}）"
                                            for y in range(2017, 2022)))
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "split_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
