"""qbreak/news.py：解析（RSS 2.0 / Atom / Google ニュース / 気象庁）、事件归类（常见误判）、严重度升级、可信度、聚类、
新鲜度与提醒规则、影响链路（因子 → 行业 → 持仓 / 候补）、公开汇总不含标题、提醒只发一次、业种对照表完整。"""
import datetime as dt
import json

import pytest

from qbreak import news as NW
from qbreak.calendar_jp import JST
from qbreak.sectors import SECTOR_ETF_JP

NOW = dt.datetime(2026, 9, 26, 12, 0, tzinfo=JST)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>日銀、政策金利を0.75%に引き上げ決定</title><link>https://example.jp/a</link><pubDate>Sat, 26 Sep 2026 09:00:00 +0900</pubDate></item>
<item><title>無関係の話題</title><link>https://example.jp/b</link><pubDate>Sat, 26 Sep 2026 08:00:00 +0900</pubDate></item>
</channel></rss>"""
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fed raises rates by 25bp</title>
<link href="https://example.com/fed"/><updated>2026-09-26T01:00:00Z</updated></entry></feed>"""
GN = """<?xml version="1.0"?><rss version="2.0"><channel><item><title>米国、日本車に追加関税を発動 - ロイター</title>
<link>https://news.google.com/x</link><pubDate>Sat, 26 Sep 2026 02:00:00 GMT</pubDate><source url="https://jp.reuters.com">ロイター</source></item></channel></rss>"""


def test_parse_rss_atom_google():
    a = NW.parse_feed(RSS, "NHK 経済", "media")
    assert [x["title"] for x in a] == ["日銀、政策金利を0.75%に引き上げ決定", "無関係の話題"]
    assert a[0]["time"] == "2026-09-26T09:00+09:00" and a[0]["publisher"] == "NHK 経済"
    b = NW.parse_feed(ATOM, "FRB", "official")
    assert b[0]["link"] == "https://example.com/fed" and b[0]["time"] == "2026-09-26T10:00+09:00"
    g = NW.parse_feed(GN, "Google ニュース", "aggregator")
    assert g[0]["title"] == "米国、日本車に追加関税を発動" and g[0]["publisher"] == "ロイター"   # 标题末尾的「 - 出版方」去掉
    assert NW.parse_feed(b"<rss><broken", "x", "media") == []


def test_parse_jma_intensity_filter():
    rows = [{"eid": "1", "at": "2026-09-26T11:00:00+09:00", "anm": "能登半島沖", "mag": "6.1", "maxi": "5+", "ttl": "震源・震度情報"},
            {"eid": "1", "at": "2026-09-26T11:00:00+09:00", "anm": "能登半島沖", "mag": "6.1", "maxi": "5+", "ttl": "震源・震度情報"},
            {"eid": "2", "at": "2026-09-26T10:00:00+09:00", "anm": "熊本県", "mag": "3.6", "maxi": "3"},
            {"eid": "3", "at": "2026-09-26T09:00:00+09:00", "anm": "", "mag": "", "maxi": ""}]
    q = NW.parse_jma(json.dumps(rows))
    assert len(q) == 1 and "最大震度5強" in q[0]["title"] and q[0]["kind"] == "official" and q[0]["quake"] == "5+"
    assert NW.parse_jma("not json") == []


@pytest.mark.parametrize("title,has,hasnt", [
    ("日銀、政策金利を0.75%に引き上げ決定", ["boj_hike"], []),
    ("【米国市況】原油安で株は堅調－円急伸", ["oil_down", "yen_strong"], ["oil_up", "yen_weak"]),
    ("嘉手納基地に米軍長距離ミサイル発射機搬入へ", [], ["war"]),
    ("Pittsburgh pediatrician killed in home invasion", [], ["war"]),
    ("北朝鮮が弾道ミサイルを発射", ["war"], []),
    ("令和８年上半期の全国の税関における関税法違反事件の取締り状況", [], ["tariff"]),
    ("米国、日本車に追加関税を発動", ["tariff"], []),
    ("熊本県熊本地方でM3.6の地震 最大震度3", [], ["disaster"]),
    ("トヨタ、国内工場で減産", [], ["oil_up"]),
    ("日経平均が急落、下げ幅1000円超", ["crash"], []),
])
def test_classify_common_cases(title, has, hasnt):
    ev = NW.classify(title)
    assert set(has) <= set(ev) and not set(hasnt) & set(ev), ev


def test_severity_needs_decision_or_escalation_words():
    assert NW.severity(["boj_hike"], "タカ派演出の植田日銀、本音は「連続利上げ難しい」") == 1        # 评论 → 不升级
    assert NW.severity(["boj_hike"], "日銀、政策金利を0.75%に引き上げ決定") == 2
    assert NW.severity(["tariff"], "Author of America's tariff statute: Trump's tariffs are illegal") == 1
    assert NW.severity(["tariff"], "米国、日本車に追加関税を発動") == 2
    assert NW.severity(["war"], "ロシアが核攻撃を示唆、ミサイル攻撃") == 3
    assert NW.severity(["credit"], "欧州で信用不安、大手銀行が破綻") == 3


def _it(title, pub="NHK 経済", kind="media", hours=1.0, **kw):
    return {"title": title, "link": "https://x/" + title[:3], "time": (NOW - dt.timedelta(hours=hours)).isoformat(timespec="minutes"),
            "source": pub, "publisher": pub, "kind": kind, **kw}


def test_credibility_tiers_confirmation_and_hedges():
    assert NW.credibility([_it("日銀が利上げ", "日本銀行", "official")])[0] == 95
    assert NW.credibility([_it("x", "某ブログ", "aggregator")])[0] == 50
    assert NW.credibility([_it("x", "ロイター", "aggregator")])[0] == 80
    two = NW.credibility([_it("A社が破綻", "ロイター", "aggregator"), _it("A社が破綻", "日本経済新聞", "aggregator")])
    assert two[0] == 90 and "2 个不同来源" in "".join(two[1])
    three = [_it("A社が破綻", p, "aggregator") for p in ("ロイター", "日本経済新聞", "某ブログ")]
    assert NW.credibility(three)[0] == 100
    hedged = NW.credibility([_it("日銀、年内利上げを検討か", "某ブログ", "aggregator")])
    assert hedged[0] == 35 and "推测" in "".join(hedged[1])
    assert NW.credibility([_it("政府が介入を検討か", "財務省", "official")])[0] == 95   # 官方来源不扣


def test_cluster_similar_titles():
    g = NW.cluster([_it("米国、日本車に追加関税を発動", "ロイター"), _it("米、日本車に追加関税発動", "NHK 経済", hours=2),
                    _it("日銀が国債買い入れ減額", "日本銀行")])
    assert sorted(len(x) for x in g) == [1, 2]


BETAS = {"银行": {"rate_jp": 26.0, "credit": -23.0}, "不动产": {"rate_jp": -10.0, "credit": 8.0}, "汽车·运输机": {"fx": 0.33}}


def test_chain_factor_rules_and_tickers():
    c = NW.chain(["boj_hike"], BETAS, {"8306.T": "银行", "8801.T": "不动产", "7203.T": "汽车·运输机"})
    assert c["shocks"] == {"rate_jp": 0.1, "fx": -1.0} and "日本 10Y +0.10 pp" in c["shock_txt"]
    assert c["up"][0][0] == "银行" and c["up"][0][1] == pytest.approx(2.6)
    assert ("不动产", -1.0) in c["down"] and ("汽车·运输机", -0.33) in c["down"]
    assert c["tickers_up"] == ["8306.T"] and c["tickers_down"] == ["7203.T", "8801.T"]
    t = NW.chain(["tariff"], BETAS, {"7203.T": "汽车·运输机"})
    assert t["rules"]["汽车·运输机"] == -1 and t["tickers_down"] == ["7203.T"] and not t["up"]


def test_analyze_freshness_alerts_order_and_public_summary():
    items = [_it("米国、日本車に追加関税を発動", "ロイター", "aggregator"),                     # 严重度 2、可信 80 → 提醒
             _it("タカ派演出の植田日銀、本音は「連続利上げ難しい」", "日本経済新聞", "aggregator"),  # 评论 → 不提醒
             _it("北朝鮮が弾道ミサイルを発射", "NHK 主要", hours=80),                                # 超过 72 小时 → 不要
             _it("未来の記事 利上げ決定", "NHK 経済", hours=-3),                                      # 时间在未来 → 不要
             _it("無関係のスポーツ", "NHK 主要")]
    ev = NW.analyze(items, BETAS, {"7203.T": "汽车·运输机"}, now=NOW)
    assert [e["title"] for e in ev] == ["米国、日本車に追加関税を発動", "タカ派演出の植田日銀、本音は「連続利上げ難しい」"]
    assert ev[0]["alert"] and not ev[1]["alert"] and ev[0]["threat"] == 1.6
    assert ev[0]["chain"]["tickers_down"] == ["7203.T"]
    s = NW.summary(ev)
    dump = json.dumps(s, ensure_ascii=False)
    assert "追加関税" not in dump and "https://" not in dump                          # 公开汇总：不含标题与链接
    assert s["n_events"] == 2 and s["n_alerts"] == 1 and s["by_type"]["tariff"]["alerts"] == 1


def test_jma_quake_becomes_severe_official_event():
    q = NW.parse_jma(json.dumps([{"eid": "9", "at": (NOW - dt.timedelta(hours=1)).isoformat(), "anm": "東京湾", "mag": "7.1", "maxi": "6+"}]))
    ev = NW.analyze(q, {}, {}, now=NOW)
    assert ev[0]["events"][0] == "disaster" and ev[0]["severity"] == 3 and ev[0]["cred"] == 95 and ev[0]["alert"]


def test_new_alerts_only_once_and_expire(tmp_path):
    fp = tmp_path / "alerted.json"
    ev = [{"id": "a", "alert": True}, {"id": "b", "alert": False}]
    assert [e["id"] for e in NW.new_alerts(ev, fp, now=NOW)] == ["a"]
    assert NW.new_alerts(ev, fp, now=NOW + dt.timedelta(hours=1)) == []
    assert [e["id"] for e in NW.new_alerts(ev, fp, now=NOW + dt.timedelta(days=8))] == ["a"]   # 7 天后记录过期


def test_fetch_all_records_failures():
    def get(url):
        if "nhk" in url:
            return RSS.encode()
        if "jma" in url:
            return b"[]"
        raise TimeoutError("x")
    items, stat = NW.fetch_all(get)
    assert stat["NHK 経済"] == 2 and stat["気象庁 地震"] == 0 and str(stat["FRB"]).startswith("失败")
    assert len(items) == 6                                                           # NHK 三个频道各 2 条


def test_sector_tables_complete():
    s33 = {v for v in json.loads((NW.paths.PROJECT_ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8"))["s33"].values()}
    assert s33 <= set(NW.S33_TO_17) and len(NW.S33_TO_17) == 33
    assert set(NW.S33_TO_17.values()) == set(SECTOR_ETF_JP.values())
    for k, (lab, rx, shocks, rules, sev, neg, esc) in NW.EVENTS.items():
        assert set(shocks) <= set(NW.FACTOR_LABEL) and set(rules) <= set(SECTOR_ETF_JP.values()) and sev in (1, 2, 3), k


def test_holdings_map_falls_back_to_repo_copy(isolated_home):
    m = NW.holdings_map(["8306.T", "7203.T", "9999.T"])
    assert m == {"8306.T": "银行", "7203.T": "汽车·运输机"}
