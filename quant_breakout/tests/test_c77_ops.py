"""〔77〕C 第 5 段：执行质量汇总（LU-18）、开户引导（OPS-14）、交易时段保持清醒（OPS-13 / UX-13）。都只读 / 可选，不改交易。"""
import argparse
import os
import subprocess
from pathlib import Path

from qbreak import exec_quality as EQ

ROOT = Path(__file__).resolve().parent.parent


def _book():
    return {"history": [
        {"fill_bar": "2026-10-01", "orders": [
            {"side": "BUY", "kind": "stock", "ticker": "7203.T", "qty": 100, "sent_qty": 100, "status": "FILLED",
             "ref_px": 3000.0, "filled_qty": 100, "filled_px": 3030.0},
            {"side": "SELL", "kind": "core", "ticker": "1545.T", "qty": 100, "sent_qty": 100, "status": "FILLED",
             "ref_px": 240.0, "filled_qty": 100, "filled_px": 241.2}]},
        {"fill_bar": "2026-10-02", "orders": [
            {"side": "BUY", "kind": "stock", "ticker": "6758.T", "qty": 100, "sent_qty": 100, "status": "UNFILLED",
             "ref_px": 2000.0, "filled_qty": 0},
            {"side": "BUY", "kind": "stock", "ticker": "9984.T", "qty": 100, "status": "BLOCKED", "ref_px": 1.0}]}],
        "compare_history": [{"date": "2026-10-01", "comparable": True, "same": True},
                            {"date": "2026-10-02", "comparable": True, "same": False}]}


def test_quality_report_slippage_fill_rate_and_compare():
    r = EQ.report(_book())
    assert r["days"] == 2 and r["orders"] == 4 and r["filled"] == 2
    assert r["fill_rate"] == round(200 / 300 * 100, 1)                     # BLOCKED 没发出：不算进发出股数
    assert r["slip"]["BUY"]["mean_bp"] == 100.0 and r["slip"]["SELL"]["mean_bp"] == -50.0   # 卖高了 = 对你有利（负）
    assert r["compare"] == {"n": 2, "same": 1, "last_diff": "2026-10-02"}
    txt = "\n".join(EQ.lines(r))
    assert "没成交 1 次" in txt and "被挡（没发） 1 次" in txt and "比较 2 天、一致 1 天" in txt
    assert EQ.report(_book(), since="2026-10-02")["orders"] == 2


def test_quality_cli(capsys):
    import json

    import run
    from qbreak import paths
    (paths.state_dir() / "live_unified_tachibana.json").write_text(json.dumps(_book()), encoding="utf-8")
    assert run.cmd_live_quality(argparse.Namespace(broker="tachibana", demo=False, dry_run=False, since=None)) == 0
    assert "成交价差" in capsys.readouterr().out


def test_onboard_lists_steps_and_next(monkeypatch, capsys):
    import run
    from qbreak import live_gate
    monkeypatch.setattr(live_gate, "check", lambda **k: [
        {"group": "门槛", "name": "① a", "ok": True, "text": "OK"},
        {"group": "准备", "name": "⑤ 本番只读检查", "ok": False, "text": "★ 还没做：bash scripts/liveu.sh probe"}])
    assert run.cmd_live_onboard(argparse.Namespace()) == 1
    out = capsys.readouterr().out
    assert "1. 开户" in out and "★ ⑤ 本番只读检查：还没做" in out and "下一步：⑤ 本番只读检查" in out
    assert live_gate.load_saved()["ok"] is False


def test_awake_agent_plist(tmp_path):
    agents, home = tmp_path / "la", tmp_path / "h"
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "launchctl").write_text("#!/bin/sh\nexit 0\n")
    (fake / "launchctl").chmod(0o755)
    env = {**os.environ, "QBREAK_LAUNCH_AGENTS": str(agents), "QBREAK_LIVEU_HOME": str(home), "PATH": f"{fake}:/usr/bin:/bin"}
    r = subprocess.run(["bash", str(ROOT / "scripts" / "install_launchd_awake.sh")], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    p = (agents / "com.qbreak.awake.plist").read_text(encoding="utf-8")
    assert "<string>/usr/bin/caffeinate</string>" in p and "<string>-s</string>" in p and "<string>23700</string>" in p
    assert p.count("<key>Hour</key><integer>8</integer><key>Minute</key><integer>55</integer>") == 5
    r = subprocess.run(["bash", str(ROOT / "scripts" / "install_launchd_awake.sh"), "uninstall"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and not (agents / "com.qbreak.awake.plist").exists()
