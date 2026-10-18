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
// 切换标签的动画（2026-10-17 用户「底部的标签切换的时候也要有动画效果」）：新的一页从切换的方向滑进来（往右边的标签 = 从右边），
// 底栏的选中底色滑过去、图标弹一下；系统「减弱动态效果」打开时只淡入（CSS）
const EASE='cubic-bezier(.2,.8,.2,1)';
let IND=null;
function tabInd(now){                                                     // 底栏选中的底色移到选中的标签下面（now = 不要动画：刚打开 / 排序之后 / 转屏）
  const bar=document.querySelector('.tabbar'); if(!bar) return;
  if(!IND){ IND=document.createElement('i'); IND.className='tabind'; IND.setAttribute('aria-hidden', 'true'); bar.prepend(IND); }
  const b=bar.querySelector('[data-tabgo].on'); if(!b){ IND.style.opacity='0'; return; }
  if(now) IND.style.transition='none';
  IND.style.transform='translateX('+(b.offsetLeft+b.offsetWidth/2-IND.offsetWidth/2)+'px)'; IND.style.opacity='1';
  if(now){ void IND.offsetWidth; IND.style.transition=''; }
}
window.addEventListener('resize', ()=>tabInd(true));
function showTab(k, keep, init){
  if(TABK.indexOf(k)<0) k='home';
  const ob=document.querySelector('.tabbar [data-tabgo].on'), was=ob && ob.dataset.tabgo;
  const order=Array.from(document.querySelectorAll('.tabbar [data-tabgo]')).map(b=>b.dataset.tabgo);
  const dir=(!init && was && was!==k) ? (order.indexOf(k)>order.indexOf(was) ? 'in-r' : 'in-l') : '';
  document.querySelectorAll('.pane').forEach(p=>{
    const on=p.dataset.tab===k; p.classList.toggle('on', on); p.classList.remove('in-r', 'in-l');
    if(on && dir){ void p.offsetWidth; p.classList.add(dir); p.addEventListener('animationend', ()=>p.classList.remove(dir), {once:true}); }
  });
  document.querySelectorAll('[data-tabgo]').forEach(b=>{ const on=b.dataset.tabgo===k; b.classList.toggle('on', on); b.setAttribute('aria-selected', on?'true':'false');
    b.classList.remove('pop'); if(on && dir){ void b.offsetWidth; b.classList.add('pop'); } });
  tabInd(!dir);
  try{ sessionStorage.setItem('qb-tab', k); }catch(e){}
  if(location.hash!=='#tab='+k){ try{ history.replaceState(null, '', location.pathname+location.search+'#tab='+k); }catch(e){} }
  if(!keep) window.scrollTo(0,0);
}
// 底部标签从左到右的顺序（2026-10-17 用户：可以自定义）：存在这台设备的 cookie qb_tabs（服务器按它画底栏；这里点了马上排、也按它再排一次：页面是缓存的也对）
const TABC='qb_tabs';
function tabOrderNow(){                                                   // cookie → 顺序（只认 TABK 里的、去重，缺的按默认接上）
  let got=[]; try{ const m=document.cookie.match(/(?:^|;\s*)qb_tabs=([^;]*)/); if(m) got=decodeURIComponent(m[1]).split(','); }catch(e){}
  const o=got.filter((k, i)=>TABK.indexOf(k)>=0 && got.indexOf(k)===i);
  return o.concat(TABK.filter(k=>o.indexOf(k)<0));
}
function tabOrderShow(o){                                                 // 底栏 + 「更多」里的列表按 o 排
  const bar=document.querySelector('.tabbar'), ls=document.getElementById('taborder-list');
  o.forEach(k=>{
    const b=bar && bar.querySelector('[data-tabgo="'+k+'"]'); if(b) bar.appendChild(b);
    const r=ls && ls.querySelector('[data-tabk="'+k+'"]'); if(r) ls.appendChild(r);
  });
}
function tabOrderSave(o){
  try{ document.cookie=TABC+'='+encodeURIComponent(o.join(','))+'; path=/; max-age=157680000; SameSite=Lax'; }catch(e){}
}
tabOrderShow(tabOrderNow());
// 「恢复默认顺序」（2026-10-17 用户：改了之后恢复到上一个状态；改了之后一段时间没再改，现在的状态就是默认）：
// 第一次改的时候记下改之前的顺序（base）；UNDO_MS 里再改不换 base、只把时间往后推；过了 UNDO_MS 没再改 → 现在的就是默认（按钮变灰）。存在这台设备
const UNDO_MS=5*60*1000, UK='qb-tabs-undo';
let UMEM=null, UT=0;
function undoGet(){
  let u=UMEM; try{ const x=localStorage.getItem(UK); if(x) u=JSON.parse(x); }catch(e){}
  return (u && Array.isArray(u.base) && Date.now()-(+u.at||0)<UNDO_MS) ? u : null;
}
function undoSet(u){ UMEM=u; try{ if(u) localStorage.setItem(UK, JSON.stringify(u)); else localStorage.removeItem(UK); }catch(e){} }
function undoShow(){
  const b=document.querySelector('[data-tabmv="reset"]'), n=document.getElementById('taborder-undo'), u=undoGet();
  const on=!!u && u.base.join(',')!==tabOrderNow().join(',');
  if(b) b.disabled=!on;
  if(n) n.textContent=on ? '改了之后 '+Math.max(1, Math.ceil((UNDO_MS-(Date.now()-u.at))/60000))+' 分钟内可以恢复到改之前的顺序；之后现在的顺序就成为默认'
                         : '现在的顺序就是默认（改了之后 '+(UNDO_MS/60000)+' 分钟内可以恢复）';
  clearTimeout(UT); if(on) UT=setTimeout(undoShow, Math.min(30000, UNDO_MS-(Date.now()-u.at)+50));
}
undoShow();
function flip(els, mutate){                                               // 排序之后各自从原来的位置滑到新的位置（FLIP）
  const R=new Map(els.map(e=>[e, e.getBoundingClientRect()]));
  mutate();
  const mv=[];
  els.forEach(e=>{ const a=R.get(e), b=e.getBoundingClientRect(), dx=a.left-b.left, dy=a.top-b.top;
    if(!a.width || (Math.abs(dx)<0.5 && Math.abs(dy)<0.5)) return;
    e.style.transition='none'; e.style.transform='translate('+dx+'px,'+dy+'px)'; mv.push(e); });
  if(!mv.length) return;
  void document.body.offsetWidth;
  mv.forEach(e=>{ e.style.transition='transform .26s '+EASE; e.style.transform='';
    e.addEventListener('transitionend', ()=>{ e.style.transition=''; }, {once:true}); });
}
const sortEls=()=>Array.from(document.querySelectorAll('.tabbar [data-tabgo], #taborder-list [data-tabk]'));
// 震一下（2026-10-17 用户「排序要用拖动的方法来做 有震动的感觉」）：Android = navigator.vibrate；iPhone 的 Safari 没有 vibrate →
// 点一下藏起来的系统开关（<input type=checkbox switch>，iOS 18 起切换时有触感）；别的（Mac）什么都不做
let HSW=null;
function haptic(k){
  try{ if(typeof navigator.vibrate==='function'){ navigator.vibrate(k==='tick' ? 8 : k==='drop' ? [6, 50, 12] : 14); return; } }catch(e){}
  try{
    if(!HSW){ HSW=document.createElement('label'); HSW.className='hsw'; HSW.setAttribute('aria-hidden', 'true');
              HSW.innerHTML="<input type='checkbox' switch tabindex='-1'>"; HSW.addEventListener('click', e=>e.stopPropagation()); document.body.appendChild(HSW); }
    HSW.click();
  }catch(e){}
}
// 按住拖动排序：box 里的 sel 一个个是能拖的；axis 'y' = 上下（「更多」里的列表）/ 'x' = 左右（底栏）。
// 鼠标：按下移一点就拖；触摸：按住 ≡（.tgr）马上拖，按住别处 0.28 秒不动才拖（先动了 = 滚页面 / 点一下照旧）。
// 拿起 / 每换一个位置 / 放下各震一下；done(新顺序的元素) 存起来。拖过之后的那一下 click 不算（不会顺手切到那个标签）。
const HOLD=280, SLOP=8;
let NOCLICK=0;
window.addEventListener('click', e=>{ if(Date.now()<NOCLICK && !(e.target.closest && e.target.closest('.hsw'))){ e.preventDefault(); e.stopPropagation(); NOCLICK=0; } }, true);
function sortable(box, sel, axis, done){
  if(!box || box._sort) return; box._sort=1;
  let st=null;
  const P=e=>axis==='y' ? e.clientY : e.clientX;
  const items=()=>Array.from(box.querySelectorAll(sel));
  function lift(){
    const its=items(), i=its.indexOf(st.it); if(i<0){ st=null; return; }
    const R=its.map(el=>el.getBoundingClientRect()), a=axis==='y' ? 'top' : 'left', z=axis==='y' ? 'height' : 'width';
    st.its=its; st.i=st.j=i; st.mid=R.map(r=>r[a]+r[z]/2);
    st.step=its.length>1 ? Math.abs((i>0 ? R[i][a]-R[i-1][a] : R[i+1][a]-R[i][a])) : R[i][z];
    st.on=true; box.classList.add('sorting'); st.it.classList.add('lift');
    its.forEach(el=>{ if(el!==st.it) el.classList.add('shift'); });
    try{ box.setPointerCapture(st.id); }catch(e){}
    haptic('pick');
  }
  function move(e){
    const d=P(e)-st.p0, c=st.mid[st.i]+d, n=st.its.length;
    let j=0; for(let k=0;k<n;k++){ if(k!==st.i && st.mid[k]<c) j++; }
    st.it.style.transform=(axis==='y' ? 'translateY(' : 'translateX(')+d+'px)';
    if(j!==st.j){
      st.j=j; haptic('tick');
      st.its.forEach((el, k)=>{ if(k===st.i) return;
        const s=(k>st.i && k<=j) ? -st.step : (k<st.i && k>=j) ? st.step : 0;
        el.style.transform=s ? (axis==='y' ? 'translateY(' : 'translateX(')+s+'px)' : ''; });
    }
  }
  function end(ok){
    clearTimeout(st && st.t);
    const s=st; st=null; if(!s || !s.on) return;
    NOCLICK=Date.now()+400;
    const o=s.its.slice(); if(ok && s.j!==s.i){ o.splice(s.i, 1); o.splice(s.j, 0, s.it); }
    flip(sortEls(), ()=>{                                                 // 放下：拿着的那个滑进它的位置，别的停在让出来的位置（不跳）
      box.classList.remove('sorting');
      s.its.forEach(el=>{ el.classList.remove('shift'); el.style.transform=''; });
      if(ok && s.j!==s.i) done(o);
    });
    setTimeout(()=>s.it.classList.remove('lift'), 120);
    if(ok && s.j!==s.i) haptic('drop');
  }
  box.addEventListener('pointerdown', e=>{
    if(st || (e.pointerType==='mouse' && e.button!==0)) return;
    const it=e.target.closest(sel); if(!it || !box.contains(it)) return;
    st={it, id:e.pointerId, x0:e.clientX, y0:e.clientY, p0:P(e), on:false, mouse:e.pointerType==='mouse', t:0};
    if(!st.mouse && e.target.closest('.tgr')){ e.preventDefault(); lift(); return; }
    if(!st.mouse) st.t=setTimeout(()=>{ if(st && !st.on) lift(); }, HOLD);
  });
  box.addEventListener('pointermove', e=>{
    if(!st || e.pointerId!==st.id) return;
    if(!st.on){
      const far=Math.hypot(e.clientX-st.x0, e.clientY-st.y0)>SLOP;
      if(far && st.mouse) lift(); else if(far){ clearTimeout(st.t); st=null; return; }   // 触摸先动了：照旧滚页面
      if(!st || !st.on) return;
    }
    e.preventDefault(); move(e);
  });
  box.addEventListener('pointerup', e=>{ if(st && e.pointerId===st.id) end(true); });
  box.addEventListener('pointercancel', e=>{ if(st && e.pointerId===st.id) end(false); });
  box.addEventListener('touchmove', e=>{ if(st && st.on) e.preventDefault(); }, {passive:false});   // 拖着的时候页面不跟着滚
  box.addEventListener('contextmenu', e=>{ if(st) e.preventDefault(); });                            // 长按不出菜单
}
function tabOrderSet(o, anim){                                           // anim：自己排（键盘 / 恢复）→ 用 flip；拖的已经在 flip 里
  const before=tabOrderNow();
  if(before.join(',')!==o.join(',')){ const u=undoGet(); undoSet({base:u ? u.base : before, at:Date.now()}); }
  const go=()=>{ tabOrderSave(o); tabOrderShow(o); };
  if(anim) flip(sortEls(), go); else go();
  undoShow(); tabInd(true);
}
sortable(document.getElementById('taborder-list'), '[data-tabk]', 'y', els=>tabOrderSet(els.map(r=>r.dataset.tabk)));
sortable(document.querySelector('.tabbar'), '[data-tabgo]', 'x', els=>tabOrderSet(els.map(b=>b.dataset.tabgo)));
document.addEventListener('keydown', e=>{                                  // 键盘：≡ 上按 ↑ / ↓ 挪一格（焦点跟着）
  const g=e.target.closest && e.target.closest('#taborder-list .tgr'); if(!g || (e.key!=='ArrowUp' && e.key!=='ArrowDown')) return;
  e.preventDefault();
  const k=g.closest('[data-tabk]').dataset.tabk, o=tabOrderNow(), i=o.indexOf(k), j=i+(e.key==='ArrowUp' ? -1 : 1);
  if(i<0 || j<0 || j>=o.length) return;
  o.splice(i, 1); o.splice(j, 0, k); tabOrderSet(o, true);
  g.focus({preventScroll:true});
});
document.addEventListener('click', e=>{
  const b=e.target.closest('[data-tabmv="reset"]'); if(!b) return;
  e.preventDefault();
  const u=undoGet(); if(!u) { undoShow(); return; }
  flip(sortEls(), ()=>{ tabOrderSave(u.base); tabOrderShow(u.base); });
  undoSet(null); undoShow(); tabInd(true); haptic('drop');
}, true);
document.addEventListener('click', e=>{ const b=e.target.closest('[data-tabgo]'); if(!b) return; e.preventDefault(); showTab(b.dataset.tabgo); }, true);
// 左右滑整个页面 = 切到底栏上相邻的标签（2026-10-18 用户「滑动整体页面的话底部的标签也可以切换到相邻的标签」）：页面跟着手指走，
// 滑过 1/4 屏宽（或快速一甩）→ 切过去并震一下，不够 → 弹回；最左 / 最右的标签再往外滑只拉动一点、不切。
// 不接：K 线（拖动 = 看更早 / 更新）、能左右滚的表格与小标签、底栏与「更多」里的排序、对话框、输入框、屏幕左右边缘（留给浏览器的返回）；
// 先上下动了 = 照旧滚页面
const SW_SKIP='.chart,.tabbar,#taborder-list,dialog,input,textarea,select,[contenteditable],.hsw,.iib';
const SW_EDGE=20, SW_LOCK=8;
let SW=null;
function swScrollsX(el){                                                  // 手指下面有能左右滚的东西 → 让它自己滚
  for(; el && el!==document.body; el=el.parentElement){
    if(el.scrollWidth>el.clientWidth+1){ const ox=getComputedStyle(el).overflowX; if(ox==='auto' || ox==='scroll') return true; }
  }
  return false;
}
function swNext(d){                                                       // 底栏上现在这个标签的左（-1）/ 右（+1）边那个；没有 → null
  const o=Array.from(document.querySelectorAll('.tabbar [data-tabgo]')).map(b=>b.dataset.tabgo);
  const ob=document.querySelector('.tabbar [data-tabgo].on'), i=ob ? o.indexOf(ob.dataset.tabgo) : -1;
  return (i>=0 && o[i+d]) ? o[i+d] : null;
}
function swPaint(panes, v, anim){
  panes.forEach(p=>{ p.style.transition=anim ? 'transform .2s '+EASE+', opacity .2s '+EASE : 'none';
    p.style.transform=v ? 'translateX('+v+'px)' : ''; p.style.opacity=v ? String(1-Math.min(0.3, Math.abs(v)/innerWidth*0.5)) : ''; });
}
function swEnd(ok){
  const s=SW; SW=null; if(!s || !s.lock) return;
  const h=s.hist, a=h[0], z=h[h.length-1], v=(a && z && z[0]>a[0]) ? (z[1]-a[1])/(z[0]-a[0]) : 0;
  const fast=Math.abs(s.dx)>40 && Math.abs(v)>0.5 && (v<0)===(s.dx<0);    // 快速一甩：最后 0.12 秒 > 0.5 px/ms、方向一致
  if(ok && s.nb && (Math.abs(s.dx)>innerWidth*0.25 || fast)){
    swPaint(s.panes, 0, false); s.panes.forEach(p=>{ p.style.transition=''; });
    showTab(s.nb); haptic('tick'); return;                                // 新的一页照旧从滑的方向滑进来
  }
  swPaint(s.panes, 0, true);                                              // 不够 → 弹回
  s.panes.forEach(p=>p.addEventListener('transitionend', ()=>{ p.style.transition=''; }, {once:true}));
}
document.addEventListener('touchstart', e=>{
  SW=null;
  if(e.touches.length!==1 || document.querySelector('dialog[open]')) return;
  const t=e.touches[0], tg=e.target;
  if(!tg || !tg.closest || !tg.closest('main') || tg.closest(SW_SKIP) || swScrollsX(tg)) return;
  if(t.clientX<SW_EDGE || t.clientX>innerWidth-SW_EDGE) return;
  SW={x0:t.clientX, y0:t.clientY, lock:false, dx:0, nb:null, panes:[], hist:[]};
}, {passive:true});
document.addEventListener('touchmove', e=>{
  if(!SW) return;
  if(e.touches.length!==1){ swEnd(false); return; }
  const t=e.touches[0], dx=t.clientX-SW.x0, dy=t.clientY-SW.y0;
  if(!SW.lock){
    if(Math.hypot(dx, dy)<SW_LOCK) return;
    if(Math.abs(dx)<Math.abs(dy)*1.3 || !e.cancelable || (window.getSelection && String(getSelection()))){ SW=null; return; }   // 上下滚 / 已经在滚 / 在选字
    SW.lock=true; SW.panes=Array.from(document.querySelectorAll('.pane.on'));
  }
  e.preventDefault();
  SW.dx=dx; SW.nb=swNext(dx<0 ? 1 : -1);
  const now=Date.now(); SW.hist.push([now, dx]); while(SW.hist.length>2 && now-SW.hist[0][0]>120) SW.hist.shift();
  swPaint(SW.panes, SW.nb ? dx : dx*0.25, false);                     // 两头没有标签：只拉动一点
}, {passive:false});
document.addEventListener('touchend', ()=>swEnd(true));
document.addEventListener('touchcancel', ()=>swEnd(false));
(function(){
  const q=new URLSearchParams(location.search), h=location.hash.replace(/^#/,'');
  let k=q.get('tab') || (h.indexOf('tab=')===0 ? h.slice(4) : '');
  let target=null;
  if(!k && h){ target=document.getElementById(h); const p=target && target.closest('.pane'); if(p) k=p.dataset.tab; }   // 旧的锚点（#holdings 等）
  if(!k){ try{ k=sessionStorage.getItem('qb-tab')||''; }catch(e){} }
  showTab(k||'home', true, true);                                       // 打开页面：不要动画
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
// 「交易」的「另有 …」/「已结束 / 不是今天的」：点开过的刷新之后照样开着（写完指令、撤单之后页面会刷新；复核 8，2026-10-16：以前每次刷新都收起来，
// 刚在里面点过按钮的那一块要再点开）。只记这个标签页（sessionStorage）；读写不了 → 照旧收起。
const FOLDK='qb-fold';
function foldKey(d, path){ const s=d.closest('section'); return path+'|'+((s&&s.id)||'')+'|'+(d.classList.contains('later') ? 'later' : 'ended'); }
function foldSave(d, store, path){
  let m={}; try{ m=JSON.parse(store.getItem(FOLDK)||'{}')||{}; }catch(e){ m={}; }
  if(d.open) m[foldKey(d, path)]=1; else delete m[foldKey(d, path)];
  try{ store.setItem(FOLDK, JSON.stringify(m)); }catch(e){}
}
function foldRestore(doc, store, path){
  let m={}; try{ m=JSON.parse(store.getItem(FOLDK)||'{}')||{}; }catch(e){ return; }
  doc.querySelectorAll('details.later, details.ended').forEach(d=>{ if(m[foldKey(d, path)]) d.open=true; });
}
document.addEventListener('toggle', e=>{                                  // toggle 不冒泡：在捕获阶段接
  const d=e.target; if(!d || !d.matches || !d.matches('details.later, details.ended')) return;
  try{ foldSave(d, sessionStorage, location.pathname); }catch(err){}
}, true);
try{ foldRestore(document, sessionStorage, location.pathname); }catch(err){}

// ⓘ = 浮在上面的小框（2026-10-17 用户：「点击ⓘ要出现弹窗的形式 不要影响周围ui布局」）：放在 ⓘ 下面（下面放不下 → 上面），
// 左右不出屏幕；同时只开一个；点别处 / Esc / 滚动 / 改窗口大小 → 收起
function tipPlace(d){
  const b=d.querySelector(':scope>.iib'), s=d.querySelector(':scope>summary'); if(!b || !s) return;
  const vw=document.documentElement.clientWidth, vh=window.innerHeight, r=s.getBoundingClientRect(), M=12, w=b.offsetWidth, h=b.offsetHeight;
  const x=Math.max(M, Math.min(r.left+r.width/2-w/2, vw-w-M));
  let y=r.bottom+6;
  if(y+h>vh-M) y=r.top-6-h>=M ? r.top-6-h : Math.max(M, vh-h-M);
  b.style.left=x+'px'; b.style.top=y+'px'; d.classList.add('on');
}
function tipsClose(keep){ document.querySelectorAll('details.ii[open]').forEach(o=>{ if(o!==keep){ o.open=false; o.classList.remove('on'); } }); }
document.addEventListener('toggle', e=>{                                  // toggle 不冒泡：在捕获阶段接
  const d=e.target; if(!d || !d.matches || !d.matches('details.ii')) return;
  if(d.open){ tipsClose(d); tipPlace(d); } else d.classList.remove('on');
}, true);
document.addEventListener('click', e=>{ if(!(e.target.closest && e.target.closest('details.ii'))) tipsClose(null); }, true);
document.addEventListener('keydown', e=>{ if(e.key==='Escape') tipsClose(null); });
window.addEventListener('scroll', e=>{ if(!(e.target && e.target.closest && e.target.closest('.iib'))) tipsClose(null); }, true);
window.addEventListener('resize', ()=>tipsClose(null));
