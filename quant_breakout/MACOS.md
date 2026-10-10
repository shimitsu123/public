# macOS 全自动运行指南（立花証券 e支店 API）

> **2026-09-25 深夜更新**：用户改用**立花 e支店**（不做美股个股 → 楽天的美元 / 换汇逻辑用不到；立花 API 能在 Mac 上无人值守下单）。
> 模拟盘已按立花個別コース计费（9/28 起）。**一个账户方案（S0C2）的实盘执行器 `run.py live-u` 已完成，并用模拟账户演练过（见 §1.6）**。
> **现在（立花还没开户）：先在 Mac 上做模拟操盘 —— 见 §1.7，一条命令装好，每个交易日早上自动跑、发通知、与云端模拟盘逐日比较。**
> §5〜§6 的分市场守护进程是旧的「每个市场一个账户」方案，一个账户模式下会拒绝运行，只作参考；§7 清单里的 `--protective-stop`、§8 表的后几行与
> 「逆指値是永远在岗的保险」也是旧方案的说法（2026-10-09 标明）：**现行执行器不挂逆指値、盘中不盯价**，离场只在每个交易日 07:40 的决策里下寄付卖单
> （Mac 那天没跑就不卖 → 09:30 自检 + 外部心跳提醒，§1.6「运行保障」）。
> 上线后的运维（2026-10-09 补）：§1.6「上线头 5 个交易日的值守清单」「退出实盘 / 回到模拟」、§1.14「换 Mac」、§8「最后停止手段」（立花网页把 API 利用設定「無効化」）。

> 面向：Mac + 不装 Excel + 想开机自启、全天常驻、自动买卖。
> 结论先行：**楽天走不通**（RSS 是 Windows 专用 Excel 插件），换 **立花証券 e支店 API** 是
> macOS 上唯一干净的方案（Apple Silicon 的 Mac mini 也可以：API 是纯 HTTP，不依赖操作系统）。
> 开户要邮寄文件（2026-05 起官方公告「通常よりもお時間」），等待期间用 `--broker paper` 把整套流程完整演练一遍。
> **ｅ支店不做美股**：美股指数仓位改用东证上市的 `1655.T`（日元），同一个账户里交易。
> （2026-10 起闲置资金的核心 ETF 是 `1545.T` / `1482.T`（`var/sim.json` 的 idle_cash Q1B）；1655 只留在基准账户的比较与 probe 的取价 / デモ发单检查里。）

---

## 0. 三条路的取舍（为什么是立花）

| 券商 | macOS 原生 | 接口 | API 费用 |
|---|---|---|---|
| **立花証券 e支店** | ✅ | HTTP(GET+JSON) + 实时推送 | 0 円 |
| 三菱UFJ eスマート（kabu） | ❌ | REST，但要 kabuステーション（Windows）常驻 | 0 円 |
| 楽天証券 | ❌ | MARKETSPEED II RSS = Windows + Excel | — |

注意：**必须开「e支店」账户**（不是ストックハウス）；立花一个人只能开一个口座（ｅ支店与对面口座二选一）。
楽天账户可以继续留着手工用，不冲突。

费用（2026-09-25 官网核对，仅对该时点有效）：現物 個別コース 每笔 10 万 77 / 50 万 187 / 100 万 341 円…（ETF 同表），
API 利用料 0 円，口座管理料 0 円；入金只能银行汇款到みずほ銀行的专用账户（汇款手续费自付，没有即时入金），出金免费。
按 100 万円规模每年约 1.0～1.3 万円手续费（`scripts/broker_cost_study.py`）。

---

## 1. 现在就能做（不需要任何账户）

```bash
cd quant_breakout
pip3 install -r requirements.txt
python3 run.py doctor          # 环境自检
python3 run.py selftest        # 155 个单元测试
python3 run.py backtest JP     # 真实数据回测
python3 run.py optimize JP --save
```

**守护进程演练**（用 yfinance 的延迟报价模拟盘中，完全不碰真钱）：

```bash
python3 run.py daemon JP --broker paper --dry-run
```

开着它过一个交易日，观察 `var/logs/qbreak.log`：
前場/午休/後場/收盘的状态切换、止损检查、收盘后的日线流程，应该全部按预期走。
**这一步跑顺之前，不要碰实盘。**

---

## 1.5 等开户期间：半自动模式（留在楽天，今天就能用）

```bash
python3 run.py signal JP --push      # 每个交易日 16:10 后跑一次（cron/launchd 均可）
python3 run.py pos add 7203.T 100 3000   # 在楽天 App 成交后登记
```

程序算信号、算数量、算寄付指値和逆指値，推送一张清单到你手机；你在 iSPEED 里照抄，
**并把逆指値挂上**。这个模式下程序永远不会发单。

## 1.6 一个账户方案的实盘执行器（`run.py live-u`，2026-09-25）

和模拟盘用**同一个推进器**（`qbreak/unified.py`）：模拟盘按「开盘价 ± 滑点」撮合，执行器把**立花的实际成交**记进同一份状态，
收盘后的离场判断与统一决策是同一段代码。代码 `qbreak/live_unified.py`；账本 `var/state/live_unified_tachibana.json`
（デモ `…_tachibana_demo.json`、dry-run `…_dryrun.json`，互不干扰）。

| 时刻（周一至五） | 命令 | 做什么 |
|---|---|---|
| 07:40 | `live-u --broker tachibana` | ① 对账：昨天下的单向立花查实际成交（股数 / 均价）记进状态；卖单没成交（ストップ安等）→ 仍是待卖，今天再下；买单没成交 → 作废（与回测「信号只在次日开盘有效」相同）<br>② 核对：券商持仓 = 状态持仓（不一致 → 今天不下单、报警）；现金以买付可能額为准（税、实际手续费、分红入账在这里对齐）<br>③ 决策：与模拟盘同一段代码<br>④ 下单：卖单 寄付成行；买单在开盘前余力内下 寄付指値（个股 = 信号日收盘 ×1.03，核心 ETF（现在 1545 / 1482）= 收盘 ×1.02），放不下的留到开盘后 |
| 08:35 | `live-u --broker tachibana --retry` | 重试（2026-10-04 加）：07:40 那次已经跑完 → 什么都不做（绝不换一份输入再决策一次）；没跑完（Mac 睡着 / 关机、断网、行情没更新被挡）→ 按正常流程跑一次（不等云端；寄付单 08:55 截止） |
| 09:05 | `live-u --broker tachibana --phase open` | 留下的买单：按始値做同样的跳空（≤ 信号日收盘 +3%）与名额检查，按模型的规则（开盘价 + 滑点）减股，下当日限り指値（占用的余力放不下时把限价降到余力能承受的最高呼値，仍 ≥ 始値） |
| 09:20 | `live-u --broker tachibana --phase open --retry` | 重试（2026-10-04 加）：还有留到开盘后、没下的买单才跑 |

**为什么分两段**：券商受理买单时就按「指値 × 股数」占用余力，开盘前还没卖出的核心 ETF / 个股的钱不算余力。满仓（个股 + 核心 ETF）时的新个股买单
几乎都要等开盘卖出核心 ETF → 在开盘后（盘中）成交，价格 ≠ 开盘价 —— 这是实盘相对模拟盘最主要的差异（历史日线模拟不出盘中价格路径）。
核心 ETF 的买单：开盘前放得下的部分先下寄付（按开盘价成交，与模型相同），只有余数留到开盘后（多一笔手续费，通常 77 円）。
（核心 ETF 现在是 1545 / 1482；下面 2026-09 的演练当时用的是 1655。）

**用模拟账户演练**（`python run.py live-u-rehearse` → `var/out/live_rehearsal.md`；同一套真实历史行情，S0C2、立花個別コース、100 万円起）：

| 窗口 | 模拟账户 | 回测引擎 | 执行器 | 最终权益差 | 说明 |
|---|---|---|---|---|---|
| 5 年 | 模拟券商（规则与引擎相同） | 23.02% | 23.02% | ¥0 | 351 笔成交逐笔一致，其中 154 笔走「开盘后补单」 |
| 5 年 | 立花适配器 + 模拟交易所 | 23.02% | 22.99% | −¥3,864 | 个股交易逐笔一致；差额是 1655 拆单多付的手续费 + 1 笔限价没成交 |
| 20 年 | 模拟券商 | 12.87% | 12.87% | ¥0 | 1,262 笔逐笔一致 |
| 20 年 | 立花适配器 + 模拟交易所 | 12.87% | 12.87% | −¥4,865 | 41 笔「模型会买、限价没成交」（多在 1655 上市前的拼接行情里），之后路径分叉 |

「立花适配器 + 模拟交易所」走的是**真实的立花发单 / 約定照会 / 持仓 / 余力代码**（`qbreak/brokers/tachibana_sim.py` 只替换网络层，
撮合假设与回测相同），所以演练覆盖了：登录解密、发单字段、寄付 / 当日限り、两段式买入、部分成交、ストップ安顺延、持仓与现金核对。
**没覆盖**：盘中价格路径、比例配分、真实的手续费与税、立花服务器的实际应答（这些只能在デモ / 本番验证）。

**每天的模拟账户**：9/28 起 `sim-day`（云端例行任务）结束时自动用模拟券商把执行器走一遍（账本 `var/state/live_unified_paper.json`），
与模拟盘逐日比较；日报顶部显示「一致 / 不一致」，不一致或失败会进「数据完整性」（例行任务汇报的第一行）。

**安全闸**（任何一道不过 → 不下单，只对账、记账、报警）：HALT 文件 / ARM 未解锁 / 单笔上限（默认 权益 ×1.05）/
时间窗口（寄付单在成交日 08:55 前；开盘后补单 09:00〜15:25；2026-10-09 起错过寄付的个股卖单改当日限价卖，见「运行保障」）/ 行情没更新到应有的交易日 / 持仓与券商不一致（同一天的盘中 / 开盘后运行也挡）/ 有状态不明的单；2026-10-09 起还有（立花）：异常熔断 / 账本属于另一台 Mac / 新代码的冒烟测试没过 / 账本读不了 / 第二暗証被拒之后的单 / Yahoo 收盘与立花前日終値差 > 3% 的买单。

**运行保障（2026-10-04 补齐；用户「什么都不改，把没有考虑的点自动补齐」：只补工程，交易规则一点没改）**：

| 没考虑到的情况 | 现在怎么处理 |
|---|---|
| Mac 睡着 / 醒来时 launchd 把错过的几个任务同时启动 | **运行锁**：同一份账本同一时间只有一个执行器进程（`fcntl` 独占锁，进程结束或崩溃时系统自动释放）；后来的等最多 20 分钟（`--lock-wait`），等不到就不运行并通知 |
| 07:40 / 09:05 没跑（睡着、断网、行情晚到） | **08:35 / 09:20 重试**（上表）；`liveu.sh run` 运行期间用 `caffeinate -i` 防止再睡，立花模式早上跑完让 Mac 醒到 09:35（09:30 自检也按时跑）；工作日自动唤醒要你在终端做一次 `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`（2026-10-09 起 06:40：本机例行任务的日报 06:45，§1.13；执行器只要 07:40 之前；06:40〜07:40 由 `com.qbreak.wakehold`（`caffeinate -i`，`install_launchd_live_u.sh` / `mac_setup.sh` 装）保持清醒，不靠桌面版开着；接着电源、不合盖）；等当天的日报最晚等到 08:30 |
| 人不在 Mac 旁边想停 | **远程停止**：在云端（手机）对话里说「停 / 今天不要下单」→ Claude 跑 `python run.py remote-halt --reason …` 并提交推送 `var/HALT_REMOTE` → Mac 的执行器下一次运行（07:40 / 08:35 / 09:05 / 09:20）建本地 HALT。同一个 id 只生效一次；已经发出的单不撤（要撤：在 Mac 对话里说「撤单」/ 面板「今天的单」的「撤单」，或立花网站 / 手机网站）；恢复只在 Mac 上明确说 |
| 入金 / 出金 | 下单本来就按立花的买付可能額（不用改设定）；**登记**之后收益按「投入本金」算、当日损益扣掉入出金：`bash scripts/liveu.sh flow 300000`（出金写负数）。早上的现金差和登记对上就记为到账；没登记的大额现金变化（≥ ¥50,000 且 ≥ 权益 2%）会提醒你登记 |
| 实盘和 ¥100 万的云端模拟盘比 | 金额（本金、税、成交价）一定对不上 → 立花实盘只比「拿的是不是同样的票」（个股、核心 ETF 的品种），不同才报警。**上线初期**（2026-10-09 补）：还从没和模拟盘拿过同样的票、实盘拿的模拟盘都有、模拟盘多出来的是上线前就买的个股（或第一天的核心 ETF 还没成交）→ 写「上线初期：实盘从空仓开始，持仓和模拟盘不同是预期的」、不报警；第一次拿的票相同之后照常 |
| 云端（例行任务）的输入没更新 / Yahoo 取不到行情（2026-10-09 补） | 判断层的三个云端文件（前向记录判断层 / 关联搭配 C / TBF）日期不对 / 没有，或云端模拟盘比执行器的决策日落后 ≥ 1 个交易日 → 通知升 warn、一行摘要「★ 判断层的输入 N 天没更新」、面板 / 页面顶部显示（只提醒：这几层当天不生效，照旧按原规则下单）。连不上 Yahoo、行情落后（立花当天不下单）→ 通知 / 面板写原因 + 修法：Mac 对话里说「升级 yfinance」（`~/.qbreak/venv/bin/python -m pip install -U yfinance`，或 `bash scripts/mac_setup.sh --upgrade-yfinance`）；持仓的行情落后 → 写清「X 今天的离场判断被跳过（行情只到 …）」。不改用 J-Quants（数据源不同属于规则，要你另外决定） |
| 立花的 API 新版本 | 登录应答里有下一个版本的发布日 → 写进日志、通知、页面（「★ 立花通知」）；旧版本会停用（v4r9 已于 2026-09-27 废止），看到就在 Mac 对话里问「立花 API 要更新吗」。2026-10-09 起看到过的预告记进账本（`tachibana_notices`）：**发布日之后也一直提醒（升 ★），直到代码换到新版本**（以前一过发布日就不提醒了），前一晚预检（本表后面「交付書面未読 …」一行）也每晚提醒；显示的是代码已经在用的这一版（v4r10 = 2026-08-29）→ 不提醒；第一次看到时已经过了的日子只提醒、不升 ★；核对过不用更新 → 你在对话里确认后 Claude 运行 `bash scripts/liveu.sh precheck --ack-api <日子>`（只清这个日子的提醒，不登录） |
| 登录失败（交付書面未読、密钥不对等） | 不再是「Python 出错」：执行器停下并把原因写进通知与页面 |
| 上线门槛是否满足 | `bash scripts/liveu.sh gate`（只读）：门槛 ①〜④（2026-10-09 起 ① 的最近一次比较还要在 10 个交易日以内，过期 ★：模拟操盘停了就不再拿以前的连续一致算数；`install_launchd_live_u.sh tachibana` 有意卸掉模拟操盘之后，只量到模拟操盘最后一次运行的那天 → install 到 ARM 之间隔多久都行）+ 准备（本番只读检查、本番 dry-run 跑通过、钥匙串 / 私钥权限 600、doctor（`bash scripts/liveu.sh doctor` 的结果）、定时任务、自动唤醒、Mac 的时区是日本）+ 参考（课税区分、ARM 三种状态 / HALT、入出金） |
| HALT 演练 | `bash scripts/liveu.sh halt-drill`：模拟账户今天早上的运行完成之后（收盘前或休市日），建演练用的 HALT → 跑一次（不下单、账本记下）→ 删掉它；真的 HALT 已经存在就不演练、也不碰 |
| 出事时人不在 Mac 前（2026-10-09 补） | **手机通知**：通知地址是密钥，放钥匙串（`qbreak-webhook`：Discord / Slack / ntfy；`qbreak-smtp`：`host:port:user:password:to`）——定时任务（launchd）读不到 `~/.zshrc` 的 `export`。**邮件（2026-10-09 起用这个）**：你自己在「终端」App 运行 `bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup`（问发件 Gmail 地址、应用专用密码（输入时不显示，空格自动去掉）、收件地址（回车 = 同发件，多个用逗号）→ 先发一封测试邮件 → 发成了才存进钥匙串 `qbreak-smtp`（覆盖旧值；服务器拒绝 = 密码 / 地址不对 → 不存，网络问题 → 问你存不存），打印「已发 / 失败（原因）」；不打印密码、不写文件；Claude 不运行它，也不要把密码贴进聊天）；Gmail 要先开两步验证，再在 https://myaccount.google.com/apppasswords 建应用专用密码（16 位字母）；改 Google 密码会让应用专用密码失效（失效后再运行一次 email-setup）；iPhone 上在「邮件」或 Gmail App 打开通知；建议在 Gmail 建过滤器：主题含 qbreak → 不送进垃圾邮件、标星；别的邮箱 `--host smtp.example.com --port 465`（465 = SMTP_SSL，其他端口 = STARTTLS，都验证证书）。webhook：你自己在终端 `security add-generic-password -s qbreak-webhook -a qbreak -w`（回车后输入，不贴进聊天）。`bash scripts/liveu.sh notify-test` 试发（只打印「已发 / 失败 / 没设置」，不打印地址）。执行器停下 / 拿不到运行锁的通知：同一个账本、同一天、同一段文字只发一次 |
| Mac 整个早上没跑（关机 / 睡着 / 断网）、跑了但没下成单 | **09:30 自检**（LaunchAgent `com.qbreak.watchdog`，周一至五 09:30，`mac_setup.sh` 装；只看：`bash scripts/liveu.sh watchdog --dry`（不写、不发）；`bash scripts/liveu.sh watchdog` = 重新自检一次（会重写结果、没通过会再发通知 / 心跳报失败；不下单）；执行器还在运行时等它结束再判定）：今天早上的执行器跑完没有、有没有状态不明的单、（立花）开盘后的买单下了没有 → 没通过 → 手机 + Mac 通知 + 外部心跳报失败；HALT 生效中不算失败（同一天提醒一次）；结果 `~/.qbreak/home/out/watchdog_<账本>.json`。**外部心跳**（另一半）：在 healthchecks.io 之类建「周一至五 09:30 JST、宽限 30 分钟」的检查，ping 地址存钥匙串 `qbreak-heartbeat` → 自检本身没跑（Mac 关机 / 睡着 / 断网）时那边推送到手机。早上跑完让 Mac 醒到 09:35（立花；模拟账户在装了自检时只在 07:40 的定时任务本身） |
| 执行器这次跑成没有 | 面板 / 手机每个账本顶部一行运行状态（`out/live_unified_<账本>_run.json`）：跑完 ✓ / ★ 停下（原因）/ ★ 今天的单没下 / ★ 被挡 · 被拒 · 状态不明的单（票、方向、股数）/ ★ 今天早上的运行还没完成 / 09:30 自检没通过的原因；有这些情况时 Mac 通知的级别也变成 warn |
| 盘中面板叫的执行器一直失败 | 失败后等待加倍（1 分钟起，最多 15 分钟）；同一天连续失败 3 次 → 当天这个账本暂停自动叫（面板顶部「★ 盘中自动下单暂停」），写新的手动指令或第二天恢复 |
| 07:40 因持仓不一致被挡，08:35 的重试 | 重试在开盘前（09:00 前）再核对一次持仓（不做现金同步），不一致照样不下单——不会因为换了一个进程就绕过核对 |
| 09:05 / 09:20 开盘后补单的单笔上限 | 和 07:40 一样按当前权益 × 倍数重算（另起的进程不再用默认上限把买单挡掉） |
| 数据目录不小心在仓库里 | `run.py` 的立花入口（`live-u --broker tachibana`、`tachibana-probe`、`manual … --broker tachibana`）发现数据目录在仓库里就拒绝运行、不写任何文件（公开仓库：真实账户的账本进去就撤不回）；`.gitignore` 也排除立花的账本 / 检查结果 / ARM / HALT。都经 `bash scripts/liveu.sh`（数据目录 `~/.qbreak/home`） |
| 已经发到交易所的单要撤（2026-10-09 补） | **撤单**：面板 / 手机「今天的单」里还挂着的单有「撤单」按钮（写撤单指令 → 面板马上叫执行器 `--phase cancel`，开盘前 / 盘中都可以、HALT 时也可以）；对话里说「撤单」→ `bash scripts/liveu.sh cancel [<cid>…] --broker tachibana`（不带 cid = 今天全部）；「停并撤单」→ `bash scripts/liveu.sh halt-cancel --broker tachibana`。只撤执行器自己今天的单；撤完向立花再确认一次 → 账本记「已撤单」+ 已成交的股数（第二天早上照立花的实际成交对账）；撤掉的卖单如果规则明天还要卖会再下、撤掉的个股买单不再买（核心 ETF 下一次决策照规则 / 闲置资金比例重新算，可能再买 / 再卖）；手动指令的单被撤 → 那条指令也撤回 |
| 状态不明的单（发送中断 / 网络错误） | 发单之前就失败的（登录失败、DNS / 连接被拒 / TLS）记「被挡」、下次可以重试；可能已到达的才是「状态不明」。**候选**：`bash scripts/liveu.sh unknown --broker tachibana`（只读：立花注文一覧里同代码、同买卖、股数相同或更少的单，按受付时刻接近排序，附登记命令草稿）；执行器因状态不明停下时，候选也写进通知、运行状态（`out/live_unified_tachibana_run.json` 的 unknown）与面板 —— 登记仍要你确认 |
| 持仓与立花不一致 / 在立花网站上人工下了单 | **核对**：`bash scripts/liveu.sh reconcile --broker tachibana`（只读：逐只股数 / 成本、执行器不管的持仓、拆股登记、今天的单、可能原因、登记草稿）；**人工代下登记**：`bash scripts/liveu.sh adopt --broker tachibana <代码> <BUY\|SELL> <股数> <均价> [--date …] [--note …]`（先备份账本、拿运行锁；卖 → 减持仓；买个股 → 新持仓，止损按引擎的新仓算法、占名额；核心 ETF → 改口数；现金第二天早上照常以买付可能額对齐；执行器今天同一只同方向也有已发出 / 已成交的单 → 拒绝（它的成交第二天早上对账自动记；确认是你另外下的单才加 `--separate`）；只在你明确说时运行）。开盘后核对时，差额正好是执行器今天的单成交了 → 显示「…」、不算不一致、不给草稿 |
| 账本坏了 / 改坏了（2026-10-09 补） | **账本备份**：每次执行器运行开始时（`--status` 不算）、登记成交（`--resolve`）/ 撤单 / 人工代下登记 / 换 Mac / 恢复之前，把账本复制到数据目录 `state/backup/live_unified_<账本>_<日期-时刻>.json`（同一分钟或内容没变不重复；每个账本留最近 60 份）。立花的账本读坏了（或不见了、但有备份 / `.corrupt` 文件）→ 执行器停下、**不悄悄从 ¥100 万重来**（读坏的改名 `.corrupt.<时刻>` 留着）；看备份：`bash scripts/liveu.sh restore --broker tachibana --list`（只读：每份的时刻、决策日、现金、持仓）；恢复：`bash scripts/liveu.sh restore --broker tachibana <备份文件名>`（先把现在的账本也备份一份、拿运行锁、账本记一条事件；只在你明确说时运行）。模拟账户读坏照旧从头开始。备份含持仓与现金，只在这台 Mac 的数据目录（不入库）；Time Machine 备份这台 Mac 时请加密（私钥 PEM 本身没有加密） |
| 交付書面未読 / 密钥 / 时钟 / API 版本的问题到 07:40 才发现（2026-10-09 补） | **前一晚预检**（LaunchAgent `com.qbreak.precheck`，周日〜周四 20:00 = 下一个交易日的前一晚；`install_launchd_live_u.sh tachibana` 一起装、切回模拟 / 卸载时一起卸；模拟模式不装）：立花本番只读 —— 拿运行锁 → 登录 → 取余力 → 登出，不下单、不改账本；明天休市、立花闭局（03:30〜05:30）、交易日 07:30 之后（执行器自己会登录）→ 不做。没通过 → 手机 + Mac 通知，原因附错误码对照表的修法（交付書面未読 → 在电脑上登录 e支店网站读完新书面；密钥 / 时钟 / IP / 版本停用 …）；登录应答里的两个预告：交付書面的更新预定日（5 个交易日以内每次预检都提醒）、API 新版本（同本表「立花的 API 新版本」一行）；顺便跑一次上线门槛（只读），和上一次比新出现的 ★ 通知一次。同一天同样的文字只通知一次。结果 `~/.qbreak/home/out/precheck_tachibana.json`（面板顶部显示没通过的原因与提醒）；手动：`bash scripts/liveu.sh precheck`（没装立花本番 → 什么都不做；`--force` 照做）。立花的登录通知邮件官方关不掉（API 登录发不发待开户后确认）→ 预检一天只登一次 |
| 新代码直接进实盘 / 依赖版本漂移 / 系统更新后 Python 坏了 / 单多得离谱（2026-10-09 补） | **冒烟测试**：立花本番早上的运行发现这次用的代码（只看代码：`qbreak/` / `run.py` / `scripts/` / `tests/` / `requirements.*` 的 git 对象 id 的摘要；云端每天推的 `var/` 提交不算新代码）和上一次验证过的不同 → 先跑执行器 / 立花适配器 / 防呆三个测试文件（最多 10 分钟；日志 `~/.qbreak/home/logs/smoke_test.log`）：没过 → 这次只对账、决策，单都不下 + 通知「新代码的冒烟测试没过」；过了 → 数据目录 `.smoke_ok` 记下这个标识。运行状态文件记这次用的 `code`（git 短 hash）、`code_tree`（只看代码的标识）与 `py`（Python / pandas / numpy / yfinance 的版本）。**依赖锁** `requirements.lock`（云端测试通过的那一套确切版本）：`mac_setup.sh` / `install_launchd_live_u.sh` 按它装（装不上退回 requirements.txt）；`bash scripts/dev.sh check` 发现不一致只提醒。**异常熔断**（立花）：一次决策的规则单笔数 > (个股名额 + 核心 ETF 只数) × 2，或金额合计 > 权益 × 2.2 → 全部不下、报 error（正常运行不会出现）。**登录 / 开机时**先试虚拟环境的 Python 能不能 `import pandas, numpy`：不能 → Mac 通知 + 手机通知「Python 环境坏了：在终端运行 mac_setup.sh」 |
| 开盘后补单取价失败 / 还没寄り付き / ストップ安附近的盘中限价（2026-10-09 补） | 09:05 取价整个失败 → 留到开盘后的买单一笔都不放弃（运行状态 ★，09:20 再试）；个别票还没有始値（特別気配）→ 09:05 留着、09:20 仍没有 → 今天不买（记入与模型的差异）。盘中指値夹在当天的制限値幅里（卖 = max(现价 × 0.995, 前日終値 − 値幅)、买 = min(现价 × 1.005, 前日終値 + 値幅)，按呼値取整；前日終値取不到就不夹）；盘中卖单取不到现价 → 不发成行（BLOCKED，手动指令留着等下一次） |
| 早上错过寄付（2026-10-09 用户「做〔77〕B」时同意的执行补救；离场规则本身不变） | 立花：同一决策的补单 / 晚到的早上运行发生在成交日 08:55〜15:25（寄付已经错过）→ 规则的个股卖单（止损 / 离场 / 减仓 / 手动卖）改成**当日限价卖**（与盘中手动卖同一算法：现价 −0.5%、夹在値幅里；取不到现价 → 等下一次运行），规则的买单与核心 ETF 的单今天不下（记入与模型的差异）；09:05 / 09:20 的开盘后运行也会补这种卖单。08:55 之前照旧寄付；早上持仓核对不一致时照样全部挡住 |
| 实盘的起始本金（2026-10-09 补） | 立花账本第一次运行：第一次现金同步时把買付可能額（第一天就有持仓的话加上按收盘的市值）当作起始本金（账本 `capital_jpy`），收益与页面「起始」按它算（不是 sim.json 的 ¥100 万）；第一天不报「现金突然变化」；之后的入出金照 `flow` 登记 |
| 两台 Mac 同时跑同一个立花账户 / 用完不登出（2026-10-09 补） | 立花本番的账本记着属于哪台 Mac（硬件 UUID 的摘要，不存原文）；另一台 Mac 拿着同一份账本运行 → 执行器停下「这个账本是另一台 Mac 的」→ 照 §1.14「换 Mac」做（最后一步 `bash scripts/liveu.sh adopt-host --broker tachibana`，只在你明确说时运行）。立花的执行器、撤单、probe、前一晚预检、`unknown` / `reconcile` 用完都登出（虚拟 URL 马上失效；登出失败不影响结果） |
| 其他小项（2026-10-09 补） | ① 拆股 / 合并后的零股（不足一手）：卖单只卖整数手，零股记进账本并提醒「在立花网站卖（端株手续费 0.55%）」，卖完说一声 → `adopt … SELL` 登记；② 拆股生效当天早上的单按拆股后的股数 / 价格；③ 立花本番的寄付买单发出前拿立花的前日終値核对决策用的收盘：差 > 3% → 那只的买单不下（卖单只提醒）；④ 第二暗証错了：第一笔被拒之后这次运行后面的单都不发（换值见 §3）；⑤ 早上持仓核对不一致 → 同一天的盘中 / 开盘后运行也不下单，直到下一次早上核对一致；⑥ 东证临时休市：`bash scripts/liveu.sh closed list`（只看）/ `closed add YYYY-MM-DD --note …`（数据目录 `extra_closed.json`；你确认后才写）；⑦ 日志 `.out` / `.err` 超过 5 MB 自动轮换（留 3 份），数据目录的磁盘剩余 < 1 GB → 通知；⑧ 只能用 IPv4（错误 10005）→ 数据目录的 `tachibana_spec.json` 写 `"force_ipv4": true`；⑨ 交易单位 1 口的 ETF 2027-03-01 起的呼値按新表（O 表）取整 |

发单前先把「发送中」写进账本再发；网络错误（可能已被受理）的单**绝不自动重发**，第二天早上执行器会停下，等你在立花网页的注文一覧确认后登记：

```bash
bash scripts/liveu.sh --broker tachibana --status                                   # 账本：持仓、今天的单、最近事件（不连券商）
bash scripts/liveu.sh unknown --broker tachibana                                    # 注文一覧里的候选 + 登记命令草稿（只读）
bash scripts/liveu.sh --broker tachibana --resolve U2026-10-01-BUY-7203.T --filled 100 --px 3001   # 没成交填 --filled 0
```

**上线步骤（立花开户之后）**

立花的デモ環境（官方 https://www.e-shiten.jp/Service/demo.html ，2026-09-25 核对，仅对该时点有效）：**要先开 e支店账户**才能用；
登录 8:30～27:00（含周末）；约定时间 9:00～11:30 / 12:30～15:00 / 15:10～27:00；**价格不是真的**（指値按指値成交、成行一律 100 円成交）；
当天的注文与约定**第二天重置**。所以デモ只能检查 API 的字段与流程，**不能做多日演练**（多日演练就是 §1.7 的 Mac 模拟操盘）。

1. `bash scripts/liveu.sh probe --demo`（= `run.py tachibana-probe --demo`；只读：登录、取价、持仓、余力、注文一覧、立花銘柄マスタ）全 `[OK]`
   （结果记在 `~/.qbreak/home/out/tachibana_probe_demo.json`，只有通过与否与 API 版本段（例 `e_api_v4r10`），没有金额与密钥；上线门槛的检查读它，
   版本段和现在的仕様不同 / 旧格式没记版本 → 门槛要求重做）。取价：交易时间里三只都取不到现价 = NG（字段名可能不对）；盘外现价为空是正常的，
   但至少要有前日終値（连前日終値都没有 = NG）；注文一覧调用失败 = NG
2. デモ一天的发单检查（8:30 以后）：`bash scripts/liveu.sh probe --demo --order-test`
   —— 当日指値买 1655 一单元 → 打印約定照会应答的字段名 → 余力与持仓的变化 → 寄付卖单 → 按注文番号撤单
   → **寄付指値买**（2026-10-09 加：执行器每天最常用的单型；限价低于现价 10%，避免成交）受理 → 按注文番号撤单。要确认的几点
   （按公开仕様書写的，没在真实服务器上跑过）：约定明细的字段（`sYakuzyouSuryou` / `sYakuzyouPrice` / `aYakuzyouSikkouList`，
   不对就改 `~/.qbreak/home/tachibana_spec.json`）；买付可能額在成交后怎么变；寄付单能否按注文番号撤掉；寄付指値买能否受理
3. `bash scripts/liveu.sh --broker tachibana --dry-run --no-clock`（本番：登录、读持仓与余力、打印会下的单，不发；
   跑通过一次 = gate「准备」的「⑤ 本番 dry-run」OK）；`bash scripts/liveu.sh doctor`（环境自检，结果给 gate 的「⑥ doctor」看）
4. 本番：`bash scripts/liveu.sh probe`（本番只读检查）→ 入金 → `bash scripts/install_launchd_live_u.sh tachibana`
   （07:40 早上的单 + 08:35 重试 + 09:05 开盘后补单 + 09:20 重试）→ 终端里 `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`（一次；2026-10-09 起 06:40，§1.13）
   → 手机通知与外部心跳存进钥匙串（上面「运行保障」表；邮件：你自己在终端 `bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup`；`bash scripts/liveu.sh notify-test` 试发）
   → `bash scripts/liveu.sh gate` 全部 OK（含 Mac 的时区是日本 +0900：定时任务按本地时间触发）→ 你明确说之后 `echo ARMED > ~/.qbreak/home/ARM`
   （Mac 上执行器的数据目录是 `~/.qbreak/home`，ARM / HALT 都放这里）
   装了立花本番之后：操作面板（Mac + 手机）不带 `?book=` 默认打开立花（顶上红色「真钱（立花本番）」），模拟账户页标「已停」；
   登录 / 开机时打开 `page_tachibana.html`，今天早上的运行没完成只发 Mac 通知（不补跑真钱）
5. 本番的「开盘前买付可能額」（是否含未交割的卖出所得、开盘卖出成交后是否即时反映）デモ验证不了（假价格、每天重置）：
   头几天每天看 `bash scripts/liveu.sh --broker tachibana --status` 与日志；执行器每天早上都会核对持仓与现金，不一致就停下
   另外记一下譲渡益税什么时候从余力里扣（〔77〕C T4）：头几次核心 ETF / 个股**盈利**卖出之后，看当天与受渡日（T+2）的余力变化，
   确认税是在约定日还是受渡日扣（面板「年内已实现」一行有预计代扣额可对照）；开盘后的买单因为余力少被减股 / 放弃时，日志会写「疑似譲渡益税预扣」
6. 第一天：执行器从最新收盘的决策开始，现金按券商余力（第一次的買付可能額记作起始本金）；同一账户里请不要人工买卖执行器管的票
   （股票池 + 核心 ETF 1545 / 1482；NISA 等别的课税区分里的同一只票也算进合计），否则持仓核对会停下
   （真的在立花网站上照单下了 → 第二天早上之前 `adopt` 登记，§8「立花 API / Mac 出故障那天」）；头 5 个交易日照下面的值守清单看

### 上线头 5 个交易日的值守清单（2026-10-09 补；缺口盘点 C-07）

先用较小金额（路线图 4：1〜2 周）。这几天每天按下面的时刻看一眼（都在面板 / 手机的「立花（本番）」页、通知里；括号里的命令只读）。
「马上停」= 在 Mac 对话里说「停」（立刻建 HALT，不用再确认；人不在 Mac 旁边 → 手机面板的 HALT 或云端对话里说「停」）。
HALT 不撤已经发出的单：要撤就说「撤单」（面板「今天的单」的「撤单」/ `bash scripts/liveu.sh cancel --broker tachibana`），或在立花网站 / 手机网站上撤。

| 时刻（JST） | 看什么 | 哪种情况马上停 |
|---|---|---|
| 前一晚 20:00 | 前一晚预检：没收到通知 = 通过；面板顶部显示没通过的原因与提醒（`~/.qbreak/home/out/precheck_tachibana.json`） | 预检没通过、当晚修不好（交付書面未読：在电脑上读完就好，不用停） |
| 07:40〜07:50 | 通知与面板「今天的单」：今天发了哪些寄付单（票、买卖、股数、限价）、与云端模拟盘拿的是不是同样的票；面板顶部运行状态 ✓ / ★（`bash scripts/liveu.sh --broker tachibana --status`） | 单的票 / 股数明显不对（例：股数多了一位、不是规则会买的票、同一只票重复）、出现「异常熔断」、看不懂的 ★ |
| 08:35 | 只有 07:40 没跑完时才有重试；运行状态与 `~/.qbreak/home/logs/com.qbreak.liveu.retry.out` | 重试也停下、原因看不懂 |
| 09:00〜09:25 | 寄付成交之后：立花网站的注文一覧 / 約定照会和面板「今天的单」对得上；09:05 / 09:20 开盘后补单（余力放不下的买单）下了没有 | 立花那边有面板上没有的单（另一台 Mac / 人工）、状态不明的单（先 `bash scripts/liveu.sh unknown --broker tachibana` 看候选；它会登录立花一次，09:05 / 09:20 的执行器在跑时自己等它结束再登录，免得把执行器的会话踢掉） |
| 09:30 | 09:30 自检（没通过才有通知；外部心跳那边没报警） | 自检没通过、原因不是 HALT |
| 收盘后 | 約定照会的成交价 / 手续费和面板一致（個別コース的表）；面板的权益、现金 | 手续费 / 成交和面板差得离谱 |
| 第二天 07:40 | 对账：昨天的成交（股数 / 均价）记进账本、持仓核对一致；现金按買付可能額对齐（约定基准还是受渡基准、开盘卖出后余力何时反映 —— デモ验证不了，头几天对照立花的余力画面记一下） | 持仓核对不一致：执行器自己已经不下单 → 先 `bash scripts/liveu.sh reconcile --broker tachibana` 看原因，不要直接改账本 |

5 天都正常 → 照路线图 4 用小金额跑满 1〜2 周，再由你决定加到计划金额（入金后 `bash scripts/liveu.sh flow <金额>` 登记）。
哪天出现看不懂的 ★：先说「停」再问；执行器自己挡下的（持仓不一致、状态不明、冒烟测试没过、熔断）不会下单，不用抢时间。

### 退出实盘 / 回到模拟（2026-10-09 补；缺口盘点 C-07）

每一步都由你在 Mac 对话里明确说（停下单除外）；Claude 不建议卖不卖。

1. 说「停」→ HALT（之后不再发新单）；已经发出、还挂着的单要撤就说「撤单」（或一起说「停并撤单」= `bash scripts/liveu.sh halt-cancel --broker tachibana`）。
2. 决定立花里的持仓（个股 + 核心 ETF）怎么办：
   - **卖掉**：最简单 = HALT 留着、你自己在立花网站 / 手机网站上卖（执行器不会再下任何单；之后不再用执行器就不用登记，以后还要用就 `adopt … SELL` 登记）。
     想让执行器去卖（寄付 / 盘中当日限价）→ 写手动卖出指令（`bash scripts/liveu.sh manual sell <代码> --broker tachibana`，每只；核心 ETF 1545 / 1482 也一样，
     卖出全部 = 之后停买闲置资金 ETF），再由你说「恢复下单，删除 HALT」（HALT 时执行器连卖单也不发）；注意删掉 HALT 之后的运行也会照规则下新的买单
     （「只卖不买」现在没有开关）→ 卖完马上再说「停」。
   - **继续由执行器管**（止损 / 离场照规则，也会照规则买）：那就不是退出 —— 删掉 HALT、保留定时任务即可。
     「只卖不买、不开新仓」属于交易规则，现在没有这个开关（要的话另外说，由你决定、记进 sim_changes）。
   - **自己管**：HALT 留着 + 卸载立花的定时任务 → 持仓从此没有任何规则在管（止损也不执行），你在立花网站上自己处理。
3. 锁上：删掉 `~/.qbreak/home/ARM`（`rm ~/.qbreak/home/ARM`；之后执行器即使被误启动也不会向立花发单）。
4. 卸载 / 切回模拟操盘：`bash scripts/install_launchd_live_u.sh paper`（卸掉立花的 07:40 / 08:35 / 09:05 / 09:20 与前一晚预检，装回模拟操盘 07:40）；
   切回模拟操盘之后面板 / 手机默认回到模拟账户、登录时打开 `page_paper.html`。
   只卸不装：`bash scripts/install_launchd_live_u.sh uninstall` —— 立花的账本还在、模拟操盘也没装 → 面板 / 手机**仍默认打开立花的账本**
   （红色「真钱（立花本番）」；看模拟账户点上面的「模拟账户」或地址加 `?book=paper`），登录时打开的是 `page_paper.html`（不再更新）。
5. 模拟账户重新起步：模拟账本停了几周再跑会和云端对不上 → 把 `~/.qbreak/home/state/live_unified_paper.json` 移到别处（不要直接删；`state/backup/` 里也有它的备份），
   下一次 07:40 从云端模拟盘当时的状态重新开始（模拟账本不在时执行器自动从云端模拟盘的状态抄一份；§1.7「与云端「不一致」时」同样的做法）；
   上线门槛 ① 的「连续一致」从那天重新数。
   HALT 对模拟账户也生效 → 模拟操盘要继续跑，HALT 要由你说「删除 HALT」（ARM 已经删了，立花不会发单）。
6. 立花的账本 `live_unified_tachibana.json` 留着（记录；以后再上线前先 `bash scripts/liveu.sh reconcile --broker tachibana` 看和立花一致没有）。
   API 不再用 → 在立花网页的「ｅ支店・API 利用設定」改成「利用しない」（§8「最后停止手段」同一个页面）。

## 1.7 现在：Mac 上的模拟操盘（立花开户前；2026-09-25 起）

用和实盘**完全相同的执行器**，只把券商换成模拟账户（PaperBroker，成交规则与回测相同）：每个交易日早上在你的 Mac 上跑一次，
下「明天开盘」的单，第二天早上按真实的开盘价撮合、对账。以后立花开户，只要把 `paper` 换成 `tachibana`。

**一次性安装**（Mac 全天开着即可）：在「终端」里粘贴这一行（可以重复运行，已装好的会更新）：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/shimitsu123/public/claude/rakuten-auto-trading-review-ka7lf0/quant_breakout/scripts/mac_bootstrap.sh)"
```

`scripts/mac_bootstrap.sh` 依次：检查 Xcode Command Line Tools（没有就弹出安装窗口，装完再运行这一行）→ 找 Python ≥ 3.10
（macOS 自带的 3.9 不够；没有就用 Homebrew 装 3.12，连 Homebrew 也没有就提示去 https://brew.sh 或 python.org）
→ 取代码到 `~/qbreak-src` 并切到分支 → `install_launchd_live_u.sh paper`：建虚拟环境 `~/.qbreak/venv` 并装依赖、
注册 LaunchAgent `com.qbreak.liveu.paper`（**周一至五 07:40**，按 Mac 的系统时区，应为日本时间）、环境自检（`doctor`）
→ `liveu.sh trial` 试跑一次（临时目录下载行情、按最新收盘做一次决策，不动正式的模拟账户）。
在云端按同样的方式（curl 下载 → 全新克隆 → 空的行情缓存）整条走过一遍：约 1 分钟，试跑成功（2026-09-25）。

**每天 07:40 自动做的事**（`scripts/liveu.sh run --broker paper`）：
1. `git pull` 等例行任务把当天的日报推上来（2026-10-09 起 Mac 的本机任务 06:45 开始，通常 07:10 前；没做 → 云端后备 07:20；最多等 50 分钟，等不到就用手上最新的并提示）
2. 把云端维护的配置与当天的判断层（`market_regime.json`）、宏观数值（`macro.json`）等拷到 Mac 的数据目录 `~/.qbreak/home`
   （执行器自己的账本、日志也在这里，**不在仓库里** → 以后 `git pull` 永远不会冲突）
3. 执行器：昨天的单按真实开盘价撮合 → 对账 → 核对 → 决策 → 下「下一开盘」的单
4. 与云端模拟盘逐日比较（同一套代码与数据，应当一致）→ 通知中心弹一条（权益、当日 / 累计损益、下一开盘的单数、是否一致）
   → 追加一节到日志 `~/.qbreak/home/out/live_unified_paper_journal.md`
5. 重写「账本 + 日志」页面并用浏览器打开（2026-09-25 加）：总权益、当日 / 累计损益、现金、与云端是否一致、
   **牛熊现在处于哪个阶段**（例：「牛市·稳固：比 250 日均线高 15.3%（20 个交易日前 +18.0%，−2.8 个百分点，向熊靠近）；
   要再跌 15.9% 并连续 5 天收在线下才会转熊」）、持仓、下一开盘的单、最近成交、最近 7 次日志、提醒。
   页面文件 `~/.qbreak/home/out/page_paper.html`；桌面上的 `qbreak模拟操盘.html` 是指向它的链接（安装时建立）。
   页面每 10 分钟自己刷新；超过应有的更新时间（下一个工作日 07:40 + 2 小时）还没更新 → 顶上标红；
   运行没走完（出错、行情取不到）→ 页面顶上标红 + 通知；`git pull` 拉不下来（`~/qbreak-src` 里有本地改动 / 本地提交）→ 页面顶上标红。
   不想每天弹出：`touch ~/.qbreak/home/NO_OPEN`。
   （页面放在数据目录而不是直接写到桌面：macOS 的「桌面」文件夹受隐私保护，定时任务写那里可能被拒绝。）

**开始日**：9/28（与云端模拟盘同一天、同一个决策）；9/28 之前运行只提示「开始日之前不推进」。
晚于 9/28 才安装：模拟账户从云端模拟盘当时的状态开始，之后逐日比较。

**常用**：

```bash
bash ~/qbreak-src/quant_breakout/scripts/liveu.sh --broker paper --status
```

```bash
open ~/.qbreak/home/out/live_unified_paper_journal.md
```

```bash
bash ~/qbreak-src/quant_breakout/scripts/liveu.sh desktop
```

```bash
bash ~/qbreak-src/quant_breakout/scripts/liveu.sh run --broker paper
```

（第三条 = 在桌面放页面的链接并打开页面（安装时已做；第一次可能会问「终端」能否访问桌面文件夹：允许）；
第四条 = 手动跑一次，与定时任务相同；同一天重复跑不会重复下单。卸载：`bash scripts/install_launchd_live_u.sh uninstall`。）

**与云端「不一致」时**：多半是两边取到的数据不同（云端例行任务当天晚了 / 失败 → Mac 用了前一天的判断层；
Yahoo 行情在两次取数之间修正；决算日期缓存不同）。日志里有两边的持仓与现金；想重新对齐就删掉
`~/.qbreak/home/state/live_unified_paper*.json`，下次从云端模拟盘当时的状态重新开始。
通知第一次会以「スクリプトエディタ / Script Editor」的名义弹出：在 系统设置 → 通知 里允许它。

## 1.8 市场仪表盘 + 经济威胁提醒（每 15 分钟；2026-09-26 起，只作展示与提醒，不下单、不改交易）

一次性安装（要先装好 1.7 的模拟操盘，它建了虚拟环境）：

```bash
git -C ~/qbreak-src pull --ff-only
```

```bash
bash ~/qbreak-src/quant_breakout/scripts/install_launchd_news.sh
```

注册 LaunchAgent `com.qbreak.news`（每 15 分钟一次，登录后先跑一次；不 `git pull`，每天 07:40 的模拟操盘会拉）。每次：
1. 取消息：NHK（経済 / 国際 / 主要）、Yahoo!ニュース（経済 / 国際）、日本銀行、財務省、FRB 的新着，Google ニュース的关键词检索（日英各一），
   気象庁的地震情報（震度 5 弱以上）
2. 可信度（0〜100 分）：来源档位（官方 95、大媒体 80、编辑精选 70、其他已知媒体 65、不认识的 50）+ 交叉确认（2 / 3 家以上 +10 / +20）
   − 推测用语（「〜か」「関係者によると」「観測」「見通し」「reportedly」…）15；这是经验打分，不是事实核查
3. 事件归类（标题关键词：日银 / 美联储加息、汇率干预、日元急贬 / 急升、原油冲击、金融系统风险、企业破产、战争升级、关税、半导体规制、
   灾害、疫情、景气转弱、通胀、股市急跌、政局）；只有出现「决定 / 发动 / 升级」一类用语才升到严重度 2〜3
4. 影响链路：事件 → 因子冲击（这类消息常见的幅度：日美 10Y ±0.10 pp、美元日元 ±2%、原油 ±5%、信用利差 +0.20 pp）
   → TOPIX-17 行业（行业 ETF 对各因子的周敏感度，控制大盘、最近 104 周，每周重算）→ 持仓 / 候补队列里属于这些行业的票；
   关税、半导体规制、灾害、疫情用经验规则只标方向
5. 负面事件、严重度 ≥ 2 且可信度 ≥ 70（严重度 3 时 ≥ 55）→ 通知中心提醒一次（同一件事不重复；钥匙串里有 `qbreak-webhook` / `qbreak-smtp`
   （或环境变量 `QBREAK_WEBHOOK` / `QBREAK_SMTP`）的话也发到手机）
6. 重写 `~/.qbreak/home/out/dashboard.html`（账本页面顶上有链接；页面每 5 分钟自动刷新）：现在偏向哪边（牛熊刻度、新仓倍数、仓位构成）、
   市场健康度 10 项（颜色 = 宏观层自己的阈值）、消费 / 零售等新公布的数据（FRED 每小时查一次，新的一期标「新」）、能源消费（每月；云端日报算好的 18 个来源的同比、历史分位与同期一起动的行业，K4 前向观察的状态）、消息与影响链路、业种强弱

马上看一次：

```bash
bash ~/qbreak-src/quant_breakout/scripts/liveu.sh news --open
```

卸载：`bash ~/qbreak-src/quant_breakout/scripts/install_launchd_news.sh uninstall`；日志 `~/.qbreak/home/logs/com.qbreak.news.out|err`。
消息的标题与链接只存在 `~/.qbreak/home/cache/news/`（公开仓库不转载第三方标题）；云端日报的「一眼看懂」只放汇总。

## 1.9 J-Quants 每天的新数据（周一至五 19:30 + 07:05；2026-09-26 起，只作展示 / 研究，不改交易）

キー（Standard 方案）只放钥匙串，**不贴进聊天、不写进文件**。在「终端」里运行这一行，回车后输入キー（屏幕上不显示、不留在历史里）：

```bash
security add-generic-password -s qbreak-jquants -a qbreak -w
```

之后运行下面 1.10 的一条命令就会注册 LaunchAgent `com.qbreak.jquants`（单独装：`bash scripts/install_launchd_jquants.sh`）。

**为什么是这两个时刻**（J-Quants 官方的更新时刻，https://jpx-jquants.com/ja/spec/data-update ，2026-09-26 查，仅对本次检索时点有效）：
株価四本値・日々公表信用残 16:30、空売り残高報告・上場銘柄一覧 17:30、決算短信（速報）18:00 → **19:30** 取当天（留出延迟余量）；
決算短信（確報）24:30、決算発表予定日 10:05（前一营业日的）→ **次日 07:05** 补取与确认（在 07:40 模拟操盘之前）。
已取到的不重取；没取到 / 空的下次自动补；周末、节假日按前一营业日处理。

每次整理出对项目有用的信息（写 `~/.qbreak/home/out/jq_today.json`，市场仪表盘的「J-Quants 每天的新信息」一节显示）：
1. 股票池（日経225 + 扩大池）10 个营业日内要发表决算的票，持仓 / 候补在前；和执行器现在用的 Yahoo 日程**不一致的标 ★**
   （执行器「决算前不买」用的是 Yahoo 日程，对照它有没有漏）
2. 当天开示的会社予想修正：营业利润（银行等用经常利润）相对上一次予想的变化 %
3. 日々公表信用残（注意喚起・規制）、空売り残高報告（≥ 0.5%）、拆股 / 合并（调整系数 ≠ 1）
4. 候补与今天买单的真实一手（收盘价 × 100 股）
5. 上市一览的变化（新上市 / 退市 / 市场区分变更；新上市的票用 `scripts/theme_link_check.py` 做关联对比）
6. 海外投資家（Prime）的周度买卖差额

马上取一次（キー自动从钥匙串读，不回显）：

```bash
bash ~/qbreak-src/quant_breakout/scripts/liveu.sh jq
```

J-Quants 的原始数据只存在 `~/.qbreak/home/cache/jquants/live/`，整理结果也只在这台 Mac 上（個人利用条款：不再分发、公开仓库不入库）。
研究脚本要キー时：`bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python scripts/<研究>.py`（从钥匙串读进那个进程，不回显）。
卸载：`bash ~/qbreak-src/quant_breakout/scripts/install_launchd_jquants.sh uninstall`；日志 `~/.qbreak/home/logs/com.qbreak.jquants.out|err`。

## 1.10 拉代码后一条命令装好 / 更新全部；以后在 Mac 的 Claude 对话里直接做

```bash
git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh
```

`scripts/mac_setup.sh`（可以重复运行；不动账本、不下单、不碰 `ARM` / `HALT`）：① Python 依赖（按 `requirements.lock`；`--upgrade-yfinance` 另把 yfinance 升到最新）→ ② 模拟操盘 `com.qbreak.liveu.paper`
（没装就装；立花本番已装时不动，缺前一晚预检 `com.qbreak.precheck` 就补上）→ ③ 市场仪表盘 + 经济威胁提醒 `com.qbreak.news` → ④ J-Quants 定时取数 `com.qbreak.jquants`
（钥匙串里有 `qbreak-jquants` 才装；只检查有没有，不读出值）→ ⑤ 研究用的第二个克隆 `~/qbreak-dev`（没有就建；没有本地改动就更新）
→ ④b 登录 / 开机后自动启动 `com.qbreak.login`（见 1.11）→ ④c 操作面板 → ④e 09:30 自检 `com.qbreak.watchdog`（两种模式都装；
钥匙串里的 `qbreak-webhook` / `qbreak-heartbeat` 只查有没有）→ ⑤b 打印本地改代码 / 推送的检查命令 → ⑤c 例行任务用的第三个克隆 `~/qbreak-sim`（§1.13）
→ ⑥ 列出已注册的定时任务与页面位置。

以后在 Mac 的 Claude 对话里**直接说要做什么**（「更新一下」「今天怎么样」「持仓最近有决算吗」「研究一下 ××」）：
Claude 自己运行需要的命令并汇报结果（规则见仓库根目录的 `CLAUDE.md`「在用户的 Mac 上」，问法对照见 `HANDOFF.md`「在 Mac 对话里怎么问」）；
研究在 `~/qbreak-dev` 里一口气走完「登记 → 运行 → 记录 → 推送」。
**2026-10-09 起改代码、提交、推送（上传）也在 Mac 本地的 Claude 里做，不需要云端会话**（例行任务也在 Mac 的本机任务里跑、云端同名例行任务是后备，§1.13；Mac 的执行器每天 07:40 照样拉它们推的文件）：

```bash
bash scripts/dev.sh check   # 第一次 / 推不上去时：只读检查（分支与上游、远端、推送权限 --dry-run、git 身份有没有设、Python ≥ 3.10 + pytest、~/qbreak-src 有没有本地改动）
bash scripts/dev.sh test    # 在 ~/qbreak-dev/quant_breakout 跑全部测试（全部通过才 git commit；提交信息不写模型名）
bash scripts/dev.sh push    # 有未提交的改动 → 停下；git pull --rebase（冲突 → 停下、不自动解决）→ 推送 → ~/qbreak-src 快进（有本地改动 / 交易日 07:30〜09:35 JST → 不动）
```

推送要你自己在终端配好 GitHub 登录（`gh auth login` 或 SSH 钥匙）与 git 的 user.name / user.email（公开仓库：用不暴露个人信息的名字与 GitHub 的 noreply 邮箱）；
令牌 / 密码不要贴进聊天。遇到权限确认点「允许」即可；想少问几次，
可以在 Mac 的 Claude Code 里用 `/permissions` 自己把常用的只读命令加进允许列表（这由你决定，Claude 不替你改权限设置）。
实盘相关（`ARM`、删 `HALT`、`--no-arm`、`--resolve`，2026-10-09 起还有撤单 `cancel` / `halt-cancel`、人工代下登记 `adopt`、恢复账本 `restore`、
换 Mac `adopt-host`、临时休市 `closed add|rm`）、改模拟盘规则、密钥，仍然要你在那次对话里明确说。

## 1.11 登录 / 开机后自动启动（LaunchAgent `com.qbreak.login`，2026-09-26 起）

Mac 睡着 / 关着的时候 07:40 的模拟操盘会错过。`scripts/mac_setup.sh` 会注册 `com.qbreak.login`（RunAtLoad：每次登录 / 开机后约 1 分钟跑一次
`scripts/liveu.sh login`，规则在 `qbreak/mac_login.py`）：
1. 市场仪表盘 `com.qbreak.news` 没加载 → 加载（没装 → 安装）
2. 今天是日本交易日、已过 07:40 JST、今天的模拟操盘还没跑成（`~/.qbreak/home/out/live_unified_paper.json` 的日期不是今天）、
   没有别的执行器在跑 → 补跑 `liveu.sh run --broker paper`（同一决策日重复跑不会重复下单）。**装的是立花本番时永远不在登录时补跑**（真钱只按定时任务）
3. 打开账本页面 `page_paper.html` 和市场仪表盘 `dashboard.html`（不想弹出：`touch ~/.qbreak/home/NO_OPEN`）

单独装 / 卸载：`bash ~/qbreak-src/quant_breakout/scripts/install_launchd_login.sh [uninstall]`；日志 `~/.qbreak/home/logs/com.qbreak.login.out|err`。

## 1.12 政策事件反应库的录入（2026-09-27 起；只改仓库里的事件表，不下单）

日银决定、財務省介入、FOMC 转折、关税、半导体规制、消费税等政策事件公布后，在 Mac 对话里让 Claude 录入（在 `~/qbreak-dev` 里，不在 `~/qbreak-src`）：

```
bash scripts/liveu.sh policy add --category BOJ_CHANGE --subtype tighten --date 2026-10-30 --source https://www.boj.or.jp/... --name-ja "利上げ 1.5%" --checked 2026-10-30
```

- `--date` 用主场当地的官方日期（美国主场用美国日期，脚本自动换算 JST）；有官方时刻加 `--time HH:MM`（当地时刻）；日银会合不给时刻 → 类别默认 12:00
- `MOF_FX` 必须写明 `--confirmed-same-day`（当日財務省 / 財務官が公表）或 `--covert --known-on 月次公表日`（覆面介入，只描述）
- `--checked` = 自己在浏览器里核对过来源（写今天；checked_hash = manual）；不写 → 只描述、不进统计，可以之后 `policy check --id <id>`
- 录入后：`git add var/policy_events.csv && git commit -m "政策事件：..." && git pull --rebase && git push`；下一个交易日云端 sim-day 追加前向记录
- 看：`bash scripts/liveu.sh policy list`（最近 90 天）、`policy tocheck`（待核对清单）、日报「政策事件反应库」块、`var/out/policy_forward_review.md`
- 日报里「待分类」= 已过去的日银 / FOMC 日程还没有事件行（无变更也要录：`--category CTRL_BOJ_NOCHG --subtype no_change` / `CTRL_FOMC_OTHER --subtype other`）

## 1.13 例行任务在 Mac 上（Claude 桌面版的本机任务；2026-10-09 起）

用户 2026-10-09「连云端例行任务也搬到 Mac」。云端例行任务不能指派到个人 Mac（官方文档，2026-10-09 检索，仅对本次检索时点有效），
所以改用 **Claude 桌面版的「本机任务」**（Local routine，要 Claude Desktop ≥ 1.1.5368）；**云端同名例行任务是后备**（Mac 当天做过就跳过）。
全部细节与建法：`routines/README.md`；说明书（云端 prompt 的 Mac 版，其余步骤原文照抄）：`routines/sim_daily.md`、`routines/shadow.md`、`routines/quarterly.md`。

| 本机任务 | 时间（JST） | 做什么 | 云端后备 |
|---|---|---|---|
| 模拟盘日报 | 周一至五 06:45 | 读市场风险报告 → `sim-day` → 入库（`sim(mac):`）→ 发布日报 artifact | 07:20 |
| 影子账户判断 | 周一至五 07:45 | 等日报入库 → step → 判断（09:00 之前）→ 入库（`shadow(mac):`）→ 重新发布日报 | 08:05 |
| 顶底择时季度复核 | 1 / 4 / 7 / 10 月 12 日 09:56 | 2〜2m、3、3b 的复核 → 入库（`季度复核(mac)：`） | 12:52 |

- 工作文件夹：例行任务专用的第三个克隆 `~/qbreak-sim`（`mac_setup.sh` 建 / 快进；只有例行任务在这里改 `var/`、提交、推送）。
  `~/qbreak-src` 照旧只 pull（07:40 的执行器），`~/qbreak-dev` 照旧给人改代码。
- 命令：`bash scripts/routines.sh done-today sim|shadow|quarterly`（做过就跳过：0 跳过 / 1 照常做 / 2 拉不下来 → 停下）、
  `run <python 参数…>`（在 `~/qbreak-sim` 里、去掉 `QBREAK_HOME` 跑：这些命令本来就写仓库的 `var/`）、`deps`（按 requirements.lock 装）、
  `push`（`git pull --rebase` → `git push`，失败 2 / 4 / 8 / 16 秒后重试；不 force、不改分支；提交信息带模型名 / 作者不是设好的 git 身份 → 不推）、
  `check`（只读：克隆、推送权限、git 身份、桌面版版本、三个本机任务、钥匙串 qbreak-jquants、pmset 唤醒、最近 5 个工作日每天是 Mac 还是云端做的）。
- 你要做的（一次）：桌面版开机自动打开（登录项）、Settings → This computer → System → **Keep computer awake** 打开、
  终端里 `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`（取代原来的 07:30；`pmset repeat` 只能有一个重复唤醒；立花执行器只要 07:40 之前）、
  然后在 Mac 的 Claude 对话里说「装本机例行任务」（Claude 照 `routines/README.md` 建三个任务、先 Run now 一次，权限选 always allow）。
- 市场风险报告 artifact 的 URL 只写在本机任务的说明里，不入库（公开仓库不写私人链接）。
- 限制：桌面版没开、Mac 睡着 / 合盖 → 不跑；醒来后只补跑最近一次；前一个任务还在跑时另一个可能被跳过 → 云端后备补上。
  两边都没做 → 07:40 的执行器用手上最新的输入继续；09:30 自检会提醒「今天的模拟盘日报没入库（Mac 的本机例行任务没跑？桌面版开着吗？）」。
- 「例行任务今天跑了吗」→ `bash scripts/routines.sh check`；桌面版 Code → Routines → 点任务 → Review history。

## 1.14 换 Mac（立花本番搬到另一台 Mac；2026-10-09 补，缺口盘点 OPS-04）

为什么要按步骤：两台 Mac 同时跑同一个立花账户会**重复下单**（立花那边挡不住：每次调用都会自动重新登录、把对方的会话踢掉；运行锁只管同一台 Mac）。
所以立花本番的账本记着「属于哪台 Mac」（硬件 UUID 的摘要，不存原文、不存主机名）：账本拷到另一台 Mac 上运行 → 执行器停下
「这个账本是另一台 Mac 的」，直到你在新 Mac 上明确说「换 Mac，账本归这台」。

1. **旧 Mac**：说「停」（HALT）；还挂着的单先撤（「撤单」）→ `bash scripts/install_launchd_live_u.sh uninstall`（立花的 07:40 / 08:35 / 09:05 / 09:20 与前一晚预检一起卸）
   → 其余定时任务也卸掉（`bash scripts/install_launchd_{watchdog,panel,login,news,jquants}.sh uninstall`）或干脆把旧 Mac 关掉；
   Claude 桌面版里旧 Mac 的本机例行任务（§1.13）也停掉 / 删掉 → `launchctl list | grep qbreak` 确认什么都没了。之后旧 Mac 不要再开着跑执行器。
2. **拷数据**（AirDrop / 外接盘 / 移行アシスタント；不经云端、不进仓库、不贴进聊天）：
   - 数据目录 `~/.qbreak/home`（账本与 `state/backup/`、手动指令、ARM / HALT、`tachibana_spec.json`、日志）—— HALT 跟着过去，新 Mac 一装好也不会发单；
   - 私钥 `~/.qbreak/e_api_private_key.pem`（在数据目录的**上一层**；デモ的 `e_api_private_key_demo.pem` 也一样）→ 新 Mac 上
     `chmod 700 ~/.qbreak` 与 `chmod 600 ~/.qbreak/e_api_private_key.pem`（别的用户可读时程序会拒绝启动）；
   - 钥匙串不一定跟着走（移行アシスタント / iCloud 钥匙串以外）：在新 Mac 的终端**你自己**重新存（回车后输入，不显示）——
     `qbreak-tachibana-authid` / `qbreak-tachibana-2nd`（デモ的 `-demo`，§3）、邮件 `bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup`、`qbreak-webhook` / `qbreak-heartbeat` / `qbreak-jquants`；
   - 旧 Mac 要卖掉 / 送人：先把上面这些从旧 Mac 删掉（数据目录、私钥、钥匙串里 `qbreak-` 开头的条目）。
3. **新 Mac**：§1.7 的一行安装 → `git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh`
   → 时区选东京、`sudo pmset repeat wakeorpoweron MTWRF 06:40:00`、Claude 桌面版开机自动打开 + 在对话里说「装本机例行任务」（§1.13）；
   手机操作要在新 Mac 上重新打开（`mac_setup.sh --phone <机器名>`；新 Mac 的 Tailscale 机器名会写进公开的证书日志 → 名字要你确认）；
   在「ｅ支店・API 利用設定」登记过固定 IP、而新 Mac 的出口 IP 不同 → 先在那里改成新的 IP。
4. 新 Mac 的 Claude 对话里明确说「**换 Mac，账本归这台**」→ `bash scripts/liveu.sh adopt-host --broker tachibana`
   （先备份账本；只改账本里的机器标识、记一条事件；不连立花、不下单）。
5. `bash scripts/liveu.sh probe`（本番只读）→ `bash scripts/liveu.sh reconcile --broker tachibana`（账本和立花一致）
   → `bash scripts/install_launchd_live_u.sh tachibana` → `bash scripts/liveu.sh gate`
   （上线之后模拟操盘不再跑：门槛 ① 停在模拟操盘最后一次运行时的结果，不会因为之后不再比较而变「过期 ★」；看其余几项）→ `bash scripts/liveu.sh notify-test`。
6. HALT 还在：你明确说「恢复下单，删除 HALT」才删（ARM 也是跟着数据目录拷过来的；要不要留着同样由你说）。

## 2. 开户与 API 设定（v4r10，2026-09-25 核对）

> 2026-10-04 再核对官方（https://www.e-shiten.jp/api/ 、/api/20260728.html，仅对该时点有效）：v4r10 是现行版本（2026-08-29 发布；v4r9 已于 2026-09-27 废止），适配器不用改。

1. 网上填表 → 邮寄 / 自行打印开户文件 → 寄回 2 种身份证明与マイナンバー → 审查 → ID / 密码以簡易書留寄到。
   账户类型选 **特定口座（源泉徴収あり）**：执行器默认只在特定口座交易（按口座的默认课税区分下单）。
   NISA（2026-10-09 统一说法）：立花的 NISA 买单只能「指値・無条件・当日中」（不能寄付 / 成行 / 逆指値；卖单可以成行），
   所以执行器现在的寄付指値买不能放 NISA；〔72〕① N2（核心 ETF 的买入放 NISA）是可选项 —— 要先另做执行器工程（按单指定课税区分、额度、
   两个区分分别对账），效果要按当日限价重新估算，是否采用由你决定（HANDOFF 待办〔72〕）。NISA 里的同一只票不要和执行器管的票重叠
   （合计股数会让持仓核对停下）。来源：立花 Q&A https://www.e-shiten.jp/QA/answer12.html（2026-10-09 检索，仅对本次检索时点有效）
2. 标准 Web 首次登录（API 的电话认证已随 v4r8 废止（2026-06-27）停用；标准 Web 首次登录还要不要电话认证 —— 待开户后确认）
   → **注册パスキー**（官方列的设备：Windows 11、iOS / iPadOS 17 以上、Android 10 以上；macOS 属「動作未確認」→ 用 iPhone；能登记备用设备就登记一台）。
   **2026-12-12（手机网站）/ 12-18（标准 Web）起网页的交易与出金必须用パスキー登录**；网页上的撤单、§8 的「最后停止手段」都要登录网页
   → パスキー设备丢了就两样都做不了（立花 https://www.e-shiten.jp/important_info/20260708.html ，2026-10-09 检索，仅对本次检索时点有效）。
   立花没有原生 App：手机上用手机专用网站 https://kabuka.e-shiten.jp/mfds_smp.php
3. お客様情報 → 設定情報「**ｅ支店・API 利用設定**」→「利用する」→ 下载**认证 ID**（`e_api_authid.txt`）
4. **公開キー登録**：「登録（自動）」会当场生成密钥，**私钥只能下载这一次**；或「手動」上传你自己生成的 RSA 2048/4096 公钥（推荐：私钥从不离开 Mac）
5. 可选：登记固定 IP（官方「強く推奨」；家里 IP 会变就先别登）。API 只支持 IPv4、TLS 1.2/1.3
6. 有未读的交付书面时 API 不发放虚拟 URL → 收到通知就在 PC 网页上读完（2026-10-09 起前一晚预检会提前提醒：更新预定日在 5 个交易日以内每晚提醒，
   当晚登录不了就通知，§1.6「运行保障」）
7. デモ環境：在 demo.e-shiten.jp 另外取得デモ用认证 ID 和密钥（デモ不需要パスキー）

API 登录从 2026-06-27 起**不再需要电话认证**（只用公開鍵方式），程序可以每天自动登录。登录通知邮件（ログインメール，官方关不掉）：
官方页面只列了标准 Web 和手机网站，API 登录发不发 —— 待开户后第一次 probe 时确认；执行器按「会发」设计（前一晚预检一天只登一次）。
会话到 03:30 失效，03:30～05:30 不能登录；当日单 0:00～15:30，15:30～16:30 不受理，16:30 起受理翌営業日的单。
仕様書全部公开：https://www.e-shiten.jp/e_api/mfds_json_api_menu.html

---

## 3. 凭证（v4r10）：认证 ID + RSA 私钥 + 第二暗証，都不进仓库

v4r10 登录只送**认证 ID**；应答里的虚拟 URL 用你登记的公钥加密，程序用**私钥**解密（RSA-OAEP / SHA-256）。
下单还必须带**第二暗証番号**。程序只从下面这些地方读，代码、配置、日志里都不出现：

```bash
mkdir -p ~/.qbreak && chmod 700 ~/.qbreak
# 私钥：「公開キー登録（自動）」时当场下载的 e_api_private_key.pem（只能下载这一次）放到这里
mv ~/Downloads/e_api_private_key.pem ~/.qbreak/e_api_private_key.pem
chmod 600 ~/.qbreak/e_api_private_key.pem          # 别的用户可读时程序会拒绝启动

# 认证 ID（e_api_authid.txt 的内容）与第二暗証番号放钥匙串（-w 后不写值 → 交互输入，不留在 shell 历史）
security add-generic-password -s qbreak-tachibana-authid -a qbreak -w
security add-generic-password -s qbreak-tachibana-2nd -a qbreak -w
```

- 想自己生成密钥（私钥从不离开 Mac）：用「公開キー登録（手動）」上传公钥，格式按官方 `authidmanual.pdf`；
  私钥 PEM（PKCS#8 或 PKCS#1 都能读）放在同一路径。
- **デモ環境是另一套**认证 ID 与密钥：`~/.qbreak/e_api_private_key_demo.pem`，钥匙串 `qbreak-tachibana-authid-demo` /
  `qbreak-tachibana-2nd-demo`（或环境变量 `TACHIBANA_AUTH_ID_DEMO` 等）。
- 也可以用环境变量：`TACHIBANA_AUTH_ID` / `TACHIBANA_AUTH_ID_FILE`（指向 e_api_authid.txt）/ `TACHIBANA_PRIVATE_KEY` / `TACHIBANA_SECOND_PASSWORD`。
- `python3 run.py doctor` 只显示「是否已设置 / 私钥是否存在」，不打印任何值。
- **换密钥 / 改第二暗証**（2026-10-09 起写明）：在立花网站改了第二暗証番号之后，在你自己的终端覆盖钥匙串里的旧值
  （`-U` = 覆盖；回车后输入，不显示、不要贴进聊天）：
  `security add-generic-password -U -s qbreak-tachibana-2nd -a qbreak -w`；认证 ID 换了同样用 `-s qbreak-tachibana-authid`；
  私钥换了就把新的 `e_api_private_key.pem` 放回原路径并 `chmod 600`。改完运行 `bash scripts/liveu.sh gate`（⑥「钥匙串能读出」那一项
  用和定时任务相同的读法试读一次，只报能不能读出）。第二暗証错了时，同一次运行里第一笔单被拒之后，后面的单都不再发（不连着错）。
- 钥匙串读不出时提示分两种：「没有这个条目」→ 照上面存；「钥匙串锁着 / 不允许交互」→ 不用重新存，登录 Mac、解锁登录钥匙串，
  「钥匙串访问」里登录钥匙串不要设「睡眠时锁定 / 闲置后锁定」。

---

## 4. 校验 API 仕様（最关键的一步）

`qbreak/brokers/tachibana.py` 里的 `TachibanaSpec` 已按 2026-09-25 的公开仕様書（v4r10）逐项核对，
但**还没在真实账户上跑过**。API 版本（URL 里的 `e_api_vXrY`）和项目名会改版（登录应答会告知下一次发布日，日志里有提示）。

```bash
bash scripts/liveu.sh probe --demo --dump-spec
```

这条命令**只读**：登录（认证 ID + 私钥解密虚拟 URL）→ 取价（7203 / 1329 / 1655）→ 持仓 → 余力 → 注文一覧，**绝不发单**。
有失败项就打开 `~/.qbreak/home/tachibana_spec.json`，对着官方仕様書**只写要改的键**（2026-10-09 起 `--dump-spec` 只导出和代码默认不同的键，
全部默认值另写在同目录的 `tachibana_spec_defaults.json`，只供参考、程序不读）；程序会自动加载，**其余代码一行都不用动**。
只写要改的键：代码以后升级默认值（例如 API 新版本的 base URL）时不会被这个文件冻住；文件里的 `base_live` / `base_demo` 还指向旧版本时，
日志与 `bash scripts/liveu.sh gate`（⑥「仕様覆盖文件」）会标 ★。注文状态的终态码（`status_*`）与错误码对照表（`err_*`）也在这里改。

全部 `[OK]` 之后，再跑一次本番環境（去掉 `--demo`）确认。

（立花的命令都经 `scripts/liveu.sh`：它把数据目录设成 `~/.qbreak/home`。直接跑 `run.py` 而数据目录在仓库里（没设 `QBREAK_HOME`）时，`live-u` / `manual --broker tachibana` 与 `tachibana-probe` 会拒绝运行、不写任何文件——这是公开仓库，真实账户的账本与检查结果不能进仓库的 `var/`；`.gitignore` 也排除了这些文件。）

---

## 5. 常驻自启

```bash
# 先用 paper 演练几天，确认无误后把 QBREAK_BROKER 改成 tachibana
export QBREAK_BROKER=paper
bash scripts/install_launchd.sh
```

装好之后：

```bash
launchctl list | grep qbreak                 # 第一列是 PID，说明在跑
tail -f var/logs/qbreak.log                  # 实时日志
cat var/heartbeat.json                       # 心跳（ts / session / pid）
launchctl unload -w ~/Library/LaunchAgents/com.qbreak.daemon.plist   # 停止
```

**让 Mac 在开市前自动唤醒**（旧方案的时刻；现行一个账户方案用 `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`，§1.13 —— `pmset repeat` 只能有一个，别再设下面这个）：

```bash
sudo pmset repeat wakeorpoweron MTWRF 08:40:00
```

---

## 6. 守护进程盘中到底在做什么

```
休市           → 睡到下一个开市时刻（不空转、不浪费 API 配额）
08:50          → 开市前对账：持仓、余力、逆指値是否都还在
09:00–11:30    → 每 60 秒：批量取现在值 → 更新峰值 → 检查止损/跟踪止损/止盈 → 维护逆指値
11:30–12:30    → 午休，低频心跳
12:30–15:30    → 同前場
15:25–15:30    → 收盘集合竞价，最后一次风控检查
15:40（立花 16:45）→ 日线信号 → 次日**寄付**单 → 日终对账 → 存明日的熔断基准
                 （立花 15:30～16:30 不受理注文；会话 03:30 失效，第二天第一次请求时自动重新登录）
```

**为什么盘中不重算信号**：当前策略的信号定义在收盘价上，回测也是这么验证的。
盘中重算 MACD 金叉会得到一堆盘中出现、收盘消失的假信号，而且**无法用现有回测验证**。
想做真正的日内策略是另一个项目（分钟级数据源 + 日内回测框架 + 全新信号定义）。

---

## 7. 上线清单

- [ ] 一个账户方案（现行）：先 §1.7 的 Mac 模拟操盘，开户后按 §1.6 的上线步骤（`live-u`）；ARM / HALT 在 `~/.qbreak/home/`；
      下面几项里「守护进程 / --protective-stop / 16:45 / var/ARM」是旧的分市场方案
- [ ] 一个账户方案：`bash scripts/liveu.sh gate` 全部 OK（上线门槛 ①〜④、本番只读检查、钥匙串、私钥权限、定时任务、自动唤醒；只读）
- [ ] `run.py doctor` 全绿
- [ ] `tachibana-probe --demo` 全 `[OK]`，且已对着官方仕様書改过 `tachibana_spec.json`
- [ ] `tachibana-probe`（本番，不加 `--demo`）全 `[OK]`，而且在交易时间（交易日 09:00〜15:30）做过一次（盘外只能确认前日終値，
      现价的字段名确认不了；`liveu.sh gate` 的 ⑤ 会提醒）
- [ ] `--broker paper` 演练过至少一个完整交易日
- [ ] （只有旧的分市场方案）`--protective-stop` 打开。**现行执行器不挂逆指値**：离场只在每个交易日 07:40 的决策里下寄付卖单（盘中不盯价）；
      Mac 那天没跑就不卖 → 靠 09:30 自检 + 外部心跳提醒你（下面两项）
- [ ] 单笔上限：默认 = 资金 ×1.1（核心 ETF 一笔可到 100%）；前两周可 `--position-pct 0.05`（覆盖同档仓位）
- [ ] 立花：守护进程默认 16:45 下次日单（15:30～16:30 不受理）；目前一个进程只管一个分仓，两个分仓合并到一个会话之前不要同时跑两个守护进程（新登录会踢掉旧会话）
- [ ] 手机通知：邮件 → 你自己在终端 `bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup`（Gmail 应用专用密码，输入时不显示；先发一封测试邮件，发成了才存进钥匙串 `qbreak-smtp`）；
      或 webhook 地址存钥匙串 `security add-generic-password -s qbreak-webhook -a qbreak -w`（回车后输入；Discord / Slack / ntfy；
      定时任务读不到 `export` 的环境变量）→ `bash scripts/liveu.sh notify-test` 收到
- [ ] 外部心跳：healthchecks.io 之类建「周一至五 09:30 JST、宽限 30 分钟」的检查，ping 地址存钥匙串 `qbreak-heartbeat`；
      09:30 自检 `com.qbreak.watchdog` 已装（`bash scripts/mac_setup.sh`）；`bash scripts/liveu.sh gate` 的 ⑧ 三项 OK
- [ ] 立花的命令都经 `bash scripts/liveu.sh`（数据目录 `~/.qbreak/home`；数据目录在仓库里时立花的入口会拒绝运行）
- [ ] 账户是**特定口座（源泉徴収あり）**：执行器只按口座的默认区分下单；NISA（〔72〕① N2）是可选项，要先另做执行器工程、由你决定（§2 第 1 步）；
      NISA 里的同一只票不要和执行器管的票（股票池 + 核心 ETF 1545 / 1482）重叠
- [ ] 立花的パスキー注册好（最好有备用设备；2026-12-12 / 12-18 起网页交易与撤单要它，§2 第 2 步）
- [ ] 读过 §1.6「上线头 5 个交易日的值守清单」「退出实盘 / 回到模拟」、§1.14「换 Mac」与 §8「最后停止手段」

**ARM（人工解锁）**：不解锁就不会发任何单（一个账户方案：数据目录 `~/.qbreak/home/`；只在你明确说之后）。
文件内容必须是 `ARMED` 才算解锁（适配器、操作面板、gate 用同一个判断；文件在但内容不对 → 面板与 gate 显示「内容不是 ARMED」，单会被挡）。
ARM 不会自动清空（每天全自动本来就要它一直在）：要停用 = 删掉它或建 HALT。本番和デモ看同一个 ARM 文件：デモ的发单检查
（`probe --demo --order-test`）自己不看 ARM；执行器的デモ账本（`--broker tachibana --demo`）照旧要 ARM。

```bash
echo ARMED > ~/.qbreak/home/ARM      # 解锁
```

```bash
rm ~/.qbreak/home/ARM                # 锁上
```

**紧急停止**（Python 侧立即拒绝一切下单）：

```bash
echo "手工停止" > ~/.qbreak/home/HALT
```

（以前这里写的 `var/ARM` / `var/HALT` 是旧的分市场方案：仓库是公开的，立花的入口在数据目录指向仓库的 `var/` 时会拒绝运行，`var/ARM` 已经没有用。）

---

## 8. 休眠、断网、崩溃

| 情况 | 会发生什么 | 兜底 |
|---|---|---|
| 一个账户的执行器（现行）：Mac 睡着 / 关机错过 07:40 / 09:05 | 08:35 / 09:20 重试；工作日 06:40 自动唤醒（pmset；2026-10-09 起，§1.13）；运行中 `caffeinate`，早上跑完醒到 09:35 | 都错过 → 那天没下单（第二天早上照常对账、决策；不补「昨天的单」） |
| 一个账户的执行器：几个任务同时启动 | 运行锁（同一份账本同时只有一个进程） | 等不到锁就不运行并通知（状态不动） |
| 一个账户的执行器：人不在 Mac 旁边要停 | 云端对话里说「停」→ `var/HALT_REMOTE` → 下一次运行建 HALT | 已发出的单不撤（手机面板「今天的单」的「撤单」，或立花手机网站 https://kabuka.e-shiten.jp/mfds_smp.php） |
| 一个账户的执行器：Mac 失控 / 联系不上，HALT 传不过去（2026-10-09 补） | —— | **最后停止手段**（本节末尾）：你在立花网页把「ｅ支店・API 利用設定」改成「無効化」→ API 马上失效；挂着的单在网页上撤 |
| 一个账户的执行器：立花 API / Mac 出故障那天（2026-10-09 补） | 面板 / 手机「今天的单」列出今天应下的单（票、买卖、股数、下法、限价、状态）| ① 只照这张表里状态是「被挡 / 不下 / 没下」的行在立花网站下单（「已下单 / 已成交 / 部分成交」的已经在交易所，别再下；标题写着「上一次决策的单（…不是今天）」= 今天早上的运行还没跑，那张表不是今天要下的）（API 故障时官方也要求在标准 Web 上操作）② 第二天早上 07:40 之前在 Mac 对话里说一声 → `bash scripts/liveu.sh adopt --broker tachibana <代码> <BUY\|SELL> <股数> <均价> [--date …]`（实际成交数与均价看立花「約定照会」；先备份账本）③ `bash scripts/liveu.sh reconcile --broker tachibana` 看账本与立花一致 → 执行器照常（不登记的话第二天的持仓核对会挡住全部下单） |
| 一个账户的执行器：整个早上都没跑 / 跑了没下成单（2026-10-09 补） | 09:30 自检没通过 → 手机 + Mac 通知 + 外部心跳报失败；Mac 关机 / 睡着 / 断网（自检也没跑）→ 心跳服务那边没收到 ping，推送到手机 | 当天没下的单不补（第二天早上照常对账、决策）；状态不明的单在立花注文一覧核对后登记 |
| 一个账户的执行器：盘中面板叫的执行器一直失败 | 等待加倍（最多 15 分钟），同一天连续 3 次 → 当天暂停自动叫；通知同一天同一段文字只发一次 | 修好后写新的手动指令，或第二天自动恢复 |
| （旧方案）守护进程崩溃 | launchd 30 秒内拉起，从磁盘恢复状态并对账 | 旧方案的逆指値挂在券商侧（**现行执行器不挂逆指値**） |
| （旧方案）Mac 空闲休眠 | `caffeinate -i` 阻止；合盖仍会睡 | 旧方案靠逆指値（`--protective-stop`）；现行执行器见本表前几行 |
| （旧方案）断网 | 取价失败，连续 5 轮后告警；**不会盲目卖出** | 旧方案靠逆指値 |
| （旧方案）API 报错 | 本轮捕获并记日志，下一轮继续；不会让守护进程死掉 | 心跳文件可判断存活 |

（旧方案的一句话：「程序是"更聪明的手"，逆指値是"永远在岗的保险"」。**现行一个账户的执行器不挂逆指値**：券商那边没有任何保护单，
离场只在每个交易日 07:40 的决策里下寄付卖单；Mac 那天没跑 → 那天不卖，靠 09:30 自检 + 外部心跳提醒你，再由你决定（手动卖 / 立花网站）。
要不要另挂灾难用的逆指値属于交易规则，没有研究过、现在不做。）

### 最后停止手段：在立花网页把 API 关掉（2026-10-09 补；缺口盘点 C-05）

HALT、手机面板的 HALT、云端对话的远程停止，都要靠 Mac 上的执行器自己去读。Mac 失控（一直在发不该发的单）、联系不上 Mac、
或者 Claude / GitHub / Tailscale 都不通时，用立花那一侧的开关（**你自己在网页上做**；Claude 不登录、不操作立花网站）：

1. 用电脑或 iPhone 的浏览器登录立花的标准 Web（PC 版网站；手机专用网站上有没有这个设定没确认）→ **お客様情報 → 設定情報 → ｅ支店・API 利用設定 →「無効化」**
   （或把利用有無改成「利用しない」）：API 的虚拟 URL 马上失效，执行器再也发不了单、也查不了。
2. 已经发出、还挂着的单不会因此撤掉 → 在网站的注文一覧里撤（标准 Web 或手机网站 https://kabuka.e-shiten.jp/mfds_smp.php；API 关了以后面板的「撤单」也用不了）。
3. 恢复要在利用設定里重新设置（可能要重新登记公钥 / 下载认证 ID —— 以开户后的实际画面为准）→ `bash scripts/liveu.sh probe` → `reconcile` → 你明确说才恢复下单。
4. 怀疑认证 ID / 私钥泄露时也用这个办法，然后重新登记公钥（§2 第 4 步）。

2026-12-12（手机网站）/ 12-18（标准 Web）起登录网页做交易要パスキー（§2 第 2 步）。
来源：立花 Q&A https://www.e-shiten.jp/QA/answer14.html（虚拟 URL 失效的条件：無効化 / 利用しない / ログアウト；2026-10-09 检索，仅对本次检索时点有效；菜单名以开户后的实际画面为准）。

---

## 9. 关于「一天能交易几次」

立花ｅ支店官方页面（2026-09-26 核对，仅对该时点有效）：
- **每天的下单 / 成交次数没有上限**（「取引のルール」与 API 仕様書里都没有次数限制；API 只要求请求一个接一个发，访问太频繁时
  某些网络服务商会卡住 —— 官方 Q&A）。一笔的上限：株数不限、金额 5 億円（「現物取引」页）；超过上市股数 5% / 30% 的单按
  交易所的「異常数量注文」处理（「異常数量注文」の防止対応について）。
- 現物取引下，**同一只股票**、同一营业日、同一笔资金只能做「买→卖」**1 个往复**；
  之后用同一笔钱再买同一只就是**差金決済**（法令禁止），会被券商拒单（「差金決済取引・日計り取引」页的例 1 / 例 2）。
  **不同股票不受此限**（「同一受渡日における同一資金での別銘柄への乗換売買」可能）。
- 单元未满股（端株）只能卖（端株売却 / 買取請求），**不能买** → 个股只能按 100 股一手买（「単元未満株式の取扱い」页）。
出处：https://www.e-shiten.jp/TorihikiRule/rule/order.html 、…/sakin_hibakari.html 、…/oddlot.html 、…/quantity.html 、https://www.e-shiten.jp/QA/answer14.html
- **盘中不要频繁取价 / 轮询**（官方 2026-03-10「APIご利用に関するお願い」，2026-10-04 查看，仅对该时点有效）：08:00〜15:30 是向交易所收发注文的时段，请避免大量频繁的取价（CLMMfdsGetMarketPrice）与频繁的照会轮询；负荷过大时可能被停用 API（访问次数不公开）；价格历史在 18:00〜翌 03:30 更新、マスタ（銘柄マスタ等）在 05:30〜08:00 取最好。现在的执行器每天只在 07:40 / 09:05 各运行一次：07:40 的寄付单发完就走（不查约定），09:05 的补单每笔每秒查一次约定、最多 20 秒（`confirm_timeout_s`，一天最多几十次照会）—— 量很小；以后若要盘中实时看价，用 EVENT I/F（WebSocket 推送）而不是轮询。
  出处：https://www.e-shiten.jp/api/20260310.html

代码里对应 `DaemonConfig.max_round_trips_per_day = 1`，程序自己会先拦一道，
不会等到被券商拒单才发现。

---

## 10. 常见问题

| 现象 | 处理 |
|---|---|
| `launchctl list` 里没有 qbreak | 现行：`bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh`（可以重复运行）；日志在 `~/.qbreak/home/logs/com.qbreak.*.err`（旧的分市场守护进程才是 `var/logs/daemon.err`）；系统更新后虚拟环境坏了 → 登录时会通知「Python 环境坏了」，同样重跑 mac_setup.sh |
| 「这个账本是另一台 Mac 的」 | §1.14「换 Mac」：旧 Mac 先 HALT 并卸载立花的任务 → 在新 Mac 的对话里明确说「换 Mac，账本归这台」→ `bash scripts/liveu.sh adopt-host --broker tachibana` |
| 「账本读不了（已改名为 … .corrupt…）：不新开账本」 | `bash scripts/liveu.sh restore --broker tachibana --list`（只读）→ 在 Mac 对话里说「恢复账本 <备份文件名>」→ `restore --broker tachibana <备份文件名>`（先备份现在的账本） |
| 「新代码的冒烟测试没过」 | 这次只对账 / 决策、单都不下；原因看 `~/.qbreak/home/logs/smoke_test.log` → 在 `~/qbreak-dev` 修好、测试全过再推（下一次运行用新代码再测一次） |
| 「异常熔断」 | 正常运行不会出现：先说「停」，在 Mac 对话里问原因（`bash scripts/liveu.sh --broker tachibana --status`、日志） |
| 「早上错过寄付 → 开盘后当日限价卖」 | 2026-10-09 你同意的执行补救（§1.6「运行保障」）：卖单改当日限价、买单今天不下，记入与模型的差异 |
| 「交付書面未読」 | 在电脑上登录 e支店网站读完新书面 → `bash scripts/liveu.sh probe`（只读）确认能登录 |
| 一直 `[NG] 登录` | 「ｅ支店・API 利用設定」没设为利用する / 公钥未登记 / 本番与デモ的认证 ID·密钥用反 / 交付書面未读 / 03:30～05:30 维护 / Mac 的时间差 30 秒以上（p_errno=8：系统设置 → 通用 → 日期与时间 →「自动设置」）/ 只能用 IPv4（10005：在 `~/.qbreak/home/tachibana_spec.json` 写 `"force_ipv4": true`；定时任务读不到 `~/.zshrc`）/ パスキー被解除 / API 被停用或版本过期；错误信息里认得出的代码会直接附上原因与修法（`TachibanaSpec` 的错误码对照表）；仕様改版时只把要改的键写进 `~/.qbreak/home/tachibana_spec.json` |
| 「虚拟 URL 解密失败」 | 私钥与登记的公钥不是一对（重新登记公钥，或换回当时下载的私钥） |
| 日志里全是「休市」 | 正常，今天是周末或祝日。`python3 -c "from qbreak.calendar_jp import session_of; print(session_of())"` 可确认 |
| 一直「未 ARM」 | 一个账户方案：`echo ARMED > ~/.qbreak/home/ARM`（只在你明确说之后；旧方案的 `var/ARM` 已经没有用） |
| 想临时停掉但不卸载 | `echo x > ~/.qbreak/home/HALT`（定时任务照常跑，但不发单；解除只在 Mac 上、你明确说） |
