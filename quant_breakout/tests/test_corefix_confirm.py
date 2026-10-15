"""固定口数 / 恢复按规则：点「确定」先给「确认下单 / 取消下单」，不直接写（2026-10-15 用户：「每天在盘中的时候固定口数点击确定的话要出现
确认下单和取消下单的确认不要直接下单」；10/14 19:21 把 1482.T 固定成 678 口 → 第二天早上的决策为了凑钱排了卖出全部 1545.T 4,110 口，
写之前没看到）。服务器没收到确认（token）就不写 → 旧页面（缓存的旧 JS）也绕不过去；本机与手机同一条路；命令行照旧直接写、多打印预计的单。"""
import datetime as dt
import json
import re
import shutil
import subprocess

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak import panel_phone as PP
from qbreak.calendar_jp import JST

from test_panel import _book1015, _js_fn
from test_panel_phone import _book as _pbook
from test_panel_phone import _local_post, _phone, servers  # noqa: F401（pytest 夹具）

AT1012 = dt.datetime(2026, 10, 15, 10, 12, tzinfo=JST)        # 2026-10-15（四）10:12：盘中
AT16 = dt.datetime(2026, 10, 15, 16, 0, tzinfo=JST)           # 收盘后：下一次决策（D1 之后决策那条路的说明在这个时刻查）
PX = {"1545.T": 243.7, "1482.T": 1474.0}


def _nofetch(ts):
    return {}


@pytest.fixture(autouse=True)
def _fresh_quotes(monkeypatch):
    """现价缓存是进程里的全局表（与 /api/quotes 共用）：每个测试从空的开始（前一个测试取到的现价不带进来）。"""
    monkeypatch.setattr(panel, "_QUOTE_CACHE", {})


def _state(fix=None, rule100=None):
    """10/15 的模拟账户：1545.T 4,110 口、1482.T 0 口、现金 192 円、总权益 1,001,799 円（收盘 1545.T 243.7 円 / 1482.T 1,474 円）；
    规则现在拿 1545.T（汇总的 idle_cash.hold）。fix：现在的固定口数（默认没有 = 10/14 19:21 写之前）。"""
    b = _book1015(fix={} if fix is None else fix)
    b["state"]["core_last"] = dict(PX)
    if rule100 is not None:
        b["core_rule"]["rule100"] = rule100
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"idle_cash": {"hold": ["1545.T"]}}), encoding="utf-8")
    return b


def _fix(units=678, **kw):
    return {"book": "paper", "kind": "corefix", "ticker": "1482", "units": units, **kw}


def test_corefix_refused_without_confirm_and_nothing_written():
    _state()
    ok, msg, rec = panel.submit(_fix(), AT1012, fetch=_nofetch)
    assert not ok and msg == panel.FIX_CONFIRM_MSG and "刷新页面" in msg            # 旧页面：照旧显示 msg（没写 + 刷新）
    assert rec["need_confirm"] is True and "id" not in rec
    c = rec["confirm"]
    assert c["title"] == "确认下单：1482 对冲版美国 7〜10 年国债 固定 678 口" and re.fullmatch(r"[0-9a-f]{16}", c["token"]) and c["changed"] is False
    assert MO.read_all("paper") == [] and not MO.requests_path("paper").exists()
    code, j = panel._req_reply(ok, msg, rec)
    assert code == 200 and j["ok"] is False and j["need_confirm"] is True and j["confirm"]["token"] == c["token"]


def test_preview_lists_funding_sells_timing_price_and_persistence():
    """确认框：现在 → 目标口数、估算金额（现价约晚 20 分钟、估算、税前）、别的 ETF 卖多少（现金 192 円不够）、什么时候、按什么价、一直有效。
    D1（2026-10-15）：盘中写的固定口数马上按现价下（以前「现在是盘中，不会马上下单；10/16 07:40 …」）：今天还没发出的同一只的买单被这条取代。"""
    _state()
    q = {"1482.T": {"px": 1480.0, "at": "2026-10-15T09:52:00+09:00"}, "1545.T": {"px": 244.0, "at": "2026-10-15T09:52:00+09:00"}}
    _ok, _m, rec = panel.submit(_fix(), AT1012, fetch=lambda ts: {t: q[t] for t in ts if t in q})
    t = rec["confirm"]["text"]
    assert "1482 对冲版美国 7〜10 年国债：现在 0 口 → 固定 678 口（买入 678 口）" in t          # 票写「代码 名字」（2026-10-15）
    assert "估算：678 口 × 约 ¥1,480 ≈ ¥1,003,440（Yahoo 09:52 的价，约晚 20 分钟；估算、税前、不含手续费）" in t
    assert "预计马上要下的核心 ETF 单" in t
    assert ("· 卖出 1545 纳斯达克 100 约 4,110 口（约 ¥1,002,840；4,110 → 0 口）：给 1482 对冲版美国 7〜10 年国债 凑钱"
            "（现金不够；先卖、卖出的钱到了才买）") in t
    assert "· 买入 1482 对冲版美国 7〜10 年国债 约 678 口" in t and "0 → 678 口）：固定口数" in t
    assert "现金约 ¥192：不够 → 执行器先卖上面的 1545 纳斯达克 100 约 4,110 口 补足" in t
    assert "什么时候：马上（盘中）按现价下单（模拟账户当场成交）" in t and "不会马上下单" not in t
    assert "按什么价：模拟账户按执行器下单那一刻的 Yahoo 现价" in t and "收盘 ×1.02 → 这次不买" in t
    assert "固定之后每天都调回 678 口" in t and "一直有效，直到点「恢复按规则」" in t
    # 10/15 还没发出的 1482.T 买单（等开盘后；凑钱的 1545.T 卖单撤了）：被这条取代，执行器不再发
    assert "今天开盘已排的 1482 对冲版美国 7〜10 年国债 买 678 口 还没发出 → 被这条取代（执行器不再发）" in t
    assert "照常" not in t
    assert t.splitlines()[-1].startswith("以上是预计")
    assert rec["confirm"]["danger"] is False
    assert MO.read_all("paper") == []


def test_preview_after_the_close_goes_to_the_next_decision():
    """收盘后（15:25 之后）写的 → 下一次决策：「10/16 07:40 的决策 → 10/16 09:00 开盘」、决策里的再平衡口径；今天的单照「交易」的判断写。"""
    _state()
    q = {"1482.T": {"px": 1480.0, "at": "2026-10-15T15:52:00+09:00"}, "1545.T": {"px": 244.0, "at": "2026-10-15T15:52:00+09:00"}}
    _ok, _m, rec = panel.submit(_fix(), dt.datetime(2026, 10, 15, 16, 0, tzinfo=JST), fetch=lambda ts: {t: q[t] for t in ts if t in q})
    t = rec["confirm"]["text"]
    assert "· 卖出 1545 纳斯达克 100 约 4,110 口（约 ¥1,002,840；4,110 → 0 口）：给 1482 对冲版美国 7〜10 年国债 腾钱" in t
    assert "现金约 ¥192：不够 → 执行器在那次决策里先卖上面的 1545 纳斯达克 100 约 4,110 口 补足" in t
    assert "什么时候：10/16 07:40 的决策 → 10/16 09:00 开盘" in t
    assert "按什么价：模拟账户按那天的开盘价（含滑点）成交；买入在卖出之后，钱不够少买" in t
    # 10/15 还挂着的 1482.T 买单（等开盘后）：凑钱的 1545.T 卖单撤了、现金 192 円 → 「交易」写「不会下单（预计）」；确认框跟着写
    # （2026-10-15 复核：以前写成「今天还有执行器的单 … 照常」，与「交易」对不上）
    assert "今天还有执行器的单：" not in t and "照常" not in t
    assert "今天的单里：今天开盘已排的 1482 对冲版美国 7〜10 年国债 买 678 口（资金来源的卖单已撤，预计不会下单：见「交易」→「今天的单」）" in t
    assert t.splitlines()[-1].startswith("以上是预计")


def test_clear_text_agrees_with_the_trade_tab_for_a_buy_that_will_not_be_placed():
    """「恢复按规则」的说明（data-plan / 提交后的说明）与「交易」同一个判断（2026-10-15 复核）：凑钱的卖单撤了、现金 192 円 →
    1482.T 买 678 口在「交易」写「不会下单（预计）」，这里不再写「照常」，写「预计不会下单」。凑钱的卖单还在 → 照常。
    D1（2026-10-15）：这是下一次决策那条路（收盘后写的）；盘中写的 → 马上调，今天还没发出的同一只的单被取代（执行器不再发）。"""
    b = _book1015()
    t = MO.corefix_clear_text(b, "1482.T", "paper", AT16)
    assert "照常" not in t and "今天开盘已排的 1482 对冲版美国 7〜10 年国债 买 678 口（资金来源的卖单已撤，预计不会下单" in t, t
    b = _book1015(sell="SENT")
    t = MO.corefix_clear_text(b, "1482.T", "paper", AT16)
    assert "今天开盘已排的 1482 对冲版美国 7〜10 年国债 买 678 口" in t and "照常" in t and "预计不会下单" not in t, t
    co = {"id": "M3-cancel_order", "kind": "cancel_order", "cid": "U2026-10-14-SELL-1545.T", "ticker": "1545.T", "status": "pending"}
    b = _book1015(sell="SENT", items={"M3-cancel_order": co})                 # 卖单在撤单中：买单也下不成；卖单写「撤单中」
    t = MO.corefix_clear_text(b, "1482.T", "paper", AT16)
    assert "预计不会下单" in t and "照常" not in t, t
    t = MO.corefix_clear_text(b, "1482.T", "paper", AT1012)                  # 盘中：马上；规则目标没算过 → 盘中不调、等开盘后的买单被取代
    assert t.startswith("马上（盘中）按现价下单（模拟账户当场成交）调到规则现在的口数") and "照常" not in t, t
    assert "规则自己的目标执行器还没算过 → 盘中不调，下一次决策照规则" in t
    assert t.endswith("今天开盘已排的 1482 对冲版美国 7〜10 年国债 买 678 口 还没发出：被这条取代（执行器不再发）"), t


def test_tachibana_preview_price_and_late_morning_text():
    """立花（2026-10-15 复核，照 live_unified 的实际做法）：买 = 寄付指値 收盘 ×1.02；要等卖出的钱的部分开盘后（09:05 / 09:20）按余力补下、
    当日限价（不看开盘跳空）；早上的运行没完成（08:55 之后）→ 补跑的决策错过寄付、核心 ETF 的单今天不发（B13）→ 下一个交易日。"""
    b = _state()
    (paths.state_dir() / "live_unified_tachibana.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    (paths.out_dir() / "live_unified_tachibana.json").write_text(json.dumps({"idle_cash": {"hold": ["1545.T"]}}), encoding="utf-8")
    pv = MO.corefix_preview(b, "tachibana", {"kind": "corefix", "ticker": "1482.T", "units": 678}, AT16, quotes={})
    t = pv["text"]
    assert "按什么价：卖 = 寄付成行（按开盘价）；买 = 寄付指値 收盘 ×1.02（开盘价更高 → 寄付不成交）" in t, t
    assert "；开盘前余力不够的部分（要等卖出的钱）在开盘后（09:05 / 09:20）按余力补下：当日限价 ≤ 收盘 ×1.02" in t
    t = MO.corefix_preview(b, "tachibana", {"kind": "corefix", "ticker": "1482.T", "units": 678}, AT1012, quotes={})["text"]
    assert "什么时候：马上（盘中）按现价下单\n" in t                                # 盘中（D1）：马上；按现价限价、M14 的上限
    assert ("按什么价：立花在执行器下单那一刻取实时现价：卖 = 限价 现价 −0.5%；买 = 限价 min(现价 +0.5%, 收盘 ×1.02)"
            "（现价超过收盘 ×1.02 → 这次不买，10 分钟后再试）；凑钱的卖单成交了才买") in t, t
    late = dt.datetime(2026, 10, 15, 9, 10, tzinfo=JST)
    old = {"state": {"last_date": "2026-10-13"}}                               # 10/15 早上的运行还没完成
    f = MO.corefix_fill(late, old, "tachibana")
    assert f["behind"] and f["text"] == ("今天早上的运行还没完成：立花 08:55 之后补跑的那次决策错过寄付，核心 ETF 的单今天不发（B13）→ "
                                         "10/16 07:40 的决策读到、10/16 09:00 开盘下单（立花不自动补跑）")
    p = MO.corefix_fill(late, old, "paper")
    assert p["behind"] and "面板会自动补跑" in p["text"] and "10/16 09:00 开盘下单" in p["text"]


def test_preview_without_quotes_uses_the_close_and_says_so():
    _state()
    _ok, _m, rec = panel.submit(_fix(), AT1012, fetch=_nofetch)
    assert "估算：678 口 × 约 ¥1,474 ≈ ¥999,372（10/14 收盘；估算、税前、不含手续费）" in rec["confirm"]["text"]


def test_confirm_writes_once_and_a_stale_token_asks_again():
    _state()
    _ok, _m, rec = panel.submit(_fix(), AT1012, fetch=_nofetch)
    tok = rec["confirm"]["token"]
    ok, msg, r2 = panel.submit(_fix(confirm="0" * 16), AT1012, fetch=_nofetch)       # 对不上（账本 / 时间段变了）→ 再给一次新的确认框
    assert not ok and r2["need_confirm"] and r2["confirm"]["changed"] is True and r2["confirm"]["token"] == tok
    assert MO.read_all("paper") == []
    ok, msg, w = panel.submit(_fix(confirm=tok), AT1012, fetch=_nofetch)
    assert ok and msg.startswith("已写：1482 对冲版美国 7〜10 年国债 固定 678 口 → 马上（盘中）按现价下单（模拟账户当场成交）")   # D1
    rs = MO.read_all("paper")
    assert len(rs) == 1 and rs[0]["kind"] == "corefix" and rs[0]["units"] == 678 and rs[0]["id"] == w["id"] and "confirm" not in rs[0]


def test_token_changes_when_what_would_be_ordered_changes():
    """确认框打开之后账本变了（执行器跑完 / 别的指令）→ 原来的 token 不再有效（不按看过的旧内容写）。"""
    _state()
    _ok, _m, rec = panel.submit(_fix(), AT1012, fetch=_nofetch)
    b = _state()
    b["state"]["core_units"]["1545.T"] = 2000
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    ok, _m, r2 = panel.submit(_fix(confirm=rec["confirm"]["token"]), AT1012, fetch=_nofetch)
    assert not ok and r2["confirm"]["changed"] and r2["confirm"]["token"] != rec["confirm"]["token"]
    assert MO.read_all("paper") == []


def test_preview_when_selling_other_etf_still_leaves_a_shortfall():
    """固定 678 → 248 口（还是要买 248 口）：1545.T 照规则卖到 2,610 口；卖了还差一点 → ★ 写清开盘后按开盘价检查、少买（收盘后写的 = 决策）。
    盘中写的（D1）：按缺多少卖 1545.T（含现金缓冲 1%），不调到它的规则目标。"""
    _state(fix={"1482.T": 678})
    _ok, _m, rec = panel.submit(_fix(248), AT16, fetch=_nofetch)
    t = rec["confirm"]["text"]
    assert "现在 0 口 → 固定 248 口（买入 248 口）；现在手动固定 678 口" in t
    assert "约 1,500 口（约 ¥365,550；4,110 → 2,610 口）" in t
    assert "现金约 ¥192：不够 → 执行器在那次决策里先卖上面的 1545 纳斯达克 100 约 1,500 口 补足" in t
    assert "★ 这样卖了也还差约 ¥" in t and "钱不够就少买（减口数）" in t
    _ok, _m, rec = panel.submit(_fix(248), AT1012, fetch=_nofetch)
    t = rec["confirm"]["text"]
    assert "约 1,530 口（约 ¥372,861；4,110 → 2,580 口）：给 1482 对冲版美国 7〜10 年国债 凑钱（现金不够；先卖、卖出的钱到了才买）" in t, t
    assert "现金约 ¥192：不够 → 执行器先卖上面的 1545 纳斯达克 100 约 1,530 口 补足" in t


def test_preview_outside_market_hours_has_no_intraday_note():
    _state()
    _ok, _m, rec = panel.submit(_fix(), dt.datetime(2026, 10, 15, 19, 21, tzinfo=JST), fetch=_nofetch)
    t = rec["confirm"]["text"]
    assert "现在是盘中" not in t and "什么时候：10/16 07:40 的决策 → 10/16 09:00 开盘\n" in t


def test_clear_preview_and_write():
    """恢复按规则：也要先确认；写清取消固定多少口、规则的目标、之后每天照规则。"""
    _state(fix={"1482.T": 678}, rule100={"1482.T": 0, "1545.T": 4110})
    body = {"book": "paper", "kind": "corefix", "ticker": "1482", "clear": True}
    ok, msg, rec = panel.submit(body, AT1012, fetch=_nofetch)
    assert not ok and rec["need_confirm"] and MO.read_all("paper") == []
    c = rec["confirm"]
    assert c["title"] == "确认下单：1482 对冲版美国 7〜10 年国债 恢复按规则" and c["danger"] is False
    assert "取消手动固定 678 口 → 恢复按规则：预计 0 → 0 口（口数不变）" in c["text"]
    assert "预计不用买卖核心 ETF（口数已经一样）" in c["text"] and "之后这只 ETF 每天照规则" in c["text"]
    assert "什么时候：马上（盘中）按现价下单（模拟账户当场成交）" in c["text"]          # D1：盘中写的马上调到规则的口数
    assert "今天开盘已排的 1482 对冲版美国 7〜10 年国债 买 678 口 还没发出 → 被这条取代（执行器不再发）" in c["text"]
    ok, msg, w = panel.submit({**body, "confirm": c["token"]}, AT1012, fetch=_nofetch)
    assert ok and msg.startswith("已写：1482 对冲版美国 7〜10 年国债 恢复按规则") and [r["clear"] for r in MO.read_all("paper")] == [True]


def test_sell_on_a_fixed_etf_also_needs_confirm_and_says_so():
    """固定的 ETF 上点「卖出全部」= 换算成固定 0 口 → 同样先确认；框里写「你点的是…只改它的固定口数」、卖出 → danger。"""
    b = _state(fix={"1482.T": 678})
    b["state"]["core_units"]["1482.T"] = 678
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    ok, _m, rec = panel.submit({"book": "paper", "kind": "sell", "ticker": "1482"}, AT1012, fetch=_nofetch)
    assert not ok and rec["need_confirm"] and MO.read_all("paper") == []
    c = rec["confirm"]
    assert c["title"] == "确认下单：1482 对冲版美国 7〜10 年国债 固定 0 口" and c["danger"] is True
    assert "现在 678 口 → 固定 0 口（卖出 678 口）" in c["text"] and "只改它的固定口数" in c["text"]


def test_need_confirm_on_the_local_and_phone_ports_then_confirm_writes(servers, monkeypatch):  # noqa: F811
    """本机与手机同一条路：没带确认 → 200 + ok:false + 确认框（什么都没写；2026-10-15 复核：以前 409，浏览器控制台每次记一条错误）；
    带上 token → 写一次。"""
    monkeypatch.setattr("qbreak.data.intraday_quotes", _nofetch)                     # 不联网
    lp, pp, tok = servers
    _pbook()
    body = {"book": "paper", "kind": "corefix", "ticker": "1545", "units": 50}
    code, j = _local_post(lp, tok, "/api/request", body)
    assert code == 200 and j["ok"] is False and j["need_confirm"] is True and "刷新" in j["msg"]
    assert j["confirm"]["title"] == "确认下单：1545 纳斯达克 100 固定 50 口" and not MO.read_all("paper")
    code, j2 = _local_post(lp, tok, "/api/request", {**body, "confirm": j["confirm"]["token"]})
    assert code == 200 and j2["ok"] and j2["id"] and len(MO.read_all("paper")) == 1
    # 手机（配对过的设备 + CSRF）
    MO.requests_path("paper").unlink()
    code_, _exp = PP.new_code()
    _ok, _msg, ck = PP.pair(code_, name="iPhone")
    csrf = PP.csrf(ck.split(".")[0])
    c, txt, _ = _phone(pp, "POST", "/api/request", body, cookie=ck, csrf=csrf)
    j = json.loads(txt)
    assert c == 200 and j["ok"] is False and j["need_confirm"] and not MO.read_all("paper")
    c, txt, _ = _phone(pp, "POST", "/api/request", {**body, "confirm": j["confirm"]["token"]}, cookie=ck, csrf=csrf)
    rs = MO.read_all("paper")
    assert c == 200 and json.loads(txt)["ok"] and len(rs) == 1 and rs[0]["source"] == "phone"


def test_page_script_only_sends_the_token_from_the_confirm_button():
    """trade.js 的 post()：服务器要确认 → 弹「确认下单 / 取消下单」；取消 → 什么都不发；确认 → 带上 token 再发一次（node 里跑）。"""
    src = (panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8")
    core = (panel.STATIC_DIR / "core.js").read_text(encoding="utf-8")
    assert "if(j && j.need_confirm && !j.ok) return j;" in core
    assert src.count("api('/api/request'") == 2 and "api('/api/request', Object.assign({}, body, {confirm:c.token}))" in src
    _state()
    assert "id='ask-no'" in panel.render("paper", "t" * 40, AT1012)                # 「取消」按钮的文字能换成「取消下单」
    node = shutil.which("node")
    if not node:
        return
    js = ("let SENT=[], RESP=[], ANS=[], TOASTS=[], ASKED=[];const NOTE='';"
          "const api=async (p,b)=>{SENT.push(b); return RESP.shift();};"
          "const ask=async (t,b,ok,o)=>{ASKED.push([t,ok,o.cancel]); return {ok:ANS.shift()};};"
          "const toast=(t)=>TOASTS.push(t);\nasync " + _js_fn(src, "post") + """
const need={ok:false, need_confirm:true, msg:'还没写', confirm:{title:'确认下单：1482.T 固定 678 口', text:'x', token:'abc', danger:false}};
(async()=>{
  RESP=[need]; ANS=[false];
  const a=await post({kind:'corefix', units:678});
  console.log(JSON.stringify({a, SENT, ASKED, TOASTS}));
  SENT=[]; ASKED=[]; TOASTS=[]; RESP=[need, {ok:true, msg:'已写'}]; ANS=[true];
  const b=await post({kind:'corefix', units:678});
  console.log(JSON.stringify({b, SENT, ASKED}));
})();""")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True, timeout=60).stdout.splitlines()
    r1, r2 = json.loads(out[0]), json.loads(out[1])
    assert r1["a"] is None and r1["SENT"] == [{"kind": "corefix", "units": 678}]                  # 取消下单：没有第二次请求
    assert r1["ASKED"] == [["确认下单：1482.T 固定 678 口", "确认下单", "取消下单"]] and r1["TOASTS"] == ["已取消：什么都没写，不会下单"]
    assert r2["b"] == {"ok": True, "msg": "已写"}
    assert r2["SENT"] == [{"kind": "corefix", "units": 678}, {"kind": "corefix", "units": 678, "confirm": "abc"}]
