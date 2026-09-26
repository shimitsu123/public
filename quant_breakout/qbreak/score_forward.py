"""score_forward.py — 买点「质量分」的前向记录（2026-09-26 事先登记；登记内容与复核规则见 scripts/score_forward.py 开头）。

每次云端 sim-day 运行（日本交易日早上）：把最近 LOOKBACK 个已处理的日本交易日（且 ≥ FORWARD_START）里，日経225 股票池
所有买入信号（entry 成立）连同 15 个因子的原值、冻结的配比（var/score_forward_model.json：F1〜F5 与各因子的训练样本分布，
用 2026-09-25 为止已平仓的交易定下，之后不改）算出的分数，追加到 var/out/score_forward.csv。
同一个「日期 × 票」只保留最早记下的那次（不改、不补写旧值；只补漏记的）。结果（这笔信号赚没赚）不写进记录：
复核时按那时的行情、用同一套出场规则算。只作记录，不影响交易。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import signal_score as S
from .scan import breakout_fields
from .sectors import SECTOR_JP

FORWARD_START = "2026-09-28"
LOOKBACK = 5
KEYS = ["F1", "F2", "F3", "F4", "F5"]
MODEL_FILE, LOG_FILE = "score_forward_model.json", "score_forward.csv"


# ── 冻结的配比 ──
def save_model(models: dict[str, S.Model], meta: dict, path: Path) -> None:
    refs: dict[str, list] = {}
    for m in models.values():
        for c in m.cols:
            refs.setdefault(c, np.sort(np.asarray(m.refs[c], float)[np.isfinite(m.refs[c])]).tolist())
    doc = {"meta": meta, "refs": refs,
           "models": {k: {"kind": m.kind, "cols": m.cols, "w": [float(x) for x in m.w], "b0": float(m.b0), "thr": float(m.thr),
                          "info": {q: v for q, v in m.info.items() if q == "lam"}} for k, m in models.items()}}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def load_model(path: Path) -> tuple[dict[str, S.Model], dict]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    refs = {c: np.asarray(v, float) for c, v in doc["refs"].items()}
    models = {k: S.Model(v["kind"], list(v["cols"]), {c: refs[c] for c in v["cols"]}, np.asarray(v["w"], float),
                         float(v["b0"]), float(v["thr"]), dict(v.get("info") or {}))
              for k, v in doc["models"].items()}
    return models, doc.get("meta") or {}


# ── 当天的信号 → 记录行 ──
def signal_rows_on(ind: dict[str, pd.DataFrame], index_close: pd.Series | None, dates: list, tickers: list[str]) -> pd.DataFrame:
    """tickers（股票池）里、dates 这些日子 entry 成立的信号 + 15 个因子（行业因子按同一个股票池算）。"""
    uni = {t: ind[t] for t in tickers if t in ind}
    if not uni or not dates:
        return pd.DataFrame(columns=["date", "ticker", *S.ALL])
    panel = S.feature_panel(uni, index_close)
    rows = S.signal_rows(panel, uni)
    return rows[rows["date"].isin(pd.DatetimeIndex(dates))].reset_index(drop=True)


def score_rows(rows: pd.DataFrame, models: dict[str, S.Model]) -> pd.DataFrame:
    out = rows.copy()
    for k, m in models.items():
        s = m.score(out) if len(out) else np.array([])
        out[k] = np.round(s, 6)
        out[f"{k}_keep"] = (s >= m.thr).astype(int) if len(out) else []
    return out


def append_log(rows: pd.DataFrame, path: Path) -> int:
    """追加；同一个 (date, ticker) 保留最早那次。返回新增的行数。"""
    if rows.empty:
        return 0
    new = rows.copy()
    new["date"] = pd.to_datetime(new["date"]).dt.strftime("%Y-%m-%d")
    if path.exists():
        old = pd.read_csv(path, dtype={"date": str, "ticker": str})
        seen = set(zip(old["date"], old["ticker"]))
        new = new[[(d, t) not in seen for d, t in zip(new["date"], new["ticker"])]]
        if new.empty:
            return 0
        allr = pd.concat([old, new], ignore_index=True)
    else:
        allr = new
    allr.sort_values(["date", "ticker"], kind="mergesort").to_csv(path, index=False)
    return int(len(new))


def run_daily(ind: dict[str, pd.DataFrame], index_close: pd.Series | None, tickers: list[str], bar_dates: list,
              planned: dict[str, list] | None, model_path: Path, log_path: Path, today: str) -> dict:
    """最近 LOOKBACK 个交易日（≥ FORWARD_START）的信号打分并追加。planned：{日期: 当天收盘后模拟盘计划买入的票}（本次处理的日子才有）。"""
    models, meta = load_model(model_path)
    days = sorted({pd.Timestamp(d) for d in bar_dates if pd.Timestamp(d) >= pd.Timestamp(FORWARD_START)})
    if not days:
        return {"logged": 0, "days": [], "note": f"{FORWARD_START} 之前不记"}
    rows = score_rows(signal_rows_on(ind, index_close, days, tickers), models)
    if len(rows):
        ds = rows["date"].dt.strftime("%Y-%m-%d")
        pl = planned or {}
        info = []
        for d, t in zip(rows["date"], rows["ticker"]):
            r = ind[t].loc[d]
            bo = breakout_fields(r)
            info.append({"close": round(float(r["Close"]), 2), "vol_ratio": round(float(r["vol_ratio"]), 3),
                         "breakout": int(bo["breakout"]), "to_box_top_pct": bo["to_box_top_pct"]})
        head = pd.DataFrame({"date": rows["date"], "ticker": rows["ticker"],
                             "sector": [SECTOR_JP.get(t.split(".")[0], "other") for t in rows["ticker"]],
                             "planned": [(1 if t in set(pl[d]) else 0) if d in pl else np.nan for d, t in zip(ds, rows["ticker"])]})
        rows = pd.concat([head, pd.DataFrame(info), rows.drop(columns=["date", "ticker"]).round(6)], axis=1)
        rows["logged_on"], rows["model"] = today, meta.get("id", "")
    n = append_log(rows, log_path)
    return {"logged": n, "signals": int(len(rows)), "days": [str(d.date()) for d in days], "model": meta.get("id", "")}
