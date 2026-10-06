"""panel.py — 本机操作面板（2026-10-06 用户：「当持仓的时候可以在画面上点击卖出后 第二天或者当天就可以在立花自动交易
可以手动调节当前持仓股票百分比 持仓股票的时候要写出为什么持仓这个股票的原因等等 现在趋势如何等等」）。

只在 127.0.0.1 上监听（Mac 的 LaunchAgent com.qbreak.panel：scripts/install_launchd_panel.sh；或 bash scripts/liveu.sh panel）：
  GET  /?book=paper|tachibana   账本：持仓（为什么持有、现在趋势、约占权益）、核心 ETF、手动指令、不买回；
                                每只持仓有「卖出全部」「减到 X%」，核心 ETF 有「闲置资金比例」，指令有「撤回」
  POST /api/request             写一条手动指令（qbreak/manual_orders.py；与 run.py manual 相同的检查）
按钮只写指令：下单永远是执行器（下一次能下寄付单的运行；HALT / ARM / 持仓核对 / 单笔上限 / 资格检查照常）。
  交易日 07:45〜08:50、今天早上的运行已经完成、有新的卖出 / 减仓 / 撤回 → 叫执行器跑一次重试
  （bash scripts/liveu.sh run --broker … --retry，同一个账本最多 3 分钟一次）→ 当天开盘执行；之后点的 → 下一个交易日 07:40 的运行。
安全：只绑 127.0.0.1；Host 头必须是 127.0.0.1:端口 / localhost:端口（挡 DNS rebinding）；写操作要
  ① 令牌（数据目录的 panel_token，0600；只嵌在本机页面里，别的网站读不到）② 自定义头 X-Qbreak-Token（跨站表单发不出）
  ③ Origin（有的话）必须是本机这个端口 ④ application/json、≤ 4 KB ⑤ 每分钟最多 30 次。
  不读立花的认证信息、不连立花、不下单；页面禁止被嵌入（frame-ancestors 'none'）。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import subprocess
import threading
import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import manual_orders as MO
from . import paths
from .calendar_jp import is_trading_day, now_jst
from .utils import read_json, setup_logging

log = setup_logging("panel")

BOOKS = {"paper": "模拟账户", "tachibana": "立花（本番）", "tachibana_demo": "立花デモ"}
MAX_BODY = 4096
TRIGGER_FROM, TRIGGER_UNTIL = dt.time(7, 45), dt.time(8, 50)
TRIGGER_GAP_S = 180
TOKEN_FILE = "panel_token"


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


# ───────────────────────── 页面 ─────────────────────────
_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#e3e3e0;--pos:#1a7f37;--neg:#c62828;--accent:#2f5bd3}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#161618;--card:#202023;--fg:#ececf0;--muted:#a1a1a8;
--line:#34343a;--pos:#4cc36b;--neg:#ff6b6b;--accent:#8aa8ff}}
:root[data-theme="dark"]{--bg:#161618;--card:#202023;--fg:#ececf0;--muted:#a1a1a8;--line:#34343a;--pos:#4cc36b;--neg:#ff6b6b;--accent:#8aa8ff}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,
"Hiragino Sans","PingFang SC",sans-serif} main{max-width:980px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:16px;margin:0 0 8px} .muted{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.warn{border-color:var(--neg)} .pos{color:var(--pos)} .neg{color:var(--neg)} .n{text-align:right;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-size:14px} td,th{border-bottom:1px solid var(--line);padding:6px 4px;text-align:left;vertical-align:top}
.scroll{overflow-x:auto} a{color:var(--accent)} ul{margin:4px 0;padding-left:18px} summary{cursor:pointer}
.tabs a{display:inline-block;margin:0 8px 6px 0;padding:3px 10px;border:1px solid var(--line);border-radius:999px;text-decoration:none}
.tabs a.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.hv{border-top:1px solid var(--line);padding:10px 0}.hv:first-of-type{border-top:0}
.act{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px}
button{font:inherit;font-size:14px;padding:4px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.sell{border-color:var(--neg);color:var(--neg)} button:disabled{opacity:.5;cursor:default}
input,select{font:inherit;font-size:14px;padding:3px 6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg);width:auto}
input[type=number]{width:80px} #msg{position:sticky;top:0;z-index:2}
"""

_JS = """
const TOKEN = __TOKEN__, BOOK = __BOOK__, PAPER = __PAPER__;
function say(t, bad){const m=document.getElementById('msg');m.hidden=false;m.className='card'+(bad?' warn':'');m.textContent=t;window.scrollTo(0,0);}
async function post(body, confirmText){
  if(confirmText && !confirm(confirmText)) return;
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{
    const r = await fetch('/api/request',{method:'POST',headers:{'Content-Type':'application/json','X-Qbreak-Token':TOKEN},
                                          body:JSON.stringify(Object.assign({book:BOOK,source:'panel'},body))});
    const j = await r.json();
    say(j.msg || (j.ok?'已写':'没写'), !j.ok);
    if(j.ok) setTimeout(()=>location.reload(), 2500); else document.querySelectorAll('button').forEach(b=>b.disabled=false);
  }catch(e){say('页面服务没有响应：'+e, true);document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
const NOTE = PAPER ? '\\n\\n模拟账户：手动操作后会和云端模拟盘不一致（上线门槛「连续 10 个交易日一致」的天数会中断）。' : '';
function sell(t, when){
  const bd = document.getElementById('bd-'+t).value;
  post({kind:'sell', ticker:t, block_days:parseInt(bd,10)},
       '卖出 '+t+' 的全部持股：执行器在 '+when+' 开盘以「寄付成行」卖出。\\n'+(bd==='0'?'之后照常可以按规则买回。':(bd==='-1'?'之后一直不自动买回（直到解除）。':'之后 '+bd+' 个交易日不自动买回。'))+'\\n卖出所得按规则：有新信号买新票，没有就进闲置资金 ETF（想留现金就把闲置资金比例调低）。'+NOTE);
}
function trim(t, cur, when){
  const v = parseFloat(document.getElementById('pct-'+t).value);
  if(!(v>=0 && v<cur)){say('减仓只能减：目标要小于现在的约 '+cur.toFixed(1)+'%（0 = 全部卖出）', true);return;}
  post({kind:'trim', ticker:t, pct:v}, '把 '+t+' 减到总权益的约 '+v+'%（按单元向下取整）：执行器在 '+when+' 开盘以「寄付成行」卖出多出来的股数。'+NOTE);
}
function core(){
  const v = parseFloat(document.getElementById('core-pct').value);
  if(!(v>=0 && v<=100)){say('比例要在 0〜100% 之间', true);return;}
  post({kind:'core', pct:v}, '闲置资金（核心 ETF）比例设为规则目标额的 '+v+'%：从下一次决策（下一个交易日早上的运行）起生效'+(v<100?'，多出来的留现金':'')+'。'+NOTE);
}
function cancelReq(id, placed){
  post({kind:'cancel', target:id}, placed?'撤回 '+id+'：之后不再重下。\\n如果这笔卖单已经发到交易所（今天开盘的单），要撤请在立花网站 / App 上撤；没撤的话开盘照常成交。':'撤回 '+id+'（执行器还没处理）');
}
function unblock(t){ post({kind:'unblock', ticker:t}, '解除 '+t+' 的「不自动买回」：之后有买入信号就会按规则买。'); }
"""


def render(tag: str, tok: str, now: dt.datetime | None = None) -> str:
    """操作面板页面（一个账本）。"""
    from . import holding_view as HV
    now = now or now_jst()
    book, sm = _load(tag)
    st = book.get("state") or {}
    paper = tag.startswith("paper")
    day, today = MO.next_window(now)
    when = f"{day:%m/%d}（{'今天' if today else '下一个交易日'}）"
    man = book.get("manual") or {}
    halt = paths.halt_file().exists()
    armed = (paths.home() / "ARM").exists()
    hist = st.get("history") or []
    eq = float(hist[-1][1]) if hist else None
    pct = MO.position_pct(st)
    pend = st.get("pending_exit") or {}
    waiting = MO.unseen(tag, book)
    busy = {r.get("ticker") for r in waiting if r.get("kind") in ("sell", "trim")}
    busy |= {it.get("ticker") for it in (man.get("items") or {}).values()
             if it.get("kind") in ("sell", "trim") and it.get("status") in MO.ACTIVE and not it.get("cancel_req")}
    H = [f"<h1>qbreak 操作面板</h1><div class='muted'>{escape(now.strftime('%Y-%m-%d %H:%M JST'))}；按钮只写「手动指令」，"
         "下单由执行器在下一次能下寄付单的运行里做（同样的闸门、同样的对账）</div>",
         "<div class='tabs'>" + "".join(f"<a href='/?book={t}' class='{'on' if t == tag else ''}'>{escape(BOOKS[t])}</a>" for t in books()) + "</div>",
         "<section id='msg' class='card' hidden></section>"]
    warn = []
    if halt:
        warn.append(f"HALT 生效中（{escape(str(paths.halt_file()))}）：手动指令会一直等着，HALT 解除之后的下一次运行才处理")
    if not paper and not armed:
        warn.append("立花还没解锁（没有 ARM）：执行器照常处理，但单会被挡住，不会真的发出去")
    if paper:
        warn.append("这是模拟账户：手动操作后会和云端模拟盘不一致（上线门槛「连续 10 个交易日一致」的天数会中断）")
    H.append(f"<section class='card{' warn' if halt else ''}'><b>{escape(BOOKS.get(tag, tag))}</b>：决策日 {escape(str(st.get('last_date') or '—'))}"
             f" → 下一成交日 {escape(str(sm.get('fill_day') or '—'))}；总权益 {_yen(eq)}；现金 {_yen(st.get('cash_jpy'))}<br>"
             f"现在点卖出 / 减仓 → <b>{escape(when)} 开盘</b>执行（成交日 {MO.CUTOFF:%H:%M} 截止；之后点的算下一个交易日）"
             + "".join(f"<br><span class='{'neg' if 'HALT' in w or 'ARM' in w else 'muted'}'>★ {w}</span>" for w in warn) + "</section>")
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

    def actions(r: dict, kind: str) -> str:
        t = str(r["ticker"])
        if kind == "core":
            return ""
        if t not in (st.get("pos") or {}):
            return "<div class='act muted'>（这只票已经不在执行器的账本里）</div>"
        if t in pend:
            return f"<div class='act'><b class='neg'>已排定开盘卖（{escape(MO.REASON_TEXT.get(pend[t], str(pend[t])))}）</b></div>"
        if t in busy:
            return "<div class='act muted'>有一条没处理完的手动指令（见下面「手动指令」，可以撤回）</div>"
        cur = pct.get(t)
        cur_t = f"{cur:.1f}" if cur is not None else "—"
        tj, wj = json.dumps(t), json.dumps(when)
        return ("<div class='act'>"
                f"<button class='sell' onclick='sell({escape(tj)},{escape(wj)})'>卖出全部</button>"
                f"<label class='muted'>之后不自动买回 <select id='bd-{escape(t)}'><option value='20' selected>20 个交易日</option>"
                "<option value='5'>5 个交易日</option><option value='60'>60 个交易日</option><option value='-1'>一直（直到解除）</option>"
                "<option value='0'>不限制</option></select></label>"
                f"<span class='muted'>｜现在约占权益 {cur_t}%，减到</span>"
                f"<input type='number' id='pct-{escape(t)}' min='0' max='100' step='0.5' value='{max(0.0, round((cur or 0) / 2, 1))}'>"
                f"<span class='muted'>%</span><button onclick='trim({escape(tj)},{cur if cur is not None else 0},{escape(wj)})'>减仓</button></div>")
    H.append("<section class='card'>" + HV.html(hv, actions=actions) + "</section>")
    cp = float(man.get("core_pct", 100.0))
    H.append("<section class='card'><h2>闲置资金（核心 ETF）比例</h2>"
             f"<div>现在：规则目标额的 <b>{cp:g}%</b>（100% = 照规则；0% = 卖出核心 ETF、留现金）</div>"
             "<div class='act'><input type='number' id='core-pct' min='0' max='100' step='5' "
             f"value='{cp:g}'><span class='muted'>%</span><button onclick='core()'>保存</button></div>"
             "<div class='muted'>从下一次决策（下一个交易日早上的运行）起生效；只改核心 ETF 的目标额，个股的规则不变。</div></section>")
    items = sorted((man.get("items") or {}).values(), key=lambda x: x.get("at", ""), reverse=True)
    rows = []
    for r in waiting:
        rows.append(f"<tr><td>{escape(str(r.get('at', ''))[5:16])}</td><td>{escape(MO.LABEL.get(r['kind'], r['kind']))} "
                    f"{escape(str(r.get('ticker') or ''))}{(' ' + format(float(r['pct']), 'g') + '%') if r.get('pct') is not None else ''}</td>"
                    "<td>等执行器读</td><td class='muted'>下一次运行处理</td>"
                    + (f"<td><button onclick='cancelReq({escape(json.dumps(r['id']))},false)'>撤回</button></td>"
                       if r["kind"] in ("sell", "trim", "core") else "<td></td>") + "</tr>")
    for it in items[:20]:
        can = it.get("status") in MO.ACTIVE and it.get("kind") in ("sell", "trim") and not it.get("cancel_req")
        rows.append(f"<tr><td>{escape(str(it.get('at', ''))[5:16])}</td><td>{escape(MO.LABEL.get(it.get('kind'), str(it.get('kind'))))} "
                    f"{escape(str(it.get('ticker') or ''))}{(' ' + format(float(it['pct']), 'g') + '%') if it.get('pct') is not None else ''}</td>"
                    f"<td>{escape(MO.STATUS.get(it.get('status'), str(it.get('status'))))}{'（撤回中）' if it.get('cancel_req') else ''}</td>"
                    f"<td class='muted'>{escape(str(it.get('msg') or ''))}</td>"
                    + (f"<td><button onclick='cancelReq({escape(json.dumps(it['id']))},{str(it.get('status') == 'placed').lower()})'>撤回</button></td>"
                       if can else "<td></td>") + "</tr>")
    H.append("<section class='card'><h2>手动指令</h2><div class='scroll'><table><tr><th>时间</th><th>指令</th><th>状态</th><th>说明</th><th></th></tr>"
             + ("".join(rows) or "<tr><td colspan=5 class='muted'>还没有</td></tr>") + "</table></div></section>")
    bl = man.get("blocks") or {}
    if bl:
        H.append("<section class='card'><h2>手动卖出后不自动买回</h2><ul>" + "".join(
            f"<li>{escape(t)}：{'一直，直到解除' if b.get('until') is None else '到 ' + escape(str(b['until']))}"
            f" <button onclick='unblock({escape(json.dumps(t))})'>解除</button></li>" for t, b in bl.items()) + "</ul></section>")
    H.append("<div class='muted'>账本与日志的完整页面：数据目录 out/page_" + escape(tag) + ".html（每天早上自动打开）。非投资建议。</div>")
    js = (_JS.replace("__TOKEN__", json.dumps(tok)).replace("__BOOK__", json.dumps(tag))
          .replace("__PAPER__", "true" if paper else "false"))
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>qbreak 操作面板</title><style>{_CSS}</style></head><body><main>{''.join(H)}</main>"
            f"<script>{js}</script></body></html>")


# ───────────────────────── 写指令 ─────────────────────────
def submit(body: dict, now: dt.datetime | None = None) -> tuple[bool, str, dict | None]:
    """页面的一次提交 → (成功?, 说明, 写进去的指令)。与 run.py manual 相同的检查。"""
    tag = str(body.get("book") or "")
    if tag not in BOOKS:
        return False, "不认识的账本", None
    try:
        rec = MO.normalize({**body, "source": "panel"})
    except ValueError as e:
        return False, f"没写：{e}", None
    book, _ = _load(tag)
    why = MO.check(rec, book, tag)
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
           "cancel": f"已写：撤回 {rec.get('target')} → 下一次运行处理"}[k]
    if paths.halt_file().exists() and k in ("sell", "trim"):
        msg += "；★ HALT 生效中：HALT 解除之后的下一次运行才处理"
    return True, msg + f"（指令 {rec['id']}）", rec


class Trigger:
    """交易日 07:45〜08:50：今天早上的运行已经完成、又有新的卖出 / 减仓 / 撤回 → 叫执行器跑一次重试（同一个账本最多 3 分钟一次）。"""

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


# ───────────────────────── HTTP ─────────────────────────
def make_handler(port: int, tok: str, trigger: Trigger | None = None, clock=None):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}
    hits: list[float] = []

    class H(BaseHTTPRequestHandler):
        server_version = "qbreak-panel"

        def log_message(self, fmt, *args):                   # 不把请求逐条写进日志（页面每次刷新都会有）
            return

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                                        "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            if self.headers.get("Host") not in hosts:
                self._send(421, "只接受 127.0.0.1 / localhost".encode("utf-8"), "text/plain; charset=utf-8")
                return False
            return True

        def do_GET(self):                                    # noqa: N802
            if not self._host_ok():
                return
            u = urlparse(self.path)
            if u.path == "/favicon.ico":
                self._send(204, b"", "text/plain")
                return
            if u.path != "/":
                self._send(404, "没有这个页面".encode("utf-8"), "text/plain; charset=utf-8")
                return
            tag = (parse_qs(u.query).get("book") or ["paper"])[0]
            if tag not in BOOKS:
                tag = "paper"
            try:
                html = render(tag, tok, (clock or now_jst)())
            except Exception as e:                           # noqa: BLE001
                log.exception("面板页面出错")
                html = f"<!doctype html><meta charset='utf-8'><p>页面出错：{escape(type(e).__name__)}: {escape(str(e))[:300]}</p>"
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):                                   # noqa: N802
            if not self._host_ok():
                return
            if urlparse(self.path).path != "/api/request":
                self._json(404, {"ok": False, "msg": "没有这个接口"})
                return
            org = self.headers.get("Origin")
            if org is not None and org not in origins:
                self._json(403, {"ok": False, "msg": "来源不对（只接受本机这个页面）"})
                return
            if not secrets.compare_digest(str(self.headers.get("X-Qbreak-Token") or ""), tok):
                self._json(403, {"ok": False, "msg": "令牌不对：刷新页面再试"})
                return
            if not str(self.headers.get("Content-Type") or "").startswith("application/json"):
                self._json(415, {"ok": False, "msg": "只接受 JSON"})
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if not 0 < n <= MAX_BODY:
                self._json(413, {"ok": False, "msg": "请求太大"})
                return
            now_m = time.monotonic()
            hits[:] = [x for x in hits if now_m - x < 60] + [now_m]
            if len(hits) > 30:
                self._json(429, {"ok": False, "msg": "太频繁了，过一分钟再试"})
                return
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                assert isinstance(body, dict)
            except Exception:                                # noqa: BLE001
                self._json(400, {"ok": False, "msg": "格式不对"})
                return
            ok, msg, rec = submit(body, (clock or now_jst)())
            if ok:
                log.info("面板写了手动指令 %s（%s）", rec["id"], body.get("book"))
                if trigger is not None and rec["kind"] in ("sell", "trim", "cancel"):
                    threading.Thread(target=trigger.check, daemon=True).start()
            self._json(200 if ok else 400, {"ok": ok, "msg": msg, "id": (rec or {}).get("id")})
    return H


def serve(port: int = 8765, open_browser: bool = False, trigger: bool = True) -> int:
    """在 127.0.0.1:port 上运行（前台；LaunchAgent 用 KeepAlive 守着）。"""
    tok = token()
    trg = Trigger() if trigger else None
    srv = ThreadingHTTPServer(("127.0.0.1", int(port)), make_handler(int(port), tok, trg))
    stop = threading.Event()
    if trg is not None:
        threading.Thread(target=trg.loop, args=(stop,), daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"操作面板：{url}（只在本机；Ctrl-C 结束）")
    log.info("操作面板启动 %s", url)
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
        srv.server_close()
    return 0


__all__ = ["serve", "render", "submit", "token", "Trigger", "make_handler", "BOOKS"]
