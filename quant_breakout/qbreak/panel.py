"""panel.py — 操作面板：Mac 本机 + 手机（2026-10-06 用户：「当持仓的时候可以在画面上点击卖出后 第二天或者当天就可以在立花自动交易
可以手动调节当前持仓股票百分比 持仓股票的时候要写出为什么持仓这个股票的原因等等 现在趋势如何等等」；同日：「做一个可以在手机上操作的页面」）。

两个只在本机（127.0.0.1）监听的端口（Mac 的 LaunchAgent com.qbreak.panel：scripts/install_launchd_panel.sh；或 bash scripts/liveu.sh panel）：
  8765 本机：http://127.0.0.1:8765/ —— 只有这台 Mac 能打开；写操作要令牌（数据目录 panel_token，0600）
  8766 手机：Tailscale Serve（bash scripts/liveu.sh phone on）把它放到 https://<Mac>.<tailnet>.ts.net/，只有你 Tailscale 里的设备能连；
       这一路永远要「已配对的设备」（qbreak/panel_phone.py：配对码只显示在 Mac 屏幕上；设备 cookie + 每台设备的 CSRF 令牌）
页面（手机优先的版面；两边一样）：
  GET  /?book=paper|tachibana   账本：持仓（为什么持有、现在趋势、约占权益、K 线）、核心 ETF（K 线）、建议的股票（规则的候选 + 「买入…」）、
                                手动指令、不买回、停止下单（HALT）；每只持仓有「卖出全部」「调整…」（股数 / 金额 / 占权益 %，可加可减；底部弹出确认），
                                核心 ETF 有「闲置资金比例」，指令有「撤回」；K 线：同花顺式日K / 周K / 月K（红涨空心、绿跌实心）+ MA5 / 10 / 20 / 30
                                + 成交量 + 成本 / 止损线（2026-10-06 用户：「趋势是做一个和图中一样的日周月的块块和线 方便看的」）
  GET  /api/chart?book=…&t=…    一只票的 K 线（执行器写的 out/charts_<账本>.json；打开 / 滑到那只票时才取；手机端口要已配对的设备）
  POST /api/request             写一条手动指令（qbreak/manual_orders.py；与 run.py manual 相同的检查）
  POST /api/halt                建 HALT（只能建、不能解除；解除只在 Mac 上、用户明确说）
  本机才有：POST /api/pair/new（生成配对码）、/api/device/revoke（取消一台设备）；手机才有：/api/pair、/api/unpair（退出这台设备）
按钮只写指令：下单永远是执行器（下一次能下寄付单的运行；HALT / ARM / 持仓核对 / 单笔上限 / 资格检查照常）。
  交易日 07:45〜08:50、今天早上的运行已经完成、有新的卖出 / 减仓 / 撤回 → 叫执行器跑一次重试
  （bash scripts/liveu.sh run --broker … --retry，同一个账本最多 3 分钟一次）→ 当天开盘执行；之后点的 → 下一个交易日 07:40 的运行。
安全：只绑 127.0.0.1；Host 头：本机端口只接受 127.0.0.1 / localhost，手机端口只接受 *.ts.net（挡 DNS rebinding）；写操作要
  ① 令牌（本机）/ 设备 cookie + CSRF 令牌（手机）② 自定义头（跨站表单发不出）③ Origin（有的话）必须是这个页面自己
  ④ application/json、≤ 4 KB ⑤ 每分钟最多 30 次（配对 10 次）。不读立花的认证信息、不连立花、不下单；页面禁止被嵌入。
代码更新（git pull）之后面板自己退出，LaunchAgent 用新代码重启。
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
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

from . import manual_orders as MO
from . import panel_phone as PP
from . import paths
from .calendar_jp import JST, is_trading_day, now_jst
from .utils import read_json, setup_logging

log = setup_logging("panel")

BOOKS = {"paper": "模拟账户", "tachibana": "立花（本番）", "tachibana_demo": "立花デモ"}
MAX_BODY = 4096
TRIGGER_FROM, TRIGGER_UNTIL = dt.time(7, 45), dt.time(8, 50)
TRIGGER_GAP_S = 180
TOKEN_FILE = "panel_token"
WATCH = ("panel.py", "panel_phone.py", "manual_orders.py", "holding_view.py")


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
    """有账本的执行器（模拟账户总列出来）。"""
    return [t for t in BOOKS if t == "paper" or (paths.state_dir() / f"live_unified_{t}.json").exists()]


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
.chartbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:10px 0 2px}
.chart{position:relative;margin-top:10px;outline:none}.chart:focus-visible{box-shadow:0 0 0 2px var(--accent);border-radius:8px}
.chart.empty{padding:6px 0}
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
.chart .ro{font-size:13px;line-height:1.45;color:var(--muted);font-variant-numeric:tabular-nums;min-height:2.9em;margin:2px 0 0}
.chart .ro b{font-size:14px}.chart .ro .m{color:var(--fg)}
.key{display:inline-block;width:14px;height:2px;border-radius:1px;vertical-align:middle;margin-right:6px}
.key.m5{background:var(--fg)}.key.m10{background:var(--ma10)}.key.m20{background:var(--ma20)}.key.m30{background:var(--ma30)}
.up{color:var(--up)}.down{color:var(--down)}
.tchips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.tchip{display:inline-block;padding:2px 10px;border-radius:999px;background:var(--chip);font-size:13px;white-space:nowrap}
.chip.hot{background:var(--accent);color:var(--accent-fg);font-weight:600}
.meta{font-size:14px;color:var(--muted);font-variant-numeric:tabular-nums}
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

_JS = """
const CFG = __CFG__;
const $ = s => document.querySelector(s);
const fmt = n => Number(n).toLocaleString('ja-JP');
const yen = v => '¥' + fmt(Math.round(v));
function toast(t, bad){const m=$('#toast');m.textContent=t;m.className='toast'+(bad?' bad':'');m.hidden=false;
  clearTimeout(toast.h);toast.h=setTimeout(()=>{m.hidden=true;}, bad?9000:6000);}
function busy(on){document.querySelectorAll('button').forEach(b=>{if(on){b.dataset.was=b.disabled?'1':'';b.disabled=true;}else{b.disabled=b.dataset.was==='1';}});}
async function api(path, body){
  busy(true);
  try{
    const h={'Content-Type':'application/json'}; h[CFG.auth.h]=CFG.auth.v;
    const r=await fetch(path,{method:'POST',headers:h,body:JSON.stringify(body||{}),credentials:'same-origin',cache:'no-store'});
    let j={}; try{ j=await r.json(); }catch(e){}
    busy(false);
    if(!r.ok || !j.ok){ toast(j.msg || ('没写成（HTTP '+r.status+'）'), true); if(r.status===401) setTimeout(()=>location.reload(),1500); return null; }
    return j;
  }catch(e){ busy(false); toast('连不上面板：'+e+'\\n（Mac 睡着了、面板没运行，或手机的 Tailscale 没连上）', true); return null; }
}
function done(j){ if(!j) return; toast(j.msg || '已写'); setTimeout(()=>location.reload(), 2200); }
function sheet(id){ const d=$(id); if(d.showModal){ if(!d.open) d.showModal(); } else d.setAttribute('open',''); return d; }
function closeAll(){ document.querySelectorAll('dialog[open]').forEach(d=>{ if(d.close) d.close(); else d.removeAttribute('open'); }); }
let ASK=null, CUR=null;
function ask(title, body, okText, opt){
  opt=opt||{}; $('#ask-title').textContent=title; $('#ask-body').textContent=body;
  const ok=$('#ask-ok'); ok.textContent=okText||'确定'; ok.className='btn '+(opt.danger?'danger':'primary');
  const inp=$('#ask-input'); inp.hidden=!opt.input; inp.value=''; inp.placeholder=opt.input||'';
  sheet('#dlg-ask'); return new Promise(res=>{ ASK=res; });
}
const NOTE = CFG.paper ? '\\n\\n模拟账户：手动操作后会和云端模拟盘不一致（上线门槛「连续 10 个交易日一致」的天数会中断）。' : '';
function coreShow(){ const r=$('#core-pct'); if(r) $('#core-val').textContent=r.value+'%'; }
// ── 调整持仓（股数 / 金额 / 占权益 %）：按最近收盘估算；执行器按决策时的收盘与权益再算一次 ──
const LOT = CFG.lot || 100;
let ADJ = null;
const pctOf = n => CFG.eq>0 && ADJ.px>0 ? (n*ADJ.px/CFG.eq*100).toFixed(1)+'%' : '—';
function adjCap(){ return ADJ.px>0 && CFG.eq>0 ? Math.floor(CFG.eq*CFG.cap/100/ADJ.px/LOT+1e-9)*LOT : 0; }
function adjTarget(){
  const v=parseFloat($('#adj-val').value); if(!(v>=0) || !isFinite(v)) return null;
  let raw;
  if(ADJ.unit==='shares') raw=v; else if(!(ADJ.px>0)) return null; else if(ADJ.unit==='yen') raw=v/ADJ.px; else raw=CFG.eq*v/100/ADJ.px;
  return Math.max(0, Math.floor(raw/LOT+1e-9)*LOT);
}
function adjShow(n){
  const u=ADJ.unit, e=$('#adj-val');
  e.value = u==='shares' ? n : u==='yen' ? Math.round(n*ADJ.px) : (CFG.eq>0 ? (n*ADJ.px/CFG.eq*100).toFixed(1) : 0);
}
function adjUnit(u){
  const n=adjTarget(); ADJ.unit=u;
  document.querySelectorAll('#adj-seg button').forEach(b=>b.setAttribute('aria-pressed', b.dataset.u===u ? 'true' : 'false'));
  $('#adj-unit').textContent = {shares:'股', yen:'円', pct:'%'}[u];
  $('#adj-val').step = u==='shares' ? LOT : u==='yen' ? 1000 : 0.1;
  adjShow(n==null ? ADJ.shares : n); adjPrev();
}
function adjPrev(){
  const go=$('#adj-go'), out=$('#adj-prev'), c=ADJ, cap=adjCap(), n=adjTarget();
  go.className='btn primary';
  if(n==null){ out.textContent='输入目标（股数 / 金额 / 占总权益 %）'; go.textContent='确认'; go.disabled=true; return; }
  const r=$('#adj-range'); r.value=Math.min(+r.max, n);
  if(n===c.shares){
    out.textContent='按最近收盘 '+yen(c.px)+' 换算还是 '+fmt(n)+' 股（'+LOT+' 股单元向下取整）：不用调';
    go.textContent='确认'; go.disabled=true; return;
  }
  if(n<c.shares){
    const k=c.shares-n;
    out.textContent='卖出 '+fmt(k)+' 股（约 '+yen(k*c.px)+'）：'+fmt(c.shares)+' → '+fmt(n)+' 股，约占权益 '+pctOf(n)
      +'\\n'+CFG.when+' 开盘「寄付成行」'+(n===0 ? '；= 全部卖出（不设「不买回」；要设请用「卖出全部」）' : '');
    go.textContent='确认卖出 '+fmt(k)+' 股'; go.className='btn danger'; go.disabled=false; return;
  }
  let t=n, note='';
  if(t>cap){ t=Math.max(cap, c.shares); note='\\n★ 超过单只上限 '+CFG.cap+'%：截到 '+fmt(t)+' 股'; }
  const k=t-c.shares;
  if(k<=0){
    const nx=c.shares+LOT, full=CFG.eq>0 && c.shares*c.px/CFG.eq*100>=CFG.cap;
    out.textContent = full ? '现在约占权益 '+pctOf(c.shares)+'，已经到单只上限 '+CFG.cap+'%：不能再加'
      : '现在约占权益 '+pctOf(c.shares)+'；再加 1 个单元（'+fmt(LOT)+' 股，约 '+yen(LOT*c.px)+'）就约占 '+pctOf(nx)
        +'，超过单只上限 '+CFG.cap+'%：不能再加';
    go.textContent='确认'; go.disabled=true; return;
  }
  out.textContent='买入 '+fmt(k)+' 股（约 '+yen(k*c.px)+'，限价约 '+yen(c.px*1.03)+'）：'+fmt(c.shares)+' → '+fmt(t)+' 股，约占权益 '+pctOf(t)+note
    +'\\n'+CFG.addWhen+' 开盘「寄付指値」；钱不够时同一个开盘先卖核心 ETF；只做一次（没买到就结束）';
  go.textContent='确认买入 '+fmt(k)+' 股'; go.disabled=false;
}
// ── 买入（建议的股票 → 手动买入指令）：按规则的仓位 / 股数 / 金额 / 占权益 %；执行器在下一次新收盘的决策里按当时的收盘再算 ──
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
  out.textContent='买入约 '+fmt(n)+' 股 · 约 '+yen(n*BUY.px)+' · 约占权益 '+bpct(n)+' · 限价约 '+yen(BUY.limit||BUY.px*1.03)+'（收盘 ×1.03）'+note
    +'\\n'+CFG.addWhen+' 开盘「寄付指値」（执行器在前一天收盘后的决策里按那天的收盘定股数与限价）；钱不够时同一个开盘先卖核心 ETF；'
    +'名额满 / 开盘高于限价 / ストップ高 → 不买；只做一次（没买到就结束）；买入后按规则的止损 / 离场';
  go.textContent='确认买入约 '+fmt(n)+' 股'; go.disabled=false;
}
document.addEventListener('input', e=>{
  if(e.target.id==='core-pct') coreShow();
  if(e.target.id==='adj-val') adjPrev();
  if(e.target.id==='adj-range'){ adjShow(+e.target.value); adjPrev(); }
  if(e.target.id==='buy-val') buyPrev();
});
document.addEventListener('DOMContentLoaded', ()=>{ const d=$('#dlg-ask'); if(d) d.addEventListener('close', ()=>{ if(ASK){ const r=ASK; ASK=null; r({ok:false}); } }); });
document.addEventListener('click', async e=>{
  const b=e.target.closest('[data-act]'); if(!b) return;
  const a=b.dataset.act, d=b.dataset;
  if(a==='reload'){ location.reload(); return; }
  if(a==='close'){ closeAll(); return; }
  if(a==='ask-ok'){ const v=$('#ask-input').value, r=ASK; ASK=null; closeAll(); if(r) r({ok:true, value:v}); return; }
  if(a==='sell'){
    CUR={t:d.t, shares:+d.shares};
    $('#sell-title').textContent='卖出 '+d.t+(d.name?' '+d.name:'');
    $('#sell-desc').textContent='全部 '+fmt(+d.shares)+' 股：执行器在 '+CFG.when+' 开盘以「寄付成行」卖出。'+NOTE;
    sheet('#dlg-sell'); return;
  }
  if(a==='sell-go'){
    const bd=document.querySelector('input[name=bd]:checked').value; closeAll();
    done(await api('/api/request',{book:CFG.book, kind:'sell', ticker:CUR.t, block_days:parseInt(bd,10)})); return;
  }
  if(a==='adj'){
    ADJ={t:d.t, shares:+d.shares, px:+d.px, unit:'shares'};
    $('#adj-title').textContent='调整 '+d.t+(d.name?' '+d.name:'');
    $('#adj-cur').textContent='现在 '+fmt(ADJ.shares)+' 股 · 约 '+yen(ADJ.shares*ADJ.px)+' · 约占权益 '+pctOf(ADJ.shares)
      +'（按最近收盘 '+yen(ADJ.px)+'）';
    $('#adj-cap').textContent=CFG.cap;
    const r=$('#adj-range'); r.max=Math.max(adjCap(), ADJ.shares, LOT); r.step=LOT; r.value=ADJ.shares;
    adjUnit('shares'); sheet('#dlg-adj'); return;
  }
  if(a==='adj-unit'){ adjUnit(d.u); return; }
  if(a==='adj-step'){ const n=adjTarget(); adjShow(Math.max(0, (n==null ? ADJ.shares : n)+(+d.d)*LOT)); adjPrev(); return; }
  if(a==='adj-go'){
    const n=adjTarget(); if(n==null || n===ADJ.shares) return;
    const v = ADJ.unit==='shares' ? n : parseFloat($('#adj-val').value);
    closeAll(); done(await api('/api/request',{book:CFG.book, kind:'adjust', ticker:ADJ.t, unit:ADJ.unit, value:v})); return;
  }
  if(a==='tf'){ TF=d.tf; try{ localStorage.setItem('qbreak.tf', TF); }catch(x){} drawAll(); return; }
  if(a==='buy'){
    BUY={t:d.t, px:+d.px, lot:+d.lot||LOT, rule:+d.rule||0, limit:+d.limit||0, unit:'rule'};
    $('#buy-title').textContent='买入 '+d.code+(d.name ? ' '+d.name : '');
    $('#buy-sig').textContent=(d.sig==='1' ? '今天收盘出了买入信号（'+d.rtext+'）。' : '★ '+d.status+'：还没有买入信号，规则不会买 —— 手动买入是你自己的决定（没有回测验证）。')
      +(d.warn ? '\\n★ '+d.warn : '')+NOTE;
    $('#buy-cap').textContent=CFG.cap;
    buyUnit('rule'); sheet('#dlg-buy'); return;
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
    const q=await ask('闲置资金比例 '+v+'%', '核心 ETF 的目标额 = 规则算出的 × '+v+'%：从下一次决策（下一个交易日早上的运行）起生效'+(v<100?'，多出来的留现金':'')+'。'+NOTE, '保存');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'core', pct:v})); return;
  }
  if(a==='cancel'){
    const q=await ask('撤回 '+d.id, d.placed==='1' ? '之后不再重下。\\n如果这笔单已经发到交易所（今天开盘的单），要撤请在立花网站 / App 上撤；没撤的话开盘照常成交。' : '执行器还没处理：撤回之后不会下单。', '撤回');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'cancel', target:d.id})); return;
  }
  if(a==='unblock'){
    const q=await ask('解除 '+d.t+' 的不自动买回', '之后有买入信号就会按规则买。', '解除');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'unblock', ticker:d.t})); return;
  }
  if(a==='halt'){
    const q=await ask('停止下单（HALT）', '全部账本（模拟账户和立花）从执行器的下一次运行起不下任何单，持仓不动。\\n已经发到交易所的单不会被撤（要撤在立花网站 / App 上撤）。\\n这里只能停：恢复只在 Mac 上（在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」）。', '停止下单', {danger:true, input:'原因（可不填）'});
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
// ── K 线（同花顺式：日K / 周K / 月K；红 = 涨（空心）、绿 = 跌（实心）；MA5 / MA10 / MA20 / MA30；成本 / 止损线）──
// 数据 = 执行器每次运行写的 out/charts_<账本>.json，打开 / 看到哪只票才取（/api/chart）；只展示
const TFS = {D:'日K', W:'周K', M:'月K'};
let TF = 'D';
try{ const v=localStorage.getItem('qbreak.tf'); if(v && TFS[v]) TF=v; }catch(x){}
const KD = {};
const NS='http://www.w3.org/2000/svg', WD=['日','一','二','三','四','五','六'];
const MAS=[['ma5','MA5','m5'],['ma10','MA10','m10'],['ma20','MA20','m20'],['ma30','MA30','m30']];
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
function dlab(d){ return TF==='M' ? d.slice(0,7).replace('-','/')+' 月' : TF==='W' ? d.replace(/-/g,'/')+' 那一周' : d.replace(/-/g,'/')+'（'+WD[new Date(d+'T00:00:00').getDay()]+'）'; }
async function loadK(t){
  if(KD[t] && KD[t]!=='error') return KD[t];
  KD[t]='loading';
  try{
    const r=await fetch('/api/chart?book='+encodeURIComponent(CFG.book)+'&t='+encodeURIComponent(t), {credentials:'same-origin', cache:'no-store'});
    if(r.status===404) KD[t]='none';
    else if(!r.ok) KD[t]='error';
    else { const j=await r.json(); KD[t]=(j && j.data) ? j.data : 'none'; }
  }catch(e){ KD[t]='error'; }
  return KD[t];
}
function legend(head, D, i){
  head.textContent='';
  nd('b',null,TFS[TF],head);
  for(const [k,lab,cls] of MAS){ const v=D[k] && D[k][i]; const sp=nd('span',null,null,head); nd('i','key '+cls,null,sp); sp.appendChild(document.createTextNode(lab+' '+(v==null?'—':pxs(v)))); }
}
function readout(el, D, i, P){
  el.textContent='';
  const pc=i>0 ? D.c[i-1] : null, c=D.c[i], dir=(pc && c>=pc)?'up':(pc && c<pc)?'down':null;
  nd('span','m', dlab(D.d[i])+' ', el);
  nd('b',dir,'收 '+pxs(c)+(pc ? ' '+pcs((c/pc-1)*100) : ''),el);
  el.appendChild(document.createTextNode(' · 开 '+pxs(D.o[i])+' 高 '+pxs(D.h[i])+' 低 '+pxs(D.l[i])
    +(pc ? ' · 振幅 '+((D.h[i]-D.l[i])/pc*100).toFixed(2)+'%' : '')+' · 量 '+vfmt(D.v[i]||0)+(P.kind==='core'?' 口':' 股')
    +(P.kind==='stock' && P.entry_px && c!=null ? ' · 比成本 '+pcs((c/P.entry_px-1)*100) : '')));
}
function drawK(box){
  const t=box.dataset.t, P=KD[t];
  const empty=s=>{ box.className='chart empty muted small'; box.textContent=s; };
  if(P==null || P==='loading') return empty('K 线载入中…');
  if(P==='none') return empty('K 线在执行器下一次运行之后显示');
  if(P==='error') return empty('K 线取不到（面板连不上？）：点「刷新」再试');
  const D=(P.tf||{})[TF];
  if(!D || !D.d || D.d.length<2) return empty('没有'+TFS[TF]+'的数据');
  box.className='chart'; box.tabIndex=0; box.textContent='';
  const held=P.kind==='stock', N=D.d.length;
  const W=Math.max(260, Math.round(box.clientWidth||320)), x0=2, x1=W-56, padT=8, H1=176, gap=10, H2=40, padB=18;
  const k=Math.max(2, Math.min(N, Math.floor((x1-x0)/6))), s0=N-k, step=(x1-x0)/k;   // 一根 K 线占 6px：手机约 45 根，Mac 约 100 根
  const X=i=> x0+(i-s0+0.5)*step, bw=Math.max(1, Math.min(13, step*0.68));
  const vb=padT+H1+gap+H2, H=vb+padB;
  const refs=[];
  if(held && P.entry_px) refs.push(['ref','成本',P.entry_px]);
  if(held && P.stop_px) refs.push(['stop','止损',P.stop_px]);
  let lo=Infinity, hi=-Infinity;
  for(let i=s0;i<N;i++){
    if(D.l[i]!=null) lo=Math.min(lo, D.l[i]); if(D.h[i]!=null) hi=Math.max(hi, D.h[i]);
    for(const [m] of MAS){ const v=D[m] && D[m][i]; if(v!=null){ lo=Math.min(lo, v); hi=Math.max(hi, v); } }
  }
  for(const r of refs){ lo=Math.min(lo, r[2]); hi=Math.max(hi, r[2]); }
  const pad=(hi-lo)*0.05 || hi*0.02 || 1; lo-=pad; hi+=pad;
  const Y=v=> padT+H1-(v-lo)/(hi-lo)*H1;
  const head=nd('div','legend',null,box); legend(head, D, N-1);
  const ro=nd('div','ro',null,box); readout(ro, D, N-1, P);                 // 读数固定在图上面（不盖住 K 线）：默认最新一根，点 / 指到哪根就是哪根
  const tr=(P.trend||{})[TF], c0=D.c[s0], c1=D.c[N-1];
  const svg=sv('svg',{viewBox:'0 0 '+W+' '+H, width:W, height:H, role:'img',
    'aria-label':t+' '+TFS[TF]+'（最近 '+k+' 根）：'+pxs(c0)+' → '+pxs(c1)+(tr ? '，趋势 '+tr.label : '')}, box);
  for(const v of nice(lo, hi, 4)){
    const y=Math.round(Y(v))+0.5; sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':'grid'}, svg);
    sv('text',{x:x1+6, y:y+4, 'class':'ax'}, svg).textContent=pxs(v);
  }
  let lastX=-1e9, prev=null;
  for(let i=s0;i<N;i++){
    const d=D.d[i], y=d.slice(0,4), m=+d.slice(5,7); let lab=null;
    const key = TF==='M' ? y : TF==='W' ? y+'-'+Math.floor((m-1)/3) : d.slice(0,7);   // 日K 每月、周K 每季、月K 每年标一次
    if(prev!=null && key!==prev) lab = TF==='M' ? y : (prev.slice(0,4)!==y ? y.slice(2)+' 年' : m+' 月');
    prev=key;
    const x=X(i);
    if(lab && x-lastX>=44 && x>=x0+14 && x<=x1-14){ sv('text',{x:x, y:H-4, 'class':'ax', 'text-anchor':'middle'}, svg).textContent=lab; lastX=x; }
  }
  for(let i=s0;i<N;i++){
    const o=D.o[i], h=D.h[i], l=D.l[i], c=D.c[i]; if(c==null) continue;
    const up=c>=(o==null?c:o), x=X(i), cls=up?'cu':'cd';
    const xx=Math.round(x)+0.5;
    sv('line',{x1:xx, x2:xx, y1:Y(h==null?c:h), y2:Y(l==null?c:l), 'class':'wk '+cls}, svg);
    const yt=Y(Math.max(o==null?c:o, c)), yb=Y(Math.min(o==null?c:o, c));
    sv('rect',{x:(x-bw/2).toFixed(1), y:yt.toFixed(1), width:bw.toFixed(1), height:Math.max(1, yb-yt).toFixed(1), 'class':'bd '+cls}, svg);
  }
  const path=a=>{ let s='', pen=false; for(let i=s0;i<N;i++){ const v=a[i]; if(v==null){ pen=false; continue; } s+=(pen?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1); pen=true; } return s; };
  for(const [m,,cls] of MAS.slice().reverse()) if(D[m]) sv('path',{d:path(D[m]), 'class':'ma '+cls}, svg);
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
  let vmax=0; for(let i=s0;i<N;i++) vmax=Math.max(vmax, D.v[i]||0);
  if(vmax>0) for(let i=s0;i<N;i++){
    const h=(D.v[i]||0)/vmax*H2; if(h<0.5) continue;
    const up=D.c[i]!=null && D.o[i]!=null ? D.c[i]>=D.o[i] : true;
    sv('rect',{x:(X(i)-bw/2).toFixed(1), y:(vb-h).toFixed(1), width:bw.toFixed(1), height:h.toFixed(1), 'class':'vl '+(up?'cu':'cd')}, svg);
  }
  sv('line',{x1:x0, x2:x1, y1:vb+0.5, y2:vb+0.5, 'class':'grid'}, svg);
  if(vmax>0) sv('text',{x:x1+6, y:vb-H2+9, 'class':'ax'}, svg).textContent=vfmt(vmax)+(P.kind==='core' ? ' 口' : ' 股');
  const xh=sv('line',{x1:0, x2:0, y1:padT, y2:vb, 'class':'xh', visibility:'hidden'}, svg);
  const yh=sv('line',{x1:x0, x2:x1, y1:0, y2:0, 'class':'xh', visibility:'hidden'}, svg);
  let cur=null;
  const show=i=>{
    i=Math.max(s0, Math.min(N-1, i)); cur=i; const x=X(i);
    xh.setAttribute('x1',x); xh.setAttribute('x2',x); xh.setAttribute('visibility','visible');
    if(D.c[i]!=null){ const y=Y(D.c[i]); yh.setAttribute('y1',y); yh.setAttribute('y2',y); yh.setAttribute('visibility','visible'); }
    legend(head, D, i); readout(ro, D, i, P);
  };
  const hide=()=>{ cur=null; xh.setAttribute('visibility','hidden'); yh.setAttribute('visibility','hidden'); legend(head, D, N-1); readout(ro, D, N-1, P); };
  box._hide=hide;
  const at=ev=>{ const r=svg.getBoundingClientRect(); return s0+Math.floor(((ev.clientX-r.left)*W/r.width-x0)/step); };
  svg.addEventListener('pointermove', ev=>show(at(ev)));
  svg.addEventListener('pointerdown', ev=>show(at(ev)));
  svg.addEventListener('pointerleave', ev=>{ if(ev.pointerType!=='touch') hide(); });
  box.addEventListener('keydown', ev=>{
    if(ev.key==='ArrowLeft' || ev.key==='ArrowRight'){ ev.preventDefault(); show((cur==null ? N-1 : cur)+(ev.key==='ArrowLeft' ? -1 : 1)); }
    else if(ev.key==='Home'){ ev.preventDefault(); show(s0); } else if(ev.key==='End'){ ev.preventDefault(); show(N-1); }
    else if(ev.key==='Escape') hide();
  });
  box.addEventListener('blur', hide);
  const foot=nd('div','legend',null,box);
  if(tr) nd('span',null,TFS[TF]+'趋势：'+tr.label+(tr.align ? '（'+tr.align+'）' : '')+' · 收盘在 MA20 '+(tr.above20?'上':'下')
    +' · MA20 比 3 根前 '+(tr.slope20_pct>=0?'+':'')+tr.slope20_pct+'%', foot);
  nd('span',null,'红 = 涨（空心）· 绿 = 跌（实心）', foot);
  const det=nd('details',null,null,box); nd('summary','muted small','最近 10 根（表）',det);
  const tb=nd('table',null,null,det), hr=nd('tr',null,null,nd('thead',null,null,tb)), body=nd('tbody',null,null,tb);
  for(const h of ['日期','开','高','低','收','涨跌','成交量']) nd('th',null,h,hr);
  for(let i=N-1;i>=Math.max(0,N-10);i--){
    const r=nd('tr',null,null,body), pc=i>0?D.c[i-1]:null;
    nd('td',null,TF==='M'?D.d[i].slice(0,7).replace('-','/'):D.d[i].slice(5).replace('-','/'),r);
    for(const a of [D.o,D.h,D.l,D.c]) nd('td',null,pxs(a[i]),r);
    nd('td',(pc && D.c[i]>=pc)?'up':(pc && D.c[i]<pc)?'down':null, pc && D.c[i]!=null ? pcs((D.c[i]/pc-1)*100) : '—', r);
    nd('td',null,Number(D.v[i]||0).toLocaleString('ja-JP'),r);
  }
}
async function showK(box){ if(!KD[box.dataset.t] || KD[box.dataset.t]==='error'){ drawK(box); await loadK(box.dataset.t); } drawK(box); }
function drawAll(){
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(KD[b.dataset.t] && b.offsetParent!==null) drawK(b); });
  document.querySelectorAll('[data-act=tf]').forEach(b=>b.setAttribute('aria-pressed', b.dataset.tf===TF ? 'true' : 'false'));
}
const IO = ('IntersectionObserver' in window) ? new IntersectionObserver(es=>{ for(const e of es) if(e.isIntersecting){ IO.unobserve(e.target); showK(e.target); } }, {rootMargin:'200px'}) : null;
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(IO) IO.observe(b); else showK(b); });
  drawAll();
});
document.addEventListener('toggle', e=>{ if(e.target.tagName==='DETAILS' && e.target.open) e.target.querySelectorAll('.chart[data-t]').forEach(b=>{ if(KD[b.dataset.t] && KD[b.dataset.t]!=='loading') drawK(b); }); }, true);
document.addEventListener('pointerdown', ev=>{ if(!ev.target.closest('.chart')) document.querySelectorAll('.chart').forEach(b=>{ if(b._hide) b._hide(); }); });
let RZ=null, LW=window.innerWidth;
window.addEventListener('resize', ()=>{ clearTimeout(RZ); RZ=setTimeout(()=>{ if(Math.abs(window.innerWidth-LW)>2){ LW=window.innerWidth; drawAll(); } }, 150); });
"""

_PAIR_JS = """
const $ = s => document.querySelector(s);
function toast(t, bad){const m=$('#toast');m.textContent=t;m.className='toast'+(bad?' bad':'');m.hidden=false;}
$('#code').addEventListener('input', e=>{ const p=e.target.selectionStart; e.target.value=e.target.value.toUpperCase(); try{e.target.setSelectionRange(p,p);}catch(x){} });
$('#go').addEventListener('click', async ()=>{
  const b=$('#go'); b.disabled=true;
  try{
    const r=await fetch('/api/pair',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',
                                     body:JSON.stringify({code:$('#code').value, name:$('#name').value})});
    let j={}; try{ j=await r.json(); }catch(e){}
    if(r.ok && j.ok){ toast(j.msg); setTimeout(()=>location.replace('/'), 900); return; }
    toast(j.msg || ('没配对成功（HTTP '+r.status+'）'), true);
  }catch(e){ toast('连不上面板：'+e, true); }
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


def _dialogs(paper: bool) -> str:
    bd = [("20", "20 个交易日（默认）"), ("5", "5 个交易日"), ("60", "60 个交易日"), ("-1", "一直（直到解除）"), ("0", "不限制")]
    return ("<dialog id='dlg-sell'><div class='sheet'><h3 id='sell-title'></h3><div id='sell-desc'></div>"
            "<fieldset><legend class='muted'>之后不自动买回</legend>"
            + "".join(f"<label><input type='radio' name='bd' value='{v}'{' checked' if v == '20' else ''}> {t}</label>" for v, t in bd)
            + "</fieldset><div class='muted small'>卖出所得按规则：有新信号买新票，没有就进闲置资金 ETF（想留现金就把闲置资金比例调低）。</div>"
            "<div class='row'><button class='btn' data-act='close'>取消</button><button class='btn danger' data-act='sell-go'>确认卖出</button></div>"
            "</div></dialog>"
            "<dialog id='dlg-adj'><div class='sheet'><h3 id='adj-title'></h3><div id='adj-cur' class='muted'></div>"
            "<div style='margin-top:10px'><div class='seg' id='adj-seg' role='group' aria-label='目标的单位'>"
            "<button data-act='adj-unit' data-u='shares' aria-pressed='true'>股数</button>"
            "<button data-act='adj-unit' data-u='yen' aria-pressed='false'>金额 ¥</button>"
            "<button data-act='adj-unit' data-u='pct' aria-pressed='false'>占权益 %</button></div></div>"
            "<div class='adjrow'><button class='btn' data-act='adj-step' data-d='-1' aria-label='少一个单元'>−</button>"
            "<div class='grow'><input type='number' id='adj-val' inputmode='decimal' min='0' aria-label='目标'><span class='unit' id='adj-unit'>股</span></div>"
            "<button class='btn' data-act='adj-step' data-d='1' aria-label='多一个单元'>＋</button></div>"
            "<input type='range' id='adj-range' min='0' max='100' step='100' value='0' aria-label='目标股数'>"
            "<div id='adj-prev'></div><div class='muted small'>目标 → 执行器按决策时的收盘与权益换成股数（单元向下取整），少于现在 → 卖出多出来的"
            "（寄付成行）；多于现在 → 加仓（寄付指値 = 收盘 ×1.03，钱不够时同一个开盘先卖核心 ETF；单只最多占总权益 "
            "<span id='adj-cap'>34</span>%；资格检查 / 新仓倍数 0 / 决算前的票不加；只做一次）。加仓后成本按股数平均，止损 / 持有天数不变。"
            "规则里的「赢家加仓」研究没有通过：加仓是你的手动决定。"
            + ("模拟账户：手动操作后会和云端模拟盘不一致。" if paper else "") + "</div>"
            "<div class='row'><button class='btn' data-act='close'>取消</button><button class='btn primary' id='adj-go' data-act='adj-go'>确认</button></div>"
            "</div></dialog>"
            "<dialog id='dlg-buy'><div class='sheet'><h3 id='buy-title'></h3><div id='buy-sig'></div>"
            "<div style='margin-top:10px'><div class='seg' id='buy-seg' role='group' aria-label='买多少'>"
            "<button data-act='buy-unit' data-u='rule' aria-pressed='true'>按规则</button>"
            "<button data-act='buy-unit' data-u='shares' aria-pressed='false'>股数</button>"
            "<button data-act='buy-unit' data-u='yen' aria-pressed='false'>金额 ¥</button>"
            "<button data-act='buy-unit' data-u='pct' aria-pressed='false'>占权益 %</button></div></div>"
            "<div class='adjrow' id='buy-row' hidden><button class='btn' data-act='buy-step' data-d='-1' aria-label='少一个单元'>−</button>"
            "<div class='grow'><input type='number' id='buy-val' inputmode='decimal' min='0' aria-label='买多少'><span class='unit' id='buy-unit'>股</span></div>"
            "<button class='btn' data-act='buy-step' data-d='1' aria-label='多一个单元'>＋</button></div>"
            "<div id='buy-prev'></div><div class='muted small'>按规则 = 与规则的新仓同一个算法（总权益 × 25% × 新仓倍数，单元向下取整）。"
            "执行器在下一次新收盘的决策里按那天的收盘再算一遍，过同样的闸门：资格检查 / 立花能不能买 / 手动卖出后不买回 / 决算前 / "
            "新仓倍数 0 的票不买；个股最多 4 只（名额满不买）；单只最多占总权益 <span id='buy-cap'>34</span>%；钱不够时同一个开盘先卖核心 ETF；"
            "开盘高于限价 / ストップ高 → 不买；只做一次。买入后与规则的持仓一样：止损按 ATR、跟踪止损 / 离场信号照常。"
            + ("模拟账户：手动操作后会和云端模拟盘不一致。" if paper else "") + "</div>"
            "<div class='row'><button class='btn' data-act='close'>取消</button><button class='btn primary' id='buy-go' data-act='buy-go'>确认买入</button></div>"
            "</div></dialog>"
            "<dialog id='dlg-ask'><div class='sheet'><h3 id='ask-title'></h3><div id='ask-body'></div>"
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


def tchips(tr: dict | None) -> str:
    """日K / 周K / 月K 的趋势标签（qbreak/kline.py；红 = 上升、绿 = 下降，文字本身就写着，不只靠颜色）。"""
    out = []
    for k, lab in TF_LABEL:
        x = (tr or {}).get(k)
        if not x:
            continue
        cls = {"上升": "up", "下降": "down"}.get(str(x.get("label")), "muted")
        out.append(f"<span class='tchip'>{lab} <b class='{cls}'>{escape(str(x.get('label')))}</b>"
                   + (f" · {escape(str(x['align']))}" if x.get("align") else "") + "</span>")
    return f"<div class='tchips' aria-label='趋势'>{''.join(out)}</div>" if out else ""


def tf_bar() -> str:
    """K 线周期切换（一行，放在所有图上面；两处按钮是同一个开关）。"""
    return ("<div class='chartbar'><span class='muted small'>K 线</span><div class='seg' role='group' aria-label='K 线周期'>"
            + "".join(f"<button data-act='tf' data-tf='{k}' aria-pressed='{'true' if k == 'D' else 'false'}'>{v}</button>" for k, v in TF_LABEL)
            + "</div><span class='muted small'>红 = 涨（空心）· 绿 = 跌（实心）· MA5 / 10 / 20 / 30</span></div>")


def _suggest_card(sg: dict, book: dict, tag: str, buying: set, add_when: str, eq, cap: float, chart, bar: str) -> str:
    """「建议的股票」= 规则的候选（qbreak/suggest.py）+ 每只的「买入…」（写手动买入指令；执行器下单前再查一遍）。"""
    rows = sg.get("rows") or []
    s = MO.slots(book, tag)
    H = ["<section class='card' id='suggest'><h2>建议的股票（规则的候选）</h2>"
         f"<div class='muted'>按 {escape(str(sg.get('asof') or '—'))} 收盘；按「今天出了买入信号 → 即将触发 → 观察中」和条件就绪度排，"
         "不是收益预测，也不是建议。「买入…」只写一条手动买入指令："
         f"<b>{escape(add_when)} 开盘</b>，执行器按规则的闸门再查一遍后下寄付指値。</div>"
         f"<div class='small'>个股名额：拿着 {s['held']} 只 + 排定买入 {s['buys']} 只 / 上限 {s['max']} 只（空 {s['free']} 个）</div>"]
    if sg.get("error"):
        H.append(f"<div class='neg small'>★ 这次没算成：{escape(str(sg['error']))}</div>")
    if not rows:
        H.append("<div class='muted'>" + ("候选在执行器下一次运行之后显示" if not sg else "今天没有出信号 / 即将触发 / 观察中的票") + "</div></section>")
        return "".join(H)
    H.append(bar)
    for r in rows:
        t, b, ru = str(r["ticker"]), r.get("buy") or {}, r.get("rule") or {}
        nm = f" {escape(str(r['name']))}" if r.get("name") else ""
        st_cls = "chip hot" if r.get("status") == "triggered" else "chip"
        meta = [f"就绪度 {r['score']:g}" if r.get("score") is not None else None,
                f"收盘 ¥{r['close']:,.0f}" if r.get("close") is not None else None,
                f"量比 {r['vol_ratio']:.2f} 倍" if r.get("vol_ratio") is not None else None,
                f"横盘振幅 {r['range_pct']:.1f}%" if r.get("range_pct") is not None else None,
                (f"距箱顶 {r['to_box_top_pct']:+.1f}%" if r.get("to_box_top_pct") is not None else None),
                "真突破" if r.get("breakout") else None]
        H.append(f"<div class='hv sg'><div class='head'><b>{escape(str(r.get('code') or t))}</b>{nm}"
                 f"<span class='{st_cls}'>{escape(str(r.get('status_text') or ''))}</span>"
                 + (f"<span class='chip'>{escape(str(r['sector']))}</span>" if r.get("sector") else "") + "</div>"
                 f"<div class='meta'>{' · '.join(x for x in meta if x)}</div>"
                 f"<div>{escape(str(ru.get('text') or ''))}</div>" + tchips(r.get("trend"))
                 + (f"<div class='small neg'>★ 顶部风险：{escape(str(r['top_risk']))}</div>" if r.get("top_risk") else ""))
        n, px, lot = int(b.get("rule_shares") or 0), float(b.get("px") or 0), int(b.get("lot") or MO.LOT)
        why = None
        if b.get("block"):
            why = f"不能买：{b['block']}"
        elif t in buying:
            why = "有一条没处理完的买入指令（见下面「手动指令」，可以撤回）"
        elif ru.get("state") in ("planned", "manual"):
            why = "已经排在下一开盘买入（不用再点）"
        elif s["free"] <= 0:
            why = f"个股名额已满（{s['used']} / {s['max']} 只）：要买先卖出一只"
        elif not (px > 0 and eq):
            why = "没有收盘价 / 总权益：执行器下一次运行之后再买"
        warn = "；".join(b.get("warn") or [])
        if why:
            H.append(f"<div class='act muted small'>{escape(why)}</div>")
        else:
            data = (f" data-t='{escape(t)}' data-code='{escape(str(r.get('code') or t))}' data-name='{escape(str(r.get('name') or ''))}'"
                    f" data-px='{px:g}' data-lot='{lot}' data-rule='{n}' data-limit='{float(b.get('limit') or 0):g}'"
                    f" data-sig='{1 if r.get('signal') else 0}' data-status='{escape(str(r.get('status_text') or ''))}'"
                    f" data-rtext='{escape(str(ru.get('text') or ''))}' data-warn='{escape(warn)}'")
            H.append(f"<div class='act'><button class='btn primary' data-act='buy'{data}>买入…</button>"
                     f"<span class='muted small'>按规则约 {n:,} 股 · 约 {_yen(n * px)}"
                     + (f" · 约占权益 {n * px / eq * 100:.1f}%" if eq else "") + "</span></div>"
                     + (f"<div class='small neg'>★ {escape(warn)}</div>" if warn else ""))
        H.append(f"<details class='kl'{' open' if r.get('status') in ('triggered', 'imminent') else ''}>"
                 f"<summary>K 线（日K / 周K / 月K）</summary>{chart(t, 'suggest')}</details></div>")
    H.append("<div class='muted small'>按规则的股数按最近收盘估算；手动买入是你自己的决定（没触发信号的票没有回测验证），会让账户和云端模拟盘不一致。"
             "非投资建议。</div></section>")
    return "".join(H)


def render(tag: str, tok: str, now: dt.datetime | None = None, mode: str = "local", device: dict | None = None,
           phone: dict | None = None) -> str:
    """操作面板页面（一个账本）。mode = local（Mac 本机：tok = 面板令牌）/ remote（手机：tok = 这台设备的 CSRF 令牌）。"""
    from . import holding_view as HV
    now = now or now_jst()
    remote = mode == "remote"
    book, sm = _load(tag)
    st = book.get("state") or {}
    paper = tag.startswith("paper")
    day, today = MO.next_window(now)
    when = f"{day:%m/%d}（{'今天' if today else '下一个交易日'}）"
    aday, atoday = MO.add_window(now, st.get("last_date"))
    add_when = f"{aday:%m/%d}（{'今天' if atoday else '下一个交易日'}）"
    man = book.get("manual") or {}
    cap = float(man.get("cap_pct") or MO.CAP_PCT)
    kl = sm.get("kline") or {}
    ktrend = kl.get("trend") or {}
    has_k = bool(kl.get("file")) and (paths.out_dir() / str(kl["file"])).exists()
    halt = PP.halt_text()
    armed = (paths.home() / "ARM").exists()
    hist = st.get("history") or []
    eq = float(hist[-1][1]) if hist else None
    pct = MO.position_pct(st)
    pend = st.get("pending_exit") or {}
    waiting = MO.unseen(tag, book)
    busy = {r.get("ticker") for r in waiting if r.get("kind") in MO.POS_KINDS}
    busy |= {it.get("ticker") for it in (man.get("items") or {}).values()
             if it.get("kind") in MO.POS_KINDS and it.get("status") in MO.ACTIVE and not it.get("cancel_req")}
    buying = {r.get("ticker") for r in waiting if r.get("kind") == "buy"}
    buying |= {it.get("ticker") for it in (man.get("items") or {}).values()
               if it.get("kind") == "buy" and it.get("status") in MO.ACTIVE and not it.get("cancel_req")}
    H = ["<header class='top'><div class='bar'><b>qbreak 操作面板</b><span class='sp'></span>"
         f"<span class='muted small'>{escape(now.strftime('%m/%d %H:%M JST'))}</span>"
         "<button class='btn sm' data-act='reload'>刷新</button></div>"
         "<nav class='tabs'>" + "".join(f"<a href='/?book={t}' class='{'on' if t == tag else ''}'>{escape(BOOKS[t])}</a>" for t in books())
         + "</nav></header><main>"]
    warn = []
    if halt:
        warn.append(f"HALT 生效中（{escape(halt)}）：手动指令会一直等着，HALT 解除之后的下一次运行才处理")
    if not paper and not armed:
        warn.append("立花还没解锁（没有 ARM）：执行器照常处理，但单会被挡住，不会真的发出去")
    if paper:
        warn.append("这是模拟账户：手动操作后会和云端模拟盘不一致（上线门槛「连续 10 个交易日一致」的天数会中断）")
    H.append(f"<section class='card{' warn' if halt else ''}'><div class='head'><b>{escape(BOOKS.get(tag, tag))}</b>"
             f"<span class='chip'>决策日 {escape(str(st.get('last_date') or '—'))} → 成交日 {escape(str(sm.get('fill_day') or '—'))}</span></div>"
             f"<div class='stats'><div><div class='muted'>总权益</div><div class='big'>{_yen(eq)}</div></div>"
             f"<div><div class='muted'>现金</div><div class='big'>{_yen(st.get('cash_jpy'))}</div></div></div>"
             f"<div>现在点卖出 / 减仓 → <b>{escape(when)} 开盘</b>执行（成交日 {MO.CUTOFF:%H:%M} 截止；之后点的算下一个交易日）；"
             f"加仓 / 买入 → <b>{escape(add_when)} 开盘</b>（只在新收盘的决策里做）。"
             "按钮只写「手动指令」，下单由执行器在下一次能下寄付单的运行里做（同样的闸门、同样的对账）</div>"
             + "".join(f"<div class='{'neg' if 'HALT' in w or 'ARM' in w else 'muted'} small'>★ {w}</div>" for w in warn) + "</section>")
    if not st:
        H.append("<section class='card'>执行器还没有账本（第一次运行之后才有持仓）。</section>")
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
            return tchips(ktrend.get(t)) + chart(t, "core")
        return tchips(ktrend.get(t)) + _actions(r, t)

    def _actions(r: dict, t: str) -> str:
        p = (st.get("pos") or {}).get(t)
        if p is None:
            return "<div class='act muted'>（这只票已经不在执行器的账本里）</div>" + chart(t, "stock")
        if t in pend:
            return (f"<div class='act'><b class='neg'>已排定开盘卖（{escape(HV.EXIT_TEXT.get(pend[t], str(pend[t])))}）</b></div>"
                    + chart(t, "stock"))
        if t in busy:
            return "<div class='act muted'>有一条没处理完的手动指令（见下面「手动指令」，可以撤回）</div>" + chart(t, "stock")
        cur = pct.get(t)
        px = float(p.get("last_close") or p.get("entry_px") or 0)
        sh = int(p.get("shares") or 0)
        data = f" data-t='{escape(t)}' data-name='{escape(str(r.get('name') or ''))}' data-shares='{sh}'"
        return ("<div class='act'>"
                f"<button class='btn sell' data-act='sell'{data}>卖出全部</button>"
                f"<button class='btn' data-act='adj'{data} data-px='{px:g}'{'' if px > 0 and eq else ' disabled'}>调整…</button></div>"
                f"<div class='muted small'>现在 {sh:,} 股 · 约 {_yen(sh * px)} · 约占权益 {f'{cur:.1f}' if cur is not None else '—'}%"
                f"（调整：按股数 / 金额 / 占权益 %，可加可减；单只上限 {cap:g}%）</div>" + chart(t, "stock"))
    bar = tf_bar() if has_k else ""
    held_core = {str(r.get("ticker")) for r in hv.get("core") or []}
    other = [(t, c) for t, c in (kl.get("items") or {}).items() if c.get("kind") == "core" and t not in held_core]
    more = ("<details class='hv'><summary class='muted'>闲置资金方式里的其他 ETF（现在没拿）的 K 线</summary>"
            + "".join(f"<div class='hv'><b>{escape(str(c.get('name') or t))}</b> <span class='muted'>现在 0 口</span>"
                      f"{tchips(ktrend.get(t))}{chart(t, 'core')}</div>" for t, c in other) + "</details>") if other else ""
    H.append("<section class='card' id='holdings'>" + HV.html(hv, actions=actions, toolbar=bar) + more + "</section>")
    H.append(_suggest_card(sm.get("suggest") or {}, book, tag, buying, add_when, eq, cap, chart, bar))
    cp = float(man.get("core_pct", 100.0))
    H.append("<section class='card' id='core'><h2>闲置资金（核心 ETF）比例</h2>"
             f"<div>现在：规则目标额的 <b>{cp:g}%</b>（100% = 照规则；0% = 卖出核心 ETF、留现金）</div>"
             "<div class='stepper'><button class='btn' data-act='core-step' data-d='-10' aria-label='减 10%'>−10</button>"
             f"<output id='core-val' class='big'>{cp:g}%</output>"
             "<button class='btn' data-act='core-step' data-d='10' aria-label='加 10%'>+10</button></div>"
             f"<input type='range' id='core-pct' min='0' max='100' step='5' value='{cp:g}' aria-label='闲置资金比例 %'>"
             "<div class='act'><button class='btn primary' data-act='core'>保存</button></div>"
             "<div class='muted small'>从下一次决策（下一个交易日早上的运行）起生效；只改核心 ETF 的目标额，个股的规则不变。</div></section>")
    items = sorted((man.get("items") or {}).values(), key=lambda x: x.get("at", ""), reverse=True)

    def _what(r: dict) -> str:
        return escape(MO.describe(r))

    rows = []
    for r in waiting:
        btn = (f"<button class='btn sm' data-act='cancel' data-id='{escape(r['id'])}' data-placed='0'>撤回</button>"
               if r["kind"] in MO.ORDER_KINDS + ("core",) else "")
        rows.append(f"<div class='li'><div class='grow'><b>{_what(r)}</b> <span class='chip'>等执行器读</span>"
                    f"<div class='muted small'>{escape(str(r.get('at', ''))[5:16].replace('T', ' '))} · 下一次运行处理</div></div>{btn}</div>")
    for it in items[:20]:
        can = it.get("status") in MO.ACTIVE and it.get("kind") in MO.ORDER_KINDS and not it.get("cancel_req")
        btn = (f"<button class='btn sm' data-act='cancel' data-id='{escape(it['id'])}' data-placed='{1 if it.get('status') == 'placed' else 0}'>撤回</button>"
               if can else "")
        rows.append(f"<div class='li'><div class='grow'><b>{_what(it)}</b> <span class='chip'>"
                    f"{escape(MO.STATUS.get(it.get('status'), str(it.get('status'))))}{'（撤回中）' if it.get('cancel_req') else ''}</span>"
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
                 "<div class='muted small'>执行器不下任何单（买卖都不下、持仓不动）。恢复只在 Mac 上：在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」。</div></section>")
    else:
        H.append("<section class='card' id='halt'><h2>紧急停止</h2><div class='muted small'>停止全部账本（模拟账户和立花）的下单：执行器的下一次运行起"
                 "买卖都不下、持仓不动。已经发到交易所的单不会被撤（要撤在立花网站 / App 上撤）。这里只能停、不能恢复。</div>"
                 "<div class='act'><button class='btn danger' data-act='halt'>停止下单（HALT）</button></div></section>")
    if not remote:
        H.append(_phone_card(phone or {}))
        H.append("<footer>账本与日志的完整页面：数据目录 out/page_" + escape(tag) + ".html（每天早上自动打开）。非投资建议。</footer>")
    else:
        dv = device or {}
        H.append(f"<footer><div>这台设备：{escape(str(dv.get('name') or '手机'))}（配对 {escape(str(dv.get('created') or '')[:10])}）。"
                 "非投资建议。</div><div class='act'><button class='btn sm' data-act='unpair'>退出这台设备</button></div></footer>")
    H.append("</main><div id='toast' class='toast' role='status' hidden></div>")
    cfg = {"auth": {"h": "X-Qbreak-Csrf" if remote else "X-Qbreak-Token", "v": tok}, "book": tag, "paper": paper,
           "when": when, "addWhen": add_when, "eq": eq or 0, "cap": cap, "lot": MO.LOT}
    js = _JS.replace("__CFG__", json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/"))
    return _head("qbreak 操作面板") + "<body>" + "".join(H) + _dialogs(paper) + f"<script>{js}</script></body></html>"


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
            "在 Mac 的面板上随时可以取消。</p></section></main><div id='toast' class='toast' role='status' hidden></div>"
            f"<script>{_PAIR_JS}</script></body></html>")


# ───────────────────────── 写指令 ─────────────────────────
def submit(body: dict, now: dt.datetime | None = None, source: str = "panel") -> tuple[bool, str, dict | None]:
    """页面的一次提交 → (成功?, 说明, 写进去的指令)。与 run.py manual 相同的检查。source：panel（Mac）/ phone（手机）。"""
    tag = str(body.get("book") or "")
    if tag not in BOOKS:
        return False, "不认识的账本", None
    try:
        rec = MO.normalize({**body, "source": source})
    except ValueError as e:
        return False, f"没写：{e}", None
    book, sm = _load(tag)
    why = MO.check(rec, book, tag, sm=sm)
    if why:
        return False, f"没写：{why}", None
    rec = MO.append(tag, rec, clock=(lambda: now) if now else None)
    day, today = MO.next_window(now or now_jst())
    when = f"{day:%m/%d}（{'今天' if today else '下一个交易日'}）开盘"
    k = rec["kind"]
    msg = {"sell": f"已写：卖出 {rec.get('ticker')} 全部 → 执行器在 {when}前的运行里下寄付成行单",
           "trim": f"已写：{rec.get('ticker')} 减到约 {rec.get('pct', 0):g}% → 执行器在 {when}前的运行里下寄付成行单",
           "core": f"已写：闲置资金比例 {rec.get('pct', 0):g}% → 从下一次决策起生效",
           "unblock": f"已写：解除 {rec.get('ticker')} 的不自动买回 → 下一次运行生效",
           "cancel": f"已写：撤回 {rec.get('target')} → 下一次运行处理"}.get(k)
    if k == "adjust":
        st = book.get("state") or {}
        a = MO.adjust_plan(rec, st, float((book.get("manual") or {}).get("cap_pct") or MO.CAP_PCT))
        if a["delta"] > 0:
            ad, at = MO.add_window(now or now_jst(), st.get("last_date"))
            msg = (f"已写：{rec['ticker']} 调到 {MO.fmt_target(rec)}（估算加 {a['delta']:,} 股 → {a['target']:,} 股"
                   + ("，截到单只上限" if a["capped"] else "") + f"）→ 执行器在 {ad:%m/%d}（{'今天' if at else '下一个交易日'}）"
                   "开盘前的运行里下寄付指値（钱不够时先卖核心 ETF；只做一次）")
        else:
            msg = (f"已写：{rec['ticker']} 调到 {MO.fmt_target(rec)}（估算卖 {-a['delta']:,} 股 → {a['target']:,} 股）"
                   f"→ 执行器在 {when}前的运行里下寄付成行单")
    if k == "buy":
        st = book.get("state") or {}
        ad, at = MO.add_window(now or now_jst(), st.get("last_date"))
        row = next((r for r in (sm.get("suggest") or {}).get("rows") or [] if r.get("ticker") == rec["ticker"]), None)
        est = ""
        if row and rec.get("unit") == "rule":
            n = int((row.get("buy") or {}).get("rule_shares") or 0)
            est = f"，按最近收盘估算约 {n:,} 股 ≈ ¥{n * float((row.get('buy') or {}).get('px') or 0):,.0f}"
        msg = (f"已写：买入 {rec['ticker']}（{MO.fmt_target(rec)}{est}）→ 执行器在 {ad:%m/%d}（{'今天' if at else '下一个交易日'}）"
               "开盘前的运行里按决策日的收盘定股数与限价，下寄付指値（钱不够时先卖核心 ETF；名额满 / 开盘高于限价 → 不买；只做一次）"
               + ("" if row and row.get("signal") else "；★ 这只还没有买入信号：规则不会买，是你自己的决定"))
    if paths.halt_file().exists() and k in MO.ORDER_KINDS:
        msg += "；★ HALT 生效中：HALT 解除之后的下一次运行才处理"
    return True, msg + f"（指令 {rec['id']}）", rec


class Trigger:
    """交易日 07:45〜08:50：今天早上的运行已经完成、又有新的卖出 / 减仓 / 调整 / 撤回 → 叫执行器跑一次重试（同一个账本最多 3 分钟一次；
    加仓不在这次补单里做，等下一次决策）。"""

    def __init__(self, run=None, clock=None):
        self.run = run or self._spawn
        self.clock = clock or now_jst
        self.last: dict[str, float] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _spawn(tag: str):
        broker = "paper" if tag == "paper" else "tachibana"
        cmd = ["/bin/bash", str(paths.PROJECT_ROOT / "scripts" / "liveu.sh"), "run", "--broker", broker, "--retry"]
        if tag == "tachibana_demo":
            cmd.append("--demo")
        lf = open(paths.log_dir() / "com.qbreak.panel.retry.log", "a", encoding="utf-8")
        lf.write(f"\n── {now_jst():%Y-%m-%d %H:%M:%S} JST 手动指令 → {' '.join(cmd[1:])}\n")
        lf.flush()
        return subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(paths.PROJECT_ROOT), start_new_session=True)

    def check(self) -> list[str]:
        """看一遍各个账本；返回这次叫了重试的账本。"""
        from .live_unified import morning_done
        from .trader import expected_last_bar
        now = self.clock()
        if not is_trading_day(now.date()) or not TRIGGER_FROM <= now.time() < TRIGGER_UNTIL:
            return []
        out = []
        with self.lock:
            for tag in books():
                p = self.procs.get(tag)
                if p is not None and getattr(p, "poll", lambda: 0)() is None:
                    continue                                 # 上一次叫的还在跑
                if time.monotonic() - self.last.get(tag, -1e9) < TRIGGER_GAP_S:
                    continue
                book, _ = _load(tag)
                if not morning_done(book, expected_last_bar(now.date(), "JP").isoformat()):
                    continue                                 # 早上的运行还没完成：它自己会读到指令
                if not MO.due(tag, book, now):
                    continue
                self.last[tag] = time.monotonic()
                try:
                    self.procs[tag] = self.run(tag)
                    out.append(tag)
                    log.info("手动指令：叫执行器跑一次重试（%s）", tag)
                except Exception as e:                       # noqa: BLE001
                    log.warning("叫执行器重试失败（%s）：%s", tag, e)
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


def chart_json(tag: str, t: str) -> tuple[int, dict]:
    """一只票的 K 线（执行器写的 out/charts_<账本>.json；按文件的修改时间缓存）→ (HTTP 状态, JSON)。"""
    fp = paths.out_dir() / f"charts_{tag}.json"
    try:
        mt = fp.stat().st_mtime
    except OSError:
        return 404, {"ok": False, "msg": "还没有 K 线（执行器下一次运行之后）"}
    with _CHART_LOCK:
        c = _CHART_CACHE.get(str(fp))
        if c is None or c[0] != mt:
            c = (mt, read_json(fp, {}) or {})
            _CHART_CACHE[str(fp)] = c
    data = c[1]
    pl = (data.get("tickers") or {}).get(t)
    if pl is None:
        return 404, {"ok": False, "msg": f"没有 {t} 的 K 线"}
    return 200, {"ok": True, "t": t, "asof": data.get("asof"), "data": pl}


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

    def _chart(self, query: str) -> None:
        """GET /api/chart?book=…&t=…：一只票的 K 线（只读；本机端口看 Host，手机端口要已配对的设备）。"""
        t = str((parse_qs(query).get("t") or [""])[0]).strip().upper()
        if not _CHART_T.fullmatch(t):
            self._json(400, {"ok": False, "msg": "代码不对"})
            return
        code, obj = chart_json(_book_of(query), t)
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
    tag = (parse_qs(query).get("book") or ["paper"])[0]
    return tag if tag in BOOKS else "paper"


def _after_submit(trigger, rec: dict | None) -> None:
    if trigger is not None and rec and rec["kind"] in MO.POS_KINDS + ("cancel",):
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
                self._chart(u.query)
                return
            if u.path != "/":
                self._text(404, "没有这个页面")
                return
            phone = {"port": phone_port, "url": PP.phone_url(), "devices": PP.devices()}
            self._page(lambda: render(_book_of(u.query), tok, (clock or now_jst)(), mode="local", phone=phone))

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
    h = str(v or "").strip().lower()
    return h[:-4] if h.endswith(":443") else h


def make_phone_handler(port: int, trigger: Trigger | None = None, clock=None):
    """手机端口（127.0.0.1:8766，Tailscale Serve 转过来）：永远要已配对的设备（cookie）；写操作还要这台设备的 CSRF 令牌。
    没配对的只看到输入配对码的页面。配对码不在这里生成，也不能取消别的设备（只在 Mac 上）。"""
    local = {f"127.0.0.1:{port}", f"localhost:{port}"}
    hits_pair: list[float] = []
    hits_post: list[float] = []

    class P(_Common):
        def _host_ok(self) -> bool:
            h = str(self.headers.get("Host") or "").strip().lower()
            if h in local or PP.TS_HOST.match(h):
                return True
            self._text(421, "只接受 Tailscale 的地址（*.ts.net）")
            return False

        def _origin_ok(self) -> bool:
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
            u = urlparse(self.path)
            if self._static(u.path):
                return
            if u.path not in ("/", "/pair", "/api/chart"):
                self._text(404, "没有这个页面")
                return
            dev = PP.device_for(self.headers.get("Cookie"))
            if u.path == "/api/chart":
                if dev is None:
                    self._json(401, {"ok": False, "msg": "这台设备还没配对（或已被取消）"})
                else:
                    self._chart(u.query)
                return
            if dev is None:
                code = (parse_qs(u.query).get("c") or [""])[0] if u.path == "/pair" else ""
                self._page(lambda: pair_page(code))
                return
            if u.path == "/pair":
                self._send(303, b"", "text/plain", [("Location", "/")])
                return
            self._page(lambda: render(_book_of(u.query), PP.csrf(dev["id"]), (clock or now_jst)(), mode="remote", device=dev))

        def do_POST(self):                                   # noqa: N802
            if not self._host_ok():
                return
            path = urlparse(self.path).path
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
            dev = PP.device_for(self.headers.get("Cookie"))
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
          + (f"；手机端口 127.0.0.1:{phone_port}（Tailscale Serve 用，要先配对）" if psrv else ""))
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
