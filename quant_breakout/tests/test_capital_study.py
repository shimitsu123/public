"""资金规模与名额分配（scripts/capital_study.py；2026-09-26 事先登记）：一手放宽默认关、打开后只在上限与现金之内买一手、
一段权益曲线的年化 / 回撤 / Calmar、判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak.unified import UnifiedConfig, UnifiedEngine

from test_unified import D, EX, P, _bars

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capital_study as CS                                                    # noqa: E402


def _run(one_lot: float, px: float = 3000.0):
    ind = {"7777.T": _bars(D, [px] * 8, entry_on=[D[1]])}                      # 默认一手 = ¥300,000 > 名额 ¥250,000
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={},
                        one_lot_cap_pct=one_lot)
    ue = UnifiedEngine(ind, cfg, {"JP": P, "US": P}, EX, {})
    ue.run()
    return ue


def test_one_lot_relaxation_default_off_and_within_cap():
    assert UnifiedConfig().one_lot_cap_pct == 0.0
    off = _run(0.0)
    assert not off.st.trades and off.skipped["lot"] == 1                        # 现行：一手超过名额 → 跳过
    on = _run(0.34)
    t = on.st.trades or [{"ticker": k, "shares": v.shares} for k, v in on.st.pos.items()]
    assert [x["ticker"] for x in t] == ["7777.T"] and t[0]["shares"] == 100     # 一手 ≤ 权益 × 34% → 买一手
    tight = _run(0.29)
    assert not tight.st.trades and tight.skipped["lot"] == 1                     # 一手 > 权益 × 29% → 仍跳过


def test_config_from_sim_reads_one_lot_option():
    from qbreak.unified import config_from_sim
    assert config_from_sim({"unified": {"one_lot_cap_pct": 0.34}}).one_lot_cap_pct == 0.34
    assert config_from_sim({"unified": {}}).one_lot_cap_pct == 0.0


def test_seg_stats_cagr_drawdown_calmar():
    idx = pd.bdate_range("2020-01-01", "2022-01-01")
    e = pd.Series(np.linspace(100, 121, len(idx)), index=idx)
    e.iloc[100:120] = e.iloc[100] * 0.8                                         # 中间回撤 20%
    s = CS.seg_stats(e)
    yrs = (idx[-1] - idx[0]).days / 365.25
    assert s["cagr"] == pytest.approx(((121 / 100) ** (1 / yrs) - 1) * 100, abs=0.01)
    assert s["dd"] == pytest.approx(-20.0, abs=0.05) and s["calmar"] == pytest.approx(s["cagr"] / abs(s["dd"]), abs=0.001)
    assert CS.seg_stats(e, "2021-01-01")["dd"] > -1                             # 后半段没有那次回撤
    assert CS.seg_stats(e.iloc[:5])["calmar"] is None


def _r(c10, h1, h2, c20, dd20, cap=1_000_000, n=3, ol=0.0):
    return {"capital": cap, "slots": n, "one_lot": ol, "w10": {"calmar": c10}, "h1": {"calmar": h1}, "h2": {"calmar": h2},
            "w20": {"calmar": c20, "dd": dd20}}


def test_decide_rules():
    R = {"1000000|4": _r(0.50, 0.40, 0.60, 0.36, -35.0, n=4),
         "1000000|3": _r(0.58, 0.45, 0.65, 0.37, -36.0),                         # 通过
         "1000000|2": _r(0.70, 0.30, 0.90, 0.40, -30.0, n=2),                    # 前半变差 → 不通过
         "1000000|5": _r(0.54, 0.45, 0.65, 0.37, -35.0, n=5),                    # 主窗口只 +0.04 → 不通过
         "1000000|6": _r(0.60, 0.45, 0.65, 0.37, -38.0, n=6),                    # 20 年回撤深 3 pp → 不通过
         "2000000|4": _r(0.90, 0.9, 0.9, 0.9, -20.0, cap=2_000_000, n=4)}         # 别的资金规模不参加判定
    V = CS.decide(R, "1000000|4")
    assert V["best"] == "1000000|3" and set(V["per"]) == {"1000000|3", "1000000|2", "1000000|5", "1000000|6"}
    assert V["per"]["1000000|2"] and V["per"]["1000000|5"] and V["per"]["1000000|6"]


ROOT = Path(__file__).resolve().parents[1]


def test_repo_sim_one_lot_relaxation_reverted_to_off():
    """2026-09-26 用户确认启用 U2（一手放宽 50%），2026-09-27 生效前用户确认撤回：仓库的 var/sim.json → config_from_sim 一手放宽 0（关），
    其余名额设定不变；一手超过名额就跳过。功能本身还在（研究用）：打开 50% 时一手 ≤ 权益 50% 买一手、超过跳过。"""
    import json
    from qbreak.unified import config_from_sim
    sim = json.loads((ROOT / "var" / "sim.json").read_text(encoding="utf-8"))
    cfg = config_from_sim(sim)
    assert cfg.one_lot_cap_pct == 0.0 and (cfg.position_pct, cfg.max_positions, cfg.max_position_pct) == (0.25, 4, 0.34)
    cur = _run(cfg.one_lot_cap_pct, px=4800.0)                                 # 一手 ¥480,000 > 名额 ¥250,000 → 跳过
    assert not cur.st.trades and not cur.st.pos and cur.skipped["lot"] == 1
    on = _run(0.5, px=4800.0)                                                  # 一手 ¥480,000 ≈ 权益 48%
    t = on.st.trades or [{"ticker": k, "shares": v.shares} for k, v in on.st.pos.items()]
    assert [x["ticker"] for x in t] == ["7777.T"] and t[0]["shares"] == 100
    over = _run(0.5, px=5200.0)                                                # 一手 ¥520,000 > 权益 50% → 跳过
    assert not over.st.trades and not over.st.pos and over.skipped["lot"] == 1


def test_liveu_copies_sim_json_to_mac_home_for_the_executor(tmp_path):
    """Mac：scripts/liveu.sh 每次运行先把仓库的 var/sim.json 拷到 ~/.qbreak/home（这里用临时目录），执行器（paper / tachibana 相同）
    经 config_from_sim 读它 → 与云端模拟盘同一设定。python 用假的（只打印参数），不跑执行器。"""
    import json
    import os
    import subprocess
    stub = tmp_path / "py"
    stub.write_text('#!/bin/sh\necho "stub $*"\n', encoding="utf-8")
    stub.chmod(0o755)
    env = {**os.environ, "QBREAK_LIVEU_HOME": str(tmp_path / "home"), "QBREAK_PYTHON": str(stub)}
    for broker in ("paper", "tachibana"):
        r = subprocess.run(["bash", "scripts/liveu.sh", "--broker", broker, "--status"], cwd=ROOT, env=env, capture_output=True, timeout=60)
        assert r.returncode == 0 and f"stub run.py live-u --broker {broker} --status" in r.stdout.decode("utf-8", "replace")
        synced = json.loads((tmp_path / "home" / "sim.json").read_text(encoding="utf-8"))
        assert synced == json.loads((ROOT / "var" / "sim.json").read_text(encoding="utf-8"))
        from qbreak.unified import config_from_sim
        assert config_from_sim(synced).one_lot_cap_pct == 0.0
