# 代码审查报告：`quant_breakout`（原版）

审查日期：2026-09-22　审查范围：上传压缩包内 7 个 `.py` + `README.md`（共 975 行）
结论先行：**架构方向是对的，但在"从回测走到实盘"这条路上有 10 个会直接导致亏损或让结论失效的缺陷。**
原版可以当作一份完整的设计草稿；直接拿去连真实账户是危险的。

---

## 0. 先说做得对的地方

这些是原版的真实优点，改版里全部保留：

1. **横盘判定用 `shift(1)`**（`strategy.py:37`）——避免当日突破大阳线把箱体自己撑大。这个细节很多人会漏。
2. **T 日信号 → T+1 开盘成交**（`backtest.py:52-64`）——入场侧没有前视偏差。
3. **回测与实盘共用 `compute_indicators`**——从源头上避免"两套逻辑"。
4. **Walk-Forward + 稳健参数区间**的方法论，以及 README 里"IS 分数不算数、只看拼接 OOS"的判断标准。
5. **RSS 的 ARM 人工闸门设计**——思路正确（虽然实现有漏洞，见 P0-6）。
6. README 主动写出了幸存者偏差、合成数据无意义、信号数太少等局限。

---

## 1. 致命问题（P0）：会直接造成资金损失，或让所有结论作废

### P0-1　合成数据静默兜底，假数据被当成真结果
`data.py:40-63`
```python
def load_ohlcv(..., allow_synthetic: bool = True):   # ← 默认 True
    try:
        df = yf.download(...)
    except Exception:
        print(f"[data] {ticker}: yfinance 不可用，改用合成数据 ← 仅供调试")
        return _synthetic(ticker, years)
```
yfinance 限流、改版、断网、代码写错（`7203.T` 写成 `7203`）——**任何一种失败都会静默变成随机数**，
而 `backtest.py` 照样打印出「年化 18.4%、夏普 1.6」。一行 `print` 混在几十行输出里，很容易被忽略。

> 改版：`allow_synthetic` 默认 `False`，取不到数据直接抛异常并给出排查清单；
> 必须显式 `--synthetic` 才启用，且报告标题会带上 `【合成数据·结果无效】`。

### P0-2　当日亏损熔断永远不会触发
`paper_trader.py:41-53`
```python
if anchor.get("date") != today:
    anchor = {"date": today, "equity": broker.equity()}   # 今天第一次跑 → 基准 = 当前权益
return (anchor["equity"] - broker.equity()) / anchor["equity"] * 100   # → 恒等于 0.00%
```
程序设计上**每天只运行一次**，所以每次都是"今天第一次"，基准恰好等于当前权益，
`daily_loss_pct` 永远返回 0。`RiskConfig.daily_max_loss_pct = 2.0` 这道风控形同虚设。

> 改版：基准改为**上一交易日收盘权益**并持久化（`risk.py`），
> 并补上总回撤 HALT、连续亏损 HALT、单日开仓数上限、`HALT` 文件人工闸。

### P0-3　跟踪止损的"最高价"从不落盘，每天被重置
`paper_trader.py:83-84` + `broker.py:88`
```python
pos.setdefault("peak", pos["avg_px"])
pos["peak"] = max(pos["peak"], float(row["High"]))   # row 是最新一根 K 线
```
两个问题叠加：
1. `pos` 是 `broker.state["positions"]` 里的字典引用，但这里改完**没有调用 `_save()`**，进程一退出就丢；
2. 即使保存了，`setdefault` 的初值是 `avg_px`，于是每次运行 `peak = max(成本价, 昨日最高价)`，
   **等于只看最近一根 K 线**，而不是入场以来的累计最高价。

结果：回测里 12% 跟踪止损锁住的利润，实盘根本锁不住。

> 改版：`Position.peak` 由 `PositionBook` 独立持久化，每根新 K 线只累加一次（带 `last_bar` 去重）。

### P0-4　回测假设"盘中触及止损即成交"，但程序做不到
`backtest.py:78-83`（盘中触及止损价成交） vs `paper_trader.py:87-91`（收盘价判断、下一次运行才卖）

回测里止损按 `Low <= stop_px` 在**当根 K 线内**以止损价成交；
而实盘程序每天收盘后跑一次、且**没有任何挂逆指値的代码**，实际只能等下一个开盘卖。
遇到利空跳空，回测记 −7%，实盘可能是 −15%。这是原版最贵的一处系统性高估。

> 改版：`ExecConfig.stop_fill_mode` 显式区分 `next_open`（默认，程序真正能做到的）
> 与 `intraday`（需要真的挂逆指値）。同时在 RSS 适配器里实现了 `place_protective_stop()`
> 与逆指値的每日改挂，`--protective-stop` 打开后 `intraday` 假设才成立。
> 两种模式跑一遍，差额就是"没挂逆指値"的代价，可以量化。

### P0-5　没有幂等，重复运行会重复下单
`paper_trader.py` 全文无任何 `order_id` / `client_id` 概念。
Windows 任务计划程序在上一次未结束时再次触发、或你手工重跑一次确认，
同一个信号会被发两次。卖出路径尤其危险（`broker.sell(t, pos["qty"])` 重复调用）。

> 改版：每个订单带 `client_id = 交易日-代码-方向`，`OrderGuard` 跨进程去重，
> 券商层再做一次拦截；计划任务也配置为 `MultipleInstances IgnoreNew`。

### P0-6　指値价格不对齐呼値，实盘会被拒单
原版 `README.md`：「发单用指値而非成行，限价 = 现价 × 1.005」

東証的**呼値（よびね / tick size）** 分价格带：3,000 円以下 1 円、3,000 超~5,000 円 5 円……
7203 现价 2,987 → 限价 3,001.9，落在 5 円档上是非法价格，券商直接拒单。
`broker.py` 的 `_place()` 把 `limit` 原样传给 VBA，没有任何取整。

> 改版：`tick.py` 实现完整呼値表，买单向下、卖单向上取整；跨价格带时二次校验。
> 并注明 JPX 已公告 **2027-03-01 起改为按个股流动性（STR）决定呼値**，届时需更新该表。

### P0-7　状态文件写在"当前工作目录"，定时任务一跑就丢仓
`paper_trader.py:29`（`DAILY_FILE = "daily_anchor.json"`）、`broker.py:53`（`state_file="paper_state.json"`）

用任务计划程序启动时 CWD 是 `C:\Windows\System32`。
现象是：手工跑有持仓，定时跑每次都从空仓开始，而且两边互相看不见对方的状态。
这是实盘阶段最容易踩、又最难自查的坑。

> 改版：`paths.py` 统一到 `QBREAK_HOME`（默认 `<项目>/var`），与启动方式无关。

### P0-8　状态文件非原子写入，中断即损坏
`broker.py:66-68`
```python
with open(self.state_file, "w", encoding="utf-8") as f:
    json.dump(self.state, f, ...)
```
写到一半被关机 / Ctrl-C / 任务超时杀掉 → 半截 JSON。下次启动 `json.load` 抛异常直接崩，
**持仓记录全部丢失**且没有备份。

> 改版：`utils.atomic_write_text()` 临时文件 + `os.replace`；读到坏文件时改名隔离并明确报错。

### P0-9　没有数据新鲜度检查，会拿旧 K 线下单
`paper_trader.py:62` 直接 `load_ohlcv(t, years, use_cache=False)` 就算信号，
从不检查最新一根 K 线是不是今天的。
東証 15:30 收盘、yfinance 日线还要 15~30 分钟才更新；
若按 README 说的 15:30 跑，很可能拿**昨天的 K 线**当今天的信号。休市日跑更是直接重放昨天。

> 改版：`RiskConfig.stale_data_max_days` 守卫，超期直接拒绝交易并通知；
> 计划任务时间改为 16:10。

### P0-10　RSS 侧没有约定核对，README 写了但代码没做
原版 README 检查清单：「每笔订单后读回 Pos 表核对约定；程序内做『发单→10 秒内查约定→不一致则告警停止』」
但 `broker.py:151-157` 的 `_place()` 发完宏就直接返回 `status="SENT"`，没有任何回读。
未成交 / 部分成交 / 被拒，程序一概当成功，本地记账与券商实际持仓从此分叉。

> 改版：`_confirm()` 在 `confirm_timeout_s` 内轮询 `QB_QueryOrder`，
> 区分 `FILLED / PARTIAL / SENT(未约定)` 并落日志告警。

---

## 2. 严重问题（P1）：结果失真或会崩

| # | 位置 | 问题 | 改版处理 |
|---|---|---|---|
| P1-1 | `backtest.py:58` | `budget = mark_to_market(d) * position_pct`，用**当日收盘**权益决定**当日开盘**的买入金额 → 前视偏差 | 改用前一日收盘权益 `equity_prev`；`tests/test_engine.py` 有断言锁住 |
| P1-2 | `optimize.py:68-69` | OOS 窗口先切片再算指标，`range_n=90` 时前 90 根全是 NaN，6 个月的样本外只剩 1/3 可用 | 指标在完整历史上计算，引擎只限制**交易窗口**（指标只用 ≤t 数据，不引入前视） |
| P1-3 | `backtest.py:44-51` | `pending_exit` 在标的当日无数据/已被平仓时不清理，残留条目会在重新建仓后立刻触发"幽灵卖单" | 执行前校验持仓是否存在，不存在即清理；`test_halted_ticker_does_not_lose_pending_exit` |
| P1-4 | `backtest.py:57` | 无跳空过滤：隔夜 +15% 开盘（ストップ高）也按开盘价成交 | `max_entry_gap_pct=3.0` 默认过滤，并在报告里统计被过滤的信号数 |
| P1-5 | `broker.py:46` | `equity()` 对取不到价的标的 `self._prices[ticker]` → `KeyError`，一只票停牌就整个程序崩 | 退回成本价，绝不让权益计算中断 |
| P1-6 | `paper_trader.py:32-38` | `load_params` 只捕获 `FileNotFoundError`；JSON 坏掉或多一个键 → `TypeError` 崩溃 | 按字段过滤 + 类型强制 + 异常降级到默认参数 |
| P1-7 | `data.py:43-45` | parquet 缓存**永不过期**，第二天跑的还是昨天的数据 | 缓存带 `fetched_at` 元数据 + TTL（默认 12 小时） |
| P1-8 | `paper_trader.py:91` | `hold >= p.max_hold_days * 1.45`，用"自然日≈交易日×1.45"近似 | 按实际处理过的 K 线数累加 `hold_bars` |
| P1-9 | `optimize.py:74` | 全部参数组合都不合格时 `gs.iloc[0]` → `IndexError` | 空结果/全 `-inf` 时跳过该窗口并记日志 |
| P1-10 | `data.py:16` | `abs(hash(ticker))` 受 `PYTHONHASHSEED` 影响，同一 ticker 每次运行数据都不同 | 改用 `zlib.crc32`，可复现；有测试锁住 |
| P1-11 | `config.py:57` | 日本株手续费写 0.055%，但楽天「ゼロコース」国内株手续费已是 **0 円**；美股 0.495% 缺 **上限 22 美元** | `ExecConfig.for_market()` 按市场给默认值，含最低/上限 |
| P1-12 | `data.py:52` | 只 `dropna()`，不检查重复日期、`High<Low`、未复权拆股造成的 ±50% 跳变 | `validate_ohlcv()` 全套检查 + 明确告警 |

---

## 3. 中等问题（P2）：可维护性与策略本身

| # | 问题 | 改版处理 |
|---|---|---|
| P2-1 | 逐只 `yf.download`，20 只 = 20 次请求，容易被限流 | 批量下载 + 指数退避重试 |
| P2-2 | 预热期不发信号只依赖"NaN 比较为 False"的隐式行为 | 显式 `warmup_bars` 屏蔽 |
| P2-3 | **没有任何测试**。回测引擎是资金决策的依据，一行改错没人发现 | 83 个单元测试，含"无前视偏差"property test |
| P2-4 | `from config import ...` 扁平导入，换个目录就崩 | 改为包 `qbreak/` + 单一入口 `run.py`，任意 CWD 可运行 |
| P2-5 | `consistently_good()` 返回全是字符串的 DataFrame，写回 JSON 会变成 `"60"` | `_coerce()` 还原类型；`StrategyParams.__post_init__` 再兜一层 |
| P2-6 | README 承诺"熔断发通知"，代码里没有 | `notify.py`（webhook / SMTP，仅标准库） |
| P2-7 | 指标缺 Sortino、每笔期望、最大连亏、资金暴露、**分年度收益** | `metrics.py` 全部补齐——一条 5 年 CAGR 常常是某一年撑起来的 |
| P2-8 | 没有基准对照 | 报告里附等权买入持有基准 |
| P2-9 | 日志无轮转，跑一年后是个几百 MB 的文件 | `RotatingFileHandler` |
| P2-10 | **策略叫"横盘突破"，但四个条件里没有任何一条要求价格突破箱体上沿**，抓的其实是"突破前的蓄势" | 新增 `require_breakout` 开关（默认关，保持可复现），打开后才是字面意义的突破 |
| P2-11 | 20 只 × 5 年信号太少（原版 README 自己也承认），且无流动性/趋势过滤 | 新增 `min_turnover` / `trend_ma_n` / `min_price` / ATR 止损 / 时间止损 |
| P2-12 | 无差金決済防护（現物同一营业日同股回转） | `forbid_same_day_rebuy` |
| P2-13 | 引擎用 pandas 标量访问 `.at[d, col]`，网格搜索很慢 | 改为 numpy 对齐矩阵，单次回测 0.03 秒（约快 1~2 个数量级），并按子参数缓存指标 |

---

## 4. 法规与账户（非代码，但会实际影响你）

- **NISA 口座不要用于自动交易**：来回买卖会消耗非課税枠，且 NISA 的亏损不能与其他所得损益通算。用**特定口座（源泉徴収あり）**。
- **楽天「ゼロコース」需要同意 SOR・R クロス**才能享受国内株 0 円手续费——这会改变你的实际成交场所，滑点假设要相应验证。
- **RSS 利用規約**：自动化仅限本人账户、合理频率。日线策略每天一次请求量极小，不是问题。
- **美股走不了 RSS**：RSS 不支持美股，US 只能停留在回测/模拟盘阶段（改版已在 `live US` 上直接拒绝）。

---

## 5. 一句话总结

原版的**策略描述、阶段划分、README 的风险意识**都在水准之上；
问题集中在"把想法变成能托管真钱的程序"这一段——
**风控写了但不生效、状态存了但会丢、约定发了但不核对、假数据会伪装成真结果**。
改版把这四类问题逐条堵上，并用 83 个测试把规则固化成可执行的说明书。
