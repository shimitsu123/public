"""tq08_forward.py — 趋势线研究最接近的做法 TQ08「日线支撑线短（第一个锚点到信号日 ≤ 75 根）的不买」的前向检验
（2026-10-07 登记；用户〔74〕选 ②「把 TQ08 加进全市场前向检验」）。

登记内容与判定规则：scripts/w2_forward_all.py 第十一节（全市场，季度复核 2i 里自动算）。只记录、不交易：模拟盘与执行器照旧（B4）。
定义照 scripts/trendline_select_study.py（登记 603712a + 2f4f5af、只运行一次、结果 284f898）一个字不改
（tests/test_tq08_forward.py 逐个核对与研究的函数相同）：
  d_sup_len = 信号日 t 的日线支撑线（qbreak/trendline.py scan：k / L / gap / R = 5 / 250 / 10 / 60、容差 0.3 × ATR14；
    第 t 根只用到 t 为止的 K 线）的第一个锚点到 t 的根数 = trendline_select_study.ticker_features 的 F08 列；没有支撑线 → NaN；
    这只票（收盘有值的行）不到 60 根 → 没有特征行。
  挡（g_tq08 = 1）= 有特征行、有支撑线、d_sup_len ≤ 75（= 研究冻结的三分位界线 BOUNDS["F08"][0]；研究的 G1，探索时挑出来挡的那一端）；
  没有特征行 / 没有支撑线（G0）/ 76 根以上（G2、G3）→ 不挡（0）。
统计与判定 = 第十节（qbreak/gate_forward.py）同一组函数：不挡 − 挡 的胜率差 / 每笔差（pp），按信号月聚类的自助法（种子见 SEED）；
  证实 = 胜率差 99% 区间下限 > 0 且每笔差 ≥ 0；否定 = 胜率差或每笔差的 95% 区间上限 < 0；任一组 < 10 笔或 < 3 个月 = 样本不够。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import gate_forward as GF
from . import trendline as TL
from . import w2_forward as W2F

ID = "TQ08"
NAME = "TQ08 日线支撑线短（≤ 75 根）的不买"
FORWARD_START = "2026-10-08"                  # 登记日（2026-10-07）的下一个东证交易日起的信号
SUP_LEN_MAX = 75.0                            # = scripts/trendline_select_study.py BOUNDS["F08"][0]（研究冻结的三分位界线 q1）
MIN_ROWS = 60                                 # = trendline_select_study.ticker_features：收盘有值的行不到 60 → 没有特征行
JUDGE_DATES = W2F.JUDGE_DATES                 # 每年一次（与 W2 / K2 / USW / X6 / R4 / 第十节同一组日期）
BOOT_N, SEED = GF.BOOT_N, 20261007
MIN_N, MIN_MONTHS = GF.MIN_N, GF.MIN_MONTHS   # 样本不够的门槛（同第十节）
FLAG = "g_tq08"
SCOPE = "TQ08"                                # 复核历史的 scope（例 all_TQ08）
YEAR_COL = "tq08_year"


def sup_len(df: pd.DataFrame) -> pd.Series | None:
    """一只票的日线（Open / High / Low / Close）→ 每个交易日的 d_sup_len（与 trendline_select_study.ticker_features 的
    d_sup_len 逐根相同）；收盘有值的行不到 60 根 → None（没有特征行）。"""
    d = df[["Open", "High", "Low", "Close"]].astype(float)
    d = d[d["Close"].notna()]
    if len(d) < MIN_ROWS:
        return None
    s = TL.scan(d, "D")
    idx = np.arange(len(d))
    return pd.Series(np.where(s["sup_a1"] >= 0, idx - s["sup_a1"], np.nan).astype(np.float32), index=d.index, name="d_sup_len")


def value_at(v: pd.Series | None, date) -> tuple[float, bool]:
    """sup_len 的结果 → 那一天的 (d_sup_len, 有没有特征行)。"""
    if v is None:
        return float("nan"), False
    k = v.index.get_indexer([pd.Timestamp(date)])[0]
    return (float(v.iloc[k]), True) if k >= 0 else (float("nan"), False)


def flag(values, has=None) -> np.ndarray:
    """d_sup_len → 1（挡：有特征行、有支撑线、≤ 75 根）/ 0（不挡）。"""
    v = np.asarray(values, float)
    ok = np.ones(len(v), bool) if has is None else np.asarray(has, bool)
    with np.errstate(invalid="ignore"):
        return (ok & np.isfinite(v) & (v <= SUP_LEN_MAX)).astype(int)


def evaluate(U: pd.DataFrame, **kw) -> dict:
    """成熟、两边都已平仓的配对（带 g_tq08）→ 不挡 / 挡 两组的统计与区间（第十节 gate_forward.evaluate，种子 SEED）。"""
    return GF.evaluate(U, FLAG, **{"seed": SEED, **kw})


def review(U: pd.DataFrame, hist: pd.DataFrame | None, today, prefix: str = "all_", **kw) -> dict:
    """统计 + 这次是不是年度判定（复核日第一次到达 JUDGE_DATES 之后；做过的年份不再做）+ 判定结果。"""
    ev = evaluate(U, **kw)
    year = W2F.due_date(today, JUDGE_DATES, W2F.history_done(hist, f"{prefix}{SCOPE}", YEAR_COL))
    return {"eval": ev, "year": year, "verdict": GF.verdict(ev) if year else None}


def verdict_lines(r: dict, next_dates=JUDGE_DATES, today=None) -> list[str]:
    ev = r["eval"]
    out = [f"- {NAME}：{GF.summary_line(ev)}"]
    if r["year"]:
        ci = (f"；胜率差 99% 区间 {ev['dwin_lo99']:+.1f}〜{ev['dwin_hi99']:+.1f} pp、每笔差 95% 区间 "
              f"{ev['dmean_lo95']:+.2f}〜{ev['dmean_hi95']:+.2f} pp") if "dwin_lo99" in ev else ""
        out.append(f"  - 判定（{r['year']} 这一年）：{GF.WORDS[r['verdict']]}{ci}")
    else:
        nxt = next((d for d in next_dates if today is None or pd.Timestamp(d) > pd.Timestamp(today)), None)
        out.append(f"  只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "  五次年度判定都已做完（只报告）")
    return out


def history_row(r: dict, run: str, prefix: str = "all_", extra: dict | None = None) -> dict:
    ev = r["eval"]
    return {"run": run, "scope": f"{prefix}{SCOPE}", "closed": ev.get("n", 0), YEAR_COL: r["year"],
            "g_dwin": ev.get("dwin"), "g_dmean": ev.get("dmean"), "g_dwin_lo95": ev.get("dwin_lo95"), "g_dwin_hi95": ev.get("dwin_hi95"),
            "g_dwin_lo99": ev.get("dwin_lo99"), "g_dwin_hi99": ev.get("dwin_hi99"), "g_dmean_lo95": ev.get("dmean_lo95"),
            "g_dmean_hi95": ev.get("dmean_hi95"), "g_verdict": r["verdict"], **(extra or {})}


__all__ = ["ID", "NAME", "FORWARD_START", "SUP_LEN_MAX", "sup_len", "value_at", "flag", "evaluate", "review", "verdict_lines",
           "history_row"]
