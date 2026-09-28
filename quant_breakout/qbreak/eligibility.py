"""eligibility.py — 下单前资格检查（用户 2026-09-28：「以后要确认要下单的股票被没被踢出」，横展开到所有下单路径）。

来由：qbreak/universes.py 的日経225 静态名单里 ニデック（6594）在 2025-10-27 因特別注意銘柄指定被臨時剔除（イビデン 4062 补入，
日本経済新聞 2025-10-27「日経平均、特別注意銘柄指定のニデックを除外 イビデンを補充」），名单没跟上 ——
静态名单 + var/index_changes.json 只覆盖定期入替。en.wikipedia 的名单到 2026-09-28 还列着ニデック：只看一个来源也会漏。

每天查三类公开来源（只存代码、类别、日期；不存公司名、理由原文与链接）→ var/out/eligibility.json：
  ① 指数成分对照：ja.wikipedia「日経平均株価」构成銘柄一覧（主，约 225 只）、en.wikipedia「Nikkei 225」（参考，只报不挡）
  ② JPX 監理・整理銘柄（株式 / その他商品 = ETF）、特別注意銘柄（臨時剔除的直接原因）
  ③ JPX 上場廃止銘柄一覧（TOB / MBO / 合併 / 基準不適合，含预定日）
规则 —— 新开个股仓（模拟盘与执行器同一段决策代码 qbreak/unified.py；执行器发买单前再查一次）：
  G1 不在今天的交易股票池 → 不开新仓（只因持仓 / 执行器账户才取了行情的票）
  G2 指数待剔除（已公布、未生效，var/index_changes.json）→ 不开新仓（原有规则，这里一起显示）
  G3 我们的名单里有、ja.wikipedia 名单里没有，且 index_changes.json 的纳入记录解释不了 → 不开新仓（可能已被臨時剔除）
  G4 JPX 特別注意 / 監理（確認中・審査中）/ 整理銘柄 → 不开新仓
  G5 JPX 上場廃止（今天往前 30 天以后的日期，含预定）→ 不开新仓
  G6 必需来源（ja.wikipedia + JPX 四页）有一个超过 4 天没取到（或从没取到）→ 今天不开新个股仓（确认不了就不买）
  核心 ETF（1655）：G4 / G5（その他商品页）→ 执行器不下核心买单（卖单照常）；来源过期不挡核心
  持仓：被 G3〜G5 标记 → 只报警（规则不自动卖，与回测相同；要不要提前卖由用户决定，人工买卖前先 HALT）
  反方向：ja.wikipedia 有、我们没有（且不是已记录的剔除）→ 只报警：改名单要用户确认，记进 var/sim_changes.md
已知局限：TOB 公布 → 整理銘柄指定之间的几周查不到（要 TDnet）；Wikipedia 是社区编辑、可能滞后（所以 JPX 那一层独立判断）。
"""
from __future__ import annotations

import datetime as dt
import html as _html
import json
import re
from dataclasses import dataclass, field

from . import paths
from .utils import atomic_write_text, read_json, setup_logging

log = setup_logging("eligibility")

FILE = "eligibility.json"
SOURCES = {
    "ja_wiki": "https://ja.wikipedia.org/wiki/%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%E6%A0%AA%E4%BE%A1",
    "en_wiki": "https://en.wikipedia.org/wiki/Nikkei_225",
    "jpx_supervision": "https://www.jpx.co.jp/listing/market-alerts/supervision/index.html",
    "jpx_supervision_etf": "https://www.jpx.co.jp/listing/market-alerts/supervision/02.html",
    "jpx_alert": "https://www.jpx.co.jp/listing/measures/alert/index.html",
    "jpx_delisted": "https://www.jpx.co.jp/listing/stocks/delisted/index.html",
}
LABEL = {"ja_wiki": "ja.wikipedia 日経225 名单", "en_wiki": "en.wikipedia 日経225 名单（参考）",
         "jpx_supervision": "JPX 監理・整理銘柄（株式）", "jpx_supervision_etf": "JPX 監理・整理銘柄（ETF 等）",
         "jpx_alert": "JPX 特別注意銘柄", "jpx_delisted": "JPX 上場廃止銘柄一覧"}
REQUIRED = ("ja_wiki", "jpx_supervision", "jpx_supervision_etf", "jpx_alert", "jpx_delisted")
MAX_AGE_DAYS = 4                 # 周末 + 1 天假日也不算过期
TTL_HOURS = 2.0                  # 2 小时内取过就不再取（07:40 的早上 + 09:05 的开盘后共用一次）
DELIST_LOOKBACK_DAYS = 30
N225_RANGE = (215, 235)          # 解析出来的成分数不在这个范围 → 当作解析失败（不用这次的结果）
_CODE = r"[0-9]{3}[0-9A-Z]"
_DATE = re.compile(r"(\d{4})[/年.-](\d{1,2})[/月.-](\d{1,2})")


# ── 解析（纯函数，测试用固定的 HTML 片段）──
def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _date(s: str) -> str | None:
    m = _DATE.search(s or "")
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def parse_ja_wiki(page: str) -> dict:
    """ja.wikipedia「日経平均株価」：表头有「証券コード」「銘柄」的表（按业种分）→ 代码；「YYYY年M月D日現在」一起记下。"""
    codes: list[str] = []
    for tb in re.findall(r"<table.*?</table>", page, re.S):
        hdr = [_txt(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", tb, re.S)]
        if "証券コード" in hdr and "銘柄" in hdr:
            codes += re.findall(r"<tr[^>]*>\s*<td[^>]*>\s*(" + _CODE + r")\s*</td>", tb)
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日現在", _txt(page))
    return {"codes": sorted(set(codes)), "note": m.group(0) if m else ""}


def parse_en_wiki(page: str) -> dict:
    return {"codes": sorted(set(re.findall(r'topSearchStr=(' + _CODE + r')"', page))
                            | set(re.findall(r"TYO:\s*(" + _CODE + r")\b", page)))}


def _tables(page: str) -> list[tuple[str, str]]:
    """[(表前面最近的小标题, 表 HTML)]。"""
    out, head = [], ""
    for m in re.finditer(r"<h[2-4][^>]*>(.*?)</h[2-4]>|<table.*?</table>", page, re.S):
        if m.group(0).startswith("<table"):
            out.append((head, m.group(0)))
        else:
            head = _txt(m.group(1))
    return out


def _rows(tb: str) -> list[list[str]]:
    return [[_txt(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)] for r in re.findall(r"<tr.*?</tr>", tb, re.S)]


def _items(page: str, cat_of) -> list[dict]:
    """有「コード」列的表 → [{code, cat, date}]；代码 / 日期按内容认（列顺序、rowspan 的续行都不影响）。"""
    out = []
    for head, tb in _tables(page):
        rows = _rows(tb)
        if not any("コード" in r for r in rows):
            continue
        cat = cat_of(head)
        for r in rows:
            code = next((c for c in r if re.fullmatch(_CODE, c)), None)
            d = next((x for x in (_date(c) for c in r) if x), None)
            if code and cat:
                out.append({"code": code, "cat": cat, "date": d})
    return out


def parse_jpx_supervision(page: str) -> dict:
    """監理・整理銘柄一覧（株式 / その他商品）：小标题 監理銘柄（確認中）/ 監理銘柄（審査中）/ 整理銘柄。"""
    if "現在の指定状況" not in page:
        raise ValueError("页面里没有「現在の指定状況」（JPX 改版？）")

    def cat(h: str) -> str | None:
        for k in ("監理銘柄（確認中）", "監理銘柄（審査中）", "整理銘柄"):
            if k in h.replace("(", "（").replace(")", "）"):
                return k
        return None
    return {"items": _items(page, cat)}


def parse_jpx_alert(page: str) -> dict:
    if "特別注意銘柄" not in page:
        raise ValueError("页面里没有「特別注意銘柄」（JPX 改版？）")
    return {"items": _items(page, lambda h: "特別注意銘柄")}


_WHY = (("TOB・MBO・株式併合", ("公開買付", "株式併合", "ＭＢＯ", "MBO", "株式等売渡請求")),
        ("合併・株式交換・株式移転", ("合併", "株式交換", "株式移転", "株式交付")),
        ("上場維持基準不適合", ("上場維持基準",)), ("破綻", ("破産", "更生", "再生", "銀行取引の停止")),
        ("申請による上場廃止", ("申請",)))


def parse_jpx_delisted(page: str) -> dict:
    """上場廃止銘柄一覧：[{code, cat:"上場廃止", date:上場廃止日, why:归类后的短标签}]（理由原文不存）。"""
    items = []
    for _, tb in _tables(page):
        rows = _rows(tb)
        if not rows or "上場廃止日" not in rows[0]:
            continue
        for r in rows[1:]:
            code = next((c for c in r if re.fullmatch(_CODE, c)), None)
            d = next((x for x in (_date(c) for c in r) if x), None)
            if not code or not d:
                continue
            reason = r[-1] if r else ""
            why = next((lab for lab, kws in _WHY if any(k in reason for k in kws)), "その他")
            items.append({"code": code, "cat": "上場廃止", "date": d, "why": why})
    if not items:
        raise ValueError("没有找到「上場廃止日」的表（JPX 改版？）")
    return {"items": items}


PARSERS = {"ja_wiki": parse_ja_wiki, "en_wiki": parse_en_wiki, "jpx_supervision": parse_jpx_supervision,
           "jpx_supervision_etf": parse_jpx_supervision, "jpx_alert": parse_jpx_alert, "jpx_delisted": parse_jpx_delisted}


def _validate(key: str, x: dict) -> None:
    if key in ("ja_wiki", "en_wiki"):
        n = len(x.get("codes") or [])
        if not N225_RANGE[0] <= n <= N225_RANGE[1]:
            raise ValueError(f"解析出 {n} 只（应约 225 只）")


# ── 快照：取数 + 保存 ──
def _now():
    from .calendar_jp import now_jst
    return now_jst()


def _fetch_url(url: str) -> str:
    """一次 25 秒、不重试：6 个页面最坏约 2.5 分钟（Mac 07:40 的运行要赶 08:55 的寄付截止）；失败就用上次成功的内容（4 天内有效）。"""
    from .factors import _get
    return _get(url, timeout=25, tries=1).decode("utf-8", "ignore")


def snapshot_path():
    return paths.out_dir() / FILE


def load(path=None) -> dict:
    d = read_json(path or snapshot_path(), {}) or {}
    d.setdefault("sources", {})
    return d


def _ok_date(s: dict) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat(str(s.get("ok_at"))).date()
    except (TypeError, ValueError):
        return None


def refresh(path=None, now=None, fetch=None, ttl_hours: float = TTL_HOURS, force: bool = False, fallback=None) -> dict:
    """逐个来源重取（2 小时内取过的跳过）；某个来源失败 → 保留上次成功的内容与日期，记下错误。
    fallback：另一份快照（Mac 上 = 仓库里云端写的 var/out/eligibility.json），某来源比自己新就用它的。"""
    path = path or snapshot_path()
    now = now or _now()
    snap = load(path)
    for key, url in SOURCES.items():
        s = dict(snap["sources"].get(key) or {})
        ok_at = s.get("ok_at")
        if not force and ok_at:
            try:
                if (now - dt.datetime.fromisoformat(ok_at)).total_seconds() < ttl_hours * 3600:
                    continue
            except (TypeError, ValueError):
                pass
        s["tried_at"] = now.isoformat(timespec="minutes")
        try:
            x = PARSERS[key]((fetch or _fetch_url)(url))
            _validate(key, x)
            s = {**x, "ok_at": s["tried_at"], "tried_at": s["tried_at"], "error": ""}
        except Exception as e:                                    # noqa: BLE001
            s["error"] = f"{type(e).__name__}: {e}"[:200]
            log.warning("资格检查 %s 没取到：%s", key, s["error"])
        snap["sources"][key] = s
    if fallback:
        fb = read_json(fallback, {}) or {}
        for key, s in (fb.get("sources") or {}).items():
            mine, theirs = _ok_date(snap["sources"].get(key) or {}), _ok_date(s)
            if theirs and (mine is None or theirs > mine):
                snap["sources"][key] = {**s, "from": "仓库快照（云端）"}
    snap["updated"] = now.isoformat(timespec="minutes")
    atomic_write_text(path, json.dumps(snap, ensure_ascii=False, indent=1))
    return snap


# ── 判定 ──
def _code(t: str) -> str:
    return str(t).split(".")[0]


def _tse(t: str) -> bool:
    """东证的票（「7203.T」或不带后缀的代码「7203」/「285A」）。"""
    s = str(t)
    return s.endswith(".T") or re.fullmatch(_CODE, s) is not None


@dataclass
class Gate:
    """今天（today）的资格判定。trade = 今天的交易股票池（代码，不带 .T）；ours = 今天的日経225（含航空 / 铁路，对照用）；
    core = 核心 ETF 代码；changes / pending = var/index_changes.json 的入替记录与已公布未生效的部分。"""
    today: dt.date
    trade: set
    ours: set
    snap: dict
    core: set = field(default_factory=set)
    changes: list = field(default_factory=list)
    pending: dict = field(default_factory=dict)
    error: str = ""                                              # 资格检查本身出错（→ 不开新个股仓）

    def __post_init__(self):
        src = self.snap.get("sources") or {}
        self.fresh = {k: (d := _ok_date(src.get(k) or {})) is not None and (self.today - d).days <= MAX_AGE_DAYS
                      for k in SOURCES}
        self.stale = [k for k in REQUIRED if not self.fresh[k]]
        eff = [c for c in self.changes if str(c.get("effective", "")) <= self.today.isoformat()]
        added = {x for c in eff for x in c.get("add", [])}
        deleted = {x for c in eff for x in c.get("delete", [])}
        self.diff: dict[str, dict] = {}
        for k in ("ja_wiki", "en_wiki"):
            codes = set((src.get(k) or {}).get("codes") or [])
            if not codes:
                continue
            self.diff[k] = {"ours_only": sorted(self.ours - codes - added), "lag": sorted((self.ours - codes) & added),
                            "src_only": sorted(codes - self.ours - deleted)}
        self.g3 = set((self.diff.get("ja_wiki") or {}).get("ours_only") or [])
        lo = (self.today - dt.timedelta(days=DELIST_LOOKBACK_DAYS)).isoformat()
        self.flags: dict[str, list[str]] = {}
        for k in ("jpx_supervision", "jpx_supervision_etf", "jpx_alert", "jpx_delisted"):
            for it in (src.get(k) or {}).get("items") or []:
                if it.get("cat") == "上場廃止":
                    if not it.get("date") or it["date"] < lo:
                        continue
                    txt = (f"JPX 上場廃止{'预定' if it['date'] >= self.today.isoformat() else ''} {it['date']}"
                           f"（{it.get('why') or 'その他'}）")
                else:
                    txt = f"JPX {it['cat']}（{it.get('date') or '—'} 指定）"
                self.flags.setdefault(it["code"], [])
                if txt not in self.flags[it["code"]]:
                    self.flags[it["code"]].append(txt)

    # 个股：G2〜G5 的理由（不含来源过期 / 不在股票池）
    def reasons(self, code: str) -> list[str]:
        out = []
        p = self.pending.get(code)
        if p and p.get("action") == "delete":
            out.append(f"日経225 待剔除（{p.get('effective')} 生效，var/index_changes.json）")
        if code in self.g3:
            out.append("ja.wikipedia 的日経225 名单里没有（可能已被臨時剔除；核实后改名单）")
        return out + self.flags.get(code, [])

    def entry_block(self, ticker: str, i=None) -> str | None:
        """新开个股仓前的检查（引擎的 entry_gate_fn）：返回理由 = 不开；None = 可以。只管东证的票（美股个股不在这里查）。"""
        if not _tse(ticker):
            return None
        code = _code(ticker)
        if self.error:
            return f"资格检查出错（{self.error}）→ 不开新个股仓"
        if self.stale:
            return "资格检查数据过期或取不到（" + "、".join(LABEL[k] for k in self.stale) + "）→ 确认不了，不开新个股仓"
        if code not in self.trade:
            return "不在今天的交易股票池（只因持仓才取了行情）"
        r = self.reasons(code)
        return "；".join(r) if r else None

    def pre_send(self, ticker: str, side: str, kind: str) -> str | None:
        """执行器发单前的最后一道：只查买单；核心 ETF 只看 JPX 标记（来源过期不挡核心）。"""
        if side != "BUY" or not _tse(ticker):
            return None
        if kind == "core":
            r = self.flags.get(_code(ticker), [])
            return "；".join(r) if r else None
        return self.entry_block(ticker)

    def held_alerts(self, tickers, account: str = "") -> list[dict]:
        """持仓（个股 + 核心）的标记：warn = 需要用户决定（规则不自动卖）；info = 已按记录剔除、规则照常持有到出场信号。"""
        out = []
        if self.error:                                            # 判定本身出错：成员名单不可信，不给持仓乱标
            return out
        for t in sorted(set(tickers)):
            code = _code(t)
            why = self.flags.get(code, []) + (["ja.wikipedia 的日経225 名单里没有（可能已被臨時剔除）"] if code in self.g3 else [])
            if why:
                out.append({"ticker": t, "account": account, "level": "warn", "why": "；".join(why)})
            elif code not in self.core and code not in self.ours:
                out.append({"ticker": t, "account": account, "level": "info",
                            "why": "已不在日経225（入替记录已生效）：规则照常持有到出场信号"})
        return out

    def panel(self, held: list[dict] | None = None, blocked_today: list | None = None) -> dict:
        """日报 / 页面用的汇总（只有代码、类别、日期）。needs_user = 需要人工看的事（报警）。"""
        src = self.snap.get("sources") or {}
        blocked = [{"code": c, "why": "；".join(self.reasons(c))} for c in sorted(self.trade) if self.reasons(c)]
        core = [{"code": c, "why": "；".join(self.flags[c])} for c in sorted(self.core) if self.flags.get(c)]
        ja = self.diff.get("ja_wiki") or {}
        warn_held = [h for h in held or [] if h.get("level") == "warn"]
        needs = []
        if self.error:
            needs.append(f"资格检查出错：{self.error}")
        if self.stale:
            needs.append("资格检查数据过期或取不到：" + "、".join(
                f"{LABEL[k]}（最后 {(src.get(k) or {}).get('ok_at') or '从没取到'}）" for k in self.stale))
        if ja.get("ours_only"):
            needs.append("我们的日経225 名单里有、ja.wikipedia 没有：" + "、".join(ja["ours_only"]) + "（已挡新仓；核实后改名单，要用户确认）")
        if ja.get("src_only"):
            needs.append("ja.wikipedia 的日経225 有、我们没有：" + "、".join(ja["src_only"]) + "（可能漏了纳入；加进股票池要用户确认）")
        for h in warn_held:
            needs.append(f"持仓 {h['ticker']}（{h.get('account') or '—'}）：{h['why']} —— 规则不自动卖，要不要提前卖由你决定")
        for c in core:
            needs.append(f"核心 ETF {c['code']}：{c['why']} —— 执行器不下它的买单")
        return {"as_of": self.today.isoformat(), "stale": list(self.stale), "error": self.error,
                "sources": {k: {"label": LABEL[k], "ok_at": (src.get(k) or {}).get("ok_at"), "fresh": self.fresh[k],
                                "n": len((src.get(k) or {}).get("codes") or (src.get(k) or {}).get("items") or []),
                                "note": (src.get(k) or {}).get("note", ""), "error": (src.get(k) or {}).get("error", "")}
                            for k in SOURCES},
                "checked": len(self.trade), "blocked": blocked, "core": core, "held": list(held or []),
                "blocked_today": list(blocked_today or []), "diff": self.diff, "needs_user": needs,
                "text": ("资格检查：" + ("；".join(needs) if needs else
                                     f"股票池 {len(self.trade)} 只已核对，" + (f"{len(blocked)} 只不开新仓" if blocked else "没有被踢出 / 被指定的"))
                         )}


def gate_for(today: dt.date, trade_tickers, core_tickers=(), refresh_first: bool = True, fetch=None) -> Gate:
    """取数（2 小时内取过就不取）→ 今天的判定。任何意外 → 返回「出错」的判定（不开新个股仓），不让模拟盘 / 执行器崩溃。"""
    from .universes import index_changes, index_pending, nikkei225
    trade = {_code(t) for t in trade_tickers if _tse(t)}
    core = {_code(t) for t in core_tickers}
    try:
        repo = paths.PROJECT_ROOT / "var" / "out" / FILE
        fb = repo if repo.resolve() != snapshot_path().resolve() and repo.exists() else None
        snap = refresh(fetch=fetch, fallback=fb) if refresh_first else load()
        ours = {_code(t) for t in nikkei225(exclude=False, today=today)}
        return Gate(today, trade, ours, snap, core, index_changes("JP"), index_pending("JP", today))
    except Exception as e:                                        # noqa: BLE001
        log.error("资格检查出错：%s", e)
        return Gate(today, trade, set(), {}, core, error=f"{type(e).__name__}: {e}"[:160])
