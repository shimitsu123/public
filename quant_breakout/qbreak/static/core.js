// qbreak 操作面板：core.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/core.js 提供；不要用构建工具）
import { req } from './net.js';

export const CFG = JSON.parse(document.getElementById('qb-cfg').textContent);   // 页面里的 <script type="application/json" id="qb-cfg">（服务器生成）
export const $ = s => document.querySelector(s);
export const fmt = n => Number(n).toLocaleString('ja-JP');
// 票的「代码 名字」（2026-10-15 用户：「如果只有股票代号标记的话不知道是哪个股票 名字也要有」）：与 qbreak/names.py 的 label / annotate
// 同一写法 —— 代码在前、空一格、名字，不带 .T；查不到名字只写代码。名字表 = CFG.names（服务器按这一页上的票给；不联网）。
const NAMES = CFG.names || {};
function code(t){ const s=String(t==null ? '' : t).trim(); return s.slice(-2)==='.T' ? s.slice(0, -2) : s; }
export function tlab(t, name){                                           // name：按钮 data-name 等别处给的（旧写法「纳斯达克 100（1545）」去掉「（代码）」）
  const s=String(t==null ? '' : t).trim(), c=code(s);
  let n=String(name || NAMES[s] || NAMES[c+'.T'] || '').trim();
  const tail='（'+c+'）', tail2='（'+c+'.T）';
  if(n.slice(-tail.length)===tail) n=n.slice(0, -tail.length).trim(); else if(n.slice(-tail2.length)===tail2) n=n.slice(0, -tail2.length).trim();
  return (n && n!==s && n!==c) ? c+' '+n : c;
}
export function tqty(t, s, name){                                       // 名字后面紧跟数量：「1545 纳斯达克 100：4,110 → 96 口」（名字可能以数字结尾，
  const l=tlab(t, name);                                                 // 直接接数量读不出哪个是口数；2026-10-15 复核）；查不到名字「5202 100 股」= names.qty
  return l===code(t) ? l+' '+s : l+'：'+s;
}
const CMD = /(^|[^A-Za-z0-9_])(bash|liveu\.sh|run\.py|python3?|dev\.sh|routines\.sh|adopt|manual\s+(sell|adjust|trim|buy|corefix|core|cancel|unblock|list))(?![A-Za-z0-9_])/;
export function nameify(text){                                           // 兜底：文字里查得到名字的「7203.T」→「7203 トヨタ自動車」；重复跑结果不变
  if(typeof text!=='string' || text.indexOf('.T')<0) return text;        // （cid / 指令 id、引号 / = / 斜线后面的、链接、要复制粘贴的命令行那一行都不动）
  try{
    return text.split('\n').map(ln=>{
      if(ln.indexOf('.T')<0 || CMD.test(ln)) return ln;
      return ln.replace(/([0-9][0-9A-Z]{3})\.T(?![A-Za-z0-9_\-]|\.[A-Za-z0-9])/g, (m, c, i)=>{
        const p=i>0 ? ln[i-1] : '';
        if(p && /[A-Za-z0-9_\-.\/'"=]/.test(p)) return m;
        if(/https?:\/\/\S*$/.test(ln.slice(0, i))) return m;
        const n=NAMES[c+'.T'];
        if(!n) return m;
        const after=ln.slice(i+m.length).replace(/^[ 　]+/, ''), before=ln.slice(Math.max(0, i-n.length-2), i);
        if(after.indexOf(n)===0 || before.indexOf(n)>=0) return c;      // 已经带着名字：只去 .T
        return c+' '+n;
      });
    }).join('\n');
  }catch(e){ return text; }
}
export const yen = v => '¥' + fmt(Math.round(v));
export function toast(t, bad, sticky){const m=$('#toast');m.textContent=nameify(String(t==null ? '' : t))+(sticky?'\n（点一下关闭）':'');m.className='toast'+(bad?' bad':'');m.hidden=false;
  const d=document.querySelector('dialog[open]'), host=d || document.body;  // 对话框开着：提示放进对话框里（以前在对话框底下被盖住 → 点了「确定」像没反应；2026-10-15）
  if(m.parentNode!==host) host.appendChild(m);
  clearTimeout(toast.h); if(!sticky) toast.h=setTimeout(()=>{m.hidden=true;}, bad?9000:6000);}
document.addEventListener('close', e=>{ const m=$('#toast'); if(m && e.target.contains && e.target.contains(m)) document.body.appendChild(m); }, true);   // 对话框关了：提示回到页面上
let LASTBTN=null;                                                        // 最近点的按钮：处理中在它上面转圈（2026-10-11 用户：要有 loading 的感觉）
document.addEventListener('pointerdown', e=>{ const b=e.target.closest && e.target.closest('button'); if(b) LASTBTN=b; }, true);
document.addEventListener('keydown', e=>{ if(e.key==='Enter'||e.key===' '){ const b=document.activeElement; if(b && b.tagName==='BUTTON') LASTBTN=b; } }, true);
export function loading(on){ document.body.classList.toggle('loading', !!on); }
// 处理中：别的按钮先不让点（不会重复写）。2026-10-15「网页app经常卡住」：以前连标签栏 / 刷新 / HALT 也一起锁住、两个请求叠在一起时
// 先回来的那个就把按钮全放开了 → 改成计数，标签栏 / 刷新 / HALT / 连接条的按钮一直能点，请求结束（含出错、超时）一定放开
const FREE = '.tabbar button, [data-act=reload], [data-act=halt], #conn button, #bootbar button';
let BUSYN = 0;
function busy(on){
  BUSYN = Math.max(0, BUSYN + (on ? 1 : -1));
  if(on && BUSYN>1) return;
  if(!on && BUSYN>0) return;
  document.querySelectorAll('button').forEach(b=>{ if(b.matches(FREE)) return;
    if(on){ b.dataset.was=b.disabled?'1':''; b.disabled=true; } else if(b.dataset.was!==undefined){ b.disabled=b.dataset.was==='1'; delete b.dataset.was; } });
  loading(on);
  if(on){ const b=LASTBTN; if(b){ b.classList.add('loading'); b.setAttribute('aria-busy','true'); } }
  else document.querySelectorAll('button.loading').forEach(b=>{ b.classList.remove('loading'); b.setAttribute('aria-busy','false'); });
}
function reloadNow(){ if(typeof window.qbReload==='function') window.qbReload('user'); else location.reload(); }   // conn.js：先确认连得上 Mac 再刷新
export function reloadPage(b, label){                                          // 刷新：按钮转圈 + 顶部进度条，然后重新载入（连不上 → 连接条倒数重试，按钮放开）
  if(b){ b.classList.add('loading'); b.setAttribute('aria-busy','true'); if(label){ if(!b.dataset.label0) b.dataset.label0=b.textContent; b.textContent=label; } b.disabled=true; }
  loading(true); setTimeout(reloadNow, 30); }
window.addEventListener('beforeunload', ()=>loading(true));
window.addEventListener('pageshow', e=>{ if(e.persisted){ loading(false); document.querySelectorAll('button.loading').forEach(b=>{b.classList.remove('loading'); b.disabled=false;}); } });
const HALT_TIP = CFG.remote ? '人不在 Mac 旁边时：在 claude.ai 的云端对话里说「停 / 今天不要下单」（Mac 的执行器下一次运行会停）'
                            : '在 Mac 的 Claude 对话里说「停 / 今天不要下单」';
export async function api(path, body){                                  // 写操作（POST）：busy 一定在 finally 里放开（超时 / 出错也是）
  busy(true);
  try{ return await post1(path, body); }finally{ busy(false); }
}
async function post1(path, body){
  const halt = path==='/api/halt', where = path==='/api/request' ? '在「手动指令」里确认' : '再看一下';
  const fail = (t, sticky) => { toast(halt ? t+'\n'+HALT_TIP : t, true, halt || sticky); return null; };   // HALT 失败：每种都提示云端的「停」、不自动消失
  try{
    const h={'Content-Type':'application/json'}; h[CFG.auth.h]=CFG.auth.v;
    const x=await req(path,{method:'POST',headers:h,body:JSON.stringify(body||{}),credentials:'same-origin',cache:'no-store'});
    const r=x.r, j=x.j;
    if(j && j.need_confirm && !j.ok) return j;                             // 要先确认（固定口数 / 恢复按规则；200 + ok:false）：什么都没写 → 调用方弹「确认下单」框（trade.js post；2026-10-15）
    if(r.ok && !j) return fail(halt ? 'HALT 可能已经建好，但回应读不出来：刷新后看有没有「HALT 生效中」'
                                    : '回应读不出来：不确定有没有生效 —— 刷新后'+where+'，不要直接再点一次', true);
    if(!r.ok || !j.ok){
      if(r.status===401){ toast((j && j.msg) || '这台设备没被认出来：正在刷新…', true); setTimeout(()=>location.reload(),1500); return null; }
      if((j && j.unsure) || (!j && r.status>=500))                         // 面板内部出错 / 中途断了：可能已经写进去了（2026-10-12 再发防止）
        return fail((j && j.msg) || ('面板没正常回应（HTTP '+r.status+'）：不确定有没有'+(path==='/api/request' ? '写进去' : '生效')+' —— 刷新后'+where+'，不要直接再点一次'), true);
      return fail((j && j.msg) || ('没写成（HTTP '+r.status+'）'));
    }
    return j;
  }catch(e){
    if(e && e.name==='Timeout'){                                           // 请求可能已经到了 Mac：不确定有没有写进去
      if(halt) return fail(CFG.remote ? 'HALT 可能没送到：超过 15 秒没有回应（Mac 可能在睡眠）' : 'HALT 可能没写成：面板超过 15 秒没有回应');
      return fail(CFG.remote ? '超过 15 秒没有回应（Mac 可能在睡眠）：不确定有没有'+(path==='/api/request' ? '写进去' : '生效')+' —— Mac 醒来后刷新，'+where+'，不要直接再点一次'
                             : '面板超过 15 秒没有回应：不确定有没有'+(path==='/api/request' ? '写进去' : '生效')+' —— 刷新后'+where+'，不要直接再点一次');
    }
    return fail((halt ? 'HALT 没送到：' : '')+'连不上面板：'+e+'\n（Mac 睡着了、面板没运行，或手机的 Tailscale 没连上）');
  }
}
export function done(j){ if(!j) return; toast(j.msg || '已写'); loading(true); setTimeout(reloadNow, 2200); }
export function sheet(id){ const d=$(id); if(d.showModal){ if(!d.open) d.showModal(); } else d.setAttribute('open',''); return d; }
export function closeAll(){ document.querySelectorAll('dialog[open]').forEach(d=>{ if(d.close) d.close(); else d.removeAttribute('open'); }); }
export function syen(v){ return (v<0 ? '−' : '+')+'¥'+fmt(Math.abs(Math.round(v))); }
export function spc(v){ return (v<0 ? '−' : '+')+Math.abs(v).toFixed(2)+'%'; }
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
export function estLine(e, k, u){                                                 // 调仓（减）的预览一行
  const p=estPart(e, k); if(!p) return '';
  return '\n这 '+fmt(k)+' '+u+'预计收益 '+syen(p.pnl)+(p.pct!=null ? '（'+spc(p.pct)+'）' : '')+'：按'+(e.src==='live' ? '现价 ' : '最近收盘 ')
    +pxs(e.px)+'，已扣两边手续费，税前';
}
export function plBox(el, e){                                                     // 卖出全部的预计收益（几行；收益那行涨红跌绿）
  el.textContent=''; el.hidden=!(e && e.lines && e.lines.length); if(el.hidden) return;
  for(const ln of e.lines){
    const cls = ln.indexOf('预计收益')===0 ? (e.pnl>=0 ? 'up' : 'down') : (ln.indexOf('已扣')===0 || ln.indexOf('卖出手续费')===0 ? 'muted' : null);
    nd('div', cls, ln, el);
  }
}
export const NOTE = CFG.paper ? '\n\n模拟账户：手动操作后会和云端模拟盘不一致。' : CFG.real ? '\n\n★ 真钱（立花本番）：执行器会在立花真的下单。' : '';
export function coreShow(){ const r=$('#core-pct'); if(r) $('#core-val').textContent=r.value+'%'; }
export function nd(tag, cls, text, par){ const e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; if(par) par.appendChild(e); return e; }
export function pxs(v){ if(v==null) return '—'; return '¥'+(v<1000 ? v.toLocaleString('ja-JP',{minimumFractionDigits:1, maximumFractionDigits:1}) : Math.round(v).toLocaleString('ja-JP')); }
export function pcs(v){ return (v>=0?'+':'')+v.toFixed(2)+'%'; }
