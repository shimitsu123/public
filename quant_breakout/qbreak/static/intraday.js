// qbreak 操作面板：intraday.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/intraday.js 提供；不要用构建工具）
// 盘中观测（2026-10-16 用户要求；只展示、不下单）：持仓每只一行（收盘卖出线离现价多远）。选股页的「今天盘中：规则的买点」卡片
// 2026-10-18 用户「没什么用 删了吧」→ 删掉。数 = /api/intraday（qbreak/intraday_watch.view：只读面板线程每 5 分钟另起进程写的结果文件，
// 请求里不取价）；服务器先画好一份（panel._intraday_line），这里定时更新文字（交易时段每 1 分钟，其他时间每 10 分钟；回到页面 / 重新连上也再取）；
// 对话框开着 / 正在输入 / 页面在后台 → 这一次不更新（等下一次）。代码一律带名字（文字里的「7203.T」用 nameify 兜底）。
import { CFG, nameify } from './core.js';
import { req } from './net.js';

export function intraShow(v){                                             // 持仓每只一行；v.ok=false / 没有 → 不动（保留上一次的）
  if(!v || !v.ok) return;
  document.querySelectorAll('[data-intra]').forEach(e=>{                   // 没有这只（卖完了 / 还没算）→ 空
    const s=(v.hold||{})[e.dataset.intra]; e.textContent=s ? nameify(s) : '';
  });
  const box=document.getElementById('sellsig-list');                      // 持仓最上面「出了卖出信号」（服务器转义好的几行；2026-10-18）
  if(box && Array.isArray(v.sell)){ box.innerHTML=v.sell.join(''); box.closest('#sellsig').hidden=!v.sell.length; }
}
function intraBusy(){                                                     // 对话框开着 / 正在输入 / 页面在后台：不重画
  const a=document.activeElement;
  return document.hidden || !!document.querySelector('dialog[open]') || (!!a && (/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) || a.isContentEditable));
}
let ITID=null, ILIVE=!!CFG.intra_live;
async function loadIntra(){
  clearTimeout(ITID);
  if(!document.querySelector('[data-intra]')) return;
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
