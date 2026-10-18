"""出过买入信号的票留在「选股」里，直到点「删除」（qbreak/signal_keep.py；2026-10-19 用户：「有买入信号机会就要一直显示除非点击删除
点击删除后要出确认dialog」；只展示）：连续几次 triggered = 同一次信号；断过之后再出 = 新的一次（删掉的那次不挡它）；
删除只拿掉这一次、since 对不上不删；面板「以前出过买入信号」有删除按钮（先确认）；执行器早上也记。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import panel, paths                                              # noqa: E402
from qbreak import signal_keep as SK                                         # noqa: E402

from test_panel import AT, SG_ROWS, _book, _card, _pane              # noqa: E402

TRIG = SG_ROWS[0]                                                            # 6501 日立：triggered（规则不买：名额已满）
WATCH = {**TRIG, "status": "watch", "close": 3700.0, "rule": {"state": "none", "text": "还没触发买入信号：规则不会买"}}


def _sg(asof, rows, fill=None):
    return {"asof": asof, "fill_day": fill, "rows": rows}


def _sm(asof, rows):
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"suggest": _sg(asof, rows)}, ensure_ascii=False), encoding="utf-8")


def test_episodes_delete_and_reappear():
    SK.note("paper", _sg("2026-10-05", [TRIG], "2026-10-06"))
    SK.note("paper", _sg("2026-10-06", [TRIG]))                              # 连续：同一次
    it = SK._load("paper")["items"]["6501.T"]
    assert (it["since"], it["last"], it["close"], it["fill"]) == ("2026-10-05", "2026-10-06", 3500.0, "2026-10-06")
    assert SK.kept("paper", _sg("2026-10-06", [TRIG])) == []                  # 还是 triggered：在上面「已经出了买入信号」
    SK.note("paper", _sg("2026-10-07", [WATCH]))
    k = SK.kept("paper", _sg("2026-10-07", [WATCH]))
    assert [x["ticker"] for x in k] == ["6501.T"] and k[0]["since"] == "2026-10-05"
    assert SK.delete("paper", "6501.T", "2026-10-01")[0] is False            # 旧页面（since 不对）→ 不删
    ok, msg = SK.delete("paper", "6501.T", "2026-10-05")
    assert ok and "不再显示" in msg and SK.kept("paper") == [] and SK.tickers() == set()
    SK.note("paper", _sg("2026-10-07", [WATCH]))                              # 同一份重看：不变
    SK.note("paper", _sg("2026-10-08", [TRIG]))                              # 断过之后又出 = 新的一次 → 删掉的不挡
    assert SK._load("paper")["items"]["6501.T"]["since"] == "2026-10-08" and SK._load("paper")["deleted"] == {}
    SK.note("paper", _sg("2026-10-02", []))                                  # 比记过的旧的汇总：不动
    assert SK._load("paper")["asof"] == "2026-10-08"


def test_panel_keeps_past_signal_with_delete_button_and_submit_removes_it():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}}, pos={})
    _sm("2026-10-05", [TRIG])
    h = _card(panel.render("paper", "t" * 40, AT), "autobuy")
    assert "已经出了买入信号" in h and "data-act='sigdel'" in h and "data-since='2026-10-05'" in h and "规则这次本来就不买" in h
    _sm("2026-10-06", [WATCH])                                               # 第二天：不再是 triggered（以前这只就消失了）
    h = _card(panel.render("paper", "t" * 40, AT), "autobuy")
    assert "<h3 class='sgh'>已经出了买入信号" not in h and "以前出过买入信号（1 只）" in h and "<b>6501</b> 日立" in h
    assert "过了买入时机" in h and "10/5（周一） 出信号" in h and "当时：信号成立但规则不买：个股名额已满（上限 4 只）" in h
    assert "信号收盘 ¥3,500 → 现在 ¥3,700（+5.7%）" in h and "data-act='sigdel'" in h and "data-live=''" in h
    ok, msg, _ = panel.submit({"book": "paper", "kind": "sigdel", "ticker": "6501.T", "since": "2026-10-04"}, AT)
    assert not ok and "刷新" in msg
    ok, msg, rec = panel.submit({"book": "paper", "kind": "sigdel", "ticker": "6501.T", "since": "2026-10-05"}, AT)
    assert ok and "6501 日立" in msg and rec["kind"] == "sigdel"
    h = _card(panel.render("paper", "t" * 40, AT), "autobuy")
    assert "以前出过买入信号" not in h and "6501" not in h


def test_kept_row_without_a_new_row_uses_the_snapshot_and_held_is_marked():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}},
          pos={"6501.T": {"shares": 200, "entry_px": 3550.0, "entry_date": "2026-10-06", "stop_px": 3300.0, "last_close": 3600.0}})
    _sm("2026-10-05", [TRIG])
    panel.render("paper", "t" * 40, AT)
    _sm("2026-10-06", [])                                                    # 这份候选里没有这只了
    h = _card(panel.render("paper", "t" * 40, AT), "autobuy")
    assert "以前出过买入信号（1 只）" in h and "在持仓" in h and "信号收盘 ¥3,500" in h and "→ 现在" not in h


def test_deleting_a_live_signal_hides_it_and_warns():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}}, pos={})
    plan = {**TRIG, "rule": {"state": "planned", "text": "规则已安排：10/06 开盘买 200 股"}}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"suggest": {**_sg("2026-10-05", [plan]), "fill_day": "2026-10-06"}},
                                                                        ensure_ascii=False), encoding="utf-8")
    h = _card(panel.render("paper", "t" * 40, AT), "autobuy")
    assert "data-live='规则照样会在 10/6（周二） 开盘买（要不买：在「交易」撤单或 HALT）'" in h
    assert panel.submit({"book": "paper", "kind": "sigdel", "ticker": "6501.T", "since": "2026-10-05"}, AT)[0]
    assert "6501" not in _pane(panel.render("paper", "t" * 40, AT), "pick")


def test_executor_morning_run_records_signals():
    src = (Path(__file__).resolve().parents[1] / "run.py").read_text(encoding="utf-8")
    i = src.index("_SK.note(tag, sm.get(\"suggest\") or {})")
    assert src.rindex("_SP.run(tag", 0, i) > src.rindex("def ", 0, i)         # 同一个函数里，推送之后


def test_js_asks_before_deleting(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    js_all = (Path(panel.__file__).parent / "static" / "trade.js").read_text(encoding="utf-8")
    i = js_all.index("if(a==='sigdel'){")
    blk = js_all[i:js_all.index("\n  }\n", i) + 4]
    js = """
const calls=[]; let answer=true;
const CFG={book:'paper'}; const tlab=(t,n)=>t.replace('.T','')+' '+n;
async function ask(title, body, ok, opt){ calls.push(['ask', title, body, ok, !!opt.danger]); return {ok:answer}; }
async function post(b){ calls.push(['api', '/api/request', b]); return {ok:true, msg:'x'}; }
function done(j){ calls.push(['done']); }
async function h(e, b){ const a=b.dataset.act, d=b.dataset;
__BLK__
}
(async()=>{
  let pd=0; const e={preventDefault(){pd++}, stopPropagation(){}};
  const b={dataset:{act:'sigdel', t:'6501.T', name:'日立', since:'2026-10-05', live:''}};
  await h(e, b); answer=false; await h(e, b);
  console.log(JSON.stringify({calls, pd}));
})();
""".replace("__BLK__", blk)
    f = tmp_path / "s.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    out = json.loads(p.stdout)
    assert out["pd"] == 2                                                    # 点删除不展开那一行
    c = out["calls"]
    assert c[0][0] == "ask" and c[0][1] == "从选股里删除 6501 日立？" and "只是不显示" in c[0][2] and c[0][3] == "删除" and c[0][4]
    assert c[1] == ["api", "/api/request", {"book": "paper", "kind": "sigdel", "ticker": "6501.T", "since": "2026-10-05"}] and c[2] == ["done"]
    assert [x[0] for x in c[3:]] == ["ask"]                                  # 取消：什么都不发
