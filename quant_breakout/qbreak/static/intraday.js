// qbreak 操作面板：intraday.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/intraday.js 提供；不要用构建工具）
// 盘中观测（2026-10-16 用户要求；只展示、不下单）：选股页最上面「今天盘中：规则的买点（暂定，约晚 20 分钟）」+ 持仓每只一行（收盘卖出线离现价多远）。
// 数 = /api/intraday（qbreak/intraday_watch.view：只读面板线程每 5 分钟另起进程写的结果文件，请求里不取价）；服务器先画好一份
// （panel._intraday_card / _intraday_line），这里定时重画同一个样子（交易时段每 1 分钟，其他时间每 10 分钟；回到页面 / 重新连上也再取）；
// 对话框开着 / 正在输入 / 页面在后台 → 这一次不重画（等下一次）。代码一律带名字（服务器给 label；文字里的「7203.T」用 nameify 兜底）。
import { $, CFG, nameify, nd, tipEl } from './core.js';
import { req } from './net.js';

export function intraShow(v){                                             // 重画卡片 + 持仓每只一行；v.ok=false / 没有 → 不动（保留上一次的）
  if(!v || !v.ok) return;
  const el=$('#intraday');
  if(el){
    const open={}; el.querySelectorAll('details.ia').forEach(d=>{ open[d.dataset.k]=d.open; });   // 展开着的保持展开
    el.textContent='';
    const hl=nd('div', 'ia-hl', null, el); nd('b', null, v.title, hl); tipEl(hl, v.foot);   // 页脚收进 ⓘ（2026-10-17）
    nd('div', 'muted small', nameify(v.head), el);
    if((v.warn||[]).length){                                              // ★ = 标签（箭头后面的结论），整句在 ⓘ 里
      const c=nd('div', 'chips', null, el);
      for(const w of v.warn) nd('span', 'chip bad', '★ '+nameify(w.includes('→') ? w.split('→').pop().trim() : w), c);
      tipEl(c, v.warn.map(w=>'★ '+nameify(w)));
    }
    const rows=(rs, box)=>{
      const ls=nd('div', 'list', null, box), cnt={};             // 多数行的数据时刻 → 不每行重复，只写和它不一样的
      rs.forEach(r=>{ cnt[r.at]=(cnt[r.at]||0)+1; });
      const mode=Object.keys(cnt).sort((a, b)=>cnt[b]-cnt[a])[0];
      for(const r of rs){
        const li=nd('div', 'li', null, ls), g=nd('div', 'grow', null, li);
        nd('b', null, r.label, g); g.appendChild(document.createTextNode(' ')); nd('span', r.kind==='ok' ? 'chip hot' : 'chip', r.status, g);
        nd('div', 'small', nameify(r.line), g);
        const ga=[r.gates, String(r.at)===mode ? null : r.at].filter(Boolean).join(' · ');              // 只这只自己的闸门 / 数据时刻（共同的在顶上 ★）
        if(ga) nd('div', 'muted small', nameify(ga), g);
      }
    };
    if((v.rows||[]).length) rows(v.rows, el);                             // 只列满足的（2026-10-17）
    if(v.none) nd('div', 'small', v.none, el);
    const fold=(k, sum)=>{ const d=nd('details', 'ia', null, el); d.dataset.k=k; if(open[k]) d.open=true; nd('summary', 'muted small', sum, d); return d; };
    for(const m of v.more||[]) rows(m.rows, fold(m.key, m.sum));         // 接近的 / 没满足的：收起
    if(v.impossible){
      const d=fold('imp', v.impossible);
      for(const x of v.groups||[]) nd('div', 'muted small', x.why+'：'+x.names, d);
    }
  }
  document.querySelectorAll('[data-intra]').forEach(e=>{                   // 持仓每只一行：没有这只（卖完了 / 还没算）→ 空
    const s=(v.hold||{})[e.dataset.intra]; e.textContent=s ? nameify(s) : '';
  });
}
function intraBusy(){                                                     // 对话框开着 / 正在输入 / 页面在后台：不重画
  const a=document.activeElement;
  return document.hidden || !!document.querySelector('dialog[open]') || (!!a && (/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) || a.isContentEditable));
}
let ITID=null, ILIVE=!!CFG.intra_live;
async function loadIntra(){
  clearTimeout(ITID);
  if(!$('#intraday') && !document.querySelector('[data-intra]')) return;
  if(!intraBusy()){
    try{
      const x=await req('/api/intraday?book='+encodeURIComponent(CFG.book), {credentials:'same-origin', cache:'no-store'});
      if(x.r.ok && x.j && x.j.ok){ intraShow(x.j); ILIVE=!!x.j.live; }
    }catch(e){}                                                           // 取不到（Mac 睡眠 / 没网）：保留上一次的
  }
  ITID=setTimeout(loadIntra, ILIVE ? 60000 : 600000);                     // 交易时段 1 分钟，其他时间 10 分钟
}
if(CFG.intra) ITID=setTimeout(loadIntra, ILIVE ? 60000 : 600000);        // 页面本身是刚画的：先不取，到时间再取
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden && CFG.intra) loadIntra(); });
window.addEventListener('qb-reconnect', ()=>{ if(CFG.intra) loadIntra(); });  // conn.js：连不上之后又连上了 → 马上再取
