"""names.py — 股票 / ETF / 指数的「代码 名字」（2026-10-15 用户：只写代码不知道是哪只，名字也要有，整体見直し）。

给人看的文字里出现代码的地方都从这里取名字（唯一入口；ETF 名字表也只有这一份：idle_cash.NAMES / money_view.CORE_NAMES 从它派生）。
写法：代码在前、空一格、名字，不带 .T ——「7203 トヨタ自動車」「1545 纳斯达克 100」「1482 对冲版美国 7〜10 年国债」；
  查不到名字只写代码（「5202」）；渲染时不联网。个股的完整名保持 JPX 原文（全角也照旧，和「建议的股票」、持仓页一致）。
  窄的地方（Mac 通知 200 字、推送正文 600 字、tile）用 short=True：NFKC 半角化、ホールディングス → HD、
  フィナンシャル・グループ / フィナンシャルグループ → FG、去掉「株式会社」、超过约 10 个字截短加「…」—— 可以缩短，不能丢名字；
  列表长（4〜6 只以上）用 labels(..., limit=N) 写「等 N 只」。
  数量紧跟在名字后面用 qty(t, "100 股") →「7203 トヨタ自動車：100 股」（名字可能以数字结尾：「1545 纳斯达克 100：4,110 口」，2026-10-15 复核）。
名字从哪来（依次；JPX 公开数据 + 自己写的中文短名；不用 J-Quants 的 CoName —— 条款：不能进入库文件）：
  ① ETF_NAMES（精选的中文短名）② INDEX_NAMES（^N225 等）③ 数据目录 jpx_names.json ④ 仓库 var/jpx_names.json
  （Mac 的数据目录 ~/.qbreak/home 以前没有它 → jpx_list.names() 在 Mac 上是空的，只剩代码；现在退回仓库的快照）
  ⑤ 数据目录 cache/jpx_names_all.json（eligibility 取 JPX 東証上場銘柄一覧时顺手写：全部上市品种，只在本机、不入库）
  ⑥ 数据目录 out/eligibility.json 里 JPX 監理・整理 / 特別注意 / 上場廃止页的銘柄名（已退市、一覧里没有了的票）→ 再没有就只写代码。
  读文件按 mtime 缓存（文件变了自动重读）。
annotate(text)：兜底，把文字里「NNNN.T」（含 133A.T 这类新代码）换成「NNNN 名字」；只换查得到名字的。不动：cid（U2026-10-14-SELL-1545.T、
  后面的 -M）、指令 id（M20261015-…-corefix-1482）、要复制粘贴的命令行（含 bash / liveu.sh / run.py / python / manual sell … / adopt 的行）、
  链接、引号 / = 后面的值（JSON 的 ticker 字段、data-t 属性）、金额与日期；边界只用 ASCII 字符类（\\w 包括中日文，「卖7203.T」会漏）；
  输出不带 .T，所以重复跑结果不变；代码后面（或前面）已经有名字的只去掉 .T、不重复加。
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from html import escape
from pathlib import Path

from . import paths

# 精选的 ETF 中文短名（只放名字，不带「（代码）」；以面板每天显示的闲置资金写法为准，2026-10-15 合并 idle_cash.NAMES 与 money_view.CORE_NAMES）
_SECTOR17 = {"1617.T": "食品", "1618.T": "能源资源", "1619.T": "建设·资材", "1620.T": "素材·化学", "1621.T": "医药品",
             "1622.T": "汽车·运输机", "1623.T": "钢铁·有色", "1624.T": "机械", "1625.T": "电机·精密", "1626.T": "信息通信·服务",
             "1627.T": "电力·燃气", "1628.T": "运输·物流", "1629.T": "商社·批发", "1630.T": "零售", "1631.T": "银行",
             "1632.T": "金融（除银行）", "1633.T": "不动产"}           # = sectors.SECTOR_ETF_JP（NEXT FUNDS TOPIX-17；tests/test_names 对照）
ETF_NAMES: dict[str, str] = {
    "1545.T": "纳斯达克 100", "2845.T": "纳斯达克 100 对冲版", "1482.T": "对冲版美国 7〜10 年国债", "1655.T": "S&P500",
    "1329.T": "日経225", "1306.T": "TOPIX", "1321.T": "日经 225", "1570.T": "日经 2 倍", "1571.T": "日经反向",
    "1540.T": "黄金", "133A.T": "美元短期国债", "1671.T": "WTI 原油", "2238.T": "S&P500 反向", "2243.T": "美国半导体",
    "2869.T": "纳指 2 倍", "2842.T": "纳指反向", "1678.T": "印度 Nifty 50",
    "2558.T": "S&P500（MAXIS）", "2631.T": "纳斯达克 100（MAXIS）", "2561.T": "日本国债", "2563.T": "S&P500 对冲版",
    **{t: f"TOPIX-17 {v}" for t, v in _SECTOR17.items()},
}
ETF_SHORT: dict[str, str] = {                                     # short=True 用（不写的按通用规则截短）
    "1482.T": "对冲美债", "2845.T": "纳指 100 对冲", "1678.T": "印度 Nifty", "2558.T": "S&P500", "2631.T": "纳斯达克 100",
    "2563.T": "S&P500 对冲", **{t: f"T17 {v}" for t, v in _SECTOR17.items()},
}
INDEX_NAMES: dict[str, str] = {
    "^N225": "日経平均", "^GSPC": "S&P500 指数", "^TPX": "TOPIX", "^TOPX": "TOPIX", "^NDX": "纳斯达克 100 指数",
    "^IXIC": "纳斯达克综合指数", "^DJI": "道琼斯工业指数", "^SOX": "费城半导体指数", "^RUT": "罗素 2000", "^VIX": "VIX 恐慌指数",
    "^VIX3M": "VIX 3 个月", "^SKEW": "SKEW 指数", "^MOVE": "MOVE 美债波动指数", "^TNX": "美国 10 年国债收益率",
    "^SP500TR": "S&P500 全收益指数", "JPY=X": "美元 / 日元", "USDJPY=X": "美元 / 日元",
}
SNAPSHOT_FILE, ALL_FILE = "jpx_names.json", "jpx_names_all.json"
SHORT_LEN = 10                                                  # short=True：超过这么多个字 → 截短加「…」
_JP = re.compile(r"[0-9][0-9A-Z]{3}")                            # 东证代码（含 285A 这类新代码）


def code(t) -> str:
    """「7203.T」→「7203」；「^N225」「VOO」照原样。"""
    s = str(t or "").strip()
    return s[:-2] if s.endswith(".T") else s


# ── 名字表（按 mtime 缓存）──
@lru_cache(maxsize=64)
def _load(fp: str, mtime: int, size: int, kind: str) -> dict:
    """一个名字来源 → {代码: 名字}。读不了、不是 JSON、结构不对（顶层不是 dict、names / sources / items 不是该有的类型）→ 当成没有（{}）：
    名字只是显示用，坏文件绝不能让执行器 / 通知 / 日报 / 退市时间表跟着出错（2026-10-15 复核：以前 [1] 这种合法 JSON 会抛 AttributeError）。"""
    try:
        d = json.loads(Path(fp).read_text(encoding="utf-8"))
    except Exception:                                             # noqa: BLE001  OSError / ValueError / 编码错误…
        return {}
    if not isinstance(d, dict):
        return {}
    out: dict[str, str] = {}
    if kind == "elig":                                            # eligibility.json：各 JPX 页的 items 里的 name（parse 时存的）
        src = d.get("sources")
        for s in (src.values() if isinstance(src, dict) else ()):
            its = s.get("items") if isinstance(s, dict) else None
            for it in (its if isinstance(its, list) else ()):
                if isinstance(it, dict) and isinstance(it.get("name"), str) and it["name"].strip() and it.get("code"):
                    out[str(it["code"])] = it["name"]
        return out
    nm = d.get("names")
    for k, v in (nm.items() if isinstance(nm, dict) else ()):
        if isinstance(v, str) and v.strip():
            out[str(k)] = v
    return out


def _read(fp: Path, kind: str = "names") -> dict:
    try:
        st = fp.stat()
    except OSError:
        return {}
    return _load(str(fp), st.st_mtime_ns, st.st_size, kind)


def _sources() -> list[tuple[Path, str]]:
    """高优先在前：数据目录 jpx_names.json → 仓库 var/jpx_names.json → 数据目录 cache/jpx_names_all.json → 数据目录 out/eligibility.json。"""
    h = paths.home()
    return [(h / SNAPSHOT_FILE, "names"), (paths.PROJECT_ROOT / "var" / SNAPSHOT_FILE, "names"), (h / "cache" / ALL_FILE, "names"),
            (h / "out" / "eligibility.json", "elig")]                    # cache/ALL_FILE = all_file()（少调一次 home()）


def _sig(fp: Path) -> tuple:
    try:
        st = fp.stat()
        return (str(fp), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(fp), None, None)


@lru_cache(maxsize=8)
def _merged(sig: tuple) -> dict:
    out: dict[str, str] = {}
    for (fp, mtime, size), kind in reversed(sig):                 # 低优先先放，高优先覆盖
        if mtime is not None:
            out.update(_load(fp, mtime, size, kind))
    return out


def _table() -> dict:
    return _merged(tuple((_sig(fp), kind) for fp, kind in _sources()))


def all_file() -> Path:
    """全部上市品种的名字（eligibility 写）：放数据目录的 cache/（.gitignore 的 var/cache/）—— 云端 / 例行任务的数据目录就是仓库 var/，
    放在根目录会被「git add quant_breakout/var」带进库；JPX 公开数据，但只是本机的缓存。"""
    return paths.home() / "cache" / ALL_FILE


def save_all(nm: dict, as_of: str = "", source: str = "") -> Path | None:
    """eligibility 取到 JPX 東証上場銘柄一覧（data_j.xlsx）时顺手写 {代码: 銘柄名}；空 → 不写。"""
    nm = {str(k).strip(): str(v).strip() for k, v in (nm or {}).items() if str(k).strip() and str(v or "").strip()}
    if not nm:
        return None
    from .utils import atomic_write_text
    fp = all_file()
    atomic_write_text(fp, json.dumps({"source": source or "JPX 東証上場銘柄一覧（data_j.xlsx；eligibility 取数时写）", "as_of": as_of,
                                      "names": dict(sorted(nm.items()))}, ensure_ascii=False))
    return fp


def jpx_snapshot() -> dict:
    """JPX 名称快照 jpx_names.json 本身（数据目录有就用它，没有〔或读不出名字：坏文件〕就用仓库 var/ 的；jpx_list.names() 转调这里）。"""
    for fp in (paths.home() / SNAPSHOT_FILE, paths.PROJECT_ROOT / "var" / SNAPSHOT_FILE):
        d = _read(fp)
        if d:
            return dict(d)
    return {}


# ── 名字与标签 ──
def _name(s: str, tbl: dict | None = None) -> str | None:
    if not s:
        return None
    if s in INDEX_NAMES:
        return INDEX_NAMES[s]
    c = code(s)
    if not _JP.fullmatch(c):                                       # 美股等：没有名字表（这次不做）
        return ETF_NAMES.get(s)
    return ETF_NAMES.get(c + ".T") or (_table() if tbl is None else tbl).get(c) or None


def name(t) -> str | None:
    """代码 → 名字（「7203.T」「7203」都行）；查不到 → None。下面这些对外的函数出了意外都退回「只写代码」/ 原文，绝不抛
    （名字只是显示用：执行器的事件、通知、日报、退市时间表都调它们；2026-10-15 复核）。"""
    try:
        return _name(str(t or "").strip())
    except Exception:                                             # noqa: BLE001
        return None


def shorten(n: str, width: int = SHORT_LEN) -> str:
    """窄处用的短名：NFKC 半角化、去掉「株式会社」、ホールディングス → HD、フィナンシャル・グループ → FG，超过 width 个字截短加「…」。"""
    s = unicodedata.normalize("NFKC", str(n or "")).replace("株式会社", "").replace("(株)", "")
    s = s.replace("ホールディングス", "HD")
    s = re.sub(r"フィナンシャル・?グループ", "FG", s)
    s = re.sub(r"(?<=[A-Za-z0-9])(HD|FG)(?![A-Za-z0-9])", r" \1", s)   # 「三菱UFJFG」→「三菱UFJ FG」「T&DHD」→「T&D HD」（ASCII 边界）
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= width else s[:max(1, width - 1)] + "…"


def short_name(t, _tbl: dict | None = None) -> str | None:
    """short=True 的名字：ETF 用精选的短名（ETF_SHORT），其余按 shorten() 的规则；查不到 → None。"""
    try:
        s = str(t or "").strip()
        n = _name(s, _tbl)
        if not n:
            return None
        return ETF_SHORT.get(code(s) + ".T") or ETF_SHORT.get(s) or shorten(n)
    except Exception:                                             # noqa: BLE001
        return None


def label(t, *, short: bool = False) -> str:
    """「7203.T」→「7203 トヨタ自動車」、「1545.T」→「1545 纳斯达克 100」；查不到名字 →「7203」（只写代码）。"""
    try:
        c = code(t)
        n = short_name(t) if short else name(t)
        return f"{c} {n}" if n and n != c else c
    except Exception:                                             # noqa: BLE001
        return code(t)


def labels(ts, sep: str = "、", limit: int | None = None, short: bool = False) -> str:
    """多只：「7203 トヨタ自動車、6758 ソニーグループ」；超过 limit 只 → 前 limit 只 +「 等 N 只」（N = 总数）。"""
    try:
        xs = [label(t, short=short) for t in (ts or [])]
        if limit is not None and len(xs) > limit:
            return sep.join(xs[:max(0, limit)]) + f" 等 {len(xs)} 只"
        return sep.join(xs)
    except Exception:                                             # noqa: BLE001
        try:
            return sep.join(code(t) for t in (ts or []))
        except Exception:                                         # noqa: BLE001
            return ""


def qty(t, s, *, short: bool = False) -> str:
    """「代码 名字」后面紧跟数量时用：「1545 纳斯达克 100：4,110 → 96 口」「7203 トヨタ自動車：100 股」；查不到名字 →「5202 100 股」
    （4 位代码后面接数量本来就分得清）。2026-10-15 复核：名字可能以数字结尾（「1545 纳斯达克 100」「1655 S&P500」「1329 日経225」），
    直接接数量写成「1545 纳斯达克 100 100 → 96 口」，读不出哪个是名字、哪个是口数。只用在给人看的文字里（cid / JSON / 命令行照旧）；
    中间隔着字的（「1545 纳斯达克 100 约 4,110 口」「固定 4,110 口」）不用它。页面脚本同一写法：static/core.js 的 tqty。"""
    try:
        lab = label(t, short=short)
        return f"{lab}：{s}" if lab != code(t) else f"{lab} {s}"
    except Exception:                                             # noqa: BLE001
        return f"{code(t)} {s}"


def names_map(ts=None) -> dict:
    """ts 给了 → {原样的 ticker: 名字}（只放查得到的；面板 CFG.names 用）；None → 全部 {代码: 名字}（ETF、指数也在里面；
    holding_view.names() 的旧用法：按不带 .T 的代码查）。"""
    try:
        if ts is not None:
            return {t: n for t in dict.fromkeys(ts) if t and (n := name(t))}
        out = dict(_table())
    except Exception:                                             # noqa: BLE001
        out = {}
        if ts is not None:
            return out
    out.update({code(t): n for t, n in ETF_NAMES.items()})
    out.update(INDEX_NAMES)
    return out


# ── annotate：兜底给文字里的「NNNN.T」加名字 ──
_TOKEN = re.compile(r"(?<![A-Za-z0-9_\-./'\"=])([0-9][0-9A-Z]{3})\.T(?![A-Za-z0-9_\-]|\.[A-Za-z0-9])")   # 后面 .json 之类 = 文件名
_URL = re.compile(r"https?://[^\s<>'\"）」]+")
_CMD = re.compile(r"(?<![A-Za-z0-9_])(?:bash|liveu\.sh|run\.py|python3?|dev\.sh|routines\.sh|adopt)(?![A-Za-z0-9_])"
                  r"|(?<![A-Za-z0-9_])manual\s+(?:sell|adjust|trim|buy|corefix|core|cancel|unblock|list)(?![A-Za-z0-9_])")
_SP = " 　"


def _seg(seg: str, short: bool, html: bool, tbl: dict) -> str:
    if ".T" not in seg or _CMD.search(seg):                       # 命令行（要复制粘贴的）整段不动
        return seg
    urls = [m.span() for m in _URL.finditer(seg)]

    def rep(m: re.Match) -> str:
        if any(a <= m.start() < b for a, b in urls):
            return m.group(0)
        c = m.group(1)
        full = _name(c, tbl)
        if not full:
            return m.group(0)                                     # 查不到名字：照原样（不去 .T）
        sn = short_name(c, tbl) or full
        cands = {full, sn}
        if html:
            cands |= {escape(x, quote=False) for x in list(cands)}
        after = seg[m.end():].lstrip(_SP)
        before = seg[max(0, m.start() - len(full) - 2):m.start()]
        if any(after.startswith(x) for x in cands) or any(x in before for x in cands):
            return c                                              # 已经带着名字：只去 .T，不重复
        n = sn if short else full
        return f"{c} {escape(n, quote=True) if html else n}"
    return _TOKEN.sub(rep, seg)


def annotate(text, *, short: bool = False, html: bool = False):
    """文字里查得到名字的「NNNN.T」→「NNNN 名字」（输出前的兜底；规则见模块说明）。不是字符串 → 照原样返回。
    html=True：名字先转义；按标签切段（一页 HTML 常常只有一行，命令行只跳过它所在的那一段）。"""
    if not isinstance(text, str) or ".T" not in text:
        return text
    try:
        tbl = _table()                                            # 一次取表（一页里几百个代码不用每个都去看文件）
        parts = re.split(r"(\n|(?=<))", text) if html else re.split(r"(\n)", text)
        return "".join(_seg(p, short, html, tbl) if p and p != "\n" else (p or "") for p in parts)
    except Exception:                                             # noqa: BLE001  兜底出了意外 → 原文（不能让出口跟着出错）
        return text


# ── 去重键：名字不算「新的原因」──
_SEEN_CODE = re.compile(r"(?<![A-Za-z0-9_\-./'\"=])([0-9][0-9A-Z]{3})(?:\.T)?(?![A-Za-z0-9_\-])")


def seen_key(text) -> str:
    """去重 / 前后比较用的文字（只拿来算键，不发出去、不显示）：「7203 トヨタ自動車」「7203 トヨタ」「7203.T」「7203」都还原成「7203.T」——
    代码后面加了名字（2026-10-15）、名字表更新（07:40 eligibility 写 cache/jpx_names_all.json 后某只从「5202」变成「5202 日本板硝子」）、
    全称 / 简称不同，都不当成新的原因，同一天不重复通知。run.py 的 notify_seen 键与手动指令前后比较、面板的通知去重共用（以前在 run.py._seen_txt）。"""
    s = str(text or "")
    try:
        tbl = _table()
        out, i = [], 0
        for m in _SEEN_CODE.finditer(s):
            if m.start() < i:                                     # 在刚跳过的名字里面
                continue
            t, j = m.group(1) + ".T", m.end()
            for n in sorted({_name(t, tbl) or "", short_name(t, tbl) or ""}, key=len, reverse=True):
                if n and s.startswith(" " + n, j):
                    j += 1 + len(n)
                    if s.startswith("：", j) and s[j + 1:j + 2].isdigit():   # qty() 的「名字：数量」= 以前的「代码 数量」（2026-10-15）
                        t, j = t + " ", j + 1
                    break
            out.append(s[i:m.start()] + t)
            i = j
        return "".join(out) + s[i:]
    except Exception:                                             # noqa: BLE001
        return s


__all__ = ["ETF_NAMES", "ETF_SHORT", "INDEX_NAMES", "code", "name", "short_name", "shorten", "label", "labels", "qty", "names_map",
           "annotate", "seen_key", "jpx_snapshot", "all_file", "save_all"]
