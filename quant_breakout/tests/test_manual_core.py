"""持有的核心 ETF 也在持仓下面「卖出全部 / 调仓…」（2026-10-07 用户：「只要是现在持仓的都要可以调整持仓 包括etf什么的
在对应持仓的股票下面显示调整持仓button等等」）。规则每天把核心 ETF 调回「规则目标额 × 闲置资金比例」，一次性的单留不住 →
ETF 的卖出 / 减仓 / 调仓换算成闲置资金比例（目标口数 ÷ 比例 100% 时的规则目标；对全部核心 ETF 一起生效）；
盘中写的马上照新比例调，开盘前写的进早上的决策（这一次不看再平衡带）。
① 引擎：比例 100% 时的目标与比例无关、core_exact 不看再平衡带；② 换算（core_rec / core_pct_for）、检查、now_due；
③ 执行器（模拟账户 + 立花适配器）：盘中卖 / 买 → 第二天对账一致、规则不再调回去；今天已有单 / 今天调过 → 下一次决策照新比例；
取不到价 / HALT → 一会儿再试；盘中没成交 → 下一次决策照比例；④ 面板：ETF 下面的按钮、提交的换算、对话框（node）；⑤ 命令行。"""
import datetime as dt
import json
import shutil
import subprocess

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST

from test_live_unified import _scenario
from test_manual_now import PX, _at, _held, _item, _morning, _paper, _quote
from test_manual_orders import TAG, _Run
from test_panel import _js_fn


def _write(tag: str, rid: str, **rec) -> dict:
    """直接写一行指令（测试里的核心 ETF 是 1655.T；页面 / 命令行的检查另外测）。"""
    rec = {"id": rid, "at": "x", "source": "test", **rec}
    with open(MO.requests_path(tag), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _conv(book: dict, **req) -> dict:
    return MO.core_rec(MO.normalize({"ticker": "1655", **req}), book)


def _core_orders(r) -> list:
    return [o for o in r.ux.orders if o.reason == "manual_core"]


# ────────── ① 引擎 ──────────
def test_engine_target_at_100pct_ignores_the_ratio_and_exact_ignores_the_band():
    make, start = _scenario([1000.0] * 30, entry=())                     # 牛市、没有个股：闲置资金都在 1655
    engs = [make() for _ in range(3)]
    lo = int(engs[0].gidx.searchsorted(start))
    for e in engs:
        e.prime(lo)
        for i in range(lo, lo + 8):
            e.step(i)
    engs[1].core_scale = engs[2].core_scale = 0.97                      # 比例 97%：差 3%，在再平衡带（10%）里
    engs[2].core_exact = True
    for e in engs:
        e.step(lo + 8)
    u = engs[0].st.core_units["1655.T"]
    t100 = engs[0].core_t100
    assert engs[1].st.core_units["1655.T"] == engs[2].st.core_units["1655.T"] == u > 0
    assert t100 == engs[1].core_t100 == engs[2].core_t100 and t100["1655.T"] >= u      # 比例 100% 时的目标与比例无关
    assert "1655.T" not in engs[0].st.core_plan and "1655.T" not in engs[1].st.core_plan   # 照规则：带里不动
    side, n = engs[2].st.core_plan["1655.T"]                              # core_exact：直接调到 目标 × 97%
    assert side == "SELL" and abs((u - n) - 0.97 * t100["1655.T"]) <= 10


# ────────── ② 换算与检查 ──────────
def _cbook(units=1130, u100=1140, pct=100.0, plan=None, px=700.0, lot=10, eq=1_000_000.0, last="2026-10-05"):
    st = {"last_date": last, "cash_jpy": 50_000.0, "history": [[last, eq, 0, 0, 150]], "pos": {}, "pending_exit": {},
          "core_units": {"1655.T": units}, "core_plan": plan or {}}
    return {"state": st, "manual": {"core_pct": pct, "items": {}, "blocks": {}, "trims": {}},
            "core_rule": {"decided_on": last, "pct": pct, "applied": pct, "units100": {"1655.T": u100},
                          "px": {"1655.T": px}, "lot": {"1655.T": lot}}}


def test_core_pct_for_rounds_so_the_target_is_exact():
    for tg, u100, lot in ((1130, 1140, 10), (1000, 1140, 10), (37, 123, 1), (0, 1140, 10), (1140, 1140, 10), (990, 1000, 10)):
        p = MO.core_pct_for(tg, u100, lot)
        assert int(u100 * p / 100 / lot + 1e-9) * lot == tg and 0 <= p <= 100
    assert MO.core_pct_for(1130, 1140, 10) == 99.13                      # 四舍五入的 99.12% 会少一个单元（1120 口）
    assert MO.core_pct_for(5, 0, 1) == 0.0


def test_core_rec_converts_sell_trim_adjust_into_the_ratio():
    b = _cbook()
    assert _conv(b, kind="sell") == {"kind": "core", "pct": 0.0, "ticker": "1655.T", "target": 0, "source": "cli"}
    a = _conv(b, kind="adjust", unit="shares", value=1000)
    assert (a["pct"], a["target"]) == (87.72, 1000)                      # 1000 ÷ 1140
    assert _conv(b, kind="adjust", unit="shares", value=1135)["target"] == 1130        # 按单元（10 口）向下取整
    assert _conv(b, kind="adjust", unit="shares", value=5000) == {**a, "pct": 100.0, "target": 1140}   # 不超过规则目标（比例 100%）
    assert _conv(b, kind="adjust", unit="yen", value=350_000)["target"] == 500         # ¥35 万 ÷ ¥700
    assert _conv(b, kind="adjust", unit="pct", value=21)["target"] == 300              # ¥100 万 × 21% ÷ ¥700 → 300 口
    assert _conv(b, kind="trim", pct=35)["target"] == 500
    with pytest.raises(ValueError, match="减仓只能减不能加"):
        _conv(b, kind="trim", pct=90)
    assert MO.core_rec(MO.normalize({"kind": "sell", "ticker": "7203"}), b) is None    # 个股：照原来的指令
    assert MO.describe(a) == "调仓 1655.T → 约 1,000 口（闲置资金比例 87.72%）"
    assert MO.describe(_conv(b, kind="sell")) == "卖出全部 1655.T（之后停买闲置资金 ETF）"
    for bk in ({**_cbook(), "core_rule": {}}, _cbook(u100=0), _cbook(plan={"1655.T": ["SELL", 1130]}), _cbook(px=0)):
        assert _conv(bk, kind="sell")["pct"] == 0.0                       # 卖出全部 = 比例 0%：不用规则目标额（执行器还没算过 / 规则在卖也行）
    with pytest.raises(ValueError, match="现在没有"):
        _conv(_cbook(units=0), kind="sell")
    bad = [(_cbook(units=0), "现在没有"), ({**_cbook(), "core_rule": {}}, "现在没有"), (_cbook(u100=0), "规则这次在卖"),
           (_cbook(plan={"1655.T": ["SELL", 1130]}), "规则这次在卖"), (_cbook(px=0), "收盘价")]
    for bk, why in bad:                                                   # 调仓要规则目标额
        with pytest.raises(ValueError, match=why):
            _conv(bk, kind="adjust", unit="shares", value=500)
    with pytest.raises(ValueError, match="目标口数"):
        MO.normalize({"kind": "core", "pct": 50, "ticker": "1655", "target": -1})


def test_check_and_now_due_for_the_ratio():
    b = _cbook()
    assert MO.check(_conv(b, kind="adjust", unit="shares", value=1140), b) == "1655.T 换算成闲置资金比例还是 100%：不用调"
    assert MO.check(_conv(b, kind="adjust", unit="shares", value=1000), b) is None
    at = lambda h, m: dt.datetime(2026, 10, 6, h, m, tzinfo=JST)        # noqa: E731  2026-10-06（火）
    assert not MO.now_due("cd", b, at(10, 0))                             # 没改比例
    b["manual"]["core_pct"] = 50.0                                        # 执行器读进来了、还没照它调
    assert MO.now_due("cd", b, at(10, 0)) and not MO.now_due("cd", b, at(8, 50)) and not MO.now_due("cd", b, at(12, 0))
    b["core_rule"]["defer"] = "2026-10-06"
    assert not MO.now_due("cd", b, at(10, 0))                             # 今天已经说了「下一次决策照新比例」
    del b["core_rule"]["defer"]
    b["core_rule"]["tried"] = at(9, 55).isoformat()
    assert not MO.now_due("cd", b, at(10, 0)) and MO.now_due("cd", b, at(10, 5))   # 取不到价：10 分钟后再叫
    b["core_rule"].update(applied=50.0)
    assert not MO.now_due("cd", b, at(10, 30))                            # 已经照新比例调过


# ────────── ③ 执行器：模拟账户 ──────────
def test_paper_etf_sell_all_at_once_and_the_rule_does_not_buy_back():
    r = _paper("ca")
    _morning(r, until=12)
    u0 = r.eng.st.core_units["1655.T"]
    rec = _conv(r.ux.book, kind="sell")
    assert rec["pct"] == 0.0 and rec["target"] == 0
    rq = _write(r.tag, "M-core-sell", **rec)
    r.now["t"] = _at(r, 10, 0)
    assert MO.now_due(r.tag, r.ux.book, r.now["t"])
    res = r.ux.now_phase(_quote(PX))
    (o,) = _core_orders(r)
    assert o.side == "SELL" and o.qty == u0 and o.status == "FILLED" and o.phase == "now" and o.kind == "core"
    assert "1655.T" not in _held(r) and r.eng.st.core_units["1655.T"] == u0     # 券商当场成交；账本明天早上对账
    assert r.ux.book["core_rule"]["applied"] == 0.0 and res["items"][-1]["status"] == "盘中已调"
    assert f"盘中卖出 1655.T {u0:,} 口" in _item(r, rq["id"])["msg"]
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 30))
    _morning(r)                                                            # 对账（持仓核对在 _morning 里）→ 决策：比例 0%
    st = r.eng.st
    assert st.core_units.get("1655.T", 0) == 0 and "1655.T" not in st.core_plan and abs(r.b.cash() - st.cash_jpy) < 1.0
    assert r.ux.book["core_rule"]["pct"] == 0.0 and r.ux.book["core_rule"]["units100"]["1655.T"] > 0
    _morning(r)
    assert r.eng.st.core_units.get("1655.T", 0) == 0 and not r.ux.blocked


def test_ratio_before_the_morning_run_goes_into_the_decision_then_raise_at_once():
    r = _paper("cb")
    _morning(r, until=12)
    u0 = r.eng.st.core_units["1655.T"]
    _write(r.tag, "M-core-50", kind="core", pct=50.0)                      # 07:40 之前写的：早上的决策照它（不看再平衡带）
    _morning(r)
    cr = r.ux.book["core_rule"]
    assert cr["applied"] == 50.0 and r.eng.st.core_plan["1655.T"][0] == "SELL"
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 0))                  # 已经照新比例下了开盘的单
    _morning(r)
    u1 = r.eng.st.core_units["1655.T"]
    assert 0.45 * u0 < u1 < 0.55 * u0
    c = MO.core_info(r.ux.book, "1655.T")
    rec = _conv(r.ux.book, kind="adjust", unit="shares", value=c["u100"])    # 盘中调回规则目标（比例 100%）
    assert rec["pct"] == 100.0 and c["pct"] == 50.0
    _write(r.tag, "M-core-up", **rec)
    r.now["t"] = _at(r, 10, 0)
    cash0 = r.b.cash()
    r.ux.now_phase(_quote(PX))
    (o,) = _core_orders(r)
    assert o.side == "BUY" and o.status == "FILLED" and 0 < o.qty <= c["u100"] - u1 and o.limit > 0
    assert r.b.cash() < cash0 and r.ux.book["core_rule"]["applied"] == 100.0
    _morning(r)
    assert r.eng.st.core_units["1655.T"] == u1 + o.qty and abs(r.b.cash() - r.eng.st.cash_jpy) < 1.0
    _morning(r)
    assert not r.ux.blocked


def test_etf_with_an_order_today_or_adjusted_today_waits_for_the_next_decision():
    r = _paper("cc")
    _morning(r, until=12)
    _write(r.tag, "M-core-50", kind="core", pct=50.0)
    _morning(r)                                                            # 今天开盘有规则的 1655 卖单（照 50%）
    _write(r.tag, "M-core-30", kind="core", pct=30.0)
    r.now["t"] = _at(r, 10, 0)
    res = r.ux.now_phase(_quote(PX))
    assert not _core_orders(r) and res["later"] == 1 and res["items"][-1]["status"] == "明天开盘"
    cr = r.ux.book["core_rule"]
    assert cr["defer"] == r.now["t"].date().isoformat() and cr["applied"] == 50.0
    assert "今天已经有执行器的单" in _item(r, "M-core-30")["msg"]
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 11, 0))                  # 今天不再叫
    _morning(r)                                                            # 下一次决策：照 30%（不看再平衡带）
    cr = r.ux.book["core_rule"]
    assert cr["applied"] == 30.0 and "defer" not in cr and r.eng.st.core_plan["1655.T"][0] == "SELL"
    _morning(r)
    u = r.eng.st.core_units["1655.T"]
    assert abs(u - 0.3 * cr["units100"]["1655.T"]) <= 10
    _write(r.tag, "M-core-0", kind="core", pct=0.0)                         # 盘中调一次……
    r.now["t"] = _at(r, 10, 0)
    r.ux.now_phase(_quote(PX))
    assert len(_core_orders(r)) == 1 and r.ux.book["core_rule"]["applied"] == 0.0
    _write(r.tag, "M-core-100", kind="core", pct=100.0)                     # ……同一天再改：账本的口数还没算进今天的成交 → 明天
    r.now["t"] = _at(r, 11, 0)
    res = r.ux.now_phase(_quote(PX))
    assert len(_core_orders(r)) == 1 and res["items"][-1]["status"] == "明天开盘"
    assert "今天已经调过一次" in _item(r, "M-core-100")["msg"]
    _morning(r)
    assert r.eng.st.core_units.get("1655.T", 0) == 0 and r.eng.st.core_plan["1655.T"][0] == "BUY"   # 先对账（卖光）再照 100% 买
    assert r.ux.book["core_rule"]["applied"] == 100.0


def test_ratio_waits_without_a_price_and_under_halt():
    r = _paper("cd")
    _morning(r, until=12)
    _write(r.tag, "M-core-60", kind="core", pct=60.0)
    paths.halt_file().write_text("测试", encoding="utf-8")
    r.now["t"] = _at(r, 10, 0)
    res = r.ux.now_phase(_quote(PX))
    assert not _core_orders(r) and res["retry"] == 1 and "HALT" in res["items"][-1]["msg"]
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 30))
    paths.halt_file().unlink()
    r.now["t"] = _at(r, 10, 20)
    res = r.ux.now_phase(lambda ts: {})                                     # 取不到现价：10 分钟后再试
    assert not _core_orders(r) and res["retry"] == 1 and res["items"][-1]["status"] == "等"
    assert "1655.T 取不到现价" in _item(r, "M-core-60")["msg"]
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 25)) and MO.now_due(r.tag, r.ux.book, _at(r, 10, 31))
    r.now["t"] = _at(r, 10, 31)
    r.ux.now_phase(_quote(PX))
    (o,) = _core_orders(r)
    assert o.side == "SELL" and o.status == "FILLED" and r.ux.book["core_rule"]["applied"] == 60.0


# ────────── ③ 执行器：立花适配器 + 模拟交易所 ──────────
class _NoIntradayCoreFill(SimExchange):
    """盘中（开盘后的当日限り）的 1655 卖单不成交（例如限价没碰到），收盘失效。"""

    def _fill(self, o, op):
        if o["ticker"] == "1655.T" and o["cond"] == self.spec.cond_normal and o["side"] == "SELL":
            return
        super()._fill(o, op)


def test_tachibana_etf_trim_at_once_reconciles_next_morning():
    r = _Run([1000.0] * 30, entry=())                                      # 牛市、没有个股：闲置资金都在 1655
    r.until(12)
    u0 = r.eng.st.core_units["1655.T"]
    rec = _conv(r.ux.book, kind="adjust", unit="shares", value=u0 - 50)     # 少 50 口（在再平衡带里：规则自己不会动）
    _write(TAG, "M-core-t", **rec)
    res = r.session(10, 0)
    (o,) = _core_orders(r)
    assert o.side == "SELL" and o.qty == 50 and o.status == "FILLED" and res["items"][-1]["status"] == "盘中已调"
    assert r.exch.pos["1655.T"] == u0 - 50
    r.day()                                                                # 收盘 → 第二天早上：对账（持仓核对）→ 决策
    assert r.eng.st.core_units["1655.T"] == u0 - 50 and not r.ux.blocked and "1655.T" not in r.eng.st.core_plan
    r.day()
    assert r.eng.st.core_units["1655.T"] == u0 - 50 and not r.ux.blocked   # 规则照新比例：不调回去


def test_tachibana_unfilled_intraday_etf_order_is_redone_by_the_next_decision():
    r = _Run([1000.0] * 30, exchange_cls=_NoIntradayCoreFill, entry=())
    r.until(12)
    u0 = r.eng.st.core_units["1655.T"]
    rec = _conv(r.ux.book, kind="adjust", unit="shares", value=u0 - 50)
    _write(TAG, "M-core-t", **rec)
    r.session(10, 0)
    (o,) = _core_orders(r)
    assert o.status == "SENT" and r.ux.book["core_rule"]["applied"] == rec["pct"]
    r.day()                                                                # 对账：没成交 → 这次决策照新比例（不看再平衡带）
    assert r.eng.st.core_units["1655.T"] == u0 and not r.ux.blocked
    assert r.eng.st.core_plan["1655.T"] == ["SELL", 50] and "redo" not in r.ux.book["core_rule"]
    r.day()
    assert r.eng.st.core_units["1655.T"] == u0 - 50 and not r.ux.blocked


class _NoOpenCoreSellOnce(SimExchange):
    """开盘（寄付）的 1655 卖单第一次没成交（例如在立花网站上撤了）。"""
    done = False

    def _fill(self, o, op):
        if o["ticker"] == "1655.T" and o["side"] == "SELL" and o["cond"] == self.spec.cond_opening and not self.done:
            self.done = True
            o["status"] = "12"
            return
        super()._fill(o, op)


def test_ratio_change_stays_pending_until_the_etf_orders_fill():
    """开盘前写的比例进早上的决策（不看再平衡带）；那张核心单没成交（HALT / 没成交 / 没下）→ 第二天的决策再照比例调，不被再平衡带吞掉。"""
    r = _Run([1000.0] * 30, exchange_cls=_NoOpenCoreSellOnce, entry=())
    r.until(12)
    u0 = r.eng.st.core_units["1655.T"]
    rec = _conv(r.ux.book, kind="adjust", unit="shares", value=u0 - 50)     # 少 50 口：在再平衡带里
    _write(TAG, "M-core-a", **rec)
    r.day()                                                                # 07:40：照新比例的决策 → 开盘卖 50 口
    cr = r.ux.book["core_rule"]
    assert cr["exact_on"] == r.eng.st.last_date and cr["exact_plan"] == ["1655.T"] and cr["applied"] == rec["pct"]
    assert r.eng.st.core_plan["1655.T"] == ["SELL", 50]
    r.day()                                                                # 开盘没成交 → 对账记下 → 这次决策再照比例
    assert r.eng.st.core_units["1655.T"] == u0 and r.eng.st.core_plan.get("1655.T") == ["SELL", 50] and not r.ux.blocked
    r.day()                                                                # 这次成交
    assert r.eng.st.core_units["1655.T"] == u0 - 50 and "1655.T" not in r.eng.st.core_plan
    assert "exact_on" not in r.ux.book["core_rule"] and "redo" not in r.ux.book["core_rule"]
    r.day()
    assert r.eng.st.core_units["1655.T"] == u0 - 50 and not r.ux.blocked


# ────────── ④ 面板 ──────────
def _pbook(tag="paper", orders=None, plan=None, rule=True, pct=100.0, applied=None):
    st = {"last_date": "2026-10-05", "cash_jpy": 50_000.0, "history": [["2026-10-05", 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 100, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0,
                             "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {"1655.T": 1130}, "core_plan": plan or {}}
    b = {"state": st, "orders": orders or [], "manual": {"core_pct": pct, "items": {}, "blocks": {}, "trims": {}}}
    if rule:
        b["core_rule"] = {"decided_on": "2026-10-05", "pct": pct, "applied": pct if applied is None else applied,
                          "units100": {"1655.T": 1140}, "px": {"1655.T": 700.0}, "lot": {"1655.T": 10}}
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


AT = dt.datetime(2026, 10, 6, 10, 0, tzinfo=JST)                           # 盘中


def _etf_block(html: str) -> str:
    i = html.index("1655.T")
    return html[i:html.index("</div></div>", html.index("data-kind='core'", i))]


def test_render_buttons_under_the_held_etf():
    _pbook()
    h = panel.render("paper", "tok", now=AT)
    assert "data-act='core-sell'" in h and "data-core='1'" in h and "data-lot='10'" in h and "data-u100='1140'" in h
    assert "现在 1,130 口 · 约 ¥791,000 · 约占权益 79.1% · 闲置资金比例 100%" in h
    assert "id='core'" not in h                                            # 拿着 ETF：在它下面调，不另外放比例卡片
    assert "<div class='qt small' data-q='1655.T'></div>" in h and "<div class='qt small' data-q='7203.T'></div>" in h   # 现价的位置
    _pbook(rule=False)                                                     # 执行器还没算过规则目标额：卖出全部照样可以，调仓等下一次运行
    h = panel.render("paper", "tok", now=AT)
    assert "data-act='core-sell'" in h and "data-act='adj' data-t='1655.T'" not in h and "id='core'" in h
    assert "现在 1,130 口 · 调仓在执行器下一次运行（交易日 07:40）之后可用" in h
    _pbook(plan={"1655.T": ["SELL", 1130]})
    h = panel.render("paper", "tok", now=AT)
    assert "规则在开盘卖出（熊市 / 换 ETF）" in h and "data-act='core-sell'" in h and "data-act='adj' data-t='1655.T'" not in h
    _pbook(pct=50.0, applied=100.0)
    assert "闲置资金比例 50%（还没照它调完，见「手动指令」）" in panel.render("paper", "tok", now=AT)
    _pbook(orders=[{"cid": "U2026-10-05-SELL-1655.T-N100000", "ticker": "1655.T", "side": "SELL", "kind": "core", "qty": 130,
                    "decided_on": "2026-10-05", "reason": "manual_core", "phase": "now", "status": "FILLED",
                    "filled_qty": 130, "filled_px": 700.0}])
    h = panel.render("paper", "tok", now=AT)
    assert "今天盘中已照比例卖出 130 口（已成交）：口数明天早上对账后更新" in h and "data-act='core-sell'" not in h
    _pbook()
    MO.append("paper", {"kind": "core", "pct": 80.0}, clock=lambda: AT)
    assert "有一条闲置资金比例的指令在处理" in panel.render("paper", "tok", now=AT)


def test_submit_etf_adjust_and_sell_become_the_ratio():
    _pbook()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "adjust", "ticker": "1655", "unit": "shares", "value": 1000}, AT)
    assert ok and rec["kind"] == "core" and (rec["pct"], rec["ticker"], rec["target"]) == (87.72, "1655.T", 1000)
    assert msg.startswith("已写：1655.T 卖 130 口（闲置资金比例 100% → 87.72%）→ 马上（盘中）卖出")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "adjust", "ticker": "1655", "unit": "shares", "value": 1000}, AT)
    assert not ok and "还是 87.72%：不用调" in msg                           # 执行器还没读的那条算「现在的比例」
    (MO.requests_path("paper")).unlink()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "sell", "ticker": "1655.T"}, dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST))
    assert ok and rec["pct"] == 0.0 and msg.startswith("已写：卖出全部 1655.T → 今天 09:00 开盘卖出；之后停买闲置资金 ETF（出现买入信号会提醒，你确认才买）")
    (MO.requests_path("paper")).unlink()
    ok, msg, _ = panel.submit({"book": "paper", "kind": "adjust", "ticker": "1655", "unit": "shares", "value": 1140}, AT)
    assert not ok and "还是 100%：不用调" in msg
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "1655"}, AT)
    assert not ok and "核心 ETF：不能手动买" in msg


def test_ratio_effects_on_the_other_core_etf():
    b = _pbook()
    b["state"]["core_units"]["1545.T"] = 100
    b["core_rule"]["units100"]["1545.T"] = 110
    b["core_rule"]["lot"]["1545.T"] = 1
    b["core_rule"]["px"]["1545.T"] = 20_000.0
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    assert MO.core_effects(b, 87.72, skip="1655.T") == [("1545.T", 100, 96)]
    assert MO.core_effects(b, 100.0) == [("1545.T", 100, 110), ("1655.T", 1130, 1140)]
    assert MO.core_effects(b, 0.0, skip="1545.T") == [("1655.T", 1130, 0)]
    ok, msg, _ = panel.submit({"book": "paper", "kind": "adjust", "ticker": "1655", "unit": "shares", "value": 1000}, AT)
    assert ok and "；同一比例也用在：1545.T 100 → 96 口" in msg
    h = panel.render("paper", "tok", now=AT)
    assert '"cores": {"1655.T": {"cur": 1130, "u100": 1140, "lot": 10}, "1545.T": {"cur": 100, "u100": 110, "lot": 1}}' in h


def test_adjust_dialog_in_core_mode_in_node(tmp_path):
    """对话框的核心 ETF 模式（按 10 口分格、最右边 = 规则目标、预览写比例）在 node 里实际跑（假的最小 DOM）。没有 node 就跳过。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    fns = "\n".join(_js_fn(panel._JS, n) for n in ("nd", "pctOf", "ALOT", "UW", "cpctOf", "adjCap", "adjTarget", "adjBar",
                                                    "coreFx", "adjPrevCore"))
    js = """
class El { constructor(t){ this.tagName=String(t).toUpperCase(); this.children=[]; this._t=''; this.className=''; this.style={}; this.attrs={};
  this.value=''; this.disabled=false; const s=this; this.classList={add(c){ s.className=(s.className ? s.className+' ' : '')+c; }}; }
  appendChild(c){ this.children.push(c); return c; }
  set textContent(v){ this._t=String(v); this.children=[]; } get textContent(){ return this._t+this.children.map(c=>c.textContent).join(''); }
  setAttribute(k,v){ this.attrs[k]=String(v); } }
const document={createElement:t=>new El(t), createTextNode:t=>{ const e=new El('#text'); e._t=String(t); return e; }};
const CFG={eq:1000000, cap:34, when:'马上（盘中）', cores:{'1655.T':{cur:1130, u100:1140, lot:10}}}, LOT=100;
const fmt=n=>Number(n).toLocaleString('ja-JP'), yen=n=>'¥'+Math.round(n).toLocaleString('ja-JP');
const R={max:'1140', value:'1130', attrs:{}, setAttribute(k,v){ this.attrs[k]=String(v); }};
const ELS={'#adj-range':R, '#adj-bar':new El('div'), '#adj-lab':new El('div'), '#adj-note':new El('div'), '#adj-go':new El('button'),
           '#adj-prev':new El('div'), '#adj-val':new El('input')};
const $=s=>ELS[s];
let ADJ={t:'1655.T', shares:1130, px:700, unit:'shares', core:true, lot:10, u100:1140, cpct:100};
__FNS__
const out={cap:adjCap(), unit:UW(), lot:ALOT()};
const prev=v=>{ $('#adj-val').value=String(v); const n=adjTarget(); adjPrevCore(n);
  return {n:n, text:$('#adj-prev').textContent, go:$('#adj-go').textContent, dis:$('#adj-go').disabled, cls:$('#adj-go').className}; };
out.down=prev(1000); out.capsame=prev(5000); out.same=prev(1135); out.zero=prev(0);
adjBar(); out.note=$('#adj-note').textContent; out.cells=ELS['#adj-bar'].children.length;
ADJ={...ADJ, shares:570, cpct:50}; out.up=prev(5000);
CFG.cores['1545.T']={cur:100, u100:110, lot:1}; ADJ={...ADJ, shares:1130, cpct:100}; out.fx=prev(1000);   // 同时拿两只：别的跟着变
console.log(JSON.stringify(out));
""".replace("__FNS__", fns)
    f = tmp_path / "c.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    assert (o["cap"], o["unit"], o["lot"]) == (1140, "口", 10)
    d = o["down"]
    assert d["n"] == 1000 and d["go"] == "确认卖出 130 口" and not d["dis"] and d["cls"] == "btn danger"
    assert "卖出 130 口（约 ¥91,000）：1,130 → 1,000 口" in d["text"] and "闲置资金比例 100% → 87.72%" in d["text"]
    assert "马上（盘中）卖出" in d["text"]
    c = o["capsame"]                                                       # 截到规则目标 = 比例 100% = 现在的比例
    assert c["dis"] and "截到 1,140 口" in c["text"] and "换算成闲置资金比例还是 100%：不用调" in c["text"]
    u = o["up"]
    assert u["go"] == "确认买入 570 口" and u["cls"] == "btn primary" and "截到 1,140 口" in u["text"]
    assert "闲置资金比例 50% → 100%" in u["text"] and "马上（盘中）买入" in u["text"]
    assert o["same"]["dis"] and o["same"]["text"] == "现在就是 1,130 口：不用调"     # 1135 → 按 10 口取整 = 1130 = 现在
    assert "同一比例" not in d["text"]                                       # 只拿一只：没有别的跟着变
    assert "★ 同一比例也用在：1545.T 100 → 96 口" in o["fx"]["text"]          # 110 × 87.72% = 96.5 → 96 口
    assert o["zero"]["go"] == "确认卖出 1,130 口" and "→ 0%" in o["zero"]["text"]
    assert "一格 = 30 口（拖动按 10 口一步）" in o["note"] and "最右边 = 规则目标额（比例 100%）" in o["note"]   # 114 个单元 → 3 个并一格
    assert o["cells"] == 38


# ────────── ⑤ 命令行 ──────────
def test_cli_manual_adjust_on_an_etf_writes_the_ratio(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    _pbook()
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    assert run.main(["manual", "adjust", "1655", "--shares", "1000", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "调仓 1655.T → 约 1,000 口（闲置资金比例 87.72%）" in out
    assert "1655.T 1,130 → 1,000 口（闲置资金比例 100% → 87.72%" in out
    (r,) = MO.read_all("paper")
    assert (r["kind"], r["pct"], r["target"]) == ("core", 87.72, 1000)
    assert run.main(["manual", "trim", "1655", "--pct", "95", "--broker", "paper"]) == 2
    assert "减仓只能减不能加" in capsys.readouterr().out
