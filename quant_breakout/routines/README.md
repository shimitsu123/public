# 例行任务在 Mac 上（Claude 桌面版的本机任务；2026-10-09 起）

用户 2026-10-09「连云端例行任务也搬到 Mac」。这个仓库的三个例行任务改在 Mac 的 **Claude 桌面版「本机任务」（Local routine）** 里跑，
工作文件夹 `~/qbreak-sim`；**云端同名例行任务是后备**（Mac 当天做过就跳过，Mac 没做时补上）。

为什么这样做（官方文档，2026-10-09 检索，仅对本次检索时点有效）：
- 云端例行任务（Routine）只能在 Anthropic 云端（或 Team / Enterprise 的自建环境）运行，不能指派到个人的 Mac（https://code.claude.com/docs/en/routines）。
- Mac 上能定时跑 Claude 的是桌面版的本机任务（https://code.claude.com/docs/en/desktop-scheduled-tasks）：要 Claude Desktop ≥ 1.1.5368；
  **只在桌面版开着、Mac 醒着时运行**（每分钟检查一次，每个任务有几分钟固定的错峰）；睡过了的时间：醒来 / 打开桌面版时只补跑**最近一次**
  （7 天以内）；合盖照样会睡。`claude -p`（launchd 调用）默认不能发布 artifact，所以不用它。

## 三个本机任务

| 本机任务（建议的名字） | 说明书（每次照做） | 时间（JST） | 云端后备（改法见 [`cloud/README.md`](cloud/README.md)） |
|---|---|---|---|
| `qbreak-sim-daily` 模拟盘日报 | `routines/sim_daily.md` | 周一至五（Weekdays）06:45 | trig_01MMZVeTtxexr6y4sDhy4rxX，改到 07:20、最前面加「做过就跳过」：**要在日报发帖的那个云端对话里改**（`cloud/sim_daily_cloud.md`） |
| `qbreak-shadow` 影子账户判断 | `routines/shadow.md` | 周一至五（Weekdays）07:45 | trig_01WndiH4mZSiFkeExpsukNm4，改到 08:05、同上：**同上，在那个对话里改**（`cloud/shadow_cloud.md`） |
| `qbreak-quarterly` 顶底择时季度复核 | `routines/quarterly.md` | 1 / 4 / 7 / 10 月 12 日 09:56 | trig_01BA4ugENPhSrYW3QSd5djK6，改到 12:52、同上：**2026-10-09 已改** |

- 07:40 的执行器等的就是日报入库（`var/out/unified_today.json` 的 date = 今天）：Mac 06:45 开始，通常 07:10 前入库；Mac 没做 → 云端 07:20 补上。
- 「做过就跳过」= 说明书最前面的 `bash scripts/routines.sh done-today sim|shadow|quarterly`：
  退出码 0 = 今天已经由 Mac 或云端入库（打印是谁做的）→ 跳过；1 = 还没做 → 照常做；
  2 = 这个克隆拉不下来（本地改动 / 没推上去的提交 / 网络）或 git 身份没设 → Mac 的本机任务停下汇报（云端后备会做）。
  云端后备用同一个命令时：0 → 跳过；1 或 2 → 照原来的步骤继续（云端是最后一道，拉不下来照原步骤如实报告）。
- 谁做的看提交信息的开头：Mac 写 `sim(mac):` / `shadow(mac):` / `季度复核(mac)：`，云端照旧 `sim:` / `shadow:` / `季度复核：`。
- 日报在休市的工作日也照常做（和云端以前一样：处理上一个交易日的收盘、发布日报）；影子账户在休市日自己跳过（说明书第 0 步）。
- 09:30 自检（`com.qbreak.watchdog`）多看一项：交易日、今天的日报没入库 → 手机通知「今天的模拟盘日报没入库（Mac 的本机例行任务没跑？桌面版开着吗？）」。

## 先决条件（`bash scripts/routines.sh check` 逐项看，只读）
1. 例行任务专用的克隆 `~/qbreak-sim`：`mac_setup.sh` 会建（没有就 `git clone`；有且干净就快进；有本地改动不动）。
   只有例行任务在这里改 `var/`、提交、推送；`~/qbreak-src` 照旧只 pull（07:40 的执行器用），`~/qbreak-dev` 照旧给人改代码。
2. git 的 user.name / user.email 已设（公开仓库：不暴露个人信息的名字与 GitHub 的 noreply 邮箱；用户自己设）、能推送（`gh auth login` 或 SSH 钥匙，用户自己做）。
3. Claude 桌面版 ≥ 1.1.5368，开机自动打开（系统设置 → 通用 → 登录项 加上 Claude），**Settings → This computer → System → Keep computer awake 打开**
   （桌面版开着时不让 Mac 空闲睡眠：本机任务运行期间要醒着；07:40 的执行器另有 `com.qbreak.wakehold` 在 06:40〜07:50 保持清醒，不靠桌面版）。
4. Mac 工作日 06:40 自动唤醒（用户自己在终端做一次，要输入 Mac 的登录密码；取代原来的 07:30，立花执行器只要 07:40 之前）：
   `sudo pmset repeat wakeorpoweron MTWRF 06:40:00`（`pmset repeat` 只能有一个重复唤醒）。接着电源、不合盖。
5. J-Quants キー在钥匙串 `qbreak-jquants`（季度复核 2i / 2j / 3b 用；用户自己 `security add-generic-password -s qbreak-jquants -a qbreak -w`）。

## 建法（在 Mac 的 Claude 桌面版对话里说「装本机例行任务」，Claude 照这里做；也可以自己点）
**先核对云端已经改成后备**（顺序很重要：云端还是原来的样子时，两边每天都做日报 / 影子账户，后推的那边 `git pull --rebase` 冲突）：
Claude 有 Claude_Code_Remote 的 `get_trigger` 就**只读**取上表三个云端例行任务，确认每个的 prompt 最前面是
`bash scripts/routines.sh done-today …`、时间是 07:20 / 08:05 / 12:52（JST）；没有这个工具 → 请用户在 claude.ai/code 的 Routines 页面看。
**还没改 → 三个本机任务建成 Paused（暂停）**，告诉用户「日报 / 影子账户的云端指令只能在它们发帖的那个云端对话里改：照 `routines/cloud/README.md` 发那一句；改好之后把本机任务切到 Active」——
不要在云端还没改时就让本机任务按时运行。（万一撞车：`routines.sh push` / `done-today` 发现云端那天已经入库了同一份结果时，
会把 Mac 的提交留在本地备份分支 `backup/routines-<日期>-<提交>`、克隆回到远端，不会一直停着。）

桌面版 **Code** 标签 → 侧栏 **Routines**（或 More 里）→ **New routine** → **Local**，每个任务：
- **Name**：上表的名字（会变成 `~/.claude/scheduled-tasks/<名字>/SKILL.md`）；**Description**：上表的中文名。
- **Instructions**：下面的固定文字（只是指向仓库里的说明书：说明书改了，下一次运行自动用新的）。
  其中「市场风险报告 URL」（日报、影子账户用）**只写在本机任务里、不入库**（公开仓库不写私人链接）：从云端例行任务「模拟盘日报」
  （trig_01MMZVeTtxexr6y4sDhy4rxX）的第 2 步抄（Claude 有 Claude_Code_Remote 的 get_trigger 就只读取它；没有就请用户在 claude.ai/code 的 Routines 页面打开那个例行任务复制给你）。
- 权限模式：默认的逐项确认（不要选跳过全部确认的模式）；模型：默认。
- 工作文件夹：`~/qbreak-sim`（第一次会问要不要信任这个文件夹 → 信任）；**独立 worktree 关掉**（要在 `~/qbreak-sim` 本身提交、推送）。
- **Schedule**：日报 Weekdays 06:45；影子账户 Weekdays 07:45；季度复核：在桌面版对话里请 Claude 设成「每年 1 / 4 / 7 / 10 月 12 日 09:56」
  （选择器里没有每季；能设就设），不能就选 Daily 09:56（说明书第 0 步：今天不是 1 / 4 / 7 / 10 月 12 日就跳过）。

固定文字（`<…>` 换成真的值；不要写进仓库）：

```
qbreak 模拟盘日报（Mac 本机例行任务）。市场风险报告 URL：<https://claude.ai/artifact/… 从云端「模拟盘日报」第 2 步抄>
1. 运行 git -C ~/qbreak-sim pull -q --ff-only origin claude/rakuten-auto-trading-review-ka7lf0（失败也继续：第 0 步会判断）。
2. 读 ~/qbreak-sim/quant_breakout/routines/sim_daily.md 全文（开头「Mac 上和云端版不同的」也要遵守），从第 0 步起严格照做（它取代任何旧的步骤说明；不要跳步、不要改策略）。
```

```
qbreak 影子账户判断（Mac 本机例行任务）。市场风险报告 URL：<同上>
1. 运行 git -C ~/qbreak-sim pull -q --ff-only origin claude/rakuten-auto-trading-review-ka7lf0（失败也继续：第 0a 步会判断）。
2. 读 ~/qbreak-sim/quant_breakout/routines/shadow.md 全文（开头「Mac 上和云端版不同的」也要遵守），从第 0a 步起严格照做（它取代任何旧的步骤说明）。
```

```
qbreak 顶底择时季度复核（Mac 本机例行任务）。
1. 运行 git -C ~/qbreak-sim pull -q --ff-only origin claude/rakuten-auto-trading-review-ka7lf0（失败也继续：第 0b 步会判断）。
2. 读 ~/qbreak-sim/quant_breakout/routines/quarterly.md 全文（开头「Mac 上和云端版不同的」也要遵守），从第 0 步起严格照做（它取代任何旧的步骤说明）。
```

第一次：每个任务点 **Run now** 手动跑一次，出现权限确认时选 **always allow**（以后同一个任务自动允许）：Bash（`git …`、
`bash scripts/routines.sh …`、`bash scripts/with_jquants.sh …`）、读写 `~/qbreak-sim` 里的文件、Artifact 的 read / publish
（第一次发布日报 artifact 要批准）、季度复核的 WebSearch / WebFetch（第 3 步日程表；日报 / 影子账户读不到市场风险报告时不要上网补，按说明书「读不到」处理）。不要在说明里写密钥；キー只经钥匙串。
注意：当天已经做过时 Run now 只会打印「跳过」，后面步骤的工具没被问到 → 第一次真正运行时还会停在权限确认（停着等你点；那天由云端后备补上）。
想一次批准完：在还没做的时候 Run now（工作日 06:45 之前 / 云端后备之前）。要写允许规则的话（你同意后由 Claude 写）：
**只写进 `~/qbreak-sim/.claude/settings.local.json`**（只对这个克隆生效；再在 `~/qbreak-sim/.git/info/exclude` 加一行
`.claude/settings.local.json`，免得被提交进公开仓库），**只列确切的命令**，例如 `Bash(bash scripts/routines.sh done-today:*)`、
`Bash(bash scripts/routines.sh push)`、`Bash(bash scripts/routines.sh deps)`、`Bash(bash scripts/routines.sh run run.py sim-day)`；
**绝不**写进全局的 `~/.claude/settings.json`（那会让 Mac 上每个 Claude 会话——包括处理实盘的那个——都自动允许），也不写宽的
`Bash(git:*)`、`Bash(bash scripts/routines.sh run:*)`（= 任意 Python）、`Bash(bash scripts/with_jquants.sh:*)`（= 带着 J-Quants キー跑任意命令）。
季度复核平时第 0 步就跳过，第一次完整运行在下一个复核日。

## 限制
- 桌面版没开、Mac 睡着 / 关机 / 合盖 → 不跑；醒来后只补跑最近一次（说明书第 0 步「做过就跳过」：云端后备已经做了就跳过）。
- 前一个本机任务还在跑时，到点的另一个任务可能被跳过（桌面版的「Review history」里会写原因）→ 云端后备补上。
- Mac 开始得晚（例如睡过了 06:45、07:15 才补跑）时，云端后备可能同时在做同一件事：先推上去的为准；Mac 后推时 `git pull --rebase` 冲突 →
  `routines.sh push` 看到云端那天已经入库了同一种结果 → Mac 的提交留在本地备份分支 `backup/routines-<日期>-<提交>`（不上传）、`~/qbreak-sim`
  回到远端，退出 0（汇报里写明「云端后备已入库，Mac 这次的结果没推」）。Mac 推送失败（网络）留下的、远端还没有的例行任务提交：
  下一次 `done-today` 先推上去。别的情况（有手改的提交 / 本地改动 / 推不上去）→ `done-today` 退出 2（停下）→ 见下面「排查」。
- Mac 没做、云端后备也没做 → 07:40 的执行器等不到当天的日报（模拟操盘最多等 50 分钟、立花等到 08:30），用手上最新的输入继续；09:30 自检会提醒。

## 排查
- 「例行任务今天跑了吗」→ `bash scripts/routines.sh check`（只读：`~/qbreak-sim`、推送权限、桌面版、三个本机任务、钥匙串、唤醒、最近 5 个工作日每天是 Mac 还是云端做的）。
- 桌面版：Code → Routines → 点任务 → Review history（每次运行、跳过的原因）；运行的会话在侧栏 **Scheduled** 下。
- `~/qbreak-sim` 有本地改动 / 没推上去的提交（`done-today` 退出码 2）：在 Mac 对话里看是哪一次例行任务留下的，用户决定怎么处理（Claude 不自动 reset / 丢弃）。
  「那天云端后备已经入库了同一份结果」与「Mac 的例行任务结果还没推上去」这两种 `routines.sh` 自己处理（上面「限制」）；剩下的（手改的提交、
  本地改动、推不上去）才会停着：用户同意后先留一份（`git -C ~/qbreak-sim branch backup/<日期>`）再
  `git -C ~/qbreak-sim reset --hard origin/claude/rakuten-auto-trading-review-ka7lf0`；Mac 的才是唯一的那份 → `bash scripts/routines.sh push`。
- 停用：桌面版里把任务切到 Paused；完全停掉云端后备要用户在对话里另外确认。
