"""FJE 按修正口径重新检验（scripts/fje_recheck.py；2026-10-03 用户 ㊼ ①「重新检验，不过就撤」）：登记的判定、只在修正口径下运行、
与第一个研究循环第 15 轮同一段代码（状态 / 接法 / 第一关 / 第二关的随机对照）、输出不覆盖当初的文件。"""
import inspect
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fje_recheck as F  # noqa: E402
import loop_r15_fxeunion as R15  # noqa: E402
import research_loop as RL  # noqa: E402


def test_registered_decision_rule():
    assert F.decision(RL.FOUND) == F.KEEP == "保留"
    assert F.decision(RL.FAIL1) == F.decision(RL.FAIL2) == F.DROP == "撤掉"
    assert F.OUT != R15.OUT and F.ORIG == (f"{R15.OUT}.json", f"{R15.OUT}_stage2_FJE.json")


def test_refuses_old_fx_alignment(monkeypatch):
    import equity_idle_study as EI
    monkeypatch.setenv(EI.FX_ALIGN_ENV, "prev")
    with pytest.raises(SystemExit):
        F.run_once()


def test_same_code_as_round_15():
    src = inspect.getsource(F.run_once)
    for s in ("R15.states(W)", "Y.hedged_frame(W[\"inp\"])", "R15.fje_over(W, uni, hedged)", "LCM.run(W, e)", "LCM.run(W, e, **ov)",
              "RL.stage1(cand, base)", "RL.stage2(stat, vals)", "RL.verdict(s1, s2)", "if s1[\"ok\"]:"):
        assert s in src, s
    s2 = inspect.getsource(F.stage_two)
    assert "R15._placebo_one" in s2 and "range(RL.PLACEBO_N)" in s2
    assert (R15.SEED0, R15.SHIFT_GAP, R15.SHIFT_FROM) == (20261015, 250, "2000-01-03")
    assert inspect.getsource(R15._placebo_one).count("fje_over(W, shifted(state, seed), hedged)") == 1


def test_write_both_outcomes(tmp_path, monkeypatch):
    from qbreak import paths
    monkeypatch.setattr(paths, "home", lambda: tmp_path)
    acct = lambda c: {"cagr": 10.0, "dd": -20.0, "calmar": c, "h1": c, "h2": c, "n": 5, "mean": 1.0, "win": 50.0}   # noqa: E731
    base = {e: acct(0.6) for e in RL.ERAS}
    cand = {e: acct(v) for e, v in zip(RL.ERAS, (0.66, 0.64, 0.57))}
    s1 = RL.stage1(cand, base)
    assert not s1["ok"] and not s1["S2"]                                                     # J −0.03 < −0.02
    res = {"code": "x", "dirty": False, "fx_align": "same", "base": base, "cand": cand, "stage1": s1, "stage2": None, "placebo": None, "q": {},
           "verdict": RL.verdict(s1, None), "decision": F.decision(RL.verdict(s1, None)), "original": {},
           "core_trades": {e: {"B0": {}, "FJE": {}} for e in RL.ERAS},
           "describe": {e: {"in_bull_pct": 10.0, "episodes": 3} for e in RL.ERAS},
           "old": {k: {"cagr": 1.0, "dd": -2.0, "calmar": 0.5} for k in ("B0", "FXE", "JBH", "FJE")}, "seconds": 1}
    F.write(res)
    md = (tmp_path / "out" / f"{F.OUT}.md").read_text(encoding="utf-8")
    assert "第一关不过 →「撤掉」" in md and "第二关：第一关没全过 → 不做" in md
    s2 = RL.stage2(0.4, [0.1] * RL.PLACEBO_N)
    res2 = {**res, "stage1": {**s1, "ok": True}, "stage2": s2, "q": {50: 0.1, 95: 0.1, 99: 0.1}, "verdict": RL.FOUND, "decision": F.KEEP}
    F.write(res2)
    md2 = (tmp_path / "out" / f"{F.OUT}.md").read_text(encoding="utf-8")
    assert "更好候选 →「保留」" in md2 and "400 次随机最大 +0.1000" in md2
    assert pd.read_json(tmp_path / "out" / f"{F.OUT}.json", typ="series")["decision"] == F.KEEP
