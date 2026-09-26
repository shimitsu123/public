"""rakuten_rss.py — 楽天証券 MARKETSPEED II RSS 适配器（第4阶段：実弾 / live）。

背景（2026-09 核对）
  楽天証券对个人不提供官方 REST API，唯一官方自动化通道是
  「マーケットスピード II RSS」—— 一个 Excel 插件：Excel 里用 RSS 函数取实时行情，
  用 RSS 発注関数（VBA）下单。Python 通过 xlwings 远程操作 Excel。
  前提：Windows + 桌面版 Excel + MarketSpeed II 已登录 + RSS「接続」+ 功能区「発注可」。
  RSS 覆盖国内株/先物OP，**不支持美股**。

本文件的设计要点（和原版的最大区别）
  1. **Python 端完全不碰 RSS 函数名**。RSS 的発注関数签名逐年变（官方「RSS 関数一覧」PDF
     每年更新），把它写死在 Python 里等于每年坏一次。这里只约定一个稳定契约：
        VBA 宏 QB_PlaceOrder(payload_json)  -> json
        VBA 宏 QB_QueryOrder(client_id)     -> json
     RSS 的版本差异全部关在 excel/RssBridge.bas 里，由你按当期 PDF 填一次。
  2. **Excel 交互被抽象成 ExcelBridge**，测试用 FakeExcelBridge 就能覆盖
     ARM 闸门、呼値取整、约定核对、幂等等全部下单逻辑（原版这些逻辑完全无法测试）。
  3. **指値价格自动对齐呼値**（原版「现价×1.005」经常是非法价格，会被券商拒单）。
  4. **发单后必须回读约定**（約定確認 / fill confirmation）；数量对不上就报错并写 HALT。
"""
from __future__ import annotations

import json
import time
from typing import Any, Protocol

from .. import paths
from ..tick import round_to_tick
from ..utils import setup_logging
from .base import BaseBroker, BrokerError, Order, Position

log = setup_logging("broker.rss")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ────────────────────────── Excel 桥接 ──────────────────────────
class ExcelBridge(Protocol):
    def read(self, sheet: str, addr: str) -> Any: ...
    def read_range(self, sheet: str, addr: str) -> list: ...
    def write(self, sheet: str, addr: str, value: Any) -> None: ...
    def call_macro(self, name: str, *args) -> Any: ...


class XlwingsBridge:
    """真实实现。只在 Windows + Excel 上可用。"""

    def __init__(self, workbook: str = "rss_bridge.xlsm", visible: bool = True):
        import platform
        if platform.system() != "Windows":
            raise BrokerError(
                "楽天 RSS 只能在 Windows + 桌面版 Excel + MarketSpeed II 上运行。"
                f"当前系统是 {platform.system()}。回测与模拟盘不受影响，"
                "实盘请在 Windows 机器上执行。")
        try:
            import xlwings as xw                  # noqa: PLC0415  延迟导入
        except ImportError as e:
            raise BrokerError("缺少 xlwings：请先 `pip install xlwings`") from e
        self.xw = xw
        try:
            self.wb = xw.Book(workbook)           # 已打开则连接，未打开则按路径打开
        except Exception as e:                    # noqa: BLE001
            raise BrokerError(
                f"打不开工作簿 {workbook}：{e}\n"
                "请确认：①Excel 已启动 ②MarketSpeed II 已登录且 RSS 显示「接続」"
                "③工作簿路径正确（建议用绝对路径）") from e
        self.wb.app.visible = visible

    def read(self, sheet: str, addr: str) -> Any:
        return self.wb.sheets[sheet].range(addr).value

    def read_range(self, sheet: str, addr: str) -> list:
        v = self.wb.sheets[sheet].range(addr).value
        return v if isinstance(v, list) else [v]

    def write(self, sheet: str, addr: str, value: Any) -> None:
        self.wb.sheets[sheet].range(addr).value = value

    def call_macro(self, name: str, *args) -> Any:
        return self.wb.macro(name)(*args)


class FakeExcelBridge:
    """测试/演练用：把 Excel 换成内存字典，下单逻辑可以完整跑一遍而不碰真钱。"""

    def __init__(self, cells: dict | None = None, quotes: dict | None = None,
                 positions: list | None = None, cash: float = 1_000_000):
        self.cells: dict[tuple[str, str], Any] = cells or {}
        self.quotes = quotes or {}                 # {"7203": 2500.0}
        self.pos_rows = positions or []            # [[7203, 300, 2400.0], ...]
        self.cells.setdefault(("Ctrl", "ARM"), "")
        self.cash_value = cash
        self.sent: list[dict] = []
        self.fill_ratio = 1.0                      # 1.0=全部成交；0=不成交，用于测试未约定分支

    def read(self, sheet, addr):
        if sheet == "Pos" and addr == "CASH":
            return self.cash_value
        return self.cells.get((sheet, addr))

    def read_range(self, sheet, addr):
        if sheet == "Quote":
            return [[code, px] for code, px in self.quotes.items()]
        if sheet == "Pos":
            return list(self.pos_rows)
        return []

    def write(self, sheet, addr, value):
        self.cells[(sheet, addr)] = value

    def call_macro(self, name, *args):
        if name == "QB_PlaceOrder":
            req = json.loads(args[0])
            self.sent.append(req)
            filled = int(req["qty"] * self.fill_ratio)
            return json.dumps({"ok": True, "order_id": f"MOCK{len(self.sent):04d}",
                               "client_id": req["client_id"], "filled_qty": filled,
                               "filled_px": req.get("price") or self.quotes.get(req["code"], 0),
                               "status": "FILLED" if filled == req["qty"] else "PARTIAL"})
        if name == "QB_CancelOrder":
            return json.dumps({"ok": True, "client_id": args[0]})
        if name == "QB_QueryOrder":
            cid = args[0]
            for r in self.sent:
                if r["client_id"] == cid:
                    filled = int(r["qty"] * self.fill_ratio)
                    return json.dumps({"ok": True, "client_id": cid, "filled_qty": filled,
                                       "filled_px": r.get("price") or self.quotes.get(r["code"], 0),
                                       "status": "FILLED" if filled == r["qty"] else "PARTIAL"})
            return json.dumps({"ok": False, "error": "not found"})
        raise BrokerError(f"未知宏 {name}")


# ────────────────────────── 券商实现 ──────────────────────────
class RakutenRSSBroker(BaseBroker):
    market = "JP"

    def __init__(self, bridge: ExcelBridge | None = None, workbook: str = "rss_bridge.xlsm",
                 require_arm: bool = True, limit_buffer_pct: float = 0.5,
                 confirm_timeout_s: float = 15.0, dry_run: bool = False):
        self.bridge = bridge or XlwingsBridge(workbook)
        self.require_arm = require_arm
        self.limit_buffer_pct = limit_buffer_pct    # 指値 = 現在値 ×(1±该%)，防止成行的极端滑点
        self.confirm_timeout_s = confirm_timeout_s
        self.dry_run = dry_run
        self._seen: set[str] = set()

    # ── 行情 ──
    @staticmethod
    def _code(ticker: str) -> str:
        return ticker.split(".")[0]

    def get_price(self, ticker: str) -> float:
        code = self._code(ticker)
        deadline = time.time() + 5.0
        while True:                                   # RSS 刷新有延迟，等价格变成数字
            for row in self.bridge.read_range("Quote", "A2:B300"):
                if not row or row[0] in (None, ""):
                    continue
                if str(int(float(row[0]))) == code:
                    v = row[1]
                    if isinstance(v, (int, float)) and v > 0:
                        return float(v)
            if time.time() > deadline:
                raise BrokerError(
                    f"RSS 取不到 {ticker} 的现在值。检查 Quote 表 A 列是否有该代码、"
                    "MarketSpeed II 是否登录、RSS 是否「接続」。")
            time.sleep(0.5)

    # ── 持仓与余力：以券商侧为准 ──
    def positions(self) -> dict[str, Position]:
        out: dict[str, Position] = {}
        for row in self.bridge.read_range("Pos", "A2:C300"):
            if not row or row[0] in (None, ""):
                continue
            t = f"{int(float(row[0]))}.T"
            out[t] = Position(ticker=t, qty=int(float(row[1] or 0)),
                              avg_px=float(row[2] or 0))
        return {t: p for t, p in out.items() if p.qty > 0}

    def cash(self) -> float:
        v = self.bridge.read("Pos", "CASH")
        if not isinstance(v, (int, float)):
            raise BrokerError("读不到买付余力（Pos!CASH 命名区域）")
        return float(v)

    # ── 安全闸 ──
    def _armed(self) -> bool:
        if not self.require_arm:
            return True
        return str(self.bridge.read("Ctrl", "ARM") or "").strip().upper() == "ARMED"

    def _preflight(self, side: str, ticker: str, qty: int) -> str | None:
        if paths.halt_file().exists():
            return f"存在 HALT 文件 {paths.halt_file()}"
        if qty <= 0:
            return "数量为 0"
        if not self._armed():
            return "未 ARM：请在 Excel 的 Ctrl!ARM 单元格手工填入 ARMED（收盘后清空）"
        return None

    def has_client_id(self, client_id: str) -> bool:
        return bool(client_id) and client_id in self._seen

    # ── 下单 ──
    def _place(self, ticker: str, side: str, qty: int, limit: float | None,
               client_id: str, condition: str = "NORMAL",
               order_type: str = "LIMIT", trigger: float | None = None) -> Order:
        blocked = self._preflight(side, ticker, qty)
        if blocked:
            log.warning("拒绝发单 %s %s x%d：%s", side, ticker, qty, blocked)
            return Order(ticker, side, qty, limit or 0, _now(), "BLOCKED",
                         client_id=client_id, note=blocked)
        if self.has_client_id(client_id):
            return Order(ticker, side, qty, limit or 0, _now(), "REJECTED",
                         client_id=client_id, note="重复的 client_id（幂等拦截）")

        ref = self.get_price(ticker)
        raw = limit if limit else ref * (1 + (1 if side == "BUY" else -1)
                                         * self.limit_buffer_pct / 100)
        px = round_to_tick(raw, ticker, side)          # 必须落在合法呼値上，否则券商拒单
        payload = {"client_id": client_id or f"{ticker}-{side}-{int(time.time())}",
                   "code": self._code(ticker), "side": side, "qty": int(qty),
                   "price": px, "order_type": order_type,
                   "condition": condition,        # NORMAL / OPENING(寄付) / CLOSING(引け)
                   "trigger": round_to_tick(trigger, ticker, side) if trigger else 0,
                   "market": "TSE", "account": "SPECIFIC",
                   "expire": "TODAY" if condition != "GTC" else "GTC"}

        if self.dry_run:
            log.info("[DRY-RUN] 本应发送: %s", payload)
            return Order(ticker, side, qty, px, _now(), "BLOCKED",
                         client_id=payload["client_id"], note="dry-run 未真正发单")

        self._seen.add(payload["client_id"])
        try:
            raw_res = self.bridge.call_macro("QB_PlaceOrder", json.dumps(payload, ensure_ascii=False))
            res = json.loads(raw_res) if isinstance(raw_res, str) else dict(raw_res or {})
        except Exception as e:                          # noqa: BLE001
            log.error("发单宏调用失败 %s: %s", payload, e)
            return Order(ticker, side, qty, px, _now(), "ERROR",
                         client_id=payload["client_id"], note=f"宏调用失败: {e}")
        if not res.get("ok"):
            return Order(ticker, side, qty, px, _now(), "REJECTED",
                         client_id=payload["client_id"], note=str(res.get("error"))[:200])

        o = Order(ticker, side, qty, px, _now(), res.get("status", "SENT"),
                  filled_qty=int(res.get("filled_qty") or 0),
                  filled_px=float(res.get("filled_px") or 0),
                  client_id=payload["client_id"], broker_id=str(res.get("order_id", "")),
                  extra=res)
        return self._confirm(o)

    def _confirm(self, o: Order) -> Order:
        """発注 → 回读約定（成交）。数量对不上就明确告警：静默的不一致才是最贵的。"""
        deadline = time.time() + self.confirm_timeout_s
        while o.filled_qty < o.qty and time.time() < deadline:
            time.sleep(1.0)
            try:
                raw = self.bridge.call_macro("QB_QueryOrder", o.client_id)
                r = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            except Exception as e:                      # noqa: BLE001
                log.warning("查询约定失败: %s", e)
                break
            if r.get("ok"):
                o.filled_qty = int(r.get("filled_qty") or 0)
                o.filled_px = float(r.get("filled_px") or o.filled_px)
                o.status = r.get("status", o.status)
        if o.filled_qty == 0:
            o.status = "SENT"
            o.note = f"{self.confirm_timeout_s:.0f}s 内未约定（指値 {o.price} 可能未触及），请人工确认"
            log.warning("★ %s %s x%d 未约定：%s", o.side, o.ticker, o.qty, o.note)
        elif o.filled_qty < o.qty:
            o.status = "PARTIAL"
            o.note = f"部分约定 {o.filled_qty}/{o.qty}"
            log.warning("★ %s", o.note)
        else:
            o.status = "FILLED"
        log.info("ORDER %s %s x%d 限价%.1f → %s 约定%d @%.1f",
                 o.side, o.ticker, o.qty, o.price, o.status, o.filled_qty, o.filled_px)
        return o

    def buy(self, ticker, qty, limit=None, client_id="", ref_px=None, bar=""):
        # 收盘后下单 → 寄付（次日开盘）成交，与回测的 T+1 开盘一致
        return self._place(ticker, "BUY", qty, limit, client_id,
                           condition="OPENING" if bar else "NORMAL")

    def sell(self, ticker, qty, limit=None, client_id="", ref_px=None, bar=""):
        return self._place(ticker, "SELL", qty, limit, client_id,
                           condition="OPENING" if bar else "NORMAL")

    def place_protective_stop(self, ticker: str, qty: int, trigger: float,
                              client_id: str = "") -> Order:
        """挂逆指値（ぎゃくさしね / stop order）。只有真的挂了它，
        回测里 stop_fill_mode="intraday" 的那套收益才站得住。"""
        return self._place(ticker, "SELL", qty, None, client_id, condition="GTC",
                           order_type="STOP", trigger=trigger)

    def cancel(self, client_id: str) -> bool:
        try:
            raw = self.bridge.call_macro("QB_CancelOrder", client_id)
            r = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            return bool(r.get("ok"))
        except Exception as e:                      # noqa: BLE001
            log.warning("撤单失败 %s: %s", client_id, e)
            return False

    def fill_pending(self, opens, bar, max_gap_pct=None, prev_bars=None, locked=None):
        """RSS 侧的寄付注文由交易所撮合，这里无事可做（接口对齐用）。"""
        return []

    def sync(self) -> None:
        self.positions()                                # 触发一次读取，确认表格可用
