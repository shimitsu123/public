"""panel.py — 操作面板：Mac 本机 + 手机（2026-10-06 用户：「当持仓的时候可以在画面上点击卖出后 第二天或者当天就可以在立花自动交易
可以手动调节当前持仓股票百分比 持仓股票的时候要写出为什么持仓这个股票的原因等等 现在趋势如何等等」；同日：「做一个可以在手机上操作的页面」）。

两个只在本机（127.0.0.1）监听的端口（Mac 的 LaunchAgent com.qbreak.panel：scripts/install_launchd_panel.sh；或 bash scripts/liveu.sh panel）：
  8765 本机：http://127.0.0.1:8765/ —— 只有这台 Mac 能打开；写操作要令牌（数据目录 panel_token，0600）
  8766 手机：Tailscale Serve（bash scripts/liveu.sh phone on）把它放到 https://<Mac>.<tailnet>.ts.net/，只有你 Tailscale 里的设备能连；
       这一路要「你本人」（qbreak/panel_phone.py）：按 Tailscale 账户登录（2026-10-07 起；只认这台 Mac 登录的账户，经 Serve 的路径密钥来的才算）
       或已配对的设备（配对码只显示在 Mac 屏幕上；设备 cookie）；写操作都要 CSRF 令牌
页面（手机优先的版面；两边一样）：
  GET  /?book=paper|tachibana   账本：持仓（为什么持有、现在趋势、约占权益、K 线）、核心 ETF（K 线）、建议的股票（规则的候选 + 「买入…」）、
                                手动指令、不买回、停止下单（HALT）；每只持仓有「卖出全部」「调仓…」（股数 / 金额 / 占权益 %，可加可减；
                                调仓条按一次最少能买卖的股数（1 个单元 = 100 股）分格；底部弹出确认），
                                核心 ETF 有「闲置资金比例」，指令有「撤回」；K 线：同花顺式（红涨空心、绿跌实心）+ 5 / 10 / 20 / 30 日均价
                                + 买入价 / 止损线（2026-10-06 用户：「趋势是做一个和图中一样的日周月的块块和线 方便看的」）；
                                每张图上边沿「日K / 周K / 月K」、下边沿「量 / MACD / DMI」各自切换，图下的说明用日常的话
                                （2026-10-07 用户：「K线的日周月button 要显示在每个K线的上面边沿方便看 / 量 MACD DMI 显示在每个K线的下面 /
                                K线解释换成通俗易懂的说法 横展开 / 现在持有的股票可以进行调仓 按照最小一次成交股数分割调仓线」）
  GET  /api/chart?book=…&t=…    一只票的 K 线（执行器写的 out/charts_<账本>.json；打开 / 滑到那只票时才取；手机端口要你本人）
  GET  /api/quotes?book=…       持有的个股与核心 ETF 的现价（Yahoo 1 分钟线，约晚 20 分钟；盘中 60 秒缓存；只展示；手机端口要你本人）
  GET  /api/trade_room?book=…   今天还能买几次 / 卖几次（qbreak/trade_room.py：时段、差金決済、执行器规则、钱、闸门；不取价、只读；手机端口要你本人）
  GET  /api/intraday?book=…     盘中观测：规则的暂定买卖点（qbreak/intraday_watch.py 的结果文件；不取价、只读；手机端口要你本人）。
                                面板里的一个线程（serve 的 intraday）交易日 08:55〜11:35、12:25〜16:30 每 5 分钟另起进程算一次（取价不在请求里做）
  POST /api/request             写一条手动指令（qbreak/manual_orders.py；与 run.py manual 相同的检查）
  POST /api/halt                建 HALT（只能建、不能解除；解除只在 Mac 上、用户明确说）
  本机才有：POST /api/pair/new（生成配对码）、/api/device/revoke（取消一台设备）；手机才有：/api/pair、/api/unpair（退出这台设备）
按钮只写指令：下单永远是执行器（HALT / ARM / 持仓核对 / 单笔上限 / 资格检查照常）。什么时候下单（qbreak/manual_orders.py；
2026-10-07 用户：「当天买入卖出的话在交易时间段就直接进行买入卖出 在交易时间之前的话就等交易时间的时候进行交易」）：
  盘中（09:00〜11:30、12:30〜15:25）→ 面板马上叫执行器跑 bash scripts/liveu.sh run --broker … --phase now（同一个账本最多 1 分钟一次）；
  交易日 07:45〜08:55、今天早上的决策已经做了、有新的卖出 / 调仓往下 / 撤回 → 叫一次重试（--retry，最多 3 分钟一次）→ 今天开盘的寄付单；
  开盘前的买入 / 加仓 → 09:00 开盘后由 --phase now 下；收盘后点的 → 下一个交易日 07:40 的运行。
  模拟账户今天早上的运行没完成（Mac 07:40 睡着等）、没有执行器在跑 → 面板补跑一次（一天最多 3 次；立花不补跑；2026-10-14 G9）。
安全：只绑 127.0.0.1；Host 头：本机端口只接受 127.0.0.1 / localhost，手机端口只接受 *.ts.net（挡 DNS rebinding）；写操作要
  ① 令牌（本机）/ 设备 cookie + CSRF 令牌（手机）② 自定义头（跨站表单发不出）③ Origin（有的话）必须是这个页面自己
  ④ application/json、≤ 4 KB ⑤ 每分钟最多 30 次（配对 10 次）。不读立花的认证信息、不连立花、不下单；页面禁止被嵌入。
代码更新（git pull）之后面板自己退出，LaunchAgent 用新代码重启。
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import hashlib
import json
import logging
import math
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import core_exit as CX
from . import dip_stats as DS
from . import intraday_watch as IW
from . import kline as KL
from . import live_ops as LO
from . import manual_orders as MO
from . import names as NM
from . import panel_phone as PP
from . import paths
from . import suggest as SG
from . import trade_room as TR
from . import watch_prob as WP
from .calendar_jp import JST, is_trading_day, now_jst
from .fees import BROKERS as _BROKERS, DEFAULT_BROKER as _DEFAULT_BROKER
from .tick import round_to_tick
from .utils import read_json, setup_logging

log = setup_logging("panel")

BOOKS = {"paper": "模拟账户", "tachibana": "立花（本番）", "tachibana_demo": "立花デモ", "tachibana_dryrun": "立花 dry-run（只读）"}
READONLY = {"tachibana_dryrun"}            # dry-run 的账本：只看（〔77〕C UX-15），面板不写指令
MAX_BODY = 4096
TRIGGER_FROM, TRIGGER_UNTIL = dt.time(7, 45), MO.CUTOFF   # 开盘前的重试：07:45〜08:55（与寄付截止对齐；2026-10-14 G20：以前到 08:50）
TRIGGER_GAP_S = 180                     # 开盘前的重试：同一个账本最多 3 分钟一次
CATCHUP_FROM = dt.time(7, 45)           # 模拟账户补跑（今天早上的运行没完成；G9）：交易日这之后、15:30 之前
CATCHUP_GRACE_S = 120                   # 连续这么久都「没完成、没有执行器在跑」才补跑（Mac 醒来时先让 launchd 拉起错过的 07:40）
CATCHUP_GAP_S = 1200                    # 补跑之间至少隔 20 分钟
CATCHUP_MAX = 3                         # 一天最多补跑几次
NOW_GAP_S = 60                          # 盘中（--phase now）：同一个账本最多 1 分钟一次
OPEN_GAP_S = 300                        # 模拟账户的开盘撮合（--phase open；D3，2026-10-15）：1 分钟线还没到时最多 5 分钟再叫一次
FAIL_GAP_MAX_S = 900                    # 盘中执行器失败后的退避：NOW_GAP_S × 2^连续失败次数，最多 15 分钟
FAIL_PAUSE_N = 3                        # 同一天连续失败几次 → 当天这个账本暂停自动叫执行器（新的手动指令 / 第二天恢复）
TOKEN_FILE = "panel_token"
WATCH = ("panel.py", "panel_phone.py", "manual_orders.py", "money_view.py", "broker_snapshot.py", "tax_ytd.py", "live_gate.py", "holding_view.py", "kline.py", "suggest.py", "watch_prob.py", "core_exit.py",
         "idle_cash.py", "dip_stats.py", "run_status.py", "precheck.py", "calendar_jp.py",
         "paths.py", "live_unified.py",         # 默认账本 / ARM 判定（paths）、数据依赖的提醒文字（live_unified）
         "live_ops.py", "data.py",              # 「预计不会下单」与执行器同一个判断（live_ops）、盘中现价（data）：2026-10-15 复核补上
         "trade_room.py",                       # 今天还能买几次 / 卖几次（D6；2026-10-15）
         "intraday_watch.py")                   # 盘中观测的卡片 / 时段（2026-10-16）


def token() -> str:
    """面板令牌：数据目录 panel_token（没有就生成，0600）。只给本机页面用；不是券商的密钥。"""
    p = paths.home() / TOKEN_FILE
    if p.exists():
        t = p.read_text(encoding="utf-8").strip()
        if len(t) >= 32:
            return t
    t = secrets.token_urlsafe(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (t + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(p, 0o600)
    return t


def books() -> list[str]:
    """有账本的执行器（模拟账户总列出来；装了立花本番时立花也总列出来，账本还没有也一样）。"""
    dft = paths.default_book()
    return [t for t in BOOKS if t in ("paper", dft) or (paths.state_dir() / f"live_unified_{t}.json").exists()]


def _load(tag: str) -> tuple[dict, dict]:
    return (read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {},
            read_json(paths.out_dir() / f"live_unified_{tag}.json", {}) or {})


def _yen(v) -> str:
    try:
        return f"¥{float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


# ───────────────────────── 页面（手机优先；Mac 上一样用） ─────────────────────────
STATIC_DIR = Path(__file__).resolve().parent / "static"     # 页面的 JS（浏览器原生 ES 模块）与 CSS（2026-10-12 从 Python 字符串搬出来）
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
JS_MODULES = ("net", "core", "conn", "trade", "kline", "quotes", "room", "intraday", "app")   # main.js 按这个顺序引入；pair.js 是配对页的


def _static_files() -> dict[str, bytes]:
    """磁盘上的 static/（原样）。面板只在启动时读一次（STATIC）。"""
    return {f.name: f.read_bytes() for f in sorted(STATIC_DIR.iterdir()) if f.suffix in STATIC_TYPES}


_STATIC_RAW = _static_files()
ASSET_V = hashlib.sha1(b"".join(_STATIC_RAW.values())).hexdigest()[:10]   # 引用时加 ?v=（代码更新后不用旧的）
BOOT_ID = secrets.token_hex(4)                              # 这个面板进程（重启 / 平滑重启后变）：/api/status 带着
_IMPORT_RE = re.compile(r"""(\b(?:from|import)\s*)(['"])\./([A-Za-z0-9_]+\.js)\2""")


def _versioned(name: str, raw: bytes) -> bytes:
    """模块里的 import './x.js' → './x.js?v=ASSET_V'（2026-10-15「网页app经常卡住」：以前子模块不带版本 → service worker /
    浏览器缓存里新旧模块混在一起，一个 import 对不上整页的脚本都不跑，只剩页头和标签栏）。"""
    if not name.endswith(".js"):
        return raw
    s = raw.decode("utf-8")
    return _IMPORT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}./{m.group(3)}?v={ASSET_V}{m.group(2)}", s).encode("utf-8")


# 启动时读一次、之后只给这一份（与 ASSET_V 是同一批字节；2026-10-15：以前每次请求现读磁盘 → git pull 之后、面板重启之前，
# 旧页面配上新的 JS）。带 ?v= 的：只给版本对的（不对 → 404，页面的 boot.js 重新载入拿新页面），可以长期缓存；gzip 预先压好。
STATIC = {n: _versioned(n, b) for n, b in _STATIC_RAW.items()}
STATIC_GZ = {n: gzip.compress(b, 9) for n, b in STATIC.items()}
# boot.js 直接写进页面（2026-10-15 复核「网页app经常卡住」：以前是 /static/boot.js?v= —— 页面是旧进程给的、它向新进程要 → 版本不对 404；
# 或网络在页面到了之后断了 → 接手的脚本自己也没载入，页面照旧卡死）。CSP 不开 'unsafe-inline'，只放行这一段的 sha256。
BOOT_JS = STATIC["boot.js"].decode("utf-8")
assert "</script" not in BOOT_JS.lower()
BOOT_SHA = "sha256-" + base64.b64encode(hashlib.sha256(BOOT_JS.encode("utf-8")).digest()).decode("ascii")
_CSS = (STATIC_DIR / "panel.css").read_text(encoding="utf-8")
def js_plain(name: str) -> str:
    """一个模块去掉 import 行与 export 前缀 → 普通脚本（测试在 node 里拼起来跑用）。"""
    src = (STATIC_DIR / f"{name}.js").read_text(encoding="utf-8")
    return "\n".join(("" if ln.startswith("import ") else ln[7:] if ln.startswith("export ") else ln) for ln in src.split("\n"))


_NET_JS = js_plain("net")
_JS = "\n".join(js_plain(m) for m in JS_MODULES)          # 全部模块拼成的普通脚本（测试用：取函数、在 node 里跑；浏览器用的是 /static/ 的模块）





def _head(title: str) -> str:
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name='theme-color' content='#f2f2f7' media='(prefers-color-scheme: light)'>"
            "<meta name='theme-color' content='#0f0f11' media='(prefers-color-scheme: dark)'>"
            "<meta name='apple-mobile-web-app-capable' content='yes'><meta name='mobile-web-app-capable' content='yes'>"
            "<meta name='apple-mobile-web-app-title' content='qbreak'><meta name='format-detection' content='telephone=no'>"
            "<link rel='manifest' href='/manifest.webmanifest'><link rel='apple-touch-icon' href='/apple-touch-icon.png'>"
            "<link rel='icon' href='/apple-touch-icon.png'>"
            f"<title>{escape(title)}</title><link rel='stylesheet' href='/static/panel.css?v={ASSET_V}'></head>")


def _dialogs(paper: bool, cap: float = MO.CAP_PCT) -> str:
    bd = [("20", "20 个交易日（默认）"), ("5", "5 个交易日"), ("60", "60 个交易日"), ("-1", "一直（直到解除）"), ("0", "不限制")]
    sim = "模拟账户：手动操作后会和云端模拟盘不一致。" if paper else ""
    return ("<dialog id='dlg-sell'><div class='sheet'><h3 id='sell-title'></h3><div id='sell-desc'></div><div id='sell-pl' class='pl' hidden></div>"
            "<fieldset><legend class='muted'>之后不自动买回</legend>"
            + "".join(f"<label><input type='radio' name='bd' value='{v}'{' checked' if v == '20' else ''}> {t}</label>" for v, t in bd)
            + "</fieldset><div class='muted small'>卖出的钱按规则：有新信号就买新票，没有就进闲置资金 ETF。</div>"
            "<div class='row'><button class='btn' data-act='close'>取消</button><button class='btn danger' data-act='sell-go'>确认卖出</button></div>"
            "</div></dialog>"
            "<dialog id='dlg-adj'><div class='sheet'><h3 id='adj-title'></h3><div id='adj-cur' class='muted'></div>"
            "<div style='margin-top:10px'><div class='seg' id='adj-seg' role='group' aria-label='目标的单位'>"
            "<button data-act='adj-unit' data-u='shares' aria-pressed='true' id='adj-u-sh'>股数</button>"
            "<button data-act='adj-unit' data-u='yen' aria-pressed='false'>金额 ¥</button>"
            "<button data-act='adj-unit' data-u='pct' aria-pressed='false'>占权益 %</button></div></div>"
            "<div class='adjrow'><button class='btn' data-act='adj-step' data-d='-1' aria-label='少一个单元'>−</button>"
            "<div class='grow'><input type='number' id='adj-val' inputmode='decimal' min='0' aria-label='目标'><span class='unit' id='adj-unit'>股</span></div>"
            "<button class='btn' data-act='adj-step' data-d='1' aria-label='多一个单元'>＋</button></div>"
            "<div class='lots'><div class='lots-bar' id='adj-bar' aria-hidden='true'></div>"
            "<input type='range' id='adj-range' min='0' max='100' step='100' value='0' aria-label='目标股数（一格 = 一次最少能买卖的股数）'></div>"
            "<div class='lots-lab' id='adj-lab' aria-hidden='true'></div><div class='muted small' id='adj-note'></div>"
            f"<div id='adj-prev'></div><div id='adj-fund'></div><div class='muted small' id='adj-rule'>一次最少 {MO.LOT} 股；最多加到总权益（钱不够从持仓平摊凑）<span id='adj-cap' hidden>{cap:g}</span>。"
            "加仓是你自己的决定（「赢家加仓」研究没有通过）；加仓后成本按股数平均，止损不变。" + sim + "</div>"
            "<div class='row'><button class='btn' data-act='close'>取消</button><button class='btn primary' id='adj-go' data-act='adj-go'>确认</button></div>"
            "</div></dialog>"
            "<dialog id='dlg-buy'><div class='sheet'><h3 id='buy-title'></h3><div id='buy-sig'></div><div id='buy-live' class='small pl'></div>"
            "<div style='margin-top:10px'><div class='seg' id='buy-seg' role='group' aria-label='买多少'>"
            "<button data-act='buy-unit' data-u='rule' aria-pressed='true'>按规则</button>"
            "<button data-act='buy-unit' data-u='shares' aria-pressed='false'>股数</button>"
            "<button data-act='buy-unit' data-u='yen' aria-pressed='false'>金额 ¥</button>"
            "<button data-act='buy-unit' data-u='pct' aria-pressed='false'>占权益 %</button></div></div>"
            "<div class='adjrow' id='buy-row' hidden><button class='btn' data-act='buy-step' data-d='-1' aria-label='少一个单元'>−</button>"
            "<div class='grow'><input type='number' id='buy-val' inputmode='decimal' min='0' aria-label='买多少'><span class='unit' id='buy-unit'>股</span></div>"
            "<button class='btn' data-act='buy-step' data-d='1' aria-label='多一个单元'>＋</button></div>"
            "<input type='range' id='buy-range' class='buyr' min='100' max='100' step='100' value='100' aria-label='买多少股（拖动；一格 = 一个单元）'>"
            f"<div id='buy-prev'></div><div id='buy-fund'></div><div class='muted small'>「按规则」= 规则自己的仓位（总权益 × 25% × 新仓倍数），只是默认值、不是上限；"
            f"可以买到总权益（钱不够从持仓平摊凑）<span id='buy-cap' hidden>{cap:g}</span>。"
            "下单前执行器再查资格、名额、决算前；买入后按规则止损、离场。</div>"
            "<div class='row'><button class='btn' data-act='close'>取消</button><button class='btn primary' id='buy-go' data-act='buy-go'>确认买入</button></div>"
            "</div></dialog>"
            "<dialog id='dlg-ask'><div class='sheet'><h3 id='ask-title'></h3><div id='ask-pl' class='pl' hidden></div><div id='ask-body'></div>"
            "<input type='text' id='ask-input' maxlength='120' hidden>"
            # 另外的选择（撤凑钱的卖单：「只撤卖单」「撤单并恢复按规则」；D2，2026-10-15）：平时不显示
            "<div class='row' id='ask-alts' hidden><button class='btn' id='ask-alt' data-act='ask-alt' hidden></button>"
            "<button class='btn' id='ask-alt2' data-act='ask-alt' hidden></button></div>"
            "<div class='row'><button class='btn' id='ask-no' data-act='close'>取消</button><button class='btn primary' id='ask-ok' data-act='ask-ok'>确定</button></div>"
            "</div></dialog>")


def _phone_card(phone: dict) -> str:
    url, devs = phone.get("url"), phone.get("devices") or []
    H = ["<section class='card' id='phone'><h2>手机</h2>"]
    if url:
        H.append(f"<div>手机地址：<b>{escape(url)}</b><br><span class='muted'>只有你 Tailscale 里的设备能打开（Tailscale Serve；不公开到互联网）</span></div>")
    else:
        H.append("<div class='muted'>手机访问还没打开：在 Mac 的 Claude 对话里说「打开手机操作」（会运行 bash scripts/liveu.sh phone on：用 Tailscale，"
                 "只有你自己的设备能连）</div>")
    ident = phone.get("identity") or {}
    if ident.get("on"):
        H.append(f"<div class='small'>按 Tailscale 账户登录：<b>开</b> —— 用这台 Mac 的 Tailscale 账户（{escape(str(ident.get('owner') or '—'))}）"
                 "登录的手机打开手机地址就能用，不用配对；别的账户 / 带 tag 的设备用下面的配对码（备用）。"
                 "<span class='muted'>改成只用配对：在 Mac 的 Claude 对话里说「手机只用配对」</span></div>")
    elif ident:
        H.append(f"<div class='small muted'>按 Tailscale 账户登录：{'关' if ident.get('off') else '现在不可用'}"
                 f"（{escape(str(ident.get('why') or '—'))}）→ 手机要配对</div>")
    if not phone.get("port"):
        H.append("<div class='neg small'>★ 面板的手机端口没在监听（端口被占用？）：bash scripts/install_launchd_panel.sh 重启面板</div>")
    H.append("<div class='act'><button class='btn primary' data-act='pair-new'>生成配对码</button></div>"
             "<div id='pair-box' hidden><div class='code' id='pair-code'></div><div class='muted' id='pair-exp' style='text-align:center'></div>"
             "<div class='qr'><img id='pair-qr' alt='配对二维码' hidden></div><div class='muted small' id='pair-url'></div></div>"
             "<div class='muted small'>配对码只显示在这台 Mac 的屏幕上（不要拍照发给别人）；10 分钟内有效、只能用一次。</div>")
    H.append(f"<h3 style='margin-top:12px'>已配对的设备（{len(devs)} 台，最多 {PP.MAX_DEVICES} 台）</h3><div class='list'>")
    H += [f"<div class='li'><div class='grow'><b>{escape(d['name'])}</b><div class='muted small'>配对 {escape(str(d.get('created') or '')[:16].replace('T', ' '))}"
          f" · 最近 {escape(str(d.get('seen') or '')[:16].replace('T', ' '))}</div></div>"
          f"<button class='btn sm' data-act='revoke' data-id='{escape(d['id'])}' data-name='{escape(d['name'])}'>取消配对</button></div>"
          for d in devs] or ["<div class='li muted'>还没有</div>"]
    H.append("</div></section>")
    return "".join(H)


TF_LABEL = (("D", "日K"), ("W", "周K"), ("M", "月K"))


def tchips(tr: dict | None, stats: bool = False) -> str:
    """日K / 周K / 月K 的趋势（qbreak/kline.py 的标签换成通俗说法：往上走 / 往下走 / 横着走 · 涨势整齐 / 跌势整齐；
    红 = 往上、绿 = 往下，文字本身就写着，不只靠颜色）。stats = True（个股）：现在是「月K 往上走 + 日K / 周K 往下走」三种组合之一时，
    下面一行写登记研究的历史统计（qbreak/dip_stats.py；2026-10-08 用户选〔75〕②；只展示、不是预测）。"""
    out = []
    for k, lab in TF_LABEL:
        x = (tr or {}).get(k)
        if not x:
            continue
        cls = {"上升": "up", "下降": "down"}.get(str(x.get("label")), "muted")
        al = KL.ALIGN_PLAIN.get(str(x.get("align") or ""), str(x.get("align") or ""))
        out.append(f"<span class='tchip'>{lab} <b class='{cls}'>{escape(KL.plain(x.get('label')))}</b>"
                   + (f" · {escape(al)}" if al else "") + "</span>")
    if not out:
        return ""
    ds = DS.line(tr) if stats else None
    return (f"<div class='tchips' aria-label='趋势'>{''.join(out)}</div>"
            + (f"<div class='dipst small'><b>{escape(ds['name'])}</b>：{escape(ds['text'])}</div>" if ds else ""))


GROUPS = (("imminent", "快要出买入信号"), ("watch", "观察中"))       # 「建议的股票」的分组；出了信号的全在「规则接下来会自动买」（_auto_pick 的 trig，2026-10-15）
RANK_GROUPS = (("rest", "观察中"),)


SG_PAGE = 5                               # 一组先显示几只（其余点「再显示」）


NOTIFY_SHOW_H = 24                                          # 「消息 → 通知记录」只显示最近几小时发出的
NEWS_SHOW_H = 24                                            # 「消息」的经济威胁消息只显示最近几小时发布的
MANUAL_SHOW_DAYS = 2                                        # 「交易」的手动指令：已经处理完的只显示最近几天
AUTO_NEAR_DAYS = 5                                          # 「快要出」列到几个交易日以内的估计金叉


def _chart_box(t: str, kind: str, has_k: bool = True) -> str:
    """一张 K 线图的占位（kline.js 看到 / 打开时才取 /api/chart 再画）。kind 只是标出在哪张卡片里（stock / core / suggest / autobuy）。"""
    return (f"<div class='chart' data-t='{escape(t)}' data-kind='{escape(kind)}'><span class='muted small'>"
            f"{'K 线（要 JavaScript）' if has_k else 'K 线在执行器下一次运行之后显示'}</span></div>")


def _kline_help() -> str:
    """整页只有一份的「怎么看 K 线图」（2026-10-15 用户：「去掉每个股票中的如何看这张图 整体留一个解释就行」）：「持仓」的 K 线上面
    （持仓卡片之前；同日用户：「选股中的怎么看K线图要放到持仓中的K线的上面」；选股只留一行「去看 ›」指过来）、默认收起；
    持仓 / 核心 ETF / 选股的每张图（日K / 周K / 月K）都按它看。图下面各自的一句话（最新一根、现在的趋势、趋势线）照旧在每张图里。"""
    def k(c: str) -> str:
        return f"<i class='key {c}'></i>"
    li = (f"每根 K 线 = 1 天 / 1 周 / 1 个月（图上边沿选 日K / 周K / 月K）：粗的一段 = 开盘到收盘，细线 = 最高到最低；"
          f"{k('box cu')}红色空心 = 涨　{k('box cd')}绿色实心 = 跌",
          f"{k('m5')}5　{k('m10')}10　{k('m20')}20　{k('m30')}30 日（周 / 个月）均价 = 最近几根收盘价的平均",
          "往上走 = 收盘在 20 均价上面、20 均价往上、5 均价在 20 均价上面；往下走 = 反过来；其余 = 横着走",
          f"拿着的股票：{k('dash')}买入价　{k('dash stop')}止损线（跌到这里按规则卖）　▲买入 = 买入那一根；候选：▲信号 = 出买入信号那一根",
          f"{k('dash tl')}趋势线：下面连低点（支撑）、上面连高点（压力），点线 = 往后延长；▲ 冲过压力线、▼ 跌破支撑线。"
          "研究（2026-10-06）：对之后的涨跌没有预测力，只用来看",
          "下面的小图：量 = 成交多少；MACD = 涨跌的力量（快线在 0 附近往上穿过慢线 = 金叉，是规则买入的条件之一）；DMI = 买卖哪边强、趋势强不强（规则不用）",
          "看以前的某一根：点一下或按住左右滑；键盘 ← → 一根一根看，Home / End 到最早 / 最新，Esc 回到最新",
          "图上都是过去的价格，不是预测")
    return ("<section class='card' id='khelp'><details class='khelp'><summary>怎么看 K 线图</summary><ul>"
            + "".join(f"<li>{x}</li>" for x in li) + "</ul></details></section>")


def _suggest_ctx(sg: dict, book: dict, tag: str, marks: dict | None = None, now: dt.datetime | None = None) -> dict:
    """「规则接下来会自动买」与「建议的股票」共用的一份（2026-10-14：两张卡里同一只票的内容 / 按钮 / 不能买的理由一样，只算一次）：
    排好的行（SG.rank：旧汇总没有 prob 也在这里补上，更新代码后不用等执行器）、不买回在解除 / 已经没了的说明（freed：手动买入不挡）、
    消息标记、个股名额、自动买那张卡列哪几只（auto = _auto_pick：建议的股票不再列这几只，2026-10-15）。
    bought = {今天已经买进的个股（对账前，live_ops.held_now）: 「今天已买进 N 股（对账前）」}：这几只不给「买入…」、不算进「买不起」
    （2026-10-16 复核：持仓里写着今天买进，选股里还给买入按钮）；名额（slots）也含今天已成交。"""
    tab = WP.load()
    rows = SG.rank([dict(r) for r in ((sg or {}).get("rows") or []) if r.get("ticker")], tab or {})
    blocks = ((book or {}).get("manual") or {}).get("blocks") or {}
    lifting = MO.lifting(tag, book)
    freed = {t: "「不自动买回」在解除：" + MO.NEXT_DECISION for t in lifting}   # 不买回在解除 / 已经没了 → 手动买入不挡
    freed.update({r["ticker"]: "「不自动买回」已经到期 / 解除（这里是上一次决策时的结果）" for r in rows
                  if r["ticker"] not in blocks and _man_block(r.get("buy"))})
    for r in rows:
        if _man_block(r.get("buy")) and r["ticker"] in blocks:
            r["buy"] = {**r["buy"], "block_until": blocks[r["ticker"]].get("until")}
    marks = _news_marks([r["ticker"] for r in rows]) if marks is None else marks
    pj = LO.held_now(book, tag, now=now)
    bt, dw = pj.get("by_ticker") or {}, pj.get("day_word") or "今天"
    bought = {t: f"{dw}已买进 {int((bt.get(t) or {}).get('buy') or 0):,} 股（对账前）"
              for t in pj.get("new") or [] if (bt.get(t) or {}).get("kind") == "stock"}
    return {"tab": tab, "rows": rows, "blocks": blocks, "lifting": lifting, "freed": freed, "marks": marks or {},
            "slots": MO.slots(book, tag, now=now, with_today=True), "auto": _auto_pick(sg, rows, blocks, lifting), "bought": bought}


def _slots_today(s: dict) -> str:
    """名额那句后面的「（含今天已成交）」/「（含 10/16（周五）已成交）」：成交让名额和只看账本时不一样（MO.slots 的 today / head；
    2026-10-16 二次复核：周末以前也写「今天」）。"""
    s = s or {}
    return f"（{s.get('head') or LO.hn_head(None)}）" if s.get("today") else ""


def _auto_pick(sg: dict, rows: list, blocks: dict, lifting) -> dict:
    """「规则接下来会自动买」列哪几只 —— 只在这里算（2026-10-15 用户：「去掉估计五个交易日内和建议的股票中重复的股票」：
    这几只「建议的股票」不再列，两张卡用同一份、不会对不上）。
    trig = 已经出了买入信号的（全部）；near = 估计 AUTO_NEAR_DAYS 个交易日内 MACD 金叉的（挡着的不列，只有「手动卖出后不买回」
    在估计金叉那天已经到期 / 在解除的还列）；gc = 估计金叉的 K 线日；wait = 还在不买回里的说明（「10/07 解除后」等）；tickers = 全部代码。"""
    from .calendar_jp import next_trading_day
    asof = _date_or_none((sg or {}).get("asof"))

    def gc_day(r):                                          # 估计金叉的 K 线日（asof 往后数 near.days 个交易日）
        gc = asof
        for _ in range(int((r.get("near") or {}).get("days") or 0)):
            gc = next_trading_day(gc) if gc else None
        return gc

    def man_wait(r) -> str | None:                           # 挡的只是「手动卖出后不买回」：估计金叉那天已经到期 / 在解除 → 还列（2026-10-13）
        b, t = r.get("buy") or {}, r["ticker"]
        if not _man_block(b):
            return None
        if t not in blocks:
            return "已解除"
        if t in lifting:
            return "解除中"
        u, gc = blocks[t].get("until"), gc_day(r)
        return f"{str(u)[5:10].replace('-', '/')} 解除后" if u is not None and gc is not None and gc.isoformat() > str(u) else None

    trig = [r for r in rows if r.get("status") == "triggered"]
    near, wait = [], {}
    for r in rows:
        nr = r.get("near") or {}
        if r.get("status") == "triggered" or nr.get("where") != "below_up" or int(nr.get("days") or 99) > AUTO_NEAR_DAYS:
            continue
        mw = man_wait(r)
        if (r.get("buy") or {}).get("block") and mw is None:
            continue
        near.append(r)
        if mw:
            wait[str(r["ticker"])] = mw
    near.sort(key=lambda r: (int(r["near"]["days"]), -float((r.get("prob") or {}).get("p") or 0)))
    return {"trig": trig, "near": near, "gc": {str(r["ticker"]): gc_day(r) for r in near}, "wait": wait,
            "tickers": {str(r["ticker"]) for r in trig + near}}


def _auto_buy_card(sg: dict, book: dict, tag: str, eq, buying: set | None = None, chart=None, ctx: dict | None = None) -> str:
    """选股最上面（2026-10-12 用户：「将会按照规则自动进行购买的股票，大概几天后」）：
    ① 已经出了信号的：规则已安排（哪天开盘、几股）/ 信号成立但不买（为什么）；② 估计 AUTO_NEAR_DAYS 个交易日内 MACD 金叉的：
    大概哪天、出了信号的话下一个交易日开盘买约几股（按现在的新仓倍数）、历史上 10 个交易日内真的出信号的比例（大多很低）。
    只是规则的展示与估算，不是建议；金叉之外还要量等条件凑齐，出了信号还要过闸门 / 名额。列哪几只 = ctx["auto"]（_auto_pick）。
    每一行可以点开（2026-10-14 用户：「估计 5 个交易日内可能出现信号的股票也要可以能看到 K 线，也可以有买入的 button」；默认收起）=
    这只在「建议的股票」里会有的那一行（_suggest_row：消息、条件、买入… / 全部换成这只… 或不能买的理由、规则的买价、K 线 · 现价；共用 ctx），
    不带名次徽章（2026-10-15 起这几只不在建议的股票里重复，名次指不到那边）。"""
    sg = sg or {}
    c = ctx if ctx is not None else _suggest_ctx(sg, book, tag)
    rows = c["rows"]
    if not rows:
        return ""
    s = c["slots"]
    a = c["auto"]
    bought = c.get("bought") or {}                          # 今天已经买进的（对账前）：不再当候选买（2026-10-16 复核）
    trig, near = a["trig"], a["near"]
    chart = chart or _chart_box
    ranked = bool(c["tab"])

    def item(badge: str, main: str, r: dict) -> str:        # 一行：收起时 = 原来的一行摘要；点开 = 建议的股票的那一行（K 线默认打开）
        t = str(r["ticker"])
        body = _suggest_row(r, s, buying or set(), eq, chart, fill=sg.get("fill_day"), mark=c["marks"].get(t), freed=c["freed"],
                            ckind="autobuy", kl_open=True, ranked=ranked and r.get("status") != "triggered", bought=bought)
        return (f"<details class='abx' data-t='{escape(t)}'><summary>{badge}<span class='grow'>{main}</span></summary>"
                f"<div class='abxb'>{body}<div class='abxe'><button type='button' class='btn' data-abxclose='1'>收起</button></div>"
                "</div></details>")                          # 底下也能收起（点开的一行很长：不用滚回摘要；2026-10-14 复核）

    def name(r):
        return f"<b>{escape(str(r.get('code') or r['ticker']))}</b> {escape(str(r.get('name') or ''))}"

    def est_shares(r):
        b = r.get("buy") or {}
        px, em, lot = float(b.get("px") or r.get("close") or 0), float(b.get("em") or 0), int(b.get("lot") or 100)
        if not (px > 0 and eq and em > 0):
            return 0
        return int(eq * CX.POS_PCT * min(1.0, em) / (px * 1.03) / lot) * lot
    H = ["<section class='card' id='autobuy'><h2>规则接下来会自动买</h2>",
         f"<div class='muted small'>按 {escape(str(sg.get('asof') or '—'))} 收盘。个股名额空 {s['free']} 个（上限 {s['max']} 只）{_slots_today(s)}。"
         "只是规则的展示与估算，不是建议。</div>"]
    if trig or near:
        H.append("<div class='muted small'>点一行展开：K 线 · 现价、买入…（这几只不在下面「建议的股票」里重复）</div>")
    if trig:
        H.append("<h3 class='sgh'>已经出了买入信号</h3><div class='list'>")
        for r in trig:
            ru = r.get("rule") or {}
            ok = ru.get("state") in ("planned", "manual")
            bw = bought.get(str(r["ticker"]))
            if bw:                                          # 今天已经买进（对账前）
                H.append(item(f"<span class='abd on'>{escape(bw.split(' ')[0])}</span>",
                              f"{name(r)}<span class='abs small'>{escape(bw)}</span>", r))
                continue
            H.append(item(f"<span class='abd{' on' if ok else ''}'>{'下个开盘' if ok else '不买'}</span>",
                          f"{name(r)}<span class='abs small{'' if ok else ' muted'}'>{escape(str(ru.get('text') or ''))}</span>", r))
        H.append("</div>")
    if near:
        sh_all = {r["ticker"]: est_shares(r) for r in near if str(r["ticker"]) not in bought}   # 今天已经买进的不算进「买不起」
        cant = sum(1 for v in sh_all.values() if v <= 0)
        H.append(f"<h3 class='sgh'>估计 {AUTO_NEAR_DAYS} 个交易日内可能出信号（{len(near)} 只）</h3>")
        if s["free"] <= 0:
            H.append("<div class='neg small'>名额满：出了信号也不会买（先卖出一只）</div>")
        elif cant:
            H.append(f"<div class='small'>★ 其中 {cant} 只出了信号也买不起：现在一只新仓约 {_yen(eq * CX.POS_PCT * min(1.0, max(float((r.get('buy') or {}).get('em') or 0) for r in near)))}"
                     "（总权益 × 25% × 新仓倍数），不够 100 股</div>")
        H.append("<div class='list'>")
        for r in near:
            n = int(r["near"]["days"])
            gc = a["gc"].get(str(r["ticker"]))
            p = (r.get("prob") or {}).get("p")
            sh = sh_all.get(r["ticker"], 0)
            miss = (r.get("near") or {}).get("miss") or []
            bw = bought.get(str(r["ticker"]))
            tag_ = (f"<span class='chip'>{escape(bw)}</span>" if bw else
                    "<span class='chip'>名额满</span>" if s["free"] <= 0 else "<span class='chip'>买不起</span>" if sh <= 0
                    else f"<span class='chip hot'>约 {sh:,} 股</span>")
            mw = a["wait"].get(str(r["ticker"]))
            if mw:                                          # 现在还在「不买回」里：到期 / 解除之后才可能买
                tag_ += f"<span class='chip'>{escape(mw)}</span>"
            sub = " · ".join(x for x in (f"约 {gc:%m/%d} 金叉" if gc else "", f"历史出信号 {float(p) * 100:.0f}%" if p is not None else "",
                                         f"还差 {len(miss)} 个条件" if miss else "") if x)
            H.append(item(f"<span class='abd'>约 {n} 天</span>", f"{name(r)} {tag_}<span class='abs muted small'>{escape(sub)}</span>", r))
        H.append("</div>")
    if not trig and not near:
        H.append(f"<div class='muted'>今天没有出信号的票，估计 {AUTO_NEAR_DAYS} 个交易日内金叉的也没有：规则近几天大概不会自动买个股</div>")
    H.append("<div class='muted small'>天数与日期是按最近一天的变化估的；金叉之外还要量等条件凑齐才出买入信号（历史比例大多很低）；"
             "出了信号下一个交易日开盘买。</div></section>")
    return "".join(H)


def _man_block(b: dict | None) -> bool:
    """「建议的股票」里这只的买入闸门是「手动卖出后不买回」（不是资格检查；旧汇总没有 block_kind → 按文字）。"""
    b = b or {}
    return bool(b.get("block")) and (b.get("block_kind") == "manual" or (
        b.get("block_kind") is None and str(b.get("block")).startswith("手动卖出后不")))


def _unblock_confirm(book: dict, tag: str, ts: list[str], what: str, selling: list[str], now: dt.datetime | None = None) -> str:
    """「恢复按规则」/「解除」的确认（2026-10-13：一点一行，说清解除之后不会怎样、什么时候、还要过什么）。
    名额与现金同一个口径：都含今天已成交（MO.slots / live_ops.held_now；2026-10-16 复核：以前名额按账本、现金含今天）。"""
    st, man = (book or {}).get("state") or {}, (book or {}).get("manual") or {}
    s = MO.slots(book, tag, now=now, with_today=True)
    pj = LO.held_now(book, tag, now=now)                   # 含今天已成交的现金（对账前；2026-10-16）
    many = len(ts) > 1
    L = [f"只解除{what}的「不自动买回」" + (f"（{NM.labels(ts)}）" if many else "") + "。",       # 票写「代码 名字」（2026-10-15）
         f"不会把{'它们' if many else '它'}买回来，也不会马上买。",
         f"{MO.NEXT_DECISION}，规则重新判断：只有那次决策看的那根 K 线出买入信号（MACD 金叉）才可能买；已经判断过的信号不会再用。",
         f"买入还要有空名额（现在空 {s['free']} 个，上限 {s['max']} 只{_slots_today(s)}）、现金（账本现金 {_yen(float(st.get('cash_jpy') or 0))}"
         + (f"（{pj.get('head') or LO.hn_head(pj.get('day_word'))}约 {_yen(pj['cash'])}）" if pj.get("has") else "") + "）、"
         "过资格检查 / 决算前 / 宏观。"]
    if MO.core_pct_now(tag, book) <= 0 or man.get("core_pause"):
        L.append("闲置资金 ETF 仍停买（0%，要另外点「确认买入」）；这批取消的固定口数不会恢复。")
    if selling:
        L.append(f"还没成交的卖出（{NM.labels(selling)}）不会撤：要停就用「撤回」/「撤单」。")
    return "\n".join(L)


def _blocks_card(book: dict, tag: str, bl: dict, tlabel, now: dt.datetime | None = None) -> tuple[str, int]:
    """「交易」的「手动卖出后不自动买回」：「全部换成 X」按批一行（「恢复按规则」= 只解除这一批）+ 每只一行（「解除」）；
    按钮带着页面看到的设定 id（设定换了 / 已经解除 → 不写；2026-10-13）。在解除的（还没读 / 等下一次决策）不给按钮。
    还在卖的 = 含今天已成交的持仓里还有（live_ops.held_now；2026-10-16 复核：今天已经卖光的以前写成「还没成交的卖出」）。
    2026-10-16（「交易里面只显示当天要成交的单」）：放进最下面收起的「已结束 / 不是今天的」（id blocks 照旧）→ (HTML, 行数)。"""
    lift = MO.lifting(tag, book)
    pj = LO.held_now(book, tag, now=now)
    pos = (pj.get("state") or {}).get("pos") or {}
    paused = MO.core_pct_now(tag, book) <= 0 or bool(((book or {}).get("manual") or {}).get("core_pause"))

    def md(v) -> str:
        return str(v or "")[5:10].replace("-", "/") or "—"

    def bid(v) -> str:                                      # 设定的 id（格式不对的旧数据：不带 → 只按代码解除）
        v = str(v or "")
        return v if re.fullmatch(r"M[0-9A-Za-z_.\-]{1,80}", v) else ""
    rows = []
    for g in MO.batch_blocks(pj["book"]):                   # 「全部换成 X」卖掉的：一批一次「恢复按规则」（2026-10-13 用户）；卖没卖完按含今天已成交
        mem = g["members"]
        who = "、".join(tlabel(m["t"]) + ("（解除中）" if m["t"] in lift else "" if m["state"] == "sold" else f"（{m['state']}）") for m in mem)
        until = MO.block_text({"until": g["until"]})
        todo = [m for m in mem if m["t"] not in lift]
        sell = [m["t"] for m in todo if m["state"] != "sold"]
        if todo:
            msg = _unblock_confirm(book, tag, [m["t"] for m in todo], f"「全部换成 {tlabel(g['x'])}」这一批", sell, now=now)
            btn = (f"<button class='btn sm' data-act='unblock-batch' data-ids='{escape(','.join(m['t'] + (':' + bid(m['id']) if bid(m['id']) else '') for m in todo))}'"
                   f" data-x='{escape(tlabel(g['x']))}' data-msg='{escape(msg)}'>恢复按规则</button>")
        else:
            btn = "<span class='chip'>解除中（下一次决策起）</span>"
        rows.append(f"<div class='li'><div class='grow'><b>「全部换成 {escape(tlabel(g['x']))}」（{md(g['at'] or g['since'])}）卖出的</b> "
                    f"<span class='muted'>{escape(who)}</span><div class='muted small'>{escape(until)}"
                    "；点「恢复按规则」= 只解除这一批（不买回、也不马上买）" + ("；闲置资金 ETF 不跟着恢复（仍停买）" if paused else "")
                    + "</div></div>" + btn + "</div>")
    for t, b in bl.items():
        if t in lift:
            btn = "<span class='chip'>解除中（下一次决策起）</span>"
        else:
            msg = _unblock_confirm(book, tag, [t], f" {tlabel(t)} ", [t] if t in pos else [], now=now)
            btn = (f"<button class='btn sm' data-act='unblock' data-t='{escape(t)}' data-id='{escape(bid(b.get('id')))}'"
                   f" data-msg='{escape(msg)}' data-name='{escape(NM.name(t) or '')}'>解除</button>")   # 名字放最后（确认框标题用；2026-10-15）
        rows.append(f"<div class='li'><div class='grow'><b>{escape(tlabel(t))}</b> <span class='muted'>{escape(MO.block_text(b))}</span></div>"
                    + btn + "</div>")
    return ("<div id='blocks'><div class='tsub'>手动卖出后不自动买回</div><div class='muted small'>到期 / 解除之前规则和手动都不买这几只；"
            f"解除 = {escape(MO.NEXT_DECISION)}（不会买回，也不马上买）</div><div class='list'>" + "".join(rows) + "</div></div>"), len(rows)


def _date_or_none(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _suggest_card(sg: dict, book: dict, tag: str, buying: set, when: str, eq, cap: float, chart, marks: dict | None = None,
                  ctx: dict | None = None) -> str:
    """「建议的股票」= 规则的候选（qbreak/suggest.py）+ 每只的「买入…」（写手动买入指令；执行器下单前再查一遍）。
    上面「规则接下来会自动买」已经列的（ctx["auto"]，_auto_pick）不再列（2026-10-15 用户：去掉重复的股票）：标题的只数 = 这里列的，
    另写一行跳过了几只；名次按这里列的从 1 数起。
    有比例表（var/watch_prob.json，登记研究判定 A）→ 观察中一组（名次 1..n；按离金叉的天数 → 历史比例，闸门挡的最后），每只写第几、历史比例；
    没有 → 快要出 → 观察中（按离买入信号的远近）。出了信号的都在上面「规则接下来会自动买」（_auto_pick 的 trig 是全部出了信号的）。
    ctx = _suggest_ctx（与「规则接下来会自动买」共用）。"""
    sg = sg or {}
    c = ctx if ctx is not None else _suggest_ctx(sg, book, tag, marks)
    tab, s, freed = c["tab"], c["slots"], c["freed"]
    skip = c["auto"]["tickers"]
    rows = [r for r in c["rows"] if str(r["ticker"]) not in skip]
    n_skip = len(c["rows"]) - len(rows)
    marks = {t: m for t, m in c["marks"].items() if t not in skip}
    ranked = bool(tab)
    H = [f"<section class='card' id='suggest'><h2>建议的股票（规则的候选，{len(rows)} 只）</h2>"]
    if not rows and n_skip:                                 # 候选都在上面那张卡里：一行，不留空卡片
        H.append(f"<div class='muted'>候选 {n_skip} 只都在上面「规则接下来会自动买」里（点开一行看 K 线、买入…），这里不重复</div>"
                 + (f"<div class='neg small'>★ 这次没算成：{escape(str(sg['error']))}</div>" if sg.get("error") else "") + "</section>")
        return "".join(H)
    H += [f"<div class='muted small'>按 {escape(str(sg.get('asof') or '—'))} 收盘。不是收益预测，也不是建议；点「买入…」→ {escape(when)}下单。</div>",
          f"<div class='small'>个股名额：空 {s['free']} 个（拿着 {s['held']} + 排定买入 {s['buys']}，上限 {s['max']} 只）{_slots_today(s)}</div>"]
    if n_skip:
        H.append(f"<div class='muted small'>上面「规则接下来会自动买」已列的 {n_skip} 只不在这里重复</div>")
    if sg.get("error"):
        H.append(f"<div class='neg small'>★ 这次没算成：{escape(str(sg['error']))}</div>")
    if not rows:
        H.append("<div class='muted'>" + ("候选在执行器下一次运行之后显示" if not sg else "今天没有出信号 / 快要出信号 / 观察中的票") + "</div></section>")
        return "".join(H)
    h = int((tab or {}).get("h") or WP.H)
    groups = []
    for g, title in (RANK_GROUPS if ranked else GROUPS):
        grp = rows if g == "rest" else [r for r in rows if r.get("status") == g]
        if grp:
            groups.append((g, title, grp))
    if marks:
        n_big = sum(1 for m in marks.values() if m["dir"] == "down" and m["level"] == "大")
        H.append(f"<div class='small'>最近 72 小时的消息影响到其中 {len(marks)} 只" + (f"（受损 大 {n_big} 只）" if n_big else "")
                 + "：见每只名字下面的「消息」标记，点开看是哪几条</div>")
    if len(groups) > 1:                                      # 分段：一次只看一组（2026-10-11 用户：不要页面很长）
        H.append("<div class='seg sgseg' role='tablist'>" + "".join(
            f"<button type='button' data-sgg='{g}'{' class=on' if n == 0 else ''}>"
            f"{escape('观察中' if g == 'rest' else str(title))} {len(grp)}</button>" for n, (g, title, grp) in enumerate(groups)) + "</div>")
    for n, (g, title, grp) in enumerate(groups):
        H.append(f"<div class='sgg' data-g='{g}'{'' if n == 0 else ' hidden'}>")
        if g == "rest":                                     # 快要出 + 观察中一组：按离金叉的天数排
            H.append(f"<h3 class='sgh'>观察中 · {len(grp)} 只（按离 MACD 金叉的天数排）</h3>"
                     f"<div class='muted small'>越上面越快出现金叉（按最近一天的变化估算的天数；同样天数时快要出的、历史比例高的在前；"
                     "已经在信号线上 / 还在往下走的排在后面，闸门挡的最后）。金叉之外还要横盘、量等条件凑齐才出买入信号，"
                     "出了信号还要过闸门 / 名额才会买。</div>")
        else:
            H.append(f"<h3 class='sgh'>{escape(title)}（{len(grp)} 只）</h3>")
            if any(r.get("near") for r in grp):
                H.append("<div class='muted small'>按离 MACD 金叉的天数排（越上面越快金叉；只是估算）</div>")
        for k, r in enumerate(grp, 1):
            row = _suggest_row(r, s, buying, eq, chart, rank=k if g == "rest" else None, fill=sg.get("fill_day"),
                               mark=marks.get(str(r["ticker"])), freed=freed, bought=c.get("bought"))
            H.append(row if k <= SG_PAGE else f"<div class='sgmore' hidden>{row}</div>")
        if len(grp) > SG_PAGE:
            H.append(f"<div class='act'><button class='btn' data-sgmore='{g}'>再显示 {len(grp) - SG_PAGE} 只</button></div>")
        H.append("</div>")
    H.append("<div class='muted small'>股数按最近收盘估算。</div></section>")
    return "".join(H)


def _news_marks(tickers, now: dt.datetime | None = None) -> dict:
    """最近 72 小时的经济威胁消息对这些票的影响（news.ticker_impacts；只展示，不参与交易）。取不到 → {}。"""
    from . import news as NW
    try:
        now = (now or now_jst()).astimezone(JST)
        cut = now - dt.timedelta(hours=NW.MAX_AGE_H)
        ev = [e for e in (NW.load() or {}).get("events") or [] if (_ts_jst(e.get("time")) or cut) >= cut and NW.level(e) != "低"]
        return NW.ticker_impacts(ev, [str(x) for x in tickers], now=now) if ev else {}
    except Exception as e:                                 # noqa: BLE001  展示用：算不出不影响页面
        log.warning("消息影响标记没算成：%s", e)
        return {}


def _news_mark(m: dict | None) -> str:
    """一只票的消息影响标记：「⚠ 消息：受损 大（2 条）」+ 点开看是哪几条（时间 JST、冲击、标题；点标题跳到「消息」页那一条）。
    2026-10-11 用户：候选股票上如果实时消息中出现了对该股的影响，根据影响大小标记，并且可以看到对应的消息。"""
    if not m:
        return ""
    down = m["dir"] == "down"
    tone = {"大": "dnb", "中": "dnm"}.get(m["level"], "") if down else "upb"      # 涨红跌绿：受损 大 = 绿框、中 = 绿字、小 = 普通；受益 = 红框
    head = f"{'⚠' if down else '↑'} 消息：{'受损' if down else '受益'} {m['level']}（{len(m['items'])} 条，估算 {m['net']:+.1f}%）"
    li = []
    for i in m["items"][:6]:
        t = _ts_jst(i.get("time"))
        nid = escape(str(i.get("id") or ""))
        li.append(f"<li><span class='muted'>{t.strftime('%m/%d %H:%M') if t else '—'} JST</span> "
                  f"<b class='{'down' if i['eff'] < 0 else 'up'}'>{i['eff']:+.1f}%</b>"
                  + (" <b class='neg'>★</b>" if i.get("alert") else "")
                  + f" <span class='chip'>{escape('、'.join(i.get('labels') or []) or '其他')}</span><br>"
                  + (f"<span class='small'>{escape(_window_text(i['timing']))}</span><br>" if i.get("timing") else "")
                  + f"<a href='?tab=news&amp;seg=news&amp;n={nid}' data-nlink='{nid}'>{escape(str(i.get('title_zh') or i.get('title') or '')[:120])}</a></li>")
    more = len(m["items"]) - 6
    win = ""
    if m.get("start") and m.get("end"):
        s, e = dt.date.fromisoformat(m["start"]), dt.date.fromisoformat(m["end"])
        now_d = now_jst().date()
        mn = m.get("main") or {}
        me = dt.date.fromisoformat(mn["end"]) if mn.get("end") else e
        win = (f"<div class='small nwin'>影响期（经验估计）：{_md(s)} {'起（已开始）' if s <= now_d else '开盘起'} → 主要那条约 {_md(me)} 前后结束"
               f"（还有约 {_tdays(max(now_d, s), me)} 个交易日）" + (f"；全部最晚约 {_md(e)}" if e > me else "") + "</div>")
    return (f"<details class='nmk'><summary><span class='chip {tone}'>{escape(head)}</span>{win}</summary>"
            f"<div class='muted small'>行业：{escape(str(m.get('sector') or ''))}。每条消息对这个行业的估算冲击 × 可信度（★ 达到提醒线的 ×1.5），最大的一条为主、其余递减加总；"
            "≥ 1% 大、≥ 0.4% 中、其余小。只是粗估，不参与交易；点标题看「消息」页的详细。</div><ul class='small nml'>" + "".join(li)
            + (f"<li class='muted'>另外 {more} 条影响较小</li>" if more > 0 else "") + "</ul></details>")


WD = "一二三四五六日"


def _md(d: dt.date) -> str:
    return f"{d.month}/{d.day}（周{WD[d.weekday()]}）"


def _tdays(a: dt.date, b: dt.date) -> int:
    """a〜b（含两头）的交易日数。"""
    from .calendar_jp import is_trading_day
    n, x = 0, a
    while x <= b:
        n += is_trading_day(x)
        x += dt.timedelta(days=1)
    return n


def _window_text(tm: dict) -> str:
    """一条消息的影响期一句话：开始 → 结束、持续几天（经验估计）。"""
    s, e = dt.date.fromisoformat(tm["start"]), dt.date.fromisoformat(tm["end"])
    how = "盘中发布、当天已开始反映" if tm.get("intraday") else f"{_md(s)} 开盘起"
    return f"影响：{how} → 约 {_md(e)} 前后结束（一般持续 {tm['lo']}〜{tm['hi']} 个交易日）· {tm['state']}"


def _prob_line(pr: dict | None) -> str:
    """之后 h 个交易日内出买入信号的历史比例（watch_prob.for_row）一行；研究判定「只排序」（show = False）→ 不写数。"""
    if not pr or pr.get("p") is None:
        return ""
    h = int(pr.get("h") or WP.H)
    if not pr.get("show", True):
        return f"<div class='small prob'>按之后 {h} 个交易日内出买入信号的历史比例排</div>"
    n = int(pr.get("n") or 0)
    return (f"<div class='small prob'>之后 {h} 个交易日内出买入信号：历史上约 <b>{float(pr['p']) * 100:.1f}%</b>"
            + (f"（同样情况 {n:,} 次）" if n else "（相近情况估算）") + "</div>")


OLD_EM0 = "新仓倍数 0（宏观 / 判断层 / 关联搭配 C / TBF 里有一层说现在不开这只的新仓）"


def _fill_mult_why(w: str) -> str:
    """执行器旧版写的「新仓倍数 0」没写是哪一层 → 用云端日报的市场层补上（2026-10-11 用户：要标清楚被什么规则挡住）。
    新版执行器（suggest.mult_why）自己写清楚，这里不动。"""
    if "（新仓倍数 0）：会被挡" not in w and OLD_EM0 not in w:
        return w
    try:
        rg = (((read_json(paths.PROJECT_ROOT / "var" / "out" / "unified_today.json", {}) or {}).get("extras") or {}).get("JP") or {}).get("regime") or {}
    except Exception:                                      # noqa: BLE001
        rg = {}
    why = []
    if rg.get("overlay_mult") is not None and float(rg["overlay_mult"]) <= 0:
        why.append(f"市场风险报告（{rg.get('overlay_as_of') or '—'}）的判断「{rg.get('overlay_action') or ''}」→ 新仓 ×0"
                   + (f"（报告的急跌概率 {float(rg['crash_prob']):g}%）" if rg.get("crash_prob") is not None else ""))
    if rg.get("quant_mult") is not None and float(rg["quant_mult"]) <= 0:
        why.append("市场状态层 risk_off（日経225 跌破 200 日线 / 离一年高点 −12% 以上 / 波动率 > 35%）")
    bb = rg.get("bullbear") or {}
    if bb.get("gating") and bb.get("state") == "bear":
        why.append(f"牛熊分界：{bb.get('since') or '—'} 起熊市")
    if not why:
        return w
    txt = "；".join(why)
    return w.replace("（新仓倍数 0）：会被挡", f"（新仓倍数 0）—— {txt}：会被挡").replace(OLD_EM0, f"新仓倍数 0 —— {txt}")


def _suggest_row(r: dict, s: dict, buying: set, eq, chart, rank: int | None = None, fill: str | None = None,
                 mark: dict | None = None, freed: dict | None = None, ckind: str = "suggest", kl_open: bool | None = None,
                 ranked: bool | None = None, bought: dict | None = None) -> str:
    """「建议的股票」的一只（「规则接下来会自动买」点开的也是它：ckind = autobuy、K 线默认打开 kl_open；2026-10-14）。
    rank = 名次徽章（只在建议的股票里）；ranked = 在按历史比例排的一组里（「快要出」标记 + 历史比例那一行；不给 = 有 rank 就算）——
    自动买那张卡里的行不带徽章、照样有这两样（2026-10-15：那几只不在建议的股票里重复，名次指不到那边）。
    元素不带 id（持仓里拿着的票与这里的图各自一份也不冲突）。
    bought = _suggest_ctx 的 bought：今天已经买进的（对账前）→ 写那句、不给「买入…」（2026-10-16 复核）。"""
    t, b, ru = str(r["ticker"]), r.get("buy") or {}, r.get("rule") or {}
    nm = f" {escape(str(r['name']))}" if r.get("name") else ""
    meta = [f"条件凑齐 {r['score']:g} / 100" if r.get("score") is not None else None,
            f"收盘 ¥{r['close']:,.0f}" if r.get("close") is not None else None,
            f"量 {r['vol_ratio']:.2f} 倍" if r.get("vol_ratio") is not None else None,
            "真突破" if r.get("breakout") else None]
    rk_on = bool(rank) if ranked is None else ranked
    tag_ = ("<span class='chip hot'>快要出</span>" if r.get("status") == "imminent" else "") if rk_on else ""
    nr = r.get("near") or {}
    if r.get("status") != "triggered" and nr.get("where"):                # 离金叉（2026-10-11 用户：按离金叉的临近日排序）
        gd = int(nr.get("days") or SG.MAX_DAYS)
        tag_ += ("<span class='chip gc'>" + (f"金叉约 {gd} 天" if nr["where"] == "below_up" and gd < SG.FAR_DAYS
                                             else "金叉还远" if nr["where"] == "below_up" else "要先拐头" if nr["where"] == "below_down"
                                             else "已在线上" if nr["where"] == "above" else "金叉算不出") + "</span>")
    rk = f"<span class='rk'>{rank}</span>" if rank else ""
    H = [f"<div class='hv sg'><div class='head'>" + rk
         + f"<b>{escape(str(r.get('code') or t))}</b>{nm}"
         + (f"<span class='chip'>{escape(str(r['sector']))}</span>" if r.get("sector") else "") + tag_ + "</div>"
         + _news_mark(mark)                                 # 消息的影响（2026-10-11 用户）
         + _prob_line(r.get("prob") if rk_on else None)
         + f"<div class='meta'>{' · '.join(x for x in meta if x)}</div>"
         + (f"<div class='small near'>{escape(str(r['near_text']))}</div>" if r.get("near_text") else "")   # 离买入信号还差什么（排序依据）
         + (f"<div>{escape(_fill_mult_why(str(ru.get('text') or '')))}</div>" if ru.get("state") not in (None, "none") else "")
         + tchips(r.get("trend"), stats=True)
         + (f"<div class='small neg'>★ 顶部风险：{escape(str(r['top_risk']))}</div>" if r.get("top_risk") else "")]
    n, px, lot = int(b.get("rule_shares") or 0), float(b.get("px") or 0), int(b.get("lot") or MO.LOT)
    why = None
    lifted = _man_block(b) and t in (freed or {})           # 不买回在解除 / 已经没了：手动买入不挡（执行器下单前按最新的再查；2026-10-13）
    if t in (bought or {}):                                 # 今天已经买进（对账前）：要加仓等对账之后用「调仓」
        why = f"{bought[t]}：在「持仓」里；要加仓等对账之后用「调仓」"
    elif _man_block(b) and not lifted:                      # 与资格检查分开写（2026-10-13）
        u = b.get("block_until")
        why = f"手动卖出后不买回（可在{MO.BLOCK_WHERE}解除）：{'到 ' + str(u) if u else '一直，直到解除' if 'block_until' in b else b['block']}"
    elif b.get("block") and not lifted:
        why = f"不能买：{b['block']}"
    elif t in buying:
        why = f"有一条买入指令在处理（见{(buying.get(t) if isinstance(buying, dict) else '') or _where_zone(None)}）"
    elif ru.get("state") in ("planned", "manual"):
        why = "已经排在开盘买入"
    elif not (px > 0 and eq):
        why = "没有收盘价 / 总权益：执行器下一次运行之后再买"
    warn = "；".join(_fill_mult_why(w) for w in b.get("warn") or [])
    full = s["free"] <= 0                                   # 名额满：只能「全部换成这只」（其他持仓全部卖出；2026-10-13 用户）
    if lifted:
        H.append(f"<div class='muted small'>{escape(freed[t])}（规则出买入信号才买；手动买入可以写）</div>")
    if why:
        H.append(f"<div class='act muted small'>{escape(why)}</div>")
    else:
        st_txt = SG.STATUS.get(str(r.get("status")), str(r.get("status_text") or ""))
        data = (f" data-t='{escape(t)}' data-code='{escape(str(r.get('code') or t))}' data-name='{escape(str(r.get('name') or ''))}'"
                f" data-px='{px:g}' data-lot='{lot}' data-rule='{n}' data-limit='{float(b.get('limit') or 0):g}'"
                f" data-sig='{1 if r.get('signal') else 0}' data-status='{escape(st_txt)}'"
                f" data-rtext='{escape(str(ru.get('text') or ''))}' data-warn='{escape(warn)}'" + (" data-full='1'" if full else ""))
        H.append(f"<div class='act'><button class='btn {'' if full else 'primary'}' data-act='buy'{data}>{'全部换成这只…' if full else '买入…'}</button>"
                 + (f"<span class='muted small'>个股名额已满（{s['used']} / {s['max']} 只）：只能把其他持仓全部卖出来换这只</span></div>" if full else
                    f"<span class='muted small'>按规则约 {n:,} 股 · 约 {_yen(n * px)}" + (f" · 约占权益 {n * px / eq * 100:.1f}%" if eq else "") + "</span></div>")
                 + (f"<div class='small neg'>★ {escape(warn)}</div>" if warn else ""))
    H.append(_buy_price_line(r, fill))                       # 规则的买价（2026-10-07 用户「建议的股票要给出合适的买价」）
    planned = " data-planned='1'" if ru.get("state") in ("planned", "manual") or b.get("planned") else ""   # 已排在开盘买：只写现价
    op = r.get("status") == "imminent" if kl_open is None else kl_open   # 出了信号的只在自动买那张卡（kl_open=True）
    H.append(f"<details class='kl'{' open' if op else ''}>"
             f"<summary>K 线 · 现价</summary><div class='qt small' data-sq='{escape(t)}'{planned}></div>{chart(t, ckind)}</details></div>")
    return "".join(H)


def _nm(t, n=None) -> str:
    """页面上的名字（不带代码）：names.name 优先（唯一入口）；查不到 → 别处给的名字（去掉旧写法末尾的「（1545）」）；都没有 → ""。
    以前按「（」截 → 「S&P500（MAXIS）」被截成「S&P500」（2026-10-15）。"""
    v = NM.name(t)
    if v:
        return v
    v = str(n or "").strip()
    c = NM.code(t)
    v = re.sub(r"\s*（" + re.escape(c) + r"(?:\.T)?）$", "", v) if c else v
    return "" if v in ("", str(t), c) else v


def _page_names(book: dict, waiting: list, sm: dict, man: dict) -> dict:
    """页面脚本用的名字表 CFG.names = {ticker: 名字}（只放查得到的；2026-10-15 用户：只写代码不知道是哪只）：持仓、核心 ETF（拿着的 /
    规则目标 / 固定的）、当前决策的单、手动指令（含凑钱的「为谁」）、不自动买回、凑钱用的持仓、K 线、建议的股票、停买的「你卖出 X / 全部换成 X」。
    单独放（不进 cores：测试断言了 cores 的 JSON）。"""
    st = (book or {}).get("state") or {}
    cr = (book or {}).get("core_rule") or {}
    ts: list = list(st.get("pos") or {}) + list(st.get("core_units") or {}) + list(cr.get("units100") or {}) + list(man.get("core_fix") or {})
    d = st.get("last_date")
    ts += [o.get("ticker") for o in (book or {}).get("orders") or [] if o.get("decided_on") == d]
    for r in list(waiting or []) + list((man.get("items") or {}).values()):
        if isinstance(r, dict):
            ts += [r.get("ticker"), r.get("fund_for")]
    ts += list(man.get("blocks") or {})
    cp = man.get("core_pause") or {}
    if isinstance(cp, dict):
        ts += [cp.get("ticker"), cp.get("allin")]
    ts += list(((sm or {}).get("kline") or {}).get("items") or {})
    ts += [r.get("ticker") for r in ((sm or {}).get("suggest") or {}).get("rows") or [] if isinstance(r, dict)]
    try:
        for g in MO.batch_blocks(book):
            ts += [g.get("x")] + [m.get("t") for m in g.get("members") or []]
    except Exception:                                      # noqa: BLE001  只是名字表
        pass
    return NM.names_map([t for t in ts if isinstance(t, str) and t])


ALLOC_COLORS = ("#4c7bf3", "#f0a030", "#9b6cf0", "#20a8a0", "#e5c53a", "#e870b0", "#a07850", "#6aa8e8")   # 不用红 / 绿（红涨绿跌另有含义）


def _alloc_card(book: dict | None, hv: dict | None, pj: dict | None = None) -> str:
    """持仓最上面的「仓位占比」（2026-10-12 用户：每个仓位占多少，用线性 / 扇形一眼看出来）：一条按金额分段的横条 + 每只一行
    （颜色点、代码名称、占比、金额）；现金灰色放最后。按最近收盘估算（与「从持仓平摊凑」同一份数字）。没有持仓 → 空。
    pj（live_ops.held_now）有成交 → 标题写「含 10/16（周五）已成交（… 对账后正式记账）」（book 是投影；2026-10-16 二次复核：以前没说）。"""
    st = (book or {}).get("state") or {}
    hold = MO.fund_holdings(book)["hold"]
    hvn = {r.get("ticker"): r.get("name") for r in ((hv or {}).get("holdings") or []) + ((hv or {}).get("core") or [])}
    items = [(h["t"], _nm(h["t"], hvn.get(h["t"])), h["cur"] * h["px"], h["kind"]) for h in hold if h["cur"] > 0 and h["px"] > 0]
    if not items:
        return ""
    items.sort(key=lambda x: -x[2])
    cash = max(0.0, float(st.get("cash_jpy") or 0))
    total = sum(x[2] for x in items) + cash
    if total <= 0:
        return ""
    rows = [(t, n, v, k, ALLOC_COLORS[i % len(ALLOC_COLORS)]) for i, (t, n, v, k) in enumerate(items)]
    if cash > 0:
        rows.append(("现金", "", cash, "cash", "var(--muted)"))
    bar = "".join(f"<i style='width:{v / total * 100:.2f}%;background:{c}' title='{escape(f'{NM.code(t)} {n}'.strip() if k != 'cash' else t)} {v / total * 100:.1f}%'></i>"
                  for t, n, v, k, c in rows)
    legend = "".join(
        f"<div class='alr'><span class='ald' style='background:{c}'></span>"
        f"<span class='aln'><b>{escape(NM.code(t))}</b>{(' ' + escape(n)) if n else ''}{' · ETF' if k == 'core' else ''}</span>"
        f"<span class='alp'>{v / total * 100:.1f}%</span><span class='aly muted'>{_yen(v)}</span></div>"
        for t, n, v, k, c in rows)
    hn = str((pj or {}).get("note") or "").split("；")[0] if (pj or {}).get("has") else ""   # 「含今天已成交（下个交易日 10/19（周一）07:40 对账后正式记账）」
    return (f"<section class='card' id='alloc'><div class='head'><b>仓位占比</b><span class='muted small'>合计 {_yen(total)} · 按最近收盘"
            + (f" · {escape(hn)}" if hn else "") + "</span></div>"
            f"<div class='alb' role='img' aria-label='仓位占比'>{bar}</div><div class='all'>{legend}</div></section>")


def _exit_html(info: dict | None) -> str:
    """拿着的核心 ETF「什么时候会自动卖」（qbreak/core_exit.py 的结果 → HTML）：全部卖的条件与离触发还有多远（离转熊线、确认几天）、
    卖完去哪（现金 / 对冲版美债 1482）、部分卖（买新个股钱不够时）、不会因为什么卖；时间线与历史收在「时间线与历史」里。"""
    if not info:
        return ""

    def dots(d) -> str:
        if not d:
            return ""
        n, k = (int(x) for x in d)
        return "<span class='dots' aria-hidden='true'>" + "".join(f"<i class='{'on' if i < n else ''}'></i>" for i in range(k)) + "</span>"

    def chip(c: dict) -> str:
        tone = {"bad": " bad", "hot": " hot"}.get(str(c.get("tone") or ""), "")
        return f"<span class='chip{tone}'>{dots(c.get('dots'))}{escape(str(c['text']))}</span>"
    tiles = "".join(
        f"<div class='{'bad' if x.get('tone') == 'bad' else ''}'><div class='l'>{escape(str(x['label']))}</div>"
        f"<div class='v'>{escape(str(x['value']))}</div>"
        + (f"<div class='mt{' hot' if x['meter'].get('hot') else ''}' title='离线越远条越长（15% 以上满格）'>"
           f"<i style='width:{float(x['meter']['frac']) * 100:.0f}%'></i></div>" if x.get("meter") else "")
        + (f"<div class='s'>{dots(x.get('dots'))}{escape(str(x.get('sub') or ''))}</div>" if x.get("sub") or x.get("dots") else "")
        + "</div>" for x in info.get("tiles") or [])
    def flow(r: dict) -> str:                              # 一眼版：「条件 → 结果」两三个小块；详细的句子收进「详细说明」
        steps = "<span class='axa'>→</span>".join(
            f"<span class='axs{ {'bad': ' bad', 'hot': ' hot'}.get(str(s.get('tone') or ''), '')}'>{escape(str(s['text']))}</span>" for s in r["flow"])
        state = f"<span class='axst'>{escape(str(r['hint']))}</span>" if r.get("hint") else ""
        return f"<div class='axf'>{steps}</div>{state}"
    rows = "".join(
        f"<div class='axr'><div class='axk'>{escape(str(r['k']))}</div><div class='axv'>"
        + (flow(r) if r.get("flow") else f"<div>{escape(str(r['text']))}</div>"
           + (f"<div class='muted small'>{escape(str(r['sub']))}</div>" if r.get("sub") else ""))
        + (f"<div class='axm'>{''.join(chip(c) for c in r['chips'])}</div>" if r.get("chips") else "") + "</div></div>"
        for r in info.get("rows") or [])
    detail = [f"{r['k']}：{r['text']}" + (f"（{r['sub']}）" if r.get("sub") else "") for r in info.get("rows") or [] if r.get("flow")]
    if info.get("never_tags"):
        detail.append(str(info.get("never") or ""))
    notes = "".join(f"<li>{escape(str(n))}</li>" for n in detail + list(info.get("notes") or []))
    never = ("<div class='axn'><span class='muted small'>不会因为</span>"
             + "".join(f"<span class='axx'>✕ {escape(str(x))}</span>" for x in info["never_tags"]) + "</div>"
             if info.get("never_tags") else f"<div class='muted small axn'>{escape(str(info.get('never') or ''))}</div>")
    return (f"<div class='axb{' hot' if info.get('hot') else ''}' data-exit='{escape(str(info.get('t') or ''))}'>"
            f"<div class='axh'><b>什么时候会自动卖</b><span class='muted small'>按 {escape(str(info.get('asof_md') or '—'))} 收盘</span></div>"
            + (f"<div class='axt'>{tiles}</div>" if tiles else "")
            + f"{rows}{never}"
            + (f"<details class='axd'><summary class='muted'>详细说明</summary><ul>{notes}</ul></details>" if notes else "")
            + "</div>")


def _buy_price_line(r: dict, fill: str | None = None) -> str:
    """规则的买价一行：出了信号 → 下一个交易日（fill）开盘最高 收盘 ×1.03（寄付指値；开盘价更高就不买）；还没出 → 出信号那天收盘 ×1.03
    （按今天收盘的参考）。盘中现价来了以后，K 线上面那行写「现在买：…」（/api/quotes 的 buy）。只是规则的上限，不是建议。"""
    b = r.get("buy") or {}
    lim, close = b.get("limit"), r.get("close")
    if not lim or not close:
        return ""
    if r.get("status") == "triggered":
        when = f"{str(fill)[5:7]}/{str(fill)[8:10]} 开盘" if fill and len(str(fill)) >= 10 else "下一个交易日开盘"
        return (f"<div class='small'>规则的买价：{when}、最高 <b>¥{float(lim):,.0f}</b>（= 收盘 ¥{float(close):,.0f} ×1.03；"
                "开盘价更高就不买）</div>")
    return (f"<div class='small muted'>规则的买价：出信号那天的收盘 ×1.03 是第二天开盘的最高价（按今天收盘 ≈ ¥{float(lim):,.0f}）</div>")


ESHITEN_SP = "https://kabuka.e-shiten.jp/mfds_smp.php"      # 立花 e支店的手机网站（注文一覧在这里看）


def _scheduled(label: str) -> bool:
    """这个定时任务的 plist 在不在（LaunchAgents 目录；QBREAK_LAUNCH_AGENTS 可改，测试用）。只看文件，不调 launchctl。"""
    agents = Path(os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")
    return (agents / f"{label}.plist").exists()


def _run_lines(tag: str, book: dict, now: dt.datetime, halt: str | None) -> list[tuple[str, str]]:
    """账本顶部的运行状态 → [(CSS 类 neg / muted, 已转义的 HTML)]（Mac 与手机同一个）：
    执行器上一次跑成没有（out/live_unified_<账本>_run.json，qbreak/run_status.py）、当前决策里被挡 / 被拒 / 状态不明的单（读账本：
    --resolve 登记之后马上消失）、交易日 08:00 之后今天早上的运行还没完成、今天 09:30 自检的结果与那条推送发成没有
    （out/watchdog_<账本>.json 的 ok / push）、设了外部心跳（可选）却没发成（同一个文件的 heartbeat）。
    文件没有 / 读坏 → 那一项不显示（不报错）。只展示，不改任何东西。"""
    from . import run_status as RS
    from .calendar_jp import prev_trading_day
    from .live_unified import lock_held, morning_done
    out: list[tuple[str, str]] = []
    now = now.astimezone(JST) if now.tzinfo else now
    today = now.date()
    paper = tag.startswith("paper")

    def at(v) -> tuple[str, bool]:                         # (「10/09 07:41」, 是不是今天)
        t = RS.ts(v)
        if t is None:
            return "—", False
        t = t.astimezone(JST)
        return t.strftime("%m/%d %H:%M"), t.date() == today
    st = book.get("state") or {}
    ld = st.get("last_date")
    rec = RS.read(tag)
    if rec:
        when, is_today = at(rec.get("at"))
        if rec.get("ok") is False:
            out.append(("neg", f"★ 执行器 {escape(when)} 停下：{escape(NM.annotate(str(rec.get('error') or '原因不明（看数据目录 logs/ 的 .err）')))}"))
        else:
            out.append(("muted", f"执行器：{escape(when)} 跑完 ✓（{escape(RS.PHASE_TEXT.get(rec.get('phase'), str(rec.get('phase') or '')))}）"))
        if rec.get("blocked"):
            day = "今天" if is_today else f"{when[:5]} "
            out.append(("neg", f"★ {escape(day)}的单没下：{escape(NM.annotate(str(rec['blocked'])))}"))   # 存下的文字只有代码 → 显示时补名字（2026-10-15）
    bad = RS.bad_orders(book.get("orders"), ld) if ld else []
    if rec and rec.get("decided_on") == ld:
        bad = RS.uncovered(bad, rec.get("blocked"))       # 「★ 今天的单没下」已经说了原因的，不再逐笔列
    if halt:                                               # HALT 挡下的：上面「HALT 生效中」已经说了
        bad = RS.actionable(bad)
    if any(o["status"] == "SENDING" for o in bad) and lock_held(paths.state_dir() / f"live_unified_{tag}.lock"):
        # 执行器正在运行（拿着运行锁）：SENDING 是正在发的单（发之前先存账本），不是状态不明 → 不叫人去核对 / 登记
        sending = [o for o in bad if o["status"] == "SENDING"]
        bad = [o for o in bad if o["status"] != "SENDING"]
        out.append(("muted", escape("发送中（执行器正在运行）：" + "、".join(
            f"{NM.label(o['ticker'])} {'买' if o['side'] == 'BUY' else '卖'} {o['qty']:,} {'口' if o['kind'] == 'core' else '股'}"
            for o in sending))))
    if bad:
        out.append(("neg", f"★ 有 {len(bad)} 笔被挡 / 被拒 / 状态不明（{escape(RS.bad_text(bad))}）："))
        for o in bad:
            unit = "口" if o["kind"] == "core" else "股"
            out.append(("neg", escape(f"・{NM.label(o['ticker'])} {'买' if o['side'] == 'BUY' else '卖'} {o['qty']:,} {unit} "
                                      f"{RS.STATUS_TEXT.get(o['status'], o['status'])}" + (f"：{NM.annotate(o['note'])}" if o["note"] else ""))))
        if not paper and any(o["status"] in ("ERROR", "SENDING") for o in bad):
            out.append(("neg", "状态不明的单：去立花网站的注文一覧核对（手机网站 "
                               f"<a href='{ESHITEN_SP}' target='_blank' rel='noopener noreferrer'>{ESHITEN_SP}</a>），再在 Mac 对话里登记"))
            unk = (rec or {}).get("unknown") if rec and rec.get("decided_on") == ld else None
            if unk:                                        # 执行器停下时查的注文一覧候选（只读；qbreak/live_ops.unknown_candidates）
                from .live_ops import unknown_text
                out.append(("neg", "注文一覧里的候选（执行器停下时查的；登记要你在 Mac 对话里确认）："))
                for ln in unknown_text(unk, drafts=False):
                    out.append(("neg", escape(ln.strip())))
    if st and not halt and is_trading_day(today) and now.time() >= dt.time(8, 0):
        exp = prev_trading_day(today).isoformat()          # 今天早上应该处理到的决策日
        # 模拟账户：装着 07:40 的定时任务（com.qbreak.liveu.paper）就一直算在用 —— 连着几天没跑更要提醒；
        # 没装（立花模式 / 不在 Mac 上）→ 只在账本最近两个交易日内动过时算（停用了的模拟账户不吵）
        in_use = (tag == "tachibana" or (tag == "paper" and _scheduled("com.qbreak.liveu.paper"))
                  or (bool(ld) and str(ld) >= prev_trading_day(prev_trading_day(today)).isoformat()))
        if in_use and (not ld or str(ld) < exp):
            out.append(("neg", f"★ 今天早上的运行还没完成（上次决策 {escape(str(ld or '—'))}）"))
        elif in_use and str(ld) == exp and not morning_done(book, exp):   # 决策做了、有单没下（G20：以前也写「运行还没完成」）
            from .live_unified import morning_unsent
            out.append(("neg", f"★ 今天早上的决策做了（决策日 {escape(exp)}），但有 {morning_unsent(book, exp)} 笔单没下（被挡 / 还没发）"))
    wd = RS.peek_json(paths.out_dir() / f"watchdog_{tag}.json")
    if isinstance(wd, dict):                               # 今天的 09:30 自检 + 每天那条推送发成没有（2026-10-14 起代替外部心跳）
        from .watchdog import push_text
        when, is_today = at(wd.get("at"))
        p = wd.get("push") if isinstance(wd.get("push"), dict) else None
        if is_today:
            rs = wd.get("reasons")
            rs = [rs] if isinstance(rs, str) else [str(x) for x in (rs if isinstance(rs, list) else [])]
            pt = push_text(p)
            if wd.get("ok") is False:
                out.append(("neg", f"★ 自检（{escape(when[6:])}）：{escape('；'.join(rs) or '没通过')}"))
            elif wd.get("ok") is None:
                out.append(("neg", f"★ 自检（{escape(when[6:])}）判定不了：{escape(str(wd.get('note') or '—'))}"))
            elif p and p.get("state") == "sent" and not pt:
                base = "通过（HALT 生效中）" if wd.get("halt") else (str(wd.get("note") or "") or "通过")
                out.append(("muted", f"自检（{escape(when[6:])}）：{escape(base)}；已推送到手机"))
            if pt:
                out.append(("neg", f"★ {escape(at(p.get('at') or wd.get('at'))[0])} {escape(pt)}"))
    if isinstance(wd, dict):                               # 外部心跳（可选）设了却没发成（09:30 自检记的；原因不含地址；2026-10-14 G12）
        from .watchdog import beat_text
        bt = beat_text(wd.get("heartbeat"))
        if bt:
            out.append(("neg", f"★ {escape(at((wd.get('heartbeat') or {}).get('at') or wd.get('at'))[0])} {escape(bt)}"))
    if tag == "tachibana":                                 # 前一晚预检（qbreak/precheck.py）：今天 / 昨晚没通过的原因、要动手的提醒
        from .precheck import last_result, panel_lines
        for ln in panel_lines(last_result(), now):
            out.append(("neg", escape(ln)))
    return out


def _input_lines(sm: dict, st: dict) -> list[tuple[str, str]]:
    """数据依赖的提醒（B10；Mac 与手机同一个）→ [(neg, 已转义的 HTML)]：执行器这次的汇总（out/live_unified_<账本>.json）里
    判断层的输入几天没更新（C-08）、行情有问题 + 修法（C-09）、行情落后的持仓今天的离场判断被跳过（LU-03）。
    汇总不是当前决策的（旧的）→ 不显示。只展示，不改任何东西。"""
    from .live_unified import YF_FIX, lag_exit_lines
    if not sm or not st or sm.get("decided_on") != st.get("last_date"):
        return []
    out: list[tuple[str, str]] = []
    si, dp = sm.get("stale_inputs") or {}, sm.get("data_problem") or {}
    if si.get("text"):
        out.append(("neg", escape(f"★ {si['text']}")))
    if dp:
        out.append(("neg", escape(f"★ 行情：{'；'.join(str(x) for x in dp.get('why') or [])}。修法：{dp.get('fix') or YF_FIX}")))
    for ln in lag_exit_lines(sm.get("lag_exits")):
        out.append(("neg", escape(f"★ {ln}")))
    return out


def _quote_peek(tag: str, now: dt.datetime) -> dict:
    """现价缓存里这个账本今天取到的每只票最新的现价 → {票: 现价}（不联网：「今天还能买几次」只用页面已经取过的；没有 → 收盘估）。"""
    with _QUOTE_LOCK:
        items = list(_QUOTE_CACHE.items())
    best: dict = {}
    today = now.date().isoformat()
    for (tg, _k), (at, q) in items:
        if tg != tag or not isinstance(q, dict):
            continue
        for t, x in q.items():
            if isinstance(x, dict) and x.get("px") and str(x.get("at") or "")[:10] == today and (t not in best or at > best[t][0]):
                best[t] = (at, float(x["px"]))
    return {t: v[1] for t, v in best.items()}


def room_of(tag: str, book: dict, sm: dict, now: dt.datetime, trigger: "Trigger | None" = None, waiting: list | None = None) -> dict:
    """「今天还能买几次 / 卖几次」（D6；qbreak/trade_room.room）：交易页的卡片、持仓的小标记、/api/trade_room 同一个数。
    面板盘中自动下单今天暂停（Trigger.paused）→ 只写一句（写新的指令就恢复）。"""
    pz = trigger.paused.get(tag) if trigger is not None else None
    paused = (pz[1] or True) if pz and pz[0] == now.date().isoformat() else False
    return TR.room(tag, book, now, quotes=_quote_peek(tag, now), waiting=waiting, sm=sm, paused=paused)


def trade_room_json(tag: str, now: dt.datetime | None = None, trigger: "Trigger | None" = None) -> tuple[int, dict]:
    """/api/trade_room?book=…（交易页的卡片每 1 分钟（盘中）/ 10 分钟刷新）。算不出 → 200 + ok=false（页面保留上一次的）。"""
    now = now or now_jst()
    try:
        book, sm = _load(tag)
        return 200, {"ok": True, **room_of(tag, book, sm, now, trigger)}
    except Exception as e:                                  # noqa: BLE001  展示用：一个读不了的数不让页面报错
        log.warning("/api/trade_room 没算成（%s：%s）", type(e).__name__, e)
        return 200, {"ok": False, "msg": "今天还能买几次 / 卖几次：这次没算成（稍后自动再算）"}


def _room_side(r: dict, side: str) -> str:
    """每只一行里的一边：「卖：最多 4,110 口 · 用「卖出全部」/「调仓…」…」/「买 ✗：现在能用的现金 ¥190 不够买 1 个单元…」。"""
    x = r[side]
    w = "卖" if side == "sell" else "买"
    u = "口" if r.get("kind") == "core" else "股"
    if x["n"]:
        return f"{w}：最多 {int(x['max_qty']):,} {u}" + (f" · 用{x['via']}" if x.get("via") else "")
    why = (x.get("why") or ["不能"])[0]
    return f"{w} ✗：{why}" + (f"（{x['next']}）" if x.get("next") and x["next"] not in why else "")


def _room_card(rm: dict | None) -> str:
    """交易页最上面的小卡（D6；2026-10-15 用户要求 3）：「今天还能：买 N 次 · 卖 M 次 · 共 K 次」+ 一行时段 + 展开看为什么、每只（代码带名字）。
    页面脚本（static/room.js 的 roomShow）按 /api/trade_room 重画同一个样子。不是建议：候选只数「能不能」。"""
    if not rm:
        return "<section class='card' id='room' hidden></section>"
    ov = rm["overall"]
    H = [f"<section class='card' id='room'><div class='rm-hl'><b>{escape(rm['headline'])}</b></div>",
         f"<div class='small'>{escape(rm['market']['line'])}</div>"]
    H += [f"<div class='neg small'>★ {escape(w)}</div>" for w in rm.get("gates") or []]
    H += [f"<div class='muted small'>· {escape(w)}</div>" for w in rm.get("notes") or []]
    H.append("<details class='rm'><summary class='muted small'>为什么是这个数 · 每只</summary>")
    H += [f"<div class='small'>{w} {int(ov[k]['n'])}：{escape(ov[k]['why'])}</div>"
          for k, w in (("buy_left", "买"), ("sell_left", "卖"), ("trades_left", "共"))]
    for r in rm["per_ticker"].values():
        if r.get("cand"):
            continue
        H.append(f"<div class='li'><div class='grow'><b>{escape(r['label'])}</b> <span class='chip'>{escape(r['chip'])}</span>"
                 f"<div class='muted small'>{escape(_room_side(r, 'sell'))}</div><div class='muted small'>{escape(_room_side(r, 'buy'))}</div></div></div>")
    c = rm.get("cands") or {}
    if c.get("n"):
        g = "、".join(f"{k} {v} 只" for k, v in sorted((c.get("groups") or {}).items(), key=lambda kv: -kv[1]))
        H.append(f"<div class='muted small'>选股页的候选 {int(c['n'])} 只：名额与钱都够的 {int(c['ok'])} 只" + (f"；不能：{escape(g)}" if g else "")
                 + "（只是数，不是建议；买不买是你的决定）</div>")
    H.append("</details>")
    H.append(f"<div class='muted small'>{escape(rm['note'])}（差金決済：<a href='{escape(rm['sakin_url'])}' target='_blank' rel='noopener'>"
             "立花 e支店的说明</a>，2026-10-15 核对）</div></section>")
    return "".join(H)


def _room_chip(rm: dict | None, t: str) -> str:
    """持仓卡片每只的小标记「今天还能卖 ✓ / 买 ✗（原因）」（static/room.js 按 /api/trade_room 更新文字）。"""
    r = ((rm or {}).get("per_ticker") or {}).get(t)
    return f"<div class='room small muted' data-room='{escape(t)}'>{escape(r['chip']) if r else ''}</div>"


# ───────────────────────── 盘中观测（qbreak/intraday_watch.py；2026-10-16 用户要求；只展示）─────────────────────────
INTRADAY_POLL_S = 30                    # 线程多久看一次（到 5 分钟才真的叫）
INTRADAY_LOG = IW.LOG_NAME              # 数据目录 logs/com.qbreak.panel.intraday.log


def intraday_json(tag: str, now: dt.datetime | None = None) -> tuple[int, dict]:
    """/api/intraday?book=…（选股页的「今天盘中」卡片、持仓每只一行；页面每 1 分钟刷新）：只读 out/intraday_<账本>.json
    （面板的线程另起进程写的），请求里不取价、不算区间。读不了 → 200 + ok=false（页面保留上一次的）。"""
    try:
        return 200, IW.view(IW.load(tag), now or now_jst())
    except Exception as e:                                  # noqa: BLE001
        log.warning("/api/intraday 读不了（%s：%s）", type(e).__name__, e)
        return 200, {"ok": False, "msg": "盘中观测读不了"}


def _intraday_card(v: dict | None) -> str:
    """选股页最上面「今天盘中：规则的买点（暂定，约晚 20 分钟）」（static/intraday.js 的 intraShow 按 /api/intraday 重画同一个样子）。
    每行：代码 + 名字、区间 ¥下沿〜¥上沿、离下沿 %、成交量到所需的 %、挡住的闸门、数据时刻；其余收起「今天不可能：N 只（理由）」。"""
    if not v or not v.get("ok"):
        return f"<section class='card' id='intraday'><div class='ia-hl'><b>{escape(IW.TITLE)}</b></div><div class='muted small'>盘中观测读不了</div></section>"
    H = [f"<section class='card' id='intraday'><div class='ia-hl'><b>{escape(v['title'])}</b></div>",
         f"<div class='muted small'>{escape(v['head'])}</div>"]
    H += [f"<div class='neg small'>★ {escape(w)}</div>" for w in v.get("warn") or []]
    if v.get("rows"):
        H.append("<div class='list'>")
        for r in v["rows"]:
            ga = " · ".join(x for x in (r.get("gates"), r.get("at")) if x)    # 只这只自己的闸门 / 数据时刻（共同的在顶上 ★）
            H.append(f"<div class='li'><div class='grow'><b>{escape(r['label'])}</b> <span class='chip{' hot' if r.get('kind') == 'ok' else ''}'>"
                     f"{escape(r['status'])}</span><div class='small'>{escape(r['line'])}</div>"
                     + (f"<div class='muted small'>{escape(ga)}</div>" if ga else "") + "</div></div>")
        H.append("</div>")
    if v.get("none"):
        H.append(f"<div class='small'>{escape(v['none'])}</div>")
    if v.get("impossible"):
        H.append(f"<details class='ia'><summary class='muted small'>{escape(v['impossible'])}</summary>")
        H += [f"<div class='muted small'>{escape(g['why'])}：{escape(g['names'])}</div>" for g in v.get("groups") or []]
        H.append("</details>")
    H.append(f"<div class='muted small'>{escape(v['foot'])}</div></section>")
    return "".join(H)


def _intraday_line(v: dict | None, t: str) -> str:
    """持仓每只一行：收盘卖出线离现价多远（static/intraday.js 按 /api/intraday 更新文字）。"""
    s = ((v or {}).get("hold") or {}).get(t) or ""
    return f"<div class='ia small muted' data-intra='{escape(t)}'>{escape(s)}</div>"


def _intraday_books() -> list[str]:
    """盘中观测算哪几个账本：模拟账户；有立花本番的账本时也算立花。"""
    return ["paper"] + (["tachibana"] if (paths.state_dir() / "live_unified_tachibana.json").exists() else [])


def _intraday_run(tag: str, timeout: float = IW.TIMEOUT_S) -> int | None:
    """另起进程算一次（python -m qbreak.intraday_watch --book …；同一个数据目录 / 环境）；最多等 timeout 秒，到时间就结束它。"""
    cmd = [sys.executable, "-m", "qbreak.intraday_watch", "--book", tag]
    with open(paths.log_dir() / INTRADAY_LOG, "a", encoding="utf-8") as lf:
        lf.write(f"\n── {now_jst():%Y-%m-%d %H:%M:%S} JST 盘中观测 {tag}\n")
        lf.flush()
        pr = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(paths.PROJECT_ROOT), start_new_session=True,
                              env=dict(os.environ))
        try:
            return pr.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pr.kill()
            try:
                pr.wait(5)
            except subprocess.TimeoutExpired:
                pass
            lf.write(f"── 超过 {timeout:.0f} 秒没算完：结束这一次\n")
            return None


def _intraday_due(tag: str, now: dt.datetime, last: dict) -> bool:
    """这个账本该算了吗：这个进程里上一次叫过之后满 5 分钟；刚启动 / 平滑重启后 → 看结果文件的时刻（不在重启后马上重复算）。"""
    if tag in last:
        return time.monotonic() - last[tag] >= IW.EVERY_S - 5
    try:
        upd = dt.datetime.fromisoformat(str((IW.load(tag) or {}).get("updated")))
        return (now - upd).total_seconds() >= IW.EVERY_S - 30
    except (TypeError, ValueError):
        return True


def _intraday_tick(now: dt.datetime | None = None, last: dict | None = None, run=None) -> list[str]:
    """一轮：交易时段里、到时间的账本一个接一个算（不重叠）；返回这次算了的账本。"""
    now = now or now_jst()
    last = {} if last is None else last
    try:
        from .calendar_jp import reload_extra_closed
        reload_extra_closed()                               # 临时休市（run.py extra-closed）当天加的也算上
    except Exception:                                       # noqa: BLE001
        pass
    if not IW.in_window(now):
        return []
    done = []
    for tag in _intraday_books():
        if not _intraday_due(tag, now, last):
            continue
        last[tag] = time.monotonic()
        (run or _intraday_run)(tag)
        done.append(tag)
    return done


def _intraday_loop(stop: threading.Event, every: float = INTRADAY_POLL_S, tick=None) -> None:
    """面板里的线程：每 every 秒看一次（交易时段、到 5 分钟才真的另起进程算）；出错只记日志、不停。平滑重启后新进程照样再起一个。"""
    last: dict = {}
    while True:
        try:
            (tick or _intraday_tick)(None, last)
        except Exception as e:                              # noqa: BLE001
            log.warning("盘中观测的线程出错（继续）：%s", e)
        if stop.wait(every):
            return


def _order_rows(book: dict, now: dt.datetime, paper: bool, waiting: list, live: dict | None = None,
                tag: str | None = None) -> tuple[list[tuple[str, str]], dict]:
    """执行器的单每笔一行（Mac 与手机同一个）：账本当前决策里执行器的单（票、买卖、股数、下法、限价、状态）。还挂着的单（SENT / PARTIAL，
    今天的、立花有注文番号）给「撤单」按钮 → 写撤单指令（kind cancel_order），面板马上叫执行器撤（qbreak/live_ops.py）；
    已经写了撤单指令的显示「撤单中」。立花 API / Mac 出故障那天：照这张表在立花网站下单，之后在 Mac 对话里说一声人工代下登记（adopt）。
    不会再做事的单（_trade_live：凑钱的卖单撤了、开盘时一定买不起 / HALT / 已收盘）把状态换成「不会下单（预计）」等并写原因，
    固定口数还有效时提醒下一次决策还会再排（2026-10-15）；卖单的「撤单」确认框列出靠这笔卖出的钱、撤了就下不成的买单（data-deps）。
    D2（2026-10-15）：执行器还没发出的单（计划 / 等开盘后）也给「撤单」（撤 = 执行器不再发）；撤之后会怎样按单的来源写（data-hint：LO.cancel_hint）；
    卖单有靠它的钱的买单（执行器记的 fund_src）→ 确认框给几个按钮（data-depn / data-keep / data-fix）：「一起撤买单」「只撤卖单（买 X 不会下 /
    减到 N 口 / 照常）」，买单是固定口数排的再加「撤单并恢复按规则」；会怎样用 LO.fund_cascade(apply=False) 预览（与撤单那一刻执行器的重算同一个函数）。
    旧账本（没有 fund_src）：撤之前 / 之后各算一次 LO.outlook 写说明。核心单写来源（D7：src_txt「为你的『固定 …』凑钱（… 写）」，
    确认框的 data-hint 也以它开头）；旧账本没有 → 照旧。只展示 + 写指令，不改账本。
    2026-10-16（用户：「交易里面只显示当天要成交的单」）：以前这里直接拼成「今天的单」一张卡片；现在只出每一行，放进哪一块（今天要成交 /
    另有 … / 已结束）由 _trade_split 决定、_trade_sections 拼（同一组的说明、按钮照旧每行都有，分在不同块也一样）。
    → ([(cid, 一行的 HTML)]（账本里的顺序）, {"f": 成交日, "stale": 今天早上的运行还没跑, "grp": 有同一组})；没有单 → ([], …)。"""
    from . import live_ops as LO
    st = book.get("state") or {}
    d = st.get("last_date")
    orders = [o for o in book.get("orders") or [] if o.get("decided_on") == d]
    f = LO.fill_day_of(book)
    stale = f is not None and f != now.date()               # 今天早上的运行没跑：这还是上一次决策的单（不是今天要下的）
    if not orders:
        return [], {"f": f, "stale": stale, "grp": False}
    live = live or _trade_live(book, waiting, now, tag)
    asked, dead, fixn = live["asked"], live["orders"], live["fix"]
    shown = set((live.get("split") or {}).get("notes") or ())   # 已经写在「今天要成交的单」上面的固定口数提醒：那一行不再重复（复核 7）
    base = None
    G = LO.groups(orders, book)                             # 一起下的单（整组撤单；2026-10-16 用户：一起下的买单和卖单要能一起撤）
    byc = {str(x.get("cid")): x for x in orders}
    jobs = LO.cancel_jobs(book, waiting, now, G)            # 还在处理的撤单：盖着的单不给「撤单」（同一组同时只有一个撤单；简化 2026-10-16）
    cfix = MO.core_fixed(book, tag) if G or any(x.get("kind") == "core" and x.get("side") == "BUY" for x in orders) else {}
    lkg: dict = {}                                          # 每一组：靠这一组卖单的钱、已经发出的买单（LO.fund_linked：整组撤单的范围里也有它们，
    lk_of: dict = {}                                        #   「同一组 N 笔」与确认框、执行器的汇总同一个数；复核 8 2026-10-16）
    for gl_ in {tuple(v) for v in G.values()}:
        xs = [str(x.get("cid")) for x in LO.fund_linked([byc[c] for c in gl_ if c in byc], orders, book)]
        lkg[gl_[0]] = xs
        for c in xs:
            lk_of.setdefault(c, gl_[0])
    rows = []
    for o in orders:
        core = o.get("kind") == "core"
        unit = "口" if core else "股"
        n = int(o.get("sent_qty") or o.get("qty") or 0)
        lim = f"，限价 ≤ ¥{float(o['limit']):,g}" if o.get("limit") and o.get("side") == "BUY" else ""
        q = int(o.get("filled_qty") or 0)
        px = float(o.get("filled_px") or 0)
        got = (f"，成交 {q:,}/{n:,}" if q and o.get("status") in ("PARTIAL", "CANCELLED", "EXPIRED") else
               f"，成交 {q:,}{f'/{n:,}' if q < n else ''} @ ¥{px:,.2f}" if q and px > 0 and o.get("status") == "FILLED" else "")
        #   ↑ 已成交写成交价（模拟账户 09:25 前后的开盘撮合之后交易页马上看到；D3，2026-10-15）
        note = str(o.get("note") or "")
        cid = str(o.get("cid"))
        cw = LO.cancel_why(o, book, now, paper)
        busy = None if cid in asked or cw is not None else LO.cancel_conflict({"cid": cid}, book, jobs, G)
        #   ↑ 本来就撤不了的行（已成交 / 已撤…）不写「等它结束再撤」（复核 6 2026-10-16）
        if cid in asked:                                    # 撤单暂停中（outlook cls stuck）：状态那里已经写了，不再写「撤单中」（复核 7）
            btn = "" if cid in (live.get("stuck") or ()) else "<span class='chip'>撤单中</span>"
        elif busy:                                          # 同一组 / 有关的单正在撤单：这一行等它结束（与 check、执行器同一个判断）
            btn = "<span class='chip'>" + ("同一组撤单中" if busy.startswith("同一组") else "撤单中" if "已经在撤" in busy
                                           else "有关的单撤单中") + "</span>"
        elif cw is None:
            deps, alt, keep_txt, afx = "", "", "", ""
            dx = LO.deps_of(o, orders) if o.get("side") == "SELL" else []
            if dx:                                          # 执行器记了靠这笔卖出的钱的买单（fund_src；D2）：预览撤掉之后它们会怎样
                try:
                    pv = {str(r["o"].get("cid")): r for r in LO.fund_cascade(
                        orders, cash=_cash_hi(book, tag) - LO._reserve_of(book, paper), now=now, book=book, dead={cid}, apply=False,
                        fill=f, queued=paper) if cid in [str(x.get("cid")) for x in r["srcs"]]}
                except (TypeError, ValueError, KeyError):  # 账本里的数读不了：不预览（只写有哪几笔）
                    pv = {}
                fixed = MO.core_fixed(book, tag)
                bits, kw = [], []
                for b in dx:
                    u = "口" if b.get("kind") == "core" else "股"
                    r = pv.get(str(b.get("cid")))
                    w = ("按现在的钱重算" if r is None else "不会下" if r["act"] == "skip"
                         else f"减到 {int(r['qty']):,} {u}" if r["act"] == "reduce" else "照常")
                    q_txt = f"{int(b.get('qty') or 0):,} {u}"     # 先算好数量文字（Python 3.10 / 3.11 不允许 f-string 里嵌套同种引号）
                    bits.append(f"买 {NM.qty(b.get('ticker'), q_txt)}（只撤卖单 → {w}）")
                    kw.append(f"买 {NM.label(b.get('ticker'))} {w}")
                deps = "靠这笔卖出的钱、执行器还没发出的买单：" + "、".join(bits) + "（已经成交的部分卖出的钱照样能用）"
                fx = next((str(b.get("ticker")) for b in dx if b.get("kind") == "core" and b.get("ticker") in fixed), "")
                keep_txt = "只撤卖单（" + "；".join(kw) + "）"
                afx = fx
                alt = (f" data-depn='{len(dx)}' data-keep='{escape(keep_txt)}'"
                       + (f" data-fix='{escape(fx)}' data-fixname='{escape(NM.name(fx) or '')}'" if fx else ""))
            elif o.get("side") == "SELL":                   # 旧账本（没有 fund_src）：靠这笔卖出的钱的买单撤了就下不成（只是确认框里说明；2026-10-15）
                try:                                        # 撤之前 / 撤之后各算一次 outlook（D5：与交易页、自检、撤单推送同一个判断）
                    base = (LO.outlook(book, waiting, now, tag=tag, halt=False, asked=asked, instr=False) if base is None else base)
                    after = LO.outlook(book, waiting, now, tag=tag, halt=False, asked=set(asked) | {cid}, instr=False)
                except (TypeError, ValueError, KeyError):  # 账本里的数读不了：不写（只是说明）
                    base, after = base or {"orders": {}}, {"orders": {}}
                bad = {c for c, r in after["orders"].items() if r["cls"] == "fund"} - {
                    c for c, r in base["orders"].items() if r["cls"] == "fund"}
                hit = [b for b in orders if str(b.get("cid")) in bad and str(b.get("cid")) not in dead]
                if hit:
                    deps = ("撤掉之后，今天等这笔卖出的钱的买单预计下不成（开盘时现金不够一单元）："
                            + "、".join("买 " + NM.qty(b.get('ticker'), f"{int(b.get('qty') or 0):,} {'口' if b.get('kind') == 'core' else '股'}") for b in hit)
                            + "（已经成交的部分卖出的钱照样能用）")
            grp = _grp_attrs(o, orders, byc, G, book, now, paper, tag, asked, cfix, alt, keep_txt, alt_fix=afx)
            btn = (f"<button class='btn sm danger' data-act='cancel-order' data-cid='{escape(cid)}' "
                   f"data-t='{escape(str(o.get('ticker')))}' data-side='{escape(str(o.get('side')))}' data-qty='{n}' "
                   f"data-core='{1 if core else 0}' data-unsent='{1 if o.get('status') in LO.UNSENT else 0}' "
                   f"data-hint='{escape((LO.src_line(o) + '。' if LO.src_line(o) else '') + LO.cancel_hint(o, book, now, tag))}'" + (f" data-deps='{escape(deps)}'" if deps else "") + alt
                   + grp + f" data-name='{escape(NM.name(o.get('ticker')) or '')}'>撤单</button>")      # 名字放最后（确认框标题；2026-10-15）
        else:
            btn = ""
        chip, why = dead.get(cid) or (LO._st_txt(o) if LO.GONE in note else LO.STATUS_TEXT.get(o.get("status"), str(o.get("status"))), "")
        #   ↑ 撤单时立花回已经失效 / 被拒：不写「已下单（等成交）」（简化 2026-10-16）
        if note and chip.startswith("不会下单"):              # 执行器排单时写的打算（「开盘后按始値检查、减股再下」）已经不会发生：标成原先的（2026-10-15 复核）
            note = "原先：" + note
        elif cid in (live.get("rerun") or {}):              # 模拟账户开盘撮合的窗口过了：哪次运行按成交日的开盘价撮合（复核 4）
            note = live["rerun"][cid]
        gm = G.get(cid) or []
        lk = lkg.get(gm[0], []) if gm else []
        og = f" og' data-g='{escape(gm[0])}" if gm else ""  # 同一组的每一行：左边一条线 + 「同一组 N 笔」+ 还有哪几笔
        gchip = f" <span class='chip'>同一组 {len(gm) + len(lk)} 笔</span>" if gm else ""
        gline = ""

        def _gtxt(x) -> str:
            xn = int(x.get("sent_qty") or x.get("qty") or 0)
            xq = f"{xn:,} {'口' if x.get('kind') == 'core' else '股'}"
            return ("买" if x.get("side") == "BUY" else "卖") + " " + NM.qty(x.get("ticker"), xq) + "（" + LO._st_txt(x) + "）"
        if gm:
            gl = [_gtxt(byc[c]) for c in gm if c in byc and c != cid]
            gl += [_gtxt(byc[c])[:-1] + "，靠这一组卖单的钱买的、不是一起下的）" for c in lk if c in byc]
            gline = f"<div class='small'>{escape('同一组（一起下的）还有：' + '、'.join(gl))}</div>"
        elif cid in lk_of:                                  # 靠一组卖单的钱、已经发出的买单：整组撤单把它算在那一组里
            gchip = " <span class='chip'>算在同一组里</span>"
            ss = [_gtxt(byc[c]) for c in G.get(lk_of[cid]) or [] if c in byc and byc[c].get("side") == "SELL"]
            tail = ("那一组整组撤单会一起撤这一笔" if LO.grp_why(o, book, now, paper) is None
                    else "这一笔撤不了：那一组整组撤单时卖单因此不撤")
            gline = f"<div class='small'>{escape('靠这一组卖单的钱买的（不是一起下的）：' + '、'.join(ss) + '；' + tail)}</div>"
        rows.append((cid, f"<div class='li{og}'><div class='grow'><b>{'买' if o.get('side') == 'BUY' else '卖'} {escape(NM.qty(o.get('ticker'), f'{n:,} {unit}'))}"
                    f"</b> <span class='chip'>{escape(chip)}</span>{gchip}"
                    + gline
                    + (f"<div class='neg small'>{escape(why)}</div>" if why else "")
                    + (f"<div class='small'>{escape(busy)}</div>" if busy else "")
                    + (f"<div class='small'>{escape(fixn[cid])}</div>" if cid in fixn and fixn[cid] not in shown else "")
                    + (f"<div class='small'>{escape(LO.src_line(o))}</div>" if LO.src_line(o) else "")   # 核心单的来源（D7：固定口数 / 凑钱 / 比例 / 规则）
                    + f"<div class='muted small'>{escape(LO.how_text(o, paper) + lim + got)}"
                    f"{(' · ' + escape(NM.annotate(note)[:160])) if note else ''}</div></div>{btn}</div>"))
    return rows, {"f": f, "stale": stale, "grp": bool(G)}


def _grp_attrs(o: dict, orders: list, byc: dict, G: dict, book: dict, now: dt.datetime, paper: bool, tag: str | None, asked,
               cfix: dict, alt: str, keep_txt: str = "", *, alt_fix: str = "") -> str:
    """「撤单」按钮上整组撤单的属性（2026-10-16；插在 data-name 之前，已有的属性不变）：
    data-grp（同一组里现在能撤、没在撤的其他单 cid，买单在前；超过 GROUP_MAX 不写）/ data-glist（确认框里一行行的说明）/
    data-solo（「只撤这一笔」的按钮文字）；固定口数还有效 → data-fix / data-fixname（「整组撤单并恢复按规则」；已经写了的不重复）。
    复核（2026-10-16）：没有 data-grp（同一组的其他单现在不能一起撤）→ 确认框只撤这一笔，data-glist 写「只撤这一笔」的说明（不写整组撤单）；
    卖单、同一组的买单还可能花钱（LO.solo_holds）→ data-solok='1'（确认框的按钮写「只撤这笔卖单」、指令写 deps=keep：执行器的闸门不再挡）。
    data-fix：点的这一行自己是固定口数的 ETF 买单 → 它；否则同一组第一笔固定口数的买单（alt_fix：data-deps 那边已经写了的）。
    复核 2（2026-10-16）：data-grp 照 LO.group_view（闸门预判：同一组有买单撤了也还会花钱 → 不给整组撤单）；能一起撤的比这一组少 →
    data-gn（这一组几笔：按钮写「整组撤单（能撤的 N 笔）」）；只撤这一笔、卖单有靠它的钱的买单（data-depn）、同一组的买单还可能花钱 →
    data-depk（「一起撤买单」改写成「撤买单（卖单不撤）」：执行器就是这么做的）。
    复核 3（2026-10-16）：data-depk / data-depw / data-depx 照 LO.legacy_plan（与执行器的「一起撤买单」同一个范围）：撤完之后还有买单会花钱 →
    data-depk；没有、但要先撤在交易所 / 已经在撤的买单 → data-depw（买单撤掉了（没成交）才撤卖单）；「一起撤买单」也发撤单撤在交易所的买单 →
    data-depx。不在一组里、只有「一起撤买单」的卖单也写 data-glist。"""
    from . import live_ops as LO
    cid = str(o.get("cid"))
    gm = G.get(cid) or []
    fix, fx = "", ""                                       # 固定口数（data-fix）紧跟已有的 depn / keep 之后（属性顺序不变）
    if "data-fix=" not in alt:
        if o.get("side") == "BUY" and o.get("kind") == "core" and o.get("ticker") in cfix:
            fx = str(o.get("ticker"))
        elif gm:
            fx = next((str(byc[c].get("ticker")) for c in gm if c in byc and byc[c].get("side") == "BUY"
                       and byc[c].get("ticker") in cfix), "")
        if fx:
            fix = f" data-fix='{escape(fx)}' data-fixname='{escape(NM.name(fx) or '')}'"
    out = ""
    ok: list = []
    deps = o.get("side") == "SELL" and "data-depn=" in alt
    if gm:
        oth = [byc[c] for c in gm if c != cid and c in byc]
        v = LO.group_view(o, orders, book, now, paper, asked)   # 与确认框、执行器同一个判断（复核 2 2026-10-16：买单已经成交 / 部分成交 /
        ok = v["ok"]                                           # 状态不明 → 整组撤单一笔卖单都不会撤 → 不给「整组撤单」，只撤这一笔）
        if ok:
            out += f" data-grp='{escape(','.join(ok))}'"
            if len(ok) + 1 < len(v["mem"]):                # 同一组还有不能一起撤的：按钮写「能撤的 N 笔」（与「同一组 N 笔」对得上；
                out += f" data-gn='{len(v['mem'])}'"       #   靠这一组卖单的钱、已经发出的买单也算：与执行器的汇总一样；复核 6）
            if any(byc[c].get("status") in LO.CANCELLABLE for c in [cid] + list(ok) if c in byc):
                out += " data-gexch='1'"                   # 范围里有在交易所的单：确认框才写「马上发撤单到立花」（复核 6）
    if gm or deps:                                         # 不在一组里、有靠它的钱的买单：「一起撤买单」也撤在交易所的 / 会留下卖单时也写（复核 3）
        gl = LO.group_lines(o, orders, book, now, paper, tag, asked, solo=not ok, fix_t=(fx or alt_fix or None))
        if gl:
            out += f" data-glist='{escape(chr(10).join(gl))}'"
    if ok:
        if o.get("side") == "BUY":
            ss = [NM.label(x.get("ticker")) for x in oth if LO.still_sells(x, now, LO.fill_day_of(book))]   # 真的还会卖的（不算立花那边已经失效 /
            #   撤单已受理 / 不会再发的；简化 2026-10-16：以前写「卖 X 照常卖」，那笔其实已经没了）
            solo = ("只撤这笔买单（卖 " + "、".join(dict.fromkeys(ss)) + " 照常卖，钱留现金）") if ss else "只撤这笔买单"
        else:
            solo = keep_txt or "只撤这笔卖单"                    # 有靠它的钱的买单：与「只撤卖单（买 X 不会下）」同一句
        out += f" data-solo='{escape(solo)}'"
        if o.get("side") == "SELL":                        # 「只撤这笔卖单」、同一组的买单还可能花钱：与单笔的确认框同一行 ★（复核 6 2026-10-16）
            hs = [LO._hold_star(c, k, t, byc.get(c), book, now, paper, set(asked or ()), "只撤卖单" if keep_txt else "只撤这笔卖单",
                                pre="同一组的" if c in gm else "靠这一组卖单的钱的")   # 靠这一组卖单的钱、已经发出的买单也挡（复核 8）
                  for c, k, t in LO._solo_holds(o, orders, book, now, G)]
            if hs:
                out += f" data-soloh='{escape(chr(10).join(hs))}'"
        return fix + out
    if gm and o.get("side") == "SELL" and LO.solo_holds(o, orders, book, now, G):
        out += " data-solok='1'"
    if deps:                                               # 「一起撤买单」（deps=cancel）执行器会怎么做（LO.legacy_plan；复核 3 2026-10-16）：
        lp = LO.legacy_plan(o, orders, book, now, paper, asked, G)   # 撤完之后还有买单会花钱 → 卖单一定不撤：按钮叫「撤买单（卖单不撤）」；
        if lp["keep"]:                                     # 没有、但要先撤在交易所 / 已经在撤的买单 → 买单撤掉了（没成交）才撤卖单（data-depw）
            out += f" data-depk='{escape(LO.DEPK)}'"       # （以前同一组的买单还可能花钱就写「卖单不撤」，执行器却先撤了那笔买单、再撤卖单）
        elif lp["exch"] or lp["ask"]:
            out += " data-depw='1'"
        if lp["exch"]:                                     # 「一起撤买单」也发撤单撤在交易所的买单
            out += " data-depx='1'"
    return fix + out


PANE = "\x00PANE:"                                         # render 里的分组标记（_panes 用；不会出现在页面上）
# 标签页（2026-10-11 用户：「总览的都分开、不要很长、每个部分归类成可以点的标签、一眼看上去就知道里面是什么」）
TABS = {"home": ("⌂", "总览", "账户现在怎样：总权益、今天的运行有没有问题、损益与已实现、最近成交、日志"),
        "hold": ("▤", "持仓", "现在拿着的个股与闲置资金 ETF：为什么拿、走势、卖出 / 调仓；立花那边的实际持仓"),
        "trade": ("⇄", "交易", "今天要成交的单（执行器下的，可撤）与今天做的手动指令；之后才下的、已结束的、卖出后不买回的票收在下面"),
        "pick": ("☆", "选股", "规则的候选：出信号的、快要出的、观察中的，买入前看价格与 K 线"),
        "news": ("⚠", "消息", "qbreak 发出的通知的记录，和经济威胁消息（内容、时间、可信度、影响的行业和持仓）；推送点开到这里"),
        "more": ("⋯", "更多", "通知设置、手机、上线准备、紧急停止（HALT）")}


def _panes(H: list, on: str | None = "home") -> str:
    """把 render 的片段按 PANE 标记包成 <div class='pane' data-tab=…>（同一个标签可以有几段，顺序照旧）；每个标签第一段前加一行说明。
    on：服务器先显示的标签（class 'pane on'；2026-10-15「网页app经常卡住」：以前全靠脚本加 on，一个模块没载入整页空白、按钮都点不动）。"""
    on = on if on in TABS else "home"
    out, cur, seen = [], None, set()
    for h in H:
        if isinstance(h, str) and h.startswith(PANE):
            if cur:
                out.append("</div>")
            cur = h[len(PANE):] or None
            if cur:
                ic, lab, desc = TABS[cur]
                head = "" if cur in seen else f"<div class='panehead'><b>{ic} {escape(lab)}</b><span>{escape(desc)}</span></div>"
                seen.add(cur)
                out.append(f"<div class='pane{' on' if cur == on else ''}' data-tab='{cur}'>{head}")
            continue
        out.append(h or "")
    if cur:
        out.append("</div>")
    return "".join(out)


CANCEL_KINDS = ("cancel", "cancel_order", "uncancel")    # 撤回 / 撤单 / 撤销撤回：本身不是买卖，不算「还会做事」


def _cash_hi(book: dict, tag: str | None) -> float:
    """开盘时能用的现金的上限（unfunded_buys 用）：live_ops.cash_hi（确认框 / 提交说明也用同一个；2026-10-15 复核）。"""
    from . import live_ops as LO
    return LO.cash_hi(book, tag)


def _trade_live(book: dict, waiting: list, now: dt.datetime, tag: str | None = None, halt: bool | None = None) -> dict:
    """_trade_live_calc，算不成（账本里有读不了的数：旧执行器写的 None、不是数字的口数…）→ 记日志、按以前的数法（等着的指令 + 还在处理的
    指令）给数字（2026-10-15 复核：/api/status 是页面的连接检查、页面本身也用它 —— 以前一个读不了的数就 500，手机上显示「连不上 Mac」）。"""
    try:
        return _trade_live_calc(book, waiting, now, tag, halt)
    except Exception as e:                                 # noqa: BLE001  只是数字与说明：不能让页面 / 连接检查打不开
        log.warning("「交易」的数字没算成（%s：%s）：按等着的指令 + 还在处理的指令数", type(e).__name__, e)
    try:
        items = ((book.get("manual") or {}).get("items") or {}).values()
        k = len(waiting) + sum(1 for it in items if isinstance(it, dict) and it.get("status") in MO.ACTIVE)
        asked = {c for r in waiting if isinstance(r, dict) and r.get("kind") == "cancel_order" for c in MO.cancel_cids(r)}   # 整组撤单：同一组的每一笔
    except Exception:                                      # noqa: BLE001
        k, asked = 0, set()
    return {"orders": {}, "fix": {}, "items": set(), "itxt": {}, "asked": asked, "n": k, "busy": k}


def _trade_live_calc(book: dict, waiting: list, now: dt.datetime, tag: str | None = None, halt: bool | None = None) -> dict:
    """「交易」标签里哪些行还会做事（2026-10-15 用户：「撤单后 / 没有执行下单等等的话交易处的数字不显示」）—— 标签上的数字、
    /api/status 的 pending、「今天要成交的单」/「手动指令」每一行怎么写都按这一个判断：
    数字 n = _trade_split 放在上面「今天要成交的单」（不含还挂在交易所、正在撤的「撤单中」）+「另有 …」里的行数（_split_n）——
    页面上看到的就是数到的，没有例外（复核 2，2026-10-16；以前单与指令在这里另数一遍，与分块有三处不一样）：
      没买到、不是系统原因的手动买入 / 加仓（_trade_split 按 live_unified.requeue_next：被拒 / 买不了 / 跳空 / 钱没来 / 在立花网站撤了）
        →「已结束」、不算（以前指令还是「已下单」、等明早对账才结束 → 照算）；
      状态不明（ERROR）的单：立花收盘前可能已被受理、还可能成交（与发送中 SENDING 一样）→ 在上面、算（以前不算）；收盘后「已收盘」→ 不算；
      固定口数「生效中 · 还没照它调」那一行（读了、还没照它排单）：执行器之后照它买卖 → 在上面 /「另有」、算（以前不算；
        还没读的同一条固定口数指令本来就算，读了之后数字不该什么都没成交就少 1）。
      执行器的单（当前决策）：已经结束的（成交 / 撤单 / 不下 / 被挡 / 失效 / 被拒…）、已经写了撤单的（撤单中）不算；
        还没发出的（PLANNED / DEFERRED）：HALT 生效中不发 → 不算（模拟账户的 DEFERRED 也一样：D3 起 09:25 前后的开盘撮合按立花 09:05 的
        闸门下，HALT 中不下；开盘撮合时被 HALT 挡下的「等开盘后」→ 不算，明早对账记为没买）；
        买单开盘时一定买不起一单元（凑钱的卖单撤了等）→ 不算；被挡但 08:55 之前还会再发的 → 算（D5）；
        每笔单的判断只在 live_ops.outlook（09:30 自检、执行器汇总、撤单推送、面板的提醒同一个；2026-10-15）；
        立花：成交日的交易所已经收盘（15:30 之后 / 成交日已过）→ 什么都不会再发生（明早对账），不算；模拟账户的单下一次运行按那天的开盘价撮合 → 照算。
      手动指令：撤回 / 撤单 / 撤销撤回本身不算，被撤回（还没读的撤回、撤回中）的不算，被撤单的单的指令、一定买不起的手动买入 / 加仓不算；
        单已经做完的（全部成交；立花收盘后已失效的买单 —— 没成交的部分不会再买）：指令还是「已下单」、明早对账才结束 → 不算
        （2026-10-15 复核：盘中手动卖出成交了，标签上一整天还是 1）；卖单没卖完的部分下一次开盘再卖 → 照算。
        HALT 中等着的照算（解除后照原样执行）。
    → {"orders": {cid: (标签, 说明) —— 不会做事的单怎么写}, "fix": {cid: 固定口数还有效的提醒}, "items": 不算的指令 id,
       "itxt": {指令 id: 状态后面加的说明（单在撤单中 / 预计下不成 / 已做完）},
       "rerun": {cid: 模拟账户开盘撮合的窗口过了的单哪次运行按成交日的开盘价撮合（outlook 的说明；行里代替 07:40 存下的说明）},
       "asked": 撤单中的 cid, "stuck": 写了撤单、面板自动下单暂停（今天没人撤，outlook cls stuck）的 cid, "paused": 面板自动下单今天暂停,
       "n": 数字, "busy": 一会儿就会变的（页面每 10 秒问一次要不要刷新）= 面板马上会叫执行器处理的手动指令
       （盘中的买卖 / 闲置资金比例 → --phase now；07:45〜08:55 的卖出 / 减仓 / 调仓 → --retry；盘中下的、还挂着的单可能随时成交）
       + 执行器正在跑（运行锁）+ 还在处理的撤单 / 撤回（单还挂着的撤单、执行器读了还在撤的、指着执行器读过的指令的撤回）；
       都还没读的「指令 + 它的撤回」不算（2026-10-15 复核：撤回了唯一一条之后页面还一直每 10 秒问、状态一变就刷新）；
       等下一次决策（07:40）才读的固定口数 / 解除 / 收盘后写的买卖不算（2026-10-15：以前晚上固定了口数，页面整晚每 10 秒问一次；
       「交易」的数字 n 照算）}。只读。"""
    from . import live_ops as LO
    st = book.get("state") or {}
    d = st.get("last_date")
    cur = [o for o in book.get("orders") or [] if o.get("decided_on") == d]
    man = book.get("manual") or {}
    items = man.get("items") or {}
    cu_now = LO.held_now(book, tag, now=now).get("core_units") or {}   # 含今天已成交：今天买进的 ETF 已经在「持仓」里（2026-10-16）
    halt = paths.halt_file().exists() if halt is None else halt
    paper = (tag or "").startswith("paper") or str(book.get("broker") or "").startswith("Paper")
    void = MO.voided(waiting)
    wl = [r for r in waiting if r.get("kind") != "uncancel" and r.get("id") not in void]
    asked = ({c for r in wl if r.get("kind") == "cancel_order" for c in LO.job_cids(r, cur)}          # 整组撤单：同一组的每一笔（2026-10-16）
             | {c for it in items.values() if it.get("kind") == "cancel_order" and it.get("status") == "pending"
                and not MO.grp_wait_stale(it, now) for c in LO.job_cids(it, cur)})   # 过了收盘还在等的整组撤单：不算撤单中（复核 2026-10-16）；
    #   还在等立花确认撤单的单（grp_wait）、「一起撤买单」会在本地一起撤的买单也算（LO.job_cids：与执行器发单前的保护同一个；复核 6）；
    #   同一组的其他几笔在「今天要成交的单」里写「同一组撤单中」（LO.cancel_conflict）
    paused = _trigger_paused(tag, waiting, now)              # 面板自动下单今天暂停（outlook 再按 panel_next 筛；单也看：开盘撮合 / 撤单；复核 7）
    ol = LO.outlook(book, waiting, now, tag=tag, halt=halt, asked=asked, instr=False, paused=paused)   # 每笔单今天会不会下：只在 live_ops.outlook 判断（D5）
    fixed = MO.core_fixed(book, tag)
    fpend, fwhen = LO.fix_pending_when(book, now, tag)       # 还没照它调的固定口数：今天开盘后 / 盘中就照它下（D1；复核 UI F2，2026-10-16）
    if fpend and paused and MO.morning_behind(book, now) and LO.panel_next(book, now, tag, cwin=True):
        fwhen = (f"面板自动下单今天暂停了、今天早上的运行不会自动补跑 → {LO.next_decision_text(now)} 的决策"   # 与 outlook 的 fix:<票>（cls paused）
                 "（修好之后也可以在 Mac 对话里说「再试一次」）")                                     # 同一个结论（复核 8，2026-10-16）
    rows, fix, dead = {}, {}, set()
    fin = {}                                                # 手动单已经做完了（全部成交 / 立花收盘后失效的买单）→ {cid: 指令后面加的说明}
    rerun, f = {}, LO.fill_day_of(book)                     # 模拟账户开盘撮合的窗口过了的单：哪次运行按成交日的开盘价撮合（outlook 的说明）
    for o in cur:
        cid, s, t = str(o.get("cid")), o.get("status"), str(o.get("ticker"))
        r = ol["orders"].get(cid) or {}
        if (paper and LO.paper_queued(o) and r.get("state") in ("will", "later") and r.get("reason")
                and r["reason"] != str(o.get("note") or "") and f is not None
                and (now.date() > f or (now.date() == f and now.time() >= LO.PAPER_OPEN_END) or r["state"] == "later")):
            rerun[cid] = r["reason"]                        # 复核 4（2026-10-16）：以前照写 07:40 存下的「已排队，次日开盘成交」/「开盘后按始値检查…」
        if (o.get("kind") == "core" and t in fixed and (s == "CANCELLED" or cid in asked or r.get("cls") == "fund"   # 撤了 / 下不成，固定口数却还在
                                                        or (s == "SKIPPED" and "凑钱的卖单" in str(o.get("note") or "")))   # 凑钱的卖单没了、执行器不下了（D2）
                and (t in fpend or not _fix_met(o, cur, st, fixed[t], asked))):   # 同一次决策别的单已经调到 / 还在调 → 不写（复核 7）
            fix[cid] = ((f"{NM.label(t)} 手动固定 {int(fixed[t]):,} 口还没照它调：{fwhen}照它下单（撤单不会取消固定口数）；不想要 → 在「持仓」"
                         if t in fpend else
                         f"{NM.label(t)} 手动固定 {int(fixed[t]):,} 口仍然有效：下一次决策（{LO.decision_text(book, now, tag, paused)}）"
                         "还会照它调（差多少补多少）；不想要 → 在「持仓」")
                        + ("" if int(cu_now.get(t) or 0) > 0 else "的「其他闲置资金 ETF（现在没拿）」")
                        + f"里 {NM.label(t)} 下面点「恢复按规则」")
        manual = o.get("reason") in LO.MANUAL_REASONS
        if manual and (s == "FILLED" or (o.get("side") == "BUY" and s in ("UNFILLED", "EXPIRED"))):
            fin[cid] = ("（已成交：明早对账后这条指令结束）" if s == "FILLED"
                        else "（单已失效：没成交的部分不会再买，明早对账后结束）")
        if r.get("chip") and r.get("cls") != "asked":       # 不会再做事的单：交易页写「不会下单（预计 / HALT）」「已收盘」…和原因
            rows[cid] = (r["chip"], r["reason"])
        if r.get("cls") in ("asked", "fund"):
            dead.add(cid)                                   # 撤单中 / 一定下不成：那条手动指令也不会再做事
        if r.get("cls") == "closed" and manual and o.get("side") == "BUY" and s in LO.AT_EXCH:
            fin[cid] = "（单已失效：没成交的部分不会再买，明早对账后结束）"   # 手动买入 / 加仓只做一次：失效了指令也不会再做事（卖单没卖完的下一次开盘再卖 → 照算）
    itxt, done_it, live_it = {}, {}, set()                  # 被撤单 / 一定买不起 / 已经做完的手动买卖：指令也不会再做事（「手动指令」那一行跟着写）
    for o in cur:
        if o.get("reason") not in LO.MANUAL_REASONS:
            continue
        cid = str(o.get("cid"))
        it = LO._manual_item(book, o)
        if not (it and it.get("id")):
            continue
        if cid in dead:
            itxt[it["id"]] = "（单在撤单中）" if cid in asked else "（预计下不成：那笔单在下面「已结束 / 不是今天的」）"
        elif cid in fin:
            done_it.setdefault(it["id"], fin[cid])
        elif o.get("status") in LO.LIVE:
            live_it.add(it["id"])                           # 同一条指令还有别的单在做 → 照算
    for k, v in done_it.items():
        if k not in live_it and k not in itxt:
            itxt[k] = v
    gone_it = set(itxt)
    dropped = MO.cancelled(wl)
    skip = set(gone_it)
    soon = 0                                                # 还会做事的手动指令里一会儿就会变的（busy）
    today = now.date().isoformat()
    behind = halt or MO.morning_behind(book, now)           # HALT / 今天早上的运行没完成：面板不叫 --phase now / --retry（等运行先处理）
    session = not behind and MO.timing(now)[0] == "now"
    morning = not behind and is_trading_day(now.date()) and TRIGGER_FROM <= now.time() < TRIGGER_UNTIL

    def quick(r: dict) -> bool:                             # 与 Trigger 的 now_due / due 同一口径（指令的种类与时段）
        if r.get("hold") == today or MO.allin_member(r):
            return False
        if r.get("status") == "placed":
            return session and bool(r.get("now"))           # 盘中下的单还挂着：随时可能成交
        k = r.get("kind")
        return (session and k in MO.ORDER_KINDS + ("core", "corefix")) or (morning and k in MO.POS_KINDS and not r.get("wait"))   # 固定口数盘中也马上（D1）
    for r in wl:
        if r.get("kind") in CANCEL_KINDS or r["id"] in dropped:
            skip.add(r["id"])
        else:
            soon += quick(r)
    for it in items.values():
        if it.get("status") not in MO.ACTIVE:
            continue
        if it.get("kind") in CANCEL_KINDS or it.get("cancel_req") or it.get("id") in gone_it or it.get("id") in dropped:
            skip.add(it.get("id"))                          # 还没读的撤回指着的、执行器读了在撤回中的：不会再做事
        else:
            soon += quick(it)
    if tag:                                                 # 执行器正在跑（07:40 的决策、面板叫的盘中运行…）：跑完状态就变
        from .live_unified import lock_held
        soon += lock_held(paths.state_dir() / f"live_unified_{tag}.lock")
    live_cids = {str(o.get("cid")) for o in cur if o.get("status") in LO.LIVE}
    flight = (len(asked & live_cids)                        # 撤单：单还挂着（执行器还没撤完）
              + sum(1 for it in items.values() if it.get("status") in MO.ACTIVE and it.get("cancel_req"))   # 撤回中（执行器读了、还在撤）
              + sum(1 for r in wl if r.get("kind") == "cancel" and (items.get(r.get("target")) or {}).get("status") in MO.ACTIVE
                    and not (items.get(r.get("target")) or {}).get("cancel_req")))   # 还没读的撤回、指着执行器已经读过的指令
    tl = {"orders": rows, "fix": fix, "items": skip, "itxt": itxt, "asked": asked, "rerun": rerun, "paused": paused,
          "stuck": {c for c, r in ol["orders"].items() if r.get("cls") == "stuck"}}
    sp = _trade_split(book, waiting, now, tag, halt, tl)    # 每一行放进哪一块（render 照用这一份）；数字按它数（复核 2，2026-10-16）
    return {**tl, "n": _split_n(sp), "busy": int(soon) + flight, "split": sp}


def _fix_met(o: dict, cur: list, st: dict, fixed, asked) -> bool:
    """撤了 / 下不成的那笔核心单之外，同一次决策同一只还有成交了（含部分）/ 还在做的单，或拿着的口数已经到了固定口数 → True
    （「仍然有效：下一次决策还会照它调」的提醒就不写了；复核 7，2026-10-16：以前 679 口的单撤了、650 口的单成交了，还写「还会再排同样的单」）。"""
    from . import live_ops as LO
    t, cid = o.get("ticker"), str(o.get("cid"))
    for x in cur:
        if x.get("kind") != "core" or x.get("ticker") != t or str(x.get("cid")) == cid:
            continue
        if int(x.get("filled_qty") or 0) > 0 or (x.get("status") in LO.LIVE and str(x.get("cid")) not in asked):
            return True
    try:
        return int((st.get("core_units") or {}).get(t) or 0) >= int(fixed)
    except (TypeError, ValueError):
        return False


def _split_n(sp: dict) -> int:
    """「交易」标签上的数字 = _trade_split 放在上面「今天要成交的单」的行（不含「撤单中」：还挂在交易所、执行器确认之前还可能成交，
    flight）+「另有 …」里的行（执行器的单、手动指令、没有指令行的「还没照它调」的固定口数）；「已结束 / 不是今天的」不算（复核 2，2026-10-16）。"""
    zs = ([z for c, z in sp["orders"].items() if c not in sp["flight"]]
          + [z for i, z in sp["items"].items() if i not in sp.get("iflight", ())]   # 撤单指令本身不算（那笔单算；复核 8）
          + [z for z, _x in sp["extra"]])
    return sum(1 for z in zs if z in ("today", "later"))


WD_ZH = "一二三四五六日"


def _md_wd(d: dt.date) -> str:
    """「10/19（周一）」（「另有 N 条等 10/19（周一）开盘」：周五 / 连休前写的那天是下周一 / 连休之后，不写「明天」）。"""
    return f"{d:%m/%d}（周{WD_ZH[d.weekday()]}）"


def _trade_split(book: dict, waiting: list, now: dt.datetime, tag: str | None = None, halt: bool | None = None,
                 tlive: dict | None = None) -> dict:
    """「交易」只显示今天要成交的（2026-10-16 用户：「交易里面只显示当天要成交的单」）：执行器的单（当前决策）与手动指令各放进一块 ——
      today（上面「今天要成交的单」）/ later（同一张卡片里「另有 N 条等 10/19（周一）开盘」，点开看、按钮照旧）/
      ended（最下面收起的「已结束 / 不是今天的（N 条）」）。
    不另做判断：每笔单 / 每条等着的指令按 live_ops.outlook（标签上的数字、09:30 自检、★ 交易 推送同一个；asked / halt 与 _trade_live 相同）：
      state will → today；later → act_at 是今天（盘中没下成、今天开盘寄付）→ today，否则 later（没有 act_at：HALT 解除后 / 下一次决策）；
      done / wont（成交、撤了、不下、被挡不再试、今天不会下、HALT 挡下的还没发出的单、立花已收盘）→ ended。
      outlook 说「会」却没有时刻的指令（等上一笔成交 wait=prev / 等凑钱的卖单 / 早上的运行没完成）：收盘后 / 休市日 → later；
        等上一笔成交的要等那笔第二天早上对账 → 下一次决策的单今天开盘（今天早上的运行还没跑完）才 today，否则 later
        「等下一次决策（MM/DD 07:40）」（复核 2026-10-16：以前一律放上面，16:00 / 周六也写在「今天要成交的单」里）。
      撤单中（asked）：还挂在交易所（SENT / PARTIAL，outlook 不算撤单时是 will = 立花还没收盘）→ today（「撤单中」：执行器确认之前还可能成交，flight）；
        还没发出就写了撤单的 → ended。面板自动下单今天暂停（撤单只有面板叫）→ outlook 给 cls stuck（「挂着（撤单暂停中）」）→ today、照算
        （复核 7，2026-10-16：以前照写「撤单中」、不算，单却没人去撤）。
      执行器读了的指令：_trade_live 不算的（tlive["items"]：撤回中、单在撤单中 / 预计下不成 / 已做完）、撤回 / 撤单本身 → ended；
        已下单（placed）的看它的单（live_ops._manual_item）：有 today → today、有 later → later；单都结束了 →
          手动买入 / 加仓（只做一次）：下一次早上的对账会不会把它留到那次决策（live_unified.requeue_next：与 _reconcile / _system_miss
            同一个函数）—— 不会（被拒、这只买不了、跳空不下、钱没来…）→ ended，状态后面写「没买到：只做一次…对账后结束」（itxt）；
            会（系统原因：开盘后补单没跑、整个运行被挡…）→ 下一次决策（HALT 中 = HALT 解除后）；
          卖出 / 减仓 / 调仓往下（没卖完 / 没发出的下一次决策再下）→ 下一次决策的单哪天开盘（HALT 中 = HALT 解除后）；
          「下一次决策的单哪天开盘」= 今天早上的运行还没跑完（模拟账户 / 立花 08:55 之前）→ 今天，否则下一个交易日
          （与 live_ops._instr_row 的「早上的运行没完成」同一个口径；复核 2026-10-16：以前按 MO.timing 一律「下一次开盘」，
          08:57 被挡的卖出写成今天、被拒的买入写「等 10/16 开盘」）。
        完成了、还没照它调的固定口数（MO.FIX_WAIT）→ 跟 outlook 的 fix:<票> 那一行（没有那一行 → _fix_zone：今天说了「下一次决策再调」→ later，
          别的照 outlook 那一行的时刻自己算；复核 4）；
        别的（完成 / 已撤回 / 没执行…）→ ended。
      outlook 的 fix:<票>（读了、还没照它调的固定口数）没有对应的指令行（恢复按规则 / 更早的）→ extra（只写一行，没有按钮）。
      闲置资金比例（复核 3，2026-10-16）：读了、还没照它调（outlook 的 core:，MO.core_wait）→ 最新生效的那条比例指令跟那一行（today / later：
        HALT 中 = 等 HALT 解除后、今天说了下一次决策再调 / 收盘后 = 下一次决策那天开盘、盘中 / 一会儿再试 = 今天）；没有那条指令的行 → extra；
        以前指令「完成」→ 已结束，数字少 1，HALT 解除后却马上照它卖（与固定口数「还没读 / 读了」数字一样同一个道理）。→ out["core"] = 那一块。
      已下单的指令、它的单是立花收盘后状态不明的（outlook cls unknown + closed）→ later「等登记状态不明的单」、状态后面写 MO.UNK_LATER
        （登记之前执行器每次运行都停下，不是「等 MM/DD 开盘」；复核 3）；买入 / 加仓写 MO.UNK_LATER_BUY（登记 0 股 → 指令结束，只做一次）。
        有这样的单时，别的还没结束的指令（还没读的、等着的、已下单的）与还没照它调的固定口数 / 比例也都 later「等登记状态不明的单」
        （执行器每次运行开头都停下：_raise_if_unknown；复核 4，2026-10-16：以前只有靠那笔单的指令这样写，别的照写「等 MM/DD 开盘」）。
        单本身留在上面（要你核对登记）。
      立花收盘前有状态不明的单（当前决策的 SENDING / ERROR：执行器每次运行开头都停下、面板也不叫它）→ 上面别的还没结束的指令
        照旧在上面、照算，状态后面写「等登记状态不明的单（〔代码 名字〕）之后才下」，不是「马上（盘中）」（复核 5，2026-10-16）。
      面板自动叫执行器今天暂停了（_trigger_paused：与 Trigger._still_paused / 09:30 自检同一份记录；outlook 的 paused）→
        later「等下一次决策（…；面板自动下单今天暂停了）」、状态后面写可以说「再试一次」（复核 5：以前照写「马上（盘中）」在上面）。
        盘中、午休、今天早上的决策之后的开盘前都这样（下一个来下它的是面板：live_ops.panel_next；立花今天还有定时运行要来、跑成了面板就恢复
        〔09:05 之前；09:20 之前而且还有开盘后的买单 / 错过寄付的卖单〕→ 照旧今天；等开盘后马上下的买入 wait=True 也算；
        复核 2026-10-16：以前只在盘中，11:30〜12:30 / 08:30 同一条指令跳回上面写「12:30 后场开盘」）。
      模拟账户今天早上的运行没完成、过了 11:30（LO.paper_late_catchup）：补跑那次决策排的单（比例 / 固定口数调的核心 ETF、
        没卖完的手动卖出）今天不再撮合 → later「等 MM/DD（周X）07:40 的运行」（补跑之后那些单同一个结论；还没读的手动买卖照旧今天：
        补跑过了 08:55 不排进那次决策、盘中马上下；复核 5）。
      读了、还没照它调的固定口数，又写了同一只还没读的固定口数 / 恢复按规则 → 读了的那条 ended「已被新写的那条取代」（MO.fix_status_text
        给了 tag 时 None；outlook 那一行就是新的那条），只算新的；读之前读之后数字一样（复核 5：以前口数相同时两条都算）。
    标签上的数字（_trade_live 的 n）就按这里数：today（不含 flight）+ later 的行数（_split_n），没有例外（复核 2，2026-10-16：
    以前 _trade_live 另数一遍 —— 状态不明（ERROR）的单、固定口数还没照它调的那一行在上面却不算，没买到的手动买入 / 加仓在 ended 却照算）。
    固定口数仍然有效的提醒（tlive["fix"]）：那笔单去了 ended → 收进 notes（上面的卡片写一次，不会被收起来）。
    → {"orders": {cid: 块}, "items": {指令 id: 块}, "flight": {cid}, "when": {ref: (排序, 排序, 「等 10/19（周一）开盘」)},
       "extra": [(块, outlook 的行)], "notes": [提醒], "itxt": {指令 id: 状态后面加的说明}, "core": 还没照它调的比例在哪一块（None = 没有）}。
    只读；算不成（账本里读不了的数）→ 还没结束的都放 today。"""
    from . import live_ops as LO
    from .calendar_jp import next_trading_day
    from .live_unified import requeue_next
    book = book or {}
    halt = paths.halt_file().exists() if halt is None else bool(halt)
    tl = tlive if tlive is not None else _trade_live(book, waiting, now, tag, halt)
    st = book.get("state") or {}
    cur = [o for o in book.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == st.get("last_date")]
    byc = {str(o.get("cid")): o for o in cur}
    paper = (tag or "").startswith("paper") or str(book.get("broker") or "").startswith("Paper")
    today = now.date()
    f = LO.fill_day_of(book)
    mode = MO.timing(now)[0]
    out = {"orders": {}, "items": {}, "flight": set(), "iflight": set(), "when": {}, "extra": [], "notes": [], "itxt": {}, "core": None,
           "nocatch": False}
    paused = tl["paused"] if "paused" in tl else _trigger_paused(tag, waiting, now)   # outlook 再按时段筛（panel_next）
    pz = paused and LO.panel_next(book, now, tag)          # 暂停、下一个来的是面板（模拟账户早上没跑完 = 补跑也不来；复核 7）
    pzc = paused and LO.panel_next(book, now, tag, cwin=True)   # 补跑 / 撤单：面板叫到 15:30（复核 8，2026-10-16）
    out["nocatch"] = bool(pzc and paper and MO.morning_behind(book, now))   # 「今天的单还没排出来」不写「跑完之后」（_trade_sections）
    try:                                                    # 与 _trade_live_calc 同一个判断（同样的 asked / halt）；指令也要（instr）
        ol = LO.outlook(book, waiting, now, tag=tag, halt=halt, asked=tl["asked"], paused=paused)
    except Exception as e:                                 # noqa: BLE001  只是分块：不能让页面打不开
        log.warning("「交易」的分块没算成（%s：%s）：还没结束的都放在上面", type(e).__name__, e)
        ol = None

    def when(at, cls: str = "") -> tuple:                  # 「另有 …」怎么说（HALT / 下一次决策 / 哪天开盘）
        if cls == "halt":
            return (2, "", "等 HALT 解除后")
        if isinstance(at, dt.datetime):
            tail = f"{at:%H:%M} 的运行" if at.time() < MO.SESSION[0][0] else "开盘"   # 模拟账户的开盘撮合没下成 → 那天 07:40 的运行
            return (0, at.isoformat(), f"等 {_md_wd(at.date())}{tail}")
        return (1, "", f"等下一次决策（{LO.next_decision_text(now)}）")

    def nd_open() -> dt.date:                              # 下一次决策的单哪天开盘：今天早上的运行还没跑完（立花 08:55 之后不自动补跑；
        if mode != "next" and f != today and not pz and (paper or now.time() < MO.CUTOFF):   # 模拟账户面板暂停 = 不补跑）→ 今天
            return today
        return next_trading_day(today)

    def soon(rec: dict | None) -> bool:                    # outlook 说「会」却没有时刻的指令：今天还会做事吗
        if mode == "next":
            return False                                   # 收盘后 / 休市日：最早下一次决策
        w = (rec or {}).get("wait")
        if not w:
            return True                                    # 早上的运行没完成：补跑之后今天下
        return nd_open() == today or (w != "prev" and f == today)   # 等上一笔成交：那笔要等下一次早上的对账

    def zone(x: dict | None, ref: str, rec: dict | None = None) -> str:
        if x is None:                                       # outlook 没给（读不了的一条）：不下结论，留在上面
            return "today"
        s, at = x.get("state"), x.get("act_at")
        if x.get("cls") == "paused":                       # 面板自动下单今天暂停了（盘中 / 午休 / 决策之后的开盘前：live_ops.panel_next）→ 下一次决策 / 你说「再试一次」
            nd = LO.next_decision_text(now)                 # （还会做 → 在「另有」、算；复核 2026-10-16：以前照写「马上（盘中）」在上面）
            out["when"][ref] = (1, "", f"等下一次决策（{nd}；面板自动下单今天暂停了）")
            out["itxt"].setdefault(ref, f"（面板自动下单今天暂停了：等下一次决策（{nd}）；修好之后也可以在 Mac 对话里说「再试一次」）")
            return "later"
        if x.get("cls") == "catchup" and isinstance(at, dt.datetime):   # 模拟账户过了 11:30 补跑：那次决策排的单今天不再撮合
            out["itxt"].setdefault(ref, f"（{LO.paper_late_text(at, now)}）")
        if s == "will" and at is None and x.get("kind") == "instr" and not soon(rec):
            out["when"][ref] = when(None)
            return "later"
        if s == "will" or (s == "later" and isinstance(at, dt.datetime) and at.date() <= today):
            return "today"
        if s == "later":
            out["when"][ref] = when(at, x.get("cls") or "")
            return "later"
        return "ended"
    for o in cur:
        cid = str(o.get("cid"))
        r = (ol["orders"].get(cid) if ol else None)
        if r is None:                                       # 算不成：还没结束的（撤单中但还挂在交易所的也算）留在上面
            s = o.get("status")
            z = "today" if s in LO.LIVE + ("BLOCKED", "ERROR") and (cid not in tl["asked"] or s in LO.CANCELLABLE) else "ended"
            if z == "today" and cid in tl["asked"]:
                out["flight"].add(cid)
        elif r.get("cls") == "asked":                       # 撤单中：还挂在交易所、交易所还开着（不算撤单时 outlook 的判断）→ 还可能成交
            z = "today" if o.get("status") in LO.CANCELLABLE and LO._order_row(
                o, now=now, paper=paper, tag=tag, halt=halt, asked=(), casc={}, unf={}, f=f)["state"] == "will" else "ended"
            if z == "today":
                out["flight"].add(cid)
        else:
            z = zone(r, cid)
        out["orders"][cid] = z
        if z == "ended" and cid in tl["fix"] and tl["fix"][cid] not in out["notes"]:
            out["notes"].append(tl["fix"][cid])            # 「手动固定 … 仍然有效：下一次决策还会再排」不跟着那笔单收起来
    oit = ol["items"] if ol else {}
    void, gone = MO.voided(waiting), MO.cancelled(waiting)

    def cz(r: dict) -> str:                                # 撤单指令：它要撤的单还在上面（撤单中 / 挂着（撤单暂停中））→ 跟着放上面、不算数字
        cs = MO.cancel_cids(r) + [str(x) for x in r.get("grp_all") or []]   # （复核 8，2026-10-16：以前「等执行器读」的撤单收进「已结束」）
        if any(out["orders"].get(c) == "today" for c in cs):
            out["iflight"].add(r.get("id"))
            return "today"
        return "ended"
    for r in waiting:
        rid = r.get("id")
        if r.get("kind") == "uncancel" or rid in void:
            continue
        out["items"][rid] = (cz(r) if r.get("kind") == "cancel_order" and rid not in gone else
                             "ended" if r.get("kind") in CANCEL_KINDS or rid in gone else zone(oit.get(rid), rid, r))
    items = [it for it in (((book.get("manual") or {}).get("items")) or {}).values() if isinstance(it, dict)]
    link: dict = {}                                         # 已下单的指令 → 它的单
    for o in cur:
        if o.get("reason") in LO.MANUAL_REASONS:
            it = LO._manual_item(book, o)
            if it and it.get("id"):
                link.setdefault(it["id"], []).append(str(o.get("cid")))
    fixrows = {str(k)[4:]: x for k, x in oit.items() if str(k).startswith("fix:")}
    has_fix = set()                                         # 有自己的指令行的固定口数（不再另写 extra）
    corerow = oit.get("core:")                              # 读了、还没照它调的闲置资金比例（复核 3）：跟它的那条指令（iid）
    newfix = {r.get("ticker") for r in waiting if r.get("kind") == "corefix" and r.get("id") not in gone
              and not r.get("fund_for")}                    # 还没读的固定口数 / 恢复按规则（与 MO.core_fixed 同一个过滤）：读到就取代同一只读了的那条
    unk = {c for c, r in ((ol or {}).get("orders") or {}).items() if r.get("cls") == "unknown" and r.get("closed")}   # 立花收盘后状态不明的单
    for it in items:
        iid, k, s = it.get("id"), it.get("kind"), it.get("status")
        if not iid or k == "uncancel" or s == "voided":
            continue
        if s in MO.ACTIVE:
            if k == "cancel_order" and s == "pending" and iid not in gone:
                z = cz(it)
            elif k in CANCEL_KINDS or it.get("cancel_req") or iid in gone or iid in tl["items"]:
                z = "ended"
            elif s == "pending":
                z = zone(oit.get(iid), iid, it) if ol else "today"
                if k == "corefix":
                    has_fix.add(it.get("ticker"))
            else:                                           # 已下单：看它的单
                zs = [out["orders"].get(c) for c in link.get(iid, [])]
                os_ = [byc[c] for c in link.get(iid, []) if c in byc]
                buy = k == "buy" or any(o.get("reason") in ("manual_buy", "manual_add") for o in os_)
                if any(c in unk for c in link.get(iid, [])):   # 单状态不明、交易所已收盘：登记之前执行器每次运行都停下（复核 3）
                    z = "later"                             # 买入只做一次：登记 0 股 → 指令结束，不是「下一次决策处理」（复核 4）
                    out["when"][iid] = UNK_WHEN
                    out["itxt"][iid] = f"（{MO.UNK_LATER_BUY if buy else MO.UNK_LATER}）"
                elif "today" in zs:
                    z = "today"
                elif "later" in zs:
                    z = "later"
                    out["when"][iid] = next(out["when"][c] for c in link[iid] if out["orders"].get(c) == "later")
                elif buy and os_ and (it.get("fund") == "all" or not any(requeue_next(o, cur, now, f, tl["asked"]) for o in os_)):
                    z = "ended"                             # 只做一次：没买到、不是系统原因 → 下一次早上的对账之后结束（不再买）
                    if (it.get("unsent") or {}).get("retry", True):   # 「没发出（只做一次）」已经写了的不重复
                        got = any(int(o.get("filled_qty") or 0) > 0 for o in os_)   # 撤单之前成交了一部分：记成交的部分
                        out["itxt"][iid] = (("（单已结束：没成交的部分不会再买" if got else "（没买到：只做一次，不再买")
                                            + f"；{LO.next_decision_text(now)} 的对账之后结束）")
                elif halt:
                    z = "later"
                    out["when"][iid] = when(None, "halt")
                else:                                       # 系统原因没下的买入 / 加仓、没卖完 / 没发出的卖出：下一次决策再下
                    day = nd_open()
                    late = None if buy else LO.paper_late_catchup(book, now, paper, halt, pzc)
                    if late is not None:                    # 卖出：补跑那次决策排的卖单过了 11:30 今天不再撮合（买入补跑之后盘中马上下 = 今天；复核 2026-10-16）
                        z = "later"
                        out["when"][iid] = when(late)
                        out["itxt"][iid] = f"（{LO.paper_late_text(late, now)}）"
                    else:
                        z = "today" if day == today else "later"
                    if z == "later" and late is None:
                        out["when"][iid] = when(None) if buy else when(LO._at(day, MO.SESSION[0][0]))
        elif k == "core" and s == "done" and corerow is not None and corerow.get("iid") == iid:
            z = zone(corerow, iid)                          # 还没照它调的比例：照 outlook 的 core: 那一行（与固定口数的 FIX_WAIT 同一个处理）
            out["core"] = z
        elif k == "corefix" and MO.fix_status_text(it, items, book, tag) == MO.FIX_WAIT:
            t = it.get("ticker")
            has_fix.add(t)
            if t in fixrows:
                z = zone(fixrows[t], iid)
            else:                                           # outlook 没给那一行（今天说了下一次决策再调 / outlook 算不成）：自己看时刻
                z = _fix_zone(it, book, now, tag, halt, zone, when, out["when"], paused=pz, pc=pzc)
        else:
            z = "ended"
            if (k == "corefix" and s == "done" and it.get("ticker") in newfix
                    and MO.fix_status_text(it, items, book) == MO.FIX_WAIT):   # 不看还没读的：读之前它就是「还没照它调」的那一条
                out["itxt"][iid] = "（已被新写的那条取代：执行器读到之后照新的调）"   # 复核 2026-10-16：以前两行都算，读了之后数字少 1
        out["items"][iid] = z
    for t, x in fixrows.items():
        if t not in has_fix:
            out["extra"].append((zone(x, x["ref"]), x))
    if corerow is not None and out["core"] is None:         # 没有那条比例指令的行（整理账本时删掉了 / 旧账本）→ 补一行
        out["core"] = zone(corerow, corerow["ref"])
        out["extra"].append((out["core"], corerow))
    if unk:                                                 # 立花收盘后有状态不明的单：登记之前执行器每次运行（07:40 的决策、开盘后、盘中）
        recs = {r.get("id"): r for r in waiting}            # 都停下（_raise_if_unknown）→ 还没结束的指令、还没照它调的固定口数 / 比例
        recs.update({it.get("id"): it for it in items})     # 都等登记，不是「等 MM/DD 开盘」（复核 4，2026-10-16：以前只有靠那笔单的指令这样写）；
        for iid, z in out["items"].items():                 # 数字不变（上面 / 另有 都算）
            if z not in ("today", "later"):
                continue
            out["items"][iid] = "later"
            out["when"][iid] = UNK_WHEN
            if MO.UNK_LATER not in str((recs.get(iid) or {}).get("msg") or ""):   # 状态已经写「等登记状态不明的单」的不重复
                out["itxt"].setdefault(iid, f"（{MO.UNK_LATER}）")
        out["extra"] = [("later" if z in ("today", "later") else z, x) for z, x in out["extra"]]
        for z, x in out["extra"]:
            if z == "later":
                out["when"][x["ref"]] = UNK_WHEN
        if out["core"] in ("today", "later"):
            out["core"] = "later"
    uo = [o for o in cur if o.get("status") in ("SENDING", "ERROR")]
    if uo and not unk:                                      # 收盘前有状态不明的单（_unknown_open）：登记之前执行器每次运行开头都停下（_raise_if_unknown），
        lab = "、".join(dict.fromkeys(f"{'买' if o.get('side') == 'BUY' else '卖'} {NM.label(o.get('ticker'))}" for o in uo))
        txt = f"等登记状态不明的单（{lab}）之后才下"         # 面板也不叫（Trigger._due）→ 今天的那几条不写「马上（盘中）」；登记了今天还能下 → 位置不变、照算
        recs = {r.get("id"): r for r in waiting}            # （复核 2026-10-16；收盘后的见上面：都等登记）
        recs.update({it.get("id"): it for it in items})
        for iid, z in out["items"].items():
            if z == "today" and (recs.get(iid) or {}).get("status") != "placed":
                out["itxt"][iid] = f"（{txt}）"
        out["extra"] = [(z, {**x, "reason": f"{txt}；{x.get('reason') or ''}".rstrip("；")} if z == "today" else x)
                        for z, x in out["extra"]]
    return out


def _trigger_paused(tag: str | None, waiting: list, now: dt.datetime) -> bool:
    """面板自动叫执行器今天暂停了吗（run_status.trigger_paused：Trigger 记的；09:30 自检同一个）—— 暂停之后又写了新的指令（叫那次
    执行器时还没有的指令 id）→ 面板下一轮就恢复（Trigger._still_paused）→ 不算暂停。交易日（盘中 / 午休 / 开盘前）用；
    outlook 只在面板是下一个会来下的时段看它（live_ops.panel_next）。"""
    if not tag:
        return False
    try:
        from . import run_status as RS
        pz = RS.trigger_paused(tag, now.date().isoformat())
        if not pz:
            return False
        new = {r.get("id") for r in waiting if isinstance(r, dict)} - {str(x) for x in pz.get("ids") or ()}
        return not new
    except Exception:                                      # noqa: BLE001  只是分块：读不了 → 当没暂停
        return False


UNK_WHEN = (3, "", "等登记状态不明的单")                    # 「另有 … 等登记状态不明的单」（_trade_split 的 when）


def _fix_zone(it: dict, book: dict, now: dt.datetime, tag: str | None, halt: bool, zone, when, wmap: dict, paused: bool = False,
              pc: bool | None = None) -> str:
    """还没照它调的固定口数（FIX_WAIT）、outlook 没给 fix:<票> 那一行时放哪一块（复核 4，2026-10-16：以前一律当成「今天说了下一次决策再调」
    → later「等下一次决策」，撤回了另一条还没读的固定口数时，今天开盘后 / 盘中就下的也这样写）：
      今天说了「下一次决策再调」（core_rule.fix_defer：corefix_pending(now) 不含这只）→ later「等下一次决策」；
      别的 → 与 outlook 的 fix:<票> 同一个时刻（live_ops._instr_row 的 corefix：corefix_fill —— 盘中 / 开盘前 / 午休 = 今天，
        早上的运行没完成：模拟账户补跑 = 今天、立花 08:55 之后 = 下一个交易日，HALT = 解除后）。
    paused：面板自动下单今天暂停、下一个来下它的是面板（已经按 live_ops.panel_next 筛过；与 outlook 的 fix:<票> 同一个结论）。"""
    from . import live_ops as LO
    t = it.get("ticker")
    try:
        defer = t not in MO.corefix_pending(book, tag, now)
    except Exception:                                      # noqa: BLE001  算不成：照旧
        defer = True
    x = None
    if not defer:
        try:
            x = LO._instr_row({**it, "status": "pending", "msg": ""}, book, now, tag, halt, paused, True, pc=pc)
        except Exception:                                  # noqa: BLE001
            x = None
    if x is None:
        wmap[it.get("id")] = when(None)
        return "later"
    return zone(x, it.get("id"))


def _where_zone(z) -> str:
    return ("「交易」→「今天要成交的单」的「手动指令」" if z == "today" else "「交易」→ 点开「另有 …」的「手动指令」" if z == "later"
            else "「交易」→ 点开「已结束 / 不是今天的」的「手动指令」" if z == "ended" else "「交易」的「手动指令」")


def _where_item(sp: dict, iid) -> str:
    """一条手动指令现在在「交易」的哪一块（别处的「要撤回在 …」用；复核 2026-10-16：「手动指令」卡片拆进了三块，
    以前写「「交易」→「手动指令」」，指令在收起的「另有 …」里时页面上找不到）。"""
    return _where_zone(((sp or {}).get("items") or {}).get(iid))


def _where_core(sp: dict) -> str:
    """还没照它调的闲置资金比例那一行在「交易」的哪一块（持仓 ETF 下面「还没照它调完，见 …」；复核 3，2026-10-16）。"""
    return _where_zone((sp or {}).get("core"))


def _fix_wait_row(x: dict) -> str:
    """outlook 的 fix:<票> / core:（读了、还没照它调的固定口数 / 闲置资金比例；没有对应的指令行）→ 一行（没有按钮：要改在「持仓」的 ETF 下面）。"""
    why = str(x.get("reason") or "")
    return (f"<div class='li'><div class='grow'><b>{escape(str(x.get('what') or x.get('ref')))}</b> <span class='chip'>{escape(MO.FIX_WAIT)}</span>"
            + (f"<div class='muted small'>{escape(NM.annotate(why))}</div>" if why else "") + "</div></div>")


def _later_line(ws: list) -> str:
    """「另有 N 条等 10/19（周一）开盘」；几种 →「另有 3 条之后才下：2 条等 10/19（周一）开盘、1 条等 HALT 解除后」（日子在前）。"""
    g: dict = {}
    for w in sorted(ws):
        g[w[-1]] = g.get(w[-1], 0) + 1
    if len(g) == 1:
        (txt, n), = g.items()
        return f"另有 {n} 条{txt}"
    return f"另有 {sum(g.values())} 条之后才下：" + "、".join(f"{n} 条{t}" for t, n in g.items())


def _trade_sections(sp: dict, orows: list, irows: list, meta: dict, now: dt.datetime, paper: bool, halt: bool,
                    blocks: str = "", nblk: int = 0, old_n: int = 0) -> list[str]:
    """「交易」的两张卡片（Mac 与手机同一个；2026-10-16 用户：「交易里面只显示当天要成交的单」）：
      「今天要成交的单」（id today）：执行器的单 + 今天做事的手动指令（按 _trade_split）；什么都没有 →「今天没有要成交的单了」/
        休市日「今天休市，没有要成交的单」/ 交易日今天早上的运行还没跑完（成交日不是今天）→「今天的单还没排出来：今天早上 07:40 的运行
        还没跑（跑完之后这里才有今天的单）」（立花 08:55 之后不自动补跑 →「…没跑成：补跑了这里才有今天的单」；模拟账户过了 11:30 →
        补跑之后排的单今天不再撮合、等下一个交易日 07:40 的运行（LO.paper_late_catchup）；模拟账户面板自动下单今天暂停（sp nocatch）→
        不会自动补跑、等下一个交易日 07:40 的运行（复核 7）；收盘后照旧「…了」；
        复核 2026-10-16：以前 07:40 之前也写「今天没有要成交的单了」，今天的单其实还没排）；HALT → 一行提醒；
        今天早上的运行还没跑 → 说执行器的单是上一次决策的；固定口数仍然有效的提醒（那笔单收起来了也写）；
        之后才做的收进「另有 N 条等 …」（点开 = 那几行与按钮；与上面一样分「执行器的单」/「手动指令」两小块，别处写的「见「手动指令」」照样找得到）。
      「已结束 / 不是今天的（N 条）」（id orders，默认收起）：结束了的单、最近 MANUAL_SHOW_DAYS 天的指令记录、卖出后不买回（id blocks）。
    orows / irows：[(cid / 指令 id, 一行)]（_order_rows / render 拼好的，按钮照旧）；blocks / nblk：卖出后不买回（_blocks_card）。"""
    from . import live_ops as LO
    from .calendar_jp import next_trading_day
    Z = {z: {"o": [], "i": [], "w": []} for z in ("today", "later", "ended")}
    for cid, h in orows:
        z = sp["orders"].get(cid, "today")
        Z[z]["o"].append(h)
        Z[z]["w"].append(sp["when"].get(cid))
    for iid, h in irows:
        z = sp["items"].get(iid, "today")
        Z[z]["i"].append(h)
        Z[z]["w"].append(sp["when"].get(iid))
    for z, x in sp["extra"]:
        Z[z]["i"].append(_fix_wait_row(x))
        Z[z]["w"].append(sp["when"].get(x["ref"]))
    f, stale = meta.get("f"), meta.get("stale")
    trading = is_trading_day(now.date())
    fd = f"（成交日 {f:%m/%d}）" if f else ""
    T, L, E = Z["today"], Z["later"], Z["ended"]
    empty = not T["o"] and not T["i"]
    after = MO.timing(now)[0] == "next"                     # 收盘后（15:25 起）/ 休市日
    late = not paper and now.time() >= MO.CUTOFF            # 立花 08:55 之后：早上的运行不自动补跑
    run = ("今天早上 07:40 的运行还没跑" if now.time() < MO.RUN_AT else "今天早上的运行没跑成" if after
           else "今天早上的运行没跑成（立花 08:55 之后不自动补跑）" if late else "今天早上的运行还没跑完")
    pending = trading and stale and not after               # 今天的单还没排出来（成交日不是今天、今天还没收盘）
    plate = paper and pending and not halt and now.time() >= LO.PAPER_OPEN_END   # 模拟账户过了 11:30：补跑排的单今天不再撮合（复核 2026-10-16）
    H = ["<section class='card' id='today'><h2>今天要成交的单</h2>"]
    if halt:
        H.append("<div class='neg small'>★ HALT 生效中：执行器今天不发新单（已经在交易所的单照样可能成交，可以撤；说明在「更多」）</div>")
    if stale and orows and (trading or T["o"] or L["o"]):   # 下面的空行已经写了为什么 → 这里只说是上一次决策的单（休市日都收在「已结束」→ 不写；复核 8）
        H.append(f"<div class='muted small'>执行器的单是上一次决策的单{escape(fd)}，不是今天的"
                 + ("" if empty and (pending or not trading) else "：" + ("今天休市" if not trading else run)) + "</div>")
    if T["o"]:
        H.append(f"<div class='tsub'>执行器的单{escape(fd)}</div><div class='list'>{''.join(T['o'])}</div>")
    if T["i"]:
        H.append(f"<div class='tsub'>手动指令</div><div class='list'>{''.join(T['i'])}</div>")
    if empty:
        H.append("<div class='tempty'>" + escape(
            "今天休市，没有要成交的单" if not trading else
            (f"今天的单还没排出来：{run}；HALT 生效中，执行器不会排出要成交的单（解除之后的运行才会）" if halt else
             f"{run}：补跑了这里才有今天的单" if late else
             f"今天的单还没排出来：{run}，面板自动下单今天暂停了、不会自动补跑（等 {_md_wd(next_trading_day(now.date()))}"
             f"{LO.PAPER_RUN_T:%H:%M} 的运行；修好之后也可以在 Mac 对话里说「再试一次」）" if sp.get("nocatch") else
             f"今天的单还没排出来：{run}（过了 {LO.PAPER_OPEN_END:%H:%M}：补跑之后排的单今天不再撮合，"
             f"等 {_md_wd(next_trading_day(now.date()))}{LO.PAPER_RUN_T:%H:%M} 的运行按今天的开盘价记）" if plate
             else f"今天的单还没排出来：{run}（跑完之后这里才有今天的单）") if pending
            else "今天没有要成交的单了") + "</div>")
    H.extend(f"<div class='small'>{escape(n)}</div>" for n in sp["notes"])
    if L["o"] or L["i"]:
        ws = [w or (1, "", f"等下一次决策（{LO.next_decision_text(now)}）") for w in L["w"]]
        H.append(f"<details class='later'><summary>{escape(_later_line(ws))}</summary>"
                 + (f"<div class='tsub'>执行器的单{escape(fd)}</div><div class='list'>{''.join(L['o'])}</div>" if L["o"] else "")
                 + (f"<div class='tsub'>手动指令</div><div class='list'>{''.join(L['i'])}</div>" if L["i"] else "")
                 + "</details>")
    if T["o"] or L["o"]:
        H.append("<div class='muted small'>" + escape(
            f"「撤单」：{LO.CANCEL_HINT}。{LO.CANCEL_HINT_CORE}。执行器还没发出的单（计划 / 等开盘后）也能撤：撤了执行器就不再发。"
            + ("同一组（一起下的：固定口数的凑钱卖单和买单、手动买入和为它卖的、拆成两笔的单）可以「整组撤单」：先撤买单，确认没成交再撤卖单；"
               "买单已经成交 / 撤不掉 → 卖单不撤。" if meta.get("grp") else "")) + "</div>")
    if orows and not paper and not stale:
        H.append("<div class='muted small'>立花 API / Mac 出故障那天：只照「被挡 / 不下 / 没下」的行（今天不会再发的收在下面「已结束 / 不是今天的」里）在立花网站下单"
                 "（「已下单 / 已成交 / 部分成交」的已经在交易所，别再下），之后在 Mac 对话里说一声登记（人工代下）。</div>")
    H.append("</section>")
    ne = len(E["o"]) + len(E["i"]) + nblk
    if not ne:
        return ["".join(H)]
    D = [f"<section class='card' id='orders'><details class='ended'><summary>已结束 / 不是今天的（{ne} 条"
         + (f"；含手动卖出后不自动买回 {nblk} 条" if nblk else "") + "）</summary>"]   # 「解除」在这里面（复核 7）
    if E["o"]:
        D.append(f"<div class='tsub'>执行器的单{escape(fd)}</div><div class='list'>{''.join(E['o'])}</div>")
    if E["i"]:
        D.append(f"<div class='tsub'>手动指令</div><div class='list'>{''.join(E['i'])}</div>")
    if old_n:
        D.append(f"<div class='muted small'>手动指令只显示最近 {MANUAL_SHOW_DAYS} 天的（没处理完的一直显示）；更早的 {old_n} 条不显示</div>")
    D.append(blocks + "</details></section>")
    return ["".join(H), "".join(D)]


def _badges(book: dict, st: dict, sm: dict, waiting: list, now: dt.datetime, tag: str | None = None,
            live: dict | None = None) -> dict:
    """标签上的数字：持仓 = 拿着的只数；交易 = 还会做事的单与指令（_trade_live：撤了 / 不会下单的不算；2026-10-15）；消息 = 24 小时内的提醒。"""
    out = {}
    n = len(st.get("pos") or {}) + sum(1 for u in (st.get("core_units") or {}).values() if int(u or 0) > 0)
    if n:
        out["hold"] = n
    act = (live or _trade_live(book, waiting, now, tag))["n"]
    if act:
        out["trade"] = act
    try:
        from . import news as NW
        ev = (NW.load() or {}).get("events") or []
        cut = now - dt.timedelta(hours=NEWS_SHOW_H)
        k = sum(1 for e in ev if NW.pushable(e) and _ts_jst(e.get("time")) and _ts_jst(e.get("time")) >= cut)
        if k:
            out["news"] = k
    except Exception:                                      # noqa: BLE001
        pass
    return out


def _ts_jst(v):
    try:
        t = dt.datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    return t.astimezone(JST) if t.tzinfo else t.replace(tzinfo=JST)


def _msg_seg(now: dt.datetime | None = None) -> str:
    n = len(_recent_notices(now)[0])                       # 按钮上的数字 = 最近 24 小时的条数（与卡片一致）
    return ("<div class='seg sgseg' role='tablist'><button type='button' data-mseg='news' class='on'>经济威胁消息</button>"   # 默认（2026-10-11 用户）
            "<button type='button' data-mseg='log'>通知记录 " + str(n) + "</button></div>")


def _recent_notices(now: dt.datetime | None = None) -> tuple[list[dict], int]:
    """最近 NOTIFY_SHOW_H 小时内发出的通知（新的在前）与更早的条数（2026-10-12 用户：「通知记录里面只显示 24 小时以内的记录」）。
    记的时刻读不出的也不显示。"""
    from . import notify as NT
    now = now or now_jst()
    cut = (now if now.tzinfo else now.replace(tzinfo=JST)) - dt.timedelta(hours=NOTIFY_SHOW_H)
    hs = NT.history(60)
    keep = [h for h in hs if _ts_jst(h.get("at")) and _ts_jst(h.get("at")) >= cut]
    return keep, len(hs) - len(keep)


def _notify_log_card(now: dt.datetime | None = None) -> str:
    """qbreak 发出的每一条通知（notify.send 记的；数据目录 out/notifications.jsonl，只在本机）：时刻（JST）、标题、内容；只显示最近 24 小时的。
    推送点开 ?tab=news&seg=log&l=<id> → 展开这一条。2026-10-11 用户：不用 Gmail，直接在 qbreak 里通知并记录。"""
    hs, n_old = _recent_notices(now)
    if not hs:
        return ("<section class='card' id='nlog'><h2>通知记录</h2><div class='muted small'>"
                + (f"最近 {NOTIFY_SHOW_H} 小时没有通知（更早的 {n_old} 条不显示）。" if n_old else "还没有。")
                + "qbreak 发出的通知（成交、09:30 自检、买入信号、HALT、经济威胁、手机连不上…）都会记在这里；打开了推送的设备同时会弹出来。</div></section>")
    rows = []
    for k, h in enumerate(hs):
        lv = str(h.get("level") or "info")
        rows.append(f"<details class='hv nw' id='l-{escape(str(h.get('id')))}'{' open' if k == 0 else ''}><summary>"
                    f"{'<b class=neg>★</b> ' if lv in ('warn', 'error') else ''}<span class='muted'>{escape(str(h.get('at') or '')[5:16].replace('-', '/'))} JST</span> "
                    f"{escape(NM.annotate(str(h.get('subject') or '')))}</summary>"      # 以前记下的只有代码 → 显示时补名字（记录本身不改；2026-10-15）
                    f"<div style='white-space:pre-wrap'>{escape(NM.annotate(str(h.get('text') or '')))}</div></details>")
    return (f"<section class='card' id='nlog'><h2>通知记录（最近 {NOTIFY_SHOW_H} 小时 {len(hs)} 条）</h2><div class='muted small'>时间都是日本时间（JST）。"
            f"只显示最近 {NOTIFY_SHOW_H} 小时的" + (f"（更早的 {n_old} 条不显示）" if n_old else "") + "；"
            "qbreak 发出的每一条通知都记在这里（只在这台 Mac）；打开了推送的设备同时会弹出来。</div>" + "".join(rows) + "</section>")


def _news_card(now: dt.datetime) -> str:
    """经济威胁消息（Mac 每 15 分钟取一次；数据目录 cache/news/news.json —— 第三方标题只在本机 / 手机页面上，不入库）。
    达到提醒线的在前；每条点开：发布时间、提醒时间、来源与可信度、冲击与影响链路（因子 → 行业 → 持仓 / 候补）、原文链接。只展示，不参与交易。"""
    from . import news as NW
    try:
        d = NW.load() or {}
        seen = read_json(NW.cache_dir() / "alerted.json", {}) or {}
    except Exception:                                      # noqa: BLE001
        d, seen = {}, {}
    ev = d.get("events") or []
    if not ev:
        return ("<section class='card' id='news'><h2>经济威胁消息</h2><div class='muted small'>还没有（市场仪表盘的定时任务每 15 分钟取一次）</div></section>")
    cut = (now if now.tzinfo else now.replace(tzinfo=JST)) - dt.timedelta(hours=NEWS_SHOW_H)   # 只显示 24 小时内发布的（2026-10-12 用户）；发布时间读不出的也不显示
    n_old = sum(1 for e in ev if not (_ts_jst(e.get("time")) and _ts_jst(e.get("time")) >= cut))
    ev = [e for e in ev if _ts_jst(e.get("time")) and _ts_jst(e.get("time")) >= cut]
    n_low = sum(1 for e in ev if NW.level(e) == "低")         # 程度低的不显示（2026-10-11 用户）
    ev = [e for e in ev if NW.level(e) != "低"]
    ev = sorted(ev, key=lambda e: -(_ts_jst(e.get("time")) or dt.datetime.min.replace(tzinfo=JST)).timestamp())[:40]   # 最新的在上面（2026-10-12 用户）

    def when(v) -> str:
        t = _ts_jst(v)
        return t.strftime("%m/%d %H:%M") if t else "—"
    rows = []
    for e in ev:
        c = e.get("chain") or {}
        lab = "、".join(e.get("event_labels") or []) or "其他"
        det = [f"<div>发布：<b>{escape(when(e.get('time')))} JST</b>"
               + (f" · 提醒：{escape(when(seen.get(e.get('id'))))} JST" if seen.get(e.get("id")) else "") + "</div>",
               f"<div>来源：{escape(str(e.get('publisher') or '—'))}（{int(e.get('n_sources') or 1)} 个来源）· 可信度 {escape(str(e.get('cred')))}"
               f"（{escape(str(e.get('cred_label') or ''))}）· 严重度 {escape(str(e.get('severity')))} · 威胁 {float(e.get('threat') or 0):.2f}</div>"]
        if e.get("why"):
            det.append("<div class='muted small'>为什么可信：" + escape("；".join(str(x) for x in e["why"])) + "</div>")
        if c.get("shock_txt"):
            det.append(f"<div>冲击：{escape(str(c['shock_txt']))}</div>")
        if c.get("down"):
            det.append("<div class='down'>受损的行业：" + escape("、".join(f"{s} {v:+.1f}%" for s, v in c["down"])) + "</div>")
        if c.get("up"):
            det.append("<div class='up'>受益的行业：" + escape("、".join(f"{s} {v:+.1f}%" for s, v in c["up"])) + "</div>")
        if c.get("rules"):
            det.append("<div>经验规则：" + escape("、".join(f"{s}{'↑' if dd > 0 else '↓'}" for s, dd in c["rules"].items())) + "</div>")
        if c.get("tickers_down"):
            det.append("<div class='down'>受损方向的持仓 / 候补：" + escape(NM.labels([str(t) for t in c["tickers_down"][:10]])) + "</div>")
        if c.get("tickers_up"):
            det.append("<div class='up'>受益方向的持仓 / 候补：" + escape(NM.labels([str(t) for t in c["tickers_up"][:10]])) + "</div>")
        link = str(e.get("link") or "")
        if link.startswith("https://"):
            det.append(f"<div><a href='{escape(link)}' target='_blank' rel='noopener noreferrer'>原文</a></div>")
        tm = NW.timing(e, now)
        if tm:
            det.insert(1, f"<div>{escape(_window_text(tm))}（经验估计）</div>")
        det.append("<div class='muted small'>只展示与提醒，不参与交易</div>")
        lv = NW.level(e)
        rows.append(f"<details class='hv nw lv-{'hi' if lv == '高' else 'mid'}' id='n-{escape(str(e.get('id')))}'><summary>"
                    f"<span class='chip {'lvh' if lv == '高' else 'lvm'}'>{lv}</span> "
                    f"{'<b class=neg>★ 已推送</b> ' if NW.pushable(e) else ''}<span class='muted'>{escape(when(e.get('time')))} JST</span> "
                    f"<span class='chip'>{escape(lab)}</span><br>{escape(str(e.get('title_zh') or e.get('title') or '')[:140])}"
                    + (f"<br><span class='muted small'>原文：{escape(str(e.get('title') or '')[:140])}</span>"
                       if e.get("title_zh") and str(e.get("title_zh")).strip() != str(e.get("title") or "").strip() else "")
                    + f"</summary>{''.join(det)}</details>")
    legend = ("<div class='small'><span class='chip lvh'>高</span> 严重度 × 可信度 ≥ 1.5（负面且达到提醒线的会推送）· "
              "<span class='chip lvm'>中</span> ≥ 0.8 · 低的不显示" + (f"（这次 {n_low} 条）" if n_low else "")
              + f" · 只显示最近 {NEWS_SHOW_H} 小时" + (f"（更早的 {n_old} 条不显示）" if n_old else "") + "</div>")
    return (f"<section class='card' id='news'><h2>经济威胁消息</h2><div class='muted small'>时间都是日本时间（JST）。Mac 每 15 分钟取一次；最近一次 {escape(str(d.get('generated') or '—'))}。"
            "★ 已推送 = 威胁度高、推送到了手机。点一条看详细（含影响期）。</div>" + legend
            + ("".join(rows) or f"<div class='muted'>最近 {NEWS_SHOW_H} 小时没有程度中以上的消息</div>") + "</section>")


def _home_stats(pj: dict, st: dict, paper: bool) -> str:
    """首页的总权益 / 现金：含今天已成交（live_ops.held_now 的对账前预计；2026-10-16 用户：卖出 1545、买入 1482 后数字没变）。
    有成交 → 主数字用预计、下面写「含今天已成交 · 账本 ¥…」；立花的现金是约数（只算已经知道的成交）。"""
    eq, cash = pj.get("equity"), pj.get("cash")
    sub_e = sub_c = ""
    if pj.get("has"):
        hd = pj.get("head") or LO.hn_head(pj.get("day_word"))   # 「含今天已成交」/「含 10/16（周五）已成交」
        ld = str(st.get("last_date") or "")
        try:
            d = dt.date.fromisoformat(ld)
            lw = f"{d.month}/{d.day}"
        except ValueError:
            lw = ld or "—"
        sub_e = f"<div class='muted small'>{escape(hd)} · 持仓按 {escape(lw)} 收盘估 · 账本 {_yen(pj.get('equity_ledger'))}</div>"
        sub_c = f"<div class='muted small'>{escape(hd)} · 账本 {_yen(pj.get('cash_ledger'))}</div>"
    ca = ("约" if pj.get("has") and not paper else "") + _yen(cash)
    return (f"<div class='stats'><div><div class='muted'>总权益</div><div class='big'>{_yen(eq)}</div>{sub_e}</div>"
            f"<div><div class='muted'>现金</div><div class='big'>{ca}</div>{sub_c}</div></div>"
            + (f"<div class='small'><b>{escape(pj['note'])}</b></div>" if pj.get("has") and pj.get("note") else ""))


def render(tag: str, tok: str, now: dt.datetime | None = None, mode: str = "local", device: dict | None = None,
           phone: dict | None = None, trigger: "Trigger | None" = None, tab: str | None = None) -> str:
    """操作面板页面（一个账本）。mode = local（Mac 本机：tok = 面板令牌）/ remote（手机：tok = 这台设备的 CSRF 令牌）。
    trigger：面板自动叫执行器的那个对象（顶部显示「盘中自动下单暂停」/ 失败后最早什么时候再叫）。
    tab：?tab=…（服务器先把这个标签显示出来，脚本没跑起来也看得到内容；默认总览）。"""
    from . import holding_view as HV
    now = now or now_jst()
    remote = mode == "remote"
    book, sm = _load(tag)
    st = book.get("state") or {}
    pj = LO.held_now(book, tag, now=now)                   # 含今天已成交的持仓 / 现金（对账前的预计，只展示；2026-10-16 用户：卖出 1545、买入 1482 后持仓没变）
    pst = pj["state"]
    hnb = pj.get("by_ticker") or {}
    pre = MO.pre_reconcile(pj, now)                         # 现在写的指令在对账之前执行（成交日当天开盘前 / 盘中 / 午休）
    later_act = ("今天盘中执行器不再动它（同一只当天只下一笔；账本" + f"{pj.get('when_sp') or ''}对账才记上）："
                 "收盘后（15:25 起）可以写卖出 / 调仓，下一个交易日开盘执行")   # 今天买进的操作那一行（成交那句在 holding_view 的 today 里）
    #                                                         收盘后 / 周末：对账之后执行 → 按钮照常（2026-10-16 二次复核）
    paper = tag.startswith("paper")
    when = MO.when_for(now, book)                           # 马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘 / 早上的运行没完成（G9）
    man = book.get("manual") or {}
    cap = MO.MANUAL_CAP_PCT                                 # 手动买入 / 加仓的上限（2026-10-12：最多到总权益）
    kl = sm.get("kline") or {}
    ktrend = kl.get("trend") or {}
    cdoc = _chart_data(tag) or {}
    if (cdoc.get("bars_asof") or "") > str(kl.get("asof") or ""):   # 收盘后补过日线（charts_refresh）→ 趋势标签用更新过的（横展开）
        fresh = {t_: v.get("trend") for t_, v in (cdoc.get("tickers") or {}).items() if v.get("trend")}
        ktrend = {**ktrend, **fresh}
        sg_ = dict(sm.get("suggest") or {})
        sg_["rows"] = [({**r, "trend": fresh[r["ticker"]]} if r.get("ticker") in fresh else r) for r in sg_.get("rows") or []]
        sm = {**sm, "suggest": sg_}
    has_k = bool(kl.get("file")) and (paths.out_dir() / str(kl["file"])).exists()
    halt = PP.halt_text()
    arm = paths.arm_state()                                 # 和立花适配器同一个判断（UX-12）：内容是 ARMED 才算解锁
    real = tag == "tachibana"                               # 真钱（立花本番）：顶栏醒目的标识（B12 / UX-11）
    hist = st.get("history") or []
    eq = float(hist[-1][1]) if hist else None
    pct = MO.position_pct(pst)                              # 只展示：含今天已成交
    pend = pst.get("pending_exit") or {}
    waiting = MO.unseen(tag, book)
    dropped = MO.cancelled(waiting)                                    # 执行器还没读、已经点了撤回的
    tlive = _trade_live(book, waiting, now, tag, halt=bool(halt))      # 「交易」里哪些行还会做事：数字、「今天要成交的单」/「手动指令」的写法同一个判断（2026-10-15）
    sp = tlive.get("split") or _trade_split(book, waiting, now, tag, bool(halt), tlive)   # 每一行放进哪一块（今天要成交 / 另有 … / 已结束；
    #   2026-10-16）：数字就是按这一份数的（_trade_live 算不成时按以前的数法 → 这里另分一次）
    #   在处理的指令：票 →「见 …」指着那条指令真正在的那一块（_where_item；复核 7，2026-10-16：以前一律写「「交易」的「手动指令」」，
    #   收盘后写的在收起的「另有 …」里时页面上找不到）
    acts = [it for it in (man.get("items") or {}).values() if it.get("status") in MO.ACTIVE and not it.get("cancel_req")]
    busy = {it.get("ticker"): _where_item(sp, it.get("id")) for it in acts if it.get("kind") in MO.POS_KINDS}
    busy.update({r.get("ticker"): _where_item(sp, r["id"]) for r in waiting if r.get("kind") in MO.POS_KINDS and r["id"] not in dropped})
    core_busy = next((_where_item(sp, r["id"]) for r in reversed(waiting)                # 执行器还没读的闲置资金比例指令
                      if r.get("kind") == "core" and r["id"] not in dropped), "")
    cr = book.get("core_rule") or {}
    bfix = MO.core_fixed(book, tag)                    # 固定口数的 ETF：不跟闲置资金比例（卖出 / 调仓只改它的固定口数；2026-10-13）；还没读的固定 / 恢复按规则也算（2026-10-14）
    core_late = bool(cr) and MO.core_pending(book) is not None   # 与执行器 / 「交易」的 core: 那一行同一个判断（复核 3）
    core_now = {str(o.get("ticker")): o for o in book.get("orders") or []          # 今天盘中已经照比例调过的核心 ETF（口数明天早上对账后更新）
                if o.get("reason") == "manual_core" and o.get("decided_on") == st.get("last_date")
                and (o.get("status") in ("SENT", "FILLED", "PARTIAL", "SENDING", "ERROR")
                     or (o.get("status") in ("EXPIRED", "CANCELLED") and int(o.get("filled_qty") or 0) > 0))}   # 已失效 / 撤掉但成交过一部分：口数也变了
    buying = {it.get("ticker"): _where_item(sp, it.get("id")) for it in acts if it.get("kind") == "buy"}   # 票 →「见 …」（同上）
    buying.update({r.get("ticker"): _where_item(sp, r["id"]) for r in waiting if r.get("kind") == "buy" and r["id"] not in dropped})
    H = [f"<header class='top{' real' if real else ''}'><div class='bar'><b>qbreak 操作面板</b>"
         + ("<span class='real-badge'>真钱（立花本番）</span>" if real else "") + "<span class='sp'></span>"
         f"<span class='muted small'>{escape(now.strftime('%m/%d %H:%M JST'))}</span>"
         "<button class='btn sm' data-act='reload'>刷新</button></div>"
         "<nav class='tabs'>" + "".join(f"<a href='/?book={t}' class='{'on' if t == tag else ''}'>{escape(BOOKS[t])}</a>"
                                       for t in BOOKS if t in books() or t == tag)        # 正在看的账本总在标签里
         + "</nav></header><main><div id='top'></div><div id='stale' class='card warn small' role='status' hidden></div>"]
    warn = []
    if halt:
        warn.append(f"HALT 生效中（{escape(NM.annotate(halt))}）：不下单，解除之后才处理")
    if not paper and arm == "bad":
        warn.append("ARM 文件在，但内容不是 ARMED（立花只认内容 ARMED）：单会被挡住，不会真的发出去")
    elif not paper and arm == "off":
        warn.append("立花还没解锁（没有 ARM）：单会被挡住，不会真的发出去")
    if tag in READONLY:
        warn.append("dry-run 的账本：只能看（只算不发单），这里的按钮不会写指令")
    if paper:
        warn.append("模拟账户：手动操作后会和云端模拟盘不一致")
        if paths.live_installed() and not _scheduled(paths.PAPER_AGENT):   # 上线后模拟操盘的定时任务已卸载（LU-20 / OPS-06）
            warn.append("模拟账户已停：装的是立花本番（模拟操盘的定时任务已卸载），这个账本不再推进，这里写的指令不会被执行"
                        " → 用上面的「立花（本番）」")
    cpause, csig = man.get("core_pause"), man.get("core_signal")      # 卖出 ETF 后停买；停着时规则从「不拿」变成「拿」= 买入信号
    if cpause and csig:
        warn.insert(0, escape(f"闲置资金 ETF 出现买入信号（{csig.get('date')} 收盘）：{MO.signal_text(csig)} → 确认后才买（见下面「闲置资金」）"))
    runl = _run_lines(tag, book, now, halt)                # 执行器这次跑成没有 / 没下成的单 / 早上没跑完 / 09:30 自检
    runl += _input_lines(sm, st)                           # 判断层的输入没更新 / 行情有问题 + 修法 / 离场判断被跳过（B10）
    tz = trigger.status(tag, now, book) if trigger is not None else None
    if tz:                                                 # 面板叫的执行器连续失败：暂停 / 退避（Trigger）
        runl.insert(0, (tz[0], escape(tz[1])))
    bad_run = any(c == "neg" for c, _ in runl)
    H.append(PANE + "home")                               # ── 下面按标签页分组（_panes 把它们包成 <div class='pane'>）──
    H.append(f"<section class='card{' warn' if halt or bad_run else ''}'><div class='head'><b>{escape(BOOKS.get(tag, tag))}</b>"
             f"<span class='chip'>决策日 {escape(str(st.get('last_date') or '—'))} → 成交日 {escape(str(sm.get('fill_day') or '—'))}</span></div>"
             + _home_stats(pj, st, paper)
             + f"<div>现在点买卖 → <b>{escape(when)}</b>下单</div><div class='muted small'>{escape(MO.RULE_TEXT)}</div>"
             + "".join(f"<div class='{'neg' if 'HALT' in w or 'ARM' in w or '买入信号' in w or '已停' in w else 'muted'} small'>★ {w}</div>"
                       for w in warn)
             + "".join(f"<div class='{c} small'>{h}</div>" for c, h in runl)
             + "</section>")
    if not st:
        H.append("<section class='card'>执行器还没有账本（第一次运行之后才有持仓）。</section>")
    H.append(_money_card(tag, book, now, pj))             # 〔77〕C：损益 / 年内已实现与预计代扣 / 最近成交 / 日志 / 入出金
    H.append(PANE + "hold")
    H.append(_alloc_card(pj["book"], HV.overlay(sm.get("holding_view") or {}, pj), pj))  # 最上面：每个仓位占多少（2026-10-12；含今天已成交，2026-10-16）
    H.append(_broker_card(tag, now, pj))                  # 〔77〕C：立花那边实际是什么（快照）
    H.append(PANE + "more")
    H.append(_gate_card(tag))                             # 〔77〕C：上线准备
    hv = sm.get("holding_view") or {}
    if not hv.get("holdings") and not hv.get("core") and st:               # 还没有算过（旧的汇总）：用账本里的数字
        hv = {"bar_date": st.get("last_date"),
              "holdings": [{"ticker": t, "name": NM.name(t), "shares": int(p.get("shares") or 0), "entry_date": p.get("entry_date"),
                            "entry_px": p.get("entry_px"), "error": "持有理由 / 趋势在下一次执行器运行之后显示"}
                           for t, p in (st.get("pos") or {}).items()],
              "core": [{"ticker": t, "name": NM.name(t), "units": int(u), "why": "闲置资金规则（核心 ETF）"}   # 名字（以前写成代码；2026-10-15）
                       for t, u in (st.get("core_units") or {}).items() if int(u)]}
    hv = HV.overlay(hv, pj)                                 # 今天已成交：卖光的移到「今天已卖出」、今天买进的加一行（对账前；2026-10-16）
    _ht = list((pst.get("pos") or {}).keys()) + [t for t, u in (pj.get("core_units") or {}).items() if int(u or 0) > 0]
    hmarks = _news_marks(_ht, now) if _ht else {}                     # 持仓（个股 + 拿着的核心 ETF）的消息影响
    try:                                                    # 盘中观测（读结果文件；不取价）：选股页的卡片、持仓每只一行
        iv = IW.view(IW.load(tag), now)
    except Exception as e:                                  # noqa: BLE001  展示用：读不了不影响页面
        log.warning("盘中观测读不了：%s", e)
        iv = None
    try:                                                    # 今天还能买几次 / 卖几次（D6；交易页的卡片与持仓的小标记同一个数）
        rm = room_of(tag, book, sm, now, trigger, waiting) if st else None
    except Exception as e:                                  # noqa: BLE001  展示用：算不出不影响页面
        log.warning("「今天还能买几次 / 卖几次」没算成：%s", e)
        rm = None

    def chart(t: str, kind: str) -> str:
        return _chart_box(t, kind, has_k)

    def actions(r: dict, kind: str) -> str:
        t = str(r["ticker"])
        if kind == "core":
            return (tchips(ktrend.get(t)) + _news_mark(hmarks.get(t)) + _room_chip(rm, t) + _core_actions(r, t)
                    + _corefix(t, _nm(t, r.get("name"))) + _core_exit(t) + chart(t, "core"))
        qt = f"<div class='qt small' data-q='{escape(t)}'></div>" if t in (pst.get("pos") or {}) else ""   # 现价（/api/quotes）
        ia = _intraday_line(iv, t) if t in (pst.get("pos") or {}) else ""   # 盘中：收盘卖出线离现价多远（/api/intraday；2026-10-16）
        return tchips(ktrend.get(t), stats=True) + qt + ia + _room_chip(rm, t) + _actions(r, t)   # 今天还能卖 / 买（D6）

    def _corefix(t: str, name: str) -> str:
        """核心 ETF 固定口数（2026-10-11 用户：持仓里的纳指 ETF、对冲美债也要能买入）：没拿的 →「买入…」、拿着的 →「固定口数…」；
        已固定 → 写出来 +「恢复按规则」。只写手动指令（什么时候下单 = corefix_fill：盘中马上 / 开盘后马上 / 下一次决策，D1；其余闲置资金照规则分）。
        已经写了、执行器还没读的固定 / 恢复按规则 → 写「已登记：…（下一次决策起）」、按钮按登记之后的样子（恢复按规则登记了 → 不再给「恢复按规则」；
        2026-10-15 复核：以前确认之后页面上还是原来的按钮，像没写成、会再点一次）。"""
        if tag in READONLY:
            return ""
        fixed = (man.get("core_fix") or {}).get(t)
        pend = [r for r in waiting if r.get("kind") == "corefix" and r.get("ticker") == t and r["id"] not in dropped and not r.get("fund_for")]
        last = pend[-1] if pend else None                   # 执行器读的时候按写的顺序：最后一条说了算
        eff = bfix.get(t) if last is not None else fixed    # 登记之后的样子（core_fixed：还没读的也算上）
        c = MO.core_info(book, t) or {}
        px, lot = float(c.get("px") or 0), int(MO.core_lot(book, t) or 1)
        cur = int((pj.get("core_units") or {}).get(t, 0))  # 含今天已成交（对账前；2026-10-16）
        data = (f" data-t='{escape(t)}' data-name='{escape(name)}' data-px='{px:g}' data-lot='{lot}' data-cur='{cur}'"
                f" data-eq='{float(eq or 0):.0f}'")
        H_ = []
        plan = ""
        if last is not None:
            H_.append("<div class='small'><b>已登记：" + ("恢复按规则" if last.get("clear") else f"固定 {int(last.get('units') or 0):,} 口")
                      + "</b><span class='muted'>（执行器还没读；" + escape(MO.corefix_fill(now, book, tag)["text"])   # D1（2026-10-15）：以前一律「下一次决策起」
                      + "；要撤回在" + _where_item(sp, last.get("id"))
                      + (f"；在那之前还是手动固定 {int(fixed):,} 口" if fixed is not None else "")
                      + "）</span></div>")
        elif fixed is not None:
            H_.append(f"<div class='small'><b>手动固定 {int(fixed):,} 口</b>（不按规则自动调、不跟闲置资金比例；其余闲置资金照规则）"
                      "<span class='muted'>；卖出 / 减仓 / 加仓：「固定口数…」（0 口 = 全部卖出）</span></div>")
        can_clear = fixed is not None and eff is not None   # 恢复按规则：账本里固定着、也没登记过恢复（只固定在还没读的指令里的 → 撤回那条）
        if can_clear:
            plan = f" data-plan='{escape(MO.corefix_clear_text(book, t, tag, now))}'"   # 「恢复按规则」之后会怎样（2026-10-13）
        btn = "买入…" if cur <= 0 and eff is None else "固定口数…"
        H_.append(f"<div class='act'><button class='btn' data-act='corefix'{data}{'' if px > 0 else ' disabled'}>{btn}</button>"
                  + (f"<button class='btn'{plan} data-act='corefix-clear'{data}>恢复按规则</button>" if can_clear else "") + "</div>")
        if px <= 0:
            H_.append("<div class='muted small'>执行器下一次运行算出价格之后可用</div>")
        return "".join(H_)

    def _core_actions(r: dict, t: str) -> str:
        """持有的核心 ETF：卖出全部（= 闲置资金比例 0%：卖出后停买，出现买入信号要你确认才买）/ 调仓…（换算成「闲置资金比例」：
        规则每天把核心调回 规则目标额 × 比例）。执行器还没算过规则目标额（更新后第一次运行之前）也能卖出全部。"""
        cur = int((pj.get("core_units") or {}).get(t, 0))  # 含今天已成交（对账前；2026-10-16）
        if t in (pj.get("sold_out") or []):                 # 今天已经卖光：不给按钮（再点卖出 = 比例 0%、停买 ETF）
            return f"<div class='act muted'>{escape(hnb[t]['text'])}</div>" if t in hnb else ""
        if cur <= 0:
            return ""
        qt = f"<div class='qt small' data-q='{escape(t)}'></div>"                      # 现价（/api/quotes，盘中每 1 分钟刷新）
        if pre and t in (pj.get("new") or []) and t not in bfix:   # 今天买进、没固定、当天对账前执行：执行器今天不动它
            return qt + f"<div class='act muted'>{escape(later_act)}</div>"   # 「今天买进…」那句上面（holding_view 的 today）已经写了，不重复（2026-10-16 复核）
        if t in bfix:                                       # 固定口数：不换算成闲置资金比例（否则别的 ETF 跟着变、固定的这只卖了又买回；2026-10-13）
            px_ = float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)
            return (qt + f"<div class='muted small'>现在 {cur:,} 口" + (f" · 约 {_yen(cur * px_)}" if px_ > 0 else "")
                    + " · 手动固定：卖出 / 减仓 / 加仓用下面的「固定口数…」（只改这只的固定口数；别的 ETF 与闲置资金比例不变）</div>")
        if core_busy:
            return qt + f"<div class='act muted'>有一条闲置资金比例的指令在处理（见{escape(core_busy)}）</div>"
        o = core_now.get(t)
        if o is not None:
            q, n = int(o.get("filled_qty") or 0), int(o.get("qty") or 0)
            got = ("已成交" if q >= n > 0 else f"成交 {q:,} / {n:,} 口" + {"EXPIRED": "，其余已失效", "CANCELLED": "，其余已撤"}.get(
                str(o.get("status")), "") if q > 0
                   else "等成交" if o.get("status") in ("SENT", "PARTIAL") else "结果不明")
            sw = pj.get("settle") or ""
            sw = "明天早上" if not sw or sw.startswith("明早") else (pj.get("when_sp") or "")   # 周五 / 连休前：「下个交易日 10/19（周一）07:40」（2026-10-16）
            return (qt + f"<div class='act muted'>今天盘中已照比例{'卖出' if o.get('side') == 'SELL' else '买入'} {n:,} 口（{got}）："
                    f"口数{sw}对账后更新</div>")
        c = MO.core_info(book, t)
        if c is not None and t in hnb:                      # 今天有成交（还拿着）：显示的口数按投影
            c = {**c, "cur": cur}
        px = c["px"] if c else float((st.get("core_last") or {}).get(t) or 0)
        sell = (f"<button class='btn sell' data-act='core-sell' data-t='{escape(t)}' data-name='{escape(_nm(t, r.get('name')))}'"
                f" data-shares='{cur}'>卖出全部</button>")
        if c is None:                                       # 比例改过、执行器还没算过规则目标额：卖出全部照样可以，调仓等下一次运行
            return (qt + "<div class='act'>" + sell + "<button class='btn' disabled>调仓…</button></div>"
                    f"<div class='muted small'>现在 {cur:,} 口" + (f" · 约 {_yen(cur * px)}" if px > 0 else "")
                    + " · 闲置资金比例改过：调仓在执行器下一次运行（交易日 07:40）之后可用</div>")
        if c["selling"]:
            if cpause and int((cr.get("units100") or {}).get(t, 0)) > 0:   # 规则想拿、是你停的（2026-10-13：不是熊市）
                return (qt + "<div class='act'>" + sell + "</div><div class='small'><b class='neg'>停买：开盘卖出（你停的）</b>"
                        "<span class='muted'>；要恢复：下面「闲置资金」的「确认买入」</span></div>")
            return (qt + "<div class='act'>" + sell + "</div><div class='small'><b class='neg'>规则在开盘卖出（熊市 / 换 ETF）</b>"
                    "<span class='muted'>；点「卖出全部」= 卖出后停买（之后要你确认才买）</span></div>")
        late_txt = f"（还没照它调完，见{_where_core(sp)}）" if core_late else ""   # 指着那一行真正在的那一块（复核 3）
        data = (f" data-t='{escape(t)}' data-name='{escape(_nm(t, r.get('name')))}' data-shares='{c['cur']}' data-px='{round(c['px'], 4)}'"
                f" data-core='1' data-lot='{c['lot']}' data-u100='{c['u100']}' data-cpct='{c['pct']:g}' data-approx='{1 if c.get('approx') else 0}'")
        share = f"{c['cur'] * c['px'] / eq * 100:.1f}" if eq and c["px"] > 0 else "—"
        return (qt + "<div class='act'>" + sell
                + f"<button class='btn' data-act='adj'{data}{'' if c['px'] > 0 and eq else ' disabled'}>调仓…</button></div>"
                f"<div class='muted small'>现在 {c['cur']:,} 口 · 约 {_yen(c['cur'] * c['px'])} · 约占权益 {share}% · "
                f"闲置资金比例 {c['pct']:g}%{late_txt}"
                + ("<br>规则目标额还没算过（执行器下一次决策才算）：100% 先按现在的口数估算" if c.get("approx") else "") + "</div>")

    def _core_exit(t: str) -> str:
        """拿着的核心 ETF「什么时候会自动卖」+ 离触发还有多远（只展示；数字 = 执行器早上的汇总）。算不了 → 不显示（不影响按钮）。"""
        try:
            c = MO.core_info(book, t)
            return _exit_html(CX.build(t, sm, pj["book"], px=c["px"] if c else None, lot=MO.core_lot(book, t),
                                       fixed=bfix.get(t)))   # 含今天已成交（卖光的 → None；2026-10-16）；固定口数的：规则不会自动卖（复核）
        except Exception as e:                                # noqa: BLE001  展示用：一只算不出不影响页面
            log.warning("ETF 卡片「什么时候会自动卖」没算成：%s", e)
            return ""

    def _actions(r: dict, t: str) -> str:
        if pre and t in (pj.get("new") or []) and t in hnb:   # 今天买进、当天对账前执行：执行器今天不动它（收盘后 / 周末 → 按钮照常）
            return f"<div class='act muted'>{escape(later_act)}</div>" + chart(t, "stock")   # 「今天买进…」那句上面已经写了（复核：以前写两遍）
        p = (pst.get("pos") or {}).get(t)                  # 今天部分成交、还拿着的：股数按投影，按钮照常（执行器对账之后按实际持仓算）
        if p is None:
            return "<div class='act muted'>（这只票已经不在执行器的账本里）</div>" + chart(t, "stock")
        if t in pend:
            if pend[t] != "manual" and r.get("queued"):
                return chart(t, "stock")                     # 标题行已经写了「已排定开盘卖（…）」
            lab = "已在卖出（手动）" if pend[t] == "manual" else f"已排定开盘卖（{HV.EXIT_TEXT.get(pend[t], str(pend[t]))}）"
            return f"<div class='act'><b class='neg'>{escape(lab)}</b></div>" + chart(t, "stock")
        if t in busy:
            return f"<div class='act muted'>有一条手动指令在处理（见{escape(busy[t])}）</div>" + chart(t, "stock")
        cur = pct.get(t)
        px = float(p.get("last_close") or p.get("entry_px") or 0)
        sh = int(p.get("shares") or 0)
        nmk = _news_mark(hmarks.get(t))                    # 拿着的票也标（横展开）
        data = f" data-t='{escape(t)}' data-name='{escape(_nm(t, r.get('name')))}' data-shares='{sh}'"
        return (nmk + "<div class='act'>"
                f"<button class='btn sell' data-act='sell'{data}>卖出全部</button>"
                f"<button class='btn' data-act='adj'{data} data-px='{px:g}'{'' if px > 0 and eq else ' disabled'}>调仓…</button></div>"
                f"<div class='muted small'>现在 {sh:,} 股 · 约 {_yen(sh * px)} · 约占权益 {f'{cur:.1f}' if cur is not None else '—'}%</div>"
                + chart(t, "stock"))
    held_core = {str(r.get("ticker")) for r in hv.get("core") or []}
    other = [(t, c) for t, c in (kl.get("items") or {}).items() if c.get("kind") == "core" and t not in held_core]
    more = ("<details class='hv'><summary class='muted'>其他闲置资金 ETF（现在没拿）的 K 线</summary>"
            + "".join(f"<div class='hv'><b>{escape(NM.code(t))} {escape(_nm(t, c.get('name')))}</b> <span class='muted'>现在 0 口</span>"
                      f"{tchips(ktrend.get(t))}{_corefix(t, _nm(t, c.get('name')))}{chart(t, 'core')}</div>" for t, c in other)
            + "</details>") if other else ""
    held_any = bool(pst.get("pos")) or any(int(u or 0) > 0 for u in (pj.get("core_units") or {}).values())
    H.append(PANE + "trade")
    H.append(_room_card(rm))                                # 最上面：今天还能买几次 / 卖几次（D6；2026-10-15 用户要求 3）；下面的两张卡片在后面拼（要先拼好指令的每一行）
    H.append(PANE + "hold")
    H.append(_kline_help())                                 # 整页一份的「怎么看 K 线图」：持仓的 K 线上面（2026-10-15 用户：「选股中的怎么看K线图要放到持仓中的K线的上面」）
    H.append("<section class='card' id='holdings'>" + HV.html(hv, actions=actions) + more
             + ("<div id='qt-note' class='muted small'>现价：Yahoo 1 分钟线（约晚 20 分钟）</div>" if held_any else "") + "</section>")
    H.append(PANE + "pick")
    H.append(_intraday_card(iv))                            # 最上面：今天盘中规则的暂定买点（约晚 20 分钟；2026-10-16）
    H.append("<div class='khgo small'>怎么看 K 线图：说明在「持仓」的 K 线上面 <a href='#khelp' data-khelpgo='1'>去看 ›</a></div>")   # 选股只留一行指过去（2026-10-15）
    sgd = sm.get("suggest") or {}
    sctx = _suggest_ctx(sgd, book, tag, marks=_news_marks([r["ticker"] for r in sgd.get("rows") or [] if r.get("ticker")], now), now=now)
    H.append(_auto_buy_card(sgd, book, tag, eq, buying=buying, chart=chart, ctx=sctx))   # 最上面：规则接下来会自动买的（2026-10-12；每行点开 = K 线、买入…，2026-10-14）
    H.append(_suggest_card(sgd, book, tag, buying, when, eq, cap, chart, ctx=sctx))      # 上面已列的不重复（2026-10-15）
    H.append(PANE + "hold")
    cp = float(man.get("core_pct", 100.0))
    slider = ("<div class='stepper'><button class='btn' data-act='core-step' data-d='-10' aria-label='减 10%'>−10</button>"
              f"<output id='core-val' class='big'>{cp:g}%</output>"
              "<button class='btn' data-act='core-step' data-d='10' aria-label='加 10%'>+10</button></div>"
              f"<input type='range' id='core-pct' min='0' max='100' step='5' value='{cp:g}' aria-label='闲置资金比例 %'>"
              "<div class='act'><button class='btn primary' data-act='core'>保存</button></div>")
    if cpause:                                              # 卖出 ETF 后停买：规则不自动买；出现买入信号只提醒，你点「确认买入」才买
        want = [(t, int(n)) for t, n in (cr.get("units100") or {}).items() if int(n) > 0 and t not in bfix]   # 固定口数的不算（2026-10-13）
        now_txt = ("想拿 " + "、".join(f"{NM.label(t)} 约 {n:,} 口" for t, n in want) if want else
                   "不拿核心 ETF（熊市 / 没有闲置资金）") if cr.get("units100") is not None else "执行器下一次运行之后显示"
        ri = MO.resume_info(book, tag, now)                 # 确认之后什么时候买（规则不拿 / 今天已经有单 → 不是马上；2026-10-13）
        la_why = MO.allin_busy_text(MO.live_allin(tag, book))   # 「全部换成」已下单 / 在等：不给恢复按钮（点了也会被拒；2026-10-14）
        btn = (f"<div class='act muted'>有一条闲置资金比例的指令在处理（见{escape(core_busy)}）</div>" if core_busy else
               f"<div class='act muted small'>{escape(la_why)}</div>" if la_why else
               f"<div class='act'><button class='btn primary' data-plan='{escape(ri['text'])}' data-act='core-resume'>确认买入（恢复照规则）</button></div>")
        fixl = ("<div class='small'>手动固定 " + "、".join(escape(NM.qty(t, f"{n:,} 口")) for t, n in sorted(bfix.items()))
                + ("（停买中也照买）" if any(n > 0 for n in bfix.values()) else "（不跟比例）") + "</div>") if bfix else ""
        prev = ""
        if cpause.get("allin"):                             # 「全部换成 X」停的：之前的比例 / 固定口数（只显示；你点了才恢复；2026-10-13）
            pp, pf = cpause.get("prev_pct"), cpause.get("prev_fix") or {}
            parts = ([f"比例 {float(pp):g}%"] if pp is not None else []) + [f"{NM.label(t)} 固定 {int(u):,} 口" for t, u in sorted(pf.items())]
            if parts:
                rb = ""
                if pp is not None and 0 < float(pp) < 100 and not core_busy and not la_why:
                    rp = MO.resume_info(book, tag, now, pct=float(pp))   # 只买规则目标额的 N%（2026-10-14）
                    rb = (f"<div class='act'><button class='btn' data-pct='{float(pp):g}' data-plan='{escape(rp['text'])}' data-act='core-restore'>"
                          f"恢复成 {float(pp):g}%</button></div>")
                prev = (f"<div class='small'>「全部换成 {escape(NM.label(cpause['allin']))}」之前：{escape('、'.join(parts))}"
                        + ("<span class='muted'>（比例 100% = 「确认买入」）</span>" if pp is not None and float(pp) >= 100 else "") + "</div>" + rb
                        + ("<div class='muted small'>固定口数不会自动恢复：要的话在各 ETF 下面重新点「固定口数…」</div>" if pf else "")
                        + "<div class='muted small'>都不会自动恢复：你点了才改</div>")
        H.append(f"<section class='card{' warn' if csig else ''}' id='core'><h2>闲置资金（核心 ETF）</h2>"
                 f"<div><b>停买中</b>（{escape(str(cpause.get('since') or '—'))} 起"
                 + (f"，你卖出 {escape(NM.label(cpause['ticker']))}" if cpause.get("ticker") else "") + "）：闲置资金留现金，规则不自动买 ETF</div>"
                 + (f"<div class='neg'><b>★ 买入信号（{escape(str(csig.get('date')))} 收盘）：{escape(MO.signal_text(csig))}</b></div>"
                    if csig else "<div class='muted small'>出现买入信号（规则从「不拿」变成「拿」）会提醒你（Mac 通知 + 这里）</div>")
                 + f"<div class='muted small'>规则现在：{escape(now_txt)}</div>" + fixl + btn
                 + ("" if la_why else f"<div class='muted small'>{escape(ri['text'])}。</div>") + prev
                 + ("" if la_why else f"<details class='hv'><summary class='muted'>按别的比例恢复（例：只放一半）</summary>{slider}</details>")
                 + "</section>")
    elif not any(MO.core_info(book, t) for t in held_core):   # 拿着核心 ETF 时在它下面调（卖出全部 / 调仓…）；没拿着时用这里
        H.append("<section class='card' id='core'><h2>闲置资金（核心 ETF）比例</h2>"
                 f"<div>现在：规则目标额的 <b>{cp:g}%</b>（100% = 照规则；0% = 全部留现金）</div>" + slider
                 + f"<div class='muted small'>{escape(when)}照新比例调核心 ETF；之后每天按这个比例。个股照规则。</div></section>")
    items = sorted((man.get("items") or {}).values(), key=lambda x: x.get("at", ""), reverse=True)

    allrec = {**{x["id"]: x for x in waiting}, **(man.get("items") or {})}
    void = MO.voided(waiting)
    _tlabel = NM.label                                     # 「代码 名字」（2026-10-12 用户：只写代码不知道是哪只；2026-10-15 起 names.py 唯一入口）

    def _named(r: dict) -> str:                            # 以前 describe 之后 str.replace 代码 → 指令 id / cid 里的代码也被换掉（2026-10-15 修）
        return MO.describe(r)

    def _what(r: dict) -> str:
        if r.get("kind") == "cancel":                       # 撤回指令：写它撤的是哪一条（带名字）
            tg = allrec.get(r.get("target"))
            return escape("撤回：" + (_named(tg) if tg else str(r.get("target"))))
        return escape(_named(r))

    def _cbtn(r: dict, placed: int) -> str:                 # 「撤单」：同批一起撤的条数按 cancel_plan（与实际撤的一致）；同批卖单还挂在交易所 → 不给按钮
        if MO.allin_member(r) and r.get("kind") != "buy":
            b0 = MO.batch_buy(r, list(allrec.values()))
            if b0 is not None and (b0.get("status") in MO.ACTIVE or b0["id"] not in (man.get("items") or {})):
                return f"<span class='chip'>随「全部换成 {escape(NM.label(r.get('fund_for')))}」一起（撤回买入那条）</span>"
        pl = MO.cancel_plan(tag, book, r["id"], now=now)
        if pl["why"]:
            return ""
        if pl["sent"] and (pl["target"] or {}).get("fund") == "all":
            return "<span class='chip'>同批卖单还挂在交易所：要撤先用「今天要成交的单」撤那几笔卖单</span>"
        wt = f" data-wtxt='{escape(MO.now_sell_withdrawn(r))}'" if placed == 2 else ""   # 15:30 失效的盘中卖出：按下单那天写（G16 复核）
        return (f"<button class='btn sm danger' data-act='cancel' data-id='{escape(r['id'])}' data-placed='{placed}' data-desc='{_what(r)}'"
                f" data-fund='{len(pl['todo'])}' data-stuck='{len(pl['stuck'])}'{wt}>撤单</button>")

    def _ubbtn(r: dict) -> str:                             # 还没读的「解除不买回」：撤回（读到之前撤回 → 不解除；2026-10-13）
        if MO.check({"kind": "cancel", "target": r["id"]}, book, tag, now=now):
            return ""
        return (f"<button class='btn sm danger' data-act='cancel' data-kind='unblock' data-id='{escape(r['id'])}' data-placed='0'"
                f" data-desc='{_what(r)}' data-fund='0' data-stuck='0'>撤回</button>")

    def _unbtn(r: dict) -> str:                             # 撤回指令的「撤销撤回」（能撤销才给；与提交同一个检查）
        if r.get("kind") != "cancel" or MO.check({"kind": "uncancel", "target": r["id"]}, book, tag, sm=sm, now=now) \
                or _uncancel_warn0(allrec, r["id"], sm):
            return ""
        tg = allrec.get(r.get("target")) or {}                # 确认框写恢复之后实际什么时候、按什么价处理（不是「原来的时间」；2026-10-13）
        hl = paths.halt_file().exists() and tg.get("kind") in MO.ORDER_KINDS + ("core", "corefix")
        return (f"<button class='btn sm' data-act='uncancel' data-id='{escape(r['id'])}' data-desc='{_what(r)}'"
                f" data-st='{escape(MO.wait_word(tg))}'"         # 恢复成「等下单」/「等执行器读」（比例 / 固定口数 / 解除不是单；2026-10-14）
                f" data-when='{escape(MO.uncancel_when(tg, now, book, tag))}'" + (" data-halt='1'" if hl else "") + ">撤销撤回</button>")

    rows = []                                               # [(指令 id, 一行)]
    for r in waiting:
        if r.get("kind") == "uncancel" or r["id"] in void:  # 撤销撤回本身、已被撤销的撤回：不显示（去掉撤销记录）
            continue
        btn = (_cbtn(r, 0) if r["kind"] in MO.ORDER_KINDS + ("core", "corefix") and r["id"] not in dropped
               else _ubbtn(r) if r["kind"] == "unblock" and r["id"] not in dropped else _unbtn(r))
        wt = MO.wait_word(r)                               # 比例 / 解除 / 撤回不是单（2026-10-13）
        wx = "" if r["id"] in dropped or r["kind"] in CANCEL_KINDS else MO.wait_text(r, now, book, tag)
        wx = wx[len(wt) + 1:] if wx.startswith(wt + "：") else ""   # 什么时候（D1 / D5，2026-10-15：与 now_due / 执行器同一个时段口径；固定口数写具体日子）
        if sp["itxt"].get(r["id"]) and r["id"] not in dropped:   # 分块另有说法（收盘后状态不明的单：等登记；复核 4）→ 代替平常的「什么时候」
            wx = sp["itxt"][r["id"]]
            wx = wx[1:-1] if wx.startswith("（") and wx.endswith("）") else wx
        rows.append((r["id"], f"<div class='li'><div class='grow'><b>{_what(r)}</b> <span class='chip'>"
                    f"{wt + '（撤回中）' if r['id'] in dropped else wt}</span>"
                    f"<div class='muted small'>{escape(str(r.get('at', ''))[5:16].replace('T', ' '))}"
                    f"{(' · ' + escape(wx)) if wx else ''}</div></div>{btn}</div>"))
    cut = now - dt.timedelta(days=MANUAL_SHOW_DAYS)                 # 2026-10-12 用户：「交易里面只显示两天以内的」
    items = [it for it in items if it.get("kind") != "uncancel" and it.get("status") != "voided"]   # 撤销撤回、已撤销的撤回：不显示
    recent = [it for it in items if it.get("status") in MO.ACTIVE or sp["items"].get(it.get("id")) in ("today", "later")
              or (_ts_jst(it.get("at")) or cut) > cut]      # 没处理完的（还没照它调的固定口数也算）一直显示
    old_n = len(items) - len(recent)
    k_end = 0
    for it in recent:
        if sp["items"].get(it.get("id"), "ended") == "ended":
            k_end += 1
            if k_end > 20:                                  # 收起的记录最多 20 条（以前整张卡片最多 20 条）
                old_n += 1
                continue
        now_it = it.get("status") == "placed" and it.get("now")
        can = (it.get("status") in MO.ACTIVE and it.get("kind") in MO.ORDER_KINDS and not it.get("cancel_req")
               and not (now_it and MO.now_cancel_why(it, now)))   # 盘中的单还挂在交易所：页面上撤不了；15:30 失效的卖出能撤回（G16）
        btn = (_cbtn(it, 2 if now_it else (1 if it.get("status") == "placed" else 0)) if can else _unbtn(it))
        rows.append((it["id"], f"<div class='li'><div class='grow'><b>{_what(it)}</b> <span class='chip'>"
                    f"{escape(MO.fix_status_text(it, items, book, tag) or MO.status_text(it, now))}{'（撤回中）' if it.get('cancel_req') else escape(tlive['itxt'].get(it.get('id')) or sp['itxt'].get(it.get('id'), ''))}</span>"   # 盘中没下成 → 开盘（G18）
                    f"<div class='muted small'>{escape(str(it.get('at', ''))[5:16].replace('T', ' '))}"
                    f"{(' · ' + escape(MO.msg_text(it, now))) if it.get('msg') else ''}</div></div>{btn}</div>"))
    orows, ometa = _order_rows(book, now, paper, waiting, tlive, tag)   # 执行器的单（还挂着的给「撤单」；API / Mac 故障时照它在立花网站下）
    bl = man.get("blocks") or {}
    bhtml, bn = _blocks_card(book, tag, bl, _tlabel, now=now) if bl else ("", 0)
    H.append(PANE + "trade")                                # 今天要成交的单（+「另有 …」）/ 最下面收起的「已结束 / 不是今天的」（2026-10-16）
    H.extend(_trade_sections(sp, orows, rows, ometa, now, paper, bool(halt), bhtml, bn, old_n))
    H.append(PANE + "more")
    if halt:
        hw = sorted((x for x in [it for it in (man.get("items") or {}).values() if it.get("status") == "pending"] + list(waiting)
                     if x.get("kind") in MO.ORDER_KINDS and x.get("id") not in dropped), key=lambda x: str(x.get("at") or ""))
        hc = MO.halt_core((man.get("items") or {}).values(), waiting, dropped)
        H.append(f"<section class='card warn' id='halt'><h2 class='neg'>HALT 生效中</h2><div>{escape(NM.annotate(halt))}</div>"
                 + (f"<div class='neg small'>等着的手动买卖指令 {len(hw)} 条（最早写于 {escape(MO.mmdd(hw[0].get('at')))}）：解除后照原样执行；"
                    "不想做了先在「交易」撤回</div>" if hw else "")                  # 2026-10-13 resume-other-3
                 + (f"<div class='neg small'>HALT 期间改的闲置资金比例 / 固定口数 {len(hc)} 条：{escape(MO.halt_core_line(hc))}"
                    f"→ 解除后照它买卖 ETF（{escape(MO.HALT_CORE_AFTER)}）；不想这样先在「闲置资金」改回</div>" if hc else "")   # 2026-10-14：读到就生效，以前 HALT 卡片不列
                 + "<div class='muted small'>不下任何单、持仓不动。恢复只在 Mac 上：在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」。</div></section>")
    else:
        H.append("<section class='card' id='halt'><h2>紧急停止</h2><div class='muted small'>全部账本（模拟和立花）从下一次运行起不下单、持仓不动；"
                 "已经发到交易所的单不会被撤（要撤：「交易」→「今天要成交的单」的「撤单」，或立花网站 / 手机网站）。这里只能停、不能恢复。</div>"
                 "<div class='act'><button class='btn danger' data-act='halt'>停止下单（HALT）</button></div></section>")
    if not remote:
        H.append(_phone_card(phone or {}))
        H.append("<footer>账本与日志的完整页面：数据目录 out/page_" + escape(tag) + ".html（每天早上自动打开）。非投资建议。</footer>")
    elif (device or {}).get("kind") == "ts":                                # 按 Tailscale 账户登录（不用配对）
        pd = device.get("paired")
        H.append(f"<footer><div>已用 Tailscale 账户登录（{escape(str(device.get('login') or '—'))}；不用配对）。非投资建议。</div>"
                 "<div class='muted small'>只认这台 Mac 登录的 Tailscale 账户。要改成只用配对：在 Mac 的 Claude 对话里说「手机只用配对」。</div>"
                 + (f"<div class='muted small'>这台设备以前也配对过（{escape(str(pd))}）：不用了可以取消。</div>"
                    "<div class='act'><button class='btn sm' data-act='unpair'>取消这台设备的配对</button></div>" if pd else "")
                 + "</footer>")
    else:
        dv = device or {}
        H.append(f"<footer><div>这台设备：{escape(str(dv.get('name') or '手机'))}（配对 {escape(str(dv.get('created') or '')[:10])}）。"
                 "非投资建议。</div><div class='act'><button class='btn sm' data-act='unpair'>退出这台设备</button></div></footer>")
    if remote:
        H.append(_notify_card())                             # 推送（网页 App）
    H.append(PANE + "news")
    H.append(_msg_seg(now))                                  # 通知记录 / 经济威胁 两段
    H.append("<div class='mseg' data-s='news'>" + _news_card(now) + "</div>")
    H.append("<div class='mseg' data-s='log' hidden>" + _notify_log_card(now) + "</div>")
    H.append(PANE + "")                                      # 分组结束
    badges = _badges(book, pst, sm, waiting, now, tag, tlive)   # 持仓的只数含今天已成交（2026-10-16）
    H.append("</main><nav class='tabbar' role='tablist' aria-label='分类'>"
             + "".join(f"<button type='button' role='tab' data-tabgo='{k}' aria-label='{escape(lab)}'"
                       + (" class='on' aria-selected='true'" if k == (tab if tab in TABS else "home") else "") + f"><b>{ic}</b>{escape(lab)}"
                       + (f"<i class='badge'>{badges[k]}</i>" if badges.get(k) else "") + "</button>"
                       for k, (ic, lab, _) in TABS.items())
             + "</nav><div id='toast' class='toast' role='status' hidden></div>")
    note = MO.sale_note(tag, now)
    ests = {}                                               # 拿着的票卖出全部的预计收益（按账本里的最近收盘；页面取到现价后换成现价的）
    ytdg = MO.ytd_gain(book, now.date())                 # T7：卖出的预计代扣按今年已实现的损益通算
    for t in list(pst.get("pos") or {}) + [t for t, u in (pj.get("core_units") or {}).items() if int(u or 0) > 0]:
        if t in hnb:                                        # 今天有成交的：成本 / 股数在对账之后才对（不给预计）
            continue
        e = MO.sell_estimate(book, t, sm=sm)
        if e:
            ests[t] = {**e, "lines": MO.est_lines(e, note, ytdg)}
    u100s = MO.core_u100s(book)[0]                          # 规则目标（比例 100%）；执行器还没算过 → 估算（比例还是 100% 时）
    fx_fill = MO.corefix_fill(now, book, tag)
    cfg = {"auth": {"h": "X-Qbreak-Csrf" if remote else "X-Qbreak-Token", "v": tok}, "book": tag, "paper": paper, "remote": remote,
           "real": real,                                                                   # 真钱（立花本番）：确认框写明
           "sq_max": SG_MAX,                                                               # 建议的股票的现价一次最多取几只（quotes.js）
           "when": when, "eq": eq or 0, "cap": cap, "lot": MO.LOT, "live": MO.timing(now)[0] == "now",   # 盘中：现价每 1 分钟刷新
           "room": bool(rm),                                                               # 有「今天还能买几次」的卡片 → room.js 定时刷新（D6）
           "intra": True, "intra_live": bool((iv or {}).get("live")),                      # 盘中观测：intraday.js 交易时段每 1 分钟、其他 10 分钟刷新
           "cores": {t: {"cur": int((pj.get("core_units") or {}).get(t, 0)), "u100": int(u100s.get(t, 0)),   # 含今天已成交（2026-10-16）
                         "lot": MO.core_lot(book, t)}                                            # 调一只核心 ETF 时别的跟着变多少
                     for t in dict.fromkeys(list(u100s) + [t for t, u in (pj.get("core_units") or {}).items() if int(u) > 0])
                     if t not in bfix},                                                  # 固定口数的不跟比例（2026-10-13）
           "kp": {"label": KL.PLAIN, "align": KL.ALIGN_PLAIN, "chan": KL.CHAN_PLAIN},     # K 线的通俗说法（qbreak/kline.py）
           "fund": MO.fund_holdings(book, tag, now=now),                                  # 收盘后 / 周末：今天有成交的也能拿来凑（对账之后执行）
           "when_all": MO.allin_when(now, book, tag),                                     # 「全部换成这只」整批什么时候做
           "when_fix": fx_fill["text"], "fix_now": fx_fill["intraday"],                   # 固定口数什么时候下单 / 盘中按现价（D1；与执行器同一个时段口径）
           "halt_allin": MO.allin_halt_note(book),                                         # HALT 确认框：同批卖单已在交易所 → X 不会买
           "block_days": MO.BLOCK_DEFAULT,                                                # 卖出后不自动买回的天数（默认）
           "alloc": {"names": {r.get("ticker"): _nm(r.get("ticker"), r.get("name"))      # 别名（旧页面脚本用）；新的看 CFG.names
                               for r in ((sm.get("holding_view") or {}).get("holdings") or []) + ((sm.get("holding_view") or {}).get("core") or [])
                               if r.get("ticker")},
                     "colors": list(ALLOC_COLORS)},
           "names": _page_names(book, waiting, sm, man),                                  # 这一页上出现的票 → 名字（core.js lab / nameify；2026-10-15）                                       # 买入框里「现在 / 买入后」的占比条（与持仓页同色）                                           # 买入钱不够 → 从持仓平摊凑（预览；提交时同一个算法再算）
           "est": ests, "fee": [[c if c != float("inf") else 1e18, f] for c, f in FEE_TIERS],
           "st": status_json(tag)[1], "v": ASSET_V,
           "gen": int(dt.datetime.now().timestamp() * 1000)}                                    # 页面生成时刻（离线时显示「几分钟前的数据」）                                                         # 〔77〕C UX-16：还在处理的指令 → 每 10 秒问一次   # 卖出的预计收益（按最近收盘；现价来了用现价的）
    cfg_json = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    pre = "".join(f"<link rel='modulepreload' href='/static/{m}.js?v={ASSET_V}'>" for m in JS_MODULES)   # 模块一起取（不用一层层等 import）；没载入成 → boot.js 确认这些都拿得到了再重新载入（2026-10-15）
    return _head("qbreak 操作面板") + "<body><div id='pbar' role='progressbar' aria-label='加载中'></div>" + _panes(H, tab) + _dialogs(paper, cap) + (f"<script type='application/json' id='qb-cfg'>{cfg_json}</script>"
              f"<script>{BOOT_JS}</script>"                                 # 普通脚本、写在页面里、先跑：模块 / 样式没载入成（网络 / 版本）→ 页面上说、自动重新载入
              + pre + f"<script type='module' src='/static/main.js?v={ASSET_V}'></script></body></html>")


def pair_page(code: str = "") -> str:
    """手机端口上还没配对的设备看到的页面：只有输入配对码的框，没有任何账本数据。"""
    c = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())[:PP.CODE_LEN]
    c = PP.fmt_code(c) if len(c) == PP.CODE_LEN else c
    return (_head("qbreak 配对") + "<body><main><section class='card' style='margin-top:24px'><h1>qbreak 手机配对</h1>"
            "<p>这台设备还没配对。在 <b>Mac</b> 的操作面板（http://127.0.0.1:8765/ 的「手机」）点「生成配对码」，"
            "把 Mac 屏幕上的 8 位配对码输进来（或用相机扫 Mac 屏幕上的二维码）。</p>"
            "<label class='muted' for='code'>配对码</label>"
            f"<input type='text' id='code' value='{escape(c)}' autocomplete='one-time-code' autocapitalize='characters' autocorrect='off' "
            "spellcheck='false' maxlength='9' placeholder='XXXX-XXXX'>"
            "<label class='muted' for='name'>这台设备的名字（可不填）</label>"
            "<input type='text' id='name' maxlength='20' placeholder='例：iPhone'>"
            "<div class='row'><button class='btn primary' id='go'>配对</button></div>"
            "<p class='muted small'>配对码 10 分钟内有效、只能用一次、输错 5 次作废。配对之后这台设备 180 天内不用再配对；"
            "在 Mac 的面板上随时可以取消。</p>"
            "<p class='muted small'>用和 Mac 同一个 Tailscale 账户登录的手机通常不用配对（Mac 上打开了「按 Tailscale 账户登录」时）："
            "还是看到这一页 → 确认手机的 Tailscale App 登录的是同一个账户，或在 Mac 上运行 bash scripts/liveu.sh phone status 看一下。</p>"
            "</section></main><div id='toast' class='toast' role='status' hidden></div>"
            f"<script type='module' src='/static/pair.js?v={ASSET_V}'></script></body></html>")


# ───────────────────────── 写指令 ─────────────────────────
def submit_flow(tag: str, body: dict, now: dt.datetime | None = None) -> tuple[bool, str, dict | None]:
    """〔77〕C UX-14：面板登记入金（+）/ 出金（−）。与 liveu.sh flow 同一个函数（live_unified.register_flow），拿账本的运行锁
    （执行器在跑 → 不等，请稍后再试）。只影响收益的显示与「现金突然变化」的提醒，不下单、不改仓位。模拟账户不登记。"""
    from .live_unified import ExecutorError, RunLock, register_flow
    if tag.startswith("paper"):
        return False, "模拟账户不用登记入出金（本金按 sim.json）", None
    try:
        jpy = float(str(body.get("jpy") or "").replace(",", "").replace("¥", "").strip())
    except ValueError:
        return False, "金额读不出来：入金写正数、出金写负数（例 300000 / -300000）", None
    if not (1 <= abs(jpy) <= 1e10):
        return False, "金额要 ≥ 1 円（入金写正数、出金写负数）", None
    day = str(body.get("date") or "").strip() or None
    note = str(body.get("note") or "")[:120]
    bp = paths.state_dir() / f"live_unified_{tag}.json"
    try:
        lock = RunLock(bp.with_suffix(".lock"), wait_s=0).acquire()
    except ExecutorError:
        return False, "执行器正在运行：等它跑完（通常几分钟）再登记", None
    reserve = bool(body.get("reserve"))
    if reserve and jpy > 0:
        return False, "预留只用于出金（写负数）：入金不用预留", None
    try:
        rec = register_flow(bp, jpy, note, day, reserve=reserve)
    except ValueError as e:
        return False, f"没登记：{e}", None
    finally:
        lock.release()
    log.info("面板登记%s %+.0f 円（%s）", "入金" if jpy > 0 else "出金", jpy, tag)
    if rec.get("reserve") and not rec.get("seen_after"):
        return True, (f"已登记出金 {jpy:+,.0f} 円（{rec['date']}）并预留：到账前的决策按扣掉它算（个股仓位变小、闲置资金 ETF 不买回；"
                      "现金不够照规则先卖核心 ETF）；到账后自动解除"), {"id": "flow", "kind": "flow"}
    return True, (f"已登记{'入金' if jpy > 0 else '出金'} {jpy:+,.0f} 円（{rec['date']}）：只影响收益的计算与提醒，不下单"
                  + ("；已经对上之前的现金变化" if rec.get("seen_after") else "；到账后（下一次早上核对）自动对上")), {"id": "flow", "kind": "flow"}


def status_json(tag: str) -> tuple[int, dict]:
    """〔77〕C UX-16：页面要不要刷新（只读）→ {sig, pending, busy, v, boot}。页面的连接检查也用它（2026-10-15：页面开着就每 10〜30 秒问一次，
    切回来 / 联网时马上问；连不上 → 页面顶上「连不上 Mac（N 秒后重试）」，不再卡在刷新里）。sig = 手动指令的状态 + 执行器这次运行 + 当前决策的单的状态
    + 「交易」的数字 的摘要；页面拿着加载时的 sig，每 10 秒问一次，变了就刷新。pending = 「交易」标签的数字（_trade_live：还会做事的单与指令，
    2026-10-15）；busy = 一会儿就会变的（盘中 / 开盘前马上处理的指令、执行器正在跑、撤单 / 撤回在处理；0 → 页面每 30 秒才问一次；
    等明早决策的固定口数不算，2026-10-15）。sig 变了：busy 或 pending 前后有一个 > 0 → 刷新（对话框开着 / 正在输入时等关掉；晚上写的卖出
    07:40 下了单、昨天的单早上对账结束都在这里 —— 2026-10-15 复核），都是 0 → 等切回来再刷新（conn.js）。
    算不成（账本里有读不了的东西）→ 照样 200（ok、sig 固定、数字 0、带 err）：页面的连接检查只看 Mac 连不连得上，
    不能因为账本里一个数显示「连不上 Mac」、页面也不能因为它打不开（2026-10-15 复核）。"""
    try:
        return _status_json(tag)
    except Exception as e:                                 # noqa: BLE001
        log.warning("/api/status 没算成（%s：%s）：照样回 200（连接检查不受影响）", type(e).__name__, e)
        return 200, {"ok": True, "sig": "err", "pending": 0, "busy": 0, "v": ASSET_V, "boot": BOOT_ID, "err": type(e).__name__}


def _status_json(tag: str) -> tuple[int, dict]:
    import hashlib
    from . import run_status as RS
    book = read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {}
    man = book.get("manual") or {}
    items = sorted(((str(k), str(v.get("status")), str(v.get("msg") or "")[:60], bool(v.get("cancel_req")))
                    for k, v in (man.get("items") or {}).items()), key=lambda x: x[0])
    wrecs = MO.unseen(tag, book)
    waiting = sorted(str(r.get("id")) for r in wrecs)
    live = _trade_live(book, wrecs, now_jst(), tag)
    d = (book.get("state") or {}).get("last_date")
    orders = sorted((str(o.get("cid")), str(o.get("status")), int(o.get("filled_qty") or 0))
                    for o in book.get("orders") or [] if o.get("decided_on") == d)
    rec = RS.read(tag) or {}
    snap = read_json(paths.out_dir() / f"broker_snapshot_{tag}.json", {}) or {}
    raw = json.dumps([items, waiting, orders, rec.get("at"), rec.get("ok"), snap.get("at"), live["n"]], ensure_ascii=False, default=str)
    return 200, {"ok": True, "sig": hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16], "pending": live["n"], "busy": live["busy"],
                 "v": ASSET_V, "boot": BOOT_ID}                # 页面的连接检查（conn.js）：v 变了 = 面板换了新代码 → 空闲时重新载入


def _after_tax_stat(m: dict, sy, cls) -> str:
    """总览「损益」的第三格：税后累计损益（估算；tax_ytd.after_tax）。2026-10-11 用户「总览里要加上税后的盈利」。"""
    a = m.get("after_tax") or {}
    if "after" not in a:
        return ""
    inv = float(m.get("inv") or 0)
    pct = f"{a['after'] / inv * 100:+.2f}%" if inv else ""
    ex = float(a.get("extra") or 0)
    return (f"<div><div class='muted'>税后累计损益（估算）</div><div class='big {cls(a['after'])}'>{sy(a['after'])}</div>"
            f"<div class='muted small'>{pct} · 已代扣约 ¥{float(a.get('paid') or 0):,.0f}"
            + (f" · 现在全部卖出还要扣约 ¥{ex:,.0f}" if ex > 0 else f" · 现在全部卖出约退还 ¥{-ex:,.0f}" if ex < 0 else "")
            + ("（" + escape(NM.labels(a["incomplete"])) + " 的成本对不上，没算进去）" if a.get("incomplete") else "") + "</div></div>")


def _money_card(tag: str, book: dict, now: dt.datetime, pj: dict | None = None) -> str:
    """〔77〕C UX-10 / T7 / UX-09 / UX-14：当日 / 累计损益、迷你权益曲线、年内已实现与预计代扣、最近成交、日志最新一节；实盘账本加
    入出金登记。Mac 与手机同一个，可折叠。账本没有 → ""。只展示（入出金只影响收益的计算）。"""
    from . import money_view as MV
    try:
        m = MV.summary(tag, book, today=now.date().isoformat())
    except Exception as e:                                # noqa: BLE001  展示用
        log.warning("面板的损益卡片没算成：%s", e)
        return ""
    if not m:
        return ""

    def sy(v) -> str:
        return ("+" if v > 0 else "−" if v < 0 else "") + f"¥{abs(float(v)):,.0f}"

    def cls(v) -> str:
        return "up" if v > 0 else "down" if v < 0 else ""          # 涨红跌绿
    y = m.get("ytd") or {}
    H = ["<section class='card' id='money'><h2>损益</h2>"
         f"<div class='stats'><div><div class='muted'>当日损益</div><div class='big {cls(m['day'])}'>{sy(m['day'])}</div>"
         f"<div class='muted small'>{m['day_pct']:+.2f}%</div></div>"
         f"<div><div class='muted'>累计损益</div><div class='big {cls(m['tot'])}'>{sy(m['tot'])}</div>"
         f"<div class='muted small'>{m['tot_pct']:+.2f}%（投入本金 {_yen(m['inv'])}）</div></div>"
         + _after_tax_stat(m, sy, cls) + "</div>"
         + MV.sparkline(m["spark"])]
    if pj and pj.get("has"):                                # 当日 / 累计是账本收盘的数：今天的成交对账之后才算进来（2026-10-16 复核：首页总权益含今天，这里没说）
        H.append(f"<div class='muted small'>{escape(LO.ledger_close_note(pj, (book or {}).get('state') or {}))}</div>")
    if pj and pj.get("has") and pj.get("realized") is not None:   # 今天已实现（预计；正式数在对账之后进年内已实现，2026-10-16）
        rz0 = float(pj["realized"])
        H.append(f"<div class='small'>{escape(pj.get('day_word') or '今天')}已实现（预计，{escape(str(pj.get('when_sp') or ''))}对账后正式记账）："
                 f"约 <b class='{cls(rz0)}'>{sy(rz0)}</b>" + ("（部分 ETF 成本对不上，没算）" if pj.get("realized_partial") else "") + "</div>")
    if y:
        g, w = float(y.get("gain") or 0), float(y.get("withheld") or 0)
        H.append(f"<div class='small'>{y.get('year')} 年已实现 <b class='{cls(g)}'>{sy(g)}</b>（{int(y.get('n') or 0)} 笔：个股 {sy(y.get('stock_gain') or 0)}"
                 f" · 核心 ETF {sy(y.get('core_gain') or 0)}）· 预计已代扣 ¥{w:,.0f}"
                 + "</div>"
                 + (f"<div class='neg small'>★ 不完整：{escape(NM.labels(y['incomplete']))} 的买入记录对不上，它的卖出没算进去</div>"
                    if y.get("incomplete") else "")
                 + "<div class='muted small'>特定口座（源泉徴収あり）20.315% 的估算：每次卖出时按「今年 1/1 起已实现损益的合计」代扣或退还"
                   "（年内盈亏通算），到 12/31 为止、第二年从 0 重新算；按成交日分年。税后累计 = 累计损益 − 历年代扣 − 现在全部卖出还要扣的。"
                   "以立花的取引報告書 / 年間取引報告書为准</div>")
    rz = m.get("realized") or []
    if rz:
        H.append("<details class='hv'><summary class='muted'>最近的已实现损益（" + str(len(rz)) + " 笔）</summary><div class='list'>" + "".join(
            f"<div class='li'><div class='grow'>{escape(r['date'][5:].replace('-', '/'))} 卖 "
            + escape(NM.qty(r['ticker'], f"{int(r['shares']):,} {'口' if r['kind'] == 'core' else '股'}")) + f" @ ¥{float(r['px']):,.1f}</div><b class='{cls(r['pnl'])}'>{sy(r['pnl'])}</b></div>"
            for r in rz) + "</div></details>")
    fl = m.get("fills") or []
    tf = (pj or {}).get("fills") or [] if (pj or {}).get("has") else []   # 今天已成交、还没对账的（最前面；2026-10-16）
    tw = escape((pj or {}).get("day_word") or "今天") + "（对账前）"
    if fl or tf:
        H.append("<details class='hv'><summary class='muted'>最近成交（" + str(len(fl) + len(tf)) + " 笔）</summary><div class='list'>" + "".join(
            f"<div class='li'><div class='grow'>{tw} {'买' if f['side'] == 'BUY' else '卖'} "
            + escape(NM.qty(f['ticker'], f"{int(f['qty']):,} {'口' if f['kind'] == 'core' else '股'}")) + f"</div><span>¥{float(f['px']):,.1f}</span></div>"
            for f in tf) + "".join(
            f"<div class='li'><div class='grow'>{escape(str(f['date'])[5:].replace('-', '/'))} {'买' if f['side'] == 'BUY' else '卖'} "
            + escape(NM.qty(f['ticker'], f"{int(f['qty']):,} {'口' if f['kind'] == 'core' else '股'}")) + f"</div><span>¥{float(f['px']):,.1f}</span></div>"
            for f in fl) + "</div></details>")
    jl = m.get("journal")
    if jl:
        H.append(f"<details class='hv'><summary class='muted'>日志：{escape(NM.annotate(jl[0]))}</summary><ul class='small'>"   # 以前写的日志只有代码 → 显示时补名字（2026-10-15）
                 + "".join(f"<li>{escape(NM.annotate(x))}</li>" for x in jl[1][:30]) + "</ul></details>")
    if not tag.startswith("paper") and tag not in READONLY:
        H.append("<details class='hv' id='flow'><summary class='muted'>登记入金 / 出金</summary>"
                 "<div class='small muted'>入金写正数、出金写负数；只影响收益的计算与「现金突然变化」的提醒，不下单。</div>"
                 "<div class='act'><input id='flow-jpy' inputmode='numeric' placeholder='金额 例 300000 / -300000' aria-label='金额（円）'>"
                 f"<input id='flow-date' type='date' value='{now.date().isoformat()}' aria-label='日期'>"
                 "<input id='flow-note' maxlength='120' placeholder='备注（可不写）' aria-label='备注'>"
                 "<button class='btn primary' data-act='flow'>登记</button></div>"
                 "<label class='small'><input type='checkbox' id='flow-reserve'> 出金：到账前先留现金（预留）</label>"
                 "<div class='muted small'>预留 = 到账之前每次决策都当作这笔钱已经出金：个股仓位按扣掉它的权益算（变小）、闲置资金 ETF 不买回、"
                 "现金不够照规则先卖核心 ETF；到账（早上的现金核对对上）后自动解除，14 天还没对上也解除并提醒。"
                 "不预留的话，出金前卖出的钱会被规则当成闲置资金买回 ETF。</div></details>")
    from .live_unified import reserves
    rv = reserves(book)
    if rv:
        H.insert(1, "<div class='neg small'>★ 出金预留中：" + escape("、".join(f"{f.get('date')} {float(f['jpy']):+,.0f} 円" for f in rv))
                 + "（到账前的决策按扣掉它算；到账后自动解除）</div>")
    H.append("</section>")
    return "".join(H)


def _broker_card(tag: str, now: dt.datetime, pj: dict | None = None) -> str:
    """〔77〕C UX-07 / TA-06：「立花那边实际是什么」（数据目录 out/broker_snapshot_<账本>.json：执行器核对时 / liveu.sh broker 记的；
    面板本身不连立花）。持仓 vs 账本差异标红、买付可能額、今天的单在立花的成交、立花现价与时刻。模拟账户 / 没有快照 → 说明怎么刷新。"""
    from . import broker_snapshot as BS
    if tag.startswith("paper"):
        return ""
    s = BS.load(tag)
    how = "刷新：在 Mac 对话里说「看立花那边」（bash scripts/liveu.sh broker；只读）；装了立花本番后 11:35 / 15:45 自动刷新并通知"
    if not s:
        return (f"<section class='card' id='broker'><h2>立花那边</h2><div class='muted small'>还没有快照（执行器第一次核对之后才有）。"
                f"{escape(how)}</div></section>")
    cm = LO.broker_compare(s, pj)                           # 账本 + 快照之前已知的成交 vs 立花（liveu.sh broker 同一个判断；2026-10-16 复核）
    cmp_, seen, late, bad, soft = cm["rows"], cm["seen"], cm["late"], cm["bad"], cm["soft"]
    head, dw = cm["head"], cm["day_word"]
    sft = {r["ticker"] for r in soft}
    after = "快照之后" + ("今天" if dw == "今天" else f" {dw}") + "又成交了，下一次刷新才看得到"
    q = s.get("quotes") or {}
    rows = "".join(
        f"<div class='li'><div class='grow'><b>{escape(NM.label(r['ticker']))}</b> 立花 {int(r['broker']):,} / 账本 {int(r['ledger']):,}"
        + ((f" <span class='muted'>差 {int(r['diff']):+,}（{escape(head)}的预计说不准，对账之后再看）</span>" if r["ticker"] in sft
            else f" <b class='neg'>差 {int(r['diff']):+,}</b>"
            + (f" <span class='muted small'>（账本按{escape(head)}算）</span>" if r["ticker"] in seen else "")) if r.get("diff") else " ✓")
        + (f"<div class='muted small'>{escape(after)}</div>" if r["ticker"] in late else "")
        + (f"<div class='muted small'>立花现价 ¥{float(q[r['ticker']]):,.1f}（{escape(str(s.get('quotes_at') or '')[11:16])}）</div>"
           if r["ticker"] in q else "") + "</div></div>"
        for r in cmp_)
    shown = {r["ticker"] for r in cmp_}
    rows += "".join(f"<div class='li'><div class='grow'><b>{escape(NM.label(t))}</b> "
                    f"<span class='muted small'>{escape(after)}</span></div></div>"
                    for t in sorted(late - shown))            # 快照之后才买进的新票（账本、立花都还是 0：上面没有它那一行）
    fl = BS.fills_lines(s)
    fd = LO.snap_day(s)
    try:
        fdw = "今天" if fd == now.date().isoformat() else LO._hn_md(dt.date.fromisoformat(fd))
    except ValueError:
        fdw = "今天"
    flw = "今天的成交" if fdw == "今天" else f"{fdw}的单的成交"
    return (f"<section class='card{' warn' if bad else ''}' id='broker'><h2>立花那边（{escape(str(s.get('at') or '')[5:16])}，"
            f"{escape(str(s.get('source') or ''))}）" + (f"（账本{escape(head)}）" if seen else "") + "</h2>"
            f"<div>买付可能額 <b>{_yen(s.get('buying_power'))}</b></div>"
            + (f"<div class='neg small'>★ 账本和立花不一致 {len(bad)} 只：下一次早上的核对会停下 → Mac 对话里说「核对持仓」</div>" if bad else "")
            + (f"<div class='muted small'>{escape(head)}的预计和立花差 {len(soft)} 只（快照前后的成交说不准）："
               f"对账（先记{escape(dw)}的成交）之后再比</div>" if soft else "")
            + f"<div class='list'>{rows or '<div class=li>立花那边没有持仓</div>'}</div>"
            + (f"<div class='small'><b>{escape(flw)}</b>（{escape(str(s.get('fills_at') or '')[5:16])} 读的）</div><ul class='small'>"
               + "".join(f"<li>{escape(x[1:])}</li>" for x in fl) + "</ul>" if fl else "")   # 只去掉「・」（以前 x[2:] 连「买 / 卖」也切掉；2026-10-15）
            + f"<div class='muted small'>只读的快照，不是实时；正式记账在下一个交易日 07:40。{escape(how)}</div></section>")


def _notify_card() -> str:
    """手机（网页 App）：推送通知的开关。iPhone 要 iOS 16.4 以上、从「添加到主屏幕」的图标打开才能打开推送（Safari 的标签页里不行）。"""
    return ("<section class='card' id='notify'><h2>通知（推送）</h2>"
            "<div id='push-st' class='small'>检查中…</div>"
            "<div class='act'><button class='btn primary' data-act='push-on'>在这台设备打开推送</button>"
            "<button class='btn' data-act='push-test'>发一条测试</button><button class='btn' data-act='push-off'>关掉</button></div>"
            "<div class='muted small'>打开后：每个工作日 09:30 自检推一条（通过 / 休市 / 没通过；哪个工作日没收到 → Mac 多半关机 / 睡着 / 断网）、"
            "成交、闲置资金 ETF 的买入信号、HALT、手机连不上等通知会直接弹到这台设备（和邮件同一段文字）。"
            "iPhone：先在 Safari 里「共享 → 添加到主屏幕」，再从主屏幕的 qbreak 图标打开、点上面的按钮、允许通知（iOS 16.4 以上）。"
            "这台设备以后都用主屏幕的图标打开 —— 不要用 127.0.0.1 的地址（那是手机自己，打不开）。</div></section>")


def _gate_card(tag: str) -> str:
    """〔77〕C UX-15：上线准备（最近一次「能上实盘了吗」/ 前一晚预检的结果：数据目录 out/gate.json；只读）。门槛与准备逐项 ✓ / ✗。"""
    from . import live_gate as LG
    if tag in READONLY or tag.endswith("_demo"):
        return ""
    g = LG.load_saved()
    if not g:
        return ("<section class='card' id='gate'><h2>上线准备</h2><div class='muted small'>还没检查过：在 Mac 对话里问「能上实盘了吗」"
                "（bash scripts/liveu.sh gate；只读）</div></section>")
    its = [it for it in g.get("items") or [] if it.get("group") in ("门槛", "准备")]
    mark = {True: "✓", False: "✗", None: "—"}
    return (f"<section class='card' id='gate'><details{' open' if tag == 'tachibana' and not g.get('ok') else ''}>"
            f"<summary><b>上线准备</b> {'全部满足 ✓' if g.get('ok') else '还没全部满足'}"
            f" <span class='muted small'>（{escape(str(g.get('at') or ''))} 的检查）</span></summary><div class='list'>"
            + "".join(f"<div class='li'><div class='grow'><span class='{'neg' if it.get('ok') is False else ''}'>{mark.get(it.get('ok'), '—')}</span> "
                      f"<b>{escape(str(it.get('name')))}</b><div class='muted small'>{escape(str(it.get('text'))[:200])}</div></div></div>"
                      for it in its)
            + "</div><div class='muted small'>重新检查：在 Mac 对话里问「能上实盘了吗」（只读）</div></details></section>")


def _buy_warn0(sm: dict | None, t: str) -> list[str]:
    """建议的股票里这只的「会被执行器挡下」（决算前 / 新仓倍数 0 …）：从持仓凑钱买（全部换成 / 平摊）之前先拒（卖了却不买）。"""
    row = next((r for r in ((sm or {}).get("suggest") or {}).get("rows") or [] if r.get("ticker") == t), None)
    return [str(w) for w in ((row or {}).get("buy") or {}).get("warn") or []]


def _uncancel_warn0(allrec: dict, cid: str, sm: dict | None) -> str | None:
    """撤销撤回「从持仓凑钱的买入」（全部换成 / 平摊）：这只现在会被执行器挡（决算前 / 新仓倍数 0 …）→ 不给恢复（与提交时同一个检查；2026-10-14）。"""
    tg = allrec.get((allrec.get(cid) or {}).get("target")) or {}
    if tg.get("kind") != "buy" or tg.get("fund") not in ("all", "split"):
        return None
    warn0 = _buy_warn0(sm, str(tg.get("ticker") or ""))
    return ("这只现在会被执行器挡下（" + "；".join(_fill_mult_why(w) for w in warn0) + "）：等它解除再重新提交") if warn0 else None


def _close_of(book: dict | None, sm: dict | None, t: str) -> float | None:
    """这只票最近的收盘（建议的股票那一行 / 持仓的 last_close）：「全部换成」晚做时比较用。没有 → None。"""
    row = next((r for r in ((sm or {}).get("suggest") or {}).get("rows") or [] if r.get("ticker") == t), None) or {}
    for v in (row.get("close"), (row.get("buy") or {}).get("px"),
              ((((book or {}).get("state") or {}).get("pos") or {}).get(t) or {}).get("last_close")):
        try:
            if v and float(v) > 0:
                return round(float(v), 4)
        except (TypeError, ValueError):
            continue
    return None


FIX_CONFIRM_MSG = "还没写：固定口数 / 恢复按规则要先看「确认下单」框、点了「确认下单」才写（页面是旧的话：刷新页面后再点一次）"


def _fix_quotes(tag: str, tickers, now: dt.datetime, fetch=None, wait: float = 3.0) -> dict:
    """确认下单框估金额用的现价（Yahoo 1 分钟线，约晚 20 分钟；只估金额，不影响写什么）：先用现价接口的缓存（Mac 与手机共用）；
    没有的另开线程取、最多等 wait 秒（Yahoo 慢 / 取不到 → 按最近收盘估，不让确认框卡住；取回来的放进缓存，下一次用）。"""
    want = sorted(set(tickers))
    if not want:
        return {}
    ttl = 60 if MO.timing(now)[0] == "now" else 600
    out: dict = {}
    with _QUOTE_LOCK:
        for (tg, _k), (at, q) in list(_QUOTE_CACHE.items()):
            if tg == tag and time.monotonic() - at <= ttl:
                out.update({t: q[t] for t in want if t in (q or {}) and t not in out})
    miss = [t for t in want if t not in out]
    if not miss:
        return out
    box: dict = {}

    def run():
        f = fetch
        if f is None:
            from .data import intraday_quotes as f
        try:
            q = f(miss) or {}
        except Exception as e:                               # noqa: BLE001
            log.warning("现价取不到（确认框）：%s", e)
            q = {}
        box["q"] = q
        with _QUOTE_LOCK:
            _QUOTE_CACHE[(tag, ("fix",) + tuple(miss))] = (time.monotonic(), q) if q else (time.monotonic() - ttl + 10, q)
    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(wait)
    out.update(box.get("q") or {})
    return out


def _req_reply(ok: bool, msg: str, rec: dict | None) -> tuple[int, dict]:
    """/api/request 的回应（本机与手机共用）：要先确认（固定口数 / 恢复按规则：submit 回 need_confirm）→ 200 + ok:false + 确认框的内容，
    什么都没写（2026-10-15 复核：以前 409，每次「固定口数…」浏览器控制台都记一条资源载入错误，其实没出错）；
    旧页面（没有确认框的 JS）看 ok:false 照旧显示 msg（= 没写 + 刷新）。没带确认的请求照样什么都不写。"""
    msg = NM.annotate(msg)                                  # 兜底：别处来的说明（检查的理由…）里剩下的「7203.T」补名字（指令 id / cid / 命令行不动；2026-10-15）
    if not ok and isinstance(rec, dict) and rec.get("need_confirm"):
        return 200, {"ok": False, "need_confirm": True, "msg": msg, "confirm": rec.get("confirm")}
    return (200 if ok else 400), {"ok": ok, "msg": msg, "id": (rec or {}).get("id")}


def submit(body: dict, now: dt.datetime | None = None, source: str = "panel", fetch=None) -> tuple[bool, str, dict | None]:
    """页面的一次提交 → (成功?, 说明, 写进去的指令)。与 run.py manual 相同的检查。source：panel（Mac）/ phone（手机）。
    固定口数 / 恢复按规则（kind corefix；固定的 ETF 上点的卖出 / 减仓 / 调仓换算成的也算）：body 没带 confirm（= 确认框给的 token）或
    token 对不上（账本 / 时间段变了）→ 不写，回 (False, FIX_CONFIRM_MSG, {"need_confirm": True, "confirm": 确认框})（2026-10-15）。
    fetch：确认框估金额取现价用（测试换掉；默认 Yahoo）。"""
    tag = str(body.get("book") or "")
    if tag not in BOOKS:
        return False, "不认识的账本", None
    if tag in READONLY:
        return False, "dry-run 的账本只能看：面板不写指令", None
    if str(body.get("kind") or "") == "flow":
        return submit_flow(tag, body, now)
    if str(body.get("kind") or "") != "cancel":            # 模拟账户的执行器没装、立花装了：写了也没人执行（2026-10-14 G13；撤回照旧能写）
        why = MO.paper_refuse(tag)
        if why:
            return False, why, None
    book, sm = _load(tag)
    if str(body.get("kind") or "") == "unblock" and isinstance(body.get("tickers"), list) and body["tickers"]:   # 一次解除一批（「恢复按规则」）
        recs, skip, seen = [], [], set()                    # 「代码:设定 id」：页面看到之后设定换了 / 已经解除的跳过（2026-10-13）；全都不行才拒绝
        for x in body["tickers"][:20]:
            tk, _s, bid = str(x).partition(":")
            try:
                r = MO.normalize({"kind": "unblock", "ticker": tk, "source": source, **({"block_id": bid} if bid else {})})
            except ValueError as e:
                skip.append(str(e))
                continue
            if r["ticker"] in seen:
                continue
            seen.add(r["ticker"])
            w = MO.check(r, book, tag, sm=sm, now=now)
            if w:
                skip.append(w)
                continue
            recs.append(r)
        if not recs:
            return False, "没写：" + "；".join(skip or ["没有要解除的"]), None
        out = MO.append_many(tag, recs, clock=(lambda: now) if now else None)
        return True, (f"已写：恢复按规则 → 解除 {NM.labels([r['ticker'] for r in out])} 的不自动买回（不会买回，也不马上买；"
                      f"指令 {out[0]['id']} 等 {len(out)} 条" + (f"；没写：{'；'.join(skip)}" if skip else "") + f"）→ {MO.next_decision(now)}"), out[0]
    if str(body.get("kind") or "") in ("cancel", "uncancel"):   # 撤回 / 撤销撤回：与命令行同一个函数（同批指令一起；2026-10-13）
        fn = MO.cancel_request if body.get("kind") == "cancel" else MO.uncancel_request
        if body.get("kind") == "uncancel":
            man = (book or {}).get("manual") or {}
            why = _uncancel_warn0({**{x["id"]: x for x in MO.unseen(tag, book)}, **(man.get("items") or {})}, str(body.get("target") or ""), sm)
            if why:
                return False, f"撤销不了：{why}", None
        ok, msg, rec = fn(tag, book, str(body.get("target") or ""), now=now, source=source, sm=sm)
        return ok, msg + (f"（指令 {rec['id']}）" if ok and rec else ""), rec
    try:
        rec = MO.normalize({**body, "source": source})
        rec = MO.core_rec(rec, book, tag, now=now) or rec    # 持有的核心 ETF 的卖出 / 调仓 → 闲置资金比例（规则每天按它调核心）；固定口数的 → 改固定口数
    except ValueError as e:
        return False, f"没写：{e}", None
    gnotes: list = []
    if rec["kind"] == "cancel_order" and rec.get("grp"):  # 整组撤单（2026-10-16）：页面过期 → 去掉现在撤不了 / 已经在撤的同一组的单
        try:
            rec, gnotes = MO.group_prune(rec, book, now or now_jst(), tag.startswith("paper"), MO.unseen(tag, book))
        except ValueError as e:
            return False, str(e), None
    c0 = (MO.core_info(book, rec["ticker"], LO.held_now(book, tag, now=now))   # 现在的口数含今天已成交（与 core_rec 同一个数；2026-10-16 二次复核）
          if rec["kind"] == "core" and rec.get("ticker") else None)
    pct0 = MO.core_pct_now(tag, book)                      # 写之前的闲置资金比例（含还没读的指令；0 = 停买中）
    fund = body.get("fund") if rec["kind"] in ("buy", "adjust", "corefix") else None
    allp, going = None, None
    if rec["kind"] == "buy" and isinstance(fund, dict) and fund.get("mode") == "all":   # 其他全部卖出，只拿这只（2026-10-13）
        la = MO.live_allin(tag, book)
        if la:
            return False, f"没写：「全部换成 {NM.label(la[0]['ticker'])}」还在处理：同时只能有一个「全部换成」（要改就先撤回那条）", None
        allp = MO.fund_all(book, tag, rec["ticker"], now=now)
        if allp["blocked"]:
            return False, f"没写（其他全部卖出）：{allp['blocked']}", None
        warn0 = _buy_warn0(sm, rec["ticker"])
        if warn0:                                          # 执行器决策时会挡的（决算前 / 新仓倍数 0）：不让「全卖换这只」（否则卖光了却不买）
            return False, "没写（其他全部卖出）：这只现在会被执行器挡下（" + "；".join(_fill_mult_why(w) for w in warn0) + "）：等它解除再做", None
        going = {t for t, _c, _p in allp["sells"]}         # 名额按「卖完之后」算
        rec["allin_fill"] = MO.allin_fill(now or now_jst(), book, tag).isoformat()   # 预计哪天开盘做：晚了（HALT / 晚跑）执行时会说明（2026-10-13）
        xc = _close_of(book, sm, rec["ticker"])
        if xc:
            rec["x_close"] = xc
    elif rec["kind"] == "buy" and isinstance(fund, dict) and fund.get("mode") == "split":
        warn0 = _buy_warn0(sm, rec["ticker"])
        if warn0:                                          # 平摊凑钱也一样：会被挡的买入不写（否则凑钱的卖出卖了却不买；2026-10-13）
            return False, "没写（从持仓凑钱买）：这只现在会被执行器挡下（" + "；".join(_fill_mult_why(w) for w in warn0) + "）：等它解除再做", None
    why = MO.check(rec, book, tag, sm=sm, now=now, going=going)
    if why:
        return False, f"没写：{why}", None
    sells = []
    if isinstance(fund, dict) and fund.get("mode") == "split":   # 钱不够 → 从持仓平摊凑：个股写成调仓往下（先卖），核心 ETF 那份执行器按当时缺多少卖
        try:
            cost = float(fund.get("cost") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        plan = MO.fund_split(cost, MO.fund_holdings(book, tag, now=now), skip=rec["ticker"]) if cost > 0 else None
        for r in (plan or {}).get("rows") or []:
            if r["kind"] != "stock":
                continue
            sr = MO.normalize({"kind": "adjust", "ticker": r["t"], "unit": "shares", "value": r["after"],
                               "fund_for": rec["ticker"], "source": source, "dir": -1, "cur0": r.get("cur")})
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（凑钱要卖的 {NM.label(r['t'])}：{w}）", None
            sells.append((sr, r))
        if plan:
            rec["fund"] = "split"
    elif allp is not None:                                 # 其他全部卖出：个股 adjust → 0；固定口数取消；闲置资金比例 → 0%（卖出全部 + 停买）；最后买入
        for t, cur, _px in allp["sells"]:
            sr = MO.normalize({"kind": "sell", "ticker": t, "block_days": MO.BLOCK_DEFAULT, "fund_for": rec["ticker"], "batch": "all",
                               "source": source})       # 卖出全部 + 不自动买回（2026-10-13 用户；整批执行时才设，「交易」里可一次「恢复按规则」）
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（要卖的 {NM.label(t)}：{w}）", None
            sells.append((sr, {"t": t, "sell": cur, "kind": "stock"}))
        for t in allp["core_clear"]:
            sr = MO.normalize({"kind": "corefix", "ticker": t, "clear": True, "fund_for": rec["ticker"], "batch": "all", "source": source,
                               "prev_units": ((book.get("manual") or {}).get("core_fix") or {}).get(t)})
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（取消 {NM.label(t)} 的固定口数：{w}）", None
            sells.append((sr, {"t": t, "sell": 0, "kind": "corefix"}))
        if float(allp["core_pct"]) > 0:
            sr = MO.normalize({"kind": "core", "pct": 0, "fund_for": rec["ticker"], "batch": "all", "source": source, "prev_pct": allp["core_pct"]})
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（闲置资金比例 → 0%：{w}）", None
            sells.append((sr, {"t": "core", "sell": 0, "kind": "core"}))
        rec["fund"] = "all"
    if rec["kind"] == "corefix":                            # 固定口数 / 恢复按规则：先给「确认下单 / 取消下单」，点了「确认下单」（带 token）才写
        n0 = now or now_jst()                               # （2026-10-15 用户：盘中固定口数点「确定」不要直接下单；旧页面 / 缓存的页面也绕不过去）
        ss = [(r["t"], int(r["sell"]), float(r.get("yen") or 0) / max(1, int(r["sell"]))) for _s, r in sells if r.get("kind") == "stock"]
        halt = paths.halt_file().exists()
        pv = MO.corefix_preview(book, tag, rec, n0, sm=sm, stock_sells=ss, halt=halt)
        got = str(body.get("confirm") or "")
        if got != pv["token"]:
            q = _fix_quotes(tag, [rec["ticker"]] + [m["t"] for m in pv["plan"]["moves"]], n0, fetch)
            if q:
                pv = MO.corefix_preview(book, tag, rec, n0, sm=sm, stock_sells=ss, quotes=q, halt=halt)
            return False, FIX_CONFIRM_MSG, {"need_confirm": True, "confirm": {
                "title": pv["title"], "text": pv["text"], "token": pv["token"], "danger": pv["danger"], "changed": bool(got)}}
    clock = (lambda: now) if now else None
    if rec["kind"] == "adjust" and not rec.get("fund_for"):   # 写入时预览的方向（+1 加 / −1 减）：执行时换算方向相反 → 不执行（2026-10-13）
        a0 = MO.adjust_plan(rec, LO.held_now(book, tag, now=now)["state"], MO.MANUAL_CAP_PCT)   # 含今天已成交 = 对账之后执行时的持仓（2026-10-16）
        if a0["delta"]:
            rec.update(dir=1 if a0["delta"] > 0 else -1, cur0=int(a0["cur"]))
    if allp is not None:                                   # 全部换成：买入 + 同批一次写进文件（执行器不会只读到一半）
        rec = MO.append_many(tag, [rec] + [sr for sr, _r in sells], clock=clock)[0]
    elif sells:                                            # 平摊凑钱：凑钱的卖在前、买入在后，一次写进文件（同一时刻 = 同一组；2026-10-13）
        rec = MO.append_many(tag, [sr for sr, _r in sells] + [rec], clock=clock)[-1]
    else:
        rec = MO.append(tag, rec, clock=clock)
    if rec["kind"] == "unblock":                           # 解除不是单：不会买回、也不马上买，下一次决策起才不挡（2026-10-13）
        return True, f"已写：解除 {NM.label(rec['ticker'])} 的不自动买回（不会买回，也不马上买；指令 {rec['id']}）→ {MO.next_decision(now)}", rec
    when = MO.when_for(now or now_jst(), book,              # 马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘 / 早上的运行没完成（G9）
                       rec.get("ticker") if rec["kind"] in MO.ORDER_KINDS else None)   # 这只今天已经有执行器还活着的单 → 下一个交易日开盘（D4）
    k, t = rec["kind"], rec.get("ticker")
    tl = NM.label(t) if t else ""                           # 说明里的票都写「代码 名字」（2026-10-15 用户：只写代码不知道是哪只；指令 id / cid 原样）
    msg = {"sell": f"已写：卖出 {tl} 全部 → {when}卖出",
           "trim": f"已写：{tl} 减到约 {rec.get('pct', 0):g}% → {when}卖出",
           "core": f"已写：闲置资金比例 {rec.get('pct', 0):g}% → 核心 ETF {when}照新比例调",
           "unblock": f"已写：解除 {tl} 的不自动买回",
           "cancel_order": f"已写：撤单 {tl}（{rec.get('cid')}）→ 执行器马上撤（已经成交的部分撤不了）"}.get(k)
    if k == "cancel_order" and rec.get("grp"):              # 整组撤单（2026-10-16）
        gw_ = []
        for c in rec["grp"]:
            mg = MO._CID.match(str(c))
            if mg:
                gw_.append(("买" if mg.group(2) == "BUY" else "卖") + " " + NM.label(mg.group(3)))
        msg = (f"已写：整组撤单 {len(rec['grp']) + 1} 笔（{tl}（{rec.get('cid')}）+ 同一组的 " + "、".join(gw_)
               + "）→ 执行器马上撤：先撤买单，确认没成交再撤卖单（已经成交的部分撤不了）")
        if gnotes:
            msg += "（" + "；".join(gnotes) + "：没写进去）"
    if k == "adjust":
        st = LO.held_now(book, tag, now=now)["state"]      # 含今天已成交（与写入的方向同一个数；2026-10-16）
        a = MO.adjust_plan(rec, st, MO.MANUAL_CAP_PCT)
        if a["delta"] > 0:
            msg = (f"已写：{tl} 加 {a['delta']:,} 股（→ {a['target']:,} 股" + ("，截到总权益" if a["capped"] else "")
                   + f"）→ {when}买入")
        else:
            msg = f"已写：{tl} 卖 {-a['delta']:,} 股（→ {a['target']:,} 股）→ {when}卖出"
    fill = MO.corefix_fill(now or now_jst(), book, tag) if k == "corefix" else None
    if k == "corefix":                                                             # 2026-10-12 再发防止：这一种以前没有说明 → msg None → 拼接崩溃 → 手机 502
        msg = (f"已写：{tl} 恢复按规则 → " + MO.corefix_clear_text(book, t, tag, now or now_jst()) if rec.get("clear") else   # 2026-10-13：会怎样
               f"已写：{tl} 固定 {int(rec.get('units') or 0):,} 口 → {fill['text']}")   # D1（2026-10-15）：盘中 / 开盘前写的也马上按现价下，与卖出 / 买入同一个时段口径
        if rec.get("from_kind"):                                                   # 固定口数的 ETF 上点的卖出 / 减仓 / 调仓（2026-10-13）
            msg += "（这只是手动固定的：只改这只 ETF 的固定口数，别的 ETF 与闲置资金比例不变）"
    if msg is None:                                                                # 新加的指令种类忘了写说明：也给一句（不让拼接崩溃）
        msg = f"已写：{MO.LABEL.get(k, k)}" + (f" {tl}" if t else "") + f" → {when}处理"
    if k == "core" and not t and pct0 <= 0 < float(rec["pct"]):                    # 停买后确认买入
        p1 = float(rec["pct"])
        ri = MO.resume_info(book, tag, now or now_jst(), pct=p1)   # 规则不拿 / 今天已经有单 → 不是马上（2026-10-13）
        full = p1 >= 100 - 1e-9                                    # 「恢复成 N%」只买规则目标额的 N%：不说照规则（2026-10-14）
        msg = (f"已写：{'确认买入' if full else f'恢复成 {p1:g}%'}（闲置资金比例 0% → {rec['pct']:g}%）→ "
               + ((f"{when}照规则买入核心 ETF" if full else f"{when}按规则目标额的 {p1:g}% 买入核心 ETF，之后每天按 {p1:g}% 调")
                  if not ri["none"] and not ri["late"] else ri["text"]))
    if k == "core" and t and int(rec.get("target") or 0) <= 0:                     # 核心 ETF 卖出全部：之后停买
        fx = MO.core_effects(book, 0.0, skip=t, tag=tag)
        msg = (f"已写：卖出全部 {tl} → {when}卖出；之后停买闲置资金 ETF（出现买入信号会提醒，你确认才买）"
               + ("；同一比例也用在：" + "、".join(NM.qty(x, f"{a_:,} → {b_:,} 口") for x, a_, b_ in fx) if fx else ""))
    elif c0:
        n = int(rec["target"]) - c0["cur"]
        fx = MO.core_effects(book, rec["pct"], skip=t, tag=tag)  # 规则同时拿两只以上核心 ETF 时：同一比例别的也跟着变
        msg = (f"已写：{'卖出全部 ' + tl if int(rec['target']) <= 0 else tl + (' 加 ' if n > 0 else ' 卖 ') + f'{abs(n):,} 口'}"
               f"（闲置资金比例 {c0['pct']:g}% → {rec['pct']:g}%）→ {when}{'买入' if n > 0 else '卖出'}"
               + ("；同一比例也用在：" + "、".join(NM.qty(x, f"{a_:,} → {b_:,} 口") for x, a_, b_ in fx) if fx else ""))
    if k == "buy":
        row = next((r for r in (sm.get("suggest") or {}).get("rows") or [] if r.get("ticker") == t), None)
        est = MO.fmt_target(rec)
        if row and rec.get("unit") == "rule":
            est = f"约 {int((row.get('buy') or {}).get('rule_shares') or 0):,} 股"
        msg = (f"已写：买入 {tl}（{est}）→ {when}买入"
               + ("" if row and row.get("signal") else "；★ 还没有买入信号：是你自己的决定"))
    if rec.get("fund") == "all":
        fx = MO.core_effects(book, 0.0, keep_fixed=True)    # 固定口数同批取消 → 也按 0% 卖
        etf = ("、".join(NM.qty(x, f"{a_:,} → 0 口") for x, a_, _b in fx) or "、".join(NM.qty(x, f"{u:,} → 0 口") for x, u in allp["cores"]))
        held = [r for _s, r in sells if r["kind"] == "stock"]
        ct_ = MO.core_tickers(book)
        going_ = "、".join(f"{NM.label(x)}（{why_}）" for x, why_ in allp.get("skip") or [] if x not in ct_)   # 已有卖出全部的指令 / 已在卖出全部：不另外写
        gone_c = "、".join(f"{NM.label(x)}（{why_}）" for x, why_ in allp.get("skip") or [] if x in ct_)     # 今天已卖光的核心 ETF（2026-10-16）
        head = "执行时拿着的 " + tl + " 以外的个股和 ETF 全部卖出（包括写指令之后规则 / 别的指令买进的）；"
        bt_ = ""                                            # 今天买进的个股（对账前，账本里还没有）：执行时一起卖（2026-10-16 复核：以前挡住不让写）
        if allp.get("bought"):
            bt_ = f"{allp.get('day_word') or '今天'}买进的：{NM.labels(allp['bought'])}（对账之后算持仓，执行时一起卖出）"
        if held:                                            # 2026-10-15 复核：别的个股都已经有卖出指令时以前写「现在拿着的：（没有别的个股）」
            head += ("现在拿着的：" + "、".join(NM.qty(r["t"], f"{r['sell']:,} 股") for r in held)
                     + f"（之后 {MO.BLOCK_DEFAULT} 个交易日规则不自动买回；「交易」里可一次「恢复按规则」）"
                     + (f"；已经在卖、不另外写的：{going_}" if going_ else "") + ("；" + bt_ if bt_ else ""))
        elif going_:
            head += f"别的个股都已经在卖、不另外写：{going_}" + ("；" + bt_ if bt_ else "")
        else:
            head += bt_ or "现在没有别的个股"
        parts = [head] + ([f"不用再卖的 ETF：{gone_c}"] if gone_c else [])
        fixed_ = [r["t"] for _s, r in sells if r["kind"] == "corefix"]
        if fixed_:                                          # ETF 的口数变化只在比例那一句写一次（以前两处各写一遍，没固定的 1545 也写在「取消固定口数」里）
            parts.append("取消固定口数：" + NM.labels(fixed_) + "（之后按比例 0% 卖出）")
        if any(r["kind"] == "core" for _s, r in sells):
            parts.append(f"闲置资金比例 {allp['core_pct']:g}% → 0%（" + (etf + "；" if etf else "")
                         + "之后停买闲置资金 ETF，出现买入信号只提醒、你点「确认买入」才恢复）")
        elif etf:
            parts.append(f"闲置资金比例已经是 0%：{etf}（照旧卖出）")
        if allp.get("also"):
            parts.append("另外规则 / 别的指令开盘还会买：" + NM.labels(allp["also"]) + "（买进了的，执行时一起卖出）")
        wa = MO.allin_when(now or now_jst(), book, tag)
        msg = (f"已写：全部换成 {tl} → {wa}整批先卖后买（那次决策先过闸门；股数由执行器按全卖之后的钱定）；" + "；".join(parts)
               + "；全卖也不够 1 个单元就不买、留现金；决策时买入被挡 → 整批不做、什么都不动；开盘跳空 / 没成交则其他已卖、留现金、不自动重买"
               "；规则对别的票仍可能用现金开新仓")
    elif sells:
        msg += ("；凑钱先卖：" + "、".join(NM.qty(r['t'], f"{r['sell']:,} 股") for _s, r in sells)
                + (("（其余由没固定的核心 ETF 补：现金不够时执行器盘中先卖它们补足，这几笔卖出先成交再买）" if fill["intraday"] else
                     "（其余由别的核心 ETF 照规则减少：现金不够时执行器在那次决策里先卖它们补足，再平衡带以内也卖）") if k == "corefix"
                   else "（核心 ETF 那份执行器按当时还缺多少卖）")
                + ("；买入先过闸门，被挡则凑钱的卖出也不做；开盘跳空 / 价格更高没买到时，凑钱的卖出照样会卖" if k == "buy" else ""))
    if paths.halt_file().exists() and k in MO.ORDER_KINDS + ("core",):
        msg += "；★ HALT 生效中：解除之后才处理"
    elif paths.halt_file().exists() and k == "corefix":                            # D7：固定口数读到就生效，ETF 的单等解除后的决策（与执行器写的同一句）
        msg += f"；★ {MO.HALT_CORE_MSG}"
    return True, msg + f"（指令 {rec['id']}）", rec


def _trigger_notify(tag: str, title: str, text: str, level: str = "warn") -> None:
    """面板自动叫执行器的提醒（暂停 / 盘中没下成改到开盘）：Mac 通知 + 手机通知（qbreak 推送 / 通知记录）。去重在 Trigger._flush。"""
    from . import notify
    from .live_unified import mac_notify
    mac_notify(title, text[:200])
    notify.send(title, text, level)


def _retry_soon(book: dict | None, now: dt.datetime) -> bool:
    """盘中没下成的指令 / 比例 / 固定口数（tried 在 MO.RETRY_S 之内）：过一会儿面板会再叫执行器 = 还有路（U4 不算「没有执行路径」）。"""
    def young(v) -> bool:
        try:
            t = dt.datetime.fromisoformat(str(v))
            return 0 <= (now - t).total_seconds() < MO.RETRY_S
        except (TypeError, ValueError):
            return False
    cr = (book or {}).get("core_rule") or {}
    if young(cr.get("tried")) or young(cr.get("fix_tried")):
        return True
    return any(it.get("status") == "pending" and young(it.get("tried"))
               for it in (((book or {}).get("manual") or {}).get("items") or {}).values() if isinstance(it, dict))


def _unknown_open(book: dict | None) -> bool:
    """账本的当前决策里有状态不明的单（SENDING / ERROR）：执行器登记之前不下单、每次运行都停下（撤单除外）。"""
    d = ((book or {}).get("state") or {}).get("last_date")
    return bool(d) and any(isinstance(o, dict) and o.get("decided_on") == d and o.get("status") in ("SENDING", "ERROR")
                           for o in (book or {}).get("orders") or [])


def _pull_mode(tag: str, mode: str, book: dict | None = None, now: dt.datetime | None = None) -> str | None:
    """面板叫的执行器要不要 git pull（2026-10-15）→ "fetch"（不 pull、不换代码，只 git fetch 看一眼远程停止）/ None（照常 pull）。
    fetch 只给今天早上的决策已经在账本里之后的运行：撤单（不建引擎）、盘中（MO.now_due 要早上的运行完成）、开盘前的重试（_due 要决策日对上）。
    补跑（早上的运行没完成：Mac 07:40 睡着 / 运行失败）= 代替 07:40 的照常运行 → 要拉云端当天的日报 / 判断层，照常 pull；
    重试时决策万一还不在账本里（run.py --retry 会按正常流程跑 = 当早上的运行）→ 也照常 pull（liveu.sh 自己也再看一次：mac_login --decided）。"""
    if mode in ("now", "cancel", "open"):               # open：模拟账户的开盘撮合（D3；早上的决策已经在账本里才会叫）
        return "fetch"
    if mode == "catchup":
        return None
    from .calendar_jp import prev_trading_day
    now = now or now_jst()
    b = book if book is not None else _load(tag)[0]
    ld = str(((b or {}).get("state") or {}).get("last_date") or "")
    return "fetch" if ld and ld >= prev_trading_day(now.date()).isoformat() else None


class _Adopted:
    """面板平滑重启（execv）之前叫的执行器：新进程只知道进程号（还是它的子进程：execv 不换进程号）。poll() 与 Popen 一样：
    还在跑 → None；结束了 → 退出码（不是自己的子进程了 / 已经被收走 → 看进程还在不在，不在当作 0）。"""

    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid == 0:
                return None
            self.returncode = os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            try:
                os.kill(self.pid, 0)
                return None
            except PermissionError:
                return None
            except OSError:
                self.returncode = 0
        return self.returncode


class Trigger:
    """面板写了手动指令之后叫执行器（同一个账本同一时间只跑一个）：
    盘中（09:00〜11:30、12:30〜15:25）有要马上下的指令 → --phase now（同一个账本最多 1 分钟一次）；
    交易日 07:45〜08:55（寄付截止 MO.CUTOFF；2026-10-14 G20：以前到 08:50）、今天早上的决策已经做了（账本处理到应有的决策日；
    有单被挡也算 —— 以前要「完成」才叫，被挡时新写的卖出加不进寄付单）、有新的卖出 / 调仓往下 / 撤回 → --retry（加进今天开盘的寄付单；最多 3 分钟一次）。
    模拟账户补跑（G9；2026-10-14）：装着 07:40 的定时任务（没装立花本番）、交易日 07:45〜15:30、今天早上的运行还没完成（Mac 07:40 睡着 /
    运行失败）、没有执行器在跑（运行锁 + liveu.sh 的运行标记）、连续 2 分钟都这样 → 叫一次照常的运行（与登录时的补跑相同：等云端的日报；
    同一天最多 3 次、相隔至少 20 分钟；模拟期开始日之前 / HALT / 有状态不明的单不叫）。立花本番（真钱）永远不补跑。
    HALT 中开盘前不叫 --retry（它什么都不做）；当前决策里有状态不明的单 → 除了撤单什么都不叫（登记之前执行器每次都停下；2026-10-14 复核）。
    失败退避（2026-10-09 立花实盘缺口 A7，条目 UX-04 / C-01：执行器失败后每分钟重叫 = 通知轰炸 + 反复登录立花，可能被判过负荷）：
    记下每个账本上一次叫的进程的退出码（非 0 = 失败）；盘中连续失败 n 次 → 从看到失败起至少等 min(60 秒 × 2^n, 15 分钟)；
    同一天连续失败 3 次（盘中 / 开盘前的重试一起算）→ 当天这个账本暂停自动叫，直到出现新的手动指令（叫那次执行器之后写的）、
    执行器之后跑成了一次（例：你在 Mac 对话里说「再试一次」）或第二天；成功一次就清零。暂停时通知一次（G23），暂停记在状态目录
    panel_trigger.json（面板重启也接着停，第二天作废）。
    盘中没下成、改到开盘（G18）：交易日 15:25 之后看一次，今天盘中试过没下成的指令 → 通知一次「盘中没下成、改到开盘：N 条」。
    模拟账户的开盘撮合（D3；2026-10-15）：成交日 09:25〜11:30、有排队的寄付单 / 等开盘后的买单、还没撮合过
    （live_unified.paper_open_due；HALT 不挡）→ --phase open（Yahoo 1 分钟线约晚 20 分钟：还没到就下一轮再叫，最多 5 分钟一次；
    撤单 / 补跑优先，同样的失败退避与暂停、同样的运行锁；QBREAK_LIVEU_PULL=fetch）。到 11:30 还没做成 → 第二天早上照旧撮合。launchd 不改。
    只管面板自己叫的；07:40 / 08:35 / 09:05 / 09:20 的定时运行不受影响。"""

    def __init__(self, run=None, clock=None, mono=None, notify=None):
        self.run = run or self._spawn
        self.clock = clock or now_jst
        self.mono = mono or time.monotonic
        self.notify = notify or _trigger_notify
        self.last: dict[str, float] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        self.started: dict[str, dt.datetime] = {}           # 账本 → 这次叫执行器的时刻（找这次的运行状态）
        self.fails: dict[str, tuple[str, int]] = {}         # 账本 → (日期, 当天连续失败次数)
        self.errs: dict[str, str] = {}                      # 账本 → 最后一次失败的原因
        self.paused: dict[str, tuple[str, str]] = {}        # 账本 → (日期, 原因)：当天暂停自动叫执行器
        self.pause_ids: dict[str, frozenset] = {}           # 暂停的基准：叫那次执行器时还没读的指令 id（出现不在里面的 = 新的指令 → 恢复）
        self.pause_at: dict[str, dt.datetime] = {}          # 暂停的时刻（之后执行器跑成了一次 → 恢复）
        self.spawn_ids: dict[str, frozenset] = {}           # 账本 → 叫执行器那一刻还没读的指令 id
        self.catchups: dict[str, tuple[str, int]] = {}      # 账本 → (日期, 今天补跑了几次)
        self.catch_last: dict[str, float] = {}              # 账本 → 上一次补跑的单调时刻
        self.behind: dict[str, tuple[str, float]] = {}      # 账本 → (日期, 从什么时候起一直「早上的运行没完成、没有执行器在跑」)
        self.rolled: dict[str, str] = {}                    # 账本 → 哪天已经看过「盘中没下成、改到开盘」
        self.open_last: dict[str, float] = {}               # 账本 → 上一次叫开盘撮合的单调时刻（1 分钟线还没到：OPEN_GAP_S 之后再叫；D3）
        self.outbox: list[tuple[str, str, str, str]] = []   # 要发的提醒（账本, 标题, 正文, 级别）：锁外面发
        self.lock = threading.Lock()
        self._load_pauses()

    @staticmethod
    def _argv(tag: str, mode: str = "retry") -> list[str]:
        """叫执行器的命令。catchup（模拟账户补跑）= 照常的运行（与登录时的补跑 mac_login 相同：等云端的日报入库、照常通知；
        2026-10-14 复核：以前用 --retry，不等日报 → 例行任务晚了时按昨天的输入决策）。"""
        broker = "paper" if tag == "paper" else "tachibana"
        cmd = ["/bin/bash", str(paths.PROJECT_ROOT / "scripts" / "liveu.sh"), "run", "--broker", broker]
        cmd += ["--phase", mode] if mode in ("now", "cancel", "open") else [] if mode == "catchup" else ["--retry"]
        if tag == "tachibana_demo":
            cmd.append("--demo")
        return cmd

    @classmethod
    def _spawn(cls, tag: str, mode: str = "retry"):
        cmd = cls._argv(tag, mode)
        lf = open(paths.log_dir() / "com.qbreak.panel.retry.log", "a", encoding="utf-8")
        what = {"catchup": "早上的运行没完成 → 补跑", "open": "模拟账户开盘撮合（09:25 前后）"}.get(mode, "手动指令")
        lf.write(f"\n── {now_jst():%Y-%m-%d %H:%M:%S} JST {what} → {' '.join(cmd[1:])}\n")
        lf.flush()
        env = {**os.environ, "QBREAK_NO_HOLD": "1"}        # 跑完马上结束，不在进程里等到 09:35（liveu.sh 把让 Mac 醒着放到后台；2026-10-14 G2：
        #                                                   以前立花的 --retry 一直活到 09:35，这段时间面板不再叫执行器 → 撤单、盘中指令都卡住）
        if env.get("QBREAK_LIVEU_PULL") != "0":             # 0 = 本来就关掉了 pull：照旧
            pm = _pull_mode(tag, mode)
            if pm:
                env["QBREAK_LIVEU_PULL"] = pm              # 重试 / 盘中 / 撤单不 git pull、不换代码，只 fetch 看远程停止（2026-10-15「网页app经常卡住」：
            else:                                          #   10-15 08:12 面板叫的 --retry 拉下新代码 → 面板重启、正在操作的手机 502）
                env.pop("QBREAK_LIVEU_PULL", None)         # 当早上的运行（补跑等）：照常 pull 拉云端当天的输入（面板自己的环境里有 fetch 也不带过去）
        return subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(paths.PROJECT_ROOT), start_new_session=True,
                                env=env)

    # ── 面板平滑重启（os.execv，同一个进程号）时把状态交给新的进程：还在跑的执行器、失败次数、补跑次数（2026-10-15） ──
    def export_state(self) -> dict:
        """交给 execv 之后的新进程（JSON；单调时钟是全系统的，跨进程照样能比）。调用方拿着 self.lock。"""
        procs = {}
        for tag, p in self.procs.items():
            pid = getattr(p, "pid", None)
            if isinstance(pid, int) and pid > 1:
                procs[tag] = pid
        return {"procs": procs, "started": {k: v.isoformat() for k, v in self.started.items()}, "last": dict(self.last),
                "fails": {k: list(v) for k, v in self.fails.items()}, "errs": dict(self.errs),
                "spawn_ids": {k: sorted(v) for k, v in self.spawn_ids.items()},
                "catchups": {k: list(v) for k, v in self.catchups.items()}, "catch_last": dict(self.catch_last),
                "behind": {k: list(v) for k, v in self.behind.items()}, "rolled": dict(self.rolled),
                "open_last": dict(self.open_last)}

    def import_state(self, d: dict) -> None:
        """execv 之前的进程交过来的状态（格式不对的跳过；暂停另外记在状态目录、构造时已经读了）。"""
        if not isinstance(d, dict):
            return
        try:
            for tag, pid in (d.get("procs") or {}).items():
                self.procs[tag] = _Adopted(int(pid))
            self.started.update({k: dt.datetime.fromisoformat(v) for k, v in (d.get("started") or {}).items()})
            self.last.update({k: float(v) for k, v in (d.get("last") or {}).items()})
            self.fails.update({k: (str(v[0]), int(v[1])) for k, v in (d.get("fails") or {}).items()})
            self.errs.update({k: str(v) for k, v in (d.get("errs") or {}).items()})
            self.spawn_ids.update({k: frozenset(str(x) for x in v) for k, v in (d.get("spawn_ids") or {}).items()})
            self.catchups.update({k: (str(v[0]), int(v[1])) for k, v in (d.get("catchups") or {}).items()})
            self.catch_last.update({k: float(v) for k, v in (d.get("catch_last") or {}).items()})
            self.behind.update({k: (str(v[0]), float(v[1])) for k, v in (d.get("behind") or {}).items()})
            self.rolled.update({k: str(v) for k, v in (d.get("rolled") or {}).items()})
            self.open_last.update({k: float(v) for k, v in (d.get("open_last") or {}).items()})
        except (TypeError, ValueError, IndexError, AttributeError) as e:
            log.warning("面板重启：接过来的自动叫执行器的状态格式不对（跳过一部分）：%s", e)

    # ── 暂停记在状态目录（面板重启也接着停；G23） ──
    def _load_pauses(self) -> None:
        from . import run_status as RS
        d = RS.peek_json(paths.state_dir() / RS.TRIGGER_FILE) or {}
        today = self.clock().date().isoformat()
        for tag, rec in (d.items() if isinstance(d, dict) else []):
            if isinstance(rec, dict) and rec.get("day") == today and tag in BOOKS:
                self.paused[tag] = (today, str(rec.get("why") or ""))
                self.pause_ids[tag] = frozenset(str(x) for x in rec.get("ids") or [])
                self.fails[tag] = (today, FAIL_PAUSE_N)
                t = RS.ts(rec.get("at"))
                if t is not None:
                    self.pause_at[tag] = t

    def _save_pauses(self) -> None:
        from .utils import atomic_write_text
        d = {tag: {"day": day, "why": why, "ids": sorted(self.pause_ids.get(tag, frozenset())),
                   "at": (self.pause_at.get(tag) or self.clock()).isoformat(timespec="seconds")}
             for tag, (day, why) in self.paused.items()}
        try:
            from . import run_status as RS
            atomic_write_text(paths.state_dir() / RS.TRIGGER_FILE, json.dumps(d, ensure_ascii=False, indent=1))
        except Exception as e:                               # noqa: BLE001
            log.warning("面板自动叫执行器的暂停没记下（面板重启后会忘）：%s", e)

    @staticmethod
    def _unseen_ids(tag: str, book: dict | None = None) -> frozenset:
        if book is None:
            book = _load(tag)[0]
        return frozenset(r["id"] for r in MO.unseen(tag, book))

    def _nfail(self, tag: str, today: str) -> int:
        d, n = self.fails.get(tag, ("", 0))
        return n if d == today else 0

    def _err(self, tag: str, rc) -> str:
        """这次失败的原因：执行器写的运行状态文件（qbreak/run_status.py）里这次运行之后的 error；没有 → 退出码。"""
        from . import run_status as RS
        rec = RS.read(tag) or {}
        try:
            t, t0 = RS.ts(rec.get("at")), self.started.get(tag)
            fresh = t is not None and (t0 is None or t >= t0 - dt.timedelta(seconds=5))
        except TypeError:                                    # 时钟没带时区：不比较
            fresh = True
        if rec.get("ok") is False and rec.get("error") and fresh:
            return str(rec["error"])
        return f"退出码 {rc}（看数据目录 logs/com.qbreak.panel.retry.log）"

    def _reap(self, tag: str, today: str) -> bool:
        """上一次叫的执行器结束了 → 记下成败（退出码非 0 = 失败）。返回「还在跑」（每次只 poll 一次：
        先看到「还在跑」、紧接着又看到「结束了」时，失败不会漏记）。没有进程对象 → False；没有 poll() 的当作已结束（成功）。"""
        p = self.procs.get(tag)
        if p is None:
            return False
        rc = getattr(p, "poll", lambda: 0)()
        if rc is None:
            return True                                    # 还在跑
        del self.procs[tag]
        if rc == 0:
            self.fails.pop(tag, None)                      # 成功一次就清零
            self.errs.pop(tag, None)
            return False
        n = self._nfail(tag, today) + 1
        self.fails[tag] = (today, n)
        self.errs[tag] = self._err(tag, rc)
        self.last[tag] = self.mono()                       # 退避从「看到失败」算起（执行器可能跑了很久才失败）
        log.warning("面板叫的执行器失败（%s，今天连续第 %d 次，退出码 %s）", tag, n, rc)
        if n >= FAIL_PAUSE_N:
            base = self.spawn_ids.get(tag, frozenset())
            if self._unseen_ids(tag) - base:               # 这次运行期间你写了新的指令：等于「修好后写新的指令」→ 不暂停、重新计数
                self.fails.pop(tag, None)
                log.info("面板叫的执行器连续失败 %d 次（%s），但期间有新的手动指令：不暂停", n, tag)
                return False
            self.paused[tag] = (today, self.errs[tag])
            self.pause_ids[tag] = base
            self.pause_at[tag] = self.clock()
            self._save_pauses()
            name = BOOKS.get(tag, tag)
            self.outbox.append((tag, f"qbreak {name} ★ 面板自动下单今天暂停",
                                f"今天剩下的盘中指令不会再自动下：执行器连续失败 {n} 次（{NM.annotate(self.errs[tag])}）。"
                                "修好后写一条新的指令，或在 Mac 对话里说「再试一次」；明天自动恢复", "warn"))
            log.warning("面板叫的执行器今天连续失败 %d 次（%s）：今天暂停自动叫（新的手动指令 / 再跑成一次 / 明天恢复）", n, tag)
        return False

    def _ran_ok_since(self, tag: str) -> bool:
        """暂停之后执行器跑成了一次（运行状态文件 ok、时刻在暂停之后；例：在 Mac 对话里说「再试一次」→ 手动跑了一次）。"""
        from . import run_status as RS
        t0 = self.pause_at.get(tag)
        rec = RS.read(tag) or {}
        t = RS.ts(rec.get("at"))
        try:
            return t0 is not None and t is not None and rec.get("ok") is True and t > t0
        except TypeError:                                    # 时钟没带时区：不比较
            return False

    def _still_paused(self, tag: str, today: str, book: dict | None = None) -> bool:
        """暂停中：第二天 / 有新的手动指令（出现叫那次执行器时还没有的指令 id）/ 暂停之后执行器跑成了一次 → 恢复（失败次数清零）。
        指令被定时运行读掉（没读的变少）不算新的指令。"""
        pz = self.paused.get(tag)
        if not pz:
            return False
        new = pz[0] == today and bool(self._unseen_ids(tag, book) - self.pause_ids.get(tag, frozenset()))
        ok = pz[0] == today and not new and self._ran_ok_since(tag)
        if pz[0] == today and not new and not ok:
            return True
        self.paused.pop(tag, None)
        self.pause_ids.pop(tag, None)
        self.pause_at.pop(tag, None)
        self.fails.pop(tag, None)
        self._save_pauses()
        log.info("面板自动叫执行器恢复（%s）：%s", tag,
                 "第二天" if pz[0] != today else ("有新的手动指令" if new else "执行器之后跑成了一次"))
        return False

    def _gap(self, tag: str, today: str, morning: bool) -> float:
        if morning:
            return TRIGGER_GAP_S                           # 开盘前的重试照旧（3 分钟一次、到 08:55 为止）
        return min(NOW_GAP_S * 2 ** self._nfail(tag, today), FAIL_GAP_MAX_S)

    def _due(self, tag: str, book: dict, now: dt.datetime, morning: bool) -> bool:
        """面板现在会不会为这个账本叫执行器（不看退避）：开盘前 = 今天早上的决策已经做了（账本处理到应有的决策日；有单被挡也算，
        G20）+ 有新的卖出 / 调仓往下 / 撤回（HALT 时不算：MO.due）；盘中 = 有要马上下的指令。
        当前决策里有状态不明的单 → 不叫（2026-10-14 复核：执行器登记之前每次都停下 → 以前连叫 3 次失败、当天暂停、发暂停通知；
        面板顶部已经写着去核对 / 登记）。"""
        from .trader import expected_last_bar
        if _unknown_open(book):
            return False
        if morning:
            ld = str((book.get("state") or {}).get("last_date") or "")
            return ld == expected_last_bar(now.date(), "JP").isoformat() and bool(MO.due(tag, book, now))
        return bool(MO.now_due(tag, book, now))

    def _open_due(self, tag: str, book: dict, now: dt.datetime) -> bool:
        """模拟账户的开盘撮合（D3；2026-10-15）：live_unified.paper_open_due（成交日 09:25〜11:30、有排队的寄付单 / 等开盘后的买单、
        还没撮合过、没有状态不明的单）+ 上一次叫开盘撮合之后过了 OPEN_GAP_S（1 分钟线还没到 → 执行器什么都不改、下一轮再叫）。"""
        from .live_unified import paper_open_due
        if tag != "paper" or not paper_open_due(book, now):
            return False
        return self.mono() - self.open_last.get(tag, -1e9) >= OPEN_GAP_S

    def _catchup_due(self, tag: str, book: dict, now: dt.datetime) -> bool:
        """模拟账户补跑（G9）：见类的说明。连续 CATCHUP_GRACE_S 秒都「没完成、没有执行器在跑」才叫（Mac 醒来时 launchd 也会把错过的
        07:40 拉起来：先让它起来）。立花永远不补跑。"""
        from . import run_status as RS
        from .calendar_jp import prev_trading_day
        from .live_unified import lock_held
        today = now.date().isoformat()
        if (tag != "paper" or not is_trading_day(now.date()) or not (CATCHUP_FROM <= now.time() < MO.CANCEL_UNTIL)
                or not _scheduled(paths.PAPER_AGENT) or paths.live_installed() or paths.halt_file().exists()):
            self.behind.pop(tag, None)
            return False
        ld = str((book.get("state") or {}).get("last_date") or "")
        if not ld or ld >= prev_trading_day(now.date()).isoformat() or _unknown_open(book):
            self.behind.pop(tag, None)
            return False                                     # 完成了（或账本还没有：第一次运行不归面板）/ 有状态不明的单（登记之前跑也会停下）
        from .watchdog import _sim_start
        start = _sim_start()
        if start and today < start:
            return False                                     # 模拟期开始日之前执行器本来就不推进模拟账户
        if lock_held(paths.state_dir() / f"live_unified_{tag}.lock") or RS.runs_active("paper"):
            self.behind.pop(tag, None)
            return False                                     # 有执行器在跑（拉代码 / 等云端 / 决策）：等它
        d, n = self.catchups.get(tag, ("", 0))
        if d == today and n >= CATCHUP_MAX:
            return False
        if d == today and self.mono() - self.catch_last.get(tag, -1e9) < CATCHUP_GAP_S:
            return False
        bd, since = self.behind.get(tag, ("", 0.0))
        if bd != today:
            self.behind[tag] = (today, self.mono())
            return False
        return self.mono() - since >= CATCHUP_GRACE_S

    def status(self, tag: str, now: dt.datetime | None = None, book: dict | None = None) -> tuple[str, str] | None:
        """面板顶部的一行（未转义的文字）：(CSS 类, 文字)。今天暂停中 → ★；今天失败过、还有要叫执行器的指令 → 最早什么时候再叫；
        今天补跑过早上的运行 → 说一声；没事（或已经没有要下的指令：之后不会再叫）→ None。book：render 已经读好的账本（不给就读）。"""
        now = now or self.clock()
        today = now.date().isoformat()
        morning = is_trading_day(now.date()) and TRIGGER_FROM <= now.time() < TRIGGER_UNTIL
        with self.lock:
            pz = self.paused.get(tag)
            if pz and pz[0] == today:
                return ("neg", f"★ 盘中自动下单暂停：执行器连续失败 {FAIL_PAUSE_N} 次（{pz[1]}）；修好后写新的指令或明天自动恢复"
                               "（也可以在 Mac 对话里说「再试一次」）")
            n = self._nfail(tag, today)
            cd, cn = self.catchups.get(tag, ("", 0))
            if n <= 0 and cd == today and cn > 0 and tag not in self.procs:
                b = book if book is not None else _load(tag)[0]
                from .calendar_jp import prev_trading_day
                if str((b.get("state") or {}).get("last_date") or "") < prev_trading_day(now.date()).isoformat():
                    return ("neg", f"★ 今天早上的运行没完成：面板已经补跑了 {cn} 次还是没完成（最多 {CATCHUP_MAX} 次）"
                                   "：在 Mac 对话里说「看一下执行器日志」")
                return None
            if n <= 0 or tag in self.procs or not (morning or MO.timing(now)[0] == "now"):
                return None
            wait = max(0.0, self._gap(tag, today, morning) - (self.mono() - self.last.get(tag, -1e9)))
        if not self._due(tag, book if book is not None else _load(tag)[0], now, morning):
            return None                                    # 指令已经被读掉 / 撤回：面板不会再叫，「最早几点再叫」就不对了
        nxt = (now + dt.timedelta(seconds=wait)).strftime("%H:%M")
        return ("muted", f"面板叫的执行器今天连续失败 {n} 次：最早 {nxt} 再自动叫（连续 {FAIL_PAUSE_N} 次失败当天暂停）")

    def _rollover(self, tag: str, now: dt.datetime) -> None:
        """交易日 15:25 之后看一次（G18）：今天盘中试过、没下成、改到开盘的指令 → 提醒一次「盘中没下成、改到开盘：N 条」。
        同时（D5 / M3；2026-10-15）：今天没下成 / 不会下的全部（live_ops.not_today：不会下的单与指令、今天该下却改到之后的指令、
        还没发出的今天的单；HALT 的不算、上面那条已经写了的不重复）→ 一条「★ 交易：… 今天没下成 / 不会下：N 笔」（warn）。"""
        today = now.date().isoformat()
        if self.rolled.get(tag) == today or not is_trading_day(now.date()) or now.time() < MO.SESSION[1][1]:
            return
        self.rolled[tag] = today
        book = _load(tag)[0]
        items = ((book.get("manual") or {}).get("items") or {}).values()
        rows = [it for it in items if MO.rolled_over(it, now) and str(it.get("tried") or "")[:10] == today]
        if rows:
            nd = MO.rolled_over(rows[0], now)
            body = "\n".join(f"- {MO.describe(it)}：{MO.msg_text(it, now) or '没下成'}" for it in rows[:10]) + ("\n…" if len(rows) > 10 else "")
            self.outbox.append((tag, f"qbreak {BOOKS.get(tag, tag)} 盘中没下成、改到开盘：{len(rows)} 条",
                                f"{body}\n→ {nd:%m/%d} 开盘（寄付）照常处理；不要了就在面板「交易」里撤回", "info"))
        self._not_today(tag, book, now, {str(it.get("id")) for it in rows})

    def _not_today(self, tag: str, book: dict, now: dt.datetime, told: set) -> None:
        """15:25 之后：今天没下成 / 不会下的汇总（D5）。told：「盘中没下成、改到开盘」已经写了的指令 id。今天早上的运行都没完成 → 不写
        （09:30 自检 / 补跑的提醒已经说了）。"""
        from . import live_ops as LO
        if not book or MO.morning_behind(book, now):
            return
        pz = self.paused.get(tag)
        ol = LO.outlook(book, MO.unseen(tag, book), now, tag=tag, paused=bool(pz and pz[0] == now.date().isoformat()))
        rows = [r for r in LO.not_today(ol, now) if r["ref"] not in told]
        if not rows:
            return
        from . import notify_seen as NS                    # 同一天同一批只推一次：去重键是哪几笔（不含金额 / 原因的文字；面板重启也不重推）
        if not NS.first(tag, f"{LO.TRADE_HEAD}|not_today|{now.date()}|" + ",".join(sorted(r["ref"] for r in rows)), now):
            return
        body = "\n".join(f"- {LO.row_text(r)}" for r in rows[:12]) + ("\n…" if len(rows) > 12 else "")
        self.outbox.append((tag, f"{LO.TRADE_HEAD}：qbreak {BOOKS.get(tag, tag)} 今天没下成 / 不会下：{len(rows)} 笔",
                            f"{body}\n→ 写了「→ 某天」的到时候照常处理；不会下的要照原样下就写新的指令；不要了：面板「交易」里撤回", "warn"))

    def _no_path(self, tag: str, book: dict, now: dt.datetime, today: str) -> None:
        """U4（D5；2026-10-15）：盘中、outlook 判「会下」的单 / 指令过了该下的时刻 10 分钟（live_ops.NO_PATH_S），却没有一条路会下它
        （面板叫执行器的几种都不成立：要马上下的指令 / 开盘前的重试 / 撤单 / 模拟账户开盘撮合 / 补跑；立花等开盘后的买单 09:30 之前
        还有 09:20 的定时运行；盘中没下成的 10 分钟内会再试）→「★ 交易：… 今天该下但没有执行路径」（warn；同一笔同一天只推一次，
        去重键不含金额）。执行器在跑 / 面板自动下单暂停 / 失败退避中 / 今天早上的运行还没完成 → 不判断（各有自己的提醒）。"""
        from . import live_ops as LO
        from . import notify_seen as NS
        from . import run_status as RS
        from .live_unified import lock_held, paper_open_due
        if (tag in self.procs or self._nfail(tag, today) > 0 or MO.morning_behind(book, now) or _unknown_open(book)
                or lock_held(paths.state_dir() / f"live_unified_{tag}.lock") or RS.runs_active(tag)):
            return
        if MO.due(tag, book, now) or MO.now_due(tag, book, now) or MO.cancel_due(tag, book, now) or paper_open_due(book, now):
            return
        if _retry_soon(book, now):
            return
        cut = now - dt.timedelta(seconds=LO.NO_PATH_S)
        ol = LO.outlook(book, MO.unseen(tag, book), now, tag=tag)
        late = []
        for r in ol["rows"]:
            t = r.get("act_at")
            if r["state"] != "will" or not isinstance(t, dt.datetime) or t > cut:
                continue
            if r["kind"] == "order" and (r.get("status") != "DEFERRED"
                                         or (tag != "paper" and now.time() < LO.LATE_UNTIL)):
                continue                                     # 在交易所的 / 立花 09:20 的定时运行还会补
            if NS.first(tag, LO.trade_key(r, now, "U4"), now):
                late.append(r)
        if late:
            body = "\n".join(f"- {LO.row_text(r)}（该在 {LO.act_text(r, now)} 下）" for r in late)
            self.outbox.append((tag, f"{LO.TRADE_HEAD}：qbreak {BOOKS.get(tag, tag)} 今天该下但没有执行路径",
                                f"{body}\n→ 面板不会再自动叫执行器下它：在 Mac 对话里说「再试一次」，或在面板「交易」里撤回", "warn"))

    def _flush(self, now: dt.datetime) -> None:
        """锁外面发提醒：同一个账本、同一天、同一段文字只发一次（qbreak/notify_seen.py）。"""
        from . import notify_seen as NS
        with self.lock:
            box, self.outbox = self.outbox, []
        for tag, title, text, level in box:
            try:
                if NS.first(tag, NM.seen_key(f"面板|{title}|{text}"), now):   # 名字不算新的原因（加了名字 / 名字表更新那天不重复发；2026-10-15）
                    self.notify(tag, title, text, level)
            except Exception as e:                           # noqa: BLE001
                log.warning("面板的提醒没发成（%s）：%s", tag, e)

    def check(self) -> list[str]:
        """看一遍各个账本；返回这次叫了执行器的账本。"""
        now = self.clock()
        today = now.date().isoformat()
        morning = is_trading_day(now.date()) and TRIGGER_FROM <= now.time() < TRIGGER_UNTIL
        session = MO.timing(now)[0] == "now"
        cwin = is_trading_day(now.date()) and now.time() < MO.CANCEL_UNTIL     # 撤单 / 补跑：开盘前 / 午休也叫（15:30 之前）
        names = books() if (morning or session or cwin) else []
        with self.lock:
            for tag in list(self.procs):
                if tag not in names:
                    self._reap(tag, today)                   # 这次不看的账本（不在叫的时段 / 不在列表里）：结束了就记下成败
            if is_trading_day(now.date()) and now.time() >= MO.SESSION[1][1]:
                for tag in books():
                    try:
                        self._rollover(tag, now)
                    except Exception as e:                   # noqa: BLE001
                        log.warning("盘中没下成的汇总出错（%s）：%s", tag, e)
        out = []
        if names:
            with self.lock:
                for tag in names:
                    if self._reap(tag, today):
                        continue                             # 上一次叫的还在跑（结束了：这里记下成败，每次只 poll 一次）
                    if tag in self.paused and self._still_paused(tag, today):
                        continue                             # 今天连续失败 3 次：等新的手动指令 / 再跑成一次 / 明天
                    book, _ = _load(tag)
                    if MO.cancel_due(tag, book, now):
                        mode = "cancel"                      # 撤单指令：先撤（不看早上的运行完成没有；HALT 时也撤）
                    elif self._catchup_due(tag, book, now):
                        mode = "catchup"                     # 模拟账户：今天早上的运行没完成、没有执行器在跑 → 补跑（G9）
                    elif self._open_due(tag, book, now):
                        mode = "open"                        # 模拟账户：09:25 前后按 1 分钟线的开盘价当天撮合（D3）
                    elif (morning or session) and self._due(tag, book, now, morning):
                        mode = "retry" if morning else "now"
                    else:
                        if session:
                            self._no_path(tag, book, now, today)   # 该下的时刻过了 10 分钟、没有路会下它 → ★ 交易（U4）
                        continue                             # 开盘前：早上的决策还没做（它自己会读到指令）/ 没有新指令
                    if self.mono() - self.last.get(tag, -1e9) < self._gap(tag, today, morning and mode not in ("cancel", "catchup")):
                        continue                             # 失败过：从看到失败起按连续失败次数加倍等
                    self.last[tag] = self.mono()
                    try:
                        self.started[tag] = now
                        self.spawn_ids[tag] = self._unseen_ids(tag, book)   # 暂停的基准：叫的这一刻还没读的指令
                        self.procs[tag] = self.run(tag, mode)
                        if mode == "open":
                            self.open_last[tag] = self.mono()
                        if mode == "catchup":
                            d, n = self.catchups.get(tag, ("", 0))
                            self.catchups[tag] = (today, (n if d == today else 0) + 1)
                            self.catch_last[tag] = self.mono()
                            self.behind.pop(tag, None)
                        out.append(tag)
                        log.info("%s：叫执行器（%s，%s）", {"catchup": "早上的运行没完成", "open": "模拟账户开盘撮合"}.get(mode, "手动指令"),
                                 tag, mode)
                    except Exception as e:                   # noqa: BLE001
                        log.warning("叫执行器失败（%s，%s）：%s", tag, mode, e)
        self._flush(now)
        return out

    def loop(self, stop: threading.Event, every: float = 30.0) -> None:
        while not stop.wait(every):
            try:
                self.check()
            except Exception as e:                           # noqa: BLE001
                log.warning("面板的定时检查出错（继续）：%s", e)


# ───────────────────────── K 线数据（按需取） ─────────────────────────
_CHART_T = re.compile(r"[0-9A-Z][0-9A-Z.^=\-]{0,14}")
_CHART_CACHE: dict = {}
_CHART_LOCK = threading.Lock()


def chart_json(tag: str, t: str, now: dt.datetime | None = None) -> tuple[int, dict]:
    """一只票的 K 线（执行器写的 out/charts_<账本>.json；按文件的修改时间缓存）→ (HTTP 状态, JSON)。
    持有的个股 / 核心 ETF：现价接口取过的「今天这一根」（1 分钟线合计，约晚 20 分钟）并进日K / 周K / 月K（kline.with_live；
    2026-10-07 用户「当天日线在交易时间在K线中要随时价钱反映」）；这里不去取价（取价只在 /api/quotes，页面每次取完再要一次图）。
    live.open：这一根是今天、还没收盘（交易日 09:00〜15:30）→ 页面写「盘中」；收盘后到正式日线换上之前 → 写「暂定」。"""
    data = _chart_data(tag)
    if data is None:
        return 404, {"ok": False, "msg": "还没有 K 线（执行器下一次运行之后）"}
    pl = (data.get("tickers") or {}).get(t)
    if pl is None:
        return 404, {"ok": False, "msg": f"没有 {NM.label(t)} 的 K 线"}
    lv = _live_bar(tag, t) if (_held(tag, t) or _suggested(tag, t)) else None
    if lv is not None:
        try:
            pl2 = KL.with_live(pl, lv.get("bar"), lv.get("at"))
        except Exception as e:                               # noqa: BLE001  只展示：并不进去就给原来的图
            log.warning("K 线并不进今天这一根（%s）：%s", t, e)
            pl2 = pl
        if pl2 is not pl and pl2.get("live"):
            now = now or now_jst()
            pl2["live"]["open"] = (pl2["live"]["d"] == now.date().isoformat() and is_trading_day(now.date())
                                   and dt.time(9, 0) <= now.time() < dt.time(15, 30))
        pl = pl2
    return 200, {"ok": True, "t": t, "asof": data.get("asof"), "data": pl}


def _prev_close(tag: str, book: dict | None, sm: dict | None, t: str, last_date: str) -> float | None:
    """今天买进（对账前）的个股的「昨收」= 决策那天（state.last_date）的收盘：执行器汇总里建议的股票那一行 → K 线文件（out/charts_<账本>.json
    的日线、last_date 当天或之前最近的一根）。都没有 → None（页面不写「比昨收」，不拿成交价充数；2026-10-16 复核）。"""
    v = _close_of(book, sm, t)
    if v:
        return v
    D = (((((_chart_data(tag) or {}).get("tickers") or {}).get(t) or {}).get("tf") or {}).get("D")) or {}
    for d, c in reversed(list(zip(D.get("d") or [], D.get("c") or []))):
        try:
            if (not last_date or str(d)[:10] <= last_date[:10]) and c and float(c) > 0:
                return round(float(c), 4)
        except (TypeError, ValueError):
            continue
    return None


def _chart_data(tag: str) -> dict | None:
    """执行器写的 out/charts_<账本>.json（按修改时间缓存）；没有 → None。"""
    fp = paths.out_dir() / f"charts_{tag}.json"
    try:
        mt = fp.stat().st_mtime
    except OSError:
        return None
    with _CHART_LOCK:
        c = _CHART_CACHE.get(str(fp))
        if c is None or c[0] != mt:
            c = (mt, read_json(fp, {}) or {})
            _CHART_CACHE[str(fp)] = c
    return c[1]


def _dvol(tag: str, t: str, n: int = 60) -> float | None:
    """这只票最近 n 天的日波动（日K 收盘的对数收益率的标准差；K 线文件里的）；算不出 → None。"""
    try:
        c = [float(x) for x in ((((_chart_data(tag) or {}).get("tickers") or {}).get(t) or {}).get("tf") or {}).get("D", {}).get("c") or []
             if x is not None and float(x) > 0][-(n + 1):]
    except (TypeError, ValueError):
        return None
    if len(c) < 21:
        return None
    r = [math.log(b / a) for a, b in zip(c, c[1:])]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def _suggested(tag: str, t: str) -> bool:
    """t 在执行器汇总的候选（suggest.rows）里 = 选股两张卡（「规则接下来会自动买」/「建议的股票」）的票（K 线并进今天这一根、现价接口只接受这些）。"""
    return any(r.get("ticker") == t for r in ((_load(tag)[1] or {}).get("suggest") or {}).get("rows") or [])


def _held(tag: str, t: str) -> bool:
    """t 现在在这个账本里拿着（个股或核心 ETF；含今天已成交，live_ops.held_now，2026-10-16）。只读账本（不读执行器汇总）。"""
    pj = LO.held_now(read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {}, tag)
    return t in (pj.get("pos") or {}) or int((pj.get("core_units") or {}).get(t, 0) or 0) > 0


def _live_bar(tag: str, t: str) -> dict | None:
    """现价缓存里这只票最新的一条（{"px", "at", "bar"}）；没取过 → None。"""
    with _QUOTE_LOCK:
        hits = [c for k, c in _QUOTE_CACHE.items() if k[0] == tag and (c[1] or {}).get(t)]
    if not hits:
        return None
    return max(hits, key=lambda c: c[0])[1][t]


# ───────────────────────── 持仓的现价（按需取） ─────────────────────────
FEE_TIERS = tuple(_BROKERS[_DEFAULT_BROKER["JP"]]["markets"]["JP"].get("commission_tiers") or ())   # 页面算部分卖出的手续费（= MO.fee_jp）
_QUOTE_CACHE: dict = {}                                     # (账本, 票的组) → (取到的单调时刻, {票: 现价})
_QUOTE_LOCK = threading.Lock()                              # 只在读写上面这个 dict 时拿着；下载在锁外（2026-10-15「网页app经常卡住」：以前整段
#                                                             Yahoo 下载都拿着它 → Yahoo 一慢，现价 40 秒、持仓 / 建议股票的 K 线 92 秒，页面 15 秒放弃「取不到」）
_QUOTE_FLIGHT: dict = {}                                    # 正在下载的组 → (threading.Event, 开始的单调时刻)（同一组同一时间只下载一次，别的请求等它）
QUOTE_FLIGHT_MAX_S = 60.0                                   # 一次下载最多算这么久：卡住了（Yahoo 不回、超时也没起作用）→ 不再等它，下一个请求重新下载
#                                                             （以前没有上限：一次卡住，这一组的现价就永远停在旧的 / 空的，直到面板重启；2026-10-15）
_QUOTE_FAILN: dict = {}                                     # 组 → 连续取不到几次（退避：盘中 10 → 30 → 120 秒；其他时间至少 60 秒）
QUOTE_WAIT_S = 8.0                                          # 没有现价时请求最多等下载这么久（页面 15 秒放弃）；等不到先回空的，下载在后台接着跑完放进缓存
QUOTE_FRESH_WAIT_S = 2.5                                    # 有上一次的现价时最多等新的这么久（Yahoo 正常 0.3〜1.4 秒）；等不到先回上一次的（每只带时刻）
QUOTE_BACKOFF_S = (10, 30, 120)
QUOTE_TIMEOUT_S = 4                                         # yfinance 每个请求的超时（默认 10 秒；一只一只取）
_QUOTE_WARN = [0.0]                                         # 取不到 / 很慢的警告：每分钟最多写一次日志


def _quote_fetch(key, tickers: list, fetch, live: bool, prev, ev: threading.Event | None = None) -> None:
    """后台下载一组现价（锁外）→ 放进缓存、叫醒等着的请求。取不到：留着上一次的现价（每只带时刻），按连续失败次数退避再试。
    ev：这次下载的 Event（超过 QUOTE_FLIGHT_MAX_S 被放弃、已经有新的下载接手 → 只在自己取到了时写缓存，不动新的那次的记录）。"""
    t0 = time.perf_counter()
    m0 = time.monotonic()
    try:
        q = fetch(list(tickers)) or {}
        err = ""
    except Exception as e:                                   # noqa: BLE001
        q, err = {}, f"{type(e).__name__}: {e}"[:200]
    el = time.perf_counter() - t0
    with _QUOTE_LOCK:
        fl = _QUOTE_FLIGHT.get(key)
        mine = fl is not None and (ev is None or fl[0] is ev)
        if q:
            _QUOTE_CACHE[key] = (time.monotonic(), q)
            _QUOTE_FAILN.pop(key, None)
        elif mine or not (_QUOTE_CACHE.get(key) and _QUOTE_CACHE[key][0] > m0):   # 被放弃的那次取不到：不盖掉之后取到的
            n = _QUOTE_FAILN.get(key, 0) + 1
            _QUOTE_FAILN[key] = n
            ttl = 60 if live else 600
            wait = QUOTE_BACKOFF_S[min(n, len(QUOTE_BACKOFF_S)) - 1] if live else max(60, QUOTE_BACKOFF_S[min(n, len(QUOTE_BACKOFF_S)) - 1])
            _QUOTE_CACHE[key] = (time.monotonic() - ttl + wait, (prev or {}) if isinstance(prev, dict) else {})
        if mine:
            _QUOTE_FLIGHT.pop(key, None)
            ev = fl[0]
    if ev is not None:
        ev.set()
    if (not q or el > 5) and time.monotonic() - _QUOTE_WARN[0] > 60:
        _QUOTE_WARN[0] = time.monotonic()
        log.warning("现价%s（%d 只，用时 %.1f 秒%s）", "取不到" if not q else "很慢", len(tickers), el, f"；{err}" if err else "")


def _short_timeout(f):
    """取现价的函数接受 timeout → 用 QUOTE_TIMEOUT_S 秒（yfinance 默认 10 秒）；不接受（换成别的取法）→ 原样。"""
    import functools
    import inspect
    try:
        ok = "timeout" in inspect.signature(f).parameters
    except (TypeError, ValueError):
        ok = False
    return functools.partial(f, timeout=QUOTE_TIMEOUT_S) if ok else f


def _quotes_cached(key, tickers: list, fetch, live: bool) -> dict:
    """一组票的现价（Mac 与手机共用缓存：盘中 60 秒、其他时间 10 分钟）。过期了 → 后台下载（同一组只下载一次），
    请求最多等 QUOTE_FRESH_WAIT_S（有上一次的）/ QUOTE_WAIT_S（没有）秒；等不到先回手上有的。"""
    ttl = 60 if live else 600
    with _QUOTE_LOCK:
        c = _QUOTE_CACHE.get(key)
        if c is not None and time.monotonic() - c[0] <= ttl:
            return c[1]
        fl = _QUOTE_FLIGHT.get(key)
        if fl is not None and time.monotonic() - fl[1] > QUOTE_FLIGHT_MAX_S:   # 上一次下载卡住了：不再等它（它晚到的结果照样放进缓存）
            log.warning("现价下载超过 %.0f 秒没结束（%d 只）：重新下载", QUOTE_FLIGHT_MAX_S, len(tickers))
            fl = None
        if fl is None:
            if fetch is None:
                from .data import intraday_quotes
                fetch = _short_timeout(intraday_quotes)
            ev = threading.Event()
            _QUOTE_FLIGHT[key] = (ev, time.monotonic())
            threading.Thread(target=_quote_fetch, args=(key, list(tickers), fetch, live, c[1] if c else None, ev),
                             daemon=True, name="qbreak-quotes").start()
        else:
            ev = fl[0]
    ev.wait(QUOTE_FRESH_WAIT_S if c and c[1] else QUOTE_WAIT_S)
    with _QUOTE_LOCK:
        c2 = _QUOTE_CACHE.get(key)
    return (c2 or c or (0.0, {}))[1]


SG_MAX = 12                                                  # 现价接口一次最多取几只建议的股票（页面只要打开的 K 线 / 买入框里的）


def _delay_min(at, now: dt.datetime) -> float | None:
    """现价是几分钟前的（盘中、今天的才算；收盘后 / 前一天的 → None：那就是收盘价）。"""
    try:
        a = dt.datetime.fromisoformat(str(at))
    except (TypeError, ValueError):
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=JST)
    if MO.timing(now)[0] != "now" or a.date() != now.date():
        return None
    return max(0.0, (now - a).total_seconds() / 60)


def quotes_json(tag: str, now: dt.datetime | None = None, fetch=None, extra: list | None = None) -> tuple[int, dict]:
    """持有的个股与核心 ETF 的现价（Yahoo 1 分钟线，约晚 20 分钟；只展示，不下单）→ (HTTP 状态, JSON)。
    extra（页面的 t=…）：选股里的票（「规则接下来会自动买」/「建议的股票」打开的 K 线 / 买入框；只接受执行器汇总里列着的候选、
    没拿着的，一次最多 SG_MAX 只）→ 只回这些。
    同一组票盘中 60 秒内、其他时间 10 分钟内只取一次（Mac 与手机共用）；票由账本 / 汇总决定（不接受随便的代码）。
    每只附：rng = 晚了这几分钟里价格通常（约 95%）在 ±几 % 以内（日波动按 K 线文件算；只是估算）；
    头上附 basis = 现在点卖 / 买，下单按什么价（MO.order_basis）。"""
    now = now or now_jst()
    book, sm = _load(tag)
    pj = LO.held_now(book, tag, now=now)                   # 拿着的 = 含今天已成交（卖光的不列、今天买进的列出；2026-10-16）
    hnb = pj.get("by_ticker") or {}
    st, cr = pj["state"], book.get("core_rule") or {}
    lpos = ((book.get("state") or {}).get("pos") or {})
    held = {t: {"kind": "stock", "n": int(p.get("shares") or 0),
                "prev": (float(p.get("last_close") or 0) if t in lpos or not p.get("today")
                         else float(_prev_close(tag, book, sm, t, str(st.get("last_date") or "")) or 0)),   # 今天买进的：比昨收 = 决策那天的收盘（不是成交价；2026-10-16 复核）
                "cost": float(p.get("entry_px") or 0)} for t, p in (st.get("pos") or {}).items()}
    held.update({t: {"kind": "core", "n": int(u), "cost": 0.0,
                     "prev": float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)}
                 for t, u in (st.get("core_units") or {}).items() if int(u) > 0})
    sgr = {}
    if extra is not None:                                    # 选股的候选（两张卡）：只接受汇总里列着的、没拿着的
        listed = {r.get("ticker"): r for r in ((sm or {}).get("suggest") or {}).get("rows") or []}
        for t in extra:
            if t in listed and t not in held and t not in sgr and len(sgr) < SG_MAX:
                sgr[t] = listed[t]
        rows = {t: {"kind": "suggest", "n": 0, "prev": float(r.get("close") or 0), "cost": 0.0} for t, r in sgr.items()}
    else:
        rows = held
    live = MO.timing(now)[0] == "now"
    paper = tag.startswith("paper")
    head = {"ok": True, "src": "Yahoo 1 分钟线（约晚 20 分钟）", "live": live, "asof": now.isoformat(timespec="minutes"),
            "basis": {"SELL": MO.order_basis(paper, now, "SELL"), "BUY": MO.order_basis(paper, now, "BUY")}}
    if not rows:
        return 200, {**head, "rows": {}}
    key = (tag, ("sg",) + tuple(sorted(rows)) if extra is not None else tuple(sorted(rows)))
    q = _quotes_cached(key, sorted(rows), fetch, live)       # 下载在锁外、同一组只下载一次、最多等几秒（2026-10-15）
    out = {}
    for t, r in rows.items():
        x = q.get(t)
        if not x:
            continue
        px = float(x["px"])
        out[t] = {"px": round(px, 2), "at": x.get("at"), "today": str(x.get("at") or "")[:10] == now.date().isoformat(),
                  "kind": r["kind"], "n": r["n"], "value": round(px * r["n"]),
                  "chg_pct": round((px / r["prev"] - 1) * 100, 2) if r["prev"] > 0 else None,
                  "pl_pct": round((px / r["cost"] - 1) * 100, 2) if r["cost"] > 0 else None}
        if r["kind"] != "suggest" and t in hnb:             # 今天有成交（对账前）：那句话；卖出全部的预计收益不给（成本 / 股数对账之后才对）
            out[t]["today_text"] = hnb[t]["text"]
        dm = _delay_min(x.get("at"), now)
        rg = MO.delay_range(_dvol(tag, t), dm) if dm is not None else None
        if rg is not None:                                   # 晚了几分钟 → 现在的价通常在 ±几 % 以内（估算）
            out[t].update(delay=round(dm), rng=rg)
        b = x.get("bar")
        if b:                                                # 今天到这个时刻为止的一根（K 线图并进去用；页面看 at 变了才重取图）
            out[t]["bar"] = {"d": b.get("d"), **{k: round(float(b[k]), 2) for k in ("o", "h", "l", "c")}, "v": int(b.get("v") or 0)}
        if r["kind"] == "suggest":                           # 建议的股票：现在买的限价（规则同一条：≤ 收盘 ×1.03；盘中 = min(现价 +0.5%, 上限)）
            sb = (sgr[t].get("buy") or {})
            top = float(sb.get("limit") or 0)
            lim = (min(top, round_to_tick(px * (1 + MO.NOW_BUY_BUF), t, "BUY")) if top > 0 else
                   round_to_tick(px * (1 + MO.NOW_BUY_BUF), t, "BUY"))
            out[t]["buy"] = {"cap": top or None, "lim": lim, "over": bool(top > 0 and px > top), "close": r["prev"] or None}
            continue
        est = None if t in hnb else MO.sell_estimate(book, t, px=px, at=x.get("at"), sm=sm)   # 卖出全部的预计收益（按这个现价）
        if est:
            out[t]["est"] = {**est, "lines": MO.est_lines(est, MO.sale_note(tag, now), MO.ytd_gain(book, now.date()))}
    return 200, {**head, "rows": out}


def _extra_of(query: str) -> list | None:
    """/api/quotes?…&t=7203.T,6758.T → 建议的股票的代码（格式不对的丢掉；没有 t → None = 持仓）。"""
    v = parse_qs(query).get("t")
    if not v:
        return None
    out = []
    for x in ",".join(v).split(","):
        x = x.strip().upper()
        if _CHART_T.fullmatch(x) and x not in out:
            out.append(x)
    return out[:SG_MAX * 2]


# ───────────────────────── HTTP ─────────────────────────
CSP = (f"default-src 'none'; script-src 'self' '{BOOT_SHA}'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; manifest-src 'self'; "
       "connect-src 'self'; worker-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")

# 网页 App 的 service worker（/sw.js）：① 页面与只读接口「网络优先、连不上用上次的」（Mac 睡着 / Tailscale 断了也能看上次的数据，
# 页面顶上会写是几分钟前的）② 收推送（qbreak/webpush.py）→ 系统通知；点通知打开面板。只缓存这个面板自己（同源 GET），写操作从不缓存。
# 2026-10-15 用户「qbreak网页app经常卡住 永久解决这个问题」（以前：没有超时、Tailscale Serve 的 502 原样显示 → 主屏幕 App 停在「刷新中…」/
# 白屏 / Bad Gateway，没有刷新键只能划掉重开）：
#   页面：网络 6 秒没回 / 5xx / 连不上 → 给存着的页面（标上 qb-cache：页面顶上写「连不上 Mac」、连上后自动刷新）或离线页（每 5 秒自动重试 +
#         大的「重新连接」）；网络晚到的照样存下（下一次用）。只存操作面板本身（X-Qbreak-Page: main），按账本存一份（不按 ?tab= 等存很多份）。
#   /static/…?v=：版本不变内容就不变 → 缓存优先（不再新旧模块混用）；页面换了新版本后删掉别的版本。
#   /api/quotes、/api/chart、/api/intraday：网络 12 秒没回 / 5xx → 存着的（标上 X-Qbreak-Cache：页面知道连不上）；最多存 40 条。
#   /api/status、/api/clientlog 不经这里（连接检查要看真的网络）。缓存名换了 → 旧缓存在 activate 时删掉。
SW_JS = r"""const C='qbreak-v4', NAV_MS=6000, NET_MS=25000, STATIC_MS=8000, API_MS=12000, API_MAX=40;
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k))))
  .then(()=>self.clients.claim())));
function tfetch(u,init,ms){ const ac=new AbortController(), t=setTimeout(()=>ac.abort(),ms);
  return fetch(u,Object.assign({},init||{},{signal:ac.signal})).finally(()=>clearTimeout(t)); }
function late(ms){ return new Promise(res=>setTimeout(()=>res(null),ms)); }
let PATIENT=0;                                           // 页面（conn.js）刚确认连得上 Mac、要刷新：下一次导航等网络到 NET_MS（页面生成得慢也拿新的，不换成存着的再来回刷新）
self.addEventListener('message',e=>{ if(e.data && e.data.qb==='patient'){ PATIENT=Date.now()+15000; if(e.ports && e.ports[0]) e.ports[0].postMessage(1); } });
function pageKey(u){ return new URL('/?qb-page='+encodeURIComponent(u.searchParams.get('book')||''),self.location).href; }
function marked(m,head){ const h=new Headers(m.headers); h.delete('Content-Length'); h.delete('Content-Encoding'); for(const k in head) h.set(k,head[k]); return h; }
function stale(m){ return m.text().then(t=>new Response(t.replace('<head>',"<head><meta name='qb-cache' content='1'>"),{status:200,headers:marked(m,{})})); }
function offline(url){                                   // 网址去掉 #tab=…（2026-10-15 复核：带着 # 时「重新连接」与 5 秒的自动刷新都只是同一页里跳锚点，一个请求都不发）
  const u=String(url).split('#')[0].replace(/[<>"']/g,'').replace(/&/g,'&amp;');
  return new Response('<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'+
    '<meta http-equiv=refresh content="5;url='+u+'"><title>qbreak</title><style>body{font:17px -apple-system,sans-serif;margin:0;padding:max(24px,env(safe-area-inset-top)) 20px 24px;'+
    'line-height:1.6;background:#f2f2f7;color:#111}@media (prefers-color-scheme:dark){body{background:#0f0f11;color:#eee}}'+
    'a{display:block;margin:24px 0 12px;padding:18px;border-radius:14px;background:#0a84ff;color:#fff;text-align:center;font-weight:600;text-decoration:none;font-size:19px}'+
    '.m{color:#888;font-size:14px}</style><h2>连不上 Mac 的面板</h2><p>Mac 睡着 / 关机 / 面板正在重启，或手机的 Tailscale 没连上；这台设备上还没有存过页面。</p>'+
    '<a href="'+u+'">重新连接</a><p class=m>每 5 秒自动重试一次，连上了就自动打开（不用划掉 App）。</p>',
    {headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}});
}
function prune(c,html){                                    // 页面换了新版本：删掉别的版本的 /static/
  const v=(html.match(/main\.js\?v=([0-9a-f]+)/)||[])[1]; if(!v) return;
  return c.keys().then(ks=>Promise.all(ks.filter(k=>{ const u=new URL(k.url); return u.pathname.indexOf('/static/')===0 && u.searchParams.get('v') && u.searchParams.get('v')!==v; })
    .map(k=>c.delete(k))));
}
function page(e,r,u){
  const key=pageKey(u);
  const net=tfetch(r.url,{credentials:'same-origin',cache:'no-store',redirect:'manual'},NET_MS).then(res=>{
    if(res.type==='opaqueredirect' || res.status<500){
      if(res.ok && res.headers.get('X-Qbreak-Page')==='main'){ const cp=res.clone();
        e.waitUntil(caches.open(C).then(c=>cp.clone().text().then(t=>c.put(key,cp).then(()=>prune(c,t)))).catch(()=>{})); }
      return res;
    }
    throw new Error('HTTP '+res.status);
  });
  e.waitUntil(net.catch(()=>null));
  const wait=Date.now()<PATIENT ? NET_MS : NAV_MS; PATIENT=0;
  return Promise.race([net.catch(()=>null),late(wait)]).then(res=>res ||
    caches.open(C).then(c=>c.match(key,{ignoreVary:true})).then(m=>m ? stale(m) : offline(r.url)).catch(()=>offline(r.url)));
}
function asset(e,r,u){
  return caches.open(C).then(c=>c.match(r.url,{ignoreVary:true}).then(m=>{
    if(m && u.searchParams.get('v')) return m;            // 带版本的：内容不会变
    return tfetch(r,{},STATIC_MS).then(res=>{ if(res.ok) e.waitUntil(c.put(r.url,res.clone()).catch(()=>{}));
      if(res.status>=500 && m) return m; return res; }).catch(()=>m || Response.error());
  }));
}
function api(e,r){                                        // 网络 12 秒没回 / 5xx → 存着的（标上 X-Qbreak-Cache）；没存过 → 原样（5xx）/ 出错
  const old=res=>caches.open(C).then(c=>c.match(r.url,{ignoreVary:true}))
    .then(m=>m ? new Response(m.body,{status:m.status,headers:marked(m,{'X-Qbreak-Cache':'1'})}) : (res || Response.error()), ()=>res || Response.error());
  return tfetch(r,{},API_MS).then(res=>{
    if(res.status>=500) return old(res);
    if(res.ok){ const cp=res.clone(); e.waitUntil(caches.open(C).then(c=>c.put(r.url,cp).then(()=>c.keys()).then(ks=>{
      const a=ks.filter(k=>new URL(k.url).pathname.indexOf('/api/')===0); return Promise.all(a.slice(0,Math.max(0,a.length-API_MAX)).map(k=>c.delete(k))); })).catch(()=>{})); }
    return res;
  },()=>old(null));
}
self.addEventListener('fetch',e=>{
  const r=e.request; if(r.method!=='GET') return;
  const u=new URL(r.url); if(u.origin!==self.location.origin) return;
  if(r.mode==='navigate'){ e.respondWith(page(e,r,u)); return; }
  if(u.pathname.indexOf('/static/')===0){ e.respondWith(asset(e,r,u)); return; }   // 页面的 JS / CSS 也缓存（离线时打开上次的页面要用）
  if(u.pathname==='/manifest.webmanifest' || u.pathname==='/apple-touch-icon.png'){ e.respondWith(asset(e,r,u)); return; }   // 连不上时用存着的（2026-10-15 复核：每次打开存着的页面都记「Manifest fetch failed」）
  if(u.pathname==='/api/quotes' || u.pathname==='/api/chart' || u.pathname==='/api/intraday') e.respondWith(api(e,r));
});
self.addEventListener('push',e=>{
  let d={}; try{ d=e.data?e.data.json():{}; }catch(x){ d={title:'qbreak', body:e.data?e.data.text():''}; }
  e.waitUntil(self.registration.showNotification(d.title||'qbreak',{body:d.body||'',data:{url:d.url||'/'},icon:'/apple-touch-icon.png',tag:d.tag||undefined}));
});
self.addEventListener('notificationclick',e=>{
  e.notification.close(); const url=(e.notification.data&&e.notification.data.url)||'/';
  e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(cs=>{
    for(const c of cs){ if('navigate' in c){ return c.navigate(url).then(w=>(w||c).focus()).catch(()=>c.focus()); } if('focus' in c) return c.focus(); }
    return self.clients.openWindow(url);
  }));
});
"""


_CLOG_HITS: list[float] = []
_CLOG_LOCK = threading.Lock()
CLOG_MAX = 30                                               # 页面报告每分钟最多记几条（两个端口一起）


def client_log(query: str, who: str) -> None:
    """GET /api/clientlog?e=种类&d=说明：页面自己报的「请求超时 / 连不上多久 / 用了存着的旧页面 / 脚本没载入成」→ 面板日志（WARNING）。
    2026-10-15「网页app经常卡住」：以前手机上卡住什么都不留，事后查不出是哪一步。不发给第三方；只记种类与简短说明（路径、错误名、秒数），
    控制字符去掉、截短，每分钟最多 CLOG_MAX 条。"""
    q = parse_qs(query)
    e = re.sub(r"[^0-9A-Za-z_\-]", "", str((q.get("e") or [""])[0]))[:24] or "?"
    d = re.sub(r"[\x00-\x1f\x7f]", " ", str((q.get("d") or [""])[0]))[:200]
    now_m = time.monotonic()
    with _CLOG_LOCK:
        _CLOG_HITS[:] = [x for x in _CLOG_HITS if now_m - x < 60] + [now_m]
        if len(_CLOG_HITS) > CLOG_MAX:
            return
    log.warning("页面报告（%s）：%s %s", who, e, d)


def push_post(path: str, body: dict, who: str) -> tuple[int, dict]:
    """推送的接口（本机与手机共用；手机要本人 + CSRF，本机要令牌 —— 调用方检查过）。"""
    from . import webpush as WP
    sub = body.get("sub") if isinstance(body.get("sub"), dict) else {}
    ep = str(body.get("endpoint") or sub.get("endpoint") or "")
    if path == "/api/push/subscribe":
        ok, msg = WP.subscribe(who, sub, who)
        if ok:
            log.info("推送：%s 打开了推送", who)
        return (200 if ok else 400), {"ok": ok, "msg": msg}
    if path == "/api/push/unsubscribe":
        WP.unsubscribe(ep)
        return 200, {"ok": True, "msg": "这台设备的推送已关掉"}
    s = WP.subs().get(WP.sub_id(ep))
    if not s:
        return 400, {"ok": False, "msg": "这台设备还没打开推送"}
    code = WP.send_one(s, "qbreak 测试推送", "能看到这条 = 推送通了：每个工作日 09:30 的自检（哪天没收到 → Mac 多半关机 / 睡着 / 断网）、"
                                           "成交、买入信号、HALT 都会这样通知你。")
    ok = code in (200, 201, 202)
    return (200 if ok else 502), {"ok": ok, "msg": "已发一条测试推送" if ok else f"推送服务没收下（HTTP {code}）：关掉推送再打开一次试试"}


class _Common(BaseHTTPRequestHandler):
    server_version = "qbreak-panel"

    def log_message(self, fmt, *args):                       # 不把请求逐条写进日志（页面每次刷新都会有）
        return

    def handle_one_request(self):
        """所有接口的总保护（2026-10-12 再发防止：处理里一出异常连接就断 → 手机经 Tailscale 看到 HTTP 502、以为没写成又点一次）：
        异常 → 记日志、回一个能读的 JSON / 文字（写入类的接口：可能已经写进去了 → 先确认、不要直接再点）。"""
        self._sent = False
        self._counted = None                                # 算进「正在处理的请求」了（POST = 写）：平滑重启 / 退出前等它做完
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception:                                   # noqa: BLE001
            log.exception("面板处理请求出错：%s %s", getattr(self, "command", "?"), urlparse(getattr(self, "path", "") or "").path)
            if self._sent:
                return
            path = urlparse(getattr(self, "path", "") or "").path
            try:
                if path.endswith("/api/request") or path.endswith("/api/halt"):
                    self._json(500, {"ok": False, "unsure": True,
                                     "msg": "面板内部出错（已记日志）：这次可能已经写进去了 —— 刷新后在「交易」的「手动指令」里确认，不要直接再点一次"})
                elif "/api/" in path:
                    self._json(500, {"ok": False, "msg": "面板内部出错（已记日志）：刷新后再试"})
                else:
                    self._text(500, "面板内部出错（已记日志）：刷新后再试")
            except Exception:                               # noqa: BLE001
                pass
        finally:
            if self._counted is not None:
                _INFLIGHT.leave(self._counted)
                self._counted = None

    def parse_request(self):
        ok = super().parse_request()
        if ok and getattr(self, "_counted", None) is None:   # 请求行读到了才算（空闲的预连接不算）
            self._counted = self.command == "POST"
            _INFLIGHT.enter(self._counted)
        return ok

    def _send(self, code: int, body: bytes, ctype: str, headers=(), cache: str = "no-store") -> None:
        self._sent = True
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict, headers=()) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", headers)

    def _text(self, code: int, msg: str) -> None:
        self._send(code, msg.encode("utf-8"), "text/plain; charset=utf-8")

    def _gz(self) -> bool:
        return "gzip" in str(self.headers.get("Accept-Encoding") or "")

    def _asset(self, name: str, query: str) -> None:
        """/static/<name>[?v=…]：启动时读好的那一份（STATIC）。带 ?v= 的只给版本对的（可以长期缓存；service worker 缓存优先）；
        版本不对 → 404（旧页面配新面板：页面的 boot.js 看到载入失败 → 重新载入）；不带 ?v=（以前存下的旧页面）→ 现在的、不让缓存。
        boot.js 例外：什么版本都给现在的（不让缓存；以前存下的、还引用 /static/boot.js?v=旧 的页面也有人接手；2026-10-15 复核）。"""
        v = (parse_qs(query).get("v") or [""])[0]
        if v and v != ASSET_V and name == "boot.js":
            v = ""
        if v and v != ASSET_V:
            self._send(404, "版本不对（面板刚更新）：重新载入页面".encode("utf-8"), "text/plain; charset=utf-8")
            return
        gz = self._gz()
        hdrs = [("Vary", "Accept-Encoding")] + ([("Content-Encoding", "gzip")] if gz else [])
        self._send(200, STATIC_GZ[name] if gz else STATIC[name], STATIC_TYPES[Path(name).suffix], hdrs,
                   cache="public, max-age=31536000, immutable" if v else "no-cache")

    def _static(self, path: str, query: str = "") -> bool:
        """不含任何数据的静态东西（图标、manifest）：不用配对也给（主屏幕图标要用）。"""
        if path == "/favicon.ico":
            self._send(204, b"", "text/plain")
        elif path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
            self._send(200, PP.touch_icon_png(), "image/png")
        elif path == "/sw.js":
            self._send(200, SW_JS.encode("utf-8"), "text/javascript; charset=utf-8", [("Service-Worker-Allowed", "/")])
        elif path.startswith("/static/") and path[8:] in STATIC:            # 页面的 JS / CSS（不含任何数据；不用配对也给）
            self._asset(path[8:], query)
        elif path == "/manifest.webmanifest":
            self._send(200, json.dumps(PP.MANIFEST, ensure_ascii=False).encode("utf-8"), "application/manifest+json; charset=utf-8")
        else:
            return False
        return True

    def _body(self, hits: list, limit: int = 30) -> dict | None:
        if not str(self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"ok": False, "msg": "只接受 JSON"})
            return None
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 < n <= MAX_BODY:
            self._json(413, {"ok": False, "msg": "请求太大"})
            return None
        now_m = time.monotonic()
        hits[:] = [x for x in hits if now_m - x < 60] + [now_m]
        if len(hits) > limit:
            self._json(429, {"ok": False, "msg": "太频繁了，过一分钟再试"})
            return None
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            assert isinstance(body, dict)
        except Exception:                                    # noqa: BLE001
            self._json(400, {"ok": False, "msg": "格式不对"})
            return None
        return body

    def _chart(self, query: str, now: dt.datetime | None = None) -> None:
        """GET /api/chart?book=…&t=…：一只票的 K 线（只读；本机端口看 Host，手机端口要你本人：按账户登录或已配对的设备）。"""
        t = str((parse_qs(query).get("t") or [""])[0]).strip().upper()
        if not _CHART_T.fullmatch(t):
            self._json(400, {"ok": False, "msg": "代码不对"})
            return
        code, obj = chart_json(_book_of(query), t, now)
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        hdrs = []
        if "gzip" in str(self.headers.get("Accept-Encoding") or "") and len(body) > 1024:
            body = gzip.compress(body, 6)
            hdrs = [("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding")]
        self._send(code, body, "application/json; charset=utf-8", hdrs)

    def _page(self, render_fn, kind: str = "main") -> None:
        """页面（kind：main = 操作面板 / pair = 配对页；X-Qbreak-Page 头：service worker 只把操作面板存成「连不上时给的旧页面」）。
        浏览器说收 gzip 就压（224 KB → 约 35 KB；2026-10-15：手机走 Tailscale 中继时整页重新下载很慢，看着像卡住）。"""
        try:
            html = render_fn()
        except Exception as e:                               # noqa: BLE001
            log.exception("面板页面出错")
            html = f"<!doctype html><meta charset='utf-8'><p>页面出错：{escape(type(e).__name__)}: {escape(str(e))[:300]}</p>"
            kind = "error"
        body = html.encode("utf-8")
        hdrs = [("X-Qbreak-Page", kind), ("Vary", "Accept-Encoding")]
        if self._gz() and len(body) > 1024:
            body = gzip.compress(body, 5)
            hdrs.append(("Content-Encoding", "gzip"))
        self._send(200, body, "text/html; charset=utf-8", hdrs)


def _book_of(query: str) -> str:
    """?book=… 的账本；没给 / 不认识 → 默认账本（B12：装了立花本番 → 立花；否则模拟账户；qbreak/paths.default_book）。"""
    tag = (parse_qs(query).get("book") or [""])[0]
    return tag if tag in BOOKS else paths.default_book()


def _halt_allin(msg: str) -> str:
    """HALT 之后（2026-10-13 resume-other-4）：「全部换成 X」同批卖单已在交易所、X 等开盘后补 → 回复里写明卖单照样成交、X 不会买。"""
    notes = []
    for t in books():
        if t in READONLY:
            continue
        try:
            n = MO.allin_halt_note(_load(t)[0])
        except Exception:                                   # noqa: BLE001 —— 提醒取不到不影响 HALT 本身
            n = None
        if n:
            notes.append(f"{BOOKS.get(t, t)}：{n}")
    return msg + ("；" + "；".join(notes) if notes else "")


def _after_submit(trigger, rec: dict | None) -> None:
    """写了买卖 / 撤回 / 闲置资金比例 → 马上看一次要不要叫执行器（盘中 → 马上下单；开盘前 → 重试加进今天的寄付单）。"""
    if trigger is not None and rec and rec.get("kind") in MO.ORDER_KINDS + ("cancel", "core", "cancel_order", "uncancel"):
        threading.Thread(target=trigger.check, daemon=True).start()


def make_handler(port: int, tok: str, trigger: Trigger | None = None, clock=None, phone_port=None):
    """本机端口（127.0.0.1:8765）：只接受本机的 Host；写操作要面板令牌。配对码在这里生成（只显示在 Mac 屏幕上）。
    phone_port：手机端口号（None = 没开）或者每次现问的函数（serve：手机端口晚些重试打开了也显示出来）。"""
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}
    hits: list[float] = []
    routes = ("/api/request", "/api/halt", "/api/pair/new", "/api/device/revoke", "/api/push/subscribe", "/api/push/unsubscribe",
              "/api/push/test")

    class H(_Common):
        def _host_ok(self) -> bool:
            if self.headers.get("Host") not in hosts:
                self._text(421, "只接受 127.0.0.1 / localhost")
                return False
            return True

        def do_GET(self):                                    # noqa: N802
            if not self._host_ok():
                return
            u = urlparse(self.path)
            if self._static(u.path, u.query):
                return
            if u.path == "/api/chart":
                self._chart(u.query, (clock or now_jst)())
                return
            if u.path == "/api/quotes":
                self._json(*quotes_json(_book_of(u.query), (clock or now_jst)(), extra=_extra_of(u.query)))
                return
            if u.path == "/api/status":
                self._json(*status_json(_book_of(u.query)))
                return
            if u.path == "/api/trade_room":                  # 今天还能买几次 / 卖几次（D6）
                self._json(*trade_room_json(_book_of(u.query), (clock or now_jst)(), trigger))
                return
            if u.path == "/api/intraday":                    # 盘中观测（只读结果文件；不取价）
                self._json(*intraday_json(_book_of(u.query), (clock or now_jst)()))
                return
            if u.path == "/api/clientlog":
                client_log(u.query, "Mac")
                self._send(204, b"", "text/plain")
                return
            if u.path == "/api/push/key":
                from . import webpush as WP
                self._json(200, {"ok": True, "key": WP.public_key()})
                return
            if u.path != "/":
                self._text(404, "没有这个页面")
                return
            phone = {"port": phone_port() if callable(phone_port) else phone_port, "url": PP.phone_url(), "devices": PP.devices(), "identity": PP.identity_state()}
            self._page(lambda: render(_book_of(u.query), tok, (clock or now_jst)(), mode="local", phone=phone, trigger=trigger,
                                      tab=(parse_qs(u.query).get("tab") or [None])[0]))

        def do_POST(self):                                   # noqa: N802
            if not self._host_ok():
                return
            path = urlparse(self.path).path
            if path not in routes:
                self._json(404, {"ok": False, "msg": "没有这个接口"})
                return
            org = self.headers.get("Origin")
            if org is not None and org not in origins:
                self._json(403, {"ok": False, "msg": "来源不对（只接受本机这个页面）"})
                return
            if not secrets.compare_digest(str(self.headers.get("X-Qbreak-Token") or ""), tok):
                self._json(403, {"ok": False, "msg": "令牌不对：刷新页面再试"})
                return
            body = self._body(hits)
            if body is None:
                return
            now = (clock or now_jst)()
            if path == "/api/request":
                ok, msg, rec = submit(body, now, source="panel")
                if ok:
                    log.info("面板写了手动指令 %s（%s）", rec["id"], body.get("book"))
                    _after_submit(trigger, rec)
                self._json(*_req_reply(ok, msg, rec))
            elif path == "/api/halt":
                ok, msg = PP.create_halt(body.get("reason"), "Mac 操作面板", now)
                self._json(200 if ok else 500, {"ok": ok, "msg": _halt_allin(msg) if ok else msg})
            elif path.startswith("/api/push/"):
                self._json(*push_post(path, body, "Mac"))
            elif path == "/api/pair/new":
                code, exp = PP.new_code()
                url = PP.phone_url()
                link = f"{url}pair?c={code}" if url else None
                self._json(200, {"ok": True, "code": PP.fmt_code(code), "expires": f"{dt.datetime.fromtimestamp(exp, JST):%H:%M}",
                                 "url": url, "qr": PP.qr_data_uri(link) if link else None,
                                 "msg": "配对码只显示在这台 Mac 的屏幕上"})
            else:
                ok = PP.revoke(str(body.get("id") or ""))
                self._json(200 if ok else 400, {"ok": ok, "msg": "已取消这台设备的配对" if ok else "没有这台设备"})
    return H


def _hostport(v: str | None) -> str:
    return PP.hostport(v)


def make_phone_handler(port: int, trigger: Trigger | None = None, clock=None):
    """手机端口（127.0.0.1:8766，Tailscale Serve 转过来）：要「你本人」—— 按 Tailscale 账户登录（qbreak/panel_phone.identity_for：
    127.0.0.1 连过来、路径带着 Serve 的路径密钥、Host 对、Tailscale-User-Login 正好是这台 Mac 登录的账户、明确打开着）或已配对的设备（cookie）；
    写操作还要 CSRF 令牌，Origin / Sec-Fetch-Site 必须是这个页面自己。Funnel（公开到互联网）来的请求一律拒绝。
    路由前先去掉路径密钥（Serve 转过来的是「/<路径密钥>/原来的路径」）。
    都不是的只看到输入配对码的页面。配对码不在这里生成，也不能取消别的设备（只在 Mac 上）。"""
    local = {f"127.0.0.1:{port}", f"localhost:{port}"}
    hits_pair: list[float] = []
    hits_post: list[float] = []
    funnel_warned = [0.0]                                                # Funnel 的警告每 10 分钟最多写一次日志（公开后会有大量扫描）

    class P(_Common):
        def _host_ok(self) -> bool:
            if self.headers.get(PP.TS_FUNNEL_H) is not None:              # Funnel（公开到互联网）来的：什么都不给
                if time.monotonic() - funnel_warned[0] > 600 or not funnel_warned[0]:
                    funnel_warned[0] = time.monotonic()
                    log.warning("手机端口：收到经 Tailscale Funnel（公开到互联网）来的请求 → 拒绝（qbreak 只用 Serve；"
                                "tailscale funnel status 看一下，关掉：tailscale funnel --https=443 off）")
                self._text(403, "不接受经 Tailscale Funnel（公开到互联网）来的请求：qbreak 只用 Serve（只在你的 tailnet 里）")
                return False
            h = str(self.headers.get("Host") or "").strip().lower()
            if h in local or PP.TS_HOST.match(h):
                return True
            self._text(421, "只接受 Tailscale 的地址（*.ts.net）")
            return False

        def _route(self) -> str:
            """去掉 Serve 加的路径密钥之后的路径（没带的原样：配对的设备照旧能用，按账户登录不算）。"""
            return PP.split_gate(self.path)[1]

        def _who(self) -> dict | None:
            """你本人：按 Tailscale 账户登录（不用配对）→ 否则已配对的设备 → 否则 None。"""
            return PP.identity_for(self.headers, self.client_address[0], self.path) or PP.device_for(self.headers.get("Cookie"))

        def _origin_ok(self) -> bool:
            sfs = self.headers.get("Sec-Fetch-Site")
            if sfs is not None and sfs.strip().lower() != "same-origin":
                self._json(403, {"ok": False, "msg": "来源不对（只接受这个页面自己）"})
                return False
            o = self.headers.get("Origin")
            if o is None:
                return True
            u = urlparse(o)
            allowed = {_hostport(self.headers.get("Host")), _hostport((self.headers.get("X-Forwarded-Host") or "").split(",")[0])} - {""}
            if u.scheme in ("https", "http") and _hostport(u.netloc) in allowed:
                return True
            self._json(403, {"ok": False, "msg": "来源不对（只接受这个页面自己）"})
            return False

        def do_GET(self):                                    # noqa: N802
            if not self._host_ok():
                return
            u = urlparse(self._route())
            if self._static(u.path, u.query):
                return
            if u.path not in ("/", "/pair", "/api/chart", "/api/quotes", "/api/status", "/api/trade_room", "/api/intraday", "/api/push/key",
                              "/api/clientlog"):
                self._text(404, "没有这个页面")
                return
            dev = self._who()
            if u.path in ("/api/chart", "/api/quotes", "/api/status", "/api/trade_room", "/api/intraday", "/api/push/key", "/api/clientlog"):
                if dev is None:
                    self._json(401, {"ok": False, "msg": "这台设备还没配对（或已被取消）"})
                elif u.path == "/api/clientlog":
                    client_log(u.query, "手机")
                    self._send(204, b"", "text/plain")
                elif u.path == "/api/push/key":
                    from . import webpush as WP
                    self._json(200, {"ok": True, "key": WP.public_key()})
                elif u.path == "/api/chart":
                    self._chart(u.query, (clock or now_jst)())
                elif u.path == "/api/status":
                    self._json(*status_json(_book_of(u.query)))
                elif u.path == "/api/trade_room":
                    self._json(*trade_room_json(_book_of(u.query), (clock or now_jst)(), trigger))
                elif u.path == "/api/intraday":
                    self._json(*intraday_json(_book_of(u.query), (clock or now_jst)()))
                else:
                    self._json(*quotes_json(_book_of(u.query), (clock or now_jst)(), extra=_extra_of(u.query)))
                return
            if dev is None:
                code = (parse_qs(u.query).get("c") or [""])[0] if u.path == "/pair" else ""
                self._page(lambda: pair_page(code), "pair")
                return
            if u.path == "/pair":
                self._send(303, b"", "text/plain", [("Location", "/")])
                return
            if dev.get("kind") == "ts":                                   # 按账户登录、这台设备也配对过 → 页面上可以取消它的配对
                paired = PP.device_for(self.headers.get("Cookie"))
                dev = dict(dev, paired=paired["name"]) if paired else dev
            self._page(lambda: render(_book_of(u.query), PP.csrf(dev["id"]), (clock or now_jst)(), mode="remote", device=dev,
                                      trigger=trigger, tab=(parse_qs(u.query).get("tab") or [None])[0]))

        def do_POST(self):                                   # noqa: N802
            if not self._host_ok():
                return
            path = urlparse(self._route()).path
            if path not in ("/api/pair", "/api/request", "/api/halt", "/api/unpair", "/api/push/subscribe", "/api/push/unsubscribe",
                            "/api/push/test"):
                self._json(404, {"ok": False, "msg": "没有这个接口"})
                return
            if not self._origin_ok():
                return
            if path == "/api/pair":
                body = self._body(hits_pair, limit=10)
                if body is None:
                    return
                ok, msg, ck = PP.pair(body.get("code"), body.get("name"), self.headers.get("User-Agent"))
                self._json(200 if ok else 400, {"ok": ok, "msg": msg}, [("Set-Cookie", PP.cookie_set(ck))] if ok else ())
                return
            dev = self._who()
            if dev is None:
                self._json(401, {"ok": False, "msg": "这台设备还没配对（或已被取消）：刷新页面重新配对"})
                return
            if not PP.csrf_ok(dev["id"], self.headers.get("X-Qbreak-Csrf")):
                self._json(403, {"ok": False, "msg": "令牌不对：刷新页面再试"})
                return
            body = self._body(hits_post)
            if body is None:
                return
            now = (clock or now_jst)()
            if path == "/api/request":
                ok, msg, rec = submit(body, now, source="phone")
                if ok:
                    log.info("手机（%s）写了手动指令 %s（%s）", dev["name"], rec["id"], body.get("book"))
                    _after_submit(trigger, rec)
                self._json(*_req_reply(ok, msg, rec))
            elif path == "/api/halt":
                ok, msg = PP.create_halt(body.get("reason"), f"手机 {dev['name']}", now)
                self._json(200 if ok else 500, {"ok": ok, "msg": _halt_allin(msg) if ok else msg})
            elif path.startswith("/api/push/"):
                self._json(*push_post(path, body, str(dev.get("name") or "手机")))
            elif dev.get("kind") == "ts":                                  # 按账户登录：这台设备也配对过才有东西可退
                paired = PP.device_for(self.headers.get("Cookie"))
                if paired:
                    PP.revoke(paired["id"])
                    self._json(200, {"ok": True, "msg": "已取消这台设备的配对（按 Tailscale 账户登录照常能用）"},
                               [("Set-Cookie", PP.cookie_clear())])
                else:
                    self._json(400, {"ok": False, "msg": "这是按 Tailscale 账户登录的（不用配对）：要改成只用配对，在 Mac 的 Claude 对话里说"
                                                         "「手机只用配对」（bash scripts/liveu.sh phone identity off）"})
            else:
                PP.revoke(dev["id"])
                self._json(200, {"ok": True, "msg": "已退出：这台设备要重新配对才能打开"}, [("Set-Cookie", PP.cookie_clear())])
    return P


def _mtimes() -> dict:
    base = Path(__file__).resolve().parent
    out = {}
    for n in list(WATCH) + [f"static/{f.name}" for f in sorted(STATIC_DIR.iterdir()) if f.suffix in STATIC_TYPES]:   # 页面的 JS / CSS 更新也重启（?v 才会变）
        try:
            out[n] = (base / n).stat().st_mtime
        except OSError:
            out[n] = None
    return out


WATCH_EVERY_S = 5.0                     # 多久看一次代码文件的修改时间
RESTART_STABLE_S = 10.0                 # 改了之后这么久没再变才重启（一次 git pull 改好几个文件只重启一次；不读写到一半的文件）
RESTART_DRAIN_S = 10.0                  # 重启 / 退出前等正在处理的请求做完：读的最多这么久
RESTART_DRAIN_WRITE_S = 30.0            # 有写指令 / HALT 正在处理：最多这么久（绝不在写的中途换进程）
TERM_DRAIN_S = (3.0, 10.0)              # 收到 SIGTERM（launchctl kickstart -k / unload）：读 / 写最多等几秒再退出（launchd 20 秒后强杀）
PHONE_RETRY_S = 2.0                     # 手机端口打不开（旧进程还占着等）：后台多久重试一次
PHONE_RETRY_FAST_FOR_S = 60.0           # 头这么久每 PHONE_RETRY_S 秒；之后每 PHONE_RETRY_SLOW_S 秒（一直试，开了就接上）
PHONE_RETRY_SLOW_S = 30.0


_PREFLIGHT_PY = r"""
import importlib, pathlib, re, sys
import qbreak.panel
pkg = pathlib.Path(qbreak.panel.__file__).parent
rx = re.compile(r"^[ \t]*from \.(\w*) import ([\w ,]+)", re.M)
todo, seen = ["panel"], set()
while todo:
    m = todo.pop()
    if m in seen:
        continue
    seen.add(m)
    try:
        importlib.import_module("qbreak." + m)
        src = (pkg / (m + ".py")).read_text(encoding="utf-8")
    except ModuleNotFoundError as e:
        if (e.name or "").split(".")[0] == "qbreak":
            raise
        continue
    except OSError:
        continue
    for a, names in rx.findall(src):
        for n in ([a] if a else [x.strip().split(" as ")[0].strip() for x in names.split(",")]):
            if n and ((pkg / (n + ".py")).exists() or (pkg / n / "__init__.py").exists()):
                todo.append(n)
print(len(seen))
"""


def _preflight() -> bool:
    """新代码起得来吗：另一个进程里 import qbreak.panel，再把它（与它用到的 qbreak 模块）在函数里才 import 的 qbreak 模块也 import 一遍
    （60 秒；2026-10-15 复核：以前只 import qbreak.panel，函数里才 import 的模块坏了照样换进来、页面 / 请求一用到就出错）。
    缺的不是 qbreak 自己的模块（可选的依赖）不算。起不来 → False（不重启、照旧用旧代码；以前直接退出 → 新代码起不来、面板就没了）。"""
    try:
        r = subprocess.run([sys.executable, "-c", _PREFLIGHT_PY], cwd=str(paths.PROJECT_ROOT), capture_output=True,
                           text=True, timeout=60, check=False)
    except Exception as e:                                   # noqa: BLE001  试不了 → 照旧重启（和以前一样）
        log.warning("面板的新代码没法先试（%s）：照旧重启", e)
        return True
    if r.returncode != 0:
        log.warning("面板的新代码 import 失败：不重启、继续用旧代码（修好之后再改到文件就会再试）\n%s", (r.stderr or "")[-800:])
        return False
    return True


def _watch_code(stop: threading.Event, srv, every: float = WATCH_EVERY_S, stable: float = RESTART_STABLE_S, preflight=None) -> None:
    """git pull 改了面板的代码 → 平滑重启（2026-10-15 用户「qbreak网页app经常卡住 永久解决这个问题」：以前每 60 秒看一次、一变就退出等 launchd
    重启 → 0.5〜1.8 秒连不上（手机经 Tailscale Serve 看到空的 502）、正在处理的现价 / K 线 / 写指令被切断；10-07〜10-15 启动了 61 次）：
    ① 文件 stable 秒没再变才动；② 先在另一个进程里试着 import 新代码（坏了 → 不重启、记日志）；③ srv.shutdown()（停止接新连接；
    监听端口不关，新连接在内核里排队）→ serve() 等正在处理的请求做完（写指令最多 30 秒）→ os.execv 换成新代码（同一个进程号、同一个监听端口：
    手机看不到 502，最多晚 1 秒左右）。"""
    base = _mtimes()
    bad = None                                               # import 失败的那一版：文件再变了才再试
    while not stop.wait(every):
        cur = _mtimes()
        if cur == base or cur == bad:
            continue
        last, since = cur, time.monotonic()
        while True:                                          # 等文件不再变
            if stop.wait(min(1.0, every)):
                return
            now_m = _mtimes()
            if now_m != last:
                last, since = now_m, time.monotonic()
            elif time.monotonic() - since >= stable:
                break
        if last == base:                                     # 改回去了
            continue
        if not (preflight or _preflight)():
            bad = last
            continue
        log.info("面板的代码更新了：平滑重启（监听端口不关；等正在处理的请求做完再换新代码）")
        print("面板的代码更新了（git pull）：平滑重启（同一个进程号；手机不会断）")
        srv.qb_restart = True
        srv.shutdown()
        return


class _Inflight:
    """正在处理的请求（两个端口一起算；write = POST）：平滑重启 / 收到 SIGTERM 时等它们做完再换进程 / 退出。"""

    def __init__(self):
        self.cv = threading.Condition()
        self.n = 0
        self.w = 0

    def enter(self, write: bool) -> None:
        with self.cv:
            self.n += 1
            self.w += 1 if write else 0

    def leave(self, write: bool) -> None:
        with self.cv:
            self.n -= 1
            self.w -= 1 if write else 0
            self.cv.notify_all()

    def drain(self, read_s: float, write_s: float) -> bool:
        """等到没有正在处理的请求（有写的最多 write_s 秒，只有读的最多 read_s 秒）→ True；等不到 → False。"""
        t0 = time.monotonic()
        with self.cv:
            while self.n > 0:
                left = t0 + (write_s if self.w > 0 else read_s) - time.monotonic()
                if left <= 0:
                    return False
                self.cv.wait(min(0.2, left))
        return True


_INFLIGHT = _Inflight()


class _Srv(ThreadingHTTPServer):
    """面板的 HTTP 服务器：等着接的连接多留一些（socketserver 默认 5：一下点开很多行、K 线 / 现价同时取时会在 TCP 层被拒，
    页面显示「K 线取不到」；2026-10-14 复核）。平滑重启时排队的连接也在这里等。"""
    request_queue_size = 64
    daemon_threads = True


FDS_ENV, TRIGGER_ENV = "QBREAK_PANEL_FDS", "QBREAK_PANEL_TRIGGER"   # 平滑重启（execv）交给新进程的：监听 socket 的 fd、自动叫执行器的状态


def _make_srv(port: int, handler, fd: int | None = None) -> _Srv:
    """监听 127.0.0.1:port。fd = 平滑重启前的进程留下的监听 socket（确认是 127.0.0.1:port 才接着用：端口一直没关，排队的连接照样接）；
    用不了 → 照常 bind。"""
    if fd is not None:
        try:
            sk = socket.socket(fileno=fd)
        except OSError as e:
            log.warning("平滑重启：接不上原来的监听 socket（fd %s：%s）：重新 bind", fd, e)
        else:
            try:
                ok = sk.type == socket.SOCK_STREAM and tuple(sk.getsockname()[:2]) == ("127.0.0.1", int(port))
            except OSError:
                ok = False
            if ok:
                os.set_inheritable(fd, False)
                srv = _Srv(("127.0.0.1", int(port)), handler, bind_and_activate=False)
                srv.socket.close()
                srv.socket = sk
                srv.server_address = sk.getsockname()
                srv.server_name, srv.server_port = "127.0.0.1", int(port)
                return srv
            sk.close()
    return _Srv(("127.0.0.1", int(port)), handler)


def _handoff() -> tuple[dict, dict | None]:
    """平滑重启前的进程留下的东西（从环境变量里拿掉：不传给执行器等子进程）→ ({端口: fd}, 自动叫执行器的状态 | None)。"""
    fds = {}
    for part in (os.environ.pop(FDS_ENV, "") or "").split(","):
        try:
            p_, f_ = part.split(":")
            fds[int(p_)] = int(f_)
        except ValueError:
            continue
    raw = os.environ.pop(TRIGGER_ENV, "")
    try:
        trg = json.loads(raw) if raw else None
    except ValueError:
        trg = None
    return fds, trg


def _reexec(servers: list, trg: "Trigger | None") -> None:
    """平滑重启：监听 socket 留给新进程（不关端口），os.execve 用同样的命令行换成新代码（同一个进程号：launchd 看不到退出、
    面板叫的执行器还是它的子进程）。成功不返回；失败 → 返回（调用方照旧关端口退出，launchd 重启）。"""
    env = dict(os.environ)
    try:
        env[FDS_ENV] = ",".join(f"{s.server_address[1]}:{s.socket.fileno()}" for s in servers if s is not None)
        for s in servers:
            if s is not None:
                os.set_inheritable(s.socket.fileno(), True)
        argv = [sys.executable] + list(getattr(sys, "orig_argv", [sys.executable] + sys.argv)[1:])
        for h in logging.getLogger("qbreak").handlers:
            h.flush()
        sys.stdout.flush()
        sys.stderr.flush()
        if trg is None:
            os.execve(sys.executable, argv, env)
        with trg.lock:                                       # 正在叫执行器的那一下做完再换（新进程接着管它）
            env[TRIGGER_ENV] = json.dumps(trg.export_state(), ensure_ascii=False)
            os.execve(sys.executable, argv, env)
    except Exception as e:                                   # noqa: BLE001
        log.warning("平滑重启没成（%s）：退出，让 LaunchAgent 用新代码重启", e)


def serve(port: int = 8765, open_browser: bool = False, trigger: bool = True, phone_port: int | None = PP.PHONE_PORT,
          intraday: bool = True) -> int:
    """在 127.0.0.1:port（本机）与 127.0.0.1:phone_port（手机，Tailscale Serve 用；0 = 不开）上运行（前台；LaunchAgent 用 KeepAlive 守着）。
    代码更新 → 平滑重启（_watch_code / _reexec）；SIGTERM → 等正在处理的请求做完再退出（launchd 重启）。
    trigger 且 intraday → 盘中观测的线程（_intraday_loop：交易时段每 5 分钟另起进程算一次；请求里从不取价）；测试 / 无头时 intraday=False 关掉。"""
    fds, tstate = _handoff()
    for p_ in [x for x in fds if x not in (int(port), int(phone_port or 0))]:   # 交过来但这次不用的端口（参数改了）：关掉
        try:
            os.close(fds.pop(p_))
        except OSError:
            pass
    tok = token()
    trg = Trigger() if trigger else None
    if trg is not None and tstate:
        trg.import_state(tstate)
    pbox: list = [None]                                      # 手机端口的服务（打开之后才有；重试的线程也会写 → plock）
    plock = threading.Lock()
    # 先开本机端口（打不开 = 旧进程还占着 → 退出、launchd 重启），再开手机端口：手机端口打不开不再一直没有（2026-10-15 复核：
    # 以前先开手机端口、打不开就整个进程都没有手机访问，要等下一次重启）→ 后台每 2 秒重试（1 分钟后每 30 秒），开了就接上
    srv = _make_srv(int(port), make_handler(int(port), tok, trg, phone_port=lambda: int(phone_port) if pbox[0] is not None else None),
                    fds.get(int(port)))
    stop, term = threading.Event(), threading.Event()

    def _phone_try(first: bool) -> bool:
        try:
            s_ = _make_srv(int(phone_port), make_phone_handler(int(phone_port), trg), fds.get(int(phone_port)) if first else None)
        except OSError as e:
            if first:
                log.warning("手机端口 127.0.0.1:%s 打不开（%s）：后台重试，本机面板照常", phone_port, e)
                print(f"★ 手机端口 127.0.0.1:{phone_port} 打不开（{e}）：后台重试，本机面板照常")
            return False
        with plock:
            if stop.is_set():                                # 正在退出：不再开
                s_.server_close()
                return True
            pbox[0] = s_
        threading.Thread(target=s_.serve_forever, daemon=True).start()
        if not first:
            log.info("手机端口 127.0.0.1:%s 重试后打开了", phone_port)
        return True

    def _phone_retry() -> None:
        t0 = time.monotonic()
        while not stop.wait(PHONE_RETRY_S if time.monotonic() - t0 < PHONE_RETRY_FAST_FOR_S else PHONE_RETRY_SLOW_S):
            if _phone_try(False):
                return
    if phone_port and not _phone_try(True):
        threading.Thread(target=_phone_retry, daemon=True).start()

    def _on_term(signum, frame):                             # launchctl kickstart -k / unload：等正在处理的请求做完再退出
        if not term.is_set():
            term.set()
            threading.Thread(target=srv.shutdown, daemon=True).start()
    try:
        signal.signal(signal.SIGTERM, _on_term)
    except ValueError:                                       # 不在主线程（测试）：照旧
        pass
    if trg is not None:
        threading.Thread(target=trg.loop, args=(stop,), daemon=True).start()
        if intraday:                                         # 盘中观测（2026-10-16；没有单独的 LaunchAgent：面板在跑才算）
            threading.Thread(target=_intraday_loop, args=(stop,), daemon=True).start()
    threading.Thread(target=_watch_code, args=(stop, srv), daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"操作面板：{url}（只在本机；Ctrl-C 结束）"
          + (f"；手机端口 127.0.0.1:{phone_port}（Tailscale Serve 用；按 Tailscale 账户登录或配对）" if pbox[0] is not None else "")
          + ("（平滑重启：接着用原来的端口）" if fds else ""))
    log.info("操作面板启动 %s%s%s", url, f"（手机端口 {phone_port}）" if pbox[0] is not None else "", "（平滑重启）" if fds else "")
    if open_browser and not fds:
        try:
            subprocess.run(["open", url], timeout=20, capture_output=True, check=False)
        except Exception:                                    # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with plock:
            stop.set()                                       # 之后重试的线程不再开手机端口
            psrv = pbox[0]
        if psrv is not None:
            psrv.shutdown()
        restart = bool(getattr(srv, "qb_restart", False)) and not term.is_set()
        if not restart:                                      # SIGTERM / Ctrl-C：先关监听（排队的连接马上被拒、浏览器 / Serve 马上重试，
            for s_ in (srv, psrv):                           # 不干等到下面的 drain 做完；新进程也能马上 bind）。平滑重启不关（交给新进程）
                if s_ is not None:
                    try:
                        s_.socket.close()
                    except OSError:
                        pass
        if restart or term.is_set():
            rs, ws = (RESTART_DRAIN_S, RESTART_DRAIN_WRITE_S) if restart else TERM_DRAIN_S
            if not _INFLIGHT.drain(rs, ws):
                log.warning("%s：还有 %d 个请求没做完（等了 %.0f 秒）", "平滑重启" if restart else "退出", _INFLIGHT.n, ws if _INFLIGHT.w else rs)
        if restart:
            _reexec([srv, psrv], trg)                        # 成功就不回来了
        if psrv is not None:
            psrv.server_close()
        srv.server_close()
    return 0


__all__ = ["serve", "render", "pair_page", "submit", "token", "Trigger", "make_handler", "make_phone_handler", "BOOKS"]
