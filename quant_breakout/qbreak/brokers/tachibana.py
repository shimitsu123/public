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
       bash scripts/liveu.sh probe --demo     （= run.py tachibana-probe --demo，数据目录 ~/.qbreak/home）
   仕様改版时只改数据目录的 tachibana_spec.json（只写要改的键：和默认一样的键不起作用，代码升级默认值时不会被冻住），其余代码不用动。
═══════════════════════════════════════════════════════════════════════════

设计要点
  1. HTTP 层抽象成 `Transport`，测试用 `FakeTransport`，下单逻辑 100% 可测
  2. 凭证只从 **环境变量 / macOS 钥匙串 / 权限 600 的私钥文件** 读，代码、配置、日志里都不出现
  3. 発注前有三道闸：HALT 文件 → ARM（环境变量或 arm 文件）→ 单笔金额上限；买单再加一道「立花能不能买」：
     立花自己的銘柄マスタ（v4r10 マスタ機能，每天早上取一次）里没有 / 優先市場不是东证 / 売買停止 / 外国株 / PRO Market /
     30 天内上場廃止 / 現物買付「取引禁止」/ 数量不是売買単位的整数倍 → 不发（qbreak/tradable.py；マスタ取不到也不发）
  4. 发单类请求（新规 / 订正 / 取消）绝不自动重发，只有「会话已切断」(p_errno=2) 这种确定没处理的情况才重新登录再发一次。
     发单结果分三种：服务器应答了错误 → REJECTED（确定没受理）；请求根本没发出（登录失败、第二暗証读不出、DNS 解析失败 / 连接被拒 /
     TLS 握手失败）→ BLOCKED（下一次运行可以安全重试）；超时 / 连接中途断开 / 应答解析失败 / 受理应答缺注文番号 → ERROR（状态不明，
     等人工核对）。约定确认遇到终态（被拒 / 失效 / 取消完了）马上停，记 REJECTED / EXPIRED。错误码按 spec 的对照表附上原因与修法
  5. 支持 **逆指値（stop order）**——这是盘中止损的真正保险，比程序轮询可靠
"""
from __future__ import annotations

import base64
import datetime as dt
import errno
import http.client
import json
import os
import re
import socket
import ssl
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Protocol

from .. import paths
from .. import tradable as TR
from ..calendar_jp import JST, is_trading_day, next_trading_day
from ..tick import price_limit_jp, round_to_tick
from ..utils import atomic_write_text, read_json, retry, setup_logging
from .base import BaseBroker, BrokerError, Order, Position

log = setup_logging("broker.tachibana")


# ══════════════════════════ 仕様（ここだけ直せばよい） ══════════════════════════
# 代码用的 API 版本段 → 那个版本的发布日（公开仕様書的改版履歴）：前一晚预检据此判断登录应答里的「新版本发布日」是不是
# 代码已经在用的这一版（qbreak/precheck.py）。改 base_live / base_demo 的版本段时这里一起加（tests/test_sched_b.py 会查）。
API_RELEASES = {"e_api_v4r10": "2026-08-29"}


@dataclass
class TachibanaSpec:
    """API のエンドポイントと項目名（v4r10 公開仕様書 2026-08-29 版で核对）。"""
    base_live: str = "https://kabuka.e-shiten.jp/e_api_v4r10/"
    base_demo: str = "https://demo-kabuka.e-shiten.jp/e_api_v4r10/"
    auth_path: str = "auth/"
    http_method: str = "POST"            # v4r8 起 GET / POST 都可；POST 把 JSON 放 body，免去 URL 编码的歧义
    min_interval_s: float = 0.2          # 一问一答 + 秒 10 件上限，留余量
    force_ipv4: bool = False             # 只用 IPv4 连接（错误码 10005 的对策；定时任务读不到 ~/.zshrc → 写进数据目录的 tachibana_spec.json
                                         # 「"force_ipv4": true」，或环境变量 QBREAK_TACHIBANA_IPV4=1）

    # 登录应答
    key_url_request: str = "sUrlRequest"
    key_url_master: str = "sUrlMaster"
    key_url_price: str = "sUrlPrice"
    key_url_event: str = "sUrlEvent"
    key_url_event_ws: str = "sUrlEventWebSocket"
    key_unread: str = "sKinsyouhouMidokuFlg"          # 1 = 交付書面未読 → 不发放虚拟 URL
    key_next_release: str = "sUpdateInformAPISpecFunction"   # 下一次 API 版本的发布日（YYYYMMDD）
    key_doc_update: str = "sUpdateInformWebDocument"          # 交付書面的更新预定日（C-04；没读完新书面之前 API 不发虚拟 URL）—— ★ デモで要確認
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
    # マスタ機能（v4r10：各个别情报的问合取得 → 仮想URL（MASTER）；API 说明：朝一度取得、日中は取得しない）
    clm_issue_mst: str = "CLMStkGetIssueMstKabu"                # 株式銘柄マスタ（優先市場 / 売買単位 / 売買停止）
    clm_issue_mkt: str = "CLMStkGetIssueSizyouMstKabu"          # 株式銘柄市場マスタ（上場市場 / 銘柄区分 / 上場区分 / 上場廃止日）
    clm_issue_kisei: str = "CLMStkGetIssueSizyouKiseiKabu"      # 株式銘柄別・市場別規制情報（現物/買付 …）
    r_issue_mst: str = "aCLMStkIssueMstKabu"
    r_issue_mkt: str = "aCLMStkIssueSizyouMstKabu"
    r_issue_kisei: str = "aCLMStkIssueSizyouKiseiKabu"

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
    # 一览的其余字段（状态不明的单找候选用：qbreak/live_ops.unknown_candidates）—— ★ デモで要確認（probe --demo 的注文一覧核对后，
    # 不同就在 tachibana_spec.json 改；只写要改的键）
    r_list_code: str = "sOrderIssueCode"           # 銘柄コード
    r_list_side: str = "sOrderBaibaiKubun"         # 売買区分（1 売 / 3 買，与 side_* 同一套值）
    r_list_qty: str = "sOrderOrderSuryou"          # 注文株数
    r_list_price: str = "sOrderOrderPrice"         # 注文単価（成行 = 0）
    r_list_filled_px: str = "sOrderYakuzyouPrice"  # 約定単価
    r_list_status_code: str = "sOrderStatusCode"   # 状态码（终态表同 status_*）
    r_list_status: str = "sOrderStatus"            # 状态名称
    r_list_time: str = "sOrderOrderDateTime"       # 注文日時（YYYYMMDDHHMMSS）
    r_exec_list: str = "aYakuzyouSikkouList"      # 明细里的约定列表（一笔成交一行；分几次成交时按数量加权）—— デモで要確認
    r_exec_qty: str = "sYakuzyouSuryou"
    r_exec_px: str = "sYakuzyouPrice"

    # 现物持仓（CLMGenbutuKabuList）/ 买付余力（CLMZanKaiKanougaku）
    r_positions: str = "aGenbutuKabuList"
    r_pos_code: str = "sUriOrderIssueCode"
    r_pos_qty: str = "sUriOrderZanKabuSuryou"
    r_pos_sellable: str = "sUriOrderUritukeKanouSuryou"
    r_pos_avg: str = "sUriOrderGaisanBokaTanka"
    r_cash: str = "sSummaryGenkabuKaituke"         # 株式現物買付可能額

    # 注文状态的终态（sOrderStatusCode，逗号分隔；仕様書「注文ステータス」：2 受付エラー / 7 取消完了 / 10 全部約定 / 11 一部失効 /
    # 12 全部失効 / 14 無効 / 17 切替注文失効 / 19 繰越失効 …）。终态 = 不会再成交：约定确认停止轮询、单记 REJECTED / EXPIRED。
    # ★ 代码值以官方参考手册为准，デモ核对后可在 tachibana_spec.json 改（只写要改的键）
    status_rejected: str = "2,14"                  # 被拒（受付エラー / 無効）
    status_expired: str = "11,12,17,19"            # 已失效（当日限り到期 / 寄付指値没成交 / ストップ安張り付き …）
    status_cancelled: str = "7"                    # 取消完了（执行器自己撤的、或在立花网站 / 手机网站上撤的）
    status_filled: str = "10"                      # 全部約定
    status_names: dict = field(default_factory=lambda: {
        "2": "受付エラー", "7": "取消完了", "10": "全部約定", "11": "一部失効", "12": "全部失効", "14": "無効",
        "17": "切替注文失効", "19": "繰越失効"})   # 应答里没有 sOrderStatus（状态名称）时显示用

    # 错误码对照表（C-15）：{代码: "原因：要做什么"}；p_errno 与 sResultCode 分开查，表里没有的再按原文里的关键词（err_words）找。
    # 来源：官方 v4r9 概要 PDF / REQUEST I/F 仕様（p_errno=8 时刻差、10005 只能用 IPv4 / 固定 IP）、e支店 Q&A；其余代码第一次
    # probe --demo 时把实际出现的补进来。★ デモ核对后可在 tachibana_spec.json 改；表里和关键词都没有的照旧只显示原文
    err_errno: dict = field(default_factory=lambda: {
        "2": "会话已切断（03:30 闭局 / 别处重新登录）：程序自动重新登录一次；一直出现 → 确认只有一个程序在用这个账户",
        "6": "p_no 没有递增（同一账户有两个程序同时在用？）：停掉另一个，重新登录",
        "8": "Mac 的时间和立花服务器差 30 秒以上：系统设置 → 通用 → 日期与时间 → 打开「自动设置」",
        "10005": "只能用 IPv4 连接（或登记了固定 IP、现在的 IP 变了）：数据目录的 tachibana_spec.json 写 \"force_ipv4\": true"
                 "（或环境变量 QBREAK_TACHIBANA_IPV4=1）强制 IPv4；登记过固定 IP 的在「ｅ支店・API 利用設定」改成现在的 IP"})
    err_result: dict = field(default_factory=lambda: {
        "10005": "只能用 IPv4 连接（或登记了固定 IP、现在的 IP 变了）：数据目录的 tachibana_spec.json 写 \"force_ipv4\": true"
                 "（或环境变量 QBREAK_TACHIBANA_IPV4=1）强制 IPv4；登记过固定 IP 的在「ｅ支店・API 利用設定」改成现在的 IP",
        **{c: "NISA 口座 / 非課税枠的限制被拒：本系统按口座的课税区分发单（NISA 买单只能「指値・無条件・当日中」）；"
              "在立花网站确认 NISA 的设定与可用枠" for c in ("11041", "11042", "11043", "11044", "11045", "11107")}})
    err_words: dict = field(default_factory=lambda: {
        "交付書面": "交付書面未読：在电脑上登录 e支店网站读完新的交付書面，再重试",
        "未読": "交付書面未読：在电脑上登录 e支店网站读完新的交付書面，再重试",
        "パスキー": "パスキー没设定 / 被解除：在 e支店网站重新设定パスキー，再确认「ｅ支店・API 利用設定」",
        "過負荷": "立花判断为过负荷、停用了 API：08:00〜15:30 不要频繁取价 / 轮询；联系立花恢复",
        "利用停止": "API 被停用（过负荷 / 设定）：在「ｅ支店・API 利用設定」确认，必要时联系立花",
        "バージョン": "这个 API 版本已停用：代码 / tachibana_spec.json 要更新到新版本（在 Mac 对话里问「立花 API 要更新吗」）",
        "暗証": "第二暗証番号不对：先修好钥匙串 qbreak-tachibana-2nd（终端：security add-generic-password -U "
                "-s qbreak-tachibana-2nd -a qbreak -w，回车后输入）",
        "余力": "买付余力不足：现金不够（未成交的买单占着余力 / 还没到账）",
        "値幅": "限价在当天的制限値幅之外（前日終値 ± 値幅）",
        "制限値": "限价在当天的制限値幅之外（前日終値 ± 値幅）",
        "内部者": "内部者登记的票：在立花网站申告之后才能买卖",
        "インサイダー": "内部者登记的票：在立花网站申告之后才能买卖",
        "差金": "差金決済的限制（同一天同一只票的买卖受限）：明天再下",
        "IPv": "只能用 IPv4 连接：数据目录的 tachibana_spec.json 写 \"force_ipv4\": true（或环境变量 QBREAK_TACHIBANA_IPV4=1）"})
    err_auth_words: str = "暗証"                   # 发单被拒的原文里有这些（逗号分隔）= 第二暗証 / 认证类 → 这次运行后面的单都不发
    err_auth_codes: str = ""                       # 同上（sResultCode，逗号分隔；デモ核对后填）

    @classmethod
    def load(cls) -> "TachibanaSpec":
        """データディレクトリ（Mac：~/.qbreak/home）の tachibana_spec.json があればそれで上書き（仕様改版時はここだけ直す）。
        只用和代码默认**不同**的键（一样的键不起作用：代码升级默认值时不会被冻住）；「_」开头的键是说明，不读。
        覆盖文件里 base_live / base_demo 的版本段和代码默认不同 → warning（上线门槛也标 ★：覆盖文件还指向旧版本）。"""
        info = override_info(cls)
        if info is None:
            return cls()
        if info["unknown"]:
            log.warning("tachibana_spec.json に未知のキー: %s（無視）", info["unknown"])
        for k, old, new in info["stale"]:
            log.warning("★ tachibana_spec.json 的 %s 指向 %s，代码默认是 %s：覆盖文件还指向旧版本？"
                        "（核对后删掉这个键，或改成新版本）", k, old, new)
        if info["keys"]:
            log.info("仕様を %s で上書きしました（覆盖的键：%s）", info["path"], info["keys"])
        return cls(**info["values"])

    def diff_from_default(self) -> dict:
        """和代码默认不同的键 → 值（--dump-spec 只写这些；面板 / 门槛显示「覆盖了哪些键」）。"""
        base = type(self)()
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) != getattr(base, f.name)}

    def dump_template(self) -> str:
        """--dump-spec：数据目录的 tachibana_spec.json 只写和代码默认不同的键（全一样 → 只有说明）；全部默认值另写一份
        tachibana_spec_defaults.json 只供参考（程序不读它）：要改哪个键，就只把那个键写进 tachibana_spec.json。"""
        home = paths.home()
        diff = self.diff_from_default()
        note = ("只写和代码默认不同的键（程序只读这些；「_」开头的是说明）。默认值见同目录的 tachibana_spec_defaults.json"
                "（只供参考、程序不读）；要改哪个键就只把那个键写进来。" + ("现在和默认完全一样。" if not diff else ""))
        fp = home / "tachibana_spec.json"
        atomic_write_text(fp, json.dumps({"_说明": note, **diff}, ensure_ascii=False, indent=1))
        atomic_write_text(home / "tachibana_spec_defaults.json",
                          json.dumps({"_说明": "TachibanaSpec 的代码默认值（只供参考，程序不读这个文件）",
                                      **{f.name: getattr(type(self)(), f.name) for f in fields(self)}},
                                     ensure_ascii=False, indent=1))
        return str(fp)


def override_info(cls=TachibanaSpec) -> dict | None:
    """数据目录的仕様覆盖文件（tachibana_spec.json）→ {path, keys（和默认不同、生效的键）, values, unknown（未知的键）,
    stale（[(键, 文件里的版本段, 代码默认的版本段)]：base_live / base_demo 的版本段和代码默认不同）}；没有文件 → None。
    文件读坏 → 抛出（和以前一样：坏的覆盖文件不能悄悄当作没有）。"""
    fp = paths.home() / "tachibana_spec.json"
    if not fp.exists():
        return None
    d = json.loads(fp.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise ValueError(f"{fp} 不是 JSON 对象")
    base = cls()
    known = {f.name for f in fields(cls)}
    vals = {k: v for k, v in d.items() if k in known and v != getattr(base, k)}
    stale = [(k, api_version(vals[k]), api_version(getattr(base, k))) for k in ("base_live", "base_demo")
             if k in vals and api_version(vals[k]) != api_version(getattr(base, k))]
    return {"path": str(fp), "keys": sorted(vals), "values": vals, "stale": stale,
            "unknown": sorted(k for k in d if k not in known and not str(k).startswith("_"))}


# ══════════════════════════ 凭证 ══════════════════════════
KC_MISSING, KC_LOCKED, KC_ERROR, KC_NONE = "missing", "locked", "error", "no-security"
_KC_WHY: dict[str, str] = {}                         # 服务名 → 上一次读不出的原因（提示用；不含值）


def keychain_why(rc: int | None, err: str = "") -> str:
    """security find-generic-password 的退出码 / stderr → 读不出的原因：
    44 = 没有这个条目（errSecItemNotFound）；36 / 29 / 51 或 stderr 含 interaction / locked = 钥匙串锁着、不允许交互（定时任务
    在锁屏 / 没登录的会话里）；None = 没有 security 命令（不是 macOS）；其他 = error。"""
    if rc is None:
        return KC_NONE
    e = (err or "").lower()
    if rc == 44:
        return KC_MISSING
    if rc in (29, 36, 51) or "interaction" in e or "locked" in e:
        return KC_LOCKED
    return KC_ERROR


def keychain_hint(service: str, why: str) -> str:
    """读不出时给人看的提示（不同原因不同修法；不含值）。"""
    if why == KC_LOCKED:
        return (f"钥匙串里的 {service} 读不出：登录钥匙串锁着 / 不允许交互（定时任务在锁屏或没登录的会话里）。请登录 Mac、解锁登录钥匙串；"
                "「钥匙串访问」→ 登录钥匙串的设置里不要勾「睡眠时锁定」/「闲置后锁定」。不用重新存密钥")
    if why == KC_ERROR:
        return f"钥匙串里的 {service} 读不出（security 出错）：在终端运行 bash scripts/liveu.sh gate 看「能读出」那一项"
    return f"存进钥匙串：security add-generic-password -s {service} -a qbreak -w（回车后输入，不要贴进聊天）"


def _keychain(service: str, account: str, run=None) -> str | None:
    """macOS 钥匙串（Keychain）から取得。存在しなければ None（读不出的原因记在 _KC_WHY，提示用）。
    登録:  security add-generic-password -s qbreak-tachibana-authid -a qbreak -w
    （-w の後に何も書かなければ対話入力になり、シェル履歴に残らない）。run：测试注入（代替 subprocess.run）。"""
    try:
        out = (run or subprocess.run)(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:                # 等授权 / 解锁超时（弹了框没人点）：当作锁着
        _KC_WHY[service] = KC_LOCKED
        return None
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        _KC_WHY[service] = KC_NONE
        return None
    if out.returncode == 0 and (out.stdout or "").strip():
        _KC_WHY.pop(service, None)
        return out.stdout.strip()
    _KC_WHY[service] = keychain_why(out.returncode, out.stderr) if out.returncode != 0 else KC_MISSING
    return None


def _kc_missing(service: str, default: str) -> str:
    """读不出的提示：钥匙串锁着 / security 出错 → 那个原因（不是「缺少」）；否则 default。"""
    why = _KC_WHY.get(service)
    return keychain_hint(service, why) if why in (KC_LOCKED, KC_ERROR) else default


def keychain_mdat(service: str, account: str = "qbreak", run=None) -> str:
    """钥匙串条目的修改时刻（security find-generic-password 不带 -w 的属性里的 mdat，例 20261009010203Z）：只读属性、不读值。
    读不出（没有这个条目 / 不是 macOS）→ ""。用来判断第二暗証被拒之后你有没有重新存过（OPS-12）。"""
    try:
        r = (run or subprocess.run)(["security", "find-generic-password", "-s", service, "-a", account],
                                    capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r'"mdat"<timedate>=\S*\s+"(\d{14}Z)', r.stdout or "") if r.returncode == 0 else None
    return m.group(1) if m else ""


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
    second_why: str = ""                 # 第二暗証读不出的原因（钥匙串锁着等；空 = 没设置 / 已读到）—— 不是值
    second_src: str = ""                 # 第二暗証从哪来："env" / "keychain"（空 = 直接给的，例如测试）—— 不是值

    def __repr__(self) -> str:
        return "Credentials(<hidden>)"

    @classmethod
    def from_env(cls, demo: bool = False) -> "Credentials":
        """本番 / デモ各一套（「本番環境とデモ環境では、各々別の認証 ID、秘密鍵、公開鍵のセット」）。
        认证 ID：TACHIBANA_AUTH_ID[_DEMO] → TACHIBANA_AUTH_ID_FILE[_DEMO]（e_api_authid.txt）→ 钥匙串 qbreak-tachibana-authid[-demo]
        私钥：TACHIBANA_PRIVATE_KEY[_DEMO] → ~/.qbreak/e_api_private_key[_demo].pem（权限必须 600）
        第二暗証：TACHIBANA_SECOND_PASSWORD → 钥匙串 qbreak-tachibana-2nd（デモ也用 -demo 后缀）"""
        sfx, kc = ("_DEMO", "-demo") if demo else ("", "")
        for svc in (f"qbreak-tachibana-authid{kc}", f"qbreak-tachibana-2nd{kc}"):
            _KC_WHY.pop(svc, None)                   # 只用这一次读的原因（常驻进程里以前锁过，不代表现在）
        aid = (os.environ.get(f"TACHIBANA_AUTH_ID{sfx}", "").strip()
               or _read_text(os.environ.get(f"TACHIBANA_AUTH_ID_FILE{sfx}"))
               or _keychain(f"qbreak-tachibana-authid{kc}", "qbreak") or "")
        if not aid:
            raise BrokerError(_kc_missing(
                f"qbreak-tachibana-authid{kc}",
                f"缺少认证 ID：设置环境变量 TACHIBANA_AUTH_ID{sfx}（或 TACHIBANA_AUTH_ID_FILE{sfx} 指向 e_api_authid.txt），"
                f"或存进钥匙串：security add-generic-password -s qbreak-tachibana-authid{kc} -a qbreak -w"))
        kp = Path(os.environ.get(f"TACHIBANA_PRIVATE_KEY{sfx}")
                  or Path.home() / ".qbreak" / f"e_api_private_key{'_demo' if demo else ''}.pem").expanduser()
        if not kp.exists():
            raise BrokerError(f"找不到私钥 {kp}：把「ｅ支店・API 利用設定」登记公钥对应的私钥放在这里（chmod 600），"
                              f"或用环境变量 TACHIBANA_PRIVATE_KEY{sfx} 指定")
        if os.name == "posix" and kp.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise BrokerError(f"私钥 {kp} 的权限太宽（别的用户可读）：chmod 600 {kp}")
        env_sec = os.environ.get(f"TACHIBANA_SECOND_PASSWORD{sfx}") or ""
        sec = env_sec or _keychain(f"qbreak-tachibana-2nd{kc}", "qbreak") or ""
        return cls(aid, kp.read_bytes(), sec, "" if sec else _kc_missing(f"qbreak-tachibana-2nd{kc}", ""),
                   "env" if env_sec else ("keychain" if sec else ""))


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


def _connect_v4(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, *a, **kw):
    """只用 IPv4 连接（立花：10005 = 只能用 IPv4；Mac 有 IPv6 时默认可能先走 IPv6）。主机名照旧（TLS 的证书核对用主机名）。"""
    host, port = address[0], address[1]
    err: OSError | None = None
    for af, st, proto, _, sa in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        try:
            return socket.create_connection(sa, timeout, source_address)
        except OSError as e:
            err = e
    raise err or OSError(f"{host} 没有 IPv4 地址")


class _V4HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._create_connection = _connect_v4


class _V4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        kw = {"context": self._context}
        if getattr(self, "_check_hostname", None) is not None:        # 旧版 Python 的参数（3.12 起没有）
            kw["check_hostname"] = self._check_hostname
        return self.do_open(_V4HTTPSConnection, req, **kw)


class HttpTransport:
    """立花 API：JSON 请求。POST（body = JSON）或 GET（URL?{JSON}，URL 编码）；应答为 Shift_JIS（按 cp932 解码）。
    这里只发一次，不重试 —— 重试策略由调用方按请求种类决定（发单类绝不自动重发）。
    ipv4=True（或环境变量 QBREAK_TACHIBANA_IPV4=1）：只用 IPv4 连接（错误码 10005 的对策）。"""

    def __init__(self, timeout: float = 15.0, method: str = "POST", ipv4: bool | None = None):
        self.timeout = timeout
        self.method = method.upper()
        self.ipv4 = (os.environ.get("QBREAK_TACHIBANA_IPV4", "").strip() == "1") if ipv4 is None else bool(ipv4)
        self._open = urllib.request.build_opener(_V4HTTPSHandler()).open if self.ipv4 else urllib.request.urlopen

    def get_json(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        if self.method == "POST":
            req = urllib.request.Request(url, data=body.encode("ascii"), method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": "qbreak/2.2"})
        else:
            req = urllib.request.Request(f"{url}?{urllib.parse.quote(body, safe='')}",
                                         headers={"User-Agent": "qbreak/2.2"})
        with self._open(req, timeout=self.timeout) as r:   # noqa: S310
            raw = r.read().decode("cp932", errors="replace")
        return json.loads(raw)


def not_sent(e: BaseException) -> bool:
    """这个网络错误能确定请求**没发到**服务器吗：DNS 解析失败 / 连接被拒 / TLS 握手失败 / 没有路由（urllib 把连接与发送阶段的错误
    包成 URLError）。超时、连接中途断开、应答读不了 / 解析不了 → False（请求可能已到达，状态不明）。"""
    r = e.reason if isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError) else None
    if r is None:
        return False
    if isinstance(r, (socket.gaierror, ConnectionRefusedError, ssl.SSLError)):
        return True
    if isinstance(r, OSError) and not isinstance(r, (TimeoutError, socket.timeout)) \
            and r.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL, errno.ENETDOWN):
        return True
    return False


class FakeTransport:
    """测试用：按 CLMID 返回预设响应，并记录所有发出的 payload。"""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.sent: list[tuple[str, dict]] = []
        self.fail_next: str | None = None
        self.fail_with: BaseException | None = None     # fail_next 时抛这个（默认 ConnectionError：可能已到达 → 状态不明）

    def get_json(self, url: str, payload: dict) -> dict:
        self.sent.append((url, dict(payload)))
        clm = payload.get("sCLMID", "")
        if self.fail_next == clm:
            self.fail_next, exc, self.fail_with = None, self.fail_with, None
            raise exc or ConnectionError(f"模拟网络错误 {clm}")   # 网络层的错误（不是服务器应答的业务错误）
        r = self.responses.get(clm)
        if callable(r):
            return r(payload)
        if r is None:
            return {"p_errno": "0", "sResultCode": "0", "sCLMID": clm}
        return dict(r)


def arm_block_text(demo: bool = False) -> str:
    """没解锁发单时单子的说明（TA-15）。ARM 不会自动清空（每天全自动本来就要它一直在）：过了上线门槛、你在对话里明确说之后才建；
    要停用 = 删掉它或建 HALT。本番和デモ看同一个 ARM 文件：デモ的发单检查（probe --demo --order-test）自己不看 ARM，
    执行器的デモ账本（live-u --demo）照旧要 ARM。"""
    st = paths.arm_state()
    head = ("未 ARM：数据目录的 ARM 文件在，但内容不是 ARMED（适配器只认内容 ARMED）"
            if st == "bad" else "未 ARM：数据目录没有 ARM 文件（内容 ARMED），也没设 QBREAK_ARM=ARMED")
    tail = "（过了上线门槛、你在对话里明确说之后才建；要停用 = 删掉它或建 HALT）"
    if demo:
        tail += "；デモ账本的执行器也看同一个 ARM（probe --demo --order-test 自己不看 ARM）"
    return head + tail


# ══════════════════════════ 券商实现 ══════════════════════════
class TachibanaBroker(BaseBroker):
    market = "JP"

    def __init__(self, transport: Transport | None = None, spec: TachibanaSpec | None = None,
                 creds: Credentials | None = None, demo: bool = False,
                 require_arm: bool = True, dry_run: bool = False,
                 limit_buffer_pct: float = 0.5, confirm_timeout_s: float = 20.0,
                 max_order_value: float = 300_000, check_tradable: bool = True):
        self.spec = spec or TachibanaSpec.load()
        self.tr = transport or HttpTransport(method=self.spec.http_method, ipv4=True if self.spec.force_ipv4 else None)
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
        self.doc_update = ""                   # 交付書面的更新预定日（登录应答告知；C-04）
        self.check_tradable = check_tradable   # 买单前查立花銘柄マスタ（qbreak/tradable.py）；只有离线测试才关
        self._master: dict[str, dict] | None = None
        self._master_day = ""
        self._unit_fail = ""                   # 为一手取マスタ失败的日子（这个进程里那天不再试）
        self._last_err = ("", "", "")          # 最近一次业务错误（p_errno, sResultCode, 原文）：判断第二暗証类的拒单用
        self._auth_bad = ""                    # 有单因第二暗証 / 认证被拒 → 后面的单都不发（OPS-12）；第二暗証来自钥匙串时还记进
        #                                        数据目录 state/（second_pw_bad*.json）：之后的运行（08:35 / 09:05 / 面板）也不再发，
        #                                        直到你重新存了钥匙串（条目的修改时刻变了）→ 再试一次（连错几次会锁取引暗証）

    # ── OPS-12：第二暗証被拒的记录（跨运行）──
    def _pw_bad_file(self) -> Path:
        return paths.state_dir() / f"second_pw_bad{'_demo' if self.demo else ''}.json"

    def _kc_service(self) -> str:
        return f"qbreak-tachibana-2nd{'-demo' if self.demo else ''}"

    def _note_pw_bad(self) -> None:
        """第二暗証来自钥匙串时记下（at、钥匙串条目的修改时刻）：之后的运行不再用同一个值发单。环境变量 / 直接给的 → 只在这次运行里挡。"""
        if getattr(self.creds, "second_src", "") != "keychain":
            return
        try:
            atomic_write_text(self._pw_bad_file(), json.dumps(
                {"at": dt.datetime.now(JST).isoformat(timespec="seconds"), "mdat": keychain_mdat(self._kc_service())}))
        except OSError as e:
            log.warning("第二暗証被拒的记录没写成：%s", e)

    def pw_bad(self) -> str:
        """之前的运行里第二暗証被拒、钥匙串还没重新存 → 挡单的原因；否则 ""（重新存过 / 改用环境变量 → 删掉记录，再试一次）。"""
        f = self._pw_bad_file()
        if not f.exists():
            return ""
        rec = read_json(f, {}) or {}
        src = getattr(self.creds, "second_src", "")
        now_m = keychain_mdat(self._kc_service()) if src == "keychain" else ""
        if src == "env" or (src == "keychain" and now_m and now_m != str(rec.get("mdat") or "")):
            try:
                f.unlink()
            except OSError:
                pass
            log.info("第二暗証：钥匙串重新存过 / 改用环境变量 → 再试一次")
            return ""
        return (f"第二暗証番号上次被拒（{str(rec.get('at') or '')[:16].replace('T', ' ')}）：之后不再发单（连错几次会锁取引暗証）。"
                "修好钥匙串 qbreak-tachibana-2nd（终端：security add-generic-password -U -s qbreak-tachibana-2nd -a qbreak -w，"
                "回车后输入）之后自动恢复")

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

    def explain(self, errno_: str = "", rc: str = "", text: str = "") -> str:
        """错误码对照表（C-15）：p_errno / sResultCode → 「原因：要做什么」；表里没有的按原文里的关键词找；都没有 → ""（只显示原文）。"""
        s = self.spec
        e, r = str(errno_ or "").strip(), str(rc or "").strip()
        if e and e != "0" and e in (s.err_errno or {}):
            return str(s.err_errno[e])
        if r and r != s.ok_result and r in (s.err_result or {}):
            return str(s.err_result[r])
        for w, why in (s.err_words or {}).items():
            if w and w in str(text or ""):
                return str(why)
        return ""

    def is_auth_error(self, rc: str = "", text: str = "") -> bool:
        """发单被拒的原因是第二暗証 / 认证类吗（OPS-12：这次运行后面的单都不发，避免连着错）。"""
        s = self.spec
        codes = {c.strip() for c in str(s.err_auth_codes or "").split(",") if c.strip()}
        words = [w.strip() for w in str(s.err_auth_words or "").split(",") if w.strip()]
        return str(rc or "").strip() in codes or any(w in str(text or "") for w in words)

    def _check(self, clmid: str, res: dict) -> None:
        s = self.spec
        en = str(res.get(s.key_errno, "0"))
        if en != "0":
            txt = str(res.get(s.key_err, ""))
            why = self.explain(en, "", txt)
            self._last_err = (en, "", txt)
            raise BrokerError(f"{clmid} 失败 {s.key_errno}={en} {txt}" + (f"（{why}）" if why else ""))
        rc = str(res.get(s.key_result, s.ok_result))
        if rc != s.ok_result:
            txt = str(res.get(s.key_result_text, ""))
            why = self.explain("", rc, txt)
            self._last_err = ("", rc, txt)
            raise BrokerError(f"{clmid} 失败 {s.key_result}={rc} {txt}" + (f"（{why}）" if why else ""))

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
            known = self.explain(str(res.get(s.key_errno, "0")), str(res.get(s.key_result, s.ok_result)),
                                 f"{res.get(s.key_err, '')} {res.get(s.key_result_text, '')}")
            raise BrokerError(f"登录失败：{e}。" + ("" if known else          # 对照表认出了原因：就按那条做

                              "请确认：①「ｅ支店・API 利用設定」=利用する ②公钥已登记 ③认证 ID 与环境一致（本番 / デモ 各一套）"
                              "④03:30～05:30 不能登录 ⑤Mac 的时间自动设置（差 30 秒以上会被拒）⑥只用 IPv4（tachibana_spec.json 的 force_ipv4）/ "
                              "登记过固定 IP 的 IP 没变 ⑦e支店网站的パスキー设定 ⑧API 没被停用、版本没过期（看立花的公告）")) from None
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
                              "`bash scripts/liveu.sh probe --demo`（= run.py tachibana-probe --demo）で応答を確認してください")
        self._urls = urls
        self._tax = str(res.get(s.f_tax) or "")
        self.next_release = str(res.get(s.key_next_release) or "").strip()
        self.doc_update = str(res.get(s.key_doc_update) or "").strip()
        self._logged_in = True
        log.info("已登录立花 e支店 API %s（%s）", api_version(base) or "?", "デモ環境" if self.demo else "本番環境")
        today = dt.datetime.now(JST).strftime("%Y%m%d")
        if self.next_release:                  # TA-09：发布日之后也记（旧版本停用之前要更新；提醒的持续在 qbreak/precheck.py）
            log.warning("立花通知：API 新版本的发布日 %s（%s）—— 代码现在用 %s；请查看仕様变更，必要时更新代码 / tachibana_spec.json",
                        self.next_release, "还没到" if self.next_release[:8] >= today else "已经过了", api_version(base) or "?")
        if self.doc_update:
            log.warning("立花通知：交付書面的更新预定日 %s —— 更新之后要先在电脑上登录 e支店网站读完新书面，API 才能登录", self.doc_update)

    def logout(self) -> None:
        """登出：只发一次 CLMAuthLogoutRequest 到现在的虚拟 URL（不经 _call：会话已经被切断时 _call 会重新登录再登出，
        而切断多半是别处登录了同一个账户 —— 重新登录会把那边的会话踢掉、再多发一封登录通知邮件）。
        会话已切断（p_errno=2）/ 其他错误 → 当作已经登出（忽略）。"""
        if not self._logged_in:
            return
        s = self.spec
        try:
            url = self._urls.get(s.key_url_request)
            if url:
                res = self._send(url, s.clm_logout, {}, idempotent=False)
                en = str(res.get(s.key_errno, "0"))
                if en == s.errno_session_cut:
                    log.info("登出：会话已经被切断（当作已登出）")
                elif en != "0":
                    log.warning("登出失败（忽略）: p_errno=%s %s", en, str(res.get(s.key_err, ""))[:100])
        except Exception as e:                      # noqa: BLE001
            log.warning("登出失败（忽略）: %s", _no_url(e))
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

    def quote_detail(self, tickers: list[str], strict: bool = False) -> dict[str, dict[str, float]]:
        """批量取行情（1 次最多 120 只）：{票: {price 现在值, open 始値, high, low, prev_close 前日終値}}。
        空值（开盘前 / 还没寄り付き / 休市 / 暂时拒绝时是 ""）不放进结果，不让一只票拖垮整轮。
        strict=True（tachibana-probe 用）：调用失败抛 BrokerError（带原因、不带 URL），不当成「没有行情」。"""
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
                if strict:
                    raise BrokerError(f"取价失败（{type(e).__name__}）：{_no_url(e)}"[:300]) from None
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
            # 开盘前 / 还没寄り付き 时现在值是空的（这不是故障）；取价这一次失败也会走到这里（quote_detail 不抛）——所以不说「休市」
            raise BrokerError(f"{ticker}: 现在值为空（开盘前 / 还没寄り付き / 取价失败 / 该代码没有行情）")
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
        return paths.armed()                         # 环境变量 QBREAK_ARM=ARMED 或 ARM 文件内容是 ARMED（面板 / gate 用同一个判断）

    def _preflight(self, ticker: str, qty: int, notional: float) -> str | None:
        if paths.halt_file().exists():
            return f"存在 HALT 文件 {paths.halt_file()}"
        if qty <= 0:
            return "数量为 0"
        if notional > self.max_order_value:
            return f"单笔金额 {notional:,.0f} > 上限 {self.max_order_value:,.0f}"
        if not self._armed():
            return arm_block_text(self.demo)
        return None

    # ── 立花能不能买（买单前；qbreak/tradable.py）──
    def issue_master(self, force: bool = False) -> dict[str, dict]:
        """立花自己的銘柄マスタ三张 → {代码: 项目}（tradable.merge_master）。一天取一次（同一进程内存 + $QBREAK_HOME/cache/
        tachibana_master.json，只有代码与几个区分，不是密钥）；取不到 → 抛 BrokerError（调用方当作「确认不了」）。"""
        s = self.spec
        today = dt.datetime.now(JST).strftime("%Y-%m-%d")
        env = "demo" if self.demo else "live"
        if not force and self._master is not None and self._master_day == today:
            return self._master
        fp = paths.home() / "cache" / "tachibana_master.json"
        if not force:
            d = read_json(fp, {}) or {}
            if d.get("day") == today and d.get("env") == env and d.get("issues"):
                self._master, self._master_day = dict(d["issues"]), today
                return self._master
        rows = {}
        for clm, key in ((s.clm_issue_mst, s.r_issue_mst), (s.clm_issue_mkt, s.r_issue_mkt), (s.clm_issue_kisei, s.r_issue_kisei)):
            rows[clm] = self._rows(self._call(clm, url_key=s.key_url_master).get(key))
        m = TR.merge_master(rows[s.clm_issue_mst], rows[s.clm_issue_mkt], rows[s.clm_issue_kisei])
        if not m:
            raise BrokerError("立花の銘柄マスタが空（仕様変更？ `bash scripts/liveu.sh probe --demo`（= run.py tachibana-probe --demo）で応答を確認）")
        self._master, self._master_day = m, today
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(fp, json.dumps({"day": today, "env": env, "issues": m}, ensure_ascii=False))
        except OSError as e:                        # 缓存写不进去不影响判断
            log.warning("銘柄マスタ缓存没写成：%s", e)
        log.info("立花銘柄マスタ %d 件（%s）", len(m), today)
        return m

    def tradable_block(self, ticker: str, qty: int | None = None) -> str | None:
        """买单前：立花銘柄マスタ里能不能买（None = 能）。マスタ取不到 → 不买（确认不了就不买）。"""
        try:
            m = self.issue_master()
        except Exception as e:                      # noqa: BLE001
            return f"立花の銘柄マスタ取不到（{type(e).__name__}: {e}）→ 确认不了能不能买，不下买单"[:300]
        code = self._code(ticker)
        return TR.broker_reason(code, m.get(code), dt.datetime.now(JST).date(), qty)

    def has_client_id(self, client_id: str) -> bool:
        return bool(client_id) and client_id in self._sent_ids

    @staticmethod
    def _px(v: float) -> str:
        """注文値段：整数就不带小数点（仕様示例 "201"）；呼値小于 1 円的价位保留小数。"""
        return str(int(round(v))) if abs(v - round(v)) < 1e-9 else f"{v:.1f}"

    def unit(self, ticker: str) -> int | None:
        """立花銘柄マスタ的売買単位（一天取一次，与买单前的检查共用缓存）；不查マスタ（离线测试）/ 取不到 / 没有这只 → None。"""
        today = dt.datetime.now(JST).strftime("%Y-%m-%d")
        if not self.check_tradable or self._unit_fail == today:
            return None
        try:
            u = str((self.issue_master().get(self._code(ticker)) or {}).get("unit") or "")
        except Exception:                           # noqa: BLE001  取不到就不按一手检查（卖单照常；买单另有マスタ检查挡）
            self._unit_fail = today                 # 今天这个进程不再为一手去取（免得每笔卖单都重试几秒）
            return None
        return int(u) if u.isdigit() and int(u) > 0 else None

    def _clamp(self, px: float, prev: float, ticker: str, side: str, on: dt.date, lot: int | None,
               ref: float = 0.0) -> float:
        """盘中指値夹在当天的制限値幅里（C-02：ストップ安附近「现价 −0.5%」会低于下限 → 交易所不受理）：
        卖 = max(px, 前日終値 − 値幅) 向上取呼値；买 = min(px, 前日終値 + 値幅) 向下取呼値。
        刚取到的现价 ref 已经在这个値幅外 → 算出来的値幅不对（基準値段不是前日終値：前一天没成交的ストップ安 = 最終特別気配、
        連続ストップ安后値幅扩大、拆股权利落ち日前日終値没调整）→ 不夹（夹了卖单会挂在现价之上、成交不了），记 warning。"""
        w = price_limit_jp(prev)
        if ref > 0 and not (prev - w <= ref <= prev + w):
            log.warning("%s 现价 %s 不在按前日終値 %s 算的値幅 ±%s 里（基準値段 / 値幅不同）：盘中指値不夹", ticker, ref, prev, w)
            return px
        if side == "SELL" and px < prev - w:
            return round_to_tick(prev - w, ticker, "SELL", on, lot)
        if side == "BUY" and px > prev + w:
            return round_to_tick(prev + w, ticker, "BUY", on, lot)
        return px

    # ── 发单 ──
    def _place(self, ticker: str, side: str, qty: int, limit: float | None,
               client_id: str, condition: str | None = None,
               stop_trigger: float | None = None) -> Order:
        s = self.spec
        auction = (condition or s.cond_normal) in (s.cond_opening, s.cond_closing)
        on, lot = _order_day(auction), self.unit(ticker)      # 呼値表按执行日（2027-03-01 起分表）与売買単位（一手 1 口的 ETF 用 O 表）
        ref = prev = 0.0
        if not stop_trigger:
            q = self.quote_detail([ticker]).get(ticker) or {}  # 取价失败 / 空值（开盘前 / 休市）→ {}：不让一次取价拖垮发单
            ref, prev = float(q.get("price") or 0), float(q.get("prev_close") or 0)
        odd = 0
        if side == "SELL" and lot and lot > 1 and int(qty) % lot:
            odd = int(qty) % lot                         # C-14：单元未满株不能用普通注文卖 → 整数手照常下，零股留给人在立花网站卖
        want, qty = int(qty), int(qty) - odd
        if stop_trigger:
            px = 0.0                                 # 只下逆指値：通常部分「指定なし」，触发后成行
        elif limit:
            px = round_to_tick(limit, ticker, side, on, lot)
        elif auction:
            px = 0.0                                 # 寄付 / 引け 不给价格 = 成行：在集合竞价里按开盘价成交（回测的「次日开盘成交」）
        else:                                        # 盘中不给价格：按现在值 ± 缓冲挂指値（可成交的限价，不用成行）
            px = ref * (1 + (1 if side == "BUY" else -1) * self.limit_buffer_pct / 100) if ref else 0.0
            px = round_to_tick(px, ticker, side, on, lot) if px else 0.0
        if px and not auction and not stop_trigger and prev > 0:
            px = self._clamp(px, prev, ticker, side, on, lot, ref)    # B9：盘中指値夹在値幅里（前日終値取不到 / 现价在値幅外 → 不夹）
        trig = round_to_tick(stop_trigger, ticker, side, on, lot) if stop_trigger else 0.0
        notional = (px or ref or trig) * qty
        odd_txt = (f"{ticker} 有 {odd} 股不足一手（売買単位 {lot}）：单元未满株不能用 API 的普通注文卖 → 在立花网站卖"
                   f"（端株手续费 0.55%），卖完在 Mac 对话里说一声登记") if odd else ""

        blocked = None
        if side == "SELL" and odd and qty <= 0:
            blocked = odd_txt
        blocked = blocked or self._preflight(ticker, qty, notional)
        if not blocked and self._auth_bad and not self.dry_run:
            blocked = self._auth_bad                     # OPS-12：这次运行里已经有单因第二暗証 / 认证被拒 → 不再连着发
        if not blocked and side == "BUY" and self.check_tradable:
            blocked = self.tradable_block(ticker, qty)
        if not blocked and side == "BUY" and not stop_trigger and not (px or ref):
            blocked = "成行买单估不出金额（取不到现在值），单笔上限无法检查 → 拒绝；请给指値"
        if not blocked and side == "SELL" and not stop_trigger and not auction and not px:
            blocked = "取不到现价，没下（不发成行单）"     # TA-12：盘中卖单不变成成行（执行器：手动指令一会儿再试；live_unified.NO_QUOTE）
        if not blocked and not self.dry_run:
            if self.creds is None:
                try:
                    self.creds = Credentials.from_env(demo=self.demo)
                except BrokerError as e:
                    blocked = str(e)
            if self.creds is not None and not self.creds.second_password:
                blocked = (self.creds.second_why or "缺少第二暗証番号（所有注文必填）：环境变量 TACHIBANA_SECOND_PASSWORD "
                           "或钥匙串 qbreak-tachibana-2nd")
            if not blocked and self.creds is not None:
                self._auth_bad = self.pw_bad()           # OPS-12：之前的运行里第二暗証被拒、还没重新存 → 不再用同一个值发
                blocked = self._auth_bad or None
        if blocked:
            log.warning("拒绝发单 %s %s x%d：%s", side, ticker, want, blocked)
            return Order(ticker, side, want, px, _now(), "BLOCKED", client_id=client_id, note=blocked,
                         extra={"odd_lot": odd, "lot": lot} if odd and qty <= 0 else {})
        if self.has_client_id(client_id):
            return Order(ticker, side, qty, px, _now(), "REJECTED",
                         client_id=client_id, note="重复的 client_id（幂等拦截）")
        if not self.dry_run:
            try:
                self.login()                             # 课税区分（sZyoutoekiKazeiC）取登录应答里的账户值
            except Exception as e:                        # noqa: BLE001  登录没成 = 注文请求根本没发出 → BLOCKED（下一次运行可以安全重试）
                log.error("登录失败，未发单 %s %s x%d: %s", side, ticker, qty, _no_url(e))
                return Order(ticker, side, want, px, _now(), "BLOCKED", client_id=client_id,
                             note=f"登录失败，没发单（{type(e).__name__}）：{_no_url(e)}"[:300])

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

        self._last_err = ("", "", "")
        try:
            res = self._call(s.clm_new_order, idempotent=False,
                             **{**fields, s.f_second_pw: self.creds.second_password})
        except BrokerError as e:                          # 服务器应答了错误（p_errno / sResultCode ≠ 0，例如余力不足）：确定没受理
            log.error("发单被拒 %s: %s", fields, e)
            en, rc, txt = self._last_err
            if self.is_auth_error(rc, txt or str(e)):     # OPS-12：第二暗証 / 认证类被拒 → 这次运行后面的单都不发
                self._auth_bad = ("第二暗証番号不对（或认证类被拒），这次运行后面的单都没发：先修好钥匙串 qbreak-tachibana-2nd"
                                  "（终端：security add-generic-password -U -s qbreak-tachibana-2nd -a qbreak -w，回车后输入）")
                self._note_pw_bad()                       # 之后的运行也不再发（直到重新存了钥匙串）
            return Order(ticker, side, qty, px, _now(), "REJECTED",
                         client_id=client_id, note=str(e)[:300])
        except Exception as e:                            # noqa: BLE001
            if not_sent(e):                               # DNS / 连接被拒 / TLS 握手失败：请求根本没发出 → BLOCKED（可以安全重试）
                log.error("没连上，未发单 %s %s x%d: %s", side, ticker, qty, _no_url(e))
                return Order(ticker, side, want, px, _now(), "BLOCKED", client_id=client_id,
                             note=f"没连上立花，没发单（{type(e).__name__}）：{_no_url(e)}"[:300])
            # 超时 / 连接中途断开 / 应答解析失败：可能已被受理 → 状态不明，绝不自动重发
            log.error("发单结果不明 %s: %s", fields, _no_url(e))
            return Order(ticker, side, qty, px, _now(), "ERROR",
                         client_id=client_id, note=f"状态不明（{type(e).__name__}）：{_no_url(e)}"[:300])

        order_no, day = str(res.get(s.f_order_no) or "").strip(), str(res.get(s.f_order_date) or "").strip()
        self._sent_ids[client_id] = (order_no, day)
        if not order_no or not day:                       # M3：受理应答里没有注文番号 / 営業日 → 查不了成交、撤不了 → 状态不明
            log.error("受理应答缺注文番号 / 営業日 %s", fields)
            return Order(ticker, side, qty, px, _now(), "ERROR", client_id=client_id, broker_id=order_no,
                         extra={"order_date": day},
                         note="状态不明：受理应答里没有注文番号 / 営業日（可能已被受理）→ 去立花的注文一覧核对后登记")
        o = Order(ticker, side, qty, px, _now(), "SENT", client_id=client_id,
                  broker_id=order_no, extra={"order_date": day})
        if odd:
            o.extra["odd_lot"], o.extra["lot"] = odd, lot    # 执行器的 odd_lots 记录按立花的売買単位（与引擎的一手可能不同）
        if (condition or s.cond_normal) == s.cond_opening or stop_trigger:
            o.note = "寄付注文を受付（次の寄付で約定）" if not stop_trigger else "逆指値を受付（条件到達まで市場に出ない）"
            if odd_txt:
                o.note += f"；★ {odd_txt}"
            return o
        o = self._confirm(o)
        if odd_txt:
            o.note = f"{o.note}；★ {odd_txt}" if o.note else f"★ {odd_txt}"
        return o

    def _confirm(self, o: Order) -> Order:
        """発注 → 約定確認。数量が合わなければ必ず声を上げる（黙って進むのが一番高くつく）。
        终态（被拒 / 失效 / 取消完了：spec 的 status_*）→ 马上停止轮询，单记 REJECTED / EXPIRED（取消完了也记 EXPIRED：不会再成交），
        note 带立花的状态名称；已经成交的部分照记（filled_qty，第二天的对账按它记账）。"""
        deadline = _mono() + self.confirm_timeout_s
        final = ""
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
            if r.get("final") in ("REJECTED", "EXPIRED", "CANCELLED"):
                final = r["final"]
                o.extra["broker_status_text"] = r.get("status") or self.spec.status_names.get(r["status_code"], "")
                break
        if final and o.filled_qty < o.qty:
            o.status = "REJECTED" if final == "REJECTED" else "EXPIRED"
            name = o.extra.get("broker_status_text") or "终态"
            o.note = (f"立花：{name}（sOrderStatusCode={o.extra.get('broker_status')}）"
                      + (f"；已成交 {o.filled_qty}/{o.qty}，其余不会再成交" if o.filled_qty else "：没成交，不会再成交"))
            log.warning("★ %s %s x%d %s", o.side, o.ticker, o.qty, o.note)
            return o
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
        code = str(r.get(s.r_status_code) or "").strip()
        return {"filled_qty": qty, "avg_px": px if qty > 0 else 0.0,
                "status_code": code, "status": str(r.get(s.r_status) or ""), "final": self.final_state(code)}

    def final_state(self, code: str) -> str:
        """sOrderStatusCode → 终态："FILLED"（全部約定）/ "REJECTED"（受付エラー等）/ "EXPIRED"（失効）/ "CANCELLED"（取消完了）；
        还会成交 / 不认识 → ""（代码表在 TachibanaSpec 的 status_*，デモ核对后可改）。"""
        s, c = self.spec, str(code or "").strip()

        def has(v: str) -> bool:
            return bool(c) and c in {x.strip() for x in str(v or "").split(",")}
        if has(s.status_filled):
            return "FILLED"
        if has(s.status_rejected):
            return "REJECTED"
        if has(s.status_cancelled):
            return "CANCELLED"
        if has(s.status_expired):
            return "EXPIRED"
        return ""

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

    def open_orders(self, strict: bool = False) -> list[dict]:
        """注文一覧（只读）。默认读不到 → []；strict=True（tachibana-probe 用）：调用失败抛 BrokerError（带原因、不带 URL）。"""
        try:
            return self._rows(self._call(self.spec.clm_order_list).get(self.spec.r_order_list))
        except Exception as e:                            # noqa: BLE001
            if strict:
                raise BrokerError(f"读取注文一覧失败（{type(e).__name__}）：{_no_url(e)}"[:300]) from None
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


def _now_dt() -> dt.datetime:
    return dt.datetime.now(JST)


def _order_day(auction: bool) -> dt.date:
    """这笔单在哪个交易日执行（呼値表按它选：2027-03-01 起分表）：今天不是交易日、或寄付 / 引け单在 15:30 以后下（受理翌営業日）
    → 下一个交易日；否则今天。"""
    now = _now_dt()
    d = now.date()
    if not is_trading_day(d) or (auction and now.time() >= dt.time(15, 30)):
        return next_trading_day(d)
    return d


def _no_url(e) -> str:
    """异常文字里的 URL（虚拟 URL 带会话）换成「<URL>」：只留原因。"""
    return re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", "<URL>", str(e))


def api_version(base: str) -> str:
    """base URL 的版本段（例如 "e_api_v4r10"；公开仕様書上的路径，不是密钥）：probe 结果文件记它，上线门槛核对版本变了没有。"""
    seg = [x for x in urllib.parse.urlsplit(str(base or "")).path.split("/") if x]
    return seg[-1] if seg else ""


def _mono() -> float:
    return time.monotonic()


def _sleep(s: float) -> None:
    time.sleep(s)
