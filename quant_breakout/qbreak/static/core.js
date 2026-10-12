// qbreak 操作面板：core.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/core.js 提供；不要用构建工具）
import { req } from './net.js';

export const CFG = JSON.parse(document.getElementById('qb-cfg').textContent);   // 页面里的 <script type="application/json" id="qb-cfg">（服务器生成）
export const $ = s => document.querySelector(s);
export const fmt = n => Number(n).toLocaleString('ja-JP');
export const yen = v => '¥' + fmt(Math.round(v));
export function toast(t, bad, sticky){const m=$('#toast');m.textContent=t+(sticky?'\n（点一下关闭）':'');m.className='toast'+(bad?' bad':'');m.hidden=false;
  clearTimeout(toast.h); if(!sticky) toast.h=setTimeout(()=>{m.hidden=true;}, bad?9000:6000);}
let LASTBTN=null;                                                        // 最近点的按钮：处理中在它上面转圈（2026-10-11 用户：要有 loading 的感觉）
document.addEventListener('pointerdown', e=>{ const b=e.target.closest && e.target.closest('button'); if(b) LASTBTN=b; }, true);
document.addEventListener('keydown', e=>{ if(e.key==='Enter'||e.key===' '){ const b=document.activeElement; if(b && b.tagName==='BUTTON') LASTBTN=b; } }, true);
export function loading(on){ document.body.classList.toggle('loading', !!on); }
function busy(on){document.querySelectorAll('button').forEach(b=>{if(on){b.dataset.was=b.disabled?'1':'';b.disabled=true;}else{b.disabled=b.dataset.was==='1';}});
  loading(on); const b=LASTBTN; if(b){ b.classList.toggle('loading', !!on); b.setAttribute('aria-busy', on?'true':'false'); } }
export function reloadPage(b, label){                                          // 刷新：按钮转圈 + 顶部进度条，然后重新载入
  if(b){ b.classList.add('loading'); b.setAttribute('aria-busy','true'); if(label) b.textContent=label; b.disabled=true; }
  loading(true); setTimeout(()=>location.reload(), 30); }
window.addEventListener('beforeunload', ()=>loading(true));
window.addEventListener('pageshow', e=>{ if(e.persisted){ loading(false); document.querySelectorAll('button.loading').forEach(b=>{b.classList.remove('loading'); b.disabled=false;}); } });
const HALT_TIP = CFG.remote ? '人不在 Mac 旁边时：在 claude.ai 的云端对话里说「停 / 今天不要下单」（Mac 的执行器下一次运行会停）'
                            : '在 Mac 的 Claude 对话里说「停 / 今天不要下单」';
export async function api(path, body){
  busy(true);
  const halt = path==='/api/halt', where = path==='/api/request' ? '在「手动指令」里确认' : '再看一下';
  const fail = (t, sticky) => { toast(halt ? t+'\n'+HALT_TIP : t, true, halt || sticky); return null; };   // HALT 失败：每种都提示云端的「停」、不自动消失
  try{
    const h={'Content-Type':'application/json'}; h[CFG.auth.h]=CFG.auth.v;
    const x=await req(path,{method:'POST',headers:h,body:JSON.stringify(body||{}),credentials:'same-origin',cache:'no-store'});
    const r=x.r, j=x.j;
    busy(false);
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
    busy(false);
    if(e && e.name==='Timeout'){                                           // 请求可能已经到了 Mac：不确定有没有写进去
      if(halt) return fail(CFG.remote ? 'HALT 可能没送到：超过 15 秒没有回应（Mac 可能在睡眠）' : 'HALT 可能没写成：面板超过 15 秒没有回应');
      return fail(CFG.remote ? '超过 15 秒没有回应（Mac 可能在睡眠）：不确定有没有'+(path==='/api/request' ? '写进去' : '生效')+' —— Mac 醒来后刷新，'+where+'，不要直接再点一次'
                             : '面板超过 15 秒没有回应：不确定有没有'+(path==='/api/request' ? '写进去' : '生效')+' —— 刷新后'+where+'，不要直接再点一次');
    }
    return fail((halt ? 'HALT 没送到：' : '')+'连不上面板：'+e+'\n（Mac 睡着了、面板没运行，或手机的 Tailscale 没连上）');
  }
}
export function done(j){ if(!j) return; toast(j.msg || '已写'); loading(true); setTimeout(()=>location.reload(), 2200); }
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
