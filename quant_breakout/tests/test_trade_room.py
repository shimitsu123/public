"""「今天还能买几次 / 卖几次」（D6；2026-10-15 用户要求 3；qbreak/trade_room.py）：
① 交易所时段（15:25 起 / 收盘后 / 休市日今天 0 次）② 差金決済（立花 e支店 2026-10-15 核对：例 1 买→卖再买要另有前受金、例 2 卖→买再卖、
例 3 换别的票不受限）③ 执行器的规则（同一只当天只下一笔、名额、不买回、新仓倍数 0、现价上限）④ 钱（cash_now 同口径 + 凑钱的核心 ETF）
⑤ 闸门（HALT / 没解锁 / 状态不明 / 持仓不一致 / 早上没跑完）；面板 /api/trade_room（本机 + 手机）、交易页的卡片、持仓的小标记、
页面脚本 room.js（node）、manual list 的一段。"""
import datetime as dt
import json
import re
import shutil
import subprocess
from html import unescape

import pytest

from qbreak import calendar_jp as CJ
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak import panel_phone as PP
from qbreak import trade_room as TR
from qbreak.calendar_jp import JST
from test_panel import _book1015, _js_fn
from test_panel import server  # noqa: F401  （fixture）
from test_panel import _req as _lreq
from test_panel_phone import servers  # noqa: F401  （fixture）
from test_panel_phone import _phone

D = "2026-10-14"                                                         # 决策日（K 线）→ 成交日 2026-10-15（四）
AT = dt.datetime(2026, 10, 15, 10, 30, tzinfo=JST)                       # 盘中（前場）


def _at(h: int, m: int, day: int = 15) -> dt.datetime:
    return dt.datetime(2026, 10, day, h, m, tzinfo=JST)


def _bk(pos=None, cores=None, cash=500_000.0, orders=None, manual=None, last=D, **kw) -> dict:
    """账本：默认拿着 7203 200 股（收盘 2,600）+ 核心 1545 100 口（收盘 2,400，一手 10 口）、现金 50 万、总权益 100 万。"""
    st = {"last_date": last, "cash_jpy": cash, "history": [[last, 1_000_000.0, cash, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "last_close": 2600.0}} if pos is None else pos,
          "pending_exit": {}, "core_units": {"1545.T": 100} if cores is None else cores}
    b = {"state": st, "orders": orders or [], "core_rule": {"lot": {"1545.T": 10}, "px": {"1545.T": 2400.0}},
         "manual": manual or {"items": {}}}
    b.update(kw)
    return b


def _o(t, side, status="FILLED", qty=100, px=2600.0, at="09:30", kind="stock", phase="now", filled=None) -> dict:
    """当前决策（D）的一笔执行器的单。"""
    f = qty if filled is None and status == "FILLED" else int(filled or 0)
    return {"cid": f"U{D}-{side}-{t}-{at.replace(':', '')}", "ticker": t, "side": side, "kind": kind, "qty": qty, "decided_on": D,
            "limit": px, "ref_px": px, "phase": phase, "status": status, "sent_qty": qty, "filled_qty": f,
            "filled_px": px if f else 0.0, "sent_at": f"2026-10-15T{at}:00+09:00"}


def _row(t, close, block=None, warn=(), em=1.0, lot=100) -> dict:
    """执行器汇总里「建议的股票」的一行（suggest.build 的样子）。"""
    return {"ticker": t, "close": close, "status": "watch",
            "buy": {"block": block, "block_kind": "gate" if block else None, "warn": list(warn), "em": em, "lot": lot, "px": close,
                    "limit": round(close * 1.03)}}


def _room(b, now=AT, tag="paper", **kw):
    kw.setdefault("halt", False)
    kw.setdefault("arm", "file")
    kw.setdefault("waiting", [])
    return TR.room(tag, b, now, **kw)


# ───────────────────────── ② 差金決済（纯函数的真值表） ─────────────────────────
@pytest.mark.parametrize("orders,held0,seq,buy_rule,sell_rule,free", [
    ([], 200, "", None, None, None),                                                         # 今天没做过
    ([_o("7203.T", "BUY")], 0, "B", None, None, None),                                       # 只买：之后卖（日計り）不受限
    ([_o("7203.T", "BUY", at="09:10"), _o("7203.T", "SELL", at="09:40")], 0, "BS", 1, None, None),   # 例 1：买 → 卖 → 再买要前受金
    ([_o("7203.T", "SELL", at="09:40"), _o("7203.T", "BUY", at="09:10")], 0, "BS", 1, None, None),   # 按发出的先后排（不是列表的顺序）
    ([_o("7203.T", "SELL", at="09:10"), _o("7203.T", "BUY", at="09:40")], 200, "SB", None, 2, 100),  # 例 2：卖 100 → 买 → 再卖不另付钱最多 100
    ([_o("7203.T", "SELL", qty=200, at="09:10"), _o("7203.T", "BUY", at="09:40")], 200, "SB", None, 2, 0),   # 开盘前的已经卖完
    ([_o("7203.T", "SELL", status="SENT", qty=200, at="09:10", filled=0), _o("7203.T", "BUY", at="09:40")], 200, "SB", None, 2, 0),  # 在途的卖单按全数算
    ([_o("7203.T", "BUY", status="CANCELLED", filled=0, at="09:10"), _o("7203.T", "SELL", at="09:40")], 200, "S", None, None, None),  # 撤了一股没成交的不算
    ([_o("7203.T", "BUY", at="09:10"), _o("7203.T", "SELL", at="09:20"), _o("7203.T", "BUY", at="09:30")], 0, "BSB", 1, None, None),
])
def test_sakin_truth_table(orders, held0, seq, buy_rule, sell_rule, free):
    sk = TR.sakin(orders, held0)
    assert sk["seq"] == seq and sk["buy"]["rule"] == buy_rule and sk["sell"]["rule"] == sell_rule and sk["sell"]["free"] == free
    if buy_rule == 1:
        assert "差金決済（例 1）" in sk["buy"]["why"] and "另有前受金" in sk["buy"]["why"] and sk["sold_jpy"] > 0
    if sell_rule == 2:
        assert "差金決済（例 2）" in sk["sell"]["why"] and f"不另付钱最多再卖 {free:,} 股" in sk["sell"]["why"]


def test_module_docstring_cites_the_broker_page():
    """规则的出处写在模块里（立花 e支店「差金決済取引・日計り取引」，2026-10-15 核对）；卡片的说明一句。"""
    assert TR.SAKIN_URL == "https://www.e-shiten.jp/TorihikiRule/rule/sakin_hibakari.html"
    assert TR.SAKIN_URL in TR.__doc__ and "2026-10-15" in TR.__doc__ and "例 3" in TR.__doc__
    assert TR.NOTE == "券商不限次数；限制来自差金決済与执行器规则"


def test_sakin_in_room_example_1_and_3():
    """例 1：7203 今天买 → 卖过 → 再买的说明写「另有前受金」（执行器同一只当天只下一笔也先挡住）；例 3：别的票（6758）不受影响。"""
    b = _bk(pos={}, orders=[_o("7203.T", "BUY", at="09:10"), _o("7203.T", "SELL", at="09:40")])
    rm = _room(b, sm={"suggest": {"rows": [_row("6758.T", 3000.0)]}})
    r = rm["per_ticker"]["7203.T"]
    assert r["sakin"]["buy"]["rule"] == 1 and any("差金決済（例 1）" in w for w in r["buy"]["why"])
    assert r["buy"]["n"] == 0 and r["buy"]["next"] == "下一笔 10/16 开盘"
    s = rm["per_ticker"]["6758.T"]
    assert s["buy"]["n"] == 1 and not any("差金決済" in w for w in s["buy"]["why"])
    assert "换别的股票不受差金決済限制（例 3）" in rm["overall"]["trades_left"]["why"]


# ───────────────────────── ① 时段 ─────────────────────────
@pytest.mark.parametrize("now,short,phase", [
    (_at(15, 27), "收盘竞价", "closing"),
    (_at(15, 40), "已收盘", "after"),
    (_at(10, 0, day=17), "休市日", "holiday"),                             # 2026-10-17（六）
])
def test_after_close_closing_and_holiday_are_zero(now, short, phase):
    rm = _room(_bk(), now)
    assert rm["market"]["phase"] == phase and not rm["market"]["today"]
    assert rm["headline"] == "今天还能：买 0 次 · 卖 0 次 · 共 0 次"
    for t in ("7203.T", "1545.T"):
        r = rm["per_ticker"][t]
        assert r["buy"]["n"] == r["sell"]["n"] == 0 and r["sell"]["short"] == short and r["buy"]["short"] == short
        assert r["chip"] == f"今天还能卖 ✗（{short}） / 买 ✗（{short}）"
    nxt = "10/16" if phase != "holiday" else "10/19"
    assert rm["market"]["next_text"] == f"{nxt} 09:00 开盘" and f"今天 0 次（下一个能交易的时刻 {nxt} 09:00 开盘）" in rm["overall"]["sell_left"]["why"]


def test_session_counts_and_one_order_per_ticker():
    """盘中、什么都没做过：7203 能卖 200 股 / 能加 100 股（最多到总权益 100 万：300 股 − 200）、1545 能卖 / 能加（不拿自己凑钱）；
    没有候选 → 新股按名额数（空 3 个）；同一只既能买又能卖 → 共 只算一次。"""
    rm = _room(_bk())
    s, c = rm["per_ticker"]["7203.T"], rm["per_ticker"]["1545.T"]
    assert s["sell"]["n"] == 1 and s["sell"]["max_qty"] == 200 and s["buy"]["n"] == 1 and s["buy"]["max_qty"] == 100
    assert s["chip"] == "今天还能卖 ✓ / 买 ✓（二选一：同一只当天只下一笔）" and s["label"] == "7203 トヨタ自動車"
    assert c["sell"]["max_qty"] == 100 and c["buy"]["n"] == 1 and c["buy"]["max_qty"] > 0 and c["buy"]["max_qty"] % 10 == 0
    assert "「固定口数…」" in c["buy"]["via"] and "核心 ETF 不能用个股的「买入」" in c["buy"]["via"]
    ov = rm["overall"]
    assert ov["buy_left"]["new"] == 3 and ov["buy_left"]["adds"] == 2 and ov["sell_left"]["n"] == 2
    assert rm["headline"] == "今天还能：买 5 次 · 卖 2 次 · 共 5 次"
    assert "既能买又能卖的 2 只（同一只当天执行器只下一笔：只算一次）" in ov["trades_left"]["why"]
    assert "没有候选的价格" in ov["buy_left"]["why"] and "钱是共用的" in ov["buy_left"]["why"]
    assert rm["market"]["line"] == "盘中（前場）：现在写的买卖 → 马上（盘中）下单"


def test_busy_ticker_waits_for_next_open():
    """7203 今天盘中已经卖过一笔（成交）→ 今天卖 / 买都 0 次：「下一笔 10/16 开盘」；别的票照常。"""
    rm = _room(_bk(orders=[_o("7203.T", "SELL", qty=100)]))
    r = rm["per_ticker"]["7203.T"]
    for side in ("sell", "buy"):
        assert r[side]["n"] == 0 and r[side]["short"] == "今天已有单" and r[side]["next"] == "下一笔 10/16 开盘"
        assert any("同一只当天只下一笔" in w for w in r[side]["why"])
    assert rm["per_ticker"]["1545.T"]["sell"]["n"] == 1
    assert rm["overall"]["sell_left"]["n"] == 1 and "7203 トヨタ自動車（今天已有单）" in rm["overall"]["sell_left"]["why"]
    # 撤了、一股没成交的单不算（D4：撤单之后当天还能写新的）
    rm = _room(_bk(orders=[_o("7203.T", "SELL", status="CANCELLED", filled=0)]))
    assert rm["per_ticker"]["7203.T"]["sell"]["n"] == 1


def test_slots_full_blocks_new_stocks():
    """个股名额 4 只都占着 → 候选不能买（名额已满）；新股 0。"""
    pos = {t: {"shares": 100, "entry_px": 1000.0, "last_close": 1000.0} for t in ("7203.T", "6758.T", "6501.T", "9984.T")}
    rm = _room(_bk(pos=pos, cash=2_000_000.0), sm={"suggest": {"rows": [_row("8035.T", 2000.0)]}})
    r = rm["per_ticker"]["8035.T"]
    assert r["cand"] and r["buy"]["n"] == 0 and r["buy"]["short"] == "名额已满"
    assert rm["overall"]["buy_left"]["new"] == 0 and rm["cands"] == {"n": 1, "ok": 0, "groups": {"名额已满": 1}}


def test_cash_lots_truth_table():
    """④ 钱：一个单元 = 价格 ×(1 + 0.5%) + 手续费；正好够 1 个 / 差 1 円 0 个。"""
    c = TR.lot_cost(2600.0, 100)
    assert TR.lots(c, 2600.0, 100) == 1 and TR.lots(c - 1, 2600.0, 100) == 0
    assert TR.lots(0, 2600.0, 100) == 0 and TR.lots(1e6, 0, 100) == 0
    assert TR.lots(2 * c + 1000, 2600.0, 100) == 2


def test_money_counts_cash_and_fundable_core_shared():
    """候选 3 只（一手 ¥20 万 / ¥30 万 / ¥50 万）、现金 ¥70 万 + 能卖来凑钱的 1545 约 ¥23.7 万：每只单独都够，
    钱是共用的 → 新股按便宜的先数：2 只（只是数，不是建议）。现金 0 → 卖核心凑钱；核心今天有单 → 不能凑 → 钱不够。"""
    sm = {"suggest": {"rows": [_row("6758.T", 3000.0), _row("6501.T", 2000.0), _row("8035.T", 5000.0)]}}
    rm = _room(_bk(pos={}, cash=700_000.0), sm=sm)
    assert all(rm["per_ticker"][t]["buy"]["n"] == 1 for t in ("6758.T", "6501.T", "8035.T"))
    assert rm["overall"]["buy_left"]["new"] == 2 and rm["cands"]["ok"] == 3
    assert rm["money"]["cash"] == round(700_000 * 0.99) and rm["money"]["fund_from"] == ["1545 纳斯达克 100"]
    rm = _room(_bk(pos={}, cash=0.0), sm=sm)
    r = rm["per_ticker"]["6501.T"]
    assert r["buy"]["n"] == 1 and r["buy"]["max_qty"] == 100 and any("加上卖核心 ETF 凑钱最多 100 股" in w for w in r["buy"]["why"])
    assert rm["per_ticker"]["8035.T"]["buy"]["short"] == "钱不够"
    rm = _room(_bk(pos={}, cash=0.0, orders=[_o("1545.T", "SELL", qty=10, px=2400.0, kind="core")]), sm=sm)
    assert rm["per_ticker"]["6501.T"]["buy"]["short"] == "钱不够" and rm["money"]["fundable"] == 0


def test_cash_now_same_formula_as_executor():
    """cash_now：(余力 − 还没下的买单要占的（限价 × 股数 + 手续费）− 出金预留) × (1 − 1%)；开盘时一定下不成的买单不留钱。"""
    b = _bk(orders=[_o("6501.T", "BUY", status="DEFERRED", qty=100, px=3000.0, phase="open", filled=0)],
            flows=[{"date": "2026-10-14", "jpy": -100_000.0, "reserve": True}])
    m = TR.cash_now(b, "tachibana", AT)
    assert m["res"] == round(300_000 + MO.fee_jp(300_000)) and m["reserve"] == 100_000
    assert m["cash"] == pytest.approx((500_000 - 300_000 - MO.fee_jp(300_000) - 100_000) * 0.99)
    assert TR.cash_now(b, "paper", AT)["reserve"] == 0                     # 模拟账户没有出金预留
    poor = _bk(cash=192.0, orders=[_o("1482.T", "BUY", status="DEFERRED", qty=678, px=1503.0, kind="core", phase="open", filled=0)])
    assert TR.cash_now(poor, "paper", AT)["res"] == 0                       # 一定下不成（LO.unfunded_buys）：不留钱


@pytest.mark.parametrize("kw,short", [
    ({"halt": True}, "HALT"),
    ({"tag": "tachibana", "arm": "off"}, "没解锁"),
    ({"tag": "tachibana_dryrun"}, "只看"),
])
def test_gates_zero_everything(kw, short):
    rm = _room(_bk(), **kw)
    assert rm["headline"] == "今天还能：买 0 次 · 卖 0 次 · 共 0 次" and rm["gates"]
    assert all(r["sell"]["n"] == r["buy"]["n"] == 0 for r in rm["per_ticker"].values())
    assert short in rm["per_ticker"]["7203.T"]["chip"]


def test_unknown_order_mismatch_and_morning_gates():
    """状态不明的单 / 今天的持仓核对不一致 / 立花今天早上的运行没完成（08:55 之后）→ 全部 0；模拟账户没完成 → 只写一句（面板会补跑）。"""
    rm = _room(_bk(orders=[_o("6501.T", "BUY", status="ERROR", filled=0)]))
    assert rm["overall"]["trades_left"]["n"] == 0 and "有状态不明的单（6501 日立製作所：100 股）" in rm["gates"][0]
    rm = _room(_bk(broker_mismatch={"text": "7203.T 账本 200 股 / 券商 100 股", "date": "2026-10-15"}))
    assert rm["overall"]["trades_left"]["n"] == 0 and "7203 トヨタ自動車" in rm["gates"][0]
    rm = _room(_bk(broker_mismatch={"text": "x", "date": "2026-10-14"}))  # 昨天的不算
    assert rm["overall"]["trades_left"]["n"] > 0
    late = _bk(last="2026-10-13")
    rm = _room(late, _at(9, 10), tag="tachibana")
    assert rm["overall"]["trades_left"]["n"] == 0 and "立花不自动补跑" in rm["gates"][0]
    rm = _room(late, _at(9, 10))
    assert not rm["gates"] and rm["overall"]["sell_left"]["n"] == 2 and any("面板自动补跑" in w and "上次决策 2026-10-13" in w for w in rm["notes"])
    rm = _room(late, _at(6, 0))                                            # 07:40 之前：决策还没跑是正常的
    assert not rm["gates"] and any("07:40 的决策还没跑" in w for w in rm["notes"])


def test_sending_while_the_executor_runs_is_not_unknown():
    """执行器拿着运行锁时 SENDING = 正在发的单（与面板同一口径）→ 不是状态不明、不全部挡住，只写一句；运行结束还是 SENDING → 状态不明。"""
    b = _bk(orders=[_o("6501.T", "BUY", status="SENDING", filled=0)])
    rm = _room(b, running=True)
    assert not rm["gates"] and any("执行器正在运行（发送中：6501 日立製作所：100 股）" in w for w in rm["notes"])
    assert rm["per_ticker"]["6501.T"]["buy"]["short"] == "今天已有单" and rm["overall"]["sell_left"]["n"] == 2
    rm = _room(b, running=False)
    assert rm["overall"]["trades_left"]["n"] == 0 and "有状态不明的单（6501 日立製作所：100 股）" in rm["gates"][0]


def test_paused_is_a_note_not_zero():
    """面板盘中自动下单今天暂停：写新的指令就恢复 → 不算 0，只写一句。"""
    rm = _room(_bk(), paused="连续失败 3 次")
    assert rm["overall"]["sell_left"]["n"] == 2 and "面板盘中自动下单今天暂停（连续失败 3 次）" in rm["notes"][0]


def test_rule_gates_mult0_block_gap_and_core_limit():
    """③ 新仓倍数 0 → 加仓 / 新股都不行；手动卖出后不买回（到 10/20 → 最早 10/22）；盘中现价比收盘高 3% 以上 → 不买；
    核心 ETF 现价比收盘高 2% 以上 → 只写一句（盘中买单限价 ≤ 收盘 ×1.02，一会儿再试）。"""
    sm = {"new_pos": {"markets": {"JP": {"mult": 0.0}}}, "suggest": {"rows": [_row("6758.T", 3000.0, em=0.0, warn=[
        "规则现在不开这只的新仓（新仓倍数 0）—— 风险报告「避险」：会被挡"])]}}
    rm = _room(_bk(), sm=sm)
    assert rm["per_ticker"]["7203.T"]["buy"]["short"] == "新仓倍数 0" and rm["per_ticker"]["6758.T"]["buy"]["short"] == "新仓倍数 0"
    assert rm["overall"]["buy_left"]["new"] == 0 and rm["cands"]["groups"] == {"新仓倍数 0": 1}
    assert rm["per_ticker"]["1545.T"]["buy"]["n"] == 1                     # 核心 ETF 不看新仓倍数
    man = {"items": {}, "blocks": {"6758.T": {"until": "2026-10-20", "id": "M1"}}}
    rm = _room(_bk(manual=man), sm={"suggest": {"rows": [_row("6758.T", 3000.0)]}})
    b = rm["per_ticker"]["6758.T"]["buy"]
    assert b["n"] == 0 and b["short"] == "不买回到 10/22" and b["next"] == "10/22 开盘" and "手动卖出后不买回" in b["why"][0]
    sm = {"suggest": {"rows": [_row("6758.T", 3000.0)]}}
    rm = _room(_bk(), sm=sm, quotes={"6758.T": 3100.0, "1545.T": {"px": 2460.0}})
    assert rm["per_ticker"]["6758.T"]["buy"]["short"] == "涨太多" and "超过 3%" in rm["per_ticker"]["6758.T"]["buy"]["why"][0]
    c = rm["per_ticker"]["1545.T"]["buy"]
    assert c["n"] == 1 and any("限价 ≤ 收盘 ×1.02" in w for w in c["why"])
    rm = _room(_bk(), _at(8, 10), sm=sm, quotes={"6758.T": 3100.0})        # 开盘前：寄付（≤ 收盘 ×1.03 的限价）→ 不按现价挡
    assert rm["per_ticker"]["6758.T"]["buy"]["n"] == 1


def test_pending_exit_and_instruction_in_flight():
    """规则已排定开盘卖 → 不再卖、不加仓；已有一条没处理完的手动指令 → 先撤回它或等它完成。"""
    b = _bk()
    b["state"]["pending_exit"] = {"7203.T": "stop"}
    r = _room(b)["per_ticker"]["7203.T"]
    assert r["sell"]["short"] == r["buy"]["short"] == "已在卖"
    w = [{"id": "M20261015-100000-trim-7203", "kind": "trim", "ticker": "7203.T", "pct": 5.0, "at": "2026-10-15T10:00:00+09:00"}]
    r = _room(_bk(), waiting=w)["per_ticker"]["7203.T"]
    assert r["sell"]["short"] == "有指令在处理" and "M20261015-100000-trim-7203" in r["sell"]["why"][0]


@pytest.mark.parametrize("tag", ["paper", "tachibana"])
def test_replay_1015_book(tag):
    """2026-10-15 的真实账本（现金 192 円、1545 ×4,110、卖 1545 已撤、买 1482 678 口还在「等开盘后」、固定 679 口还没被读）：
    盘中 → 1545 能卖 4,110 口、不能加（钱不够：不拿自己凑钱）；1482 今天已经有执行器的单 → 下一笔 10/16 开盘；买 0 · 卖 1 · 共 1。"""
    b = _book1015(tag)
    b["core_rule"]["px"] = {"1545.T": 243.7, "1482.T": 1474.0}           # 那天账本里的收盘（执行器 10/14 的决策写的）
    w = [{"id": "M20261015-084829-corefix-1482", "kind": "corefix", "ticker": "1482.T", "units": 679, "at": "2026-10-15T08:48:29+09:00"}]
    sm = {"new_pos": {"markets": {"JP": {"mult": 0.0}}}}                  # 那天：风险报告「避险」→ 新仓倍数 0
    rm = _room(b, _at(10, 12), tag=tag, waiting=w, sm=sm)
    assert rm["headline"] == "今天还能：买 0 次 · 卖 1 次 · 共 1 次"
    assert "新仓倍数 0：规则现在不开新仓" in rm["overall"]["buy_left"]["why"]
    a, f = rm["per_ticker"]["1545.T"], rm["per_ticker"]["1482.T"]
    assert a["sell"]["n"] == 1 and a["sell"]["max_qty"] == 4110 and a["buy"]["short"] == "钱不够"
    assert f["buy"]["n"] == 0 and any("同一只当天只下一笔 → 下一笔 10/16 开盘" in x for x in f["buy"]["why"])
    assert f["label"] == "1482 对冲版美国 7〜10 年国债" and rm["money"]["cash"] == round(192 * 0.99)
    assert _room(b, _at(10, 12), tag=tag, waiting=w, sm=sm, arm="off" if tag == "tachibana" else "file")["overall"]["trades_left"]["n"] == (
        0 if tag == "tachibana" else 1)
    assert _room(b, _at(15, 40), tag=tag, waiting=w, sm=sm)["headline"] == "今天还能：买 0 次 · 卖 0 次 · 共 0 次"
    # 新仓倍数不是 0、又没有候选的价格 → 新股只数名额（空 4 个；卖 1545 凑钱）：只是数，不猜买哪只
    rm = _room(b, _at(10, 12), tag=tag, waiting=w)
    assert rm["overall"]["buy_left"]["new"] == 4 and rm["money"]["fund_from"] == ["1545 纳斯达克 100"]


# ───────────────────────── 面板 / 接口 / 页面脚本 / 命令行 ─────────────────────────
def _pbook():
    """面板用的账本文件（盘中 = AT 那天）。"""
    b = _bk()
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def test_page_has_card_on_top_of_trade_tab_and_chips():
    """交易页最上面的小卡（标题、一行时段、展开看每只：代码带名字）+ 持仓每只的小标记；CFG.room = 有卡片。"""
    _pbook()
    h = panel.render("paper", "t" * 40, AT)
    i = h.index("<section class='card' id='room'>")
    card = h[i:h.index("</section>", i)]
    assert "<b>今天还能：买 5 次 · 卖 2 次 · 共 5 次</b>" in card and "盘中（前場）：现在写的买卖 → 马上（盘中）下单" in card
    assert "<b>7203 トヨタ自動車</b> <span class='chip'>今天还能卖 ✓ / 买 ✓（二选一：同一只当天只下一笔）</span>" in card
    assert "卖：最多 200 股 · 用「卖出全部」/「调仓…」" in card and "1545 纳斯达克 100" in card
    assert "券商不限次数；限制来自差金決済与执行器规则" in card and TR.SAKIN_URL in card
    assert i < h.index("<section class='card' id='orders'>")                  # 交易页：卡片在「手动指令」之前（最上面）
    assert "data-room='7203.T'>今天还能卖 ✓ / 买 ✓（二选一：同一只当天只下一笔）</div>" in h
    assert "data-room='1545.T'>今天还能卖 ✓" in h
    cfg = json.loads(re.search(r"<script type='application/json' id='qb-cfg'>(.*?)</script>", h, re.S).group(1))
    assert cfg["room"] is True
    assert "<link rel='modulepreload' href='/static/room.js?v=" in h


def test_api_local_and_phone(server, servers):  # noqa: F811
    """/api/trade_room：本机端口直接给；手机端口要你本人（没配对 401，配对了 200）。"""
    _pbook()
    port, _tok = server
    code, body, _ = _lreq(port, "GET", "/api/trade_room?book=paper")
    j = json.loads(body)
    assert code == 200 and j["ok"] and j["headline"].startswith("今天还能：买 ") and "7203.T" in j["per_ticker"]
    assert j["note"] == TR.NOTE and j["per_ticker"]["7203.T"]["label"] == "7203 トヨタ自動車"
    _lp, pp, _t = servers
    code, txt, _ = _phone(pp, "GET", "/api/trade_room?book=paper")
    assert code == 401 and "7203" not in txt
    c, _ = PP.new_code()
    ok, _m, ck = PP.pair(c, "iPhone")
    code, txt, _ = _phone(pp, "GET", "/api/trade_room?book=paper", cookie=ck)
    assert code == 200 and json.loads(txt)["ok"]


def test_api_survives_a_broken_book(monkeypatch):
    """算不出 → 200 + ok=false（页面保留上一次的，不报错）。"""
    _pbook()
    monkeypatch.setattr(TR, "room", lambda *a, **k: 1 / 0)
    code, j = panel.trade_room_json("paper", AT)
    assert code == 200 and j["ok"] is False and "没算成" in j["msg"]


def _text(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html))


def test_room_js_renders_same_card_in_node(tmp_path):
    """页面脚本 room.js 的 roomShow 按 /api/trade_room 重画的卡片与服务器画的（panel._room_card）字一样；持仓的小标记跟着变；
    接口出错（ok=false）→ 不动。没有 node 就跳过。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    sm = {"suggest": {"rows": [_row("6758.T", 3000.0), _row("8035.T", 9_000_000.0)]}}
    rm = _room(_bk(orders=[_o("1545.T", "SELL", qty=10, px=2400.0, kind="core")]), sm=sm, paused="x")
    want = _text(panel._room_card(rm))
    fns = "\n".join(_js_fn(panel._JS, n) for n in ("nd", "roomSide", "roomShow"))
    js = """
class El { constructor(t){ this.tagName=String(t).toUpperCase(); this.children=[]; this._t=''; this.className=''; this.dataset={}; this.hidden=true; this.open=false; }
  appendChild(c){ this.children.push(c); return c; }
  querySelector(s){ for(const c of this.children){ if(c.tagName===String(s).toUpperCase()) return c; const x=c.querySelector && c.querySelector(s); if(x) return x; } return null; }
  set textContent(v){ this._t=String(v); this.children=[]; } get textContent(){ return this._t+this.children.map(c=>c.textContent).join(''); } }
const ROOM=new El('section'), CHIP=new El('div'), GONE=new El('div'); CHIP.dataset.room='7203.T'; GONE.dataset.room='9999.T'; GONE.textContent='old';
const document={createElement:t=>new El(t), createTextNode:t=>({textContent:String(t)}), querySelectorAll:s=>[CHIP, GONE]};
const $=s=>s==='#room' ? ROOM : null;
const nameify=s=>s;
__FNS__
const J=__J__;
roomShow(J);
const out={card:ROOM.textContent, hidden:ROOM.hidden, chip:CHIP.textContent, gone:GONE.textContent,
           a:ROOM.children.filter(c=>c.tagName==='DIV').pop().children.filter(c=>c.tagName==='A').map(a=>a.href)};
ROOM.children[3].open=true; roomShow(J); out.keep=ROOM.querySelector('details').open;
roomShow({ok:false}); out.same=ROOM.textContent===out.card;
console.log(JSON.stringify(out));
""".replace("__FNS__", fns).replace("__J__", json.dumps({"ok": True, **rm}, ensure_ascii=False))
    f = tmp_path / "room.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    assert o["card"] == want and o["hidden"] is False and o["same"] and o["keep"] is True
    assert o["chip"] == rm["per_ticker"]["7203.T"]["chip"] and o["gone"] == "" and o["a"] == [TR.SAKIN_URL]
    assert "选股页的候选 2 只：名额与钱都够的 1 只；不能：钱不够 1 只（只是数，不是建议；买不买是你的决定）" in o["card"]
    assert "1545 纳斯达克 100" in o["card"] and "1545.T" not in o["card"]


def test_manual_list_prints_the_section(monkeypatch, capsys):
    import run
    _pbook()
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    assert run.main(["manual", "list", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "今天还能：买 5 次 · 卖 2 次 · 共 5 次（券商不限次数；限制来自差金決済与执行器规则）" in out
    assert "  - 7203 トヨタ自動車：今天还能卖 ✓ / 买 ✓（二选一：同一只当天只下一笔）" in out
    assert f"  差金決済：{TR.SAKIN_URL}（2026-10-15 核对）" in out
