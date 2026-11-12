"""持仓最上面「★ 持仓出了卖出信号」（2026-10-18 用户：「持仓里面还要做一个现在如果有持仓股票出了卖出信号的话也要进行提示」；只展示）：
① 规则已经判卖（pending_exit）→ 哪天开盘卖 + 那笔单怎样；你自己写的卖出 / 减仓不算；
② 盘中暂定（盘中观测越过收盘卖出线）→ 那根 K 线执行器已经决策过就不再写；没有 → 卡藏起来；/api/intraday 带同一份（页面每分钟更新）。"""
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import intraday_watch as IW                                      # noqa: E402
from qbreak import panel, paths                                              # noqa: E402

from test_intraday_watch import AT, _fetcher, _setup                         # noqa: E402,F401
from test_panel import _js_fn, _pane                                         # noqa: E402


def _state(**kw):
    fp = paths.state_dir() / "live_unified_paper.json"
    b = json.loads(fp.read_text(encoding="utf-8"))
    b["state"].update(kw.pop("state", {}))
    b.update(kw)
    fp.write_text(json.dumps(b), encoding="utf-8")


def _card(html, cid):
    i = html.index(f"id='{cid}'")
    return html[html.rindex("<section", 0, i):html.index("</section>", i) + len("</section>")]


def _text(h):
    import re
    return re.sub(r"<[^>]+>", "", h)


def test_rule_sell_signal_is_listed_with_when_and_order_status(monkeypatch):
    _setup(monkeypatch)
    _state(state={"pending_exit": {"6758.T": "trail"}, "last_date": "2026-10-15"},
           orders=[{"ticker": "6758.T", "side": "SELL", "kind": "stock", "decided_on": "2026-10-15", "status": "SENT", "qty": 100}])
    html = panel.render("paper", "t" * 40, AT)
    hold = _pane(html, "hold")
    c = _card(html, "sellsig")
    assert "id='sellsig' hidden" not in html and hold.index("id='sellsig'") < hold.index("id='alloc'")   # 持仓最上面
    assert ("6758 ソニーグループ 100 股：规则出了卖出信号（跟踪止损，按 10/15（周四）收盘）→ 10/16（周五） 09:00 开盘卖 · 已下单（等成交）"
            in _text(c))
    assert "执行器照常在开盘卖出，不需要操作" in c and "建议" not in c and ".T " not in _text(c)


def test_own_manual_sell_is_not_a_signal_and_card_hides(monkeypatch):
    _setup(monkeypatch)
    _state(state={"pending_exit": {"6758.T": "manual"}, "last_date": "2026-10-15"})
    html = panel.render("paper", "t" * 40, AT)                                 # 没有盘中观测的结果、只有你自己写的卖出
    assert "id='sellsig' hidden" in html and "规则出了卖出信号" not in html


def test_intraday_cross_shows_provisional_until_the_bar_is_decided(monkeypatch):
    frames, c0 = _setup(monkeypatch)
    IW.run_once("paper", AT, fetch=_fetcher(frames, {}, sell_px=c0 * 0.92), send=lambda *a, **k: None)   # 6758 跌破止损（−7%）
    html = panel.render("paper", "t" * 40, AT)
    t = _text(_card(html, "sellsig"))
    assert "id='sellsig' hidden" not in html and "6758 ソニーグループ 100 股：盘中暂定（数据 14:20，约晚 20 分钟）现价" in t
    assert f"已越过 止损（买价 −7%） {IW._px(round(c0 * 0.93, 2))}" in t and "→ 若收盘仍在这里，规则下个交易日 10/19（周一）开盘卖（止损" in t
    code, j = panel.intraday_json("paper", AT)                                 # 页面每分钟按它更新：同一份
    assert code == 200 and j["sell"] == panel._sell_signals(json.loads((paths.state_dir() / "live_unified_paper.json").read_text()),
                                                            panel.LO.held_now(json.loads((paths.state_dir() / "live_unified_paper.json")
                                                                                         .read_text()), "paper", now=AT)["state"],
                                                            IW.load("paper"), AT)
    assert len(j["sell"]) == 1 and "盘中暂定" in j["sell"][0]
    _state(state={"last_date": "2026-10-16"})                                 # 执行器已经按 10/16 的收盘决策过（没判卖）→ 不再写暂定
    assert "id='sellsig' hidden" in panel.render("paper", "t" * 40, AT + dt.timedelta(hours=3))
    _state(state={"last_date": "2026-10-15", "pending_exit": {"6758.T": "stop"}})   # 已经判卖：只写一行（规则的那一行）
    t = _text(_card(panel.render("paper", "t" * 40, AT), "sellsig"))
    assert t.count("6758 ソニーグループ") == 1 and "规则出了卖出信号（止损" in t and "股：盘中暂定" not in t


def test_no_cross_no_card(monkeypatch):
    frames, _ = _setup(monkeypatch)
    IW.run_once("paper", AT, fetch=_fetcher(frames, {}), send=lambda *a, **k: None)   # 持平：规则不卖
    assert "id='sellsig' hidden" in panel.render("paper", "t" * 40, AT)
    assert panel.intraday_json("paper", AT)[1]["sell"] == []


def test_js_updates_and_hides_the_card(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    js = """
const SEC={hidden:true}, BOX={innerHTML:'', closest:()=>SEC};
const document={querySelectorAll:()=>[], getElementById:id=>id==='sellsig-list'?BOX:null};
const nameify=s=>s;
__FN__
const out=[];
intraShow({ok:true, hold:{}, sell:["<div class='ss'>a</div>"]}); out.push([SEC.hidden, BOX.innerHTML]);
intraShow({ok:true, hold:{}}); out.push([SEC.hidden, BOX.innerHTML]);          // 没给 sell（算不成）→ 不动
intraShow({ok:true, hold:{}, sell:[]}); out.push([SEC.hidden, BOX.innerHTML]);
console.log(JSON.stringify(out));
""".replace("__FN__", _js_fn(panel._JS, "intraShow"))
    f = tmp_path / "s.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    assert json.loads(p.stdout) == [[False, "<div class='ss'>a</div>"], [False, "<div class='ss'>a</div>"], [True, ""]]
