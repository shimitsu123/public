"""sectors.py — 股票池的行业标签（板块倾斜用）。

粗分组，只到「宏观因子能区分方向」的粒度：
  energy / trading(商社) / shipping(海運) / airline / land_transport / utility / chemical / paper /
  steel_metal / bank / insurance / finance / realestate / semis / software_internet / hardware /
  auto / precision / machinery / construction / telecom / pharma / food / retail / consumer / other
HIGH_GROWTH = semis ∪ software_internet：10Y > 5% 时减半的「高估值成长」近似（未用估值数据，见 README）。
"""
from __future__ import annotations

# 日経225（代码不带 .T）
SECTOR_JP: dict[str, str] = {}


def _jp(group: str, codes: str) -> None:
    for c in codes.split():
        SECTOR_JP[c] = group


_jp("energy", "1605 5019 5020")
_jp("trading", "2768 8001 8002 8015 8031 8053 8058")
_jp("shipping", "9101 9104 9107")
_jp("airline", "9201 9202")
_jp("land_transport", "9001 9005 9007 9008 9009 9020 9021 9022 9064 9147 9301")
_jp("utility", "9501 9502 9503 9531 9532")
_jp("chemical", "3401 3402 3405 3407 4004 4005 4021 4042 4043 4061 4063 4183 4188 4208 5101 5108 5201 5214 5233 5301 5332 5333 6988")
_jp("paper", "3861")
_jp("steel_metal", "5401 5406 5411 5706 5711 5713 5714 5801 5802 5803")
_jp("bank", "5831 7186 8304 8306 8308 8309 8316 8331 8354 8411")
_jp("insurance", "8630 8725 8750 8766 8795")
_jp("finance", "8253 8591 8697 8601 8604 6178")
_jp("realestate", "3289 8801 8802 8804 8830")
_jp("semis", "6146 6857 8035 6723 6920 6963 6526 3436 4062 7735 6762 6981")
_jp("software_internet", "9984 4385 4689 4755 4751 3659 4704 6098 2413 4324 9613 2432 6532 7974 9766 4661 9602 9735")
_jp("hardware", "6479 6501 6503 6504 6506 6594 6645 6674 6702 6724 6752 6753 6758 6770 6841 6861 6902 6952 6971 6976 7751 7752 7832 4901")
_jp("auto", "7201 7202 7203 7205 7211 7261 7267 7269 7270 7272")
_jp("precision", "4543 4902 7731 7733 7741 7762")
_jp("machinery", "5631 6103 6113 6273 6301 6302 6305 6326 6361 6367 6471 6472 6473 7011 7012 7013 6954")
_jp("construction", "1721 1801 1802 1803 1808 1812 1925 1928 1963 7911 7912 7951")
_jp("telecom", "9432 9433 9434")
_jp("pharma", "4151 4502 4503 4506 4507 4519 4523 4568 4578")
_jp("food", "1332 2002 2269 2282 2501 2502 2503 2801 2802 2871 2914")
_jp("retail", "3086 3092 3099 3382 7453 8233 8252 8267 9843 9983")
_jp("consumer", "4452 4911")

SECTOR_US: dict[str, str] = {}


def _us(group: str, tickers: str) -> None:
    for t in tickers.split():
        SECTOR_US[t] = group


_us("energy", "CVX BKR FANG")
_us("semis", "NVDA AVGO AMD QCOM AMAT TXN ADI MU LRCX INTC KLAC MRVL NXPI MCHP ON GFS ARM ASML SNPS CDNS")
_us("software_internet", "MSFT META GOOGL GOOG NFLX ADBE INTU PANW CRWD FTNT ADSK WDAY DDOG ZS MDB TEAM PLTR APP TTD CRM IBM CTSH EA TTWO ABNB DASH BKNG MELI PYPL MSTR CSGP VRSK ROP CDW AXON")
_us("hardware", "AAPL CSCO")
_us("consumer", "AMZN TSLA COST HD SBUX ORLY MAR DIS WBD PG")
_us("telecom", "CMCSA CHTR TMUS VZ")
_us("pharma", "AMGN ISRG VRTX GILD REGN IDXX BIIB DXCM GEHC JNJ MRK UNH")
_us("machinery", "HON CTAS PCAR FAST CPRT PAYX ADP BA CAT MMM")
_us("chemical", "LIN SHW")
_us("utility", "CEG AEP EXC XEL")
_us("finance", "AXP GS JPM V TRV")

HIGH_GROWTH = {"semis", "software_internet"}
OIL_WINNERS = {"energy", "trading", "shipping"}
OIL_LOSERS = {"airline": 0.0, "land_transport": 0.5, "chemical": 0.5, "paper": 0.5, "utility": 0.5,
              "food": 0.75, "retail": 0.75, "consumer": 0.75}      # 内需 = 食品/零售/消费

SECTOR_CN = {
    "energy": "能源", "trading": "商社", "shipping": "海运", "airline": "航空", "land_transport": "陆运",
    "utility": "电力燃气", "chemical": "化学", "paper": "纸浆", "steel_metal": "钢铁金属", "bank": "银行",
    "insurance": "保险", "finance": "金融", "realestate": "不动产", "semis": "半导体", "software_internet": "软件互联网",
    "hardware": "电机硬件", "auto": "汽车", "precision": "精密", "machinery": "机械工业", "construction": "建设",
    "telecom": "通信", "pharma": "医药", "food": "食品", "retail": "零售", "consumer": "消费", "other": "其他",
}


def sector_of(ticker: str, market: str) -> str:
    if market.upper() == "JP":
        return SECTOR_JP.get(ticker.split(".")[0], "other")
    return SECTOR_US.get(ticker.upper(), "other")


def sector_cn(ticker: str, market: str) -> str:
    return SECTOR_CN.get(sector_of(ticker, market), "其他")
