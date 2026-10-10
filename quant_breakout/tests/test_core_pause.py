"""卖出闲置资金 ETF 之后停买 + 买入信号只提醒 + 确认才买（2026-10-07 用户：「现在持仓的etf也要有卖出的button
卖出口持有现金自动停止闲置资金买入etf，如果出现买入信号要提醒 确认之后才会继续买入」）。
停买 = 闲置资金比例 0%（钱留现金，规则每天的核心目标 × 0 = 不买）；买入信号 = 停着时规则的核心目标从「不拿」（0 口）变成「拿」；
确认买入 = 比例回到 100%（盘中马上照规则买，开盘前写的进早上的决策）。
① 执行器（模拟账户）：卖出 → 停买；信号只提醒不买；确认 → 盘中买入、停买与信号清掉；执行器还没算过规则目标额也能卖、不会误报信号；
② now_due / check / lines / 通知；③ 面板：停买卡片、信号横幅、确认买入；④ 命令行。"""
import datetime as dt
import json

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST
from qbreak.live_unified import daily_text

from test_manual_core import AT, _cbook, _conv, _core_orders, _pbook, _write
from test_manual_now import PX, _at, _held, _item, _morning, _paper, _quote


# ────────── ① 执行器（模拟账户）──────────
def test_sell_all_pauses_and_a_rule_buy_signal_only_alerts_until_confirmed():
    r = _paper("pz")
    _morning(r, until=12)
    _write(r.tag, "M-core-sell", **_conv(r.ux.book, kind="sell"))
    r.now["t"] = _at(r, 10, 0)
    r.ux.now_phase(_quote(PX))
    man = r.ux.book["manual"]
    assert man["core_pct"] == 0.0 and "1655.T" not in _held(r)
    assert man["core_pause"] == {"since": r.now["t"].date().isoformat(), "id": "M-core-sell", "ticker": "1655.T"}
    assert "停买闲置资金 ETF" in _item(r, "M-core-sell")["msg"] and "core_signal" not in man
    _morning(r)                                                            # 规则照样想拿 1655（牛市）：不是「不拿 → 拿」→ 没有信号、不买
    st = r.eng.st
    assert st.core_units.get("1655.T", 0) == 0 and "1655.T" not in st.core_plan and "core_signal" not in r.ux.book["manual"]
    assert r.ux.book["core_rule"]["units100"]["1655.T"] > 0
    r.ux.book["core_rule"]["units100"]["1655.T"] = 0                       # 当作上一次决策时规则不拿 1655（熊市 / 拿的是别的 ETF）
    _morning(r)
    sg = r.ux.book["manual"]["core_signal"]
    u100 = r.ux.book["core_rule"]["units100"]["1655.T"]
    assert sg["date"] == r.eng.st.last_date and [x["ticker"] for x in sg["items"]] == ["1655.T"] and sg["items"][0]["units"] == u100 > 0
    assert r.eng.st.core_units.get("1655.T", 0) == 0 and "1655.T" not in r.eng.st.core_plan     # 只提醒，不买
    ev = [e["msg"] for e in r.ux.book["events"] if e["msg"].startswith("★ 闲置资金 ETF 买入信号")]
    assert len(ev) == 1 and "确认后才买" in ev[0] and "liveu.sh manual core --pct 100" in ev[0]
    sm = r.ux.summary()
    assert sm["manual"]["core_signal"] == sg and sm["manual"]["core_pause"]["ticker"] == "1655.T"
    _, short, body = daily_text(sm, r.eng.st, None, True, 1_000_000)
    assert short.endswith("｜★ 闲置资金 ETF 买入信号：确认后才买")
    assert "- 闲置资金买入 ETF：停着（" in body and f"- ★ 闲置资金 ETF 买入信号（{sg['date']} 收盘）：规则想买 1655.T 约 {u100:,} 口" in body
    _write(r.tag, "M-core-go", kind="core", pct=100.0)                      # 确认买入：盘中马上照规则买
    r.now["t"] = _at(r, 10, 0)
    assert MO.now_due(r.tag, r.ux.book, r.now["t"])
    r.ux.now_phase(_quote(PX))
    (o,) = [o for o in _core_orders(r) if o.side == "BUY"]
    assert o.status == "FILLED" and 0 < o.qty <= u100 and o.phase == "now"
    man = r.ux.book["manual"]
    assert man["core_pct"] == 100.0 and "core_pause" not in man and "core_signal" not in man
    assert r.ux.book["core_rule"]["applied"] == 100.0
    _morning(r)
    assert r.eng.st.core_units["1655.T"] == o.qty and abs(r.b.cash() - r.eng.st.cash_jpy) < 1.0
    _, short, _ = daily_text(r.ux.summary(), r.eng.st, None, True, 1_000_000)
    assert "买入信号" not in short


def test_paused_morning_decision_keeps_the_cash_and_the_signal_is_raised_once():
    r = _paper("py")
    _morning(r, until=12)
    _write(r.tag, "M-core-0", kind="core", pct=0.0)                         # 开盘前写的比例 0%（= 停买）：早上的决策照它卖光
    _morning(r)
    assert r.ux.book["manual"]["core_pause"]["ticker"] is None and r.eng.st.core_plan["1655.T"][0] == "SELL"
    _morning(r)
    assert r.eng.st.core_units.get("1655.T", 0) == 0
    r.ux.book["core_rule"]["units100"]["1655.T"] = 0
    _morning(r)
    sg = r.ux.book["manual"]["core_signal"]
    _morning(r)                                                            # 规则一直想拿：同一个信号留着（不重复提醒），也不买
    assert r.ux.book["manual"]["core_signal"] == sg and r.eng.st.core_units.get("1655.T", 0) == 0
    assert len([e for e in r.ux.book["events"] if e["msg"].startswith("★ 闲置资金 ETF 买入信号")]) == 1
    _, short, _ = daily_text(r.ux.summary(), r.eng.st, None, True, 1_000_000)
    assert "买入信号" not in short                                         # 通知只在出现信号的那一天；页面 / 日志一直写到你确认
    k = r.k - 1
    r.eng.core_t100 = {**r.eng.core_t100, "1655.T": 0}                     # 还没确认，规则又不拿了（例如又进熊市）→ 信号撤掉、继续停买
    r.ux._record_core(k)
    assert "core_signal" not in r.ux.book["manual"] and r.ux.book["manual"]["core_pct"] == 0.0
    assert any("买入信号" in e["msg"] and "没了" in e["msg"] for e in r.ux.events)


def test_sell_all_before_the_first_rule_run_and_no_spurious_signal():
    r = _paper("px")
    _morning(r, until=12)
    u0 = r.eng.st.core_units["1655.T"]
    r.ux.book.pop("core_rule")                                             # 更新之后第一次运行之前：执行器还没算过规则目标额
    rec = _conv(r.ux.book, kind="sell")
    assert rec == {"kind": "core", "pct": 0.0, "ticker": "1655.T", "target": 0, "source": "cli"}
    _write(r.tag, "M-core-s0", **rec)
    r.now["t"] = _at(r, 10, 0)
    assert MO.now_due(r.tag, r.ux.book, r.now["t"])
    r.ux.now_phase(_quote(PX))
    (o,) = _core_orders(r)
    assert o.side == "SELL" and o.qty == u0 and o.status == "FILLED"
    cr = r.ux.book["core_rule"]
    assert cr["applied"] == 0.0 and "units100" not in cr
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 30))                 # 已经卖了：面板不再叫
    _morning(r)                                                            # 对账（卖光）→ 决策：上一次没有规则目标额 → 不算信号
    assert r.eng.st.core_units.get("1655.T", 0) == 0 and "core_signal" not in r.ux.book["manual"]
    assert r.ux.book["core_rule"]["units100"]["1655.T"] > 0
    _morning(r)
    assert "core_signal" not in r.ux.book["manual"] and r.eng.st.core_units.get("1655.T", 0) == 0 and not r.ux.blocked


def test_adjust_before_the_first_rule_run_uses_the_estimate():
    """更新之后第一次决策之前（没有 core_rule.units100）也能调仓（2026-10-07 用户「ETF的话也要可以进行调仓 现在的button我看是非活性」）：
    规则目标（比例 100%）先按现在的口数估算 → 盘中照它卖到目标；第二天对账一致，决策写入准确的规则目标，不再调回去。"""
    r = _paper("pa")
    _morning(r, until=12)
    u0 = r.eng.st.core_units["1655.T"]
    r.ux.book.pop("core_rule")                                             # 更新之后第一次运行之前
    c = MO.core_info(r.ux.book, "1655.T")
    assert c["approx"] and c["u100"] == u0 + MO.core_u100_est(0, r.eng.st.core_plan.get("1655.T"))
    tg = (u0 // 2) // 10 * 10
    rec = _conv(r.ux.book, kind="adjust", unit="shares", value=tg)
    assert rec["kind"] == "core" and rec["target"] == tg and 0 < rec["pct"] < 100
    _write(r.tag, "M-core-a1", **rec)
    r.now["t"] = _at(r, 10, 0)
    assert MO.now_due(r.tag, r.ux.book, r.now["t"])
    r.ux.now_phase(_quote(PX))
    (o,) = _core_orders(r)
    assert o.side == "SELL" and o.qty == u0 - tg and o.status == "FILLED"
    cr = r.ux.book["core_rule"]
    assert cr["applied"] == rec["pct"] and "units100" not in cr
    assert not MO.now_due(r.tag, r.ux.book, _at(r, 10, 30))                 # 已经调了：面板不再叫
    assert MO.core_info(r.ux.book, "1655.T") is None                      # 今天调过：等下一次决策（面板显示盘中的单）
    _morning(r)                                                            # 对账 → 决策（这次写入准确的规则目标）
    assert r.eng.st.core_units["1655.T"] == tg and r.ux.book["core_rule"]["units100"]["1655.T"] > 0
    assert r.ux.book["core_rule"]["pct"] == rec["pct"] and not r.ux.blocked
    _morning(r)
    assert abs(r.eng.st.core_units["1655.T"] - tg) <= 0.1 * u0 and not r.ux.blocked   # 再平衡带以内不调回去


# ────────── ② now_due / check / lines ──────────
def test_now_due_check_and_lines_while_paused():
    at = lambda h, m: dt.datetime(2026, 10, 6, h, m, tzinfo=JST)        # noqa: E731
    b = _cbook()
    b["core_rule"] = {}
    b["manual"]["core_pct"] = 0.0                                         # 执行器还没算过规则目标额 + 卖出全部
    assert MO.now_due("pq", b, at(10, 0)) and not MO.now_due("pq", b, at(8, 30))
    b["core_rule"] = {"applied": 0.0}
    assert not MO.now_due("pq", b, at(10, 0))                              # 盘中已经卖了
    b["core_rule"] = {"defer": "2026-10-06"}
    assert not MO.now_due("pq", b, at(10, 0))
    b["core_rule"] = {}
    b["manual"]["core_pct"] = 50.0
    assert MO.now_due("pq", b, at(10, 0))                                  # 不是卖出全部：按估算的规则目标额照样调（第 9 轮起）
    b["core_rule"] = {"defer": "2026-10-06"}
    assert not MO.now_due("pq", b, at(10, 0))                              # 今天说了「明天再调」
    b["core_rule"] = {}
    b["manual"]["core_pct"] = 0.0
    b["state"]["core_units"] = {"1655.T": 0}
    assert not MO.now_due("pq", b, at(10, 0))                              # 没拿着
    b = _cbook(pct=0.0)
    assert MO.check(_conv(b, kind="sell"), b) == "已经在停买闲置资金 ETF（比例 0%）：1655.T 在执行器下一次运行时卖出"
    assert MO.check(MO.normalize({"kind": "core", "pct": 100}), b) is None
    assert MO.core_pct_now(None, b) == 0.0
    sm = {"core_pct": 0.0, "core_pause": {"since": "2026-10-06", "id": "x", "ticker": "1655.T"},
          "core_signal": {"date": "2026-10-08", "items": [{"ticker": "1545.T", "units": 110, "px": 20_700.0, "yen": 2_277_000}]}}
    assert MO.lines(sm)[:2] == [
        "- 闲置资金买入 ETF：停着（2026-10-06 起，卖出 1655.T）：钱留现金；出现买入信号会提醒，你确认才买",
        "- ★ 闲置资金 ETF 买入信号（2026-10-08 收盘）：规则想买 1545.T 约 110 口（约 ¥2,277,000）："
        "确认后才买（面板「确认买入」，或 liveu.sh manual core --pct 100）"]
    assert MO.lines({"core_pct": 0.0, "core_pause": {"since": "2026-10-06"}}) == [
        "- 闲置资金买入 ETF：停着（2026-10-06 起）：钱留现金；出现买入信号会提醒，你确认才买"]
    assert MO.signal_text(None) == "规则想买核心 ETF"


# ────────── ③ 面板 ──────────
def _paused(sig: bool = False) -> dict:
    b = _pbook(pct=0.0)
    b["state"]["core_units"] = {"1655.T": 0}
    b["manual"]["core_pause"] = {"since": "2026-10-06", "id": "M-x", "ticker": "1655.T"}
    if sig:
        b["manual"]["core_signal"] = {"date": "2026-10-05", "items": [{"ticker": "1655.T", "units": 1140, "px": 700.0, "yen": 798_000}]}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def test_panel_paused_card_signal_banner_and_confirm():
    _paused()
    h = panel.render("paper", "tok", now=AT)
    assert "<section class='card' id='core'>" in h and "<b>停买中</b>（2026-10-06 起，你卖出 1655.T）" in h
    assert "规则现在：想拿 1655.T 约 1,140 口" in h and "出现买入信号（规则从「不拿」变成「拿」）会提醒你" in h
    assert "data-act='core-resume'>确认买入（恢复照规则）</button>" in h and "★ 买入信号" not in h and "ETF 出现买入信号" not in h
    _paused(sig=True)
    h = panel.render("paper", "tok", now=AT)
    assert ("<div class='neg small'>★ 闲置资金 ETF 出现买入信号（2026-10-05 收盘）：规则想买 1655.T 约 1,140 口（约 ¥798,000）"
            " → 确认后才买（见下面「闲置资金」）</div>") in h
    assert "<section class='card warn' id='core'>" in h and "★ 买入信号（2026-10-05 收盘）" in h
    ok, msg, rec = panel.submit({"book": "paper", "kind": "core", "pct": 100}, AT)
    assert ok and rec["pct"] == 100.0 and msg.startswith("已写：确认买入（闲置资金比例 0% → 100%）→ 马上（盘中）照规则买入核心 ETF")
    h = panel.render("paper", "tok", now=AT)
    assert "data-act='core-resume'" not in h and "有一条闲置资金比例的指令在处理" in h
    ok, msg, _ = panel.submit({"book": "paper", "kind": "core", "pct": 100}, AT)
    assert not ok and "闲置资金比例现在就是 100%：不用改" in msg              # 还没读的那条算现在的比例
    MO.requests_path("paper").unlink()
    b = _paused()
    b["core_rule"]["units100"] = {"1655.T": 0}                             # 规则现在不拿（熊市）
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    assert "规则现在：不拿核心 ETF（熊市 / 没有闲置资金）" in panel.render("paper", "tok", now=AT)
    b.pop("core_rule")
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    assert "规则现在：执行器下一次运行之后显示" in panel.render("paper", "tok", now=AT)


def test_panel_sell_message_and_the_sell_button_while_paused_with_units_left():
    b = _pbook(pct=0.0)                                                    # 停着、口数还在（例如开盘的卖单还没成交）
    b["manual"]["core_pause"] = {"since": "2026-10-06", "id": "M-x", "ticker": "1655.T"}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    h = panel.render("paper", "tok", now=AT)
    assert "data-act='core-sell'" in h and "停买中" in h
    ok, msg, _ = panel.submit({"book": "paper", "kind": "sell", "ticker": "1655"}, AT)
    assert not ok and "已经在停买闲置资金 ETF（比例 0%）" in msg


# ────────── ④ 命令行 ──────────
def test_cli_etf_sell_all_pauses_and_core_100_confirms(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    _pbook()
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    assert run.main(["manual", "sell", "1655", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "卖出全部 1655.T（之后停买闲置资金 ETF）" in out and "按最近收盘" not in out
    assert ("核心 ETF 马上（盘中）卖出；之后停买闲置资金 ETF（钱留现金；出现买入信号会提醒你，确认才买："
            "bash scripts/liveu.sh manual core --pct 100）") in out
    assert run.main(["manual", "core", "--pct", "100", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "确认买入：停买结束，核心 ETF 马上（盘中）照规则买入（闲置资金比例 0% → 100%）" in out
    assert [(r["kind"], r["pct"]) for r in MO.read_all("paper")] == [("core", 0.0), ("core", 100.0)]


def test_cli_manual_list_shows_the_pause_and_what_the_rule_wants(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    b = _paused(sig=True)
    b["core_rule"]["units100"] = {"1545.T": 110, "1655.T": 0}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    assert run.main(["manual", "list", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "闲置资金买入 ETF：停着（2026-10-06 起，卖出 1655.T）：钱留现金；出现买入信号会提醒，你确认才买" in out
    assert "★ 闲置资金 ETF 买入信号（2026-10-05 收盘）：规则想买 1655.T 约 1,140 口（约 ¥798,000）" in out
    assert "规则现在：想拿 1545.T 约 110 口（确认买入：bash scripts/liveu.sh manual core --pct 100）" in out
    b["core_rule"]["units100"] = {"1655.T": 0}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    run.main(["manual", "list", "--broker", "paper"])
    assert "规则现在：不拿核心 ETF（确认买入" in capsys.readouterr().out
    b.pop("core_rule")
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    run.main(["manual", "list", "--broker", "paper"])
    assert "规则现在：执行器下一次运行之后显示" in capsys.readouterr().out
