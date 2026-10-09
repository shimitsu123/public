# 云端「影子账户判断」的后备版（trig_01WndiH4mZSiFkeExpsukNm4）

时间：`CRON_TZ=Asia/Tokyo 5 8 * * 1-5`（周一至五 08:05 JST；Mac 的本机任务 07:45 先做）。
和原来的区别只有两处：开头「现在约 07:45 JST」→「08:05」；在第 0 步之后加第 0b 步（Mac 今天做过就跳过）。其余逐字照抄原指令（2026-10-09 读取）。
只能在这个例行任务发帖的那个对话里改（见 README.md）。

## 指令

```text
例行唤醒：影子账户（判断型选股，只前向记录，不影响模拟盘与交易）。用户 2026-09-26 在另一个对话里要求并确认；规则与评估标准见 /home/user/public/quant_breakout/scripts/shadow_account.py 开头，已事先登记（提交 673dad6），不得改。现在约 08:05 JST。
0. 用 bash 运行 TZ=Asia/Tokyo date '+%F %H:%M %a'。今天不是日本交易日，或不在 2026-09-28〜2026-12-24 之间（2026-12-25 起见第 7 步）→ 只回复一行「影子账户：今天不做（原因）」并结束。
0b. 后备模式（2026-10-09 用户「连云端例行任务也搬到 Mac」：这个任务主要在 Mac 的 Claude 桌面版本机任务里跑（周一至五 07:45，~/qbreak-sim，说明书 quant_breakout/routines/shadow.md），云端是后备）：cd /home/user/public && git pull --ff-only origin claude/rakuten-auto-trading-review-ka7lf0 && cd quant_breakout && bash scripts/routines.sh done-today shadow。退出码 0（Mac 今天已经做过并入库）→ 只回复一行「影子账户：今天已由 Mac 做过（云端后备跳过）」并结束，不做下面任何步骤。退出码 1 或 2 → 照下面 1〜8 步做（云端补做；提交信息照旧「shadow: …」），汇报第一行写「★ 云端后备补做了今天的影子账户判断（Mac 的本机任务没做）」。
1. cd /home/user/public && git pull --ff-only origin claude/rakuten-auto-trading-review-ka7lf0；确认 quant_breakout/var/out/unified_today.json 的 date 是今天（今天的模拟盘日报已入库）。还不是今天：用 Bash 的 run_in_background 跑一个「每 2 分钟 git pull 一次，直到 date 变成今天或到 08:40 JST 为止」的 until 循环，等它结束；到 08:40 还不是今天 → 回复「影子账户：今天的日报没入库，不做判断」并结束（不补）。
2. cd /home/user/public/quant_breakout && python scripts/shadow_account.py step（按真实开盘价撮合之前的单、公司行为、收盘估值、与规则账户逐日对比）。
3. 判断：读 var/out/report_data.json（牛熊、市场状态 / 新仓倍数、宏观、威胁指数、经济威胁消息汇总 news、能源消费 energy、主题 / 业种强弱、候补队列、规则账户今天的单 todo）、今天早上读过的市场风险报告（没读过就 Artifact read https://claude.ai/artifact/7yUZBHV5FjcL4EV6HFEPMK，只读）、var/out/shadow_today.json（影子账户的持仓与现金）。按你自己的判断（可以和规则不同，也可以不动）决定今天 09:00 开盘的买卖；不另外上网查个股消息。
4. 写 /tmp/shadow_decision.json：{"for_date": "今天 YYYY-MM-DD", "view": "一句话市场判断", "orders": [{"ticker": "7203.T", "side": "BUY 或 SELL", "shares": 股数, "reason": "一句话理由"}], "inputs": "用了哪些信息"}。只能用日経225 成分股与 1655.T / 1329.T；个股 100 股一单位、1655.T 10 口一单位；个股最多 4 只、单只买入后 ≤ 权益 35%；不加杠杆；不动就写 "orders": []。然后 python scripts/shadow_account.py decide --file /tmp/shadow_decision.json：不合格会列出原因、整份不记 → 改好再交；必须在 09:00 JST 之前，过了就不交（当天不下单，照实汇报）。
5. 入库：cd /home/user/public && git add quant_breakout/var/state/shadow_state.json quant_breakout/var/out/shadow_* quant_breakout/var/out/report.html quant_breakout/var/out/report_data.json && git commit -m "shadow: <今天 YYYY-MM-DD> 判断"（末尾附当前 system-reminder 的署名行）；先 git pull --rebase 再 push 到 claude/rakuten-auto-trading-review-ka7lf0；失败按 2s/4s/8s/16s 重试，仍失败醒目写「★ 影子账户未能入库」。
6. 发布日报（含「影子账户」一栏）：Artifact read https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ，然后 publish file_path=/home/user/public/quant_breakout/var/out/report.html 并传 url=https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ（原地更新，不要新建）。
7. 2026-12-25 起的第一次运行：cd /home/user/public && git pull --ff-only origin claude/rakuten-auto-trading-review-ka7lf0 && cd quant_breakout && python scripts/shadow_account.py step && python scripts/shadow_account.py evaluate（3 个月评估，标准见该文件开头第四节；结论只是记录，不改模拟盘），把 var/out/shadow_eval.md、var/out/shadow_eval.json 与影子账户的文件按第 5 步入库；汇报第一行写「影子账户评估：<结论>；记录已结束，可以删除这个例行任务」，再写累计收益差 ±x.xx pp、日超额收益平均 ±x.xx 基点 / 天与 95% 区间、两个账户的最大回撤 %、判断覆盖率 %。之后每次只回复一行「影子账户：记录已结束，可以删除这个例行任务」。
8. 中文汇报 ≤8 行，数字都带单位（¥、%、pp、股、口、JST）：影子账户权益 ¥（累计 ±x.xx%）、规则账户 ¥、差 ±x.xx pp；昨天的成交 / 取消（代码、买卖、x 股、成交价 ¥）；今天的判断一句话与单子（代码 / 买卖 / x 股 / 理由），或没有记录的原因。
禁止：改动或补写 var/out/shadow_decisions.jsonl、var/out/shadow_trades.csv、var/out/shadow_equity.csv 的已有内容；改 scripts/shadow_account.py 的规则与评估标准；改规则账户（模拟盘）的任何配置或状态（var/sim.json、var/state/unified_state.json 等）；为影子账户另外上网查个股消息；09:00 JST 之后交判断；使用合成数据。
```
