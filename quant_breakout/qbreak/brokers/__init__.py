from .base import BaseBroker, BrokerError, Order, Position
from .paper import PaperBroker

__all__ = ["BaseBroker", "BrokerError", "Order", "Position", "PaperBroker"]


def make_broker(kind: str, **kw) -> BaseBroker:
    """kind: paper | rss"""
    if kind == "paper":
        return PaperBroker(**kw)
    if kind == "rss":
        from .rakuten_rss import RakutenRSSBroker   # 仅 Windows 需要 xlwings，延迟导入
        return RakutenRSSBroker(**kw)
    raise ValueError(f"未知券商类型: {kind}")
