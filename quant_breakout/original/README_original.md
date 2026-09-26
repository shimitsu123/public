# 横盘突破量化交易程序（レンジブレイクアウト戦略）

日股（東証）/ 美股通用，纯 pandas/numpy 实现，无需 backtrader。
**楽天証券没有个人 REST API**，官方唯一自动化通道是 MARKETSPEED II RSS（Excel 插件），第4阶段通过 xlwings 对接；RSS 不支持美股。

```
quant_breakout/
├── config.py        参数表（全部可调项都在这里）
├── data.py          数据加载：yfinance → 失败时合成数据（仅调试）
├── strategy.py      信号量化（回测 / 实盘共用）
├── backtest.py      第1阶段 回测
├── optimize.py      第2阶段 网格搜索 + Walk-Forward
├── broker.py        PaperBroker（模拟）/ RakutenRSSBroker（楽天 RSS）
├── paper_trader.py  第3/4阶段 每日自动交易入口
└── README.md
```

## 0. 安装

```bash
pip install pandas numpy yfinance pyarrow      # 基础
pip install xlwings                           # 仅第4阶段、Windows
```

## 策略量化定义

| 条件 | 公式 | 说明 |
|---|---|---|
| ① 横盘 | `(High.rolling(N).max − Low.rolling(N).min) / Low.min < X%`，取**昨日**值 | 用昨日值避免当天大阳线撑大振幅 |
| ② MACD 金叉 | `MACD_t > Signal_t` 且 `MACD_{t-1} ≤ Signal_{t-1}` | |
| ③ 0 轴附近 | `|MACD| / Close × 100 < zero_band%` | 用价格归一化，跨股票可比 |
| ④ 放量 | `Volume > MA(Volume, 20) × 1.5` | |
| 入场 | ①∧②∧③∧④ 在 T 日收盘成立 → **T+1 开盘**买入 | 无前视偏差 |

### 可调参数（config.py → StrategyParams）

| 参数 | 默认 | 作用 | 调大 → |
|---|---|---|---|
| `range_n` | 60 | 横盘回看天数 | 要求横盘更久，信号更少 |
| `range_x_pct` | 15 | 横盘允许振幅 % | 放宽横盘定义，信号更多 |
| `macd_fast / slow / signal` | 12/26/9 | MACD 三周期 | 慢线越大越迟钝、越稳 |
| `macd_zero_band_pct` | 1.0 | "0 轴附近"容忍带 % | 接受离 0 轴更远的金叉 |
| `vol_ma_n` | 20 | 均量周期 | |
| `vol_mult` | 1.5 | 放量倍数 | 要求更强放量 |
| `stop_loss_pct` | 7 | 固定止损 % | 容忍更大回撤 |
| `take_profit_pct` | 25 | 固定止盈 %（0=关闭） | |
| `trailing_stop_pct` | 12 | 跟踪止损 %（0=关闭） | 让利润跑更远，回吐也更多 |
| `max_hold_days` | 60 | 最长持有交易日（0=不限） | |
| `exit_on_macd_dead_cross` | True | 死叉平仓 | 关掉后靠跟踪止损锁利，更适合"暴涨"目标 |

回测参数（BacktestConfig）：`position_pct` 单笔 20%、`max_positions` 5、`commission_pct`、`slippage_pct` 0.1%、`lot_size` 100（美股 1）。

## 第1阶段 回测

```bash
python backtest.py JP      # 或 US
```
输出：交易次数、胜率、年化 CAGR、最大回撤、夏普、盈亏比、出场原因分布；保存 `trades.csv` / `equity.csv`。

## 第2阶段 参数优化

```bash
python optimize.py JP
```
- 网格：`GRID` 字典（默认 36 组，约 1 分钟/20 只股票）
- Walk-Forward：训练 2 年 → 测试 6 个月，滚动 5 次
- 输出三样东西，**只看后两样**：
  1. 各窗口 IS 最优参数 → OOS 表现
  2. 稳健参数区间（min/median/max/众数/稳定度）
  3. **在所有窗口都进前 20% 的参数组合** ← 把它写进 `best_params.json`，paper_trader 自动读取
- `拼接 OOS 曲线` 的年化/回撤才是接近实盘的期望；IS 分数不算数
- 若第 3 项为空 → 策略对参数敏感，应改规则而不是继续调参

```json
// best_params.json 示例
{"range_n": 40, "range_x_pct": 15.0, "macd_fast": 12, "macd_slow": 21, "macd_signal": 9,
 "macd_zero_band_pct": 1.0, "vol_ma_n": 20, "vol_mult": 1.5, "stop_loss_pct": 7.0,
 "take_profit_pct": 25.0, "trailing_stop_pct": 12.0, "max_hold_days": 60, "exit_on_macd_dead_cross": true}
```

## 第3阶段 模拟盘

```bash
python paper_trader.py JP          # 每交易日 15:30 后运行一次
```
- 状态在 `paper_state.json`，日志在 `trader.log`
- 风控（RiskConfig）：`daily_max_loss_pct` 2% 熔断、`max_positions` 5、`max_order_value` 单笔上限
- 定时：Windows「タスクスケジューラ」或 cron `30 15 * * 1-5 python paper_trader.py JP`
- **至少跑 3 个月**，对照回测的胜率/平均单笔是否一致；不一致先查数据/成交假设

## 第4阶段 实盘（楽天 RSS）切换清单

**环境**
- [ ] Windows + Excel（桌面版）+ MarketSpeed II 已登录，RSS 插件「接続」状态
- [ ] `rss_bridge.xlsm` 三张表：`Quote`（=RssMarket 报价）、`Pos`（保有株・余力）、`Order`（VBA `PlaceOrder` 宏 + 名为 `ARM` 的单元格）
- [ ] RSS 函数名对照当年官方「RSS 関数一覧」PDF（每年更新，2026 年有 JAX/Cboe 相关变动）
- [ ] `pip install xlwings`，`python -c "import xlwings"` 通过

**安全**
- [ ] `RiskConfig.require_arm = True`：每日人工在 Excel `ARM` 单元格填 `ARMED` 后程序才会发单，收盘后清空
- [ ] `max_order_value` 设为你能接受的单笔上限；`daily_max_loss_pct` 先设 1%
- [ ] 前 2 周 `position_pct` 降到 5%，只买 1 手
- [ ] 发单用**指値（limit）**而非成行，限价 = 现价 × 1.005
- [ ] 每笔订单后读回 `Pos` 表核对约定（成交）；程序内做"发单→10 秒内查约定→不一致则告警停止"
- [ ] 熔断触发时发送通知（LINE Notify / 邮件），不要静默

**数据一致性**
- [ ] yfinance 日线与楽天 RSS 现在值对齐：收盘后 yfinance 有延迟约 15–30 分钟，建议 16:00 后运行
- [ ] 复权：yfinance `auto_adjust=True`，RSS 是原始价；除权日会出现假信号 → 除权日当天跳过开仓
- [ ] 股票池中若有停牌/退市股，`load_ohlcv` 抛异常已被捕获并跳过

**流程**
- [ ] `--live` 参数运行前，先用同一天的 paper 输出对比：两边信号列表完全一致
- [ ] 保留 paper 与 live 同时跑 1 个月，比较滑点实际值，回填 `slippage_pct`
- [ ] 每月重跑 `optimize.py`，若稳健参数漂移超过一档才更新 `best_params.json`

**法规/账户**
- [ ] 楽天 RSS 利用規約同意（自动化仅限本人账户、合理频率）
- [ ] 特定口座（源泉徴収あり）下无需自行申报；NISA 口座频繁交易会浪费额度，实盘用一般/特定口座

## 已知局限与坑点

1. **横盘突破策略本身的胜率通常 30–45%**，靠盈亏比赢钱；默认 `exit_on_macd_dead_cross=True` 会过早砍掉大趋势，想抓"暴涨"应设为 False 并依赖 `trailing_stop_pct`。
2. 合成数据只用于跑通代码，**任何用合成数据得出的收益数字都无意义**。
3. yfinance 是非官方接口，可能限流/改版；正式使用建议改用 J-Quants API（東証官方，免费档有 12 周延迟，付费档实时）。
4. 幸存者偏差：股票池用的是今天还在的公司；严谨做法是用历史成分股名单。
5. 20 只股票 × 5 年信号很少（每年个位数），统计意义弱；扩到 100+ 只再看参数稳健性。

> 本程序仅为技术实现示例，不构成投资建议；自动交易可能造成本金损失。
