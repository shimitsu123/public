"""公开仓库防呆（缺口盘点 C-03）：立花的账本 / 检查结果 / 仕様文件 / ARM / HALT 不入库（.gitignore），
数据目录在仓库里面时立花的入口（live-u / manual --broker tachibana、tachibana-probe、旧的分市场实盘）直接拒绝运行、不建任何文件。"""
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from qbreak import paths

IGNORED = [   # 只在 Mac 的数据目录：真实账户的持仓 / 现金 / 单子、检查结果、解锁 / 停止文件、运行锁、运行状态、自检、通知去重
    "var/state/live_unified_tachibana.json", "var/state/live_unified_tachibana_demo.json",
    "var/state/live_unified_tachibana_dryrun.json", "var/state/live_unified_tachibana_broker.json",
    "var/state/live_unified_tachibana.lock", "var/state/live_unified_paper.lock",
    "var/out/live_unified_tachibana.json", "var/out/live_unified_tachibana_journal.md",
    "var/out/tachibana_probe_live.json", "var/out/tachibana_probe_demo.json",
    "var/out/charts_tachibana.json", "var/out/page_tachibana.html",
    "var/tachibana_spec.json", "var/ARM", "var/HALT", "var/e_api_private_key.pem",
    "var/out/watchdog_tachibana.json", "var/out/watchdog_paper.json",
    "var/out/notify_seen_tachibana.json", "var/out/live_unified_tachibana_run.json", "var/out/live_unified_paper_run.json",
    "var/manual/requests_tachibana.jsonl",
]
KEPT = [      # 模拟账户（云端 / 研究要看）与远程停止照旧入库
    "var/state/live_unified_paper.json", "var/state/live_unified_paper_broker.json",
    "var/out/live_unified_paper.json", "var/out/live_unified_paper_journal.md",
    "var/HALT_REMOTE", "var/out/tachibana_gap_audit.md", "var/state/unified_state.json",
]
PATTERNS = ["var/state/live_unified_tachibana*", "var/out/live_unified_tachibana*", "var/out/tachibana_probe_*",
            "var/out/charts_tachibana*", "var/tachibana_spec.json", "var/ARM", "var/HALT", "var/state/*.lock", "var/*.pem",
            "var/out/watchdog_*", "var/out/notify_seen_*", "var/out/live_unified_*_run.json"]


def _git_ok() -> bool:
    if not shutil.which("git"):
        return False
    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=paths.PROJECT_ROOT, capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def test_tachibana_outputs_are_gitignored():
    gi = (paths.PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for p in PATTERNS:
        assert p in gi, p
    if not _git_ok():
        pytest.skip("没有 git 工作树：只查了 .gitignore 的文字")
    for p in IGNORED + KEPT:                              # --no-index：只看规则（文件在不在、是否已跟踪都不影响）
        r = subprocess.run(["git", "check-ignore", "-q", "--no-index", p], cwd=paths.PROJECT_ROOT, capture_output=True)
        assert r.returncode in (0, 1), (p, r.stderr)
        assert (r.returncode == 0) == (p in IGNORED), p
    tracked_ignored = subprocess.run(["git", "ls-files", "-ci", "--exclude-standard", "--", "var"],
                                     cwd=paths.PROJECT_ROOT, capture_output=True, text=True).stdout.split()
    assert tracked_ignored == []                          # 已跟踪的文件（模拟账户的账本等）一个都没被新规则盖住


def test_inside_repo(tmp_path, monkeypatch):
    var = paths.PROJECT_ROOT / "var"
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    assert paths.inside_repo()                            # 没设 = 仓库的 var/
    monkeypatch.setenv("QBREAK_HOME", str(var))
    assert paths.inside_repo()
    probe = var / "no_such_dir_repo_guard"
    monkeypatch.setenv("QBREAK_HOME", str(probe))
    assert paths.inside_repo() and not probe.exists()     # 只判断，不建目录
    monkeypatch.setenv("QBREAK_HOME", str(paths.repo_root()))
    assert paths.inside_repo()                            # 仓库根本身
    monkeypatch.chdir(paths.PROJECT_ROOT)
    monkeypatch.setenv("QBREAK_HOME", "var")
    assert paths.inside_repo()                            # 相对路径按当前目录
    link = tmp_path / "link_to_repo_var"
    link.symlink_to(var, target_is_directory=True)
    monkeypatch.setenv("QBREAK_HOME", str(link))
    assert paths.inside_repo()                            # 符号链接按实际位置
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path / "home"))
    assert not paths.inside_repo()


def test_repo_root_looks_one_level_up_only(tmp_path, monkeypatch):
    top = tmp_path / "home"
    proj = top / "src" / "quant_breakout"
    proj.mkdir(parents=True)
    (top / ".git").mkdir()                                # 家目录本身是 git 仓库（两级以上）：不算
    monkeypatch.setattr(paths, "PROJECT_ROOT", proj)
    assert paths.repo_root() == proj
    monkeypatch.setenv("QBREAK_HOME", str(top / ".qbreak" / "home"))
    assert not paths.inside_repo()
    (top / "src" / ".git").mkdir()                        # <仓库>/quant_breakout 的布局：仓库根 = 上一级
    assert paths.repo_root() == top / "src"
    monkeypatch.setenv("QBREAK_HOME", str(top / "src" / "var"))
    assert paths.inside_repo()


def _no_broker(monkeypatch):
    from qbreak.brokers import tachibana as T

    def boom(*a, **k):
        raise AssertionError("被拒绝时不应该连立花")
    monkeypatch.setattr(T.TachibanaBroker, "__init__", boom)
    monkeypatch.setattr(T.TachibanaSpec, "load", classmethod(lambda cls: boom()))


REFUSED = [
    ["live-u", "--broker", "tachibana"],
    ["live-u", "--broker", "tachibana", "--status"],
    ["live-u", "--broker", "tachibana", "--demo", "--no-clock"],
    ["live-u", "--broker", "tachibana", "--dry-run", "--phase", "open", "--retry"],
    ["live-u", "--broker", "tachibana", "--phase", "now"],
    ["live-u", "--broker", "tachibana", "--flow", "300000"],
    ["live-u", "--broker", "tachibana", "--resolve", "c1", "--filled", "100", "--px", "1000"],
    ["tachibana-probe"],
    ["tachibana-probe", "--demo", "--dump-spec"],
    ["tachibana-probe", "--demo", "--order-test"],
    ["tachibana-probe", "--order-test"],
    ["manual", "list", "--broker", "tachibana"],
    ["manual", "sell", "7203", "--broker", "tachibana"],
    ["manual", "core", "--pct", "0", "--broker", "tachibana", "--demo"],
]


@pytest.mark.parametrize("argv", REFUSED, ids=lambda v: " ".join(v))
def test_tachibana_entries_refuse_repo_home_and_write_nothing(argv, tmp_path, monkeypatch, capsys):
    import run
    repo = tmp_path / "repo"                              # 假的仓库：没设 QBREAK_HOME → 数据目录 = repo/var
    repo.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", repo)
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    _no_broker(monkeypatch)
    assert run.main(argv) == 2
    out = capsys.readouterr().out
    assert "不能放进仓库的 var/" in out and "liveu.sh" in out and "QBREAK_HOME=~/.qbreak/home" in out
    assert "没设 QBREAK_HOME" in out and str(repo) not in out          # 不打印路径
    assert list(repo.rglob("*")) == []                    # 没建任何文件 / 目录
    monkeypatch.setenv("QBREAK_HOME", str(repo / "var"))  # QBREAK_HOME 明确指到仓库里：一样拒绝
    assert run.main(argv) == 2
    assert "QBREAK_HOME 指向仓库里面" in capsys.readouterr().out
    assert list(repo.rglob("*")) == []


def test_real_repo_var_is_refused_by_the_guard(monkeypatch, capsys):
    """真实仓库的布局（.git 在上一级）：只判断，不运行任何入口（入口被拒绝、不写文件由上面的假仓库测试覆盖；
    防呆一旦回归，在真实仓库里跑入口就会把页面 / 账本写进工作树）。"""
    import run
    var = paths.PROJECT_ROOT / "var"
    for env in (None, str(var)):
        if env is None:
            monkeypatch.delenv("QBREAK_HOME", raising=False)
        else:
            monkeypatch.setenv("QBREAK_HOME", env)
        assert paths.inside_repo()
        assert run._refuse_repo_home("x") == 2
    assert capsys.readouterr().out.count("不能放进仓库的 var/") == 2


def test_nested_repo_layout_refuses_entries_and_writes_nothing(tmp_path, monkeypatch):
    """<仓库>/quant_breakout 的布局（.git 在上一级）放在临时目录里：没设 QBREAK_HOME → 数据目录 = <仓库>/quant_breakout/var → 拒绝。"""
    import run
    top = tmp_path / "repo"
    proj = top / "quant_breakout"
    proj.mkdir(parents=True)
    (top / ".git").mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", proj)
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    _no_broker(monkeypatch)
    for argv in (["live-u", "--broker", "tachibana", "--status"], ["tachibana-probe", "--dump-spec"],
                 ["manual", "list", "--broker", "tachibana"]):
        assert run.main(argv) == 2
    assert sorted(p.name for p in top.rglob("*")) == [".git", "quant_breakout"]


def test_legacy_tachibana_broker_refused(tmp_path, monkeypatch, capsys):
    import run
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", repo)
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    _no_broker(monkeypatch)
    a = SimpleNamespace(cmd="live", broker="tachibana", demo=False, no_arm=False, dry_run=True, limit_buffer=0.5,
                        max_order_value=300_000)
    with pytest.raises(SystemExit) as e:
        run._make_broker(a, "JP", None)
    assert e.value.code == 2 and "live --broker tachibana" in capsys.readouterr().out
    assert list(repo.rglob("*")) == []


def test_outside_repo_and_paper_not_refused(tmp_path, monkeypatch, capsys):
    import run
    assert not paths.inside_repo()                        # 测试的数据目录 = tmp_path（conftest）
    assert run._refuse_repo_home("x") is None
    assert run.main(["manual", "list", "--broker", "tachibana"]) == 0
    assert "不能放进仓库的 var/" not in capsys.readouterr().out
    repo = tmp_path / "repo"                              # 模拟账户：数据目录在仓库里也照常（云端 / 测试）
    repo.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", repo)
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    assert paths.inside_repo()
    assert run.main(["manual", "list", "--broker", "paper"]) == 0
    assert "不能放进仓库的 var/" not in capsys.readouterr().out
