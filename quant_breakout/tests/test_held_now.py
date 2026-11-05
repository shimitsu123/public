"""今天已成交的买卖马上算进「现在拿着什么」（qbreak/live_ops.held_now；2026-10-16 用户：「我今天卖出了纳指etf然后买了对冲的
但是持仓里面并没有反应」）：账本仍在下个交易日 07:40 对账后才正式记账（执行器不改）；这里是只读的对账前预计 ——
算哪些成交、费用与损益照引擎、日历文字、幂等不改入参、对账之后自然归零（不重复计算）、执行器不读它。"""
import copy
import datetime as dt
import json

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import names as NM
from qbreak import paths
from qbreak.calendar_jp import JST
from qbreak.fees import DEFAULT_BROKER, etf_cost, side_fee

AT = dt.datetime(2026, 10, 16, 16, 0, tzinfo=JST)                      # 10/16（周五）收盘后
SELL_PX, BUY_PX = 237.52872610168458, 1485.7424999999998


def _b1016() -> dict:
    """2026-10-16 模拟账户的账本（字面量，照数据副本的值）：10/15 决策；09:43 盘中卖出 1545 全部 4,110 口、买入 1482 650 口（都已成交），
    早上的两笔单已撤；state 还是 10/15 收盘的（1545 4,110 口、现金 ¥191.68）。"""
    st = {"last_date": "2026-10-15", "cash_jpy": 191.67823918163776, "pos": {}, "pending_exit": {},
          "core_units": {"1655.T": 0, "1545.T": 4110, "2845.T": 0, "1482.T": 0},
          "core_last": {"1655.T": 868.4000244140625, "1545.T": 236.39999389648438, "2845.T": 3699.0, "1482.T": 1483.0},
          "history": [["2026-10-14", 1001798.67, 191.68, 0.0, 158.284], ["2026-10-15", 971795.65, 191.68, 0.0, 157.934]],
          "core_trades": [["2026-10-01", "1545.T", "BUY", 4110, 241.9, 341.0]], "trades": [], "plan": {}, "core_plan": {}}
    orders = [
        {"cid": "U2026-10-15-SELL-1545.T", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 4110, "sent_qty": 4110,
         "filled_qty": 0, "filled_px": 0.0, "status": "CANCELLED", "reason": "核心 ETF 调整", "phase": "morning", "limit": None,
         "ref_px": 236.39999389648438, "decided_on": "2026-10-15"},
        {"cid": "U2026-10-15-BUY-1482.T", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 679, "sent_qty": 0,
         "filled_qty": 0, "filled_px": 0.0, "status": "CANCELLED", "reason": "核心 ETF 调整", "phase": "open", "limit": 1512.0,
         "ref_px": 1483.0, "decided_on": "2026-10-15"},
        {"cid": "U2026-10-15-SELL-1545.T-N094306", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 4110, "sent_qty": 4110,
         "filled_qty": 4110, "filled_px": SELL_PX, "status": "FILLED", "reason": "fix_fund", "phase": "now", "limit": None,
         "ref_px": 237.60000610351562, "decided_on": "2026-10-15"},
        {"cid": "U2026-10-15-BUY-1482.T-N094306", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 650, "sent_qty": 650,
         "filled_qty": 650, "filled_px": BUY_PX, "status": "FILLED", "reason": "core_fix", "phase": "now", "limit": 1492.0,
         "ref_px": 1485.0, "decided_on": "2026-10-15"}]
    return {"state": st, "orders": orders, "broker": "PaperBroker",
            "core_rule": {"px": {"1482.T": 1483.0, "1545.T": 236.4}, "lot": {"1482.T": 1, "1545.T": 10}},
            "manual": {"items": {}, "core_fix": {"1482.T": 655}, "core_pct": 100.0}}


def _cfee(t: str, side: str, notional: float) -> float:
    return side_fee(etf_cost(DEFAULT_BROKER["JP"], t, "JP"), side)(notional)


# ────────── 1. 10/16 的真实状态 ──────────
def test_1016_paper_book_projects_the_two_fills():
    b = _b1016()
    pj = LO.held_now(b, "paper", now=AT)
    assert pj["has"] and pj["fill_day"] == "2026-10-16" and pj["settle_day"] == "2026-10-19"
    assert abs(pj["cash"] - 10020.1175) < 1e-3 and pj["cash_ledger"] == b["state"]["cash_jpy"]
    assert pj["core_units"]["1545.T"] == 0 and pj["core_units"]["1482.T"] == 650
    assert pj["state"]["core_units"] == pj["core_units"] and pj["state"]["cash_jpy"] == pj["cash"]
    assert pj["sold_out"] == ["1545.T"] and pj["new"] == ["1482.T"]
    assert [f["side"] for f in pj["fills"]] == ["SELL", "BUY"]                 # 对账的顺序：先卖后买
    cost = 4110 * 241.9 + 341.0                                                 # 移动平均成本（含买入手续费）
    fee = _cfee("1545.T", "SELL", 4110 * SELL_PX)
    exp = 4110 * SELL_PX - fee - cost
    assert abs(pj["realized"] - exp) < 1e-6 and not pj["realized_partial"] and exp < 0
    assert abs(pj["equity"] - 973970.1) < 0.5 and pj["equity_ledger"] == 971795.65
    assert "下个交易日 10/19（周一）07:40" in pj["note"] and "明早" not in pj["note"]
    assert pj["note"].startswith("含今天已成交")
    assert not pj["pending"] and not pj["missed"] and pj["paper"]
    for t, x in pj["by_ticker"].items():
        assert NM.label(t) in x["text"] and "明早" not in x["text"]
    assert pj["by_ticker"]["1545.T"]["text"] == ("1545 纳斯达克 100：今天已卖出全部 4,110 口 @ ¥237.53"
                                                 f"（已实现约 −¥{abs(exp):,.0f}；下个交易日 10/19（周一）07:40 对账后正式记账）")
    assert pj["by_ticker"]["1482.T"]["text"] == ("1482 对冲版美国 7〜10 年国债：今天买进 650 口 @ ¥1,485.74"
                                                 "（下个交易日 10/19（周一）07:40 对账之后才算持仓）")
    assert pj["by_ticker"]["1482.T"]["net"] == 650 and pj["by_ticker"]["1545.T"]["net"] == -4110
    # 只换这几项：history / trades / core_trades / plan 不编造
    for k in ("history", "core_trades", "trades", "plan", "core_plan", "last_date", "core_last"):
        assert pj["state"][k] == b["state"][k]


def test_core_cost_mismatch_gives_none_pnl_and_partial():
    b = _b1016()
    b["state"]["core_trades"] = [["2026-10-01", "1545.T", "BUY", 1000, 241.9, 341.0]]   # 记录对不上现在的口数 → 成本不知道
    pj = LO.held_now(b, "paper", now=AT)
    assert pj["realized"] is None and pj["realized_partial"]
    assert "已实现" not in pj["by_ticker"]["1545.T"]["text"] and "今天已卖出全部 4,110 口" in pj["by_ticker"]["1545.T"]["text"]


# ────────── 2. 对账前的投影 = 第二天早上对账之后的账本 ──────────
def test_projection_matches_next_morning_reconcile():
    from test_manual_now import PX, _at, _morning, _paper, _quote, _req
    r = _paper("paper_hn")
    _morning(r, until=14)
    _req(r, kind="trim", ticker="A.T", pct=12.0)
    _req(r, kind="buy", ticker="B.T", unit="rule")
    r.now["t"] = _at(r, 10, 0)
    res = r.ux.now_phase(_quote(PX))
    assert res["placed"] == 2
    bf = paths.state_dir() / "book_paper_hn.json"
    book = json.loads(bf.read_text(encoding="utf-8"))
    pj = LO.held_now(book, "paper_hn", now=_at(r, 10, 30))
    assert pj["has"] and not pj["pending"]                                     # 早上没有别的单在等：投影 = 全部成交
    assert {f["kind"] for f in pj["fills"]} == {"stock", "core"}
    assert pj["new"] == ["B.T"] and pj["pos"]["A.T"]["shares"] == 100 and pj["pos"]["B.T"]["stop_px"] is None
    _morning(r)
    nb = json.loads(bf.read_text(encoding="utf-8"))
    nst = nb["state"]
    assert {t: int(p["shares"]) for t, p in nst["pos"].items()} == {t: int(p["shares"]) for t, p in pj["pos"].items()}
    assert {t: int(u) for t, u in nst["core_units"].items() if int(u)} == {t: int(u) for t, u in pj["core_units"].items() if int(u)}
    assert abs(float(nst["cash_jpy"]) - pj["cash"]) < 1e-6
    assert LO.held_now(nb, "paper_hn", now=_at(r, 10, 0))["has"] is False      # 对账之后不重复计算


# ────────── 3-7. 算哪些成交 ──────────
def _tbook(orders: list, pos: dict | None = None, core: dict | None = None, pex: dict | None = None) -> dict:
    st = {"last_date": "2026-10-15", "cash_jpy": 500_000.0, "pos": pos or {}, "pending_exit": pex or {},
          "core_units": core or {}, "history": [["2026-10-15", 1_000_000.0, 500_000.0, 0, 150]]}
    for i, o in enumerate(orders):
        o.setdefault("cid", f"U2026-10-15-{o['side']}-{o['ticker']}-{i}")
        o.setdefault("decided_on", "2026-10-15")
        o.setdefault("kind", "stock")
        o.setdefault("phase", "morning")
    return {"state": st, "orders": orders, "broker": "TachibanaBroker"}


def _o(t="7203.T", side="BUY", status="FILLED", qty=100, filled=0, px=0.0, **kw) -> dict:
    return {"ticker": t, "side": side, "status": status, "qty": qty, "sent_qty": qty, "filled_qty": filled, "filled_px": px, **kw}


AT_TB = dt.datetime(2026, 10, 16, 15, 50, tzinfo=JST)


def test_tachibana_sent_morning_order_counts_snapshot_fills():
    b = _tbook([_o(status="SENT", qty=300, ref_px=2500.0)])
    snap = {"fills_at": "2026-10-16T15:45:00+09:00",
            "fills": [{"cid": "U2026-10-15-BUY-7203.T-0", "filled_qty": 100, "avg_px": 2490.0}]}
    pj = LO.held_now(b, "tachibana", now=AT_TB, snap=snap)
    assert pj["has"] and [(f["qty"], f["px"], f["src"]) for f in pj["fills"]] == [(100, 2490.0, "snapshot")]
    assert pj["pending"][0]["left"] == 200 and pj["pos"]["7203.T"]["shares"] == 100
    assert "以立花为准" in pj["note"] and "现金是约数" in pj["note"]
    assert "今天还没确认成交的部分不算在里面（已经收盘" in pj["note"] and "还在等成交" not in pj["note"]   # 15:50：已经收盘
    assert not pj["paper"]
    old = {**snap, "fills_at": "2026-10-15T15:45:00+09:00"}                   # 前一天的快照：不算
    pj = LO.held_now(b, "tachibana", now=AT_TB, snap=old)
    assert pj["has"] is False and pj["pending"][0]["left"] == 300


def test_only_sent_is_pending_and_state_equals_ledger():
    b = _tbook([_o(status="SENT", qty=300, ref_px=2500.0)])
    pj = LO.held_now(b, "tachibana", now=AT_TB, snap={})
    assert pj["has"] is False and [p["left"] for p in pj["pending"]] == [300]
    assert pj["state"] == b["state"] and pj["cash"] == 500_000.0 and pj["equity"] == 1_000_000.0 and pj["pos"] == {}


def test_filled_without_qty_uses_sent_qty():
    b = _tbook([_o(status="FILLED", qty=200, filled=0, px=2500.0)])
    pj = LO.held_now(b, "tachibana", now=AT_TB, snap={})
    assert [(f["qty"], f["src"]) for f in pj["fills"]] == [(200, "sent_qty")] and pj["pos"]["7203.T"]["shares"] == 200


def test_sending_and_error_never_count():
    b = _tbook([_o(status="SENDING", filled=100, px=2500.0), _o(t="6758.T", status="ERROR", filled=100, px=3000.0)])
    pj = LO.held_now(b, "tachibana", now=AT_TB, snap={})
    assert pj["has"] is False and {p["ticker"] for p in pj["pending"]} == {"7203.T", "6758.T"}
    assert pj["state"] == b["state"]


def test_cancelled_after_partial_fill_counts_the_filled_part():
    b = _tbook([_o(status="CANCELLED", qty=300, filled=50, px=2500.0)])
    pj = LO.held_now(b, "tachibana", now=AT_TB, snap={})
    assert pj["has"] and pj["fills"][0]["qty"] == 50 and pj["pos"]["7203.T"]["shares"] == 50 and not pj["pending"]


def test_missing_price_falls_back_to_limit_and_marks_approx():
    b = _tbook([_o(status="FILLED", qty=100, filled=100, px=0.0, limit=2550.0, ref_px=2500.0)])
    pj = LO.held_now(b, "tachibana", now=AT_TB, snap={})
    assert pj["fills"][0]["px"] == 2550.0 and pj["fills"][0]["approx"] and pj["approx"]


# ────────── 8. 个股 ──────────
def test_stock_new_buy_full_sell_trim_and_add():
    pos = {"6758.T": {"shares": 200, "entry_px": 3000.0, "entry_date": "2026-09-01", "stop_px": 2800.0, "last_close": 3050.0},
           "8035.T": {"shares": 200, "entry_px": 3000.0, "entry_date": "2026-09-01", "stop_px": 2800.0, "last_close": 3050.0},
           "9984.T": {"shares": 200, "entry_px": 3000.0, "entry_date": "2026-09-01", "stop_px": 2800.0, "last_close": 3050.0}}
    b = _tbook([_o("7203.T", "BUY", qty=100, filled=100, px=2500.0, reason="manual_buy", phase="now"),
                _o("6758.T", "SELL", qty=200, filled=200, px=3100.0, reason="manual_sell", phase="now"),
                _o("8035.T", "SELL", qty=100, filled=100, px=3100.0, reason="manual_trim", phase="now"),
                _o("9984.T", "BUY", qty=100, filled=100, px=3200.0, reason="manual_add", phase="now")],
               pos=pos, pex={"6758.T": "manual"})
    b["broker"] = "PaperBroker"
    pj = LO.held_now(b, "paper", now=AT)
    p = pj["pos"]
    assert p["7203.T"]["stop_px"] is None and p["7203.T"]["today"] is True and p["7203.T"]["entry_date"] == "2026-10-16"
    assert p["7203.T"]["shares"] == 100 and pj["new"] == ["7203.T"]
    assert "6758.T" not in p and "6758.T" not in pj["state"]["pending_exit"] and pj["sold_out"] == ["6758.T"]
    f = next(x for x in pj["fills"] if x["ticker"] == "6758.T")
    assert abs(f["pnl"] - ((3100.0 - 3000.0) * 200 - MO.fee_jp(200 * 3100.0) - MO.fee_jp(200 * 3000.0))) < 1e-9   # = unified._close
    assert p["8035.T"]["shares"] == 100 and p["8035.T"]["entry_px"] == 3000.0                   # 部分卖出：入场价不变
    assert p["9984.T"]["shares"] == 300 and abs(p["9984.T"]["entry_px"] - (3000.0 * 200 + 3200.0 * 100) / 300) < 1e-9
    assert pos["6758.T"]["shares"] == 200 and pos["9984.T"]["entry_px"] == 3000.0               # 入参没变
    tx = pj["by_ticker"]
    assert tx["8035.T"]["text"] == f"{NM.label('8035.T')}：今天卖出 100 股，现在 100 股（对账前）"
    assert tx["7203.T"]["text"].startswith(f"{NM.label('7203.T')}：今天买进 100 股 @ ¥2,500.00（")
    assert "现在 300 股" in tx["9984.T"]["text"]
    assert [f["side"] for f in pj["fills"]] == ["SELL", "SELL", "BUY", "BUY"]


# ────────── 9. 日历 ──────────
def test_calendar_words():
    b = _b1016()
    pj = LO.held_now(b, "paper", now=dt.datetime(2026, 10, 17, 12, 0, tzinfo=JST))   # 周六
    assert pj["note"].startswith("含 10/16（周五）已成交（下个交易日 10/19（周一）07:40")
    assert pj["by_ticker"]["1482.T"]["text"].startswith("1482 对冲版美国 7〜10 年国债：10/16（周五）买进 650 口")
    pj = LO.held_now(b, "paper", now=dt.datetime(2026, 10, 18, 12, 0, tzinfo=JST))   # 周日
    assert "（明早 07:40 对账后正式记账）" in pj["note"]
    pj = LO.held_now(b, "paper", now=dt.datetime(2026, 10, 19, 7, 0, tzinfo=JST))
    assert "（今天 07:40 对账后正式记账）" in pj["note"] and not pj["missed"]
    pj = LO.held_now(b, "paper", now=dt.datetime(2026, 10, 19, 9, 0, tzinfo=JST))     # 早上的运行没做完
    assert pj["missed"] and "早上的运行还没完成" in pj["note"] and pj["has"]
    assert "下一次执行器运行对账后正式记账" in pj["by_ticker"]["1545.T"]["text"]           # 时点不以数字结尾 → 不加空格（复核）
    assert "下一次执行器运行 对账" not in pj["by_ticker"]["1545.T"]["text"] and pj["when_sp"] == "下一次执行器运行"
    pj = LO.held_now(b, "paper", now=dt.datetime(2026, 10, 15, 16, 0, tzinfo=JST))   # 成交日之前：不可能有成交
    assert pj["has"] is False
    h = _b1016()                                                               # 祝日：10/30（周五）决策 → 11/2 成交 → 11/3 文化の日 → 11/4
    h["state"]["last_date"] = "2026-10-30"
    for o in h["orders"]:
        o["decided_on"] = "2026-10-30"
    pj = LO.held_now(h, "paper", now=dt.datetime(2026, 11, 2, 16, 0, tzinfo=JST))
    assert pj["settle_day"] == "2026-11-04" and "下个交易日 11/4（周三）07:40" in pj["note"]


# ────────── 10-12. 幂等、对账后归零、执行器不读 ──────────
def test_idempotent_and_does_not_mutate():
    b = _b1016()
    b0 = copy.deepcopy(b)
    pj = LO.held_now(b, "paper", now=AT)
    assert b == b0
    again = LO.held_now(pj["book"], "paper", now=AT)
    assert again["cash"] == pj["cash"] and again["core_units"] == pj["core_units"] and again["state"] is pj["book"]["state"]
    assert again["fills"] == pj["fills"] and again["book"] is pj["book"]
    json.dumps(pj["book"], ensure_ascii=False)                                  # 能存 / 能传


def test_after_reconcile_nothing_to_add():
    b = _b1016()
    b["state"]["last_date"] = "2026-10-16"                                      # 对账：这批单删掉、推进 last_date
    b["orders"] = [{"cid": "U2026-10-16-BUY-1482.T", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 5, "sent_qty": 0,
                    "filled_qty": 0, "status": "PLANNED", "decided_on": "2026-10-16", "phase": "morning"}]
    pj = LO.held_now(b, "paper", now=dt.datetime(2026, 10, 19, 8, 0, tzinfo=JST))
    assert pj["has"] is False and pj["state"] is b["state"]


def test_bad_book_never_raises():
    assert LO.held_now(None, "paper")["has"] is False
    assert LO.held_now({"state": {"last_date": "x"}}, "paper")["has"] is False
    b = _b1016()
    b["orders"].append({"ticker": "1545.T", "side": "SELL", "decided_on": "2026-10-15", "status": "FILLED", "filled_qty": "?"})
    assert LO.held_now(b, "paper", now=AT)["core_units"]["1545.T"] == 0


def test_executor_never_reads_the_projection():
    for f in ("live_unified.py", "unified.py"):
        assert "held_now" not in (paths.PROJECT_ROOT / "qbreak" / f).read_text(encoding="utf-8")
