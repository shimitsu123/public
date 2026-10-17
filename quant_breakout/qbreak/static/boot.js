// qbreak 操作面板：boot.js（普通脚本，在 main.js 之前跑；qbreak/panel.py 直接写进页面里（内联 + CSP 的 sha256）；不要用构建工具）
// 2026-10-15 用户「qbreak网页app经常卡住 永久解决这个问题」：页面的脚本（ES 模块）有一个没载入成（网络断在半路 / 面板正在重启 /
// 新旧版本对不上 → 404）整页就没反应，以前只能划掉 App 重开。这里：模块 / 样式没载入成 → 先逐个确认页面要的脚本与样式现在都拿得到
// （拿不到 → 页面底上倒数重试，不来回刷新）再自动重新载入；8 秒还没载入完 → 页面底上「页面还在载入」，15 秒还没有 → 同样确认后重新载入。
// 自动重新载入 1 分钟最多 2 次（确认过都拿得到的：4 次），到了就等这 1 分钟过去再试（不会刷新个没完，也不会一直停着）。
// 2026-10-15 复核：① 以前它自己也是 /static/boot.js?v= —— 页面是旧进程给的、脚本向新进程要（平滑重启正好在中间）/ 网络在页面到了之后断了 →
// 它自己也没载入，页面照旧卡死 → 现在写进页面里（页面到了它就在）；② 带版本的脚本 404 = 页面是旧版本（面板换了新代码）→ 以前只倒数重试、
// 一直不重新载入 → 现在直接重新载入拿新页面（告诉 service worker 这次多等网络，不再换成存着的旧页面）；③ 样式（panel.css）没载入成也接手。
(function(){
  'use strict';
  var T0 = Date.now(), done = false, timer = 0, tries = 0, kind = '', BACKOFF = [3, 5, 10, 20, 30];
  var book = '';
  try{ book = (JSON.parse(document.getElementById('qb-cfg').textContent) || {}).book || ''; }catch(e){}
  function ready(){ return !!window.__qbReady; }
  function beacon(e, d){
    try{ fetch('/api/clientlog?e=' + encodeURIComponent(e) + '&d=' + encodeURIComponent(String(d || '').slice(0, 180)),
               {credentials: 'same-origin', cache: 'no-store', keepalive: true}).catch(function(){}); }catch(x){}
  }
  function bar(text, btn){
    var el = document.getElementById('bootbar');
    if(!el){
      el = document.createElement('div'); el.id = 'bootbar'; el.setAttribute('role', 'alert');
      el.style.cssText = 'position:fixed;left:12px;right:12px;bottom:calc(env(safe-area-inset-bottom) + 76px);z-index:40;max-width:696px;margin:0 auto;'
        + 'display:flex;gap:10px;align-items:center;padding:12px 14px;border-radius:12px;background:#ff9f0a;color:#111;'
        + 'font:15px/1.45 -apple-system,BlinkMacSystemFont,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.25)';
      var t = document.createElement('span'); t.style.flex = '1'; el.appendChild(t);
      var b = document.createElement('button'); b.type = 'button';
      b.style.cssText = 'flex:none;padding:10px 14px;border:0;border-radius:10px;background:#111;color:#fff;font:600 15px -apple-system,sans-serif';
      b.addEventListener('click', function(){ reload('button'); });
      el.appendChild(b);
      (document.body || document.documentElement).appendChild(el);
    }
    el.firstChild.textContent = text; el.lastChild.textContent = btn || '重新载入'; el.hidden = false;
  }
  function hide(){ var el = document.getElementById('bootbar'); if(el) el.hidden = true; }
  function reload(why){
    if(why !== 'button'){                                                 // 自动的：1 分钟内最多 2 次（确认过脚本都拿得到的 'fixed'：4 次）
      var a = [], now = Date.now(), lim = (why === 'fixed' || why === 'ver') ? 4 : 2;
      try{ a = JSON.parse(sessionStorage.getItem('qb-bootreload') || '[]').filter(function(t){ return now - t < 60000; }); }catch(e){}
      if(a.length >= lim){                                                // 到了：先停，过了这 1 分钟再自动试（'ver' 也是 4 次：Mac 慢、service worker 一直给存着的旧页面时）
        bar('页面还是没载入完（已自动重新载入 ' + a.length + ' 次）：稍后自动再试，或点右边', '重新载入');
        clearTimeout(timer); timer = setTimeout(recover, Math.max(1000, a[0] + 60000 - now + 500)); return;
      }
      a.push(now); try{ sessionStorage.setItem('qb-bootreload', JSON.stringify(a)); }catch(e){}
    }
    patient(function(){ location.reload(); });
  }
  function patient(go){                                                   // 告诉 service worker：这次导航多等一会儿网络（不马上换成存着的旧页面；conn.js 同一个）
    var sw = navigator.serviceWorker && navigator.serviceWorker.controller, t = 0, ok = false;
    function once(){ if(!ok){ ok = true; clearTimeout(t); go(); } }
    if(!sw || typeof MessageChannel === 'undefined') return once();
    try{ var ch = new MessageChannel(); ch.port1.onmessage = once; t = setTimeout(once, 300); sw.postMessage({qb: 'patient'}, [ch.port2]); }
    catch(e){ once(); }
  }
  function urls(){                                                        // 页面要的脚本与样式（main.js、modulepreload 的模块、panel.css）
    var n = document.querySelectorAll("script[type=module][src], link[rel=modulepreload], link[rel=stylesheet][href^='/static/']"), a = [];
    for(var i = 0; i < n.length; i++) a.push(n[i].src || n[i].href);
    return a.length ? a : ['/api/status?book=' + encodeURIComponent(book)];
  }
  function probe(){                                                       // → '' = 都拿得到（或要登录）/ 'ver' = 页面是旧版本 / 'net' = 连不上 Mac / 'slow' = 6 秒没回 / 其他 = 哪个拿不到
    var ac = ('AbortController' in window) ? new AbortController() : null, to = setTimeout(function(){ if(ac) ac.abort(); }, 6000);
    return Promise.all(urls().map(function(u){
      return fetch(u, {credentials: 'same-origin', cache: 'no-store', signal: ac ? ac.signal : undefined}).then(function(r){
        if(r.status === 404 && /\/static\/[^?]*\?(.*&)?v=/.test(String(u))) throw new Error('VER');   // 带版本的 404 = 面板换了新代码、这页是旧的
        if(!(r.ok || r.status === 401 || r.status === 403)) throw new Error(String(u).replace(/^.*\/(static\/)?/, '').replace(/\?.*$/, '') + ' 拿不到（HTTP ' + r.status + '）');
      });
    })).then(function(){ clearTimeout(to); return ''; }, function(e){
      clearTimeout(to); if(ac) ac.abort();
      var m = String(e && e.message);
      return m === 'VER' ? 'ver' : /拿不到/.test(m) ? m : (e && e.name === 'AbortError') ? 'slow' : 'net';
    });
  }
  function recover(){                                                     // 确认都拿得到（或要登录）→ 重新载入；拿不到 → 倒数重试
    clearTimeout(timer);
    if(ready() && kind !== 'css'){ hide(); return; }                      // 样式没载入成：脚本跑起来了也要重新载入（不然整页没有样式）
    probe().then(function(why){
      if(ready() && kind !== 'css'){ hide(); return; }
      if(!why || why === 'ver') return reload(why === 'ver' ? 'ver' : (kind === 'script' || kind === 'css') ? 'fixed' : 'auto');   // 都拿得到 / 页面是旧版本 → 重新载入
      var s = BACKOFF[Math.min(tries++, BACKOFF.length - 1)];
      bar(why === 'net' ? '页面没载入完，也连不上 Mac（' + s + ' 秒后重试）' : why === 'slow' ? '页面没载入完：Mac 回应太慢（' + s + ' 秒后重试）'
          : '页面没载入完：' + why + '（' + s + ' 秒后重试）', '重新载入');
      timer = setTimeout(recover, s * 1000);
    });
  }
  function fail(k, detail){
    if(done || ready()) return;
    done = true; kind = k;
    beacon('boot-' + k, detail + '（' + Math.round((Date.now() - T0) / 1000) + ' 秒）');
    bar('页面没载入完（' + (k === 'timeout' ? '太慢' : k === 'css' ? '样式没载入成' : '脚本没载入成') + '）：正在重新连接…', '重新载入');
    recover();
  }
  window.addEventListener('error', function(e){                           // <script type=module> / modulepreload / 样式没载入成（网络 / 5xx / 404）；模块的 import 对不上
    var t = e && e.target;
    if(t && (t.tagName === 'SCRIPT' || (t.tagName === 'LINK' && /modulepreload|stylesheet/.test(t.rel || ''))))
      fail('script', String(t.src || t.href || '').replace(/^.*\/static\//, ''));
    else if(e && e.message && !ready()) fail('module', e.message);      // 模块跑到一半出错（import 的名字对不上也是这个）
  }, true);
  (function(){                                                            // 样式：页头的 <link> 比这里先载入完（脚本要等它）；没载入成（sheet 是 null）→ 同样接手
    var n = document.querySelectorAll("link[rel=stylesheet][href^='/static/']");
    for(var i = 0; i < n.length; i++){ try{ if(!n[i].sheet){ fail('css', String(n[i].href).replace(/^.*\/static\//, '')); return; } }catch(e){} }
  })();
  setTimeout(function(){ if(!ready()) bar('页面还在载入（网络慢 / Mac 刚醒）…', '重新载入'); }, 8000);
  setTimeout(function(){ if(!ready()) fail('timeout', 'main.js'); }, 15000);
  window.__qbBootOk = function(){ if(kind === 'css') return; done = true; clearTimeout(timer); hide(); };   // main.js 跑完了（样式没载入成的照样接着重新载入）
})();
