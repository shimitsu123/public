"""面板的稳健性复核（2026-10-24）：写的途中 / 结果刚出来不自动刷新、同一笔再送一次不重复写（rid）、连不上时「不确定」、
推送没登记上不写「已打开 ✓」、两步撤单的第二步失败不被盖掉、卖出信号没算成也留着卡、轮询不叠、窄屏的按钮不被切、
ⓘ 点的范围、刷新按钮一定放开、推送订阅并发不丢、存着的立花实时价写日期。"""
import datetime as dt
import json
import os
import subprocess
import threading
import time
import urllib.error

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak import webpush as WP
from qbreak.calendar_jp import JST

from panel_js_harness import node, run_conn
from test_app_ab import _ua
from test_panel_c77 import _book as _c77_book
from test_panel_submit_kinds import TIMES, _setup

AT = dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)


@pytest.fixture(autouse=True)
def _fresh_rids():
    panel._RID_DONE.clear()
    panel._RID_BUSY.clear()
    yield
    panel._RID_DONE.clear()
    panel._RID_BUSY.clear()


def _flows():
    b = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    return b.get("flows") or []


# ── 2：同一笔再送一次不重复写 ──
def test_flow_with_the_same_rid_registers_once():
    _c77_book()
    body = {"book": "tachibana", "kind": "flow", "jpy": "300000", "date": "2026-10-06", "rid": "a1b2c3d4e5f6a1b2c3d4e5f6"}
    ok1, msg1, rec1 = panel.submit(body, AT)
    ok2, msg2, rec2 = panel.submit(dict(body), AT)
    assert ok1 and ok2 and len(_flows()) == 1
    assert msg2.startswith(panel.RID_DUP_MSG) and msg1 in msg2 and rec2.get("dup") and not rec1.get("dup")
    ok3, _m, _r = panel.submit({**body, "rid": "ffffffffffffffffffffffff"}, AT)    # 另一个 rid = 你又点了一次：照常登记
    assert ok3 and len(_flows()) == 2
    ok4, _m, _r = panel.submit({**body, "jpy": "1000"}, AT)                         # 同一个 rid、内容不同：不是同一笔
    assert ok4 and len(_flows()) == 3


def test_manual_order_with_the_same_rid_is_written_once():
    _setup()
    body = {"book": "paper", "kind": "sell", "ticker": "8306", "rid": "r0001"}
    ok1, _m1, rec1 = panel.submit(body, TIMES["after"], fetch=lambda ts: {})
    ok2, msg2, rec2 = panel.submit(dict(body), TIMES["after"], fetch=lambda ts: {})
    assert ok1 and ok2 and rec2["id"] == rec1["id"] and rec2.get("dup") and panel.RID_DUP_MSG in msg2
    sells = [r for r in MO.unseen("paper", json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8")))
             if r.get("kind") == "sell" and r.get("ticker") == "8306.T"]
    assert len(sells) == 1
    assert "rid" in panel.CLIENT_DROP


def test_rid_only_remembers_results_that_were_written(monkeypatch):
    calls = []

    def fake(body, now=None, source="panel", fetch=None):
        calls.append(body)
        if body.get("confirm") != "tok":
            return False, "要先确认", {"need_confirm": True, "confirm": {"token": "tok"}}
        return True, "已写", {"id": f"M{len(calls)}", "kind": "sell"}
    monkeypatch.setattr(panel, "_submit_once", fake)
    b = {"book": "paper", "kind": "corefix", "ticker": "1545", "rid": "x1"}
    assert panel.submit(b)[0] is False                                    # 要先确认：什么都没写 → 不记
    assert "rid" not in calls[0]                                          # rid 不交给下面
    ok, _m, rec = panel.submit({**b, "confirm": "tok"})
    assert ok and rec["id"] == "M2"
    ok, msg, rec = panel.submit(b)                                        # 结果不确定之后再点同一笔（没带 confirm）：回原来的结果
    assert ok and rec["id"] == "M2" and rec["dup"] and len(calls) == 2 and msg.startswith(panel.RID_DUP_MSG)
    panel.submit({"book": "paper", "kind": "sell", "ticker": "8306"})    # 没带 rid：照旧每次都写
    panel.submit({"book": "paper", "kind": "sell", "ticker": "8306", "rid": "bad id!"})   # 格式不对的 rid：当没带
    assert len(calls) == 4


def test_same_rid_at_the_same_time_is_written_once(monkeypatch):
    n = []

    def slow(body, now=None, source="panel", fetch=None):
        n.append(1)
        time.sleep(0.2)
        return True, "已写", {"id": "M1", "kind": "flow"}
    monkeypatch.setattr(panel, "_submit_once", slow)
    out = []
    ts = [threading.Thread(target=lambda: out.append(panel.submit({"book": "tachibana", "kind": "flow", "jpy": 1, "rid": "c1"})))
          for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(n) == 1 and len(out) == 3 and all(o[0] for o in out) and sum(1 for o in out if o[2].get("dup")) == 2


def test_duplicate_does_not_call_the_executor_again():
    class T:
        n = 0

        def check(self):
            T.n += 1
    panel._after_submit(T(), {"id": "M1", "kind": "sell", "dup": True})
    time.sleep(0.05)
    assert T.n == 0


def test_page_sends_rid_and_keeps_unsure_network_failures():
    J = panel.js_plain("core")
    assert "Object.assign({}, body||{}, {rid:rid})" in J and "sessionStorage.setItem(RIDK" in J
    assert "k!=='rid' && k!=='confirm'" in J                              # 「确认下单」之后那次与第一次是同一笔
    assert "先刷新看「交易」/ 通知记录再决定要不要再点" in J
    i = J.index("先刷新看「交易」/ 通知记录")
    assert J[i:J.index(";", i)].endswith(", true)")                       # 一直留着（sticky），不 9 秒就消失


# ── 1：写的途中 / 结果刚出来不自动刷新 ──
def test_conn_waits_for_a_write_and_its_result_before_reloading(tmp_path):
    o = run_conn(tmp_path, r"""
  DOC.writing = true; NET.v = 'V2';                                        // 写的请求在路上（或结果提示刚出来）时面板换了新代码
  await advance(31000);
  const r0 = R.reloads, b0 = banner();
  DOC.writing = false; await advance(2500);
  return {r0, b0, r1: R.reloads};
""", gen_ago_min=1, setup="window.qbWriting = () => !!DOC.writing;")
    assert o["r0"] == 0 and "看完写的结果后自动刷新" in o["b0"] and o["r1"] == 1, o
    J = panel.js_plain("core")
    assert "busy(false); WHOLD=Date.now()+WHOLD_MS;" in J and "window.qbWriting = writeHold;" in J
    assert "m.dataset.sticky==='1'" in J                                  # 不自动消失的提示开着：也等


# ── 8：刷新按钮一定放开 ──
def test_reload_button_is_released_on_every_path():
    C = panel.js_plain("conn")
    go = C[C.index("function go(r){"):C.index("window.qbReload = function")]
    assert go.count("freeBtn()") >= 4 and "loading(false)" not in go
    assert "e=>{ freeBtn(); beacon('reload-err'" in C and "if(!x) freeBtn();" in C
    J = panel.js_plain("core")
    assert "reloadPage.h=setTimeout(freeReload, 45000)" in J and "window.qbFreeReload = freeReload;" in J


# ── 3：推送 ──
def test_push_success_only_when_the_mac_accepted():
    A = panel.js_plain("app")
    on = A[A.index("if(a==='push-on'){"):A.index("}else{", A.index("if(a==='push-on'){"))]
    assert "if(j){ pushBad(''); toast(" in on and "pushBad(s.endpoint)" in on and "重试" in on
    st = A[A.index("async function pushState(){"):A.index("document.addEventListener('DOMContentLoaded'")]
    assert st.index("bad ?") < st.index("推送已打开 ✓") and "推送没打开好 ✗" in st


# ── 4：两步撤单 ──
def test_cancel_then_restore_shows_the_second_step_failure():
    T = panel.js_plain("trade")
    assert T.count("else half2(j, '恢复按规则');") == 2
    assert "done(k ? {msg:" not in T
    d2 = T[T.index("function half2(j, what){"):T.index("// ── 调仓")]
    assert "PWHY" in d2 and "true, true)" in d2
    assert "if(!j) PWHY=lastFail();" in T and "PWHY='确认框里点了取消" in T


# ── 5：卖出信号没算成 ──
def test_sell_card_placeholder_when_signals_fail(monkeypatch):
    _c77_book("paper")

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(panel, "_sell_signals", boom)
    h = panel.render("paper", "t" * 40, AT)
    assert "id='sellsig'" in h and "id='sellsig-list'" in h and panel.SELL_CARD_ERR in h
    i = h.index("id='sellsig'")
    assert " hidden" not in h[i:h.index(">", i)]
    I = panel.js_plain("intraday")
    assert "h.textContent='★ 持仓出了卖出信号'" in I


# ── 6：轮询不叠 ──
def test_room_and_intraday_polls_are_single_flight():
    for mod, fly, tid, fn in (("room", "RFLY", "RTID", "loadRoom"), ("intraday", "IFLY", "ITID", "loadIntra")):
        J = panel.js_plain(mod)
        body = J[J.index(f"async function {fn}(){{"):]
        assert f"if({fly}) return;" in body and f"}}finally{{ {fly}=false; }}" in body, mod
        assert f"clearTimeout({tid}); {tid}=setTimeout({fn}," in body, mod


def test_room_poll_does_not_stack_timers_in_node(tmp_path):
    src = panel.js_plain("room")
    load = src[src.index("let RTID=null"):src.index("if(CFG.room) RTID=")]
    js = r"""
let NOW = 0; const T = []; let ID = 0;
globalThis.setTimeout = (fn, ms) => { const id = ++ID; T.push({id, fn}); return id; };
globalThis.clearTimeout = id => { const i = T.findIndex(t => t.id === id); if (i >= 0) T.splice(i, 1); };
const CFG = {book: 'paper', live: true};
const $ = s => (s === '#room' ? {} : null);
let REQS = 0, rel = [];
function req(){ REQS++; return new Promise(r => rel.push(() => r({r: {ok: true}, j: null}))); }
function roomShow(){}
""" + load + r"""
(async () => {
  const a = loadRoom(), b = loadRoom(), c = loadRoom();                  // 取的途中又被叫两次（切回来 / 重新连上）
  rel.forEach(f => f()); await a; await b; await c;
  console.log(JSON.stringify({reqs: REQS, timers: T.length}));
})();
"""
    f = tmp_path / "room.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node(), str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-800:]
    assert json.loads(r.stdout.strip().splitlines()[-1]) == {"reqs": 1, "timers": 1}


# ── 7：CSS ──
def test_segments_shrink_and_info_tap_target_is_large():
    css = panel._CSS
    seg = css[css.index(".seg{"):css.index("}", css.index(".seg{"))]
    assert "nowrap" not in seg
    btn = css[css.index(".seg button{"):css.index("}", css.index(".seg button{"))]
    assert "min-width:0" in btn and "white-space:normal" in btn
    assert "details.ii>summary::before{" in css and "width:max(32px,100%);height:max(32px,100%)" in css
    s = css[css.index("details.ii>summary{"):css.index("}", css.index("details.ii>summary{"))]
    assert "position:relative" in s


# ── 9：推送订阅并发 ──
def test_send_keeps_a_subscription_added_while_sending():
    old = _ua()
    assert WP.subscribe("A", old, "A")[0]
    new = {**_ua(), "endpoint": "https://web.push.apple.com/new"}

    def opener(req, timeout=15):                                          # 发的途中另一台设备打开了推送；这一台已失效
        WP.subscribe("B", new, "B")
        raise urllib.error.HTTPError(req.full_url, 410, "Gone", {}, None)
    assert WP.send("t", "b", opener=opener) is False
    d = WP.subs()
    assert WP.sub_id(new["endpoint"]) in d and WP.sub_id(old["endpoint"]) not in d
    assert oct(os.stat(paths.home() / WP.SUBS_FILE).st_mode & 0o777) == "0o600"


# ── 10：存着的立花实时价写日期 ──
def test_cached_realtime_quote_shows_its_date(tmp_path):
    J = panel._JS
    fns = J[J.index("function jstDay(){"):J.index("export async function rtQ(") if "export async function rtQ(" in J else J.index("async function rtQ(")]
    pxs = J[J.index("function pxs(v){"):J.index("\n", J.index("function pxs(v){"))]
    pcs = J[J.index("function pcs(v){"):J.index("\n", J.index("function pcs(v){"))]
    js = pxs + "\n" + pcs + "\n" + fns + r"""
Date.now = () => Date.parse('2026-10-24T01:00:00Z');                    // JST 10:00
console.log(JSON.stringify({today: rtText({at: '2026-10-24T09:58:00+09:00', px: 2500}),
                            old: rtText({at: '2026-10-23T14:59:00+09:00', px: 2500}, true)}));
"""
    f = tmp_path / "q.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node(), str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-800:]
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["today"].startswith("立花实时 09:58 ") and "10/" not in o["today"]
    assert o["old"].startswith("立花实时 10/23 14:59 ") and "存着的旧数据" in o["old"]
    Q = panel.js_plain("quotes")
    assert "x.r.headers.get('X-Qbreak-Cache')" in Q and "rtShow(el, 'off', rtText(q, true))" in Q
