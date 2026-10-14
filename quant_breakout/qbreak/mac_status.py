"""mac_status.py — Mac 上 qbreak 的状态一览（菜单栏小图标 / 每 15 分钟的检查；只读，除了 --ensure-phone 的自动修复）。

  python -m qbreak.mac_status --write          → 数据目录 out/mac_status.json（菜单栏 App 每 2 分钟叫一次、读这个文件）
  python -m qbreak.mac_status --ensure-phone   → 手机访问断了就自动重新打开 Tailscale Serve（qbreak/panel_phone.ensure），修不好通知一次
每一项 {name, level: ok / warn / bad / info, text}；整体 level = 最差的一项。只读执行器自己的文件、launchctl list、tailscale status，
不连券商、不下单、不读密钥。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from . import paths
from .calendar_jp import JST, is_trading_day, now_jst, prev_trading_day
from .utils import read_json, write_json

ORDER = {"ok": 0, "info": 0, "warn": 1, "bad": 2}
PANEL_URL = "http://127.0.0.1:8765/"
# 装了就应该一直是「已加载」的定时任务（plist 在 LaunchAgents 里却没加载 = 被卸掉 / 停用了：2026-10 测试误停用过 com.qbreak.login）
WATCH_AGENTS = ("com.qbreak.liveu.paper", "com.qbreak.liveu.morning", "com.qbreak.liveu.retry", "com.qbreak.liveu.open",
                "com.qbreak.liveu.open2", "com.qbreak.liveu.fills1", "com.qbreak.liveu.fills2", "com.qbreak.precheck",
                "com.qbreak.news", "com.qbreak.jquants", "com.qbreak.login", "com.qbreak.panel", "com.qbreak.watchdog",
                "com.qbreak.wakehold", "com.qbreak.menubar", "com.qbreak.awake")


def _agents_dir() -> Path:
    return Path(os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")


def _loaded(run=subprocess.run) -> set[str] | None:
    try:
        r = run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {ln.split()[-1] for ln in r.stdout.splitlines() if ln.strip() and ln.split()[-1].startswith("com.qbreak.")}


def _agents_item(run=subprocess.run) -> dict:
    ag = _agents_dir()
    have = [lb for lb in WATCH_AGENTS if (ag / f"{lb}.plist").exists()]
    loaded = _loaded(run)
    if loaded is None:
        return {"name": "定时任务", "level": "info", "text": "（这台机器没有 launchctl：不检查）"}
    miss = [lb for lb in have if lb not in loaded]
    if miss:
        return {"name": "定时任务", "level": "bad",
                "text": "没加载：" + "、".join(m.replace("com.qbreak.", "") for m in miss)
                        + " → 在 Mac 对话里说「拉代码并更新」（bash scripts/mac_setup.sh 会重新加载）"}
    return {"name": "定时任务", "level": "ok", "text": f"{len(have)} 个都在"}


def _book_item(tag: str, now: dt.datetime) -> dict:
    from . import run_status as RS
    from .live_unified import morning_done
    name = "模拟操盘" if tag == "paper" else "立花（本番）"
    book = RS.peek_json(paths.state_dir() / f"live_unified_{tag}.json") or {}
    st = book.get("state") or {}
    if not st:
        return {"name": name, "level": "info", "text": "还没有账本"}
    rec = RS.read(tag) or {}
    ld = str(st.get("last_date") or "")
    today = now.date()
    if rec.get("ok") is False:
        return {"name": name, "level": "bad", "text": f"上次运行停下：{str(rec.get('error') or '原因不明')[:120]}"}
    if is_trading_day(today) and now.time() >= dt.time(8, 0):
        exp = prev_trading_day(today).isoformat()
        if ld < exp or (ld == exp and not morning_done(book, exp)):
            return {"name": name, "level": "bad", "text": f"今天早上的运行还没完成（上次决策 {ld or '—'}）"}
    sm = read_json(paths.out_dir() / f"live_unified_{tag}.json", {}) or {}
    cmp = sm.get("compare") or {}
    hist = st.get("history") or []
    eq = f"总权益 ¥{float(hist[-1][1]):,.0f}" if hist else ""
    if cmp.get("comparable") and not cmp.get("same") and not cmp.get("early") and not cmp.get("explained"):
        return {"name": name, "level": "warn", "text": f"★ 与云端模拟盘不一致（决策日 {ld}）{('；' + eq) if eq else ''}"}
    if sm.get("blocked") and sm.get("decided_on") == ld:
        return {"name": name, "level": "warn", "text": f"★ 这次的单没下：{str(sm['blocked'])[:100]}"}
    return {"name": name, "level": "ok", "text": f"决策日 {ld} 跑完" + (f"；{eq}" if eq else "")}


def _watchdog_item(tag: str, now: dt.datetime) -> dict | None:
    from . import run_status as RS
    wd = RS.peek_json(paths.out_dir() / f"watchdog_{tag}.json")
    if not wd:
        return None
    t = RS.ts(wd.get("at"))
    if t is None or t.astimezone(JST).date() != now.date():
        return None
    if wd.get("ok") is False:
        rs = wd.get("reasons")
        rs = [rs] if isinstance(rs, str) else [str(x) for x in (rs if isinstance(rs, list) else [])]
        return {"name": "09:30 自检", "level": "bad", "text": "没通过：" + ("；".join(rs) or "—")[:160]}
    return {"name": "09:30 自检", "level": "ok", "text": "通过"}


def _beat_item(tag: str) -> dict | None:
    """外部心跳（09:30 自检 ping 的；out/watchdog_<账本>.json 的 heartbeat，原因不含地址）：最后一次没发成 → bad；发了 → ok；
    没设置 / 没记 → 不显示（没设置由上线检查 ⑧ 管）（2026-10-14 G12）。"""
    from . import run_status as RS
    from .watchdog import beat_text
    wd = RS.peek_json(paths.out_dir() / f"watchdog_{tag}.json")
    hb = wd.get("heartbeat") if isinstance(wd, dict) else None
    if not isinstance(hb, dict):
        return None
    t = RS.ts(hb.get("at"))
    when = t.astimezone(JST).strftime("%m/%d %H:%M") if t else "—"
    bt = beat_text(hb)
    if bt:
        return {"name": "外部心跳", "level": "bad", "text": f"{when} {bt}"[:240]}
    if hb.get("state") == "sent":
        return {"name": "外部心跳", "level": "ok", "text": f"{when} 已发"}
    return None


def _charts_item(tag: str, now: dt.datetime) -> dict | None:
    """面板 K 线的最后一根是不是最近一个已收盘的交易日（qbreak/charts_refresh；2026-10-11 周五收盘后日线没反映的再发防止）。
    收盘后 2 小时内（补日线还在等 Yahoo）不算；没有 K 线文件 → 不显示。"""
    from . import charts_refresh as CR
    s = CR.stale(tag, now)
    if not s["have"]:
        return None
    name = "K 线" + ("（立花）" if tag == "tachibana" else "")
    grace = is_trading_day(now.date()) and CR.CLOSE_READY <= now.time() < CR.STALE_WARN
    if s["stale"] and not grace:
        return {"name": name, "level": "warn", "text": f"日线只到 {s['have']}（应有 {s['want']}）→ bash scripts/liveu.sh charts 补"}
    return {"name": name, "level": "ok", "text": f"日线到 {s['have']}"}


def _translate_item() -> dict | None:
    """消息标题的中文翻译（本机离线；qbreak/translate.py）：小工具没装 / 语言包没下载 → 提醒（通知照发、标题是原文）。"""
    from . import translate as TR
    s = TR.status()
    if not s["tool"]:
        return {"name": "翻译", "level": "info", "text": "翻译小工具没装（bash scripts/install_translate.sh）：通知照发、标题是原文"}
    miss = [k for k, v in (s.get("langs") or {}).items() if k == "en" and v != "installed"]   # 只翻英文（2026-10-11）
    if miss or not s.get("langs"):
        return {"name": "翻译", "level": "warn",
                "text": "语言包没下载（" + "、".join({"ja": "日本語", "en": "English"}.get(m, m) for m in miss) + "）：系统设置 → 通用 → 语言与地区 → 翻译语言 → 下载（含 中文（简体））"}
    return {"name": "翻译", "level": "ok", "text": "英文消息标题翻成中文（本机离线；日文保持原文）"}


def _phone_item() -> dict:
    from . import panel_phone as PP
    try:
        h = PP.health()
    except Exception as e:                                # noqa: BLE001
        return {"name": "手机访问", "level": "warn", "text": f"检查失败：{type(e).__name__}"}
    if not h["enabled"]:
        return {"name": "手机访问", "level": "info", "text": "没打开（Mac 对话里说「打开手机操作」）"}
    if h["ok"]:
        return {"name": "手机访问", "level": "ok", "text": f"正常：手机用 {h['url']}（不是 127.0.0.1）", "url": h["url"]}
    return {"name": "手机访问", "level": "bad", "text": "连不上：" + "；".join(h["problems"]), "url": h["url"]}


def build(now: dt.datetime | None = None, run=subprocess.run) -> dict:
    from . import panel_phone as PP
    now = (now or now_jst()).astimezone(JST)
    items = []
    if PP.halt_text():
        items.append({"name": "HALT", "level": "warn", "text": f"生效中：不下单（{PP.halt_text()}）"})
    tags = ["tachibana"] if paths.live_installed() else []
    if (paths.state_dir() / "live_unified_paper.json").exists() or not tags:
        tags.append("paper")
    for tag in tags:
        items.append(_book_item(tag, now))
        w = _watchdog_item(tag, now)
        if w:
            items.append(w)
        hb = _beat_item(tag)
        if hb:
            items.append(hb)
        c = _charts_item(tag, now)
        if c:
            items.append(c)
    items.append(_agents_item(run))
    tr = _translate_item()
    if tr:
        items.append(tr)
    items.append(_phone_item())
    from .panel_phone import listening
    items.append({"name": "操作面板", "level": "ok" if listening(8765) else "bad",
                  "text": f"{PANEL_URL}（只在这台 Mac 上）" if listening(8765) else "没在运行（bash scripts/install_launchd_panel.sh）"})
    level = max((it["level"] for it in items), key=lambda x: ORDER.get(x, 0), default="ok")
    if ORDER.get(level, 0) == 0:
        level = "ok"
    phone = next((it.get("url") for it in items if it["name"] == "手机访问" and it.get("url")), None)
    return {"at": now.strftime("%Y-%m-%d %H:%M"), "level": level, "items": items, "panel_url": PANEL_URL, "phone_url": phone,
            "page": str(paths.out_dir() / f"page_{tags[0]}.html"), "dashboard": str(paths.out_dir() / "dashboard.html"),
            "title": {"ok": "qbreak ✓", "warn": "qbreak !", "bad": "qbreak ✕"}[level]}


def path() -> Path:
    return paths.out_dir() / "mac_status.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m qbreak.mac_status")
    ap.add_argument("--write", action="store_true", help="写数据目录 out/mac_status.json（菜单栏 App 读）")
    ap.add_argument("--ensure-phone", action="store_true", help="手机访问断了就自动重新打开；修不好通知一次")
    ap.add_argument("--print", action="store_true", help="打印一览")
    a = ap.parse_args(argv)
    if a.ensure_phone:
        from . import panel_phone as PP

        def _notify(subject: str, text: str) -> None:
            try:
                from . import notify
                notify.send(subject, text, level="warn")
            except Exception:                             # noqa: BLE001
                pass
        try:
            h = PP.ensure(notify=_notify)
            if h.get("repaired"):
                print("手机访问：Serve 的设置不在了 → 已自动重新打开")
        except Exception as e:                            # noqa: BLE001
            print(f"手机访问的检查失败（不影响别的）：{type(e).__name__}")
    s = build()
    if a.write:
        write_json(path(), s)
    if a.print or not (a.write or a.ensure_phone):
        print(f"{s['title']}（{s['at']} JST）")
        for it in s["items"]:
            print(f"  [{ {'ok': '✓', 'info': '·', 'warn': '!', 'bad': '✕'}.get(it['level'], '?') }] {it['name']}：{it['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
