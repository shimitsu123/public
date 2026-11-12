"""scripts/layer_tax_study.py：登记值与「税后看个股层」的读法（四）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import layer_tax_study as LT  # noqa: E402
import nisa_tax_study as NT  # noqa: E402


def test_registration_shares_the_nisa_study_tax_code():
    assert LT.NT is NT and LT.FP == "1241753c8f2529c6" and LT.ERAS == ("Z", "E", "J")
    assert LT.POLICIES == NT.POLICIES and LT.SIZES == NT.SIZES and LT.DECIDE_SIZE == 1_000_000 and LT.RESCUE == ("N3", "N1")
    doc = LT.__doc__
    for s in ("O0 = B4 但这个年代全部 W2 信号都不开", "Δ = B4 税后年化 − O0 税后年化", "三个年代 P0 税后 Δ 都 ≤ 0", "模拟盘 / 执行器不因这次研究改"):
        assert s in doc


def _at(p0, n3=None, n1=None):
    out = {"P0": dict(zip(LT.ERAS, p0))}
    out["N3"] = dict(zip(LT.ERAS, n3 or p0))
    out["N1"] = dict(zip(LT.ERAS, n1 or p0))
    return out


def test_read_positive_and_pre_only():
    r = LT.read({"Z": 7.0, "E": 2.0, "J": 0.5}, _at((5.0, 0.8, -0.3)))
    assert r["positive"] == ["Z", "E"] and r["nonpositive"] == ["J"] and r["pre_only"] == ["J"]
    assert r["rescue"] == {} and not r["all_nonpositive"]


def test_read_rescue_and_all_nonpositive():
    r = LT.read({"Z": 1.0, "E": -0.5, "J": 0.2}, _at((0.0, -1.0, -0.2), n3=(0.4, -0.5, 0.1), n1=(-0.1, 0.2, -0.1)))
    assert r["all_nonpositive"] and r["positive"] == []
    assert r["pre_only"] == ["Z", "J"]                                      # E 税前就不正 → 不算「只在税前有用」
    assert r["rescue"] == {"Z": ["N3"], "E": ["N1"], "J": ["N3"]}
    zero = LT.read({"Z": 0.0, "E": 0.0, "J": 0.0}, _at((0.0, 0.0, 0.0)))  # Δ = 0 算「没有贡献」
    assert zero["nonpositive"] == ["Z", "E", "J"] and zero["pre_only"] == []
