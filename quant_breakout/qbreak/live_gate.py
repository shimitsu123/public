"""live_gate.py — 立花实盘的上线门槛（HANDOFF 路线图 4，2026-09-26 用户原样采用）与本番运行的准备，逐项检查。

只读：不下单、不改任何文件、不打印任何密钥的值（钥匙串只看「有没有」，私钥只看「在不在、权限是不是 600」，不读内容）。
用法：bash scripts/liveu.sh gate（= run.py live-gate；Mac 对话里问「能上实盘了吗」）。

门槛（四项都满足才上本番，先用较小金额跑 1〜2 周）：
 ① Mac 模拟操盘与云端模拟盘连续 ≥ 10 个交易日一致（或差异都能解释 → 由用户确认）；最近一次比较要在 10 个交易日以内（过期 ★；
   装了立花本番、模拟操盘的定时任务有意卸掉之后，只量到模拟操盘最后一次运行的那天）
 ②没有状态不明的单
 ③ HALT 演练过一次（执行器在 HALT 存在时运行过：账本的 halt_seen；bash scripts/liveu.sh halt-drill）
 ④ デモ发单检查的几点确认（约定字段、余力 / 持仓变化、按注文番号撤单、寄付指値买受理：tachibana-probe --demo --order-test 的结果文件）
准备（本番每天全自动要用到）：⑤ 本番只读检查通过 ⑥ 认证信息在钥匙串（并用和定时任务相同的读法试读一次：值丢进 /dev/null，只看
 能不能读出 / 钥匙串锁着）、私钥权限 600、cryptography 已装、仕様覆盖文件没指向旧版本、Mac 的时钟准（sntp，只读）
 （④ / ⑤：结果文件记着当时的 API 版本段；与现在的仕様不同、或是没记版本的旧格式 → 要重新做；做了几天只显示、不判定）
 ⑤ 还有：本番 dry-run 跑通过（只算不发单；dry-run 账本的运行状态）；⑥ 还有：doctor 通过（out/doctor.json；没做过只提醒）
 ⑦ 立花的定时任务已装（含前一晚预检 com.qbreak.precheck）、Mac 每个交易日早上自动唤醒（pmset）、Mac 的时区是日本（date +%z）
 ⑧ 人不在 Mac 前也知道出事：手机通知通道（钥匙串 qbreak-webhook / qbreak-smtp）、外部心跳（qbreak-heartbeat）、09:30 自检任务（com.qbreak.watchdog）
参考（不算门槛）：口座课税区分、ARM / HALT 现在的状态、登记过的入出金。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import re
import subprocess
from pathlib import Path

from . import paths
from .utils import read_json

STREAK_NEED = 10
FRESH_DAYS = 10                                        # ① 的最近一次比较要在几个交易日以内（B14 / C-07；不是新门槛数字，只防过期）
LIVE_LABELS = ("com.qbreak.liveu.morning", "com.qbreak.liveu.retry", "com.qbreak.liveu.open", "com.qbreak.liveu.open2",
               "com.qbreak.precheck")                  # 前一晚预检（B5）：install_launchd_live_u.sh tachibana 一起装
KEYCHAIN = (("qbreak-tachibana-authid", "认证 ID", "TACHIBANA_AUTH_ID"),
            ("qbreak-tachibana-2nd", "第二暗証番号", "TACHIBANA_SECOND_PASSWORD"))
WAKE_CMD = "sudo pmset repeat wakeorpoweron MTWRF 06:40:00"   # 2026-10-09 起 06:40（本机例行任务的日报 06:45；判断照旧只要 07:40 之前）
_SAME, _DIFF = "- 与云端模拟盘一致", "- ★ 与云端模拟盘不一致"
REDO = {"demo": "bash scripts/liveu.sh probe --demo --order-test", "live": "bash scripts/liveu.sh probe"}
ACCEPTED = ("SENT", "FILLED", "PARTIAL")


def _cmd(run, args: list[str], env: dict | None = None) -> tuple[int | None, str]:
    """跑一个只读的系统命令（security / launchctl / pmset）→ (退出码, 标准输出)；命令不存在 → (None, "")。输出只用来判断，不打印。
    env：给这个命令的环境变量（None = 照这个进程的）。"""
    try:
        r = run(args, capture_output=True, text=True, timeout=15, **({"env": env} if env is not None else {}))
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return r.returncode, r.stdout or ""


def compare_days(book: dict, journal: str = "") -> dict[str, bool]:
    """每个决策日与云端比较的结果 {日期: 一致?}：日志（旧的日子）+ 账本的 compare_history（2026-10-04 起；同一天以它为准）。
    「不是同一天，这次不比」的日子不算一致、也不算不一致。"""
    out: dict[str, bool] = {}
    for sec in ("\n" + (journal or "")).split("\n## ")[1:]:
        lines = sec.splitlines()
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", lines[0]) if lines else None
        if not m:
            continue
        for ln in lines[1:]:
            if ln.startswith(_SAME):
                out[m.group(1)] = True
            elif ln.startswith(_DIFF):
                out[m.group(1)] = False
    for h in (book or {}).get("compare_history") or []:
        if h.get("comparable") and h.get("date"):
            out[str(h["date"])] = bool(h.get("same"))
    return dict(sorted(out.items()))


def streak(days: dict[str, bool]) -> tuple[int, str | None]:
    """从最近的决策日往前数连续一致的天数 → (天数, 最近一次不一致的日期 | None)。"""
    n = 0
    for d in sorted(days, reverse=True):
        if not days[d]:
            return n, d
        n += 1
    return n, None


def tdays_since(day: str, today: dt.date) -> int | None:
    """day（YYYY-MM-DD）之后到 today（含）有几个交易日（东证日历）；day 读不出 → None；day 在 today 之后 → 0。"""
    from .calendar_jp import is_trading_day
    try:
        x = dt.date.fromisoformat(str(day or "")[:10])
    except ValueError:
        return None
    n = 0
    while x < today:
        x += dt.timedelta(days=1)
        n += is_trading_day(x)
    return n


def _streak_item(days: dict[str, bool], today: dt.date, paper_stopped: dt.date | None = None) -> tuple[bool, str]:
    """门槛 ①：连续一致 ≥ STREAK_NEED 个决策日，而且最近一次比较在 FRESH_DAYS 个交易日以内（C-07 / B14：模拟操盘停了
    ——例如模拟操盘的定时任务坏了——以前 ① 会一直显示 OK；数字 10 不变，只是不再拿很久以前的连续一致算数）。
    paper_stopped：装了立花本番、模拟操盘的定时任务是有意卸掉的（install_launchd_live_u.sh tachibana）→ 新鲜度只量到模拟操盘
    最后一次运行的那天（之后没有比较是正常的：不让 ① 在卸掉 10 个交易日之后自己变 ★、前一晚预检也不当作新出现的 ★ 通知）。"""
    n, bad = streak(days)
    last = max(days) if days else ""
    ref = min(today, paper_stopped) if paper_stopped else today
    k = tdays_since(last, ref) if last else None
    stale = k is not None and k > FRESH_DAYS
    txt = (f"最近连续一致 {n} 个决策日（一共比过 {len(days)} 天"
           + (f"；最近一次不一致 {bad}：差异如果都能解释，由你确认后算通过" if bad else "") + "）")
    if last:
        txt += f"；最近一次比较 {last}" + (f"（{k} 个交易日前）" if k and not paper_stopped else "")
    if paper_stopped:
        txt += (f"；立花本番已安装、模拟操盘的定时任务已卸掉（最后一次运行 {ref.isoformat()}）："
                "只看卸掉之前的比较，之后不再比较是正常的")
    if stale:
        txt = (f"★ 最近一次比较是 {last}，" + (f"到模拟操盘最后一次运行（{ref.isoformat()}）" if paper_stopped else "")
               + f"已经 {k} 个交易日没和云端比了（要在 {FRESH_DAYS} 个交易日以内；模拟操盘停了？① 就不再算数）：" + txt)
    return n >= STREAK_NEED and not stale, txt


def _paper_stopped(agents: Path, days: dict[str, bool]) -> dt.date | None:
    """模拟操盘是不是有意停的（装了立花本番、com.qbreak.liveu.paper 的 plist 不在）→ 模拟操盘最后一次运行的日子
    （运行状态文件 out/live_unified_paper_run.json 的 at；没有 → 最近一次比较的日子）；不是 → None（照常量到今天）。"""
    if (agents / f"{paths.PAPER_AGENT}.plist").exists() or not paths.live_installed(agents):
        return None
    rs = read_json(paths.out_dir() / "live_unified_paper_run.json", {}) or {}
    try:
        return dt.date.fromisoformat(str(rs.get("at") or "")[:10])
    except ValueError:
        pass
    try:
        return dt.date.fromisoformat(max(days)[:10]) if days else None
    except ValueError:
        return None


def _book(tag: str) -> dict:
    return read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {}


def _journal(tag: str) -> str:
    p = paths.out_dir() / f"live_unified_{tag}_journal.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _api_now(env: str) -> str | None:
    """现在的仕様（数据目录的 tachibana_spec.json 覆盖默认值）的 base URL 版本段（例如 e_api_v4r10）；仕様文件读不了 → None。"""
    from .brokers.tachibana import TachibanaSpec, api_version
    try:
        sp = TachibanaSpec.load()
    except Exception:                                # noqa: BLE001
        return None
    return api_version(sp.base_demo if env == "demo" else sp.base_live)


def _stale(env: str, rec: dict) -> str | None:
    """probe 结果文件是旧格式（没记 api）/ 当时的 API 版本与现在的仕様不同 → ★ 文字（要重新做）；没问题 → None。"""
    old, now = str(rec.get("api") or ""), _api_now(env)
    if not old:
        return f"★ 检查结果是旧格式：重新做 {REDO[env]}"
    if now is None:
        return f"★ 数据目录的 tachibana_spec.json 读不了：先修好它，再重新做 {REDO[env]}"
    if old != now:
        return f"★ API 版本变了（{old} → {now}）：重新做 {REDO[env]}"
    return None


def _general_ok() -> bool:
    from .brokers.tachibana import tax_general_ok_file
    return tax_general_ok_file().exists()


def _tax_text(tax: str) -> str:
    """T5：1 特定 → 正常；3 一般 → ★ 要你确认（要自己申告；执行器默认不发）；5 / 6 NISA → ★ 执行器不发。只显示、不改门槛。"""
    from .brokers.tachibana import TAX_NAMES, tax_general_ok_file
    if tax == "":
        return "还不知道（本番只读检查之后显示）；源泉徴収あり / なし 看不出来，开户时选「特定口座（源泉徴収あり）」并在立花网站上确认"
    if tax == "1":
        return "特定口座（执行器按它发单；源泉徴収あり / なし 从 API 看不出来，请在立花网站上确认是「あり」）"
    if tax == "3":
        ok = tax_general_ok_file().exists()
        return ("一般口座（你已同意用它：要自己申告）" if ok else
                "★ 一般口座：执行器默认不发单（要自己申告）。确认要用 → 在对话里明确说；或在立花开特定口座（源泉徴収あり）")
    return f"★ {TAX_NAMES.get(tax, '代码 ' + tax)}：执行器不在这个区分下单（NISA 不用，〔72〕③），单会被挡 → 请在立花确认口座区分"


def _age(at, today: dt.date) -> str:
    """结果文件的 at（"YYYY-MM-DD HH:MM JST"）→ 「（N 天前做的）」；读不出 → ""。只显示、不判定。"""
    try:
        n = (today - dt.date.fromisoformat(str(at or "")[:10])).days
    except ValueError:
        return ""
    return "（今天做的）" if n == 0 else f"（{n} 天前做的）"


def _wake(sched: str) -> tuple[bool | None, str]:
    """pmset -g sched 的「Repeating power events」里有没有工作日（或每天）07:40 之前的唤醒 / 开机。"""
    rep = sched.split("Repeating power events:", 1)[1] if "Repeating power events:" in sched else ""
    rep = rep.split("Scheduled power events:", 1)[0]
    lines = [ln.strip() for ln in rep.splitlines() if "wake" in ln.lower() or "poweron" in ln.lower()]
    if not lines:
        return False, f"★ 没有设定：在终端运行 {WAKE_CMD}（要输入 Mac 的登录密码；Mac 接着电源、不合盖）"
    ln = lines[0]
    m = re.search(r"at\s+(\d{1,2}):(\d{2})\s*([AP]M)?", ln, re.I)
    days = ln.lower()
    if not m or not ("weekday" in days or "every day" in days):
        return None, f"有重复唤醒、读不出是不是工作日 07:40 之前（{ln}）：请确认，或重设 {WAKE_CMD}"
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
    if ap:
        h = h % 12 + (12 if ap == "PM" else 0)
    if (h, mi) <= (7, 40):
        return True, f"已设定：{ln}"
    return False, f"★ 唤醒时间晚于 07:40（{ln}）：{WAKE_CMD}"


def _kc_readable(add, run, have: list[str]) -> None:
    """TA-07：用和定时任务（适配器）相同的命令（security find-generic-password … -w）试读一次钥匙串里有的条目。
    值直接丢进 /dev/null（不进这个程序、不打印、不记录），只看退出码：能读出 / 钥匙串锁着、不允许交互 / 出错。"""
    from .brokers.tachibana import KC_LOCKED, KC_NONE, keychain_hint, keychain_why
    if not have:
        return
    why = {}
    for svc in have:
        try:
            r = run(["security", "find-generic-password", "-s", svc, "-a", "qbreak", "-w"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=15)
            why[svc] = "" if r.returncode == 0 else keychain_why(r.returncode, r.stderr or "")
        except subprocess.TimeoutExpired:            # 弹了授权框 / 等解锁超时：当作锁着、不允许交互
            why[svc] = KC_LOCKED
        except (OSError, subprocess.SubprocessError):
            why[svc] = KC_NONE
    name = "⑥ 钥匙串能读出（和定时任务相同的读法）"
    if all(w == KC_NONE for w in why.values()):
        add("准备", name, None, "没有 security 命令：跳过")
        return
    bad = {s: w for s, w in why.items() if w}
    add("准备", name, not bad,
        ("试读了 " + "、".join(have) + "：都能读出（值没有显示、也没留在这个程序里；从这个终端试读，定时任务在登录后的桌面会话里用同样的读法）")
        if not bad else "★ " + "；".join(keychain_hint(s, w) for s, w in bad.items()))


def _ver(v: str) -> tuple[int, int] | None:
    m = re.search(r"v(\d+)r(\d+)", str(v or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _spec_override(add) -> None:
    """TA-10 / OPS-05：数据目录的仕様覆盖文件（tachibana_spec.json）生效中的键；base_live / base_demo 的版本段和代码默认不同 → ★。"""
    from .brokers.tachibana import override_info
    name = "⑥ 仕様覆盖文件（数据目录的 tachibana_spec.json）"
    try:
        info = override_info()
    except Exception as e:                           # noqa: BLE001
        add("准备", name, False, f"★ 读不了（{type(e).__name__}）：修好或删掉 {paths.home() / 'tachibana_spec.json'}（删掉 = 用代码默认的仕様）")
        return
    if info is None:
        add("准备", name, True, "没有（用代码默认的仕様）")
        return
    if info["stale"]:
        txt = "；".join(f"{k} 指向 {old or '?'}，代码默认是 {new}"
                       + ("（★ 覆盖文件还指向旧版本）" if (_ver(old) or (0, 0)) < (_ver(new) or (0, 0)) else "（比代码新：代码还没更新到这个版本）")
                       for k, old, new in info["stale"])
        add("准备", name, False, f"★ {txt}：对着官方仕様書核对后，从 {info['path']} 删掉这个键（或改成对的版本），再重新做 probe")
        return
    add("准备", name, True, ("生效中，覆盖的键：" + "、".join(info["keys"]) if info["keys"] else "有文件，但和代码默认一样（不起作用）")
        + (f"；★ 不认识的键（不读）：{'、'.join(info['unknown'])}" if info["unknown"] else ""))


def _clock(run) -> tuple[bool | None, str]:
    """TA-16：Mac 的时钟准不准（立花的 p_sd_date 要在服务器时间 ±30 秒内；差了登录 / 发单都被拒，p_errno=8）。
    sntp -t 3 time.apple.com（只读，只查偏差）→ 偏差 ≤ 10 秒 OK；查不了 → systemsetup -getusingnetworktime（自动对时开着没有）→ 再不行 None。"""
    fix = "系统设置 → 通用 → 日期与时间 → 打开「自动设置」"
    rc, out = _cmd(run, ["sntp", "-t", "3", "time.apple.com"])
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*\+/-", out or "") if rc == 0 else None
    if m:
        off = float(m.group(1))
        if abs(off) <= 10:
            return True, f"和 time.apple.com 差 {off:+.2f} 秒"
        return False, f"★ Mac 的时钟和 time.apple.com 差 {off:+.1f} 秒（立花要求 30 秒以内，差 10 秒就该修）：{fix}"
    rc2, out2 = _cmd(run, ["systemsetup", "-getusingnetworktime"])
    low = (out2 or "").lower()
    if rc2 == 0 and "network time:" in low:
        if low.split("network time:", 1)[1].strip().startswith("on"):
            return True, "自动对时开着（systemsetup；sntp 没查到偏差）"
        return False, f"★ 自动对时关着：{fix}"
    if rc is None and rc2 is None:
        return None, "不是 macOS（没有 sntp / systemsetup）：跳过"
    return None, f"查不了（sntp 连不上 time.apple.com / systemsetup 要管理员权限）：请自己确认 {fix}"


DRYRUN_CMD = "bash scripts/liveu.sh --broker tachibana --dry-run --no-clock"
DOCTOR_CMD = "bash scripts/liveu.sh doctor"


# LU-13：「准备」里再加三项（门槛数字不变；只读）：本番 dry-run 跑通过、doctor 通过、Mac 的时区是日本
def _dryrun(add, today: dt.date) -> None:
    """本番 dry-run 跑通过：数据目录 out/ 里 dry-run 账本的运行状态文件 ok，或 dry-run 账本里至少处理过一个决策日。"""
    from . import run_status as RS
    name = "⑤ 本番 dry-run 跑通过（登录 / 对账 / 决策，只算不发单）"
    rec = RS.read("tachibana_dryrun") or {}
    hist = ((_book("tachibana_dryrun").get("state") or {}).get("history") or [])
    when = str(rec.get("at") or "")[:16].replace("T", " ")
    if rec.get("ok") is True:
        add("准备", name, True, f"上次 {when} 跑完{_age(when, today)}")
    elif hist:
        add("准备", name, True, f"dry-run 账本处理过 {len(hist)} 个决策日（最近 {hist[-1][0]}）"
            + (f"；★ 上次 {when} 停下：{rec.get('error') or '原因见数据目录 logs/'}（再做一次：{DRYRUN_CMD}）"
               if rec.get("ok") is False else ""))
    elif rec:
        add("准备", name, False, f"★ 上次 {when} 没跑通：{rec.get('error') or '原因见数据目录 logs/'}：修好后再做 {DRYRUN_CMD}")
    else:
        add("准备", name, False, f"★ 还没做：{DRYRUN_CMD}（本番登录、读持仓与余力、打印会下的单，不发；用单独的 dry-run 账本，不动实盘账本）")


def _timezone(add, run) -> None:
    """Mac 的时区是日本（date +%z = +0900）：launchd 的定时任务按 Mac 的本地时间触发。读不出 → None。
    run.py 一启动就把这个进程的 TZ 设成 Asia/Tokyo（_pin_jst）→ 子进程不带 TZ 跑 date，才看得到 Mac 系统设置的时区。"""
    rc, out = _cmd(run, ["date", "+%z"], env={k: v for k, v in os.environ.items() if k != "TZ"})
    z = (out or "").strip()
    name = "⑦ Mac 的时区（定时任务按 Mac 的本地时间触发）"
    if rc != 0 or not re.fullmatch(r"[+-]\d{4}", z):
        add("准备", name, None, "查不了（没有 date 命令 / 读不出）：请自己确认 系统设置 → 通用 → 日期与时间 → 时区 是东京")
    elif z == "+0900":
        add("准备", name, True, "日本时间（+0900）")
    else:
        add("准备", name, False, f"★ Mac 的时区是 {z}（不是日本 +0900）：07:40 / 08:35 / 09:05 / 09:20 的定时任务会按这个时区错开 → "
                                 "系统设置 → 通用 → 日期与时间 → 时区选「东京」，然后重新跑 bash scripts/mac_setup.sh")


def _doctor(add, today: dt.date) -> None:
    """doctor 通过：数据目录 out/doctor.json（bash scripts/liveu.sh doctor 写；run.py _doctor_result）；没做过 → None（只提醒）。"""
    from . import run_status as RS
    name = "⑥ doctor（Python / 依赖 / 外网）"
    dr = RS.peek_json(paths.out_dir() / "doctor.json")
    if not dr:
        add("准备", name, None, f"还没做过（只读，1 分钟）：{DOCTOR_CMD}")
    elif dr.get("ok") is True:
        add("准备", name, True, f"上次 {str(dr.get('at') or '—')[:16].replace('T', ' ')} 通过{_age(dr.get('at'), today)}")
    else:
        probs = [str(x) for x in dr.get("problems") or []] if isinstance(dr.get("problems"), list) else []
        add("准备", name, False, f"★ 上次 {str(dr.get('at') or '—')[:16].replace('T', ' ')} 没通过"
            + (f"：{'；'.join(probs)}" if probs else "") + f"（修好后再做 {DOCTOR_CMD}；依赖坏了 → bash scripts/mac_setup.sh）")


def _alerts(add, run, agents: Path, rc_list: int | None, listing: str) -> None:
    """⑧ 人不在 Mac 前也知道出事：手机通知通道、外部心跳、09:30 自检任务（只查钥匙串里有没有，不取出值；不发通知）。"""
    from . import notify as NT

    def kc(name: str):                                # 钥匙串里有没有（定时任务读不到 ~/.zshrc 的环境变量 → 只看钥匙串）
        return NT.configured(name, run=run, env=False)
    env_only = "（环境变量有设置，但定时任务读不到 ~/.zshrc 的环境变量）"
    wh, em = kc("webhook"), kc("email")
    if wh is None and em is None:
        add("准备", "⑧ 手机通知通道（webhook / 邮件）", None, "不是 macOS（没有 security 命令）：跳过")
    elif wh or em:
        add("准备", "⑧ 手机通知通道（webhook / 邮件）", True,
            "钥匙串里有 " + "、".join(s for s, x in (("qbreak-webhook", wh), ("qbreak-smtp", em)) if x)
            + "（只查了有没有；发一条试试：bash scripts/liveu.sh notify-test）")
    else:
        add("准备", "⑧ 手机通知通道（webhook / 邮件）", False,
            "★ 钥匙串里没有 qbreak-webhook / qbreak-smtp"
            + (env_only if os.environ.get("QBREAK_WEBHOOK") or os.environ.get("QBREAK_SMTP") else "")
            + "：邮件（Gmail）→ 在你自己的终端运行 bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup（应用专用密码输入时不显示，存好后发一封测试邮件）；"
              "或在 Discord / Slack / ntfy 建一个只给自己的通知地址，在终端运行 security add-generic-password -s qbreak-webhook -a qbreak -w"
              "（回车后输入，不要贴进聊天），再 bash scripts/liveu.sh notify-test")
    hb = kc("heartbeat")
    if hb is None:
        add("准备", "⑧ 外部心跳（Mac 没跑的提醒）", None, "不是 macOS（没有 security 命令）：跳过")
    elif hb:
        add("准备", "⑧ 外部心跳（Mac 没跑的提醒）", True, "钥匙串里有 qbreak-heartbeat（只查了有没有；每个交易日 09:30 自检时 ping）")
    else:
        add("准备", "⑧ 外部心跳（Mac 没跑的提醒）", False,
            "★ 钥匙串里没有 qbreak-heartbeat" + (env_only if os.environ.get("QBREAK_HEARTBEAT") else "")
            + "：在 healthchecks.io 之类的服务建一个「周一至五 09:30 JST、宽限 30 分钟」的检查（时区选 Asia/Tokyo），"
              "把 ping 地址存进钥匙串：security add-generic-password -s qbreak-heartbeat -a qbreak -w（回车后输入，不要贴进聊天）；"
              "Mac 关机 / 睡着 / 断网时那边会推送到手机")
    lb = "com.qbreak.watchdog"
    has = (agents / f"{lb}.plist").exists()
    loaded = rc_list != 0 or lb in listing
    if has and loaded:
        add("准备", "⑧ 09:30 自检任务（com.qbreak.watchdog）", True, "已装" + ("" if rc_list == 0 else "（没有 launchctl：只看了文件）"))
    else:
        add("准备", "⑧ 09:30 自检任务（com.qbreak.watchdog）", False,
            f"★ {'没装' if not has else '没加载'}：bash scripts/mac_setup.sh（或 bash scripts/install_launchd_watchdog.sh）")


def check(agents=None, run=subprocess.run, today: dt.date | None = None) -> list[dict]:
    """逐项检查 → [{"group": 门槛 / 准备 / 参考, "name", "ok": True / False / None（只供参考）, "text"}]。today：测试注入（JST 的日期）。"""
    from .calendar_jp import now_jst
    from .live_unified import UNKNOWN, flows
    today = today or now_jst().date()
    out: list[dict] = []

    def add(group: str, name: str, ok, text: str) -> None:
        out.append({"group": group, "name": name, "ok": ok, "text": text})

    agents = Path(agents or os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")
    paper, live = _book("paper"), _book("tachibana")
    days = compare_days(paper, _journal("paper"))
    ok1, txt1 = _streak_item(days, today, _paper_stopped(agents, days))
    add("门槛", f"① Mac 模拟操盘与云端连续 ≥ {STREAK_NEED} 个交易日一致", ok1, txt1)
    unk = [(br, f"{name} {o.get('cid')} {o.get('side')} {o.get('ticker')}")
           for name, br, b in (("模拟账户", "paper", paper), ("立花", "tachibana", live))
           for o in b.get("orders") or [] if o.get("status") in UNKNOWN]
    how = "；".join(f"bash scripts/liveu.sh --broker {br} --resolve <cid> --filled <股数> --px <均价>"   # 经 liveu.sh：数据目录 ~/.qbreak/home
                   for br in dict.fromkeys(br for br, _ in unk))
    add("门槛", "② 没有状态不明的单", not unk,
        "没有" if not unk else "★ " + "；".join(t for _, t in unk) + f"（在立花的注文一覧确认后：{how}；没成交填 0）")
    seen = sorted(set((paper.get("halt_seen") or []) + (live.get("halt_seen") or [])))
    add("门槛", "③ HALT 演练过一次", bool(seen),
        f"执行器在 HALT 存在时运行过：{'、'.join(seen[-3:])}" if seen
        else "还没有：在 Mac 对话里说「做一次 HALT 演练」（bash scripts/liveu.sh halt-drill；不动真的 HALT）")
    demo = read_json(paths.out_dir() / "tachibana_probe_demo.json", {}) or {}
    ot = demo.get("order_test") or {}
    if not ot:
        add("门槛", "④ デモ发单检查（约定字段、余力变化、按注文番号撤单）", False,
            "还没做：开户、登记デモ用的公钥之后 bash scripts/liveu.sh probe --demo --order-test（デモ环境 9:00〜15:00 / 15:10〜）")
    else:
        miss = ot.get("fields_missing") or []
        olb, oc = ot.get("opening_limit_buy"), ot.get("opening_cancel")
        if "opening_limit_buy" not in ot:            # 旧的检查（2026-10-09 之前）没测执行器最常用的单型 → 要重新做
            olb_txt = "★ 没测（旧的检查）"
        elif olb in ACCEPTED:
            olb_txt = "受理、" + ("撤单成功" if oc else "已成交（不用撤）" if oc is None else "★ 撤单没成功")
        else:
            olb_txt = f"★ 没受理（{olb or '—'}）"
        txt = (f"{demo.get('at', '—')}{_age(demo.get('at'), today)}：约定字段 {'齐' if not miss else '★ 缺 ' + '、'.join(miss)}；"
               f"余力 / 持仓变化 {'有' if ot.get('cash_or_pos_changed') else '★ 没看到'}；"
               f"按注文番号撤单 {'成功' if ot.get('cancel') else '★ 没成功'}；寄付指値买 {olb_txt}")
        st = _stale("demo", demo)
        add("门槛", "④ デモ发单检查（约定字段、余力变化、按注文番号撤单）",
            bool(ot.get("ok")) and olb in ACCEPTED and oc is not False and not st, f"{st}（上次 {txt}）" if st else txt)
    lv = read_json(paths.out_dir() / "tachibana_probe_live.json", {}) or {}
    if not lv:
        add("准备", "⑤ 本番只读检查（登录 / 取价 / 持仓 / 余力 / 立花能不能买）", False, "还没做：bash scripts/liveu.sh probe（只读，不发单）")
    else:
        txt = (f"{lv.get('at', '—')}{_age(lv.get('at'), today)}："
               + ("全部通过" if lv.get("ok") else "★ 没通过：" + "、".join(k for k, v in (lv.get("steps") or {}).items() if not v)))
        if lv.get("ok") and not lv.get("price_checked"):     # 只提醒（不算没通过）：盘外的检查只看到前日終値，现价的字段名没确认
            txt += "；★ 现价字段还没在交易时间里确认过：交易日 09:00〜15:30 再做一次 bash scripts/liveu.sh probe（只读）"
        st = _stale("live", lv)
        add("准备", "⑤ 本番只读检查（登录 / 取价 / 持仓 / 余力 / 立花能不能买）", bool(lv.get("ok")) and not st,
            f"{st}（上次 {txt}）" if st else txt)
    _dryrun(add, today)
    have = []
    for svc, label, env in KEYCHAIN:
        rc, _ = _cmd(run, ["security", "find-generic-password", "-s", svc, "-a", "qbreak"])   # 不加 -w：不取出值
        name = f"⑥ {label}{' ' if label[-1].isascii() else ''}在钥匙串"
        if rc == 0:
            have.append(svc)
            add("准备", name, True, f"钥匙串里有 {svc}（只查了有没有）")
        elif rc is None:
            add("准备", name, None, "不是 macOS（没有 security 命令）：跳过")
        else:
            add("准备", name, False,
                f"★ 钥匙串里没有 {svc}" + ("（环境变量有设置，但定时任务读不到 ~/.zshrc 的环境变量）" if os.environ.get(env) else "")
                + f"：在终端运行 security add-generic-password -s {svc} -a qbreak -w（回车后输入，不要贴进聊天）")
    _kc_readable(add, run, have)
    key = Path(os.environ.get("TACHIBANA_PRIVATE_KEY") or Path.home() / ".qbreak" / "e_api_private_key.pem").expanduser()
    if not key.exists():
        add("准备", "⑥ 私钥文件", False, f"★ 没有 {key}：放「ｅ支店・API 利用設定」登记的公钥对应的私钥（chmod 600）")
    else:
        mode = key.stat().st_mode & 0o777
        add("准备", "⑥ 私钥文件", mode & 0o077 == 0,
            f"{key} 权限 {mode:o}" + ("" if mode & 0o077 == 0 else f"：★ 太宽，chmod 600 {key}"))
    has_crypto = importlib.util.find_spec("cryptography") is not None
    add("准备", "⑥ cryptography（解密虚拟 URL）", has_crypto, "已装" if has_crypto else "★ 没装：bash scripts/mac_setup.sh")
    _spec_override(add)
    ok_, txt_ = _clock(run)
    add("准备", "⑥ Mac 的时钟（立花要求和服务器差 30 秒以内）", ok_, txt_)
    _doctor(add, today)
    miss = [lb for lb in LIVE_LABELS if not (agents / f"{lb}.plist").exists()]
    rc_list, listing = _cmd(run, ["launchctl", "list"])
    unloaded = [lb for lb in LIVE_LABELS if lb not in miss and rc_list == 0 and lb not in listing]
    if not miss and not unloaded:
        txt = "已装" + ("" if rc_list == 0 else "（没有 launchctl：只看了文件）")
    else:
        txt = ("★ " + "；".join(x for x in ("没装 " + "、".join(miss) if miss else "", "没加载 " + "、".join(unloaded) if unloaded else "") if x)
               + "：开户、过了门槛之后 bash scripts/install_launchd_live_u.sh tachibana")
    add("准备", "⑦ 立花的定时任务（07:40 / 08:35 / 09:05 / 09:20 + 前一晚 20:00 的预检）", not miss and not unloaded, txt)
    rc, sched = _cmd(run, ["pmset", "-g", "sched"])
    if rc is None:
        add("准备", "⑦ Mac 工作日早上自动唤醒", None, "不是 macOS（没有 pmset）：跳过")
    elif rc != 0:
        add("准备", "⑦ Mac 工作日早上自动唤醒", None, "pmset -g sched 读不出：请自己确认")
    else:
        ok, txt = _wake(sched)
        add("准备", "⑦ Mac 工作日早上自动唤醒", ok, txt)
    _timezone(add, run)
    _alerts(add, run, agents, rc_list, listing)
    tax = str(lv.get("tax") or "")
    tax_ok = None if tax == "" else (tax == "1" or (tax == "3" and _general_ok()))   # 〔77〕C 审查：区分不对时执行器不发单 → 门槛不能算过
    add("准备" if tax_ok is False else "参考", "口座课税区分", tax_ok, _tax_text(tax))
    arm = paths.arm_state()                           # 和立花适配器同一个判断（UX-12）：内容是 ARMED 才算
    add("参考", "ARM（解锁发单）", None, {
        "file": "已解锁（ARM 文件内容 ARMED；要停用 = 删掉它或建 HALT）",
        "env": "已解锁（环境变量 QBREAK_ARM=ARMED；只对这个终端有效，定时任务看的是 ARM 文件）",
        "bad": "★ ARM 文件在，但内容不是 ARMED：适配器不认，单会被挡（过了门槛、你明确说之后才改成 ARMED）",
    }.get(arm, "未解锁（过了门槛、你在对话里明确说之后才建；不会自动清空）"))
    add("参考", "HALT", None, f"★ 生效中（{paths.halt_file()}）" if paths.halt_file().exists() else "不存在")
    pwb = paths.state_dir() / "second_pw_bad.json"         # OPS-12：第二暗証被拒之后，执行器不再用同一个值发单（直到重新存钥匙串）
    if pwb.exists():
        at = str((read_json(pwb, {}) or {}).get("at") or "")[:16].replace("T", " ")
        add("准备", "⑥ 第二暗証番号", False, f"★ {at} 被立花拒了：之后执行器不再发单（连错几次会锁取引暗証）→ 在终端运行 "
            "security add-generic-password -U -s qbreak-tachibana-2nd -a qbreak -w（回车后输入；存好后下一次运行自动再试一次）")
    fl = flows(live)
    add("参考", "登记过的入出金（立花）", None,
        f"{len(fl)} 笔，合计 {sum(float(f.get('jpy') or 0) for f in fl):+,.0f} 円" if fl else "没有")
    _precheck_ref(add, live, today)
    return out


def _precheck_ref(add, live: dict, today: dt.date) -> None:
    """参考（C-04 / B5）：前一晚预检的上次结果、立花的预告（交付書面的更新预定日、API 新版本）还要不要动手。只读、不算门槛。"""
    from . import precheck as PC
    pr = PC.last_result()
    rem = PC.reminders(PC.merge(live.get(PC.KEY), pr.get(PC.KEY)), _api_now("live") or "", today)
    if pr:
        txt = (f"上次 {str(pr.get('at') or '—')[:16].replace('T', ' ')}："
               + ("通过" if pr.get("ok") else "★ 没通过：" + "；".join(str(x) for x in pr.get("reasons") or [])))
    else:
        txt = ("还没做过（装了立花本番之后每个交易日的前一晚 20:00 自动做；手动：bash scripts/liveu.sh precheck --force，"
               "会登录立花一次 → 可能收到一封登录通知邮件）")
    add("参考", "前一晚预检 / 立花的预告（交付書面、API 版本）", None, txt + ("；" + "；".join(rem) if rem else "；没有要动手的预告"))


def report(items: list[dict]) -> tuple[str, bool]:
    """给人看的几行 + 门槛与准备是否全部满足（None = 跳过 / 只供参考，不算）。"""
    mark = {True: "OK", False: "★ 未完成", None: "—"}
    lines, cur = [], None
    for it in items:
        if it["group"] != cur:
            cur = it["group"]
            lines.append({"门槛": "【上线门槛】（2026-09-26 采用；全部满足才上本番）", "准备": "【本番运行的准备】",
                          "参考": "【参考】"}[cur])
        txt = it["text"][2:] if it["ok"] is False and it["text"].startswith("★ ") else it["text"]
        lines.append(f"  [{mark[it['ok']]}] {it['name']}：{txt}")
    need = [it for it in items if it["group"] in ("门槛", "准备") and it["ok"] is not None]
    ok = all(it["ok"] for it in need)
    lines.append("全部满足：可以在对话里明确说「上实盘」（建 ARM、先用较小金额跑 1〜2 周）" if ok
                 else "还没全部满足（★ 的几项）；这个检查只读，什么都没改")
    return "\n".join(lines), ok


def save(items: list[dict], ok: bool | None = None) -> None:
    """〔77〕C UX-15：最近一次的检查结果 → 数据目录 out/gate.json（面板「上线准备」卡片读；只放名字、✓/✗ 与一句话，不含密钥）。"""
    from .calendar_jp import now_jst
    from .utils import write_json
    need = [it for it in items if it["group"] in ("门槛", "准备") and it["ok"] is not None]
    write_json(paths.out_dir() / "gate.json", {"at": now_jst().strftime("%Y-%m-%d %H:%M"),
                                               "ok": all(it["ok"] for it in need) if ok is None else ok,
                                               "items": [{k: it[k] for k in ("group", "name", "ok", "text")} for it in items]})


def load_saved() -> dict:
    from .utils import read_json
    return read_json(paths.out_dir() / "gate.json", {}) or {}

