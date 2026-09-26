# CLAUDE.md（仓库根目录：Claude Code 在这个仓库里启动时自动读取）

主体是 `quant_breakout/`：个人用的日本股票量化交易系统（研究 → 云端模拟盘 → Mac 上的执行器）。命令都在 `quant_breakout/` 下运行。
现状、每天的流程、决定与理由、已知限制、路线图（先读它）：@quant_breakout/HANDOFF.md

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
- 云端例行任务（Routines）：没有用户在这次对话里确认，不新建、不修改、不删除

## 方法论（不改规则去迎合结果）
- 研究先登记规则（commit）再运行；看到结果之后不改规则；前向记录 `quant_breakout/var/out/*_forward.csv` 只追加，不改、不补写
- 配置变更与研究结论记在 `quant_breakout/var/sim_changes.md`（事后的改动写明是事后）
- 不改策略参数、仓位、股票池、宏观阈值、牛熊分界参数，除非用户明确要求并记进 sim_changes.md
- 新出现的行业 / 主题 / 公司（日报「新出现的联动」、新上市、用户提的新主题）：先用 `quant_breakout/scripts/theme_link_check.py`
  和现有东证业种 + 主题做关联对比，结果写进 sim_changes.md；改主题表 `quant_breakout/qbreak/themes.py` 要用户同意；
  影响度历年值 `var/theme_influence.json` 每年 1 月用 `scripts/theme_influence.py` 加上刚结束的一年

## 在用户的 Mac 上（2026-09-26 起：用户只在 Mac 的 Claude 对话里提问与执行）
用户的问法与对应的命令见 HANDOFF.md「在 Mac 对话里怎么问」。
- **直接执行，不要只列命令**：用户问到的事凡是要运行命令才能回答或完成（看账本 / 页面 / 日志、拉代码、装或更新定时任务、取数、做研究），
  Claude 自己运行并把结果告诉用户；遇到权限确认就请用户点允许。只有下面「实盘相关」的几件事、改模拟盘规则、密钥，要用户在这次对话里明确说
- **拉代码后一条命令装好 / 更新全部**（依赖、模拟操盘、市场仪表盘 + 经济威胁提醒、J-Quants 定时取数、研究用克隆）：
  `git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh`（可重复运行，不动账本、不下单）
- **研究一口气做完**：在 `~/qbreak-dev` 里走完「登记（提交推送）→ 运行 → 记进 sim_changes → 推送 → 汇报」，中途不停下来问；
  只有推不上去（没配 GitHub 登录）或结果需要用户决定（要不要改模拟盘）时才停
- 两个克隆：`~/qbreak-src` = 每个交易日 07:40 定时任务用的仓库，**只 `git pull`，不改、不提交被跟踪的文件**（本地改动或本地提交会让
  定时任务拉不下来，模拟 / 实盘就用旧代码、旧数据）；`~/qbreak-dev` = 改代码、做研究用的第二个克隆（同一分支；第一次需要时建：
  `git clone -b claude/rakuten-auto-trading-review-ka7lf0 https://github.com/shimitsu123/public.git ~/qbreak-dev`）
- 在 `~/qbreak-dev` 里改代码 / 做研究：规则同「在云端」一节（先登记后运行、全部测试通过才提交、`git pull --rebase` 后再推、不写模型名）；
  推送要用户自己在 Mac 上配好 GitHub 登录（`gh auth login` 或 SSH 钥匙；不在对话里贴令牌），推不上去就停下告诉用户；
  推上去之后 `git -C ~/qbreak-src pull --ff-only`（不拉也行，第二天 07:40 会自动拉）
- 云端例行任务照旧（每个交易日 06:57 模拟盘日报、每季复核）：它们每天推 `var/`，所以 dev 克隆推之前一定先 `git pull --rebase`
- 不在 Mac 上对仓库的 `var/` 运行 `run.py sim-day` / `sim-*` / `report` / `optimize` 等（会改被跟踪的文件；模拟盘只在云端跑）
- 执行器只经 `scripts/liveu.sh`（它把数据目录设成 `~/.qbreak/home`）；直接跑 `run.py` 时先 `export QBREAK_HOME=~/.qbreak/home`
  （只读命令也一样）；Python 用 `~/.qbreak/venv/bin/python`（macOS 自带的 3.9 不够）
- J-Quants（Standard，研究用）：密钥放钥匙串（服务名 `qbreak-jquants`，用户自己用 `security add-generic-password -s qbreak-jquants -a qbreak -w` 存），
  命令需要キー时用 `bash scripts/with_jquants.sh <命令>`（从钥匙串读进那个进程的环境变量、绝不回显）；每天的新数据由
  LaunchAgent `com.qbreak.jquants`（周一至五 19:30 + 07:05）取，整理结果 `~/.qbreak/home/out/jq_today.json`（只展示 / 研究）
- 实盘相关（立花）：不创建 `~/.qbreak/home/ARM`、不删除 `HALT`、不加 `--no-arm`、不用 `--resolve` 登记成交，除非用户在这次对话里明确要求；
  用户说「停 / 今天不要下单」→ 立刻建 `~/.qbreak/home/HALT`（停下单不用再确认）；不在执行器之外向立花发任何单（不写临时脚本调 API 下单）；
  用户想人工买卖执行器管的股票（股票池 + 1655）→ 先说明这会让第二天的持仓核对停下，建议先 HALT 再商量
- 排查先看：`~/.qbreak/home/logs/com.qbreak.liveu.*.out|err`、`~/.qbreak/home/out/live_unified_paper_journal.md`、
  页面 `~/.qbreak/home/out/page_paper.html`、`bash scripts/liveu.sh --broker paper --status`、`launchctl list | grep qbreak`；
  市场仪表盘 / 经济威胁提醒（每 15 分钟）：`~/.qbreak/home/out/dashboard.html`、`~/.qbreak/home/logs/com.qbreak.news.out|err`（只展示与提醒，不下单）；
  J-Quants：`~/.qbreak/home/logs/com.qbreak.jquants.out|err`

## 在云端（claude.ai/code 会话 / 例行任务）
- 开发分支 `claude/rakuten-auto-trading-review-ka7lf0`：只推这个分支，不开 PR（除非用户要求）
- 提交前在 `quant_breakout/` 跑 `set -o pipefail; python -m pytest -q`（必须全部通过）；推之前 `git pull --rebase`（例行任务每天也推 `var/`）
- 代码、注释、提交信息里不写模型名
- shell 脚本：`$变量` 后面紧跟中文 / 全角字符时写成 `${变量}`（macOS 自带的 bash 3.2 在 UTF-8 下会把下一个字节算进变量名，
  `set -u` 时直接退出；`tests/test_shell_scripts.py` 会查）
