"""delist_schedule.py — 实时的退市时间表 + 到日自动更新股票池（用户 2026-09-30：「做一个实时股票退市时间表 check，到日期后就把对应股票池更新」）。

来由：qbreak/eligibility.py 每天取 JPX 上場廃止銘柄一覧（含预定日）与 監理・整理銘柄，只拿来「不开新仓」（G4 / G5）；
静态名单 qbreak/universes.NIKKEI225 到了上場廃止日不会自己变，只有定期入替（var/index_changes.json）按生效日自动增删。
这里把有日期的事放进一张表 —— var/delist_schedule.json（Mac 上是 ~/.qbreak/home/delist_schedule.json：scripts/liveu.sh 先拷云端的，
执行器再用自己取的 JPX 数据更新）—— 每次决策前（云端 sim-day、Mac 执行器，都在算股票池之前）更新：
  ① JPX 上場廃止（含预定）：上場廃止日、最終売買日（= 上場廃止日的前一个交易日）、理由类别（TOB / 合併 / 基準不適合 …）
  ② 日経225 定期入替（var/index_changes.json）：公布日、生效日、加 / 减（原有机制按生效日自动增删，这里只显示）
  ③ JPX 整理銘柄（已指定、上場廃止日还没登在一览上）：日期未定
到日期自动做的事 —— 只做「减」：
  • 上場廃止日 ≤ 今天 → 该票从交易股票池去掉：记进 applied，universes.nikkei225() 读这张表（config.universe → 模拟盘 / 执行器 /
    候补队列 / 时间线全部一致）。上場廃止日早上的决策（按前一天收盘、当天开盘成交）就已经不含它：那天开盘已经买不到
  • applied 的记录一直留着（JPX 一览大约一年后会滚掉、资格检查只看 30 天）；400 天后清掉（那时静态名单早该更新，JPX 也不会这么快
    把代码给别的公司）
不自动做的事（CLAUDE.md）：补入的票（臨時入替的替补、ja.wikipedia 名单里多出的）要用户确认后改名单 → 只提醒；
持仓不自动卖 → 只报警，写明最終売買日与剩余交易日；到了上場廃止日还拿着 → 规则卖不掉，要人工处理（先 HALT）。
"""
from __future__ import annotations

import datetime as dt
import json

from . import paths
from .utils import atomic_write_text, read_json, setup_logging

log = setup_logging("delist_schedule")

FILE = "delist_schedule.json"
LOOKBACK_DAYS = 30            # 表里保留：日期在今天往前 30 天以后的（与资格检查 G5 同一口径）
KEEP_DAYS = 400               # applied（已从股票池去掉）的记录保留天数
K_DELIST, K_DEL, K_ADD, K_SEIRI = "上場廃止", "指数剔除", "指数纳入", "整理銘柄"
SRC = {K_DELIST: "JPX 上場廃止銘柄一覧", K_DEL: "var/index_changes.json", K_ADD: "var/index_changes.json", K_SEIRI: "JPX 監理・整理銘柄"}
ST_WAIT, ST_TODAY, ST_DONE, ST_TBD = "待生效", "今天生效", "已生效", "日期未定"


def path():
    return paths.home() / FILE


def load(fp=None) -> dict:
    d = read_json(fp or path(), {}) or {}
    d.setdefault("items", [])
    d.setdefault("applied", [])
    return d


def applied_codes(today: dt.date, fp=None) -> set[str]:
    """已到上場廃止日（≤ today）、从股票池去掉的代码 —— universes.nikkei225(today=…) 用（按日期比，时点一致）。"""
    d = today.isoformat()
    return {str(a["code"]) for a in load(fp)["applied"] if str(a.get("date") or "") <= d}


def _code(t) -> str:
    return str(t).split(".")[0]


def trading_days_left(today: dt.date, last_trade: dt.date) -> int:
    """从今天（含，若是交易日）到最終売買日（含）还有几个东证交易日；已过 → 0。"""
    from .calendar_jp import is_trading_day
    n, x = 0, today
    while x <= last_trade:
        n += int(is_trading_day(x))
        x += dt.timedelta(days=1)
    return n


def _status(date: str | None, today: str) -> str:
    if not date:
        return ST_TBD
    return ST_WAIT if date > today else ST_TODAY if date == today else ST_DONE


def build(today: dt.date, snap: dict, pool=(), held=None, core=(), changes=None, prev: dict | None = None) -> dict:
    """今天的时间表。snap = 资格检查快照（eligibility.load / refresh 的结果）；pool = 今天的交易股票池（代码，可带 .T；
    传进来的应是上一次 applied 已去掉之后的池子）；held = {代码: [账户, …]}；core = 核心 ETF；changes = index_changes("JP")；
    prev = 上一次的表（applied 从它延续）。只有代码、类别、日期（不存公司名、理由原文）。"""
    from .calendar_jp import prev_trading_day
    held = {_code(k): list(v) for k, v in (held or {}).items()}
    pool_c, core_c = {_code(t) for t in pool}, {_code(t) for t in core}
    src = snap.get("sources") or {}
    d0 = today.isoformat()
    lo = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()

    def row(kind, code, date, **x):
        code = _code(code)
        return {"kind": kind, "code": code, "date": date, "status": _status(date, d0), "in_pool": code in pool_c,
                "held": held.get(code, []), "core": code in core_c, "src": SRC[kind], **x}
    items, dated = [], set()
    for it in (src.get("jpx_delisted") or {}).get("items") or []:
        if it.get("cat") != K_DELIST or not it.get("date") or it["date"] < lo:
            continue
        lt = prev_trading_day(dt.date.fromisoformat(it["date"]))
        items.append(row(K_DELIST, it["code"], it["date"], why=it.get("why") or "その他", last_trade=lt.isoformat(),
                         days_left=trading_days_left(today, lt)))
        dated.add(_code(it["code"]))
    for k in ("jpx_supervision", "jpx_supervision_etf"):
        for it in (src.get(k) or {}).get("items") or []:
            if it.get("cat") == K_SEIRI and _code(it["code"]) not in dated:
                items.append(row(K_SEIRI, it["code"], None, designated=it.get("date")))
    for ch in changes or []:
        eff = str(ch.get("effective") or "")
        if not eff or eff < lo:
            continue
        for key, kind in (("delete", K_DEL), ("add", K_ADD)):
            for c in ch.get(key, []):
                items.append(row(kind, c, eff, announced=ch.get("announced")))
    # applied：上一次的 + 今天到期的（只记我们股票池里的票）；400 天后清掉
    keep_from = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    applied = {a["code"]: dict(a) for a in (prev or {}).get("applied") or [] if str(a.get("applied_on") or a.get("date") or "") >= keep_from}
    for r in items:
        if r["kind"] == K_DELIST and r["date"] <= d0 and r["in_pool"] and r["code"] not in applied:
            applied[r["code"]] = {"code": r["code"], "date": r["date"], "last_trade": r["last_trade"], "why": r["why"], "applied_on": d0}
    for r in items:
        r["removed"] = r["kind"] == K_DELIST and r["code"] in applied
    order = {K_DELIST: 0, K_DEL: 1, K_ADD: 2, K_SEIRI: 3}
    items.sort(key=lambda r: (r["date"] or "9999-99-99", order[r["kind"]], r["code"]))
    ours = [r for r in items if r["in_pool"] or r["held"] or r["core"] or r["removed"] or r["kind"] in (K_DEL, K_ADD)]
    needs = []
    for r in ours:
        who = "、".join(r["held"])
        if r["kind"] == K_DELIST and r["held"]:
            if r["date"] > d0:
                needs.append(f"持仓 {r['code']}（{who}）：{r['date']} 上場廃止（{r['why']}），最終売買日 {r['last_trade']}"
                             f"（剩 {r['days_left']} 个交易日）—— 规则不自动卖；要提前卖先 HALT 再人工处理")
            else:
                needs.append(f"持仓 {r['code']}（{who}）：已在 {r['date']} 上場廃止 —— 规则卖不掉，需要你人工处理（先 HALT）")
        elif r["kind"] == K_SEIRI and (r["held"] or r["in_pool"] or r["core"]):
            needs.append(f"{'持仓 ' + r['code'] + '（' + who + '）' if r['held'] else ('核心 ETF ' if r['core'] else '股票池里的 ') + r['code']}："
                         f"JPX 整理銘柄（{r.get('designated') or '—'} 指定），上場廃止日还没公布 —— 等一览登出日期后自动进时间表"
                         + ("；规则不自动卖" if r["held"] else ""))
        elif r["kind"] == K_DELIST and r["core"]:
            needs.append(f"核心 ETF {r['code']}：{r['date']} 上場廃止（{r['why']}）—— 执行器不下它的买单；持有的要你决定")
    recent = [a for a in applied.values() if str(a.get("applied_on") or "") >= lo]
    for a in sorted(recent, key=lambda a: a["date"]):
        needs.append(f"{a['code']} 已于 {a['date']} 上場廃止、从股票池去掉（{a['why']}）—— 日経225 的补入銘柄要你确认后加进名单"
                     "（看「下单前资格检查」名单对照的「它有我们没有」）")
    n_pool = [r for r in items if r["kind"] == K_DELIST and r["in_pool"] and r["date"] >= d0]
    n_other = sum(1 for r in items if r["kind"] == K_DELIST and not (r["in_pool"] or r["held"] or r["core"] or r["removed"]))
    idx = [r for r in items if r["kind"] in (K_DEL, K_ADD) and r["date"] >= d0]
    parts = [f"股票池里 {len(n_pool)} 只有上場廃止预定" + ("（" + "、".join(f"{r['code']} {r['date']}" for r in n_pool) + "；到日自动去掉）"
                                                     if n_pool else "")]
    if idx:
        parts.append("定期入替 " + "、".join(sorted({r["date"] for r in idx})) + " 生效（+"
                     + "/".join(r["code"] for r in idx if r["kind"] == K_ADD) + " −" + "/".join(r["code"] for r in idx if r["kind"] == K_DEL) + "）")
    if recent:
        parts.append("最近 30 天已去掉 " + "、".join(a["code"] for a in recent))
    parts.append(f"JPX 一览另有 {n_other} 只不在股票池")
    stale = not (src.get("jpx_delisted") or {}).get("ok_at")
    return {"as_of": d0, "items": items, "ours": ours, "applied": sorted(applied.values(), key=lambda a: a["date"]),
            "needs_user": needs, "n_other": n_other, "stale": stale,
            "source_ok_at": {k: (src.get(k) or {}).get("ok_at") for k in ("jpx_delisted", "jpx_supervision", "jpx_supervision_etf")},
            "text": "股票池更新时间表：" + ("★ JPX 上場廃止一览从没取到；" if stale else "") + "；".join(parts)}


def update(today: dt.date, held=None, core=(), fetch=None, fp=None, snap=None) -> dict:
    """取快照（2 小时内取过就不取；snap 给定 = 不取、只用这份）→ 今天的表 → 写文件。
    任何意外 → 不改文件、上一次的表照常生效（applied 不变），记下错误。"""
    fp = fp or path()
    prev = load(fp)
    try:
        from . import eligibility as EL
        from .calendar_jp import now_jst
        from .universes import index_changes, nikkei225
        snap = snap if snap is not None else EL.refresh_today(fetch=fetch)
        d = build(today, snap, nikkei225(exclude=False, today=today), held, core, index_changes("JP"), prev)
        d["updated"] = now_jst().isoformat(timespec="minutes")
        atomic_write_text(fp, json.dumps(d, ensure_ascii=False, indent=1))
        return d
    except Exception as e:                                        # noqa: BLE001
        log.error("退市时间表没更新（上一次的表照常生效）：%s", e)
        prev["error"] = f"{type(e).__name__}: {e}"[:200]
        return prev


def lines(d: dict) -> list[str]:
    """命令行 / 日志用的几行（每个日期带状态）。"""
    out = [d.get("text") or "股票池更新时间表：—"]
    for r in d.get("ours") or []:
        rel = "；".join(x for x in (("股票池" if r.get("in_pool") else ""), ("持仓 " + "、".join(r["held"]) if r.get("held") else ""),
                                   ("核心 ETF" if r.get("core") else ""), ("已从股票池去掉" if r.get("removed") else "")) if x)
        if r["kind"] == K_DELIST:
            out.append(f"  {r['date']} 上場廃止 {r['code']}（{r['why']}）：最終売買日 {r['last_trade']}，剩 {r['days_left']} 个交易日；"
                       f"{r['status']}；{rel or '—'}")
        elif r["kind"] == K_SEIRI:
            out.append(f"  日期未定 整理銘柄 {r['code']}（{r.get('designated') or '—'} 指定）；{rel or '—'}")
        else:
            out.append(f"  {r['date']} {r['kind']} {r['code']}（{r.get('announced') or '—'} 公布）：{r['status']}；{rel or '—'}")
    for a in d.get("applied") or []:
        out.append(f"  已去掉 {a['code']}：{a['date']} 上場廃止（{a['why']}），{a.get('applied_on')} 起不在股票池")
    for n in d.get("needs_user") or []:
        out.append(f"  ★ {n}")
    if d.get("error"):
        out.append(f"  ★ 这次没更新：{d['error']}（上一次的表照常生效）")
    return out
