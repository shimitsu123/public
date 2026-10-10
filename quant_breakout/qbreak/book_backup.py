"""book_backup.py — 执行器账本的备份 / 恢复 / 读坏时不新开（缺口盘点 B4：LU-09、OPS-03）。

备份放数据目录的 state/backup/（Mac：~/.qbreak/home/state/backup/；仓库的 var/state/backup/ 在 .gitignore 里、不入库：含持仓与现金）：
  live_unified_<账本>_<YYYYmmdd-HHMMSS>.json —— 每次执行器运行开始时（--status 不算）、登记成交（--resolve）/ 撤单 / 人工代下登记 /
  恢复之前各一份；同一分钟已经有一份、或内容和最近一份完全相同 → 不重复；只留最近 60 份（按时间删旧的）。
立花的账本（tachibana*）读坏了、或者不见了（但有备份 / .corrupt 文件在）→ problem() 给原因，执行器停下：
  不悄悄从 sim.json 的 ¥100 万重来（有持仓时会被持仓核对天天挡住，空仓时就悄悄从头开始）。模拟账户照旧（读坏 → 改名 .corrupt、从头开始）。
恢复（restore）：先把现在的账本也备份一份，再把选中的备份拷回；只在你明确说时运行（bash scripts/liveu.sh restore …）。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path

from . import paths
from .calendar_jp import now_jst
from .utils import atomic_write_text, setup_logging

log = setup_logging("book_backup")

KEEP = 60                                             # 每个账本只留最近几份
_STAMP = "%Y%m%d-%H%M%S"


def backup_dir() -> Path:
    return paths.state_dir() / "backup"


def _pat(book) -> re.Pattern:
    """这个账本的备份文件名：<账本文件名去掉 .json>_<YYYYmmdd-HHMMSS>.json（tachibana 与 tachibana_demo 不会互相混）。"""
    return re.compile(rf"^{re.escape(Path(book).stem)}_(\d{{8}}-\d{{6}})\.json$")


def list_backups(book) -> list[Path]:
    """这个账本的备份，新的在前。"""
    d = backup_dir()
    if not d.is_dir():
        return []
    pat = _pat(book)
    return sorted((p for p in d.iterdir() if p.is_file() and pat.match(p.name)), key=lambda p: p.name, reverse=True)


def _valid(text: str) -> bool:
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def backup(book, now=None, keep: int = KEEP, force: bool = False) -> Path | None:
    """账本存在（而且读得了）→ 复制一份到 state/backup/，返回备份的路径；没有账本 / 读不了 / 不用重复 → None。
    同一分钟已经有一份（force 时不看这条）或内容与最近一份相同 → 不重复；之后只留最近 keep 份。写不成只记 warning（不影响交易）。"""
    p = Path(book)
    try:
        if not p.is_file():
            return None
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        log.warning("账本没备份（读不了：%s）", e)
        return None
    if not _valid(text):
        log.warning("账本没备份（内容不是完整的 JSON：读坏的账本不覆盖备份）")
        return None
    now = now or now_jst()
    stamp = now.strftime(_STAMP)
    have = list_backups(p)
    if have:
        newest = have[0]
        if not force and _pat(p).match(newest.name).group(1)[:13] == stamp[:13]:
            return None                                       # 同一分钟已经备份过
        try:
            if newest.read_text(encoding="utf-8") == text:
                return None                                   # 内容没变
        except (OSError, UnicodeDecodeError):
            pass
    try:
        dst = backup_dir() / f"{p.stem}_{stamp}.json"
        n = 0
        while dst.exists() and n < 60:                        # force：同一秒已经有一份（内容不同）→ 往后挪一秒，不盖掉
            n += 1
            dst = backup_dir() / f"{p.stem}_{(now + dt.timedelta(seconds=n)).strftime(_STAMP)}.json"
        atomic_write_text(dst, text)
        for old in list_backups(p)[max(1, int(keep)):]:
            try:
                old.unlink()
            except OSError:
                pass
        return dst
    except OSError as e:
        log.warning("账本没备份（写不进 %s：%s）", backup_dir().name, e)
        return None


def restore_hint(broker_args: str = "tachibana") -> str:
    return (f"用 bash scripts/liveu.sh restore --broker {broker_args} --list 看备份，然后在 Mac 对话里说「恢复账本 <备份文件名>」"
            "（确实要从头开始，例如デモ：把数据目录 state/backup/ 里这个账本的备份与 state/ 里的 .corrupt 文件移走）")


def problem(book, broker_args: str = "tachibana") -> str | None:
    """立花的账本能不能安全地用：None = 能（读得了，或第一次运行：没有账本、也没有备份 / .corrupt 文件）。
    读不了 → 改名为 .corrupt.<时刻>（留着看）并返回原因；账本不见了但有 .corrupt 文件（别的程序读的时候已经改了名）或有备份 → 返回原因。
    原因里只有文件名（不带本机路径）。"""
    p = Path(book)
    if p.exists():
        try:
            text = p.read_text(encoding="utf-8")
            if _valid(text):
                return None
            why = "内容不是完整的 JSON"
        except (OSError, UnicodeDecodeError) as e:
            why = type(e).__name__
        bad = p.with_suffix(p.suffix + f".corrupt.{int(time.time())}")
        try:
            p.rename(bad)
        except OSError:
            bad = p
        log.error("账本读不了（%s），已改名为 %s", why, bad.name)
        return f"账本读不了（{why}；已改名为 {bad.name}）：不新开账本。" + restore_hint(broker_args)
    corrupt = sorted(p.parent.glob(p.name + ".corrupt.*"))
    if corrupt:
        return f"账本读不了（已改名为 {corrupt[-1].name}）：不新开账本。" + restore_hint(broker_args)
    baks = list_backups(p)
    if baks:
        return f"账本 {p.name} 不见了（最近的备份 {baks[0].name}）：不新开账本。" + restore_hint(broker_args)
    return None


def describe(fp: Path) -> str:
    """一份备份的一行说明：时刻、决策日、现金、持仓（只读）。"""
    m = re.search(r"_(\d{8})-(\d{6})\.json$", fp.name)
    at = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]} {m.group(2)[:2]}:{m.group(2)[2:4]}:{m.group(2)[4:]}" if m else "?"
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return f"{fp.name}  {at}  ★ 读不了"
    st = (d or {}).get("state") or {}
    pos = st.get("pos") or {}
    core = {t: int(u) for t, u in (st.get("core_units") or {}).items() if int(u or 0)}
    held = "、".join([f"{t} {int((v or {}).get('shares') or 0):,} 股" for t, v in pos.items()]
                    + [f"{t} {u:,} 口" for t, u in core.items()]) or "无"
    return (f"{fp.name}  备份于 {at} JST；决策日 {st.get('last_date') or '—'}；现金 ¥{float(st.get('cash_jpy') or 0):,.0f}；"
            f"持仓 {held}；单 {len(d.get('orders') or [])} 笔")


def restore(book, name: str, now=None) -> dict:
    """把备份 name（只给文件名）拷回成账本：先把现在的账本备份一份（读不了的改名 .corrupt），再拷回，账本里记一条事件。
    名字不对 / 没有这份 / 备份读不了 → ValueError / FileNotFoundError（什么都不改）。"""
    p = Path(book)
    name = str(name or "").strip()
    if not name or "/" in name or "\\" in name or not _pat(p).match(name):
        raise ValueError(f"备份文件名不对：{name or '（空）'}（要像 {p.stem}_20261009-074012.json；先 --list 看有哪些）")
    src = backup_dir() / name
    if not src.is_file():
        raise FileNotFoundError(f"没有这份备份：{name}（先 --list 看有哪些）")
    text = src.read_text(encoding="utf-8")
    if not _valid(text):
        raise ValueError(f"这份备份读不了：{name}")
    now = now or now_jst()
    saved = None
    if p.exists():
        if _valid(p.read_text(encoding="utf-8", errors="replace")):
            saved = backup(p, now, force=True)
        else:
            bad = p.with_suffix(p.suffix + f".corrupt.{int(time.time())}")
            p.rename(bad)
            saved = bad
    d = json.loads(text)
    d.setdefault("events", []).append({"at": now.isoformat(timespec="seconds"), "level": "warn",
                                       "msg": f"从备份恢复账本：{name}（用户确认）"
                                              + (f"；恢复前的账本另存为 {saved.name}" if saved else "")})
    atomic_write_text(p, json.dumps(d, ensure_ascii=False, indent=1))
    st = d.get("state") or {}
    return {"from": name, "saved": saved.name if saved else None, "decided_on": st.get("last_date"),
            "cash_jpy": st.get("cash_jpy")}
