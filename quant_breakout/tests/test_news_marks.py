"""选股候选 / 持仓上的消息影响标记（news.ticker_impacts + panel._news_mark；2026-10-11 用户：根据影响大小标记，并且可以看到对应的消息）。"""
import datetime as dt
import json

from qbreak import news as NW
from qbreak import panel
from qbreak.calendar_jp import JST

NOW = dt.datetime(2026, 10, 11, 12, 0, tzinfo=JST)


def _ev(i, imp, cred=80, alert=False, hours=1, rules=None):
    return {"id": i, "title": f"title {i}", "time": (NOW - dt.timedelta(hours=hours)).isoformat(), "event_labels": ["利率"],
            "cred": cred, "alert": alert, "chain": {"impacts": imp, "rules": rules or {}}}


SEC = {"7203.T": "自動車・輸送機", "8306.T": "銀行", "9984.T": "情報通信・サービスその他"}


def test_levels_direction_and_rule_fallback():
    ev = [_ev("a", [["自動車・輸送機", -1.0]], alert=True),            # -1.0 × 0.8 × 1.5 = -1.2
          _ev("b", [["自動車・輸送機", -0.2]]),                        # -0.16
          _ev("c", [["銀行", 0.6]]),                                   # +0.48 → 中
          _ev("d", [], rules={"情報通信・サービスその他": -1}, cred=30)]  # 规则 -0.5 × 0.3 = -0.15 → 小
    m = NW.ticker_impacts(ev, list(SEC), SEC)
    assert m["7203.T"]["level"] == "大" and m["7203.T"]["dir"] == "down" and [i["id"] for i in m["7203.T"]["items"]] == ["a", "b"]
    assert m["8306.T"]["level"] == "中" and m["8306.T"]["dir"] == "up"
    assert m["9984.T"]["level"] == "小"
    assert NW.ticker_impacts([_ev("e", [["銀行", 0.05]])], ["8306.T"], SEC) == {}     # 太小不标


def test_panel_mark_html_links_to_news_item():
    m = NW.ticker_impacts([_ev("a1", [["自動車・輸送機", -2.0]], alert=True)], ["7203.T"], SEC)["7203.T"]
    h = panel._news_mark(m)
    assert "受损 大" in h and "chip dnb" in h and "data-nlink='a1'" in h and "n=a1" in h and "JST" in h
    assert panel._news_mark(None) == ""


def test_news_marks_reads_cache_and_drops_old(monkeypatch):
    d = NW.cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "news.json").write_text(json.dumps({"events": [_ev("new", [["銀行", -2.0]]), _ev("old", [["銀行", -2.0]], hours=100)]}),
                                 encoding="utf-8")
    monkeypatch.setattr(NW, "holdings_map", lambda ts: {t: SEC[t] for t in ts if t in SEC})
    m = panel._news_marks(["8306.T"], NOW)
    assert [i["id"] for i in m["8306.T"]["items"]] == ["new"]


def test_level_hides_low_and_colors():
    assert NW.level({"severity": 1, "cred": 60}) == "低"
    assert NW.level({"severity": 1, "cred": 85}) == "中"
    assert NW.level({"severity": 2, "cred": 50}) == "中"
    assert NW.level({"severity": 2, "cred": 80}) == "高" and NW.level({"severity": 1, "cred": 10, "alert": True}) == "高"


def test_timing_start_end_and_state():
    sat = dt.datetime(2026, 10, 10, 20, 0, tzinfo=JST)                    # 周六晚上发布 → 10/12 体育の日休市 → 10/13 开盘起
    tm = NW.timing({"time": sat.isoformat(), "events": ["fed_decision"]}, NOW)
    assert tm["start"] == "2026-10-13" and tm["end"] == "2026-10-14" and (tm["lo"], tm["hi"]) == (1, 2) and tm["state"] == "未开始"
    mid = dt.datetime(2026, 10, 9, 10, 0, tzinfo=JST)                     # 周五盘中 → 当天开始；油价 5〜20 天
    tm = NW.timing({"time": mid.isoformat(), "events": ["oil_up", "fed_decision"]}, NOW)
    assert tm["intraday"] and tm["start"] == "2026-10-09" and tm["hi"] == 20 and tm["state"] == "影响中"
    old = NW.timing({"time": mid.isoformat(), "events": ["fed_decision"]}, dt.datetime(2026, 10, 20, 12, 0, tzinfo=JST))
    assert old["state"] == "已过"


def test_core_etf_uses_its_own_betas_and_drops_ended_events():
    ev = [{**_ev("fx", []), "events": ["yen_strong"], "chain": {"shocks": {"fx": -2.0}}},
          {**_ev("gone", []), "time": "2026-09-01T10:00:00+09:00", "events": ["fed_decision"], "chain": {"shocks": {"fx": -2.0}}}]
    m = NW.ticker_impacts(ev, ["1545.T"], sectors={}, assets={"1545.T": {"fx": 0.9}}, now=NOW)["1545.T"]
    assert m["dir"] == "down" and m["level"] == "大" and [i["id"] for i in m["items"]] == ["fx"]   # -2 × 0.9 × 0.8 = -1.44
    assert "纳斯达克" in m["sector"] and m["start"] and m["end"]
    h = panel._news_mark(m)
    assert "影响期（经验估计）" in h and "个交易日" in h


def test_news_card_hides_low_and_colors_levels():
    d = NW.cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    evs = [{**_ev("hi1", []), "severity": 2, "cred": 80, "alert": True, "events": ["oil_up"], "threat": 1.6},
           {**_ev("mid1", []), "severity": 1, "cred": 90, "events": ["oil_up"]},
           {**_ev("low1", []), "severity": 1, "cred": 50, "events": ["oil_up"]}]
    (d / "news.json").write_text(json.dumps({"events": evs}), encoding="utf-8")
    h = panel._news_card(NOW)
    assert "id='n-hi1'" in h and "id='n-mid1'" in h and "id='n-low1'" not in h
    assert "lv-hi" in h and "lv-mid" in h and "低的不显示（这次 1 条）" in h and "影响：" in h


def test_mult_why_names_the_layer():
    """「不买的原因」写清楚是哪一层（2026-10-11 用户）：风险报告避险 / 关联搭配 C / TBF …"""
    from types import SimpleNamespace
    import run
    from qbreak import suggest as SG
    reg = SimpleNamespace(overlay_mult=0.0, overlay_action="避险", overlay_as_of="2026-10-08", crash_prob=15.0, quant_mult=1.0)
    P = SimpleNamespace(scale=0.0, tmult={}, block=None, bb={"state": "bull"}, reg=reg, macro_info={"mult": 0.5}, fx_info={})
    e = SimpleNamespace(live_mult={}, gidx=[0])
    run._apply_live_mults(e, {"JP": P}, None, "2026-10-08")
    assert "市场风险报告（2026-10-08）的判断「避险」" in SG.mult_why(e, "7203.T") and "15%" in SG.mult_why(e, "7203.T")
    P2 = SimpleNamespace(scale=1.0, tmult={}, block=None, bb={}, reg=None, macro_info={}, fx_info={})
    tbf = {"enabled": True, "as_of": "2026-10-08", "skip_all": ["7203.T"], "errors": {}}
    run._apply_live_mults(e, {"JP": P2}, None, "2026-10-08", tbf_pl=tbf)
    assert SG.mult_why(e, "7203.T").startswith("TBF") and "新仓倍数 0（宏观" in SG.mult_why(e, "6758.T")
