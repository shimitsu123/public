"""立花証券 e支店 API 适配器测试。

注意：这里验证的是**我们这一侧的逻辑**（安全闸、呼値、幂等、約定核对、逆指値），
不是立花 API 的真实契约 —— 后者必须用 `run.py tachibana-probe --demo` 对着官方仕様書验证。
"""
import pytest

from qbreak import paths
from qbreak.brokers.base import BrokerError
from qbreak.brokers.tachibana import (Credentials, FakeTransport, TachibanaBroker,
                                      TachibanaSpec)

SPEC = TachibanaSpec()
LOGIN_OK = {"sResultCode": "0", "sUrlRequest": "https://x/req", "sUrlPrice": "https://x/price",
            "sUrlMaster": "https://x/master", "sUrlEvent": "https://x/event"}


def _broker(**kw):
    resp = {
        SPEC.clm_login: LOGIN_OK,
        SPEC.clm_price: {"sResultCode": "0", "pDPP": "2987"},
        SPEC.clm_new_order: {"sResultCode": "0", "sOrderNumber": "A0001"},
        SPEC.clm_order_detail: {"sResultCode": "0", "sOrderYakuzyouSuryou": "100",
                                "sOrderYakuzyouPrice": "3000", "sOrderStatus": "3"},
        SPEC.clm_positions: {"sResultCode": "0", "aGenbutuKabuList": [
            {"sIssueCode": "7203", "sZanKabuSuryou": "300", "sHyoukaTanka": "2400"}]},
        SPEC.clm_buying_power: {"sResultCode": "0", "sSuiziKaiTukeKanouGaku": "500000"},
    }
    resp.update(kw.pop("responses", {}))
    tr = FakeTransport(resp)
    kw.setdefault("creds", Credentials("u", "p"))
    kw.setdefault("confirm_timeout_s", 2.0)
    return TachibanaBroker(transport=tr, spec=SPEC, **kw), tr


def _arm():
    (paths.home() / "ARM").write_text("ARMED", encoding="utf-8")


# ────────── 会话 ──────────
def test_login_failure_gives_actionable_message():
    b, _ = _broker(responses={SPEC.clm_login: {"sResultCode": "9"}})
    with pytest.raises(BrokerError, match="登录失败"):
        b.login()


def test_login_without_request_url_is_rejected():
    b, _ = _broker(responses={SPEC.clm_login: {"sResultCode": "0"}})
    with pytest.raises(BrokerError, match="tachibana-probe"):
        b.login()


def test_sequence_number_increments_per_request():
    b, tr = _broker()
    b.get_price("7203.T")
    b.get_price("7203.T")
    seqs = [int(p["p_no"]) for _, p in tr.sent]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_credentials_never_appear_outside_login():
    b, tr = _broker()
    _arm()
    b.buy("7203.T", 100, client_id="c1")
    for url, p in tr.sent:
        if p.get("sCLMID") != SPEC.clm_login:
            assert "sPassword" not in p and "sUserId" not in p


# ────────── 安全闸 ──────────
def test_arm_gate_blocks_orders():
    b, tr = _broker()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "BLOCKED" and "ARM" in o.note
    assert not any(p.get("sCLMID") == SPEC.clm_new_order for _, p in tr.sent)


def test_halt_file_blocks_orders():
    b, tr = _broker()
    _arm()
    paths.halt_file().write_text("stop", encoding="utf-8")
    assert b.buy("7203.T", 100, client_id="c1").status == "BLOCKED"
    assert not any(p.get("sCLMID") == SPEC.clm_new_order for _, p in tr.sent)


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
    assert not any(p.get("sCLMID") == SPEC.clm_new_order for _, p in tr.sent)


def test_idempotent_client_id():
    b, tr = _broker()
    _arm()
    assert b.buy("7203.T", 100, client_id="c1").status == "FILLED"
    assert b.buy("7203.T", 100, client_id="c1").status == "REJECTED"
    n = sum(1 for _, p in tr.sent if p.get("sCLMID") == SPEC.clm_new_order)
    assert n == 1


# ────────── 发单内容 ──────────
def test_limit_price_snaps_to_legal_tick():
    b, tr = _broker(limit_buffer_pct=0.5)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    # 2987×1.005 = 3001.9 → 3000 円超の価格帯（呼値 5 円）に丸める
    assert o.price == 3000.0
    sent = [p for _, p in tr.sent if p.get("sCLMID") == SPEC.clm_new_order][0]
    assert sent[SPEC.f_price] == "3000.0"


def test_buy_sell_side_codes_and_account_type():
    b, tr = _broker()
    _arm()
    b.buy("7203.T", 100, client_id="c1")
    b.sell("7203.T", 100, client_id="c2")
    orders = [p for _, p in tr.sent if p.get("sCLMID") == SPEC.clm_new_order]
    assert orders[0][SPEC.f_side] == SPEC.side_buy
    assert orders[1][SPEC.f_side] == SPEC.side_sell
    assert all(o[SPEC.f_tax] == SPEC.tax_specific for o in orders)   # 特定口座


def test_after_close_order_uses_opening_condition():
    b, tr = _broker()
    _arm()
    b.buy("7203.T", 100, client_id="c1", bar="2026-09-23")
    sent = [p for _, p in tr.sent if p.get("sCLMID") == SPEC.clm_new_order][0]
    assert sent[SPEC.f_condition] == SPEC.cond_opening       # 寄付


def test_protective_stop_sets_gyakusashi_fields():
    b, tr = _broker()
    _arm()
    o = b.place_protective_stop("7203.T", 100, 2777.7, client_id="s1")
    sent = [p for _, p in tr.sent if p.get("sCLMID") == SPEC.clm_new_order][0]
    assert sent[SPEC.f_stop_type] == SPEC.stop_only
    assert sent[SPEC.f_stop_trigger] == "2778.0"             # 呼値 1 円・売りは切上げ
    assert sent[SPEC.f_stop_price] == SPEC.price_market      # 触发后成行，确保成交
    assert o.side == "SELL"


# ────────── 約定確認 ──────────
def test_partial_fill_reported():
    b, _ = _broker(responses={SPEC.clm_order_detail: {
        "sResultCode": "0", "sOrderYakuzyouSuryou": "50", "sOrderYakuzyouPrice": "3000"}},
        confirm_timeout_s=1.0)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "PARTIAL" and o.filled_qty == 50


def test_unfilled_order_is_flagged_not_silently_ok():
    b, _ = _broker(responses={SPEC.clm_order_detail: {
        "sResultCode": "0", "sOrderYakuzyouSuryou": "0"}}, confirm_timeout_s=1.0)
    _arm()
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "SENT" and "未约定" in o.note


def test_order_error_does_not_raise():
    b, tr = _broker()
    _arm()
    tr.fail_next = SPEC.clm_new_order
    o = b.buy("7203.T", 100, client_id="c1")
    assert o.status == "ERROR"                       # 交易主流程不应因为一次发单失败而崩


# ────────── 读取 ──────────
def test_positions_and_cash():
    b, _ = _broker()
    assert b.positions()["7203.T"].qty == 300
    assert b.cash() == 500_000


def test_empty_price_is_an_error_not_zero():
    b, _ = _broker(responses={SPEC.clm_price: {"sResultCode": "0", "pDPP": ""}})
    with pytest.raises(BrokerError, match="现在值为空"):
        b.get_price("7203.T")


def test_quotes_skips_failing_tickers():
    def price(p):
        return ({"sResultCode": "0", "pDPP": "100"} if p["sIssueCode"] == "7203"
                else {"sResultCode": "0", "pDPP": ""})
    b, _ = _broker(responses={SPEC.clm_price: price})
    assert b.quotes(["7203.T", "6758.T"]) == {"7203.T": 100.0}


# ────────── 仕様の差し替え ──────────
def test_spec_can_be_overridden_by_json_file():
    fp = paths.home() / "tachibana_spec.json"
    fp.write_text('{"clm_new_order": "CLMSomethingElse", "side_buy": "9"}', encoding="utf-8")
    s = TachibanaSpec.load()
    assert s.clm_new_order == "CLMSomethingElse" and s.side_buy == "9"
    assert s.clm_price == TachibanaSpec().clm_price      # 未指定项保持默认


def test_credentials_require_env():
    import os
    os.environ.pop("TACHIBANA_USER_ID", None)
    with pytest.raises(BrokerError, match="TACHIBANA_USER_ID"):
        Credentials.from_env()
