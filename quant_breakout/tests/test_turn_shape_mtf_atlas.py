"""scripts/turn_shape_mtf_atlas.py：只读结果画图 —— 形状 = 起涨 / 起跌点减同期全部、模型值折算成每 20 日、页面没有残留占位符、
数据可解析、周 / 月线上涨模型区间整体 < 0 时摘要写「方向相反」、显示名改写。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_mtf_atlas as A  # noqa: E402


def _model(top, ci):
    return {"deciles": {str(d): {"R20x": (top if d == 9 else -0.4 if d == 0 else 0.0)} for d in range(10)}, "top_ci_pp": ci,
            "auc": 0.86, "auc_base": 0.80, "auc_ext": 0.50, "tier": "没有用", "gates": {f"G{i}": i < 3 for i in range(1, 7)}}


def _cell():
    m = {"auc": 0.85, "auc_ext": 0.52, "top_pp": -0.5, "spread_pp": 0.4, "top_ci_pp": [-1.0, 0.1], "info": False}
    return {"rows": 1000, "per_day": 50.0, "RS_pct": 0.8, "FS_pct": 0.2, "bins": 10, "rise": dict(m), "fall": dict(m)}


def _atlas():
    rng = {"d": (-60, 40), "w": (-26, 8), "m": (-24, 3)}
    paths = {tf: {lab: {str(o): (0.0 if o == 0 else k * min(abs(o), 10) * (1 if o < 0 else -1)) for o in range(lo, hi + 1)}
                  for lab, k in (("RS", 1.0), ("FS", -1.0), ("ALL", 0.2))} for tf, (lo, hi) in rng.items()}
    lifts = {f: {"q": {str(q): {"RS": rs, "FS": fs} for q, rs, fs in ((0, x, 0.1), (4, 0.2, x / 2))}}
             for f, x in (("d_r5", 3.0), ("w_streak", 4.5), ("m_rsi", 2.0))}
    return {"C": {"paths": paths, "lifts": lifts, "patterns": {}}}


def _inputs():
    cnt = {"rows": 100000, "days": 200, "per_day": 500.0, "RS_pct": 0.5, "FS_pct": 0.1}
    wide = {"universes": {"U2": {"atlas": _atlas(), "counts": {"C": cnt}, "groups": {k: _cell() for k in "ABCDEF"},
                                 "models": {"rise": _model(-0.1, [-0.3, 0.1]), "fall": _model(-0.2, [-0.4, 0.0])}}}}
    sc = {"W": (3.25, _model(-1.0, [-2.0, -0.1])), "M": (6.3, _model(-2.3, [-4.8, 0.2]))}
    mtf = {"git": {"rev": "abc1234"}, "scales": {k: {"atlas": _atlas(), "counts": {"C": cnt}, "groups": {g: _cell() for g in "ABCDEF"}, "scale": f,
                                                     "models": {"rise": m, "fall": _model(0.5, [-0.5, 1.5])}} for k, (f, m) in sc.items()}}
    return mtf, wide


def test_shapes_and_models_normalized():
    mtf, wide = _inputs()
    blk = A.scale_blocks(mtf, wide)
    sh = A.shapes(blk)
    s = sh["W"]["tf"]["w"]
    assert s["x"][0] == -26 and s["RS"][s["x"].index(-10)] == 8.0 and s["FS"][s["x"].index(-10)] == -12.0   # 10 − 2、−10 − 2
    assert sh["D"]["n_rs"] == 500 and sh["D"]["n_fs"] == 100
    mod = {(m["sc"], m["mk"]): m for m in A.models(blk)}
    assert len(mod) == 6 and mod[("D", "rise")]["h"] == 20 and mod[("W", "rise")]["h"] == 65 and mod[("M", "rise")]["h"] == 126
    assert mod[("W", "rise")]["top_n"] == round(-1.0 / 3.25, 3) and mod[("M", "rise")]["ci_n"] == [round(-4.8 / 6.3, 3), round(0.2 / 6.3, 3)]
    assert mod[("D", "rise")]["gates"] == "✓✓✗✗✗✗"


def test_build_page():
    mtf, wide = _inputs()
    page = A.build(mtf, wide)
    assert "__" not in page and "非投资建议" in page and "<title>起涨起跌·三种尺度</title>" in page and "abc1234" in page
    data = json.loads(page.split("const D = ", 1)[1].split(";\n", 1)[0])
    assert sorted(data["shapes"]) == ["D", "M", "W"] and len(data["models"]) == 6 and len(data["groups"]) == 18
    assert data["lifts"]["W"]["RS"][0]["lift"] == 4.5 and data["lifts"]["W"]["FS"][0]["lift"] == 2.25
    assert "三种尺度都「事前用不了」" in page and "方向还相反" in page                    # 只有周线上涨的区间整体 < 0
    assert "周线尺度 −1.00 pp / 65 日" in page and "月线尺度 −2.30 pp / 126 日" not in page
    assert A.nice("日 连涨 / 连跌 最低 1/5") == "日 连跌最多的 1/5" and A.nice("周 连涨 / 连跌 最高 1/5") == "周 连涨最多的 1/5"
