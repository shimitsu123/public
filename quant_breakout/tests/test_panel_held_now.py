"""面板 / 手机 / 现价 / 提交 / 凑钱按「含今天已成交」（live_ops.held_now；2026-10-16 用户：「我今天卖出了纳指etf然后买了对冲的
但是持仓里面并没有反应」）：10/16 16:00 的模拟账户 —— 1545 纳斯达克 100 盘中卖光 4,110 口、1482 对冲版美国 7〜10 年国债 买进 650 口，
账本（state）要到 10/19（周一）07:40 才对账。页面显示投影、写指令前窄的守卫；执行器、名额、存在性仍按账本。"""
import copy
import datetime as dt
import json
import re

from qbreak import manual_orders as MO
from qbreak import names as NM
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_held_now import _b1016

AT = dt.datetime(2026, 10, 16, 16, 0, tzinfo=JST)                      # 10/16（周五）收盘后
SETTLE = "下个交易日 10/19（周一）07:40"


def _write(b: dict, tag: str = "paper") -> dict:
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def _book() -> dict:
    return _write(_b1016())


def _book_stocks() -> dict:
    """再加两只个股：6758.T 账本 400 股、今天盘中减了 200 股；7203.T 今天盘中新买 100 股（账本里还没有）。"""
    b = _b1016()
    b["state"]["pos"] = {"6758.T": {"shares": 400, "entry_px": 3000.0, "entry_date": "2026-09-01", "stop_px": 2800.0,
                                    "last_close": 3050.0, "peak": 3100.0, "hold": 20}}
    b["state"]["history"][-1][1] += 400 * 3050.0
    b["state"]["cash_jpy"] = 400_000.0
    b["orders"] += [
        {"cid": "U2026-10-15-SELL-6758.T-N100000", "ticker": "6758.T", "side": "SELL", "kind": "stock", "qty": 200, "sent_qty": 200,
         "filled_qty": 200, "filled_px": 3060.0, "status": "FILLED", "reason": "manual_trim", "phase": "now", "decided_on": "2026-10-15"},
        {"cid": "U2026-10-15-BUY-7203.T-N100000", "ticker": "7203.T", "side": "BUY", "kind": "stock", "qty": 100, "sent_qty": 100,
         "filled_qty": 100, "filled_px": 2500.0, "status": "FILLED", "reason": "manual_buy", "phase": "now", "decided_on": "2026-10-15"}]
    return _write(b)


def _text(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).replace("&amp;", "&")


def _common(h: str) -> None:
    t = _text(h)
    assert "1545 纳斯达克 100：今天已卖出全部 4,110 口" in t
    assert not re.search(r"data-act='core-sell' data-t='1545\.T'", h)            # 卖光的不再给卖出按钮
    assert "1482 对冲版美国 7〜10 年国债" in t and "650 口" in t and "今天买进 650 口" in t
    assert "¥10,020" in t and "¥973,970" in t and "含今天已成交" in t and "账本 ¥971,796" in t
    assert SETTLE in t and "明早 07:40" not in t


def test_render_shows_todays_fills():
    b = _book()
    b0 = copy.deepcopy(b)
    h = panel.render("paper", "t" * 40, AT)
    _common(h)
    t = _text(h)
    assert "账本 ¥192" in t and "持仓按 10/15 收盘估" in t
    assert "今天（对账前）" in t                                                    # 最近成交：今天的两笔先列出来
    assert "今天已实现（预计，" + SETTLE + " 对账后正式记账）：约 −¥" in t
    assert json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8")) == b0   # 只读：账本没动


def test_phone_page_shows_the_same():
    _book()
    h = panel.render("paper", "c" * 40, AT, mode="remote", device={"name": "iPhone", "created": "2026-10-06T08:00:00+09:00"})
    _common(h)


def test_quotes_json_lists_what_is_held_now(monkeypatch):
    monkeypatch.setattr(panel, "_QUOTE_CACHE", {})
    _book()

    def fetch(ts):
        return {t: {"px": 240.0 if t == "1545.T" else 1490.0, "at": "2026-10-16T15:00+09:00"} for t in ts}
    code, js = panel.quotes_json("paper", now=AT, fetch=fetch)
    rows = js["rows"]
    assert code == 200 and "1545.T" not in rows and rows["1482.T"]["n"] == 650
    assert "est" not in rows["1482.T"] and "今天买进 650 口" in rows["1482.T"]["today_text"]


def test_submit_guards_on_todays_fills():
    _book()
    ok, msg, _r = panel.submit({"book": "paper", "kind": "sell", "ticker": "1545.T"}, now=AT)
    assert not ok and "今天已经卖出全部 4,110 口" in msg and "1545 纳斯达克 100" in msg
    assert not MO.requests_path("paper").exists()                               # 什么都没写（不会变成闲置资金比例 0%、停买 ETF）
    ok, msg, _r = panel.submit({"book": "paper", "kind": "trim", "ticker": "1545.T", "pct": 10}, now=AT)
    assert not ok and "今天已经卖出全部" in msg and not MO.requests_path("paper").exists()


def test_submit_stock_new_and_trimmed():
    _book_stocks()
    ok, msg, _r = panel.submit({"book": "paper", "kind": "buy", "ticker": "7203.T", "unit": "rule"}, now=AT)
    assert not ok and "今天已经买进 100 股" in msg and NM.label("7203.T") in msg
    ok, msg, _r = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203.T"}, now=AT)
    assert not ok and "才算持仓" in msg and NM.label("7203.T") in msg
    assert not MO.requests_path("paper").exists()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "adjust", "ticker": "6758.T", "unit": "shares", "value": 300}, now=AT)
    assert ok, msg                                                               # 账本 400 股、今天减到 200 股 → 调到 300 股 = 加（按账本会是减）
    assert rec["dir"] == 1 and rec["cur0"] == 200 and "加 100 股" in msg


def test_fund_holdings_and_fund_all_use_the_projection():
    b = _book()
    fh = MO.fund_holdings(b, "paper", now=AT)
    assert fh["cash"] == round(10020.1175 * 0.99)
    hold = {r["t"]: r for r in fh["hold"]}
    assert "1545.T" not in hold and hold["1482.T"]["cur"] == 650
    assert not {"1545.T", "1482.T"} & set(fh["busy"])                        # 收盘后写的凑钱在对账之后的决策里执行：今天有成交的也能凑（复核）
    fh10 = MO.fund_holdings(b, "paper", now=AT.replace(hour=10))              # 成交日盘中：当天动不了（busy_today）
    assert {"1545.T", "1482.T"} <= set(fh10["busy"])
    fa = MO.fund_all(b, "paper", "9984.T")
    assert "1545.T" in [t for t, _w in fa["skip"]] and "1545.T" not in [t for t, _c, _p in fa["sells"]]
    b = _book_stocks()
    fa = MO.fund_all(b, "paper", "9984.T")                                   # 今天买进的个股：不挡，执行时一起卖（复核：以前挡住）
    assert fa["blocked"] is None and fa["bought"] == ["7203.T"] and "7203.T" not in [t for t, _c, _p in fa["sells"]]
    assert "7203.T" in MO.fund_holdings(b, "paper", now=AT)["busy"]           # 今天买进的个股对账之前写不了卖出：不拿来凑


def test_new_texts_carry_names():
    _book_stocks()
    t = _text(panel.render("paper", "t" * 40, AT))
    for tk in ("1545.T", "1482.T", "7203.T", "6758.T"):
        assert NM.label(tk) in t
    for tk in ("7203", "6758", "1545", "1482"):
        assert not re.search(tk + r"(\.T)?：今天", t), tk                        # 不会只写代码就接「：今天…」


def test_allin_message_skips_the_etf_sold_today():
    _book()
    ok, msg, _r = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984.T", "unit": "rule", "fund": {"mode": "all"}}, now=AT)
    assert ok, msg
    assert "不用再卖的 ETF：1545 纳斯达克 100（今天已卖出全部 4,110 口（" + SETTLE + " 对账后正式记账））" in msg
    assert "1482 对冲版美国 7〜10 年国债：650 → 0 口" in msg and "4,110 → 0 口" not in msg


def test_desktop_page_and_status_with_a_stock_bought_today(monkeypatch, capsys):
    """今天买进的个股没有止损价（stop_px None）：桌面页与 --status 不崩，止损写「—」。"""
    import run
    from qbreak import desktop_page as DP
    _book_stocks()
    monkeypatch.setattr(DP, "now_jst", lambda: AT)
    t = _text(DP.render("paper", 1_000_000, "2026-09-28"))
    assert NM.label("7203.T") in t and "今天有成交（对账前）" in t and "含今天已成交" in t and SETTLE in t
    assert "1545 纳斯达克 100：今天已卖出全部 4,110 口" in t
    import shutil
    shutil.copy(paths.PROJECT_ROOT / "var" / "sim.json", paths.home() / "sim.json")   # liveu.sh 的 sync_inputs 做的事
    monkeypatch.setattr("qbreak.calendar_jp.now_jst", lambda: AT)             # run.py 在函数里 import
    assert run.main(["live-u", "--broker", "paper", "--status"]) == 0
    out = capsys.readouterr().out
    assert "止损 —" in out and "（今天买进，对账前）" in out and "含今天已成交" in out
    assert f"持仓 {NM.qty('7203.T', '100 股')}" in out and f"持仓 {NM.qty('6758.T', '200 股')}" in out
    assert "已成交（对账前） 1545 纳斯达克 100：今天已卖出全部 4,110 口" in out and "核心 1545" not in out
