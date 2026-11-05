"""leap2_s6_combo.py — 「选股本身的质的飞跃」第 S6 轮探索：指标两两搭配 × 阈值搜索（只描述、不登记；E / J，Z 不看）。

用户（2026-09-27）：「继续找新方向 各个分析指数互相搭配 调整阈值进行研究」。
做法（写在运行之前，防止在几千个组合里挑到偶然好的）：
一、池子（单独交易，scripts/leap2_s6_features.py 的全部指标表）：P1 = 日経225 的全部突破（不加 W2）；
   P2 = 日経225 + T500x（TOPIX 500 级，今天的成分）的全部突破。W2（周线量比 ≥ 1）本身也当一条规则。
二、规则：每个连续指标 4 条 —— ≤ 1/3 分位、≤ 中位数、≥ 中位数、≥ 2/3 分位（分位点 = 这个池子 E + J 合起来的分位，是固定数字，
   以后在 Z 上原样用）；二值指标（w2、earn、hi3y）2 条（是 / 否）。组合 = 单条规则，或两条不同指标的规则「且」。
三、筛选（E、J 各自）：笔数 ≥ 40；胜率 ≥ 对照 + 8 pp、每笔 ≥ 对照 + 1 pp（对照 = 日経225 · W2 的单独交易）；
   4 个半段（E1 2006-10〜2011-09 / E2 / J1 2017〜2021 / J2）各自的胜率与每笔都不低于同一半段的对照。
四、偶然的基线：每个年代里把交易结果随机打乱 20 次、重跑同样的搜索 → 「过筛选」的组合平均有几个、95% 分位几个；
   真实的个数要明显多于它，才说明搜到的不只是运气。
五、过筛选的组合按「两个年代里较差那个的胜率超出对照多少」排序，报前 25；下一步（S6b）把前几个放进组合 + 随机对照（门槛 S5）。
输出：var/out/leap2_s6_combo.md / .json（只有统计）
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
import leap2_s6_features as FT                                               # noqa: E402
import leap_common as LC                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402

PARTS = {"E1": ("2006-10-01", "2011-10-01"), "E2": ("2011-10-01", "2016-10-01"), "J1": ("2017-01-01", "2022-01-01"), "J2": ("2022-01-01", "2026-10-01")}
ERA_PARTS = {"E": ("E1", "E2"), "J": ("J1", "J2")}
BINARY = ["w2", "earn", "hi3y"]
MIN_N, WIN_UP, MEAN_UP, PERM = 40, 8.0, 1.0, 20
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def make_rules(P: pd.DataFrame, cont: list[str], binary: list[str]) -> tuple[np.ndarray, list[dict]]:
    """规则矩阵（规则 × 交易，布尔）与说明。连续指标的分位点 = 这个池子全部（E + J）有值的交易的分位；缺值 → 不满足。"""
    rows, meta = [], []
    for f in cont:
        x = P[f].astype(float).to_numpy()
        ok = np.isfinite(x)
        if ok.sum() < 100:
            continue
        q = np.quantile(x[ok], [1 / 3, 1 / 2, 2 / 3])
        for op, thr, lab in (("<=", q[0], "≤ 1/3 分位"), ("<=", q[1], "≤ 中位数"), (">=", q[1], "≥ 中位数"), (">=", q[2], "≥ 2/3 分位")):
            rows.append(ok & ((x <= thr) if op == "<=" else (x >= thr)))
            meta.append({"feat": f, "op": op, "thr": float(thr), "lab": f"{f} {lab}（{thr:.4g}）"})
    for f in binary:
        x = P[f].astype(float).to_numpy()
        for v, lab in ((1.0, "是"), (0.0, "否")):
            rows.append(np.isfinite(x) & (x == v))
            meta.append({"feat": f, "op": "==", "thr": v, "lab": f"{f} {lab}"})
    return np.array(rows, bool), meta


def pair_stats(R: np.ndarray, y: np.ndarray, sel: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """sel = 这一段的交易掩码 → 规则 i ∧ 规则 j 的（笔数、胜率 %、每笔平均）矩阵（对角 = 单条规则）。"""
    A = (R & sel[None, :]).astype(float)
    n = A @ A.T
    w = (A * (y > 0)[None, :]) @ A.T
    s = (A * y[None, :]) @ A.T
    with np.errstate(invalid="ignore", divide="ignore"):
        return n, np.where(n > 0, w / n * 100, np.nan), np.where(n > 0, s / n, np.nan)


def screen(R: np.ndarray, meta: list[dict], y: np.ndarray, masks: dict[str, np.ndarray], base: dict[str, tuple[float, float]]) -> tuple[np.ndarray, dict]:
    """过筛选的 (i, j)（i ≤ j，不同指标或同一条）布尔矩阵 + 各段统计。base = {段: (胜率, 每笔)}（E、J 与 4 个半段）。"""
    st = {k: pair_stats(R, y, m) for k, m in masks.items()}
    feat = np.array([m["feat"] for m in meta])
    ok = np.triu(np.ones((len(meta), len(meta)), bool))
    ok &= (feat[:, None] != feat[None, :]) | np.eye(len(meta), dtype=bool)
    for era in ("E", "J"):
        n, w, mu = st[era]
        bw, bm = base[era]
        ok &= (n >= MIN_N) & (w >= bw + WIN_UP) & (mu >= bm + MEAN_UP)
        for part in ERA_PARTS[era]:
            _, wp, mp = st[part]
            pw, pm = base[part]
            ok &= (wp >= pw) & (mp >= pm)
    return ok, st


def main() -> int:
    t0 = time.time()
    T = FT.build()
    LC.assert_explore_dates(T["sig_date"])
    cont = FT.STOCK + [c for c in FT.EVENT if c not in BINARY] + FT.MARKET + FT.MACRO
    d = T["sig_date"]
    say(f"# 「选股本身的质的飞跃」第 S6 轮探索：指标两两搭配 × 阈值搜索（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s6_combo.py 开头（指标表 scripts/leap2_s6_features.py）。格子 = 笔数 / 胜率 / 每笔净收益（单独交易，扣成本）。")
    b0 = T[T["n225"] & (T["w2"] == 1)]
    base = {}
    for k, (a, b) in {**{"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}, **PARTS}.items():
        x = b0.loc[(b0["sig_date"] >= a) & (b0["sig_date"] < b), "net"]
        base[k] = (float((x > 0).mean() * 100), float(x.mean()))
    say("对照（日経225 · W2 的单独交易）：" + "；".join(f"{k} {v[0]:.1f}% / {v[1]:+.2f}%" for k, v in base.items()))
    out = {"base": base, "pools": {}}
    rng = np.random.default_rng(0)
    for pool, P in (("P1 日経225", T[T["n225"]]), ("P2 日経225 + T500x", T[T["seg"].isin(["N225", "T500x"])])):
        P = P.reset_index(drop=True)
        R, meta = make_rules(P, cont, BINARY)
        y = P["net"].to_numpy(float)
        dd = P["sig_date"]
        masks = {"E": ((dd >= "2006-10-01") & (dd < "2016-10-01")).to_numpy(), "J": ((dd >= "2017-01-01") & (dd < "2026-10-01")).to_numpy()}
        masks.update({k: ((dd >= a) & (dd < b)).to_numpy() for k, (a, b) in PARTS.items()})
        ok, st = screen(R, meta, y, masks, base)
        real = int(ok.sum())
        null = []
        for _ in range(PERM):
            yp = y.copy()
            for era in ("E", "J"):
                idx = np.flatnonzero(masks[era])
                yp[idx] = y[rng.permutation(idx)]
            null.append(int(screen(R, meta, yp, masks, base)[0].sum()))
        ncomb = int(np.triu(np.ones((len(meta), len(meta)), bool)).sum())
        say(f"\n## {pool}（{len(P)} 笔：E {int(masks['E'].sum())}、J {int(masks['J'].sum())}；规则 {len(meta)} 条、组合约 {ncomb} 个）")
        say(f"- 过筛选的组合：**{real}** 个；打乱结果 {PERM} 次的偶然基线：平均 {np.mean(null):.1f} 个、95% 分位 {np.percentile(null, 95):.0f} 个、最多 {max(null)} 个")
        I, J = np.nonzero(ok)
        rows = []
        for i, j in zip(I, J):
            r = {"rule": meta[i]["lab"] + ("" if i == j else " ∧ " + meta[j]["lab"]), "i": int(i), "j": int(j)}
            for k in ("E", "J", "E1", "E2", "J1", "J2"):
                n, w, mu = st[k]
                r[k] = {"n": int(n[i, j]), "win": round(float(w[i, j]), 1), "mean": round(float(mu[i, j]), 3)}
            r["score"] = round(min(r["E"]["win"] - base["E"][0], r["J"]["win"] - base["J"][0]), 1)
            rows.append(r)
        rows.sort(key=lambda r: -r["score"])
        out["pools"][pool] = {"real": real, "null": null, "n_rules": len(meta), "rules": meta, "top": rows[:60]}
        if rows:
            say("| 组合 | E | J | E1 / E2 胜率 | J1 / J2 胜率 | 较差年代的胜率超出 |")
            say("|---|---|---|---|---|---|")
            fm = lambda s: f"{s['n']} / {s['win']:.0f}% / {s['mean']:+.2f}%"                                            # noqa: E731
            for r in rows[:25]:
                say(f"| {r['rule']} | {fm(r['E'])} | {fm(r['J'])} | {r['E1']['win']:.0f}% / {r['E2']['win']:.0f}% | "
                    f"{r['J1']['win']:.0f}% / {r['J2']['win']:.0f}% | +{r['score']:.1f} pp |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s6_combo"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
