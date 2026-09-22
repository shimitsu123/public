# Excel ⇄ 楽天 RSS 桥接搭建（第4阶段前置）

> 只有这一步是**必须在 Windows 上手工做一次**的。做完之后 Python 侧完全不用改。

## 0. 前提

| 项目 | 说明 |
|---|---|
| OS | Windows（RSS 是 Excel COM 插件，macOS/Linux 不可用） |
| Excel | **桌面版**（Microsoft 365 / 2019 以上）。网页版 Excel 不行 |
| MarketSpeed II | 已安装并**登录**，RSS 插件显示「接続」 |
| 発注状态 | MarketSpeed II 功能区把状态切到「**発注可**」，否则発注関数一律失败 |
| Python | `pip install xlwings` |
| 对象 | **仅国内株**。RSS 不支持美股，`run.py live US` 会直接拒绝 |

## 1. 建工作簿

1. 新建 Excel，另存为 **启用宏**的 `rss_bridge.xlsm`（放在固定路径，例如 `D:\trading\rss_bridge.xlsm`）
2. `Alt+F11` → 文件 → 导入文件 → 选择本仓库的 `excel/RssBridge.bas`
3. 回到 Excel，`Alt+F8` 运行 **`QB_SetupSheets`** → 自动生成 `Quote / Pos / Ctrl / OrderLog` 四张表和 `CASH`、`ARM` 两个命名区域

## 2. 填 RSS 函数

**Quote 表**（A 列写你的股票池代码，注意是 `7203` 不是 `7203.T`）

| | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
|1|銘柄コード|現在値|始値|高値|安値|出来高|
|2|7203|`=RssMarket($A2,"現在値")`|`=RssMarket($A2,"始値")`|`=RssMarket($A2,"高値")`|`=RssMarket($A2,"安値")`|`=RssMarket($A2,"出来高")`|

**Pos 表**：A:C 用 RSS 的保有株式系列函数拉持仓，`E2`（命名为 `CASH`）填買付可能額。

> ⚠️ **函数名与引数名必须对照当期官方「RSS 関数一覧」PDF**。RSS 的函数表每年更新，
> 网上博客里的写法很可能已经过期。填完后 `Alt+F8` 运行 **`QB_SelfTest`**，
> 它会逐项告诉你哪里没通。

## 3. 填発注函数（唯一需要写代码的地方）

打开 `RssBridge.bas` 里三处 `★TODO★`，按 PDF 填入真实的 RSS 発注 / 注文状況 / 取消函数调用：

- `QB_PlaceOrder`：下单，把券商返回的注文番号赋给 `orderId`
- `QB_QueryOrder`：按注文番号回读約定数量 / 約定単価 / 状態
- `QB_CancelOrder`：撤单（跟踪止损改挂逆指値时会用到）

填写要点：
- **口座区分选「特定」，不要用 NISA** —— 自动交易来回买卖会把 NISA 额度浪费掉，而且 NISA 亏损不能与其他所得损益通算
- 执行条件：本桥用 `order_type = LIMIT / STOP`，`condition = NORMAL / OPENING(寄付) / GTC`
- 日线策略在收盘后运行，买卖单都应下成 **寄付（次日开盘）**，这样才和回测的「T+1 开盘成交」一致

## 4. 日常操作

| 时点 | 动作 |
|---|---|
| 开市前 / 运行前 | 在 `Ctrl!B1`（ARM）手工填入 `ARMED` |
| 16:00 JST 之后 | 运行 `python run.py live JP`，程序发出次日寄付单 |
| 运行结束后 | 把 ARM 单元格**清空** |

`ARM` 是最后一道人工闸门：Python 不会、也没有办法自己写入这个单元格（VBA 侧也做了二次检查）。
这意味着任何程序 bug 都不可能在你不知情的情况下发出订单。

## 5. 常见故障

| 现象 | 原因 |
|---|---|
| `打不开工作簿` | Excel 没启动，或路径写成了相对路径。用绝对路径 |
| `RSS 取不到现在值` | MS2 未登录 / RSS 未「接続」/ Quote 表 A 列没有该代码 / 函数名过期 |
| 発注函数返回错误 | 没切到「発注可」；或口座区分、売買区分取值不对 |
| `not_implemented` | `★TODO★` 还没填 —— 这是故意的默认值，防止拿占位代码去实盘 |
| Python 报 COM 错误 | Excel 弹了模态对话框（比如"是否保存"）挡住了。关掉对话框，设置自动保存 |
