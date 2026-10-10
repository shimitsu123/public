# CLAUDE.md（仓库根目录：Claude Code 在这个仓库里启动时自动读取）

主体是 `quant_breakout/`：个人用的日本股票量化交易系统（研究 → 云端模拟盘 → Mac 上的执行器）。命令都在 `quant_breakout/` 下运行。
现状、每天的流程、决定与理由、已知限制、路线图（先读它）：@quant_breakout/HANDOFF.md
全部研究按层与时间串起来的检查时间线（每天 / 每周 / 每月 / 每季 / 每年、事件驱动、判定日历）：`quant_breakout/CHECK_TIMELINE.md`

## 和用户沟通
- 用中文；结论先行 → 要点（≤ 7 条）→ 详解 / 来源 / 下一步
- 每个数字带单位（¥ / 円、股、口、%、pp、円/USD、pt、JST）；专业术语第一次出现附英文或日文原词
- 涉及交易、行情、个股的回答最后写「非投资建议」；不给买卖指令、不承诺收益
- 需要联网的事实（价格、手续费、制度、版本、日程）写日期与来源，并注明「仅对本次检索时点有效」
- 信息稍缺但不影响结论时先答，再列「待补参数」；少反问
- 命令每条单独一个代码块

## 安全（必须遵守）
- 绝不打印、回显、记录、提交任何密钥的值（`JQUANTS_API_KEY`、立花的认证 ID / 私钥 / 第二暗証番号、webhook URL 等）；只检查「是否已设置」
- 绝不让用户把密钥、令牌、密码贴进聊天：放 Mac 的钥匙串（Keychain）/ `~/.zshrc` / launchd 的 plist，或云端环境设置
- 立花私钥 `~/.qbreak/e_api_private_key.pem` 保持 `chmod 600`，不读出内容
- J-Quants 原始数据不能入库（公开仓库 + 个人自用条款）：缓存只在 `quant_breakout/var/cache/jquants/`（已 gitignore）
- 消息监控（`qbreak/news.py`）取来的第三方标题 / 链接不能入库：只放 `var/cache/news/`（已 gitignore）与 Mac 本机页面；日报（会入库）只放汇总
- 不抓取、不自动操作楽天証券网站或 iSPEED（総合証券取引約款 第35条第12項）
- 这是**公开仓库**：CLAUDE.md、HANDOFF.md、代码、提交信息里不写个人信息（姓名、邮箱、账户号、住址、Mac 用户名、私人链接）
- 云端例行任务（Routines）与 Mac 桌面版的本机例行任务：没有用户在这次对话里确认，不新建、不修改、不删除
  （用户说「装本机例行任务」= 确认照 `quant_breakout/routines/README.md` 建那三个本机任务）

## 方法论（不改规则去迎合结果）
- 研究先登记规则（commit）再运行；看到结果之后不改规则；前向记录 `quant_breakout/var/out/*_forward.csv` 只追加，不改、不补写
- 配置变更与研究结论记在 `quant_breakout/var/sim_changes.md`（事后的改动写明是事后）
- 不改策略参数、仓位、股票池、宏观阈值、牛熊分界参数，除非用户明确要求并记进 sim_changes.md
- 新出现的行业 / 主题 / 公司（日报「新出现的联动」、新上市、用户提的新主题）：先用 `quant_breakout/scripts/theme_link_check.py`
  和现有东证业种 + 主题做关联对比，结果写进 sim_changes.md；改主题表 `quant_breakout/qbreak/themes.py` 要用户同意；
  影响度历年值 `var/theme_influence.json` 每年 1 月用 `scripts/theme_influence.py` 加上刚结束的一年

## 在用户的 Mac 上（2026-09-26 起：用户只在 Mac 的 Claude 对话里提问与执行）
**2026-10-09 起：问、答、改代码、做研究、提交、推送（上传）都在 Mac 本地的 Claude 里做，不需要云端会话**
（例行任务也在 Mac 上：Claude 桌面版的本机任务 + 云端后备，见下面「例行任务」一条）。用户的问法与对应的命令见 HANDOFF.md「在 Mac 对话里怎么问」。
- **直接执行，不要只列命令**：用户问到的事凡是要运行命令才能回答或完成（看账本 / 页面 / 日志、拉代码、装或更新定时任务、取数、做研究），
  Claude 自己运行并把结果告诉用户；遇到权限确认就请用户点允许。只有下面「实盘相关」的几件事、改模拟盘规则、密钥，要用户在这次对话里明确说
- **拉代码后一条命令装好 / 更新全部**（依赖、模拟操盘、市场仪表盘 + 经济威胁提醒、J-Quants 定时取数、研究用克隆）：
  `git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh`（可重复运行，不动账本、不下单）
  连手机上操作一起（用户说「拉代码，手机操作全部执行」）：同一条命令后面加 `--phone node`（拉代码 → 全部更新 → 打开 Tailscale Serve → 在 Mac 上打开面板的「手机」；之后照常的更新会确认手机访问还在）
- **研究一口气做完**：在 `~/qbreak-dev` 里走完「登记（提交推送）→ 运行 → 记进 sim_changes → 推送 → 汇报」，中途不停下来问
  （推送都用下面的 `bash scripts/dev.sh push`）；只有推不上去（没配 GitHub 登录）或结果需要用户决定（要不要改模拟盘）时才停
- 三个克隆：`~/qbreak-src` = 每个交易日 07:40 定时任务用的仓库，**只 `git pull`，不改、不提交被跟踪的文件**（本地改动或本地提交会让
  定时任务拉不下来，模拟 / 实盘就用旧代码、旧数据）；`~/qbreak-dev` = 改代码、做研究用的第二个克隆（同一分支；第一次需要时建：
  `git clone -b claude/rakuten-auto-trading-review-ka7lf0 https://github.com/shimitsu123/public.git ~/qbreak-dev`）；
  `~/qbreak-sim` = 本机例行任务专用的第三个克隆（`mac_setup.sh` 建；只有例行任务在这里改 `var/`、提交、推送，对话里不在那里改东西）
- 在 `~/qbreak-dev` 里改代码 / 做研究（规则同「在云端」一节：先登记后运行、全部测试通过才提交、不写模型名、只推开发分支、不开 PR），
  流程（命令在 `quant_breakout/` 下运行，用哪个克隆里的 `scripts/dev.sh` 都行）：
  `bash scripts/dev.sh check`（第一次 / 出问题时；只读：分支与上游、远端、推送权限、git 身份有没有设、Python ≥ 3.10 + pytest、`~/qbreak-src` 有没有本地改动）
  → 在 `~/qbreak-dev` 改 → `bash scripts/dev.sh test`（全部通过才提交）→ `git commit`（不写模型名）
  → `bash scripts/dev.sh push`（有未提交的改动 → 停下；先 `git pull --rebase`，冲突 → 停下、不自动解决；推送；再让 `~/qbreak-src` 快进
  ——它有本地改动不动、交易日 07:30〜09:35 JST 不换代码（执行器早上的几次运行用同一份代码），不拉也行，下一个交易日 07:40 会自动拉）；
  推不上去（没登录 GitHub）→ 停下，请用户自己在终端 `gh auth login`（或配 SSH 钥匙；令牌 / 密码不在对话里贴）；
  git 的 user.name / user.email 没设 → 请用户自己设（公开仓库：用不暴露个人信息的名字与 GitHub 的 noreply 邮箱），Claude 不替用户填
- 例行任务（2026-10-09 起）：模拟盘日报（周一至五 06:45）、影子账户判断（07:45）、季度复核（1 / 4 / 7 / 10 月 12 日 09:56）在 Mac 的
  Claude 桌面版本机任务里跑（工作文件夹 `~/qbreak-sim`，说明书 `quant_breakout/routines/`）；云端同名例行任务是后备（Mac 当天做过就跳过：
  `bash scripts/routines.sh done-today …`）；改 / 停要用户在对话里另外确认。前提：桌面版开着（登录项）、Keep computer awake 打开、
  Mac 工作日 06:40 自动唤醒（用户自己在终端 `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`）。它们（本机或云端）每天推 `var/`，
  所以 dev 克隆推之前一定先 `git pull --rebase`（`dev.sh push` 自己先做）；Mac 的执行器仍在每个交易日 07:40 `git pull` 读它们推的文件；
  用户问「例行任务今天跑了吗」→ `bash scripts/routines.sh check`（只读）
- 停下单：在 Mac 上直接说「停 / 今天不要下单」→ 建本地 `~/.qbreak/home/HALT`（见下面「实盘相关」）；人不在 Mac 旁边时才用云端对话的远程停止（「在云端」一节）
- `run.py sim-day` / `sim-*` / `report` / `optimize` 等对仓库 `var/` 的命令（会改被跟踪的文件）只由例行任务在 `~/qbreak-sim` 里运行
  （`bash scripts/routines.sh run …`）；`~/qbreak-src` / `~/qbreak-dev` 里不跑
- 执行器只经 `scripts/liveu.sh`（它把数据目录设成 `~/.qbreak/home`）；直接跑 `run.py` 时先 `export QBREAK_HOME=~/.qbreak/home`
  （只读命令也一样；数据目录在仓库里时立花的入口会拒绝运行——公开仓库）；Python 用 `~/.qbreak/venv/bin/python`（macOS 自带的 3.9 不够）
- 手机通知 / 外部心跳（2026-10-09 起）：地址是密钥，放钥匙串（`qbreak-webhook`：Discord / Slack / ntfy；`qbreak-smtp`；`qbreak-heartbeat`），
  用户自己在终端 `security add-generic-password -s qbreak-webhook -a qbreak -w`（回车后输入，不贴进聊天）；邮件（2026-10-09 起用这个）：用户自己在「终端」App
  运行 `bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup`（交互输入 Gmail 应用专用密码，先发一封测试邮件、发成了才存进钥匙串 `qbreak-smtp`；Claude 不运行它）；Claude 只说有 / 没有；
  试发 `bash scripts/liveu.sh notify-test`；09:30 自检（LaunchAgent `com.qbreak.watchdog`）：问「今天的自检过了吗」→ 看
  `~/.qbreak/home/out/watchdog_{paper,tachibana}.json` 或跑 `bash scripts/liveu.sh watchdog --dry`（只判定、打印，不写、不发）；
  不带 `--dry` = 重新自检一次（会重写结果文件，没通过会再发手机通知、让外部心跳报失败）→ 只在用户要「再自检一次」时跑
- J-Quants（Standard，研究用）：密钥放钥匙串（服务名 `qbreak-jquants`，用户自己用 `security add-generic-password -s qbreak-jquants -a qbreak -w` 存），
  命令需要キー时用 `bash scripts/with_jquants.sh <命令>`（从钥匙串读进那个进程的环境变量、绝不回显）；每天的新数据由
  LaunchAgent `com.qbreak.jquants`（周一至五 19:30 + 07:05）取，整理结果 `~/.qbreak/home/out/jq_today.json`（只展示 / 研究）
- 实盘相关（立花）：不创建 `~/.qbreak/home/ARM`、不删除 `HALT`、不加 `--no-arm`、不用 `--resolve` 登记成交，除非用户在这次对话里明确要求；
  2026-10-09 起同级（用户这次明确说才运行）：撤单 `bash scripts/liveu.sh cancel [<cid>…] --broker tachibana` / 停并撤单 `bash scripts/liveu.sh halt-cancel --broker tachibana`（不写 `--broker` = 有账本的都撤；用户说「撤单」；只撤执行器自己今天还挂着的单）、
  人工代下登记 `liveu.sh adopt --broker tachibana <代码> <BUY|SELL> <股数> <均价>`（用户给出在立花网站上的实际成交）、恢复账本 `liveu.sh restore --broker tachibana <备份文件名>`、
  换 Mac `liveu.sh adopt-host --broker tachibana`（用户说「换 Mac，账本归这台」，旧 Mac 已停）、临时休市 `liveu.sh closed add|rm`（先核对 JPX 官方公告）；
  只读的可以直接跑：`liveu.sh unknown|reconcile|broker --broker tachibana`（会登录立花一次；执行器在跑时自己等它结束再登录，最多 5 分钟；所有登录本番的进程共用一把会话锁）、`liveu.sh quality|export|onboard`（只读账本 / 上线检查，不登录）、`liveu.sh restore --broker tachibana --list`、`liveu.sh closed list`；前一晚预检 `liveu.sh precheck` 会登录立花一次 → 用户要「再预检一次」才跑；`liveu.sh precheck --ack-api <日子>`（API 新版本的预告核对过、不用更新 → 只清这个提醒，不登录）用户确认后才跑；
  Mac 失控 / 联系不上时的最后停止手段：告诉用户自己在立花网页把「ｅ支店・API 利用設定」改成「無効化」（MACOS.md §8；Claude 不登录、不操作立花网站）；
  上线头几天 / 退出实盘 / 换 Mac 照 MACOS.md §1.6 / §1.14；
  用户说「停 / 今天不要下单」→ 立刻建 `~/.qbreak/home/HALT`（停下单不用再确认）；不在执行器之外向立花发任何单（不写临时脚本调 API 下单）；
  「做一次 HALT 演练」→ `bash scripts/liveu.sh halt-drill`（只删它自己建的演练 HALT；真的 HALT 存在时不演练）；「能上实盘了吗」→ `bash scripts/liveu.sh gate`（只读）；
  用户说入金 / 出金 → `bash scripts/liveu.sh flow <金额>`（出金写负数；只影响收益的计算与提醒，不下单；面板的「登记入金 / 出金」同一个函数）；
  口座课税区分不是特定口座时执行器不发单（〔77〕C T5）：一般口座（3）只有用户在对话里明确同意才建 `~/.qbreak/home/TAX_GENERAL_OK`，NISA（5 / 6）不放行；
  交易时段保持清醒 `bash scripts/install_launchd_awake.sh`（耗电）只在用户同意时装；
  手动卖出 / 减仓 / 调整持仓 / 买入 / 闲置资金比例（2026-10-06 起）：只经 `bash scripts/liveu.sh manual …` 或本机操作面板 http://127.0.0.1:8765/ 写「手动指令」，
  下单由执行器做（2026-10-07 起）：盘中（09:00〜11:30、12:30〜15:25）写的马上下（面板叫 `liveu.sh run --phase now`）、开盘前 / 午休写的等开盘、
  收盘后 / 休市日写的等下一个交易日开盘（闸门、对账照常，持仓核对不会停）；用户在这次对话里明确说要卖 / 减 / 加 / 买 / 改比例才写，没说账本就用模拟账户
  （`--broker paper`），立花本番要用户说「立花」；写之前告诉用户：什么时候下单（`manual list` 显示）、卖 / 减的预计收益（面板确认框或 `/api/quotes` 的 est：估算，现价约晚 20 分钟、税前，不是承诺）、按什么价下单（`/api/quotes` 的 basis：立花盘中按下单那一刻的实时现价挂限价 卖 −0.5% / 买 +0.5% 且 ≤ 收盘 ×1.03（2026-10-09 起夹在当天的制限値幅里；取不到现价不发成行），模拟账户按 Yahoo 现价，盘外按开盘价）、盘中的单发出后可以撤（面板「今天的单」的「撤单」或 `liveu.sh cancel`，用户说「撤单」才做；已经成交的部分撤不了；立花网站 / 手机网站也能撤）、
  卖出后默认 20 个交易日不自动买回、模拟账户的手动操作会中断上线门槛「连续一致」的天数；
  调整持仓（`manual adjust <代码> --shares N | --yen 金额 | --pct %`，可加可减）的加仓只加**已经持有**的个股；
  拿着的核心 ETF（2026-10-07 起）也能卖出 / 调整（面板 ETF 下面的按钮或 `manual sell|adjust|trim <ETF 代码>`）：换算成「闲置资金比例」、之后每天按它，
  比例对全部核心 ETF 一起生效（同时拿两只时另一只也跟着变 → 写之前告诉用户）；ETF 卖出全部 / 比例 0% = 停买闲置资金 ETF（钱留现金）：
  停着时规则从「不拿」变成「拿」= 买入信号，只提醒（通知 / 日志 / 面板）、不自动买 → 用户在这次对话里说「确认买入 / 恢复买 ETF」才写
  `manual core --pct 100`（Claude 不主动建议恢复）；
  买入新股（`manual buy <代码>`，默认按规则的仓位，或 `--shares / --yen / --pct`；面板「建议的股票」的「买入…」）= 与规则的新仓同一条路：占名额（个股最多 4 只，
  满了要先卖出一只）、不能买核心 ETF、手动卖出后不买回期内的票要先解除；加仓与买入：开盘前写的进新收盘的决策（寄付指値 = 收盘 ×1.03）、
  已经决策过 / 盘中写的开盘后盘中马上买（限价 = min(现价 +0.5%, 收盘 ×1.03)，现价超过收盘 ×1.03 不买）、今天已经有执行器单的票明天开盘再处理、
  钱不够先卖核心 ETF、单只最多占总权益 34%、资格检查 / 立花能不能买 / 新仓倍数 0 / 决算前的票不买、只做一次；
  加仓与买入都是用户自己的决定（「赢家加仓」研究没通过；面板列的是规则的候选，不是 Claude 的建议；观察中的排序 = 出买入信号的历史比例（都很低，只是排序与展示）；没触发信号的票没有回测验证）→ Claude 不主动建议加仓或买哪只；
  用户要在立花网站 / 手机网站（立花没有原生 App）上直接买卖执行器管的股票（股票池 + 核心 ETF）→ 先说明这会让第二天的持仓核对停下，建议先 HALT 再商量；
  已经买卖了 → 第二天早上之前用 `adopt` 登记（用户给实际成交数与均价）；
  下单前资格检查（`qbreak/eligibility.py`）与「立花能不能买」检查（`qbreak/tradable.py`：JPX 市場区分 + 立花銘柄マスタ）挡掉的票不要绕过；手上的票被标记（被踢出日経225 / JPX 指定 / 上場廃止预定）时规则不自动卖 →
  告诉用户、由用户决定（要卖就写手动卖出指令 `liveu.sh manual sell <代码>`）；名单差异（`run.py eligibility`）要改 `qbreak/universes.py` 须用户确认并记 sim_changes.md；
  退市时间表（`run.py delist-schedule`，`var/delist_schedule.json`）到了上場廃止日自动从股票池去掉（只减），补入仍要用户确认
- 手机上操作（2026-10-06 起）：只用 Tailscale **Serve**（`bash scripts/liveu.sh phone on|off|status|forget`；只在用户自己的 tailnet 里），
  **绝不用 Tailscale Funnel**、不把面板绑到 127.0.0.1 以外、不用别的公开转发；第一次打开会显示机器名（会写进公开的证书透明度日志）→
  用户 2026-10-06 已确认机器名 `node`（`mac_setup.sh --phone node` 只在机器名正好是 node 时才打开）；名字不一样就告诉用户、用户同意才换名字再运行；
  2026-10-07 起手机默认按 Tailscale 账户登录（不用配对）：只认这台 Mac 登录的 Tailscale 账户，只信任 127.0.0.1 上、路径带着 Serve 路径密钥（`phone on` 生成，Serve 的目标 = `http://127.0.0.1:8766/<路径密钥>`）的请求里的 Tailscale-User-Login 头，经 Funnel 来的请求一律拒绝；配对码留作备用；改登录方式（`bash scripts/liveu.sh phone identity on|off`）要用户在这次对话里明确说（`phone forget` 也会关掉按账户登录；手机丢了 → 先请用户在 Tailscale 管理页删掉那台手机，再打开）；账户名只显示打码后的、不写进仓库 / 对话 / 日志；路径密钥不显示、不读出 `~/.qbreak/home/panel_phone.json`，排查用 `bash scripts/liveu.sh phone status`、不把 `tailscale serve status` 的原文贴进对话；配对码只显示在 Mac 的本机操作面板上：Claude 不调 `/api/pair/new`、不读 `~/.qbreak/home/panel_devices.json`、
  不在对话 / 终端 / 日志里写配对码或设备令牌（请用户自己在 Mac 屏幕上点「生成配对码」）；手机页面的 HALT 只能建、不能解除（解除照旧只在 Mac 上、
  用户明确说）；手机上点的卖出 / 减仓 / 比例和本机面板一样只是「手动指令」（规则同上一条）
- 排查先看：`~/.qbreak/home/logs/com.qbreak.liveu.*.out|err`、`~/.qbreak/home/out/live_unified_paper_journal.md`、
  页面 `~/.qbreak/home/out/page_paper.html`、`bash scripts/liveu.sh --broker paper --status`、`launchctl list | grep qbreak`；
  市场仪表盘 / 经济威胁提醒（每 15 分钟）：`~/.qbreak/home/out/dashboard.html`、`~/.qbreak/home/logs/com.qbreak.news.out|err`（只展示与提醒，不下单）；
  J-Quants：`~/.qbreak/home/logs/com.qbreak.jquants.out|err`；登录 / 开机后的自动启动（补跑、打开页面）：
  `~/.qbreak/home/logs/com.qbreak.login.out|err`；操作面板 / 手动指令：`bash scripts/liveu.sh manual list [--broker tachibana]`、
  `~/.qbreak/home/logs/com.qbreak.panel.{out,err,retry.log}`；手机：`bash scripts/liveu.sh phone status`（只读，不含配对码）；
  执行器这次跑成没有：`~/.qbreak/home/out/live_unified_{paper,tachibana}_run.json`（面板顶部也显示）；09:30 自检：`~/.qbreak/home/out/watchdog_{paper,tachibana}.json`、
  `~/.qbreak/home/logs/com.qbreak.watchdog.out|err`；本地改代码 / 推不上去：`bash scripts/dev.sh check`（只读）；
  本机例行任务（今天跑了没有、是 Mac 还是云端后备做的）：`bash scripts/routines.sh check`（只读）、桌面版 Code → Routines → Review history；
  立花（2026-10-09 起）：前一晚预检 `~/.qbreak/home/out/precheck_tachibana.json`、状态不明的单的候选 `bash scripts/liveu.sh unknown --broker tachibana`、
  持仓核对 `bash scripts/liveu.sh reconcile --broker tachibana`、账本备份 `bash scripts/liveu.sh restore --broker tachibana --list`（都只读）、
  新代码的冒烟测试 `~/.qbreak/home/logs/smoke_test.log`

## 在云端（可选：例行任务的后备；人不在 Mac 旁边时也能用）
- claude.ai/code 会话 / 例行任务（模拟盘日报、影子账户判断、每季复核）。2026-10-09 起改代码 / 推送在 Mac 本地做（上一节），不需要云端会话；
  例行任务主要在 Mac 的本机任务里跑，云端同名例行任务是后备（Mac 当天做过就跳过）；改 / 停要用户在对话里另外确认
- 开发分支 `claude/rakuten-auto-trading-review-ka7lf0`：只推这个分支，不开 PR（除非用户要求）
- 提交前在 `quant_breakout/` 跑 `set -o pipefail; python -m pytest -q`（必须全部通过）；推之前 `git pull --rebase`（例行任务每天也推 `var/`）
- 代码、注释、提交信息里不写模型名
- 用户在云端对话里说「停 / 今天不要下单」（人不在 Mac 旁边）→ 立刻在 `quant_breakout/` 跑 `python run.py remote-halt --reason "<用户原话>"`，
  提交并推送 `var/HALT_REMOTE`（不用再确认；`git pull --rebase` 后推）→ Mac 的执行器下一次运行（07:40 / 08:35 / 09:05 / 09:20）建本地 HALT；
  只能停、不能恢复（恢复只在 Mac 上、用户明确说）；告诉用户：已经发到交易所的单不会被撤（要撤：手机面板「今天的单」的「撤单」、
  在 Mac 对话里说「撤单」，或立花网站 / 手机网站 https://kabuka.e-shiten.jp/mfds_smp.php）；Mac 失控 / 联系不上 → 最后停止手段（MACOS.md §8：用户自己在立花网页把 API「無効化」）
- shell 脚本：`$变量` 后面紧跟中文 / 全角字符时写成 `${变量}`（macOS 自带的 bash 3.2 在 UTF-8 下会把下一个字节算进变量名，
  `set -u` 时直接退出；`tests/test_shell_scripts.py` 会查）
