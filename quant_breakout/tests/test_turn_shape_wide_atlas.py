"""scripts/turn_shape_wide_atlas.py：只读结果画图 —— 组内形状 = 起涨 / 起跌点减本组平均、页面没有残留占位符、数据可解析、名字里没有会被当成标签的「<」。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_wide_atlas as A  # noqa: E402


def _model(top, ext=0.58):
    return {"deciles": {str(d): {"R20x": (top if d == 9 else -0.2 if d == 0 else 0.0)} for d in range(10)}, "top_ci_pp": [top - 0.3, top + 0.3],
            "auc": 0.88, "auc_base": 0.74, "auc_ext": ext, "tier": "没有用", "gates": {f"G{i}": i < 3 for i in range(1, 7)}}


def _cell(rows=1000, info=False):
    m = {"auc": 0.86, "auc_ext": 0.55, "top_pp": 0.1, "bottom_pp": -0.2, "spread_pp": 0.3, "top_ci_pp": [-0.2, 0.4], "info": info}
    return {"rows": rows, "per_day": 60.0, "RS_pct": 0.7, "FS_pct": 0.3, "M_median_pct": 20.0, "bins": 10, "rise": dict(m), "fall": dict(m, spread_pp=0.8)}


def _paths():
    rng = {"d": (-60, 40), "w": (-26, 8), "m": (-24, 3)}
    return {tf: {lab: {str(o): (0.0 if o == 0 else k * min(abs(o), 10) * (1 if o < 0 else -1)) for o in range(lo, hi + 1)}
                 for lab, k in (("RS", 1.0), ("FS", -1.0), ("ALL", 0.2))} for tf, (lo, hi) in rng.items()}


def _res():
    cnt = {"C": {"stocks_per_day": 3000.0, "rows": 600000}, "last": "2026-07-17"}
    U = {uk: {"counts": cnt, "models": {"rise": _model(-0.05), "fall": _model(-0.15)}} for uk in ("U0", "U1", "U2")}
    U["U0"]["reproduce"] = {"available": True, "rows": [1162144, 1162144], "rise": {"auc": [0.894, 0.894]}, "fall": {"auc": [0.883, 0.883]}, "same": True}
    U["U0"]["models"]["rise"]["auc_ext"], U["U0"]["models"]["fall"]["auc_ext"] = 0.582, 0.601
    U["U1"]["buckets"] = {k: _cell() for k in ("L1", "L2", "L3")}
    U["U2"]["groups"] = {k: _cell() for k in "ABCDEF"}
    U["U2"]["groups"]["F"] = {"rows": 50, "per_day": 5.0, "RS_pct": 1.0, "FS_pct": 0.5, "M_median_pct": 22.0, "bins": 0,
                              "rise": {"auc": 0.8, "auc_ext": 0.6}, "fall": {"auc": 0.5, "auc_ext": 0.4}}
    U["U2"]["group_atlas"] = {k: {"paths": _paths(), "patterns": {}} for k in "ABCDEF"}
    return {"git": {"rev": "abc1234"}, "universes": U}


def test_group_paths_relative_to_group_mean():
    gp = A.group_paths(_res())
    s = gp["A"]["tf"]["d"]
    assert s["x"][0] == -60 and s["RS"][s["x"].index(-10)] == 8.0 and s["FS"][s["x"].index(-10)] == -12.0   # 10 − 2、−10 − 2
    assert gp["A"]["n_rs"] == 7 and gp["F"]["n_fs"] == 0


def test_build_page():
    page = A.build(_res())
    assert "__" not in page and "非投资建议" in page and "<title>起涨起跌·全部品种</title>" in page
    data = json.loads(page.split("const D = ", 1)[1].split(";\n", 1)[0])
    assert len(data["uni"]) == 6 and [g["k"] for g in data["groups"]] == list("ABCDEF") and data["groups"][-1]["bins"] == 0
    assert all("<" not in v for v in A.SHORT.values())
    assert "没有一个品种组 / 成交额档「有信息」" in page and "最接近的是" in page
