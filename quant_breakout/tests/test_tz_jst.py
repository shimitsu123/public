"""时间一律按日本时间（JST）的再发防止（2026-10-11 用户「消息里面的时间都改为日本时间、横展开、再发防止」）：
qbreak 包一 import 就把进程的时区固定成 Asia/Tokyo（qbreak/__init__.py）—— run.py 以外的入口（python -m qbreak.*、scripts/*.py、
面板、菜单栏叫的 mac_status）在 UTC 的机器（云端后备）上也显示日本时间。"""
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAIVE = re.compile(r"(?<![\w.])(?:_?dt\.|_d\.)?(?:datetime\.now\(\)|datetime\.today\(\)|date\.today\(\)|datetime\.utcnow\(\))")


def test_importing_qbreak_pins_tokyo_even_on_a_utc_machine():
    env = {**os.environ, "TZ": "UTC"}
    env.pop("QBREAK_KEEP_TZ", None)
    code = ("import datetime as d, time; import qbreak; "
            "print(time.tzname[0], (d.datetime.now() - d.datetime.utcnow()).total_seconds() / 3600)")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    name, off = r.stdout.split()
    assert name == "JST" and round(float(off)) == 9


def test_mac_status_entry_prints_jst_time_on_utc_machine(tmp_path):
    env = {**os.environ, "TZ": "UTC", "QBREAK_HOME": str(tmp_path), "QBREAK_LAUNCH_AGENTS": str(tmp_path / "la")}
    r = subprocess.run([sys.executable, "-m", "qbreak.mac_status", "--print"], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    m = re.search(r"（(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) JST）", r.stdout)
    jst_now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).replace(tzinfo=None)
    assert m and abs((dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M") - jst_now).total_seconds()) < 180


def test_scripts_with_naive_now_import_qbreak():
    """scripts/*.py 里用了不带时区的 now() / today() 的，必须 import qbreak（这样进程时区是 JST）；否则写 now_jst()。"""
    bad = []
    for p in sorted((ROOT / "scripts").glob("*.py")):
        s = p.read_text(encoding="utf-8")
        if NAIVE.search(s) and not re.search(r"^\s*(from qbreak\b|import qbreak\b)", s, re.M):
            bad.append(p.name)
    assert not bad, bad


def test_news_times_are_labelled_jst():
    from qbreak import news as NW
    from qbreak import panel
    from qbreak.utils import write_json
    write_json(NW.cache_dir() / "news.json", {"generated": "2026-10-11 10:23 JST", "events": [
        {"id": "u1", "title": "x", "time": "2026-10-10T15:46+00:00", "event_labels": ["t"], "alert": True, "threat": 1, "chain": {}}]})
    h = panel._news_card(dt.datetime(2026, 10, 11, 10, 30))
    assert "10/11 00:46 JST" in h                                          # UTC 15:46 → JST 00:46（第二天）
    assert "时间都是日本时间（JST）" in h
