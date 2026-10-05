"""turn_shape_posthoc.py — 「起涨点 / 起跌点 × 日 / 周 / 月线图形」（turn_shape_study.py，登记 d915a9e）的事后诊断（只描述；看了结果之后才写的，
不改任何判定、不能当做法；脚本与读法先提交、只运行一次）。

为什么做：登记运行里两个模型认起涨点 / 起跌点的 AUC 很高（确认期 0.894 / 0.883），但分数最高的一组之后 20 日超额 ≈ 0（−0.04 / −0.12 pp）。
  猜测：起涨点的定义里「t 的收盘是 [t − 10, t + 10] 里最低」有一半（[t − 10, t] 里最低）当天就知道 —— 模型认出的是「今天是近 10 日最低」，
  而不是「这个低点之后会涨起来」。
做法：同一个样本表、同一个模型（turn_shape_study 的函数原样调用）；另算 lo10 = 收盘是 [t − 10, t] 里最低（当天已知）、hi10 = 最高。
  报：① 全部样本 vs lo10（hi10）样本里起涨点（起跌点）的比例；② 只在 lo10（hi10）样本里的 AUC；③ 只在 lo10（hi10）样本里每天按分数分十组，
  最高 / 最低一组的 20 日超额、先涨 M 的比例 U、先跌 M 的比例 D。都是确认期（2022〜）。
读法（事先写）：lo10 里起涨点的比例远高于全部、而 lo10 里的 AUC 掉到 0.6 左右且十组超额没有差 → 「图形认得出新低 / 新高，认不出之后会不会转」。非投资建议。
用法：python scripts/turn_shape_posthoc.py（写 var/out/turn_shape_posthoc.md / .json）
"""
from __future__ import annotations

import json
import logging
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402
import turn_shape_study as S                                                  # noqa: E402

BACK = 10
OUT_MD, OUT_JSON = "turn_shape_posthoc.md", "turn_shape_posthoc.json"


def back_extreme(C: np.ndarray, n: int = BACK) -> tuple[np.ndarray, np.ndarray]:
    """收盘是 [t − n, t] 里最低 / 最高（当天收盘时已知）。"""
    lo = S.rmin(C, n + 1)
    hi = S.rmax(C, n + 1)
    with np.errstate(invalid="ignore"):
        return np.isfinite(C) & (C <= lo), np.isfinite(C) & (C >= hi)


def block(D: pd.DataFrame, sc: np.ndarray, lab: str) -> dict:
    dec = S.deciles_by_day(sc, D["date"].to_numpy())
    out = {"n": int(len(D)), "rate_pct": round(float(D[lab].mean()) * 100, 2), "auc": S.auc(sc, D[lab].to_numpy(float))}
    for name, d in (("top", S.N_DEC - 1), ("bottom", 0)):
        x = D[dec == d]
        out[name] = {"n": int(len(x)), "R20x": round(float(np.nanmean(x["R20x"])) * 100, 3), "U": round(float(x["U"].mean()) * 100, 2),
                     "D": round(float(x["D"].mean()) * 100, 2), "lab": round(float(x[lab].mean()) * 100, 2)}
    return out


def main() -> int:
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    t0 = time.time()
    import allstock_data as AD
    A = AD.load()
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    T, _ = S.build_table(A, days, names, with_patterns=False, with_paths=False, say=lambda s_: print(s_, flush=True))
    lo, hi = back_extreme(A["C"].astype(float))
    T["lo10"] = lo[T["k"].to_numpy(), T["j"].to_numpy()]
    T["hi10"] = hi[T["k"].to_numpy(), T["j"].to_numpy()]
    w = S.windows(T)
    comp = T[S.FEATS].notna().all(axis=1).to_numpy()
    xi, ci = w["X"] & comp, w["C"] & comp
    Xr = T.loc[xi, S.FEATS].to_numpy(float)
    Xs, st = S.winsor_std(Xr, Xr)
    Xc = S.apply_std(T.loc[ci, S.FEATS].to_numpy(float), st)
    Dc = T[ci].reset_index(drop=True)
    res = {"elapsed_s": None, "models": {}}
    for mk, (lab, s) in S.MODELS.items():
        cond = "lo10" if lab == "RS" else "hi10"
        wf = S.fit_logit(Xs, T.loc[xi, lab].to_numpy(float))
        sc = S.predict(wf, Xc)
        m = Dc[cond].to_numpy(bool)
        res["models"][mk] = {"label": lab, "cond": cond, "all": block(Dc, sc, lab), "within": block(Dc[m].reset_index(drop=True), sc[m], lab),
                             "cond_share_pct": round(float(m.mean()) * 100, 1), "label_in_cond_pct": round(float(Dc.loc[m, lab].sum() / max(Dc[lab].sum(), 1)) * 100, 1)}
        print(mk, json.dumps(res["models"][mk], ensure_ascii=False), flush=True)
    res["elapsed_s"] = round(time.time() - t0)
    out_dir = paths.PROJECT_ROOT / "var" / "out"
    L = ["# 起涨点 / 起跌点 × 图形：事后诊断（只描述；turn_shape_study 登记 d915a9e 的结果之后写的，不改判定）", ""]
    for mk, r in res["models"].items():
        a, b = r["all"], r["within"]
        L.append(f"## {'上涨' if mk == 'rise' else '下跌'}模型（{r['label']}；条件 {r['cond']} = 收盘是近 {BACK} 日{'最低' if r['cond'] == 'lo10' else '最高'}，当天已知）")
        L.append(f"- 确认期样本里 {r['cond']} 占 {r['cond_share_pct']}%，却包含 {r['label_in_cond_pct']}% 的{'起涨点' if r['label'] == 'RS' else '起跌点'}；"
                 f"比例 全部 {a['rate_pct']}% → {r['cond']} 里 {b['rate_pct']}%")
        L.append(f"- AUC：全部 {a['auc']} → 只在 {r['cond']} 里 {b['auc']}")
        L.append(f"- 只在 {r['cond']} 里分十组：最高一组 20 日超额 {b['top']['R20x']:+.2f} pp、U {b['top']['U']}%、D {b['top']['D']}%；"
                 f"最低一组 {b['bottom']['R20x']:+.2f} pp、U {b['bottom']['U']}%、D {b['bottom']['D']}%")
        L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。非投资建议。")
    (out_dir / OUT_MD).write_text("\n".join(L) + "\n", encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
