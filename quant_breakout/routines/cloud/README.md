# 云端例行任务改成「后备」（2026-10-09 用户「连云端例行任务也搬到 Mac」）

例行任务的指令（prompt）：2026-10-10 实测别的对话（Mac 的 Claude 经 RemoteTrigger）也能改；原来写的「只能在发帖的对话里改」不对。

| 云端例行任务 | 发帖的对话 | 后备版 | 状态 |
|---|---|---|---|
| 顶底择时季度复核 trig_01BA4ugENPhSrYW3QSd5djK6 | 改代码 / 研究的那个云端对话 | 最前面「做过就跳过」、时间 1 / 4 / 7 / 10 月 12 日 12:52 | 2026-10-09 已改 |
| 模拟盘日报 trig_01MMZVeTtxexr6y4sDhy4rxX | 每天日报发帖的那个云端对话 | [`sim_daily_cloud.md`](sim_daily_cloud.md)，时间周一至五 07:20 | 2026-10-10 已改 |
| 影子账户判断 trig_01WndiH4mZSiFkeExpsukNm4 | 同上（每天日报发帖的那个对话） | [`shadow_cloud.md`](shadow_cloud.md)，时间周一至五 08:05 | 2026-10-10 已改 |

**怎么改（你在 claude.ai/code 打开每天日报发帖的那个对话，发这一句）：**

> 把这个对话的两个例行任务改成后备：模拟盘日报（trig_01MMZVeTtxexr6y4sDhy4rxX）的指令换成仓库 quant_breakout/routines/cloud/sim_daily_cloud.md 里「指令」那一节的全文、时间改成 CRON_TZ=Asia/Tokyo 20 7 * * 1-5；影子账户判断（trig_01WndiH4mZSiFkeExpsukNm4）的指令换成 quant_breakout/routines/cloud/shadow_cloud.md 里「指令」那一节的全文、时间改成 CRON_TZ=Asia/Tokyo 5 8 * * 1-5。先 git pull 读文件，逐字照抄，改完用 get_trigger 读回来确认。

后备版 = 原来的指令一字不改，只在最前面加第 0 步（`bash scripts/routines.sh done-today …`：Mac 今天做过 → 跳过；没做 → 照原来的步骤补做）、开头的「现在约 … JST」改成新的时间。

**顺序很重要**：云端还没改成后备时，Mac 上的三个本机任务先建成 Paused（暂停），等上表两个都改好再切到 Active（`routines/README.md`）——
不然两边每天都做日报 / 影子账户，后推的一边 `git pull --rebase` 冲突。

完全不要云端（不留后备）：在对话里说「暂停云端的日报 / 影子账户 / 季度复核」（暂停可以从别的对话做；之后 Mac 没做的那天就没有人补）。
