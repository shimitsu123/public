"""scripts/turn_shape_atlas.py：只读结果画图 —— 形状 = 起涨 / 起跌点减全部样本、形态按倍数排序且只取 ≥ 200 次、页面没有残留占位符、数据可解析。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_atlas as A  # noqa: E402


def _res():
    rng = {"d": (-60, 40), "w": (-26, 8), "m": (-24, 3)}
    paths = {tf: {lab: {str(o): (0.0 if o == 0 else k * (1 if o < 0 else -1) * min(abs(o), 10)) for o in range(lo, hi + 1)}
                  for lab, k in (("RS", 1.0), ("FS", -1.0), ("ALL", 0.1))} for tf, (lo, hi) in rng.items()}
    pats = {"pw_B3": {"n": 1811, "RS": 6.95, "FS": 0.0, "R20x": 0.27}, "pd_BIGB": {"n": 12654, "RS": 0.01, "FS": 7.65, "R20x": -0.56},
            "pd_GAP3D": {"n": 165, "RS": 16.0, "FS": 0.0, "R20x": -0.98}, "pd_HAM": {"n": 13041, "RS": 0.76, "FS": 0.26, "R20x": -0.18},
            "pd_DOJI": {"n": 20}}
    model = lambda v: {"deciles": {str(d): {"R20x": v * (d - 4.5) / 10} for d in range(10)}, "top_ci_pp": [-0.4, 0.3], "auc": 0.8941, "auc_base": 0.7421}  # noqa: E731
    return {"git": {"rev": "abc1234"}, "counts": {"last": "2026-07-17", "C": {"stocks_per_day": 2786.9, "rows": 618688, "RS_pct": 0.75, "FS_pct": 0.3,
                                                                              "M_median_pct": 24.8}},
            "atlas": {"C": {"paths": paths, "patterns": pats}}, "models": {"rise": model(0.1), "fall": model(-0.1)}}


def test_series_and_patterns():
    res = _res()
    s = A.series(res)
    i = s["d"]["x"].index(-10)
    assert s["d"]["x"][0] == -60 and s["d"]["x"][-1] == 40 and s["d"]["RS"][i] == 9.0 and s["d"]["FS"][i] == -11.0
    rs = A.top_patterns(res, "RS")
    assert [r["code"] for r in rs] == ["pw_B3", "pd_HAM", "pd_BIGB"]                # ≥ 200 次（GAP3D 165 次、DOJI 没算倍数不列）、倍数从高到低
    assert rs[0]["name"] == "周 黒三兵" and rs[0]["dir"] == "看跌" and rs[0]["other"] == 0.0
    assert A.top_patterns(res, "FS")[0]["name"] == "日 大陽線"


def test_build_has_no_placeholders_and_parsable_data():
    page = A.build(_res(), {"models": {"rise": {"all": {"auc": 0.894}, "within": {"auc": 0.5822}}, "fall": {"all": {"auc": 0.883}, "within": {"auc": 0.6011}}}})
    assert "__" not in page.replace("__proto__", "") and "非投资建议" in page and "<title>起涨起跌平均形状</title>" in page
    data = json.loads(page.split("const D = ", 1)[1].split(";\n", 1)[0])
    assert data["post"]["rise"] == [0.894, 0.582] and data["auc"]["rise"] == [0.894, 0.742] and len(data["dec"]["fall"]) == 10
    assert "最后 10 个交易日多跌约 9.0%" in page and "−0.40〜+0.30" in page
