"""qbreak — 横盘突破（レンジブレイクアウト / range breakout）日线量化交易框架。

设计原则
  1. 回测与实盘共用同一套信号函数与出场规则，避免"回测赢、实盘输"。
  2. 任何可能造成前视偏差（先読みバイアス / look-ahead bias）的写法都在引擎层被结构性禁止。
  3. 真实下单路径上的每一步都可被单元测试覆盖（Excel/RSS 被抽象成可替换的 Bridge）。
"""
__version__ = "2.0.0"


def _pin_jst() -> None:
    """日期与时刻一律按日本时间（JST）——放在包的入口：run.py 以外的入口（python -m qbreak.mac_status / mac_login、scripts/*.py、
    操作面板、测试）也一样。云端容器是 UTC：不固定的话 date.today() / datetime.now() 会差 9 小时（显示的时刻、日期、前向记录的日子都会错）。
    QBREAK_KEEP_TZ=1 时不动（只给要验证「在别的时区也对」的测试用）。"""
    import os
    import time
    if os.environ.get("QBREAK_KEEP_TZ") == "1":
        return
    if os.environ.get("TZ") != "Asia/Tokyo":
        os.environ["TZ"] = "Asia/Tokyo"
        if hasattr(time, "tzset"):
            time.tzset()


_pin_jst()

