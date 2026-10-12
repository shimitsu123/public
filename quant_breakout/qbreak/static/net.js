// qbreak 操作面板：net.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/net.js 提供；不要用构建工具）

const TMO = 15000;                                                        // 15 秒没有回应就不再等（Mac 睡眠时请求会一直挂着）
function timed(p, ac){
  let tid;
  const to=new Promise((_, rej)=>{ tid=setTimeout(()=>{ rej(Object.assign(new Error('timeout'), {name:'Timeout'})); try{ if(ac) ac.abort(); }catch(x){} }, TMO); });
  return Promise.race([p, to]).finally(()=>clearTimeout(tid));
}
export function req(url, opt){                                                   // → {r, j}（连内容一起 15 秒内读完；超时抛 name = 'Timeout'）
  const ac=('AbortController' in window) ? new AbortController() : null;      // j = null：内容读不出来 / 不是 JSON（连接中途断了也是）
  return timed((async()=>{ const r=await fetch(url, Object.assign({}, opt||{}, ac ? {signal:ac.signal} : {})); let j=null; try{ j=await r.json(); }catch(e){} return {r:r, j:j}; })(), ac);
}
