// qbreak 操作面板：quotes.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/quotes.js 提供；不要用构建工具）
import { $, CFG, nd, pcs, pxs, spc, syen, yen } from './core.js';
import { KD, KP, drawK } from './kline.js';
import { req } from './net.js';
import { BUY } from './trade.js';
        // 预计收益的百分比（负号与金额一样用 −）
let QD = null;                                                             // 最近一次取到的现价（/api/quotes）：卖出的预计收益优先用它
export function estOf(t){ const r=rtOf(t); return (r && r.q.est) || (QD && QD.rows && QD.rows[t] && QD.rows[t].est) || (CFG.est||{})[t] || null; }
// ── 确认框的立花实时价（2026-10-17 用户「想定时取得的话用yahoo，下单的时候在确认页面的时候用立花能看到实时价格 k线也可以更新到那时候」）──
// 定时的现价照旧 Yahoo；打开卖出 / 调仓 / 买入框时（盘中）才要一次 /api/quotes?rt=票（服务器登录立花只读取一次，60 秒内用缓存）→
// 框里的价 / 预计收益 / 限价按它算，K 线今天这一根更新到那个时刻；取不到 → 框里写原因、照旧 Yahoo。盘外不取（框里不显示这一行）。
const RT = {};                                                            // 票 → {q, j, ms}
export function rtOf(t){ const r=RT[t]; return r && Date.now()-r.ms<90000 ? r : null; }
let RTN = 0;
function rtShow(el, cls, text){
  el.hidden=false; el.className='rtl small'+(cls ? ' '+cls : ''); el.textContent='';
  if(cls==='ld') nd('span', 'spin', null, el);
  nd('span', null, text, el);
}
function rtText(q){ return '立花实时 '+String(q.at||'').slice(11,16)+' · '+pxs(q.px)+(q.chg_pct!=null ? ' · '+pcs(q.chg_pct) : ''); }
export async function rtQ(t, box, sg, onq){                               // box：框里那一行的 id；sg：建议的股票（没拿着）；onq(q)：取到之后框里重算
  const el=$(box); if(!el) return;
  el.hidden=true; const n=++RTN;
  if(!CFG.rt || !t) return;
  const hit=rtOf(t); if(hit){ rtShow(el, 'ok', rtText(hit.q)); if(onq) onq(hit.q); return; }
  rtShow(el, 'ld', '取立花实时价…');
  for(let i=0; i<3; i++){
    let x=null;
    try{ x=await req('/api/quotes?book='+encodeURIComponent(CFG.book)+'&rt='+encodeURIComponent(t)+(sg ? '&t='+encodeURIComponent(t) : ''),
                     {credentials:'same-origin', cache:'no-store', tmo:11000}); }catch(e){}
    if(n!==RTN) return;                                                    // 已经换了一个框
    const j=x && x.r.ok ? x.j : null, q=j && j.rows ? j.rows[t] : null, r=(j && j.rt) || {};
    if(j && !j.live){ el.hidden=true; return; }                            // 盘外：不取（下单按开盘价）
    if(q && q.src==='rt'){
      RT[t]={q:q, j:j, ms:Date.now()};
      if(sg) SQ={...j, rows:{...((SQ && SQ.rows) || {}), [t]:q}};
      rtShow(el, 'ok', rtText(q)); liveK({[t]:q}, j.live); if(onq) onq(q); if(sg) buyLive(); return;
    }
    if(r.pending){ await new Promise(res=>setTimeout(res, 3000)); continue; }
    rtShow(el, 'off', (r.why || (j ? '立花没回这只的现在值' : 'Mac 连不上'))+' → 按 Yahoo（约晚 20 分钟）'); return;
  }
  rtShow(el, 'off', '立花还没回 → 按 Yahoo（约晚 20 分钟）');
}
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
let SQERR = false;                                                        // 最近一次取现价失败了（买入框写「取不到」，不一直「载入中」）
function priceHead(q){ return '现价 '+pxs(q.px)+'（'+(q.src==='rt' ? '立花实时 ' : '')+hmOf(q)+(q.today && q.src!=='rt' ? '，约晚 20 分钟' : '')+'）'+(q.chg_pct!=null ? ' · 比收盘 '+pcs(q.chg_pct) : ''); }
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
    const q=R[e.dataset.sq]; if(!q || e.dataset.over) return;              // 没取的（K 线没打开）/ 超过一次能取的只数（写着说明）不动
    e.textContent='';
    nd('span', q.chg_pct==null ? null : (q.chg_pct>=0 ? 'up' : 'down'), priceHead(q), e);
    if(e.dataset.planned==='1') return;                                    // 已排在开盘买：只写现价
    for(const l of buyLines(q, j, false)) nd('div', 'muted sellx', l, e);
  });
  buyLive();
}
const SQMAX = CFG.sq_max || 12;                                            // 一次最多取几只（= 服务器的 SG_MAX）
let RECENT = [];                                                          // 最近点开的票（新的在前）：打开的超过 SQMAX 只时先取它们
function sqAll(){                                                         // 要取现价的建议股票：买入框里的 → 最近点开的 → 其余打开的（页面顺序）
  const open=[];
  document.querySelectorAll('#autobuy details.abx[open] details.kl[open] .chart[data-t], #suggest details.kl[open] .chart[data-t]')
    .forEach(b=>{ if(open.indexOf(b.dataset.t)<0) open.push(b.dataset.t); });
  const s=[];
  const d=$('#dlg-buy'); if(BUY && d && d.open) s.push(BUY.t);
  for(const t of RECENT.concat(open)) if(open.indexOf(t)>=0 && s.indexOf(t)<0) s.push(t);
  return s;
}
function sqWant(){ return sqAll().slice(0, SQMAX); }
function sqOver(over, n){                                                 // 这次取不到的（超过 SQMAX 只）：写一行说明，不留空、不留上一次的旧价
  document.querySelectorAll('.qt[data-sq]').forEach(e=>{
    if(over.indexOf(e.dataset.sq)>=0){
      e.dataset.over='1'; e.textContent='';
      nd('span', 'muted', '现价一次最多取 '+SQMAX+' 只（现在打开了 '+n+' 只）：收起几行再看', e);
    }else if(e.dataset.over){ delete e.dataset.over; e.textContent=''; }
  });
}
export async function loadSQ(){
  const all=sqAll(), ts=all.slice(0, SQMAX);
  sqOver(all.slice(SQMAX), all.length);
  if(!ts.length) return;
  let ok=false;
  try{
    const x=await req('/api/quotes?book='+encodeURIComponent(CFG.book)+'&t='+encodeURIComponent(ts.join(',')), {credentials:'same-origin', cache:'no-store'});
    if(x.r.ok && x.j){ ok=true; SQ={...x.j, rows:{...((SQ && SQ.rows) || {}), ...(x.j.rows || {})}}; showSQ(SQ); liveK(x.j.rows||{}, x.j.live); }
  }catch(e){}                                                              // 取不到：保留上一次的
  SQERR=!ok; if(!ok) buyLive();                                           // 买入框不再一直停在「现价载入中…」（2026-10-15）
}
export function buyLive(){                                                        // 买入框：现价 + 现在买按什么价 + 下单依据
  const e=$('#buy-live'); if(!e || !BUY) return;
  const q=SQ && SQ.rows && SQ.rows[BUY.t];
  e.textContent='';
  if(!q){ e.textContent=SQERR ? '现价取不到（Mac 连不上？连上之后会自动再取）：下单时执行器按当时的价格算' : '现价载入中…（Yahoo，约晚 20 分钟）'; return; }
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
document.addEventListener('toggle', e=>{                                   // 打开一只建议股票的 K 线（或「规则接下来会自动买」的一行）→ 取它的现价（并进今天这一根）
  const d=e.target; if(d.tagName!=='DETAILS' || !d.closest('#suggest, #autobuy')) return;
  if(d.open){ const c=d.querySelector('.chart[data-t]'), t=d.matches('details.abx, details.kl') && c ? c.dataset.t : null;
              if(t) RECENT=[t].concat(RECENT.filter(x=>x!==t)).slice(0, 50); }   // 最近点开的排前面
  if(d.open || document.querySelector('.qt[data-sq][data-over]')){ clearTimeout(SQT); SQT=setTimeout(loadSQ, 300); }   // 收起了几行：超过的那些现在取
}, true);
document.addEventListener('DOMContentLoaded', loadQ);
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) loadQ(); });
window.addEventListener('qb-reconnect', ()=>loadQ());                     // conn.js：连不上之后又连上了 → 马上再取现价
