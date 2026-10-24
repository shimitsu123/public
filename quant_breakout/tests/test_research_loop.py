"""研究循环（scripts/research_loop.py、scripts/loop_common.py，2026-10-01 登记）：登记值、两关判定、上限与状态、规则指纹、J 终点固定。"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_common as LCM  # noqa: E402
import research_loop as RL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _acct(cal, dd=-20.0, h1=None, h2=None):
    return {e: {"calmar": c, "dd": dd, "h1": c if h1 is None else h1, "h2": c if h2 is None else h2} for e, c in zip(RL.ERAS, cal)}


def test_registered_constants():
    assert (RL.CAP, RL.SUM_MIN, RL.ERA_TOL, RL.DD_TOL, RL.PLACEBO_N) == (20, 0.03, 0.02, 2.0, 400)
    assert RL.ERAS == ("Z", "E", "J") and LCM.J_END == "2026-09-30"
    assert (RL.FOUND, RL.FAIL1, RL.FAIL2) == ("更好候选", "第一关不过", "第二关不过")


def test_stage1_each_condition():
    base = _acct([0.90, 0.55, 0.55])
    ok = RL.stage1(_acct([0.91, 0.565, 0.565]), base)
    assert ok["ok"] and abs(ok["sum"] - 0.04) < 1e-9 and not ok["applies"] and ok["lenses"] is None
    assert not RL.stage1(_acct([0.90, 0.56, 0.56]), base)["S1"]                          # 合计 +0.02 < +0.03
    low = RL.stage1(_acct([0.875, 0.60, 0.56]), base)                                     # Z 低 0.025
    assert low["S1"] and not low["S2"] and not low["ok"]
    deep = RL.stage1({**_acct([0.95, 0.56, 0.56]), "E": {"calmar": 0.56, "dd": -22.5, "h1": 0.56, "h2": 0.56}}, base)
    assert not deep["S3"] and not deep["ok"]                                               # E 回撤深 2.5 pp
    edge = RL.stage1({**_acct([0.95, 0.56, 0.56]), "E": {"calmar": 0.56, "dd": -22.0, "h1": 0.56, "h2": 0.56}}, base)
    assert edge["S3"]                                                                      # 正好 2 pp 算过
    half = RL.stage1(_acct([0.95, 0.60, 0.60], h1=0.0), _acct([0.90, 0.55, 0.55], h1=0.1))
    assert not half["S4"] and half["h1"] < 0 and half["h2"] > 0                             # 前一半合计变差
    none = RL.stage1({**_acct([0.95, 0.60, 0.60]), "J": {"calmar": None, "dd": -20.0, "h1": 0.5, "h2": 0.5}}, base)
    assert not none["S1"] and not none["S2"] and not none["ok"]


def test_stage1_other_stocks_and_lenses():
    base, cand = _acct([0.90, 0.55, 0.55]), _acct([0.92, 0.57, 0.57])
    good = {"W": {"n": 100, "dwin": 0.5, "dmean": 0.1}, "Jx": {"n": 0, "dwin": None, "dmean": None}}
    assert RL.stage1(cand, base, trade=good)["ok"] and RL.stage1(cand, base, trade=good)["applies"]
    bad = {"W": {"n": 100, "dwin": 0.5, "dmean": -0.01}, "Jx": {"n": 50, "dwin": 1.0, "dmean": 0.2}}
    assert not RL.stage1(cand, base, trade=bad)["S5"]
    lz = {"loeo": (cand, base), "fwd": (_acct([0.90, 0.56, 0.56]), base)}                  # 前推合计 +0.02 → S6 不过
    r = RL.stage1(cand, base, lenses=lz)
    assert not r["S6"] and not r["ok"] and r["lenses"]["loeo"]["S1"] and not r["lenses"]["fwd"]["S1"]
    assert RL.stage1(cand, base, lenses={"loeo": (cand, base), "fwd": (cand, base)})["S6"]
    assert not RL.stage1(cand, base, lenses={"loeo": (cand, base)})["S6"]                  # 少一种检验 = 不过


def test_stage2_strictly_beats_max_of_400():
    pl = list(np.linspace(-0.05, 0.05, 400))
    assert RL.stage2(0.051, pl)["ok"]
    r = RL.stage2(0.05, pl)
    assert not r["ok"] and r["ge_stat"] == 1                                               # 等于最大值 = 不过
    assert not RL.stage2(0.2, pl[:399])["ok"]                                              # 次数不够
    assert not RL.stage2(0.2, pl[:399] + [None])["ok"]                                     # 有算不出的
    assert not RL.stage2(None, pl)["ok"] and not RL.stage2(float("nan"), pl)["ok"]
    assert RL.verdict({"ok": False}, None) == RL.FAIL1 and RL.verdict({"ok": True}, None) == RL.FAIL2
    assert RL.verdict({"ok": True}, {"ok": False}) == RL.FAIL2 and RL.verdict({"ok": True}, {"ok": True}) == RL.FOUND


def _rnd(k, verdicts):
    return {"round": k, "date": "2026-10-01", "title": f"第 {k} 轮", "approaches": [{"id": f"R{k}{i}", "verdict": v, "sum": 0.01}
                                                                                for i, v in enumerate(verdicts)]}


def test_state_append_cap_and_status():
    st = {"cap": 20, "status": "running", "rounds": []}
    st = RL.add_round(st, _rnd(1, [RL.FAIL1, RL.FAIL2]))
    assert RL.used(st) == 2 and RL.left(st) == 18 and st["status"] == "running"
    with pytest.raises(ValueError):
        RL.add_round(st, _rnd(3, [RL.FAIL1]))                                              # 轮次号要接着来
    with pytest.raises(ValueError):
        RL.add_round(st, _rnd(2, [RL.FAIL1] * 19))                                         # 超过剩下的上限
    with pytest.raises(ValueError):
        RL.add_round(st, _rnd(2, ["通过"]))                                                 # 结论只有三种
    full = RL.add_round(st, _rnd(2, [RL.FAIL1] * 18))
    assert full["status"] == "exhausted" and RL.left(full) == 0
    with pytest.raises(ValueError):
        RL.add_round(full, _rnd(3, [RL.FAIL1]))
    found = RL.add_round(st, _rnd(2, [RL.FAIL1, RL.FOUND]))
    assert found["status"] == "found" and len(st["rounds"]) == 1                            # 原来的不改
    assert "做法 4 / 20" in RL.status_text({**found, "start": "2026-10-01", "baseline": {}})


def test_status_after_adoption(monkeypatch):
    st = {"start": "2026-10-01", "baseline": {}, "fingerprint": "aaa", "rounds": [], "cap": RL.CAP,
          "adopted": {"date": "2026-10-02", "candidate": "X", "change": "Q1 → Q1H", "fingerprint_after": "bbb"}}
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: "bbb")
    t = RL.status_text(st)
    assert "采用：2026-10-02" in t and "已按「采用」改过" in t and "★" not in t
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: "ccc")
    assert "★ 与登记时不同" in RL.status_text(st)                                           # 采用之后又改了别的 → 照旧提示


def test_fingerprint_sensitive_to_rules_not_notes(tmp_path):
    for f in ("sim.json", "best_params_JP.json", "bullbear.json"):
        shutil.copy(ROOT / "var" / f, tmp_path / f)
    fp = RL.rules_fingerprint(tmp_path)
    assert fp == RL.rules_fingerprint(tmp_path) and len(fp) == 16
    sim = json.loads((tmp_path / "sim.json").read_text(encoding="utf-8"))
    sim["idle_cash"]["note"] = "改了说明文字"
    sim["note"] = "改了说明文字"
    (tmp_path / "sim.json").write_text(json.dumps(sim, ensure_ascii=False), encoding="utf-8")
    assert RL.rules_fingerprint(tmp_path) == fp                                             # 说明文字不算
    sim["idle_cash"]["mode"] = "K0"
    (tmp_path / "sim.json").write_text(json.dumps(sim, ensure_ascii=False), encoding="utf-8")
    assert RL.rules_fingerprint(tmp_path) != fp                                             # 闲置资金改了 → 不同
    sim["idle_cash"]["mode"] = "Q1"
    sim["fwd_judgment"]["enabled"] = False
    (tmp_path / "sim.json").write_text(json.dumps(sim, ensure_ascii=False), encoding="utf-8")
    assert RL.rules_fingerprint(tmp_path) != fp


def test_registered_state_file_is_consistent():
    st = RL.load_state(ROOT / "var")                                                       # 仓库里的那一份（测试时 QBREAK_HOME 可能指向别处）
    if not st:
        pytest.skip("研究循环还没有登记")
    assert st["cap"] == RL.CAP and st["criteria"]["sum_min"] == RL.SUM_MIN and st["criteria"]["placebo_n"] == RL.PLACEBO_N
    assert set(st["baseline"]) >= set(RL.ERAS) and RL.used(st) <= RL.CAP
    assert [r["round"] for r in st.get("rounds") or []] == list(range(1, len(st.get("rounds") or []) + 1))


def test_fix_j_end_and_mul_scale():
    ctx = {"era": "J", "end": None, "windows": {"J": ("2017-01-04", None), "J1": ("2017-01-04", "2021-12-31"), "J2": ("2022-01-01", None)}}
    f = LCM.fix_j_end(ctx)
    assert f["end"] == "2026-09-30" and f["windows"]["J"] == ("2017-01-04", "2026-10-01") and f["windows"]["J2"][1] == "2026-10-01"
    assert f["windows"]["J1"] == ("2017-01-04", "2021-12-31") and ctx["end"] is None                    # 原来的不改
    z = {"era": "Z", "end": "2006-09-30", "windows": {"Z": ("2001-01-04", "2006-09-30")}}
    assert LCM.fix_j_end(z) is z
    a = pd.Series([1.0, 0.5, 1.0, 0.75], index=pd.bdate_range("2020-01-06", periods=4))
    b = pd.Series([0.5], index=[pd.Timestamp("2020-01-07")])
    m = LCM.mul_scale(a, b)
    assert m.tolist() == [1.0, 0.25, 0.5, 0.375]                                           # b 之前缺 = 1，之后向后填
    assert LCM.mul_scale(None, b) is b and LCM.mul_scale(a, None) is a
