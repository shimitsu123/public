"""手动买入 / 加仓没下成、没成交的缺口（2026-10-14 复核：G4 / G5 / G6 / G14 / G15 / G21 / G25）：
G4 盘中买入也不拿出金预留买（与决策同一口径；面板「够买」的现金也扣掉）；
G5 下单时才查的闸门（资格检查 / 立花能不能买 / LU-15）在凑钱卖核心 ETF 之前；凑钱已经卖了、买单才没成 → 说明里写清楚；
G6 凑钱要卖的核心 ETF 今天已经有单 → 明天开盘、取不到现价 → 一会儿再试（不当成钱不够）；
G14 开盘买入一股没买就被跳过 / 被挡的规则新仓不算「已经排在开盘买入」、不占名额；
G15 适配器挡下的原因分类：临时的（マスタ取不到 / 登录失败 / 没连上）一会儿再试、买不了的当场不做、早上的买入排进计划前先查；
G21 开盘的手动买入因为系统原因没下（异常熔断 / 开盘后补单没跑…）→ 留到下一次决策，不当成「没买到 → 只做一次」；
G25 模拟账户的说明写「模拟账户」而不是「立花」。"""
import dataclasses

from qbreak import manual_orders as MO
from qbreak.brokers.base import Order
from qbreak.live_unified import LATE_BUY_NOTE, ExecOrder, UnifiedExecutor, block_kind

from test_manual_buy import _buy, _write
from test_manual_now import PX, _at, _item, _morning, _paper, _quote, _req
from test_manual_orders import TAG, _Run

QX = {"A.T": 1000.0, "B.T": 1500.0, "1655.T": 700.0}


def _hist(r, t: str) -> list[tuple[str, str, str]]:
    """这只票所有的单（历史 + 当前决策）：(cid, 状态, 说明)。"""
    out = [(o["cid"], o["status"], o.get("note") or "") for h in r.ux.book.get("history") or [] for o in h["orders"] if o["ticker"] == t]
    return out + [(o.cid, o.status, o.note or "") for o in r.ux.orders if o.ticker == t]


def _no_open_phase_day(r) -> None:
    """r.day() 但 09:05 / 09:20 开盘后的补单没有运行（Mac 睡着了…）：开盘撮合 → 第二天 07:40 的早上运行。"""
    k = r.k
    r.exch.open(k)
    r.exch.close_day()
    r.exch.set_day(k + 1)
    r.now["t"] = r.at(k, 7, 40)
    r.ux.morning([k])
    r.k += 1


# ────────── G4：出金预留 ──────────
def test_g4_intraday_buy_does_not_spend_the_withdrawal_reserve():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    r.ux.book["flows"] = [{"date": str(r.eng.gidx[r.k - 1].date()), "jpy": -760000.0, "reserve": True, "note": "test"}]
    u0 = dict(r.exch.pos)
    _buy(r, unit="pct", value=50, id="M-g4")
    res = r.session(10, 0)
    it = r.item("M-g4")
    assert res["rejected"] == 1 and it["status"] == "rejected"
    assert "不够买 1 个单元" in it["msg"] and "出金预留 ¥760,000 不能用" in it["msg"]
    assert dict(r.exch.pos) == u0                                         # 核心 ETF 也没为它卖
    r2 = _Run([1000.0] * 30, entry=(10,))                                 # 对照：没有出金预留 → 照常买（卖核心补）
    r2.until(14)
    _buy(r2, unit="pct", value=50, id="M-g4b")
    assert r2.session(10, 0)["placed"] == 1 and r2.item("M-g4b")["status"] == "placed"


def test_g4_fund_holdings_cash_is_after_the_reserve():
    book = {"state": {"cash_jpy": 1_000_000.0, "pos": {}, "core_units": {}}, "manual": {"items": {}},
            "flows": [{"date": "2026-10-13", "jpy": -300000.0, "reserve": True}]}
    f = MO.fund_holdings(book, "tachibana")
    assert f["reserve"] == 300000 and f["cash"] == round(700000 * (1 - MO.CASH_BUF_PCT / 100))
    p = MO.fund_holdings(book, "paper")                                    # 模拟账户：执行器不扣预留，页面也不扣
    assert p["reserve"] == 0 and p["cash"] == round(1_000_000 * (1 - MO.CASH_BUF_PCT / 100))
    book["flows"][0]["seen_after"] = "2026-10-14"                          # 到账了：不再预留
    assert MO.fund_holdings(book, "tachibana")["reserve"] == 0


# ────────── G5：闸门在凑钱之前 ──────────
def test_g5_intraday_eligibility_block_does_not_sell_core_first():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    r.ux.pre_send = lambda t, side, kind: "被踢出日経225（测试）" if t == "B.T" and side == "BUY" else None
    u0 = dict(r.exch.pos)
    _buy(r, id="M-g5")
    r.session(10, 0, quote=_quote(QX))
    it = r.item("M-g5")
    assert it["status"] == "rejected" and "不买：资格检查：被踢出日経225" in it["msg"]
    assert dict(r.exch.pos) == u0 and not [o for o in r.ux.orders if o.phase == "now"]   # 一笔都没发（以前先卖了核心 ETF）


def test_g5_morning_plain_buy_lu15_is_rejected_before_the_rule_sells_core():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    core0 = int(r.eng.st.core_units["1655.T"])
    _buy(r, id="M-g5m")
    r.ux._prev_closes = lambda ts: {"B.T": 1600.0}                        # 立花前日終値 ≠ Yahoo 收盘 6.7%
    r.day()
    it = r.item("M-g5m")
    assert it["status"] == "rejected" and "立花前日終値" in it["msg"] and "只做一次" in it["msg"]
    d = r.eng.st.last_date
    assert not [o for o in r.ux.orders if o.decided_on == d and (o.ticker == "B.T" or o.kind == "core")]   # 规则没为它卖核心 ETF
    del r.ux._prev_closes
    r.day()
    assert int(r.eng.st.core_units["1655.T"]) == core0


def test_g5_refusal_after_core_was_sold_says_so():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    orig = r.b.buy

    def buy(ticker, qty, **kw):                                            # 交易所拒绝 B.T 的买单（例：余力不足）
        if ticker == "B.T":
            return Order(ticker, "BUY", qty, kw.get("limit") or 0, "", "REJECTED", client_id=kw.get("client_id", ""),
                         note="余力不足（测试）")
        return orig(ticker, qty, **kw)
    r.b.buy = buy
    _buy(r, id="M-g5s")
    r.session(10, 0, quote=_quote(QX))
    it = r.item("M-g5s")
    assert it["status"] == "rejected" and "立花没受理：余力不足" in it["msg"]
    assert "已卖核心 ETF 1655.T" in it["msg"] and "钱留现金" in it["msg"]


# ────────── G6：凑钱的核心 ETF 今天有单 / 取不到现价 ──────────
def test_g6_core_with_an_order_today_means_tomorrow_not_shortfall():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(10)                                                            # 这次决策：A.T 新仓 + 卖核心 ETF 凑钱（今天有单）
    assert any(o.ticker == "1655.T" and o.side == "SELL" for o in r.ux.orders)
    _buy(r, id="M-g6")
    res = r.session(10, 0, quote=_quote(QX))
    it = r.item("M-g6")
    assert res["later"] == 1 and it["status"] == "pending" and it.get("hold")
    assert "凑钱要卖的核心 ETF 1655.T 今天已经有执行器的单" in it["msg"] and MO.status_text(it) == "明天开盘"


def test_g6_core_without_a_quote_retries():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    u0 = dict(r.exch.pos)
    _buy(r, id="M-g6q")
    res = r.session(10, 0, quote=_quote({"A.T": 1000.0, "B.T": 1500.0}))   # 核心 ETF 这一刻取不到现价
    it = r.item("M-g6q")
    assert res["retry"] == 1 and it["status"] == "pending" and not it.get("hold")
    assert "凑钱要卖的核心 ETF 1655.T 取不到现价" in it["msg"] and dict(r.exch.pos) == u0
    res = r.session(10, 10, quote=_quote(QX))                             # 10 分钟后取到了 → 卖核心补、买入
    assert res["placed"] == 1 and r.item("M-g6q")["status"] == "placed"


# ────────── G14：没买成的规则新仓不占位 ──────────
def test_g14_plan_live_drops_entries_whose_open_order_died():
    d = "2026-10-13"
    plan = {"A.T": [1000.0, 100, d], "B.T": [1000.0, 100, d], "C.T": [1000.0, 100, d]}
    orders = [{"cid": "a", "ticker": "A.T", "side": "BUY", "kind": "stock", "decided_on": d, "status": "SKIPPED", "filled_qty": 0},
              {"cid": "b", "ticker": "B.T", "side": "BUY", "kind": "stock", "decided_on": d, "status": "SENT", "filled_qty": 0},
              {"cid": "c", "ticker": "C.T", "side": "BUY", "kind": "stock", "decided_on": d, "status": "BLOCKED", "filled_qty": 0},
              {"cid": "c2", "ticker": "C.T", "side": "BUY", "kind": "stock", "decided_on": d, "status": "SENT", "filled_qty": 0,
               "phase": "open"}]
    assert MO.plan_live(plan, orders, d) == {"B.T", "C.T"}                 # C.T 还有一笔在交易所 → 还算
    assert MO.plan_live(plan, orders[:1], "2026-10-14") == set(plan)       # 别的决策的单不算
    assert MO.plan_live(plan, [ExecOrder("x", "A.T", "BUY", "stock", 100, d, status="EXPIRED")], d) == {"B.T", "C.T"}
    st = {"last_date": d, "history": [[d, 1_000_000.0]], "pos": {}, "pending_exit": {}, "plan": {"A.T": plan["A.T"]}}
    book = {"state": st, "manual": {"items": {}, "blocks": {}, "max_positions": 1, "core": ["1655.T"]}, "orders": orders[:1]}
    assert MO.slots(book)["free"] == 1
    assert MO.check(MO.normalize({"kind": "buy", "ticker": "6501"}), book) is None
    assert MO.check({"kind": "buy", "ticker": "A.T", "unit": "rule"}, book) is None   # 以前：「已经排在开盘买入」
    book["orders"] = []
    assert "名额已满" in MO.check(MO.normalize({"kind": "buy", "ticker": "6501"}), book)


def test_g14_gap_skipped_rule_entry_does_not_hold_a_slot_intraday():
    opens = [1000.0] * 30
    opens[11] = 1060.0                                                     # A.T 新仓开盘跳空 +6% → 规则不买（SKIPPED）
    r = _Run([1000.0] * 30, a_open=opens, entry=(10,))
    r.eng.cfg = dataclasses.replace(r.eng.cfg, max_positions=1)
    r.until(10)
    assert "A.T" in r.eng.st.plan
    _buy(r, id="M-g14")
    res = r.session(10, 0, quote=_quote({**QX, "A.T": 1010.0}))
    assert any(s == "SKIPPED" for _, s, _n in _hist(r, "A.T"))
    assert res["placed"] == 1 and r.item("M-g14")["status"] == "placed"   # 以前：「个股名额已满」


# ────────── G15：适配器挡下的原因分类 ──────────
def test_g15_block_kind():
    assert block_kind("取不到现价，没下（不发成行单）") == "retry"
    assert block_kind("立花の銘柄マスタ取不到（TimeoutError: x）→ 确认不了能不能买，不下买单") == "retry"
    assert block_kind("登录失败，没发单（URLError）：x") == block_kind("没连上立花，没发单（ConnectionRefusedError）：x") == "retry"
    assert block_kind("上場廃止日 2026-11-01（30 天以内）→ 不下买单") == "no"
    assert block_kind("未 ARM：…") == block_kind("口座课税区分是一般口座…") == "no"
    assert block_kind("单笔金额 2,000,000 > 上限 1,000,000") == block_kind("存在 HALT 文件 x") == "later"


def _flaky_master(r, second: str):
    """立花能不能买：盘中的预先检查（第一次）过、适配器发单时（第二次起）返回 second。"""
    orig, n = r.b.tradable_block, {"B.T": 0}

    def tb(t, q=None):
        if t != "B.T":
            return orig(t, q)
        n["B.T"] += 1
        return None if n["B.T"] == 1 else second
    r.b.tradable_block = tb
    return n


def test_g15_intraday_transient_master_failure_retries_without_selling_core():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    orig = r.b.tradable_block
    r.b.tradable_block = lambda t, q=None: ("立花の銘柄マスタ取不到（TimeoutError: x）→ 确认不了能不能买，不下买单" if t == "B.T"
                                            else orig(t, q))
    u0 = dict(r.exch.pos)
    _buy(r, id="M-g15t")
    res = r.session(10, 0, quote=_quote(QX))
    it = r.item("M-g15t")
    assert res["retry"] == 1 and it["status"] == "pending" and not it.get("hold")
    assert it["msg"].startswith("立花の銘柄マスタ取不到（TimeoutError: x）：确认不了能不能买") and dict(r.exch.pos) == u0


def test_g15_intraday_delisting_rejects_now_and_does_not_come_back():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    orig = r.b.tradable_block
    r.b.tradable_block = lambda t, q=None: "上場廃止日 2026-11-01（30 天以内）→ 不下买单" if t == "B.T" else orig(t, q)
    u0 = dict(r.exch.pos)
    _buy(r, id="M-g15d")
    r.session(10, 0, quote=_quote(QX))
    it = r.item("M-g15d")
    assert it["status"] == "rejected" and "上場廃止" in it["msg"] and dict(r.exch.pos) == u0
    r.day()
    r.day()
    assert r.item("M-g15d")["status"] == "rejected" and not _hist(r, "B.T")   # 以前：明天开盘「已下单」、后天才作废


def test_g15_adapter_permanent_block_after_funding_is_rejected_and_says_core_was_sold():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _flaky_master(r, "現物買付「取引禁止」（立花の規制情報）→ 不下买单")
    _buy(r, id="M-g15a")
    r.session(10, 0, quote=_quote(QX))
    it = r.item("M-g15a")
    assert it["status"] == "rejected" and "取引禁止" in it["msg"] and "只做一次" in it["msg"]   # 以前：明天开盘
    assert "已卖核心 ETF 1655.T" in it["msg"]


def test_g15_adapter_transient_block_retries_and_the_later_fill_counts():
    """盘中第一笔被适配器挡下（マスタ取不到 → SKIPPED，一会儿再试）、10 分钟后重下成交：第二天早上的对账不能把那笔没发出的
    当成「没买到」把指令作废（以前先对到 SKIPPED 的那笔 → 作废，成交的那笔就记不到指令上）。"""
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _flaky_master(r, "立花の銘柄マスタ取不到（TimeoutError: x）→ 确认不了能不能买，不下买单")
    _buy(r, id="M-g15r")
    res = r.session(10, 0, quote=_quote(QX))
    it = r.item("M-g15r")
    assert res["retry"] == 1 and it["status"] == "pending" and "10 分钟后再试" in it["msg"]
    assert [s for _, s, _n in _hist(r, "B.T")] == ["SKIPPED"]
    r.b.tradable_block = lambda t, q=None: None                           # 之后マスタ取得到了
    res = r.session(10, 10, quote=_quote(QX))
    assert res["placed"] == 1 and r.item("M-g15r")["status"] == "placed"
    r.day()
    assert r.item("M-g15r")["status"] == "done" and "B.T" in r.eng.st.pos


def test_g15_morning_buy_and_add_reject_untradable_before_planning():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    orig = r.b.tradable_block
    r.b.tradable_block = lambda t, q=None: ("上場廃止日 2026-11-01（30 天以内）→ 不下买单" if t in ("A.T", "B.T") else orig(t, q))
    core0 = int(r.eng.st.core_units["1655.T"])
    _buy(r, id="M-g15b")
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 300, "source": "test", "id": "M-g15add",
            "at": r.at(r.k - 1, 6).isoformat()}, TAG)
    r.day()
    b, a = r.item("M-g15b"), r.item("M-g15add")
    assert b["status"] == "rejected" and b["msg"].startswith("不买：上場廃止") and "只做一次" in b["msg"]
    assert a["status"] == "rejected" and a["msg"].startswith("不加仓：上場廃止")
    d = r.eng.st.last_date
    assert not [o for o in r.ux.orders if o.decided_on == d and o.side == "BUY" and o.kind == "stock"]
    r.day()
    assert int(r.eng.st.core_units["1655.T"]) == core0                     # 规则没为它们卖核心 ETF


# ────────── G21：系统原因没下 → 留到下一次决策 ──────────
def test_g21_system_miss_classification():
    E = lambda st, note="", **kw: ExecOrder("c", "B.T", "BUY", "stock", 100, "2026-10-13", status=st, note=note, **kw)   # noqa: E731
    sm = UnifiedExecutor._system_miss
    assert sm(E("MISSED", "开盘后补单没有运行（--phase open），没买 —— 与模拟盘出现差异")) == "开盘后补单没有运行（--phase open）"
    assert sm(E("BLOCKED", "异常熔断：这次决策的规则单 30 笔")).startswith("异常熔断")
    assert sm(E("BLOCKED", "登录失败，没发单（URLError）：x")) and sm(E("SKIPPED", LATE_BUY_NOTE))
    for o in (E("SKIPPED", "开盘 1060 比信号日收盘 1000 高 +6.0%，超过 3%"), E("UNFILLED"), E("REJECTED", "余力不足"),
              E("BLOCKED", "上場廃止日 2026-11-01（30 天以内）→ 不下买单"), E("BLOCKED", "未 ARM：x"),
              E("BLOCKED", "Yahoo 收盘 ¥1,500 和立花前日終値 ¥1,600 差 6.7%（拆股 / 数据错？）：这只的买单不下"),
              E("BLOCKED", "dry-run 未真正发单"), E("BLOCKED", "单笔金额 2,000,000 > 上限 1,000,000"),
              E("BLOCKED", "异常熔断", phase="now"), E("MISSED", "x", broker_id="S1"), E("MISSED", "x", filled_qty=100)):
        assert sm(o) is None, o


def test_g21_breaker_keeps_the_manual_buy_for_the_next_decision():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _buy(r, id="M-g21")
    r.ux._breaker = lambda k, todo: "异常熔断：测试"
    r.day()
    d0 = r.eng.st.last_date
    assert r.item("M-g21")["status"] == "placed" and ("U%s-BUY-B.T-M" % d0, "BLOCKED", "异常熔断：测试") in _hist(r, "B.T")
    del r.ux._breaker
    r.ux.blocked = None
    r.day()
    it = r.item("M-g21")
    assert it["status"] == "placed" and it["decided_on"] == r.eng.st.last_date != d0   # 以前：「没买到 → 只做一次」
    assert any("不算没买到" in str(e.get("msg") or e) for e in r.ux.book.get("events") or [])
    r.day()
    assert r.item("M-g21")["status"] == "done" and "B.T" in r.eng.st.pos


def test_g21_deferred_buy_whose_open_phase_never_ran_is_kept():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _buy(r, id="M-g21d")
    r.day()                                                                # 决策：B.T 留到开盘后（开盘前的余力不够，先卖核心）
    d0 = r.eng.st.last_date
    assert [s for c, s, _n in _hist(r, "B.T") if d0 in c] == ["DEFERRED"]
    _no_open_phase_day(r)                                                  # 09:05 / 09:20 没跑 → 第二天早上对账：MISSED
    assert any(s == "MISSED" for _, s, _n in _hist(r, "B.T"))
    it = r.item("M-g21d")
    assert it["status"] == "placed" and it["decided_on"] == r.eng.st.last_date != d0   # 留到这次决策（不是只做一次）
    r.day()
    assert r.item("M-g21d")["status"] == "done" and "B.T" in r.eng.st.pos


# ────────── G25：模拟账户的说明 ──────────
def test_g25_paper_texts_say_paper_not_tachibana():
    r = _paper("pg25")
    _morning(r, until=14)
    r.b.state["positions"]["A.T"]["qty"] = 0                              # 模拟账户那边没有这只（例：状态文件被改）→ 卖单被拒
    it = _req(r, kind="sell", ticker="A.T", block_days=20)
    r.now["t"] = _at(r, 10, 0)
    r.ux.now_phase(_quote(PX))
    x = _item(r, it["id"])
    assert x["status"] == "rejected" and x["msg"].startswith("模拟账户没受理") and "立花" not in x["msg"]
    d = r.eng.st.last_date
    r.ux.orders.append(ExecOrder(f"U{d}-SELL-A.T-X", "A.T", "SELL", "stock", 100, d, status="ERROR", reason="manual"))
    why = r.ux.unknown_why()
    assert "模拟账户" in why and "立花的注文一覧" not in why
    assert r.ux.bname == "模拟账户"


def test_g25_tachibana_texts_keep_tachibana():
    r = _Run([1000.0] * 30, entry=(10,))
    assert r.ux.bname == "立花" and "立花的注文一覧" in r.ux.unk_hint
