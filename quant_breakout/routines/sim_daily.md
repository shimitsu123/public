# 模拟盘日报（Mac 本机例行任务；周一至五 06:45 JST）

云端例行任务「模拟盘日报（一个账户，汇报带单位）」（trig_01MMZVeTtxexr6y4sDhy4rxX）的 Mac 版（2026-10-09 用户「连云端例行任务也搬到 Mac」）。
怎么在 Claude 桌面版里建这个本机任务：同目录的 `README.md`。云端那个例行任务改成后备（Mac 当天做过就跳过）。

## Mac 上和云端版不同的只有这些（其余步骤、禁止事项、汇报格式与云端版原文相同）
- 工作目录：`~/qbreak-sim`（例行任务专用的克隆）；命令都在 `~/qbreak-sim/quant_breakout` 下运行。`~/qbreak-src`、`~/qbreak-dev` 里什么都不做。
- Python：一律 `bash scripts/routines.sh run <参数>`（= 在 `~/qbreak-sim` 里、去掉 `QBREAK_HOME` 的 `~/.qbreak/venv/bin/python`；
  这些命令本来就写仓库的 `var/`）。每次 Bash 调用的环境变量不会留到下一次，所以不要只 `unset QBREAK_HOME` 一次，一律经 `routines.sh run`；
  它在 `~/qbreak-sim` 以外拒绝运行 → 照实汇报、停下。
- 依赖：`bash scripts/routines.sh deps`（按 `requirements.lock` 装，没有 lock 才 `requirements.txt`），不另外 `pip install`。
- 提交信息开头写 `sim(mac):`（云端后备写 `sim:`；`routines.sh` 据此分辨是谁做的）。提交信息不写模型名：桌面版要加署名行的话，
  只能用不含模型名的那种；不确定就不加署名行。
- 推送：`bash scripts/routines.sh push`（`git pull --rebase` → `git push`，失败 2 / 4 / 8 / 16 秒后重试；只推这个分支、不 force、
  不改用别的分支）。它停下（冲突、没提交的改动、提交信息带模型名、作者不是设好的 git 身份）→ 不要自己绕过，照实汇报。
- 不 `git reset` / `git stash` / `git checkout -- <文件>` / 丢弃任何改动；拉不下来就停下汇报（云端后备会做）。
- 给 Artifact 工具的 `file_path` 用绝对路径（`echo ~/qbreak-sim/quant_breakout/var/out/report.html` 的结果）；汇报里只写 `~/qbreak-sim/…`
  （不写出 Mac 的用户名）。
- 市场风险报告的 URL 写在这个本机任务的说明（Instructions）里（不入库：公开仓库不写私人链接）；那里没有 → 用 Artifact 工具 `list`
  找标题含「市场风险报告」的那个；都找不到 → 按第 2 步「读不到」处理。日报 artifact：https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ
  （README.md「日报」那一行的同一个链接）。

## 步骤
例行唤醒：现在约 06:45 JST。按下面步骤执行今天的模拟盘运行（代码在 `~/qbreak-sim/quant_breakout`，分支 `claude/rakuten-auto-trading-review-ka7lf0`）。
本说明书取代之前的任何步骤说明。不要跳步，不要改策略。

0. 做过就跳过：`cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh done-today sim`（它先 `git pull --ff-only`）。
   - 退出码 0（今天的日报已经由 Mac 或云端入库，或今天是周末）→ 只回复一行「模拟盘日报：<它打印的那一行>：跳过」并结束。
   - 退出码 2（`~/qbreak-sim` 拉不下来 / git 身份没设）→ 只回复「★ 模拟盘日报（Mac）今天没做：<它打印的原因>（云端后备会做；在 Mac 对话里问「例行任务今天跑了吗」）」并结束。
   - 退出码 1 → 继续。
1. 取最新代码与状态（代码已由第 0 步拉好）：`git -C ~/qbreak-sim status -sb` 确认在 `claude/rakuten-auto-trading-review-ka7lf0` 上，然后
   `cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh deps && bash scripts/routines.sh run run.py doctor`
2. 读取市场状态：用 Artifact 工具 read 市场风险报告（URL 见上），找到最新一期（早报或晚报）的「行动四选一」和「24h 崩盘概率」（美股、日本各一组），
   写入 `~/qbreak-sim/quant_breakout/var/market_regime.json`，格式严格为：
   `{"as_of": "YYYY-MM-DD", "source": "市场风险报告 <期号>", "JP": {"action": "观望|加仓观察|减仓观察|避险", "crash_prob": 数字}, "US": {"action": "...", "crash_prob": 数字}}`
   读不到或无法确定时不要编造：写 `{"as_of": "YYYY-MM-DD", "JP": {}, "US": {}}` 并在汇报里说明。
2b. 从同一期报告提取宏观数值，写入 `~/qbreak-sim/quant_breakout/var/macro.json`，格式严格为（数值不带单位与百分号；报告里没有的字段写 null，绝不编造；日期为报告生成日）：
   `{"as_of": "YYYY-MM-DD", "source": "市场风险报告 <期号>", "brent": Brent收盘, "wti": WTI收盘, "us10y": 美10Y收益率%, "us2y": 美2Y%, "fed_hike_prob": 下次FOMC加息(或降息取负)隐含概率%, "fed_next": "下次FOMC决定日 YYYY-MM-DD", "vix": VIX, "hy_oas_bp": HY利差bp, "usdjpy": USD/JPY, "jgb10y": JGB10Y%, "boj_hike_prob": 下次BOJ加息隐含概率%, "boj_next": "下次BOJ决定日 YYYY-MM-DD", "breadth_pct": S&P成分股>50日线比例%}`
   若报告里出现新的 FOMC/BOJ/CPI/NFP 日期且 `var/macro_events.json` 里没有，追加到该文件的 events 数组（`{"date","kind","home"}`），不要删除已有条目（事件窗口目前关闭，日程只用于日报提示）。
   若报告或新闻提到新的指数定期入替（日経225 / NASDAQ-100）且 `var/index_changes.json` 里没有，按该文件格式追加（announced/effective/add/delete/source，代码必须来自公告原文，不确定就不写并在汇报里说明）。
3. 运行当日：`bash scripts/routines.sh run run.py sim-day`（绝不加 `--synthetic` / `--allow-stale`；Yahoo 被拦截时程序会自动改用 var/csv，若 CSV 也没有或过期就如实报告失败）。
   一个账户模式在 `var/sim.json` 的 start 之前只做预览（不推进账户、不下单），这是正常的。程序最后会打印「数据完整性：…」或「★ 日报缺数据 N 项」。
4. 首次成功产生数据时（journal.csv 首次出现数据行）额外做真实数据回测（与模拟盘同口径）：
   `bash scripts/routines.sh run run.py backtest JP --universe broad --position-pct 0.34 --max-positions 3 --macro sim > var/out/backtest_JP.txt`
   `bash scripts/routines.sh run run.py backtest US --universe broad --position-pct 0.2 --max-positions 5 --macro sim > var/out/backtest_US.txt`
   （optimize、variant_study、bullbear_study、regime_strategy_study 都不要在例行任务里跑）
5. 入库（必须成功）：`cd ~/qbreak-sim && git add quant_breakout/var && git commit -m "sim(mac): <最新 bar_date> 日报"`（署名行见上面「Mac 上和云端版不同的」）
   → `cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh push`（它自己 `git pull --rebase`、失败重试 2s/4s/8s/16s）；仍失败则汇报里醒目写「★ 状态未能入库」。
6. 发布日报：Artifact read https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ ，然后 publish `file_path=<~/qbreak-sim/quant_breakout/var/out/report.html 的绝对路径>`
   并传 `url=https://claude.ai/artifact/1RuryVLyrXpD9a2aS4tAZQ`（原地更新，不要新建）。
7. 中文汇报 ≤16 行。**每一项数字都必须带单位**：金额 ¥ / $（美元同时写折合日元 ¥）、股数「股」、ETF「口」、汇率「円/USD」、日経点位「円」、S&P500 点位「pt」、涨跌与比例「%」、倍数「倍」、就绪度「分」、威胁指数「分」、百分位「分位」、时间「JST」；没有值写「—（原因）」，不要只写数字，也不要写「—%」。依次写：
   ① 数据完整性（读 var/out/report_data.json 的 missing：为空写「数据完整性：全部取到」；不为空时整份汇报第一行写「★ 日报缺数据 N 项」，并逐项列出项目与原因）；
   ② 数据源（yfinance / csv）与被拦截域名；
   ③ 牛熊分界（日経 / S&P500 各自：牛或熊、自何日、翻转价位 x 円 / x pt、距现价 ±x.xx%；数值取自 report_data.json 的 markets.<市场>.regime.bullbear；当天发生翻转要醒目写出）；
   ④ 市场状态（量化层 + 判断层 + 汇率层 + 宏观层触发规则 → 各市场最终新仓倍数 x 倍）；
   ⑤ 账户：总权益 ¥、当日损益 ¥（±x.xx%）、累计损益 ¥（±x.xx%）、最大回撤 x.x%、日元现金 ¥、美元现金 $（折合 ¥）、USD/JPY x 円/USD；持仓（代码、x 股、成本 ¥ 或 $、止损 ¥ 或 $）；核心 ETF（代码、x 口、市值 ¥）；
   ⑥ 当日除息 / 拆股 / ストップ安顺延（日志里「配当落ち」「株式分割」「顺延」字样）；
   ⑦ 今日成交（hh:mm JST、代码、买或卖、x 股、成交价 ¥ 或 $）；排队待成交的买单（代码 / x 股 / 参考价 ¥ / 止损位 ¥）；
   ⑧ 候补队列前 5 名（代码、板块、状态、就绪度 x 分、收盘 ¥、宏观倾斜 x 倍）。
   若 last_run.json 的 ok 为 false，写明原因与用户需要做的事（网络策略见 quant_breakout/network_allowlist.txt；或在 Mac 上运行 scripts/fetch_and_push.sh 提供 CSV）。
8. 若 var/sim.json 的 end 已过：生成最终总结（累计收益 ¥ 与 %、最大回撤 %、交易笔数 笔、胜率 %、美股折日元后与日经对比、与买入持有对比，数字都带单位），第一行写「模拟已结束，请删除例行任务」。

禁止：修改策略参数、仓位、股票池名单、宏观阈值与开关、状态层模式与牛熊分界参数；使用合成数据；对失败或缺数据静默；新建第二个 artifact。
（Mac 另加）在 `~/qbreak-sim` 以外运行这些命令；`git reset` / `git stash` / 丢弃改动 / `git push --force` / 推到别的分支；打印或回显任何密钥的值。
