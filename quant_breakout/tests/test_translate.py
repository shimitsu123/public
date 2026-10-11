"""消息标题翻成中文（qbreak/translate.py）+ 通知正文（news.notify_lines）—— 2026-10-11 用户「通知里面的新闻都要翻译为中文后进行通知」。"""
import json
import subprocess

from qbreak import news as NW
from qbreak import translate as TR


def _ev(i, title, zh=None):
    e = {"id": i, "title": title, "time": "2026-10-11T09:30:00+09:00", "event_labels": ["原油供给冲击 / 油价急涨"], "cred": 80,
         "cred_label": "高", "chain": {"shock_txt": "原油 +5%", "down": [["运输·物流", -1.2]], "rules": {}, "tickers_down": []}}
    if zh:
        e["title_zh"] = zh
    return e


def test_to_zh_uses_tool_caches_and_falls_back(tmp_path, monkeypatch):
    b = tmp_path / "qbreak-translate"
    b.write_text("")
    monkeypatch.setenv("QBREAK_TRANSLATE", str(b))
    calls = []

    def run(cmd, input=None, **k):
        calls.append(json.loads(input))
        out = [{"zh": "中文:" + t, "src": "ja"} if "原油" in t else {"zh": None, "err": "notInstalled"} for t in json.loads(input)]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out, ensure_ascii=False))
    assert TR.to_zh(["原油高騰", "Stocks fall"], run=run) == ["中文:原油高騰", None]
    assert TR.to_zh(["原油高騰"], run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("缓存命中不该再翻"))) == ["中文:原油高騰"]
    assert len(calls) == 1


def test_no_tool_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("QBREAK_TRANSLATE", str(tmp_path / "none"))
    assert TR.to_zh(["原油高騰"]) == [None] and TR.status()["tool"] is False


def test_notify_lines_chinese_first_with_original():
    t = NW.notify_lines([_ev("a", "原油高騰", "原油价格飙升"), _ev("b", "Oil spikes")])
    assert "09:30 JST 原油价格飙升｜原油供给冲击" in t and "（原文：原油高騰）" in t
    assert "Oil spikes" in t and "还没翻译成中文" in t


def test_news_card_and_marks_show_chinese(monkeypatch):
    import datetime as dt
    from qbreak import panel
    from qbreak.calendar_jp import JST
    d = NW.cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    e = {**_ev("zz1", "原油高騰", "原油价格飙升"), "severity": 2, "alert": True, "events": ["oil_up"], "threat": 1.6}
    (d / "news.json").write_text(json.dumps({"events": [e]}, ensure_ascii=False), encoding="utf-8")
    h = panel._news_card(dt.datetime(2026, 10, 11, 12, 0, tzinfo=JST))
    assert "原油价格飙升" in h and "原文：原油高騰" in h
