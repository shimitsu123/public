# macOS 全自动运行指南（立花証券 e支店 API）

> **2026-09-25 晚更新**：用户决定继续用楽天（MARKETSPEED II RSS，需要一台 Windows 11），模拟盘改为楽天「一个账户」模式（见 README「一个账户（楽天）」一节）。本指南保留为可选方案：想在 Mac 上原生全自动交易日本株时再用。

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
