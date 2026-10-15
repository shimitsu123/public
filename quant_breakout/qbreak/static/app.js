// qbreak 操作面板：app.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/app.js 提供；不要用构建工具）
import { $, api, toast } from './core.js';
import { beacon } from './conn.js';
import { req } from './net.js';
// 切回来时页面旧了就刷新、在处理的指令状态变了就刷新、页面顶上「这是 N 分钟前的页面」：2026-10-15 起都在 conn.js（先确认连得上 Mac 再刷新、
// 对话框开着不刷新；以前这里直接 location.reload()，连不上时停在「刷新中…」）。
(function(){                                                              // 网页 App：service worker（连不上时看上次的页面 + 推送）
  if('serviceWorker' in navigator){                                      // updateViaCache: 'none' → sw.js 本身不走 HTTP 缓存（面板换了新代码马上用新的）
    navigator.serviceWorker.register('/sw.js',{scope:'/', updateViaCache:'none'}).catch(err=>beacon('sw-register', String(err)));
  }
})();
function b64key(s){ s=s.replace(/-/g,'+').replace(/_/g,'/'); s+='='.repeat((4-s.length%4)%4); const r=atob(s), o=new Uint8Array(r.length); for(let i=0;i<r.length;i++) o[i]=r.charCodeAt(i); return o; }
function standalone(){ return (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone===true; }
async function pushReg(){                                                // service worker 3 秒还没准备好 → 当作没有（以前一直等 → 推送那一行与按钮没反应）
  if(!('serviceWorker' in navigator) || !('PushManager' in window)) return null;
  return Promise.race([navigator.serviceWorker.ready, new Promise(res=>setTimeout(()=>res(null), 3000))]);
}
async function pushState(){
  const el=$('#push-st'); if(!el) return;
  const reg=await pushReg().catch(()=>null);
  if(!reg){ el.textContent=(/iPhone|iPad/.test(navigator.userAgent) && !standalone()) ? '要先在 Safari「共享 → 添加到主屏幕」，再从主屏幕的 qbreak 图标打开，才能打开推送（iOS 16.4 以上）' : '这个浏览器不支持推送'; return; }
  const s=await reg.pushManager.getSubscription().catch(()=>null);
  el.textContent = s ? '这台设备：推送已打开 ✓' : ('这台设备：推送没打开'+(typeof Notification!=='undefined' && Notification.permission==='denied' ? '（通知被拒绝了：在 iPhone 设置 → 通知 → qbreak 里打开）' : ''));
}
document.addEventListener('DOMContentLoaded', ()=>{ pushState(); });
document.addEventListener('click', async e=>{
  const b=e.target.closest('[data-act^="push-"]'); if(!b) return;
  e.stopPropagation();
  const a=b.dataset.act, reg=await pushReg().catch(()=>null);
  if(!reg){ toast('这里打不开推送：iPhone 要从主屏幕的 qbreak 图标打开（Safari 的标签页里不行）', true); return; }
  if(a==='push-on'){
    const perm=await Notification.requestPermission();
    if(perm!=='granted'){ toast('没有允许通知：iPhone 设置 → 通知 → qbreak 里打开', true); return; }
    let key=null; try{ const x=await req('/api/push/key',{credentials:'same-origin',cache:'no-store'}); key=x.j && x.j.key; }catch(err){}
    if(!key){ toast('取不到推送的公钥（连不上 Mac？）', true); return; }
    let s=null; try{ s=await reg.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:b64key(key)}); }catch(err){ toast('打开推送失败：'+err, true); return; }
    const j=await api('/api/push/subscribe',{sub:s.toJSON()}); if(j) toast(j.msg||'已打开');
  }else{
    const s=await reg.pushManager.getSubscription();
    if(!s){ toast('这台设备还没打开推送', true); return; }
    if(a==='push-test'){ const j=await api('/api/push/test',{endpoint:s.endpoint}); if(j) toast(j.msg); }
    else { await s.unsubscribe().catch(()=>{}); const j=await api('/api/push/unsubscribe',{endpoint:s.endpoint}); if(j) toast(j.msg); }
  }
  pushState();
}, true);
const TABK=['home','hold','trade','pick','news','more'];                  // 标签页（总览 / 持仓 / 交易 / 选股 / 消息 / 更多）
function showTab(k, keep){
  if(TABK.indexOf(k)<0) k='home';
  document.querySelectorAll('.pane').forEach(p=>p.classList.toggle('on', p.dataset.tab===k));
  document.querySelectorAll('[data-tabgo]').forEach(b=>{ const on=b.dataset.tabgo===k; b.classList.toggle('on', on); b.setAttribute('aria-selected', on?'true':'false'); });
  try{ sessionStorage.setItem('qb-tab', k); }catch(e){}
  if(location.hash!=='#tab='+k){ try{ history.replaceState(null, '', location.pathname+location.search+'#tab='+k); }catch(e){} }
  if(!keep) window.scrollTo(0,0);
}
document.addEventListener('click', e=>{ const b=e.target.closest('[data-tabgo]'); if(!b) return; e.preventDefault(); showTab(b.dataset.tabgo); }, true);
(function(){
  const q=new URLSearchParams(location.search), h=location.hash.replace(/^#/,'');
  let k=q.get('tab') || (h.indexOf('tab=')===0 ? h.slice(4) : '');
  let target=null;
  if(!k && h){ target=document.getElementById(h); const p=target && target.closest('.pane'); if(p) k=p.dataset.tab; }   // 旧的锚点（#holdings 等）
  if(!k){ try{ k=sessionStorage.getItem('qb-tab')||''; }catch(e){} }
  showTab(k||'home', true);
  const seg=q.get('seg') || (q.get('l') ? 'log' : '');                   // 消息：经济威胁（默认）/ 通知记录
  if(seg) showMseg(seg);
  const l=q.get('l');                                                     // 推送点开：?tab=news&seg=log&l=<id> → 通知记录里那一条
  if(l){ const d=document.getElementById('l-'+l); if(d){ d.open=true; target=d; d.classList.add('hl'); } }
  const n=q.get('n');                                                     // 推送点开：?tab=news&n=<id> → 展开那一条
  if(n){ const d=document.getElementById('n-'+n); if(d){ d.open=true; const pd=d.parentElement && d.parentElement.closest('details'); if(pd) pd.open=true; target=d; d.classList.add('hl'); } }
  if(target) setTimeout(()=>{ const top=document.querySelector('.top'); window.scrollTo(0, target.getBoundingClientRect().top+window.scrollY-((top&&top.offsetHeight)||0)-8); }, 50);
})();
document.addEventListener('click', e=>{                                   // 选股：分段（出信号 / 快要出 / 观察中）与「再显示」
  const s=e.target.closest('[data-sgg]');
  if(s){ e.preventDefault(); document.querySelectorAll('[data-sgg]').forEach(b=>b.classList.toggle('on', b===s));
         document.querySelectorAll('.sgg').forEach(g=>{ g.hidden = g.dataset.g!==s.dataset.sgg; }); return; }
  const m=e.target.closest('[data-sgmore]');
  if(m){ e.preventDefault(); const g=document.querySelector('.sgg[data-g="'+m.dataset.sgmore+'"]');
         if(g) g.querySelectorAll('.sgmore').forEach(x=>x.hidden=false); m.closest('.act').remove(); }
}, true);
document.addEventListener('click', e=>{                                   // 选股 / 持仓的消息标记：点标题 → 「消息」页那一条
  const a=e.target.closest('[data-nlink]'); if(!a) return;
  const d=document.getElementById('n-'+a.dataset.nlink); if(!d) return;
  e.preventDefault(); showTab('news', true); showMseg('news');
  d.open=true; const pd=d.parentElement && d.parentElement.closest('details'); if(pd) pd.open=true; d.classList.add('hl');
  setTimeout(()=>{ const top=document.querySelector('.top'); window.scrollTo(0, d.getBoundingClientRect().top+window.scrollY-((top&&top.offsetHeight)||0)-8); }, 50);
}, true);
document.addEventListener('click', e=>{                                   // 「规则接下来会自动买」点开的一行底下的「收起」：收起并回到那一行的摘要（点开的一行很长；2026-10-14）
  const b=e.target.closest('[data-abxclose]'); if(!b) return;
  const d=b.closest('details.abx'); if(!d) return;
  e.preventDefault(); d.open=false;
  const sm=d.querySelector('summary'), top=document.querySelector('.top'), h=(top&&top.offsetHeight)||0, y=sm.getBoundingClientRect().top;
  if(y<h || y>window.innerHeight-40) window.scrollTo(0, y+window.scrollY-h-8);   // 摘要在页头下面 / 屏幕外 → 滚到页头下面
  sm.focus({preventScroll:true});
}, true);
document.addEventListener('click', e=>{                                   // 选股的「怎么看 K 线图 去看 ›」→「持仓」里那一份（打开、滚到它；2026-10-15）
  const a=e.target.closest('[data-khelpgo]'); if(!a) return;
  const d=document.querySelector('#khelp details'); if(!d) return;
  e.preventDefault(); showTab('hold', true); d.open=true;
  setTimeout(()=>{ const top=document.querySelector('.top'); window.scrollTo(0, d.getBoundingClientRect().top+window.scrollY-((top&&top.offsetHeight)||0)-8); }, 50);
}, true);
function showMseg(s){ document.querySelectorAll('[data-mseg]').forEach(b=>b.classList.toggle('on', b.dataset.mseg===s));
  document.querySelectorAll('.mseg').forEach(g=>{ g.hidden = g.dataset.s!==s; }); }
document.addEventListener('click', e=>{ const b=e.target.closest('[data-mseg]'); if(!b) return; e.preventDefault(); showMseg(b.dataset.mseg); }, true);
