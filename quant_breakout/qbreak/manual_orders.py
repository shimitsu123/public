"""manual_orders.py — 手动指令：页面上点「卖出 / 减仓 / 调闲置资金比例」→ 执行器在下一次能下寄付单的运行里下单
（2026-10-06 用户：「当持仓的时候可以在画面上点击卖出后 第二天或者当天就可以在立花自动交易 可以手动调节当前持仓股票百分比」）。

页面（qbreak/panel.py，只在本机 127.0.0.1）或命令行（run.py manual …）只把「指令」追加到数据目录的
manual/requests_<账本>.jsonl；真正下单的永远是执行器（qbreak/live_unified.py）：它在下一次能下寄付单的运行里把指令变成单，
经过与平时完全相同的闸门（HALT / ARM / 持仓核对 / 单笔上限 / 时间窗口）。所以手动卖出不会让第二天的持仓核对停下
（直接在立花网站上手动买卖才会）。

指令（kind）：
  sell     卖出一只个股的全部（寄付成行）；之后 block_days 个交易日不自动买回（默认 20；0 = 不限制；-1 = 一直不买回，直到 unblock）
  trim     把一只个股减到总权益的 pct %（按单元向下取整；只能减不能加 —— 引擎每只票只有一个成本 / 止损，加仓要另一套记账，
           而且「赢家加仓」研究没有通过）；减到 0 股等于卖出全部
  core     闲置资金（核心 ETF）比例：规则算出的目标额 × pct %（100 = 照规则；0 = 卖出、留现金）。一直有效，直到再改
  unblock  解除「不自动买回」
  cancel   撤回一条指令（target = 指令 id）：还没交给执行器的 → 马上撤；已经交给执行器的 → 之后不再重下
           （已经发到交易所的那一笔要撤，请在立花网站 / App 上撤；没撤的话开盘照常成交）
什么时候成交：执行器只在「成交日 08:55 之前」接手（寄付 = 开盘集合竞价；不在盘中下单）——
  成交日 08:55 之前点的 → 当天开盘卖（执行器 07:40 的运行；页面在 07:45〜08:45 之间点会马上叫执行器跑一次）；
  之后点的 → 下一个交易日开盘卖。闲置资金比例从下一次决策（下一个交易日早上的运行）起生效。
卖出所得：和规则卖出一样 —— 下一次决策里有新信号就买新票，没有就进闲置资金 ETF；想留现金就把闲置资金比例调低。
状态：pending 等执行器 → placed 已交给执行器（下一开盘的单）→ done 完成；rejected（理由）/ cancelled / superseded（规则也要卖）。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re

from . import paths
from .calendar_jp import is_trading_day, next_trading_day, now_jst

KINDS = ("sell", "trim", "core", "unblock", "cancel")
BLOCK_DEFAULT = 20                      # 手动卖出后多少个交易日不自动买回（默认）
BLOCK_MAX = 250
CUTOFF = dt.time(8, 55)                 # 寄付注文的最后时刻（与 live_unified.MORNING_CUTOFF 相同）
LABEL = {"sell": "卖出全部", "trim": "减仓", "core": "闲置资金比例", "unblock": "解除不买回", "cancel": "撤回指令"}
STATUS = {"pending": "等执行器", "placed": "已交给执行器", "done": "完成", "rejected": "没执行", "cancelled": "已撤回",
          "superseded": "规则也要卖（按规则的单）"}
REASON_TEXT = {"manual": "手动卖出", "manual_trim": "手动减仓"}
ACTIVE = ("pending", "placed")
_TICKER = re.compile(r"^[0-9][0-9A-Z]{3}\.T$")


def requests_path(tag: str):
    """指令文件（只追加）：<数据目录>/manual/requests_<账本标签>.jsonl —— 页面与命令行写，执行器读。"""
    return paths.sub("manual") / f"requests_{tag}.jsonl"


def normalize(req: dict) -> dict:
    """检查指令的格式（不看账本）：类型、代码、比例、天数。不合格 → ValueError（中文说明）。"""
    kind = str(req.get("kind") or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"不认识的指令 {kind!r}（可用：{'、'.join(KINDS)}）")
    out = {"kind": kind}
    if kind in ("sell", "trim", "unblock"):
        t = str(req.get("ticker") or "").strip().upper()
        if t and "." not in t:
            t += ".T"
        if not _TICKER.match(t):
            raise ValueError(f"代码 {t or '—'} 不对（东证 4 位代码，例 7203 或 7203.T）")
        out["ticker"] = t
    if kind in ("trim", "core"):
        try:
            pct = float(req.get("pct"))
        except (TypeError, ValueError):
            raise ValueError("要给比例（%）") from None
        if not math.isfinite(pct) or not 0 <= pct <= 100:
            raise ValueError("比例要在 0〜100% 之间")
        out["pct"] = round(pct, 2)
    if kind == "sell":
        bd = req.get("block_days", BLOCK_DEFAULT)
        try:
            bd = int(bd)
        except (TypeError, ValueError):
            raise ValueError("不买回的天数要是整数（0 = 不限制，-1 = 一直）") from None
        if not -1 <= bd <= BLOCK_MAX:
            raise ValueError(f"不买回的天数要在 -1〜{BLOCK_MAX} 之间")
        out["block_days"] = bd
    if kind == "cancel":
        tg = str(req.get("target") or "").strip()
        if not re.fullmatch(r"M[0-9A-Za-z\-]{6,60}", tg):
            raise ValueError("撤回要给指令 id（例 M20261006-081500-sell-7203）")
        out["target"] = tg
    note = " ".join(str(req.get("note") or "").split())
    if note:
        out["note"] = note[:200]
    out["source"] = re.sub(r"[^0-9A-Za-z_\-]", "", str(req.get("source") or "cli"))[:20] or "cli"
    return out


def append(tag: str, req: dict, clock=None) -> dict:
    """追加一条指令（先 normalize）；返回带 id / at 的记录。一行一条 JSON，O_APPEND 写入（同一台机器上多个写的人也不会互相覆盖）。"""
    rec = normalize(req)
    now = (clock or now_jst)()
    rec["at"] = now.isoformat(timespec="seconds")
    rec["id"] = f"M{now:%Y%m%d-%H%M%S}-{rec['kind']}" + (f"-{rec['ticker'].split('.')[0]}" if rec.get("ticker") else "")
    have = {r.get("id") for r in read_all(tag)}
    base, n = rec["id"], 2
    while rec["id"] in have:                                 # 同一秒的第二条
        rec["id"] = f"{base}-{n}"
        n += 1
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(requests_path(tag), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    return rec


def read_all(tag: str) -> list[dict]:
    """全部指令（按写入顺序）；坏行跳过。"""
    p = requests_path(tag)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("id") and r.get("kind") in KINDS:
            out.append(r)
    return out


def unseen(tag: str, book: dict | None) -> list[dict]:
    """指令文件里执行器还没读进账本的指令（页面显示「等执行器读」用）。"""
    have = set(((book or {}).get("manual") or {}).get("items") or {})
    return [r for r in read_all(tag) if r["id"] not in have]


def add_trading_days(d: dt.date, n: int) -> dt.date:
    x = d
    for _ in range(max(0, int(n))):
        x = next_trading_day(x)
    return x


def position_pct(state: dict) -> dict:
    """账本状态（dict）里每只个股占总权益的 %（按最近收盘 last_close；权益 = 历史最后一行）。"""
    hist = state.get("history") or []
    eq = float(hist[-1][1]) if hist else 0.0
    out = {}
    for t, p in (state.get("pos") or {}).items():
        px = float(p.get("last_close") or p.get("entry_px") or 0)
        out[t] = round(int(p.get("shares") or 0) * px / eq * 100, 2) if eq > 0 else None
    return out


def check(rec: dict, book: dict, tag: str | None = None) -> str | None:
    """下指令时对着执行器账本看一眼（页面 / 命令行用；执行器下单前还会按最新的收盘再查一次）：不行 → 理由；行 → None。
    tag：账本标签（给了就连指令文件里执行器还没读的指令一起看，避免同一只票点两次）。"""
    st = (book or {}).get("state") or {}
    waiting = unseen(tag, book) if tag else []
    pos = st.get("pos") or {}
    man = (book or {}).get("manual") or {}
    items = man.get("items") or {}
    k = rec["kind"]
    t = rec.get("ticker")
    if k in ("sell", "trim"):
        if t not in pos:
            return f"执行器的账本里没有 {t} 这只持仓（核心 ETF 用「闲置资金比例」调）"
        why = (st.get("pending_exit") or {}).get(t)
        if why:
            return f"{t} 已经排在下一开盘卖出全部（{REASON_TEXT.get(why, why)}），不用再点"
        act = [it for it in items.values() if it.get("ticker") == t and it.get("kind") in ("sell", "trim")
               and it.get("status") in ACTIVE and not it.get("cancel_req")]
        act += [r for r in waiting if r.get("ticker") == t and r.get("kind") in ("sell", "trim")
                and not any(c.get("kind") == "cancel" and c.get("target") == r["id"] for c in waiting)]
        if act:
            return f"{t} 已经有一条没处理完的手动指令（{act[-1].get('id')}）：先撤回它，或等它完成"
    if k == "trim":
        cur = position_pct(st).get(t)
        if cur is not None and rec["pct"] >= cur:
            return f"{t} 现在约占权益 {cur:.1f}%，目标 {rec['pct']:g}% 不低于现在：只能减不能加"
    if k == "unblock" and t not in (man.get("blocks") or {}):
        return f"{t} 没有「不自动买回」的设定"
    if k == "cancel":
        it = items.get(rec["target"])
        if it is None:
            if any(r["id"] == rec["target"] for r in waiting):
                return None
            return f"没有指令 {rec['target']}"
        if it.get("status") not in ACTIVE:
            return f"指令 {rec['target']} 已经是「{STATUS.get(it.get('status'), it.get('status'))}」，撤不了"
        if it.get("cancel_req"):
            return f"指令 {rec['target']} 已经在撤回中"
    return None


def next_window(now: dt.datetime) -> tuple[dt.date, bool]:
    """现在点下去，最早哪个交易日的开盘执行：(日期, 是不是今天)。成交日 08:55 之前 → 当天；之后 → 下一个交易日。"""
    d = now.date()
    if is_trading_day(d) and now.time() < CUTOFF:
        return d, True
    return next_trading_day(d), False


def due(tag: str, book: dict | None, now: dt.datetime | None = None) -> bool:
    """今天开盘之前还来得及（交易日、08:55 之前）、而且有要变成单的手动指令（还没读的卖出 / 减仓 / 撤回，或读了还在等的）
    → 早上的运行已经完成时，重试（08:35 / 页面）要再跑一次，把它加进今天开盘的单。"""
    now = now or now_jst()
    if not is_trading_day(now.date()) or now.time() >= CUTOFF:
        return False
    if any(r["kind"] in ("sell", "trim", "cancel") for r in unseen(tag, book)):
        return True
    items = ((book or {}).get("manual") or {}).get("items") or {}
    return any((it.get("status") == "pending" and it.get("kind") in ("sell", "trim"))
               or (it.get("status") == "placed" and it.get("cancel_req")) for it in items.values())


class Manual:
    """执行器里的手动指令：读指令文件 → 在下一次能下寄付单的运行里变成单 → 成交后记完成。状态都在执行器账本的 book["manual"]。"""

    def __init__(self, book: dict, tag: str, clock=None):
        self.book, self.tag, self.clock = book, tag, clock or now_jst
        m = book.setdefault("manual", {})
        m.setdefault("items", {})
        m.setdefault("blocks", {})
        m.setdefault("trims", {})
        m.setdefault("core_pct", 100.0)
        m["tag"] = tag
        self.m = m

    # ── 设定 ──
    @property
    def core_pct(self) -> float:
        return float(self.m.get("core_pct", 100.0))

    def block_reason(self, t: str, day) -> str | None:
        """t 在 day（决策用的 K 线日）还在「手动卖出后不自动买回」期内 → 理由。"""
        b = (self.m.get("blocks") or {}).get(t)
        if not b:
            return None
        until = b.get("until")
        d = day.date() if hasattr(day, "date") else day
        if until is None or str(d) <= str(until):
            return f"手动卖出后不自动买回（{'一直，直到解除' if until is None else f'到 {until}'}）"
        return None

    def _set_block(self, t: str, days: int, decided: dt.date, rid: str) -> None:
        if days == 0:
            return
        until = None if days < 0 else add_trading_days(decided, days).isoformat()
        self.m["blocks"][t] = {"until": until, "since": decided.isoformat(), "id": rid}

    def cancelling(self, t: str) -> bool:
        """t 有撤回中的手动指令（对账之后就撤）。"""
        return any(it.get("cancel_req") for it in self._active_for(t))

    def _active_for(self, t: str) -> list[dict]:
        return [it for it in self.m["items"].values()
                if it.get("ticker") == t and it.get("kind") in ("sell", "trim") and it.get("status") == "placed"]

    # ── 读指令 ──
    def ingest(self) -> list[tuple[str, str]]:
        """新指令 → items（pending）；core / unblock 当场生效；cancel：等执行器的马上撤，已交给执行器的记下「撤回中」
        （settle 在对账之后处理）。返回 [(级别, 说明)]。"""
        msgs = []
        items = self.m["items"]
        for r in read_all(self.tag):
            if r["id"] in items:
                continue
            it = {**r, "status": "pending"}
            items[r["id"]] = it
            k = r["kind"]
            if k == "core":
                self.m["core_pct"] = float(r["pct"])
                it.update(status="done", msg=f"闲置资金比例设为 {r['pct']:g}%（规则的目标额 × {r['pct']:g}%），从下一次决策起生效")
            elif k == "unblock":
                gone = self.m["blocks"].pop(r["ticker"], None)
                it.update(status="done" if gone else "rejected",
                          msg=f"{r['ticker']} 解除「不自动买回」" if gone else f"{r['ticker']} 本来就没有「不自动买回」")
            elif k == "cancel":
                tg = items.get(r["target"])
                if tg is not None and tg.get("status") == "pending":
                    tg.update(status="cancelled", msg=f"已撤回（{r['id']}）")
                    it.update(status="done", msg=f"撤回 {r['target']}")
                elif tg is not None and tg.get("status") == "placed" and not tg.get("cancel_req"):
                    tg["cancel_req"] = r["id"]
                    it.update(status="done", msg=f"撤回 {r['target']}：之后不再重下（已经发到交易所的那一笔要撤，请在立花网站 / App 上撤）")
                else:
                    it.update(status="rejected", msg=f"{r['target']} 不是「等执行器 / 已交给执行器」的指令，撤不了")
            else:
                it["msg"] = "等执行器在下一次能下寄付单的运行里处理"
            msgs.append(("info", f"手动指令 {r['id']}：{LABEL[k]}{(' ' + r['ticker']) if r.get('ticker') else ''}"
                                 f"{(' ' + format(r['pct'], 'g') + '%') if 'pct' in r else ''} → {it['msg']}"))
        return msgs

    def pending(self, kinds=("sell", "trim")) -> list[dict]:
        return sorted((it for it in self.m["items"].values() if it.get("status") == "pending" and it.get("kind") in kinds),
                      key=lambda x: x.get("at", ""))

    def has_work(self) -> bool:
        """还有要变成单的手动指令（等执行器的 sell / trim）或要处理的撤回。"""
        return bool(self.pending()) or any(it.get("cancel_req") and it.get("status") == "placed"
                                          for it in self.m["items"].values())

    # ── 变成单 ──
    def apply(self, eng, i: int, fill_day: dt.date, halted: bool = False) -> list[tuple[str, str]]:
        """第 i 根 K 线收盘后的决策之前（或同一决策补单之前）：等着的 sell / trim → 执行器的单。
        补跑的旧 K 线（成交日已经过了）不处理；成交日 08:55 之后、HALT 生效时也不动（下一次运行再看）。返回 [(级别, 说明)]。"""
        todo = self.pending()
        if not todo:
            return []
        now = self.clock()
        if now.date() > fill_day:
            return []
        if now.date() == fill_day and now.time() >= CUTOFF:
            return [("info", f"手动指令 {len(todo)} 条：已过 {fill_day} 的 {CUTOFF:%H:%M}，寄付来不及 → 下一个交易日早上的运行处理")]
        if halted:
            return [("warn", f"手动指令 {len(todo)} 条没处理：HALT 生效中（解除之后的下一次运行处理）")]
        st, out = eng.st, []
        decided = eng.gidx[i].date()
        for it in todo:
            t = it["ticker"]
            ps = st.pos.get(t)
            rule = st.pending_exit.get(t)
            if ps is None:
                it.update(status="rejected", msg="执行器的账本里没有这只持仓（已经卖掉了？）")
            elif rule == "manual":
                it.update(status="rejected", msg="已经排在开盘卖出全部（之前的手动卖出），不用再点")
            elif rule:
                it.update(status="superseded", decided_on=str(decided), fill_day=str(fill_day),
                          msg=f"规则也要在 {fill_day} 开盘卖出全部（{rule}）：按规则的单卖")
                if it["kind"] == "sell":
                    self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"])
            elif t in self.m["trims"]:
                it["msg"] = "同一只票的手动减仓还没成交完：等它成交后再处理"
                out.append(("info", f"手动指令 {it['id']}：{t} {it['msg']}"))
                continue
            else:
                self._place(eng, i, it, ps, decided, fill_day)
            out.append(("warn" if it["status"] == "rejected" else "info", f"手动指令 {it['id']}：{t} {it['msg']}"))
        return out

    def _place(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date) -> None:
        t, st = it["ticker"], eng.st
        sell_all, target, n_sell = it["kind"] == "sell", None, None
        if not sell_all:
            eq = float(eng.equity(i))
            px = float(eng._px_close(t, i))
            lot = int(eng.lots[eng.col[t]]) if t in eng.col else 100
            target = int(math.floor(eq * float(it["pct"]) / 100 / px / lot)) * lot if px > 0 and eq > 0 else 0
            n_sell = int(ps.shares) - max(0, target)
            if n_sell <= 0:
                it.update(status="rejected", msg=f"现在 {ps.shares:,} 股约占权益 {ps.shares * px / eq * 100:.1f}%，"
                                                 f"不高于目标 {it['pct']:g}%：不用减")
                return
            sell_all = target <= 0
        if sell_all:
            st.pending_exit[t] = "manual"
            if it["kind"] == "sell":
                self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"])
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(ps.shares),
                      msg=f"{fill_day} 开盘寄付成行卖出全部 {ps.shares:,} 股")
        else:
            self.m["trims"][t] = {"id": it["id"], "shares": int(n_sell), "target": int(target), "decided_on": str(decided)}
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(n_sell),
                      msg=f"{fill_day} 开盘寄付成行卖出 {n_sell:,} 股（{ps.shares:,} → {target:,} 股，约占权益 {it['pct']:g}%）")

    def trim_orders(self, st) -> list[tuple[str, int, str]]:
        """这次决策要下的减仓卖单 [(票, 股数, 指令 id)]：规则已经要全部卖的票不下（按规则的单）。"""
        out = []
        for t, x in list(self.m["trims"].items()):
            ps = st.pos.get(t)
            if ps is None:
                self.m["trims"].pop(t, None)
                continue
            if t in st.pending_exit:
                continue
            n = min(int(x["shares"]), int(ps.shares))
            if n > 0:
                out.append((t, n, x["id"]))
        return out

    # ── 成交 → 完成 ──
    def on_fill(self, ticker: str, reason: str, qty: int, px: float, bar: str, st) -> None:
        """执行器对账时每笔手动卖单（reason manual / manual_trim）的结果（qty = 0：没成交）。"""
        fill = {"qty": int(qty), "px": round(float(px), 2)}
        if reason == "manual_trim":
            x = self.m["trims"].get(ticker)
            if not x:
                return
            it = self.m["items"].get(x["id"]) or {}
            if qty <= 0:
                it["msg"] = f"{bar} 开盘没成交（ストップ安等）→ 下一开盘再卖"
                return
            left = int(x["shares"]) - int(qty)
            if left > 0 and ticker in st.pos:
                x["shares"] = left                          # 部分成交：剩下的下一次再卖
                it["msg"] = f"{bar} 开盘卖出 {qty:,} 股 @ ¥{px:,.2f}，还差 {left:,} 股（下一开盘再卖）"
                return
            self.m["trims"].pop(ticker, None)
            it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} 开盘卖出 {qty:,} 股 @ ¥{px:,.2f}（减仓完成）")
            return
        for it in self._active_for(ticker):
            if ticker in self.m["trims"] and self.m["trims"][ticker].get("id") == it["id"]:
                continue
            if ticker not in st.pos:
                it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} 开盘卖出 {qty:,} 股 @ ¥{px:,.2f}（全部卖出完成）"
                          + ("；撤回来不及：交易所的单已经成交" if it.get("cancel_req") else ""))
            elif qty > 0:
                it["msg"] = f"{bar} 开盘只成交 {qty:,} 股 @ ¥{px:,.2f}，剩下的下一开盘再卖"
            else:
                it["msg"] = f"{bar} 开盘没成交（ストップ安等）→ 下一开盘再卖"

    def settle(self, st, sent: set | None = None) -> list[tuple[str, str]]:
        """对账之后（或没有新交易日时下单之前）：撤回中的指令 → 交易所那边没有在途的单就撤（之后不再重下）；
        持仓已经没了的 → 完成；过期的「不买回」去掉；只留最近 200 条记录。sent = 这次决策里已经发到交易所的手动卖单的票。"""
        out, sent = [], set(sent or ())
        for it in self.m["items"].values():
            if it.get("status") != "placed" or it.get("kind") not in ("sell", "trim"):
                continue
            t = it.get("ticker")
            mine_trim = (self.m["trims"].get(t) or {}).get("id") == it["id"]
            if t not in st.pos:
                if mine_trim:
                    self.m["trims"].pop(t, None)
                it.setdefault("done_on", st.last_date)
                it["status"] = "done"
                if it.get("cancel_req"):
                    it["msg"] = "撤回来不及：已经卖出了"
                continue
            if not it.get("cancel_req") or t in sent:
                continue
            if it["kind"] == "sell" or not mine_trim:
                if st.pending_exit.get(t) == "manual":
                    st.pending_exit.pop(t)
                b = self.m["blocks"].get(t)
                if b and b.get("id") == it["id"]:
                    self.m["blocks"].pop(t)
            if mine_trim:
                self.m["trims"].pop(t, None)
            it.update(status="cancelled", msg=f"已撤回（{it['cancel_req']}）：之后不再下这笔卖单")
            out.append(("info", f"手动指令 {it['id']}：{t} {it['msg']}"))
        today = self.clock().date().isoformat()
        for t, b in list(self.m["blocks"].items()):
            if b.get("until") is not None and str(b["until"]) < today:
                self.m["blocks"].pop(t)
        items = self.m["items"]
        if len(items) > 200:
            for k in sorted(items, key=lambda x: items[x].get("at", ""))[:len(items) - 200]:
                if items[k].get("status") not in ACTIVE:
                    items.pop(k)
        return out

    # ── 汇报 ──
    def summary(self) -> dict:
        items = sorted(self.m["items"].values(), key=lambda x: x.get("at", ""), reverse=True)
        keep = ("id", "at", "kind", "ticker", "pct", "block_days", "target", "status", "msg", "decided_on", "fill_day",
                "done_on", "fill", "shares", "source", "note", "cancel_req")
        return {"core_pct": self.core_pct, "blocks": dict(self.m["blocks"]), "trims": dict(self.m["trims"]),
                "items": [{k: v for k, v in it.items() if k in keep} for it in items[:30]],
                "active": sum(1 for it in items if it.get("status") in ACTIVE)}


def active(sm: dict | None) -> bool:
    """有手动操作在影响账户（闲置资金比例不是 100%、有「不买回」、有没完成的指令）→ 与云端模拟盘不同是预期的。"""
    sm = sm or {}
    return (float(sm.get("core_pct", 100.0)) != 100.0 or bool(sm.get("blocks")) or bool(sm.get("trims"))
            or bool(sm.get("active")) or any(it.get("status") == "done" and it.get("kind") in ("sell", "trim")
                                             for it in sm.get("items") or []))


def lines(sm: dict | None, today: str | None = None) -> list[str]:
    """日志 / 通知用：手动指令的几行（没有就空）。today = 这一天完成的也列出来。"""
    sm = sm or {}
    out = []
    if float(sm.get("core_pct", 100.0)) != 100.0:
        out.append(f"- 闲置资金比例：手动设为规则目标额的 {float(sm['core_pct']):g}%（页面上改回 100% 就照规则）")
    for t, b in (sm.get("blocks") or {}).items():
        out.append(f"- {t}：手动卖出后不自动买回（{'一直，直到解除' if b.get('until') is None else '到 ' + str(b['until'])}）")
    for it in sm.get("items") or []:
        if it.get("status") in ACTIVE or (today and str(it.get("done_on") or "") >= today) \
                or (today and str(it.get("at") or "")[:10] >= today):
            out.append(f"- 手动指令 {it.get('id')}：{LABEL.get(it.get('kind'), it.get('kind'))}"
                       f"{(' ' + it['ticker']) if it.get('ticker') else ''}"
                       f"{(' ' + format(float(it['pct']), 'g') + '%') if it.get('pct') is not None else ''}"
                       f" → {STATUS.get(it.get('status'), it.get('status'))}：{it.get('msg') or ''}")
    return out


__all__ = ["KINDS", "BLOCK_DEFAULT", "Manual", "append", "read_all", "unseen", "normalize", "check", "next_window", "due",
           "requests_path", "position_pct", "active", "lines", "LABEL", "STATUS", "REASON_TEXT"]
