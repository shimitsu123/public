// qbreak 操作面板：kline.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/kline.js 提供；不要用构建工具）
import { CFG, nd, pcs, pxs } from './core.js';
import { req } from './net.js';

// ── K 线（同花顺式：红 = 涨（空心）、绿 = 跌（实心）；5 / 10 / 20 / 30 日均价；买入价 / 止损线）──
// 每张图自己的按钮（2026-10-07 用户：「K线的日周月button 要显示在每个K线的上面边沿方便看 / 量 MACD DMI 显示在每个K线的下面」）：
//   上边沿 = 日K / 周K / 月K，下边沿 = 量 / MACD / DMI；每张图各自切换，新打开的图用最近一次选的（记在这台设备的浏览器里）
// 说明都用日常的话（同日：「K线解释换成通俗易懂的说法 横展开」）：标签的说法来自 qbreak/kline.py（CFG.kp），其余按图里的数字现算
// 小图：量 / MACD（规则同一组参数）/ DMI（同花顺写法）；趋势线：连低点的支撑线、连高点的压力线（qbreak/trendline.py）+ 往后延长的点线 + 破线点
// 数据 = 执行器每次运行写的 out/charts_<账本>.json，打开 / 看到哪只票才取（/api/chart）；只展示
// 每张图不带说明 / 数字表（2026-10-15 用户：「整体留一个解释就行」「不需要最近十个月的数字 看图就行」）：
//   整页一份「怎么看 K 线图」在选股最下面（服务器画：panel._kline_help）；图下面只留各自的一句话（最新一根、现在的趋势、趋势线）
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
function loadK(t){
  if(KD[t] && KD[t]!=='error' && KD[t]!=='timeout' && KD[t]!=='loading') return Promise.resolve(KD[t]);
  if(KP[t]) return KP[t];                                                   // 同一只票已经在取：等同一个请求
  KD[t]='loading';
  const p=(async()=>{
    try{
      const x=await req('/api/chart?book='+encodeURIComponent(CFG.book)+'&t='+encodeURIComponent(t), {credentials:'same-origin', cache:'no-store'});
      if(x.r.status===404) KD[t]='none';
      else if(x.r.status===401){ KD[t]='auth'; setTimeout(()=>location.reload(), 1500); }   // 这台设备没被认出来：刷新（会到配对页）
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
function kSubKey(el, P, tf, sub){                                          // 小图的图例（意思在选股最下面的「怎么看 K 线图」里）
  el.textContent='';
  const row=nd('div','legend',null,el);
  const k=(c, t)=>{ const sp=nd('span',null,null,row); nd('i','key '+c,null,sp); sp.appendChild(document.createTextNode(t)); };
  if(sub==='macd'){ k('dif','快线'); k('dea','慢线'); k('box mhu','柱 = 快线 − 慢线'); nd('span',null,'MACD '+((P.ind||{}).macd||[12,26,9]).join(','),row); }
  else if(sub==='dmi'){ k('pdi','+DI 买方'); k('mdi','−DI 卖方'); k('adx','ADX 趋势强度'); k('adxr','ADXR'); nd('span',null,'DMI '+((P.ind||{}).dmi||[14,6]).join(','),row); }
  else { k('box cu','涨'); k('box cd','跌'); nd('span',null,'成交量（'+(P.kind==='core' ? '口' : '股')+'）',row); }
}
function kSubNow(el, D, i, P, tf, sub){                                    // 小图「这一根」一句话（跟着十字线走）
  let s='';
  if(sub==='macd'){
    const a=D.dif && D.dif[i], b=D.dea && D.dea[i], h=D.mh && D.mh[i], h0=i>0 && D.mh ? D.mh[i-1] : null;
    if(a==null || b==null) s='K 线还不够多，算不出来';
    else {
      if(h!=null && h0!=null && h0<0 && h>=0) s='金叉（快线刚往上穿过慢线）';
      else if(h!=null && h0!=null && h0>0 && h<=0) s='死叉（快线刚往下穿过慢线）';
      else s=(a>=b ? '快线在慢线上面（涨的力量强）' : '快线在慢线下面（跌的力量强）')
             +(h!=null && h0!=null ? (Math.abs(h)>Math.abs(h0) ? '，在变强' : '，在变弱') : '');
      s+='；在 0 线'+(a>=0 ? '上面（偏涨）' : '下面（偏跌）');
    }
  } else if(sub==='dmi'){
    const p=D.pdi && D.pdi[i], m=D.mdi && D.mdi[i], x=D.adx && D.adx[i], x0=i>0 && D.adx ? D.adx[i-1] : null;
    if(p==null || m==null) s='K 线还不够多，算不出来';
    else {
      s=p>=m ? '买方强' : '卖方强';
      if(x!=null) s+='；ADX '+x.toFixed(1)+(x>=25 ? '（趋势明显）' : x<20 ? '（没什么趋势）' : '（趋势一般）')+(x0!=null ? (x>x0 ? '，在变强' : '，在变弱') : '');
    }
  } else {
    const v=D.v[i]||0; let sm=0, n=0;
    for(let j=Math.max(0, i-20); j<i; j++){ if(D.v[j]!=null){ sm+=D.v[j]; n++; } }
    s='成交 '+vfmt(v)+(P.kind==='core' ? ' 口' : ' 股')+(n>=5 && sm>0 ? '，是前 '+n+' '+KU[tf]+'平均的 '+(v/(sm/n)).toFixed(2)+' 倍' : '');
  }
  const lv=isLive(P, D, i, tf);
  el.textContent=(lv ? (P.live.open ? '今天这一根（到 '+liveAt(P)+'，还没收盘）' : '暂定的一根（1 分钟线到 '+liveAt(P)+'；正式日线在执行器下一次运行后换上）')
    : i===D.d.length-1 ? '最新一根' : sdate(D.d[i], tf))+'：'+s;
}
function kTrend(el, tr, tf){                                               // 现在的趋势（一句话；kline.py 的标签换成日常的话）
  const L=KPL.label||{}, A=KPL.align||{}, m=KMA[tf], sl=+tr.slope20_pct||0;
  nd('span',null,'现在的趋势：',el);
  nd('b', tr.label==='上升' ? 'up' : tr.label==='下降' ? 'down' : null, L[tr.label] || tr.label || '—', el);
  el.appendChild(document.createTextNode('（收盘在 20 '+m+'均价'+(tr.above20 ? '上面' : '下面')+'，20 '+m+'均价'
    +(Math.abs(sl)<0.005 ? '走平' : sl>0 ? '往上' : '往下')+'）'+(tr.align ? ' · '+(A[tr.align] || tr.align) : '')));
}
function kTL(el, TL, tf){                                                  // 现在的趋势线（一句话；图上的记号在选股最下面的「怎么看 K 线图」里）
  const C=KPL.chan||{};
  const one=(L, sup)=>{ const d=L.dist_pct;
    return (sup ? '支撑 ' : '压力 ')+pxs(L.now)+(d==null ? '' : sup ? (d<=0 ? '（比收盘低 '+Math.abs(d)+'%）' : '（已跌破）')
                                                                : (d>=0 ? '（比收盘高 '+d+'%）' : '（已冲过）')); };
  const parts=[]; if(TL.sup) parts.push(one(TL.sup, true)); if(TL.res) parts.push(one(TL.res, false));
  nd('div',null,'趋势线：'+(TL.chan ? (C[TL.chan] || TL.chan) : '只找到'+(TL.sup ? '下面' : '上面')+'的一条')+(parts.length ? ' · '+parts.join(' · ') : ''),el);
}
function kBar(box, pos, act, opts, cur, label, hint){                      // 图的上边沿（周期）/ 下边沿（小图）的按钮
  const bar=nd('div','kbar '+pos,null,box), g=nd('div','seg',null,bar);
  g.setAttribute('role','group'); g.setAttribute('aria-label',label);
  for(const k in opts){ const b=nd('button',null,opts[k],g); b.type='button'; b.dataset.act=act; b.dataset.v=k; b.setAttribute('aria-pressed', k===cur ? 'true' : 'false'); }
  if(hint) nd('span','hint',hint,bar);
  return bar;
}
export function drawK(box){
  const t=box.dataset.t, P=KD[t];
  box.removeAttribute('data-retry'); box.removeAttribute('role'); box.onkeydown=null; box.onblur=null; box._hide=null;
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
  box.className='chart'; box.textContent='';
  kBar(box, 'ktop', 'ktf', TFS, tf, 'K 线的周期', '每根 = 1 '+KU[tf]);           // 类名不用 top：页头的 .top 是 sticky
  const D=(P.tf||{})[tf];
  if(!D || !D.d || D.d.length<2){ box.removeAttribute('tabindex'); nd('div','muted small','没有'+TFS[tf]+'的数据（上市不久？换一个周期看看）',box); return; }
  box.tabIndex=0;
  const held=P.kind==='stock', N=D.d.length, TL=D.tl||null, PJ=TL && (TL.sup || TL.res) ? (TL.proj||0) : 0;
  const H2=56, gap=16;                                                      // 小图三种一样高：切换时下边沿的按钮不跳
  const cs=getComputedStyle(box), inner=box.clientWidth-(parseFloat(cs.paddingLeft)||0)-(parseFloat(cs.paddingRight)||0);
  const W=Math.max(260, Math.round(inner>0 ? inner : 300)), x0=2, x1=W-56, padT=8, H1=176, padB=18;
  const slots=Math.max(4, Math.floor((x1-x0)/6));                          // 一根 K 线占 6px：手机约 40 根，Mac 约 100 根（右边留出趋势线往后延长的几根）
  const k=Math.max(2, Math.min(N, slots-PJ)), s0=N-k, step=(x1-x0)/(k+PJ);
  const X=i=> x0+(i-s0+0.5)*step, bw=Math.max(1, Math.min(13, step*0.68));
  const vb=padT+H1+gap+H2, H=vb+padB;
  const refs=[];
  if(held && P.entry_px) refs.push(['ref','买入价',P.entry_px]);
  if(held && P.stop_px) refs.push(['stop','止损',P.stop_px]);
  let lo=Infinity, hi=-Infinity;
  for(let i=s0;i<N;i++){
    if(D.l[i]!=null) lo=Math.min(lo, D.l[i]); if(D.h[i]!=null) hi=Math.max(hi, D.h[i]);
    for(const [m] of MAS){ const v=D[m] && D[m][i]; if(v!=null){ lo=Math.min(lo, v); hi=Math.max(hi, v); } }
  }
  for(const r of refs){ lo=Math.min(lo, r[2]); hi=Math.max(hi, r[2]); }
  const tly=(L,i)=> L.y1+L.b*(i-L.i1);                                      // 趋势线在第 i 根的值（i 可以超过最后一根 = 往后延长）
  if(TL){ const sp=hi-lo; for(const s of ['sup','res']){ const L=TL[s]; if(!L) continue;
    for(const v of [tly(L,N-1), tly(L,N-1+PJ)]) if(v>=lo-0.25*sp && v<=hi+0.25*sp){ lo=Math.min(lo,v); hi=Math.max(hi,v); } } }   // 离得太远的线不拉大坐标，超出的部分裁掉
  const pad=(hi-lo)*0.05 || hi*0.02 || 1; lo-=pad; hi+=pad;
  const Y=v=> padT+H1-(v-lo)/(hi-lo)*H1;
  const head=nd('div','legend',null,box); legend(head, D, N-1, tf);
  const ro=nd('div','ro',null,box); readout(ro, D, N-1, P, tf);             // 读数固定在图上面（不盖住 K 线）：默认最新一根，点 / 指到哪根就是哪根
  const tr=(P.trend||{})[tf], c0=D.c[s0], c1=D.c[N-1];
  const svg=sv('svg',{viewBox:'0 0 '+W+' '+H, width:W, height:H, role:'img',
    'aria-label':t+' '+TFS[tf]+'（最近 '+k+' '+KU[tf]+'）：'+pxs(c0)+' → '+pxs(c1)+(tr ? '，'+((KPL.label||{})[tr.label] || tr.label) : '')}, box);
  for(const v of nice(lo, hi, 4)){
    const y=Math.round(Y(v))+0.5; sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':'grid'}, svg);
    sv('text',{x:x1+6, y:y+4, 'class':'ax'}, svg).textContent=pxs(v);
  }
  let lastX=-1e9, prev=null;
  for(let i=s0;i<N;i++){
    const d=D.d[i], y=d.slice(0,4), m=+d.slice(5,7); let lab=null;
    const key = tf==='M' ? y : tf==='W' ? y+'-'+Math.floor((m-1)/3) : d.slice(0,7);   // 日K 每月、周K 每季、月K 每年标一次
    if(prev!=null && key!==prev) lab = tf==='M' ? y : (prev.slice(0,4)!==y ? y.slice(2)+' 年' : m+' 月');
    prev=key;
    const x=X(i);
    if(lab && x-lastX>=44 && x>=x0+14 && x<=x1-14){ sv('text',{x:x, y:H-4, 'class':'ax', 'text-anchor':'middle'}, svg).textContent=lab; lastX=x; }
  }
  for(let i=s0;i<N;i++){
    const o=D.o[i], h=D.h[i], l=D.l[i], c=D.c[i]; if(c==null) continue;
    const up=c>=(o==null?c:o), x=X(i), cls=up?'cu':'cd';
    const xx=Math.round(x)+0.5;
    sv('line',{x1:xx, x2:xx, y1:Y(h==null?c:h), y2:Y(l==null?c:l), 'class':'wk '+cls}, svg);
    const yt=Y(Math.max(o==null?c:o, c)), yb=Y(Math.min(o==null?c:o, c)), lv=isLive(P, D, i, tf);
    sv('rect',{x:(x-bw/2).toFixed(1), y:yt.toFixed(1), width:bw.toFixed(1), height:Math.max(1, yb-yt).toFixed(1), 'class':'bd '+cls+(lv ? ' live' : '')}, svg);
    if(lv) sv('text',{x:(x+bw/2).toFixed(1), y:Math.max(padT+9, Y(h==null?c:h)-5).toFixed(1), 'class':'lv', 'text-anchor':'end'}, svg).textContent=P.live.open ? '盘中' : '暂定';   // 右边对齐这一根（不压到价格轴），描边盖住后面的线
  }
  const path=a=>{ let s='', pen=false; for(let i=s0;i<N;i++){ const v=a[i]; if(v==null){ pen=false; continue; } s+=(pen?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1); pen=true; } return s; };
  for(const [m,,cls] of MAS.slice().reverse()) if(D[m]) sv('path',{d:path(D[m]), 'class':'ma '+cls}, svg);
  if(PJ>0 || (TL && (TL.ev||[]).length)){
    const id='kc'+(++CPN), cp=sv('clipPath',{id:id}, sv('defs',{},svg)); sv('rect',{x:x0, y:padT, width:x1-x0, height:H1}, cp);
    const g=sv('g',{'clip-path':'url(#'+id+')'}, svg);
    for(const [s, lab, below] of [['sup','支撑',true],['res','压力',false]]){
      const L=TL[s]; if(!L) continue;
      const ia=Math.max(L.i1, s0); if(ia>N-1) continue;
      const p=(i)=> X(i).toFixed(1)+' '+Y(tly(L,i)).toFixed(1);
      sv('path',{d:'M'+p(ia)+'L'+p(N-1), 'class':'tl'}, g);
      sv('path',{d:'M'+p(N-1)+'L'+p(N-1+PJ), 'class':'tlp'}, g);
      for(const ii of [L.i1, L.i2]) if(ii>=s0 && ii<N) sv('circle',{cx:X(ii).toFixed(1), cy:Y(tly(L,ii)).toFixed(1), r:2.6, 'class':'tla'}, g);
      const ye=Math.max(padT+11, Math.min(padT+H1-3, below ? Y(tly(L,N-1+PJ))+13 : Y(tly(L,N-1+PJ))-6));   // 标签留在图里
      sv('text',{x:(x1-3).toFixed(1), y:ye.toFixed(1), 'class':'rl', 'text-anchor':'end'}, g).textContent=lab+' '+pxs(L.now);
    }
    for(const [ii, kd] of (TL.ev||[])){                                    // ▲ 收盘冲过压力线 / ▼ 收盘跌破支撑线（各自当时的线；连续几根只标第一次）
      if(ii<s0 || ii>=N) continue;
      const x=X(ii).toFixed(1);
      if(kd==='rb'){ const y=Math.min(padT+H1-8, Y(D.l[ii]!=null ? D.l[ii] : D.c[ii])+4); sv('path',{d:'M'+x+' '+y.toFixed(1)+'l3.5 6h-7z', 'class':'tbu'}, g); }
      else { const y=Math.max(padT+8, Y(D.h[ii]!=null ? D.h[ii] : D.c[ii])-4); sv('path',{d:'M'+x+' '+y.toFixed(1)+'l3.5 -6h-7z', 'class':'tbd'}, g); }
    }
  }
  let prevY=null;
  for(const [cls, lab, v] of refs){
    const y=Math.round(Y(v))+0.5; sv('line',{x1:x0, x2:x1, y1:y, y2:y, 'class':cls}, svg);
    const ty = prevY!=null && Math.abs(prevY-(y-4))<13 ? y+13 : y-4; prevY=ty;
    sv('text',{x:x0+4, y:ty, 'class':'rl'}, svg).textContent=lab+' '+pxs(v);
  }
  const mark = held ? [P.entry_date, '买入'] : (P.signal_date ? [P.signal_date, '信号'] : null);
  if(mark && mark[0] && D.d[s0]<=mark[0]){
    let ie=-1; for(let i=s0;i<N;i++) if(D.d[i]>=mark[0]){ ie=i; break; }
    if(ie>=0 && D.l[ie]!=null){
      const cx=X(ie), cy=Math.min(padT+H1-2, Y(D.l[ie])+9);
      sv('path',{d:'M'+cx+' '+(cy-5)+'l4 7h-8z', 'class':'mk'}, svg);
      sv('text',{x:cx, y:Math.min(padT+H1+8, cy+13), 'class':'rl', 'text-anchor':'middle'}, svg).textContent=mark[1];
    }
  }
  const st=vb-H2, pth=(a,F)=>{ let s='', pen=false; for(let i=s0;i<N;i++){ const v=a && a[i]; if(v==null){ pen=false; continue; } s+=(pen?'L':'M')+X(i).toFixed(1)+' '+F(v).toFixed(1); pen=true; } return s; };
  let sl=null;
  if(sub==='macd'){                                                         // MACD：柱 = DIF − DEA（规则的定义），0 轴居中
    let m=0; for(let i=s0;i<N;i++) for(const a of [D.dif,D.dea,D.mh]){ const v=a && a[i]; if(v!=null) m=Math.max(m, Math.abs(v)); }
    if(m>0){
      const F=v=> st+H2/2-v/m*(H2/2-2), z=Math.round(F(0))+0.5;
      sv('line',{x1:x0, x2:x1, y1:z, y2:z, 'class':'zl'}, svg);
      for(let i=s0;i<N;i++){ const v=D.mh && D.mh[i]; if(v==null) continue; const y=F(v);
        sv('rect',{x:(X(i)-bw/2).toFixed(1), y:Math.min(z,y).toFixed(1), width:bw.toFixed(1), height:Math.max(0.5, Math.abs(y-z)).toFixed(1), 'class':v>=0?'mhu':'mhd'}, svg); }
      sv('path',{d:pth(D.dif,F), 'class':'s1 dif'}, svg); sv('path',{d:pth(D.dea,F), 'class':'s1 dea'}, svg);
      sv('text',{x:x1+6, y:z+4, 'class':'ax'}, svg).textContent='0';
    }
  } else if(sub==='dmi'){                                                   // DMI：+DI 红实线、−DI 绿虚线、ADX 紫、ADXR 蓝点线
    let m=30; for(let i=s0;i<N;i++) for(const a of [D.pdi,D.mdi,D.adx,D.adxr]){ const v=a && a[i]; if(v!=null) m=Math.max(m, v); }
    const F=v=> vb-v/m*(H2-2);
    for(const [a,cls] of [[D.adxr,'adxr'],[D.adx,'adx'],[D.mdi,'mdi'],[D.pdi,'pdi']]) if(a) sv('path',{d:pth(a,F), 'class':'s1 '+cls}, svg);
    sv('text',{x:x1+6, y:st+9, 'class':'ax'}, svg).textContent=String(Math.round(m));
  } else {
    let vmax=0; for(let i=s0;i<N;i++) vmax=Math.max(vmax, D.v[i]||0);
    if(vmax>0) for(let i=s0;i<N;i++){
      const h=(D.v[i]||0)/vmax*H2; if(h<0.5) continue;
      const up=D.c[i]!=null && D.o[i]!=null ? D.c[i]>=D.o[i] : true;
      sv('rect',{x:(X(i)-bw/2).toFixed(1), y:(vb-h).toFixed(1), width:bw.toFixed(1), height:h.toFixed(1), 'class':'vl '+(up?'cu':'cd')}, svg);
    }
    if(vmax>0) sv('text',{x:x1+6, y:vb-H2+9, 'class':'ax'}, svg).textContent=vfmt(vmax)+(P.kind==='core' ? ' 口' : ' 股');
  }
  if(sub!=='v'){ sl=sv('text',{x:x0+2, y:st-5, 'class':'sl'}, svg); sl.textContent=subText(D, N-1, sub); }
  sv('line',{x1:x0, x2:x1, y1:vb+0.5, y2:vb+0.5, 'class':'grid'}, svg);
  const xh=sv('line',{x1:0, x2:0, y1:padT, y2:vb, 'class':'xh', visibility:'hidden'}, svg);
  const yh=sv('line',{x1:x0, x2:x1, y1:0, y2:0, 'class':'xh', visibility:'hidden'}, svg);
  kBar(box, 'kbot', 'ksub', SUBS, sub, '下面的小图显示什么');                  // 下边沿：量 / MACD / DMI
  kSubKey(nd('div','kexp',null,box), P, tf, sub);
  const sn=nd('div','kexp now',null,box); kSubNow(sn, D, N-1, P, tf, sub);
  let cur=null;
  const show=i=>{
    i=Math.max(s0, Math.min(N-1, i)); cur=i; const x=X(i);
    xh.setAttribute('x1',x); xh.setAttribute('x2',x); xh.setAttribute('visibility','visible');
    if(D.c[i]!=null){ const y=Y(D.c[i]); yh.setAttribute('y1',y); yh.setAttribute('y2',y); yh.setAttribute('visibility','visible'); }
    legend(head, D, i, tf); readout(ro, D, i, P, tf); if(sl) sl.textContent=subText(D, i, sub); kSubNow(sn, D, i, P, tf, sub);
    box.dataset.hover = i<N-1 ? '1' : '';                                   // 在看以前的某一根：现价刷新时先不重画
  };
  const hide=()=>{ cur=null; box.dataset.hover=''; xh.setAttribute('visibility','hidden'); yh.setAttribute('visibility','hidden'); legend(head, D, N-1, tf); readout(ro, D, N-1, P, tf);
    if(sl) sl.textContent=subText(D, N-1, sub); kSubNow(sn, D, N-1, P, tf, sub); };
  box._hide=hide;
  const at=ev=>{ const r=svg.getBoundingClientRect(); return s0+Math.floor(((ev.clientX-r.left)*W/r.width-x0)/step); };
  svg.addEventListener('pointermove', ev=>show(at(ev)));
  svg.addEventListener('pointerdown', ev=>show(at(ev)));
  svg.addEventListener('pointerleave', ev=>{ if(ev.pointerType!=='touch') hide(); });
  box.onkeydown=ev=>{                                                       // 用属性不用 addEventListener：重画时换掉、不越积越多
    if(ev.target!==box) return;                                             // 按钮上按的键不动十字线
    if(ev.key==='ArrowLeft' || ev.key==='ArrowRight'){ ev.preventDefault(); show((cur==null ? N-1 : cur)+(ev.key==='ArrowLeft' ? -1 : 1)); }
    else if(ev.key==='Home'){ ev.preventDefault(); show(s0); } else if(ev.key==='End'){ ev.preventDefault(); show(N-1); }
    else if(ev.key==='Escape') hide();
  };
  box.onblur=hide;
  if(tr) kTrend(nd('div','kexp',null,box), tr, tf);
  if(TL && (TL.sup || TL.res)) kTL(nd('div','kexp',null,box), TL, tf);
}
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
