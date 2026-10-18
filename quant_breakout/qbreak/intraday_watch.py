"""intraday_watch.py — 盘中观测：持仓的收盘卖出线（约晚 20 分钟；2026-10-16 用户要求；只展示 + 手机提醒，不下单、不改规则）。

2026-10-18 用户：「今天盘中规则的买点 感觉没什么用 不需要这个功能 删了吧」→ 买点那一半（选股页「今天盘中：规则的买点」卡片、
股票池 225 只的买点区间、暂定买点的推送）删掉；留下持仓的这一半：现行日线规则「如果今天就收在现价」，持仓的每条收盘卖出线离现价多远、
越过了 → 若收盘仍在这里，规则明早 09:00 开盘卖（执行器照常卖）。暂定：收盘前价格还会变；以明早 07:40 执行器的决策为准。
分钟 K 线研究（scripts/minute_study.py；var/sim_changes.md 2026-10-15）：日内规则扣成本后都亏 → 不加日内规则。

怎么跑：操作面板（qbreak/panel.py serve）里的一个线程：交易日（含临时休市）08:55〜11:35、12:25〜16:30 每 5 分钟叫一次
  python -m qbreak.intraday_watch --book <账本>（模拟账户；有立花本番账本时也跑立花）；Mac 睡着 / 面板没开 → 不跑（没有单独的 LaunchAgent）。
  看结果：bash scripts/liveu.sh intraday（读最近一次的结果，只读）；--dry = 现在算一次、只打印（不写、不推送）。
一次做什么：
  ① 盯的票 = 持仓 + 核心 ETF；日线 = 数据目录 cache/ 里执行器早上取好的（这里不取日线、不写缓存）；Yahoo 1 分钟线
     （qbreak/data.intraday_quotes；约晚 20 分钟；不连立花）；取不到 → 留着上一次的、标「过期」；
  ② 持仓：每条收盘卖出线离现价多远（timeline.exit_lines；越过 = 若收盘仍在这里 → 规则明早开盘卖）；核心 ETF：现价与今天的涨跌；
  ③ 写 out/intraday_<账本>.json（原子写；数据时刻、「约晚 20 分钟」）；
  ④ 手机推送（qbreak/notify.send = qbreak 推送 + 通知记录；设置：数据目录 intraday.json {"push": true}，
     bash scripts/liveu.sh intraday push on|off）：持仓、数据时刻 ≥ 14:10、越过一条收盘卖出线（止损 / 跟踪止损 / 止盈 / 吊灯 / 死叉）
     且规则判卖；同一只一天一次（qbreak/notify_seen，键不含价格）、每个账本一天最多 5 条；数据过期（> 30 分钟）/ 取不到 → 不推；
     HALT 中写明「明早不会下单」。
不做：不下单、不写手动指令、不改账本 / 规则 / 参数 / 股票池。代码一律带名字（qbreak/names.py）。非投资建议。
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
from .calendar_jp import JST, is_trading_day, next_trading_day, now_jst, prev_trading_day
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
AM_END, PM_START, CLOSE = dt.time(11, 30), dt.time(12, 30), dt.time(15, 30)
SETTINGS = "intraday.json"
LOG_NAME = "com.qbreak.panel.intraday.log"
FOOT = "暂定：以下一次执行器的决策（交易日 07:40）为准；非投资建议"
NO_RESEARCH = "盘中手动买卖没有研究支持（分钟 K 线研究 2026-10-15：日内规则扣成本后都亏）"
_TAG = re.compile(r"[a-z][a-z0-9_]{0,31}")


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


def next_word(day: dt.date | str | None) -> str:
    """看的这天收盘之后，执行器下一次决策 / 开盘是哪天：明天 →「明早」；周五 / 连休前 →「下个交易日 10/19（周一）」
    （2026-10-16 周五实测写成「明早」：下一次决策其实是周一）。"""
    try:
        d = dt.date.fromisoformat(day) if isinstance(day, str) else day
        nd = next_trading_day(d)
    except (TypeError, ValueError):
        return "下一个交易日"
    if nd == d + dt.timedelta(days=1):
        return "明早"
    return f"下个交易日 {nd.month}/{nd.day}（周{'一二三四五六日'[nd.weekday()]}）"


def _at(word: str, hm: str) -> str:
    """「明早 09:00」/「下个交易日 10/19（周一）09:00」。"""
    return f"{word}{'' if word.endswith('）') else ' '}{hm}"


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


# ───────────────────────── 输入：参数、日线 ─────────────────────────
def _sim() -> dict:
    return peek_json(paths.home() / "sim.json") or {}


def _params(sim: dict):
    """离场用的参数：与执行器同一个 load_params + 离场方式（var/sim.json 的 exits；只改离场字段）。"""
    from . import exit_rules as EXR
    from .trader import load_params
    return EXR.apply(load_params(None, "JP"), EXR.mode_of(sim, "JP"))


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
    p_out = _params(sim)
    from .live_ops import held_now                            # 函数里 import（live_ops 在函数里 import 本模块的 next_word；不循环）
    pj = held_now(peek_json(paths.state_dir() / f"live_unified_{tag}.json") or {}, tag, now=now)
    bk = pj["state"]                                          # 含今天已成交（对账前；卖光的不再出现、今天买进的个股没有离场线；2026-10-16）
    doc: dict = {"version": VERSION, "book": tag, "day": day.isoformat(), "updated": now.isoformat(timespec="seconds"),
                 "src": SRC, "lag": LAG, "error": "", "stale": False, "age_min": None, "data_at": None,
                 "halt": paths.halt_file().exists(), "holdings": [], "core": []}
    if frames is not None:                                    # 测试：直接给日线
        def _daily(t):
            df = frames.get(t)
            return (df.loc[df.index < pd.Timestamp(day)], None) if df is not None else (None, "没有日线")
    else:
        def _daily(t):
            return daily(t, day)
    held = dict(bk.get("pos") or {})
    pend = dict(bk.get("pending_exit") or {})
    core = _core_set(sim, bk)
    watch = sorted(set(held) | set(core))
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
    # 持仓
    for t, ps in sorted(held.items()):
        row = {"ticker": t, "label": NM.label(t), "shares": int(ps.get("shares") or 0), "entry_px": ps.get("entry_px"),
               "queued": pend.get(t), "queued_text": TL.REASON.get(pend[t], str(pend[t])) if pend.get(t) else None, "push_ok": False}
        q = quotes.get(t)
        df, why = _daily(t)
        if ps.get("today") or ps.get("stop_px") is None:     # 今天买进（对账前）：止损价、离场线在对账之后的决策才有 → 不算、不推送
            w_ = pj.get("when_sp") or (pj.get("when") or "下一次执行器运行")   # 「在下个交易日 10/19（周一）07:40 的决策」/「在下一次执行器运行的决策」（复核：以前多空格）
            row.update(today=True, status=f"{pj.get('day_word') or '今天'}买进（对账前）：离场线在{w_}的决策之后才有")
            if q:
                row.update(px=q.get("px"), at=q.get("at"))
            doc["holdings"].append(row)
            continue
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
def _sell_text(r: dict, doc: dict) -> tuple[str, str]:
    lab, nx = r["label"], next_word(doc.get("day"))
    why = r.get("now_text") or str(r.get("now"))
    lv = next((x for x in r.get("levels") or [] if x.get("hit") and str(x.get("rule", "")).startswith(why)), None)
    line = f"「{why}」{_px(lv['px'])}" if lv else f"「{why}」"
    text = (f"暂定（{SRC}，数据 {_hm(r.get('at'))}）：持仓 {lab}（{int(r.get('shares') or 0):,} 股）现价 {_px(r.get('px'))}"
            f"（买价 {_px(r.get('entry_px'))}，{_pct(r.get('ret_pct'))}）已越过收盘卖出线 {line}。"
            f"如果收在这里，规则{_at(nx, '09:00')} 开盘会卖（执行器照常处理，现在不需要操作）。" + NO_RESEARCH + "。"
            + (f"（HALT 中：{nx}不会下单）" if doc.get("halt") else ""))
    return f"盘中暂定卖点：{lab}", text


def push(doc: dict, tag: str, now: dt.datetime | None = None, prev: dict | None = None, send=None) -> list[dict]:
    """按结果推手机（qbreak 推送 + 通知记录）；返回这次推了的。设置关 / 不在时段 / 不是今天 / 数据过期或取不到 → 不推。
    同一只一天一次（notify_seen + 结果文件里的记录，两道）、每个账本一天最多 CAP 条。就地把记录写进 doc["pushes"]。"""
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
    want = [("sell", r, _sell_text) for r in doc.get("holdings") or [] if r.get("push_ok")]
    for side, r, fn in want:
        if len(sent) >= CAP:
            break
        key = f"盘中|{NM.code(r['ticker'])}|{side}"
        if any(x.get("key") == key for x in sent) or not NS.first(f"intraday_{tag}", key, now):
            continue
        subject, text = fn(r, doc)
        try:
            from .notify import book_scope
            with book_scope(tag):                             # 这个账本的通知记录（2026-10-19）
                send(subject, text, level="info")
        except Exception as e:                                # noqa: BLE001  notify.send 不抛；兜底
            log.warning("盘中观测的推送失败：%s", type(e).__name__)
        rec = {"key": key, "ticker": r["ticker"], "side": side, "at": now.isoformat(timespec="seconds")}
        sent.append(rec)
        out.append({**rec, "subject": subject, "text": text})
    return out


# ───────────────────────── 文字（终端 / 面板共用）─────────────────────────
def _hold_line(r: dict, nx: str = "明早") -> str:
    """持仓每只一行：每条收盘卖出线离现价多远；越过的写「若收盘仍在这里 → 规则明早开盘卖（理由）」（nx：next_word，周五 → 下个交易日）。"""
    if r.get("queued"):
        return f"已排定开盘卖（{r.get('queued_text') or r['queued']}）"
    if r.get("today"):                                        # 今天买进（对账前）：没有离场线（2026-10-16）
        return f"盘中：{r.get('status')}" + (f"（现价 {_px(r['px'])}，数据 {_hm(r.get('at'))}）" if r.get("px") is not None else "")
    if r.get("px") is None:
        return f"盘中：{r.get('status') or '还没有今天的数据'}"
    parts = [f"盘中（暂定，数据 {_hm(r.get('at'))}，{LAG}）：现价 {_px(r['px'])}（买价起 {_pct(r.get('ret_pct'))}）"]
    hit = False
    for lv in r.get("levels") or []:
        rule = str(lv.get("rule") or "").split("（持有以来")[0]
        if lv.get("hit"):
            hit = True
            parts.append(f"{rule} {_px(lv['px'])}：若收盘仍在这里 → 规则{nx}开盘卖（{rule}）")
        else:
            parts.append(f"{rule} {_px(lv['px'])}（{_pct(lv.get('dist_pct'))}）")
    q = r.get("now")
    if q and not hit:
        parts.append(f"若收盘仍在这里 → 规则{nx}开盘卖（{r.get('now_text') or q}）")
    elif not q and not hit:
        parts.append("收盘仍在这里：规则不卖")
    return " · ".join(parts)


def view(doc: dict | None, now: dt.datetime | None = None) -> dict:
    """持仓每只一行（服务器先画一份，static/intraday.js 按 /api/intraday 更新文字）+ 终端的几行。只读、不取价。"""
    now = _jst(now)
    v = {"ok": True, "head": "", "warn": [], "core": [], "hold": {}, "live": in_window(now)}
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
        v["warn"].append(f"HALT 中：{next_word(day)}不会下单")
    for r in doc.get("core") or []:
        s = f"{r['label']}：" + (f"现价 {_px(r['px'])}（今天 {_pct(r.get('chg_pct'), 2)}）" if r.get("px") is not None else "还没有今天的数据")
        s += f" · 拿着 {int(r['units']):,} 口" if r.get("units") else " · 没拿"
        v["core"].append(s)
    for r in doc.get("holdings") or []:
        v["hold"][r["ticker"]] = _hold_line(r, next_word(day))
    return v


def text(doc: dict | None, now: dt.datetime | None = None, tag: str = "paper") -> str:
    """终端（run.py intraday / --dry）用的几行。"""
    v = view(doc, now)
    out = [f"盘中观测（{tag}）：持仓的收盘卖出线（暂定，{LAG}）", f"  {v['head']}"]
    out += [f"  ★ {w}" for w in v["warn"]]
    if doc and doc.get("holdings"):
        out.append("  持仓（收盘卖出线）：")
        out += [f"  - {r['label']}：{v['hold'].get(r['ticker'], '')}" for r in doc["holdings"]]
    elif doc:
        out.append("  没有持仓的个股")
    if v["core"]:
        out.append("  核心 ETF：")
        out += [f"  - {c}" for c in v["core"]]
    pz = ((doc or {}).get("pushes") or {}).get("sent") or []
    if pz:
        out.append(f"  今天推过 {len(pz)} 条：" + "、".join(f"{NM.label(x['ticker'])}（卖）" for x in pz))
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
    ap = argparse.ArgumentParser(prog="python -m qbreak.intraday_watch", description="盘中观测：持仓的收盘卖出线（约晚 20 分钟；只展示）")
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
    print(f"{now:%H:%M:%S} {a.book}：数据 {_hm(doc.get('data_at'))}（{LAG}）· 持仓 {len(doc['holdings'])} 只" + (f" · ★ {doc['error']}" if doc.get("error") else "") + (" · 数据过期" if doc.get("stale") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
