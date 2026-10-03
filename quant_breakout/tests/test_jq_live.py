"""qbreak/jq_live.py：取数时刻（晚 = 当天 / 早 = 前一营业日）、已取到的不重取且早上重取決算短信、决算日程与 Yahoo 对照、
会社予想修正 %、上市一览变化、整理结果与文字摘要、run.py jq-live（不连网）。J-Quants 原始数据与整理结果都不入库。"""
import datetime as dt
import json

import pandas as pd

from qbreak import jq_live as JL
from qbreak.calendar_jp import JST


def test_target_day_evening_and_morning():
    fri = dt.datetime(2026, 9, 25, 19, 30, tzinfo=JST)                        # 周五 19:30 → 当天
    assert JL.target_day(fri) == (dt.date(2026, 9, 25), "evening")
    mon = dt.datetime(2026, 9, 28, 7, 5, tzinfo=JST)                          # 周一 07:05 → 上周五、早
    assert JL.target_day(mon) == (dt.date(2026, 9, 25), "morning")
    sat = dt.datetime(2026, 9, 26, 20, 0, tzinfo=JST)                         # 周六 → 前一营业日
    assert JL.target_day(sat) == (dt.date(2026, 9, 25), "morning")
    assert JL.next_days(dt.date(2026, 9, 25), 2) == [dt.date(2026, 9, 28), dt.date(2026, 9, 29)]


class FakeClient:
    def __init__(self, data: dict):
        self.data, self.calls = data, []

    def get(self, path, **params):
        self.calls.append((path, params))
        v = self.data.get(path)
        if isinstance(v, Exception):
            raise v
        return v(params) if callable(v) else list(v or [])


def _client():
    return FakeClient({
        "/equities/bars/daily": [{"Date": "2026-09-25", "Code": "72030", "C": 3000.0, "AdjFactor": 1.0},
                                 {"Date": "2026-09-25", "Code": "83060", "C": 1500.0, "AdjFactor": 0.5}],
        "/fins/earnings-date": lambda p: ([{"PubDate": "2026-09-25", "SchDate": "2026-10-01", "FQName": "2Q", "Code": "72030", "CoName": "トヨタ"}]
                                          if p.get("scheduled_date") == "2026-10-01" else []),
        "/markets/margin-alert": [{"PubDate": "2026-09-25", "Code": "72030", "PubReason": "{}", "SLRatio": 12.5}],
        "/markets/short-sale-report": [{"DiscDate": "2026-09-25", "Code": "83060", "SSName": "X Fund", "ShrtPosToSO": 0.6, "PrevRptRatio": 0.5}],
        "/fins/summary": lambda p: ([{"DiscDate": "2026-08-01", "Code": "72030", "DocType": "1QFinancialStatements_Consolidated_JP",
                                      "CurFYEn": "2027-03-31", "FOP": "5000", "FNP": "4000"}] if "code" in p else []) + [
            {"DiscDate": "2026-09-25", "Code": "72030", "DocType": "EarnForecastRevision", "CurFYEn": "2027-03-31", "FOP": "5500", "FNP": "4000"}],
        "/equities/master": [{"Date": "2026-09-28", "Code": "72030", "CoName": "トヨタ", "MktNm": "プライム"},
                             {"Date": "2026-09-28", "Code": "99990", "CoName": "新会社", "MktNm": "グロース"}],
        "/markets/margin-interest": RuntimeError("HTTP 400"),
        "/equities/investor-types": [{"Section": "TSEPrime", "StDate": "2026-09-14", "EnDate": "2026-09-18", "FrgnBal": 123456}],
    })


def test_fetch_skips_existing_refetches_fins_in_morning_and_schedule(isolated_home):
    day = dt.date(2026, 9, 25)
    c = _client()
    st = JL.fetch(c, day, "evening")
    assert st["bars"] == 2 and st["margin_daily"].startswith("RuntimeError") and "earn_sched" not in st
    n = len(c.calls)
    st2 = JL.fetch(c, day, "evening")
    assert st2["bars"].startswith("已有") and len(c.calls) == n + 2                # 只重取没取到 / 空的：margin_daily、earn_pub
    st3 = JL.fetch(c, day, "morning")
    assert st3["fins"] == 1 and st3["earn_sched"] == 1                           # 早上：決算短信再取（確報）+ 10 个营业日的日程
    sched_calls = [p for path, p in c.calls if path == "/fins/earnings-date" and "scheduled_date" in p]
    assert len(sched_calls) == JL.SOON_DAYS and sched_calls[0]["scheduled_date"] == "2026-09-28"
    assert (isolated_home / "cache" / "jquants" / "live" / "2026-09-25_bars.csv.gz").exists()


def test_earnings_soon_tags_and_yahoo_mismatch():
    sched = pd.DataFrame([{"Code": "72030", "SchDate": "2026-10-01", "FQName": "2Q", "CoName": "A"},
                          {"Code": "83060", "SchDate": "2026-10-02", "FQName": "2Q", "CoName": "B"},
                          {"Code": "99990", "SchDate": "2026-10-02", "FQName": "FY", "CoName": "C"},
                          {"Code": "67580", "SchDate": "", "FQName": "2Q", "CoName": "D"}])
    out = JL.earnings_soon(sched, {"7203", "8306", "6758"}, {"8306": "持仓"}, {"7203": "2026-10-03"})
    assert [e["code"] for e in out] == ["8306", "7203"] and out[0]["tag"] == "持仓"   # 持仓在前；股票池外、未定的不列
    assert out[1]["mismatch"] and out[1]["yahoo"] == "2026-10-03"


def test_revisions_change_vs_previous_forecast():
    hist = pd.DataFrame([{"Code": "72030", "CurFYEn": "2027-03-31", "FOP": "5000", "FNP": "4000"}])
    new = pd.DataFrame([{"Code": "72030", "DocType": "EarnForecastRevision", "CurFYEn": "2027-03-31", "FOP": "5500", "FNP": "3600"},
                        {"Code": "11110", "DocType": "x", "CurFYEn": "2027-03-31", "FOP": "1", "FNP": "1"}])
    r = JL.revisions(new, {"7203"}, hist)
    assert len(r) == 1 and r[0]["FOP_chg_pct"] == 10.0 and r[0]["FNP_chg_pct"] == -10.0 and r[0]["main"] == "营业利润"
    bank = JL.revisions(pd.DataFrame([{"Code": "83460", "DocType": "EarnForecastRevision", "CurFYEn": "2027-03-31", "FOdP": "120"}]),
                        {"8346"}, pd.DataFrame([{"Code": "83460", "CurFYEn": "2027-03-31", "FOdP": "100"}]))
    assert bank[0]["main"] == "经常利润" and bank[0]["main_chg_pct"] == 20.0
    assert JL.revisions(new, {"7203"}, None)[0]["FOP_chg_pct"] is None          # 没有旧值 → 不算 %


def test_listing_changes():
    prev = pd.DataFrame([{"Code": "72030", "CoName": "A", "MktNm": "プライム"}, {"Code": "11110", "CoName": "Old", "MktNm": "スタンダード"}])
    nxt = pd.DataFrame([{"Code": "72030", "CoName": "A", "MktNm": "スタンダード"}, {"Code": "99990", "CoName": "New", "MktNm": "グロース"}])
    ch = JL.listing_changes(nxt, prev)
    assert [x["code"] for x in ch["new"]] == ["9999"] and [x["code"] for x in ch["gone"]] == ["1111"]
    assert ch["moved"] == [{"code": "7203", "name": "A", "from": "プライム", "to": "スタンダード"}]


def test_derive_and_text(isolated_home):
    day = dt.date(2026, 9, 25)
    c = _client()
    JL.fetch(c, day, "evening")
    JL.fetch(c, day, "morning")
    JL.fetch(c, day, "morning", universe={"7203", "8306"})                     # 予想修正的公司再取历史
    d = JL.derive(day, {"7203", "8306"}, {"7203": "候补"}, ["7203.T"], {"7203": "2026-10-01"})
    assert d["revisions"][0]["FOP_chg_pct"] == 10.0 and d["revisions"][0]["FNP_chg_pct"] == 0.0 and d["revisions"][0]["doc"] == "业绩预想修正"
    assert d["earnings_soon"][0]["code"] == "7203" and not d["earnings_soon"][0]["mismatch"]
    assert d["margin_alerts"][0]["code"] == "7203" and d["short_reports"][0]["holder"] == "X Fund"
    assert d["lots"] == [{"code": "7203", "close": 3000.0, "lot_jpy": 300000.0}] and d["splits"] == [{"code": "8306", "factor": 0.5}]
    assert d["foreign"]["balance"] == 123456.0
    t = JL.as_text(d)
    assert "10 个营业日内决算：股票池 1 只" in t and "空売り残高報告：1 只（8306）" in t and "7203 营业利润 +10.0%" in t
    json.dumps(d, ensure_ascii=False, default=float)


def test_cmd_jq_live_offline(isolated_home, monkeypatch, capsys):
    import run
    import qbreak.jquants
    monkeypatch.setattr(qbreak.jquants, "JQuants", lambda *a, **k: _client())
    assert run.main(["jq-live", "--date", "2026-09-25"]) == 0
    out = capsys.readouterr().out
    assert "J-Quants 2026-09-25（evening）" in out and "没取到（下次自动补）：margin_daily" in out
    d = json.loads((isolated_home / "out" / "jq_today.json").read_text(encoding="utf-8"))
    assert d["phase"] == "evening" and d["fetch"]["bars"] == 2


def test_jq_outputs_are_gitignored():
    from qbreak import paths
    gi = (paths.PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "var/cache/" in gi and "var/out/jq_today.json" in gi
