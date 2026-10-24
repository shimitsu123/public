"""routines.py — 例行任务搬到 Mac（2026-10-09 用户「连云端例行任务也搬到 Mac」）：scripts/routines.sh 用的小工具（只读、只算）。

模拟盘日报 / 影子账户判断 / 季度复核在 Mac 的 Claude 桌面版「本机任务」里跑（工作文件夹 ~/qbreak-sim，说明书 routines/*.md）；
云端同名例行任务是后备（Mac 当天做过就跳过）。谁做的看提交信息的开头：Mac 写「sim(mac): / shadow(mac): / 季度复核(mac)：」，
云端照旧「sim: / shadow: / 季度复核：」（仓库里没有别的代码解析这些前缀，2026-10-09 查过）。
只看提交信息与提交时间，不看、不打印提交者的名字 / 邮箱。

命令（routines.sh 调用；输入输出都是纯文本；提交 = 每行「提交时间戳（秒）<TAB>标题」，git log --format='%ct%x09%s'）：
  python -m qbreak.routines day [YYYY-MM-DD]               → 「星期（1〜7） 交易日（1 / 0）」；不给日期 = 今天（JST）
  python -m qbreak.routines done <shadow|quarterly> <日期>  < 提交 → 找到那天的 → 打印「Mac / 云端」、退出 0；没有 → 退出 1
  python -m qbreak.routines who                             < 一行标题 → 「Mac / 云端」
  python -m qbreak.routines wake [HH:MM]                    < pmset -g sched 的输出 → 「OK|NG|?<TAB>说明」（默认 06:50 之前）
  python -m qbreak.routines app <Info.plist> [最低版本]       → 「OK|NG|?<TAB>说明」（Claude 桌面版的版本）
  python -m qbreak.routines table <日期> [n]                 < 提交 → 最近 n 个工作日（周一至五）每天的日报 / 影子账户是谁做的
  python -m qbreak.routines local                           < 没推上去的提交、一行「--origin--」、远端的提交
                                                            → redundant（都是 Mac 例行任务的结果，远端那天已经有同一种的）/
                                                              pushable（都是 Mac 例行任务的结果，远端还没有）/ other（有别的提交）
  python -m qbreak.routines listed <运行记录目录> <任务 id>   → 「1|0|?」：最新的 scheduled-tasks.json 里有没有这个任务（读不到 → ?；2026-10-24 复核）
  python -m qbreak.routines desktop <运行记录目录> <对话记录目录> <任务 id=名字（一行一个）>
                                                            → 「OK|NG|WARN|?<TAB>说明」一行一条：本机任务按时跑了没有、有没有卡住的运行
                                                              （桌面版的 scheduled-tasks.json / local_*.json / 对话记录；只读；现在 = QBREAK_ROUTINES_NOW 或真的现在）
  python -m qbreak.routines allow-check                     → 「OK|NG|?|HINT<TAB>说明」：说明书要运行的 Bash 命令有没有对不上允许规则的（只打印对不上的命令）
  python -m qbreak.routines allow-missing                   → 对不上的命令要加的规则（JSON 数组，「Bash(…)」；没有 → []）
     （规则文件 QBREAK_SIM_SETTINGS，默认 <QBREAK_SIM 或 ~/qbreak-sim>/.claude/settings.local.json；任务自己允许过的从
      QBREAK_DESKTOP_DIR / CLAUDE_CONFIG_DIR 读；2026-10-16 起）
  python -m qbreak.routines reap [--dry]                     → 本机任务卡在权限确认 30 分钟以上（进程还在、没在跑命令）→ 停止它、推一条通知
                                                              （liveu.sh news 每 15 分钟调用；一个任务一天最多 2 次；2026-10-21 起）
"""
from __future__ import annotations

import datetime as dt
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .calendar_jp import JST, is_trading_day, now_jst

APP_MIN = "1.1.5368"                      # 桌面版有「本机任务」（Local routine）的最低版本（官方文档，2026-10-09 查）
WAKE_BY = (6, 50)                         # 本机日报 06:45：Mac 要在这之前醒（pmset 工作日 06:40）
WAKE_CMD = "sudo pmset repeat wakeorpoweron MTWRF 06:40:00"
_PREFIX = {
    "sim": re.compile(r"^sim(\(mac\))?:"),
    "shadow": re.compile(r"^shadow(\(mac\))?:\s*(\d{4}-\d{2}-\d{2})"),
    "quarterly": re.compile(r"^季度复核(\(mac\))?："),
}
WEEK = "一二三四五六日"


def who(subject: str) -> str:
    """提交标题 → 「Mac」（开头的标签带 (mac)）/「云端」。"""
    return "Mac" if re.match(r"^[^:：\s]{1,12}\(mac\)[:：]", subject or "") else "云端"


def parse_log(text: str) -> list[tuple[dt.date, str]]:
    """「时间戳<TAB>标题」的行 → [(提交日（JST）, 标题)]；读不懂的行跳过。"""
    out = []
    for ln in (text or "").splitlines():
        ts, _, subj = ln.partition("\t")
        try:
            d = dt.datetime.fromtimestamp(int(ts.strip()), JST).date()
        except (ValueError, OverflowError, OSError):
            continue
        out.append((d, subj.strip()))
    return out


def find(kind: str, entries: list[tuple[dt.date, str]], day: dt.date) -> str | None:
    """那天的「日报 / 影子账户 / 季度复核」提交是谁做的（「Mac」/「云端」）；没有 → None。entries 新的在前。
    日报：标题 sim: / sim(mac):、提交日 = 那天（标题里的是 K 线日期，不是运行日）；影子账户：标题里的日期 = 那天；
    季度复核：标题 季度复核：/ 季度复核(mac)：，标题里有那天的日期或提交日 = 那天（「季度复核加 …」这类改例行任务的提交不算）。"""
    pat = _PREFIX[kind]
    for d, s in entries:
        m = pat.match(s)
        if not m:
            continue
        if kind == "shadow":
            ok = m.group(2) == day.isoformat()
        elif kind == "quarterly":
            ok = day.isoformat() in s or d == day
        else:
            ok = d == day
        if ok:
            return who(s)
    return None


def classify_local(local: list[tuple[dt.date, str]], origin: list[tuple[dt.date, str]]) -> str:
    """例行任务克隆里没推上去的提交（上一次推送失败 / 和云端后备同时做、rebase 冲突留下的）：
    "redundant" = 全是 Mac 例行任务的结果（标题 sim(mac): / shadow(mac): / 季度复核(mac)：），而远端那天已经有同一种的（云端后备做了）→
    可以放到备份分支、回到远端；"pushable" = 全是 Mac 例行任务的结果、远端还没有 → 该推上去；"other" = 有别的提交 → 不自动处理。"""
    if not local:
        return "other"
    missing = False
    for d, s in local:
        kind = next((k for k, p in _PREFIX.items() if p.match(s)), None)
        if kind is None or who(s) != "Mac":
            return "other"
        day = d
        if kind == "shadow":
            day = dt.date.fromisoformat(_PREFIX["shadow"].match(s).group(2))
        if find(kind, origin, day) is None:
            missing = True
    return "pushable" if missing else "redundant"


def weekdays_back(today: dt.date, n: int) -> list[dt.date]:
    """今天（含）往前 n 个周一至五（例行任务只在工作日跑；休市的工作日也算：日报照常做）。"""
    out, d = [], today
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out


def table(entries: list[tuple[dt.date, str]], today: dt.date, n: int = 5) -> list[str]:
    """最近 n 个工作日每天的日报 / 影子账户提交是谁做的（Mac / 云端 / —）。"""
    rows = []
    for d in weekdays_back(today, n):
        closed = not is_trading_day(d)
        sim = find("sim", entries, d) or "—"
        sh = find("shadow", entries, d) or ("—（休市不做）" if closed else "—")
        rows.append(f"{d}（周{WEEK[d.weekday()]}{'，休市' if closed else ''}）：日报 {sim}；影子账户 {sh}")
    return rows


def wake(sched: str, by: tuple[int, int] = WAKE_BY) -> tuple[bool | None, str]:
    """pmset -g sched 的「Repeating power events」里有没有工作日（或每天）by 之前的唤醒 / 开机（读法同 live_gate._wake）。"""
    rep = sched.split("Repeating power events:", 1)[1] if "Repeating power events:" in sched else ""
    rep = rep.split("Scheduled power events:", 1)[0]
    lines = [ln.strip() for ln in rep.splitlines() if "wake" in ln.lower() or "poweron" in ln.lower()]
    hm = f"{by[0]:02d}:{by[1]:02d}"
    if not lines:
        return False, f"没有设定：在终端运行 {WAKE_CMD}（要输入 Mac 的登录密码；Mac 接着电源、不合盖）"
    ln = lines[0]
    m = re.search(r"at\s+(\d{1,2}):(\d{2})\s*([AP]M)?", ln, re.I)
    days = ln.lower()
    if not m or not ("weekday" in days or "every day" in days):
        return None, f"有重复唤醒、读不出是不是工作日 {hm} 之前（{ln}）：请确认，或重设 {WAKE_CMD}"
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
    if ap:
        h = h % 12 + (12 if ap == "PM" else 0)
    if (h, mi) <= by:
        return True, f"已设定：{ln}"
    return False, (f"唤醒时间晚于 {hm}（{ln}）：本机日报 06:45 开始，Mac 那时还在睡 → 改成 {WAKE_CMD}"
                   "（取代原来的 07:30；立花执行器只要 07:40 之前）")


def _vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


def app(plist_path: str, need: str = APP_MIN) -> tuple[bool | None, str]:
    """Claude 桌面版的 Info.plist → 版本够不够（≥ need：有「本机任务」）。没有文件 → 没装。"""
    try:
        with open(plist_path, "rb") as f:
            v = str(plistlib.load(f).get("CFBundleShortVersionString") or "")
    except FileNotFoundError:
        return False, f"没装 Claude 桌面版：本机任务要它（≥ {need}；从 Claude 官网下载）"
    except Exception as e:                                    # noqa: BLE001
        return None, f"读不出桌面版的版本（{type(e).__name__}）：在桌面版的 关于 里看，要 ≥ {need}"
    if not _vtuple(v):
        return None, f"读不出桌面版的版本：在桌面版的 关于 里看，要 ≥ {need}"
    if _vtuple(v) >= _vtuple(need):
        return True, f"Claude 桌面版 {v}（≥ {need}：有本机任务）"
    return False, f"Claude 桌面版 {v} 低于 {need}（没有本机任务）：在桌面版里更新"


# ────────── 本机任务按时跑了没有 / 有没有卡住（桌面版的运行记录，只读）──────────
# 2026-10-16 发现：10-12 的三次本机运行停在第一条命令的权限确认上、没人点允许，进程一直挂着；桌面版在那次运行结束之前不再启动
# 同一个任务（scheduled-tasks.json 的 recordedSkips 每分钟记一条 per_task_limit）→ 10-13〜10-16 全靠云端后备，而 check 还说全部 OK。
# 桌面版的文件（格式不是公开接口，读不懂就跳过）：<运行记录目录>/<账户>/<组织>/scheduled-tasks.json
#   {"scheduledTasks": [{"id", "cronExpression"（本机时间）, "enabled", "createdAt"（毫秒）, "lastRunAt" / "lastScheduledFor"（ISO，UTC）…}],
#    "recordedSkips": {任务 id: [{"at"（毫秒）, "reason"}]}}；同一目录的 local_<uuid>.json = 每次运行的会话
#   {"scheduledTaskId", "createdAt", "lastActivityAt"（毫秒）, "isArchived", "permissionMode", "completedTurns", "cliSessionId"}；
#   对话记录 = <对话记录目录>/<工作文件夹编码>/<cliSessionId>.jsonl（最后一条消息是还没有结果的工具调用 = 停在那一步）。
GRACE = dt.timedelta(minutes=30)          # 到点之后多久还没跑算错过（桌面版每分钟检查、有几分钟错峰；Mac 06:40 才醒）
STUCK_AFTER = dt.timedelta(hours=2)       # 开始 2 小时后还停在同一处 = 卡住（季度复核最长的一步也远不到）
IDLE_S = 60                               # 没有对话记录时：最后动静离开始不到 60 秒、一轮也没做完 = 一开始就停住
SKIP_RECENT = dt.timedelta(hours=2)       # 桌面版最近 2 小时还在记「跳过」= 现在还被挡着
PROMPT_MODES = ("default", "acceptEdits", "plan")   # 要人确认的权限模式
_TAIL_BYTES = 262144


def _parse_ts(v) -> dt.datetime | None:
    """毫秒时间戳 / ISO 字符串（Z 或带时区）→ aware datetime；读不懂 → None。"""
    try:
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v, dt.timezone.utc)
        if isinstance(v, str) and v:
            t = dt.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=JST)
    except (ValueError, OverflowError, OSError):
        return None
    return None


def _md(t: dt.datetime) -> str:
    j = t.astimezone(JST)
    return f"{j.month}/{j.day}"


def _mdhm(t: dt.datetime) -> str:
    j = t.astimezone(JST)
    return f"{j.month}/{j.day} {j:%H:%M}"


def _cron_field(spec: str, lo: int, hi: int) -> set[int]:
    vals: set[int] = set()
    for part in spec.split(","):
        step, stepped = 1, "/" in part
        if stepped:
            part, s = part.split("/", 1)
            step = int(s)
            if step <= 0:
                raise ValueError(spec)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = int(part)
            b = hi if stepped else a                          # 「5/15」= 5 起每 15
        if a < lo or b > hi or a > b:
            raise ValueError(spec)
        vals.update(range(a, b + 1, step))
    return vals


def parse_cron(expr: str):
    """5 段的 cron（分 时 日 月 星期；星期 0 / 7 = 周日）→ (分, 时, 日, 月, 星期, 日是 *, 星期是 *)。读不懂 → ValueError。"""
    f = str(expr or "").split()
    if len(f) != 5:
        raise ValueError(expr)
    return (_cron_field(f[0], 0, 59), _cron_field(f[1], 0, 23), _cron_field(f[2], 1, 31), _cron_field(f[3], 1, 12),
            {d % 7 for d in _cron_field(f[4], 0, 7)}, f[2].startswith("*"), f[4].startswith("*"))


def fires_back(expr: str, now: dt.datetime, tz=None, days: int = 400):
    """now（含）之前 cron 的触发时刻，新的在前（aware）。cron 按本机时间（桌面版就是这样跑的）：tz 不给 = 本机时区（TZ 环境变量）。
    日和星期都限定时照 cron 的规矩取「或」。"""
    mi, hr, dom, mon, dow, dom_star, dow_star = parse_cron(expr)
    loc = now.astimezone(tz) if tz else now.astimezone()
    loc = loc.replace(tzinfo=None)
    times = sorted(((h, m) for h in hr for m in mi), reverse=True)
    d = loc.date()
    for _ in range(days):
        cd = (d.weekday() + 1) % 7
        dom_ok, dow_ok = d.day in dom, cd in dow
        if d.month in mon and ((dom_ok and dow_ok) if (dom_star or dow_star) else (dom_ok or dow_ok)):
            for h, m in times:
                naive = dt.datetime.combine(d, dt.time(h, m))
                if naive <= loc:
                    yield naive.replace(tzinfo=tz) if tz else naive.astimezone()
        d -= dt.timedelta(days=1)


def missed_runs(task: dict, now: dt.datetime, tz=None, grace: dt.timedelta = GRACE) -> list[dt.datetime] | None:
    """到点 + grace 已经过去、却在最后一次运行（lastRunAt / lastScheduledFor）之后的触发时刻（旧的在前）；读不懂 → None。
    每天 / 工作日的任务（日、月都是 *）只算东证的交易日（休市的工作日到点没跑不算错过）；季度复核之类按 cron 原样算。"""
    expr = task.get("cronExpression")
    try:
        f = str(expr or "").split()
        parse_cron(expr)
    except ValueError:
        return None
    marks = [t for t in (_parse_ts(task.get("lastRunAt")), _parse_ts(task.get("lastScheduledFor"))) if t]
    floor = max(marks) if marks else _parse_ts(task.get("createdAt"))
    if floor is None:
        return None
    every_day = f[2] == "*" and f[3] == "*"
    out: list[dt.datetime] = []
    for fire in fires_back(expr, now - grace, tz):
        if fire <= floor + dt.timedelta(minutes=1):
            break
        if every_day and not is_trading_day(fire.astimezone(JST).date()):
            continue
        out.append(fire)
        if len(out) >= 60:
            break
    return sorted(out)


def _transcript_tail(projects: Path, sid) -> tuple[bool, str, dt.datetime | None] | None:
    """对话记录最后一条消息：(停在还没有结果的工具调用上？, 工具名, 那条消息的时刻)；找不到 / 读不懂 → None。只读文件末尾。"""
    if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", sid):
        return None
    try:
        hits = sorted(projects.glob(f"*/{sid}.jsonl"))
    except OSError:
        return None
    if not hits:
        return None
    try:
        with open(hits[0], "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - _TAIL_BYTES))
            raw = fh.read()
    except OSError:
        return None
    lines = raw.decode("utf-8", "replace").splitlines()
    if size > _TAIL_BYTES:
        lines = lines[1:]                                     # 第一行可能只读到一半
    last, tools = None, []                                    # tools：最后一批还没有结果的工具调用（同时发的几个各占一条）
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if not (isinstance(e, dict) and e.get("type") in ("assistant", "user") and isinstance(e.get("message"), dict)):
            continue
        content = e["message"].get("content")
        calls = []
        if e.get("type") == "assistant" and isinstance(content, list):
            calls = [str(c.get("name") or "") for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
        if not calls:
            tools = []
        elif last is not None and last.get("type") == "assistant" and tools:
            tools = tools + calls
        else:
            tools = calls
        last = e
    if last is None:
        return None
    names = []
    for n in tools:
        n = re.sub(r"[^\w.-]", "", n)[:40]
        if n and n not in names:
            names.append(n)
    return bool(tools), "、".join(names[:4]), _parse_ts(last.get("timestamp"))


def _load_desktop(root: Path) -> tuple[dict, dict, list, str]:
    """运行记录目录 → (任务 id → 任务, 任务 id → 跳过记录, 会话列表, 问题说明（空 = 读到了）)。几个文件里都有同一个 id → 文件新的为准。"""
    try:
        files = sorted(root.glob("*/*/scheduled-tasks.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        files = []
    if not files:
        return {}, {}, [], "没有桌面版的运行记录（scheduled-tasks.json）"
    tasks: dict = {}
    skips: dict = {}
    dirs: list[Path] = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = data.get("scheduledTasks") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        rs = data.get("recordedSkips") if isinstance(data.get("recordedSkips"), dict) else {}
        for t in items:
            if isinstance(t, dict) and isinstance(t.get("id"), str):
                tasks[t["id"]] = t
                skips[t["id"]] = rs.get(t["id"]) if isinstance(rs.get(t["id"]), list) else []
        dirs.append(p.parent)
    if not dirs:
        return {}, {}, [], "桌面版的运行记录读不出 / 格式和预期不同"
    sessions = []
    for d in dirs:
        try:
            locs = sorted(d.glob("local_*.json"))
        except OSError:
            continue
        for p in locs:
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(j, dict) and isinstance(j.get("scheduledTaskId"), str):
                sessions.append(j)
    return tasks, skips, sessions, ""


NOT_LISTED = "桌面版的排程里没有这个任务（被删了 / 没建好）：在桌面版 Code → Routines 里看；要重建在对话里说"


def listed_ids(root) -> set | None:
    """最新的 scheduled-tasks.json（按修改时间）里的任务 id；读不到 / 格式不同 → None（不下结论）。
    2026-10-24 复核：~/.claude/scheduled-tasks/<id>/SKILL.md 还在、但桌面版的排程里已经没有这个任务（qbreak-shadow 就是这样）
    → 以前 check 照样写「已建」、这里只记「?」跳过；其实它再也不会跑。只读，只看 id。"""
    try:
        files = sorted(Path(root).glob("*/*/scheduled-tasks.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = data.get("scheduledTasks") if isinstance(data, dict) else None
        if isinstance(items, list):
            return {t["id"] for t in items if isinstance(t, dict) and isinstance(t.get("id"), str)}
    return None


def _stuck_runs(mine: list, projects, now: dt.datetime, procs: list | None = None) -> list[tuple[dt.datetime, str]]:
    """一个任务的会话里卡住的运行 → [(开始时刻, 停在哪里)]（旧的在前）：没归档、开始 2 小时以上，对话记录最后是还没有结果的工具调用
    （也已经 2 小时没动），或没有对话记录、开始几秒之后就没有动静、一轮也没做完。
    之后同一个任务又开始了运行的 → 不算（那次已经被停掉 / 结束了：桌面版只在上一次结束之后才启动下一次；2026-10-21 起）。
    procs（claude_procs 的结果；None = 不看进程）：那次运行的进程已经不在了 → 不算（被停掉 / 自动停止了；2026-10-21 起）。"""
    out = []
    last = max((_parse_ts(s.get("createdAt")) for s in mine if _parse_ts(s.get("createdAt"))), default=None)
    for s in mine:
        if s.get("isArchived") is True:
            continue
        if last is not None and (_parse_ts(s.get("createdAt")) or last) < last:
            continue
        if procs is not None and _proc_of(s, procs) is None:
            continue
        created = _parse_ts(s.get("createdAt"))
        if created is None or now - created < STUCK_AFTER:
            continue
        tail = _transcript_tail(Path(projects), s.get("cliSessionId") or s.get("sessionId"))
        if tail is not None:
            pending, tool, at = tail
            if not pending or now - (at or created) < STUCK_AFTER:
                continue
            where = f"停在工具调用（{tool}）上、没有结果" if tool else "停在工具调用上、没有结果"
        else:
            act = _parse_ts(s.get("lastActivityAt")) or created
            if s.get("completedTurns") or (act - created).total_seconds() > IDLE_S:
                continue
            where = "开始几秒之后就没有动静"
        out.append((created, where))
    return out


def _skips_after(t: dict, skips: dict, tid: str) -> list[tuple[dt.datetime, str]]:
    """桌面版在最后一次运行之后记的「跳过」[(时刻, 原因)]。"""
    floor = max([x for x in (_parse_ts(t.get("lastRunAt")), _parse_ts(t.get("lastScheduledFor"))) if x], default=None)
    recent = [(_parse_ts(x.get("at")), str(x.get("reason") or "")) for x in skips.get(tid, []) if isinstance(x, dict)]
    return [(a, r) for a, r in recent if a and (floor is None or a > floor)]


def desktop_report(root, projects, want: dict, now: dt.datetime, tz=None, procs: list | None = None) -> list[tuple[str, str]]:
    """本机任务（want：任务 id → 中文名）按时跑了没有、有没有卡住的运行 → [("OK"|"NG"|"WARN"|"?", 说明)]。只读；不打印路径、命令、内容。
    procs = claude_procs 的结果（None = 不看进程：进程已经不在的那次也照对话记录算）。"""
    tasks, skips, sessions, why = _load_desktop(Path(root))
    if why:
        return [("?", f"{why}：跳过「按时跑了没有」（在桌面版 Code → Routines → Review history 看）")]
    out: list[tuple[str, str]] = []
    prompt_mode: list[str] = []
    fix = "让它不再问：说明书里的命令都要一字不差地在允许规则里（见 routines/README.md）"
    listed = listed_ids(root)
    for tid, label in want.items():
        t = tasks.get(tid)
        if listed is not None and tid not in listed:          # 排程文件读到了、里面没有它（2026-10-24 复核）
            out.append(("NG", f"本机任务「{label}」：{NOT_LISTED}"))
            continue
        if t is None:
            out.append(("?", f"本机任务「{label}」：桌面版的运行记录里没有它（刚建 / 记录格式变了？）：跳过「按时跑了没有」"))
            continue
        mine = sorted((s for s in sessions if s.get("scheduledTaskId") == tid), key=lambda s: _parse_ts(s.get("createdAt")) or now)
        last_run = _parse_ts(t.get("lastRunAt"))
        recent = _skips_after(t, skips, tid)                  # 桌面版最近还在记的「跳过」（最后一次运行之后的）
        blocked = [a for a, r in recent if r == "per_task_limit"]
        blocked_now = bool(blocked) and max(blocked) >= now - SKIP_RECENT
        if t.get("enabled") is False:
            out.append(("NG", f"本机任务「{label}」在桌面版里是暂停的（Paused）：不会按时跑（没有云端后备）；"
                              "要恢复：桌面版 Code → Routines → 这个任务切到 Active"))
        else:
            miss = missed_runs(t, now, tz)
            lr = f"最后一次运行 {_mdhm(last_run)}" if last_run else "建好之后还没跑过"
            if miss is None:
                out.append(("?", f"本机任务「{label}」的时间表 / 运行时刻读不懂：跳过「按时跑了没有」（在桌面版 Code → Routines → Review history 看）"))
            elif miss:
                ndays = len({x.astimezone(JST).date() for x in miss})
                if len(miss) == 1:
                    span = _mdhm(miss[0])
                elif ndays == len(miss):
                    span = f"{_md(miss[0])}〜{_md(miss[-1])}"
                else:
                    span = f"{_mdhm(miss[0])}〜{_mdhm(miss[-1])}"
                out.append(("NG", f"本机任务「{label}」{lr}；之后应该跑的 {span} 没跑（{len(miss)} 次；"
                                  "错过的没有云端后备：要补在 Mac 对话里说「补跑」）"))
            else:
                out.append(("OK", f"本机任务「{label}」：{lr}（之后没有错过的）"))
        stuck = 0
        for created, where in _stuck_runs(mine, projects, now, procs):
            stuck += 1
            extra = "；之后到点的运行桌面版都跳过了（上一次运行还没结束）" if blocked_now else ""
            out.append(("NG", f"本机任务「{label}」{_mdhm(created)} 那次一直没动（{where}：多半在等权限确认、没人点允许）{extra}"
                              f" → 这次运行不结束，桌面版不会再启动这个任务：在桌面版 Code → Routines 打开那次运行、停止它；{fix}"))
        if not stuck and blocked_now:
            out.append(("NG", f"本机任务「{label}」：桌面版从 {_mdhm(min(blocked))} 起一直跳过它（上一次运行还没结束）"
                              f" → 在桌面版 Code → Routines 打开还没结束的那次运行、停止它；{fix}"))
        other = sorted({r for a, r in recent if r != "per_task_limit" and a >= now - SKIP_RECENT})
        if other:
            rs = "、".join(re.sub(r"[^\w-]", "", r)[:40] or "?" for r in other)
            out.append(("?", f"本机任务「{label}」最近被桌面版跳过（原因 {rs}）：在桌面版 Code → Routines → Review history 看"))
        if mine and str(mine[-1].get("permissionMode") or "") in PROMPT_MODES:
            at = _parse_ts(mine[-1].get("createdAt")) or now
            prompt_mode.append(f"{label} {_mdhm(at)}")
    if prompt_mode:
        which = "、".join(prompt_mode)
        out.append(("WARN", f"本机任务最近一次运行用的是要确认的权限模式（{which}）：无人值守时，"
                            "和允许规则对不上的第一条命令就会停下等确认、一直等着，之后到点的运行也被挡住 → "
                            "说明书里的命令都要一字不差地在允许规则里（见 routines/README.md）"))
    return out


# ────────── 09:30 自检的推送：本机任务今天卡住 / 没跑 / 晚了（2026-10-16；只读，读不到就什么都不说）──────────
# 用户今天把 ~/qbreak-sim 改回默认的逐项确认：和允许规则对不上的命令会停在权限确认、一直等着（10-12〜10-16 就这样）。
# routines.sh check 只在有人问时才看 → 交易日 09:30 自检的那条推送里加一行（不改自检的结论：不影响下单）。
KINDS = (("sim_daily", "日报"), ("shadow", "影子账户"), ("quarterly", "季度复核"))
DESKTOP_DEFAULT = "Library/Application Support/Claude/claude-code-sessions"   # 家目录下（routines.sh 同一个默认）
LATE_AFTER = GRACE                        # 今天的运行比到点晚这么久才开始 = 晚了（Mac 睡着 / 桌面版没开）
HISTORY_HINT = "在 Mac 对话里问「例行任务今天跑了吗」"


def desktop_dir() -> Path | None:
    """桌面版的运行记录目录：QBREAK_DESKTOP_DIR；没设 → 只在 macOS 上用默认的（别的系统 → None，不看）。"""
    v = os.environ.get("QBREAK_DESKTOP_DIR", "").strip()
    if v:
        return Path(v).expanduser()
    return Path.home() / DESKTOP_DEFAULT if sys.platform == "darwin" else None


def config_dir() -> Path:
    v = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return Path(v).expanduser() if v else Path.home() / ".claude"


def task_ids(cfg=None) -> dict:
    """说明书名（sim_daily / shadow / quarterly）→ 本机任务 id：<配置目录>/scheduled-tasks/<id>/SKILL.md 里写着 routines/<名>.md 的
    （routines.sh check 同一个找法：文件名排序的第一个）。只读、不打印内容；读不了 → 空。"""
    root = Path(cfg) if cfg is not None else config_dir()
    try:
        files = sorted((root / "scheduled-tasks").glob("*/SKILL.md"))
    except OSError:
        return {}
    out: dict = {}
    for p in files:
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for kind, _ in KINDS:
            if kind not in out and f"routines/{kind}.md" in body:
                out[kind] = p.parent.name
    return out


def _hm_jst(t: dt.datetime) -> str:
    return f"{t.astimezone(JST):%H:%M}"


def today_lines(now: dt.datetime, root=None, projects=None, cfg=None, tz=None, procs: list | None = None) -> list[str]:
    """交易日 09:30 自检推送里的「本机例行任务」行（一个任务最多一行；没问题 / 读不到 / 不是 Mac → []）：
    卡住的运行（2 小时以上停在没有结果的工具调用上 = 多半在等权限确认）或桌面版一直在跳过它（上一次运行还没结束）；
    今天到点 30 分钟以上还没跑；今天的运行比到点晚 30 分钟以上才开始。暂停（Paused）的不说（人自己停的；check 里报）。
    只读；不写路径、命令、内容。"""
    if root is None:
        root = desktop_dir()
        if root is None:
            return []
        if procs is None:
            procs = claude_procs(now)                         # 真的 Mac 上：进程已经不在的那次不算卡住
    cfg = Path(cfg) if cfg is not None else config_dir()
    projects = Path(projects) if projects is not None else cfg / "projects"
    ids = task_ids(cfg)
    if not ids:
        return []
    tasks, skips, sessions, why = _load_desktop(Path(root))
    if why:
        return []
    today = now.astimezone(JST).date()
    out: list[str] = []
    for kind, label in KINDS:
        tid = ids.get(kind)
        t = tasks.get(tid) if tid else None
        if not isinstance(t, dict) or t.get("enabled") is False:
            continue
        mine = sorted((s for s in sessions if s.get("scheduledTaskId") == tid), key=lambda s: _parse_ts(s.get("createdAt")) or now)
        stuck = _stuck_runs(mine, projects, now, procs)
        blocked = [a for a, r in _skips_after(t, skips, tid) if r == "per_task_limit"]
        if stuck or (blocked and max(blocked) >= now - SKIP_RECENT):
            since = stuck[0][0] if stuck else min(blocked)
            if since.astimezone(JST).date() == today:
                fix = "在桌面版 Code → Routines 打开那次运行点允许（或停止它）；今天的要补：在 Mac 对话里说「补跑」"
            else:
                fix = "在桌面版 Code → Routines 打开那次运行、停止它（不停止，之后到点也不会再跑）；今天的要补：在 Mac 对话里说「补跑」"
            out.append(f"本机例行任务：{label}卡住了（多半在等权限确认；{_mdhm(since)} 起）→ {fix}；{HISTORY_HINT}")
            continue
        expr = t.get("cronExpression")
        try:
            fire = next(fires_back(expr, now, tz), None)
            every_day = str(expr).split()[2:4] == ["*", "*"]
        except (ValueError, IndexError):
            continue
        if fire is None or fire.astimezone(JST).date() != today or now - fire < GRACE:
            continue                                          # 今天不该跑 / 还没到点 + 30 分钟
        if every_day and not is_trading_day(today):
            continue
        last = _parse_ts(t.get("lastRunAt"))
        sched = _parse_ts(t.get("lastScheduledFor"))
        lo = fire - dt.timedelta(minutes=1)
        ran = (last is not None and lo <= last <= now) or (sched is not None and lo <= sched <= now)
        if not ran:
            out.append(f"本机例行任务：{label}今天 {_hm_jst(fire)} 没跑（桌面版没开 / Mac 睡着？）→ 今天的要补：在 Mac 对话里说「补跑」；{HISTORY_HINT}")
        elif last is not None and last <= now and last - fire >= LATE_AFTER:
            out.append(f"本机例行任务：{label}今天 {_hm_jst(last)} 才开始（应在 {_hm_jst(fire)}：那时 Mac 睡着 / 桌面版没开 / 前一次运行还没结束？）"
                       f"→ 那之前执行器用的是旧的输入；{HISTORY_HINT}")
    return out


# ────────── 卡住的运行自动停止（2026-10-21 用户「现在 qbreak 好像停了，再发防止对策」）──────────
# 10/19 06:45 的日报停在一条说明书以外的命令（python -c）的权限确认上、没人点允许 → 这次运行一直不结束，桌面版之后到点都跳过它，
# 07:40 的执行器连着 3 天用旧的判断层 / 宏观输入、09:30 自检连着 3 天没通过；10/21 09:37 补跑的那次又停在 git diff 上 13 小时。
# → 每 15 分钟（liveu.sh news）查一次：本机任务最近一次运行停在没有结果的工具调用上 30 分钟以上、它的进程还在、而且进程没有子进程
#   （真的在跑命令时有子进程；等权限确认时没有）→ 停止那个进程（桌面版随后会再启动错过的 / 下次到点照常跑），推一条手机通知。
#   一个任务一天最多停 2 次（补跑又卡住也不来回停：之后照旧由 09:30 自检 / routines.sh check 报）；只停这三个本机任务的会话
#   （工作文件夹对得上的那个进程），不碰别的对话。记录：数据目录 out/routines_reap.json（只在本机）。
REAP_AFTER = dt.timedelta(minutes=30)
REAP_MAX_PER_DAY = 2
PROC_SLACK_S = 120                         # 进程开始时刻和会话 createdAt 差多少秒以内算同一个
_ETIME = re.compile(r"^(?:(?:(\d+)-)?(\d+):)?(\d+):(\d+)$")


def _etime_s(v: str) -> int | None:
    """ps 的 etime（[[天-]时:]分:秒）→ 秒；读不懂 → None。"""
    m = _ETIME.match(str(v).strip())
    if not m:
        return None
    d, h, mi, sec = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + sec


def _tool(name: str, default: str) -> str:
    return shutil.which(name) or default


def claude_procs(now: dt.datetime | None = None, run=None) -> list[dict] | None:
    """在跑的 Claude Code 会话进程（桌面版启动的，stream-json）→ [{pid, start, cwd, kids}]；列不出（ps 失败）→ None。只读。
    kids = 它的子进程数（在跑 Bash 命令时 ≥ 1；等权限确认时 0）。"""
    run = run or subprocess.run
    now = now or now_jst()
    try:
        p = run([_tool("ps", "/bin/ps"), "-axo", "pid=,ppid=,etime=,command="], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    rows = []
    for ln in str(p.stdout or "").splitlines():
        parts = ln.split(None, 3)
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2], parts[3]))
    out = []
    for pid, _, et, cmd in rows:
        exe = cmd.split(" --", 1)[0]                          # 可执行文件（路径里可能有空格）；外面包的 disclaimer 不算
        secs = _etime_s(et)
        if not (exe.endswith("/claude") and "stream-json" in cmd) or secs is None:
            continue
        cwd = None
        try:
            q = run([_tool("lsof", "/usr/sbin/lsof"), "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True, timeout=20)
            cwd = next((x[1:] for x in str(q.stdout or "").splitlines() if x.startswith("n")), None)
        except (OSError, subprocess.SubprocessError):
            pass
        out.append({"pid": pid, "start": now - dt.timedelta(seconds=secs), "cwd": cwd, "kids": sum(1 for r in rows if r[1] == pid)})
    return out


def _same_dir(a, b) -> bool:
    try:
        return os.path.realpath(str(a)) == os.path.realpath(str(b))
    except (OSError, ValueError):
        return False


def _proc_of(s: dict, procs: list) -> dict | None:
    """这次运行（会话）的进程：开始时刻差 2 分钟以内、工作文件夹一样（两边都知道时）。没有 → None。"""
    created = _parse_ts(s.get("createdAt"))
    if created is None:
        return None
    cwd = s.get("cwd")
    for p in procs:
        st = p.get("start")
        if not isinstance(st, dt.datetime) or abs((st - created).total_seconds()) > PROC_SLACK_S:
            continue
        if cwd and p.get("cwd") and not _same_dir(cwd, p["cwd"]):
            continue
        return p
    return None


def _terminate(pid: int, wait_s: float = 10) -> bool:
    """停止一个进程（先 SIGTERM，等不到再 SIGKILL）→ 停了没有。"""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    for _ in range(max(1, int(wait_s * 10))):
        time.sleep(0.1)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            break
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return True


def reap_path() -> Path:
    from . import paths
    return paths.out_dir() / "routines_reap.json"


def _reap_log(path: Path) -> list:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def reap(now: dt.datetime | None = None, root=None, projects=None, cfg=None, procs: list | None = None,
         dry: bool = False, kill=None, send=None, log_path=None) -> list[str]:
    """停止卡住的本机任务运行（见上面的说明）→ 做了什么（一条一行；没有 → []）。dry = 只说会停哪个（不停、不推、不记）。
    kill / send / procs / log_path：测试注入（默认 _terminate / qbreak.notify.send / claude_procs() / reap_path()）。只在 Mac 上做事。"""
    now = now or now_jst()
    if root is None:
        root = desktop_dir()
        if root is None:
            return []
    cfg = Path(cfg) if cfg is not None else config_dir()
    projects = Path(projects) if projects is not None else cfg / "projects"
    ids = task_ids(cfg)
    if not ids:
        return []
    tasks, _, sessions, why = _load_desktop(Path(root))
    if why:
        return []
    if procs is None:
        procs = claude_procs(now)
        if procs is None:
            return []
    log_path = Path(log_path) if log_path is not None else reap_path()
    hist = _reap_log(log_path)
    day = now.astimezone(JST).date().isoformat()
    out: list[str] = []
    for kind, label in KINDS:
        tid = ids.get(kind)
        mine = sorted((s for s in sessions if tid and s.get("scheduledTaskId") == tid), key=lambda s: _parse_ts(s.get("createdAt")) or now)
        if not mine or mine[-1].get("isArchived") is True:
            continue
        s = mine[-1]                                          # 最近一次运行（更早的那些桌面版已经结束了）
        created = _parse_ts(s.get("createdAt"))
        if created is None or now - created < REAP_AFTER:
            continue
        tail = _transcript_tail(projects, s.get("cliSessionId") or s.get("sessionId"))
        if tail is not None:
            pending, tool, at = tail
            since = at or created
            if not pending or now - since < REAP_AFTER:
                continue
            where = f"停在工具调用（{tool}）上、没有结果" if tool else "停在工具调用上、没有结果"
        else:
            act = _parse_ts(s.get("lastActivityAt")) or created
            if s.get("completedTurns") or (act - created).total_seconds() > IDLE_S:
                continue
            since, where = created, "开始几秒之后就没有动静"
        p = _proc_of(s, procs)
        if p is None or not p.get("cwd") or not s.get("cwd") or p.get("kids"):
            continue                                          # 进程不在 / 对不上工作文件夹 / 正在跑命令 → 不碰
        if sum(1 for x in hist if x.get("day") == day and x.get("kind") == kind) >= REAP_MAX_PER_DAY:
            continue
        mins = int((now - since).total_seconds() // 60)
        dur = f"{mins // 60} 小时 {mins % 60} 分钟" if mins >= 120 else f"{mins} 分钟"
        head = f"本机例行任务「{label}」{_mdhm(created)} 开始的那次{where}，已经 {dur}（多半在等权限确认、没人点允许）"
        if dry:
            out.append(f"{head} → 会自动停止（--dry：没停）")
            continue
        ok = bool((kill or _terminate)(int(p["pid"])))
        hist.append({"at": now.isoformat(timespec="seconds"), "day": day, "kind": kind, "started": created.isoformat(timespec="seconds"),
                     "where": where, "minutes": mins, "ok": ok})
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(json.dumps(hist[-60:], ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
        if ok:
            subject = f"qbreak 本机例行任务「{label}」卡住了：已自动停止"
            text = (f"{head} → 已自动停止（不停的话，之后到点的运行桌面版都会跳过）。桌面版随后会再启动错过的那次 / 下次到点照常跑。"
                    f"根治：桌面版 Code → Routines → 这个任务的权限改成跳过确认（Bypass permissions）；{HISTORY_HINT}")
        else:
            subject = f"qbreak 本机例行任务「{label}」卡住了：自动停止没成功"
            text = f"{head} → 自动停止没成功：在桌面版 Code → Routines 打开那次运行、停止它；{HISTORY_HINT}"
        out.append(f"{subject}：{text}")
        try:
            if send is None:
                from . import notify
                send = notify.send
            send(subject, text, level="warn")
        except Exception:                                     # noqa: BLE001 —— 推送失败不影响别的
            pass
    return out


# ────────── 允许规则够不够（2026-10-16；只读）──────────
# 无人值守的本机任务只有和允许规则对得上的 Bash 命令才自动执行，否则停在权限确认、一直等着（10-12〜10-16）。这里把说明书
# （sim_daily.md / shadow.md / quarterly.md 的命令、README.md 固定文字里的第 1 步）要运行的 Bash 命令逐条和
# ~/qbreak-sim/.claude/settings.local.json 的 permissions.allow（+ 桌面版里那个任务自己的 approvedPermissions）对照。
# 对照法（Claude Code 的规则，近似）：规则 = 一字不差，或以「:*」/「 *」结尾的前缀（* 也可以在中间 = 任意文字）；
# 用 && / || / ; / | 连起来的命令 → 整条一字不差地在规则里，或拆开之后每一段都对得上（cd 进 ~/qbreak-sim 里的那段不用规则）；
# 说明书里 <…> 占位的地方（提交信息里的日期）要规则在那里有 *。只打印对不上的命令（仓库里的文字），不打印规则文件的别的内容。
MANUALS = ("sim_daily", "shadow", "quarterly")
_CMD_HEAD = re.compile(r"^(cd ~/qbreak-sim|bash scripts/|git -C ~/qbreak-sim |git add |git commit |TZ=|echo ~/|until )")
_PLACEHOLDER = re.compile(r"<[^<>`]+>")
_SAMPLES = ("2026-10-16", "x y")
_OPS = ("&&", "||", ";", "|")


def _unquoted(s: str) -> str:
    """去掉引号里的部分（判断 <…> 是不是在引号外 = 说明书里「<参数>」之类的写法，不是要照抄的命令）。"""
    return re.sub(r"\"[^\"]*\"|'[^']*'", "", s)


def manual_commands(rdir=None) -> dict:
    """说明书名 → 它让本机任务运行的 Bash 命令（去重、按出现顺序）。说明书里 `…` 里以命令开头的（cd ~/qbreak-sim / bash scripts/ /
    git -C ~/qbreak-sim / TZ= / echo ~/ / until；「&& git commit …」接在上一段后面的也算），引号外有 <…> 或以「 X」结尾的（写法说明）不算；
    README.md 固定文字（``` 块）里「运行 …（」的命令算进每一个说明书。"""
    rdir = Path(rdir) if rdir is not None else Path(__file__).resolve().parent.parent / "routines"
    first: list[str] = []
    try:
        readme = (rdir / "README.md").read_text(encoding="utf-8")
    except OSError:
        readme = ""
    for block in re.findall(r"```\n(.*?)```", readme, re.S):
        for m in re.finditer(r"运行 (.+?)（", block):
            c = m.group(1).strip()
            if _CMD_HEAD.match(c) and c not in first:
                first.append(c)
    out: dict = {}
    for name in MANUALS:
        try:
            text = (rdir / f"{name}.md").read_text(encoding="utf-8")
        except OSError:
            continue
        cmds = list(first)
        for m in re.finditer(r"`([^`\n]+)`", text):
            c = m.group(1).strip()
            if c.startswith("&& "):
                c = c[3:].strip()
            if not _CMD_HEAD.match(c) or _PLACEHOLDER.search(_unquoted(c)) or re.search(r"\s[A-Z]$", c):
                continue
            if c not in cmds:
                cmds.append(c)
        out[name] = cmds
    return out


def split_top(cmd: str, ops=_OPS) -> list[str]:
    """在引号、$( … ) 之外的 && / || / ; / | 处拆开（2>&1 之类不拆）。"""
    parts, cur, i, q, depth = [], [], 0, "", 0
    while i < len(cmd):
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == q:
                q = ""
            i += 1
            continue
        if ch in "\"'":
            q = ch
        elif cmd.startswith("$(", i):
            depth += 1
            cur.append("$(")
            i += 2
            continue
        elif ch == ")" and depth:
            depth -= 1
        elif not depth:
            op = next((o for o in sorted(ops, key=len, reverse=True) if cmd.startswith(o, i)), None)
            if op:
                parts.append("".join(cur).strip())
                cur = []
                i += len(op)
                continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur).strip())
    return [p for p in parts if p]


def rule_matches(rule: str, cmd: str) -> bool:
    """Claude Code 的 Bash 规则（括号里那部分）对不对得上这条命令：一字不差 / 「前缀:*」/ 带 * 的（* = 任意文字；结尾的「 *」也认没有参数的）。
    带 && 之类的命令只认一字不差（前缀规则不放行连起来的命令）。"""
    rule, cmd = rule.strip(), cmd.strip()
    if rule == cmd:
        return True
    if len(split_top(cmd)) > 1:
        return False
    if rule.endswith(":*"):
        p = rule[:-2]
        return cmd == p or cmd.startswith(p + " ")
    if "*" not in rule:
        return False
    if rule.endswith(" *") and cmd == rule[:-2]:
        return True
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in rule)
    return re.fullmatch(rx, cmd, re.S) is not None


def _match_any(rules: list[str], cmd: str) -> bool:
    if "*" in rules:                                          # 规则「Bash」（不带括号）= 全部 Bash
        return True
    if _PLACEHOLDER.search(cmd):                              # <…> 换成两种不同的文字都要对得上（规则在那里有 *）
        return all(any(rule_matches(r, _PLACEHOLDER.sub(x, cmd)) for r in rules) for x in _SAMPLES)
    return any(rule_matches(r, cmd) for r in rules)


def _cd_ok(part: str) -> bool:
    """cd 进 ~/qbreak-sim 里面（本机任务的工作文件夹）：Claude Code 不用规则。"""
    return re.fullmatch(r"cd ~/qbreak-sim(/[\w./-]*)?", part.strip()) is not None


def missing_parts(cmd: str, rules: list[str]) -> list[str]:
    """一条说明书命令里对不上任何规则的那几段（整条对得上 / 每段都对得上 → []）。"""
    if _match_any(rules, cmd):
        return []
    rest = cmd
    while True:
        m = re.match(r"cd ~/qbreak-sim(/[\w./-]*)?\s*&&\s*", rest)
        if not m:
            break
        rest = rest[m.end():]
    if rest != cmd and _match_any(rules, rest):
        return []
    out = []
    for part in split_top(rest, ("&&",)):
        if _cd_ok(part) or _match_any(rules, part):
            continue
        sub = split_top(part)
        if len(sub) > 1 and all(_cd_ok(x) or _match_any(rules, x) for x in sub):
            continue
        out.append(part)
    return out


def settings_path() -> Path:
    v = os.environ.get("QBREAK_SIM_SETTINGS", "").strip()
    if v:
        return Path(v).expanduser()
    sim = os.environ.get("QBREAK_SIM", "").strip()
    return (Path(sim).expanduser() if sim else Path.home() / "qbreak-sim") / ".claude" / "settings.local.json"


def _bash_rule(r) -> str | None:
    """「Bash(…)」→ 括号里的；「Bash」→ "*"（全部）；别的工具 → None。"""
    if not isinstance(r, str):
        return None
    r = r.strip()
    if r == "Bash":
        return "*"
    m = re.fullmatch(r"Bash\((.*)\)", r, re.S)
    return m.group(1) if m else None


def load_rules(path=None) -> tuple[list[str] | None, str]:
    """settings.local.json 的 permissions.allow 里的 Bash 规则 → (规则, 问题说明)；没有文件 / 读不懂 → (None, 说明)。不打印内容。"""
    p = Path(path) if path is not None else settings_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "没有 ~/qbreak-sim/.claude/settings.local.json（允许规则）"
    except (OSError, ValueError):
        return None, "~/qbreak-sim/.claude/settings.local.json 读不懂（不是 JSON？）"
    allow = ((data.get("permissions") or {}).get("allow") if isinstance(data, dict) and isinstance(data.get("permissions"), dict)
             else None)
    if not isinstance(allow, list):
        return [], ""
    return [x for x in (_bash_rule(r) for r in allow) if x is not None], ""


def task_rules(root=None, cfg=None) -> dict:
    """说明书名 → 桌面版里那个本机任务自己的 approvedPermissions（Bash 的）。读不到 → 空。"""
    if root is None:
        root = desktop_dir()
    ids = task_ids(cfg)
    if root is None or not ids:
        return {}
    tasks, _, _, why = _load_desktop(Path(root))
    if why:
        return {}
    out: dict = {}
    for kind, tid in ids.items():
        ap = (tasks.get(tid) or {}).get("approvedPermissions")
        rules = []
        for x in ap if isinstance(ap, list) else []:
            if isinstance(x, dict) and x.get("toolName") == "Bash":
                c = x.get("ruleContent")
                rules.append(c if isinstance(c, str) and c.strip() else "*")
        out[kind] = rules
    return out


def allow_missing(rdir=None, path=None, root=None, cfg=None) -> tuple[list[tuple[str, list[str]]] | None, str]:
    """说明书要运行、允许规则里却对不上的命令段 → ([(命令段, [哪几个说明书])], 问题说明)；没有规则文件 → (None, 说明)。"""
    rules, why = load_rules(path)
    if rules is None:
        return None, why
    per_task = task_rules(root, cfg)
    miss: dict = {}
    for name, cmds in manual_commands(rdir).items():
        rs = rules + per_task.get(name, [])
        for c in cmds:
            for part in missing_parts(c, rs):
                miss.setdefault(part, [])
                if name not in miss[part]:
                    miss[part].append(name)
    return list(miss.items()), ""


def suggest_rule(part: str) -> str:
    """对不上的命令段 → 要加的规则（「Bash(…)」）：一字不差；有 <…> 占位的 → 占位前面到最后一个空格为止的前缀 + 「 *」。"""
    m = _PLACEHOLDER.search(part)
    if m:
        head = part[:m.start()]
        cut = head.rstrip().rfind(" ")
        head = head[:cut] if cut > 0 else head.rstrip()
        return f"Bash({head.rstrip()} *)"
    return f"Bash({part})"


def _now_arg() -> dt.datetime:
    v = os.environ.get("QBREAK_ROUTINES_NOW", "").strip()          # 测试用（ISO；不带时区 = JST）
    return (_parse_ts(v) if v else None) or now_jst()


def _today(arg: str | None) -> dt.date:
    return dt.date.fromisoformat(arg) if arg else now_jst().date()


def _mark(ok: bool | None) -> str:
    return {True: "OK", False: "NG"}.get(ok, "?")


def main(argv: list[str] | None = None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    cmd = a.pop(0) if a else ""
    if cmd == "day":
        d = _today(a[0] if a else None)
        print(d.isoweekday(), 1 if is_trading_day(d) else 0)
        return 0
    if cmd == "done" and len(a) >= 2 and a[0] in ("shadow", "quarterly", "sim"):
        w = find(a[0], parse_log(sys.stdin.read()), _today(a[1]))
        if w:
            print(w)
            return 0
        return 1
    if cmd == "who":
        print(who(sys.stdin.readline().strip()))
        return 0
    if cmd == "wake":
        by = WAKE_BY
        if a:
            h, _, m = a[0].partition(":")
            by = (int(h), int(m or 0))
        ok, txt = wake(sys.stdin.read(), by)
        print(f"{_mark(ok)}\t{txt}")
        return 0
    if cmd == "app" and a:
        ok, txt = app(a[0], a[1] if len(a) > 1 else APP_MIN)
        print(f"{_mark(ok)}\t{txt}")
        return 0
    if cmd == "local":
        mine, _, theirs = sys.stdin.read().partition("--origin--")
        print(classify_local(parse_log(mine), parse_log(theirs)))
        return 0
    if cmd == "listed" and len(a) >= 2:                     # routines.sh check：这个任务 id 在桌面版的排程里吗 → 1 / 0 / ?
        ids = listed_ids(a[0])
        print("?" if ids is None else ("1" if a[1] in ids else "0"))
        return 0
    if cmd == "desktop" and len(a) >= 3:
        want = {}
        for spec in "\n".join(a[2:]).splitlines():
            tid, _, label = spec.strip().partition("=")
            if tid:
                want[tid] = label or tid
        now = _now_arg()
        for mark, txt in desktop_report(a[0], a[1], want, now, procs=None if os.environ.get("QBREAK_ROUTINES_NOW") else claude_procs(now)):
            print(f"{mark}\t{txt}")
        return 0
    if cmd in ("allow-missing", "allow-check"):
        miss, why = allow_missing()
        if cmd == "allow-missing":                            # 要加进 ~/qbreak-sim/.claude/settings.local.json 的规则（用户同意后由 Claude 加）
            print(json.dumps([] if miss is None else list(dict.fromkeys(suggest_rule(p) for p, _ in miss)), ensure_ascii=False, indent=1))
            if miss is None:
                print(why, file=sys.stderr)
            return 0 if miss is not None else 1
        if miss is None:
            print(f"?\t允许规则：{why}：跳过「说明书的命令在不在允许规则里」（本机任务的权限模式要确认时，每条命令都会停下等）")
        elif not miss:
            n = sum(len(v) for v in manual_commands().values())
            print(f"OK\t允许规则：说明书要运行的命令（{n} 条）都对得上（~/qbreak-sim/.claude/settings.local.json + 任务自己允许过的）")
        else:                                                 # 文件夹记的「跳过全部确认」管不到本机任务（2026-10-21 查到：运行用 --permission-mode=default）
            label = dict(KINDS)
            for part, names in miss:
                who_ = "、".join(label.get(x, x) for x in names)
                print(f"NG\t允许规则里没有（{who_}；无人值守时会停在权限确认）：{part}")
            print("HINT\t→ 加规则：在 Mac 对话里说「把例行任务缺的允许规则加上」（你同意后由 Claude 加进 ~/qbreak-sim/.claude/settings.local.json；"
                  "要加的见 python -m qbreak.routines allow-missing）")
        return 0
    if cmd == "reap":                                        # liveu.sh news（每 15 分钟）调用；--dry = 只说会停哪个
        for x in reap(dry="--dry" in a):
            print(x)
        return 0
    if cmd == "table" and a:
        print("\n".join(table(parse_log(sys.stdin.read()), _today(a[0]), int(a[1]) if len(a) > 1 else 5)))
        return 0
    print(__doc__.split("命令", 1)[1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
