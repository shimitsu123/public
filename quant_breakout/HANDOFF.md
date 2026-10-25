# HANDOFF：现状与要点（给新的 Claude 会话；2026-09-25 写，2026-10-24 整理：历史记录移到 `HANDOFF_ARCHIVE.md`；有变化就更新这里）

细节以代码与这些文件为准：`README.md`（总览）、`MACOS.md`（Mac 与立花）、`var/sim_changes.md`（每次变更与研究结论，按时间）、
`REVIEW.md`（原版代码审查）、`var/out/`（研究报告与日报数据）、`RESEARCH_PLAN.md`（研究路线图：方向 R1〜R6、顺序与「稳定」的判定口径）、
`HANDOFF_ARCHIVE.md`（2026-09-26〜10-24 的逐条记录、已完成的待办原文、研究脚本的文件条目；CLAUDE.md 不引用它，要查时 grep）、
**`CHECK_TIMELINE.md`（检查时间线：全部研究按层与时间串起来 —— 每天 / 每周 / 每月 / 每季 / 每年看什么、事件驱动、前向记录的判定日历；日报「检查日历」一栏自动列出接下来 45 天）**。

## 一句话
个人资金 ¥1,000,000，一个账户方案 **S0C2**（立花証券 e支店 個別コース）：日本个股每只 25%、名额不设上限（2026-10-24 起；以前 4 个名额）（日経225 股票池）
+ 闲置资金全部买纳斯达克 100：**1545.T**（NEXT FUNDS 纳斯达克 100，东证上市、不对冲）；按 S&P500 的牛熊分界择时
（2026-10-02〜10-04 曾有「日元走强时换对冲版 2845.T」= FJE；2026-10-03 研究的汇率时点修正后按同一套标准重新检验不过 → 用户 ㊼ ① 事先同意 → **10-02 收盘的决策起撤掉**，`scripts/fje_recheck.py`），
熊市那份：**股债负相关（S&P500 与对冲版美债最近 63 天日收益相关 < 0）时拿 1482.T**（iシェアーズ・コア 米国債 7-10年 為替ヘッジあり；BCU，
2026-10-03 用户「采用」第六个研究循环的更好候选，10-02 收盘的决策起），否则留现金（1545 自 2026-09-30 起，用户要求「比 1655 收益更高的股票类」）；
原规则 = 1655.T（iシェアーズ S&P500，同一个牛熊分界），只给基准账户对照。
模拟期 **2026-09-28 → 2026-12-24**（2026-10-09 起模拟操盘与例行任务都在 Mac 本机；云端例行任务 2026-10-19 已删）；立花已开户、上线检查 `liveu.sh gate` 2026-10-24 全 OK，
**ARM 没建**：上不上实盘由用户决定。

## 现在在哪一步（2026-10-24）
2026-09-26〜10-24 每一次改动的来由、用户原话与长篇说明都移到了 `HANDOFF_ARCHIVE.md`「一」（不被 CLAUDE.md 引用；按关键词或编号 grep，
例 `grep -n "〔77〕" HANDOFF_ARCHIVE.md`）。这里只写现在的状态；以代码、`var/sim_changes.md` 与 `bash scripts/liveu.sh --broker paper --status` 为准。

**账户与规则**
- 模拟期 2026-09-28 → 2026-12-24（到期按事先的格式总结，待办 ⑬）；方案 S0C2、选股 B4（= B3 + TBF）定案（`var/sim.json` 的 unified 段），规则见下面「交易规则」。
  研究一律「先登记 → 再运行」，没通过的不采用（`var/sim_changes.md`、`var/out/research_map.md`）。
- 在用、会改变交易的层：个股突破 + W2、决算前 2 个交易日不进场、下单前资格检查 + 立花能不能买、退市时间表、新仓倍数（量化状态层 × 市场风险报告的判断层（2026-10-24 起停用、只显示）
  × 宏观层 × 板块倾斜）、前向记录判断层、关联搭配 C、TBF；离场 X6 吊灯止损；闲置资金 Q1B（美股牛 → 1545 纳斯达克 100（不对冲）；美股熊且股债 63 天负相关
  → 1482 对冲版美国 7〜10 年国债；否则现金）。全表：`CHECK_TIMELINE.md`「〇 一条主线」的表。
- 模拟账户（Mac 本机账本 `~/.qbreak/home/state/live_unified_paper.json`，不在仓库）：2026-10-24 权益约 ¥975,270；核心拿的是用户手动「固定口数」的
  1482 对冲版美国 7〜10 年国债（不是规则此刻的 1545 纳斯达克 100：固定口数期间不按规则调，直到「恢复按规则」）。实时数字以 `--status` / 面板为准。
- 股票池：日経225 全部 225 只（2026-09-30 起；以前 213 只）。

**立花証券 e支店（实盘）**
- 已开户；本番只读登录 2026-10-17 起正常（面板取实时现价 / 模拟账户取始値都用它）；デモ发单检查 2026-10-19 通过；`bash scripts/liveu.sh gate` 2026-10-24 全 OK
  （门槛 ②〜④ + 准备 ⑤〜⑧；① 与云端的连续一致 2026-10-19 起只作参考）。**ARM 没建、还没登记入金 → 现在不发真单**。
- 上不上本番、什么时候、多少钱由用户决定（待办 ⑫、〔77〕E1、路线图 3〜4）；ARM 只在用户这次对话里明确要求时建。实盘相关命令的等级照 CLAUDE.md「实盘相关（立花）」。
- 上线后头 5 个交易日照 MACOS.md §1.6「上线头 5 个交易日的值守清单」；退出 / 换 Mac / Mac 失控照 §1.6「退出实盘 / 回到模拟」、§1.14、§8「最后停止手段」。

**Mac 上的运行（2026-10-09 起全部在 Mac；云端例行任务 2026-10-19 已删，没有后备）**
- 执行器（模拟账户 `com.qbreak.liveu.paper`）每个交易日 07:40：`git pull` → 等当天的 `var/out/unified_today.json`（日报例行任务入库的，最多 50 分钟）
  → 同步判断层 / 宏观输入 → 撮合 → 对账 → 决策 → 下单；模拟账户的寄付单成交日 09:25 前后按开盘价当天撮合（2026-10-17 起开盘价 = 立花本番的始値，
  取不到 → Yahoo 1 分钟线），第二天早上按正式开盘价改记。09:30 自检每个工作日推一条到手机。
- 本机例行任务（Claude 桌面版，工作文件夹 `~/qbreak-sim`，说明书 `routines/`）：模拟盘日报 周一至五 06:45（2026-10-20 起不发布 artifact，只算 07:40 执行器的
  判断层 / 宏观输入并入库）、季度复核 1 / 4 / 7 / 10 月 12 日 09:56。没做 → 用户说「补跑」；问「例行任务今天跑了吗」→ `bash scripts/routines.sh check`。
- 2026-10-20〜10-23 本机任务停在权限确认（复合命令 / `$(…)` 要人确认），那几天 07:40 的执行器用的是旧的判断层 / 宏观输入；10-21 加自动停止（`qbreak.routines reap`）、
  10-23 改成单条命令 `routines.sh save / wait-sim`、2026-10-24 补了 4 条允许规则（见「已知限制」）。
- 唤醒：工作日 06:45 之前醒着即可 —— 文档写的 `sudo pmset repeat wakeorpoweron MTWRF 06:40:00` 或现在实际设的每天 06:30 都行；桌面版开着（登录项）+ Keep computer awake。
- 通知：qbreak 推送（网页 App）+ 通知记录（面板「消息 → 通知记录」）；邮件 / webhook 可选（不再推荐 `email-setup`）；外部心跳（healthchecks.io）不用。
- 面板 http://127.0.0.1:8765/（只在这台 Mac 上能打开）；手机只经 Tailscale Serve（地址看 `bash scripts/liveu.sh phone status`），按 Tailscale 账户登录。
- 手动指令（卖 / 减 / 调 / 买 / 闲置资金比例 / 固定口数 / 全部换成）只经面板或 `bash scripts/liveu.sh manual …`，下单由执行器做；时段口径与注意事项见 CLAUDE.md「实盘相关」与下面「在 Mac 对话里怎么问」。

**研究（等用户决定的在待办里）**
- 第十二〜十四个研究循环 + 以前约 150 个做法：没有比 B4 更好的选股；「碰巧通过」的之间没有关联（〔82〕）。
- 诊断：账户 ≥ 10% 回撤的亏损 76〜100% 来自核心 1545；SBS（美股牛时也 1545 : 1482 = 4 : 1）第一关与稳健都过但年化少 1.2〜3.5 pp（〔81〕，等用户选）。
- 前向记录（只追加）与判定日历：`CHECK_TIMELINE.md` 第八节；季度复核 2026-10-12 已跑（提交 9a686e2），下一次 2027-01-12。
- 2026-10-24 补记（事后）：新出现的联动群关联对比、数据体检的新问题（9201 日本航空没有加入年份）→ `var/sim_changes.md` 末尾两节。

## 待办清单（2026-10-24 清理：做完 / 已决定的移到 `HANDOFF_ARCHIVE.md`「二」（原文），这里只留没做完的 + 已完成的编号；按编号做，一次一项，做完报告结果）
🤖 = Mac 上的 Claude 可以直接执行　✋ = 要用户本人在 Mac 前操作或决定（2026-10-09 起改代码、改例行任务说明书也在 Mac 本地做，以前的 ☁️ 标记已去掉）。
做完的项由 Mac 上的 Claude 在 `~/qbreak-dev` 里移到 `HANDOFF_ARCHIVE.md`「二」（清单加一行、原文放进去）、下面「已完成」加编号（照常提交推送；`~/qbreak-src` 不改）。
条目里「见上面 …」指的说明多半已移到 `HANDOFF_ARCHIVE.md`「一」。

**A. 等用户决定 / 用户要做的**
- ⑫ ✋ 立花上本番（用户决定）：✅ 开户；✅ 本番只读登录（2026-10-17 起正常）；✅ デモ发单检查（2026-10-19 通过）；✅ `bash scripts/liveu.sh gate` 2026-10-24 全 OK（门槛 ②〜④ + 准备 ⑤〜⑧，含立花的定时任务与自动唤醒；① 只作参考）。交易时段里的现价字段（门槛 ⑤ 的提醒）：一次性 LaunchAgent `com.qbreak.probeonce` 2026-10-26〜10-30 工作日 10:30 只读 probe，取到就推送并自己卸掉（日志 `~/.qbreak/home/logs/probeonce.log`）。
  剩下：入金（到账后 `bash scripts/liveu.sh flow <金额>` 登记）→ 再跑一次 gate → `ARM`（只在用户这次对话里明确要求时建，MACOS.md §1.6）；先用较小金额跑 1〜2 周（路线图 4、〔77〕E1）；上线后头 5 个交易日照 MACOS.md §1.6「上线头 5 个交易日的值守清单」
- 〔77〕E1 ✅ 2026-10-24 用户「照 HANDOFF 待办清单选最优解」→ 小额试运行的做法定为（sim_changes 2026-10-24「用户决定」节）：**第一阶段先入金 ¥30 万、跑 10 个交易日**（个股一年约 6 笔，两周里多半只有核心 ETF 的单 → 试运行验证的是执行器 / 对账 / 自检，不是收益；小额时多数个股一手超过名额会被跳过，是预期的）；**加到计划金额 ¥100 万的条件（10 个交易日全部满足）**：每天执行器跑成（run.json）、09:30 自检每天通过、`reconcile` 没有不一致、`unknown` 没有状态不明的单、执行器的单没有被拒（资金不足 / 价格外之外的）、至少 1 笔核心 ETF 买单成交并对上账；`quality` 只作参考。出一次问题 → 先 HALT、查清修好，从 0 重新数 10 天；满足后入金 ¥70 万 → `liveu.sh flow 700000` 登记。入金、ARM 仍由用户在对话里明确说才做
- 〔83〕 ✅ 2026-10-24 用户「83③ 停用」→ **③ 停用判断层**：`var/sim.json` use_report_overlay = false（市场风险报告的行动照旧读、照旧显示，新仓倍数不再乘；量化层 / 宏观 / 前向记录判断层 / TBF 照旧；改回 true = 恢复；sim_changes 2026-10-24「用户决定」节）
- 〔82〕 ✅ 2026-10-24 用户「照 HANDOFF 待办清单选最优解」→ **① 选股研究先暂停**（没有比 B4 更好的选股、碰巧通过的之间没有关联；不加购 TDnet〔65〕；模拟盘不变）
- 〔81〕 ✅ 2026-10-24 用户「照 HANDOFF 待办清单选最优解」→ **① 维持现状**（SBS 1545 : 1482 = 4 : 1 回撤浅但年化少 1.2〜3.5 pp/年、没有平移的第二关 = 风险档的取舍，不是更准的时点；进取档、年化优先；不改 idle_cash）
- 〔65〕 ✋ 2026-10-05 **TDnet（适时开示）研究要你自己加购 J-Quants 附加包**（sim_changes 同日「用户决定（待办〔64〕选 ③）」）：用现在的 API 键实测 `/v2/td/list` 返回 403（Standard 不含）；附加包「TDnet / 適時開示情報」过去 5 年、¥11,000 / 月（税込）（J-Quants 官方价格页 2026-10-05 查，仅对本次检索时点有效）。要做就在 J-Quants 网站上自己加购（同一个 API 键就能用，键不用换、不要贴进对话），然后说「TDnet 已加购」→ Claude 先取数核对覆盖，再登记「有消息的突破 vs 没消息的突破」研究（按公開項目コード分类；先在全市場 W2 突破上判定）；不买也没关系（大量保有那一半已用 Standard 在做，见下一条与研究一节）。Claude 不代为购买、不操作网站。**影响估算**（2026-10-05 用户问，sim_changes 同日「做 TDnet 的话…」）：B3 每年只有约 6 笔日本个股、TDnet 窗口里约 30 笔，只能在全市場池上判定；找到可用规则约 10〜15%，找到了账户约 0〜+0.6 pp / 年（¥100 万约 ¥0〜6,000）；只为研究订 1 个月 ¥11,000，长期订 ¥132,000 / 年不划算

**B. 按日期 / 随时**
- ⑬ 2026-12-24 模拟期结束：总结 → 用户决定继续 / 上实盘 / 调整；同时看模拟盘（纳指 1545）与基准账户（1655）的差；（可选）J-Quants 付费档做无幸存者偏差回测（路线图 6）
- ㉑ ✅ 取消：2026-10-24 用户「不要影子账户任务」→ 影子账户（判断型）停用，前向记录停在 2026-10-23 那一条（只追加、不补），12-25 的 3 个月评估不做；中间统计照旧可看 `python scripts/shadow_account.py evaluate --interim`
  `python scripts/shadow_account.py evaluate`（标准见该文件开头第四节），汇报第一行写结论；只是记录，模拟盘不改；之后提示删除这个例行任务
- ⑳ 2029-09-28 之后第一次：K4 前向记录 3 年判定 `python scripts/energy_forward.py --review`（2031-09-28 之后再做 5 年判定；平时只看
  `var/out/energy_forward.csv` 是否每天在追加；2026-09-26 用户确认后，季度例行任务每次汇报进度（2h），只汇报不判定）
- ㉕ 2027-09-28 之后第一次：W2 前向记录的第一次年度判定 —— 每日记录在季度复核 2f 里自动算（看 `var/out/score_forward_review.md` 的 W2 一节）；全市场版在季度复核 2i 里自动算（2026-09-27 用户确认加入；手动：🤖 Mac：`bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python scripts/w2_forward_all.py --review`（在 `~/qbreak-dev`））；「失效警报成立」→ 提议关掉 W2，用户确认才改；同一份复核里另有 K2（放量 ∧ 低 β）/ USW（美国对应行业弱）两个只记录不交易的标记（2026-09-27 用户确认登记；`qbreak/idio_forward.py`），每年判定一次，证实也只是记录
- ㉖ 随时：时代主线前向记录的进度 🤖 `bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python scripts/era_outlook.py --review`（在 `~/qbreak-dev`）（2026-10 起每月一次；记满 36 个月 ≈ 2029-10 起判定失效与否；
  2026-09-29 起另报 3 个月判定的 JP-S33Q / JP-THQ「下一季」与最新一季的影响占比，记满 12 个季度起判定）；已加进季度复核 2j（2026-09-27 用户确认；同时每季刷新展望 `var/out/era_outlook.md`）
- ㊾ 随时 / 急跌时：VCT 前向记录 🤖 `env -u QBREAK_HOME ~/.qbreak/venv/bin/python scripts/vct_forward.py --status`（Mac 在 `~/qbreak-src/quant_breakout`，先 `git pull`；只读）；平时看日报那张卡片；满 1 年且有足够的急跌段才判定（规则 `qbreak/vct_forward.py` 开头；原来的说明见 HANDOFF_ARCHIVE.md「一」「VCT」）；✅ 2026-10-04 你确认 → 已加进季度复核 2m（10-12 起每季汇报进度）
- ㉝ 随时 / 事件发生时：「≤ −15% 深跌」前向记录（日経225；对照 S&P 500 / DAX / FTSE 100） 🤖 `env -u QBREAK_HOME ~/.qbreak/venv/bin/python scripts/deepdip_forward.py --status`
  （Mac 在 `~/qbreak-src/quant_breakout`，先 `git pull`；只读、不写文件）；平时看日报那一栏即可；有事件时日报标 ★，JP 满 5 个且都过了 60 个交易日起每次运行自动判定；只记录，用到交易要另外登记、用户确认）
- 〔78〕 🤖 2027-10-05（TBF 第一次年度复核日）之前：按 sim_changes 2026-10-06「配置变更」已登记的规则写 TBF 复核代码（每年一次：日経225 W2 信号里 TBF 挡 / 不挡两组的 X6 每笔，失效警报 = 不挡 − 挡 的 95% 上限 < 0 → 提议关掉；只读前向记录、只汇报），加测试，再给 `routines/quarterly.md` 加一步（云端后备 2026-10-19 已删）（〔69〕① 用户 2026-10-10 已确认；规则不改）

**已完成 / 已决定（2026-10-24 清理）**：⑭、⑨、㉔、⑩、⑪、㉞、㉙、㉚、数据完整性、日报可视化、㉛、㉜、㉟、㊱、㊲、交付书面、㊳、〔77〕、〔76〕、〔75〕、〔74〕、〔73〕、〔72〕、〔71〕、〔70〕、〔69〕、〔80〕、〔79〕、〔68〕、〔67〕、〔66〕、〔64〕、〔63〕、〔62〕、〔61〕、〔60〕、〔59〕、〔58〕、〔57〕、〔56〕、〔55〕、〔54〕、〔53〕、〔52〕、〔51〕、㊿、㊽、㊼、㊻、㊺、㊹、㊸、㊷、㊶、㊵、㊴、⑲、⑱（共 58 项）→ 一行一项的清单在 `HANDOFF_ARCHIVE.md`「二」最前面，原文在它后面（按编号 grep）。

## 交易规则（摘要；代码是准）
- 决策在日本与美国都收盘之后（日本时间 06:30 以后才算前一天完整）；成交在下一交易日 **09:00 寄付**（开盘）
- 个股：日経225 股票池的突破信号（`qbreak/strategy.py`，参数 `qbreak/config.py` + `var/best_params_JP.json`）；
  每只权益 25%、名额不设上限（2026-10-24 用户「个股名额空 4 个的上限去掉」；sim.json unified.max_positions = null，以前 4），单只 ≤ 34%；按名额买不到一手（100 股）就跳过（一手放宽 2026-09-27 生效前撤回，`var/sim.json` 的
  unified.one_lot_cap_pct = 0）；新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜；事件窗口关闭；
  决算前 2 个交易日不进场（`var/best_params.json` 的 earnings_blackout_days；交易日按东证日历数，2026-09-30 起含祝日；取不到决算日时不拦截）；
  **W2（2026-09-27 用户确认启用）**：最近完成的一周成交量 ÷ 之前 10 周平均 < 1.0 的突破不买（`var/best_params_JP.json` 的
  min_weekly_vol_ratio；周的完成按东证日历；历史不够不拦截）
- **下单前资格检查（2026-09-28 用户要求）**：被踢出日経225（名单对照 ja.wikipedia）、被 JPX 指定（特別注意 / 監理 / 整理）、上場廃止（含预定）、
  指数待剔除、股票池外的票不开新仓；资格数据 4 天以上取不到 → 当天不开新个股仓；执行器发买单前再查一次（`qbreak/eligibility.py`）；
  **退市时间表（2026-09-30 用户要求）**：上場廃止日 ≤ 今天 → 自动从股票池去掉（`qbreak/delist_schedule.py`，只减；补入要你确认、持仓不自动卖）
- 闲置资金（`var/sim.json` 的 `idle_cash.mode` = "Q1B"，`qbreak/idle_cash.py`；2026-10-02 收盘的决策起 FJE 撤掉）：美股牛 → 纳斯达克 100 1545（不对冲）；
  美股熊 + 股债 63 天负相关（BCU，`qbreak/bond_refuge.py`）→ 对冲版美债 1482、美股熊 + 不是负相关 → 现金；美股牛熊分界 = S&P500 连续 5 天收在 250 日均线 ×0.97 之下 → 熊（卖出，留现金）；连续 5 天在 ×1.03 之上 → 牛（`var/bullbear.json`）。
  基准账户照旧 1655 + 同一个分界（原规则）
- 回撤自动 HALT：**现在的一个账户模式（unified）没有** —— 回测（B3）、云端模拟盘、Mac 执行器三者一致，停下单只靠手动 HALT 文件（你说「停」就建）；`var/sim.json` 里 jp / us 段的 halt_dd_pct 45% 只在旧的分市场模式（`qbreak/risk.py`）里生效（2026-10-04 核对代码更正，以前这里写成「回撤达 45% → HALT（停新仓）」；要加自动回撤 HALT 是规则变更，见待办〔55〕）
- 牛熊的「现在处于哪个阶段」（牛市·稳固 / 走弱 / 临界 / 牛→熊确认中，熊市同理）只用于展示，阈值 3% / 8% / 5 pp 是展示用的，
  **不改交易规则**（`qbreak/bullbear.py` 的 `phase()`）
- 日报的「真突破 / 未破箱顶（差 x%）/ 距箱顶 x%」标签（个股买单与候补队列）同样只用于展示（`qbreak/scan.py` 的 `breakout_fields()`）
- 日报的「主题与业种」一节与个股的主题 / 业种标签（近 1 / 3 个月相对 TOPIX 1000、排名、与日経的同步度 R²、新出现的联动群）
  只用于展示（2026-09-26 用户要求；`qbreak/theme_monitor.py`，sim-day 写进 `unified_today.json` 的 themes）
- 日报顶部的「一眼看懂」仪表盘、Mac 的市场仪表盘与经济威胁提醒只用于展示与提醒（`macro_now` / `news` 写进 `unified_today.json`，
  健康度的颜色用宏观层自己的阈值；消息归类是标题关键词，影响链路的冲击幅度是「这类消息常见的幅度」× 行业敏感度，都不是预测）

## 每天的流程（周一至五，JST）
1. 前一晚 22:00：用户的另一个例行任务更新「市场风险报告」artifact（判断层与宏观数值的来源）
2. 06:45 Mac 的本机例行任务（2026-10-09 起；Claude 桌面版，`~/qbreak-sim`，`routines/sim_daily.md`；没做 → 说「补跑」，云端后备 2026-10-19 已删）：拉代码 → 从风险报告写 `var/market_regime.json`、`var/macro.json` → `sim-day`（其中先取资格数据：日経225 名单 + JPX 指定 → 行情对 J-Quants 交叉核对（只报警）→ 决策）→ 入库（2026-10-20 起不发布日报 artifact）；
   （07:45 影子账户判断：2026-10-24 用户「不要影子账户任务」停用）
   （云端容器是 UTC：`run.py` 启动时把进程时区固定为 JST（2026-09-27 起），「今天」、预计成交日、前向记录的日期与 Mac 一致）
3. 07:40 Mac（`scripts/liveu.sh run --broker paper`）：`git pull`，等当天的 `var/out/unified_today.json`（例行任务入库的；最多 50 分钟）
   → 把配置与输入拷到 `~/.qbreak/home` → 执行器：昨天的单按真实开盘价撮合（2026-10-15 起模拟账户成交日 09:25 前后已经撮合过的 → 这里只按正式日线开盘价改记；
   当天没撮合成的照旧在这里撮合）→ 对账 → 决策 → 资格检查（Mac 自己再取一次）→ 下「下一开盘」的单
   → 与日报例行任务的模拟盘逐日比较（只作参考，2026-10-19 起不算上线门槛）→ 通知中心 → 日志 → 重写页面并用浏览器打开（桌面的 `qbreak模拟操盘.html` 指向它）
   （手动指令：执行器每次运行先读 `~/.qbreak/home/manual/`；07:40 跑完以后点的卖出 / 减仓（Mac 或手机），交易日 07:45〜08:55 由操作面板叫执行器重试一次 → 当天开盘；
    加仓 / 买入不在重试里做 → 09:00 开盘后盘中马上（按现价限价，2026-10-07 起）；固定口数同样不重排寄付单 → 09:00 开盘后盘中马上（2026-10-15 起））
4. 模拟账户（2026-10-15 起）：成交日 09:25 前后操作面板叫 `bash scripts/liveu.sh run --broker paper --phase open`：按开盘价撮合寄付单（2026-10-17 起 = 立花本番的始値，取不到 → Yahoo 1 分钟线第一根），
   再按撮合之后的实际现金下等开盘后的买单（与立花 09:05 同一条路）；立花上线后另有 09:05 的开盘后补单（开盘前余力不够的买单）、08:35 / 09:20 的重试；09:30 自检（两种模式都有）；
   前一晚 20:00（周日〜周四）立花本番的前一晚预检（只读：登录 → 取余力 → 登出；2026-10-09 起，MACOS §1.6「运行保障」）

## 文件地图
- `qbreak/unified.py` 一个账户的推进器（回测、模拟盘、执行器共用）；`qbreak/live_unified.py` 执行器（对账、下单、安全闸、演练、比较、日志）
- `qbreak/brokers/tachibana.py` 立花 API v4r10 适配器；`qbreak/brokers/tachibana_sim.py` 模拟交易所（演练用）；`qbreak/brokers/paper.py` 模拟券商
- 立花实盘的运维（2026-10-09 缺口盘点 A / B 组，条目见 `var/out/tachibana_gap_audit.md`）：`qbreak/live_gate.py`（上线门槛，只读）、`qbreak/run_status.py`（运行状态文件）、`qbreak/watchdog.py`（09:30 自检；2026-10-14 起每个工作日推一条到手机，代替外部心跳）、`qbreak/notify.py`（手机通知：qbreak 推送 + 钥匙串的 webhook / 邮件；外部心跳可选、不再用）+ `qbreak/notify_seen.py`（同一天同样的文字只通知一次）、`qbreak/live_ops.py`（撤单 / 状态不明的候选 / 持仓核对 / 人工代下登记；2026-10-15 起还有资金依赖的级联 `fund_cascade`、「今天已有执行器的单」`busy`、「今天会不会下」的唯一判断 `outlook`）、`qbreak/trade_room.py`（今天还能买几次 / 卖几次；2026-10-15 起）、`qbreak/book_backup.py`（账本备份 / 恢复 / 读坏不新开）、`qbreak/precheck.py`（前一晚预检）、`qbreak/versions.py`（运行状态记的代码 / 依赖版本）、`requirements.lock` + `scripts/install_deps.sh`（依赖锁）、`scripts/install_launchd_{watchdog,precheck}.sh`、`scripts/dev.sh`（Mac 本地改代码 / 推送）；例行任务搬到 Mac：`qbreak/routines.py` + `scripts/routines.sh` + `routines/`；测试 `tests/test_docs_b.py`（文档与门槛 ① 过期）等
- `qbreak/bullbear.py` 牛熊分界 + 阶段；`qbreak/report_unified.py` 日报；`qbreak/desktop_page.py` Mac 的账本页面
- 手动指令：`qbreak/manual_orders.py`（指令文件、检查、执行器里的 Manual：卖出 / 减仓 / 调整持仓（可加可减）/ 买入 / 闲置资金比例 / 不买回 / 撤回；
  名额估算 `slots`；核心 ETF 的买卖 → 闲置资金比例 `core_info` / `core_rec` / `core_pct_for` / `core_effects` / `core_pct_now`，执行器账本的 `core_rule`、
  引擎的 `core_t100` / `core_exact`；停买与买入信号 `manual.core_pause` / `manual.core_signal`（执行器 `_record_core` 判信号）、`signal_text`）、
  `qbreak/panel.py`（本机操作面板 127.0.0.1:8765，只写指令；「调仓…」「买入…」对话框、K 线、`/api/chart`、持仓现价 `/api/quotes` = `quotes_json`
  ← `qbreak/data.intraday_quotes`（含今天到那个时刻的一根 `bar`）；持仓的 K 线盘中并进今天这一根 = `kline.with_live`（`chart_json` 里，`live.open` = 盘中 / 暂定）；
  卖出的预计收益 = `manual_orders.sell_estimate` / `est_lines` / `core_cost`（ETF 移动平均成本）/ `sale_note` / `fee_jp`，页面 `CFG.est` + 现价接口的 `est`）、
  `scripts/install_launchd_panel.sh`（LaunchAgent `com.qbreak.panel`）；
  加仓在引擎里：`UState.add_plan`、`add_room` / `add_fill` / `_exec_adds`（`qbreak/unified.py`），执行器的单 reason = manual_add（cid `U<决策日>-BUY-<票>-M`）；
  买入 = `UState.plan`（与规则的新仓同一笔计划）+ 账本 `manual.buys`，执行器的单 reason = manual_buy（cid 同上）；
  建议的股票：`qbreak/suggest.py`（run.py `_suggest`）；K 线：`qbreak/kline.py`（run.py `_kline` → `out/charts_<账本>.json`；副图 MACD / DMI、
  趋势线 `qbreak/trendline.py`，测试 `tests/test_trendline.py`；趋势线研究 `scripts/trendline_study.py` / `scripts/trendline_select_study.py`；TQ08 前向检验 `qbreak/tq08_forward.py` + `scripts/w2_forward_all.py` 第十一节，测试 `tests/test_tq08_forward.py`）；
  建议的股票的排序：`suggest.rank` / `order_key`（有 `var/watch_prob.json` → 闸门 → 历史比例 `qbreak/watch_prob.py`（登记研究 `scripts/watch_prob_study.py`，
  测试 `tests/test_watch_prob.py`）→ `near_key`；没有 → 快要出 → 观察中 + `near_key`）、`suggest.proximity` / `near_text`（离买入信号的远近，只展示）；
  下单按什么价 `manual_orders.order_basis` / 晚了几分钟的范围 `delay_range`（面板 `_dvol` / `_delay_min`）；建议的股票的现价 `quotes_json(…, extra=…)`（`/api/quotes?t=`，
  `SG_MAX` 只、只接受汇总里的）+ K 线并进今天这一根（`chart_json` 的 `_suggested`）；ETF 的规则目标估算 `manual_orders.core_u100s` / `core_u100_est`（执行器 `_core_pending` /
  `now_phase` 同一个）；测试 `tests/test_panel_suggest_live.py`；
  趋势标签旁的历史统计（〔75〕②）：`qbreak/dip_stats.py`（`kline.month_up` = 研究的 MUB → trend.M.up3；测试 `tests/test_dip_stats.py`）；
  ETF 卡片「什么时候会自动卖」：`qbreak/core_exit.py`（`build` / `market_row` / `market_tiles` / `partial_row`；面板 `_exit_html`；数字 = 执行器汇总的 `market` / `idle_cash` /
  `new_pos` ← run.py `_new_pos_brief`；测试 `tests/test_core_exit.py`）；
  持有理由与趋势：`qbreak/holding_view.py`；测试 `tests/test_manual_adjust.py`、`tests/test_manual_buy.py`、`tests/test_suggest.py`、`tests/test_kline.py`、
  `tests/test_manual_core.py`、`tests/test_core_pause.py`（停买 / 买入信号 / 确认买入）、`tests/test_panel_quotes.py`（现价）、
  `tests/test_kline_live.py`（K 线盘中的一根）、`tests/test_sell_estimate.py`（卖出的预计收益）
- 手机上操作：`qbreak/panel_phone.py`（配对码 / 设备 / CSRF / 按 Tailscale 账户登录 `identity_for` + 路径密钥 `split_gate` / HALT 只能建 / Tailscale Serve 的 on・off・status・forget・identity / 二维码 / 主屏幕图标）、
  `qbreak/panel.py` 的手机端口 127.0.0.1:8766（`make_phone_handler`；页面请求 15 秒超时 `_NET_JS`）、`run.py panel-phone`、测试 `tests/test_panel_phone.py`
- `run.py`：`sim-day`（日报例行任务）、`live-u`（执行器）、`live-u-rehearse`（演练）、`tachibana-probe`（连通性检查）、`doctor`
- `scripts/liveu.sh`（Mac 上跑执行器；`news` = 市场仪表盘 + 经济威胁提醒）、`scripts/install_launchd_live_u.sh`（注册定时任务）、
  `scripts/install_launchd_news.sh`（仪表盘每 15 分钟）、`scripts/mac_bootstrap.sh`（一行安装）
- `qbreak/dashboard.py` 仪表盘（日报顶部与 Mac 页面共用）、`qbreak/macro_now.py` 健康度与新数据、`qbreak/news.py` 消息监控、`qbreak/viz.py` 小图
- 政策事件反应库：`qbreak/policy_events.py`（规则）、`scripts/policy_event_data.py`（数据）、`scripts/policy_event_study.py`（登记 + 研究）、
  `scripts/policy_event_verify.py`（来源核对）、`qbreak/policy_forward.py`（前向记录）、`var/policy_events.csv`（事件表）、`var/policy_extra_pool.json`（长历史池补充票）
- 日报例行任务的模拟盘状态：`var/state/unified_state.json`；Mac 状态：`~/.qbreak/home/state/live_unified_paper.json`（账本，不在仓库）
- 前向记录判断层：`qbreak/fwd_judgment.py`（规则与计分）、`var/fwd_judgment.json`（每天的判定，日报例行任务写、执行器读）、
  `var/state/unified_state_base.json`（基准账户：原规则 = 不加判断层、离场用死叉、闲置资金 1655 + 牛熊分界）、`scripts/fwd_judgment_check.py`（历史检验）
- 关联搭配 C：`qbreak/combo_c.py`（冻结的规则、特征、市场格、每天的文件、前向记录的列与第十二节复核）、`var/combo_c.json`（每天的判定，日报例行任务写、执行器读）、
  `run._cc_compute`（sim-day 决策前算）、`tests/test_combo_c.py`
- TBF 像起跌点就不买：`qbreak/tbf.py`（特征、打分、实盘日历、每天的文件、前向记录）、`var/tbf_model.json`（冻结的三个尺度的模型参数；`scripts/tbf_export.py` 从研究重拟合导出）、
  `var/tbf.json`（每天的判定，日报例行任务写、执行器读）、`var/out/tbf_forward.csv`（前向记录，只追加）、`run._tbf_compute`（sim-day 决策前算）、`tests/test_tbf.py`
- 个股离场方式：`qbreak/exit_rules.py`（DC / X6 / R4 / X6R4 / ALL；`var/sim.json` 的 exits 选用）、引擎实现在 `qbreak/unified.py` 的 `_check_exits`
- 闲置资金方式：`qbreak/idle_cash.py`（K0〜K6、股票类 Q1〜Q6 与「预计下跌 → 反向」开关 P1〜P4（没采用）；`var/sim.json` 的 idle_cash 选用；
  月末开关 TR: / RT: / XR 与 EQ / IV 键进引擎的 bear）、研究 `scripts/idle_cash_study.py`、`scripts/equity_idle_study.py`
- 投资流向（按行业的季度设备投资）：`qbreak/invest_flow.py`（財務省 法人企業統計 季報的取数 → `var/cache/mof/`、固定資本マトリックス → `var/cache/io/`；
  导出的暴露 `var/invest_fcm_2020.json`）、研究 `scripts/invest_flow_study.py`（不成立，只作背景）；日报的季度快照 `var/invest_flow_snapshot.json`
  （`qbreak/invest_flow.py` 的 snapshot / refresh_snapshot，㉟，2026-09-30 起）
- 股票池：`qbreak/universes.py`（2026-09-30 起日経225 全部 225 只；以前剔除的名单 `*_UNTIL_20260929`）；换股票池后的研究复核
  `scripts/universe_recheck.py`（同一脚本在 213 / 225 只两个股票池各跑一遍，比较结论 → `var/out/universe_recheck.md`）
- 季度决算的轨迹：`scripts/earn_traj_data.py`（J-Quants 決算短信 → 单季营业利润、Yahoo → 美股每季 EPS、六种形态）、
  `scripts/earn_traj_study.py`（登记 fabde0b：事件层 + 选股层）→ `var/out/earn_traj_study.md`
- 日报的决算形态（㊱）：`qbreak/earn_state.py`（panel / state_of / tag_html；缓存 `var/cache/jquants/fins_code/`，不入库）
- 买卖时间线：`qbreak/timeline.py`（build / buy_trigger / sell_levels / scenario_entry / scenario_exit / html；run.py 的 `_timeline_panel` 接进 sim-day）、测试 `tests/test_timeline.py`（真实引擎核对）；「预计卖出」的统计 `scripts/timeline_stats.py` → `var/timeline_stats.json`（规则或股票池改了就重跑）；W2 × 连休短周的描述 `scripts/w2_short_week.py` → `var/out/w2_short_week.md`（㊲ 的背景）；W2 的日均版 W2d 对照 `scripts/w2d_study.py` → `var/out/w2d_study.md`（㊲，没通过；定义 `qbreak/mtf.weekly_volume_ratio_per_day` 只研究用）；周末 / 祝日：东证日历 `qbreak/calendar_jp.py`、美国日历 `qbreak/calendar_us.py`（规则计算）、休市期间日経225先物参考 `qbreak/holiday_gap.py`（日报一行）与描述 `scripts/holiday_gap_study.py` → `var/out/holiday_gaps.md` / `var/holiday_gaps.json`
- 闲置资金 BCU（2026-10-03 采用）：`qbreak/bond_refuge.py`（`tests/test_bond_refuge.py`）→ `var/bond_refuge.json`（sim-day 写）；`run._br_compute` / `run._br_keys`
- VCT 前向记录（2026-10-04 起）：规则 / 记录 / 复核 `qbreak/vct_forward.py`（sim-day 的 `_vct_forward_log`）→ `var/out/vct_forward.csv`；状态 / 复核 `scripts/vct_forward.py --status / --review`；`tests/test_vct_forward.py`
- 行情缓存：`qbreak/data.py`（有效期 12 小时 + 按交易日历查新鲜度；盘中取的缓存在收盘后视为过期、重新下载 —— 2026-09-29 修正，以前收盘后 12 小时内会把盘中快照当成收盘价；重下载失败去掉那一根并记为「行情落后」）；**价格调整口径 v2（2026-09-30）**：不用 yfinance 的 auto_adjust，改为 `qbreak.data.adjust_prices` 按 Yahoo 的分红 / 拆股记录自己调整（同一口径，实测与 Yahoo 的 Adj Close 差 < 1e-6），**拆股当天的分红按拆股后口径**（Yahoo 把日本株分割与配当同一基準日的分红记成分割前每股金额 → 8766.T 2026-09-29 被当成 22.8% 的分红、之前价格整体调低、当天「涨」25.8%；横向扫描 1,076 只近 2 年 20 例，含 8035.T / 5401.T 2025-09-29），公司行为随缓存的 meta 保存（`actions_of` / `fixes_of`）、缓存 meta 带 `adj` 版本号（口径不同就重新下载）；**指数日线缺收盘 → 用当天 5 分钟线合成**（`fill_index_from_intraday`，只补 `^` 开头、已收盘的日子；Yahoo 的 ^N225 2026-09-29 只给开盘、收盘 NaN），记进 `FILLED`，日报「数据完整性 · 自动修复」列出；**中间漏掉的日子也补**（2026-10-06 用户要求；`missing_days`：最后一天之前 10 个交易日里按东证 / 纽约日历缺的日子，只查日历确定的股票指数 `GAP_TICKERS`，例 ^N225 2026-10-05；补不上的记进 `GAPS`、日报「数据完整性」列为「行情中间缺日」；同日修正：日报数据以前没带 `filled` / `data_fixes`，「自动修复」一直没显示）；威胁指数的指数序列同样处理（`qbreak/threat.py`）
- 下单前资格检查：`qbreak/eligibility.py`（快照 `var/out/eligibility.json`；只读检查 `run.py eligibility`）；退市时间表：`qbreak/delist_schedule.py`
  （`var/delist_schedule.json`；`run.py delist-schedule`；`tests/test_delist_schedule.py`）；成本 × 销售显示与 S2 前向记录：`qbreak/cost_sales_forward.py`
  （复核 / 当前分组 `scripts/cost_sales_forward.py --review | --show`）
- 研究脚本的文件条目（B・N・F、利率 / 国债 / 贸易、关联搭配、各研究循环的规则与状态等，以前在这一节）：`HANDOFF_ARCHIVE.md`「三」；全部研究的总表 `var/out/research_map.md`

## 用户常问的，去哪里查
- 「今天买卖了什么 / 为什么没买」：页面、日志 `~/.qbreak/home/out/live_unified_paper_journal.md`、当天汇总
  `~/.qbreak/home/out/live_unified_paper.json`（orders 的 status / note、blocked、events）
- 「和云端不一致」（2026-10-19 起只作参考：比较的是日报例行任务的模拟盘）：日志里的比较行（两边的持仓、现金、权益差）。多半是数据不同（日报例行任务当天晚了 / 没跑 → Mac 用了前一天的判断层；
  Yahoo 行情修正）。重新对齐：删掉 `~/.qbreak/home/state/live_unified_paper*.json`，下次从日报例行任务的模拟盘当时的状态开始
- 「页面没更新 / 没弹出」：`launchctl list | grep qbreak`、`~/.qbreak/home/logs/`；`~/.qbreak/home/NO_OPEN` 存在就不弹出
- 「前向记录判断层今天生效了吗 / 为什么减半」：Mac 页面「前向记录判断层」卡片与日志那一行（`~/.qbreak/home/out/live_unified_paper.json` 的 fwd_judgment）；
  日报例行任务算的详细读数与候选判定在日报「前向记录判断层」卡片（`var/out/unified_today.json` 的 fwdj、`var/fwd_judgment.json`）；
  「★ 没生效」多半是日报例行任务当天晚了 / 没跑（文件日期是前一天）→ 那天按原规则，和云端的对照会不一致
- 「关联搭配 C 今天跳过了谁 / 为什么」：Mac 页面「关联搭配 C」卡片与日志那一行（`live_unified_paper.json` 的 combo_c）；日报例行任务算的特征 / 投票 / 分数在日报
  「关联搭配 C」卡片（`var/out/unified_today.json` 的 combo_c、`var/combo_c.json`）；不在「平静的牛市」（日経在 200 日线下或 VIX ≥ 20）时 C 不动
- 「TBF 今天挡了谁 / 为什么」：Mac 页面「TBF 像起跌点就不买」卡片与日志那一行（`live_unified_paper.json` 的 tbf）；日报例行任务算的三个百分位在日报「TBF」卡片
  （`var/out/unified_today.json` 的 tbf、`var/tbf.json`）；「★ TBF 没生效」= 日报例行任务当天晚了 / 没跑（文件日期是前一天）→ 那天按原规则
- 「选股放在美股（楽天）好还是日経（立花）好」：`var/out/market_compare_study.md`（2026-09-29：日経更好，美股被楽天约 1% 的来回费用吃掉）
- 「明天 / 这几天会买卖什么、什么价位会卖、候补什么价位会出买点」：日报「买卖时间线」卡片或 Mac 账本页面同名一节（`var/out/unified_today.json` 的 timeline；日报例行任务每天按前一天收盘重算；价位是规则的翻译、情景不是预测）
- 「牛熊现在怎样」：页面「牛熊：现在处于哪个阶段」或日报「市场状态」（离 250 日线的 %、20 个交易日的变化 pp、离翻转还差多少 %）
- 「现在偏向哪边 / 市场健康吗 / 有什么威胁消息」：Mac 的 `~/.qbreak/home/out/dashboard.html`（每 15 分钟，账本页面顶上有链接）或日报「一眼看懂」；
  消息的全文列表 `~/.qbreak/home/cache/news/news.json`；定时任务日志 `~/.qbreak/home/logs/com.qbreak.news.out|err`

## 在 Mac 对话里怎么问（2026-09-26 起用户只用 Mac 的 Claude 对话；规则见 CLAUDE.md「在用户的 Mac 上」）
**用户问什么，Claude 就直接运行需要的命令并汇报结果**（不是把命令列给用户去跑；研究在 `~/qbreak-dev` 里一口气做完）。
**2026-10-09 起改代码、提交、推送（上传）也在 Mac 本地的 Claude 里做，不需要云端会话**（`scripts/dev.sh check | test | push`）；**例行任务也在 Mac 上**（Claude 桌面版的本机任务，`~/qbreak-sim`、`routines/`；云端同名例行任务 2026-10-19 已删，没有后备：没做 → 说「补跑」）。
执行器管理买卖的方式：每个交易日 07:40 按规则自动决策、下「下一开盘」的单（立花上线后另有 09:05 开盘后补单；模拟账户 2026-10-15 起成交日 09:25 前后按开盘价当天撮合）；
你控制的是「开 / 停 / 只演练 / 确认状态不明的单」，以及 2026-10-06 起的**手动卖出 / 减仓 / 调整持仓（可加可减）/ 闲置资金比例**（只写指令，执行器在下一次
能下寄付单的运行里下单，同样的闸门；加仓只能加已经持有的个股、有闸门，不能手动开新仓）。系统不给买卖建议，也不在执行器之外发单。

| 想做什么 | 这样问（例） | Claude 做什么 | 注意 |
|---|---|---|---|
| 装 / 更新全部 | 「拉一下最新代码并更新」「把定时任务都装好」 | `git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh`（手机访问打开过的话，这条也会确认 Tailscale Serve 还在、不弹页面） | 不动账本、不下单 |
| 改代码 / 修问题 | 「改 xxx」「修 xxx」「面板上加 xxx」 | 在 `~/qbreak-dev`（`quant_breakout/` 下）：第一次 / 出问题时 `bash scripts/dev.sh check` → 改 → `bash scripts/dev.sh test`（全部通过）→ `git commit`（不写模型名）→ `bash scripts/dev.sh push` → 汇报改了什么、推了哪几个提交 | `~/qbreak-src` 只 pull、不改；交易规则 / 参数 / 仓位 / 股票池不改，除非你明确说并记 sim_changes；研究先登记（提交推送）再运行 |
| 推上去 / 上传 | 「推上去」「上传到 GitHub」「让明天的定时任务用新代码」 | `bash scripts/dev.sh push`：有未提交的改动 → 停下；`git pull --rebase`（冲突 → 停下、不自动解决，回到 pull 之前）→ 推送 → `~/qbreak-src` 快进（它有本地改动不动；交易日 07:30〜09:35 JST 不换代码，不拉也行：下一个交易日 07:40 自动拉）→ 列出推了哪几个提交 | 只推开发分支、不开 PR；推不上去（没登录 GitHub）→ 请你自己在终端 `gh auth login`（或配 SSH 钥匙），令牌不贴进聊天 |
| 检查本地开发环境 | 「检查本地开发环境」「为什么推不上去」 | `bash scripts/dev.sh check`（只读：`~/qbreak-dev` 的分支与上游、能不能连远端、推送权限（`--dry-run`）、git 的 user.name / user.email 有没有设、Python ≥ 3.10 + pytest、`~/qbreak-src` 有没有本地改动） | 只读；不打印用户名 / 邮箱 / 令牌；git 身份由你自己设（公开仓库：用不暴露个人信息的名字与 GitHub 的 noreply 邮箱） |
| 立花那边实际是什么 / 今天的成交 | 「看立花那边」「今天成交了吗」 | `bash scripts/liveu.sh broker`（只读：持仓 / 余力 / 注文一覧 / 今天每笔单的约定 / 立花现价 → 面板「立花那边」；拿运行锁与立花本番会话锁）；立花本番装好后 11:35 / 15:45 自动跑并通知（〔77〕C） | 只读；正式记账仍在下一个交易日 07:40 |
| 执行质量 | 「执行质量怎么样」「成交价差多少」 | `bash scripts/liveu.sh quality [--since YYYY-MM-DD]`（只读：成交率、成交价差 bp、没成交 / 被挡次数、与云端一致天数，只作参考） | 只读；加到计划金额的条件按〔77〕E1（2026-10-24 定） |
| 导出交易记录 | 「导出今年的交易记录」 | `bash scripts/liveu.sh export [--year 2027]`（成交 / 已实现 / 入出金 / 现金差 CSV → 数据目录 out/export/，UTF-8 BOM） | 只读、不入库 |
| 开户之后怎么做 | 「立花开户了，下一步做什么」 | `bash scripts/liveu.sh onboard`（只读：步骤 + 上线检查里还没完成的 + 下一步；不登录、不建 ARM） | 密钥由你自己在终端存进钥匙串 |
| 出金（先留现金） | 「我要出金 30 万，先留着别买回」 | 你明确说要预留时 `bash scripts/liveu.sh flow -300000 --flow-reserve`（到账前决策按扣掉它算：个股仓位变小、ETF 不买回、现金不够先卖核心 ETF；到账后自动解除） | 会动仓位；不预留只登记 = 只影响收益显示 |
| 手机连不上 / 菜单栏图标是红的 | 「手机连不上」「菜单栏变红了」 | `~/.qbreak/venv/bin/python -m qbreak.mac_status --print`（只读：执行器、自检、定时任务有没有被卸掉、手机访问、面板）；手机访问断了每 15 分钟自动修一次 | 手机只用 https://<机器名>.ts.net/（主屏幕图标），127.0.0.1 是手机自己 |
| 手机上收推送 | 「手机要推送」 | iPhone：Safari 打开手机地址 →「共享 → 添加到主屏幕」→ 从主屏幕图标打开 →「通知（推送）」→「在这台设备打开推送」→ 允许；`bash scripts/liveu.sh notify-test` 会同时发推送 | iOS 16.4 以上 |
| 交易时间 Mac 不要睡 | 「交易时间 Mac 不要睡」「手机盘中连不上」 | 你同意后 `bash scripts/install_launchd_awake.sh`（周一至五 08:55〜15:30 caffeinate -i -s，接电源时有效；卸载加 `uninstall`）；系统设置里已经关了自动睡眠就不用 | 耗电、合盖照样睡 |
| 装本机例行任务 | 「装本机例行任务」「把云端的例行任务搬到 Mac」 | 照 `quant_breakout/routines/README.md`：确认 `~/qbreak-sim` 在（没有就跑 `mac_setup.sh`）→ 在 Claude 桌面版的 Code → Routines → New routine → Local 建两个本机任务（模拟盘日报 周一至五 06:45、季度复核 1 / 4 / 7 / 10 月 12 日 09:56；工作文件夹 `~/qbreak-sim`、不用独立 worktree；说明只写那份固定文字，市场风险报告的 URL 只写进本机任务、不入库）→ 每个先 **Run now** 一次、权限选 always allow → `bash scripts/routines.sh check` | 要你在这次对话里说才建；桌面版开着（登录项）、Keep computer awake 打开、`sudo pmset repeat wakeorpoweron MTWRF 06:40:00`（或每天 06:30：早于 06:45 就行）你自己在终端做；云端同名例行任务 2026-10-19 已删（没有后备） |
| 例行任务今天跑了吗 | 「例行任务今天跑了吗」「今天的日报是 Mac 做的还是云端做的」 | `bash scripts/routines.sh check`（只读：`~/qbreak-sim` 的分支 / 本地改动 / 推送权限 / git 身份、桌面版 ≥ 1.1.5368、三个本机任务建了没有、钥匙串有没有 qbreak-jquants、pmset 工作日 06:50 之前唤醒、最近 5 个工作日每天的日报 / 影子账户是 Mac 还是云端做的、本机任务按时跑了没有 / 有没有卡住的运行（读桌面版的运行记录；读不到就跳过）、说明书要运行的命令在不在允许规则里（`~/qbreak-sim/.claude/settings.local.json` + 任务自己允许过的；对不上的逐条 [★]、只打印说明书里的命令；2026-10-16 起）；历史表看三个克隆里远端记录最新的那个）；桌面版 Code → Routines → 点任务 → Review history | 只读；`~/qbreak-sim` 有本地改动 / 没推上去的提交 → 说清是哪一次留下的，你决定怎么处理（不自动 reset / 丢弃）；报「那次一直没动」/「没跑」→ 照 routines/README.md「限制」恢复（在 Code → Routines 停掉卡住的运行；把停下的那条命令加进允许规则要用户同意；2026-10-21 起卡在权限确认 30 分钟以上的由每 15 分钟的 `python -m qbreak.routines reap` 自动停止 + 推送，记录 `~/.qbreak/home/out/routines_reap.json`）；报「允许规则里没有」→ 要加的规则 `python -m qbreak.routines allow-missing`（只读），用户同意后才加进 `~/qbreak-sim/.claude/settings.local.json`（不写全局设置、不写宽规则）。09:30 自检的推送也会带一行「★ 本机例行任务：…」（下一行） |
| 手机通知 | 「手机通知设好了吗」「发一条测试通知」「手机通知用邮件」 | 看：`bash scripts/liveu.sh gate` 的 ⑧；试发：`bash scripts/liveu.sh notify-test`（按钥匙串里设置了的通道各发一条，打印「已发 / 失败 / 没设置」）；设邮件（2026-10-09 起用这个）：**你自己**在「终端」App 运行 `bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup`（问发件 Gmail 地址、应用专用密码（不显示，空格自动去掉）、收件地址（回车 = 同发件，多个用逗号）→ 先发一封测试邮件 → 发成了才存进钥匙串 `qbreak-smtp`（密码 / 地址被服务器拒绝 → 不存）；Claude 的工具里没有终端，它会拒绝运行）；Gmail 先开两步验证，在 https://myaccount.google.com/apppasswords 建应用专用密码；改 Google 密码会让它失效（再运行一次 email-setup）；iPhone 的「邮件」或 Gmail App 打开通知；Gmail 建过滤器：主题含 qbreak → 不进垃圾邮件、标星；别的邮箱加 `--host … --port 465`；设 webhook：你自己在终端 `security add-generic-password -s qbreak-webhook -a qbreak -w`（回车后输入 Discord / Slack / ntfy 的通知地址，不贴进聊天） | 地址 / 密码是密钥：Claude 只说有 / 没有、不打印；定时任务读不到 `~/.zshrc` 的环境变量，所以放钥匙串 |
| 09:30 自检 / 每天的推送 | 「今天的自检过了吗」「Mac 没跑会提醒我吗」「今天怎么没收到 09:30 的推送」 | 看结果 `~/.qbreak/home/out/watchdog_{paper,tachibana}.json`（ok、reasons、push = 那条推送发成没有）、日志 `~/.qbreak/home/logs/com.qbreak.watchdog.out`，或 `bash scripts/liveu.sh watchdog --dry`（只判定、打印：今天早上的执行器跑完没有、有没有状态不明的单、（立花）开盘后的买单下了没有、该下了还没下的手动指令（过了该下的时刻 10 分钟以上：面板没开 / 自动下单暂停 / 早上没跑完；2026-10-14 起；2026-10-15 起还没读的固定口数也算）、今天不会下的单（凑钱的卖单撤了 / 钱不够 / 钱没来 / 被拒…：`live_ops.outlook` 同一个判断，2026-10-15 起两种账本都看，以前照样「✓ 通过」）、写了撤单而面板自动下单暂停、单还挂着（2026-10-16 起；要撤就「再试一次」或在立花网站 / 手机网站撤）；不写结果文件、不推送；执行器还在跑时自检等它跑完（看 liveu.sh 的运行标记，跑完之后让 Mac 醒着到 09:35 的那段不等））；「再自检一次」才跑 `bash scripts/liveu.sh watchdog`（会重写结果文件；没通过会再推一条，通过且今天已经推过就不再推；不下单）。外部心跳（healthchecks.io）2026-10-14 起不用（用户「不用做 healthchecks.io 心跳 check，改为每天用 qbreak 进行推送就可以」） | 每个工作日推一条到手机（2026-10-14 起）：通过 →「✓ HH:MM 自检通过」（决策日、今天的单几笔成交 / 挂着；2026-10-15 起之后才下的单 / 指令列在后面、不算失败）、平日休市 →「今天休市（系统正常）」、没通过 → ★ + Mac 通知（单 / 指令今天不会下 → 标题以「★ 交易：」开头，2026-10-15 起）、HALT →「HALT 生效中」、执行器一直在跑 →「★ 自检判定不了」、自检程序出错 →「★ 自检出错」（看 `com.qbreak.watchdog.out` 的堆栈）；交易日本机例行任务卡住了（多半在等权限确认）/ 今天到点 30 分钟还没跑 / 晚 30 分钟以上才开始 → 那条推送里加一行「★ 本机例行任务：…」、通过的标题后面加「· ★ 本机例行任务」（2026-10-16 起；**不算没通过**：例行任务不下单；没有云端后备 → 说「补跑」；不另推；读不到桌面版的运行记录就不说；结果文件记 routines）→ 问「例行任务今天跑了吗」；同一天的「通过」只推一次（早些时候没通过、或那条没推到手机 → 再推）；**哪个工作日 09:30 左右没收到 → Mac 多半关机 / 睡着 / 断网**（那时推不出来；睡着 → 醒来之后才推）；推送没发成 → 60 秒后自动重推一次，还不行 → 面板顶部 / 菜单栏 ★（当天不再自动推：「再自检一次」才再推） |
| 执行器这次跑成没有 / 再试一次 | 「刚才执行器跑成了吗」「面板说今天的单没下」「盘中自动下单为什么暂停了」「再试一次」 | 面板 / 手机每个账本顶部的运行状态；读 `~/.qbreak/home/out/live_unified_{paper,tachibana}_run.json`（at / phase / ok / error / blocked / bad_orders）；盘中面板叫的执行器连续失败 3 次 → 当天暂停自动叫（看 `~/.qbreak/home/logs/com.qbreak.panel.*`；2026-10-14 起暂停时手机 + Mac 通知一次、记在 `~/.qbreak/home/state/panel_trigger.json`，面板重启也接着停），写新的手动指令、执行器之后跑成一次或第二天恢复；「再试一次」→ Claude 先跑 `bash scripts/liveu.sh manual list --broker <账本>` 告诉你会下什么，再跑 `bash scripts/liveu.sh run --broker <账本> --phase now`（盘中）/ `--retry`（开盘前）；模拟账户成交日 09:25〜11:30 的开盘撮合（2026-10-15 起面板自动叫）没做成 / HALT 中等开盘后的买单没下、11:30 之前解除了 → `bash scripts/liveu.sh run --broker paper --phase open`（不跑 → 第二天早上照旧撮合 / 记为没买） | 只读；状态不明的单 → 你先在立花的注文一覧核对，再在 Mac 对话里登记（下面「状态不明的单」） |
| 开机后补跑了吗 | 「今天开机后模拟操盘补跑了吗？」 | 读 `~/.qbreak/home/logs/com.qbreak.login.out`；`launchctl list \| grep qbreak` | 只读；立花本番不在登录时补跑 |
| 闲置资金 / 股债相关判定（BCU） | 「美股熊市的时候闲置资金会拿什么？」「股债相关现在是多少？」 | 读 `~/.qbreak/home/bond_refuge.json`（日报例行任务入库、执行器同步来的判定：on / since / corr / corr_date / us_bear / hold / bond_date）与 `~/.qbreak/home/out/live_unified_paper_journal.md` 里「闲置资金」那一行；页面标「★ 本机现算」时看 `git -C ~/qbreak-src log -1 -- quant_breakout/var/bond_refuge.json` 日报例行任务那天写了没有 | 只读；改回 "Q1H"（美股熊只拿现金）要你明确说、在 `~/qbreak-dev` 改 `var/sim.json` 并记 sim_changes |
| 影子账户（判断型；2026-10-24 停用） | 「影子账户今天怎么样？比规则账户好吗？」 | 记录停在 2026-10-23；读 `var/out/shadow_today.json`、`var/out/shadow_equity.csv`（例行任务每天记）；中间统计 `python scripts/shadow_account.py evaluate --interim` | 只读；判断只在例行任务（Mac 的本机任务）里做 |
| 前向记录进度 | 「前向记录记了多少？X6 吊灯止损现在怎样？」 | `git -C ~/qbreak-src pull --ff-only` 后 `env -u QBREAK_HOME ~/.qbreak/venv/bin/python scripts/score_forward.py --status`（在 `~/qbreak-src/quant_breakout`，读仓库里日报例行任务每天追加的记录；不联网、不写文件）；详细结果读季度复核的 `var/out/score_forward_review.md`、`w2_forward_all_review.md`（全市场：W2 / K2 / USW / X6 / R4 / 第十节 HWN・X2G・JRM / 第十一节趋势线 TQ08） | 只读；判定只在季度复核里做 |
| VCT 前向记录 | 「VCT 今天有没有急跌信号？前向记录记了几天？」 | `git -C ~/qbreak-src pull --ff-only` 后 `env -u QBREAK_HOME ~/.qbreak/venv/bin/python scripts/vct_forward.py --status`（在 `~/qbreak-src/quant_breakout`，读日报例行任务每天追加的 `var/out/vct_forward.csv`；不写文件）；也可看日报「VCT 前向记录」卡片 | 只读 / 只展示，不改交易 |
| 深跌前向记录 | 「日経离 −15% 还有多远？深跌前向记录记了几个？」 | `git -C ~/qbreak-src pull --ff-only` 后 `env -u QBREAK_HOME ~/.qbreak/venv/bin/python scripts/deepdip_forward.py --status`（在 `~/qbreak-src/quant_breakout`，读日报例行任务每天算好的 `var/out/unified_today.json`；不联网、不写文件）；也可直接看日报「深跌前向记录」一栏 | 只读 / 只展示，不改交易 |
| 接下来要检查什么 | 「这个月 / 接下来要注意什么？」「什么时候判定 W2？」 | 读 `CHECK_TIMELINE.md` 与日报「检查日历」（`var/out/unified_today.json` 的 calendar） | 只读 |
| 股票被踢出了吗 | 「要下单 / 手上的股票有没有被踢出日経225、被指定特別注意？」 | `QBREAK_HOME=~/.qbreak/home ~/.qbreak/venv/bin/python run.py eligibility`（在 `~/qbreak-src/quant_breakout`） | 只读；名单差异要改名单 → 你确认后在 `~/qbreak-dev` 改（`qbreak/universes.py`，记 sim_changes） |
| 谁快退市了 | 「哪些股票快退市了？最終売買日是哪天？股票池更新了吗？」 | `QBREAK_HOME=~/.qbreak/home ~/.qbreak/venv/bin/python run.py delist-schedule`（在 `~/qbreak-src/quant_breakout`；`--offline` 不重取）或看日报「股票池更新时间表」 | 到了上場廃止日自动从股票池去掉（只减）；补入要你确认；持仓不自动卖（要卖先 HALT） |
| 数据对不对 | 「研究 / 模拟盘用的数据对不对？缺什么？」 | 读 `var/out/data_audit.md`（每项 OK / 注意 / 问题 / 缺 与用在哪里）；重跑：季度复核 3b 自动做；手动在 `~/qbreak-dev` 里 `bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python scripts/data_audit.py --warm`（约 5〜15 分钟） | 只读；修正要另记 sim_changes |
| 行情有没有错位 | 「今天的行情和 J-Quants 对得上吗？」「有没有复权错位？」 | 读 `var/out/unified_today.json` 的 price_check（日报例行任务每天）；Mac 上现查：`QBREAK_HOME=~/.qbreak/home bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python run.py price-check`（在 `~/qbreak-src/quant_breakout`，约 2 分钟） | 只读、只报警；告警的票在买单 / 持仓里 → 先核对哪边对，要停就建 HALT |
| 成本 × 销售 | 「现在原材料在涨吗？哪些业种偏间接？」 | `~/.qbreak/venv/bin/python scripts/cost_sales_forward.py --show`；进度 `--review` | 只展示；行业层，不是个股建议 |
| 买卖时间线 | 「明天 / 这几天买卖什么？」「7203 收在多少会卖？」「候补哪天可能出买点？」 | `git -C ~/qbreak-src pull --ff-only` 后读 `var/out/unified_today.json` 的 timeline（或账本页面「买卖时间线」一节）；决算形态在同一文件的 earn_state | 只读 / 只展示；价位是现行规则的翻译，情景推算不是预测；不给买卖指令 |
| 持仓离收盘卖出线还有多远 | 「持仓离收盘卖出线还有多远」「今天盘中持仓会不会触发卖出」 | `bash scripts/liveu.sh intraday`（只读：读操作面板的线程最近一次算的 `~/.qbreak/home/out/intraday_{paper,tachibana}.json`：持仓每条收盘卖出线离现价多远、越过了 = 若收盘仍在这里 → 规则下一个开盘卖；核心 ETF 今天的涨跌；Yahoo 1 分钟线约晚 20 分钟）；现在算一次、只打印（不写、不推送）：`bash scripts/liveu.sh intraday --dry`；手机推送开 / 关：`bash scripts/liveu.sh intraday push on|off`（数据目录 intraday.json，默认开）；页面：面板「持仓」每只一行；日志 `~/.qbreak/home/logs/com.qbreak.panel.intraday.log`（2026-10-16 起；选股页「今天盘中：规则的买点」卡片与暂定买点的推送 2026-10-18 用户「没什么用」删掉） | 只展示 + 手机提醒，不下单、不改规则；暂定（以明早 07:40 执行器为准）；交易日 08:55〜11:35、12:25〜16:30 由操作面板每 5 分钟算一次（没有单独的 LaunchAgent：面板没开 / Mac 睡着 → 暂停）；推送：持仓数据 14:10 之后越过收盘卖出线，同一只一天一次、每个账本一天最多 5 条、数据过期（> 30 分钟）/ 取不到不推；盘中手动买卖没有研究支持（分钟 K 线研究 2026-10-15：日内规则扣成本后都亏） |
| 持仓有没有出卖出信号 | 「持仓出卖出信号了吗」「哪只要被卖」「明天开盘会卖什么」 | 操作面板「持仓」最上面「★ 持仓出了卖出信号」（没有就不显示；2026-10-18）：规则已经判卖的（`state.pending_exit`，你自己写的卖出 / 减仓不算）写哪天 09:00 开盘卖 + 那笔单现在怎样；盘中 / 收盘后越过收盘卖出线的写「盘中暂定」（那根 K 线执行器决策过就不再写）；对话里：`curl -s "http://127.0.0.1:8765/api/intraday?book=paper"` 的 `sell`（立花 `book=tachibana`） | 只展示；执行器照常在开盘卖、不需要操作；「盘中暂定」约晚 20 分钟、收盘前还会变，以下一次决策（交易日 07:40）为准；要不要停是用户自己的决定（停 = HALT） |
| 买点 / 卖点的推送 | 「出买点 / 卖点会推送吗」「为什么没收到买点推送」「买卖点推送推了几次」 | 执行器早上的决策（交易日 07:40）之后，新出现的买点（候选里 status = triggered，后面写已安排 / 规则不买的理由）与卖点（`pending_exit` 里规则判卖的；手动卖出 / 减仓不算）合成一条推送「qbreak 模拟操盘 / 立花实盘：买点 N 只、卖点 N 只」（`qbreak/signal_push.py`，2026-10-18）；同一只同一方向只推刚出现的那次（连续几天的信号只推第一天、重试不重推），记录在 `~/.qbreak/home/out/signal_push_<账本>.json`；看推过什么 → 面板「消息 → 通知记录」；盘中暂定卖点（14:10 之后，`liveu.sh intraday push on|off`）照旧另推 | 只是通知；执行器照常处理；HALT 中写明不会下单 |
| 出过买入信号的票 / 删除 | 「选股里以前出过信号的票怎么删」「过了买点的票为什么还在」 | 选股「规则接下来会自动买」的「以前出过买入信号」：出过 triggered 的票一直留着，直到点那一行的「删除」（先出确认框；`qbreak/signal_keep.py`，记录 `~/.qbreak/home/out/signal_keep_<账本>.json`，2026-10-19）；删除只是不显示这一次信号，之后再出新的信号会再显示 | 只是展示；规则照旧买 / 不买 |
| 通知记录分账本 | 「本番的通知记录里怎么有模拟的」「立花登录的推送在哪里」 | 面板「消息 → 通知记录」只显示这个账本的 + 共通的（经济威胁等，带「共通」标签）；模拟的在模拟账户页、立花本番的（含每次本番登录）在立花页（`notify.book_of`，2026-10-19） | 通知照发，只是分开显示 |
| 看今天的情况 | 「今天模拟操盘怎么样？」「现在持仓和下一开盘的单是什么？」 | `bash scripts/liveu.sh --broker paper --status`（立花上线后 `--broker tachibana`），读页面与日志 | 只读 |
| 市场偏向 / 威胁消息 | 「现在偏向哪边？」「有什么经济威胁消息？」 | `bash scripts/liveu.sh news --open`（仪表盘重写并打开），读 `~/.qbreak/home/cache/news/news.json` | 只读；每条的来源只写国家（`qbreak/news_country.py`，认不出 = 不明；2026-10-19） |
| J-Quants 今天的新数据 | 「持仓 / 候补最近有决算吗？」「今天有哪些予想修正？」 | 读 `~/.qbreak/home/out/jq_today.json`；要马上取：`bash scripts/liveu.sh jq` | 只读；キー不回显 |
| 和云端对账 | 「今天和云端一致吗？不一致为什么？」 | 读日志的比较行（两边持仓、现金、权益差；「云端」= 日报例行任务的模拟盘） | 只读；2026-10-19 起只作参考、不是上线门槛；模拟账户有手动指令时不一致是预期的 |
| 每年交易多少笔 / 都买哪些股票 | 「现在每年大概交易多少笔？」「都买哪些股票？」 | `git -C ~/qbreak-src pull --ff-only` 后读 `var/out/b3_trades_summary.md`（现行规则 B3 在三个年代回测里的每年笔数、常买的股票与业种；2026-10-04 起）；现在离买点近的票看日报的候补队列 | 只读 / 只描述；回测不是预测；重算 `python scripts/b3_trades_summary.py` 在 `~/qbreak-dev` 做（约 5 分钟）；换本金看：`--capital 2000000` → `var/out/b3_trades_summary_cap2000000.md`（2026-10-04 起） |
| 为什么没买 / 为什么卖 | 「为什么今天没买 7203？」 | 查日志的 blocked / skipped（一手太贵、名额满、跳空 > 3%、决算前等） | 只读 |
| 立花连得上吗 | 「检查立花连通（只读）」「用デモ环境检查」 | `bash scripts/liveu.sh probe [--demo]`（= `run.py tachibana-probe`：登录、取价、持仓、余力、注文一覧、立花銘柄マスタ；结果记在 `~/.qbreak/home/out/tachibana_probe_{live,demo}.json`，没有金额与密钥，2026-10-09 起也记 API 版本段）；デモ一天的发单检查 `probe --demo --order-test`（2026-10-09 起多测执行器最常用的「寄付指値买」受理 + 按注文番号撤单） | 本番不发单；デモ才发单；交易时间里取不到现价 / 盘外连前日終値都没有 = NG（字段名可能不对）；API 版本变了 → 上线门槛要求重做 |
| 能上实盘了吗 | 「能上实盘了吗？」「上线门槛满足了吗？」 | `bash scripts/liveu.sh gate`（= `run.py live-gate`）：门槛 ②〜④（① 连续 10 天一致 2026-10-19 起不算门槛、只在【参考】里写比较情况）：没有状态不明的单、HALT 演练、デモ几点 + 寄付指値买）+ 准备（本番只读检查、本番 dry-run 跑通过、钥匙串 / 私钥 600、doctor、定时任务、自动唤醒、Mac 的时区是日本、⑧ 手机通知 / 每天的自检推送（2026-10-14 起代替外部心跳）/ 09:30 自检）+ 参考（ARM 三种状态：已解锁 / 未解锁 / 文件在但内容不是 ARMED） | 只读：不下单、不改文件、钥匙串只查有没有 |
| 环境自检 | 「做一次环境自检」「doctor」 | `bash scripts/liveu.sh doctor`（= `run.py doctor`：Python / 依赖 / 外网 / yfinance；结果记在 `~/.qbreak/home/out/doctor.json`，gate 的「准备」读） | 只读；不打印密钥 |
| 行情取不到 / 升级 yfinance | 「升级 yfinance」（通知 / 面板出现「★ 行情：…修法：…」时） | `~/.qbreak/venv/bin/python -m pip install -U yfinance`（或 `bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh --upgrade-yfinance`）→ 汇报升到的版本；之后再跑 `mac_setup.sh` 会按 `requirements.lock` 装回锁定的版本 → 新版本修好了的话在 `~/qbreak-dev` 把 lock 里的 yfinance 也改掉、测试、推送 | 不改用 J-Quants 代替（数据源不同会让决策和模拟盘不同，属于规则，要你另外决定）；行情落后的那天立花不下单（规则卖单也不下），持仓的离场判断被跳过会写在通知 / 面板上 |
| HALT 演练 | 「做一次 HALT 演练」 | `bash scripts/liveu.sh halt-drill`：模拟账户今天早上的运行完成之后（收盘前或休市日）建演练用的 HALT → 跑一次（不下单，账本记下）→ 删掉它 | 只删它自己建的演练 HALT；真的 HALT 已经存在就不演练 |
| 入金 / 出金 | 「我入金了 30 万」「出金 10 万」 | `bash scripts/liveu.sh flow 300000 --flow-note 入金`（出金写负数；默认立花的账本） | 只影响收益的计算与提醒，不下单；下单本来就按立花的买付可能額 |
| 早上没跑 / Mac 睡着了 | 「今天早上执行器跑了吗？」「为什么 09:05 没补单？」 | 读 `~/.qbreak/home/logs/com.qbreak.liveu.{morning,retry,open,open2}.out`、`launchctl list \| grep qbreak`、`pmset -g sched` | 只读；08:35 / 09:20 的重试只在前一次没跑完时才跑 |
| 立花 API 要更新吗 | 「立花 API 要更新吗？」（日志 / 页面出现「★ 立花通知」时） | 看通知里的发布日，查 e支店 API 的公告与新仕様書，对照 `~/.qbreak/home/tachibana_spec.json` 与适配器 | 改代码在 `~/qbreak-dev` 里做、测试全过才推；核对完不用更新 → 用户确认后 `bash scripts/liveu.sh precheck --ack-api <日子>`（只清这个提醒） |
| 政策事件库（G1） | 「日银今天决定加息了，录进政策事件库」「最近的政策事件反应怎么样？」「哪些会合还没分类？」 | 在 `~/qbreak-dev` 里 `bash scripts/liveu.sh policy add --category BOJ_CHANGE --subtype tighten --date 2026-10-30 --source <日银官方 URL> --name-ja … --checked 2026-10-30`（美国主场用美国当地日期；MOF_FX 要 `--confirmed-same-day` 或 `--covert --known-on 月次公表日`）→ `git add var/policy_events.csv && git commit -m … && git pull --rebase && git push`；看：`bash scripts/liveu.sh policy list`、`policy tocheck`、日报「政策事件反应库」块、`var/out/policy_forward_review.md` | 只改事件表、只展示 + 前向记录，不下单；日报例行任务的 sim-day 是前向记录唯一写者 |
| 演练 | 「用 dry-run 看今天实盘会下什么单」 | `bash scripts/liveu.sh --broker tachibana --dry-run --no-clock` | 登录与读取照常，单只打印 |
| 开始实盘 | 「我确认开始实盘，创建 ARM」 | `echo ARMED > ~/.qbreak/home/ARM` | 只在你这次明确说时；先满足路线图 4 的上线门槛 |
| 停止下单 | 「停」「今天不要下单」 | 立刻建 `~/.qbreak/home/HALT`（买卖都不下，持仓不动） | 恢复要你明确说「恢复下单，删除 HALT」；删之前 Claude 先跑 `bash scripts/liveu.sh manual list --broker <账本>`（有账本的都看）告诉你 HALT 期间等着的手动指令与写于哪天（解除后照原样执行，不要的先撤回；2026-10-13 起页面 HALT 卡片、`manual list`、解除后第一次运行的通知也列出来） |
| 不在 Mac 旁边要停 | 在云端（手机）的 Claude 对话里说「停」「今天不要下单」 | 云端立刻 `python run.py remote-halt --reason "<你的原话>"` → 提交推送 `var/HALT_REMOTE` → Mac 的执行器下一次运行（07:40 / 08:35 / 09:05 / 09:20）建本地 HALT | 已经发到交易所的单不撤（要撤：在 Mac 对话里说「撤单」、面板「今天要成交的单」的「撤单」，或立花网站 / 手机网站）；同一个 id 只生效一次；恢复只在 Mac 上明确说 |
| 状态不明的单 | 「U2026-10-01-BUY-7203.T 在立花网页上是成交 100 股 3,001 円」 | `bash scripts/liveu.sh --broker tachibana --resolve … --filled 100 --px 3001` | 你先在立花的注文一覧看过；没成交就说「没成交」 |
| 状态不明的单的候选 | 「状态不明的那笔在立花是什么情况？」「执行器因为状态不明停下了」 | `bash scripts/liveu.sh unknown --broker tachibana`（只读：立花注文一覧里同代码、同买卖、股数相同或更少的单，按受付时刻接近排序，附登记命令草稿）；执行器停下时候选也写在通知、运行状态与面板上 | 登记（`--resolve`）只在你看过、这次明确说之后；还挂着的单等它成交 / 失效（或撤掉）之后再登记成交数 |
| 撤单 / 停并撤单 | 「撤掉 7203 的单」「把今天立花还挂着的单都撤了」「停，并且撤单」 | 先说清楚撤哪几笔（`bash scripts/liveu.sh --broker tachibana --status` 看今天的单）→ `bash scripts/liveu.sh cancel [<cid>…] --broker tachibana`（不带 cid = 今天全部还挂着的执行器单）；停并撤单 = `bash scripts/liveu.sh halt-cancel --broker tachibana`（先建 HALT 再撤全部）；面板 / 手机「今天要成交的单」的「撤单」按钮做同一件事（写撤单指令，面板马上叫执行器撤）；2026-10-15 起执行器排好、还没发出的单（计划 / 等开盘后；2026-10-17 起还有被挡、08:55 之前还会再发的）也能撤（= 执行器不再发，不连券商）；2026-10-17 起还没下的都在那一行撤：还没照它调的固定口数 / 还差几口 →「不补了… / 撤回…」（固定成现在的口数 = 预计不买不卖 / 改回上一次照它调的 / 恢复按规则，之后照旧有「确认下单」框）、还没照它调的闲置资金比例 →「撤回…」（改回上一次照它调的比例），还没读的指令照旧「撤单 / 撤回」；下一次决策规则自己的单那时才排出来 → 要停用 HALT 或 07:40 之后、09:00 之前撤单；撤凑钱的卖单之前先说清楚靠它的钱的买单（面板确认框三选一「一起撤买单」「只撤卖单」「撤单并恢复按规则」；「一起撤买单」写了之后执行器就不再发靠这笔卖出的钱、等开盘后的买单；命令行：不在一组里的凑钱卖单 = 只撤卖单，买单按现在的钱重算（`cancel-plan` 先写照常 / 减股 / 不会下）；一组里的卖单在同一组的买单还挂着 / 已成交时默认不撤（只撤卖单 `--solo`、整组撤 `--group`，先用 `cancel-plan` 看））；整组撤单（2026-10-16 起：一起下的买单和卖单一起撤）：先 `bash scripts/liveu.sh cancel-plan <cid> --broker …`（只读，看会撤哪些）→ 用户说撤才 `bash scripts/liveu.sh cancel <cid> --group --broker …`（先撤买单，确认没成交再撤卖单；买单已成交 / 撤不掉 → 卖单不撤） | 只在你这次明确说「撤单」时运行；只撤执行器自己今天还挂着的单（已经成交的部分撤不了，照成交记账）；撤之后会怎样按单的来源说（2026-10-15 起）：规则的卖单明天还要卖会再下、撤掉的个股买单不再买、核心 ETF 下一次决策照规则 / 闲置资金比例重新算（可能再买 / 再卖）、固定口数排的单 → 固定口数仍有效、下一次决策还会再排（要停 = 「恢复按规则」）；撤了凑钱的卖单 → 靠它的钱的买单照常 / 减股 / 不会下（面板的撤单：不会下 / 减股 → ★ 交易 推送；命令行只打印在终端、不推送，Claude 在对话里告诉你），盘中为手动买入凑钱的核心卖单被撤 → 那条买入默认一起撤回；手动指令的单被撤 → 那条指令也撤回；HALT 时也能撤；立花网站 / 手机网站（https://kabuka.e-shiten.jp/mfds_smp.php）也能撤 |
| 整组撤单 / 一起撤 | 「一起下的买单和卖单一起撤」「把 1545 那一组都撤了」 | 先跑只读的 `bash scripts/liveu.sh cancel-plan <cid> --broker tachibana`（不连券商、不改账本：这笔单所在的一组每一笔会怎样——撤 / 已成交 / 撤不了、撤之后靠它的钱的买单、固定口数），把组员（代码带名字、股 / 口）告诉用户 → 用户明确说撤再跑 `bash scripts/liveu.sh cancel <cid> --group --broker tachibana`；面板 / 手机「交易」里同一组的行有「同一组 N 笔」（分在「今天要成交的单」与「已结束 / 不是今天的」两处也一样），点「撤单」→ 确认框「整组撤单（N 笔）」做同一件事 | 只在你这次明确说「撤单」时运行；先撤买单、确认没成交再撤卖单；买单已经成交 / 撤不掉 → 卖单不撤（面板的撤单 ★ 交易 推送；命令行只打印在终端、不推送）；靠这一组卖单的钱、已经发到交易所的买单（不是一起下的，例：规则的买单）也算进这一组、一起先撤，已经成交 → 卖单不撤；立花买单的撤单还没确认 → 卖单先不撤，约 1 分钟后再查、最多 10 分钟（命令行：开始等的时刻记在账本里，过 1 分钟再运行同一条命令接着查、不再发撤单，这时 cancel-plan 写「再运行会接着查那一条」；面板也会约 1 分钟后自动再查，由面板做完的推一条、单的说明写「命令行写的，面板自动再查」，之后再跑同一条命令写「已经由面板的自动再查做完」；10 分钟到了给立花网站的链接）、收盘前 3 分钟（15:27）起不再等；单笔撤一组里的卖单、同一组的买单（含靠这一组卖单的钱、已经发出的买单）还挂着 / 已成交 → 默认不撤卖单（用户明确说只撤卖单 = `liveu.sh cancel <cid> --solo --broker tachibana`，面板确认框「只撤这笔卖单」）；固定口数不会自动取消（要停 = 「整组撤单并恢复按规则」）；同一组同时只有一个撤单：还有撤单在处理（面板 / 手机写的在等也算；命令行自己在等的那一条除外 = 接着查）→ 预览写「这次什么都不撤」+ 是哪一条在撤，命令行也不撤（等它结束再跑）；一条命令点了彼此有关的几组（同一笔买单靠两组卖单的钱）→ 先写的那组做、其余写「这次不撤」+ 理由 |
| 持仓核对 / 人工代下登记 | 「立花的持仓和账本对得上吗」「为什么说持仓不一致」「API 坏了，我在立花网站上照单买了 7203 100 股 2,500 円，登记一下」 | 看：`bash scripts/liveu.sh reconcile --broker tachibana`（只读：逐只账本 vs 立花的股数 / 成本、执行器不管的持仓、拆股登记、今天的单、可能原因、登记草稿）；登记：`bash scripts/liveu.sh adopt --broker tachibana 7203 BUY 100 2500 [--date YYYY-MM-DD] [--note …]`（先备份账本；新仓的止损按引擎的新仓算法；名额满 / 不是一手的整数倍 / 不在股票池 / 日期在未来 → 拒绝）→ 再 reconcile 看一致了没有 | adopt 只在你这次明确说、并给出实际成交数与均价（立花「約定照会」）时运行（与 `--resolve` 同级）；执行器自己的单（含状态不明的）不要当成人工代下登记 |
| 账本备份 / 恢复 | 「账本坏了」「执行器说账本读不了」「把立花的账本恢复到今天早上那份」 | 看：`bash scripts/liveu.sh restore --broker tachibana --list`（只读：每份备份的时刻、决策日、现金、持仓）→ 你选一份 → `bash scripts/liveu.sh restore --broker tachibana <备份文件名>`（先把现在的账本也备份一份、拿运行锁、账本记一条事件） | 恢复只在你这次明确说、指定了哪一份时运行（与 `--resolve` 同级）；恢复之后先 `reconcile` 看和立花一致没有；备份每次执行器运行开始时自动做（留最近 60 份）；模拟账户用 `--broker paper` |
| 前一晚预检 | 「昨晚的预检过了吗」「明天立花能登录吗」「交付書面要读吗」「再预检一次」 | 看：面板顶部、`~/.qbreak/home/out/precheck_tachibana.json`（at / ok / reasons / 预告）、`~/.qbreak/home/logs/com.qbreak.precheck.out`；「再预检一次」→ `bash scripts/liveu.sh precheck`（没装立花本番 → 什么都不做；`--force` 照做） | 只读（登录 → 取余力 → 登出，不下单、不改账本）；会登录立花一次（可能收到一封登录通知邮件）→ 只在你要时手动跑；交付書面未読 → 你在电脑上登录 e支店网站读完 |
| 换 Mac | 「换 Mac」「新 Mac 上执行器说账本是另一台 Mac 的」 | 照 MACOS.md §1.14：旧 Mac HALT + 卸载立花的任务 → 拷数据目录 `~/.qbreak/home` 与私钥 `~/.qbreak/e_api_private_key.pem` → 新 Mac `mac_setup.sh`、钥匙串你自己重新存 → 你明确说「换 Mac，账本归这台」→ `bash scripts/liveu.sh adopt-host --broker tachibana` → `probe` / `reconcile` / `install_launchd_live_u.sh tachibana` / `gate` | `adopt-host` 只在你这次明确说时运行（与 `--resolve` 同级）；确认旧 Mac 不再运行之前不要做（两台 Mac 同时跑会重复下单） |
| 上线头几天看什么 / 退出实盘 | 「上线头几天要看什么」「不做实盘了，回到模拟」 | 读 MACOS.md §1.6「上线头 5 个交易日的值守清单」「退出实盘 / 回到模拟」，按你的回答一步步做 | 退出里的每一步（撤单、手动卖出、删 HALT / ARM、卸载、移走模拟账本）都按各自的规则要你明确说；卖不卖是你的决定，Claude 不建议 |
| 最后停止手段（Mac 失控 / 联系不上） | 「Mac 联系不上，怎么让它不再下单」「彻底关掉立花 API」 | 告诉你 MACOS.md §8「最后停止手段」：你自己登录立花网页 → お客様情報 → 設定情報 → ｅ支店・API 利用設定 →「無効化」（API 马上失效）；挂着的单在网页上撤 | Claude 不登录、不操作立花网站；恢复要在利用設定重新设置 → `probe` → `reconcile` → 你明确说才恢复下单 |
| 临时休市 | 「明天东证临时休市」「X 日东证系统故障全天停」 | 先找 JPX 官方公告核对（写日期与来源）→ 你确认后 `bash scripts/liveu.sh closed add YYYY-MM-DD --note …`（数据目录 `extra_closed.json`）；看：`closed list`；取消：`closed rm YYYY-MM-DD` | add / rm 只在你这次确认后运行；只写 Mac 的数据目录（仓库里不放）；长期的新休日照旧改 `qbreak/calendar_jp.py` |
| 零股（不足一手） | 「7203 有零股是怎么回事」「零股在网站上卖了，30 股 2,480 円」 | 拆股 / 合并后多出来的不足一手的股数用 API 的普通注文卖不掉 → 你在立花网站卖（端株手续费 0.55%）→ 你说了实际股数与均价 → `bash scripts/liveu.sh adopt --broker tachibana 7203 SELL 30 2480` | adopt 只在你明确说、给出实际成交时运行 |
| 冒烟测试没过 / 异常熔断 / 错过寄付 | 「为什么说冒烟测试没过」「熔断是什么」「早上错过寄付是什么意思」 | 冒烟测试：读 `~/.qbreak/home/logs/smoke_test.log` → 在 `~/qbreak-dev` 修好、测试全过再推；熔断：`bash scripts/liveu.sh --broker tachibana --status` 与日志找原因；错过寄付：MACOS §1.6「运行保障」（个股卖单改开盘后当日限价卖、买单今天不下） | 冒烟测试没过 / 熔断的那次单都没下（对账 / 决策照常）；熔断正常运行不会出现 → 先建议你说「停」 |
| 改了第二暗証 / 换密钥 | 「我在立花改了第二暗証番号」「换了公钥」 | 请你自己在终端 `security add-generic-password -U -s qbreak-tachibana-2nd -a qbreak -w`（回车后输入，不显示；认证 ID 用 `-s qbreak-tachibana-authid`；私钥放回原路径 `chmod 600`）→ `bash scripts/liveu.sh gate`（⑥ 用和定时任务相同的读法试读一次，只报能不能读出） | 密码 / 密钥不贴进聊天；Claude 只说有 / 没有（MACOS §3） |
| 手动卖出 / 减仓 | 「卖掉 7203」「7203 减到 10%」「立花的 7203 卖掉，之后一直不买回」 | 先说清楚哪个账本、什么时候成交（盘中 = 马上、开盘前 = 今天开盘、收盘后 = 下一个交易日开盘；`manual list` 显示）、卖出后几天不买回 → `bash scripts/liveu.sh manual sell 7203 [--block-days 20\|0\|-1] [--broker tachibana]`、`manual trim 7203 --pct 10`；面板开着时它自己叫执行器（交易日 07:45〜08:55 `--retry`、盘中 `--phase now`），没开时：开盘前 `bash scripts/liveu.sh run --broker paper --retry`、盘中 `bash scripts/liveu.sh run --broker paper --phase now`（立花 `--broker tachibana`） | 只写指令，下单由执行器做（HALT / ARM / 持仓核对照常）；没说账本 = 模拟账户（会和日报例行任务的模拟盘不一致，只作参考）；立花要你说「立花」；只能卖 / 减；盘中的单发出后可以撤（下面「撤单」） |
| 调整持仓（加 / 减） | 「7203 调到 300 股」「6758 加到 50 万円」「7203 调到 20%」 | 先说清楚哪个账本、预计卖 / 买几股、什么时候成交 → `bash scripts/liveu.sh manual adjust 7203 --shares 300`（或 `--yen 500000` / `--pct 20`；立花加 `--broker tachibana`）；`manual list` 看最早哪天开盘 | 少于现在 = 减仓；多于现在 = 加仓：开盘前说的进决策（寄付）、07:40 之后 / 盘中说的开盘后盘中马上买（现价超过收盘 ×1.03 不买）、钱不够先卖核心 ETF、单只上限 34%、资格 / 新仓倍数 0 / 决算前不加、只做一次；买还没拿的票用下一行「买入」；Claude 不主动建议加仓 |
| 买入（新开仓） | 「买 6501」「建议的股票里的 8035 买 50 万円」「按规则的仓位买 6501」 | 先说清楚哪个账本、按规则约几股、什么时候成交、这只有没有买入信号（`~/.qbreak/home/out/live_unified_paper.json` 的 suggest）→ `bash scripts/liveu.sh manual buy 6501`（按规则的仓位；或 `--shares 300` / `--yen 500000` / `--pct 20`；立花加 `--broker tachibana`）；`manual list` 看名额与最早哪天开盘 | 开盘前说的进决策（寄付）、07:40 之后 / 盘中说的开盘后盘中马上买（现价超过收盘 ×1.03 不买）、收盘后说的下一个交易日开盘、占名额（4 只满了先卖一只）、资格 / 立花能不能买 / 新仓倍数 0 / 决算前 / 不买回期内不买、单只上限 34%、只做一次；买入后按规则离场；没触发信号的票是用户自己的决定；Claude 不主动建议买哪只 |
| 闲置资金比例 / 核心 ETF 调仓 | 「闲置资金只放一半」「核心 ETF 先全部卖掉留现金」「1545 纳斯达克 100 调到 50 口」「改回照规则」 | `bash scripts/liveu.sh manual core --pct 50`（0 = 卖出留现金并停买；100 = 照规则）；拿着的 ETF 也可以 `manual sell 1545` / `manual adjust 1545 --shares 50`（换算成比例；固定口数的 ETF 改的是它的固定口数，2026-10-13 起） | 盘中说的马上照新比例调（盘中的核心 ETF 买入限价 ≤ 决策日收盘 ×1.02，现价更高 → 这次不买、10 分钟后再试；2026-10-15 起）、开盘前 / 收盘后说的进下一次决策（这一次不看再平衡带）；之后每天按这个比例；比例对全部核心 ETF 一起生效（同时拿两只时另一只也跟着变，写之前告诉用户；固定口数的 ETF 不跟着比例变）；只改核心 ETF 的目标额；卖出全部 / 0% 之后停买：出现买入信号只提醒（下一行） |
| 核心 ETF 固定口数 | 「1482 对冲版美国 7〜10 年国债 固定 678 口」「1545 纳斯达克 100 买 50 万円」「1482 对冲版美国 7〜10 年国债 恢复按规则」 | 先说清楚哪个账本、调到几口（要卖 / 买几口、钱不够先卖哪只没固定的核心 ETF）、什么时候下 → `bash scripts/liveu.sh manual corefix 1482 --units 678`（或 `--yen 500000`；恢复按规则 `--clear`；立花加 `--broker tachibana`）；`manual list` 看什么时候下 | 2026-10-15 起与买卖同一个时段口径：盘中说的马上按现价（模拟账户当场成交）、早上的决策之后的开盘前 / 午休说的 09:00 / 12:30 开盘后马上（按现价限价，不是寄付）、决策之前说的进那次决策（寄付）、15:25 之后 / 休市日说的进下一次决策（写具体日期）；盘中买入限价 ≤ 收盘 ×1.02；同一只还没发出的旧单被新的固定口数取代、交易所还挂着的单先等它成交 / 撤掉；HALT 中不下（回执写明 HALT）；之后不再按规则（牛熊 / 股债相关）自动调，直到「恢复按规则」；用户在这次对话里明确说才写；模拟账户的手动操作会让它和日报例行任务的模拟盘不一致（只作参考） |
| 停买后恢复买 ETF | 「确认买入」「闲置资金 ETF 出现买入信号了，买吧」「恢复买 ETF」「停买状态怎么样」 | 看：`bash scripts/liveu.sh manual list`（停买从哪天起、有没有买入信号、规则现在想拿哪只约几口）；恢复：先告诉用户会买哪只约几口、什么时候下单 → `bash scripts/liveu.sh manual core --pct 100`（立花加 `--broker tachibana`；只买一部分 = `--pct 50` 等） | 用户在这次对话里明确说才写；Claude 不主动建议恢复；盘中说的马上照规则买、开盘前 / 收盘后说的进下一次决策；规则现在不拿 → 确认后不会马上买、之后规则转为拿时自动买（2026-10-13 起写明）；「全部换成」停的 → 告诉用户之前的比例 / 固定口数（固定口数不自动恢复）；模拟账户的手动操作会让它和日报例行任务的模拟盘不一致（只作参考） |
| 持仓现在的价 | 「7203 现在多少钱」「持仓现在涨了多少」 | 操作面板每只持仓下面的「现价」一行；对话里：`curl -s "http://127.0.0.1:8765/api/quotes?book=paper"`（立花 `book=tachibana`） | 只展示；Yahoo 1 分钟线约晚 20 分钟，不是立花的价；盘中 60 秒缓存 |
| 现在卖能赚多少 | 「7203 现在卖出能赚多少」「全部卖掉的话收益多少」「1655 卖了赚多少」 | 操作面板点「卖出全部」看确认框（不点确认就不下单）；对话里：`curl -s "http://127.0.0.1:8765/api/quotes?book=paper"` 的 `rows.<票>.est.lines`（立花 `book=tachibana`；面板没开 → 先照「操作面板」一行打开它） | 只是估算：现价约晚 20 分钟、实际成交价会不同、手续费按立花 個別コース、税按特定口座 20.315% 粗算；不是承诺；不借此建议卖或不卖 |
| 下单按什么价（现价晚 20 分钟怎么办） | 「页面的价晚了 20 分钟，卖的时候按什么价」「立花按什么价下单」「现在点卖会按多少成交」 | 操作面板每只持仓下面的「下单：…」一行；对话里：`curl -s "http://127.0.0.1:8765/api/quotes?book=paper"` 的 `basis.SELL` / `basis.BUY`（立花 `book=tachibana`） | 页面的现价（Yahoo）只用来看和估算；立花盘中按下单那一刻的实时现价挂限价（卖 −0.5%、买 +0.5% 且 ≤ 收盘 ×1.03）；模拟账户按 Yahoo 现价；盘外按开盘价。不承诺成交价 |
| 选股里的票现在多少钱 / 现在买的价 | 「8035 现在多少钱」「现在买 6501 大概多少」「选股的实时 K 线」 | 操作面板选股「规则接下来会自动买」里那只的「K 线 · 现价」（点开那一行就开着；2026-10-18 起选股页只有这一张卡，「建议的股票」不显示）；对话里：`curl -s "http://127.0.0.1:8765/api/quotes?book=paper&t=8035.T"` 的 `rows.<票>.buy`（lim = 现在买的限价、cap = 收盘 ×1.03、over = 现价已超过上限） | 只接受汇总里列着的候选（suggest.rows，页面上看不到的观察中的票也算）、没拿着的；规则的上限不是建议；买不买是用户自己的决定（Claude 不主动建议买哪只） |
| 哪只最快 / 最可能先出买入信号 | 「观察中哪只最可能买」「哪只最快出信号」「排第一的是什么意思」 | 先看选股最上面「规则接下来会自动买」：「已经出了买入信号」+「估计 5 个交易日内可能出信号」（按估计金叉的天数 → 历史比例排，不带名次）；其余的（观察中）2026-10-18 起面板不显示（用户：只留出了信号的与估计 5 个交易日内的）→ 要看就在对话里读汇总（历史比例 `var/watch_prob.json`，研究 `var/out/watch_prob_study.md`）；对话里读 `~/.qbreak/home/out/live_unified_paper.json` 的 suggest.rows（`status` / `near.days` / `prob.p`） | 天数是按最近一天的变化估算的；历史比例都很低（平均约 2〜3%，最高约 9%）；金叉之外还要量等条件凑齐，出了信号还要过闸门 / 名额；只是排序与展示，不是预测、也不是建议 |
| 闲置资金 ETF 什么时候会自动卖 | 「1545 什么时候会自动卖」「离转熊还有多远」「转熊后去现金还是 1482」 | 操作面板 ETF 卡片「什么时候会自动卖」：最上面三格（离转熊线 %、已确认 n / 5 天、转熊后 现金 / 1482）+ 全部卖 / 卖完去哪 / 部分卖 / 不会因为；对话里读 `~/.qbreak/home/out/live_unified_paper.json` 的 `market.US`（`to_flip_pct` / `confirm_days` / `flip_line`）、`idle_cash.bond_refuge`（`corr` / `on`）、`new_pos`（立花 `live_unified_tachibana.json`） | 只展示、按最近收盘（执行器早上 07:40 算）；规则只在 S&P500 连续 5 天收在 250 日均价 ×0.97 下时全部卖、没有止损；买新个股钱不够时部分卖；不借此建议卖或不卖 |
| 看 / 撤回手动指令 | 「手动指令处理了吗？」「撤回刚才的卖出」「7203 解除不买回」 | `bash scripts/liveu.sh manual list`；`manual cancel <指令 id>`；`manual unblock 7203` | 已经发到交易所的那一笔用「撤单」（下一行）撤；撤回只保证「之后不再重下」；解除不买回从下一次 07:40 决策起生效、不会马上买（「全部换成」卖出的一批在面板「交易」按批「恢复按规则」）；撤销撤回按现在的账本重查，对不上 → 请重新下（2026-10-13 起）；`manual list` 每条写什么时候下（具体时刻 / 日期，不再写「等执行器读」；2026-10-15 起）；写错的撤单（撤单指令）在撤单的运行做它之前也能撤回（面板那一行的「撤回」/ `manual cancel <撤单指令 id>`；之后那笔单照常挂着 / 照常发；撤单的运行已经在撤 / 做完、执行器正在运行 → 撤回不了，撤掉的单不会恢复；2026-10-16 起） |
| 今天还能买几次 / 卖几次 | 「今天还能买几次、卖几次」「今天还能做几次交易」「7203 今天还能卖吗」 | 面板「交易」页最上面的小卡「今天还能：买 N 次 · 卖 M 次 · 共 K 次」（展开看每只；持仓每只有小标记「今天还能卖 ✓ / 买 ✗（原因）」）；对话里：`bash scripts/liveu.sh manual list`（最后一段同样的内容）或 `curl -s "http://127.0.0.1:8765/api/trade_room?book=paper"`（立花 `book=tachibana`） | 只读、不下单、不是建议（只数「能不能」，不说该买哪只）；立花不限每天的下单次数，限制来自差金決済与执行器规则（下面「今天还能交易几次」一节）；2026-10-15 起 |
| 今天会不会下 / ★ 交易 提醒 | 「这笔单今天会下吗」「为什么说不会下」「收到『★ 交易』是什么意思」 | 面板「交易」页每行的状态与原因（`live_ops.outlook`：会下 / 已结束 / 今天不会下 / 之后某天）；对话里：`bash scripts/liveu.sh manual list --broker <账本>` 与 `bash scripts/liveu.sh --broker <账本> --status`、日志 `~/.qbreak/home/out/live_unified_<账本>_journal.md` | 只读；「★ 交易」= 有单 / 指令今天不会下（凑钱的卖单撤了 / 钱不够 / 被拒 / 盘中过了该下的时刻 10 分钟还没有执行路径 / 15:25 之后的汇总），level 是 warn（经济威胁提醒不变）；同一笔同一天只推一次；要不要补下是用户的决定 |
| 操作面板 | 「打开操作面板」 | `open "http://127.0.0.1:8765/"`（不带 `?book=` = 默认账本：装了立花本番 → 立花，否则模拟账户；指定 `?book=paper` / `?book=tachibana`）；打不开 → `launchctl list \| grep qbreak.panel`，没有就 `bash scripts/install_launchd_panel.sh` | 只在这台 Mac 上；按钮只写指令；立花本番的页面顶上有红色「真钱（立花本番）」；上线后模拟账户页标「已停」（那里写的指令不会被执行）；登录时打开的账本页面也跟着换成立花的 |
| 手机上操作（一条命令全部做完） | 「拉代码，手机操作全部执行」「打开手机操作」「手机上怎么用」 | `git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh --phone node`（拉代码 → 依赖与全部定时任务 → 重启操作面板 → Tailscale Serve 打开手机访问 → 在 Mac 上打开面板的「手机」）。`node` = 用户 2026-10-06 确认可以写进公开证书日志的 Tailscale 机器名：只有这台 Mac 的机器名正好是 node 才打开；名字不一样（退出码 3）→ 把显示的机器名告诉用户、用户同意后换成那个名字再运行；HTTPS 没开（退出码 4，已在浏览器里打开 Tailscale 管理页）→ 请用户点 Enable HTTPS 后再运行一次。打开之后：iPhone 的 Tailscale App 用和 Mac 同一个账户登录、Safari 打开手机地址就能用（2026-10-07 起按 Tailscale 账户登录，不用配对）；别的账户 / 带 tag 的设备才要请用户自己在 Mac 屏幕上点「生成配对码」、用相机扫码 | 只用 Tailscale Serve（只在用户自己的 tailnet），绝不用 Funnel；配对码只显示在 Mac 屏幕上：Claude 不调配对接口、不读、不在对话里写 |
| 手机配对的状态 | 「手机配对了吗？」「有哪些设备能打开？」「手机打不开」 | `bash scripts/liveu.sh phone status`（只读：Tailscale、Serve、手机端口、已配对的设备、按 Tailscale 账户登录 开 / 关，不含配对码、账户只显示打码后的）；手机打不开 → Mac 醒着吗、手机的 Tailscale 开着吗、`launchctl list \| grep qbreak.panel`、`~/.qbreak/home/logs/com.qbreak.panel.{out,err}` | 按账户登录开着、自己的 iPhone 还是看到配对页 → 手机的 Tailscale App 登录的是不是同一个账户、`phone status` 里账户登录是不是「开」（「现在不可用」/「设置是旧的」/「和记下的账户不一样」→ 再运行一次 `bash scripts/liveu.sh phone on`）；只用配对时：主屏幕上的网页要求重新配对 → 再生成一次配对码（主屏幕与 Safari 的 cookie 可能是分开的） |
| 手机只用配对 / 改回按账户登录 | 「手机只用配对」「手机按 Tailscale 账户登录」「手机不用配对」 | 只用配对：`bash scripts/liveu.sh phone identity off`；按账户登录：`bash scripts/liveu.sh phone identity on`；只看：`bash scripts/liveu.sh phone identity` | 用户在这次对话里明确说才改；账户名只显示打码后的、不写进仓库 / 对话；路径密钥不显示；Mac 上有别人的 macOS 用户账户 → 建议只用配对（第一次 `phone on` 也默认只用配对） |
| 取消手机配对 / 关掉手机访问 | 「取消 iPhone 的配对」「关掉手机访问」「手机丢了」 | 一台：操作面板「手机」里的「取消配对」（按账户登录的手机页面底部也能取消这台设备以前的配对）；全部：`bash scripts/liveu.sh phone forget`（按 Tailscale 账户登录也一起关掉）；关掉：`bash scripts/liveu.sh phone off`（已配对的设备保留） | 手机丢了：先 `phone forget`（立刻挡住），再请用户在 Tailscale 管理页 Machines 把那台手机删掉（Remove）；删掉之后才 `phone identity on`（那台手机还在 tailnet、还登录着你的账户时，打开按账户登录它就又能用） |
| 看 K 线 / 趋势 | 「看一下 7203 的 K 线」「6501 周 K 怎么样」「核心 ETF 月 K」「选股里有哪些」「哪只最快会出买入信号」「看 MACD / DMI」「趋势线 / 支撑压力在哪」 | 打开操作面板（Mac：`open "http://127.0.0.1:8765/?book=paper"`；手机：面板地址）→ 持仓 / 核心 ETF / 选股（「规则接下来会自动买」点开的行）下面的 K 线（「哪只最快会出买入信号」看上面「哪只最快 / 最可能先出买入信号」一行），每张图上边沿的「日K / 周K / 月K」与下边沿的「量 / MACD / DMI」各自切换（图下有日常说法的一句话；整页一份「怎么看 K 线图」在选股最下面）；对话里要数字就读 `~/.qbreak/home/out/charts_paper.json`（K 线、MACD / DMI、趋势线 `tf.*.tl`、趋势标签）与 `live_unified_paper.json` 的 suggest / kline | 只展示；数据是执行器最近一次运行写的，拿着的票盘中多一根「今天这一根」（Yahoo 1 分钟线合成，约晚 20 分钟；收盘后写「暂定」）；趋势标签是均线位置的机械描述；趋势线的延长不是验证过的预测（研究结果见 sim_changes / `var/out/trendline_study.md`、`var/out/trendline_select_study.md`：方向、破线、质地特征都没有信息） |
| 决算图 / 下次决算 | 「7203 最近几季决算怎么样」「下次决算什么时候」「会社予想进度多少」「决算图怎么看」 | 操作面板持仓每只、选股「规则接下来会自动买」点开的行里的小图（2026-10-18）：实线 = 最近 8 季的单季营业利润（银行等用经常利润），圆点红 = 同比增、绿 = 同比减；虚线空心点「予想」= 按会社予想摊算的下一季；竖虚线 = 下次决算日（「?」= Yahoo 预计、还没公布）；浅底 = 这一期；标签：最近一季同比、全年予想进度、上修 / 下修；对话里读 `~/.qbreak/home/out/fins_view.json`（`qbreak/fins_view.py`；J-Quants 定时取数〔交易日 19:30 + 次日 07:05，`liveu.sh jq`〕顺便取持仓 + 出了买入信号 / 估计 5 个交易日内的票） | 只展示；「予想」是公司自己的全年目标摊下来的数，不是预测；数据是 J-Quants 派生、只在本机（不入库）；新进选股的票在下一次取数之后才有图 |
| 为什么持有 / 现在趋势 | 「为什么买 7203？」「持仓现在趋势怎么样？」 | 读 `~/.qbreak/home/out/live_unified_paper.json` 的 holding_view（或账本页面 / 操作面板 / 日志）；日报例行任务的模拟盘看 `var/out/unified_today.json` 的 holding_view 与日报 ② | 只展示：买入那天的规则读数 + 均线位置的机械描述，不是预测；不给买卖建议 |
| 直接在立花网站 / 手机网站上人工买卖 | —— | 执行器管的股票（股票池 + 核心 ETF 1545 / 1482）在执行器之外买卖会让第二天的持仓核对停下（立花没有原生 App；手机网站 https://kabuka.e-shiten.jp/mfds_smp.php） | 要卖请用上面的手动卖出；真要在网站上操作：先说「停」，再商量；已经做了 → 第二天早上之前 `adopt` 登记（上面「持仓核对 / 人工代下登记」） |
| 研究 / 改规则 | 「用 J-Quants 数据研究 XX，先登记再跑」 | 在 `~/qbreak-dev` 里：登记（提交）→ 运行 → 结果写进 sim_changes → 推送 | 模拟盘 / 实盘规则只在你确认后改 |
| 研究循环进度 | 「第 N 个研究循环进度？」「停止研究循环」 | `git -C ~/qbreak-src pull --ff-only` 后 `env -u QBREAK_HOME ~/.qbreak/venv/bin/python scripts/research_loopN.py --status`（第一个是 `research_loop.py`，其余 `research_loop2.py`〜`research_loop14.py`；在 `~/qbreak-src/quant_breakout`，读 `var/research_loop*.json`；只读）；停止 = 不再开新的一轮 | 循环只研究、只提议，不改模拟盘 / 执行器 |
| 日报 / 季度复核 | 「上次季度复核说了什么？」「今天日报的主题强弱？」 | `git -C ~/qbreak-src pull --ff-only` 后读 `var/out/`（`*_review.md`、`unified_today.json`） | 只读 |

立花的交易次数与能买的股票（2026-09-26 查官方页面，仅对该时点有效；出处见 sim_changes.md 同日一节）：
- 每天的下单 / 成交次数**没有上限**（官方规则与 API 仕様里都没有）；一笔上限 = 株数不限、金额 5 億円；现物同一只股票同一天用同一笔钱
  「买 → 卖 → 再买」是差金決済（法律禁止，会被拒单），换成别的股票（乗換）可以。执行器每天最多约 4〜6 笔（个股 + 核心 ETF），远离任何限制
- 股票池 225 只（2026-09-30 起加回航空 / 陆运 12 只；以前 213 只）全部是东证 Prime（J-Quants 上市一览 2026-09-26），立花都能买；但**只能按 100 股一手买**（立花不做单元未满股的买入）
- 按 ¥100 万、一个名额 25%（¥25 万）：2026-09-25 收盘时 213 只里有 140 只一手 > ¥25 万、107 只 > ¥34 万 → 这些票出信号时会被跳过
  （日报候补队列的「买得起：是 / 否（一手 ¥…）」就是这个）
- **买的都能在立花买（2026-10-04 用户要求「保证现在买的股票只在立花证券里面都可以买」；`qbreak/tradable.py`；sim_changes 同日「工程（用户要求）」）**：
  2026-10-04 核对 JPX 上場一覧（2026-08-31 版）：股票池 225 只全部「プライム（内国株式）」、核心 1545 / 1482 都是「ETF・ETN」→ 现在都能买。
  以后自动守住：① 资格检查 G7（日报例行任务的模拟盘 + Mac 执行器）：JPX 市場区分不是内国株式 / ETF・ETN、或一覧里没有 → 个股不开新仓、核心那份留现金、执行器不下买单；
  ② 执行器接立花本番时，发每一笔买单前再查立花自己的銘柄マスタ（每天早上取一次）：没有 / 優先市場不是東証 / 売買停止 / 外国株 / PRO Market /
  30 天内上場廃止 / 現物買付「取引禁止」/ 数量不是売買単位的整数倍 → 不发；マスタ取不到也不发。都只挡买单，卖单与持仓不受影响。
  上实盘前在 Mac 上跑一次只读核对（不发单）：`bash scripts/liveu.sh probe`（最后一步「立花銘柄マスタ：股票池 + 核心能不能买」，也核对売買単位与一手）

## 今天还能交易几次（2026-10-15 起；用户「还要结合股市交易逻辑可以看到当前还可以买几次 卖几次 进行几次股票交易」；只读、不是建议）
- 看哪里：操作面板（Mac + 手机）「交易」页最上面的小卡「今天还能：买 N 次 · 卖 M 次 · 共 K 次」+ 一行时段（现在写的指令什么时候下、下一个能交易的时刻），
  展开看每只（代码带名字）；持仓每只一个小标记「今天还能卖 ✓ / 买 ✗（原因）」；`/api/trade_room?book=…`（手机端口要你本人；页面盘中每 1 分钟、其他时间每 10 分钟重画）；
  `bash scripts/liveu.sh manual list` 最后一段。算法只有一处：`qbreak/trade_room.py`（`room()`；测试 `tests/test_trade_room.py`）。
- 立花不限每天的下单次数（上面一节）→ 次数的限制来自下面五条，按顺序合起来、取最严（任何一条说今天不行 → 0）：
  ① 交易所时段：前場 09:00〜11:30、後場 12:30〜15:30；15:25〜15:30 是收盘竞价（执行器盘中的路到 15:25）→ 15:25 之后 / 休市日今天 0 次。
  ② 差金決済（立花 e支店「差金決済取引・日計り取引」https://www.e-shiten.jp/TorihikiRule/rule/sakin_hibakari.html ，2026-10-15 核对，仅对该时点有效）：
     同一只、同一天、同一笔钱 —— 买 → 卖之后再买要另有前受金（卖出所得不能拿来再买）；拿着的 卖 → 买之后再卖要另有前受金或持股 ≥ 合计卖出股数；换别的股票不受限。
  ③ 执行器的规则：同一只当天只下一笔（成交过的照算；撤了 / 不下 / 被拒 / 失效的不算）→「下一笔 MM/DD 开盘」；个股名额（2026-10-24 起不设上限；设了上限时含已写的买入）；手动卖出后不买回（到哪天）；
     资格检查 / 立花能不能买 / 决算前 / 新仓倍数 0；盘中现价比收盘高 3% 以上不买；核心 ETF 不用「买入」（用固定口数 / 闲置资金比例）。
     核心 ETF 的「同一只当天只下一笔」/「今天买进」只挡「卖出全部」/「调仓…」（闲置资金比例）；「固定口数…」与执行器 fix_prep 同一个判断：
     只有还挂在交易所没成交完的单、今天已经买过也卖过才挡，口数按账本 + 今天的成交算（2026-10-16 整合复核）。
  ④ 钱：与执行器盘中买入同一个式子（余力 − 还没下的买单要占的 − 出金预留）×(1 − 1% 现金缓冲)，加上能卖来凑钱的核心 ETF；钱是共用的，新股按一个单元便宜的先数（只是数）。
  ⑤ 闸门：HALT / 立花没解锁 / 状态不明的单 / 今天的持仓核对不一致 / 立花 08:55 之后早上的运行没完成 → 全部 0；模拟账户早上没跑完、面板盘中自动下单暂停 → 只写一句（补跑 / 写新指令就恢复）。
- 「买 N」= 名额与钱都够的新股只数 + 拿着的还能加仓的只数；「卖 M」= 拿着的、今天还能卖的只数；「共 K」= 两者之和，同一只既能买又能卖只算一次（执行器同一只当天只下一笔）。
  「拿着的」含今天已成交（与「持仓」角标同一份：开盘前拿着的 − 今天已卖光的 + 今天买进的；2026-10-16 整合复核 2：以前按开盘前的持仓数，今天买进、能用「固定口数…」卖的核心 ETF 不算进卖，今天已卖光的反而算「还能加仓」）。
  每个数都带一句「为什么是这个数」。Claude 回答时照它说，不借此建议买卖哪只；非投资建议。

## 已知限制
- 操作面板的 K 线、建议的股票与「约占权益」按执行器最近一次运行写的收盘（不是盘中实时）；加仓 / 买入：07:40 的决策之前点的进那次决策（寄付），之后 / 盘中点的
  开盘后盘中马上买（2026-10-07 起；以前一律下一个交易日开盘），现价高于决策日收盘 ×1.03 不买；开盘后才下的买单（等开盘后）发出之前也能用面板「今天要成交的单」的「撤单」撤
  （2026-10-15 起 = 执行器不再发；以前 09:05 之后才能撤），发出之后同样能撤（已成交的部分撤不了）；
  加仓成交后成本按股数平均、止损不变（不按加仓价重设）；面板上「按规则约几股」按最近收盘估算，执行器按决策日的收盘与权益再算
- 行情主要来自 Yahoo（yfinance），偶有修正与缺失；被拦截时用 `var/csv`。日报「数据完整性」逐项列出没取到的数据
- 股票池是 2026-09 时点的成分股 → 回测有幸存者偏差（偏乐观），只适合比较方案之间的相对差异；回测收益是税前（税后估算 2026-10-06 `var/out/nisa_tax_study.md`：全部特定口座少 2.7〜4.0 pp / 年，核心放 NISA 可收回 1.4〜2.1 pp）。
  J-Quants Standard 的 10 年时点股票池回测（2016-10〜，TOPIX500，只做个股突破）：偏差约 0.05〜0.10 pp / 年（`var/out/pit_backtest.md`）；
  整套 S0C2 同口径（J-Quants 行情、真实一手）：今天的日経225 年化 13.41% vs 时点 TOPIX 500 12.53%（差 0.88 pp / 年，含股票池不同；`var/out/pit_retrain_study.md`）
- 回测用复权价：拆股前的真实一手比回测以为的贵（按当时真实股价修正 2016-09 以后，20 年年化 −0.55 pp，`var/out/jq_study.md` A 部分）；
  ¥100 万、一个名额 ¥25 万时，股票池 225 只里约 140 只一手就超过名额（2026-09-25 收盘按当时的 213 只数的；2026-09-30 起 225 只）→ 实际可交易的票远少于 225 只
- 模拟账户按开盘价 + 滑点撮合（与回测相同；2026-10-15 起成交日 09:25 前后先按开盘价当天撮合 —— 2026-10-17 起开盘价 = 立花本番的始値（只读登录一次），取不到 → Yahoo 1 分钟线第一根；第二天早上按正式日线开盘价改记 ——
  两者让结论不同〔跳空上限 / 张贴 / 等开盘后的买单按当天现金算的股数〕时只记一条 warn、不回滚，那天与云端可能不一致，可解释）；实盘还有：开盘后补单的盘中价格、限价没成交、比例配分。
  演练（立花适配器 + 模拟交易所）：5 年年化 22.99% vs 回测 23.02%（−¥3,864）；20 年 12.87% vs 12.87%（−¥4,865）
- 立花デモ環境价格是假的、每天重置 → 只能检查 API 字段与流程；开盘前买付可能額的实际行为要本番头几天确认（MACOS §1.6「上线头 5 个交易日的值守清单」）
- 现行执行器**不挂逆指値**（旧守护进程的「逆指値是永远在岗的保险」不适用）：离场只在每个交易日 07:40 的决策里下寄付卖单，盘中不盯价、券商那边没有保护单；
  Mac 那天没跑 → 那天不卖（09:30 自检每个工作日推一条到手机；那天没收到 = Mac 没跑，靠你发现）；立花 API / Mac 故障那天照面板「今天要成交的单」（与收起的「已结束 / 不是今天的」里被挡 / 没下的行）在立花网站下、第二天早上之前 `adopt` 登记（MACOS §8）
- Mac 要开着且已登录（合盖 / 关机就不跑）；本机例行任务没跑 / 卡住时 07:40 的执行器用手上最新的输入继续，并提示（★ 判断层的输入 N 天没更新）。
  立花模式（2026-10-04 起）：睡着错过 07:40 / 09:05 → 08:35 / 09:20 重试；工作日自动唤醒要你做一次 `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`（2026-10-09 起 06:40：本机例行任务 06:45 开始；现在实际设的每天 06:30 也行 —— 早于 06:45 就行；执行器只要 07:40 之前）；
  重试也错过（例如一直关机到 09:20 以后）→ 那天不下单，第二天照常对账、决策（不补前一天的单）
- **本机例行任务没有后备**（云端 2026-10-19 已删）：2026-10-20〜10-23 本机任务停在权限确认（复合命令 / `$(…)` 一律要人确认），日报晚入库或没入库 → 那几天 07:40 的执行器用的是旧的判断层 / 宏观输入（前向记录判断层、关联搭配 C、TBF、市场状态；照旧下单，只是这几层按旧文件或不生效）。对策：10-21 卡住 30 分钟以上自动停止 + 推送（`python -m qbreak.routines reap`）、10-23 入库 / 等日报改成单条命令 `routines.sh save / wait-sim`、2026-10-24 在 `~/qbreak-sim/.claude/settings.local.json` 补了 4 条允许规则（`python -m qbreak.routines allow-missing` 只读列出缺的）、2026-10-25 自动停止日报时把这次已经跑成的 sim-day 结果自己入库推送 + 07:00〜07:40 卡住只等 10 分钟（10/23 停掉了却没入库，08:29 才推上来）；Mac 没做的那天要人说「补跑」，09:30 自检会提醒「今天的模拟盘日报没入库」
- **账户的收益与回撤主要来自核心 ETF 1545 纳斯达克 100**（不对冲美元）：诊断（`var/sim_changes.md` 2026-10-23「现行算法（B4）的不足在哪里」节、`var/out/b4_weakness_diag.md`）核心占权益 81〜93%、账户 ≥ 10% 回撤的亏损 76〜100% 来自核心，多在美股仍判为牛的快跌里；个股层平均只占用约 5〜7% 的资金 → 选股改进对账户的影响很小；1545 不对冲 → 日元走强时日元计的回撤更深（对冲版 FJE 2026-10-03 撤掉；BCU 只在美股熊时换 1482）
- **市场风险报告的判断层不在主回测里（2026-10-24 起停用）**：最近几天让新仓倍数为 0 的「避险 → 不开新仓」（「减仓观察」→ ×0.5）是按每天的报告实时用的，B3 / B4 的回测没有它；报告的判断放到过去重现（`var/out/report_judgment_backtest.md`）：风险准、方向不准、照着做不比一直拿着好；2026-10-24 放进 B4 账户检验（〔71〕③）：让账户变差（合计 −0.299）→ 同日用户选〔83〕③ 停用（use_report_overlay = false，只显示）
- **面板 / 手机的现价约晚 20 分钟**（Yahoo；持仓现价、卖出的预计收益、盘中 K 线、选股的现在买价）：只有立花本番的快照（始値 / 実時現在値，`qbreak/rt_quotes.py`，只读登录一次）是实时的；立花盘中下单按下单那一刻的立花实时现价挂限价，与面板上看到的价可能不同
- 日历：东证的将来休日来自规则 + 官方日历核对（J-Quants 的官方日历目前到 2027-12-31；新的特别休日 / 临时休市要改 `qbreak/calendar_jp.py`，季度数据体检 A2b 会报出来；当天才知道的东证临时休市：你确认后 `bash scripts/liveu.sh closed add YYYY-MM-DD --note …`，只写 Mac 的数据目录）。日経225先物的休市期间行情只有 CME（Yahoo NIY=F）；大阪的祝日取引数据要 J-Quants Premium（现在是 Standard）

## 路线图 / 未来的展望
1. 2026-09-28 起：模拟期（到 12-24）。每天看页面；「与云端一致」2026-10-19 起只作参考（云端例行任务已删、以本地为准）
2. ✅ 2026-10-12：第一次季度复核已跑（提交 9a686e2；判定有变化时第一行会写「需要用户确认」，不自动改规则）；下一次 2027-01-12
3. 立花：✅ 已开户；✅ 本番只读 probe（2026-10-17 起正常）；✅ デモ发单检查（2026-10-19）；✅ gate 全 OK（2026-10-24）；还没做：入金、ARM（用户决定）。原来的步骤（参考）：开户 → 马上注册パスキー（最好有备用设备；2026-12-12 / 12-18 起网页交易与撤单要它）→ e支店・API 利用設定、公開キー登録 → `bash scripts/liveu.sh probe --demo` 与 `probe --demo --order-test`（一天）
   → 本番 `bash scripts/liveu.sh probe`（只读）与 `--dry-run` → 入金 → `install_launchd_live_u.sh tachibana`（07:40 / 08:35 重试 / 09:05 / 09:20 重试）
   → `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`（你在终端做一次；或每天 06:30，早于 06:45 就行）→ `bash scripts/liveu.sh gate` 全 OK → `echo ARMED > ~/.qbreak/home/ARM`（MACOS.md §1.6）
   → 上线后头 5 个交易日照 MACOS.md §1.6「上线头 5 个交易日的值守清单」看；要退出 / 换 Mac / Mac 失控时照 §1.6「退出实盘 / 回到模拟」、§1.14、§8「最后停止手段」
4. 上线门槛（2026-09-26 用户原样采用；事先定下，之后不因模拟结果改数字；**2026-10-19 用户：「Mac 模拟操盘与云端连续 ≥ 10 个交易日一致这个不需要了 云端的现在定时任务删除了 以本地为准」→ ① 不再是门槛，`liveu.sh gate` 只在【参考】里写比较情况；与云端的不一致只供参考、不升 warn、不加 ★**）：~~Mac 模拟操盘与云端连续 ≥ 10 个交易日一致~~
   （或差异都能解释）、没有状态不明的单、HALT 演练过一次、デモ发单检查的三点（约定字段、余力变化、按注文番号撤单）确认；
   全部满足才上本番，先用较小金额跑 1〜2 周再加到计划金额（2026-10-04 起逐项检查：`bash scripts/liveu.sh gate`，只读；
   HALT 演练：`bash scripts/liveu.sh halt-drill`；门槛的数字不变；2026-10-09 起 ① 另要求最近一次比较在 10 个交易日以内 —— 2026-10-19 起 ① 整条只作参考，这一条随之不算门槛）
5. 2026-12-24 模拟期结束：按事先的格式总结（累计收益、最大回撤、交易笔数、胜率、与买入持有对比）→ 用户决定继续 / 上实盘 / 调整
6. J-Quants Standard（¥3,300/月，10 年）已购买（2026-09-26）：新数据研究与 10 年无幸存者偏差回测已做（`var/out/jq_study.md`、`pit_backtest.md`）；
   20 年的无幸存者偏差要 Premium（¥16,500/月，2008-05 起；2026-09-26 官方页面）
7. 前向记录（威胁指数各版本、日経 / 美股前瞻观察、配比最优化）继续只追加；到期由季度复核按事先规则评估
