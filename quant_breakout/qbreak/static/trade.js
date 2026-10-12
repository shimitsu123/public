// qbreak 操作面板：trade.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/trade.js 提供；不要用构建工具）
import { $, CFG, NOTE, api, closeAll, coreShow, done, estLine, fmt, nd, plBox, reloadPage, sheet, toast, yen } from './core.js';
import { SUBS, TFS, drawK, setSUB, setTF, showK } from './kline.js';
import { buyLive, estOf, loadSQ } from './quotes.js';

let ASK=null, CUR=null;
function ask(title, body, okText, opt){
  opt=opt||{}; $('#ask-title').textContent=title; $('#ask-body').textContent=body; plBox($('#ask-pl'), opt.pl||null);
  const ok=$('#ask-ok'); ok.textContent=okText||'确定'; ok.className='btn '+(opt.danger?'danger':'primary');
  const inp=$('#ask-input'); inp.hidden=!opt.input; inp.value=''; inp.placeholder=opt.input||'';
  sheet('#dlg-ask'); return new Promise(res=>{ ASK=res; });
}
// ── 调仓（股数 / 金额 / 占权益 %）：按最近收盘估算；执行器下单时按当时的价格再算一次；调仓条按单元（LOT 股）分格 ──
const LOT = CFG.lot || 100;
let ADJ = null, ADJ_RULE = null;                                           // ADJ_RULE：调仓对话框里个股那行说明的原文（核心 ETF 换掉、个股换回）
function pctOf(n){ return CFG.eq>0 && ADJ.px>0 ? (n*ADJ.px/CFG.eq*100).toFixed(1)+'%' : '—'; }
function ALOT(){ return (ADJ && ADJ.lot) || LOT; }                         // 一个单元几股（核心 ETF：几口）
function UW(){ return (ADJ && ADJ.core) ? '口' : '股'; }
function cpctOf(n){                                                        // 核心 ETF：目标口数 → 闲置资金比例 %（与 manual_orders.core_pct_for 相同）
  if(!(ADJ.u100>0)) return 0;
  const m=Math.min(n, ADJ.u100), L=ALOT(); let p=Math.ceil(m/ADJ.u100*10000-1e-9)/100;
  if(Math.floor(ADJ.u100*p/100/L+1e-9)*L!==m) p=Math.round(m/ADJ.u100*10000)/100;
  return p;
}
function capLab(){ return CFG.cap>=100 ? '总权益' : '单只上限 '+CFG.cap+'%'; }   // 手动买入 / 加仓的上限（2026-10-12 起 = 总权益）
function adjCap(){                                                          // 个股：单只上限 cap%；核心 ETF：规则目标额（比例 100%）；固定口数：总权益
  if(ADJ.fix) return ADJ.px>0 && CFG.eq>0 ? Math.floor(CFG.eq/ADJ.px/ALOT()+1e-9)*ALOT() : 0;
  if(ADJ.core) return Math.floor((ADJ.u100||0)/ALOT())*ALOT();
  return ADJ.px>0 && CFG.eq>0 ? Math.floor(CFG.eq*CFG.cap/100/ADJ.px/ALOT()+1e-9)*ALOT() : 0;
}
function adjTarget(){
  const v=parseFloat($('#adj-val').value); if(!(v>=0) || !isFinite(v)) return null;
  let raw;
  if(ADJ.unit==='shares') raw=v; else if(!(ADJ.px>0)) return null; else if(ADJ.unit==='yen') raw=v/ADJ.px; else raw=CFG.eq*v/100/ADJ.px;
  return Math.max(0, Math.floor(raw/ALOT()+1e-9)*ALOT());
}
function adjShow(n){
  const u=ADJ.unit, e=$('#adj-val');
  e.value = u==='shares' ? n : u==='yen' ? Math.round(n*ADJ.px) : (CFG.eq>0 ? (n*ADJ.px/CFG.eq*100).toFixed(1) : 0);
}
function adjUnit(u){
  const n=adjTarget(); ADJ.unit=u;
  document.querySelectorAll('#adj-seg button').forEach(b=>b.setAttribute('aria-pressed', b.dataset.u===u ? 'true' : 'false'));
  $('#adj-unit').textContent = {shares:UW(), yen:'円', pct:'%'}[u];
  $('#adj-val').step = u==='shares' ? ALOT() : u==='yen' ? 1000 : 0.1;
  adjShow(n==null ? ADJ.shares : n); adjPrev();
}
function adjBar(){                                                         // 调仓条按「一次最少能买卖的股数」（1 个单元 = LOT 股 / 口）分格
  const r=$('#adj-range'), bar=$('#adj-bar'), lab=$('#adj-lab'), note=$('#adj-note'); if(!r || !bar || !ADJ) return;
  const LOT=ALOT(), U=UW();
  const n=Math.max(1, Math.round(+r.max/LOT)), have=Math.round(ADJ.shares/LOT), tgt=Math.round(+r.value/LOT), capN=Math.floor(adjCap()/LOT);
  const G=Math.ceil(n/50);                                                  // 单元太多（> 50）时几格并成一格，手机上也看得清
  bar.textContent='';
  for(let a=0; a<n; a+=G){
    const b=Math.min(n, a+G);                                               // 这一格 = 第 a+1〜b 个单元
    const cls = (tgt<have && tgt<b && a<have) ? 'cut' : (have<tgt && have<b && a<tgt) ? 'add'      // 这一格碰到「要卖的」/「要加的」那一段
              : (a<Math.min(have, tgt)) ? 'keep' : (a>=Math.max(capN, have)) ? 'over' : '';
    nd('i', cls, null, bar);
  }
  lab.textContent='';
  const at=(j, text, cls)=>{ const p=j/n*100, e=nd('span', cls, text, lab); e.style.left=p+'%';
    if(p<=0) e.classList.add('l'); else if(p>=100) e.classList.add('r'); };
  if(n<=8 && G===1){ for(let j=0;j<=n;j++) at(j, fmt(j*LOT), 't'); }
  else { at(0, '0', 't'); at(n, fmt(n*LOT)+' '+U, 't'); }
  const pk=Math.min(100, have/n*100), num=n<=8 ? '' : ' '+fmt(ADJ.shares);            // ▲ 对准现在的位置：左半边往右写、右半边往左写（不出框）
  const kl=nd('span', 'k', pk<=60 ? '▲现在'+num : '现在'+num+' ▲', lab);
  kl.style.left=pk+'%'; kl.style.transform = pk<=60 ? 'translateX(-6px)' : 'translateX(calc(-100% + 6px))';
  const lim = ADJ.fix ? '总权益' : ADJ.core ? '规则目标额（比例 100%）' : capLab();
  const capTxt = capN>=n ? '最右边 = '+lim
               : capN<have ? lim+' ≈ '+fmt(capN*LOT)+' '+U+'（现在已超过，只能减）'
               : lim+' ≈ '+fmt(capN*LOT)+' '+U;
  note.textContent='一格 = '+fmt(G*LOT)+' '+U+(G>1 ? '（拖动按 '+fmt(LOT)+' '+U+'一步）' : '')
    +' · 半透明 留着 · 实心 要加 · 红框 要卖 · 斜线 超过上限 · '+capTxt;
  r.setAttribute('aria-valuetext', '目标 '+fmt(tgt*LOT)+' '+U+'（'+tgt+' 个单元）；现在 '+fmt(ADJ.shares)+' '+U);
}
function adjPrev(){
  const go=$('#adj-go'), out=$('#adj-prev'), c=ADJ, cap=adjCap(), n=adjTarget();
  go.className='btn primary'; ADJ.cost=0; fundBox($('#adj-fund'), 0, c.t);
  const r=$('#adj-range'); if(n!=null) r.value=Math.min(+r.max, n);
  adjBar();
  if(n==null){ out.textContent='输入目标（'+UW()+'数 / 金额 / 占总权益 %）'; go.textContent='确认'; go.disabled=true; return; }
  if(c.fix){ adjPrevFix(n); return; }
  if(c.core){ adjPrevCore(n); return; }
  if(n===c.shares){
    out.textContent='换算还是 '+fmt(n)+' 股：不用调';
    go.textContent='确认'; go.disabled=true; return;
  }
  if(n<c.shares){
    const k=c.shares-n;
    out.textContent='卖出 '+fmt(k)+' 股（约 '+yen(k*c.px)+'）：'+fmt(c.shares)+' → '+fmt(n)+' 股，约占权益 '+pctOf(n)
      +estLine(estOf(c.t), k, '股')+'\n'+CFG.when+'卖出'+(n===0 ? '（= 全部卖出，不设「不买回」）' : '');
    go.textContent='确认卖出 '+fmt(k)+' 股'; go.className='btn danger'; go.disabled=false; return;
  }
  let t=n, note='';
  if(t>cap){ t=Math.max(cap, c.shares); note='\n★ 超过'+capLab()+'：截到 '+fmt(t)+' 股'; }
  const k=t-c.shares;
  if(k<=0){
    const full=CFG.eq>0 && c.shares*c.px/CFG.eq*100>=CFG.cap;
    out.textContent = full ? '已经到'+capLab()+'：不能再加' : '再加 '+fmt(LOT)+' 股就超过'+capLab()+'：不能再加';
    go.textContent='确认'; go.disabled=true; return;
  }
  ADJ.cost=k*c.px*1.03; fundBox($('#adj-fund'), ADJ.cost, c.t);
  out.textContent='买入 '+fmt(k)+' 股（约 '+yen(k*c.px)+'）：'+fmt(c.shares)+' → '+fmt(t)+' 股，约占权益 '+pctOf(t)+note
    +'\n'+CFG.when+'买入（最高 '+yen(c.px*1.03)+' = 收盘 ×1.03）；只做一次';
  go.textContent='确认买入 '+fmt(k)+' 股'; go.disabled=false;
}
function adjPrevFix(n){                                                    // 核心 ETF 固定口数（2026-10-11）：买入 / 卖出多少、占权益、什么时候、之后怎样
  const c=ADJ, go=$('#adj-go'), out=$('#adj-prev'), cap=adjCap(), t=Math.min(n, cap), k=t-c.shares;
  ADJ.cost = k>0 ? k*c.px : 0; fundBox($('#adj-fund'), ADJ.cost, c.t);     // 2026-10-12：买的话钱不够 → 从持仓平摊凑（同个股买入）
  const head = k>0 ? '买入 '+fmt(k)+' 口（约 '+yen(k*c.px)+'）：' : k<0 ? '卖出 '+fmt(-k)+' 口（约 '+yen(-k*c.px)+'）：' : '保持现在的口数：';
  out.textContent = head+fmt(c.shares)+' → '+fmt(t)+' 口，约 '+yen(t*c.px)+' · 约占权益 '+pctOf(t)+(n>cap ? '\n★ 超过总权益：截到 '+fmt(t)+' 口' : '')
    +'\n下一次决策起（交易日 07:40，开盘下单）正好调到 '+fmt(t)+' 口，不再按规则（牛熊 / 股债相关）自动调；一直有效，直到点「恢复按规则」。'
    +(k>0 ? '' : '\n剩下的钱照规则分给其他核心 ETF；规则不拿别的 ETF 时留现金。');
  go.textContent = k>0 ? '确认买入 '+fmt(k)+' 口' : k<0 ? '确认卖出 '+fmt(-k)+' 口' : '确认固定 '+fmt(t)+' 口';
  go.className = k<0 ? 'btn danger' : 'btn primary'; go.disabled = !(c.px>0);
}
function coreFx(q, skip, lab){                                             // 同一个比例对别的核心 ETF（规则同时拿两只以上时）：会变的列出来
  const C=CFG.cores||{}, out=[];
  for(const t of Object.keys(C)){
    if(t===skip) continue;
    const c=C[t], L=c.lot||1, tg=Math.floor(c.u100*q/100/L+1e-9)*L;
    if(tg!==c.cur && (c.cur>0 || tg>0)) out.push(t+' '+fmt(c.cur)+' → '+fmt(tg)+' 口');
  }
  return out.length ? '\n'+(lab||'★ 同一比例也用在：')+out.join('、') : '';
}
function adjPrevCore(n){                                                   // 核心 ETF：目标口数 → 闲置资金比例（之后每天按它）
  const go=$('#adj-go'), out=$('#adj-prev'), c=ADJ, cap=adjCap();
  let t=n, note='';
  if(t>cap){ t=Math.max(cap, 0); note='\n★ 超过规则目标额（比例 100%）：截到 '+fmt(t)+' 口'; }
  const q=cpctOf(t), ratio='\n闲置资金比例 '+c.cpct+'% → '+q+'%（之后每天按规则目标额 × '+q+'%）'+coreFx(q, c.t);
  if(t===c.shares){ out.textContent='现在就是 '+fmt(t)+' 口：不用调'+note; go.textContent='确认'; go.disabled=true; return; }
  if(q===c.cpct){
    out.textContent='换算成闲置资金比例还是 '+q+'%：不用调'+note; go.textContent='确认'; go.disabled=true; return;
  }
  const k=Math.abs(t-c.shares), sell=t<c.shares;
  out.textContent=(sell ? '卖出 ' : '买入 ')+fmt(k)+' 口（约 '+yen(k*c.px)+'）：'+fmt(c.shares)+' → '+fmt(t)+' 口，约占权益 '+pctOf(t)
    +(sell ? estLine(estOf(c.t), k, '口') : '')+note+ratio+'\n'+CFG.when+(sell ? '卖出' : '买入');
  go.textContent=(sell ? '确认卖出 ' : '确认买入 ')+fmt(k)+' 口'; go.className=sell ? 'btn danger' : 'btn primary'; go.disabled=false;
}
// ── 买入钱不够 → 从持仓平摊凑（2026-10-12；与 manual_orders.fund_split 同一个算法）：差额按金额平分到每只持仓，
//    不够分的卖完、剩下的再平分；个股按单元取最接近的整数单元，核心 ETF 补足剩下的 ──
let FUND_MODE = 'split';
function fundSplit(cost, skip){
  const F=CFG.fund||{}, short=cost-(F.cash||0); if(!(short>0)) return null;
  const busy=F.busy||[];
  const H=(F.hold||[]).filter(h=>h.t!==skip && busy.indexOf(h.t)<0 && h.cur>0 && h.px>0).map(h=>Object.assign({}, h));
  const by=(a,b)=>(a.cur*a.px-b.cur*b.px) || (a.t<b.t ? -1 : a.t>b.t ? 1 : 0);
  H.sort(by);
  let rem=short, k=H.length;
  for(const h of H){ h.give=Math.min(h.cur*h.px, rem/k); rem-=h.give; k--; }
  let got=0;
  for(const h of H){ h.sell=0; if(h.kind==='stock'){ h.sell=Math.min(h.cur, Math.round(h.give/h.px/h.lot)*h.lot); got+=h.sell*h.px; } }
  const cores=H.filter(h=>h.kind==='core').sort(by); let need=short-got; k=cores.length;
  for(const h of cores){ const g=Math.min(h.cur*h.px, Math.max(0, need)/k);
    h.sell=Math.min(h.cur, Math.ceil(g/h.px/h.lot-1e-9)*h.lot); need-=h.sell*h.px; k--; got+=h.sell*h.px; }
  while(got<short){
    const room=H.filter(h=>h.kind==='stock' && h.sell+h.lot<=h.cur); if(!room.length) break;
    room.sort((a,b)=>(a.lot*a.px-b.lot*b.px) || (a.t<b.t ? -1 : 1)); const h=room[0]; h.sell+=h.lot; got+=h.lot*h.px;
  }
  const rows=H.filter(h=>h.sell>0).sort((a,b)=>a.t<b.t ? -1 : 1)
    .map(h=>({t:h.t, kind:h.kind, cur:h.cur, sell:h.sell, yen:Math.round(h.sell*h.px), after:h.cur-h.sell}));
  return {short:Math.round(short), rows:rows, got:Math.round(got), left:Math.round(Math.max(0, short-got))};
}
function allocViz(el, cost, skip, p){                                       // 买入前后的仓位占比（2026-10-12）：两条按金额分段的横条 + 每只「现在 → 买入后」
  const F=CFG.fund||{}, A=CFG.alloc||{}, N=A.names||{}, C=A.colors||['#4c7bf3'];
  const now={}; for(const h of (F.hold||[])) if(h.cur>0 && h.px>0) now[h.t]=(now[h.t]||0)+h.cur*h.px;
  const order=Object.keys(now).sort((a,b)=>now[b]-now[a]); const col={}; order.forEach((t,i)=>col[t]=C[i%C.length]);
  if(skip && !(skip in col)) col[skip]=C[order.length%C.length];
  const after=Object.assign({}, now); let cash=F.cash||0;
  if(p){
    if(FUND_MODE==='split') for(const r of p.rows) after[r.t]=Math.max(0, (after[r.t]||0)-r.yen);
    else { let need=p.short; for(const t of order){ const h=(F.hold||[]).find(x=>x.t===t); if(!h || h.kind!=='core' || t===skip || need<=0) continue;
      const s=Math.min(after[t], need); after[t]-=s; need-=s; } }
    cash=Math.max(0, cash+(FUND_MODE==='split' ? p.got : p.short)-cost);
  } else cash=Math.max(0, cash-cost);
  after[skip]=(after[skip]||0)+cost;
  const keys=order.concat(skip && order.indexOf(skip)<0 ? [skip] : []);
  const tot=o=>keys.reduce((s,t)=>s+(o[t]||0), 0);
  const T0=tot(now)+(F.cash||0), T1=tot(after)+cash; if(!(T0>0) || !(T1>0)) return;
  const box=nd('div', 'fund aviz', null, el); nd('div', 'fh', '买入前后的仓位占比', box);
  const bar=(lab, o, c, T)=>{ const r=nd('div', 'avr', null, box); nd('span', 'avl muted small', lab, r); const b=nd('div', 'alb', null, r);
    for(const t of keys){ const v=o[t]||0; if(v<=0) continue; const i=nd('i', null, null, b); i.style.width=(v/T*100).toFixed(2)+'%'; i.style.background=col[t];
      if(t===skip) i.className='new'; }
    if(c>0){ const i=nd('i', null, null, b); i.style.width=(c/T*100).toFixed(2)+'%'; i.style.background='var(--muted)'; } };
  bar('现在', now, F.cash||0, T0); bar('买入后', after, cash, T1);
  const leg=nd('div', 'all', null, box);
  const line=(t, lab, a, b, c)=>{ const r=nd('div', 'alr avg', null, leg); const d=nd('span', 'ald', null, r); d.style.background=c;
    nd('span', 'aln', lab, r); const pa=a/T0*100, pb=b/T1*100;
    nd('span', 'alp'+(Math.abs(pb-pa)>=0.05 ? (pb>pa ? ' up' : ' down') : ''), pa.toFixed(1)+'% → '+pb.toFixed(1)+'%', r); };
  for(const t of keys){ if(!(now[t]>0) && !(after[t]>0)) continue;
    line(t, t.replace('.T', '')+(N[t] ? ' '+N[t] : '')+(t===skip && !(now[t]>0) ? '（新）' : ''), now[t]||0, after[t]||0, col[t]); }
  line('', '现金', F.cash||0, cash, 'var(--muted)');
}
function fundBox(el, cost, skip){                                          // 拖动 / 输入时实时更新：要卖哪几只、各卖多少
  if(!el) return; el.textContent='';
  const F=CFG.fund||{}, p=cost>0 ? fundSplit(cost, skip) : null;
  if(cost>0) allocViz(el, cost, skip, p);
  if(!p){ if(cost>0) nd('div', 'muted small', '现金约 '+yen(F.cash||0)+'：够买，不用卖别的', el); return; }
  const box=nd('div', 'fund', null, el);
  nd('div', 'fh', '现金约 '+yen(F.cash||0)+'，还差约 '+yen(p.short), box);
  const seg=nd('div', 'seg fseg', null, box);
  for(const [m, lab] of [['split', '各持仓平摊卖'], ['core', '只卖核心 ETF']]){
    const b=nd('button', null, lab, seg); b.dataset.act='fund-mode'; b.dataset.m=m; b.setAttribute('aria-pressed', FUND_MODE===m ? 'true' : 'false'); }
  if(FUND_MODE==='core'){ nd('div', 'muted small', '执行器按当时还缺多少卖核心 ETF（原来的做法）；核心 ETF 不够 → 少买', box); return; }
  if(!p.rows.length){ nd('div', 'neg small', '没有能卖来凑的持仓（都有没处理完的指令 / 规则在卖）：执行器会少买', box); return; }
  const mx=Math.max.apply(null, p.rows.map(r=>r.yen));
  for(const r of p.rows){
    const row=nd('div', 'frow', null, box), U=r.kind==='core' ? '口' : '股';
    nd('span', 'ft', r.t.replace('.T', '')+(r.kind==='core' ? ' ETF' : ''), row);
    const bar=nd('span', 'fbar', null, row); nd('i', null, null, bar).style.width=(r.yen/mx*100).toFixed(0)+'%';
    nd('span', 'fv', '卖 '+fmt(r.sell)+' '+U+' ≈ '+yen(r.yen), row);
    nd('div', 'muted small fsub', fmt(r.cur)+' → '+fmt(r.after)+' '+U+(r.after===0 ? '（全部卖出）' : ''), row);
  }
  nd('div', 'muted small', '合计约 '+yen(p.got)+(p.left>0 ? '，还差 '+yen(p.left)+' → 执行器会少买' : '')
    +' · 按最近收盘估算，个股按 100 股取整', box);
}
function fundBody(body, cost){ if(FUND_MODE==='split' && cost>0 && fundSplit(cost, body.ticker)) body.fund={mode:'split', cost:Math.round(cost)}; return body; }
// ── 买入（建议的股票 → 手动买入指令）：按规则的仓位 / 股数 / 金额 / 占权益 %；执行器下单时按当时的价格再算 ──
export let BUY = null;
const bpct = n => CFG.eq>0 && BUY.px>0 ? (n*BUY.px/CFG.eq*100).toFixed(1)+'%' : '—';
function buyCap(){ return BUY.px>0 && CFG.eq>0 ? Math.floor(CFG.eq*CFG.cap/100/BUY.px/BUY.lot+1e-9)*BUY.lot : 0; }
function buyTarget(){
  if(BUY.unit==='rule') return BUY.rule;
  const v=parseFloat($('#buy-val').value); if(!(v>0) || !isFinite(v)) return null;
  let raw; if(BUY.unit==='shares') raw=v; else if(!(BUY.px>0)) return null; else if(BUY.unit==='yen') raw=v/BUY.px; else raw=CFG.eq*v/100/BUY.px;
  return Math.max(0, Math.floor(raw/BUY.lot+1e-9)*BUY.lot);
}
function buyShow(n){
  const u=BUY.unit, e=$('#buy-val');
  e.value = u==='shares' ? n : u==='yen' ? Math.round(n*BUY.px) : (CFG.eq>0 ? (n*BUY.px/CFG.eq*100).toFixed(1) : 0);
}
function buyUnit(u){
  let n=buyTarget(); BUY.unit=u;
  if(n!=null) n=Math.min(n, Math.max(buyCap(), BUY.lot));            // 换单位时不把超过单只上限的数带过去
  document.querySelectorAll('#buy-seg button').forEach(b=>b.setAttribute('aria-pressed', b.dataset.u===u ? 'true' : 'false'));
  $('#buy-row').hidden = u==='rule';
  if(u!=='rule'){
    $('#buy-unit').textContent = {shares:'股', yen:'円', pct:'%'}[u];
    $('#buy-val').step = u==='shares' ? BUY.lot : u==='yen' ? 1000 : 0.1;
    buyShow(n==null || n<=0 ? (BUY.rule || BUY.lot) : n);
  }
  buyPrev();
}
function buyPrev(){
  const go=$('#buy-go'), out=$('#buy-prev');
  let n=buyTarget();
  if(n==null){ out.textContent='输入要买多少（股数 / 金额 / 占总权益 %）'; go.textContent='确认买入'; go.disabled=true; return; }
  const cap=buyCap(); let note='';
  if(n>cap){ n=cap; note='\n★ 超过'+capLab()+'：截到 '+fmt(n)+' 股'; }
  if(n<=0){
    fundBox($('#buy-fund'), 0, BUY.t);
    out.textContent = BUY.unit==='rule' ? '按规则的仓位不够买 1 个单元（'+fmt(BUY.lot)+' 股 ≈ '+yen(BUY.lot*BUY.px)+'）：改用股数 / 金额试试'
      : '不够 1 个单元（'+fmt(BUY.lot)+' 股 ≈ '+yen(BUY.lot*BUY.px)+'）';
    go.textContent='确认买入'; go.disabled=true; return;
  }
  const br=$('#buy-range'); if(br) br.value=n;
  BUY.cost=n*(BUY.limit||BUY.px*1.03); fundBox($('#buy-fund'), BUY.cost, BUY.t);
  out.textContent='买入约 '+fmt(n)+' 股 · 约 '+yen(n*BUY.px)+' · 约占权益 '+bpct(n)+note
    +'\n'+CFG.when+'买入（最高 '+yen(BUY.limit||BUY.px*1.03)+' = 收盘 ×1.03）；名额满 / 价格更高 → 不买；只做一次';
  go.textContent='确认买入约 '+fmt(n)+' 股'; go.disabled=false;
}
document.addEventListener('input', e=>{
  if(e.target.id==='core-pct') coreShow();
  if(e.target.id==='adj-val') adjPrev();
  if(e.target.id==='adj-range'){ adjShow(+e.target.value); adjPrev(); }
  if(e.target.id==='buy-val') buyPrev();
  if(e.target.id==='buy-range'){ const v=+e.target.value;                // 先记下拖到的位置（换单位时 buyPrev 会把拖动条拨回旧的股数）
    if(BUY.unit!=='shares') buyUnit('shares'); buyShow(v); buyPrev(); }
});
document.addEventListener('DOMContentLoaded', ()=>{ const d=$('#dlg-ask'); if(d) d.addEventListener('close', ()=>{ if(ASK){ const r=ASK; ASK=null; r({ok:false}); } }); });
document.addEventListener('keydown', e=>{ const b=e.target;                // 「点这里再试」也能用键盘（Enter / 空格）
  if((e.key==='Enter' || e.key===' ') && b && b.matches && b.matches('.chart[data-retry]')){ e.preventDefault(); b.click(); } });
document.addEventListener('click', async e=>{
  if(e.target.closest('#toast')){ $('#toast').hidden=true; return; }       // 提示：点一下关闭
  const rk=e.target.closest('.chart[data-retry]');
  if(rk){ rk.removeAttribute('data-retry'); showK(rk); return; }           // K 线取不到 / 超时：点一下再取（同一只票已经在取 → 等那一个）
  const b=e.target.closest('[data-act]'); if(!b) return;
  const a=b.dataset.act, d=b.dataset;
  if(a==='reload'){ reloadPage(b, '刷新中…'); return; }
  if(a==='close'){ closeAll(); return; }
  if(a==='ask-ok'){ const v=$('#ask-input').value, r=ASK; ASK=null; closeAll(); if(r) r({ok:true, value:v}); return; }
  if(a==='sell'){
    CUR={t:d.t, shares:+d.shares};
    $('#sell-title').textContent='卖出 '+d.t+(d.name?' '+d.name:'');
    $('#sell-desc').textContent='全部 '+fmt(+d.shares)+' 股 · '+CFG.when+'卖出'+NOTE;
    plBox($('#sell-pl'), estOf(d.t));                                      // 买入成交价 → 现价 / 预计卖出 → 预计收益与收益率
    sheet('#dlg-sell'); return;
  }
  if(a==='sell-go'){
    const bd=document.querySelector('input[name=bd]:checked').value; closeAll();
    done(await api('/api/request',{book:CFG.book, kind:'sell', ticker:CUR.t, block_days:parseInt(bd,10)})); return;
  }
  if(a==='adj'){
    const core=d.core==='1';
    ADJ={t:d.t, shares:+d.shares, px:+d.px, unit:'shares', core:core, lot:core ? (+d.lot||1) : LOT, u100:+d.u100||0, cpct:+d.cpct||0, approx:d.approx==='1'};
    $('#adj-title').textContent='调仓 '+d.t+(d.name?' '+d.name:'');
    $('#adj-cur').textContent='现在 '+fmt(ADJ.shares)+' '+UW()+' · 约 '+yen(ADJ.shares*ADJ.px)+' · 约占权益 '+pctOf(ADJ.shares)
      +(core ? ' · 闲置资金比例 '+ADJ.cpct+'%' : '');
    $('#adj-u-sh').textContent=UW()+'数';
    const ru=$('#adj-rule'); if(ru){ if(ADJ_RULE==null) ADJ_RULE=ru.innerHTML;
      if(core) ru.textContent='核心 ETF 按「闲置资金比例」调：比例 = 目标 ÷ 规则目标额（最右边 = 100% = 照规则）；之后每天按这个比例，改回 100% 就照规则。'
        +(ADJ.approx ? '规则目标额执行器还没算过：100% 先按现在的口数估算，下一次决策用准确的数（口数可能再小调）。' : '')+NOTE.trim();
      else { ru.innerHTML=ADJ_RULE; $('#adj-cap').textContent=CFG.cap; } }
    $('#adj-val').value='';                                                // 从这只票现在的股数开始（不带上一只票输过的数）
    const L=ALOT(), r=$('#adj-range'); r.max=Math.max(1, Math.ceil(Math.max(adjCap(), ADJ.shares, L)/L))*L; r.step=L; r.value=ADJ.shares;   // 整数个单元
    adjUnit('shares'); sheet('#dlg-adj'); return;
  }
  if(a==='core-sell'){
    const q=await ask('卖出全部 '+d.t+(d.name?' '+d.name:''), '全部 '+fmt(+d.shares)+' 口：'+CFG.when+'卖出'+coreFx(0, d.t)
      +'\n卖出后停买闲置资金 ETF（钱留现金）；出现买入信号会提醒你，你点「确认买入」才买'+NOTE, '卖出', {danger:true, pl:estOf(d.t)});
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'sell', ticker:d.t})); return;
  }
  if(a==='core-resume'){                                                   // 停买后确认买入：闲置资金比例 0% → 100%（照规则）
    const q=await ask('确认买入：恢复闲置资金买入 ETF', '闲置资金比例 0% → 100%（照规则）'+coreFx(100, '', '会买：')
      +'\n'+CFG.when+'买入；之后每天照规则调'+NOTE, '确认买入');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'core', pct:100})); return;
  }
  if(a==='adj-unit'){ adjUnit(d.u); return; }
  if(a==='fund-mode'){ FUND_MODE=d.m; if($('#dlg-buy').open) buyPrev(); else adjPrev(); return; }
  if(a==='adj-step'){ const n=adjTarget(); adjShow(Math.max(0, (n==null ? ADJ.shares : n)+(+d.d)*ALOT())); adjPrev(); return; }
  if(a==='adj-go'){
    if(ADJ && ADJ.fix){ const n=adjTarget(); if(n==null) return; const u=Math.min(n, adjCap());
      closeAll(); done(await api('/api/request', fundBody({book:CFG.book, kind:'corefix', ticker:ADJ.t, units:u}, u>ADJ.shares ? (u-ADJ.shares)*ADJ.px : 0))); return; }
    const n=adjTarget(); if(n==null || n===ADJ.shares) return;
    const v = ADJ.unit==='shares' ? n : parseFloat($('#adj-val').value);
    closeAll(); done(await api('/api/request', fundBody({book:CFG.book, kind:'adjust', ticker:ADJ.t, unit:ADJ.unit, value:v}, n>ADJ.shares ? ADJ.cost||0 : 0))); return;
  }
  if(a==='ktf' || a==='ksub'){                                            // 一张图自己的周期 / 小图（别的图不变）；也记成新打开的图的默认
    const bx=b.closest('.chart[data-t]'); if(!bx || !(a==='ktf' ? TFS : SUBS)[d.v]) return;
    if(a==='ktf'){ setTF(d.v); bx.dataset.tf=d.v; try{ localStorage.setItem('qbreak.tf', d.v); }catch(x){} }   // 模块之间不能直接给别的模块的变量赋值 → setTF
    else { setSUB(d.v); bx.dataset.sub=d.v; try{ localStorage.setItem('qbreak.sub', d.v); }catch(x){} }
    drawK(bx);
    const nb=bx.querySelector('[data-act="'+a+'"][data-v="'+d.v+'"]'); if(nb) nb.focus({preventScroll:true});   // 重画后焦点留在刚按的按钮上（键盘用）
    return;
  }
  if(a==='buy'){
    BUY={t:d.t, px:+d.px, lot:+d.lot||LOT, rule:+d.rule||0, limit:+d.limit||0, unit:'rule'};
    $('#buy-title').textContent='买入 '+d.code+(d.name ? ' '+d.name : '');
    $('#buy-sig').textContent=(d.sig==='1' ? '今天出了买入信号（'+d.rtext+'）' : '★ '+d.status+'：还没有买入信号，规则不会买 —— 是你自己的决定')
      +(d.warn ? '\n★ '+d.warn : '')+NOTE;
    $('#buy-cap').textContent=CFG.cap;
    { const r=$('#buy-range'), L=BUY.lot; r.min=L; r.step=L; r.max=Math.max(L, buyCap()); }
    buyUnit('rule'); sheet('#dlg-buy'); buyLive(); loadSQ(); return;            // 现价 + 现在买按什么价（Yahoo，约晚 20 分钟）
  }
  if(a==='buy-unit'){ buyUnit(d.u); return; }
  if(a==='buy-step'){ if(BUY.unit!=='rule'){ const n=buyTarget(); buyShow(Math.max(BUY.lot, (n==null||n<=0 ? BUY.lot : n)+(+d.d)*BUY.lot)); } buyPrev(); return; }
  if(a==='buy-go'){
    const n=buyTarget(); if(!n) return;
    const body={book:CFG.book, kind:'buy', ticker:BUY.t, unit:BUY.unit};
    if(BUY.unit!=='rule') body.value = BUY.unit==='shares' ? Math.min(n, buyCap()) : parseFloat($('#buy-val').value);
    closeAll(); done(await api('/api/request', fundBody(body, BUY.cost||0))); return;
  }
  if(a==='core-step'){ const r=$('#core-pct'); r.value=Math.max(0, Math.min(100, parseFloat(r.value)+parseFloat(d.d))); coreShow(); return; }
  if(a==='core'){
    const v=parseFloat($('#core-pct').value);
    const q=await ask('闲置资金比例 '+v+'%', '核心 ETF 的目标额 = 规则算出的 × '+v+'%，下一次决策起生效'+(v<100?'（多出来的留现金）':'')+NOTE, '保存');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'core', pct:v})); return;
  }
  if(a==='cancel-order'){                                                 // 撤单：执行器今天已经发到交易所、还挂着的单（面板马上叫执行器撤）
    const q=await ask('撤单 '+(d.side==='BUY'?'买 ':'卖 ')+d.t+' '+fmt(+d.qty)+(d.core==='1'?' 口':' 股'),
      (d.core==='1' ? '核心 ETF 的单：已经成交的部分撤不了；下一次决策照规则 / 闲置资金比例重新算目标，可能再买 / 再卖（要少拿用「闲置资金比例」）。'
                    : '已经成交的部分撤不了；撤掉的卖单如果规则明天还要卖会再下；撤掉的个股买单不再买。')+(CFG.paper ? '' : '\n马上发撤单到立花（之后看「今天的单」的状态）'),
      '撤单', {danger:true});
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'cancel_order', cid:d.cid})); return;
  }
  if(a==='cancel'){                                                       // 撤单前一定确认（2026-10-12 用户：防止误撤）：写清撤的是哪一条
    const q=await ask('确认撤单？', (d.desc||d.id)+'\n\n'+(d.placed==='1' ? '之后不再下。已经发到交易所的单用「今天的单」的「撤单」撤。' : '还没下单：撤掉之后不会下。')
      +(+d.fund>0 ? '\n为这笔买入凑钱的 '+d.fund+' 条卖出也一起撤掉。' : '')+'\n（指令 '+d.id+'）', '确认撤单', {danger:true});
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'cancel', target:d.id})); return;
  }
  if(a==='uncancel'){                                                     // 撤销一条撤回（2026-10-12）：原来的指令恢复「等下单」、撤回记录不再显示
    const q=await ask('撤销这条撤回？', (d.desc||d.id)+'\n\n撤销之后，原来的指令恢复「等下单」，照原来的时间处理；这条撤回不再显示。\n（指令 '+d.id+'）', '撤销撤回');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'uncancel', target:d.id})); return;
  }
  if(a==='corefix' || a==='corefix-clear'){                               // 核心 ETF 固定口数 / 恢复按规则（2026-10-11）
    const px=+d.px||0, lot=+d.lot||1, eq=+d.eq||0, cur=+d.cur||0;
    if(a==='corefix-clear'){
      const q=await ask(d.name+'：恢复按规则', '下一次决策起，这只 ETF 又按规则（美股牛熊 / 股债相关）自动买卖。'+NOTE, '恢复');
      if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'corefix', ticker:d.t, clear:true})); return;
    }
    ADJ={t:d.t, shares:cur, px:px, unit:'shares', core:true, fix:true, lot:lot, u100:0, cpct:0, approx:false, name:d.name};
    $('#adj-title').textContent=(cur>0 ? '固定口数 ' : '买入 ')+d.t+(d.name?' '+d.name:'');
    $('#adj-cur').textContent='现在 '+fmt(cur)+' 口 · 约 '+yen(cur*px)+' · 约占权益 '+pctOf(cur)+' · 收盘 ¥'+px+' · 一个单元 '+fmt(lot)+' 口';
    $('#adj-u-sh').textContent='口数';
    const ru=$('#adj-rule'); if(ru){ if(ADJ_RULE==null) ADJ_RULE=ru.innerHTML;
      ru.textContent='拖动滑条或输入目标（口数 / 金额 / 占总权益 %），按单元（'+fmt(lot)+' 口）取整；最右边 = 总权益全部。'+NOTE.trim(); }
    $('#adj-val').value='';
    const r=$('#adj-range'); r.max=Math.max(1, Math.ceil(Math.max(adjCap(), cur, lot)/lot))*lot; r.step=lot; r.value=cur;
    adjUnit('shares'); sheet('#dlg-adj'); return;
  }
  if(a==='unblock'){
    const q=await ask('解除 '+d.t+' 的不自动买回', '之后有买入信号就会按规则买。', '解除');
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'unblock', ticker:d.t})); return;
  }
  if(a==='flow'){                                                         // 〔77〕C UX-14：登记入金 / 出金（只影响收益的计算）
    const v=($('#flow-jpy').value||'').replace(/[,¥\s]/g,''), n=+v;
    if(!v || !isFinite(n) || Math.abs(n)<1){ toast('金额：入金写正数、出金写负数（例 300000 / -300000）', true); return; }
    const rs=!!($('#flow-reserve')||{}).checked && n<0;
    const q=await ask((n>0?'登记入金 ':'登记出金 ')+(n>0?'+':'−')+'¥'+fmt(Math.abs(n))+(rs?'（预留）':''), '日期 '+($('#flow-date').value||'今天')+'。'+(rs ? '预留：到账前的决策按扣掉这笔钱算（个股仓位变小、闲置资金 ETF 不买回；现金不够先卖核心 ETF）；到账后自动解除。' : '只影响收益的计算与「现金突然变化」的提醒，不下单。'), '登记');
    const rsv=!!($('#flow-reserve')||{}).checked;
    if(rsv && n>0){ toast('预留只用于出金（写负数）', true); return; }
    if(q.ok) done(await api('/api/request',{book:CFG.book, kind:'flow', jpy:n, date:$('#flow-date').value, note:$('#flow-note').value, reserve:rsv})); return;
  }
  if(a==='halt'){
    const q=await ask('停止下单（HALT）', '全部账本（模拟和立花）从下一次运行起不下单、持仓不动。\n已经发到交易所的单不会被撤（要撤：「今天的单」的「撤单」，或立花网站 / 手机网站）。\n这里只能停：恢复只在 Mac 上（在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」）。', '停止下单', {danger:true, input:'原因（可不填）'});
    if(q.ok) done(await api('/api/halt',{reason:q.value})); return;
  }
  if(a==='pair-new'){
    const j=await api('/api/pair/new',{}); if(!j) return;
    $('#pair-code').textContent=j.code; $('#pair-exp').textContent=j.expires+' JST 前有效（只能用一次；输错 5 次作废）';
    const img=$('#pair-qr'); if(j.qr){ img.src=j.qr; img.hidden=false; } else img.hidden=true;
    $('#pair-url').textContent = j.url ? '手机：用相机扫二维码，或 Safari 打开 '+j.url+' 输入上面的配对码' : '手机访问还没打开：先在 Mac 的 Claude 对话里说「打开手机操作」（bash scripts/liveu.sh phone on），手机才连得上';
    $('#pair-box').hidden=false; return;
  }
  if(a==='revoke'){
    const q=await ask('取消「'+d.name+'」的配对', '这台设备之后打不开面板（要用的话重新配对）。', '取消配对', {danger:true});
    if(q.ok) done(await api('/api/device/revoke',{id:d.id})); return;
  }
  if(a==='unpair'){
    const q=await ask('退出这台设备', '之后这台设备要重新配对才能打开（在 Mac 的操作面板上生成配对码）。', '退出', {danger:true});
    if(q.ok){ const j=await api('/api/unpair',{}); if(j){ toast(j.msg); setTimeout(()=>location.reload(), 1200); } } return;
  }
});
