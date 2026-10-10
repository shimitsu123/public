"""立花实盘缺口 B 组「SCHED」（2026-10-09「做〔77〕B」；只改工程）：
① B5 前一晚预检（qbreak/precheck.py）：交付書面的更新预告、API 新版本的提醒（发布日之后也持续，直到代码更新）、上线门槛新出现的 ★、
   只在立花本番、什么时候做、登出；② B6 代码版本 / Python 版本记进运行状态、requirements.lock、冒烟测试挡住不下单（--block-reason）；
③ B14 执行器 / probe 结束时登出、两台 Mac（账本的机器标识）；④ C-13 临时休市（数据目录的 extra_closed.json）。
只用假 broker / FakeTransport / 临时数据目录；不联网、不调真的 launchctl / security / osascript。"""
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from qbreak import calendar_jp as CJ
from qbreak import notify_seen, paths
from qbreak import precheck as PC
from qbreak import run_status as RS
from qbreak import versions as V
from qbreak.calendar_jp import JST

from test_tachibana import LOGIN_OK, SPEC, _broker

ROOT = Path(__file__).resolve().parent.parent
THU_EVE = dt.datetime(2026, 10, 8, 20, 0, tzinfo=JST)        # 周四 20:00 → 检查周五（交易日）
FRI_EVE = dt.datetime(2026, 10, 9, 20, 0, tzinfo=JST)        # 周五 20:00 → 周六休市
API = "e_api_v4r10"


# ────────── ② B6：代码 / 依赖的版本 ──────────
def test_code_and_python_versions_go_into_the_run_status():
    rec = RS.build({}, phase="morning", ok=True, rc=0)
    assert rec["code"] == V.code_version() and (rec["code"] == "?" or all(c in "0123456789abcdef" for c in rec["code"]))
    assert set(rec["py"]) == {"python", "pandas", "numpy", "yfinance"} and rec["py"]["pandas"] not in ("", None)
    assert V.code_version(root="/nonexistent-dir-for-test") == "?"                  # 不是 git 仓库 → "?"
    assert V.brief().startswith("代码 ") and "pandas " in V.brief()


def test_code_tree_ignores_data_only_commits(tmp_path):
    """只看代码的标识：var/ 的提交（云端例行任务每天推）不改变它；qbreak/ 改了才变。运行状态文件里也有。"""
    import subprocess
    repo = tmp_path / "r"
    (repo / "qbreak").mkdir(parents=True)
    (repo / "var").mkdir()

    def git(*a):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", *a], check=True, capture_output=True)
    git("init", "-q")
    (repo / "qbreak" / "x.py").write_text("a = 1\n", encoding="utf-8")
    (repo / "var" / "d.json").write_text("{}", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "c1")
    V.code_tree.cache_clear()
    t1 = V.code_tree(str(repo))
    (repo / "var" / "d.json").write_text('{"day": 2}', encoding="utf-8")
    git("commit", "-qam", "var")
    V.code_tree.cache_clear()
    assert V.code_tree(str(repo)) == t1 and len(t1) == 12                       # 只有 var/ 变：同一个标识
    (repo / "qbreak" / "x.py").write_text("a = 2\n", encoding="utf-8")
    git("commit", "-qam", "code")
    V.code_tree.cache_clear()
    assert V.code_tree(str(repo)) not in (t1, "?")
    assert V.code_tree(str(tmp_path / "nope")) == "?"
    assert "code_tree" in RS.build({}, phase="morning", ok=True, rc=0)


def test_requirements_lock_pins_the_tested_versions():
    lock = V.read_lock()
    for p in ("pandas", "numpy", "yfinance", "requests", "cryptography", "pytest"):
        assert p in lock and lock[p][1][0].isdigit(), p                            # 确切的版本（==）
    assert "==" in (ROOT / "requirements.lock").read_text(encoding="utf-8")
    assert V.lock_diff(version_of=lambda n: "0.0") and "colorama" not in {n for n, _, _ in V.lock_diff(version_of=lambda n: "0.0")}


def _vt(v: str) -> tuple:
    return tuple(int(x) for x in __import__("re").findall(r"\d+", v)[:3])


# 安全相关的包：锁的版本不能低于这些（已知漏洞修好的版本；Mac 上 install_deps.sh 照锁装 → 低了就是把 Mac 降级到有漏洞的版本）。
# cryptography：CVE-2023-50782 / CVE-2024-26130 / 内置 OpenSSL（CVE-2024-12797 → 44.0.1）；requests：CVE-2024-47081（2.32.4）；
# urllib3：CVE-2025-50181 / 50182（2.5.0）；certifi：去掉被吊销的根证书（2024.7.4）。立花的私钥解密、登录都经过它们。
SEC_FLOOR = {"cryptography": "44.0.1", "requests": "2.32.4", "urllib3": "2.5.0", "certifi": "2024.7.4"}


def test_requirements_lock_is_not_older_than_the_security_floor_or_the_test_env():
    """锁要在干净的虚拟环境里生成（不含系统 site-packages：Ubuntu 的 cryptography 41.0.7 带发行版补丁，PyPI 的同版本没有）。
    安全相关的包：不低于已知漏洞修好的版本，也不低于跑测试的这个环境里装的版本。"""
    lock = V.read_lock()
    for name, floor in SEC_FLOOR.items():
        assert name in lock, name
        assert _vt(lock[name][1]) >= _vt(floor), (name, lock[name][1], floor)
        have = V._ver(name)
        if have not in ("没装", "?"):
            assert _vt(lock[name][1]) >= _vt(have), (name, "锁", lock[name][1], "测试环境", have)
    head = (ROOT / "requirements.lock").read_text(encoding="utf-8").split("\n# ── 依赖")[0]
    assert "干净的虚拟环境" in head and "dist-packages" in head


def test_lock_check_only_reminds_and_skips_other_platforms(tmp_path):
    f = tmp_path / "requirements.lock"
    f.write_text("# c\npandas==3.0.6\nnumpy==2.4.6  # x\ncolorama==0.4.6 ; sys_platform == \"win32\"\n", encoding="utf-8")
    have = {"pandas": "3.0.6", "numpy": "2.4.6"}
    lines, ok = V.lock_check_lines(f, version_of=lambda n: have.get(n, "没装"))
    assert ok and lines[0].startswith("[OK]")                                    # colorama 只在 Windows：不比较
    have["pandas"] = "2.2.3"
    lines, ok = V.lock_check_lines(f, version_of=lambda n: have.get(n, "没装"))
    assert not ok and lines[0].startswith("[提醒]") and "pandas 2.2.3（锁 3.0.6）" in lines[0] and "★" not in lines[0]
    lines, ok = V.lock_check_lines(tmp_path / "none.lock")
    assert not ok and "没有 none.lock" in lines[0]


def _paper_now():
    from test_manual_now import PX, _at, _morning, _paper, _quote, _req
    r = _paper("sb")
    _morning(r, until=14)
    rec = _req(r, kind="trim", ticker="A.T", pct=12.0)
    r.now["t"] = _at(r, 10, 0)
    return r, rec, _quote(PX)


def test_block_reason_also_holds_intraday_manual_orders():
    """冒烟测试没过（run.py --block-reason）：盘中的手动指令也不下，留着一会儿再试。"""
    r, rec, q = _paper_now()
    r.ux.block("新代码的冒烟测试没过（abc1234）：今天不下单")
    res = r.ux.now_phase(q)
    it = r.ux.book["manual"]["items"][rec["id"]]
    assert res["retry"] == 1 and res["placed"] == 0 and "冒烟测试没过" in it["msg"] and it["status"] == "pending"


# ────────── ③ B14：登出、两台 Mac ──────────
def test_executor_body_logs_out_even_when_the_run_fails(monkeypatch):
    import run
    seen = []

    class B:
        def logout(self):
            seen.append("logout")
            raise RuntimeError("登出失败也不影响")

    def body(a, opened):
        opened.append(B())
        raise ValueError("中途出错")
    monkeypatch.setattr(run, "_live_unified_run", body)
    with pytest.raises(ValueError):
        run._live_unified_body(SimpleNamespace())
    assert seen == ["logout"]
    monkeypatch.setattr(run, "_live_unified_run", lambda a, opened: (opened.append(B()), 0)[1])
    assert run._live_unified_body(SimpleNamespace()) == 0 and seen == ["logout", "logout"]


def test_probe_logs_out_at_the_end(monkeypatch):
    import run
    b, tr = _broker(responses={SPEC.clm_login: {**LOGIN_OK, "sUpdateInformWebDocument": "20261020",
                                                "sUpdateInformAPISpecFunction": "20261128"}})
    monkeypatch.setattr("qbreak.brokers.tachibana.TachibanaBroker", lambda **kw: b)
    monkeypatch.setattr(run, "_tachibana_tradable_check", lambda b_: "都能买、一手一致")
    run.main(["tachibana-probe"])
    clms = [p.get("sCLMID") for _, p in tr.sent]
    assert clms[-1] == SPEC.clm_logout and b.doc_update == "20261020" and b.next_release == "20261128"
    rec = json.loads((paths.out_dir() / "tachibana_probe_live.json").read_text(encoding="utf-8"))
    assert rec["doc_update"] == "20261020"


@pytest.mark.parametrize("logout_res", [{"p_errno": "2", "p_err": "session cut"}, {"p_errno": "9", "p_err": "x"}])
def test_logout_after_a_session_cut_does_not_log_in_again(logout_res):
    """会话已经被切断（多半是别处登录了同一个账户）时登出：只发一次登出，不重新登录（不把那边的会话踢掉、不多一封登录通知邮件）。"""
    b, tr = _broker(responses={SPEC.clm_logout: logout_res})
    b.login()
    b.logout()
    clms = [p.get("sCLMID") for _, p in tr.sent]
    assert clms == [SPEC.clm_login, SPEC.clm_logout] and b._logged_in is False
    b.logout()                                                                # 已登出：什么都不发
    assert [p.get("sCLMID") for _, p in tr.sent] == clms


def test_host_is_recorded_once_and_another_mac_is_refused():
    from qbreak.live_unified import adopt_host, check_host
    book: dict = {}
    assert check_host(book, "aaaa1111") is None and book["host"] == "aaaa1111"   # 第一次：记下这台
    assert check_host(book, "aaaa1111") is None
    why = check_host(book, "bbbb2222")
    assert why and "另一台 Mac" in why and "adopt-host" in why and book["host"] == "aaaa1111"
    assert check_host(book, "?") is None                                       # 读不出这台的标识 → 不判定（不误挡）
    p = paths.state_dir() / "live_unified_tachibana.json"
    p.write_text(json.dumps(book), encoding="utf-8")
    r = adopt_host(p, "bbbb2222")
    assert r == {"old": "aaaa1111", "new": "bbbb2222", "changed": True}
    nb = json.loads(p.read_text(encoding="utf-8"))
    assert nb["host"] == "bbbb2222" and "换 Mac" in nb["events"][-1]["msg"]
    assert adopt_host(p, "bbbb2222")["changed"] is False
    from qbreak import book_backup
    assert book_backup.list_backups(p)                                         # 改之前备份了


def test_host_id_is_a_short_digest_not_the_name(monkeypatch):
    from qbreak.live_unified import host_id

    def ioreg(args, **kw):
        return SimpleNamespace(returncode=0, stdout='  "IOPlatformUUID" = "11111111-2222-3333-4444-555555555555"\n')
    h = host_id(run=ioreg)
    assert len(h) == 8 and "1111" not in h and h == host_id(run=ioreg)
    assert host_id(run=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("ioreg")),
                   platform="linux") not in ("", None)


def test_host_id_does_not_depend_on_path_and_never_uses_the_hostname_on_macos(tmp_path, monkeypatch):
    """定时任务（launchd）的 PATH 不带 /usr/sbin、终端里的带：同一台 Mac 必须得出同一个标识（用 ioreg 的绝对路径）；
    macOS 上 ioreg 读不出 → "?"（不判定），不退回会随网络变的主机名。"""
    import hashlib

    from qbreak.live_unified import host_id
    uuid = "11111111-2222-3333-4444-555555555555"
    fake = tmp_path / "sbin" / "ioreg"
    fake.parent.mkdir()
    fake.write_text(f"#!/bin/sh\necho '  \"IOPlatformUUID\" = \"{uuid}\"'\n", encoding="utf-8")
    fake.chmod(0o755)
    empty = tmp_path / "bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))                                   # PATH 里没有 ioreg
    monkeypatch.setattr("socket.gethostname", lambda: "should-not-be-used")
    want = hashlib.sha1(f"uuid:{uuid}".encode("utf-8")).hexdigest()[:8]
    assert host_id(ioreg=str(fake), platform="darwin") == want
    assert host_id(ioreg=str(tmp_path / "nope" / "ioreg"), platform="darwin",
                   machine_id=str(tmp_path / "no-machine-id")) == "?"
    host = hashlib.sha1(b"host:should-not-be-used").hexdigest()[:8]
    assert host_id(ioreg=str(tmp_path / "nope" / "ioreg"), platform="darwin") != host
    # 其他系统照旧：machine-id → 主机名
    assert host_id(ioreg=str(tmp_path / "nope" / "ioreg"), platform="linux",
                   machine_id=str(tmp_path / "no-machine-id")) == host


def test_live_and_panel_agents_see_usr_sbin():
    """执行器 / 面板的 LaunchAgent 的 PATH 带 /usr/sbin（和终端一样），别的入口不会得出不同的环境。"""
    for name in ("install_launchd_live_u.sh", "install_launchd_panel.sh"):
        s = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "/usr/bin:/bin:/usr/sbin:/sbin</string>" in s, name


def test_cli_adopt_host(monkeypatch, capsys):
    import run
    monkeypatch.setattr("qbreak.live_unified.host_id", lambda run=None: "cccc3333")
    assert run.main(["live-u", "--broker", "tachibana", "--adopt-host"]) == 0
    assert "还没有立花本番的账本" in capsys.readouterr().out
    p = paths.state_dir() / "live_unified_tachibana.json"
    p.write_text(json.dumps({"host": "aaaa1111", "state": None}), encoding="utf-8")
    assert run.main(["live-u", "--broker", "tachibana", "--adopt-host"]) == 0
    assert "aaaa1111 → cccc3333" in capsys.readouterr().out
    assert json.loads(p.read_text(encoding="utf-8"))["host"] == "cccc3333"
    assert run.main(["live-u", "--broker", "tachibana", "--demo", "--adopt-host"]) == 2


def test_executor_on_another_mac_stops_without_touching_the_broker(monkeypatch, capsys):
    """账本是另一台 Mac 的：执行器停下（退出码 3、运行状态写明），不登录立花（不把另一台的会话踢掉），结束时照样登出（没登录 = 什么都不做）。"""
    import run
    from test_live_unified import _scenario
    make, _ = _scenario([1000.0] * 30)
    eng = make()
    calls = []

    class FakeB:
        next_release = doc_update = ""

        def __init__(self, **kw):
            calls.append("new")

        def login(self):
            calls.append("login")

        def cash(self):
            calls.append("cash")
            return 1e6

        def logout(self):
            calls.append("logout")
    p = paths.state_dir() / "live_unified_tachibana.json"
    p.write_text(json.dumps({"host": "aaaa1111"}), encoding="utf-8")
    monkeypatch.setattr("qbreak.live_unified.host_id", lambda run=None: "bbbb2222")
    monkeypatch.setattr("qbreak.brokers.tachibana.TachibanaBroker", FakeB)
    monkeypatch.setattr(run, "_sim_cfg", lambda: {"mode": "unified", "start": "2020-01-05"})
    monkeypatch.setattr(run, "_unified_cfg", lambda cfg: SimpleNamespace(stock_markets=("JP",), capital_jpy=1_000_000))
    monkeypatch.setattr(run, "_netcheck", lambda: [])
    monkeypatch.setattr(run, "_unified_engine", lambda a, cfg, state, provider: (
        eng, SimpleNamespace(ex=eng.ex, gate=SimpleNamespace(pre_send=None))))
    assert run.main(["live-u", "--broker", "tachibana", "--no-clock"]) == 3
    out = capsys.readouterr().out
    assert "另一台 Mac" in out and "代码 " in out                                # 日志里有这次用的代码版本
    assert calls == ["new", "logout"]                                         # 没登录、没取余力；结束时登出
    st = RS.read("tachibana")
    assert st["ok"] is False and "另一台 Mac" in st["error"] and st["code"] and "py" in st
    assert json.loads(p.read_text(encoding="utf-8"))["host"] == "aaaa1111"   # 账本没改


# ────────── ④ C-13 临时休市 ──────────
@pytest.fixture
def fresh_calendar():
    CJ.reload_extra_closed()
    yield
    CJ.reload_extra_closed()


def test_extra_closed_day_is_not_a_trading_day(fresh_calendar, monkeypatch):
    day = dt.date(2026, 10, 14)                                               # 周三
    assert CJ.is_trading_day(day)
    (paths.home() / "extra_closed.json").write_text(json.dumps({"dates": [day.isoformat()], "note": "东证全日停止"}),
                                                     encoding="utf-8")
    CJ.reload_extra_closed()
    assert not CJ.is_trading_day(day) and CJ.next_trading_day(dt.date(2026, 10, 13)) == dt.date(2026, 10, 15)
    assert CJ.prev_trading_day(dt.date(2026, 10, 15)) == dt.date(2026, 10, 13)
    (paths.home() / "extra_closed.json").write_text("{坏的", encoding="utf-8")
    CJ.reload_extra_closed()
    assert CJ.is_trading_day(day)                                             # 写坏的文件：当作没有（不弄乱所有交易日）
    monkeypatch.delenv("QBREAK_HOME")
    CJ.reload_extra_closed()
    assert CJ.is_trading_day(day)                                             # 没设数据目录（云端）：不读


def test_extra_closed_cli(fresh_calendar, capsys):
    import run
    assert run.main(["extra-closed", "list"]) == 0 and "没有登记临时休市" in capsys.readouterr().out
    assert run.main(["extra-closed", "add", "2026-10-14", "--note", "东证全日停止"]) == 0
    assert not CJ.is_trading_day(dt.date(2026, 10, 14))                        # 写完马上生效
    assert run.main(["extra-closed", "add", "2026-10-17"]) == 0 and "周末" in capsys.readouterr().out
    run.main(["extra-closed", "list"])
    assert "2026-10-14 临时休市：东证全日停止" in capsys.readouterr().out
    assert run.main(["extra-closed", "rm", "2026-10-14"]) == 0 and CJ.is_trading_day(dt.date(2026, 10, 14))
    assert run.main(["extra-closed", "add", "bad"]) == 2


# ────────── ① B5 前一晚预检 ──────────
def test_target_day_and_when_not_to_login():
    assert PC.target_day(THU_EVE) == (dt.date(2026, 10, 9), "")
    d, why = PC.target_day(FRI_EVE)
    assert d is None and "休市" in why                                        # 周六休市：不登录（登录通知邮件一天一封）
    assert PC.target_day(dt.datetime(2026, 10, 11, 20, 0, tzinfo=JST))[0] is None    # 周日晚 → 周一 10/12 体育の日休市
    assert PC.target_day(dt.datetime(2026, 10, 12, 20, 0, tzinfo=JST))[0] == dt.date(2026, 10, 13)
    assert PC.target_day(dt.datetime(2026, 10, 9, 4, 0, tzinfo=JST))[0] is None     # 闭局
    assert PC.target_day(dt.datetime(2026, 10, 9, 6, 0, tzinfo=JST))[0] == dt.date(2026, 10, 9)
    assert PC.target_day(dt.datetime(2026, 10, 9, 10, 0, tzinfo=JST))[0] is None    # 交易日白天：执行器自己会登录


def test_api_version_reminder_persists_after_the_release_until_the_code_moves():
    n = PC.record({}, next_release="20261128", api=API, today=dt.date(2026, 10, 8))
    before = PC.reminders(n, API, dt.date(2026, 11, 1))
    assert len(before) == 1 and "2026-11-28" in before[0] and not before[0].startswith("★")
    n = PC.record(n, next_release="", api=API, today=dt.date(2026, 12, 1))     # 发布日之后应答里没有了：记录不清掉
    after = PC.reminders(n, API, dt.date(2026, 12, 1))
    assert len(after) == 1 and after[0].startswith("★") and "已于 2026-11-28 发布" in after[0]
    assert PC.reminders(n, "e_api_v4r11", dt.date(2026, 12, 1)) == []        # 代码更新到新版本 → 消掉
    assert n["next_release"]["first_seen"] == "2026-10-08"


def test_api_release_of_the_current_version_or_first_seen_late_is_not_a_star():
    """应答里显示的就是代码已经在用的这一版（v4r10 = 2026-08-29）→ 不提醒；第一次看到时已经过了的日子 → 只是提醒、不升 ★
    （否则 ★ 永远消不掉：执行器每天的通知都变 warn、面板顶部一直 ★）。"""
    from qbreak.brokers.tachibana import API_RELEASES, TachibanaSpec, api_version
    assert api_version(TachibanaSpec().base_live) in API_RELEASES               # 改版本段时发布日一起加
    assert api_version(TachibanaSpec().base_demo) in API_RELEASES
    n = PC.record(None, next_release="20260829", api=API, today=dt.date(2026, 10, 9))
    assert PC.reminders(n, API, dt.date(2026, 10, 9)) == []
    assert PC.reminders(n, API, dt.date(2027, 3, 1)) == []
    n = PC.record(None, next_release="20261001", api=API, today=dt.date(2026, 10, 9))   # 不改版本段的仕様变更（看到时已过）
    r = PC.reminders(n, API, dt.date(2026, 10, 9))
    assert len(r) == 1 and not r[0].startswith("★") and "--ack-api 2026-10-01" in r[0]
    assert not PC.panel_lines({"at": FRI_EVE.isoformat(), "ok": True, "notices": r}, FRI_EVE)


def test_api_release_reminder_can_be_acknowledged(tmp_path):
    """用户确认「核对过、不用更新」→ run.py live-precheck --ack-api：这个日子不再提醒（并进账本后也不提醒）；新的日子照常提醒。"""
    import run
    n = PC.record(None, next_release="20261128", api=API, today=dt.date(2026, 10, 8))
    PC.result_path().parent.mkdir(parents=True, exist_ok=True)
    PC.result_path().write_text(json.dumps({"at": THU_EVE.isoformat(), "ok": True, PC.KEY: n,
                                            "notices": PC.reminders(n, API, dt.date(2026, 12, 1))}), encoding="utf-8")
    assert run.main(["live-precheck", "--ack-api", "2026-11-29"]) == 2          # 日子不对：不改
    assert run.main(["live-precheck", "--ack-api", "2026-11-28"]) == 0
    rec = json.loads(PC.result_path().read_text(encoding="utf-8"))
    assert rec[PC.KEY]["next_release"]["acked"] == "2026-11-28" and rec["notices"] == []
    book_n = PC.record({"next_release": {**n["next_release"]}}, next_release="20261128", api=API,
                       today=dt.date(2026, 12, 2))                                # 执行器：账本里的记录（没有 acked、更新）
    merged = PC.merge(book_n, rec[PC.KEY])
    assert merged["next_release"]["acked"] == "2026-11-28"                        # 合并后确认留着
    assert PC.reminders(merged, API, dt.date(2026, 12, 2)) == []
    again = PC.record(merged, next_release="20270301", api=API, today=dt.date(2026, 12, 3))   # 新的发布日 → 照常提醒
    assert "acked" not in again["next_release"] and PC.reminders(again, API, dt.date(2026, 12, 3))


def test_doc_update_reminder_within_five_trading_days():
    n = PC.record({}, doc_update="2026/10/20", api=API, today=dt.date(2026, 10, 9))
    assert n["doc_update"]["value"] == "2026-10-20"
    assert PC.reminders(n, API, dt.date(2026, 10, 9)) == []                   # 10/13〜10/20 = 6 个交易日：还早
    r = PC.reminders(n, API, dt.date(2026, 10, 13))
    assert len(r) == 1 and r[0].startswith("★") and "交付書面 2026-10-20" in r[0]
    assert PC.reminders(n, API, dt.date(2026, 10, 20))                       # 当天也提醒
    assert PC.reminders(n, API, dt.date(2026, 10, 21)) == []                 # 过了：没读的话登录会失败（预检报原因）


def test_merge_keeps_the_latest_and_the_earliest_first_seen():
    a = {"doc_update": {"value": "2026-10-20", "first_seen": "2026-10-09", "last_seen": "2026-10-09"}}
    b = {"doc_update": {"value": "2026-10-20", "first_seen": "2026-10-12", "last_seen": "2026-10-12"}}
    m = PC.merge(b, a)
    assert m["doc_update"]["first_seen"] == "2026-10-09" and m["doc_update"]["last_seen"] == "2026-10-12"


class _FakeTachi:
    def __init__(self, fail=None, next_release="", doc_update=""):
        self.calls, self.fail = [], fail
        self.next_release, self.doc_update = next_release, doc_update
        self.spec = SimpleNamespace(base_live=f"https://kabuka.e-shiten.jp/{API}/")

    def login(self):
        self.calls.append("login")
        if self.fail:
            raise self.fail

    def cash(self):
        self.calls.append("cash")
        return 300_000.0

    def logout(self):
        self.calls.append("logout")


def _agents(tmp_path, live=True) -> Path:
    a = tmp_path / "LaunchAgents"
    a.mkdir(exist_ok=True)
    if live:
        (a / "com.qbreak.liveu.morning.plist").write_text("x", encoding="utf-8")
    return a


def _run_pc(tmp_path, b, stars=(), now=THU_EVE, **kw):
    sent = []
    gate = [{"group": "准备", "name": s, "ok": False, "text": "★"} for s in stars] + [{"group": "参考", "name": "x", "ok": None}]
    rc = PC.run(_agents(tmp_path, kw.pop("live", True)), now=now, make_broker=lambda: b, gate=lambda ag: gate,
                send=lambda *x: sent.append(x), mac=lambda *x: sent.append(("mac",) + x), **kw)
    return rc, sent


def test_precheck_only_for_the_live_install(tmp_path, capsys):
    b = _FakeTachi()
    rc, sent = _run_pc(tmp_path, b, live=False)
    assert rc == 0 and b.calls == [] and not PC.result_path().exists() and "模拟模式不用" in capsys.readouterr().out
    rc, sent = _run_pc(tmp_path, b, now=FRI_EVE)
    assert rc == 0 and b.calls == [] and not sent                            # 明天休市：不登录


def test_precheck_ok_logs_in_reads_cash_and_logs_out(tmp_path):
    b = _FakeTachi()
    rc, sent = _run_pc(tmp_path, b)
    rec = json.loads(PC.result_path().read_text(encoding="utf-8"))
    assert rc == 0 and b.calls == ["login", "cash", "logout"] and rec["ok"] is True and rec["target"] == "2026-10-09"
    assert rec["api"] == API and not sent                                    # 没问题：不发通知


def test_precheck_failure_notifies_once_a_day_and_shows_in_the_panel(tmp_path):
    import json as _j
    b = _FakeTachi(fail=_j.JSONDecodeError("Expecting value", "<html>", 0))
    rc, sent = _run_pc(tmp_path, b)
    rec = json.loads(PC.result_path().read_text(encoding="utf-8"))
    assert rc == 1 and rec["ok"] is False and "可能是这个 API 版本已经停用" in rec["reasons"][0]
    assert b.calls == ["login", "logout"]                                     # 失败也登出
    titles = [x[0] for x in sent if x[0] != "mac"]
    assert titles == ["qbreak 立花实盘 ★ 前一晚预检没通过"] and sent[-1][2] == "warn"
    rc, sent2 = _run_pc(tmp_path, _FakeTachi(fail=_j.JSONDecodeError("Expecting value", "<html>", 0)))
    assert rc == 1 and not sent2                                              # 同一天同样的内容：不再发
    lines = PC.panel_lines(rec, THU_EVE + dt.timedelta(hours=12))
    assert lines and lines[0].startswith("★ 前一晚预检（10/08 20:00）没通过")
    assert PC.panel_lines(rec, THU_EVE + dt.timedelta(hours=40)) == []        # 太旧的不显示


def test_precheck_reminds_doc_update_and_api_release(tmp_path):
    b = _FakeTachi(next_release="20261128", doc_update="20261014")
    rc, sent = _run_pc(tmp_path, b)
    rec = json.loads(PC.result_path().read_text(encoding="utf-8"))
    assert rc == 0 and rec["ok"] is True and len(rec["notices"]) == 2
    assert rec[PC.KEY]["next_release"]["api"] == API and rec[PC.KEY]["doc_update"]["value"] == "2026-10-14"
    body = [x for x in sent if x[0] != "mac"][0]
    assert "★" in body[0] and "交付書面 2026-10-14" in body[1] and body[2] == "warn"


def test_precheck_gate_reports_only_new_stars(tmp_path):
    rc, sent = _run_pc(tmp_path, _FakeTachi(), stars=["⑥ 私钥文件"])
    assert [x for x in sent if x[0] != "mac"][0][1].count("⑥ 私钥文件") == 1    # 第一次：现有的 ★ 报一次
    rc, sent = _run_pc(tmp_path, _FakeTachi(), stars=["⑥ 私钥文件"], now=THU_EVE + dt.timedelta(days=4))   # 下周一晚
    assert not sent                                                            # 没有新的 ★：不发
    rc, sent = _run_pc(tmp_path, _FakeTachi(), stars=["⑥ 私钥文件", "⑦ Mac 工作日早上自动唤醒"],
                       now=THU_EVE + dt.timedelta(days=5))
    body = [x for x in sent if x[0] != "mac"][0][1]
    assert "⑦ Mac 工作日早上自动唤醒" in body and "⑥ 私钥文件" not in body
    rec = json.loads(PC.result_path().read_text(encoding="utf-8"))
    assert rec["new_stars"] == ["准备：⑦ Mac 工作日早上自动唤醒"]


def test_precheck_cli_refuses_without_live_install(capsys):
    import run
    assert run.main(["live-precheck"]) == 0 and "模拟模式不用" in capsys.readouterr().out


def test_gate_reference_shows_the_precheck():
    from qbreak import live_gate

    def run_(args, **kw):
        raise FileNotFoundError(args[0])
    items = live_gate.check(run=run_, today=dt.date(2026, 10, 9))
    ref = [it for it in items if it["name"].startswith("前一晚预检")]
    assert ref and ref[0]["ok"] is None and "还没做过" in ref[0]["text"]
    assert not notify_seen.path("tachibana").exists()                          # 门槛检查只读：不发通知


@pytest.mark.parametrize("argv", [["live-precheck"], ["live-precheck", "--force"], ["extra-closed", "add", "2026-10-14"],
                                  ["extra-closed", "rm", "2026-10-14"], ["live-u", "--broker", "tachibana", "--adopt-host"]],
                         ids=lambda v: " ".join(v))
def test_new_entries_refuse_repo_home_and_write_nothing(argv, tmp_path, monkeypatch, capsys):
    """公开仓库：数据目录在仓库里时，前一晚预检 / 临时休市的写入 / 换 Mac 都拒绝运行、不建任何文件、不连立花。"""
    import run
    from test_repo_guard import _no_broker
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", repo)
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    _no_broker(monkeypatch)
    assert run.main(argv) == 2
    assert "不能放进仓库的 var/" in capsys.readouterr().out
    assert list(repo.rglob("*")) == []
