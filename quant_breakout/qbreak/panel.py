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
  POST /api/request             写一条手动指令（qbreak/manual_orders.py；与 run.py manual 相同的检查）
  POST /api/halt                建 HALT（只能建、不能解除；解除只在 Mac 上、用户明确说）
  本机才有：POST /api/pair/new（生成配对码）、/api/device/revoke（取消一台设备）；手机才有：/api/pair、/api/unpair（退出这台设备）
按钮只写指令：下单永远是执行器（HALT / ARM / 持仓核对 / 单笔上限 / 资格检查照常）。什么时候下单（qbreak/manual_orders.py；
2026-10-07 用户：「当天买入卖出的话在交易时间段就直接进行买入卖出 在交易时间之前的话就等交易时间的时候进行交易」）：
  盘中（09:00〜11:30、12:30〜15:25）→ 面板马上叫执行器跑 bash scripts/liveu.sh run --broker … --phase now（同一个账本最多 1 分钟一次）；
  交易日 07:45〜08:50、今天早上的运行已经完成、有新的卖出 / 调仓往下 / 撤回 → 叫一次重试（--retry，最多 3 分钟一次）→ 今天开盘的寄付单；
  开盘前的买入 / 加仓 → 09:00 开盘后由 --phase now 下；收盘后点的 → 下一个交易日 07:40 的运行。
安全：只绑 127.0.0.1；Host 头：本机端口只接受 127.0.0.1 / localhost，手机端口只接受 *.ts.net（挡 DNS rebinding）；写操作要
  ① 令牌（本机）/ 设备 cookie + CSRF 令牌（手机）② 自定义头（跨站表单发不出）③ Origin（有的话）必须是这个页面自己
  ④ application/json、≤ 4 KB ⑤ 每分钟最多 30 次（配对 10 次）。不读立花的认证信息、不连立花、不下单；页面禁止被嵌入。
代码更新（git pull）之后面板自己退出，LaunchAgent 用新代码重启。
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import math
import os
import re
import secrets
import subprocess
import threading
import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import core_exit as CX
from . import dip_stats as DS
from . import kline as KL
from . import manual_orders as MO
from . import panel_phone as PP
from . import paths
from . import suggest as SG
from . import watch_prob as WP
from .calendar_jp import JST, is_trading_day, now_jst
from .fees import BROKERS as _BROKERS, DEFAULT_BROKER as _DEFAULT_BROKER
from .tick import round_to_tick
from .utils import read_json, setup_logging

log = setup_logging("panel")

BOOKS = {"paper": "模拟账户", "tachibana": "立花（本番）", "tachibana_demo": "立花デモ", "tachibana_dryrun": "立花 dry-run（只读）"}
READONLY = {"tachibana_dryrun"}            # dry-run 的账本：只看（〔77〕C UX-15），面板不写指令
MAX_BODY = 4096
TRIGGER_FROM, TRIGGER_UNTIL = dt.time(7, 45), dt.time(8, 50)
TRIGGER_GAP_S = 180                     # 开盘前的重试：同一个账本最多 3 分钟一次
NOW_GAP_S = 60                          # 盘中（--phase now）：同一个账本最多 1 分钟一次
FAIL_GAP_MAX_S = 900                    # 盘中执行器失败后的退避：NOW_GAP_S × 2^连续失败次数，最多 15 分钟
FAIL_PAUSE_N = 3                        # 同一天连续失败几次 → 当天这个账本暂停自动叫执行器（新的手动指令 / 第二天恢复）
TOKEN_FILE = "panel_token"
WATCH = ("panel.py", "panel_phone.py", "manual_orders.py", "money_view.py", "broker_snapshot.py", "tax_ytd.py", "live_gate.py", "holding_view.py", "kline.py", "suggest.py", "watch_prob.py", "core_exit.py",
         "idle_cash.py", "dip_stats.py", "run_status.py", "precheck.py", "calendar_jp.py",
         "paths.py", "live_unified.py")         # 默认账本 / ARM 判定（paths）、数据依赖的提醒文字（live_unified）


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
JS_MODULES = ("net", "core", "trade", "kline", "quotes", "app")   # main.js 按这个顺序引入；pair.js 是配对页的


def _static_files() -> dict[str, bytes]:
    return {f.name: f.read_bytes() for f in sorted(STATIC_DIR.iterdir()) if f.suffix in STATIC_TYPES}


ASSET_V = __import__("hashlib").sha1(b"".join(_static_files().values())).hexdigest()[:10]   # 引用时加 ?v=（代码更新后不用旧的）
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
            "<div class='row'><button class='btn' data-act='close'>取消</button><button class='btn primary' id='ask-ok' data-act='ask-ok'>确定</button></div>"
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


GROUPS = (("triggered", "今天出了买入信号"), ("imminent", "快要出买入信号"), ("watch", "观察中"))
RANK_GROUPS = (("triggered", "今天出了买入信号"), ("rest", "观察中"))


SG_PAGE = 5                               # 一组先显示几只（其余点「再显示」）


NOTIFY_SHOW_H = 24                                          # 「消息 → 通知记录」只显示最近几小时发出的
NEWS_SHOW_H = 24                                            # 「消息」的经济威胁消息只显示最近几小时发布的
MANUAL_SHOW_DAYS = 2                                        # 「交易」的手动指令：已经处理完的只显示最近几天
AUTO_NEAR_DAYS = 5                                          # 「快要出」列到几个交易日以内的估计金叉


def _auto_buy_card(sg: dict, book: dict, tag: str, eq) -> str:
    """选股最上面（2026-10-12 用户：「将会按照规则自动进行购买的股票，大概几天后」）：
    ① 已经出了信号的：规则已安排（哪天开盘、几股）/ 信号成立但不买（为什么）；② 估计 AUTO_NEAR_DAYS 个交易日内 MACD 金叉的：
    大概哪天、出了信号的话下一个交易日开盘买约几股（按现在的新仓倍数）、历史上 10 个交易日内真的出信号的比例（大多很低）。
    只是规则的展示与估算，不是建议；金叉之外还要量等条件凑齐，出了信号还要过闸门 / 名额。"""
    from .calendar_jp import next_trading_day
    rows = [r for r in (sg or {}).get("rows") or [] if r.get("ticker")]
    if not rows:
        return ""
    s = MO.slots(book, tag)
    asof = _date_or_none(sg.get("asof"))
    fill = _date_or_none(sg.get("fill_day"))
    trig = [r for r in rows if r.get("status") == "triggered"]
    blocks = ((book or {}).get("manual") or {}).get("blocks") or {}
    freed = MO.lifting(tag, book)

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
        if t in freed:
            return "解除中"
        u, gc = blocks[t].get("until"), gc_day(r)
        return f"{str(u)[5:10].replace('-', '/')} 解除后" if u is not None and gc is not None and gc.isoformat() > str(u) else None

    def keep(r) -> bool:
        b = r.get("buy") or {}
        return not b.get("block") or man_wait(r) is not None
    near = sorted((r for r in rows if r.get("status") != "triggered" and (r.get("near") or {}).get("where") == "below_up"
                   and int((r.get("near") or {}).get("days") or 99) <= AUTO_NEAR_DAYS and keep(r)),
                  key=lambda r: (int(r["near"]["days"]), -float((r.get("prob") or {}).get("p") or 0)))

    def name(r):
        return f"<b>{escape(str(r.get('code') or r['ticker']))}</b> {escape(str(r.get('name') or ''))}"

    def est_shares(r):
        b = r.get("buy") or {}
        px, em, lot = float(b.get("px") or r.get("close") or 0), float(b.get("em") or 0), int(b.get("lot") or 100)
        if not (px > 0 and eq and em > 0):
            return 0
        return int(eq * CX.POS_PCT * min(1.0, em) / (px * 1.03) / lot) * lot
    H = ["<section class='card' id='autobuy'><h2>规则接下来会自动买</h2>",
         f"<div class='muted small'>按 {escape(str(sg.get('asof') or '—'))} 收盘。个股名额空 {s['free']} 个（上限 {s['max']} 只）。"
         "只是规则的展示与估算，不是建议。</div>"]
    if trig:
        H.append("<h3 class='sgh'>已经出了买入信号</h3><div class='list'>")
        for r in trig:
            ru = r.get("rule") or {}
            ok = ru.get("state") in ("planned", "manual")
            H.append(f"<div class='li'><span class='abd{' on' if ok else ''}'>{'下个开盘' if ok else '不买'}</span>"
                     f"<div class='grow'>{name(r)}<div class='small{'' if ok else ' muted'}'>{escape(str(ru.get('text') or ''))}</div></div></div>")
        H.append("</div>")
    if near:
        sh_all = {r["ticker"]: est_shares(r) for r in near}
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
            gc = gc_day(r)
            p = (r.get("prob") or {}).get("p")
            sh = sh_all[r["ticker"]]
            miss = (r.get("near") or {}).get("miss") or []
            tag_ = ("<span class='chip'>名额满</span>" if s["free"] <= 0 else "<span class='chip'>买不起</span>" if sh <= 0
                    else f"<span class='chip hot'>约 {sh:,} 股</span>")
            mw = man_wait(r)
            if mw:                                          # 现在还在「不买回」里：到期 / 解除之后才可能买
                tag_ += f"<span class='chip'>{escape(mw)}</span>"
            sub = " · ".join(x for x in (f"约 {gc:%m/%d} 金叉" if gc else "", f"历史出信号 {float(p) * 100:.0f}%" if p is not None else "",
                                         f"还差 {len(miss)} 个条件" if miss else "") if x)
            H.append(f"<div class='li'><span class='abd'>约 {n} 天</span><div class='grow'>{name(r)} {tag_}"
                     f"<div class='muted small'>{escape(sub)}</div></div></div>")
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


def _unblock_confirm(book: dict, tag: str, ts: list[str], what: str, selling: list[str]) -> str:
    """「恢复按规则」/「解除」的确认（2026-10-13：一点一行，说清解除之后不会怎样、什么时候、还要过什么）。"""
    st, man = (book or {}).get("state") or {}, (book or {}).get("manual") or {}
    s = MO.slots(book, tag)
    many = len(ts) > 1
    L = [f"只解除{what}的「不自动买回」" + (f"（{'、'.join(t.split('.')[0] for t in ts)}）" if many else "") + "。",
         f"不会把{'它们' if many else '它'}买回来，也不会马上买。",
         f"{MO.NEXT_DECISION}，规则重新判断：只有那次决策看的那根 K 线出买入信号（MACD 金叉）才可能买；已经判断过的信号不会再用。",
         f"买入还要有空名额（现在空 {s['free']} 个，上限 {s['max']} 只）、现金（账本现金 {_yen(float(st.get('cash_jpy') or 0))}）、"
         "过资格检查 / 决算前 / 宏观。"]
    if MO.core_pct_now(tag, book) <= 0 or man.get("core_pause"):
        L.append("闲置资金 ETF 仍停买（0%，要另外点「确认买入」）；这批取消的固定口数不会恢复。")
    if selling:
        L.append(f"还没成交的卖出（{'、'.join(t.split('.')[0] for t in selling)}）不会撤：要停就用「撤回」/「撤单」。")
    return "\n".join(L)


def _blocks_card(book: dict, tag: str, bl: dict, tlabel) -> str:
    """「交易」的「手动卖出后不自动买回」：「全部换成 X」按批一行（「恢复按规则」= 只解除这一批）+ 每只一行（「解除」）；
    按钮带着页面看到的设定 id（设定换了 / 已经解除 → 不写；2026-10-13）。在解除的（还没读 / 等下一次决策）不给按钮。"""
    lift = MO.lifting(tag, book)
    pos = ((book or {}).get("state") or {}).get("pos") or {}
    paused = MO.core_pct_now(tag, book) <= 0 or bool(((book or {}).get("manual") or {}).get("core_pause"))

    def md(v) -> str:
        return str(v or "")[5:10].replace("-", "/") or "—"

    def bid(v) -> str:                                      # 设定的 id（格式不对的旧数据：不带 → 只按代码解除）
        v = str(v or "")
        return v if re.fullmatch(r"M[0-9A-Za-z_.\-]{1,80}", v) else ""
    rows = []
    for g in MO.batch_blocks(book):                          # 「全部换成 X」卖掉的：一批一次「恢复按规则」（2026-10-13 用户）
        mem = g["members"]
        names = "、".join(tlabel(m["t"]) + ("（解除中）" if m["t"] in lift else "" if m["state"] == "sold" else f"（{m['state']}）") for m in mem)
        until = MO.block_text({"until": g["until"]})
        todo = [m for m in mem if m["t"] not in lift]
        sell = [m["t"] for m in todo if m["state"] != "sold"]
        if todo:
            msg = _unblock_confirm(book, tag, [m["t"] for m in todo], f"「全部换成 {tlabel(g['x'])}」这一批", sell)
            btn = (f"<button class='btn sm' data-act='unblock-batch' data-ids='{escape(','.join(m['t'] + (':' + bid(m['id']) if bid(m['id']) else '') for m in todo))}'"
                   f" data-x='{escape(tlabel(g['x']))}' data-msg='{escape(msg)}'>恢复按规则</button>")
        else:
            btn = "<span class='chip'>解除中（下一次决策起）</span>"
        rows.append(f"<div class='li'><div class='grow'><b>「全部换成 {escape(tlabel(g['x']))}」（{md(g['at'] or g['since'])}）卖出的</b> "
                    f"<span class='muted'>{escape(names)}</span><div class='muted small'>{escape(until)}"
                    "；点「恢复按规则」= 只解除这一批（不买回、也不马上买）" + ("；闲置资金 ETF 不跟着恢复（仍停买）" if paused else "")
                    + "</div></div>" + btn + "</div>")
    for t, b in bl.items():
        if t in lift:
            btn = "<span class='chip'>解除中（下一次决策起）</span>"
        else:
            msg = _unblock_confirm(book, tag, [t], f" {tlabel(t)} ", [t] if t in pos else [])
            btn = (f"<button class='btn sm' data-act='unblock' data-t='{escape(t)}' data-id='{escape(bid(b.get('id')))}'"
                   f" data-msg='{escape(msg)}'>解除</button>")
        rows.append(f"<div class='li'><div class='grow'><b>{escape(tlabel(t))}</b> <span class='muted'>{escape(MO.block_text(b))}</span></div>"
                    + btn + "</div>")
    return ("<section class='card' id='blocks'><h2>手动卖出后不自动买回</h2><div class='muted small'>到期 / 解除之前规则和手动都不买这几只；"
            f"解除 = {escape(MO.NEXT_DECISION)}（不会买回，也不马上买）</div><div class='list'>" + "".join(rows) + "</div></section>")


def _date_or_none(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _suggest_card(sg: dict, book: dict, tag: str, buying: set, when: str, eq, cap: float, chart, marks: dict | None = None) -> str:
    """「建议的股票」= 规则的候选（qbreak/suggest.py；全部列出）+ 每只的「买入…」（写手动买入指令；执行器下单前再查一遍）。
    有比例表（var/watch_prob.json，登记研究判定 A）→ 出了信号 / 其余一组（闸门 → 之后 10 个交易日内出买入信号的历史比例 → near_key），
    每只写第几、历史比例；没有 → 以前的 出了信号 → 快要出 → 观察中（按离买入信号的远近）。"""
    tab = WP.load()
    rows = SG.rank([dict(r) for r in (sg.get("rows") or [])], tab or {})   # 旧汇总没有 prob 也在这里补上（更新代码后不用等执行器）
    ranked = bool(tab)
    s = MO.slots(book, tag)
    blocks = ((book or {}).get("manual") or {}).get("blocks") or {}
    freed = {t: "「不自动买回」在解除：" + MO.NEXT_DECISION for t in MO.lifting(tag, book)}   # 不买回在解除 / 已经没了 → 手动买入不挡
    freed.update({r["ticker"]: "「不自动买回」已经到期 / 解除（这里是上一次决策时的结果）" for r in rows
                  if r.get("ticker") not in blocks and _man_block(r.get("buy"))})
    for r in rows:
        if _man_block(r.get("buy")) and r.get("ticker") in blocks:
            r["buy"] = {**r["buy"], "block_until": blocks[r["ticker"]].get("until")}
    marks = _news_marks([r["ticker"] for r in rows]) if marks is None else marks
    H = [f"<section class='card' id='suggest'><h2>建议的股票（规则的候选，{len(rows)} 只）</h2>"
         f"<div class='muted small'>按 {escape(str(sg.get('asof') or '—'))} 收盘。不是收益预测，也不是建议；点「买入…」→ {escape(when)}下单。</div>"
         f"<div class='small'>个股名额：空 {s['free']} 个（拿着 {s['held']} + 排定买入 {s['buys']}，上限 {s['max']} 只）</div>"]
    if sg.get("error"):
        H.append(f"<div class='neg small'>★ 这次没算成：{escape(str(sg['error']))}</div>")
    if not rows:
        H.append("<div class='muted'>" + ("候选在执行器下一次运行之后显示" if not sg else "今天没有出信号 / 快要出信号 / 观察中的票") + "</div></section>")
        return "".join(H)
    h = int((tab or {}).get("h") or WP.H)
    groups = []
    for g, title in (RANK_GROUPS if ranked else GROUPS):
        grp = [r for r in rows if r.get("status") != "triggered"] if g == "rest" else [r for r in rows if r.get("status") == g]
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
        if g == "rest":                                     # 快要出 + 观察中一组：按出买入信号的可能性排
            H.append(f"<h3 class='sgh'>观察中 · {len(grp)} 只（按离 MACD 金叉的天数排）</h3>"
                     f"<div class='muted small'>越上面越快出现金叉（按最近一天的变化估算的天数；同样天数时快要出的、历史比例高的在前；"
                     "已经在信号线上 / 还在往下走的排在后面，闸门挡的最后）。金叉之外还要横盘、量等条件凑齐才出买入信号，"
                     "出了信号还要过闸门 / 名额才会买。</div>")
        else:
            H.append(f"<h3 class='sgh'>{escape(title)}（{len(grp)} 只）</h3>")
            if g != "triggered" and any(r.get("near") for r in grp):
                H.append("<div class='muted small'>按离 MACD 金叉的天数排（越上面越快金叉；只是估算）</div>")
        for k, r in enumerate(grp, 1):
            row = _suggest_row(r, s, buying, eq, chart, rank=k if g == "rest" else None, fill=sg.get("fill_day"),
                               mark=marks.get(str(r["ticker"])), freed=freed)
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
                 mark: dict | None = None, freed: dict | None = None) -> str:
    t, b, ru = str(r["ticker"]), r.get("buy") or {}, r.get("rule") or {}
    nm = f" {escape(str(r['name']))}" if r.get("name") else ""
    meta = [f"条件凑齐 {r['score']:g} / 100" if r.get("score") is not None else None,
            f"收盘 ¥{r['close']:,.0f}" if r.get("close") is not None else None,
            f"量 {r['vol_ratio']:.2f} 倍" if r.get("vol_ratio") is not None else None,
            "真突破" if r.get("breakout") else None]
    tag_ = ("<span class='chip hot'>快要出</span>" if r.get("status") == "imminent" else "") if rank else ""
    nr = r.get("near") or {}
    if r.get("status") != "triggered" and nr.get("where"):                # 离金叉（2026-10-11 用户：按离金叉的临近日排序）
        gd = int(nr.get("days") or SG.MAX_DAYS)
        tag_ += ("<span class='chip gc'>" + (f"金叉约 {gd} 天" if nr["where"] == "below_up" and gd < SG.FAR_DAYS
                                             else "金叉还远" if nr["where"] == "below_up" else "要先拐头" if nr["where"] == "below_down"
                                             else "已在线上" if nr["where"] == "above" else "金叉算不出") + "</span>")
    H = [f"<div class='hv sg'><div class='head'>" + (f"<span class='rk'>{rank}</span>" if rank else "")
         + f"<b>{escape(str(r.get('code') or t))}</b>{nm}"
         + (f"<span class='chip'>{escape(str(r['sector']))}</span>" if r.get("sector") else "") + tag_ + "</div>"
         + _news_mark(mark)                                 # 消息的影响（2026-10-11 用户）
         + _prob_line(r.get("prob") if rank else None)
         + f"<div class='meta'>{' · '.join(x for x in meta if x)}</div>"
         + (f"<div class='small near'>{escape(str(r['near_text']))}</div>" if r.get("near_text") else "")   # 离买入信号还差什么（排序依据）
         + (f"<div>{escape(_fill_mult_why(str(ru.get('text') or '')))}</div>" if ru.get("state") not in (None, "none") else "")
         + tchips(r.get("trend"), stats=True)
         + (f"<div class='small neg'>★ 顶部风险：{escape(str(r['top_risk']))}</div>" if r.get("top_risk") else "")]
    n, px, lot = int(b.get("rule_shares") or 0), float(b.get("px") or 0), int(b.get("lot") or MO.LOT)
    why = None
    lifted = _man_block(b) and t in (freed or {})           # 不买回在解除 / 已经没了：手动买入不挡（执行器下单前按最新的再查；2026-10-13）
    if _man_block(b) and not lifted:                        # 与资格检查分开写（2026-10-13）
        u = b.get("block_until")
        why = f"手动卖出后不买回（可在「交易」解除）：{'到 ' + str(u) if u else '一直，直到解除' if 'block_until' in b else b['block']}"
    elif b.get("block") and not lifted:
        why = f"不能买：{b['block']}"
    elif t in buying:
        why = "有一条买入指令在处理（见「手动指令」）"
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
    H.append(f"<details class='kl'{' open' if r.get('status') in ('triggered', 'imminent') else ''}>"
             f"<summary>K 线 · 现价</summary><div class='qt small' data-sq='{escape(t)}'{planned}></div>{chart(t, 'suggest')}</details></div>")
    return "".join(H)


ALLOC_COLORS = ("#4c7bf3", "#f0a030", "#9b6cf0", "#20a8a0", "#e5c53a", "#e870b0", "#a07850", "#6aa8e8")   # 不用红 / 绿（红涨绿跌另有含义）


def _alloc_card(book: dict | None, hv: dict | None) -> str:
    """持仓最上面的「仓位占比」（2026-10-12 用户：每个仓位占多少，用线性 / 扇形一眼看出来）：一条按金额分段的横条 + 每只一行
    （颜色点、代码名称、占比、金额）；现金灰色放最后。按最近收盘估算（与「从持仓平摊凑」同一份数字）。没有持仓 → 空。"""
    st = (book or {}).get("state") or {}
    hold = MO.fund_holdings(book)["hold"]
    names = {r.get("ticker"): r.get("name") for r in ((hv or {}).get("holdings") or []) + ((hv or {}).get("core") or [])}
    items = [(h["t"], names.get(h["t"]) or "", h["cur"] * h["px"], h["kind"]) for h in hold if h["cur"] > 0 and h["px"] > 0]
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
    bar = "".join(f"<i style='width:{v / total * 100:.2f}%;background:{c}' title='{escape(t)} {v / total * 100:.1f}%'></i>"
                  for t, _n, v, _k, c in rows)
    legend = "".join(
        f"<div class='alr'><span class='ald' style='background:{c}'></span>"
        f"<span class='aln'><b>{escape(t.replace('.T', ''))}</b>{(' ' + escape(str(n).split('（')[0])) if n else ''}{' · ETF' if k == 'core' else ''}</span>"
        f"<span class='alp'>{v / total * 100:.1f}%</span><span class='aly muted'>{_yen(v)}</span></div>"
        for t, n, v, k, c in rows)
    return (f"<section class='card' id='alloc'><div class='head'><b>仓位占比</b><span class='muted small'>合计 {_yen(total)} · 按最近收盘</span></div>"
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
    --resolve 登记之后马上消失）、交易日 08:00 之后今天早上的运行还没完成、今天 09:30 自检没通过（out/watchdog_<账本>.json）、
    最后一次外部心跳没发成（同一个文件的 heartbeat）。
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
            out.append(("neg", f"★ 执行器 {escape(when)} 停下：{escape(str(rec.get('error') or '原因不明（看数据目录 logs/ 的 .err）'))}"))
        else:
            out.append(("muted", f"执行器：{escape(when)} 跑完 ✓（{escape(RS.PHASE_TEXT.get(rec.get('phase'), str(rec.get('phase') or '')))}）"))
        if rec.get("blocked"):
            day = "今天" if is_today else f"{when[:5]} "
            out.append(("neg", f"★ {escape(day)}的单没下：{escape(str(rec['blocked']))}"))
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
            f"{o['ticker']} {'买' if o['side'] == 'BUY' else '卖'} {o['qty']:,} {'口' if o['kind'] == 'core' else '股'}"
            for o in sending))))
    if bad:
        out.append(("neg", f"★ 有 {len(bad)} 笔被挡 / 被拒 / 状态不明（{escape(RS.bad_text(bad))}）："))
        for o in bad:
            unit = "口" if o["kind"] == "core" else "股"
            out.append(("neg", escape(f"・{o['ticker']} {'买' if o['side'] == 'BUY' else '卖'} {o['qty']:,} {unit} "
                                      f"{RS.STATUS_TEXT.get(o['status'], o['status'])}" + (f"：{o['note']}" if o["note"] else ""))))
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
        if in_use and (not ld or str(ld) < exp or (str(ld) == exp and not morning_done(book, exp))):
            out.append(("neg", f"★ 今天早上的运行还没完成（上次决策 {escape(str(ld or '—'))}）"))
    wd = RS.peek_json(paths.out_dir() / f"watchdog_{tag}.json")
    if wd and wd.get("ok") is False:
        when, is_today = at(wd.get("at"))
        rs = wd.get("reasons")
        rs = [rs] if isinstance(rs, str) else [str(x) for x in (rs if isinstance(rs, list) else [])]
        if is_today:
            out.append(("neg", f"★ 自检（{escape(when[6:])}）：{escape('；'.join(rs) or '没通过')}"))
    if isinstance(wd, dict):                               # 外部心跳没发成（09:30 自检记的；原因不含地址；2026-10-14 G12）
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


def _orders_card(book: dict, now: dt.datetime, paper: bool, waiting: list) -> str:
    """「今天的单」（Mac 与手机同一个）：账本当前决策里执行器的单（票、买卖、股数、下法、限价、状态）。还挂着的单（SENT / PARTIAL，
    今天的、立花有注文番号）给「撤单」按钮 → 写撤单指令（kind cancel_order），面板马上叫执行器撤（qbreak/live_ops.py）；
    已经写了撤单指令的显示「撤单中」。立花 API / Mac 出故障那天：照这张表在立花网站下单，之后在 Mac 对话里说一声人工代下登记（adopt）。
    没有单 → ""。只展示 + 写指令，不改账本。"""
    from . import live_ops as LO
    st = book.get("state") or {}
    d = st.get("last_date")
    orders = [o for o in book.get("orders") or [] if o.get("decided_on") == d]
    if not orders:
        return ""
    items = ((book.get("manual") or {}).get("items") or {}).values()
    asked = ({str(r.get("cid")) for r in waiting if r.get("kind") == "cancel_order"}
             | {str(it.get("cid")) for it in items if it.get("kind") == "cancel_order" and it.get("status") == "pending"})
    f = LO.fill_day_of(book)
    stale = f is not None and f != now.date()               # 今天早上的运行没跑：这还是上一次决策的单（不是今天要下的）
    rows = []
    for o in orders:
        core = o.get("kind") == "core"
        unit = "口" if core else "股"
        n = int(o.get("sent_qty") or o.get("qty") or 0)
        lim = f"，限价 ≤ ¥{float(o['limit']):,g}" if o.get("limit") and o.get("side") == "BUY" else ""
        q = int(o.get("filled_qty") or 0)
        got = f"，成交 {q:,}/{n:,}" if q and o.get("status") in ("PARTIAL", "CANCELLED", "EXPIRED") else ""
        note = str(o.get("note") or "")
        if str(o.get("cid")) in asked:
            btn = "<span class='chip'>撤单中</span>"
        elif LO.cancel_why(o, book, now, paper) is None:
            btn = (f"<button class='btn sm danger' data-act='cancel-order' data-cid='{escape(str(o.get('cid')))}' "
                   f"data-t='{escape(str(o.get('ticker')))}' data-side='{escape(str(o.get('side')))}' data-qty='{n}' "
                   f"data-core='{1 if core else 0}'>撤单</button>")
        else:
            btn = ""
        rows.append(f"<div class='li'><div class='grow'><b>{'买' if o.get('side') == 'BUY' else '卖'} {escape(str(o.get('ticker')))} "
                    f"{n:,} {unit}</b> <span class='chip'>{escape(LO.STATUS_TEXT.get(o.get('status'), str(o.get('status'))))}</span>"
                    f"<div class='muted small'>{escape(LO.how_text(o) + lim + got)}"
                    f"{(' · ' + escape(note[:140])) if note else ''}</div></div>{btn}</div>")
    foot = (f"「撤单」：{LO.CANCEL_HINT}。{LO.CANCEL_HINT_CORE}。"
            + ("" if paper or stale else
               "立花 API / Mac 出故障那天：只照这张表里「被挡 / 不下 / 没下」的行在立花网站下单（「已下单 / 已成交 / 部分成交」的已经在交易所，"
               "别再下），之后在 Mac 对话里说一声登记（人工代下）。"))
    head = (f"上一次决策的单（成交日 {escape(str(f))}，不是今天：今天早上的运行还没跑）" if stale else
            f"今天的单（执行器{'，成交日 ' + escape(str(f)) if f else ''}）")
    return (f"<section class='card' id='today'><h2>{head}</h2>"
            f"<div class='list'>{''.join(rows)}</div><div class='muted small'>{escape(foot)}</div></section>")


PANE = "\x00PANE:"                                         # render 里的分组标记（_panes 用；不会出现在页面上）
# 标签页（2026-10-11 用户：「总览的都分开、不要很长、每个部分归类成可以点的标签、一眼看上去就知道里面是什么」）
TABS = {"home": ("⌂", "总览", "账户现在怎样：总权益、今天的运行有没有问题、损益与已实现、最近成交、日志"),
        "hold": ("▤", "持仓", "现在拿着的个股与闲置资金 ETF：为什么拿、走势、卖出 / 调仓；立花那边的实际持仓"),
        "trade": ("⇄", "交易", "今天的单（执行器下的，可撤）与你写的手动指令、卖出后不买回的票"),
        "pick": ("☆", "选股", "规则的候选：出信号的、快要出的、观察中的，买入前看价格与 K 线"),
        "news": ("⚠", "消息", "qbreak 发出的通知的记录，和经济威胁消息（内容、时间、可信度、影响的行业和持仓）；推送点开到这里"),
        "more": ("⋯", "更多", "通知设置、手机、上线准备、紧急停止（HALT）")}


def _panes(H: list) -> str:
    """把 render 的片段按 PANE 标记包成 <div class='pane' data-tab=…>（同一个标签可以有几段，顺序照旧）；每个标签第一段前加一行说明。"""
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
                out.append(f"<div class='pane' data-tab='{cur}'>{head}")
            continue
        out.append(h or "")
    if cur:
        out.append("</div>")
    return "".join(out)


def _badges(book: dict, st: dict, sm: dict, waiting: list, now: dt.datetime) -> dict:
    """标签上的数字：持仓 = 拿着的只数；交易 = 今天还挂着 / 等处理的单与指令；消息 = 24 小时内的提醒。"""
    out = {}
    n = len(st.get("pos") or {}) + sum(1 for u in (st.get("core_units") or {}).values() if int(u or 0) > 0)
    if n:
        out["hold"] = n
    d = st.get("last_date")
    act = sum(1 for o in book.get("orders") or [] if o.get("decided_on") == d and o.get("status") in ("SENT", "PARTIAL", "PLANNED", "DEFERRED", "SENDING"))
    act += len(waiting) + sum(1 for it in ((book.get("manual") or {}).get("items") or {}).values() if it.get("status") in MO.ACTIVE)
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
                    f"{escape(str(h.get('subject') or ''))}</summary><div style='white-space:pre-wrap'>{escape(str(h.get('text') or ''))}</div></details>")
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
            det.append("<div class='down'>受损方向的持仓 / 候补：" + escape("、".join(c["tickers_down"][:10])) + "</div>")
        if c.get("tickers_up"):
            det.append("<div class='up'>受益方向的持仓 / 候补：" + escape("、".join(c["tickers_up"][:10])) + "</div>")
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


def render(tag: str, tok: str, now: dt.datetime | None = None, mode: str = "local", device: dict | None = None,
           phone: dict | None = None, trigger: "Trigger | None" = None) -> str:
    """操作面板页面（一个账本）。mode = local（Mac 本机：tok = 面板令牌）/ remote（手机：tok = 这台设备的 CSRF 令牌）。
    trigger：面板自动叫执行器的那个对象（顶部显示「盘中自动下单暂停」/ 失败后最早什么时候再叫）。"""
    from . import holding_view as HV
    now = now or now_jst()
    remote = mode == "remote"
    book, sm = _load(tag)
    st = book.get("state") or {}
    paper = tag.startswith("paper")
    when = MO.when_text(now)                                # 马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘
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
    pct = MO.position_pct(st)
    pend = st.get("pending_exit") or {}
    waiting = MO.unseen(tag, book)
    dropped = MO.cancelled(waiting)                                    # 执行器还没读、已经点了撤回的
    busy = {r.get("ticker") for r in waiting if r.get("kind") in MO.POS_KINDS and r["id"] not in dropped}
    busy |= {it.get("ticker") for it in (man.get("items") or {}).values()
             if it.get("kind") in MO.POS_KINDS and it.get("status") in MO.ACTIVE and not it.get("cancel_req")}
    core_busy = any(r.get("kind") == "core" and r["id"] not in dropped for r in waiting)   # 执行器还没读的闲置资金比例指令
    cr = book.get("core_rule") or {}
    bfix = MO.core_fixed(book, tag)                    # 固定口数的 ETF：不跟闲置资金比例（卖出 / 调仓只改它的固定口数；2026-10-13）；还没读的固定 / 恢复按规则也算（2026-10-14）
    core_late = bool(cr) and abs(float(man.get("core_pct", 100.0)) - float(cr.get("applied", cr.get("pct", 100.0)))) > 1e-9
    core_now = {str(o.get("ticker")): o for o in book.get("orders") or []          # 今天盘中已经照比例调过的核心 ETF（口数明天早上对账后更新）
                if o.get("reason") == "manual_core" and o.get("decided_on") == st.get("last_date")
                and (o.get("status") in ("SENT", "FILLED", "PARTIAL", "SENDING", "ERROR")
                     or (o.get("status") in ("EXPIRED", "CANCELLED") and int(o.get("filled_qty") or 0) > 0))}   # 已失效 / 撤掉但成交过一部分：口数也变了
    buying = {r.get("ticker") for r in waiting if r.get("kind") == "buy" and r["id"] not in dropped}
    buying |= {it.get("ticker") for it in (man.get("items") or {}).values()
               if it.get("kind") == "buy" and it.get("status") in MO.ACTIVE and not it.get("cancel_req")}
    H = [f"<header class='top{' real' if real else ''}'><div class='bar'><b>qbreak 操作面板</b>"
         + ("<span class='real-badge'>真钱（立花本番）</span>" if real else "") + "<span class='sp'></span>"
         f"<span class='muted small'>{escape(now.strftime('%m/%d %H:%M JST'))}</span>"
         "<button class='btn sm' data-act='reload'>刷新</button></div>"
         "<nav class='tabs'>" + "".join(f"<a href='/?book={t}' class='{'on' if t == tag else ''}'>{escape(BOOKS[t])}</a>"
                                       for t in BOOKS if t in books() or t == tag)        # 正在看的账本总在标签里
         + "</nav></header><main><div id='top'></div><div id='stale' class='card warn small' role='status' hidden></div>"]
    warn = []
    if halt:
        warn.append(f"HALT 生效中（{escape(halt)}）：不下单，解除之后才处理")
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
             f"<div class='stats'><div><div class='muted'>总权益</div><div class='big'>{_yen(eq)}</div></div>"
             f"<div><div class='muted'>现金</div><div class='big'>{_yen(st.get('cash_jpy'))}</div></div></div>"
             f"<div>现在点买卖 → <b>{escape(when)}</b>下单</div><div class='muted small'>{escape(MO.RULE_TEXT)}</div>"
             + "".join(f"<div class='{'neg' if 'HALT' in w or 'ARM' in w or '买入信号' in w or '已停' in w else 'muted'} small'>★ {w}</div>"
                       for w in warn)
             + "".join(f"<div class='{c} small'>{h}</div>" for c, h in runl)
             + "</section>")
    if not st:
        H.append("<section class='card'>执行器还没有账本（第一次运行之后才有持仓）。</section>")
    H.append(_money_card(tag, book, now))                 # 〔77〕C：损益 / 年内已实现与预计代扣 / 最近成交 / 日志 / 入出金
    H.append(PANE + "hold")
    H.append(_alloc_card(book, sm.get("holding_view") or {}))  # 最上面：每个仓位占多少（2026-10-12）
    H.append(_broker_card(tag, now))                      # 〔77〕C：立花那边实际是什么（快照）
    H.append(PANE + "more")
    H.append(_gate_card(tag))                             # 〔77〕C：上线准备
    hv = sm.get("holding_view") or {}
    if not hv.get("holdings") and not hv.get("core") and st:               # 还没有算过（旧的汇总）：用账本里的数字
        hv = {"bar_date": st.get("last_date"),
              "holdings": [{"ticker": t, "shares": int(p.get("shares") or 0), "entry_date": p.get("entry_date"),
                            "entry_px": p.get("entry_px"), "error": "持有理由 / 趋势在下一次执行器运行之后显示"}
                           for t, p in (st.get("pos") or {}).items()],
              "core": [{"ticker": t, "name": t, "units": int(u), "why": "闲置资金规则（核心 ETF）"}
                       for t, u in (st.get("core_units") or {}).items() if int(u)]}
    _ht = list((st.get("pos") or {}).keys()) + [t for t, u in (st.get("core_units") or {}).items() if int(u or 0) > 0]
    hmarks = _news_marks(_ht, now) if _ht else {}                     # 持仓（个股 + 拿着的核心 ETF）的消息影响

    def chart(t: str, kind: str) -> str:
        return (f"<div class='chart' data-t='{escape(t)}' data-kind='{kind}'><span class='muted small'>"
                f"{'K 线（要 JavaScript）' if has_k else 'K 线在执行器下一次运行之后显示'}</span></div>")

    def actions(r: dict, kind: str) -> str:
        t = str(r["ticker"])
        if kind == "core":
            return (tchips(ktrend.get(t)) + _news_mark(hmarks.get(t)) + _core_actions(r, t) + _corefix(t, str(r.get("name") or t))
                    + _core_exit(t) + chart(t, "core"))
        qt = f"<div class='qt small' data-q='{escape(t)}'></div>" if t in (st.get("pos") or {}) else ""   # 现价（/api/quotes）
        return tchips(ktrend.get(t), stats=True) + qt + _actions(r, t)

    def _corefix(t: str, name: str) -> str:
        """核心 ETF 固定口数（2026-10-11 用户：持仓里的纳指 ETF、对冲美债也要能买入）：没拿的 →「买入…」、拿着的 →「固定口数…」；
        已固定 → 写出来 +「恢复按规则」。只写手动指令（下一次决策起；其余闲置资金照规则分）。"""
        if tag in READONLY:
            return ""
        fixed = (man.get("core_fix") or {}).get(t)
        c = MO.core_info(book, t) or {}
        px, lot = float(c.get("px") or 0), int(MO.core_lot(book, t) or 1)
        cur = int((st.get("core_units") or {}).get(t, 0))
        data = (f" data-t='{escape(t)}' data-name='{escape(name)}' data-px='{px:g}' data-lot='{lot}' data-cur='{cur}'"
                f" data-eq='{float(eq or 0):.0f}'")
        H_ = []
        plan = ""
        if fixed is not None:
            H_.append(f"<div class='small'><b>手动固定 {int(fixed):,} 口</b>（不按规则自动调、不跟闲置资金比例；其余闲置资金照规则）"
                      "<span class='muted'>；卖出 / 减仓 / 加仓：「固定口数…」（0 口 = 全部卖出）</span></div>")
            plan = f" data-plan='{escape(MO.corefix_clear_text(book, t, tag, now))}'"   # 「恢复按规则」之后会怎样（2026-10-13）
        btn = "买入…" if cur <= 0 and fixed is None else "固定口数…"
        H_.append(f"<div class='act'><button class='btn' data-act='corefix'{data}{'' if px > 0 else ' disabled'}>{btn}</button>"
                  + (f"<button class='btn'{plan} data-act='corefix-clear'{data}>恢复按规则</button>" if fixed is not None else "") + "</div>")
        if px <= 0:
            H_.append("<div class='muted small'>执行器下一次运行算出价格之后可用</div>")
        return "".join(H_)

    def _core_actions(r: dict, t: str) -> str:
        """持有的核心 ETF：卖出全部（= 闲置资金比例 0%：卖出后停买，出现买入信号要你确认才买）/ 调仓…（换算成「闲置资金比例」：
        规则每天把核心调回 规则目标额 × 比例）。执行器还没算过规则目标额（更新后第一次运行之前）也能卖出全部。"""
        cur = int((st.get("core_units") or {}).get(t, 0))
        if cur <= 0:
            return ""
        qt = f"<div class='qt small' data-q='{escape(t)}'></div>"                      # 现价（/api/quotes，盘中每 1 分钟刷新）
        if t in bfix:                                       # 固定口数：不换算成闲置资金比例（否则别的 ETF 跟着变、固定的这只卖了又买回；2026-10-13）
            px_ = float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)
            return (qt + f"<div class='muted small'>现在 {cur:,} 口" + (f" · 约 {_yen(cur * px_)}" if px_ > 0 else "")
                    + " · 手动固定：卖出 / 减仓 / 加仓用下面的「固定口数…」（只改这只的固定口数；别的 ETF 与闲置资金比例不变）</div>")
        if core_busy:
            return qt + "<div class='act muted'>有一条闲置资金比例的指令在处理（见「手动指令」）</div>"
        o = core_now.get(t)
        if o is not None:
            q, n = int(o.get("filled_qty") or 0), int(o.get("qty") or 0)
            got = ("已成交" if q >= n > 0 else f"成交 {q:,} / {n:,} 口" + {"EXPIRED": "，其余已失效", "CANCELLED": "，其余已撤"}.get(
                str(o.get("status")), "") if q > 0
                   else "等成交" if o.get("status") in ("SENT", "PARTIAL") else "结果不明")
            return (qt + f"<div class='act muted'>今天盘中已照比例{'卖出' if o.get('side') == 'SELL' else '买入'} {n:,} 口（{got}）："
                    "口数明天早上对账后更新</div>")
        c = MO.core_info(book, t)
        px = c["px"] if c else float((st.get("core_last") or {}).get(t) or 0)
        sell = (f"<button class='btn sell' data-act='core-sell' data-t='{escape(t)}' data-name='{escape(str(r.get('name') or ''))}'"
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
        data = (f" data-t='{escape(t)}' data-name='{escape(str(r.get('name') or ''))}' data-shares='{c['cur']}' data-px='{round(c['px'], 4)}'"
                f" data-core='1' data-lot='{c['lot']}' data-u100='{c['u100']}' data-cpct='{c['pct']:g}' data-approx='{1 if c.get('approx') else 0}'")
        share = f"{c['cur'] * c['px'] / eq * 100:.1f}" if eq and c["px"] > 0 else "—"
        return (qt + "<div class='act'>" + sell
                + f"<button class='btn' data-act='adj'{data}{'' if c['px'] > 0 and eq else ' disabled'}>调仓…</button></div>"
                f"<div class='muted small'>现在 {c['cur']:,} 口 · 约 {_yen(c['cur'] * c['px'])} · 约占权益 {share}% · "
                f"闲置资金比例 {c['pct']:g}%{'（还没照它调完，见「手动指令」）' if core_late else ''}"
                + ("<br>规则目标额还没算过（执行器下一次决策才算）：100% 先按现在的口数估算" if c.get("approx") else "") + "</div>")

    def _core_exit(t: str) -> str:
        """拿着的核心 ETF「什么时候会自动卖」+ 离触发还有多远（只展示；数字 = 执行器早上的汇总）。算不了 → 不显示（不影响按钮）。"""
        try:
            c = MO.core_info(book, t)
            return _exit_html(CX.build(t, sm, book, px=c["px"] if c else None, lot=MO.core_lot(book, t)))
        except Exception as e:                                # noqa: BLE001  展示用：一只算不出不影响页面
            log.warning("ETF 卡片「什么时候会自动卖」没算成：%s", e)
            return ""

    def _actions(r: dict, t: str) -> str:
        p = (st.get("pos") or {}).get(t)
        if p is None:
            return "<div class='act muted'>（这只票已经不在执行器的账本里）</div>" + chart(t, "stock")
        if t in pend:
            if pend[t] != "manual" and r.get("queued"):
                return chart(t, "stock")                     # 标题行已经写了「已排定开盘卖（…）」
            lab = "已在卖出（手动）" if pend[t] == "manual" else f"已排定开盘卖（{HV.EXIT_TEXT.get(pend[t], str(pend[t]))}）"
            return f"<div class='act'><b class='neg'>{escape(lab)}</b></div>" + chart(t, "stock")
        if t in busy:
            return "<div class='act muted'>有一条手动指令在处理（见「手动指令」）</div>" + chart(t, "stock")
        cur = pct.get(t)
        px = float(p.get("last_close") or p.get("entry_px") or 0)
        sh = int(p.get("shares") or 0)
        nmk = _news_mark(hmarks.get(t))                    # 拿着的票也标（横展开）
        data = f" data-t='{escape(t)}' data-name='{escape(str(r.get('name') or ''))}' data-shares='{sh}'"
        return (nmk + "<div class='act'>"
                f"<button class='btn sell' data-act='sell'{data}>卖出全部</button>"
                f"<button class='btn' data-act='adj'{data} data-px='{px:g}'{'' if px > 0 and eq else ' disabled'}>调仓…</button></div>"
                f"<div class='muted small'>现在 {sh:,} 股 · 约 {_yen(sh * px)} · 约占权益 {f'{cur:.1f}' if cur is not None else '—'}%</div>"
                + chart(t, "stock"))
    held_core = {str(r.get("ticker")) for r in hv.get("core") or []}
    other = [(t, c) for t, c in (kl.get("items") or {}).items() if c.get("kind") == "core" and t not in held_core]
    more = ("<details class='hv'><summary class='muted'>其他闲置资金 ETF（现在没拿）的 K 线</summary>"
            + "".join(f"<div class='hv'><b>{escape(str(c.get('name') or t))}</b> <span class='muted'>现在 0 口</span>"
                      f"{tchips(ktrend.get(t))}{_corefix(t, str(c.get('name') or t))}{chart(t, 'core')}</div>" for t, c in other)
            + "</details>") if other else ""
    held_any = bool(st.get("pos")) or any(int(u) > 0 for u in (st.get("core_units") or {}).values())
    H.append(PANE + "trade")
    H.append(_orders_card(book, now, paper, waiting))       # 今天的单（执行器）：还挂着的给「撤单」；API / Mac 故障时照它在立花网站下
    H.append(PANE + "hold")
    H.append("<section class='card' id='holdings'>" + HV.html(hv, actions=actions) + more
             + ("<div id='qt-note' class='muted small'>现价：Yahoo 1 分钟线（约晚 20 分钟）</div>" if held_any else "") + "</section>")
    H.append(PANE + "pick")
    H.append(_auto_buy_card(sm.get("suggest") or {}, book, tag, eq))   # 最上面：规则接下来会自动买的（2026-10-12）
    H.append(_suggest_card(sm.get("suggest") or {}, book, tag, buying, when, eq, cap, chart,
                           marks=_news_marks([r["ticker"] for r in (sm.get("suggest") or {}).get("rows") or []], now)))
    H.append(PANE + "hold")
    cp = float(man.get("core_pct", 100.0))
    slider = ("<div class='stepper'><button class='btn' data-act='core-step' data-d='-10' aria-label='减 10%'>−10</button>"
              f"<output id='core-val' class='big'>{cp:g}%</output>"
              "<button class='btn' data-act='core-step' data-d='10' aria-label='加 10%'>+10</button></div>"
              f"<input type='range' id='core-pct' min='0' max='100' step='5' value='{cp:g}' aria-label='闲置资金比例 %'>"
              "<div class='act'><button class='btn primary' data-act='core'>保存</button></div>")
    if cpause:                                              # 卖出 ETF 后停买：规则不自动买；出现买入信号只提醒，你点「确认买入」才买
        want = [(t, int(n)) for t, n in (cr.get("units100") or {}).items() if int(n) > 0 and t not in bfix]   # 固定口数的不算（2026-10-13）
        now_txt = ("想拿 " + "、".join(f"{t} 约 {n:,} 口" for t, n in want) if want else
                   "不拿核心 ETF（熊市 / 没有闲置资金）") if cr.get("units100") is not None else "执行器下一次运行之后显示"
        ri = MO.resume_info(book, tag, now)                 # 确认之后什么时候买（规则不拿 / 今天已经有单 → 不是马上；2026-10-13）
        la_why = MO.allin_busy_text(MO.live_allin(tag, book))   # 「全部换成」已下单 / 在等：不给恢复按钮（点了也会被拒；2026-10-14）
        btn = ("<div class='act muted'>有一条闲置资金比例的指令在处理（见「手动指令」）</div>" if core_busy else
               f"<div class='act muted small'>{escape(la_why)}</div>" if la_why else
               f"<div class='act'><button class='btn primary' data-plan='{escape(ri['text'])}' data-act='core-resume'>确认买入（恢复照规则）</button></div>")
        fixl = ("<div class='small'>手动固定 " + "、".join(f"{escape(t)} {n:,} 口" for t, n in sorted(bfix.items()))
                + ("（停买中也照买）" if any(n > 0 for n in bfix.values()) else "（不跟比例）") + "</div>") if bfix else ""
        prev = ""
        if cpause.get("allin"):                             # 「全部换成 X」停的：之前的比例 / 固定口数（只显示；你点了才恢复；2026-10-13）
            pp, pf = cpause.get("prev_pct"), cpause.get("prev_fix") or {}
            parts = ([f"比例 {float(pp):g}%"] if pp is not None else []) + [f"{t} 固定 {int(u):,} 口" for t, u in sorted(pf.items())]
            if parts:
                rb = ""
                if pp is not None and 0 < float(pp) < 100 and not core_busy and not la_why:
                    rp = MO.resume_info(book, tag, now, pct=float(pp))   # 只买规则目标额的 N%（2026-10-14）
                    rb = (f"<div class='act'><button class='btn' data-pct='{float(pp):g}' data-plan='{escape(rp['text'])}' data-act='core-restore'>"
                          f"恢复成 {float(pp):g}%</button></div>")
                prev = (f"<div class='small'>「全部换成 {escape(str(cpause['allin']))}」之前：{escape('、'.join(parts))}"
                        + ("<span class='muted'>（比例 100% = 「确认买入」）</span>" if pp is not None and float(pp) >= 100 else "") + "</div>" + rb
                        + ("<div class='muted small'>固定口数不会自动恢复：要的话在各 ETF 下面重新点「固定口数…」</div>" if pf else "")
                        + "<div class='muted small'>都不会自动恢复：你点了才改</div>")
        H.append(f"<section class='card{' warn' if csig else ''}' id='core'><h2>闲置资金（核心 ETF）</h2>"
                 f"<div><b>停买中</b>（{escape(str(cpause.get('since') or '—'))} 起"
                 + (f"，你卖出 {escape(str(cpause['ticker']))}" if cpause.get("ticker") else "") + "）：闲置资金留现金，规则不自动买 ETF</div>"
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

    nm = HV.names()                                        # 代码 → 公司名（2026-10-12 用户：只写代码不知道是哪只）
    from .idle_cash import NAMES as IC_NAMES
    allrec = {**{x["id"]: x for x in waiting}, **(man.get("items") or {})}
    void = MO.voided(waiting)

    def _tlabel(tk: str) -> str:
        code = str(tk).split(".")[0]
        n = str(IC_NAMES.get(tk) or "").split("（")[0] or nm.get(code) or ""
        return f"{code} {n}".strip()

    def _named(r: dict) -> str:
        s, tk = MO.describe(r), r.get("ticker")
        return s.replace(tk, _tlabel(tk)) if tk else s

    def _what(r: dict) -> str:
        if r.get("kind") == "cancel":                       # 撤回指令：写它撤的是哪一条（带名字）
            tg = allrec.get(r.get("target"))
            return escape("撤回：" + (_named(tg) if tg else str(r.get("target"))))
        return escape(_named(r))

    def _cbtn(r: dict, placed: int) -> str:                 # 「撤单」：同批一起撤的条数按 cancel_plan（与实际撤的一致）；同批卖单还挂在交易所 → 不给按钮
        if MO.allin_member(r) and r.get("kind") != "buy":
            b0 = MO.batch_buy(r, list(allrec.values()))
            if b0 is not None and (b0.get("status") in MO.ACTIVE or b0["id"] not in (man.get("items") or {})):
                return f"<span class='chip'>随「全部换成 {escape(str(r.get('fund_for')))}」一起（撤回买入那条）</span>"
        pl = MO.cancel_plan(tag, book, r["id"], now=now)
        if pl["why"]:
            return ""
        if pl["sent"] and (pl["target"] or {}).get("fund") == "all":
            return "<span class='chip'>同批卖单还挂在交易所：要撤先用「今天的单」撤那几笔卖单</span>"
        return (f"<button class='btn sm danger' data-act='cancel' data-id='{escape(r['id'])}' data-placed='{placed}' data-desc='{_what(r)}'"
                f" data-fund='{len(pl['todo'])}' data-stuck='{len(pl['stuck'])}'>撤单</button>")

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

    rows = []
    for r in waiting:
        if r.get("kind") == "uncancel" or r["id"] in void:  # 撤销撤回本身、已被撤销的撤回：不显示（去掉撤销记录）
            continue
        btn = (_cbtn(r, 0) if r["kind"] in MO.ORDER_KINDS + ("core", "corefix") and r["id"] not in dropped
               else _ubbtn(r) if r["kind"] == "unblock" and r["id"] not in dropped else _unbtn(r))
        wt = MO.wait_word(r)                               # 比例 / 解除 / 撤回不是单（2026-10-13）
        rows.append(f"<div class='li'><div class='grow'><b>{_what(r)}</b> <span class='chip'>"
                    f"{wt + '（撤回中）' if r['id'] in dropped else wt}</span>"
                    f"<div class='muted small'>{escape(str(r.get('at', ''))[5:16].replace('T', ' '))}</div></div>{btn}</div>")
    cut = now - dt.timedelta(days=MANUAL_SHOW_DAYS)                 # 2026-10-12 用户：「交易里面只显示两天以内的」
    items = [it for it in items if it.get("kind") != "uncancel" and it.get("status") != "voided"]   # 撤销撤回、已撤销的撤回：不显示
    recent = [it for it in items if it.get("status") in MO.ACTIVE or (_ts_jst(it.get("at")) or cut) > cut]   # 没处理完的一直显示
    old_n = len(items) - len(recent)
    for it in recent[:20]:
        can = (it.get("status") in MO.ACTIVE and it.get("kind") in MO.ORDER_KINDS and not it.get("cancel_req")
               and not (it.get("status") == "placed" and it.get("now")))          # 盘中的单已经发到交易所：页面上撤不了
        btn = (_cbtn(it, 1 if it.get("status") == "placed" else 0) if can else _unbtn(it))
        rows.append(f"<div class='li'><div class='grow'><b>{_what(it)}</b> <span class='chip'>"
                    f"{escape(MO.status_text(it))}{'（撤回中）' if it.get('cancel_req') else ''}</span>"
                    f"<div class='muted small'>{escape(str(it.get('at', ''))[5:16].replace('T', ' '))}"
                    f"{(' · ' + escape(str(it['msg']))) if it.get('msg') else ''}</div></div>{btn}</div>")
    H.append(PANE + "trade")
    H.append("<section class='card' id='orders'><h2>手动指令</h2><div class='list'>"
             + ("".join(rows) or f"<div class='li muted'>最近 {MANUAL_SHOW_DAYS} 天没有</div>") + "</div>"
             + (f"<div class='muted small'>只显示最近 {MANUAL_SHOW_DAYS} 天的（没处理完的一直显示）；更早的 {old_n} 条不显示</div>" if old_n else "")
             + "</section>")
    bl = man.get("blocks") or {}
    if bl:
        H.append(_blocks_card(book, tag, bl, _tlabel))
    H.append(PANE + "more")
    if halt:
        hw = sorted((x for x in [it for it in (man.get("items") or {}).values() if it.get("status") == "pending"] + list(waiting)
                     if x.get("kind") in MO.ORDER_KINDS and x.get("id") not in dropped), key=lambda x: str(x.get("at") or ""))
        hc = MO.halt_core((man.get("items") or {}).values(), waiting, dropped)
        H.append(f"<section class='card warn' id='halt'><h2 class='neg'>HALT 生效中</h2><div>{escape(halt)}</div>"
                 + (f"<div class='neg small'>等着的手动买卖指令 {len(hw)} 条（最早写于 {escape(MO.mmdd(hw[0].get('at')))}）：解除后照原样执行；"
                    "不想做了先在「交易」撤回</div>" if hw else "")                  # 2026-10-13 resume-other-3
                 + (f"<div class='neg small'>HALT 期间改的闲置资金比例 / 固定口数 {len(hc)} 条：{escape(MO.halt_core_line(hc))}"
                    "→ 解除后下一次决策照它买卖 ETF；不想这样先在「闲置资金」改回</div>" if hc else "")   # 2026-10-14：读到就生效，以前 HALT 卡片不列
                 + "<div class='muted small'>不下任何单、持仓不动。恢复只在 Mac 上：在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」。</div></section>")
    else:
        H.append("<section class='card' id='halt'><h2>紧急停止</h2><div class='muted small'>全部账本（模拟和立花）从下一次运行起不下单、持仓不动；"
                 "已经发到交易所的单不会被撤（要撤：上面「今天的单」的「撤单」，或立花网站 / 手机网站）。这里只能停、不能恢复。</div>"
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
    badges = _badges(book, st, sm, waiting, now)
    H.append("</main><nav class='tabbar' role='tablist' aria-label='分类'>"
             + "".join(f"<button type='button' role='tab' data-tabgo='{k}' aria-label='{escape(lab)}'><b>{ic}</b>{escape(lab)}"
                       + (f"<i class='badge'>{badges[k]}</i>" if badges.get(k) else "") + "</button>"
                       for k, (ic, lab, _) in TABS.items())
             + "</nav><div id='toast' class='toast' role='status' hidden></div>")
    note = MO.sale_note(tag, now)
    ests = {}                                               # 拿着的票卖出全部的预计收益（按账本里的最近收盘；页面取到现价后换成现价的）
    ytdg = MO.ytd_gain(book, now.date())                 # T7：卖出的预计代扣按今年已实现的损益通算
    for t in list(st.get("pos") or {}) + [t for t, u in (st.get("core_units") or {}).items() if int(u or 0) > 0]:
        e = MO.sell_estimate(book, t, sm=sm)
        if e:
            ests[t] = {**e, "lines": MO.est_lines(e, note, ytdg)}
    u100s = MO.core_u100s(book)[0]                          # 规则目标（比例 100%）；执行器还没算过 → 估算（比例还是 100% 时）
    cfg = {"auth": {"h": "X-Qbreak-Csrf" if remote else "X-Qbreak-Token", "v": tok}, "book": tag, "paper": paper, "remote": remote,
           "real": real,                                                                   # 真钱（立花本番）：确认框写明
           "when": when, "eq": eq or 0, "cap": cap, "lot": MO.LOT, "live": MO.timing(now)[0] == "now",   # 盘中：现价每 1 分钟刷新
           "cores": {t: {"cur": int((st.get("core_units") or {}).get(t, 0)), "u100": int(u100s.get(t, 0)),
                         "lot": MO.core_lot(book, t)}                                            # 调一只核心 ETF 时别的跟着变多少
                     for t in dict.fromkeys(list(u100s) + [t for t, u in (st.get("core_units") or {}).items() if int(u) > 0])
                     if t not in bfix},                                                  # 固定口数的不跟比例（2026-10-13）
           "kp": {"label": KL.PLAIN, "align": KL.ALIGN_PLAIN, "chan": KL.CHAN_PLAIN},     # K 线的通俗说法（qbreak/kline.py）
           "fund": MO.fund_holdings(book, tag),
           "when_all": MO.allin_when(now, book, tag),                                     # 「全部换成这只」整批什么时候做
           "halt_allin": MO.allin_halt_note(book),                                         # HALT 确认框：同批卖单已在交易所 → X 不会买
           "block_days": MO.BLOCK_DEFAULT,                                                # 卖出后不自动买回的天数（默认）
           "alloc": {"names": {r.get("ticker"): str(r.get("name") or "").split("（")[0]
                               for r in ((sm.get("holding_view") or {}).get("holdings") or []) + ((sm.get("holding_view") or {}).get("core") or [])
                               if r.get("ticker")},
                     "colors": list(ALLOC_COLORS)},                                       # 买入框里「现在 / 买入后」的占比条（与持仓页同色）                                           # 买入钱不够 → 从持仓平摊凑（预览；提交时同一个算法再算）
           "est": ests, "fee": [[c if c != float("inf") else 1e18, f] for c, f in FEE_TIERS],
           "st": status_json(tag)[1],
           "gen": int(dt.datetime.now().timestamp() * 1000)}                                    # 页面生成时刻（离线时显示「几分钟前的数据」）                                                         # 〔77〕C UX-16：还在处理的指令 → 每 10 秒问一次   # 卖出的预计收益（按最近收盘；现价来了用现价的）
    cfg_json = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return _head("qbreak 操作面板") + "<body><div id='pbar' role='progressbar' aria-label='加载中'></div>" + _panes(H) + _dialogs(paper, cap) + (f"<script type='application/json' id='qb-cfg'>{cfg_json}</script>"
              f"<script type='module' src='/static/main.js?v={ASSET_V}'></script></body></html>")


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
    """〔77〕C UX-16：页面要不要刷新（只读）→ {sig, pending}。sig = 手动指令的状态 + 执行器这次运行 + 当前决策的单的状态 的摘要；
    页面拿着加载时的 sig，每 10 秒问一次，变了就刷新。pending = 还在处理的指令数（0 → 页面不轮询）。"""
    import hashlib
    from . import run_status as RS
    book = read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {}
    man = book.get("manual") or {}
    items = sorted(((str(k), str(v.get("status")), str(v.get("msg") or "")[:60], bool(v.get("cancel_req")))
                    for k, v in (man.get("items") or {}).items()), key=lambda x: x[0])
    waiting = sorted(str(r.get("id")) for r in MO.unseen(tag, book))
    d = (book.get("state") or {}).get("last_date")
    orders = sorted((str(o.get("cid")), str(o.get("status")), int(o.get("filled_qty") or 0))
                    for o in book.get("orders") or [] if o.get("decided_on") == d)
    rec = RS.read(tag) or {}
    snap = read_json(paths.out_dir() / f"broker_snapshot_{tag}.json", {}) or {}
    raw = json.dumps([items, waiting, orders, rec.get("at"), rec.get("ok"), snap.get("at")], ensure_ascii=False, default=str)
    pend = len(waiting) + sum(1 for _, s, _, _ in items if s in MO.ACTIVE)
    return 200, {"ok": True, "sig": hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16], "pending": pend}


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
            + ("（" + escape("、".join(a["incomplete"])) + " 的成本对不上，没算进去）" if a.get("incomplete") else "") + "</div></div>")


def _money_card(tag: str, book: dict, now: dt.datetime) -> str:
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
    if y:
        g, w = float(y.get("gain") or 0), float(y.get("withheld") or 0)
        H.append(f"<div class='small'>{y.get('year')} 年已实现 <b class='{cls(g)}'>{sy(g)}</b>（{int(y.get('n') or 0)} 笔：个股 {sy(y.get('stock_gain') or 0)}"
                 f" · 核心 ETF {sy(y.get('core_gain') or 0)}）· 预计已代扣 ¥{w:,.0f}"
                 + "</div>"
                 + (f"<div class='neg small'>★ 不完整：{escape('、'.join(y['incomplete']))} 的买入记录对不上，它的卖出没算进去</div>"
                    if y.get("incomplete") else "")
                 + "<div class='muted small'>特定口座（源泉徴収あり）20.315% 的估算：每次卖出时按「今年 1/1 起已实现损益的合计」代扣或退还"
                   "（年内盈亏通算），到 12/31 为止、第二年从 0 重新算；按成交日分年。税后累计 = 累计损益 − 历年代扣 − 现在全部卖出还要扣的。"
                   "以立花的取引報告書 / 年間取引報告書为准</div>")
    rz = m.get("realized") or []
    if rz:
        H.append("<details class='hv'><summary class='muted'>最近的已实现损益（" + str(len(rz)) + " 笔）</summary><div class='list'>" + "".join(
            f"<div class='li'><div class='grow'>{escape(r['date'][5:].replace('-', '/'))} 卖 {escape(r['ticker'])} {int(r['shares']):,} "
            f"{'口' if r['kind'] == 'core' else '股'} @ ¥{float(r['px']):,.1f}</div><b class='{cls(r['pnl'])}'>{sy(r['pnl'])}</b></div>"
            for r in rz) + "</div></details>")
    fl = m.get("fills") or []
    if fl:
        H.append("<details class='hv'><summary class='muted'>最近成交（" + str(len(fl)) + " 笔）</summary><div class='list'>" + "".join(
            f"<div class='li'><div class='grow'>{escape(str(f['date'])[5:].replace('-', '/'))} {'买' if f['side'] == 'BUY' else '卖'} "
            f"{escape(f['ticker'])} {int(f['qty']):,} {'口' if f['kind'] == 'core' else '股'}</div><span>¥{float(f['px']):,.1f}</span></div>"
            for f in fl) + "</div></details>")
    jl = m.get("journal")
    if jl:
        H.append(f"<details class='hv'><summary class='muted'>日志：{escape(jl[0])}</summary><ul class='small'>"
                 + "".join(f"<li>{escape(x)}</li>" for x in jl[1][:30]) + "</ul></details>")
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


def _broker_card(tag: str, now: dt.datetime) -> str:
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
    bad = [r for r in s.get("compare") or [] if r.get("diff")]
    q = s.get("quotes") or {}
    rows = "".join(
        f"<div class='li'><div class='grow'><b>{escape(r['ticker'])}</b> 立花 {int(r['broker']):,} / 账本 {int(r['ledger']):,}"
        + (f" <b class='neg'>差 {int(r['diff']):+,}</b>" if r.get("diff") else " ✓")
        + (f"<div class='muted small'>立花现价 ¥{float(q[r['ticker']]):,.1f}（{escape(str(s.get('quotes_at') or '')[11:16])}）</div>"
           if r["ticker"] in q else "") + "</div></div>"
        for r in s.get("compare") or [])
    fl = BS.fills_lines(s)
    return (f"<section class='card{' warn' if bad else ''}' id='broker'><h2>立花那边（{escape(str(s.get('at') or '')[5:16])}，"
            f"{escape(str(s.get('source') or ''))}）</h2>"
            f"<div>买付可能額 <b>{_yen(s.get('buying_power'))}</b></div>"
            + (f"<div class='neg small'>★ 账本和立花不一致 {len(bad)} 只：下一次早上的核对会停下 → Mac 对话里说「核对持仓」</div>" if bad else "")
            + f"<div class='list'>{rows or '<div class=li>立花那边没有持仓</div>'}</div>"
            + (f"<div class='small'><b>今天的成交</b>（{escape(str(s.get('fills_at') or '')[11:16])}）</div><ul class='small'>"
               + "".join(f"<li>{escape(x[2:])}</li>" for x in fl) + "</ul>" if fl else "")
            + f"<div class='muted small'>只读的快照，不是实时；正式记账在下一个交易日 07:40。{escape(how)}</div></section>")


def _notify_card() -> str:
    """手机（网页 App）：推送通知的开关。iPhone 要 iOS 16.4 以上、从「添加到主屏幕」的图标打开才能打开推送（Safari 的标签页里不行）。"""
    return ("<section class='card' id='notify'><h2>通知（推送）</h2>"
            "<div id='push-st' class='small'>检查中…</div>"
            "<div class='act'><button class='btn primary' data-act='push-on'>在这台设备打开推送</button>"
            "<button class='btn' data-act='push-test'>发一条测试</button><button class='btn' data-act='push-off'>关掉</button></div>"
            "<div class='muted small'>打开后：成交、09:30 自检没通过、闲置资金 ETF 的买入信号、HALT、手机连不上等通知会直接弹到这台设备（和邮件同一段文字）。"
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


def submit(body: dict, now: dt.datetime | None = None, source: str = "panel") -> tuple[bool, str, dict | None]:
    """页面的一次提交 → (成功?, 说明, 写进去的指令)。与 run.py manual 相同的检查。source：panel（Mac）/ phone（手机）。"""
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
        return True, (f"已写：恢复按规则 → 解除 {'、'.join(r['ticker'] for r in out)} 的不自动买回（不会买回，也不马上买；"
                      f"指令 {out[0]['id']} 等 {len(out)} 条" + (f"；没写：{'；'.join(skip)}" if skip else "") + f"）→ {MO.NEXT_DECISION}"), out[0]
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
        rec = MO.core_rec(rec, book, tag) or rec             # 持有的核心 ETF 的卖出 / 调仓 → 闲置资金比例（规则每天按它调核心）；固定口数的 → 改固定口数
    except ValueError as e:
        return False, f"没写：{e}", None
    c0 = MO.core_info(book, rec["ticker"]) if rec["kind"] == "core" and rec.get("ticker") else None
    pct0 = MO.core_pct_now(tag, book)                      # 写之前的闲置资金比例（含还没读的指令；0 = 停买中）
    fund = body.get("fund") if rec["kind"] in ("buy", "adjust", "corefix") else None
    allp, going = None, None
    if rec["kind"] == "buy" and isinstance(fund, dict) and fund.get("mode") == "all":   # 其他全部卖出，只拿这只（2026-10-13）
        la = MO.live_allin(tag, book)
        if la:
            return False, f"没写：「全部换成 {la[0]['ticker']}」还在处理：同时只能有一个「全部换成」（要改就先撤回那条）", None
        allp = MO.fund_all(book, tag, rec["ticker"])
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
        plan = MO.fund_split(cost, MO.fund_holdings(book, tag), skip=rec["ticker"]) if cost > 0 else None
        for r in (plan or {}).get("rows") or []:
            if r["kind"] != "stock":
                continue
            sr = MO.normalize({"kind": "adjust", "ticker": r["t"], "unit": "shares", "value": r["after"],
                               "fund_for": rec["ticker"], "source": source, "dir": -1, "cur0": r.get("cur")})
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（凑钱要卖的 {r['t']}：{w}）", None
            sells.append((sr, r))
        if plan:
            rec["fund"] = "split"
    elif allp is not None:                                 # 其他全部卖出：个股 adjust → 0；固定口数取消；闲置资金比例 → 0%（卖出全部 + 停买）；最后买入
        for t, cur, _px in allp["sells"]:
            sr = MO.normalize({"kind": "sell", "ticker": t, "block_days": MO.BLOCK_DEFAULT, "fund_for": rec["ticker"], "batch": "all",
                               "source": source})       # 卖出全部 + 不自动买回（2026-10-13 用户；整批执行时才设，「交易」里可一次「恢复按规则」）
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（要卖的 {t}：{w}）", None
            sells.append((sr, {"t": t, "sell": cur, "kind": "stock"}))
        for t in allp["core_clear"]:
            sr = MO.normalize({"kind": "corefix", "ticker": t, "clear": True, "fund_for": rec["ticker"], "batch": "all", "source": source,
                               "prev_units": ((book.get("manual") or {}).get("core_fix") or {}).get(t)})
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（取消 {t} 的固定口数：{w}）", None
            sells.append((sr, {"t": t, "sell": 0, "kind": "corefix"}))
        if float(allp["core_pct"]) > 0:
            sr = MO.normalize({"kind": "core", "pct": 0, "fund_for": rec["ticker"], "batch": "all", "source": source, "prev_pct": allp["core_pct"]})
            w = MO.check(sr, book, tag, sm=sm, now=now)
            if w:
                return False, f"没写（闲置资金比例 → 0%：{w}）", None
            sells.append((sr, {"t": "core", "sell": 0, "kind": "core"}))
        rec["fund"] = "all"
    clock = (lambda: now) if now else None
    if rec["kind"] == "adjust" and not rec.get("fund_for"):   # 写入时预览的方向（+1 加 / −1 减）：执行时换算方向相反 → 不执行（2026-10-13）
        a0 = MO.adjust_plan(rec, book.get("state") or {}, MO.MANUAL_CAP_PCT)
        if a0["delta"]:
            rec.update(dir=1 if a0["delta"] > 0 else -1, cur0=int(a0["cur"]))
    if allp is not None:                                   # 全部换成：买入 + 同批一次写进文件（执行器不会只读到一半）
        rec = MO.append_many(tag, [rec] + [sr for sr, _r in sells], clock=clock)[0]
    elif sells:                                            # 平摊凑钱：凑钱的卖在前、买入在后，一次写进文件（同一时刻 = 同一组；2026-10-13）
        rec = MO.append_many(tag, [sr for sr, _r in sells] + [rec], clock=clock)[-1]
    else:
        rec = MO.append(tag, rec, clock=clock)
    if rec["kind"] == "unblock":                           # 解除不是单：不会买回、也不马上买，下一次决策起才不挡（2026-10-13）
        return True, f"已写：解除 {rec['ticker']} 的不自动买回（不会买回，也不马上买；指令 {rec['id']}）→ {MO.NEXT_DECISION}", rec
    when = MO.when_text(now or now_jst())                   # 马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘
    k, t = rec["kind"], rec.get("ticker")
    msg = {"sell": f"已写：卖出 {t} 全部 → {when}卖出",
           "trim": f"已写：{t} 减到约 {rec.get('pct', 0):g}% → {when}卖出",
           "core": f"已写：闲置资金比例 {rec.get('pct', 0):g}% → 核心 ETF {when}照新比例调",
           "unblock": f"已写：解除 {t} 的不自动买回",
           "cancel_order": f"已写：撤单 {rec.get('ticker')}（{rec.get('cid')}）→ 执行器马上撤（已经成交的部分撤不了）"}.get(k)
    if k == "adjust":
        st = book.get("state") or {}
        a = MO.adjust_plan(rec, st, MO.MANUAL_CAP_PCT)
        if a["delta"] > 0:
            msg = (f"已写：{t} 加 {a['delta']:,} 股（→ {a['target']:,} 股" + ("，截到总权益" if a["capped"] else "")
                   + f"）→ {when}买入")
        else:
            msg = f"已写：{t} 卖 {-a['delta']:,} 股（→ {a['target']:,} 股）→ {when}卖出"
    if k == "corefix":                                                             # 2026-10-12 再发防止：这一种以前没有说明 → msg None → 拼接崩溃 → 手机 502
        msg = (f"已写：{t} 恢复按规则 → " + MO.corefix_clear_text(book, t, tag, now or now_jst()) if rec.get("clear") else   # 2026-10-13：会怎样
               f"已写：{t} 固定 {int(rec.get('units') or 0):,} 口 → 下一次决策（交易日 07:40）起调到这个口数、开盘下单")
        if rec.get("from_kind"):                                                   # 固定口数的 ETF 上点的卖出 / 减仓 / 调仓（2026-10-13）
            msg += "（这只是手动固定的：只改这只 ETF 的固定口数，别的 ETF 与闲置资金比例不变；不是盘中马上下单）"
    if msg is None:                                                                # 新加的指令种类忘了写说明：也给一句（不让拼接崩溃）
        msg = f"已写：{MO.LABEL.get(k, k)}" + (f" {t}" if t else "") + f" → {when}处理"
    if k == "core" and not t and pct0 <= 0 < float(rec["pct"]):                    # 停买后确认买入
        p1 = float(rec["pct"])
        ri = MO.resume_info(book, tag, now or now_jst(), pct=p1)   # 规则不拿 / 今天已经有单 → 不是马上（2026-10-13）
        full = p1 >= 100 - 1e-9                                    # 「恢复成 N%」只买规则目标额的 N%：不说照规则（2026-10-14）
        msg = (f"已写：{'确认买入' if full else f'恢复成 {p1:g}%'}（闲置资金比例 0% → {rec['pct']:g}%）→ "
               + ((f"{when}照规则买入核心 ETF" if full else f"{when}按规则目标额的 {p1:g}% 买入核心 ETF，之后每天按 {p1:g}% 调")
                  if not ri["none"] and not ri["late"] else ri["text"]))
    if k == "core" and t and int(rec.get("target") or 0) <= 0:                     # 核心 ETF 卖出全部：之后停买
        fx = MO.core_effects(book, 0.0, skip=t, tag=tag)
        msg = (f"已写：卖出全部 {t} → {when}卖出；之后停买闲置资金 ETF（出现买入信号会提醒，你确认才买）"
               + ("；同一比例也用在：" + "、".join(f"{x} {a_:,} → {b_:,} 口" for x, a_, b_ in fx) if fx else ""))
    elif c0:
        n = int(rec["target"]) - c0["cur"]
        fx = MO.core_effects(book, rec["pct"], skip=t, tag=tag)  # 规则同时拿两只以上核心 ETF 时：同一比例别的也跟着变
        msg = (f"已写：{'卖出全部 ' + t if int(rec['target']) <= 0 else t + (' 加 ' if n > 0 else ' 卖 ') + f'{abs(n):,} 口'}"
               f"（闲置资金比例 {c0['pct']:g}% → {rec['pct']:g}%）→ {when}{'买入' if n > 0 else '卖出'}"
               + ("；同一比例也用在：" + "、".join(f"{x} {a_:,} → {b_:,} 口" for x, a_, b_ in fx) if fx else ""))
    if k == "buy":
        row = next((r for r in (sm.get("suggest") or {}).get("rows") or [] if r.get("ticker") == t), None)
        est = MO.fmt_target(rec)
        if row and rec.get("unit") == "rule":
            est = f"约 {int((row.get('buy') or {}).get('rule_shares') or 0):,} 股"
        msg = (f"已写：买入 {t}（{est}）→ {when}买入"
               + ("" if row and row.get("signal") else "；★ 还没有买入信号：是你自己的决定"))
    if rec.get("fund") == "all":
        fx = MO.core_effects(book, 0.0, keep_fixed=True)    # 固定口数同批取消 → 也按 0% 卖
        etf = ("、".join(f"{x} {a_:,} → 0 口" for x, a_, _b in fx) or "、".join(f"{x} {u:,} → 0 口" for x, u in allp["cores"]))
        parts = ["执行时拿着的 " + t + " 以外的个股和 ETF 全部卖出（包括写指令之后规则 / 别的指令买进的）；现在拿着的："
                 + ("、".join(f"{r['t']} {r['sell']:,} 股" for _s, r in sells if r["kind"] == "stock") or "（没有别的个股）")
                 + (f"（之后 {MO.BLOCK_DEFAULT} 个交易日规则不自动买回；「交易」里可一次「恢复按规则」）" if any(r["kind"] == "stock" for _s, r in sells) else "")]
        if any(r["kind"] == "corefix" for _s, r in sells):
            parts.append("取消固定口数：" + "、".join(r["t"] for _s, r in sells if r["kind"] == "corefix") + (f"（{etf}：之后按比例 0% 卖出）" if etf else ""))
        if any(r["kind"] == "core" for _s, r in sells):
            parts.append(f"闲置资金比例 {allp['core_pct']:g}% → 0%（" + (etf + "；" if etf else "")
                         + "之后停买闲置资金 ETF，出现买入信号只提醒、你点「确认买入」才恢复）")
        elif not any(r["kind"] == "corefix" for _s, r in sells) and etf:
            parts.append(f"闲置资金比例已经是 0%：{etf}（照旧卖出）")
        if allp.get("also"):
            parts.append("另外规则 / 别的指令开盘还会买：" + "、".join(allp["also"]) + "（买进了的，执行时一起卖出）")
        wa = MO.allin_when(now or now_jst(), book, tag)
        msg = (f"已写：全部换成 {t} → {wa}整批先卖后买（那次决策先过闸门；股数由执行器按全卖之后的钱定）；" + "；".join(parts)
               + "；全卖也不够 1 个单元就不买、留现金；决策时买入被挡 → 整批不做、什么都不动；开盘跳空 / 没成交则其他已卖、留现金、不自动重买"
               "；规则对别的票仍可能用现金开新仓")
    elif sells:
        msg += ("；凑钱先卖：" + "、".join(f"{r['t']} {r['sell']:,} 股" for _s, r in sells)
                + ("（其余由别的核心 ETF 照规则减少：现金不够时执行器在那次决策里先卖它们补足，再平衡带以内也卖）" if k == "corefix" else "（核心 ETF 那份执行器按当时还缺多少卖）")
                + ("；买入先过闸门，被挡则凑钱的卖出也不做；开盘跳空 / 价格更高没买到时，凑钱的卖出照样会卖" if k == "buy" else ""))
    if paths.halt_file().exists() and k in MO.ORDER_KINDS + ("core",):
        msg += "；★ HALT 生效中：解除之后才处理"
    return True, msg + f"（指令 {rec['id']}）", rec


class Trigger:
    """面板写了手动指令之后叫执行器（同一个账本同一时间只跑一个）：
    盘中（09:00〜11:30、12:30〜15:25）有要马上下的指令 → --phase now（同一个账本最多 1 分钟一次）；
    交易日 07:45〜08:50、今天早上的运行已经完成、有新的卖出 / 调仓往下 / 撤回 → --retry（加进今天开盘的寄付单；最多 3 分钟一次）。
    失败退避（2026-10-09 立花实盘缺口 A7，条目 UX-04 / C-01：执行器失败后每分钟重叫 = 通知轰炸 + 反复登录立花，可能被判过负荷）：
    记下每个账本上一次叫的进程的退出码（非 0 = 失败）；盘中连续失败 n 次 → 从看到失败起至少等 min(60 秒 × 2^n, 15 分钟)；
    同一天连续失败 3 次（盘中 / 开盘前的重试一起算）→ 当天这个账本暂停自动叫，直到出现新的手动指令（叫那次执行器之后写的）或第二天；
    成功一次就清零。只管面板自己叫的；07:40 / 08:35 / 09:05 / 09:20 的定时运行不受影响。"""

    def __init__(self, run=None, clock=None, mono=None):
        self.run = run or self._spawn
        self.clock = clock or now_jst
        self.mono = mono or time.monotonic
        self.last: dict[str, float] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        self.started: dict[str, dt.datetime] = {}           # 账本 → 这次叫执行器的时刻（找这次的运行状态）
        self.fails: dict[str, tuple[str, int]] = {}         # 账本 → (日期, 当天连续失败次数)
        self.errs: dict[str, str] = {}                      # 账本 → 最后一次失败的原因
        self.paused: dict[str, tuple[str, str]] = {}        # 账本 → (日期, 原因)：当天暂停自动叫执行器
        self.pause_ids: dict[str, frozenset] = {}           # 暂停的基准：叫那次执行器时还没读的指令 id（出现不在里面的 = 新的指令 → 恢复）
        self.spawn_ids: dict[str, frozenset] = {}           # 账本 → 叫执行器那一刻还没读的指令 id
        self.lock = threading.Lock()

    @staticmethod
    def _spawn(tag: str, mode: str = "retry"):
        broker = "paper" if tag == "paper" else "tachibana"
        cmd = ["/bin/bash", str(paths.PROJECT_ROOT / "scripts" / "liveu.sh"), "run", "--broker", broker]
        cmd += ["--phase", mode] if mode in ("now", "cancel") else ["--retry"]
        if tag == "tachibana_demo":
            cmd.append("--demo")
        lf = open(paths.log_dir() / "com.qbreak.panel.retry.log", "a", encoding="utf-8")
        lf.write(f"\n── {now_jst():%Y-%m-%d %H:%M:%S} JST 手动指令 → {' '.join(cmd[1:])}\n")
        lf.flush()
        env = {**os.environ, "QBREAK_NO_HOLD": "1"}        # 跑完马上结束，不在进程里等到 09:35（liveu.sh 把让 Mac 醒着放到后台；2026-10-14 G2：
        #                                                   以前立花的 --retry 一直活到 09:35，这段时间面板不再叫执行器 → 撤单、盘中指令都卡住）
        return subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(paths.PROJECT_ROOT), start_new_session=True,
                                env=env)

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
            log.warning("面板叫的执行器今天连续失败 %d 次（%s）：今天暂停自动叫（新的手动指令 / 明天恢复）", n, tag)
        return False

    def _still_paused(self, tag: str, today: str, book: dict | None = None) -> bool:
        """暂停中：第二天 / 有新的手动指令（出现叫那次执行器时还没有的指令 id）→ 恢复（失败次数清零）。
        指令被定时运行读掉（没读的变少）不算新的指令。"""
        pz = self.paused.get(tag)
        if not pz:
            return False
        if pz[0] == today and not (self._unseen_ids(tag, book) - self.pause_ids.get(tag, frozenset())):
            return True
        self.paused.pop(tag, None)
        self.pause_ids.pop(tag, None)
        self.fails.pop(tag, None)
        log.info("面板自动叫执行器恢复（%s）：%s", tag, "第二天" if pz[0] != today else "有新的手动指令")
        return False

    def _gap(self, tag: str, today: str, morning: bool) -> float:
        if morning:
            return TRIGGER_GAP_S                           # 开盘前的重试照旧（3 分钟一次、到 08:50 为止）
        return min(NOW_GAP_S * 2 ** self._nfail(tag, today), FAIL_GAP_MAX_S)

    def _due(self, tag: str, book: dict, now: dt.datetime, morning: bool) -> bool:
        """面板现在会不会为这个账本叫执行器（不看退避）：开盘前 = 早上的运行已完成 + 有新的卖出 / 调仓往下 / 撤回；
        盘中 = 有要马上下的指令。"""
        from .live_unified import morning_done
        from .trader import expected_last_bar
        if morning:
            return morning_done(book, expected_last_bar(now.date(), "JP").isoformat()) and bool(MO.due(tag, book, now))
        return bool(MO.now_due(tag, book, now))

    def status(self, tag: str, now: dt.datetime | None = None, book: dict | None = None) -> tuple[str, str] | None:
        """面板顶部的一行（未转义的文字）：(CSS 类, 文字)。今天暂停中 → ★；今天失败过、还有要叫执行器的指令 → 最早什么时候再叫；
        没事（或已经没有要下的指令：之后不会再叫）→ None。book：render 已经读好的账本（不给就读）。"""
        now = now or self.clock()
        today = now.date().isoformat()
        morning = is_trading_day(now.date()) and TRIGGER_FROM <= now.time() < TRIGGER_UNTIL
        with self.lock:
            pz = self.paused.get(tag)
            if pz and pz[0] == today:
                return ("neg", f"★ 盘中自动下单暂停：执行器连续失败 {FAIL_PAUSE_N} 次（{pz[1]}）；修好后写新的指令或明天自动恢复")
            n = self._nfail(tag, today)
            if n <= 0 or tag in self.procs or not (morning or MO.timing(now)[0] == "now"):
                return None
            wait = max(0.0, self._gap(tag, today, morning) - (self.mono() - self.last.get(tag, -1e9)))
        if not self._due(tag, book if book is not None else _load(tag)[0], now, morning):
            return None                                    # 指令已经被读掉 / 撤回：面板不会再叫，「最早几点再叫」就不对了
        nxt = (now + dt.timedelta(seconds=wait)).strftime("%H:%M")
        return ("muted", f"面板叫的执行器今天连续失败 {n} 次：最早 {nxt} 再自动叫（连续 {FAIL_PAUSE_N} 次失败当天暂停）")

    def check(self) -> list[str]:
        """看一遍各个账本；返回这次叫了执行器的账本。"""
        now = self.clock()
        today = now.date().isoformat()
        morning = is_trading_day(now.date()) and TRIGGER_FROM <= now.time() < TRIGGER_UNTIL
        session = MO.timing(now)[0] == "now"
        cwin = is_trading_day(now.date()) and now.time() < MO.CANCEL_UNTIL     # 撤单：开盘前 / 午休也叫（15:30 之前）
        names = books() if (morning or session or cwin) else []
        with self.lock:
            for tag in list(self.procs):
                if tag not in names:
                    self._reap(tag, today)                   # 这次不看的账本（不在叫的时段 / 不在列表里）：结束了就记下成败
        if not names:
            return []
        out = []
        with self.lock:
            for tag in names:
                if self._reap(tag, today):
                    continue                                 # 上一次叫的还在跑（结束了：这里记下成败，每次只 poll 一次）
                if tag in self.paused and self._still_paused(tag, today):
                    continue                                 # 今天连续失败 3 次：等新的手动指令或明天
                book, _ = _load(tag)
                if MO.cancel_due(tag, book, now):
                    mode = "cancel"                          # 撤单指令：先撤（不看早上的运行完成没有；HALT 时也撤）
                elif (morning or session) and self._due(tag, book, now, morning):
                    mode = "retry" if morning else "now"
                else:
                    continue                                 # 开盘前：早上的运行还没完成（它自己会读到指令）/ 没有新指令
                if self.mono() - self.last.get(tag, -1e9) < self._gap(tag, today, morning and mode != "cancel"):
                    continue                                 # 失败过：从看到失败起按连续失败次数加倍等
                self.last[tag] = self.mono()
                try:
                    self.started[tag] = now
                    self.spawn_ids[tag] = self._unseen_ids(tag, book)   # 暂停的基准：叫的这一刻还没读的指令
                    self.procs[tag] = self.run(tag, mode)
                    out.append(tag)
                    log.info("手动指令：叫执行器（%s，%s）", tag, mode)
                except Exception as e:                       # noqa: BLE001
                    log.warning("叫执行器失败（%s，%s）：%s", tag, mode, e)
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
        return 404, {"ok": False, "msg": f"没有 {t} 的 K 线"}
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
    """t 在执行器汇总的「建议的股票」里（K 线并进今天这一根、现价接口只接受这些）。"""
    return any(r.get("ticker") == t for r in ((_load(tag)[1] or {}).get("suggest") or {}).get("rows") or [])


def _held(tag: str, t: str) -> bool:
    """t 现在在这个账本里拿着（个股或核心 ETF）。只读账本（不读执行器汇总）。"""
    st = ((read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {}).get("state") or {})
    return t in (st.get("pos") or {}) or int((st.get("core_units") or {}).get(t, 0) or 0) > 0


def _live_bar(tag: str, t: str) -> dict | None:
    """现价缓存里这只票最新的一条（{"px", "at", "bar"}）；没取过 → None。"""
    with _QUOTE_LOCK:
        hits = [c for k, c in _QUOTE_CACHE.items() if k[0] == tag and (c[1] or {}).get(t)]
    if not hits:
        return None
    return max(hits, key=lambda c: c[0])[1][t]


# ───────────────────────── 持仓的现价（按需取） ─────────────────────────
FEE_TIERS = tuple(_BROKERS[_DEFAULT_BROKER["JP"]]["markets"]["JP"].get("commission_tiers") or ())   # 页面算部分卖出的手续费（= MO.fee_jp）
_QUOTE_CACHE: dict = {}
_QUOTE_LOCK = threading.Lock()


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
    extra（页面的 t=…）：「建议的股票」里的票（打开的 K 线 / 买入框；只接受执行器汇总里列着的、没拿着的，一次最多 SG_MAX 只）→ 只回这些。
    同一组票盘中 60 秒内、其他时间 10 分钟内只取一次（Mac 与手机共用）；票由账本 / 汇总决定（不接受随便的代码）。
    每只附：rng = 晚了这几分钟里价格通常（约 95%）在 ±几 % 以内（日波动按 K 线文件算；只是估算）；
    头上附 basis = 现在点卖 / 买，下单按什么价（MO.order_basis）。"""
    now = now or now_jst()
    book, sm = _load(tag)
    st, cr = book.get("state") or {}, book.get("core_rule") or {}
    held = {t: {"kind": "stock", "n": int(p.get("shares") or 0), "prev": float(p.get("last_close") or 0),
                "cost": float(p.get("entry_px") or 0)} for t, p in (st.get("pos") or {}).items()}
    held.update({t: {"kind": "core", "n": int(u), "cost": 0.0,
                     "prev": float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)}
                 for t, u in (st.get("core_units") or {}).items() if int(u) > 0})
    sgr = {}
    if extra is not None:                                    # 建议的股票：只接受汇总里列着的、没拿着的
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
    with _QUOTE_LOCK:
        c = _QUOTE_CACHE.get(key)
        if c is None or time.monotonic() - c[0] > (60 if live else 600):
            if fetch is None:
                from .data import intraday_quotes as fetch
            try:
                q = fetch(list(sorted(rows))) or {}
            except Exception as e:                           # noqa: BLE001
                log.warning("现价取不到：%s", e)
                q = {}
            c = (time.monotonic(), q) if q else (time.monotonic() - (50 if live else 540), q)   # 取不到：10 秒 / 1 分钟后再试
            _QUOTE_CACHE[key] = c
    out = {}
    for t, r in rows.items():
        x = c[1].get(t)
        if not x:
            continue
        px = float(x["px"])
        out[t] = {"px": round(px, 2), "at": x.get("at"), "today": str(x.get("at") or "")[:10] == now.date().isoformat(),
                  "kind": r["kind"], "n": r["n"], "value": round(px * r["n"]),
                  "chg_pct": round((px / r["prev"] - 1) * 100, 2) if r["prev"] > 0 else None,
                  "pl_pct": round((px / r["cost"] - 1) * 100, 2) if r["cost"] > 0 else None}
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
        est = MO.sell_estimate(book, t, px=px, at=x.get("at"), sm=sm)   # 卖出全部的预计收益（按这个现价）
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
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; manifest-src 'self'; "
       "connect-src 'self'; worker-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")

# 网页 App 的 service worker（/sw.js）：① 页面与只读接口「网络优先、连不上用上次的」（Mac 睡着 / Tailscale 断了也能看上次的数据，
# 页面顶上会写是几分钟前的）② 收推送（qbreak/webpush.py）→ 系统通知；点通知打开面板。只缓存这个面板自己（同源 GET），写操作从不缓存。
SW_JS = r"""const C='qbreak-v3';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
function keep(r,res){ if(res && res.ok){ const cp=res.clone(); caches.open(C).then(c=>c.put(r.url,cp)).catch(()=>{}); } return res; }
const OFF='<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>qbreak</title>'+
  '<p style="font:16px -apple-system,sans-serif;padding:24px;line-height:1.6">连不上 Mac 的面板（Mac 睡着 / 关机 / 手机的 Tailscale 没连上），'+
  '这台设备上也还没有存过页面。<br>Mac 醒来、Tailscale 连上之后下拉刷新。</p>';
self.addEventListener('fetch',e=>{
  const r=e.request; if(r.method!=='GET') return;
  const u=new URL(r.url); if(u.origin!==self.location.origin) return;
  if(r.mode==='navigate'){
    e.respondWith(fetch(r).then(res=>keep(r,res)).catch(()=>caches.open(C).then(c=>c.match(r.url).then(m=>m||c.match(new URL('/',self.location).href)))
      .then(m=>m||new Response(OFF,{headers:{'Content-Type':'text/html; charset=utf-8'}}))));
    return;
  }
  if(['/api/status','/api/quotes','/api/chart'].indexOf(u.pathname)>=0 || u.pathname.indexOf('/static/')===0){   // 页面的 JS / CSS 也缓存（离线时打开上次的页面要用）
    e.respondWith(fetch(r).then(res=>keep(r,res)).catch(()=>caches.open(C).then(c=>c.match(r.url)).then(m=>m||Response.error())));
  }
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
    code = WP.send_one(s, "qbreak 测试推送", "能看到这条 = 推送通了：成交、自检没过、买入信号、HALT 都会这样通知你。")
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
                                     "msg": "面板内部出错（已记日志）：这次可能已经写进去了 —— 刷新后在「手动指令」里确认，不要直接再点一次"})
                elif "/api/" in path:
                    self._json(500, {"ok": False, "msg": "面板内部出错（已记日志）：刷新后再试"})
                else:
                    self._text(500, "面板内部出错（已记日志）：刷新后再试")
            except Exception:                               # noqa: BLE001
                pass

    def _send(self, code: int, body: bytes, ctype: str, headers=()) -> None:
        self._sent = True
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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

    def _static(self, path: str) -> bool:
        """不含任何数据的静态东西（图标、manifest）：不用配对也给（主屏幕图标要用）。"""
        if path == "/favicon.ico":
            self._send(204, b"", "text/plain")
        elif path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
            self._send(200, PP.touch_icon_png(), "image/png")
        elif path == "/sw.js":
            self._send(200, SW_JS.encode("utf-8"), "text/javascript; charset=utf-8", [("Service-Worker-Allowed", "/")])
        elif path.startswith("/static/") and path[8:] in _static_files():   # 页面的 JS / CSS（不含任何数据；不用配对也给）
            self._send(200, _static_files()[path[8:]], STATIC_TYPES[Path(path).suffix])
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

    def _page(self, render_fn) -> None:
        try:
            html = render_fn()
        except Exception as e:                               # noqa: BLE001
            log.exception("面板页面出错")
            html = f"<!doctype html><meta charset='utf-8'><p>页面出错：{escape(type(e).__name__)}: {escape(str(e))[:300]}</p>"
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")


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


def make_handler(port: int, tok: str, trigger: Trigger | None = None, clock=None, phone_port: int | None = None):
    """本机端口（127.0.0.1:8765）：只接受本机的 Host；写操作要面板令牌。配对码在这里生成（只显示在 Mac 屏幕上）。"""
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
            if self._static(u.path):
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
            if u.path == "/api/push/key":
                from . import webpush as WP
                self._json(200, {"ok": True, "key": WP.public_key()})
                return
            if u.path != "/":
                self._text(404, "没有这个页面")
                return
            phone = {"port": phone_port, "url": PP.phone_url(), "devices": PP.devices(), "identity": PP.identity_state()}
            self._page(lambda: render(_book_of(u.query), tok, (clock or now_jst)(), mode="local", phone=phone, trigger=trigger))

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
                self._json(200 if ok else 400, {"ok": ok, "msg": msg, "id": (rec or {}).get("id")})
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
            if self._static(u.path):
                return
            if u.path not in ("/", "/pair", "/api/chart", "/api/quotes", "/api/status", "/api/push/key"):
                self._text(404, "没有这个页面")
                return
            dev = self._who()
            if u.path in ("/api/chart", "/api/quotes", "/api/status", "/api/push/key"):
                if dev is None:
                    self._json(401, {"ok": False, "msg": "这台设备还没配对（或已被取消）"})
                elif u.path == "/api/push/key":
                    from . import webpush as WP
                    self._json(200, {"ok": True, "key": WP.public_key()})
                elif u.path == "/api/chart":
                    self._chart(u.query, (clock or now_jst)())
                elif u.path == "/api/status":
                    self._json(*status_json(_book_of(u.query)))
                else:
                    self._json(*quotes_json(_book_of(u.query), (clock or now_jst)(), extra=_extra_of(u.query)))
                return
            if dev is None:
                code = (parse_qs(u.query).get("c") or [""])[0] if u.path == "/pair" else ""
                self._page(lambda: pair_page(code))
                return
            if u.path == "/pair":
                self._send(303, b"", "text/plain", [("Location", "/")])
                return
            if dev.get("kind") == "ts":                                   # 按账户登录、这台设备也配对过 → 页面上可以取消它的配对
                paired = PP.device_for(self.headers.get("Cookie"))
                dev = dict(dev, paired=paired["name"]) if paired else dev
            self._page(lambda: render(_book_of(u.query), PP.csrf(dev["id"]), (clock or now_jst)(), mode="remote", device=dev,
                                      trigger=trigger))

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
                self._json(200 if ok else 400, {"ok": ok, "msg": msg, "id": (rec or {}).get("id")})
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


def _watch_code(stop: threading.Event, srv, every: float = 60.0) -> None:
    """git pull 改了面板的代码 → 退出（LaunchAgent 的 KeepAlive 用新代码重启）。"""
    first = _mtimes()
    while not stop.wait(every):
        if _mtimes() != first:
            log.info("面板的代码更新了：退出，让 LaunchAgent 用新代码重启")
            print("面板的代码更新了（git pull）：退出；LaunchAgent 会用新代码重启（手动运行的话再运行一次）")
            srv.shutdown()
            return


def serve(port: int = 8765, open_browser: bool = False, trigger: bool = True, phone_port: int | None = PP.PHONE_PORT) -> int:
    """在 127.0.0.1:port（本机）与 127.0.0.1:phone_port（手机，Tailscale Serve 用；0 = 不开）上运行（前台；LaunchAgent 用 KeepAlive 守着）。"""
    tok = token()
    trg = Trigger() if trigger else None
    psrv = None
    if phone_port:
        try:
            psrv = ThreadingHTTPServer(("127.0.0.1", int(phone_port)), make_phone_handler(int(phone_port), trg))
        except OSError as e:
            log.warning("手机端口 127.0.0.1:%s 打不开（%s）：手机访问不可用", phone_port, e)
            print(f"★ 手机端口 127.0.0.1:{phone_port} 打不开（{e}）：手机访问不可用，本机面板照常")
    srv = ThreadingHTTPServer(("127.0.0.1", int(port)), make_handler(int(port), tok, trg, phone_port=int(phone_port) if psrv else None))
    stop = threading.Event()
    if psrv is not None:
        threading.Thread(target=psrv.serve_forever, daemon=True).start()
    if trg is not None:
        threading.Thread(target=trg.loop, args=(stop,), daemon=True).start()
    threading.Thread(target=_watch_code, args=(stop, srv), daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"操作面板：{url}（只在本机；Ctrl-C 结束）"
          + (f"；手机端口 127.0.0.1:{phone_port}（Tailscale Serve 用；按 Tailscale 账户登录或配对）" if psrv else ""))
    log.info("操作面板启动 %s%s", url, f"（手机端口 {phone_port}）" if psrv else "")
    if open_browser:
        try:
            subprocess.run(["open", url], timeout=20, capture_output=True, check=False)
        except Exception:                                    # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if psrv is not None:
            psrv.shutdown()
            psrv.server_close()
        srv.server_close()
    return 0


__all__ = ["serve", "render", "pair_page", "submit", "token", "Trigger", "make_handler", "make_phone_handler", "BOOKS"]
