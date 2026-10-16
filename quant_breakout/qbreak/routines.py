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
  python -m qbreak.routines desktop <运行记录目录> <对话记录目录> <任务 id=名字（一行一个）>
                                                            → 「OK|NG|WARN|?<TAB>说明」一行一条：本机任务按时跑了没有、有没有卡住的运行
                                                              （桌面版的 scheduled-tasks.json / local_*.json / 对话记录；只读；现在 = QBREAK_ROUTINES_NOW 或真的现在）
"""
from __future__ import annotations

import datetime as dt
import json
import os
import plistlib
import re
import sys
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


def desktop_report(root, projects, want: dict, now: dt.datetime, tz=None) -> list[tuple[str, str]]:
    """本机任务（want：任务 id → 中文名）按时跑了没有、有没有卡住的运行 → [("OK"|"NG"|"WARN"|"?", 说明)]。只读；不打印路径、命令、内容。"""
    tasks, skips, sessions, why = _load_desktop(Path(root))
    if why:
        return [("?", f"{why}：跳过「按时跑了没有」（在桌面版 Code → Routines → Review history 看）")]
    out: list[tuple[str, str]] = []
    prompt_mode: list[str] = []
    fix = "让它不再问：说明书里的命令都要一字不差地在允许规则里（见 routines/README.md）"
    for tid, label in want.items():
        t = tasks.get(tid)
        if t is None:
            out.append(("?", f"本机任务「{label}」：桌面版的运行记录里没有它（刚建 / 记录格式变了？）：跳过「按时跑了没有」"))
            continue
        mine = sorted((s for s in sessions if s.get("scheduledTaskId") == tid), key=lambda s: _parse_ts(s.get("createdAt")) or now)
        last_run = _parse_ts(t.get("lastRunAt"))
        floor = max([x for x in (last_run, _parse_ts(t.get("lastScheduledFor"))) if x], default=None)
        # 桌面版最近还在记的「跳过」（最后一次运行之后的）
        recent = [(_parse_ts(x.get("at")), str(x.get("reason") or "")) for x in skips.get(tid, []) if isinstance(x, dict)]
        recent = [(a, r) for a, r in recent if a and (floor is None or a > floor)]
        blocked = [a for a, r in recent if r == "per_task_limit"]
        blocked_now = bool(blocked) and max(blocked) >= now - SKIP_RECENT
        if t.get("enabled") is False:
            out.append(("NG", f"本机任务「{label}」在桌面版里是暂停的（Paused）：不会按时跑（云端后备会做）；"
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
                                  "错过的只能靠云端后备，见下面「最近 5 个工作日」）"))
            else:
                out.append(("OK", f"本机任务「{label}」：{lr}（之后没有错过的）"))
        stuck = 0
        for s in mine:
            if s.get("isArchived") is True:
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
    if cmd == "desktop" and len(a) >= 3:
        want = {}
        for spec in "\n".join(a[2:]).splitlines():
            tid, _, label = spec.strip().partition("=")
            if tid:
                want[tid] = label or tid
        for mark, txt in desktop_report(a[0], a[1], want, _now_arg()):
            print(f"{mark}\t{txt}")
        return 0
    if cmd == "table" and a:
        print("\n".join(table(parse_log(sys.stdin.read()), _today(a[0]), int(a[1]) if len(a) > 1 else 5)))
        return 0
    print(__doc__.split("命令", 1)[1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
