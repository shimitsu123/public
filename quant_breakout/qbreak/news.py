"""news.py — 经济威胁消息的实时监控：取消息 → 判断可信度 → 归类事件 → 影响链路（因子 → 行业 → 持仓 / 候补）→ 提醒。
只作展示与提醒，不参与交易（交易规则只按事先登记、检验过的信号）。

来源（公开 RSS / JSON，每 15 分钟取一次也不算频繁）：NHK（経済 / 国際 / 主要）、Yahoo!ニュース（経済 / 国際）、
日本銀行、財務省、FRB 的新着，Google ニュース的关键词检索（日英各一）。
2026-10-29 用户「关于地震之类的消息不要推送 / 放到消息里」：自然灾害（地震 / 津波 / 台风 / 喷火…，事件 disaster）不再取、不再显示、不再推送
（MUTED_EVENTS；気象庁的地震情報不再取，Google ニュース的检索词去掉「地震」；同一条里还有别的事件的照常按别的事件算）。
可信度（0〜100 分，只是经验打分，不是事实核查）：
  来源档位 —— 官方（日銀 / 財務省 / FRB / 気象庁）95、大媒体（NHK、日経、ロイター、Bloomberg、共同、時事…）80、
  编辑精选（Yahoo!ニュース トピックス）70、其他已知媒体 65、不认识的 50；
  交叉确认 —— 同一件事（标题相似）有 2 家 / 3 家以上不同来源报道 +10 / +20；有官方来源 → 至少 95；
  推测用语（「〜か」「関係者によると」「観測」「可能性」「reportedly」「sources said」…）−15。高 ≥ 80、中 60〜79、低 < 60。
影响链路：事件 → 因子冲击（按这类消息常见的幅度：日本 / 美国 10Y ±0.10 pp、美元日元 ±2%、原油 ±5%、信用利差 +0.20 pp）
  → TOPIX-17 行业（行业 ETF 对各因子的周敏感度 × 冲击，控制大盘，最近 104 周；qbreak/sensitivity.py pair_beta）
  → 持仓 / 候补队列里属于这些行业的票。关税、半导体规制、灾害、疫情等没有对应因子的，用经验规则只标方向（写明「经验规则」）。
提醒：负面事件、严重度 ≥ 2 且可信度 ≥ 70（或严重度 3 且可信度 ≥ 55）→ 提醒一次（同一件事不重复：换了媒体 / 换了说法的同一件事
  48 小时内也不再推，只推第一次；严重度升级才再推 —— new_alerts，2026-10-17）。
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

from . import news_country as NC
from . import paths
from .calendar_jp import JST, is_trading_day, next_trading_day, now_jst
from .utils import read_json, write_json

log = logging.getLogger(__name__)

MAX_AGE_H = 72
ALERT_CRED, ALERT_CRED_SEVERE = 70, 55
MUTED_EVENTS = frozenset({"disaster"})        # 不取、不显示、不推送的事件（2026-10-29 用户：地震之类的消息不要）
SIM_MIN = 0.35                                   # 标题相似度（字符 2-gram 的 Jaccard）≥ 这个 → 同一件事

_GN_JA = ("(日銀 OR 利上げ OR 利下げ OR 円安 OR 円高 OR 為替介入 OR 関税 OR 原油 OR 景気後退 OR 経営破綻 OR ミサイル OR 株価急落)"
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
# 朝鲜的导弹发射 / 核试验之类（2026-10-12 用户：「不用推送，也不用算成威胁因素」）：提到朝鲜的标题不算「战争 / 军事冲突」
# （同一条里别的事件——股市急跌等——照常算）。
NO_WAR = re.compile(r"(北朝鮮|北朝鲜|朝鲜|朝鮮中央|金正恩|平壌|平壤|North Korea|N\. ?Korea|Pyongyang|DPRK|Kim Jong)", re.I)
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
    """RSS 2.0 / RSS 1.0（RDF）/ Atom → [{title, link, time, source, publisher, country, kind}]。Google ニュース取 <source> 的出版方
    （与它的网址 <source url>）；country = 来源国家（qbreak/news_country.py）。"""
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
        pub_url = next((c.get("url") for c in el if c.tag.split("}")[-1] == "source" and c.get("url")), "") if pub else ""
        if pub and title.endswith(" - " + pub):
            title = title[: -len(pub) - 3].strip()
        t = _when(_txt(el, "pubDate", "date", "updated", "published"))
        if title:
            out.append({"title": title, "link": link, "time": t.isoformat(timespec="minutes") if t else None, "source": name,
                        "publisher": pub or name, "country": NC.country(pub or name, pub_url), "kind": kind})
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
                    "time": t.isoformat(timespec="minutes") if t else None, "source": "気象庁", "publisher": "気象庁", "country": "日本", "kind": "official",
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
    if "disaster" not in MUTED_EVENTS:                                       # 2026-10-29 起不取（用户：地震之类的消息不要）
        try:
            got = parse_jma(get(JMA_QUAKE))
            items += got
            stat["気象庁 地震"] = len(got)
        except Exception as e:                                               # noqa: BLE001
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
    if "war" in evs and NO_WAR.search(text):
        evs.remove("war")
    for keep, drop in CONFLICT:
        if keep in evs and drop in evs:
            evs.remove(drop)
    return [e for e in evs if e not in MUTED_EVENTS]


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
    why = [f"来源：{NC.of_event(best)}（{tier}）"]                      # 只写国家（2026-10-19 用户）
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
            "impacts": [(s, v) for s, v in imp if abs(v) >= 0.01],                 # 全部行业的估算冲击（%；个股标记用）
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
        if it.get("quake") and "disaster" in MUTED_EVENTS:                     # 以前缓存下来的気象庁地震情報：不显示、不推送
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
                    "time": head.get("time"), "publisher": head.get("publisher"), "country": NC.of_event(head), "n_sources": len({z.get("publisher") for z in g}),
                    "others": [{"title": z["title"], "publisher": z.get("publisher"), "country": NC.of_event(z), "link": z.get("link")}
                               for z in g[1:4]],
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
        if old.get("date") and "assets" in old and (now_jst().date() - dt.date.fromisoformat(old["date"])).days < max_age_days:
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
        from .money_view import CORE_NAMES
        etf = load_universe(list(SECTOR_ETF_JP) + list(CORE_NAMES), DataConfig(provider="yfinance", years=5, allow_synthetic=False).validate())

        def fit(sym: str) -> dict:
            df = etf.get(sym)
            if df is None or not len(df):
                return {}
            y = SN.stock_weekly(df["Close"], W.index)
            row = {}
            for f in SN.FACTORS:
                b = SN.pair_beta(y, W[f], W["mkt"], W.index[-1])
                if b is not None:
                    row[f] = round(b[0], 4)
            return row
        out = {name: r for sym, name in SECTOR_ETF_JP.items() if (r := fit(sym))}
        assets = {sym: r for sym in CORE_NAMES if (r := fit(sym))}      # 核心 ETF（持仓的标记用；2026-10-11）
        write_json(fp, {"date": str(now_jst().date()), "note": "TOPIX-17 行业 ETF / 核心 ETF 周收益 ~ 大盘 + 单个因子，最近 104 周（qbreak/news.py）",
                        "betas": out, "assets": assets})
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


def asset_betas() -> dict:
    """核心 ETF 的周敏感度（sector_betas 顺便算、缓存在 out/sector_betas.json 的 assets；这里只读，不联网）。"""
    return (read_json(paths.out_dir() / "sector_betas.json", {}) or {}).get("assets") or {}


# ── 消息的程度（2026-10-11 用户：威胁程度低的消息不用显示，按程度用颜色区分）──
def level(e: dict) -> str:
    """消息的程度：严重度 × 可信度 /100（正负面都算）→ 高（≥ 1.5）/ 中（≥ 0.8）/ 低（其余：面板不显示）。
    2026-10-12 起不再「达到提醒线就算高」：推送只推「高」（pushable），面板的高 / 中与推送一致。"""
    s = float(e.get("severity") or 1) * float(e.get("cred") or 0) / 100
    return "高" if s >= 1.5 else "中" if s >= 0.8 else "低"


def pushable(e: dict) -> bool:
    """推送（手机 / Mac 通知）：达到提醒线（负面、严重度 × 可信度够）且程度「高」（≥ 1.5）。2026-10-12 用户「只推送威胁度为高的，中的不用推送」。"""
    return bool(e.get("alert")) and level(e) == "高"


# ── 影响什么时候开始、持续多久（2026-10-11 用户：持仓要标大概什么时候影响、什么时候结束、影响多久）──
# 每类事件对行业 / 资产价格的影响一般持续几个交易日（经验估计：决定公布类当天到两天消化；供给冲击 / 战争 / 关税几周；
# 金融系统风险、衰退、疫情更久）。没有用历史消息回测过 → 页面写「经验估计」，只作参考。
DURATION = {"boj_hike": (3, 10), "boj_decision": (1, 2), "fed_hike": (3, 10), "fed_cut": (3, 10), "fed_decision": (1, 2),
            "intervention": (1, 5), "yen_weak": (2, 5), "yen_strong": (2, 5), "oil_up": (5, 20), "oil_down": (3, 10),
            "credit": (10, 40), "bankruptcy": (1, 5), "war": (5, 20), "tariff": (5, 20), "semis": (5, 20), "disaster": (3, 10),
            "pandemic": (20, 60), "recession": (10, 40), "inflation": (5, 15), "crash": (2, 10), "politics": (3, 10)}


def _add_tdays(d: dt.date, n: int) -> dt.date:
    for _ in range(max(0, n)):
        d = next_trading_day(d)
    return d


def timing(e: dict, now: dt.datetime | None = None) -> dict | None:
    """一条消息的影响期（日本时间）：开始 = 发布在交易日 09:00〜15:30 → 当天（盘中已开始反映），否则下一个交易日开盘；
    持续 lo〜hi 个交易日（DURATION，几类事件取最长的）；结束 ≈ 开始 + hi − 1 个交易日。
    → {start, end, lo, hi, intraday, state: 未开始 / 影响中 / 已过}；时间读不出 → None。"""
    now = (now or now_jst()).astimezone(JST)
    try:
        t = dt.datetime.fromisoformat(str(e.get("time")))
    except (TypeError, ValueError):
        return None
    t = t.astimezone(JST) if t.tzinfo else t.replace(tzinfo=JST)
    d = t.date()
    intraday = is_trading_day(d) and dt.time(9, 0) <= t.time() < dt.time(15, 30)
    start = d if intraday or (is_trading_day(d) and t.time() < dt.time(9, 0)) else next_trading_day(d)
    lo, hi = max((DURATION.get(k, (2, 5)) for k in e.get("events") or []), key=lambda x: x[1], default=(2, 5))
    end = _add_tdays(start, hi - 1)
    today = now.date()
    if today > end or (today == end and now.time() >= dt.time(15, 30)):
        state = "已过"
    elif today < start or (today == start and now.time() < dt.time(9, 0)):
        state = "未开始"
    else:
        state = "影响中"
    return {"start": start.isoformat(), "end": end.isoformat(), "lo": lo, "hi": hi, "intraday": intraday, "state": state}


RULE_PCT = 0.5          # 只有经验规则、没有敏感度估算的行业：当作 ±0.5% 的冲击
LEVELS = ((1.0, "大"), (0.4, "中"), (0.1, "小"))


def ticker_impacts(events: list[dict], tickers: list[str], sectors: dict[str, str] | None = None,
                   assets: dict | None = None, now: dt.datetime | None = None) -> dict[str, dict]:
    """消息对个股的影响（2026-10-11 用户：「候选股票上如果实时消息中出现了对该股的影响，根据影响大小标记，并且可以看到对应的消息」）。
    个股 → TOPIX-17 行业 → 每条消息对这个行业的估算冲击（chain.impacts，%；只有经验规则 → ±RULE_PCT）× 可信度 /100（达到提醒线的 ×1.5）
    → 按影响大小排、第 k 条 ×0.5^k 加总（同一件事的多条报道不重复放大）：≥ 1.0 大、≥ 0.4 中、≥ 0.1 小（更小的不标）。只是展示用的粗估（敏感度来自 TOPIX-17 行业 ETF 的周敏感度），不参与交易。
    核心 ETF（不在东证业种里）：直接用它自己的因子敏感度（asset_betas）× 这条消息的因子冲击。
    每条附影响期（timing：开始 / 结束 / 持续几天，经验估计）；已经过了影响期的不算。
    → {代码: {"net", "level", "dir": "down" | "up", "sector", "start", "end", "items": [{id, time, title, labels, eff, alert, cred, sector, timing}]}}"""
    sectors = sectors if sectors is not None else holdings_map(tickers)
    assets = assets if assets is not None else asset_betas()
    out: dict[str, dict] = {}
    for t in tickers:
        sec = sectors.get(t)
        ab = assets.get(t) if not sec else None
        if not sec and not ab:
            continue
        if not sec:
            from .names import label                    # 「1545 纳斯达克 100」（2026-10-15 统一成「代码 名字」，不再「名字（代码）」）
            sec = label(t)
        items = []
        for e in events or []:
            c = e.get("chain") or {}
            if ab:
                sh = c.get("shocks") or {}
                v = round(sum(float(ab[f]) * float(x) for f, x in sh.items() if ab.get(f) is not None), 2) if sh else None
            else:
                imp = {s: float(v) for s, v in (c.get("impacts") or (list(c.get("up") or []) + list(c.get("down") or [])))}
                v = imp.get(sec)
                if v is None:
                    d = (c.get("rules") or {}).get(sec)
                    v = RULE_PCT * (1 if d > 0 else -1) if d else None
            if v is None:
                continue
            tm = timing(e, now)
            if tm and tm["state"] == "已过":
                continue
            eff = v * float(e.get("cred") or 50) / 100 * (1.5 if e.get("alert") else 1.0)
            if abs(eff) < 0.05:
                continue
            items.append({"id": e.get("id"), "time": e.get("time"), "title": e.get("title"), "title_zh": e.get("title_zh"),
                          "labels": e.get("event_labels") or [],
                          "eff": round(eff, 2), "alert": bool(e.get("alert")), "cred": e.get("cred"), "sector": sec, "timing": tm})
        if not items:
            continue
        items.sort(key=lambda i: -abs(i["eff"]))
        net = round(sum(i["eff"] * 0.5 ** k for k, i in enumerate(items)), 2)   # 同一件事常有好几条报道：最大的一条为主、其余递减（不简单相加）
        lv = next((lab for th, lab in LEVELS if abs(net) >= th), None)
        if lv is None:
            continue
        tms = [i["timing"] for i in items if i.get("timing")]
        out[t] = {"net": net, "level": lv, "dir": "down" if net < 0 else "up", "sector": sec, "items": items,
                  "start": min((x["start"] for x in tms), default=None), "end": max((x["end"] for x in tms), default=None),
                  "main": items[0].get("timing")}                                # 影响最大的那条的影响期
    return out


# ── 存取与提醒 ──
def cache_dir():
    return paths.sub("cache/news")


def save(events: list[dict], stat: dict, generated: str) -> None:
    write_json(cache_dir() / "news.json", {"generated": generated, "sources": stat, "events": events})


def load() -> dict:
    """数据目录 cache/news/news.json；不显示的事件（MUTED_EVENTS，2026-10-29 起的自然灾害）在这里去掉 —— 以前存下来的也不再显示。"""
    d = read_json(cache_dir() / "news.json", {}) or {}
    if isinstance(d.get("events"), list):
        d["events"] = [e for e in d["events"] if not muted(e)]
    return d


def muted(e: dict) -> bool:
    """这条事件只属于不显示的类别（2026-10-29 用户：地震之类的消息不要推送 / 放到消息里）。"""
    evs = [str(x) for x in (e or {}).get("events") or []]
    return bool(evs) and all(x in MUTED_EVENTS for x in evs)


def clean_notice(h: dict) -> dict | None:
    """以前推出去的经济威胁通知：去掉属于不显示类别的那几条（「｜自然灾害｜」那一行与它下面的「（原文：…）」）；
    全是这种 → None（通知记录里不再列）；别的通知原样返回。"""
    if not str((h or {}).get("subject") or "").startswith("经济威胁"):
        return h
    labels = {EVENTS[k][0] for k in MUTED_EVENTS if k in EVENTS}
    out, drop, removed = [], False, False
    for ln in str(h.get("text") or "").split("\n"):
        if "｜" in ln:
            drop = any(lb in ln.split("｜") for lb in labels)
            removed |= drop
        if not drop:
            out.append(ln)
    if not removed:
        return h
    if not any("｜" in ln for ln in out):
        return None
    return {**h, "text": "\n".join(out)}


# ── 同一件事只推第一次（2026-10-17 用户：「消息里面的重复的消息不要一直推送 只推送出现的第一次」）──
# 以前只按这一组标题的 id（最新那条标题的哈希）判断：同一件事换一家媒体 / 换个说法（「特朗普暂停对俄制裁」一中午 5 种标题）、
# 标题后面多了媒体名（「…（テレビ岩手ニュース）」）、组里来了更新的标题 → id 变了，又推一次。现在另记「推过的事」（标题们 + 事件类别），
# 新的提醒和第一次推出去之后 STORY_H 小时内、推出去的那条（标题 + 中文译文 + 同组的其他标题）是同一件事 → 不推
# （只和推出去的比、不和压下的比：不然一件事越滚越大，几天里所有「制裁」都成了一件事 —— 用过去一周的推送重放过）。同一件事 =
#   日文 / 中文：去掉末尾媒体名后 2-gram 相似度 ≥ SIM_MIN，或事件类别有重合且 ≥ STORY_SIM；
#   英文：相似度 ≥ EN_SIM，或事件类别有重合且共有 ≥ STORY_WORDS 个实词（不算停用词与类别词 sanctions / oil / rate…；占少的那边 ≥ 40%）。
# 严重度比那件事推过的高（升级，例：震度 5 强 → 6 强）→ 照推。只影响推送 / Mac 通知，面板「消息」照旧每条都列。
STORY_H = 48
STORY_SIM = 0.25
EN_SIM = 0.5
STORY_WORDS = 3
_TAIL = re.compile(r"(\s*[（(][^（）()]{1,40}[）)]|\s+[-–—|｜]\s+[^-–—|｜]{1,40})\s*$")   # 「…（媒体名）」「… - Reuters」
_STOP = frozenset("""the and for with from that this after before over into onto says said say new will could would should has have had are was
were its his her they their them amid than more most since about what why how who may might can not but out off all been being also just
still says while near upon under amid against amidst stock stocks share shares market markets price prices index report week year years day
days percent""".split())
_KINDW = frozenset("""sanc tari oil pric rate rate hike infl fed cut cuts plun tumb fall rise rose surg jump drop sink sank slid slip decl rout
sell yiel trea cpi earn crud bren gold yen dollar doll bond bank fear odds lead lowe high war atta stri bomb miss quak eart tsun
recess rece slum cras""".split())   # 事件类别本身的词（类别重合时它们本来就一样）：不算「共有的实词」


def _bare(t: str) -> str:
    t = str(t or "")
    for _ in range(2):
        t = _TAIL.sub("", t)
    return t


def _words(t: str) -> set[str]:
    ws = re.findall(r"[a-z][a-z']+", unicodedata.normalize("NFKC", str(t or "")).lower())
    return {w[:4] for w in ws if len(w) >= 3 and w not in _STOP and w[:4] not in _KINDW}


def _cjk(t: str) -> bool:
    n = sum(1 for c in t if "\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff")
    return n >= max(4, len(t) * 0.3)


def _titles(e: dict) -> list[str]:
    ts = [e.get("title"), e.get("title_zh")] + [z.get("title") for z in e.get("others") or [] if isinstance(z, dict)]
    return [_bare(t) for t in ts if t and _bare(t)]


def same_story(e: dict, story: dict) -> bool:
    """这条提醒和推过的那件事（{"titles", "events"}）是不是同一件事（规则见上面）。"""
    kin = bool(set(e.get("events") or ()) & set(story.get("events") or ()))
    for a in _titles(e):
        wa, ca = _words(a), _cjk(a)
        for b in story.get("titles") or ():
            if ca != _cjk(b):                                # 中文译文 vs 英文原文：没法比
                continue
            sim = similar(a, b)
            if ca:                                           # 日文 / 中文：字符 2-gram 本来就像词，类别重合时放宽一点
                if sim >= SIM_MIN or (kin and sim >= STORY_SIM):
                    return True
                continue
            if sim >= EN_SIM:                                # 英文：不相干的标题字符相似度也常有 0.3〜0.4 → 要更像，或看共有的实词
                return True
            wb = _words(b)
            both = wa & wb
            if kin and len(both) >= STORY_WORDS and len(both) >= 0.4 * min(len(wa), len(wb)):
                return True
    return False


def _age_h(v, now: dt.datetime) -> float:
    try:
        return (now - dt.datetime.fromisoformat(str(v))).total_seconds() / 3600
    except (TypeError, ValueError):
        return float("inf")


def new_alerts(events: list[dict], state_path=None, keep_h: float = 7 * 24, now: dt.datetime | None = None) -> list[dict]:
    """还没提醒过的提醒事件（同一件事只提醒一次：id 记录保留 7 天；换了媒体 / 说法的同一件事第一次推之后 STORY_H 小时内不再推，严重度升级才再推）。
    记录 var/cache/news/alerted.json（不入库）：{"v": 2, "ids": {id: 时刻}, "stories": [{"at", "last", "n", "titles", "events", "sev"}]}；
    旧格式（{id: 时刻}）照读。"""
    now = now or now_jst()
    fp = state_path or (cache_dir() / "alerted.json")
    raw = read_json(fp, {}) or {}
    old_ids = raw.get("ids") if raw.get("v") == 2 else raw
    ids = {k: v for k, v in (old_ids or {}).items() if isinstance(v, str) and _age_h(v, now) < keep_h}
    stories = [s for s in (raw.get("stories") or [] if raw.get("v") == 2 else []) if isinstance(s, dict)
               and _age_h(s.get("at"), now) < STORY_H]
    stamp = now.isoformat(timespec="minutes")
    if raw.get("v") != 2:                                     # 旧格式（只有 id）：这次列表里已经推过的，记成推过的事（换代码后正在发酵的事不再推一次）
        stories = [{"at": ids[e["id"]], "last": ids[e["id"]], "n": 1, "titles": _titles(e)[:30], "events": list(e.get("events") or ()),
                    "sev": int(e.get("severity") or 0)} for e in events if e.get("id") in ids and _age_h(ids[e["id"]], now) < STORY_H]
    out = []
    for e in events:
        if not pushable(e) or e["id"] in ids:
            continue
        ids[e["id"]] = stamp
        sev = int(e.get("severity") or 0)
        hit = next((s for s in stories if same_story(e, s)), None)
        if hit is None:
            stories.append({"at": stamp, "last": stamp, "n": 1, "titles": _titles(e)[:30], "events": list(e.get("events") or ()), "sev": sev})
            out.append(e)
            continue
        hit["last"], hit["n"] = stamp, int(hit.get("n") or 1) + 1   # 同一件事：不推（只数一下）
        if sev > int(hit.get("sev") or 0):                   # 升级（严重度变高）：照推，这条的标题也算推出去的
            hit["sev"] = sev
            hit["titles"] = list(dict.fromkeys((hit.get("titles") or []) + _titles(e)))[:30]
            out.append(e)
    write_json(fp, {"v": 2, "ids": ids, "stories": stories})
    return out


def alert_text(e: dict) -> str:
    c = e["chain"]
    parts = [f"{'、'.join(e['event_labels'])}｜威胁度 {level(e)}｜可信度 {e['cred']}"]   # 不写「可信度（中）」：会被当成威胁度
    if c.get("shock_txt"):
        parts.append(f"冲击：{c['shock_txt']}")
    if c.get("down"):
        parts.append("受损：" + "、".join(f"{s} {v:+.1f}%" for s, v in c["down"]))
    if c.get("rules"):
        parts.append("经验规则：" + "、".join(f"{s}{'↑' if d > 0 else '↓'}" for s, d in c["rules"].items()))
    if c.get("tickers_down"):                      # 2026-10-15 用户：只写代码不知道是哪只 → 代码 + 简称、最多 4 只（推送 / Mac 通知有长度上限）
        from .names import labels
        parts.append("受损方向的持仓 / 候补：" + labels([str(t) for t in c["tickers_down"]], limit=4, short=True))
    return "；".join(parts)


def notify_lines(events: list[dict], n: int = 5) -> str:
    """推送 / 通知记录的正文：每条「时刻 JST 中文标题｜类别、冲击、受损…」+ 下一行原文（有中文译文时）。
    2026-10-11 用户「通知里面的新闻都要翻译为中文后进行通知」；翻不了 → 原文（照发）。"""
    out = []
    for e in events[:n]:
        zh, raw = e.get("title_zh"), str(e.get("title") or "")
        head = f"{str(e.get('time') or '')[11:16]} JST {zh or raw}｜{alert_text(e)}"
        from .translate import is_english                      # 只翻英文：日文标题保持原文、不加提示（2026-10-11）
        note = "" if zh or not is_english(raw) else "\n（英文标题还没翻译成中文：上面是原文）"
        out.append(head + (f"\n（原文：{raw}）" if zh and zh.strip() != raw.strip() else note))
    return "\n".join(out)


def notify_mac(title: str, text: str) -> bool:
    """macOS 通知中心（只在 Mac 上；失败不影响任何东西）。
    代码后面补简称再截断（2026-10-15 用户：只写代码不知道是哪只；notify.compact，失败照原文）。"""
    import subprocess
    import sys
    if sys.platform != "darwin":
        return False
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')                 # noqa: E731
    try:
        from .notify import compact
        title, text = compact(title), compact(text)
    except Exception:                                                        # noqa: BLE001
        pass
    try:
        subprocess.run(["osascript", "-e", f'display notification "{esc(text[:220])}" with title "{esc(title[:60])}"'],
                       check=False, timeout=10, capture_output=True)
        return True
    except Exception:                                                        # noqa: BLE001
        return False
