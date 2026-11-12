// qbreak 操作面板：kline.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/kline.js 提供；不要用构建工具）
import { CFG, fmt, nd, pcs, pxs, tipEl, tlab, toast } from './core.js';
import { req } from './net.js';

// ── K 线（同花顺式：红 = 涨（空心）、绿 = 跌（实心）；5 / 10 / 20 / 30 日均价；买入价 / 止损线）──
// 每张图自己的按钮（2026-10-07 用户：「K线的日周月button 要显示在每个K线的上面边沿方便看 / 量 MACD DMI 显示在每个K线的下面」）：
//   上边沿 = 日K / 周K / 月K，下边沿 = 量 / MACD / DMI；每张图各自切换，新打开的图用最近一次选的（记在这台设备的浏览器里）
// 说明都用日常的话（同日：「K线解释换成通俗易懂的说法 横展开」）：标签的说法来自 qbreak/kline.py（CFG.kp），其余按图里的数字现算
// 小图：量 / MACD（规则同一组参数）/ DMI（同花顺写法）；趋势线：连低点的支撑线、连高点的压力线（qbreak/trendline.py）+ 往后延长的点线 + 破线点
// 数据 = 执行器每次运行写的 out/charts_<账本>.json，打开 / 看到哪只票才取（/api/chart）；只展示
// 每张图不带说明 / 数字表（2026-10-15 用户：「整体留一个解释就行」「不需要最近十个月的数字 看图就行」）：
//   整页一份「怎么看 K 线图」在「持仓」的 K 线上面（服务器画：panel._kline_help）；图下面只留各自的一句话（最新一根、现在的趋势、趋势线）
export const TFS = {D:'日K', W:'周K', M:'月K'}, SUBS = {v:'量', macd:'MACD', dmi:'DMI'};
const KU = {D:'天', W:'周', M:'个月'}, KMA = {D:'日', W:'周', M:'个月'};   // 一根 = 1 天 / 1 周 / 1 个月；20 日均价 / 20 周均价 / 20 个月均价
const KPL = CFG.kp || {};
let TF = 'D', SUB = 'v', CPN = 0;                                         // 新打开的图默认用的周期 / 小图（= 最近一次选的）
export function setTF(v){ TF=v; }                                        // 别的模块改「新打开的图默认周期 / 小图」用这两个
export function setSUB(v){ SUB=v; }
try{ const v=localStorage.getItem('qbreak.tf'); if(v && TFS[v]) TF=v; }catch(x){}
try{ const v=localStorage.getItem('qbreak.sub'); if(v && SUBS[v]) SUB=v; }catch(x){}
export const KD = {}, KP = {};
const NS='http://www.w3.org/2000/svg', WD=['日','一','二','三','四','五','六'];
const MAS=[['ma5',5,'m5'],['ma10',10,'m10'],['ma20',20,'m20'],['ma30',30,'m30']];
function sv(tag, at, par){ const e=document.createElementNS(NS, tag); for(const k in at) e.setAttribute(k, at[k]); if(par) par.appendChild(e); return e; }
function nice(lo, hi, n){
  const raw=(hi-lo||Math.abs(hi)||1)/n, p=Math.pow(10, Math.floor(Math.log10(raw))), f=raw/p;
  const st=(f<1.5?1:f<3?2:f<3.5?2.5:f<7.5?5:10)*p, out=[];
  for(let v=Math.ceil(lo/st)*st; v<=hi+st*1e-9; v+=st) out.push(+v.toFixed(8));
  return out;
}
function vfmt(v){ return v>=1e8 ? (v/1e8).toFixed(1)+' 亿' : v>=1e4 ? (v/1e4).toFixed(v>=1e6?0:1)+' 万' : String(v); }
function dlab(d, tf){ return tf==='M' ? d.slice(0,4)+' 年 '+(+d.slice(5,7))+' 月' : tf==='W' ? '到 '+d.replace(/-/g,'/')+' 的一周' : d.replace(/-/g,'/')+'（'+WD[new Date(d+'T00:00:00').getDay()]+'）'; }
function sdate(d, tf){ return tf==='M' ? d.slice(0,7).replace('-','/') : d.slice(5).replace('-','/'); }
function authReload(){                                                     // 2026-10-15 复核：以前每张 401 的图各自 1.5 秒后 location.reload()，不管对话框开没开（输入的口数会丢）
  if(typeof window.qbAuth==='function'){ window.qbAuth(); return; }       // conn.js：等对话框关掉 / 输入完、只刷新一次
  if(authReload.on) return; authReload.on=1;
  (function wait(){ if(document.querySelector('dialog[open]')) setTimeout(wait, 2000); else location.reload(); })();
}
function loadK(t){
  if(KD[t] && KD[t]!=='error' && KD[t]!=='timeout' && KD[t]!=='loading') return Promise.resolve(KD[t]);
  if(KP[t]) return KP[t];                                                   // 同一只票已经在取：等同一个请求
  KD[t]='loading';
  const p=(async()=>{
    try{
      const x=await req('/api/chart?book='+encodeURIComponent(CFG.book)+'&t='+encodeURIComponent(t), {credentials:'same-origin', cache:'no-store'});
      if(x.r.status===404) KD[t]='none';
      else if(x.r.status===401){ KD[t]='auth'; authReload(); }             // 这台设备没被认出来：刷新（会到配对页；对话框开着 / 正在输入 → 等关掉；几张图一起也只一次）
      else if(!x.r.ok || !x.j) KD[t]='error';                                // 内容读不出来（连接中途断了）也算取不到：可以再点
      else KD[t]=x.j.data ? x.j.data : 'none';
    }catch(e){ KD[t]=(e && e.name==='Timeout') ? 'timeout' : 'error'; }   // 15 秒没有回应（Mac 睡眠时不会一直停在「载入中」）
    return KD[t];
  })();
  KP[t]=p; p.then(()=>{ if(KP[t]===p) delete KP[t]; });
  return p;
}
function legend(head, D, i, tf){
  head.textContent='';
  nd('b',null,'均价线',head);
  for(const [k,n,cls] of MAS){ const v=D[k] && D[k][i]; const sp=nd('span',null,null,head); nd('i','key '+cls,null,sp); sp.appendChild(document.createTextNode(n+' '+KMA[tf]+' '+(v==null?'—':pxs(v)))); }
}
function isLive(P, D, i, tf){ const L=P && P.live; return !!(L && i===D.d.length-1 && (L.tf||[]).indexOf(tf)>=0 && D.d[i]>=L.d); }
function liveAt(P){ return String((P.live||{}).at||'').slice(11,16); }
function readout(el, D, i, P, tf){
  el.textContent='';
  const pc=i>0 ? D.c[i-1] : null, c=D.c[i], dir=(pc && c!=null) ? (c>=pc ? 'up' : 'down') : null, lv=isLive(P, D, i, tf);
  nd('span','m', dlab(D.d[i], tf)+' ', el);
  if(lv) nd('span','m',(P.live.open ? '盘中 ' : '暂定 ')+liveAt(P)+' ', el);   // 今天这一根：到这个时刻为止（Yahoo 1 分钟线，约晚 20 分钟）；收盘后 = 暂定
  nd('b',dir,(lv ? (P.live.open ? '现价 ' : '最新价 ') : '收盘 ')+pxs(c)+(pc && c!=null ? '（'+pcs((c/pc-1)*100)+'）' : ''),el);
  el.appendChild(document.createTextNode(' · 开 '+pxs(D.o[i])+' · 高 '+pxs(D.h[i])+' · 低 '+pxs(D.l[i])+' · 量 '+vfmt(D.v[i]||0)+(P.kind==='core'?' 口':' 股')
    +(P.kind==='stock' && P.entry_px && c!=null ? ' · 比买入价 '+pcs((c/P.entry_px-1)*100) : '')));
}
function fmx(a, i, sg){ const v=a && a[i]; if(v==null) return '—'; const s=Math.abs(v)>=100 ? v.toFixed(0) : Math.abs(v)>=1 ? v.toFixed(2) : v.toFixed(3); return (sg && v>0 ? '+' : '')+s; }
function f1(a, i){ const v=a && a[i]; return v==null ? '—' : v.toFixed(1); }
function subText(D, i, sub){                                               // 小图左上角的数字（短：手机上一行放得下）
  if(sub==='macd') return 'DIF '+fmx(D.dif,i)+' · DEA '+fmx(D.dea,i)+' · 柱 '+fmx(D.mh,i,true);
  if(sub==='dmi') return '+DI '+f1(D.pdi,i)+' · −DI '+f1(D.mdi,i)+' · ADX '+f1(D.adx,i)+' · ADXR '+f1(D.adxr,i);
  return '';
}
function kSubKey(el, P, tf, sub){                                          // 小图的图例（意思在「持仓」K 线上面的「怎么看 K 线图」里）
  el.textContent='';
  const row=nd('div','legend',null,el);
  const k=(c, t)=>{ const sp=nd('span',null,null,row); nd('i','key '+c,null,sp); sp.appendChild(document.createTextNode(t)); };
  if(sub==='macd'){ k('dif','快线'); k('dea','慢线'); k('box mhu','柱 = 快线 − 慢线'); nd('span',null,'MACD '+((P.ind||{}).macd||[12,26,9]).join(','),row); }
  else if(sub==='dmi'){ k('pdi','+DI 买方'); k('mdi','−DI 卖方'); k('adx','ADX 趋势强度'); k('adxr','ADXR'); nd('span',null,'DMI '+((P.ind||{}).dmi||[14,6]).join(','),row); }
  else { k('box cu','涨'); k('box cd','跌'); nd('span',null,'成交量（'+(P.kind==='core' ? '口' : '股')+'）',row); }
}
function kPut(el, parts){ for(const [t, c] of parts) if(t) (c ? nd('b', c, t, el) : el.appendChild(document.createTextNode(t))); }   // 要点上色、补充是灰字（2026-10-17：一句话太长 → 颜色看重点）
function kSubNow(el, D, i, P, tf, sub){                                    // 小图「这一根」（跟着十字线走）：要点上色（金叉 / 买方强 = 红〔涨〕、死叉 / 卖方强 = 绿、量比 ≥ 2 = 加粗）
  const ps=[];
  if(sub==='macd'){
    const a=D.dif && D.dif[i], b=D.dea && D.dea[i], h=D.mh && D.mh[i], h0=i>0 && D.mh ? D.mh[i-1] : null;
    if(a==null || b==null) ps.push(['K 线还不够多，算不出来']);
    else {
      if(h!=null && h0!=null && h0<0 && h>=0) ps.push(['金叉','up'],['（快线刚往上穿过慢线）']);
      else if(h!=null && h0!=null && h0>0 && h<=0) ps.push(['死叉','down'],['（快线刚往下穿过慢线）']);
      else ps.push(a>=b ? ['快线在慢线上面','up'] : ['快线在慢线下面','down'], [(a>=b ? '（涨的力量强）' : '（跌的力量强）')
             +(h!=null && h0!=null ? (Math.abs(h)>Math.abs(h0) ? '，在变强' : '，在变弱') : '')]);
      ps.push(['；在 0 线'+(a>=0 ? '上面（偏涨）' : '下面（偏跌）')]);
    }
  } else if(sub==='dmi'){
    const p=D.pdi && D.pdi[i], m=D.mdi && D.mdi[i], x=D.adx && D.adx[i], x0=i>0 && D.adx ? D.adx[i-1] : null;
    if(p==null || m==null) ps.push(['K 线还不够多，算不出来']);
    else {
      ps.push(p>=m ? ['买方强','up'] : ['卖方强','down']);
      if(x!=null) ps.push(['；ADX '+x.toFixed(1)+(x>=25 ? '（趋势明显）' : x<20 ? '（没什么趋势）' : '（趋势一般）')+(x0!=null ? (x>x0 ? '，在变强' : '，在变弱') : '')]);
    }
  } else {
    const v=D.v[i]||0; let sm=0, n=0;
    for(let j=Math.max(0, i-20); j<i; j++){ if(D.v[j]!=null){ sm+=D.v[j]; n++; } }
    ps.push(['成交 '+vfmt(v)+(P.kind==='core' ? ' 口' : ' 股')]);
    if(n>=5 && sm>0){ const r=v/(sm/n); ps.push(['，是前 '+n+' '+KU[tf]+'平均的 '], [r.toFixed(2)+' 倍', r>=2 ? 'hi' : null]); }
  }
  const lv=isLive(P, D, i, tf);
  el.textContent='';
  kPut(el, [[(lv ? (P.live.open ? '今天这一根（到 '+liveAt(P)+'，还没收盘）' : '暂定的一根（1 分钟线到 '+liveAt(P)+'；正式日线在执行器下一次运行后换上）')
    : i===D.d.length-1 ? '最新一根' : sdate(D.d[i], tf))+'：']].concat(ps));
}
function kTrend(el, tr, tf){                                               // 现在的趋势（kline.py 的标签换成日常的话；趋势上色、括号里的是灰字）
  const L=KPL.label||{}, A=KPL.align||{}, m=KMA[tf], sl=+tr.slope20_pct||0;
  nd('span',null,'现在的趋势：',el);
  nd('b', tr.label==='上升' ? 'up' : tr.label==='下降' ? 'down' : null, L[tr.label] || tr.label || '—', el);
  el.appendChild(document.createTextNode('（收盘在 20 '+m+'均价'+(tr.above20 ? '上面' : '下面')+'，20 '+m+'均价'
    +(Math.abs(sl)<0.005 ? '走平' : sl>0 ? '往上' : '往下')+'）'));
  if(tr.align){ el.appendChild(document.createTextNode(' · ')); nd('b', null, A[tr.align] || tr.align, el); }
}
function kTL(el, TL, tf, D, mode){                                         // 现在的趋势线（图上的记号在「持仓」K 线上面的「怎么看 K 线图」里）：价位加粗、跌破 / 冲过上色
  const C=KPL.chan||{};
  const one=(L, sup)=>{ const d=L.dist_pct;
    return [[sup ? ' · 支撑 ' : ' · 压力 '], [pxs(L.now), 'px'], d==null ? [''] : sup ? (d<=0 ? ['（比收盘低 '+Math.abs(d)+'%）'] : ['（已跌破）','down'])
                                                                    : (d>=0 ? ['（比收盘高 '+d+'%）'] : ['（已冲过）','up'])]; };
  const row=nd('div','ktl',null,el);
  const g=nd('div','seg sm',null,row); g.setAttribute('role','group'); g.setAttribute('aria-label','趋势线怎么连');   // 2026-10-17 用户「精确趋势线」：按影线 / 按收盘
  for(const [k, lab] of [['w','按影线'],['c','按收盘']]){ const b=nd('button',null,lab,g); b.type='button'; b.dataset.act='ktlm'; b.dataset.v=k; b.setAttribute('aria-pressed', k===mode ? 'true' : 'false'); }
  const tx=nd('span',null,null,row);
  if(mode==='c' && !('tlc' in D) && D.tl){ kPut(tx, [['趋势线：按收盘的线在执行器下一次运行之后显示（旧的 K 线数据里没有）']]); return; }   // 2026-10-17 之前写的 charts_*.json
  if(!TL || !(TL.sup || TL.res)){ kPut(tx, [['趋势线：'+(mode==='c' ? '按收盘' : '按影线')+'找不到（没有碰过两次以上、还没被破的线）']]); return; }
  kPut(tx, [['趋势线：'+(TL.chan ? (C[TL.chan] || TL.chan) : '只找到'+(TL.sup ? '下面' : '上面')+'的一条')]]
    .concat(TL.sup ? one(TL.sup, true) : [], TL.res ? one(TL.res, false) : []));
  const at=i=> i>=0 && i<D.d.length ? (tf==='M' ? D.d[i].slice(0,7) : D.d[i]).replace(/-/g,'/') : '图外更早';   // 锚点（连的两个点）是哪两根（带年份）
  const pt=mode==='c' ? '收盘' : '';
  const tip=[];
  for(const [s, lab, w] of [['sup','支撑线','低点'],['res','压力线','高点']]){ const L=TL[s]; if(!L) continue;
    tip.push(lab+'：连 '+at(L.i1)+' 和 '+at(L.i2)+' 的两个'+(pt || w)+'，碰过 '+(L.touch||2)+' 次；每根 '+(L.slope_pct>=0 ? '+' : '')+(L.slope_pct==null ? '—' : L.slope_pct)+'%'); }
  if(TL.tol) tip.push('容差 '+pxs(TL.tol)+'（图上线两边的淡色带）：离线这么近算碰到，收盘出了带子才算破');
  tip.push(mode==='c' ? '按收盘：只看收盘价连线（影线的长短不影响）' : '按影线：支撑连最低价、压力连最高价（同花顺的画法）');
  tipEl(tx, tip);
}
function kBar(box, pos, act, opts, cur, label, hint){                      // 图的上边沿（周期）/ 下边沿（小图）的按钮
  const bar=nd('div','kbar '+pos,null,box), g=nd('div','seg',null,bar);
  g.setAttribute('role','group'); g.setAttribute('aria-label',label);
  for(const k in opts){ const b=nd('button',null,opts[k],g); b.type='button'; b.dataset.act=act; b.dataset.v=k; b.setAttribute('aria-pressed', k===cur ? 'true' : 'false'); }
  if(hint) nd('span','hint',hint,bar);
  return bar;
}
function kBtn(par, txt, act, v, lab, on){                                   // 图上的小按钮（缩放 / 对数 / 画线）
  const b=nd('button','kz',txt,par); b.type='button'; b.dataset.act=act; if(v!=null) b.dataset.v=v;
  if(lab){ b.setAttribute('aria-label', lab); b.title=lab; }
  if(on!=null) b.setAttribute('aria-pressed', on ? 'true' : 'false');
  return b;
}
// ── 看更早 / 放大缩小 / 对数 / 自己画线（2026-10-17 用户：「简化成交操作」「精确趋势线」）──
// 每张图各自记着（box._zv[周期] = {k: 显示几根, back: 离最新几根}）；对数每个周期的默认记在这台设备（默认月K 用对数）；
// 趋势线按影线 / 按收盘、自己画的线也记在这台设备的浏览器里（qbreak.tlm / qbreak.lines）。只展示，不下单。
let TLM='w', LOGD={D:false, W:false, M:true}, ULS={};
try{ const v=localStorage.getItem('qbreak.tlm'); if(v==='c' || v==='w') TLM=v; }catch(x){}
try{ const v=JSON.parse(localStorage.getItem('qbreak.log')||'null'); if(v && typeof v==='object') for(const k in LOGD) if(typeof v[k]==='boolean') LOGD[k]=v[k]; }catch(x){}
try{ const v=JSON.parse(localStorage.getItem('qbreak.lines')||'null'); if(v && typeof v==='object' && !Array.isArray(v)) ULS=v; }catch(x){}
function ulSave(){ try{ localStorage.setItem('qbreak.lines', JSON.stringify(ULS)); }catch(x){} }
function ulOf(t){ const a=ULS[t]; return Array.isArray(a) ? a.filter(u=>u && (u.k==='h' ? u.p>0 : u.k==='s' && u.p1>0 && u.p2>0 && u.d1 && u.d2)) : []; }
function idxOf(D, d){ let i=D.d.indexOf(d); if(i>=0) return i; for(i=0;i<D.d.length;i++) if(D.d[i]>=d) return i; return D.d.length-1; }   // 日期 → 这个周期里的第几根（周K / 月K：那一根所在的）
export function kRedraw(bx, btn){                                           // 重画一张图、页面不跳（2026-10-17 用户：点日 / 周 / 月、量 / MACD / DMI 页面滚动了）
  const sel = btn && btn.dataset && btn.dataset.act ? '[data-act="'+btn.dataset.act+'"]'+(btn.dataset.v!=null ? '[data-v="'+btn.dataset.v+'"]' : '') : null;
  const yb = btn ? btn.getBoundingClientRect().top : 0, yx=bx.getBoundingClientRect().top;
  bx.style.minHeight=bx.offsetHeight+'px';                                  // 画的时候先撑住高度，下面的内容不往上缩
  drawK(bx);
  bx.style.minHeight='';
  const nb = sel ? bx.querySelector(sel) : null;
  const dy = nb ? nb.getBoundingClientRect().top-yb : bx.getBoundingClientRect().top-yx;   // 刚按的按钮（没了 → 图本身）放回原来的屏幕位置
  if(Math.abs(dy)>0.5) window.scrollBy(0, dy);
  if(nb) nb.focus({preventScroll:true});                                    // 重画后焦点留在刚按的按钮上（键盘用）
}
let RAF=null;
function kSoon(bx){ if(RAF) return; RAF=requestAnimationFrame(()=>{ RAF=null; kRedraw(bx); }); }   // 拖动 / 捏合时一帧最多重画一次
export function drawK(box){
  const t=box.dataset.t, P=KD[t];
  box.removeAttribute('data-retry'); box.removeAttribute('role'); box.onkeydown=null; box.onblur=null; box._hide=null; box._show=null;
  box.onpointerdown=box.onpointermove=box.onpointerup=box.onpointercancel=box.onpointerleave=box.onwheel=null;
  const empty=s=>{ box.className='chart empty muted small'; box.removeAttribute('tabindex'); box.textContent=s; };
  const retry=s=>{ empty(s); box.setAttribute('data-retry', '1'); box.setAttribute('role', 'button'); box.tabIndex=0; };
  if(P==null || P==='loading') return empty('K 线载入中…');
  if(P==='none') return empty('K 线在执行器下一次运行之后显示');
  if(P==='auth') return empty('这台设备没被认出来：正在刷新…');
  if(P==='timeout') return retry(CFG.remote ? 'Mac 可能在睡眠：取不到（超过 15 秒没有回应；点这里再试）' : 'K 线取不到（面板超过 15 秒没有回应）：点这里再试');
  if(P==='error') return retry('K 线取不到（面板连不上？）：点这里再试');
  let tf=box.dataset.tf, sub=box.dataset.sub;                              // 这张图自己的周期 / 小图：第一次画时用最近一次选的，之后各自记着
  if(!TFS[tf]) tf=box.dataset.tf=TF;
  if(!SUBS[sub]) sub=box.dataset.sub=SUB;
  const tlm = box.dataset.tlm==='c' || box.dataset.tlm==='w' ? box.dataset.tlm : (box.dataset.tlm=TLM);
  const lgs = box._lg || (box._lg={...LOGD}), zvs = box._zv || (box._zv={});
  box.className='chart'; box.textContent='';
  const D=(P.tf||{})[tf];
  const top=kBar(box, 'ktop', 'ktf', TFS, tf, 'K 线的周期', '每根 = 1 '+KU[tf]);   // 类名不用 top：页头的 .top 是 sticky
  if(!D || !D.d || D.d.length<2){ box.removeAttribute('tabindex'); nd('div','muted small','没有'+TFS[tf]+'的数据（上市不久？换一个周期看看）',box); return; }
  box.tabIndex=0;
  const held=P.kind==='stock', N=D.d.length, TL=(tlm==='c' ? D.tlc : D.tl) || null;
  const H2=56, gap=16;                                                      // 小图三种一样高：切换时下边沿的按钮不跳
  const cs=getComputedStyle(box), inner=box.clientWidth-(parseFloat(cs.paddingLeft)||0)-(parseFloat(cs.paddingRight)||0);
  const W=Math.max(260, Math.round(inner>0 ? inner : 300)), x0=2, x1=W-56, padT=8, H1=176, padB=18;
  const slots=Math.max(4, Math.floor((x1-x0)/6));                          // 默认一根 K 线占 6px：手机约 40 根，Mac 约 100 根（右边留出趋势线往后延长的几根）
  const PJ0=TL && (TL.sup || TL.res) ? (TL.proj||0) : 0;
  const zv=zvs[tf] || (zvs[tf]={}), kmin=Math.min(N, 10);
  const k=Math.max(Math.min(2, N), Math.min(N, zv.k ? Math.max(kmin, zv.k) : slots-PJ0));
  const back=Math.max(0, Math.min(N-k, zv.back||0)); zv.back=back; zv.kcur=k;          // 离最新几根（0 = 看到最新）
  const E=N-back, s0=E-k, PJ=back===0 ? PJ0 : 0, step=(x1-x0)/(k+PJ);     // 看的是 [s0, E)；往后延长的线只在看到最新时画
  const X=i=> x0+(i-s0+0.5)*step, bw=Math.max(1, Math.min(13, step*0.68));
  const vb=padT+H1+gap+H2, H=vb+padB;
  const zg=nd('div','kzg',null,top); zg.setAttribute('role','group'); zg.setAttribute('aria-label','放大缩小（拖动图看更早）');
  kBtn(zg, '−', 'kz', 'out', '缩小（看更多根）').disabled = k>=N;
  kBtn(zg, '＋', 'kz', 'in', '放大（看更少根）').disabled = k<=kmin;
  const lg=!!lgs[tf];
  const refs=[];
  if(held && P.entry_px) refs.push(['ref','买入价',P.entry_px]);
  if(held && P.stop_px) refs.push(['stop','止损',P.stop_px]);
  const ords=tf==='D' ? ((CFG.ords||{})[t]||[]) : [], nolim=[];                // 今天的单只画在日K 上（周K / 月K 太挤）
  for(const o of ords){                                                     // 今天要成交的单：有限价的画成线，寄付 / 开盘价的写在图下面
    const lab=(o.s==='B' ? '买 ' : '卖 ')+fmt(o.n)+' '+o.u+(o.c ? '（'+o.c+'）' : '');
    if(o.lim>0) refs.push([o.s==='B' ? 'ob' : 'os', lab+(o.s==='B' ? ' ≤ ' : ' ≥ '), o.lim]); else nolim.push(lab);
  }
  const uls=ulOf(t).filter(u=>u.k==='h' || u.tf===tf);
  let lo=Infinity, hi=-Infinity;
  for(let i=s0;i<E;i++){
    if(D.l[i]!=null) lo=Math.min(lo, D.l[i]); if(D.h[i]!=null) hi=Math.max(hi, D.h[i]);
    for(const [m] of MAS){ const v=D[m] && D[m][i]; if(v!=null){ lo=Math.min(lo, v); hi=Math.max(hi, v); } }
  }
  const sp0=hi-lo;
  for(const r of refs) if(r[0]==='ref' || r[0]==='stop' || (r[2]>=lo-0.3*sp0 && r[2]<=hi+0.3*sp0)){ lo=Math.min(lo, r[2]); hi=Math.max(hi, r[2]); }   // 离得太远的单不拉大坐标
  for(const u of uls) if(u.k==='h' && u.p>=lo-0.3*sp0 && u.p<=hi+0.3*sp0){ lo=Math.min(lo, u.p); hi=Math.max(hi, u.p); }
  const tly=(L,i)=> L.y1+L.b*(i-L.i1);                                      // 趋势线在第 i 根的值（i 可以超过最后一根 = 往后延长）
  if(TL){ const sp=hi-lo; for(const s of ['sup','res']){ const L=TL[s]; if(!L) continue;
    for(const v of [tly(L,E-1), tly(L,E-1+PJ)]) if(v>=lo-0.25*sp && v<=hi+0.25*sp){ lo=Math.min(lo,v); hi=Math.max(hi,v); } } }   // 离得太远的线不拉大坐标，超出的部分裁掉
  const pad=(hi-lo)*0.05 || hi*0.02 || 1; lo-=pad; hi+=pad;
  const LG=lg && lo>0, llo=LG ? Math.log(lo) : 0, lhi=LG ? Math.log(hi) : 0;
  const Y=v=> LG ? padT+H1-(Math.log(Math.max(v, 1e-9))-llo)/(lhi-llo)*H1 : padT+H1-(v-lo)/(hi-lo)*H1;
  const iY=y=>{ const f=(padT+H1-y)/H1; return LG ? Math.exp(llo+f*(lhi-llo)) : lo+f*(hi-lo); };   // 屏幕 → 价格（画线用）
  const head=nd('div','legend',null,box); legend(head, D, E-1, tf);
  const ro=nd('div','ro',null,box); readout(ro, D, E-1, P, tf);             // 读数固定在图上面（不盖住 K 线）：默认看到的最后一根，点 / 指到哪根就是哪根
  const tr=(P.trend||{})[tf], c0=D.c[s0], c1=D.c[E-1];
  const wrap=nd('div','ksv',null,box);                                      // 图 + 浮在右上角的「最新 ›」（往前翻着看时）
  const svg=sv('svg',{viewBox:'0 0 '+W+' '+H, width:W, height:H, role:'img',
    'aria-label':tlab(t)+' '+TFS[tf]+'（'+(back ? sdate(D.d[s0], tf)+'〜'+sdate(D.d[E-1], tf)+' 的 ' : '最近 ')+k+' '+KU[tf]+(LG ? '，对数坐标' : '')+'）：'+pxs(c0)+' → '+pxs(c1)+(tr && !back ? '，'+((KPL.label||{})[tr.label] || tr.label) : '')}, wrap);
  for(const v of (LG ? logTicks(lo, hi) : nice(lo, hi, 4))){
    const y=Math.round(Y(v))+0.5; sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':'grid'}, svg);
    sv('text',{x:x1+6, y:y+4, 'class':'ax'}, svg).textContent=pxs(v);
  }
  let lastX=-1e9, prev=null;
  for(let i=s0;i<E;i++){
    const d=D.d[i], y=d.slice(0,4), m=+d.slice(5,7); let lab=null;
    const key = tf==='M' ? y : tf==='W' ? y+'-'+Math.floor((m-1)/3) : d.slice(0,7);   // 日K 每月、周K 每季、月K 每年标一次
    if(prev!=null && key!==prev) lab = tf==='M' ? y : (prev.slice(0,4)!==y ? y.slice(2)+' 年' : m+' 月');
    prev=key;
    const x=X(i);
    if(lab && x-lastX>=44 && x>=x0+14 && x<=x1-14){ sv('text',{x:x, y:H-4, 'class':'ax', 'text-anchor':'middle'}, svg).textContent=lab; lastX=x; }
  }
  for(let i=s0;i<E;i++){
    const o=D.o[i], h=D.h[i], l=D.l[i], c=D.c[i]; if(c==null) continue;
    const up=c>=(o==null?c:o), x=X(i), cls=up?'cu':'cd';
    const xx=Math.round(x)+0.5;
    sv('line',{x1:xx, x2:xx, y1:Y(h==null?c:h), y2:Y(l==null?c:l), 'class':'wk '+cls}, svg);
    const yt=Y(Math.max(o==null?c:o, c)), yb=Y(Math.min(o==null?c:o, c)), lv=isLive(P, D, i, tf);
    sv('rect',{x:(x-bw/2).toFixed(1), y:yt.toFixed(1), width:bw.toFixed(1), height:Math.max(1, yb-yt).toFixed(1), 'class':'bd '+cls+(lv ? ' live' : '')}, svg);
    if(lv) sv('text',{x:(x+bw/2).toFixed(1), y:Math.max(padT+9, Y(h==null?c:h)-5).toFixed(1), 'class':'lv', 'text-anchor':'end'}, svg).textContent=P.live.open ? '盘中' : '暂定';   // 右边对齐这一根（不压到价格轴），描边盖住后面的线
  }
  const path=a=>{ let s='', pen=false; for(let i=s0;i<E;i++){ const v=a[i]; if(v==null){ pen=false; continue; } s+=(pen?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1); pen=true; } return s; };
  for(const [m,,cls] of MAS.slice().reverse()) if(D[m]) sv('path',{d:path(D[m]), 'class':'ma '+cls}, svg);
  const cid='kc'+(++CPN), cp=sv('clipPath',{id:cid}, sv('defs',{},svg)); sv('rect',{x:x0, y:padT, width:x1-x0, height:H1}, cp);
  const g=sv('g',{'clip-path':'url(#'+cid+')'}, svg);
  const line=(f, a, b)=>{ if(!LG) return 'M'+X(a).toFixed(1)+' '+Y(f(a)).toFixed(1)+'L'+X(b).toFixed(1)+' '+Y(f(b)).toFixed(1);   // 价格上的直线：对数坐标时按根取点（是曲线）
    let s=''; const n=Math.max(1, Math.ceil(b-a)); for(let j=0;j<=n;j++){ const i=a+(b-a)*j/n; s+=(j?'L':'M')+X(i).toFixed(1)+' '+Y(f(i)).toFixed(1); } return s; };
  if(TL && (TL.sup || TL.res)){
    for(const [s, lab, below] of [['sup','支撑',true],['res','压力',false]]){
      const L=TL[s]; if(!L) continue;
      const ia=Math.max(L.i1, s0), ie=E-1; if(ia>ie) continue;
      const f=i=> tly(L,i);
      if(TL.tol>0){                                                         // 容差带：离线这么近算碰到，收盘出了带子才算破
        const n=LG ? Math.max(1, Math.ceil(ie+PJ-ia)) : 1, up=[], dn=[];
        for(let j=0;j<=n;j++){ const i=ia+(ie+PJ-ia)*j/n; up.push(X(i).toFixed(1)+' '+Y(f(i)+TL.tol).toFixed(1)); dn.unshift(X(i).toFixed(1)+' '+Y(Math.max(f(i)-TL.tol, 1e-9)).toFixed(1)); }
        sv('path',{d:'M'+up.join('L')+'L'+dn.join('L')+'Z', 'class':'tlb'}, g);
      }
      sv('path',{d:line(f, ia, ie), 'class':'tl'}, g);
      if(PJ>0) sv('path',{d:line(f, ie, ie+PJ), 'class':'tlp'}, g);
      for(const ii of [L.i1, L.i2]) if(ii>=s0 && ii<E) sv('circle',{cx:X(ii).toFixed(1), cy:Y(f(ii)).toFixed(1), r:2.6, 'class':'tla'}, g);
      const yl=Y(f(ie+PJ)), ye=Math.max(padT+11, Math.min(padT+H1-3, below ? yl+13 : yl-6));   // 标签留在图里
      sv('text',{x:(x1-3).toFixed(1), y:ye.toFixed(1), 'class':'rl', 'text-anchor':'end'}, g).textContent=lab+' '+pxs(back ? f(ie) : L.now);
    }
    for(const [ii, kd] of (TL.ev||[])){                                    // ▲ 收盘冲过压力线 / ▼ 收盘跌破支撑线（各自当时的线；连续几根只标第一次）
      if(ii<s0 || ii>=E) continue;
      const x=X(ii).toFixed(1);
      if(kd==='rb'){ const y=Math.min(padT+H1-8, Y(D.l[ii]!=null ? D.l[ii] : D.c[ii])+4); sv('path',{d:'M'+x+' '+y.toFixed(1)+'l3.5 6h-7z', 'class':'tbu'}, g); }
      else { const y=Math.max(padT+8, Y(D.h[ii]!=null ? D.h[ii] : D.c[ii])-4); sv('path',{d:'M'+x+' '+y.toFixed(1)+'l3.5 -6h-7z', 'class':'tbd'}, g); }
    }
  }
  for(const u of uls){                                                      // 自己画的线：水平线 = 价位；斜线 = 两个点（画在对数图上的按对数连）
    if(u.k==='h'){ const y=Math.round(Y(u.p))+0.5; sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':'ul'}, g);
      sv('text',{x:(x1-3).toFixed(1), y:(y-4).toFixed(1), 'class':'rl ult', 'text-anchor':'end'}, g).textContent='我的线 '+pxs(u.p); continue; }
    const i1=idxOf(D, u.d1), i2=idxOf(D, u.d2); if(i1===i2) continue;
    const f=u.lg ? (i=> Math.exp(Math.log(u.p1)+(Math.log(u.p2)-Math.log(u.p1))*(i-i1)/(i2-i1))) : (i=> u.p1+(u.p2-u.p1)*(i-i1)/(i2-i1));
    const a=Math.max(Math.min(i1, i2), s0), b=E-1+PJ; if(a>b) continue;
    const LG0=LG; const pth=(LG0===!!u.lg) ? 'M'+X(a).toFixed(1)+' '+Y(f(a)).toFixed(1)+'L'+X(b).toFixed(1)+' '+Y(f(b)).toFixed(1)   // 同一种坐标：直线
      : (()=>{ let s=''; const n=Math.max(1, Math.ceil(b-a)); for(let j=0;j<=n;j++){ const i=a+(b-a)*j/n; s+=(j?'L':'M')+X(i).toFixed(1)+' '+Y(f(i)).toFixed(1); } return s; })();
    sv('path',{d:pth, 'class':'ul'}, g);
    for(const ii of [i1, i2]) if(ii>=s0 && ii<E) sv('circle',{cx:X(ii).toFixed(1), cy:Y(f(ii)).toFixed(1), r:2.6, 'class':'ula'}, g);
    if(f(E-1)>0) sv('text',{x:(x1-3).toFixed(1), y:Math.max(padT+11, Math.min(padT+H1-3, Y(f(E-1))-4)).toFixed(1), 'class':'rl ult', 'text-anchor':'end'}, g).textContent='我的线 '+pxs(f(E-1));
  }
  if(box._draw && box._dp && box._dp.tf===tf){ const i=idxOf(D, box._dp.d); if(i>=s0 && i<E) sv('circle',{cx:X(i).toFixed(1), cy:Y(box._dp.p).toFixed(1), r:4, 'class':'ula on'}, g); }
  let prevY=null;
  refs.sort((a, b)=>b[2]-a[2]);                                             // 从上往下排，标签挤在一起时往下错开
  for(const [cls, lab, v] of refs){
    const y=Math.round(Y(v))+0.5; if(y<padT-2 || y>padT+H1+2) continue;      // 坐标外（离得太远的单）：不画，图下面照样写
    sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':cls}, svg);
    const ty = prevY!=null && (y-4)-prevY<13 ? prevY+13 : y-4; prevY=ty;
    const od=cls==='ob' || cls==='os';
    sv('text',{x:x0+4, y:ty, 'class':'rl'+(od ? ' '+cls+'t' : '')}, svg).textContent=lab+(od ? '' : ' ')+pxs(v);
  }
  const mark = held ? [P.entry_date, '买入'] : (P.signal_date ? [P.signal_date, '信号'] : null);
  if(mark && mark[0] && D.d[s0]<=mark[0]){
    let ie=-1; for(let i=s0;i<E;i++) if(D.d[i]>=mark[0]){ ie=i; break; }
    if(ie>=0 && D.l[ie]!=null){
      const cx=X(ie), cy=Math.min(padT+H1-2, Y(D.l[ie])+9);
      sv('path',{d:'M'+cx+' '+(cy-5)+'l4 7h-8z', 'class':'mk'}, svg);
      sv('text',{x:cx, y:Math.min(padT+H1+8, cy+13), 'class':'rl', 'text-anchor':'middle'}, svg).textContent=mark[1];
    }
  }
  const st=vb-H2, pth=(a,F)=>{ let s='', pen=false; for(let i=s0;i<E;i++){ const v=a && a[i]; if(v==null){ pen=false; continue; } s+=(pen?'L':'M')+X(i).toFixed(1)+' '+F(v).toFixed(1); pen=true; } return s; };
  let sl=null;
  if(sub==='macd'){                                                         // MACD：柱 = DIF − DEA（规则的定义），0 轴居中
    let m=0; for(let i=s0;i<E;i++) for(const a of [D.dif,D.dea,D.mh]){ const v=a && a[i]; if(v!=null) m=Math.max(m, Math.abs(v)); }
    if(m>0){
      const F=v=> st+H2/2-v/m*(H2/2-2), z=Math.round(F(0))+0.5;
      sv('line',{x1:x0, x2:x1, y1:z, y2:z, 'class':'zl'}, svg);
      for(let i=s0;i<E;i++){ const v=D.mh && D.mh[i]; if(v==null) continue; const y=F(v);
        sv('rect',{x:(X(i)-bw/2).toFixed(1), y:Math.min(z,y).toFixed(1), width:bw.toFixed(1), height:Math.max(0.5, Math.abs(y-z)).toFixed(1), 'class':v>=0?'mhu':'mhd'}, svg); }
      sv('path',{d:pth(D.dif,F), 'class':'s1 dif'}, svg); sv('path',{d:pth(D.dea,F), 'class':'s1 dea'}, svg);
      sv('text',{x:x1+6, y:z+4, 'class':'ax'}, svg).textContent='0';
    }
  } else if(sub==='dmi'){                                                   // DMI：+DI 红实线、−DI 绿虚线、ADX 紫、ADXR 蓝点线
    let m=30; for(let i=s0;i<E;i++) for(const a of [D.pdi,D.mdi,D.adx,D.adxr]){ const v=a && a[i]; if(v!=null) m=Math.max(m, v); }
    const F=v=> vb-v/m*(H2-2);
    for(const [a,cls] of [[D.adxr,'adxr'],[D.adx,'adx'],[D.mdi,'mdi'],[D.pdi,'pdi']]) if(a) sv('path',{d:pth(a,F), 'class':'s1 '+cls}, svg);
    sv('text',{x:x1+6, y:st+9, 'class':'ax'}, svg).textContent=String(Math.round(m));
  } else {
    let vmax=0; for(let i=s0;i<E;i++) vmax=Math.max(vmax, D.v[i]||0);
    if(vmax>0) for(let i=s0;i<E;i++){
      const h=(D.v[i]||0)/vmax*H2; if(h<0.5) continue;
      const up=D.c[i]!=null && D.o[i]!=null ? D.c[i]>=D.o[i] : true;
      sv('rect',{x:(X(i)-bw/2).toFixed(1), y:(vb-h).toFixed(1), width:bw.toFixed(1), height:h.toFixed(1), 'class':'vl '+(up?'cu':'cd')}, svg);
    }
    if(vmax>0) sv('text',{x:x1+6, y:vb-H2+9, 'class':'ax'}, svg).textContent=vfmt(vmax)+(P.kind==='core' ? ' 口' : ' 股');
  }
  if(sub!=='v'){ sl=sv('text',{x:x0+2, y:st-5, 'class':'sl'}, svg); sl.textContent=subText(D, E-1, sub); }
  sv('line',{x1:x0, x2:x1, y1:vb+0.5, y2:vb+0.5, 'class':'grid'}, svg);
  const xh=sv('line',{x1:0, x2:0, y1:padT, y2:vb, 'class':'xh', visibility:'hidden'}, svg);
  const yh=sv('line',{x1:x0, x2:x1, y1:0, y2:0, 'class':'xh', visibility:'hidden'}, svg);
  if(back>0){ const lb=kBtn(wrap, '最新 ›', 'kz', 'end', '回到最新'); lb.classList.add('klast'); lb.style.right=(W-x1+6)/W*100+'%'; lb.style.top=(padT+H1-34)+'px'; }   // 价格图的右下角（TradingView 一样的位置）
  const bot=kBar(box, 'kbot', 'ksub', SUBS, sub, '下面的小图显示什么');      // 下边沿：量 / MACD / DMI + 对数 / 自己画线
  const zg2=nd('div','kzg',null,bot);
  kBtn(zg2, '对数', 'klog', null, '对数坐标（涨跌幅一样的距离一样高）', lg);
  kBtn(zg2, '✎', 'kdraw', null, '自己画线（存在这台设备）', !!box._draw);
  if(box._draw){                                                            // 画线：水平线 = 点一下；斜线 = 点两个点（存在这台设备）
    const dr=nd('div','kdraw',null,box), g=nd('div','seg sm',null,dr);
    g.setAttribute('role','group'); g.setAttribute('aria-label','画什么线');
    for(const [m, lab] of [['h','水平线'],['s','斜线']]){ const b=nd('button',null,lab,g); b.type='button'; b.dataset.act='kdm'; b.dataset.v=m; b.setAttribute('aria-pressed', (box._dm||'h')===m ? 'true' : 'false'); }
    const n=ulOf(t).length;
    kBtn(dr, '撤销', 'kundo', null, '撤销最后一条').disabled = !n;
    kBtn(dr, '清除', 'kclr', null, '清除这只的线').disabled = !n;
    nd('span','hint', (box._dm||'h')==='h' ? '点图上的位置（靠近最高 / 最低 / 开盘 / 收盘会吸过去）' : (box._dp ? '再点第二个点' : '点第一个点'), dr);
  }
  kSubKey(nd('div','kexp',null,box), P, tf, sub);
  const sn=nd('div','kexp now',null,box); kSubNow(sn, D, E-1, P, tf, sub);
  let cur=null;
  const show=i=>{
    i=Math.max(s0, Math.min(E-1, i)); cur=i; const x=X(i);
    xh.setAttribute('x1',x); xh.setAttribute('x2',x); xh.setAttribute('visibility','visible');
    if(D.c[i]!=null){ const y=Y(D.c[i]); yh.setAttribute('y1',y); yh.setAttribute('y2',y); yh.setAttribute('visibility','visible'); }
    legend(head, D, i, tf); readout(ro, D, i, P, tf); if(sl) sl.textContent=subText(D, i, sub); kSubNow(sn, D, i, P, tf, sub);
    box.dataset.hover = i<N-1 ? '1' : '';                                   // 在看以前的某一根：现价刷新时先不重画
  };
  const hide=()=>{ cur=null; box.dataset.hover = back ? '1' : ''; xh.setAttribute('visibility','hidden'); yh.setAttribute('visibility','hidden'); legend(head, D, E-1, tf); readout(ro, D, E-1, P, tf);
    if(sl) sl.textContent=subText(D, E-1, sub); kSubNow(sn, D, E-1, P, tf, sub); };
  box._hide=hide; box._show=show; box.dataset.hover = back ? '1' : '';    // 往前翻着看：现价刷新时先不重画（不跳回最新）
  const sxy=ev=>{ const r=svg.getBoundingClientRect(); return [(ev.clientX-r.left)*W/r.width, (ev.clientY-r.top)*H/r.height]; };
  const at=ev=> s0+Math.floor((sxy(ev)[0]-x0)/step);
  const inSvg=ev=> ev.target && ev.target.closest && ev.target.closest('svg')===svg;
  const setZ=(nk, nb)=>{ const kk=Math.max(kmin, Math.min(N, Math.round(nk))); const bb=Math.max(0, Math.min(N-kk, Math.round(nb)));
    if(kk===k && bb===back) return false; zv.k=kk; zv.back=bb; return true; };
  const drawTap=ev=>{                                                       // 画线模式：点一下
    const [x, y]=sxy(ev); if(y<padT || y>padT+H1 || x<x0 || x>x1) return;
    const i=Math.max(s0, Math.min(E-1, at(ev))); let p=iY(y), best=10;
    for(const v of [D.h[i], D.l[i], D.o[i], D.c[i]]) if(v!=null && Math.abs(Y(v)-y)<best){ best=Math.abs(Y(v)-y); p=v; }   // 靠近这一根的高 / 低 / 开 / 收：吸过去
    p=+(p>=1000 ? Math.round(p) : p.toFixed(1)); if(!(p>0)) return;
    const a=ULS[t]=ulOf(t);
    if((box._dm||'h')==='h'){ a.push({k:'h', p:p}); ulSave(); box._dp=null; kRedraw(box); return; }
    if(!box._dp || box._dp.tf!==tf){ box._dp={tf:tf, d:D.d[i], p:p}; kRedraw(box); return; }
    if(D.d[i]===box._dp.d){ box._dp={tf:tf, d:D.d[i], p:p}; kRedraw(box); return; }   // 同一根：当成重新点第一个点
    const q=box._dp, f=q.d<D.d[i];
    a.push({k:'s', tf:tf, d1:f ? q.d : D.d[i], p1:f ? q.p : p, d2:f ? D.d[i] : q.d, p2:f ? p : q.p, lg:LG});
    ulSave(); box._dp=null; kRedraw(box);
  };
  box.onpointerdown=ev=>{                                                   // 拖动 = 看更早 / 更新；两指捏合 = 放大缩小；按住不动 = 十字线跟着手指；点一下 = 看那一根
    if(!inSvg(ev) || (ev.pointerType==='mouse' && ev.button!==0)) return;
    const z=box._pz || (box._pz={pts:{}});
    z.pts[ev.pointerId]={x:ev.clientX, y:ev.clientY};
    try{ box.setPointerCapture(ev.pointerId); }catch(x){}
    const ids=Object.keys(z.pts);
    clearTimeout(z.tm);
    if(ids.length>=2 && !box._draw){                                         // 捏合：以两指中间为中心
      const [a, b]=ids.map(k=>z.pts[k]), r=svg.getBoundingClientRect();
      Object.assign(z, {mode:'pinch', d0:Math.hypot(a.x-b.x, a.y-b.y)||1, k0:k, e0:E, f:Math.max(0, Math.min(1, (((a.x+b.x)/2-r.left)*W/r.width-x0)/(x1-x0)))});
      hide(); return;
    }
    Object.assign(z, {mode:'wait', id:ev.pointerId, x0:ev.clientX, y0:ev.clientY, b0:back, st0:step*svg.getBoundingClientRect().width/W});
    if(ev.pointerType==='mouse') show(at(ev));
    else if(!box._draw) z.tm=setTimeout(()=>{ if(z.mode==='wait'){ z.mode='scrub'; show(at(ev)); } }, 280);   // 按住不动 0.28 秒：十字线（以前的「按住左右滑」）
  };
  box.onpointermove=ev=>{
    const z=box._pz;
    if(!z || !z.pts || !z.pts[ev.pointerId]){ if(ev.pointerType==='mouse' && !ev.buttons && inSvg(ev)) show(at(ev)); return; }
    z.pts[ev.pointerId]={x:ev.clientX, y:ev.clientY};
    if(z.mode==='pinch'){
      const ids=Object.keys(z.pts); if(ids.length<2) return;
      const [a, b]=ids.map(k=>z.pts[k]), nk=z.k0*z.d0/(Math.hypot(a.x-b.x, a.y-b.y)||1);
      const kk=Math.max(kmin, Math.min(N, Math.round(nk))), ic=z.e0-z.k0+z.f*z.k0, ne=Math.round(ic+(1-z.f)*kk);
      if(setZ(kk, N-ne)) kSoon(box); return;
    }
    if(ev.pointerId!==z.id) return;
    const dx=ev.clientX-z.x0, dy=ev.clientY-z.y0;
    if(z.mode==='wait'){
      if(Math.abs(dx)>6 && Math.abs(dx)>=Math.abs(dy) && !box._draw){ clearTimeout(z.tm); z.mode='pan'; hide(); }
      else if(ev.pointerType==='mouse'){ show(at(ev)); return; }
      else if(Math.abs(dy)>8){ clearTimeout(z.tm); z.mode='none'; return; }
    }
    if(z.mode==='scrub'){ show(at(ev)); return; }
    if(z.mode==='pan'){ if(setZ(k, z.b0+dx/z.st0)) kSoon(box); }            // 往右拖 = 看更早
  };
  const end=ev=>{
    const z=box._pz; if(!z || !z.pts || !z.pts[ev.pointerId]) return;
    delete z.pts[ev.pointerId]; clearTimeout(z.tm);
    try{ box.releasePointerCapture(ev.pointerId); }catch(x){}
    if(ev.type==='pointerup' && ev.pointerId===z.id && z.mode==='wait'){ if(box._draw) drawTap(ev); else show(at(ev)); }   // 点一下
    if(!Object.keys(z.pts).length) box._pz=null;
    else if(z.mode==='pinch') z.mode='none';                                // 捏合放开一指：这次手势不再动
  };
  box.onpointerup=end; box.onpointercancel=end;                             // 竖着滑 = 页面照常滚动（浏览器接手 → pointercancel）
  box.onpointerleave=ev=>{ if(ev.pointerType==='mouse' && !box._pz) hide(); };
  box.onwheel=ev=>{                                                         // Mac 触控板：捏合（ctrl + 滚轮）= 放大缩小、左右滑 = 看更早 / 更新；上下滚照常滚页面
    if(!inSvg(ev)) return;
    if(ev.ctrlKey){ ev.preventDefault(); if(setZ(k*Math.exp(ev.deltaY*0.01), back)) kSoon(box); return; }
    if(Math.abs(ev.deltaX)>Math.abs(ev.deltaY)){ ev.preventDefault(); box._wx=(box._wx||0)-ev.deltaX;
      const nb=Math.trunc(box._wx/Math.max(1, step*svg.getBoundingClientRect().width/W)); if(nb){ box._wx-=nb*step*svg.getBoundingClientRect().width/W; if(setZ(k, back+nb)) kSoon(box); } }
  };
  box.onkeydown=ev=>{                                                       // 用属性不用 addEventListener：重画时换掉、不越积越多
    if(ev.target!==box) return;                                             // 按钮上按的键不动十字线
    if(ev.key==='ArrowLeft' || ev.key==='ArrowRight'){ ev.preventDefault();
      const i=(cur==null ? E-1 : cur)+(ev.key==='ArrowLeft' ? -1 : 1);
      if((i<s0 && back<N-k) || (i>=E && back>0)){ setZ(k, back+(i<s0 ? 1 : -1)); kRedraw(box); box.focus({preventScroll:true}); if(box._show) box._show(i); return; }   // 到边上：往前 / 往后翻一根
      show(i); }
    else if(ev.key==='Home'){ ev.preventDefault(); show(s0); } else if(ev.key==='End'){ ev.preventDefault(); show(E-1); }
    else if(ev.key==='+' || ev.key==='='){ ev.preventDefault(); if(setZ(k/1.5, back)){ kRedraw(box); box.focus({preventScroll:true}); } }
    else if(ev.key==='-'){ ev.preventDefault(); if(setZ(k*1.5, back)){ kRedraw(box); box.focus({preventScroll:true}); } }
    else if(ev.key==='Escape') hide();
  };
  box.onblur=hide;
  if(tr && !back) kTrend(nd('div','kexp',null,box), tr, tf);
  if(nolim.length) kPut(nd('div','kexp',null,box), [['今天要成交的单：'], [nolim.join('、'), 'px'], ['（开盘价 / 没有限价，图上没有价位线）']]);
  if(D.tl || D.tlc) kTL(nd('div','kexp',null,box), TL, tf, D, tlm);
}
function logTicks(lo, hi){                                                  // 对数坐标的刻度：1 / 2 / 5 × 10^n，太密就隔开
  const out=[]; for(let e=Math.floor(Math.log10(lo)); e<=Math.ceil(Math.log10(hi)); e++) for(const m of [1, 2, 5]){ const v=m*Math.pow(10, e); if(v>=lo && v<=hi) out.push(v); }
  if(out.length>=3) return out;
  return nice(lo, hi, 4);                                                   // 范围窄（不到 2.5 倍）：照普通的刻度
}
document.addEventListener('click', e=>{                                     // 图上的小按钮：缩放 / 对数 / 画线 / 趋势线怎么连（重画这一张；页面不跳）
  const b=e.target.closest('.chart[data-t] [data-act]'); if(!b) return;
  const a=b.dataset.act, bx=b.closest('.chart[data-t]'), tf=bx.dataset.tf, zv=((bx._zv||(bx._zv={}))[tf]||(bx._zv[tf]={}));
  if(a==='kz'){
    const P=KD[bx.dataset.t], D=P && P.tf && P.tf[tf]; if(!D) return;
    const N=D.d.length, cur=zv.kcur || zv.k || Math.min(N, 40);          // 现在显示几根（drawK 记的）
    if(b.dataset.v==='end') zv.back=0;
    else zv.k=Math.max(Math.min(N, 10), Math.min(N, Math.round(cur*(b.dataset.v==='in' ? 2/3 : 1.5))));
  } else if(a==='klog'){ const lg=bx._lg || (bx._lg={...LOGD}); lg[tf]=!lg[tf]; LOGD[tf]=lg[tf]; try{ localStorage.setItem('qbreak.log', JSON.stringify(LOGD)); }catch(x){} }
  else if(a==='kdraw'){ bx._draw=!bx._draw; bx._dp=null; }
  else if(a==='kdm'){ bx._dm=b.dataset.v; bx._dp=null; }
  else if(a==='kundo'){ const u=ulOf(bx.dataset.t); u.pop(); ULS[bx.dataset.t]=u; ulSave(); }
  else if(a==='kclr'){ const n=ulOf(bx.dataset.t).length; delete ULS[bx.dataset.t]; ulSave(); bx._dp=null; toast('已清除 '+n+' 条自己画的线（这台设备）'); }
  else if(a==='ktlm'){ bx.dataset.tlm=TLM=b.dataset.v; try{ localStorage.setItem('qbreak.tlm', TLM); }catch(x){} }
  else return;
  kRedraw(bx, b);
});
export async function showK(box){
  const t=box.dataset.t, s=KD[t];
  if(!s || s==='error' || s==='timeout' || s==='loading'){ drawK(box); await loadK(t); }
  drawK(box);
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(b!==box && b.dataset.t===t && b.offsetParent!==null) drawK(b); });   // 同一只票的别的图
}
function drawAll(){
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(KD[b.dataset.t] && b.offsetParent!==null) drawK(b); });
}
const IO = ('IntersectionObserver' in window) ? new IntersectionObserver(es=>{ for(const e of es) if(e.isIntersecting){ IO.unobserve(e.target); showK(e.target); } }, {rootMargin:'200px'}) : null;
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('.chart[data-t]').forEach(b=>{ if(IO) IO.observe(b); else showK(b); });
});
document.addEventListener('toggle', e=>{ if(e.target.tagName==='DETAILS' && e.target.open) e.target.querySelectorAll('.chart[data-t]').forEach(b=>{   // 打开的那块里的图：按现在的宽度重画
  if(KD[b.dataset.t] && KD[b.dataset.t]!=='loading') drawK(b);
  else if(!KD[b.dataset.t] && !b.closest('details:not([open])')){ if(IO) IO.unobserve(b); showK(b); }   // 还没取过、现在看得到（「规则接下来会自动买」点开的一行等）：马上取，不等滚到
}); }, true);
document.addEventListener('pointerdown', ev=>{ if(!ev.target.closest('.chart')) document.querySelectorAll('.chart').forEach(b=>{ if(b._hide) b._hide(); }); });
let RZ=null, LW=window.innerWidth;
window.addEventListener('resize', ()=>{ clearTimeout(RZ); RZ=setTimeout(()=>{ if(Math.abs(window.innerWidth-LW)>2){ LW=window.innerWidth; drawAll(); } }, 150); });
