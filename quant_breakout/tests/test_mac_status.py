"""mac_status 入口没设 QBREAK_HOME 时用 ~/.qbreak/home（2026-10-24 复核）：以前落到仓库的 var/，报错状态。"""
from __future__ import annotations

import os

from qbreak import mac_status as MS
from qbreak import paths


def _fake_build(seen):
    def build(now=None, run=None):
        seen.append(str(paths.home()))
        return {"title": "qbreak ✓", "at": "2026-10-24 09:00", "items": []}
    return build


def test_unset_home_uses_dot_qbreak_home(tmp_path, monkeypatch, capsys):
    home = tmp_path / "u" / ".qbreak" / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "u"))
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    seen = []
    monkeypatch.setattr(MS, "build", _fake_build(seen))
    assert MS.main(["--print"]) == 0
    out = capsys.readouterr().out
    assert seen == [str(home)]
    assert out.splitlines()[0] == f"数据目录：{home}（没设 QBREAK_HOME，自动用这个）"


def test_set_home_is_kept(tmp_path, monkeypatch, capsys):
    (tmp_path / "u" / ".qbreak" / "home").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "u"))
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path / "mine"))
    seen = []
    monkeypatch.setattr(MS, "build", _fake_build(seen))
    MS.main(["--print"])
    assert seen == [str(tmp_path / "mine")]
    assert capsys.readouterr().out.splitlines()[0] == f"数据目录：{tmp_path / 'mine'}"


def test_no_dot_qbreak_home_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "nobody"))
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    assert MS._pick_home() is None
    seen = []
    monkeypatch.setattr(MS, "build", _fake_build(seen))
    MS.main(["--print"])
    assert "QBREAK_HOME" not in os.environ and seen == [str(paths.PROJECT_ROOT / "var")]
