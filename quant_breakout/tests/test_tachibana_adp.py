"""立花适配器的 B 组修补（〔77〕B：B8 / B9 / B2 第 1 点 / B16 的 TA-07・TA-16・TA-10・C-15・C-14・TA-11・TA-12・OPS-12）：
① 约定确认遇到终态（被拒 / 失效 / 取消完了）马上停、记 REJECTED / EXPIRED，执行器第二天按已成交的部分对账；
② 盘中指値夹在制限値幅里（ストップ安附近的卖单按下限价挂）、取不到现价的盘中卖单不发成行；
③ 发送失败分类：请求根本没发出 → BLOCKED（可以重试），可能已到达 → ERROR（状态不明），受理应答缺注文番号 → ERROR；
④ 错误码对照表、第二暗証错了不连着发、钥匙串锁着的提示、仕様覆盖文件只读和默认不同的键、单元未满株、2027-03 的呼値表、
   上线门槛的钥匙串试读 / 时钟 / 覆盖文件版本。
全部用 FakeTransport / 模拟交易所 / 假的 subprocess.run：不联网、不调真的 security / sntp。"""
import datetime as dt
import errno
import http.client
import json
import socket
import ssl
import subprocess
import types
import urllib.error

import pandas as pd
import pytest

from qbreak import paths
from qbreak import run_status as RS
from qbreak.brokers import tachibana as TB
from qbreak.brokers.base import BrokerError
from qbreak.brokers.tachibana import Credentials, TachibanaBroker, TachibanaSpec
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST

from test_live_ops import _fake_run
from test_live_unified import _frame, _scenario
from test_manual_orders import _Run, _sell_req
from test_tachibana import PEM, SPEC, _arm, _broker, _master, _orders


def _detail(code, filled="0", px="", text=None):
    r = {"p_errno": "0", "sResultCode": "0", "sOrderStatusCode": code, "sYakuzyouSuryou": filled, "sYakuzyouPrice": px}
    if text is not None:
        r["sOrderStatus"] = text
    return r


def _details(tr):
    return [p for _, p in tr.sent if p.get("sCLMID") == SPEC.clm_order_detail]


# ────────── B8 约定状态码：终态马上停、REJECTED / EXPIRED ──────────
@pytest.mark.parametrize("code,text,filled,want", [
    ("12", "全部失効", "0", "EXPIRED"),
    ("2", "受付エラー", "0", "REJECTED"),
    ("7", None, "0", "EXPIRED"),                       # 取消完了（在立花网站上撤了）：不会再成交 → EXPIRED；没有状态名称 → 用 spec 的名字
    ("11", "一部失効", "50", "EXPIRED"),               # 成交一半、其余失效：已成交的照记
])
def test_confirm_stops_polling_on_a_terminal_status(monkeypatch, code, text, filled, want):
    monkeypatch.setattr(TB, "_sleep", lambda s: None)
    b, tr = _broker(responses={SPEC.clm_order_detail: _detail(code, filled, "3000" if filled != "0" else "", text)},
                    confirm_timeout_s=30.0)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == want and o.filled_qty == int(filled)
    assert len(_details(tr)) == 1                                          # 第一次查到终态就停（不等 30 秒）
    assert f"sOrderStatusCode={code}" in o.note and (text or "取消完了") in o.note
    assert ("其余不会再成交" if filled != "0" else "不会再成交") in o.note


def test_order_status_final_state_codes():
    b, _ = _broker()
    assert [b.final_state(c) for c in ("10", "2", "14", "7", "11", "12", "19", "1", "9", "")] == \
        ["FILLED", "REJECTED", "REJECTED", "CANCELLED", "EXPIRED", "EXPIRED", "EXPIRED", "", "", ""]
    b2, _ = _broker()
    b2.spec = TachibanaSpec(status_expired="12,99")                         # デモ核对后可在 tachibana_spec.json 改
    assert b2.final_state("99") == "EXPIRED" and b2.final_state("11") == ""


class _HalfExpire(SimExchange):
    """盘中卖 A.T：成交一半，其余马上在交易所那边失效（一部失効 = 11）。"""

    def _fill(self, o, op):
        if o["side"] == "SELL" and o["ticker"] == "A.T" and o["cond"] == self.spec.cond_normal:
            full = o["qty"]
            o["qty"] = full // 2
            super()._fill(o, op)
            o.update(qty=full, status="11")
            return
        super()._fill(o, op)


def test_expired_partial_now_order_is_shown_and_reconciled_by_filled_qty():
    r = _Run([1000.0] * 40, exchange_cls=_HalfExpire, entry=(10,), bear_all=True)
    r.until(14)
    held = r.eng.st.pos["A.T"].shares
    assert held >= 200
    rec = _sell_req(r)
    res = r.session(10, 0)
    it = r.item(rec["id"])
    o = [x for x in r.ux.orders if x.ticker == "A.T" and x.phase == "now"][0]
    assert o.status == "EXPIRED" and o.filled_qty == held // 2 and "一部失効" in o.note
    assert res["placed"] == 1 and "其余已失效" in it["msg"]
    bad = RS.bad_orders([o.__dict__])
    assert bad and RS.STATUS_TEXT[bad[0]["status"]] == "已失效"                    # 面板 / 通知：「已失效」
    r.day()                                                                         # 第二天早上：按已成交的部分对账
    assert not r.ux.blocked                                                         # 账本 = 券商（没有「持仓不一致」）
    assert r.eng.st.pos["A.T"].shares == held - held // 2 and r.eng.st.pending_exit.get("A.T") == "manual"
    hist = [x for h in r.ux.book["history"] for x in h["orders"] if x["cid"] == o.cid][0]
    assert hist["status"] == "EXPIRED" and hist["filled_qty"] == held // 2


def test_morning_reconcile_writes_the_terminal_status_name_into_the_note():
    """寄付卖单遇到一整天ストップ安：立花那边全部失効 → 对账时把状态名称记进 note（以前只写「寄付注文を受付」）。"""
    a = [1000.0] * 20 + [700.0] * 10
    from test_live_unified import rehearse
    make, start = _scenario(a, entry=(10,), dead=(19,), lock=(20,))
    r = rehearse(make, start, kind="tachibana-sim")
    sells = [o for h in r["ux"].book["history"] for o in h["orders"] if o["ticker"] == "A.T" and o["side"] == "SELL"]
    assert [o["status"] for o in sells] == ["UNFILLED", "FILLED"]
    assert "sOrderStatusCode=12" in sells[0]["note"]


# ────────── B9 / TA-12 盘中指値夹在値幅里；取不到现价不发成行 ──────────
def _quote(price, prev):
    def f(p):
        return {"p_errno": "0", SPEC.r_price_list: [{"sIssueCode": c, "pDPP": price, "pPRP": prev}
                                                   for c in p[SPEC.f_target_codes].split(",")]}
    return f


def test_intraday_sell_near_limit_down_is_clamped_to_the_lower_limit():
    b, tr = _broker(responses={SPEC.clm_price: _quote("700", "1000")})           # 前日終値 1,000 → 値幅 300 → 下限 700
    _arm()
    o = b.sell("7203.T", 100, client_id="s1")
    assert _orders(tr)[0]["sOrderPrice"] == "700" and o.price == 700.0           # 700 × 0.995 = 696.5 → 697 < 下限 → 按下限挂
    b2, tr2 = _broker(responses={SPEC.clm_price: _quote("700", "")})             # 前日終値取不到 → 不夹（照旧）
    _arm()
    b2.sell("7203.T", 100, client_id="s2")
    assert _orders(tr2)[0]["sOrderPrice"] == "697"


def test_intraday_sell_is_not_clamped_when_the_quote_is_outside_the_computed_band():
    """现价已经在按前日終値算的値幅外（前一天没成交的ストップ安 = 基準値段是最終特別気配 / 値幅扩大 / 拆股前日終値没调整）
    → 算出来的値幅不对：不夹（夹到 700 = 比现价高 17%，卖单成交不了），照「现价 −0.5%」挂。"""
    b, tr = _broker(responses={SPEC.clm_price: _quote("600", "1000")})
    _arm()
    o = b.sell("7203.T", 100, client_id="s1")
    assert _orders(tr)[0]["sOrderPrice"] == "597" and o.price == 597.0
    b2, tr2 = _broker(responses={SPEC.clm_price: _quote("1400", "1000")})        # 买单同理：现价在上限之外 → 不夹
    _arm()
    b2.buy("7203.T", 100, client_id="b1")
    assert _orders(tr2)[0]["sOrderPrice"] == "1407"


def test_intraday_buy_near_limit_up_is_clamped_to_the_upper_limit():
    b, tr = _broker(responses={SPEC.clm_price: _quote("1300", "1000")})          # 上限 1,300
    _arm()
    b.buy("7203.T", 100, client_id="b1")                                         # 1300 × 1.005 = 1306.5 → 1306 > 上限 → 1300
    assert _orders(tr)[0]["sOrderPrice"] == "1300"
    b2, tr2 = _broker(responses={SPEC.clm_price: _quote("1300", "1000")})
    _arm()
    b2.buy("7203.T", 100, limit=1290.0, client_id="b2")                          # 执行器给的限价在値幅内：不动
    assert _orders(tr2)[0]["sOrderPrice"] == "1290"


def test_opening_orders_are_not_clamped():
    b, tr = _broker(responses={SPEC.clm_price: _quote("", "1000")})
    _arm()
    b.sell("7203.T", 100, client_id="s1", bar="2026-10-08")
    assert _orders(tr)[0]["sOrderPrice"] == SPEC.price_market                    # 寄付成行照旧


def test_intraday_sell_without_a_price_is_blocked_not_sent_as_market():
    b, tr = _broker(responses={SPEC.clm_price: _quote("", "")})
    _arm()
    o = b.sell("7203.T", 100, client_id="s1")
    assert o.status == "BLOCKED" and "取不到现价" in o.note and "成行" in o.note and not _orders(tr)


def test_sim_exchange_rejects_limits_outside_the_band_and_the_adapter_clamps_into_it():
    """模拟交易所：前日終値 1,000、开盘 700（ストップ安）。盘中手动卖出：适配器按下限 700 挂 → 受理、成交；
    不夹的 697 交易所不受理（値幅外）。"""
    n = 30
    op = [1000.0] * n
    op[15] = 700.0
    r = _Run([1000.0] * n, a_open=op, entry=(10,), bear_all=True)
    r.until(14)
    _sell_req(r)
    r.session(10, 0)
    o = [x for x in r.ux.orders if x.ticker == "A.T" and x.phase == "now"][0]
    assert o.status == "FILLED", o.note
    sent = [x for x in r.exch.orders.values() if x["ticker"] == "A.T" and x["side"] == "SELL" and x["cond"] == SPEC.cond_normal]
    assert sent and sent[-1]["lim"] == 700.0

    def sell(code, px):
        return r.exch.get_json("x", {"sCLMID": SPEC.clm_new_order, "sSecondPassword": "x", "sIssueCode": code, "sBaibaiKubun": "1",
                                     "sOrderSuryou": "100", "sCondition": "0", "sOrderPrice": px})
    bad = sell("A", "697")                                                          # 不夹的价：下限 700 之外
    assert bad["sResultCode"] == "991014" and "値幅" in bad["sResultText"]
    r.exch.pos["B.T"] = 100                                                         # B.T：前日終値 1,500、値幅 400 → 1,100〜1,900
    assert sell("B", "1100")["sResultCode"] == "0"
    assert sell("B", "1099")["sResultCode"] == "991014"
    assert sell("B", "1100.5")["sResultCode"] == "991013"                          # 不在呼値的格子上


# ────────── B2 第 1 点 发送失败分类 / M3 ──────────
def test_login_failure_before_sending_is_blocked_not_unknown():
    b, tr = _broker(responses={SPEC.clm_login: {"p_errno": "-50", "p_err": "ログインエラー。"}})
    _arm()
    o = b.sell("7203.T", 100, client_id="s1", bar="2026-10-08")
    assert o.status == "BLOCKED" and "登录失败，没发单" in o.note and not _orders(tr)


@pytest.mark.parametrize("exc,want", [
    (urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")), "BLOCKED"),   # DNS 解析失败
    (urllib.error.URLError(ConnectionRefusedError(61, "Connection refused")), "BLOCKED"),       # 连接被拒
    (urllib.error.URLError(ssl.SSLError(1, "handshake failure")), "BLOCKED"),                   # TLS 握手失败
    (urllib.error.URLError(OSError(errno.ENETUNREACH, "Network is unreachable")), "BLOCKED"),   # 没有路由
    (urllib.error.URLError(TimeoutError("timed out")), "ERROR"),                                # 超时：可能已到达
    (urllib.error.URLError(ConnectionResetError(54, "reset")), "ERROR"),                        # 发送中途断开
    (http.client.RemoteDisconnected("Remote end closed connection"), "ERROR"),                  # 应答没收到
    (TimeoutError("read timed out"), "ERROR"),
    (json.JSONDecodeError("bad", "x", 0), "ERROR"),                                             # 应答解析失败
    (ConnectionError("模拟网络错误"), "ERROR"),
])
def test_send_failures_are_classified(exc, want):
    b, tr = _broker()
    _arm()
    b.login()
    tr.fail_next, tr.fail_with = SPEC.clm_new_order, exc
    o = b.sell("7203.T", 100, client_id="s1", bar="2026-10-08")
    assert o.status == want and len(_orders(tr)) == 1                              # 发单类绝不自动重发
    assert ("没连上立花，没发单" if want == "BLOCKED" else "状态不明") in o.note
    assert "://" not in o.note                                                      # 不带 URL（虚拟 URL 带会话）


def test_acceptance_without_order_number_is_unknown_not_sent():
    b, _ = _broker(responses={SPEC.clm_new_order: {"p_errno": "0", "sResultCode": "0", "sOrderNumber": "", "sEigyouDay": "20261008"}})
    _arm()
    o = b.sell("7203.T", 100, client_id="s1", bar="2026-10-08")
    assert o.status == "ERROR" and "注文番号" in o.note
    b2, _ = _broker(responses={SPEC.clm_new_order: {"p_errno": "0", "sResultCode": "0", "sOrderNumber": "A1"}})
    _arm()
    assert b2.sell("7203.T", 100, client_id="s2", bar="2026-10-08").status == "ERROR"


def test_keychain_mdat_reads_only_the_attribute():
    out = ('keychain: "/x/login.keychain-db"\nattributes:\n    "acct"<blob>="qbreak"\n'
           '    "mdat"<timedate>=0x32303236313030393031303230335A00  "20261009010203Z\\000"\n')
    seen = []

    def run(args, **kw):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, out, "")
    assert TB.keychain_mdat("qbreak-tachibana-2nd", run=run) == "20261009010203Z"
    assert "-w" not in seen[0]                                                           # 不读值
    assert TB.keychain_mdat("x", run=lambda a, **k: subprocess.CompletedProcess(a, 44, "", "")) == ""


# ────────── C-15 错误码对照表 / IPv4 ──────────
def test_error_table_explains_known_codes_and_keeps_raw_text_otherwise():
    b, _ = _broker(responses={SPEC.clm_buying_power: {"p_errno": "8", "p_err": "p_sd_date が不正です"}})
    with pytest.raises(BrokerError) as ei:
        b.cash()
    assert "p_errno=8" in str(ei.value) and "日期与时间" in str(ei.value) and "自动设置" in str(ei.value)
    b2, _ = _broker(responses={SPEC.clm_buying_power: {"p_errno": "0", "sResultCode": "11041", "sResultText": "NISA"}})
    with pytest.raises(BrokerError, match="NISA 口座"):
        b2.cash()
    b3, _ = _broker(responses={SPEC.clm_buying_power: {"p_errno": "0", "sResultCode": "77777", "sResultText": "なにか"}})
    with pytest.raises(BrokerError) as ei:
        b3.cash()
    assert str(ei.value).endswith("sResultCode=77777 なにか")                    # 表里没有：只显示原文
    assert b.explain("", "99", "買付余力が不足しています").startswith("买付余力不足")
    assert b.explain("", "99", "値幅制限の範囲外").startswith("限价在当天的制限値幅之外")


def test_login_failure_message_uses_the_table_or_lists_more_causes():
    b, _ = _broker(responses={SPEC.clm_login: {"p_errno": "8", "p_err": "時刻エラー"}})
    with pytest.raises(BrokerError) as ei:
        b.login()
    assert "日期与时间" in str(ei.value) and "利用設定" not in str(ei.value)       # 认出了原因：只给那条修法
    b2, _ = _broker(responses={SPEC.clm_login: {"p_errno": "-50", "p_err": "ログインエラー。"}})
    with pytest.raises(BrokerError) as ei:
        b2.login()
    for w in ("利用設定", "自动设置", "IPv4", "パスキー", "版本"):
        assert w in str(ei.value)


def test_spec_tables_can_be_overridden_and_unknown_messages_still_work():
    fp = paths.home() / "tachibana_spec.json"
    fp.write_text(json.dumps({"err_result": {"12345": "测试原因：测试修法"}}), encoding="utf-8")
    b = TachibanaBroker(transport=TB.FakeTransport(), spec=TachibanaSpec.load(), creds=Credentials("A", PEM, "x"))
    assert b.explain("", "12345", "") == "测试原因：测试修法" and b.explain("", "11041", "") == ""


def test_http_transport_can_force_ipv4(monkeypatch):
    assert TB.HttpTransport().ipv4 is False
    monkeypatch.setenv("QBREAK_TACHIBANA_IPV4", "1")
    t = TB.HttpTransport()
    assert t.ipv4 is True and t._open is not TB.urllib.request.urlopen
    seen = {}

    def gai(host, port, family=0, type_=0, *a):
        seen["family"] = family
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))]

    def cc(sa, timeout=None, source_address=None):
        seen["addr"] = sa
        return "sock"
    monkeypatch.setattr(TB.socket, "getaddrinfo", gai)
    monkeypatch.setattr(TB.socket, "create_connection", cc)
    assert TB._connect_v4(("kabuka.e-shiten.jp", 443), 5) == "sock"
    assert seen == {"family": socket.AF_INET, "addr": ("192.0.2.1", 443)}
    c = TB._V4HTTPSConnection("kabuka.e-shiten.jp", 443)
    assert c._create_connection is TB._connect_v4 and c.host == "kabuka.e-shiten.jp"   # 证书核对照旧用主机名
    monkeypatch.delenv("QBREAK_TACHIBANA_IPV4")
    assert TachibanaBroker(creds=Credentials("A", PEM, "x")).tr.ipv4 is False
    (paths.home() / "tachibana_spec.json").write_text('{"force_ipv4": true}', encoding="utf-8")   # 定时任务读得到的设法
    assert TachibanaBroker(creds=Credentials("A", PEM, "x")).tr.ipv4 is True


# ────────── OPS-12 第二暗証错了：这次运行后面的单都不发 ──────────
def test_wrong_second_password_stops_the_rest_of_this_run():
    b, tr = _broker(responses={SPEC.clm_new_order: {"p_errno": "0", "sResultCode": "991004",
                                                    "sResultText": "第二暗証番号が違います"}})
    _arm()
    o1 = b.sell("7203.T", 100, client_id="s1", bar="2026-10-08")
    o2 = b.sell("7203.T", 100, client_id="s2", bar="2026-10-08")
    o3 = b.buy("7203.T", 100, limit=2990.0, client_id="b1", bar="2026-10-08")
    assert o1.status == "REJECTED" and "第二暗証番号不对" in o1.note                  # 对照表的说明附在原文后面
    assert o2.status == o3.status == "BLOCKED" and "qbreak-tachibana-2nd" in o2.note and "-U" in o2.note
    assert len(_orders(tr)) == 1                                                     # 只发了第一笔
    b2, tr2 = _broker(responses={SPEC.clm_new_order: {"p_errno": "0", "sResultCode": "991020", "sResultText": "買付余力不足"}})
    _arm()
    b2.sell("7203.T", 100, client_id="s1", bar="2026-10-08")
    assert b2.sell("7203.T", 100, client_id="s2", bar="2026-10-08").status == "REJECTED"   # 别的拒单不连坐
    assert len(_orders(tr2)) == 2


def test_wrong_second_password_from_the_keychain_also_stops_later_runs(monkeypatch):
    """第二暗証来自钥匙串、被拒 → 记进数据目录：之后的运行（08:35 / 09:05 / 面板，新的进程）不再用同一个值发单；
    你重新存了钥匙串（条目的修改时刻变了）→ 再试一次（ADP-2：连错几次会锁取引暗証）。"""
    mdat = {"v": "20261001000000Z"}
    monkeypatch.setattr(TB, "keychain_mdat", lambda svc, account="qbreak", run=None: mdat["v"])
    bad = {SPEC.clm_new_order: {"p_errno": "0", "sResultCode": "991004", "sResultText": "第二暗証番号が違います"}}
    kc = Credentials("AUTH-XYZ", PEM, "2nd-pw", "", "keychain")
    b, tr = _broker(responses=bad, creds=kc)
    _arm()
    assert b.sell("7203.T", 100, client_id="s1", bar="2026-10-08").status == "REJECTED"
    f = paths.state_dir() / "second_pw_bad.json"
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["mdat"] == "20261001000000Z" and set(rec) == {"at", "mdat"}                # 只记时刻（没有值）
    b2, tr2 = _broker(creds=Credentials("AUTH-XYZ", PEM, "2nd-pw", "", "keychain"))      # 下一次运行（新进程）
    o = b2.sell("7203.T", 100, client_id="s2", bar="2026-10-08")
    assert o.status == "BLOCKED" and "上次被拒" in o.note and "-U" in o.note and not _orders(tr2)
    mdat["v"] = "20261009070000Z"                                                        # 你重新存了钥匙串
    b3, tr3 = _broker(creds=Credentials("AUTH-XYZ", PEM, "2nd-pw", "", "keychain"))
    assert b3.sell("7203.T", 100, client_id="s3", bar="2026-10-08").status == "SENT" and len(_orders(tr3)) == 1
    assert not f.exists()
    b4, _ = _broker(responses=bad)                                                       # 直接给的（环境变量 / 测试）：只在这次运行里挡
    b4.sell("7203.T", 100, client_id="s4", bar="2026-10-08")
    assert not f.exists()
    from qbreak import live_gate as G
    f.write_text(json.dumps({"at": "2026-10-09T07:40:00+09:00", "mdat": ""}), encoding="utf-8")
    it = {x["name"]: x for x in G.check(agents=paths.home() / "ag", run=_fake_run()[0], today=dt.date(2026, 10, 9))}
    assert it["⑥ 第二暗証番号"]["ok"] is False and "2026-10-09 07:40" in it["⑥ 第二暗証番号"]["text"]


# ────────── TA-07 钥匙串：没有这个条目 vs 锁着 ──────────
def _security(rc, err=""):
    def run(args, **kw):
        assert args[:2] == ["security", "find-generic-password"]
        return subprocess.CompletedProcess(args, rc, "", err)
    return run


def test_keychain_distinguishes_missing_from_locked():
    assert TB._keychain("svc-a", "qbreak", run=_security(44, "could not be found")) is None
    assert TB._KC_WHY["svc-a"] == TB.KC_MISSING
    assert TB._keychain("svc-b", "qbreak", run=_security(36, "User interaction is not allowed.")) is None
    assert TB._KC_WHY["svc-b"] == TB.KC_LOCKED
    assert TB.keychain_why(1, "The specified keychain could not be found / keychain is locked") == TB.KC_LOCKED
    assert TB.keychain_why(None) == TB.KC_NONE and TB.keychain_why(1, "?") == TB.KC_ERROR
    assert TB._keychain("svc-c", "qbreak", run=lambda a, **k: subprocess.CompletedProcess(a, 0, "v\n", "")) == "v"
    assert "svc-c" not in TB._KC_WHY


def test_locked_keychain_gives_unlock_hint_not_missing(tmp_path, monkeypatch):
    for k in ("TACHIBANA_AUTH_ID", "TACHIBANA_AUTH_ID_FILE", "TACHIBANA_SECOND_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(TB.subprocess, "run", _security(36, "User interaction is not allowed."))
    with pytest.raises(BrokerError) as ei:
        Credentials.from_env()
    assert "解锁" in str(ei.value) and "缺少认证 ID" not in str(ei.value)
    kp = tmp_path / "k.pem"
    kp.write_bytes(PEM)
    kp.chmod(0o600)
    monkeypatch.setenv("TACHIBANA_PRIVATE_KEY", str(kp))
    monkeypatch.setenv("TACHIBANA_AUTH_ID", "AUTH")
    c = Credentials.from_env()
    assert c.second_password == "" and "解锁" in c.second_why and "second_why" not in repr(c)
    b, tr = _broker(creds=c)
    _arm()
    o = b.sell("7203.T", 100, client_id="s1", bar="2026-10-08")
    assert o.status == "BLOCKED" and "解锁" in o.note and not _orders(tr)


def test_gate_trial_read_never_takes_the_value_into_the_process(tmp_path, monkeypatch):
    from qbreak import live_gate as G
    monkeypatch.setenv("HOME", str(tmp_path))
    run_, calls = _fake_run(security=0, security_read=(36, "User interaction is not allowed."))
    it = {x["name"]: x for x in G.check(agents=tmp_path, run=run_)}["⑥ 钥匙串能读出（和定时任务相同的读法）"]
    assert it["ok"] is False and "解锁" in it["text"] and "不用重新存密钥" in it["text"]
    assert [c for c in calls if c[0] == "security" and "-w" in c]                 # 试读过（假的 run 断言了 stdout = DEVNULL）
    run_, _ = _fake_run(security=0)
    it = {x["name"]: x for x in G.check(agents=tmp_path, run=run_)}["⑥ 钥匙串能读出（和定时任务相同的读法）"]
    assert it["ok"] is True and "都能读出" in it["text"]
    run_, calls = _fake_run(security=44)
    names = [x["name"] for x in G.check(agents=tmp_path, run=run_)]
    assert "⑥ 钥匙串能读出（和定时任务相同的读法）" not in names                    # 条目都没有：不试读


# ────────── TA-16 时钟 ──────────
@pytest.mark.parametrize("sntp,ok,word", [
    ((0, "+0.004512 +/- 0.010329 time.apple.com 17.253.4.125\n"), True, "+0.00 秒"),
    ((0, "-45.2 +/- 0.01 time.apple.com 17.253.4.125\n"), False, "自动设置"),
    (None, None, "不是 macOS"),
    ((1, "sntp: Exchange failed: timeout\n"), None, "查不了"),
])
def test_gate_clock_check(tmp_path, monkeypatch, sntp, ok, word):
    from qbreak import live_gate as G
    monkeypatch.setenv("HOME", str(tmp_path))
    run_, _ = _fake_run(security=44, sntp=sntp)
    it = {x["name"]: x for x in G.check(agents=tmp_path, run=run_)}["⑥ Mac 的时钟（立花要求和服务器差 30 秒以内）"]
    assert it["ok"] is ok and word in it["text"]


def test_gate_clock_falls_back_to_systemsetup():
    from qbreak import live_gate as G

    def run_(args, **kw):
        if args[0] == "sntp":
            raise FileNotFoundError("sntp")
        return subprocess.CompletedProcess(args, 0, "Network Time: Off\n", "")
    ok, txt = G._clock(run_)
    assert ok is False and "自动对时关着" in txt


# ────────── TA-10 / OPS-05 仕様覆盖文件 ──────────
def test_old_full_dump_only_overrides_changed_keys_and_flags_the_old_version(caplog):
    fp = paths.home() / "tachibana_spec.json"
    old = dict(TachibanaSpec().__dict__)                                            # 旧代码导出的「全部字段」
    old["base_live"] = "https://kabuka.e-shiten.jp/e_api_v4r9/"
    old["r_cash"] = "sMyCash"                                                       # 用户改过的键
    fp.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    info = TB.override_info()
    assert info["keys"] == ["base_live", "r_cash"]                                  # 和默认一样的键不算覆盖
    assert info["stale"] == [("base_live", "e_api_v4r9", "e_api_v4r10")]
    with caplog.at_level("WARNING"):
        s = TachibanaSpec.load()
    assert s.r_cash == "sMyCash" and s.base_live.endswith("/e_api_v4r9/")          # 照用（是你写的），但提醒
    assert "旧版本" in caplog.text
    from qbreak import live_gate as G
    items = []
    G._spec_override(lambda g, n, ok, t: items.append((ok, t)))
    assert items[0][0] is False and "★ 覆盖文件还指向旧版本" in items[0][1]


def test_dump_writes_only_changed_keys_and_a_reference_copy():
    p = TachibanaSpec().dump_template()
    d = json.loads(open(p, encoding="utf-8").read())
    assert set(d) == {"_说明"} and "现在和默认完全一样" in d["_说明"]
    ref = json.loads((paths.home() / "tachibana_spec_defaults.json").read_text(encoding="utf-8"))
    assert ref["base_live"] == TachibanaSpec().base_live
    assert TachibanaSpec.load() == TachibanaSpec()                                  # 只有说明 → 等于默认（「_」开头的键不读、不报未知）
    s = TachibanaSpec(r_cash="sX")
    d = json.loads(open(s.dump_template(), encoding="utf-8").read())
    assert {k for k in d if not k.startswith("_")} == {"r_cash"} and TachibanaSpec.load().r_cash == "sX"
    from qbreak import live_gate as G
    items = []
    G._spec_override(lambda g, n, ok, t: items.append((ok, t)))
    assert items[0] == (True, "生效中，覆盖的键：r_cash")


# ────────── C-14 单元未满株 ──────────
def test_odd_lot_sell_sends_whole_lots_and_reports_the_rest():
    b, tr = _broker()                                                              # 立花マスタ：7203 売買単位 100
    _arm()
    o = b.sell("7203.T", 150, client_id="s1", bar="2026-10-08")
    assert _orders(tr)[0]["sOrderSuryou"] == "100" and o.qty == 100 and o.status == "SENT"
    assert o.extra["odd_lot"] == 50 and o.extra["lot"] == 100 and "50 股不足一手" in o.note and "立花网站" in o.note
    o2 = b.sell("7203.T", 50, client_id="s2", bar="2026-10-08")
    assert o2.status == "BLOCKED" and "50 股不足一手" in o2.note and len(_orders(tr)) == 1
    assert o2.extra == {"odd_lot": 50, "lot": 100}                                 # 执行器的零股记录按立花的売買単位
    (paths.home() / "cache" / "tachibana_master.json").unlink()                     # 同一天的缓存（上面那个进程取的）
    b3, tr3 = _broker(responses=_master(stk=[]), max_order_value=1_000_000)         # 一手不知道（マスタ里没有）→ 照旧整笔下
    _arm()
    b3.sell("7203.T", 150, client_id="s3", bar="2026-10-08")
    assert _orders(tr3)[0]["sOrderSuryou"] == "150"


def test_sim_exchange_rejects_odd_lot_sells():
    make, _ = _scenario([1000.0] * 30)
    exch = SimExchange(make(), cash=1_000_000)
    exch.set_day(10)
    exch.pos["A.T"] = 150
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, check_tradable=False)
    o = b.sell("A.T", 150, client_id="x1", bar="2026-01-16")
    assert o.status == "REJECTED" and "991022" in o.note and "単元未満" in o.note
    b2 = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False)   # 查マスタ：整数手照常下
    o2 = b2.sell("A.T", 150, client_id="x2", bar="2026-01-16")
    assert o2.status == "SENT" and o2.qty == 100 and o2.extra["odd_lot"] == 50


# ────────── TA-11 2027-03-01 起：一手 1 口的 ETF 用 O 表 ──────────
def _at_2027(monkeypatch, hh=10):
    monkeypatch.setattr(TB, "_now_dt", lambda: dt.datetime(2027, 3, 1, hh, 0, tzinfo=JST))


@pytest.mark.parametrize("unit,want", [("1", "357"), ("10", "357.5")])
def test_core_etf_limit_follows_the_unit_after_2027_03(monkeypatch, unit, want):
    """1545（立花マスタ的売買単位是多少就按多少）：一手 1 口 → O 表（1 円）；一手 10 口 → C 表（100〜500 円带 0.5 円）。"""
    _at_2027(monkeypatch)
    stk = [{"sIssueCode": "1545", "sYusenSizyou": "00", "sBaibaiTani": unit, "sBaibaiTeisiC": " "}]
    mkt = [{"sIssueCode": "1545", "sZyouzyouSizyou": "00", "sIssueKubunC": " ", "sZyouzyouKubun": "01",
            "sZyouzyouHaisiDay": "00000000"}]
    b, tr = _broker(responses=_master(stk, mkt))
    _arm()
    b.buy("1545.T", 10, limit=357.714, client_id="c1", bar="2027-02-26")
    assert _orders(tr)[0]["sOrderPrice"] == want
    before = TB._order_day(True)
    assert before == dt.date(2027, 3, 1)


def test_order_day_moves_to_the_next_session_after_the_close(monkeypatch):
    monkeypatch.setattr(TB, "_now_dt", lambda: dt.datetime(2027, 2, 26, 17, 0, tzinfo=JST))   # 金曜 17:00 の寄付注文 → 3/1（月）
    assert TB._order_day(True) == dt.date(2027, 3, 1) and TB._order_day(False) == dt.date(2027, 2, 26)


def test_engine_core_limit_passes_the_lot_to_the_tick_table(monkeypatch):
    """引擎的核心 ETF 寄付指値（收盘 ×1.02）：一手 1 口的 ETF 在 2027-03 起按 O 表取整（以前不传一手 → C 表的 0.5 円）。"""
    from qbreak.config import StrategyParams
    from qbreak.fees import etf_cost
    from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs

    class _D(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2027, 3, 2)
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=7.0)
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                        stock_markets=("JP",), core={"1482.T": 1.0}, core_index={"1482.T": "US"})
    core = _frame([350.7] * 30)
    core["entry"] = False
    eng = UnifiedEngine({"A.T": _frame([1000.0] * 30), "1482.T": core}, cfg, {"JP": P, "US": P},
                        exec_configs(("JP",), {"broker": "tachibana"}), {"1482.T": etf_cost("tachibana", "1482.T", "JP")},
                        bear={"US": pd.Series(False, index=core.index)})
    assert int(eng.lots[eng.col["1482.T"]]) == 1
    eng.prime(10)
    eng.st.core_plan["1482.T"] = ("BUY", 10)
    monkeypatch.setattr("qbreak.tick.dt", types.SimpleNamespace(date=_D))
    lim = [x for x in eng.todo(9)["JP"] if x["ticker"] == "1482.T"][0]["limit"]
    assert lim == 357.0                                                             # 350.7 × 1.02 = 357.714 → O 表 1 円


class _BlankQuote(SimExchange):
    """立花的取价这一刻是空的（适配器自己的那次取价）；blank = False 之后恢复。"""
    blank = True

    def _price(self, p):
        r = super()._price(p)
        if self.blank:
            for row in r[self.spec.r_price_list]:
                row[self.spec.r_price] = ""
        return r


def test_now_sell_blocked_for_no_quote_is_retried_in_a_few_minutes_not_tomorrow():
    """TA-12：执行器取到了现价、适配器那一刻取不到 → 不发成行（BLOCKED）；手动指令一会儿再试（不是推到明天开盘）。"""
    r = _Run([1000.0] * 40, exchange_cls=_BlankQuote, entry=(10,), bear_all=True)
    r.until(14)
    rec = _sell_req(r)
    r.session(10, 0, quote=lambda ts: {t: 1000.0 for t in ts})
    it = r.item(rec["id"])
    o = [x for x in r.ux.orders if x.ticker == "A.T" and x.phase == "now"][0]
    assert o.status == "SKIPPED" and o.note.startswith("取不到现价") and "成行" in o.note and "分钟后再试" in o.note
    assert it["status"] == "pending" and "hold" not in it and "分钟后再试" in it["msg"]
    assert not [x for x in r.exch.orders.values() if x["ticker"] == "A.T" and x["cond"] == SPEC.cond_normal]
    r.exch.blank = False
    r.now["t"] = r.now["t"] + dt.timedelta(minutes=10)
    from qbreak.brokers import tachibana as tb
    old = tb._sleep, r.b.confirm_timeout_s
    tb._sleep, r.b.confirm_timeout_s = (lambda s: None), 5.0
    try:
        res = r.ux.now_phase(r.quote)
    finally:
        tb._sleep, r.b.confirm_timeout_s = old
    assert res["placed"] == 1 and r.item(rec["id"])["status"] == "placed"
    assert [x.status for x in r.ux.orders if x.ticker == "A.T" and x.phase == "now"] == ["SKIPPED", "FILLED"]
    r.day()                                                                         # 第二天早上：卖出记进账本，与券商一致
    assert not r.ux.blocked and "A.T" not in r.eng.st.pos
