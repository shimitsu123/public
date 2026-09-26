"""news.py — 经济威胁消息的实时监控：取消息 → 判断可信度 → 归类事件 → 影响链路（因子 → 行业 → 持仓 / 候补）→ 提醒。
只作展示与提醒，不参与交易（交易规则只按事先登记、检验过的信号）。

来源（公开 RSS / JSON，每 15 分钟取一次也不算频繁）：NHK（経済 / 国際 / 主要）、Yahoo!ニュース（経済 / 国際）、
日本銀行、財務省、FRB 的新着，Google ニュース的关键词检索（日英各一），気象庁的地震情報（震度 5 弱以上）。
可信度（0〜100 分，只是经验打分，不是事实核查）：
  来源档位 —— 官方（日銀 / 財務省 / FRB / 気象庁）95、大媒体（NHK、日経、ロイター、Bloomberg、共同、時事…）80、
  编辑精选（Yahoo!ニュース トピックス）70、其他已知媒体 65、不认识的 50；
  交叉确认 —— 同一件事（标题相似）有 2 家 / 3 家以上不同来源报道 +10 / +20；有官方来源 → 至少 95；
  推测用语（「〜か」「関係者によると」「観測」「可能性」「reportedly」「sources said」…）−15。高 ≥ 80、中 60〜79、低 < 60。
影响链路：事件 → 因子冲击（按这类消息常见的幅度：日本 / 美国 10Y ±0.10 pp、美元日元 ±2%、原油 ±5%、信用利差 +0.20 pp）
  → TOPIX-17 行业（行业 ETF 对各因子的周敏感度 × 冲击，控制大盘，最近 104 周；qbreak/sensitivity.py pair_beta）
  → 持仓 / 候补队列里属于这些行业的票。关税、半导体规制、灾害、疫情等没有对应因子的，用经验规则只标方向（写明「经验规则」）。
提醒：负面事件、严重度 ≥ 2 且可信度 ≥ 70（或严重度 3 且可信度 ≥ 55）→ 提醒一次（同一件事不重复）。
公开仓库：标题与链接只写到 var/cache/news/（不入库）与本机页面；日报（会入库）只放汇总（事件类别、条数、影响的行业）。
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import json
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from urllib.parse import quote

from . import paths
from .calendar_jp import JST, now_jst
from .utils import read_json, write_json

log = logging.getLogger(__name__)

MAX_AGE_H = 72
ALERT_CRED, ALERT_CRED_SEVERE = 70, 55
SIM_MIN = 0.35                                   # 标题相似度（字符 2-gram 的 Jaccard）≥ 这个 → 同一件事

_GN_JA = ("(日銀 OR 利上げ OR 利下げ OR 円安 OR 円高 OR 為替介入 OR 関税 OR 原油 OR 景気後退 OR 経営破綻 OR 地震 OR ミサイル OR 株価急落)"
          " when:1d")
_GN_EN = ('(tariffs OR recession OR "rate hike" OR "rate cut" OR "oil prices" OR "sovereign default" OR "bank failure" '
          'OR sanctions OR "invasion of" OR "stocks plunge" OR "yen intervention") when:1d')
SOURCES = [
    ("NHK 経済", "https://www3.nhk.or.jp/rss/news/cat5.xml", "media"),
    ("NHK 国際", "https://www3.nhk.or.jp/rss/news/cat6.xml", "media"),
    ("NHK 主要", "https://www3.nhk.or.jp/rss/news/cat0.xml", "media"),
    ("Yahoo!ニュース 経済", "https://news.yahoo.co.jp/rss/topics/business.xml", "curated"),
    ("Yahoo!ニュース 国際", "https://news.yahoo.co.jp/rss/topics/world.xml", "curated"),
    ("日本銀行", "https://www.boj.or.jp/rss/whatsnew.xml", "official"),
    ("財務省", "https://www.mof.go.jp/news.rss", "official"),
    ("FRB", "https://www.federalreserve.gov/feeds/press_all.xml", "official"),
    ("Google ニュース", f"https://news.google.com/rss/search?q={quote(_GN_JA)}&hl=ja&gl=JP&ceid=JP:ja", "aggregator"),
    ("Google News", f"https://news.google.com/rss/search?q={quote(_GN_EN)}&hl=en-US&gl=US&ceid=US:en", "aggregator"),
]
JMA_QUAKE = "https://www.jma.go.jp/bosai/quake/data/list.json"
TIER = {"official": 95, "media": 80, "curated": 70}
MAJOR = ("日本経済新聞", "日経", "NHK", "ロイター", "Reuters", "Bloomberg", "ブルームバーグ", "共同通信", "時事", "朝日新聞", "読売新聞",
         "毎日新聞", "産経", "東京新聞", "テレ東", "テレビ東京", "TBS", "日テレ", "FNN", "Wall Street Journal", "WSJ", "Financial Times",
         "Associated Press", "AP News", "AFP", "CNBC", "BBC", "New York Times", "CNN", "Nikkei Asia", "Kyodo", "Jiji")
KNOWN = ("東洋経済", "ダイヤモンド", "ITmedia", "PRESIDENT", "Forbes", "Business Insider", "MarketWatch", "Yahoo Finance", "Barron",
         "Fortune", "Axios", "Politico", "Guardian", "Japan Times", "Mainichi", "Asahi", "Yomiuri", "Nikkei", "みんかぶ", "株探",
         "モーニングスター", "ZUU", "時事ドットコム", "nomura", "Investing.com", "Al Jazeera", "Deutsche Welle", "NPR",
         "Yahoo!ニュース", "Yahoo!ファイナンス", "文春", "Seeking Alpha", "Moomoo")
HEDGE = re.compile(r"(か$|か[　 ]|関係者(による|の話)|観測|うわさ|噂|未確認|とみられ|との見方|可能性|検討へ|見通し|予想(?!通り)|予測|SNS|匿名|"
                   r"\breportedly\b|\brumou?rs?\b|\bsources? (say|said|familiar)\b|\bunconfirmed\b|\bpeople familiar\b|"
                   r"\bforecasts?\b|\bexpects?\b|\boutlook\b|\bcould\b|\blikely\b)", re.I)

# 事件：键 → (中文名, 正则, 因子冲击 {因子: 冲击}, 经验规则 {TOPIX-17 行业: ±1}, 基础严重度, 负面?, 升级 (正则, 严重度) 或 None)
# 标题关键词归类会把评论 / 预告 / 回顾文章也算进来 → 基础严重度放低，只有出现「决定 / 发动 / 升级」一类用语才升到 2〜3（提醒要 ≥ 2）。
FACTOR_LABEL = {"rate_jp": "日本 10Y", "rate_us": "美国 10Y", "fx": "美元日元", "oil": "原油", "credit": "信用利差"}
FACTOR_UNIT = {"rate_jp": "pp", "rate_us": "pp", "fx": "%", "oil": "%", "credit": "pp"}
_BOJ = r"(日銀|日本銀行|BOJ|Bank of Japan|植田)"
_FED = r"(FRB|FOMC|米連邦準備|パウエル|\bFed\b|Federal Reserve|Powell)"
_IDX = r"(日経平均|東証株価指数|TOPIX|NYダウ|ダウ平均|米国株|S&P ?500|ナスダック)"
_DECIDE = r"(決定|決めた|踏み切|引き上げた|引き下げた|を引き上げ|を引き下げ|raises|raised|hikes|hiked|cuts rates|cut rates|lowers|lowered)"
_OIL = r"(原油|原油価格|原油先物|原油相場|WTI|北海ブレント)"
EVENTS = {
    "boj_hike": ("日银加息 / 收紧", re.compile(_BOJ + r".{0,30}(利上げ|金融引き締め|政策金利.{0,12}引き上げ|rate hike|raise[sd]? rates)", re.I),
                 {"rate_jp": 0.10, "fx": -1.0}, {}, 1, True, (re.compile(_DECIDE, re.I), 2)),
    "boj_decision": ("日银政策决定公布", re.compile(r"(当面の金融政策運営について|金融政策決定会合.{0,8}(結果|決定))"), {}, {}, 1, False, None),
    "fed_hike": ("美联储加息 / 偏鹰", re.compile(_FED + r".{0,30}(利上げ|タカ派|rate hike|raise[sd]? rates|hawkish)", re.I),
                 {"rate_us": 0.10, "fx": 1.0}, {}, 1, True, (re.compile(_DECIDE, re.I), 2)),
    "fed_cut": ("美联储降息 / 偏鸽", re.compile(_FED + r".{0,30}(利下げ|ハト派|rate cut|cut[s]? rates|dovish)", re.I),
                {"rate_us": -0.10, "fx": -1.0}, {}, 1, False, None),
    "fed_decision": ("FOMC 决定公布", re.compile(r"(FOMC statement|issues FOMC)", re.I), {}, {}, 1, False, None),
    "intervention": ("日元汇率干预", re.compile(r"(為替介入|介入.{0,6}(円|為替)|レートチェック|yen intervention|intervene.{0,20}yen)", re.I),
                     {"fx": -3.0}, {}, 1, True, (re.compile(r"(実施|踏み切|確認|intervened|confirms)", re.I), 2)),
    "yen_weak": ("日元急贬", re.compile(r"(円安.{0,8}(進|加速|急|最安)|円相場.{0,10}(下落|安値)|円急落|"
                                    r"yen (slides|slumps|weakens|tumbles|hits.{0,10}low))", re.I),
                 {"fx": 2.0}, {}, 1, True, None),
    "yen_strong": ("日元急升", re.compile(r"(円高.{0,8}(進|加速|急)|円相場.{0,10}(上昇|高値)|円急伸|円急騰|yen (surges|jumps|strengthens|soars))", re.I),
                   {"fx": -2.0}, {}, 1, True, None),
    "oil_up": ("原油供给冲击 / 油价急涨", re.compile(_OIL + r"(が|は)?(高騰|急騰|急伸|大幅上昇|高値|上昇)|(OPEC|産油国).{0,10}減産|ホルムズ|"
                                             r"oil (prices? )?(surge|jump|soar|spike|rall)|crude (surge|jump|soar|spike)|Hormuz|"
                                             r"(OPEC|oil).{0,20}output cut", re.I),
               {"oil": 5.0}, {}, 1, True, (re.compile(r"(封鎖|供給途絶|攻撃|急騰|blockade|closure|attack|surge|soar|spike)", re.I), 2)),
    "oil_down": ("油价急跌", re.compile(_OIL + r"(が|は)?(急落|大幅下落|下落|安値)|原油安|"
                                    r"oil (prices? )?(plunge|slump|tumble|crash|fall|drop|slide|sink)", re.I),
                 {"oil": -5.0}, {}, 1, False, None),
    "credit": ("金融系统风险（银行危机 / 主权违约）", re.compile(r"(信用不安|金融危機|取り付け|銀行.{0,6}破綻|債務不履行|デフォルト|"
                                                   r"bank (failure|collapse|run)|banking crisis|credit crunch|sovereign default|"
                                                   r"default(s|ed)? on.{0,20}(debt|bonds))", re.I),
               {"credit": 0.20}, {"银行": -1, "金融（除银行）": -1}, 2, True, (re.compile(r"(連鎖|破綻|collapse|failure|run on)", re.I), 3)),
    "bankruptcy": ("企业破产", re.compile(r"(経営破綻|倒産|民事再生|会社更生|bankrupt|chapter 11|insolven)", re.I),
                   {"credit": 0.02}, {}, 1, True, (re.compile(r"(連鎖倒産|大型倒産|過去最大|largest ever|record bankrupt)", re.I), 2)),
    "war": ("战争 / 军事冲突升级", re.compile(r"(侵攻|ミサイル.{0,4}発射(?!機|台|装置)|ミサイル攻撃|弾道ミサイル|軍事衝突|空爆|武力攻撃|核実験|開戦|宣戦|"
                                         r"invasion of|invaded|missile (strike|attack|launch)|airstrike|military strike|declares? war)", re.I),
            {"oil": 3.0, "credit": 0.05}, {"机械": 1, "运输·物流": -1}, 1, True,
            (re.compile(r"(核|全面|大規模攻撃|新たに|開始|nuclear|full-scale|all-out|launches|launched)", re.I), 3)),
    "tariff": ("关税 / 贸易摩擦 / 制裁", re.compile(r"(追加関税|報復関税|相互関税|関税.{0,6}(引き上げ|発動|賦課|強化|措置)|貿易摩擦|貿易戦争|輸出規制|"
                                              r"経済制裁|\btariffs?\b|trade war|export controls?|sanctions? on)", re.I),
               {}, {"汽车·运输机": -1, "电机·精密": -1, "机械": -1, "钢铁·有色": -1}, 1, True,
               (re.compile(r"(発動|引き上げ|報復|imposes?|slaps?|new tariffs|raises? tariffs|tariff hike|takes effect)", re.I), 2)),
    "semis": ("半导体规制", re.compile(r"(半導体.{0,12}(規制|輸出|禁止)|chip (export|ban|curb)|semiconductor (curb|ban|export))", re.I),
              {}, {"电机·精密": -1, "机械": -1}, 1, True, (re.compile(r"(発動|強化|新た|imposes?|tighten|new)", re.I), 2)),
    "disaster": ("自然灾害", re.compile(r"(大地震|震度[5-7５-７]|津波(警報|注意報)|大津波|噴火警報|特別警報|甚大な被害|大規模災害|災害救助法|"
                                    r"台風.{0,10}(上陸|甚大|記録的)|major earthquake|tsunami warning|magnitude [6-9]|"
                                    r"devastating (earthquake|typhoon|hurricane|flood))", re.I),
                 {}, {"建设·资材": 1, "金融（除银行）": -1, "零售": -1}, 1, True,
                 (re.compile(r"(震度[6-7６-７]|大津波|甚大な被害|大規模災害|magnitude [7-9]|major earthquake)", re.I), 3)),
    "pandemic": ("疫情", re.compile(r"(パンデミック|新型ウイルス|緊急事態宣言|(新型|世界的).{0,6}感染拡大|pandemic|lockdown)", re.I),
                 {}, {"运输·物流": -1, "零售": -1, "医药品": 1}, 2, True, None),
    "recession": ("景气转弱 / 衰退", re.compile(r"(景気後退|リセッション|景気.{0,6}悪化|失業率.{0,6}(上昇|悪化)|マイナス成長|recession|"
                                        r"jobless claims (rise|jump)|economy (shrinks|contracts))", re.I),
                  {"rate_us": -0.10, "credit": 0.05}, {}, 1, True,
                  (re.compile(r"(入り|確認|急上昇|急増|マイナス成長|shrinks|contracts|jump)", re.I), 2)),
    "inflation": ("通胀升温", re.compile(r"(インフレ.{0,8}(加速|上振れ|高進)|物価.{0,8}(高騰|上振れ)|inflation (accelerat|jump|surge|hotter|rises))", re.I),
                  {"rate_us": 0.10}, {}, 2, True, None),
    "crash": ("股市急跌", re.compile(_IDX + r".{0,10}(急落|暴落|大幅安|大幅下落|下げ幅)|世界同時株安|stocks? (plunge|tumble|crash|sink)|"
                                          r"Wall Street (plunges|tumbles)|market (crash|rout)|sell-?off", re.I),
              {}, {}, 2, True, (re.compile(r"(暴落|世界同時株安|ブラックマンデー|crash|rout)", re.I), 3)),
    "politics": ("政局 / 财政", re.compile(r"(衆院解散|解散総選挙|内閣.{0,4}(総辞職|不信任)|政府閉鎖|債務上限|government shutdown|debt ceiling)", re.I),
                 {}, {}, 1, True, None),
}
CONFLICT = (("oil_down", "oil_up"), ("yen_strong", "yen_weak"), ("fed_cut", "fed_hike"))   # 同时命中 → 去掉后一个（方向以明确的价格用语为准）
SHOCK_TXT = {"rate_jp": "日本 10Y {:+.2f} pp", "rate_us": "美国 10Y {:+.2f} pp", "fx": "美元日元 {:+.0f}%", "oil": "原油 {:+.0f}%",
             "credit": "信用利差 {:+.2f} pp"}

# 东证 33 业种 → TOPIX-17 行业（qbreak/sectors.py 的 SECTOR_ETF_JP 名称）
S33_TO_17 = {
    "水産・農林業": "食品", "食料品": "食品", "鉱業": "能源资源", "石油・石炭製品": "能源资源",
    "建設業": "建设·资材", "ガラス・土石製品": "建设·资材", "金属製品": "建设·资材",
    "繊維製品": "素材·化学", "パルプ・紙": "素材·化学", "化学": "素材·化学", "医薬品": "医药品",
    "ゴム製品": "汽车·运输机", "輸送用機器": "汽车·运输机", "鉄鋼": "钢铁·有色", "非鉄金属": "钢铁·有色", "機械": "机械",
    "電気機器": "电机·精密", "精密機器": "电机·精密", "その他製品": "信息通信·服务", "情報・通信業": "信息通信·服务",
    "サービス業": "信息通信·服务", "電気・ガス業": "电力·燃气", "陸運業": "运输·物流", "海運業": "运输·物流", "空運業": "运输·物流",
    "倉庫・運輸関連業": "运输·物流", "卸売業": "商社·批发", "小売業": "零售", "銀行業": "银行",
    "証券、商品先物取引業": "金融（除银行）", "保険業": "金融（除银行）", "その他金融業": "金融（除银行）", "不動産業": "不动产",
}


# ── 取数与解析 ──
def _txt(el, *names) -> str:
    for n in names:
        for c in el:
            if c.tag.split("}")[-1] == n and (c.text or "").strip():
                return c.text.strip()
    return ""


def _when(s: str) -> dt.datetime | None:
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=JST)
    return d.astimezone(JST)


def parse_feed(raw: bytes | str, name: str, kind: str) -> list[dict]:
    """RSS 2.0 / RSS 1.0（RDF）/ Atom → [{title, link, time, source, publisher, kind}]。Google ニュース取 <source> 的出版方。"""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log.warning("%s 解析失败：%s", name, e)
        return []
    out = []
    for el in root.iter():
        if el.tag.split("}")[-1] not in ("item", "entry"):
            continue
        title = _txt(el, "title")
        link = _txt(el, "link")
        if not link:
            for c in el:
                if c.tag.split("}")[-1] == "link" and c.get("href"):
                    link = c.get("href")
                    break
        pub = _txt(el, "source") if kind == "aggregator" else ""
        if pub and title.endswith(" - " + pub):
            title = title[: -len(pub) - 3].strip()
        t = _when(_txt(el, "pubDate", "date", "updated", "published"))
        if title:
            out.append({"title": title, "link": link, "time": t.isoformat(timespec="minutes") if t else None, "source": name,
                        "publisher": pub or name, "kind": kind})
    return out


def parse_jma(raw: bytes | str, min_int: str = "5-") -> list[dict]:
    """気象庁 地震情報一览 → 震度 min_int 以上的「震源・震度情報」。"""
    order = ["1", "2", "3", "4", "5-", "5+", "6-", "6+", "7"]
    try:
        rows = json.loads(raw)
    except (ValueError, TypeError):
        return []
    out, seen = [], set()
    for r in rows or []:
        mx = str(r.get("maxi") or "")
        if mx not in order or order.index(mx) < order.index(min_int) or r.get("eid") in seen:
            continue
        seen.add(r.get("eid"))
        t = _when(r.get("at") or "")
        jp = mx.replace("-", "弱").replace("+", "強")
        out.append({"title": f"地震 最大震度{jp}（{r.get('anm') or '震源不明'}、M{r.get('mag') or '?'}）", "link": "https://www.jma.go.jp/bosai/map.html#contents=earthquake_map",
                    "time": t.isoformat(timespec="minutes") if t else None, "source": "気象庁", "publisher": "気象庁", "kind": "official",
                    "quake": mx})
    return out


def fetch_all(get=None, timeout: int = 20) -> tuple[list[dict], dict]:
    """全部来源；get(url) → bytes（默认 qbreak.factors._get，失败只记下）。返回（条目，{来源: 条数或错误}）。"""
    if get is None:
        from .factors import _get
        get = lambda u: _get(u, timeout=timeout, tries=1)                    # noqa: E731
    items, stat = [], {}
    for name, url, kind in SOURCES:
        try:
            got = parse_feed(get(url), name, kind)
            items += got
            stat[name] = len(got)
        except Exception as e:                                               # noqa: BLE001
            stat[name] = f"失败：{type(e).__name__}"
    try:
        got = parse_jma(get(JMA_QUAKE))
        items += got
        stat["気象庁 地震"] = len(got)
    except Exception as e:                                                   # noqa: BLE001
        stat["気象庁 地震"] = f"失败：{type(e).__name__}"
    return items, stat


# ── 可信度、归类、聚类 ──
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[\s\W_]+", "", s)


def _grams(s: str) -> set[str]:
    n = _norm(s)
    return {n[i:i + 2] for i in range(len(n) - 1)} or {n}


def similar(a: str, b: str) -> float:
    x, y = _grams(a), _grams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def source_score(it: dict) -> tuple[int, str]:
    k = it.get("kind")
    if k in TIER:
        return TIER[k], {"official": "官方", "media": "大媒体", "curated": "编辑精选"}[k]
    pub = it.get("publisher") or ""
    if any(m.lower() in pub.lower() for m in MAJOR):
        return 80, "大媒体"
    if any(m.lower() in pub.lower() for m in KNOWN):
        return 65, "已知媒体"
    return 50, "来源不明"


def classify(text: str) -> list[str]:
    evs = [k for k, (_, rx, *_rest) in EVENTS.items() if rx.search(text)]
    for keep, drop in CONFLICT:
        if keep in evs and drop in evs:
            evs.remove(drop)
    return evs


def severity(evs: list[str], text: str) -> int:
    out = 0
    for e in evs:
        base, esc = EVENTS[e][4], EVENTS[e][6]
        out = max(out, max(base, esc[1]) if esc is not None and esc[0].search(text) else base)
    return out


def cluster(items: list[dict], sim_min: float = SIM_MIN) -> list[list[dict]]:
    """标题相似的归成同一件事（贪心；按时间新的在前）。"""
    items = sorted(items, key=lambda z: z.get("time") or "", reverse=True)
    groups: list[list[dict]] = []
    for it in items:
        for g in groups:
            if similar(it["title"], g[0]["title"]) >= sim_min:
                g.append(it)
                break
        else:
            groups.append([it])
    return groups


def credibility(g: list[dict]) -> tuple[int, list[str]]:
    """一件事（一组相似标题）的可信度与理由。"""
    best = max(g, key=lambda z: source_score(z)[0])
    base, tier = source_score(best)
    why = [f"来源：{best.get('publisher')}（{tier}）"]
    pubs = {(z.get("publisher") or z.get("source")) for z in g}
    n = len(pubs)
    score = base + (20 if n >= 3 else 10 if n == 2 else 0)
    if n >= 2:
        why.append(f"{n} 个不同来源都有报道")
    if any(z.get("kind") == "official" for z in g):
        score = max(score, 95)
    elif all(HEDGE.search(z["title"]) for z in g):
        score -= 15
        why.append("标题是推测 / 未确认的说法")
    return max(0, min(100, score)), why


def cred_label(s: int) -> str:
    return "高" if s >= 80 else ("中" if s >= 60 else "低")


# ── 影响链路 ──
def sector_impacts(shocks: dict[str, float], betas: dict[str, dict[str, float]]) -> list[tuple[str, float]]:
    """行业 → Σ 敏感度 × 冲击（%）；betas = {行业名: {因子: 敏感度}}。按影响从大到小。"""
    out = []
    for sec, b in (betas or {}).items():
        v = sum(float(b[f]) * x for f, x in shocks.items() if b.get(f) is not None)
        if shocks and any(b.get(f) is not None for f in shocks):
            out.append((sec, round(v, 2)))
    return sorted(out, key=lambda z: -abs(z[1]))


def chain(evs: list[str], betas: dict, holdings: dict[str, str] | None = None, top: int = 3) -> dict:
    """事件 → 因子冲击 → 行业（敏感度估算 + 经验规则）→ 持仓 / 候补里的票。holdings = {代码: TOPIX-17 行业}。"""
    shocks: dict[str, float] = {}
    rules: dict[str, int] = {}
    for e in evs:
        for f, x in EVENTS[e][2].items():
            shocks[f] = shocks.get(f, 0.0) + x
        for s, d in EVENTS[e][3].items():
            rules[s] = rules.get(s, 0) + d
    imp = sector_impacts(shocks, betas)
    up = [(s, v) for s, v in imp if v > 0][:top]
    dn = [(s, v) for s, v in imp if v < 0][:top]
    good = {s for s, _ in up} | {s for s, d in rules.items() if d > 0}
    bad = {s for s, _ in dn} | {s for s, d in rules.items() if d < 0}
    hold = holdings or {}
    return {"shocks": {f: round(x, 3) for f, x in shocks.items()},
            "shock_txt": "、".join(SHOCK_TXT[f].format(x) for f, x in shocks.items() if abs(x) > 1e-9),
            "up": up, "down": dn, "rules": {s: d for s, d in rules.items() if d},
            "tickers_down": sorted(t for t, s in hold.items() if s in bad), "tickers_up": sorted(t for t, s in hold.items() if s in good)}


def analyze(items: list[dict], betas: dict | None = None, holdings: dict[str, str] | None = None,
            now: dt.datetime | None = None, max_age_h: float = MAX_AGE_H) -> list[dict]:
    """条目 → 与经济有关的「事件」列表（按威胁从高到低）。"""
    now = now or now_jst()
    fresh = []
    for it in items:
        t = _when(it.get("time") or "")
        if t is None or (now - t).total_seconds() / 3600 > max_age_h or (t - now).total_seconds() > 3600:
            continue
        fresh.append(it)
    out = []
    for g in cluster(fresh):
        text = " ".join(z["title"] for z in g)
        evs = classify(text)
        if any(z.get("quake") for z in g):
            evs = ["disaster"] + [e for e in evs if e != "disaster"]
        if not evs:
            continue
        cred, why = credibility(g)
        sev = severity(evs, text)
        if any(z.get("quake") in ("6-", "6+", "7") for z in g):
            sev = 3
        elif any(z.get("quake") for z in g):
            sev = max(sev, 2)
        neg = any(EVENTS[e][5] for e in evs)
        alert = neg and ((sev >= 2 and cred >= ALERT_CRED) or (sev >= 3 and cred >= ALERT_CRED_SEVERE))
        head = g[0]
        out.append({"id": hashlib.sha1(_norm(head["title"]).encode()).hexdigest()[:12], "title": head["title"], "link": head.get("link"),
                    "time": head.get("time"), "publisher": head.get("publisher"), "n_sources": len({z.get("publisher") for z in g}),
                    "others": [{"title": z["title"], "publisher": z.get("publisher"), "link": z.get("link")} for z in g[1:4]],
                    "events": evs, "event_labels": [EVENTS[e][0] for e in evs], "severity": sev, "negative": neg,
                    "cred": cred, "cred_label": cred_label(cred), "why": why, "alert": alert,
                    "threat": round(sev * cred / 100, 2) if neg else 0.0, "chain": chain(evs, betas or {}, holdings)})
    out.sort(key=lambda z: z.get("time") or "", reverse=True)                  # 同样威胁：新的在前
    return sorted(out, key=lambda z: -z["threat"])


def summary(events: list[dict]) -> dict:
    """日报（会入库）用的汇总：不含标题与链接。"""
    by: dict[str, dict] = {}
    for e in events:
        for k in e["events"]:
            b = by.setdefault(k, {"label": EVENTS[k][0], "n": 0, "alerts": 0, "max_cred": 0, "negative": EVENTS[k][5]})
            b["n"] += 1
            b["alerts"] += int(e["alert"])
            b["max_cred"] = max(b["max_cred"], e["cred"])
    secs: dict[str, float] = {}
    for e in events:
        if e["negative"] and e["cred"] >= 60:
            for s, v in e["chain"]["up"] + e["chain"]["down"]:
                secs[s] = secs.get(s, 0.0) + v
    return {"n_events": len(events), "n_alerts": sum(e["alert"] for e in events),
            "max_threat": max((e["threat"] for e in events), default=0.0), "by_type": by,
            "sectors": sorted(((s, round(v, 2)) for s, v in secs.items()), key=lambda z: z[1])}


# ── 行业敏感度（每周更新一次，缓存）──
def sector_betas(max_age_days: float = 7.0, inputs: dict | None = None) -> dict:
    """TOPIX-17 行业 ETF 对 5 个宏观因子的周敏感度（控制日経225，最近 104 周）：{行业名: {因子: %/单位}}。缓存 out/sector_betas.json。"""
    fp = paths.out_dir() / "sector_betas.json"
    old = read_json(fp, {}) or {}
    try:
        if old.get("date") and (now_jst().date() - dt.date.fromisoformat(old["date"])).days < max_age_days:
            return old.get("betas") or {}
    except ValueError:
        pass
    try:
        import pandas as pd

        from . import sensitivity as SN
        from . import threat as T
        from .config import DataConfig
        from .data import load_universe
        from .sectors import SECTOR_ETF_JP
        d = inputs or T.load_inputs()
        r = d["raw"]
        days = d["n225"].index[d["n225"].index >= d["n225"].index[-1] - pd.Timedelta(days=365 * 3)]
        lv = SN.factor_levels(days, d["n225"], d["jgb"], r["DGS10"], r["DCOILWTICO"], d["fx"], r["BAA10Y"])
        W = SN.weekly_changes(lv)
        etf = load_universe(list(SECTOR_ETF_JP), DataConfig(provider="yfinance", years=5, allow_synthetic=False).validate())
        out = {}
        for sym, name in SECTOR_ETF_JP.items():
            df = etf.get(sym)
            if df is None or not len(df):
                continue
            y = SN.stock_weekly(df["Close"], W.index)
            row = {}
            for f in SN.FACTORS:
                b = SN.pair_beta(y, W[f], W["mkt"], W.index[-1])
                if b is not None:
                    row[f] = round(b[0], 4)
            out[name] = row
        write_json(fp, {"date": str(now_jst().date()), "note": "TOPIX-17 行业 ETF 周收益 ~ 大盘 + 单个因子，最近 104 周（qbreak/news.py）",
                        "betas": out})
        return out
    except Exception as e:                                                   # noqa: BLE001
        log.warning("行业敏感度计算失败（用旧的）：%s", e)
        return old.get("betas") or {}


def holdings_map(tickers: list[str]) -> dict[str, str]:
    """代码 → TOPIX-17 行业（var/industry_s33.json）；没有的略过。"""
    doc = read_json(paths.home() / "industry_s33.json", None) or read_json(paths.PROJECT_ROOT / "var" / "industry_s33.json", {}) or {}
    s33 = doc.get("s33") or {}                                               # Mac 的数据目录没有这个文件 → 用仓库里的
    out = {}
    for t in tickers:
        s = S33_TO_17.get(s33.get(str(t).split(".")[0], ""))
        if s:
            out[t] = s
    return out


# ── 存取与提醒 ──
def cache_dir():
    return paths.sub("cache/news")


def save(events: list[dict], stat: dict, generated: str) -> None:
    write_json(cache_dir() / "news.json", {"generated": generated, "sources": stat, "events": events})


def load() -> dict:
    return read_json(cache_dir() / "news.json", {}) or {}


def new_alerts(events: list[dict], state_path=None, keep_h: float = 7 * 24, now: dt.datetime | None = None) -> list[dict]:
    """还没提醒过的提醒事件（同一件事只提醒一次；记录保留 7 天）。"""
    now = now or now_jst()
    fp = state_path or (cache_dir() / "alerted.json")
    seen = read_json(fp, {}) or {}
    keep = {}
    for k, v in seen.items():
        try:
            if (now - dt.datetime.fromisoformat(v)).total_seconds() < keep_h * 3600:
                keep[k] = v
        except (TypeError, ValueError):
            continue
    out = [e for e in events if e["alert"] and e["id"] not in keep]
    for e in out:
        keep[e["id"]] = now.isoformat(timespec="minutes")
    write_json(fp, keep)
    return out


def alert_text(e: dict) -> str:
    c = e["chain"]
    parts = [f"{'、'.join(e['event_labels'])}｜可信度 {e['cred']}（{e['cred_label']}）"]
    if c.get("shock_txt"):
        parts.append(f"冲击：{c['shock_txt']}")
    if c.get("down"):
        parts.append("受损：" + "、".join(f"{s} {v:+.1f}%" for s, v in c["down"]))
    if c.get("rules"):
        parts.append("经验规则：" + "、".join(f"{s}{'↑' if d > 0 else '↓'}" for s, d in c["rules"].items()))
    if c.get("tickers_down"):
        parts.append("受损方向的持仓 / 候补：" + "、".join(c["tickers_down"][:6]))
    return "；".join(parts)


def notify_mac(title: str, text: str) -> bool:
    """macOS 通知中心（只在 Mac 上；失败不影响任何东西）。"""
    import subprocess
    import sys
    if sys.platform != "darwin":
        return False
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')                 # noqa: E731
    try:
        subprocess.run(["osascript", "-e", f'display notification "{esc(text[:220])}" with title "{esc(title[:60])}"'],
                       check=False, timeout=10, capture_output=True)
        return True
    except Exception:                                                        # noqa: BLE001
        return False
