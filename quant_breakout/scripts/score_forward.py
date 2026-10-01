"""score_forward.py — 买点「质量分」的前向记录：登记（2026-09-26）、冻结配比（--freeze）、复核（--review）。

为什么要前向记录：score_study（登记 600ba6d，结果 7eb72e1）里 F1〜F5 都没通过，但有几个现象（量比、F2 / F3 的分数、
「行业已经涨过一段的突破更差」、个股相对行业强度）值得验证。这 20 年的数据已经看过了，再从里面挑就是数据挖掘；
只有登记之后才发生的信号是真正的样本外。

一、记录什么（qbreak/score_forward.py；云端 sim-day 每天自动追加到 var/out/score_forward.csv；不影响交易）
  2026-09-28 起，日経225 股票池的每个买入信号（不管模拟盘有没有买）：日期、代码、行业、模拟盘当天有没有计划买入、收盘、
  量比、真突破、距箱顶 %、15 个因子的原值、F1〜F5 的分数与「保留」标记（分数 ≥ 冻结的门槛）、记录日、模型编号。
  同一个「日期 × 票」只保留最早记下的那次（不改、不补写；每次运行看最近 5 个交易日，只补漏记的）。
  记录失败会出现在日报「数据完整性」里。
二、冻结的配比（var/score_forward_model.json；登记时 --freeze 生成一次，之后不改）
  与 score_study 同一套因子与方法（qbreak/signal_score.py）；训练样本 = 2026-09-25 为止已平仓的全部交易（每只票单独、一次一仓、
  现行出场规则）；F1 等权 / F2 逻辑回归（L2，交叉验证选惩罚）/ F3 IC 加权 / F4 只用行业 / F5 只用个股；门槛 = 训练样本分数的 1/3 分位。
三、结果（赚没赚）不写进记录：复核时用那时的行情、每只票单独、一次一仓、现行出场规则、扣 ¥25 万一笔的来回手续费算
  （与 score_study 相同）；只算已平仓的；记录里的信号在重算的行情里对不上的，单独列出、不算。
四、事先写定的前向假设（方向与 score_study 的样本外观察一致，但那是事后观察，所以要新数据验证）
  主假设（2 个）：P1 F2（逻辑回归）的分数 → 赚钱：AUC 的区间下限 > 0.5
                  P2 量比（对数）→ 赚钱：AUC 的区间下限 > 0.5
  次假设（只报告「倾向」，不单独作为改规则的依据）：
    S1 F3 保留的信号：胜率比全部信号高（差的区间下限 > 0）且每笔期望不低于全部
    S2 行业 20 日动量、行业 60 日动量 → 赚钱：AUC 的区间上限 < 0.5（行业已经涨过一段的突破更差）
    S3 个股相对行业强度 → 赚钱：AUC 的区间下限 > 0.5
    另报：F1 / F4 / F5、真突破的 AUC。
  判定时点：已平仓的信号第一次达到 100、200、400 笔时各判定一次（其他时候只报告进度，不判定）。
  每个时点主假设用 99% 区间（控制 3 次查看 × 2 个主假设的误判），次假设用 95%。区间 = 按信号月聚类的自助法 2,000 次（种子 20260926）。
  检出力的现实（按过去 13 年每年约 36 个信号）：100 笔约 3 年、只能分辨 AUC ≈ 0.70 以上的效果；200 笔约 0.64；400 笔（约 11 年）约 0.60
  （80% 检出力）。score_study 里量比的样本外 AUC 是 0.594 —— 以这个股票池的信号频率，前向记录是防止数据挖掘的长期保险，不是快速答案。
  主假设成立 → 另写一份事先登记的组合研究（用这个分数跳过 / 排序），通过门槛且用户确认后才可能改模拟盘；只凭前向记录不改规则。
五、复核：python scripts/score_forward.py --review（只读 var/out/score_forward.csv 与 score_forward_wide.csv，不改、不补写）
  → var/out/score_forward_review.md / .json，并追加 var/out/score_forward_review_history.csv。
  只看进度（不联网、不写任何文件，2026-09-28 加）：python scripts/score_forward.py --status。
六、追加登记（2026-09-26，用户要求「加快前向记录」；此时前向记录还没有任何数据）
  - 扩大池：TOPIX 1000（プライム，規模区分 Core30 / Large70 / Mid400 / Small 1）里日経225 股票池以外的票，同样剔除航空 / 陆运 /
    仓储物流（var/universe_wide.json，東証上場銘柄一覧 2026-08-31 版，冻结）：T500x 249 只（过去 5 年每年约 66 个信号）、
    S1x 467 只（约 149 个）。行业因子对照日経225 同组成员（qbreak/wide_universe.py，東証 33 业种 → 现有分组的对照表事先写定），
    用同一个冻结的配比打分，记到 var/out/score_forward_wide.csv（规则同上：只追加、同一日期 × 票保留最早）。
  - 主判定改为「合并样本」（日経225 + T500x + S1x）：已平仓第一次达到 200、400、800 笔时判定（主假设 99% 区间、次假设 95%），
    主假设另外要求：大中型股（日経225 + T500x）的点估计也在事先方向。只看日経225 的 100 / 200 / 400 笔判定照旧，作为附带。
  - 预计每年约 250 个信号 → 200 笔约 1 年、400 笔约 1.6〜2 年、800 笔约 3〜3.5 年；400 笔时约能分辨 AUC 0.60，800 笔时约 0.57（80% 检出力）。
  - 同一天另登记「没参与过设计的股票」检验（scripts/heldout_study.py）：扩大池 2013〜 的历史信号，现在就能给出股票不同、时期相同的样本外证据。
七、追加登记 X2（2026-09-26，用户要求「X2 登记进前向记录」；此时前向记录还没有任何数据）
  来由：fund_study（登记 efa7235，结果 04190e0）里 X2「自己业种的顾客业种的短観业况变化」样本外 AUC 0.569（95% 区间 0.503〜0.630，
  两半 0.569 / 0.565），过了第一条门槛；但前半保留的胜率只 +0.09 pp、S0C2 Calmar 0.360 < 0.363、比对照 V0 的 AUC 差区间含 0 → 没通过。
  另外同一个信号（S5）对业种收益本身几乎没有作用（F1：公布后 63 日 IC +0.004，t 0.18）→ 事先的看法：X2 的 AUC 多半有偶然成分，
  前向记录是为了不错过，不是预期它会成立。
  - 记录：两份记录（score_forward.csv / score_forward_wide.csv）每个信号另记 x2 = 这只票的東証业种（var/industry_s33.json）的 S5
    （信号日当天或之前已可用的最近一次短観；可用日按 qbreak/tankan.py available() 的保守日期）与 x2_survey（用到的调查季度末）。
    算法与 fund_study 相同（qbreak/score_forward.py x2_table / x2_lookup；tests/test_score_forward.py 核对两者一致）。
    短観取不到 → 空（不补写；日报「数据完整性」会列出）；复核只用有值的。
  - 假设 X2（事先方向 +，与主假设同级）：X2 → 赚钱：AUC 的 99% 区间下限 > 0.5；合并样本另外要求大中型股（日経225 + T500x）的点估计 > 0.5。
  - 区间：X2 在同一次调查、同一业种里的值都一样 → 自助法按「用到的调查季度」聚类（2,000 次，种子 20260926），不按月。
    有值的已平仓信号覆盖的调查季度 < 8 个时，这个时点不判定 X2（只报告），到下一个时点再判定（最多 3 次，所以仍用 99%）。
  - 判定时点与主判定相同：合并样本 200 / 400 / 800 笔；只看日経225 的 100 / 200 / 400 笔另报。合并样本 200 笔时预计只有约 4 个
    调查季度 → 第一次实际判定多半在 400 笔（约 2 年）。
  - 成立 → 与主假设一样：另写一份事先登记的组合研究，通过门槛且用户确认后才可能改模拟盘；只凭前向记录不改规则。
八、追加登记 W2（2026-09-27，用户「登记 W2 前向记录，加全市场版」；此时两份记录都还没有任何数据）
  来由：W2（周线量比 ≥ 1.0 的突破才买，2026-09-27 启用）的证据都来自看过多次的历史数据；模拟盘只买 W2 留下的信号，
  挡掉的不会出现在账本里 → 要另外记下来才知道 W2 在新数据里是帮了还是害了。
  另外：W2 写进了信号本身（qbreak/strategy.py compute_indicators 的 entry），这份记录原来直接用模拟盘的信号 → 启用后只剩 W2 留下的
  约一半，与第一节「每个买入信号」（登记时 = 不加 W2 的突破）不符 → 这里把记录范围恢复为「不加 W2 的突破」。
  - 记录：两份记录（score_forward.csv / score_forward_wide.csv）都记「不加 W2 的突破」（参数 = 当时的现行参数去掉 W2，其他不变）；
    每个信号另记 w5v = 周线量比（qbreak/mtf.py weekly_volume_ratio + 东证日历补下一个交易日 = 实盘 W2 同一个定义）与
    w2_keep = W2 是否保留（w5v < 1.0 → 0；≥ 1.0 或缺值 → 1；门槛 1.0 在这里写定，不跟着参数变）。planned 照旧（W2 挡掉的 = 0）。
  - 复核：结果照第三节，但重算交易用「现行参数去掉 W2」（与记录同一个信号范围，否则 W2 挡掉的信号对不上）；第一〜七节的假设照旧。
  - W2 的假设（事先方向：W2 保留的每笔净收益 > 挡掉的）：已平仓的信号按 w2_keep 分两组，差 = 保留 − 挡掉的每笔平均净收益 pp，
    区间 = 按信号月聚类的自助法 2,000 次（种子 20260927）。都用合并样本（日経225 + T500x + S1x）：
    失效警报（每年一次：复核日第一次到达 2027-09-28、2028-09-28、2029-09-28、2030-09-28、2031-09-28 之后的那次复核）：
      「挡掉 − 保留」的 95% 区间下限 > 0 → 提议关掉 W2；
    证实（已平仓第一次达到 400、800 笔时）：「保留 − 挡掉」的 99% 区间下限 > 0 → 记为「新数据证实 W2」；
    其他时候只报告进度；另报日経225 / T500x / S1x 分段的笔数、胜率、每笔。
  - 检出力（每年约 250 笔、每笔标准差约 5.9%、保留约 45%；80%）：每笔差 1 pp 的反转约 3.5〜4.5 年、证实 +0.5〜0.7 pp 约 9〜18 年
    → 长期保险；更快的全市场版见 scripts/w2_forward_all.py（同日登记）。
  - 警报 / 证实都只是提议：改模拟盘与执行器要用户在对话里确认，并记 sim_changes.md。
九、追加登记 K2 / USW（2026-09-27，用户「F 前向记录」；此时两份记录都还没有任何数据；定义 qbreak/idio_forward.py）
  来由：「选股本身的质的飞跃」循环（scripts/leap2_common.py）S6 登记检验（a88cbd3）：K2「突破日量比 ≥ 2.0 ∧ 对日経225 的 β ≤ 0.70」
  在 2001〜2006 / 2006〜2016 / 2017〜2026 每笔都比现行多赚 1.2〜1.5 pp、组合 Calmar 都不差，但胜率只 +3.2 pp、随机对照没过 → 按规则不通过；
  S4（scripts/leap2_s4b_explore.py）：USW「所在東証业种的美国对应行业（Ken French 49）12 个月强弱最弱 1/3」只在 2017〜2026 成立
  （W2 ∧ USW 25 笔 68% / +3.54%），2006〜2016 没有 → 时代依赖。两个都只能靠登记之后的数据检验，不交易。
  - 记录：两份记录每个信号另记 vr1（突破日量比）、b_n225（104 周 β，信号周之前一周为止）、k2_keep、us12（美国对应行业百分位，
    月数据只用到两个月前）、usw_keep。量比 / β 缺值 → k2_keep = 0（= 登记检验里「不买」）；us12 取不到 → 空、不补写
    （复核时 us12 为空的可以按同一规则从 Ken French 数据补算，只用于复核、不写回记录）；记录时行情只有 2 年 → β 用约 100 周（≥ 69 周才算）。
  - 假设（事先方向）：K2：全部（不加 W2）突破里 K2 = 1 的每笔净收益 > 其余；USW：W2 保留的突破里 USW = 1 的每笔净收益 > 其余（us12 缺值的不算）。
  - 判定（每年一次：与 W2 同一组日期 2027-09-28 … 2031-09-28 之后的那次复核；合并样本 = 日経225 + T500x + S1x；做过的年份不再做）：
    证实：「标记 − 其余」的 99% 区间下限 > 0（按信号月聚类的自助法 2,000 次，种子 20260927）→ 记为「新数据证实」；
    反向：「其余 − 标记」的 95% 区间下限 > 0 → 记为「新数据否定」；其他时候只报告进度。另报日経225 / T500x / S1x 分段。
  - 检出力（每年约 250 笔、每笔标准差约 5.9%；K2 约 19%、USW ≈ W2 保留 45% 的 1/3；80%）：K2 每笔差 1.5 pp 约 4 年、USW 差 2 pp 约 3.5〜4 年
    → 长期保险；全市场版（scripts/w2_forward_all.py 同日加 K2 / USW，主对象每年约 1,000 笔）差同样大小约 1 年。
  - 证实 / 否定都只是记录：要改模拟盘 / 执行器另写一份事先登记的组合研究，并经用户确认。
十、追加登记 卖法 X6「吊灯止损」（2026-09-28，用户「㉛ 选 ① 走前向记录」；此时两份记录都还没有任何数据；定义与统计 qbreak/exit_forward.py）
  来由：买点 / 卖点 / 持有时间 横展开（scripts/bsh_explore.py，结果 da9c1dc）里 X6「持有以来最高价 − 3 × ATR14，收盘跌破就卖（代替 MACD 死叉）」
  组合里每笔明显变好，但账户 Calmar 只 +0.02、没过入选规则；它是看过 E / J 之后挑出来的 → 只能用登记之后才发生的信号检验。只记录，不交易。
  - 做法：记录里的每个信号（按记录的日期与票，不重算买点）只留这一个买入信号，用回测引擎（qbreak/engine.run_backtest，现行成交假设）跑两次：
    现行 / 只把死叉换成吊灯止损（最高价从买入价起算、ATR 用当天的 Wilder ATR14、k = 3；止损 −7%、跟踪 12%、止盈 +25%、放量阴线、
    最长 60 天两边相同）。两边买入完全相同 → 配对差 = X6 − 现行 的净收益 pp（来回手续费两边相同）。
  - 成熟：信号日之后至少 65 根 K 线（两边都应已平仓）才算；有一边还没卖的不算、另报笔数
    （不这样做，X6 拿得久、还没卖的多半是赚的，会让早期结果偏向现行）。
  - 主假设（事先方向：X6 每笔 > 现行）：合并样本（日経225 + T500x + S1x）里 W2 保留（w2_keep = 1）的成熟配对，配对差的平均；
    区间 = 按信号月聚类的自助法 2,000 次（种子 20260928）。判定时点：成熟配对第一次达到 100 / 200 / 400 笔（做过的不再做）：
      证实 = 99% 区间下限 > 0；否定 = 95% 区间上限 < 0（X6 每笔反而更差 → 结束跟踪，记录照留）；其他 = 未定、只报告进度。
    另报（不判定）：只看日経225（W2 保留）、不管 W2 的全部突破；两边的胜率 / 每笔 / 持有中位、X6 更好的占比、X6 的出场原因。
  - 登记前的校准（scripts/x6_forward_calib.py → var/out/x6_forward_calib.md；用的是已看过的 E / J，只核对模拟器、估检出力，不是检验）：
    配对的现行一边与引擎一只票一次一仓的交易逐笔一致（E 127 / 127、J 172 / 172 笔）；今天的日経225 W2 保留的配对差
    E +1.35 pp（95% 区间 −0.08〜+2.98）、J +0.38 pp（−0.72〜+1.58），标准差 6.2〜7.5 pp，X6 更好的只占 23〜32%（少数大赚拉高平均），
    胜率 X6 反而低 2〜3 pp。检出力（按聚类标准误外推；99% 下限 > 0、80%）：差 1 pp 约 710〜930 笔（这份记录 W2 保留每年约 110 笔
    → 6.5〜8.5 年）、差 1.5 pp 约 320〜420 笔（约 3〜4 年）→ 这份记录是长期保险；快的是全市场版（scripts/w2_forward_all.py 第八节，同日登记）。
  - 证实也只是记录：X6 在组合里账户几乎不动（个股仓位小、拿得久资金离开 1655）→ 要改模拟盘另写一份事先登记的组合研究，并经用户确认。
  - 同日顺带修正（不是规则改动）：复核读行情的年数改为「覆盖登记日之前 2 年、最少 3 年」（data_years；原来固定 3 年，
    2029 年以后最早的记录会落到行情外、对不上）。
十一、追加登记 卖出判定 R4「抛物线 SAR 翻转代替死叉」（2026-09-28，用户「继续 把前向记录和卖出判定研究做完」；此时两份记录都还没有任何数据；
  定义与统计 qbreak/exit_forward.py）
  来由：卖出判定的确认（scripts/sell_confirm.py，登记 c9149d1、结果 391acd6）里**事后**看到：没看过的数据（2001〜2006 日経225 + 另一批股票 714 只，
  650 对）上 R4 胜率 +4.2 pp（95% 区间 +1.5〜+6.9）、每笔 −0.03 pp（−0.34〜+0.26）—— 15 个判定里唯一「胜率升、每笔不降」的；
  但探索用的 2006〜2016 日経225 里胜率 ±0、每笔 −0.32 pp，并不一致。它不是事先的假设 → 只能用登记之后的数据检验。只记录，不交易。
  - 做法：与第十节同一批配对多跑一边：只把死叉换成「抛物线 SAR（0.02 / 0.02 / 0.2）从价格下方翻到上方的那天收盘」，其余卖法不变；
    成熟（信号日之后 ≥ 65 根 K 线）、现行与 R4 两边都已平仓的才算。
  - 主假设（事先方向：胜率升、每笔不降）：合并样本 W2 保留的成熟配对；区间 = 按信号月聚类的自助法 2,000 次（种子 20260928）。
    判定时点：成熟配对第一次达到 100 / 200 / 400 笔（做过的不再做）：
      证实 = 胜率差（R4 − 现行）的 99% 区间下限 > 0，且每笔差的 95% 区间下限 > −0.30 pp（非劣效的界限，写定）；
      否定 = 胜率差的 95% 区间上限 < 0，或每笔差的 95% 区间上限 < −0.30 pp（→ 结束跟踪，记录照留）；其他 = 未定。
    另报（不判定）：只看日経225（W2 保留）、不管 W2 的全部突破。
  - 检出力（按确认的数据外推：胜率差的聚类标准误约 1.4 pp / 650 对）：胜率差 +4 pp 要约 900 对 → 这份记录约 8 年；快的是全市场版（第九节）约 2 年。
  - 证实也只是记录：改模拟盘另写一份事先登记的组合研究，并经用户确认。
十二、追加登记 关联搭配 C「市场状态 × 个股特征」（2026-10-01，用户「加进模拟盘并记录」；C 从 2026-10-01 收盘的决策（10-02 成交）起
  作用在模拟盘与执行器；此时两份记录都还没有任何 C 的数据；定义 qbreak/combo_c.py）
  来由：全部研究的关联搭配（scripts/combo_all_study.py，登记 7f2ca59、结果 729c4ee、事后核对 63fa4d2）里 C 按事先写定的 D1〜D4b 全部通过：
  2017〜2026 日経225 W2 信号胜率 40.1% → 46.5%、每笔 +0.91% → +1.88%（保留 74%）；但 2001〜2016 只略好，别的股票（W / Jx）几乎没有效果
  （+0.05 / +0.04 pp）→ 效果可能只属于今天的日経225 + 这个年代。用户决定直接加进模拟盘，这一节记它在登记之后的新数据里还成不成立。
  - 记录：两份记录（score_forward.csv / score_forward_wide.csv）每个信号另记 cc_on（信号日 日経225 收盘在 200 日线上且 VIX < 20 = 1，
    否则 0；算不了 = 空）、cc_ma200、cc_vix、5 个特征 cc_vexp / cc_upper / cc_atrp / cc_r12 / cc_us12、分数 cc_score、cc_skip
    （C 会不会跳过 = cc_on = 1 且分数 < −1）。算法 = 模拟盘同一个函数（qbreak/combo_c.fields；与研究面板逐信号核对一致，见 sim_changes.md）。
    扩大池（T500x / S1x）只记录，C 不作用在它们身上。
  - 结果：第十节的配对里 X6 那一边（模拟盘的离场 = X6，与研究同一个结果定义），成熟、两边都已平仓的才算（qbreak/exit_forward.usable）。
  - 样本：信号日 ≥ 2026-10-01、W2 保留（w2_keep = 1）、cc_on = 1。主 = 日経225（C 实际作用的股票）；另报合并样本（日経225 + T500x + S1x）。
    C 的列为空的（算不了的日子）不算、不补算，另报个数。
  - 假设（事先方向）：保留（cc_skip = 0）的 X6 每笔净收益 > 跳过的（cc_skip = 1）。差 = 保留 − 跳过，区间 = 按信号月聚类的自助法 2,000 次
    （种子 20260927，qbreak/w2_forward.evaluate 同一函数）。
  - 判定（每年一次：与 W2 同一组日期 2027-09-28 … 2031-09-28 之后的那次复核；做过的年份不再做；保留 / 跳过任一组已平仓 < 10 笔 →
    这一年记「样本不够、不判定」，也算做过）：
      失效警报：保留 − 跳过 的 95% 区间上限 < 0（= 跳过的反而更好）→ 提议关掉 C（var/sim.json combo_c.enabled = false；用户在对话里确认才改）；
      证实：保留 − 跳过 的 99% 区间下限 > 0 → 记为「新数据证实 C」；其他 = 只报告进度。另报（不判定）：合并样本、两组胜率、跳过个数。
  - 检出力（照实写）：研究里日経225 每年被跳过的只有约 2〜3 笔（2017〜2026：23 笔 / 9.75 年）→ 跳过组到 10 笔约要 4 年，
    每笔差 1 pp 在这个笔数上分不出来 → 这份记录只能抓住「明显变坏」；账户层面的模拟盘 − 基准账户含其它改动，只作背景。
  - 警报 / 证实都只是提议或记录：改模拟盘 / 执行器要用户在对话里确认，并记 sim_changes.md。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import combo_c as CC                                            # noqa: E402
from qbreak import exit_forward as EF                                        # noqa: E402
from qbreak import idio_forward as IF                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import score_forward as SF                                       # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import w2_forward as W2F                                         # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

TRAIN_END = "2026-09-26"                         # 训练样本：信号日与平仓日都在这之前
CHECKPOINTS = (100, 200, 400)                    # 只看日経225（附带）
CHECKPOINTS_WIDE = (200, 400, 800)               # 合并样本（主判定，2026-09-26 追加登记）
BOOT_N, SEED = 2000, 20260926
NOTIONAL = 250_000
X2_MIN_CLUSTERS = 8                              # X2：有值的已平仓信号覆盖的调查季度少于这个数 → 这个时点不判定（第七节）
W2_CHECKPOINTS = (400, 800)                      # W2：合并样本已平仓第一次达到 → 证实判定（第八节）；失效警报按年（qbreak/w2_forward.py）
# 变量 → (说明, 事先方向：+1 = 越大越赚钱, 主 / 次)
HYP = {"F2": ("F2 逻辑回归分数", 1, "P1"), "vol": ("量比（对数）", 1, "P2"),
       "ind_mom20": ("行业 20 日动量", -1, "S2"), "ind_mom60": ("行业 60 日动量", -1, "S2"), "rel_ind60": ("个股相对行业", 1, "S3"),
       "F1": ("F1 等权分数", 1, "另报"), "F3": ("F3 IC 加权分数", 1, "另报"), "F4": ("F4 只用行业", 1, "另报"),
       "F5": ("F5 只用个股", 1, "另报"), "breakout": ("真突破", 1, "另报"),
       "x2": ("X2 顾客业种的短観业况变化", 1, "X2")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 冻结 ──
def freeze(force: bool = False) -> Path:
    import signal_study as SS
    import score_study as Z
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    fp = paths.home() / SF.MODEL_FILE
    if fp.exists() and not force:
        raise SystemExit(f"{fp} 已存在（冻结后不改）；确实要重建请加 --force 并在 sim_changes.md 写明原因")
    p = load_params(market="JP")
    data = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    ind0 = dict(IndicatorCache(data).all(p))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    panel = S.feature_panel(ind0, load(*SYM["JP"])["Close"])
    rows = S.signal_rows(panel, ind0, SS.START)
    T = Z.label(SS.trades(ind0, p, bt), ind0, rows, gidx)
    cut = pd.Timestamp(TRAIN_END)
    tr = T[(T["sig_date"] < cut) & (T["exit_date"] < cut)]
    models = {k: S.fit(*Z.CANDS[k], tr) for k in SF.KEYS}
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=Path(__file__).resolve().parent).stdout.strip()
    meta = {"id": f"v1-{tr['exit_date'].max():%Y%m%d}", "trained_through": str(tr["exit_date"].max().date()),
            "n_train": int(len(tr)), "win_train": round(float(tr["win"].mean()) * 100, 2), "code": head,
            "created": str(pd.Timestamp.today().date()), "forward_start": SF.FORWARD_START,
            "note": "score_study 同一套因子与方法；登记后不改（scripts/score_forward.py）"}
    SF.save_model(models, meta, fp)
    print(json.dumps(meta, ensure_ascii=False), {k: round(m.thr, 4) for k, m in models.items()})
    return fp


# ── 复核 ──
def trades_from(ind: dict, p, bt, start: str) -> pd.DataFrame:
    from qbreak.engine import run_backtest
    fee = bt.exec_cfg.fee
    rt = (fee(NOTIONAL) * 2) / NOTIONAL * 100
    rows = []
    for t, df in ind.items():
        try:
            r = run_backtest({t: df}, p, bt, start=start)
        except ValueError:
            continue
        tr = r.trades.copy()
        if len(tr):
            tr["ticker"] = t
            ix = df.index
            tr["sig_date"] = [ix[ix.searchsorted(pd.Timestamp(d)) - 1] for d in tr["entry_date"]]
            rows.append(tr)
    if not rows:
        return pd.DataFrame(columns=["ticker", "sig_date", "entry_date", "exit_date", "ret_pct", "net", "win", "reason"])
    T = pd.concat(rows, ignore_index=True)
    T["net"] = T["ret_pct"] - rt
    T["win"] = (T["net"] > 0).astype(float)
    return T


def match(log: pd.DataFrame, T: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """记录里的信号 ← 重算的交易（按信号日 × 票）；只留已平仓的。"""
    L = log.copy()
    L["date"] = pd.to_datetime(L["date"])
    R = T[["ticker", "sig_date", "exit_date", "net", "win", "reason"]].rename(columns={"sig_date": "date"})
    R["date"] = pd.to_datetime(R["date"])
    M = L.merge(R, on=["date", "ticker"], how="left")
    cnt = {"logged": int(len(L)), "matched": int(M["net"].notna().sum()),
           "open": int((M["reason"] == "end").sum()), "unmatched": int(M["net"].isna().sum())}
    C = M[M["net"].notna() & (M["reason"] != "end")].reset_index(drop=True)
    cnt["closed"] = int(len(C))
    return C, cnt


def boot_ci(C: pd.DataFrame, cols: list[str], seed: int = SEED, cluster: np.ndarray | None = None) -> np.ndarray:
    """按信号月（cluster 给定时按它，例 X2 用到的调查季度）聚类的自助法 AUC。"""
    mon = C["date"].dt.to_period("M").to_numpy() if cluster is None else np.asarray(cluster)
    groups = [np.flatnonzero(mon == m) for m in np.unique(mon)]
    rng = np.random.default_rng(seed)
    V = C[cols].to_numpy(float)
    y = C["win"].to_numpy(float)
    out = np.full((BOOT_N, len(cols)), np.nan)
    for b in range(BOOT_N):
        idx = np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))])
        for j in range(len(cols)):
            a = auc_np(V[idx, j], y[idx])
            out[b, j] = np.nan if a is None else a
    return out


def _auc_row(C: pd.DataFrame, c: str, B: np.ndarray, j: int) -> dict:
    a = auc_np(C[c], C["win"]) if len(C) else None
    q = lambda p: round(float(np.nanpercentile(B[:, j], p)), 4) if np.isfinite(B[:, j]).any() else None   # noqa: E731
    return {"auc": None if a is None else round(a, 4), "lo95": q(2.5), "hi95": q(97.5), "lo99": q(0.5), "hi99": q(99.5)}


def evaluate(C: pd.DataFrame, cnt: dict) -> dict:
    ev = {"count": cnt, "win": round(float(C["win"].mean()) * 100, 2) if len(C) else None,
          "exp": round(float(C["net"].mean()), 3) if len(C) else None, "auc": {}}
    cols = [c for c in HYP if c in C.columns and c != "x2"]
    B = boot_ci(C, cols) if len(C) >= 10 else np.full((1, len(cols)), np.nan)
    for j, c in enumerate(cols):
        ev["auc"][c] = _auc_row(C, c, B, j)
    if "x2" in C.columns:                                      # X2：只用有值的；按用到的调查季度聚类（第七节）
        X = C.assign(x2=pd.to_numeric(C["x2"], errors="coerce"))
        X = X[np.isfinite(X["x2"].to_numpy(float))].reset_index(drop=True)
        svy = X["x2_survey"].fillna("").astype(str).to_numpy() if "x2_survey" in X.columns else np.array([""] * len(X))
        k = int(len(np.unique(svy[svy != ""]))) if len(X) else 0
        Bx = boot_ci(X, ["x2"], cluster=svy) if len(X) >= 10 and k >= 2 else np.full((1, 1), np.nan)
        ev["auc"]["x2"] = _auc_row(X, "x2", Bx, 0)
        ev["x2"] = {"n": int(len(X)), "clusters": k}
    if "F3_keep" in C.columns and len(C):                      # S1：F3 保留的 vs 全部
        from signal_study import boot
        K = C[C["F3_keep"] == 1]
        b = boot(C.assign(entry_date=C["date"]), K.assign(entry_date=K["date"]), SEED) if len(K) >= 5 else {}
        ev["f3_keep"] = {"n": int(len(K)), "win": round(float(K["win"].mean()) * 100, 2) if len(K) else None,
                         "exp": round(float(K["net"].mean()), 3) if len(K) else None, **b}
    return ev


def decide(ev: dict, history: pd.DataFrame | None = None, checkpoints=CHECKPOINTS, scope: str = "N225",
           large_mid: dict | None = None) -> dict:
    """判定时点：已平仓第一次达到 checkpoints 里的笔数（history 里同一 scope 已判定过的不再判定）。
    large_mid：{变量: 大中型股的 AUC 点估计}（合并样本的主假设另外要求它在事先方向）。"""
    n = ev["count"]["closed"]
    h = history if history is not None and not history.empty else pd.DataFrame()
    if len(h) and "scope" in h.columns:
        h = h[h["scope"].fillna("N225") == scope]
    elif len(h) and scope != "N225":
        h = h.iloc[0:0]
    done = {int(x) for x in h.get("checkpoint", pd.Series(dtype=float)).dropna()} if len(h) else set()
    cp = max([c for c in checkpoints if n >= c], default=None)
    if cp is None or cp in done:
        nxt = min([c for c in checkpoints if c > n and c not in done], default=None)
        return {"checkpoint": None, "text": f"只报告进度：已平仓 {n} 笔（下一个判定时点 {nxt} 笔）" if nxt else f"已平仓 {n} 笔；三个判定时点都已做完"}
    res = {}
    for c, (lab, sgn, kind) in HYP.items():
        a = ev["auc"].get(c) or {}
        if kind not in ("P1", "P2", "S2", "S3") or a.get("auc") is None:
            continue
        lo, hi = (a["lo99"], a["hi99"]) if kind.startswith("P") else (a["lo95"], a["hi95"])
        ok = (lo is not None and lo > 0.5) if sgn > 0 else (hi is not None and hi < 0.5)
        note = ""
        if ok and kind.startswith("P") and large_mid is not None:
            v = large_mid.get(c)
            if v is None or (v - 0.5) * sgn <= 0:
                ok, note = False, f"大中型股的点估计 {v} 不在事先方向"
        res[c] = {"hyp": kind, "label": lab, "ok": bool(ok), "range": [lo, hi], "level": "99%" if kind.startswith("P") else "95%",
                  "note": note}
    k = ev.get("f3_keep") or {}
    res["F3_keep"] = {"hyp": "S1", "label": "F3 保留的信号", "ok": bool(k.get("dwin_lo", -1) > 0 and (k.get("exp") or -9) >= (ev["exp"] or 9)),
                      "range": [k.get("dwin_lo"), k.get("dwin_hi")], "level": "95%", "note": ""}
    a = ev["auc"].get("x2") or {}
    if a.get("auc") is not None:                               # X2（第七节）：调查季度够 8 个才判定
        nx = ev.get("x2") or {}
        lo, hi = a.get("lo99"), a.get("hi99")
        if nx.get("clusters", 0) < X2_MIN_CLUSTERS:
            res["x2"] = {"hyp": "X2", "label": HYP["x2"][0], "ok": False, "judged": False, "range": [lo, hi], "level": "99%",
                         "note": f"有值的 {nx.get('n', 0)} 笔只覆盖 {nx.get('clusters', 0)} 个调查季度（< {X2_MIN_CLUSTERS}）→ 这个时点不判定，下一个时点再判定"}
        else:
            ok, note = bool(lo is not None and lo > 0.5), ""
            if ok and large_mid is not None:
                v = large_mid.get("x2")
                if v is None or v <= 0.5:
                    ok, note = False, f"大中型股的点估计 {v} 不在事先方向"
            res["x2"] = {"hyp": "X2", "label": HYP["x2"][0], "ok": ok, "judged": True, "range": [lo, hi], "level": "99%",
                         "note": note or f"有值的 {nx.get('n', 0)} 笔、{nx.get('clusters', 0)} 个调查季度"}
    return {"checkpoint": cp, "results": res}


def read_logs() -> pd.DataFrame:
    """两份记录合在一起（只读）：segment = N225 / T500x / S1x。"""
    parts = []
    for fn, seg in ((SF.LOG_FILE, "N225"), (SF.LOG_WIDE, None)):
        fp = paths.out_dir() / fn
        if fp.exists():
            d = pd.read_csv(fp, dtype={"date": str, "ticker": str})
            if seg is not None:
                d["segment"] = seg
            parts.append(d)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["date", "ticker", "segment"])


def seg_auc(C: pd.DataFrame, cols: list[str]) -> dict:
    out = {}
    for seg in ("N225", "T500x", "S1x", "大中型"):
        d = C[C["segment"].isin(["N225", "T500x"])] if seg == "大中型" else C[C["segment"] == seg]
        out[seg] = {"n": int(len(d)), **{c: (round(a, 4) if (a := auc_np(d[c], d["win"])) is not None else None)
                                          for c in cols if c in d.columns}}
    return out


def _say_eval(title: str, ev: dict, V: dict) -> None:
    say(f"\n## {title}")
    cnt = ev["count"]
    say(f"对上行情的 {cnt.get('matched', 0)} 个（持有中 {cnt.get('open', 0)}、对不上 {cnt.get('unmatched', 0)}）；已平仓 {cnt['closed']} 笔"
        + (f"，胜率 {ev['win']}%，每笔期望 {ev['exp']:+.2f}%" if cnt["closed"] else ""))
    if ev.get("auc"):
        say("| 变量 | 事先方向 | 假设 | AUC | 95% 区间 | 99% 区间 |")
        say("|---|---|---|---|---|---|")
        for c, a in ev["auc"].items():
            lab, sgn, kind = HYP[c]
            say(f"| {lab if lab.startswith(c) else f'{c} {lab}'} | {'+' if sgn > 0 else '−'} | {kind} | {a['auc'] if a['auc'] is not None else '—'} | "
                f"{a['lo95']}〜{a['hi95']} | {a['lo99']}〜{a['hi99']} |")
    if ev.get("x2"):
        say(f"X2 有值的已平仓 {ev['x2']['n']} 笔、覆盖 {ev['x2']['clusters']} 个调查季度（X2 的区间按调查季度聚类；第七节）")
    if V.get("checkpoint"):
        say(f"判定（已平仓第一次达到 {V['checkpoint']} 笔）：")
        for c, r in V["results"].items():
            verdict = "不判定" if r.get("judged") is False else ("成立" if r["ok"] else "不成立")
            say(f"- {r['hyp']} {r['label']}：{verdict}（{r['level']} 区间 {r['range'][0]}〜{r['range'][1]}）"
                + (f"；{r['note']}" if r.get("note") else ""))
    else:
        say(V.get("text", ""))


def idio_fill(C: pd.DataFrame) -> pd.DataFrame:
    """第九节：us12 为空的信号按同一规则从 Ken French 数据补算（只用于这次复核，不写回记录）；取不到就原样。"""
    if not len(C) or "us12" not in C.columns:
        return C
    u = pd.to_numeric(C["us12"], errors="coerce")
    if u.notna().all():
        return C
    try:
        from qbreak import factors as F
        s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
        P = IF.us_rank_asof(F.ff_industries(49, "vw"))
    except Exception as e:                                                   # noqa: BLE001
        say(f"（K2 / USW：us12 为空的 {int(u.isna().sum())} 笔补算不了：{type(e).__name__}: {e}）")
        return C
    C = C.copy()
    fill = [IF.us12_at(P, s33.get(t), d) if not np.isfinite(x) else x for x, t, d in zip(u, C["ticker"], C["date"])]
    C["us12"] = fill
    C["usw_keep"] = IF.usw_flag(fill)
    return C


def w2_review(C: pd.DataFrame, hist: pd.DataFrame | None, today) -> dict:
    """第八节：合并样本里已平仓、有 W2 标记的信号 → 保留 vs 挡掉；失效警报按年、证实按已平仓笔数，做过的不再做。"""
    ev = W2F.evaluate(C)
    year = W2F.due_date(today, W2F.JUDGE_DATES, W2F.history_done(hist, "W2", "w2_year"))
    cp = W2F.due_checkpoint(ev["n"], W2_CHECKPOINTS, W2F.history_done(hist, "W2", "checkpoint"))
    seg = {}
    if len(C) and "w2_keep" in C.columns:
        k = pd.to_numeric(C["w2_keep"], errors="coerce").to_numpy(float)
        for g in ("N225", "T500x", "S1x"):
            m = (C["segment"] == g).to_numpy() if "segment" in C.columns else np.zeros(len(C), bool)
            seg[g] = {"keep": W2F.stat(C.loc[m & (k == 1), "net"]), "drop": W2F.stat(C.loc[m & (k == 0), "net"])}
    return {"eval": ev, "year": year, "checkpoint": cp, "alarm": W2F.alarm(ev) if year else None,
            "confirmed": W2F.confirmed(ev) if cp else None, "segments": seg}


def _say_w2(w: dict) -> None:
    say("\n## W2（第八节）：保留 vs 挡掉（合并样本、已平仓）")
    ev = w["eval"]
    say(W2F.summary_line(ev) if ev["n"] else "还没有已平仓、带 W2 标记的信号")
    lines = W2F.verdict_lines(ev, f"{w['year']} 这一年" if w["year"] else None,
                              f"已平仓第一次达到 {w['checkpoint']} 笔" if w["checkpoint"] else None)
    if lines:
        for x in lines:
            say(f"- {x}")
    else:
        nxt_y = next((d for d in W2F.JUDGE_DATES if pd.Timestamp(d) > pd.Timestamp.today()), None)
        nxt_c = next((c for c in W2_CHECKPOINTS if c > ev["n"]), None)
        say(f"只报告进度（下一次失效警报判定：{nxt_y or '—'} 之后的复核；下一次证实判定：已平仓 {nxt_c or '—'} 笔）")
    if w["segments"]:
        f = lambda s: f"{s['n']} 笔 {s['mean']:+.2f}%" if s.get("n") else "0 笔"                                  # noqa: E731
        say("分段（只描述）：" + "；".join(f"{g} 保留 {f(v['keep'])} / 挡掉 {f(v['drop'])}" for g, v in w["segments"].items()))


def data_years(today) -> int:
    """复核要的行情年数：覆盖登记日（FORWARD_START）之前至少 2 年（指标预热），最少 3 年。
    2026-09-28 追加（第十节同日）：原来固定 3 年，2029 年以后最早的记录会落到行情外、对不上 → 按经过的年数加长。"""
    gone = (pd.Timestamp(today) - pd.Timestamp(SF.FORWARD_START)).days / 365.25
    return max(3, int(np.ceil(max(gone, 0.0))) + 2)


# ── 第十节：卖法 X6（吊灯止损）的配对 ──
def x6_review(log: pd.DataFrame, ind: dict, p, bt, hist: pd.DataFrame | None) -> dict:
    """记录里的信号（按记录的日期与票，不重算买点）逐个配对模拟 现行 / X6（qbreak/exit_forward.py）。
    主：合并样本里 W2 保留的（w2_keep = 1）；成熟配对第一次达到 100 / 200 / 400 笔时判定（做过的不再做）。
    另报（不判定）：只看日経225（W2 保留）、不管 W2 的全部突破。"""
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    cols = [c for c in ("date", "ticker", "segment", "w2_keep", "cc_on", "cc_skip") if c in log.columns]   # cc_*：第十二节
    S = log[cols].copy()
    S["date"] = pd.to_datetime(S["date"])
    P = EF.pairs_frame(ind, S, p, bt, rt)
    k = pd.to_numeric(P["w2_keep"], errors="coerce").to_numpy(float) if len(P) and "w2_keep" in P.columns else np.zeros(len(P))
    M = P[k == 1] if len(P) else P
    ev = EF.evaluate(M)
    cp = W2F.due_checkpoint(ev["n"], EF.CHECKPOINTS, W2F.history_done(hist, "X6", "checkpoint"))
    seg = M["segment"].to_numpy() if len(M) and "segment" in M.columns else np.array([""] * len(M))
    side = {"只看日経225（W2 保留）": EF.evaluate(M[seg == "N225"]), "不管 W2 的全部突破（合并样本）": EF.evaluate(P)}
    e4 = EF.evaluate_r4(M)                                                    # 第十一节：R4（同一批配对多跑的一边）
    r4 = {"eval": e4, "checkpoint": W2F.due_checkpoint(e4["n"], EF.CHECKPOINTS, W2F.history_done(hist, "R4", "checkpoint")),
          "side": {"只看日経225（W2 保留）": EF.evaluate_r4(M[seg == "N225"]), "不管 W2 的全部突破（合并样本）": EF.evaluate_r4(P)}}
    cc = CC.review(P, log, hist, pd.Timestamp.today())                       # 第十二节：关联搭配 C（同一批配对的 X6 那一边）
    return {"eval": ev, "checkpoint": cp, "side": side, "r4": r4, "cc": cc}


def _say_x6(x: dict) -> None:
    say("\n## 卖法 X6（第十节）：同一个信号 现行 vs 吊灯止损（合并样本、W2 保留、成熟配对）")
    ev = x["eval"]
    say(EF.summary_line(ev))
    lines = EF.verdict_lines(ev, f"成熟配对第一次达到 {x['checkpoint']} 笔" if x["checkpoint"] else None)
    for s_ in lines:
        say(f"- {s_}")
    if not lines:
        nxt = next((c for c in EF.CHECKPOINTS if c > ev["n"]), None)
        say(f"只报告进度（下一个判定时点：成熟配对 {nxt} 笔）" if nxt else "三个判定时点都已做完（只报告）")
    for k, e in x["side"].items():
        say(f"- 另报 {k}：{EF.summary_line(e)}")
    r4 = x.get("r4")
    if r4 is not None:                                                        # 第十一节
        say("\n## 卖出判定 R4（第十一节）：同一个信号 现行 vs 抛物线 SAR 翻转（合并样本、W2 保留、成熟配对）")
        say(EF.r4_summary_line(r4["eval"]))
        lines = EF.r4_verdict_lines(r4["eval"], f"成熟配对第一次达到 {r4['checkpoint']} 笔" if r4["checkpoint"] else None)
        for s_ in lines:
            say(f"- {s_}")
        if not lines:
            nxt = next((c for c in EF.CHECKPOINTS if c > r4["eval"]["n"]), None)
            say(f"只报告进度（下一个判定时点：成熟配对 {nxt} 笔）" if nxt else "三个判定时点都已做完（只报告）")
        for k, e in r4["side"].items():
            say(f"- 另报 {k}：{EF.r4_summary_line(e)}")
    cc = x.get("cc")
    if cc is not None:                                                        # 第十二节
        say(f"\n## 关联搭配 C（第十二节）：会跳过 vs 保留（{CC.SINCE} 起、W2 保留、平静的牛市、X6 的成熟配对）")
        for s_ in CC.say_lines(cc):
            say(f"- {s_}")


def review() -> int:
    from qbreak.config import BacktestConfig, DataConfig
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    log = read_logs()
    say(f"# 买点「质量分」前向记录复核（{pd.Timestamp.today().date()}）")
    say(f"记录 {len(log)} 个信号（" + "、".join(f"{k} {v}" for k, v in log["segment"].value_counts().items()) + f"；{SF.FORWARD_START}〜"
        f"{log['date'].max() if len(log) else '—'}）；规则见 scripts/score_forward.py 开头（第六节 = 追加登记的扩大池与合并判定）。")
    hist_fp = paths.out_dir() / "score_forward_review_history.csv"
    hist = pd.read_csv(hist_fp) if hist_fp.exists() else pd.DataFrame()
    evs, Vs, segs = {}, {}, {}
    w2 = idio = x6 = None
    if len(log):
        p = SF.no_w2_params(load_params(market="JP"))           # 第八节：与记录同一个范围（不加 W2 的突破）
        data = load_universe(sorted(set(log["ticker"])), DataConfig(provider="yfinance", years=data_years(pd.Timestamp.today()),
                                                                     allow_synthetic=False).validate())
        ind = dict(IndicatorCache(data).all(p))
        bt = BacktestConfig.for_market("JP", 3, "tachibana")
        bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
        T = trades_from(ind, p, bt, SF.FORWARD_START)
        for scope, sub, cps in (("combined", log, CHECKPOINTS_WIDE), ("N225", log[log["segment"] == "N225"], CHECKPOINTS)):
            C, cnt = match(sub, T)
            evs[scope] = evaluate(C, cnt) if cnt["closed"] else {"count": cnt, "auc": {}}
            segs[scope] = seg_auc(C, list(HYP)) if cnt["closed"] else {}
            lm = {c: segs[scope].get("大中型", {}).get(c) for c in HYP} if scope == "combined" else None
            Vs[scope] = (decide(evs[scope], hist, cps, scope, lm) if cnt["closed"]
                         else {"checkpoint": None, "text": "还没有已平仓的信号"})
            if scope == "combined":
                w2 = w2_review(C, hist, pd.Timestamp.today())
                idio = IF.review_pair(idio_fill(C), hist, pd.Timestamp.today())   # 第九节：K2 / USW（us12 为空的按同一规则补算，不写回）
        x6 = x6_review(log, ind, p, bt, hist)                                 # 第十节：卖法 X6 的配对
    for scope, title in (("combined", "合并样本（主判定：日経225 + T500x + S1x）"), ("N225", "只看日経225（附带）")):
        if scope in evs:
            _say_eval(title, evs[scope], Vs[scope])
            if segs.get(scope):
                say("分段 AUC（点估计）：" + "；".join(f"{g} {v['n']} 笔 F2 {v.get('F2')} / 量比 {v.get('vol')} / X2 {v.get('x2')}"
                                                      for g, v in segs[scope].items()))
    if w2 is not None:
        _say_w2(w2)
    if idio is not None:
        say("\n## K2 / USW（第九节）：标记 vs 其余（合并样本、已平仓）")
        for x in IF.say_lines(idio):
            say(x)
    if x6 is not None:
        _say_x6(x6)
    if not evs:
        say("\n还没有记录。")
    if any(any(r["ok"] for r in V.get("results", {}).values() if r["hyp"].startswith("P") or r["hyp"] == "X2") for V in Vs.values()):
        say("\n主假设（或 X2）成立 → 需要另写一份事先登记的组合研究；模拟盘规则不变（改需用户确认）。")
    out = paths.out_dir() / "score_forward_review"
    Path(f"{out}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{out}.json").write_text(json.dumps({"eval": evs, "decision": Vs, "segments": segs, "w2": w2, "idio": idio, "x6": x6}, ensure_ascii=False,
                                              indent=1, default=float), encoding="utf-8")
    rows = [{"run": str(pd.Timestamp.today().date()), "scope": sc, "logged": int(len(log)), "closed": ev["count"].get("closed"),
             "checkpoint": Vs[sc].get("checkpoint"), **{f"auc_{c}": (a or {}).get("auc") for c, a in (ev.get("auc") or {}).items()}}
            for sc, ev in evs.items()] or [{"run": str(pd.Timestamp.today().date()), "scope": "combined", "logged": 0, "closed": 0}]
    if w2 is not None:                                          # 第八节：W2 一行（判定过的年份 / 笔数，下次不再判定）
        e = w2["eval"]
        rows.append({"run": str(pd.Timestamp.today().date()), "scope": "W2", "logged": int(len(log)), "closed": e["n"],
                     "w2_year": w2["year"], "checkpoint": w2["checkpoint"], "w2_diff": e.get("diff"), "w2_lo95": e.get("lo95"),
                     "w2_hi95": e.get("hi95"), "w2_lo99": e.get("lo99"), "w2_hi99": e.get("hi99"), "w2_alarm": w2["alarm"],
                     "w2_confirmed": w2["confirmed"]})
    if idio is not None:                                        # 第九节：K2 / USW 各一行（判定过的年份下次不再判定）
        rows += IF.history_rows(idio, str(pd.Timestamp.today().date()), "", {"logged": int(len(log))})
    if x6 is not None:                                          # 第十节：X6 一行（判定过的笔数下次不再判定）
        rows.append(EF.history_row(x6["eval"], str(pd.Timestamp.today().date()), "X6", "checkpoint", x6["checkpoint"],
                                   {"logged": int(len(log))}))
        rows.append(EF.r4_history_row(x6["r4"]["eval"], str(pd.Timestamp.today().date()), "R4", "checkpoint", x6["r4"]["checkpoint"],
                                      {"logged": int(len(log))}))                # 第十一节
        if x6.get("cc") is not None:                            # 第十二节：C 一行（判定过的年份（含样本不够）下次不再判定）
            rows.append(CC.history_row(x6["cc"], str(pd.Timestamp.today().date()), {"logged": int(len(log))}))
    pd.concat([hist, pd.DataFrame(rows)], ignore_index=True).to_csv(hist_fp, index=False)
    print(f"{time.time() - t0:.0f}s")
    return 0


# ── 只读的进度（不联网、不写任何文件；Mac 上也可以直接跑）──
def trading_days_after(dates, today) -> np.ndarray:
    """每个日期之后（不含当天）到 today（含）为止的东证交易日数。"""
    from qbreak.calendar_jp import is_trading_day
    d = pd.to_datetime(pd.Series(dates)).dt.normalize()
    t = pd.Timestamp(today).normalize()
    if not len(d):
        return np.zeros(0, int)
    days = [x for x in pd.date_range(d.min(), t, freq="D") if is_trading_day(x.date())]
    idx = pd.DatetimeIndex(days)
    return (len(idx) - idx.searchsorted(d.to_numpy(), side="right")).astype(int)


def _last_hist(fp: Path, scope: str) -> dict | None:
    if not fp.exists():
        return None
    h = pd.read_csv(fp)
    h = h[h["scope"] == scope] if "scope" in h.columns else h.iloc[0:0]
    return None if h.empty else h.iloc[-1].to_dict()


def status_lines(log: pd.DataFrame, today, out_dir: Path) -> list[str]:
    t = pd.Timestamp(today).normalize()
    L = [f"# 前向记录进度（只读；{t.date()}）"]
    if not len(log):
        L.append(f"还没有记录：{SF.FORWARD_START} 的 K 线起，云端 sim-day 每个交易日早上追加（日経225 → score_forward.csv、扩大池 → score_forward_wide.csv）。")
    else:
        d = pd.to_datetime(log["date"])
        seg = "、".join(f"{k} {v}" for k, v in log["segment"].value_counts().items())
        L.append(f"记录 {len(log)} 个信号（{seg}；{d.min().date()}〜{d.max().date()}）。")
        k = pd.to_numeric(log["w2_keep"], errors="coerce").to_numpy(float) if "w2_keep" in log.columns else np.full(len(log), np.nan)
        age = trading_days_after(d, t)
        mat = (k == 1) & (age >= EF.MATURE_BARS)
        nxt = next((c for c in EF.CHECKPOINTS if c > int(mat.sum())), None)
        L.append(f"W2 保留 {int((k == 1).sum())} 个、挡掉 {int((k == 0).sum())} 个；卖法 X6（第十节）：W2 保留里信号日之后已满 {EF.MATURE_BARS} 个交易日的"
                 f" {int(mat.sum())} 个（按日历估；复核时按行情确认两边都已卖出）→ 下一个判定时点：成熟配对 {nxt or '—'} 笔。")
        for c, lab in (("k2_keep", "K2 标记"), ("usw_keep", "USW 标记")):
            if c in log.columns:
                v = pd.to_numeric(log[c], errors="coerce")
                L.append(f"{lab}：1 = {int((v == 1).sum())} 个、0 = {int((v == 0).sum())} 个、空 = {int(v.isna().sum())} 个。")
        if "cc_on" in log.columns:                                            # 第十二节：关联搭配 C
            m = (d >= pd.Timestamp(CC.SINCE)).to_numpy() & (k == 1) & (log["segment"] == "N225").to_numpy()
            on = pd.to_numeric(log["cc_on"], errors="coerce").to_numpy(float)
            sk = pd.to_numeric(log["cc_skip"], errors="coerce").to_numpy(float)
            L.append(f"关联搭配 C（第十二节，日経225、{CC.SINCE} 起、W2 保留）：{int(m.sum())} 个，平静的牛市 {int((m & (on == 1)).sum())} 个、"
                     f"其中会跳过 {int((m & (on == 1) & (sk == 1)).sum())} 个；市场格为空 {int((m & np.isnan(on)).sum())} 个"
                     f"（成熟、已平仓的「保留 vs 跳过」看季度复核）。")
    nxt_y = next((x for x in EF.JUDGE_DATES if pd.Timestamp(x) > t), None)
    L.append(f"下一次年度判定（W2 / K2 / USW、X6 全市场、关联搭配 C）：{nxt_y or '五次都已过'} 之后的第一次季度复核。")
    for fn, scope, lab in (("score_forward_review_history.csv", "X6", "每日记录"), ("w2_forward_all_history.csv", "all_X6", "全市场")):
        r = _last_hist(out_dir / fn, scope)
        if r is None:
            L.append(f"X6 {lab}：还没有复核过（季度复核 {'2f' if scope == 'X6' else '2i'} 会算）。")
        else:
            ci = "" if pd.isna(r.get("x6_lo95")) else f"（95% 区间 {r['x6_lo95']:+.2f}〜{r['x6_hi95']:+.2f}）"
            diff = "—" if pd.isna(r.get("x6_diff")) else f"{r['x6_diff']:+.2f} pp"
            L.append(f"X6 {lab}：最近一次复核 {r.get('run')}，成熟配对 {int(r.get('closed') or 0)} 笔，X6 − 现行 {diff}{ci}。")
    for fn, scope, lab in (("score_forward_review_history.csv", "R4", "每日记录"), ("w2_forward_all_history.csv", "all_R4", "全市场")):
        r = _last_hist(out_dir / fn, scope)
        if r is None:
            L.append(f"R4（抛物线 SAR）{lab}：还没有复核过。")
        else:
            dw = "—" if pd.isna(r.get("r4_dwin")) else f"{r['r4_dwin']:+.1f} pp"
            dm = "—" if pd.isna(r.get("r4_dmean")) else f"{r['r4_dmean']:+.2f} pp"
            L.append(f"R4（抛物线 SAR）{lab}：最近一次复核 {r.get('run')}，成熟配对 {int(r.get('closed') or 0)} 笔，胜率差 {dw}、每笔差 {dm}。")
    L.append("已平仓的收益、AUC、W2 保留 vs 挡掉要按行情重算 → 看季度复核的 var/out/score_forward_review.md 与 w2_forward_all_review.md。")
    return L


def status(today=None) -> int:
    for x in status_lines(read_logs(), today or pd.Timestamp.today(), paths.out_dir()):
        print(x)
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", action="store_true", help="登记时生成冻结的配比（只做一次）")
    g.add_argument("--review", action="store_true", help="复核前向记录")
    g.add_argument("--status", action="store_true", help="只读的进度（不联网、不写文件）")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.freeze:
        freeze(a.force)
        return 0
    if a.status:
        return status()
    return review()


if __name__ == "__main__":
    raise SystemExit(main())
