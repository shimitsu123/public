# HANDOFF：现状与来龙去脉（给新的 Claude 会话；2026-09-25 写，有变化就更新这里）

细节以代码与这些文件为准：`README.md`（总览）、`MACOS.md`（Mac 与立花）、`var/sim_changes.md`（每次变更与研究结论，按时间）、
`REVIEW.md`（原版代码审查）、`var/out/`（研究报告与日报数据）。

## 一句话
个人资金 ¥1,000,000，一个账户方案 **S0C2**（立花証券 e支店 個別コース）：日本个股 4 个名额 × 25%（日経225 股票池）
+ 闲置资金全部买 **1655.T**（iシェアーズ S&P500，东证上市，按 S&P500 的牛熊分界择时，熊市那份留现金）。
先用云端模拟盘 + Mac 模拟操盘跑 **2026-09-28 → 2026-12-24**，再决定要不要上立花实盘。

## 现在在哪一步（2026-09-25）
- 策略：S0C2 定案（`var/sim.json` 的 unified 段）；主要研究都是「先登记规则 → 再运行」，没通过的一律不采用（见 sim_changes.md）
- 云端模拟盘：例行任务「模拟盘日报」周一至五 06:57 JST → `sim-day` → `var/` 入库 → 更新日报 artifact（README 里的日报链接）；
  9/28 之前只预览（不推进账户、不下单）
- Mac 模拟操盘：已安装并试跑成功（2026-09-25）；LaunchAgent `com.qbreak.liveu.paper` 周一至五 07:40；9/28 起正式推进
- 立花：**还没开户**；执行器 `run.py live-u` + 立花适配器已完成，用模拟交易所做过历史演练（MACOS.md §1.6）
- 季度复核：例行任务每年 1 / 4 / 7 / 10 月 12 日 09:56 JST（下一次 2026-10-12）：顶底择时复核、敏感度表、前向记录评估、大事件日程

## 交易规则（摘要；代码是准）
- 决策在日本与美国都收盘之后（日本时间 06:30 以后才算前一天完整）；成交在下一交易日 **09:00 寄付**（开盘）
- 个股：日経225 股票池的突破信号（`qbreak/strategy.py`，参数 `qbreak/config.py` + `var/best_params_JP.json`）；
  4 个名额 × 权益 25%，单只 ≤ 34%；新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜；事件窗口关闭
- 1655：闲置资金全部；S&P500 连续 5 天收在 250 日均线 ×0.97 之下 → 熊（卖出，留现金）；连续 5 天在 ×1.03 之上 → 牛（`var/bullbear.json`）
- 回撤达 45% → HALT（停新仓）
- 牛熊的「现在处于哪个阶段」（牛市·稳固 / 走弱 / 临界 / 牛→熊确认中，熊市同理）只用于展示，阈值 3% / 8% / 5 pp 是展示用的，
  **不改交易规则**（`qbreak/bullbear.py` 的 `phase()`）

## 每天的流程（周一至五，JST）
1. 前一晚 22:00：用户的另一个例行任务更新「市场风险报告」artifact（判断层与宏观数值的来源）
2. 06:57 云端：拉代码 → 从风险报告写 `var/market_regime.json`、`var/macro.json` → `sim-day` → 入库 → 发布日报
3. 07:40 Mac（`scripts/liveu.sh run --broker paper`）：`git pull`，等云端当天的 `var/out/unified_today.json`（最多 50 分钟）
   → 把配置与输入拷到 `~/.qbreak/home` → 执行器：昨天的单按真实开盘价撮合 → 对账 → 决策 → 下「下一开盘」的单
   → 与云端模拟盘逐日比较 → 通知中心 → 日志 → 重写页面并用浏览器打开（桌面的 `qbreak模拟操盘.html` 指向它）
4. 立花上线后另有 09:05 的开盘后补单（开盘前余力不够的买单）

## 文件地图
- `qbreak/unified.py` 一个账户的推进器（回测、模拟盘、执行器共用）；`qbreak/live_unified.py` 执行器（对账、下单、安全闸、演练、比较、日志）
- `qbreak/brokers/tachibana.py` 立花 API v4r10 适配器；`qbreak/brokers/tachibana_sim.py` 模拟交易所（演练用）；`qbreak/brokers/paper.py` 模拟券商
- `qbreak/bullbear.py` 牛熊分界 + 阶段；`qbreak/report_unified.py` 日报；`qbreak/desktop_page.py` Mac 的账本页面
- `run.py`：`sim-day`（云端）、`live-u`（执行器）、`live-u-rehearse`（演练）、`tachibana-probe`（连通性检查）、`doctor`
- `scripts/liveu.sh`（Mac 上跑执行器）、`scripts/install_launchd_live_u.sh`（注册定时任务）、`scripts/mac_bootstrap.sh`（一行安装）
- 云端状态：`var/state/unified_state.json`（模拟盘）；Mac 状态：`~/.qbreak/home/state/live_unified_paper.json`（账本，不在仓库）

## 用户常问的，去哪里查
- 「今天买卖了什么 / 为什么没买」：页面、日志 `~/.qbreak/home/out/live_unified_paper_journal.md`、当天汇总
  `~/.qbreak/home/out/live_unified_paper.json`（orders 的 status / note、blocked、events）
- 「和云端不一致」：日志里的比较行（两边的持仓、现金、权益差）。多半是数据不同（云端当天晚了或失败 → Mac 用了前一天的判断层；
  Yahoo 行情修正）。重新对齐：删掉 `~/.qbreak/home/state/live_unified_paper*.json`，下次从云端模拟盘当时的状态开始
- 「页面没更新 / 没弹出」：`launchctl list | grep qbreak`、`~/.qbreak/home/logs/`；`~/.qbreak/home/NO_OPEN` 存在就不弹出
- 「牛熊现在怎样」：页面「牛熊：现在处于哪个阶段」或日报「市场状态」（离 250 日线的 %、20 个交易日的变化 pp、离翻转还差多少 %）

## 已知限制
- 行情主要来自 Yahoo（yfinance），偶有修正与缺失；被拦截时用 `var/csv`。日报「数据完整性」逐项列出没取到的数据
- 股票池是 2026-09 时点的成分股 → 回测有幸存者偏差（偏乐观），只适合比较方案之间的相对差异；回测收益是税前、未计 NISA
- 模拟账户按开盘价 + 滑点撮合（与回测相同）；实盘还有：开盘后补单的盘中价格、限价没成交、比例配分、1655 拆单多付的手续费（通常 77 円）。
  演练（立花适配器 + 模拟交易所）：5 年年化 22.99% vs 回测 23.02%（−¥3,864）；20 年 12.87% vs 12.87%（−¥4,865）
- 立花デモ環境价格是假的、每天重置 → 只能检查 API 字段与流程；开盘前买付可能額的实际行为要本番头几天确认
- Mac 要开着且已登录（合盖 / 关机就不跑）；云端例行任务失败时 Mac 用手上最新的输入继续，并提示

## 路线图 / 未来的展望（带「提案」的还没经用户确认）
1. 2026-09-28 起：模拟期（到 12-24）。每天看页面与「与云端一致」；第一周重点确认通知、页面按时出现，比较没有无法解释的差异
2. 2026-10-12：第一次季度复核（例行任务自动跑，判定有变化时第一行会写「需要用户确认」，不自动改规则）
3. 立花开户（时间由用户定）→ e支店・API 利用設定、公開キー登録 → `tachibana-probe --demo` 与 `--demo --order-test`（一天）
   → 本番 `--dry-run` → 入金 → `install_launchd_live_u.sh tachibana` → `echo ARMED > ~/.qbreak/home/ARM`（MACOS.md §1.6）
4. 提案：上线门槛 = Mac 模拟操盘与云端连续 ≥ 10 个交易日一致（或差异都能解释）、没有状态不明的单、HALT 演练过一次、
   デモ发单检查的三点（约定字段、余力变化、按注文番号撤单）确认；先用较小金额跑 1〜2 周再加到计划金额
5. 2026-12-24 模拟期结束：按事先的格式总结（累计收益、最大回撤、交易笔数、胜率、与买入持有对比）→ 用户决定继续 / 上实盘 / 调整
6. 可选研究（要花钱，用户决定）：J-Quants Standard（10 年，¥3,300/月）或 Premium（20 年，¥16,500/月；2026-09-24 价格）
   做无幸存者偏差的回测（`scripts/pit_backtest.py`，Free 档流程已验证）
7. 前向记录（威胁指数各版本、日経 / 美股前瞻观察、配比最优化）继续只追加；到期由季度复核按事先规则评估
