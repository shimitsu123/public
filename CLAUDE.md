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

## 在用户的 Mac 上（`~/qbreak-src` = 每个交易日 07:40 定时任务用的仓库）
- **不改、不提交 `~/qbreak-src` 里被 git 跟踪的文件**：定时任务每天 `git pull --ff-only`，本地改动或本地提交会让它拉不下来，
  模拟操盘就会用旧代码、旧数据。要改代码 → 告诉用户在云端会话（claude.ai/code）里改（那里跑全部测试、推到分支），Mac 只 `git pull`
- 不在 Mac 上对仓库的 `var/` 运行 `run.py sim-day` / `sim-*` / `report` / `optimize` 等（会改被跟踪的文件；模拟盘只在云端跑）
- 执行器只经 `scripts/liveu.sh`（它把数据目录设成 `~/.qbreak/home`）；直接跑 `run.py` 时先 `export QBREAK_HOME=~/.qbreak/home`
  （只读命令也一样）；Python 用 `~/.qbreak/venv/bin/python`（macOS 自带的 3.9 不够）
- 实盘相关：不创建 `~/.qbreak/home/ARM`、不删除 `HALT`、不加 `--no-arm`，除非用户在这次对话里明确要求
- 排查先看：`~/.qbreak/home/logs/com.qbreak.liveu.*.out|err`、`~/.qbreak/home/out/live_unified_paper_journal.md`、
  页面 `~/.qbreak/home/out/page_paper.html`、`bash scripts/liveu.sh --broker paper --status`、`launchctl list | grep qbreak`

## 在云端（claude.ai/code 会话 / 例行任务）
- 开发分支 `claude/rakuten-auto-trading-review-ka7lf0`：只推这个分支，不开 PR（除非用户要求）
- 提交前在 `quant_breakout/` 跑 `set -o pipefail; python -m pytest -q`（必须全部通过）；推之前 `git pull --rebase`（例行任务每天也推 `var/`）
- 代码、注释、提交信息里不写模型名
- shell 脚本：`$变量` 后面紧跟中文 / 全角字符时写成 `${变量}`（macOS 自带的 bash 3.2 在 UTF-8 下会把下一个字节算进变量名，
  `set -u` 时直接退出；`tests/test_shell_scripts.py` 会查）
