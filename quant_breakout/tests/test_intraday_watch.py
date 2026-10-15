"""盘中观测（qbreak/intraday_watch.py + timeline 的盘中小函数 + 面板的线程 / 接口；2026-10-16 用户要求；只展示）：
暂定买点 = 引擎同一个 compute_indicators 的 entry（真引擎逐日走、次日开盘买不买与暂定一致）；暂定卖点 = 引擎的离场顺序；
时段（午休、休市日、临时休市）；数据过期 / 取不到 → 不推送；同一只同一边一天一次、每天最多 5 条；推送文字（暂定、执行器、
没有「建议」、HALT）；代码都带名字；面板接口只读结果文件（请求里不取价）、线程可以关掉。不连网（取价用注入的函数）。"""
import datetime as dt
import json
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import calendar_jp as CJ                                         # noqa: E402
from qbreak import exit_rules as EXR                                         # noqa: E402
from qbreak import intraday_watch as IW                                      # noqa: E402
from qbreak import panel, paths                                              # noqa: E402
from qbreak import timeline as TL                                            # noqa: E402
from qbreak.calendar_jp import JST                                           # noqa: E402
from qbreak.config import StrategyParams                                     # noqa: E402
from qbreak.strategy import compute_indicators                               # noqa: E402
from qbreak.unified import UnifiedEngine                                     # noqa: E402

from test_live_unified import CC, CFG, EX                                    # noqa: E402
from test_timeline import _core, _days, _open_position, _walk                # noqa: E402

DAY = dt.date(2026, 10, 16)                                                  # 周五、交易日
AT = dt.datetime(2026, 10, 16, 14, 40, tzinfo=JST)


# ───────────────────────── 暂定 = 引擎 ─────────────────────────
def _engine_buys(frame, p, s1) -> bool:
    """真引擎逐日走：只留 s1 那天自己算出来的 entry（之前的信号清掉，免得别的持仓占着），s2 开盘有没有买进。"""
    ind = compute_indicators(frame, p)
    ind.loc[ind.index != pd.Timestamp(s1), "entry"] = False
    e = UnifiedEngine({"A.T": ind, "1655.T": _core(frame.index)}, CFG, {"JP": p, "US": p}, EX, CC,
                      bear={"US": pd.Series(False, index=frame.index)})
    e.prime(5)
    for i in range(5, len(frame.index)):
        e.step(i)
    return "A.T" in e.st.pos


@pytest.mark.parametrize("seed", [5, 6])
def test_provisional_entry_equals_engine(seed):
    p = StrategyParams()
    base = _walk(seed, n=300, drift=0.0, vol=0.007)
    s1, s2 = _days(base, 2)
    bt = TL.buy_trigger(base, p, s1)
    lo, hi, v = bt["lo"], bt["hi"], bt["v_need"]
    prev = float(base["Close"].iloc[-1])
    seen = set()
    for x, vol in (((lo + hi) / 2, v), (lo * (1 + 1e-4), v), (lo * (1 - 1e-3), v), ((lo + hi) / 2, v - 1)):
        bar = {"o": prev, "h": max(prev, x), "l": min(prev, x), "c": x, "v": vol}          # 与 with_bars 同样的假设 K 线
        mine = TL.provisional_entry(base, p, bar, s1)
        full = TL.with_bars(base, [s1, s2], [x, x], [vol, vol])
        assert mine["entry"] == bool(compute_indicators(full.iloc[:-1], p)["entry"].iloc[-1]) == _engine_buys(full, p, s1)
        assert mine["entry"] or mine["fails"]
        seen.add(mine["entry"])
    assert seen == {True, False}                                                      # 区间里成立、区间外 / 少一股不成立


def test_live_frame_with_shadows_is_the_same_bar_the_engine_sees():
    """有影线、开盘不等于前收的真实一根：live_frame = 日线 + 那一根（同一个 compute_indicators 的每一列都一样）。"""
    p = StrategyParams()
    base = _walk(9, n=300, drift=0.0, vol=0.007)
    s1 = _days(base, 1)[0]
    bar = {"o": 1003.0, "h": 1021.0, "l": 998.5, "c": 1012.0, "v": 2.4e6}
    fr = TL.live_frame(pd.concat([base, pd.DataFrame([{"Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 1}],
                                                     index=[pd.Timestamp(s1)])]), bar, s1)    # 缓存里混进当天的一根也会被去掉
    full = pd.concat([TL._tail(base), pd.DataFrame([{"Open": 1003.0, "High": 1021.0, "Low": 998.5, "Close": 1012.0, "Volume": 2.4e6}],
                                                   index=pd.DatetimeIndex([pd.Timestamp(s1)]))])
    a, b = compute_indicators(fr, p).iloc[-1], compute_indicators(full, p).iloc[-1]
    for k in ("entry", "is_range", "golden_cross", "near_zero", "vol_surge", "upper_shadow_ratio", "macd", "macd_sig"):
        assert (a[k] == b[k]) or (pd.isna(a[k]) and pd.isna(b[k])), k
    assert TL.provisional_entry(base, p, bar, s1)["entry"] == bool(b["entry"])


@pytest.mark.parametrize("mode,seed,off", [("DC", 7, 8), ("X6", 3, 15), ("DC", 3, 8)])
def test_exit_lines_now_equals_engine(mode, seed, off):
    """持仓：「如果今天收在现价」规则判不判卖、为什么 = 真引擎当天收盘的判定（次日开盘卖）。越过最高的那条下行线 → 判卖。"""
    from test_timeline import _engine_exit
    p = EXR.apply(StrategyParams(exit_on_climax=True), mode)
    base, sig, pos = _open_position(seed, p, off)
    days = _days(base, 3)
    vol = float(base["Volume"].tail(p.vol_ma_n).mean())
    c0 = float(base["Close"].iloc[-1])
    sl = TL.sell_levels(base, p, pos, days)
    for x in (sl["first_down"]["px"] * (1 - 2e-4), sl["first_down"]["px"] * (1 + 2e-4), c0):
        bar = {"o": c0, "h": max(c0, x), "l": min(c0, x), "c": x, "v": vol}
        el = TL.exit_lines(base, p, pos, bar, days[0])
        eng = _engine_exit(base, p, sig, days, [x, x], vol)
        got = (days[1].isoformat(), el["now"]) if el["now"] else None
        assert got == (eng if eng and eng[0] == days[1].isoformat() else None)
        assert el["sell_day"] == days[1].isoformat()
        hit = [lv for lv in el["levels"] if lv["hit"]]
        assert bool(hit) == (x < sl["first_down"]["px"] or x >= [lv for lv in sl["levels"] if lv["side"] == "up"][0]["px"])


def test_scenario_exit_still_uses_the_same_order():
    """scenario_exit 改成调 exit_reason_at 之后照旧：exit_reason_at 一根一根判 = scenario_exit 的结果。"""
    p = EXR.apply(StrategyParams(exit_on_climax=True, max_hold_days=20), "X6")
    base, _, pos = _open_position(3, p, 15)
    days = _days(base, 12)
    sc = TL.scenario_exit(base, p, pos, days, 0.0)
    assert sc and sc["reason"] == TL.REASON["max_hold"]
    st = TL._pos_state(pos)
    st["hold"] = 19
    r = pd.Series({"High": pos["entry_px"], "Close": pos["entry_px"], "atr": np.nan, "climax": False, "dead_cross": False})
    assert TL.exit_reason_at(r, st, p) == "max_hold" and st["hold"] == 20


# ───────────────────────── 时段 ─────────────────────────
def test_window_gating_lunch_closed_days_and_extra_closed(monkeypatch):
    def at(d, h, m):
        return dt.datetime.combine(d, dt.time(h, m), tzinfo=JST)
    ok = [(8, 55), (9, 0), (11, 34), (12, 25), (15, 30), (16, 29)]
    ng = [(8, 54), (11, 35), (12, 0), (12, 24), (16, 30), (20, 0)]
    assert all(IW.in_window(at(DAY, h, m)) for h, m in ok)
    assert not any(IW.in_window(at(DAY, h, m)) for h, m in ng)
    assert not IW.in_window(at(dt.date(2026, 10, 17), 10, 0))                     # 土曜
    assert not IW.in_window(at(dt.date(2026, 11, 3), 10, 0))                      # 文化の日
    (paths.home() / "extra_closed.json").write_text(json.dumps({"dates": ["2026-10-16"], "note": "测试"}), encoding="utf-8")
    CJ.reload_extra_closed()
    try:
        assert not IW.in_window(at(DAY, 10, 0))                                   # 临时休市
    finally:
        (paths.home() / "extra_closed.json").unlink()
        CJ.reload_extra_closed()
    assert IW.target_day(at(DAY, 10, 0)) == DAY
    assert IW.target_day(at(DAY, 2, 30)) == dt.date(2026, 10, 15)                  # 开盘前：看昨天的盘
    assert IW.target_day(at(dt.date(2026, 10, 18), 10, 0)) == DAY                 # 周日：看周五的盘


def test_panel_tick_runs_only_in_window_and_every_5_minutes(monkeypatch):
    ran = []
    monkeypatch.setattr(panel, "_intraday_books", lambda: ["paper", "tachibana"])
    last: dict = {}
    assert panel._intraday_tick(dt.datetime(2026, 10, 16, 12, 0, tzinfo=JST), last, run=ran.append) == []   # 午休
    assert panel._intraday_tick(dt.datetime(2026, 10, 17, 10, 0, tzinfo=JST), last, run=ran.append) == []   # 土曜
    assert ran == []
    assert panel._intraday_tick(dt.datetime(2026, 10, 16, 10, 0, tzinfo=JST), last, run=ran.append) == ["paper", "tachibana"]
    assert panel._intraday_tick(dt.datetime(2026, 10, 16, 10, 1, tzinfo=JST), last, run=ran.append) == []   # 不到 5 分钟
    last["paper"] -= IW.EVERY_S
    assert panel._intraday_tick(dt.datetime(2026, 10, 16, 10, 5, tzinfo=JST), last, run=ran.append) == ["paper"]
    assert ran == ["paper", "tachibana", "paper"]                                  # 一个接一个（不重叠）
    IW.out_path("paper").write_text(json.dumps({"updated": "2026-10-16T10:04:00+09:00"}), encoding="utf-8")
    assert not panel._intraday_due("paper", dt.datetime(2026, 10, 16, 10, 6, tzinfo=JST), {})    # 平滑重启后：刚算过的不马上再算
    assert panel._intraday_due("paper", dt.datetime(2026, 10, 16, 10, 9, tzinfo=JST), {})


# ───────────────────────── 一次：候补、持仓、推送 ─────────────────────────
def _tse_index(n, end=dt.date(2026, 10, 15)):
    out = [end]
    while len(out) < n:
        out.append(CJ.prev_trading_day(out[-1]))
    return pd.DatetimeIndex([pd.Timestamp(d) for d in reversed(out)])


def _frame(seed, p0=1000.0):
    b = _walk(seed, n=300, drift=0.0, vol=0.007, p0=p0)
    b.index = _tse_index(300)
    return b


POOL = ["7203.T", "9984.T", "8306.T"]


def _setup(monkeypatch, halt=False, mult=1.0, decided="2026-10-15"):
    """股票池 3 只（7203 / 9984 有区间、8306 横盘不成立）、持仓 6758（买价 = 昨收、止损 −7%）、核心 1545（拿着）+ 1655（规则的）；
    执行器的汇总是今天早上的。"""
    frames = {"7203.T": _frame(5), "9984.T": _frame(6), "8306.T": _frame(2), "6758.T": _frame(7), "1545.T": _frame(8, p0=250.0),
              "1655.T": _frame(9, p0=700.0)}
    monkeypatch.setattr(IW, "_pool", lambda sim: list(POOL))
    monkeypatch.setattr(IW, "daily", lambda t, day: ((frames[t].loc[frames[t].index < pd.Timestamp(day)], None) if t in frames
                                                     else (None, "没有日线缓存")))     # 数据目录的日线缓存 → 这里的假日线
    c6758 = float(frames["6758.T"]["Close"].iloc[-1])
    st = {"pos": {"6758.T": {"ticker": "6758.T", "shares": 100, "entry_px": c6758, "entry_date": "2026-10-08", "stop_px": c6758 * 0.93,
                             "peak": c6758, "hold": 5, "armed": False, "last_close": c6758}},
          "core_units": {"1545.T": 100}, "pending_exit": {}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps({"state": st}), encoding="utf-8")
    live = {"decided_on": decided, "equity_jpy": 1_000_000, "new_pos": {"markets": {"JP": {"mult": mult, "why": [["风险报告「避险」", 0.0]]}},
                                                                       "position_pct": 0.25, "max_positions": 4},
            "eligibility": {"blocked": [{"code": "9984", "why": "测试挡住"}]}, "suggest": {"rows": []}}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(live), encoding="utf-8")
    if halt:
        paths.halt_file().write_text("test", encoding="utf-8")
    return frames, c6758


def _fetcher(frames, bands, at="2026-10-16T14:20+09:00", sell_px=None, calls=None):
    """7203 收在区间中间、量刚好够；9984 价在区间、量差一半；6758 = sell_px（默认持平）；1545 +1%。"""
    def f(ts):
        if calls is not None:
            calls.append(sorted(ts))
        out = {}
        for t in ts:
            prev = float(frames[t]["Close"].iloc[-1])
            if t in bands:
                b = bands[t]
                x = (b["lo"] + b["hi"]) / 2
                v = b["v_need"] if t == "7203.T" else b["v_need"] / 2
            elif t == "6758.T":
                x, v = (sell_px or prev), 1e6
            else:
                x, v = prev * 1.01, 1e5
            out[t] = {"px": x, "at": at, "bar": {"d": DAY.isoformat(), "o": prev, "h": max(prev, x), "l": min(prev, x), "c": x, "v": v}}
        return out
    return f


def _bands(frames):
    p = StrategyParams()
    return {t: TL.buy_trigger(frames[t].loc[frames[t].index < pd.Timestamp(DAY)], p, DAY) for t in ("7203.T", "9984.T")}


def test_evaluate_candidates_holdings_gates_and_names(monkeypatch):
    frames, c0 = _setup(monkeypatch)
    calls = []
    doc = IW.evaluate("paper", AT, fetch=_fetcher(frames, _bands(frames), calls=calls), frames=frames)
    assert calls == [["1545.T", "1655.T", "6758.T", "7203.T", "9984.T"]]                       # 盯的票 = 可能出买点的 + 持仓 + 核心 ETF（不扫全部）
    c = {r["ticker"]: r for r in doc["candidates"]}
    assert set(c) == {"7203.T", "9984.T"} and c["7203.T"]["kind"] == "ok" and c["7203.T"]["push_ok"]
    assert c["9984.T"]["kind"] == "vol" and c["9984.T"]["status"] == "价在区间、量还差 50%" and not c["9984.T"]["push_ok"]
    assert c["9984.T"]["blocks"] == ["资格检查：测试挡住"] and c["7203.T"]["blocks"] == []
    assert doc["impossible"] == [{"why": "横盘不成立", "tickers": ["8306.T"]}]
    assert not doc["stale"] and doc["age_min"] == 20 and doc["data_at"] == "2026-10-16T14:20+09:00"
    h = doc["holdings"][0]
    assert h["ticker"] == "6758.T" and h["now"] is None and not h["push_ok"] and h["px"] == round(c0, 2)
    assert doc["core"][0]["ticker"] == "1545.T" and doc["core"][0]["chg_pct"] == 1.0
    # 代码一律带名字：卡片（显示出来的字）、持仓一行、终端（"t" / hold 的键是给页面找元素用的，不显示）
    from test_trade_room import _text
    v = IW.view(doc, AT)
    txt = IW.text(doc, AT, "paper")
    blob = _text(panel._intraday_card(v)) + "".join(v["hold"].values()) + txt
    for t in ("7203.T", "9984.T", "8306.T", "6758.T", "1545.T"):
        assert t not in blob
    for lab in ("7203 トヨタ自動車", "9984 ソフトバンクグループ", "6758 ソニーグループ", "1545 纳斯达克 100", "1655 "):
        assert lab in txt
    assert "7203 トヨタ自動車" in v["rows"][0]["label"] and "离下沿" in v["rows"][0]["line"] and "成交量 100%" in v["rows"][0]["line"]
    assert v["hold"]["6758.T"].startswith("盘中（暂定，数据 14:20，约晚 20 分钟）：现价") and "收盘仍在这里：规则不卖" in v["hold"]["6758.T"]
    assert "8306 三菱ＵＦＪフィナンシャル・グループ" in v["groups"][0]["names"] and v["impossible"] == "今天不可能：1 只（横盘不成立 1）"
    assert v["foot"] == "暂定：以明早 07:40 执行器为准；规则的候选，不是建议；非投资建议" and v["live"] is True


def test_gates_global_and_unknown(monkeypatch):
    frames, _ = _setup(monkeypatch, mult=0.0)
    doc = IW.evaluate("paper", AT, fetch=_fetcher(frames, _bands(frames)), frames=frames)
    assert doc["gates"]["global"] == ["新仓倍数 0（风险报告「避险」）→ 明早不开新仓"]
    assert all("新仓倍数 0（风险报告「避险」）→ 明早不开新仓" in r["blocks"] for r in doc["candidates"])
    v = IW.view(doc, AT)                                     # 所有票都挡的：卡片顶上 ★ 一次，每行不重复
    assert "新仓倍数 0（风险报告「避险」）→ 明早不开新仓" in v["warn"]
    assert v["rows"] and not any("新仓倍数" in r["gates"] for r in v["rows"])
    frames, _ = _setup(monkeypatch, decided="2026-10-14")
    doc = IW.evaluate("paper", AT, fetch=_fetcher(frames, _bands(frames)), frames=frames)
    assert not doc["gates"]["known"] and doc["gates"]["note"] == "闸门未知（执行器的汇总是 2026-10-14 收盘的，应有 2026-10-15）"
    v = IW.view(doc, AT)
    assert any("闸门未知" in w for w in v["warn"]) and v["rows"][0]["gates"] == ""   # 卡片顶上写一次，每行不重复
    (paths.out_dir() / "live_unified_paper.json").write_text("{坏的", encoding="utf-8")
    assert IW.load_gates("paper", DAY, {})["note"] == "闸门未知（执行器早上的汇总读不到）"


def test_push_buy_and_sell_text_dedupe(monkeypatch):
    frames, c0 = _setup(monkeypatch, halt=True)
    sent = []
    fetch = _fetcher(frames, _bands(frames), sell_px=c0 * 0.92)                       # 6758 跌破止损（−7%）
    doc = IW.run_once("paper", AT, fetch=fetch, send=lambda s, t, level="info": sent.append((s, t)))
    assert [s for s, _ in sent] == ["盘中暂定买点：7203 トヨタ自動車", "盘中暂定卖点：6758 ソニーグループ"]
    for s, t in sent:
        assert "暂定" in t and "执行器" in t and "建议" not in t and "建议" not in s
        assert "现在不需要操作" in t and "盘中手动买卖没有研究支持" in t and t.endswith("（HALT 中：明早不会下单）")
        assert ".T" not in t
    assert "如果收在这里，规则明早 09:00 开盘会买（执行器照常处理，现在不需要操作）" in sent[0][1]
    assert "如果收在这里，规则明早 09:00 开盘会卖（执行器照常处理，现在不需要操作）" in sent[1][1]
    assert f"已越过收盘卖出线 「止损（买价 −7%）」{IW._px(round(c0 * 0.93, 2))}。" in sent[1][1]
    keys = [x["key"] for x in json.loads(IW.out_path("paper").read_text(encoding="utf-8"))["pushes"]["sent"]]
    assert keys == ["盘中|7203|buy", "盘中|6758|sell"]                                 # 键不含价格
    IW.run_once("paper", AT + dt.timedelta(minutes=5), fetch=fetch, send=lambda s, t, level="info": sent.append((s, t)))
    assert len(sent) == 2                                                              # 同一只同一边一天一次
    v = IW.view(IW.load("paper"), AT)
    assert "HALT 中：明早不会下单" in v["warn"] and "若收盘仍在这里 → 规则明早开盘卖（止损（买价 −7%））" in v["hold"]["6758.T"]


def test_sell_push_only_after_1410_and_blocked_buy_says_so(monkeypatch):
    frames, c0 = _setup(monkeypatch, mult=0.0)
    sent = []
    early = dt.datetime(2026, 10, 16, 13, 30, tzinfo=JST)
    fetch = _fetcher(frames, _bands(frames), at="2026-10-16T13:10+09:00", sell_px=c0 * 0.92)
    IW.run_once("paper", early, fetch=fetch, send=lambda s, t, level="info": sent.append((s, t)))
    assert [s for s, _ in sent] == ["盘中暂定买点：7203 トヨタ自動車"]                     # 卖点：数据 13:10 < 14:10 → 不推
    assert "但现在被挡（新仓倍数 0（风险报告「避险」）→ 明早不开新仓）→ 明早不会买（执行器照常处理，现在不需要操作）" in sent[0][1]
    assert "HALT" not in sent[0][1]


def test_daily_cap_5(monkeypatch):
    doc = {"day": DAY.isoformat(), "stale": False, "error": "", "halt": False, "gates": {"known": True},
           "candidates": [{"ticker": t, "label": f"{t[:4]} 名", "lo": 100, "hi": 110, "px": 105, "v": 10, "v_need": 10, "v_pct": 100,
                           "at": "2026-10-16T10:00+09:00", "blocks": [], "push_ok": True}
                          for t in ("7203.T", "6758.T", "9984.T", "8306.T", "6501.T", "8035.T", "4063.T")], "holdings": []}
    sent = []
    now = dt.datetime(2026, 10, 16, 10, 20, tzinfo=JST)
    out = IW.push(doc, "paper", now, send=lambda s, t, level="info": sent.append(s))
    assert len(out) == len(sent) == IW.CAP == 5
    doc2 = json.loads(json.dumps({**doc, "pushes": None}))
    assert IW.push(doc2, "paper", now + dt.timedelta(minutes=5), prev=doc, send=lambda s, t, level="info": sent.append(s)) == []
    assert len(sent) == 5                                                              # 今天已经 5 条：后面两只不再推
    assert IW.push(json.loads(json.dumps(doc)), "paper", now + dt.timedelta(days=3), prev=doc, send=lambda *a, **k: None) == []   # 周一：不在今天 → 不推


def test_stale_or_failed_fetch_never_pushes(monkeypatch):
    frames, _ = _setup(monkeypatch)
    sent = []
    snd = lambda s, t, level="info": sent.append(s)                                    # noqa: E731
    old = _fetcher(frames, _bands(frames), at="2026-10-16T13:50+09:00")                # 14:40 时只有 13:50 的 → 过期 50 分钟
    doc = IW.run_once("paper", AT, fetch=old, send=snd)
    assert doc["stale"] and doc["age_min"] == 50 and sent == []
    assert "数据过期 50 分钟（不推送）" in IW.view(doc, AT)["head"]

    def boom(ts):
        raise TimeoutError("yahoo")
    doc2 = IW.run_once("paper", AT + dt.timedelta(minutes=5), fetch=boom, send=snd)
    assert doc2["error"].startswith("Yahoo 取不到（TimeoutError）") and sent == []
    assert all(r.get("old") for r in doc2["candidates"] if r.get("px") is not None)    # 留着上一次的、标上
    assert not any(r["push_ok"] for r in doc2["candidates"])
    doc3 = IW.run_once("paper", AT + dt.timedelta(minutes=10), fetch=lambda ts: {}, send=snd)
    assert doc3["error"].startswith("Yahoo 取不到（没有数据）") and sent == []
    IW.set_push(False)                                                                 # 设置关 → 新鲜的数据也不推
    IW.run_once("paper", AT + dt.timedelta(minutes=15), fetch=_fetcher(frames, _bands(frames), at="2026-10-16T14:35+09:00"), send=snd)
    assert sent == [] and IW.settings()["push"] is False
    (paths.home() / IW.SETTINGS).write_text("{坏的", encoding="utf-8")
    assert IW.settings()["push"] is True                                               # 读坏 → 默认开


def test_dry_does_not_write_or_push(monkeypatch):
    frames, _ = _setup(monkeypatch)
    sent = []
    doc = IW.run_once("paper", AT, dry=True, fetch=_fetcher(frames, _bands(frames)), send=lambda *a, **k: sent.append(a))
    assert doc["candidates"] and sent == [] and not IW.out_path("paper").exists()


def test_cli_push_toggle_and_read(monkeypatch, capsys):
    import run
    assert run.main(["intraday", "--push", "off"]) == 0
    assert "盘中观测的手机推送：关" in capsys.readouterr().out and IW.settings()["push"] is False
    assert run.main(["intraday", "--push", "on"]) == 0 and IW.settings()["push"] is True
    capsys.readouterr()
    assert run.main(["intraday"]) == 0
    out = capsys.readouterr().out
    assert "盘中观测（paper）" in out and "还没有盘中观测" in out and IW.FOOT in out


# ───────────────────────── 面板：接口只读、线程可以关 ─────────────────────────
@pytest.fixture()
def servers():
    tok = panel.token()
    lsrv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    psrv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_phone_handler(1))
    lp, pp = lsrv.server_address[1], psrv.server_address[1]
    lsrv.RequestHandlerClass = panel.make_handler(lp, tok, clock=lambda: AT, phone_port=pp)
    psrv.RequestHandlerClass = panel.make_phone_handler(pp, clock=lambda: AT)
    for s in (lsrv, psrv):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    yield lp, pp
    for s in (lsrv, psrv):
        s.shutdown()
        s.server_close()


def test_panel_api_reads_the_file_and_never_fetches(monkeypatch, servers):
    from test_panel_phone import _phone, _req
    from qbreak import data as D
    frames, _ = _setup(monkeypatch)
    IW.run_once("paper", AT, fetch=_fetcher(frames, _bands(frames)), send=lambda *a, **k: None)

    def boom(*a, **k):
        raise AssertionError("请求里不该取价 / 算区间")
    for mod, fn in ((D, "intraday_quotes"), (IW, "_fetch_default"), (IW, "evaluate"), (IW, "bands_for"), (TL, "buy_trigger")):
        monkeypatch.setattr(mod, fn, boom)
    lp, pp = servers
    st, raw, hd = _req(lp, "GET", "/api/intraday?book=paper")
    j = json.loads(raw.decode("utf-8"))
    assert st == 200 and j["ok"] and j["title"] == IW.TITLE and j["rows"][0]["label"] == "7203 トヨタ自動車"
    st, raw, _ = _req(lp, "GET", "/?book=paper")
    html = raw.decode("utf-8")
    assert st == 200 and "<section class='card' id='intraday'>" in html and "data-intra='6758.T'" in html
    assert html.index("id='intraday'") < html.index("class='khgo small'")              # 选股页最上面
    assert "<link rel='modulepreload' href='/static/intraday.js?v=" in html
    code, body, _ = _phone(pp, "GET", "/api/intraday?book=paper")                     # 手机：没配对 → 401（与 /api/quotes 一样）
    assert code == 401 and "7203" not in body


def test_panel_card_text_equals_js_rendering(monkeypatch, tmp_path):
    """页面脚本 intraday.js 的 intraShow 按 /api/intraday 重画的卡片与服务器画的（panel._intraday_card）字一样；持仓一行跟着变；ok=false → 不动。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    from test_panel import _js_fn
    from test_trade_room import _text
    frames, _ = _setup(monkeypatch)
    doc = IW.run_once("paper", AT, fetch=_fetcher(frames, _bands(frames)), send=lambda *a, **k: None)
    v = IW.view(doc, AT)
    want = _text(panel._intraday_card(v))
    fns = "\n".join(_js_fn(panel._JS, n) for n in ("nd", "intraShow"))
    js = """
class El { constructor(t){ this.tagName=String(t).toUpperCase(); this.children=[]; this._t=''; this.className=''; this.dataset={}; this.open=false; }
  appendChild(c){ this.children.push(c); return c; }
  querySelector(s){ for(const c of this.children){ if(c.tagName===String(s).toUpperCase()) return c; const x=c.querySelector && c.querySelector(s); if(x) return x; } return null; }
  set textContent(v){ this._t=String(v); this.children=[]; } get textContent(){ return this._t+this.children.map(c=>c.textContent).join(''); } }
const CARD=new El('section'), HOLD=new El('div'), GONE=new El('div'); HOLD.dataset.intra='6758.T'; GONE.dataset.intra='9999.T'; GONE.textContent='old';
const document={createElement:t=>new El(t), createTextNode:t=>({textContent:String(t)}), querySelectorAll:s=>[HOLD, GONE]};
const $=s=>s==='#intraday' ? CARD : null;
const nameify=s=>s;
__FNS__
const V=__V__;
intraShow(V);
const out={card:CARD.textContent, hold:HOLD.textContent, gone:GONE.textContent};
CARD.querySelector('details').open=true; intraShow(V); out.keep=CARD.querySelector('details').open;
intraShow({ok:false}); out.same=CARD.textContent===out.card;
console.log(JSON.stringify(out));
""".replace("__FNS__", fns).replace("__V__", json.dumps(v, ensure_ascii=False))
    f = tmp_path / "intra.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    assert o["card"] == want and o["same"] and o["keep"] is True
    assert o["hold"] == v["hold"]["6758.T"] and o["gone"] == ""
    assert "7203 トヨタ自動車" in o["card"] and "今天不可能：1 只" in o["card"] and IW.FOOT in o["card"]


class _FakeSrv:
    """serve() 用的假服务：serve_forever 等线程起来（最多 2 秒）就返回（不开端口）。"""
    def __init__(self, ready):
        self.ready = ready
        self.socket = type("S", (), {"close": lambda self: None})()

    def serve_forever(self):
        self.ready.wait(2)

    def shutdown(self):
        pass

    def server_close(self):
        pass


@pytest.mark.parametrize("trigger,intraday,want", [(True, True, 1), (True, False, 0), (False, True, 0)])
def test_serve_starts_the_thread_only_when_enabled(monkeypatch, trigger, intraday, want):
    started, ready = [], threading.Event()
    monkeypatch.setattr(panel, "_make_srv", lambda *a, **k: _FakeSrv(ready))
    monkeypatch.setattr(panel, "_watch_code", lambda *a, **k: ready.set() if not (trigger and intraday) else None)
    monkeypatch.setattr(panel.Trigger, "loop", lambda self, stop, every=30: None)
    monkeypatch.setattr(panel, "_intraday_loop", lambda stop, *a, **k: (started.append(1), ready.set()))
    monkeypatch.setattr(panel.signal, "signal", lambda *a, **k: None)                 # 不改 pytest 自己的 SIGTERM 处理
    assert panel.serve(port=1, trigger=trigger, intraday=intraday, phone_port=0) == 0
    assert len(started) == want


def test_intraday_loop_survives_errors_and_stops():
    stop = threading.Event()
    n = []

    def tick(now, last):
        n.append(1)
        if len(n) == 1:
            raise RuntimeError("第一次出错")
        stop.set()
    panel._intraday_loop(stop, every=0.01, tick=tick)
    assert len(n) == 2


def test_mac_status_line(monkeypatch):
    from qbreak import mac_status as MS
    assert MS._intraday_item("paper", AT) is None                                     # 没有结果文件 → 不显示
    IW.out_path("paper").write_text(json.dumps({"day": "2026-10-16", "updated": "2026-10-16T14:35:00+09:00",
                                                "data_at": "2026-10-16T14:15+09:00", "error": ""}), encoding="utf-8")
    it = MS._intraday_item("paper", AT)
    assert it["name"] == "盘中观测" and it["level"] == "ok" and it["text"].startswith("最后一次 10-16 14:35（10-16 的盘，数据 14:15")
    it = MS._intraday_item("paper", AT + dt.timedelta(minutes=30))
    assert it["level"] == "warn" and "超过 15 分钟没更新" in it["text"]
    IW.out_path("paper").write_text(json.dumps({"day": "2026-10-16", "updated": "2026-10-16T14:35:00+09:00", "error": "X: y"}),
                                    encoding="utf-8")
    assert MS._intraday_item("paper", AT)["text"].endswith("出错：X: y")


def test_js_modules_concatenate_without_name_clashes(tmp_path):
    """intraday.js 加进 JS_MODULES 之后：全部模块拼成一个普通脚本（测试用的 panel._JS）顶层名字不重复（let / const 重复 = 语法错误）。"""
    assert "intraday" in panel.JS_MODULES and "import './intraday.js';" in (panel.STATIC_DIR / "main.js").read_text(encoding="utf-8")
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    f = tmp_path / "all.js"
    f.write_text(panel._JS, encoding="utf-8")
    p = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
