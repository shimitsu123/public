"""lvs_event_study.py — 大量保有報告書「提出之后」的股价（事件研究；登记版：事件、对照、门槛、读法全部写在这里；提交后不改规则、只运行一次）。

来由：用户 2026-10-05「回到〔63〕的选股方向（TDnet 适时开示 / 大量保有報告書）。」→ 先登记了「大量保有 × 全市場 W2 突破」（scripts/lvs_study.py，6826c2b）。
  登记后、运行前只数个数（没算任何收益）：2021-09-01〜2026-06-25 全市場 W2 突破 3,729 个信号里，前 60 天内有 L1 / L2 / L3 报告的只有 71 / 98 / 28 个
  （1.9% / 2.6% / 0.8%），今天的日経225 只有 0 / 17 / 2 个 → 按登记的 S3（≥ 300 笔）三个都必定不过，而且就算有效也只碰得到约 2% 的突破、碰不到 B3
  → 突破过滤这条路不运行收益（结论 = 不成立：覆盖太少；sim_changes 同日登记记录）。
  改问一个更基本、样本够大的问题：这类报告本身有没有信息 —— 提出之后股价有没有往预期方向走？
  有、而且够大 → 才值得另外登记「事件买点」的引擎精确研究（全市场，用户确认）；没有 → 大量保有这条线结束。不改交易规则、模拟盘、执行器。

一 事件（scripts/lvs_data.py 整理的报告；分类 = scripts/lvs_study.classify：只用书类 350、去掉报告义务发生日 = 2026-05-01 的，分类定义同 lvs_study 三）
  E1 = L1 一般报告的买进（种别 1 / 2 / 3 的新进或增持 ∧ 最近 60 日有市场内取得）：方向 s = +1（之后跑赢）
  E2 = L2 特例报告（种别 4 / 5，机构投资者）的新进或增持：s = +1（先验偏弱：多是被动 / 指数资金）
  E3 = L3 减持 ∧ 最近 60 日有市场内处分：s = −1（之后跑输）
  只描述（不判定）：E4 重要提案行為等 ∧ 新进或增持（积极股东）；E5 一般报告的新进（种别 1）∧ 市场内取得（第一次买到 5%）。
  票要在全市场面板（var/cache/jquants/allstock_panel，东证一般市場）里；t1 = 提出日之后的第一个交易日（提出日当天不算：报告可能收盘后才提出）；
  同一只票同一类事件：离上一个保留的事件不到 20 个交易日的不算新事件（连续的变更报告只算一次）；t1 前要有 61 个交易日、t1 + 59 不超过面板末尾。

二 收益与对照
  r_H = 收盘[t1 + H − 1] ÷ 开盘[t1] − 1（复权价；中途退市 = 用最后一个收盘，TOB 也一样）；H = 20 / 60 个交易日。
  对照格子（t1 − 1 收盘时已知）：市值五分位 × 过去 60 个交易日收益五分位（25 格；全部有值的股票分格）；对照 = 同一天、同一格全部股票的 r_H 等权平均；
  超额 AR_H = r_H − 对照（控制规模与动量：报告前的买盘常把股价推高，不能把动量当成报告的信息）。
  只描述：提出前 20 个交易日的超额（C[t1 − 1] ÷ C[t1 − 21] − 1 减同一市值五分位的平均）= 信息在提出之前已经反映了多少。
  区间：按 t1 所在周（W-FRI）聚类的自助法 2,000 次（种子 20261005）→ 每笔均值的 95% 区间。

三 判定（每类事件；s × = 往预期方向）
  G1 s × 平均 AR20 > 0 且 s × AR20 的周聚类 95% 区间下限 > 0；G2 s × 平均 AR60 > 0；G3 s × AR20 中位数 > 0；
  G4 前一半（t1 ≤ 2023-12-29）与后一半（t1 ≥ 2024-01-04）的 s × 平均 AR20 都 > 0；G5 s × 平均 AR20 ≥ 1.0 pp（够付来回成本与滑点的大小）。
  档位：G1〜G5 全过 = 「有信息而且够大」→ 提议另外登记「事件买点」的引擎精确研究（全市场 W2 池同一套逐笔、对照与档位；用户确认）；
    G1 ∧ G3 ∧ G4 过（G2 或 G5 不过）= 「有信息但不够大」→ 只记录；其余 = 「没有信息」。
  3 类事件的家族偶然率：G1 单独约 3 × 2.5%，加上 G3、G4 约 2〜4%。

四 前视与数据质量（事先声明）：只用提出日 < t1 的报告；报告是「今天看到的」集合（不用订正）；2026-05-01 制度变更那一天的报告不用、之后的格式变了
  （2026-06 的特例报告个数是平时的 2〜3 倍 → 另报 t1 ≥ 2026-05-01 的事件个数）；面板只有东证一般市場；市值五分位按当天有值的全部股票分；
  输出只有统计（var/out/lvs_event_study.md / .json），没有个别报告、提出者或个股名单。

五 诚实的预期：E1 约 35% 到「有信息」、约 15% 到「有信息而且够大」（研究里超额多在公告前后几天，之后的漂移小）；E2 约 10%；E3 约 20%；
  3 类都「没有信息」的可能最大（约 50%）。非投资建议。

用法：python scripts/lvs_event_study.py --counts（登记前只数事件个数）；python scripts/lvs_event_study.py --run
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402
import lvs_data as LD                                                         # noqa: E402
import lvs_study as LS                                                        # noqa: E402

START = "2021-07-01"
H_SHORT, H_LONG, PRE, PAST, GAP, NQ = 20, 60, 20, 60, 20, 5
HALF_END, HALF2_START = "2023-12-29", "2024-01-04"
TRANSITION = LS.TRANSITION
BOOT_N, SEED, BIG_PP = 2000, 20261005, 1.0
TYPES = {"E1": ("L1", 1, "一般报告的买进（新进或增持 ∧ 市场内取得）"), "E2": ("L2", 1, "特例报告（机构）的新进或增持"),
         "E3": ("L3", -1, "减持 ∧ 市场内处分")}
DESC = {"E4": "重要提案行為等 ∧ 新进或增持（积极股东）", "E5": "一般报告的新进（种别 1）∧ 市场内取得"}
OUT_MD, OUT_JSON = "lvs_event_study.md", "lvs_event_study.json"


# ───────────────────────── 事件 ─────────────────────────
def type_mask(o: pd.DataFrame, key: str) -> np.ndarray:
    if key in TYPES:
        return o[TYPES[key][0]].to_numpy(bool)
    if key == "E4":
        return (o["imp"] & o["up"]).to_numpy(bool)
    if key == "E5":
        return ((o["lh_type"].astype(str) == "1") & o["buy_mkt"].astype(bool)).to_numpy(bool)
    raise KeyError(key)


def dedupe(k1: np.ndarray, gap: int = GAP) -> np.ndarray:
    """升序的 t1 位置 → 保留的（离上一个保留的 ≥ gap 个交易日）。"""
    keep = np.zeros(len(k1), bool)
    last = None
    for i, k in enumerate(k1):
        if last is None or k - last >= gap:
            keep[i] = True
            last = k
    return keep


def events(o: pd.DataFrame, days: pd.DatetimeIndex, names: list[str], key: str) -> pd.DataFrame:
    """某一类事件：票在面板里、t1 = 提出日之后第一个交易日、前后够长、同票去重。"""
    col = {t: j for j, t in enumerate(names)}
    x = o[type_mask(o, key) & o["ticker"].isin(col).to_numpy() & (o["sub_date"] >= pd.Timestamp(START)).to_numpy()].copy()
    if not len(x):
        return pd.DataFrame(columns=["ticker", "j", "sub_date", "k1", "t1"])
    x["k1"] = np.searchsorted(days.to_numpy(dtype="datetime64[ns]"), x["sub_date"].to_numpy(dtype="datetime64[ns]"), side="right")
    x = x[(x["k1"] >= PAST + 1) & (x["k1"] + H_LONG - 1 <= len(days) - 1)]
    x = x.sort_values(["ticker", "k1"], kind="stable").reset_index(drop=True)
    keep = np.zeros(len(x), bool)
    for _, g in x.groupby("ticker", sort=False):
        keep[g.index.to_numpy()] = dedupe(g["k1"].to_numpy())
    x = x[keep].copy()
    x["j"] = x["ticker"].map(col).astype(int)
    x["t1"] = days[x["k1"].to_numpy()]
    return x[["ticker", "j", "sub_date", "rpt_date", "k1", "t1"]].reset_index(drop=True)


# ───────────────────────── 收益与对照 ─────────────────────────
def ffill_close(C: np.ndarray) -> np.ndarray:
    """收盘价沿时间向前填（退市后 = 最后一个收盘；上市前仍是 NaN）。"""
    return pd.DataFrame(C).ffill().to_numpy(float)


def quintile(x: np.ndarray, valid: np.ndarray, n: int = NQ) -> np.ndarray:
    """有值的按秩分 n 组（0..n−1），无值 −1。"""
    out = np.full(len(x), -1, int)
    idx = np.where(valid)[0]
    if len(idx) < n:
        return out
    r = pd.Series(x[idx]).rank(method="first").to_numpy()
    out[idx] = np.minimum((r - 1) * n // len(idx), n - 1).astype(int)
    return out


def day_cells(k: int, MC: np.ndarray, C: np.ndarray) -> np.ndarray:
    """t1 = k 那天的对照格子（市值五分位 × 过去 60 日收益五分位；t1 − 1 收盘已知）；无值 −1。"""
    mc = MC[k - 1].astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        past = C[k - 1].astype(float) / C[k - 1 - PAST].astype(float) - 1
    v = np.isfinite(mc) & (mc > 0) & np.isfinite(past)
    a, b = quintile(mc, v), quintile(past, v)
    return np.where(v, a * NQ + b, -1)


def abnormal(ev: pd.DataFrame, O: np.ndarray, C: np.ndarray, Cff: np.ndarray, MC: np.ndarray, H: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """每个事件的 (r_H, AR_H, 市值五分位)：r = Cff[t1 + H − 1] ÷ O[t1] − 1；对照 = 同一天同一格的等权平均。ev 要是 RangeIndex。"""
    r_out = np.full(len(ev), np.nan)
    ar_out = np.full(len(ev), np.nan)
    sq_out = np.full(len(ev), -1, int)
    for k, g in ev.groupby("k1"):
        k = int(k)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = Cff[k + H - 1] / O[k].astype(float) - 1
        cell = day_cells(k, MC, C)
        ok = (cell >= 0) & np.isfinite(r)
        means = pd.Series(r[ok]).groupby(cell[ok]).mean()
        jj = g["j"].to_numpy()
        rr = r[jj]
        bench = means.reindex(cell[jj]).to_numpy(float)
        r_out[g.index.to_numpy()] = rr
        ar_out[g.index.to_numpy()] = np.where(cell[jj] >= 0, rr - bench, np.nan)
        sq_out[g.index.to_numpy()] = np.where(cell[jj] >= 0, cell[jj] // NQ, -1)
    return r_out, ar_out, sq_out


def pre_abnormal(ev: pd.DataFrame, C: np.ndarray, MC: np.ndarray) -> np.ndarray:
    """只描述：提出前 20 个交易日的超额（C[t1 − 1] ÷ C[t1 − 21] − 1 减同一市值五分位的平均；市值在 t1 − 21）。"""
    out = np.full(len(ev), np.nan)
    for k, g in ev.groupby("k1"):
        k = int(k)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = C[k - 1].astype(float) / C[k - 1 - PRE].astype(float) - 1
        mc = MC[k - 1 - PRE].astype(float)
        v = np.isfinite(r) & np.isfinite(mc) & (mc > 0)
        q = quintile(mc, v)
        means = pd.Series(r[v]).groupby(q[v]).mean()
        jj = g["j"].to_numpy()
        out[g.index.to_numpy()] = np.where(q[jj] >= 0, r[jj] - means.reindex(q[jj]).to_numpy(float), np.nan)
    return out


def boot_ci(x: np.ndarray, weeks: np.ndarray, n: int = BOOT_N, seed: int = SEED) -> tuple[float | None, float | None]:
    """按周聚类的自助法：均值的 2.5 / 97.5 分位。"""
    m = np.isfinite(x)
    x, weeks = x[m], weeks[m]
    if len(x) < 10:
        return None, None
    codes, uniq = pd.factorize(weeks)
    s = np.bincount(codes, weights=x, minlength=len(uniq))
    c = np.bincount(codes, minlength=len(uniq)).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uniq), size=(n, len(uniq)))
    bm = s[idx].sum(1) / c[idx].sum(1)
    return round(float(np.percentile(bm, 2.5)) * 100, 3), round(float(np.percentile(bm, 97.5)) * 100, 3)


def stats(ar: np.ndarray, weeks: np.ndarray | None = None) -> dict:
    """超额的 n / 平均 / 中位数 / 正的比例（%、pp）+ 周聚类区间。"""
    x = ar[np.isfinite(ar)]
    if not len(x):
        return {"n": 0}
    out = {"n": int(len(x)), "mean": round(float(x.mean()) * 100, 3), "median": round(float(np.median(x)) * 100, 3), "pos": round(float((x > 0).mean()) * 100, 1)}
    if weeks is not None:
        lo, hi = boot_ci(ar, weeks)
        out["ci"] = [lo, hi]
    return out


# ───────────────────────── 判定 ─────────────────────────
def judge(key: str, s20: dict, s60: dict, halves: dict) -> dict:
    s = TYPES[key][1]
    g = {}
    lo, hi = (s20.get("ci") or [None, None])
    slo = None if lo is None else (lo if s > 0 else -hi)
    g["G1"] = bool(s20.get("n")) and s * s20["mean"] > 0 and slo is not None and slo > 0
    g["G2"] = bool(s60.get("n")) and s * s60["mean"] > 0
    g["G3"] = bool(s20.get("n")) and s * s20["median"] > 0
    g["G4"] = all(bool(h.get("n")) and s * h["mean"] > 0 for h in halves.values()) and len(halves) == 2
    g["G5"] = bool(s20.get("n")) and s * s20["mean"] >= BIG_PP
    if all(g.values()):
        tier = "有信息而且够大 → 提议另外登记「事件买点」的引擎精确研究（全市场；用户确认）"
    elif g["G1"] and g["G3"] and g["G4"]:
        tier = "有信息但不够大（只记录）"
    else:
        tier = "没有信息"
    return {"gates": g, "tier": tier, "s_lo": slo}


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/lvs_event_study.py", "scripts/lvs_study.py", "scripts/lvs_data.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def half_masks(t1: pd.Series) -> dict:
    return {"H1": (t1 <= pd.Timestamp(HALF_END)).to_numpy(), "H2": (t1 >= pd.Timestamp(HALF2_START)).to_numpy()}


def counts(evs: dict, n225: set) -> dict:
    out = {}
    for key, ev in evs.items():
        if not len(ev):
            out[key] = {"n": 0}
            continue
        hm = half_masks(ev["t1"])
        out[key] = {"n": int(len(ev)), "H1": int(hm["H1"].sum()), "H2": int(hm["H2"].sum()), "tickers": int(ev["ticker"].nunique()),
                    "n225_today": int(ev["ticker"].isin(n225).sum()), "after_transition": int((ev["t1"] >= pd.Timestamp(TRANSITION)).sum()),
                    "by_year": {int(y): int(c) for y, c in ev["t1"].dt.year.value_counts().sort_index().items()}}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="大量保有報告書提出之后的股价（事件研究；登记版）")
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if not (a.counts or a.run):
        raise SystemExit("要 --counts 或 --run")
    logging.disable(logging.CRITICAL)
    t0 = time.time()
    import allstock_data as AD
    A = AD.load()
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    o = LS.classify(LD.load())
    n225 = LS.n225_today()
    keys = list(TYPES) + list(DESC)
    evs = {k: events(o, days, names, k) for k in keys}
    cnt = counts(evs, n225)
    if a.counts:
        print(json.dumps(cnt, ensure_ascii=False, indent=1))
        return 0
    O, C, MC = A["O"], A["C"], A["MC"]
    Cff = ffill_close(C)
    res = {"git": git_info(), "days": [str(days[0].date()), str(days[-1].date())], "counts": cnt, "types": {}}
    for key in keys:
        ev = evs[key]
        if not len(ev):
            res["types"][key] = {"n": 0}
            continue
        wk = ev["t1"].dt.to_period("W-FRI").astype(str).to_numpy()
        r20, ar20, size_q = abnormal(ev, O, C, Cff, MC, H_SHORT)
        _, ar60, _ = abnormal(ev, O, C, Cff, MC, H_LONG)
        pre = pre_abnormal(ev, C, MC)
        hm = half_masks(ev["t1"])
        s20, s60 = stats(ar20, wk), stats(ar60, wk)
        halves = {h: stats(ar20[m], wk[m]) for h, m in hm.items()}
        rec = {"desc": TYPES[key][2] if key in TYPES else DESC[key], "sign": TYPES[key][1] if key in TYPES else None,
               "ar20": s20, "ar60": s60, "raw20": stats(r20), "pre20": stats(pre), "halves": halves,
               "by_size": {int(q): stats(ar20[size_q == q]) for q in range(NQ)},
               "n225_today": stats(ar20[ev["ticker"].isin(n225).to_numpy()]),
               "by_year": {int(y): stats(ar20[(ev["t1"].dt.year == y).to_numpy()]) for y in sorted(ev["t1"].dt.year.unique())},
               "after_transition": stats(ar20[(ev["t1"] >= pd.Timestamp(TRANSITION)).to_numpy()])}
        if key in TYPES:
            rec.update(judge(key, s20, s60, halves))
        res["types"][key] = rec
        print(f"{key}：{len(ev)} 个事件；{time.time() - t0:.0f}s", flush=True)
    res["elapsed_s"] = round(time.time() - t0)
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report(res)
    (out_dir / OUT_MD).write_text(md + "\n", encoding="utf-8")
    (out_dir / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md)
    return 0


def _s(x: dict | None) -> str:
    if not x or not x.get("n"):
        return "n=0"
    ci = f"，区间 {x['ci'][0]}〜{x['ci'][1]}" if x.get("ci") and x["ci"][0] is not None else ""
    return f"n={x['n']} 平均 {x['mean']:+.2f} pp、中位数 {x['median']:+.2f} pp、为正 {x['pos']:.1f}%{ci}"


def report(res: dict) -> str:
    L = [f"# 大量保有報告書提出之后的股价（事件研究；git {res['git']['rev']}{'（脏）' if res['git'].get('dirty') else ''}；只运行一次）", "",
         f"面板 {res['days'][0]}〜{res['days'][1]}；超额 = 同一天、同一格（市值五分位 × 过去 60 日收益五分位）等权平均之上的部分；t1 = 提出日之后第一个交易日的开盘买", ""]
    for key, r in res["types"].items():
        if not r.get("n", 1):
            L.append(f"## {key}：没有事件")
            continue
        L.append(f"## {key} {r['desc']}" + (f"（方向 {'之后跑赢' if r['sign'] > 0 else '之后跑输'}）" if r.get("sign") else "（只描述）"))
        L.append(f"- 20 日超额：{_s(r['ar20'])}")
        L.append(f"- 60 日超额：{_s(r['ar60'])}")
        L.append(f"- 20 日原始收益：{_s(r['raw20'])}；提出前 20 日超额（只描述）：{_s(r['pre20'])}")
        L.append("- 两半：" + "；".join(f"{h} {_s(v)}" for h, v in r["halves"].items()))
        L.append("- 按市值五分位（0 最小）：" + "；".join(f"{q} {_s(v)}" for q, v in r["by_size"].items()))
        L.append(f"- 今天的日経225：{_s(r['n225_today'])}；t1 ≥ 2026-05-01（制度变更后）：{_s(r['after_transition'])}")
        L.append("- 按年：" + "；".join(f"{y} {_s(v)}" for y, v in r["by_year"].items()))
        if "gates" in r:
            L.append("- 判定：" + "、".join(f"{g} {'✓' if ok else '✗'}" for g, ok in r["gates"].items()) + f" → **{r['tier']}**")
        L.append("")
    L.append(f"事件个数（登记前已数）：{json.dumps(res['counts'], ensure_ascii=False)}")
    L.append("")
    L.append(f"耗时 {res['elapsed_s']} s。读法与档位见脚本开头（登记时写定）。非投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
