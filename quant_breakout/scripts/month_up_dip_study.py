"""month_up_dip_study.py — 月K 往上走（≥ 3 个月）时日K / 周K 往下走：买点与卖点的成功率和收益率
（登记版：规则、代码、测试与登记前个数一起提交，之后不改、只运行一次）。

来由：用户 2026-10-07「做一个月线趋势在一段时间上涨但是日线 周线或者只有日线或者只有周线在跌的时候 买/卖点 成功率 收益率研究」。
判定一共 6 个：A 部分 MUDW / MUD / MUW 各一个（h = 20 个交易日，主指标 x20）；B 部分卖点候选 MXDW / MXD / MXW 的第一关。其余都只描述。
只是研究：不改模拟盘、执行器、例行任务、面板，也不改策略参数、仓位、股票池。非投资建议。

〇 以前做过的：mtf_study A 表（fe49536）同类格子之后 20 日超额（验证 / 留出）：「月 > 10 个月线、日 < 20 日线、周不在 Stage 2」+0.08 / −0.34 pp；
   「月 > 10 个月线、日 < 20 日线、周 Stage 2」−0.07 / −0.07 pp；「月 > 10 个月线、日 > 20 日线、周不在 Stage 2」−0.28 / −0.09 pp（区间全部含 0）。
   candle 押し目 C1〜C5（1e9bb57）探索期 +1.52%、验证期 −0.18%、留出期 −0.36%。其余：dip_study（a2c6fcd）、leap_r4 REVUP、madev_event（180d597）、
   rebound_study（77539c6）、turn_shape_mtf（de4b60c）；trendline_study A1 面板标签「往上走 − 往下走」之后 20 日的差 −0.07 pp（−0.29〜+0.15）。
   sim_changes 第 3605 行登记过「反向 / 抄底 / 越跌越买类不再单独重测」；这次是用户明确提出的问题 → 照做，但只登记 6 个判定，结论上限写死（十四）。
   新的地方：直接用面板的「往上走 / 横着走 / 往下走」标签；「一段时间上涨」= 面板月K 现在往上走且之前 3 个整月都往上走；三种情形分开；
   同一组事件同时报买点 / 卖点视角；两个基准（全市场等权、同一天其他月涨的票）；持仓卖点与现行 B4 结合。

一 标签（qbreak/kline_series.py；和面板同一个函数 qbreak/kline.trend、同一口径，SLOPE_BARS = 3）：
   一个周期的 K 线收盘 c：MA5 / MA20 含最后一根；prev20 = 往前第 3 根那时的 MA20；slope = (MA20 ÷ prev20 − 1) × 100（prev20 ≤ 0 → 0）。
   上升（往上走，+1）= 收盘 > MA20 且 slope > 0 且 MA5 > MA20；下降（往下走，−1）= 三条都反过来；其余震荡（横着走，0）；K 线不到 23 根 → NA（int8 −128）。
   「在跌」= 下降；「没在跌」= 上升或震荡；NA 不算「没在跌」。
   K 线：日K = 这只票自己的每一行；周K = to_period("W-FRI")；月K = 日历月；收盘 = 那一周 / 月最后一行的收盘；整周 / 整月没有行 → 没有这根。
   用哪些行（label_rows = kline_series.clean_rows）：Close 有值且 Volume > 0（QB_DROP_ZERO_VOL=1；J-Quants 同一规则）；断言日期递增、没有重复、
   没有周六 / 周日（任一违反就停）；再删掉不是 JPX 交易日的行（calendar_jp.is_trading_day；登记前数个数，预期 0；--prep 实数 6 段都是 0 行）。
   主口径 = 面板口径（as-of）：第 t 行 = 这只票第 t 个交易日收盘之后：D_t = kline.trend(rows[:t+1])，W_t / M_t = kline.trend(kline.bars(rows[:t+1], tf))，
   最后一根是本周 / 本月到 t 为止的部分 K 线（收盘 = c_t）。向量化（只用到 t 为止的数据；细节见 qbreak/kline_series.py 说明三）：g = t 所在周期的序号、
   B_j = 周期 j 最后一行的收盘；MA20_t = (B_{g−19} + … + B_{g−1} + c_t) / 20，MA5_t = (B_{g−4} + … + B_{g−1} + c_t) / 5，
   prev20_t = 已完成第 g−3 根的 MA20 = B.rolling(20).mean().shift(3)；g < 22 → NA。近平局回退：margin = min(|c/MA20 − 1|, |MA20/prev20 − 1|,
   |MA5/MA20 − 1|) < 1e−9（TIE_EPS）或为 NaN（任一分量是 NaN 就是 NaN）→ 这一行改用原函数 kline.trend(kline.bars(rows[:t+1], tf))，并标 fragile（fW / fM）；
   日K 本身是从左往右的滚动计算、与截断后重算逐位相同，不回退，但 margin 同样小的行同样标 fragile（fD）。
   时点：t 收盘后算出的标签 = t 收盘后到 t+1 开盘前面板上看到的标签（盘外 drop_partial_bar）→ 最早 t+1 开盘成交；盘中 with_live 的标签不在范围内。
   这偏离了仓库「周 / 月线只用已完成 K 线」的约定（照实写）：用户问的就是面板上的标签；t 的标签只用到 t 的收盘。
   不偷看的保证见 tests/test_kline_series.py（逐行等于原函数、截断点之后乘随机倍数不变、三种禁止写法都能检出）。
   对照口径「只用已完成 K 线」（只描述，记 CMP）：周 / 月用 mtf.completion_days + mtf.bars，日历 = kline_series.jpx_calendar（is_trading_day 生成，
   延长到数据最后一天之后 1 个交易日）；放回日线 = 完成日 ≤ t 的最后一根（side='right' 再 −1）、完成日收盘起生效；日历最后一个周期不算已完成
   （规格写「数据最后一个周期不算已完成」，实现时的解释：数据最后一天正好是那个周期最后一个交易日时，那个周期当天收盘就算走完；
   在周期中间结束 → 数据最后一个周期不算已完成）。
   价格来源：Z / E / W / Zx / J-Y 用 Yahoo 27y 缓存（var/cache/*_27y.csv；拆股 + 分红调整，与面板同一份）；J / J2 用 J-Quants 宽表（candle_data.load，
   只做拆股调整）。标签用每只票缓存的第一行（Yahoo 约 1999-10、J-Quants 2016-09-26；LABEL_FROM 之前的行不用，预期 0 行）一直算到这一段的数据最后一天
   （标签只用到 t 为止的行 → 每只票只算一次、截到用到它的各段里最晚的数据最后一天，各段取自己那一段，和每段分别算逐位相同）。
   Yahoo 标签表的票 = 今天的日経225 ∪ zx_names（有 27y 缓存的；B 部分 Zx 池子里 2005-09 之前就退市、不在 W 面板里的票也查得到）；J-Quants 标签表 = U0 ∪ U2 的列。
   先决核对：标签输入和收益面板在重叠日的 Close 最大相对差 ≤ 1e−12，否则停。
二 「月线一段时间上涨」MUB（N = 3）：M_t = 上升，且本月之前最近 3 根已完成月K（g−1 … g−3，每根的标签 = 它那个月最后一行收盘时的月K 标签）都是上升。
   M_t 或那 3 根里任何一根 NA → 未知：不进任何状态（MU*、MN*、36 格、B-买分组一 / 二都算「未知 / 标签不全」）、不进任何基准（ALL、MUB 同伴、
   「MUB 任意日子」、「ALL 的全部股票日」：ALL = 同一天 MUB 已知的全部成员，madev_event.market_mean 换成这个掩码；这一天这只票没有标签行
   也算未知），冷却期里也不能当「不在状态」。热身至少 26 根月K（含本月）。本月之前的月份一定已经走完，不需要市场日历。
   日常说法：月K 现在往上走，而且前 3 个月的月底也都是往上走（收盘在 20 个月均线之上、20 个月均线比 3 个月前高、5 个月均线在 20 个月均线之上，
   这样已经至少一个季度）；主口径要求本月此刻仍是上升 →「月涨 + 日 / 周跌」= 回调、但还没把月K 打成横着走。
   有效起点（规格估 Z 约 2001-12、E / W 整个窗口、J / J2 约 2018-10〜11；--prep 实数：MUB 最早有值日期的中位数 Z 2002-02-01、J / J2 2018-10-01）。
   敏感度（只描述）：N = 0（只看此刻月K）、N = 6、MUC3（之前 3 根已完成月K 都上升，不看本月此刻）、CMP（已完成口径：周K 用已完成周K，
   月线条件 = 最近 3 根已按日历完成的月K 都上升）。
三 状态（都要求 MUB 为真、D 和 W 已知；三者互斥）：MUDW = MUB ∧ D = −1 ∧ W = −1；MUD = MUB ∧ D = −1 ∧ W ∈ {0, +1}（细分 MUD-u 周K 上升 / MUD-f 震荡）；
   MUW = MUB ∧ W = −1 ∧ D ∈ {0, +1}（细分 MUW-u 日K 上升 / MUW-f 震荡；细分事件 = 母组的进入事件按事件日的周K（MUD）/ 日K（MUW）拆开，
   加起来正好 = 母组，不是独立状态的进入事件：回调中途换档不算新事件）。只描述：MUN = MUB ∧ D ≠ −1 ∧ W ≠ −1（MUDW ∪ MUD ∪ MUW ∪ MUN = MUB，两两互斥）；
   MUA = 三个都往上走（MUN 的子集）；MNDW / MND / MNW = M_t ∈ {0, −1}（已知）且 MUB 已知（二）时同样的日 / 周条件；面板速查 36 格 = 月 4 档（MUB /
   月K 上升但不满 3 个月 / 横着走 / 往下走；MUB 未知 → 不进任何一格）× 日 3 档 × 周 3 档（状态日、事件都同一口径：都要 MUB 已知）。
   基准：ALL = 同一段同一天的全部成员（J2 = 当天 U2 成员；MUB 未知的不进，见二）→ 超额 x；MUB 同伴 = 同一段同一天 MUB 为真的成员 → y；
   「MUB 任意日子」= 窗口内全部 MUB 为真的「股票 × 日」（成功率与收益的基准；ALL 的全部股票日同样报）。
四 事件与成交：每只票、每个状态 k 在这只票自己的行上：第 i 行是事件 ⇔ state_k(i) 为真、前 20 行（i−20〜i−1）state_k 都为假（COOL = 20）、
   i−20〜i 这 21 行的 D、W、M、MUB 都已知。同一段回调只算第一次；断了不到 20 行又回来不算新事件；刚有标签的前 20 行不出事件；事件日在窗口 [a, b] 内
   （两端含）；J2 还要求事件日是 U2 成员（冷却期不看成员资格，持有期跨出成员期照算）；三个状态各自独立；只描述的组（MUN、MN*、敏感度）同一套规则
   （敏感度把 MUB 换成那个口径的月线条件、CMP 再把 W 换成已完成周K）；细分（MUD-u / -f、MUW-u / -f）= 母组事件按事件日拆开（见三）。
   成交（同 madev_event.fwd_returns）：事件日 e 收盘后知道 → 第 e+1 个市场交易日开盘买（O[e+1]）、第 e+h 个市场交易日收盘卖（C[e+h]）；
   h ∈ {5, 10, 20, 40, 60}（这一段的市场日历行数），主判定 h = 20；O[e+1] 或 C[e+h] 没有值 → 这个 h 不算（不顺延）。
   成本 RT = loop11_common.bt_rt() 的 rt（≈ 0.1496%，立花 ¥25 万一笔的来回手续费；登记 RT_REF，运行时差 ≥ 5e−5 就停）；不扣税、不扣滑点、不处理涨停。
   卖点视角 = 同一组事件、同一个 r_h：「拿着的人在 e+1 开盘卖掉」对「继续拿到 e+h 收盘」。
   只描述的派生事件：结束事件 MUDWE / MUDE / MUWE = 每个事件之后 60 行内第一个 D = +1 ∧ W ∈ {0, +1} ∧ MUB 为真的行（同样次日开盘买、第 h 天收盘卖；
   同一天只算一个；结束日不要求在窗口里 / 是成员）；先出现「MUB 已知且为假」→「月线转弱」只数个数；60 行内都没有 → 没有结束事件。
   状态日：从窗口第一天起每 5 个市场交易日取一天（EVERY = 5），那天处在某组的全部成员（36 格、和 mtf_study A 表对接）。
   A2「按现在的卖法拿」（只描述，只做 Z / E / J）：每个事件当作信号日，turn_shape_combo.single_with_events(t, fa[t], e, W["p0"], bt, rt, None) 的
   第一个返回值（B3 / B4 的 X6 卖法：吊灯止损 3 × ATR14、止损 −7%、跟踪 12%、止盈 +25%、最长 60 日；次日开盘 +0.10% 滑点买入，开盘比事件日收盘高
   3% 以上或涨停买不到 → 不买；130 根内没卖出的不算）；MUN 进入事件作对照。
五 指标（每个事件、每个 h；% / pp）：r_h = (C[e+h] ÷ O[e+1] − 1) × 100；net_h = r_h − RT；x_h = r_h − 同一段同一天成员（MUB 已知，见二）
   r_h 的等权平均（含自己，madev_event.market_mean）；y_h = r_h − 同一段同一天 MUB 为真的成员的等权平均（含自己）。
   两个基准都用主口径 MUB（N = 3）：判定用的 MUDW / MUD / MUW 事件那天 MUB = 1 且是成员，自己一定在里面；只描述的 MN*（那天 MUB = 0）、
   敏感度（N0 / N6 / MUC3 / CMP：那天 MUB(N=3) 可能是 0 或未知）、结束事件（J2 可能落在非成员日）的 ȳ = 比同一天 MUB(N=3) 为真的票，
   自己不一定在里面（读作「对照：比月涨的票」）；MUB(N=3) 未知或非成员的那天自己也不在 ALL 里（同一天没有 MUB 已知的成员 → x 为 NaN）。只描述。
   MIN_PEERS = 5 数的是「r_h 有值的 MUB 同伴」（同一天 MUB 为真、但 e+1 开盘或 e+h 收盘没有价格的成员不算）：不到 5 只 → y 与 lift_buy / lift_sell
   都是 NaN（登记前个数 y_ok、同伴不到 5 只的天数同一口径）。
   买点：成功率 P(net20 > 0)、平均 / 中位 net、平均赚 / 平均亏 / 赔率、5% 分位、P(x > 0)、x̄、ȳ、lift_buy = 平均[1{net_i > 0} − 同一天 MUB 同伴里
   net > 0 的比例] × 100（同伴 < 5 → NaN）。卖点：卖对的比例 P(r20 < 0)、P(x20 < 0)；卖出避开的收益 = −r̄（正 = 卖掉少亏、负 = 卖早了）；
   相对大盘 = −x̄；lift_sell 同上（看 r < 0）。基准成功率：ALL 与「MUB 任意日子」的全部股票日 P(net20 > 0)、平均 net20、平均 r20（MUB 另报 x̄），每段和合并。
   区间：按事件日所在日历月（"YYYY-MM"）聚类的自助法（整月有放回、按事件数加权；BOOT_N = 2,000，SEED = 20261008，每次调用重新播种）；合并时不同段的
   同一个月算同一个聚类；同一状态的 x̄ / ȳ / 成功率 / lift 共用同一组抽到的月份（boot_joint）；判定用 98.33% 区间（1 − 0.05/3），同时报 95%；
   按季度聚类的 95% 区间只描述。汇总：每段内按事件等权；合并 POOL = Z + E + W + J2（全部事件等权）；J 是 J2 的一部分，单独报、参与「每段同号」。
六 样本（只读冻结的缓存）：
   Z  今天的日経225（universe("JP", "broad")，≥ 80 根，约 201 只）；LF.context("Z")（Yahoo 27y，2000-01-04〜2007-06-29）；窗口 2001-01-04〜2006-09-30；成员全 True
   E  同上（约 217 只）；LF.context("E")（2005-09-01〜2016-12-30）；窗口 2006-10-01〜2016-09-30
   J  今天的日経225（candle_data U0 列，225 只）；J-Quants 2016-09-26〜2026-09-25；窗口 2017-01-04〜2026-09-25；成员全 True
   J2 时点 TOPIX 1000（U2，1,378 列，含退市 178 只）；同 J；成员 = mem["U2"]
   W  loop10_common.zx_names()（扩大池 716 只去掉今天的日経225 4 只 = 712 只），≥ 80 根；LF.yf_panel(names, "2005-09-01", "2017-03-31")（Yahoo 27y）；
      窗口 2006-10-01〜2016-09-30。与 madev_event 两处不同（照实写）：行情用 27y 缓存不用 21y（21y 从 2005-10-06 起，MUB 要到约 2007-12 才有，
      会缺 2006-10〜2007-11 的见顶前段；实测 716 只全有 27y 缓存）；去掉 4 只今天的日経225（合并样本里 E 和 W 没有重复的票）。
      实际进面板的是 667 只（登记前实数，照实写、不改规则）：712 只全有 27y 缓存，但其中 45 只的缓存第一行在 2017-02-24 或更晚（多半是 2017 年 2 月以后上市），
      在 2005-09-01〜2017-03-31 里不满 80 根（Close 有值且 Volume > 0 的行），被「≥ 80 根」滤掉。
   J-Y（只描述）今天的日経225；LF.yf_panel(N225, "2016-09-26", "2026-09-25")（Yahoo 27y）；窗口同 J —— 量化「面板（Yahoo）标签」和 J-Quants 标签的差。
   市场日历 = 这一段面板的日期去掉非 JPX 交易日。「薄日」（成员不到中位数一半）照算、登记前报个数。
   冻结缓存（--prep 和 --run 都做）：QB_DROP_ZERO_VOL=1；qbreak.data.behind → None、partial_cached → False、_yf_download → 直接抛错（缺文件的票只会被跳过，
   不联网、不写缓存）；同一目的的补充（登记前试跑发现只有那三处不够）：fill_index_from_intraday → 原样返回、_read_cache 不看有效期（TTL）、
   qbreak.factors._get → 直接抛错（宏观因子下载失败 → 用已有的缓存）；加这三处之前的第一次试跑刷新过宏观因子缓存，见十三「缓存」。数据指纹 DATA_FP = 每段每只票（段, 票, 首日, 末日, 行数, round(Close 合计, 4)）
   （标签输入的行、截到这一段的数据最后一天）+ 每段收益面板一项（段, 市场日数, 首日, 末日, round(Close 合计, 4), round(Open 合计, 4), 成员股票日数）
   + 每段标签一项（这一段的票、截到数据最后一天的各标签列取值个数、fragile 行数、STK 合计、FRM 行数、DEP 三档与 NaN 的行数）排序后 sha256 前 16 位；
   --prep 写进常数，--run 不一致就停。
   环境与面板代码（--prep 和 --run 开头都核对，不一致就停）：QB_DROP_ZERO_VOL 必须 = "1"（脚本用 setdefault，外面设成别的值也会停）；
   kline.SLOPE_BARS = 3；KLINE_SRC_SHA = kline.trend / bars / ohlcv 的源码 + (SLOPE_BARS, MAS) 的 sha1 前 16 位（登记时的面板代码；
   之后面板改了这几个函数 → 停，不用新规则的标签）。
七 A 部分的判定（3 个；h = 20；主指标 x20）：MIN_EV_POOL = 100（合并 x20 有值的事件数）、MIN_MONTHS = 24（这些事件的不同月份数）、MIN_EV_SAMPLE = 30、
   MIN_SEG = 3、MIN_PP = 0.30 pp、区间 98.33%。valid = Z / E / J / W / J2 里 n_s ≥ 30 的段；FULL = 五段都 valid。verdict_a（纯函数，从上往下第一个成立）：
   1 合并 n < 100 或月份 < 24 →「事件太少」；
   2「买点成立」= FULL ∧ 98.33% 下限(x̄) > 0 ∧ x̄ ≥ +0.30 ∧ 98.33% 下限(ȳ) > 0 ∧ valid 各段 x̄_s > 0 ∧ valid 各段 ȳ_s > 0；
   3「卖点成立（拿着的人卖掉更好）」与 2 对称（上限 < 0、x̄ ≤ −0.30、各段 < 0）；
   4 合并 x 显著（98.33% 区间不含 0）但有一个 valid 段 x̄_s 与合并方向相反 →「不成立（有一段相反）」；
   5 合并 x 显著但不是 FULL →「样本不全（合并显著）」；
   6 合并 x 显著且 |x̄| ≥ 0.30，但 y 没有同向显著或 y 分段不同号 →「比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）」；
   7 valid ≥ 3 段且各段 x̄_s 同号 →「方向一致但不够」；8 其余 →「没有信息（和平常买差不多）」。
   每个判定同时用两种视角说（买点成立 = 卖点视角「这时卖掉是错的」；卖点成立 = 买点视角「这时买更差」）；另写 95% 区间下结论会不会变（只展示）、
   成功率差（事件 − MUB 任意日子，pp）和 lift（只描述：「胜率高不等于赚钱」）。
   结论用语对照（登记 = 常数 VERDICT_SAY / SEEN；md〇 照判定直接取这一句填空，z = |合并 x̄20|，「好 / 差」按合并 x̄20 的正负取一个）：
   买点成立「月K 往上走时看到 …，第二天买、拿一个月，历史上每个年代都比大盘好约 z pp，也比同一天其他月涨的票好」；
   卖点成立「这时手上有的话先走，历史上之后一个月比大盘差约 z pp」；有一段相反「有的年代好、有的年代差（例如 2008 型慢熊里接飞刀），不能靠」；
   回调本身不加分「好 / 差来自月线在涨本身，回调这个时机不加分」；方向一致但不够「略好 / 略差，但不够确定」；没有信息「这种组合本身不说明什么」；
   规格没列的两个（登记时补、没看任何结果）：事件太少「事件太少，说不了什么」；样本不全「合起来看有差，但不是每个年代 / 股票池都有够多的事件，不能靠」。
八 B 部分（与现行交易系统 B4 = B3 + TBF 结合；loop10_common.load + trendline_study.tbf_gates）：
   先决条件（任一不过就停、不算 B 部分）：1 research_loop.rules_fingerprint = 1241753c8f2529c6；2 B4 重算 = var/out/turn_shape_combo.json 的 cand.TBF
   （trendline_study.same_b4：个股笔数与胜率相同、Calmar 差 ≤ 0.005；trendline_study.B4_TOL 必须 = 本文件登记的 B4_TOL，不等就停）；3 接线核对
   （从来没拿过的 0000.T 放一个 exit_tick → 账户各键和 B4 完全相同：trendline_study.prereq 比 6 个键，本文件再对 loop9_common.KEYS 的全部 8 个键
   （含前一半 / 后一半 h1 / h2）比一次，两边都是 None / NaN 算相同）；4 标签覆盖（B4 每笔成交的信号日都查得到标签；查不到 / 未知的照实归入「标签不全」，
   只计数、不是停的条件（J 年代 MUB 约 2018-10 才有 → 2017〜2018 年中的笔一定未知）；--run 时再数一次、写在 md 开头，有标签不全的年代标 ★）；5 池子假想单笔 nb 与 kept_pool 的 net 一致（|nb − net| < 1e−6，绝对差、不带相对容差；NaN 算不一致）的比例 ≥ 99%
   （BASE_MATCH_MIN；--run 时在任何候选账户 / 配对之前核对、写在 md 开头；三个候选共用这一份 nb）。
   核对的顺序：不用载入行情的几项（b_precheck：规则指纹 = FP、trendline_study.FP / B4_TOL = 登记的值、turn_shape_combo.json 有 cand.TBF）在 --run 开头、
   载入任何数据和算任何结果之前查，不过 → 整个停（什么都没算，可以作为运行前修正）；B4 重算与接线核对要载入 B3，放在 A 之后，不过（含核对时抛错，
   例：「TBF 旗子与信号对不上」）→ B 部分记为停、A 照写进文件；A 之后的其他步骤（B3 载入、A2、B 部分本身）出错也一样：
   只记异常类型名与代码位置（不写异常信息）、B 记为停（出错前算完的候选留在 json 的 B.partial、md 照实列出），照常写出 json / md；--prep 也查这几项，不过就醒目地打印「★ B 先决条件不过」。标签按（票, 日期）查：Z / E / W / Zx 查 Yahoo 27y 标签表，J / Jx 查 J-Quants 标签表（与成交价格同一来源）。
   B-卖（判定 3 个）：MXDW = B4 +「拿着的日本个股收盘时处于 MUDW → 第二天开盘卖」（收盘时处于状态的任意一天，不是「刚变成」；成交日当天收盘也算；
   candle_portfolio exit_tick，reason = pre_earnings；不设冷却；与 X6、止损等现行离场谁先到用谁；核心 ETF、名额、仓位不变）；MXD / MXW 同理对应 MUD / MUW。
   接法：L6.run(W, e, em_tick=C9.tick_of(S.ticker, S.date, tbf), exit_tick={票: frozenset(状态 k 为真的日子)})。池子：W / Jx（V4）和 Zx（posthoc = False，
   只报告）里 B4 会买的信号（kept_pool 且 TBF 没挡）→ turn_shape_combo.single_with_events 做「X6」对「X6 + 事件」配对 → loop11_common.pair_stats。
   几乎不触发：Z + E + J 三个候选账户里因事件多卖出的个股笔数（候选的 pre_earnings 笔数 − B4 的同一数）< 10（MIN_TRIG）→「几乎不触发」，不下第一关结论。
   第一关 = research_loop11.stage1(cand, base, other={W, Jx, Zx}, lenses=None, posthoc=False)，过任一条路线就算：路线 A（账户）Calmar 差三个年代合计
   ≥ +0.03、每个年代 ≥ −0.02、最大回撤不深 2 pp 以上、前一半 / 后一半合计 ≥ −0.02、合起来胜率差 ≥ −2 pp；路线 B（成功率）合起来胜率差 ≥ +2 pp 且每笔差 ≥ 0、
   每个年代胜率差 ≥ −2 pp、账户不变差；两条路线都要 V4（W 和 Jx 同方向）。第二关（第一关过了才做；另行登记、只运行一次）：事件日在每只票自己的日序列上
   循环平移 400 次，候选严格大于 400 次里的最大值。两关都过 =「更好候选」（只报告给用户）。
   B 每个候选的结论只有三种写法：「几乎不触发」/「第一关通过（要另行登记第二关）」/「第一关不过」（这次只做第一关）。
   B-买（只描述，不判定）：Z / E / J 的 B4 实际成交（窗口内买入、已平仓、去掉 1545 / 1482 / 1655 / 2845，信号日 = 成交日前一个交易日，net = 引擎 pnl ÷ 成本）
   与 W / Jx 里 B4 会买的信号（X6 假想单笔的净收益）。分组一（信号日收盘时的组合）：MUDW / MUD / MUW / MUN / 月K 上升但不满 3 个月 / 月K 横着走或往下走 /
   标签不全（没有行、D / W / M 有 NA、或 MUB 未知：「月K 上升但 MUB 未知」「月K 横着走 / 往下走但 MUB 未知」也归这里，不进「不满 3 个月」「横着走或往下走」）。
   分组二（信号日及之前 20 行 = 这只票自己的 21 行，含信号日；看信号日那天的 MUB）：P1 MUB 为真且出现过 MUDW；P2 MUB 为真、不属于 P1、出现过
   MUD 或 MUW；P3 MUB 为真、以上都没出现过；P4 MUB 为假；NA。每组报笔数、胜率、每笔、95% 区间（按信号月聚类）。Zx 不分组（留作以后任何买点过滤的
   V6 没看过的数据）。读法写死：哪组差得多都不作为规则；任何过滤想法都属于事后、要另行登记。
   另外只描述：B4 成交里持有期内（成交日收盘〜实际卖出前一天）出现状态 k 的笔数、成交日当天已处于状态 k 的笔数；这些笔改卖之后的胜率和每笔（取自候选账户）。
   不做：不把「逢跌买」作为新买点加进账户测（以前登记过「反向 / 抄底类不再单独重测」；A 部分已回答买点问题；要做须另行登记、由用户决定）。
九 多重检验：登记的判定 6 个（A 3 个：Bonferroni 98.33% + 两个基准同向显著 + 五段点估计同号 + 幅度 ≥ 0.30 pp + 合并 ≥ 100 个事件、≥ 24 个月；
   B 3 个第一关；第二关 400 次平移，误报约 1/401）。只描述、事先列全、不能升级为判定：h = 5 / 10 / 40 / 60；成功率、lift、成功率差；N = 0 / 6、MUC3、
   已完成口径；J-Y；去掉 fragile 事件（fragile = 事件日这一行自己的 D / W / M 近平局（FR），或 MUB 用到的前 3 根已完成月K 的月末行近平局（FRM：
   那几根月末标签决定 MUB，复权后浮点可能翻转，FR 看不到））；MUD / MUW 细分；MUN、MUA、MNDW / MND / MNW；结束事件、状态日格子；跌幅分档（离过去 20 行（含当天）最高收盘
   < 5% / 5〜10% / ≥ 10%）；大盘一起跌（同段成员里 D 已知的票中 D = −1 的比例 ≥ 0.50）vs 个股自己跌；按年份、J2 两半（≤ 2022-06-30 / ≥ 2022-07-01）、
   去掉事件最多的 3 个月、单一年份贡献占比；按季度聚类的区间；A2；B-买分组；B4 触发笔的描述。
   数据反复使用（照实写）：Z / E / J / W / J2 已被 mtf_study、candle、madev_event、rebound、turn_shape 四轮、trendline 等用过很多次；以往 159 个做法里
   π0 ≈ 51%，三个样本全为正的 17 个、随机预期 19.9 个；同类先验接近 0。
   登记后不改：N = 3、COOL = 20、h = 20、HORIZONS、门槛（0.30 / 100 / 24 / 30 / 3）、MIN_PEERS = 5、98.33%、SEED、BOOT_N、RT、样本、窗口、POOL 的组成、
   BREADTH_CUT、跌幅分档、MIN_TRIG = 10、BASE_MATCH_MIN = 0.99。运行前发现必须改的地方：只能在看到任何结果之前另交「运行前修正」提交（写明没有算出任何结果）。
十 登记前个数（--prep：只数事件个数和诊断，不算任何收益、成功率、超额或均值）：
   1 标签正确性（任何一项不是 0 就停）：逐日穷举 20 只票（8370、1321、4587、4980、9301、9046、7203 + 种子 SEED 随机抽 13 只）× 日 / 周 / 月与
     kline.trend(kline.bars(d.iloc[:i+1], tf)) 比；全部 Yahoo 票与 J-Quants 列每只随机 5 行 × 3 个周期；已完成月标签与截断重算一致；近平局回退次数、fragile 行数。
     固定的 9301.T / 9046.T 不在任何样本里，27y 缓存是旧的价格调整口径（meta 没有 "adj": 2，冻结后 leap_data 载入不了）→ 只读地直接读缓存文件
     （exh_raw / read_cache_direct；比的是同一份行情上快速算法与原函数，和复权口径无关；不进 DATA_FP）。缺票和不一致分开报（label_check_stop），都停。
   2 数据：每段票数、行数、日期范围、窗口内交易日数、成员股票日数；删掉的非 JPX 交易日行数、成交量 0 行数；J2 里成交量 0 但收盘有值的行数；标签输入与收益面板
     重叠日的最大相对差；薄日个数；DATA_FP。
   3 标签分布（每段）：D / W / M 的上升 / 震荡 / 下降 / NA 占比；MUB 在 N = 0 / 3 / 6、MUC3 下占成员股票日的比例；MUB 最早有值日期的中位数；连续上升
     已完成月数的分布；各组状态日数（状态日 = 每 5 个市场交易日一天，和 36 格同一口径；窗口内全部日子的状态股票日数另报）；36 格的状态日数。
   4 事件个数：每段 × 每个状态的事件数（按年份、不同月份数、事件最多 5 个月的占比）；各 h 下 O[e+1] 与 C[e+h] 都有值的个数（只看有没有价格）；y 能算
     （当天同伴 ≥ 5）的个数；J2 因 h 天内退市而缺价的个数；同伴不到 5 只的天数；敏感度、J-Y、MN 对照、结束事件和「月线转弱」的个数；大盘一起跌的占比；
     跌幅三档的个数；可行性预检（FULL 能不能成立、合并是否 ≥ 100 个事件、≥ 24 个月）。
   5 标签来源的差别：今天的日経225 在 2018-10〜2026-09 的 Yahoo 与 J-Quants 标签一致率（D / W / M）；Yahoo 删 / 不删工作日成交量 0 行时标签不同的行数。
   6 B 部分：规则指纹；B4 重算与参照（已公开的基准）；接线核对；标签覆盖；B4 成交笔数（参照 Z 28 / E 34 / J 52）；每个候选持有期内出现状态的 B4 成交笔数、
     成交日当天已处于状态的笔数；W / Jx / Zx 里 B4 会买的信号数与其中成交后 60 行内出现状态的个数；B-买两种分组的个数（不含 Zx）；A2 的单笔次数和用时估计。
   7 用时与峰值内存。个数写进 sim_changes 登记节和 registry 的 notes；有意外照实写，不改规则。
十一 输出：var/out/month_up_dip_study.md / .json（只有汇总统计，没有个股名单和原始行情）。md 开头：代码 <rev>（scripts/ 与 qbreak/ 下有未提交的改动时
   标出并列出文件）、DATA_FP、规则指纹、先决条件（含 4 标签覆盖的笔数、5 池子一致的比例）、判定规则摘要；正文 〇 一句话结论（买点 / 卖点视角）、
   一 面板速查主表（MUDW / MUD / MUW，h20，合并：事件数与月份数、第二天买拿 20 个交易日的成功率与 ALL / MUB 任意日子的成功率、平均 / 中位 net、
   x̄ 与 ȳ（95% / 98.33%）、卖对的比例、卖出避开的收益、判定）、二 分段表（Z / E / J / W / J2 / 合并；J-Y 另附、标「只描述」；列 = n、成功率、net̄、
   x̄、ȳ 及区间）、三 各期限 h5 / 10 / 20 / 40 / 60、四 只描述（36 格、细分、MUN / MUA / MN 对照、敏感度、结束事件、跌幅、大盘一起跌、年份、去掉事件最多的
   3 个月、A2；J-Y 对 J 用同一期间：≥ max(SRC_CMP_FROM, J 这个状态第一个事件日)；全期的那组标「期间不同」）、五 结合 B4（B-卖账户表：Calmar、回撤、
   前后两半、笔数、胜率、每笔、因事件卖出的笔数；stage1 各项；池子配对；B-买分组表）、六 与登记前个数（PREP_EVENTS：--prep 之后写进常数，
   --run 逐项列「登记前 / 运行时」）/ 事前预期的对照、七 局限和结论上限、「非投资建议」。
   json 键：registered（全部登记常数）、git、data_fp、prereq、counts、A、verdict、describe、B（cand / base / stage1 / pools / buy_groups 等）、elapsed_s。
   只运行一次的保证：A 部分一算完就写 var/out/month_up_dip_study.partial.json（之后 A2 写一次、B 的先决条件 4 / 5 核对完与每个候选
   算完各写一次、最后再写一次）；最后先写 json 再写 md，然后删掉 partial；
   var/out 里 .json / .partial.json / .md（以及写到一半留下的 .json.tmp / .partial.json.tmp）任何一个已经存在 → 停（中途出错留下的 partial 也算跑过：照实记录、由用户决定，不重跑）；不能换输出目录；
   终端只报「完成」，判定只在文件里（--run 的终端只有进度、个数与先决条件；A / B 的判定和任何收益数字都不打印，最后只打印输出文件的路径）。
   结果提交：sim_changes 结果节（标题「## 日期「月K 往上走时日K / 周K 往下走：买卖点成功率与收益率」结果（登记 <hash>；只运行一次）：<一句话> → 模拟盘不变」）、
   registry（kind = study，domain = 选股/买点，卖点结论写进 notes）、重新生成 research_map、HANDOFF / CHECK_TIMELINE 结果子条目（写明「不进定期检查」）、
   待办〔75〕给出选项并标推荐：① 只记结论、不改 ② 面板这三种组合旁边只展示历史统计（例如「历史上之后 20 个交易日：赚钱的比例 x%、平均 y%、比大盘 z pp；
   这不是预测」）③ 第一关过了的卖点候选另行登记第二关 ④ 前向记录。
十二 事前预期（运行前写，来自以往结论）：A 三个状态 x̄ 多半在 ±0.3 pp 之内，最可能「没有信息」或「方向一致但不够」；MUDW 年代相反的可能性最高
   （E / W 在 2008 型慢熊里接飞刀为负、J / J2 在 V 形反弹里为正 →「不成立（有一段相反）」）；MUD 约为 0、ȳ 可能略正（约 1 个月的短期反转）；
   MUW 约为 0 或略负（中期动量）；任一状态「买点成立」的概率不到 5%，「卖点成立」也低。P(net20 > 0) 约 50〜56%，与 MUB 任意日子差 ±3 pp 之内，
   左尾偏厚；卖对的比例约 45〜50%（多半卖早了）；效应多半来自全市场一起跌之后的反弹，个股自己跌的部分约 0 或为负。B：现行持有中位 11〜15 天，
   MXDW / MXW 可能「几乎不触发」；MXD 会碰到一些（早卖：胜率略升、每笔下降，第一关多半不过）；每个候选第一关约 2〜5%；B-买 MUDW / MUD 组几乎为空。
十三 局限：
   1 幸存者偏差：Z / E / J / W 用的是今天的名单，只有 J2 是时点成员；J2 里事件后 h 天内退市的票收益是 NaN、被丢掉 → 结果偏乐观。
   2 价格口径：Yahoo 拆股 + 分红调整、J-Quants 只调拆股 → J / J2 的标签只是近似于面板（J-Y 量化这个差；登记前个数：今天的日経225 在 2018-10〜2026-09
     Yahoo 与 J-Quants 标签一致率 D 97.764% / W 95.234% / M 91.567% / MUB 95.076%）；研究删掉工作日成交量 0 的行、面板保留 → 少数行的标签不同
     （登记前个数：Yahoo 3,644,026 行里 D 14,284 / W 1,404 / M 1,135 行）。
   3 热身：J / J2 约 2018-10〜11 起才有事件（缺 2017〜2018 年中），Z 约 2002 年初起（MUB 最早有值日期的中位数 2002-02-01）。
   4 主口径 as-of：偏离仓库「只用已完成 K 线」的约定（理由见一）；部分 K 线的标签会在周内 / 月内来回翻，冷却期只能部分处理；fragile 行受复权影响可能翻转，
     只做敏感度。
   5 重叠与扎堆：同一只票的主窗口不重叠，但不同票同一天、相邻月份仍然相关，按月聚类只处理一部分；事件可能集中在 2008、2020-03、2024-08、2025-04
     → 另报一起跌 / 自己跌、年份、去掉事件最多的 3 个月、按季度聚类。
   6 基准与成本：基准是同段等权平均（含自己），不是指数；事件研究税前、不扣滑点、不处理涨停（A2 处理了）。
   7 「在跌」的定义：只按面板标签，没有覆盖跌幅、连跌、MACD 等写法，不能外推到这些写法。
   8 B 部分：样本小（B4 只有 114 笔 = Z 28 / E 34 / J 52，单个年代一笔约等于 2〜4 pp 的胜率；J 有 7 笔在 2017〜2018 热身期、标签不全）；
     W 池子的成交用 21y 价格、标签用 27y 价格，有很小的差。
   9 缓存：冻结在 --prep 时（2026-10-08）的缓存状态，用 DATA_FP 7c2fedecdacfe0bf 核对（--run 不一致就停），不包含之后的复权修正。DATA_FP 只覆盖 A 部分
     各段（标签输入、收益面板、标签）；B 部分的输入（loop10_common.load 的 21y 行情、Zx、宏观因子缓存）不在指纹里，靠先决条件 2（B4 重算 = 参照）与 5 核对。
     照实写：第一次试跑 B 部分载入时（加 _read_cache / fill_index_from_intraday / factors._get 三处补丁之前；文件时间 2026-10-08 01:42〜01:43 UTC），
     var/cache/factors/ 下 115 个宏观因子缓存（FRED 67、Yahoo 36、日银 7、GPR 2、TPU / Shiller / 财务省各 1；已 gitignore）被联网刷新过；
     加补丁之后，经本脚本（freeze_cache 之后）的运行对行情 / 因子缓存 0 写入（--prep 只写了本研究自己的标签缓存 var/cache/month_up_dip_labels.pkl），
     --prep 时 B4 重算仍与参照一致。另：var/cache/7203.T_27y.csv 在 2026-10-08 02:50 UTC（--prep 之前）被一次没有冻结的读取
     （qbreak.data「缓存落后 → 重新下载」；来源未查明）更新到 2026-10-08，已包含在 DATA_FP 里。
   10 多重检验与数据复用：见九。
十四 结论上限：A 最多「买点成立 / 卖点成立」，只回答问题、不改交易（之后的选项要用户同意：面板这三种组合旁边只展示历史统计（写明「这不是预测」）、
   前向记录、另行登记「B4 + 新买点」的账户检验（做法和门槛同 madev_event D1〜D3））；
   B 最多「更好候选」，进模拟盘或执行器要用户在对话里明确同意并记进 sim_changes.md。本研究不改模拟盘、执行器、例行任务、面板、策略参数、仓位、股票池、
   宏观阈值。非投资建议。
登记时的决定（2026-10-08）：W 段用 Yahoo 27y 缓存 + loop10_common.zx_names()（去掉 4 只今天的日経225）；B 部分卖点触发 = 收盘时处于状态的任意一天
   （不是「刚变成」）；在云端容器里登记、运行（数据缓存在那里）；A2 只做 Z / E / J。规格里的常数照写。
实现时的解释（登记时定、没看任何结果；正文各节已写，这里汇总）：W 实际 667 只（六）；Yahoo 标签表 = 今天的日経225 ∪ zx_names（一；Zx 池子查得到）；
   标签每只票只算一次、截到用到它的各段里最晚的数据最后一天（一；与每段分别算逐位相同）；CMP 口径 = 周K 用已完成周K、月线条件 = 最近 3 根按日历已完成的
   月K 都上升，「日历最后一个周期不算已完成」（一 / 二）；MUB 未知不进任何状态和基准（二：ALL 只算 MUB 已知的成员，MN* 与 36 格也要 MUB 已知）；
   细分 = 母组事件按事件日拆开（三）；结束事件 W 已知且 ≥ 0、同一天只算一个、结束日不要求在窗口里 / 是成员（四）；同伴数 = r_h 有值的 MUB 同伴，
   不到 5 只 y 与 lift 都是 NaN（五）；跌幅的「过去 20 行」含当天、大盘一起跌的分母 = D 已知的成员（九）；B-买分组一的「标签不全」含「月K 上升但 MUB 未知」、
   分组二 = 21 行、持有期 = 成交日 ≤ 日期 < 卖出日（八）；先决条件 4 只计数、不是停的条件（八）；冻结缓存多加三处补丁、DATA_FP 多带段名与收益面板 /
   标签项（六）；规格没列的两句结论用语（七）；RT 核对（四）；只运行一次的保证、终端不打印判定（十一）；A 之后出错只照实记下、照常写出 json / md，
   出错前算完的 B 候选留在 B.partial（八 / 十一）。
用法：python scripts/month_up_dip_study.py --prep（冻结缓存 + 标签 + 标签核对 + 先决条件 + 只数个数；不算任何收益；最后打印要写进常数的
      DATA_FP 与 PREP_EVENTS）；python scripts/month_up_dip_study.py --run（只运行一次：A + A2 + B 第一关 + 只描述）。可加 --workers（缺省 4）。
缓存（不入库）：var/cache/month_up_dip_labels.pkl（钥匙 = kline_series / calendar_jp / mtf 的文件 sha1 + KLINE_SRC_SHA + 本文件标签代码的 sha1
      + 标签用到的登记常数的值（N_MONTHS、N_SENS、RECENT、LABEL_FROM、TAB_COLS、VARIANTS、CHECK_ROWS、SEED、DEPTH_BINS 等）+ 输入指纹，不一致就停）。非投资建议。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import logging
import os
import pickle
import resource
import subprocess
import sys
import time
import traceback
import warnings
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qbreak import calendar_jp as CAL                                       # noqa: E402
from qbreak import kline as K                                               # noqa: E402
from qbreak import kline_series as KS                                       # noqa: E402
from qbreak import mtf as MTF                                               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NA = KS.NA

# ───────────────────────── 登记常数（登记后不改） ─────────────────────────
IDS_A = ("MUDW", "MUD", "MUW")
IDS_B = ("MXDW", "MXD", "MXW")
B_OF = {"MXDW": "MUDW", "MXD": "MUD", "MXW": "MUW"}
DESC = ("MUN", "MUA", "MNDW", "MND", "MNW")
SUBS = ("MUD-u", "MUD-f", "MUW-u", "MUW-f")
SUB_OF = {"MUD-u": ("MUD", "W", 1), "MUD-f": ("MUD", "W", 0), "MUW-u": ("MUW", "D", 1), "MUW-f": ("MUW", "D", 0)}   # 细分 = 母组事件 ∧ 事件日那一列 = 值
GROUPS = (*IDS_A, "MUN", "MUA", *SUBS, "MNDW", "MND", "MNW")
END_IDS = {"MUDW": "MUDWE", "MUD": "MUDE", "MUW": "MUWE"}
NAMES = {"MUDW": "月涨 + 日K、周K 都往下走", "MUD": "月涨 + 只有日K 往下走", "MUW": "月涨 + 只有周K 往下走",
         "MUN": "月涨、日周都没跌", "MUA": "三个都往上走", "MNDW": "月K 没在往上走 + 日K、周K 都往下走",
         "MND": "月K 没在往上走 + 只有日K 往下走", "MNW": "月K 没在往上走 + 只有周K 往下走",
         "MUD-u": "MUD 事件日周K 上升", "MUD-f": "MUD 事件日周K 震荡", "MUW-u": "MUW 事件日日K 上升", "MUW-f": "MUW 事件日日K 震荡",
         "MXDW": "拿着的票收盘时处于 MUDW → 第二天开盘卖", "MXD": "拿着的票收盘时处于 MUD → 第二天开盘卖",
         "MXW": "拿着的票收盘时处于 MUW → 第二天开盘卖"}
N_MONTHS = 3
N_SENS = (0, 6)
VARIANTS = {"main": ("MUB", "W"), "N0": ("MUB0", "W"), "N6": ("MUB6", "W"), "MUC3": ("MUC3", "W"), "CMP": ("MUBc", "Wc")}
COOL = 20
END_WITHIN = 60
EVERY = 5
RECENT = 20                                                                 # 跌幅分档的「过去 20 行」、B-买分组二的「信号日及之前 20 行」
HORIZONS = (5, 10, 20, 40, 60)
H = 20
SAMPLES = ("Z", "E", "J", "W", "J2")
POOL = ("Z", "E", "W", "J2")
SEGS = ("Z", "E", "J", "W", "J2", "JY")                                      # JY = J-Y（只描述）
SRC = {"Z": "yahoo", "E": "yahoo", "W": "yahoo", "JY": "yahoo", "J": "jq", "J2": "jq"}
WINDOWS = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", "2026-09-25"),
           "J2": ("2017-01-04", "2026-09-25"), "W": ("2006-10-01", "2016-09-30"), "JY": ("2017-01-04", "2026-09-25")}
DATA_RANGE = {"Z": ("2000-01-04", "2007-06-29"), "E": ("2005-09-01", "2016-12-30"), "J": ("2016-09-26", "2026-09-25"),
              "J2": ("2016-09-26", "2026-09-25"), "W": ("2005-09-01", "2017-03-31"), "JY": ("2016-09-26", "2026-09-25")}
W_NAMES = "zx_names"
LABEL_FROM = "1999-01-01"
MIN_EV_POOL, MIN_MONTHS, MIN_EV_SAMPLE, MIN_SEG = 100, 24, 30, 3
MIN_PP = 0.30
MIN_PEERS = 5
CI_LEVEL = 1 - 0.05 / 3
Q98 = (100 * 0.05 / 3 / 2, 100 - 100 * 0.05 / 3 / 2)                          # 98.33% 区间 = 0.833 / 99.167 分位
Q95 = (2.5, 97.5)
BOOT_N, SEED = 2000, 20261008
TIE_EPS = KS.TIE_EPS
BREADTH_CUT = 0.50
DEPTH_BINS = (5.0, 10.0)
DEPTH_NAMES = ("< 5%", "5〜10%", "≥ 10%")
J2_HALVES = ("2022-06-30", "2022-07-01")
DROP_TOP_MONTHS = 3
RT_REF = 0.1496                                                             # loop11_common.bt_rt() 的 rt（%）；运行时差 ≥ RT_TOL 就停
RT_TOL = 5e-5
FP = "1241753c8f2529c6"                                                     # B4 = B3 + TBF 的模拟盘规则指纹
B4_TOL = 0.005
MIN_TRIG = 10
BASE_MATCH_MIN = 0.99
B4_TRADES_REF = {"Z": 28, "E": 34, "J": 52}
N225_ERAS = ("Z", "E", "J")
B_POOLS = ("W", "Jx", "Zx")
B_SM = {"W": "W", "Jx": "J2", "Zx": "Zx"}                                    # 池子的行情在 W["SM"] 的哪个键
B_SRC = {"Z": "yahoo", "E": "yahoo", "J": "jq", "W": "yahoo", "Jx": "jq", "Zx": "yahoo"}
POOL_WINDOW = 60                                                            # 只数个数：成交后 60 行内有没有状态
A2_SEGS = ("Z", "E", "J")
A2_IDS = (*IDS_A, "MUN")
A2_MS = 20                                                                  # A2 用时估计：每次单笔约 20 ms（登记前不调用，只估）
EXH_FIXED = ("8370.T", "1321.T", "4587.T", "4980.T", "9301.T", "9046.T", "7203.T")
EXH_RANDOM = 13
CHECK_ROWS = 5
SRC_CMP_FROM = "2018-10-01"
STOCK_SKIP = ("1545.T", "1482.T", "1655.T", "2845.T")
SLOPE_BARS = 3                                                              # 面板 kline.SLOPE_BARS（--prep / --run 开头核对）
KLINE_SRC_SHA = "65302837180f8b35"                                          # kline.trend / bars / ohlcv 源码 + (SLOPE_BARS, MAS) 的 sha1 前 16 位
ZERO_VOL_ENV = "1"                                                          # QB_DROP_ZERO_VOL 必须是这个值
BASE_MATCH_TOL = 1e-6                                                       # 先决条件 5：|nb − net| < 1e−6（绝对差）
DATA_FP: str | None = "7c2fedecdacfe0bf"                                    # --prep（2026-10-08）之后写入（登记提交里）；--run 不一致就停
PREP_EVENTS: dict | None = {                                                # --prep（2026-10-08）之后写入（登记提交里）：{段: {状态: 事件数}}；--run 在 md 第六节逐项对照
    "Z": {"MUDW": 584, "MUD": 1385, "MUW": 494, "MUN": 679, "MUA": 938, "MNDW": 932, "MND": 1049, "MNW": 792},
    "E": {"MUDW": 1192, "MUD": 2703, "MUW": 953, "MUN": 1244, "MUA": 1867, "MNDW": 3425, "MND": 3266, "MNW": 2905},
    "J": {"MUDW": 1110, "MUD": 2510, "MUW": 915, "MUN": 1198, "MUA": 1810, "MNDW": 2697, "MND": 2588, "MNW": 2162},
    "W": {"MUDW": 3531, "MUD": 7873, "MUW": 2973, "MUN": 3777, "MUA": 5491, "MNDW": 9767, "MND": 9120, "MNW": 8393},
    "J2": {"MUDW": 4281, "MUD": 9541, "MUW": 3538, "MUN": 4752, "MUA": 6862, "MNDW": 11959, "MND": 11919, "MNW": 10143},
    "JY": {"MUDW": 1514, "MUD": 3588, "MUW": 1253, "MUN": 1646, "MUA": 2554, "MNDW": 3039, "MND": 2898, "MNW": 2352}}
LABEL_CACHE = "month_up_dip_labels.pkl"
OUT_MD, OUT_JSON, OUT_PARTIAL = "month_up_dip_study.md", "month_up_dip_study.json", "month_up_dip_study.partial.json"
EXPECT_A = {"MUDW": "x̄ 多半在 ±0.3 pp 之内；年代相反的可能性最高（E / W 慢熊里为负、J / J2 V 形反弹里为正 →「不成立（有一段相反）」）",
            "MUD": "x̄ 约 0，ȳ 可能略正（约 1 个月的短期反转）", "MUW": "x̄ 约 0 或略负（中期动量）"}
EXPECT_B = {"MXDW": "可能「几乎不触发」", "MXD": "会碰到一些，早卖：胜率略升、每笔下降，第一关多半不过", "MXW": "可能「几乎不触发」"}
G1 = ("MUDW", "MUD", "MUW", "MUN", "月K 上升但不满 3 个月", "月K 横着走或往下走", "标签不全")
G2 = ("P1", "P2", "P3", "P4", "NA")
G2_NAMES = {"P1": "MUB 为真且出现过 MUDW", "P2": "MUB 为真、出现过 MUD 或 MUW", "P3": "MUB 为真、都没出现过", "P4": "MUB 为假", "NA": "未知"}
MLEVELS = ("MUB", "月K 上升但不满 3 个月", "横着走", "往下走")
LEVEL3 = {1: "上升", 0: "震荡", -1: "下降"}
VERDICT_VIEW = {"事件太少": ("事件太少，不下结论", "事件太少，不下结论"),
                "买点成立": ("买点成立", "这时卖掉是错的"),
                "卖点成立（拿着的人卖掉更好）": ("这时买更差", "卖点成立（拿着的人卖掉更好）"),
                "不成立（有一段相反）": ("不成立（有一段相反）", "不成立（有一段相反）"),
                "样本不全（合并显著）": ("样本不全（合并显著）", "样本不全（合并显著）"),
                "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）": ("比大盘有差，但回调本身不加分", "比大盘有差，但回调本身不加分"),
                "方向一致但不够": ("方向一致但不够", "方向一致但不够"),
                "没有信息（和平常买差不多）": ("没有信息（和平常买差不多）", "没有信息（卖不卖差不多）")}
# 七「结论用语对照」（登记；运行后 md〇 照判定直接取这一句填空，不另写）：{seen} = SEEN[状态]；{z} = |合并 x̄20|（pp，两位小数）；
# {hao} / {luehao} = 合并 x̄20 > 0 →「好」/「略好」，< 0 →「差」/「略差」（没有值或 = 0 → 「好 / 差」/「略好 / 略差」原样）。
# 规格只列了 6 个判定的说法；「事件太少」「样本不全（合并显著）」两句是登记时同一口吻补上的（没看任何结果）。
SEEN = {"MUDW": "日K、周K 都往下走", "MUD": "只有日K 往下走（周K 没在跌）", "MUW": "只有周K 往下走（日K 没在跌）"}
VERDICT_SAY = {"买点成立": "月K 往上走时看到{seen}，第二天买、拿一个月，历史上每个年代都比大盘好约 {z} pp，也比同一天其他月涨的票好",
               "卖点成立（拿着的人卖掉更好）": "这时手上有的话先走，历史上之后一个月比大盘差约 {z} pp",
               "不成立（有一段相反）": "有的年代好、有的年代差（例如 2008 型慢熊里接飞刀），不能靠",
               "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）": "{hao}来自月线在涨本身，回调这个时机不加分",
               "方向一致但不够": "{luehao}，但不够确定",
               "没有信息（和平常买差不多）": "这种组合本身不说明什么",
               "事件太少": "事件太少，说不了什么",
               "样本不全（合并显著）": "合起来看有差，但不是每个年代 / 股票池都有够多的事件，不能靠"}
EPS = 1e-12                                                                # verdict_a 的边界容差（x̄ ≥ MIN_PP − EPS 等：0.30 正好算够）


# ───────────────────────── 冻结缓存 / 数据指纹 / git ─────────────────────────
def _no_download(*a, **k):
    raise RuntimeError("冻结缓存：不联网、不写缓存（month_up_dip_study）")


def freeze_cache() -> list[str]:
    """qbreak.data：behind → None、partial_cached → False、_yf_download → 直接抛错（缺文件的票只会被跳过）。
    同一目的的补充（不联网、不写缓存；登记前试跑发现只有那三处不够）：fill_index_from_intraday → 原样返回（指数日线补缺）；
    _read_cache 不看有效期（TTL 过了也读同一份缓存，否则 B 部分载入 1655.T 等会因为不能下载而停）；
    qbreak.factors._get → 直接抛错（宏观因子 FRED / Yahoo / 日银 / 财务省：_cached 下载失败时用已有的缓存）。返回改了哪些名字。"""
    from qbreak import data as QD
    from qbreak import factors as QF
    QD.behind = lambda *a, **k: None
    QD.partial_cached = lambda *a, **k: False
    QD._yf_download = _no_download
    QD.fill_index_from_intraday = lambda t, df, *a, **k: df
    if not getattr(QD._read_cache, "_frozen", False):
        orig = QD._read_cache

        def _read_cache(ticker, years, ttl_hours=None):
            return orig(ticker, years, float("inf"))

        _read_cache._frozen = True
        QD._read_cache = _read_cache
    QF._get = _no_download
    return ["data.behind", "data.partial_cached", "data._yf_download", "data.fill_index_from_intraday", "data._read_cache（不看 TTL）",
            "factors._get"]


_OHLCV: dict = {}


def memo_leap_data() -> None:
    """同一进程里同一只票的 Yahoo 27y 缓存只读一次（leap_data.ohlcv 包一层；内容相同，只是省时间）。"""
    import leap_data as LD
    if getattr(LD.ohlcv, "_memo", False):
        return
    orig = LD.ohlcv

    def ohlcv(tickers, years=LD.YEARS):
        if years != LD.YEARS:
            return orig(tickers, years)
        need = [t for t in tickers if t not in _OHLCV]
        if need:
            try:
                got = orig(need, years)
            except Exception:                                               # noqa: BLE001  全部缺 → load_universe 抛错
                got = {}
            for t in need:
                _OHLCV[t] = got.get(t)
        return {t: _OHLCV[t] for t in tickers if _OHLCV.get(t) is not None}

    ohlcv._memo = True
    LD.ohlcv = ohlcv


def fp_items(segs: dict, LAB: dict) -> list:
    """数据指纹的项（见文件开头六）：每段每只票 (段, 票, 首日, 末日, 行数, round(Close 合计, 4))（标签输入的行、截到这一段的数据最后一天）；
    每段收益面板一项 ("panel", 段, 市场日数, 首日, 末日, round(Close 合计, 4), round(Open 合计, 4), 成员股票日数)（段里有 days 时）；
    每段标签一项 ("labels", 段, {列: {取值: 行数}}, fragile 行数, STK 合计, FRM 行数, [DEP 三档与 NaN 的行数])
    （这一段的票、截到数据最后一天；表里有这些列时；DEP 分档用登记的 DEPTH_BINS，RECENT / 分档改了指纹就变）。"""
    out = []
    for s in SEGS:
        if s not in segs:
            continue
        seg = segs[s]
        hi = pd.Timestamp(DATA_RANGE[s][1])
        cnt = {k: np.zeros(256, np.int64) for k in TAB_COLS}
        fr = stk = frm = 0
        dep = np.zeros(4, np.int64)                                          # depth_bin 的 −1（NaN）/ 0 / 1 / 2
        has_lab = False
        for t in seg["names"]:
            tab = LAB[SRC[s]].get(t)
            if tab is None or not len(tab):
                out.append((s, t, None, None, 0, 0.0))
                continue
            m = tab.index <= hi
            c = tab["C"].to_numpy(float)[m]
            ix = tab.index[m]
            out.append((s, t, str(ix[0].date()) if len(ix) else None, str(ix[-1].date()) if len(ix) else None, int(m.sum()),
                        round(float(c.sum()), 4)))
            if set(TAB_COLS) <= set(tab.columns):
                has_lab = True
                for k in TAB_COLS:
                    cnt[k] += np.bincount(tab[k].to_numpy(np.int8)[m].astype(np.int16) + 128, minlength=256)
                fr += int(tab["FR"].to_numpy(bool)[m].sum()) if "FR" in tab.columns else 0
                stk += int(tab["STK"].to_numpy(np.int64)[m].sum()) if "STK" in tab.columns else 0
                frm += int(tab["FRM"].to_numpy(bool)[m].sum()) if "FRM" in tab.columns else 0
                if "DEP" in tab.columns:
                    dep += np.bincount(depth_bin(tab["DEP"].to_numpy(float)[m]).astype(np.int64) + 1, minlength=4)
        if "days" in seg:
            days = pd.DatetimeIndex(seg["days"])
            out.append(("panel", s, int(len(days)), str(days[0].date()) if len(days) else None, str(days[-1].date()) if len(days) else None,
                        round(float(np.nansum(np.asarray(seg["C"], float))), 4), round(float(np.nansum(np.asarray(seg["O"], float))), 4),
                        int(np.asarray(seg["mem"], bool).sum())))
        if has_lab:
            out.append(("labels", s, {k: {str(int(v) - 128): int(cnt[k][v]) for v in np.flatnonzero(cnt[k])} for k in TAB_COLS}, int(fr), int(stk),
                        int(frm), [int(x) for x in dep]))
    return out


def data_fp(items) -> str:
    """排序后 sha256 前 16 位（顺序无关）。"""
    s = json.dumps(sorted([list(x) for x in items], key=lambda r: json.dumps(r, default=str)), ensure_ascii=False, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def kline_src_sha() -> str:
    """标签依赖的面板代码：kline.trend / bars / ohlcv 的源码 + (SLOPE_BARS, MAS) 的 sha1 前 16 位。"""
    s = "".join(inspect.getsource(f) for f in (K.trend, K.bars, K.ohlcv)) + repr((K.SLOPE_BARS, K.MAS))
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def check_code() -> dict:
    """--prep / --run 开头：QB_DROP_ZERO_VOL = "1"、kline.SLOPE_BARS = 3、面板代码 = 登记时的（KLINE_SRC_SHA）。任一不对 → 停。"""
    env = os.environ.get("QB_DROP_ZERO_VOL")
    if env != ZERO_VOL_ENV:
        raise SystemExit(f"QB_DROP_ZERO_VOL = {env!r}（登记的是 {ZERO_VOL_ENV!r}）→ 停")
    if K.SLOPE_BARS != SLOPE_BARS:
        raise SystemExit(f"kline.SLOPE_BARS = {K.SLOPE_BARS}（登记的是 {SLOPE_BARS}）→ 停")
    sha = kline_src_sha()
    if sha != KLINE_SRC_SHA:
        raise SystemExit(f"面板标签代码（kline.trend / bars / ohlcv）的 sha1 {sha} ≠ 登记的 {KLINE_SRC_SHA}（登记后改过）→ 停")
    return {"QB_DROP_ZERO_VOL": env, "SLOPE_BARS": int(K.SLOPE_BARS), "kline_src_sha": sha}


GIT_PATHS = ("scripts", "qbreak")                                           # 本研究与它用到的研究工具 / 交易代码都在这两个目录下


def git_info() -> dict:
    """代码版本；scripts/ 与 qbreak/ 下有没有未提交的改动（本文件、kline_series、kline、mtf、calendar_jp，以及复用的 madev_event、loop6 / 9 / 10 / 11_common、
    turn_shape_combo、trendline_study、research_loop11、candle_portfolio、leap_confirm、leap_data、candle_data 等都在里面）。"""
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
        st = subprocess.run(["git", "status", "--porcelain", "--", *GIT_PATHS], capture_output=True, text=True, check=True, cwd=ROOT).stdout
        files = sorted({ln[3:].strip() for ln in st.splitlines() if ln.strip()})
        return {"rev": rev, "dirty": bool(files), "paths": list(GIT_PATHS), "dirty_files": files}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None, "paths": list(GIT_PATHS), "dirty_files": None}


# ───────────────────────── 标签（只用到 t 为止的行） ─────────────────────────
def label_rows(df: pd.DataFrame, end=None) -> tuple[pd.DataFrame, dict]:
    """标签用的行 = kline_series.clean_rows（Close 有值且 Volume > 0、断言递增 / 不重复 / 没有周末、去掉非 JPX 交易日），
    再去掉 LABEL_FROM 之前（数个数，预期 0）与 end 之后的行。"""
    d, info = KS.clean_rows(df)
    early = d.index < pd.Timestamp(LABEL_FROM)
    info["before_from"] = int(early.sum())
    d = d.loc[~early]
    if end is not None:
        late = d.index > pd.Timestamp(end)
        info["after_end"] = int(late.sum())
        d = d.loc[~late]
    info["rows"] = int(len(d))
    return d, info


def completed_up(lab: pd.DataFrame, cal, n: int = N_MONTHS) -> np.ndarray:
    """CMP 口径的月线条件：最近 n 根「按日历已完成」的月K 都是上升 → 1；有 NA → NA；其余 0（int8，对齐 lab 的行）。
    每根已完成月K 的标签 = 它那个月最后一行收盘时的月K 标签（kline_series.month_done），从日历完成日收盘起生效（完成日 ≤ t 的最后一根）。"""
    C = KS.month_done(lab)
    cv = C.to_numpy(np.int8)
    known = np.ones(len(cv), bool)
    good = np.ones(len(cv), bool)
    for k in range(int(n)):
        v = np.full(len(cv), NA, np.int8)
        if k < len(cv):
            v[k:] = cv[:len(cv) - k]
        known &= v != NA
        good &= v == 1
    up = np.where(known, good.astype(np.int8), NA).astype(np.int8)
    comp = MTF.completion_days(pd.DatetimeIndex(cal), "M")
    cd = comp.reindex(MTF.period_key(C.index, "M")).to_numpy()
    ok = ~pd.isna(cd)
    if not ok.any():
        return np.full(len(lab), NA, np.int8)
    s = pd.Series(up[ok], index=pd.DatetimeIndex(cd[ok]))
    return KS.on_days(s, lab.index, fill=NA).to_numpy().astype(np.int8)


TAB_COLS = ("D", "W", "M", "MUB", "MUB0", "MUB6", "MUC3", "Wc", "MUBc")


def prior_month_fragile(lab: pd.DataFrame, n: int = N_MONTHS) -> np.ndarray:
    """FRM：MUB（N = n）用到的 g−1 … g−n 这 n 根已完成月K 里，有没有哪一根的月末那一行本身是近平局（fM）→ bool（对齐 lab 的行）。
    这些月末标签决定了 MUB，复权后浮点可能翻转，但它们的 fM 只记在月末那一行，FR（这一行自己的 fD | fW | fM）看不到。
    和 kline_series._done_by_bar 同样按月K 的绝对序号 asof_M 放（只用到本月之前、已经走完的月份 → 不偷看）；没有那一根 → 不算。"""
    g = lab["asof_M"].to_numpy().astype(np.int64)
    out = np.zeros(len(g), bool)
    if not len(g):
        return out
    last = KS._last_rows(g)
    F = np.zeros(int(g.max()) + 1, bool)
    F[g[last]] = lab["fM"].to_numpy(bool)[last]
    for k in range(1, int(n) + 1):
        j = g - k
        ok = j >= 0
        out[ok] |= F[j[ok]]
    return out


def ticker_table(rows: pd.DataFrame, cal_end, stats: dict | None = None) -> pd.DataFrame:
    """一只票（label_rows 之后的行）→ 每一行的标签表：D / W / M（as-of）、MUB（N = 3）、MUB0 / MUB6、MUC3、Wc / MUBc（CMP 口径）（int8）、
    STK（之前连着几根已完成月K 上升）、FR（这一行自己的 fragile：fD | fW | fM）、FRM（MUB 用到的前 3 根已完成月K 的月末行有 fM：
    prior_month_fragile）、DEP（离过去 20 行（含当天）最高收盘的跌幅 %）、C（收盘，核对与指纹用）。「去掉 fragile 事件」去掉 FR | FRM。"""
    lab = KS.labels_partial(rows, stats=stats)
    out = pd.DataFrame(index=lab.index)
    if not len(lab):
        for k in TAB_COLS:
            out[k] = np.zeros(0, np.int8)
        out["STK"], out["FR"], out["FRM"] = np.zeros(0, np.int16), np.zeros(0, bool), np.zeros(0, bool)
        out["DEP"], out["C"] = np.zeros(0, np.float32), np.zeros(0)
        return out
    for k in ("D", "W", "M"):
        out[k] = lab[k].to_numpy(np.int8)
    out["MUB"] = KS.mub(lab, N_MONTHS).to_numpy(np.int8)
    for n in N_SENS:
        out[f"MUB{n}"] = KS.mub(lab, n).to_numpy(np.int8)
    out["MUC3"] = KS.mubc(lab, N_MONTHS).to_numpy(np.int8)
    cal = KS.jpx_calendar(lab.index[0], max(pd.Timestamp(cal_end), lab.index[-1]))
    out["Wc"] = KS.labels_completed(rows, cal, "W").to_numpy(np.int8)
    out["MUBc"] = completed_up(lab, cal, N_MONTHS)
    out["STK"] = KS.done_streak(lab, "M").to_numpy().astype(np.int16)
    out["FR"] = (lab["fD"] | lab["fW"] | lab["fM"]).to_numpy(bool)
    out["FRM"] = prior_month_fragile(lab, N_MONTHS)
    c = K.ohlcv(rows)["Close"].astype(float)
    out["DEP"] = ((1 - c / c.rolling(RECENT).max()) * 100).to_numpy(np.float32)
    out["C"] = c.to_numpy(float)
    return out[[*TAB_COLS, "STK", "FR", "FRM", "DEP", "C"]]


def sample_check(t: str, rows: pd.DataFrame, tab: pd.DataFrame, k: int = CHECK_ROWS) -> dict:
    """随机 k 行 × D / W / M 与原函数比；再随机 1 根已完成月K 与截断重算比（种子 = SEED + 票名）。"""
    rng = np.random.default_rng([SEED, zlib.crc32(t.encode("utf-8"))])
    out = {"rows": 0, "bad": 0, "month": 0, "month_bad": 0}
    n = len(tab)
    if not n:
        return out
    for i in sorted(rng.choice(n, size=min(k, n), replace=False)):
        for tf in ("D", "W", "M"):
            out["rows"] += 1
            out["bad"] += int(KS.ref_code(rows.iloc[:i + 1], tf) != int(tab[tf].iloc[i]))
    C = KS.month_done(KS.labels_partial(rows))
    if len(C) >= 2:
        j = int(rng.integers(0, len(C) - 1))                                  # 不含最后一根（可能没走完）
        out["month"] += 1
        out["month_bad"] += int(KS.ref_code(rows.loc[:C.index[j]], "M") != int(C.iloc[j]))
    return out


def nd_diff(df: pd.DataFrame, end, tab: pd.DataFrame) -> dict:
    """Yahoo 不删工作日成交量 0 的行（面板的口径）时 D / W / M 和研究（删掉）不同的行数（只比两边都有的行）。"""
    d, _ = KS.clean_rows(df, drop_zero_vol=False)
    d = d.loc[(d.index >= pd.Timestamp(LABEL_FROM)) & (d.index <= pd.Timestamp(end))]
    lab = KS.labels_partial(d)
    common = tab.index.intersection(lab.index)
    a, b = tab.loc[common], lab.loc[common]
    return {"rows": int(len(common)), **{tf: int((a[tf].to_numpy() != b[tf].to_numpy()).sum()) for tf in ("D", "W", "M")}}


def _label_job(item):
    src, t, df, end = item
    try:
        rows, info = label_rows(df, end)
        st: dict = {}
        tab = ticker_table(rows, end, st)
        info["check"] = sample_check(t, rows, tab)
        if src == "yahoo":
            info["nd"] = nd_diff(df, end, tab)
        return src, t, tab, st, info
    except Exception as ex:                                                  # noqa: BLE001
        return src, t, repr(ex), None, None


def _exh_job(item):
    """逐日穷举：每一行 × D / W / M 与 kline.trend(kline.bars(d.iloc[:i+1], tf)) 比；已完成月标签与截断重算比。"""
    t, df, end = item
    try:
        rows, _ = label_rows(df, end)
        tab = ticker_table(rows, end)
        bad = {"D": 0, "W": 0, "M": 0}
        for i in range(len(rows)):
            part = rows.iloc[:i + 1]
            for tf in bad:
                bad[tf] += int(KS.ref_code(part, tf) != int(tab[tf].iloc[i]))
        C = KS.month_done(KS.labels_partial(rows))
        mb = sum(int(KS.ref_code(rows.loc[:C.index[j]], "M") != int(C.iloc[j])) for j in range(max(0, len(C) - 1)))
        return t, {"rows": int(len(rows)), "bad": bad, "months": int(max(0, len(C) - 1)), "month_bad": int(mb)}
    except Exception as ex:                                                  # noqa: BLE001
        return t, repr(ex)


LABEL_SRC_FILES = ("qbreak/kline_series.py", "qbreak/calendar_jp.py", "qbreak/mtf.py")


def label_consts() -> str:
    """标签表用到的登记常数的值（标签缓存的钥匙用：只改常数、不改代码时缓存也要作废）。"""
    return repr((N_MONTHS, N_SENS, RECENT, LABEL_FROM, TAB_COLS, VARIANTS, CHECK_ROWS, SEED, DEPTH_BINS, KS.TIE_EPS, KS.NEED))


def _label_key(raw_fp: str) -> str:
    """标签缓存的钥匙：kline_series / calendar_jp / mtf 的文件 sha1 + 面板标签代码（kline_src_sha）+ 本文件标签代码的 sha1
    + 标签用到的登记常数的值（label_consts）+ 输入指纹。"""
    src = b"".join((ROOT / f).read_bytes() for f in LABEL_SRC_FILES)
    mine = "".join(inspect.getsource(f) for f in (label_rows, completed_up, prior_month_fragile, ticker_table, sample_check, nd_diff,
                                                  _label_job)).encode("utf-8")
    return (hashlib.sha1(src).hexdigest() + ":" + kline_src_sha() + ":" + hashlib.sha1(mine).hexdigest() + ":"
            + hashlib.sha1(label_consts().encode("utf-8")).hexdigest() + ":" + raw_fp)


def raw_fingerprint(raw: dict, ends: dict) -> str:
    items = []
    for src in sorted(raw):
        for t in sorted(raw[src]):
            df = raw[src][t]
            c = pd.to_numeric(df["Close"], errors="coerce").to_numpy(float)
            v = pd.to_numeric(df["Volume"], errors="coerce").to_numpy(float) if "Volume" in df.columns else np.zeros(len(df))
            items.append((src, t, int(len(df)), str(df.index[0]) if len(df) else None, str(df.index[-1]) if len(df) else None,
                          round(float(np.nansum(c)), 4), round(float(np.nansum(v)), 1), str(ends[src][t])))
    return data_fp(items)


def build_labels(raw: dict, ends: dict, say=print, workers: int = 4) -> tuple[dict, dict, dict]:
    """全部票的标签表（并行；var/cache 有同一份就读缓存）→ (LAB {src: {票: 表}}, STATS {src: 累加的回退 / fragile 个数}, INFO {src: {票: 行数等}})。"""
    from qbreak import paths
    key = _label_key(raw_fingerprint(raw, ends))
    cp = paths.sub("cache") / LABEL_CACHE
    if cp.exists():
        with open(cp, "rb") as f:
            z = pickle.load(f)
        if z.get("key") != key:
            raise SystemExit(f"标签缓存 var/cache/{LABEL_CACHE} 和现在的代码 / 输入不一致 → 删掉它再跑（不改规则）")
        say("标签：用缓存（同一份代码、同一份输入）")
        return z["LAB"], z["STATS"], z["INFO"]
    t0 = time.time()
    items = [(src, t, raw[src][t], ends[src][t]) for src in sorted(raw) for t in sorted(raw[src])]
    LAB: dict = {s: {} for s in raw}
    STATS: dict = {s: {} for s in raw}
    INFO: dict = {s: {} for s in raw}
    bad = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for src, t, tab, st, info in ex.map(_label_job, items, chunksize=8):
            if isinstance(tab, str):
                bad.append((src, t, tab))
                continue
            LAB[src][t] = tab
            INFO[src][t] = info
            for k, v in st.items():
                STATS[src][k] = STATS[src].get(k, 0) + int(v)
    if bad:
        raise SystemExit(f"{len(bad)} 只票算不出标签（例：{bad[:2]}）→ 停")
    with open(cp, "wb") as f:
        pickle.dump({"key": key, "LAB": LAB, "STATS": STATS, "INFO": INFO}, f)
    say(f"标签：{sum(len(v) for v in LAB.values())} 只票；{time.time() - t0:.0f}s（存 var/cache/{LABEL_CACHE}）")
    return LAB, STATS, INFO


def exh_tickers(yahoo_names: list[str]) -> list[str]:
    """逐日穷举的 20 只：登记的 7 只 + 种子 SEED 从 Yahoo 标签票（排序后，去掉那 7 只）里随机抽 13 只。"""
    pool = sorted(t for t in set(yahoo_names) if t not in EXH_FIXED)
    rng = np.random.default_rng(SEED)
    pick = sorted(pool[i] for i in rng.choice(len(pool), size=min(EXH_RANDOM, len(pool)), replace=False))
    return [*EXH_FIXED, *pick]


def read_cache_direct(t: str, years: int | None = None) -> pd.DataFrame | None:
    """只读：直接读 var/cache/{t}_{years}y.csv（或 .parquet），再过一遍 qbreak.data.validate_ohlcv（同 leap_data.ohlcv 的 DataConfig）。
    不看 meta（有效期、价格调整口径 ADJ_VERSION）、不联网、不写缓存。没有文件或读不出 → None。"""
    import leap_data as LD
    from qbreak import data as QD
    from qbreak.config import DataConfig
    years = int(years or LD.YEARS)
    base = QD._cache_path(t, years)
    for fp in (base.with_suffix(".csv"), base.with_suffix(".parquet")):
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(fp) if fp.suffix == ".parquet" else pd.read_csv(fp, index_col=0, parse_dates=True)
            df.index = pd.DatetimeIndex(df.index)
            cfg = DataConfig(provider="yfinance", years=years, allow_synthetic=False, cache_ttl_hours=1e9, min_bars=60).validate()
            return QD.validate_ohlcv(t, df, cfg)
        except Exception:                                                    # noqa: BLE001
            return None
    return None


def exh_raw(t: str, raw_yahoo: dict) -> tuple[pd.DataFrame | None, str]:
    """逐日穷举一只票的行情 → (行情, 来源)：标签输入里有 →「labels」；否则 leap_data.ohlcv（冻结缓存）→「leap_data」；
    还是没有 → read_cache_direct →「csv」。固定的 9301.T / 9046.T 不在任何样本里（不在今天的日経225、也不在 zx_names），它们的 27y 缓存
    是 2026-09-27 取的、meta 没有 "adj": 2：qbreak.data._read_cache 当作旧口径要重新下载，冻结后就被跳过。逐日穷举比的是同一份行情上
    快速算法与原函数，和复权口径无关 → 直接读文件就够；这些票不进 raw / LAB → DATA_FP 不受影响。都没有 → (None, "missing")。"""
    import leap_data as LD
    df = raw_yahoo.get(t)
    if df is not None:
        return df, "labels"
    try:
        df = LD.ohlcv([t]).get(t)
    except Exception:                                                        # noqa: BLE001  只有这一只、又载入不了 → load_universe 抛错
        df = None
    if df is not None:
        return df, "leap_data"
    df = read_cache_direct(t)
    return (df, "csv") if df is not None else (None, "missing")


def label_check_stop(lc: dict) -> str | None:
    """label_check 的结果 → 要停的原因（缺票和真正的不一致分开写）；都没有 → None。"""
    why = []
    miss = (lc.get("exhaustive") or {}).get("missing") or []
    if miss:
        why.append(f"逐日穷举的票载入不了：{miss}（缺票，不是标签不一致；查缓存文件）")
    ex_bad, s_bad = int((lc.get("exhaustive") or {}).get("bad") or 0), int(lc.get("sample_bad") or 0)
    if ex_bad or s_bad:
        why.append(f"标签核对有不一致（逐日穷举 {ex_bad}、抽样 {s_bad}；修代码作为运行前修正）")
    return "；".join(why) + " → 停" if why else None


def label_check(raw: dict, ends: dict, INFO: dict, STATS: dict, say=print, workers: int = 4) -> dict:
    """十-1：逐日穷举 20 只票 + 全部票随机 5 行 × 3 个周期 + 已完成月标签；回退 / fragile 个数。任何不一致或缺票 → ok = False
    （原因用 label_check_stop 分开写）。逐日穷举的行情来源见 exh_raw（记在 exhaustive.source）。"""
    t0 = time.time()
    ticks = exh_tickers(list(raw["yahoo"]))
    end_max = max(DATA_RANGE[s][1] for s in SEGS)
    items = []
    missing = []
    source = {}
    for t in ticks:
        df, source[t] = exh_raw(t, raw["yahoo"])
        if df is None:
            missing.append(t)
            continue
        items.append((t, df, ends["yahoo"].get(t, end_max)))
    exh, bad = {}, []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for t, r in ex.map(_exh_job, items, chunksize=1):
            if isinstance(r, str):
                bad.append((t, r))
            else:
                exh[t] = r
    if bad:
        raise SystemExit(f"逐日穷举算不出（例：{bad[:2]}）→ 停")
    ex_bad = sum(sum(r["bad"].values()) + r["month_bad"] for r in exh.values())
    samp = {}
    for src in INFO:
        c = {"tickers": 0, "rows": 0, "bad": 0, "month": 0, "month_bad": 0}
        for info in INFO[src].values():
            ch = info.get("check") or {}
            c["tickers"] += 1
            for k in ("rows", "bad", "month", "month_bad"):
                c[k] += int(ch.get(k, 0))
        samp[src] = c
    s_bad = sum(c["bad"] + c["month_bad"] for c in samp.values())
    out = {"exhaustive": {"tickers": list(exh), "missing": missing, "source": source, "rows": int(sum(r["rows"] for r in exh.values())),
                          "checks": int(sum(r["rows"] for r in exh.values()) * 3), "months": int(sum(r["months"] for r in exh.values())),
                          "bad": int(ex_bad), "per": exh},
           "sample": samp, "sample_bad": int(s_bad), "fallback": STATS, "ok": bool(ex_bad == 0 and s_bad == 0 and not missing),
           "seconds": round(time.time() - t0)}
    direct = [t for t, v in source.items() if v == "csv"]
    say(f"标签核对：逐日穷举 {len(exh)} 只 {out['exhaustive']['checks']:,} 次不一致 {ex_bad}；抽样 "
        + "、".join(f"{s} {c['rows']:,} 次不一致 {c['bad']}（月 {c['month']} / {c['month_bad']}）" for s, c in samp.items())
        + (f"；直接读缓存文件 {direct}" if direct else "") + (f"；★ 缺票 {missing}" if missing else ""))
    return out


# ───────────────────────── 数据（A 部分的面板） ─────────────────────────
def _jpx_mask(days: pd.DatetimeIndex) -> np.ndarray:
    return np.array([CAL.is_trading_day(d.date()) for d in pd.DatetimeIndex(days)], bool)


def seg_from_panel(tag: str, P: dict, days, names, mem=None) -> dict:
    """面板 → 一段：限在数据范围内、去掉非 JPX 交易日（市场日历）；成员缺 → 全 True。"""
    days = pd.DatetimeIndex(days)
    lo, hi = DATA_RANGE[tag]
    keep = np.asarray((days >= pd.Timestamp(lo)) & (days <= pd.Timestamp(hi)))
    jpx = _jpx_mask(days)
    C = np.asarray(P["C"], float)
    k = keep & jpx
    seg = {"tag": tag, "src": SRC[tag], "names": [str(t) for t in names], "days": days[k],
           "O": np.asarray(P["O"], float)[k], "C": C[k],
           "mem": np.ones((int(k.sum()), C.shape[1]), bool) if mem is None else np.asarray(mem, bool)[k],
           "drop_days": int((keep & ~jpx).sum()), "drop_rows": int(np.isfinite(C[keep & ~jpx]).sum())}
    return seg


def load_a_panels(say=print) -> tuple[dict, dict, dict]:
    """→ (segs, raw, ends)。segs = 六段（Z / E / J / J2 / W / JY）的市场日历与 O / C / 成员；raw = 标签输入（Yahoo 27y 缓存原样、J-Quants 宽表的列）；
    ends = 每只票标签算到哪一天（用到它的各段里最晚的数据最后一天）。"""
    import candle_data as CD
    import leap_confirm as LF
    import leap_data as LD
    import loop10_common as C10
    from qbreak.config import universe
    memo_leap_data()
    t0 = time.time()
    n225 = list(universe("JP", "broad"))
    zx = C10.zx_names()
    segs: dict = {}
    for s in ("Z", "E"):
        ctx = LF.context(s)
        segs[s] = seg_from_panel(s, ctx["P"], ctx["days"], ctx["names"])
        say(f"{s}：{len(segs[s]['names'])} 只 × {len(segs[s]['days'])} 天；{time.time() - t0:.0f}s")
    for s, names in (("W", zx), ("JY", n225)):
        P, days, nm = LF.yf_panel(names, *DATA_RANGE[s])
        segs[s] = seg_from_panel(s, P, days, nm)
        say(f"{s}：{len(segs[s]['names'])} 只 × {len(segs[s]['days'])} 天；{time.time() - t0:.0f}s")
    D = CD.load()
    names = [str(x) for x in D["names"]]
    jcols = {}
    for s, u in (("J", "U0"), ("J2", "U2")):
        cols = [j for j in range(len(names)) if D["mem"][u][:, j].any()]
        jcols[s] = cols
        mem = D["mem"]["U2"][:, cols] if s == "J2" else None
        segs[s] = seg_from_panel(s, {k: D["P"][k][:, cols] for k in ("O", "C")}, D["days"], [names[j] for j in cols], mem)
        say(f"{s}：{len(segs[s]['names'])} 只 × {len(segs[s]['days'])} 天；{time.time() - t0:.0f}s")
    raw: dict = {"yahoo": {}, "jq": {}}
    ends: dict = {"yahoo": {}, "jq": {}}
    # Yahoo 标签表 = 今天的日経225 ∪ zx_names（有 27y 缓存的；B 部分的 Zx 池子也查它，含 2005-09 之前就退市、不在 W 面板里的票）
    ynames = sorted(set(n225) | set(zx) | set(segs["Z"]["names"]) | set(segs["E"]["names"]) | set(segs["W"]["names"]) | set(segs["JY"]["names"]))
    data = LD.ohlcv(ynames)
    for t in ynames:
        if t in data:
            raw["yahoo"][t] = data[t]
            use = [s for s in ("Z", "E", "W", "JY") if t in segs[s]["names"]] or (["W"] if t in set(zx) else ["JY"])
            ends["yahoo"][t] = max(DATA_RANGE[s][1] for s in use)
    jdays = pd.DatetimeIndex(D["days"])
    for j in sorted(set(jcols["J"]) | set(jcols["J2"])):
        ok = np.isfinite(D["P"]["C"][:, j])
        raw["jq"][names[j]] = pd.DataFrame({k: D["P"][k[0]][ok, j] for k in ("Open", "High", "Low", "Close", "Volume")}, index=jdays[ok])
        ends["jq"][names[j]] = DATA_RANGE["J"][1]
    say(f"标签输入：Yahoo {len(raw['yahoo'])} 只、J-Quants {len(raw['jq'])} 列；{time.time() - t0:.0f}s")
    return segs, raw, ends


def panel_check(segs: dict, LAB: dict) -> dict:
    """先决核对：标签输入与收益面板重叠日的 Close 最大相对差（≤ 1e−12）；数据范围内有标签行却不在市场日历里的行数（预期 0）。"""
    out = {}
    for s, seg in segs.items():
        mx, outside, over = 0.0, 0, 0
        lo, hi = (pd.Timestamp(x) for x in DATA_RANGE[s])
        for j, t in enumerate(seg["names"]):
            tab = LAB[SRC[s]].get(t)
            if tab is None:
                continue
            ix = tab.index
            inr = (ix >= lo) & (ix <= hi)
            pos = seg["days"].get_indexer(ix[inr])
            outside += int((pos < 0).sum())
            ok = pos >= 0
            a = tab["C"].to_numpy(float)[inr][ok]
            b = seg["C"][pos[ok], j]
            f = np.isfinite(b)
            over += int(f.sum())
            if f.any():
                mx = max(mx, float(np.max(np.abs(a[f] / b[f] - 1))))
        out[s] = {"max_rel": mx, "rows": over, "outside": outside}
    out["ok"] = all(v["max_rel"] <= 1e-12 for v in out.values() if isinstance(v, dict))
    return out


# ───────────────────────── 矩阵、状态、事件（纯函数，有测试） ─────────────────────────
def to_matrix(seg: dict, tabs: dict) -> dict:
    """一段的标签矩阵（市场日 × 票）：TAB_COLS（int8，没有行 → NA）、ROW（这一天这只票有标签行）、FR、FRM、DEP、STK。"""
    days, names = seg["days"], seg["names"]
    T, N = len(days), len(names)
    m = {k: np.full((T, N), NA, np.int8) for k in TAB_COLS}
    m["ROW"] = np.zeros((T, N), bool)
    m["FR"] = np.zeros((T, N), bool)
    m["FRM"] = np.zeros((T, N), bool)
    m["DEP"] = np.full((T, N), np.nan, np.float32)
    m["STK"] = np.full((T, N), -1, np.int16)
    for j, t in enumerate(names):
        tab = tabs.get(t)
        if tab is None or not len(tab):
            continue
        pos = days.get_indexer(tab.index)
        ok = pos >= 0
        p = pos[ok]
        for k in TAB_COLS:
            m[k][p, j] = tab[k].to_numpy(np.int8)[ok]
        m["ROW"][p, j] = True
        m["FR"][p, j] = tab["FR"].to_numpy(bool)[ok]
        m["FRM"][p, j] = tab["FRM"].to_numpy(bool)[ok]
        m["DEP"][p, j] = tab["DEP"].to_numpy(np.float32)[ok]
        m["STK"][p, j] = tab["STK"].to_numpy(np.int16)[ok]
    return m


def states(m: dict, variant: str = "main") -> dict[str, np.ndarray]:
    """各组状态（布尔，形状同输入）：MUDW / MUD / MUW / MUN / MUA / 细分 / MNDW / MND / MNW。都要求 D、W 已知；MU* 要求月线条件（MUB 或敏感度口径）为真；
    MN* 要求 M 已知且 ∈ {0, −1}，并且月线条件已知（二：MUB 未知的行不进任何状态；和事件规则 3 的 known 同一口径）。
    variant 见 VARIANTS（CMP 另把 W 换成已完成周K）。"""
    uk, wk = VARIANTS[variant]
    D, Wv, M, U = (np.asarray(m[k]) for k in ("D", wk, "M", uk))
    dw = (D != NA) & (Wv != NA)
    mu = dw & (U == 1)
    dn_d, dn_w = D == -1, Wv == -1
    ok_d, ok_w = dw & (D >= 0), dw & (Wv >= 0)
    out = {"MUDW": mu & dn_d & dn_w, "MUD": mu & dn_d & ok_w, "MUW": mu & dn_w & ok_d, "MUN": mu & ok_d & ok_w}
    out["MUA"] = out["MUN"] & (D == 1) & (Wv == 1) & (M == 1)
    out["MUD-u"], out["MUD-f"] = out["MUD"] & (Wv == 1), out["MUD"] & (Wv == 0)
    out["MUW-u"], out["MUW-f"] = out["MUW"] & (D == 1), out["MUW"] & (D == 0)
    mn = dw & (M != NA) & (M <= 0) & (U != NA)
    out["MNDW"], out["MND"], out["MNW"] = mn & dn_d & dn_w, mn & dn_d & ok_w, mn & dn_w & ok_d
    return out


def known(m: dict, variant: str = "main") -> np.ndarray:
    """事件规则 3 的「都已知」：D、W（CMP = 已完成周K）、M、月线条件（MUB 或敏感度口径）。"""
    uk, wk = VARIANTS[variant]
    return (np.asarray(m["D"]) != NA) & (np.asarray(m[wk]) != NA) & (np.asarray(m["M"]) != NA) & (np.asarray(m[uk]) != NA)


def _entry_1d(s: np.ndarray, k: np.ndarray, cool: int) -> np.ndarray:
    n = len(s)
    out = np.zeros(n, bool)
    if n <= cool:
        return out
    cs = np.r_[0, np.cumsum(s.astype(np.int64))]
    cu = np.r_[0, np.cumsum((~k).astype(np.int64))]
    i = np.arange(cool, n)
    out[cool:] = s[cool:] & ((cs[i] - cs[i - cool]) == 0) & ((cu[i + 1] - cu[i - cool]) == 0)
    return out


def entry_events(state, kn, row=None, cool: int = COOL) -> np.ndarray:
    """进入事件（在每只票自己的行上）：state 为真、前 cool 行 state 都为假、这 cool + 1 行都已知。
    1-D = 一只票的行；2-D = 市场日 × 票，row = 那天这只票有没有行（没有行的日子跳过，不算一行）。"""
    s, k = np.asarray(state, bool), np.asarray(kn, bool)
    if s.ndim == 1:
        if row is None:
            return _entry_1d(s, k, cool)
        r = np.flatnonzero(np.asarray(row, bool))
        out = np.zeros(len(s), bool)
        out[r] = _entry_1d(s[r], k[r], cool)
        return out
    out = np.zeros(s.shape, bool)
    rw = np.ones(s.shape, bool) if row is None else np.asarray(row, bool)
    for j in range(s.shape[1]):
        r = np.flatnonzero(rw[:, j])
        if len(r) > cool:
            out[r, j] = _entry_1d(s[r, j], k[r, j], cool)
    return out


def window_member(ev: np.ndarray, days: pd.DatetimeIndex, a, b, mem=None) -> np.ndarray:
    """事件日在窗口 [a, b]（两端含）且那天是成员（J2）。"""
    d = pd.DatetimeIndex(days)
    inwin = np.asarray((d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b)))
    out = np.asarray(ev, bool) & (inwin[:, None] if np.ndim(ev) == 2 else inwin)
    return out if mem is None else out & np.asarray(mem, bool)


def end_events(ev, m: dict, row=None, within: int = END_WITHIN) -> tuple[np.ndarray, dict]:
    """结束事件：每个事件之后 within 行内（这只票自己的行）第一个 D = +1 ∧ W ∈ {0, +1} ∧ MUB 为真的行；先出现「MUB 已知且为假」→ 月线转弱（只数）；
    都没有 → 没有。同一天只算一个。返回（结束事件布尔矩阵, {events, end, weak, none}）。"""
    e = np.asarray(ev, bool)
    one = e.ndim == 1
    E = e[:, None] if one else e
    D = np.asarray(m["D"]).reshape(E.shape)
    Wv = np.asarray(m["W"]).reshape(E.shape)
    U = np.asarray(m["MUB"]).reshape(E.shape)
    rw = np.ones(E.shape, bool) if row is None else np.asarray(row, bool).reshape(E.shape)
    good = (D == 1) & (Wv != NA) & (Wv >= 0) & (U == 1)
    weak = U == 0
    out = np.zeros(E.shape, bool)
    cnt = {"events": 0, "end": 0, "weak": 0, "none": 0}
    for j in np.flatnonzero(E.any(axis=0)):
        r = np.flatnonzero(rw[:, j])
        er = E[r, j]
        g, w = good[r, j], weak[r, j]
        for p in np.flatnonzero(er):
            cnt["events"] += 1
            sl = slice(p + 1, p + 1 + within)
            gi = np.flatnonzero(g[sl])
            wi = np.flatnonzero(w[sl])
            if len(gi) and (not len(wi) or gi[0] < wi[0]):
                out[r[p + 1 + gi[0]], j] = True
                cnt["end"] += 1
            elif len(wi):
                cnt["weak"] += 1
            else:
                cnt["none"] += 1
    return (out[:, 0] if one else out), cnt


def pick_days(days: pd.DatetimeIndex, a, b, every: int = EVERY) -> np.ndarray:
    """状态日：从窗口第一天起每 every 个市场交易日取一天 → 布尔（对齐 days）。"""
    d = pd.DatetimeIndex(days)
    idx = np.flatnonzero(np.asarray((d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b))))
    out = np.zeros(len(d), bool)
    out[idx[::every]] = True
    return out


def month_level(M, U) -> np.ndarray:
    """月 4 档：0 MUB / 1 月K 上升但不满 3 个月 / 2 横着走 / 3 往下走；−1 = 未知（M 是 NA，或 MUB 未知：二「未知的行不进任何状态」）。"""
    M, U = np.asarray(M), np.asarray(U)
    out = np.full(M.shape, -1, np.int8)
    uk = U != NA
    out[U == 1] = 0
    out[(M == 1) & (U == 0)] = 1
    out[(M == 0) & uk] = 2
    out[(M == -1) & uk] = 3
    return out


def cell_codes(m: dict) -> np.ndarray:
    """36 格的格号（月 4 档 × 日 3 档 × 周 3 档 = 0〜35；未知 → −1）。"""
    ml = month_level(m["M"], m["MUB"])
    D, Wv = np.asarray(m["D"]), np.asarray(m["W"])
    ok = (ml >= 0) & (D != NA) & (Wv != NA)
    code = ml.astype(np.int16) * 9 + (1 - D.astype(np.int16)) * 3 + (1 - Wv.astype(np.int16))
    return np.where(ok, code, -1).astype(np.int16)


def cell_name(code: int) -> str:
    ml, rest = divmod(int(code), 9)
    d, w = divmod(rest, 3)
    return f"月 {MLEVELS[ml]} / 日 {LEVEL3[1 - d]} / 周 {LEVEL3[1 - w]}"


def sub_events(EV: dict, m: dict) -> dict:
    """细分事件（只描述）= 母组的进入事件按事件日的周K（MUD）/ 日K（MUW）拆开（SUB_OF）：MUD-u = MUD 事件 ∧ 事件日 W = +1 等。
    不是独立状态的进入事件（回调中途周K / 日K 换档不算新事件）→ 细分加起来正好 = 母组。"""
    return {k: np.asarray(EV[p], bool) & (np.asarray(m[col]) == v) for k, (p, col, v) in SUB_OF.items()}


def seg_events(seg: dict, m: dict) -> tuple[dict, dict]:
    """一段的全部事件（布尔矩阵，已限窗口 + 成员）：主口径 8 组（IDS_A、DESC）+ 细分 4（sub_events：母组事件按事件日拆开）、
    敏感度 4 × 3（键 "MUDW@N0" 等）、结束事件 3；另返回结束事件的个数。"""
    a, b = WINDOWS[seg["tag"]]
    if int((pd.DatetimeIndex(seg["days"]) < pd.Timestamp(a)).sum()) <= COOL:
        raise ValueError("窗口开始之前的市场日不够 COOL 行（冷却期会落到这一段数据之外）")
    EV, extra = {}, {}
    for v in VARIANTS:
        st = states(m, v)
        kn = known(m, v)
        for k in ((*IDS_A, *DESC) if v == "main" else IDS_A):
            EV[k if v == "main" else f"{k}@{v}"] = window_member(entry_events(st[k], kn, m["ROW"]), seg["days"], a, b, seg["mem"])
    EV.update(sub_events(EV, m))
    for k in IDS_A:
        EV[END_IDS[k]], extra[k] = end_events(EV[k], m, m["ROW"])
    return EV, extra


def shift_up(X: np.ndarray, k: int) -> np.ndarray:
    """第 e 行 = 原来第 e + k 行（后面补 NaN）。"""
    X = np.asarray(X, float)
    out = np.full(X.shape, np.nan)
    if k < X.shape[0]:
        out[:X.shape[0] - k] = X[k:]
    return out


def px_ok(seg: dict, h: int) -> np.ndarray:
    """只看有没有价格：O[e+1] 与 C[e+h] 都有值（登记前个数用；不算收益）。"""
    return np.isfinite(shift_up(seg["O"], 1)) & np.isfinite(shift_up(seg["C"], h))


def breadth_days(m: dict, mem) -> np.ndarray:
    """每个市场日：同段成员里 D 已知的票中 D = −1 的比例 ≥ BREADTH_CUT →「大盘一起跌」。"""
    D = np.asarray(m["D"])
    k = np.asarray(mem, bool) & (D != NA)
    n = k.sum(axis=1)
    dn = (k & (D == -1)).sum(axis=1)
    return (n > 0) & (dn >= BREADTH_CUT * np.maximum(n, 1))


def depth_bin(dep) -> np.ndarray:
    """跌幅三档：0 = < 5%、1 = 5〜10%、2 = ≥ 10%；NaN → −1。"""
    x = np.asarray(dep, float)
    out = np.full(x.shape, -1, np.int8)
    f = np.isfinite(x)
    out[f & (x < DEPTH_BINS[0])] = 0
    out[f & (x >= DEPTH_BINS[0]) & (x < DEPTH_BINS[1])] = 1
    out[f & (x >= DEPTH_BINS[1])] = 2
    return out


# ───────────────────────── 指标（--run 才用；纯函数，有测试） ─────────────────────────
def fwd_tables(seg: dict, mub, rt: float, horizons=HORIZONS) -> dict:
    """每个 h：r（%，T × N）、mk（ALL = 同日成员里 MUB 已知的等权平均，含自己；MUB 未知的成员不进任何基准，见二）、
    pk（同日 MUB 为真的成员等权平均；r 有值的不到 MIN_PEERS → NaN）、pc（同伴数）、
    pwin / ploss（同伴里 net > 0 / r < 0 的比例；同伴不到 MIN_PEERS → NaN）。mub = 主口径 MUB（N = 3）。"""
    import madev_event as ME
    R = ME.fwd_returns({"O": seg["O"], "C": seg["C"]}, horizons)
    mem = np.asarray(seg["mem"], bool)
    mub = np.asarray(mub)
    am = mem & (mub != NA)
    pm = mem & (mub == 1)
    out = {}
    for h in horizons:
        r = R[h] * 100
        fin = np.isfinite(r)
        mk = ME.market_mean(r, am)
        pk = ME.market_mean(r, pm)
        pc = (pm & fin).sum(axis=1)
        okp = pc >= MIN_PEERS
        den = np.maximum(pc, 1)
        with np.errstate(invalid="ignore"):
            pwin = np.where(okp, (pm & fin & ((r - rt) > 0)).sum(axis=1) / den, np.nan)
            ploss = np.where(okp, (pm & fin & (r < 0)).sum(axis=1) / den, np.nan)
        out[h] = {"r": r, "mk": mk, "pk": np.where(okp, pk, np.nan), "pc": pc, "pwin": pwin, "ploss": ploss}
    return out


def event_rows(tag: str, key: str, ev: np.ndarray, F: dict, seg: dict, m: dict, rt: float, extra: dict | None = None) -> pd.DataFrame:
    """事件表（每行一个事件）：seg / state / j / e / date / month / quarter / year / fr / frm / breadth / depth + 每个 h 的 r / net / x / y / lb / ls。"""
    e, j = np.nonzero(np.asarray(ev, bool))
    days = pd.DatetimeIndex(seg["days"])
    d = days[e]
    out = pd.DataFrame({"seg": tag, "state": key, "j": j, "e": e, "date": d, "month": d.strftime("%Y-%m"),
                        "quarter": [f"{x.year}-Q{(x.month - 1) // 3 + 1}" for x in d], "year": d.year,
                        "fr": np.asarray(m["FR"])[e, j], "frm": np.asarray(m["FRM"])[e, j], "dep": depth_bin(np.asarray(m["DEP"])[e, j])})
    if extra and "breadth" in extra:
        out["breadth"] = np.asarray(extra["breadth"])[e]
    for h, f in F.items():
        r = f["r"][e, j]
        net = r - rt
        out[f"r{h}"] = r
        out[f"net{h}"] = net
        out[f"x{h}"] = r - f["mk"][e]
        out[f"y{h}"] = r - f["pk"][e]
        with np.errstate(invalid="ignore"):
            out[f"lb{h}"] = np.where(np.isfinite(r), (net > 0).astype(float), np.nan) - f["pwin"][e]
            out[f"ls{h}"] = np.where(np.isfinite(r), (r < 0).astype(float), np.nan) - f["ploss"][e]
    return out


def boot_joint(vals: dict, months, n: int = BOOT_N, seed: int = SEED, levels: dict | None = None) -> dict:
    """按月聚类的自助法（整月有放回、按事件数加权；每次调用用 seed 重新播种）：全部变量共用同一组抽到的月份。
    vals = {名字: 每个事件的值（NaN = 这个变量没有）}；levels = {"95": (2.5, 97.5), "98.33": Q98}。返回 {名字: {水平: (下限, 上限)}}。
    单个变量、没有 NaN 时与 madev_event.boot_mean 同一个抽法（95% 区间相同）。"""
    levels = levels or {"95": Q95, "98.33": Q98}
    months = np.asarray(months).astype(str)
    V = {k: np.asarray(v, float) for k, v in vals.items()}
    anyf = np.zeros(len(months), bool)
    for v in V.values():
        anyf |= np.isfinite(v)
    nan2 = {lv: (np.nan, np.nan) for lv in levels}
    u, inv = np.unique(months[anyf], return_inverse=True)
    if len(u) == 0:
        return {k: dict(nan2) for k in V}
    rng = np.random.default_rng(seed)
    J = np.empty((n, len(u)), np.int64)
    for i in range(n):
        J[i] = rng.integers(0, len(u), len(u))
    out = {}
    for k, v in V.items():
        x = v[anyf]
        f = np.isfinite(x)
        if f.sum() < 2:
            out[k] = dict(nan2)
            continue
        s = np.bincount(inv[f], weights=x[f], minlength=len(u))
        c = np.bincount(inv[f], minlength=len(u)).astype(float)
        S, Cn = s[J].sum(axis=1), c[J].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            st = np.where(Cn > 0, S / np.where(Cn > 0, Cn, 1), np.nan)
        out[k] = {lv: (float(np.nanpercentile(st, q[0])), float(np.nanpercentile(st, q[1]))) for lv, q in levels.items()}
    return out


def _mean(x) -> float | None:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x.mean()) if len(x) else None


def _rate(cond, base) -> float | None:
    b = np.asarray(base, bool)
    return float(np.asarray(cond, bool)[b].mean() * 100) if b.any() else None


def summarize(T: pd.DataFrame, h: int = H, ci: bool = True, cluster: str = "month", levels: dict | None = None) -> dict:
    """一组事件在 h 下的买点 / 卖点指标（见文件开头五）；ci → 按 cluster（month / quarter）聚类的 x̄ / ȳ / 成功率 / lift 区间（共用抽样）。"""
    if T is None or not len(T):
        return {"n": 0}
    r, net, x, y = (T[f"{k}{h}"].to_numpy(float) for k in ("r", "net", "x", "y"))
    lb, ls = T[f"lb{h}"].to_numpy(float), T[f"ls{h}"].to_numpy(float)
    f = np.isfinite(net)
    if not f.any():
        return {"n": 0}
    w, lo_ = net[f & (net > 0)], net[f & (net <= 0)]
    fx = np.isfinite(x)
    out = {"n": int(f.sum()), "n_x": int(fx.sum()), "n_y": int(np.isfinite(y).sum()),
           "months": int(T.loc[fx, "month"].nunique()) if fx.any() else 0,
           "win": _rate(net > 0, f), "net_mean": _mean(net), "net_med": float(np.median(net[f])),
           "avg_win": float(w.mean()) if len(w) else None, "avg_loss": float(lo_.mean()) if len(lo_) else None,
           "q05": float(np.percentile(net[f], 5)), "beat": _rate(x > 0, fx), "x_mean": _mean(x), "y_mean": _mean(y),
           "r_mean": _mean(r), "lift_buy": None if _mean(lb) is None else _mean(lb) * 100,
           "right_r": _rate(r < 0, np.isfinite(r)), "right_x": _rate(x < 0, fx),
           "lift_sell": None if _mean(ls) is None else _mean(ls) * 100}
    out["odds"] = (out["avg_win"] / abs(out["avg_loss"])) if out["avg_win"] is not None and out["avg_loss"] not in (None, 0.0) else None
    out["avoided"] = None if out["r_mean"] is None else -out["r_mean"]
    out["rel"] = None if out["x_mean"] is None else -out["x_mean"]
    if ci:
        winv = np.where(f, (net > 0) * 100.0, np.nan)
        B = boot_joint({"x": x, "y": y, "win": winv, "lift_buy": lb * 100, "net": net}, T[cluster].to_numpy(), levels=levels)
        out["ci"] = {k: {lv: [None if not np.isfinite(a) else a, None if not np.isfinite(b) else b] for lv, (a, b) in v.items()}
                     for k, v in B.items()}
    return out


def verdict_a(pool: dict, per: dict) -> str:
    """A 部分的判定（见文件开头七；纯函数）。pool = {n, months, x_mean, x_lo, x_hi, y_mean, y_lo, y_hi}（98.33% 区间）；
    per = {段: {n, x_mean, y_mean}}（Z / E / J / W / J2）。"""
    def num(v):
        return None if v is None or not np.isfinite(float(v)) else float(v)
    n, mo = int(pool.get("n") or 0), int(pool.get("months") or 0)
    if n < MIN_EV_POOL or mo < MIN_MONTHS:
        return "事件太少"
    xm, xl, xh = num(pool.get("x_mean")), num(pool.get("x_lo")), num(pool.get("x_hi"))
    yl, yh = num(pool.get("y_lo")), num(pool.get("y_hi"))                     # ȳ 的点估计不进判定（只看区间与各段）
    valid = [s for s in SAMPLES if int((per.get(s) or {}).get("n") or 0) >= MIN_EV_SAMPLE]
    full = len(valid) == len(SAMPLES)
    xs = [num(per[s].get("x_mean")) for s in valid]
    ys = [num(per[s].get("y_mean")) for s in valid]
    pos_x = xl is not None and xl > 0
    neg_x = xh is not None and xh < 0
    sig = pos_x or neg_x
    if full and pos_x and xm is not None and xm >= MIN_PP - EPS and yl is not None and yl > 0 \
            and all(v is not None and v > 0 for v in xs) and all(v is not None and v > 0 for v in ys):
        return "买点成立"
    if full and neg_x and xm is not None and xm <= -MIN_PP + EPS and yh is not None and yh < 0 \
            and all(v is not None and v < 0 for v in xs) and all(v is not None and v < 0 for v in ys):
        return "卖点成立（拿着的人卖掉更好）"
    if sig:
        d = 1 if pos_x else -1
        if any(v is not None and v * d < 0 for v in xs):
            return "不成立（有一段相反）"
        if not full:
            return "样本不全（合并显著）"
        if xm is not None and abs(xm) >= MIN_PP - EPS:
            y_sig = (yl is not None and yl > 0) if d > 0 else (yh is not None and yh < 0)
            y_same = all(v is not None and v * d > 0 for v in ys)
            if not (y_sig and y_same):
                return "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）"
    if len(valid) >= MIN_SEG and (all(v is not None and v > 0 for v in xs) or all(v is not None and v < 0 for v in xs)):
        return "方向一致但不够"
    return "没有信息（和平常买差不多）"


def judge_input(pool: dict, per: dict) -> tuple[dict, dict]:
    """summarize 的结果 → verdict_a 的输入（98.33% 区间；另给 95% 区间版只展示）。"""
    def side(s, lv):
        ci = (s.get("ci") or {})
        return {"x_lo": (ci.get("x") or {}).get(lv, [None, None])[0], "x_hi": (ci.get("x") or {}).get(lv, [None, None])[1],
                "y_lo": (ci.get("y") or {}).get(lv, [None, None])[0], "y_hi": (ci.get("y") or {}).get(lv, [None, None])[1]}
    base = {"n": pool.get("n_x", 0), "months": pool.get("months", 0), "x_mean": pool.get("x_mean"), "y_mean": pool.get("y_mean")}
    p98 = {**base, **side(pool, "98.33")}
    p95 = {**base, **side(pool, "95")}
    pr = {s: {"n": (per.get(s) or {}).get("n_x", 0), "x_mean": (per.get(s) or {}).get("x_mean"), "y_mean": (per.get(s) or {}).get("y_mean")}
          for s in SAMPLES}
    return {"p98": p98, "p95": p95}, pr


def say_verdict(k: str, verdict: str, x_mean) -> str:
    """md〇 的一句话 = 登记的结论用语对照 VERDICT_SAY[判定] 填空（见常数旁的说明；纯函数）。没登记的判定 → 判定原文。"""
    tpl = VERDICT_SAY.get(verdict)
    if tpl is None:
        return str(verdict)
    x = None if x_mean is None or not np.isfinite(float(x_mean)) else float(x_mean)
    z = "—" if x is None else f"{abs(x):.2f}"
    hao = "好" if x is not None and x > 0 else ("差" if x is not None and x < 0 else "好 / 差")
    return tpl.format(seen=SEEN.get(k, k), z=z, hao=hao, luehao="略" + hao if hao in ("好", "差") else "略好 / 略差")


# ───────────────────────── 登记前个数（只数个数，不算任何收益） ─────────────────────────
def _vc(x: np.ndarray) -> dict:
    v, c = np.unique(np.asarray(x), return_counts=True)
    return {str(int(a)): int(b) for a, b in zip(v, c)}


def _share(mask, base) -> float | None:
    b = int(np.asarray(base, bool).sum())
    return round(float(np.asarray(mask, bool).sum()) / b * 100, 3) if b else None


def ev_profile(ev: np.ndarray, days: pd.DatetimeIndex) -> dict:
    """事件个数、按年份、不同月份数、事件最多 5 个月的占比。"""
    e, _ = np.nonzero(np.asarray(ev, bool))
    d = pd.DatetimeIndex(days)[e]
    n = int(len(e))
    if not n:
        return {"n": 0, "by_year": {}, "months": 0, "top5_share": None}
    mo = pd.Series(d.strftime("%Y-%m")).value_counts()
    return {"n": n, "by_year": {str(k): int(v) for k, v in pd.Series(d.year).value_counts().sort_index().items()},
            "months": int(len(mo)), "top5_share": round(float(mo.iloc[:5].sum()) / n * 100, 2)}


def counts_seg(seg: dict, m: dict, EV: dict, extra: dict) -> dict:
    """一段的登记前个数（十-2〜4）：数据、标签分布、事件个数、价格有没有、同伴个数、退市缺价、跌幅 / 一起跌、敏感度、结束事件。不算收益。"""
    tag = seg["tag"]
    days = pd.DatetimeIndex(seg["days"])
    a, b = WINDOWS[tag]
    inwin = np.asarray((days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b)))
    mem = np.asarray(seg["mem"], bool)
    has_px = np.isfinite(seg["C"])
    md = mem & has_px & inwin[:, None]                                       # 成员股票日（窗口内、那天有收盘）
    per_day = md.sum(axis=1)[inwin]
    med = float(np.median(per_day)) if len(per_day) else 0.0
    out: dict = {"tickers": len(seg["names"]), "days": int(len(days)), "range": [str(days[0].date()), str(days[-1].date())] if len(days) else None,
                 "window_days": int(inwin.sum()), "member_days": int(md.sum()), "label_rows": int(m["ROW"].sum()),
                 "drop_days": seg.get("drop_days"), "drop_rows": seg.get("drop_rows"),
                 "thin_days": int((per_day < med / 2).sum()), "member_median": med}
    dist = {}
    for k in ("D", "W", "M"):
        v = np.asarray(m[k])[md]
        dist[k] = {"上升": _share(v == 1, np.ones(len(v), bool)), "震荡": _share(v == 0, np.ones(len(v), bool)),
                   "下降": _share(v == -1, np.ones(len(v), bool)), "NA": _share(v == NA, np.ones(len(v), bool))}
    out["dist"] = dist
    out["mub_share"] = {k: {"真": _share(np.asarray(m[c])[md] == 1, np.ones(int(md.sum()), bool)),
                            "NA": _share(np.asarray(m[c])[md] == NA, np.ones(int(md.sum()), bool))}
                        for k, c in (("N0", "MUB0"), ("N3", "MUB"), ("N6", "MUB6"), ("MUC3", "MUC3"), ("CMP", "MUBc"))}
    first = []
    U = np.asarray(m["MUB"])
    for j in range(U.shape[1]):
        k = np.flatnonzero(U[:, j] != NA)
        if len(k):
            first.append(days[k[0]])
    out["mub_first_median"] = str(pd.Series(pd.DatetimeIndex(first)).median().date()) if first else None
    stk = np.asarray(m["STK"])[md & np.asarray(m["ROW"])]
    out["streak"] = {"0": int((stk == 0).sum()), "1": int((stk == 1).sum()), "2": int((stk == 2).sum()), "3": int((stk == 3).sum()),
                     "4-5": int(((stk >= 4) & (stk <= 5)).sum()), "6-11": int(((stk >= 6) & (stk <= 11)).sum()), "≥ 12": int((stk >= 12).sum())}
    st = states(m, "main")
    pick = pick_days(days, a, b)
    pk = md & pick[:, None]                                                  # 状态日（四：每 EVERY 个市场交易日一天）× 成员，和 36 格同一口径
    out["state_days"] = {k: int((st[k] & pk).sum()) for k in GROUPS}
    out["state_days"]["MUB"] = int(((U == 1) & pk).sum())
    out["state_stock_days_all"] = {k: int((st[k] & md).sum()) for k in GROUPS}   # 另报：窗口内全部日子的状态股票日数（不是状态日）
    out["state_stock_days_all"]["MUB"] = int(((U == 1) & md).sum())
    cc = cell_codes(m)[pick][md[pick]]
    out["cells"] = {cell_name(c): int((cc == c).sum()) for c in range(36)}
    out["cells_unknown"] = int((cc < 0).sum())
    bre = breadth_days(m, mem)
    ok = {h: px_ok(seg, h) for h in HORIZONS}
    pm = mem & (U == 1)
    peers20 = (pm & ok[H]).sum(axis=1)
    out["peer_short_days"] = int(((peers20 < MIN_PEERS) & inwin).sum())
    lastc = np.full(len(seg["names"]), -1)
    for j in range(len(seg["names"])):
        k = np.flatnonzero(has_px[:, j])
        if len(k):
            lastc[j] = k[-1]
    ev_out = {}
    for key, ev in EV.items():
        r = ev_profile(ev, days)
        e, j = np.nonzero(ev)
        r["px"] = {str(h): int(ok[h][e, j].sum()) for h in HORIZONS}
        r["y_ok"] = int((ok[H][e, j] & (peers20[e] >= MIN_PEERS)).sum())
        if tag == "J2":
            r["delist_miss"] = {str(h): int((~ok[h][e, j] & (e + h < len(days)) & (lastc[j] < e + h)).sum()) for h in HORIZONS}
        r["breadth"] = int(bre[e].sum())
        db = depth_bin(np.asarray(m["DEP"])[e, j])
        r["depth"] = {DEPTH_NAMES[i]: int((db == i).sum()) for i in range(3)}
        fr, frm = np.asarray(m["FR"])[e, j], np.asarray(m["FRM"])[e, j]
        r["fragile"] = int(fr.sum())                                         # 事件日这一行自己的 D / W / M 近平局
        r["fragile_prev_month"] = int(frm.sum())                             # MUB 用到的前 3 根月末行近平局
        r["fragile_any"] = int((fr | frm).sum())                             # 「去掉 fragile 事件」去掉的个数
        ev_out[key] = r
    out["events"] = ev_out
    out["end"] = extra
    return out


def feasibility(C: dict) -> dict:
    """可行性预检：每个状态（h = 20 有价格的事件）五段是否都 ≥ 30（FULL 能不能成立）、合并是否 ≥ 100 个、≥ 24 个月（月份按全部事件数）。"""
    out = {}
    for k in IDS_A:
        per = {s: C[s]["events"][k]["px"][str(H)] for s in SAMPLES if s in C}
        pool_n = sum(C[s]["events"][k]["px"][str(H)] for s in POOL if s in C)
        out[k] = {"per": per, "full_possible": all(v >= MIN_EV_SAMPLE for v in per.values()) and len(per) == len(SAMPLES),
                  "pool_n": int(pool_n), "pool_ok": bool(pool_n >= MIN_EV_POOL)}
    return out


def pool_months(EVS: dict, segs: dict, key: str, h: int = H) -> int:
    """合并（POOL）里 h 有价格的事件的不同月份数（只看价格有没有）。"""
    mo = set()
    for s in POOL:
        if s not in EVS:
            continue
        ev = EVS[s][key]
        ok = px_ok(segs[s], h)
        e, j = np.nonzero(ev & ok)
        mo |= set(pd.DatetimeIndex(segs[s]["days"])[e].strftime("%Y-%m"))
    return len(mo)


def source_diff(LAB: dict, jnames: list[str], ynames: list[str]) -> dict:
    """十-5：今天的日経225 在 SRC_CMP_FROM〜J 数据最后一天的 Yahoo 与 J-Quants 标签一致率（两边都有行且都已知）。"""
    lo, hi = pd.Timestamp(SRC_CMP_FROM), pd.Timestamp(DATA_RANGE["J"][1])
    agree = {k: [0, 0] for k in ("D", "W", "M", "MUB")}
    for t in sorted(set(jnames) & set(ynames)):
        a, b = LAB["yahoo"].get(t), LAB["jq"].get(t)
        if a is None or b is None:
            continue
        ix = a.index.intersection(b.index)
        ix = ix[(ix >= lo) & (ix <= hi)]
        for k in agree:
            x, y = a.loc[ix, k].to_numpy(), b.loc[ix, k].to_numpy()
            f = (x != NA) & (y != NA)
            agree[k][0] += int((x[f] == y[f]).sum())
            agree[k][1] += int(f.sum())
    return {k: {"rows": v[1], "agree_pct": round(v[0] / v[1] * 100, 3) if v[1] else None} for k, v in agree.items()}


# ───────────────────────── B 部分（与 B4 结合） ─────────────────────────
_STATE_CACHE: dict = {}


def tab_states(src: str, t: str, tab: pd.DataFrame) -> dict:
    """一只票标签表的主口径状态（布尔数组，对齐表的行）。"""
    hit = _STATE_CACHE.get((src, t))
    if hit is None or hit[0] is not tab:                                     # 存着表本身：同一个对象才用缓存
        hit = (tab, states({k: tab[k].to_numpy() for k in ("D", "W", "M", "MUB")}, "main"))
        _STATE_CACHE[(src, t)] = hit
    return hit[1]


def state_ticks(tabs: dict, state: str, src: str, only=None) -> dict[str, frozenset]:
    """收盘时处于状态的日子 → candle_portfolio.run 的 exit_tick {票: frozenset(收盘日)}（那天收盘还拿着 → 第二天开盘卖）。"""
    out = {}
    for t, tab in tabs.items():
        if only is not None and t not in only:
            continue
        v = tab_states(src, t, tab)[state]
        if v.any():
            out[t] = frozenset(pd.DatetimeIndex(tab.index[v]).normalize())
    return out


def pre_earnings_n(tr: pd.DataFrame) -> int:
    """因 exit_tick 卖出的个股笔数（reason = pre_earnings）。"""
    return int((tr["reason"].astype(str) == "pre_earnings").sum()) if len(tr) else 0


def trades_of(W: dict, e: str, tr: pd.DataFrame, with_net: bool) -> pd.DataFrame:
    """引擎成交 → 窗口内买入、已平仓的日本个股（去掉 STOCK_SKIP）：ticker / fill / sig（成交日前一个交易日）/ exit / reason（with_net → net %）。"""
    if not len(tr):                                                          # 带类型的空表（fill / sig / exit 是日期列：part_b 的 .dt 不会因为一笔都没有而出错）
        out = pd.DataFrame({"ticker": pd.Series(dtype=object), "fill": pd.Series(dtype="datetime64[ns]"), "sig": pd.Series(dtype="datetime64[ns]"),
                            "exit": pd.Series(dtype="datetime64[ns]"), "reason": pd.Series(dtype=object)})
        if with_net:
            out["net"] = pd.Series(dtype=float)
        return out
    a, b = W["ctx"][e]["windows"][e]
    a, b = pd.Timestamp(a), pd.Timestamp(b) if b else pd.Timestamp("2026-10-01")
    tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(STOCK_SKIP) & (tr["reason"] != "end")]
    ed = pd.to_datetime(tr["entry_date"])
    tr = tr[((ed >= a) & (ed < b)).to_numpy()].reset_index(drop=True)
    days = pd.DatetimeIndex(W["ctx"][e]["days"])
    sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]
    out = pd.DataFrame({"ticker": tr["ticker"].astype(str), "fill": pd.to_datetime(tr["entry_date"]), "sig": pd.DatetimeIndex(sig),
                        "exit": pd.to_datetime(tr["exit_date"]), "reason": tr["reason"].astype(str)})
    if with_net:
        out["net"] = tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100
    return out


def b4_trades(W: dict, e: str, tbf, with_net: bool = False) -> pd.DataFrame:
    """B4 实际成交（trendline_study.b4_trades 的取法；--prep 不要 net）。"""
    import jq_study as JS
    import loop9_common as C9
    C9.run_block(W, e, tbf)
    return trades_of(W, e, pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades), with_net)


def row_pos(tab: pd.DataFrame, d) -> int | None:
    k = tab.index.get_indexer([pd.Timestamp(d)])[0]
    return None if k < 0 else int(k)


def group_one(tab: pd.DataFrame | None, i: int | None) -> str:
    """B-买分组一（信号日收盘时的组合）。"""
    if tab is None or i is None:
        return "标签不全"
    D, Wv, M, U = (int(tab[k].iloc[i]) for k in ("D", "W", "M", "MUB"))
    if NA in (D, Wv, M, U):                                                  # MUB 未知 → 不进任何组（二）
        return "标签不全"
    if U == 1:
        if D == -1 and Wv == -1:
            return "MUDW"
        if D == -1:
            return "MUD"
        if Wv == -1:
            return "MUW"
        return "MUN"
    if M <= 0:
        return "月K 横着走或往下走"
    return "月K 上升但不满 3 个月"


def group_two(st: dict | None, tab: pd.DataFrame | None, i: int | None, recent: int = RECENT) -> str:
    """B-买分组二（信号日及之前 recent 行）：P1 / P2 / P3 / P4 / NA。"""
    if tab is None or i is None or st is None:
        return "NA"
    u = int(tab["MUB"].iloc[i])
    if u == NA:
        return "NA"
    if u == 0:
        return "P4"
    sl = slice(max(0, i - recent), i + 1)
    if st["MUDW"][sl].any():
        return "P1"
    if (st["MUD"][sl] | st["MUW"][sl]).any():
        return "P2"
    return "P3"


def groups_of(LABsrc: dict, src: str, tickers, dates) -> tuple[list, list]:
    g1, g2 = [], []
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates))):
        tab = LABsrc.get(str(t))
        i = None if tab is None else row_pos(tab, d)
        st = None if tab is None else tab_states(src, str(t), tab)
        g1.append(group_one(tab, i))
        g2.append(group_two(st, tab, i))
    return g1, g2


def held_counts(LABsrc: dict, src: str, tr: pd.DataFrame) -> dict:
    """B4 成交里：持有期内（成交日收盘〜实际卖出前一天）出现状态 k 的笔数、成交日当天已处于状态 k 的笔数。"""
    out = {k: {"held": 0, "at_fill": 0} for k in IDS_A}
    for t, f, x in zip(tr["ticker"], tr["fill"], tr["exit"]):
        tab = LABsrc.get(str(t))
        if tab is None:
            continue
        st = tab_states(src, str(t), tab)
        m = np.asarray((tab.index >= pd.Timestamp(f)) & (tab.index < pd.Timestamp(x)))
        i = row_pos(tab, f)
        for k in IDS_A:
            out[k]["held"] += int(st[k][m].any())
            out[k]["at_fill"] += int(i is not None and bool(st[k][i]))
    return out


def window_has_state(LABsrc: dict, src: str, tickers, dates, k: str, n: int = POOL_WINDOW) -> int:
    """信号（票, 信号日）→ 成交日（之后第一行）起 n 行内有没有状态 k（只数个数）。"""
    c = 0
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates))):
        tab = LABsrc.get(str(t))
        if tab is None:
            continue
        p = int(tab.index.searchsorted(pd.Timestamp(d), side="right"))
        c += int(tab_states(src, str(t), tab)[k][p:p + n].any())
    return c


def coverage(LABsrc: dict, tr: pd.DataFrame) -> dict:
    """先决条件 4：B4 成交的信号日查得到标签行、D / W / M / MUB 都已知的笔数。"""
    row = known4 = 0
    for t, d in zip(tr["ticker"], tr["sig"]):
        tab = LABsrc.get(str(t))
        i = None if tab is None else row_pos(tab, d)
        if i is None:
            continue
        row += 1
        known4 += int(all(int(tab[k].iloc[i]) != NA for k in ("D", "W", "M", "MUB")))
    return {"trades": int(len(tr)), "with_row": int(row), "all_known": int(known4)}


def b_load(say=print) -> tuple[dict, dict, dict]:
    import loop10_common as C10
    import trendline_study as TS
    t0 = time.time()
    W = C10.load()
    say(f"载入 B3 + Zx：{time.time() - t0:.0f}s")
    tbf, tbf_pool = TS.tbf_gates(W, say)
    return W, tbf, tbf_pool


def same_acct(a: dict, b: dict, keys) -> bool:
    """账户各键完全相同（接线核对）：值相等，或两边都是 None / NaN。"""
    def same(x, y):
        if x is None or y is None:
            return x is None and y is None
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            return x == y
        return (np.isnan(fx) and np.isnan(fy)) or fx == fy
    return all(same(a.get(k), b.get(k)) for k in keys)


def b_precheck() -> dict:
    """B 部分先决条件里不用载入行情的几项（--run 开头、载入任何数据和算任何结果之前；--prep 也记下）：
    规则指纹 research_loop.rules_fingerprint(var) = FP、trendline_study.FP = FP、trendline_study.B4_TOL = B4_TOL、
    var/out/turn_shape_combo.json 存在且有 cand.TBF 的 Z / E / J。返回 {fingerprint, …, ok, why}。"""
    import research_loop as RL
    import trendline_study as TS
    from qbreak import paths
    why = []
    try:
        fp = RL.rules_fingerprint(paths.PROJECT_ROOT / "var")
    except Exception as ex:                                                  # noqa: BLE001
        fp = None
        why.append(f"规则指纹算不出（{type(ex).__name__}）")
    if fp is not None and fp != FP:
        why.append(f"规则指纹 {fp} ≠ 登记的 {FP}")
    if TS.FP != FP:
        why.append(f"trendline_study.FP = {TS.FP} ≠ 登记的 {FP}")
    if TS.B4_TOL != B4_TOL:
        why.append(f"trendline_study.B4_TOL = {TS.B4_TOL} ≠ 登记的 {B4_TOL}")
    ref = paths.PROJECT_ROOT / "var" / "out" / "turn_shape_combo.json"
    try:
        tbf_ref = json.loads(ref.read_text(encoding="utf-8"))["cand"]["TBF"]
        if not all(e in tbf_ref for e in N225_ERAS):
            why.append("turn_shape_combo.json 的 cand.TBF 缺年代")
    except Exception as ex:                                                  # noqa: BLE001
        why.append(f"var/out/turn_shape_combo.json 读不出 cand.TBF（{type(ex).__name__}）")
    return {"fingerprint": fp, "ok": not why, "why": why}


def b_prereq(W: dict, tbf: dict, say=print) -> dict:
    """先决条件 1〜3（trendline_study.prereq：规则指纹、B4 重算 = turn_shape_combo 的 TBF、接线核对 6 个键）+ 本研究登记的指纹 +
    接线核对再比 loop9_common.KEYS 的全部 8 个键（含 h1 / h2）。trendline_study.B4_TOL ≠ 本文件的 B4_TOL → 停。"""
    import loop6_common as L6
    import loop9_common as C9
    import trendline_study as TS
    if TS.B4_TOL != B4_TOL:
        raise SystemExit(f"trendline_study.B4_TOL = {TS.B4_TOL} ≠ 登记的 {B4_TOL} → 停")
    pre = TS.prereq(W, tbf, say)
    pre["fp_mine_ok"] = pre.get("fingerprint") == FP
    pre["b4_tol"] = B4_TOL
    wired = {}
    for e in N225_ERAS:
        S = C9.signals(W, e)
        tick = C9.tick_of(S["ticker"], S["date"], tbf[e])
        day = pd.Timestamp(W["ctx"][e]["days"][100]).normalize()
        fake = C9.acct(L6.run(W, e, em_tick=tick, exit_tick={"0000.T": frozenset([day])}))
        wired[e] = bool(same_acct(fake, pre["base"][e], C9.KEYS))
        pre.setdefault(e, {})["wired_all_keys"] = wired[e]
    pre["wired_keys"] = list(C9.KEYS)
    say("接线核对（全部 " + "、".join(C9.KEYS) + "）：" + "、".join(f"{e} {'一致' if v else '★ 不一致'}" for e, v in wired.items()))
    pre["ok"] = bool(pre["ok"] and pre["fp_mine_ok"] and all(wired.values()))
    return pre


def pool_signals(W: dict, s: str, tbf_pool: dict) -> pd.DataFrame:
    """池子里 B4 会买的信号（kept_pool 且 TBF 没挡）。"""
    import trendline_study as TS
    return TS.pool_x(W, s)[~np.asarray(tbf_pool[s], bool)].reset_index(drop=True)


def b_counts(W: dict, tbf: dict, tbf_pool: dict, LAB: dict, b4: dict) -> dict:
    """十-6：B4 成交笔数、标签覆盖、持有期内 / 成交日的状态笔数、池子信号与 60 行内的状态、B-买分组的个数（不含 Zx）。不算收益。"""
    out: dict = {"n225": {}, "pools": {}}
    for e in N225_ERAS:
        tr = b4[e]
        src = B_SRC[e]
        g1, g2 = groups_of(LAB[src], src, tr["ticker"], tr["sig"])
        out["n225"][e] = {"b4_trades": int(len(tr)), "ref": B4_TRADES_REF[e], "pre_earnings": pre_earnings_n(tr),
                          "coverage": coverage(LAB[src], tr), "held": held_counts(LAB[src], src, tr),
                          "g1": {k: g1.count(k) for k in G1}, "g2": {k: g2.count(k) for k in G2}}
    for s in B_POOLS:
        X = pool_signals(W, s, tbf_pool)
        src = B_SRC[s]
        r = {"signals": int(len(X)), "state_60": {k: window_has_state(LAB[src], src, X["ticker"], X["date"], k) for k in IDS_A}}
        if s != "Zx":
            g1, g2 = groups_of(LAB[src], src, X["ticker"], X["date"])
            r["g1"], r["g2"] = {k: g1.count(k) for k in G1}, {k: g2.count(k) for k in G2}
        out["pools"][s] = r
    return out


def run_cand(W: dict, e: str, tbf, ticks: dict) -> tuple[dict, pd.DataFrame]:
    """B4 + exit_tick → (账户, 成交)。"""
    import jq_study as JS
    import loop6_common as L6
    import loop9_common as C9
    S = C9.signals(W, e)
    tick = C9.tick_of(S["ticker"], S["date"], tbf)
    r = L6.run(W, e, em_tick=tick, exit_tick=ticks) if ticks else L6.run(W, e, em_tick=tick)
    return C9.acct(r), trades_of(W, e, pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades), with_net=True)


def pool_base(W: dict, s: str, X: pd.DataFrame, bt, rt: float) -> np.ndarray:
    """池子 s 每个信号的「X6」假想单笔 nb = turn_shape_combo.single_with_events(…, None) 的第一个返回值（净 %；行情缺 → NaN）。
    第一个返回值不看事件日（single_with_events 先算 X6、再算「X6 + 事件」）→ 先决条件 5 在任何候选之前核对，三个候选共用这一份。"""
    import turn_shape_combo as TC
    fa = W["SM"][B_SM[s]]["fa"]
    out = []
    for t, d in zip(X["ticker"], pd.to_datetime(X["date"])):
        df = fa.get(t)
        out.append(np.nan if df is None else float(TC.single_with_events(t, df, d, W["p0"], bt, rt, None)[0]))
    return np.asarray(out, float)


def base_match_info(nb, net) -> dict:
    """先决条件 5：{n, match, frac}（frac = 一致的比例；没有信号 → None）。"""
    ok = base_match(nb, net)
    n = int(len(ok))
    return {"n": n, "match": int(ok.sum()), "frac": float(ok.sum() / n) if n else None}


def pool_pairs(W: dict, s: str, X: pd.DataFrame, ticks: dict, bt, rt: float, nb: np.ndarray) -> dict:
    """池子 s 的配对假想单笔：「X6」（nb = pool_base）对「X6 + 事件」（single_with_events 的第二个返回值；这只票没有状态日 → 和 X6 相同，
    同 single_with_events 自己的做法）→ loop11_common.pair_stats。nb_diff = 带事件那次的第一个返回值和 nb 不同的笔数（预期 0）。"""
    import loop11_common as LC
    import turn_shape_combo as TC
    fa = W["SM"][B_SM[s]]["fa"]
    nb = np.asarray(nb, float)
    if len(nb) != len(X):
        raise ValueError("nb 与池子信号对不上")
    nv = nb.copy()
    diff = 0
    for i, (t, d) in enumerate(zip(X["ticker"], pd.to_datetime(X["date"]))):
        ev, df = ticks.get(t), fa.get(t)
        if df is None or not ev:
            continue
        a, b = TC.single_with_events(t, df, d, W["p0"], bt, rt, ev)
        nv[i] = b
        diff += int(not (a == nb[i] or (np.isnan(a) and np.isnan(nb[i]))))
    st = LC.pair_stats(nb, nv, np.isfinite(nb) & np.isfinite(nv) & ~np.isclose(nb, nv, atol=1e-9))
    st["nb_diff"] = int(diff)
    return st


def base_match(nb, net, tol: float = BASE_MATCH_TOL) -> np.ndarray:
    """先决条件 5 的「一致」：|nb − net| < tol（绝对差，不带 np.isclose 的相对容差；任一边 NaN → 不一致）。"""
    nb, net = np.asarray(nb, float), np.asarray(net, float)
    with np.errstate(invalid="ignore"):
        return np.isfinite(nb) & np.isfinite(net) & (np.abs(nb - net) < tol)


def trig_count(cand_tr: dict, base_tr: dict) -> int:
    """因事件多卖出的个股笔数 = Σ（候选的 pre_earnings 笔数 − B4 的同一数）（Z + E + J）。"""
    return int(sum(pre_earnings_n(cand_tr[e]) - pre_earnings_n(base_tr[e]) for e in N225_ERAS if e in cand_tr))


def trade_summary(net, months, ci: bool = True) -> dict:
    x = np.asarray(net, float)
    f = np.isfinite(x)
    if not f.any():
        return {"n": 0}
    out = {"n": int(f.sum()), "win": float((x[f] > 0).mean() * 100), "mean": float(x[f].mean())}
    if ci and f.sum() >= 2:
        B = boot_joint({"mean": x, "win": np.where(f, (x > 0) * 100.0, np.nan)}, months, levels={"95": Q95})
        out["ci"] = {k: list(v["95"]) for k, v in B.items()}
    return out


def part_b(W: dict, tbf: dict, tbf_pool: dict, LAB: dict, pre: dict, say=print, keep=None) -> dict:
    """B 部分（--run）：B-卖 3 个候选（账户 + 池子配对 + 第一关）、B-买分组、B4 触发笔的描述。
    keep(out)：先决条件 4 / 5 核对完、每个候选算完各调一次（run 用它落盘：后面的候选出错或进程被杀，前面算完的也留在文件里）。"""
    import loop11_common as LC
    import research_loop11 as R11
    t0 = time.time()
    keep = keep or (lambda o: None)
    out: dict = {"cand": {}, "base": pre["base"], "stage1": {}, "pools": {}, "trig": {}, "verdict": {}, "describe": {}}
    bt, rt = LC.bt_rt()
    base_tr = {e: b4_trades(W, e, tbf[e], with_net=True) for e in N225_ERAS}
    out["base_pre_earnings"] = {e: pre_earnings_n(base_tr[e]) for e in N225_ERAS}
    out["prereq"] = {"coverage": {e: coverage(LAB[B_SRC[e]], base_tr[e]) for e in N225_ERAS}, "base_match": {}}   # 先决条件 4 / 5（md 开头）
    X = {s: pool_signals(W, s, tbf_pool) for s in B_POOLS}
    NB = {s: pool_base(W, s, X[s], bt, rt) for s in B_POOLS}                  # 先决条件 5：在任何候选账户 / 配对之前核对
    out["prereq"]["base_match"] = {s: base_match_info(NB[s], X[s]["net"].to_numpy(float)) for s in B_POOLS}
    bad = [s for s in B_POOLS if (out["prereq"]["base_match"][s]["frac"] or 0) < BASE_MATCH_MIN]
    if bad:
        out["stopped"] = f"先决条件 5 不过：{bad} 的池子假想单笔与 kept_pool 的 net 一致的比例 < {BASE_MATCH_MIN}"
        say(out["stopped"])
        return out
    keep(out)
    for k in IDS_B:
        st = B_OF[k]
        cand, ctr = {}, {}
        for e in N225_ERAS:
            src = B_SRC[e]
            tabs = {t: LAB[src][t] for t in W["SM"][e]["fa"] if t in LAB[src]}
            cand[e], ctr[e] = run_cand(W, e, tbf[e], state_ticks(tabs, st, src))
        pools = {}
        for s in B_POOLS:
            src = B_SRC[s]
            only = set(X[s]["ticker"])
            pools[s] = pool_pairs(W, s, X[s], state_ticks({t: LAB[src][t] for t in only if t in LAB[src]}, st, src), bt, rt, NB[s])
        out["cand"][k], out["pools"][k] = cand, pools
        out["trig"][k] = trig_count(ctr, base_tr)
        out["stage1"][k] = R11.stage1(cand, pre["base"], pools, lenses=None, posthoc=False)
        out["verdict"][k] = ("几乎不触发" if out["trig"][k] < MIN_TRIG else
                             ("第一关通过（要另行登记第二关）" if out["stage1"][k]["ok"] else "第一关不过"))
        sold = pd.concat([ctr[e][ctr[e]["reason"] == "pre_earnings"].assign(era=e) for e in N225_ERAS], ignore_index=True)
        out["describe"][k] = {"sold": trade_summary(sold["net"], sold["fill"].dt.strftime("%Y-%m"), ci=False) if len(sold) else {"n": 0},
                              "held": {e: held_counts(LAB[B_SRC[e]], B_SRC[e], base_tr[e])[st] for e in N225_ERAS}}
        say(f"{k} 完成（判定只写在文件里）；{time.time() - t0:.0f}s")
        keep(out)
    bb: dict = {}
    for e in N225_ERAS:
        tr = base_tr[e]
        src = B_SRC[e]
        g1, g2 = groups_of(LAB[src], src, tr["ticker"], tr["sig"])
        bb[e] = {"net": tr["net"].to_numpy(float), "month": tr["sig"].dt.strftime("%Y-%m").to_numpy(), "g1": g1, "g2": g2}
    for s in ("W", "Jx"):
        src = B_SRC[s]
        g1, g2 = groups_of(LAB[src], src, X[s]["ticker"], X[s]["date"])
        bb[s] = {"net": X[s]["net"].to_numpy(float), "month": pd.to_datetime(X[s]["date"]).dt.strftime("%Y-%m").to_numpy(), "g1": g1, "g2": g2}
    out["buy_groups"] = {}
    for s, v in bb.items():
        g1, g2 = np.asarray(v["g1"]), np.asarray(v["g2"])
        out["buy_groups"][s] = {"g1": {g: trade_summary(v["net"][g1 == g], v["month"][g1 == g]) for g in G1},
                                "g2": {g: trade_summary(v["net"][g2 == g], v["month"][g2 == g]) for g in G2}}
    out["seconds"] = round(time.time() - t0)
    return out


# ───────────────────────── A 部分（--run） ─────────────────────────
def a2_job(item):
    """A2：一只票的事件 → turn_shape_combo.single_with_events(…, None) 的第一个返回值（X6 假想单笔，净 %）。
    单笔出错 → 记 NaN 并计数（A2 只描述：不让一笔异常中断只运行一次的 --run）。返回 (票, [净 %], 出错笔数, 出错的类型名)。"""
    import turn_shape_combo as TC
    t, df, dates, p0, bt, rt = item
    vals, err, kinds = [], 0, set()
    for d in dates:
        try:
            vals.append(float(TC.single_with_events(t, df, d, p0, bt, rt, None)[0]))
        except Exception as ex:                                              # noqa: BLE001
            vals.append(float("nan"))
            err += 1
            kinds.add(type(ex).__name__)
    return t, vals, err, sorted(kinds)


def part_a2(W: dict, EVT: pd.DataFrame, rt: float, say=print, workers: int = 4) -> dict:
    """A2（只描述）：Z / E / J 的 MUDW / MUD / MUW 进入事件（MUN 作对照）按现在的卖法拿。"""
    import loop11_common as LC
    t0 = time.time()
    bt, _ = LC.bt_rt()
    T = EVT[EVT["seg"].isin(A2_SEGS) & EVT["state"].isin(A2_IDS)][["seg", "state", "ticker", "date", "month"]].copy()
    items, metas = [], []
    for (seg, t), g in T.groupby(["seg", "ticker"]):
        df = W["SM"][seg]["fa"].get(t)
        if df is None:
            continue
        ds = sorted(set(pd.DatetimeIndex(g["date"])))
        items.append((t, df, ds, W["p0"], bt, rt))
        metas.append((seg, t, ds))
    if workers <= 1:
        got = [a2_job(it) for it in items]                                   # 同一进程（测试用）
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            got = list(ex.map(a2_job, items, chunksize=2))
    res, errors, kinds = {}, 0, set()
    for (seg, t, ds), (_, vals, err, kk) in zip(metas, got):
        errors += int(err)
        kinds |= set(kk)
        for d, v in zip(ds, vals):
            res[(seg, t, d)] = v
    T["net"] = [res.get((s, t, pd.Timestamp(d)), np.nan) for s, t, d in zip(T["seg"], T["ticker"], T["date"])]
    out = {"rt": rt, "seconds": round(time.time() - t0), "errors": int(errors), "error_kinds": sorted(kinds), "by": {}}
    for k in A2_IDS:
        x = T[T["state"] == k]
        out["by"][k] = {"pool": trade_summary(x["net"], x["month"]),
                        **{s: trade_summary(x.loc[x["seg"] == s, "net"], x.loc[x["seg"] == s, "month"], ci=False) for s in A2_SEGS}}
    say(f"A2 完成：{int(np.isfinite(T['net']).sum())} / {len(T)} 笔（单笔出错 {errors}）；{out['seconds']}s")
    return out


def _r(v, nd=4):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


def describe_extra(T: pd.DataFrame) -> dict:
    """只描述：按年份、J2 两半、去掉事件最多的 3 个月、单一年份贡献占比、按季度聚类、跌幅三档、大盘一起跌、
    去掉 fragile（事件日这一行自己的 D / W / M 近平局 FR，或 MUB 用到的前 3 根已完成月K 的月末行近平局 FRM）。"""
    out: dict = {}
    if not len(T):
        return out
    x = T[f"x{H}"].to_numpy(float)
    f = np.isfinite(x)
    tot = float(x[f].sum()) if f.any() else 0.0
    yr = {}
    for y, g in T.groupby("year"):
        xs = g[f"x{H}"].to_numpy(float)
        ff = np.isfinite(xs)
        yr[str(y)] = {"n": int(ff.sum()), "x_mean": _r(xs[ff].mean()) if ff.any() else None,
                      "contrib_pct": _r(float(xs[ff].sum()) / tot * 100, 2) if tot and ff.any() else None}
    out["by_year"] = yr
    cs = {k: v["contrib_pct"] for k, v in yr.items() if v["contrib_pct"] is not None}
    out["max_year"] = max(cs.items(), key=lambda kv: abs(kv[1])) if cs else None
    mo = T.loc[f, "month"].value_counts()
    top = list(mo.index[:DROP_TOP_MONTHS])
    out["drop_top_months"] = {**summarize(T[~T["month"].isin(top)], H, levels={"95": Q95}), "dropped": top}
    out["quarter"] = summarize(T, H, cluster="quarter", levels={"95": Q95})
    out["depth"] = {DEPTH_NAMES[i]: summarize(T[T["dep"] == i], H, levels={"95": Q95}) for i in range(3)}
    if "breadth" in T:
        out["breadth"] = {"一起跌": summarize(T[T["breadth"].astype(bool)], H, levels={"95": Q95}),
                          "自己跌": summarize(T[~T["breadth"].astype(bool)], H, levels={"95": Q95})}
    out["no_fragile"] = summarize(T[~(T["fr"].astype(bool) | T["frm"].astype(bool))], H, levels={"95": Q95})
    return out


def base_rates(seg: dict, F: dict, mub, rt: float) -> dict:
    """基准：窗口内 ALL（成员、MUB 已知：未知的不进任何基准，见二）与「MUB 任意日子」的全部股票日（h = 20）：数组（合并时拼起来）。"""
    days = pd.DatetimeIndex(seg["days"])
    a, b = WINDOWS[seg["tag"]]
    inwin = np.asarray((days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b)))
    mem = np.asarray(seg["mem"], bool) & inwin[:, None]
    r = F[H]["r"]
    x = r - F[H]["mk"][:, None]
    fin = np.isfinite(r)
    mub = np.asarray(mub)
    allm, mubm = mem & fin & (mub != NA), mem & fin & (mub == 1)
    return {"ALL": {"r": r[allm], "x": x[allm]}, "MUB": {"r": r[mubm], "x": x[mubm]}}


def base_summary(parts: list, rt: float) -> dict:
    if not parts:
        return {"n": 0}
    r = np.concatenate([p["r"] for p in parts])
    x = np.concatenate([p["x"] for p in parts])
    if not len(r):
        return {"n": 0}
    net = r - rt
    return {"n": int(len(r)), "win": float((net > 0).mean() * 100), "net_mean": float(net.mean()), "r_mean": float(r.mean()),
            "x_mean": float(np.nanmean(x)) if np.isfinite(x).any() else None}


def cells_table(parts: list) -> dict:
    """36 格（状态日、合并 POOL）：每格 n、成功率、平均 net20、x̄20、ȳ20。parts = [(格号, r, net, x, y)]。"""
    if not parts:
        return {}
    code = np.concatenate([p[0] for p in parts])
    r, net, x, y = (np.concatenate([p[i] for p in parts]) for i in range(1, 5))
    out = {}
    for c in range(36):
        k = (code == c) & np.isfinite(net)
        out[cell_name(c)] = {"n": int(k.sum()), "win": _rate(net[k] > 0, np.ones(int(k.sum()), bool)) if k.any() else None,
                             "net_mean": _mean(net[k]), "x_mean": _mean(x[k]), "y_mean": _mean(y[k])}
    return out


def jy_vs_j(EVT: pd.DataFrame, k: str) -> dict:
    """J-Y（Yahoo 标签）对 J（J-Quants 标签）：同一期间（事件日 ≥ max(SRC_CMP_FROM, J 这个状态第一个事件日)；J-Quants 数据 2016-09-26 起、
    MUB 约 2018-10〜11 才有，Yahoo 从 1999 年起算）各报一组，另报全期（期间不同，只作参考）。"""
    jy = EVT[(EVT["state"] == k) & (EVT["seg"] == "JY")]
    j = EVT[(EVT["state"] == k) & (EVT["seg"] == "J")]
    cut = pd.Timestamp(SRC_CMP_FROM)
    if len(j):
        cut = max(cut, pd.Timestamp(j["date"].min()))
    lv = {"95": Q95}
    return {"from": str(cut.date()), "JY": summarize(jy[jy["date"] >= cut], H, levels=lv), "J": summarize(j[j["date"] >= cut], H, levels=lv),
            "JY_all": summarize(jy, H, levels=lv), "J_all": summarize(j, H, levels=lv)}


def part_a(segs: dict, LAB: dict, rt: float, say=print) -> tuple[dict, pd.DataFrame]:
    """A 部分（--run）：每段的事件表 → 每段 / 合并的指标、判定、只描述。返回 (A, 事件表)。"""
    t0 = time.time()
    tabs_rows, base_parts, cell_parts, ends_cnt = [], {s: [] for s in SEGS}, [], {}
    for s in SEGS:
        seg = segs[s]
        m = to_matrix(seg, LAB[SRC[s]])
        EV, extra = seg_events(seg, m)
        ends_cnt[s] = extra
        F = fwd_tables(seg, m["MUB"], rt)
        ex = {"breadth": breadth_days(m, seg["mem"])}
        for key, ev in EV.items():
            R = event_rows(s, key, ev, F, seg, m, rt, ex)
            R["ticker"] = [seg["names"][j] for j in R["j"]]
            tabs_rows.append(R)
        base_parts[s].append(base_rates(seg, F, m["MUB"], rt))
        days = pd.DatetimeIndex(seg["days"])
        if s in POOL:
            pk = pick_days(days, *WINDOWS[s])[:, None] & np.asarray(seg["mem"], bool) & m["ROW"]
            cc = cell_codes(m)
            r = F[H]["r"]
            cell_parts.append((cc[pk], r[pk], r[pk] - rt, (r - F[H]["mk"][:, None])[pk], (r - F[H]["pk"][:, None])[pk]))
        say(f"A {s}：{sum(int(v.sum()) for v in EV.values())} 个事件（全部口径）；{time.time() - t0:.0f}s")
        del m, EV, F
    EVT = pd.concat(tabs_rows, ignore_index=True)
    A: dict = {"states": {}, "base": {}, "by_h": {}, "verdict": {}, "verdict95": {}, "end_counts": ends_cnt}
    for s in SEGS:
        A["base"][s] = {k: base_summary([p[k] for p in base_parts[s]], rt) for k in ("ALL", "MUB")}
    A["base"]["POOL"] = {k: base_summary([p[k] for s in POOL for p in base_parts[s]], rt) for k in ("ALL", "MUB")}
    for k in IDS_A:
        X = EVT[EVT["state"] == k]
        per = {s: summarize(X[X["seg"] == s], H) for s in SEGS}
        pool = summarize(X[X["seg"].isin(POOL)], H)
        ji, pr = judge_input(pool, per)
        v98 = verdict_a(ji["p98"], pr)
        v95 = verdict_a({**ji["p95"]}, pr)
        mub_win = A["base"]["POOL"]["MUB"].get("win")
        A["states"][k] = {"per": per, "pool": pool, "verdict": v98, "verdict_95": v95,
                          "view": VERDICT_VIEW.get(v98), "win_minus_mub": None if pool.get("win") is None or mub_win is None
                          else pool["win"] - mub_win}
        A["verdict"][k] = v98
        A["verdict95"][k] = v95
        A["by_h"][k] = {str(h): summarize(X[X["seg"].isin(POOL)], h, levels={"95": Q95}) for h in HORIZONS}
    D: dict = {"groups": {}, "sens": {}, "end": {}, "extra": {}, "cells": cells_table(cell_parts), "JY": {}}
    for k in (*DESC, *SUBS):
        X = EVT[(EVT["state"] == k) & EVT["seg"].isin(POOL)]
        D["groups"][k] = summarize(X, H, levels={"95": Q95})
    for k in IDS_A:
        for v in VARIANTS:
            if v == "main":
                continue
            X = EVT[(EVT["state"] == f"{k}@{v}") & EVT["seg"].isin(POOL)]
            D["sens"][f"{k}@{v}"] = summarize(X, H, levels={"95": Q95})
        X = EVT[(EVT["state"] == END_IDS[k]) & EVT["seg"].isin(POOL)]
        D["end"][END_IDS[k]] = summarize(X, H, levels={"95": Q95})
        X = EVT[(EVT["state"] == k) & EVT["seg"].isin(POOL)]
        D["extra"][k] = describe_extra(X)
        J2 = EVT[(EVT["state"] == k) & (EVT["seg"] == "J2")]
        D["extra"][k]["J2_halves"] = {"≤ " + J2_HALVES[0]: summarize(J2[J2["date"] <= pd.Timestamp(J2_HALVES[0])], H, levels={"95": Q95}),
                                      "≥ " + J2_HALVES[1]: summarize(J2[J2["date"] >= pd.Timestamp(J2_HALVES[1])], H, levels={"95": Q95})}
        D["JY"][k] = jy_vs_j(EVT, k)
    A["describe"] = D
    A["seconds"] = round(time.time() - t0)
    return A, EVT


# ───────────────────────── 流程 ─────────────────────────
def peak_mem_mb() -> dict:
    a = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    b = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    return {"self_mb": round(a), "children_mb": round(b)}


def load_labels(say=print, workers: int = 4) -> tuple[dict, dict, dict, dict, dict, dict]:
    segs, raw, ends = load_a_panels(say)
    LAB, STATS, INFO = build_labels(raw, ends, say, workers)
    return segs, raw, ends, LAB, STATS, INFO


def prep(say=print, workers: int = 4) -> dict:
    """--prep：冻结缓存 + 标签 + 标签核对 + 先决条件 + 只数个数（不算任何收益、成功率、超额或均值）。"""
    t0 = time.time()
    code = check_code()
    frozen = freeze_cache()
    segs, raw, ends, LAB, STATS, INFO = load_labels(say, workers)
    out: dict = {"git": git_info(), "code": code, "frozen": frozen, "data_fp": data_fp(fp_items(segs, LAB))}
    say(f"DATA_FP = {out['data_fp']}")
    out["label_check"] = label_check(raw, ends, INFO, STATS, say, workers)
    stop = label_check_stop(out["label_check"])
    if stop or not out["label_check"]["ok"]:
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        raise SystemExit(stop or "标签核对没过 → 停")
    out["panel_check"] = panel_check(segs, LAB)
    if not out["panel_check"]["ok"]:
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        raise SystemExit("标签输入与收益面板的 Close 对不上 → 停")
    out["clean"] = {src: {k: int(sum(int(i.get(k, 0)) for i in INFO[src].values()))
                          for k in ("rows_in", "nan_close", "zero_vol", "non_jpx", "before_from", "after_end", "rows")} for src in INFO}
    out["clean"]["J2_zero_vol_with_close"] = int(sum(int(INFO["jq"][t].get("zero_vol", 0)) for t in segs["J2"]["names"] if t in INFO["jq"]))
    out["nd_diff"] = {k: int(sum(int((i.get("nd") or {}).get(k, 0)) for i in INFO["yahoo"].values())) for k in ("rows", "D", "W", "M")}
    out["source_diff"] = source_diff(LAB, segs["J"]["names"], segs["JY"]["names"])
    C, EVS = {}, {}
    for s in SEGS:
        seg = segs[s]
        m = to_matrix(seg, LAB[SRC[s]])
        EV, extra = seg_events(seg, m)
        C[s] = counts_seg(seg, m, EV, extra)
        EVS[s] = {k: EV[k] for k in (*IDS_A, "MUN")}
        say(f"{s}：事件 " + "、".join(f"{k} {C[s]['events'][k]['n']}" for k in IDS_A) + f"；{time.time() - t0:.0f}s")
        del m, EV
    out["counts"] = C
    out["prep_events"] = prep_events(C)
    out["feasibility"] = feasibility(C)
    for k in IDS_A:
        out["feasibility"][k]["pool_months"] = pool_months(EVS, segs, k)
        out["feasibility"][k]["months_ok"] = out["feasibility"][k]["pool_months"] >= MIN_MONTHS
    a2_ev = {s: [(segs[s]["names"][j], pd.DatetimeIndex(segs[s]["days"])[e]) for k in A2_IDS for e, j in zip(*np.nonzero(EVS[s][k]))]
             for s in A2_SEGS}
    del EVS
    segs.clear()
    out["b_precheck"] = b_precheck()
    W, tbf, tbf_pool = b_load(say)
    pre = b_prereq(W, tbf, say)
    out["prereq_b"] = {k: v for k, v in pre.items() if k != "base"}
    if not (pre["ok"] and out["b_precheck"]["ok"]):
        say(f"★ B 先决条件不过（{'；'.join(out['b_precheck']['why']) or '见 prereq_b'}）：b_precheck 不过 → --run 开头就停；"
            "B4 重算 / 接线核对不过 → --run 的 B 部分停 → 先修好再登记")
    out["prereq_b"]["base_published"] = {e: {k: pre["base"][e].get(k) for k in ("calmar", "n", "win")} for e in N225_ERAS}
    b4 = {e: b4_trades(W, e, tbf[e], with_net=False) for e in N225_ERAS}
    out["b"] = b_counts(W, tbf, tbf_pool, LAB, b4)
    n_a2 = {s: int(sum(1 for t, _ in a2_ev[s] if t in W["SM"][s]["fa"])) for s in A2_SEGS}
    out["a2"] = {"singles": n_a2, "total": int(sum(n_a2.values())),
                 "est_minutes_4proc": round(sum(n_a2.values()) * A2_MS / 1000 / 4 / 60, 1), "note": f"按每次约 {A2_MS} ms 估计，登记前不调用"}
    out["elapsed_s"] = round(time.time() - t0)
    out["peak_mem"] = peak_mem_mb()
    say(f"要写进常数（登记提交）：DATA_FP = {out['data_fp']!r}；PREP_EVENTS = {json.dumps(out['prep_events'], ensure_ascii=False)}")
    return out


def prep_events(C: dict) -> dict:
    """登记前个数里每段 × 每个状态（IDS_A + DESC）的事件数（写进常数 PREP_EVENTS；--run 的 md 第六节逐项对照）。"""
    return {s: {k: int(C[s]["events"][k]["n"]) for k in (*IDS_A, *DESC)} for s in SEGS if s in C}


def run(say=print, workers: int = 4, save=None) -> dict:
    """--run（只运行一次）：A + A2 + B 第一关 + 只描述。save(res) = 每算完一部分就把到那时为止的结果写进 partial（见文件开头十一）。
    A 之后（B3 载入、A2、B 先决条件、B）出错 → 照实记下、照常返回（文件开头八）。"""
    import loop11_common as LC
    t0 = time.time()
    code = check_code()
    if DATA_FP is None or PREP_EVENTS is None:
        raise SystemExit("DATA_FP / PREP_EVENTS 还没登记（先 --prep，把数据指纹和登记前事件数写进常数并提交）→ 停")
    bpre0 = b_precheck()                                                     # 先决条件里不用载入行情的几项：不过 → 算任何结果之前整个停
    if not bpre0["ok"]:
        raise SystemExit(f"B 部分先决条件不过（{'；'.join(bpre0['why'])}）→ 停（还没有算任何结果）")
    frozen = freeze_cache()
    git = git_info()
    save = save or (lambda r: None)
    segs, raw, ends, LAB, STATS, INFO = load_labels(say, workers)
    fp = data_fp(fp_items(segs, LAB))
    if fp != DATA_FP:
        raise SystemExit(f"数据指纹 {fp} ≠ 登记的 {DATA_FP}（缓存变了）→ 停")
    pc = panel_check(segs, LAB)
    if not pc["ok"]:
        raise SystemExit(f"标签输入与收益面板的 Close 对不上：{pc} → 停")
    _, rt = LC.bt_rt()
    if abs(rt - RT_REF) >= RT_TOL:
        raise SystemExit(f"成本 RT {rt:.6f} 和登记的 {RT_REF} 差太多 → 停")
    res: dict = {"registered": registered(), "git": git, "code": code, "data_fp": fp, "frozen": frozen, "rt": rt,
                 "prereq": {"panel_check": pc, "fallback": STATS, "B_precheck": bpre0}, "prep_events": PREP_EVENTS}
    A, EVT = part_a(segs, LAB, rt, say)
    res["describe"] = A.pop("describe")
    res["A"] = A
    res["verdict"] = A["verdict"]
    res["counts"] = {"events": {s: {k: int(((EVT["seg"] == s) & (EVT["state"] == k)).sum()) for k in (*IDS_A, *DESC)} for s in SEGS}}
    res["elapsed_s"] = round(time.time() - t0)
    save(res)                                                                # A 一算完就落盘（之后出错也留下记录，不能重跑）
    say(f"A 部分完成（判定只写在文件里）；{time.time() - t0:.0f}s")
    segs.clear()
    # A 写进 partial 之后的每一步（B3 载入、A2、B 先决条件、B）出错都只照实记下（异常类型名 + 代码位置，不写异常信息），
    # 照常走到最后写出 json / md：不让进程带着 traceback 退出、把 A 只留在 partial 里、登记的 B 判定永远没有
    try:
        W, tbf, tbf_pool = b_load(say)
    except (SystemExit, Exception) as ex:                                    # noqa: BLE001
        why = err_info(ex)
        res["describe"]["A2"] = {"error": f"B3 载入出错：{why}"}
        res["prereq"]["B"] = {"ok": False, "error": f"B3 载入出错：{why}"}
        res["B"] = {"stopped": f"B3 载入出错（{why}）：A2 和 B 都没有算"}
        say(f"B3 载入出错（{type(ex).__name__}）：照实记下，A2 和 B 都没有算")
        res["elapsed_s"] = round(time.time() - t0)
        save(res)
        return res
    try:
        res["describe"]["A2"] = part_a2(W, EVT, rt, say, workers)
    except (SystemExit, Exception) as ex:                                    # noqa: BLE001  A2 只描述：整段出错也照实记下，接着算 B
        res["describe"]["A2"] = {"error": err_info(ex)}
        say(f"A2 出错（{type(ex).__name__}）：照实记下，接着算 B")
    del EVT
    res["elapsed_s"] = round(time.time() - t0)
    save(res)
    try:                                                                     # B4 重算与接线核对要载入 B3（A 之后）：核对时出错也只停 B、A 照写
        pre = b_prereq(W, tbf, say)
    except (SystemExit, Exception) as ex:                                    # noqa: BLE001  例：trendline_study.prereq「TBF 旗子与信号对不上 → 停」
        pre = {"ok": False, "error": f"SystemExit: {ex}" if isinstance(ex, SystemExit) else err_info(ex)}   # 停的理由是写好的句子；其他异常只写类型和位置
    res["prereq"]["B"] = {k: v for k, v in pre.items() if k != "base"}
    if not pre["ok"]:
        res["B"] = {"stopped": f"先决条件 1〜3 不过：{res['prereq']['B']}"}
    else:
        def keep(o):                                                         # 每个候选算完就落盘（进程在这之后被杀 → partial 里是「没有算完」+ 已算完的）
            res["B"] = {"stopped": "B 部分没有算完（中途落盘之后进程停下）", "partial": copy.deepcopy(o)}
            res["elapsed_s"] = round(time.time() - t0)
            save(res)
        try:
            res["B"] = part_b(W, tbf, tbf_pool, LAB, pre, say, keep=keep)
        except (SystemExit, Exception) as ex:                                # noqa: BLE001
            done = (res.get("B") or {}).get("partial")                       # 出错之前最后一次落盘的（只含算完的候选）
            res["B"] = {"stopped": f"B 部分出错（{err_info(ex)}）", **({"partial": done} if done else {})}
            say(f"B 部分出错（{type(ex).__name__}）：照实记下（出错前算完的候选留在文件里）")
    res["elapsed_s"] = round(time.time() - t0)
    save(res)
    return res


def err_info(ex: BaseException) -> str:
    """--run 里 A 之后出错时写进文件的说明：异常类型名 + 最里面一层的代码位置（文件名:行号 函数名）。
    不写异常信息（可能带数字或票名）；位置只写文件名、不写目录。"""
    tb = traceback.extract_tb(ex.__traceback__)
    if not tb:
        return type(ex).__name__
    f = tb[-1]
    return f"{type(ex).__name__}；{Path(f.filename).name}:{f.lineno} {f.name}"


REGISTERED = ("IDS_A", "IDS_B", "B_OF", "DESC", "SUBS", "SUB_OF", "GROUPS", "END_IDS", "N_MONTHS", "N_SENS", "VARIANTS", "COOL", "END_WITHIN", "EVERY", "RECENT",
              "HORIZONS", "H", "SAMPLES", "POOL", "SEGS", "SRC", "WINDOWS", "DATA_RANGE", "W_NAMES", "LABEL_FROM", "MIN_EV_POOL", "MIN_MONTHS",
              "MIN_EV_SAMPLE", "MIN_SEG", "MIN_PP", "MIN_PEERS", "CI_LEVEL", "Q98", "Q95", "BOOT_N", "SEED", "TIE_EPS", "BREADTH_CUT", "DEPTH_BINS",
              "J2_HALVES", "DROP_TOP_MONTHS", "RT_REF", "RT_TOL", "FP", "B4_TOL", "MIN_TRIG", "BASE_MATCH_MIN", "BASE_MATCH_TOL", "B4_TRADES_REF",
              "N225_ERAS", "B_POOLS", "B_SM", "B_SRC", "POOL_WINDOW", "A2_SEGS", "A2_IDS", "EXH_FIXED", "EXH_RANDOM", "CHECK_ROWS", "SRC_CMP_FROM",
              "STOCK_SKIP", "SLOPE_BARS", "KLINE_SRC_SHA", "ZERO_VOL_ENV", "EPS", "SEEN", "VERDICT_SAY", "DATA_FP", "PREP_EVENTS")


def registered() -> dict:
    """json 的 registered：全部登记常数（登记后不改）。"""
    g = globals()
    return {k: g[k] for k in REGISTERED}


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:+.2f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def _ci(s: dict, key: str, lv: str, fmt="{:+.2f}") -> str:
    c = ((s.get("ci") or {}).get(key) or {}).get(lv)
    return "—" if not c else f"{_f(c[0], fmt)}〜{_f(c[1], fmt)}"


def compare_lines(res: dict) -> list[str]:
    """md 第六节：登记前个数（PREP_EVENTS）/ 运行时的事件数逐项对照；事前预期（文件开头十二）→ 结果。"""
    prep = res.get("prep_events") or {}
    now = (res.get("counts") or {}).get("events") or {}
    L = ["事件数（登记前 / 运行时；不一样的标 ★）：", "", "| 段 | " + " | ".join((*IDS_A, *DESC)) + " |", "|---|" + "---|" * len((*IDS_A, *DESC))]
    diff = 0
    for s in SEGS:
        cells = []
        for k in (*IDS_A, *DESC):
            a, b = (prep.get(s) or {}).get(k), (now.get(s) or {}).get(k)
            bad = a is None or b is None or int(a) != int(b)
            diff += int(bad)
            cells.append(f"{'—' if a is None else a} / {'—' if b is None else b}{' ★' if bad else ''}")
        L.append(f"| {s} | " + " | ".join(cells) + " |")
    L += ["", f"登记前个数与运行时{'完全相同' if not diff else f'有 {diff} 处不同（照实写，不改规则）'}。", "", "事前预期（运行前写，来自以往结论）→ 结果："]
    A, B = res.get("A") or {}, b_of(res)
    pv, pt = b_done(B)
    bp = ((A.get("base") or {}).get("POOL") or {}).get("MUB") or {}
    for k in IDS_A:
        st = (A.get("states") or {}).get(k) or {}
        p = st.get("pool") or {}
        L.append(f"- {k}：预期「{EXPECT_A[k]}」→ 判定「{st.get('verdict')}」，x̄ {_f(p.get('x_mean'))} pp、ȳ {_f(p.get('y_mean'))} pp；"
                 f"成功率 {_f(p.get('win'), '{:.1f}')}%（预期约 50〜56%）、与 MUB 任意日子差 {_f(st.get('win_minus_mub'))} pp（预期 ±3 pp 之内）；"
                 f"卖对的比例 {_f(p.get('right_r'), '{:.1f}')}%（预期约 45〜50%）")
    L.append(f"- 「MUB 任意日子」的成功率 {_f(bp.get('win'), '{:.1f}')}%。")
    for k in IDS_B:
        if not B.get("stopped"):
            got = f"「{(B.get('verdict') or {}).get(k)}」（因事件多卖出 {(B.get('trig') or {}).get(k)} 笔）"
        elif k in pv:
            got = f"「{pv[k]}」（因事件多卖出 {pt.get(k)} 笔；B 部分停下之前已算完）"
        else:
            got = "B 部分没有算"
        L.append(f"- {k}：预期「{EXPECT_B[k]}」→ {got}")
    return L


def b_of(res: dict) -> dict:
    """md 用的 B：文件里没有 B 键（例：A 一算完写的 partial）或是空的 → 当作「停」处理（report 不因为缺键出错）。"""
    return res.get("B") or {"stopped": "文件里没有 B 部分的结果（A 之后中途停下）"}


def b_done(B: dict) -> tuple[dict, dict]:
    """B 部分停下 / 出错之前已算完的候选：({候选: 结论}, {候选: 因事件多卖出的笔数})（取自 B.partial；没有 → 两个空表）。"""
    p = B.get("partial") or {}
    return dict(p.get("verdict") or {}), dict(p.get("trig") or {})


def report(res: dict) -> str:
    A, B = res["A"], b_of(res)
    D = res["describe"]
    g = res["git"]
    bpre = B.get("prereq") or (B.get("partial") or {}).get("prereq") or {}
    pre_b = res["prereq"].get("B") or {}
    rules_fp = pre_b.get("fingerprint") or (res["prereq"].get("B_precheck") or {}).get("fingerprint")   # B 核对出错 → 用开头 b_precheck 核对过的
    cov = bpre.get("coverage") or {}
    bm = bpre.get("base_match") or {}
    dirty = f"（有未提交的改动！{', '.join(g.get('dirty_files') or [])}）" if g.get("dirty") else ""
    L = ["# 月K 往上走时日K / 周K 往下走：买卖点成功率与收益率（scripts/month_up_dip_study.py；只运行一次）", "",
         f"代码 {g['rev']}{dirty}；DATA_FP {res['data_fp']}；面板标签代码 {(res.get('code') or {}).get('kline_src_sha')}；规则指纹 "
         f"{rules_fp}；成本 RT {res['rt']:.4f}%。",
         f"先决条件：标签输入与面板 Close 最大相对差 ≤ 1e−12（{'是' if res['prereq']['panel_check']['ok'] else '否'}）；B 部分"
         f"{'停（' + B['stopped'] + '）' if B.get('stopped') else '先决条件 1〜3、5 都过；4 标签覆盖只计数（查不到 / 未知的归入「标签不全」，不是停的条件）'}。",
         "先决条件 4 标签覆盖（B4 成交笔数 / 信号日查得到标签行 / D、W、M、MUB 都已知；★ = 有标签不全的笔）："
         + ("；".join(f"{e} {v['trades']} / {v['with_row']} / {v['all_known']}"
                     f"{'（★ ' + str(v['trades'] - v['all_known']) + ' 笔标签不全）' if v['all_known'] < v['trades'] else ''}"
                     for e, v in cov.items()) or "—")
         + f"；先决条件 5 池子假想单笔与 kept_pool 一致（|差| < {BASE_MATCH_TOL:g}，门槛 ≥ {BASE_MATCH_MIN:.0%}）："
         + ("；".join(f"{s} {v.get('match')} / {v.get('n')}（{_f(None if v.get('frac') is None else v['frac'] * 100, '{:.2f}')}%）"
                     for s, v in bm.items()) or "—") + "。",
         "判定（文件开头七）：合并 POOL = Z + E + W + J2；98.33% 区间（按事件月聚类自助法 2,000 次）；买点成立要 FULL、x̄ ≥ +0.30 pp 且下限 > 0、"
         "ȳ 下限 > 0、各段 x̄ / ȳ 都 > 0；卖点成立对称。", "",
         "## 〇 一句话结论", ""]
    for k in IDS_A:
        s = A["states"][k]
        v = s["view"] or (s["verdict"], s["verdict"])
        p = s["pool"]
        L.append(f"- **{k}「{NAMES[k]}」**：{say_verdict(k, s['verdict'], p.get('x_mean'))}。买点视角「{v[0]}」、卖点视角「{v[1]}」"
                 f"（第二天买、拿 20 个交易日：赚钱的比例 {_f(p.get('win'), '{:.1f}')}%、"
                 f"比大盘 {_f(p.get('x_mean'))} pp、比同一天其他月涨的票 {_f(p.get('y_mean'))} pp）")
    L += ["", "## 一 面板速查主表（合并 Z + E + W + J2；h = 20）", "",
          "| 状态 | 事件 / 月份 | 成功率（ALL / MUB 任意日子） | 平均 / 中位 net | x̄（95% / 98.33%） | ȳ（95% / 98.33%） | 卖对的比例（r / x） | 卖出避开的收益 | 判定 |",
          "|---|---|---|---|---|---|---|---|---|"]
    bp = A["base"]["POOL"]
    for k in IDS_A:
        p = A["states"][k]["pool"]
        L.append(f"| {k} | {p.get('n_x', 0)} / {p.get('months', 0)} | {_f(p.get('win'), '{:.1f}')}%（{_f(bp['ALL'].get('win'), '{:.1f}')} / "
                 f"{_f(bp['MUB'].get('win'), '{:.1f}')}%） | {_f(p.get('net_mean'))} / {_f(p.get('net_med'))}% | {_f(p.get('x_mean'))}（{_ci(p, 'x', '95')} / "
                 f"{_ci(p, 'x', '98.33')}） | {_f(p.get('y_mean'))}（{_ci(p, 'y', '95')} / {_ci(p, 'y', '98.33')}） | {_f(p.get('right_r'), '{:.1f}')} / "
                 f"{_f(p.get('right_x'), '{:.1f}')}% | {_f(p.get('avoided'))}% | **{A['verdict'][k]}**（95% 下：{A['verdict95'][k]}） |")
    L += ["", "成功率差（事件 − MUB 任意日子，pp）与 lift（只描述）：" + "；".join(
        f"{k} {_f(A['states'][k]['win_minus_mub'])} / lift_buy {_f(A['states'][k]['pool'].get('lift_buy'))} / lift_sell "
        f"{_f(A['states'][k]['pool'].get('lift_sell'))}" for k in IDS_A), "",
          "## 二 分段表（h = 20；J-Y 另附、只描述）", "",
          "| 状态 | 段 | n | 成功率 | net̄ | x̄（95%） | ȳ（95%） |", "|---|---|---|---|---|---|---|"]
    for k in IDS_A:
        for s in (*SAMPLES, "JY"):
            q = A["states"][k]["per"][s]
            L.append(f"| {k} | {s}{'（只描述）' if s == 'JY' else ''} | {q.get('n_x', 0)} | {_f(q.get('win'), '{:.1f}')}% | {_f(q.get('net_mean'))}% | "
                     f"{_f(q.get('x_mean'))}（{_ci(q, 'x', '95')}） | {_f(q.get('y_mean'))}（{_ci(q, 'y', '95')}） |")
        p = A["states"][k]["pool"]
        L.append(f"| {k} | 合并 | {p.get('n_x', 0)} | {_f(p.get('win'), '{:.1f}')}% | {_f(p.get('net_mean'))}% | {_f(p.get('x_mean'))}（{_ci(p, 'x', '95')}） | "
                 f"{_f(p.get('y_mean'))}（{_ci(p, 'y', '95')}） |")
    L += ["", "基准（h = 20，全部股票日）：" + "；".join(
        f"{s} ALL {_f(A['base'][s]['ALL'].get('win'), '{:.1f}')}% / net {_f(A['base'][s]['ALL'].get('net_mean'))}%、MUB {_f(A['base'][s]['MUB'].get('win'), '{:.1f}')}% / "
        f"net {_f(A['base'][s]['MUB'].get('net_mean'))}% / x̄ {_f(A['base'][s]['MUB'].get('x_mean'))}" for s in (*SAMPLES, "POOL")),
          "", "## 三 各期限（合并；成功率 / 平均 net / x̄ / ȳ）", "", "| 状态 | " + " | ".join(f"h{h}" for h in HORIZONS) + " |",
          "|---|" + "---|" * len(HORIZONS)]
    for k in IDS_A:
        L.append(f"| {k} | " + " | ".join(f"{_f(q.get('win'), '{:.1f}')}% / {_f(q.get('net_mean'))} / {_f(q.get('x_mean'))} / {_f(q.get('y_mean'))}"
                                          for q in (A["by_h"][k][str(h)] for h in HORIZONS)) + " |")
    L += ["", "## 四 只描述", "", "### 36 格（状态日，每 5 个交易日一天；合并）", "", "| 格 | n | 成功率 | net̄ | x̄ | ȳ |", "|---|---|---|---|---|---|"]
    for name, q in D["cells"].items():
        L.append(f"| {name} | {q['n']} | {_f(q['win'], '{:.1f}')}% | {_f(q['net_mean'])} | {_f(q['x_mean'])} | {_f(q['y_mean'])} |")

    def row(name, q, ref=False):
        return (f"| {name} | {q.get('n_x', 0)} | {_f(q.get('win'), '{:.1f}')}% | {_f(q.get('net_mean'))} | {_f(q.get('x_mean'))}（{_ci(q, 'x', '95')}） | "
                f"{_f(q.get('y_mean'))}{'†' if ref else ''} |")
    L += ["", "### 细分、对照组、敏感度、结束事件（合并，h = 20）", "",
          "细分（MUD-u / -f、MUW-u / -f）= 母组的进入事件按事件日的周K / 日K 拆开（加起来 = 母组）。"
          "† MN* / 敏感度 / 结束事件的 ȳ = 比同一天 MUB(N=3) 为真的票（对照：比月涨的票），事件本身不一定在里面，不是「回调本身加不加分」；"
          "x̄ 的 ALL 也只含那天 MUB(N=3) 已知的成员。只描述。", "",
          "| 组 | n | 成功率 | net̄ | x̄（95%） | ȳ |", "|---|---|---|---|---|---|"]
    for k, q in D["groups"].items():
        L.append(row(f"{k} {NAMES.get(k, '')}", q, ref=k in ("MNDW", "MND", "MNW")))
    for k, q in D["sens"].items():
        L.append(row(k, q, ref=True))
    for k, q in D["end"].items():
        L.append(row(f"{k}（回调结束再买）", q, ref=True))
    L.append("")
    L.append("月线转弱 / 没有结束：" + "；".join(f"{s} " + "、".join(f"{k} {v.get('weak', 0)} / {v.get('none', 0)}" for k, v in A["end_counts"][s].items())
                                          for s in SEGS))
    for k in IDS_A:
        x = D["extra"][k]
        if "depth" not in x:
            continue
        L += ["", f"### {k} 的切法（合并，h = 20，x̄ 与 95% 区间）", "",
              "- 跌幅：" + "；".join(f"{b} {q.get('n_x', 0)} 个 {_f(q.get('x_mean'))}（{_ci(q, 'x', '95')}）" for b, q in x["depth"].items()),
              "- 大盘一起跌 / 自己跌：" + "；".join(f"{b} {q.get('n_x', 0)} 个 {_f(q.get('x_mean'))}（{_ci(q, 'x', '95')}）" for b, q in (x.get("breadth") or {}).items()),
              f"- 去掉事件最多的 3 个月（{', '.join(x['drop_top_months']['dropped'])}）：{_f(x['drop_top_months'].get('x_mean'))}（{_ci(x['drop_top_months'], 'x', '95')}）",
              f"- 按季度聚类：{_ci(x['quarter'], 'x', '95')}；去掉 fragile（FR 或 FRM）：{_f(x['no_fragile'].get('x_mean'))}（{_ci(x['no_fragile'], 'x', '95')}）",
              "- J2 两半：" + "；".join(f"{b} {q.get('n_x', 0)} 个 {_f(q.get('x_mean'))}" for b, q in x["J2_halves"].items()),
              "- 按年份（n / x̄ / 占合计 %）：" + "；".join(f"{y} {v['n']} / {_f(v['x_mean'])} / {_f(v['contrib_pct'], '{:.0f}')}" for y, v in x["by_year"].items()),
              f"- J-Y 对 J（Yahoo 标签 vs J-Quants 标签；同一期间 ≥ {D['JY'][k].get('from')}，x̄（n））：{_f(D['JY'][k]['JY'].get('x_mean'))}"
              f"（{D['JY'][k]['JY'].get('n_x', 0)}）vs {_f(D['JY'][k]['J'].get('x_mean'))}（{D['JY'][k]['J'].get('n_x', 0)}）；全期（期间不同，只作参考）"
              f"{_f((D['JY'][k].get('JY_all') or {}).get('x_mean'))}（{(D['JY'][k].get('JY_all') or {}).get('n_x', 0)}）vs "
              f"{_f((D['JY'][k].get('J_all') or {}).get('x_mean'))}（{(D['JY'][k].get('J_all') or {}).get('n_x', 0)}）"]
    a2 = D.get("A2") or {}
    if a2.get("error"):
        L += ["", f"### A2 按现在的卖法拿：没有算出（出错 {a2['error']}；只描述，照实记下）"]
    elif a2:
        L += ["", "### A2 按现在的卖法拿（Z / E / J；X6 假想单笔，净 %）", "",
              *([f"单笔出错 {a2['errors']} 笔（{', '.join(a2.get('error_kinds') or [])}；记 NaN、不算）。", ""] if a2.get("errors") else []),
              "| 状态 | 合并 n | 胜率 | 每笔（95%） | Z / E / J 每笔 |", "|---|---|---|---|---|"]
        for k, v in a2["by"].items():
            p = v["pool"]
            ci = (p.get("ci") or {}).get("mean")
            L.append(f"| {k} | {p.get('n', 0)} | {_f(p.get('win'), '{:.1f}')}% | {_f(p.get('mean'))}（{'—' if not ci else _f(ci[0]) + '〜' + _f(ci[1])}） | "
                     + " / ".join(f"{_f(v[s].get('mean'))}（{v[s].get('n', 0)}）" for s in A2_SEGS) + " |")
    L += ["", "## 五 结合 B4", ""]
    if B.get("stopped"):
        L.append(f"B 部分没有算：{B['stopped']}")
        pv, pt = b_done(B)
        if pv:
            L += ["", "停下之前已算完的候选（照实记录；账户、池子、第一关的数字见 json 的 B.partial）："
                  + "；".join(f"**{k}「{NAMES[k]}」** → **{pv[k]}**（因事件多卖出 {pt.get(k)} 笔）" for k in IDS_B if k in pv)
                  + "；其余候选和 B-买分组没有算。"]
    else:
        L += ["| 候选 | 年代 | Calmar | 差 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
        for k in IDS_B:
            for e in N225_ERAS:
                b, c = B["base"][e], B["cand"][k][e]
                L.append(f"| {k} | {e} | {_f(b['calmar'], '{:.3f}')} → {_f(c['calmar'], '{:.3f}')} | "
                         f"{_f(None if c['calmar'] is None or b['calmar'] is None else c['calmar'] - b['calmar'], '{:+.3f}')} | {_f(b['dd'], '{:.2f}')} → "
                         f"{_f(c['dd'], '{:.2f}')}% | {_f(c['h1'], '{:.3f}')} / {_f(c['h2'], '{:.3f}')} | {b['n']} → {c['n']} | {_f(b['win'], '{:.1f}')} → "
                         f"{_f(c['win'], '{:.1f}')}% | {_f(b['mean'])} → {_f(c['mean'])}% |")
        L.append("")
        for k in IDS_B:
            s = B["stage1"][k]
            ra, rb = s["routes"]["A"], s["routes"]["B"]
            o = B["pools"][k]
            L.append(f"- **{k}「{NAMES[k]}」**：因事件多卖出 {B['trig'][k]} 笔；路线 A " + " ".join(f"{x}{'✓' if ra[x] else '✗'}" for x in ("A1", "A2", "A3", "V4"))
                     + "；路线 B " + " ".join(f"{x}{'✓' if rb[x] else '✗'}" for x in ("B1", "B2", "B3", "V4")) + "；池子 "
                     + "；".join(f"{q} {o[q].get('changed', 0)} / {o[q].get('n', 0)}（胜率差 {_f(o[q].get('dwin'))} pp、每笔差 {_f(o[q].get('dmean'), '{:+.3f}')} pp"
                                f"{'；★ 带事件那次的 X6 与 nb 不同 ' + str(o[q]['nb_diff']) + ' 笔' if o[q].get('nb_diff') else ''}）"
                                for q in B_POOLS) + f" → **{B['verdict'][k]}**")
            ds = B["describe"][k]
            L.append(f"  改卖的笔：{ds['sold'].get('n', 0)} 笔、胜率 {_f(ds['sold'].get('win'), '{:.1f}')}%、每笔 {_f(ds['sold'].get('mean'))}%；B4 持有期内出现状态："
                     + "、".join(f"{e} {v['held']} 笔（成交日已在 {v['at_fill']}）" for e, v in ds["held"].items()))
        L += ["", "### B-买分组（只描述；不作为规则）", "", "| 样本 | 分组 | 笔数 | 胜率 | 每笔（95%） |", "|---|---|---|---|---|"]
        for s, v in B["buy_groups"].items():
            for gk in ("g1", "g2"):
                for name, q in v[gk].items():
                    ci = (q.get("ci") or {}).get("mean")
                    L.append(f"| {s} | {G2_NAMES.get(name, name)} | {q.get('n', 0)} | {_f(q.get('win'), '{:.1f}')}% | {_f(q.get('mean'))}"
                             f"（{'—' if not ci else _f(ci[0]) + '〜' + _f(ci[1])}） |")
    L += ["", "## 六 与登记前个数、事前预期的对照", "", *compare_lines(res), "",
          "## 七 局限和结论上限", "",
          "（全文见 scripts/month_up_dip_study.py 文件开头十三；这里是摘要）", "",
          "1. 幸存者偏差：Z / E / J / W 用今天的名单，只有 J2 是时点成员；J2 事件后 h 天内退市的票收益是 NaN、被丢掉 → 偏乐观。",
          "2. 价格口径：Yahoo 拆股 + 分红调整、J-Quants 只调拆股 → J / J2 的标签只是近似于面板（J-Y 量化这个差）；研究删掉工作日成交量 0 的行、"
          "面板保留 → 少数行的标签不同（登记前个数见文件开头十三-2）。",
          "3. 热身：J / J2 约 2018-10〜11 起才有事件（缺 2017〜2018 年中），Z 约 2002 年初起。",
          "4. 主口径 as-of：偏离「只用已完成 K 线」的约定；部分 K 线的标签在周内 / 月内来回翻，冷却期只能部分处理；fragile 行只做敏感度。",
          "5. 重叠与扎堆：不同票同一天、相邻月份仍然相关，按月聚类只处理一部分；事件可能集中在 2008、2020-03、2024-08、2025-04"
          "（四节另报一起跌 / 自己跌、年份、去掉事件最多的 3 个月、按季度聚类）。",
          "6. 基准与成本：基准是同段等权平均（含自己），不是指数；事件研究税前、不扣滑点、不处理涨停（A2 处理了）。",
          "7. 「在跌」只按面板标签，没有覆盖跌幅、连跌、MACD 等写法，不能外推到这些写法。",
          f"8. B 部分样本小（B4 {sum(B4_TRADES_REF.values())} 笔 = " + " / ".join(f"{e} {B4_TRADES_REF[e]}" for e in N225_ERAS)
          + "，单个年代一笔约等于 2〜4 pp 的胜率；J 有几笔在热身期、标签不全）；W 池子的成交用 21y 价格、标签用 27y 价格，有很小的差。",
          f"9. 缓存：冻结在 --prep 时（2026-10-08）的状态，用 DATA_FP {DATA_FP} 核对；DATA_FP 只覆盖 A 部分各段，B 部分的输入（21y 行情、Zx、宏观因子）"
          "不在指纹里，靠先决条件 2（B4 重算 = 参照）与 5 核对；登记前第一次试跑刷新过宏观因子缓存（照实记在文件开头十三-9）；W 实际进面板 667 只。",
          "10. 多重检验与数据反复使用：判定只有 6 个，其余都只描述；Z / E / J / W / J2 已被以往很多研究用过（文件开头九）。", "",
          "结论上限：A 部分最多「买点成立 / 卖点成立」，只回答问题、不改交易；B 部分最多「更好候选」，"
          "进模拟盘 / 执行器要用户明确同意。模拟盘不变。", "",
          f"用时 {res['elapsed_s']} s。只有汇总统计，没有个股名单和原始行情。非投资建议。"]
    return "\n".join(L) + "\n"


def _jsonable(o):
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    return str(o)


def out_dir() -> Path:
    """结果只写在 var/out（不能换目录：换了就能绕过「只运行一次」）。"""
    from qbreak import paths
    return paths.PROJECT_ROOT / "var" / "out"


def run_guard(d: Path) -> None:
    """只运行一次：.json / .partial.json / .md、以及写到一半留下的 .json.tmp / .partial.json.tmp（write_json 先写 .tmp 再换名；
    写到一半被杀 / 磁盘满时里面已经有结果数字）任何一个已经存在 → 停（中途出错留下的也算跑过）。"""
    for f in (OUT_JSON, OUT_PARTIAL, OUT_MD, OUT_JSON + ".tmp", OUT_PARTIAL + ".tmp"):
        if (d / f).exists():
            raise SystemExit(f"{d / f} 已经存在（只运行一次；中途停下的也算跑过：照实记录、由用户决定，不重跑）→ 停")


def write_json(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=_jsonable), encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prep", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    t0 = time.time()
    say = lambda s_: print(f"{s_}；{time.time() - t0:.0f}s", flush=True)     # noqa: E731
    if a.prep:
        out = prep(say, a.workers)
        print(json.dumps(out, ensure_ascii=False, indent=1, default=_jsonable))
        return 0
    d = out_dir()
    run_guard(d)
    d.mkdir(parents=True, exist_ok=True)
    res = run(say, a.workers, save=lambda r: write_json(d / OUT_PARTIAL, r))
    write_json(d / OUT_JSON, res)                                            # 先写 json（md 生成出错也不丢结果）
    md = report(res)
    (d / OUT_MD).write_text(md, encoding="utf-8")
    (d / OUT_PARTIAL).unlink(missing_ok=True)
    print(f"完成：{d / OUT_JSON}、{d / OUT_MD}（判定和数字只在文件里）", flush=True)   # 终端只报「完成」（文件开头十一）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
