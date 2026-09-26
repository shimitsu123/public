from .base import BaseBroker, BrokerError, Order, Position
from .paper import PaperBroker

__all__ = ["BaseBroker", "BrokerError", "Order", "Position", "PaperBroker", "make_broker"]


def make_broker(kind: str, **kw) -> BaseBroker:
    """kind: paper（模拟）| tachibana（立花 e支店 API，Mac/Linux）| rss（楽天，Windows+Excel）"""
    if kind == "paper":
        return PaperBroker(**kw)
    if kind == "manual":
        from .manual import ManualBroker              # 半自动：只算不发单，持仓手工登记
        return ManualBroker(**kw)
    if kind == "tachibana":
        from .tachibana import TachibanaBroker          # 延迟导入：只在需要时读凭证
        return TachibanaBroker(**kw)
    if kind == "rss":
        from .rakuten_rss import RakutenRSSBroker       # 仅 Windows 需要 xlwings
        return RakutenRSSBroker(**kw)
    raise ValueError(f"未知券商类型: {kind}（可选 paper / manual / tachibana / rss）")
