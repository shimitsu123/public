"""买卖点参数横展开（scripts/param_study.py；2026-09-26 事先登记）：方案都合法且只改一个参数、候选规则、组合时同一参数只取一个值、判定。"""
import sys
from dataclasses import replace
from pathlib import Path

from qbreak.config import StrategyParams

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import param_study as PS                                                      # noqa: E402


def test_variants_valid_one_parameter_each_and_differ_from_current():
    base = StrategyParams(max_distribution_days=6, max_upper_shadow_ratio=3.0, exit_on_climax=True)   # 现行日本参数的非默认项
    labels = [lab for lab, _ in PS.VARIANTS]
    assert len(labels) == len(set(labels)) and len(labels) >= 40
    for lab, ch in PS.VARIANTS:
        p = replace(base, **ch).validate()
        assert len(PS.key_of(ch).split("+")) == 1, lab                       # 每个方案只改一个参数
        assert any(getattr(p, k) != getattr(base, k) for k in ch), lab       # 真的和现行不同
    assert {"macd_signal", "vol_mult", "trend_ma_n", "stop_loss_pct", "trailing_stop_pct", "exit_on_climax"} <= {
        PS.key_of(ch) for _, ch in PS.VARIANTS}                              # 不止 MACD


def _r(d, dd=-30.0, v=0.5, v1=0.4, v2=0.6, vc=15.0, vdd=-30.0, a=0.4):
    return {"d": {"calmar": d, "dd": dd}, "v": {"calmar": v, "cagr": vc, "dd": vdd}, "v1": {"calmar": v1}, "v2": {"calmar": v2},
            "all": {"calmar": a}}


def test_candidates_and_best_per_param():
    B = _r(0.30)
    R = {"a": _r(0.34), "b": _r(0.40, dd=-33.0), "c": _r(0.36, dd=-29.0), "d": _r(0.32), "e": _r(0.50, dd=-35.0)}
    assert PS.candidates(R, B) == ["c", "a"]                                  # b、e 回撤深 3 / 5 pp；d 只高 0.02
    ch = {"a": {"vol_mult": 1.2}, "c": {"vol_mult": 2.0}, "x": {"time_stop_days": 20, "time_stop_min_ret_pct": 0.0}}
    assert PS.best_per_param(["c", "a", "x"], ch) == ["c", "x"]              # 同一个参数只取最好的一个
    assert PS.key_of(ch["x"]) == "time_stop_days"


def test_decide_rules():
    B = _r(0.30)
    assert PS.decide(_r(0.4, v=0.56, v1=0.41, v2=0.61, vc=15.5, vdd=-31.0, a=0.41), B) == []
    f = PS.decide(_r(0.4, v=0.54, v1=0.39, v2=0.61, vc=14.9, vdd=-32.5, a=0.39), B)
    assert len(f) == 5                                                       # 验证期 +0.04、前半变差、年化低、回撤深 2.5 pp、20 年低
