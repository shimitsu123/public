"""pressure_threat_posthoc.py — 综合压力指数 × 威胁指数一起看会怎样（事后描述，2026-09-29；用户问；不参与判定、不改规则）。

用户：「综合压力指数和威胁指数一起考虑结果会如何」。
两个指数都已经在同一段美国 / 日本数据上评估过（威胁指数 A0：threat_index_study；综合压力：pressure_study 38b648e），
所以这里只能是描述：不是检验，结果不改任何规则。
- 威胁指数 = 日报里的 A0（qbreak/threat.py：VIX、VIX 变化、信用利差扩大、曲线倒挂、利率急升、油价、失业、指数波动；日本另加日元、日本国债），每天；
- 综合压力 = pressure_study 的 P_all（离两年低点的涨幅、250 日线乖离、利率上升、曲线变平、信用利差收窄、波动低、宽度），每个月末；
- 样本 = 两个都有值的月末（美国、日本都约 1993〜），目标 = 之后 60 个交易日内跌 ≥ 10%（威胁指数的目标），另报一年内跌 ≥ 10%。
看：两者的相关；A0 单独、压力单独、两种等权组合（「两个都高 = 危险」：平均(A0, 压力)；「威胁高、压力已释放 = 危险」：平均(A0, 100 − 压力)）
的 AUC 与前后两半（〜2010 / 2011〜）；A0 三分位 × 压力三分位的 9 格里之后跌 ≥ 10% 的比例；现在落在哪一格。
第二种组合的方向是看过 pressure_study 之后才知道的（60 天里压力是反向的）→ 两种都报，不挑。非投资建议。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

SPLIT, N_BOOT, SEED, BLOCK = "2011-01-01", 2000, 20260929, 24
HS = (60, 250)


def month_asof(daily: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """每个月末取「当天或之前」最后一个日值。"""
    s = daily.dropna().sort_index()
    pos = s.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    return pd.Series(np.where(pos >= 0, s.to_numpy(float)[np.clip(pos, 0, None)], np.nan), index=dates)


def combos(a0: pd.Series, p: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"A0": a0, "P": p, "P_inv": 100 - p, "C_both": (a0 + p) / 2, "C_rel": (a0 + (100 - p)) / 2})


def grid(a0: pd.Series, p: pd.Series, ev: pd.Series) -> dict:
    """A0 三分位 × 压力三分位 → 每格的月末数与之后跌 ≥ 10% 的比例（分位点用样本自己的）。"""
    d = pd.DataFrame({"a": a0, "p": p, "e": ev}).dropna()
    qa, qp = d["a"].quantile([1 / 3, 2 / 3]).to_numpy(), d["p"].quantile([1 / 3, 2 / 3]).to_numpy()
    d["ga"], d["gp"] = np.searchsorted(qa, d["a"], side="right"), np.searchsorted(qp, d["p"], side="right")
    cells = {}
    for ga in range(3):
        for gp in range(3):
            m = (d["ga"] == ga) & (d["gp"] == gp)
            cells[f"{ga}{gp}"] = {"n": int(m.sum()), "rate": None if not m.any() else round(float(d["e"][m].mean() * 100), 1)}
    return {"cells": cells, "qa": [round(float(x), 1) for x in qa], "qp": [round(float(x), 1) for x in qp],
            "base": round(float(d["e"].mean() * 100), 1), "n": int(len(d))}


def cell_of(a: float, p: float, g: dict) -> str:
    return f"{int(np.searchsorted(g['qa'], a, side='right'))}{int(np.searchsorted(g['qp'], p, side='right'))}"


def boot_diff(s1: pd.Series, s0: pd.Series, ev: pd.Series, block: int = BLOCK, n_boot: int = N_BOOT, seed: int = SEED) -> tuple | None:
    """AUC(s1) − AUC(s0) 的 95% 区间：月末按 24 个月一段（环形）整段重抽。"""
    import pressure_study as PS
    d = pd.DataFrame({"a": s1, "b": s0, "e": ev}).dropna()
    n = len(d)
    if n < 2 * block:
        return None
    A, B, E = d["a"].to_numpy(), d["b"].to_numpy(), d["e"].to_numpy()
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = (rng.integers(0, n, int(np.ceil(n / block)))[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        x, y = PS.auc(pd.Series(A[idx]), pd.Series(E[idx])), PS.auc(pd.Series(B[idx]), pd.Series(E[idx]))
        if x is not None and y is not None:
            vals.append(x - y)
    return (round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)) if vals else None


def main() -> int:
    import pressure_study as PS
    from qbreak import threat as TH
    built = TH.build(TH.load_inputs())
    out, now = {}, {}
    for mkt in ("US", "JP"):
        raw, S, T, cur, c = PS.build(mkt)
        a0d = built[mkt][0]
        a0 = month_asof(a0d, S.index)
        X = combos(a0, S["P_all"])
        m = X[["A0", "P"]].notna().all(axis=1)
        X, T2 = X[m], T[m]
        res = {"n": int(len(X)), "start": str(X.index[0].date()), "corr": round(float(X["A0"].rank().corr(X["P"].rank())), 3)}
        for h in HS:
            ev = T2[f"ev{h}"]
            r = {}
            for k in X.columns:
                full = PS.auc(X[k], ev)
                h1 = PS.auc(X[k][X.index < SPLIT], ev[X.index < SPLIT])
                h2 = PS.auc(X[k][X.index >= SPLIT], ev[X.index >= SPLIT])
                r[k] = [None if v is None else round(v, 3) for v in (full, h1, h2)]
            r["diff_rel"] = boot_diff(X["C_rel"], X["A0"], ev)
            r["diff_both"] = boot_diff(X["C_both"], X["A0"], ev)
            r["grid"] = grid(X["A0"], X["P"], ev)
            res[f"h{h}"] = r
        out[mkt] = res
        a_now, p_now = float(a0d.dropna().iloc[-1]), PS.now_reading(raw, cur, S, T)["P_all"]
        g = res["h60"]["grid"]
        cell = cell_of(a_now, p_now, g) if p_now is not None else None
        now[mkt] = {"A0": round(a_now, 1), "A0_date": str(a0d.dropna().index[-1].date()), "P_all": p_now, "cell": cell,
                    "rate60": g["cells"][cell]["rate"] if cell else None, "n60": g["cells"][cell]["n"] if cell else None,
                    "rate250": res["h250"]["grid"]["cells"][cell_of(a_now, p_now, res["h250"]["grid"])]["rate"] if cell else None}
    fm = lambda v, f="{:.3f}": "—" if v is None else f.format(v)                                    # noqa: E731
    nm = {"A0": "威胁指数 A0", "P": "综合压力", "P_inv": "100 − 综合压力", "C_both": "平均(A0, 压力)", "C_rel": "平均(A0, 100 − 压力)"}
    lvl = ["低", "中", "高"]
    L = ["# 综合压力 × 威胁指数一起看（事后描述，2026-09-29；两个指数都已在同一段数据上评估过，不是检验，不改规则）", ""]
    for mkt in ("US", "JP"):
        r = out[mkt]
        L += [f"## {'美国 S&P 500' if mkt == 'US' else '日本 日経225'}（{r['start']}〜，{r['n']} 个月末；A0 与压力的秩相关 {r['corr']:+.2f}）", "",
              "| 指数 | 60 天内跌 ≥ 10% 的 AUC 全部 / 〜2010 / 2011〜 | 一年内跌 ≥ 10% 的 AUC 全部 / 〜2010 / 2011〜 |", "|---|---|---|"]
        for k in nm:
            a, b = r["h60"][k], r["h250"][k]
            L.append(f"| {nm[k]} | {fm(a[0])} / {fm(a[1])} / {fm(a[2])} | {fm(b[0])} / {fm(b[1])} / {fm(b[2])} |")
        for h in HS:
            dr, db = r[f"h{h}"]["diff_rel"], r[f"h{h}"]["diff_both"]
            L.append(f"- {h} 天：平均(A0, 100 − 压力) − A0 的 AUC 差 95% 区间 {dr}；平均(A0, 压力) − A0 {db}")
        g = r["h60"]["grid"]
        L += ["", f"之后 60 天内跌 ≥ 10% 的比例（全部 {g['base']}%；A0 分点 {g['qa']}，压力分点 {g['qp']}）：", "",
              "| A0 \\ 压力 | 低 | 中 | 高 |", "|---|---|---|---|"]
        for ga in range(3):
            L.append(f"| {lvl[ga]} | " + " | ".join(f"{g['cells'][f'{ga}{gp}']['rate']}%（{g['cells'][f'{ga}{gp}']['n']}）" for gp in range(3)) + " |")
        n = now[mkt]
        if n["cell"]:
            L += ["", f"现在：A0 {n['A0']}（{n['A0_date']}）、综合压力 {n['P_all']} → 威胁{lvl[int(n['cell'][0])]} × 压力{lvl[int(n['cell'][1])]} 这一格："
                  f"历史上之后 60 天内跌 ≥ 10% {n['rate60']}%（{n['n60']} 个月末），一年内跌 ≥ 10% {n['rate250']}%", ""]
    L.append("非投资建议。")
    print("\n".join(L))
    fp = paths.out_dir() / "pressure_threat_posthoc"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"results": out, "now": now}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
