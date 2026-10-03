"""前向记录判断层接进模拟盘 / 执行器（run.py）：只在最新一根 K 线上缩日本个股新仓、s 高的候选先；日期对不上 = 原规则；
云端现算写文件、单项算不了按中性；基准账户（不加这一层）第一次复制模拟盘状态、之后各走各的；日报 / 执行器日志 / 页面的显示。"""
import json
from types import SimpleNamespace

import pandas as pd

from qbreak import fwd_judgment as FJ
from qbreak import paths
from qbreak.unified import UnifiedEngine, UState

from test_live_unified import CC, CFG, EX, P, _frame

CALM = {"crel_pct": 50.0, "tv_pct": 50.0, "wj_pct": 50.0, "w_pct": 50.0, "t23": 0.0, "deepdip": False, "C_rel": 49.0}


def _ind(n=30):
    a = _frame([100.0] * n, entry=(n - 1,))
    b = _frame([100.0] * n, entry=(n - 1,))
    core = _frame([700.0] * n)
    core["entry"] = False
    return {"A.T": a, "B.T": b, "1655.T": core}, pd.Series(True, index=core.index)   # 美股熊 → 核心那份留现金


def _engine(ind, bear, st=None):
    return UnifiedEngine(ind, CFG, {"JP": P, "US": P}, EX, CC, bear={"US": bear}, state=st)


def _plan_after(e, n=30):
    e.prime(5)
    for i in range(5, n):
        e.step(i)
    return {t: int(v[1]) for t, v in e.st.plan.items()}, list(e.st.plan)


def test_apply_live_mults_scales_last_bar_and_orders_candidates():
    import run
    ind, bear = _ind()
    bar = str(ind["1655.T"].index[-1].date())
    plans = {"JP": SimpleNamespace(scale=1.0, tmult={}, block=None)}
    pl = FJ.payload(bar, {**CALM, "wj_pct": 93.0}, False,                        # 市场 1 分 → ×0.75
                    {"A.T": {"F2": -0.9, "F2_thr": -0.444}, "B.T": {"F2": 0.3, "F2_thr": -0.444, "era": True}})
    e0, e1, e2 = _engine(ind, bear), _engine(ind, bear), _engine(ind, bear)
    assert run._apply_live_mults(e0, plans, None, bar) is None
    assert run._apply_live_mults(e1, plans, pl, bar) is pl
    assert run._apply_live_mults(e2, plans, pl, "2026-01-05") is None                # 文件日期对不上 → 原规则
    (s0, o0), (s1, o1), (s2, o2) = _plan_after(e0), _plan_after(e1), _plan_after(e2)
    assert s2 == s0 and o2 == o0 == ["A.T", "B.T"]                               # 原规则：按代码
    assert o1 == ["B.T", "A.T"]                                                  # 判断层：s 高的先
    assert s1["B.T"] < s0["B.T"] and s1["A.T"] < s1["B.T"]                      # ×0.75；A 再 ×0.5（s = −1）
    assert abs(s1["B.T"] - 0.75 * s0["B.T"]) <= 100 and abs(s1["A.T"] - 0.375 * s0["A.T"]) <= 100   # 一手 100 股的取整
    assert e1.live_mult["JP"][0] == 0.75 and e1.live_mult["JP"][1] == {"A.T": 0.5}
    last = len(e1.gidx) - 1
    assert e1.entry_priority_fn("B.T", last) > e1.entry_priority_fn("A.T", last) and e1.entry_priority_fn("B.T", last - 1) is None
    low = {"JP": SimpleNamespace(scale=0.3, tmult={"B.T": 0.2}, block=None)}     # 原有更低 → 不变（取 min，不放大）
    e3 = _engine(ind, bear)
    run._apply_live_mults(e3, low, pl, bar)
    assert e3.live_mult["JP"][0] == 0.3 and e3.live_mult["JP"][1] == {"B.T": 0.2, "A.T": 0.5}


def test_fj_compute_writes_file_and_counts_failures_as_neutral(monkeypatch):
    import run
    ind, _ = _ind()
    bar = str(ind["1655.T"].index[-1].date())
    ind["B.T"].loc[ind["B.T"].index[-1], "entry"] = False
    H = pd.DataFrame([{**CALM, "crel_pct": 85.0}], index=pd.DatetimeIndex([bar]))
    monkeypatch.setattr(FJ, "market_history", lambda *a, **k: H)
    monkeypatch.setattr(run, "_sim_cfg", lambda: {"unified": {"core": {"1655.T": 1.0}}})
    seen = {}

    def inputs(ind_, params, u, bd, cands, pre):
        seen["cands"] = cands
        return {t: {"F2": -0.9, "F2_thr": -0.444, "industry": "電気機器"} for t in cands}, {"B2 X2": "取不到"}
    monkeypatch.setattr(run, "_fj_stock_inputs", inputs)
    pl = run._fj_compute(ind, {}, {}, bar, {"energy": {"k4": {"on": False}}})
    assert seen["cands"] == ["A.T"]                                             # 只有最新 K 线上成立的日本个股（核心除外）
    assert pl["as_of"] == bar and pl["market"]["points"] == 2 and pl["market"]["mult"] == 0.5 and pl["market"]["date"] == bar
    assert pl["stocks"]["A.T"]["mult"] == 0.5 and pl["errors"] == {"B2 X2": "取不到"}
    assert json.loads((paths.home() / FJ.FILE).read_text(encoding="utf-8"))["as_of"] == bar
    idx = ind["1655.T"].index                                                   # 日経225 当天的 K 线缺：落后 1 个交易日照用并标日期
    monkeypatch.setattr(FJ, "market_history", lambda *a, **k: pd.DataFrame([{**CALM, "crel_pct": 85.0}], index=idx[-2:-1]))
    p1 = run._fj_compute(ind, {}, {}, bar, {"energy": {"k4": {"on": False}}})
    assert p1["market"]["points"] == 2 and p1["market"]["date"] == str(idx[-2].date()) and "市场层读数" not in p1["errors"]
    late = pd.DatetimeIndex([idx[-4], idx[-1] + pd.Timedelta(days=3)])          # 落后 2 个交易日 → 按中性；晚于最新 K 线的行不用
    monkeypatch.setattr(FJ, "market_history", lambda *a, **k: pd.DataFrame([{**CALM, "crel_pct": 85.0}, {**CALM}], index=late))
    p2 = run._fj_compute(ind, {}, {}, bar, {"energy": {"k4": {"on": False}}})
    assert p2["market"]["points"] == 0 and "落后 2 个交易日" in p2["errors"]["市场层读数"] and p2["market"]["date"] == str(idx[-4].date())
    assert run._jp_trading_days_between("2026-02-10", "2026-02-13") == 2 and run._jp_trading_days_between("2026-02-13", "2026-02-13") == 0
    monkeypatch.setattr(FJ, "market_history", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("FRED 取不到")))
    pl2 = run._fj_compute(ind, {}, {}, bar, {"energy": {"error": "JODI 取不到"}})
    assert pl2["market"]["points"] == 0 and pl2["market"]["mult"] == 1.0                # 整个市场层算不了 → 中性
    assert "市场层读数" in pl2["errors"] and pl2["errors"]["A5 K4"] == "JODI 取不到"


def test_baseline_step_copies_state_once_then_runs_without_layer(monkeypatch):
    import run
    ind, bear = _ind()
    monkeypatch.setattr(run, "_corp_actions_provider", lambda: SimpleNamespace(actions=lambda t: []))
    main = _engine(ind, bear)
    main.prime(5)
    for i in range(5, 29):
        main.step(i)
    raw_before = main.st.to_dict()
    calls = []

    def make(st, fj=True, base=False):
        calls.append(base)
        return _engine(ind, bear, st)
    ctx = SimpleNamespace(make=make, today="2026-09-30", ucfg=SimpleNamespace(capital_jpy=1_000_000))
    b = run._baseline_step(ctx, raw_before)
    assert calls == [True] and b["since"] == "2026-09-30" and b["last_date"] == str(ind["1655.T"].index[-1].date())   # 原规则的引擎
    assert b["plan"] == ["A.T", "B.T"] and b["equity_jpy"] is not None
    doc = json.loads((paths.state_dir() / "unified_state_base.json").read_text(encoding="utf-8"))
    assert doc["_since"] == "2026-09-30" and doc["last_date"] == b["last_date"]
    b2 = run._baseline_step(SimpleNamespace(make=make, today="2026-10-01", ucfg=ctx.ucfg), {"cash_jpy": 1.0})
    assert b2["since"] == "2026-09-30" and b2["last_date"] == b["last_date"]      # 之后读自己的状态，不再复制
    bad = run._baseline_step(SimpleNamespace(make=lambda st, fj=True, base=False: 1 / 0, today="x", ucfg=ctx.ucfg), raw_before)
    assert "ZeroDivisionError" in bad["error"]                                   # 失败只记下，不影响模拟盘


def test_brief_summary_and_displays():
    import run
    from qbreak.live_unified import daily_text, fj_text
    from qbreak.report_unified import _fwdj_html, missing_items
    pl = FJ.payload("2026-09-29", {**CALM, "wj_pct": 93.0, "w_pct": 90.0}, True, {"A.T": {"F2": -0.9, "F2_thr": -0.444, "industry": "電気機器"}},   # Wj + W = 2 分（K4 不计分）
                    {"B2 X2": "取不到"})
    assert run._fj_brief(SimpleNamespace(fj_on=False)) == {"enabled": False}
    miss = run._fj_brief(SimpleNamespace(fj_on=True, fj=None, bar_date="2026-09-29"))
    assert miss["applied"] is False and FJ.FILE in miss["why"]
    old = run._fj_brief(SimpleNamespace(fj_on=True, fj=pl, bar_date="2026-09-30"))
    assert old["applied"] is False and "2026-09-29" in old["why"]
    ok = run._fj_brief(SimpleNamespace(fj_on=True, fj=pl, bar_date="2026-09-29"))
    assert ok["applied"] and ok["points"] == 2 and ok["mult"] == 0.5 and ok["halved"] == ["A.T"] and ok["why"] is None
    sm = run._fj_summary(SimpleNamespace(fj_on=True, fj=pl, bar_date="2026-09-29"), {"since": "2026-09-30", "equity_jpy": 990_000},
                         1_000_000)
    assert sm["diff_jpy"] == 10_000 and sm["errors"] == {"B2 X2": "取不到"}
    sm_old = run._fj_summary(SimpleNamespace(fj_on=True, fj=pl, bar_date="2026-09-30"), {"error": "boom"}, 1_000_000)
    assert "生效" in sm_old["errors"]
    assert "×0.5" in fj_text(ok) and "A.T" in fj_text(ok) and fj_text(old).startswith("- ★ 前向记录判断层没生效")
    title, short, body = daily_text({"decided_on": "2026-09-29", "orders": [], "fwd_judgment": old}, UState(cash_jpy=1e6), None, True, 1e6)
    assert "★ 判断层没生效" in short and "前向记录判断层没生效" in body
    _, short2, body2 = daily_text({"decided_on": "2026-09-29", "orders": [], "fwd_judgment": ok}, UState(cash_jpy=1e6), None, True, 1e6)
    assert "判断层" not in short2 and "市场 2 分" in body2
    d = {"fwdj": sm, "extras": {"JP": {"regime": {"final_mult": 0.5, "fwd_judgment": {"applied": True, "before": 0.75}}}}}
    html = _fwdj_html(d)
    assert "前向记录判断层" in html and "A.T" in html and "×0.5" in html and "+¥10,000" in html and "0.75 倍" in html
    assert _fwdj_html({"fwdj": {"enabled": False}}) == ""
    items = missing_items({"history": [1], "fwdj": sm_old, "survey_failed": {"fred:WALCL": "ConnectionError"}})
    assert any("「B2 X2」" in x for x in items) and any(x.startswith("前向记录判断层：判断层文件是") for x in items)
    assert any("基准账户" in x and "boom" in x for x in items) and any("fred:WALCL" in x for x in items)
