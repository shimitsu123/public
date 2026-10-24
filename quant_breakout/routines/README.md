# 例行任务在 Mac 上（Claude 桌面版的本机任务；2026-10-09 起）

用户 2026-10-09「连云端例行任务也搬到 Mac」。这个仓库的三个例行任务改在 Mac 的 **Claude 桌面版「本机任务」（Local routine）** 里跑，
工作文件夹 `~/qbreak-sim`；云端同名例行任务原是后备，**2026-10-19 已删**（用户：以本地为准）→ 没有后备，Mac 没做的那天在 Mac 对话里说「补跑」。

为什么这样做（官方文档，2026-10-09 检索，仅对本次检索时点有效）：
- 云端例行任务（Routine）只能在 Anthropic 云端（或 Team / Enterprise 的自建环境）运行，不能指派到个人的 Mac（https://code.claude.com/docs/en/routines）。
- Mac 上能定时跑 Claude 的是桌面版的本机任务（https://code.claude.com/docs/en/desktop-scheduled-tasks）：要 Claude Desktop ≥ 1.1.5368；
  **只在桌面版开着、Mac 醒着时运行**（每分钟检查一次，每个任务有几分钟固定的错峰）；睡过了的时间：醒来 / 打开桌面版时只补跑**最近一次**
  （7 天以内）；合盖照样会睡。`claude -p`（launchd 调用）默认不能发布 artifact，所以不用它。

## 本机任务（原来三个；影子账户 2026-10-24 停用 → 现在两个）

| 本机任务（建议的名字） | 说明书（每次照做） | 时间（JST） |
|---|---|---|
| `qbreak-sim-daily` 模拟盘日报（2026-10-20 起不发布日报，只算执行器的输入） | `routines/sim_daily.md` | 周一至五（Weekdays）06:45 |
| ~~`qbreak-shadow` 影子账户判断~~ **停用 2026-10-24**（用户「不要影子账户任务」：不再建、不再跑、补跑也不做） | `routines/shadow.md`（只留作历史） | ~~周一至五（Weekdays）07:45~~ |
| `qbreak-quarterly` 顶底择时季度复核 | `routines/quarterly.md` | 1 / 4 / 7 / 10 月 12 日 09:56 |

**云端后备已删（2026-10-19 用户：「云端的现在定时任务删除了 以本地为准」）**：Mac 没做的那天没有人补 → 在 Mac 对话里说「补跑」
（Claude 照说明书在 `~/qbreak-sim` 里做；交易日 07:40 之前补完执行器当天就用上，之后补的下一个交易日才用）。说明书 `routines/cloud/` 也删了。

- 07:40 的执行器等的就是日报入库（`var/out/unified_today.json` 的 date = 今天）：Mac 06:45 开始，通常 07:10 前入库；Mac 没做 → 没有后备（执行器等到 08:40 前后，用手上最新的输入继续）。
- 「做过就跳过」= 说明书最前面的 `bash scripts/routines.sh done-today sim|shadow|quarterly`：
  退出码 0 = 今天已经由 Mac 或云端入库（打印是谁做的）→ 跳过；1 = 还没做 → 照常做；
  2 = 这个克隆拉不下来（本地改动 / 没推上去的提交 / 网络）或 git 身份没设 → Mac 的本机任务停下汇报（没有云端后备：要补在 Mac 对话里说「补跑」）。
- 谁做的看提交信息的开头：Mac 写 `sim(mac):` / `shadow(mac):` / `季度复核(mac)：`，云端照旧 `sim:` / `shadow:` / `季度复核：`。
- 日报在休市的工作日也照常做（和云端以前一样：处理上一个交易日的收盘；2026-10-20 起不发布日报 artifact：只算 07:40 执行器的输入并入库）。
- 影子账户判断 2026-10-24 起停用：`done-today shadow` 打印「已停用」、退出 0；`save shadow` 不入库；`check` 显示「影子账户：…停用」（桌面版排程里还有它 → [!] 提醒删掉），09:30 自检 / 自动停止 / 允许规则对照都不再看它；以前的 `shadow:` / `shadow(mac):` 提交照旧在「最近 5 个工作日」里读到 10-23 为止。
- 09:30 自检（`com.qbreak.watchdog`）多看一项：交易日、今天的日报没入库 → 手机通知「今天的模拟盘日报没入库（Mac 的本机例行任务没跑？桌面版开着吗？）」。
- 09:30 自检的推送还看本机任务本身（2026-10-16 起；读桌面版的运行记录，只读）：交易日、本机任务卡住了（多半在等权限确认）/ 今天到点 30 分钟还没跑 /
  今天晚 30 分钟以上才开始 → 那条推送里加一行「★ 本机例行任务：…」（例：「日报卡住了（多半在等权限确认；10/19 06:32 起）→ 在桌面版 Code → Routines
  打开那次运行点允许（或停止它）；今天的要补：在 Mac 对话里说「补跑」」），通过的标题后面加「· ★ 本机例行任务」。**不算没通过**（例行任务不下单；
  真影响 07:40 执行器的「日报没入库」上面那条已经算没通过），也不为它另推：同一天的「通过」照旧只推一次。读不到运行记录 / 不是 Mac → 不说。

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
（云端后备已删，不用再核对云端。旧的 Mac 提交与远端撞车时 `routines.sh push` / `done-today` 照旧把 Mac 的提交留在本地备份分支、克隆回到远端。）

桌面版 **Code** 标签 → 侧栏 **Routines**（或 More 里）→ **New routine** → **Local**，每个任务：
- **Name**：上表的名字（会变成 `~/.claude/scheduled-tasks/<名字>/SKILL.md`）；**Description**：上表的中文名。
- **Instructions**：下面的固定文字（只是指向仓库里的说明书：说明书改了，下一次运行自动用新的）。
  其中「市场风险报告 URL」（日报、影子账户用）**只写在本机任务里、不入库**（公开仓库不写私人链接）：从云端例行任务「模拟盘日报」
  （trig_01MMZVeTtxexr6y4sDhy4rxX）的第 2 步抄（Claude 有 Claude_Code_Remote 的 get_trigger 就只读取它；没有就请用户在 claude.ai/code 的 Routines 页面打开那个例行任务复制给你）。
- 权限模式：用户 2026-10-17 决定「跳过全部确认」（`~/qbreak-sim` 文件夹在桌面版记的是 bypassPermissions），但 **2026-10-21 查到这个文件夹设置管不到本机任务**：桌面版启动本机任务的运行用的是每个任务自己的权限模式（三个任务都是逐项确认 `--permission-mode=default`）→ 说明书以外的命令照样停在权限确认上（10/19〜10/21 的日报 / 影子账户就这样卡住）。根治 = 用户在桌面版 Code → Routines → 每个任务的权限改成跳过确认（Bypass permissions；Claude 不改）；改之前：说明书的命令都在允许规则里（`python -m qbreak.routines allow-missing` = []），说明书写明只运行写出的命令、看文件用 Read 工具，卡住 30 分钟以上的运行由每 15 分钟的检查自动停止（见下面「限制」）；模型：默认。
- 工作文件夹：`~/qbreak-sim`（第一次会问要不要信任这个文件夹 → 信任）；**独立 worktree 关掉**（要在 `~/qbreak-sim` 本身提交、推送）。
- **Schedule**：日报 Weekdays 06:45；影子账户 Weekdays 07:45；季度复核：在桌面版对话里请 Claude 设成「每年 1 / 4 / 7 / 10 月 12 日 09:56」
  （选择器里没有每季；能设就设），不能就选 Daily 09:56（说明书第 0 步：今天不是 1 / 4 / 7 / 10 月 12 日就跳过）。

固定文字（`<…>` 换成真的值；不要写进仓库）：

```
qbreak 模拟盘日报（Mac 本机例行任务）。市场风险报告 URL：<https://claude.ai/artifact/… 从云端「模拟盘日报」第 2 步抄>
命令规矩（无人值守：只有和允许规则一字不差的命令才会自动执行，否则会停在权限确认、整个任务卡住）：每条 Bash 命令一字不差照抄这里和说明书写的（说明书写成 `cd ~/qbreak-sim/quant_breakout && …` 的就照抄这个样子）；不要自己再加 `; echo …`、`| …`、`2>&1`、`|| …` 之类，不要改写路径（`~/qbreak-sim` 就写 `~/qbreak-sim`）；要知道成功没有，看工具返回的退出码与输出。
1. 运行 git -C ~/qbreak-sim pull -q --ff-only origin claude/rakuten-auto-trading-review-ka7lf0（失败也继续：第 0 步会判断）。
2. 读 ~/qbreak-sim/quant_breakout/routines/sim_daily.md 全文（开头「Mac 上和云端版不同的」也要遵守），从第 0 步起严格照做（它取代任何旧的步骤说明；不要跳步、不要改策略）。
```

（影子账户判断的固定文字 2026-10-24 删掉：用户停用了这个任务，「装本机例行任务」不再建它；原文在 git 历史里。）

```
qbreak 顶底择时季度复核（Mac 本机例行任务）。
命令规矩（无人值守：只有和允许规则一字不差的命令才会自动执行，否则会停在权限确认、整个任务卡住）：每条 Bash 命令一字不差照抄这里和说明书写的（说明书写成 `cd ~/qbreak-sim/quant_breakout && …` 的就照抄这个样子）；不要自己再加 `; echo …`、`| …`、`2>&1`、`|| …` 之类，不要改写路径（`~/qbreak-sim` 就写 `~/qbreak-sim`）；要知道成功没有，看工具返回的退出码与输出。
1. 运行 git -C ~/qbreak-sim pull -q --ff-only origin claude/rakuten-auto-trading-review-ka7lf0（失败也继续：第 0b 步会判断）。
2. 读 ~/qbreak-sim/quant_breakout/routines/quarterly.md 全文（开头「Mac 上和云端版不同的」也要遵守），从第 0 步起严格照做（它取代任何旧的步骤说明）。
```

第一次：每个任务点 **Run now** 手动跑一次，出现权限确认时选 **always allow**（以后同一个任务自动允许）：Bash（`git …`、
`bash scripts/routines.sh …`、`bash scripts/with_jquants.sh …`）、读写 `~/qbreak-sim` 里的文件、Artifact 的 read / publish
（第一次发布日报 artifact 要批准）、季度复核的 WebSearch / WebFetch（第 3 步日程表；日报 / 影子账户读不到市场风险报告时不要上网补，按说明书「读不到」处理）。不要在说明里写密钥；キー只经钥匙串。
注意：当天已经做过时 Run now 只会打印「跳过」，后面步骤的工具没被问到 → 第一次真正运行时还会停在权限确认（停着等你点；那天没人补）。
想一次批准完：在还没做的时候 Run now（工作日 06:45 之前）。要写允许规则的话（你同意后由 Claude 写）：
**只写进 `~/qbreak-sim/.claude/settings.local.json`**（只对这个克隆生效；再在 `~/qbreak-sim/.git/info/exclude` 加一行
`.claude/settings.local.json`，免得被提交进公开仓库），**只列确切的命令**，例如 `Bash(bash scripts/routines.sh done-today:*)`、
`Bash(bash scripts/routines.sh push)`、`Bash(bash scripts/routines.sh deps)`、`Bash(bash scripts/routines.sh run run.py sim-day)`；
**绝不**写进全局的 `~/.claude/settings.json`（那会让 Mac 上每个 Claude 会话——包括处理实盘的那个——都自动允许），也不写宽的
`Bash(git:*)`、`Bash(bash scripts/routines.sh run:*)`（= 任意 Python）、`Bash(bash scripts/with_jquants.sh:*)`（= 带着 J-Quants キー跑任意命令）。
季度复核平时第 0 步就跳过，第一次完整运行在下一个复核日。
**说明书的命令在不在允许规则里**（2026-10-16 起）：`bash scripts/routines.sh check` 把说明书 `sim_daily.md`、`quarterly.md`（和上面固定文字的第 1 步；`shadow.md` 2026-10-24 停用、不再对照）要运行的 Bash 命令
逐条和 `~/qbreak-sim/.claude/settings.local.json` 的 permissions.allow（加上桌面版里那个任务自己「always allow」过的）对照，对不上的逐条报 [★]
（只打印说明书里的命令，不打印规则文件的别的内容）；要加的规则：`python -m qbreak.routines allow-missing`（JSON 数组，在 `quant_breakout/` 下运行、只读）——
**用户同意后**由 Claude 加进 `~/qbreak-sim/.claude/settings.local.json`。对照法近似 Claude Code：一字不差，或以 `:*` / ` *` 结尾的前缀（`*` 也可以在中间）；
用 `&&` 连起来的命令拆开后每段都要对得上（`cd ~/qbreak-sim…` 那段不用规则）；提交信息里的 `<…>` 要规则在那里有 `*`。
**2026-10-23 起**说明书不再写「cd … && git …」与带 `$(…)` 的 until 循环（Claude Code 对它们一律要人确认、允许规则也放不过：10/21〜10/23 每天停在入库与等日报那一步）→ 入库 `routines.sh save sim|shadow|quarterly`、等日报 `routines.sh wait-sim`，各一条规则。说明书改了、加了命令 → 先跑一次 check，缺的规则加好再让本机任务跑。
2026-10-12 实际遇到：本机任务每天准时启动，但执行任务的 Claude 在第 1 步的命令后面自己加了 `; echo rc=$?` → 和允许规则对不上 → 停在权限确认、什么都没做（全靠云端后备）。所以上面的固定文字都有「命令规矩」那一行；说明书里带重定向 / 循环的命令（日报的两条 `backtest … > var/out/backtest_*.txt`、影子账户等日报的 `until …; done`）也要照原文一字不差写进允许规则。

## 限制
- 桌面版没开、Mac 睡着 / 关机 / 合盖 → 不跑；醒来后只补跑最近一次（说明书第 0 步「做过就跳过」）。
- 前一个本机任务还在跑时，到点的另一个任务可能被跳过（桌面版的「Review history」里会写原因）→ 没有云端后备：在 Mac 对话里说「补跑」。
- **本机任务都要能在没人点「允许」的情况下跑完**：说明书里的每条命令都在允许规则里（上面「建法」的做法）；把任务的权限模式改成不用确认
  要用户自己决定（「建法」默认不选）。有一条命令要确认，无人值守的运行就停在那里一直等、进程不退出；**这次运行结束之前，桌面版不会再启动同一个任务**
  （之后每次到点都记成跳过，Review history 里是「上一次运行还没结束」）→ 以后每天都不跑（2026-10-19 起没有云端后备）。2026-10-12 的三次运行就这样一直挂到 10-16
  （10-13〜10-16 的日报 / 影子账户全是云端后备做的）；`routines.sh check` 会报「…那次一直没动」「之后应该跑的 … 没跑」。
  恢复：桌面版 Code → Routines（或侧栏 Scheduled）打开卡住的那次运行、停止它，再把它停下的那条命令一字不差地加进允许规则；
  停止之后桌面版会马上补跑最近错过的一次（第 0 步「做过就跳过」）。
  **2026-10-21 起自动停止**：每 15 分钟（`liveu.sh news`，LaunchAgent `com.qbreak.news`）跑 `python -m qbreak.routines reap`：本机任务（停用的影子账户除外）最近一次运行停在没有结果的工具调用上 30 分钟以上、它的进程还在、而且没有子进程（真的在跑命令时有；等权限确认时没有）→ 停止那个进程、推一条手机通知（「qbreak 本机例行任务「日报」卡住了：已自动停止」）；一个任务一天最多 2 次；只停工作文件夹对得上的那个会话进程，不碰别的对话；记录在数据目录 `out/routines_reap.json`。`python -m qbreak.routines reap --dry` = 只说会停哪个。停止之后停下的那条命令照旧要看要不要加进允许规则（用户同意）。
- Mac 开始得晚（例如睡过了 06:45、07:15 才补跑）时，（2026-10-19 以前）云端后备可能同时在做同一件事：先推上去的为准（现在没有云端后备，这段只在远端已经有同一种结果时才会遇到）；Mac 后推时 `git pull --rebase` 冲突 →
  `routines.sh push` 看到云端那天已经入库了同一种结果 → Mac 的提交留在本地备份分支 `backup/routines-<日期>-<提交>`（不上传）、`~/qbreak-sim`
  回到远端，退出 0（汇报里写明「云端后备已入库，Mac 这次的结果没推」）。Mac 推送失败（网络）留下的、远端还没有的例行任务提交：
  下一次 `done-today` 先推上去。别的情况（有手改的提交 / 本地改动 / 推不上去）→ `done-today` 退出 2（停下）→ 见下面「排查」。
- Mac 没做（没有云端后备）→ 07:40 的执行器等不到当天的日报（模拟操盘最多等 50 分钟、立花等到 08:30），用手上最新的输入继续；09:30 自检会提醒。

## 排查
- 「例行任务今天跑了吗」→ `bash scripts/routines.sh check`（只读：`~/qbreak-sim`、推送权限、桌面版、本机任务建了没有（影子账户显示「停用」）、
  本机任务按时跑了没有 / 有没有卡住的运行（读桌面版的运行记录；读不到就跳过）、说明书的命令在不在允许规则里（对不上的逐条 [★]）、钥匙串、唤醒、
  最近 5 个工作日每天是 Mac 还是云端做的（看三个克隆里远端记录最新的那个；不 fetch））。
- 桌面版：Code → Routines → 点任务 → Review history（每次运行、跳过的原因）；运行的会话在侧栏 **Scheduled** 下。
- `~/qbreak-sim` 有本地改动 / 没推上去的提交（`done-today` 退出码 2）：在 Mac 对话里看是哪一次例行任务留下的，用户决定怎么处理（Claude 不自动 reset / 丢弃）。
  「那天云端后备已经入库了同一份结果」与「Mac 的例行任务结果还没推上去」这两种 `routines.sh` 自己处理（上面「限制」）；剩下的（手改的提交、
  本地改动、推不上去）才会停着：用户同意后先留一份（`git -C ~/qbreak-sim branch backup/<日期>`）再
  `git -C ~/qbreak-sim reset --hard origin/claude/rakuten-auto-trading-review-ka7lf0`；Mac 的才是唯一的那份 → `bash scripts/routines.sh push`。
- 停用：桌面版里把任务切到 Paused。（云端后备 2026-10-19 已删。）
