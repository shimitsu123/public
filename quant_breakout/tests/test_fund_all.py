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

from test_panel import AT, _book, _js_fn, _sm


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
    assert [r["kind"] for r in rs] == ["buy"] + ["adjust"] * 4 + ["corefix", "core"]          # 先写买入（写到一半中断也不会只剩卖出）
    assert [r["ticker"] for r in rs[1:5]] == ["6758.T", "7203.T", "8306.T", "9432.T"] and all(r["value"] == 0 and r["unit"] == "shares" for r in rs[1:5])
    assert rs[5]["clear"] is True and rs[5]["ticker"] == "1545.T" and rs[5]["prev_units"] == 100
    assert rs[6]["pct"] == 0 and "ticker" not in rs[6] and rs[6]["prev_pct"] == 100.0
    assert all(r["fund_for"] == "6501.T" for r in rs[1:]) and all(r["at"] == rec["at"] for r in rs)
    assert "先全部卖出其他持仓：6758.T 100 股、7203.T 100 股、8306.T 100 股、9432.T 100 股" in msg
    assert "取消固定口数：1545.T（1545.T 100 → 0 口：之后按比例 0% 卖出）" in msg and "闲置资金比例 100% → 0%（1545.T 100 → 0 口；之后停买" in msg
    assert "全卖也不够 1 个单元就不买、留现金" in msg and "卖出的个股不设「不买回」" in msg and "这只明天开盘买" in msg
    assert len(MO.fund_companions(rec, rs)) == 6


def test_submit_all_allowed_when_slots_full_and_button_rendered():
    _book4()                                                                  # 4 / 4 只：名额满
    _sm()
    html = panel.render("paper", "t" * 40, AT)
    assert "data-full='1'" in html and ">全部换成这只…<" in html and "只能把其他持仓全部卖出来换这只" in html
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300}, AT)
    assert not ok and "名额已满" in msg
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and rec["fund"] == "all", msg


def test_submit_all_skips_core_when_pct_already_zero():
    _book4(core_pct=0.0)
    _sm()
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and not _reqs("core") and "闲置资金比例已经是 0%：1545.T 100 → 0 口（照旧卖出）" in msg


def test_fund_all_skips_exiting_and_blocks_on_unfinished_instruction():
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
    assert [t for t, _c, _p in plan["sells"]] == ["6758.T", "8306.T", "9432.T"] and plan["skip"][0][0] == "7203.T"
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and [r["ticker"] for r in _reqs("adjust")] == ["6758.T", "8306.T", "9432.T"]
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
    assert all(it[r["id"]]["status"] == "cancelled" for r in _reqs() if r["kind"] in ("adjust", "buy", "core", "corefix"))
    assert man.core_pct == 100.0 and man.m["core_fix"] == {"1545.T": 100}        # 读到之前撤回：比例 / 固定口数都没动


def test_cancel_read_split_buy_writes_one_cancel_per_companion():
    """回归（2026-10-13 读者发现）：执行器读过的凑钱卖出以前会被写两条撤回（指令文件 + 账本各算一次）。"""
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    b["state"]["cash_jpy"] = 0.0
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
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
    assert q["got"] == 2_600_000 + 740_400 and q["avail"] == int(50_000 + q["got"] * 0.995 * 0.99)
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
    assert r.eng.core_fix == {} and r.eng.st.core_plan["1655.T"] == ["SELL", want] or tuple(r.eng.st.core_plan["1655.T"]) == ("SELL", want)
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
    """命令行撤回（run.py manual cancel）与面板同一个函数：同批一起撤；撤销撤回也同批一起恢复；同批有一条已被处理 → 拒绝撤销。"""
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
    assert it[buy["id"]]["status"] == "pending" and all(it[r["id"]]["status"] == "pending" for r in _reqs("adjust"))
    assert it[cxl["id"]]["status"] == "voided" and man.core_pct == 0.0 and man.m["core_fix"] == {}   # 读到：比例 0% / 取消固定口数生效
    # 已被执行器读过（处理过）的撤回：撤销不了 → 整个拒绝
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    ok, msg, cxl2 = MO.cancel_request("paper", b, buy["id"], now=AT, source="cli")
    assert ok and "闲置资金比例 100% → 0% 已经生效，撤不了：要恢复把比例设回 100%" in msg and "1545.T 的固定口数已取消（撤不了）" in msg
    man = MO.Manual(b, "paper")
    man.ingest()                                                              # 这次的撤回被读到：买入与 4 条卖出 → 已撤回
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    ok, msg, _ = MO.uncancel_request("paper", b, cxl2["id"], now=AT)
    assert ok                                                                 # 买卖类被撤成「已撤回」的能恢复（同批 4 条卖出一起）
    assert "同批的 4 条" in msg


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
    assert r.item("M-all-a")["status"] == "placed" and r.item("M-all-buy")["status"] == "pending" and r.item("M-all-buy").get("hold")
    assert "明天早上的决策" in r.item("M-all-buy")["msg"] and res["later"] >= 1
    r.day()                                                                   # 明天 07:40：对账（A 已卖、1655 已卖）→ 决策：B 按全卖之后的钱买
    assert r.item("M-all-buy")["status"] == "placed" and int(r.eng.st.plan["B.T"][1]) == 600
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
    r.ux.morning([])                                                          # 同一决策的补单（--retry）
    assert r.item("M-all-a")["status"] == "placed" and r.item("M-all-buy")["status"] == "pending"
    assert r.item("M-all-buy").get("hold") and not r.item("M-all-buy").get("wait") and "下一次决策" in r.item("M-all-buy")["msg"]
    r.day()                                                                   # 今天开盘 A 卖掉；明天 07:40 决策：B 用全部的钱买
    assert r.item("M-all-buy")["status"] == "placed" and "A.T" not in r.eng.st.pos


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
    assert r.item("M-all-buy")["status"] == "rejected" and "决算前 2 天" in r.item("M-all-buy")["msg"] and "其他持仓不卖" in r.item("M-all-buy")["msg"]
    assert r.item("M-all-a")["status"] == "rejected" and "A.T" not in r.eng.st.pending_exit
    assert r.ux.manual.core_pct == 100.0 and r.eng.core_scale == 1.0 and r.eng.core_fix == {"1655.T": want} and r.ux.manual.m["core_fix"] == {"1655.T": want}
    r.day()
    assert "A.T" in r.eng.st.pos and int(r.eng.st.core_units["1655.T"]) == want
