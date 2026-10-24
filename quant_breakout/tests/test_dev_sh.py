"""scripts/dev.sh：Mac 本地的 Claude 改代码 → 测试 → 提交 → 推送 → ~/qbreak-src 快进（2026-10-09 起不需要云端会话）。

全部在临时目录：一个 bare 仓库当远端，三个克隆（dev = ~/qbreak-dev、src = ~/qbreak-src、cloud = 云端例行任务）；
HOME 也指向临时目录（不读你的 git 全局设置），不联网、不碰真的仓库。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEV_SH = ROOT / "scripts" / "dev.sh"
BRANCH = "claude/rakuten-auto-trading-review-ka7lf0"

pytestmark = pytest.mark.skipif(not shutil.which("git") or not shutil.which("bash"), reason="需要 git + bash")


def _git(cwd, *args, ident=True) -> str:
    pre = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"] if ident else []
    r = subprocess.run(["git", *pre, *args], cwd=cwd, capture_output=True, text=True, timeout=60,
                       env=_base_env(Path(cwd)))
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r.stdout


def _base_env(home: Path) -> dict:
    """不读你的 git 设置（HOME / XDG 指向临时目录、不读系统设置），不经代理（远端都是本机路径或连不上的地址）。"""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GIT_", "QBREAK_", "XDG_")) and k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    return {**env, "HOME": str(home), "XDG_CONFIG_HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1", "LANG": "C.UTF-8", "TZ": "UTC"}


@pytest.fixture
def repos(tmp_path):
    """远端（bare）+ dev / src / cloud 三个克隆；dev 设了 git 身份（像用户在 Mac 上设好的那样）。"""
    t = tmp_path
    _git(t, "init", "-q", "--bare", "remote.git", ident=False)
    seed = t / "seed"
    (seed / "quant_breakout" / "tests").mkdir(parents=True)
    (seed / "quant_breakout" / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    (seed / "quant_breakout" / "tests" / "test_env.py").write_text(
        'import os\n\ndef test_no_home():\n    assert "QBREAK_HOME" not in os.environ\n', encoding="utf-8")
    (seed / "quant_breakout" / "app.txt").write_text("v1\n", encoding="utf-8")
    _git(seed, "init", "-q", "-b", BRANCH, ident=False)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "init")
    _git(seed, "push", "-q", str(t / "remote.git"), BRANCH, ident=False)
    for name in ("dev", "src", "cloud"):
        _git(t, "clone", "-q", "-b", BRANCH, str(t / "remote.git"), name, ident=False)
    _git(t / "dev", "config", "user.name", "t", ident=False)
    _git(t / "dev", "config", "user.email", "t@example.invalid", ident=False)
    return t


def _run(t: Path, *args, **extra) -> tuple[int, str]:
    env = {**_base_env(t), "QBREAK_DEV": str(t / "dev"), "QBREAK_SRC": str(t / "src"),
           "QBREAK_PYTHON": sys.executable, "QBREAK_DEV_CLOCK": "6 1200", **extra}   # 默认：周六中午（不在执行器的时段）
    r = subprocess.run(["bash", str(DEV_SH), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    return r.returncode, r.stdout + r.stderr


def _commit(clone: Path, rel: str, text: str, msg: str):
    p = clone / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    _git(clone, "add", rel)
    _git(clone, "commit", "-q", "-m", msg)


def _head(clone: Path, ref: str = "HEAD") -> str:
    return _git(clone, "rev-parse", ref, ident=False).strip()


def test_usage_without_args(repos):
    rc, out = _run(repos)
    assert rc == 2 and "用法：bash scripts/dev.sh check | test [pytest 参数] | push" in out


def test_check_all_ok(repos):
    rc, out = _run(repos, "check")
    assert rc == 0, out
    for s in ("[OK] 当前分支：" + BRANCH, "[OK] 上游：origin/" + BRANCH, "[OK] 能连到远端 origin",
              "[OK] 推送权限：有（--dry-run，什么都没推）", "[OK] git 的 user.name / user.email：都设了（只看了有没有）",
              "[OK] 测试环境：Python ", "没有本地改动（07:40 的定时任务能拉到新代码）", "全部 [OK]（8 项）"):
        assert s in out, (s, out)
    assert "[★]" not in out
    assert "t@example.invalid" not in out                                # 只说有没有，不打印值


def test_check_is_read_only_and_flags_problems(repos):
    t = repos
    _commit(t / "cloud", "quant_breakout/var/x.csv", "1\n", "routine")   # 远端有新提交（例行任务）→ 推送权限仍算有
    _git(t / "cloud", "push", "-q", "origin", BRANCH, ident=False)
    (t / "src" / "quant_breakout" / "app.txt").write_text("改了\n", encoding="utf-8")   # src 被改过 → 07:40 拉不下来
    _git(t / "dev", "config", "--unset", "user.email", ident=False)
    before = (_head(t / "dev"), _head(t / "remote.git", BRANCH))
    rc, out = _run(t, "check")
    assert rc == 1, out
    assert "[OK] 推送权限：有（远端有本地还没有的新提交" in out
    assert "[★] git 的 user.email 没设：" in out and "noreply" in out
    assert "被跟踪的文件被改过：07:40 的 git pull 会失败" in out
    assert "★ 2 项要处理" in out
    assert (_head(t / "dev"), _head(t / "remote.git", BRANCH)) == before   # 只读：什么都没动
    assert (t / "src" / "quant_breakout" / "app.txt").read_text(encoding="utf-8") == "改了\n"


def test_check_push_denied_and_bad_python(repos, tmp_path):
    t = repos
    _git(t / "dev", "remote", "set-url", "--push", "origin", "https://ghp_abcdefghijklmnopqrstu@127.0.0.1:9/x.git", ident=False)
    fake = tmp_path / "py"
    fake.write_text("#!/bin/sh\necho 3.9\nexit 1\n", encoding="utf-8")
    fake.chmod(0o755)
    rc, out = _run(t, "check", QBREAK_PYTHON=str(fake))
    assert rc == 1, out
    assert "[★] 推不上去（没有推送权限 / 没登录 GitHub）：请你自己在终端运行 gh auth login" in out and "令牌 / 密码不要贴进聊天" in out
    assert "ghp_abcdefghijklmnopqrstu" not in out                           # 报错里没有令牌（这里 git 自己就抹掉了；scrub 见下一个测试）
    assert "[★] Python 3.9 低于 3.10" in out
    _git(t / "dev", "checkout", "-q", "-b", "other", ident=False)
    rc, out = _run(t, "check")
    assert "[★] 当前分支是 other，不是 " + BRANCH in out


def test_check_missing_clones(tmp_path):
    rc, out = _run(tmp_path, "check")
    assert rc == 1
    assert "[★] 没有研究用的克隆 " in out and "[★] 没有定时任务用的克隆 " in out


def test_test_runs_pytest_without_qbreak_home(repos):
    rc, out = _run(repos, "test", QBREAK_HOME="/should/not/leak")
    assert rc == 0, out
    assert "1 passed" in out
    (repos / "dev" / "quant_breakout" / "tests" / "test_fail.py").write_text("def test_f():\n    assert False\n", encoding="utf-8")
    rc, out = _run(repos, "test", "-k", "test_f")
    assert rc != 0 and "1 failed" in out                                    # 退出码照 pytest（失败 → 不能提交）


def test_push_pushes_rebases_and_fast_forwards_src(repos):
    t = repos
    _commit(t / "cloud", "quant_breakout/var/daily.csv", "1\n", "routine: 日报")   # 例行任务先推了 var/
    _git(t / "cloud", "push", "-q", "origin", BRANCH, ident=False)
    _commit(t / "dev", "quant_breakout/app.txt", "v2\n", "改 app：第二版")
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b")
    rc, out = _run(t, "push")
    assert rc == 0, out
    assert "[OK] 已推送 2 个提交到 origin/" + BRANCH in out
    assert "改 app：第二版" in out and "加 b" in out and "routine" not in out.split("已推送", 1)[1]
    assert _head(t / "remote.git", BRANCH) == _head(t / "dev")
    assert "已快进到最新（07:40 的定时任务用新代码）" in out
    assert _head(t / "src") == _head(t / "dev")
    assert (t / "src" / "quant_breakout" / "var" / "daily.csv").exists()
    rc, out = _run(t, "push")                                               # 再跑一次：没有要推的
    assert rc == 0 and "没有要推的提交（远端已经是最新）" in out


def test_push_stops_on_uncommitted_changes(repos):
    t = repos
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b")
    (t / "dev" / "quant_breakout" / "app.txt").write_text("没提交\n", encoding="utf-8")
    remote = _head(t / "remote.git", BRANCH)
    rc, out = _run(t, "push")
    assert rc == 1
    assert "有未提交的改动：没推" in out and "quant_breakout/app.txt" in out
    assert _head(t / "remote.git", BRANCH) == remote                         # 什么都没推


def test_push_stops_on_conflict_without_resolving(repos):
    t = repos
    _commit(t / "cloud", "quant_breakout/app.txt", "云端\n", "cloud edit")
    _git(t / "cloud", "push", "-q", "origin", BRANCH, ident=False)
    _commit(t / "dev", "quant_breakout/app.txt", "本地\n", "dev edit")
    head, remote = _head(t / "dev"), _head(t / "remote.git", BRANCH)
    rc, out = _run(t, "push")
    assert rc == 1, out
    assert "pull --rebase 有冲突" in out and "quant_breakout/app.txt" in out and "不自动解决、什么都没推" in out
    assert _head(t / "dev") == head and _head(t / "remote.git", BRANCH) == remote
    assert (t / "dev" / "quant_breakout" / "app.txt").read_text(encoding="utf-8") == "本地\n"
    assert not (t / "dev" / ".git" / "rebase-merge").exists() and not (t / "dev" / ".git" / "rebase-apply").exists()


def test_push_leaves_dirty_src_alone(repos):
    t = repos
    (t / "src" / "quant_breakout" / "app.txt").write_text("src 里改了\n", encoding="utf-8")
    src = _head(t / "src")
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b")
    rc, out = _run(t, "push")
    assert rc == 0, out
    assert "[OK] 已推送 1 个提交" in out and "有本地改动：不动" in out
    assert _head(t / "src") == src and (t / "src" / "quant_breakout" / "app.txt").read_text(encoding="utf-8") == "src 里改了\n"


def test_push_does_not_swap_src_code_during_the_executor_morning(repos):
    t = repos
    src = _head(t / "src")
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b")
    rc, out = _run(t, "push", QBREAK_DEV_CLOCK="3 0850")                    # 周三 08:50 JST：09:05 的开盘后补单还没跑
    assert rc == 0, out
    assert "[OK] 已推送 1 个提交" in out and "执行器早上运行的时段：不换" in out
    assert _head(t / "src") == src


def test_push_refuses_other_branch_and_missing_identity(repos):
    t = repos
    _git(t / "dev", "config", "--unset", "user.name", ident=False)
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b")
    remote = _head(t / "remote.git", BRANCH)
    rc, out = _run(t, "push")
    assert rc == 1 and "user.name / user.email 没设：没推" in out
    _git(t / "dev", "checkout", "-q", "-b", "other", ident=False)
    rc, out = _run(t, "push")
    assert rc == 1 and "不是 " + BRANCH + "：不推" in out
    assert _head(t / "remote.git", BRANCH) == remote


def test_push_auth_failure_hint(repos):
    t = repos
    _git(t / "dev", "remote", "set-url", "--push", "origin", str(t / "nope.git"), ident=False)
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b")
    rc, out = _run(t, "push")
    assert rc == 1
    assert "★ 推不上去（没有推送权限 / 没登录 GitHub）：请你自己在终端运行 gh auth login" in out


def test_check_scrubs_tokens_that_git_itself_prints(repos, tmp_path):
    """git 不会替你抹掉的地方（假 git：push 的报错里带「账户:令牌@」的 URL 和 github_pat_ 令牌）→ dev.sh 的 scrub 抹掉再显示。"""
    real = shutil.which("git")
    b = tmp_path / "fakebin"
    b.mkdir()
    (b / "git").write_text(
        "#!/bin/sh\nfor a in \"$@\"; do if [ \"$a\" = push ]; then\n"
        "  echo \"fatal: unable to access 'https://u:ghp_abcdefghijklmnopqrstu@h.example/x.git/': token github_pat_11ABCDEFGHIJKLMNOP_xyz\" >&2\n"
        f"  exit 128\nfi; done\nexec \"{real}\" \"$@\"\n", encoding="utf-8")
    (b / "git").chmod(0o755)
    rc, out = _run(repos, "check", PATH=f"{b}{os.pathsep}{os.environ['PATH']}")
    assert rc == 1 and "[★] 推不上去" in out
    assert "ghp_abcdefghijklmnopqrstu" not in out and "github_pat_11ABCDEFGHIJKLMNOP" not in out and "u:ghp" not in out
    assert "https://***@h.example/x.git/" in out and "token ***" in out


def _commit_as(clone: Path, rel: str, msg: str, who: str | None = None):
    """以别的身份（像没设 git 身份时 git 用本机用户名 / 主机名凑的那样）提交。"""
    env = _base_env(clone)
    if who:
        env.update({"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": f"{who}@Johns-MacBook.local",
                    "GIT_COMMITTER_NAME": who, "GIT_COMMITTER_EMAIL": f"{who}@Johns-MacBook.local"})
    (clone / rel).parent.mkdir(parents=True, exist_ok=True)
    (clone / rel).write_text(msg + "\n", encoding="utf-8")
    for args in (["add", rel], ["commit", "-q", "-m", msg]):
        r = subprocess.run(["git", *args], cwd=clone, env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


def test_push_refuses_commits_made_with_another_identity(repos):
    """没设身份时做的提交（git 用本机用户名 / 主机名凑的身份）：之后设好身份也不会改它们 → 不推，告诉你怎么改。"""
    t = repos
    _commit_as(t / "dev", "quant_breakout/b.txt", "加 b", who="macuser")
    remote = _head(t / "remote.git", BRANCH)
    rc, out = _run(t, "push")
    assert rc == 1, out
    assert "2 处作者 / 提交者不是现在设的 git 身份" in out and "--reset-author" in out and "没推" in out
    assert "macuser" not in out and "Johns-MacBook" not in out and "t@example.invalid" not in out   # 不打印名字 / 邮箱
    assert _head(t / "remote.git", BRANCH) == remote
    _git(t / "dev", "rebase", "-q", "origin/" + BRANCH, "--exec", "git commit --amend --no-edit --reset-author -q", ident=False)
    rc, out = _run(t, "push")                                               # 照提示改成现在的身份 → 推上去
    assert rc == 0 and "[OK] 已推送 1 个提交" in out, out
    assert _git(t / "remote.git", "log", "-1", "--format=%an <%ae> %cn <%ce>", BRANCH, ident=False).strip() == \
        "t <t@example.invalid> t <t@example.invalid>"


def test_push_refuses_a_versioned_model_trailer(repos):
    """提交信息不写模型名（CLAUDE.md）：带版本号的「Co-Authored-By: Claude <名字> <版本>」署名行 → 不推；不带模型名的署名照常。"""
    t = repos
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b\n\nCo-Authored-By: Claude Foo 9.9 <noreply@anthropic.com>")
    remote = _head(t / "remote.git", BRANCH)
    rc, out = _run(t, "push")
    assert rc == 1 and "带模型名的署名行" in out and "没推" in out, out
    assert _head(t / "remote.git", BRANCH) == remote
    _git(t / "dev", "rebase", "-q", "origin/" + BRANCH, "--exec",
         "git log -1 --format=%B | grep -viE '^Co-Authored-By:.*Claude [A-Za-z]+ [0-9]' | git commit --amend -q -F -", ident=False)
    _commit(t / "dev", "quant_breakout/c.txt", "c\n", "加 c\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    rc, out = _run(t, "push")                                               # 照提示去掉那一行；不带模型名的署名照常推
    assert rc == 0 and "[OK] 已推送 2 个提交" in out, out
    assert "Foo 9.9" not in _git(t / "remote.git", "log", "--format=%B", BRANCH, ident=False)


def test_push_remote_rejection_shows_the_remote_reason(repos):
    """远端拒绝（GitHub 的推送保护 GH013 等）不是登录问题：显示 remote: 的原因，不叫你重新登录。"""
    t = repos
    hook = t / "remote.git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'error: GH013: Repository rule violations found for refs/heads/x.' >&2\n"
                    "echo '- Push cannot contain secrets' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    _commit(t / "dev", "quant_breakout/b.txt", "b\n", "加 b")
    remote = _head(t / "remote.git", BRANCH)
    rc, out = _run(t, "push")
    assert rc == 1, out
    assert "★ 远端拒绝（GitHub 的仓库规则 / 推送保护" in out and "不要绕过推送保护" in out
    assert "remote: error: GH013: Repository rule violations found" in out and "Push cannot contain secrets" in out
    assert "gh auth login" not in out and _head(t / "remote.git", BRANCH) == remote
