"""era_forward.py — 「时代主线」的前向记录（2026-09-27 登记；只记录、只展示，不影响交易）。

依据：scripts/era_study.py（登记 825bd56）—— 最近 12 个月（跳过最近 1 个月）领先的行业之后平均还会跑赢（美国 1931〜2026 三段都成立，
日本 2006〜2026 两段都 +4.7〜4.9%/年）；3 年以上的领先反而反转。这里把「现在的排名」每个月记一次，以后用真实发生的收益核对（= 模型每个月
用新数据重排、准确率自动记分）。
记录（var/out/era_forward.csv，只追加、同一个 (market, asof, group) 只留最早那次、不改、不补写）：
  JP-S33 / JP-TH：日本東証业种 / 12 个主题的 12-1 个月相对收益与排名（qbreak/theme_monitor.py strength 的 r12，TOPIX 1000 等权）。
    每个月第一次 sim-day 运行（数据的最后一天已是上个月）时记一次，asof = 数据最后一天所在的月份（= 上个月末的排名）。
  US-FF49：美国 49 行业（Ken French）M12 分数与排名；新的月份出来时记一次，asof = 数据的最后一个月。
  2026-10-01 起记（第一次 = 2026-09 末的排名）。
复核（scripts/era_outlook.py --review，事先写定）：每个 asof 月的前 7（日本业种）/ 前 3（主题）/ 前 10（美国）之后 1 个月、12 个月的相对收益
（日本 = 相对 TOPIX 1000 等权平均；美国 = 相对 49 行业等权平均）；记满 36 个月（3 年）起，日本业种前 7「之后 1 个月」的平均超额
95% 区间上限 < 0 → 判为「时代主线在新数据里失效」→ 日报不再把它叫时代主线、要重新研究（改日报要用户确认）；其余时候只报告进度。
3 个月判定（2026-09-29 登记；用户 2026-09-28 要求「时间主线从一年改为3个月一判定，时间主线要标记当前各行业影响占比」）：
  JP-S33Q / JP-THQ：最近一个完整日历季度的业种 / 主题相对收益（qbreak/theme_monitor.py quarter_rank，TOPIX 1000 等权）与排名，
    asof = 「2026Q3」这样的季度；新季度第一次 sim-day 运行（判定的季度 = 今天所在季度的上一个季度）时记一次；数据没到季末 → 那天不记。
  JP-INFQ：同一个季度里各业种的「影响占比」（qbreak/sector_influence.py，J-Quants 東証業種別指数；score = 占比 %，按占比排名）；取不到就不记。
  2026-10-01 起记（第一次 = 2026Q3）。复核（scripts/era_outlook.py --review）：每季的业种前 7 / 主题前 3 下一季的相对收益；
  记满 12 个季度（3 年）起，业种前 7「下一季」平均超额的 95% 区间上限 < 0 → 判为 3 个月的主线在新数据里失效（改日报要用户确认）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FORWARD_START = "2026-10-01"
LOG_FILE = "era_forward.csv"
COLS = ["logged_on", "market", "asof", "group", "score", "rank", "of"]
TOP = {"JP-S33": 7, "JP-TH": 3, "US-FF49": 10, "JP-S33Q": 7, "JP-THQ": 3}
JUDGE_MONTHS = 36
JUDGE_QUARTERS = 12


def jp_rows(groups: dict, theme_keys, asof_day: str, today: str) -> list[dict]:
    """theme_monitor 的 groups → 记录行（业种 JP-S33、主题 JP-TH；r12 缺值的不记）。"""
    asof = str(asof_day)[:7]
    rows = []
    for g, v in (groups or {}).items():
        if v.get("r12") is None or v.get("rank12") is None:
            continue
        rows.append({"logged_on": today, "market": "JP-TH" if g in theme_keys else "JP-S33", "asof": asof, "group": g,
                     "score": float(v["r12"]), "rank": int(v["rank12"]), "of": int(v.get("of12") or 0)})
    return rows


def us_rows(R: pd.DataFrame, today: str) -> list[dict]:
    """Ken French 49 行业月收益 → 最后一个月的 M12（第 t−11 … t−1 个月的累计对数收益 %）排名。"""
    L = np.log1p(R / 100.0) * 100
    s = L.shift(1).rolling(11, min_periods=11).sum().iloc[-1].dropna().sort_values(ascending=False)
    asof = str(R.index[-1])[:7]
    return [{"logged_on": today, "market": "US-FF49", "asof": asof, "group": g, "score": round(float(v), 3), "rank": k + 1, "of": len(s)}
            for k, (g, v) in enumerate(s.items())]


def append(path: Path, rows: list[dict]) -> int:
    """只追加；同一个 (market, asof, group) 已经有了就不写。返回新增行数。"""
    if not rows:
        return 0
    new = pd.DataFrame(rows, columns=COLS)
    if path.exists():
        old = pd.read_csv(path, dtype={"asof": str, "group": str, "market": str})
        seen = set(zip(old["market"], old["asof"], old["group"]))
        new = new[[(m, a, g) not in seen for m, a, g in zip(new["market"], new["asof"], new["group"])]]
        if new.empty:
            return 0
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return int(len(new))


def due_jp(asof_day: str | None, today: str) -> bool:
    """日本：今天 ≥ 开始日、且数据的最后一天已经是上个月（= 这是新月份的第一次运行）。"""
    if not asof_day or str(today) < FORWARD_START:
        return False
    return str(asof_day)[:7] < str(today)[:7]


def log_month(path: Path, themes: dict | None, today: str, us_R: pd.DataFrame | None = None) -> dict:
    """sim-day 调用：该记的时候记（日本按月、美国按新月份）；返回 {jp, us, rows}。"""
    from . import themes as TH
    res = {"jp": 0, "us": 0}
    th = themes or {}
    if due_jp(th.get("asof"), today):
        res["jp"] = append(path, jp_rows(th.get("groups") or {}, set(TH.THEMES), th.get("asof"), today))
    if us_R is not None and len(us_R) and str(today) >= FORWARD_START:
        res["us"] = append(path, us_rows(us_R, today))
    res["rows"] = int(len(pd.read_csv(path))) if path.exists() else 0
    return res


def score_next(log: pd.DataFrame, rel_month: pd.DataFrame, market: str, horizon: int = 1) -> pd.DataFrame:
    """某个市场每个 asof 月：前 k 名之后 horizon 个月的相对收益平均（rel_month = 月 × 组 的相对收益 %，index = 月份 'YYYY-MM'）。"""
    k = TOP[market]
    d = log[log["market"] == market]
    rows = []
    months = list(rel_month.index)
    for a, g in d.groupby("asof"):
        if a not in months:
            continue
        i = months.index(a)
        fut = months[i + 1:i + 1 + horizon]
        if len(fut) < horizon:
            continue
        top = list(g.sort_values("rank")["group"].iloc[:k])
        cols = [c for c in top if c in rel_month.columns]
        if not cols:
            continue
        x = rel_month.loc[fut, cols].sum(axis=0).mean()
        rows.append({"asof": a, "excess": float(x), "n": len(cols)})
    return pd.DataFrame(rows, columns=["asof", "excess", "n"])


def quarter_rows(era_q: dict, theme_keys, today: str) -> list[dict]:
    """theme_monitor.quarter_rank → 记录行（业种 JP-S33Q、主题 JP-THQ）。"""
    q = era_q.get("quarter")
    return [{"logged_on": today, "market": "JP-THQ" if g in theme_keys else "JP-S33Q", "asof": q, "group": g,
             "score": float(v["q"]), "rank": int(v["rank"]), "of": int(v["of"])} for g, v in (era_q.get("rank") or {}).items()]


def influence_rows(infl: dict, quarter: str, today: str) -> list[dict]:
    """sector_influence.shares（判定季度的窗口）→ JP-INFQ 行（score = 影响占比 %，按占比排名）。"""
    rows = list((infl or {}).get("rows", {}).items())
    return [{"logged_on": today, "market": "JP-INFQ", "asof": quarter, "group": g, "score": float(v["share"]), "rank": k + 1,
             "of": len(rows)} for k, (g, v) in enumerate(rows)]


def due_quarter(era_q: dict | None, today: str) -> bool:
    """今天 ≥ 开始日，且判定的季度正好是今天所在季度的上一个季度（数据已到季末）。"""
    q = (era_q or {}).get("quarter")
    if not q or str(today) < FORWARD_START or not (era_q or {}).get("rank"):
        return False
    return pd.Period(q, freq="Q") == pd.Timestamp(today).to_period("Q") - 1


def log_quarter(path: Path, themes: dict | None, today: str, infl_q: dict | None = None) -> dict:
    """sim-day 调用：新季度的第一次运行记上一季的 3 个月判定（与影响占比）；只追加，同一个 (market, asof, group) 只留最早那次。"""
    from . import themes as TH
    eq = (themes or {}).get("era_q") or {}
    if not due_quarter(eq, today):
        return {"q": 0, "inf": 0}
    res = {"q": append(path, quarter_rows(eq, set(TH.THEMES), today)), "inf": 0, "quarter": eq["quarter"]}
    if infl_q and infl_q.get("rows") and infl_q.get("window"):
        res["inf"] = append(path, influence_rows(infl_q, eq["quarter"], today))
    return res


def judge(s: pd.DataFrame, need: int = JUDGE_MONTHS) -> dict:
    """记满 need 期（缺省 36 个月；3 个月判定用 12 个季度）起：平均超额的 95% 区间上限 < 0 → 失效；其余只报告进度。"""
    x = s["excess"].to_numpy(float) if len(s) else np.array([])
    n = len(x)
    out = {"n": n, "mean": float(x.mean()) if n else None, "hit": float((x > 0).mean() * 100) if n else None}
    if n >= 2:
        se = x.std(ddof=1) / np.sqrt(n)
        out["lo95"], out["hi95"] = float(x.mean() - 1.96 * se), float(x.mean() + 1.96 * se)
    out["judged"] = n >= need
    out["failed"] = bool(out["judged"] and out.get("hi95") is not None and out["hi95"] < 0)
    return out
