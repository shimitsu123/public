"""经济威胁消息的来源只写国家（qbreak/news_country.py；2026-10-19 用户：「消息里面的消息要显示来源于哪国只写国家就行」；只展示）：
已知媒体表 → 美国呼号 → 假名 / 汉字 = 日本 → 网址国家域名 → 不明；Google ニュース取 <source url>；面板标题行有国家、详细只写国家不写媒体名；
旧缓存（没有 country）按出版方现算。"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import dashboard as DB                                           # noqa: E402
from qbreak import news as NW                                                # noqa: E402
from qbreak import news_country as NC                                        # noqa: E402
from qbreak import panel                                                     # noqa: E402

from test_news import GN, NOW, _it                                           # noqa: E402


@pytest.mark.parametrize("pub,url,want", [
    ("Reuters", None, "英国"), ("ロイター", None, "英国"), ("Bloomberg.com", None, "美国"), ("BNN Bloomberg", None, "加拿大"),
    ("WSJ", None, "美国"), ("KIRO 7 News Seattle", None, "美国"), ("WLOX", None, "美国"), ("Toronto Star", None, "加拿大"),
    ("The Times of India", None, "印度"), ("NDTV Profit", None, "印度"), ("VOV World", None, "越南"), ("Theinvestor", None, "韩国"),
    ("ウクルインフォルム通信", None, "乌克兰"), ("聯合ニュース", None, "韩国"), ("Kyiv Independent", None, "乌克兰"),
    ("Yahoo!ファイナンス", None, "日本"), ("Yahoo Finance", None, "美国"), ("日本経済新聞", None, "日本"), ("みんかぶ FX/為替", None, "日本"),
    ("NHK 経済", None, "日本"), ("日本銀行", None, "日本"), ("FRB", None, "美国"), ("気象庁", None, "日本"), ("Al Jazeera English", None, "卡塔尔"),
    ("X", None, "不明"), ("TradingView", None, "不明"), ("Some Blog", "https://www.example.co.uk/a", "英国"), ("Somebody", "https://foo.com", "不明"),
    ("Somebody", "https://www.reuters.com/x", "英国"),
])
def test_country(pub, url, want):
    assert NC.country(pub, url) == want


def test_parse_feed_and_analyze_carry_country():
    g = NW.parse_feed(GN, "Google ニュース", "aggregator")
    assert g[0]["publisher"] == "ロイター" and g[0]["country"] == "英国"
    assert NW.parse_feed(GN.replace(">ロイター</source>", ">Some Daily</source>").replace(" - ロイター", ""),
                         "Google ニュース", "aggregator")[0]["country"] == "英国"     # 名字认不出 → <source url> 的 reuters
    ev = NW.analyze([_it("米国、日本車に追加関税を発動", "ロイター", "aggregator", country="英国"),
                     _it("米国、日本車に追加関税を発動へ", "Bloomberg", "aggregator", hours=2)], now=NOW)
    assert ev[0]["country"] == "英国" and ev[0]["others"][0]["country"] == "美国"
    assert any(w.startswith("来源：") and "ロイター" not in w and "Bloomberg" not in w for w in ev[0]["why"])


def _write(evs):
    d = NW.cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "news.json").write_text(json.dumps({"events": evs}, ensure_ascii=False), encoding="utf-8")


BASE = {"title": "Oil spikes", "time": (NOW - dt.timedelta(hours=1)).isoformat(), "event_labels": ["原油上涨"], "events": ["oil_up"],
        "cred": 90, "cred_label": "高", "severity": 2, "threat": 1.8, "alert": True, "chain": {}}


def test_panel_and_dashboard_show_only_the_country():
    _write([{**BASE, "id": "a", "publisher": "Reuters", "country": "英国", "n_sources": 2, "why": ["来源：英国（大媒体）"],
             "others": [{"title": "Oil up", "publisher": "CNBC", "country": "美国"}]}])
    h = panel._news_card(NOW)
    assert "<span class='chip' title='来源国家'>英国</span>" in h and "来源：英国（2 个来源：英国、美国）" in h
    assert "Reuters" not in h and "CNBC" not in h
    _write([{**BASE, "id": "b", "publisher": "Toronto Star", "n_sources": 1, "why": ["来源：Toronto Star（来源不明）"]}])   # 旧缓存
    h = panel._news_card(NOW)
    assert "title='来源国家'>加拿大</span>" in h and "来源：加拿大（1 个来源）" in h and "为什么可信：来源：加拿大（来源不明）" in h
    assert "Toronto Star" not in h
    hd = DB.news_full_html([{**BASE, "publisher": "Reuters", "country": "英国", "why": []}])
    assert "来源：英国｜" in hd and "Reuters" not in hd
