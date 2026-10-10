"""tachibana-probe / 上线门槛不再误判通过（2026-10-09，A5）：
取价 / 注文一覧调用失败 = NG（strict）；交易时间里没有现价 = NG、盘外至少要有前日終値；发单检查加「寄付指値买 → 撤单」；
结果文件记 API 版本段，上线门槛在版本变了 / 旧格式时要求重新做。只用假 broker / FakeTransport / 模拟交易所，不联网。"""
import datetime as dt
import json

import pytest

from qbreak import paths
from qbreak.brokers.base import BrokerError, Order
from qbreak.brokers.tachibana import TachibanaSpec, api_version
from qbreak.calendar_jp import JST
from test_tachibana import SPEC, _broker

SESSION = dt.datetime(2026, 10, 9, 10, 0, tzinfo=JST)        # 金曜・交易日的盘中
EVENING = dt.datetime(2026, 10, 9, 20, 0, tzinfo=JST)        # 交易日的盘后
HOLIDAY = dt.datetime(2026, 10, 12, 10, 0, tzinfo=JST)       # スポーツの日（休市）的白天
V_DEMO, V_LIVE = api_version(TachibanaSpec().base_demo), api_version(TachibanaSpec().base_live)


# ────────── 适配器：strict ──────────
def test_api_version_is_the_path_segment_of_the_base_url():
    assert api_version("https://kabuka.e-shiten.jp/e_api_v4r10/") == "e_api_v4r10"
    assert api_version("https://demo-kabuka.e-shiten.jp/e_api_v4r11") == "e_api_v4r11"
    assert api_version("") == "" and V_DEMO == V_LIVE == "e_api_v4r10"


def test_quote_detail_and_open_orders_raise_only_when_strict_and_never_show_the_url(monkeypatch):
    monkeypatch.setattr("qbreak.utils.time.sleep", lambda s: None)            # 只读请求的网络错误会退避重试：测试里不等

    def boom(p):
        raise ConnectionError("connect failed https://x/price/BBB/ (session)")
    bad = {"p_errno": "0", "sResultCode": "991", "sResultText": "サービス時間外"}
    b, _ = _broker(responses={SPEC.clm_price: boom, SPEC.clm_order_list: bad})
    assert b.quote_detail(["7203.T"]) == {} and b.quotes(["7203.T"]) == {}    # 默认：照旧当成「没有行情」
    assert b.open_orders() == []
    with pytest.raises(BrokerError) as e:
        b.quote_detail(["7203.T"], strict=True)
    assert "取价失败（ConnectionError）" in str(e.value) and "://" not in str(e.value) and "BBB" not in str(e.value)
    with pytest.raises(BrokerError, match="注文一覧.*サービス時間外"):
        b.open_orders(strict=True)
    ok, _ = _broker()                                                         # 成功时 strict 与默认结果相同
    assert ok.quote_detail(["7203.T"], strict=True) == ok.quote_detail(["7203.T"]) == {"7203.T": {"price": 2987.0}}


# ────────── probe 的取价步骤（注入时刻）──────────
class _Q:
    def __init__(self, rows=None, exc=None):
        self.rows, self.exc = rows or {}, exc

    def quote_detail(self, tickers, strict=False):
        assert strict is True                                                 # probe 一定用 strict（失败 = NG）
        if self.exc:
            raise self.exc
        return {t: d for t, d in self.rows.items() if t in tickers}


@pytest.mark.parametrize("now,rows,good,word", [
    (SESSION, {}, False, "★ 交易时间里取不到现价（字段名不对？）"),
    (SESSION, {"7203.T": {"prev_close": 2980.0}}, False, "★ 交易时间里取不到现价"),
    (SESSION, {"7203.T": {"price": 3010.0, "prev_close": 2980.0}}, True, "现价 7203 3,010 円（1329、1655 没有现价"),
    (EVENING, {"7203.T": {"prev_close": 2980.0}}, True, "盘外：现价为空是正常的（前日終値 7203 2,980 円）"),
    (EVENING, {"7203.T": {"price": 3010.0, "prev_close": 2980.0}}, True, "盘外：现价 7203 3,010 円（前日終値"),
    (EVENING, {}, False, "★ 连前日終値都没有：字段名可能不对"),
    (EVENING, {"7203.T": {"price": 3010.0}}, False, "★ 连前日終値都没有"),
    (HOLIDAY, {}, False, "★ 连前日終値都没有"),
    (HOLIDAY, {"1655.T": {"prev_close": 700.0}}, True, "盘外：现价为空是正常的（前日終値 1655 700 円）"),
])
def test_probe_quote_step_judges_by_session(now, rows, good, word):
    import run
    r = run._probe_quote_text(_Q(rows), now=now)
    assert ("★" not in r) is good and word in r


@pytest.mark.parametrize("now,rows,checked", [
    (SESSION, {"7203.T": {"price": 3010.0, "prev_close": 2980.0}}, True),      # 交易时间里取到了现价 = 字段名确认过
    (SESSION, {"7203.T": {"prev_close": 2980.0}}, False),
    (EVENING, {"7203.T": {"price": 3010.0, "prev_close": 2980.0}}, None),       # 盘外：确认不了（不记）
    (HOLIDAY, {"1655.T": {"prev_close": 700.0}}, None),
])
def test_probe_quote_step_records_whether_the_price_field_was_seen_in_session(now, rows, checked):
    import run
    info = {}
    run._probe_quote_text(_Q(rows), now=now, info=info)
    assert info.get("price_checked") is checked


def test_probe_records_price_checked_in_session(monkeypatch):
    import run
    b, _ = _broker(responses={SPEC.clm_price: _price_rows("3010", "2980")})
    monkeypatch.setattr("qbreak.brokers.tachibana.TachibanaBroker", lambda **kw: b)
    monkeypatch.setattr("qbreak.calendar_jp.now_jst", lambda: SESSION)
    monkeypatch.setattr(run, "_tachibana_tradable_check", lambda b_: "都能买、一手一致")
    assert run.main(["tachibana-probe"]) == 0
    rec = json.loads((paths.out_dir() / "tachibana_probe_live.json").read_text(encoding="utf-8"))
    assert rec["ok"] is True and rec["price_checked"] is True
    it = _gate(paths.home())[G5]
    assert it["ok"] is True and "现价字段还没" not in it["text"]


def test_probe_quote_step_call_failure_propagates():
    import run
    with pytest.raises(BrokerError):
        run._probe_quote_text(_Q(exc=BrokerError("取价失败（ConnectionError）")), now=EVENING)


# ────────── probe 全流程（FakeTransport + 注入时钟）──────────
def _price_rows(price: str, prev: str):
    def f(p):
        return {"p_errno": "0", SPEC.r_price_list: [{"sIssueCode": c, "pDPP": price, "pPRP": prev}
                                                    for c in p[SPEC.f_target_codes].split(",")]}
    return f


@pytest.mark.parametrize("now,price,prev,orders_ok,rc,bad_steps", [
    (SESSION, "", "2980", True, 1, ["取价 7203 / 1329 / 1655"]),                # 盘中全空 → NG（以前会算通过）
    (EVENING, "", "2980", True, 0, []),                                       # 盘外有前日終値 → OK
    (EVENING, "", "", True, 1, ["取价 7203 / 1329 / 1655"]),                    # 盘外全空 → NG（字段名可能不对）
    (EVENING, "", "2980", False, 1, ["注文一覧"]),                              # 注文一覧调用失败 → NG（以前当成 0 件）
])
def test_probe_records_api_version_and_judges_quote_and_order_list(monkeypatch, capsys, now, price, prev, orders_ok, rc,
                                                                   bad_steps):
    import run
    bad = {"p_errno": "0", "sResultCode": "991", "sResultText": "サービス時間外"}
    resp = {SPEC.clm_price: _price_rows(price, prev)}
    if not orders_ok:
        resp[SPEC.clm_order_list] = bad
    b, _ = _broker(responses=resp)
    monkeypatch.setattr("qbreak.brokers.tachibana.TachibanaBroker", lambda **kw: b)
    monkeypatch.setattr("qbreak.calendar_jp.now_jst", lambda: now)
    monkeypatch.setattr(run, "_tachibana_tradable_check", lambda b_: "都能买、一手一致")
    assert run.main(["tachibana-probe", "--demo"]) == rc
    rec = json.loads((paths.out_dir() / "tachibana_probe_demo.json").read_text(encoding="utf-8"))
    assert rec["api"] == V_DEMO and rec["ok"] is (rc == 0) and rec["env"] == "demo"
    assert rec["price_checked"] is False                                       # 盘外 / 盘中全空：现价的字段名没确认
    assert [k for k, v in rec["steps"].items() if not v] == bad_steps
    out = capsys.readouterr().out
    assert "https://x/" not in out and "AUTH-XYZ" not in out and "2nd-pw" not in out    # 虚拟 URL / 认证信息绝不打印


# ────────── 发单检查：寄付指値买 → 撤单 ──────────
class _OB:
    """只测寄付指値买那一步的假 broker：受理状态 / 撤单结果 / 是否已成交可调。"""

    def __init__(self, status="SENT", cancel=True, filled=0):
        self.status, self.cancel, self.filled, self.calls = status, cancel, filled, []

    def buy(self, t, qty, limit=None, client_id="", bar=""):
        self.calls.append(("buy", t, qty, limit, bar))
        no = "" if self.status in ("REJECTED", "BLOCKED") else "B0001"
        return Order(t, "BUY", qty, limit, "now", self.status, client_id=client_id, broker_id=no,
                     extra={"order_date": "20261009"})

    def cancel_order(self, no, day):
        self.calls.append(("cancel", no, day))
        return self.cancel

    def order_status(self, no, day):
        return {"filled_qty": self.filled, "avg_px": 0.0, "status_code": "", "status": ""}


@pytest.mark.parametrize("b_,accepted,cancel,line", [
    (_OB(), True, True, "[OK] 寄付指値撤单 : 已撤"),
    (_OB(cancel=False, filled=10), True, None, "已经成交"),                     # 撤不掉是因为已经成交 → None（也算通过）
    (_OB(cancel=False), True, False, "[NG] 寄付指値撤单"),                      # 没成交又撤不掉 → NG
    (_OB(status="REJECTED"), False, False, "[NG] 寄付指値买"),
])
def test_opening_limit_buy_step(capsys, b_, accepted, cancel, line):
    import run
    ot = {}
    assert run._order_test_opening_limit_buy(b_, "1655.T", 10, 700.0, ot) is accepted
    assert ot["opening_limit_buy"] == b_.status and ot["opening_cancel"] is cancel
    assert b_.calls[0] == ("buy", "1655.T", 10, 630.0, "next")               # 寄付（bar 非空）+ 价格 = 现价 × 0.9
    assert line in capsys.readouterr().out


def test_order_test_fails_when_the_opening_limit_buy_is_rejected():
    """模拟交易所上余力只够第一笔：寄付指値买被拒 → order_test 的 ok 是 False（门槛 ④ 不会过）。"""
    import run
    from qbreak.brokers.tachibana import TachibanaBroker
    from qbreak.brokers.tachibana_sim import SimExchange
    from test_live_unified import _scenario
    make, _ = _scenario([1000.0] * 30)
    exch = SimExchange(make(), cash=7_500)
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), dry_run=True, require_arm=True,
                        confirm_timeout_s=0.0)
    exch.set_day(10)
    exch.open(10)
    rec = {}
    assert run._tachibana_order_test(b, exch.spec, rec) is True                # 第一笔照样受理
    ot = rec["order_test"]
    assert ot["opening_limit_buy"] == "REJECTED" and ot["opening_cancel"] is False and ot["ok"] is False


# ────────── 上线门槛 ④ / ⑤：版本、旧格式、几天前 ──────────
def _no_cmd(args, **kw):
    raise FileNotFoundError(args[0])                                          # 不是 macOS：security / launchctl / pmset 都没有


def _gate(tmp_path, today=dt.date(2026, 10, 9)):
    from qbreak import live_gate as G
    return {it["name"]: it for it in G.check(agents=tmp_path / "agents", run=_no_cmd, today=today)}


G4 = "④ デモ发单检查（约定字段、余力变化、按注文番号撤单）"
G5 = "⑤ 本番只读检查（登录 / 取价 / 持仓 / 余力 / 立花能不能买）"
OT_OLD = {"ok": True, "fields_missing": [], "cash_or_pos_changed": True, "cancel": True}
OT_NEW = {**OT_OLD, "opening_limit_buy": "SENT", "opening_cancel": True}


def _write(env, rec):
    (paths.out_dir() / f"tachibana_probe_{env}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("rec,ok,words", [
    ({"at": "2026-10-07 10:00 JST", "ok": True, "order_test": OT_OLD}, False,
     ["★ 检查结果是旧格式：重新做 bash scripts/liveu.sh probe --demo --order-test", "寄付指値买 ★ 没测"]),
    ({"at": "2026-10-07 10:00 JST", "ok": True, "api": V_DEMO, "order_test": OT_OLD}, False, ["寄付指値买 ★ 没测"]),
    ({"at": "2026-10-07 10:00 JST", "ok": True, "api": "e_api_v4r9", "order_test": OT_NEW}, False,
     [f"★ API 版本变了（e_api_v4r9 → {V_DEMO}）：重新做 bash scripts/liveu.sh probe --demo --order-test"]),
    ({"at": "2026-10-07 10:00 JST", "ok": True, "api": V_DEMO, "order_test": {**OT_NEW, "opening_limit_buy": "REJECTED"}},
     False, ["寄付指値买 ★ 没受理（REJECTED）"]),
    ({"at": "2026-10-07 10:00 JST", "ok": True, "api": V_DEMO, "order_test": OT_NEW}, True,
     ["2026-10-07 10:00 JST（2 天前做的）", "寄付指値买 受理、撤单成功"]),
    ({"at": "2026-10-09 10:00 JST", "ok": True, "api": V_DEMO, "order_test": {**OT_NEW, "opening_cancel": None}}, True,
     ["（今天做的）", "寄付指値买 受理、已成交（不用撤）"]),
])
def test_gate_demo_order_test_needs_current_api_and_the_opening_limit_buy(tmp_path, rec, ok, words):
    _write("demo", rec)
    it = _gate(tmp_path)[G4]
    assert it["ok"] is ok and all(w in it["text"] for w in words), it["text"]


@pytest.mark.parametrize("rec,ok,word", [
    ({"at": "2026-10-08 08:00 JST", "ok": True, "steps": {"登录": True}}, False, "★ 检查结果是旧格式：重新做 bash scripts/liveu.sh probe"),
    ({"at": "2026-10-08 08:00 JST", "ok": True, "api": "e_api_v4r9", "steps": {}}, False, f"★ API 版本变了（e_api_v4r9 → {V_LIVE}）"),
    ({"at": "2026-10-08 08:00 JST", "ok": False, "api": V_LIVE, "steps": {"注文一覧": False}}, False, "★ 没通过：注文一覧"),
    ({"at": "2026-10-08 08:00 JST", "ok": True, "api": V_LIVE, "steps": {}}, True, "2026-10-08 08:00 JST（1 天前做的）：全部通过"),
])
def test_gate_live_probe_needs_current_api(tmp_path, rec, ok, word):
    _write("live", rec)
    it = _gate(tmp_path)[G5]
    assert it["ok"] is ok and word in it["text"], it["text"]


@pytest.mark.parametrize("checked,star", [(False, True), (None, True), (True, False)])
def test_gate_live_probe_reminds_until_the_price_field_is_checked_in_session(tmp_path, checked, star):
    """盘外做的检查只看到前日終値（现价的字段名没确认）→ ⑤ 照样通过，但提醒交易时间里再做一次（只提醒，不算没通过）。"""
    rec = {"at": "2026-10-08 20:00 JST", "ok": True, "api": V_LIVE, "steps": {}}
    if checked is not None:
        rec["price_checked"] = checked
    _write("live", rec)
    it = _gate(tmp_path)[G5]
    assert it["ok"] is True and "全部通过" in it["text"]
    assert ("★ 现价字段还没在交易时间里确认过：交易日 09:00〜15:30 再做一次 bash scripts/liveu.sh probe" in it["text"]) is star


def test_gate_follows_the_spec_override_in_the_data_dir(tmp_path):
    """仕様改版时只改数据目录的 tachibana_spec.json：base 换成新版本 → 旧版本做的检查要重新做。"""
    _write("demo", {"at": "2026-10-07 10:00 JST", "ok": True, "api": V_DEMO, "order_test": OT_NEW})
    _write("live", {"at": "2026-10-08 08:00 JST", "ok": True, "api": V_LIVE, "steps": {}})
    (paths.home() / "tachibana_spec.json").write_text(json.dumps({"base_demo": "https://demo-kabuka.e-shiten.jp/e_api_v4r11/"}),
                                                     encoding="utf-8")
    items = _gate(tmp_path)
    assert items[G4]["ok"] is False and f"API 版本变了（{V_DEMO} → e_api_v4r11）" in items[G4]["text"]
    assert items[G5]["ok"] is True                                            # 本番的 base 没变
    (paths.home() / "tachibana_spec.json").write_text("{broken", encoding="utf-8")
    items = _gate(tmp_path)
    assert items[G4]["ok"] is False and "tachibana_spec.json 读不了" in items[G4]["text"]
