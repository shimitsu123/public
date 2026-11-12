"""登录立花本番时推一条到手机（2026-10-17 用户：「每次登录立花本番的时候要在 qbreak 里面也要进行推送通过 api 登陆之类的消息
然后要简单说明接下来做什么」）：qbreak/brokers/tachibana.push_login。デモ不推；推送里不写认证 ID / 虚拟 URL / 金额；推送失败不影响登录。"""
import datetime as dt
import json

import pytest

from qbreak import paths
from qbreak.brokers import tachibana as T
from qbreak.calendar_jp import JST

from test_tachibana import _broker


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(T.LOGIN_PUSH_ENV, "1")


@pytest.mark.parametrize("argv, what, nxt", [
    (["run.py", "live-u", "--broker", "tachibana"], "早上的运行", "下今天的寄付单"),
    (["run.py", "live-u", "--broker", "tachibana", "--retry"], "早上运行的重试", "补下没下成的寄付单"),
    (["run.py", "live-u", "--broker", "tachibana", "--phase", "open"], "开盘后补单（09:05）", "下等开盘后的买单"),
    (["run.py", "live-u", "--broker", "tachibana", "--phase", "open", "--retry"], "09:20 最后一次", "还没始値的放弃"),
    (["run.py", "live-u", "--broker", "tachibana", "--phase", "now"], "盘中的手动指令", "先卖后买"),
    (["run.py", "live-u", "--broker", "tachibana", "--cancel", "U1"], "撤单", "按注文番号撤"),
    (["run.py", "live-u", "--broker", "tachibana", "--dry-run", "--no-clock"], "dry-run", "不发"),
    (["run.py", "tachibana-probe"], "连通检查（只读）", "不发单"),
    (["run.py", "live-precheck"], "前一晚预检", "不发单"),
    (["run.py", "live-reconcile"], "持仓核对", "不发单"),
    (["run.py", "live-unknown"], "状态不明", "不改账本"),
    (["run.py", "live-broker"], "今天的成交", "不发单"),
    (["run.py", "something-new"], "run.py something-new", "登出"),
])
def test_purpose_says_what_and_what_next(argv, what, nxt):
    w, n = T.login_purpose(argv)
    assert what in w and nxt in n and "登出" in n


def test_push_text_has_time_purpose_next_and_how_to_stop(on):
    got = []
    b = type("B", (), {"purpose": ("模拟账户取实时价（只读）", "取现价 → 马上登出")})()
    T.push_login(b, when=dt.datetime(2026, 10, 19, 9, 25, tzinfo=JST), send=lambda *a: got.append(a))
    (subj, text, lvl), = got
    assert subj == "立花本番 API 登录 09:25：模拟账户取实时价（只读）" and lvl == "info"
    assert text.startswith("接下来：取现价 → 马上登出\n") and "「停」" in text and "無効化" in text


def test_push_is_off_in_tests_and_never_raises(monkeypatch):
    got = []
    T.push_login(object(), send=lambda *a: got.append(a))
    assert got == []                                                     # conftest 关着
    monkeypatch.setenv(T.LOGIN_PUSH_ENV, "1")
    T.push_login(object(), send=lambda *a: (_ for _ in ()).throw(RuntimeError("推送挂了")))   # 不抛


def test_real_login_records_one_push_and_no_secrets(on, monkeypatch):
    monkeypatch.setattr("sys.argv", ["run.py", "live-u", "--broker", "tachibana"])
    b, tr = _broker()
    b.login()
    b.login()                                                            # 已经登录：不再登录、不再推
    rows = [json.loads(x) for x in (paths.out_dir() / "notifications.jsonl").read_text(encoding="utf-8").splitlines()]
    mine = [r for r in rows if r["subject"].startswith("立花本番 API 登录")]
    assert len(mine) == 1 and "早上的运行" in mine[0]["subject"] and "下今天的寄付单" in mine[0]["text"]
    blob = json.dumps(mine, ensure_ascii=False)
    assert "AUTH-XYZ" not in blob and "https://x/" not in blob and "2nd-pw" not in blob
    b.logout()


def test_demo_login_does_not_push(on, monkeypatch):
    got = []
    monkeypatch.setattr(T, "push_login", lambda *a, **k: got.append(a))
    b, _ = _broker(demo=True)
    b.login()
    assert got == []
    b2, _ = _broker()
    b2.login()
    assert len(got) == 1
    b2.logout()
