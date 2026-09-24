"""universes.py — 广域股票池（ユニバース）。成分为 2026-09-24 时点（日経225 / NASDAQ-100 取自 Wikipedia）；
之后的指数入替写在 var/index_changes.json，生效日起自动增删（见 index_changes()）。

原版 20 只太少（每年信号个位数，统计意义弱）。这里给出：
  • NIKKEI225 : 日経平均構成銘柄（**基于公开信息整理的静态名单，成分会调整**；
                代码错误/退市的只会在取数时被跳过，不会造成误交易）
  • US_BROAD  : NASDAQ-100 + Dow 30，并按用户偏好剔除
                航空/运输、百货、服装、食品饮料餐饮、中国背景公司
名单可用 `python run.py universe-update` 在有外网的机器上刷新（写入 var/universe_*.json，优先级高于本文件）。
"""
from __future__ import annotations

import json

from . import paths

NIKKEI225 = [
    # 医薬品
    "4151", "4502", "4503", "4506", "4507", "4519", "4523", "4568", "4578",
    # 電気機器
    "6479", "6501", "6503", "6504", "6506", "6526", "6594", "6645", "6702", "6723",
    "6724", "6752", "6753", "6758", "6762", "6770", "6841", "6857", "6861", "6902", "6920",
    "6954", "6963", "6971", "6976", "6981", "7735", "7751", "7752", "7832", "8035",
    "6146",
    # 自動車
    "7201", "7202", "7203", "7211", "7261", "7267", "7269", "7270", "7272",
    # 精密機器
    "4543", "4902", "7731", "7733", "7741", # 通信
    "9432", "9433", "9434", "9984",
    # 銀行・金融
    "5831", "7186", "8304", "8306", "8308", "8309", "8316", "8331", "8354", "8411",
    "8253", "8591", "8697", "8601", "8604", "8630", "8725", "8750", "8766", "8795",
    # 水産・食品
    "1332", "2002", "2269", "2282", "2501", "2502", "2503", "2801", "2802", "2871", "2914",
    # 小売
    "3086", "3092", "3099", "3382", "7453", "8233", "8252", "8267", "9843", "9983",
    # サービス
    "2413", "2432", "3659", "4324", "4385", "4661", "4689", "4704", "4751", "4755", "6098",
    "6178", "6532", "7974", "9602", "9735", "9766",
    # 鉱業・繊維・パルプ・化学
    "1605", "3401", "3402", "3861", "3405", "3407", "4004", "4005", "4021", "4042", "4043",
    "4061", "4063", "4183", "4188", "4208", "4452", "4901", "4911", "6988",
    # 石油・ゴム・ガラス土石・鉄鋼・非鉄
    "5019", "5020", "5101", "5108", "5201", "5214", "5233", "5301", "5332", "5333",
    "5401", "5406", "5411", "3436", "5706", "5711", "5713", "5714", "5801", "5802", "5803",
    # 商社
    "2768", "8001", "8002", "8015", "8031", "8053", "8058",
    # 建設・機械・造船・その他製品
    "1721", "1801", "1802", "1803", "1808", "1812", "1925", "1928", "1963",
    "5631", "6103", "6113", "6273", "6301", "6302", "6305", "6326", "6361", "6367",
    "6471", "6472", "6473", "7011", "7012", "7013", "7911", "7912", "7951",
    # 不動産・陸運・海運・空運・倉庫・電力ガス
    "3289", "8801", "8802", "8804", "8830",
    "9001", "9005", "9007", "9008", "9009", "9020", "9021", "9022", "9064", "9147",
    "9101", "9104", "9107", "9201", "9202", "9501", "9502", "9503", "9531", "9532",
    # 2025–2026 新成分（Wikipedia 2026-09-24 时点；285A キオクシア、543A ARCHION 等）
    "285A", "3697", "4307", "543A", "6701", "7004", "7532",
]

# NASDAQ-100 + Dow 30（按用户偏好剔除后）。剔除项见 US_EXCLUDED，方便复查。
US_BROAD = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO", "TSLA", "COST", "NFLX",
    "AMD", "ADBE", "LIN", "CSCO", "TMUS", "QCOM", "INTU", "AMAT", "TXN", "ISRG", "CMCSA",
    "AMGN", "HON", "BKNG", "PANW", "VRTX", "ADP", "GILD", "ADI", "MU", "LRCX", "MELI",
    "INTC", "KLAC", "REGN", "CTAS", "PYPL", "SNPS", "CDNS", "MAR", "CRWD", "ORLY", "CEG",
    "FTNT", "ABNB", "DASH", "ROP", "MRVL", "ADSK", "NXPI", "PCAR", "WDAY", "CPRT", "AEP",
    "PAYX", "FAST", "GEHC", "EXC", "DDOG", "XEL", "BKR",
    "IDXX", "FANG", "TTWO", "DXCM", "WBD", "MCHP", "AXON", "PLTR", "APP", "MSTR", "ARM", "ASML", "SBUX",
    # 2025–2026 新进 NASDAQ-100（Yahoo 代码已核实）
    "ALNY", "ALAB", "CRWV", "HONA", "LITE", "MPWR", "NBIS", "RKLB", "SNDK", "SPCX", "STX",
    "SHOP", "TER", "TRI", "WDC",
    # Dow 30 中不在上面的
    "AXP", "BA", "CAT", "CRM", "CVX", "DIS", "GS", "HD", "IBM", "JNJ", "JPM", "MMM", "MRK",
    "PG", "SHW", "TRV", "UNH", "V", "VZ",
]
US_EXCLUDED = {
    "航空/运输": ["CSX", "ODFL", "UPS", "FER"],   # FER = 收费公路 / 机场运营
    "百货/零售": ["WMT"],
    "服装": ["NKE", "LULU", "ROST"],
    "食品饮料餐饮": ["PEP", "MDLZ", "KDP", "KHC", "MNST", "CCEP", "KO", "MCD"],
    "中国背景": ["PDD", "BIDU", "NTES", "JD"],
}


JP_EXCLUDED = {
    "航空": ["9201", "9202"],
    "陆运/物流": ["9001", "9005", "9007", "9008", "9009", "9020", "9021", "9022", "9064", "9147", "9301"],
    # 海運（9101 / 9104 / 9107）保留：它是油价与运价的受益组，用户在板块倾斜里单列
}
_JP_EXCLUDED_SET = {c for v in JP_EXCLUDED.values() for c in v}


def index_changes(market: str) -> list[dict]:
    """var/index_changes.json：[{announced, effective, add:[...], delete:[...], source}]（代码不带 .T）。"""
    d = _read_changes()
    return [c for c in d.get(market.upper(), []) if c.get("effective")]


def _read_changes() -> dict:
    fp = paths.home() / "index_changes.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8")) or {}
    except Exception:          # noqa: BLE001
        return {}


def _apply_changes(codes: list[str], market: str, today) -> list[str]:
    """生效日（含）之后：加入 add、去掉 delete。today=None 表示今天。"""
    import datetime as _dt
    d = (today or _dt.date.today()).isoformat()
    base = [c.split(".")[0] if market == "JP" else c for c in codes]
    out = list(dict.fromkeys(base))
    for ch in sorted(index_changes(market), key=lambda c: c["effective"]):
        if ch["effective"] <= d:
            out = [c for c in out if c not in set(ch.get("delete", []))]
            out += [c for c in ch.get("add", []) if c not in out]
    return out


def index_pending(market: str, today=None) -> dict[str, dict]:
    """已公布、未生效的入替：{代码: {"action": "add"/"delete", "effective": ..., "announced": ...}}。
    规则：待剔除 → 公布日起不开新仓（指数基金在生效前一天大引け集中卖出）；
         待纳入 → 生效日才进股票池（纳入需求造成的上涨多在公布后很快结束，之后常回吐）。"""
    import datetime as _dt
    d = (today or _dt.date.today()).isoformat()
    out: dict[str, dict] = {}
    for ch in index_changes(market):
        if ch.get("announced", "") <= d < ch["effective"]:
            for c in ch.get("delete", []):
                out[c] = {"action": "delete", "effective": ch["effective"], "announced": ch.get("announced", "")}
            for c in ch.get("add", []):
                out[c] = {"action": "add", "effective": ch["effective"], "announced": ch.get("announced", "")}
    return out


def nikkei225(exclude: bool = True, today=None) -> list[str]:
    ov = _override("JP")
    codes = _apply_changes(ov or NIKKEI225, "JP", today)
    codes = [c for c in codes if not (exclude and c.split(".")[0] in _JP_EXCLUDED_SET)]
    return [c if c.endswith(".T") else f"{c}.T" for c in codes]


def us_broad(today=None) -> list[str]:
    excl = {t for v in US_EXCLUDED.values() for t in v}
    return [t for t in _apply_changes(_override("US") or list(US_BROAD), "US", today) if t not in excl]


def _override(market: str) -> list[str] | None:
    fp = paths.home() / f"universe_{market}.json"
    if fp.exists():
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(d, list) and d:
                return [str(x) for x in d]
        except Exception:      # noqa: BLE001
            return None
    return None
