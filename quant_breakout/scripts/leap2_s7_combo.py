"""leap2_s7_combo.py — 「选股本身的质的飞跃」第 S7 轮探索：加上「突破当天本身」的指标，再搜两两搭配 × 阈值（只描述、不登记；E / J，Z 不看）。

与 S6（scripts/leap2_s6_combo.py）的不同（写在运行之前）：
  ① 指标 33 → 45（scripts/leap2_s7_features.py 的 12 个新指标）；② 每个连续指标 6 条规则（≤ 1/3、≤ 1/2、≤ 2/3、≥ 1/3、≥ 1/2、≥ 2/3 分位）；
  ③ 筛选多一条：E、J 各自保留 ≥ 35% 的信号（S6 登记检验说明保留太少就过不了随机对照）；其余同 S6（笔数 ≥ 40；胜率 ≥ 对照 + 8 pp、
     每笔 ≥ 对照 + 1 pp；4 个半段都不低于对照）；④ 偶然基线同样：打乱结果 20 次。
另报：每个新指标单独的三分位（E / J、W2 保留）；预先写定的合成分 C4 = 秩平均(突破日量比 ↑, 对日経 β ↓, 股息率 ↑, 周线量比 ↑)
  按年代分五档的胜率 / 每笔（连续分数代替硬阈值，不那么怕阈值抖动）。
「放量 ∧ 低 β」这一族 Z 已经用过（S6）：这一轮过筛选的组合如果和 K2 挑的交易重叠 ≥ 50% → 算同一族，只能走前向记录；
  重叠 < 50% 的才算新家族、才可以登记后用 Z 确认一次。
第一次运行（保留 ≥ 35%）两个池子都是 0 个 → 事后再跑一次 `--min-keep 0`（不限保留比例）看全景，输出加后缀 _nokeep（只描述）。
输出：var/out/leap2_s7_combo.md / .json（只有统计）
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
import leap2_s6_features as F6                                               # noqa: E402
import leap2_s7_features as F7                                               # noqa: E402
import leap_common as LC                                                     # noqa: E402
from leap2_s3_explore import tercile_table                                   # noqa: E402
from leap2_s6_combo import BINARY, ERA_PARTS, MEAN_UP, MIN_N, PARTS, PERM, WIN_UP, pair_stats   # noqa: E402
from qbreak import paths                                                     # noqa: E402

MIN_KEEP = 0.35
CUTS = ((1 / 3, "<=", "≤ 1/3 分位"), (1 / 2, "<=", "≤ 中位数"), (2 / 3, "<=", "≤ 2/3 分位"),
        (1 / 3, ">=", "≥ 1/3 分位"), (1 / 2, ">=", "≥ 中位数"), (2 / 3, ">=", "≥ 2/3 分位"))
K2 = {"vr1": (">=", 2.0), "b_n225": ("<=", 0.70)}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def make_rules6(P: pd.DataFrame, cont: list[str], binary: list[str]) -> tuple[np.ndarray, list[dict]]:
    rows, meta = [], []
    for f in cont:
        x = P[f].astype(float).to_numpy()
        ok = np.isfinite(x)
        if ok.sum() < 100:
            continue
        for q, op, lab in CUTS:
            thr = float(np.quantile(x[ok], q))
            rows.append(ok & ((x <= thr) if op == "<=" else (x >= thr)))
            meta.append({"feat": f, "op": op, "thr": thr, "lab": f"{f} {lab}（{thr:.4g}）"})
    for f in binary:
        x = P[f].astype(float).to_numpy()
        for v, lab in ((1.0, "是"), (0.0, "否")):
            rows.append(np.isfinite(x) & (x == v))
            meta.append({"feat": f, "op": "==", "thr": v, "lab": f"{f} {lab}"})
    return np.array(rows, bool), meta


def screen7(R: np.ndarray, meta: list[dict], y: np.ndarray, masks: dict[str, np.ndarray], base: dict) -> tuple[np.ndarray, dict]:
    st = {k: pair_stats(R, y, m) for k, m in masks.items()}
    feat = np.array([m["feat"] for m in meta])
    ok = np.triu(np.ones((len(meta), len(meta)), bool))
    ok &= (feat[:, None] != feat[None, :]) | np.eye(len(meta), dtype=bool)
    for era in ("E", "J"):
        n, w, mu = st[era]
        bw, bm = base[era]
        tot = int(masks[era].sum())
        ok &= (n >= MIN_N) & (n >= MIN_KEEP * tot) & (w >= bw + WIN_UP) & (mu >= bm + MEAN_UP)
        for part in ERA_PARTS[era]:
            _, wp, mp = st[part]
            pw, pm = base[part]
            ok &= (wp >= pw) & (mp >= pm)
    return ok, st


def composite_c4(P: pd.DataFrame) -> pd.Series:
    R = pd.concat([P["vr1"].rank(pct=True), 1 - P["b_n225"].rank(pct=True), P["dy"].rank(pct=True), P["w5v"].rank(pct=True)], axis=1)
    return R.mean(axis=1, skipna=True).where(R.notna().sum(axis=1) >= 3)


def main() -> int:
    global MIN_KEEP
    t0 = time.time()
    if "--min-keep" in sys.argv:
        MIN_KEEP = float(sys.argv[sys.argv.index("--min-keep") + 1])
    suffix = "" if MIN_KEEP == 0.35 else "_nokeep" if MIN_KEEP == 0 else f"_keep{int(MIN_KEEP * 100)}"
    T = F7.build()
    LC.assert_explore_dates(T["sig_date"])
    cont = F6.STOCK + [c for c in F6.EVENT if c not in BINARY] + F6.MARKET + F6.MACRO + F7.NEW
    say(f"# 「选股本身的质的飞跃」第 S7 轮探索：加「突破当天本身」的指标，再搜两两搭配 × 阈值（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s7_combo.py 开头。格子 = 笔数 / 胜率 / 每笔净收益（单独交易，扣成本）。")
    b0 = T[T["n225"] & (T["w2"] == 1)]
    base = {}
    for k, (a, b) in {**{"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}, **PARTS}.items():
        x = b0.loc[(b0["sig_date"] >= a) & (b0["sig_date"] < b), "net"]
        base[k] = (float((x > 0).mean() * 100), float(x.mean()))
    say("对照（日経225 · W2 的单独交易）：" + "；".join(f"{k} {v[0]:.1f}% / {v[1]:+.2f}%" for k, v in base.items()))
    out = {"base": base, "single": {}, "pools": {}, "c4": {}}
    # ── 新指标单独 ──
    for era, (a, b) in (("E", ("2006-10-01", "2016-10-01")), ("J", ("2017-01-01", "2026-10-01"))):
        V = T[T["n225"] & (T["w2"] == 1) & (T["sig_date"] >= a) & (T["sig_date"] < b)]
        say(f"\n## 新指标单独 · {era} · 日経225 · W2（{len(V)} 笔）")
        say("| 指标 | 低 | 中 | 高 | 高 − 低：胜率 pp / 每笔 pp | 高 > 低 的年数 |")
        say("|---|---|---|---|---|---|")
        for f in F7.NEW:
            r = tercile_table(V, f)
            out["single"][f"{era}/{f}"] = r
            if r:
                fm = lambda s: f"{s['n']} / {s['win']:.0f}% / {s['mean']:+.2f}%"                                         # noqa: E731
                say(f"| {f} | {fm(r['low'])} | {fm(r['mid'])} | {fm(r['high'])} | {r['d_win']:+.1f} / {r['d_mean']:+.2f} | {r['years'][0]}/{r['years'][1]} |")
    # ── 合成分 C4 ──
    say("\n## 预先写定的合成分 C4（秩平均：突破日量比 ↑、对日経 β ↓、股息率 ↑、周线量比 ↑）· 日経225 · 全部突破，按年代分五档")
    say("| 年代 | Q1（低） | Q2 | Q3 | Q4 | Q5（高） | 上半（Q4 + Q5） |")
    say("|---|---|---|---|---|---|---|")
    for era, (a, b) in (("E", ("2006-10-01", "2016-10-01")), ("J", ("2017-01-01", "2026-10-01"))):
        V = T[T["n225"] & (T["sig_date"] >= a) & (T["sig_date"] < b)].copy()
        V["c4"] = composite_c4(V)
        ok = V["c4"].notna()
        q = pd.qcut(V.loc[ok, "c4"].rank(method="first"), 5, labels=False)
        cells = []
        for k in range(5):
            y = V.loc[ok][q == k]["net"]
            cells.append(f"{len(y)} / {(y > 0).mean() * 100:.0f}% / {y.mean():+.2f}%")
        y = V.loc[ok][q >= 3]["net"]
        out["c4"][era] = {"cells": cells, "top_half": {"n": int(len(y)), "win": round(float((y > 0).mean() * 100), 1), "mean": round(float(y.mean()), 3)}}
        say(f"| {era} | " + " | ".join(cells) + f" | {len(y)} / {(y > 0).mean() * 100:.0f}% / {y.mean():+.2f}% |")
    # ── 搭配搜索 ──
    rng = np.random.default_rng(0)
    for pool, P in (("P1 日経225", T[T["n225"]]), ("P2 日経225 + T500x", T[T["seg"].isin(["N225", "T500x"])])):
        P = P.reset_index(drop=True)
        R, meta = make_rules6(P, cont, BINARY)
        y = P["net"].to_numpy(float)
        dd = P["sig_date"]
        masks = {"E": ((dd >= "2006-10-01") & (dd < "2016-10-01")).to_numpy(), "J": ((dd >= "2017-01-01") & (dd < "2026-10-01")).to_numpy()}
        masks.update({k: ((dd >= a) & (dd < b)).to_numpy() for k, (a, b) in PARTS.items()})
        ok, st = screen7(R, meta, y, masks, base)
        real = int(ok.sum())
        null = []
        for _ in range(PERM):
            yp = y.copy()
            for era in ("E", "J"):
                idx = np.flatnonzero(masks[era])
                yp[idx] = y[rng.permutation(idx)]
            null.append(int(screen7(R, meta, yp, masks, base)[0].sum()))
        k2 = (np.nan_to_num(P["vr1"].to_numpy(float), nan=-np.inf) >= 2.0) & (np.nan_to_num(P["b_n225"].to_numpy(float), nan=np.inf) <= 0.70)
        say(f"\n## {pool}（{len(P)} 笔：E {int(masks['E'].sum())}、J {int(masks['J'].sum())}；规则 {len(meta)} 条、组合约 {int(np.triu(np.ones((len(meta),) * 2, bool)).sum())} 个；保留 ≥ {MIN_KEEP:.0%}）")
        say(f"- 过筛选的组合：**{real}** 个；打乱结果 {PERM} 次的偶然基线：平均 {np.mean(null):.1f} 个、95% 分位 {np.percentile(null, 95):.0f} 个、最多 {max(null)} 个")
        I, J = np.nonzero(ok)
        rows = []
        for i, j in zip(I, J):
            sel = R[i] & R[j]
            r = {"rule": meta[i]["lab"] + ("" if i == j else " ∧ " + meta[j]["lab"]), "i": int(i), "j": int(j),
                 "overlap_k2": round(float((sel & k2).sum() / max(1, sel.sum())), 2)}
            for k in ("E", "J", "E1", "E2", "J1", "J2"):
                n, w, mu = st[k]
                r[k] = {"n": int(n[i, j]), "win": round(float(w[i, j]), 1), "mean": round(float(mu[i, j]), 3)}
            r["keep"] = {era: round(float(r[era]["n"] / masks[era].sum()), 2) for era in ("E", "J")}
            r["score"] = round(min(r["E"]["win"] - base["E"][0], r["J"]["win"] - base["J"][0]), 1)
            rows.append(r)
        rows.sort(key=lambda r: -r["score"])
        out["pools"][pool] = {"real": real, "null": null, "n_rules": len(meta), "top": rows[:60]}
        if rows:
            say("| 组合 | E | J | 保留 E / J | E1 / E2 胜率 | J1 / J2 胜率 | 与 K2 重叠 | 较差年代的胜率超出 |")
            say("|---|---|---|---|---|---|---|---|")
            fm = lambda s: f"{s['n']} / {s['win']:.0f}% / {s['mean']:+.2f}%"                                            # noqa: E731
            for r in rows[:25]:
                say(f"| {r['rule']} | {fm(r['E'])} | {fm(r['J'])} | {r['keep']['E']:.0%} / {r['keep']['J']:.0%} | {r['E1']['win']:.0f}% / {r['E2']['win']:.0f}% | "
                    f"{r['J1']['win']:.0f}% / {r['J2']['win']:.0f}% | {r['overlap_k2']:.0%} | +{r['score']:.1f} pp |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / f"leap2_s7_combo{suffix}"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
