"""通知记录按账本分开（2026-10-19 用户：「模拟盘的操作记录的通知记录不要放到本番的通知记录里面 本番的操作记录通知记录才放到本番通知记录
登录本番账号的时候要可以放到本番的通知记录里面」）：记录带 book；定法 = 明写 → 标题 → 这个进程的账本（--broker）→ 共通；
面板只显示这个账本的 + 共通的（共通的带标签）；推送点开带 &book=；立花本番的登录（模拟账户取开盘价时的也算）→ 本番。"""
import datetime as dt
import json

from qbreak import notify as NT
from qbreak import panel, paths
from qbreak.brokers import tachibana as TB

AT = dt.datetime.now(panel.JST)


def _recs():
    return [json.loads(x) for x in (paths.out_dir() / NT.LOG_FILE).read_text(encoding="utf-8").splitlines()]


def test_book_is_explicit_then_subject_then_process_then_common(monkeypatch):
    seen = []
    monkeypatch.setattr("qbreak.webpush.send", lambda t, b, url="": seen.append(url))
    NT.send("qbreak 模拟操盘 2026-10-19", "a")
    NT.set_book("paper")
    NT.send("立花本番 API 登录 07:40：早上的运行", "b")                   # 模拟账户的进程里登录本番 → 本番
    NT.send("qbreak 盘中：6758 ソニーグループ 暂定卖点", "c")              # 标题认不出 → 这个进程的账本
    NT.send("whatever", "d", book="tachibana")                            # 明写优先
    NT.set_book(None)
    NT.send("经济威胁 高（10/19 09:00 JST 发布）", "e")                    # 共通
    NT.send("✓ デモ发单检查通过", "f")                                     # 本番上线前的检查 → 本番
    assert [r["book"] for r in _recs()] == ["paper", "tachibana", "paper", "tachibana", None, "tachibana"]
    assert seen[0].endswith("&book=paper") and seen[1].endswith("&book=tachibana") and "book=" not in seen[4]
    with NT.book_scope("tachibana"):
        NT.send("x", "g")
    NT.send("y", "h")
    assert [r["book"] for r in _recs()][-2:] == ["tachibana", None]


def test_history_filters_and_old_records_use_the_subject():
    lines = [{"id": "1", "at": "2026-10-19 07:00:00", "subject": "qbreak 模拟操盘 2026-10-16", "text": ""},   # 旧记录：没有 book
             {"id": "2", "at": "2026-10-19 07:01:00", "subject": "qbreak 立花实盘 2026-10-16", "text": ""},
             {"id": "3", "at": "2026-10-19 07:02:00", "subject": "经济威胁 高", "text": ""},
             {"id": "4", "at": "2026-10-19 07:03:00", "subject": "qbreak 盘中", "text": "", "book": "paper"},
             {"id": "5", "at": "2026-10-19 07:04:00", "subject": "qbreak 立花", "text": "", "book": None}]
    (paths.out_dir() / NT.LOG_FILE).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
    assert [h["id"] for h in NT.history(book="tachibana")] == ["5", "3", "2"]
    assert [h["id"] for h in NT.history(book="paper")] == ["5", "4", "3", "1"]
    assert len(NT.history()) == 5


def test_panel_log_card_shows_only_this_book_plus_common():
    NT.record("qbreak 模拟操盘 2026-10-19", "模拟的", book="paper")
    NT.record("立花本番 API 登录 07:40：早上的运行", "本番的", book="tachibana")
    NT.record("经济威胁 高", "共通的", book=None)
    t = panel._notify_log_card(AT, "tachibana")
    assert "立花本番 API 登录" in t and "经济威胁 高" in t and "模拟操盘" not in t
    assert t.count("<span class='chip'>共通</span>") == 1 and "这里是立花（本番）的 + 共通的" in t
    p = panel._notify_log_card(AT, "paper")
    assert "模拟操盘" in p and "立花本番 API 登录" not in p
    assert "通知记录 2<" in panel._msg_seg(AT, "paper")


def test_tachibana_login_push_goes_to_the_real_book(monkeypatch):
    got = []
    monkeypatch.setenv(TB.LOGIN_PUSH_ENV, "1")
    monkeypatch.setattr(NT, "send", lambda *a, **k: got.append((a, k)))
    NT.set_book("paper")                                                   # 模拟账户取开盘价时的登录
    TB.push_login(type("B", (), {"purpose": ("开盘价（模拟账户）", "登出")})())
    assert got and got[0][1].get("book") == "tachibana" and got[0][0][0].startswith("立花本番 API 登录")
