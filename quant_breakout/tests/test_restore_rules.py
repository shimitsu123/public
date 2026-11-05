"""「更多」的「恢复自动交易规则」（2026-10-17 用户：「更多里面加一个如果现在没有遵循自动交易规则的话要出现一个恢复自动交易规则的button」）：
没按规则（固定口数 / 闲置资金比例 ≠ 100% / 不自动买回）才出现；点了先给确认框（会怎样、什么时候），带 token 再点才写；
每样写一条平常的指令（corefix clear / core 100 / unblock）；「全部换成」还在处理 → 不做；都按规则 → 卡片不出现。"""
import json

from qbreak import manual_orders as MO
from qbreak import panel, paths

from test_manual_core import AT, _pbook


def _save(b, tag="paper"):
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")


def _deviate():
    b = _pbook(pct=50.0)
    b["manual"]["core_fix"] = {"1655.T": 1000}
    b["manual"]["blocks"] = {"6758.T": {"until": "2026-11-02", "since": "2026-10-02", "id": "M1"}}
    _save(b)
    return b


def test_no_card_when_everything_follows_the_rules():
    _pbook()
    assert "id='restore'" not in panel.render("paper", "tok", now=AT)
    ok, msg, _ = panel.submit({"book": "paper", "kind": "restore"}, AT)
    assert not ok and "已经全部按自动交易规则" in msg


def test_card_lists_each_override_as_a_chip_with_one_button():
    _deviate()
    h = panel.render("paper", "tok", now=AT)
    i = h.index("id='restore'")
    card = h[i:h.index("</section>", i)]
    assert "data-act='restore'" in card and "chip warn" in card
    for k in ("固定 1,000 口", "闲置资金比例 50%", "不买回"):
        assert k in card
    assert h.index("id='restore'") > h.index("data-tab='more'") if "data-tab='more'" in h else True


def test_restore_needs_confirm_then_writes_one_record_per_override():
    _deviate()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "restore"}, AT)
    assert not ok and rec["need_confirm"] and MO.unseen("paper", json.loads((paths.state_dir() / "live_unified_paper.json").read_text())) == []
    c = rec["confirm"]
    assert c["title"] == "恢复自动交易规则" and c["danger"]
    assert "取消固定 1,000 口" in c["text"] and "50% → 100%" in c["text"] and "解除不自动买回" in c["text"] and "HALT 不动" in c["text"]
    ok, msg, first = panel.submit({"book": "paper", "kind": "restore", "confirm": c["token"]}, AT)
    assert ok and "恢复自动交易规则（3 条" in msg
    book = json.loads((paths.state_dir() / "live_unified_paper.json").read_text())
    got = [(r["kind"], r.get("ticker"), r.get("pct"), r.get("clear")) for r in MO.unseen("paper", book)]
    assert ("corefix", "1655.T", None, True) in got and ("core", None, 100.0, None) in got and ("unblock", "6758.T", None, None) in got
    assert MO.core_fixed(book, "paper") == {} and MO.core_pct_now("paper", book) == 100.0
    ok, msg, rec = panel.submit({"book": "paper", "kind": "restore"}, AT)   # 写了之后：没有要恢复的了（解除在等决策 = 已经在解除）
    assert not ok and not (rec or {}).get("need_confirm")


def test_wrong_token_gives_a_fresh_confirm_and_writes_nothing():
    _deviate()
    ok, _m, rec = panel.submit({"book": "paper", "kind": "restore", "confirm": "old"}, AT)
    assert not ok and rec["need_confirm"] and rec["confirm"]["changed"]


def test_readonly_book_has_no_card():
    assert panel._restore_card("tachibana_dryrun", {"manual": {"core_pct": 0}}, {}, AT) == ""
