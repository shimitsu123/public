"""模拟账户用立花本番的实时行情（2026-10-17 用户：「现在能取到实盘实时数据的话直接全体能用到立花实时数据的地方用实时数据就可以了」）。

只在「一次运行取一次」的地方用（每天几次）：
  - 盘中的手动指令（--phase now）：成交价 = 立花的現在値（以前 = Yahoo 最新的 1 分钟线，约晚 20 分钟）
  - 成交日的开盘撮合（--phase open）：开盘价 = 立花的始値 / 高値 / 安値（以前 = Yahoo 1 分钟线今天第一根，和正式开盘价常不一样）
  - 面板的确认框（2026-10-17 用户「想定时取得的话用yahoo，下单的时候在确认页面的时候用立花能看到实时价格 k线也可以更新到那时候」）：
    打开卖出 / 调仓 / 买入 / 固定口数的框时取一次（qbreak/panel.rt_quotes；同一只 60 秒内不再登录，没取成 60 秒内不再试）
面板每分钟的报价、盘中观测每 5 分钟不用它：立花 2026-03-10「APIご利用に関するお願い」请用户盘中避免频繁取价（负荷大可能停用 API），
而且同一账户只能一个会话（登录会把执行器踢掉）→ 那几处要另做（EVENT I/F 推送 + 一个进程拿会话），这里不做。

只读：TachibanaBroker(dry_run=True, require_arm=True) —— 绝不发单；登录前拿「立花本番会话锁」（与执行器 / probe 共用），
只等 WAIT_S 秒（执行器在跑就不等它，照旧 Yahoo）；取完马上登出、放锁。
取不到（没有凭证 / 会话被占 / 登录失败 / 维护时间 / 还没寄付）→ 那只票不给，调用方照旧用 Yahoo，并写明用的是哪个（src）。
关掉：环境变量 QBREAK_PAPER_RT=0（测试里 conftest 默认关掉：不让测试登录真的立花）。"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

ENV = "QBREAK_PAPER_RT"
WAIT_S = 20.0
SRC_RT = "立花实时"
SRC_YH = "Yahoo 1 分钟线（约晚 20 分钟）"
PURPOSE = ("模拟账户取实时价（只读）", "取现价 / 始値 → 马上登出（不发单）→ 模拟账户按这个价成交")
PANEL_PURPOSE = ("面板确认框取实时价（只读）", "取现价 → 马上登出（不发单）→ 确认框与 K 线按这个价显示")


def enabled() -> bool:
    return os.environ.get(ENV, "1").strip().lower() not in ("0", "off", "no", "false")


def _default_make():
    from .brokers.tachibana import TachibanaBroker
    return TachibanaBroker(demo=False, dry_run=True, require_arm=True)


def tachibana_detail(tickers, make=None, wait_s: float = WAIT_S, purpose: tuple | None = None) -> tuple[dict, str | None]:
    """登录立花本番（只读）→ quote_detail → 登出。→ ({票: {price, open, high, low, prev_close}}, 没取到的原因 或 None)。"""
    tickers = sorted(set(tickers))
    if not tickers:
        return {}, None
    if not enabled():
        return {}, f"没开（{ENV}=0）"
    from .brokers import tachibana as T
    b = None
    old = os.environ.get("QBREAK_TACHIBANA_SESSION_WAIT_S")
    os.environ["QBREAK_TACHIBANA_SESSION_WAIT_S"] = str(wait_s)       # 执行器拿着会话：只等一会儿，不拖住面板 / 这次运行
    try:
        b = (make or _default_make)()
        b.purpose = purpose or PURPOSE                                 # 登录推送写这个（qbreak/brokers/tachibana.push_login）
        b.login()
        return b.quote_detail(list(tickers)), None
    except Exception as e:                                             # noqa: BLE001  没有凭证 / 会话被占 / 登录失败 → 照旧 Yahoo
        why = f"{type(e).__name__}: {T._no_url(e)}"[:200]
        log.info("立花实时价没取到（照旧 Yahoo）：%s", why)
        return {}, why
    finally:
        if old is None:
            os.environ.pop("QBREAK_TACHIBANA_SESSION_WAIT_S", None)
        else:
            os.environ["QBREAK_TACHIBANA_SESSION_WAIT_S"] = old
        if b is not None:
            try:
                b.logout()
            except Exception:                                          # noqa: BLE001
                pass


class NowQuote:
    """--phase now 的 quote(票列表) → {票: 现在价}：先立花的現在値，没有的票用 yahoo(票列表)。src = 这次用的来源（成交说明写它）。"""

    def __init__(self, yahoo, make=None):
        self.yahoo, self.make = yahoo, make
        self.src, self.why = SRC_YH, None

    def __call__(self, tickers) -> dict:
        ts = sorted(set(tickers))
        d, self.why = tachibana_detail(ts, self.make)
        out = {t: float(v["price"]) for t, v in d.items() if t in ts and float(v.get("price") or 0) > 0}
        rest = [t for t in ts if t not in out]
        yh = {t: float(p) for t, p in ((self.yahoo(rest) or {}) if rest else {}).items() if p and float(p) > 0}
        self.src = (f"{SRC_RT} + {SRC_YH}" if out and yh else SRC_RT if out else SRC_YH)
        out.update(yh)
        return out


class OpenFeed:
    """--phase open 的 feed(票, now) → {票: {"open", "high", "low", "first"}}：立花在应答 → 只用立花的始値（寄付之后才有；
    还没寄付的票不给 → 执行器整批等下一轮）；立花取不到 → 整批用 yahoo(票, now)（不混用：同一批的开盘价口径一样）。src = 这次用的来源。"""

    def __init__(self, yahoo, make=None):
        self.yahoo, self.make = yahoo, make
        self.src, self.why = SRC_YH, None

    def __call__(self, tickers, now=None) -> dict:
        ts = sorted(set(tickers))
        d, self.why = tachibana_detail(ts, self.make)
        out = {}
        for t, v in d.items():
            op = float(v.get("open") or 0)
            if t in ts and op > 0 and float(v.get("price") or 0) > 0:   # 现在值也有才算今天寄付了（开盘前现在值是空的：不拿前一天的始値）
                hi, lo = float(v.get("high") or op), float(v.get("low") or op)
                out[t] = {"open": op, "high": max(hi, op), "low": min(lo, op), "first": "09:00"}
        if self.why is None and d:
            self.src = SRC_RT                     # 立花在应答：还没寄付的票就是还没有（下一轮再试），不拿 Yahoo 补
            return out
        self.src = SRC_YH
        return self.yahoo(ts, now) if now is not None else self.yahoo(ts)
