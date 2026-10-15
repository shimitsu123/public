// qbreak 操作面板的入口（浏览器原生 ES 模块，不用构建工具）。页面：<script type="application/json" id="qb-cfg">（配置）+ boot.js（普通脚本：
// 模块没载入成 → 页面上说、自动重新载入）+ <script type="module" src="/static/main.js">。
// 模块：net（请求、超时）→ core（配置、共用小工具、提示、写指令）→ conn（连接检查、自动重连、安全的自动刷新）
//       → trade（卖出 / 调仓 / 买入 / 凑钱 / 撤单的对话框）→ kline（K 线）→ quotes（现价、预计收益）→ room（今天还能买几次 / 卖几次）
//       → app（标签页、推送、选股分段、消息）。
import './core.js';
import './conn.js';
import './trade.js';
import './kline.js';
import './quotes.js';
import './room.js';
import './app.js';
window.__qbReady = 1;                                                     // boot.js：全部模块跑完了
if(typeof window.__qbBootOk === 'function') window.__qbBootOk();
