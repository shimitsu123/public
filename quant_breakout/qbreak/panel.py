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
_CSS = """
:root{--bg:#f2f2f7;--card:#fff;--fg:#1c1c1e;--muted:#6e6e73;--line:#e3e3e8;--pos:#1a7f37;--neg:#c62828;--accent:#2f5bd3;
--accent-fg:#fff;--chip:#eef0f6;--shadow:0 1px 2px rgba(0,0,0,.06);--up:#e0373a;--down:#0e8f50;--ma10:#8e4bb3;--ma20:#c26a00;--ma30:#2a5db0}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0f0f11;--card:#1c1c1f;--fg:#ececf0;--muted:#a1a1a8;
--line:#2e2e33;--pos:#4cc36b;--neg:#ff6b6b;--accent:#8aa8ff;--accent-fg:#0f0f11;--chip:#2a2a30;--shadow:none;
--up:#e8484d;--down:#17905a;--ma10:#a66fd0;--ma20:#c47f2c;--ma30:#5b8be0}}
:root[data-theme="dark"]{--bg:#0f0f11;--card:#1c1c1f;--fg:#ececf0;--muted:#a1a1a8;--line:#2e2e33;--pos:#4cc36b;--neg:#ff6b6b;
--accent:#8aa8ff;--accent-fg:#0f0f11;--chip:#2a2a30;--shadow:none;--up:#e8484d;--down:#17905a;--ma10:#a66fd0;--ma20:#c47f2c;--ma30:#5b8be0}
*{box-sizing:border-box} [hidden]{display:none!important} html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Hiragino Sans","PingFang SC",sans-serif;
-webkit-tap-highlight-color:transparent;overflow-wrap:break-word}
.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);
padding:calc(env(safe-area-inset-top) + 8px) max(16px,env(safe-area-inset-right)) 8px max(16px,env(safe-area-inset-left))}
.bar{display:flex;align-items:center;gap:8px;max-width:720px;margin:0 auto}.bar .sp{flex:1}.bar b{font-size:17px}
.tabs{display:flex;gap:8px;overflow-x:auto;max-width:720px;margin:8px auto 0;scrollbar-width:none}.tabs::-webkit-scrollbar{display:none}
.tabs a{flex:0 0 auto;padding:6px 14px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--fg);
text-decoration:none;font-size:14px}.tabs a.on{background:var(--accent);border-color:var(--accent);color:var(--accent-fg)}
main{max-width:720px;margin:0 auto;padding:4px max(16px,env(safe-area-inset-right)) calc(env(safe-area-inset-bottom) + 40px) max(16px,env(safe-area-inset-left))}
h1{font-size:20px;margin:0 0 8px} h2{font-size:17px;margin:0 0 8px} h3{font-size:17px;margin:0 0 8px}
.muted{color:var(--muted);font-size:14px} .small{font-size:13px} .pos{color:var(--pos)} .neg{color:var(--neg)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:12px 0;box-shadow:var(--shadow)}
.card.warn{border-color:var(--neg)} a{color:var(--accent)}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
.big{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.25}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;background:var(--chip);font-size:13px;color:var(--fg);white-space:nowrap}
.head{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}.head b{white-space:nowrap}
.hv{border-top:1px solid var(--line);padding:12px 0}.hv ul{margin:4px 0;padding-left:18px} details summary{cursor:pointer;padding:4px 0}
.act{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}.act .btn{flex:1 1 140px}
.btn{font:inherit;font-size:16px;min-height:44px;padding:10px 16px;border-radius:12px;border:1px solid var(--line);background:var(--card);
color:var(--fg);cursor:pointer;touch-action:manipulation}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-fg);font-weight:600}
.btn.sell{border-color:var(--neg);color:var(--neg);font-weight:600}
.btn.danger{background:var(--neg);border-color:var(--neg);color:#fff;font-weight:600}
.btn.sm{min-height:36px;padding:6px 12px;font-size:14px;flex:0 0 auto} .btn:disabled{opacity:.45;cursor:default}
.top.real{border-bottom:3px solid var(--neg)} .real-badge{display:inline-block;padding:2px 10px;border-radius:999px;background:var(--neg);
color:#fff;font-size:13px;font-weight:700;white-space:nowrap}
.list .li{display:flex;gap:10px;align-items:center;border-top:1px solid var(--line);padding:10px 0}.list .li:first-child{border-top:0}
.grow{flex:1;min-width:0}
input[type=range]{width:100%;height:44px;accent-color:var(--accent)}
input[type=text],input[type=number]{font:inherit;font-size:17px;width:100%;padding:12px;margin:4px 0 10px;border-radius:12px;
border:1px solid var(--line);background:var(--card);color:var(--fg)}
input[type=number]{font-variant-numeric:tabular-nums;text-align:center;margin:0;-moz-appearance:textfield;appearance:textfield}
input[type=number]::-webkit-inner-spin-button,input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;white-space:nowrap;max-width:100%}
.seg button{font:inherit;font-size:14px;min-height:36px;padding:6px 12px;border:0;border-left:1px solid var(--line);background:var(--card);
color:var(--fg);cursor:pointer;touch-action:manipulation}.seg button:first-child{border-left:0}
.seg button[aria-pressed=true]{background:var(--accent);color:var(--accent-fg);font-weight:600}
.adjrow{display:flex;align-items:center;gap:10px;margin:10px 0 4px}.adjrow .grow{position:relative}
.adjrow .unit{position:absolute;right:14px;top:50%;transform:translateY(-50%);color:var(--muted);pointer-events:none}
.kbar{display:flex;align-items:center;gap:6px 10px;flex-wrap:wrap}.kbar .seg button{min-height:38px;padding:4px 16px;font-size:15px}
.kbar.ktop{padding:0 0 6px;border-bottom:1px solid var(--line);margin-bottom:4px}.kbar.kbot{padding:6px 0 2px;border-top:1px solid var(--line);margin-top:2px}.kbar .hint{font-size:12px;color:var(--muted)}
.kexp{font-size:13px;line-height:1.55;color:var(--muted);margin:4px 0}.kexp b{color:var(--fg)}.kexp b.up{color:var(--up)}.kexp b.down{color:var(--down)}
.kexp.now{color:var(--fg)}.kexp .legend{margin:0 0 2px}.kexp ul{margin:2px 0;padding-left:18px}
details.khelp{margin:2px 0 4px}details.khelp>summary{font-size:13px;color:var(--accent)}
details.khelp ul{margin:4px 0;padding-left:18px;font-size:13px;line-height:1.55;color:var(--muted)}
.lots{position:relative;height:44px;margin:8px 0 0}
.lots-bar{position:absolute;left:14px;right:14px;top:15px;height:14px;display:flex;gap:2px;pointer-events:none}
.lots-bar i{flex:1 1 0;min-width:1px;border-radius:3px;background:var(--line)}.lots-bar i.keep{background:var(--accent);opacity:.45}
.lots-bar i.add{background:var(--accent)}.lots-bar i.cut{background:transparent;box-shadow:inset 0 0 0 2px var(--neg)}
.lots-bar i.over{background:repeating-linear-gradient(135deg,var(--line) 0 3px,transparent 3px 6px)}
.lots input[type=range]{position:absolute;left:0;top:0;width:100%;height:44px;margin:0;background:transparent;-webkit-appearance:none;appearance:none}
.lots input[type=range]::-webkit-slider-runnable-track{height:44px;background:transparent;border:0}
.lots input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:28px;height:28px;margin-top:8px;border-radius:50%;background:var(--card);border:2px solid var(--accent);box-shadow:0 1px 4px rgba(0,0,0,.35)}
.lots input[type=range]::-moz-range-track{height:44px;background:transparent;border:0}
.lots input[type=range]::-moz-range-thumb{box-sizing:border-box;width:28px;height:28px;border-radius:50%;background:var(--card);border:2px solid var(--accent)}
.lots input[type=range]:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:8px}
.lots-lab{position:relative;height:34px;margin:2px 14px 0;font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.lots-lab span{position:absolute;white-space:nowrap;transform:translateX(-50%)}.lots-lab span.t{top:0}.lots-lab span.k{top:16px;color:var(--fg);font-weight:600}.lots-lab span.l{transform:none}.lots-lab span.r{transform:translateX(-100%)}
.chart{position:relative;margin-top:10px;outline:none}.chart:focus-visible{box-shadow:0 0 0 2px var(--accent);border-radius:8px}
.chart:not(.empty){border:1px solid var(--line);border-radius:12px;padding:6px 10px 4px}
.chart.empty{padding:6px 0}.chart[data-retry]{cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}
.chart svg{display:block;width:100%;touch-action:pan-y;-webkit-user-select:none;user-select:none}
.chart .grid{stroke:var(--line);stroke-width:1;shape-rendering:crispEdges}
.chart .ax{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.chart .wk,.chart .bd,.chart .vl{stroke-width:1;shape-rendering:crispEdges}.chart .vl{opacity:.8}
.chart .cu{stroke:var(--up);fill:var(--card)}.chart .cd{stroke:var(--down);fill:var(--down)}
.chart .ma{fill:none;stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}
.chart .m5{stroke:var(--fg)}.chart .m10{stroke:var(--ma10)}.chart .m20{stroke:var(--ma20)}.chart .m30{stroke:var(--ma30)}
.chart .ref{stroke:var(--muted);stroke-width:1;stroke-dasharray:4 3;shape-rendering:crispEdges}
.chart .stop{stroke:var(--neg);stroke-width:1;stroke-dasharray:4 3;shape-rendering:crispEdges}
.chart .rl{font-size:11px;fill:var(--fg);paint-order:stroke;stroke:var(--card);stroke-width:3px;stroke-linejoin:round}
.chart .xh{stroke:var(--muted);stroke-width:1;stroke-dasharray:2 2;shape-rendering:crispEdges}.chart .mk{fill:var(--accent)}
.chart .tl{fill:none;stroke:var(--fg);stroke-width:1.6;stroke-dasharray:7 3;stroke-linecap:round}
.chart .tlp{fill:none;stroke:var(--fg);stroke-width:1.4;stroke-dasharray:1.5 3;stroke-linecap:round;opacity:.85}
.chart .tla{fill:var(--card);stroke:var(--fg);stroke-width:1.4}.chart .tbu{fill:var(--up)}.chart .tbd{fill:var(--down)}
.chart .zl{stroke:var(--muted);stroke-width:1;shape-rendering:crispEdges}.chart .s1{fill:none;stroke-width:1.3;stroke-linejoin:round}
.chart .dif{stroke:var(--fg)}.chart .dea{stroke:var(--ma20)}.chart .mhu{fill:var(--up)}.chart .mhd{fill:var(--down)}
.chart .pdi{stroke:var(--up)}.chart .mdi{stroke:var(--down);stroke-dasharray:4 2}.chart .adx{stroke:var(--ma10)}
.chart .adxr{stroke:var(--ma30);stroke-dasharray:1.5 2}.chart .sl{font-size:10.5px;fill:var(--muted);font-variant-numeric:tabular-nums}
.chart .ro{font-size:13px;line-height:1.45;color:var(--muted);font-variant-numeric:tabular-nums;min-height:2.9em;margin:2px 0 0}
.chart .ro b{font-size:14px}.chart .ro .m{color:var(--fg)}
.key{display:inline-block;width:14px;height:2px;border-radius:1px;vertical-align:middle;margin-right:6px}
.key.m5{background:var(--fg)}.key.m10{background:var(--ma10)}.key.m20{background:var(--ma20)}.key.m30{background:var(--ma30)}
.key.dif{background:var(--fg)}.key.dea{background:var(--ma20)}.key.pdi{background:var(--up)}.key.mdi{background:var(--down)}.key.adx{background:var(--ma10)}.key.adxr{background:var(--ma30)}
.key.box{width:9px;height:9px;border-radius:2px}.key.cu{background:transparent;box-shadow:inset 0 0 0 1.5px var(--up)}.key.cd,.key.mhd{background:var(--down)}.key.mhu{background:var(--up)}
.key.dash{height:0;background:none;border-top:2px dashed var(--muted);border-radius:0}.key.dash.stop{border-top-color:var(--neg)}.key.dash.tl{border-top-color:var(--fg)}
.up{color:var(--up)}.down{color:var(--down)}
.tchips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.tchip{display:inline-block;padding:2px 10px;border-radius:999px;background:var(--chip);font-size:13px;white-space:nowrap}
.chip.hot{background:var(--accent);color:var(--accent-fg);font-weight:600}
.meta{font-size:14px;color:var(--muted);font-variant-numeric:tabular-nums}
.sgh{font-size:15px;margin:14px 0 0;padding-top:10px;border-top:1px solid var(--line)}
.near{line-height:1.5;margin:2px 0}
.rk{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;padding:0 6px;border-radius:999px;background:var(--chip);font-size:13px;font-weight:700;font-variant-numeric:tabular-nums}
.prob{margin:2px 0}.prob b{font-variant-numeric:tabular-nums}
.qt .sellx{margin-top:2px}.qt[data-sq]{margin:4px 0}
.dipst{color:var(--muted);line-height:1.5;margin:-2px 0 6px}.dipst b{color:var(--fg);font-weight:600}
.axb{margin:10px 0 0;padding:8px 12px 4px;border:1px solid var(--line);border-radius:12px;background:var(--bg)}.axb.hot{border-color:var(--neg)}
.axh{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:2px 10px;padding-bottom:4px}
.axr{display:grid;grid-template-columns:4.4em minmax(0,1fr);gap:0 10px;padding:6px 0;border-top:1px solid var(--line)}
.axk{font-size:13px;color:var(--muted);line-height:1.75}.axv{min-width:0;font-size:15px;line-height:1.5}
.axm{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 2px}.axm .chip{font-variant-numeric:tabular-nums}
.chip.bad{background:transparent;box-shadow:inset 0 0 0 1px var(--neg);color:var(--neg);font-weight:600}
.dots{display:inline-flex;gap:3px;margin-right:6px;vertical-align:1px}
.dots i{width:8px;height:8px;border-radius:50%;box-shadow:inset 0 0 0 1.5px var(--muted)}.dots i.on{background:var(--neg);box-shadow:none}
.axn{padding:6px 0 2px;border-top:1px solid var(--line)}
.axd>summary{font-size:13px}.axd ul{margin:2px 0 6px;padding-left:18px;font-size:13px;line-height:1.55;color:var(--muted)}
.axt{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:6px;margin:2px 0 8px}
.axt>div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:6px 8px 5px;min-width:0}
.axt .l{font-size:12px;color:var(--muted);line-height:1.4}.axt .s{font-size:12px;color:var(--muted);line-height:1.4;overflow-wrap:anywhere}
.axt .v{font-size:19px;font-weight:700;line-height:1.3;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.axt .bad{border-color:var(--neg)}.axt .bad .v{color:var(--neg)}
.pl{margin:10px 0;padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);font-size:14px;line-height:1.55;
white-space:normal;font-variant-numeric:tabular-nums}.pl .up{color:var(--up)}.pl .down{color:var(--down)}.pl .muted{font-size:13px}
.chart .live{stroke-dasharray:3 2}.chart .lv{font-size:10px;fill:var(--fg);paint-order:stroke;stroke:var(--card);stroke-width:3px;stroke-linejoin:round}
details.kl>summary{color:var(--accent);font-size:14px}
.legend{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:13px;color:var(--muted);margin:2px 0}
.chart table{border-collapse:collapse;font-size:13px;width:100%;font-variant-numeric:tabular-nums;margin-top:4px}
.chart td,.chart th{padding:4px 6px;border-top:1px solid var(--line);text-align:right;font-weight:400}
.chart td:first-child,.chart th:first-child{text-align:left}.chart th{color:var(--muted)}
.stepper{display:flex;align-items:center;gap:12px;margin:8px 0}.stepper output{flex:1;text-align:center}
dialog{border:0;padding:0;background:var(--card);color:var(--fg);width:100%;max-width:min(720px,100%);max-height:88vh;
margin:auto auto 0;border-radius:18px 18px 0 0;box-shadow:0 -8px 30px rgba(0,0,0,.25)}
dialog::backdrop{background:rgba(0,0,0,.45)}
.sheet{padding:18px max(16px,env(safe-area-inset-right)) calc(env(safe-area-inset-bottom) + 18px) max(16px,env(safe-area-inset-left));
overflow:auto;white-space:pre-line}
@media (min-width:760px){dialog{margin:auto;border-radius:18px;max-width:520px}}
fieldset{border:0;margin:8px 0;padding:0;white-space:normal}
fieldset label{display:flex;align-items:center;gap:10px;min-height:44px;border-top:1px solid var(--line)}fieldset label:first-of-type{border-top:0}
input[type=radio]{width:20px;height:20px;accent-color:var(--accent)}
.row{display:flex;gap:10px;margin-top:14px;white-space:normal}.row .btn{flex:1}
.toast{position:fixed;left:16px;right:16px;bottom:calc(env(safe-area-inset-bottom) + 16px);z-index:20;max-width:688px;margin:0 auto;
background:var(--fg);color:var(--bg);padding:12px 16px;border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.25);white-space:pre-line}
.toast.bad{background:var(--neg);color:#fff}
.code{font:700 34px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:3px;text-align:center;margin:8px 0}
.qr{display:flex;justify-content:center;margin:8px 0}.qr img{width:220px;height:220px;background:#fff;padding:10px;border-radius:12px}
footer{margin:16px 0;color:var(--muted);font-size:13px}
"""

_NET_JS = """
const TMO = 15000;                                                        // 15 秒没有回应就不再等（Mac 睡眠时请求会一直挂着）
function timed(p, ac){
  let tid;
  const to=new Promise((_, rej)=>{ tid=setTimeout(()=>{ rej(Object.assign(new Error('timeout'), {name:'Timeout'})); try{ if(ac) ac.abort(); }catch(x){} }, TMO); });
  return Promise.race([p, to]).finally(()=>clearTimeout(tid));
}
function req(url, opt){                                                   // → {r, j}（连内容一起 15 秒内读完；超时抛 name = 'Timeout'）
  const ac=('AbortController' in window) ? new AbortController() : null;      // j = null：内容读不出来 / 不是 JSON（连接中途断了也是）
  return timed((async()=>{ const r=await fetch(url, Object.assign({}, opt||{}, ac ? {signal:ac.signal} : {})); let j=null; try{ j=await r.json(); }catch(e){} return {r:r, j:j}; })(), ac);
}
"""

_JS = """
const CFG = __CFG__;
const $ = s => document.querySelector(s);
const fmt = n => Number(n).toLocaleString('ja-JP');
const yen = v => '¥' + fmt(Math.round(v));
function toast(t, bad, sticky){const m=$('#toast');m.textContent=t+(sticky?'\\n（点一下关闭）':'');m.className='toast'+(bad?' bad':'');m.hidden=false;
  clearTimeout(toast.h); if(!sticky) toast.h=setTimeout(()=>{m.hidden=true;}, bad?9000:6000);}
function busy(on){document.querySelectorAll('button').forEach(b=>{if(on){b.dataset.was=b.disabled?'1':'';b.disabled=true;}else{b.disabled=b.dataset.was==='1';}});}
const HALT_TIP = CFG.remote ? '人不在 Mac 旁边时：在 claude.ai 的云端对话里说「停 / 今天不要下单」（Mac 的执行器下一次运行会停）'
                            : '在 Mac 的 Claude 对话里说「停 / 今天不要下单」';
async function api(path, body){
  busy(true);
  const halt = path==='/api/halt', where = path==='/api/request' ? '在「手动指令」里确认' : '再看一下';
  const fail = (t, sticky) => { toast(halt ? t+'\\n'+HALT_TIP : t, true, halt || sticky); return null; };   // HALT 失败：每种都提示云端的「停」、不自动消失
  try{
    const h={'Content-Type':'application/json'}; h[CFG.auth.h]=CFG.auth.v;
    const x=await req(path,{method:'POST',headers:h,body:JSON.stringify(body||{}),credentials:'same-origin',cache:'no-store'});
    const r=x.r, j=x.j;
    busy(false);
    if(r.ok && !j) return fail(halt ? 'HALT 可能已经建好，但回应读不出来：刷新后看有没有「HALT 生效中」'
                                    : '回应读不出来：不确定有没有生效 —— 刷新后'+where+'，不要直接再点一次', true);
    if(!r.ok || !j.ok){
      if(r.status===401){ toast((j && j.msg) || '这台设备没被认出来：正在刷新…', true); setTimeout(()=>location.reload(),1500); return null; }
      return fail((j && j.msg) || ('没写成（HTTP '+r.status+'）'));
    }
    return j;
  }catch(e){
    busy(false);
    if(e && e.name==='Timeout'){                                           // 请求可能已经到了 Mac：不确定有没有写进去
      if(halt) return fail(CFG.remote ? 'HALT 可能没送到：超过 15 秒没有回应（Mac 可能在睡眠）' : 'HALT 可能没写成：面板超过 15 秒没有回应');
      return fail(CFG.remote ? '超过 15 秒没有回应（Mac 可能在睡眠）：不确定有没有'+(path==='/api/request' ? '写进去' : '生效')+' —— Mac 醒来后刷新，'+where+'，不要直接再点一次'
                             : '面板超过 15 秒没有回应：不确定有没有'+(path==='/api/request' ? '写进去' : '生效')+' —— 刷新后'+where+'，不要直接再点一次');
    }
    return fail((halt ? 'HALT 没送到：' : '')+'连不上面板：'+e+'\\n（Mac 睡着了、面板没运行，或手机的 Tailscale 没连上）');
  }
}
function done(j){ if(!j) return; toast(j.msg || '已写'); setTimeout(()=>location.reload(), 2200); }
function sheet(id){ const d=$(id); if(d.showModal){ if(!d.open) d.showModal(); } else d.setAttribute('open',''); return d; }
function closeAll(){ document.querySelectorAll('dialog[open]').forEach(d=>{ if(d.close) d.close(); else d.removeAttribute('open'); }); }
let ASK=null, CUR=null;
function syen(v){ return (v<0 ? '−' : '+')+'¥'+fmt(Math.abs(Math.round(v))); }
function spc(v){ return (v<0 ? '−' : '+')+Math.abs(v).toFixed(2)+'%'; }        // 预计收益的百分比（负号与金额一样用 −）
let QD = null;                                                             // 最近一次取到的现价（/api/quotes）：卖出的预计收益优先用它
function estOf(t){ return (QD && QD.rows && QD.rows[t] && QD.rows[t].est) || (CFG.est||{})[t] || null; }
function jfee(x){                                                          // 一笔的手续费（立花 個別コース；与 manual_orders.fee_jp 相同）
  x=Math.abs(+x||0); if(!(x>0)) return 0;
  for(const [cap, f] of (CFG.fee||[])) if(x<=cap) return +f;
  return 0;
}
function estPart(e, k){                                                    // 卖出一部分（k 股 / 口）的预计收益：与 manual_orders.sell_estimate 同一个算法
  if(!e || !(k>0) || e.entry_px==null || !(e.n>0)) return null;
  const proceeds=e.px*k, base=((e.cost||0)+(e.buy_fee||0))*k/e.n, pnl=proceeds-jfee(proceeds)-base;
  return {k:k, proceeds:proceeds, pnl:pnl, pct: base>0 ? pnl/base*100 : null};
}
function estLine(e, k, u){                                                 // 调仓（减）的预览一行
  const p=estPart(e, k); if(!p) return '';
  return '\\n这 '+fmt(k)+' '+u+'预计收益 '+syen(p.pnl)+(p.pct!=null ? '（'+spc(p.pct)+'）' : '')+'：按'+(e.src==='live' ? '现价 ' : '最近收盘 ')
    +pxs(e.px)+'，已扣两边手续费，税前';
}
function plBox(el, e){                                                     // 卖出全部的预计收益（几行；收益那行涨红跌绿）
  el.textContent=''; el.hidden=!(e && e.lines && e.lines.length); if(el.hidden) return;
  for(const ln of e.lines){
    const cls = ln.indexOf('预计收益')===0 ? (e.pnl>=0 ? 'up' : 'down') : (ln.indexOf('已扣')===0 || ln.indexOf('卖出手续费')===0 ? 'muted' : null);
    nd('div', cls, ln, el);
  }
}
function ask(title, body, okText, opt){
  opt=opt||{}; $('#ask-title').textContent=title; $('#ask-body').textContent=body; plBox($('#ask-pl'), opt.pl||null);
  const ok=$('#ask-ok'); ok.textContent=okText||'确定'; ok.className='btn '+(opt.danger?'danger':'primary');
  const inp=$('#ask-input'); inp.hidden=!opt.input; inp.value=''; inp.placeholder=opt.input||'';
  sheet('#dlg-ask'); return new Promise(res=>{ ASK=res; });
}
const NOTE = CFG.paper ? '\\n\\n模拟账户：手动操作后会和云端模拟盘不一致。' : CFG.real ? '\\n\\n★ 真钱（立花本番）：执行器会在立花真的下单。' : '';
function coreShow(){ const r=$('#core-pct'); if(r) $('#core-val').textContent=r.value+'%'; }
// ── 调仓（股数 / 金额 / 占权益 %）：按最近收盘估算；执行器下单时按当时的价格再算一次；调仓条按单元（LOT 股）分格 ──
const LOT = CFG.lot || 100;
let ADJ = null, ADJ_RULE = null;                                           // ADJ_RULE：调仓对话框里个股那行说明的原文（核心 ETF 换掉、个股换回）
function pctOf(n){ return CFG.eq>0 && ADJ.px>0 ? (n*ADJ.px/CFG.eq*100).toFixed(1)+'%' : '—'; }
function ALOT(){ return (ADJ && ADJ.lot) || LOT; }                         // 一个单元几股（核心 ETF：几口）
function UW(){ return (ADJ && ADJ.core) ? '口' : '股'; }
function cpctOf(n){                                                        // 核心 ETF：目标口数 → 闲置资金比例 %（与 manual_orders.core_pct_for 相同）
  if(!(ADJ.u100>0)) return 0;
  const m=Math.min(n, ADJ.u100), L=ALOT(); let p=Math.ceil(m/ADJ.u100*10000-1e-9)/100;
  if(Math.floor(ADJ.u100*p/100/L+1e-9)*L!==m) p=Math.round(m/ADJ.u100*10000)/100;
  return p;
}
function adjCap(){                                                          // 个股：单只上限 cap%；核心 ETF：规则目标额（比例 100%）
  if(ADJ.core) return Math.floor((ADJ.u100||0)/ALOT())*ALOT();
  return ADJ.px>0 && CFG.eq>0 ? Math.floor(CFG.eq*CFG.cap/100/ADJ.px/ALOT()+1e-9)*ALOT() : 0;
}
function adjTarget(){
  const v=parseFloat($('#adj-val').value); if(!(v>=0) || !isFinite(v)) return null;
  let raw;
  if(ADJ.unit==='shares') raw=v; else if(!(ADJ.px>0)) return null; else if(ADJ.unit==='yen') raw=v/ADJ.px; else raw=CFG.eq*v/100/ADJ.px;
  return Math.max(0, Math.floor(raw/ALOT()+1e-9)*ALOT());
}
function adjShow(n){
  const u=ADJ.unit, e=$('#adj-val');
  e.value = u==='shares' ? n : u==='yen' ? Math.round(n*ADJ.px) : (CFG.eq>0 ? (n*ADJ.px/CFG.eq*100).toFixed(1) : 0);
}
function adjUnit(u){
  const n=adjTarget(); ADJ.unit=u;
  document.querySelectorAll('#adj-seg button').forEach(b=>b.setAttribute('aria-pressed', b.dataset.u===u ? 'true' : 'false'));
  $('#adj-unit').textContent = {shares:UW(), yen:'円', pct:'%'}[u];
  $('#adj-val').step = u==='shares' ? ALOT() : u==='yen' ? 1000 : 0.1;
  adjShow(n==null ? ADJ.shares : n); adjPrev();
}
function adjBar(){                                                         // 调仓条按「一次最少能买卖的股数」（1 个单元 = LOT 股 / 口）分格
  const r=$('#adj-range'), bar=$('#adj-bar'), lab=$('#adj-lab'), note=$('#adj-note'); if(!r || !bar || !ADJ) return;
  const LOT=ALOT(), U=UW();
  const n=Math.max(1, Math.round(+r.max/LOT)), have=Math.round(ADJ.shares/LOT), tgt=Math.round(+r.value/LOT), capN=Math.floor(adjCap()/LOT);
  const G=Math.ceil(n/50);                                                  // 单元太多（> 50）时几格并成一格，手机上也看得清
  bar.textContent='';
  for(let a=0; a<n; a+=G){
    const b=Math.min(n, a+G);                                               // 这一格 = 第 a+1〜b 个单元
    const cls = (tgt<have && tgt<b && a<have) ? 'cut' : (have<tgt && have<b && a<tgt) ? 'add'      // 这一格碰到「要卖的」/「要加的」那一段
              : (a<Math.min(have, tgt)) ? 'keep' : (a>=Math.max(capN, have)) ? 'over' : '';
    nd('i', cls, null, bar);
  }
  lab.textContent='';
  const at=(j, text, cls)=>{ const p=j/n*100, e=nd('span', cls, text, lab); e.style.left=p+'%';
    if(p<=0) e.classList.add('l'); else if(p>=100) e.classList.add('r'); };
  if(n<=8 && G===1){ for(let j=0;j<=n;j++) at(j, fmt(j*LOT), 't'); }
  else { at(0, '0', 't'); at(n, fmt(n*LOT)+' '+U, 't'); }
  const pk=Math.min(100, have/n*100), num=n<=8 ? '' : ' '+fmt(ADJ.shares);            // ▲ 对准现在的位置：左半边往右写、右半边往左写（不出框）
  const kl=nd('span', 'k', pk<=60 ? '▲现在'+num : '现在'+num+' ▲', lab);
  kl.style.left=pk+'%'; kl.style.transform = pk<=60 ? 'translateX(-6px)' : 'translateX(calc(-100% + 6px))';
  const lim = ADJ.core ? '规则目标额（比例 100%）' : '单只上限 '+CFG.cap+'%';
  const capTxt = capN>=n ? '最右边 = '+lim
               : capN<have ? lim+' ≈ '+fmt(capN*LOT)+' '+U+'（现在已超过，只能减）'
               : lim+' ≈ '+fmt(capN*LOT)+' '+U;
  note.textContent='一格 = '+fmt(G*LOT)+' '+U+(G>1 ? '（拖动按 '+fmt(LOT)+' '+U+'一步）' : '')
    +' · 半透明 留着 · 实心 要加 · 红框 要卖 · 斜线 超过上限 · '+capTxt;
  r.setAttribute('aria-valuetext', '目标 '+fmt(tgt*LOT)+' '+U+'（'+tgt+' 个单元）；现在 '+fmt(ADJ.shares)+' '+U);
}
function adjPrev(){
  const go=$('#adj-go'), out=$('#adj-prev'), c=ADJ, cap=adjCap(), n=adjTarget();
  go.className='btn primary';
  const r=$('#adj-range'); if(n!=null) r.value=Math.min(+r.max, n);
  adjBar();
  if(n==null){ out.textContent='输入目标（'+UW()+'数 / 金额 / 占总权益 %）'; go.textContent='确认'; go.disabled=true; return; }
  if(c.core){ adjPrevCore(n); return; }
  if(n===c.shares){
    out.textContent='换算还是 '+fmt(n)+' 股：不用调';
    go.textContent='确认'; go.disabled=true; return;
  }
  if(n<c.shares){
    const k=c.shares-n;
    out.textContent='卖出 '+fmt(k)+' 股（约 '+yen(k*c.px)+'）：'+fmt(c.shares)+' → '+fmt(n)+' 股，约占权益 '+pctOf(n)
      +estLine(estOf(c.t), k, '股')+'\\n'+CFG.when+'卖出'+(n===0 ? '（= 全部卖出，不设「不买回」）' : '');
    go.textContent='确认卖出 '+fmt(k)+' 股'; go.className='btn danger'; go.disabled=false; return;
  }
  let t=n, note='';
  if(t>cap){ t=Math.max(cap, c.shares); note='\\n★ 超过单只上限 '+CFG.cap+'%：截到 '+fmt(t)+' 股'; }
  const k=t-c.shares;
  if(k<=0){
    const full=CFG.eq>0 && c.shares*c.px/CFG.eq*100>=CFG.cap;
    out.textContent = full ? '已经到单只上限 '+CFG.cap+'%：不能再加' : '再加 '+fmt(LOT)+' 股就超过单只上限 '+CFG.cap+'%：不能再加';
    go.textContent='确认'; go.disabled=true; return;
  }
  out.textContent='买入 '+fmt(k)+' 股（约 '+yen(k*c.px)+'）：'+fmt(c.shares)+' → '+fmt(t)+' 股，约占权益 '+pctOf(t)+note
    +'\\n'+CFG.when+'买入（最高 '+yen(c.px*1.03)+' = 收盘 ×1.03）；钱不够先卖核心 ETF；只做一次';
  go.textContent='确认买入 '+fmt(k)+' 股'; go.disabled=false;
}
function coreFx(q, skip, lab){                                             // 同一个比例对别的核心 ETF（规则同时拿两只以上时）：会变的列出来
  const C=CFG.cores||{}, out=[];
  for(const t of Object.keys(C)){
    if(t===skip) continue;
    const c=C[t], L=c.lot||1, tg=Math.floor(c.u100*q/100/L+1e-9)*L;
    if(tg!==c.cur && (c.cur>0 || tg>0)) out.push(t+' '+fmt(c.cur)+' → '+fmt(tg)+' 口');
  }
  return out.length ? '\\n'+(lab||'★ 同一比例也用在：')+out.join('、') : '';
}
function adjPrevCore(n){                                                   // 核心 ETF：目标口数 → 闲置资金比例（之后每天按它）
  const go=$('#adj-go'), out=$('#adj-prev'), c=ADJ, cap=adjCap();
  let t=n, note='';
  if(t>cap){ t=Math.max(cap, 0); note='\\n★ 超过规则目标额（比例 100%）：截到 '+fmt(t)+' 口'; }
  const q=cpctOf(t), ratio='\\n闲置资金比例 '+c.cpct+'% → '+q+'%（之后每天按规则目标额 × '+q+'%）'+coreFx(q, c.t);
  if(t===c.shares){ out.textContent='现在就是 '+fmt(t)+' 口：不用调'+note; go.textContent='确认'; go.disabled=true; return; }
  if(q===c.cpct){
    out.textContent='换算成闲置资金比例还是 '+q+'%：不用调'+note; go.textContent='确认'; go.disabled=true; return;
  }
  const k=Math.abs(t-c.shares), sell=t<c.shares;
  out.textContent=(sell ? '卖出 ' : '买入 ')+fmt(k)+' 口（约 '+yen(k*c.px)+'）：'+fmt(c.shares)+' → '+fmt(t)+' 口，约占权益 '+pctOf(t)
    +(sell ? estLine(estOf(c.t), k, '口') : '')+note+ratio+'\\n'+CFG.when+(sell ? '卖出' : '买入');
  go.textContent=(sell ? '确认卖出 ' : '确认买入 ')+fmt(k)+' 口'; go.className=sell ? 'btn danger' : 'btn primary'; go.disabled=false;
}
// ── 买入（建议的股票 → 手动买入指令）：按规则的仓位 / 股数 / 金额 / 占权益 %；执行器下单时按当时的价格再算 ──
let BUY = null;
const bpct = n => CFG.eq>0 && BUY.px>0 ? (n*BUY.px/CFG.eq*100).toFixed(1)+'%' : '—';
function buyCap(){ return BUY.px>0 && CFG.eq>0 ? Math.floor(CFG.eq*CFG.cap/100/BUY.px/BUY.lot+1e-9)*BUY.lot : 0; }
function buyTarget(){
  if(BUY.unit==='rule') return BUY.rule;
  const v=parseFloat($('#buy-val').value); if(!(v>0) || !isFinite(v)) return null;
  let raw; if(BUY.unit==='shares') raw=v; else if(!(BUY.px>0)) return null; else if(BUY.unit==='yen') raw=v/BUY.px; else raw=CFG.eq*v/100/BUY.px;
  return Math.max(0, Math.floor(raw/BUY.lot+1e-9)*BUY.lot);
}
function buyShow(n){
  const u=BUY.unit, e=$('#buy-val');
  e.value = u==='shares' ? n : u==='yen' ? Math.round(n*BUY.px) : (CFG.eq>0 ? (n*BUY.px/CFG.eq*100).toFixed(1) : 0);
}
function buyUnit(u){
  let n=buyTarget(); BUY.unit=u;
  if(n!=null) n=Math.min(n, Math.max(buyCap(), BUY.lot));            // 换单位时不把超过单只上限的数带过去
  document.querySelectorAll('#buy-seg button').forEach(b=>b.setAttribute('aria-pressed', b.dataset.u===u ? 'true' : 'false'));
  $('#buy-row').hidden = u==='rule';
  if(u!=='rule'){
    $('#buy-unit').textContent = {shares:'股', yen:'円', pct:'%'}[u];
    $('#buy-val').step = u==='shares' ? BUY.lot : u==='yen' ? 1000 : 0.1;
    buyShow(n==null || n<=0 ? (BUY.rule || BUY.lot) : n);
  }
  buyPrev();
}
function buyPrev(){
  const go=$('#buy-go'), out=$('#buy-prev');
  let n=buyTarget();
  if(n==null){ out.textContent='输入要买多少（股数 / 金额 / 占总权益 %）'; go.textContent='确认买入'; go.disabled=true; return; }
  const cap=buyCap(); let note='';
  if(n>cap){ n=cap; note='\\n★ 超过单只上限 '+CFG.cap+'%：截到 '+fmt(n)+' 股'; }
  if(n<=0){
    out.textContent = BUY.unit==='rule' ? '按规则的仓位不够买 1 个单元（'+fmt(BUY.lot)+' 股 ≈ '+yen(BUY.lot*BUY.px)+'）：改用股数 / 金额试试'
      : '不够 1 个单元（'+fmt(BUY.lot)+' 股 ≈ '+yen(BUY.lot*BUY.px)+'）';
    go.textContent='确认买入'; go.disabled=true; return;
  }
  out.textContent='买入约 '+fmt(n)+' 股 · 约 '+yen(n*BUY.px)+' · 约占权益 '+bpct(n)+note
    +'\\n'+CFG.when+'买入（最高 '+yen(BUY.limit||BUY.px*1.03)+' = 收盘 ×1.03）；名额满 / 价格更高 → 不买；只做一次';
  go.textContent='确认买入约 '+fmt(n)+' 股'; go.disabled=false;
}
document.addEventListener('input', e=>{
  if(e.target.id==='core-pct') coreShow();
  if(e.target.id==='adj-val') adjPrev();
  if(e.target.id==='adj-range'){ adjShow(+e.target.value); adjPrev(); }
  if(e.target.id==='buy-val') buyPrev();
});
document.addEventListener('DOMContentLoaded', ()=>{ const d=$('#dlg-ask'); if(d) d.addEventListener('close', ()=>{ if(ASK){ const r=ASK; ASK=null; r({ok:false}); } }); });
document.addEventListener('keydown', e=>{ const b=e.target;                // 「点这里再试」也能用键盘（Enter / 空格）
  if((e.key==='Enter' || e.key===' ') && b && b.matches && b.matches('.chart[data-retry]')){ e.preventDefault(); b.click(); } });
document.addEventListener('click', async e=>{
  if(e.target.closest('#toast')){ $('#toast').hidden=true; return; }       // 提示：点一下关闭
  const rk=e.target.closest('.chart[data-retry]');
  if(rk){ rk.removeAttribute('data-retry'); showK(rk); return; }           // K 线取不到 / 超时：点一下再取（同一只票已经在取 → 等那一个）
  const b=e.target.closest('[data-act]'); if(!b) return;
  const a=b.dataset.act, d=b.dataset;
  if(a==='reload'){ location.reload(); return; }
  if(a==='close'){ closeAll(); return; }
  if(a==='ask-ok'){ const v=$('#ask-input').value, r=ASK; ASK=null; closeAll(); if(r) r({ok:true, value:v}); return; }
  if(a==='sell'){
    CUR={t:d.t, shares:+d.shares};
    $('#sell-title').textContent='卖出 '+d.t+(d.name?' '+d.name:'');
    $('#sell-desc').textContent='全部 '+fmt(+d.shares)+' 股 · '+CFG.when+'卖出'+NOTE;
    plBox($('#sell-pl'), estOf(d.t));                                      // 买入成交价 → 现价 / 预计卖出 → 预计收益与收益率
    sheet('#dlg-sell'); return;
  }
  if(a==='sell-go'){
    const bd=document.querySelector('input[name=bd]:checked').value; closeAll();
    done(await api('/api/request',{book:CFG.book, kind:'sell', ticker:CUR.t, block_days:parseInt(bd,10)})); return;
  }
  if(a==='adj'){
    const core=d.core==='1';
    ADJ={t:d.t, shares:+d.shares, px:+d.px, unit:'shares', core:core, lot:core ? (+d.lot||1) : LOT, u100:+d.u100||0, cpct:+d.cpct||0, approx:d.approx==='1'};
    $('#adj-title').textContent='调仓 '+d.t+(d.name?' '+d.name:'');
    $('#adj-cur').textContent='现在 '+fmt(ADJ.shares)+' '+UW()+' · 约 '+yen(ADJ.shares*ADJ.px)+' · 约占权益 '+pctOf(ADJ.shares)
      +(core ? ' · 闲置资金比例 '+ADJ.cpct+'%' : '');
    $('#adj-u-sh').textContent=UW()+'数';
    const ru=$('#adj-rule'); if(ru){ if(ADJ_RULE==null) ADJ_RULE=ru.innerHTML;
      if(core) ru.textContent='核心 ETF 按「闲置资金比例」调：比例 = 目标 ÷ 规则目标额（最右边 = 100% = 照规则）；之后每天按这个比例，改回 100% 就照规则。'
        +(ADJ.approx ? '规则目标额执行器还没算过：100% 先按现在的口数估算，下一次决策用准确的数（口数可能再小调）。' : '')+NOTE.trim();
      else { ru.innerHTML=ADJ_RULE; $('#adj-cap').textContent=CFG.cap; } }
    $('#adj-val').value='';                                                // 从这只票现在的股数开始（不带上一只票输过的数）
    const L=ALOT(), r=$('#adj-range'); r.max=Math.max(1, Math.ceil(Math.max(adjCap(), ADJ.shares, L)/L))*L; r.step=L; r.value=ADJ.shares;   // 整数个单元
    adjUnit('shares'); sheet('#dlg-adj'); return;
  }
  if(a==='core-sell'){
    const q=await ask('卖出全部 '+d.t+(d.name?' '+d.name:''), '全部 '+fmt(+d.shares)+' 口：'+CFG.when+'卖出'+coreFx(0, d.t)
      +'\\n卖出后停买闲置资金 ETF（钱留现金）；出现买入信号会提醒你，你点「确认买入」才买'+NOTE, '卖出', {danger:true, pl:estOf(d.t)});
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'sell', ticker:d.t})); return;
  }
  if(a==='core-resume'){                                                   // 停买后确认买入：闲置资金比例 0% → 100%（照规则）
    const q=await ask('确认买入：恢复闲置资金买入 ETF', '闲置资金比例 0% → 100%（照规则）'+coreFx(100, '', '会买：')
      +'\\n'+CFG.when+'买入；之后每天照规则调'+NOTE, '确认买入');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'core', pct:100})); return;
  }
  if(a==='adj-unit'){ adjUnit(d.u); return; }
  if(a==='adj-step'){ const n=adjTarget(); adjShow(Math.max(0, (n==null ? ADJ.shares : n)+(+d.d)*ALOT())); adjPrev(); return; }
  if(a==='adj-go'){
    const n=adjTarget(); if(n==null || n===ADJ.shares) return;
    const v = ADJ.unit==='shares' ? n : parseFloat($('#adj-val').value);
    closeAll(); done(await api('/api/request',{book:CFG.book, kind:'adjust', ticker:ADJ.t, unit:ADJ.unit, value:v})); return;
  }
  if(a==='ktf' || a==='ksub'){                                            // 一张图自己的周期 / 小图（别的图不变）；也记成新打开的图的默认
    const bx=b.closest('.chart[data-t]'); if(!bx || !(a==='ktf' ? TFS : SUBS)[d.v]) return;
    if(a==='ktf'){ bx.dataset.tf=TF=d.v; try{ localStorage.setItem('qbreak.tf', TF); }catch(x){} }
    else { bx.dataset.sub=SUB=d.v; try{ localStorage.setItem('qbreak.sub', SUB); }catch(x){} }
    drawK(bx);
    const nb=bx.querySelector('[data-act="'+a+'"][data-v="'+d.v+'"]'); if(nb) nb.focus({preventScroll:true});   // 重画后焦点留在刚按的按钮上（键盘用）
    return;
  }
  if(a==='buy'){
    BUY={t:d.t, px:+d.px, lot:+d.lot||LOT, rule:+d.rule||0, limit:+d.limit||0, unit:'rule'};
    $('#buy-title').textContent='买入 '+d.code+(d.name ? ' '+d.name : '');
    $('#buy-sig').textContent=(d.sig==='1' ? '今天出了买入信号（'+d.rtext+'）' : '★ '+d.status+'：还没有买入信号，规则不会买 —— 是你自己的决定')
      +(d.warn ? '\\n★ '+d.warn : '')+NOTE;
    $('#buy-cap').textContent=CFG.cap;
    buyUnit('rule'); sheet('#dlg-buy'); buyLive(); loadSQ(); return;            // 现价 + 现在买按什么价（Yahoo，约晚 20 分钟）
  }
  if(a==='buy-unit'){ buyUnit(d.u); return; }
  if(a==='buy-step'){ if(BUY.unit!=='rule'){ const n=buyTarget(); buyShow(Math.max(BUY.lot, (n==null||n<=0 ? BUY.lot : n)+(+d.d)*BUY.lot)); } buyPrev(); return; }
  if(a==='buy-go'){
    const n=buyTarget(); if(!n) return;
    const body={book:CFG.book, kind:'buy', ticker:BUY.t, unit:BUY.unit};
    if(BUY.unit!=='rule') body.value = BUY.unit==='shares' ? Math.min(n, buyCap()) : parseFloat($('#buy-val').value);
    closeAll(); done(await api('/api/request', body)); return;
  }
  if(a==='core-step'){ const r=$('#core-pct'); r.value=Math.max(0, Math.min(100, parseFloat(r.value)+parseFloat(d.d))); coreShow(); return; }
  if(a==='core'){
    const v=parseFloat($('#core-pct').value);
    const q=await ask('闲置资金比例 '+v+'%', '核心 ETF 的目标额 = 规则算出的 × '+v+'%，下一次决策起生效'+(v<100?'（多出来的留现金）':'')+NOTE, '保存');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'core', pct:v})); return;
  }
  if(a==='cancel-order'){                                                 // 撤单：执行器今天已经发到交易所、还挂着的单（面板马上叫执行器撤）
    const q=await ask('撤单 '+(d.side==='BUY'?'买 ':'卖 ')+d.t+' '+fmt(+d.qty)+(d.core==='1'?' 口':' 股'),
      (d.core==='1' ? '核心 ETF 的单：已经成交的部分撤不了；下一次决策照规则 / 闲置资金比例重新算目标，可能再买 / 再卖（要少拿用「闲置资金比例」）。'
                    : '已经成交的部分撤不了；撤掉的卖单如果规则明天还要卖会再下；撤掉的个股买单不再买。')+(CFG.paper ? '' : '\\n马上发撤单到立花（之后看「今天的单」的状态）'),
      '撤单', {danger:true});
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'cancel_order', cid:d.cid})); return;
  }
  if(a==='cancel'){
    const q=await ask('撤回 '+d.id, d.placed==='1' ? '之后不再下。已经发到交易所的单用「今天的单」的「撤单」撤。' : '还没下单：撤回之后不会下。', '撤回');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'cancel', target:d.id})); return;
  }
  if(a==='unblock'){
    const q=await ask('解除 '+d.t+' 的不自动买回', '之后有买入信号就会按规则买。', '解除');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'unblock', ticker:d.t})); return;
  }
  if(a==='flow'){                                                         // 〔77〕C UX-14：登记入金 / 出金（只影响收益的计算）
    const v=($('#flow-jpy').value||'').replace(/[,¥\\s]/g,''), n=+v;
    if(!v || !isFinite(n) || Math.abs(n)<1){ toast('金额：入金写正数、出金写负数（例 300000 / -300000）', true); return; }
    const rs=!!($('#flow-reserve')||{}).checked && n<0;
    const q=await ask((n>0?'登记入金 ':'登记出金 ')+(n>0?'+':'−')+'¥'+fmt(Math.abs(n))+(rs?'（预留）':''), '日期 '+($('#flow-date').value||'今天')+'。'+(rs ? '预留：到账前的决策按扣掉这笔钱算（个股仓位变小、闲置资金 ETF 不买回；现金不够先卖核心 ETF）；到账后自动解除。' : '只影响收益的计算与「现金突然变化」的提醒，不下单。'), '登记');
    const rsv=!!($('#flow-reserve')||{}).checked;
    if(rsv && n>0){ toast('预留只用于出金（写负数）', true); return; }
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'flow', jpy:n, date:$('#flow-date').value, note:$('#flow-note').value, reserve:rsv})); return;
  }
  if(a==='halt'){
    const q=await ask('停止下单（HALT）', '全部账本（模拟和立花）从下一次运行起不下单、持仓不动。\\n已经发到交易所的单不会被撤（要撤：「今天的单」的「撤单」，或立花网站 / 手机网站）。\\n这里只能停：恢复只在 Mac 上（在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」）。', '停止下单', {danger:true, input:'原因（可不填）'});
    if(q.ok) done(await api('/api/halt',{reason:q.value})); return;
  }
  if(a==='pair-new'){
    const j=await api('/api/pair/new',{}); if(!j) return;
    $('#pair-code').textContent=j.code; $('#pair-exp').textContent=j.expires+' JST 前有效（只能用一次；输错 5 次作废）';
    const img=$('#pair-qr'); if(j.qr){ img.src=j.qr; img.hidden=false; } else img.hidden=true;
    $('#pair-url').textContent = j.url ? '手机：用相机扫二维码，或 Safari 打开 '+j.url+' 输入上面的配对码' : '手机访问还没打开：先在 Mac 的 Claude 对话里说「打开手机操作」（bash scripts/liveu.sh phone on），手机才连得上';
    $('#pair-box').hidden=false; return;
  }
  if(a==='revoke'){
    const q=await ask('取消「'+d.name+'」的配对', '这台设备之后打不开面板（要用的话重新配对）。', '取消配对', {danger:true});
    if(q.ok) done(await api('/api/device/revoke',{id:d.id})); return;
  }
  if(a==='unpair'){
    const q=await ask('退出这台设备', '之后这台设备要重新配对才能打开（在 Mac 的操作面板上生成配对码）。', '退出', {danger:true});
    if(q.ok){ const j=await api('/api/unpair',{}); if(j){ toast(j.msg); setTimeout(()=>location.reload(), 1200); } } return;
  }
});
// ── K 线（同花顺式：红 = 涨（空心）、绿 = 跌（实心）；5 / 10 / 20 / 30 日均价；买入价 / 止损线）──
// 每张图自己的按钮（2026-10-07 用户：「K线的日周月button 要显示在每个K线的上面边沿方便看 / 量 MACD DMI 显示在每个K线的下面」）：
//   上边沿 = 日K / 周K / 月K，下边沿 = 量 / MACD / DMI；每张图各自切换，新打开的图用最近一次选的（记在这台设备的浏览器里）
// 说明都用日常的话（同日：「K线解释换成通俗易懂的说法 横展开」）：标签的说法来自 qbreak/kline.py（CFG.kp），其余按图里的数字现算
// 小图：量 / MACD（规则同一组参数）/ DMI（同花顺写法）；趋势线：连低点的支撑线、连高点的压力线（qbreak/trendline.py）+ 往后延长的点线 + 破线点
// 数据 = 执行器每次运行写的 out/charts_<账本>.json，打开 / 看到哪只票才取（/api/chart）；只展示
const TFS = {D:'日K', W:'周K', M:'月K'}, SUBS = {v:'量', macd:'MACD', dmi:'DMI'};
const KU = {D:'天', W:'周', M:'个月'}, KMA = {D:'日', W:'周', M:'个月'};   // 一根 = 1 天 / 1 周 / 1 个月；20 日均价 / 20 周均价 / 20 个月均价
const KPL = CFG.kp || {};
let TF = 'D', SUB = 'v', CPN = 0;                                         // 新打开的图默认用的周期 / 小图（= 最近一次选的）
try{ const v=localStorage.getItem('qbreak.tf'); if(v && TFS[v]) TF=v; }catch(x){}
try{ const v=localStorage.getItem('qbreak.sub'); if(v && SUBS[v]) SUB=v; }catch(x){}
const KD = {}, KP = {};
const NS='http://www.w3.org/2000/svg', WD=['日','一','二','三','四','五','六'];
const MAS=[['ma5',5,'m5'],['ma10',10,'m10'],['ma20',20,'m20'],['ma30',30,'m30']];
function sv(tag, at, par){ const e=document.createElementNS(NS, tag); for(const k in at) e.setAttribute(k, at[k]); if(par) par.appendChild(e); return e; }
function nd(tag, cls, text, par){ const e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; if(par) par.appendChild(e); return e; }
function pxs(v){ if(v==null) return '—'; return '¥'+(v<1000 ? v.toLocaleString('ja-JP',{minimumFractionDigits:1, maximumFractionDigits:1}) : Math.round(v).toLocaleString('ja-JP')); }
function pcs(v){ return (v>=0?'+':'')+v.toFixed(2)+'%'; }
function nice(lo, hi, n){
  const raw=(hi-lo||Math.abs(hi)||1)/n, p=Math.pow(10, Math.floor(Math.log10(raw))), f=raw/p;
  const st=(f<1.5?1:f<3?2:f<3.5?2.5:f<7.5?5:10)*p, out=[];
  for(let v=Math.ceil(lo/st)*st; v<=hi+st*1e-9; v+=st) out.push(+v.toFixed(8));
  return out;
}
function vfmt(v){ return v>=1e8 ? (v/1e8).toFixed(1)+' 亿' : v>=1e4 ? (v/1e4).toFixed(v>=1e6?0:1)+' 万' : String(v); }
function dlab(d, tf){ return tf==='M' ? d.slice(0,4)+' 年 '+(+d.slice(5,7))+' 月' : tf==='W' ? '到 '+d.replace(/-/g,'/')+' 的一周' : d.replace(/-/g,'/')+'（'+WD[new Date(d+'T00:00:00').getDay()]+'）'; }
function sdate(d, tf){ return tf==='M' ? d.slice(0,7).replace('-','/') : d.slice(5).replace('-','/'); }
function loadK(t){
  if(KD[t] && KD[t]!=='error' && KD[t]!=='timeout' && KD[t]!=='loading') return Promise.resolve(KD[t]);
  if(KP[t]) return KP[t];                                                   // 同一只票已经在取：等同一个请求
  KD[t]='loading';
  const p=(async()=>{
    try{
      const x=await req('/api/chart?book='+encodeURIComponent(CFG.book)+'&t='+encodeURIComponent(t), {credentials:'same-origin', cache:'no-store'});
      if(x.r.status===404) KD[t]='none';
      else if(x.r.status===401){ KD[t]='auth'; setTimeout(()=>location.reload(), 1500); }   // 这台设备没被认出来：刷新（会到配对页）
      else if(!x.r.ok || !x.j) KD[t]='error';                                // 内容读不出来（连接中途断了）也算取不到：可以再点
      else KD[t]=x.j.data ? x.j.data : 'none';
    }catch(e){ KD[t]=(e && e.name==='Timeout') ? 'timeout' : 'error'; }   // 15 秒没有回应（Mac 睡眠时不会一直停在「载入中」）
    return KD[t];
  })();
  KP[t]=p; p.then(()=>{ if(KP[t]===p) delete KP[t]; });
  return p;
}
function legend(head, D, i, tf){
  head.textContent='';
  nd('b',null,'均价线',head);
  for(const [k,n,cls] of MAS){ const v=D[k] && D[k][i]; const sp=nd('span',null,null,head); nd('i','key '+cls,null,sp); sp.appendChild(document.createTextNode(n+' '+KMA[tf]+' '+(v==null?'—':pxs(v)))); }
}
function isLive(P, D, i, tf){ const L=P && P.live; return !!(L && i===D.d.length-1 && (L.tf||[]).indexOf(tf)>=0 && D.d[i]>=L.d); }
function liveAt(P){ return String((P.live||{}).at||'').slice(11,16); }
function readout(el, D, i, P, tf){
  el.textContent='';
  const pc=i>0 ? D.c[i-1] : null, c=D.c[i], dir=(pc && c!=null) ? (c>=pc ? 'up' : 'down') : null, lv=isLive(P, D, i, tf);
  nd('span','m', dlab(D.d[i], tf)+' ', el);
  if(lv) nd('span','m',(P.live.open ? '盘中 ' : '暂定 ')+liveAt(P)+' ', el);   // 今天这一根：到这个时刻为止（Yahoo 1 分钟线，约晚 20 分钟）；收盘后 = 暂定
  nd('b',dir,(lv ? (P.live.open ? '现价 ' : '最新价 ') : '收盘 ')+pxs(c)+(pc && c!=null ? '（'+pcs((c/pc-1)*100)+'）' : ''),el);
  el.appendChild(document.createTextNode(' · 开 '+pxs(D.o[i])+' · 高 '+pxs(D.h[i])+' · 低 '+pxs(D.l[i])+' · 量 '+vfmt(D.v[i]||0)+(P.kind==='core'?' 口':' 股')
    +(P.kind==='stock' && P.entry_px && c!=null ? ' · 比买入价 '+pcs((c/P.entry_px-1)*100) : '')));
}
function fmx(a, i, sg){ const v=a && a[i]; if(v==null) return '—'; const s=Math.abs(v)>=100 ? v.toFixed(0) : Math.abs(v)>=1 ? v.toFixed(2) : v.toFixed(3); return (sg && v>0 ? '+' : '')+s; }
function f1(a, i){ const v=a && a[i]; return v==null ? '—' : v.toFixed(1); }
function subText(D, i, sub){                                               // 小图左上角的数字（短：手机上一行放得下）
  if(sub==='macd') return 'DIF '+fmx(D.dif,i)+' · DEA '+fmx(D.dea,i)+' · 柱 '+fmx(D.mh,i,true);
  if(sub==='dmi') return '+DI '+f1(D.pdi,i)+' · −DI '+f1(D.mdi,i)+' · ADX '+f1(D.adx,i)+' · ADXR '+f1(D.adxr,i);
  return '';
}
function kSubKey(el, P, tf, sub){                                          // 小图的图例（意思在「怎么看这张图」里）
  el.textContent='';
  const row=nd('div','legend',null,el);
  const k=(c, t)=>{ const sp=nd('span',null,null,row); nd('i','key '+c,null,sp); sp.appendChild(document.createTextNode(t)); };
  if(sub==='macd'){ k('dif','快线'); k('dea','慢线'); k('box mhu','柱 = 快线 − 慢线'); nd('span',null,'MACD '+((P.ind||{}).macd||[12,26,9]).join(','),row); }
  else if(sub==='dmi'){ k('pdi','+DI 买方'); k('mdi','−DI 卖方'); k('adx','ADX 趋势强度'); k('adxr','ADXR'); nd('span',null,'DMI '+((P.ind||{}).dmi||[14,6]).join(','),row); }
  else { k('box cu','涨'); k('box cd','跌'); nd('span',null,'成交量（'+(P.kind==='core' ? '口' : '股')+'）',row); }
}
function kSubNow(el, D, i, P, tf, sub){                                    // 小图「这一根」一句话（跟着十字线走）
  let s='';
  if(sub==='macd'){
    const a=D.dif && D.dif[i], b=D.dea && D.dea[i], h=D.mh && D.mh[i], h0=i>0 && D.mh ? D.mh[i-1] : null;
    if(a==null || b==null) s='K 线还不够多，算不出来';
    else {
      if(h!=null && h0!=null && h0<0 && h>=0) s='金叉（快线刚往上穿过慢线）';
      else if(h!=null && h0!=null && h0>0 && h<=0) s='死叉（快线刚往下穿过慢线）';
      else s=(a>=b ? '快线在慢线上面（涨的力量强）' : '快线在慢线下面（跌的力量强）')
             +(h!=null && h0!=null ? (Math.abs(h)>Math.abs(h0) ? '，在变强' : '，在变弱') : '');
      s+='；在 0 线'+(a>=0 ? '上面（偏涨）' : '下面（偏跌）');
    }
  } else if(sub==='dmi'){
    const p=D.pdi && D.pdi[i], m=D.mdi && D.mdi[i], x=D.adx && D.adx[i], x0=i>0 && D.adx ? D.adx[i-1] : null;
    if(p==null || m==null) s='K 线还不够多，算不出来';
    else {
      s=p>=m ? '买方强' : '卖方强';
      if(x!=null) s+='；ADX '+x.toFixed(1)+(x>=25 ? '（趋势明显）' : x<20 ? '（没什么趋势）' : '（趋势一般）')+(x0!=null ? (x>x0 ? '，在变强' : '，在变弱') : '');
    }
  } else {
    const v=D.v[i]||0; let sm=0, n=0;
    for(let j=Math.max(0, i-20); j<i; j++){ if(D.v[j]!=null){ sm+=D.v[j]; n++; } }
    s='成交 '+vfmt(v)+(P.kind==='core' ? ' 口' : ' 股')+(n>=5 && sm>0 ? '，是前 '+n+' '+KU[tf]+'平均的 '+(v/(sm/n)).toFixed(2)+' 倍' : '');
  }
  const lv=isLive(P, D, i, tf);
  el.textContent=(lv ? (P.live.open ? '今天这一根（到 '+liveAt(P)+'，还没收盘）' : '暂定的一根（1 分钟线到 '+liveAt(P)+'；正式日线在执行器下一次运行后换上）')
    : i===D.d.length-1 ? '最新一根' : sdate(D.d[i], tf))+'：'+s;
}
function kTrend(el, tr, tf){                                               // 现在的趋势（一句话；kline.py 的标签换成日常的话）
  const L=KPL.label||{}, A=KPL.align||{}, m=KMA[tf], sl=+tr.slope20_pct||0;
  nd('span',null,'现在的趋势：',el);
  nd('b', tr.label==='上升' ? 'up' : tr.label==='下降' ? 'down' : null, L[tr.label] || tr.label || '—', el);
  el.appendChild(document.createTextNode('（收盘在 20 '+m+'均价'+(tr.above20 ? '上面' : '下面')+'，20 '+m+'均价'
    +(Math.abs(sl)<0.005 ? '走平' : sl>0 ? '往上' : '往下')+'）'+(tr.align ? ' · '+(A[tr.align] || tr.align) : '')));
}
function kTL(el, TL, tf){                                                  // 现在的趋势线（一句话；图上的记号在「怎么看这张图」里）
  const C=KPL.chan||{};
  const one=(L, sup)=>{ const d=L.dist_pct;
    return (sup ? '支撑 ' : '压力 ')+pxs(L.now)+(d==null ? '' : sup ? (d<=0 ? '（比收盘低 '+Math.abs(d)+'%）' : '（已跌破）')
                                                                : (d>=0 ? '（比收盘高 '+d+'%）' : '（已冲过）')); };
  const parts=[]; if(TL.sup) parts.push(one(TL.sup, true)); if(TL.res) parts.push(one(TL.res, false));
  nd('div',null,'趋势线：'+(TL.chan ? (C[TL.chan] || TL.chan) : '只找到'+(TL.sup ? '下面' : '上面')+'的一条')+(parts.length ? ' · '+parts.join(' · ') : ''),el);
}
function kHelp(box, P, tf, hasTL, PJ){                                         // 「怎么看这张图」（收起来；打开 / 关上记在这张图上，切换周期也不变）
  const det=nd('details','khelp',null,box); if(box.dataset.help==='1') det.open=true;
  det.addEventListener('toggle', ()=>{ box.dataset.help = det.open ? '1' : ''; });
  nd('summary',null,'怎么看这张图',det);
  const ul=nd('ul',null,null,det), u=KU[tf], m=KMA[tf];
  const li=(...ps)=>{ const e=nd('li',null,null,ul); for(const p of ps) e.appendChild(typeof p==='string' ? document.createTextNode(p) : p); };
  const key=c=>nd('i','key '+c,null,null);
  li('每根 K 线 = 1 '+u+'：粗的一段 = 开盘到收盘，细线 = 最高到最低；',key('box cu'),'红色空心 = 涨　',key('box cd'),'绿色实心 = 跌');
  li(key('m5'),'5　',key('m10'),'10　',key('m20'),'20　',key('m30'),'30 '+m+'均价 = 最近几'+u+'收盘价的平均');
  li('往上走 = 收盘在 20 '+m+'均价上面、20 '+m+'均价往上、5 '+m+'均价在 20 '+m+'均价上面；往下走 = 反过来；其余 = 横着走');
  if(P.kind==='stock') li(key('dash'),'买入价　',key('dash stop'),'止损线（跌到这里按规则卖）　▲买入 = 买入那一根');
  else if(P.signal_date) li('▲信号 = 出买入信号那一根');
  if(hasTL) li(key('dash tl'),'趋势线：下面连低点（支撑）、上面连高点（压力），点线 = 往后延长 '+PJ+' '+u+'；▲ 冲过压力线、▼ 跌破支撑线。'
    +'研究（2026-10-06）：对之后的涨跌没有预测力，只用来看');
  li('下面的小图：量 = 成交多少；MACD = 涨跌的力量（快线在 0 附近往上穿过慢线 = 金叉，是规则买入的条件之一）；DMI = 买卖哪边强、趋势强不强（规则不用）');
  li('看以前的某一根：点一下或按住左右滑；键盘 ← → 一根一根看，Home / End 到最早 / 最新，Esc 回到最新');
  li('图上都是过去的价格，不是预测');
}
function kBar(box, pos, act, opts, cur, label, hint){                      // 图的上边沿（周期）/ 下边沿（小图）的按钮
  const bar=nd('div','kbar '+pos,null,box), g=nd('div','seg',null,bar);
  g.setAttribute('role','group'); g.setAttribute('aria-label',label);
  for(const k in opts){ const b=nd('button',null,opts[k],g); b.type='button'; b.dataset.act=act; b.dataset.v=k; b.setAttribute('aria-pressed', k===cur ? 'true' : 'false'); }
  if(hint) nd('span','hint',hint,bar);
  return bar;
}
function drawK(box){
  const t=box.dataset.t, P=KD[t];
  box.removeAttribute('data-retry'); box.removeAttribute('role'); box.onkeydown=null; box.onblur=null; box._hide=null;
  const empty=s=>{ box.className='chart empty muted small'; box.removeAttribute('tabindex'); box.textContent=s; };
  const retry=s=>{ empty(s); box.setAttribute('data-retry', '1'); box.setAttribute('role', 'button'); box.tabIndex=0; };
  if(P==null || P==='loading') return empty('K 线载入中…');
  if(P==='none') return empty('K 线在执行器下一次运行之后显示');
  if(P==='auth') return empty('这台设备没被认出来：正在刷新…');
  if(P==='timeout') return retry(CFG.remote ? 'Mac 可能在睡眠：取不到（超过 15 秒没有回应；点这里再试）' : 'K 线取不到（面板超过 15 秒没有回应）：点这里再试');
  if(P==='error') return retry('K 线取不到（面板连不上？）：点这里再试');
  let tf=box.dataset.tf, sub=box.dataset.sub;                              // 这张图自己的周期 / 小图：第一次画时用最近一次选的，之后各自记着
  if(!TFS[tf]) tf=box.dataset.tf=TF;
  if(!SUBS[sub]) sub=box.dataset.sub=SUB;
  box.className='chart'; box.textContent='';
  kBar(box, 'ktop', 'ktf', TFS, tf, 'K 线的周期', '每根 = 1 '+KU[tf]);           // 类名不用 top：页头的 .top 是 sticky
  const D=(P.tf||{})[tf];
  if(!D || !D.d || D.d.length<2){ box.removeAttribute('tabindex'); nd('div','muted small','没有'+TFS[tf]+'的数据（上市不久？换一个周期看看）',box); return; }
  box.tabIndex=0;
  const held=P.kind==='stock', N=D.d.length, TL=D.tl||null, PJ=TL && (TL.sup || TL.res) ? (TL.proj||0) : 0;
  const H2=56, gap=16;                                                      // 小图三种一样高：切换时下边沿的按钮不跳
  const cs=getComputedStyle(box), inner=box.clientWidth-(parseFloat(cs.paddingLeft)||0)-(parseFloat(cs.paddingRight)||0);
  const W=Math.max(260, Math.round(inner>0 ? inner : 300)), x0=2, x1=W-56, padT=8, H1=176, padB=18;
  const slots=Math.max(4, Math.floor((x1-x0)/6));                          // 一根 K 线占 6px：手机约 40 根，Mac 约 100 根（右边留出趋势线往后延长的几根）
  const k=Math.max(2, Math.min(N, slots-PJ)), s0=N-k, step=(x1-x0)/(k+PJ);
  const X=i=> x0+(i-s0+0.5)*step, bw=Math.max(1, Math.min(13, step*0.68));
  const vb=padT+H1+gap+H2, H=vb+padB;
  const refs=[];
  if(held && P.entry_px) refs.push(['ref','买入价',P.entry_px]);
  if(held && P.stop_px) refs.push(['stop','止损',P.stop_px]);
  let lo=Infinity, hi=-Infinity;
  for(let i=s0;i<N;i++){
    if(D.l[i]!=null) lo=Math.min(lo, D.l[i]); if(D.h[i]!=null) hi=Math.max(hi, D.h[i]);
    for(const [m] of MAS){ const v=D[m] && D[m][i]; if(v!=null){ lo=Math.min(lo, v); hi=Math.max(hi, v); } }
  }
  for(const r of refs){ lo=Math.min(lo, r[2]); hi=Math.max(hi, r[2]); }
  const tly=(L,i)=> L.y1+L.b*(i-L.i1);                                      // 趋势线在第 i 根的值（i 可以超过最后一根 = 往后延长）
  if(TL){ const sp=hi-lo; for(const s of ['sup','res']){ const L=TL[s]; if(!L) continue;
    for(const v of [tly(L,N-1), tly(L,N-1+PJ)]) if(v>=lo-0.25*sp && v<=hi+0.25*sp){ lo=Math.min(lo,v); hi=Math.max(hi,v); } } }   // 离得太远的线不拉大坐标，超出的部分裁掉
  const pad=(hi-lo)*0.05 || hi*0.02 || 1; lo-=pad; hi+=pad;
  const Y=v=> padT+H1-(v-lo)/(hi-lo)*H1;
  const head=nd('div','legend',null,box); legend(head, D, N-1, tf);
  const ro=nd('div','ro',null,box); readout(ro, D, N-1, P, tf);             // 读数固定在图上面（不盖住 K 线）：默认最新一根，点 / 指到哪根就是哪根
  const tr=(P.trend||{})[tf], c0=D.c[s0], c1=D.c[N-1];
  const svg=sv('svg',{viewBox:'0 0 '+W+' '+H, width:W, height:H, role:'img',
    'aria-label':t+' '+TFS[tf]+'（最近 '+k+' '+KU[tf]+'）：'+pxs(c0)+' → '+pxs(c1)+(tr ? '，'+((KPL.label||{})[tr.label] || tr.label) : '')}, box);
  for(const v of nice(lo, hi, 4)){
    const y=Math.round(Y(v))+0.5; sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':'grid'}, svg);
    sv('text',{x:x1+6, y:y+4, 'class':'ax'}, svg).textContent=pxs(v);
  }
  let lastX=-1e9, prev=null;
  for(let i=s0;i<N;i++){
    const d=D.d[i], y=d.slice(0,4), m=+d.slice(5,7); let lab=null;
    const key = tf==='M' ? y : tf==='W' ? y+'-'+Math.floor((m-1)/3) : d.slice(0,7);   // 日K 每月、周K 每季、月K 每年标一次
    if(prev!=null && key!==prev) lab = tf==='M' ? y : (prev.slice(0,4)!==y ? y.slice(2)+' 年' : m+' 月');
    prev=key;
    const x=X(i);
    if(lab && x-lastX>=44 && x>=x0+14 && x<=x1-14){ sv('text',{x:x, y:H-4, 'class':'ax', 'text-anchor':'middle'}, svg).textContent=lab; lastX=x; }
  }
  for(let i=s0;i<N;i++){
    const o=D.o[i], h=D.h[i], l=D.l[i], c=D.c[i]; if(c==null) continue;
    const up=c>=(o==null?c:o), x=X(i), cls=up?'cu':'cd';
    const xx=Math.round(x)+0.5;
    sv('line',{x1:xx, x2:xx, y1:Y(h==null?c:h), y2:Y(l==null?c:l), 'class':'wk '+cls}, svg);
    const yt=Y(Math.max(o==null?c:o, c)), yb=Y(Math.min(o==null?c:o, c)), lv=isLive(P, D, i, tf);
    sv('rect',{x:(x-bw/2).toFixed(1), y:yt.toFixed(1), width:bw.toFixed(1), height:Math.max(1, yb-yt).toFixed(1), 'class':'bd '+cls+(lv ? ' live' : '')}, svg);
    if(lv) sv('text',{x:(x+bw/2).toFixed(1), y:Math.max(padT+9, Y(h==null?c:h)-5).toFixed(1), 'class':'lv', 'text-anchor':'end'}, svg).textContent=P.live.open ? '盘中' : '暂定';   // 右边对齐这一根（不压到价格轴），描边盖住后面的线
  }
  const path=a=>{ let s='', pen=false; for(let i=s0;i<N;i++){ const v=a[i]; if(v==null){ pen=false; continue; } s+=(pen?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1); pen=true; } return s; };
  for(const [m,,cls] of MAS.slice().reverse()) if(D[m]) sv('path',{d:path(D[m]), 'class':'ma '+cls}, svg);
  if(PJ>0 || (TL && (TL.ev||[]).length)){
    const id='kc'+(++CPN), cp=sv('clipPath',{id:id}, sv('defs',{},svg)); sv('rect',{x:x0, y:padT, width:x1-x0, height:H1}, cp);
    const g=sv('g',{'clip-path':'url(#'+id+')'}, svg);
    for(const [s, lab, below] of [['sup','支撑',true],['res','压力',false]]){
      const L=TL[s]; if(!L) continue;
      const ia=Math.max(L.i1, s0); if(ia>N-1) continue;
      const p=(i)=> X(i).toFixed(1)+' '+Y(tly(L,i)).toFixed(1);
      sv('path',{d:'M'+p(ia)+'L'+p(N-1), 'class':'tl'}, g);
      sv('path',{d:'M'+p(N-1)+'L'+p(N-1+PJ), 'class':'tlp'}, g);
      for(const ii of [L.i1, L.i2]) if(ii>=s0 && ii<N) sv('circle',{cx:X(ii).toFixed(1), cy:Y(tly(L,ii)).toFixed(1), r:2.6, 'class':'tla'}, g);
      const ye=Math.max(padT+11, Math.min(padT+H1-3, below ? Y(tly(L,N-1+PJ))+13 : Y(tly(L,N-1+PJ))-6));   // 标签留在图里
      sv('text',{x:(x1-3).toFixed(1), y:ye.toFixed(1), 'class':'rl', 'text-anchor':'end'}, g).textContent=lab+' '+pxs(L.now);
    }
    for(const [ii, kd] of (TL.ev||[])){                                    // ▲ 收盘冲过压力线 / ▼ 收盘跌破支撑线（各自当时的线；连续几根只标第一次）
      if(ii<s0 || ii>=N) continue;
      const x=X(ii).toFixed(1);
      if(kd==='rb'){ const y=Math.min(padT+H1-8, Y(D.l[ii]!=null ? D.l[ii] : D.c[ii])+4); sv('path',{d:'M'+x+' '+y.toFixed(1)+'l3.5 6h-7z', 'class':'tbu'}, g); }
      else { const y=Math.max(padT+8, Y(D.h[ii]!=null ? D.h[ii] : D.c[ii])-4); sv('path',{d:'M'+x+' '+y.toFixed(1)+'l3.5 -6h-7z', 'class':'tbd'}, g); }
    }
  }
  let prevY=null;
  for(const [cls, lab, v] of refs){
    const y=Math.round(Y(v))+0.5; sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':cls}, svg);
    const ty = prevY!=null && Math.abs(prevY-(y-4))<13 ? y+13 : y-4; prevY=ty;
    sv('text',{x:x0+4, y:ty, 'class':'rl'}, svg).textContent=lab+' '+pxs(v);
  }
  const mark = held ? [P.entry_date, '买入'] : (P.signal_date ? [P.signal_date, '信号'] : null);
  if(mark && mark[0] && D.d[s0]<=mark[0]){
    let ie=-1; for(let i=s0;i<N;i++) if(D.d[i]>=mark[0]){ ie=i; break; }
    if(ie>=0 && D.l[ie]!=null){
      const cx=X(ie), cy=Math.min(padT+H1-2, Y(D.l[ie])+9);
      sv('path',{d:'M'+cx+' '+(cy-5)+'l4 7h-8z', 'class':'mk'}, svg);
      sv('text',{x:cx, y:Math.min(padT+H1+8, cy+13), 'class':'rl', 'text-anchor':'middle'}, svg).textContent=mark[1];
    }
  }
  const st=vb-H2, pth=(a,F)=>{ let s='', pen=false; for(let i=s0;i<N;i++){ const v=a && a[i]; if(v==null){ pen=false; continue; } s+=(pen?'L':'M')+X(i).toFixed(1)+' '+F(v).toFixed(1); pen=true; } return s; };
  let sl=null;
  if(sub==='macd'){                                                         // MACD：柱 = DIF − DEA（规则的定义），0 轴居中
    let m=0; for(let i=s0;i<N;i++) for(const a of [D.dif,D.dea,D.mh]){ const v=a && a[i]; if(v!=null) m=Math.max(m, Math.abs(v)); }
    if(m>0){
      const F=v=> st+H2/2-v/m*(H2/2-2), z=Math.round(F(0))+0.5;
      sv('line',{x1:x0, x2:x1, y1:z, y2:z, 'class':'zl'}, svg);
      for(let i=s0;i<N;i++){ const v=D.mh && D.mh[i]; if(v==null) continue; const y=F(v);
        sv('rect',{x:(X(i)-bw/2).toFixed(1), y:Math.min(z,y).toFixed(1), width:bw.toFixed(1), height:Math.max(0.5, Math.abs(y-z)).toFixed(1), 'class':v>=0?'mhu':'mhd'}, svg); }
      sv('path',{d:pth(D.dif,F), 'class':'s1 dif'}, svg); sv('path',{d:pth(D.dea,F), 'class':'s1 dea'}, svg);
      sv('text',{x:x1+6, y:z+4, 'class':'ax'}, svg).textContent='0';
    }
  } else if(sub==='dmi'){                                                   // DMI：+DI 红实线、−DI 绿虚线、ADX 紫、ADXR 蓝点线
    let m=30; for(let i=s0;i<N;i++) for(const a of [D.pdi,D.mdi,D.adx,D.adxr]){ const v=a && a[i]; if(v!=null) m=Math.max(m, v); }
    const F=v=> vb-v/m*(H2-2);
    for(const [a,cls] of [[D.adxr,'adxr'],[D.adx,'adx'],[D.mdi,'mdi'],[D.pdi,'pdi']]) if(a) sv('path',{d:pth(a,F), 'class':'s1 '+cls}, svg);
    sv('text',{x:x1+6, y:st+9, 'class':'ax'}, svg).textContent=String(Math.round(m));
  } else {
    let vmax=0; for(let i=s0;i<N;i++) vmax=Math.max(vmax, D.v[i]||0);
    if(vmax>0) for(let i=s0;i<N;i++){
      const h=(D.v[i]||0)/vmax*H2; if(h<0.5) continue;
      const up=D.c[i]!=null && D.o[i]!=null ? D.c[i]>=D.o[i] : true;
      sv('rect',{x:(X(i)-bw/2).toFixed(1), y:(vb-h).toFixed(1), width:bw.toFixed(1), height:h.toFixed(1), 'class':'vl '+(up?'cu':'cd')}, svg);
    }
    if(vmax>0) sv('text',{x:x1+6, y:vb-H2+9, 'class':'ax'}, svg).textContent=vfmt(vmax)+(P.kind==='core' ? ' 口' : ' 股');
  }
  if(sub!=='v'){ sl=sv('text',{x:x0+2, y:st-5, 'class':'sl'}, svg); sl.textContent=subText(D, N-1, sub); }
  sv('line',{x1:x0, x2:x1, y1:vb+0.5, y2:vb+0.5, 'class':'grid'}, svg);
  const xh=sv('line',{x1:0, x2:0, y1:padT, y2:vb, 'class':'xh', visibility:'hidden'}, svg);
  const yh=sv('line',{x1:x0, x2:x1, y1:0, y2:0, 'class':'xh', visibility:'hidden'}, svg);
  kBar(box, 'kbot', 'ksub', SUBS, sub, '下面的小图显示什么');                  // 下边沿：量 / MACD / DMI
  kSubKey(nd('div','kexp',null,box), P, tf, sub);
  const sn=nd('div','kexp now',null,box); kSubNow(sn, D, N-1, P, tf, sub);
  let cur=null;
  const show=i=>{
    i=Math.max(s0, Math.min(N-1, i)); cur=i; const x=X(i);
    xh.setAttribute('x1',x); xh.setAttribute('x2',x); xh.setAttribute('visibility','visible');
    if(D.c[i]!=null){ const y=Y(D.c[i]); yh.setAttribute('y1',y); yh.setAttribute('y2',y); yh.setAttribute('visibility','visible'); }
    legend(head, D, i, tf); readout(ro, D, i, P, tf); if(sl) sl.textContent=subText(D, i, sub); kSubNow(sn, D, i, P, tf, sub);
    box.dataset.hover = i<N-1 ? '1' : '';                                   // 在看以前的某一根：现价刷新时先不重画
  };
  const hide=()=>{ cur=null; box.dataset.hover=''; xh.setAttribute('visibility','hidden'); yh.setAttribute('visibility','hidden'); legend(head, D, N-1, tf); readout(ro, D, N-1, P, tf);
    if(sl) sl.textContent=subText(D, N-1, sub); kSubNow(sn, D, N-1, P, tf, sub); };
  box._hide=hide;
  const at=ev=>{ const r=svg.getBoundingClientRect(); return s0+Math.floor(((ev.clientX-r.left)*W/r.width-x0)/step); };
  svg.addEventListener('pointermove', ev=>show(at(ev)));
  svg.addEventListener('pointerdown', ev=>show(at(ev)));
  svg.addEventListener('pointerleave', ev=>{ if(ev.pointerType!=='touch') hide(); });
  box.onkeydown=ev=>{                                                       // 用属性不用 addEventListener：重画时换掉、不越积越多
    if(ev.target!==box) return;                                             // 按钮 / 说明上按的键不动十字线
    if(ev.key==='ArrowLeft' || ev.key==='ArrowRight'){ ev.preventDefault(); show((cur==null ? N-1 : cur)+(ev.key==='ArrowLeft' ? -1 : 1)); }
    else if(ev.key==='Home'){ ev.preventDefault(); show(s0); } else if(ev.key==='End'){ ev.preventDefault(); show(N-1); }
    else if(ev.key==='Escape') hide();
  };
  box.onblur=hide;
  if(tr) kTrend(nd('div','kexp',null,box), tr, tf);
  if(TL && (TL.sup || TL.res)) kTL(nd('div','kexp',null,box), TL, tf);
  kHelp(box, P, tf, !!(TL && (TL.sup || TL.res)), PJ);
  const det=nd('details',null,null,box); if(box.dataset.tbl==='1') det.open=true;
  det.addEventListener('toggle', ()=>{ box.dataset.tbl = det.open ? '1' : ''; });
  nd('summary','muted small','最近 10 '+KU[tf]+'的数字（表）',det);
  const tb=nd('table',null,null,det), hr=nd('tr',null,null,nd('thead',null,null,tb)), body=nd('tbody',null,null,tb);
  for(const h of ['日期','开盘','最高','最低','收盘','涨跌','成交量']) nd('th',null,h,hr);
  for(let i=N-1;i>=Math.max(0,N-10);i--){
    const r=nd('tr',null,null,body), pc=i>0?D.c[i-1]:null;
    nd('td',null,sdate(D.d[i], tf),r);
    for(const a of [D.o,D.h,D.l,D.c]) nd('td',null,pxs(a[i]),r);
    nd('td',(pc && D.c[i]!=null) ? (D.c[i]>=pc ? 'up' : 'down') : null, pc && D.c[i]!=null ? pcs((D.c[i]/pc-1)*100) : '—', r);
    nd('td',null,Number(D.v[i]||0).toLocaleString('ja-JP'),r);
  }
}
async function showK(box){
  const t=box.dataset.t, s=KD[t];
  if(!s || s==='error' || s==='timeout' || s==='loading'){ drawK(box); await loadK(t); }
  drawK(box);
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(b!==box && b.dataset.t===t && b.offsetParent!==null) drawK(b); });   // 同一只票的别的图
}
function drawAll(){
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(KD[b.dataset.t] && b.offsetParent!==null) drawK(b); });
}
const IO = ('IntersectionObserver' in window) ? new IntersectionObserver(es=>{ for(const e of es) if(e.isIntersecting){ IO.unobserve(e.target); showK(e.target); } }, {rootMargin:'200px'}) : null;
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(IO) IO.observe(b); else showK(b); });
});
document.addEventListener('toggle', e=>{ if(e.target.tagName==='DETAILS' && e.target.open) e.target.querySelectorAll('.chart[data-t]').forEach(b=>{ if(KD[b.dataset.t] && KD[b.dataset.t]!=='loading') drawK(b); }); }, true);
document.addEventListener('pointerdown', ev=>{ if(!ev.target.closest('.chart')) document.querySelectorAll('.chart').forEach(b=>{ if(b._hide) b._hide(); }); });
let RZ=null, LW=window.innerWidth;
window.addEventListener('resize', ()=>{ clearTimeout(RZ); RZ=setTimeout(()=>{ if(Math.abs(window.innerWidth-LW)>2){ LW=window.innerWidth; drawAll(); } }, 150); });
// ── 现价（/api/quotes：Yahoo 1 分钟线，约晚 20 分钟；盘中每 1 分钟刷新，其他时间每 10 分钟）──
// 持仓：现价 + 卖的话按什么价（下单时立花用实时现价，见 MO.order_basis）+ 晚了几分钟的大概范围 + 预计收益；
// 建议的股票（2026-10-07 用户「建议的股票中也要能看到当天实时的K线 点击买入的时候也可以看到当前的价格」）：打开的 K 线 / 买入框里的才取（一次最多 12 只）
function hmOf(q){ const hm=String(q.at||'').slice(11,16), d=String(q.at||'').slice(5,10).replace('-','/'); return q.today ? hm : d+' '+hm; }
function qText(q, kind){                                                   // 一只票的现价一行
  const u = kind==='core' ? '口' : '股';
  const parts=['现价 '+pxs(q.px)+'（'+hmOf(q)+(q.today ? '' : '，最近一个交易日')+'）'];
  if(q.chg_pct!=null) parts.push('比昨收 '+pcs(q.chg_pct));
  parts.push('市值约 '+yen(q.value)+'（'+Number(q.n).toLocaleString('ja-JP')+' '+u+'）');
  if(q.pl_pct!=null) parts.push('比买入价 '+pcs(q.pl_pct));
  return parts.join(' · ');
}
function rngText(q){                                                       // 晚了几分钟 → 现在的价通常（约 95%）在哪个范围（按日波动估算）
  if(q.rng==null) return '';
  return '晚约 '+q.delay+' 分钟：现在的价通常在 '+pxs(q.px*(1-q.rng/100))+'〜'+pxs(q.px*(1+q.rng/100))+'（±'+q.rng+'%）';
}
function sellLines(q, j){                                                  // 卖的话：预计卖价 + 预计收益 / 下单按什么价 + 晚了几分钟的范围
  const live=!!(j && j.live), b=(j && j.basis && j.basis.SELL) || '';
  const l1=[!live ? '预计卖价：开盘价（参考现价 '+pxs(q.px)+'）' : CFG.paper ? '预计卖价 约 '+pxs(q.px) : '预计卖价 约 '+pxs(q.px*0.995)+'〜'+pxs(q.px)];
  const e=q.est; if(e && e.pnl!=null) l1.push('预计收益 '+syen(e.pnl)+'（'+spc(e.net_pct!=null ? e.net_pct : e.ret_pct)+'，扣手续费、税前）');
  const l2=[]; if(b) l2.push('下单：'+b); const r=rngText(q); if(r) l2.push(r);
  return [l1.join(' · '), l2.join('；')].filter(x=>x);
}
function showQ(j){
  const R=(j && j.rows) || {}, none=!Object.keys(R).length;
  document.querySelectorAll('.qt[data-q]').forEach(e=>{
    const q=R[e.dataset.q];
    e.textContent='';
    if(!q){ e.textContent = !(j && j.ok) ? '' : none ? '现价暂时取不到（Yahoo 没回应：会自动再取）' : '现价取不到（Yahoo 没有这只的分钟线）'; return; }
    const cls = q.chg_pct==null ? null : (q.chg_pct>=0 ? 'up' : 'down');
    nd('span', cls, qText(q, q.kind), e);
    for(const l of sellLines(q, j)) nd('div', 'muted sellx', l, e);
  });
  const n=$('#qt-note'); if(n && j && j.ok) n.textContent='现价：'+j.src+(j.live ? '，盘中每 1 分钟刷新' : '')+'；'+String(j.asof||'').slice(11,16)+' 取'
    +'；只用来看和估算 —— 下单时立花用实时现价（模拟账户按 Yahoo 现价）';
}
let SQ = null;                                                            // 建议的股票最近一次取到的现价
function priceHead(q){ return '现价 '+pxs(q.px)+'（'+hmOf(q)+(q.today ? '，约晚 20 分钟' : '')+'）'+(q.chg_pct!=null ? ' · 比收盘 '+pcs(q.chg_pct) : ''); }
function buyLines(q, j, full){                                             // 建议的股票：现在买按什么价（规则同一条：≤ 收盘 ×1.03）；full = 买入框（多写一行下单依据）
  const live=!!(j && j.live), b=q.buy||{}, B=(j && j.basis && j.basis.BUY) || '', out=[];
  if(b.over) out.push('★ 现价已超过收盘 ×1.03（'+pxs(b.cap)+'）：现在不买（规则和手动买入都一样）');
  else if(live) out.push((CFG.paper ? '现在买：约 '+pxs(q.px)+' 成交（模拟账户按现价）' : '现在买：限价约 '+pxs(b.lim))   // 模拟账户：按现价成交；立花：限价
                        +(b.cap ? '；上限 = 收盘 ×1.03 = '+pxs(b.cap) : ''));
  else if(!full && B) out.push(B);
  if(full && B) out.push('下单：'+B);
  const r=rngText(q); if(r) out.push(r);
  return out;
}
function showSQ(j){
  const R=(j && j.rows) || {};
  document.querySelectorAll('.qt[data-sq]').forEach(e=>{
    const q=R[e.dataset.sq]; if(!q) return;                                // 没取的（K 线没打开）不动
    e.textContent='';
    nd('span', q.chg_pct==null ? null : (q.chg_pct>=0 ? 'up' : 'down'), priceHead(q), e);
    if(e.dataset.planned==='1') return;                                    // 已排在开盘买：只写现价
    for(const l of buyLines(q, j, false)) nd('div', 'muted sellx', l, e);
  });
  buyLive();
}
function sqWant(){                                                         // 要取现价的建议股票：打开的 K 线 + 买入框里的（最多 12 只）
  const s=[];
  const d=$('#dlg-buy'); if(BUY && d && d.open) s.push(BUY.t);
  document.querySelectorAll('#suggest details.kl[open] .chart[data-t]').forEach(b=>{ if(s.indexOf(b.dataset.t)<0) s.push(b.dataset.t); });
  return s.slice(0, 12);
}
async function loadSQ(){
  const ts=sqWant(); if(!ts.length) return;
  try{
    const x=await req('/api/quotes?book='+encodeURIComponent(CFG.book)+'&t='+encodeURIComponent(ts.join(',')), {credentials:'same-origin', cache:'no-store'});
    if(x.r.ok && x.j){ SQ={...x.j, rows:{...((SQ && SQ.rows) || {}), ...(x.j.rows || {})}}; showSQ(SQ); liveK(x.j.rows||{}, x.j.live); }
  }catch(e){}                                                              // 取不到：保留上一次的
}
function buyLive(){                                                        // 买入框：现价 + 现在买按什么价 + 下单依据
  const e=$('#buy-live'); if(!e || !BUY) return;
  const q=SQ && SQ.rows && SQ.rows[BUY.t];
  e.textContent='';
  if(!q){ e.textContent='现价载入中…（Yahoo，约晚 20 分钟）'; return; }
  nd('div', q.chg_pct==null ? null : (q.chg_pct>=0 ? 'up' : 'down'), priceHead(q), e);
  for(const l of buyLines(q, SQ, true)) nd('div', 'muted', l, e);
}
const LAT = {};                                                           // 每只票上一次的「今天这一根」到几点 + 盘中与否（变了才重取 K 线）
function liveK(R, on){                                                     // 现价更新了 / 开盘收盘变了 → 重取 K 线（服务器把今天这一根并进去）
  for(const t in R){
    const q=R[t], k=q && q.bar ? q.at+'|'+(on ? 1 : 0) : null; if(!k || LAT[t]===k) continue; LAT[t]=k;
    if(KD[t]==='loading' && KP[t]) KP[t].then(()=>{ if(KD[t] && typeof KD[t]==='object') reloadK(t); });   // 图正在取（可能比现价先到）：取完再要一次
    else if(KD[t] && typeof KD[t]==='object') reloadK(t);
  }
}
async function reloadK(t){
  try{
    const x=await req('/api/chart?book='+encodeURIComponent(CFG.book)+'&t='+encodeURIComponent(t), {credentials:'same-origin', cache:'no-store'});
    if(!(x.r.ok && x.j && x.j.data)) return;
    KD[t]=x.j.data;
    document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(b.dataset.t===t && b.offsetParent!==null && b.dataset.hover!=='1') drawK(b); });   // 正在看某一根的图不打断
  }catch(e){}
}
let QTID=null, QLIVE=CFG.live, SQT=null;
async function loadQ(){
  if(document.querySelector('.qt[data-q]')){
    try{
      const x=await req('/api/quotes?book='+encodeURIComponent(CFG.book), {credentials:'same-origin', cache:'no-store'});
      if(x.r.ok && x.j){ QD=x.j; showQ(x.j); QLIVE=!!x.j.live; liveK(x.j.rows||{}, x.j.live); }
    }catch(e){}                                                            // 取不到（Mac 睡眠 / 没网）：保留上一次的
  }
  await loadSQ();
  clearTimeout(QTID);
  QTID=setTimeout(loadQ, QLIVE ? 60000 : 600000);                         // 盘中 1 分钟，其他时间 10 分钟（开盘后自动变快）
}
document.addEventListener('toggle', e=>{                                   // 打开一只建议股票的 K 线 → 取它的现价（并进今天这一根）
  if(e.target.tagName==='DETAILS' && e.target.open && e.target.closest('#suggest')){ clearTimeout(SQT); SQT=setTimeout(loadSQ, 300); }
}, true);
document.addEventListener('DOMContentLoaded', loadQ);
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) loadQ(); });   // 手机切回来马上刷新
(function(){                                                              // 〔77〕C UX-16：还有在处理的指令 → 每 10 秒问一次，状态变了就刷新（最多约 2 分钟）
  const s0=(CFG.st||{}); if(!(s0.pending>0)) return;
  let n=0;
  async function tick(){
    n++;
    try{ const x=await req('/api/status?book='+encodeURIComponent(CFG.book),{credentials:'same-origin',cache:'no-store'});
         if(x.r.ok && x.j && x.j.sig && x.j.sig!==s0.sig){ toast('状态更新了：刷新中…'); setTimeout(()=>location.reload(), 800); return; } }catch(e){}
    if(n<12 && !document.hidden) setTimeout(tick, 10000);
  }
  setTimeout(tick, 10000);
})();
"""

_PAIR_JS = """
const $ = s => document.querySelector(s);
function toast(t, bad){const m=$('#toast');m.textContent=t;m.className='toast'+(bad?' bad':'');m.hidden=false;}
$('#code').addEventListener('input', e=>{ const p=e.target.selectionStart; e.target.value=e.target.value.toUpperCase(); try{e.target.setSelectionRange(p,p);}catch(x){} });
$('#go').addEventListener('click', async ()=>{
  const b=$('#go'); b.disabled=true;
  try{
    const x=await req('/api/pair',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',
                                   body:JSON.stringify({code:$('#code').value, name:$('#name').value})});
    const r=x.r, j=x.j||{};
    if(r.ok && j.ok){ toast(j.msg); setTimeout(()=>location.replace('/'), 900); return; }
    toast(r.ok && !x.j ? '回应读不出来：刷新页面看看是不是已经配对好了（提示配对码无效的话，在 Mac 上重新生成）'
                       : (j.msg || ('没配对成功（HTTP '+r.status+'）')), true);
  }catch(e){ toast(e && e.name==='Timeout' ? 'Mac 可能在睡眠：超过 15 秒没有回应（Mac 醒来后再试；配对码 10 分钟内有效；提示配对码无效的话，在 Mac 上重新生成）'
                                           : '连不上面板：'+e, true); }
  b.disabled=false;
});
"""


def _head(title: str) -> str:
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name='theme-color' content='#f2f2f7' media='(prefers-color-scheme: light)'>"
            "<meta name='theme-color' content='#0f0f11' media='(prefers-color-scheme: dark)'>"
            "<meta name='apple-mobile-web-app-capable' content='yes'><meta name='mobile-web-app-capable' content='yes'>"
            "<meta name='apple-mobile-web-app-title' content='qbreak'><meta name='format-detection' content='telephone=no'>"
            "<link rel='manifest' href='/manifest.webmanifest'><link rel='apple-touch-icon' href='/apple-touch-icon.png'>"
            "<link rel='icon' href='/apple-touch-icon.png'>"
            f"<title>{escape(title)}</title><style>{_CSS}</style></head>")


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
            f"<div id='adj-prev'></div><div class='muted small' id='adj-rule'>一次最少 {MO.LOT} 股；单只上限 <span id='adj-cap'>{cap:g}</span>%。"
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
            f"<div id='buy-prev'></div><div class='muted small'>按规则 = 总权益 × 25% × 新仓倍数；单只上限 <span id='buy-cap'>{cap:g}</span>%。"
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


def _suggest_card(sg: dict, book: dict, tag: str, buying: set, when: str, eq, cap: float, chart) -> str:
    """「建议的股票」= 规则的候选（qbreak/suggest.py；全部列出）+ 每只的「买入…」（写手动买入指令；执行器下单前再查一遍）。
    有比例表（var/watch_prob.json，登记研究判定 A）→ 出了信号 / 其余一组（闸门 → 之后 10 个交易日内出买入信号的历史比例 → near_key），
    每只写第几、历史比例；没有 → 以前的 出了信号 → 快要出 → 观察中（按离买入信号的远近）。"""
    tab = WP.load()
    rows = SG.rank([dict(r) for r in (sg.get("rows") or [])], tab or {})   # 旧汇总没有 prob 也在这里补上（更新代码后不用等执行器）
    ranked = bool(tab)
    s = MO.slots(book, tag)
    H = [f"<section class='card' id='suggest'><h2>建议的股票（规则的候选，{len(rows)} 只）</h2>"
         f"<div class='muted small'>按 {escape(str(sg.get('asof') or '—'))} 收盘。不是收益预测，也不是建议；点「买入…」→ {escape(when)}下单。</div>"
         f"<div class='small'>个股名额：空 {s['free']} 个（拿着 {s['held']} + 排定买入 {s['buys']}，上限 {s['max']} 只）</div>"]
    if sg.get("error"):
        H.append(f"<div class='neg small'>★ 这次没算成：{escape(str(sg['error']))}</div>")
    if not rows:
        H.append("<div class='muted'>" + ("候选在执行器下一次运行之后显示" if not sg else "今天没有出信号 / 快要出信号 / 观察中的票") + "</div></section>")
        return "".join(H)
    h = int((tab or {}).get("h") or WP.H)
    for g, title in (RANK_GROUPS if ranked else GROUPS):
        grp = [r for r in rows if r.get("status") != "triggered"] if g == "rest" else [r for r in rows if r.get("status") == g]
        if not grp:
            continue
        if g == "rest":                                     # 快要出 + 观察中一组：按出买入信号的可能性排
            H.append(f"<h3 class='sgh'>观察中 · {len(grp)} 只（按出买入信号的可能性排）</h3>"
                     f"<div class='muted small'>越上面越可能先出买入信号（同样情况的历史比例：日経225，2006〜2026）。比例都不高；"
                     "出了信号还要过闸门 / 名额才会买。</div>")
        else:
            H.append(f"<h3 class='sgh'>{escape(title)}（{len(grp)} 只）</h3>")
            if g != "triggered" and any(r.get("near") for r in grp):
                H.append("<div class='muted small'>按离买入信号的远近排（越上面越可能先出信号；只是估算）</div>")
        for k, r in enumerate(grp, 1):
            H.append(_suggest_row(r, s, buying, eq, chart, rank=k if g == "rest" else None, fill=sg.get("fill_day")))
    H.append("<div class='muted small'>股数按最近收盘估算。</div></section>")
    return "".join(H)


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


def _suggest_row(r: dict, s: dict, buying: set, eq, chart, rank: int | None = None, fill: str | None = None) -> str:
    t, b, ru = str(r["ticker"]), r.get("buy") or {}, r.get("rule") or {}
    nm = f" {escape(str(r['name']))}" if r.get("name") else ""
    meta = [f"条件凑齐 {r['score']:g} / 100" if r.get("score") is not None else None,
            f"收盘 ¥{r['close']:,.0f}" if r.get("close") is not None else None,
            f"量 {r['vol_ratio']:.2f} 倍" if r.get("vol_ratio") is not None else None,
            "真突破" if r.get("breakout") else None]
    tag_ = ("<span class='chip hot'>快要出</span>" if r.get("status") == "imminent" else "") if rank else ""
    H = [f"<div class='hv sg'><div class='head'>" + (f"<span class='rk'>{rank}</span>" if rank else "")
         + f"<b>{escape(str(r.get('code') or t))}</b>{nm}"
         + (f"<span class='chip'>{escape(str(r['sector']))}</span>" if r.get("sector") else "") + tag_ + "</div>"
         + _prob_line(r.get("prob") if rank else None)
         + f"<div class='meta'>{' · '.join(x for x in meta if x)}</div>"
         + (f"<div class='small near'>{escape(str(r['near_text']))}</div>" if r.get("near_text") else "")   # 离买入信号还差什么（排序依据）
         + (f"<div>{escape(str(ru.get('text') or ''))}</div>" if ru.get("state") not in (None, "none") else "")
         + tchips(r.get("trend"), stats=True)
         + (f"<div class='small neg'>★ 顶部风险：{escape(str(r['top_risk']))}</div>" if r.get("top_risk") else "")]
    n, px, lot = int(b.get("rule_shares") or 0), float(b.get("px") or 0), int(b.get("lot") or MO.LOT)
    why = None
    if b.get("block"):
        why = f"不能买：{b['block']}"
    elif t in buying:
        why = "有一条买入指令在处理（见「手动指令」）"
    elif ru.get("state") in ("planned", "manual"):
        why = "已经排在开盘买入"
    elif s["free"] <= 0:
        why = f"个股名额已满（{s['used']} / {s['max']} 只）：先卖出一只"
    elif not (px > 0 and eq):
        why = "没有收盘价 / 总权益：执行器下一次运行之后再买"
    warn = "；".join(b.get("warn") or [])
    if why:
        H.append(f"<div class='act muted small'>{escape(why)}</div>")
    else:
        st_txt = SG.STATUS.get(str(r.get("status")), str(r.get("status_text") or ""))
        data = (f" data-t='{escape(t)}' data-code='{escape(str(r.get('code') or t))}' data-name='{escape(str(r.get('name') or ''))}'"
                f" data-px='{px:g}' data-lot='{lot}' data-rule='{n}' data-limit='{float(b.get('limit') or 0):g}'"
                f" data-sig='{1 if r.get('signal') else 0}' data-status='{escape(st_txt)}'"
                f" data-rtext='{escape(str(ru.get('text') or ''))}' data-warn='{escape(warn)}'")
        H.append(f"<div class='act'><button class='btn primary' data-act='buy'{data}>买入…</button>"
                 f"<span class='muted small'>按规则约 {n:,} 股 · 约 {_yen(n * px)}"
                 + (f" · 约占权益 {n * px / eq * 100:.1f}%" if eq else "") + "</span></div>"
                 + (f"<div class='small neg'>★ {escape(warn)}</div>" if warn else ""))
    H.append(_buy_price_line(r, fill))                       # 规则的买价（2026-10-07 用户「建议的股票要给出合适的买价」）
    planned = " data-planned='1'" if ru.get("state") in ("planned", "manual") or b.get("planned") else ""   # 已排在开盘买：只写现价
    H.append(f"<details class='kl'{' open' if r.get('status') in ('triggered', 'imminent') else ''}>"
             f"<summary>K 线 · 现价</summary><div class='qt small' data-sq='{escape(t)}'{planned}></div>{chart(t, 'suggest')}</details></div>")
    return "".join(H)


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
        + (f"<div class='s'>{dots(x.get('dots'))}{escape(str(x.get('sub') or ''))}</div>" if x.get("sub") or x.get("dots") else "")
        + "</div>" for x in info.get("tiles") or [])
    rows = "".join(
        f"<div class='axr'><div class='axk'>{escape(str(r['k']))}</div><div class='axv'><div>{escape(str(r['text']))}</div>"
        + (f"<div class='axm'>{''.join(chip(c) for c in r['chips'])}</div>" if r.get("chips") else "")
        + (f"<div class='muted small'>{escape(str(r['sub']))}</div>" if r.get("sub") else "") + "</div></div>"
        for r in info.get("rows") or [])
    notes = "".join(f"<li>{escape(str(n))}</li>" for n in info.get("notes") or [])
    return (f"<div class='axb{' hot' if info.get('hot') else ''}' data-exit='{escape(str(info.get('t') or ''))}'>"
            f"<div class='axh'><b>什么时候会自动卖</b><span class='muted small'>按 {escape(str(info.get('asof_md') or '—'))} 收盘</span></div>"
            + (f"<div class='axt'>{tiles}</div>" if tiles else "")
            + f"{rows}<div class='muted small axn'>{escape(str(info.get('never') or ''))}</div>"
            + (f"<details class='axd'><summary class='muted'>时间线与历史</summary><ul>{notes}</ul></details>" if notes else "")
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
    --resolve 登记之后马上消失）、交易日 08:00 之后今天早上的运行还没完成、今天 09:30 自检没通过（out/watchdog_<账本>.json）。
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
    cap = float(man.get("cap_pct") or MO.CAP_PCT)
    kl = sm.get("kline") or {}
    ktrend = kl.get("trend") or {}
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
         + "</nav></header><main>"]
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
    H.append(_broker_card(tag, now))                      # 〔77〕C：立花那边实际是什么（快照）
    H.append(_gate_card(tag))                             # 〔77〕C：上线准备
    hv = sm.get("holding_view") or {}
    if not hv.get("holdings") and not hv.get("core") and st:               # 还没有算过（旧的汇总）：用账本里的数字
        hv = {"bar_date": st.get("last_date"),
              "holdings": [{"ticker": t, "shares": int(p.get("shares") or 0), "entry_date": p.get("entry_date"),
                            "entry_px": p.get("entry_px"), "error": "持有理由 / 趋势在下一次执行器运行之后显示"}
                           for t, p in (st.get("pos") or {}).items()],
              "core": [{"ticker": t, "name": t, "units": int(u), "why": "闲置资金规则（核心 ETF）"}
                       for t, u in (st.get("core_units") or {}).items() if int(u)]}

    def chart(t: str, kind: str) -> str:
        return (f"<div class='chart' data-t='{escape(t)}' data-kind='{kind}'><span class='muted small'>"
                f"{'K 线（要 JavaScript）' if has_k else 'K 线在执行器下一次运行之后显示'}</span></div>")

    def actions(r: dict, kind: str) -> str:
        t = str(r["ticker"])
        if kind == "core":
            return tchips(ktrend.get(t)) + _core_actions(r, t) + _core_exit(t) + chart(t, "core")
        qt = f"<div class='qt small' data-q='{escape(t)}'></div>" if t in (st.get("pos") or {}) else ""   # 现价（/api/quotes）
        return tchips(ktrend.get(t), stats=True) + qt + _actions(r, t)

    def _core_actions(r: dict, t: str) -> str:
        """持有的核心 ETF：卖出全部（= 闲置资金比例 0%：卖出后停买，出现买入信号要你确认才买）/ 调仓…（换算成「闲置资金比例」：
        规则每天把核心调回 规则目标额 × 比例）。执行器还没算过规则目标额（更新后第一次运行之前）也能卖出全部。"""
        cur = int((st.get("core_units") or {}).get(t, 0))
        if cur <= 0:
            return ""
        qt = f"<div class='qt small' data-q='{escape(t)}'></div>"                      # 现价（/api/quotes，盘中每 1 分钟刷新）
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
        data = f" data-t='{escape(t)}' data-name='{escape(str(r.get('name') or ''))}' data-shares='{sh}'"
        return ("<div class='act'>"
                f"<button class='btn sell' data-act='sell'{data}>卖出全部</button>"
                f"<button class='btn' data-act='adj'{data} data-px='{px:g}'{'' if px > 0 and eq else ' disabled'}>调仓…</button></div>"
                f"<div class='muted small'>现在 {sh:,} 股 · 约 {_yen(sh * px)} · 约占权益 {f'{cur:.1f}' if cur is not None else '—'}%</div>"
                + chart(t, "stock"))
    held_core = {str(r.get("ticker")) for r in hv.get("core") or []}
    other = [(t, c) for t, c in (kl.get("items") or {}).items() if c.get("kind") == "core" and t not in held_core]
    more = ("<details class='hv'><summary class='muted'>其他闲置资金 ETF（现在没拿）的 K 线</summary>"
            + "".join(f"<div class='hv'><b>{escape(str(c.get('name') or t))}</b> <span class='muted'>现在 0 口</span>"
                      f"{tchips(ktrend.get(t))}{chart(t, 'core')}</div>" for t, c in other) + "</details>") if other else ""
    held_any = bool(st.get("pos")) or any(int(u) > 0 for u in (st.get("core_units") or {}).values())
    H.append(_orders_card(book, now, paper, waiting))       # 今天的单（执行器）：还挂着的给「撤单」；API / Mac 故障时照它在立花网站下
    H.append("<section class='card' id='holdings'>" + HV.html(hv, actions=actions) + more
             + ("<div id='qt-note' class='muted small'>现价：Yahoo 1 分钟线（约晚 20 分钟）</div>" if held_any else "") + "</section>")
    H.append(_suggest_card(sm.get("suggest") or {}, book, tag, buying, when, eq, cap, chart))
    cp = float(man.get("core_pct", 100.0))
    slider = ("<div class='stepper'><button class='btn' data-act='core-step' data-d='-10' aria-label='减 10%'>−10</button>"
              f"<output id='core-val' class='big'>{cp:g}%</output>"
              "<button class='btn' data-act='core-step' data-d='10' aria-label='加 10%'>+10</button></div>"
              f"<input type='range' id='core-pct' min='0' max='100' step='5' value='{cp:g}' aria-label='闲置资金比例 %'>"
              "<div class='act'><button class='btn primary' data-act='core'>保存</button></div>")
    if cpause:                                              # 卖出 ETF 后停买：规则不自动买；出现买入信号只提醒，你点「确认买入」才买
        want = [(t, int(n)) for t, n in (cr.get("units100") or {}).items() if int(n) > 0]
        now_txt = ("想拿 " + "、".join(f"{t} 约 {n:,} 口" for t, n in want) if want else
                   "不拿核心 ETF（熊市 / 没有闲置资金）") if cr.get("units100") is not None else "执行器下一次运行之后显示"
        btn = ("<div class='act muted'>有一条闲置资金比例的指令在处理（见「手动指令」）</div>" if core_busy else
               "<div class='act'><button class='btn primary' data-act='core-resume'>确认买入（恢复照规则）</button></div>")
        H.append(f"<section class='card{' warn' if csig else ''}' id='core'><h2>闲置资金（核心 ETF）</h2>"
                 f"<div><b>停买中</b>（{escape(str(cpause.get('since') or '—'))} 起"
                 + (f"，你卖出 {escape(str(cpause['ticker']))}" if cpause.get("ticker") else "") + "）：闲置资金留现金，规则不自动买 ETF</div>"
                 + (f"<div class='neg'><b>★ 买入信号（{escape(str(csig.get('date')))} 收盘）：{escape(MO.signal_text(csig))}</b></div>"
                    if csig else "<div class='muted small'>出现买入信号（规则从「不拿」变成「拿」）会提醒你（Mac 通知 + 这里）</div>")
                 + f"<div class='muted small'>规则现在：{escape(now_txt)}</div>" + btn
                 + f"<div class='muted small'>确认后{escape(when)}照规则买入，之后每天照规则调。</div>"
                 + f"<details class='hv'><summary class='muted'>按别的比例恢复（例：只放一半）</summary>{slider}</details></section>")
    elif not any(MO.core_info(book, t) for t in held_core):   # 拿着核心 ETF 时在它下面调（卖出全部 / 调仓…）；没拿着时用这里
        H.append("<section class='card' id='core'><h2>闲置资金（核心 ETF）比例</h2>"
                 f"<div>现在：规则目标额的 <b>{cp:g}%</b>（100% = 照规则；0% = 全部留现金）</div>" + slider
                 + f"<div class='muted small'>{escape(when)}照新比例调核心 ETF；之后每天按这个比例。个股照规则。</div></section>")
    items = sorted((man.get("items") or {}).values(), key=lambda x: x.get("at", ""), reverse=True)

    def _what(r: dict) -> str:
        return escape(MO.describe(r))

    rows = []
    for r in waiting:
        btn = (f"<button class='btn sm' data-act='cancel' data-id='{escape(r['id'])}' data-placed='0'>撤回</button>"
               if r["kind"] in MO.ORDER_KINDS + ("core",) and r["id"] not in dropped else "")
        rows.append(f"<div class='li'><div class='grow'><b>{_what(r)}</b> <span class='chip'>"
                    f"{'等下单（撤回中）' if r['id'] in dropped else '等下单'}</span>"
                    f"<div class='muted small'>{escape(str(r.get('at', ''))[5:16].replace('T', ' '))}</div></div>{btn}</div>")
    for it in items[:20]:
        can = (it.get("status") in MO.ACTIVE and it.get("kind") in MO.ORDER_KINDS and not it.get("cancel_req")
               and not (it.get("status") == "placed" and it.get("now")))          # 盘中的单已经发到交易所：页面上撤不了
        btn = (f"<button class='btn sm' data-act='cancel' data-id='{escape(it['id'])}' data-placed='{1 if it.get('status') == 'placed' else 0}'>撤回</button>"
               if can else "")
        rows.append(f"<div class='li'><div class='grow'><b>{_what(it)}</b> <span class='chip'>"
                    f"{escape(MO.status_text(it))}{'（撤回中）' if it.get('cancel_req') else ''}</span>"
                    f"<div class='muted small'>{escape(str(it.get('at', ''))[5:16].replace('T', ' '))}"
                    f"{(' · ' + escape(str(it['msg']))) if it.get('msg') else ''}</div></div>{btn}</div>")
    H.append("<section class='card' id='orders'><h2>手动指令</h2><div class='list'>"
             + ("".join(rows) or "<div class='li muted'>还没有</div>") + "</div></section>")
    bl = man.get("blocks") or {}
    if bl:
        H.append("<section class='card'><h2>手动卖出后不自动买回</h2><div class='list'>" + "".join(
            f"<div class='li'><div class='grow'><b>{escape(t)}</b> <span class='muted'>"
            f"{'一直，直到解除' if b.get('until') is None else '到 ' + escape(str(b['until']))}</span></div>"
            f"<button class='btn sm' data-act='unblock' data-t='{escape(t)}'>解除</button></div>" for t, b in bl.items()) + "</div></section>")
    if halt:
        H.append(f"<section class='card warn' id='halt'><h2 class='neg'>HALT 生效中</h2><div>{escape(halt)}</div>"
                 "<div class='muted small'>不下任何单、持仓不动。恢复只在 Mac 上：在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」。</div></section>")
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
    H.append("</main><div id='toast' class='toast' role='status' hidden></div>")
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
                     for t in dict.fromkeys(list(u100s) + [t for t, u in (st.get("core_units") or {}).items() if int(u) > 0])},
           "kp": {"label": KL.PLAIN, "align": KL.ALIGN_PLAIN, "chan": KL.CHAN_PLAIN},     # K 线的通俗说法（qbreak/kline.py）
           "est": ests, "fee": [[c if c != float("inf") else 1e18, f] for c, f in FEE_TIERS],
           "st": status_json(tag)[1]}                                                         # 〔77〕C UX-16：还在处理的指令 → 每 10 秒问一次   # 卖出的预计收益（按最近收盘；现价来了用现价的）
    js = _NET_JS + _JS.replace("__CFG__", json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/"))
    return _head("qbreak 操作面板") + "<body>" + "".join(H) + _dialogs(paper, cap) + f"<script>{js}</script></body></html>"


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
            f"<script>{_NET_JS}{_PAIR_JS}</script></body></html>")


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
        return "pos" if v > 0 else "neg" if v < 0 else ""
    y = m.get("ytd") or {}
    H = ["<section class='card' id='money'><h2>损益</h2>"
         f"<div class='stats'><div><div class='muted'>当日损益</div><div class='big {cls(m['day'])}'>{sy(m['day'])}</div>"
         f"<div class='muted small'>{m['day_pct']:+.2f}%</div></div>"
         f"<div><div class='muted'>累计损益</div><div class='big {cls(m['tot'])}'>{sy(m['tot'])}</div>"
         f"<div class='muted small'>{m['tot_pct']:+.2f}%（投入本金 {_yen(m['inv'])}）</div></div></div>"
         + MV.sparkline(m["spark"])]
    if y:
        g, w = float(y.get("gain") or 0), float(y.get("withheld") or 0)
        H.append(f"<div class='small'>{y.get('year')} 年已实现 <b class='{cls(g)}'>{sy(g)}</b>（{int(y.get('n') or 0)} 笔：个股 {sy(y.get('stock_gain') or 0)}"
                 f" · 核心 ETF {sy(y.get('core_gain') or 0)}）· 预计已代扣 ¥{w:,.0f}"
                 + "</div>"
                 + (f"<div class='neg small'>★ 不完整：{escape('、'.join(y['incomplete']))} 的买入记录对不上，它的卖出没算进去</div>"
                    if y.get("incomplete") else "")
                 + "<div class='muted small'>特定口座（源泉徴収あり）20.315% 的估算，年内盈亏通算，按成交日分年；以立花的取引報告書 / 年間取引報告書为准</div>")
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


def submit(body: dict, now: dt.datetime | None = None, source: str = "panel") -> tuple[bool, str, dict | None]:
    """页面的一次提交 → (成功?, 说明, 写进去的指令)。与 run.py manual 相同的检查。source：panel（Mac）/ phone（手机）。"""
    tag = str(body.get("book") or "")
    if tag not in BOOKS:
        return False, "不认识的账本", None
    if tag in READONLY:
        return False, "dry-run 的账本只能看：面板不写指令", None
    if str(body.get("kind") or "") == "flow":
        return submit_flow(tag, body, now)
    book, sm = _load(tag)
    try:
        rec = MO.normalize({**body, "source": source})
        rec = MO.core_rec(rec, book) or rec                  # 持有的核心 ETF 的卖出 / 调仓 → 闲置资金比例（规则每天按它调核心）
    except ValueError as e:
        return False, f"没写：{e}", None
    c0 = MO.core_info(book, rec["ticker"]) if rec["kind"] == "core" and rec.get("ticker") else None
    pct0 = MO.core_pct_now(tag, book)                      # 写之前的闲置资金比例（含还没读的指令；0 = 停买中）
    why = MO.check(rec, book, tag, sm=sm, now=now)
    if why:
        return False, f"没写：{why}", None
    rec = MO.append(tag, rec, clock=(lambda: now) if now else None)
    when = MO.when_text(now or now_jst())                   # 马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘
    k, t = rec["kind"], rec.get("ticker")
    msg = {"sell": f"已写：卖出 {t} 全部 → {when}卖出",
           "trim": f"已写：{t} 减到约 {rec.get('pct', 0):g}% → {when}卖出",
           "core": f"已写：闲置资金比例 {rec.get('pct', 0):g}% → 核心 ETF {when}照新比例调",
           "unblock": f"已写：解除 {t} 的不自动买回",
           "cancel": f"已写：撤回 {rec.get('target')}",
           "cancel_order": f"已写：撤单 {rec.get('ticker')}（{rec.get('cid')}）→ 执行器马上撤（已经成交的部分撤不了）"}.get(k)
    if k == "adjust":
        st = book.get("state") or {}
        a = MO.adjust_plan(rec, st, float((book.get("manual") or {}).get("cap_pct") or MO.CAP_PCT))
        if a["delta"] > 0:
            msg = (f"已写：{t} 加 {a['delta']:,} 股（→ {a['target']:,} 股" + ("，截到单只上限" if a["capped"] else "")
                   + f"）→ {when}买入")
        else:
            msg = f"已写：{t} 卖 {-a['delta']:,} 股（→ {a['target']:,} 股）→ {when}卖出"
    if k == "core" and not t and pct0 <= 0 < float(rec["pct"]):                    # 停买后确认买入
        msg = f"已写：确认买入（闲置资金比例 0% → {rec['pct']:g}%）→ {when}照规则买入核心 ETF"
    if k == "core" and t and int(rec.get("target") or 0) <= 0:                     # 核心 ETF 卖出全部：之后停买
        fx = MO.core_effects(book, 0.0, skip=t)
        msg = (f"已写：卖出全部 {t} → {when}卖出；之后停买闲置资金 ETF（出现买入信号会提醒，你确认才买）"
               + ("；同一比例也用在：" + "、".join(f"{x} {a_:,} → {b_:,} 口" for x, a_, b_ in fx) if fx else ""))
    elif c0:
        n = int(rec["target"]) - c0["cur"]
        fx = MO.core_effects(book, rec["pct"], skip=t)        # 规则同时拿两只以上核心 ETF 时：同一比例别的也跟着变
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
        return subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(paths.PROJECT_ROOT), start_new_session=True)

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
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; manifest-src 'self'; "
       "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")


class _Common(BaseHTTPRequestHandler):
    server_version = "qbreak-panel"

    def log_message(self, fmt, *args):                       # 不把请求逐条写进日志（页面每次刷新都会有）
        return

    def _send(self, code: int, body: bytes, ctype: str, headers=()) -> None:
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


def _after_submit(trigger, rec: dict | None) -> None:
    """写了买卖 / 撤回 / 闲置资金比例 → 马上看一次要不要叫执行器（盘中 → 马上下单；开盘前 → 重试加进今天的寄付单）。"""
    if trigger is not None and rec and rec.get("kind") in MO.ORDER_KINDS + ("cancel", "core", "cancel_order"):
        threading.Thread(target=trigger.check, daemon=True).start()


def make_handler(port: int, tok: str, trigger: Trigger | None = None, clock=None, phone_port: int | None = None):
    """本机端口（127.0.0.1:8765）：只接受本机的 Host；写操作要面板令牌。配对码在这里生成（只显示在 Mac 屏幕上）。"""
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}
    hits: list[float] = []
    routes = ("/api/request", "/api/halt", "/api/pair/new", "/api/device/revoke")

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
                self._json(200 if ok else 500, {"ok": ok, "msg": msg})
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
            if u.path not in ("/", "/pair", "/api/chart", "/api/quotes", "/api/status"):
                self._text(404, "没有这个页面")
                return
            dev = self._who()
            if u.path in ("/api/chart", "/api/quotes", "/api/status"):
                if dev is None:
                    self._json(401, {"ok": False, "msg": "这台设备还没配对（或已被取消）"})
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
            if path not in ("/api/pair", "/api/request", "/api/halt", "/api/unpair"):
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
                self._json(200 if ok else 500, {"ok": ok, "msg": msg})
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
    for n in WATCH:
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
