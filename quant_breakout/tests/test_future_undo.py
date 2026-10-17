"""还没下的单 / 还没照它调的指令都能在「交易」那一行撤（2026-10-17 用户：「类似现在周一要下单的未来的还没有下单的单都可以进行撤销」）。
周六的模拟账户：「1482 固定 655 口：现在 650 口（含 10/16 已成交），还差 5 口 → 10/19（周一）07:40 的决策照它调（开盘买）」以前没有按钮。
  · 固定口数还差几口（fix_short）/ 读了、还没照它调的固定口数（FIX_WAIT、outlook 的 fix:<票>）→「不补了… / 撤回…」：
    只用现有的写法（kind corefix）：固定成现在拿着的口数（预计不买也不卖）/ 改回上一次照它调的 / 恢复按规则，点了之后照旧有服务器的「确认下单」框；
  · 读了、还没照它调的闲置资金比例（core_wait、outlook 的 core:）→「撤回…」= 比例改回上一次照它调的（MO.core_applied；kind core）；
  · 被挡、还没发到交易所、今天还会再发的执行器单（BLOCKED、没有注文番号、blocked_retry）→「撤单」= 执行器不再重试；
  · 还没发出、还会做事却撤不了的执行器单 → 写为什么（以前什么都不写）；
  · 「全部换成」同批的比例 / 固定口数（读了、等那次决策）→「随「全部换成 X」一起（撤回买入那条）」；
  · 下一次决策规则自己排的单现在还没有 → 一行：HALT，或 07:40 之后、09:00 开盘之前撤（没有假按钮）。
Mac 与手机同一份 HTML、同一个 trade.js；按钮发的请求在 node 里实际跑。"""
import datetime as dt
import html as H
import json
import re

import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST, is_trading_day, next_trading_day

from test_core_etf_restore import _morning, _paper2, _w
from test_corefix_now import _disk
from test_manual_now import _at, _quote
from test_trade_today import (CORE50, D, _badge_ok, _etf_book, _mbook, _morder, _named, _parts, _row, _save, _t)

PXQ = {"A.T": 1000.0, "B.T": 1500.0, "1545.T": 700.0, "1482.T": 1000.0}
LAB = "1482 对冲版美国 7〜10 年国债"
RULE_NOTE = "规则自己也可能买卖（那时才排出单，现在还没有，撤不了）"


def _btn(part: str, act: str) -> dict | None:
    """part 里第一个 data-act=act 的按钮 → {属性: 值（已反转义）, "_text": 按钮上的字}；没有 → None。"""
    m = re.search(rf"<button[^>]*data-act='{act}'[^>]*>([^<]*)</button>", part)
    if not m:
        return None
    out = {k: H.unescape(v) for k, v in re.findall(r"data-([\w-]+)='([^']*)'", m.group(0))}
    out["_text"] = H.unescape(m.group(1))
    return out


def _block(J: str, head: str) -> str:
    """trade.js 里 if(a==='…'){…} 那一段（按大括号配对）。"""
    i = J.index(head)
    j = J.index("{", i + len(head) - 1)
    depth = 0
    for k in range(j, len(J)):
        depth += {"{": 1, "}": -1}.get(J[k], 0)
        if depth == 0:
            return J[i:k + 1]
    raise ValueError(head)


def _node(act: str, d: dict, ans: dict, tag: str = "paper") -> dict:
    """trade.js 点这个按钮那一段在 node 里跑（ask 回答 ans）→ {SENT: 发出的请求, ASKED: [标题, 正文, 主按钮, 另外的选择]}；没有 node → skip。"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    J = (panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8")
    blk = _block(J, f"if(a==='{act}'){{")
    js = (f"let SENT=[], ASKED=[];const CFG={{book:{json.dumps(tag)}}};const NOTE='';"
          "const post=async b=>{SENT.push(b); return {ok:true, msg:'已写'};};"
          f"const ANS={json.dumps(ans)};"
          "const ask=async (t,b,ok,o)=>{ASKED.push([t, b, ok, ((o||{}).alt||[]).map(x=>[x.text, x.v])]); return ANS;};"
          "const done=j=>0;"
          "async function Hh(a,d){ " + blk + " }\n"
          f"const d={json.dumps(d, ensure_ascii=False)};"
          f"Hh({json.dumps(act)}, d).then(()=>console.log(JSON.stringify({{SENT, ASKED}})));")
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True, timeout=60).stdout.splitlines()[-1])


def _submit(body: dict, now: dt.datetime) -> tuple[bool, str]:
    """面板写指令（trade.js 的 post 同一个）：固定口数先给「确认下单」框 → 带 token 再发一次。"""
    ok, msg, j = panel.submit(dict(body), now=now)
    if not ok and (j or {}).get("need_confirm"):
        c = j["confirm"]
        ok, msg, _j = panel.submit({**body, "confirm": c["token"]}, now=now)
        return ok, c["text"] + "\n=>\n" + msg
    return ok, msg


# ────────── 固定口数还差几口（模拟账户：真的跑执行器） ──────────
def _short_fri():
    """test_fix_short._short 晚一天：成交日是周五（2026-01-23）—— 1545 照规则拿满 → 10:30 固定 1482 U 口 → 现金只够 q 口（还差 U − q 口）。"""
    r = _paper2()
    _morning(r, 9)
    eq = r.eng.st.cash_jpy + sum(u * 700 for u in r.eng.st.core_units.values())
    u = int(eq / 1000) + 50
    _w(r.tag, "M-fix", kind="corefix", ticker="1482.T", units=u)
    r.now["t"] = _at(r, 10, 30)
    r.ux.now_phase(_quote(PXQ))
    b = _disk(r)
    q = int(LO.held_now(b, r.tag, now=_at(r, 15, 45))["core_units"]["1482.T"])
    assert 0 < q < u and MO.fix_applied(b)["1482.T"] == u and _at(r, 0, 0).weekday() == 4
    return r, u, q


def _sat(r, hh: int = 12) -> dt.datetime:
    d = _at(r, 0, 0).date() + dt.timedelta(days=1)
    assert not is_trading_day(d)
    return dt.datetime.combine(d, dt.time(hh, 0), tzinfo=JST)


def test_weekend_shortfall_row_gets_dont_top_up_and_monday_does_not_buy():
    r, u, q = _short_fri()
    sat = _sat(r)
    mon = next_trading_day(sat.date())
    html = panel.render(r.tag, "t" * 40, sat)
    top, later, _ended = _parts(html)
    assert "今天休市，没有要成交的单" in top and f"<summary>另有 1 条等 {LO.md_wd(mon)}开盘</summary>" in later
    assert f"下一次决策（{mon:%m/%d} 07:40）{RULE_NOTE}" in top and "停止下单（HALT）" in top   # 规则的单：没有假按钮，说怎么停
    row = _row(later, f"<b>{LAB} 固定 {u:,} 口")
    assert f"<span class='chip'>还差 {u - q:,} 口</span>" in row and "「不补了…」" in row   # 说明指着这一行的按钮（SHORT_NOTE）
    b = _btn(row, "fix-undo")
    assert b is not None and b["_text"] == "不补了…" and b["t"] == "1482.T"
    assert json.loads(b["opts"]) == [{"l": f"不补了：固定成现在 {q:,} 口", "u": q}, {"l": "恢复按规则", "c": 1}]
    assert f"取代固定 {u:,} 口：读到之后（{mon:%m/%d} 07:40 的决策 → {mon:%m/%d} 09:00 开盘）口数一样 → 预计不买也不卖" in b["body"]
    assert "「恢复按规则」= 取消固定口数：" in b["body"] and "「确认下单」框" in b["body"]
    assert _badge_ok(html, r.tag, sat) == 1
    _named(html)
    js = _node("fix-undo", b, {"ok": True})                                    # 主按钮「不补了」
    assert js["SENT"] == [{"book": "paper", "kind": "corefix", "ticker": "1482.T", "units": q}]
    assert js["ASKED"][0][2] == f"不补了：固定成现在 {q:,} 口" and js["ASKED"][0][3] == [["恢复按规则", "1"]]
    ok, msg = _submit(js["SENT"][0], sat)
    assert ok and "下一次决策预计不用买卖核心 ETF" in msg and f"什么时候：{mon:%m/%d} 07:40 的决策" in msg, msg
    html = panel.render(r.tag, "t" * 40, sat)
    top, later, _ended = _parts(html)
    assert "还差" not in top + later and _btn(later, "fix-undo") is None       # 那一行没了：换成刚写的那条（还没读，能撤回）
    row = _row(_ended, f"<b>固定 {LAB}：{q:,} 口（不按规则自动调）</b>")       # 口数一样 = 不下单：收进「已结束」、不算数字（2026-10-17）
    assert "<span class='chip'>不下单</span>" in row
    c = _btn(row, "cancel")
    assert c is not None and c["_text"] == "撤回" and c["ctx"] == (f"执行器还没读：撤回之后这条不生效，{LAB} 照旧固定 {u:,} 口"   # 不是「撤掉之后不会下」
                                                               f"（现在 {q:,} 口 → 买 {u - q:,} 口：{mon:%m/%d} 07:40 的决策 → "
                                                               f"{mon:%m/%d} 09:00 开盘；钱不够只买得起的部分）")
    assert _badge_ok(html, r.tag, sat) == 0
    js = _node("cancel", c, {"ok": True})                                      # 想了想又要补：撤回刚写的那条 → 那一行回来
    assert js["SENT"] == [{"book": "paper", "kind": "cancel", "target": c["id"]}] and c["ctx"] in js["ASKED"][0][1]
    ok, msg = _submit(js["SENT"][0], sat)
    assert ok, msg
    html = panel.render(r.tag, "t" * 40, sat)
    _top, later, _ended = _parts(html)
    assert _btn(_row(later, f"<b>{LAB} 固定 {u:,} 口"), "fix-undo") is not None and _badge_ok(html, r.tag, sat) == 1
    ok, msg = _submit({"book": "paper", "kind": "corefix", "ticker": "1482.T", "units": q}, sat)   # 再点一次「不补了」
    assert ok, msg
    _morning(r)                                                                # 周一 07:40 的决策：口数一样，不买
    d = r.ux.book["state"]["last_date"]
    assert not [o for o in r.ux.orders if o.decided_on == d and o.ticker == "1482.T"]
    b2 = _disk(r)
    assert MO.fix_applied(b2)["1482.T"] == q and MO.core_fixed(b2)["1482.T"] == q
    html = panel.render(r.tag, "t" * 40, _at(r, 8, 0))
    assert f"还差 {u - q:,} 口" not in html
    _badge_ok(html, r.tag, _at(r, 8, 0))


def test_weekend_shortfall_restore_option_goes_through_the_confirm_box():
    r, u, q = _short_fri()
    sat = _sat(r)
    b = _btn(_parts(panel.render(r.tag, "t" * 40, sat))[1], "fix-undo")
    js = _node("fix-undo", b, {"ok": True, "alt": "1"})                        # 另外的选择「恢复按规则」
    assert js["SENT"] == [{"book": "paper", "kind": "corefix", "ticker": "1482.T", "clear": True}]
    ok, msg, j = panel.submit(dict(js["SENT"][0]), now=sat)
    assert not ok and j["need_confirm"] and "恢复按规则" in j["confirm"]["title"]   # 照旧先给「确认下单」框
    assert js["ASKED"] and not _node("fix-undo", b, {"ok": False})["SENT"]      # 取消：什么都不发


def test_shortfall_row_before_the_decision_is_today_with_the_button():
    r, u, q = _short_fri()
    mon7 = dt.datetime.combine(next_trading_day(_at(r, 0, 0).date()), dt.time(7, 0), tzinfo=JST)
    html = panel.render(r.tag, "t" * 40, mon7)
    top, later, _ended = _parts(html)
    row = _row(top, f"<b>{LAB} 固定 {u:,} 口")
    assert "今天 07:40 的决策照它调" in row and _btn(row, "fix-undo")["_text"] == "不补了…"
    assert RULE_NOTE in top                                                    # 今天 07:40 的决策还没做
    _morning(r)                                                                # 07:40 决策照固定口数排了买单 → 那一行变成执行器的单（能撤单）
    at8 = _at(r, 8, 0)
    html = panel.render(r.tag, "t" * 40, at8)
    top, later, _ended = _parts(html)
    assert _btn(top + later, "fix-undo") is None and RULE_NOTE not in top
    c = _btn(_row(top, f"<b>买 {LAB}：{u - q:,} 口</b>"), "cancel-order")
    assert c is not None and c["unsent"] == "1"
    _badge_ok(html, r.tag, at8)


# ────────── 静态账本：两种账本、各个时刻 ──────────
def _short_book(tag: str) -> dict:
    """10/15 的决策之后（成交日 10/16 周五）：固定 1482 655 口、已照它调过（fix_applied 655），拿着 650 口；现金够补。"""
    b = _etf_book(tag)
    b["state"]["core_units"] = {"1545.T": 0, "1482.T": 650}
    b["state"]["pos"] = {}
    b["core_rule"]["px"]["1482.T"] = 1483.0
    b["core_rule"]["units100"] = {"1545.T": 0, "1482.T": 0}
    b["core_rule"]["fix_applied"] = {"1482.T": 655}
    b["manual"]["core_fix"] = {"1482.T": 655}
    b["manual"]["items"]["M20261016-094233-corefix-1482"] = {
        "id": "M20261016-094233-corefix-1482", "kind": "corefix", "ticker": "1482.T", "units": 655, "status": "done",
        "at": "2026-10-16T09:42:33+09:00", "msg": "现金只够 650 口（还差 5 口：下一次决策照它调）"}
    return _save(b, tag)


@pytest.mark.parametrize("tag", ["paper", "tachibana"])
@pytest.mark.parametrize("now", [_t(2026, 10, 16, 16, 0), _t(2026, 10, 17, 12, 0), _t(2026, 10, 19, 7, 0),
                                 _t(2026, 10, 19, 8, 0), _t(2026, 10, 19, 10, 30), _t(2026, 10, 19, 16, 0)])
def test_shortfall_row_has_the_button_wherever_it_is_shown(tag, now):
    """周五收盘后 / 周六 / 周一 07:00 / 08:00 / 10:30 / 16:00（周一的决策还没跑：早上的运行没完成）—— 那一行在上面或「另有」就有按钮，
    选择一样；数字与行数一致。"""
    _short_book(tag)
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    head = f"<b>{LAB} 固定 655 口：现在 650 口"
    part = top if head in top else later
    assert head in part, now
    b = _btn(_row(part, head), "fix-undo")
    assert b is not None and json.loads(b["opts"]) == [{"l": "不补了：固定成现在 650 口", "u": 650}, {"l": "恢复按规则", "c": 1}]
    assert _badge_ok(html, tag, now) == 1
    _named(html)


# ────────── 读了、还没照它调的固定口数（FIX_WAIT） ──────────
@pytest.mark.parametrize("tag", ["paper", "tachibana"])
def test_read_fix_not_applied_yet_offers_keep_now_back_to_previous_and_rule(tag):
    b = _short_book(tag)
    b["manual"]["core_fix"] = {"1482.T": 700}                                 # 周六之前读了「固定 700 口」，还没照它调（fix_applied 655）
    rid = "M20261016-180000-corefix-1482"
    b["manual"]["items"][rid] = {"id": rid, "kind": "corefix", "ticker": "1482.T", "units": 700, "status": "done",
                                 "at": "2026-10-16T18:00:00+09:00", "msg": "固定 700 口"}
    _save(b, tag)
    now = _t(2026, 10, 17, 12, 0)
    html = panel.render(tag, "t" * 40, now)
    _top, later, _ended = _parts(html)
    head = f"<b>固定 {LAB}：700 口（不按规则自动调）</b>"
    row = _row(later, head)
    assert f"<span class='chip'>{MO.FIX_WAIT}</span>" in row
    x = _btn(row, "fix-undo")
    assert x["_text"] == "撤回…" and json.loads(x["opts"]) == [
        {"l": "这次不调：固定成现在 650 口", "u": 650}, {"l": "改回固定 655 口（上一次照它调的）", "u": 655}, {"l": "恢复按规则", "c": 1}]
    assert "（现在 650 口 → 买 5 口；钱不够只买得起的部分）" in x["body"]
    js = _node("fix-undo", x, {"ok": True, "alt": "1"}, tag)
    assert js["SENT"] == [{"book": tag, "kind": "corefix", "ticker": "1482.T", "units": 655}]
    assert [a[1] for a in js["ASKED"][0][3]] == ["1", "2"]
    ok, msg = _submit(js["SENT"][0], now)
    assert ok, msg
    html = panel.render(tag, "t" * 40, now)
    _top, later, ended = _parts(html)
    assert head in ended and _btn(_row(ended, head), "fix-undo") is None      # 被新写的那条取代
    assert _btn(_row(later, f"<b>固定 {LAB}：655 口（不按规则自动调）</b>"), "cancel") is not None
    assert _badge_ok(html, tag, now) == 1


def test_pending_restore_rule_row_offers_fixing_again():
    """读了「恢复按规则」、还没照它调（周一要卖 650 口）→「撤回…」：固定成现在 650 口（= 上一次照它调的口数时只给一个）。"""
    tag = "paper"
    b = _short_book(tag)
    b["manual"]["core_fix"] = {}
    b["core_rule"]["fix_applied"] = {"1482.T": 650}
    rid = "M20261016-180000-corefix-1482"
    b["manual"]["items"][rid] = {"id": rid, "kind": "corefix", "ticker": "1482.T", "clear": True, "status": "done",
                                 "at": "2026-10-16T18:00:00+09:00", "msg": "恢复按规则"}
    _save(b, tag)
    now = _t(2026, 10, 17, 12, 0)
    html = panel.render(tag, "t" * 40, now)
    _top, later, _ended = _parts(html)
    row = _row(later, f"<b>{LAB} 恢复按规则（还没照它调）</b>")
    x = _btn(row, "fix-undo")
    assert json.loads(x["opts"]) == [{"l": "这次不调：固定成现在 650 口", "u": 650}] and "取代「恢复按规则」" in x["body"]
    ok, msg = _submit({"book": tag, "kind": "corefix", "ticker": "1482.T", "units": 650}, now)
    assert ok and "下一次决策预计不用买卖核心 ETF" in msg, msg
    assert _badge_ok(panel.render(tag, "t" * 40, now), tag, now) == 0          # 固定成拿着的口数 = 不下单：不算（2026-10-17）


# ────────── 读了、还没照它调的闲置资金比例 ──────────
@pytest.mark.parametrize("tag", ["paper", "tachibana"])
@pytest.mark.parametrize("now,where", [(_t(2026, 10, 16, 16, 0), "later"), (_t(2026, 10, 17, 12, 0), "later"),
                                       (_t(2026, 10, 19, 7, 0), "top")])
def test_core_ratio_not_applied_yet_can_be_reverted(tag, now, where):
    b = _etf_book(tag)
    rid = "M20261016-100000-core"
    b["manual"]["core_pct"] = 50.0
    b["manual"]["items"][rid] = {"id": rid, "kind": "core", "ticker": "1545.T", "pct": 50.0, "target": 2000, "status": "done",
                                 "at": "2026-10-16T10:00:00+09:00", "msg": "闲置资金比例设为 50%（1545 纳斯达克 100 约 2,000 口）"}
    _save(b, tag)
    html = panel.render(tag, "t" * 40, now)
    top, later, _ended = _parts(html)
    part = top if where == "top" else later
    x = _btn(_row(part, CORE50), "core-undo")
    assert x is not None and x["pct"] == "100" and x["ok"] == "改回 100%" and x["_text"] == "撤回…"
    assert "「改回 100%」= 写闲置资金比例 100%（上一次照它调的比例）：执行器读到就生效" in x["body"] and "不照 50% 买卖" in x["body"]
    assert "规则自己变了照样会买卖" in x["body"] and "「固定口数…」" in x["body"]
    js = _node("core-undo", x, {"ok": True}, tag)
    assert js["SENT"] == [{"book": tag, "kind": "core", "pct": 100}] and js["ASKED"][0][0] == "撤回？闲置资金比例 50% → 改回 100%"
    ok, msg = _submit(js["SENT"][0], now)
    assert ok and msg.startswith("已写：闲置资金比例改回 100%（上一次照它调的；50% 还没照它调）→ 执行器读到就生效"), msg
    html = panel.render(tag, "t" * 40, now)
    top, later, ended = _parts(html)
    assert CORE50 not in top + later and _btn(top + later, "core-undo") is None   # 收进「已结束」（超过 2 天的不显示）
    assert _btn(_row(top + later, "<b>闲置资金比例 100%"), "cancel") is not None   # 刚写的那条（还没读）：能撤回
    assert _badge_ok(html, tag, now) == 1
    b2 = _etf_book(tag)                                                        # 执行器读到 = core_pct 100 = applied → 不再照 50% 调
    assert MO.core_pending(b2) is None and MO.core_applied(b2) == 100.0
    _named(html)


def test_core_ratio_row_without_its_instruction_also_gets_the_button():
    tag = "paper"
    b = _etf_book(tag)
    b["manual"]["core_pct"] = 50.0
    _save(b, tag)
    now = _t(2026, 10, 16, 16, 0)
    _top, later, _ended = _parts(panel.render(tag, "t" * 40, now))
    x = _btn(_row(later, "<b>闲置资金比例 50%（还没照它调）</b>"), "core-undo")
    assert x is not None and x["pct"] == "100"


def test_stop_buying_not_applied_yet_revert_says_no_sell():
    tag = "paper"
    b = _etf_book(tag)
    rid = "M20261016-100000-core"
    b["manual"]["core_pct"] = 0.0
    b["manual"]["core_pause"] = {"since": "2026-10-16", "id": rid, "ticker": "1545.T"}
    b["manual"]["items"][rid] = {"id": rid, "kind": "core", "ticker": "1545.T", "pct": 0.0, "target": 0, "status": "done",
                                 "at": "2026-10-16T16:30:00+09:00", "msg": "卖出全部 1545 纳斯达克 100，之后停买闲置资金 ETF"}
    _save(b, tag)
    now = _t(2026, 10, 17, 12, 0)
    html = panel.render(tag, "t" * 40, now)
    x = _btn(_parts(html)[1], "core-undo")
    assert x is not None and "停买闲置资金 ETF（比例 0%）还没照它调" in x["body"] and "（不卖、不停买）" in x["body"]
    ok, msg = _submit({"book": tag, "kind": "core", "pct": 100}, now)
    assert ok and "改回 100%" in msg and "确认买入" not in msg, msg


# ────────── 被挡、还没发出的执行器单 ──────────
def _blocked_sell(tag: str) -> dict:
    it = {"id": "M1-sell", "kind": "sell", "ticker": "7203.T", "status": "placed", "decided_on": D, "fill_day": "2026-10-15",
          "shares": 200, "side": "SELL", "msg": "10/15 开盘卖出全部 200 股", "at": "2026-10-14T19:00:00+09:00"}
    return _mbook(tag, D, [_morder(D, "SELL", "7203.T", "manual", "BLOCKED", "闸门：异常熔断", qty=200, sent_qty=200)], {"M1-sell": it})


@pytest.mark.parametrize("tag", ["paper", "tachibana"])
def test_blocked_unsent_order_that_will_be_retried_can_be_cancelled(tag):
    b = _blocked_sell(tag)
    cid = f"U{D}-SELL-7203.T"
    now = _t(2026, 10, 15, 8, 30)                                              # 08:55 之前：08:35 / --retry 还会再发
    o = b["orders"][0]
    assert LO.blocked_retry(o, now, LO.fill_day_of(b)) and LO.cancel_why(o, b, now, tag == "paper") is None
    html = panel.render(tag, "t" * 40, now)
    top, _later, _ended = _parts(html)
    c = _btn(_row(top, "<b>卖 7203 トヨタ自動車：200 股</b>"), "cancel-order")
    assert c is not None and c["cid"] == cid and c["unsent"] == "1" and "还没发到交易所：撤了执行器就不再发" in c["hint"]
    ok, msg, _r = panel.submit({"book": tag, "kind": "cancel_order", "cid": cid}, now=now)
    assert ok, msg
    kind, why = LO._cancel_one(o, None, tag == "paper", now, "test", 1)        # 撤单的运行（单笔）：本地撤，不连券商
    assert kind == "done" and o["status"] == "CANCELLED" and "执行器不再重试" in why
    late = _t(2026, 10, 15, 9, 30)                                             # 08:55 之后：今天不会再发 → 不用撤
    assert LO.cancel_why(_blocked_sell(tag)["orders"][0], _blocked_sell(tag), late, tag == "paper") == "被挡、今天不会再发了（不在交易所）：不用撤"


def test_unsent_order_that_still_acts_but_cannot_be_cancelled_says_why():
    """模拟账户收盘后的「等开盘后」买单：明早的运行按今天的开盘价照旧撮合 → 收在「另有」、照算，撤不了 → 那一行写为什么。"""
    from test_panel import _book1015
    _book1015("paper", sell="SENT", cash=2_000_000.0, fix={})
    now = _t(2026, 10, 15, 16, 0)
    html = panel.render("paper", "t" * 40, now)
    _top, later, _ended = _parts(html)
    row = _row(later, "<b>买 1482 对冲版美国 7〜10 年国债：678 口</b>")
    assert "撤不了：已经收盘（15:30）：模拟账户等开盘后的买单明早的运行按今天的开盘价照旧撮合" in H.unescape(row)
    assert _btn(row, "cancel-order") is None
    sat = _t(2026, 10, 17, 12, 0)                                              # 周末：不写「不是今天的单」，写之后怎样
    _top, later, _ended = _parts(panel.render("paper", "t" * 40, sat))
    row = H.unescape(_row(later, "<b>买 1482 对冲版美国 7〜10 年国债：678 口</b>"))
    assert "撤不了：成交日 10/15 已过：之后的运行按那天的开盘价照旧撮合（钱够才买），现在撤不了" in row and "不是今天的单" not in row


# ────────── 「全部换成」同批（读了、等那次决策） ──────────
def test_read_allin_members_point_to_the_buy_line():
    tag = "paper"
    b = _etf_book(tag)
    at = "2026-10-16T18:00:00+09:00"
    b["manual"]["items"].update({
        "M-all-core": {"id": "M-all-core", "kind": "core", "pct": 0.0, "fund_for": "6501.T", "batch": "all", "status": "pending",
                       "at": at, "msg": "等「全部换成 6501 日立製作所」的决策一起生效"},
        "M-all-buy": {"id": "M-all-buy", "kind": "buy", "ticker": "6501.T", "unit": "shares", "value": 300, "fund": "all",
                      "status": "pending", "at": at}})
    _save(b, tag)
    now = _t(2026, 10, 17, 12, 0)
    html = panel.render(tag, "t" * 40, now)
    top, later, _ended = _parts(html)
    part = top + later
    assert "随「全部换成 6501 日立製作所」一起（撤回买入那条）" in part
    i = part.index("data-id='M-all-buy'")
    assert "data-act='cancel'" in part[part.rindex("<button", 0, i):i]
    _badge_ok(html, tag, now)


# ────────── 手机同一份 ──────────
def test_phone_page_has_the_same_buttons():
    _short_book("paper")
    now = _t(2026, 10, 17, 12, 0)
    from test_trade_today import REMOTE
    mac = _parts(panel.render("paper", "t" * 40, now))[1]
    ph = _parts(panel.render("paper", "t" * 40, now, **REMOTE))[1]
    assert _btn(mac, "fix-undo") == _btn(ph, "fix-undo") is not None
