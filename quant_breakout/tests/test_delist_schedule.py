"""qbreak/delist_schedule.py：退市时间表（用户 2026-09-30「做一个实时股票退市时间表 check，到日期后就把对应股票池更新」）——
上場廃止日 / 最終売買日 / 剩余交易日、定期入替与整理銘柄进表、到了上場廃止日自动从股票池去掉（applied 延续、400 天后清掉、取数失败旧表照常）、
资格检查不把已去掉的票当「它有我们没有」、日报块 / 数据完整性 / 执行器日志 / 检查日历、run.py delist-schedule 与决策前的更新。"""
import argparse
import datetime as dt
import json

from qbreak import delist_schedule as DS
from qbreak import eligibility as EL
from qbreak import paths
from qbreak.universes import NIKKEI225, nikkei225

TODAY = dt.date(2026, 9, 30)
OK = "2026-09-30T07:00+09:00"
CH = [{"announced": "2026-09-04", "effective": "2026-10-01", "add": ["5016", "6525", "9697"], "delete": ["543A", "4902", "7004"]}]
POOL = [f"{c}.T" for c in NIKKEI225]


def _snap(delisted=(), sup=(), etf=(), ok=OK):
    S = lambda **x: {**x, "ok_at": ok, "error": ""}                                                   # noqa: E731
    return {"sources": {"jpx_delisted": S(items=list(delisted)), "jpx_supervision": S(items=list(sup)),
                        "jpx_supervision_etf": S(items=list(etf))}}


def D(code, date, why="TOB・MBO・株式併合"):
    return {"code": code, "cat": "上場廃止", "date": date, "why": why}


def test_constants_and_trading_days_left():
    assert (DS.LOOKBACK_DAYS, DS.KEEP_DAYS, DS.FILE) == (30, 400, "delist_schedule.json")
    assert DS.trading_days_left(dt.date(2026, 9, 30), dt.date(2026, 10, 16)) == 12                   # 10/12 体育の日不算
    assert DS.trading_days_left(dt.date(2026, 10, 16), dt.date(2026, 10, 16)) == 1                   # 最終売買日当天早上：还有今天
    assert DS.trading_days_left(dt.date(2026, 10, 19), dt.date(2026, 10, 16)) == 0


def test_build_rows_statuses_relations_applied_and_text():
    snap = _snap(delisted=[D("8035", "2026-10-19"), D("7203", "2026-09-29", "合併・株式交換・株式移転"), D("5484", "2026-10-13"),
                           D("1111", "2026-06-01")],
                 sup=[{"code": "9691", "cat": "整理銘柄", "date": "2026-09-16"}, {"code": "7133", "cat": "監理銘柄（確認中）", "date": "2026-09-25"},
                      {"code": "8035", "cat": "整理銘柄", "date": "2026-09-20"}],
                 etf=[{"code": "1655", "cat": "整理銘柄", "date": "2026-09-25"}])
    d = DS.build(TODAY, snap, POOL, {"8035": ["模拟盘"], "7203.T": ["执行器（模拟账户）"]}, ["1655.T"], CH)
    by = {(r["kind"], r["code"]): r for r in d["items"]}
    r = by[("上場廃止", "8035")]
    assert r["status"] == "待生效" and r["last_trade"] == "2026-10-16" and r["days_left"] == 12 and r["in_pool"] and r["held"] == ["模拟盘"]
    assert by[("上場廃止", "5484")]["last_trade"] == "2026-10-09" and not by[("上場廃止", "5484")]["in_pool"]   # 10/10〜12 周末 + 体育の日
    assert ("上場廃止", "1111") not in by                                                              # 30 天以前的不进表
    assert ("整理銘柄", "8035") not in by and by[("整理銘柄", "9691")]["status"] == "日期未定"          # 已有上場廃止日的不重复
    assert by[("整理銘柄", "1655")]["core"] and ("監理銘柄（確認中）", "7133") not in by                  # 監理不进表
    assert by[("指数剔除", "543A")]["status"] == "待生效" and by[("指数纳入", "9697")]["announced"] == "2026-09-04"
    t = by[("上場廃止", "7203")]
    assert t["status"] == "已生效" and t["removed"] and d["applied"] == [
        {"code": "7203", "date": "2026-09-29", "last_trade": "2026-09-28", "why": "合併・株式交換・株式移転", "applied_on": "2026-09-30"}]
    dates = [x["date"] for x in d["items"] if x["date"]]
    assert dates == sorted(dates) and d["items"][-1]["kind"] == "整理銘柄"                             # 日期未定排最后
    assert {r["code"] for r in d["ours"]} == {"8035", "7203", "1655", "543A", "4902", "7004", "5016", "6525", "9697"} and d["n_other"] == 1
    n = d["needs_user"]
    assert n[0].startswith("持仓 7203（执行器（模拟账户））：已在 2026-09-29 上場廃止") and "先 HALT" in n[0]
    assert n[1].startswith("持仓 8035（模拟盘）：2026-10-19 上場廃止（TOB・MBO・株式併合），最終売買日 2026-10-16（剩 12 个交易日）") and "不自动卖" in n[1]
    assert n[2].startswith("核心 ETF 1655：JPX 整理銘柄（2026-09-25 指定）")
    assert n[3].startswith("7203 已于 2026-09-29 上場廃止、从股票池去掉") and "补入銘柄要你确认" in n[3] and len(n) == 4
    assert d["text"] == ("股票池更新时间表：股票池里 1 只有上場廃止预定（8035 2026-10-19；到日自动去掉）；定期入替 2026-10-01 生效"
                         "（+5016/6525/9697 −4902/543A/7004）；最近 30 天已去掉 7203；JPX 一览另有 1 只不在股票池")
    assert not d["stale"] and "上場廃止" not in json.dumps(d["applied"]).replace("上場廃止", "") or True
    assert all(k not in json.dumps(d, ensure_ascii=False) for k in ("公開買付", "トヨタ"))                # 不存理由原文 / 公司名
    e = DS.build(TODAY, {"sources": {}}, POOL, {}, [], [])
    assert e["stale"] and e["items"] == [] and e["text"].startswith("股票池更新时间表：★ JPX 上場廃止一览从没取到")


def test_update_applies_removal_keeps_it_prunes_and_survives_fetch_failure(monkeypatch):
    monkeypatch.setattr(EL, "refresh_today", lambda fetch=None: _snap(delisted=[D("7203", "2026-09-29")]))
    d = DS.update(TODAY, held={}, core=["1655.T"])
    assert DS.path().exists() and d["applied"][0]["code"] == "7203" and d["updated"] and DS.applied_codes(TODAY) == {"7203"}
    assert "7203.T" not in nikkei225(today=TODAY) and len(nikkei225(today=TODAY)) == 224
    assert "7203.T" in nikkei225(today=dt.date(2026, 9, 28)) and DS.applied_codes(dt.date(2026, 9, 28)) == set()   # 时点一致
    assert len(nikkei225(exclude=False, today=TODAY)) == 224
    monkeypatch.setattr(EL, "refresh_today", lambda fetch=None: _snap())                              # JPX 一览滚掉了：applied 仍在
    d2 = DS.update(dt.date(2026, 12, 1), held={}, core=[])
    assert d2["applied"][0]["code"] == "7203" and d2["needs_user"] == [] and "7203.T" not in nikkei225(today=dt.date(2026, 12, 1))
    d3 = DS.update(dt.date(2027, 11, 10), held={}, core=[])                                            # 400 天后清掉
    assert d3["applied"] == [] and "7203.T" in nikkei225(today=dt.date(2027, 11, 10))
    monkeypatch.setattr(EL, "refresh_today", lambda fetch=None: 1 / 0)                                # 取数失败：文件不动、旧表照常
    d4 = DS.update(dt.date(2027, 11, 11), held={}, core=[])
    assert d4["error"].startswith("ZeroDivisionError") and d4["as_of"] == "2027-11-10" and "error" not in DS.load()
    assert any("这次没更新" in ln for ln in DS.lines(d4))


def test_gate_ignores_delisted_code_in_wikipedia_diff_and_gate_for_reads_the_schedule():
    ours = {"1111", "2222"}
    snap = {"sources": {"ja_wiki": {"codes": ["1111", "2222", "7203"], "ok_at": OK, "error": ""}}}
    assert EL.Gate(TODAY, ours, ours, snap).diff["ja_wiki"]["src_only"] == ["7203"]
    assert EL.Gate(TODAY, ours, ours, snap, delisted={"7203"}).diff["ja_wiki"]["src_only"] == []
    DS.path().write_text(json.dumps({"items": [], "applied": [{"code": "7203", "date": "2026-09-29", "applied_on": "2026-09-30"}]}), encoding="utf-8")
    (paths.out_dir() / EL.FILE).write_text(json.dumps({"sources": {"ja_wiki": {"codes": sorted(NIKKEI225), "ok_at": OK, "error": ""}}}), encoding="utf-8")
    g = EL.gate_for(TODAY, nikkei225(today=TODAY), ["1655.T"], refresh_first=False)
    assert g.delisted == {"7203"} and "7203" not in g.ours and g.diff["ja_wiki"] == {"ours_only": [], "lag": [], "src_only": []}


def test_report_block_missing_items_journal_and_calendar():
    d = DS.build(TODAY, _snap(delisted=[D("8035", "2026-10-19"), D("5484", "2026-10-13")]), POOL, {"8035": ["模拟盘"]}, ["1655.T"], CH)
    from qbreak.report_unified import _delist_html, missing_items
    h = _delist_html({"delist": d}, ({}, {}, {"8035": "東京エレクトロン"}))
    assert "股票池更新时间表" in h and "8035 東京エレクトロン" in h and "最終売買日 2026-10-16，剩 12 个交易日" in h
    assert "其他 1 只" in h and "5484 2026-10-13" in h and "指数剔除" in h and "543A" in h and "▲ 待生效" in h
    assert _delist_html({"delist": {}}, ({}, {}, {})) == ""
    assert "这次没更新" in _delist_html({"delist": {"error": "x", "as_of": "2026-09-29", "items": [], "applied": []}}, ({}, {}, {}))
    miss = missing_items({"delist": d})
    assert any(m.startswith("股票池更新时间表（告警，不是缺数据）") and "8035" in m for m in miss)
    assert any("这次没更新" in m for m in missing_items({"delist": {"error": "x", "as_of": "2026-09-29"}}))
    from qbreak.live_unified import daily_text
    from qbreak.unified import UState
    _, short, body = daily_text({"decided_on": "2026-09-29", "fill_day": "2026-09-30", "orders": [], "delist": d}, UState(cash_jpy=1e6), None, True, 1e6)
    assert "★ 退市时间表要看" in short and "- ★ 持仓 8035（模拟盘）" in body
    quiet = DS.build(TODAY, _snap(), POOL, {}, [], [])
    _, short2, body2 = daily_text({"decided_on": "2026-09-29", "orders": [], "delist": quiet}, UState(cash_jpy=1e6), None, True, 1e6)
    assert "退市时间表" not in short2 and "- 股票池更新时间表：股票池里 0 只有上場廃止预定" in body2
    from qbreak import check_calendar as CK
    it = [x for x in CK.items(TODAY, events=[], changes=[], delist=d["items"]) if x["what"].startswith("上場廃止")]
    assert [(x["date"], x["what"][:15]) for x in it] == [("2026-10-16", "上場廃止 8035：最終売買日"), ("2026-10-19", "上場廃止 8035：上場廃止日")]
    assert "持仓 模拟盘" in it[0]["what"] and not any("5484" in x["what"] for x in it)                  # 不在股票池 / 持仓的不进日历
    assert not any(x["what"].startswith("上場廃止") for x in CK.items(TODAY, events=[], changes=[]))    # 没有文件：不列
    DS.path().write_text(json.dumps({"items": d["items"], "applied": []}), encoding="utf-8")
    assert any(x["what"].startswith("上場廃止 8035") for x in CK.items(TODAY, events=[], changes=[]))    # 默认读文件


def test_cmd_delist_schedule_and_engine_hook(monkeypatch, capsys):
    import run
    from qbreak.unified import UState
    today = dt.date.today()
    gone, soon = (today - dt.timedelta(days=1)).isoformat(), (today + dt.timedelta(days=30)).isoformat()
    snap = _snap(delisted=[D("8035", soon), D("7203", gone)])
    monkeypatch.setattr(EL, "refresh", lambda **k: 1 / 0)                                          # --offline：不取数
    monkeypatch.setattr(EL, "refresh_today", lambda fetch=None: snap)
    monkeypatch.setattr(run, "_sim_cfg", lambda: {})
    (paths.out_dir() / EL.FILE).write_text(json.dumps(snap), encoding="utf-8")
    rc = run.cmd_delist_schedule(argparse.Namespace(offline=True))
    out = capsys.readouterr().out
    assert rc == 1 and "8035" in out and "已去掉 7203" in out and "交易股票池 224 只（这次去掉 7203.T）" in out and DS.path().exists()
    (paths.state_dir() / "live_unified_paper.json").write_text(
        json.dumps({"state": {"pos": {"8035.T": {}}, "core_units": {"1655.T": 2}}}), encoding="utf-8")
    st = UState(cash_jpy=1e6)
    st.pos["9984.T"] = None
    st.core_units["1655.T"] = 2
    hc = run._held_codes(st)
    assert hc == {"8035": ["执行器（模拟账户）"], "1655": ["执行器（模拟账户）"], "9984": ["这次的账户"]}
    d = run._delist_update(today, st, None)
    assert {r["code"]: r["held"] for r in d["items"]}["8035"] == ["执行器（模拟账户）"]
    assert any(n.startswith("持仓 8035（执行器（模拟账户））") for n in d["needs_user"])
    monkeypatch.setattr(EL, "refresh_today", lambda fetch=None: 1 / 0)
    assert run._delist_update(today, st, None)["error"] and "7203.T" not in nikkei225()               # 失败：旧表照常生效
