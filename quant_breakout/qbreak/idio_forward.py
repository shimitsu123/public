"""idio_forward.py — 「个别驱动的突破」的前向记录（2026-09-27 登记；用户「F 前向记录」；规则见 scripts/score_forward.py 第九节）。

两个只记录、不交易的标记，跟着 W2 的两份前向记录（每日记录 + 全市场版）一起记、一起复核：
  K2  = 突破日量比 ≥ 2.0 ∧ 对日経225 的 β ≤ 0.70（scripts/leap2_s6_study.py 登记检验里三个年代每笔都更好、组合都不差的那一个）
        突破日量比 = 信号日成交量 ÷ 之前 20 日均量（不含当天，≥ 15 天有值；scripts/leap_r11_explore.vr1 同一定义）；
        β = 信号日所在周之前那个周五为止、最近 104 周的周收益（周五收盘，截断 ±50%）对日経225 周收益的回归斜率
        （有值 ≥ 69 周才算；不足 104 周（新上市、或记录时行情只有 2 年 ≈ 100 周）就用有的；scripts/leap2_s5_explore.rolling_betas 同一算法）；
        量比或 β 缺值 → 0（= 登记检验里「不买」）。
  USW = 所在東証 33 业种的美国对应行业（Ken French 49 行业，对应表 S33_FF49 在 scripts/leap2_s4_explore.py 看结果之前写定）
        过去 12 个月相对 49 行业平均的累计收益百分位 ≤ 1/3；月数据只用到信号日那个月之前第 2 个月（Ken French 按月更新、有延迟）；
        取不到 → 空（复核时可以按同样的规则补算，但不写回记录）。scripts/leap2_s4b_explore.py：只在 2017〜2026 成立（W2 ∧ USW 25 笔 68% / +3.54%）。
门槛（2.0 / 0.70 / 1/3）在这里写定，不跟着参数变。判定与 W2 相同的年度日期（qbreak/w2_forward.py JUDGE_DATES），共用其自助法与判定函数。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import w2_forward as W2F

K2_VR, K2_BETA = 2.0, 0.70
USW_Q = 1 / 3
BETA_WEEKS, BETA_MIN_WEEKS = 104, 69
US_LAG_MONTHS = 2
COLS = ("vr1", "b_n225", "k2_keep", "us12", "usw_keep")
JUDGE_DATES = W2F.JUDGE_DATES
S33_FF49 = {"水産・農林業": "Agric", "鉱業": "Oil", "建設業": "Cnstr", "食料品": "Food", "繊維製品": "Txtls", "パルプ・紙": "Paper",
            "化学": "Chems", "医薬品": "Drugs", "石油・石炭製品": "Oil", "ゴム製品": "Rubbr", "ガラス・土石製品": "BldMt", "鉄鋼": "Steel",
            "非鉄金属": "Steel", "金属製品": "FabPr", "機械": "Mach", "電気機器": "Chips", "輸送用機器": "Autos", "精密機器": "LabEq",
            "その他製品": "Toys", "電気・ガス業": "Util", "陸運業": "Trans", "海運業": "Trans", "空運業": "Trans", "倉庫・運輸関連業": "Trans",
            "情報・通信業": "Telcm", "卸売業": "Whlsl", "小売業": "Rtail", "銀行業": "Banks", "証券、商品先物取引業": "Fin", "保険業": "Insur",
            "その他金融業": "Fin", "不動産業": "RlEst", "サービス業": "BusSv"}


# ── 单个信号的输入 ──
def vr1_series(df: pd.DataFrame) -> pd.Series:
    """突破日量比：当天成交量 ÷ 之前 20 天平均（不含当天）。"""
    v = df["Volume"].astype(float)
    return v / v.shift(1).rolling(20, min_periods=15).mean()


def weekly_returns(close: pd.Series) -> pd.Series:
    """日收盘 → 周五为止的周收盘 → 周收益（截断 ±50%）。"""
    return close.dropna().resample("W-FRI").last().pct_change().clip(-0.5, 0.5)


def beta_asof(y_w: pd.Series, m_w: pd.Series, asof) -> float:
    """信号日所在周之前那个周五为止、最近 BETA_WEEKS 周的 y ~ m 回归斜率（有值 ≥ BETA_MIN_WEEKS 周）；不够 → NaN。"""
    cutoff = pd.Timestamp(asof).to_period("W-FRI").start_time - pd.Timedelta(days=1)
    y = y_w[y_w.index <= cutoff].iloc[-BETA_WEEKS:]
    if not len(y):
        return float("nan")
    x = m_w.reindex(y.index)
    ok = y.notna() & x.notna()
    if int(ok.sum()) < BETA_MIN_WEEKS:
        return float("nan")
    A = np.column_stack([np.ones(int(ok.sum())), x[ok].to_numpy(float)])
    coef, *_ = np.linalg.lstsq(A, y[ok].to_numpy(float), rcond=None)
    return float(coef[1])


def us_rank_asof(R_pct: pd.DataFrame, lag_months: int = US_LAG_MONTHS) -> pd.DataFrame:
    """Ken French 月收益（%，索引 = 月初）→ 每个月 m：到 m − lag_months 为止 12 个月的相对累计对数收益在 49 行业里的百分位（0〜1）。
    索引比数据多延 lag_months 个月（数据到 8 月 → 9 月、10 月的信号用到 7 月、8 月为止的数据）。"""
    L = np.log1p(R_pct / 100.0)
    rel = L.sub(L.mean(axis=1), axis=0)
    pct = rel.rolling(12, min_periods=12).sum().rank(axis=1, pct=True)
    if len(pct) and lag_months > 0:
        last = pd.Timestamp(pct.index[-1])
        pct = pct.reindex(pct.index.append(pd.DatetimeIndex([last + pd.DateOffset(months=k) for k in range(1, lag_months + 1)])))
    return pct.shift(lag_months)


def us12_at(us_pct: pd.DataFrame | None, s33_name: str | None, date) -> float:
    ff = S33_FF49.get(s33_name or "")
    if us_pct is None or ff is None or ff not in us_pct.columns:
        return float("nan")
    m = pd.Timestamp(date).to_period("M").to_timestamp()
    v = us_pct.at[m, ff] if m in us_pct.index else float("nan")
    return float(v) if v is not None and np.isfinite(v) else float("nan")


def k2_flag(vr1, beta) -> np.ndarray:
    """量比 ≥ 2.0 ∧ β ≤ 0.70 → 1；否则（含缺值）→ 0。"""
    v, b = np.asarray(vr1, float), np.asarray(beta, float)
    return (np.isfinite(v) & np.isfinite(b) & (v >= K2_VR) & (b <= K2_BETA)).astype(int)


def usw_flag(us12) -> np.ndarray:
    """美国对应行业百分位 ≤ 1/3 → 1；> 1/3 → 0；缺值 → NaN。"""
    u = np.asarray(us12, float)
    return np.where(np.isfinite(u), (u <= USW_Q).astype(float), np.nan)


def fields(ind: dict[str, pd.DataFrame], dates, tickers, mkt_close: pd.Series | None, us_pct: pd.DataFrame | None,
           s33: dict[str, str] | None) -> dict[str, list]:
    """每个信号（日期、票）→ 5 个记录列（列名 COLS）。ind[t] = 这只票的日线（含 Volume、Close）；mkt_close = 日経225 日收盘。"""
    m_w = weekly_returns(mkt_close) if mkt_close is not None else None
    cache: dict[str, tuple[pd.Series, pd.Series | None]] = {}
    vr, bt, us = [], [], []
    for d, t in zip(dates, tickers):
        if t not in cache:
            df = ind[t]
            cache[t] = (vr1_series(df), weekly_returns(df["Close"]) if m_w is not None else None)
        v_s, y_w = cache[t]
        v = v_s.get(pd.Timestamp(d), np.nan)
        vr.append(round(float(v), 4) if v is not None and np.isfinite(v) else np.nan)
        b = beta_asof(y_w, m_w, d) if y_w is not None else float("nan")
        bt.append(round(b, 4) if np.isfinite(b) else np.nan)
        u = us12_at(us_pct, (s33 or {}).get(t), d)
        us.append(round(u, 4) if np.isfinite(u) else np.nan)
    return {"vr1": vr, "b_n225": bt, "k2_keep": k2_flag(vr, bt).tolist(), "us12": us, "usw_keep": usw_flag(us).tolist()}


# ── 复核 ──
def evaluate_k2(C: pd.DataFrame, date_col: str = "date", n: int = W2F.BOOT_N) -> dict:
    """全部（不加 W2 的）突破里 K2 = 1 vs 0：笔数 / 胜率 / 每笔、差与区间（qbreak/w2_forward.py 同一自助法）。"""
    return W2F.evaluate(C, keep_col="k2_keep", date_col=date_col, n=n)


def evaluate_usw(C: pd.DataFrame, date_col: str = "date", n: int = W2F.BOOT_N) -> dict:
    """W2 保留的突破里 USW = 1 vs 0（us12 缺值的不算）。"""
    if not len(C) or "w2_keep" not in C.columns or "usw_keep" not in C.columns:
        return W2F.evaluate(C.iloc[0:0] if len(C) else pd.DataFrame(columns=["usw_keep", "net", date_col]), keep_col="usw_keep",
                            date_col=date_col, n=n)
    k = pd.to_numeric(C["w2_keep"], errors="coerce").to_numpy(float)
    return W2F.evaluate(C[k == 1], keep_col="usw_keep", date_col=date_col, n=n)


def review_pair(C: pd.DataFrame, hist: pd.DataFrame | None, today, scope_prefix: str = "", date_col: str = "date",
                seg_col: str | None = "segment") -> dict:
    """K2 与 USW 各自：评估 + 每年一次的判定（证实 = 保留 − 其余 的 99% 区间下限 > 0；反向 = 其余 − 保留 的 95% 区间下限 > 0）；
    做过的年份（历史的 scope = prefix + K2 / USW，列 idio_year）不再做。另报分段。"""
    out = {}
    for key, ev in (("K2", evaluate_k2(C, date_col)), ("USW", evaluate_usw(C, date_col))):
        year = W2F.due_date(today, JUDGE_DATES, W2F.history_done(hist, f"{scope_prefix}{key}", "idio_year"))
        seg = {}
        col = "k2_keep" if key == "K2" else "usw_keep"
        if len(C) and col in C.columns and seg_col and seg_col in C.columns:
            base = C if key == "K2" else C[pd.to_numeric(C["w2_keep"], errors="coerce").to_numpy(float) == 1]
            kv = pd.to_numeric(base[col], errors="coerce").to_numpy(float)
            for g in ("N225", "T500x", "S1x"):
                m = (base[seg_col] == g).to_numpy()
                seg[g] = {"keep": W2F.stat(base.loc[m & (kv == 1), "net"]), "drop": W2F.stat(base.loc[m & (kv == 0), "net"])}
        out[key] = {"eval": ev, "year": year, "alarm": W2F.alarm(ev) if year else None, "confirmed": W2F.confirmed(ev) if year else None,
                    "segments": seg}
    return out


def history_rows(rev: dict, run: str, scope_prefix: str, extra: dict | None = None) -> list[dict]:
    rows = []
    for key, r in rev.items():
        e = r["eval"]
        rows.append({"run": run, "scope": f"{scope_prefix}{key}", "closed": e["n"], "idio_year": r["year"], "idio_diff": e.get("diff"),
                     "idio_lo95": e.get("lo95"), "idio_hi95": e.get("hi95"), "idio_lo99": e.get("lo99"), "idio_hi99": e.get("hi99"),
                     "idio_alarm": r["alarm"], "idio_confirmed": r["confirmed"], **(extra or {})})
    return rows


def say_lines(rev: dict, next_dates=JUDGE_DATES, today=None) -> list[str]:
    """复核报告里的几行（两份复核共用）。"""
    lab = {"K2": "K2 放量 ∧ 低 β（全部突破里 K2 vs 其余）", "USW": "USW 美国对应行业弱（W2 保留里 USW vs 其余）"}
    out = []
    for key, r in rev.items():
        ev = r["eval"]
        out.append(f"- {lab[key]}：" + (W2F.summary_line(ev) if ev["n"] else "还没有已平仓、带标记的信号"))
        lines = W2F.verdict_lines(ev, f"{r['year']} 这一年" if r["year"] else None, f"{r['year']} 这一年" if r["year"] else None)
        for x in lines:
            out.append(f"  - {x}")
        if not lines:
            t = pd.Timestamp(today) if today is not None else pd.Timestamp.today()
            nxt = next((d for d in next_dates if pd.Timestamp(d) > t), None)
            out.append(f"  - 只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "  - 五次年度判定都已做完（只报告）")
        if r.get("segments"):
            f = lambda s: f"{s['n']} 笔 {s['mean']:+.2f}%" if s.get("n") else "0 笔"                                  # noqa: E731
            out.append("  - 分段（只描述）：" + "；".join(f"{g} 标记 {f(v['keep'])} / 其余 {f(v['drop'])}" for g, v in r["segments"].items()))
    return out
