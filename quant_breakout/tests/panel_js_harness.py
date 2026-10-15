"""面板页面脚本在 node 里跑的小环境（测试用；2026-10-15「qbreak网页app经常卡住 永久解决这个问题」）。

run_conn：conn.js（连接检查 / 自动重连 / 安全的自动刷新）+ net.js，假的时钟（setTimeout / Date.now 都是假的，advance(ms) 往前拨）、
          假的 DOM（对话框开没开、输入框有没有焦点、页面看不看得见）、假的网络（NET.mode = up / down / hang / 502 / 500 / 401）。
run_sw：  service worker（panel.SW_JS），假的 caches / fetch / FetchEvent；超时换成几十毫秒。
没有 node → pytest.skip。"""
import json
import shutil
import subprocess

import pytest

from qbreak import panel

CONN_PRELUDE = r"""
const H_IMM = setImmediate;
let H_NOW = 1800000000000;
const H_T = []; let H_ID = 0;
globalThis.setTimeout = (fn, ms) => { const id = ++H_ID; H_T.push({id, at: H_NOW + Math.max(0, +ms || 0), fn}); return id; };
globalThis.clearTimeout = id => { const i = H_T.findIndex(t => t.id === id); if (i >= 0) H_T.splice(i, 1); };
Date.now = () => H_NOW;
async function flush(){ for (let i = 0; i < 30; i++) await new Promise(r => H_IMM(r)); }
async function advance(ms){
  const end = H_NOW + ms;
  for (;;) {
    await flush();
    H_T.sort((a, b) => a.at - b.at || a.id - b.id);
    const t = H_T[0];
    if (!t || t.at > end) break;
    H_T.shift(); H_NOW = Math.max(H_NOW, t.at); t.fn();
  }
  H_NOW = end; await flush();
}
function timers(){ return H_T.length; }
const NET = {mode: 'up', page: null, sig: 'S0', busy: 0, v: 'V1', calls: 0, pages: 0, beacons: []};   // page：页面本身（null = 跟 mode）
const H_HDR = {get: () => null};
globalThis.fetch = (url, opt) => new Promise((res, rej) => {
  url = String(url);
  if (url.startsWith('/api/clientlog')) { NET.beacons.push(decodeURIComponent(url.split('?')[1] || '')); return res({ok: true, status: 204, headers: H_HDR, json: async () => { throw new SyntaxError('empty'); }}); }
  if (!url.startsWith('/api/')) {                                         // 页面本身（conn.js 刷新存着的旧页面之前先确认）
    NET.pages++; const pm = NET.page || NET.mode;
    if (pm === 'up') return res({ok: true, status: 200, headers: {get: k => (k === 'X-Qbreak-Page' ? 'main' : null)}, json: async () => { throw new SyntaxError('html'); }});
    if (pm === '502') return res({ok: false, status: 502, headers: H_HDR, json: async () => { throw new SyntaxError('html'); }});
    if (pm === 'down') return rej(new TypeError('Load failed'));
    if (opt && opt.signal) opt.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), {name: 'AbortError'})));
    return;
  }
  NET.calls++;
  const m = NET.mode;
  if (m === 'up') return res({ok: true, status: 200, headers: H_HDR, json: async () => ({ok: true, sig: NET.sig, busy: NET.busy, pending: NET.busy, v: NET.v, boot: 'b1'})});
  if (m === '401') return res({ok: false, status: 401, headers: H_HDR, json: async () => ({ok: false})});
  if (m === '502') return res({ok: false, status: 502, headers: H_HDR, json: async () => { throw new SyntaxError('html'); }});
  if (m === '500') return res({ok: false, status: 500, headers: H_HDR, json: async () => ({ok: false, msg: '内部错误'})});   // 面板自己出错
  if (m === 'down') return rej(new TypeError('Load failed'));
  if (opt && opt.signal) opt.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), {name: 'AbortError'})));   // hang
});
function H_el(tag){
  const e = {tagName: String(tag).toUpperCase(), hidden: false, textContent: '', dataset: {}, attrs: {}, ls: {}, id: '',
    classList: {s: new Set(), toggle(c, on){ if (on === undefined) on = !this.s.has(c); if (on) this.s.add(c); else this.s.delete(c); },
                add(c){ this.s.add(c); }, remove(c){ this.s.delete(c); }, contains(c){ return this.s.has(c); }},
    setAttribute(k, v){ this.attrs[k] = v; }, addEventListener(t, f){ this.ls[t] = f; }, appendChild(c){ return c; },
    querySelector(s){ return s === 'button' ? this._b : s === '.conn-t' ? this._t : null; }};
  Object.defineProperty(e, 'innerHTML', {set(){ e._t = H_el('span'); e._b = H_el('button'); }});
  return e;
}
const H_DL = {}, H_WL = {};
const DOC = {hidden: false, dlg: null, active: null, cached: false, els: {stale: Object.assign(H_el('div'), {hidden: true})}};
globalThis.document = {
  get hidden(){ return DOC.hidden; },
  addEventListener(t, f){ (H_DL[t] = H_DL[t] || []).push(f); },
  querySelector(s){
    if (s === 'meta[name="qb-cache"]') return DOC.cached ? {} : null;
    if (s === 'dialog[open]') return DOC.dlg;
    if (s[0] === '#') return DOC.els[s.slice(1)] || null;
    return null;
  },
  querySelectorAll(){ return []; },
  createElement: H_el,
  get activeElement(){ return DOC.active; },
  body: {appendChild(c){ if (c.id) DOC.els[c.id] = c; return c; }, classList: {toggle(){}}},
};
globalThis.window = globalThis;
globalThis.addEventListener = (t, f) => { (H_WL[t] = H_WL[t] || []).push(f); };
globalThis.dispatchEvent = e => { (H_WL[e.type] || []).forEach(f => f(e)); return true; };
function dfire(t, e){ (H_DL[t] || []).forEach(f => f(e || {type: t})); }
function wfire(t, e){ (H_WL[t] || []).forEach(f => f(e || {type: t})); }
async function hideFor(ms){ DOC.hidden = true; dfire('visibilitychange'); await advance(ms); DOC.hidden = false; dfire('visibilitychange'); await advance(1); }
const R = {reloads: 0, toasts: [], loading: 0, reconnect: 0};
globalThis.location = {pathname: '/', search: '?book=paper', reload(){ R.reloads++; }};
const H_SS = {};
globalThis.sessionStorage = {getItem: k => (k in H_SS ? H_SS[k] : null), setItem: (k, v) => { H_SS[k] = String(v); }};
Object.defineProperty(globalThis, 'navigator', {value: {onLine: true}, configurable: true, writable: true});
addEventListener('qb-reconnect', () => { R.reconnect++; });
const $ = s => document.querySelector(s);
function loading(on){ R.loading = on ? 1 : 0; }
function toast(t, bad){ R.toasts.push(String(t)); }
function banner(){ const e = DOC.els.conn; return e && !e.hidden ? e._t.textContent : ''; }
"""


def node() -> str:
    n = shutil.which("node")
    if not n:
        pytest.skip("没有 node")
    return n


def _run(tmp_path, name: str, src: str) -> dict:
    f = tmp_path / name
    f.write_text(src, encoding="utf-8")
    r = subprocess.run([node(), str(f)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout[-500:], r.stderr[-1500:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def run_conn(tmp_path, scenario: str, cfg: dict | None = None, gen_ago_min: float | None = None, cached: bool = False,
             setup: str = "") -> dict:
    """conn.js 在假环境里跑：cfg = 页面的 CFG（gen_ago_min：页面是几分钟前生成的）；cached = service worker 给的存着的页面；
    setup = conn.js 载入之前要做的（例：NET.mode='down'）；scenario = async 的步骤，最后 `return {...}` → 这里拿到的 dict。"""
    cfg = dict(cfg or {"book": "paper", "v": "V1", "st": {"sig": "S0", "busy": 0, "pending": 0}})
    pre = (CONN_PRELUDE + f"\nconst CFG = {json.dumps(cfg, ensure_ascii=False)};\n"
           + (f"CFG.gen = H_NOW - {float(gen_ago_min)} * 60000;\n" if gen_ago_min is not None else "")
           + f"DOC.cached = {'true' if cached else 'false'};\n" + setup + "\n")
    body = panel.js_plain("net") + "\n" + panel.js_plain("conn")
    return _run(tmp_path, "conn_case.js", pre + body + "\n(async () => {\n" + scenario
                + "\n})().then(o => console.log(JSON.stringify(o)), e => { console.error(e && e.stack || e); process.exit(1); });\n")


SW_PRELUDE = r"""
const ORIGIN = 'https://node.example.ts.net';
const SL = {};
globalThis.self = globalThis;
self.location = new URL(ORIGIN + '/sw.js');
self.addEventListener = (t, f) => { SL[t] = f; };
self.skipWaiting = () => Promise.resolve();
self.clients = {claim: () => Promise.resolve(), matchAll: async () => []};
self.registration = {showNotification: async () => {}};
const STORE = {};
const key = k => (typeof k === 'string' ? k : k.url);
globalThis.caches = {
  open: async n => { const m = STORE[n] = STORE[n] || new Map(); return {
    put: async (k, r) => { m.set(key(k), r); },
    match: async (k) => { const r = m.get(key(k)); return r ? r.clone() : undefined; },
    keys: async () => [...m.keys()].map(u => ({url: u})),
    delete: async k => m.delete(key(k)) }; },
  keys: async () => Object.keys(STORE),
  delete: async n => { const had = n in STORE; delete STORE[n]; return had; },
};
const NET = {routes: {}, calls: []};                       // url（不含 origin）→ () => Response | 'hang' | 'down'
globalThis.fetch = (u, init) => new Promise((res, rej) => {
  const url = key(u).replace(ORIGIN, ''); NET.calls.push(url);
  const f = NET.routes[url.split('#')[0]];
  const r = f ? f() : 'down';
  if (r === 'down') return rej(new TypeError('Failed to fetch'));
  if (r === 'hang') { if (init && init.signal) init.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), {name: 'AbortError'}))); return; }
  if (r && r.then) return r.then(res, rej);
  res(r);
});
function mkpage(body, kind, status){ return new Response(body, {status: status || 200, headers: {'Content-Type': 'text/html; charset=utf-8', 'X-Qbreak-Page': kind || 'main'}}); }
function later(ms, r){ return new Promise(res => setTimeout(() => res(r), ms)); }
async function go(path, mode){
  const waits = []; let rp = null; const t0 = Date.now();
  const ev = {request: {method: 'GET', mode: mode || 'navigate', url: ORIGIN + path}, respondWith(p){ rp = Promise.resolve(p); }, waitUntil(p){ waits.push(p); }};
  SL.fetch(ev);
  if (!rp) return {passed: true};
  const r = await rp; const ms = Date.now() - t0;                  // 页面拿到回应用了多久
  const text = r.type === 'error' ? null : await r.text();
  for (let n = 0; n < waits.length;) {                            // 后台的（晚到的网络、存缓存；途中又加的）也做完
    const batch = waits.slice(n); n = waits.length; await Promise.all(batch.map(p => p.catch(() => null)));
  }
  return {status: r.status, type: r.type, text, cache: r.headers.get('X-Qbreak-Cache'), ms};
}
async function cached(){ const m = STORE['qbreak-v4'] || new Map(); return [...m.keys()].map(u => u.replace(ORIGIN, '')); }
"""


def run_sw(tmp_path, scenario: str, ms: dict | None = None) -> dict:
    """service worker 在假环境里跑：超时换短（毫秒）；scenario = async 的步骤，最后 `return {...}`。"""
    ms = {"NAV_MS": 80, "NET_MS": 400, "STATIC_MS": 80, "API_MS": 80, **(ms or {})}
    sw = panel.SW_JS
    head = "const C='qbreak-v4', NAV_MS=6000, NET_MS=25000, STATIC_MS=8000, API_MS=12000, API_MAX=40;"
    assert head in sw
    sw = sw.replace(head, f"const C='qbreak-v4', NAV_MS={ms['NAV_MS']}, NET_MS={ms['NET_MS']}, STATIC_MS={ms['STATIC_MS']}, "
                          f"API_MS={ms['API_MS']}, API_MAX=3;")
    return _run(tmp_path, "sw_case.js", SW_PRELUDE + sw + "\n(async () => {\n" + scenario
                + "\n})().then(o => console.log(JSON.stringify(o)), e => { console.error(e && e.stack || e); process.exit(1); });\n")
