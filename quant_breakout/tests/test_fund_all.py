"""买新股时把持仓拖到最大 = 其他持仓全部卖出、只拿这只 + 现金（2026-10-13 用户：「把持仓口数点满 = 把其他的股票都卖掉来买这个股票；
都卖掉不够最小口数金额的话就手持现金，不持有其他以外的股票 / ETF」）。
提交：个股 adjust → 0、固定口数取消、闲置资金比例 → 0%（卖出全部 + 停买）、最后买入（fund = all）；名额按卖完之后算；撤回买入时一起撤；
执行器：早上先卖后买，卖出所得撑起买入股数；全卖也不够 1 个单元 → 不买、留现金；早上读到的「取消固定口数」当天决策生效。"""
import dataclasses
import json
import shutil
import subprocess

import pytest

from qbreak import manual_orders as MO
from qbreak import panel

from test_panel import AT, _book, _card, _js_fn, _sm, _sm_nowarn


def _book4(**kw):
    """4 只个股 + 1545（100 口）+ 现金 ¥50 万；manual 带 core / core_fix。"""
    pos = {t: {"shares": 100, "entry_px": 2000.0, "entry_date": "2026-09-01", "stop_px": 1800.0, "last_close": 2100.0}
           for t in ("7203.T", "6758.T", "8306.T", "9432.T")}
    man = {"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"], **kw}
    b = _book(pos=pos, manual=man)
    b["state"]["core_last"] = {"1545.T": 250.0}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def _reqs(kind=None):
    rs = MO.read_all("paper")
    return [r for r in rs if kind is None or r["kind"] == kind]


def test_submit_all_writes_sells_corefix_core_then_buy():
    _book4(core_fix={"1545.T": 100})
    _sm()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and rec["fund"] == "all" and rec["value"] == 300, msg
    rs = _reqs()
    assert [r["kind"] for r in rs] == ["buy"] + ["sell"] * 4 + ["corefix", "core"]            # 先写买入；个股是「卖出全部」（不自动买回）
    assert [r["ticker"] for r in rs[1:5]] == ["6758.T", "7203.T", "8306.T", "9432.T"] and all(r["block_days"] == MO.BLOCK_DEFAULT for r in rs[1:5])
    assert rs[5]["clear"] is True and rs[5]["ticker"] == "1545.T" and rs[5]["prev_units"] == 100
    assert rs[6]["pct"] == 0 and "ticker" not in rs[6] and rs[6]["prev_pct"] == 100.0
    assert all(r["fund_for"] == "6501.T" for r in rs[1:]) and all(r["at"] == rec["at"] for r in rs)
    assert "执行时拿着的 6501.T 以外的个股和 ETF 全部卖出（包括写指令之后规则 / 别的指令买进的）；现在拿着的：6758.T 100 股、7203.T 100 股、8306.T 100 股、9432.T 100 股" in msg
    assert "取消固定口数：1545.T（1545.T 100 → 0 口：之后按比例 0% 卖出）" in msg and "闲置资金比例 100% → 0%（1545.T 100 → 0 口；之后停买" in msg
    assert "全卖也不够 1 个单元就不买、留现金" in msg and "之后 20 个交易日规则不自动买回；「交易」里可一次「恢复按规则」" in msg
    assert msg.startswith("已写：全部换成 6501.T → 10/07 开盘整批先卖后买")                 # 10/06 08:00、今天的决策已做 → 下一个交易日
    assert len(MO.fund_companions(rec, rs)) == 6


def test_submit_all_allowed_when_slots_full_and_button_rendered():
    _book4()                                                                  # 4 / 4 只：名额满
    _sm()
    html = panel.render("paper", "t" * 40, AT)
    sg, ab = _card(html, "suggest"), _card(html, "autobuy")                  # 两张卡各查（「规则接下来会自动买」点开的也是同一行，2026-10-14）
    assert "data-full='1'" in sg and ">全部换成这只…<" in sg and "只能把其他持仓全部卖出来换这只" in sg
    assert ab.count("data-full='1'") == ab.count("data-act='buy'") >= 1 and ">全部换成这只…<" in ab
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300}, AT)
    assert not ok and "名额已满" in msg
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and rec["fund"] == "all", msg


def test_submit_all_skips_core_when_pct_already_zero():
    _book4(core_pct=0.0)
    _sm()
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and not _reqs("core") and "闲置资金比例已经是 0%：1545.T 100 → 0 口（照旧卖出）" in msg


def test_fund_all_writes_exiting_and_blocks_on_unfinished_instruction():
    b = _book4()
    b["state"]["pending_exit"] = {"7203.T": "macd"}
    b["manual"]["items"] = {"M-trim": {"id": "M-trim", "kind": "trim", "ticker": "6758.T", "pct": 5.0, "status": "pending", "at": "2026-10-05T20:00:00+09:00"}}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    plan = MO.fund_all(b, "paper", "6501.T")
    assert plan["blocked"].startswith("6758.T 有没处理完的指令（M-trim）")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert not ok and "先撤回它" in msg
    b["manual"]["items"] = {}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    plan = MO.fund_all(b, "paper", "6501.T")
    assert [t for t, _c, _p in plan["sells"]] == ["6758.T", "7203.T", "8306.T", "9432.T"] and not plan["skip"]   # 规则在卖的也写（执行时只设「不买回」，2026-10-13）
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and [r["ticker"] for r in _reqs("sell")] == ["6758.T", "7203.T", "8306.T", "9432.T"], msg
    assert MO.fund_holdings(b, "paper")["exiting"] == ["7203.T"]


def test_cancel_all_buy_cancels_companions_before_executor_reads():
    _book4(core_fix={"1545.T": 100})
    _sm()
    ok, _m, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok
    html = panel.render("paper", "t" * 40, AT)
    i = html.index(f"data-id='{buy['id']}'")
    assert "data-fund='6'" in html[i:html.index("</button>", i)]
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel", "target": buy["id"]}, AT)
    assert ok and "为这笔买入写的 6 条卖出 / 闲置资金指令也撤回" in msg
    cancels = {r["target"] for r in _reqs("cancel")}
    assert len(cancels) == 7 and buy["id"] in cancels
    b = json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())
    man = MO.Manual(b, "paper")
    man.ingest()
    it = man.m["items"]
    assert all(it[r["id"]]["status"] == "cancelled" for r in _reqs() if r["kind"] in ("sell", "buy", "core", "corefix"))
    assert man.core_pct == 100.0 and man.m["core_fix"] == {"1545.T": 100}        # 读到之前撤回：比例 / 固定口数都没动


def test_cancel_read_split_buy_writes_one_cancel_per_companion():
    """回归（2026-10-13 读者发现）：执行器读过的凑钱卖出以前会被写两条撤回（指令文件 + 账本各算一次）。"""
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    b["state"]["cash_jpy"] = 0.0
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm_nowarn()
    ok, _m, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300,
                                "fund": {"mode": "split", "cost": 150_000}}, AT)
    assert ok and len(_reqs("adjust")) == 1
    p = panel.paths.state_dir() / "live_unified_paper.json"
    b = json.loads(p.read_text())
    MO.Manual(b, "paper").ingest()                                            # 执行器读了（买入与凑钱的卖出都 pending）
    p.write_text(json.dumps(b), encoding="utf-8")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel", "target": buy["id"]}, AT)
    assert ok and "为它凑钱的 1 条卖出也撤回" in msg
    assert len(_reqs("cancel")) == 2


def test_js_fund_all_preview_and_alloc():
    """页面的「其他全部卖出」：每只 → 0，买入后只有这只 + 现金（两条占比都合计 100%）；买不起 1 个单元时 n = 0。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    J = panel._JS
    fns = "\n".join(_js_fn(J, n) for n in ("nd", "fundSplit", "fundAll", "allocViz"))
    cfg = {"fund": {"cash": 50_000, "busy": ["8306.T"], "exiting": [],
                    "hold": [{"t": "7203.T", "kind": "stock", "cur": 1000, "px": 2600.0, "lot": 100}, {"t": "8306.T", "kind": "stock", "cur": 500, "px": 1900.0, "lot": 100},
                             {"t": "1545.T", "kind": "core", "cur": 3000, "px": 246.8, "lot": 10}], "core_pct": 100, "fix": []},
           "alloc": {"names": {"7203.T": "トヨタ"}, "colors": ["#4c7bf3", "#f0a030", "#9b6cf0", "#20a8a0"]}}
    js = """
class El { constructor(t){ this.children=[]; this._t=''; this.className=''; this.style={}; }
  appendChild(c){ this.children.push(c); return c; } set textContent(v){ this._t=String(v); this.children=[]; } get textContent(){ return this._t; } }
const document={createElement:t=>new El(t)};
let FUND_MODE='all'; const CFG=__CFG__;
__FNS__
const q=fundAll('6501.T', 2000, 100);
const el=new El('div'); allocViz(el, q.buy, '6501.T', q);
const box=el.children[0], bars=box.children.filter(c=>c.className==='avr').map(r=>r.children[1].children.map(i=>parseFloat(i.style.width)));
const leg=box.children.find(c=>c.className==='all').children.map(r=>[r.children[1].textContent, r.children[2].textContent]);
const q0=fundAll('6501.T', 9000000, 100);
console.log(JSON.stringify({q:q, bars:bars, leg:leg, n0:q0.n, buy0:q0.buy}));
""".replace("__CFG__", json.dumps(cfg)).replace("__FNS__", fns)
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    o = json.loads(r.stdout)
    q = o["q"]
    assert [x["t"] for x in q["rows"]] == ["7203.T", "1545.T"] and all(x["after"] == 0 for x in q["rows"]) and q["keep"][0]["t"] == "8306.T"
    assert q["got"] == 2_600_000 + 740_400 and q["avail"] == int(50_000 / 0.99 + q["got"] * 0.995)    # 不留 1% 现金缓冲
    assert q["n"] == (q["avail"] // (2000 * 1.005)) // 100 * 100 and q["buy"] == q["n"] * 2000 and q["n"] >= 1500
    assert [round(sum(b)) for b in o["bars"]] == [100, 100]
    leg = dict(o["leg"])
    assert leg["7203 トヨタ"].endswith("→ 0.0%") and leg["1545"].endswith("→ 0.0%") and leg["6501（新）"].startswith("0.0% → ")
    assert float(leg["6501（新）"].split("→ ")[1].rstrip("%")) > 70 and not leg["8306"].endswith("→ 0.0%")   # 留着的那只（8306 约 ¥95 万）不变
    assert o["n0"] == 0 and o["buy0"] == 0                                       # 全卖也不够 100 股 → 不买


# ────────── 执行器（立花适配器 + 模拟交易所；tests/test_manual_orders._Run）──────────
def test_executor_morning_sells_everything_then_buys_with_the_proceeds():
    from test_manual_buy import _write
    from test_manual_orders import TAG, _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    a_sh = int(r.eng.st.pos["A.T"].shares)
    u = int(r.eng.st.core_units["1655.T"])
    cash0 = float(r.eng.st.cash_jpy)
    assert a_sh > 0 and u > 0 and cash0 < 100_000                                 # 现金不多：买入要靠卖出所得
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "source": "test", "id": "M-all-core", "at": at})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    r.day()
    assert r.item("M-all-a")["status"] == "placed" and r.eng.st.pending_exit.get("A.T") == "manual"
    assert r.item("M-all-buy")["status"] == "placed" and "全部换成这只（按总权益）" in r.item("M-all-buy")["msg"]
    sh = int(r.eng.st.plan["B.T"][1])
    assert sh == 600 and sh * 1500 > 5 * cash0                                   # B.T ¥1,500：总权益约 ¥100 万 → 最多 600 股；只靠现金连 1 个单元都买不起
    side, n = r.eng.st.core_plan["1655.T"]
    assert side == "SELL" and n == u                                              # 比例 0%：核心 ETF 全部卖
    r.day()
    assert set(r.eng.st.pos) == {"B.T"} and int(r.eng.st.pos["B.T"].shares) == sh and r.eng.st.core_units.get("1655.T", 0) == 0
    assert r.item("M-all-buy")["status"] == "done" and r.ux.manual.core_pct == 0.0


def test_executor_all_in_but_cannot_afford_one_unit_keeps_cash():
    from test_manual_buy import _write
    from test_manual_orders import TAG, _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "source": "test", "id": "M-all-core", "at": at})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    j = r.eng.col["B.T"]
    r.eng.A.close[:, j] = 50_000.0                                                # B.T 一手 ¥500 万：全卖也买不起
    r.eng.A.open[:, j] = 50_000.0
    r.day()
    assert r.item("M-all-buy")["status"] == "rejected" and "不够买 1 个单元" in r.item("M-all-buy")["msg"]
    assert r.item("M-all-a")["status"] == "placed" and r.eng.st.core_plan["1655.T"][0] == "SELL"
    r.day()
    assert not r.eng.st.pos and r.eng.st.core_units.get("1655.T", 0) == 0 and r.eng.st.cash_jpy > 900_000   # 全现金


def test_morning_applies_corefix_clear_in_the_same_decision():
    """2026-10-13 修：早上读到的「取消固定口数」以前要到下一次决策才生效（eng.core_fix 只在启动时读一次）。"""
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=())
    r.until(14)
    u = int(r.eng.st.core_units["1655.T"])
    want = (u // 2 // 10) * 10
    r.ask(kind="corefix", ticker="1655", units=want)
    r.day()
    assert r.eng.st.core_plan.get("1655.T", ("", 0))[0] == "SELL" and r.eng.core_fix == {"1655.T": want}
    r.day()
    assert int(r.eng.st.core_units["1655.T"]) == want
    r.ask(kind="corefix", ticker="1655", clear=True)
    r.ask(kind="core", pct=0)
    r.day()
    assert r.eng.core_fix == {}
    assert tuple(r.eng.st.core_plan["1655.T"]) == ("SELL", want)
    r.day()
    assert r.eng.st.core_units.get("1655.T", 0) == 0


def test_submit_all_refused_when_executor_would_block_the_buy():
    """决算前 / 新仓倍数 0（面板只警告的）：「其他全部卖出」不让提交（否则卖光了却不买）。"""
    _book4()
    _sm([{"ticker": "6501.T", "code": "6501", "name": "日立", "status": "watch", "signal": False,
          "buy": {"block": None, "warn": ["决算前 2 天"], "em": 1.0, "lot": 100, "px": 3500.0, "limit": 3605.0, "rule_shares": 200}}])
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert not ok and "会被执行器挡下" in msg and not _reqs()


def test_cli_cancel_helper_cancels_companions_and_uncancel_restores_all():
    """命令行撤回（run.py manual cancel）与面板同一个函数：同批一起撤；撤销撤回也同批一起恢复；单独撤销同批某条 → 拒绝。
    同批的比例 / 固定口数在执行器读到时只是「等决策一起生效」（pending）→ 读到之后也能撤。"""
    _book4(core_fix={"1545.T": 100})
    _sm()
    ok, _m, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok
    b = json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())
    ok, msg, cxl = MO.cancel_request("paper", b, buy["id"], now=AT, source="cli")
    assert ok and "为这笔买入写的 6 条卖出 / 闲置资金指令也撤回" in msg and len(_reqs("cancel")) == 7
    ok, msg, un = panel.submit({"book": "paper", "kind": "uncancel", "target": cxl["id"]}, AT)
    assert ok and "同批的 6 条卖出 / 闲置资金指令一起恢复" in msg and len(_reqs("uncancel")) == 7
    assert MO.cancelled(MO.unseen("paper", b)) == set()                         # 7 条撤回都被撤销 → 一条都不算撤回中
    man = MO.Manual(b, "paper")
    man.ingest()
    it = man.m["items"]
    assert it[buy["id"]]["status"] == "pending" and all(it[r["id"]]["status"] == "pending" for r in _reqs("sell"))
    assert it[cxl["id"]]["status"] == "voided"
    core = next(r for r in _reqs("core")); fix = next(r for r in _reqs("corefix"))
    assert it[core["id"]]["status"] == "pending" and it[fix["id"]]["status"] == "pending"   # 读到但不生效：等决策一起
    assert man.core_pct == 100.0 and man.m["core_fix"] == {"1545.T": 100}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    # 读到之后撤回：同批 6 条都还是 pending → 都能撤
    ok, msg, cxl2 = MO.cancel_request("paper", b, buy["id"], now=AT, source="cli")
    assert ok and "为这笔买入写的 6 条" in msg
    # 单独撤销同批某条的撤回 → 拒绝（要整批跟着买入那条）
    c_adj = [r for r in _reqs("cancel") if r["target"] == _reqs("sell")[0]["id"]][-1]      # 第二批的那条（第一批的已撤销）
    ok, msg, _ = MO.uncancel_request("paper", b, c_adj["id"], now=AT)
    assert not ok and "同批指令：要恢复请撤销买入那条的撤回" in msg
    html = panel.render("paper", "t" * 40, AT)
    i = html.index(f"data-id='{cxl2['id']}'")
    assert "data-act='uncancel'" in html[i - 60:i + 10] or f"data-act='uncancel' data-id='{cxl2['id']}'" in html   # 买入那条的撤回有按钮
    assert f"data-act='uncancel' data-id='{c_adj['id']}'" not in html                     # 同批那条没有


def test_cancel_refused_once_batch_sells_are_at_the_exchange():
    """立花账本：07:40 决策已把同批卖单发到交易所（寄付）→ 只撤买入会变成「全卖不买」→ 拒绝，提示先用「撤单」撤卖单。"""
    from test_manual_buy import _write
    from test_manual_orders import TAG, _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    r.day()                                                                   # 决策：A 寄付卖单已发出、核心 ETF 卖单已发出、买入 DEFERRED
    assert r.item("M-all-a")["status"] == "placed" and r.item("M-all-buy")["status"] == "placed"
    r.ux.save()
    book = json.loads((panel.paths.state_dir() / "book.json").read_text())
    ok, msg, _ = MO.cancel_request(TAG, book, "M-all-buy", now=r.at(r.k - 1, 8, 0), source="cli")
    assert not ok and "还挂在交易所" in msg and "全卖不买" in msg
    plan = MO.cancel_plan(TAG, book, "M-all-buy", now=r.at(r.k - 1, 8, 0))
    assert [c["id"] for c in plan["sent"]] == ["M-all-a", "M-all-core"] and not plan["todo"]      # 比例 0% 这次决策已生效、核心卖单挂着 → 也算
    for o in book["orders"]:                                                    # 用户照提示在「今天的单」把卖单都撤了
        if o["side"] == "SELL":
            o["status"] = "CANCELLED"
    ok, msg, _ = MO.cancel_request(TAG, book, "M-all-buy", now=r.at(r.k - 1, 8, 5), source="cli")
    assert ok, msg                                                              # 撤掉之后就能撤回（以前照样被拒）


def test_uncancel_clears_cancel_req_so_next_decision_really_buys():
    """回归（第二轮审计）：撤销撤回后 cancel_req 残留 → 下一次决策执行器自己又撤一次。"""
    from test_manual_buy import _write
    from test_manual_orders import TAG, _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100, "source": "test", "id": "M-buy-plain", "at": at})
    r.day()
    assert r.item("M-buy-plain")["status"] == "placed"
    r.ux.save()
    book = json.loads((panel.paths.state_dir() / "book.json").read_text())
    ok, _m, cxl = MO.cancel_request(TAG, book, "M-buy-plain", now=r.at(r.k - 1, 8, 0), source="cli")
    assert ok, _m
    r.now["t"] = r.at(r.k - 1, 8, 0)
    r.ux.morning([])                                                          # 补单：读到撤回 → 这笔买入不下
    assert r.item("M-buy-plain")["status"] == "cancelled"
    r.ux.save()
    book = json.loads((panel.paths.state_dir() / "book.json").read_text())
    ok, msg_u, _u = MO.uncancel_request(TAG, book, cxl["id"], now=r.at(r.k - 1, 8, 30), source="cli")
    assert ok, msg_u
    r.day()                                                                   # 下一次决策：恢复的买入真的下单（不再被 settle 撤）
    assert r.item("M-buy-plain")["status"] == "placed" and "cancel_req" not in r.item("M-buy-plain")
    r.day()
    assert "B.T" in r.eng.st.pos and r.item("M-buy-plain")["status"] == "done"


def test_submit_message_says_when_the_batch_runs():
    _book4()
    _sm()
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}},
                              AT.replace(hour=10))                             # 盘中：下一个交易日
    assert ok and msg.startswith("已写：全部换成 6501.T → 10/07 开盘整批先卖后买") and "马上（盘中）买入" not in msg
    MO.requests_path("paper").unlink()                                        # 上一条买入还在等 → 清掉再写
    b = _book4()
    b["state"]["last_date"] = "2026-10-02"                                    # 今天 08:00、今天的决策还没做 → 今天开盘
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and msg.startswith("已写：全部换成 6501.T → 今天 09:00 开盘整批先卖后买")
    assert MO.describe({"kind": "buy", "ticker": "6501.T", "unit": "shares", "value": 300, "fund": "all"}) == "全部换成这只 6501.T（其他全卖；股数由执行器按全卖之后的钱定）"


def test_add_room_and_manual_sizing_exclude_cash_hold():
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    i = r.k - 1
    room0 = r.eng.add_room("B.T", i)
    eq0 = MO.Manual._numbers(r.eng, i, "B.T")[0]
    r.eng.cash_hold = 300_000.0
    assert r.eng.add_room("B.T", i) <= room0 - 100 and MO.Manual._numbers(r.eng, i, "B.T")[0] == eq0   # % 目标仍按总权益换算
    r.eng.cash_hold = 0.0


def test_executor_intraday_all_in_sells_today_and_buys_next_morning():
    """盘中写的「全部换成这只」：其他持仓今天卖，这只推到明天早上的决策（卖出所得都算进去），不会按手头现金少买 / 被拒。"""
    from test_manual_buy import _write
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    u = int(r.eng.st.core_units["1655.T"])
    at = r.at(r.k, 10, 0).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    res = r.session(10, 0)
    assert r.item("M-all-a")["status"] == "pending" and r.item("M-all-a").get("hold") and "一起" in r.item("M-all-a")["msg"]   # 同批卖出也等
    assert r.item("M-all-buy")["status"] == "pending" and r.item("M-all-buy").get("hold") and res["later"] >= 2
    assert r.item("M-all-core")["status"] == "pending" and r.ux.manual.core_pct == 100.0   # 比例也等那次决策
    assert "A.T" in r.eng.st.pos and r.eng.st.core_units["1655.T"] == u                 # 今天什么都没卖
    r.day()                                                                   # 明天 07:40 决策：闸门过 → 比例 0% 生效、A 待卖、B 按全卖之后的钱买
    assert r.item("M-all-buy")["status"] == "placed" and int(r.eng.st.plan["B.T"][1]) == 600 and r.ux.manual.core_pct == 0.0
    assert r.eng.st.pending_exit.get("A.T") == "manual" and r.eng.st.core_plan["1655.T"][0] == "SELL"
    r.day()
    assert set(r.eng.st.pos) == {"B.T"} and r.eng.st.core_units.get("1655.T", 0) == 0 and r.item("M-all-buy")["status"] == "done"


def test_executor_retry_window_all_in_holds_buy_to_next_decision():
    """07:40 之后、08:55 之前写的：卖出进今天的寄付单，买入不等 09:00 盘中下（钱还没到），留到下一次决策。"""
    from test_manual_buy import _write
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    at = r.at(r.k - 1, 8, 0).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    r.now["t"] = r.at(r.k - 1, 8, 0)
    r.ux.morning([])                                                          # 同一决策的补单（--retry）：整批等下一次决策
    assert r.item("M-all-a")["status"] == "pending" and r.item("M-all-a").get("hold") and r.item("M-all-buy")["status"] == "pending"
    assert r.item("M-all-buy").get("hold") and not r.item("M-all-buy").get("wait") and "下一次决策" in r.item("M-all-buy")["msg"]
    r.day()                                                                   # 今天开盘什么都不动；明天 07:40 决策：先卖后买
    assert "A.T" in r.eng.st.pos and r.item("M-all-buy")["status"] == "placed" and r.eng.st.pending_exit.get("A.T") == "manual"
    r.day()
    assert set(r.eng.st.pos) == {"B.T"}


def test_executor_gate_rejects_all_in_buy_then_nothing_is_sold_and_settings_restored():
    """买入被闸门挡（例：决算前）→ 同批的卖出作废、闲置资金比例 / 固定口数还原：什么都不卖。"""
    from test_manual_buy import _write
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(13)
    u = int(r.eng.st.core_units["1655.T"])
    want = (u // 2 // 10) * 10
    r.ask(kind="corefix", ticker="1655", units=want)
    r.day()
    assert r.eng.core_fix == {"1655.T": want}
    base = r.eng.entry_block_fn
    r.eng.entry_block_fn = lambda t, i, _b=base: "决算前 2 天" if t == "B.T" else (_b(t, i) if _b else None)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "corefix", "ticker": "1655.T", "clear": True, "fund_for": "B.T", "source": "test", "id": "M-all-fix", "at": at, "prev_units": want})
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    r.day()
    assert r.item("M-all-buy")["status"] == "rejected" and "决算前 2 天" in r.item("M-all-buy")["msg"] and "整批不做" in r.item("M-all-buy")["msg"]
    assert r.item("M-all-a")["status"] == "rejected" and "A.T" not in r.eng.st.pending_exit
    assert r.item("M-all-core")["status"] == "rejected" and r.item("M-all-fix")["status"] == "rejected"   # 比例 / 固定口数从没生效过
    assert r.ux.manual.core_pct == 100.0 and r.eng.core_scale == 1.0 and r.eng.core_fix == {"1655.T": want} and r.ux.manual.m["core_fix"] == {"1655.T": want}
    r.day()
    assert "A.T" in r.eng.st.pos and int(r.eng.st.core_units["1655.T"]) == want


# ────────── 第三轮审计的回归 ──────────
def test_pending_batch_core_not_mistaken_for_rule_core_sell_at_exchange():
    """同批的比例 0% 还没生效：规则自己当天的核心 ETF 卖单（SENT / FILLED）不算「同批卖单已在交易所」→ 能撤回整批。"""
    b = _book4()
    b["state"]["last_date"] = "2026-10-05"
    b["orders"] = [{"cid": "U2026-10-05-SELL-1545.T", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 50, "decided_on": "2026-10-05",
                    "status": "SENT", "reason": "核心 ETF 调整"}]
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    ok, _m, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT.replace(hour=20))
    assert ok
    plan = MO.cancel_plan("paper", b, buy["id"], now=AT.replace(hour=20, minute=5))
    assert not plan["sent"] and len(plan["todo"]) == 5
    html = panel.render("paper", "t" * 40, AT.replace(hour=20, minute=5))
    i = html.index(f"data-id='{buy['id']}'")
    assert "data-act='cancel'" in html[html.rindex("<button", 0, i):i]
    assert "随「全部换成 6501.T」一起（撤回买入那条）" in html                     # 同批的单条不给撤单按钮


def test_second_allin_and_core_change_refused_while_batch_waits():
    _book4()
    _sm()
    ok, _m, _b = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert not ok and "同时只能有一个「全部换成」" in msg
    ok, msg, _ = panel.submit({"book": "paper", "kind": "core", "pct": 50}, AT)
    assert not ok and "在等决策" in msg
    assert MO.core_pct_now("paper", json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())) == 100.0   # 整批的 0% 等决策
    adj = _reqs("sell")[0]
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel", "target": adj["id"]}, AT)
    assert not ok and "撤回买入那条（整批一起撤）" in msg


def test_split_companion_can_still_be_cancelled_and_restored_alone():
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm_nowarn()
    ok, _m, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300, "fund": {"mode": "split", "cost": 645_000}}, AT)
    adj = _reqs("adjust")[0]
    ok, msg, cx = panel.submit({"book": "paper", "kind": "cancel", "target": adj["id"]}, AT)
    assert ok, msg
    ok, msg, _ = panel.submit({"book": "paper", "kind": "uncancel", "target": cx["id"]}, AT)
    assert ok, msg


def test_due_not_true_for_held_batch():
    """07:40 之后写的「全部换成」：MO.due 不再一直为真（以前面板每 3 分钟叫一次 --retry）。"""
    b = _book4()
    b["state"]["last_date"] = "2026-10-05"
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    ok, _m, _b = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and not MO.due("paper", b, AT)                                    # 还没读：整批只在决策里做
    man = MO.Manual(b, "paper")
    man.ingest()
    for it in man.m["items"].values():                                         # 补单把整批 hold 住
        it["hold"] = AT.date().isoformat()
    assert not MO.due("paper", b, AT)


def test_allin_when_follows_last_decision_bar_across_holidays():
    import datetime as dt
    from qbreak.calendar_jp import JST
    bk = lambda last: {"state": {"last_date": last}}                            # noqa: E731
    at = lambda d, h, m=0: dt.datetime.combine(dt.date.fromisoformat(d), dt.time(h, m), tzinfo=JST)   # noqa: E731
    assert MO.allin_when(at("2026-10-12", 10), bk("2026-10-09")) == "10/14 开盘"          # 体育の日 07:40 已决策 10/09（成交 10/13）→ 下一次 10/14
    assert MO.allin_when(at("2026-10-14", 7, 0), bk("2026-10-09")) == "今天 09:00 开盘"   # 10/14 07:40 之前：今天
    assert MO.allin_when(at("2026-10-14", 8, 56), bk("2026-10-09")) == "10/15 开盘"       # 过了 08:55：寄付来不及
    assert MO.allin_when(at("2026-10-14", 8, 0), bk("2026-10-13")) == "10/15 开盘"        # 今天的决策已做
    assert MO.allin_when(at("2026-10-16", 20), bk("2026-10-15")) == "10/19 开盘"          # 周五晚上 → 周一 07:40 决策周五那根 → 周一开盘


def test_blocked_run_keeps_batch_untouched():
    """那次运行不下单（行情落后 / 冒烟测试）：整批不动（比例不生效、个股不进待卖），下一次能下单的决策再做。"""
    from test_manual_buy import _write
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    r.ux.block("测试：行情落后")
    r.day()
    assert r.item("M-all-buy")["status"] == "pending" and r.item("M-all-core")["status"] == "pending" and r.item("M-all-a")["status"] == "pending"
    assert "A.T" not in r.eng.st.pending_exit and r.ux.manual.core_pct == 100.0 and "B.T" not in r.eng.st.plan
    r.ux.blocked = None
    r.day()
    assert r.item("M-all-buy")["status"] == "placed" and r.ux.manual.core_pct == 0.0 and r.eng.st.pending_exit.get("A.T") == "manual"


def test_orphan_batch_members_rejected_when_buy_ended():
    """买入在闸门之外结束（例：被单独拒掉）→ 同批还 pending 的卖出 / 比例一律作废，不单独执行。"""
    from test_manual_buy import _write
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    r.ux.manual.ingest()
    r.item("M-all-buy").update(status="rejected", msg="测试：买入在别处结束")
    r.day()
    assert r.item("M-all-a")["status"] == "rejected" and r.item("M-all-core")["status"] == "rejected"
    assert "A.T" not in r.eng.st.pending_exit and r.ux.manual.core_pct == 100.0


def test_batch_written_in_one_write():
    _book4()
    _sm()
    ok, _m, _b = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and all(r.get("batch") == "all" for r in _reqs() if r["kind"] != "buy") and len({r["at"] for r in _reqs()}) == 1


def test_allin_sells_set_no_rebuy_and_batch_unblock_restores_rule():
    """2026-10-13 用户：「卖出的个股设『不买回』，需要一个回到规则的 button」—— 整批执行后个股 20 个交易日不自动买回；
    「交易」里按批一次「恢复按规则」（解除这一批的全部）。"""
    from test_manual_buy import _write
    from test_manual_orders import TAG, _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "sell", "ticker": "A.T", "block_days": 20, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-a", "at": at})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    r.day()
    blk = r.ux.manual.m["blocks"]
    assert "A.T" in blk and blk["A.T"]["id"] == "M-all-a" and blk["A.T"]["until"]
    r.ux.save()
    book = json.loads((panel.paths.state_dir() / "book.json").read_text())
    g = MO.batch_blocks(book)                                                  # 一批一条（2026-10-13：带设定 id，设定换了不动新的）
    assert len(g) == 1 and g[0]["x"] == "B.T" and [(m["t"], m["id"]) for m in g[0]["members"]] == [("A.T", "M-all-a")]
    assert blk["A.T"]["fund_for"] == "B.T" and blk["A.T"]["batch_at"] == at              # 批的身份记在设定里（指令被裁掉也认得）


def test_panel_batch_unblock_button_and_submit():
    b = _book4()
    b["manual"]["items"] = {
        "M-x-a": {"id": "M-x-a", "kind": "sell", "ticker": "7203.T", "fund_for": "6501.T", "batch": "all", "status": "done", "at": "2026-10-05T06:00:00+09:00"},
        "M-x-b": {"id": "M-x-b", "kind": "sell", "ticker": "6758.T", "fund_for": "6501.T", "batch": "all", "status": "done", "at": "2026-10-05T06:00:00+09:00"},
        "M-y": {"id": "M-y", "kind": "sell", "ticker": "8306.T", "status": "done", "at": "2026-10-04T06:00:00+09:00"}}
    b["manual"]["blocks"] = {"7203.T": {"until": "2026-11-02", "since": "2026-10-05", "id": "M-x-a"},
                             "6758.T": {"until": "2026-11-02", "since": "2026-10-05", "id": "M-x-b"},
                             "8306.T": {"until": "2026-11-01", "since": "2026-10-04", "id": "M-y"}}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    html = panel.render("paper", "t" * 40, AT)
    assert "data-act='unblock-batch' data-ids='6758.T:M-x-b,7203.T:M-x-a'" in html and ">恢复按规则<" in html
    assert html.count("data-act='unblock' data-t=") == 3                        # 单只的「解除」照旧
    assert "a==='unblock-batch'" in panel._JS
    ok, msg, _ = panel.submit({"book": "paper", "kind": "unblock", "ticker": "6758.T", "tickers": ["6758.T", "7203.T"]}, AT)
    assert ok and "恢复按规则 → 解除 6758.T、7203.T" in msg and msg.endswith("→ 下一次决策（交易日 07:40）起生效")
    assert [r["ticker"] for r in _reqs("unblock")] == ["6758.T", "7203.T"] and len({r["at"] for r in _reqs("unblock")}) == 1
    man = MO.Manual(b, "paper")
    man.ingest()                                                               # 读到不马上去掉：记下从哪一次决策起不挡（2026-10-13）
    bl = man.m["blocks"]
    assert set(bl) == {"6758.T", "7203.T", "8306.T"} and "lift_from" not in bl["8306.T"]
    assert bl["6758.T"]["lift_from"] == bl["7203.T"]["lift_from"] == "2026-10-07"      # 10/06 08:00 写 → 10/07 07:40 的决策起


def test_allin_buy_uses_all_money_without_cash_buffer():
    """2026-10-13 用户：「拖到最大」股数不留 1% 现金缓冲：add_room(buffer=False) 按全部的钱算（手续费 / 滑点照算）。"""
    from test_manual_orders import _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    i = r.k - 1
    assert r.eng.add_room("B.T", i, buffer=False) >= r.eng.add_room("B.T", i)
    st = r.eng.st
    pool = st.cash_jpy + r.eng._core_liq(i) + sum(r.eng._sell_net(x, i) for x in st.pending_exit if x in st.pos)
    px = r.eng._px_close("B.T", i) * (1 + r.eng.slip["JP"])
    n = r.eng.add_room("B.T", i, buffer=False)
    assert n * px <= pool and (n + 100) * px + r.eng.fees["JP"]((n + 100) * px) > pool      # 最后一手：再多 100 股就不够
