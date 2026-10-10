"""earn_state.py — 最近一次决算的「形态」（㊱ 2026-09-29 用户确认：日报的候补队列 / 持仓旁标出；只展示，不改交易）。

定义与登记研究完全相同（直接用 scripts/earn_traj_data.py，登记 fabde0b；结果 var/out/earn_traj_study.md）：
  J-Quants 決算短信サマリー（/fins/summary）→ 每个单季的营业利润（同一会计年度的累计相减；每季只用第一次开示的数字；
  有连结就只用连结）→ 6 季连续时的形态：T1 亏损收窄 / T2 扭亏为盈 / T3 盈转亏 / T4 亏损扩大 / T5 盈利连续两季同比 −20% 以上 /
  T6 盈利加速 / N 其余。
研究结论（只作参考）：日本全市场开示后 60 个交易日，T2 / T6 比其余跑赢约 1〜2 pp、T3 / T4 跑输约 1.4〜2.4 pp（2017〜2021 与
  2022〜 都显著）；T1 / T5 没有影响；放到 W2 突破上当过滤没有增益 → 不改交易。
数据：每只票每天最多调一次 J-Quants（原始数据只缓存在 var/cache/jquants/fins_code/，不入库）；日报只放形态标签与开示日。
非投资建议。
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import sys

import numpy as np
import pandas as pd

from . import paths
from .utils import read_json, write_json

log = logging.getLogger(__name__)

SHORT = {"T1": "亏损收窄", "T2": "扭亏为盈", "T3": "盈转亏", "T4": "亏损扩大", "T5": "盈利连续恶化", "T6": "盈利加速",
         "N": "无特定形态"}
EFFECT = {"T2": "+", "T6": "+", "T3": "−", "T4": "−"}          # 研究里两个年代都显著的方向（+ = 之后 60 日跑赢其余）
MAX_AGE_DAYS = 100                                              # 研究的选股层用「信号日前 100 天内最近一次开示」；更旧 → 标「旧」


def _et():
    sp = str(paths.PROJECT_ROOT / "scripts")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    import earn_traj_data as ET                                 # 登记时的定义（fabde0b），不在这里另写一份
    return ET


def code5(ticker: str) -> str | None:
    """7203.T → 72030（J-Quants 的 5 位代码）；不是东证代码 → None。"""
    t = str(ticker)
    if not t.endswith(".T"):
        return None
    c = t[:-2]
    return f"{c}0" if len(c) == 4 else None


def _cache_path(c5: str):
    from .jquants import cache_dir
    d = cache_dir() / "fins_code"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{c5}.json"


def fetch_rows(client, c5: str, today: dt.date, fetch: bool = True) -> tuple[list[dict], str | None]:
    """一只票的決算短信（缓存当天取过就不再取；取不到 → 用缓存里旧的，另报原因）。"""
    fp = _cache_path(c5)
    cached = read_json(fp, {}) or {}
    if cached.get("fetched") == today.isoformat() or not fetch or client is None:
        return list(cached.get("rows") or []), (None if cached else "没有缓存")
    try:
        rows = client.get("/fins/summary", code=c5)
    except Exception as e:                                      # noqa: BLE001
        return list(cached.get("rows") or []), f"{type(e).__name__}: {e}"[:160]
    write_json(fp, {"fetched": today.isoformat(), "rows": rows})
    return rows, None


def state_of(rows: list[dict], asof: dt.date) -> dict | None:
    """決算短信 → 最近一次开示（≤ asof）的形态；最近一季凑不满 6 季连续 → state None（另附开示日）。"""
    if not rows:
        return None
    ET = _et()
    F = pd.DataFrame(rows)
    for c in ET.COLS:
        if c not in F.columns:
            F[c] = None
    F = F[ET.COLS].astype(str).replace({"nan": np.nan, "None": np.nan, "": np.nan})
    if not pd.to_numeric(F["OP"], errors="coerce").notna().any():       # 银行 / 保险等只报经常利润 → 研究里也不算
        return {"state": None, "label": "不适用（没有营业利润）", "disc": None, "age_days": None, "stale": False}
    Q = ET.jp_quarters(F)
    if Q.empty:
        return None
    cut = pd.Timestamp(asof)
    Q = Q[Q["disc"] <= cut].reset_index(drop=True)
    if Q.empty:
        return None
    last_disc = Q["disc"].max()
    S = ET.states(Q, "JP")
    S = S[S["disc"] <= cut]
    age = (cut - last_disc).days
    if S.empty or S["disc"].max() < last_disc:
        return {"state": None, "label": "数据不足（凑不满 6 季连续）", "disc": str(last_disc.date()), "age_days": int(age),
                "stale": age > MAX_AGE_DAYS}
    st = str(S.iloc[-1]["state"])
    return {"state": st, "label": SHORT.get(st, st), "effect": EFFECT.get(st), "disc": str(last_disc.date()),
            "age_days": int(age), "stale": age > MAX_AGE_DAYS}


def panel(tickers, asof: dt.date, client=None, fetch: bool = True) -> dict:
    """日报用：{"asof", "states": {ticker: {...}}, "errors": {...}}。没有 JQUANTS_API_KEY → 只用缓存（没有缓存就报原因）。"""
    want = sorted({t for t in tickers if code5(t)})
    out: dict = {"asof": asof.isoformat(), "states": {}, "errors": {}}
    if client is None and fetch and os.environ.get("JQUANTS_API_KEY"):
        try:
            from .jquants import JQuants
            client = JQuants()
        except Exception as e:                                  # noqa: BLE001
            out["errors"]["client"] = f"{type(e).__name__}: {e}"[:160]
    if client is None and fetch:
        out["note"] = "没有 JQUANTS_API_KEY：只用缓存"
    for t in want:
        rows, err = fetch_rows(client, code5(t), asof, fetch=fetch)
        if err and not rows:
            out["errors"][t] = err
            continue
        try:
            s = state_of(rows, asof)
        except Exception as e:                                  # noqa: BLE001
            out["errors"][t] = f"{type(e).__name__}: {e}"[:160]
            continue
        if s is not None:
            out["states"][t] = s
        if err:
            out["errors"][t] = f"用了缓存（{err}）"
    return out


def tag_html(s: dict | None) -> str:
    """日报里的小标签：扭亏为盈 / 盈利加速（+）、盈转亏 / 亏损扩大（−）醒目，其余淡色；开示日在后面。"""
    from html import escape
    if not s:
        return "<span class='muted'>—</span>"
    lab = escape(str(s.get("label") or "—"))
    eff = s.get("effect")
    cls = "pos" if eff == "+" else ("neg" if eff == "−" else "muted")
    old = "（旧）" if s.get("stale") else ""
    d = s.get("disc")
    tail = f"<span class='muted'> {escape(str(d))[5:]} 开示{old}</span>" if d else ""
    return f"<span class='{cls}'>{lab}</span>{tail}"
