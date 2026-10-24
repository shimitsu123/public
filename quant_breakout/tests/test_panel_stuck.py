"""2026-10-15 用户「qbreak网页app经常卡住 永久解决这个问题」：面板不再因为自己叫的执行器 git pull 而重启、代码更新平滑换上（同一个进程号、
监听端口不关、不在写的中途换）、service worker 有超时与连不上时的退路、页面的连接检查 / 自动重连 / 安全的自动刷新、现价下载不卡住别的请求。"""
import datetime as dt
import gzip
import http.client
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from panel_js_harness import run_conn, run_sw
from qbreak import panel, paths
from qbreak.calendar_jp import JST

ROOT = Path(__file__).resolve().parent.parent
AT = dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)


def _book(tag="paper"):
    st = {"last_date": "2026-10-05", "cash_jpy": 500_000.0, "history": [["2026-10-05", 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {"1545.T": 100}}
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps({"state": st, "orders": []}), encoding="utf-8")


def _req(port, method, path, body=None, headers=None, timeout=10):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    h = {"Host": f"127.0.0.1:{port}"}
    h.update(headers or {})
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    out = r.status, r.read(), dict(r.getheaders())
    c.close()
    return out


@pytest.fixture()
def local():
    tok = panel.token()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    port = srv.server_address[1]
    srv.RequestHandlerClass = panel.make_handler(port, tok, clock=lambda: AT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port
    srv.shutdown()
    srv.server_close()


# ────────── ① 面板叫的执行器不 git pull（10-15 08:12：--retry 拉下新代码 → 面板重启、手机 502） ──────────
def _decided_book(tag, today_decided: bool):
    from qbreak.calendar_jp import now_jst, prev_trading_day
    ld = prev_trading_day(now_jst().date())
    ld = ld if today_decided else prev_trading_day(ld)
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps({"state": {"last_date": ld.isoformat()}, "orders": []}),
                                                                 encoding="utf-8")


def test_panel_triggered_runs_never_pull(monkeypatch):
    got = []

    class _P:
        def __init__(self, cmd, **kw):
            got.append((cmd, kw))
    monkeypatch.setattr(panel.subprocess, "Popen", _P)
    monkeypatch.delenv("QBREAK_LIVEU_PULL", raising=False)
    _decided_book("tachibana", True)                                          # 今天早上的决策已经在账本里（面板只在这之后叫 --retry）
    for mode in ("retry", "now", "cancel"):
        panel.Trigger._spawn("tachibana", mode)
        assert got[-1][1]["env"]["QBREAK_LIVEU_PULL"] == "fetch", mode       # 不 pull、不换代码；只 fetch 看远程停止
    panel.Trigger._spawn("paper", "catchup")                                   # 补跑 = 代替 07:40 的照常运行：要云端当天的输入，照旧 pull
    assert "QBREAK_LIVEU_PULL" not in got[-1][1]["env"] and "--retry" not in got[-1][0]
    monkeypatch.setenv("QBREAK_LIVEU_PULL", "0")                               # 本来就关掉了的：照旧关（不改成 fetch）
    panel.Trigger._spawn("paper", "retry")
    assert got[-1][1]["env"]["QBREAK_LIVEU_PULL"] == "0"


def test_run_that_acts_as_the_morning_run_still_pulls(monkeypatch):
    """今天早上的运行没完成（Mac 07:40 睡着 / 运行失败）时面板叫的运行 = 当早上的运行：照常 git pull 拉云端当天的日报 / 判断层
    （fetch 只给决策已经在账本里之后的运行）；面板自己的环境里万一有 fetch 也不带过去。"""
    got = []

    class _P:
        def __init__(self, cmd, **kw):
            got.append((cmd, kw))
    monkeypatch.setattr(panel.subprocess, "Popen", _P)
    monkeypatch.setenv("QBREAK_LIVEU_PULL", "fetch")
    _decided_book("paper", False)                                              # 账本还停在前天的决策
    panel.Trigger._spawn("paper", "catchup")
    assert "QBREAK_LIVEU_PULL" not in got[-1][1]["env"]
    panel.Trigger._spawn("paper", "retry")                                     # 万一这时叫了重试（run.py --retry 会按正常流程跑）：也照常 pull
    assert "QBREAK_LIVEU_PULL" not in got[-1][1]["env"]
    (paths.state_dir() / "live_unified_paper.json").unlink()                   # 账本读不了：照常 pull
    panel.Trigger._spawn("paper", "retry")
    assert "QBREAK_LIVEU_PULL" not in got[-1][1]["env"]
    for mode in ("now", "cancel"):                                             # 盘中 / 撤单本来就不 pull（liveu.sh 的开盘后路径；now_due 要早上的运行完成）
        panel.Trigger._spawn("paper", mode)
        assert got[-1][1]["env"]["QBREAK_LIVEU_PULL"] == "fetch", mode
    _decided_book("paper", True)
    panel.Trigger._spawn("paper", "retry")
    assert got[-1][1]["env"]["QBREAK_LIVEU_PULL"] == "fetch"
    at = dt.datetime(2026, 10, 15, 8, 10, tzinfo=JST)                          # 时刻按 JST 的交易日历：周四早上 → 应有的决策日 = 周三
    assert panel._pull_mode("paper", "retry", {"state": {"last_date": "2026-10-14"}}, at) == "fetch"
    assert panel._pull_mode("paper", "retry", {"state": {"last_date": "2026-10-13"}}, at) is None
    assert panel._pull_mode("paper", "retry", {}, at) is None
    mon = dt.datetime(2026, 10, 19, 8, 10, tzinfo=JST)                         # 周一早上 → 上周五
    assert panel._pull_mode("paper", "retry", {"state": {"last_date": "2026-10-16"}}, mon) == "fetch"
    assert panel._pull_mode("paper", "catchup", {"state": {"last_date": "2026-10-16"}}, mon) is None


def test_mac_login_decided_reads_the_book(tmp_path):
    from qbreak import mac_login as ML
    home = tmp_path / "h"
    (home / "state").mkdir(parents=True)
    d = dt.date(2026, 10, 15)
    assert ML.decided(home, "paper", d) is False                               # 没有账本 → 照常 pull
    for ld, want in (("2026-10-14", True), ("2026-10-13", False), ("", False)):
        (home / "state" / "live_unified_paper.json").write_text(json.dumps({"state": {"last_date": ld}}), encoding="utf-8")
        assert ML.decided(home, "paper", d) is want, ld
    (home / "state" / "live_unified_tachibana.json").write_text("{坏的", encoding="utf-8")
    assert ML.decided(home, "tachibana", d) is False


def _liveu_env(tmp_path, pull: str, show_halt: bool = True, pull_fail: bool = False):
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    stubs = {
        "git": ('#!/bin/sh\necho "git $*" >> "$CALLS"\n'
                + ('case "$*" in pull*) exit 1 ;; esac\n' if pull_fail else "")
                + ('case "$*" in show*) echo "云端：停" ; exit 0 ;; esac\n' if show_halt else 'case "$*" in show*) exit 128 ;; esac\n')
                + "exit 0\n"),
        "fakepy": ('#!/bin/sh\necho "py $*" >> "$CALLS"\n'
                   'case " $* " in *" -c "*) exit 0 ;; esac\nexit 0\n'),
        "osascript": "#!/bin/sh\nexit 0\n", "caffeinate": "#!/bin/sh\nexit 0\n",
    }
    for n, body in stubs.items():
        (b / n).write_text(body, encoding="utf-8")
        (b / n).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QBREAK_", "XPC_"))}
    env.update({"PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path / "home"), "CALLS": str(log),
                "QBREAK_PYTHON": str(b / "fakepy"), "QBREAK_LIVEU_HOME": str(tmp_path / "lh"), "QBREAK_LIVEU_WAIT_MIN": "0",
                "QBREAK_LIVEU_PULL": pull, "QBREAK_CAFFEINATED": "1", "QBREAK_NO_HOLD": "1",
                "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents"), "LC_ALL": "C.UTF-8"})
    (tmp_path / "home").mkdir(exist_ok=True)
    if log.exists():
        log.unlink()
    return env, log


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_fetch_mode_looks_at_remote_halt_without_pulling(tmp_path):
    env, log = _liveu_env(tmp_path, "fetch")
    subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper", "--retry"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    c = log.read_text(encoding="utf-8")
    fetched = tmp_path / "lh" / ".halt_remote_fetched"
    assert "git pull" not in c and "git fetch -q" in c and "git show @{u}:./var/HALT_REMOTE" in c
    assert f"--remote-halt {fetched}" in c and "--retry" in c                    # 远程停止照样看（fetch 到的那份）
    assert fetched.read_text(encoding="utf-8").strip() == "云端：停"
    env, log = _liveu_env(tmp_path, "fetch", show_halt=False)                  # 远端没有 HALT_REMOTE → 不留旧的
    subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper", "--phase", "now"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    assert not fetched.exists() and "git pull" not in log.read_text(encoding="utf-8")
    env, log = _liveu_env(tmp_path, "1")                                       # 定时任务（默认 1）：照旧先 pull
    subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper", "--retry"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    c = log.read_text(encoding="utf-8")
    assert "git pull -q --ff-only" in c and f"--remote-halt {ROOT / 'var' / 'HALT_REMOTE'}" in c


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_morning_pull_failure_still_sees_remote_halt(tmp_path):
    """07:40 git pull 失败（本地改动等）→ 工作区的 HALT_REMOTE 是旧的：照样 fetch 远端那份传给执行器（2026-10-24 复核）。"""
    env, log = _liveu_env(tmp_path, "1", pull_fail=True)
    r = subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    c = log.read_text(encoding="utf-8")
    fetched = tmp_path / "lh" / ".halt_remote_fetched"
    assert "git pull 失败" in r.stdout and "git fetch -q" in c and "git show @{u}:./var/HALT_REMOTE" in c
    assert f"--remote-halt {fetched}" in c and fetched.read_text(encoding="utf-8").strip() == "云端：停"


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_fetch_mode_pulls_when_the_morning_decision_is_not_in_the_book(tmp_path):
    """面板叫的（fetch），但今天早上的决策还不在账本里（mac_login --decided 退出码 1）→ 这次就是早上的运行：照常 git pull、用仓库的 HALT_REMOTE。"""
    env, log = _liveu_env(tmp_path, "fetch")
    fp = Path(env["QBREAK_PYTHON"])
    fp.write_text('#!/bin/sh\necho "py $*" >> "$CALLS"\ncase " $* " in *" --decided "*) exit 1 ;; esac\nexit 0\n', encoding="utf-8")
    r = subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "tachibana", "--demo", "--retry"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    c = log.read_text(encoding="utf-8")
    assert "-m qbreak.mac_login --decided tachibana_demo" in c                  # 看的是这次运行的账本
    assert "git pull -q --ff-only" in c and f"--remote-halt {ROOT / 'var' / 'HALT_REMOTE'}" in c
    assert "当早上的运行" in r.stdout
    env, log = _liveu_env(tmp_path, "fetch")                                   # 决策已经在账本里（退出码 0）→ 不 pull
    subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper", "--retry"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    c = log.read_text(encoding="utf-8")
    assert "-m qbreak.mac_login --decided paper" in c and "git pull" not in c
    env, log = _liveu_env(tmp_path, "fetch")                                   # 盘中 / 撤单：不看（本来就不 pull）
    subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper", "--phase", "now"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    c = log.read_text(encoding="utf-8")
    assert "--decided" not in c and "git pull" not in c


# ────────── ② 代码更新：等文件不再变 → 先试 import → 等请求做完 → 同一个进程里换新代码 ──────────
class _Seq:
    """假的 _mtimes：按时间表返回（秒 → 修改时间）。"""

    def __init__(self, plan):
        self.t0 = time.monotonic()
        self.plan = plan

    def __call__(self):
        el = time.monotonic() - self.t0
        cur = self.plan[0][1]
        for at, v in self.plan:
            if el >= at:
                cur = v
        return {"panel.py": cur}


class _FakeSrv:
    def __init__(self):
        self.calls = []

    def shutdown(self):
        self.calls.append(time.monotonic())


def _watch(monkeypatch, plan, preflight, run_s=1.2, stable=0.25):
    monkeypatch.setattr(panel, "_mtimes", _Seq(plan))
    stop, srv = threading.Event(), _FakeSrv()
    th = threading.Thread(target=panel._watch_code, args=(stop, srv), kwargs={"every": 0.02, "stable": stable, "preflight": preflight},
                          daemon=True)
    t0 = time.monotonic()
    th.start()
    th.join(run_s)
    stop.set()
    th.join(2)
    return srv, t0


def test_code_watcher_waits_until_files_stop_changing(monkeypatch):
    """git pull 一次改好几个文件、分几下写：最后一下之后 stable 秒才重启，只重启一次。"""
    tries = []
    srv, t0 = _watch(monkeypatch, [(0, 1.0), (0.1, 2.0), (0.2, 3.0), (0.3, 4.0)], lambda: tries.append(1) or True)
    assert len(srv.calls) == 1 and srv.calls[0] - t0 >= 0.3 + 0.25 - 0.05 and srv.qb_restart is True and tries == [1]


def test_code_watcher_keeps_old_code_when_new_code_does_not_import(monkeypatch):
    """新代码 import 失败 → 不重启（继续用旧代码）；同一版不再试；文件又改了（修好了）→ 再试、重启。"""
    tries = []

    def pre():
        tries.append(time.monotonic())
        return len(tries) > 1
    srv, _ = _watch(monkeypatch, [(0, 1.0), (0.1, 2.0), (0.8, 3.0)], pre, run_s=1.6, stable=0.2)
    assert len(tries) == 2 and len(srv.calls) == 1
    srv, _ = _watch(monkeypatch, [(0, 1.0), (0.1, 2.0), (0.2, 1.0)], lambda: True, run_s=0.8, stable=0.2)   # 改回去了 → 不动
    assert srv.calls == []


def test_preflight_runs_the_import_in_another_process(monkeypatch, caplog):
    assert panel._preflight() is True                                         # 这份代码 import 得了
    seen = []

    class _R:
        returncode, stderr = 1, "SyntaxError: bad"
    monkeypatch.setattr(panel.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or _R())
    with caplog.at_level(logging.WARNING, logger="qbreak"):
        assert panel._preflight() is False
    assert seen[0][1] == "-c" and seen[0][2] == panel._PREFLIGHT_PY and "继续用旧代码" in caplog.text


def test_preflight_also_imports_the_modules_panel_imports_inside_functions(tmp_path):
    """2026-10-15 复核：以前只 import qbreak.panel → 函数里才 import 的 qbreak 模块（webpush / news / live_ops …）坏了照样换进来。
    现在顺着 `from . import X` / `from .X import y` 一个个 import；缺的是别的包（可选的依赖）不算，缺 qbreak 自己的模块算。"""
    r = subprocess.run([sys.executable, "-c", panel._PREFLIGHT_PY], cwd=str(panel.paths.PROJECT_ROOT), capture_output=True, text=True,
                       timeout=60, check=False)
    assert r.returncode == 0, r.stderr[-800:]
    assert int(r.stdout.strip()) > 20                                          # 不只 panel 一个

    def fake_pkg(extra: str):
        """一个假的 qbreak 包：panel 的函数里 import 一个坏模块。"""
        root = tmp_path / f"r{len(list(tmp_path.iterdir()))}"
        (root / "qbreak").mkdir(parents=True)
        (root / "qbreak" / "__init__.py").write_text("", encoding="utf-8")
        (root / "qbreak" / "panel.py").write_text("def f():\n    from . import lazy as L\n    from .other import g\n", encoding="utf-8")
        (root / "qbreak" / "other.py").write_text("def g():\n    pass\n", encoding="utf-8")
        (root / "qbreak" / "lazy.py").write_text(extra, encoding="utf-8")
        return subprocess.run([sys.executable, "-c", panel._PREFLIGHT_PY], cwd=str(root), capture_output=True, text=True,
                              timeout=60, check=False, env={**os.environ, "PYTHONPATH": str(root)})
    ok = fake_pkg("X = 1\n")
    assert ok.returncode == 0 and ok.stdout.strip() == "3", ok.stderr
    bad = fake_pkg("def broken(:\n")
    assert bad.returncode != 0 and "SyntaxError" in bad.stderr
    gone = fake_pkg("from .missing import x\n")
    assert gone.returncode != 0 and "missing" in gone.stderr
    opt = fake_pkg("import not_installed_optional_pkg_xyz\n")                # 别的包（可选的依赖）缺 → 不算
    assert opt.returncode == 0, opt.stderr


def test_inflight_drain_waits_for_writes_longer_than_reads():
    f = panel._Inflight()
    f.enter(False)
    t0 = time.monotonic()
    assert f.drain(0.1, 5.0) is False and time.monotonic() - t0 < 1.0           # 只有读的：最多等 read_s
    f.leave(False)
    f.enter(True)
    threading.Timer(0.4, f.leave, args=(True,)).start()
    t0 = time.monotonic()
    assert f.drain(0.1, 5.0) is True and 0.3 < time.monotonic() - t0 < 3.0     # 有写的：等它做完（最多 write_s）
    assert f.drain(0.1, 0.1) is True


def test_make_srv_adopts_the_listening_socket_only_for_the_same_port():
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sk.bind(("127.0.0.1", 0))
    sk.listen(8)
    port = sk.getsockname()[1]
    fd = sk.detach()
    srv = panel._make_srv(port, panel.make_handler(port, "t" * 40), fd)
    try:
        assert srv.socket.fileno() == fd and srv.server_address[1] == port
    finally:
        srv.server_close()
    sk2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk2.bind(("127.0.0.1", 0))
    sk2.listen(1)
    other = sk2.detach()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    srv = panel._make_srv(free, panel.make_handler(free, "t" * 40), other)    # 端口对不上 → 不用它、照常 bind
    try:
        assert srv.server_address[1] == free and srv.socket.getsockname()[1] == free
    finally:
        srv.server_close()


DRIVER = r"""
import os, sys, threading, time
from pathlib import Path
from qbreak import panel
gen2 = bool(os.environ.get(panel.FDS_ENV))
flag = Path(sys.argv[2])
base = panel.make_handler

def make_handler(port, tok, trg=None, **kw):
    H = base(port, tok, trg, **kw)
    class S(H):
        def do_POST(self):
            if self.path == "/slow":
                time.sleep(1.5)
                self._send(200, b"done", "text/plain")
                return
            return H.do_POST(self)
    return S
panel.make_handler = make_handler
if gen2:
    panel._watch_code = lambda stop, srv, **kw: None
    print("GEN2", os.getpid(), flush=True)
else:
    def w(stop, srv, **kw):
        while not flag.exists():
            if stop.wait(0.02):
                return
        srv.qb_restart = True
        srv.shutdown()
    panel._watch_code = w
    print("GEN1", os.getpid(), flush=True)
panel.serve(port=int(sys.argv[1]), trigger=False, phone_port=0)
"""


def test_smooth_restart_keeps_the_port_and_finishes_the_write(tmp_path):
    """平滑重启（真的 os.execve）：重启的时候正在处理的写（POST）照样做完、回应完整；重启前后一直连得上（同一个监听端口、
    新连接在内核里排队）；同一个进程号（launchd 看不到退出）。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    drv = tmp_path / "drv.py"
    drv.write_text(DRIVER, encoding="utf-8")
    flag = tmp_path / "go"
    env = {**os.environ, "QBREAK_HOME": str(tmp_path / "home"), "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}
    env.pop(panel.FDS_ENV, None)
    p = subprocess.Popen([sys.executable, str(drv), str(port), str(flag)], cwd=str(tmp_path), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines: list = []
    threading.Thread(target=lambda: [lines.append(x) for x in p.stdout], daemon=True).start()
    try:
        for _ in range(200):
            if any("操作面板" in x for x in lines):
                break
            time.sleep(0.05)
        assert _req(port, "GET", "/sw.js")[0] == 200
        slow = {}
        th = threading.Thread(target=lambda: slow.update(r=_req(port, "POST", "/slow", body=b"{}",
                                                                headers={"Content-Type": "application/json"}, timeout=30)))
        th.start()
        time.sleep(0.3)
        flag.write_text("1", encoding="utf-8")                                 # 写还在处理时要求重启
        fails, oks, t_end = [], 0, time.monotonic() + 4.0
        while time.monotonic() < t_end:
            try:
                st, body, _ = _req(port, "GET", "/sw.js", timeout=10)
                oks += st == 200 and b"qbreak-v4" in body
            except OSError as e:
                fails.append(repr(e))
            time.sleep(0.02)
        th.join(30)
        assert slow["r"][0] == 200 and slow["r"][1] == b"done"                 # 写做完了才换进程
        assert fails == [] and oks > 20, (fails[:3], oks)
        assert p.poll() is None
        gen = [x for x in lines if x.startswith(("GEN1", "GEN2"))]
        assert [g.split()[0] for g in gen] == ["GEN1", "GEN2"] and gen[0].split()[1] == gen[1].split()[1] == str(p.pid)
        assert any("平滑重启：接着用原来的端口" in x for x in lines)
    finally:
        p.kill()
        p.wait(10)


def _serve_in_thread(monkeypatch, port, phone_port):
    """serve() 放在线程里跑（不在主线程 → 不装 SIGTERM 处理）；返回 (线程, 拿到本机端口服务的盒子)。"""
    box = {}
    monkeypatch.delenv(panel.FDS_ENV, raising=False)
    monkeypatch.setattr(panel, "_watch_code", lambda stop, srv, **kw: box.update(srv=srv))
    th = threading.Thread(target=panel.serve, kwargs={"port": port, "trigger": False, "phone_port": phone_port}, daemon=True)
    th.start()
    for _ in range(200):
        if "srv" in box:
            break
        time.sleep(0.02)
    return th, box


def _free_port():
    with socket.socket() as s_:
        s_.bind(("127.0.0.1", 0))
        return s_.getsockname()[1]


def test_phone_port_busy_at_start_is_retried_and_the_local_port_still_opens(monkeypatch):
    """2026-10-15 复核：以前先开手机端口、打不开（旧进程还占着）→ 这个进程一直没有手机访问。现在先开本机端口，
    手机端口后台重试，空出来就接上；本机页面的「手机」也跟着显示（make_handler 的 phone_port 每次现问）。"""
    monkeypatch.setattr(panel, "PHONE_RETRY_S", 0.1)
    port, pport = _free_port(), _free_port()
    hold = socket.socket()
    hold.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    hold.bind(("127.0.0.1", pport))
    hold.listen(1)
    seen = []
    base = panel.make_handler
    monkeypatch.setattr(panel, "make_handler", lambda *a, **kw: seen.append(kw.get("phone_port")) or base(*a, **kw))
    th, box = _serve_in_thread(monkeypatch, port, pport)
    try:
        assert _req(port, "GET", "/sw.js")[0] == 200                           # 本机端口照常
        pp = seen[0]
        assert callable(pp) and pp() is None                                   # 手机端口还没开：本机页面写「没开」
        hold.close()                                                           # 旧进程放开了
        for _ in range(100):
            if pp() == pport:
                break
            time.sleep(0.05)
        assert pp() == pport
        st_, body_, _ = _req(pport, "GET", "/sw.js")
        assert st_ == 200 and b"qbreak-v4" in body_                            # 手机端口是面板在接
    finally:
        hold.close()
        if "srv" in box:
            box["srv"].shutdown()
        th.join(10)
    assert not th.is_alive()
    with pytest.raises(OSError):                                               # 退出时两个端口都关了
        socket.create_connection(("127.0.0.1", pport), timeout=1).close()


def test_phone_port_retry_stops_when_the_panel_exits(monkeypatch):
    """一直打不开（别的程序占着）→ 一直重试；面板退出 → 重试的线程也停、不会在退出之后再开端口。"""
    monkeypatch.setattr(panel, "PHONE_RETRY_S", 0.05)
    port, pport = _free_port(), _free_port()
    hold = socket.socket()
    hold.bind(("127.0.0.1", pport))
    hold.listen(1)
    th, box = _serve_in_thread(monkeypatch, port, pport)
    try:
        assert _req(port, "GET", "/sw.js")[0] == 200
        time.sleep(0.3)
        box["srv"].shutdown()
        th.join(10)
        assert not th.is_alive()
        hold.close()
        time.sleep(0.3)                                                        # 退出之后空出来：不再开
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", pport), timeout=1).close()
    finally:
        hold.close()


TERM_DRIVER = r"""
import socket, sys
from qbreak import panel
port = int(sys.argv[1])

def drain(rs, ws):
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", port))
        print("DRAIN connected", flush=True)
    except OSError as e:
        print("DRAIN refused", type(e).__name__, flush=True)
    finally:
        s.close()
    return True
panel._INFLIGHT.drain = drain
panel._watch_code = lambda stop, srv, **kw: None
panel.serve(port=port, trigger=False, phone_port=0)
print("EXIT", flush=True)
"""


def test_sigterm_closes_the_listening_port_before_waiting_for_requests(tmp_path):
    """SIGTERM（launchctl kickstart -k / 重装）：先关监听再等正在处理的请求（以前等完才关 → 这几秒里新的连接排队干等、
    然后被断开；Serve 回空的 502）。现在新连接马上被拒，页面 / Serve 马上重试，新进程也能马上 bind。"""
    import signal as _sig
    port = _free_port()
    drv = tmp_path / "term.py"
    drv.write_text(TERM_DRIVER, encoding="utf-8")
    env = {**os.environ, "QBREAK_HOME": str(tmp_path / "home"), "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}
    env.pop(panel.FDS_ENV, None)
    p = subprocess.Popen([sys.executable, str(drv), str(port)], cwd=str(tmp_path), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines: list = []
    threading.Thread(target=lambda: [lines.append(x) for x in p.stdout], daemon=True).start()
    try:
        for _ in range(200):
            if any("操作面板" in x for x in lines):
                break
            time.sleep(0.05)
        assert _req(port, "GET", "/sw.js")[0] == 200
        p.send_signal(_sig.SIGTERM)
        p.wait(20)
        time.sleep(0.2)
        assert any(x.startswith("DRAIN refused") for x in lines), lines
        assert any(x.startswith("EXIT") for x in lines)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(10)


# ────────── ③ 静态文件：启动时读好的一份、带版本、gzip；页面 gzip + 只存操作面板 ──────────
def test_static_assets_are_versioned_snapshots(local):
    core = panel.STATIC["core.js"].decode("utf-8")
    assert f"from './net.js?v={panel.ASSET_V}'" in core and "from './net.js'" not in core   # 子模块也带版本（不再新旧混用）
    main = panel.STATIC["main.js"].decode("utf-8")
    assert f"import './conn.js?v={panel.ASSET_V}';" in main and "window.__qbReady = 1" in main
    st, body, h = _req(local, "GET", f"/static/core.js?v={panel.ASSET_V}", headers={"Accept-Encoding": "gzip"})
    assert st == 200 and h["Content-Encoding"] == "gzip" and gzip.decompress(body) == panel.STATIC["core.js"]
    assert "immutable" in h["Cache-Control"]
    st, body, h = _req(local, "GET", "/static/core.js")                       # 不带版本（以前存下的旧页面）：现在的、不让缓存
    assert st == 200 and body == panel.STATIC["core.js"] and h["Cache-Control"] == "no-cache" and "Content-Encoding" not in h
    st, body, _ = _req(local, "GET", "/static/core.js?v=0000000000")          # 版本不对 → 404（boot.js 重新载入）
    assert st == 404 and "版本不对" in body.decode("utf-8")
    assert _req(local, "GET", f"/static/boot.js?v={panel.ASSET_V}")[0] == 200
    st, body, h = _req(local, "GET", "/static/boot.js?v=0000000000")          # boot.js 不分版本（旧页面也拿得到它）、不让缓存
    assert st == 200 and body == panel.STATIC["boot.js"] and h["Cache-Control"] == "no-cache"


def test_page_is_gzipped_and_marked_for_the_service_worker(local):
    _book()
    st, body, h = _req(local, "GET", "/?book=paper", headers={"Accept-Encoding": "gzip"})
    html = gzip.decompress(body).decode("utf-8")
    assert st == 200 and h["X-Qbreak-Page"] == "main" and h["Content-Encoding"] == "gzip" and h["Cache-Control"] == "no-store"
    i, j = html.index(f"<script>{panel.BOOT_JS}</script>"), html.index(f"/static/main.js?v={panel.ASSET_V}")
    assert i < j and "<script src='/static/boot.js" not in html                             # boot.js 写在页面里（2026-10-15 复核：单独取的 boot.js
    assert f"'{panel.BOOT_SHA}'" in h["Content-Security-Policy"]              # 自己没载入成就没人接手）；CSP 按 sha256 放行这一段
    pre = [html.index(f"<link rel='modulepreload' href='/static/{m}.js?v={panel.ASSET_V}'>") for m in panel.JS_MODULES]
    assert i < min(pre) and max(pre) < j                                       # 模块一起取；在 boot.js 之后（它先接上出错事件）
    s = panel.status_json("paper")[1]
    assert s["v"] == panel.ASSET_V and s["boot"] == panel.BOOT_ID


def test_page_starts_on_the_requested_tab_without_waiting_for_scripts():
    """脚本还没跑（或没载入成）时页面也不是空的：服务器直接给开着的那一页（以前全部 pane 都藏着，等 app.js 打开）。"""
    _book()
    def on(h):
        return {x.split("'")[1] for x in h.split("class='pane on' data-tab=")[1:]}
    h = panel.render("paper", "t" * 40, AT)
    assert on(h) == {"home"} and "data-tabgo='home' aria-label='总览' class='on' aria-selected='true'" in h
    h = panel.render("paper", "t" * 40, AT, tab="trade")
    assert on(h) == {"trade"} and h.count("aria-selected='true'") == 1 and "data-tabgo='trade' aria-label='交易' class='on'" in h
    assert on(panel.render("paper", "t" * 40, AT, tab="../x")) == {"home"}


# ────────── ④ 现价：下载在锁外、同一组只下载一次、慢了先回上一次的 ──────────
def test_slow_yahoo_does_not_block_other_requests(monkeypatch):
    monkeypatch.setattr(panel, "_QUOTE_CACHE", {})
    monkeypatch.setattr(panel, "_QUOTE_FLIGHT", {})
    monkeypatch.setattr(panel, "_QUOTE_FAILN", {})
    monkeypatch.setattr(panel, "QUOTE_WAIT_S", 0.3)
    monkeypatch.setattr(panel, "QUOTE_FRESH_WAIT_S", 0.1)
    gate, calls = threading.Event(), []

    def slow(ts):
        calls.append(list(ts))
        gate.wait(5)
        return {t: {"px": 100.0} for t in ts}
    out = {}
    ths = [threading.Thread(target=lambda i=i: out.update({i: panel._quotes_cached(("paper", "A"), ["7203.T"], slow, True)}))
           for i in range(3)]
    t0 = time.monotonic()
    for th in ths:
        th.start()
    time.sleep(0.05)
    assert panel._QUOTE_LOCK.acquire(timeout=0.05)                              # 下载中锁是空的（K 线 / 别的组不用等）
    panel._QUOTE_LOCK.release()
    for th in ths:
        th.join(3)
    assert time.monotonic() - t0 < 1.5 and out == {0: {}, 1: {}, 2: {}} and calls == [["7203.T"]]   # 等不到先回空的；只下载一次
    gate.set()
    for _ in range(50):
        if not panel._QUOTE_FLIGHT:
            break
        time.sleep(0.02)
    assert panel._quotes_cached(("paper", "A"), ["7203.T"], slow, True) == {"7203.T": {"px": 100.0}}   # 后台下完放进缓存
    assert calls == [["7203.T"]]
    k = ("paper", "A")
    panel._QUOTE_CACHE[k] = (time.monotonic() - 999, panel._QUOTE_CACHE[k][1])  # 过期了、Yahoo 又慢：最多等 0.1 秒，先回上一次的
    gate.clear()
    t0 = time.monotonic()
    assert panel._quotes_cached(k, ["7203.T"], slow, True) == {"7203.T": {"px": 100.0}} and time.monotonic() - t0 < 0.8
    gate.set()


def test_failed_quotes_back_off_and_keep_the_last_prices(monkeypatch):
    monkeypatch.setattr(panel, "_QUOTE_CACHE", {})
    monkeypatch.setattr(panel, "_QUOTE_FLIGHT", {})
    monkeypatch.setattr(panel, "_QUOTE_FAILN", {})
    k = ("paper", "B")
    panel._QUOTE_CACHE[k] = (time.monotonic() - 999, {"7203.T": {"px": 1.0}})

    def boom(ts):
        raise TimeoutError("yahoo")
    assert panel._quotes_cached(k, ["7203.T"], boom, True) == {"7203.T": {"px": 1.0}}
    for _ in range(50):
        if not panel._QUOTE_FLIGHT:
            break
        time.sleep(0.02)
    at, q = panel._QUOTE_CACHE[k]
    assert q == {"7203.T": {"px": 1.0}} and panel._QUOTE_FAILN[k] == 1
    assert 60 - 10 - 1 <= time.monotonic() - at <= 60 - 10 + 1                  # 盘中：10 秒后再试（缓存 60 秒 − 10 秒）
    assert panel._short_timeout(lambda ts: ts)(["x"]) == ["x"]                 # 不接受 timeout 的取法：原样
    f = panel._short_timeout(lambda ts, timeout=10: timeout)
    assert f(["x"]) == panel.QUOTE_TIMEOUT_S


def test_hung_quote_download_is_abandoned_after_the_overall_limit(monkeypatch):
    """一次下载卡住（Yahoo 不回、超时也没起作用）：超过 QUOTE_FLIGHT_MAX_S 不再等它，下一个请求重新下载（以前这一组的现价永远停在旧的）；
    被放弃的那次晚到的「取不到」不盖掉之后取到的现价。"""
    monkeypatch.setattr(panel, "_QUOTE_CACHE", {})
    monkeypatch.setattr(panel, "_QUOTE_FLIGHT", {})
    monkeypatch.setattr(panel, "_QUOTE_FAILN", {})
    monkeypatch.setattr(panel, "QUOTE_WAIT_S", 0.1)
    monkeypatch.setattr(panel, "QUOTE_FLIGHT_MAX_S", 0.3)
    k, hang, calls = ("paper", "H"), threading.Event(), []

    def hung(ts):
        calls.append("hung")
        hang.wait(5)
        return {}
    assert panel._quotes_cached(k, ["7203.T"], hung, True) == {}
    assert panel._quotes_cached(k, ["7203.T"], hung, True) == {} and calls == ["hung"]   # 还没到上限：等同一次下载，不重复下
    time.sleep(0.35)

    def ok(ts):
        calls.append("ok")
        return {t: {"px": 7.0} for t in ts}
    assert panel._quotes_cached(k, ["7203.T"], ok, True) == {"7203.T": {"px": 7.0}} and calls == ["hung", "ok"]
    hang.set()                                                                 # 卡住的那次终于回来了（取不到）：不盖掉新的现价
    for _ in range(50):
        if not any(th.name == "qbreak-quotes" and th.is_alive() for th in threading.enumerate()):
            break
        time.sleep(0.02)
    assert panel._QUOTE_CACHE[k][1] == {"7203.T": {"px": 7.0}} and not panel._QUOTE_FLIGHT
    assert panel._quotes_cached(k, ["7203.T"], hung, True) == {"7203.T": {"px": 7.0}} and calls == ["hung", "ok"]   # 缓存还新：不再下载


# ────────── ⑤ 页面报告（连不上多久、旧页面、脚本没载入成）→ 面板日志；限流 ──────────
def test_client_log_is_sanitized_and_rate_limited(local, caplog, monkeypatch):
    monkeypatch.setattr(panel, "_CLOG_HITS", [])
    with caplog.at_level(logging.WARNING, logger="qbreak"):
        st, _, _ = _req(local, "GET", "/api/clientlog?e=reconnect%0A%3Cx%3E&d=" + "%E8%BF%9E" * 300 + "%0Aforged")
        assert st == 204
        for _ in range(panel.CLOG_MAX + 10):
            _req(local, "GET", "/api/clientlog?e=boot-script&d=x")
    rows = [r.getMessage() for r in caplog.records if "页面报告" in r.getMessage()]
    assert len(rows) == panel.CLOG_MAX and "\n" not in rows[0] and "<x>" not in rows[0] and len(rows[0]) < 300


# ────────── ⑥ 平滑重启时自动叫执行器的状态交给新进程 ──────────
def test_trigger_state_survives_the_reexec(monkeypatch):
    t = panel.Trigger(run=lambda tag, mode="retry": None, clock=lambda: AT, mono=lambda: 100.0, notify=lambda *a: None)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    t.procs["paper"] = child
    t.started["paper"] = AT
    t.last["paper"] = 90.0
    t.fails["paper"] = ("2026-10-06", 2)
    st = json.loads(json.dumps(t.export_state()))
    t2 = panel.Trigger(run=lambda tag, mode="retry": None, clock=lambda: AT, mono=lambda: 100.0, notify=lambda *a: None)
    t2.import_state(st)
    assert t2.started["paper"] == AT and t2.last["paper"] == 90.0 and t2.fails["paper"] == ("2026-10-06", 2)
    a = t2.procs["paper"]
    assert isinstance(a, panel._Adopted) and a.pid == child.pid and a.poll() is None   # 还在跑：新进程接着等它
    child.wait(5)
    assert a.poll() is not None
    t2.import_state({"procs": {"paper": "x"}})                                  # 格式不对：跳过、不出错


# ────────── ⑦ service worker：超时 → 存着的页面 / 离线页（自动重试 + 重新连接）；5xx 也是 ──────────
def test_service_worker_text():
    sw = panel.SW_JS
    assert "const C='qbreak-v4'" in sw and "NAV_MS=6000" in sw and "caches.delete" in sw and "updateViaCache" not in sw
    assert "e.data.qb==='patient'" in sw and "Date.now()<PATIENT ? NET_MS : NAV_MS; PATIENT=0;" in sw
    assert 'refresh content="5;url=' in sw and "重新连接" in sw and "下拉刷新" not in sw and "addEventListener('push'" in sw
    assert "/api/status" not in sw.split("addEventListener('fetch'")[1].split("addEventListener('push'")[0]   # 连接检查看真的网络


def test_service_worker_navigation_falls_back_fast(tmp_path):
    o = run_sw(tmp_path, r"""
  const main = "<!doctype html><html><head><title>x</title></head><body><script type='module' src='/static/main.js?v=aaaa'></script>v1</body></html>";
  NET.routes['/?book=paper'] = () => mkpage(main);
  const a = await go('/?book=paper');
  NET.routes['/?book=paper&tab=trade'] = () => 'hang';                    // Mac 睡着：请求一直挂着
  const b = await go('/?book=paper&tab=trade');
  NET.routes['/?book=paper'] = () => mkpage('<html><body>Bad Gateway</body></html>', 'x', 502);   // Tailscale Serve 接不上面板
  const c = await go('/?book=paper');
  const d = await go('/?book=tachibana');                                 // 这个账本没存过、连不上 → 离线页
  const d2 = await go('/?book=tachibana&tab=hold#tab=hold');              // 带 #：自动刷新 / 重新连接的网址去掉 #（不然只是同一页里跳锚点）
  NET.routes['/pair'] = () => mkpage('<html><head></head><body>pair</body></html>', 'pair');
  await go('/pair');
  NET.routes['/?book=paper'] = () => later(150, mkpage(main.replace('v1', 'v2')));   // 晚到的（> 6 秒）：先给旧的，晚到的存下
  const e = await go('/?book=paper');
  NET.routes['/?book=paper'] = () => 'down';
  const f = await go('/?book=paper');
  NET.routes['/r'] = () => ({type: 'opaqueredirect', status: 0, headers: new Headers(), text: async () => ''});
  const g = await go('/r');
  NET.routes['/?book=paper'] = () => later(150, mkpage(main.replace('v1', 'v3')));   // 页面生成得慢（> NAV_MS、< NET_MS）
  const ack = []; SL.message({data: {qb: 'patient'}, ports: [{postMessage: x => ack.push(x)}]});
  const h = await go('/?book=paper');                                     // conn.js 刚确认连得上 Mac → 这次等网络（不换成存着的再来回刷新）
  const h2 = await go('/?book=paper');                                    // 只管一次：下一次照常 NAV_MS 就换存着的
  return {h: h.text.indexOf('v3') > 0 && h.text.indexOf('qb-cache') < 0, ack, h2: h2.text.indexOf('qb-cache') > 0,a: a.text.indexOf('v1') > 0 && a.text.indexOf('qb-cache') < 0, keys: await cached(),
          b: b.status === 200 && b.text.indexOf("<meta name='qb-cache' content='1'>") > 0 && b.ms < 300,
          c: c.status === 200 && c.text.indexOf('qb-cache') > 0 && c.text.indexOf('Bad Gateway') < 0,
          d: d.text.indexOf('refresh content="5;url=' + ORIGIN + '/?book=tachibana">') > 0 && d.text.indexOf('<a href="' + ORIGIN + '/?book=tachibana">重新连接') > 0,
          d2: d2.text.indexOf('content="5;url=' + ORIGIN + '/?book=tachibana&amp;tab=hold">') > 0
              && d2.text.indexOf('<a href="' + ORIGIN + '/?book=tachibana&amp;tab=hold">') > 0 && d2.text.indexOf('#tab') < 0,
          e: e.text.indexOf('v1') > 0 && e.text.indexOf('qb-cache') > 0, f: f.text.indexOf('v2') > 0, g: g.type};
""")
    assert o["a"] and o["b"] and o["c"] and o["d"] and o["d2"] and o["e"] and o["f"], o
    assert o["keys"] == ["/?qb-page=paper"] and o["g"] == "opaqueredirect"     # 只存操作面板、按账本一份（配对页不存）
    assert o["h"] and o["ack"] == [1] and o["h2"], o


def test_service_worker_assets_and_read_only_api(tmp_path):
    o = run_sw(tmp_path, r"""
  NET.routes['/static/core.js?v=aaaa'] = () => new Response('core-a');
  const a1 = await go('/static/core.js?v=aaaa', 'cors');
  NET.routes['/static/core.js?v=aaaa'] = () => 'down';
  const a2 = await go('/static/core.js?v=aaaa', 'cors');                 // 带版本：缓存优先（不用网络）
  NET.routes['/static/old.js'] = () => new Response('old-1');
  await go('/static/old.js', 'cors');
  NET.routes['/static/old.js'] = () => 'hang';
  const u = await go('/static/old.js', 'cors');                         // 不带版本：网络优先，超时 → 存着的
  NET.routes['/static/none.js?v=bbbb'] = () => 'hang';
  const n = await go('/static/none.js?v=bbbb', 'cors');                 // 没存过又连不上：出错（boot.js 接手），不一直挂着
  NET.routes['/api/quotes?book=paper'] = () => new Response('{"ok":true,"px":1}');
  await go('/api/quotes?book=paper', 'cors');
  NET.routes['/api/quotes?book=paper'] = () => new Response('bad', {status: 502});
  const q = await go('/api/quotes?book=paper', 'cors');
  NET.routes['/api/chart?t=X'] = () => new Response('gw', {status: 504});
  const ch = await go('/api/chart?t=X', 'cors');                         // 没存过：原样给 504（页面照常显示「取不到」）
  for (const t of ['A', 'B', 'C', 'D']) { NET.routes['/api/chart?t=' + t] = () => new Response('{}'); await go('/api/chart?t=' + t, 'cors'); }
  NET.routes['/manifest.webmanifest'] = () => new Response('{"name":"qbreak"}');
  NET.routes['/apple-touch-icon.png'] = () => new Response('png');
  await go('/manifest.webmanifest', 'cors'); await go('/apple-touch-icon.png', 'no-cors');
  NET.routes['/manifest.webmanifest'] = () => 'down'; NET.routes['/apple-touch-icon.png'] = () => 'down';
  const mf = await go('/manifest.webmanifest', 'cors'), ic = await go('/apple-touch-icon.png', 'no-cors');   // 连不上：存着的（2026-10-15 复核）
  const st = await go('/api/status?book=paper', 'cors');
  const cl = await go('/api/clientlog?e=x', 'cors');
  const before = (await cached()).filter(k => k.indexOf('/static/') === 0);
  NET.routes['/?book=paper'] = () => mkpage("<html><head></head><body><script type='module' src='/static/main.js?v=cccc'></script></body></html>");
  await go('/?book=paper');
  const after = (await cached()).filter(k => k.indexOf('/static/') === 0);
  STORE['qbreak-v3'] = new Map();
  await new Promise(res => { SL.activate({waitUntil: p => p.then(res)}); });
  return {a1: a1.text, a2: a2.text, u: u.text, n: n.type, q: [q.status, q.cache, q.text], ch: ch.status,
          mf: mf.text, ic: ic.text,
          api: (await cached()).filter(k => k.indexOf('/api/') === 0), st: !!st.passed, cl: !!cl.passed, before, after,
          names: await caches.keys()};
""")
    assert o["a1"] == o["a2"] == "core-a" and o["u"] == "old-1" and o["n"] == "error", o
    assert o["q"] == [200, "1", '{"ok":true,"px":1}'] and o["ch"] == 504
    assert o["api"] == ["/api/chart?t=B", "/api/chart?t=C", "/api/chart?t=D"]  # 最多存 API_MAX 条（这里 3），旧的先删
    assert o["st"] and o["cl"]                                                 # 连接检查 / 页面报告不经 service worker
    assert o["mf"] == '{"name":"qbreak"}' and o["ic"] == "png"                # manifest / 图标连不上时用存着的
    assert "/static/core.js?v=aaaa" in o["before"] and o["after"] == ["/static/old.js"]   # 页面换了新版本：别的版本删掉
    assert o["names"] == ["qbreak-v4"]                                          # 旧的缓存名在 activate 时删掉


# ────────── ⑧ 页面的连接检查（conn.js）：连不上 → 顶上倒数重试；连上自动消失；刷新前先确认、对话框开着不刷新 ──────────
def test_conn_banner_backs_off_and_recovers_without_reload(tmp_path):
    o = run_conn(tmp_path, r"""
  NET.mode = 'down';
  DOC.hidden = true; dfire('visibilitychange'); await advance(60000);      // 看不见的时候不问
  const hiddenCalls = NET.calls;
  DOC.hidden = false; dfire('visibilitychange');
  await advance(1100);                                                     // 切回来：马上问、1 秒后再问一次才算连不上
  const b1 = banner(), c1 = NET.calls;
  await advance(3000); const c2 = NET.calls;                               // 3 秒后重试
  await advance(5000); const c3 = NET.calls;                               // 再 5 秒
  NET.mode = 'up';
  await advance(10000);
  return {hiddenCalls, b1, c1, c2, c3, b2: banner(), reloads: R.reloads, beacons: NET.beacons, rc: R.reconnect, timers: timers()};
""", gen_ago_min=1)
    assert o["hiddenCalls"] == 0 and o["c1"] == 2 and o["c2"] == 3 and o["c3"] == 4, o
    assert o["b1"].startswith("连不上 Mac（3 秒后重试）") and o["b2"] == "" and o["reloads"] == 0
    assert o["rc"] == 1 and any(b.startswith("e=reconnect") for b in o["beacons"]) and o["timers"] == 1   # 只剩一个定时器（心跳）


def test_conn_hung_status_counts_as_down_and_no_duplicate_timers(tmp_path):
    o = run_conn(tmp_path, r"""
  for (let i = 0; i < 20; i++) { dfire('visibilitychange'); wfire('focus'); wfire('pageshow', {persisted: true}); }
  await advance(120000);
  const idle = NET.calls, t1 = timers();                                   // 空闲：每 30 秒一次
  NET.mode = 'hang';
  wfire('online');
  await advance(5100);
  const b = banner();
  await advance(60000);
  return {idle, t1, b, t2: timers(), reloads: R.reloads};
""", gen_ago_min=1)
    assert 4 <= o["idle"] <= 5 and o["t1"] == 1 and o["t2"] <= 3, o              # 事件再多也只有一个定时器链（+ 倒数显示 + 正在问的超时）
    assert o["b"].startswith("连不上 Mac") and o["reloads"] == 0
    o = run_conn(tmp_path, r"""
  await advance(1000);
  for (let i = 0; i < 5; i++) { await hideFor(200); wfire('focus'); }      // 很快切走又切回（拉下控制中心 / 看一眼通知）：3 秒内只问一次……
  const c0 = NET.calls;
  await advance(120000);                                                   // ……但心跳要接着走（以前这样之后就再也不问了）
  return {c0, c1: NET.calls, t: timers()};
""", gen_ago_min=1)
    assert o["c0"] <= 2 and 4 <= o["c1"] - o["c0"] <= 5 and o["t"] == 1, o


def test_conn_offline_event_and_reload_request_while_down(tmp_path):
    o = run_conn(tmp_path, r"""
  navigator.onLine = false; NET.mode = 'down';
  wfire('offline');
  const b = banner();
  await window.qbReload('user');                                           // 写完之后 / 点「刷新」：连不上 → 不刷新（不停在白屏），提示
  const r0 = R.reloads, t0 = R.toasts.slice();
  navigator.onLine = true; NET.mode = 'up';
  DOC.dlg = {};                                                            // 等着的时候开了对话框 → 连上后也等它关掉
  wfire('online'); await advance(100);
  const r1 = R.reloads, b1 = banner();
  DOC.dlg = null; dfire('close'); await advance(100);
  return {b, r0, t0, r1, b1, r2: R.reloads};
""", gen_ago_min=1)
    assert o["b"].startswith("连不上 Mac") and "这台设备没有网络" in o["b"], o
    assert o["r0"] == 0 and any("连上之后自动刷新" in t for t in o["t0"])
    assert o["r1"] == 0 and "关掉对话框后自动刷新" in o["b1"] and o["r2"] == 1


def test_conn_reloads_on_new_version_or_finished_order_only_when_safe(tmp_path):
    o = run_conn(tmp_path, r"""
  NET.v = 'V2'; DOC.active = {tagName: 'INPUT'};                           // 面板换了新代码，但正在输入
  await advance(31000);
  const r0 = R.reloads, b0 = banner();
  DOC.active = null; dfire('focusout'); await advance(500);
  return {r0, b0, r1: R.reloads, beacons: NET.beacons};
""", gen_ago_min=1)
    assert o["r0"] == 0 and "面板更新了" in o["b0"] and o["r1"] == 1, o
    busy = run_conn(tmp_path, r"""
  await advance(9000); const r0 = R.reloads;
  NET.sig = 'S1'; NET.busy = 0;                                            // 在处理的指令做完了（sig 变了）→ 10 秒的轮询看到、刷新
  await advance(2000);
  return {r0, r1: R.reloads};
""", cfg={"book": "paper", "v": "V1", "st": {"sig": "S0", "busy": 1, "pending": 1}}, gen_ago_min=1)
    assert busy == {"r0": 0, "r1": 1}
    idle = run_conn(tmp_path, r"""
  NET.sig = 'S1';                                                          // 别的变化（没有在处理的）：不打断正在看的页面……
  await advance(31000); const r0 = R.reloads;
  await hideFor(5000); await advance(2000);                                // ……切回来时再刷新
  return {r0, r1: R.reloads};
""", gen_ago_min=1)
    assert idle == {"r0": 0, "r1": 1}


def test_conn_reloads_pending_item_change_even_when_nothing_is_busy(tmp_path):
    """2026-10-15 复核：busy 只数一会儿就会变的之后，晚上写的卖出（pending 1、busy 0）07:40 下了单、昨天的单早上对账结束（pending 1 → 0），
    页面开着也只记 dirty、要切回来才刷新 →「交易」里还会做事的（pending）前后有一个 > 0 就在 30 秒的轮询里刷新；对话框开着照样等关掉。"""
    night = run_conn(tmp_path, r"""
  NET.pending = 1; await advance(31000); const r0 = R.reloads;           // 等 07:40：每 30 秒问一次，sig 没变不刷新
  NET.sig = 'S1';                                                          // 07:40 的运行下了单（pending 还是 1）
  await advance(31000);
  return {r0, r1: R.reloads};
""", cfg={"book": "paper", "v": "V1", "st": {"sig": "S0", "busy": 0, "pending": 1}}, gen_ago_min=1)
    assert night == {"r0": 0, "r1": 1}
    done = run_conn(tmp_path, r"""
  NET.pending = 0; NET.sig = 'S1';                                         // 早上对账：昨天的单结束了（pending 1 → 0）
  DOC.dlg = {}; await advance(31000); const r0 = R.reloads, b0 = banner();
  DOC.dlg = null; dfire('close'); await advance(100);
  return {r0, b0, r1: R.reloads};
""", cfg={"book": "paper", "v": "V1", "st": {"sig": "S0", "busy": 0, "pending": 1}}, gen_ago_min=1)
    assert done["r0"] == 0 and "关掉对话框后自动刷新" in done["b0"] and done["r1"] == 1, done
    fresh = run_conn(tmp_path, r"""
  NET.pending = 2; NET.sig = 'S1';                                         // 07:40 规则排了新单（pending 0 → 2）
  await advance(31000);
  return {r: R.reloads};
""", gen_ago_min=1)
    assert fresh == {"r": 1}


def test_conn_cached_page_reloads_once_connected_with_loop_guard(tmp_path):
    o = run_conn(tmp_path, r"""
  await advance(100);
  return {r: R.reloads, stale: DOC.els.stale.hidden, text: DOC.els.stale.textContent, beacons: NET.beacons};
""", gen_ago_min=30, cached=True)
    assert o["r"] == 1 and o["stale"] is False and "30 分钟前的页面" in o["text"] and "连上之后会自动刷新" in o["text"], o
    assert any(b.startswith("e=cached-page") for b in o["beacons"])
    o = run_conn(tmp_path, r"""
  await advance(100);
  return {r: R.reloads, b: banner(), beacons: NET.beacons};
""", gen_ago_min=30, cached=True, setup="H_SS['qb-autoreload'] = JSON.stringify([H_NOW - 1000, H_NOW - 2000, H_NOW - 3000]);")
    assert o["r"] == 0 and "自动刷新太频繁" in o["b"] and any(b.startswith("e=reload-loop") for b in o["beacons"]), o
    o = run_conn(tmp_path, r"""
  await advance(100);
  const r0 = R.reloads, b0 = banner();
  NET.mode = 'up'; await advance(3500);
  return {r0, b0, r1: R.reloads};
""", gen_ago_min=30, cached=True, setup="NET.mode = 'down';")
    assert o["r0"] == 0 and o["b0"].startswith("连不上 Mac") and o["r1"] == 1, o
    o = run_conn(tmp_path, "NET.mode = '401'; await hideFor(1000); await advance(100); return {r: R.reloads};", gen_ago_min=1)
    assert o == {"r": 1}                                                       # 设备没被认出来：重新载入（到登录 / 配对页）
    o = run_conn(tmp_path, r"""
  NET.page = '502';                                                        // /api/status 通、页面本身 5xx（面板刚启动 / 页面生成出错）
  await advance(1500);
  const r0 = R.reloads, b0 = banner(), p0 = NET.pages;
  await advance(60000);                                                    // 1 分钟：不来回刷新，按 3 / 5 / 10 / 20 秒再确认
  const r1 = R.reloads, p1 = NET.pages;
  NET.page = null; await advance(30000);
  return {r0, b0, p0, r1, p1, r2: R.reloads, b2: banner()};
""", gen_ago_min=30, cached=True)
    assert o["r0"] == 0 and "连得上 Mac，但页面还打不开（HTTP 502" in o["b0"] and o["p0"] == 2, o   # GET 的 502 隔 1 秒再试一次
    assert o["r1"] == 0 and 6 <= o["p1"] <= 14 and o["r2"] == 1, o


def test_old_page_reload_on_resume_matches_the_old_behavior(tmp_path):
    """以前 app.js 的「切回来时页面超过约 10 分钟 → 重新载入；对话框开着 → 不丢输入」现在在 conn.js（先确认连得上）。"""
    out = {}
    for name, ago, dlg, stay_hidden in (("nogen", None, False, False), ("fresh", 5, False, False), ("hidden", 11, False, True),
                                        ("stale", 11, False, False), ("dialog", 30, True, False)):
        out[name] = run_conn(tmp_path, ("DOC.dlg = {};" if dlg else "") + r"""
  DOC.hidden = true; dfire('visibilitychange'); await advance(1000);
  """ + ("" if stay_hidden else "DOC.hidden = false; dfire('visibilitychange'); await advance(100);") + r"""
  return {r: R.reloads, b: banner(), calls: NET.calls};
""", gen_ago_min=ago)
    assert [out[k]["r"] for k in ("nogen", "fresh", "hidden", "stale", "dialog")] == [0, 0, 0, 1, 0], out
    assert out["hidden"]["calls"] == 0 and "关掉对话框后自动刷新" in out["dialog"]["b"]
    assert out["dialog"]["b"].startswith("页面放久了：")                      # 2026-10-15 复核：以前写成「状态更新了：」


def test_conn_banner_says_panel_error_on_http_500(tmp_path):
    """/api/status 回 500 = Mac 上的面板自己出错（不是 Mac 睡着 / 网络）：写「Mac 上的面板出错了」+ 去 Mac 的对话里说（2026-10-15 复核）；
    502（Tailscale Serve 接不上面板）照旧「连不上 Mac」。"""
    o = run_conn(tmp_path, "NET.mode = '500'; await hideFor(1000); await advance(100); return {b: banner(), r: R.reloads};")
    assert o["b"].startswith("Mac 上的面板出错了（HTTP 500，") and "在 Mac 的 Claude 对话里说一声" in o["b"] and o["r"] == 0, o
    o = run_conn(tmp_path, "NET.mode = '502'; await hideFor(1000); await advance(1500); return {b: banner()};")   # GET 的 502 隔 1 秒再试一次
    assert o["b"].startswith("连不上 Mac（") and "面板出错" not in o["b"], o


def test_conn_banner_goes_into_an_open_dialog(tmp_path):
    """对话框开着：连接条放进对话框最上面（以前固定在页面顶上、被对话框的遮罩盖住，点不到「重试」）；关掉 → 回到页头 / 页面。"""
    o = run_conn(tmp_path, r"""
  const dlg = Object.assign(H_el('dialog'), {kids: [], firstChild: null,
    insertBefore(c){ this.kids.unshift(c); c.parentNode = this; return c; }, contains(c){ return this.kids.indexOf(c) >= 0; }});
  DOC.dlg = dlg;
  NET.mode = 'down'; await hideFor(1000); await advance(1500);              // 切回来：1 秒后再问一次才算连不上
  const inDlg = dlg.kids.length === 1 && dlg.kids[0] === DOC.els.conn, b0 = banner();
  return {inDlg, b0};
""")
    assert o["inDlg"] and o["b0"].startswith("连不上 Mac"), o
    css = panel._CSS
    assert "dialog>.conn{position:sticky;top:0" in css and ".top>.conn{position:static" in css


def test_conn_auth_reload_waits_for_the_dialog_and_happens_once(tmp_path):
    """这台设备没被认出来（401）：对话框开着 / 正在输入 → 等关掉再刷新（以前 /api/status 的 401 不等、K 线的 401 各自 1.5 秒后刷新 →
    输入的口数丢了）；kline.js 经 window.qbAuth 走同一条路，几张图一起 401 也只刷新一次。"""
    o = run_conn(tmp_path, r"""
  DOC.dlg = {};
  NET.mode = '401'; await hideFor(1000); await advance(100);
  const r0 = R.reloads, b0 = banner();
  DOC.dlg = null; dfire('close', {type: 'close', target: {}}); await advance(200);
  return {r0, b0, r1: R.reloads};
""")
    assert o["r0"] == 0 and o["b0"] == "这台设备要重新登录：关掉对话框后自动刷新" and o["r1"] == 1, o
    o = run_conn(tmp_path, r"""
  DOC.dlg = {};
  window.qbAuth(); window.qbAuth(); window.qbAuth(); await advance(100);
  const r0 = R.reloads, b0 = banner();
  DOC.dlg = null; dfire('close', {type: 'close', target: {}}); await advance(5000);
  return {r0, b0, r1: R.reloads, fn: typeof window.qbAuth};
""")
    assert o["fn"] == "function" and o["r0"] == 0 and "这台设备要重新登录" in o["b0"] and o["r1"] == 1, o


# ────────── ⑨ 写操作：busy 一定放开；标签栏 / 刷新 / HALT 不锁 ──────────
def test_write_busy_is_released_and_never_locks_navigation():
    J = panel.js_plain("core")
    api = J[J.index("async function api(path, body){"):J.index("async function post1(")]
    assert "try{ return await post1(path, body); }finally{ busy(false); }" in api
    assert "busy(false)" not in J[J.index("async function post1("):J.index("function done(j){")]
    assert ".tabbar button, [data-act=reload], [data-act=halt], #conn button" in J and "BUSYN" in J
    assert "setTimeout(reloadNow, 2200)" in J and "window.qbReload('user')" in J
    assert "document.querySelector('dialog[open]'), host=d || document.body" in J            # 对话框开着：提示放进对话框（不被盖住）
    css = panel._CSS
    assert ".toast{bottom:calc(env(safe-area-inset-bottom) + 72px)}" in css and ".conn{position:fixed" in css


def test_boot_script_recovers_when_modules_do_not_load():
    b = panel.STATIC["boot.js"].decode("utf-8")
    assert "window.__qbReady" in b and "t.tagName === 'SCRIPT'" in b and "/api/status?book=" in b and "location.reload()" in b
    assert "qb-bootreload" in b and "lim = (why === 'fixed' || why === 'ver') ? 4 : 2" in b and "15000" in b and "\nimport " not in b and "export " not in b   # 普通脚本、1 分钟最多自动 2 次
    # 2026-10-15 复核：版本对不上（带版本的 404）以前当成「拿不到」只在页面底上倒数、一直不重新载入 → 现在 'ver' 直接重新载入（告诉 SW 多等网络）
    assert "throw new Error('VER')" in b and "m === 'VER' ? 'ver'" in b and "if(!why || why === 'ver') return reload(" in b
    assert "patient(function(){ location.reload(); })" in b and "{qb: 'patient'}" in b
    assert "link[rel=stylesheet][href^='/static/']" in b and "fail('css'" in b and "if(kind === 'css') return;" in b   # 样式没载入成也接手
    assert "link[rel=modulepreload]" in b and "modulepreload|stylesheet" in b                 # 哪个模块没载入成：逐个确认拿得到了再重新载入
    m = panel.STATIC["main.js"].decode("utf-8")
    assert m.index("import './app.js") < m.index("window.__qbReady = 1") < m.index("__qbBootOk")


BOOT_HARNESS = r"""
const calls = {reload: 0, beacons: []}, listeners = {}, els = {};
globalThis.window = globalThis;
window.addEventListener = (t, f) => { listeners[t] = f; };
globalThis.sessionStorage = {s: {}, getItem(k){ return this.s[k] || null; }, setItem(k, v){ this.s[k] = v; }};
Object.defineProperty(globalThis, 'location', {value: {reload(){ calls.reload++; }}});
Object.defineProperty(globalThis, 'navigator', {value: {}});
const NODES = __NODES__;
function mk(t){
  const e = {tagName: t, style: {}, kids: [], appendChild(c){ this.kids.push(c); this.firstChild = this.kids[0]; this.lastChild = c; },
             setAttribute(){}, addEventListener(){}};
  Object.defineProperty(e, 'id', {set(v){ els[v] = e; }});
  return e;
}
globalThis.document = {
  getElementById(id){ return id === 'qb-cfg' ? {textContent: '{"book":"paper"}'} : (els[id] || null); },
  querySelectorAll(sel){ return sel.startsWith('link[rel=stylesheet]') ? NODES.filter(n => n.rel === 'stylesheet') : NODES; },
  createElement: mk, body: {appendChild(){}}, documentElement: {appendChild(){}},
};
const MODE = __MODE__;
globalThis.fetch = async (u) => {
  if(String(u).startsWith('/api/clientlog')){ calls.beacons.push(String(u)); return {ok: true, status: 204}; }
  if(MODE === 'net') throw new TypeError('Load failed');
  if(MODE === 'ver' && /\?v=old/.test(u)) return {ok: false, status: 404};
  return {ok: true, status: 200};
};
__BOOT__
if(MODE === 'css'){ window.__qbReady = 1; window.__qbBootOk(); }        // 脚本照样跑起来了：样式没载入成也要重新载入
else listeners.error({target: {tagName: 'SCRIPT', src: '/static/main.js?v=old'}});
setTimeout(() => {
  const bar = els.bootbar;
  console.log(JSON.stringify({reload: calls.reload, bar: bar ? bar.firstChild.textContent : '', beacons: calls.beacons.length}));
  process.exit(0);
}, 300);
"""


@pytest.mark.parametrize("mode", ["ver", "css", "net"])
def test_boot_script_reloads_on_version_mismatch_and_on_missing_styles_in_node(tmp_path, mode):
    """boot.js 在 node 里实际跑（假的最小 DOM）：带版本的脚本 404（页面是旧版本）→ 直接重新载入（以前当成「拿不到」只倒数、一直不重新载入）；
    样式没载入成（sheet 是 null）→ 脚本跑起来了也重新载入；连不上 Mac → 不来回刷新，页面底上倒数重试。"""
    from panel_js_harness import _run
    nodes = [{"tagName": "SCRIPT", "type": "module", "src": "/static/main.js?v=old"},
             {"tagName": "LINK", "rel": "stylesheet", "href": "/static/panel.css?v=old", "sheet": None if mode == "css" else {}}]
    src = (BOOT_HARNESS.replace("__NODES__", json.dumps(nodes)).replace("__MODE__", json.dumps(mode))
           .replace("__BOOT__", panel.BOOT_JS))
    r = _run(tmp_path, f"boot_{mode}.mjs", src)
    if mode == "net":
        assert r["reload"] == 0 and "连不上 Mac" in r["bar"]
    else:
        assert r["reload"] == 1, r
    assert r["beacons"] >= 1


# ────────── ⑩ mac_setup 重跑：plist 没变、面板在跑 → 不重启面板 ──────────
@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_panel_installer_does_not_restart_an_unchanged_panel(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    log = tmp_path / "lc.log"
    (b / "launchctl").write_text('#!/bin/sh\necho "launchctl $*" >> "$LCLOG"\n'
                                 'case "$1" in list) [ -f "$LOADED" ] && exit 0; exit 113 ;; load) : > "$LOADED" ;; esac\nexit 0\n',
                                 encoding="utf-8")
    (b / "launchctl").chmod(0o755)
    env = {**os.environ, "PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "LCLOG": str(log), "LOADED": str(tmp_path / "loaded"),
           "QBREAK_SKIP_VENV": "1", "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents"), "QBREAK_LIVEU_HOME": str(tmp_path / "lh"),
           "QBREAK_PYTHON": sys.executable}

    def run(**extra):
        if log.exists():
            log.unlink()
        r = subprocess.run(["bash", "scripts/install_launchd_panel.sh"], cwd=ROOT, env={**env, **extra}, capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stderr
        return r.stdout, log.read_text(encoding="utf-8") if log.exists() else ""
    out, c = run()
    plist = (tmp_path / "agents" / "com.qbreak.panel.plist").read_text(encoding="utf-8")
    assert "launchctl load -w" in c and "<key>ThrottleInterval</key><integer>10</integer>" in plist
    out, c = run()
    assert "load -w" not in c and "unload" not in c and "不重启" in out             # 没变 → 不动正在跑的面板
    out, c = run(QBREAK_PANEL_PORT="8799")
    assert "unload -w" in c and "load -w" in c                                   # 变了 → 照旧重新注册
    assert not list((tmp_path / "agents").glob("*.new.*"))
