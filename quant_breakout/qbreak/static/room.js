// qbreak 操作面板：room.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/room.js 提供；不要用构建工具）
// 「今天还能买几次 / 卖几次」（D6；2026-10-15 用户要求 3）：交易页最上面的小卡 + 持仓卡片每只的小标记「今天还能卖 ✓ / 买 ✗（原因）」。
// 数 = /api/trade_room（qbreak/trade_room.py：时段、差金決済、执行器规则、钱、闸门）；服务器先画好一份（panel._room_card），这里定时重画同一个样子
// （盘中每 1 分钟，其他时间每 10 分钟；回到页面 / 重新连上也再取）。代码一律带名字（服务器给 label；文字里的「7203.T」用 nameify 兜底）。
import { $, CFG, nameify, nd } from './core.js';
import { req } from './net.js';

export function roomSide(r, side){                                         // 每只一行里的一边（与 panel._room_side 同一写法）
  const x=r[side]||{}, w=side==='sell' ? '卖' : '买', u=r.kind==='core' ? '口' : '股';
  if(x.n) return w+'：最多 '+Number(x.max_qty||0).toLocaleString('ja-JP')+' '+u+(x.via ? ' · 用'+x.via : '');
  const why=(x.why && x.why[0]) || '不能';
  return w+' ✗：'+why+(x.next && why.indexOf(x.next)<0 ? '（'+x.next+'）' : '');
}
export function roomShow(j){                                               // 重画卡片 + 持仓的小标记；j.ok=false / 没有 → 不动（保留上一次的）
  if(!j || !j.ok) return;
  const el=$('#room');
  if(el){
    el.hidden=false;
    const open=!!(el.querySelector('details') && el.querySelector('details').open);   // 展开着的保持展开
    el.textContent='';
    const hl=nd('div', 'rm-hl', null, el); nd('b', null, j.headline, hl);
    nd('div', 'small', nameify(j.market.line), el);
    for(const w of j.gates||[]) nd('div', 'neg small', '★ '+nameify(w), el);
    for(const w of j.notes||[]) nd('div', 'muted small', '· '+nameify(w), el);
    const d=nd('details', 'rm', null, el); if(open) d.open=true;
    nd('summary', 'muted small', '为什么是这个数 · 每只', d);
    const ov=j.overall||{};
    for(const [k, w] of [['buy_left','买'],['sell_left','卖'],['trades_left','共']]) if(ov[k]) nd('div', 'small', w+' '+ov[k].n+'：'+nameify(ov[k].why), d);
    for(const t in (j.per_ticker||{})){
      const r=j.per_ticker[t]; if(r.cand) continue;
      const li=nd('div', 'li', null, d), g=nd('div', 'grow', null, li);
      nd('b', null, r.label, g); g.appendChild(document.createTextNode(' ')); nd('span', 'chip', r.chip, g);
      nd('div', 'muted small', nameify(roomSide(r, 'sell')), g); nd('div', 'muted small', nameify(roomSide(r, 'buy')), g);
    }
    const c=j.cands||{};
    if(c.n){
      const gs=Object.entries(c.groups||{}).sort((a, b)=>b[1]-a[1]).map(([k, v])=>k+' '+v+' 只').join('、');
      nd('div', 'muted small', '选股页的候选 '+c.n+' 只：名额与钱都够的 '+c.ok+' 只'+(gs ? '；不能：'+gs : '')+'（只是数，不是建议；买不买是你的决定）', d);
    }
    const n=nd('div', 'muted small', j.note+'（差金決済：', el);
    const a=nd('a', null, '立花 e支店的说明', n); a.href=j.sakin_url; a.target='_blank'; a.rel='noopener';
    n.appendChild(document.createTextNode('，2026-10-15 核对）'));
  }
  document.querySelectorAll('[data-room]').forEach(e=>{                    // 持仓的小标记：没有这只（卖完了 / 不在账本）→ 空
    const r=(j.per_ticker||{})[e.dataset.room]; e.textContent=r ? r.chip : '';
  });
}
let RTID=null, RFLY=false;
async function loadRoom(){                                                 // 同时只取一次（2026-10-24 复核：取的途中切回来 / 重新连上又叫一次 → 两条定时器叠在一起）
  if(RFLY) return;
  RFLY=true; clearTimeout(RTID); RTID=null;
  try{
    if(!$('#room')) return;
    let live=!!CFG.live;
    try{
      const x=await req('/api/trade_room?book='+encodeURIComponent(CFG.book), {credentials:'same-origin', cache:'no-store'});
      if(x.r.ok && x.j){ roomShow(x.j); live=!!(x.j.market && ['am','pm'].indexOf(x.j.market.phase)>=0); }
    }catch(e){}                                                            // 取不到（Mac 睡眠 / 没网）：保留上一次的
    clearTimeout(RTID); RTID=setTimeout(loadRoom, live ? 60000 : 600000);   // 盘中 1 分钟，其他时间 10 分钟（现价缓存更新了数也会变）
  }finally{ RFLY=false; }
}
if(CFG.room) RTID=setTimeout(loadRoom, CFG.live ? 60000 : 600000);       // 页面本身是刚画的：先不取，到时间再取
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden && CFG.room) loadRoom(); });
window.addEventListener('qb-reconnect', ()=>{ if(CFG.room) loadRoom(); });  // conn.js：连不上之后又连上了 → 马上再取
