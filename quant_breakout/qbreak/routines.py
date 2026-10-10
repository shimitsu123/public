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
"""
from __future__ import annotations

import datetime as dt
import plistlib
import re
import sys

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
    if cmd == "table" and a:
        print("\n".join(table(parse_log(sys.stdin.read()), _today(a[0]), int(a[1]) if len(a) > 1 else 5)))
        return 0
    print(__doc__.split("命令", 1)[1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
