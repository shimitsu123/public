"""qbreak/eligibility.py：下单前资格检查（被踢出 / 被指定 / 确认不了的票不开新个股仓）—— 解析、取数与保留旧值、G1〜G6、
核心 ETF、持仓报警、引擎的资格闸、执行器发买单前的最后一道、日报块、旧命令 universe-update 不再改股票池。"""
import argparse
import datetime as dt
import json

import pytest

from qbreak import eligibility as EL
from qbreak import paths
from qbreak.universes import NIKKEI225

TODAY = dt.date(2026, 9, 28)
OK = "2026-09-28T07:00+09:00"


# ── 固定的 HTML 片段 ──
def _ja_page(codes, note="2026年4月1日現在"):
    rows = "".join(f'<tr id="r">\n<td id="c">{c}</td><td><a href="x">名</a></td><td></td></tr>\n' for c in codes)
    return (f"<p>構成銘柄一覧 {note}。</p><table class='wikitable'><tr><th>証券コード</th><th>銘柄</th><th>備考</th></tr>{rows}</table>"
            "<table><tr><th>年</th><th>除外</th></tr><tr><td>9999</td><td>x</td></tr></table>")


def _en_page(codes):
    return "".join(f'<td><a href="https://www.nikkei.com/nkd/company/?scode={c}&amp;topSearchStr={c}">{c}</a></td>' for c in codes)


SUP = ("<h2>現在の指定状況</h2><h3>監理銘柄（確認中）</h3><table><tr><th>指定年月日</th><th>銘柄名</th><th>コード</th><th>市場区分 （注）</th></tr>"
       "<tr><td>2026/09/25</td><td>Ａ（株）</td><td>7133</td><td>グロース</td></tr></table>"
       "<h3>監理銘柄（審査中）</h3><table><tr><th>指定年月日</th><th>銘柄名</th><th>コード</th></tr>"
       "<tr><td>2026/04/01</td><td>Ｂ（株）</td><td>9229</td></tr></table>"
       "<h3>整理銘柄</h3><table><tr><th>指定年月日</th><th>銘柄名</th><th>コード</th></tr>"
       "<tr><td>2026/09/16</td><td>Ｃ（株）</td><td>9691</td></tr></table>")
SUP_ETF = "<h2>現在の指定状況</h2><h3>監理銘柄（確認中）</h3><p>該当なし</p>"
ALERT = ("<h1>特別注意銘柄一覧</h1><h2>現在の指定状況（2024年1月以降に指定した銘柄）</h2><table>"
         "<tr><th>銘柄名</th><th>コード</th><th>市場区分</th><th>指定日</th><th>審査状況</th></tr><tr><th>指定継続日</th></tr>"
         "<tr><td>ニデック（株）</td><td>6594</td><td>プライム</td><td>2025/10/28</td><td>審査中</td></tr><tr><td>-</td><td>-</td></tr></table>")
DELISTED = ("<table><tr><th>上場廃止日</th><th>銘柄名</th><th>コード</th><th>市場区分</th><th>上場廃止理由</th></tr>"
            "<tr><td>2026/10/19</td><td>Ｄ（株）</td><td>5484</td><td>スタンダード</td><td>支配株主等による買収（公開買付け、株式併合）</td></tr>"
            "<tr><td>2026/06/01</td><td>Ｅ（株）</td><td>1111</td><td>プライム</td><td>上場維持基準への不適合</td></tr></table>")


def _pages(ja=None, en=None):
    ja = list(NIKKEI225) if ja is None else ja
    return {EL.SOURCES["ja_wiki"]: _ja_page(ja), EL.SOURCES["en_wiki"]: _en_page(en if en is not None else ja),
            EL.SOURCES["jpx_supervision"]: SUP, EL.SOURCES["jpx_supervision_etf"]: SUP_ETF,
            EL.SOURCES["jpx_alert"]: ALERT, EL.SOURCES["jpx_delisted"]: DELISTED}


def _now(h=7):
    from qbreak.calendar_jp import JST
    return dt.datetime(2026, 9, 28, h, 0, tzinfo=JST)


# ── 解析 ──
def test_parsers_read_codes_categories_and_dates():
    x = EL.parse_ja_wiki(_ja_page(["4062", "285A", "7203"]))
    assert x["codes"] == ["285A", "4062", "7203"] and x["note"] == "2026年4月1日現在"      # 其他表（历史）不算
    assert EL.parse_en_wiki(_en_page(["6594", "7203"]))["codes"] == ["6594", "7203"]
    s = EL.parse_jpx_supervision(SUP)["items"]
    assert [(i["code"], i["cat"], i["date"]) for i in s] == [("7133", "監理銘柄（確認中）", "2026-09-25"),
                                                             ("9229", "監理銘柄（審査中）", "2026-04-01"),
                                                             ("9691", "整理銘柄", "2026-09-16")]
    assert EL.parse_jpx_supervision(SUP_ETF)["items"] == []                                  # 没有 ETF 被指定也算取到
    a = EL.parse_jpx_alert(ALERT)["items"]
    assert a == [{"code": "6594", "cat": "特別注意銘柄", "date": "2025-10-28"}]               # 续行（指定継続日 / -）跳过
    d = EL.parse_jpx_delisted(DELISTED)["items"]
    assert [(i["code"], i["date"], i["why"]) for i in d] == [("5484", "2026-10-19", "TOB・MBO・株式併合"),
                                                             ("1111", "2026-06-01", "上場維持基準不適合")]
    assert "理由" not in json.dumps(d, ensure_ascii=False) and "買収" not in json.dumps(d, ensure_ascii=False)   # 理由原文不存
    with pytest.raises(ValueError):
        EL.parse_jpx_supervision("<html>改版</html>")
    with pytest.raises(ValueError):
        EL.parse_jpx_delisted("<table><tr><th>x</th></tr></table>")


# ── 取数 ──
def test_refresh_ttl_failure_keeps_last_good_and_validation(tmp_path):
    fp = tmp_path / "e.json"
    calls = []

    def fetch(url):
        calls.append(url)
        return _pages()[url]
    s = EL.refresh(fp, now=_now(7), fetch=fetch)
    assert len(calls) == 6 and all(v["ok_at"] == _now(7).isoformat(timespec="minutes") for v in s["sources"].values())
    assert len(s["sources"]["ja_wiki"]["codes"]) == 225
    EL.refresh(fp, now=_now(8), fetch=lambda u: 1 / 0)                                     # 2 小时内：不再取
    assert len(calls) == 6

    def bad(url):
        if url == EL.SOURCES["jpx_alert"]:
            raise RuntimeError("503")
        if url == EL.SOURCES["ja_wiki"]:
            return _ja_page(["7203"] * 1 + ["4062"])                                        # 解析出 2 只 → 不用
        return _pages()[url]
    s2 = EL.refresh(fp, now=_now(10), fetch=bad)
    assert s2["sources"]["jpx_alert"]["ok_at"] == _now(7).isoformat(timespec="minutes") and "503" in s2["sources"]["jpx_alert"]["error"]
    assert s2["sources"]["jpx_alert"]["items"][0]["code"] == "6594"                          # 上次成功的内容保留
    assert len(s2["sources"]["ja_wiki"]["codes"]) == 225 and "解析出 2 只" in s2["sources"]["ja_wiki"]["error"]
    assert s2["sources"]["jpx_delisted"]["ok_at"] == _now(10).isoformat(timespec="minutes")


def test_refresh_takes_fresher_sources_from_the_repo_snapshot(tmp_path):
    mine, repo = tmp_path / "mine.json", tmp_path / "repo.json"
    old = {"sources": {"jpx_alert": {"items": [], "ok_at": "2026-09-01T07:00+09:00", "error": ""}}}
    mine.write_text(json.dumps(old), encoding="utf-8")
    repo.write_text(json.dumps({"sources": {"jpx_alert": {"items": [{"code": "6594", "cat": "特別注意銘柄", "date": "2025-10-28"}],
                                                          "ok_at": "2026-09-28T06:57+09:00", "error": ""}}}), encoding="utf-8")
    s = EL.refresh(mine, now=_now(9), fetch=lambda u: 1 / 0, fallback=repo)                  # Mac 上取不到：用云端的
    assert s["sources"]["jpx_alert"]["items"][0]["code"] == "6594" and s["sources"]["jpx_alert"]["from"]


# ── 判定 ──
def _snap(ja, en=None, sup=(), etf=(), alert=(), delisted=(), ok=OK, ok_of=None):
    ok_of = ok_of or {}
    S = lambda k, **x: {**x, "ok_at": ok_of.get(k, ok), "error": ""}                          # noqa: E731
    return {"sources": {"ja_wiki": S("ja_wiki", codes=sorted(ja)), "en_wiki": S("en_wiki", codes=sorted(en if en is not None else ja)),
                        "jpx_supervision": S("jpx_supervision", items=list(sup)),
                        "jpx_supervision_etf": S("jpx_supervision_etf", items=list(etf)),
                        "jpx_alert": S("jpx_alert", items=list(alert)), "jpx_delisted": S("jpx_delisted", items=list(delisted))}}


def test_g1_g3_membership_and_both_directions_of_the_diff():
    ours = {"1111", "2222", "3333", "6594"}
    g = EL.Gate(TODAY, ours - {"3333"}, ours, _snap({"1111", "2222", "3333", "4062"}, en=ours), {"1655"})
    assert g.entry_block("1111.T") is None
    assert "ja.wikipedia" in g.entry_block("6594.T")                                          # G3：被臨時剔除的那种
    assert "不在今天的交易股票池" in g.entry_block("3333.T") and "不在今天的交易股票池" in g.entry_block("9999.T")   # G1
    assert g.entry_block("AAPL") is None and g.pre_send("AAPL", "BUY", "stock") is None      # 美股个股不在这里查
    pn = g.panel()
    assert any("6594" in n for n in pn["needs_user"]) and any("4062" in n and "加进股票池要用户确认" in n for n in pn["needs_user"])
    assert pn["diff"]["en_wiki"]["ours_only"] == [] and pn["blocked"] == [{"code": "6594", "why": g.reasons("6594")[0]}]


def test_index_changes_explain_wikipedia_lag_and_pending_delete_blocks():
    ch = [{"announced": "2026-09-04", "effective": "2026-10-01", "add": ["5016"], "delete": ["543A"]}]
    base = {"1111", "2222"}
    pend = {"543A": {"action": "delete", "effective": "2026-10-01", "announced": "2026-09-04"}}
    g0 = EL.Gate(TODAY, base | {"543A"}, base | {"543A"}, _snap(base | {"543A"}), set(), ch, pend)
    assert "待剔除（2026-10-01 生效" in g0.entry_block("543A.T")                               # G2：公布 → 生效前一天
    after = dt.date(2026, 10, 2)
    g1 = EL.Gate(after, base | {"5016"}, base | {"5016"}, _snap(base | {"543A"}, ok="2026-10-02T07:00+09:00"), set(), ch, {})
    assert g1.entry_block("5016.T") is None                                                   # Wikipedia 还没更新：记录解释得了 → 不挡
    assert g1.diff["ja_wiki"] == {"ours_only": [], "lag": ["5016"], "src_only": []} and not g1.panel()["needs_user"]


def test_g4_g5_jpx_flags_and_delisting_window():
    ours = {"7133", "9691", "5484", "1111", "7203"}
    snap = _snap(ours, sup=EL.parse_jpx_supervision(SUP)["items"], alert=EL.parse_jpx_alert(ALERT)["items"],
                 delisted=EL.parse_jpx_delisted(DELISTED)["items"])
    g = EL.Gate(TODAY, ours, ours, snap, {"1655"})
    assert "監理銘柄（確認中）" in g.entry_block("7133.T") and "整理銘柄" in g.entry_block("9691.T")
    assert "上場廃止预定 2026-10-19（TOB・MBO・株式併合）" in g.entry_block("5484.T")
    assert g.entry_block("1111.T") is None                                                    # 废止日早于 30 天前：不算（代码可能被再用）
    assert g.entry_block("7203.T") is None
    assert {b["code"] for b in g.panel()["blocked"]} == {"7133", "9691", "5484"}


def test_g6_stale_or_missing_source_blocks_new_stock_buys_but_not_core():
    ours = {"7203"}
    g = EL.Gate(TODAY, ours, ours, _snap(ours, ok_of={"jpx_alert": "2026-09-20T07:00+09:00"}), {"1655"})
    assert g.stale == ["jpx_alert"] and "过期或取不到" in g.entry_block("7203.T")
    assert g.pre_send("1655.T", "BUY", "core") is None and g.pre_send("7203.T", "SELL", "stock") is None
    g2 = EL.Gate(TODAY, ours, ours, _snap(ours, ok_of={"en_wiki": "2026-01-01T07:00+09:00"}), {"1655"})
    assert g2.stale == [] and g2.entry_block("7203.T") is None                                 # en.wikipedia 只作参考
    g3 = EL.Gate(TODAY, ours, ours, {}, {"1655"})
    assert set(g3.stale) == set(EL.REQUIRED) and g3.entry_block("7203.T")                      # 从没取到 → 确认不了就不买
    assert any("过期或取不到" in n for n in g3.panel()["needs_user"])


def test_core_etf_flag_blocks_core_buys_only_and_held_alerts():
    ours = {"7203", "6594"}
    etf = [{"code": "1655", "cat": "整理銘柄", "date": "2026-09-25"}]
    g = EL.Gate(TODAY, ours, ours, _snap(ours, etf=etf, alert=EL.parse_jpx_alert(ALERT)["items"]), {"1655"})
    assert "整理銘柄" in g.pre_send("1655.T", "BUY", "core") and g.pre_send("1655.T", "SELL", "core") is None
    h = g.held_alerts(["6594.T", "543A.T", "1655.T", "7203.T"], "模拟盘")
    assert [(x["ticker"], x["level"]) for x in h] == [("1655.T", "warn"), ("543A.T", "info"), ("6594.T", "warn")]
    pn = g.panel(held=h)
    assert pn["core"][0]["code"] == "1655" and any("核心 ETF 1655" in n for n in pn["needs_user"])
    assert any("持仓 6594.T（模拟盘）" in n and "不自动卖" in n for n in pn["needs_user"])
    assert not any("543A" in n for n in pn["needs_user"])                                     # 按记录剔除的持仓只是提示


def test_gate_for_error_blocks_new_stock_buys(monkeypatch):
    monkeypatch.setattr(EL, "refresh", lambda **k: 1 / 0)
    g = EL.gate_for(TODAY, ["7203.T"], ["1655.T"])
    assert g.error and "资格检查出错" in g.entry_block("7203.T") and g.pre_send("1655.T", "BUY", "core") is None
    assert g.held_alerts(["7203.T"]) == [] or all(x["level"] == "info" for x in g.held_alerts(["7203.T"]))


def test_gate_for_uses_todays_universe_and_index_changes(monkeypatch):
    (paths.home() / "index_changes.json").write_text(json.dumps({"JP": [
        {"announced": "2026-09-04", "effective": "2026-10-01", "add": ["5016"], "delete": ["543A"]}]}), encoding="utf-8")
    pages = _pages()
    g = EL.gate_for(TODAY, [f"{c}.T" for c in NIKKEI225], ["1655.T"], fetch=lambda u: pages[u])
    assert not g.stale and g.diff["ja_wiki"]["ours_only"] == [] and "待剔除" in g.entry_block("543A.T")
    assert "JPX 特別注意銘柄" in (g.reasons("6594") or [""])[0]                               # 旧名单里还有 6594 的话也会被 JPX 挡住
    assert (paths.out_dir() / EL.FILE).exists()


# ── 引擎 / 执行器 ──
def test_engine_gate_blocks_entry_and_logs_reason():
    from test_live_unified import _scenario
    make, start = _scenario([1000.0] * 30, entry=(10,), bear_all=True)
    free = make().run(start)
    assert "A.T" in set(free.trades["ticker"])                                               # 不设闸门：照常买
    eng = make()
    eng.entry_gate_fn = lambda t, i: "JPX 特別注意銘柄（测试）" if t == "A.T" else None
    res = eng.run(start)
    assert "A.T" not in set(res.trades["ticker"]) and eng.skipped["gate"] >= 1
    assert eng.gate_log[0][1:] == ("A.T", "JPX 特別注意銘柄（测试）")


def test_executor_pre_send_skips_flagged_buy_and_never_sends_it():
    from test_live_unified import NEW, _scenario
    from qbreak.brokers.tachibana import TachibanaBroker
    from qbreak.brokers.tachibana_sim import SimExchange
    from qbreak.live_unified import UnifiedExecutor
    make, start = _scenario([1000.0] * 30, entry=(10,), bear_all=True)
    eng = make()
    exch = SimExchange(eng, cash=eng.st.cash_jpy)
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book.json", paper=False, check_clock=False,
                         pre_send=lambda t, side, kind: "JPX 整理銘柄（测试）" if t == "A.T" and side == "BUY" else None)
    lo = int(eng.gidx.searchsorted(start))
    eng.prime(lo)
    for k in range(lo, 11):
        exch.open(k)
        ux.open_phase()
        exch.close_day()
        exch.set_day(k + 1)
        ux.run_bar(k)
    o = [x for x in ux.orders if x.ticker == "A.T"][0]
    assert o.status == "SKIPPED" and o.note.startswith("资格检查：") and exch.calls.get(NEW, 0) == 0
    assert ux.stats["gate"] == 1 and any("资格检查" in e["msg"] for e in ux.events + ux.book.get("events", []))
    ux.morning([])                                                                            # 同一决策重跑：不重发
    assert exch.calls.get(NEW, 0) == 0


def test_daily_text_and_report_show_eligibility_alerts():
    from qbreak.live_unified import daily_text
    from qbreak.report_unified import _eligibility_html, missing_items
    from qbreak.unified import UState
    ours = {"7203", "6594"}
    g = EL.Gate(TODAY, ours, ours, _snap(ours, alert=EL.parse_jpx_alert(ALERT)["items"]), {"1655"})
    pn = g.panel(held=g.held_alerts(["6594.T"], "执行器"), blocked_today=[{"date": "2026-09-25", "ticker": "6594.T", "why": "x"}])
    sm = {"decided_on": "2026-09-25", "fill_day": "2026-09-28", "orders": [], "eligibility": pn}
    title, short, body = daily_text(sm, UState(cash_jpy=1e6), None, True, 1e6)
    assert "★ 资格检查要确认" in short and "持仓 6594.T（执行器）" in body
    html = _eligibility_html({"eligibility": pn}, ({}, {}, {"6594": "ニデック"}))
    assert "下单前资格检查" in html and "6594 ニデック" in html and "今天被挡掉的信号" in html
    miss = missing_items({"eligibility": pn})
    assert any(m.startswith("下单前资格检查（告警，不是缺数据）") and "6594" in m for m in miss)


def test_universe_fix_and_universe_update_no_longer_overwrites(monkeypatch, capsys):
    assert "6594" not in NIKKEI225 and "4062" in NIKKEI225 and len(set(NIKKEI225)) == 225
    import run
    pages = _pages()
    monkeypatch.setattr(EL, "_fetch_url", lambda u: pages[u])
    rc = run.cmd_universe_update(argparse.Namespace())
    assert rc == 0 and not (paths.home() / "universe_JP.json").exists()
    out = capsys.readouterr().out
    assert "不再改股票池" in out and "JPX 特別注意銘柄" in out
