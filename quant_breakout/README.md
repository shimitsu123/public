# 横盘突破量化交易框架 v2（レンジブレイクアウト / range breakout）

日股（東証）/ 美股通用，纯 `pandas` + `numpy`，**可以直接在你自己的电脑上跑完四个阶段**。

> 这是对上传版本的 review + 重写。原版逐条问题见 **[REVIEW.md](REVIEW.md)**；
> 原始文件完整保留在 `original/` 里，方便对照。

**楽天証券对个人不提供官方 REST API**，唯一官方自动化通道是
「マーケットスピード II RSS」（Excel 插件），Python 经 `xlwings` 操作 Excel 下单；
RSS 仅支持国内株，不支持美股。第4阶段的搭建步骤见 [`excel/README_excel.md`](excel/README_excel.md)。

---

## 0. 三分钟跑起来

```bash
pip install -r requirements.txt
python run.py doctor          # 环境自检：Python 版本、依赖、yfinance 连通性
python run.py selftest        # 83 个单元测试，全绿才继续
python run.py backtest JP     # 第1阶段
```

没有网络 / yfinance 被限流时，可以加 `--synthetic` 先跑通流程 —— 但**任何基于合成数据的收益
数字都没有意义**，报告标题会自动标注。

```
quant_breakout/
├── run.py                统一入口（backtest / optimize / paper / live / status / doctor / selftest）
├── qbreak/
│   ├── config.py         全部参数 + 校验
│   ├── paths.py          所有状态/日志/缓存的位置（QBREAK_HOME）
│   ├── data.py           行情：yfinance 批量 / 本地 CSV / 质量检查 / TTL 缓存
│   ├── strategy.py       信号（回测与实盘共用）
│   ├── engine.py         numpy 回测引擎
│   ├── metrics.py        绩效指标 + 报告
│   ├── optimize.py       网格搜索 + Walk-Forward
│   ├── risk.py           熔断 / HALT / 单笔上限
│   ├── trader.py         每日执行流程
│   ├── notify.py         webhook / 邮件通知
│   └── brokers/          paper（模拟）· rakuten_rss（实盘）
├── excel/                RssBridge.bas（VBA 桥）+ 搭建说明
├── scripts/              Windows 任务计划程序 / cron
├── tests/                83 个测试
└── original/             上传的原始版本（仅作对照，不参与运行）
```

---

## 1. 策略定义

| 条件 | 公式 | 说明 |
|---|---|---|
| ① 横盘 | `(High.rolling(N).max − Low.rolling(N).min) / Low.min < X%`，取**昨日**值 | 用昨日值，避免当天大阳线把箱体自己撑大 |
| ② MACD 金叉 | `MACD_t > Signal_t` 且 `MACD_{t-1} ≤ Signal_{t-1}` | ゴールデンクロス |
| ③ 0 轴附近 | `|MACD| / Close × 100 < zero_band%` | 用价格归一化，跨股票可比 |
| ④ 放量 | `Volume > MA(Volume, 20) × 1.5` | 出来高確認 |
| ⑤ 真突破（可选） | `Close > 过去 N 日最高（不含当日）` | **原版没有这一条** —— 见下方说明 |
| 入场 | 以上条件在 T 日收盘成立 → **T+1 开盘**买入 | 无前视偏差 |

> ⚠️ 原版策略叫"横盘突破"，但 ①~④ 里没有任何一条要求价格**突破箱体上沿**，
> 实际抓的是"突破前的蓄势"。想做字面意义的突破，把 `require_breakout` 打开，
> 然后**重跑 walk-forward** 对比两者的拼接 OOS 曲线，再决定用哪个。

### 可调参数（`qbreak/config.py → StrategyParams`）

| 参数 | 默认 | 作用 | 调大 → |
|---|---|---|---|
| `range_n` | 60 | 横盘回看天数 | 要求横盘更久，信号更少 |
| `range_x_pct` | 15 | 横盘允许振幅 % | 放宽箱体定义，信号更多 |
| `macd_fast/slow/signal` | 12/26/9 | MACD 三周期 | 慢线越大越迟钝、越稳 |
| `macd_zero_band_pct` | 1.0 | 「0 轴附近」容忍带 % | 接受离 0 轴更远的金叉 |
| `vol_mult` | 1.5 | 放量倍数 | 要求更强放量 |
| `require_breakout` | False | 真突破确认 | 打开后信号更少但更"像突破" |
| `trend_ma_n` | 0 | 长期趋势过滤（如 200） | 只在均线上方做多 |
| `min_turnover` | 0 | 最低 20 日平均売買代金 | 建议日本株设 1e8，否则滑点假设不成立 |
| `stop_loss_pct` | 7 | 固定止损 % | 容忍更大回撤 |
| `atr_stop_mult` | 0 | ATR 止损倍数（>0 时覆盖上一项） | 止损随个股波动自适应 |
| `take_profit_pct` | 25 | 固定止盈 %（0=关闭） | |
| `trailing_stop_pct` | 12 | 跟踪止损 %（0=关闭） | 让利润跑更远，回吐也更多 |
| `trailing_arm_pct` | 0 | 浮盈超过该 % 才启动跟踪 | 避免刚建仓就被震出去 |
| `max_hold_days` | 60 | 最长持有交易日（0=不限） | |
| `time_stop_days` | 0 | 时间止损：持有 N 日仍无浮盈则离场 | 释放"死钱" |
| `exit_on_macd_dead_cross` | True | 死叉平仓 | 关掉后靠跟踪止损锁利，更适合抓大波段 |

---

## 2. 成交假设（**看懂这一节再看任何收益数字**）

| 项目 | 设定 | 为什么 |
|---|---|---|
| 入场 | T+1 开盘价 ×(1+滑点) | 信号在收盘后才知道，最早只能次日开盘买 |
| 跳空过滤 | 开盘价 > 信号日收盘 ×(1+3%) 则放弃 | ストップ高 追不进去；不过滤会严重高估收益 |
| 止损成交 | **`next_open`（默认）**：收盘价触发 → 次日开盘成交 | 一个每天只跑一次的程序**只能**做到这个 |
| | `intraday`：盘中触及即成交 | 只有真的挂了**逆指値（stop order）**才成立 |
| 手续费 | JP 0%（ゼロコース）/ US 0.495% 上限 22 美元 | 你的コース不同就改 `ExecConfig` |
| 滑点 | 单边 0.1%（JP） | 流动性差的票要调大 |
| 仓位 | 用**前一日收盘权益**计算 | 用当日数据就是前视偏差 |
| 単元株 | JP 100 股 / US 1 股 | ETF、REIT 等例外在 `tick.py:LOT_OVERRIDE` 里改 |

两种止损模式各跑一次，差额就是"没挂逆指値"的成本：

```bash
python run.py backtest JP                          # next_open（保守、真实）
python run.py backtest JP --stop-mode intraday     # intraday（乐观，需配合 --protective-stop 实盘）
```

---

## 3. 四个阶段

### 第1阶段　回测

```bash
python run.py backtest JP --years 5
```
输出：交易次数/胜率/盈亏比/每笔期望/CAGR/最大回撤/夏普/索提诺/最大连亏/资金暴露/**分年度收益**，
外加等权买入持有基准对照。产物在 `var/out/`。

**怎么看**：先看分年度表——如果 5 年收益靠某一年撑起来，这个策略你拿不住；
再看"被过滤的信号"，`gap` 很多说明策略在追涨停，`full` 很多说明持仓上限卡住了。

### 第2阶段　参数优化（Walk-Forward）

```bash
python run.py optimize JP --train-years 2 --test-months 6 --save
```
输出四样东西，**只看后两样**：
1. 各窗口 IS 最优参数 → OOS 实测
2. 稳健参数区间（众数 + stability%）
3. **参数敏感度**：某个参数换一档分数就断崖 → 策略对它过敏，实盘会很难受
4. **在所有窗口都进前 20% 的参数组合** ← `--save` 会把它写进 `var/best_params.json`，第3/4阶段自动读取

最后一行「拼接 OOS 曲线」才是接近实盘的期望值。**IS 分数再漂亮也不算数。**
如果第 4 项为空，程序会**拒绝写入** `best_params.json` —— 这时应该改规则（例如打开
`require_breakout` / `trend_ma_n`）而不是继续调参。

### 第3阶段　模拟盘（至少 3 个月）

```bash
python run.py paper JP                # 每交易日 16:10 JST 之后运行一次
python run.py status                  # 看持仓/权益/风控状态
```
- 模拟盘的订单会**排队到次日开盘成交**，与回测引擎完全一致 —— 这样"第3阶段验证第1阶段"才有意义
- 状态在 `var/state/`，日志在 `var/logs/`，每日流水在 `var/out/journal.csv`
- 跑满 3 个月后，把 `journal.csv` 的胜率/平均单笔和回测对比；**对不上先查数据和成交假设，不要先改策略**

### 第4阶段　实盘（楽天 RSS，仅 Windows + 国内株）

先读 [`excel/README_excel.md`](excel/README_excel.md) 搭好 Excel 桥，然后：

```bash
python run.py live JP --dry-run       # 演练：只算不发单，先跑一周
python run.py live JP                 # 实盘（Excel 里 Ctrl!ARM 填 ARMED 才会发单）
python run.py live JP --stop-mode intraday --protective-stop   # 自动挂/改逆指値
```

**上线前清单**

- [ ] `run.py doctor` 全绿；Excel 里 `QB_SelfTest` 通过
- [ ] `RssBridge.bas` 三处 `★TODO★` 已按当期「RSS 関数一覧」PDF 填写（默认是占位实现，会直接拒绝下单）
- [ ] MarketSpeed II 已登录、RSS「接続」、功能区切到「**発注可**」
- [ ] 口座选**特定口座**，不要用 NISA（自动交易会浪费非課税枠，且亏损不能损益通算）
- [ ] `--max-order-value` 设成你能承受的单笔上限；前两周 `--position-pct 0.05`，只买 1 単元
- [ ] 熔断线先设 1%：`RiskConfig.daily_max_loss_pct`
- [ ] 通知打开：`set QBREAK_WEBHOOK=https://...`（Discord/Slack/LINE 兼容）
- [ ] 同一天 paper 与 live 各跑一次，**两边的信号列表必须完全一致**
- [ ] 每天收盘后清空 Excel 的 `ARM` 单元格

**紧急停止**：在 `var/` 下建一个名为 `HALT` 的文件，任何下单都会被拒绝（Python 侧和 VBA 侧双重拦截）。

---

## 4. 定时运行

**Windows**（推荐 16:10 JST，不是 15:30 —— 收盘后 yfinance 日线还要 15~30 分钟才更新）

```powershell
# 先改 scripts\run_daily.bat 里的 PROJ / QBREAK_HOME 路径，然后管理员运行：
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
```

**macOS / Linux**

```bash
crontab -e
# 10 16 * * 1-5 /path/to/quant_breakout/scripts/run_daily.sh
```

休市日也会触发，程序会因为「数据过期」自动跳过，属正常。
重叠触发也没关系：每个订单带 `client_id`，同一根 K 线不会下两次单。

---

## 5. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `没有取到任何行情数据` | yfinance 限流或网络问题。等几分钟重试；或用 `--provider csv` 读本地数据 |
| 收益数字好得不真实 | 先确认没有 `--synthetic`；再确认 `--stop-mode` 不是 `intraday` 而你并没挂逆指値 |
| 定时任务跑完像是空仓 | 没设 `QBREAK_HOME`，或 `.bat` 里没 `cd /d` 到项目目录 |
| 实盘发单被拒 | 九成是呼値或「発注可」没切。看 `var/logs/qbreak.log` 和 Excel 的 `OrderLog` 表 |
| walk-forward 说"无稳健参数" | 这是有用的结论，不是失败。说明策略对参数过敏，该改规则 |
| 想换数据源 | 把券商/RSS 导出的日线放进 `var/csv/<代码>.csv`（`Date,Open,High,Low,Close,Volume`），`--provider csv` |

---

## 6. 已知局限（原版列出的仍然成立，加上新的）

1. **横盘突破策略的胜率通常 30~45%**，靠盈亏比赢钱。默认 `exit_on_macd_dead_cross=True` 会过早砍掉大趋势；想抓大波段应设为 False 并依赖跟踪止损。
2. **幸存者偏差**：股票池用的是今天还在的公司。严谨做法是用历史成分股名单。
3. **20 只 × 5 年信号很少**（每年个位数），统计意义弱。扩到 100+ 只再谈参数稳健性。
4. **yfinance 是非官方接口**，可能限流/改版；复权方式与券商原始价不同，除权日容易出假信号。长期方案是把 RSS 的日线落到本地 CSV，做到**实盘与回测同源**。
5. **呼値表 2027-03-01 会变**（JPX 改为按个股流动性 STR 决定），届时需更新 `qbreak/tick.py`。
6. **值幅制限（ストップ高/安）未建模**：跳空过滤只是近似。
7. 本框架只做**現物・買い（做多）**，不含信用取引、空売り、分批建仓/加仓。

---

> 本程序仅为技术实现示例，**不构成投资建议**；自动交易可能造成本金损失。
> 上线前请自行核对楽天証券的当期手数料コース、RSS 利用規約与関数一覧 PDF。
