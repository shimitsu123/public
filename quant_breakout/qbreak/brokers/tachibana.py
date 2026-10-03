"""tachibana.py — 立花証券 e支店 API 适配器（v4r10；macOS / Linux 原生，无需 Excel、无需 Windows）。

为什么选它：日本の個人向けで「特定のOSやアプリを前提にしない」発注 API は実質これだけ。
  • 楽天         : MARKETSPEED II RSS = Windows + Excel 必須
  • 三菱UFJ eスマート(kabu): REST だが kabuステーション（Windows 専用）常駐が必要
  • 立花 e支店    : HTTP(GET/POST + JSON) + イベント配信。Mac/Linux/クラウドで直接動く。API 利用料 0 円
  • ｅ支店は東証上場の現物・信用のみ（米国株なし）→ 美股指数仓位用东证上市的 1655 等 ETF

v4r10（2026-08-29 发布；v4r9 于 2026-09-27 废止；公开仕様書 https://www.e-shiten.jp/e_api/mfds_json_api_menu.html）
  • 登录只送「认证 ID」（sAuthId）：ID / 密码已从引数中废止，2026-06-27 起 API 也不再需要电话认证
  • 应答里的 5 个虚拟 URL 用你在「ｅ支店・API 利用設定」登记的 RSA 公钥加密（RSA-OAEP / SHA-256 / MGF1-SHA-256，Base64），
    本地用私钥解密后使用 → 程序可以每天全自动登录（每次登录会收到一封「ログインメール」）
  • 交付書面未读（sKinsyouhouMidokuFlg=1）时不发放虚拟 URL：必须先在标准 Web（PC）上读完
  • 会话到 03:30 闭局失效（03:30～05:30 不能登录）；再次登录会让旧的虚拟 URL 失效 → 一个账户只能有一个进程在用
  • 一问一答：前一个应答收到之前不能发下一个请求；流量上限 秒 10 件；p_no 必须递增；p_sd_date 与服务器时刻差 30 秒以内
  • 所有注文都必须带第二暗証番号（sSecondPassword）

═══════════════════════════════════════════════════════════════════════════
★ `TachibanaSpec` 的默认值按 2026-09-25 的公开仕様書（v4r10）逐项核对过，但**没有在真实账户上跑过**。
   本番发单前必须先在デモ環境通过（デモ用认证 ID 与密钥另行取得）：
       python run.py tachibana-probe --demo
   仕様改版时只改 var/tachibana_spec.json（覆盖这里的默认值），其余代码不用动。
═══════════════════════════════════════════════════════════════════════════

设计要点
  1. HTTP 层抽象成 `Transport`，测试用 `FakeTransport`，下单逻辑 100% 可测
  2. 凭证只从 **环境变量 / macOS 钥匙串 / 权限 600 的私钥文件** 读，代码、配置、日志里都不出现
  3. 発注前有三道闸：HALT 文件 → ARM（环境变量或 arm 文件）→ 单笔金额上限
  4. 发单类请求（新规 / 订正 / 取消）绝不自动重发，只有「会话已切断」(p_errno=2) 这种确定没处理的情况才重新登录再发一次
  5. 支持 **逆指値（stop order）**——这是盘中止损的真正保险，比程序轮询可靠
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import stat
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
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
    """API のエンドポイントと項目名（v4r10 公開仕様書 2026-08-29 版で核对）。"""
    base_live: str = "https://kabuka.e-shiten.jp/e_api_v4r10/"
    base_demo: str = "https://demo-kabuka.e-shiten.jp/e_api_v4r10/"
    auth_path: str = "auth/"
    http_method: str = "POST"            # v4r8 起 GET / POST 都可；POST 把 JSON 放 body，免去 URL 编码的歧义
    min_interval_s: float = 0.2          # 一问一答 + 秒 10 件上限，留余量

    # 登录应答
    key_url_request: str = "sUrlRequest"
    key_url_master: str = "sUrlMaster"
    key_url_price: str = "sUrlPrice"
    key_url_event: str = "sUrlEvent"
    key_url_event_ws: str = "sUrlEventWebSocket"
    key_unread: str = "sKinsyouhouMidokuFlg"          # 1 = 交付書面未読 → 不发放虚拟 URL
    key_next_release: str = "sUpdateInformAPISpecFunction"
    f_auth_id: str = "sAuthId"

    # 结果 / 错误
    key_errno: str = "p_errno"           # "0" = 正常
    key_err: str = "p_err"
    errno_session_cut: str = "2"         # 「セッションが切断しました。」→ 重新登录
    key_result: str = "sResultCode"      # 业务结果 "0" = 正常（时价类应答没有这个字段）
    ok_result: str = "0"
    key_result_text: str = "sResultText"

    # CLMID（機能 ID）
    clm_login: str = "CLMAuthLoginRequest"
    clm_logout: str = "CLMAuthLogoutRequest"
    clm_price: str = "CLMMfdsGetMarketPrice"          # → 仮想URL（PRICE）
    clm_new_order: str = "CLMKabuNewOrder"
    clm_cancel_order: str = "CLMKabuCancelOrder"
    clm_order_list: str = "CLMOrderList"
    clm_order_detail: str = "CLMOrderListDetail"
    clm_positions: str = "CLMGenbutuKabuList"
    clm_buying_power: str = "CLMZanKaiKanougaku"

    # 共通項目
    f_clmid: str = "sCLMID"
    f_json_fmt: str = "sJsonOfmt"
    json_fmt: str = "4"                  # 4 = 用项目名（而不是项目编号）应答
    f_seq: str = "p_no"
    f_time: str = "p_sd_date"
    time_format: str = "%Y.%m.%d-%H:%M:%S.000"

    # 新规注文（CLMKabuNewOrder）
    f_tax: str = "sZyoutoekiKazeiC"      # 1 特定 / 3 一般 / 5 NISA / 6 N成長；默认取登录应答里的账户值
    tax_specific: str = "1"
    f_code: str = "sIssueCode"
    f_market: str = "sSizyouC"
    market_tokyo: str = "00"
    f_side: str = "sBaibaiKubun"
    side_buy: str = "3"                  # 1 売 / 3 買
    side_sell: str = "1"
    f_condition: str = "sCondition"
    cond_normal: str = "0"               # 0 指定なし / 2 寄付 / 4 引け / 6 不成
    cond_opening: str = "2"
    cond_closing: str = "4"
    f_price: str = "sOrderPrice"
    price_market: str = "0"              # 0 = 成行；"*" = 指定なし（只下逆指値时）
    price_none: str = "*"
    f_qty: str = "sOrderSuryou"
    f_cash_margin: str = "sGenkinShinyouKubun"
    cash_only: str = "0"                 # 0 現物
    f_expire: str = "sOrderExpireDay"
    expire_today: str = "0"              # 0 当日；YYYYMMDD（10 営業日内，只能配「指定なし」条件）
    f_stop_type: str = "sGyakusasiOrderType"
    stop_none: str = "0"                 # 0 通常 / 1 逆指値 / 2 通常＋逆指値
    stop_only: str = "1"
    f_stop_trigger: str = "sGyakusasiZyouken"
    stop_trigger_none: str = "0"
    f_stop_price: str = "sGyakusasiPrice"
    stop_price_none: str = "*"
    f_tatebi: str = "sTatebiType"        # 建日種類：現物は "*"
    tatebi_none: str = "*"
    f_pos_tax: str = "sTategyokuZyoutoekiKazeiC"   # 現引・現渡以外は "*"
    pos_tax_none: str = "*"
    f_second_pw: str = "sSecondPassword"
    f_order_no: str = "sOrderNumber"
    f_order_date: str = "sEigyouDay"     # 注文番号 + 営業日 で一意；订正 / 取消 / 明细都要两者

    # 时价（CLMMfdsGetMarketPrice）
    f_target_codes: str = "sTargetIssueCode"       # 逗号分隔，1 次最多 120 只
    f_target_cols: str = "sTargetColumn"
    price_cols: str = "pDPP,pDOP,pDHP,pDLP,pDV,pPRP"
    max_quote_codes: int = 120
    r_price_list: str = "aCLMMfdsMarketPrice"
    r_price_code: str = "sIssueCode"
    r_price: str = "pDPP"                # 現在値
    r_open: str = "pDOP"
    r_high: str = "pDHP"
    r_low: str = "pDLP"
    r_volume: str = "pDV"
    r_prev_close: str = "pPRP"

    # 注文明细（CLMOrderListDetail）/ 一览（CLMOrderList）
    r_filled_qty: str = "sYakuzyouSuryou"          # 明细：約定株数
    r_filled_px: str = "sYakuzyouPrice"            # 明细：約定単価
    r_status_code: str = "sOrderStatusCode"        # 7 取消完了 / 9 一部約定 / 10 全部約定 / 12 全部失効 …
    r_status: str = "sOrderStatus"                 # 状态名称
    r_order_list: str = "aOrderList"
    r_list_order_no: str = "sOrderOrderNumber"
    r_list_filled_qty: str = "sOrderYakuzyouSuryo"  # 一览里没有末尾的 u
    r_exec_list: str = "aYakuzyouSikkouList"       # 明细里的约定列表（一笔成交一行；分几次成交时按数量加权）—— デモで要確認
    r_exec_qty: str = "sYakuzyouSuryou"
    r_exec_px: str = "sYakuzyouPrice"

    # 现物持仓（CLMGenbutuKabuList）/ 买付余力（CLMZanKaiKanougaku）
    r_positions: str = "aGenbutuKabuList"
    r_pos_code: str = "sUriOrderIssueCode"
    r_pos_qty: str = "sUriOrderZanKabuSuryou"
    r_pos_sellable: str = "sUriOrderUritukeKanouSuryou"
    r_pos_avg: str = "sUriOrderGaisanBokaTanka"
    r_cash: str = "sSummaryGenkabuKaituke"         # 株式現物買付可能額

    @classmethod
    def load(cls) -> "TachibanaSpec":
        """var/tachibana_spec.json があればそれで上書き（仕様改版時はここだけ直す）。"""
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
    登録:  security add-generic-password -s qbreak-tachibana-authid -a qbreak -w
    （-w の後に何も書かなければ対話入力になり、シェル履歴に残らない）"""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def _read_text(p: str | None) -> str | None:
    if not p:
        return None
    fp = Path(p).expanduser()
    return fp.read_text(encoding="utf-8").strip() if fp.exists() else None


@dataclass(repr=False)
class Credentials:
    """认证 ID + RSA 私钥（PEM）+ 第二暗証番号。repr 不输出任何值，避免意外写进日志。"""
    auth_id: str
    private_key_pem: bytes
    second_password: str = ""

    def __repr__(self) -> str:
        return "Credentials(<hidden>)"

    @classmethod
    def from_env(cls, demo: bool = False) -> "Credentials":
        """本番 / デモ各一套（「本番環境とデモ環境では、各々別の認証 ID、秘密鍵、公開鍵のセット」）。
        认证 ID：TACHIBANA_AUTH_ID[_DEMO] → TACHIBANA_AUTH_ID_FILE[_DEMO]（e_api_authid.txt）→ 钥匙串 qbreak-tachibana-authid[-demo]
        私钥：TACHIBANA_PRIVATE_KEY[_DEMO] → ~/.qbreak/e_api_private_key[_demo].pem（权限必须 600）
        第二暗証：TACHIBANA_SECOND_PASSWORD → 钥匙串 qbreak-tachibana-2nd（デモ也用 -demo 后缀）"""
        sfx, kc = ("_DEMO", "-demo") if demo else ("", "")
        aid = (os.environ.get(f"TACHIBANA_AUTH_ID{sfx}", "").strip()
               or _read_text(os.environ.get(f"TACHIBANA_AUTH_ID_FILE{sfx}"))
               or _keychain(f"qbreak-tachibana-authid{kc}", "qbreak") or "")
        if not aid:
            raise BrokerError(
                f"缺少认证 ID：设置环境变量 TACHIBANA_AUTH_ID{sfx}（或 TACHIBANA_AUTH_ID_FILE{sfx} 指向 e_api_authid.txt），"
                f"或存进钥匙串：security add-generic-password -s qbreak-tachibana-authid{kc} -a qbreak -w")
        kp = Path(os.environ.get(f"TACHIBANA_PRIVATE_KEY{sfx}")
                  or Path.home() / ".qbreak" / f"e_api_private_key{'_demo' if demo else ''}.pem").expanduser()
        if not kp.exists():
            raise BrokerError(f"找不到私钥 {kp}：把「ｅ支店・API 利用設定」登记公钥对应的私钥放在这里（chmod 600），"
                              f"或用环境变量 TACHIBANA_PRIVATE_KEY{sfx} 指定")
        if os.name == "posix" and kp.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise BrokerError(f"私钥 {kp} 的权限太宽（别的用户可读）：chmod 600 {kp}")
        sec = (os.environ.get(f"TACHIBANA_SECOND_PASSWORD{sfx}")
               or _keychain(f"qbreak-tachibana-2nd{kc}", "qbreak") or "")
        return cls(aid, kp.read_bytes(), sec)


def decrypt_url(private_key_pem: bytes, value: str) -> str:
    """虚拟 URL 的解密：Base64（标准字母表）→ RSA-OAEP（SHA-256，MGF1-SHA-256，无 label）→ ASCII。与官方 v4r10 样例相同。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    raw = key.decrypt(base64.b64decode(value),
                      padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return raw.decode("ascii").rstrip("\r\n")


# ══════════════════════════ 传输层 ══════════════════════════
class Transport(Protocol):
    def get_json(self, url: str, payload: dict) -> dict: ...


class HttpTransport:
    """立花 API：JSON 请求。POST（body = JSON）或 GET（URL?{JSON}，URL 编码）；应答为 Shift_JIS（按 cp932 解码）。
    这里只发一次，不重试 —— 重试策略由调用方按请求种类决定（发单类绝不自动重发）。"""

    def __init__(self, timeout: float = 15.0, method: str = "POST"):
        self.timeout = timeout
        self.method = method.upper()

    def get_json(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        if self.method == "POST":
            req = urllib.request.Request(url, data=body.encode("ascii"), method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": "qbreak/2.2"})
        else:
            req = urllib.request.Request(f"{url}?{urllib.parse.quote(body, safe='')}",
                                         headers={"User-Agent": "qbreak/2.2"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:   # noqa: S310
            raw = r.read().decode("cp932", errors="replace")
        return json.loads(raw)


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
            raise ConnectionError(f"模拟网络错误 {clm}")          # 网络层的错误（不是服务器应答的业务错误）
        r = self.responses.get(clm)
        if callable(r):
            return r(payload)
        if r is None:
            return {"p_errno": "0", "sResultCode": "0", "sCLMID": clm}
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
        self.tr = transport or HttpTransport(method=self.spec.http_method)
        self.creds = creds
        self.demo = demo
        self.require_arm = require_arm
        self.dry_run = dry_run
        self.limit_buffer_pct = limit_buffer_pct
        self.confirm_timeout_s = confirm_timeout_s
        self.max_order_value = max_order_value
        self._urls: dict[str, str] = {}
        self._seq = 0
        self._lock = threading.RLock()         # 一问一答：发请求 + 收应答 全程持锁（守护进程是多线程的）
        self._last_sent = 0.0
        self._sent_ids: dict[str, tuple[str, str]] = {}   # client_id -> (注文番号, 営業日)
        self._logged_in = False
        self._tax = ""                         # 登录应答里的账户课税区分（1 特定 / 3 一般 …）
        self.next_release = ""                 # 下一次 API 版本发布日（登录应答告知）

    # ── 会话 ──
    def _send(self, url: str, clmid: str, fields: dict, idempotent: bool) -> dict:
        """一问一答：分配 p_no、盖时间戳、发送、等应答，全程持锁；只读请求遇网络错误退避重试。"""
        s = self.spec

        def once() -> dict:
            with self._lock:
                wait = s.min_interval_s - (time.monotonic() - self._last_sent)
                if wait > 0:
                    time.sleep(wait)
                self._seq += 1
                p = {s.f_seq: str(self._seq), s.f_time: dt.datetime.now(JST).strftime(s.time_format),
                     s.f_clmid: clmid, s.f_json_fmt: s.json_fmt}
                p.update({k: v for k, v in fields.items() if v is not None})
                try:
                    return self.tr.get_json(url, p)
                finally:
                    self._last_sent = time.monotonic()
        return retry(once, attempts=3, base_delay=1.0, log=log) if idempotent else once()

    def _check(self, clmid: str, res: dict) -> None:
        s = self.spec
        errno = str(res.get(s.key_errno, "0"))
        if errno != "0":
            raise BrokerError(f"{clmid} 失败 {s.key_errno}={errno} {res.get(s.key_err, '')}")
        rc = str(res.get(s.key_result, s.ok_result))
        if rc != s.ok_result:
            raise BrokerError(f"{clmid} 失败 {s.key_result}={rc} {res.get(s.key_result_text, '')}")

    def login(self) -> None:
        if self._logged_in:
            return
        s = self.spec
        c = self.creds = self.creds or Credentials.from_env(demo=self.demo)
        base = s.base_demo if self.demo else s.base_live
        res = self._send(base + s.auth_path, s.clm_login, {s.f_auth_id: c.auth_id}, idempotent=True)
        try:
            self._check(s.clm_login, res)
        except BrokerError as e:
            raise BrokerError(f"登录失败：{e}。请确认：①「ｅ支店・API 利用設定」=利用する ②公钥已登记 "
                              f"③认证 ID 与环境一致（本番 / デモ 各一套）④03:30～05:30 不能登录") from None
        if str(res.get(s.key_unread, "0")) == "1":
            raise BrokerError("交付書面未読：API 不发放虚拟 URL。请在标准 Web（PC）上阅读确认后重试")
        urls = {}
        for k in (s.key_url_request, s.key_url_master, s.key_url_price, s.key_url_event, s.key_url_event_ws):
            v = res.get(k)
            if v:
                try:
                    urls[k] = decrypt_url(c.private_key_pem, v)
                except ImportError:
                    raise BrokerError("缺少 cryptography（解密虚拟 URL 需要）：pip install -r requirements.txt") from None
                except Exception as e:                    # noqa: BLE001
                    raise BrokerError(f"虚拟 URL 解密失败（{type(e).__name__}）：私钥与登记的公钥不配对，"
                                      "或本番 / デモ的密钥用反了") from None
        if s.key_url_request not in urls:
            raise BrokerError(f"登录响应里没有 {s.key_url_request}，仕様が想定と違います。"
                              "`python run.py tachibana-probe --demo` で応答を確認してください")
        self._urls = urls
        self._tax = str(res.get(s.f_tax) or "")
        self.next_release = str(res.get(s.key_next_release) or "")
        self._logged_in = True
        log.info("已登录立花 e支店 API v4r10（%s）", "デモ環境" if self.demo else "本番環境")
        if self.next_release and self.next_release >= dt.datetime.now(JST).strftime("%Y%m%d"):
            log.warning("立花通知：下一次 API 版本发布日 %s —— 请查看仕様变更，必要时更新 tachibana_spec.json", self.next_release)

    def logout(self) -> None:
        if not self._logged_in:
            return
        try:
            self._call(self.spec.clm_logout)
        except Exception as e:                      # noqa: BLE001
            log.warning("登出失败（忽略）: %s", e)
        finally:
            self._logged_in = False

    def _call(self, clmid: str, url_key: str | None = None, *, idempotent: bool = True, **kw) -> dict:
        """发到虚拟 URL。会话被切断（03:30 闭局 / 别处重新登录）时重新登录一次再发：p_errno=2 表示该请求没被处理，
        所以发单类也可以安全重发这一次；其他错误一律抛出，不猜。"""
        s = self.spec
        for attempt in (1, 2):
            self.login()
            url = self._urls.get(url_key or s.key_url_request) or self._urls[s.key_url_request]
            res = self._send(url, clmid, kw, idempotent=idempotent)
            if str(res.get(s.key_errno, "0")) == s.errno_session_cut and attempt == 1:
                log.warning("%s：会话已切断（%s），重新登录后重试一次", clmid, res.get(s.key_err, ""))
                self._logged_in = False
                continue
            self._check(clmid, res)
            return res
        raise BrokerError(f"{clmid}：重新登录后会话仍被切断")          # pragma: no cover

    # ── 行情 ──
    @staticmethod
    def _code(ticker: str) -> str:
        return ticker.split(".")[0]

    @staticmethod
    def _rows(v) -> list[dict]:
        """列表项：有数据是数组，没有数据是 ""（仕様）。"""
        if isinstance(v, dict):
            return [v]
        return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []

    def quote_detail(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        """批量取行情（1 次最多 120 只）：{票: {price 现在值, open 始値, high, low, prev_close 前日終値}}。
        空值（开盘前 / 还没寄り付き / 休市 / 暂时拒绝时是 ""）不放进结果，不让一只票拖垮整轮。"""
        s = self.spec
        cols = {"price": s.r_price, "open": s.r_open, "high": s.r_high, "low": s.r_low, "prev_close": s.r_prev_close}
        out: dict[str, dict[str, float]] = {}
        for i in range(0, len(tickers), s.max_quote_codes):
            chunk = tickers[i:i + s.max_quote_codes]
            try:
                res = self._call(s.clm_price, url_key=s.key_url_price,
                                 **{s.f_target_codes: ",".join(self._code(t) for t in chunk),
                                    s.f_target_cols: s.price_cols})
            except Exception as e:                  # noqa: BLE001
                log.debug("取价失败 %s: %s", chunk[:3], e)
                continue
            by = {str(r.get(s.r_price_code, "")).strip(): r for r in self._rows(res.get(s.r_price_list))}
            for t in chunk:
                row, d = by.get(self._code(t)) or {}, {}
                for k, f in cols.items():
                    v = row.get(f)
                    try:
                        if v not in (None, "") and float(v) > 0:
                            d[k] = float(v)
                    except (TypeError, ValueError):
                        pass
                if d:
                    out[t] = d
        return out

    def quotes(self, tickers: list[str]) -> dict[str, float]:
        """批量取现在值（quote_detail 的 price）。"""
        return {t: d["price"] for t, d in self.quote_detail(tickers).items() if "price" in d}

    def get_price(self, ticker: str) -> float:
        q = self.quotes([ticker])
        if ticker not in q:
            # 券商在开盘前/休市时会返回空值，这不是故障
            raise BrokerError(f"{ticker}: 现在值为空（休市或该代码无行情）")
        return q[ticker]

    # ── 持仓与余力：以券商侧为准 ──
    def positions(self) -> dict[str, Position]:
        """现物保有：同一只票可能按课税区分（特定 / NISA…）分成多行 → 合计股数、按股数加权平均成本。"""
        s = self.spec
        res = self._call(s.clm_positions, **{s.f_code: ""})
        agg: dict[str, list[float]] = {}
        for r in self._rows(res.get(s.r_positions)):
            try:
                code = str(r.get(s.r_pos_code) or "").strip()
                qty = int(float(r.get(s.r_pos_qty) or 0))
                avg = float(r.get(s.r_pos_avg) or 0)
            except (TypeError, ValueError):
                continue
            if code and qty > 0:
                q0, c0 = agg.get(code, [0, 0.0])
                agg[code] = [q0 + qty, c0 + qty * avg]
        return {f"{c}.T": Position(ticker=f"{c}.T", qty=int(q), avg_px=(v / q if q else 0.0))
                for c, (q, v) in agg.items()}

    def cash(self) -> float:
        s = self.spec
        res = self._call(s.clm_buying_power, **{s.f_code: "", s.f_market: ""})
        v = res.get(s.r_cash)
        if v in (None, ""):
            raise BrokerError(f"读不到株式現物買付可能額（{s.r_cash}），仕様を確認してください")
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

    @staticmethod
    def _px(v: float) -> str:
        """注文値段：整数就不带小数点（仕様示例 "201"）；呼値小于 1 円的价位保留小数。"""
        return str(int(round(v))) if abs(v - round(v)) < 1e-9 else f"{v:.1f}"

    # ── 发单 ──
    def _place(self, ticker: str, side: str, qty: int, limit: float | None,
               client_id: str, condition: str | None = None,
               stop_trigger: float | None = None) -> Order:
        s = self.spec
        ref = 0.0
        if not stop_trigger:
            try:
                ref = self.get_price(ticker)
            except BrokerError:
                pass
        auction = (condition or s.cond_normal) in (s.cond_opening, s.cond_closing)
        if stop_trigger:
            px = 0.0                                 # 只下逆指値：通常部分「指定なし」，触发后成行
        elif limit:
            px = round_to_tick(limit, ticker, side)
        elif auction:
            px = 0.0                                 # 寄付 / 引け 不给价格 = 成行：在集合竞价里按开盘价成交（回测的「次日开盘成交」）
        else:                                        # 盘中不给价格：按现在值 ± 缓冲挂指値（可成交的限价，不用成行）
            px = ref * (1 + (1 if side == "BUY" else -1) * self.limit_buffer_pct / 100) if ref else 0.0
            px = round_to_tick(px, ticker, side) if px else 0.0
        trig = round_to_tick(stop_trigger, ticker, side) if stop_trigger else 0.0
        notional = (px or ref or trig) * qty

        blocked = self._preflight(ticker, qty, notional)
        if not blocked and side == "BUY" and not stop_trigger and not (px or ref):
            blocked = "成行买单估不出金额（取不到现在值），单笔上限无法检查 → 拒绝；请给指値"
        if not blocked and not self.dry_run:
            if self.creds is None:
                try:
                    self.creds = Credentials.from_env(demo=self.demo)
                except BrokerError as e:
                    blocked = str(e)
            if self.creds is not None and not self.creds.second_password:
                blocked = ("缺少第二暗証番号（所有注文必填）：环境变量 TACHIBANA_SECOND_PASSWORD "
                           "或钥匙串 qbreak-tachibana-2nd")
        if blocked:
            log.warning("拒绝发单 %s %s x%d：%s", side, ticker, qty, blocked)
            return Order(ticker, side, qty, px, _now(), "BLOCKED",
                         client_id=client_id, note=blocked)
        if self.has_client_id(client_id):
            return Order(ticker, side, qty, px, _now(), "REJECTED",
                         client_id=client_id, note="重复的 client_id（幂等拦截）")
        if not self.dry_run:
            try:
                self.login()                             # 课税区分（sZyoutoekiKazeiC）取登录应答里的账户值
            except Exception as e:                        # noqa: BLE001
                log.error("登录失败，未发单 %s %s x%d: %s", side, ticker, qty, e)
                return Order(ticker, side, qty, px, _now(), "ERROR", client_id=client_id, note=str(e)[:300])

        fields = {
            s.f_tax: self._tax or s.tax_specific,
            s.f_code: self._code(ticker),
            s.f_market: s.market_tokyo,
            s.f_side: s.side_buy if side == "BUY" else s.side_sell,
            s.f_condition: condition or s.cond_normal,
            s.f_price: (s.price_none if stop_trigger else (self._px(px) if px else s.price_market)),
            s.f_qty: str(int(qty)),
            s.f_cash_margin: s.cash_only,
            s.f_expire: s.expire_today,
            s.f_stop_type: s.stop_only if stop_trigger else s.stop_none,
            s.f_stop_trigger: self._px(trig) if stop_trigger else s.stop_trigger_none,
            s.f_stop_price: s.price_market if stop_trigger else s.stop_price_none,   # 逆指値触发后成行，确保成交
            s.f_tatebi: s.tatebi_none,
            s.f_pos_tax: s.pos_tax_none,
        }
        if self.dry_run:
            log.info("[DRY-RUN] 本应发送 %s", fields)
            return Order(ticker, side, qty, px, _now(), "BLOCKED",
                         client_id=client_id, note="dry-run 未真正发单", extra=dict(fields))

        try:
            res = self._call(s.clm_new_order, idempotent=False,
                             **{**fields, s.f_second_pw: self.creds.second_password})
        except BrokerError as e:                          # 服务器应答了错误（p_errno / sResultCode ≠ 0，例如余力不足）：确定没受理
            log.error("发单被拒 %s: %s", fields, e)
            return Order(ticker, side, qty, px, _now(), "REJECTED",
                         client_id=client_id, note=str(e)[:300])
        except Exception as e:                            # noqa: BLE001  网络 / 超时 / 应答解析失败：可能已被受理 → 状态不明，绝不自动重发
            log.error("发单结果不明 %s: %s", fields, e)
            return Order(ticker, side, qty, px, _now(), "ERROR",
                         client_id=client_id, note=f"状态不明（{type(e).__name__}）：{e}"[:300])

        order_no, day = str(res.get(s.f_order_no) or ""), str(res.get(s.f_order_date) or "")
        self._sent_ids[client_id] = (order_no, day)
        o = Order(ticker, side, qty, px, _now(), "SENT", client_id=client_id,
                  broker_id=order_no, extra={"order_date": day})
        if (condition or s.cond_normal) == s.cond_opening or stop_trigger:
            o.note = "寄付注文を受付（次の寄付で約定）" if not stop_trigger else "逆指値を受付（条件到達まで市場に出ない）"
            return o
        return self._confirm(o)

    def _confirm(self, o: Order) -> Order:
        """発注 → 約定確認。数量が合わなければ必ず声を上げる（黙って進むのが一番高くつく）。"""
        deadline = _mono() + self.confirm_timeout_s
        while o.filled_qty < o.qty and _mono() < deadline:
            _sleep(1.0)
            try:
                r = self.order_status(o.broker_id, o.extra.get("order_date", ""))
            except Exception as e:                        # noqa: BLE001
                log.warning("約定確認失败: %s", e)
                break
            o.filled_qty = r["filled_qty"]
            o.filled_px = r["avg_px"] or o.filled_px
            o.extra["broker_status"] = r["status_code"]
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
        # bar 非空 = 收盘后下单 → 寄付（次日开盘）成交，与回测的 T+1 开盘一致；16:30 起受理翌営業日分
        cond = self.spec.cond_opening if bar else self.spec.cond_normal
        return self._place(ticker, "BUY", qty, limit, client_id, condition=cond)

    def sell(self, ticker, qty, limit=None, client_id="", ref_px=None, bar=""):
        cond = self.spec.cond_opening if bar else self.spec.cond_normal
        return self._place(ticker, "SELL", qty, limit, client_id, condition=cond)

    def place_protective_stop(self, ticker: str, qty: int, trigger: float,
                              client_id: str = "") -> Order:
        """逆指値（ぎゃくさしね / stop order）。挂在券商侧才是真正的止损保险：
        Mac 休眠、断网、程序崩溃都不影响它。当日有效，守护进程每个交易日开盘前重新挂。"""
        return self._place(ticker, "SELL", qty, None, client_id,
                           condition=self.spec.cond_normal, stop_trigger=trigger)

    def order_status(self, broker_id: str, order_date: str) -> dict:
        """注文番号 + 営業日 → {filled_qty 約定株数, avg_px 約定平均単価, status_code, status}（CLMOrderListDetail，只读）。
        明细里有约定列表时：一笔就用它的价格，分几笔成交按数量加权；没有列表时用明细顶层的約定株数 / 約定単価。
        一个账户的执行器第二天早上用它把前一天的实际成交记进模型状态（注文番号与営業日存在执行器的账本里）。"""
        s = self.spec
        r = self._call(s.clm_order_detail, **{s.f_order_no: broker_id, s.f_order_date: order_date})
        rows = []
        for x in self._rows(r.get(s.r_exec_list)):
            try:
                q, p = int(float(x.get(s.r_exec_qty) or 0)), float(x.get(s.r_exec_px) or 0)
            except (TypeError, ValueError):
                continue
            if q > 0 and p > 0:
                rows.append((q, p))
        if rows:
            qty = sum(q for q, _ in rows)
            px = rows[0][1] if len(rows) == 1 else sum(q * p for q, p in rows) / qty
        else:
            try:
                qty, px = int(float(r.get(s.r_filled_qty) or 0)), float(r.get(s.r_filled_px) or 0)
            except (TypeError, ValueError):
                qty, px = 0, 0.0
        return {"filled_qty": qty, "avg_px": px if qty > 0 else 0.0,
                "status_code": str(r.get(s.r_status_code) or ""), "status": str(r.get(s.r_status) or "")}

    def cancel_order(self, broker_id: str, order_date: str) -> bool:
        """按注文番号 + 営業日撤单（执行器把两者存在账本里：进程重启后也能撤）。撤单只会减少风险，HALT 时也允许。"""
        if not broker_id:
            return False
        s = self.spec
        try:
            if self.creds is None:
                self.creds = Credentials.from_env(demo=self.demo)
            if not self.creds.second_password:
                raise BrokerError("缺少第二暗証番号")
            self._call(s.clm_cancel_order, idempotent=False,
                       **{s.f_order_no: broker_id, s.f_order_date: order_date, s.f_second_pw: self.creds.second_password})
            return True
        except Exception as e:                            # noqa: BLE001
            log.warning("撤单失败 %s: %s", broker_id, e)
            return False

    def cancel(self, client_id: str) -> bool:
        ref = self._sent_ids.get(client_id)
        return bool(ref) and self.cancel_order(*ref)

    def open_orders(self) -> list[dict]:
        try:
            return self._rows(self._call(self.spec.clm_order_list).get(self.spec.r_order_list))
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
    return time.monotonic()


def _sleep(s: float) -> None:
    time.sleep(s)
