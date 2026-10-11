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
    assert "受损 大" in h and "chip bad" in h and "data-nlink='a1'" in h and "n=a1" in h and "JST" in h
    assert panel._news_mark(None) == ""


def test_news_marks_reads_cache_and_drops_old(monkeypatch):
    d = NW.cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "news.json").write_text(json.dumps({"events": [_ev("new", [["銀行", -2.0]]), _ev("old", [["銀行", -2.0]], hours=100)]}),
                                 encoding="utf-8")
    monkeypatch.setattr(NW, "holdings_map", lambda ts: {t: SEC[t] for t in ts if t in SEC})
    m = panel._news_marks(["8306.T"], NOW)
    assert [i["id"] for i in m["8306.T"]["items"]] == ["new"]
