"""loop12_common.py — 第十二个研究循环（规则 scripts/research_loop12.py）的共用部分：基准 B4（B3 + TBF）、候选（再多挡一些信号）的跑法、
池子（W / Jx / Zx）、第二关的随机挡、J-Quants 特征（2016-10 起）按「可用日」对到每个信号。非投资建议。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop9_common as C9                                                    # noqa: E402
import loop10_common as C10                                                  # noqa: E402
import research_loop12 as R12                                                # noqa: E402

ERAS = C9.ERAS
acct, signals = C9.acct, C9.signals
L6 = C9.L6
POOLS = (("W", "E", "W"), ("Jx", "J", "J2"), ("Zx", "Z", "Zx"))


def load() -> dict:
    """第十个循环的全部输入（含 Zx）+ TBF 旗子（N225 每个年代的信号、池子信号）。"""
    import trendline_study as TS
    W = C10.load(with_zx=True)
    tbf, tbf_pool = TS.tbf_gates(W, say=lambda *a: None)
    W["tbf"], W["tbf_pool"] = tbf, tbf_pool
    return W


def run_b4(W: dict, e: str, extra=None) -> dict:
    """B4 = B3 + TBF；extra（与 signals(W, e) 同序的 bool）= 再多挡的。"""
    g = np.asarray(W["tbf"][e], bool)
    if extra is not None:
        g = g | np.asarray(extra, bool)
    return acct(C9.run_block(W, e, g))


def pool_x(W: dict, s: str) -> pd.DataFrame:
    """池子 s 里 B4 会买的信号（B3 会买的去掉 TBF 挡的）。"""
    X = C10.kept_pool(W, s, dict((p, f) for p, f, _ in POOLS)[s])
    t = np.asarray(W["tbf_pool"].get(s, np.zeros(len(X), bool)), bool) if s in W["tbf_pool"] else np.zeros(len(X), bool)
    return X[~t].reset_index(drop=True)


def other_stocks(W: dict, gate_fn) -> dict:
    """gate_fn(池子名, X) → 要挡的（bool，与 X 同序）→ 保留的 vs 全部（假想单笔）。"""
    import combo_all_common as CA
    out = {}
    for s, _, _ in POOLS:
        if s not in W["D"]:
            continue
        X = pool_x(W, s)
        g = np.asarray(gate_fn(s, X), bool)
        net = X["net"].to_numpy(float)
        dl = CA.delta(net, ~g)
        gone = net[g]
        out[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                  "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


def scale(W: dict, gates: dict) -> dict:
    """规模（只数个数）：每个做法每个年代挡掉的信号数（不算 TBF 已经挡的）。"""
    out = {}
    for k, g in gates.items():
        out[k] = {e: int((np.asarray(g[e], bool) & ~np.asarray(W["tbf"][e], bool)).sum()) for e in ERAS}
    return out


def placebo(W: dict, frac: dict, routes: list[str], base: dict, n: int, log=print) -> list[dict]:
    """第二关：每个年代按候选「多挡」的比例随机挡（在 TBF 之外的信号里）→ {A: Calmar 差合计, B: 合起来胜率差, JA: J Calmar 差, JB: J 胜率差}。"""
    import research_loop10 as R10
    out, t0 = [], time.time()
    eras = ERAS if any(r in ("A", "B") for r in routes) else ("J",)
    for s in range(n):
        cand = {}
        for e in eras:
            S = signals(W, e)
            g = R12.random_block(len(S), frac[e], s) & ~np.asarray(W["tbf"][e], bool)
            cand[e] = run_b4(W, e, g)
        row = {}
        if "A" in routes or "B" in routes:
            d = [None if cand[e]["calmar"] is None or base[e]["calmar"] is None else cand[e]["calmar"] - base[e]["calmar"] for e in ERAS]
            row["A"] = None if any(x is None for x in d) else float(sum(d))
            c, b = R10.pooled_trades(cand), R10.pooled_trades(base)
            row["B"] = None if c["win"] is None or b["win"] is None else float(c["win"] - b["win"])
        if "JA" in routes or "JB" in routes:
            cj, bj = cand["J"], base["J"]
            row["JA"] = None if cj["calmar"] is None or bj["calmar"] is None else cj["calmar"] - bj["calmar"]
            row["JB"] = None if cj["win"] is None or bj["win"] is None else cj["win"] - bj["win"]
        out.append(row)
        if (s + 1) % 50 == 0:
            log(f"随机挡 {s + 1} / {n}（{time.time() - t0:.0f}s）")
    return out


# ───────────────────────── J-Quants 特征（2016-10 起；按可用日 = 开示日之后第一个交易日对到信号日） ─────────────────────────
FINS_COLS = ["DiscDate", "DiscTime", "Code", "DocType", "CurPerType", "CurFYEn", "NxtFYEn", "OP", "OdP", "NP", "FOP", "FOdP", "FNP",
             "NxFOP", "NxFOdP", "NxFNp", "BPS", "ROE", "CFO", "CFI", "EqAR", "Sales"]


def fins_rows() -> pd.DataFrame:
    """決算短信（不含予想修正文档、REIT）→ 长表：ticker, date, avail, per, doc + 数值列。"""
    import jq_extra_data as JX
    from qbreak import jq_data as JD
    F = JD.read_bulk(JX.bulk_files("fins/summary"), FINS_COLS)
    doc = F["DocType"].fillna("").astype(str)
    F = F[doc.str.contains("FinancialStatements") & ~doc.str.contains("REIT")].copy()
    out = pd.DataFrame({"ticker": JX._tickers(F["Code"]), "date": pd.to_datetime(F["DiscDate"]),
                        "time": F.get("DiscTime", pd.Series("", index=F.index)).fillna("").astype(str),
                        "per": F["CurPerType"].fillna("").astype(str), "doc": F["DocType"].astype(str)})
    for c in FINS_COLS[7:]:
        out[c] = pd.to_numeric(F[c], errors="coerce") if c in F.columns else np.nan
    return out.dropna(subset=["ticker"]).sort_values(["ticker", "date", "time"], kind="mergesort").reset_index(drop=True)


def _profit(r) -> tuple[float, float, float]:
    """这家公司用哪一档利润（有营业利润用营业利润；银行 / 保险 → 经常利润 → 净利润）：(累计实绩, 当期予想, 下期予想)。"""
    for a, f, nx in (("OP", "FOP", "NxFOP"), ("OdP", "FOdP", "NxFOdP"), ("NP", "FNP", "NxFNp")):
        if np.isfinite(r[a]) or np.isfinite(r[f]):
            return r[a], r[f], r[nx]
    return np.nan, np.nan, np.nan


BENCH = {"1Q": 25.0, "2Q": 50.0, "3Q": 75.0}                                  # 进度率的季节基准（%）


def derive(F: pd.DataFrame) -> pd.DataFrame:
    """每条决算短信 → 派生：pbr 用的 BPS、roe、fcf（FY 与 2Q 才有现金流）、nxg（FY：下期予想 ÷ 本期实绩 − 1，%）、
    prg（1Q〜3Q：累计实绩 ÷ 当期予想 × 100 − 季节基准，pp）。"""
    rows = []
    for r in F.to_dict("records"):
        a, f, nx = _profit(r)
        nxg = (nx / abs(a) - 1) * 100 if r["per"] == "FY" and np.isfinite(nx) and np.isfinite(a) and a != 0 else np.nan
        prg = (a / f * 100 - BENCH[r["per"]]) if r["per"] in BENCH and np.isfinite(a) and np.isfinite(f) and f > 0 else np.nan
        fcf = r["CFO"] + r["CFI"] if r["per"] == "FY" and np.isfinite(r["CFO"]) and np.isfinite(r["CFI"]) else np.nan
        rows.append({"ticker": r["ticker"], "date": r["date"], "BPS": r["BPS"], "roe": r["ROE"], "fcf": fcf, "nxg": nxg, "prg": prg})
    return pd.DataFrame(rows)


def asof(ev: pd.DataFrame, col: str, tickers, dates, stale_days: int = 400) -> np.ndarray:
    """每个（票, 信号日）：col 不缺的、开示日 < 信号日的最后一条（开示当天收盘后公布 → 只用于之后的信号日）；太旧（> stale_days）→ NaN。"""
    e = ev.dropna(subset=[col]).sort_values(["ticker", "date"], kind="mergesort")
    by = {t: (g["date"].to_numpy("datetime64[ns]"), g[col].to_numpy(float)) for t, g in e.groupby("ticker")}
    out = np.full(len(tickers), np.nan)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)).to_numpy("datetime64[ns]"))):
        x = by.get(str(t))
        if x is None:
            continue
        k = int(np.searchsorted(x[0], d, side="left")) - 1
        if k >= 0 and (d - x[0][k]) <= np.timedelta64(stale_days, "D"):
            out[i] = x[1][k]
    return out


def close_at(fa: dict, tickers, dates) -> np.ndarray:
    out = np.full(len(tickers), np.nan)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        df = fa.get(str(t))
        if df is not None and d in df.index:
            out[i] = float(df.loc[d, "Close"])
    return out
