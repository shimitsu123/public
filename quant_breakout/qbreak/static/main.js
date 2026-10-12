// qbreak 操作面板的入口（浏览器原生 ES 模块，不用构建工具）。页面：<script type="application/json" id="qb-cfg">（配置）+ <script type="module" src="/static/main.js">。
// 模块：net（请求、超时）→ core（配置、共用小工具、提示、写指令）→ trade（卖出 / 调仓 / 买入 / 凑钱 / 撤单的对话框）
//       → kline（K 线）→ quotes（现价、预计收益）→ app（标签页、推送、选股分段、消息）。
import './core.js';
import './trade.js';
import './kline.js';
import './quotes.js';
import './app.js';
