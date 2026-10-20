"""watchdog.py — 09:30 自检：死人开关的本机一半 + 每个工作日推一条到手机（只看、只提醒；不下单、不改账本）。

LaunchAgent com.qbreak.watchdog（周一至五 09:30，scripts/install_launchd_watchdog.sh）→ scripts/liveu.sh watchdog → run.py live-watchdog。
- 看装的是哪种：<LaunchAgents>/com.qbreak.liveu.morning.plist 在 → 立花本番的账本（tachibana）；com.qbreak.liveu.paper.plist 在 →
  模拟账户（paper）；两个都在（install_launchd_live_u.sh both，2026-10-17）→ 两个账本各查一次、各推一条；都不在 → 只打印、不发。
- 每个工作日推一条（2026-10-14 用户「不用做 healthchecks.io 心跳 check，改为每天用 qbreak 进行推送就可以」：代替外部心跳）：
  通过 →「✓ HH:MM 自检通过」（info；决策日、今天的单几笔成交 / 挂着）；平日休市 →「今天休市（系统正常）」；模拟期开始前 → 说明；
  同一个账本同一天只推一次（qbreak/notify_seen.py：「再自检一次」/ 补跑不再推）；早些时候没通过、现在通过 → 再推一次；
  那条没推到手机（失败 / 没有通道）→ 同一天再自检时再推。
  推送时设置了的通道都没发成（网络抖动等）→ 60 秒后重推一次（只一次；2026-10-14 复核）；还不行 → 结果文件记 failed、面板 / 菜单栏 ★
  （自动的自检一天只跑 09:30 那一次：当天不会自动再推，要再推 → 在 Mac 对话里说「再自检一次」）。
  哪个工作日 09:30 左右没收到 → Mac 多半关机 / 睡着 / 断网（那时 qbreak 推不出来，靠你发现「今天没收到」）。周末不推。
- 交易日：今天早上的运行跑完了（账本处理到上一个交易日、这个决策没有 PLANNED / BLOCKED 的单）、没有状态不明的单、（立花）没有留到
  现在的开盘后买单（DEFERRED）→ 通过；否则 → 手机通知（warn，每次；标题「★ HH:MM 自检没通过」是真的运行时刻）+ Mac 通知，原因写清
  （执行器停下的原因读运行状态文件 out/live_unified_<账本>_run.json，qbreak/run_status.py）。
- HALT 存在：不算失败；「HALT 生效中」同一天只推一次，这一条就是当天的推送（不再另推「通过」；没推到手机 → 再自检时再推）。
- 模拟账户在模拟期开始日（sim.json 的 start）之前不推进：不算失败。
- 今天的模拟盘日报入库了吗（2026-10-09 起例行任务在 Mac 的 Claude 桌面版本机任务里跑，云端同名例行任务是后备）：交易日、
  仓库（~/qbreak-src，paths.PROJECT_ROOT）的 var/out/unified_today.json 的 date ≠ 今天 → 原因「今天的模拟盘日报没入库（…）」
  （07:40 的执行器用的是旧的判断层 / 宏观数值）；模拟期开始前 / 结束后、这个文件不在（不是仓库的克隆）→ 不报。两种账本都看。
- 本机例行任务（2026-10-16 起；Claude 桌面版的本机任务，qbreak/routines.py today_lines）：交易日判定时看桌面版的运行记录，
  卡住了（多半在等权限确认）/ 今天到点 30 分钟还没跑 / 今天晚 30 分钟以上才开始 → 当天那条推送里加「★ 本机例行任务：…」一行
  （通过的标题后面加「· ★ 本机例行任务」）。**不改结论**（不算没通过）：例行任务不下单；真影响执行器的
  「今天的日报没入库」上面已经算没通过。不另推、不改同一天只推一次的规矩（那条已经推过 → 不为它再推）；结果文件记 routines。
  读不到 / 不是 Mac / 出错 → 什么都不说（不影响自检）。
- 执行器正在运行（拿着运行锁；例：Mac 睡着错过 07:40，醒来时 launchd 把错过的任务和自检一起拉起）→ 等它结束再判定（最多 10 分钟）；
  还在跑 → 这次不判定，推一条 warn「自检判定不了：执行器已经跑了 N 分钟」（同一天只一次；2026-10-14 起，以前一声不响；
  今天已经判定过 → 不推、不盖掉）。
  （scripts/liveu.sh watchdog 在这之前先看 liveu.sh run 的运行标记：拉代码 / 等云端也算在跑；跑完之后让 Mac 醒着到 09:35 的那段不算 ——
  以前按进程名看，一直等到 09:35；2026-10-14 G24）
- 该下了还没下的手动指令（盘中 / 开盘该下的买卖、闲置资金比例；过了该下的时刻 10 分钟以上）→ 原因（面板没开 / 自动下单暂停 /
  早上的运行没完成；2026-10-14 G24）。
- 写 out/watchdog_<账本>.json（at、ok、reasons、halt、note、push）：面板 / 手机顶部、菜单栏显示今天的结果与推送发成没有
  （push：{at, state: sent / failed / none, why}；none = 没有能推到手机的通道）。
- 外部心跳（可选，2026-10-14 起不用、不再推荐）：钥匙串 qbreak-heartbeat 有地址时照旧 ping（成功 / 「地址/fail」），结果记 heartbeat
  （{at, state: sent / failed, why}；why 不含地址），没发成 → 手机 + Mac 通知同一天只一次；没设置 = 正常，什么都不说、不记。
- 自检程序自己出错（代码的 bug 等；2026-10-14 复核：以前只写日志，当天没有推送，看起来和 Mac 关机一样）→ 推一条 warn「★ HH:MM 自检出错」
  （只写异常的类型名；同一天只一次）+ Mac 通知；今天还没有判定结果 → 结果文件写 ok = None（面板 / 菜单栏 ★）。
- 发出去的文字（手机通知 / 心跳）里的本机路径换成「数据目录」/「~」（不带 Mac 的用户名）。
- dry=True（liveu.sh watchdog --dry）：只判定、打印；不写结果文件、不推送、不等运行锁。
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from . import paths
from .calendar_jp import JST, is_trading_day, now_jst, prev_trading_day
from .utils import atomic_write_text, setup_logging

log = setup_logging("watchdog")

LIVE_PLIST, PAPER_PLIST = "com.qbreak.liveu.morning", "com.qbreak.liveu.paper"
LABEL = "com.qbreak.watchdog"
JUDGE_FROM = dt.time(9, 0)          # 这之前早上的运行（07:40〜08:55）可能还在进行：不判定
OPEN_DONE = dt.time(9, 25)          # 这之后 09:05 / 09:20 的开盘后补单应该已经跑完
ESHITEN_SP = "https://kabuka.e-shiten.jp/mfds_smp.php"     # 立花 e支店的手机网站（注文一覧在这里看）
HALT_KEY = "09:30 自检：HALT 生效中"                          # 去重用的固定文字（同一天只提醒一次）
BEAT_KEY = "09:30 自检：外部心跳没发成"                        # 同上（2026-10-14 G12）
DAILY_KEY = "09:30 自检：每个工作日的推送"                     # 同上：通过 / 休市 / 模拟期开始前的推送（2026-10-14 代替外部心跳）
STUCK_KEY = "09:30 自检：执行器一直在跑，判定不了"             # 同上
CRASH_KEY = "09:30 自检：出错"                                # 同上：自检程序自己出错（2026-10-14 复核）
DAILY_LINE = "每个工作日 09:30 左右推一条；哪天没收到 → Mac 多半关机 / 睡着 / 断网"
PUSH_FIX = ("iPhone 从主屏幕的 qbreak 图标打开面板 →「更多 → 通知（推送）」→「在这台设备打开推送」→ 允许"
            "（iPhone 设置里也要允许 qbreak 的通知）；每条也记在面板「消息 → 通知记录」")
RETRY_S = 60                        # 推送没发成（设置了的通道都失败：网络抖动等）→ 等这么久再推一次（只一次；2026-10-14 复核）
FAIL_FIX = ("今天不会自动再推；要再推一次 → 在 Mac 对话里说「再自检一次」（明天 09:30 照常推）；"
            "连着几天都这样 → 在 Mac 对话里说「看一下自检日志」")
BEAT_RESAVE = ("在「终端」App 重新存一次：security add-generic-password -U -s qbreak-heartbeat -a qbreak -w"
               "（回车后输入地址；不要贴进聊天）；不用外部心跳了就删掉：security delete-generic-password -s qbreak-heartbeat -a qbreak")
LOCK_WAIT_S, LOCK_POLL_S = 600, 15                            # 执行器正在运行：最多等 10 分钟、每 15 秒看一次
DAILY_FILE = paths.PROJECT_ROOT / "var" / "out" / "unified_today.json"   # 例行任务入库的当天日报（执行器 07:40 git pull 之后读；测试换成临时文件）
DAILY_REASON = "今天的模拟盘日报没入库（Mac 的本机例行任务没跑？桌面版开着吗？）"
DAILY_UNPULLED = "今天的模拟盘日报已入库，但这台 Mac 的 ~/qbreak-src 没拉到"


ROUTINE_TAG = " · ★ 本机例行任务"                              # 通过的推送标题后面加的（今天本机例行任务卡住 / 没跑 / 晚了）


def _routine_lines(now: dt.datetime) -> list[str]:
    """今天本机例行任务的问题（qbreak/routines.py today_lines；只读）。读不到 / 出错 → []（绝不让自检出错）。"""
    try:
        from .routines import today_lines
        return [str(x) for x in today_lines(now)][:3]
    except Exception as e:                                    # noqa: BLE001
        log.warning("本机例行任务的状态没读成（不影响自检）：%s", type(e).__name__)
        return []


def _with_routines(text: str, r: dict, bullet: str = "★ ") -> str:
    """推送正文的最后（DAILY_LINE 之前）加「★ 本机例行任务：…」几行。"""
    rt = r.get("routines") or []
    if not rt:
        return text
    extra = "\n".join(f"{bullet}{x}" for x in rt)
    if text.endswith(DAILY_LINE):
        return text[:-len(DAILY_LINE)] + extra + "\n" + DAILY_LINE
    return text + "\n" + extra


def installed(agents) -> str | None:
    """装的是哪种执行器：立花本番 → "tachibana"；模拟操盘 → "paper"；都没装 → None（两个都装 → 立花；全部见 installed_all）。"""
    tags = installed_all(agents)
    return tags[0] if tags else None


def installed_all(agents) -> list[str]:
    """装了的执行器（立花在前）：两个都装（install_launchd_live_u.sh both）→ ["tachibana", "paper"]。"""
    agents = Path(agents)
    return [t for t, f in (("tachibana", LIVE_PLIST), ("paper", PAPER_PLIST)) if (agents / f"{f}.plist").exists()]


def path(tag: str) -> Path:
    return paths.out_dir() / f"watchdog_{tag}.json"


def _halt() -> str | None:
    p = paths.halt_file()
    if not p.exists():
        return None
    try:
        return (p.read_text(encoding="utf-8", errors="replace").splitlines() or ["HALT"])[0][:160] or "HALT"
    except OSError:
        return "HALT"


def _sim_start() -> str | None:
    """模拟期开始日（执行器读的数据目录 sim.json 的 start；liveu.sh 每次运行前从仓库拷过来）。读不了 → None。"""
    from .utils import read_json
    try:
        v = (read_json(paths.home() / "sim.json", {}) or {}).get("start")
        return str(dt.date.fromisoformat(str(v))) if v else None
    except (ValueError, TypeError, AttributeError):
        return None


def _daily_missing(today: dt.date) -> str | None:
    """今天的模拟盘日报没入库 → 原因；入库了 / 文件不在（不是仓库的克隆）/ 模拟期开始前 / 结束后 → None。只读。
    模拟期读数据目录的 sim.json（liveu.sh 从仓库拷过来）；没有就读仓库的 var/sim.json。"""
    from . import run_status as RS
    if not DAILY_FILE.exists():
        return None
    cfg = RS.peek_json(paths.home() / "sim.json")
    if cfg is None:
        cfg = RS.peek_json(DAILY_FILE.parent.parent / "sim.json") or {}
    day = today.isoformat()
    start, end = str(cfg.get("start") or "")[:10], str(cfg.get("end") or "")[:10]
    if (start and day < start) or (end and day > end):
        return None
    d = str((RS.peek_json(DAILY_FILE) or {}).get("date") or "")
    if d == day:
        return None
    if _remote_daily_date() == day:                         # 远端有了、工作区没有：不是例行任务没跑，是这个克隆没拉到
        return (f"{DAILY_UNPULLED}（git pull 失败——有本地改动？——或日报入库晚于早上最后一次拉取 08:35）：工作区最新的是 {d or '—'}，"
                "07:40 的执行器用的是旧的判断层 / 宏观数值（在 Mac 对话里说「检查本地仓库」→ bash scripts/dev.sh check）")
    return f"{DAILY_REASON}：仓库里最新的是 {d or '—'}（07:40 的执行器用的是旧的判断层 / 宏观数值；在 Mac 对话里问「例行任务今天跑了吗」）"


def _remote_daily_date(run=None) -> str | None:
    """远端（这个克隆上次 git fetch / pull 拿到的 @{u}；pull 合并失败时 fetch 也已经做了）里日报的日期。只读；读不了 → None。"""
    import json
    import subprocess
    root = DAILY_FILE.parent.parent.parent                  # var/out/unified_today.json → quant_breakout/
    try:
        r = (run or subprocess.run)(["git", "-C", str(root), "show", "@{u}:./var/out/unified_today.json"],
                                    capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return str((json.loads(r.stdout or "{}") or {}).get("date") or "") or None
    except (ValueError, AttributeError):
        return None


def _olab(o: dict) -> str:
    """「1482 对冲版美国 7〜10 年国债 买 678 口」（代码 + 名字、口 / 股；2026-10-15 用户：只写代码不知道是哪只）。"""
    from .names import label
    unit = "口" if o.get("kind") == "core" else "股"
    return (f"{label(o.get('ticker')) if o.get('ticker') else '—'} {'买' if o.get('side') == 'BUY' else '卖'} "
            f"{int(o.get('sent_qty') or o.get('qty') or 0):,} {unit}")


def _otext(o: dict) -> str:
    from . import run_status as RS
    from .names import annotate
    st = {**RS.STATUS_TEXT, "PLANNED": "还没发"}.get(o.get("status"), str(o.get("status")))
    note = annotate(str(o.get("note") or ""))                # 以前写下的说明只有代码 → 补名字
    return f"{_olab(o)} {st}" + (f"：{note}" if note else "")


def _manual_unsent(book: dict, exp: str, today: dt.date, done: bool) -> list[str]:
    """决策 exp 里没发出的手动指令的单（被挡 / 被拒；HALT 不算；G7，2026-10-14）：早上的运行跑完（morning_done）时被拒的单
    以前一声不响 → 列出来（没跑完时上面「有 N 笔没下」已经逐笔列了）；同一条指令连续 2 个成交日以上没发出（指令的 unsent，
    执行器下单时记）→ ★。"""
    from . import manual_orders as MO
    from . import run_status as RS
    from .live_ops import MANUAL_REASONS, _manual_item
    bad = [o for o in book.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == exp
           and o.get("reason") in MANUAL_REASONS and o.get("status") in ("BLOCKED", "REJECTED")
           and o.get("phase") != "now" and not RS.is_halt(o)]        # 只认 HALT 的说明开头（没 ARM 的说明里也有「HALT」字样；2026-10-14 复核）
    out = []
    if done and bad:
        out.append(f"决策 {exp} 有 {len(bad)} 笔手动指令的单没发出：" + "；".join(_otext(o) for o in bad[:5])
                   + ("…" if len(bad) > 5 else ""))
    seen = set()
    for o in bad:
        it = _manual_item(book, o) or {}
        u = it.get("unsent") or {}
        n = int(u.get("n") or 0) if str(u.get("last") or "") == today.isoformat() and not u.get("halt") else 0
        if n >= 2 and it.get("id") not in seen:
            seen.add(it.get("id"))
            out.append(f"★ 手动指令 {it.get('id')}（{MO.describe(it)}）连续 {n} 个交易日没发出（{u.get('why') or '被挡'}）："
                       "在 Mac 对话里看一下原因；不要了就在面板撤回")
    return out


MANUAL_GRACE_S = 600                # 手动指令过了该下的时刻这么久还没下 → 自检报（G24）


def _due_at(at, today: dt.date) -> dt.datetime | None:
    """一条手动指令今天最晚该在什么时刻下（G24）：live_ops.instr_due（outlook 同一个口径；2026-10-15）。"""
    from .live_ops import instr_due
    return instr_due(at, today)


def _manual_waiting(tag: str, book: dict, now: dt.datetime, done: bool) -> list[str]:
    """该下了还没下的手动指令（G24；2026-10-14）：盘中 / 开盘该下的买卖（执行器读了还在等的，或面板叫的执行器根本没读到的；
    闲置资金比例、固定口数没读到的也算），过了该下的时刻 10 分钟以上 → 一条原因（面板没开 / 自动下单暂停 / 早上的运行没完成…）。
    「明天开盘」、等上一笔成交、「全部换成」整批、撤回中的不算；盘中正在一会儿再试（取不到现价等，面板上写着）的不算。"""
    from . import manual_orders as MO
    from . import run_status as RS
    from .live_ops import wrote
    today = now.date()
    td = today.isoformat()
    items = (book.get("manual") or {}).get("items") or {}
    rows: list[tuple[dict, str]] = []
    for it in items.values():
        if (not isinstance(it, dict) or it.get("status") != "pending" or it.get("kind") not in MO.ORDER_KINDS
                or it.get("hold") == td or it.get("wait") == "prev" or MO.allin_member(it) or it.get("cancel_req")):
            continue
        tr = RS.ts(it.get("tried"))
        if tr is not None and (now - tr).total_seconds() < MO.RETRY_S + 300:
            continue
        rows.append((it, str(it.get("msg") or "执行器读了，还没下")))
    try:
        waiting = MO.unseen(tag, book)
    except Exception:                                         # noqa: BLE001  指令文件读不了：只看账本里的
        waiting = []
    gone = MO.cancelled(waiting)
    for r in waiting:                                         # 固定口数也算（D1 起当天按时段下；D5，2026-10-15：以前 08:48 写的固定口数整天没人读也通过）
        if r.get("kind") in MO.ORDER_KINDS + ("core", "corefix") and not MO.allin_member(r) and r.get("id") not in gone:
            rows.append((r, "执行器还没读到"))
    late = []
    for it, why in sorted(rows, key=lambda x: str(x[0].get("at") or "")):
        t = _due_at(it.get("at"), today)
        if t is not None and (now - t).total_seconds() >= MANUAL_GRACE_S:
            w_ = wrote(it.get("at")) or f"写于 {MO.mmdd(it.get('at'))}"   # 写的时刻、该下的时刻都写到分钟（D5；2026-10-15）
            late.append(f"{it.get('id')}（{MO.describe(it)}，{w_}，该在 {t:%m/%d %H:%M} 下）：{why}")
    if not late:
        return []
    pz = RS.trigger_paused(tag, td)
    hint = (f"面板自动下单今天暂停了（{pz.get('why') or '执行器连续失败'}）" if pz else
            "今天早上的运行还没完成：补跑之后才下" if not done and str(((book.get("state") or {}).get("last_date")) or "")
            < prev_trading_day(today).isoformat() else
            "面板没开（盘中的单要面板叫执行器）？在 Mac 对话里说「看一下面板」")
    return [f"有 {len(late)} 条手动指令到现在还没下（{hint}）：" + "；".join(late[:5]) + ("…" if len(late) > 5 else "")]


ORDER_WORDS = (("成交", ("FILLED", "RESOLVED")), ("部分成交", ("PARTIAL",)), ("挂着", ("SENT",)),
               ("开盘后再下", ("DEFERRED",)), ("没成交", ("UNFILLED", "MISSED", "EXPIRED")), ("已撤", ("CANCELLED",)),
               ("没下",("PLANNED", "BLOCKED", "REJECTED")), ("状态不明", ("SENDING", "ERROR")))
WONT_WORDS = (("预计下不成", ("DEFERRED", "PLANNED", "BLOCKED")), ("不会下", ("SKIPPED",)))   # outlook 判「今天不会下」的单（D5）


def orders_brief(book: dict, exp: str, ol: dict | None = None) -> str:
    """决策 exp 的单（今天下的）→「今天没有单」/「今天的单 3 笔：成交 1、挂着 2」（只数笔数，不写价格）。
    规则自己的不下（SKIPPED：与模型相同的跳空 / 资格…）不算；ol（live_ops.outlook）给了 → 它判「今天不会下」的单按它的词数
    （等开盘后的写「预计下不成」、钱没来 / 凑钱的卖单没了的不下写「不会下」；D5，2026-10-15：以前一律「开盘后再下」、不下的不计数）。"""
    from .live_ops import skip_wont
    wont = {c for c, r in ((ol or {}).get("orders") or {}).items() if r.get("state") == "wont"}
    os_ = [o for o in (book or {}).get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == exp
           and (o.get("status") != "SKIPPED" or skip_wont(o))]
    if not os_:
        return "今天没有单"
    won = [o for o in os_ if str(o.get("cid")) in wont and any(o.get("status") in sts for _, sts in WONT_WORDS)
           or (o.get("status") == "SKIPPED")]
    rest = [o for o in os_ if o not in won]
    parts = [f"{w} {n}" for w, sts in WONT_WORDS if (n := sum(1 for o in won if o.get("status") in sts))]
    parts += [f"{w} {n}" for w, sts in ORDER_WORDS if (n := sum(1 for o in rest if o.get("status") in sts))]
    known = {s for _, sts in ORDER_WORDS for s in sts}
    other = sum(1 for o in rest if o.get("status") not in known)
    return f"今天的单 {len(os_)} 笔：" + "、".join(parts + ([f"其他 {other}"] if other else []))


def _outlook(tag: str, book: dict, now: dt.datetime) -> dict:
    """自检用的 outlook（指令文件里还没读的、HALT、面板自动下单今天暂停 都算上）；算不成 → 空（不下结论，记日志）。"""
    from . import manual_orders as MO
    from . import run_status as RS
    from .live_ops import outlook
    try:
        try:
            waiting = MO.unseen(tag, book)
        except Exception:                                     # noqa: BLE001  指令文件读不了：只看账本里的
            waiting = []
        return outlook(book, waiting, now, tag=tag, halt=bool(_halt()), paused=bool(RS.trigger_paused(tag, now.date().isoformat())))
    except Exception as e:                                    # noqa: BLE001
        log.warning("今天会不会下单没算成（%s：%s）：自检只看别的", type(e).__name__, e)
        return {"rows": [], "orders": {}, "items": {}, "asked": set(), "n": {}}


def _orow(r: dict, now: dt.datetime | None = None) -> str:
    """outlook 的一行 → 自检原因 / 推送里的一句（什么时候下写在前面；代码带名字）。"""
    from .live_ops import act_text, row_text
    w = act_text(r, now) if now is not None else ""
    return (f"{w} " if w else "") + row_text(r)


def evaluate(tag: str, now: dt.datetime | None = None) -> dict:
    """→ {"at", "tag", "trading", "judged", "ok", "halt", "reasons": [...], "note", "decided", "orders"}。只读（账本读坏也不改名）。
    decided / orders：今天早上应该处理到的决策日与那次的单的笔数（通过时的推送用；不写进结果文件）。"""
    from . import run_status as RS
    from .live_unified import UNKNOWN, morning_done, open_pending
    now = now or now_jst()
    now = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    today = now.date()
    rec = {"at": now.isoformat(timespec="seconds"), "tag": tag, "trading": is_trading_day(today), "judged": True,
           "ok": True, "halt": None, "reasons": [], "note": ""}
    if not rec["trading"]:
        rec["note"] = f"{today} 休市"
        return rec
    if now.time() < JUDGE_FROM:
        rec["judged"] = False
        rec["note"] = f"还早：{JUDGE_FROM:%H:%M} 之前不判定（早上的运行 07:40〜08:55 可能还在进行）"
        return rec
    start = _sim_start() if tag.startswith("paper") else None
    if start and today.isoformat() < start:                   # 执行器在开始日之前故意不推进模拟账户（run.py live-u）
        rec["note"] = f"模拟期开始日 {start} 之前（模拟账户还不推进）"
        return rec
    reasons: list[str] = []
    bp = paths.state_dir() / f"live_unified_{tag}.json"
    book = RS.peek_json(bp)
    if book is None and bp.exists():
        reasons.append("账本文件读不了（可能损坏）：在 Mac 对话里说「看一下执行器日志」")
    book = book or {}
    st = book.get("state") or {}
    ld = st.get("last_date")
    exp = prev_trading_day(today).isoformat()                 # 今天早上应该处理到的决策日
    done = morning_done(book, exp)
    if not done and str(ld or "") != exp:
        reasons.append(f"今天早上的执行器没有跑完（上次决策 {ld or '—'}）")
    rs = RS.read(tag)
    t_rs = RS.ts((rs or {}).get("at"))
    rs_today = bool(rs) and t_rs is not None and t_rs.astimezone(JST).date() == today
    if rs_today:
        if rs.get("ok") is False:
            reasons.append(f"执行器停下（{t_rs.astimezone(JST):%H:%M}）：{rs.get('error') or '原因不明（看数据目录 logs/ 的 .err）'}")
        if rs.get("blocked") and not done:
            reasons.append(f"今天的单没下：{rs['blocked']}")
    ol = _outlook(tag, book, now)                             # 每笔单 / 每条指令今天会不会下：live_ops.outlook（面板、执行器汇总同一个判断；D5）
    if str(ld or "") == exp:                                  # 决策处理了，但有单没下（被挡 / 还没发 / 被拒）：逐笔说清
        #                                                       D5（2026-10-15）：不再只在「早上没做完」时看 —— 跑完了、被拒的单以前一声不响
        from .live_ops import MANUAL_REASONS
        stuck = [o for o in book.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == exp
                 and o.get("status") in ("PLANNED", "BLOCKED", "REJECTED")
                 and not (done and o.get("reason") in MANUAL_REASONS and o.get("phase") != "now")   # 手动指令的单：下面 _manual_unsent 列
                 and not (o.get("status") != "REJECTED" and (ol["orders"].get(str(o.get("cid"))) or {}).get("state") == "will")]   # 08:55 之前还会再发
        stuck = RS.uncovered(stuck, rs.get("blocked") if rs_today else None)   # 「今天的单没下：…」已经说了原因的不再逐笔列
        if stuck:
            reasons.append(f"决策 {exp} 处理了，但有 {len(stuck)} 笔没下：" + "；".join(_otext(o) for o in stuck[:5])
                           + ("…" if len(stuck) > 5 else ""))
        reasons += _manual_unsent(book, exp, today, done)     # 手动指令的单没发出（被拒 / 连续几天被挡；G7）
        wont = [r for r in ol["rows"] if r["kind"] == "order" and r["state"] == "wont"
                and r["cls"] not in ("halt", "closed", "open_missed", "blocked") and r.get("status") not in ("PLANNED", "BLOCKED", "REJECTED")]
        if wont:                                              # 今天不会下的单（凑钱的卖单撤了 / 钱不够 / 钱没来 / 错过…）：以前 09:30 照样「✓ 通过」（M2）
            reasons.append(f"今天不会下的单 {len(wont)} 笔：" + "；".join(_orow(r) for r in wont[:5]) + ("…" if len(wont) > 5 else ""))
            rec["trade"] = True
    stk = [r for r in ol["rows"] if r.get("kind") == "order" and r.get("cls") == "stuck"]
    if stk:                                                   # 写了撤单、面板自动下单暂停：撤单今天没人处理、单还挂着（复核 8，2026-10-16：以前照样「通过」）
        reasons.append(f"写了撤单、单还挂着 {len(stk)} 笔：" + "；".join(_orow(r) for r in stk[:5])
                       + ("…" if len(stk) > 5 else ""))
        rec["trade"] = True
    if not _halt():                                           # 该下了还没下的手动指令（面板没开 / 暂停 / 早上没跑完；G24）
        mw = _manual_waiting(tag, book, now, done)
        reasons += mw
        rec["trade"] = rec.get("trade") or bool(mw)           # 交易问题（单 / 指令今天不会下）→ 推送标题以「★ 交易」开头（D5）
    unk = [o for o in book.get("orders") or [] if isinstance(o, dict) and o.get("status") in UNKNOWN]
    if unk:
        what = "、".join(_olab(o) for o in unk[:5]) + (f" 等 {len(unk)} 笔" if len(unk) > 5 else "")
        reasons.append(f"有状态不明的单 {len(unk)} 笔（{what}）：" + (
            "在 Mac 对话里看一下" if tag.startswith("paper")
            else f"去立花的注文一覧核对（手机网站 {ESHITEN_SP}），再在 Mac 对话里登记"))
    if tag.startswith("tachibana") and now.time() >= OPEN_DONE and open_pending(book):
        n = sum(1 for o in book.get("orders") or [] if o.get("decided_on") == ld and o.get("status") == "DEFERRED")
        reasons.append(f"开盘后的买单还没下（{n} 笔：09:05 / 09:20 的补单没跑成）")
    miss = _daily_missing(today)                              # 例行任务（Mac 的本机任务 / 云端后备）今天的日报
    if miss:
        reasons.append(miss)
    rec["routines"] = _routine_lines(now)                     # 本机例行任务卡住 / 没跑 / 晚了：推送里加一行，不算没通过（2026-10-16）
    from .names import annotate                               # 执行器 / 运行状态文件里只有代码的原因 → 补名字（命令行、cid 不动；2026-10-15）
    rec["reasons"] = [annotate(x) for x in reasons]
    rec["decided"], rec["orders"] = exp, orders_brief(book, exp, ol)
    rec["halt"] = _halt()
    rec["later"] = [_orow(r, now) for r in ol["rows"] if r["state"] == "later" and r["cls"] != "halt"]   # 之后才下的：写进当天推送、不算失败
    rec["halt_wait"] = [_orow(r) for r in ol["rows"] if r["cls"] == "halt" and r["kind"] == "instr"]   # HALT 期间等着的指令（解除后照原样）
    rec["ok"] = bool(rec["halt"]) or not reasons                # HALT 生效中：不下单是预期的，不算失败
    return rec


def write(rec: dict) -> None:
    """out/watchdog_<账本>.json（面板 / 菜单栏读 at / ok / reasons / halt / note / push / heartbeat）。写不成只记 warning。
    ok = None：这次没判定（执行器一直在跑）。heartbeat 只在设了外部心跳时有。"""
    keys = ("at", "ok", "reasons", "halt", "note") + tuple(k for k in ("push", "heartbeat") if k in rec) + (
        ("routines",) if rec.get("routines") else ())
    try:
        atomic_write_text(path(rec["tag"]), json.dumps({k: rec.get(k) for k in keys}, ensure_ascii=False, indent=1))
    except Exception as e:                                    # noqa: BLE001
        log.warning("自检结果文件没写成（不影响交易）：%s", e)


def today_rec(tag: str, today: dt.date) -> dict | None:
    """今天写过的结果文件（读不了 / 不是今天的 → None）。只读。"""
    from . import run_status as RS
    wd = RS.peek_json(path(tag))
    if not isinstance(wd, dict):
        return None
    t = RS.ts(wd.get("at"))
    return wd if t is not None and t.astimezone(JST).date() == today else None


def _hm(at) -> str:
    from . import run_status as RS
    t = RS.ts(at)
    return t.astimezone(JST).strftime("%H:%M") if t else "—"


def _sent(res) -> str:
    """{webhook / email / push: True / False / None} → 「推送（网页 App） 已发、webhook 没设置」（不含任何值）。"""
    from .notify import LABEL as NL
    word = {True: "已发", False: "★ 失败", None: "没设置"}
    return "、".join(f"{NL.get(k, k)} {word.get(v, v)}" for k, v in (res or {}).items()) or "—"


def push_state(res, at: str) -> dict:
    """notify.send 的结果 → 结果文件的 push：{at, state, why}（不含任何地址）。有一个通道发成 → sent；设置了的都失败 → failed；
    一个通道都没有（没有设备打开 qbreak 推送、也没设 webhook / 邮件：只记进了通知记录）→ none。"""
    from .notify import LABEL as NL
    res = res if isinstance(res, dict) else {}
    ok = [NL.get(k, k) for k, v in res.items() if v is True]
    bad = [NL.get(k, k) for k, v in res.items() if v is False]
    if ok:
        return {"at": at, "state": "sent", "why": "、".join(ok) + " 已发" + (f"（{'、'.join(bad)} 失败）" if bad else "")}
    if bad:
        return {"at": at, "state": "failed", "why": "、".join(bad) + " 失败"}
    return {"at": at, "state": "none", "why": "没有设备打开 qbreak 推送（也没设 webhook / 邮件）：只记进了面板「消息 → 通知记录」"}


def push_word(p) -> str:
    """结果文件的 push → 一小段（终端 / 菜单栏 / 面板）。"""
    if not isinstance(p, dict):
        return "—"
    st = p.get("state")
    if st == "sent":
        return "已推送"
    if st == "failed":
        return f"★ 推送没发成（{p.get('why') or '原因不明'}）"
    if st == "none":
        return "★ 没推到手机（没有设备打开 qbreak 推送）"
    return str(p.get("why") or st or "—")


def push_fix(p) -> str | None:
    """push 没发成 → 怎么做：failed（设置了的通道都失败，重推一次也没成：网络 / 推送服务）→ 再自检一次；none（没有通道）→
    怎么在手机上打开推送。发了 / 没记 → None。"""
    st = p.get("state") if isinstance(p, dict) else None
    return FAIL_FIX if st == "failed" else PUSH_FIX if st == "none" else None


def push_text(p) -> str | None:
    """push 没发成 / 没有通道 → 一句话 + 怎么做（面板顶部 / 菜单栏 / 上线检查）；发了 / 没记 → None。
    自动的自检每个工作日只跑 09:30 那一次：没发成不会自动再推（2026-10-14 复核：以前写「下一次会再推」，像是当天会自动再推）。"""
    fix = push_fix(p)
    if not fix:
        return None
    if p["state"] == "failed":
        return f"自检的推送没发成（{p.get('why') or '原因不明'}）：{fix}"
    return f"自检没推到手机（没有设备打开 qbreak 推送） → {fix}"


def _push(send, sleep, title: str, text: str, level: str, at: str, out) -> tuple[dict, dict]:
    """推一条 → (notify.send 的结果, 结果文件的 push)。设置了的通道都没发成（网络抖动等；2026-10-14 复核：自动的自检一天只跑一次，
    一次抖动就让当天没有推送、看起来像 Mac 关机）→ 等 RETRY_S 秒再推一次（只一次；重推不再记进通知记录）。没有通道 → 不重推。"""
    res = send(title, text, level)
    p = push_state(res, at)
    if p["state"] != "failed":
        return res, p
    out(f"  推送没发成（{p['why']}）：{RETRY_S} 秒后再推一次")
    sleep(RETRY_S)
    res = send(title, text, level, resend=True)
    p = push_state(res, at)
    if p["state"] == "failed":
        p["why"] += f"；{RETRY_S} 秒后重推也没成"
    elif p["state"] == "sent":
        p["why"] += f"（第一次没发成，{RETRY_S} 秒后重推）"
    return res, p


def _carry(prev: dict | None, at: str) -> dict:
    """今天已经推过：沿用今天那次的 push（没记 → skipped）。"""
    p = (prev or {}).get("push")
    if isinstance(p, dict) and p.get("state"):
        return p
    return {"at": at, "state": "skipped", "why": "今天已经推过（这次不再推）"}


def _daily(title, text, tag: str, now, send, seen, prev: dict | None, at: str, force: bool = False, *,
           sleep=None, out=print) -> tuple[dict | None, bool]:
    """每个工作日的那一条（通过 / 休市 / 模拟期开始前）→ (结果文件的 push, 这次推了没有)。同一个账本同一天只推一次；
    force（早些时候没通过、现在通过）或今天那次没推到手机 → 照推。title = None（周末）→ 不推、不记。"""
    if title is None:
        return None, False
    first = seen(tag, DAILY_KEY, now)
    old = _carry(prev, at)
    if first or force or old.get("state") in ("failed", "none"):
        return _push(send, sleep or time.sleep, title, text, "info", at, out)[1], True
    return old, False


def _lock_since(lock, today: dt.date) -> dt.datetime | None:
    """运行锁文件里执行器开始的时刻（RunLock 写「pid N 从 YYYY-MM-DD HH:MM:SS JST」）；读不了 / 不是今天 → None。只读。"""
    import re
    try:
        m = re.search(r"从 (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", Path(lock).read_text(encoding="utf-8", errors="replace"))
        t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST) if m else None
    except (OSError, ValueError):
        return None
    return t if t is not None and t.date() == today else None


def _stuck(tag: str, name: str, lock, now: dt.datetime, send, mac, seen, out, sleep=None) -> int:
    """执行器跑了 LOCK_WAIT_S 以上还没结束：这次不判定 → 推一条 warn（同一天只一次；2026-10-14 起，以前一声不响）。
    今天还没有结果文件 → 写一份「判定不了」（ok = None）。今天已经判定过（通过 / 没通过；例：09:30 通过之后「再自检一次」时
    面板叫的执行器正在跑）→ 不推、不盖掉那次的结果（2026-10-14 复核：以前照推「今天早上的单下没下还不知道」，早上明明确认过）。"""
    now = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    since = _lock_since(lock, now.date())
    mins = int((now - since).total_seconds() // 60) if since is not None and now >= since else None
    ran = f"从 {since:%H:%M} 起已经跑了 {mins} 分钟" if mins is not None else f"已经跑了 {LOCK_WAIT_S // 60} 分钟以上"
    note = f"执行器{ran}还没结束：这次不判定"
    prev = today_rec(tag, now.date())
    if prev is not None and prev.get("ok") is not None:
        out(f"{name}（{now:%Y-%m-%d %H:%M} JST）：今天 {_hm(prev.get('at'))} 已经判定过（{'通过' if prev['ok'] else '没通过'}）；"
            f"这次执行器还在跑（{ran}），不再判定、不推送")
        return 0
    rec = {"at": now.isoformat(timespec="seconds"), "tag": tag, "ok": None, "reasons": [], "halt": _halt(), "note": note}
    out(f"{name}（{now:%Y-%m-%d %H:%M} JST）：{note}")
    if seen(tag, STUCK_KEY, now):
        title = f"qbreak {name} ★ {now:%H:%M} 自检判定不了"
        text = (f"{note}（今天早上的单下没下还不知道）。\n在 Mac 对话里说「看一下执行器日志」；跑完之后问「今天的自检过了吗」"
                "（bash scripts/liveu.sh watchdog --dry，只看不发）")
        res, rec["push"] = _push(send, sleep or time.sleep, title, text, "warn", rec["at"], out)
        mac(title, note[:200])
        out(f"  推送：{push_word(rec['push'])}（{_sent(res)}）")
    else:
        out("  （今天已经推过「判定不了」：这次不再推）")
    if prev is None:                                          # 今天早些时候也判定不了 → 留着那次的（含那次的推送结果）
        write(rec)
    return 0


def _crashed(tag: str, name: str, e: BaseException, now: dt.datetime | None, send, mac, seen, out, sleep) -> int:
    """自检程序自己出错（代码的 bug、文件读不了…；2026-10-14 复核：以前只写日志、退出 1，当天一条推送都没有，看起来和 Mac 关机一样）
    → 推一条 warn「★ HH:MM 自检出错」+ Mac 通知（同一天只一次）；今天还没有判定结果 → 写一份 ok = None（面板 / 菜单栏 ★）。
    文字只写异常的类型名（不带路径、不带值）；详细的堆栈只进日志（com.qbreak.watchdog.out）。→ 1。"""
    log.exception("09:30 自检出错：%s", type(e).__name__)
    try:
        now = now or now_jst()
        now = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
        kind = type(e).__name__
        note = f"自检程序出错（{kind}）；在 Mac 对话里说「看一下自检日志」"
        rec = {"at": now.isoformat(timespec="seconds"), "tag": tag, "ok": None, "reasons": [], "halt": _halt(), "note": note}
        out(f"{name}（{now:%Y-%m-%d %H:%M} JST）：★ {note}")
        if seen(tag, CRASH_KEY, now):
            title = f"qbreak {name} ★ {now:%H:%M} 自检出错"
            text = f"{kind}：这次没判定（今天早上的单下没下还不知道）。\n在 Mac 对话里说「看一下自检日志」"
            res, rec["push"] = _push(send, sleep, title, text, "warn", rec["at"], out)
            mac(title, text[:200])
            out(f"  推送：{push_word(rec['push'])}（{_sent(res)}）")
        else:
            out("  （今天已经推过「自检出错」：这次不再推）")
        old = today_rec(tag, now.date())
        if old is None or old.get("ok") is None:              # 今天已经判定过（通过 / 没通过）→ 不盖掉
            write(rec)
    except Exception:                                         # noqa: BLE001  提醒本身也出错：只记日志
        log.exception("自检出错之后的提醒也没发成")
    return 1


def run(agents, now: dt.datetime | None = None, *, send=None, beat=None, mac=None, seen=None, out=print, sleep=None,
        dry: bool = False) -> int:
    """自检一次：（执行器正在运行 → 等它结束）判定 → 写结果文件 → 推送 /（设了的话）外部心跳。0 = 通过（含休市、HALT、还早、没装、
    模拟期开始前、执行器一直在跑），1 = 没通过 / 自检程序出错。dry：只判定、打印（不写、不发、不等；出错照常抛）。
    推送（2026-10-14 起每个工作日一条，代替外部心跳）：通过 / 平日休市 / 模拟期开始前 → info，同一个账本同一天只一次（_daily）；
    HALT →「HALT 生效中」一天一次（就是当天那条；没推到手机 → 再自检时再推）；没通过 → warn，每次；执行器一直在跑 →「判定不了」
    warn 一天一次（_stuck）；自检程序自己出错 →「自检出错」warn 一天一次（_crashed）。设置了的通道都没发成 → 60 秒后重推一次（_push）。
    send / beat / mac / seen / sleep：测试注入（默认 qbreak.notify.send / heartbeat_detail、Mac 通知、qbreak.notify_seen.first、time.sleep；
    send 重推时带 resend=True；beat 返回 (状态, 原因) 或只返回状态都行，None = 没设外部心跳）。"""
    from . import notify, notify_seen
    send = send or notify.send
    beat = beat or notify.heartbeat_detail
    seen = seen or notify_seen.first
    sleep = sleep or time.sleep
    if mac is None:
        from .live_unified import mac_notify as mac
    tags = installed_all(agents)
    if not tags:
        out(f"没装执行器的定时任务（{agents} 里 {LIVE_PLIST} / {PAPER_PLIST} 都没有）：只打印，不推送")
        return 0
    rc = 0
    for tag in tags:                                          # 立花 + 模拟一起装（both）：各查一次、各推一条（标题写是哪个账本）
        name = "立花实盘" if tag == "tachibana" else "模拟操盘"
        if dry:
            rc = max(rc, _check(tag, name, now, send, beat, mac, seen, out, sleep, dry=True))
            continue
        try:
            rc = max(rc, _check(tag, name, now, send, beat, mac, seen, out, sleep))
        except Exception as e:                                # noqa: BLE001  自检程序出错：推一条（不然当天没有推送，像 Mac 关机）
            rc = max(rc, _crashed(tag, name, e, now, send, mac, seen, out, sleep))
    return rc


def _check(tag: str, name: str, now: dt.datetime | None, send, beat, mac, seen, out, sleep, dry: bool = False) -> int:
    """run 的本体（出错由 run 接住）。"""
    from . import run_status as RS
    from .live_unified import lock_held
    lock = paths.state_dir() / f"live_unified_{tag}.lock"
    if not dry and lock_held(lock):                           # 执行器正在运行：判定的是还没跑完的账本 → 等它结束
        out(f"（{name}的执行器正在运行：等它结束再判定，最多 {LOCK_WAIT_S // 60} 分钟）")
        waited = 0
        while lock_held(lock) and waited < LOCK_WAIT_S:
            sleep(LOCK_POLL_S)
            waited += LOCK_POLL_S
        now = None if now is None else now + dt.timedelta(seconds=waited)
        if lock_held(lock):
            return _stuck(tag, name, lock, now or now_jst(), send, mac, seen, out, sleep)
    now = now or now_jst()
    r = evaluate(tag, now)
    when = r["at"][:16].replace("T", " ")
    if dry:
        busy = "（执行器正在运行：结果可能还会变）" if lock_held(lock) else ""
        if not r["judged"] or not r["trading"] or not r["reasons"]:
            out(f"{name}（{when} JST，只看不发）：{r['note'] or '自检通过（今天早上的运行跑完、没有状态不明的单）'}{busy}")
        else:
            out(f"{name}（{when} JST，只看不发）：{'HALT 生效中（不算失败）；' if r['halt'] else '★ 没通过：'}\n"
                + "\n".join(f"- {x}" for x in r["reasons"]) + busy)
        for x in r.get("routines") or []:
            out(f"- ★ {x}（不算没通过）")
        return 0 if r["ok"] else 1
    r["reasons"] = [RS.local_paths_out(x) for x in r["reasons"]]   # 手机通知 / 心跳的正文不带本机路径（Mac 的用户名）
    r["routines"] = [RS.local_paths_out(x) for x in r.get("routines") or []]
    if not r["judged"]:
        out(f"{name}（{when} JST）：{r['note']}；不推送")
        return 0
    today, hhmm = dt.date.fromisoformat(r["at"][:10]), when[11:16]
    prev = today_rec(tag, today)                              # 今天早些时候的结果（这次写之前读）
    write(r)
    if not r["trading"] or (r["ok"] and r["note"] and not r["reasons"]):   # 休市 / 模拟期开始日之前
        if r["trading"]:
            title, text = f"qbreak {name} ✓ {hhmm} 自检：模拟期开始前", f"{r['note']}。\n{DAILY_LINE}"
        elif today.weekday() < 5:                             # 平日的休市（祝日 / 年末年始）：照推，说系统正常
            title, text = (f"qbreak {name}：今天休市（系统正常）",
                           f"{today:%m/%d} 休市：执行器今天不下单；{hhmm} 自检照常运行。\n{DAILY_LINE}")
        else:                                                 # 周末：不推
            title = text = None
        p, pushed = _daily(title, text, tag, now, send, seen, prev, r["at"], sleep=sleep, out=out)
        hb = _hb(beat(True, f"qbreak {name}：{r['note']}"))
        out(f"{name}（{when} JST）：{r['note']}{_tail(p, pushed, hb)}")
        _finish(r, p, hb, tag, name, now, send, mac, seen, out)
        return 0
    if r["halt"]:
        extra = ("\n另外：" + "；".join(r["reasons"])) if r["reasons"] else ""
        hw = r.get("halt_wait") or []                         # HALT 期间等着的指令：解除后照原样执行（M18）
        if hw:
            extra += f"\n等着的指令 {len(hw)} 条（解除后照原样执行）：" + "；".join(hw[:5]) + ("…" if len(hw) > 5 else "")
        text = RS.local_paths_out(_with_routines(
            f"HALT 生效中（{r['halt']}）：执行器不下单、持仓不动；解除只在 Mac 上、你明确说之后{extra}", r))
        first, old = seen(tag, HALT_KEY, now), _carry(prev, r["at"])
        if first or old.get("state") in ("failed", "none"):  # 这一条就是今天的推送（不再另推「通过」）；没推到手机 → 再推
            title = f"qbreak {name}：HALT 生效中"
            res, p = _push(send, sleep, title, text, "info", r["at"], out)
            if first:                                         # Mac 通知只在第一次（重推只为手机）
                mac(title, text[:200])
            out(f"{name}（{when} JST）：{text}\n  通知：{_sent(res)}")
        else:
            p = old
            out(f"{name}（{when} JST）：{text}\n  （今天已经推过 HALT：这次不再推）")
        hb = _hb(beat(True, f"qbreak {name}：HALT 生效中"))
        if hb[0] is not None:
            out(f"  外部心跳 {_beat(hb)}")
        _finish(r, p, hb, tag, name, now, send, mac, seen, out)
        return 0
    if r["ok"]:
        back = bool(prev) and prev.get("ok") is False         # 早些时候没通过、现在通过：照推（说一声好了）
        lead = f"现在通过了（{_hm(prev.get('at'))} 没通过）。\n" if back else ""
        title = f"qbreak {name} ✓ {hhmm} 自检通过" + (ROUTINE_TAG if r.get("routines") else "")
        lat = r.get("later") or []                            # 之后才下的（不算失败；D5）
        text = _with_routines(f"{lead}决策 {r.get('decided') or '—'} 处理完；{r.get('orders') or '今天没有单'}。\n"
                              + (f"之后才下 {len(lat)} 条：" + "；".join(lat[:5]) + ("…" if len(lat) > 5 else "") + "\n" if lat else "")
                              + DAILY_LINE, r)
        p, pushed = _daily(title, text, tag, now, send, seen, prev, r["at"], force=back, sleep=sleep, out=out)
        hb = _hb(beat(True, f"qbreak {name}：{when} 自检通过"))
        out(f"{name}（{when} JST）：自检通过（今天早上的运行跑完、没有状态不明的单）{_tail(p, pushed, hb)}"
            + "".join(f"\n  ★ {x}" for x in r.get("routines") or []))
        _finish(r, p, hb, tag, name, now, send, mac, seen, out)
        return 0
    title = (("★ 交易：" if r.get("trade") else "")         # 有单 / 指令今天不会下（D5；2026-10-15）：交易问题的推送都以「★ 交易」开头
             + f"qbreak {name} ★ {hhmm} 自检没通过")           # 真的运行时刻（Mac 晚醒就写晚的；2026-10-14 复核：以前固定写 09:30）
    text = _with_routines("\n".join(f"- {x}" for x in r["reasons"]), r, "- ★ ")   # 本机例行任务：附在后面（不是没通过的原因）
    res, p = _push(send, sleep, title, text, "warn", r["at"], out)
    mac(title, r["reasons"][0][:200])
    hb = _hb(beat(False, f"{title}\n{text}"))
    out(f"{title}（{when} JST）：\n{text}\n  通知：{_sent(res)}" + (f"；外部心跳（失败）{_beat(hb)}" if hb[0] is not None else ""))
    _finish(r, p, hb, tag, name, now, send, mac, seen, out)
    return 1


def _tail(p: dict | None, pushed: bool, hb: tuple[bool | None, str]) -> str:
    """终端那一行的结尾：→ 推送 已推送 / 今天已经推过 / 周末不推；设了外部心跳才说心跳。"""
    if p is None:
        s = " → 周末不推送"
    elif not pushed:
        s = " → 今天已经推过（这次不再推）"
    else:
        s = f" → 推送 {push_word(p)}"
    return s + (f"；外部心跳 {_beat(hb)}" if hb[0] is not None else "")


def _hb(res) -> tuple[bool | None, str]:
    """beat 的返回值 → (True 发了 / False 没发成 / None 没设置, 原因)：notify.heartbeat_detail 给 (状态, 原因)，只给状态的也认。"""
    if isinstance(res, tuple):
        return (res[0] if res else None), str(res[1] if len(res) > 1 and res[1] else "")
    return res, ""


def _beat(hb) -> str:
    ok, why = _hb(hb)
    if ok is False:
        return f"★ 没发成（{why or '原因不明'}）"
    return {True: "已发"}.get(ok, "没设置")


def beat_fix(why: str) -> str:
    """心跳没发成的原因 → 该怎么做（不含地址；2026-10-14 G12）。"""
    w = str(why or "")
    if w.startswith("地址"):                                  # 地址不是 http(s):// 开头 / 有空白或换行 / 格式不对
        return BEAT_RESAVE
    if w.startswith("HTTP 4"):
        return "心跳服务不认这个地址（检查删掉了 / 地址抄错？）：在心跳服务上确认这个检查还在，再" + BEAT_RESAVE
    return "多半是网络问题：下一次自检会再 ping；连着几天都这样 → 在 Mac 对话里说「看一下自检日志」"


def beat_text(hb: dict | None) -> str | None:
    """结果文件里的 heartbeat 没发成 → 一句话（面板顶部 / 菜单栏的状态用）；发了 / 没设置 / 没记 → None。
    外部心跳 2026-10-14 起是可选的（每天的推送代替它）：只在设了地址、又没发成时才说。"""
    if not isinstance(hb, dict) or hb.get("state") != "failed":
        return None
    why = str(hb.get("why") or "原因不明")
    return f"外部心跳没发成（{why}）：钥匙串里设了 qbreak-heartbeat（可选）。{beat_fix(why)}"


def _finish(r: dict, p: dict | None, hb: tuple[bool | None, str], tag: str, name: str, now, send, mac, seen, out) -> None:
    """推送与外部心跳的结果写进结果文件（push；heartbeat 只在设了地址时）；心跳没发成 → 手机 + Mac 通知（同一天只一次）。
    文字里没有地址（2026-10-14 G12）。"""
    if p is not None:
        r["push"] = p
    ok, why = hb
    if ok is None:                                            # 没设外部心跳：正常（2026-10-14 起不用），不记、不说
        r.pop("heartbeat", None)
    else:
        r["heartbeat"] = {"at": r["at"], "state": "sent" if ok else "failed", "why": "" if ok else (why or "原因不明")}
    write(r)
    text = beat_text(r.get("heartbeat"))
    if not text:
        return
    if seen(tag, BEAT_KEY, now):
        title = f"qbreak {name}：外部心跳没发成"
        res = send(title, text, "warn")
        mac(title, text[:200])
        out(f"  {text}\n  通知：{_sent(res)}")
    else:
        out("  （今天已经提醒过外部心跳没发成：这次不再发通知）")


__all__ = ["installed", "evaluate", "write", "run", "path", "beat_text", "beat_fix", "push_state", "push_word", "push_text",
           "push_fix", "today_rec", "orders_brief", "LABEL", "MANUAL_GRACE_S", "DAILY_LINE", "PUSH_FIX", "FAIL_FIX", "RETRY_S"]
