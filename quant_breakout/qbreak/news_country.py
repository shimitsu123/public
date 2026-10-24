"""news_country.py — 经济威胁消息的来源只写国家（2026-10-19 用户：「消息里面的消息要显示来源于哪国只写国家就行」）。只展示。

country(出版方, 网址) → 「日本」「美国」… / 「不明」。顺序：
  ① 已知媒体 / 机构表（名字或网址里的关键词；以总部 / 发行地算：Reuters = 英国、Bloomberg = 美国）；
  ② 美国电视台 / 电台呼号（KIRO、WLOX …）；
  ③ 名字里有假名 / 汉字 → 日本（日文版 Google ニュース与日本的媒体；中文 / 韩文媒体的日文版在 ① 里先认）；
  ④ 网址的国家域名（.jp / .uk / .ca …）；
  都认不出 → 不明（X、TradingView 一类平台的内容来自哪国看不出，也写不明）。
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

UNKNOWN = "不明"

_T = [  # (正则, 国家)：越具体的放越前
    (r"yahoo!|ヤフー", "日本"),
    (r"yahoo (finance|news)|finance\.yahoo\.com", "美国"),
    (r"abc news \(au|australian broadcasting|abc\.net\.au", "澳大利亚"),
    (r"nikkei asia|日本経済新聞|日経|nikkei|nhk|共同通信|kyodo|時事|jiji|朝日新聞|asahi|読売|yomiuri|毎日新聞|mainichi|産経|sankei|"
     r"東京新聞|テレ東|テレビ東京|\btbs\b|日テレ|\bfnn\b|japan times|東洋経済|ダイヤモンド|itmedia|president (online|\.jp)|みんかぶ|株探|ZUU|"
     r"日本銀行|日銀|bank of japan|財務省|金融庁|内閣府|気象庁|経済産業省|外為どっとコム|マネクリ|モーニングスター", "日本"),
    (r"聯合|聨合|yonhap|中央日報|joongang|朝鮮日報|chosun|ハンギョレ|hankyoreh|korea herald|korea times|theinvestor|the investor|"
     r"東亜日報|donga|kbs world|arirang", "韩国"),
    (r"新華|xinhua|人民網|人民日报|people'?s daily|global times|cgtn|china daily|中国網|\bcri\b|caixin|財新|south china morning post|scmp",
     "中国"),
    (r"focus taiwan|taipei times|中央社", "台湾"),
    (r"reuters|ロイター|\bbbc\b|financial times|\bft\.com|guardian|the economist|telegraph|sky news|city a\.?m|"
     r"\bitv\b|evening standard|this is money|daily mail", "英国"),
    (r"\bafp\b|afpbb|france ?24|le monde|les echos|\brfi\b|euronews", "法国"),
    (r"deutsche welle|\bdw\b|handelsblatt|spiegel|frankfurter|\bfaz\b", "德国"),
    (r"toronto star|globe and mail|national post|\bcbc\b|\bctv\b|financial post|energynow|global news|bnn bloomberg", "加拿大"),
    (r"bloomberg|ブルームバーグ|wall street journal|\bwsj\b|new york times|\bnyt\b|\bcnn\b|cnbc|associated press|\bap news\b|^ap$|"
     r"abc news|cbs news|nbc news|\bfox (news|business)\b|usa today|washington post|forbes|marketwatch|barron|axios|politico|"
     r"\bnpr\b|public radio|business insider|fortune|the hill|newsweek|\bvox\b|time\.com|^time$|seeking alpha|kiplinger|"
     r"thestreet|investopedia|benzinga|zacks|motley fool|counterpunch|southern farm network|acg aaa|\baaa\b|notus|yoursun|"
     r"federal reserve|\bfrb\b|\bfomc\b|white house|treasury\.gov|los angeles times|chicago tribune|boston globe|"
     r"miami herald|houston chronicle|oilprice|rigzone|\bcbs\b|\bnbc\b|\bpbs\b|voice of america|\bvoa\b|radio free", "美国"),
    (r"sydney morning herald|the australian|\bafr\b|news\.com\.au|sbs news", "澳大利亚"),
    (r"times of india|ndtv|hindustan times|economic times|the hindu|livemint|\bmint\b|business standard|india today|"
     r"moneycontrol|firstpost|deccan|news18", "印度"),
    (r"the news international|^dawn\b|dawn\.com|express tribune|geo news", "巴基斯坦"),
    (r"al jazeera|アルジャジーラ", "卡塔尔"),
    (r"arab news|saudi gazette|al arabiya", "沙特阿拉伯"),
    (r"gulf news|khaleej|agbi|arabian gulf business|zawya", "阿联酋"),
    (r"times of israel|haaretz|jerusalem post|ynet", "以色列"),
    (r"anadolu|daily sabah|hurriyet", "土耳其"),
    (r"ukrinform|ウクルインフォルム|kyiv independent|kyiv post|ukrainska", "乌克兰"),
    (r"\btass\b|タス通信|sputnik|スプートニク|\brt\b|ria novosti|moscow times|interfax", "俄罗斯"),
    (r"vov world|\bvov\b|vietnam news|vnexpress|tuoi tre", "越南"),
    (r"straits times|channel ?news ?asia|\bcna\b|business times singapore", "新加坡"),
    (r"bangkok post|the nation thailand", "泰国"),
    (r"inquirer\.net|philippine daily inquirer|philstar|rappler", "菲律宾"),
    (r"jakarta post|antara|tempo\.co", "印度尼西亚"),
    (r"the star malaysia|malay mail|new straits times|bernama", "马来西亚"),
    (r"8am media|hasht-?e subh|tolo ?news|pajhwok", "阿富汗"),
    (r"fxstreet|el pa[ií]s|expansi[oó]n", "西班牙"),
    (r"swissinfo|neue z[uü]rcher|\bnzz\b", "瑞士"),
    (r"\bansa\b|il sole 24|corriere", "意大利"),
]
_TABLE = [(re.compile(p, re.I), c) for p, c in _T]
_CALL = re.compile(r"^[KW][A-Z]{2,3}(\b|-|\d)")                    # 美国电视台 / 电台呼号（KIRO 7、WLOX、KTVN …）
_JA = re.compile(r"[぀-ヿ㐀-鿿]")
_TLD = {"jp": "日本", "uk": "英国", "ca": "加拿大", "au": "澳大利亚", "in": "印度", "de": "德国", "fr": "法国", "kr": "韩国",
        "cn": "中国", "hk": "中国", "tw": "台湾", "sg": "新加坡", "vn": "越南", "ua": "乌克兰", "ru": "俄罗斯", "it": "意大利",
        "es": "西班牙", "ch": "瑞士", "nl": "荷兰", "be": "比利时", "se": "瑞典", "no": "挪威", "dk": "丹麦", "fi": "芬兰",
        "ie": "爱尔兰", "nz": "新西兰", "za": "南非", "br": "巴西", "mx": "墨西哥", "ar": "阿根廷", "tr": "土耳其", "il": "以色列",
        "sa": "沙特阿拉伯", "ae": "阿联酋", "qa": "卡塔尔", "pk": "巴基斯坦", "th": "泰国", "my": "马来西亚", "id": "印度尼西亚",
        "ph": "菲律宾", "pl": "波兰", "at": "奥地利", "gr": "希腊", "pt": "葡萄牙", "eg": "埃及", "ng": "尼日利亚", "ke": "肯尼亚",
        "gov": "美国", "mil": "美国", "us": "美国"}


def _host(url: str | None) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def country(publisher: str | None, url: str | None = None) -> str:
    """出版方（与它的网址，可没有）→ 国家；认不出 → 「不明」。"""
    name, host = str(publisher or "").strip(), _host(url)
    for s in (name, host):
        if s:
            for rx, c in _TABLE:
                if rx.search(s):
                    return c
    if _CALL.match(name):
        return "美国"
    if _JA.search(name):
        return "日本"
    if host:
        return _TLD.get(host.rsplit(".", 1)[-1], UNKNOWN)
    return UNKNOWN


def of_event(e: dict) -> str:
    """一条消息（news.analyze 的事件）的来源国家：新的事件里有 country；旧缓存没有 → 按出版方现算。"""
    return str(e.get("country") or country(e.get("publisher")))


def countries(e: dict) -> list[str]:
    """这条消息的各个来源（头一条 + 相似的几条）的国家，去重、按出现顺序。"""
    out: list[str] = []
    for z in [e] + [o for o in (e.get("others") or []) if isinstance(o, dict)]:
        c = of_event(z)
        if c not in out:
            out.append(c)
    return out


__all__ = ["country", "of_event", "countries", "UNKNOWN"]
