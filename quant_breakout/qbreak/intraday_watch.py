"""intraday_watch.py — 盘中观测：现行日线规则的暂定买卖点（约晚 20 分钟；2026-10-16 用户要求；只展示 + 手机提醒，不下单、不改规则）。

用户（2026-10-15）：「研究按照股票分钟k线的话怎么做策略才会让收益最大化 实时观测所有股票是否出现买卖点等等」。
分钟 K 线研究（scripts/minute_study.py；var/sim_changes.md 2026-10-15）：日内规则 A〜D 的 11 格扣成本后每笔都亏 → 不加日内规则。
这里只把**现行的日线规则**搬到盘中看：「如果今天就收在现价（成交量就是现在的累计量）」，规则今天收盘会不会出买点 / 卖点
（→ 明早 09:00 开盘由执行器照常买 / 卖）。暂定：收盘前价格还会变；以明早 07:40 执行器的决策为准。

怎么跑：操作面板（qbreak/panel.py serve）里的一个线程：交易日（含临时休市）08:55〜11:35、12:25〜16:30 每 5 分钟叫一次
  python -m qbreak.intraday_watch --book <账本>（模拟账户；有立花本番账本时也跑立花）；Mac 睡着 / 面板没开 → 不跑（没有单独的 LaunchAgent）。
  看结果：bash scripts/liveu.sh intraday（读最近一次的结果，只读）；--dry = 现在算一次、只打印（不写、不推送）。
一次做什么：
  ① 每天第一次：执行器的股票池（日経225）的日线（数据目录 cache/ 里执行器早上取好的；这里不取日线、不写缓存）→ 每只今天收盘的
     买点区间（qbreak/timeline.buy_trigger：¥下沿〜¥上沿、成交量至少多少；上沿不超过涨停价）→ 存进结果文件，当天复用；
  ② 盯的票 = 今天可能出买点的 + 持仓 + 核心 ETF；Yahoo 1 分钟线（qbreak/data.intraday_quotes；约晚 20 分钟；不连立花）；
     取不到 → 留着上一次的、标「过期」；
  ③ 候补：价 + 量都已满足（暂定成立）/ 价在区间、量还差 X% / 离下沿 ≤ 1% / 不在区间（成立与否用 timeline.provisional_entry：
     今天到现在为止的开 / 高 / 低 / 现价 / 累计量接在日线后面、同一个 compute_indicators）；闸门读执行器早上的汇总
     out/live_unified_<账本>.json（HALT、新仓倍数 0、名额、资格检查、立花能不能买、一手买不起、候补队列写的挡住理由），读不到 →「闸门未知」；
     持仓：每条收盘卖出线离现价多远（timeline.exit_lines；越过 = 若收盘仍在这里 → 规则明早开盘卖）；核心 ETF：现价与今天的涨跌；
  ④ 写 out/intraday_<账本>.json（原子写；数据时刻、「约晚 20 分钟」）；
  ⑤ 手机推送（qbreak/notify.send = qbreak 推送 + 通知记录；设置：数据目录 intraday.json {"push": true}，
     bash scripts/liveu.sh intraday push on|off）：
     买 = 价在区间 且 累计量 ≥ 所需 且 完整的买入条件成立；卖 = 持仓、数据时刻 ≥ 14:10、越过一条收盘卖出线（止损 / 跟踪止损 / 止盈 /
     吊灯 / 死叉）且规则判卖；同一只同一边一天一次（qbreak/notify_seen，键不含价格）、每个账本一天最多 5 条；
     数据过期（> 30 分钟）/ 取不到 → 不推；HALT 中写明「明早不会下单」。不做收盘汇总推送。
不做：不下单、不写手动指令、不改账本 / 规则 / 参数 / 股票池；不扫全市场（只扫执行器的股票池）。
代码一律带名字（qbreak/names.py）。非投资建议。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from . import names as NM
from . import paths
from .calendar_jp import JST, is_trading_day, now_jst, prev_trading_day
from .run_status import peek_json
from .utils import atomic_write_text, setup_logging

log = setup_logging("intraday")

VERSION = 1
LAG = "约晚 20 分钟"
SRC = "Yahoo 1 分钟线（约晚 20 分钟）"
WINDOWS = ((dt.time(8, 55), dt.time(11, 35)), (dt.time(12, 25), dt.time(16, 30)))   # 面板叫的时段（JST，交易日）
EVERY_S = 300                      # 面板每 5 分钟叫一次
TIMEOUT_S = 120                    # 一次最多 2 分钟（面板到时间就结束它）
STALE_MIN = 30                     # 数据比应有的晚 30 分钟以上 → 过期（不推送）
CAP = 5                            # 每个账本一天最多推 5 条
SELL_FROM = dt.time(14, 10)        # 卖点只在数据时刻 14:10 之后推（离收盘近，价格不太会再大变）
NEAR_PCT = 1.0                     # 离下沿 ≤ 1%
AM_END, PM_START, CLOSE = dt.time(11, 30), dt.time(12, 30), dt.time(15, 30)
SETTINGS = "intraday.json"
LOG_NAME = "com.qbreak.panel.intraday.log"
TITLE = "今天盘中：规则的买点（暂定，约晚 20 分钟）"
FOOT = "暂定：以明早 07:40 执行器为准；规则的候选，不是建议；非投资建议"
NO_RESEARCH = "盘中手动买卖没有研究支持（分钟 K 线研究 2026-10-15：日内规则扣成本后都亏）"
_TAG = re.compile(r"[a-z][a-z0-9_]{0,31}")
KIND_ORDER = {"ok": 0, "shape": 1, "vol": 2, "near": 3, "out": 4, "nodata": 5}


# ───────────────────────── 时间 ─────────────────────────
def _jst(now: dt.datetime | None) -> dt.datetime:
    now = now or now_jst()
    return now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)


def in_window(now: dt.datetime | None = None) -> bool:
    """面板该叫的时候：交易日（含 run.py extra-closed 的临时休市）08:55〜11:35、12:25〜16:30（JST）。"""
    now = _jst(now)
    if not is_trading_day(now.date()):
        return False
    t = now.time()
    return any(a <= t < b for a, b in WINDOWS)


def target_day(now: dt.datetime | None = None) -> dt.date:
    """看哪一天的盘：交易日 08:55 之后 = 今天；之前 / 休市日 = 最近一个交易日（那天的收盘 = 明早执行器决策用的那根）。"""
    now = _jst(now)
    d = now.date()
    if is_trading_day(d) and now.time() >= WINDOWS[0][0]:
        return d
    return prev_trading_day(d)


def _expected_at(now: dt.datetime, day: dt.date) -> dt.datetime:
    """day 这一天、现在应该有的最新数据时刻（午休 → 11:30；收盘后 / 之后的日子 → 15:30；盘中 → 现在）。"""
    now = _jst(now)
    if now.date() > day or now.time() >= CLOSE:
        return dt.datetime.combine(day, CLOSE, tzinfo=JST)
    if AM_END <= now.time() < PM_START:
        return dt.datetime.combine(day, AM_END, tzinfo=JST)
    return now


def _hm(iso: str | None) -> str:
    try:
        return dt.datetime.fromisoformat(str(iso)).astimezone(JST).strftime("%H:%M")
    except (TypeError, ValueError):
        return "—"


def _px(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"¥{v:,.1f}" if v < 1000 else f"¥{v:,.0f}"


def _pct(v, nd: int = 1) -> str:
    return "—" if v is None else f"{float(v):+.{nd}f}%".replace("-", "−")


# ───────────────────────── 设置（数据目录 intraday.json；读不了 → 默认）─────────────────────────
def settings() -> dict:
    try:
        d = json.loads((paths.home() / SETTINGS).read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001  没有 / 读坏 → 默认
        d = {}
    d = d if isinstance(d, dict) else {}
    return {**d, "push": bool(d.get("push", True))}


def set_push(on: bool) -> dict:
    s = {**settings(), "push": bool(on)}
    atomic_write_text(paths.home() / SETTINGS, json.dumps(s, ensure_ascii=False, indent=1))
    return s


def out_path(tag: str) -> Path:
    if not _TAG.fullmatch(str(tag)):
        raise ValueError(f"账本名不对：{tag!r}")
    return paths.out_dir() / f"intraday_{tag}.json"


def load(tag: str) -> dict | None:
    """最近一次的结果（只读；没有 / 读坏 → None）。"""
    try:
        return peek_json(out_path(tag))
    except ValueError:
        return None


# ───────────────────────── 输入：参数、股票池、日线、闸门 ─────────────────────────
def _sim() -> dict:
    return peek_json(paths.home() / "sim.json") or {}


def _params(sim: dict):
    """买入用的参数（与执行器同一个 load_params）+ 离场方式（var/sim.json 的 exits；只改离场字段）。"""
    from . import exit_rules as EXR
    from .trader import load_params
    p = load_params(None, "JP")
    return p, EXR.apply(p, EXR.mode_of(sim, "JP"))


def _pool(sim: dict) -> list[str]:
    from .config import universe
    u = sim.get("unified") or {}
    return list(universe("JP", (u.get("universe") or {}).get("JP", "broad")))


def _core_set(sim: dict, book_state: dict) -> list[str]:
    from . import idle_cash as IC
    held = {t for t, u in (book_state.get("core_units") or {}).items() if int(u or 0) > 0}
    return sorted(set((IC.MODES.get(IC.mode_of(sim)) or {}).get("core") or ()) | held)


def daily(t: str, day: dt.date):
    """数据目录 cache/ 里执行器取好的日线（2 年）：day 之前的部分；最后一根必须是 day 的前一个交易日。不取、不写缓存。
    → (DataFrame | None, 问题 | None)。"""
    import pandas as pd

    from . import data as D
    from .config import DataConfig
    df = D._read_cache(t, 2, 1e9)
    if df is None:
        return None, "没有日线缓存"
    try:
        df = D.validate_ohlcv(t, df, DataConfig(provider="yfinance", years=2, min_bars=60).validate())
    except Exception as e:                                   # noqa: BLE001
        return None, f"日线不合格（{type(e).__name__}）"
    df = df.loc[df.index < pd.Timestamp(day)]
    want = prev_trading_day(day)
    last = df.index[-1].date() if len(df) else None
    if last != want:
        return None, f"日线只到 {last.isoformat() if last else '—'}（应有 {want.isoformat()}）"
    return df, None


def load_gates(tag: str, day: dt.date, book_state: dict, live: dict | None = None) -> dict:
    """执行器早上的汇总 out/live_unified_<账本>.json → 明早开新仓的闸门（只读）。汇总读不到 / 不是今天早上的 → known=False（「闸门未知」）。
    global：所有票都挡的（新仓倍数 0、名额已满）；per：{票: [理由]}（资格检查、立花能不能买、候补队列写的挡住理由）。"""
    g = {"known": False, "note": None, "halt": paths.halt_file().exists(), "global": [], "per": {}, "mult": None,
         "equity": None, "position_pct": None, "max_positions": None, "free": None}
    j = live if live is not None else peek_json(paths.out_dir() / f"live_unified_{tag}.json")
    want = prev_trading_day(day).isoformat()
    if not j:
        g["note"] = "闸门未知（执行器早上的汇总读不到）"
        return g
    if str(j.get("decided_on") or "") != want:
        g["note"] = f"闸门未知（执行器的汇总是 {j.get('decided_on') or '—'} 收盘的，应有 {want}）"
        return g
    g["known"] = True
    npos = j.get("new_pos") or {}
    jp = (npos.get("markets") or {}).get("JP") or {}
    try:
        g["mult"] = float(jp["mult"]) if jp.get("mult") is not None else None
    except (TypeError, ValueError):
        g["mult"] = None
    if g["mult"] is not None and g["mult"] <= 0:
        why = "、".join(str(w[0]) for w in jp.get("why") or [] if isinstance(w, (list, tuple)) and w)
        g["global"].append(f"新仓倍数 0（{why or '宏观 / 板块 / 判断层'}）→ 明早不开新仓")
    sg = j.get("suggest") or {}
    g["equity"] = j.get("equity_jpy")
    g["position_pct"] = npos.get("position_pct") or sg.get("position_pct")
    mx = npos.get("max_positions") or sg.get("max_positions")
    if mx:
        held = len(book_state.get("pos") or {}) - len(book_state.get("pending_exit") or {})
        g["max_positions"], g["free"] = int(mx), int(mx) - max(0, held)
        if g["free"] <= 0:
            g["global"].append(f"名额已满（个股 {max(0, held)} / {int(mx)} 只；要有持仓先卖出）")
    el = j.get("eligibility") or {}
    for b in el.get("blocked") or []:
        if isinstance(b, dict) and b.get("code"):
            g["per"].setdefault(f"{b['code']}.T", []).append(f"资格检查：{b.get('why') or '挡住'}")
    if tag.startswith("tachibana"):
        for b in (el.get("tachibana") or {}).get("stock") or []:
            if isinstance(b, dict) and b.get("code"):
                g["per"].setdefault(f"{b['code']}.T", []).append(f"立花不能买：{b.get('why') or '—'}")
    for r in sg.get("rows") or []:
        blk = ((r or {}).get("buy") or {}).get("block")
        if r.get("ticker") and blk:
            g["per"].setdefault(str(r["ticker"]), []).append(str(blk))
    return g


def _blocks(g: dict, t: str, px: float | None) -> list[str]:
    out = list(g["global"]) + list(g["per"].get(t) or [])
    try:
        mult = 1.0 if g.get("mult") is None else min(1.0, max(0.0, float(g["mult"])))
        budget = float(g["equity"]) * float(g["position_pct"]) * mult
        if px and mult > 0 and px * 100 > budget:
            out.append(f"一手 ¥{px * 100:,.0f} > 每个名额 ¥{budget:,.0f} → 买不起就跳过")
    except (TypeError, ValueError):
        pass
    return out


# ───────────────────────── 买点区间（每天一次）─────────────────────────
def bands_for(day: dt.date, pool: list[str], p, prev: dict | None = None, now: dt.datetime | None = None, daily_fn=None) -> dict:
    """整个股票池今天收盘的买点区间（上沿不超过涨停价）。prev（上一次的结果文件）里是同一天的、日线也都齐 → 直接用
    （日线有缺的：15 分钟后重算，执行器晚到的日线补上了就用上）。daily_fn(票) → (日线, 问题)（默认 daily：数据目录的缓存）。"""
    from . import timeline as TL
    from .tick import price_limit_jp
    now = _jst(now)
    b = (prev or {}).get("bands") or {}
    if b.get("day") == day.isoformat() and b.get("pool_n") == len(pool):
        try:
            age = (now - dt.datetime.fromisoformat(b["computed"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = 1e9
        if not b.get("daily_bad") or age < 900:
            return b
    frames, bad = {}, {}
    for t in pool:
        df, why = (daily_fn or (lambda x: daily(x, day)))(t)
        if df is None:
            bad[t] = why or "没有日线"
        else:
            frames[t] = df
    r = TL.buy_bands(frames, p, day, [t for t in pool if t in frames])
    rows = {}
    for t, bt in r["bands"].items():
        c = float(bt["close"])
        up = c + price_limit_jp(c)                             # 涨停价（制限値幅）：上沿不超过它
        if float(bt["lo"]) > up:
            r["no"][t] = "涨停也够不到下沿"
            continue
        rows[t] = {"lo": bt["lo"], "hi": round(up if bt.get("hi_open") else min(float(bt["hi"]), up), 2), "hi_open": bool(bt.get("hi_open")),
                   "v_need": bt.get("v_need"), "v_min": bt.get("v_min"), "v_w2": bt.get("v_w2"), "close": bt["close"],
                   "x_gc": bt.get("x_gc"), "limit_up": round(up, 2)}
    return {"day": day.isoformat(), "computed": now.isoformat(timespec="seconds"), "pool_n": len(pool), "rows": rows,
            "no": r["no"], "daily_bad": bad}


# ───────────────────────── 取价 ─────────────────────────
def _fetch_default(tickers: list[str]) -> dict:
    from . import data as D
    return D.intraday_quotes(tickers, timeout=4)


# ───────────────────────── 一次 ─────────────────────────
def evaluate(tag: str, now: dt.datetime | None = None, fetch=None, prev: dict | None = None, frames: dict | None = None) -> dict:
    """算一次（不写、不推送）→ 结果（写进 out/intraday_<账本>.json 的那份）。
    fetch(票列表) → {票: {"px", "at", "bar": {"d","o","h","l","c","v"}}}（默认 Yahoo 1 分钟线）；frames（测试用）：{票: 日线}。"""
    import pandas as pd

    from . import timeline as TL
    now = _jst(now)
    day = target_day(now)
    sim = _sim()
    p_in, p_out = _params(sim)
    bk = (peek_json(paths.state_dir() / f"live_unified_{tag}.json") or {}).get("state") or {}
    pool = _pool(sim)
    gates = load_gates(tag, day, bk)
    doc: dict = {"version": VERSION, "book": tag, "day": day.isoformat(), "updated": now.isoformat(timespec="seconds"),
                 "src": SRC, "lag": LAG, "error": "", "stale": False, "age_min": None, "data_at": None, "halt": gates["halt"],
                 "gates": {k: gates[k] for k in ("known", "note", "global", "max_positions", "free", "mult")},
                 "candidates": [], "holdings": [], "core": [], "pool_n": len(pool)}
    if frames is not None:                                    # 测试：直接给日线
        def _daily(t):
            df = frames.get(t)
            return (df.loc[df.index < pd.Timestamp(day)], None) if df is not None else (None, "没有日线")
    else:
        def _daily(t):
            return daily(t, day)
    bands = bands_for(day, pool, p_in, prev, now, _daily)
    doc["bands"] = bands
    held = dict(bk.get("pos") or {})
    pend = dict(bk.get("pending_exit") or {})
    core = _core_set(sim, bk)
    watch = sorted(set(bands["rows"]) | set(held) | set(core))
    # 取价：取不到的留着上一次的（同一天的）
    old = ((prev or {}).get("quotes") or {}) if (prev or {}).get("day") == day.isoformat() else {}
    try:
        got = (fetch or _fetch_default)(watch) if watch else {}
    except Exception as e:                                    # noqa: BLE001
        got, doc["error"] = {}, f"Yahoo 取不到（{type(e).__name__}）：留着上一次的数据"
    if watch and not got and not doc["error"]:
        doc["error"] = "Yahoo 取不到（没有数据）：留着上一次的数据"
    quotes = {}
    for t in watch:
        q = got.get(t) or old.get(t)
        if q and (q.get("bar") or {}).get("d") == day.isoformat():
            quotes[t] = {"px": q.get("px"), "at": q.get("at"), "bar": q.get("bar"), "old": t not in got}
    doc["quotes"] = quotes
    ats = [q["at"] for q in quotes.values() if q.get("at") and not q.get("old")] or [q["at"] for q in quotes.values() if q.get("at")]
    if ats:
        data_at = max(dt.datetime.fromisoformat(a) for a in ats)
        doc["data_at"] = data_at.isoformat(timespec="minutes")
        age = (_expected_at(now, day) - data_at).total_seconds() / 60
        doc["age_min"] = int(round(max(0.0, age)))
        doc["stale"] = age > STALE_MIN
    elif watch:
        doc["stale"] = True
    # 候补
    for t, b in sorted(bands["rows"].items()):
        q = quotes.get(t)
        row = {"ticker": t, "label": NM.label(t), "lo": b["lo"], "hi": b["hi"], "hi_open": b["hi_open"], "v_need": b["v_need"],
               "prev_close": b["close"], "blocks": [], "push_ok": False}
        if not q:
            row.update(kind="nodata", status="还没有今天的数据")
            row["blocks"] = _blocks(gates, t, None)
            doc["candidates"].append(row)
            continue
        bar = q["bar"]
        px, v = float(bar["c"]), float(bar.get("v") or 0)
        need = float(b["v_need"] or 0)
        lo, hi = float(b["lo"]), float(b["hi"])
        in_band = lo <= px <= hi
        row.update(px=round(px, 2), at=q["at"], v=int(v), v_pct=round(v / need * 100, 1) if need > 0 else None,
                   dist_lo_pct=round((px / lo - 1) * 100, 2), in_band=in_band, old=q.get("old"))
        df, _ = _daily(t)
        try:
            pe = TL.provisional_entry(df, p_in, bar, day) if df is not None else {"entry": False, "fails": ["没有日线"]}
        except Exception as e:                                # noqa: BLE001
            pe = {"entry": False, "fails": [f"算不了（{type(e).__name__}）"]}
        row["entry"], row["fails"] = pe["entry"], pe["fails"]
        vol_ok = v >= need
        if pe["entry"]:
            row.update(kind="ok", status="价 + 量都已满足（暂定成立）")
        elif in_band and vol_ok:
            row.update(kind="shape", status="价、量都到了，形态不成立（暂不成立）")
        elif in_band:
            row.update(kind="vol", status=f"价在区间、量还差 {max(0.0, 100 - (row['v_pct'] or 0)):.0f}%")
        elif px < lo and (px / lo - 1) * 100 >= -NEAR_PCT:
            row.update(kind="near", status=f"离下沿 {abs(row['dist_lo_pct']):.1f}%（≤ {NEAR_PCT:g}%）")
        else:
            row.update(kind="out", status="不在区间（" + ("高于上沿" if px > hi else f"低于下沿 {abs(row['dist_lo_pct']):.1f}%") + "）")
        row["blocks"] = _blocks(gates, t, px)
        row["push_ok"] = bool(pe["entry"] and in_band and vol_ok and not q.get("old"))
        doc["candidates"].append(row)
    doc["candidates"].sort(key=lambda r: (KIND_ORDER.get(r["kind"], 9),
                                          -float(r.get("v_pct") or 0) if r["kind"] in ("ok", "shape", "vol")
                                          else -float(r["dist_lo_pct"]) if r.get("dist_lo_pct") is not None else 0.0, r["ticker"]))
    no = bands.get("no") or {}
    groups: dict[str, list[str]] = {}
    for t, why in sorted(no.items()):
        groups.setdefault(str(why), []).append(t)
    for t, why in sorted((bands.get("daily_bad") or {}).items()):
        groups.setdefault(str(why).split("（")[0] if str(why).startswith("日线只到") else str(why), []).append(t)
    doc["impossible"] = [{"why": k, "tickers": v} for k, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    doc["daily_bad_n"] = len(bands.get("daily_bad") or {})
    if bands.get("daily_bad"):
        ex = next(iter(bands["daily_bad"].values()))
        doc["daily_note"] = f"{len(bands['daily_bad'])} 只没有可用的日线（例：{ex}）：这些今天不算区间"
    # 持仓
    for t, ps in sorted(held.items()):
        row = {"ticker": t, "label": NM.label(t), "shares": int(ps.get("shares") or 0), "entry_px": ps.get("entry_px"),
               "queued": pend.get(t), "queued_text": TL.REASON.get(pend[t], str(pend[t])) if pend.get(t) else None, "push_ok": False}
        q = quotes.get(t)
        df, why = _daily(t)
        if not q:
            row["status"] = "还没有今天的数据"
        elif df is None:
            row["status"] = why or "没有日线"
        else:
            try:
                pos = {"entry_px": ps["entry_px"], "peak": ps.get("peak") or ps["entry_px"], "stop_px": ps["stop_px"],
                       "hold": ps.get("hold") or 0, "armed": ps.get("armed")}
                el = TL.exit_lines(df, p_out, pos, q["bar"], day)
                row.update(px=el["px"], at=q["at"], ret_pct=el["ret_pct"], levels=el["levels"], now=el["now"], now_text=el["now_text"],
                           extra=[x.get("text") for x in el.get("extra") or []], old=q.get("old"))
                at = dt.datetime.fromisoformat(q["at"]).astimezone(JST).time()
                row["push_ok"] = bool(el["now"] in TL.PRICE_EXITS and at >= SELL_FROM and not pend.get(t) and not q.get("old"))
            except Exception as e:                            # noqa: BLE001
                row["status"] = f"算不了（{type(e).__name__}）"
        doc["holdings"].append(row)
    # 核心 ETF
    for t in core:
        q = quotes.get(t)
        units = int((bk.get("core_units") or {}).get(t) or 0)
        row = {"ticker": t, "label": NM.label(t), "units": units}
        if q:
            df, _ = _daily(t)
            pc = float(df["Close"].iloc[-1]) if df is not None and len(df) else None
            row.update(px=q["px"], at=q["at"], chg_pct=round((float(q["px"]) / pc - 1) * 100, 2) if pc else None)
        doc["core"].append(row)
    return doc


# ───────────────────────── 推送 ─────────────────────────
def _buy_text(r: dict, doc: dict) -> tuple[str, str]:
    lab = r["label"]
    head = f"暂定（{SRC}，数据 {_hm(r.get('at'))}）：{lab} 现价 {_px(r.get('px'))} 在规则的买点区间 {_px(r['lo'])}〜{_px(r['hi'])} 里，" \
           f"累计成交量 {int(r.get('v') or 0):,} 股 = 所需 {int(r.get('v_need') or 0):,} 股的 {float(r.get('v_pct') or 0):.0f}%。"
    if not (doc.get("gates") or {}).get("known"):
        mid = f"如果收在这里，规则明早 09:00 开盘会买（{(doc.get('gates') or {}).get('note') or '闸门未知'}；执行器照常处理，现在不需要操作）。"
    elif r.get("blocks"):
        mid = f"如果收在这里，规则会出买点，但现在被挡（{'；'.join(r['blocks'])}）→ 明早不会买（执行器照常处理，现在不需要操作）。"
    else:
        mid = "如果收在这里，规则明早 09:00 开盘会买（执行器照常处理，现在不需要操作）。"
    text = head + mid + NO_RESEARCH + "。" + ("（HALT 中：明早不会下单）" if doc.get("halt") else "")
    return f"盘中暂定买点：{lab}", text


def _sell_text(r: dict, doc: dict) -> tuple[str, str]:
    lab = r["label"]
    why = r.get("now_text") or str(r.get("now"))
    lv = next((x for x in r.get("levels") or [] if x.get("hit") and str(x.get("rule", "")).startswith(why)), None)
    line = f"「{why}」{_px(lv['px'])}" if lv else f"「{why}」"
    text = (f"暂定（{SRC}，数据 {_hm(r.get('at'))}）：持仓 {lab}（{int(r.get('shares') or 0):,} 股）现价 {_px(r.get('px'))}"
            f"（买价 {_px(r.get('entry_px'))}，{_pct(r.get('ret_pct'))}）已越过收盘卖出线 {line}。"
            "如果收在这里，规则明早 09:00 开盘会卖（执行器照常处理，现在不需要操作）。" + NO_RESEARCH + "。"
            + ("（HALT 中：明早不会下单）" if doc.get("halt") else ""))
    return f"盘中暂定卖点：{lab}", text


def push(doc: dict, tag: str, now: dt.datetime | None = None, prev: dict | None = None, send=None) -> list[dict]:
    """按结果推手机（qbreak 推送 + 通知记录）；返回这次推了的。设置关 / 不在时段 / 不是今天 / 数据过期或取不到 → 不推。
    同一只同一边一天一次（notify_seen + 结果文件里的记录，两道）、每个账本一天最多 CAP 条。就地把记录写进 doc["pushes"]。"""
    from . import notify_seen as NS
    now = _jst(now)
    today = now.date().isoformat()
    pv = (prev or {}).get("pushes") or {}
    sent = list(pv.get("sent") or []) if pv.get("date") == today else []
    doc["pushes"] = {"date": today, "sent": sent}
    if not settings()["push"] or doc.get("stale") or doc.get("error") or doc.get("day") != today or not in_window(now):
        return []
    if send is None:
        from .notify import send
    out = []
    want = [("buy", r, _buy_text) for r in doc.get("candidates") or [] if r.get("push_ok")]
    want += [("sell", r, _sell_text) for r in doc.get("holdings") or [] if r.get("push_ok")]
    for side, r, fn in want:
        if len(sent) >= CAP:
            break
        key = f"盘中|{NM.code(r['ticker'])}|{side}"
        if any(x.get("key") == key for x in sent) or not NS.first(f"intraday_{tag}", key, now):
            continue
        subject, text = fn(r, doc)
        try:
            send(subject, text, level="info")
        except Exception as e:                                # noqa: BLE001  notify.send 不抛；兜底
            log.warning("盘中观测的推送失败：%s", type(e).__name__)
        rec = {"key": key, "ticker": r["ticker"], "side": side, "at": now.isoformat(timespec="seconds")}
        sent.append(rec)
        out.append({**rec, "subject": subject, "text": text})
    return out


# ───────────────────────── 文字（终端 / 面板共用）─────────────────────────
def _gate_line(r: dict, doc: dict) -> str:
    """每只一行的闸门：只写这只自己的（所有票都挡的 / 闸门未知已在卡片顶上 ★ 写过一次，手机上不再每行重复）。"""
    g = doc.get("gates") or {}
    if not g.get("known"):
        return ""
    glob = {str(x) for x in g.get("global") or []}
    own = [b for b in r.get("blocks") or [] if str(b) not in glob]
    if own:
        return "闸门：" + "；".join(own)
    return "" if glob else "闸门：目前没有挡住的"


def _hold_line(r: dict) -> str:
    """持仓每只一行：每条收盘卖出线离现价多远；越过的写「若收盘仍在这里 → 规则明早开盘卖（理由）」。"""
    if r.get("queued"):
        return f"已排定开盘卖（{r.get('queued_text') or r['queued']}）"
    if r.get("px") is None:
        return f"盘中：{r.get('status') or '还没有今天的数据'}"
    parts = [f"盘中（暂定，数据 {_hm(r.get('at'))}，{LAG}）：现价 {_px(r['px'])}（买价起 {_pct(r.get('ret_pct'))}）"]
    hit = False
    for lv in r.get("levels") or []:
        rule = str(lv.get("rule") or "").split("（持有以来")[0]
        if lv.get("hit"):
            hit = True
            parts.append(f"{rule} {_px(lv['px'])}：若收盘仍在这里 → 规则明早开盘卖（{rule}）")
        else:
            parts.append(f"{rule} {_px(lv['px'])}（{_pct(lv.get('dist_pct'))}）")
    q = r.get("now")
    if q and not hit:
        parts.append(f"若收盘仍在这里 → 规则明早开盘卖（{r.get('now_text') or q}）")
    elif not q and not hit:
        parts.append("收盘仍在这里：规则不卖")
    return " · ".join(parts)


def view(doc: dict | None, now: dt.datetime | None = None) -> dict:
    """面板的卡片 / 持仓的一行（服务器先画一份，static/intraday.js 按 /api/intraday 重画同一个样子）。只读、不取价。"""
    now = _jst(now)
    v = {"ok": True, "title": TITLE, "foot": FOOT, "head": "", "warn": [], "rows": [], "none": "", "impossible": "",
         "groups": [], "core": [], "hold": {}, "live": in_window(now)}
    day = target_day(now)
    if not doc:
        v["head"] = "还没有盘中观测：交易日 08:55〜11:35、12:25〜16:30 操作面板每 5 分钟算一次（Mac 睡着时暂停）"
        return v
    if doc.get("day") != day.isoformat():
        v["head"] = f"今天的还没开始（上一次是 {doc.get('day') or '—'}）：交易日 08:55 起每 5 分钟（Mac 睡着时暂停）"
        return v
    h = f"数据 {_hm(doc.get('data_at'))}（{LAG}）· 上次计算 {_hm(doc.get('updated'))}"
    if doc.get("stale"):
        h += f" · ★ 数据过期{'' if doc.get('age_min') is None else ' ' + str(doc['age_min']) + ' 分钟'}（不推送）"
    if doc.get("error"):
        h += f" · ★ {doc['error']}"
    if not settings()["push"]:
        h += " · 手机推送：关"
    v["head"] = h
    if doc.get("halt"):
        v["warn"].append("HALT 中：明早不会下单")
    g = doc.get("gates") or {}
    if not g.get("known"):
        v["warn"].append(g.get("note") or "闸门未知")
    v["warn"] += [str(x) for x in g.get("global") or []]
    if doc.get("daily_note"):
        v["warn"].append(doc["daily_note"])
    for r in doc.get("candidates") or []:
        line = f"区间 {_px(r['lo'])}〜{_px(r['hi'])}" + ("（涨停也在区间里）" if r.get("hi_open") else "")
        if r.get("px") is not None:
            line += f" · 现价 {_px(r['px'])}（离下沿 {_pct(r.get('dist_lo_pct'))}）"
            line += f" · 成交量 {float(r['v_pct']):.0f}%（所需 {int(r.get('v_need') or 0):,} 股）" if r.get("v_pct") is not None else ""
        if r.get("kind") == "shape" and r.get("fails"):
            line += " · 没过：" + "；".join(r["fails"])
        v["rows"].append({"t": r["ticker"], "label": r["label"], "kind": r.get("kind"), "status": r.get("status"), "line": line,
                          "gates": _gate_line(r, doc),
                          "at": f"数据 {_hm(r.get('at'))}" if r.get("at") and _hm(r.get("at")) != _hm(doc.get("data_at")) else ""})   # 与顶上的数据时刻一样 → 不重复
    imp = doc.get("impossible") or []
    n_imp = sum(len(x["tickers"]) for x in imp)
    if not v["rows"]:
        v["none"] = f"今天收盘可能出买点的：0 只（股票池 {int(doc.get('pool_n') or 0)} 只）"
    if n_imp:
        v["impossible"] = f"今天不可能：{n_imp} 只（" + " · ".join(f"{x['why']} {len(x['tickers'])}" for x in imp) + "）"
        v["groups"] = [{"why": x["why"], "names": NM.labels(x["tickers"], limit=40)} for x in imp]
    for r in doc.get("core") or []:
        s = f"{r['label']}：" + (f"现价 {_px(r['px'])}（今天 {_pct(r.get('chg_pct'), 2)}）" if r.get("px") is not None else "还没有今天的数据")
        s += f" · 拿着 {int(r['units']):,} 口" if r.get("units") else " · 没拿"
        v["core"].append(s)
    for r in doc.get("holdings") or []:
        v["hold"][r["ticker"]] = _hold_line(r)
    return v


def text(doc: dict | None, now: dt.datetime | None = None, tag: str = "paper") -> str:
    """终端（run.py intraday / --dry）用的几行。"""
    v = view(doc, now)
    out = [f"盘中观测（{tag}）：{TITLE}", f"  {v['head']}"]
    out += [f"  ★ {w}" for w in v["warn"]]
    for r in v["rows"]:
        out.append(f"  - {r['label']}：{r['status']}")
        out.append(f"      {r['line']}")
        if r["gates"] or r.get("at"):
            out.append("      " + " · ".join(x for x in (r["gates"], r.get("at")) if x))
    if v["none"]:
        out.append(f"  {v['none']}")
    if v["impossible"]:
        out.append(f"  {v['impossible']}")
    if doc and doc.get("holdings"):
        out.append("  持仓（收盘卖出线）：")
        out += [f"  - {r['label']}：{v['hold'].get(r['ticker'], '')}" for r in doc["holdings"]]
    if v["core"]:
        out.append("  核心 ETF：")
        out += [f"  - {c}" for c in v["core"]]
    pz = ((doc or {}).get("pushes") or {}).get("sent") or []
    if pz:
        out.append(f"  今天推过 {len(pz)} 条：" + "、".join(f"{NM.label(x['ticker'])}（{'买' if x['side'] == 'buy' else '卖'}）" for x in pz))
    out.append(f"  手机推送：{'开' if settings()['push'] else '关'}（bash scripts/liveu.sh intraday push on|off）")
    out.append(f"  {FOOT}")
    return "\n".join(out)


def status_line(tag: str, now: dt.datetime | None = None) -> dict | None:
    """mac_status 的「盘中观测」一行：最后一次是什么时候、出没出错（没有结果文件 → None）。"""
    doc = load(tag)
    if not doc:
        return None
    now = _jst(now)
    upd = doc.get("updated")
    try:
        age = (now - dt.datetime.fromisoformat(upd)).total_seconds() / 60
    except (TypeError, ValueError):
        age = None
    try:
        md = dt.datetime.fromisoformat(str(upd)).astimezone(JST).strftime("%m-%d")
    except (TypeError, ValueError):
        md = "—"
    last = f"最后一次 {md} {_hm(upd)}（{str(doc.get('day') or '')[5:]} 的盘，数据 {_hm(doc.get('data_at'))}，{LAG}）"
    if doc.get("error"):
        return {"level": "warn", "text": f"{last}；出错：{doc['error']}"}
    if in_window(now) and (age is None or age > 15):
        return {"level": "warn", "text": f"{last}；交易时段里超过 15 分钟没更新（面板没在跑 / Mac 睡着？）"}
    return {"level": "ok", "text": last + ("；★ 数据过期" if doc.get("stale") else "")}


# ───────────────────────── 运行 ─────────────────────────
def run_once(tag: str, now: dt.datetime | None = None, dry: bool = False, fetch=None, send=None) -> dict:
    """算一次；dry = 只算（不写结果、不推送）。"""
    now = _jst(now)
    prev = load(tag)
    doc = evaluate(tag, now, fetch=fetch, prev=prev)
    if dry:
        doc["pushes"] = (prev or {}).get("pushes") if (prev or {}).get("day") == doc["day"] else None
        return doc
    pushed = push(doc, tag, now, prev=prev, send=send)
    atomic_write_text(out_path(tag), json.dumps(doc, ensure_ascii=False, default=str))
    for x in pushed:
        log.info("推送：%s", x["subject"])
    return doc


def _lock(tag: str):
    """同一个账本同时只跑一个（面板平滑重启时旧的那次可能还没跑完）；拿不到 → None。"""
    import fcntl
    p = paths.out_dir() / f"intraday_{tag}.lock"
    f = open(p, "a+", encoding="utf-8")                        # noqa: SIM115
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m qbreak.intraday_watch", description="盘中观测：规则的暂定买卖点（约晚 20 分钟；只展示）")
    ap.add_argument("--book", default="paper", help="账本：paper（模拟账户）/ tachibana（立花本番）")
    ap.add_argument("--dry", action="store_true", help="现在算一次、只打印（不写结果、不推送）")
    a = ap.parse_args(argv)
    if not _TAG.fullmatch(a.book):
        print(f"账本名不对：{a.book}")
        return 2
    if a.book.startswith("tachibana") and paths.inside_repo() and not a.dry:
        print("立花的盘中观测结果只写 Mac 的数据目录（QBREAK_HOME=~/.qbreak/home）：数据目录在仓库里 → 不运行（公开仓库）")
        return 2
    now = now_jst()
    if a.dry:
        doc = run_once(a.book, now, dry=True)
        print(text(doc, now, a.book))
        return 0
    lk = _lock(a.book)
    if lk is None:
        print(f"{now:%H:%M:%S} {a.book}：上一次还在跑 → 这次跳过")
        return 0
    try:
        doc = run_once(a.book, now)
    except Exception as e:                                     # noqa: BLE001  记下来（mac_status 显示），不让面板的线程停
        log.exception("盘中观测失败")
        prev = load(a.book) or {}
        prev.update(updated=now.isoformat(timespec="seconds"), error=f"{type(e).__name__}: {e}"[:200])
        try:
            atomic_write_text(out_path(a.book), json.dumps(prev, ensure_ascii=False, default=str))
        except Exception:                                     # noqa: BLE001
            pass
        print(f"{now:%H:%M:%S} {a.book}：出错 {type(e).__name__}: {e}")
        return 1
    finally:
        lk.close()
    n_ok = sum(1 for r in doc["candidates"] if r.get("kind") == "ok")
    print(f"{now:%H:%M:%S} {a.book}：数据 {_hm(doc.get('data_at'))}（{LAG}）· 可能出买点 {len(doc['candidates'])} 只（暂定成立 {n_ok}）"
          f" · 持仓 {len(doc['holdings'])} 只" + (f" · ★ {doc['error']}" if doc.get("error") else "") + (" · 数据过期" if doc.get("stale") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
