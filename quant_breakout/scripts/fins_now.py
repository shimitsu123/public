"""fins_now.py — 全部上市个股「最新决算 + 会社予想修正」一览（J-Quants Standard 決算短信サマリー；只展示 / 研究，不影响交易）。

用户（2026-09-27）：「取得现在所有个股的决算、业绩修正」。
数据：var/cache/jquants/bulk/fins/summary（qbreak/jq_data.py DATASETS["fins"]，先用 bulk_download 刷新）+ 最新的月末上市一览（业种、规模）。
每家公司（qbreak/jq_data.fins_events 同一算法：利润档 = 营业利润 → 经常利润 → 净利润）：
  最近一次决算开示（日期、期间 1Q/2Q/3Q/FY、累计利润对上年同期 %）；最近一次「真的改了予想」的开示（日期、修正 %、方向）；当期予想值。
输出：var/cache/jquants/out/fins_now.csv（全表；J-Quants 原始数据派生，不入库）+ 终端摘要（最近 N 天上修 / 下修的分布与前列）。
用法：python scripts/fins_now.py [--days 30] [--top 15] [--no-refresh]；Mac：bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python scripts/fins_now.py
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import jq_data as JD                                             # noqa: E402
from qbreak import jquants as JQ                                             # noqa: E402


def latest_master() -> pd.DataFrame:
    """缓存里最新的月末上市一览（qbreak/pit_data.master_files）。"""
    from qbreak import pit_data as PD
    files = PD.master_files()
    if not files:
        return pd.DataFrame(columns=["Code"])
    return pd.read_csv(files[max(files)], dtype=str)


def build(F: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """決算短信全表 + 上市一览 → 每家公司一行。"""
    name_col = JQ.pick(master, "CoName", "CompanyName", "Name", "CoNameEn")
    s33_col = JQ.pick(master, "S33Nm", "Sector33CodeName")
    scale_col = JQ.pick(master, "ScaleCat", "ScaleCategory")
    info = {}
    if len(master):
        for r in master.itertuples(index=False):
            d = r._asdict()
            info[str(d["Code"])] = {"name": d.get(name_col, "") if name_col else "", "s33": d.get(s33_col, "") if s33_col else "",
                                    "scale": d.get(scale_col, "") if scale_col else ""}
    rows = []
    for code, g in F.groupby("Code"):
        ev = JD.fins_events(g)
        if ev.empty:
            continue
        ev = ev.sort_values("date", kind="mergesort")
        last = ev.iloc[-1]
        rv = ev[np.isfinite(ev["rev"]) & (ev["rev"] != 0)]
        yy = ev[np.isfinite(ev["yoy"])]
        gg = g.sort_values(["DiscDate", "DiscTime"] if "DiscTime" in g.columns else ["DiscDate"], kind="mergesort")
        lastdoc = gg.iloc[-1]
        i = info.get(str(code), {})
        rows.append({"code": str(code), "ticker": (str(code)[:4] + ".T") if len(str(code)) == 5 else str(code), "name": i.get("name", ""),
                     "s33": i.get("s33", ""), "scale": i.get("scale", ""),
                     "last_disc": str(pd.Timestamp(last["date"]).date()), "last_period": str(lastdoc.get("CurPerType") or ""),
                     "fy_end": str(last["fy"] or ""), "forecast": last["fc"],
                     "yoy_pct": float(yy.iloc[-1]["yoy"]) if len(yy) else np.nan, "yoy_date": str(pd.Timestamp(yy.iloc[-1]["date"]).date()) if len(yy) else "",
                     "rev_pct": float(rv.iloc[-1]["rev"]) if len(rv) else np.nan, "rev_date": str(pd.Timestamp(rv.iloc[-1]["date"]).date()) if len(rv) else "",
                     "n_disc": int(len(ev))})
    out = pd.DataFrame(rows)
    return out.sort_values("code").reset_index(drop=True) if len(out) else out


def digest(T: pd.DataFrame, days: int, top: int, asof: pd.Timestamp) -> str:
    L = []
    since = asof - pd.Timedelta(days=days)
    rd = pd.to_datetime(T["rev_date"], errors="coerce")
    R = T[(rd >= since) & np.isfinite(T["rev_pct"])].copy()
    R["rev_date_ts"] = rd[R.index]
    up, dn = R[R["rev_pct"] > 0], R[R["rev_pct"] < 0]
    L.append(f"公司 {len(T)} 家；最近一次开示在 {days} 天内的 {int((pd.to_datetime(T['last_disc']) >= since).sum())} 家；"
             f"{days} 天内改了予想的 {len(R)} 家：上修 {len(up)}、下修 {len(dn)}（数据到 {T['last_disc'].max()}）")
    by = R.groupby("s33")["rev_pct"].agg(["count", "median"]).sort_values("count", ascending=False)
    if len(by):
        L.append("按业种（家数 / 修正率中位数 %）：" + "；".join(f"{s} {int(c)} / {m:+.1f}" for s, (c, m) in by.head(10).iterrows()))
    for lab, D in (("上修前列", up.sort_values("rev_pct", ascending=False)), ("下修前列", dn.sort_values("rev_pct"))):
        L.append(f"\n{lab}（{days} 天内；修正 % / 日期 / 业种 / 规模）：")
        for r in D.head(top).itertuples():
            L.append(f"  {r.ticker} {r.name} {r.rev_pct:+.1f}% {r.rev_date} {r.s33} {r.scale}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--no-refresh", action="store_true", help="不刷新批量文件（用缓存）")
    a = ap.parse_args(argv)
    t0 = time.time()
    path, cols = JD.DATASETS["fins"]
    if a.no_refresh:
        d = JD.bulk_dir() / path.strip("/")
        files = sorted(d.glob("historical/*/*.csv.gz")) + sorted(d.glob("historical/*.csv.gz")) + sorted(d.glob("live/*.csv.gz"))
    else:
        files = JD.bulk_download(JQ.JQuants(), path, log=lambda s: print(s, file=sys.stderr, flush=True))
    F = JD.read_bulk(files, cols)
    print(f"決算短信 {len(F)} 行、{F['Code'].nunique()} 家；{time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    T = build(F, latest_master())
    out = JQ.cache_dir() / "out"
    out.mkdir(parents=True, exist_ok=True)
    fp = out / "fins_now.csv"
    T.to_csv(fp, index=False)
    print(digest(T, a.days, a.top, pd.Timestamp(pd.to_datetime(T["last_disc"]).max())))
    print(f"\n全表 {fp}（{len(T)} 行；J-Quants 派生数据，不入库）；用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
