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
        out = [{"zh": "中文:" + t, "src": "ja"} if "制裁" in t else {"zh": None, "err": "notInstalled"} for t in json.loads(input)]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out, ensure_ascii=False))
    assert TR.to_zh(["対ロ制裁", "Stocks fall"], run=run) == ["中文:対ロ制裁", None]
    assert TR.to_zh(["対ロ制裁"], run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("缓存命中不该再翻"))) == ["中文:対ロ制裁"]
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


def test_checks_flag_real_mistranslations_2026_10_11():
    """2026-10-11 实测 63 条里规则能抓的 3 条意思错（都要标）+ 正确的不误报。"""
    assert TR.checks("Why Bitcoin Can Fall Before a Fed Rate Hike, Then Rally After It Happens",
                     "为什么比特币可以在美联储加息之前下跌，然后在加息后下跌") == ["涨跌方向"]
    assert "数量级" in TR.checks("Loss of ‘Hundreds of Billions’ in Revenue", "「数十亿美元」收入损失")
    assert TR.checks('Opposition to Trump\'s "Easing of Sanctions on Russia"', "反对特朗普的“放大对俄罗斯的制裁”") == ["放松 / 加强"]
    assert TR.checks("US lifts sanctions on sale of Russian diesel amid unprecedented price surge",
                     "在价格空前飙升的情况下，美国取消对全球市场销售俄罗斯柴油的制裁") == []
    assert TR.checks("1%から1.25%へ日銀が政策金利引き上げ", "日本央行将政策利率从1%提高到1.25%") == []
    assert "数字" in TR.checks("12 killed", "多人死亡")


def test_pre_glossary_and_tidy():
    assert "鲁比奥" in TR.pre("Rubio calls sanctions necessary") and "日本央行" in TR.pre("日銀が利上げ")
    assert TR.pre("住宅ローン【福岡発】").endswith("【福冈报道】") or "报道】" in TR.pre("住宅ローン【福岡発】")
    assert TR.tidy("在中期中期之前") == "在中期之前"


def test_dashboard_shows_chinese_with_original():
    from qbreak import dashboard as DB
    import inspect
    src = inspect.getsource(DB)
    assert 'e.get("title_zh") or e["title"]' in src and "原文：{escape(e[\"title\"])}" in src
