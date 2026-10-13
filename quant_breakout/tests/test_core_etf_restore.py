"""核心 ETF 的「恢复」路径（2026-10-13 审计 core-etf 那一批）：固定口数的 ETF 不换算成闲置资金比例、盘中不按比例调它、
停买中的信号 / 规则现在不算它；「恢复按规则」/「确认买入」/「全部换成」之前的比例 —— 确认框与提交说明写清楚之后会怎样；
固定口数要加口数、现金不够 → 执行器先卖别的（不固定的）核心 ETF 补足（再平衡带以内也卖）。
两只核心 ETF（1545.T 美股牛熊 + 1482.T 股债相关；美股牛市时 1482 规则不拿），follow 模式。"""
import datetime as dt
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import pandas as pd

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.fees import etf_cost
from qbreak.live_unified import UnifiedExecutor, _MemPaper
from qbreak.unified import UnifiedConfig, UnifiedEngine

from test_live_unified import EX, P, _frame
from test_manual_now import _at, _quote
from test_panel import _js_fn

CC = {t: etf_cost("tachibana", t, "JP") for t in ("1545.T", "1482.T")}
CFG2 = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                     stock_markets=("JP",), core={"1545.T": 1.0, "1482.T": 1.0},
                     core_index={"1545.T": "US", "1482.T": "BR:BD"}, core_mode="follow")
PX2 = {"A.T": 1000.0, "B.T": 1500.0, "1545.T": 700.0, "1482.T": 1000.0}


def _paper2(tag: str = "paper", us_bear: bool = False, n: int = 30):
    a, b = _frame([1000.0] * n, entry=()), _frame([1500.0] * n)
    c1, c2 = _frame([700.0] * n), _frame([1000.0] * n)
    c1["entry"] = c2["entry"] = False
    idx = c1.index
    bear = {"US": pd.Series(bool(us_bear), index=idx), "BR:BD": pd.Series(True, index=idx)}   # 1482 规则不拿
    eng = UnifiedEngine({"A.T": a, "B.T": b, "1545.T": c1, "1482.T": c2}, CFG2, {"JP": P, "US": P}, EX, CC, bear=bear)
    br = _MemPaper(state_file=paths.state_dir() / f"paper_{tag}.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"], market="JP")
    now = {"t": None}
    ux = UnifiedExecutor(eng, br, paths.state_dir() / f"live_unified_{tag}.json", paper=True, check_clock=False,
                         clock=lambda: now["t"], manual_tag=tag)
    r = SimpleNamespace(eng=eng, b=br, now=now, ux=ux, k=int(eng.gidx.searchsorted(idx[5])), tag=tag)
    eng.prime(r.k)
    return r


def _morning(r, n: int = 1) -> None:
    for _ in range(n):
        r.now["t"] = dt.datetime.combine(next_trading_day(r.eng.gidx[r.k].date()), dt.time(7, 40), tzinfo=JST)
        r.ux.morning([r.k])
        r.k += 1


def _w(tag: str, rid: str, **rec) -> dict:
    rec = {"id": rid, "at": "x", "source": "test", **rec}
    with open(MO.requests_path(tag), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _units(r) -> dict:
    return {t: int(u) for t, u in r.eng.st.core_units.items()}


def _fixed_1482(r, units: int = 100, early: bool = True) -> None:
    """1482 固定 units 口（early：一开始全是现金时固定；否则先照规则全拿 1545 再固定）。"""
    if early:
        _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=units)
        _morning(r, 8)
    else:
        _morning(r, 8)
        _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=units)
    _morning(r, 2)


def _cfg(h: str) -> dict:
    return json.loads(re.search(r"<script type='application/json' id='qb-cfg'>(.*?)</script>", h, re.S).group(1))


def _save(r) -> None:
    r.ux.save(force=True)


# ────────── 执行器 ──────────
def test_rule100_is_recorded_and_clear_text_says_sell_all_when_the_rule_holds_none():
    """etf-restore-3：固定 1482 100 口、规则自己不拿（美股牛市）→ core_rule.rule100 = 0；「恢复按规则」的说明 = 下一次决策全部卖出（与执行器一致）。"""
    r = _paper2()
    _fixed_1482(r)
    cr = r.ux.book["core_rule"]
    assert _units(r)["1482.T"] == 100 and cr["units100"]["1482.T"] == 100
    assert cr["rule100"] == {"1482.T": 0} and cr["band_pct"] == 10.0
    txt = MO.corefix_clear_text(r.ux.book, "1482.T", r.tag, _at(r, 16, 0))
    assert txt.startswith("下一次决策（交易日 07:40）起这只 ETF 又按规则") and "规则现在不拿（熊市 / 换 ETF）→ 下一次决策全部卖出 100 口" in txt
    _w(r.tag, "M-clear-1482", kind="corefix", ticker="1482.T", clear=True)
    _morning(r)
    assert r.eng.st.core_plan.get("1482.T") == ["SELL", 100]


def test_fixed_buy_is_funded_by_selling_the_other_core_etf_inside_the_band():
    """etf-restore-9：1545 照规则拿满之后固定 1482 100 口（¥100,000 < 再平衡带 10%）→ 执行器在同一次决策里先卖 1545 补足，
    1482 一次买到、不被拒（以前 1545 在带内不卖 → 现金不够 → 每天被拒）。"""
    r = _paper2()
    _morning(r, 8)
    u0 = _units(r)["1545.T"]
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=100)
    _morning(r)
    plan = dict(r.eng.st.core_plan)
    assert plan.get("1482.T") == ["BUY", 100] and plan.get("1545.T", [""])[0] == "SELL"
    seen = list(r.ux.orders)
    _morning(r)
    seen += list(r.ux.orders)
    assert _units(r)["1482.T"] == 100 and _units(r)["1545.T"] == u0 - plan["1545.T"][1]
    assert not [o for o in seen if o.ticker == "1482.T" and o.status == "REJECTED"]


def test_no_fixed_etf_keeps_the_book_shape():
    """没有固定口数时 core_rule 不多出 rule100 / band_pct（回测 / 模拟盘不变）。"""
    r = _paper2()
    _morning(r, 8)
    assert "rule100" not in r.ux.book["core_rule"] and "band_pct" not in r.ux.book["core_rule"]


def test_sell_or_adjust_on_a_fixed_etf_only_changes_its_fixed_units():
    """etf-restore-1：固定的 ETF 上点「卖出全部」/「调仓…」/ 减仓 → 改它的固定口数（不换算成闲置资金比例：别的 ETF 不跟着变）。"""
    r = _paper2()
    _fixed_1482(r)
    b = r.ux.book
    held1545 = _units(r).get("1545.T", 0)
    assert held1545 > 0
    rec = MO.core_rec(MO.normalize({"kind": "sell", "ticker": "1482"}), b, r.tag)
    assert {k: rec[k] for k in ("kind", "ticker", "units", "from_kind")} == {"kind": "corefix", "ticker": "1482.T", "units": 0, "from_kind": "sell"}
    rec2 = MO.core_rec(MO.normalize({"kind": "adjust", "ticker": "1482", "unit": "shares", "value": 50}), b, r.tag)
    assert rec2["kind"] == "corefix" and rec2["units"] == 50 and rec2["from_kind"] == "adjust"
    try:
        MO.core_rec(MO.normalize({"kind": "adjust", "ticker": "1482", "unit": "shares", "value": 100}), b, r.tag)
        raise AssertionError("same units should be refused")
    except ValueError as e:
        assert "已经固定 100 口" in str(e)
    assert MO.check(rec, b, r.tag) is None
    assert [x[0] for x in MO.core_effects(b, 50.0)] == ["1545.T"]               # 比例只对不固定的 ETF
    assert "1482.T" in [x[0] for x in MO.core_effects(b, 0.0, keep_fixed=True)]
    w = MO.append(r.tag, rec)
    assert w["from_kind"] == "sell"                                       # append 重新整理之后也留着
    _morning(r)
    assert r.eng.st.core_plan.get("1482.T") == ["SELL", 100] and "1545.T" not in r.eng.st.core_plan
    _morning(r)
    assert _units(r).get("1482.T", 0) == 0 and _units(r)["1545.T"] == held1545
    assert float(r.ux.book["manual"]["core_pct"]) == 100.0 and "core_pause" not in r.ux.book["manual"]


def test_intraday_ratio_change_does_not_touch_the_fixed_etf():
    """etf-restore-2：停买中、1482 固定 → 盘中「按别的比例恢复」50% → 盘中只调不固定的 1545；1482 不动（第二天不再买回）。"""
    r = _paper2()
    _fixed_1482(r)
    _w(r.tag, "M-pause", kind="core", pct=0.0)
    _morning(r, 2)
    assert _units(r)["1482.T"] == 100 and _units(r).get("1545.T", 0) == 0
    _w(r.tag, "M-half", kind="core", pct=50.0)
    r.now["t"] = _at(r, 10, 0)
    r.ux.now_phase(_quote(PX2))
    now_orders = [(o.ticker, o.side) for o in r.ux.orders if o.reason == "manual_core"]
    assert now_orders and all(t == "1545.T" for t, _s in now_orders)
    _morning(r)
    assert _units(r)["1482.T"] == 100 and "1482.T" not in r.eng.st.core_plan


def test_fixing_while_paused_is_not_a_buy_signal_and_the_card_shows_it():
    """etf-restore-6：停买中固定一只规则不拿的 ETF → 不是「买入信号」；停买卡片的「规则现在」不算它，另起一行「手动固定 … 停买中也照买」。"""
    r = _paper2()
    _morning(r, 8)
    _w(r.tag, "M-pause", kind="core", pct=0.0)
    _morning(r, 2)
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=100)
    _morning(r)
    assert "core_signal" not in r.ux.book["manual"]
    assert not [e for e in r.ux.book["events"] if "买入信号" in e["msg"]]
    h = panel.render(r.tag, "tok", now=_at(r, 10, 0))
    j = h.index("规则现在：")
    assert "1482.T" not in h[j:j + 40]
    assert "手动固定 1482.T 100 口（停买中也照买）" in h


def test_signal_withdrawn_is_a_warning():
    """etf-restore-10：停买中出过买入信号、规则又不拿了 → 信号撤掉，事件是 warn（会通知）。"""
    r = _paper2(us_bear=True)
    _morning(r, 6)
    _w(r.tag, "M-pause", kind="core", pct=0.0)
    _morning(r, 2)
    r.ux.book["manual"]["core_signal"] = {"date": "2026-01-01", "items": [{"ticker": "1545.T", "units": 100, "px": 700.0, "yen": 70000}]}
    r.ux.manual.m["core_signal"] = r.ux.book["manual"]["core_signal"]
    r.ux.book["core_rule"]["units100"]["1545.T"] = 100
    _morning(r)
    ev = [e for e in r.ux.book["events"] if "已撤" in e["msg"] and "买入信号" in e["msg"]]
    assert ev and ev[-1]["level"] == "warn" and ev[-1]["msg"].endswith("已撤：规则又不拿了，继续停买")
    assert "core_signal" not in r.ux.book["manual"]


# ────────── 指令检查 / 说明 ──────────
def test_corefix_clear_is_refused_while_an_allin_batch_waits():
    """etf-restore-8：「全部换成」整批在等 → 「恢复按规则」也拦（以前先 return 了 → 漏过）。"""
    r = _paper2()
    _fixed_1482(r)
    at = "2026-10-13T08:00:00+09:00"
    _w(r.tag, "M-allin-buy", kind="buy", ticker="B.T", unit="shares", value=100, fund="all", at=at)
    _w(r.tag, "M-allin-fx", kind="corefix", ticker="1482.T", clear=True, fund_for="B.T", batch="all", prev_units=100, at=at)
    _w(r.tag, "M-allin-core", kind="core", pct=0.0, fund_for="B.T", batch="all", prev_pct=100.0, at=at)
    why = MO.check(MO.normalize({"kind": "corefix", "ticker": "1482", "clear": True}), r.ux.book, r.tag)
    assert why and "全部换成" in why


def test_clear_text_while_paused_and_with_todays_order():
    """etf-restore-3 / 4：停买中「恢复按规则」= 下一次决策全部卖出；今天开盘已排的单照常 + 撤单 + 下一次决策可能反向。"""
    r = _paper2()
    _morning(r, 8)
    _w(r.tag, "M-pause", kind="core", pct=0.0)
    _morning(r, 2)
    _w(r.tag, "M-fix-1545", kind="corefix", ticker="1545.T", units=500)
    _morning(r, 2)
    assert _units(r)["1545.T"] == 500
    txt = MO.corefix_clear_text(r.ux.book, "1545.T", r.tag, _at(r, 16, 0))
    assert "停买中（闲置资金比例 0%）→ 下一次决策全部卖出 500 口" in txt
    _w(r.tag, "M-clear-1545", kind="corefix", ticker="1545.T", clear=True)
    _morning(r)
    assert r.eng.st.core_plan.get("1545.T") == ["SELL", 500]
    r2 = _paper2("p2")                                                    # 今天 07:40 的决策已经排了固定的单 → 08:00 点「恢复按规则」
    _morning(r2, 8)
    _w(r2.tag, "M-fix-1545", kind="corefix", ticker="1545.T", units=1000)
    _morning(r2)
    plan = r2.eng.st.core_plan.get("1545.T")
    assert plan and plan[0] == "SELL"
    txt = MO.corefix_clear_text(r2.ux.book, "1545.T", r2.tag, _at(r2, 8, 0))
    assert f"今天开盘已排的 1545.T 卖 {plan[1]:,} 口照常（要不做：「今天的单」→ 撤单）；下一次决策起照规则，可能反向买卖" in txt
    assert "今天的单成交后约 1,000 口" in txt


def test_resume_when_the_rule_holds_nothing_or_already_traded_today():
    """etf-restore-5 / resume-other-10：规则不拿（熊市）→「确认买入」不会马上买（照写）；今天开盘已经卖了 → 明天开盘再买。"""
    r = _paper2(us_bear=True)
    _morning(r, 6)
    _w(r.tag, "M-pause", kind="core", pct=0.0)
    _morning(r, 2)
    ri = MO.resume_info(r.ux.book, r.tag, _at(r, 10, 0))
    assert ri["none"] and ri["text"].startswith("规则现在不拿 ETF：确认后不会马上买")
    h = panel.render(r.tag, "tok", now=_at(r, 10, 0))
    assert f"data-plan='{ri['text']}' data-act='core-resume'" in h and f"{ri['text']}。" in h
    ok, msg, _ = panel.submit({"book": r.tag, "kind": "core", "pct": 100}, _at(r, 10, 0))
    assert ok and msg.startswith("已写：确认买入（闲置资金比例 0% → 100%）→ 规则现在不拿 ETF：确认后不会马上买")
    r2 = _paper2("p2")
    _morning(r2, 8)
    _w(r2.tag, "M-pause", kind="core", pct=0.0)
    _morning(r2)                                                          # 07:40：决策 → 今天开盘卖 1545 全部
    ri = MO.resume_info(r2.ux.book, r2.tag, _at(r2, 10, 0))
    assert ri["late"] == ["1545.T"] and not ri["none"]
    assert ri["text"].startswith(f"确认后{ri['late_when']}照规则买入（1545.T 今天已经有执行器的单：盘中不再调）")
    h = panel.render(r2.tag, "tok", now=_at(r2, 10, 0))
    assert "停买：开盘卖出（你停的）" in h and "规则在开盘卖出（熊市 / 换 ETF）" not in h
    assert ri["late_when"] in panel.render(r2.tag, "tok", now=_at(r2, 10, 0))
    assert MO.resume_info(r2.ux.book, r2.tag, _at(r2, 16, 0))["late"] == []      # 收盘后写 = 下一次决策照常


# ────────── 面板 ──────────
def test_panel_fixed_etf_has_no_ratio_buttons_and_the_clear_button_explains():
    """etf-restore-1 / 3：固定的 ETF 下面没有「卖出全部 / 调仓…」（只有「固定口数…」）；CFG.cores 不含它；「恢复按规则」带说明。"""
    r = _paper2()
    _fixed_1482(r)
    h = panel.render(r.tag, "tok", now=_at(r, 10, 0))
    assert "data-act='core-sell' data-t='1482.T'" not in h and "data-act='core-sell' data-t='1545.T'" in h
    assert "手动固定：卖出 / 减仓 / 加仓用下面的「固定口数…」" in h
    assert "1482.T" not in _cfg(h)["cores"] and "1545.T" in _cfg(h)["cores"]
    m = re.search(r"data-plan='([^']*)' data-act='corefix-clear' data-t='1482.T'", h)
    assert m and "规则现在不拿（熊市 / 换 ETF）→ 下一次决策全部卖出 100 口" in m.group(1)


def test_panel_submit_texts_for_fixed_etf():
    """固定的 ETF 上点卖出 → 提交说明写「只改这只 ETF 的固定口数」；「恢复按规则」→ 写之后会怎样。"""
    r = _paper2()
    _fixed_1482(r)
    ok, msg, rec = panel.submit({"book": r.tag, "kind": "sell", "ticker": "1482"}, _at(r, 16, 0))
    assert ok and rec["kind"] == "corefix" and rec["units"] == 0 and "只改这只 ETF 的固定口数" in msg
    MO.requests_path(r.tag).unlink()
    ok, msg, rec = panel.submit({"book": r.tag, "kind": "corefix", "ticker": "1482", "clear": True}, _at(r, 16, 0))
    assert ok and msg.startswith("已写：1482.T 恢复按规则 → 下一次决策（交易日 07:40）起这只 ETF 又按规则")
    assert "下一次决策全部卖出 100 口" in msg


def test_panel_pause_card_after_allin_shows_the_previous_settings():
    """etf-restore-11（页面）：「全部换成」停的 → 卡片写出之前的比例 / 固定口数；0 < 比例 < 100 → 「恢复成 N%」按钮（点了才写）；固定口数不自动恢复。"""
    r = _paper2()
    _morning(r, 8)
    m = r.ux.book["manual"]
    m["core_pct"] = 0.0
    m["core_pause"] = {"since": "2026-10-13", "id": "M-ai-core", "ticker": None, "allin": "B.T", "prev_pct": 50.0, "prev_fix": {"1482.T": 100}}
    r.ux.manual.m.update(core_pct=0.0, core_pause=m["core_pause"])
    _save(r)
    h = panel.render(r.tag, "tok", now=_at(r, 16, 0))
    assert "「全部换成 B.T」之前：比例 50%、1482.T 固定 100 口" in h
    assert re.search(r"data-pct='50' data-plan='[^']*' data-act='core-restore'>恢复成 50%</button>", h)
    assert "固定口数不会自动恢复" in h
    assert not [x for x in MO.read_all(r.tag) if x.get("kind") == "core"]   # 只显示，什么都没写
    m["core_pause"]["prev_pct"] = 100.0
    r.ux.manual.m["core_pause"] = m["core_pause"]
    _save(r)
    h = panel.render(r.tag, "tok", now=_at(r, 16, 0))
    assert "data-act='core-restore'" not in h and "（比例 100% = 「确认买入」）" in h


# ────────── 页面脚本（node）──────────
def _node():
    return shutil.which("node")


def test_trade_js_restore_dialogs_and_fixed_funding_note():
    """「确认买入」/「恢复按规则」的确认框用服务器写的说明；「恢复成 N%」只在点了之后写 kind core pct N；
    固定口数加口数、现金不够 → 写清执行器先卖别的核心 ETF（最多到规则目标），不够 → ★ 钱可能不够。"""
    src = (paths.PROJECT_ROOT / "qbreak" / "static" / "trade.js").read_text(encoding="utf-8")
    assert "if(a==='core-restore'){" in src and "kind:'core', pct:v" in src
    assert "(d.plan || CFG.when+'买入；之后每天照规则调')" in src
    assert "(d.plan || '下一次决策起，这只 ETF 又按规则（美股牛熊 / 股债相关）自动买卖。')" in src
    node = _node()
    if not node:
        return
    cfg = {"fund": {"cash": 50000, "fix": ["1482.T"], "core_pct": 100,
                    "hold": [{"t": "1545.T", "kind": "core", "cur": 1000, "px": 700.0, "lot": 10},
                             {"t": "1482.T", "kind": "core", "cur": 0, "px": 1000.0, "lot": 1}], "busy": []},
           "cores": {"1545.T": {"cur": 1000, "u100": 800, "lot": 10}}}
    js = ("const CFG=" + json.dumps(cfg) + ";let FUND_MODE='core';const yen=n=>'¥'+Math.round(n).toLocaleString('ja-JP');\n"
          + _js_fn(src, "fundSplit") + "\n" + _js_fn(src, "fixFundNote")
          + "\nconsole.log(fixFundNote(100000,'1482.T').trim());console.log('|'+fixFundNote(40000,'1482.T')+'|');"
          + "console.log(fixFundNote(500000,'1482.T').trim());")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout.splitlines()
    assert out[0] == "现金不够的约 ¥50,000：执行器在那次决策里先卖别的核心 ETF 补足（在再平衡带以内也卖，最多卖到它们的规则目标）"
    assert out[1] == "||"
    assert out[2].startswith("★ 钱可能不够：还差约 ¥450,000，别的核心 ETF 最多能卖约 ¥140,000")


# ────────── 命令行 ──────────
def test_cli_sell_on_a_fixed_etf_and_clear_texts(capsys, monkeypatch):
    """命令行与面板同一个换算：固定的 ETF 上 sell → 固定 0 口（只改这只）；corefix --clear → 写之后会怎样。"""
    import run
    from qbreak import calendar_jp as CJ
    r = _paper2()
    _fixed_1482(r)
    monkeypatch.setattr(CJ, "now_jst", lambda: _at(r, 16, 0))
    n0 = len(MO.read_all("paper"))
    assert run.main(["manual", "sell", "1482", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "这只 ETF 是手动固定的：只改它的固定口数（别的 ETF 与闲置资金比例不变）" in out
    assert [(x["kind"], x.get("units"), x.get("from_kind")) for x in MO.read_all("paper")[n0:]] == [("corefix", 0, "sell")]
    assert run.main(["manual", "cancel", MO.read_all("paper")[-1]["id"], "--broker", "paper"]) == 0
    capsys.readouterr()
    assert run.main(["manual", "corefix", "1482", "--clear", "--broker", "paper"]) == 0
    assert "规则现在不拿（熊市 / 换 ETF）→ 下一次决策全部卖出 100 口" in capsys.readouterr().out


def test_cli_resume_when_the_rule_holds_nothing(capsys, monkeypatch):
    """停买中、规则不拿（熊市）→ manual core --pct 100 写进去，但说清不会马上买。"""
    import run
    from qbreak import calendar_jp as CJ
    r = _paper2(us_bear=True)
    _morning(r, 6)
    _w(r.tag, "M-pause", kind="core", pct=0.0)
    _morning(r, 2)
    monkeypatch.setattr(CJ, "now_jst", lambda: _at(r, 16, 0))
    assert run.main(["manual", "core", "--pct", "100", "--broker", "paper"]) == 0
    assert "确认买入：停买结束（闲置资金比例 0% → 100%）；规则现在不拿 ETF：确认后不会马上买" in capsys.readouterr().out
