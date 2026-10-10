# 影子账户判断（Mac 本机例行任务；周一至五 07:45 JST）

云端例行任务「影子账户判断（判断型选股，只记录）」（trig_01WndiH4mZSiFkeExpsukNm4）的 Mac 版（2026-10-09 用户「连云端例行任务也搬到 Mac」）。
怎么在 Claude 桌面版里建这个本机任务：同目录的 `README.md`。云端那个例行任务改成后备（Mac 当天做过就跳过）。

## Mac 上和云端版不同的只有这些（其余步骤、禁止事项、汇报格式与云端版原文相同）
- 工作目录：`~/qbreak-sim`（例行任务专用的克隆）；命令都在 `~/qbreak-sim/quant_breakout` 下运行。`~/qbreak-src`、`~/qbreak-dev` 里什么都不做。
- Python：一律 `bash scripts/routines.sh run <参数>`（= 在 `~/qbreak-sim` 里、去掉 `QBREAK_HOME` 的 `~/.qbreak/venv/bin/python`）；
  每次 Bash 调用的环境变量不会留到下一次，所以不要只 `unset QBREAK_HOME` 一次。它在 `~/qbreak-sim` 以外拒绝运行 → 照实汇报、停下。
- 提交信息开头写 `shadow(mac):`（云端后备写 `shadow:`）；提交信息不写模型名（桌面版要加署名行的话只能用不含模型名的那种；不确定就不加）。
- 推送：`bash scripts/routines.sh push`（`git pull --rebase` → `git push`，失败 2 / 4 / 8 / 16 秒后重试；只推这个分支、不 force）；它停下 → 照实汇报。
- 不 `git reset` / `git stash` / 丢弃任何改动；给 Artifact 工具的 `file_path` 用绝对路径，汇报里只写 `~/qbreak-sim/…`。
- 市场风险报告的 URL 写在这个本机任务的说明（Instructions）里（不入库）；那里没有 → 用 Artifact 工具 `list` 找标题含「市场风险报告」的那个。
  日报 artifact：https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ

## 步骤
例行唤醒：影子账户（判断型选股，只前向记录，不影响模拟盘与交易）。用户 2026-09-26 在另一个对话里要求并确认；规则与评估标准见
`~/qbreak-sim/quant_breakout/scripts/shadow_account.py` 开头，已事先登记（提交 673dad6），不得改。现在约 07:45 JST。

0a. 做过就跳过：`cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh done-today shadow`（它先 `git pull --ff-only`）。
   退出码 0（今天的判断已经由 Mac 或云端入库）→ 只回复一行「影子账户：<它打印的那一行>：跳过」并结束；
   退出码 2（`~/qbreak-sim` 拉不下来 / git 身份没设）→ 只回复「★ 影子账户（Mac）今天没做：<它打印的原因>（云端后备会做）」并结束；退出码 1 → 继续。
0. 用 bash 运行 `TZ=Asia/Tokyo date '+%F %H:%M %a'`。今天不是日本交易日，或不在 2026-09-28〜2026-12-24 之间（2026-12-25 起见第 7 步）→ 只回复一行「影子账户：今天不做（原因）」并结束。
1. 代码已由第 0a 步拉好；确认今天的模拟盘日报已入库：`cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh done-today sim` 打印「今天已经做过」（退出码 0）。
   还不是：用 Bash 的 run_in_background 跑一个「每 2 分钟看一次，直到日报入库或到 08:40 JST 为止」的 until 循环，等它结束：
   `cd ~/qbreak-sim/quant_breakout && until bash scripts/routines.sh done-today sim >/dev/null 2>&1 || [ "$(TZ=Asia/Tokyo date +%H%M)" -ge 0840 ]; do sleep 120; done`
   之后再运行一次 `bash scripts/routines.sh done-today sim`：到 08:40 还不是今天 → 回复「影子账户：今天的日报没入库，不做判断」并结束（不补）。
2. `cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh run scripts/shadow_account.py step`（按真实开盘价撮合之前的单、公司行为、收盘估值、与规则账户逐日对比）。
3. 判断：读 var/out/report_data.json（牛熊、市场状态 / 新仓倍数、宏观、威胁指数、经济威胁消息汇总 news、能源消费 energy、主题 / 业种强弱、候补队列、规则账户今天的单 todo）、
   今天早上读过的市场风险报告（没读过就 Artifact read 市场风险报告（URL 见上），只读）、var/out/shadow_today.json（影子账户的持仓与现金）。
   按你自己的判断（可以和规则不同，也可以不动）决定今天 09:00 开盘的买卖；不另外上网查个股消息。
4. 写 /tmp/shadow_decision.json：`{"for_date": "今天 YYYY-MM-DD", "view": "一句话市场判断", "orders": [{"ticker": "7203.T", "side": "BUY 或 SELL", "shares": 股数, "reason": "一句话理由"}], "inputs": "用了哪些信息"}`。
   只能用日経225 成分股与 1655.T / 1329.T；个股 100 股一单位、1655.T 10 口一单位；个股最多 4 只、单只买入后 ≤ 权益 35%；不加杠杆；不动就写 `"orders": []`。
   然后 `cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh run scripts/shadow_account.py decide --file /tmp/shadow_decision.json`：不合格会列出原因、整份不记 → 改好再交；
   必须在 09:00 JST 之前，过了就不交（当天不下单，照实汇报）。
5. 入库：`cd ~/qbreak-sim && git add quant_breakout/var/state/shadow_state.json quant_breakout/var/out/shadow_* quant_breakout/var/out/report.html quant_breakout/var/out/report_data.json && git commit -m "shadow(mac): <今天 YYYY-MM-DD> 判断"`
   （署名行见上）→ `cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh push`（先 `git pull --rebase` 再 push 到 claude/rakuten-auto-trading-review-ka7lf0；失败按 2s/4s/8s/16s 重试）；
   仍失败醒目写「★ 影子账户未能入库」。
6. 发布日报（含「影子账户」一栏）：Artifact read https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ ，然后 publish `file_path=<~/qbreak-sim/quant_breakout/var/out/report.html 的绝对路径>`
   并传 `url=https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ`（原地更新，不要新建）。
7. 2026-12-25 起的第一次运行（代码已由第 0a 步拉好）：`cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh run scripts/shadow_account.py step && bash scripts/routines.sh run scripts/shadow_account.py evaluate`
   （3 个月评估，标准见该文件开头第四节；结论只是记录，不改模拟盘），把 var/out/shadow_eval.md、var/out/shadow_eval.json 与影子账户的文件按第 5 步入库；
   汇报第一行写「影子账户评估：<结论>；记录已结束，可以删除这个例行任务」，再写累计收益差 ±x.xx pp、日超额收益平均 ±x.xx 基点 / 天与 95% 区间、两个账户的最大回撤 %、判断覆盖率 %。
   之后每次只回复一行「影子账户：记录已结束，可以删除这个例行任务」（本机任务在桌面版的 Routines 里删；云端后备由用户在对话里确认后删）。
8. 中文汇报 ≤8 行，数字都带单位（¥、%、pp、股、口、JST）：影子账户权益 ¥（累计 ±x.xx%）、规则账户 ¥、差 ±x.xx pp；昨天的成交 / 取消（代码、买卖、x 股、成交价 ¥）；
   今天的判断一句话与单子（代码 / 买卖 / x 股 / 理由），或没有记录的原因。

禁止：改动或补写 var/out/shadow_decisions.jsonl、var/out/shadow_trades.csv、var/out/shadow_equity.csv 的已有内容；改 scripts/shadow_account.py 的规则与评估标准；
改规则账户（模拟盘）的任何配置或状态（var/sim.json、var/state/unified_state.json 等）；为影子账户另外上网查个股消息；09:00 JST 之后交判断；使用合成数据。
（Mac 另加）在 `~/qbreak-sim` 以外运行这些命令；`git reset` / `git stash` / 丢弃改动 / `git push --force` / 推到别的分支；打印或回显任何密钥的值。
