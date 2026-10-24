"""固定口数还差几口（2026-10-16，事后；整合复核 2 的已知限制）：固定 1482 N 口、盘中现金只够买一部分（执行器 fix_buy「现金只够 q 口（还差 …：
下一次决策照它调）」）→ 固定口数记为已照它调（fix_applied），以前交易页（收盘后 / 周末）没有那只的一行、也不算进「另有 N 条等 …」，
执行器下一次决策却照旧去补。现在 outlook 补一行 fix:<票>（live_ops.fix_short；与 panel._trade_split / 09:30 自检 / 执行器汇总同一个判断），
只在执行器真的会去买时：HALT 中 → 等 HALT 解除后；有没处理完的「全部换成」/ 这只还有没读的固定口数 / 还在调的 / 还有没结束的单 /
钱连一单元都不够 → 不写；不和已有的 fix:<票> 重复。"""
import json

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths

from test_core_etf_restore import _morning, _paper2, _w
from test_corefix_now import _disk
from test_manual_now import _at, _quote
from test_trade_today import _badge_ok, _parts

PXQ = {"A.T": 1000.0, "B.T": 1500.0, "1545.T": 700.0, "1482.T": 1000.0}
LAB = "1482 对冲版美国 7〜10 年国债"


def _short():
    """1545 照规则拿满 → 10:30 固定 1482 U 口（比总权益多 50 口）→ 盘中卖光 1545、现金只够买 q 口（还差 U − q 口）。"""
    r = _paper2()
    _morning(r, 8)
    eq = r.eng.st.cash_jpy + sum(u * 700 for u in r.eng.st.core_units.values())
    u = int(eq / 1000) + 50
    _w(r.tag, "M-fix", kind="corefix", ticker="1482.T", units=u)
    r.now["t"] = _at(r, 10, 30)
    r.ux.now_phase(_quote(PXQ))
    b = _disk(r)
    q = int(LO.held_now(b, r.tag, now=_at(r, 15, 45))["core_units"]["1482.T"])
    assert 0 < q < u and MO.fix_applied(b)["1482.T"] == u and not MO.corefix_pending(b, r.tag, _at(r, 15, 45))
    return r, u, q


def _rows(b, tag, now, **kw):
    ol = LO.outlook(b, MO.unseen(tag, b), now, tag=tag, **kw)
    return [x for x in ol["rows"] if x.get("ticker") == "1482.T" and x["kind"] == "instr"]


def test_shortfall_row_after_close_counts_and_executor_buys_it():
    r, u, q = _short()
    T = _at(r, 15, 45)
    nd = _at(r, 9, 0, days=1)
    b = _disk(r)
    xs = _rows(b, r.tag, T)
    assert len(xs) == 1 and xs[0]["ref"] == "fix:1482.T" and xs[0]["state"] == "later" and xs[0]["act_at"] == nd
    want = (f"{LAB} 固定 {u:,} 口：现在 {q:,} 口（含今天已成交），还差 {u - q:,} 口 → "
            f"{LO.md_wd(nd.date())}07:40 的决策照它调（开盘买）")
    assert xs[0]["what"] == want                                              # 以前：没有这一行
    html = panel.render(r.tag, "t" * 40, T)
    _top, later, _ended = _parts(html)
    assert want in later and f"<span class='chip'>还差 {u - q:,} 口</span>" in later
    assert f"另有 1 条等 {LO.md_wd(nd.date())}开盘" in later
    assert _badge_ok(html, r.tag, T) == 1                                     # 以前 0
    _morning(r)                                                               # 下一次决策：执行器照固定口数补
    d = r.ux.book["state"]["last_date"]
    assert [(o.side, o.qty) for o in r.ux.orders if o.decided_on == d and o.ticker == "1482.T"] == [("BUY", u - q)]
    b = _disk(r)
    assert not [x for x in _rows(b, r.tag, _at(r, 8, 0)) if x["ref"] == "fix:1482.T"]   # 那笔单自己有一行：不重复


def test_halt_waits_for_release():
    r, u, q = _short()
    T = _at(r, 15, 45)
    paths.halt_file().write_text("test", encoding="utf-8")
    try:
        b = _disk(r)
        xs = _rows(b, r.tag, T)
        assert len(xs) == 1 and xs[0]["cls"] == "halt" and xs[0]["what"].endswith("→ HALT 解除后的决策照它调（开盘买）")
        _top, later, _ = _parts(panel.render(r.tag, "t" * 40, T))
        assert "另有 1 条等 HALT 解除后" in later
    finally:
        paths.halt_file().unlink()


def test_before_the_decision_it_is_today():
    r, u, q = _short()
    T = _at(r, 7, 0, days=1)                                                  # 下一个交易日 07:00：今天的决策还没做
    xs = _rows(_disk(r), r.tag, T)
    assert len(xs) == 1 and xs[0]["state"] == "will" and xs[0]["act_at"] == _at(r, 9, 0, days=1)
    assert xs[0]["what"].endswith("→ 今天 07:40 的决策照它调（09:00 开盘买）")


def test_no_row_when_the_executor_will_not_buy():
    r, u, q = _short()
    T = _at(r, 15, 45)
    b = _disk(r)
    assert LO.fix_short(b, T, r.tag)
    b0 = json.loads(json.dumps(b))
    b0["state"]["cash_jpy"] -= LO.held_now(b, r.tag, now=T)["state"]["cash_jpy"] - 500.0   # 含今天成交的投影只剩 500 円
    assert LO.fix_short(b0, T, r.tag, cash=1005.0 * 1.006)                    # 一单元（1,000 円 ×(1+0.5%)）够
    assert not LO.fix_short(b0, T, r.tag, cash=0.0)                           # 钱连一单元都不够（1545 已经卖光，没有可卖的核心 ETF）
    b2 = json.loads(json.dumps(b))
    b2["core_rule"].pop("fix_applied")
    b2["manual"]["core_fix"]["1482.T"] = q                                    # 固定口数已经拿够
    assert not LO.fix_short(b2, T, r.tag)
    _w(r.tag, "M-all", kind="buy", ticker="A.T", fund="all", at="2026-01-22T15:00:00+09:00")   # 「全部换成」那次决策取消全部固定口数
    assert MO.live_allin(r.tag, b) and not LO.fix_short(b, T, r.tag)
    assert not [x for x in _rows(b, r.tag, T) if x["ref"] == "fix:1482.T"]


def test_no_duplicate_with_unread_or_pending_corefix():
    r, u, q = _short()
    T = _at(r, 15, 45)
    _w(r.tag, "M-fix2", kind="corefix", ticker="1482.T", units=u, at="2026-01-22T15:40:00+09:00")   # 还没读、同一个口数
    b = _disk(r)
    xs = _rows(b, r.tag, T)
    assert [x["ref"] for x in xs] == ["M-fix2"]                               # 那一行就是它
    MO.Manual(b, r.tag, lambda: T).ingest()                                    # 读了：口数一样 → 固定口数已照它调，又回到还差的那一行
    xs = _rows(b, r.tag, T)
    assert [x["ref"] for x in xs] == ["fix:1482.T"] and "还差" in xs[0]["what"]
    _w(r.tag, "M-fix3", kind="corefix", ticker="1482.T", units=u + 10, at="2026-01-22T15:41:00+09:00")
    MO.Manual(b, r.tag, lambda: T).ingest()                                    # 新的口数、还没照它调：只有 corefix_pending 那一行
    xs = _rows(b, r.tag, T)
    assert [x["ref"] for x in xs] == ["fix:1482.T"] and "还没照它调" in xs[0]["what"] and "还差" not in xs[0]["what"]
