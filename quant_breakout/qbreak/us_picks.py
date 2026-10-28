"""us_picks.py — 选股页的「美股（只看，不会自动买）」（2026-10-28 用户：「选股里面的也要加上美股被选出来的股票」）。

只展示：立花 ｅ支店不做美股、楽天的美股不能由程序自动下单 → 执行器不碰美股；这里只把规则在美股上选出来的票列出来，
没有买入按钮、不写手动指令、不登录券商、不动账本。不是建议。

和日本的「规则接下来会自动买」（qbreak/panel._auto_pick）同一套判定：
  signal  最新一根美股日 K 线收盘出了买入信号（compute_indicators 的 entry 列，与 qbreak/scan.py 的 triggered 同一个定义）
  near    还没出信号、scan 的状态是「快要出 / 观察中」、MACD 在信号线下往上靠、估计 NEAR_DAYS 个交易日内金叉（qbreak/suggest.proximity）
参数 = var/best_params.json 叠加 var/best_params_US.json（qbreak/trader.load_params(market="US")）；股票池 = qbreak/universes.us_broad()
（NASDAQ-100 + Dow 30）；新仓倍数（S&P500 牛熊分界 / 市场状态 / 汇率 / 宏观，run._plan_inputs("US", …)）只写进说明，不挡列出。
算的命令：python run.py us-picks（scripts/liveu.sh 模拟账户早上的运行之后在后台跑；也可以 bash scripts/liveu.sh us-picks）
→ 数据目录 out/us_picks.json（不入库）。
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import calendar_us as CU
from . import names as NM
from .calendar_jp import now_jst
from .suggest import NEED, near_text, proximity

FILE = "us_picks.json"
NEAR_DAYS = 5                       # = panel.AUTO_NEAR_DAYS（日本那张卡的「估计 5 个交易日内可能出信号」）
STALE_DAYS = 3                      # as_of 之后又过了这么多个美股交易日以上 → 页面写「旧了」
NOTE = ("立花 ｅ支店不做美股、楽天的美股不能由程序自动下单 → 这里只显示规则选出的美股，没有买入按钮；不是建议。"
        "以前的比较（var/out/market_compare_study.md）：美股被楽天约 1% 的来回费用吃掉。")
STATE_TEXT = {"signal": "已出买入信号", "near": f"估计 {NEAR_DAYS} 个交易日内可能出信号"}


def _f(x, nd: int = 2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if v == v and abs(v) != float("inf") else None


def _gc_day(asof: dt.date, days: int) -> dt.date:
    d = asof
    for _ in range(max(0, int(days))):
        d = CU.next_trading_day(d)
    return d


def build(ind: dict, params, *, scale: float | None = None, tmult: dict | None = None, regime: dict | None = None,
          names: dict | None = None, now: dt.datetime | None = None) -> dict:
    """ind：{代码: compute_indicators 的结果}（已去掉未收盘的 K 线）→ {"as_of", "generated_at", "rows", "counts", "regime", "note"}。
    只列最新那根 K 线日（as_of）有 K 线的票；scale = 美股的新仓倍数（None = 不知道）；tmult = {代码: 板块倾斜 / 指数剔除倍数}。"""
    from .scan import scan
    frames = {t: df for t, df in (ind or {}).items() if df is not None and len(df) and NEED <= set(df.columns)}
    asof = max((df.index[-1] for df in frames.values()), default=None)
    frames = {t: df for t, df in frames.items() if df.index[-1] == asof}
    gen = (now or now_jst()).isoformat(timespec="seconds")
    sc = scan(frames, params, "US", 1e15, top=len(frames)) if frames else pd.DataFrame()
    rec = sc.to_dict("records") if len(sc) else []
    a_day = asof.date() if asof is not None else None
    rows = []
    for r in rec:
        t, st = str(r["ticker"]), r.get("status")
        nm = (names or {}).get(t) or NM.name(t)
        tm = (tmult or {}).get(t)
        gate = []
        if scale is not None and float(scale) <= 0:
            gate.append("美股的新仓倍数现在是 0（牛熊分界 / 市场状态 / 宏观）→ 按规则这时也不开新仓")
        if tm is not None and float(tm) <= 0:
            gate.append("这只的板块倾斜 / 指数剔除倍数 0 → 按规则不开新仓")
        base = {"ticker": t, "code": t, "name": nm, "close": _f(r.get("close")), "score": _f(r.get("score"), 1),
                "vol_ratio": _f(r.get("vol_ratio")), "top_risk": r.get("top_risk") or "", "gate": gate}
        if st == "triggered":
            reason = f"{a_day:%m/%d} 美股收盘出了买入信号（横盘 + MACD 0 轴附近金叉 + 放量）"
            if r.get("top_risk"):
                reason += f"；顶部风险标记：{r['top_risk']}"
            rows.append({**base, "state": "signal", "state_text": STATE_TEXT["signal"], "reason": "；".join([reason] + gate)})
            continue
        if st not in ("imminent", "watch"):
            continue
        n = proximity(frames[t], params)
        if n.get("where") != "below_up" or int(n.get("days") or 99) > NEAR_DAYS:
            continue
        gc = _gc_day(a_day, int(n["days"]))
        rows.append({**base, "state": "near", "state_text": STATE_TEXT["near"], "near": n, "near_days": int(n["days"]),
                     "gc_day": gc.isoformat(), "near_text": near_text(n, params),
                     "reason": "；".join([f"MACD 估计约 {gc:%m/%d}（{int(n['days'])} 个交易日后）金叉；出了买入信号才算"] + gate)})
    rows.sort(key=lambda x: (0, -float(x.get("score") or 0)) if x["state"] == "signal"
              else (1, int(x.get("near_days") or 99), -float(x.get("score") or 0)))
    return {"as_of": a_day.isoformat() if a_day else None, "generated_at": gen, "market": "US", "n_universe": len(frames),
            "rows": rows, "counts": {k: sum(1 for x in rows if x["state"] == k) for k in STATE_TEXT},
            "near_days": NEAR_DAYS, "scale": _f(scale, 3), "regime": regime or {}, "note": NOTE}


def path():
    from . import paths
    return paths.out_dir() / FILE


def write(payload: dict):
    from .utils import write_json
    fp = path()
    write_json(fp, payload)
    return fp


def load() -> dict | None:
    """数据目录 out/us_picks.json；没有 / 读不了 → None（页面写「还没算过」）。"""
    from .utils import read_json
    try:
        d = read_json(path(), None)
    except Exception:                                             # noqa: BLE001  展示用
        return None
    return d if isinstance(d, dict) else None


def lag_days(as_of, today: dt.date | None = None) -> int | None:
    """as_of 之后、到「JST 今天的前一天」为止（美股收盘在 JST 第二天早上）又有几个美股交易日；算不出 → None。"""
    try:
        a = dt.date.fromisoformat(str(as_of)[:10])
    except (TypeError, ValueError):
        return None
    end = (today or now_jst().date()) - dt.timedelta(days=1)
    n, d = 0, a
    while True:
        d = CU.next_trading_day(d)
        if d > end:
            return n
        n += 1


def is_stale(as_of, today: dt.date | None = None) -> bool:
    n = lag_days(as_of, today)
    return n is None or n > STALE_DAYS


def lines(d: dict | None) -> list[str]:
    """命令行用：一行一只（代码 + 名字）。"""
    out = []
    for r in (d or {}).get("rows") or []:
        nm = f" {r['name']}" if r.get("name") else ""
        px = f"${float(r['close']):,.2f}" if r.get("close") is not None else "—"
        out.append(f"- {r['code']}{nm}：{r.get('state_text')}；收盘 {px}；{r.get('reason') or ''}")
    return out


__all__ = ["build", "write", "load", "path", "lag_days", "is_stale", "lines", "FILE", "NEAR_DAYS", "STALE_DAYS", "NOTE", "STATE_TEXT"]
