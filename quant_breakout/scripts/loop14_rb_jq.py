"""loop14_rb_jq.py — 第十四个研究循环 B 轮：AGR / ISS / PAY（定义见 scripts/research_loop14.py；J-Quants，路线 J）。非投资建议。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402
import loop12_r03_fund3 as R3                                                # noqa: E402
import loop14_common as L14                                                  # noqa: E402

IDS = ("AGR", "ISS", "PAY")
AGR_MIN, ISS_MIN, ISS_MAX, PAY_MIN = 0.20, 0.03, 0.40, 1.0               # J-Quants 的配当性向是比例（0.31 = 31%）→ 100% = 1.0（接线核对后改正单位）
GAP_DAYS, FY_STALE, PAY_STALE = (300, 430), 400, 200
COLS = ["DiscDate", "DiscTime", "Code", "DocType", "CurPerType", "CurFYEn", "TA", "ShOutFY", "TrShFY", "FPayoutRatioAnn", "NxFPayoutRatioAnn"]


def rows() -> pd.DataFrame:
    """決算短信（不含予想修正文档、REIT）→ ticker, date, time, per, fye, ta, sh（期末发行股数 − 自己株式数）, pay（予想配当性向 %）。"""
    import jq_extra_data as JX
    from qbreak import jq_data as JD
    F = JD.read_bulk(JX.bulk_files("fins/summary"), COLS)
    doc = F["DocType"].fillna("").astype(str)
    F = F[doc.str.contains("FinancialStatements") & ~doc.str.contains("REIT")].copy()
    num = {c: pd.to_numeric(F[c], errors="coerce") if c in F.columns else pd.Series(np.nan, index=F.index) for c in COLS[6:]}
    per = F["CurPerType"].fillna("").astype(str)
    out = pd.DataFrame({"ticker": JX._tickers(F["Code"]), "date": pd.to_datetime(F["DiscDate"]),
                        "time": F["DiscTime"].fillna("").astype(str) if "DiscTime" in F.columns else "",
                        "per": per, "fye": F["CurFYEn"].fillna("").astype(str), "ta": num["TA"],
                        "sh": num["ShOutFY"] - num["TrShFY"].fillna(0.0),
                        "pay": np.where(per == "FY", num["NxFPayoutRatioAnn"], num["FPayoutRatioAnn"])})
    return out.dropna(subset=["ticker"]).sort_values(["ticker", "date", "time"], kind="mergesort").reset_index(drop=True)


def fy_growth(R: pd.DataFrame) -> pd.DataFrame:
    """年度短信（同一决算期只用第一次开示）：总资产、净股数 ÷ 上一份年度的 − 1；两份开示日相差 GAP_DAYS 天之内才算。"""
    fy = R[R["per"] == "FY"].drop_duplicates(["ticker", "fye"], keep="first")
    out = []
    for t, g in fy.groupby("ticker", sort=False):
        g = g.sort_values("date", kind="mergesort").to_dict("records")
        for a, b in zip(g[:-1], g[1:]):
            dd = (b["date"] - a["date"]).days
            if not (GAP_DAYS[0] <= dd <= GAP_DAYS[1]):
                continue
            agr = b["ta"] / a["ta"] - 1 if np.isfinite(a["ta"]) and np.isfinite(b["ta"]) and a["ta"] > 0 else np.nan
            iss = b["sh"] / a["sh"] - 1 if np.isfinite(a["sh"]) and np.isfinite(b["sh"]) and a["sh"] > 0 else np.nan
            out.append({"ticker": t, "date": b["date"], "agr": agr, "iss": iss})
    return pd.DataFrame(out, columns=["ticker", "date", "agr", "iss"])


def gates(R: pd.DataFrame, FG: pd.DataFrame, tickers, dates) -> dict:
    agr = np.where(R3._fin(tickers), np.nan, LC.asof(FG, "agr", tickers, dates, stale_days=FY_STALE))
    iss = LC.asof(FG, "iss", tickers, dates, stale_days=FY_STALE)
    pay = LC.asof(R, "pay", tickers, dates, stale_days=PAY_STALE)
    with np.errstate(invalid="ignore"):
        return {"AGR": np.isfinite(agr) & (agr >= AGR_MIN), "ISS": np.isfinite(iss) & (iss >= ISS_MIN) & (iss < ISS_MAX),
                "PAY": np.isfinite(pay) & (pay >= PAY_MIN)}


def build(W: dict) -> dict:
    R = rows()
    FG = fy_growth(R)
    G = {k: {"era": {}, "pool": {}} for k in IDS}
    S = LC.signals(W, "J")
    gj = gates(R, FG, S["ticker"], S["date"])
    X = LC.pool_x(W, "Jx")
    gp = gates(R, FG, X["ticker"], X["date"])
    for k in IDS:
        G[k]["era"]["J"], G[k]["pool"]["Jx"] = gj[k], gp[k]
    return G


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true")
    a = ap.parse_args(argv)
    W = LC.load()
    G = build(W)
    if a.wiring:
        r = L14.wiring(W, G)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r["same_as_b4"] else 1
    G.pop("ISS")                                                             # 接线核对：J 一个都不挡 → 作废（a113821），不运行
    L14.run(W, G, "# 第十四个研究循环 B 轮：资产增长 / 股数增加 / 予想配当性向 AGR / ISS / PAY", "loop14_rb_jq")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
