"""最近几季决算的小图（qbreak/fins_view.py；2026-10-18 用户：持仓与选股出了买入信号的票加决算图、标出下次决算日与预期、少写字；只展示）：
单季 = 同一会计年度累计相减、连结优先、只用今天以前开示的；下一季 = 按会社予想摊算（上半期予想 / 全年予想）；全年进度、修正；
没有营业利润的用经常利润；图里有下次决算日（Yahoo 预计带「?」）；面板的持仓与选股行显示、没有数据不显示；取数不联网（注入）。"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import fins_view as FV                                           # noqa: E402
from qbreak import panel, paths                                              # noqa: E402

TODAY = dt.date(2026, 10, 18)


def _r(fye, per, cum, disc, kind="Consolidated", **kw):
    fy_en = dt.date.fromisoformat(fye)
    st = dt.date(fy_en.year - 1, 4, 1)
    pen = {"1Q": dt.date(st.year, 6, 30), "2Q": dt.date(st.year, 9, 30), "3Q": dt.date(st.year, 12, 31), "FY": fy_en}[per]
    return {"DiscDate": disc, "DiscTime": "15:00", "Code": "72030", "DocType": f"{per}FinancialStatements_{kind}_JP", "CurPerType": per,
            "CurPerSt": st.isoformat(), "CurPerEn": pen.isoformat(), "CurFYSt": st.isoformat(), "CurFYEn": fye, "OP": cum, **kw}


E = 1e8                                                                      # 亿円


def _rows():
    a, b, c = "2025-03-31", "2026-03-31", "2027-03-31"
    return [_r(a, "1Q", 100 * E, "2024-08-01"), _r(a, "2Q", 220 * E, "2024-11-01"), _r(a, "3Q", 330 * E, "2025-02-01"),
            _r(a, "FY", 460 * E, "2025-05-01"),
            _r(b, "1Q", 110 * E, "2025-08-01"), _r(b, "2Q", 250 * E, "2025-11-01"), _r(b, "3Q", 380 * E, "2026-02-01"),
            _r(b, "FY", 520 * E, "2026-05-10", NxFOP=560 * E, NxFOP2Q=250 * E),
            _r(b, "1Q", 999 * E, "2025-08-01", kind="NonConsolidated"),            # 有连结 → 单体不用
            _r(c, "1Q", 120 * E, "2026-08-05", FOP=600 * E, FOP2Q=270 * E),       # 上修：560 → 600
            _r(c, "2Q", 300 * E, "2026-11-05")]                                    # 还没到的开示：不用


def test_series_single_quarters_yoy_forecast_progress_revision():
    s = FV.series(_rows(), TODAY)
    assert s["basis"] == "营业利润"
    assert [x["lab"] for x in s["q"]] == ["24/9", "24/12", "25/3", "25/6", "25/9", "25/12", "26/3", "26/6"]   # 最近 8 季
    assert [round(x["v"] / E) for x in s["q"]] == [120, 110, 130, 110, 140, 130, 140, 120]
    assert s["q"][-1]["yoy"] == 9.1 and s["q"][-1]["dir"] == 1 and s["q"][0]["yoy"] is None
    nx = s["next"]
    assert nx["lab"] == "26/9" and round(nx["v"] / E) == 150 and nx["how"] == "上半期予想 − 1Q" and nx["yoy"] == 7.1
    assert s["fy"]["fye"] == "2027-03-31" and s["fy"]["prog"] == 20 and s["fy"]["rev_pct"] == 7.1 and s["fy"]["rev_disc"] == "2026-08-05"


def test_series_after_fy_results_and_full_year_path():
    rows = [r for r in _rows() if r["CurFYEn"] != "2027-03-31"]
    s = FV.series(rows, TODAY)                                               # 最近一季 = FY → 下一季是新一期的 1Q：上半期予想 ÷ 2
    assert s["q"][-1]["lab"] == "26/3" and s["next"]["lab"] == "26/6" and round(s["next"]["v"] / E) == 125
    assert s["next"]["how"] == "上半期予想 ÷ 2" and s["fy"]["prog"] is None and "rev_pct" not in s["fy"]
    rows = [r for r in _rows() if r["DiscDate"] <= "2026-02-01" and r["DocType"].endswith("_Consolidated_JP")]
    rows[-1]["FOP"] = 500 * E                                                # 3Q 的开示里写着全年予想
    s = FV.series(rows, TODAY)
    assert s["next"]["lab"] == "26/3" and round(s["next"]["v"] / E) == 120 and s["next"]["how"] == "(全年予想 − 已开示累计) ÷ 1"
    assert s["fy"]["prog"] == 76


def test_series_bank_uses_ordinary_profit_and_loss_words():
    rows = [{**r, "OP": None, "OdP": v} for r, v in zip(_rows(), (100, 220, 330, 460, -10, -40, -60, -20, 0, 50, 0))]
    s = FV.series([{**r, "OdP": (r["OdP"] or 0) * E} for r in rows], TODAY)
    assert s["basis"] == "经常利润"
    q = {x["lab"]: x for x in s["q"]}
    assert FV._yw(q["25/6"]) == "转亏" and FV._yw(q["26/6"]) == "扭亏" and FV._yw(q["25/12"]) == "转亏"
    assert FV._yw({"v": -5, "ly": -10}) == "亏损收窄" and FV._yw({"v": -15, "ly": -10}) == "亏损扩大" and FV._yw({"v": 1}) is None
    assert q["25/9"]["dir"] == -1 and q["25/9"]["yoy"] is None
    assert FV.series([], TODAY) is None and FV.series([{**r, "OP": None} for r in _rows()], TODAY) is None


def test_html_marks_next_date_forecast_and_keeps_text_short():
    s = FV.series(_rows(), TODAY)
    s.update(date="2026-11-05", date_src="jquants")
    h = FV.html(s, tip=panel._tip)
    assert "<svg class='fv'" in h and "决算 11/5</text>" in h and "予想 150</text>" in h and "class='fvp up'" in h
    assert "26/6 同比 +9%" in h and "全年予想 进度 20%" in h and "上修 +7%" in h and "予想 同比 +7%" in h
    assert "本期</text>" in h and "营业利润 · 单季 · 亿円" in h and "72030" not in h and "7203" not in h
    s.update(date_src="yahoo")
    assert "决算 11/5?</text>" in FV.html(s)
    s.pop("date")
    assert "决算 未定</text>" in FV.html(s)
    assert FV.html(None) == "" and FV.html({"q": []}) == ""


class _Cl:
    def __init__(self):
        self.calls = []

    def get(self, path, **kw):
        self.calls.append((path, kw))
        return _rows()


class _Earn:
    source = {}

    def next_earnings(self, t):
        self.source[t] = "jquants"
        return dt.date(2026, 11, 5)


def test_scope_build_write_load_and_panel_rows():
    st = {"pos": {"7203.T": {"shares": 100, "entry_px": 2500.0}, "1545.T": {"shares": 1}}, "core_units": {"1545.T": 100}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps({"state": st}), encoding="utf-8")
    rows = [{"ticker": "6501.T", "status": "triggered"}, {"ticker": "9984.T", "status": "watch", "near": {"where": "below_up", "days": 3}},
            {"ticker": "8035.T", "status": "watch", "near": {"where": "below_up", "days": 9}}]
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"suggest": {"rows": rows}}), encoding="utf-8")
    assert FV.scope() == ["6501.T", "7203.T", "9984.T"]                       # 核心 ETF、9 天后的不取
    cl = _Cl()
    doc = FV.build(["7203.T", "AAPL"], TODAY, client=cl, earnings=_Earn())   # 不是东证代码：不取
    assert set(doc["rows"]) == {"7203.T"} and cl.calls == [("/fins/summary", {"code": "72030"})]
    assert doc["rows"]["7203.T"]["date"] == "2026-11-05" and doc["rows"]["7203.T"]["date_src"] == "jquants"
    n = len(cl.calls)
    FV.build(["7203.T"], TODAY, client=cl, earnings=_Earn())                  # 同一天：用缓存，不再取
    assert len(cl.calls) == n
    FV.write(FV.build(["7203.T"], TODAY, client=None, earnings=_Earn()))      # 没有キー：只用缓存
    assert set(FV.load()["rows"]) == {"7203.T"}


def test_panel_shows_the_chart_in_holdings_only_when_there_is_data():
    st = {"pos": {"7203.T": {"ticker": "7203.T", "shares": 100, "entry_px": 2500.0, "entry_date": "2026-10-01", "stop_px": 2300.0}},
          "core_units": {}, "pending_exit": {}, "cash_jpy": 1e6, "history": [["2026-10-16", 1.25e6]], "last_date": "2026-10-16"}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps({"state": st}), encoding="utf-8")
    at = dt.datetime(2026, 10, 18, 10, 0, tzinfo=panel.JST)
    assert "class='fvbox'" not in panel.render("paper", "t" * 40, at)
    s = FV.series(_rows(), TODAY)
    s.update(date="2026-11-05", date_src="jquants")
    FV.write({"asof": TODAY.isoformat(), "rows": {"7203.T": s}, "errors": {}})
    from test_panel import _pane
    h = _pane(panel.render("paper", "t" * 40, at), "hold")
    assert h.count("class='fvbox'") == 1 and "决算 11/5</text>" in h and "决算图怎么看" in h


def test_pick_rows_show_the_chart():
    from test_panel import SG_ROWS, _card, _sm
    _sm()
    s = FV.series(_rows(), TODAY)
    t = next(r["ticker"] for r in SG_ROWS if r.get("status") == "triggered")
    FV.write({"asof": TODAY.isoformat(), "rows": {t: s}, "errors": {}})
    html = panel.render("paper", "t" * 40, dt.datetime(2026, 10, 6, 10, 0, tzinfo=panel.JST))
    ab = _card(html, "autobuy")
    assert ab.count("class='fvbox'") == 1 and "决算 未定</text>" in ab
