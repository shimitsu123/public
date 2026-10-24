"""gate_forward_calib.py — HWN / X2G / JRM 前向检验（scripts/w2_forward_all.py 第十节，2026-10-05 登记）的检出力估计。

只用第十个循环已经看过的历史池子（W：扩大池 2006〜2016、Jx：TOPIX 1000 非日経225 2017〜、Zx：扩大池 2001〜2006；B3 会买的信号、
X6 假想单笔）估计「不挡 − 挡」胜率差的区间宽度（与前向检验同一个函数 qbreak/gate_forward.evaluate：按信号月聚类的自助法），
再外推到前向的主样本（全市场主对象 W2 保留，每年约 450 笔成熟配对）：
  - 按笔数外推（乐观）：标准误 ∝ 1 / √笔数；
  - 按月数外推（保守）：标准误 ∝ 1 / √月数（按日子挡的闸门新证据按月累积）。
要多少年：99% 区间下限 > 0 的检出力 80% → 真实差 ≥ (2.576 + 0.842) × 标准误。只算区间宽度，不是检验（历史差在第十个循环看过）。
运行：python scripts/gate_forward_calib.py → var/out/gate_forward_calib.md / .json。非投资建议。
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
from qbreak import gate_forward as GF                                        # noqa: E402

FWD_PER_YEAR = 450                     # 全市场主对象 W2 保留的成熟配对，每年约（第八节的估计）
Z_SUM = 2.576 + 0.842                  # 99% 下限 > 0、检出力 80%
EFFECTS = (4.0, 6.0, 8.0, 12.0)        # 胜率差（不挡 − 挡，pp）


def years_needed(se: float, n_ref: float, per_year: float, effect: float) -> float:
    """标准误 se 来自 n_ref 个单位；前向每年 per_year 个单位 → 让 Z_SUM × 标准误 ≤ effect 要的年数。"""
    if not np.isfinite(se) or se <= 0 or n_ref <= 0:
        return float("nan")
    return float(n_ref * (Z_SUM * se / effect) ** 2 / per_year)


def flags_for(X: pd.DataFrame, jrm: pd.Series) -> pd.DataFrame:
    out = X.copy()
    out["g_hwn"] = GF.hwn_flag(out["date"])
    out["g_x2g"] = GF.x2g_flag(out["x2"]) if "x2" in out.columns else np.nan
    out["g_jrm"] = GF.jrm_flag(out["date"], jrm)
    return out


def main() -> int:
    import loop10_common as C10
    import loop9_r01_market as R1
    import loop9_r03_relative as R3
    from qbreak import paths
    t0 = time.time()
    W = C10.load()
    jrm = GF.jrm_days(R1.n225(W), R3.core_close(W))
    res, lines = {}, ["# HWN / X2G / JRM 前向检验的检出力估计（只算区间宽度；历史池子在第十个循环看过）", ""]
    lines.append(f"外推到前向主样本：每年约 {FWD_PER_YEAR} 笔（全市场主对象 W2 保留的成熟配对）、12 个月；真实差 ≥ {Z_SUM:.2f} × 标准误 才有 80% 机会让 99% 下限 > 0。")
    lines.append("")
    lines.append("| 池子 | 闸门 | 笔数 / 月数 | 挡掉的占比 | 胜率差标准误 pp | " + " | ".join(f"差 +{e:g} pp 要几年（按笔 〜 按月）" for e in EFFECTS) + " |")
    lines.append("|---|---|---|---|---|" + "---|" * len(EFFECTS))
    for s, fold, _ in C10.OTHER:
        X = flags_for(C10.kept_pool(W, s, fold), jrm)
        res[s] = {}
        for k in GF.IDS:
            ev = GF.evaluate(X, f"g_{k.lower()}", net_col="net", date_col="date")
            se = (ev["dwin_hi95"] - ev["dwin_lo95"]) / 3.92 if "dwin_lo95" in ev else float("nan")
            n_b = ev["block"]["n"] if ev.get("block") else 0
            yrs = {e: (years_needed(se, ev["n"], FWD_PER_YEAR, e), years_needed(se, ev.get("months", 0), 12, e)) for e in EFFECTS}
            res[s][k] = {"n": ev["n"], "months": ev.get("months"), "blocked": n_b, "se_dwin": round(se, 3) if np.isfinite(se) else None,
                         "years": {str(e): [round(a, 1), round(b, 1)] for e, (a, b) in yrs.items()}}
            frac = n_b / ev["n"] * 100 if ev["n"] else float("nan")
            lines.append(f"| {s} | {k} | {ev['n']} / {ev.get('months', 0)} | {frac:.0f}% | {se:.2f} | "
                         + " | ".join(f"{a:.1f} 〜 {b:.1f}" for a, b in yrs.values()) + " |")
    lines += ["", "读法：按日子挡的 HWN / JRM 新证据按月累积（「按月」那一栏更接近实际）；X2G 按业种挡、同一个月里两组都有（「按笔」更接近）。",
              f"用时 {time.time() - t0:.0f}s。非投资建议。"]
    text = "\n".join(lines) + "\n"
    (paths.out_dir() / "gate_forward_calib.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / "gate_forward_calib.json").write_text(json.dumps({"per_year": FWD_PER_YEAR, "z": Z_SUM, "pools": res},
                                                                        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
