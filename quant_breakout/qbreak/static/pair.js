// qbreak 手机配对页（浏览器原生 ES 模块；/static/pair.js）
import { req } from './net.js';
const $ = s => document.querySelector(s);
function toast(t, bad){const m=$('#toast');m.textContent=t;m.className='toast'+(bad?' bad':'');m.hidden=false;}
$('#code').addEventListener('input', e=>{ const p=e.target.selectionStart; e.target.value=e.target.value.toUpperCase(); try{e.target.setSelectionRange(p,p);}catch(x){} });
$('#go').addEventListener('click', async ()=>{
  const b=$('#go'); b.disabled=true;
  try{
    const x=await req('/api/pair',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',
                                   body:JSON.stringify({code:$('#code').value, name:$('#name').value})});
    const r=x.r, j=x.j||{};
    if(r.ok && j.ok){ toast(j.msg); setTimeout(()=>location.replace('/'), 900); return; }
    toast(r.ok && !x.j ? '回应读不出来：刷新页面看看是不是已经配对好了（提示配对码无效的话，在 Mac 上重新生成）'
                       : (j.msg || ('没配对成功（HTTP '+r.status+'）')), true);
  }catch(e){ toast(e && e.name==='Timeout' ? 'Mac 可能在睡眠：超过 15 秒没有回应（Mac 醒来后再试；配对码 10 分钟内有效；提示配对码无效的话，在 Mac 上重新生成）'
                                           : '连不上面板：'+e, true); }
  b.disabled=false;
});
