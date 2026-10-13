"""HALT 期间等着的手动指令（2026-10-13 resume-other-3）与过时页面的自动刷新（resume-other-9）。
① HALT 中：等着的买卖指令写明「HALT 中：解除后照原样执行（写于 MM/DD）」（同样的文字不反复改）、账本的 manual 里记 halt_seen；
② HALT 解除后的第一次运行（早上 / 开盘后 / 盘中 now）→ warn 事件列出积压的指令（id、票、种类、写于哪天），标记清掉、只说一次；
   日报的一行摘要标 ★；没有积压 → 悄悄清掉标记；③ 面板的 HALT 卡片与 manual list 列出积压；
④ app.js：页面回到前台、生成超过约 10 分钟 → 重新载入（没有 gen → 不动；对话框开着 → 只提示）。"""
import datetime as dt
import json
import subprocess

import pytest

import run
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST
from qbreak.live_unified import daily_text

from test_manual_orders import _Run, _sell_req
from test_panel import AT, _book

BACKLOG = "条手动指令在 HALT 期间等着，现在照原样执行"


def _md(rec: dict) -> str:
    return rec["at"][5:10].replace("-", "/")


def _now(r, hh: int, mm: int) -> dict:
    """成交日（第 r.k 根）hh:mm 的盘中 now_phase（不再开一次盘：HALT 解除后马上由面板叫的那一次）。"""
    from qbreak.brokers import tachibana as tb
    r.now["t"] = dt.datetime.combine(r.eng.gidx[r.k].date(), dt.time(hh, mm), tzinfo=JST)
    old = tb._sleep, r.b.confirm_timeout_s
    tb._sleep, r.b.confirm_timeout_s = (lambda s: None), 5.0
    try:
        return r.ux.now_phase(r.quote)
    finally:
        tb._sleep, r.b.confirm_timeout_s = old


def _backlog_events(r) -> list[dict]:
    return [e for e in r.ux.book["events"] if BACKLOG in e["msg"]]


# ────────── ① ② 执行器 ──────────
def test_halt_marks_waiting_items_then_first_run_after_removal_warns_once():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    rec = _sell_req(r)
    paths.halt_file().write_text("stop", encoding="utf-8")
    r.day()
    it = r.item(rec["id"])
    want = f"HALT 中：解除后照原样执行（写于 {_md(rec)}）"
    assert it["status"] == "pending" and it["msg"] == want == MO.halt_text(it)   # 以前写「等执行器下单」
    hs = r.ux.book["manual"]["halt_seen"]
    assert hs["since"] and hs["last"] and not _backlog_events(r)
    since0 = hs["since"]
    r.day()                                                    # HALT 第二天：同样的说明、since 不变
    assert r.item(rec["id"])["msg"] == want and r.ux.book["manual"]["halt_seen"]["since"] == since0
    assert isinstance(r.ux.book.get("halt_seen", []), list)    # 顶层的 halt_seen（HALT 演练的证据）不受影响
    paths.halt_file().unlink()
    r.ux.blocked = None
    r.day()                                                    # 解除后的第一次运行：列出积压、照原样下单
    ev = _backlog_events(r)
    assert len(ev) == 1 and ev[0]["level"] == "warn"
    assert ev[0]["msg"].startswith(f"1 {BACKLOG}：{rec['id']} A.T 卖出全部 写于 {_md(rec)}")
    assert "manual cancel" in ev[0]["msg"] and "halt_seen" not in r.ux.book["manual"]
    it = r.item(rec["id"])
    assert it["status"] == "placed"
    sm = r.ux.summary()
    assert BACKLOG in (sm["manual"].get("halt_backlog") or "")
    assert any(ln.startswith(f"- ★ 1 {BACKLOG}") for ln in MO.lines(sm["manual"]))
    _, short, _ = daily_text(sm, r.eng.st, None, False, 1_000_000.0)
    assert "★ HALT 期间等着的手动指令现在照原样执行" in short
    r.day()
    r.day()
    assert len(_backlog_events(r)) == 1                        # 只说一次


def test_halt_removed_without_waiting_items_clears_the_marker_silently():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    paths.halt_file().write_text("stop", encoding="utf-8")
    r.day()
    assert "halt_seen" in r.ux.book["manual"]
    paths.halt_file().unlink()
    r.ux.blocked = None
    r.day()
    assert "halt_seen" not in r.ux.book["manual"] and not _backlog_events(r)
    assert not r.ux.summary()["manual"].get("halt_backlog")


def test_halt_removed_mid_session_now_phase_lists_the_backlog_before_selling():
    """HALT 中盘中被挡的指令说明「解除后照原样执行（写于…）」；盘中删掉 HALT → 面板叫的 now_phase 先列出积压再下单。"""
    r = _Run([1000.0] * 15 + [1100.0] * 25, entry=(10,), bear_all=True)
    r.until(13)
    rec = _sell_req(r)
    paths.halt_file().write_text("stop", encoding="utf-8")
    res0 = r.session(10, 0)
    assert r.item(rec["id"])["msg"] == MO.halt_text(rec)
    assert [x["msg"] for x in res0["items"]] == [MO.halt_text(rec)]
    paths.halt_file().unlink()
    r.ux.blocked = None
    res = _now(r, 10, 30)
    ev = _backlog_events(r)
    assert len(ev) == 1 and f"{rec['id']} A.T 卖出全部 写于 {_md(rec)}" in ev[0]["msg"]
    assert res["placed"] == 1 and r.item(rec["id"])["status"] != "pending"
    assert BACKLOG in r.ux.summary()["manual"]["halt_backlog"]
    _now(r, 10, 40)
    assert len(_backlog_events(r)) == 1


def test_now_report_puts_the_backlog_first_and_warns(monkeypatch):
    from types import SimpleNamespace
    from qbreak import live_unified as LU
    from qbreak import notify
    r = _Run([1000.0] * 15 + [1100.0] * 25, entry=(10,), bear_all=True)
    r.until(13)
    rec = _sell_req(r)
    paths.halt_file().write_text("stop", encoding="utf-8")
    r.session(10, 0)
    paths.halt_file().unlink()
    r.ux.blocked = None
    res = _now(r, 10, 30)
    sent, macs = [], []
    monkeypatch.setattr(notify, "send", lambda title, body, level="info", **k: sent.append((body, level)))
    monkeypatch.setattr(LU, "mac_notify", lambda title, body: macs.append(body))
    assert run._now_report(SimpleNamespace(notify=True), r.ux, res, False, "t") == 0
    body, level = sent[-1]
    assert level == "warn" and body.splitlines()[0].startswith(f"- ★ 1 {BACKLOG}：{rec['id']}")
    assert macs[-1].startswith("★ HALT 期间等着的手动指令现在照原样执行｜下单 1 笔")


def test_mmdd_and_halt_text():
    assert MO.mmdd("2026-10-06T06:00:00+09:00") == "10/06" and MO.mmdd(None) == "—" and MO.mmdd("bad") == "—"
    assert MO.halt_text({"at": "2026-10-06T06:00:00+09:00"}) == "HALT 中：解除后照原样执行（写于 10/06）"


# ────────── ③ 面板 / manual list ──────────
def _waiting_book():
    it = {"id": "M20261005-150000-sell-7203", "kind": "sell", "ticker": "7203.T", "status": "pending", "block_days": 20,
          "at": "2026-10-05T15:00:00+09:00", "msg": "HALT 中：解除后照原样执行（写于 10/05）"}
    old = {"id": "M20261002-150000-trim-7203", "kind": "trim", "ticker": "7203.T", "status": "cancelled", "shares": 100,
           "at": "2026-10-02T15:00:00+09:00"}
    _book(manual={"core_pct": 100.0, "items": {it["id"]: it, old["id"]: old}, "seen": [it["id"], old["id"]]})
    return it


def test_panel_halt_card_lists_the_waiting_instructions():
    _waiting_book()
    paths.halt_file().write_text("stop", encoding="utf-8")
    h = panel.render("paper", "t" * 40, AT)
    card = h[h.index("id='halt'"):]
    card = card[:card.index("</section>")]
    assert "等着的手动买卖指令 1 条（最早写于 10/05）：解除后照原样执行" in card
    paths.halt_file().unlink()
    h = panel.render("paper", "t" * 40, AT)
    assert "等着的手动买卖指令" not in h


def test_cli_manual_list_under_halt_shows_the_backlog_with_dates(capsys, monkeypatch):
    from qbreak import calendar_jp as CJ
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    it = _waiting_book()
    paths.halt_file().write_text("stop", encoding="utf-8")
    assert run.main(["manual", "list", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert (f"★ HALT 生效中：等着的买卖指令 1 条，解除后照原样执行：{it['id']} 卖出全部 7203.T" in out
            and "（写于 10/05）（要不做：先 manual cancel <指令 id>）" in out)
    paths.halt_file().unlink()
    run.main(["manual", "list", "--broker", "paper"])
    assert "★ HALT 生效中" not in capsys.readouterr().out


# ────────── ④ app.js：切回来时页面过时 → 重新载入 ──────────
def _node():
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    return node


def test_app_js_reloads_a_stale_page_when_it_becomes_visible(tmp_path):
    src = (panel.STATIC_DIR / "app.js").read_text(encoding="utf-8")
    i = src.index("(function(){", src.index("import { req }"))
    frag = src[i:src.index("})();", i) + 5]
    assert "手机切回来马上刷新" in frag and "visibilitychange" in frag and "CFG.gen" in frag and "location.reload()" in frag
    harness = "function setup(CFG, document, location, loading, toast){\n" + frag + "\n}\n" + r"""
function run(cfg, steps){
  let fn=null, reloads=0, toasts=0, dlg=null;
  const doc={hidden:true, addEventListener:(e,f)=>{ if(e==='visibilitychange') fn=f; }, querySelector:s=>dlg};
  setup(cfg, doc, {reload:()=>{reloads++;}}, ()=>{}, ()=>{toasts++;});
  for(const s of steps){ doc.hidden=s.hidden; dlg=s.dlg||null; fn(); }
  return [reloads, toasts];
}
const now=Date.now(), M=60000, V={hidden:false}, out={};
out.nogen=run({}, [V, V]);
out.badgen=run({gen:'x'}, [V]);
out.fresh=run({gen:now-5*M}, [V]);
out.hidden=run({gen:now-11*M}, [{hidden:true}]);
out.stale=run({gen:now-11*M}, [V, V]);
out.dialog=run({gen:now-30*M}, [{hidden:false, dlg:{}}]);
out.nocfg=run(null, [V]);
console.log(JSON.stringify(out));
"""
    f = tmp_path / "t.js"
    f.write_text(harness, encoding="utf-8")
    p = subprocess.run([_node(), str(f)], capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out == {"nogen": [0, 0], "badgen": [0, 0], "fresh": [0, 0], "hidden": [0, 0], "stale": [1, 0],
                   "dialog": [0, 1], "nocfg": [0, 0]}
