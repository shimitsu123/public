"""2026-10-14 复核（986a4fb 之后的提交）：
① 固定口数 + 明早日本买入的日元缺口 → 缺口先补、固定的买入不被取消（以前先凑钱后被缺口取消，多卖的钱闲着）；
② 「全部换成」已下单（今天在执行）→ 不显示「恢复成 N%」/「确认买入」、改比例的说明不叫你撤回整批；
③ 别的票还没执行的手动买入 + 「全部换成」→ 两边都拒（同一次决策买进、留着不卖）；
④ 撤销撤回：比例 / 固定口数恢复成「等执行器读」（不是「等下单」）；
⑤ 「恢复成 N%」（N < 100）的说明写「按规则目标额的 N%」，不写照规则；
⑥ 平摊凑钱的加仓（adjust 往上）被挡 → 凑钱的卖出也不做（决策时 / 盘中）；
⑦ HALT 中读到的闲置资金比例 / 固定口数：说明写明、HALT 卡片 / manual list 列出、解除时列进积压；
⑧ core_effects / 面板：还没读的固定口数指令也算。"""
import json

from qbreak import manual_orders as MO
from qbreak import panel, paths

from test_allin_exec import _orders
from test_core_etf_restore import _morning, _paper2, _save, _units, _w
from test_manual_buy import _write
from test_manual_now import _at
from test_manual_orders import TAG, _Run


# ────────── ① 固定口数 + 日元缺口 ──────────
def _decide(fix: bool, short: bool):
    r = _paper2()
    _morning(r, 8)
    eng, st = r.eng, r.eng.st
    if fix:
        eng.core_fix = {"1482.T": 100}
    eq = st.cash_jpy + sum(u * 700.0 for u in st.core_units.values())
    reserve = st.cash_jpy + 50_000 if short else 0.0                   # 明早的日本买入比现金多 ¥50,000
    eng._decide_core(r.k - 1, eq, [], reserve, st.cash_jpy, 0.0, 150.0)
    return dict(st.core_plan), _units(r)


def test_fixed_buy_survives_a_stock_shortfall():
    plan0, u = _decide(False, True)
    assert u["1545.T"] > 0 and plan0 == {"1545.T": ["SELL", plan0["1545.T"][1]]} and plan0["1545.T"][1] * 700 >= 50_000
    plan1, _ = _decide(True, False)
    assert plan1["1482.T"] == ["BUY", 100] and plan1["1545.T"][0] == "SELL"
    plan, _ = _decide(True, True)
    assert plan["1482.T"] == ["BUY", 100]                              # 以前：缺口那一步把固定的买入取消、1545 多卖的钱闲着
    assert plan["1545.T"][0] == "SELL" and plan["1545.T"][1] > plan0["1545.T"][1]
    assert plan["1545.T"][1] * 700 >= 50_000 + 100 * 1000              # 卖出所得够补缺口 + 固定的买入


# ────────── ② 「全部换成」已下单的那天 ──────────
def test_allin_placed_hides_restore_buttons_and_does_not_say_withdraw():
    r = _paper2()
    _morning(r, 8)
    _w(r.tag, "M-half", kind="core", pct=50.0)
    _morning(r, 2)
    _w(r.tag, "M-all-core", kind="core", pct=0, fund_for="B.T", batch="all", prev_pct=50)
    _w(r.tag, "M-all-buy", kind="buy", ticker="B.T", unit="shares", value=100_000, fund="all")
    _morning(r)
    _save(r)
    assert r.ux.book["manual"]["items"]["M-all-buy"]["status"] == "placed"
    assert (r.ux.book["manual"].get("core_pause") or {}).get("prev_pct") == 50
    for hh in (10, 16):
        now = _at(r, hh, 0)
        h = panel.render(r.tag, "tok", now=now)
        assert "data-act='core-restore'" not in h and "data-act='core-resume'" not in h and "恢复成 50%" not in h
        assert "「全部换成 B」今天已下单、在执行" in h                 # 文字写 label（假代码没名字：只写代码；2026-10-15）
        for pct in (50, 100):
            ok, msg, _ = panel.submit({"book": r.tag, "kind": "core", "pct": pct}, now)
            assert not ok and "今天已下单、在执行" in msg and "先撤回" not in msg


def test_allin_busy_text_by_status():
    assert MO.allin_busy_text([]) is None
    pend = {"ticker": "B.T", "status": "pending"}
    assert MO.allin_busy_text([pend]).endswith("先撤回它（整批一起撤），再改")
    placed = {"ticker": "B.T", "status": "placed"}
    assert "今天已下单" in MO.allin_busy_text([pend, placed]) and "撤回" not in MO.allin_busy_text([placed])


# ────────── ③ 还没执行的手动买入 + 「全部换成」 ──────────
def test_pending_manual_buy_blocks_allin_and_allin_blocks_a_new_buy():
    r = _Run([1000.0] * 30, entry=())
    r.until(14)
    assert "A.T" not in r.eng.st.pos
    _write({"kind": "buy", "ticker": "A.T", "unit": "shares", "value": 100, "source": "test", "id": "M-a-buy",
            "at": r.at(r.k - 1, 5).isoformat()})
    fa = MO.fund_all(r.ux.book, TAG, "B.T")
    assert fa["blocked"] and "A 有还没执行的买入指令（M-a-buy）" in fa["blocked"] and "先撤回它" in fa["blocked"]
    MO.requests_path(TAG).unlink()
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    why = MO.check({"kind": "buy", "ticker": "A.T", "unit": "rule"}, r.ux.book, TAG)   # 测试用的票（A.T）不过 normalize
    assert why and "「全部换成 B」在等决策" in why and "A 会和它在同一次决策里买进" in why


# ────────── ④ 撤销撤回的状态词 ──────────
def test_uncancel_of_a_ratio_goes_back_to_waiting_for_the_executor():
    from test_panel import AT, _book
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    ok, _m, core = panel.submit({"book": "paper", "kind": "core", "pct": 50}, AT)
    assert ok
    ok, _m, cxl = panel.submit({"book": "paper", "kind": "cancel", "target": core["id"]}, AT)
    assert ok
    h = panel.render("paper", "t" * 40, AT)
    assert f"data-act='uncancel' data-id='{cxl['id']}'" in h and "data-st='等执行器读'" in h
    ok, msg, _ = panel.submit({"book": "paper", "kind": "uncancel", "target": cxl["id"]}, AT)
    assert ok and "原来的指令恢复「等执行器读」" in msg and "「等下单」" not in msg
    assert MO.wait_word({"kind": "sell"}) == "等下单" and MO.wait_word({"kind": "core"}) == "等执行器读"
    assert MO.wait_word({"kind": "corefix"}) == "等下单"                  # D1（2026-10-15）：固定口数当天按时段下单
    assert MO.wait_word({"kind": "corefix", "fund_for": "B.T", "batch": "all"}) == "等执行器读"   # 「全部换成」同批的：等那次决策
    js = (panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8")
    assert "原来的指令恢复「'+(d.st||'等下单')+'」" in js


# ────────── ⑤ 「恢复成 N%」的说明 ──────────
def test_restore_to_half_says_half_of_the_rule_target():
    from test_core_pause import AT, _paused
    b = _paused()
    ri = MO.resume_info(b, "paper", AT, pct=50.0)
    assert "按规则目标额的 50% 买入" in ri["text"] and "之后每天按 50% 调" in ri["text"] and "照规则买入" not in ri["text"]
    assert "照规则买入" in MO.resume_info(b, "paper", AT)["text"]               # 100% 不变
    ok, msg, _ = panel.submit({"book": "paper", "kind": "core", "pct": 50}, AT)
    assert ok and msg.startswith("已写：恢复成 50%（闲置资金比例 0% → 50%）") and "按规则目标额的 50% 买入核心 ETF" in msg
    assert "照规则买入" not in msg
    js = (panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8")
    assert "CFG.when+'按规则目标额的 '+v+'% 买入；之后每天按 '+v+'% 调'" in js


# ────────── ⑥ 平摊凑钱的加仓被挡 ──────────
def _held_two(r, block: bool = True):
    r.until(14)
    assert "A.T" in r.eng.st.pos
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 200, "source": "test", "id": "M-b",
            "at": r.at(r.k - 1, 6).isoformat()})
    r.day()
    r.day()
    assert "B.T" in r.eng.st.pos
    base = r.eng.entry_block_fn
    if block:
        r.eng.entry_block_fn = lambda t, i, _b=base: "决算前 2 天" if t == "A.T" else (_b(t, i) if _b else None)
    return int(r.eng.st.pos["A.T"].shares), int(r.eng.st.pos["B.T"].shares)


def _split_add(at: str, sha: int, shb: int) -> None:
    _write({"kind": "adjust", "ticker": "B.T", "unit": "shares", "value": shb - 100, "fund_for": "A.T", "source": "test",
            "id": "M-sp-b", "at": at, "dir": -1, "cur0": shb})
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": sha + 100, "fund": "split", "source": "test",
            "id": "M-sp-a", "at": at, "dir": 1, "cur0": sha})


def test_split_add_blocked_at_decision_sells_nothing():
    r = _Run([1000.0] * 40, entry=(10,), bear_all=True)
    sha, shb = _held_two(r)
    _split_add(r.at(r.k - 1, 6).isoformat(), sha, shb)
    r.day()
    a, b = r.item("M-sp-a"), r.item("M-sp-b")
    assert a["status"] == "rejected" and a["msg"].startswith("不加仓：决算前 2 天") and "凑钱的卖出也不做" in a["msg"]
    assert b["status"] == "rejected" and "加仓 A 被挡 → 凑钱的卖出也不做" in b["msg"]
    assert "B.T" not in r.ux.manual.m["trims"] and not _orders(r, "B.T", "SELL")
    r.day()
    assert int(r.eng.st.pos["B.T"].shares) == shb and int(r.eng.st.pos["A.T"].shares) == sha


def test_split_add_not_blocked_still_sells_then_adds():
    """闸门不误挡：没被挡的平摊凑钱加仓照常 —— 凑钱的卖出与加仓同一次决策都下。"""
    r = _Run([1000.0] * 40, entry=(10,), bear_all=True)
    sha, shb = _held_two(r, block=False)
    _split_add(r.at(r.k - 1, 6).isoformat(), sha, shb)
    r.day()
    assert r.item("M-sp-a")["status"] == "placed" and r.item("M-sp-b")["status"] == "placed"
    r.day()
    assert int(r.eng.st.pos["B.T"].shares) == shb - 100 and int(r.eng.st.pos["A.T"].shares) == sha + 100


def test_split_add_blocked_intraday_sends_no_funding_sell():
    r = _Run([1000.0] * 40, entry=(10,), bear_all=True)
    sha, shb = _held_two(r)
    _split_add(r.at(r.k, 10, 0).isoformat(), sha, shb)
    r.session(10, 0)
    a, b = r.item("M-sp-a"), r.item("M-sp-b")
    assert a["status"] == "rejected" and "决算前 2 天" in a["msg"] and "凑钱的卖出也不做" in a["msg"]
    assert b["status"] == "rejected" and "加仓 A 被挡" in b["msg"]
    assert not _orders(r, "B.T", "SELL") and int(r.eng.st.pos["B.T"].shares) == shb


# ────────── ⑦ HALT 中读到的闲置资金比例 / 固定口数 ──────────
def test_core_written_during_halt_is_marked_listed_and_reported_on_lift(capsys, monkeypatch):
    r = _paper2()
    _morning(r, 8)
    u0 = _units(r)["1545.T"]
    assert u0 > 0
    paths.halt_file().write_text("stop", encoding="utf-8")
    _w(r.tag, "M-core-0", kind="core", ticker="1545.T", pct=0.0, target=0, at="2026-01-05T20:00:00+09:00")
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=100, at="2026-01-05T20:01:00+09:00")
    _morning(r, 2)
    it = r.ux.book["manual"]["items"]
    assert it["M-core-0"]["status"] == "done" and it["M-core-0"].get("halt") and it["M-fix-1482"].get("halt")
    assert it["M-core-0"]["msg"].endswith(f"（{MO.HALT_CORE_MSG}）") and it["M-core-0"]["msg"].count(MO.HALT_CORE_MSG) == 1
    assert _units(r)["1545.T"] == u0                                       # HALT 中不动
    _save(r)
    h = panel.render(r.tag, "tok", now=_at(r, 16, 0))
    card = h[h.index("id='halt'"):]
    card = card[:card.index("</section>")]
    assert "HALT 期间改的闲置资金比例 / 固定口数 2 条" in card and "M-core-0 卖出全部 1545 纳斯达克 100（之后停买闲置资金 ETF） 写于 01/05" in card
    assert "解除后照它买卖 ETF（盘中解除会马上按现价下单" in card      # 复核 UI F1（2026-10-16）：以前写「解除后下一次决策照它买卖 ETF」
    from qbreak import calendar_jp as CJ
    import run
    monkeypatch.setattr(CJ, "now_jst", lambda: _at(r, 16, 0))
    assert run.main(["manual", "list", "--broker", r.tag]) == 0
    out = capsys.readouterr().out
    assert f"★ HALT 期间改的闲置资金比例 / 固定口数 2 条，解除后照它买卖 ETF（{MO.HALT_CORE_AFTER}）：M-core-0" in out
    paths.halt_file().unlink()
    r.ux.blocked = None
    _morning(r)
    ev = [e for e in r.ux.book["events"] if "HALT 期间改的闲置资金比例 / 固定口数" in e["msg"]]
    assert len(ev) == 1 and ev[0]["level"] == "warn"
    assert ev[0]["msg"].startswith(f"HALT 期间改的闲置资金比例 / 固定口数 2 条，照它买卖 ETF（{MO.HALT_CORE_AFTER}）："
                                   "M-core-0 卖出全部 1545 纳斯达克 100")
    assert "要改回" in ev[0]["msg"] and "manual cancel" not in ev[0]["msg"]
    it = r.ux.book["manual"]["items"]
    assert not it["M-core-0"].get("halt") and MO.HALT_CORE_MSG not in it["M-core-0"]["msg"]
    assert r.ux.summary()["manual"]["halt_backlog"] == ev[0]["msg"]
    _morning(r, 2)
    assert len([e for e in r.ux.book["events"] if "HALT 期间改的闲置资金比例" in e["msg"]]) == 1   # 只说一次
    assert _units(r).get("1545.T", 0) == 0 and _units(r).get("1482.T", 0) == 100


def test_halt_core_lists_unread_but_not_batch_or_dropped():
    items = [{"id": "a", "kind": "core", "halt": True, "pct": 50.0, "at": "2026-10-06T10:00"},
             {"id": "b", "kind": "core", "pct": 80.0, "at": "2026-10-05T10:00"}]
    unread = [{"id": "c", "kind": "corefix", "ticker": "1482.T", "units": 100, "at": "2026-10-04T10:00"},
              {"id": "d", "kind": "core", "pct": 0, "fund_for": "B.T", "at": "2026-10-04T10:00"},
              {"id": "e", "kind": "core", "pct": 20.0, "at": "2026-10-04T10:00"},
              {"id": "f", "kind": "sell", "ticker": "A.T", "at": "2026-10-04T10:00"}]
    assert [x["id"] for x in MO.halt_core(items, unread, {"e"})] == ["c", "a"]


# ────────── ⑧ 还没读的固定口数 ──────────
def test_core_effects_counts_an_unread_corefix():
    r = _paper2()
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=100)
    _morning(r, 8)                                                         # 1482 固定 100 口、1545 照规则
    _save(r)
    book = json.loads((paths.state_dir() / f"live_unified_{r.tag}.json").read_text(encoding="utf-8"))
    assert MO.core_fixed(book) == {"1482.T": 100}
    _w(r.tag, "M-fix-1545", kind="corefix", ticker="1545.T", units=_units(r)["1545.T"])   # 还没读：1545 也固定
    assert [t for t, *_ in MO.core_effects(book, 50.0)] == ["1545.T"]
    assert MO.core_effects(book, 50.0, tag=r.tag) == []                   # 以前说 1545 跟着比例变
    _w(r.tag, "M-clear-1482", kind="corefix", ticker="1482.T", clear=True)   # 还没读的恢复按规则：1482 又跟比例
    assert "1482.T" not in MO.core_fixed(book, r.tag)
    h = panel.render(r.tag, "tok", now=_at(r, 16, 0))
    cfg = json.loads(h.split("id='qb-cfg'>", 1)[1].split("</script>", 1)[0])
    assert "1545.T" not in cfg["cores"]                                    # 页面上调一只 ETF 时的联动也不算它
