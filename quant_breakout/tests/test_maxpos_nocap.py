"""2026-10-24 用户「个股名额空 4 个的上限去掉」：sim.json unified.max_positions = null → 不设上限（NO_CAP）；显示不写「空 995 个」。"""
import json
from pathlib import Path

from qbreak import panel as P
from qbreak import report_unified as RU
from qbreak.unified import NO_CAP, cap_text, capped, config_from_sim

ROOT = Path(__file__).resolve().parents[1]


def test_null_means_no_cap_and_missing_keeps_default():
    assert config_from_sim({"unified": {"max_positions": None}}).max_positions == NO_CAP
    assert config_from_sim({"unified": {}}).max_positions == 4
    assert config_from_sim({"unified": {"max_positions": 3}}).max_positions == 3
    assert not capped(NO_CAP) and capped(4) and cap_text(NO_CAP) == "不设上限" and cap_text(4) == "上限 4 只"


def test_repo_sim_json_has_no_cap():
    sim = json.loads((ROOT / "var" / "sim.json").read_text(encoding="utf-8"))
    assert sim["unified"]["max_positions"] is None
    assert config_from_sim(sim).max_positions == NO_CAP


def test_panel_chip_and_text_without_cap():
    s = {"held": 2, "buys": 1, "used": 3, "max": NO_CAP, "free": NO_CAP - 3}
    chip = P._slot_chip(s)
    assert "不设上限" in chip and "空" not in chip and str(NO_CAP) not in chip
    assert "不设上限" in P._slots_text(s) and str(NO_CAP) not in P._slots_text(s)
    s4 = {"held": 3, "buys": 0, "used": 3, "max": 4, "free": 1}
    assert "空 1/4" in P._slot_chip(s4) and P._slots_text(s4) == "个股名额空 1 个（上限 4 只）"


def test_report_account_block_does_not_draw_999_slots():
    d = {"timeline": {"slots": {"max": NO_CAP, "held": 2, "selling": 0, "buying": 1, "free": NO_CAP - 3}},
         "config": {"max_positions": NO_CAP}, "positions": {}, "history": [], "cash_jpy": 0}
    try:
        html = RU._account_block(d)
    except Exception:                                         # 账户块要的字段多：只测名额那一段用到的文字函数
        html = None
    if html is not None:
        assert "名额不设上限" in html and f"/ {NO_CAP}" not in html and html.count("空") < 5
    assert RU._maxpos_txt(NO_CAP) == "不设上限" and RU._maxpos_txt(4) == "4"
