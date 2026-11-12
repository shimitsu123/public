"""盘中观测（qbreak/intraday_watch.py + timeline 的盘中小函数 + 面板的线程 / 接口；2026-10-16 用户要求；只展示）：
暂定卖点 = 引擎的离场顺序；时段（午休、休市日、临时休市）；数据过期 / 取不到 → 不推送；同一只一天一次、每天最多 5 条；
推送文字（暂定、执行器、没有「建议」、HALT）；代码都带名字；面板接口只读结果文件（请求里不取价）、线程可以关掉。不连网（取价用注入的函数）。
2026-10-18 用户「今天盘中规则的买点 感觉没什么用 … 删了吧」：买点那一半（选股页卡片、股票池的买点区间、暂定买点的推送）删掉 → 这里查它不再出现。"""
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
    assert not hasattr(TL, "provisional_entry") and not hasattr(TL, "buy_bands")       # 盘中买点删掉（2026-10-18）


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


# ───────────────────────── 一次：持仓、推送 ─────────────────────────
def _tse_index(n, end=dt.date(2026, 10, 15)):
    out = [end]
    while len(out) < n:
        out.append(CJ.prev_trading_day(out[-1]))
    return pd.DatetimeIndex([pd.Timestamp(d) for d in reversed(out)])


def _frame(seed, p0=1000.0):
    b = _walk(seed, n=300, drift=0.0, vol=0.007, p0=p0)
    b.index = _tse_index(300)
    return b


def _setup(monkeypatch, halt=False, mult=1.0, decided="2026-10-15"):
    """持仓 6758（买价 = 昨收、止损 −7%）、核心 1545（拿着）+ 1655（规则的）；7203 / 9984 / 8306 是股票池里的（不再盯）；
    执行器的汇总是今天早上的。"""
    frames = {"7203.T": _frame(5), "9984.T": _frame(6), "8306.T": _frame(2), "6758.T": _frame(7), "1545.T": _frame(8, p0=250.0),
              "1655.T": _frame(9, p0=700.0)}
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


def test_evaluate_holdings_core_and_names(monkeypatch):
    frames, c0 = _setup(monkeypatch)
    calls = []
    doc = IW.evaluate("paper", AT, fetch=_fetcher(frames, {}, calls=calls), frames=frames)
    assert calls == [["1545.T", "1655.T", "6758.T"]]                                   # 盯的票 = 持仓 + 核心 ETF（股票池的买点不再算）
    assert not {"candidates", "bands", "gates", "impossible", "pool_n"} & set(doc)
    assert not doc["stale"] and doc["age_min"] == 20 and doc["data_at"] == "2026-10-16T14:20+09:00"
    h = doc["holdings"][0]
    assert h["ticker"] == "6758.T" and h["now"] is None and not h["push_ok"] and h["px"] == round(c0, 2)
    assert doc["core"][0]["ticker"] == "1545.T" and doc["core"][0]["chg_pct"] == 1.0
    # 代码一律带名字：持仓一行、终端（hold 的键是给页面找元素用的，不显示）
    v = IW.view(doc, AT)
    txt = IW.text(doc, AT, "paper")
    blob = "".join(v["hold"].values()) + txt
    for t in ("6758.T", "1545.T"):
        assert t not in blob
    for lab in ("6758 ソニーグループ", "1545 纳斯达克 100", "1655 "):
        assert lab in txt
    assert "买点" not in txt and "7203" not in txt
    assert v["hold"]["6758.T"].startswith("盘中（暂定，数据 14:20，约晚 20 分钟）：现价") and "收盘仍在这里：规则不卖" in v["hold"]["6758.T"]
    assert set(v) == {"ok", "head", "warn", "core", "hold", "live"} and v["live"] is True


def test_push_sell_text_dedupe_and_no_buy(monkeypatch):
    frames, c0 = _setup(monkeypatch, halt=True)
    sent = []
    fetch = _fetcher(frames, {}, sell_px=c0 * 0.92)                                    # 6758 跌破止损（−7%）
    IW.run_once("paper", AT, fetch=fetch, send=lambda s, t, level="info": sent.append((s, t)))
    assert [s for s, _ in sent] == ["盘中暂定卖点：6758 ソニーグループ"]                  # 买点不再推（2026-10-18）
    for s, t in sent:
        assert "暂定" in t and "执行器" in t and "建议" not in t and "建议" not in s
        assert "现在不需要操作" in t and "盘中手动买卖没有研究支持" in t and t.endswith("（HALT 中：下个交易日 10/19（周一）不会下单）")
        assert ".T" not in t
    assert "如果收在这里，规则下个交易日 10/19（周一）09:00 开盘会卖（执行器照常处理，现在不需要操作）" in sent[0][1]
    assert f"已越过收盘卖出线 「止损（买价 −7%）」{IW._px(round(c0 * 0.93, 2))}。" in sent[0][1]
    keys = [x["key"] for x in json.loads(IW.out_path("paper").read_text(encoding="utf-8"))["pushes"]["sent"]]
    assert keys == ["盘中|6758|sell"]                                                  # 键不含价格
    IW.run_once("paper", AT + dt.timedelta(minutes=5), fetch=fetch, send=lambda s, t, level="info": sent.append((s, t)))
    assert len(sent) == 1                                                              # 同一只一天一次
    v = IW.view(IW.load("paper"), AT)
    assert "HALT 中：下个交易日 10/19（周一）不会下单" in v["warn"] and "若收盘仍在这里 → 规则下个交易日 10/19（周一）开盘卖（止损（买价 −7%））" in v["hold"]["6758.T"]


def test_sell_push_only_after_1410(monkeypatch):
    frames, c0 = _setup(monkeypatch)
    sent = []
    early = dt.datetime(2026, 10, 16, 13, 30, tzinfo=JST)
    fetch = _fetcher(frames, {}, at="2026-10-16T13:10+09:00", sell_px=c0 * 0.92)
    IW.run_once("paper", early, fetch=fetch, send=lambda s, t, level="info": sent.append((s, t)))
    assert sent == []                                                                  # 数据 13:10 < 14:10 → 不推


def test_daily_cap_5(monkeypatch):
    doc = {"day": DAY.isoformat(), "stale": False, "error": "", "halt": False, "candidates": [],
           "holdings": [{"ticker": t, "label": f"{t[:4]} 名", "shares": 100, "px": 95, "entry_px": 100, "ret_pct": -5.0, "now": "stop",
                         "now_text": "止损", "levels": [], "at": "2026-10-16T14:15+09:00", "push_ok": True}
                        for t in ("7203.T", "6758.T", "9984.T", "8306.T", "6501.T", "8035.T", "4063.T")]}
    sent = []
    now = dt.datetime(2026, 10, 16, 14, 20, tzinfo=JST)
    out = IW.push(doc, "paper", now, send=lambda s, t, level="info": sent.append(s))
    assert len(out) == len(sent) == IW.CAP == 5 and all(s.startswith("盘中暂定卖点：") for s in sent)
    doc2 = json.loads(json.dumps({**doc, "pushes": None}))
    assert IW.push(doc2, "paper", now + dt.timedelta(minutes=5), prev=doc, send=lambda s, t, level="info": sent.append(s)) == []
    assert len(sent) == 5                                                              # 今天已经 5 条：后面两只不再推
    assert IW.push(json.loads(json.dumps(doc)), "paper", now + dt.timedelta(days=3), prev=doc, send=lambda *a, **k: None) == []   # 周一：不在今天 → 不推
    doc3 = {**json.loads(json.dumps(doc)), "holdings": [], "candidates": [{"ticker": "7203.T", "push_ok": True}]}   # 旧格式的买点候补：不推
    assert IW.push(doc3, "paper", now, send=lambda *a, **k: None) == []


def test_stale_or_failed_fetch_never_pushes(monkeypatch):
    frames, _ = _setup(monkeypatch)
    sent = []
    snd = lambda s, t, level="info": sent.append(s)                                    # noqa: E731
    old = _fetcher(frames, {}, at="2026-10-16T13:50+09:00")                            # 14:40 时只有 13:50 的 → 过期 50 分钟
    doc = IW.run_once("paper", AT, fetch=old, send=snd)
    assert doc["stale"] and doc["age_min"] == 50 and sent == []
    assert "数据过期 50 分钟（不推送）" in IW.view(doc, AT)["head"]

    def boom(ts):
        raise TimeoutError("yahoo")
    doc2 = IW.run_once("paper", AT + dt.timedelta(minutes=5), fetch=boom, send=snd)
    assert doc2["error"].startswith("Yahoo 取不到（TimeoutError）") and sent == []
    assert all(r.get("old") for r in doc2["holdings"] if r.get("px") is not None)      # 留着上一次的、标上
    assert not any(r["push_ok"] for r in doc2["holdings"])
    doc3 = IW.run_once("paper", AT + dt.timedelta(minutes=10), fetch=lambda ts: {}, send=snd)
    assert doc3["error"].startswith("Yahoo 取不到（没有数据）") and sent == []
    IW.set_push(False)                                                                 # 设置关 → 新鲜的数据也不推
    IW.run_once("paper", AT + dt.timedelta(minutes=15), fetch=_fetcher(frames, {}, at="2026-10-16T14:35+09:00"), send=snd)
    assert sent == [] and IW.settings()["push"] is False
    (paths.home() / IW.SETTINGS).write_text("{坏的", encoding="utf-8")
    assert IW.settings()["push"] is True                                               # 读坏 → 默认开


def test_dry_does_not_write_or_push(monkeypatch):
    frames, _ = _setup(monkeypatch)
    sent = []
    doc = IW.run_once("paper", AT, dry=True, fetch=_fetcher(frames, {}), send=lambda *a, **k: sent.append(a))
    assert doc["holdings"] and sent == [] and not IW.out_path("paper").exists()


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
    IW.run_once("paper", AT, fetch=_fetcher(frames, {}), send=lambda *a, **k: None)

    def boom(*a, **k):
        raise AssertionError("请求里不该取价 / 算区间")
    for mod, fn in ((D, "intraday_quotes"), (IW, "_fetch_default"), (IW, "evaluate"), (TL, "buy_trigger")):
        monkeypatch.setattr(mod, fn, boom)
    lp, pp = servers
    st, raw, hd = _req(lp, "GET", "/api/intraday?book=paper")
    j = json.loads(raw.decode("utf-8"))
    assert st == 200 and j["ok"] and j["hold"]["6758.T"].startswith("盘中（暂定") and "rows" not in j and "title" not in j
    st, raw, _ = _req(lp, "GET", "/?book=paper")
    html = raw.decode("utf-8")
    assert st == 200 and "id='intraday'" not in html and "规则的买点" not in html and "data-intra='6758.T'" in html   # 选股页的卡片删掉（2026-10-18）
    assert "<link rel='modulepreload' href='/static/intraday.js?v=" in html
    code, body, _ = _phone(pp, "GET", "/api/intraday?book=paper")                     # 手机：没配对 → 401（与 /api/quotes 一样）
    assert code == 401 and "7203" not in body


def test_js_updates_the_holding_lines(monkeypatch, tmp_path):
    """页面脚本 intraday.js 的 intraShow 按 /api/intraday 更新持仓每只一行（没有这只 → 空）；ok=false → 不动。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    from test_panel import _js_fn
    frames, _ = _setup(monkeypatch)
    doc = IW.run_once("paper", AT, fetch=_fetcher(frames, {}), send=lambda *a, **k: None)
    v = IW.view(doc, AT)
    js = """
const HOLD={dataset:{intra:'6758.T'}, textContent:''}, GONE={dataset:{intra:'9999.T'}, textContent:'old'};
const document={querySelectorAll:s=>[HOLD, GONE], getElementById:()=>null};
const nameify=s=>s;
__FN__
const V=__V__;
intraShow(V);
const out={hold:HOLD.textContent, gone:GONE.textContent};
intraShow({ok:false}); out.same=HOLD.textContent===out.hold;
console.log(JSON.stringify(out));
""".replace("__FN__", _js_fn(panel._JS, "intraShow")).replace("__V__", json.dumps(v, ensure_ascii=False))
    f = tmp_path / "intra.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    assert o["hold"] == v["hold"]["6758.T"] and o["gone"] == "" and o["same"]


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


def test_next_word_friday_and_midweek():
    """2026-10-16（周五）实测：卡片 / 推送写「明早」，下一次决策其实是 10/19（周一）→ 按交易日历写。"""
    assert IW.next_word(dt.date(2026, 10, 15)) == "明早"                                   # 周四 → 周五
    assert IW.next_word(dt.date(2026, 10, 16)) == "下个交易日 10/19（周一）"               # 周五 → 周一
    assert IW.next_word("2026-10-16") == "下个交易日 10/19（周一）"
    assert IW.next_word(None) == "下一个交易日"
    assert IW._at("明早", "09:00") == "明早 09:00" and IW._at("下个交易日 10/19（周一）", "09:00") == "下个交易日 10/19（周一）09:00"
    assert "明早" not in IW.FOOT


def test_todays_fills_bought_has_no_exit_lines_and_sold_is_gone(monkeypatch):
    """今天已成交（对账前；live_ops.held_now，2026-10-16）：卖光的 6758 不再出现、不推卖点；今天买进的 8306 没有离场线、不推送。"""
    frames, c0 = _setup(monkeypatch)
    p = paths.state_dir() / "live_unified_paper.json"
    b = json.loads(p.read_text(encoding="utf-8"))
    b["state"]["last_date"] = "2026-10-15"
    c8306 = float(frames["8306.T"]["Close"].iloc[-1])
    b["orders"] = [{"cid": "U2026-10-15-SELL-6758.T-N100000", "ticker": "6758.T", "side": "SELL", "kind": "stock", "qty": 100,
                    "sent_qty": 100, "filled_qty": 100, "filled_px": c0, "status": "FILLED", "reason": "manual_sell", "phase": "now",
                    "decided_on": "2026-10-15"},
                   {"cid": "U2026-10-15-BUY-8306.T-N100000", "ticker": "8306.T", "side": "BUY", "kind": "stock", "qty": 100,
                    "sent_qty": 100, "filled_qty": 100, "filled_px": c8306, "status": "FILLED", "reason": "manual_buy", "phase": "now",
                    "decided_on": "2026-10-15"}]
    p.write_text(json.dumps(b), encoding="utf-8")
    sent = []
    fetch = _fetcher(frames, {}, sell_px=c0 * 0.92)               # 6758 跌破止损：卖光了 → 不推
    doc = IW.run_once("paper", AT, fetch=fetch, send=lambda s, t, level="info": sent.append((s, t)))
    hs = {h["ticker"]: h for h in doc["holdings"]}
    assert set(hs) == {"8306.T"} and hs["8306.T"]["today"] and not hs["8306.T"]["push_ok"] and hs["8306.T"].get("now") is None
    assert "今天买进（对账前）：离场线在下个交易日 10/19（周一）07:40 的决策之后才有" in hs["8306.T"]["status"]   # 「在」后面不加空格（复核）
    assert not any("卖点" in s for s, _t in sent) and not any("8306" in s for s, _t in sent)
    v = IW.view(doc, AT)
    assert v["hold"]["8306.T"].startswith("盘中：今天买进（对账前）") and "6758.T" not in v["hold"]
