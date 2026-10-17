"""撤回一条撤单指令（2026-10-16，事后）：撤单指令的 id 带下划线（M20261015-081500-cancel_order-1545），以前撤回的 id 格式不收 →
面板 / 手机上「等执行器读」的撤单那一行没有按钮，命令行 manual cancel 回「撤回要给指令 id」，什么都没写。
现在执行器读到之前能撤回：撤回之后那笔单不再算「撤单中」（live_ops.asked_cids / cancel_jobs / 面板 / MO.cancel_due 同一个），
执行器照常发 / 照常挂着；撤单的运行（只读撤单）也认这条撤回、不撤。执行器已经读到（可能已经发到立花）/ 正在运行 → 拒绝、写理由。"""
import datetime as dt
import json

import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST
from test_panel import AT15, _book1015
from test_trade_today import BUY, BUY_B, _badge_ok, _parts, _row

TAG = "paper"


def _load() -> dict:
    return json.loads((paths.state_dir() / f"live_unified_{TAG}.json").read_text(encoding="utf-8"))


def _setup():
    """1482.T 的买单还没发出（等开盘后）；面板写了撤单 → 执行器还没读。"""
    _book1015(TAG, sell="SENT", cash=2_000_000.0, fix={})
    n0 = _badge_ok(panel.render(TAG, "t" * 40, AT15), TAG, AT15)
    ok, msg, rec = panel.submit({"book": TAG, "kind": "cancel_order", "cid": BUY}, AT15)
    assert ok, msg
    assert "_" in rec["id"]                                                    # 撤单指令的 id 带下划线（cancel_order）
    return rec, n0


def test_normalize_accepts_cancel_order_ids():
    rid = "M20261015-081500-cancel_order-1545"
    assert MO.normalize({"kind": "cancel", "target": rid})["target"] == rid   # 以前 ValueError「撤回要给指令 id」
    assert MO.normalize({"kind": "uncancel", "target": rid})["target"] == rid
    with pytest.raises(ValueError):
        MO.normalize({"kind": "cancel", "target": "M2026 x"})


def test_withdraw_unread_cancel_order_end_to_end():
    rec, n0 = _setup()
    rid = rec["id"]
    b = _load()
    assert BUY in LO.asked_cids(b, MO.unseen(TAG, b)) and MO.cancel_due(TAG, b, AT15)
    html = panel.render(TAG, "t" * 40, AT15)
    assert f"data-act='cancel' data-kind='cancel_order' data-id='{rid}'" in html   # 等执行器读的撤单：给「撤回」（以前没有按钮）
    ok, msg, wrec = panel.submit({"book": TAG, "kind": "cancel", "target": rid}, AT15)
    assert ok, msg                                                             # 以前「没写：撤回要给指令 id」
    assert wrec["target"] == rid and "撤单 1482 对冲版美国 7〜10 年国债" in msg and "不撤" in msg
    b = _load()
    w = MO.unseen(TAG, b)
    assert BUY not in LO.asked_cids(b, w)                                     # 执行器发单前的保护 / 对账：不再当成你撤了
    assert not LO.cancel_jobs(b, w, AT15)                                     # 不再挡别的撤单
    assert not MO.cancel_due(TAG, b, AT15)                                    # 面板不再为它叫撤单的运行
    html = panel.render(TAG, "t" * 40, AT15)
    top, _later, ended = _parts(html)
    assert "撤单中" not in _row(ended, BUY_B) if BUY_B in ended else True
    assert _badge_ok(html, TAG, AT15) == n0                                   # 数字回到写撤单之前
    assert f"data-kind='cancel_order' data-id='{rid}'" not in html            # 已经在撤回中：不再给按钮
    ok, msg, _ = panel.submit({"book": TAG, "kind": "cancel", "target": rid}, AT15)
    assert not ok and "已经在撤回中" in msg
    ok, msg, _ = panel.submit({"book": TAG, "kind": "cancel_order", "cid": BUY}, AT15)   # 想撤还能重新点「撤单」
    assert ok, msg


def test_cancel_phase_reads_the_withdrawal_and_does_not_cancel():
    """撤单的运行只读撤单（ingest(only=cancel_order)）：以前它照样读到撤单、去撤；现在认得还没读的撤回 → 撤单指令「已撤回」、不撤。"""
    rec, _ = _setup()
    rid = rec["id"]
    ok, msg, wrec = panel.submit({"book": TAG, "kind": "cancel", "target": rid}, AT15)
    assert ok, msg
    b = _load()
    man = MO.Manual(b, TAG, lambda: AT15)
    man.ingest(only=("cancel_order",))
    it = b["manual"]["items"][rid]
    assert it["status"] == "cancelled" and "撤回" in it["msg"]
    assert not man.pending(("cancel_order",))                                 # 撤单的运行这次什么都不撤
    assert wrec["id"] not in b["manual"]["items"]                             # 撤回本身留给平常的运行读
    MO.Manual(b, TAG, lambda: AT15).ingest()
    assert b["manual"]["items"][wrec["id"]]["status"] == "done"
    assert b["manual"]["items"][rid]["status"] == "cancelled"
    assert BUY not in LO.asked_cids(b, MO.unseen(TAG, b))


def test_same_run_reads_both():
    rec, _ = _setup()
    rid = rec["id"]
    ok, _msg, wrec = panel.submit({"book": TAG, "kind": "cancel", "target": rid}, AT15)
    assert ok
    b = _load()
    MO.Manual(b, TAG, lambda: AT15).ingest()
    items = b["manual"]["items"]
    assert items[rid]["status"] == "cancelled" and items[wrec["id"]]["status"] == "done"


def _save(b: dict) -> None:
    (paths.state_dir() / f"live_unified_{TAG}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")


def test_read_by_another_run_but_not_cancelled_yet_can_be_withdrawn():
    """09:05 的开盘后运行读了撤单（pending，撤单的运行还没做）→ 还能撤回；撤单的运行读到撤回 → 不撤。"""
    rec, _ = _setup()
    rid = rec["id"]
    b = _load()
    MO.Manual(b, TAG, lambda: AT15).ingest()
    assert b["manual"]["items"][rid]["status"] == "pending"
    _save(b)
    assert f"data-kind='cancel_order' data-id='{rid}'" in panel.render(TAG, "t" * 40, AT15)
    ok, msg, wrec = panel.submit({"book": TAG, "kind": "cancel", "target": rid}, AT15)
    assert ok, msg
    b = _load()
    w = MO.unseen(TAG, b)
    assert BUY not in LO.asked_cids(b, w) and not LO.cancel_jobs(b, w, AT15) and not MO.cancel_due(TAG, b, AT15)
    man = MO.Manual(b, TAG, lambda: AT15)
    man.ingest(only=("cancel_order",))                                        # 撤单的运行
    assert b["manual"]["items"][rid]["status"] == "cancelled" and not man.pending(("cancel_order",))
    MO.Manual(b, TAG, lambda: AT15).ingest()
    assert b["manual"]["items"][wrec["id"]]["status"] == "done"


def test_withdraw_refused_once_the_cancel_run_started():
    """撤单的运行已经在撤（发到立花、在等立花确认：grp_wait）→ 撤回不了、写理由；万一写进去了（页面过期），执行器读到时也拒绝、不动撤单指令。"""
    rec, _ = _setup()
    rid = rec["id"]
    b = _load()
    MO.Manual(b, TAG, lambda: AT15).ingest(only=("cancel_order",))
    b["manual"]["items"][rid].update(grp_wait=[BUY], recheck_at=(AT15 + dt.timedelta(minutes=1)).isoformat())
    _save(b)
    ok, msg, _ = panel.submit({"book": TAG, "kind": "cancel", "target": rid}, AT15)
    assert not ok and "已经在撤" in msg and "撤回不了" in msg
    assert f"data-kind='cancel_order' data-id='{rid}'" not in panel.render(TAG, "t" * 40, AT15)
    t1 = AT15 + dt.timedelta(minutes=1)                                      # 页面过期写进去的（直接写一行）
    MO.append(TAG, {"kind": "cancel", "target": rid, "source": "test"}, clock=lambda: t1)
    w = MO.unseen(TAG, b)
    assert BUY in LO.asked_cids(b, w)                                        # 读之前也照样算撤单中
    MO.Manual(b, TAG, lambda: t1).ingest()
    assert b["manual"]["items"][rid]["status"] == "pending"                  # 撤单照做
    wr = next(it for it in b["manual"]["items"].values() if it["kind"] == "cancel")
    assert wr["status"] == "rejected" and "撤回不了" in wr["msg"]
    assert BUY in LO.asked_cids(b, MO.unseen(TAG, b))
    b["manual"]["items"][rid]["status"] = "done"                              # 做完了：撤回不了
    _save(b)
    ok, msg, _ = panel.submit({"book": TAG, "kind": "cancel", "target": rid}, AT15)
    assert not ok and "撤回不了" in msg


def test_withdraw_refused_while_the_executor_runs(monkeypatch):
    from qbreak import live_unified as LU
    rec, _ = _setup()
    monkeypatch.setattr(LU, "lock_held", lambda p: True)
    ok, msg, _ = panel.submit({"book": TAG, "kind": "cancel", "target": rec["id"]}, AT15)
    assert not ok and "执行器正在运行" in msg


def test_uncancel_of_a_cancel_order_withdrawal_is_refused():
    rec, _ = _setup()
    ok, _msg, wrec = panel.submit({"book": TAG, "kind": "cancel", "target": rec["id"]}, AT15)
    assert ok
    ok, msg, _ = panel.submit({"book": TAG, "kind": "uncancel", "target": wrec["id"]}, AT15)
    assert not ok and "重新点「撤单」" in msg


def test_cli_cancel_request():
    rec, _ = _setup()
    b = _load()
    ok, msg, w = MO.cancel_request(TAG, b, rec["id"], now=AT15, source="cli")
    assert ok and w["target"] == rec["id"] and msg.startswith("已写：撤回")


def test_trade_js_confirms_cancel_order_withdrawal():
    from pathlib import Path
    js = (Path(panel.__file__).parent / "static" / "trade.js").read_text(encoding="utf-8")
    assert "d.kind==='cancel_order'" in js and "撤回这条撤单" in js
