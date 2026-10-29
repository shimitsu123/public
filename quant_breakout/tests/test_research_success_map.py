"""研究成功率统计（scripts/research_success_map.py）：层的划分、第二关百分位的读法、只差一条的口径、真实状态文件上的合计。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_success_map as T  # noqa: E402


def test_layer_and_pctile():
    assert T.layer_of(1, {"id": "UBG"}) == ("个股层", "闸门·离场") and T.layer_of(1, {"id": "FJE"}) == ("核心层", "核心")
    assert T.layer_of(2, {"family": "核心·熊市避险资产"})[0] == "核心层" and T.layer_of(2, {"family": "执行·核心分批切换"})[0] == "核心层"
    assert T.layer_of(2, {"family": "风险层·账户回撤刹车"})[0] == "账户风险层"
    assert T.layer_of(4, {"family": "选股·季节性"}) == ("个股层", "选股") and T.layer_of(5, {"family": "仓位·基本面"}) == ("个股层", "仓位")
    assert T.layer_of(3, {"family": "个股层·DeMark 离场"}) == ("个股层", "闸门·离场")
    assert T.pctile_of({"verdict": "第二关不过", "note": "第二关 400 次里最大 +0.254（约第 99.5 百分位）"}) == 99.5
    assert T.pctile_of({"verdict": "第二关不过", "why": "在 400 次循环平移里排约 98%（8 次 ≥ 它）"}) == 98.0
    assert T.pctile_of({"verdict": "更好候选"}) == 100.0 and T.pctile_of({"verdict": "第二关不过", "note": "—"}) is None


def test_real_state_totals():
    R = T.rows(ROOT / "var")
    assert len(R) >= 86
    by = T.summarize(R, "layer")
    assert by["核心层"]["found"] >= 1 and "FJE" in by["核心层"]["ids_pass1"]
    assert all(not (x["near"] and x["pass1"]) for x in R)
    assert all(x["passed"] is None or x["passed"] <= x["full"] for x in R)
