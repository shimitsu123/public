"""「交易」只显示今天要成交的单 —— 复核 8（2026-10-16，事后）：
  ① 15:25〜15:30 面板自动下单暂停：撤单 / 模拟账户的补跑面板叫到 15:30（不是 15:25）→ 这 5 分钟里也看暂停；
  ② 模拟账户早上没跑完、面板暂停（08:55 之前）：固定口数 /「全部换成」不再写「今天 09:00 开盘」放在上面；
  ③ 整组撤单等立花确认时又暂停：买单写「撤单已受理、等立花确认」，卖单先确认买单再撤（不一律建议去立花网站撤）；
  ④ 09:30 自检：写了撤单、面板暂停、单还挂着 → 没通过（★ 交易）；撤单指令本身跟着那笔单放在上面（不算数字）；
  ⑤ 写了撤单、撤单的运行没处理到的还没发出的单：执行器对账时当成你撤了（手动买入不留到下一次决策重新买）；
  ⑥ HALT 中「今天的单还没排出来」不写「跑完之后这里才有今天的单」；⑦ 休市日不重复「今天休市」；
  ⑧ 「另有 …」/「已结束 / 不是今天的」点开过的刷新之后照样开着。"""
import datetime as dt
import json
import re
import shutil
import subprocess

import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST
from test_trade_today import (BUY_ID, D, _badge_ok, _buy_book, _done_book, _mbook, _morder, _parts, _pause, _row, _t,
                              _trg_calls, _want)
from test_panel import _book1015

SELL_7203 = "<b>卖 7203 トヨタ自動車：100 股</b>"


def _agent():
    ag = paths.launch_agents()
    ag.mkdir(parents=True, exist_ok=True)
    (ag / f"{paths.PAPER_AGENT}.plist").write_text("<plist/>", encoding="utf-8")


def _tb_cancel(now_rid_at: dt.datetime):
    """立花：10/16 08:30 发出的寄付卖单（还挂着）+ 写了撤单（指令文件里）。"""
    tag, last = "tachibana", "2026-10-15"
    o = _morder(last, "SELL", "7203.T", "rule", "SENT", "已下单", broker_id="B1", sent_at="2026-10-16T08:30:00+09:00")
    b = _mbook(tag, last, [o], {})
    rid = f"M{now_rid_at:%Y%m%d-%H%M%S}-cancel_order"
    _want({"id": rid, "kind": "cancel_order", "cid": o["cid"], "at": now_rid_at.isoformat()}, tag)
    return b, o, rid


# ────────── ① 15:25〜15:30 ──────────
def test_cancel_paused_between_1525_and_1530_stays_stuck_and_counted():
    tag = "tachibana"
    now = _t(2026, 10, 16, 15, 27)
    b, o, rid = _tb_cancel(_t(2026, 10, 16, 9, 10))
    assert _trg_calls(now) == [(tag, "cancel")]                                  # 没暂停：面板 15:30 之前照样叫撤单
    _pause(tag, [rid], _t(2026, 10, 16, 9, 15))
    assert _trg_calls(now) == []
    html = panel.render(tag, "t" * 40, now)
    top, _later, _ = _parts(html)
    row = _row(top, SELL_7203)
    assert f"<span class='chip'>{LO.STUCK_CHIP}</span>" in row and "<span class='chip'>撤单中</span>" not in row
    assert _badge_ok(html, tag, now) == 1                                        # 以前 0（「撤单中」）
    r = LO.outlook(b, MO.unseen(tag, b), now, tag=tag, halt=False, paused=True)["orders"][o["cid"]]
    assert r["cls"] == "stuck" and r["state"] == "will"


def test_paper_morning_behind_paused_between_1525_and_1530_does_not_promise_a_catchup():
    _agent()
    for hh, mm in ((15, 20), (15, 27)):
        now = _t(2026, 10, 16, hh, mm)
        _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})            # 10/16 早上的运行没跑（成交日 10/15 的单）
        _pause("paper", [], _t(2026, 10, 16, 9, 0))
        html = panel.render("paper", "t" * 40, now)
        top, later, _ = _parts(html)
        assert "面板会自动补跑" not in top + later, (hh, mm)
        assert "<summary>另有 2 条等 10/19（周一）07:40 的运行</summary>" in later, (hh, mm)
        assert _badge_ok(html, "paper", now) == 2


# ────────── ② 模拟账户早上没跑完、暂停（08:55 之前）──────────
@pytest.mark.parametrize("kind", ["corefix", "allin"])
def test_paper_morning_behind_paused_fix_and_allin_are_not_today(kind):
    now = _t(2026, 10, 16, 8, 20)
    b = _done_book("2026-10-14")                                                  # 10/16 早上的运行没完成
    if kind == "corefix":
        b["core_rule"] = {"lot": {"1545.T": 10, "1482.T": 1}, "decided_on": "2026-10-14"}
        (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b), encoding="utf-8")
        rid = "M20261016-080000-corefix-1482"
        _want({"id": rid, "kind": "corefix", "ticker": "1482.T", "units": 500, "at": "2026-10-16T08:00:00+09:00"})
        head = "固定 1482 对冲版美国 7〜10 年国债"
    else:
        rid = "M20261016-080000-buy-6758"
        _want({"id": rid, "kind": "buy", "ticker": "6758.T", "fund": "all", "at": "2026-10-16T08:00:00+09:00"})
        head = "全部换成这只 6758 ソニーグループ"
    _agent()
    _pause("paper", [rid], _t(2026, 10, 16, 8, 10))
    assert _trg_calls(now) == []                                                  # 补跑不来
    html = panel.render("paper", "t" * 40, now)
    top, later, _ = _parts(html)
    assert head not in top and head in later and "今天 09:00 开盘" not in top
    assert "面板自动下单今天暂停了" in _row(later, "<b>" + head)
    assert _badge_ok(html, "paper", now) == 1
    bk = json.loads((paths.state_dir() / "live_unified_paper.json").read_text())
    x = LO.outlook(bk, MO.unseen("paper", bk), now, tag="paper", halt=False, paused=True)["items"][rid]
    assert x["state"] == "wont" and x["cls"] == "paused"


# ────────── ③ 整组撤单等立花确认时又暂停 ──────────
def test_group_cancel_waiting_for_confirmation_then_paused_says_what_to_check_first(monkeypatch):
    from test_cancel_group import BUY, SELL, T9, _at_exch, _gbook, _Pending, _tbook
    monkeypatch.setattr(LO, "_sleep", lambda s: None)
    b = _gbook()
    _at_exch(b, BUY, "B1")
    _at_exch(b, SELL, "S1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: T9)
    res = LO.cancel_book(p, lambda: _Pending(LO.GROUP_POLLS), paper=False, tag="tachibana", requests=True, clock=lambda: T9,
                         source="面板的撤单指令")
    assert res["grp"][SELL]["state"] == "wait"                                    # 买单的撤单已受理、立花还没确认
    now = T9 + dt.timedelta(minutes=5)
    _pause("tachibana", [], T9 + dt.timedelta(minutes=3))
    bk = json.loads(p.read_text(encoding="utf-8"))
    rows = LO.outlook(bk, MO.unseen("tachibana", bk), now, tag="tachibana", halt=False, paused=True)["orders"]
    buy, sell = rows[BUY], rows[SELL]
    assert buy["cls"] == sell["cls"] == "stuck"
    assert "撤单已受理、等立花确认" in buy["reason"]
    assert "先在立花的注文一覧确认买单（买 1482 对冲版美国 7〜10 年国债）已撤掉 / 没成交，再撤这笔" in sell["reason"]
    assert "或在立花网站 / 手机网站撤单" not in sell["reason"] and "或在立花网站 / 手机网站撤单" not in buy["reason"]
    html = panel.render("tachibana", "t" * 40, now)
    assert _badge_ok(html, "tachibana", now) == 2


# ────────── ④ 09:30 自检 / 撤单指令的位置 ──────────
def test_watchdog_fails_when_a_cancel_is_stuck_and_the_cancel_row_stays_with_its_order():
    from qbreak import watchdog as WD
    tag = "tachibana"
    b, o, rid = _tb_cancel(_t(2026, 10, 16, 9, 10))
    now = _t(2026, 10, 16, 9, 31)
    html = panel.render(tag, "t" * 40, now)                                       # 没暂停：撤单中 → 撤单指令跟着在上面
    top, _later, ended = _parts(html)
    assert "<b>撤单" in top and "<b>撤单" not in ended
    assert _badge_ok(html, tag, now) == 0
    _pause(tag, [rid], _t(2026, 10, 16, 9, 15))
    rec = WD.evaluate(tag, now)
    assert rec["ok"] is False and rec.get("trade") is True
    assert any(r.startswith("写了撤单、单还挂着 1 笔：") and "7203 トヨタ自動車" in r for r in rec["reasons"])
    html = panel.render(tag, "t" * 40, now)
    top, _later, ended = _parts(html)
    assert "<b>撤单" in top and "<b>撤单" not in ended
    assert _badge_ok(html, tag, now) == 1                                         # 那笔单算、撤单指令本身不算


# ────────── ⑤ 写了撤单、撤单的运行没处理到的还没发出的单 ──────────
def test_unsent_manual_buy_with_an_unprocessed_cancel_is_not_bought_again(monkeypatch):
    from qbreak.live_unified import ASKED_UNSENT
    from test_manual_buy import _buy
    from test_manual_orders import TAG, _Run
    monkeypatch.setattr(MO, "_CID", re.compile(r"^U(\d{4}-\d{2}-\d{2})-(BUY|SELL)-([0-9A-Z]{1,4}\.T)(-[0-9A-Za-z]{1,20})?$"))
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _buy(r, id="M-x")
    r.day()                                                                       # 决策：B.T 等开盘后（DEFERRED）
    d0 = r.eng.st.last_date
    buy = next(o for o in r.ux.orders if o.ticker == "B.T")
    assert buy.status == "DEFERRED"
    t902 = dt.datetime.combine(r.eng.gidx[r.k].date(), dt.time(9, 2), tzinfo=JST)
    MO.append(TAG, {"kind": "cancel_order", "cid": buy.cid}, clock=lambda: t902)   # 09:02 点了撤单；撤单的运行没来（暂停 / 失败）
    r.day()                                                                       # 09:05 开盘后：不发（CANCEL_ASKED）→ 下一个 07:40 对账
    hist = [o for h in r.ux.book.get("history") or [] for o in h["orders"] if o["cid"] == buy.cid]
    assert hist and hist[0]["status"] == "CANCELLED" and hist[0]["note"] == ASKED_UNSENT
    it = r.item("M-x")
    assert it["status"] == "cancelled", it                                        # 以前：留到下一次决策（placed）、第二天又买
    assert not any(o.ticker == "B.T" and o.side == "BUY" for o in r.ux.orders if o.decided_on != d0)


def test_requeue_and_cancel_texts_follow_the_cancel():
    from qbreak.live_unified import requeue_next
    b = _buy_book("tachibana", "DEFERRED", "开盘前余力不足 → 开盘后按始値检查", sent_qty=0)
    o = b["orders"][0]
    now = _t(2026, 10, 15, 15, 40)                                                # 成交日收盘之后：开盘后的补单没跑 → 系统原因
    assert requeue_next(o, b["orders"], now, dt.date(2026, 10, 15)) is True
    assert requeue_next(o, b["orders"], now, dt.date(2026, 10, 15), {o["cid"]}) is False
    why = LO.cancel_why(o, b, now, paper=False)
    assert "会在下一次决策重新处理" in why and f"撤回 {BUY_ID}" in why and "不用撤" not in why
    _want({"id": "M20261015-151000-cancel_order", "kind": "cancel_order", "cid": o["cid"], "at": "2026-10-15T15:10:00+09:00"},
          "tachibana")                                                            # 15:30 之前写了撤单、撤单的运行没处理到
    html = panel.render("tachibana", "t" * 40, now)
    top, later, ended = _parts(html)
    assert "买入 6758 ソニーグループ" in ended and "买入 6758 ソニーグループ" not in later + top   # 以前「另有 … 等下一次决策」
    assert _badge_ok(html, "tachibana", now) == 0


# ────────── ⑥ HALT / ⑦ 休市日 ──────────
@pytest.mark.parametrize("hh,run", [(7, "今天早上 07:40 的运行还没跑"), (8, "今天早上的运行还没跑完")])
def test_halt_pending_does_not_promise_todays_orders(hh, run):
    _done_book("2026-10-14")                                                      # 成交日 10/15 的决策：10/16 的单还没排
    paths.halt_file().write_text("测试", encoding="utf-8")
    try:
        now = _t(2026, 10, 16, hh, 0)
        html = panel.render("paper", "t" * 40, now)
        top, _later, _ = _parts(html)
        assert "跑完之后这里才有今天的单" not in top
        assert f"今天的单还没排出来：{run}；HALT 生效中，执行器不会排出要成交的单（解除之后的运行才会）" in top
    finally:
        paths.halt_file().unlink()


def test_non_trading_day_says_closed_once():
    now = _t(2026, 10, 17, 12, 0)                                                 # 周六
    _done_book("2026-10-15")
    html = panel.render("paper", "t" * 40, now)
    top, _later, _ended = _parts(html)
    assert re.sub(r"<[^>]+>", " ", top).count("今天休市") == 1
    assert "执行器的单是上一次决策的单" not in top                               # 都收在「已结束」：不再提它们


# ────────── ⑧ 点开过的「另有 …」/「已结束」刷新之后照样开着 ──────────
def test_folded_sections_reopen_after_reload_in_node(tmp_path):
    from test_panel import _js_fn
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    js = panel._JS
    fns = "\n".join(_js_fn(js, n) for n in ("foldKey", "foldSave", "foldRestore"))
    src = r"""
const FOLDK='qb-fold';
function mk(sec, cls){ return {open:false, classList:{contains:c=>c===cls}, closest:()=>({id:sec})}; }
const store = {m:{}, getItem(k){ return this.m[k]===undefined ? null : this.m[k]; }, setItem(k, v){ this.m[k]=String(v); }};
__FNS__
let L = mk('today', 'later'), E = mk('orders', 'ended');
L.open = true; foldSave(L, store, '/');                         // 点开「另有 …」
const doc = {querySelectorAll: () => [L, E]};
L = mk('today', 'later'); E = mk('orders', 'ended');            // 刷新：都是新的、收起的
const doc2 = {querySelectorAll: () => [L, E]};
foldRestore(doc2, store, '/');
const a = [L.open, E.open];
L.open = false; foldSave(L, store, '/');                        // 又收起来
const L2 = mk('today', 'later'); foldRestore({querySelectorAll: () => [L2]}, store, '/');
const bad = {getItem(){ throw new Error('blocked'); }, setItem(){ throw new Error('blocked'); }};
const L3 = mk('today', 'later'); foldRestore({querySelectorAll: () => [L3]}, bad, '/'); foldSave(L3, bad, '/');
console.log(JSON.stringify({a, b: L2.open, c: L3.open}));
""".replace("__FNS__", fns)
    f = tmp_path / "fold.js"
    f.write_text(src, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    assert json.loads(p.stdout) == {"a": [True, False], "b": False, "c": False}
    assert "document.addEventListener('toggle'" in js and "foldRestore(document, sessionStorage, location.pathname)" in js


def test_claude_md_points_at_the_renamed_card():
    """CLAUDE.md 让 Claude 指给用户的卡片名跟着面板改（「今天的单」→「今天要成交的单」；复核 8）。"""
    from pathlib import Path
    md = Path(__file__).resolve().parents[2] / "CLAUDE.md"
    if not md.exists():
        pytest.skip("没有仓库根目录的 CLAUDE.md")
    s = md.read_text(encoding="utf-8")
    assert "「今天的单」" not in s and "「今天要成交的单」的「撤单」" in s
