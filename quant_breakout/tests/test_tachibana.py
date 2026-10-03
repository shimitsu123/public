"""立花証券 e支店 API 适配器测试（v4r10 契约：认证 ID + RSA-OAEP 解密虚拟 URL、官方字段名）。

注意：这里验证的是**我们这一侧的逻辑**（登录解密、会话切断重登、安全闸、呼値、幂等、約定核对、逆指値），
字段名按 2026-09-25 的公开仕様書；真实服务器的行为仍须 `run.py tachibana-probe --demo` 验证。
"""
import base64
import os

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from qbreak import paths
from qbreak.brokers.base import BrokerError
from qbreak.brokers.tachibana import (Credentials, FakeTransport, TachibanaBroker,
                                      TachibanaSpec, decrypt_url)

SPEC = TachibanaSpec()
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = _KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                         serialization.NoEncryption())


def _enc(url: str) -> str:
    """服务器一侧：用登记的公钥加密虚拟 URL（RSA-OAEP / SHA-256，Base64）。"""
    ct = _KEY.public_key().encrypt(url.encode("ascii"), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return base64.b64encode(ct).decode("ascii")


LOGIN_OK = {"p_errno": "0", "sResultCode": "0", "sZyoutoekiKazeiC": "1", "sKinsyouhouMidokuFlg": "0",
            "sUrlRequest": _enc("https://x/request/AAA/"), "sUrlPrice": _enc("https://x/price/BBB/"),
            "sUrlMaster": _enc("https://x/master/CCC/"), "sUrlEvent": _enc("https://x/event/DDD/"),
            "sUrlEventWebSocket": _enc("wss://x/ws/EEE/")}


def _price(p):
    codes = p[SPEC.f_target_codes].split(",")
    return {"p_errno": "0", SPEC.r_price_list: [{"sIssueCode": c, "pDPP": "2987"} for c in codes]}


def _broker(**kw):
    resp = {
        SPEC.clm_login: LOGIN_OK,
        SPEC.clm_price: _price,
        SPEC.clm_new_order: {"p_errno": "0", "sResultCode": "0", "sOrderNumber": "A0001", "sEigyouDay": "20260928"},
        SPEC.clm_order_detail: {"p_errno": "0", "sResultCode": "0", "sYakuzyouSuryou": "100",
                                "sYakuzyouPrice": "3000", "sOrderStatusCode": "10"},
        SPEC.clm_positions: {"p_errno": "0", "sResultCode": "0", "aGenbutuKabuList": [
            {"sUriOrderIssueCode": "7203", "sUriOrderZanKabuSuryou": "200", "sUriOrderGaisanBokaTanka": "2400"},
            {"sUriOrderIssueCode": "7203", "sUriOrderZanKabuSuryou": "100", "sUriOrderGaisanBokaTanka": "2700"}]},
        SPEC.clm_buying_power: {"p_errno": "0", "sResultCode": "0", "sSummaryGenkabuKaituke": "500000"},
    }
    resp.update(kw.pop("responses", {}))
    tr = FakeTransport(resp)
    kw.setdefault("creds", Credentials("AUTH-XYZ", PEM, "2nd-pw"))
    kw.setdefault("confirm_timeout_s", 2.0)
    b = TachibanaBroker(transport=tr, spec=SPEC, **kw)
    b.spec.min_interval_s = 0.0
    return b, tr


def _arm():
    (paths.home() / "ARM").write_text("ARMED", encoding="utf-8")


def _orders(tr):
    return [p for _, p in tr.sent if p.get("sCLMID") == SPEC.clm_new_order]


# ────────── 会话（v4r10：认证 ID + 私钥解密）──────────
def test_login_sends_only_auth_id_and_decrypts_virtual_urls():
    b, tr = _broker()
    b.login()
    url, p = tr.sent[0]
    assert url == SPEC.base_live + "auth/" and p["sCLMID"] == SPEC.clm_login
    assert p["sAuthId"] == "AUTH-XYZ" and "sPassword" not in p and "sUserId" not in p
    assert b._urls[SPEC.key_url_request] == "https://x/request/AAA/"
    assert b._urls[SPEC.key_url_price] == "https://x/price/BBB/"
    assert decrypt_url(PEM, LOGIN_OK["sUrlMaster"]) == "https://x/master/CCC/"


def test_requests_go_to_decrypted_urls():
    b, tr = _broker()
    b.get_price("7203.T")
    b.cash()
    assert tr.sent[1][0] == "https://x/price/BBB/"           # 时价 → 仮想URL（PRICE）
    assert tr.sent[2][0] == "https://x/request/AAA/"         # 余力 → 仮想URL（REQUEST）


def test_login_failure_gives_actionable_message():
    b, _ = _broker(responses={SPEC.clm_login: {"p_errno": "-50", "p_err": "ログインエラー。"}})
    with pytest.raises(BrokerError, match="利用設定"):
        b.login()


def test_unread_documents_block_login_with_instruction():
    b, _ = _broker(responses={SPEC.clm_login: {**LOGIN_OK, "sKinsyouhouMidokuFlg": "1", "sUrlRequest": ""}})
    with pytest.raises(BrokerError, match="交付書面未読"):
        b.login()


def test_wrong_private_key_is_reported():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    b, _ = _broker(creds=Credentials("AUTH-XYZ", other, "2nd-pw"))
    with pytest.raises(BrokerError, match="不配对"):
        b.login()


def test_login_without_request_url_is_rejected():
    b, _ = _broker(responses={SPEC.clm_login: {"p_errno": "0", "sResultCode": "0"}})
    with pytest.raises(BrokerError, match="tachibana-probe"):
        b.login()


def test_session_cut_relogins_once_and_retries():
    state = {"n": 0}

    def cash(p):
        state["n"] += 1
        if state["n"] == 1:
            return {"p_errno": "2", "p_err": "セッションが切断しました。"}
        return {"p_errno": "0", "sResultCode": "0", "sSummaryGenkabuKaituke": "123"}
    b, tr = _broker(responses={SPEC.clm_buying_power: cash})
    assert b.cash() == 123
    logins = [p for _, p in tr.sent if p["sCLMID"] == SPEC.clm_login]
    assert len(logins) == 2                                   # 03:30 闭局后第二天自动重新登录


def test_sequence_number_strictly_increases_across_relogin():
    b, tr = _broker()
    b.get_price("7203.T")
    b._logged_in = False
    b.get_price("7203.T")
    seqs = [int(p["p_no"]) for _, p in tr.sent]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert all(len(p["p_sd_date"]) == 23 for _, p in tr.sent)   # YYYY.MM.DD-HH:MM:SS.TTT


def test_secrets_never_leave_their_request():
    b, tr = _broker()
    _arm()
    b.buy("7203.T", 100, client_id="c1")
    for _, p in tr.sent:
        if p["sCLMID"] != SPEC.clm_login:
            assert "sAuthId" not in p
        if p["sCLMID"] not in (SPEC.clm_new_order, SPEC.clm_cancel_order):
            assert "sSecondPassword" not in p
    assert "AUTH" not in repr(b.creds) and "2nd" not in repr(b.creds)


# ────────── 安全闸 ──────────
def test_arm_gate_blocks_orders():
    b, tr = _broker()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "BLOCKED" and "ARM" in o.note
    assert not _orders(tr)


def test_halt_file_blocks_orders():
    b, tr = _broker()
    _arm()
    paths.halt_file().write_text("stop", encoding="utf-8")
    assert b.buy("7203.T", 100, client_id="c1").status == "BLOCKED"
    assert not _orders(tr)


def test_missing_second_password_blocks_orders():
    b, tr = _broker(creds=Credentials("AUTH-XYZ", PEM, ""))
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "BLOCKED" and "第二暗証" in o.note and not _orders(tr)


def test_max_order_value_blocks():
    b, _ = _broker(max_order_value=10_000)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")           # 3000×100 = 30 万
    assert o.status == "BLOCKED" and "上限" in o.note


def test_dry_run_never_sends_order():
    b, tr = _broker(dry_run=True)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "BLOCKED" and "dry-run" in o.note
    assert not _orders(tr)


def test_idempotent_client_id():
    b, tr = _broker()
    _arm()
    assert b.buy("7203.T", 100, client_id="c1").status == "FILLED"
    assert b.buy("7203.T", 100, client_id="c1").status == "REJECTED"
    assert len(_orders(tr)) == 1


def test_order_is_never_resent_after_network_error():
    b, tr = _broker()
    _arm()
    b.login()
    tr.fail_next = SPEC.clm_new_order
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "ERROR" and len(_orders(tr)) == 1      # 发单类不自动重发（可能已被受理）


# ────────── 发单内容（v4r10 字段）──────────
def test_new_order_carries_all_required_fields():
    b, tr = _broker(limit_buffer_pct=0.5)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    # 2987×1.005 = 3001.9 → 3000 円超の価格帯（呼値 5 円）に丸める
    assert o.price == 3000.0
    p = _orders(tr)[0]
    assert (p["sOrderPrice"], p["sOrderSuryou"], p["sIssueCode"], p["sSizyouC"]) == ("3000", "100", "7203", "00")
    assert (p["sBaibaiKubun"], p["sGenkinShinyouKubun"], p["sZyoutoekiKazeiC"]) == ("3", "0", "1")
    assert (p["sGyakusasiOrderType"], p["sGyakusasiZyouken"], p["sGyakusasiPrice"]) == ("0", "0", "*")
    assert (p["sTatebiType"], p["sTategyokuZyoutoekiKazeiC"], p["sOrderExpireDay"]) == ("*", "*", "0")
    assert p["sSecondPassword"] == "2nd-pw"


def test_buy_sell_side_codes():
    b, tr = _broker()
    _arm()
    b.buy("7203.T", 100, client_id="c1")
    b.sell("7203.T", 100, client_id="c2")
    orders = _orders(tr)
    assert [o["sBaibaiKubun"] for o in orders] == ["3", "1"]


def test_after_close_order_uses_opening_condition_and_skips_fill_polling():
    b, tr = _broker()
    _arm()
    o = b.buy("7203.T", 100, limit=2990.0, client_id="c1", bar="2026-09-25")
    p = _orders(tr)[0]
    assert p["sCondition"] == SPEC.cond_opening and p["sOrderPrice"] == "2990"       # 寄付指値
    assert o.status == "SENT" and "寄付" in o.note
    assert not any(q["sCLMID"] == SPEC.clm_order_detail for _, q in tr.sent)      # 次の寄付で約定：不轮询


def test_protective_stop_is_stop_only_market_on_trigger():
    b, tr = _broker()
    _arm()
    o = b.place_protective_stop("7203.T", 100, 2777.7, client_id="s1")
    p = _orders(tr)[0]
    assert (p["sGyakusasiOrderType"], p["sGyakusasiZyouken"], p["sGyakusasiPrice"]) == ("1", "2778", "0")
    assert p["sOrderPrice"] == "*"                               # 通常部分「指定なし」
    assert o.side == "SELL" and o.status == "SENT"


def test_cancel_sends_order_number_business_day_and_second_password():
    b, tr = _broker()
    _arm()
    b.buy("7203.T", 100, limit=2990.0, client_id="c1", bar="2026-09-25")
    assert b.cancel("c1")
    p = [q for _, q in tr.sent if q["sCLMID"] == SPEC.clm_cancel_order][0]
    assert (p["sOrderNumber"], p["sEigyouDay"], p["sSecondPassword"]) == ("A0001", "20260928", "2nd-pw")


# ────────── 約定確認 ──────────
def test_detail_request_uses_order_number_and_business_day():
    b, tr = _broker()
    _arm()
    assert b.buy("7203.T", 100, client_id="c1").status == "FILLED"
    p = [q for _, q in tr.sent if q["sCLMID"] == SPEC.clm_order_detail][0]
    assert (p["sOrderNumber"], p["sEigyouDay"]) == ("A0001", "20260928")


def test_partial_fill_reported():
    b, _ = _broker(responses={SPEC.clm_order_detail: {
        "p_errno": "0", "sResultCode": "0", "sYakuzyouSuryou": "50", "sYakuzyouPrice": "3000"}},
        confirm_timeout_s=1.0)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "PARTIAL" and o.filled_qty == 50


def test_unfilled_order_is_flagged_not_silently_ok():
    b, _ = _broker(responses={SPEC.clm_order_detail: {
        "p_errno": "0", "sResultCode": "0", "sYakuzyouSuryou": "0"}}, confirm_timeout_s=1.0)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "SENT" and "未约定" in o.note


# ────────── 读取 ──────────
def test_positions_merge_tax_rows_and_cash():
    b, _ = _broker()
    pos = b.positions()["7203.T"]
    assert pos.qty == 300 and pos.avg_px == pytest.approx((200 * 2400 + 100 * 2700) / 300)
    assert b.cash() == 500_000


def test_empty_list_is_empty_string_per_spec():
    b, _ = _broker(responses={SPEC.clm_positions: {"p_errno": "0", "sResultCode": "0", "aGenbutuKabuList": ""},
                              SPEC.clm_order_list: {"p_errno": "0", "sResultCode": "0", "aOrderList": ""}})
    assert b.positions() == {} and b.open_orders() == []


def test_empty_price_is_an_error_not_zero():
    b, _ = _broker(responses={SPEC.clm_price: {"p_errno": "0", SPEC.r_price_list: [{"sIssueCode": "7203", "pDPP": ""}]}})
    with pytest.raises(BrokerError, match="现在值为空"):
        b.get_price("7203.T")


def test_quotes_batch_up_to_120_and_skip_blank():
    def price(p):
        codes = p[SPEC.f_target_codes].split(",")
        assert len(codes) <= 120
        return {"p_errno": "0", SPEC.r_price_list: [{"sIssueCode": c, "pDPP": "" if c == "6758" else "100"}
                                                    for c in codes]}
    b, tr = _broker(responses={SPEC.clm_price: price})
    many = ["7203.T", "6758.T"] + [f"{1000 + i}.T" for i in range(150)]
    q = b.quotes(many)
    assert q["7203.T"] == 100.0 and "6758.T" not in q and len(q) == 151
    assert sum(1 for _, p in tr.sent if p["sCLMID"] == SPEC.clm_price) == 2


# ────────── 仕様の差し替え / 凭证 ──────────
def test_spec_can_be_overridden_by_json_file():
    fp = paths.home() / "tachibana_spec.json"
    fp.write_text('{"clm_new_order": "CLMSomethingElse", "side_buy": "9"}', encoding="utf-8")
    s = TachibanaSpec.load()
    assert s.clm_new_order == "CLMSomethingElse" and s.side_buy == "9"
    assert s.clm_price == TachibanaSpec().clm_price      # 未指定项保持默认
    assert s.base_live.endswith("/e_api_v4r10/")


def test_credentials_from_env_require_auth_id_and_private_key_600(tmp_path, monkeypatch):
    for k in ("TACHIBANA_AUTH_ID", "TACHIBANA_AUTH_ID_FILE", "TACHIBANA_PRIVATE_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("qbreak.brokers.tachibana._keychain", lambda s, a: None)
    with pytest.raises(BrokerError, match="认证 ID"):
        Credentials.from_env()
    (tmp_path / "e_api_authid.txt").write_text("AUTH-FROM-FILE\n", encoding="utf-8")
    monkeypatch.setenv("TACHIBANA_AUTH_ID_FILE", str(tmp_path / "e_api_authid.txt"))
    kp = tmp_path / "k.pem"
    kp.write_bytes(PEM)
    monkeypatch.setenv("TACHIBANA_PRIVATE_KEY", str(kp))
    if os.name == "posix":
        kp.chmod(0o644)
        with pytest.raises(BrokerError, match="chmod 600"):
            Credentials.from_env()
        kp.chmod(0o600)
    c = Credentials.from_env()
    assert c.auth_id == "AUTH-FROM-FILE" and c.private_key_pem == PEM


# ────────── 一个账户的执行器要用到的：寄付成行、約定照会、按注文番号撤单、始値 ──────────
def test_opening_sell_without_limit_is_market_order():
    """寄付 + 不给价格 = 成行（在开盘集合竞价按开盘价成交 = 回测的「次日开盘」），不能变成现在值 −0.5% 的指値。"""
    b, tr = _broker()
    _arm()
    o = b.sell("7203.T", 100, client_id="c1", bar="2026-09-25")
    p = _orders(tr)[0]
    assert (p["sCondition"], p["sOrderPrice"]) == (SPEC.cond_opening, SPEC.price_market) and o.status == "SENT"


def test_market_buy_without_any_price_is_blocked():
    """取不到现在值时的成行买单：单笔上限没法检查 → 拒绝（原来会以金额 0 通过闸门）。"""
    b, tr = _broker(responses={SPEC.clm_price: {"p_errno": "0", SPEC.r_price_list: [{"sIssueCode": "7203", "pDPP": ""}]}})
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "BLOCKED" and "成行买单" in o.note and not _orders(tr)


def test_server_rejection_is_rejected_not_unknown():
    """服务器应答了业务错误（例如余力不足）→ REJECTED（确定没受理，执行器可以放心）；网络错误才是 ERROR（状态不明）。"""
    b, _ = _broker(responses={SPEC.clm_new_order: {"p_errno": "0", "sResultCode": "991020", "sResultText": "買付余力不足"}})
    _arm()
    o = b.buy("7203.T", 100, limit=2990.0, client_id="c1", bar="2026-09-25")
    assert o.status == "REJECTED" and "991020" in o.note


def test_order_status_uses_execution_list_vwap():
    b, tr = _broker(responses={SPEC.clm_order_detail: {
        "p_errno": "0", "sResultCode": "0", "sOrderStatusCode": "10", "sYakuzyouSuryou": "300", "sYakuzyouPrice": "9",
        SPEC.r_exec_list: [{SPEC.r_exec_qty: "100", SPEC.r_exec_px: "3000"}, {SPEC.r_exec_qty: "200", SPEC.r_exec_px: "3003"}]}})
    r = b.order_status("A0001", "20260928")
    assert r["filled_qty"] == 300 and r["avg_px"] == pytest.approx(3002.0) and r["status_code"] == "10"
    p = [q for _, q in tr.sent if q["sCLMID"] == SPEC.clm_order_detail][0]
    assert (p["sOrderNumber"], p["sEigyouDay"]) == ("A0001", "20260928")


def test_order_status_falls_back_to_top_level_fields():
    b, _ = _broker()
    assert b.order_status("A0001", "20260928") == {"filled_qty": 100, "avg_px": 3000.0, "status_code": "10", "status": ""}


def test_cancel_by_persisted_order_number_works_after_restart():
    """执行器把注文番号 + 営業日存在账本里：进程重启（内存里的 client_id 映射没了）也能撤单。"""
    b, tr = _broker()
    assert b.cancel("unknown-cid") is False
    assert b.cancel_order("A0009", "20260928")
    p = [q for _, q in tr.sent if q["sCLMID"] == SPEC.clm_cancel_order][0]
    assert (p["sOrderNumber"], p["sEigyouDay"], p["sSecondPassword"]) == ("A0009", "20260928", "2nd-pw")


def test_quote_detail_returns_open_and_skips_blank():
    def price(p):
        return {"p_errno": "0", SPEC.r_price_list: [
            {"sIssueCode": "7203", "pDPP": "3010", "pDOP": "2995", "pDHP": "", "pDLP": "", "pPRP": "2980"},
            {"sIssueCode": "6758", "pDPP": "", "pDOP": "", "pPRP": ""}]}
    b, _ = _broker(responses={SPEC.clm_price: price})
    q = b.quote_detail(["7203.T", "6758.T"])
    assert q == {"7203.T": {"price": 3010.0, "open": 2995.0, "prev_close": 2980.0}}
    assert b.quotes(["7203.T", "6758.T"]) == {"7203.T": 3010.0}
