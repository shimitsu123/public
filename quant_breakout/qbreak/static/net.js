// qbreak 操作面板：net.js（浏览器原生 ES 模块；由 qbreak/panel.py 以 /static/net.js 提供；不要用构建工具）

const TMO = 15000;                                                        // 15 秒没有回应就不再等（Mac 睡眠时请求会一直挂着）
function timed(p, ac, ms){
  let tid;
  const to=new Promise((_, rej)=>{ tid=setTimeout(()=>{ rej(Object.assign(new Error('timeout'), {name:'Timeout'})); try{ if(ac) ac.abort(); }catch(x){} }, ms); });
  return Promise.race([p, to]).finally(()=>clearTimeout(tid));
}
function hook(name, a, b){ try{ const f=window[name]; if(typeof f==='function') f(a, b); }catch(x){} }   // conn.js 的连接检查（没有就不管）
const RETRY = [502, 503, 504];                                            // 面板正在重启 / Tailscale Serve 一时接不上：GET 隔一会儿再试一次（写操作不重试）
export function req(url, opt){                                                   // → {r, j}（连内容一起 15 秒内读完；超时抛 name = 'Timeout'）
  opt=Object.assign({}, opt||{});                                         // j = null：内容读不出来 / 不是 JSON（连接中途断了也是）
  const ms=opt.tmo>0 ? opt.tmo : TMO, quiet=!!opt.quiet, get=!opt.method || String(opt.method).toUpperCase()==='GET';
  delete opt.tmo; delete opt.quiet;                                       // tmo：这次的超时（毫秒）；quiet：连接检查自己发的（不再回头通知 conn.js）
  const t0=Date.now();
  async function once(){
    const ac=('AbortController' in window) ? new AbortController() : null;
    return timed((async()=>{ const r=await fetch(url, Object.assign({}, opt, ac ? {signal:ac.signal} : {})); let j=null; try{ j=await r.json(); }catch(e){} return {r:r, j:j}; })(),
                 ac, Math.max(1, ms-(Date.now()-t0)));
  }
  return (async()=>{
    let x;
    try{
      x=await once();
      const wait=Math.min(1000, ms/10);
      if(get && RETRY.indexOf(x.r.status)>=0 && ms-(Date.now()-t0)>wait*3){ await new Promise(r=>setTimeout(r, wait)); x=await once(); }
    }catch(e){ if(!quiet) hook('qbNetFail', url, (e && e.name)||'net'); throw e; }
    if(!quiet){                                                            // service worker 给的是存着的（X-Qbreak-Cache）/ 5xx → 连接有问题；其他回应 → 连得上
      const cached=!!(x.r.headers && x.r.headers.get && x.r.headers.get('X-Qbreak-Cache'));
      if(cached || x.r.status>=500) hook('qbNetFail', url, cached ? 'cache' : 'http'); else hook('qbNetOk', url);
    }
    return x;
  })();
}
