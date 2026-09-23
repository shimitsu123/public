# macOS 全自动运行指南（立花証券 e支店 API）

> 面向：Mac + 不装 Excel + 想开机自启、全天常驻、自动买卖。
> 结论先行：**楽天走不通**（RSS 是 Windows 专用 Excel 插件），换 **立花証券 e支店 API** 是
> macOS 上唯一干净的方案；开户有约 1 周的书面手续，在此期间你可以用 `--broker paper` 把
> 整套流程完整演练一遍。

---

## 0. 三条路的取舍（为什么是立花）

| 券商 | macOS 原生 | 接口 | API 费用 |
|---|---|---|---|
| **立花証券 e支店** | ✅ | HTTP(GET+JSON) + 实时推送 | 0 円 |
| 三菱UFJ eスマート（kabu） | ❌ | REST，但要 kabuステーション（Windows）常驻 | 0 円 |
| 楽天証券 | ❌ | MARKETSPEED II RSS = Windows + Excel | — |

注意：**必须开「e支店」账户**（不是ストックハウス），书面手续，开户 1 周以上。
楽天账户可以继续留着手工用，不冲突。

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

## 2. 开户与 API 申请

1. 开 **立花証券 e支店** 账户（注意不要开成ストックハウス，开错了要先解约才能转）
2. 在会员页面申请 **API 利用**（免费），拿到**官方 API 仕様書**
3. 账户类型选 **特定口座（源泉徴収あり）**；不要用 NISA 做自动交易

---

## 3. 凭证放钥匙串，不要写进文件

```bash
security add-generic-password -s qbreak-tachibana -a <你的ログインID> -w
# 回车后会提示输入密码，不会留在 shell 历史里

# 取引暗証番号（如果需要）
security add-generic-password -s qbreak-tachibana-2nd -a <你的ログインID> -w
```

然后只需要在环境里设 ID：

```bash
echo 'export TACHIBANA_USER_ID=<你的ログインID>' >> ~/.zshrc
```

程序**只**从环境变量或钥匙串读凭证，代码和配置文件里不出现密码。

---

## 4. 校验 API 仕様（最关键的一步）

`qbreak/brokers/tachibana.py` 里的 `TachibanaSpec` 是**公开信息推断出的默认值**，
不是官方仕様書验证过的。API 版本（URL 里的 `e_api_vXrY`）和项目名会改版。

```bash
python3 run.py tachibana-probe --demo --dump-spec
```

这条命令**只读**：登录 → 取价 → 持仓 → 余力 → 注文一覧，**绝不发单**。
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
15:40          → 日线信号 → 次日**寄付**单 → 日终对账 → 存明日的熔断基准
```

**为什么盘中不重算信号**：当前策略的信号定义在收盘价上，回测也是这么验证的。
盘中重算 MACD 金叉会得到一堆盘中出现、收盘消失的假信号，而且**无法用现有回测验证**。
想做真正的日内策略是另一个项目（分钟级数据源 + 日内回测框架 + 全新信号定义）。

---

## 7. 上线清单

- [ ] `run.py doctor` 全绿
- [ ] `tachibana-probe --demo` 全 `[OK]`，且已对着官方仕様書改过 `tachibana_spec.json`
- [ ] `tachibana-probe`（本番，不加 `--demo`）全 `[OK]`
- [ ] `--broker paper` 演练过至少一个完整交易日
- [ ] `--protective-stop` 打开（逆指値是盘中止损的真正保险）
- [ ] 单笔上限：`--max-order-value 50000`，前两周 `--position-pct 0.05`
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
| 一直 `[NG] 登录` | API 利用申込未生效，或 URL 里的 API 版本变了（改 `tachibana_spec.json`） |
| 日志里全是「休市」 | 正常，今天是周末或祝日。`python3 -c "from qbreak.calendar_jp import session_of; print(session_of())"` 可确认 |
| 一直「未 ARM」 | `echo ARMED > var/ARM` |
| 想临时停掉但不卸载 | `echo x > var/HALT`（守护进程继续跑，但不发单） |
