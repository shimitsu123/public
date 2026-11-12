"""loop12_r05_mix.py — 第十二个研究循环第 5 轮：PER / 销售指引（路线 J）+ 月初月末（路线 A / B）（规则 scripts/research_loop12.py）。
（2026-10-12 登记；先提交后只运行一次。看过第 1〜4 轮之后设计，但不是它们的变体。）

  PEH〔选股·估值〕：PER = 信号日收盘 ÷ 最近一次年度（FY）决算短信的 EPS（EPS > 0 才算；400 天以内）≥ J 信号 PER 的 80 分位 → 不买（路线 J）。
  FGR〔选股·成长〕：最近一次决算短信给的当期销售额予想 ÷ 上一期（FY）实绩销售额 − 1 < 0 → 不买（销售指引下滑；路线 J）。
  TOM〔选股·日历〕：成交日（信号日的下一个交易日）是当月第 6 个交易日到倒数第 6 个交易日之间（月中）→ 不买，只买月末 5 天 + 月初 5 天
       （月初月末效应：Ariel 1987、Lakonishok & Smidt 1988；日本也有记录）；三个年代、路线 A / B。
缺值不挡；都不是事后组合。第二关另行登记。运行：python scripts/loop12_r05_mix.py；--wiring。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402
import loop12_r01_fund as R1                                                 # noqa: E402
import loop12_r04_price as R4                                                # noqa: E402
import research_loop12 as R12                                                # noqa: E402

ROUND = 5
IDS = ("PEH", "FGR", "TOM")
FAMILY = {"PEH": "选股·估值", "FGR": "选股·成长", "TOM": "选股·日历"}
ROUTE = {"PEH": "J", "FGR": "J", "TOM": "AB"}
OUT = "loop12_r05_mix"
PER_Q, TOM_N = 80, 5


def derive5(F: pd.DataFrame) -> pd.DataFrame:
    F = F.copy()
    F["fy"] = F["fye"].str[:4]
    fy_sales = {(r["ticker"], r["fy"]): r["Sales"] for r in F[F["per"] == "FY"].to_dict("records") if np.isfinite(r["Sales"])}
    rows = []
    for r in F.to_dict("records"):
        eps = r["EPS"] if r["per"] == "FY" and np.isfinite(r["EPS"]) and r["EPS"] > 0 else np.nan
        prev = fy_sales.get((r["ticker"], str(int(r["fy"]) - 1))) if r["fy"].isdigit() else None
        fgr = (r["FSales"] / prev - 1) * 100 if prev and prev > 0 and np.isfinite(r["FSales"]) and r["FSales"] > 0 else np.nan
        rows.append({"ticker": r["ticker"], "date": r["date"], "eps": eps, "fgr": fgr})
    return pd.DataFrame(rows)


def jfeat(F, fa, tickers, dates) -> pd.DataFrame:
    eps = LC.asof(F, "eps", tickers, dates)
    px = LC.close_at(fa, tickers, dates)
    return pd.DataFrame({"per": np.where(eps > 0, px / np.where(eps > 0, eps, np.nan), np.nan), "fgr": LC.asof(F, "fgr", tickers, dates)})


def tom_block(dates, days: pd.DatetimeIndex) -> np.ndarray:
    """成交日 = 信号日的下一个交易日；在当月交易日里的位置 → 月中（第 TOM_N+1 个到倒数第 TOM_N+1 个）→ True。"""
    days = pd.DatetimeIndex(sorted(set(days)))
    pos = pd.Series(np.arange(len(days)), index=days)
    per = days.to_period("M")
    first = pd.Series(days, index=days).groupby(per).transform("min")
    last = pd.Series(days, index=days).groupby(per).transform("max")
    k_in = pd.Series(np.arange(len(days)), index=days).groupby(per).cumcount()
    n_in = pd.Series(1, index=days).groupby(per).transform("sum")
    out = []
    for d in pd.to_datetime(np.asarray(dates)):
        i = days.searchsorted(d, side="right")
        if i >= len(days):
            out.append(False)
            continue
        f = days[i]
        k, n = int(k_in[f]), int(n_in[f])
        out.append(TOM_N <= k < n - TOM_N)
    return np.array(out, bool)


def build(W: dict) -> dict:
    F = derive5(LC.fins_rows())
    S = LC.signals(W, "J")
    XJ = jfeat(F, W["SM"]["J"]["fa"], S["ticker"], S["date"])
    cut = float(np.nanpercentile(XJ["per"], PER_Q))
    X = LC.pool_x(W, "Jx")
    XP = jfeat(F, W["SM"]["J2"]["fa"], X["ticker"], X["date"])
    gJ = {"PEH": (XJ["per"] >= cut).fillna(False).to_numpy(bool), "FGR": (XJ["fgr"] < 0).fillna(False).to_numpy(bool)}
    gP = {"PEH": (XP["per"] >= cut).fillna(False).to_numpy(bool), "FGR": (XP["fgr"] < 0).fillna(False).to_numpy(bool)}
    gT = {e: tom_block(LC.signals(W, e)["date"], W["ctx"][e]["days"]) for e in LC.ERAS}
    days_of = {"W": W["ctx"]["E"]["days"], "Jx": W["ctx"]["J"]["days"], "Zx": W["ctx"]["Z"]["days"]}
    gTP = {s: tom_block(LC.pool_x(W, s)["date"], days_of[s]) for s in ("W", "Jx", "Zx") if s in W["D"]}
    cov = {"per": int(XJ["per"].notna().sum()), "fgr": int(XJ["fgr"].notna().sum()), "signals": int(len(S))}
    return {"cut": cut, "gJ": gJ, "gP": gP, "gT": gT, "gTP": gTP, "coverage": cov}


def wiring() -> int:
    W = LC.load()
    B = build(W)
    same = all(LC.run_b4(W, e, np.zeros(len(LC.signals(W, e)), bool)) == LC.run_b4(W, e) for e in LC.ERAS)
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    print(json.dumps({"same_as_b4": bool(same), "per_cut": round(B["cut"], 2), "coverage": B["coverage"],
                      "blocked_extra": {"PEH": int((B["gJ"]["PEH"] & ~tbf["J"]).sum()), "FGR": int((B["gJ"]["FGR"] & ~tbf["J"]).sum()),
                                        "TOM": {e: int((B["gT"][e] & ~tbf[e]).sum()) for e in LC.ERAS}},
                      "pool_blocked": {"PEH": int(B["gP"]["PEH"].sum()), "FGR": int(B["gP"]["FGR"].sum()), "TOM": {s: int(v.sum()) for s, v in B["gTP"].items()}},
                      "signals": {e: int(len(LC.signals(W, e))) for e in LC.ERAS}}, ensure_ascii=False))
    return 0 if same else 1


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = R1.git_head()
    W = LC.load()
    B = build(W)
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    res = {"loop": 12, "round": ROUND, "ids": list(IDS), "family": FAMILY, "route": ROUTE, "code": code, "dirty": dirty, "per_cut": B["cut"],
           "coverage": B["coverage"], "base": base, "cand": {}, "stage1": {}, "other": {}, "frac": {}}
    for k in ("PEH", "FGR"):
        cand = dict(base)
        cand["J"] = LC.run_b4(W, "J", B["gJ"][k])
        other = LC.other_stocks(W, lambda s, X, _g=B["gP"][k]: _g if s == "Jx" else np.zeros(len(X), bool))
        res["cand"][k], res["other"][k] = cand, other
        res["frac"][k] = {"J": float((B["gJ"][k] & ~tbf["J"]).mean())}
        res["stage1"][k] = R12.stage1_j(cand["J"], base["J"], other.get("Jx"))
        print(f"{k} 完成（{time.time() - t0:.0f}s）", flush=True)
    cand = {e: LC.run_b4(W, e, B["gT"][e]) for e in LC.ERAS}
    other = LC.other_stocks(W, lambda s, X: B["gTP"].get(s, np.zeros(len(X), bool)))
    res["cand"]["TOM"], res["other"]["TOM"] = cand, other
    res["frac"]["TOM"] = {e: float((B["gT"][e] & ~tbf[e]).mean()) for e in LC.ERAS}
    res["stage1"]["TOM"] = R12.stage1_all(cand, base, other)
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    f = R1._f
    L = [f"# 第十二个研究循环第 5 轮：PER / 销售指引 / 月初月末 PEH / FGR / TOM（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}）", "",
         f"PER 门槛（J 信号 80 分位）{res['per_cut']:.1f} 倍；覆盖（J 信号 {res['coverage']['signals']}）：PER {res['coverage']['per']}、销售指引 {res['coverage']['fgr']}", ""]
    for k in ("PEH", "FGR"):
        s, o = res["stage1"][k], res["other"][k].get("Jx") or {}
        d = s["d"]
        L.append(f"- **{k}**（{FAMILY[k]}，路线 J）：J Calmar 差 {f(d['calmar'], '{:+.3f}')}、胜率差 {f(d['win'], '{:+.2f}')} pp、每笔差 {f(d['mean'], '{:+.3f}')} pp、"
                 f"两半 {f(d['h1'], '{:+.3f}')} / {f(d['h2'], '{:+.3f}')}；Jx 挡 {o.get('gone_n')} / {o.get('n')}、保留的胜率差 {f(o.get('dwin'), '{:+.2f}')} pp、"
                 f"每笔差 {f(o.get('dmean'), '{:+.3f}')} pp；JA {'✓' if s['routes']['JA']['ok'] else '✗'}、JB {'✓' if s['routes']['JB']['ok'] else '✗'} → "
                 f"**{'第一关全过' if s['ok'] else R12.FAIL1}**")
    s = res["stage1"]["TOM"]
    A, Bq, o = s["routes"]["A"], s["routes"]["B"], res["other"]["TOM"]
    L.append(f"- **TOM**（选股·日历，路线 A / B）：每个年代 " + "、".join(
        f"{e} Calmar {f(res['base'][e]['calmar'])} → {f(res['cand']['TOM'][e]['calmar'])}、胜率 {f(res['base'][e]['win'], '{:.1f}')} → {f(res['cand']['TOM'][e]['win'], '{:.1f}')}%"
        for e in LC.ERAS) + f"；路线 A（合计 {f(A['sum'], '{:+.3f}')}）" + "、".join(f"{x} {'✓' if A[x] else '✗'}" for x in ("A1", "A2", "A3", "V4"))
        + f"；路线 B（胜率差 {f(Bq['dwin'], '{:+.2f}')} pp、每笔 {f(Bq['dmean'], '{:+.3f}')} pp）" + "、".join(f"{x} {'✓' if Bq[x] else '✗'}" for x in ("B1", "B2", "B3", "V4"))
        + "；" + "；".join(f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}、{f(o[x]['dwin'], '{:+.2f}')} pp、{f(o[x]['dmean'], '{:+.3f}')} pp" for x in ("W", "Jx", "Zx") if x in o)
        + f" → **{'第一关全过' if s['ok'] else R12.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
