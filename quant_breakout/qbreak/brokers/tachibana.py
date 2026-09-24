"""tachibana.py — 立花証券 e支店 API 适配器（macOS / Linux 原生，无需 Excel、无需 Windows）。

为什么选它：日本の個人向けで「特定のOSやアプリを前提にしない」発注 API は実質これだけ。
  • 楽天         : MARKETSPEED II RSS = Windows + Excel 必須
  • 三菱UFJ eスマート(kabu): REST だが kabuステーション（Windows 専用）常駐が必要
  • 立花 e支店    : HTTP(GET+JSON) + イベント配信。Mac/Linux/クラウドで直接動く。API 利用料 0 円

═══════════════════════════════════════════════════════════════════════════
★ 非常に重要：`TachibanaSpec` の中身は「公開情報ベースの既定値」であって、
   公式仕様書で検証したものではありません。本番発注の前に必ず
       python run.py tachibana-probe --demo
   をデモ環境で通し、口座開設時にもらう公式 API 仕様書と 1 項目ずつ突き合わせてください。
   API のバージョン（URL の e_api_vXrY）や項目名は改訂されます。
   ——この一箇所さえ直せば他のコードは触らなくて済むよう、定数は全部ここに閉じ込めてあります。
═══════════════════════════════════════════════════════════════════════════

设计要点（和 RSS 适配器同样的思路）
  1. HTTP 层抽象成 `Transport`，测试用 `FakeTransport`，下单逻辑 100% 可测
  2. 凭证只从 **环境变量 / macOS 钥匙串** 读，代码和配置文件里不出现密码
  3. 発注前有三道闸：HALT 文件 → ARM（环境变量或 arm 文件）→ 单笔金额上限
  4. 発注后必须回读約定；数量对不上就告警
  5. 支持 **逆指値（stop order）**——这是盘中止损的真正保险，比程序轮询可靠
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .. import paths
from ..calendar_jp import JST
from ..tick import round_to_tick
from ..utils import retry, setup_logging
from .base import BaseBroker, BrokerError, Order, Position

log = setup_logging("broker.tachibana")


# ══════════════════════════ 仕様（ここだけ直せばよい） ══════════════════════════
@dataclass
class TachibanaSpec:
    """API のエンドポイントと項目名。**公式仕様書で必ず検証すること。**"""
    base_live: str = "https://kabuka.e-shiten.jp/e_api_v4r6/"
    base_demo: str = "https://demo-kabuka.e-shiten.jp/e_api_v4r6/"
    auth_path: str = "auth/"

    # 応答に含まれる各機能の URL キー
    key_url_request: str = "sUrlRequest"
    key_url_master: str = "sUrlMaster"
    key_url_price: str = "sUrlPrice"
    key_url_event: str = "sUrlEvent"
    key_result: str = "sResultCode"
    ok_result: str = "0"

    # CLMID（機能コード）
    clm_login: str = "CLMAuthLoginRequest"
    clm_logout: str = "CLMAuthLogoutRequest"
    clm_price: str = "CLMMfdsGetMarketPrice"
    clm_new_order: str = "CLMKabuNewOrder"
    clm_cancel_order: str = "CLMKabuCancelOrder"
    clm_order_list: str = "CLMOrderList"
    clm_order_detail: str = "CLMOrderListDetail"
    clm_positions: str = "CLMGenbutuKabuList"
    clm_buying_power: str = "CLMZanKaiKanougaku"

    # 共通項目
    f_clmid: str = "sCLMID"
    f_json_fmt: str = "sJsonOfmt"
    json_fmt: str = "4"
    f_seq: str = "p_no"
    f_time: str = "p_sd_date"
    time_format: str = "%Y.%m.%d-%H:%M:%S.000"

    # 発注項目
    f_code: str = "sIssueCode"
    f_market: str = "sSizyouC"
    market_tokyo: str = "00"
    f_side: str = "sBaibaiKubun"
    side_buy: str = "3"          # ★ 1=売 / 3=買 が一般的だが仕様書で要確認
    side_sell: str = "1"
    f_qty: str = "sChuumonSuryou"
    f_price: str = "sChuumonPrice"
    price_market: str = "0"      # 0 = 成行
    f_condition: str = "sCondition"
    cond_normal: str = "0"
    cond_opening: str = "2"      # 寄付（よりつき）
    cond_closing: str = "4"      # 引け
    f_stop_type: str = "sGyakusasiOrderType"
    stop_none: str = "0"
    stop_only: str = "1"         # 逆指値のみ
    f_stop_trigger: str = "sGyakusasiZyouken"
    f_stop_price: str = "sGyakusasiPrice"
    f_account: str = "sTatebiType"      # 口座/建日区分
    f_tax: str = "sZyoutoekiKazeiC"
    tax_specific: str = "1"      # 特定口座（源泉徴収あり）★要確認
    f_expire: str = "sOrderExpireDay"
    expire_today: str = "0"
    f_order_no: str = "sOrderNumber"
    f_order_date: str = "sEigyouDay"

    # 応答項目
    r_price: str = "pDPP"                # 現在値
    r_open: str = "pDOP"
    r_high: str = "pDHP"
    r_low: str = "pDLP"
    r_volume: str = "pDV"
    r_order_no: str = "sOrderNumber"
    r_filled_qty: str = "sOrderYakuzyouSuryou"
    r_filled_px: str = "sOrderYakuzyouPrice"
    r_status: str = "sOrderStatus"
    r_positions: str = "aGenbutuKabuList"
    r_pos_code: str = "sUriKanouSuryou"
    r_cash: str = "sSuiziKaiTukeKanouGaku"

    @classmethod
    def load(cls) -> "TachibanaSpec":
        """var/tachibana_spec.json があればそれで上書き（公式仕様書に合わせて直した内容）。"""
        fp = paths.home() / "tachibana_spec.json"
        if not fp.exists():
            return cls()
        d = json.loads(fp.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(d) - known
        if unknown:
            log.warning("tachibana_spec.json に未知のキー: %s（無視）", sorted(unknown))
        log.info("仕様を %s で上書きしました", fp)
        return cls(**{k: v for k, v in d.items() if k in known})

    def dump_template(self) -> str:
        fp = paths.home() / "tachibana_spec.json"
        fp.write_text(json.dumps(self.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
        return str(fp)


# ══════════════════════════ 凭证 ══════════════════════════
def _keychain(service: str, account: str) -> str | None:
    """macOS 钥匙串（Keychain）から取得。存在しなければ None。
    登録:  security add-generic-password -s qbreak-tachibana -a <ID> -w
    （-w の後に何も書かなければ対話入力になり、シェル履歴に残らない）"""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


@dataclass
class Credentials:
    user_id: str
    password: str
    second_password: str = ""      # 取引暗証番号（第二パスワード）

    @classmethod
    def from_env(cls) -> "Credentials":
        uid = os.environ.get("TACHIBANA_USER_ID", "").strip()
        if not uid:
            raise BrokerError(
                "缺少凭证：请设置环境变量 TACHIBANA_USER_ID，"
                "密码放环境变量 TACHIBANA_PASSWORD 或 macOS 钥匙串：\n"
                "  security add-generic-password -s qbreak-tachibana -a <你的ID> -w")
        pw = os.environ.get("TACHIBANA_PASSWORD") or _keychain("qbreak-tachibana", uid)
        if not pw:
            raise BrokerError(f"找不到 {uid} 的密码（环境变量 TACHIBANA_PASSWORD 或钥匙串都没有）")
        sec = (os.environ.get("TACHIBANA_SECOND_PASSWORD")
               or _keychain("qbreak-tachibana-2nd", uid) or "")
        return cls(uid, pw, sec)


# ══════════════════════════ 传输层 ══════════════════════════
class Transport(Protocol):
    def get_json(self, url: str, payload: dict) -> dict: ...


class HttpTransport:
    """立花 API は「JSON を URL エンコードしてクエリに付けた GET」で全てやり取りする。"""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def get_json(self, url: str, payload: dict) -> dict:
        # 認証 URL は末尾 "/" にそのまま連結、それ以外は "?" で連結する仕様
        q = urllib.parse.quote(json.dumps(payload, ensure_ascii=False))
        full = f"{url}{q}" if url.endswith("/") else f"{url}?{q}"

        def _do():
            req = urllib.request.Request(full, headers={"User-Agent": "qbreak/2.1"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:   # noqa: S310
                raw = r.read().decode("cp932", errors="replace")
            return json.loads(raw)

        return retry(_do, attempts=3, base_delay=1.0, log=log)


class FakeTransport:
    """测试用：按 CLMID 返回预设响应，并记录所有发出的 payload。"""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.sent: list[tuple[str, dict]] = []
        self.fail_next: str | None = None

    def get_json(self, url: str, payload: dict) -> dict:
        self.sent.append((url, dict(payload)))
        clm = payload.get("sCLMID", "")
        if self.fail_next == clm:
            self.fail_next = None
            raise BrokerError(f"模拟网络错误 {clm}")
        r = self.responses.get(clm)
        if callable(r):
            return r(payload)
        if r is None:
            return {"sResultCode": "0", "sCLMID": clm}
        return dict(r)


# ══════════════════════════ 券商实现 ══════════════════════════
class TachibanaBroker(BaseBroker):
    market = "JP"

    def __init__(self, transport: Transport | None = None, spec: TachibanaSpec | None = None,
                 creds: Credentials | None = None, demo: bool = False,
                 require_arm: bool = True, dry_run: bool = False,
                 limit_buffer_pct: float = 0.5, confirm_timeout_s: float = 20.0,
                 max_order_value: float = 300_000):
        self.spec = spec or TachibanaSpec.load()
        self.tr = transport or HttpTransport()
        self.creds = creds
        self.demo = demo
        self.require_arm = require_arm
        self.dry_run = dry_run
        self.limit_buffer_pct = limit_buffer_pct
        self.confirm_timeout_s = confirm_timeout_s
        self.max_order_value = max_order_value
        self._urls: dict[str, str] = {}
        self._seq = 0
        self._lock = threading.Lock()          # 守护进程是多线程的，p_no 必须串行
        self._sent_ids: dict[str, str] = {}    # client_id -> 注文番号
        self._logged_in = False

    # ── 会话 ──
    def _next_seq(self) -> str:
        with self._lock:
            self._seq += 1
            return str(self._seq)

    def _envelope(self, clmid: str, **kw) -> dict:
        s = self.spec
        p = {s.f_clmid: clmid, s.f_json_fmt: s.json_fmt, s.f_seq: self._next_seq(),
             s.f_time: dt.datetime.now(JST).strftime(s.time_format)}
        p.update({k: v for k, v in kw.items() if v is not None})
        return p

    def login(self) -> None:
        if self._logged_in:
            return
        s = self.spec
        c = self.creds or Credentials.from_env()
        base = s.base_demo if self.demo else s.base_live
        res = self.tr.get_json(base + s.auth_path,
                               self._envelope(s.clm_login, sUserId=c.user_id,
                                              sPassword=c.password))
        if str(res.get(s.key_result, "")) != s.ok_result:
            raise BrokerError(f"登录失败 {s.key_result}={res.get(s.key_result)}："
                              f"请核对 ID/密码、API 利用申込是否已生效、以及 API 版本 URL")
        for k in (s.key_url_request, s.key_url_master, s.key_url_price, s.key_url_event):
            if res.get(k):
                self._urls[k] = res[k]
        if s.key_url_request not in self._urls:
            raise BrokerError(f"登录响应里没有 {s.key_url_request}，仕様が想定と違います。"
                              "`python run.py tachibana-probe --demo` で応答を確認してください")
        self._logged_in = True
        log.info("已登录立花 e支店 API（%s）", "デモ環境" if self.demo else "本番環境")

    def logout(self) -> None:
        if not self._logged_in:
            return
        try:
            self._call(self.spec.clm_logout)
        except Exception as e:                      # noqa: BLE001
            log.warning("登出失败（忽略）: %s", e)
        finally:
            self._logged_in = False

    def _call(self, clmid: str, url_key: str | None = None, **kw) -> dict:
        self.login()
        s = self.spec
        url = self._urls.get(url_key or s.key_url_request) or self._urls[s.key_url_request]
        res = self.tr.get_json(url, self._envelope(clmid, **kw))
        rc = str(res.get(s.key_result, s.ok_result))
        if rc != s.ok_result:
            raise BrokerError(f"{clmid} 失败 {s.key_result}={rc} {res.get('sResultText', '')}")
        return res

    # ── 行情 ──
    @staticmethod
    def _code(ticker: str) -> str:
        return ticker.split(".")[0]

    def get_price(self, ticker: str) -> float:
        s = self.spec
        res = self._call(s.clm_price, url_key=s.key_url_price,
                         **{s.f_code: self._code(ticker), s.f_market: s.market_tokyo})
        raw = res.get(s.r_price)
        if raw in (None, "", 0, "0"):
            # 券商在开盘前/休市时会返回空值，这不是故障
            raise BrokerError(f"{ticker}: 现在值为空（休市或该代码无行情）")
        return float(raw)

    def quotes(self, tickers: list[str]) -> dict[str, float]:
        """批量取价。取不到的跳过，不让一只票拖垮整轮。"""
        out: dict[str, float] = {}
        for t in tickers:
            try:
                out[t] = self.get_price(t)
            except Exception as e:                  # noqa: BLE001
                log.debug("取价失败 %s: %s", t, e)
        return out

    # ── 持仓与余力：以券商侧为准 ──
    def positions(self) -> dict[str, Position]:
        s = self.spec
        res = self._call(s.clm_positions)
        rows = res.get(s.r_positions) or []
        out: dict[str, Position] = {}
        for r in rows:
            try:
                code = str(r.get(s.f_code) or r.get("sIssueCode") or "").strip()
                qty = int(float(r.get("sZanKabuSuryou") or r.get(s.r_pos_code) or 0))
                avg = float(r.get("sHyoukaTanka") or r.get("sGaisanBokaTanka") or 0)
            except (TypeError, ValueError):
                continue
            if code and qty > 0:
                t = f"{code}.T"
                out[t] = Position(ticker=t, qty=qty, avg_px=avg)
        return out

    def cash(self) -> float:
        s = self.spec
        res = self._call(s.clm_buying_power)
        v = res.get(s.r_cash)
        if v in (None, ""):
            raise BrokerError("读不到買付可能額，仕様を確認してください")
        return float(v)

    # ── 安全闸 ──
    def _armed(self) -> bool:
        if not self.require_arm:
            return True
        if os.environ.get("QBREAK_ARM", "").strip().upper() == "ARMED":
            return True
        f = paths.home() / "ARM"
        return f.exists() and f.read_text(encoding="utf-8").strip().upper() == "ARMED"

    def _preflight(self, ticker: str, qty: int, notional: float) -> str | None:
        if paths.halt_file().exists():
            return f"存在 HALT 文件 {paths.halt_file()}"
        if qty <= 0:
            return "数量为 0"
        if notional > self.max_order_value:
            return f"单笔金额 {notional:,.0f} > 上限 {self.max_order_value:,.0f}"
        if not self._armed():
            return ("未 ARM：请 `echo ARMED > $QBREAK_HOME/ARM` 或设 QBREAK_ARM=ARMED "
                    "（收盘后清空，这是防误单的最后一道人工闸）")
        return None

    def has_client_id(self, client_id: str) -> bool:
        return bool(client_id) and client_id in self._sent_ids

    # ── 发单 ──
    def _place(self, ticker: str, side: str, qty: int, limit: float | None,
               client_id: str, condition: str | None = None,
               stop_trigger: float | None = None) -> Order:
        s = self.spec
        ref = 0.0
        try:
            ref = self.get_price(ticker)
        except BrokerError:
            pass
        px = limit if limit else (ref * (1 + (1 if side == "BUY" else -1)
                                         * self.limit_buffer_pct / 100) if ref else 0)
        px = round_to_tick(px, ticker, side) if px else 0.0
        notional = px * qty if px else ref * qty

        blocked = self._preflight(ticker, qty, notional)
        if blocked:
            log.warning("拒绝发单 %s %s x%d：%s", side, ticker, qty, blocked)
            return Order(ticker, side, qty, px, _now(), "BLOCKED",
                         client_id=client_id, note=blocked)
        if self.has_client_id(client_id):
            return Order(ticker, side, qty, px, _now(), "REJECTED",
                         client_id=client_id, note="重复的 client_id（幂等拦截）")

        fields = {
            s.f_code: self._code(ticker),
            s.f_market: s.market_tokyo,
            s.f_side: s.side_buy if side == "BUY" else s.side_sell,
            s.f_qty: str(int(qty)),
            s.f_price: str(px) if px else s.price_market,
            s.f_condition: condition or s.cond_normal,
            s.f_tax: s.tax_specific,
            s.f_expire: s.expire_today,
        }
        if stop_trigger:
            fields[s.f_stop_type] = s.stop_only
            fields[s.f_stop_trigger] = str(round_to_tick(stop_trigger, ticker, side))
            fields[s.f_stop_price] = s.price_market      # 触发后成行（确保成交）
        else:
            fields[s.f_stop_type] = s.stop_none

        if self.dry_run:
            log.info("[DRY-RUN] 本应发送 %s", fields)
            return Order(ticker, side, qty, px, _now(), "BLOCKED",
                         client_id=client_id, note="dry-run 未真正发单", extra=fields)

        try:
            res = self._call(s.clm_new_order, **fields)
        except Exception as e:                            # noqa: BLE001
            log.error("发单失败 %s: %s", fields, e)
            return Order(ticker, side, qty, px, _now(), "ERROR",
                         client_id=client_id, note=str(e)[:300])

        order_no = str(res.get(s.r_order_no) or "")
        self._sent_ids[client_id] = order_no
        o = Order(ticker, side, qty, px, _now(), "SENT", client_id=client_id,
                  broker_id=order_no, extra={"order_date": res.get(s.f_order_date, "")})
        return self._confirm(o)

    def _confirm(self, o: Order) -> Order:
        """発注 → 約定確認。数量が合わなければ必ず声を上げる（黙って進むのが一番高くつく）。"""
        s = self.spec
        deadline = _mono() + self.confirm_timeout_s
        while o.filled_qty < o.qty and _mono() < deadline:
            _sleep(1.0)
            try:
                r = self._call(s.clm_order_detail, **{s.f_order_no: o.broker_id})
            except Exception as e:                        # noqa: BLE001
                log.warning("約定確認失败: %s", e)
                break
            try:
                o.filled_qty = int(float(r.get(s.r_filled_qty) or 0))
                o.filled_px = float(r.get(s.r_filled_px) or o.filled_px)
            except (TypeError, ValueError):
                pass
            o.extra["broker_status"] = r.get(s.r_status, "")
        if o.filled_qty == 0:
            o.status = "SENT"
            o.note = f"{self.confirm_timeout_s:.0f}s 内未约定（指値 {o.price} 未触及），保持挂单"
            log.warning("★ %s %s x%d %s", o.side, o.ticker, o.qty, o.note)
        elif o.filled_qty < o.qty:
            o.status = "PARTIAL"
            o.note = f"部分约定 {o.filled_qty}/{o.qty}"
            log.warning("★ %s", o.note)
        else:
            o.status = "FILLED"
        log.info("ORDER %s %s x%d 限价%.1f → %s 约定%d @%.1f (注文番号 %s)",
                 o.side, o.ticker, o.qty, o.price, o.status, o.filled_qty, o.filled_px,
                 o.broker_id)
        return o

    def buy(self, ticker, qty, limit=None, client_id="", ref_px=None, bar=""):
        # bar 非空 = 收盘后下单 → 寄付（次日开盘）成交，与回测的 T+1 开盘一致
        cond = self.spec.cond_opening if bar else self.spec.cond_normal
        return self._place(ticker, "BUY", qty, limit, client_id, condition=cond)

    def sell(self, ticker, qty, limit=None, client_id="", ref_px=None, bar=""):
        cond = self.spec.cond_opening if bar else self.spec.cond_normal
        return self._place(ticker, "SELL", qty, limit, client_id, condition=cond)

    def place_protective_stop(self, ticker: str, qty: int, trigger: float,
                              client_id: str = "") -> Order:
        """逆指値（ぎゃくさしね / stop order）。挂在券商侧才是真正的止损保险：
        Mac 休眠、断网、程序崩溃都不影响它。"""
        return self._place(ticker, "SELL", qty, None, client_id,
                           condition=self.spec.cond_normal, stop_trigger=trigger)

    def cancel(self, client_id: str) -> bool:
        no = self._sent_ids.get(client_id)
        if not no:
            return False
        try:
            self._call(self.spec.clm_cancel_order, **{self.spec.f_order_no: no})
            return True
        except Exception as e:                            # noqa: BLE001
            log.warning("撤单失败 %s: %s", client_id, e)
            return False

    def open_orders(self) -> list[dict]:
        try:
            return list(self._call(self.spec.clm_order_list).get("aOrderList") or [])
        except Exception as e:                            # noqa: BLE001
            log.warning("读取注文一覧失败: %s", e)
            return []

    def fill_pending(self, opens, bar, max_gap_pct=None, prev_bars=None, locked=None):
        """寄付注文は取引所側で約定するので、ここですることは無い（インタフェース整合用）。"""
        return []

    def sync(self) -> None:
        self.login()
        self.positions()


def _now() -> str:
    return dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def _mono() -> float:
    import time
    return time.monotonic()


def _sleep(s: float) -> None:
    import time
    time.sleep(s)
