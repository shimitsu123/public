// qbreak 操作面板：conn.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/conn.js 提供；不要用构建工具）
// 连接检查 + 自动重连 + 安全的自动刷新（2026-10-15 用户「qbreak网页app经常卡住 永久解决这个问题」）。以前：切回来 / 写完之后不管连不连得上
// 都直接 location.reload() → Mac 睡着 / 面板重启 / Tailscale 没连上时停在白屏或「刷新中…」，主屏幕 App 没有刷新键只能划掉重开；
// 状态变了的刷新不管对话框开没开。现在：
//   · 只有一个定时器（setTimeout 链，不会叠出好几个）：空闲每 30 秒、有在处理的指令每 10 秒问一次 /api/status（5 秒没回 = 连不上）；
//     页面看不见时不问，切回来 / 从后台恢复（pageshow）/ 联网 / 窗口拿到焦点时马上问；
//   · 连不上 → 页面顶上「连不上 Mac（N 秒后重试）」+「重试」，3 / 5 / 10 / 20 / 30 秒退避，连上了自动消失；
//   · 刷新之前先确认连得上（写完之后、点「刷新」、切回来发现页面旧了 / 面板换了新代码 / 在处理的指令状态变了）；
//   · 对话框开着 / 正在输入 → 不刷新，顶上提示「关掉对话框后自动刷新」，关掉后再刷新；1 分钟内最多自动刷新 3 次（不会刷新个没完）。
// 2026-10-15 复核：连接条放在页头里（以前固定在最上面、盖住「刷新」和时刻）、对话框开着时放进对话框（以前在遮罩底下点不到「现在刷新」）；
//   /api/status 回 500 写「Mac 上的面板出错了」（不是「Mac 睡着」）；K 线等请求 401（这台设备没被认出来）也经这里刷新（对话框开着 / 正在输入时等关掉）。
import { $, CFG, loading, toast } from './core.js';
import { req } from './net.js';

const PING_MS = 5000, IDLE_MS = 30000, BUSY_MS = 10000, BACKOFF = [3, 5, 10, 20, 30], STALE_MS = 10 * 60000;
const st0 = CFG.st || {};
const S = {up: true, fails: 0, timer: 0, tick: 0, next: 0, last: 0, flight: null, want: null, downAt: 0, downWhy: '', downKind: '',
           sig: st0.sig || null, busy: +(st0.busy !== undefined ? st0.busy : st0.pending) || 0, hiddenAt: 0,
           cached: !!document.querySelector('meta[name="qb-cache"]')};
function busyNow(){ return S.busy > 0; }
function age(){ const g = +CFG.gen; return g > 0 ? Date.now() - g : 0; }
function mins(ms){ const m = ms / 60000; return m < 90 ? Math.max(1, Math.round(m)) + ' 分钟' : Math.round(m / 60) + ' 小时'; }

export function beacon(e, d){                                             // 页面报告 → 面板日志（只记种类与简短说明；连不上时发不出去就算了）
  try{ fetch('/api/clientlog?e=' + encodeURIComponent(e) + '&d=' + encodeURIComponent(String(d || '').slice(0, 180)),
             {credentials: 'same-origin', cache: 'no-store', keepalive: true}).catch(()=>{}); }catch(x){}
}

function ping(){                                                          // → {up, j?, auth?, why?}；同时只问一次
  if(S.flight) return S.flight;
  S.flight = req('/api/status?book=' + encodeURIComponent(CFG.book || ''), {credentials: 'same-origin', cache: 'no-store', tmo: PING_MS, quiet: true})
    .then(x=>{
      if(x.r.status === 401 || x.r.status === 403) return {up: true, auth: true};
      if(x.r.ok && x.j && x.j.sig) return {up: true, j: x.j};
      return {up: false, why: 'HTTP ' + x.r.status, kind: x.r.status === 500 ? 'panel' : 'http'};   // 500 = 面板自己出错（502 / 503 / 504 = 接不上面板）
    }, e=>(e && e.name === 'Timeout' ? {up: false, why: '5 秒没有回应', kind: 'timeout'} : {up: false, why: '连不上', kind: 'net'}))
    .finally(()=>{ S.flight = null; });
  return S.flight;
}

function bar(){                                                           // 页面顶上的连接条（连不上 / 等对话框关掉）
  let el = $('#conn');
  if(!el){
    el = document.createElement('div'); el.id = 'conn'; el.className = 'conn'; el.setAttribute('role', 'status'); el.hidden = true;
    el.innerHTML = "<span class='conn-t'></span><button type='button' class='conn-b'>重试</button>";
    el.querySelector('button').addEventListener('click', ev=>{ ev.preventDefault(); ev.stopPropagation(); onButton(); });
    document.body.appendChild(el);
  }
  return el;
}
function place(el){                                                       // 放哪：对话框开着 → 对话框里最上面（遮罩上面、点得到）；否则页头里（不盖住「刷新」/ 时刻）
  const d = document.querySelector('dialog[open]'), top = document.querySelector('.top');
  const host = (d && d.insertBefore) ? d : (top && top.insertBefore) ? top : document.body;
  if(el.parentNode === host) return;
  if(host === document.body) host.appendChild(el); else host.insertBefore(el, host.firstChild);
}
document.addEventListener('close', e=>{ const el = $('#conn'); if(el && e.target && e.target.contains && e.target.contains(el)) place(el); }, true);   // 对话框关了：回到页头
function show(text, btn, warn){
  const el = bar(); place(el); el.querySelector('.conn-t').textContent = text;
  const b = el.querySelector('button'); b.textContent = btn || '重试'; b.hidden = btn === false;
  el.classList.toggle('warn', !!warn); el.hidden = false;
}
function hide(){ const el = $('#conn'); if(el) el.hidden = true; }
function onButton(){
  if(!S.up){ show('正在连接 Mac…', false); check('button'); return; }
  go('button');                                                           // 「现在刷新」：用户自己点的，不管对话框
}
function paint(){                                                         // 连不上：每秒更新倒数
  clearTimeout(S.tick);
  if(S.up || document.hidden) return;
  const s = Math.max(0, Math.ceil((S.next - Date.now()) / 1000));
  const why = navigator.onLine === false ? '这台设备没有网络' : 'Mac 睡着 / 关机 / 面板正在重启，或手机的 Tailscale 没连上';
  if(S.downKind === 'panel') show(s > 0 ? 'Mac 上的面板出错了（' + S.lastWhy + '，' + s + ' 秒后重试）：一直这样 → 在 Mac 的 Claude 对话里说一声' : '正在连接 Mac…',
                                  s > 0 ? '重试' : false, true);
  else show(s > 0 ? '连不上 Mac（' + s + ' 秒后重试）：' + why : '正在连接 Mac…', s > 0 ? '重试' : false, true);
  if(s > 0) S.tick = setTimeout(paint, 1000);
}

function schedule(){
  clearTimeout(S.timer); S.timer = 0;
  if(document.hidden) return;                                             // 看不见的时候不问（切回来马上问）
  const ms = !S.up ? BACKOFF[Math.min(S.fails - 1, BACKOFF.length - 1)] * 1000 : busyNow() ? BUSY_MS : IDLE_MS;
  S.next = Date.now() + ms; S.timer = setTimeout(()=>check('timer'), ms);
  if(!S.up) paint();
}

export async function check(why){
  clearTimeout(S.timer); S.timer = 0;
  if(document.hidden && why !== 'reload') return null;
  S.last = Date.now();
  let x = await ping();
  if(!x.up && x.kind === 'net' && S.up && (why === 'resume' || why === 'online')){   // iPhone 从后台回来的第一个请求常常马上失败：1 秒后再问一次再算连不上
    await new Promise(r=>setTimeout(r, 1000)); x = await ping();
  }
  if(x.up) onUp(x, why); else onDown(x.why, x.kind);
  schedule();
  return x;
}

function onDown(why, kind){
  if(S.up){ S.downAt = Date.now(); S.downWhy = why; }
  S.lastWhy = why; S.downKind = kind || '';
  S.up = false; S.fails++;
  loading(false);                                                         // 刷新到一半连不上：进度条与按钮放开（不卡在「刷新中…」）
  document.querySelectorAll('[data-act=reload].loading').forEach(b=>{ b.classList.remove('loading'); b.disabled = false; b.setAttribute('aria-busy', 'false');
    if(b.dataset.label0) b.textContent = b.dataset.label0; });
}

function onUp(x, why){
  const back = !S.up;
  S.up = true; S.fails = 0; clearTimeout(S.tick);
  if(back){ beacon('reconnect', S.downWhy + '，' + Math.round((Date.now() - S.downAt) / 1000) + ' 秒后连上'); S.downAt = 0;
            try{ window.dispatchEvent(new Event('qb-reconnect')); }catch(e){} }   // quotes.js 等：马上再取
  if(x.auth){ want('auth', why === 'reload' || why === 'button'); return; }   // 这台设备没被认出来：重新载入（会到登录 / 配对页；对话框开着 → 等关掉）
  const j = x.j, was = S.busy;
  S.busy = +(j.busy !== undefined ? j.busy : j.pending) || 0;
  let r = S.want;
  if(!r && S.cached) r = 'cache';                                         // 打开的是存着的旧页面 → 连上了换成新的
  if(!r && j.v && CFG.v && j.v !== CFG.v) r = 'ver';                      // 面板换了新代码（页面的脚本是旧的）
  if(!r && S.sig && j.sig !== S.sig){
    if(was > 0 || S.busy > 0) r = 'sig';                                  // 在处理的指令状态变了（以前每 10 秒问一次的那个）
    else S.dirty = true;                                                  // 别的变化：下次切回来时再刷新（不打断正在看的页面）
  }
  if(!r && (why === 'resume' || why === 'online') && (age() > STALE_MS || S.dirty)) r = 'old';
  if(r) want(r, why === 'reload' || why === 'button'); else if(!S.want) hide();
}

function editing(){ const a = document.activeElement; return !!a && (/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) || a.isContentEditable); }
function safe(){ return !document.hidden && !document.querySelector('dialog[open]') && !editing(); }
const WHY = {ver: '面板更新了：', user: '连上了：', cache: '连上了：', old: '页面放久了：', auth: '这台设备要重新登录：', sig: '状态更新了：'};
function want(r, now){                                                    // 要刷新：安全时马上刷新；对话框开着 / 正在输入 → 等关掉
  S.want = r;                                                             // now：用户刚点的「刷新」/ 刚写完（连不上时等着的，连上后照样等对话框关掉）
  if(now || safe()){ go(r); return; }
  show((WHY[r] || '状态更新了：') + (document.querySelector('dialog[open]') ? '关掉对话框后自动刷新' : '输入完后自动刷新'), '现在刷新');
  clearTimeout(S.pend); S.pend = setTimeout(retryWant, 2000);             // 没有 close 事件的旧浏览器也会再看
}
function retryWant(){ clearTimeout(S.pend); if(S.want && S.up){ if(safe()) go(S.want); else S.pend = setTimeout(retryWant, 2000); } }
document.addEventListener('close', ()=>setTimeout(retryWant, 50), true);  // 对话框关掉（close 不冒泡，用捕获）
document.addEventListener('focusout', ()=>setTimeout(retryWant, 300), true);

const RL_KEY = 'qb-autoreload', PAGE_MS = 20000;
function recent(now){ try{ return JSON.parse(sessionStorage.getItem(RL_KEY) || '[]').filter(t=>now - t < 60000); }catch(e){ return []; } }
function pageOk(){                                                        // 存着的旧页面：刷新之前先确认页面本身打得开 → '' / 打不开的原因
  if(!S.cached) return Promise.resolve('');                               // （/api/status 通、页面却 5xx / 太慢时，刷新只会又拿到存着的 → 来回刷新）
  return req(location.pathname + location.search, {credentials: 'same-origin', cache: 'no-store', tmo: PAGE_MS, quiet: true})   // 不是导航：不经 service worker
    .then(x=>(x.r.status >= 500 ? 'HTTP ' + x.r.status : ''), e=>(e && e.name === 'Timeout' ? PAGE_MS / 1000 + ' 秒没有回应' : '连不上'));
}
function patient(){                                                       // 告诉 service worker：这次导航多等一会儿（刚确认连得上；页面生成得慢也等新的，不马上换成存着的）
  const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
  if(!sw || typeof MessageChannel === 'undefined') return Promise.resolve();
  return new Promise(res=>{
    const ch = new MessageChannel(), t = setTimeout(res, 300);
    ch.port1.onmessage = ()=>{ clearTimeout(t); res(); };
    try{ sw.postMessage({qb: 'patient'}, [ch.port2]); }catch(e){ clearTimeout(t); res(); }
  });
}
function go(r){                                                           // 真的重新载入（自动的：1 分钟内最多 3 次；同时只走一次）
  if(S.going) return;
  const auto = r !== 'user' && r !== 'button';
  if(auto){
    const a = recent(Date.now());
    if(a.length >= 3){                                                    // 1 分钟内已经 3 次：先停，等到能再刷新时再试（不会刷新个没完，也不会一直停着）
      S.want = null; show('自动刷新太频繁，先停一下（这页可能不是最新的）', '现在刷新', true); beacon('reload-loop', r);
      clearTimeout(S.pend); S.pend = setTimeout(()=>{ if(!S.want) want(r); }, Math.max(1000, a[0] + 60000 - Date.now() + 500)); return;
    }
  }
  S.going = true; S.want = null; clearTimeout(S.pend); hide(); loading(true);
  pageOk().then(bad=>{
    if(bad){                                                              // 页面打不开：留在存着的页面上，倒数再试（不刷新）
      S.going = false; loading(false); S.pageFails = (S.pageFails || 0) + 1;
      const s = BACKOFF[Math.min(S.pageFails - 1, BACKOFF.length - 1)];
      show('连得上 Mac，但页面还打不开（' + bad + '，面板可能正在启动）：' + s + ' 秒后再试', '重试', true);
      S.pend = setTimeout(()=>{ if(!S.going) want(S.want || r); }, s * 1000); return;     // 这期间又要刷新的（按钮 / 新版本）也在这时一起
    }
    if(auto && r !== 'auth' && !safe()){ S.going = false; loading(false); want(r); return; }   // 确认的时候开了对话框 / 开始输入 → 等关掉
    S.pageFails = 0;
    if(auto){ const a = recent(Date.now()); a.push(Date.now()); try{ sessionStorage.setItem(RL_KEY, JSON.stringify(a)); }catch(e){} }
    return patient().then(()=>{ location.reload(); setTimeout(()=>{ S.going = false; loading(false); }, 40000); });   // 40 秒后还在这页 = 没换成（不一直挡着）
  });
}

window.qbReload = function(r){                                            // core.js：写完之后 / 点「刷新」→ 先确认连得上再刷新
  S.want = r || 'user';
  return check('reload').then(x=>{ if(x && !x.up) toast('连不上 Mac：连上之后自动刷新（页面顶上可以点「重试」）', true); });
};
window.qbNetFail = function(url, kind){                                   // net.js：别的请求超时 / 连不上 / 拿到存着的 → 马上查一次（3 秒内只查一次）
  if(S.up && Date.now() - S.last > 3000 && !S.flight) check('fail');
};
window.qbNetOk = function(){ if(!S.up && !S.flight) check('ok'); };
window.qbAuth = function(){ if(S.want !== 'auth' && !S.going) want('auth'); };   // kline.js 等：请求 401 → 刷新（几张图一起 401 也只一次；对话框开着 / 正在输入 → 等关掉）

function resume(){                                                        // 切回来 / 从后台恢复 / 联网 / 拿到焦点（3 秒内只查一次）
  if(document.hidden) return;
  if(Date.now() - S.last < 3000 && S.up){ if(!S.timer) schedule(); return; }   // 刚问过：不再问，但定时器要接上（切走时停了；以前快速切走切回后就不再问）
  check('resume');
}
document.addEventListener('visibilitychange', ()=>{
  if(document.hidden){ S.hiddenAt = Date.now(); clearTimeout(S.timer); S.timer = 0; clearTimeout(S.tick); return; }
  resume();
});
window.addEventListener('pageshow', e=>{ if(e.persisted) resume(); });
document.addEventListener('resume', resume);                              // 冻结的页面恢复（Page Lifecycle：后台久了的标签页）
window.addEventListener('focus', resume);
window.addEventListener('online', ()=>{ S.last = 0; check('online'); });
window.addEventListener('offline', ()=>{ if(S.up) onDown('没有网络'); schedule(); });

(function(){                                                              // 打开的是存着的旧页面（service worker 给的）/ 页面很旧 → 顶上写明
  const el = $('#stale'), a = age();
  if(el && (S.cached || a > 3 * 60000)){
    el.textContent = '★ 这是 ' + mins(a) + '前的页面（连不上 Mac：Mac 睡着 / 关机 / Tailscale 没连上）。按钮现在点了也送不到 —— 连上之后会自动刷新。';
    el.hidden = false;
  }
  if(S.cached) beacon('cached-page', mins(a) + '前的页面');
  if(S.cached) check('load'); else schedule();
})();
