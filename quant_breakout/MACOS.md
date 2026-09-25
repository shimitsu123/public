# macOS 全自动运行指南（立花証券 e支店 API）

> **2026-09-25 深夜更新**：用户改用**立花 e支店**（不做美股个股 → 楽天的美元 / 换汇逻辑用不到；立花 API 能在 Mac 上无人值守下单）。
> 模拟盘已按立花個別コース计费（9/28 起）。**一个账户方案（S0C2）的实盘执行器 `run.py live-u` 已完成，并用模拟账户演练过（见 §1.6）**。
> **现在（立花还没开户）：先在 Mac 上做模拟操盘 —— 见 §1.7，一条命令装好，每个交易日早上自动跑、发通知、与云端模拟盘逐日比较。**
> §5〜§6 的分市场守护进程是旧的「每个市场一个账户」方案，一个账户模式下会拒绝运行，只作参考。

> 面向：Mac + 不装 Excel + 想开机自启、全天常驻、自动买卖。
> 结论先行：**楽天走不通**（RSS 是 Windows 专用 Excel 插件），换 **立花証券 e支店 API** 是
> macOS 上唯一干净的方案（Apple Silicon 的 Mac mini 也可以：API 是纯 HTTP，不依赖操作系统）。
> 开户要邮寄文件（2026-05 起官方公告「通常よりもお時間」），等待期间用 `--broker paper` 把整套流程完整演练一遍。
> **ｅ支店不做美股**：美股指数仓位改用东证上市的 `1655.T`（日元），同一个账户里交易。

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
| 07:40 | `live-u --broker tachibana` | ① 对账：昨天下的单向立花查实际成交（股数 / 均价）记进状态；卖单没成交（ストップ安等）→ 仍是待卖，今天再下；买单没成交 → 作废（与回测「信号只在次日开盘有效」相同）<br>② 核对：券商持仓 = 状态持仓（不一致 → 今天不下单、报警）；现金以买付可能額为准（税、实际手续费、分红入账在这里对齐）<br>③ 决策：与模拟盘同一段代码<br>④ 下单：卖单 寄付成行；买单在开盘前余力内下 寄付指値（个股 = 信号日收盘 ×1.03，1655 = 收盘 ×1.02），放不下的留到开盘后 |
| 09:05 | `live-u --broker tachibana --phase open` | 留下的买单：按始値做同样的跳空（≤ 信号日收盘 +3%）与名额检查，按模型的规则（开盘价 + 滑点）减股，下当日限り指値（占用的余力放不下时把限价降到余力能承受的最高呼値，仍 ≥ 始値） |

**为什么分两段**：券商受理买单时就按「指値 × 股数」占用余力，开盘前还没卖出的 1655 / 个股的钱不算余力。满仓（个股 + 1655）时的新个股买单
几乎都要等开盘卖出 1655 → 在开盘后（盘中）成交，价格 ≠ 开盘价 —— 这是实盘相对模拟盘最主要的差异（历史日线模拟不出盘中价格路径）。
1655 的买单：开盘前放得下的部分先下寄付（按开盘价成交，与模型相同），只有余数留到开盘后（多一笔手续费，通常 77 円）。

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
时间窗口（寄付单在成交日 08:55 前；开盘后补单 09:00〜15:25）/ 行情没更新到应有的交易日 / 持仓与券商不一致 / 有状态不明的单。
发单前先把「发送中」写进账本再发；网络错误（可能已被受理）的单**绝不自动重发**，第二天早上执行器会停下，等你在立花网页的注文一覧确认后登记：

```bash
python3 run.py live-u --broker tachibana --status                                   # 账本：持仓、今天的单、最近事件（不连券商）
python3 run.py live-u --broker tachibana --resolve U2026-10-01-BUY-7203.T --filled 100 --px 3001   # 没成交填 --filled 0
```

**上线步骤（立花开户之后）**

立花的デモ環境（官方 https://www.e-shiten.jp/Service/demo.html ，2026-09-25 核对，仅对该时点有效）：**要先开 e支店账户**才能用；
登录 8:30～27:00（含周末）；约定时间 9:00～11:30 / 12:30～15:00 / 15:10～27:00；**价格不是真的**（指値按指値成交、成行一律 100 円成交）；
当天的注文与约定**第二天重置**。所以デモ只能检查 API 的字段与流程，**不能做多日演练**（多日演练就是 §1.7 的 Mac 模拟操盘）。

1. `python3 run.py tachibana-probe --demo`（只读：登录、取价、持仓、余力、注文一覧）全 `[OK]`
2. デモ一天的发单检查（8:30 以后）：`python3 run.py tachibana-probe --demo --order-test`
   —— 当日指値买 1655 一单元 → 打印約定照会应答的字段名 → 余力与持仓的变化 → 寄付卖单 → 按注文番号撤单。要确认的三点
   （按公开仕様書写的，没在真实服务器上跑过）：约定明细的字段（`sYakuzyouSuryou` / `sYakuzyouPrice` / `aYakuzyouSikkouList`，
   不对就改 `var/tachibana_spec.json`）；买付可能額在成交后怎么变；寄付单能否按注文番号撤掉
3. `python3 run.py live-u --broker tachibana --dry-run --no-clock`（本番：登录、读持仓与余力、打印会下的单，不发）
4. 本番：入金 → `bash scripts/install_launchd_live_u.sh tachibana`（07:40 早上的单 + 09:05 开盘后补单）→ `echo ARMED > ~/.qbreak/home/ARM`
   （Mac 上执行器的数据目录是 `~/.qbreak/home`，ARM / HALT 都放这里）
5. 本番的「开盘前买付可能額」（是否含未交割的卖出所得、开盘卖出成交后是否即时反映）デモ验证不了（假价格、每天重置）：
   头几天每天看 `bash scripts/liveu.sh --broker tachibana --status` 与日志；执行器每天早上都会核对持仓与现金，不一致就停下
6. 第一天：执行器从最新收盘的决策开始，现金按券商余力；同一账户里请不要人工买卖执行器管的票（股票池 + 1655），否则持仓核对会停下

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
1. `git pull` 等云端例行任务把当天的数据推上来（06:57 开始，通常 07:10～07:30；最多等 50 分钟，等不到就用手上最新的并提示）
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

## 2. 开户与 API 设定（v4r10，2026-09-25 核对）

1. 网上填表 → 邮寄 / 自行打印开户文件 → 寄回 2 种身份证明与マイナンバー → 审查 → ID / 密码以簡易書留寄到。
   账户类型选 **特定口座（源泉徴収あり）**；不要用 NISA 做自动交易（NISA 买单只能当日限价、不能逆指値）
2. 标准 Web 首次登录（电话认证一次）→ **注册パスキー**（官方只验证过 Windows 11，macOS 属「動作未確認」；可用 iPhone 等设备）
3. お客様情報 → 設定情報「**ｅ支店・API 利用設定**」→「利用する」→ 下载**认证 ID**（`e_api_authid.txt`）
4. **公開キー登録**：「登録（自動）」会当场生成密钥，**私钥只能下载这一次**；或「手動」上传你自己生成的 RSA 2048/4096 公钥（推荐：私钥从不离开 Mac）
5. 可选：登记固定 IP（官方「強く推奨」；家里 IP 会变就先别登）。API 只支持 IPv4、TLS 1.2/1.3
6. 有未读的交付书面时 API 不发放虚拟 URL → 收到通知就在 PC 网页上读完
7. デモ環境：在 demo.e-shiten.jp 另外取得デモ用认证 ID 和密钥（デモ不需要パスキー）

API 登录从 2026-06-27 起**不再需要电话认证**（只用公開鍵方式），程序可以每天自动登录；每次登录会收到一封「ログインメール」。
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

---

## 4. 校验 API 仕様（最关键的一步）

`qbreak/brokers/tachibana.py` 里的 `TachibanaSpec` 已按 2026-09-25 的公开仕様書（v4r10）逐项核对，
但**还没在真实账户上跑过**。API 版本（URL 里的 `e_api_vXrY`）和项目名会改版（登录应答会告知下一次发布日，日志里有提示）。

```bash
python3 run.py tachibana-probe --demo --dump-spec
```

这条命令**只读**：登录（认证 ID + 私钥解密虚拟 URL）→ 取价（7203 / 1329 / 1655）→ 持仓 → 余力 → 注文一覧，**绝不发单**。
有失败项就打开 `var/tachibana_spec.json`，对着官方仕様書逐项改；
程序会自动加载这个文件，**其余代码一行都不用动**。

全部 `[OK]` 之后，再跑一次本番環境（去掉 `--demo`）确认。

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

**让 Mac 在开市前自动唤醒**：

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
- [ ] `run.py doctor` 全绿
- [ ] `tachibana-probe --demo` 全 `[OK]`，且已对着官方仕様書改过 `tachibana_spec.json`
- [ ] `tachibana-probe`（本番，不加 `--demo`）全 `[OK]`
- [ ] `--broker paper` 演练过至少一个完整交易日
- [ ] `--protective-stop` 打开（逆指値是盘中止损的真正保险）
- [ ] 单笔上限：默认 = 资金 ×1.1（核心 ETF 一笔可到 100%）；前两周可 `--position-pct 0.05`（覆盖同档仓位）
- [ ] 立花：守护进程默认 16:45 下次日单（15:30～16:30 不受理）；目前一个进程只管一个分仓，两个分仓合并到一个会话之前不要同时跑两个守护进程（新登录会踢掉旧会话）
- [ ] 通知打开：`export QBREAK_WEBHOOK=https://...`
- [ ] 账户是**特定口座**，不是 NISA

**ARM（人工解锁）**：不解锁就不会发任何单。

```bash
echo ARMED > var/ARM      # 解锁
rm var/ARM                # 收盘后锁上
```

**紧急停止**（Python 侧立即拒绝一切下单）：

```bash
echo "手工停止" > var/HALT
```

---

## 8. 休眠、断网、崩溃

| 情况 | 会发生什么 | 兜底 |
|---|---|---|
| 进程崩溃 | launchd 30 秒内拉起，从磁盘恢复状态并对账 | 逆指値仍挂在券商侧 |
| Mac 空闲休眠 | `caffeinate -i` 阻止；合盖仍会睡 | **逆指値**（这就是必须开 `--protective-stop` 的原因） |
| 断网 | 取价失败，连续 5 轮后告警；**不会盲目卖出** | 逆指値 |
| API 报错 | 本轮捕获并记日志，下一轮继续；不会让守护进程死掉 | 心跳文件可判断存活 |

一句话：**程序是"更聪明的手"，逆指値是"永远在岗的保险"**。不要把止损只交给进程。

---

## 9. 关于「一天能交易几次」

現物取引下，**同一只股票**、同一营业日、同一笔资金只能做「买→卖」**1 个往复**；
之后用同一笔钱再买同一只就是**差金決済**，会被券商拒单。
**不同股票不受此限**（乗り換え売買 OK）。

代码里对应 `DaemonConfig.max_round_trips_per_day = 1`，程序自己会先拦一道，
不会等到被券商拒单才发现。

---

## 10. 常见问题

| 现象 | 处理 |
|---|---|
| `launchctl list` 里没有 qbreak | 看 `var/logs/daemon.err`，多半是 Python 路径或 `pip install` 没做 |
| 一直 `[NG] 登录` | 「ｅ支店・API 利用設定」没设为利用する / 公钥未登记 / 本番与デモ的认证 ID·密钥用反 / 交付書面未读 / 03:30～05:30 维护；仕様改版时改 `tachibana_spec.json` |
| 「虚拟 URL 解密失败」 | 私钥与登记的公钥不是一对（重新登记公钥，或换回当时下载的私钥） |
| 日志里全是「休市」 | 正常，今天是周末或祝日。`python3 -c "from qbreak.calendar_jp import session_of; print(session_of())"` 可确认 |
| 一直「未 ARM」 | `echo ARMED > var/ARM` |
| 想临时停掉但不卸载 | `echo x > var/HALT`（守护进程继续跑，但不发单） |
