// qbreak 操作面板：trade.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/trade.js 提供；不要用构建工具）
import { $, CFG, NOTE, api, closeAll, coreShow, done, estLine, fmt, nameify, nd, plBox, reloadPage, sheet, tlab, toast, tqty, yen } from './core.js';
import { SUBS, TFS, drawK, setSUB, setTF, showK } from './kline.js';
import { buyLive, estOf, loadSQ } from './quotes.js';

let ASK=null, CUR=null;
function ask(title, body, okText, opt){
  opt=opt||{}; $('#ask-title').textContent=nameify(title); $('#ask-body').textContent=nameify(body); plBox($('#ask-pl'), opt.pl||null);   // 代码带名字（2026-10-15 用户：「只有股票代号的话不知道是哪个股票」）
  const ok=$('#ask-ok'); ok.textContent=okText||'确定'; ok.className='btn '+(opt.danger?'danger':'primary');
  const no=$('#ask-no'); if(no) no.textContent=opt.cancel||'取消';         // 「取消下单」（确认下单框；2026-10-15）/ 平时「取消」
  const inp=$('#ask-input'); inp.hidden=!opt.input; inp.value=''; inp.placeholder=opt.input||'';
  const alts=opt.alt||[], box=$('#ask-alts');                              // 另外的选择（撤凑钱的卖单：只撤卖单 / 撤单并恢复按规则；D2，2026-10-15）→ {ok:true, alt:v}
  ['#ask-alt','#ask-alt2'].forEach((id,i)=>{ const b=$(id); if(!b) return; const x=alts[i];
    b.hidden=!x; if(x){ b.textContent=nameify(x.text); b.dataset.v=x.v; b.className='btn'+(x.danger?' danger':''); } });
  if(box) box.hidden=!alts.length;
  sheet('#dlg-ask'); const bd=$('#ask-body'); if(bd) bd.scrollTop=0;      // 说明从头看起（上一个框滚过的位置不带过来）
  return new Promise(res=>{ ASK=res; });
}
// 写一条手动指令（2026-10-15 用户：「盘中固定口数点击确定的话要出现确认下单和取消下单的确认，不要直接下单」）：服务器说要先确认
// （固定口数 / 恢复按规则：need_confirm + 服务器算好的「要下什么单、什么时候、按什么价、钱够不够卖哪几只」）→ 弹框，
// 点「确认下单」才带上 token 再发一次（服务器重算一样才写；账本 / 时间段变了 → 再给一次新的确认框）；「取消下单」什么都不写。
async function post(body){
  let j=await api('/api/request', body);
  for(let n=0; j && j.need_confirm; n++){
    const c=j.confirm||{};
    if(n>=3 || !c.token){ toast((j.msg||'没写')+'\n（情况一直在变：刷新页面后再试）', true, true); return null; }
    const q=await ask(c.title||'确认下单', (c.changed ? '★ 刚才看到的内容变了（账本更新 / 过了时间段），这是最新的：\n\n' : '')+(c.text||'')+NOTE,
                      '确认下单', {cancel:'取消下单', danger:!!c.danger});
    if(!q.ok){ toast('已取消：什么都没写，不会下单'); return null; }
    j=await api('/api/request', Object.assign({}, body, {confirm:c.token}));
  }
  return j;
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
    +'\n什么时候：'+(CFG.when_fix||'下一次决策（交易日 07:40）→ 那天 09:00 开盘')+'；正好调到 '+fmt(t)+' 口，之后不再按规则（牛熊 / 股债相关）自动调；一直有效，直到点「恢复按规则」。'   // D1（2026-10-15）：与执行器同一个时段口径
    +(k>0 ? fixFundNote(k*c.px, c.t) : '\n剩下的钱照规则分给其他核心 ETF；规则不拿别的 ETF 时留现金。')
    +'\n点「确定」→ 先列出要下的单（哪几只、多少口、什么时候、按什么价），再点「确认下单」才写。';   // 2026-10-15
  go.textContent = k>0 ? '确定：买入 '+fmt(k)+' 口' : k<0 ? '确定：卖出 '+fmt(-k)+' 口' : '确定：固定 '+fmt(t)+' 口';
  go.className = k<0 ? 'btn danger' : 'btn primary'; go.disabled = !(c.px>0);
}
function fixFundNote(cost, skip){                                         // 固定口数加口数、现金不够（2026-10-13）：别的（不固定的）核心 ETF 能卖多少
  const F=CFG.fund||{}, C=CFG.cores||{}, fix=F.fix||[], short=cost-(F.cash||0);
  if(!(short>0)) return '';
  let need=short;                                                          // 平摊卖：个股那份写成卖出指令，核心 ETF 那份由执行器卖
  if(FUND_MODE==='split'){ const p=fundSplit(cost, skip); need=p ? p.rows.filter(r=>r.kind==='core').reduce((a,r)=>a+r.yen, 0)+p.left : short; }
  if(!(need>0)) return '';
  const q=F.core_pct==null ? 100 : F.core_pct; let room=0;
  for(const h of (F.hold||[])){                                            // 决策：最多卖到它们自己的规则目标（目标 = 规则目标额 × 闲置资金比例）
    if(h.kind!=='core' || h.t===skip || fix.indexOf(h.t)>=0 || !(h.cur>0) || !(h.px>0)) continue;   // 盘中（D1）：按缺多少卖，最多卖光
    const c=C[h.t], L=h.lot||1, tg=CFG.fix_now ? 0 : (c ? Math.floor(c.u100*q/100/L+1e-9)*L : h.cur);
    room+=Math.max(0, h.cur-tg)*h.px;
  }
  if(CFG.fix_now) return room>=need
    ? '\n现金不够的约 '+yen(need)+'：执行器盘中先卖没固定的核心 ETF 补足（大的先卖、按缺多少卖），卖出成交后再买'
    : '\n★ 钱可能不够：还差约 '+yen(need)+'，没固定的核心 ETF 全卖也只有约 '+yen(room)+' → 执行器按当时的钱少买';
  return room>=need
    ? '\n现金不够的约 '+yen(need)+'：执行器在那次决策里先卖别的核心 ETF 补足（在再平衡带以内也卖，最多卖到它们的规则目标）'
    : '\n★ 钱可能不够：还差约 '+yen(need)+'，别的核心 ETF 最多能卖约 '+yen(room)+'（只卖到它们的规则目标）→ 执行器按当时的钱少买';
}
function coreFx(q, skip, lab){                                             // 同一个比例对别的核心 ETF（规则同时拿两只以上时）：会变的列出来
  const C=CFG.cores||{}, out=[];
  for(const t of Object.keys(C)){
    if(t===skip) continue;
    const c=C[t], L=c.lot||1, tg=Math.floor(c.u100*q/100/L+1e-9)*L;
    if(tg!==c.cur && (c.cur>0 || tg>0)) out.push(tqty(t, fmt(c.cur)+' → '+fmt(tg)+' 口')+(lab ? (tg>c.cur ? '（买）' : '（卖）') : ''));
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
let FUND_MODE = 'split', FUND_PREV = 'split';                             // 'split' 各持仓平摊卖 / 'core' 只卖核心 ETF / 'all' 其他全部卖出（买入拖到最大时自动；2026-10-13）
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
  const F=CFG.fund||{}, A=CFG.alloc||{}, N=Object.assign({}, CFG.names||{}, A.names||{}), C=A.colors||['#4c7bf3'];
  const now={}; for(const h of (F.hold||[])) if(h.cur>0 && h.px>0) now[h.t]=(now[h.t]||0)+h.cur*h.px;
  const order=Object.keys(now).sort((a,b)=>now[b]-now[a]); const col={}; order.forEach((t,i)=>col[t]=C[i%C.length]);
  if(skip && !(skip in col)) col[skip]=C[order.length%C.length];
  const after=Object.assign({}, now); let cash=F.cash||0;
  if(p && p.all){                                                          // 其他全部卖出：买入后只有这只 + 现金
    for(const r of p.rows) after[r.t]=0;
    cash=Math.max(0, cash+p.got-p.buy); after[skip]=(after[skip]||0)+p.buy;
  } else {
    if(p){
      if(FUND_MODE==='split') for(const r of p.rows) after[r.t]=Math.max(0, (after[r.t]||0)-r.yen);
      else { let need=p.short; for(const t of order){ const h=(F.hold||[]).find(x=>x.t===t); if(!h || h.kind!=='core' || t===skip || need<=0) continue;
        const s=Math.min(after[t], need); after[t]-=s; need-=s; } }
      cash=Math.max(0, cash+(FUND_MODE==='split' ? p.got : p.short)-cost);
    } else cash=Math.max(0, cash-cost);
    after[skip]=(after[skip]||0)+cost;
  }
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
function fundSeg(seg, withAll){                                            // 凑钱方式的三个按钮（「其他全部卖出」只在买入框里有）
  const opts=[['split', '各持仓平摊卖'], ['core', '只卖核心 ETF']]; if(withAll) opts.push(['all', '其他全部卖出']);
  for(const [m, lab] of opts){ const b=nd('button', null, lab, seg); b.dataset.act='fund-mode'; b.dataset.m=m; b.setAttribute('aria-pressed', FUND_MODE===m ? 'true' : 'false'); }
}
function fundAll(skip, px, lot){                                           // 其他全部卖出：除这只以外能卖的持仓全部 → 0；估计全卖之后买得起几股（照执行器的口径粗算：扣滑点、手续费、1% 缓冲）
  const F=CFG.fund||{}, busy=F.busy||[], exiting=F.exiting||[], selling=F.selling||[], rows=[], keep=[]; let got=0;
  for(const h of (F.hold||[])){
    if(h.t===skip || !(h.cur>0)) continue;
    if(!(h.px>0)){ keep.push({t:h.t, kind:h.kind, cur:h.cur, yen:0, why:'没有收盘价：执行器跑过一次再试'}); continue; }
    const y=Math.round(h.cur*h.px), already=exiting.indexOf(h.t)>=0 ? '规则已在卖出全部' : selling.indexOf(h.t)>=0 ? '已有卖出全部的指令' : '';
    if(busy.indexOf(h.t)>=0 && !already){ keep.push({t:h.t, kind:h.kind, cur:h.cur, yen:y, why:'有没处理完的指令：先撤回它'}); continue; }   // 提交时会拦下
    rows.push({t:h.t, kind:h.kind, cur:h.cur, sell:h.cur, yen:y, after:0, note:already}); got+=y;
  }
  rows.sort((a,b)=>b.yen-a.yen);
  const cash=F.cash||0, avail=Math.floor((cash/0.99)+got*0.995);          // 不留 1% 现金缓冲（2026-10-13 用户）：现金（缓冲前）+ 卖出（扣滑点 / 手续费约 0.5%）
  const n=px>0 && lot>0 ? Math.floor(avail/(px*1.005)/lot)*lot : 0;
  return {all:true, rows:rows, keep:keep, got:Math.round(got), cash:Math.round(cash), avail:avail, n:n, buy:Math.round(n*px), left:Math.max(0, avail-Math.round(n*px))};
}
function fundAllBox(el, skip, q, only){                                     // 「其他全部卖出」那一块：每只 → 0、核心 ETF 比例 → 0%、合计、能买几股
  const F=CFG.fund||{};
  allocViz(el, q.buy, skip, q);
  const box=nd('div', 'fund', null, el);
  nd('div', 'fh', '其他持仓全部卖出，只拿这只 + 现金', box);
  nd('div', 'muted small', '执行时拿着的这只以外的个股和 ETF 全部卖出（包括写指令之后规则 / 别的指令买进的）；下面是现在拿着的', box);   // 2026-10-13：执行时再扫一遍
  if(only) nd('div', 'muted small', '个股名额已满：只能这样买（其他全部卖出）', box);
  else fundSeg(nd('div', 'seg fseg', null, box), true);
  for(const r of q.rows){
    const row=nd('div', 'frow', null, box), U=r.kind==='core' ? '口' : '股';
    nd('span', 'ft', r.t.replace('.T', '')+(r.kind==='core' ? ' ETF' : ''), row);
    const bar=nd('span', 'fbar', null, row); nd('i', null, null, bar).style.width='100%';
    nd('span', 'fv', '卖 '+fmt(r.sell)+' '+U+' ≈ '+yen(r.yen), row);
    nd('div', 'muted small fsub', (fnm(r.t) ? fnm(r.t)+' · ' : '')+fmt(r.cur)+' → 0 '+U+'（'+(r.note || '全部卖出')+'）', row);
  }
  for(const r of q.keep){
    const row=nd('div', 'frow', null, box);
    nd('span', 'ft', r.t.replace('.T', ''), row); nd('span', 'fbar', null, row);
    nd('span', 'fv neg', '留着', row);
    nd('div', 'muted small fsub', (fnm(r.t) ? fnm(r.t)+' · ' : '')+r.why+'（提交会被拦下）', row);
  }
  const cp=F.core_pct==null ? 100 : F.core_pct;
  if(cp>0) nd('div', 'small', '闲置资金比例 '+cp+'% → 0%：核心 ETF 卖出全部、之后停买（出现买入信号只提醒，你点「确认买入」才恢复）', box);
  if((F.fix||[]).length) nd('div', 'small', '取消固定口数：'+F.fix.map(x=>tlab(x)).join('、')+'（之后按比例 0% 卖出）', box);
  nd('div', 'muted small', '卖出合计约 '+yen(q.got)+' + 现金约 '+yen(q.cash)+rsvTxt()+' → 可用约 '+yen(q.avail)
    +(q.n>0 ? '；买 '+fmt(q.n)+' 股 ≈ '+yen(q.buy)+'，剩现金约 '+yen(q.left) : '；不够 1 个单元：不买、留现金')
    +' · 按最近收盘估算（税和手续费另计）；执行器在早上的决策里按全卖之后的钱再算', box);
  nd('div', 'muted small', '整批在 '+(CFG.when_all||'下一次决策')+' 一起做：先过闸门（决算前 / 资格 / 名额），再先卖后买；被挡则整批不做、什么都不动。'
    +'开盘跳空 / 没成交则其他已卖、留现金、不自动重买。卖出的个股 '+(CFG.block_days||20)+' 个交易日内规则不自动买回（「交易」里可一次「恢复按规则」）；规则对别的票仍可能用现金开新仓。'
    +(CFG.real ? '立花：卖出所得何时能用于买入未验证（买单等同批卖单成交到 09:20），买到的可能比预览少。' : ''), box);
}
function fnm(t){                                                          // 凑钱那几行的名字（.ft 窄格只放代码，名字写在下面的小字里；2026-10-15）
  const h=((CFG.fund||{}).hold||[]).find(x=>x.t===t); return (CFG.names||{})[t] || (h && h.name) || ''; }
function rsvTxt(){ const r=(CFG.fund||{}).reserve||0; return r>0 ? '（已扣出金预留 '+yen(r)+'）' : ''; }   // 立花：出金预留不拿来买（执行器同一口径；2026-10-14 G4）
function fundBox(el, cost, skip, opt){                                     // 拖动 / 输入时实时更新：要卖哪几只、各卖多少（opt：买入框才有 → 可选「其他全部卖出」）
  if(!el) return; el.textContent='';
  if(FUND_MODE==='all' && opt){ fundAllBox(el, skip, opt.q, !!opt.only); return; }
  const F=CFG.fund||{}, p=cost>0 ? fundSplit(cost, skip) : null;
  if(cost>0) allocViz(el, cost, skip, p);
  if(!p){
    if(cost>0) nd('div', 'muted small', '现金约 '+yen(F.cash||0)+rsvTxt()+'：够买，不用卖别的', el);
    else if(opt){                                                           // 买入框：输入不够 1 个单元 / 权益买不起 1 个单元 → 仍能选「其他全部卖出」
      const box=nd('div', 'fund', null, el), none=!(opt.cap>0);
      nd('div', 'fh', none ? '总权益按收盘价买不起 1 个单元' : '输入的数不够 1 个单元', box);
      fundSeg(nd('div', 'seg fseg', null, box), true);
      nd('div', 'muted small', none ? '选「其他全部卖出」= 其他持仓全部卖出、留现金、不买这只（下单时价格变了买得起才买）'
                                    : '选「其他全部卖出」= 其他持仓全部卖出，按全卖之后的钱买这只', box);
    }
    return;
  }
  const box=nd('div', 'fund', null, el);
  nd('div', 'fh', '现金约 '+yen(F.cash||0)+rsvTxt()+'，还差约 '+yen(p.short), box);
  fundSeg(nd('div', 'seg fseg', null, box), !!opt);
  if(FUND_MODE==='core'){ nd('div', 'muted small', '执行器按当时还缺多少卖核心 ETF（原来的做法）；核心 ETF 不够 → 少买', box); return; }
  if(!p.rows.length){ nd('div', 'neg small', '没有能卖来凑的持仓（都有没处理完的指令 / 规则在卖）：执行器会少买', box); return; }
  const mx=Math.max.apply(null, p.rows.map(r=>r.yen));
  for(const r of p.rows){
    const row=nd('div', 'frow', null, box), U=r.kind==='core' ? '口' : '股';
    nd('span', 'ft', r.t.replace('.T', '')+(r.kind==='core' ? ' ETF' : ''), row);
    const bar=nd('span', 'fbar', null, row); nd('i', null, null, bar).style.width=(r.yen/mx*100).toFixed(0)+'%';
    nd('span', 'fv', '卖 '+fmt(r.sell)+' '+U+' ≈ '+yen(r.yen), row);
    nd('div', 'muted small fsub', (fnm(r.t) ? fnm(r.t)+' · ' : '')+fmt(r.cur)+' → '+fmt(r.after)+' '+U+(r.after===0 ? '（全部卖出）' : ''), row);
  }
  nd('div', 'muted small', '合计约 '+yen(p.got)+(p.left>0 ? '，还差 '+yen(p.left)+' → 执行器会少买' : '')
    +' · 按最近收盘估算，个股按 100 股取整', box);
  if(opt) nd('div', 'muted small', '买入先过闸门，被挡则凑钱的卖出也不做；开盘跳空 / 价格更高没买到时，凑钱的卖出照样会卖', box);   // 2026-10-13
}
function fundBody(body, cost){
  if(FUND_MODE==='all' && body.kind==='buy'){ body.fund={mode:'all'}; return body; }
  if(FUND_MODE==='split' && cost>0 && fundSplit(cost, body.ticker)) body.fund={mode:'split', cost:Math.round(cost)};
  return body;
}
function allPrev(n, cap, go, out){                                         // 「其他全部卖出，只拿这只」的预览（拖到最大 / 名额已满 / 手选）
  const q=fundAll(BUY.t, BUY.px, BUY.lot), wa=CFG.when_all||'下一次决策';
  BUY.cost=q.buy; fundBox($('#buy-fund'), q.buy, BUY.t, {q:q, only:BUY.fullOnly});
  const bv=$('#buy-val'); if(bv){ bv.disabled=true; bv.value=q.n; }                 // 股数由执行器定：输入框只显示估算
  if(q.keep.length){ out.textContent='★ 有持仓现在卖不了（见下面「留着」）：先处理它再全部换成这只'; go.textContent='确认'; go.className='btn danger'; go.disabled=true; return; }
  if(q.n<=0){
    out.textContent='★ 其他持仓全部卖出（约 '+yen(q.got)+'）+ 现金约 '+yen(q.cash)+' 也不够 1 个单元（'+fmt(BUY.lot)+' 股 ≈ '+yen(BUY.lot*BUY.px)+'）'
      +'\n→ 照样全部卖出、留现金、不买（那天价格变了买得起才买）；'+wa+'整批处理';
    go.textContent='确认全部卖出（不买）'; go.className='btn danger'; go.disabled=false; return;
  }
  out.textContent='★ 其他持仓全部卖出，只拿这只 + 现金：'+wa+'整批先卖后买；买入约 '+fmt(q.n)+' 股（估算 · 约 '+yen(q.buy)+' · 约占权益 '+bpct(q.n)+'）'
    +'\n股数与限价（决策日 = 前一交易日的收盘 ×1.03）由执行器在那次决策里按全卖之后的钱再算，可能少 1 个单元；只做一次';
  go.textContent='确认：全卖其他、买入约 '+fmt(q.n)+' 股'; go.className='btn danger'; go.disabled=false;
}
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
  $('#buy-row').hidden = u==='rule' || !!(BUY && BUY.fullOnly);
  if(u!=='rule'){
    $('#buy-unit').textContent = {shares:'股', yen:'円', pct:'%'}[u];
    $('#buy-val').step = u==='shares' ? BUY.lot : u==='yen' ? 1000 : 0.1;
    buyShow(n==null || n<=0 ? (BUY.rule || BUY.lot) : n);
  }
  buyPrev();
}
function buyPrev(){
  const go=$('#buy-go'), out=$('#buy-prev');
  go.className='btn primary';
  { const bv=$('#buy-val'); if(bv && FUND_MODE!=='all') bv.disabled=false; }        // 离开「其他全部卖出」：输入框恢复（任何早退之前）
  let n=buyTarget();
  if(n==null && FUND_MODE!=='all'){ out.textContent='输入要买多少（股数 / 金额 / 占总权益 %）'; go.textContent='确认买入'; go.disabled=true; return; }
  const cap=buyCap(); let note='';
  if(FUND_MODE==='all'){ allPrev(n, cap, go, out); return; }
  if(n==null){ out.textContent='输入要买多少（股数 / 金额 / 占总权益 %）'; go.textContent='确认买入'; go.disabled=true; return; }
  if(n>cap){ n=cap; note='\n★ 超过'+capLab()+'：截到 '+fmt(n)+' 股'; }
  if(n<=0){
    fundBox($('#buy-fund'), 0, BUY.t, {cap:cap});
    out.textContent = BUY.unit==='rule' ? '按规则的仓位不够买 1 个单元（'+fmt(BUY.lot)+' 股 ≈ '+yen(BUY.lot*BUY.px)+'）：改用股数 / 金额试试'
      : '不够 1 个单元（'+fmt(BUY.lot)+' 股 ≈ '+yen(BUY.lot*BUY.px)+'）';
    go.textContent='确认买入'; go.disabled=true; return;
  }
  const br=$('#buy-range'); if(br) br.value=n;
  BUY.cost=n*(BUY.limit||BUY.px*1.03); fundBox($('#buy-fund'), BUY.cost, BUY.t, {});   // {}：买入框 → 凑钱方式多一个「其他全部卖出」
  out.textContent='买入约 '+fmt(n)+' 股 · 约 '+yen(n*BUY.px)+' · 约占权益 '+bpct(n)+note
    +'\n'+CFG.when+'买入（最高 '+yen(BUY.limit||BUY.px*1.03)+' = 收盘 ×1.03）；名额满 / 价格更高 → 不买；只做一次';
  go.textContent='确认买入约 '+fmt(n)+' 股'; go.disabled=false;
}
document.addEventListener('input', e=>{
  if(e.target.id==='core-pct') coreShow();
  if(e.target.id==='adj-val') adjPrev();
  if(e.target.id==='adj-range'){ adjShow(+e.target.value); adjPrev(); }
  if(e.target.id==='buy-val') buyPrev();
  if(e.target.id==='buy-range'){ const v=+e.target.value, mx=+e.target.max;   // 先记下拖到的位置（换单位时 buyPrev 会把拖动条拨回旧的股数）
    if(v>=mx && buyCap()>BUY.lot && FUND_MODE!=='all'){ FUND_PREV=FUND_MODE; FUND_MODE='all'; BUY.autoAll=true; }   // 拖到最右 = 其他全部卖出（2026-10-13 用户）；上限只有 1 个单元时不自动切（手选）
    else if(v<mx && FUND_MODE==='all' && BUY.autoAll && !BUY.fullOnly){ FUND_MODE=FUND_PREV; BUY.autoAll=false; }   // 自动进入的，拖回来就还原；手选的不动
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
  if(a==='ask-alt'){ const r=ASK; ASK=null; closeAll(); if(r) r({ok:true, alt:d.v}); return; }
  if(a==='sell'){
    CUR={t:d.t, shares:+d.shares};
    $('#sell-title').textContent='卖出 '+tlab(d.t, d.name);                // 「7203 トヨタ自動車」（不带 .T；名字查不到只写代码）
    $('#sell-desc').textContent='全部 '+fmt(+d.shares)+' 股 · '+CFG.when+'卖出'+NOTE;
    plBox($('#sell-pl'), estOf(d.t));                                      // 买入成交价 → 现价 / 预计卖出 → 预计收益与收益率
    sheet('#dlg-sell'); return;
  }
  if(a==='sell-go'){
    const bd=document.querySelector('input[name=bd]:checked').value; closeAll();
    done(await post({book:CFG.book, kind:'sell', ticker:CUR.t, block_days:parseInt(bd,10)})); return;
  }
  if(a==='adj'){
    if(FUND_MODE==='all') FUND_MODE='split';                                // 「其他全部卖出」只属于买入框
    const core=d.core==='1';
    ADJ={t:d.t, shares:+d.shares, px:+d.px, unit:'shares', core:core, lot:core ? (+d.lot||1) : LOT, u100:+d.u100||0, cpct:+d.cpct||0, approx:d.approx==='1'};
    $('#adj-title').textContent='调仓 '+tlab(d.t, d.name);
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
    const q=await ask('卖出全部 '+tlab(d.t, d.name), '全部 '+fmt(+d.shares)+' 口：'+CFG.when+'卖出'+coreFx(0, d.t)
      +'\n卖出后停买闲置资金 ETF（钱留现金）；出现买入信号会提醒你，你点「确认买入」才买'+NOTE, '卖出', {danger:true, pl:estOf(d.t)});
    if(q.ok) done(await post({book:CFG.book, kind:'sell', ticker:d.t})); return;
  }
  if(a==='core-resume'){                                                   // 停买后确认买入：闲置资金比例 0% → 100%（照规则）
    const q=await ask('确认买入：恢复闲置资金买入 ETF', '闲置资金比例 0% → 100%（照规则）'+coreFx(100, '', '会调：')
      +'\n'+(d.plan || CFG.when+'买入；之后每天照规则调')+NOTE, '确认买入');   // 2026-10-13：规则不拿 / 今天已经有单 → 服务器写的实际时间
    if(q.ok) done(await post({book:CFG.book, kind:'core', pct:100})); return;
  }
  if(a==='core-restore'){                                                  // 「全部换成」之前的比例（2026-10-13）：只在你点了之后写；固定口数不跟着恢复；只买规则目标额的 N%（2026-10-14）
    const v=+d.pct; if(!(v>0 && v<100)) return;
    const q=await ask('恢复成 '+v+'%：闲置资金比例', '闲置资金比例 0% → '+v+'%（规则目标额 × '+v+'%）'+coreFx(v, '', '会调：')
      +'\n'+(d.plan || CFG.when+'按规则目标额的 '+v+'% 买入；之后每天按 '+v+'% 调')+'\n固定口数不会跟着恢复：要的话在各 ETF 下面重新点「固定口数…」'+NOTE, '恢复成 '+v+'%');
    if(q.ok) done(await post({book:CFG.book, kind:'core', pct:v})); return;
  }
  if(a==='adj-unit'){ adjUnit(d.u); return; }
  if(a==='fund-mode'){
    const inBuy=$('#dlg-buy').open; if(d.m==='all' && !inBuy) return;
    if(inBuy && BUY && BUY.fullOnly && d.m!=='all') return;                // 名额已满：只能「其他全部卖出」
    FUND_MODE=d.m; if(FUND_MODE!=='all') FUND_PREV=FUND_MODE; if(inBuy && BUY) BUY.autoAll=false;   // 手选的：拖回来也不还原
    if(inBuy && FUND_MODE==='all' && BUY.unit!=='shares'){ buyUnit('shares'); return; }   // 金额 / % 单位下手选：先换成股数（输入框显示的是股数）
    if(inBuy) buyPrev(); else adjPrev(); return;
  }
  if(a==='adj-step'){ const n=adjTarget(); adjShow(Math.max(0, (n==null ? ADJ.shares : n)+(+d.d)*ALOT())); adjPrev(); return; }
  if(a==='adj-go'){
    if(ADJ && ADJ.fix){ const n=adjTarget(); if(n==null) return; const u=Math.min(n, adjCap());
      closeAll(); done(await post(fundBody({book:CFG.book, kind:'corefix', ticker:ADJ.t, units:u}, u>ADJ.shares ? (u-ADJ.shares)*ADJ.px : 0))); return; }
    const n=adjTarget(); if(n==null || n===ADJ.shares) return;
    const v = ADJ.unit==='shares' ? n : parseFloat($('#adj-val').value);
    closeAll(); done(await post(fundBody({book:CFG.book, kind:'adjust', ticker:ADJ.t, unit:ADJ.unit, value:v}, n>ADJ.shares ? ADJ.cost||0 : 0))); return;
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
    BUY={t:d.t, px:+d.px, lot:+d.lot||LOT, rule:+d.rule||0, limit:+d.limit||0, unit:'rule', autoAll:false, fullOnly:d.full==='1'};
    FUND_MODE=FUND_PREV='split';
    if(d.name) (CFG.names=CFG.names||{})[d.t]=d.name;                    // 建议的股票可能不在页面的名字表里：凑钱 / 仓位占比那几行也带上名字
    $('#buy-title').textContent='买入 '+tlab(d.code||d.t, d.name);
    $('#buy-sig').textContent=(d.sig==='1' ? '今天出了买入信号（'+d.rtext+'）' : '★ '+d.status+'：还没有买入信号，规则不会买 —— 是你自己的决定')
      +(d.warn ? '\n★ '+d.warn : '')+NOTE;
    $('#buy-cap').textContent=CFG.cap;
    { const r=$('#buy-range'), L=BUY.lot; r.min=L; r.step=L; r.max=Math.max(L, buyCap()); }
    { const lock=BUY.fullOnly; $('#buy-range').disabled=lock; $('#buy-seg').hidden=lock; }   // 名额已满：只能「其他全部卖出」，股数由执行器定
    if(BUY.fullOnly){ FUND_MODE='all'; buyUnit('shares'); } else buyUnit('rule');
    sheet('#dlg-buy'); buyLive(); loadSQ(); return;            // 现价 + 现在买按什么价（Yahoo，约晚 20 分钟）
  }
  if(a==='buy-unit'){ buyUnit(d.u); return; }
  if(a==='buy-step'){ if(FUND_MODE==='all') return; if(BUY.unit!=='rule'){ const n=buyTarget(); buyShow(Math.max(BUY.lot, (n==null||n<=0 ? BUY.lot : n)+(+d.d)*BUY.lot)); } buyPrev(); return; }
  if(a==='buy-go'){
    const n=buyTarget(); if(!n && FUND_MODE!=='all') return;
    const body={book:CFG.book, kind:'buy', ticker:BUY.t, unit:BUY.unit};
    if(FUND_MODE==='all'){ body.unit='shares'; body.value=Math.max(buyCap(), BUY.lot); }   // 股数由执行器按全卖之后的钱再算
    else if(BUY.unit!=='rule') body.value = BUY.unit==='shares' ? Math.min(n, buyCap()) : parseFloat($('#buy-val').value);
    closeAll(); done(await post(fundBody(body, BUY.cost||0))); return;
  }
  if(a==='core-step'){ const r=$('#core-pct'); r.value=Math.max(0, Math.min(100, parseFloat(r.value)+parseFloat(d.d))); coreShow(); return; }
  if(a==='core'){
    const v=parseFloat($('#core-pct').value);
    const q=await ask('闲置资金比例 '+v+'%', '核心 ETF 的目标额 = 规则算出的 × '+v+'%，下一次决策起生效'+(v<100?'（多出来的留现金）':'')+NOTE, '保存');
    if(q.ok) done(await post({book:CFG.book, kind:'core', pct:v})); return;
  }
  if(a==='cancel-order'){                                                 // 撤单：执行器今天的单（还挂着的 / 还没发出的计划・等开盘后；面板马上叫执行器撤）
    const hint=d.hint || (d.core==='1' ? '核心 ETF 的单：已经成交的部分撤不了；下一次决策照规则 / 闲置资金比例重新算目标，可能再买 / 再卖（要少拿用「闲置资金比例」）'
                    : '已经成交的部分撤不了；撤掉的卖单如果规则明天还要卖会再下；撤掉的个股买单不再买');   // 撤之后会怎样：服务器按单的来源写（data-hint；M5，2026-10-15）
    const head='撤单 '+(d.side==='BUY'?'买 ':'卖 ')+tqty(d.t, fmt(+d.qty)+(d.core==='1'?' 口':' 股'), d.name);
    const gl=d.glist ? '\n'+d.glist : '';                                // 同一组每一笔会怎样（服务器算：data-glist；2026-10-16）
    const g=(d.grp||'').split(',').filter(Boolean);                       // 同一组里现在能撤的其他单（data-grp）
    if(g.length>0){                                                       // 整组撤单（2026-10-16 用户：一起下的买单和卖单要能一起撤）
      const n=g.length+1, gn=Math.max(+d.gn||0, n), solo=d.solo||'只撤这一笔', galt=[{text:solo, v:'one'}];
      const glab='整组撤单（'+(gn>n ? '能撤的 ' : '')+n+' 笔）';            // 同一组还有不能一起撤的（已成交 / 已撤 / 撤单中）：写「能撤的 N 笔」（data-gn；复核 2）
      if(d.fix) galt.push({text:'整组撤单并恢复按规则（'+tlab(d.fix, d.fixname)+'）', v:'fix', danger:true});
      const q=await ask(head+' · 同一组 '+gn+' 笔',
        hint+'。'+(CFG.paper ? '' : d.gexch==='1' ? '\n马上发撤单到立花（之后看「今天要成交的单」的状态）' : '\n这几笔都还没发到立花：撤了执行器就不再发')+gl   // data-gexch（复核 6）
        +'\n「'+glab+'」= 这一组能撤的一起撤：先撤买单，确认没成交再撤卖单；「'+solo+'」= 只撤这一笔'
        +(d.fix ? '；「整组撤单并恢复按规则」= 一起撤、再取消固定口数（照规则调：什么时候见下一个确认框）' : '')
        +(d.soloh ? '\n'+d.soloh : ''),                                // data-soloh：只撤卖单的 ★（放最后一行；复核 8：以前按钮说明接在 ★ 后面）
        glab, {danger:true, alt:galt});
      if(!q.ok) return;
      let body={book:CFG.book, kind:'cancel_order', cid:d.cid, deps:'cancel', grp:g};
      if(q.alt==='one'){ body={book:CFG.book, kind:'cancel_order', cid:d.cid}; if(d.side==='SELL') body.deps='keep'; }
      const j=await post(body);
      if(q.alt!=='fix' || !j){ done(j); return; }
      const k=await post({book:CFG.book, kind:'corefix', ticker:d.fix, clear:true});   // 恢复按规则：服务器给「确认下单」框（取消 → 只撤了单）
      done(k ? {msg:(j.msg||'已写撤单')+'\n'+(k.msg||'已写恢复按规则')} : j);
      return;
    }
    const dep=+d.depn||0, alt=[], dk=d.depk||'一起撤买单';                // 靠这笔卖出的钱、执行器还没发出的买单（fund_src；D2）：几个按钮
                                                                          // （执行器撤完买单之后还有买单会花钱 → 卖单不撤：data-depk「撤买单（卖单不撤）」；复核 2）
    const fk=d.depk ? '撤买单并恢复按规则' : '撤单并恢复按规则';            // 复核 3（2026-10-16）：卖单不撤时这个按钮也这么叫、这么写（以前写「一起撤」）
    const bx=d.depx==='1' ? '（还没发出的执行器不再发，在交易所的发撤单）' : '（执行器不再发）';   // data-depx：「一起撤买单」也撤在交易所的买单
    if(dep>0){ alt.push({text:d.keep||'只撤卖单', v:'keep'}); if(d.fix) alt.push({text:fk+'（'+tlab(d.fix, d.fixname)+(d.depk ? '；卖单不撤' : '')+'）', v:'fix', danger:true}); }
    else if(d.fix) alt.push({text:'撤单并恢复按规则（'+tlab(d.fix, d.fixname)+'）', v:'fix', danger:true});   // 固定口数排的单（2026-10-16）
    const q=await ask(head,
      hint+'。'+(d.unsent==='1' ? '' : (CFG.paper ? '' : '\n马上发撤单到立花（之后看「今天要成交的单」的状态）'))
      +(d.deps ? '\n★ '+d.deps : '')                                    // 靠这笔卖出的钱的买单（服务器算：data-deps；2026-10-15）
      +(dep>0 ? '\n「'+dk+'」= 这几笔买单'+(d.depk ? '撤掉'+bx+'，这笔卖单不撤（见下面 ★）'
                : '也撤'+bx+(d.depw==='1' ? '，买单撤掉了（没成交）才撤这笔卖单（见下面 ★）' : ''))   // data-depw：先撤买单、确认没成交再撤卖单（复核 3）
        +'；「只撤卖单」= 买单按现在的钱重算'
        +(d.fix ? '；「'+fk+'」= '+(d.depk ? '靠它的钱的买单撤掉、这笔卖单不撤' : d.depw==='1' ? '和「一起撤买单」一样（买单撤掉了才撤这笔卖单）' : '一起撤')
          +'，再取消固定口数（照规则调：什么时候见下一个确认框）' : '') : '')
      +gl
      +(dep===0 && d.fix ? '\n「撤单并恢复按规则」= 撤单、再取消固定口数（照规则调：什么时候见下一个确认框）' : ''),
      dep>0 ? dk : (d.solok==='1' ? '只撤这笔卖单' : '撤单'), {danger:true, alt:alt});
    if(!q.ok) return;
    const body={book:CFG.book, kind:'cancel_order', cid:d.cid};
    if(dep>0) body.deps = q.alt==='keep' ? 'keep' : 'cancel';
    else if(d.solok==='1') body.deps='keep';                              // 同一组的买单还可能花钱、你选了只撤这笔卖单（data-solok；复核 2026-10-16）
    const j=await post(body);
    if(q.alt!=='fix' || !j){ done(j); return; }
    const k=await post({book:CFG.book, kind:'corefix', ticker:d.fix, clear:true});   // 恢复按规则：服务器给「确认下单」框（取消 → 只撤了单）
    done(k ? {msg:(j.msg||'已写撤单')+'\n'+(k.msg||'已写恢复按规则')} : j);
    return;
  }
  if(a==='fix-undo'){                                                     // 还没照它调的固定口数 / 还差几口：不补了・撤回（2026-10-17；选择与说明由服务器按账本写好：data-opts / data-body）
    let o=[]; try{ o=JSON.parse(d.opts||'[]'); }catch(_){ o=[]; }
    if(!o.length) return;
    const q=await ask(d.title||'撤回？', (d.body||'')+NOTE, o[0].l, {alt:o.slice(1,3).map((x,i)=>({text:x.l, v:String(i+1), danger:!!x.c}))});
    if(!q.ok) return;
    const x=o[q.alt ? +q.alt : 0]; if(!x) return;                         // 下一步：服务器的「确认下单」框（那次预计下的单；点了才写）
    done(await post(x.c ? {book:CFG.book, kind:'corefix', ticker:d.t, clear:true} : {book:CFG.book, kind:'corefix', ticker:d.t, units:+x.u}));
    return;
  }
  if(a==='core-undo'){                                                    // 还没照它调的闲置资金比例：改回上一次照它调的（2026-10-17）
    const q=await ask(d.title||'撤回？', (d.body||'')+NOTE, d.ok||'改回');
    if(q.ok) done(await post({book:CFG.book, kind:'core', pct:+d.pct})); return;
  }
  if(a==='cancel' && d.kind==='unblock'){                                 // 还没读的「解除不买回」：撤回（2026-10-13）
    const q=await ask('撤回这条解除？', (d.desc||d.id)+'\n\n执行器还没读：撤回之后不解除，「不自动买回」照旧。\n（指令 '+d.id+'）', '撤回', {danger:true});
    if(q.ok) done(await post({book:CFG.book, kind:'cancel', target:d.id})); return;
  }
  if(a==='cancel' && d.kind==='cancel_order'){                            // 还没读的撤单：撤回（2026-10-16 事后）
    const q=await ask('撤回这条撤单？', (d.desc||d.id)+'\n\n撤单的运行还没做它：撤回之后不撤这笔单（还挂着的照常挂着、还没发出的照常发；HALT 中不发）。'
      +'\n已经在撤 / 执行器正在运行时撤回不了（提交后会说明）。\n（指令 '+d.id+'）', '撤回撤单');
    if(q.ok) done(await post({book:CFG.book, kind:'cancel', target:d.id})); return;
  }
  if(a==='cancel'){                                                       // 撤单前一定确认（2026-10-12 用户：防止误撤）：写清撤的是哪一条
    const q=await ask('确认撤单？', (d.desc||d.id)+'\n\n'+(d.placed==='2' ? (d.wtxt||'盘中的单已在 15:30 失效：撤回之后下一次开盘不再卖（下一次早上的对账之后结束；已经成交的部分照记）')+'。'   // G16（2026-10-14；复核：服务器按下单那天写 data-wtxt）
      : d.placed==='1' ? '之后不再下。已经发到交易所的单用「今天要成交的单」的「撤单」撤。' : '还没下单：撤掉之后不会下。')
      +(+d.fund>0 ? '\n为这笔买入写的 '+d.fund+' 条卖出 / 闲置资金指令也一起撤掉。' : '')+(+d.stuck>0 ? '\n另有 '+d.stuck+' 条已经生效 / 已在撤回中，撤不了（提交后会说明）。' : '')+'\n（指令 '+d.id+'）', '确认撤单', {danger:true});
    if(q.ok) done(await post({book:CFG.book, kind:'cancel', target:d.id})); return;
  }
  if(a==='uncancel'){                                                     // 撤销一条撤回（2026-10-12）：原来的指令恢复「等下单」/「等执行器读」（data-st；2026-10-14）、撤回记录不再显示
    const q=await ask('撤销这条撤回？', (d.desc||d.id)+'\n\n撤销之后，原来的指令恢复「'+(d.st||'等下单')+'」，这条撤回不再显示。\n什么时候处理：'
      +(d.when||'执行器下一次运行时')+(d.halt==='1' ? '\n★ HALT 生效中（解除后才处理）' : '')+'\n（指令 '+d.id+'）', '撤销撤回');   // 2026-10-13：写实际的时间与价格（服务器算的），不是「原来的时间」
    if(q.ok) done(await post({book:CFG.book, kind:'uncancel', target:d.id})); return;
  }
  if(a==='corefix' || a==='corefix-clear'){
    if(FUND_MODE==='all') FUND_MODE='split';                                // 「其他全部卖出」只属于买入框                               // 核心 ETF 固定口数 / 恢复按规则（2026-10-11）
    const px=+d.px||0, lot=+d.lot||1, eq=+d.eq||0, cur=+d.cur||0;
    if(a==='corefix-clear'){                                               // 2026-10-15：直接给「确认下单」框（服务器算：会买 / 卖多少、别的 ETF、什么时候、今天的单），点「确认下单」才写
      done(await post({book:CFG.book, kind:'corefix', ticker:d.t, clear:true})); return;
    }
    ADJ={t:d.t, shares:cur, px:px, unit:'shares', core:true, fix:true, lot:lot, u100:0, cpct:0, approx:false, name:d.name};
    $('#adj-title').textContent=(cur>0 ? '固定口数 ' : '买入 ')+tlab(d.t, d.name);
    $('#adj-cur').textContent='现在 '+fmt(cur)+' 口 · 约 '+yen(cur*px)+' · 约占权益 '+pctOf(cur)+' · 收盘 ¥'+px+' · 一个单元 '+fmt(lot)+' 口';
    $('#adj-u-sh').textContent='口数';
    const ru=$('#adj-rule'); if(ru){ if(ADJ_RULE==null) ADJ_RULE=ru.innerHTML;
      ru.textContent='拖动滑条或输入目标（口数 / 金额 / 占总权益 %），按单元（'+fmt(lot)+' 口）取整；最右边 = 总权益全部。'+NOTE.trim(); }
    $('#adj-val').value='';
    const r=$('#adj-range'); r.max=Math.max(1, Math.ceil(Math.max(adjCap(), cur, lot)/lot))*lot; r.step=lot; r.value=cur;
    adjUnit('shares'); sheet('#dlg-adj'); return;
  }
  if(a==='unblock-batch'){                                                // 「全部换成」卖掉的票：只解除这一批的不自动买回（2026-10-13；说明由页面按账本写好）
    const ps=(d.ids||'').split(',').filter(Boolean);                      // 「代码:设定 id」：设定换了 / 已经解除的服务器跳过
    const q=await ask('恢复按规则：「全部换成 '+d.x+'」卖出的 '+ps.length+' 只', (d.msg||'')+NOTE, '恢复按规则');
    if(q.ok) done(await post({book:CFG.book, kind:'unblock', ticker:ps[0].split(':')[0], tickers:ps})); return;
  }
  if(a==='unblock'){
    const q=await ask('解除 '+tlab(d.t, d.name)+' 的不自动买回', (d.msg||'')+NOTE, '解除');
    if(q.ok) done(await post({book:CFG.book, kind:'unblock', ticker:d.t, block_id:d.id||undefined})); return;
  }
  if(a==='flow'){                                                         // 〔77〕C UX-14：登记入金 / 出金（只影响收益的计算）
    const v=($('#flow-jpy').value||'').replace(/[,¥\s]/g,''), n=+v;
    if(!v || !isFinite(n) || Math.abs(n)<1){ toast('金额：入金写正数、出金写负数（例 300000 / -300000）', true); return; }
    const rs=!!($('#flow-reserve')||{}).checked && n<0;
    const q=await ask((n>0?'登记入金 ':'登记出金 ')+(n>0?'+':'−')+'¥'+fmt(Math.abs(n))+(rs?'（预留）':''), '日期 '+($('#flow-date').value||'今天')+'。'+(rs ? '预留：到账前的决策按扣掉这笔钱算（个股仓位变小、闲置资金 ETF 不买回；现金不够先卖核心 ETF）；到账后自动解除。' : '只影响收益的计算与「现金突然变化」的提醒，不下单。'), '登记');
    const rsv=!!($('#flow-reserve')||{}).checked;
    if(rsv && n>0){ toast('预留只用于出金（写负数）', true); return; }
    if(q.ok) done(await post({book:CFG.book, kind:'flow', jpy:n, date:$('#flow-date').value, note:$('#flow-note').value, reserve:rsv})); return;
  }
  if(a==='halt'){
    const q=await ask('停止下单（HALT）', '全部账本（模拟和立花）从下一次运行起不下单、持仓不动。\n已经发到交易所的单不会被撤（要撤：「今天要成交的单」的「撤单」，或立花网站 / 手机网站）。\n这里只能停：恢复只在 Mac 上（在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」）。'
      +(CFG.halt_allin ? '\n注意：'+CFG.halt_allin+'。' : ''), '停止下单', {danger:true, input:'原因（可不填）'});   // 2026-10-13：同批卖单已在交易所
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
