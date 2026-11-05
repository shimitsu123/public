"""charts_refresh.py — 收盘后把正式日线补进操作面板的 K 线（out/charts_<账本>.json）；只展示，不动账本、不做决策。

2026-10-11 用户：「现在的日线在周五闭盘了也没有反应对应的股价，制定永久防止对策，横展开」。
根因：K 线文件只在执行器早上的运行（交易日 07:40）重写，画到「决策用的那一天」为止；盘中那一根只在面板内存里（现价缓存，面板重启就没了）。
→ 周五收盘之后到下一个交易日 07:40（连休时更久）图上一直缺最近的那一根。
对策：
  - refresh(tag)：K 线文件里最后一根日K 早于「最近一个已收盘的交易日」（expected_bar）→ 同一批票、原来的标注（kind / 买入价 / 止损…）
    按最新的正式日线重画（drop_partial_bar 去掉没收盘的当天），写 bars_asof；执行器正在跑（账本锁）→ 这次不动。
  - 定时：市场仪表盘的定时任务（每 15 分钟，scripts/liveu.sh news）顺带跑 `run.py charts-refresh --if-stale`（不落后 = 什么都不做）。
  - 检出：菜单栏状态（qbreak/mac_status.py）「K 线」一项：收盘 2 小时后还落后 → 警告。
  - 横展开：面板的日 / 周 / 月趋势标签（持仓、核心 ETF、建议的股票）用 K 线文件里更新过的那一份（比执行器汇总新的时候）。
"""
from __future__ import annotations

import datetime as dt
import logging

from . import paths
from .calendar_jp import JST, is_trading_day, now_jst, prev_trading_day
from .utils import read_json, write_json

log = logging.getLogger("qbreak.charts_refresh")
CLOSE_READY = dt.time(15, 45)            # 15:30 收盘、Yahoo 日线约 15 分钟后可取
STALE_WARN = dt.time(17, 45)             # 收盘 2 小时后还落后 → 菜单栏警告
META = ("tf", "trend", "ind")


def expected_bar(now: dt.datetime | None = None) -> dt.date:
    """最近一个已经收盘（且日线可取）的东证交易日。"""
    now = (now or now_jst()).astimezone(JST)
    d = now.date()
    if is_trading_day(d) and now.time() >= CLOSE_READY:
        return d
    return prev_trading_day(d)


def path(tag: str):
    return paths.out_dir() / f"charts_{tag}.json"


def last_bar(doc: dict) -> str | None:
    """K 线文件里最后一根日K 的日期（全部票里最新的）。"""
    best = None
    for pl in (doc.get("tickers") or {}).values():
        ds = (((pl or {}).get("tf") or {}).get("D") or {}).get("d") or []
        if ds and (best is None or str(ds[-1]) > best):
            best = str(ds[-1])[:10]
    return best


def stale(tag: str, now: dt.datetime | None = None) -> dict:
    """{"have": 最后一根, "want": 应该有的, "stale": bool}；没有文件 → have None、stale False（执行器还没跑过）。"""
    doc = read_json(path(tag), None)
    want = expected_bar(now).isoformat()
    if not doc:
        return {"have": None, "want": want, "stale": False}
    have = last_bar(doc)
    return {"have": have, "want": want, "stale": bool(have and have < want)}


def _busy(tag: str) -> bool:
    from .live_unified import RunLock
    try:
        lk = RunLock((paths.state_dir() / f"live_unified_{tag}.json").with_suffix(".lock"), wait_s=0).acquire()
    except Exception:                                        # noqa: BLE001  拿不到 = 执行器正在跑
        return True
    lk.release()
    return False


def refresh(tag: str, now: dt.datetime | None = None, force: bool = False, loader=None) -> dict:
    """落后就重画（force = 不看落后）。loader(tickers) → {票: OHLCV DataFrame}（测试用；缺省 = 10 年 yfinance，带缓存）。
    → {"ok", "did", "have", "want", "n", "msg"}；绝不抛。"""
    from . import kline as KL
    from .trader import drop_partial_bar
    st = stale(tag, now)
    if not force and not st["stale"]:
        return {"ok": True, "did": False, **st, "msg": "不落后" if st["have"] else "还没有 K 线文件（执行器下一次运行写）"}
    if _busy(tag):
        return {"ok": True, "did": False, **st, "msg": "执行器正在运行：这次不动（它自己会写）"}
    doc = read_json(path(tag), {}) or {}
    tk = doc.get("tickers") or {}
    if not tk:
        return {"ok": True, "did": False, **st, "msg": "K 线文件是空的"}
    try:
        if loader is None:
            from .config import DataConfig
            from .data import load_universe

            def loader(ts):
                return load_universe(ts, DataConfig(provider="yfinance", years=10, allow_synthetic=False, min_bars=60).validate())
        data = loader(sorted(tk))
    except Exception as e:                                   # noqa: BLE001
        log.warning("K 线补日线：行情取不到：%s", e)
        return {"ok": False, "did": False, **st, "msg": f"行情取不到：{type(e).__name__}"}
    out, n = {}, 0
    for t, pl in tk.items():
        df = data.get(t)
        df = drop_partial_bar(df, "JP" if t.endswith(".T") else "US", now) if df is not None and len(df) else None
        info = {k: v for k, v in (pl or {}).items() if k not in META}
        new = KL.payload(df, None, info) if df is not None and len(df) else None
        if new and (((new.get("tf") or {}).get("D") or {}).get("d") or [""])[-1] >= ((((pl or {}).get("tf") or {}).get("D") or {}).get("d") or [""])[-1]:
            out[t], n = new, n + 1
        else:
            out[t] = pl                                       # 取不到 / 反而更旧 → 原样
    doc2 = {**doc, "tickers": out, "refreshed": (now or now_jst()).isoformat(timespec="seconds")}
    doc2["bars_asof"] = last_bar(doc2)
    write_json(path(tag), doc2)
    return {"ok": True, "did": True, "have": doc2["bars_asof"], "want": st["want"], "n": n,
            "msg": f"日线补到 {doc2['bars_asof']}（{n} / {len(tk)} 只）"}


def books() -> list[str]:
    """有 K 线文件的账本。"""
    return sorted(p.stem[len("charts_"):] for p in paths.out_dir().glob("charts_*.json"))
