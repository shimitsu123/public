"""gate_forward.py — 第十个研究循环最接近的三个选股闸门 HWN / X2G / JRM 的前向检验（2026-10-05 登记；用户「把 HWN、X2G、JRM 加进前向检验」）。

登记内容与判定规则：scripts/w2_forward_all.py 第十节（全市场，季度复核 2i 里自动算）。只记录、不交易：模拟盘与执行器照旧（B3）。
三个闸门的定义照第十个循环登记、运行过的代码，一个字不改（tests/test_gate_forward.py 逐个核对与研究的函数相同）：
  HWN：信号日的月份在 5〜10 月 → 挡（scripts/loop10_r07_final.py season_gate）；
  X2G：x2 ≤ 0 → 挡；x2 = 这只票的東証业种的「顾客业种的短観业况变化」（信号日当天或之前已可用的最近一次短観；
       qbreak/score_forward.x2_lookup）；缺值 → 不挡（scripts/loop10_r02_diagfeat.py feature_gate）；
  JRM：日経225 最近 60 个交易日涨幅 − 核心（纳斯达克 100：1545）同期涨幅 ≤ −0.10 → 那天不开新仓
       （scripts/loop10_r01_weakvote.py rel_gap_days；核心按日経的日子取之前最后一个值；不够 60 天 → 不挡；
       信号日没有值 → 之前最后一个，scripts/loop9_r01_market.py on_days）。
统计（每个闸门各自）：样本里的信号按「挡 / 不挡」分两组 → 笔数 / 胜率 / 每笔；胜率差与每笔差 = 不挡 − 挡（pp）；
  区间 = 按信号月聚类的自助法（每次有放回地抽月份，两组都在抽到的月份里算；某一组抽空 → 那一次不算）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import w2_forward as W2F

IDS = ("HWN", "X2G", "JRM")
FORWARD_START = "2026-10-06"                  # 登记日（2026-10-05）的下一个东证交易日起的信号
HWN_MONTHS = (5, 6, 7, 8, 9, 10)
X2G_CUT = 0.0                                 # x2 ≤ 0 → 挡
JRM_N, JRM_GAP = 60, -0.10
CORE_TICKER = "1545.T"
CORE_JUMP = 0.30                              # 核心收盘一天变动超过 ±30% → 当作没调整的分割 / 错价，那一天的变动记为 0
JUDGE_DATES = W2F.JUDGE_DATES                 # 每年一次（与 W2 / K2 / USW / X6 / R4 同一组日期）
BOOT_N, SEED = 2000, 20261005
MIN_N, MIN_MONTHS = 10, 3                     # 挡 / 不挡 任一组 < 10 笔或 < 3 个信号月 → 这一年「样本不够、不判定」（也算做过）
COLS = ("x2", "g_hwn", "g_x2g", "jrm_gap", "g_jrm")
SCOPE = "G10_"                                # 复核历史的 scope 前缀（例 all_G10_HWN）
YEAR_COL = "g10_year"


# ───────────────────────── 三个闸门（定义 = 第十个循环登记的） ─────────────────────────
def hwn_flag(dates, months=HWN_MONTHS) -> np.ndarray:
    """信号日的月份在 months 里 → 1（挡），否则 0。"""
    d = pd.to_datetime(np.asarray(dates))
    return np.isin(np.asarray(d.month), np.asarray(months)).astype(int)


def x2g_flag(x2, cut: float = X2G_CUT) -> np.ndarray:
    """x2 ≤ cut → 1（挡）；x2 > cut 或缺值 → 0（缺值不挡）。"""
    x = np.asarray(x2, float)
    with np.errstate(invalid="ignore"):
        return (np.isfinite(x) & (x <= cut)).astype(int)


def rel_gap(jp: pd.Series, core: pd.Series, n: int = JRM_N) -> pd.Series:
    """日経最近 n 个交易日的涨幅 − 核心同期涨幅（核心按日経的日子取之前最后一个值；不够 n 天 → NaN）。"""
    j = jp.astype(float).dropna()
    j = j[~j.index.duplicated(keep="last")].sort_index()
    c = core.astype(float).dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    ca = c.reindex(c.index.union(j.index)).ffill().reindex(j.index)
    return (j / j.shift(n) - 1) - (ca / ca.shift(n) - 1)


def jrm_days(jp: pd.Series, core: pd.Series, n: int = JRM_N, gap: float = JRM_GAP) -> pd.Series:
    """日経的每个交易日：rel_gap ≤ gap → True（与 scripts/loop10_r01_weakvote.rel_gap_days 相同）。"""
    return (rel_gap(jp, core, n) <= gap).fillna(False)


def asof(series: pd.Series, dates) -> np.ndarray:
    """日期索引的序列 → 对齐到 dates（当天没有值 → 之前最后一个；最开头 → NaN）。"""
    s = series[~series.index.duplicated(keep="last")].sort_index()
    d = pd.DatetimeIndex(pd.to_datetime(np.asarray(dates)))
    return s.reindex(s.index.union(d.unique())).ffill().reindex(d).to_numpy()


def jrm_flag(dates, days: pd.Series) -> np.ndarray:
    """jrm_days 的日序列 → 信号日（之前最后一个值；最开头 → 不挡）。"""
    v = asof(days.astype(float), dates)
    return np.where(np.isfinite(v.astype(float)), v.astype(float), 0.0).astype(int)


def clean_core(close: pd.Series, jump: float = CORE_JUMP) -> pd.Series:
    """核心的收盘 → 收益指数：一天变动超过 ±jump 的当作没调整的分割 / 错价，那一天的变动记为 0，其余照原样连乘
    （yfinance 的 ETF 有时有没调整的分割；纳指在日元里一天从没动过 30%）。只用来算涨幅，水平不重要（从第一天的收盘起算）。"""
    c = close.astype(float).dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    if len(c) < 2:
        return c
    r = c.pct_change()
    r[r.abs() > jump] = 0.0
    return (1 + r.fillna(0.0)).cumprod() * float(c.iloc[0])


def add_flags(F: pd.DataFrame, x2: np.ndarray | None, n225: pd.Series | None, core: pd.Series | None,
              date_col: str = "sig_date") -> pd.DataFrame:
    """信号表 → 加上 x2、三个闸门的标记（1 = 挡）与 jrm_gap。x2 = None（短観取不到）→ x2 / g_x2g 为空；
    日経或核心取不到 → jrm_gap / g_jrm 为空（这个闸门这次算不了，不影响另外两个）。"""
    out = F.copy()
    d = pd.to_datetime(out[date_col]) if len(out) else pd.Series(dtype="datetime64[ns]")
    out["g_hwn"] = hwn_flag(d) if len(out) else pd.Series(dtype=int)
    if x2 is None:
        out["x2"], out["g_x2g"] = np.nan, np.nan
    else:
        out["x2"] = np.asarray(x2, float)
        out["g_x2g"] = x2g_flag(out["x2"])
    if n225 is None or core is None or not len(out):
        out["jrm_gap"], out["g_jrm"] = np.nan, np.nan
    else:
        cc = clean_core(core)
        out["jrm_gap"] = np.round(asof(rel_gap(n225, cc), d).astype(float), 6)
        out["g_jrm"] = jrm_flag(d, jrm_days(n225, cc))
    return out


# ───────────────────────── 统计与判定 ─────────────────────────
def boot_groups(y, g, dates, n: int = BOOT_N, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    """按信号月聚类的自助法：每次有放回地抽月份 → 不挡组 − 挡组 的胜率差（pp）与每笔差（pp）；某一组抽空 → NaN。"""
    y, g = np.asarray(y, float), np.asarray(g, int)
    mon = pd.to_datetime(pd.Series(np.asarray(dates))).dt.to_period("M").to_numpy()
    groups = [np.flatnonzero(mon == m) for m in pd.unique(mon)]
    rng = np.random.default_rng(seed)
    dw, dm = np.full(n, np.nan), np.full(n, np.nan)
    for b in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        yy, gg = y[idx], g[idx]
        k, x = yy[gg == 0], yy[gg == 1]
        if len(k) and len(x):
            dw[b] = ((k > 0).mean() - (x > 0).mean()) * 100
            dm[b] = k.mean() - x.mean()
    return dw, dm


def evaluate(U: pd.DataFrame, flag_col: str, net_col: str = "net_x6", date_col: str = "sig_date",
             n: int = BOOT_N, seed: int = SEED) -> dict:
    """已平仓的信号（flag_col 有值的）→ 不挡 / 挡 两组的统计、胜率差 / 每笔差（不挡 − 挡）与区间、够不够判定。"""
    if not len(U) or flag_col not in U.columns:
        return {"n": 0, "keep": {"n": 0}, "block": {"n": 0}, "enough": False}
    fv = pd.to_numeric(U[flag_col], errors="coerce").to_numpy(float)
    yv = pd.to_numeric(U[net_col], errors="coerce").to_numpy(float)
    ok = np.isfinite(fv) & np.isfinite(yv)
    C = U[ok]
    f, y = fv[ok].astype(int), yv[ok]
    mon = pd.to_datetime(C[date_col]).dt.to_period("M")
    keep, block = W2F.stat(y[f == 0]), W2F.stat(y[f == 1])
    out = {"n": int(len(C)), "keep": keep, "block": block, "months": int(mon.nunique()),
           "keep_months": int(mon[f == 0].nunique()), "block_months": int(mon[f == 1].nunique()),
           "missing": int((~np.isfinite(fv)).sum())}
    out["enough"] = bool(keep["n"] >= MIN_N and block["n"] >= MIN_N and out["keep_months"] >= MIN_MONTHS
                         and out["block_months"] >= MIN_MONTHS)
    if not (keep["n"] and block["n"]):
        return out
    out["dwin"] = round(keep["win"] - block["win"], 2)
    out["dmean"] = round(keep["mean"] - block["mean"], 3)
    dw, dm = boot_groups(y, f, C[date_col], n, seed)
    w_ok, m_ok = dw[np.isfinite(dw)], dm[np.isfinite(dm)]
    if len(w_ok):
        q = lambda a, p_: round(float(np.percentile(a, p_)), 3)                                       # noqa: E731
        out.update({"dwin_lo95": q(w_ok, 2.5), "dwin_hi95": q(w_ok, 97.5), "dwin_lo99": q(w_ok, 0.5), "dwin_hi99": q(w_ok, 99.5),
                    "dmean_lo95": q(m_ok, 2.5), "dmean_hi95": q(m_ok, 97.5)})
    return out


def confirmed(ev: dict) -> bool:
    """证实：样本够、胜率差（不挡 − 挡）的 99% 区间下限 > 0，且每笔差的点估计 ≥ 0（第十个循环 V1：每笔不降）。"""
    return bool(ev.get("enough") and ev.get("dwin_lo99") is not None and ev["dwin_lo99"] > 0 and ev["dmean"] >= 0)


def refuted(ev: dict) -> bool:
    """否定：样本够、胜率差的 95% 区间上限 < 0（挡掉的反而赢得多），或每笔差的 95% 区间上限 < 0（挡掉的反而赚得多）。"""
    return bool(ev.get("enough") and ev.get("dwin_hi95") is not None and (ev["dwin_hi95"] < 0 or ev["dmean_hi95"] < 0))


def verdict(ev: dict) -> str:
    if not ev.get("enough"):
        return "insufficient"
    return "confirmed" if confirmed(ev) else "refuted" if refuted(ev) else "undecided"


def review(U: pd.DataFrame, hist: pd.DataFrame | None, today, prefix: str = "all_", **kw) -> dict:
    """三个闸门各自：统计 + 这次是不是年度判定（复核日第一次到达 JUDGE_DATES 之后；做过的年份不再做）+ 判定结果。"""
    out = {}
    for k in IDS:
        ev = evaluate(U, f"g_{k.lower()}", **kw)
        year = W2F.due_date(today, JUDGE_DATES, W2F.history_done(hist, f"{prefix}{SCOPE}{k}", YEAR_COL))
        out[k] = {"eval": ev, "year": year, "verdict": verdict(ev) if year else None}
    return out


NAMES = {"HWN": "HWN 5〜10 月不开新仓", "X2G": "X2G 顾客业种短観变化 ≤ 0 不买", "JRM": "JRM 日経落后核心 ≥ 10 pp 的日子不开新仓"}
WORDS = {"confirmed": "**证实成立 = 新数据里挡掉的信号胜率确实更低、每笔不更高**（只是记录：要改模拟盘另写一份事先登记的账户研究，并经用户确认）",
         "refuted": "**否定成立 = 新数据里挡掉的反而更好** → 这个闸门结束跟踪（记录照留）",
         "undecided": "证实 / 否定都不成立（未定）",
         "insufficient": "样本不够（挡 / 不挡 任一组 < 10 笔或 < 3 个信号月）→ 这一年不判定（算做过）"}


def summary_line(ev: dict) -> str:
    k, b = ev.get("keep") or {"n": 0}, ev.get("block") or {"n": 0}
    f = lambda s: "0 笔" if not s.get("n") else f"{s['n']} 笔 / 胜率 {s['win']:.1f}% / 每笔 {s['mean']:+.2f}%"      # noqa: E731
    s = f"不挡 {f(k)}；挡 {f(b)}"
    if ev.get("dwin") is not None:
        s += f"；胜率差 {ev['dwin']:+.1f} pp、每笔差 {ev['dmean']:+.2f} pp"
        if "dwin_lo95" in ev:
            s += f"（胜率差 95% 区间 {ev['dwin_lo95']:+.1f}〜{ev['dwin_hi95']:+.1f}，{ev.get('months', 0)} 个月）"
    if ev.get("missing"):
        s += f"；标记缺值 {ev['missing']} 笔（不算）"
    return s


def verdict_lines(r: dict, next_dates=JUDGE_DATES, today=None) -> list[str]:
    """review() 的结果 → 每个闸门的进度与（到时的）判定文字。"""
    out = []
    for k in IDS:
        x = r[k]
        ev = x["eval"]
        out.append(f"- {NAMES[k]}：{summary_line(ev)}")
        if x["year"]:
            ci = (f"；胜率差 99% 区间 {ev['dwin_lo99']:+.1f}〜{ev['dwin_hi99']:+.1f} pp、每笔差 95% 区间 "
                  f"{ev['dmean_lo95']:+.2f}〜{ev['dmean_hi95']:+.2f} pp") if "dwin_lo99" in ev else ""
            out.append(f"  - 判定（{x['year']} 这一年）：{WORDS[x['verdict']]}{ci}")
    if not any(r[k]["year"] for k in IDS):
        nxt = next((d for d in next_dates if today is None or pd.Timestamp(d) > pd.Timestamp(today)), None)
        out.append(f"  只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "  五次年度判定都已做完（只报告）")
    return out


def history_rows(r: dict, run: str, prefix: str = "all_", extra: dict | None = None) -> list[dict]:
    """复核历史：每个闸门一行（scope = all_G10_HWN 等）；判定过的年份下次不再判定。"""
    rows = []
    for k in IDS:
        ev, y = r[k]["eval"], r[k]["year"]
        rows.append({"run": run, "scope": f"{prefix}{SCOPE}{k}", "closed": ev.get("n", 0), YEAR_COL: y,
                     "g_dwin": ev.get("dwin"), "g_dmean": ev.get("dmean"), "g_dwin_lo95": ev.get("dwin_lo95"),
                     "g_dwin_hi95": ev.get("dwin_hi95"), "g_dwin_lo99": ev.get("dwin_lo99"), "g_dwin_hi99": ev.get("dwin_hi99"),
                     "g_dmean_lo95": ev.get("dmean_lo95"), "g_dmean_hi95": ev.get("dmean_hi95"),
                     "g_verdict": r[k]["verdict"], **(extra or {})})
    return rows


def by_month(U: pd.DataFrame, net_col: str = "net_x6", date_col: str = "sig_date") -> dict:
    """只描述（HWN 用）：按信号的日历月 → 笔数 / 胜率 / 每笔。"""
    if not len(U):
        return {}
    m = pd.to_datetime(U[date_col]).dt.month
    return {int(k): W2F.stat(g[net_col]) for k, g in U.groupby(m)}
