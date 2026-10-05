"""tbf_export.py — 把 TBF「像起跌点就不买」用的冻结评分模型导出到 var/tbf_model.json（2026-10-06，用户：「把 TBF 加进现在的选股判断」）。

来源：scripts/turn_shape_combo.py 的重拟合（var/cache/turn_shape_combo_models.pkl；没有缓存就用登记的代码在同一份 J-Quants 缓存上重算）：
日线尺度 = turn_shape_wide U2（登记 2757571）、周 / 月线尺度 = turn_shape_mtf（登记 de4b60c）的下跌模型（像起跌点）。
先决条件同研究：重拟合的前 12 个系数与结果文件逐个相同、训练行数相同、宽表打分 = 样本表打分 → 不满足就不导出。
只导出参数（46 个特征的 1% / 99% 截尾分位、均值、标准差，截距与 46 个系数），不含任何行情。用法：python scripts/tbf_export.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import turn_shape_combo as TC                                                # noqa: E402
import turn_shape_study as S                                                 # noqa: E402

OUT = "tbf_model.json"


def export(models: dict) -> dict:
    """turn_shape_combo.load_models 的结果 → 写进 var/tbf_model.json 的内容（只要下跌模型）。"""
    if not models.get("ok"):
        raise SystemExit("评分模型核对不过（与登记的结果不同 / 接线核对不过）→ 不导出")
    sc = {}
    for k in TC.SCALES3:
        f = models["fits"][k]
        st = f["st"]
        sc[k] = {"lo": [float(x) for x in st["lo"]], "hi": [float(x) for x in st["hi"]], "mu": [float(x) for x in st["mu"]],
                 "sd": [float(x) for x in st["sd"]], "w": [float(x) for x in f["w"]["fall"]], "n_train": int(f["n_train"])}
    chk = {k: {"coef_same": bool(models["check"][k]["fall"]["same"]), "n_train": models["check"][k]["n_train"],
               "wiring_max_diff": models["check"][k]["wiring"]["fall"]} for k in TC.SCALES3}
    return {"model": "TBF（像起跌点就不买）的三个尺度下跌模型", "feats": list(S.FEATS),
            "source": {"D": "turn_shape_wide U2（登记 2757571）", "W": "turn_shape_mtf 周线尺度（登记 de4b60c）", "M": "turn_shape_mtf 月线尺度（登记 de4b60c）",
                       "study": "scripts/turn_shape_combo.py（登记 23e248a，结果 b36c893）"},
            "rule": {"top_pct": TC.TOP, "min_scales": 2, "lmc": "一律当缺值（标准化后 0）"}, "check": chk, "scales": sc}


def main() -> int:
    from qbreak import paths
    m = TC.load_models()
    doc = export(m)
    fp = paths.PROJECT_ROOT / "var" / OUT
    fp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(fp, {k: doc["check"][k] for k in TC.SCALES3})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
