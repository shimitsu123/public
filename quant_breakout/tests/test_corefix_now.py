"""固定口数当天按时段下单（D1）+ 核心 ETF 盘中买入的限价上限（M14）；2026-10-15。
事故（模拟账户，真实状态）：10/15 盘中把 1482.T 固定成 679 口 → 以前一律「下一次决策（10/16 07:40）读到 → 10/16 09:00 开盘」，
页面整天写「等执行器读」；当时账本：现金 191.68 円、1545.T 拿着、凑钱的卖 1545.T 已撤、买 1482.T 678 口还 DEFERRED（孤儿）。
现在：与卖出 / 买入同一个时段口径 —— 盘中写的马上按现价调（模拟账户当场成交）、决策之后开盘前 / 午休写的开盘后马上（按现价限价，
不是寄付）、决策之前写的那次决策读到、收盘后 / 休市日 → 下一次决策；面板什么时候叫执行器（now_due / due）、执行器什么时候下单、
写给你的说明三者一致（下面的参数化矩阵查）。同一只今天还没到交易所的单被取代、还挂在交易所的先等（不叠单）；
核心 ETF 盘中买入限价 = min(现价 ×1.005, 收盘 ×1.02)，现价更高 → 这次不买、10 分钟后再试。"""
import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.brokers.tachibana import TachibanaBroker
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.live_unified import ACCEPTED, UnifiedExecutor, _MemPaper
from qbreak.unified import UnifiedEngine

from test_core_etf_restore import CC, CFG2, _morning, _paper2, _w
from test_fund_src import _fixed_case, _one, _tachi2, _tday, _tfixed
from test_live_unified import EX, P, _frame
from test_manual_now import _at, _quote

PXQ = {"A.T": 1000.0, "B.T": 1500.0, "1545.T": 700.0, "1482.T": 1000.0}   # 盘中现价 = 收盘（M14 的上限之内）
SKIP_NOTE = "被新的固定口数取代"


def _disk(r) -> dict:
    """面板读到的账本（执行器存下的那一份）。"""
    r.ux.save(force=True)
    return json.loads((paths.state_dir() / f"live_unified_{r.tag}.json").read_text(encoding="utf-8"))


def _now_orders(r, reason: str | None = None) -> list:
    d = r.ux.book["state"]["last_date"]
    return [o for o in r.ux.orders if o.decided_on == d and o.phase == "now" and (reason is None or o.reason == reason)]


# ══════════════════════════ 重放 2026-10-15 的账本 ══════════════════════════
def _orphan(r):
    """固定 1482 678 口的决策：卖 1545（寄付）+ 买 1482 678 口（现金 191.68 円不够 → 等开盘后，fund_src = 那笔卖单）；
    卖单在执行器之外撤了（旧版本没有撤单级联）→ 买单还是 DEFERRED（孤儿）。"""
    sell, buy = _fixed_case(r)
    r.b.cancel_pending(sell.cid)
    sell.status = "CANCELLED"
    return sell, buy


def test_paper_replay_corefix_679_at_1030_supersedes_the_orphan_sells_1545_and_buys_now():
    r = _paper2()
    sell, buy = _orphan(r)
    assert r.eng.st.cash_jpy == pytest.approx(191.68) and int(r.eng.st.core_units["1545.T"]) > 0
    assert sell.status == "CANCELLED" and buy.status == "DEFERRED" and buy.qty == 678
    T = _at(r, 10, 30)
    w = _w(r.tag, "M-fix-679", kind="corefix", ticker="1482.T", units=679)    # 还没读的固定口数 679 口
    b = _disk(r)
    assert MO.now_due(r.tag, b, T) and not MO.due(r.tag, b, T)                # 面板：马上叫执行器 --phase now
    assert MO.wait_text(w, T, b, r.tag) == "等下单：马上（盘中）按现价下单（模拟账户当场成交）"
    r.now["t"] = T
    res = r.ux.now_phase(_quote(PXQ))
    assert res["placed"] == 1 and res["retry"] == 0 and res["later"] == 0
    assert buy.status == "SKIPPED" and buy.note == f"{SKIP_NOTE}（10:30）"     # 今天还没发出的旧买单：被取代，不叠单
    fs, fb = _now_orders(r, "fix_fund"), _now_orders(r, "core_fix")
    assert [(o.ticker, o.side, o.status) for o in fs] == [("1545.T", "SELL", "FILLED")]
    assert [(o.ticker, o.side, o.qty, o.status) for o in fb] == [("1482.T", "BUY", 679, "FILLED")]
    assert fb[0].limit == pytest.approx(1005.0) and fb[0].fund_src == [fs[0].cid]   # M14：min(现价 ×1.005, 收盘 ×1.02)
    cr = r.ux.book["core_rule"]
    assert cr["fix_applied"]["1482.T"] == 679 and cr["fix_fund"]["1482.T"]["cids"] == [fs[0].cid]
    it = r.ux.book["manual"]["items"]["M-fix-679"]
    assert it["status"] == "done" and it["msg"].startswith("1482 对冲版美国 7〜10 年国债 固定 679 口：今天还没发出的 买 1482")
    assert "盘中买入 1482 对冲版美国 7〜10 年国债：679 口" in it["msg"] and "先卖核心 ETF 1545 纳斯达克 100：" in it["msg"]
    b = _disk(r)
    assert not MO.corefix_pending(b, r.tag, T) and not MO.now_due(r.tag, b, T + dt.timedelta(minutes=11))   # 调完：不再叫
    seen = list(r.ux.orders)
    _morning(r)                                                               # 第二天早上：对账 + 决策
    assert not [o for o in seen + list(r.ux.orders) if o.status == "REJECTED"] and not r.ux.blocked
    assert int(r.eng.st.core_units["1482.T"]) == 679 and "1482.T" not in r.eng.st.core_plan   # 已经是固定口数：决策不再动它


def test_tachibana_replay_same_ledger_on_the_sim_exchange():
    """立花（模拟交易所）同一份账本：09:05 / 09:20 的开盘后补单没跑（Mac 睡着），10:30 写固定 679 口 → 同一条路、同一个闸门：
    旧买单被取代，卖 1545（现价 −0.5% 限价）、买 1482（限价 min(现价 +0.5%, 收盘 ×1.02)）。"""
    r = _tachi2()
    for _ in range(9):
        _tday(r)
    r.exch.cash = r.eng.st.cash_jpy = 191.68                                 # 与 10/15 早上的模拟账户一样少
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=678)
    _tday(r)
    sell, buy = _one(r, "SELL", "1545.T"), _one(r, "BUY", "1482.T")
    assert sell.status == "SENT" and buy.status == "DEFERRED" and buy.qty == 678 and buy.fund_src == [sell.cid]
    r.exch.orders[sell.broker_id]["status"] = "7"                           # 卖单在立花网站上撤了（执行器之外）
    sell.status = "CANCELLED"
    r.exch.open(r.k)
    T = _at(r, 10, 30)
    w = _w(r.tag, "M-fix-679", kind="corefix", ticker="1482.T", units=679)
    b = _disk(r)
    assert MO.now_due(r.tag, b, T) and MO.wait_text(w, T, b, r.tag) == "等下单：马上（盘中）按现价下单"
    r.now["t"] = T
    res = r.ux.now_phase(_quote(PXQ))
    assert res["placed"] == 1 and buy.status == "SKIPPED" and buy.note == f"{SKIP_NOTE}（10:30）" and not buy.broker_id
    fs, fb = _now_orders(r, "fix_fund"), _now_orders(r, "core_fix")
    assert [(o.ticker, o.side) for o in fs] == [("1545.T", "SELL")] and fs[0].status in ACCEPTED
    assert [(o.ticker, o.side, o.qty) for o in fb] == [("1482.T", "BUY", 679)] and fb[0].status in ACCEPTED
    lims = [r.exch.orders[o.broker_id]["lim"] for o in fs + fb]               # 交易所收到的限价：卖 现价 −0.5%、买 min(现价 +0.5%, 收盘 ×1.02)
    assert lims == [pytest.approx(697.0), pytest.approx(1005.0)]
    assert r.exch.pos.get("1482.T") == 679                                   # 交易所里成交了（按开盘价撮合）
    assert r.ux.book["core_rule"]["fix_applied"]["1482.T"] == 679
    assert not MO.now_due(r.tag, _disk(r), T + dt.timedelta(minutes=11))


def test_no_manual_instruction_means_no_intraday_core_move_and_old_books_are_seeded():
    """没有新的手动指令：决策照固定口数排过单（fix_applied = 固定口数）→ 盘中什么都不做（规则的决策不变）；
    旧账本没有 fix_applied → 启动时按现在的固定口数补上（不追溯、不在盘中重新调）。"""
    r = _paper2()
    sell, buy = _fixed_case(r)
    assert r.ux.book["core_rule"]["fix_applied"] == {"1482.T": 678}
    b = _disk(r)
    T = _at(r, 10, 30)
    assert not MO.corefix_pending(b, r.tag, T) and not MO.now_due(r.tag, b, T)
    n0 = len(r.ux.orders)
    r.now["t"] = T
    res = r.ux.now_phase(_quote(PXQ))
    assert res == {"placed": 0, "later": 0, "rejected": 0, "retry": 0, "items": []} and len(r.ux.orders) == n0
    assert sell.status == "SENT" and buy.status == "DEFERRED"
    p = paths.state_dir() / "live_unified_paper.json"
    old = json.loads(p.read_text(encoding="utf-8"))
    old["core_rule"].pop("fix_applied")
    assert not MO.corefix_pending(old, r.tag, T)                              # 面板：旧账本当成已经照现在的固定口数排过
    p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    ux = UnifiedExecutor(r.eng, r.b, p, paper=True, check_clock=False, clock=lambda: r.now["t"], manual_tag=r.tag)
    assert ux.book["core_rule"]["fix_applied"] == {"1482.T": 678}


# ══════════════════════════ 种类 × 时刻 × 账本：面板的触发、执行器下单、说明一致 ══════════════════════════
def _mk(book: str, n: int = 30):
    """A.T（第 8 根出买入信号 → 规则拿着 200 股）、B.T（没拿）、核心 ETF 1545（规则拿）/ 1482（规则不拿）；模拟账户或立花（模拟交易所）。"""
    a, b = _frame([1000.0] * n, entry=(8,)), _frame([1500.0] * n)
    c1, c2 = _frame([700.0] * n), _frame([1000.0] * n)
    c1["entry"] = c2["entry"] = False
    idx = c1.index
    bear = {"US": pd.Series(False, index=idx), "BR:BD": pd.Series(True, index=idx)}
    eng = UnifiedEngine({"A.T": a, "B.T": b, "1545.T": c1, "1482.T": c2}, CFG2, {"JP": P, "US": P}, EX, CC, bear=bear)
    exch = None
    if book == "paper":
        br = _MemPaper(state_file=paths.state_dir() / "paper_paper.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"],
                       market="JP")
    else:
        exch = SimExchange(eng, cash=eng.st.cash_jpy)
        br = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0,
                             max_order_value=10_000_000)
    now = {"t": None}
    ux = UnifiedExecutor(eng, br, paths.state_dir() / f"live_unified_{book}.json", paper=book == "paper", check_clock=False,
                         clock=lambda: now["t"], manual_tag=book)
    r = SimpleNamespace(eng=eng, exch=exch, b=br, ux=ux, now=now, k=int(eng.gidx.searchsorted(idx[5])), tag=book)
    eng.prime(r.k)
    return r


def _d0(r) -> dt.date:                                   # 成交日（上一次决策之后的那个交易日 = 今天）
    return r.eng.gidx[r.k].date()


def _at0(r, hh: int, mm: int, days: int = 0) -> dt.datetime:
    return dt.datetime.combine(_d0(r) + dt.timedelta(days=days), dt.time(hh, mm), tzinfo=JST)


def _open_day(r) -> None:
    """立花：成交日开盘（模拟交易所撮合寄付）+ 09:05 的开盘后补单；模拟账户：寄付单第二天早上撮合，这里什么都不做。"""
    if r.exch is not None and not (r.exch.phase == "open" and r.exch.k == r.k):
        r.exch.open(r.k)
        r.now["t"] = _at0(r, 9, 5)
        r.ux.open_phase()


def _close_day(r) -> None:
    if r.exch is not None:
        _open_day(r)
        r.exch.close_day()
        r.exch.set_day(r.k + 1)


def _decide(r) -> None:                                  # 下一交易日 07:40 的早上运行（模拟账户：先按开盘撮合上一次的单）
    r.now["t"] = dt.datetime.combine(next_trading_day(_d0(r)), dt.time(7, 40), tzinfo=JST)
    r.ux.morning([r.k])
    r.k += 1
    assert not r.ux.blocked


def _base(book: str):
    """成交日是星期五（2026-01-23）：A.T 200 股、1545 拿着、1482 没拿；下一次决策是星期一 01/26 07:40。"""
    r = _mk(book)
    for _ in range(9):
        _close_day(r)
        _decide(r)
    assert _d0(r) == dt.date(2026, 1, 23) and r.eng.st.pos["A.T"].shares == 200 and int(r.eng.st.core_units["1545.T"]) > 0
    return r


KINDS = {                                               # 指令 → 执行器要下的那一笔（票, 方向）
    "corefix": ({"kind": "corefix", "ticker": "1482.T", "units": 100}, ("1482.T", "BUY")),
    "core": ({"kind": "core", "pct": 50.0}, ("1545.T", "SELL")),
    "sell": ({"kind": "sell", "ticker": "A.T"}, ("A.T", "SELL")),
    "buy": ({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100}, ("B.T", "BUY")),
}
TIMES = {                                               # 写的时刻（成交日 星期五 01/23 起算的天数, 时, 分）→ 走哪条路
    "06:00": ((3, 6, 0), "decision"),                   # 星期一 06:00：那天早上的决策之前
    "07:50": ((0, 7, 50), "open"),
    "08:50": ((0, 8, 50), "open"),
    "08:57": ((0, 8, 57), "open"),                      # 寄付截止（08:55）之后
    "10:30": ((0, 10, 30), "now"),
    "12:00": ((0, 12, 0), "lunch"),
    "15:27": ((0, 15, 27), "next"),
    "15:40": ((0, 15, 40), "next"),
    "closed": ((1, 10, 0), "next"),                     # 星期六（休市日）
}
WANT_TXT = {                                            # 写给你的「什么时候」（MO.wait_text）
    "corefix": {"now": "马上（盘中）按现价下单", "open": "今天 09:00 开盘后马上（按现价限价，不是寄付）",
                "lunch": "12:30 后场开盘后马上（按现价限价，不是寄付）", "next": "01/26 07:40 的决策 → 01/26 09:00 开盘",
                "decision": "今天早上的决策（07:40）读到 → 今天 09:00 开盘（寄付）"},
    "sell": {"now": "马上（盘中）", "open": "今天 09:00 开盘", "lunch": "12:30 后场开盘", "next": "01/26 开盘", "decision": "今天 09:00 开盘"},
}
WANT_TXT["buy"] = WANT_TXT["sell"]
WANT_TXT["core"] = {k: f"读到就生效，核心 ETF {v}照新比例调" for k, v in WANT_TXT["sell"].items()}


def _run_now(r, T: dt.datetime, t: str, side: str, tries: int = 3) -> list:
    """面板的触发（now_due）→ 执行器 --phase now；没下成（例：立花凑钱的卖单还没成交）→ 面板 10 分钟后再叫。"""
    for _ in range(tries):
        assert MO.now_due(r.tag, _disk(r), T), f"面板 {T:%H:%M} 应该叫执行器"
        r.now["t"] = T
        r.ux.now_phase(_quote(PXQ))
        got = [o for o in _now_orders(r) if o.ticker == t and o.side == side and o.status in ACCEPTED]
        if got:
            return got
        T += dt.timedelta(minutes=MO.RETRY_S // 60)
    raise AssertionError(f"执行器 {T:%H:%M} 前没有下 {side} {t}：{r.ux.book['manual'].get('items')}")


def _decided(r, t: str, side: str) -> list:
    """当前决策里（不是盘中的）这只这个方向、还会动作的单。"""
    d = r.ux.book["state"]["last_date"]
    return [o for o in r.ux.orders if o.decided_on == d and o.phase != "now" and o.ticker == t and o.side == side
            and o.status not in ("SKIPPED", "REJECTED", "CANCELLED", "BLOCKED", "EXPIRED")]


@pytest.mark.parametrize("book", ["paper", "tachibana"])
@pytest.mark.parametrize("kind", list(KINDS))
@pytest.mark.parametrize("when", list(TIMES))
def test_trigger_executor_and_text_agree(book, kind, when):
    r = _base(book)
    (dd, hh, mm), path = TIMES[when]
    rec, (t, side) = KINDS[kind]
    T = _at0(r, hh, mm, dd)
    if path == "decision":                                # 星期一 06:00：星期五的交易日已经结束（立花：收盘）
        _close_day(r)
    elif T >= _at0(r, 9, 0):                              # 盘中 / 收盘后 / 休市日写的：今天已经开盘了
        _open_day(r)
    w = _w(r.tag, f"M-{kind}", **rec)
    b = _disk(r)
    txt = MO.wait_text(w, T, b, r.tag)
    want = WANT_TXT[kind][path] + ("（模拟账户当场成交）" if (kind, path, book) == ("corefix", "now", "paper") else "")
    if when == "08:57" and kind != "corefix":             # 寄付截止之后：开盘后由盘中的路按现价下（D7 / M19；2026-10-15）
        want = want.replace("今天 09:00 开盘", MO.OPEN_NOW_TXT)
    assert txt.split("：", 1)[1] == want, txt                            # ① 说明
    assert txt.startswith("等执行器读" if kind == "core" else "等下单")
    if path == "now":                                     # ② 面板马上叫 → ③ 执行器盘中按现价下
        assert not MO.due(r.tag, b, T)
        _run_now(r, T, t, side)
    elif path in ("open", "lunch"):
        assert not MO.now_due(r.tag, b, T)                # 现在不叫 --phase now
        if kind == "sell" and T.time() < MO.CUTOFF:       # 卖出（决策之后、寄付截止之前）：面板叫 --retry 加进今天的寄付单
            assert MO.due(r.tag, b, T)
            r.now["t"] = T
            r.ux.morning([])
            assert _decided(r, t, side) and not _now_orders(r)
            return
        assert not MO.due(r.tag, b, T)                    # 固定口数 / 比例 / 买入：不进寄付补单（不是寄付）
        T1 = _at0(r, 9, 0) if path == "open" else _at0(r, 12, 30)
        if r.exch is not None and path == "open":
            r.exch.open(r.k)                              # 09:00 开盘（09:05 的开盘后补单之前，面板已经叫了）
        got = _run_now(r, T1, t, side)                    # 开盘后第一次盘中运行：按现价限价
        assert all(o.phase == "now" for o in got)
    else:                                                 # 下一次决策 / 那天早上的决策
        assert not MO.now_due(r.tag, b, T)
        if not (kind == "sell" and path == "decision"):
            assert not MO.due(r.tag, b, T)
        if path == "next":
            _close_day(r)
        _decide(r)
        assert _d0(r) == dt.date(2026, 1, 26)              # 星期一 07:40 的决策 → 星期一 09:00 开盘（说明写的那天）
        assert _decided(r, t, side), f"{when} 写的 {kind}：那次决策应该下 {side} {t}"
        assert not _now_orders(r)
    if kind == "corefix":
        assert r.ux.book["core_rule"]["fix_applied"] == {"1482.T": 100}
        assert not MO.corefix_pending(_disk(r), r.tag, r.now["t"])


# ══════════════════════════ M14：核心 ETF 盘中买入的限价上限 ══════════════════════════
@pytest.mark.parametrize("book", ["paper", "tachibana"])
def test_m14_quote_at_close_x103_does_not_buy_then_buys_under_the_cap(book):
    r = _base(book)
    _open_day(r)
    T = _at0(r, 10, 30)
    _w(r.tag, "M-fix", kind="corefix", ticker="1482.T", units=100)
    r.now["t"] = T
    res = r.ux.now_phase(_quote({**PXQ, "1482.T": 1030.0}))             # 现价 = 收盘 ×1.03
    assert res["retry"] == 1 and res["placed"] == 0 and not _now_orders(r, "core_fix") and not _now_orders(r, "fix_fund")
    it = r.ux.book["manual"]["items"]["M-fix"]
    assert "现价 ¥1,030 高于" in it["msg"] and "收盘 ¥1,000 ×1.02（¥1,020）：这次不买" in it["msg"] and "10 分钟后再试" in it["msg"]
    b = _disk(r)
    assert MO.corefix_pending(b, r.tag, T) == {"1482.T": 100}
    assert not MO.now_due(r.tag, b, T + dt.timedelta(minutes=9)) and MO.now_due(r.tag, b, T + dt.timedelta(minutes=10))   # RETRY_S 退避
    r.now["t"] = T + dt.timedelta(minutes=10)
    r.ux.now_phase(_quote({**PXQ, "1482.T": 1018.0}))                   # 回到上限之内：限价 = min(1018 ×1.005, 1,020) = 1,020
    fb = _now_orders(r, "core_fix")
    assert [(o.side, o.qty) for o in fb] == [("BUY", 100)] and fb[0].limit == pytest.approx(1020.0)
    assert r.ux.book["core_rule"]["fix_applied"] == {"1482.T": 100}


def test_m14_ratio_buy_intraday_is_capped_too():
    """闲置资金比例的盘中买入（停买 0% → 恢复 100%）同一个上限：现价 > 收盘 ×1.02 → 这次不买、一会儿再试。"""
    r = _base("paper")
    _w(r.tag, "M-pause", kind="core", pct=0.0)
    _close_day(r)
    _decide(r)                                                          # 决策：卖出全部 1545
    _decide(r)
    assert int(r.eng.st.core_units.get("1545.T", 0)) == 0
    _w(r.tag, "M-resume", kind="core", pct=100.0)
    r.now["t"] = _at0(r, 10, 30)
    res = r.ux.now_phase(_quote({**PXQ, "1545.T": 721.0}))              # 700 ×1.03
    assert res["placed"] == 0 and not [o for o in _now_orders(r) if o.ticker == "1545.T" and o.side == "BUY"]
    assert "收盘 ¥700 ×1.02（¥714）：这次不买" in json.dumps(r.ux.book.get("events") or [], ensure_ascii=False)


# ══════════════════════════ 不叠单 / 取代 / 差金決済 / HALT ══════════════════════════
def test_tachibana_live_order_of_the_same_etf_waits_then_the_rest_is_superseded():
    """立花：决策排了买 1482 5 口（寄付，挂在交易所）+ 余下 673 口开盘后；开盘前写固定 600 口 → 09:00 不叠单（先等那 5 口成交）；
    寄り付いた之后再叫：按成交后的口数调（600 − 5 = 595 口），还没发出的 673 口被取代。"""
    r = _tachi2()
    sell, rest = _tfixed(r)
    first = _one(r, "BUY", "1482.T")
    assert first.status == "SENT" and first.qty == 5 and rest.status == "DEFERRED"
    T = _at(r, 8, 50)
    w = _w(r.tag, "M-fix-600", kind="corefix", ticker="1482.T", units=600)
    b = _disk(r)
    assert MO.wait_text(w, T, b, r.tag) == "等下单：今天 09:00 开盘后马上（按现价限价，不是寄付）" and not MO.due(r.tag, b, T)
    T1 = _at(r, 9, 0)
    r.exch.phase = "open"                                               # 09:00：特別気配、还没寄り付いた（寄付单还挂着）
    r.exch.k = r.exch.day_k = r.k
    assert MO.now_due(r.tag, b, T1)
    r.now["t"] = T1
    res = r.ux.now_phase(_quote(PXQ))
    assert res["retry"] == 1 and not _now_orders(r)
    msg = r.ux.book["manual"]["items"]["M-fix-600"]["msg"]
    assert "先等今天还挂着的" in msg and "买 1482 对冲版美国 7〜10 年国债：5 口" in msg and "再按成交后的口数调" in msg
    assert rest.status == "DEFERRED"                                    # 一会儿再试：还没发出的先不动
    r.exch.open(r.k)                                                    # 09:0x 寄り付いた：寄付单成交
    r.now["t"] = T1 + dt.timedelta(minutes=10)
    r.ux.now_phase(_quote(PXQ))
    assert rest.status == "SKIPPED" and rest.note.startswith(SKIP_NOTE)
    fb = _now_orders(r, "core_fix")
    assert [(o.side, o.qty) for o in fb] == [("BUY", 595)] and fb[0].status in ACCEPTED
    assert r.ux.book["core_rule"]["fix_applied"] == {"1482.T": 600}


def test_same_day_round_trip_defers_and_a_new_value_tries_again():
    """模拟账户：盘中固定 100 口（买）→ 再改 0 口（卖）→ 再改 50 口：同一只当天已经买过也卖过（差金決済）→ 下一次决策；
    面板不再为同一个值叫（fix_defer）；改成别的口数 → 又叫；第二天早上的决策照它调。"""
    r = _base("paper")
    for i, (u, side) in enumerate(((100, "BUY"), (0, "SELL"))):
        T = _at0(r, 10, 0 + 10 * i)
        _w(r.tag, f"M-fix-{u}", kind="corefix", ticker="1482.T", units=u)
        r.now["t"] = T
        r.ux.now_phase(_quote(PXQ))
        assert _now_orders(r, "core_fix")[-1].side == side and _now_orders(r, "core_fix")[-1].status == "FILLED"
    T = _at0(r, 13, 0)
    _w(r.tag, "M-fix-50", kind="corefix", ticker="1482.T", units=50)
    r.now["t"] = T
    res = r.ux.now_phase(_quote(PXQ))
    assert res["later"] == 1 and len(_now_orders(r, "core_fix")) == 2
    msg = r.ux.book["manual"]["items"]["M-fix-50"]["msg"]
    assert "今天已经买过也卖过（差金決済" in msg and "下一次决策照它调（01/26 07:40 的决策 → 01/26 09:00 开盘）" in msg
    b = _disk(r)
    assert b["core_rule"]["fix_defer"]["1482.T"] == {"day": "2026-01-23", "units": 50}
    assert not MO.now_due(r.tag, b, T + dt.timedelta(hours=1))
    _w(r.tag, "M-fix-60", kind="corefix", ticker="1482.T", units=60)    # 新的值 → 又叫（执行器再判断）
    assert MO.now_due(r.tag, _disk(r), T + dt.timedelta(hours=1))
    _decide(r)
    assert _decided(r, "1482.T", "BUY")[0].qty == 60 and r.ux.book["core_rule"]["fix_applied"] == {"1482.T": 60}


def test_halt_receipt_and_executor_wait_for_corefix():
    """D7：HALT 中写的固定口数 → 说明写 HALT_CORE_MSG（解除后照它买卖 ETF：盘中解除马上按现价下；复核 UI F1）；面板不叫、执行器不下（读到就生效）。"""
    from test_corefix_confirm import AT1012, _state
    r = _base("paper")
    _w(r.tag, "M-fix", kind="corefix", ticker="1482.T", units=100)
    T = _at0(r, 10, 30)
    b = _disk(r)
    paths.halt_file().write_text("测试", encoding="utf-8")
    assert MO.wait_text({"kind": "corefix", "ticker": "1482.T", "units": 100}, T, b, r.tag).startswith("等下单：马上")
    assert not MO.now_due(r.tag, b, T)                                   # HALT：面板不叫
    r.now["t"] = T
    res = r.ux.now_phase(_quote(PXQ))                                   # 执行器被叫到也不下（读到就生效）
    assert res["placed"] == 0 and not _now_orders(r)
    assert [x["msg"] for x in res["items"]] == [f"1482 对冲版美国 7〜10 年国债 固定 100 口：{MO.HALT_CORE_MSG}"]
    assert r.ux.book["manual"]["core_fix"] == {"1482.T": 100} and MO.corefix_pending(r.ux.book, r.tag, T) == {"1482.T": 100}
    _state()                                                            # 面板写的说明（模拟账户 10/15 的账本）
    body = {"book": "paper", "kind": "corefix", "ticker": "1482", "units": 678}
    _ok, _m, rec = panel.submit(body, AT1012, fetch=lambda ts: {})
    ok, msg, _w2 = panel.submit({**body, "confirm": rec["confirm"]["token"]}, AT1012, fetch=lambda ts: {})
    assert ok and msg.endswith(f"；★ {MO.HALT_CORE_MSG}（指令 {_w2['id']}）")
    paths.halt_file().unlink()


# ══════════════════════════ 复核（2026-10-16） ══════════════════════════
def test_corefix_without_core_rule_waits_for_the_first_decision():
    """promise F4：执行器还没做过核心 ETF 的决策（没有 core_rule）→ 盘中的路不排（corefix_pending 是 {}）→ 面板不叫执行器、
    文字写「第一次决策时照它排单」（以前说「马上」，实际要等第一次决策）；有了 core_rule → 照旧马上。"""
    now = dt.datetime(2026, 10, 15, 10, 30, tzinfo=JST)                       # 星期四 盘中
    book = {"state": {"last_date": "2026-10-14"}, "manual": {"items": {}}}
    MO.append("paper", {"kind": "corefix", "ticker": "1482.T", "units": 100}, clock=lambda: now)
    assert MO.corefix_pending(book, "paper", now) == {} and not MO.now_due("paper", book, now)
    f = MO.corefix_fill(now, book, "paper")
    assert f["mode"] == "decision" and f["day"] == dt.date(2026, 10, 16) and not f["intraday"]
    assert f["text"] == "10/16 07:40 的决策 → 10/16 09:00 开盘（执行器还没做过核心 ETF 的决策：第一次决策时照它排单）"
    assert MO.corefix_fill(dt.datetime(2026, 10, 15, 7, 0, tzinfo=JST), {}, "paper")["day"] == dt.date(2026, 10, 15)   # 还没跑过：今天 07:40
    book["core_rule"] = {"lot": {"1482.T": 1}}
    assert MO.now_due("paper", book, now) and MO.corefix_fill(now, book, "paper")["mode"] == "now"


def test_cancel_hint_for_a_fixed_etf_not_yet_applied_says_when_it_is_ordered():
    """UI F2：固定口数还没照它调（D1：今天开盘后 / 盘中就下）→ 撤单提示 / 交易页写「什么时候照它下单」，不是「下一次决策还会再排」。"""
    from test_fund_src import _dict_book
    from qbreak import live_ops as LO
    from qbreak.live_unified import ExecOrder
    book = _dict_book()
    book["manual"]["core_fix"] = {"1482.T": 679}
    book["core_rule"]["fix_applied"] = {"1482.T": 678}
    o = ExecOrder.from_dict(book["orders"][1])
    now = dt.datetime(2026, 10, 15, 10, 30, tzinfo=JST)
    h = LO.cancel_hint(o, book, now, "tachibana")
    assert "1482 对冲版美国 7〜10 年国债 手动固定 679 口还没照它调：马上（盘中）按现价下单（撤这笔单不会取消固定口数" in h
    assert "下一次决策还会再排" not in h
    pend, when = LO.fix_pending_when(book, now, "tachibana")
    assert pend == {"1482.T": 679} and when == "马上（盘中）按现价下单"


def test_next_decision_text_has_the_date():
    """UI F5：「下一次决策（MM/DD 07:40）起生效」：周五收盘后 → 下周一；早上 07:40 之前 → 今天。"""
    assert MO.next_decision(dt.datetime(2026, 10, 16, 16, 0, tzinfo=JST)) == "下一次决策（10/19 07:40）起生效"
    assert MO.next_decision(dt.datetime(2026, 10, 15, 7, 0, tzinfo=JST)) == "下一次决策（10/15 07:40）起生效"


def test_fix_status_text_waiting_until_applied():
    """读进执行器、还没照它排单的固定口数：状态写「生效中 · 还没照它调」，不写「完成」（2026-10-16 复核：10-15 的 679 口显示「完成」）。"""
    old = {"kind": "corefix", "ticker": "1482.T", "units": 678, "id": "M1", "at": "2026-10-14T19:21:00+09:00", "status": "done"}
    new = {"kind": "corefix", "ticker": "1482.T", "units": 679, "id": "M2", "at": "2026-10-15T08:48:29+09:00", "status": "done"}
    items = [new, old]
    book = {"core_rule": {"decided_on": "2026-10-14", "fix_applied": {"1482.T": 678}}, "manual": {"core_fix": {"1482.T": 679}, "items": {}}}
    assert MO.fix_status_text(new, items, book) == MO.FIX_WAIT
    assert MO.fix_status_text(old, items, book) is None                       # 旧的那条照旧「完成」
    sm = {"items": items}
    ln = MO.lines(sm, today="2026-10-15", book=book)
    assert any(MO.FIX_WAIT in x and "679" in x for x in ln) and not any(MO.FIX_WAIT in x and "678" in x for x in ln)
    assert not any(MO.FIX_WAIT in x for x in MO.lines(sm, today="2026-10-15"))   # 没给账本（日志 / 通知）：照旧
    book["core_rule"]["fix_applied"] = {"1482.T": 679}                        # 照它排了单 → 完成
    assert MO.fix_status_text(new, items, book) is None
    clr = {"kind": "corefix", "ticker": "1482.T", "clear": True, "id": "M3", "at": "2026-10-15T10:00:00+09:00", "status": "done"}
    book["core_rule"]["fix_applied"] = {"1482.T": 678}
    assert MO.fix_status_text(new, items + [clr], book) is None               # 后面有一条恢复按规则：这条不是现在的
