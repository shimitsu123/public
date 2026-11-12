"""nkt_study.py — 日経转弱的日子，把持仓的吊灯止损从 3×ATR 收到 2×ATR（ID = NKT；登记版：规则、代码、测试与登记前个数一起提交，
之后不改规则、只运行一次）。

来由：用户 2026-10-08 从推荐清单选「两个都做」：① 本研究（推荐清单第 1 项）；② 一直放宽卖法的账户级检验（k4 / 90 天，〔62〕②；另行登记、
各只运行一次、不做组合，两者方向相反）。胜率诊断（var/out/winrate_diag.md，J 年代）：持有期间日経涨的那些笔胜率 69.7%、跌的 24.1% —— 那是持有期间
同期的方向，事先不知道；本研究问「收盘时已经知道的日経转弱」能不能用。以前做过、形状不同：按信号日的状态给整笔定参数（第十一个循环 JRT / X2T / HWT，
第 5 轮都不过）、按局势每月切换卖法（model_switch_study 3ae491f / baa3823，12 个检验都不过）、外部事件触发清仓（FXX、SEX）、只升不降的吊灯（推荐清单
第 6 项 CHR，未做）。「持有中每天按大盘状态更新、只收紧距离」以前没有做过。已知的不利证据（事后、只描述）：model_switch_study「一直收紧」（k 2、60 天）
g = −0.600 %/笔（t −2.66）、「一直放宽」+0.420、「一直 B3」+0.180；loop11_cycle_describe 除金融地产外每一类里收紧的每笔都最低；NKT 的日历剂量约为
一直收紧的 26〜35% → 没有择时信息的话，预期每笔是负的。所以关键不是「收紧好不好」，而是：在日経转弱的那些日子收紧，比随便挑日历上同样多、同样成段的
日子收紧好多少（循环平移安慰剂）。平移保留的是日历剂量（weak 的天数、成段结构），不是持仓剂量（真正换了卖点的笔数）→ 另加「每次换卖点的平均差 G」，
剂量不同时结论有上限（九）。家族：卖法·大盘状态按日收紧（新家族，不属于任何研究循环、不占循环名额；判定标准借用第十一个循环的第一关）。
只是研究：不改模拟盘、执行器、例行任务、面板、策略参数、仓位、股票池、宏观阈值、牛熊分界参数。非投资建议。

二 定义
  2.1 日経状态（触发）：数据 = var/cache/idx_N225_27y.csv（Yahoo ^N225，已 gitignore，只读），读法 month_up_dip_study.read_cache_direct("^N225", 27)
      （直接读文件 + qbreak.data.validate_ohlcv；不看 TTL、不联网、不写缓存）。行 = qbreak/kline_series.clean_rows(df, drop_zero_vol=False)：指数不删
      成交量 0 的行（规格阶段核对：保留 669 行，1999〜2002 与 2017〜2020 零星，都是真实价格行；删掉会断掉 Z 年代的标签）；断言日期递增、不重复、
      没有周六 / 周日；删掉不是 JPX 交易日的行（规格阶段核对：1 行，2018-07-16）。标签 = kline_series.labels_partial(rows)["D"]，即每一行 t 收盘时的
      kline.trend(rows[:t+1])（逐位相同、不偷看）。「下降」= 收盘 < MA20、MA20 比 3 根前低、MA5 < MA20 三条同时成立（SLOPE_BARS = 3）。
      weak_t = (D_t == −1)；震荡 / 上升 / NA（前 22 行）都不是 weak；fragile（近平局）行照用、只计数。
      代码与环境指纹（--prep / --run 开头核对，不一致就停）：KLINE_SRC_SHA（kline.trend / bars / ohlcv 源码 + (SLOPE_BARS, MAS)，与 month_up_dip_study
      同一个值）；KS_SRC_SHA（kline_series.labels_partial / _rule / _lag / clean_rows / _closed_weekdays 的源码 + (NEED, SB, TIE_EPS)）；
      CP_SRC_SHA（scripts/candle_portfolio.py 整个文件内容的 sha1 前 16 位；钩子「改前 vs 改后」只在登记时核对一次，--run 靠这个指纹保证是同一份
      candle_portfolio.py；它管不到钩子能不能生效所依赖的 qbreak/unified.py（_check_exits 在日本市场的离场循环里经 self._p(t) 取离场参数）与 MixEngine 的
      父类链 → --run 第 2 步另外重做正向对照 R1 / R2，不过就停（三⑤⑥）；测试里这三个指纹只测机制，登记值的核对只在 --prep / --run）；
      QB_DROP_ZERO_VOL 必须是 "1"（开头 setdefault；外面设成别的值也会停；它只影响个股与池子的数据，指数用 drop_zero_vol=False，不读这个环境变量）。
  2.2 时点（as-of）：第 d 天（日本个股的交易日）收盘后的离场判断，用 weak 在「日経最后一个 ≤ d 的行」上的值：有同一天的行就是当天收盘（执行器次日
      07:40 才决策 → 不偷看）；日経那天缺行 → 用前一个日経交易日（只会更旧；规格阶段核对 2000〜2026 缺 3 天，最旧 4 个日历日）。取值不向前填补 NaN：
      index.searchsorted(dates, side="right") − 1，取那一行的值原样（= kline_series.on_days(lab, idx, fill=NaN)；不用 reindex(union).ffill()）。
      末尾语义：「≤ d 的最后一行」在序列最后一行之后会一直沿用最后一行的值 → 钩子用的 KSER 建在完整的日経日期索引上（每一行都有值：weak → 2.0，
      否则 NaN）；核对每个账户引擎**逐日推进的日子**（UnifiedEngine.run(start, end) 推进、记进权益历史的日子 = gidx 在 ctx 的 [start, end] 之内的部分；
      钩子只在这些日子的收盘离场判断里读 KSER）：≥ KSER 首日的日期 as-of 取到的行最旧不超过 MAX_STALE_DAYS = 7 个日历日，超过 → 停
      （同时挡住「个股日期超出日経末日、一直沿用最后一行」）。不核对 gidx 里 end 之后的日子：核心合成价（1545 / 1482）建在实时 ^N225 的日期上、
      不受冻结缓存管，会一直延到运行当天，那些日子引擎从不推进、对结果没有影响（只数个数 gidx_not_stepped）。单笔层同样按个股日期 as-of 取 weak，同样核对最旧天数。
  2.3 吊灯线（按天重算，和现行 X6 一致：qbreak/unified.py 与 qbreak/exit_forward.chandelier_flags）：peak_t = max(买入价, 买入日起每天的最高价)（含当天）；
      收盘 c_t < peak_t − k × ATR14_t → 当天收盘排队、第二天开盘卖；线每天重算（ATR 变大时线会往下走，不是只升不降）。NKT：k_t = 2 if weak_t else 3，
      同样每天重算、没有记忆（weak 的日子线往上跳 1 × ATR，恢复后退回 3 × ATR 的位置；「只升不降」是 CHR，不混进来）。因为 ATR ≥ 0，
      c < peak − 3·ATR 一定也满足 c < peak − 2·ATR → NKT 的吊灯旗子 = ch3 | (weak & ch2)，ch_k = chandelier_flags(f, kk, px, k)。从成交日当天收盘起适用；
      判断顺序沿用 X6：放量阴线 → 死叉 → 吊灯 → SAR → 最长持有（单笔引擎 engine.run_backtest 同一顺序）→ 单笔层的 ch3 | (z & ch2) 与账户层「k 每天重算」是同一件事。
  2.4 只收紧、其余照 B4：只动吊灯这一条的倍数，k_eff = min(这笔自己的 k, 当天的值)；这笔 k = 0（没有吊灯）→ 不加吊灯 → 不新增卖出理由；当天的值必须 > 0
      （有限且 ≤ 0 → ValueError：min(k, 0) = 0 等于关掉吊灯，是放宽）。离场原因仍记 chandelier（单笔引擎借用死叉列，原因 "dead_cross" 统一改记 chandelier）。
      其余照 B4（= B3 + TBF；模拟盘规则指纹 1241753c8f2529c6）：止损 −7%、跟踪 12%、止盈 +25%、放量阴线、最长 60 个交易日；买哪只、什么时候买、仓位、
      核心 / 闲置资金都不变。只对日本个股（market == "JP" 且不是核心 ETF）；核心 ETF（1545 / 1482 / 1655 / 2845）和美股不受影响。
三 研究引擎钩子（scripts/candle_portfolio.py；缺省不启用、逐位不变）：asof_pos / asof_take；MixEngine.CHAND_K_DAY（__init__ 校验值并 as-of 到 gidx；
   _check_exits 只在日本市场那次离场判断里设 _k_cap，finally 清掉；_p 在 cap < 这笔的 k 且 k > 0、非核心、日本个股时返回只换吊灯倍数的副本，否则原样返回
   同一个对象）；make_runner.run(..., chand_k_day=None)（设类属性，在已有的 finally 里复原）。接法 L6.run(W, e, em_tick=C9.tick_of(S.ticker, S.date, tbf[e]),
   chand_k_day=KSER)（L6.run → loop2_common.merge_over → loop_common.run → leap_confirm.run → make_runner.run(**kw)）。
   缺省逐位不变的证明与正向对照（六层）：① 代码（缺省只多 None / 空缓存与 is None 判断，_p 返回同一个对象）；② 改前钉子（tests/test_candle_portfolio_kday.py H0：改钩子
   之前用改前代码算出 4 个合成场景的规范化 sha256；改后缺省 / 显式 None / 全 NaN / 全 3.0 / 全 4.0 / 数据开始前 2.0 六种都要等于它）；③ 改前 vs 改后（真实数据，
   --prep，只打印 ✓ / ✗：git show PRE_REV 的旧文件写到临时目录 → 子进程用同一个 python、cwd = quant_breakout/、冻结缓存、bullbear_study.load 换成读主进程
   存下的同一份 pickle，先把旧源码以模块名 candle_portfolio 载入（__file__ = 仓库里的真实路径），算 Z / E / J 的 B4 成交表与权益历史的规范化 sha256；
   主进程用改后的代码（钩子缺省）算同样的 sha256 → 三个年代逐个相同才 ✓）；④ 接线（--prep 与 --run）：B4 重算 = 已公开参照（trendline_study.same_b4，
   B4_TOL = 0.005）；W1〜W5（缺省 / 全 NaN / 全 3.0 / 全 4.0 / 1999-12-01 之前的行 2.0、之后每一行 NaN；W2〜W5 都建在完整日経索引上）× Z / E / J 的账户：
   loop9_common.KEYS 8 个键都与 B4 完全相同（两边 None / NaN 算相同），另外 W2〜W5 的成交表与权益历史的规范化 sha256 都等于 W1（按引擎记录的精度逐位；
   --prep 记 hook_wiring_sha，--run 第 2 步也要求）；⑤ 正向对照 R1（--prep 与 --run 第 2 步，只记 ✓ / ✗）：全 2.0 的钩子账户（完整日経索引）=
   「PARAMS_TD 给每个信号 k 2」的账户（loop11_common.build_params_td，菜单 k 2 / 60 天、fill_dates(days_of(W, e), S.date)，带 TBF 的 em_tick），8 个键
   完全相同，另外两边的 sha256 也相同（R1_sha）；⑥ 正向对照 R2（--prep 与 --run 第 2 步，只记 ✓ / ✗；日期对齐）：只用 B4 已有的成交、不碰真实 z —— 选一笔 B4 成交
   与它持有期（成交日〜卖出日前第二个交易日）里收盘落在 [peak − 3·ATR, peak − 2·ATR) 的一天 d（r2_pick 的条件：d 与下一天 d′ 都是日経的行、也是引擎
   gidx 里相邻的两天，d′ 不是整天跌停，d′ 收盘在 2·ATR 线之上）：KSER 只在 d 那一行是 2.0 → 这笔在 d′ 开盘卖、原因 chandelier；KSER 只在 d′ 那一行
   是 2.0 → 卖出日与原因不变。两条都对才 ✓（钩子整体早一天 / 晚一天都会让其中一条 ✗；W1〜W5 与 R1 的序列与时间无关，查不出日期错位）。
   --prep 的 ✗ → 停、修好再登记；--run 第 2 步的 R1 / R2 ✗ → 停、不写任何输出（还没碰真实 z、没写 partial，属于运行前可修正）：W1〜W5 的序列本来就
   不改变结果，钩子悄悄失效（例如 unified.py 重构后离场循环不再经 _p 取参数）时 B4 = 参照与接线照样全部 ✓，只有正向对照看得出来。
   规范化 sha256 = 列名排序、浮点 float.hex()、日期 ISO、逐行 JSON（canon_sha；不用 pandas 自带的哈希）。比的是引擎记录下来的成交表与权益历史，
   引擎记录时已经四舍五入（成交价 1e−4、pnl / 权益与现金 0.01 円、ret_pct 1e−3、pnl_jpy 1 円、汇率 1e−4；qbreak/unified.py）→ 本文件说的「逐位」都是
   「按引擎记录的精度逐位相同」：比四舍五入后的 8 键细得多，但不是浮点逐位（钩子真正起作用时会改卖出日，是离散的变化，一定看得出来）。
   每跑完一个账户断言 MixEngine.CHAND_K_DAY is None（--prep 与 --run）。
四 样本与数据：--prep / --run 开头 month_up_dip_study.freeze_cache()（不联网下载行情、不写行情缓存）。账户层不是完全冻结的（照实写）：
   candle_portfolio.make_runner 里的 bullbear_study.load（牛熊与汇率）直接走 yfinance，冻结补丁管不到 → 不改这条通路，靠「B4 重算 = 参照」核对；
   live_fp() 给 bullbear_study.load 包一层，只记录、不改变返回值（代码、首日、末日、行数、round(Close 合计, 2)）；--prep 记下指纹并核对 ^N225 实时序列与
   缓存在重叠日期上 Close 一致（|相对差| ≤ LIVE_TOL）的比例（写进 PREP_COUNTS；比例 ≥ LIVE_MIN = 0.99 才 ✓ —— 这是唯一能看出触发序列日期错位的量）；
   --run 同样记下比例（json live_overlap，md 开头与登记前对照），不作为停止条件。
   B4 = month_up_dip_study.b_load()（loop10_common.load() + trendline_study.tbf_gates(W)）；账户 = C9.acct(C9.run_block(W, e, tbf[e]))；窗口 Z 2001-01〜2006-09 /
   E 2006-10〜2016-09 / J 2017-01〜2026-09-30。已公开参照（var/out/turn_shape_combo.json cand.TBF）：Calmar Z 1.209 / E 0.627 / J 0.677，个股笔数 28 / 34 / 52，
   胜率 75.0 / 50.0 / 51.9%（E 重算 0.628 是缓存刷新后的漂移，在 B4_TOL 之内）。比较用的 base 一律是本次运行重算的 B4；参照只用来核对。
   四个池子（假想单笔）= B4 会买的信号：N（日経225）= Z / E / J 各年代 C9.signals(W, e) 里 CA.apply_c(W["c_fold"][e], signals)（C 留一年代）保留、
   且 TBF 没挡的，行情 W["SM"][e]["fa"]，三个年代合成一个池子；W = kept_pool(W, "W", "E") 且 TBF 没挡（行情 W["SM"]["W"]）；Jx = kept_pool(W, "Jx", "J")
   且 TBF 没挡（W["SM"]["J2"]）；Zx = kept_pool(W, "Zx", "Z") 且 TBF 没挡（W["SM"]["Zx"]）（= month_up_dip_study.pool_signals）。池子之间有重叠也不去重
   （--prep 数 N 与 W / Jx / Zx 共有的票与（票, 信号日））。成本 = loop11_common.bt_rt() 的 rt（登记 RT_REF = 0.1496 %，差 ≥ 5e−5 就停）。
   数据指纹 DATA_FP（--prep 算出写进常数，--run 不一致就停；month_up_dip_study.data_fp 同一个哈希）：日経 (首日, 末日, 行数, round(Close 合计, 4), weak 行数,
   NA 行数, fragile 行数)；每个池子 ("sig", 池子, 信号数, 排序后 (票, 信号日) 列表的 sha1)；每个池子用到的每只票 (池子:行情键, 票, 首日, 末日, 行数,
   round(Close / Open / High / atr 合计, 4))。B4 账户的输入不在指纹里，靠先决条件（B4 重算 = 参照）核对。
五 第一步：信息检查（单笔配对 + 循环平移安慰剂）
  5.1 每个信号的配对：X6（基准）nb = turn_shape_combo.single_with_events(t, df, d, W["p0"], bt, rt, None)[0]（吊灯 k 3、最长 60 天；130 根内没卖掉 → NaN）；
      NKT = 同一笔（同一个成交日、同一个价），吊灯旗子换成 ch3 | (weak & ch2)，其余同 X6。配对集合 = nb 有值的信号（NKT 只会更早卖 → 与 weak 序列无关，
      每次安慰剂都是同一批）；某个信号任一个查表结果是 NaN（预期 0 个）→ 对所有序列都剔除，计数写进 md。
  5.2 查表（精确）：每个信号按 single_with_events 的同一做法：f = df.copy()，entry 只在信号日；先用 W["p0"] 跑 exit_forward._one(t, f, p0, bt, d, end) 定成交日 kk，
      px = 成交日开盘 × (1 + 滑点)；离场参数 pv = replace(p0, max_hold_days=60)；end = df.index[min(len(df) − 1, pos + END_BARS)]；ch3、ch2；
      候选触发日 C = {t : kk ≤ t ≤ 信号日 + 130 根，ch2_t 且非 ch3_t}（升序）。对 C 里的日子依次跑 _one(t, f.assign(dead_cross=ch3 | onehot(t)), pv, bt, d, end)
      → r_t；一旦 r_t 的（成交日、卖出日、卖出价）与 X6 相同，之后的 t 全记成 nb、停止（加一个旗子都不改变结果 → 那天收盘已经不持有或已排队离场；
      engine.py 排队之后每天重新判定只改原因、不改卖出的时间和价格）。任一 weak 序列 z 下：τ(z) = C 里第一个 z(t) = 1 的日子；NKT 净收益 = r_τ；
      没有这样的日子 → nb（证明：ch3 | (z & ch2) 与 ch3 | onehot(τ) 在 τ 之前逐日相同、τ 当天都为真；τ 之后的旗子只会重复排队、价格相同 → 两笔完全相同）。
      changed（换了卖点）= NKT 那笔的卖出日 ≠ X6 的卖出日，或 |nv − nb| > LOOKUP_TOL = 1e−9（不用 np.isclose：它带 rtol）。
      核对：--prep（只打印 ✓ / ✗ 与一致的比例，不对真实 z 取查表值）：(a) nb = single_with_events(…, None)[0] 逐位相同；(b) W / Jx / Zx 的 nb 与 kept_pool 的 net
      一致（|差| < BASE_MATCH_TOL = 1e−6）的比例 ≥ BASE_MATCH_MIN = 0.99；(c) 查表 = 直接跑：SYNTH_Z 的 6 个非真实序列（z ≡ 0、z ≡ 1、交替（日経行号偶数为 1）、
      rolled(w, grid[0])、rolled(w, grid[199])、rolled(w, grid[399])），全部池子的全部配对信号上，查表与直接用 ch3 | (z & ch2) 跑一次相同（|差| < 1e−9），
      changed 也一致。--run：(a)(b) 重做（只涉及 X6 基准；不过 → 停、不写任何输出，可以做「运行前修正」）；(c') 真实 z 的查表 = 直接跑（第一次碰真实 z；
      不过 → 停、不出判定、照实记下，这次运行算用掉）。查表只放在内存里，不落盘。
  5.3 统计量（判定一律用未四舍五入的 numpy 值）：每个池子 n_p = 配对数；d̄_p = mean(nv − nb)（含没换卖点的配对，pp/笔）；c_p = changed 笔数；x_p = c_p / n_p；
      g_p = Σ(nv − nb) / max(c_p, 1)（每次换卖点的平均差，没换 → 0；恒等式 d̄_p = x_p · g_p）；dw_p = 胜率差（pp）。T = 四个池子 d̄ 等权平均；G = 四个 g 等权平均。
      loop11_common.pair_stats 会先四舍五入 → 只用于展示；判定与第一关的 other 都用未四舍五入的值。
  5.4 安慰剂：日経状态整段循环平移。weak 数组 w = 日経全部行（NA → False）；平移 s：w_s = np.roll(w, s)（w_s[p] = w[(p − s) mod N]），再按 2.2 的 as-of 位置
      映射到个股日期。保留：weak 总天数与成段结构（日历剂量）；打断：它与真实大盘涨跌的对应，以及 W2 信号时点、个股回撤进吊灯带、账户层量化状态层与 weak 的
      耦合（审查只数天数的证据：信号后 60 行 weak 占比的真实值都低于平移中位）→ T 混着「剂量 × 每次效果」→ 另加 G；剂量不同时加写死的限定语（九）。
      整段平移（不照第九个循环的年代内平移）的理由：年代内平移也对不上剂量（Z 的真实值低于全部年代内平移）；N 池子跨三个年代、W / Jx / Zx 各在一个年代，
      共用一个平移量 T_s 与 G_s 才一一对应；剂量差由 G 与九的上限处理。代价：Z 与 J 的日历剂量互相混（D4 报告）。平移量 = 确定网格：MIN_SHIFT = 250 行，
      N_SHIFT = 400，s_k = MIN_SHIFT + floor(k × (N − 2·MIN_SHIFT) / (N_SHIFT − 1))，k = 0〜399。相邻平移高度相关（照实写）→ corr_len：沿网格的自相关 ρ_k，
      τ = 1 + 2 Σ_{k≥1} ρ_k（加到第一个 ρ_k ≤ 0 或 k = M/4 为止），K_eff = M / τ，L = τ × 步长；md 报 L、K_eff、经验 p 与最小可达 p ≈ 1 / (K_eff + 1)。
  5.5 判定（verdict_info，纯函数，从上往下第一个成立的就是结论）：1 任一池子 c_p < MIN_CHANGED = 20 →「有池子换卖点的不到 20 笔」；2 任一 d̄_p / g_p / T / G
      不是有限值，或 T_s / G_s 有非有限值、个数不是 400 →「有算不出的」；3 四个 d̄_p 都 ≤ EPS = 1e−12 →「四个池子都没变好」；4 四个 d̄_p 不是都 > EPS →
      「四个池子方向不一」；5 T ≤ np.quantile(T_s, 0.95) + EPS →「同方向，但不超过平移的 95 分位」；6 G ≤ np.quantile(G_s, 0.95) + EPS →「超过平移的 95 分位，
      但每次换卖点的平均差不超过」；7 其余 →「信息检查通过 → 进账户层」。剂量限定（不改判定）：任一池子真实 c_p 落在自己 400 个 c_p,s 的 DOSE_Q = (0.05, 0.95)
      分位之外 → dose_outside；判定是第 5 条及之后时加九的限定语。另报（不参与判定）：p_T = (1 + #{T_s ≥ T}) / 401（p_G 同理）、K_eff / L / 最小可达 p、
      检出力 MDE_T = q95(T_s) − 中位(T_s)（MDE_G 同理）、每个池子 d̄ / g / c 在自己平移值里的分位。信息检查不过 → 账户层不计算。
六 第二步：账户层第一关（只在信息检查通过时）：候选 = C9.acct(L6.run(W, e, em_tick=C9.tick_of(S.ticker, S.date, tbf[e]), chand_k_day=KSER))；base = 本次运行
   重算的 B4。几乎不触发：Z + E + J 候选里「（票, 成交日）也在 B4 里、但卖出日更早」的笔数 < MIN_TRIG = 10 →「几乎不触发」。第一关 = research_loop11.stage1(cand,
   base, other={W, Jx, Zx: {changed: c_p, dwin: dw_p, dmean: d̄_p}}（未四舍五入、真实 z）, lenses=None, posthoc=True)：路线 A（三个年代 Calmar 差合计 ≥ +0.03、
   每个年代 ≥ −0.02、回撤不深 2 pp 以上、两半合计都 ≥ −0.02、合起来胜率差 ≥ −2.0 pp）或路线 B（合起来胜率差 ≥ +2.0 pp 且每笔差 ≥ 0、每个年代胜率差 ≥ −2.0 pp、
   账户不变差）；V4 W 与 Jx 同方向、V5 不适用、V6 适用（posthoc：动机来自 J 年代胜率诊断与 model_switch_study；W / Jx / Zx 已被用过）→ Zx 也要同方向。
   照实写：V4 / V6 与信息检查用的是同一组数，不是独立证据（信息检查通过时路线 A 的 V4 / V6 自动成立）；第一关真正新增的只有 A1〜A3 / B1〜B3。
   结论只有三种：「几乎不触发」/「第一关不过」/「第一关通过（要另行登记第二关）」。
七 第二关（第一关过了才做；另行登记 = 新的提交，之后只运行一次；本文件不实现，只写死设计）：账户层的日経状态整段循环平移，网格 shift_grid(N, M)，
   M = research_loop11.placebo_n(routes)（一条路线 400、两条 800）；每个 s 跑 Z / E / J 三个候选（KSER 换成平移后的序列，同样建在完整日経索引上），base = 同一次
   运行重算的 B4；每个 s 记路线统计量 r_s（A = Calmar 差合计，B = 合起来胜率差）、剂量 D_s（同 trig_count）、只描述 B4 持仓日里 weak 的个数。第一关过了的路线 r
   要三条同时成立：(i) stage2 原始：候选严格大于 M 次最大值（有算不出 → 不过）；(ii) 扣掉剂量：M 次上最小二乘 r_s = a + b·D_s（D_s 全相同 → b = 0），
   候选残差 e = r − (a + b·D) 严格大于 max(e_s) + EPS；(iii) 不外推：候选 D 在 [min D_s, max D_s] 之内，否则「外推：第二关不下结论（不过）」。
   误报约 1 / (K_eff + 1) ≈ L / N（不宣称 1/401，也不宣称两条路线合计约 2/801）。两关都过 =「更好候选」→ 只报告给用户；进模拟盘 / 执行器要用户明确同意。
八 只描述（不能升级为判定；信息检查不过时只算 D1〜D7）：D1 每个池子的配对数、c、x、两边胜率与胜率差、每笔平均差与中位差、g、换卖点里变好 / 变差的比例与
   平均差；D2 X6 净收益 ≤ −7%（BIG_LOSS）的配对数与它们的 NKT − X6 平均、两边净收益 5% 分位与最小值；D3「一直 k 2」（z ≡ 1）每个池子的 d̄、g、胜率差
   → 0（X6）/ NKT / 一直 k 2 三档；D4 安慰剂分布（每个池子与 T、G 的平移中位 / 5% / 95% / 最大与真实分位；持仓剂量 c 的分布、x、g；剂量回归 OLS
   d̄_p,s = a_p + b_p·x_p,s 的真实残差与分位（真实 x 在平移范围外 → 外推）；日历剂量（成交日起 60 行 weak 占比）真实与平移分布、平移后各窗口 weak 占比；
   corr_len 的 L 与 K_eff）；D5 N 池子按年代与按年份的配对数、d̄、g；D6 V 形反弹窗口（按已知的市场历史事后挑选，md 标「事后」）V1 2008-09-15〜2009-06-30、
   V2 2020-02-20〜2020-06-30、V3 2024-07-11〜2024-09-30、V4 2025-03-27〜2025-05-30：成交日在窗口里的换卖点配对数与平均差；D7 换卖点配对按 X6 原来的离场原因
   （chandelier / stop / max_hold / 其它）分组的个数与平均差，按信号日当天是否 weak 分组的 d̄；D8（只在账户层计算时）每个年代因 NKT 提前卖出的笔数、这些笔在
   B4 / 候选里的胜率与每笔、平均持有天数、离场原因构成、逐年收益差。
九 结论用语（写死；md〇 按判定取这一句）：见常数 VERDICT_SAY；剂量限定语 DOSE_NOTE（dose_outside 且判定是 5.5 第 5 条及之后、或是账户层三种结论、
   或是「信息检查通过，账户层出错」（STOP_ACCOUNT：也是信息检查通过之后才有的结论）时加在后面；= DOSE_LABELS）；
   {mde_t} / {mde_g} 保留 3 位小数。
十 多重检验、数据复用、事后：信息检查 1 个（单侧 5%；T 与 G 两条都要过、四个池子都要 > 0 → 实际误报低于 5%）；账户第一关 1 个；第二关另行登记（误报约 L / N）。
   Z / E / J、W / Jx / Zx 已被第一〜十一个循环、model_switch_study、trendline_study、month_up_dip_study 反复用过；X6（k 3）本身是在 E / J 上挑出来的 →
   池子不是没看过的数据；信息检查的防线是平移安慰剂（日历剂量与成段结构相同），不是样本外检验。posthoc = True。
   登记后不改：k 2 / 3、触发定义、as-of 与末尾语义、MAX_STALE_DAYS、END_BARS 130、MIN_SHIFT 250、N_SHIFT 400、0.95、判定顺序与 T / G 的定义（四池等权、
   g 的 max(c, 1)）、DOSE_Q、MIN_CHANGED 20、MIN_TRIG 10、四个池子的组成、RT、B4 参照与容差、BASE_MATCH_MIN 0.99、LOOKUP_TOL、SYNTH_Z、V 窗口、BIG_LOSS、LIVE_TOL、
   LIVE_MIN、R2_MARGIN、WXA_REQUIRED（只能由运行前修正改 False）、最旧天数的核对范围（逐日推进的日子）、第二关的 (i)〜(iii)。运行前发现必须改的：只能在看到任何结果之前另交「运行前修正」提交（写明没有算出任何结果）。
十一 登记前个数（--prep：只数个数，不算任何收益）：日経行数 / 成交量 0 的行 / 非 JPX 日 / 第一个有标签的日子 / fragile、各窗口 weak 占比与成段、缺的 JPX 交易日、
   最旧天数；池子信号数（N 分年代与合计、W 303 / Jx 606 / Zx 334）、有行情的个数、信号日当天 weak 的个数、N 与 W / Jx / Zx 的重叠；剂量（不跑离场模拟，只看
   价格旗子，px = 下一行开盘 × (1 + 滑点)，不管跳空过滤）：(a) 日历剂量 [成交日, 成交日 + 59 行] weak 占比（真实与 400 个平移的最小 / 中位 / 最大、真实分位）、
   (b) 持仓剂量代理「[成交日, min(成交日 + 59 行, 第一个 ch3 日 − 1)] 里有 weak 且 ch2 非 ch3 的日子」的信号数（真实与平移的最小 / 5% / 中位 / 95% / 最大、真实分位；
   在 5〜95% 之外 → 登记节写「结论可能带剂量限定语」，不改规则）、(c) 候选触发日总数与查表实际运行次数；池子信号数 W / Jx / Zx = POOL_REF（pool_ref ✓ / ✗）；
   B4 实际成交（已公开 28 / 34 / 52 笔）里持有期
   （成交日〜卖出日前第二个交易日）出现「weak 且 peak − 3·ATR ≤ c < peak − 2·ATR」的笔数（合计 < 10 → 登记节写「账户层可能几乎不触发」）；平移网格；
   先决条件与核对的 ✓ / ✗；用时与峰值内存；DATA_FP；ID 核对（NKT 不在 research_loop11.previous_ids()、var/research_loop11.json 的做法 ID、RESERVED_IDS、
   research_registry.json、仓库全文（var/cache 与本研究自己的文件除外））。任一项 ✗ → 先修好再登记（登记前，不算运行前修正）。
十二 运行流程、只运行一次、终端不打印：--prep：冻结缓存 → check_code → 日経状态 → 载入 B4（live_fp 记录实时序列）→ 先决条件 + 接线 + 改前 vs 改后 + R1 →
   池子查表与 (a)(b)(c)（不对真实 z 取查表值，查表不落盘）→ 只数个数 → 打印 DATA_FP、PREP_COUNTS、CP_SRC_SHA；全程不算、不打印任何收益。
   --run（只运行一次）：0 不载入数据的先决（DATA_FP / PREP_COUNTS 已登记且 PREP_COUNTS 的核对全是 ✓；规则指纹 = FP；trendline_study / month_up_dip_study 的
   FP / B4_TOL = 登记值；turn_shape_combo.json 有 cand.TBF；代码指纹；QB_DROP_ZERO_VOL；输出文件都不存在；登记状态 reg_status：本研究的 SELF_FILES 已提交、
   与 HEAD 没有差别、读得到上游时已推送，同一天登记的 WXA（WXA_SCRIPT）已提交且读得到上游时已推送 —— 「两个都登记之后才运行任何一个的 --run」，
   与 wide_exit_study 的 NKT_REQUIRED 对称；用户放弃 WXA → 运行前修正把 WXA_REQUIRED 改 False）→ 1 冻结缓存 → 日経状态 → 载入 W + TBF（记实时序列
   指纹与 ^N225 一致比例）→ DATA_FP 一致 → RT 一致 → 2 B4 重算 = 参照、接线 W1〜W5（8 键 + 逐位）、逐日推进日子的最旧天数、
   正向对照 R1 / R2（重做；不碰真实 z）→ 池子查表 → nb 逐位、base_match（只涉及 X6 基准；不过 → 停、不写任何输出）→ 3 先写 partial（「已开始第 3 步」：之后被 Ctrl-C / 杀掉 / 内存不够也留下记录 = 算跑过）→ 真实 z：查表 = 直接跑
   （不过 → 停、不出判定、照实记下）→ 信息检查（真实 + 400 次平移）→ 写 partial → 4 通过 → 候选账户 → MIN_TRIG → 第一关 → 写 partial；
   不通过 → 账户层不计算 → 5 只描述 → 先写 json、再写 md → 删 partial。只运行一次：var/out/nkt_study.json / .partial.json / .md（及 .json.tmp / .partial.json.tmp）
   任何一个存在 → 停（中途出错留下的也算跑过：照实记录、由用户决定，不重跑；不能换输出目录）。第 3 步之后出错：只记异常类型名 + 代码位置，照常写出 json / md。
   第 3 步之后的异常：Exception / SystemExit 照实记下、照常写出 json / md；Ctrl-C 等（BaseException）先写 partial 再往上抛。几乎不触发时 md 的第一关
   一行写「几乎不触发 → 不下第一关结论」（stage1 只记在 json，作描述）。
   终端只有进度、个数与先决条件的 ✓ / ✗；任何判定、收益、配对差都不打印；最后只打印「完成：<json>、<md>（判定和数字只在文件里）」。
十三 输出：var/out/nkt_study.md / .json（只有汇总统计，没有个股名单、逐笔价格）。结果提交（运行后）：sim_changes 结果节、registry（kind = study、domain = 卖法）、
   research_map、HANDOFF / CHECK_TIMELINE 结果子条目（不进定期检查）、待办给出选项并标推荐。
十四 事前预期（运行前写）：「一直收紧」每笔明显为负；NKT 的日历剂量约是一直收紧的 26〜35% → 没有择时信息时 d̄ 约 −0.2〜−0.5 pp，T_s 多半整体在 0 之下；
   真实对齐的日历剂量低于平移中位，持仓剂量方向不确定 → 结论可能带剂量限定语；V 形反弹（2009、2020-03、2024-08、2025-04）里收紧会卖在低点；Z / Zx 方向最不确定，
   J 年代 weak 占比最低、改变的笔数最少。估计：信息检查通过约 10〜15%；第一关约 5%；第二关约 1%；最可能的结论是「四个池子都没变好」，其次「四个池子方向不一」。
十五 局限：样本小（B4 114 笔）；池子不是没看过的数据、Z / E / W / Zx 用今天的名单（只有 Jx 来自时点 TOPIX 1000）；平移安慰剂只处理到一阶（G 假设每次换卖点的效果
   与次数无关；Z / J 剂量互相混；K_eff 远小于 400；单侧 5%）；单笔 ≠ 账户（名额、核心 ETF、仓位与费用）；指数数据缺 3 个交易日、牛熊 / 汇率序列联网读取；
   定义单一（只用面板日K「下降」，不能外推到别的「转弱」写法）；成本只扣来回手续费 0.1496%、不扣税；采用需要改 qbreak/ 的执行器（本研究不改）；
   V4 / V6 不独立；真实 z 的查表核对只能在 --run 做（结构已在 --prep 用 6 个非真实序列核对过）。
十六 结论上限：信息检查最多「通过 → 进账户层」，有剂量限定语时最多「和随便挑日子收紧不同」；账户第一关最多「第一关通过（要另行登记第二关）」；两关都过最多
   「更好候选」。任何结果都不自动改模拟盘、执行器、例行任务、面板、策略参数、仓位、股票池、宏观阈值、牛熊分界参数；信息检查通过但账户不过 → 最多「只记结论 /
   前向记录（由用户决定）」。
实现时的解释（登记时定、没看任何结果）：规格没列的三句结论用语（查表核对不过、账户层出错、中途出错）按同一口吻补在 VERDICT_SAY；pool_eval 的位置映射放在
   查表结构里（cpos），不另传 pos_map；--prep 的「改前 vs 改后」子进程经本文件的内部入口 _pre_worker 运行（不是第三种运行模式）；ID 核对的仓库全文 = git 跟踪的
   与未忽略的未跟踪文本文件（var/cache 已 gitignore），本研究自己的四个文件（本文件、两个测试、candle_portfolio.py 的钩子说明）与 var/out/nkt_study.* 除外；
   同一天另行登记的 WXA（scripts/wide_exit_study.py 与它的测试，按名字提到本研究）与登记材料（sim_changes / registry / research_map / HANDOFF /
   CHECK_TIMELINE）里的提到只列出（repo_known）、不算重用 —— registry 的候选 ID 另有结构化核对：script 含 nkt_study.py 的条目是本研究自己的登记 /
   结果，不算重用（同 wide_exit_study.id_check）；候选 dict 与字符串两种写法都认。
   钩子的 _p 保留原来的分支与顺序，只把两处返回值交给 _k_capped（缺省原样返回同一个对象）；live_fp 另把已经 import 过、在模块顶层拿走了原函数的
   `load` 名字也换成包装（改前 vs 改后的子进程同样换成读 pickle 的版本），子进程按调用顺序逐次回放（同一个键第 n 次调用 = 主进程第 n 次取到的那份），
   这样两边的牛熊 / 汇率输入一定相同；同一个键几次取到的是否完全相同另记在 PREP_COUNTS 的 live.repeat。PREP_COUNTS = --prep 输出 JSON 的
   prep_counts（checks 的 20 项 ✓ / ✗ + 个数），--run 要求 checks 全是 ✓（PREP_CHECKS）。check_code 另核对 trendline_study.FOLD = POOL_FOLD
   （池子用的 C 那一折）。tests/test_candle_portfolio_kday.py 另加 H0b：
   子进程以真实路径载入 git show PRE_REV 的旧源码（install_old_cp，与 _pre_worker 同一个载入方式），4 个合成场景复现改前钉子。
实现审查（2026-10-08，登记前、没有运行 --run、没看任何结果）之后加的：W2〜W5 / R1 的逐位核对、R2（日期对齐的正向对照）、pool_ref、live_n225、
   最旧天数只看逐日推进的日子（不看 gidx 里 end 之后由核心合成价带进来的日子）、第 3 步碰真实 z 之前先写 partial、--run 的登记状态核对（含 WXA）、
   实时序列副本按调用顺序回放、几乎不触发时 md 不写第一关结论、--run 也记 ^N225 一致比例、check_code 核对 POOL_FOLD。
第二次实现审查（2026-10-08，登记前、没有运行 --prep / --run、没看任何结果）之后改的：--run 第 2 步重做正向对照 R1 / R2 作为停止条件（CP_SRC_SHA 管不到
   qbreak/unified.py）；「信息检查通过，账户层出错」也加剂量限定语（DOSE_LABELS 加 STOP_ACCOUNT，partial 里的那句同样）；「逐位」的说法改成按引擎记录的精度；
   测试里的代码指纹只测机制（以后合法地改了研究引擎或 kline 不让 NKT 的测试失败；--prep / --run 里的指纹核对是登记的规则，不变）。
用法：python scripts/nkt_study.py --prep（只数个数与先决条件的 ✓ / ✗）；python scripts/nkt_study.py --run（只运行一次）。非投资建议。
"""
from __future__ import annotations

import argparse
import ast
import copy
import datetime as _dt
import hashlib
import inspect
import json
import logging
import os
import pickle
import subprocess
import sys
import tempfile
import textwrap
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import month_up_dip_study as MUD                                            # noqa: E402  （只 import qbreak 的标签模块，不碰 candle_portfolio）
from qbreak import calendar_jp as CAL                                       # noqa: E402
from qbreak import kline as K                                               # noqa: E402
from qbreak import kline_series as KS                                       # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# ───────────────────────── 登记常数（登记后不改） ─────────────────────────
ID = "NKT"
FAMILY = "卖法·大盘状态按日收紧"
K_BASE, K_WEAK = 3.0, 2.0
NK_TICKER, NK_YEARS = "^N225", 27
MAX_STALE_DAYS = 7
END_BARS = 130
MAX_HOLD = 60                                                                # 单笔 X6 / NKT 的最长持有（同 single_with_events）
POOLS = ("N", "W", "Jx", "Zx")
POOL_FOLD = {"W": "E", "Jx": "J", "Zx": "Z"}
POOL_SM = {"W": "W", "Jx": "J2", "Zx": "Zx"}
POOL_ERA = {"W": "E", "Jx": "J", "Zx": "Z"}                                  # 池子各在哪个年代（N 跨 Z / E / J）
N225_ERAS = ("Z", "E", "J")
OTHER_POOLS = ("W", "Jx", "Zx")                                              # 第一关 other 只取这三个
MIN_SHIFT, N_SHIFT = 250, 400
Q = 0.95
DOSE_Q = (0.05, 0.95)
MIN_CHANGED, MIN_TRIG = 20, 10
POSTHOC = True
EPS = 1e-12
FP = "1241753c8f2529c6"                                                     # B4 = B3 + TBF 的模拟盘规则指纹
B4_TOL = 0.005
B4_REF = {"Z": {"calmar": 1.209, "n": 28, "win": 75.0}, "E": {"calmar": 0.627, "n": 34, "win": 50.0},
          "J": {"calmar": 0.677, "n": 52, "win": 51.9}}                     # var/out/turn_shape_combo.json cand.TBF（已公开）
RT_REF, RT_TOL = 0.1496, 5e-5
BASE_MATCH_MIN, BASE_MATCH_TOL = 0.99, 1e-6
LOOKUP_TOL = 1e-9
LIVE_TOL = 1e-6
LIVE_MIN = 0.99                                                             # --prep：^N225 实时与缓存在重叠日期上一致（|相对差| ≤ LIVE_TOL）的比例 ≥ 这个值才 ✓
R2_MARGIN = 1e-3                                                            # R2 选笔：收盘离两条线至少这么远（円；成交表的成交价只留 4 位小数）
SYNTH_Z =("zero", "one", "alt", "roll0", "roll199", "roll399")
SYNTH_ROLL = {"roll0": 0, "roll199": 199, "roll399": 399}                    # 网格里的第几个平移
W5_CUT = "1999-12-01"                                                       # 接线 W5：这之前的日経行 2.0、之后每一行 NaN
DOSE_ROWS = 60                                                              # 日历剂量 / 持仓剂量代理：[成交日, 成交日 + 59 行]
BIG_LOSS = -7.0
V_WINDOWS = {"V1": ("2008-09-15", "2009-06-30"), "V2": ("2020-02-20", "2020-06-30"), "V3": ("2024-07-11", "2024-09-30"),
             "V4": ("2025-03-27", "2025-05-30")}
NK_WINDOWS = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", "2026-09-30")}
JPX_FROM = "2000-01-04"                                                     # 缺的 JPX 交易日从这天数起
POOL_REF = {"W": 303, "Jx": 606, "Zx": 334}                                 # 已公开的池子信号数（--prep 对照）
B4_TRADES_REF = {"Z": 28, "E": 34, "J": 52}
STOCK_SKIP = ("1545.T", "1482.T", "1655.T", "2845.T")
SLOPE_BARS = 3
ZERO_VOL_ENV = "1"
KLINE_SRC_SHA = "65302837180f8b35"                                          # 与 month_up_dip_study 同一个值
KS_SRC_SHA = "d4668c5e520243b8"                                             # kline_series 标签代码（登记时算出）
CP_SRC_SHA: str | None = "d9552829447bc292"                                 # scripts/candle_portfolio.py 文件 sha1 前 16 位（登记时写入；钩子之后不能再改那个文件）
PRE_REV = "d0909c0"                                                         # 改钩子之前的提交
PRE_CP_SHA1 = "8f98a56d3fea506bc73821a5fe35bc49e689d04f"                    # 改前 candle_portfolio.py 的 sha1（git show PRE_REV 的内容要等于它）
DATA_FP: str | None = "4cba1912cc330a3b"                                    # --prep（2026-10-08）之后写入（登记提交里）；--run 不一致就停
PREP_COUNTS: dict | None = {                                             # --prep（2026-10-08）之后写入（登记提交里）：只有个数与 ✓ / ✗；--run 要求核对全是 ✓
    "checks": {"code": True, "b_precheck": True, "b4_same_ref": True, "exit_tick_wiring": True, "hook_wiring": True, "hook_wiring_sha": True,
               "gidx_stale": True, "single_stale": True, "pre_vs_post": True, "R1": True, "R1_sha": True, "R2": True, "nb_exact": True, "base_match": True,
               "lookup_synth": True, "pool_ref": True, "live_n225": True, "rt": True, "chand_none": True, "id_check": True},
    "nikkei": {"rows_in": 6611, "rows": 6610, "nan_close": 0, "non_jpx": 1, "dropped_dates": ["2018-07-16"], "zero_vol_kept": 669,
               "zero_vol_by_year": {"1999": 60, "2000": 248, "2001": 246, "2002": 105, "2017": 3, "2018": 3, "2019": 3, "2020": 1},
               "zero_vol_last": "2020-06-23", "first": "1999-10-04", "last": "2026-10-02", "first_labeled": "1999-11-05", "na_rows": 22, "fragile": 0,
               "weak_rows": 2012, "jpx_days_from": "2000-01-04", "jpx_days": 6553, "jpx_missing": ["2009-09-01", "2010-07-20", "2010-09-15"],
               "jpx_max_stale_days": 4,
               "windows": {"Z": {"rows": 1414, "jpx_days": 1414, "weak_share": 0.3465346534653465, "segments": 52, "seg_median": 6.5,
                                 "seg_mean": 9.423076923076923, "seg_max": 35},
                           "E": {"rows": 2447, "jpx_days": 2450, "weak_share": 0.32243563547200654, "segments": 81, "seg_median": 6.0,
                                 "seg_mean": 9.74074074074074, "seg_max": 42},
                           "J": {"rows": 2378, "jpx_days": 2378, "weak_share": 0.25862068965517243, "segments": 89, "seg_median": 5.0,
                                 "seg_mean": 6.910112359550562, "seg_max": 22},
                           "all": {"rows": 6610, "jpx_days": None, "weak_share": 0.30438729198184566, "segments": 232, "seg_median": 6.0,
                                   "seg_mean": 8.672413793103448, "seg_max": 42}}},
    "pools": {"N": {"signals": 249, "with_data": 249, "paired": 245, "excluded": 0, "x6_nan": 0, "no_fill": 4, "sig_weak": 63, "ref": None},
              "W": {"signals": 303, "with_data": 303, "paired": 303, "excluded": 0, "x6_nan": 0, "no_fill": 0, "sig_weak": 70, "ref": 303},
              "Jx": {"signals": 606, "with_data": 606, "paired": 606, "excluded": 0, "x6_nan": 0, "no_fill": 0, "sig_weak": 131, "ref": 606},
              "Zx": {"signals": 334, "with_data": 334, "paired": 334, "excluded": 0, "x6_nan": 0, "no_fill": 0, "sig_weak": 84, "ref": 334}},
    "n_by_era": {"Z": 80, "E": 77, "J": 92},
    "overlap": {"W": {"tickers": 0, "pairs": 0}, "Jx": {"tickers": 0, "pairs": 0}, "Zx": {"tickers": 0, "pairs": 0}},
    "dose": {"N": {"signals_used": 249, "cal_real": 0.24397590361445784,
                   "cal_shift": {"n": 400, "min": 0.24866131191432397, "q05": 0.26758366800535477, "median": 0.30518741633199464, "q95": 0.3480655957161981,
                                 "max": 0.39846050870147254, "pct": 0.0},
                   "hold_real": 76, "hold_shift": {"n": 400, "min": 68.0, "q05": 86.0, "median": 103.0, "q95": 122.0, "max": 139.0, "pct": 0.00375},
                   "hold_outside": True, "cand_days": 4037, "sig_weak": 63, "sig_n": 249},
             "W": {"signals_used": 303, "cal_real": 0.2804180418041804,
                   "cal_shift": {"n": 400, "min": 0.21523652365236523, "q05": 0.24502475247524752, "median": 0.2953245324532453, "q95": 0.3725,
                                 "max": 0.4048954895489549, "pct": 0.32625},
                   "hold_real": 104, "hold_shift": {"n": 400, "min": 78.0, "q05": 97.95, "median": 121.0, "q95": 145.0, "max": 171.0, "pct": 0.11625},
                   "hold_outside": False, "cand_days": 5213, "sig_weak": 70, "sig_n": 303},
             "Jx": {"signals_used": 606, "cal_real": 0.24815887463798098,
                    "cal_shift": {"n": 400, "min": 0.2253206454282168, "q05": 0.2510067576885947, "median": 0.3015170321334988, "q95": 0.3925899875879189,
                                  "max": 0.4168528478830506, "pct": 0.0475},
                    "hold_real": 212,
                    "hold_shift": {"n": 400, "min": 176.0, "q05": 208.9, "median": 249.0, "q95": 308.04999999999995, "max": 330.0, "pct": 0.075},
                    "hold_outside": False, "cand_days": 11389, "sig_weak": 131, "sig_n": 606},
             "Zx": {"signals_used": 334, "cal_real": 0.26921157684630737,
                    "cal_shift": {"n": 400, "min": 0.19505988023952095, "q05": 0.2189496007984032, "median": 0.29191616766467066, "q95": 0.4016017964071856,
                                  "max": 0.4526447105788423, "pct": 0.285},
                    "hold_real": 126, "hold_shift": {"n": 400, "min": 91.0, "q05": 109.0, "median": 146.0, "q95": 184.0, "max": 204.0, "pct": 0.185},
                    "hold_outside": False, "cand_days": 7232, "sig_weak": 84, "sig_n": 334}},
    "lookup_runs": {"N": 992, "W": 1261, "Jx": 2767, "Zx": 1572},
    "lookup_seconds": 93,
    "b4_band": {"Z": {"trades": 28, "ref": 28, "hit": 5}, "E": {"trades": 34, "ref": 34, "hit": 7}, "J": {"trades": 52, "ref": 52, "hit": 13}, "total": 25,
                "may_rarely_trigger": False},
    "grid": {"N": 6610, "M": 400, "min": 250, "max": 6360, "step": 15.31328320802005, "unique": True},
    "window_shift": {"Z": {"real": 0.3465346534653465, "min": 0.23974540311173975, "median": 0.28995756718529, "max": 0.3910891089108911},
                     "E": {"real": 0.32243563547200654, "min": 0.2468328565590519, "median": 0.3077237433592154, "max": 0.37065794850837763},
                     "J": {"real": 0.25862068965517243, "min": 0.25483599663582845, "median": 0.31328847771236334, "max": 0.37174095878889823}},
    "stale": {"accounts": {"Z": {"n": 1414, "max": 0, "dist": {"0": 1414}}, "E": {"n": 2447, "max": 0, "dist": {"0": 2447}},
                           "J": {"n": 2379, "max": 3, "dist": {"0": 2378, "3": 1}}},
              "single": {"N": {"n": 3951, "max": 0, "dist": {"0": 3951}}, "W": {"n": 5213, "max": 0, "dist": {"0": 5213}},
                         "Jx": {"n": 11389, "max": 0, "dist": {"0": 11389}}, "Zx": {"n": 7232, "max": 0, "dist": {"0": 7232}}},
              "gidx_not_stepped": {"Z": 8595, "E": 7562, "J": 7630}},
    "live": {"fp": [["JPY=X", "2000-01-03", "2026-10-07", 6949, 790005.18], ["QQQ", "1999-03-10", "2026-10-08", 6939, 1039127.27],
                    ["^NDX", "1985-10-01", "2026-10-08", 10335, 46125445.86], ["^SOX", "1994-05-04", "2026-10-08", 8163, 11103616.91],
                    ["^SP500TR", "1988-01-04", "2026-10-08", 9765, 33872383.7], ["^GSPC", "1950-01-03", "2026-10-08", 19314, 18922395.28],
                    ["^N225", "1965-01-05", "2026-10-07", 15181, 227511379.35], ["^NSEI", "2007-09-17", "2026-10-08", 4676, 53543740.88],
                    ["^BSESN", "1997-07-01", "2026-10-08", 7211, 191956525.22], ["^N225", "1965-01-05", "2026-10-07", 15181, 227511379.35],
                    ["^GSPC", "1950-01-03", "2026-10-08", 19314, 18922395.65], ["JPY=X", "2000-01-03", "2026-10-07", 6949, 790005.18],
                    ["^N225", "1965-01-05", "2026-10-07", 15181, 227511379.35], ["^GSPC", "1950-01-03", "2026-10-08", 19314, 18922395.73],
                    ["JPY=X", "2000-01-03", "2026-10-08", 6950, 790163.5], ["^N225", "1965-01-05", "2026-10-07", 15181, 227511379.35],
                    ["^GSPC", "1950-01-03", "2026-10-08", 19314, 18922395.74], ["JPY=X", "2000-01-03", "2026-10-08", 6950, 790163.49]],
             "n225_overlap": {"n": 6610, "frac": 1.0, "ok": True, "copies": 4},
             "repeat": {"[[\"JPY=X\", \"2000-01-01\"], []]": {"calls": 4, "identical": False},
                        "[[\"QQQ\", \"1999-01-01\"], []]": {"calls": 1, "identical": True}, "[[\"^NDX\", \"1985-01-01\"], []]": {"calls": 1, "identical": True},
                        "[[\"^SOX\", \"1994-01-01\"], []]": {"calls": 1, "identical": True},
                        "[[\"^SP500TR\", \"1988-01-01\"], []]": {"calls": 1, "identical": True},
                        "[[\"^GSPC\", \"1950-01-01\"], []]": {"calls": 4, "identical": False},
                        "[[\"^N225\", \"1965-01-01\"], []]": {"calls": 4, "identical": True},
                        "[[\"^NSEI\", \"2007-01-01\"], []]": {"calls": 1, "identical": True},
                        "[[\"^BSESN\", \"1997-01-01\"], []]": {"calls": 1, "identical": True}}},
    "R2": {"picked": True, "era": "Z", "i": 0, "fire": True, "next": True, "ok": True},
    "pool_ref": {"W": True, "Jx": True, "Zx": True},
    "id": {"previous_ids": True, "reserved": True, "loop11": True, "registry": True, "registry_hits": [], "repo_hits": [],
           "repo_known": ["quant_breakout/scripts/wide_exit_study.py", "quant_breakout/tests/test_wide_exit_study.py"], "repo": True, "ok": True},
    "elapsed_s": 803,
    "peak_mem": {"self_mb": 2368, "children_mb": 2368}}
PREP_CHECKS = ("code", "b_precheck", "b4_same_ref", "exit_tick_wiring", "hook_wiring", "hook_wiring_sha", "gidx_stale", "single_stale",
               "pre_vs_post", "R1", "R1_sha", "R2", "nb_exact", "base_match", "lookup_synth", "pool_ref", "live_n225", "rt", "chand_none",
               "id_check")
WXA_REQUIRED = True                                                         # 同一天登记的 WXA 已登记（提交；读得到上游时已推送）才运行 --run（用户放弃 WXA → 运行前修正改 False）
WXA_SCRIPT = "scripts/wide_exit_study.py"
SELF_FILES = ("scripts/nkt_study.py", "tests/test_nkt_study.py", "tests/test_candle_portfolio_kday.py", "scripts/candle_portfolio.py")
OUT_MD, OUT_JSON, OUT_PARTIAL = "nkt_study.md", "nkt_study.json", "nkt_study.partial.json"
OWN_FILES = ("quant_breakout/scripts/nkt_study.py", "quant_breakout/tests/test_nkt_study.py", "quant_breakout/tests/test_candle_portfolio_kday.py",
             "quant_breakout/scripts/candle_portfolio.py")
ID_COMPANION = ("quant_breakout/scripts/wide_exit_study.py", "quant_breakout/tests/test_wide_exit_study.py")   # 同一天另行登记的 WXA（按名字提到本研究）
ID_DOCS = ("quant_breakout/var/sim_changes.md", "quant_breakout/var/research_registry.json", "quant_breakout/var/out/research_map.md",
           "quant_breakout/HANDOFF.md", "quant_breakout/CHECK_TIMELINE.md")     # 登记材料（NKT / WXA 的登记节会写到本研究的名字）

INFO_LABELS = ("信息检查不过：有池子换卖点的不到 20 笔", "信息检查不过：有算不出的", "信息检查不过：四个池子都没变好", "信息检查不过：四个池子方向不一",
               "信息检查不过：同方向，但不超过平移的 95 分位", "信息检查不过：超过平移的 95 分位，但每次换卖点的平均差不超过", "信息检查通过 → 进账户层")
INFO_PASS = INFO_LABELS[6]
ACCT_LABELS = ("几乎不触发", "第一关不过", "第一关通过（要另行登记第二关）")
STOP_LOOKUP = "查表核对不过（真实 z）：不出判定"
STOP_ACCOUNT = "信息检查通过，账户层出错：没有第一关结论"
STOP_ERROR = "中途出错：没有判定"
DOSE_LABELS = (*INFO_LABELS[4:], *ACCT_LABELS, STOP_ACCOUNT)                 # 剂量限定语只加在这些结论后面（STOP_ACCOUNT 也是信息检查通过 = 5.5 第 7 条之后才有的结论）
STARTED_3 = "已开始第 3 步（第一次碰真实 z）；没有写完 = 中途停下（算跑过：照实记录、由用户决定，不重跑）"
VERDICT_SAY = {
    INFO_LABELS[0]: "换卖点的太少，说不了什么 → 模拟盘不变",
    INFO_LABELS[1]: "有算不出的，不下结论 → 模拟盘不变",
    INFO_LABELS[2]: "日経转弱的日子收紧吊灯，四个股票池每笔都没有变好 → 不进账户层；模拟盘不变",
    INFO_LABELS[3]: "日経转弱的日子收紧吊灯，有的股票池变好、有的没有 → 不进账户层；模拟盘不变",
    INFO_LABELS[4]: "四个股票池都变好，但和随便挑同样多的日子收紧分不开：没有证据显示择时加分（检出力有限，MDE_T = {mde_t} pp/笔）→ 不进账户层；模拟盘不变",
    INFO_LABELS[5]: "四个股票池都变好、也超过随便挑日子收紧的 95 分位，但扣掉换卖点次数的差别之后不超过：可能只是剂量不同（检出力有限，MDE_G = {mde_g} pp）"
                    "→ 不进账户层；模拟盘不变",
    ACCT_LABELS[0]: "单笔层通过了信息检查（初筛），但账户里几乎碰不到 → 模拟盘不变",
    ACCT_LABELS[1]: "单笔层通过了信息检查（初筛），但账户没有变好 → 模拟盘不变",
    ACCT_LABELS[2]: "单笔层信息检查（初筛）与账户第一关都过 → 要另行登记第二关（平移 400 / 800 次、扣掉剂量），过了才是更好候选",
    # 规格没列、登记时同一口吻补上的三句（没看任何结果）
    STOP_LOOKUP: "查表与直接跑在真实序列上对不上，不出判定（这次运行算用掉，照实记下、由用户决定）→ 模拟盘不变",
    STOP_ACCOUNT: "单笔层通过了信息检查（初筛），但账户层中途出错、没有第一关结论（照实记下、由用户决定）→ 模拟盘不变",
    STOP_ERROR: "中途出错，没有判定（照实记下、由用户决定，不重跑）→ 模拟盘不变"}
DOSE_NOTE = "注意：真实换卖点的笔数在平移的 5〜95% 之外（剂量也不同）→ 只能说「和随便挑日子收紧不同」，择时与剂量分不开。"
EXPECT = ("「一直收紧」每笔明显为负；NKT 的日历剂量约是一直收紧的 26〜35% → 没有择时信息时 d̄ 约 −0.2〜−0.5 pp，T_s 多半整体在 0 之下；"
          "信息检查通过约 10〜15%、第一关约 5%、第二关约 1%；最可能「四个池子都没变好」，其次「四个池子方向不一」")


# ───────────────────────── 规范化哈希 / 指纹 / git ─────────────────────────
def _canon(v):
    """一个值的规范化表示（canon_sha 用）：None / NaN / NaT 有固定写法；布尔、整数原样；浮点 float.hex()；日期 ISO；其余 str。"""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        x = float(v)
        return "nan" if x != x else x.hex()
    if isinstance(v, (pd.Timestamp, np.datetime64, _dt.datetime, _dt.date)):
        ts = pd.Timestamp(v)
        return None if pd.isna(ts) else ts.isoformat()
    return str(v)


def canon_sha(df) -> str:
    """成交表 / 权益历史的规范化 sha256（不用 pandas 自带的哈希：云端与 Mac 的 pandas 版本可能不同）：
    列名排序；index 当作第一列 "__index__"；浮点用 float.hex()；日期用 ISO；逐行 JSON。Series → 一列的表。"""
    if isinstance(df, pd.Series):
        df = df.to_frame(name="value" if df.name is None else str(df.name))
    df = pd.DataFrame(df)
    names = {str(c): c for c in df.columns}
    if len(names) != len(df.columns):
        raise ValueError("列名转成字符串后有重复")
    cols = sorted(names)
    h = hashlib.sha256(json.dumps(["__index__", *cols], ensure_ascii=False).encode("utf-8"))
    idx = list(df.index)
    data = [df[names[c]].to_numpy(dtype=object) for c in cols]
    for r in range(len(df)):
        row = [_canon(idx[r])] + [_canon(col[r]) for col in data]
        h.update(b"\n" + json.dumps(row, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def ks_src_sha() -> str:
    """日経标签用到的 kline_series 代码：labels_partial / _rule / _lag / clean_rows / _closed_weekdays 的源码 + (NEED, SB, TIE_EPS) 的 sha1 前 16 位。"""
    s = "".join(inspect.getsource(f) for f in (KS.labels_partial, KS._rule, KS._lag, KS.clean_rows, KS._closed_weekdays))
    s += repr((KS.NEED, KS.SB, KS.TIE_EPS))
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def cp_src_sha(path: Path | None = None) -> str:
    """scripts/candle_portfolio.py 整个文件内容的 sha1 前 16 位。"""
    p = path or (ROOT / "scripts" / "candle_portfolio.py")
    return hashlib.sha1(p.read_bytes()).hexdigest()[:16]


def hook_present() -> dict:
    """钩子在：MixEngine.CHAND_K_DAY 类属性（缺省 None）、make_runner 里 run 的参数 chand_k_day、finally 里复原（按 AST 查）。"""
    import candle_portfolio as CP
    attr = hasattr(CP.MixEngine, "CHAND_K_DAY") and CP.MixEngine.CHAND_K_DAY is None
    tree = ast.parse(textwrap.dedent(inspect.getsource(CP.make_runner)))
    runs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run"]
    arg = bool(runs) and "chand_k_day" in [a.arg for a in runs[0].args.args + runs[0].args.kwonlyargs]
    restore = False
    for n in (ast.walk(runs[0]) if runs else ()):
        if isinstance(n, ast.Try):
            for st in n.finalbody:
                for x in ast.walk(st):
                    if (isinstance(x, ast.Assign) and isinstance(x.value, ast.Constant) and x.value.value is None
                            and any(isinstance(tg, ast.Attribute) and tg.attr == "CHAND_K_DAY" for tg in x.targets)):
                        restore = True
    return {"attr": bool(attr), "arg": bool(arg), "restore": bool(restore), "ok": bool(attr and arg and restore)}


def check_code(strict: bool = True) -> dict:
    """--prep / --run 开头：QB_DROP_ZERO_VOL = "1"、kline.SLOPE_BARS = 3、三个代码指纹 = 登记值、钩子在、month_up_dip_study 的 FP / B4_TOL = 登记值。
    任一不对 → 停（strict）。CP_SRC_SHA 还没登记（None）时 --prep 只记下现在的值（要写进常数），--run 停。"""
    env = os.environ.get("QB_DROP_ZERO_VOL")
    out = {"QB_DROP_ZERO_VOL": env, "SLOPE_BARS": int(K.SLOPE_BARS), "kline_src_sha": MUD.kline_src_sha(), "ks_src_sha": ks_src_sha(),
           "cp_src_sha": cp_src_sha(), "hook": hook_present()}
    why = []
    if env != ZERO_VOL_ENV:
        why.append(f"QB_DROP_ZERO_VOL = {env!r}（登记的是 {ZERO_VOL_ENV!r}）")
    if K.SLOPE_BARS != SLOPE_BARS:
        why.append(f"kline.SLOPE_BARS = {K.SLOPE_BARS}（登记的是 {SLOPE_BARS}）")
    if out["kline_src_sha"] != KLINE_SRC_SHA:
        why.append(f"kline 标签代码的 sha1 {out['kline_src_sha']} ≠ 登记的 {KLINE_SRC_SHA}")
    if out["ks_src_sha"] != KS_SRC_SHA:
        why.append(f"kline_series 标签代码的 sha1 {out['ks_src_sha']} ≠ 登记的 {KS_SRC_SHA}")
    if CP_SRC_SHA is None:
        if strict:
            why.append("CP_SRC_SHA 还没登记")
    elif out["cp_src_sha"] != CP_SRC_SHA:
        why.append(f"candle_portfolio.py 的 sha1 {out['cp_src_sha']} ≠ 登记的 {CP_SRC_SHA}")
    if not out["hook"]["ok"]:
        why.append(f"研究引擎的钩子不全：{out['hook']}")
    if MUD.FP != FP or MUD.B4_TOL != B4_TOL:
        why.append(f"month_up_dip_study.FP / B4_TOL = {MUD.FP} / {MUD.B4_TOL} ≠ 登记的 {FP} / {B4_TOL}")
    import trendline_study as TS
    out["pool_fold"] = dict(TS.FOLD) == dict(POOL_FOLD)
    if not out["pool_fold"]:
        why.append(f"trendline_study.FOLD = {TS.FOLD} ≠ 登记的 POOL_FOLD {POOL_FOLD}（池子用的 C 那一折）")
    out["ok"] = not why
    out["why"] = why
    if why:
        raise SystemExit("代码 / 环境指纹不对：" + "；".join(why) + " → 停")
    return out


def consts_check() -> dict:
    """不载入数据的先决（规则指纹、trendline_study / month_up_dip_study 的 FP / B4_TOL、turn_shape_combo.json 的 cand.TBF = month_up_dip_study.b_precheck）
    + 已公开参照的值 = B4_REF。返回 {ok, why, …}。"""
    pre = MUD.b_precheck()
    why = list(pre["why"])
    try:
        from qbreak import paths
        ref = json.loads((paths.PROJECT_ROOT / "var" / "out" / "turn_shape_combo.json").read_text(encoding="utf-8"))["cand"]["TBF"]
        for e in N225_ERAS:
            if any(ref[e].get(k) != v for k, v in B4_REF[e].items()):
                why.append(f"turn_shape_combo.json 的 cand.TBF.{e} 与登记的 B4_REF 不同")
    except Exception as ex:                                                  # noqa: BLE001
        why.append(f"turn_shape_combo.json 读不出（{type(ex).__name__}）")
    return {"fingerprint": pre.get("fingerprint"), "ok": not why, "why": why}


def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=root)


def git_state(rel: str, root=None) -> dict:
    """一个文件的登记状态（与 wide_exit_study.git_state 同一口径；git 出错 / 不是仓库 → 各项 None）：tracked = 在索引里；commit = 最后一次改它的提交
    （空 = 只 git add、没提交过）；clean = 与 HEAD 没有差别（含暂存区）；pushed = 那个提交已在上游里（读不到上游 → None，只记录）。只读 git。"""
    root = Path(root) if root is not None else ROOT
    none = {"tracked": None, "commit": None, "clean": None, "pushed": None, "upstream": None}
    try:
        ls = _git(root, "ls-files", "--", rel)
        lg = _git(root, "log", "-1", "--format=%H", "--", rel)
        if ls.returncode != 0 or lg.returncode != 0:
            return none
        commit = lg.stdout.strip() or None
        df = _git(root, "diff", "--quiet", "HEAD", "--", rel).returncode
        up = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        has_up = up.returncode == 0 and bool(up.stdout.strip())
        pushed = None
        if commit and has_up:
            a = _git(root, "merge-base", "--is-ancestor", commit, "@{u}").returncode
            pushed = True if a == 0 else (False if a == 1 else None)
        return {"tracked": bool(ls.stdout.strip()), "commit": commit, "clean": True if df == 0 else (False if df == 1 else None),
                "pushed": pushed, "upstream": bool(has_up)}
    except Exception:                                                        # noqa: BLE001
        return none


def reg_status(root=None, wxa_required: bool | None = None) -> dict:
    """--run 第 0 步：「NKT 与 WXA 两个都登记（提交并推送）之后才运行」。
    self = 本研究的 SELF_FILES 都已提交、与 HEAD 没有差别、读得到上游时已推送；wxa = WXA_SCRIPT 已提交（只 git add 不算）、读得到上游时已推送
    （WXA_REQUIRED = False 时只记录）。与 wide_exit_study 的 NKT_REQUIRED / self_status 对称。"""
    req = WXA_REQUIRED if wxa_required is None else bool(wxa_required)
    files = {f: git_state(f, root) for f in SELF_FILES}
    bad = [f for f, g in files.items() if not (g["tracked"] and g["commit"] and g["clean"] is True and g["pushed"] is not False)]
    w = git_state(WXA_SCRIPT, root)
    wxa_ok = bool(w["commit"]) and w["pushed"] is not False
    why = []
    if bad:
        why.append(f"NKT 没有登记完（没提交 / 有未提交的改动 / 没推送：{'、'.join(bad)}）")
    if req and not wxa_ok:
        why.append(f"WXA 还没登记（{WXA_SCRIPT} 没提交或没推送）：两个都登记之后才运行任何一个的 --run")
    return {"ok": not why, "why": why, "self_bad": bad, "wxa": {"required": req, "committed": bool(w["commit"]), "pushed": w["pushed"],
                                                                "ok": wxa_ok}}


# ───────────────────────── 日経状态 ─────────────────────────
def nikkei_rows() -> tuple[pd.DataFrame, dict]:
    """var/cache/idx_N225_27y.csv（read_cache_direct：不看 TTL、不联网、不写缓存）→ clean_rows(drop_zero_vol=False)。
    info：clean_rows 的个数 + 删掉的日期、保留下来的成交量 0 的行（合计、按年份、最后一行）。"""
    df = MUD.read_cache_direct(NK_TICKER, NK_YEARS)
    if df is None or not len(df):
        raise SystemExit(f"{NK_TICKER} 的 {NK_YEARS}y 缓存读不出 → 停")
    rows, info = KS.clean_rows(df, drop_zero_vol=False)
    info = dict(info)
    info["dropped_dates"] = [str(x.date()) for x in pd.DatetimeIndex(df.index).difference(pd.DatetimeIndex(rows.index))]
    vol = pd.to_numeric(rows["Volume"], errors="coerce").to_numpy(float) if "Volume" in rows.columns else np.full(len(rows), np.nan)
    with np.errstate(invalid="ignore"):
        zv = ~(vol > 0)
    ix = pd.DatetimeIndex(rows.index)
    by = pd.Series(zv, index=ix).groupby(ix.year).sum()
    info["zero_vol_kept"] = int(zv.sum())
    info["zero_vol_by_year"] = {str(int(y)): int(n) for y, n in by.items() if n}
    info["zero_vol_last"] = str(ix[zv][-1].date()) if zv.any() else None
    return rows, info


def nikkei_state(rows: pd.DataFrame) -> pd.DataFrame:
    """每一行收盘时的日K 标签 D（kline_series.labels_partial，= kline.trend(rows[:t+1])）→ DataFrame[weak, known, fD, D]（index = 日経的行）。"""
    lab = KS.labels_partial(rows)
    if not pd.DatetimeIndex(lab.index).equals(pd.DatetimeIndex(rows.index)):
        raise ValueError("标签的行与日経的行对不上")
    d = lab["D"].to_numpy(np.int8)
    return pd.DataFrame({"weak": d == -1, "known": d != KS.NA, "fD": lab["fD"].to_numpy(bool), "D": d}, index=pd.DatetimeIndex(lab.index))


def k_series(state: pd.DataFrame) -> pd.Series:
    """钩子用的 KSER：完整日経索引，weak → K_WEAK（2.0），否则 NaN（不变）。"""
    return pd.Series(np.where(state["weak"].to_numpy(bool), K_WEAK, np.nan), index=pd.DatetimeIndex(state.index), name="chand_k")


def _runs(mask: np.ndarray) -> list[int]:
    """连续为真的段的长度。"""
    m = np.asarray(mask, bool).astype(np.int8)
    if not m.any():
        return []
    d = np.diff(np.r_[0, m, 0])
    return list((np.flatnonzero(d == -1) - np.flatnonzero(d == 1)).astype(int))


def jpx_days(a, b) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([x for x in pd.bdate_range(pd.Timestamp(a), pd.Timestamp(b)) if CAL.is_trading_day(x.date())])


def nikkei_counts(rows: pd.DataFrame, state: pd.DataFrame, info: dict) -> dict:
    """十一 A / B-1：行数、成交量 0、非 JPX 日、第一个有标签的日子、NA / fragile、缺的 JPX 交易日、各窗口的 weak 占比与成段（只数天数）。"""
    ix = pd.DatetimeIndex(state.index)
    weak, known = state["weak"].to_numpy(bool), state["known"].to_numpy(bool)
    jd = jpx_days(JPX_FROM, ix[-1])
    miss = jd.difference(ix)
    out = {"rows_in": int(info.get("rows_in", 0)), "rows": int(len(ix)), "nan_close": int(info.get("nan_close", 0)),
           "non_jpx": int(info.get("non_jpx", 0)), "dropped_dates": info.get("dropped_dates"), "zero_vol_kept": info.get("zero_vol_kept"),
           "zero_vol_by_year": info.get("zero_vol_by_year"), "zero_vol_last": info.get("zero_vol_last"),
           "first": str(ix[0].date()), "last": str(ix[-1].date()), "first_labeled": str(ix[known][0].date()) if known.any() else None,
           "na_rows": int((~known).sum()), "fragile": int(state["fD"].to_numpy(bool).sum()), "weak_rows": int(weak.sum()),
           "jpx_days_from": JPX_FROM, "jpx_days": int(len(jd)), "jpx_missing": [str(x.date()) for x in miss],
           "jpx_max_stale_days": int(max([0] + [int((x - ix[ix <= x][-1]).days) for x in miss if (ix <= x).any()])), "windows": {}}
    for k, (a, b) in {**NK_WINDOWS, "all": (str(ix[0].date()), str(ix[-1].date()))}.items():
        m = (ix >= pd.Timestamp(a)) & (ix <= pd.Timestamp(b))
        seg = _runs(weak[m])
        out["windows"][k] = {"rows": int(m.sum()), "jpx_days": int(len(jpx_days(a, b))) if k != "all" else None,
                             "weak_share": float(weak[m].mean()) if m.any() else None, "segments": len(seg),
                             "seg_median": float(np.median(seg)) if seg else None, "seg_mean": float(np.mean(seg)) if seg else None,
                             "seg_max": int(max(seg)) if seg else None}
    return out


# ───────────────────────── as-of ─────────────────────────
def weak_pos(nk_index, dates) -> np.ndarray:
    """日期 → 日経里 ≤ 这一天的最后一行的位置（没有 → −1）= candle_portfolio.asof_pos。"""
    import candle_portfolio as CP
    return CP.asof_pos(nk_index, dates)


def stale_days(nk_index, dates) -> np.ndarray:
    """每个日期 as-of 取到的日経行离它几个日历日（之前没有行 → NaN）。"""
    ix = pd.DatetimeIndex(nk_index)
    dd = pd.DatetimeIndex(dates)
    pos = weak_pos(ix, dd)
    out = np.full(len(dd), np.nan)
    ok = pos >= 0
    if ok.any():
        out[ok] = (dd[ok] - ix[pos[ok]]).days.to_numpy(float)
    return out


def check_stale(nk_index, dates_by_key: dict) -> dict:
    """每组日期里 ≥ 日経首日的那些：as-of 最旧天数 ≤ MAX_STALE_DAYS，否则停。返回 {键: {n, max, 天数分布}}。"""
    out = {}
    bad = []
    for k, dates in dates_by_key.items():
        s = stale_days(nk_index, dates)
        s = s[np.isfinite(s)]
        mx = int(s.max()) if len(s) else None
        out[k] = {"n": int(len(s)), "max": mx, "dist": {str(int(v)): int(c) for v, c in zip(*np.unique(s, return_counts=True))} if len(s) else {}}
        if mx is not None and mx > MAX_STALE_DAYS:
            bad.append(k)
    if bad:
        raise SystemExit(f"as-of 取到的日経行太旧（> {MAX_STALE_DAYS} 个日历日）：{bad} → 停（运行前修正）")
    return out


# ───────────────────────── 平移 ─────────────────────────
def shift_grid(n: int, m: int = N_SHIFT, min_shift: int = MIN_SHIFT) -> list[int]:
    """确定的平移网格：s_k = min_shift + floor(k × (n − 2·min_shift) / (m − 1))，k = 0〜m−1（第二关也用，m = 400 / 800）。"""
    if m < 2 or n - 2 * min_shift < m - 1:
        raise ValueError("网格太密或序列太短")
    return [int(min_shift + (k * (n - 2 * min_shift)) // (m - 1)) for k in range(m)]


def rolled(w, s: int) -> np.ndarray:
    """整段循环平移：rolled(w, s)[p] = w[(p − s) mod N]（= np.roll）。"""
    return np.roll(np.asarray(w, bool), int(s))


def synth_z(w, grid) -> dict:
    """--prep 的查表核对用的 6 个非真实序列（SYNTH_Z）。"""
    w = np.asarray(w, bool)
    n = len(w)
    out = {"zero": np.zeros(n, bool), "one": np.ones(n, bool), "alt": (np.arange(n) % 2 == 0)}
    for k, i in SYNTH_ROLL.items():
        out[k] = rolled(w, grid[i])
    return {k: out[k] for k in SYNTH_Z}


def corr_len(v, step: float) -> dict:
    """沿网格顺序的自相关：τ = 1 + 2 Σ_{k≥1} ρ_k（加到第一个 ρ_k ≤ 0 或 k = M/4 为止）；K_eff = M / τ；L = τ × 步长；p_min = 1 / (K_eff + 1)。"""
    x = np.asarray(v, float)
    m = len(x)
    nan = {"tau": float("nan"), "K_eff": float("nan"), "L": float("nan"), "p_min": float("nan"), "M": int(m)}
    if m < 4 or not np.isfinite(x).all():
        return nan
    x = x - x.mean()
    den = float((x * x).sum())
    if den <= 0:
        return nan
    tau = 1.0
    for k in range(1, m // 4 + 1):
        rho = float((x[:-k] * x[k:]).sum()) / den
        if rho <= 0:
            break
        tau += 2.0 * rho
    ke = m / tau
    return {"tau": tau, "K_eff": ke, "L": tau * float(step), "p_min": 1.0 / (ke + 1.0), "M": int(m)}


def mde(v) -> float:
    """检出力：q95 − 中位（平移分布）。"""
    x = np.asarray(v, float)
    return float(np.quantile(x, Q) - np.median(x)) if len(x) and np.isfinite(x).all() else float("nan")


def pct_of(real, vals) -> float | None:
    """真实值在平移值里的分位（小于它的比例 + 相等的一半）。"""
    x = np.asarray(vals, float)
    if real is None or not np.isfinite(real) or not len(x):
        return None
    return float((x < real).mean() + 0.5 * (x == real).mean())


def dist(vals) -> dict:
    x = np.asarray(vals, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "min": float(x.min()), "q05": float(np.quantile(x, 0.05)), "median": float(np.median(x)),
            "q95": float(np.quantile(x, 0.95)), "max": float(x.max())}


# ───────────────────────── 池子 ─────────────────────────
def pool_signals(W: dict, tbf: dict, tbf_pool: dict) -> dict[str, pd.DataFrame]:
    """四个池子里 B4 会买的信号 → {池子: DataFrame[ticker, date, era, sm, (net)]}（N = Z / E / J 合成；W / Jx / Zx = month_up_dip_study.pool_signals）。"""
    import combo_all_common as CA
    import loop9_common as C9
    out = {}
    parts = []
    for e in N225_ERAS:
        S = C9.signals(W, e)
        g = np.asarray(tbf[e], bool)
        if len(g) != len(S):
            raise SystemExit("TBF 旗子与日経225 信号对不上 → 停")
        keep = np.asarray(CA.apply_c(W["c_fold"][e], S), bool) & ~g
        X = S.loc[keep, ["ticker", "date"]].copy()
        X["era"], X["sm"] = e, e
        parts.append(X)
    out["N"] = pd.concat(parts, ignore_index=True)
    for s in OTHER_POOLS:
        X = MUD.pool_signals(W, s, tbf_pool)
        Y = X[["ticker", "date"]].copy()
        Y["date"] = pd.to_datetime(Y["date"])
        Y["era"], Y["sm"] = POOL_ERA[s], POOL_SM[s]
        if "net" in X.columns:
            Y["net"] = X["net"].to_numpy(float)
        out[s] = Y.reset_index(drop=True)
    for s in POOLS:
        out[s]["ticker"] = out[s]["ticker"].astype(str)
        out[s]["date"] = pd.to_datetime(out[s]["date"])
    return out


def pool_frames(W: dict) -> dict:
    """池子行情：{行情键: {票: 指标表}}（N 用 Z / E / J 各自的，W / Jx / Zx 用 W / J2 / Zx）。"""
    return {k: W["SM"][k]["fa"] for k in (*N225_ERAS, *POOL_SM.values())}


def pool_overlap(P: dict) -> dict:
    """N 与 W / Jx / Zx 共有的票数与（票, 信号日）数（只数个数）。"""
    n_t = set(P["N"]["ticker"])
    n_k = set(zip(P["N"]["ticker"], pd.to_datetime(P["N"]["date"])))
    out = {}
    for s in OTHER_POOLS:
        X = P[s]
        out[s] = {"tickers": len(n_t & set(X["ticker"])), "pairs": len(n_k & set(zip(X["ticker"], pd.to_datetime(X["date"]))))}
    return out


def sig_sha(X: pd.DataFrame) -> str:
    keys = sorted(f"{t}|{pd.Timestamp(d).date()}" for t, d in zip(X["ticker"], X["date"]))
    return hashlib.sha1("\n".join(keys).encode("utf-8")).hexdigest()


def fp_items(state: pd.DataFrame, rows: pd.DataFrame, P: dict, frames: dict) -> list:
    """数据指纹的项（四）：日経一项、每个池子一项信号、每个池子用到的每只票一项。"""
    ix = pd.DatetimeIndex(state.index)
    c = pd.to_numeric(rows["Close"], errors="coerce").to_numpy(float)
    items = [("N225", str(ix[0].date()), str(ix[-1].date()), int(len(ix)), round(float(np.nansum(c)), 4), int(state["weak"].sum()),
              int((~state["known"]).sum()), int(state["fD"].sum()))]
    for s in POOLS:
        X = P[s]
        items.append(("sig", s, int(len(X)), sig_sha(X)))
        for sm in sorted(set(X["sm"])):
            fa = frames[sm]
            for t in sorted(set(X.loc[X["sm"] == sm, "ticker"])):
                df = fa.get(t)
                if df is None or not len(df):
                    items.append((f"{s}:{sm}", t, None, None, 0, 0.0, 0.0, 0.0, 0.0))
                    continue
                sm4 = [round(float(np.nansum(pd.to_numeric(df[k], errors="coerce").to_numpy(float))), 4) for k in ("Close", "Open", "High", "atr")]
                items.append((f"{s}:{sm}", t, str(df.index[0].date()), str(df.index[-1].date()), int(len(df)), *sm4))
    return items


# ───────────────────────── 查表（单笔） ─────────────────────────
def _flags(f: pd.DataFrame, kk: int, px: float) -> tuple[np.ndarray, np.ndarray]:
    from qbreak import exit_forward as XF
    return (np.asarray(XF.chandelier_flags(f, kk, px, k=K_BASE), bool), np.asarray(XF.chandelier_flags(f, kk, px, k=K_WEAK), bool))


def cand_days(f: pd.DataFrame, kk: int, px: float, end_pos: int) -> np.ndarray:
    """候选触发日：kk ≤ t ≤ end_pos 里 ch2 且非 ch3 的位置（升序）。"""
    ch3, ch2 = _flags(f, kk, px)
    t = np.arange(int(kk), int(end_pos) + 1)
    t = t[(t >= 0) & (t < len(f))]
    return t[ch2[t] & ~ch3[t]].astype(np.int64)


def _net(r, a, rt: float) -> float:
    """引擎的一笔 → 净收益 %（没买到 / 还没卖 / 成交日对不上 → NaN；同 single_with_events）。"""
    if r is None or r["reason"] == "end" or r["entry_date"] != a["entry_date"]:
        return float("nan")
    return float(r["ret_pct"]) - rt


def _reason(r) -> str | None:
    if r is None:
        return None
    return "chandelier" if r["reason"] == "dead_cross" else str(r["reason"])


def _prepare(tk: str, df: pd.DataFrame | None, d, p0, bt):
    """single_with_events 的前半：(f, d, end, a, kk, px, pos, end_pos) 或 (None, 理由)。"""
    from qbreak import exit_forward as XF
    if df is None:
        return None, "no_data"
    d = pd.Timestamp(d)
    if d not in df.index:
        return None, "no_signal_row"
    pos = int(df.index.get_loc(d))
    end_pos = min(len(df) - 1, pos + END_BARS)
    end = df.index[end_pos]
    f = df.copy()
    f["entry"] = np.asarray(df.index == d)
    try:
        a = XF._one(tk, f, p0, bt, d, end)
    except ValueError:
        return None, "short"
    if a is None:
        return None, "no_fill"
    kk = int(f.index.get_loc(pd.Timestamp(a["entry_date"])))
    px = float(f["Open"].to_numpy(float)[kk]) * (1 + bt.exec_cfg.slippage_pct / 100)
    return (f, d, end, a, kk, px, pos, end_pos), None


def lookup_one(tk: str, df: pd.DataFrame | None, d, p0, bt, rt: float) -> dict:
    """一个信号的查表（5.2）：nb（X6）、成交位置 kk、候选触发日与每个候选日「只在那天加一个旗子」的结果（r 与卖出日）；与 X6 相同之后的都记 nb。
    paired = nb 有值且查表没有 NaN；excluded = 查表里有 NaN（整个信号剔除）。"""
    from qbreak import exit_forward as XF
    out = {"ticker": str(tk), "date": pd.Timestamp(d), "nb": float("nan"), "paired": False, "excluded": False, "why": None, "runs": 0}
    pr, why = _prepare(tk, df, d, p0, bt)
    if pr is None:
        out["why"] = why
        return out
    f, d, end, a, kk, px, pos, end_pos = pr
    ch3, ch2 = _flags(f, kk, px)
    pv = replace(p0, max_hold_days=MAX_HOLD)
    b = XF._one(tk, f.assign(dead_cross=ch3), pv, bt, d, end)
    nb = _net(b, a, rt)
    out.update({"nb": nb, "kk": kk, "pos": pos, "end_pos": end_pos, "fill": str(a["entry_date"]),
                "x6_exit": None if b is None else str(b["exit_date"]), "x6_reason": _reason(b)})
    if not np.isfinite(nb):
        out["why"] = "x6_nan"
        return out
    t_all = np.arange(kk, end_pos + 1)
    cand = t_all[ch2[t_all] & ~ch3[t_all]].astype(np.int64)
    key6 = (b["entry_date"], b["exit_date"], b["exit_px"])
    cnet, cexit, creason = [], [], []
    stop, runs = False, 0
    for t in cand:
        if stop:
            cnet.append(nb), cexit.append(out["x6_exit"]), creason.append(out["x6_reason"])
            continue
        one = np.zeros(len(f), bool)
        one[t] = True
        r = XF._one(tk, f.assign(dead_cross=ch3 | one), pv, bt, d, end)
        runs += 1
        if r is not None and (r["entry_date"], r["exit_date"], r["exit_px"]) == key6:
            stop = True
            cnet.append(nb), cexit.append(out["x6_exit"]), creason.append(out["x6_reason"])
            continue
        cnet.append(_net(r, a, rt)), cexit.append(None if r is None else str(r["exit_date"])), creason.append(_reason(r))
    cnet = np.asarray(cnet, float)
    out.update({"cand": cand, "cdates": pd.DatetimeIndex(f.index[cand]), "cnet": cnet, "cexit": cexit, "creason": creason, "runs": runs})
    if len(cnet) and not np.isfinite(cnet).all():
        out["excluded"], out["why"] = True, "lookup_nan"
        return out
    out["paired"] = True
    return out


def nkt_net(L: dict, weak_at) -> tuple[float, bool]:
    """查表（5.2）：weak_at = 与 L["cand"] 同序的 z（候选日那天的 weak）→ τ = 第一个 weak 的候选日 → (NKT 净收益, changed)；没有 → (nb, False)。"""
    nb = float(L["nb"])
    w = np.asarray(weak_at, bool)
    hit = np.flatnonzero(w)
    if not len(hit):
        return nb, False
    k = int(hit[0])
    nv = float(L["cnet"][k])
    ch = (L["cexit"][k] != L["x6_exit"]) or bool(abs(nv - nb) > LOOKUP_TOL)
    return nv, bool(ch)


def direct_net(tk: str, df: pd.DataFrame | None, d, p0, bt, rt: float, weak_flags) -> dict:
    """核对用：直接用 ch3 | (weak & ch2) 跑一次（weak_flags 与 df 的行同序）→ {net, exit}。"""
    from qbreak import exit_forward as XF
    pr, why = _prepare(tk, df, d, p0, bt)
    if pr is None:
        return {"net": float("nan"), "exit": None, "why": why}
    f, d, end, a, kk, px, pos, end_pos = pr
    ch3, ch2 = _flags(f, kk, px)
    z = np.asarray(weak_flags, bool)
    r = XF._one(tk, f.assign(dead_cross=ch3 | (z & ch2)), replace(p0, max_hold_days=MAX_HOLD), bt, d, end)
    return {"net": _net(r, a, rt), "exit": None if r is None else str(r["exit_date"]), "why": None}


def build_lookups(P: dict, frames: dict, p0, bt, rt: float, say=print) -> dict[str, list[dict]]:
    """四个池子每个信号的查表（只在内存里，不落盘）。"""
    LK = {}
    for s in POOLS:
        X = P[s]
        LK[s] = []
        for t, d, sm in zip(X["ticker"], X["date"], X["sm"]):
            L = lookup_one(t, frames[sm].get(t), d, p0, bt, rt)
            L["sm"] = sm
            L["era"] = POOL_ERA.get(s, sm)
            LK[s].append(L)
        say(f"{s}：查表 {len(X)} 个信号、配对 {sum(L['paired'] for L in LK[s])}、引擎运行 {sum(L['runs'] for L in LK[s])} 次")
    return LK


def _days(x) -> np.ndarray:
    """日期字符串 / None → int64 天数（None → 最小值）。"""
    out = np.full(len(x), np.iinfo(np.int64).min, np.int64)
    for i, v in enumerate(x):
        if v is not None:
            out[i] = pd.Timestamp(v).value // 86_400_000_000_000
    return out


def flatten(Ls: list[dict], nk_index) -> dict:
    """一个池子配对信号的查表 → 向量化用的平铺数组（nb、X6 卖出日、每个信号的候选段、候选日的日経 as-of 位置 cpos、候选的净收益与卖出日）+ 描述用的元数据。"""
    keep = [L for L in Ls if L["paired"]]
    n = len(keep)
    seg = np.zeros(n + 1, np.int64)
    if n:
        seg[1:] = np.cumsum([len(L["cand"]) for L in keep])
    cd = pd.DatetimeIndex(np.concatenate([L["cdates"].to_numpy() for L in keep])) if n and seg[-1] else pd.DatetimeIndex([])
    return {"n": n, "nb": np.asarray([L["nb"] for L in keep], float), "x6exit": _days([L["x6_exit"] for L in keep]), "seg": seg,
            "cpos": weak_pos(nk_index, cd) if len(cd) else np.zeros(0, np.int64),
            "cnet": np.concatenate([L["cnet"] for L in keep]) if n and seg[-1] else np.zeros(0),
            "cexit": _days([v for L in keep for v in L["cexit"]]), "excluded": int(sum(L["excluded"] for L in Ls)),
            "ticker": [L["ticker"] for L in keep], "date": pd.DatetimeIndex([L["date"] for L in keep]),
            "fill": pd.DatetimeIndex([pd.Timestamp(L["fill"]) for L in keep]), "era": [L.get("era") for L in keep],
            "x6_reason": [L["x6_reason"] for L in keep]}


def eval_z(F: dict, z) -> tuple[np.ndarray, np.ndarray]:
    """一个日経行级的 weak 序列 z → 每个配对的 (NKT 净收益, changed)（τ = 每个信号候选段里第一个 weak 的候选日）。"""
    z = np.asarray(z, bool)
    nb = F["nb"]
    n = len(nb)
    nv, ch = nb.copy(), np.zeros(n, bool)
    if not n or not len(F["cpos"]):
        return nv, ch
    cp = F["cpos"]
    zc = np.zeros(len(cp), bool)
    ok = cp >= 0
    zc[ok] = z[cp[ok]]
    idx = np.flatnonzero(zc)
    if not len(idx):
        return nv, ch
    st, en = F["seg"][:-1], F["seg"][1:]
    k = np.searchsorted(idx, st)
    first = idx[np.minimum(k, len(idx) - 1)]
    has = (k < len(idx)) & (first < en)
    if has.any():
        fi = first[has]
        nv[has] = F["cnet"][fi]
        ch[has] = (F["cexit"][fi] != F["x6exit"][has]) | (np.abs(nv[has] - nb[has]) > LOOKUP_TOL)
    return nv, ch


def nb_exact_check(LK: dict, frames: dict, p0, bt, rt: float) -> dict:
    """(a) nb = turn_shape_combo.single_with_events(…, None)[0] 逐位相同（NaN 对 NaN 算相同）。"""
    import turn_shape_combo as TC
    n = bad = 0
    for s in POOLS:
        for L in LK[s]:
            df = frames[L["sm"]].get(L["ticker"])
            ref = float("nan") if df is None else float(TC.single_with_events(L["ticker"], df, L["date"], p0, bt, rt, None)[0])
            n += 1
            same = (np.isnan(ref) and np.isnan(L["nb"])) or (ref == L["nb"])
            bad += int(not same)
    return {"n": n, "bad": bad, "ok": bad == 0}


def base_match_check(LK: dict, P: dict) -> dict:
    """(b) W / Jx / Zx 的 nb 与 kept_pool 的 net 一致（|差| < BASE_MATCH_TOL）的比例 ≥ BASE_MATCH_MIN。"""
    out = {}
    for s in OTHER_POOLS:
        nb = np.asarray([L["nb"] for L in LK[s]], float)
        out[s] = MUD.base_match_info(nb, P[s]["net"].to_numpy(float)) if "net" in P[s].columns else {"n": len(nb), "match": 0, "frac": None}
    out["ok"] = all((out[s]["frac"] or 0) >= BASE_MATCH_MIN for s in OTHER_POOLS)
    return out


def lookup_check(LK: dict, frames: dict, zs: dict, nk_index, p0, bt, rt: float, say=print) -> dict:
    """查表 = 直接跑：每个序列（日経行级的 weak）在全部池子的全部配对信号上，查表（nkt_net）与直接用 ch3 | (z & ch2) 跑一次相同（|差| < LOOKUP_TOL），
    changed 也一致。返回 {序列名: {n, match, ok}, ok}（只有个数与 ✓ / ✗）。"""
    pos_cache: dict = {}
    out = {}
    for name, z in zs.items():
        z = np.asarray(z, bool)
        n = match = 0
        for s in POOLS:
            for L in LK[s]:
                if not L["paired"]:
                    continue
                df = frames[L["sm"]].get(L["ticker"])
                key = (L["sm"], L["ticker"])
                if key not in pos_cache:
                    pos_cache[key] = weak_pos(nk_index, df.index)
                rp = pos_cache[key]
                wf = np.where(rp >= 0, z[np.clip(rp, 0, None)], False)
                cp = weak_pos(nk_index, L["cdates"]) if len(L["cand"]) else np.zeros(0, np.int64)
                wa = np.where(cp >= 0, z[np.clip(cp, 0, None)], False)
                nv, ch = nkt_net(L, wa)
                dr = direct_net(L["ticker"], df, L["date"], p0, bt, rt, wf)
                dch = (dr["exit"] != L["x6_exit"]) or bool(abs(dr["net"] - L["nb"]) > LOOKUP_TOL)
                same = np.isfinite(nv) and np.isfinite(dr["net"]) and abs(nv - dr["net"]) < LOOKUP_TOL and bool(ch) == bool(dch)
                n += 1
                match += int(same)
        out[name] = {"n": n, "match": match, "ok": n > 0 and match == n}
        say(f"查表 = 直接跑（{name}）：{'✓' if out[name]['ok'] else '✗'}（{match} / {n}）")
    out["ok"] = all(v["ok"] for k, v in out.items() if k != "ok")
    return out


# ───────────────────────── 信息检查 ─────────────────────────
def pool_stats(nb, nv, changed) -> dict:
    """一个池子的配对统计（未四舍五入）：n、c、x、dbar、g、dwin（另带两边胜率 / 每笔，展示用）。"""
    b, v = np.asarray(nb, float), np.asarray(nv, float)
    ch = np.asarray(changed, bool)
    n = int(len(b))
    if not n:
        return {"n": 0, "c": 0, "x": float("nan"), "dbar": float("nan"), "g": float("nan"), "dwin": float("nan"),
                "win_b": float("nan"), "win_v": float("nan"), "mean_b": float("nan"), "mean_v": float("nan")}
    d = v - b
    c = int(ch.sum())
    wb, wv = float((b > 0).mean() * 100), float((v > 0).mean() * 100)
    return {"n": n, "c": c, "x": c / n, "dbar": float(d.mean()), "g": float(d.sum() / max(c, 1)), "dwin": wv - wb,
            "win_b": wb, "win_v": wv, "mean_b": float(b.mean()), "mean_v": float(v.mean())}


def pool_eval(F: dict, z) -> tuple[dict, float, float]:
    """四个池子在序列 z 下的统计 → (pools, T, G)；T / G = 四个池子 d̄ / g 的等权平均（缺池子 → NaN）。"""
    pools = {}
    for s in POOLS:
        if s not in F:
            pools[s] = pool_stats([], [], [])
            continue
        nv, ch = eval_z(F[s], z)
        pools[s] = pool_stats(F[s]["nb"], nv, ch)
    T = float(np.mean([pools[s]["dbar"] for s in POOLS]))
    G = float(np.mean([pools[s]["g"] for s in POOLS]))
    return pools, T, G


def _finite(*xs) -> bool:
    try:
        return all(x is not None and np.isfinite(float(x)) for x in xs)
    except (TypeError, ValueError):
        return False


def verdict_info(real: dict, plc: dict) -> tuple[str, str, bool]:
    """5.5 的判定（纯函数，从上往下第一个成立的就是结论）。real = {"pools": {池子: {c, dbar, g}}, "T", "G"}；
    plc = {"T": [400], "G": [400], "pools": {池子: {"c": [400]}}}。返回 (判定, 理由, dose_outside)。"""
    pools = real.get("pools") or {}
    T, G = real.get("T"), real.get("G")
    Ts, Gs = np.asarray(plc.get("T", []), float), np.asarray(plc.get("G", []), float)
    dose = False
    for s in POOLS:
        cs = np.asarray(((plc.get("pools") or {}).get(s) or {}).get("c", []), float)
        c = (pools.get(s) or {}).get("c")
        if c is not None and len(cs) and np.isfinite(cs).all():
            lo, hi = np.quantile(cs, DOSE_Q[0]), np.quantile(cs, DOSE_Q[1])
            dose |= bool(c < lo - EPS or c > hi + EPS)
    cs = [(pools.get(s) or {}).get("c") for s in POOLS]
    if all(c is not None for c in cs) and any(int(c) < MIN_CHANGED for c in cs):
        return INFO_LABELS[0], "c_p < MIN_CHANGED", dose
    vals = [(pools.get(s) or {}).get(k) for s in POOLS for k in ("dbar", "g")]
    if (not all(c is not None for c in cs) or not _finite(*vals, T, G) or len(Ts) != N_SHIFT or len(Gs) != N_SHIFT
            or not np.isfinite(Ts).all() or not np.isfinite(Gs).all()):
        return INFO_LABELS[1], "有非有限值或平移个数不对", dose
    db = [float(pools[s]["dbar"]) for s in POOLS]
    if all(x <= EPS for x in db):
        return INFO_LABELS[2], "四个 d̄ ≤ EPS", dose
    if not all(x > EPS for x in db):
        return INFO_LABELS[3], "四个 d̄ 不是都 > EPS", dose
    if float(T) <= float(np.quantile(Ts, Q)) + EPS:
        return INFO_LABELS[4], "T ≤ q95(T_s) + EPS", dose
    if float(G) <= float(np.quantile(Gs, Q)) + EPS:
        return INFO_LABELS[5], "G ≤ q95(G_s) + EPS", dose
    return INFO_PASS, "全部条件成立", dose


def say_verdict(label: str, dose_outside: bool, mde_t=None, mde_g=None) -> str:
    """第九节的一句话（含剂量限定语）。"""
    f = lambda v: "—" if v is None or not np.isfinite(v) else f"{v:.3f}"     # noqa: E731
    s = VERDICT_SAY.get(label, label).format(mde_t=f(mde_t), mde_g=f(mde_g))
    if dose_outside and label in DOSE_LABELS:
        s += " " + DOSE_NOTE
    return s


def info_check(F: dict, w, grid, say=print) -> dict:
    """信息检查（真实 + 平移）：判定只用未四舍五入的值。"""
    w = np.asarray(w, bool)
    pools, T, G = pool_eval(F, w)
    Ts, Gs = [], []
    pp = {s: {"dbar": [], "g": [], "c": [], "x": []} for s in POOLS}
    for s_ in grid:
        ps, t_, g_ = pool_eval(F, rolled(w, s_))
        Ts.append(t_)
        Gs.append(g_)
        for s in POOLS:
            for k in ("dbar", "g", "c", "x"):
                pp[s][k].append(ps[s][k])
    say(f"平移 {len(grid)} 次完成")
    Ts, Gs = np.asarray(Ts, float), np.asarray(Gs, float)
    plc = {"T": Ts, "G": Gs, "pools": {s: {k: np.asarray(v, float) for k, v in pp[s].items()} for s in POOLS}}
    real = {"pools": pools, "T": T, "G": G}
    label, why, dose = verdict_info(real, plc)
    step = (len(w) - 2 * MIN_SHIFT) / (len(grid) - 1)
    ok_t = len(Ts) and np.isfinite(Ts).all()
    ok_g = len(Gs) and np.isfinite(Gs).all()
    return {"pools": pools, "T": T, "G": G, "placebo": {"T": Ts, "G": Gs, "pools": plc["pools"]},
            "q95_T": float(np.quantile(Ts, Q)) if ok_t else None, "q95_G": float(np.quantile(Gs, Q)) if ok_g else None,
            "p_T": float((1 + np.sum(Ts >= T)) / (len(Ts) + 1)) if ok_t and np.isfinite(T) else None,
            "p_G": float((1 + np.sum(Gs >= G)) / (len(Gs) + 1)) if ok_g and np.isfinite(G) else None,
            "corr": {"T": corr_len(Ts, step), "G": corr_len(Gs, step)}, "step": step,
            "mde": {"T": mde(Ts), "G": mde(Gs)}, "dose_outside": bool(dose), "verdict": label, "why": why,
            "pct": {s: {k: pct_of(pools[s][k], plc["pools"][s][k]) for k in ("dbar", "g", "c")} for s in POOLS},
            "excluded": {s: int(F[s]["excluded"]) for s in POOLS if s in F}}


def other_of(pools: dict) -> dict:
    """第一关的 other：只取 W / Jx / Zx，未四舍五入（changed = c_p、dwin = dw_p、dmean = d̄_p）。"""
    return {s: {"changed": int(pools[s]["c"]), "dwin": float(pools[s]["dwin"]), "dmean": float(pools[s]["dbar"])} for s in OTHER_POOLS}


def stage1_of(cand: dict, base: dict, pools: dict) -> dict:
    """账户层第一关：research_loop11.stage1(cand, base, other（W / Jx / Zx，未四舍五入）, lenses=None, posthoc=POSTHOC)。"""
    import research_loop11 as R11
    return R11.stage1(cand, base, other_of(pools), lenses=None, posthoc=POSTHOC)


# ───────────────────────── 账户 ─────────────────────────
_LIVE: dict = {"log": [], "store": None}


def live_fp(store: dict | None = None) -> list:
    """bullbear_study.load 包一层：只记录 (代码, 首日, 末日, 行数, round(Close 合计, 2))，返回值原样（同一个对象）；store 不是 None → 按调用顺序
    另存每一次取到的副本（store[键] = [第 1 次, 第 2 次, …]；改前 vs 改后的子进程按同样的顺序逐次回放，同一个键取了几次、几次不完全相同也照样一致）。
    已经包过 → 只换 store。返回记录的列表。"""
    import bullbear_study as BB
    _LIVE["store"] = store
    if getattr(BB.load, "_nkt_live", False):
        return _LIVE["log"]
    orig = BB.load

    def load(*a, **k):
        df = orig(*a, **k)
        try:
            c = pd.to_numeric(df["Close"], errors="coerce").to_numpy(float)
            _LIVE["log"].append((str(a[0]) if a else str(k.get("sym")), str(df.index[0].date()) if len(df) else None,
                                 str(df.index[-1].date()) if len(df) else None, int(len(df)), round(float(np.nansum(c)), 2)))
        except Exception:                                                    # noqa: BLE001  只记录，记不下来也不影响返回值
            _LIVE["log"].append((str(a[0]) if a else "?", None, None, None, None))
        if _LIVE["store"] is not None:
            _LIVE["store"].setdefault(_bb_key(a, k), []).append(copy.deepcopy(df))
        return df

    load._nkt_live = True
    load._orig = orig
    BB.load = load
    _swap_load(orig, load)
    return _LIVE["log"]


def _swap_load(orig, new) -> list[str]:
    """已经 import 过、在模块顶层 `from bullbear_study import load` 拿走了原函数的模块：把那个名字也换成 new（之后 import 的模块自然拿到 new）。"""
    done = []
    for name, mod in list(sys.modules.items()):
        try:
            if mod is not None and getattr(mod, "load", None) is orig and name != "bullbear_study":
                setattr(mod, "load", new)
                done.append(name)
        except Exception:                                                    # noqa: BLE001
            continue
    return done


def _bb_key(a, k) -> str:
    return json.dumps([list(map(str, a)), sorted((str(x), str(y)) for x, y in k.items())])


def _copies(v) -> list:
    """store 的值：按调用顺序的副本列表（旧写法的单个 DataFrame 也认）。"""
    return list(v) if isinstance(v, (list, tuple)) else [v]


def live_repeat(store: dict) -> dict:
    """同一个键（代码 + 参数）取了几次、几次是否完全相同（DataFrame.equals）→ {键: {calls, identical}}（只数个数；不同 → 改前 vs 改后的 ✗ 能看出原因）。"""
    out = {}
    for key, v in (store or {}).items():
        cs = _copies(v)
        out[key] = {"calls": len(cs), "identical": bool(all(cs[0].equals(c) for c in cs[1:]))}
    return out


def live_overlap(store: dict, rows: pd.DataFrame) -> dict:
    """^N225 实时序列（bullbear_study.load；第一次取到的那份）与缓存在重叠日期上 Close 一致（|相对差| ≤ LIVE_TOL）的比例；
    ok = 比例 ≥ LIVE_MIN（--prep 的 live_n225 核对；--run 只记录）。"""
    hit = [c for key, v in (store or {}).items() if json.loads(key)[0][:1] == [NK_TICKER] for c in _copies(v)]
    if not hit:
        return {"n": 0, "frac": None, "ok": False}
    live = hit[0]["Close"].astype(float)
    cache = pd.to_numeric(rows["Close"], errors="coerce").astype(float)
    ix = pd.DatetimeIndex(live.index).intersection(pd.DatetimeIndex(cache.index))
    if not len(ix):
        return {"n": 0, "frac": None, "ok": False}
    a, b = live.reindex(ix).to_numpy(float), cache.reindex(ix).to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        ok = np.isfinite(a) & np.isfinite(b) & (np.abs(a / b - 1) <= LIVE_TOL)
    frac = float(ok.mean())
    return {"n": int(len(ix)), "frac": frac, "ok": bool(frac >= LIVE_MIN), "copies": len(hit)}


def _l6_run(W: dict, e: str, **kw) -> dict:
    import loop6_common as L6
    return L6.run(W, e, **kw)


def engine_days(eng) -> pd.DatetimeIndex:
    """引擎真正逐日推进的日子 = UnifiedEngine.run(start, end) 每推进一天就在权益历史里记一行（close_phase）→ 权益历史的日期。
    钩子只在这些日子的收盘离场判断里读 KSER；gidx 里 end 之后的日子（核心合成价按实时 ^N225 的日期一直延到今天）从不推进。"""
    return pd.DatetimeIndex(pd.to_datetime([h[0] for h in eng.st.history]))


def run_acct(W: dict, e: str, hashes: bool = False, **kw) -> dict:
    """一个账户（loop6_common.run）→ {acct（8 键）, years, trades（引擎的成交表）, gidx（引擎的全部日期）, days（逐日推进的日子）, [sha]}；
    跑完断言 MixEngine.CHAND_K_DAY is None。"""
    import candle_portfolio as CP
    import jq_study as JS
    import loop9_common as C9
    r = _l6_run(W, e, **kw)
    if CP.MixEngine.CHAND_K_DAY is not None:
        raise SystemExit("账户跑完后 MixEngine.CHAND_K_DAY 没有复原 → 停")
    eng = JS.RealLotEngine.LAST[-1]
    out = {"acct": C9.acct(r), "years": dict(r.get("years") or {}), "trades": pd.DataFrame(eng.st.trades), "gidx": pd.DatetimeIndex(eng.gidx),
           "days": engine_days(eng)}
    if hashes:
        out["sha"] = {"trades": canon_sha(pd.DataFrame(eng.st.trades)), "history": canon_sha(pd.DataFrame(eng.st.history))}
    return out


def era_tick(W: dict, e: str, tbf) -> dict:
    import loop9_common as C9
    S = C9.signals(W, e)
    return C9.tick_of(S["ticker"], S["date"], tbf)


def prereq_b4(W: dict, tbf: dict) -> dict:
    """B4 重算 = 参照 + exit_tick 的 8 键接线（month_up_dip_study.b_prereq；它的说明文字不打印）。"""
    pre = MUD.b_prereq(W, tbf, say=lambda s: None)
    pre["same_ref"] = {e: bool((pre.get(e) or {}).get("same_ref")) for e in N225_ERAS}
    pre["wired"] = {e: bool((pre.get(e) or {}).get("wired_all_keys")) for e in N225_ERAS}
    return pre


def wiring_series(nk_index) -> dict:
    """接线 W2〜W5 的序列（都建在完整日経索引上）。"""
    ix = pd.DatetimeIndex(nk_index)
    return {"W2": pd.Series(np.nan, index=ix), "W3": pd.Series(3.0, index=ix), "W4": pd.Series(4.0, index=ix),
            "W5": pd.Series(np.where(ix < pd.Timestamp(W5_CUT), K_WEAK, np.nan), index=ix)}


def hook_wiring(W: dict, tbf: dict, nk_index, base: dict) -> dict:
    """接线 W1〜W5 × Z / E / J：8 个键都与 B4（base）完全相同（eras / ok）；另外逐位核对：W2〜W5 的成交表与权益历史的规范化 sha256 都等于 W1
    （sha_eras / sha_ok；不增加账户运行次数，只多算哈希）。另返回每个年代 W1（= 钩子缺省的 B4）引擎的 gidx（R2 选笔用）、逐日推进的日子 days
    （最旧天数核对用）、成交表（B4 实际成交的个数、R2 用）与规范化 sha256（改前 vs 改后用）。"""
    import loop9_common as C9
    ser = wiring_series(nk_index)
    out, sha_eq, gidx, days, trades, sha = {}, {}, {}, {}, {}, {}
    for e in N225_ERAS:
        tick = era_tick(W, e, tbf[e])
        r1 = run_acct(W, e, hashes=True, em_tick=tick)
        gidx[e], days[e], trades[e], sha[e] = r1["gidx"], r1["days"], r1["trades"], r1["sha"]
        res = {"W1": MUD.same_acct(r1["acct"], base[e], C9.KEYS)}
        seq = {}
        for k, s in ser.items():
            rk = run_acct(W, e, hashes=True, em_tick=tick, chand_k_day=s)
            res[k] = MUD.same_acct(rk["acct"], base[e], C9.KEYS)
            seq[k] = rk["sha"] == r1["sha"]
        out[e] = {k: bool(v) for k, v in res.items()}
        sha_eq[e] = {k: bool(v) for k, v in seq.items()}
    return {"eras": out, "ok": all(all(v.values()) for v in out.values()), "sha_eras": sha_eq,
            "sha_ok": all(all(v.values()) for v in sha_eq.values()), "gidx": gidx, "days": days, "trades": trades, "sha": sha}


def hook_vs_params_td(W: dict, tbf: dict, nk_index) -> dict:
    """R1（正向对照）：全 2.0 的钩子账户（完整日経索引）= PARAMS_TD 给每个信号 k 2（菜单 k 2 / 60 天、带 TBF 的 em_tick）的账户，8 个键完全相同
    （eras / ok）；另外逐位核对两边成交表与权益历史的规范化 sha256（sha_eras / sha_ok）。"""
    import loop11_common as LC
    import loop9_common as C9
    out, sha_eq = {}, {}
    all2 = pd.Series(K_WEAK, index=pd.DatetimeIndex(nk_index))
    for e in N225_ERAS:
        S = C9.signals(W, e)
        tick = C9.tick_of(S["ticker"], S["date"], tbf[e])
        fills = LC.fill_dates(LC.days_of(W, e), S["date"])
        ptd = LC.build_params_td(W["px"], S["ticker"], fills, ["k2"] * len(S), {"k2": {"k": K_WEAK, "mh": MAX_HOLD}})
        a = run_acct(W, e, hashes=True, em_tick=tick, chand_k_day=all2)
        b = run_acct(W, e, hashes=True, em_tick=tick, params_td=ptd)
        out[e] = bool(MUD.same_acct(a["acct"], b["acct"], C9.KEYS))
        sha_eq[e] = bool(a["sha"] == b["sha"])
    return {"eras": out, "ok": all(out.values()), "sha_eras": sha_eq, "sha_ok": all(sha_eq.values())}


def r2_pick(W: dict, b4raw: dict, gidx: dict, nk_index) -> dict | None:
    """R2 选笔（只用 B4 已有的成交与价格，不碰真实 z）：按 Z → E → J、每个年代按成交表的顺序，找第一个（笔, d）满足：
    d 在 [成交日, 卖出日前第二个交易日] 里（个股的行）、收盘落在 [peak − 3·ATR, peak − 2·ATR) 里（离两条线都 ≥ R2_MARGIN；peak = max(成交价, 成交日起的最高价)，
    同引擎）；d 是日経的行，而且 d 的下一个日経行 = 个股的下一行 d′ = 引擎 gidx 里 d 的下一天，d′ 之后引擎的下一天也是日経的下一行；
    d′ 不是整天跌停（d 收盘排队后 d′ 开盘卖得掉）；
    d′ 收盘在 peak′ − 2·ATR′ 之上（离线 ≥ R2_MARGIN，不在带里）。返回 {era, i（这笔在年代成交表里的序号）, ticker, fill, d, d1, exit, reason} 或 None。
    B4 的卖出日 ≥ d′ 的下一天 → B4 在 d 收盘没有因别的原因排队（排了的话 d′ 就卖了）。"""
    from qbreak.tick import limit_lock
    ix = pd.DatetimeIndex(nk_index)
    for e in N225_ERAS:
        tr = trades_frame(W, e, b4raw.get(e))
        fa = W["SM"][e]["fa"]
        g = pd.DatetimeIndex(gidx[e])
        for i, (t, fill, ex, epx, rsn) in enumerate(zip(tr["ticker"], tr["fill"], tr["exit"], tr["entry_px"], tr["reason"])):
            df = fa.get(t)
            if df is None or pd.Timestamp(fill) not in df.index or pd.Timestamp(ex) not in df.index:
                continue
            kk, xe = int(df.index.get_loc(pd.Timestamp(fill))), int(df.index.get_loc(pd.Timestamp(ex)))
            h, c, a = (df[k].to_numpy(float) for k in ("High", "Close", "atr"))
            peak = float(epx)
            lo_ = df["Low"].to_numpy(float)
            for p in range(kk, xe - 1):                                      # p = 成交日〜卖出日前第二个交易日
                peak = max(peak, h[p]) if np.isfinite(h[p]) else peak
                if not np.isfinite(a[p]):
                    continue
                if not (c[p] >= peak - K_BASE * a[p] + R2_MARGIN and c[p] < peak - K_WEAK * a[p] - R2_MARGIN):
                    continue
                d, d1 = df.index[p], df.index[p + 1]
                pn = int(ix.searchsorted(d))
                if pn >= len(ix) - 1 or ix[pn] != d or ix[pn + 1] != d1:
                    continue
                pg = int(g.searchsorted(d))
                if pg >= len(g) - 1 or g[pg] != d or g[pg + 1] != d1:
                    continue
                if (g[pg + 2] if pg + 2 < len(g) else None) != (ix[pn + 2] if pn + 2 < len(ix) else None):
                    continue                                                 # d′ 之后引擎的下一天也是日経的行（d′ 那一行的 2.0 不会 as-of 延到别的日子）
                if limit_lock(c[p], h[p + 1], lo_[p + 1], c[p + 1], "JP") == "down":
                    continue
                pk1 = max(peak, h[p + 1]) if np.isfinite(h[p + 1]) else peak
                if not (np.isfinite(a[p + 1]) and c[p + 1] >= pk1 - K_WEAK * a[p + 1] + R2_MARGIN):
                    continue
                return {"era": e, "i": int(i), "ticker": str(t), "fill": pd.Timestamp(fill), "d": d, "d1": d1, "exit": pd.Timestamp(ex),
                        "reason": str(rsn)}
    return None


def hook_positive_b4(W: dict, tbf: dict, nk_index, b4raw: dict, gidx: dict) -> dict:
    """R2（正向对照、日期对齐；--prep，只记 ✓ / ✗）：r2_pick 选出的那笔 B4 成交，在它的年代跑两个账户（完整日経索引、其余每一行 NaN）：
    fire = KSER 只在 d 那一行是 2.0 → 这笔（同一个票与成交日）在 d′（d 的下一个交易日）开盘卖、原因 chandelier；
    next = KSER 只在 d′ 那一行是 2.0（那天收盘不在带里）→ 卖出日与原因都不变。两条都对才 ✓（钩子早一天 / 晚一天都会让其中一条 ✗）。
    不打印、不存任何收益；返回里只有年代、序号与 ✓ / ✗。"""
    pk = r2_pick(W, b4raw, gidx, nk_index)
    if pk is None:
        return {"picked": False, "fire": False, "next": False, "ok": False}
    e = pk["era"]
    tick = era_tick(W, e, tbf[e])
    ix = pd.DatetimeIndex(nk_index)
    res = {}
    for name, day in (("fire", pk["d"]), ("next", pk["d1"])):
        s = pd.Series(np.where(ix == day, K_WEAK, np.nan), index=ix)
        tr = trades_frame(W, e, run_acct(W, e, em_tick=tick, chand_k_day=s)["trades"])
        m = tr[(tr["ticker"] == pk["ticker"]) & (tr["fill"] == pk["fill"])]
        if len(m) != 1:
            res[name] = False
            continue
        x, rsn = pd.Timestamp(m["exit"].iloc[0]), str(m["reason"].iloc[0])
        res[name] = bool((x == pk["d1"] and rsn == "chandelier") if name == "fire" else (x == pk["exit"] and rsn == pk["reason"]))
    return {"picked": True, "era": e, "i": pk["i"], **res, "ok": bool(res["fire"] and res["next"])}


def pre_vs_post(W: dict, tbf: dict, store: dict, here: dict | None = None, timeout: int = 7200) -> dict:
    """改前 vs 改后（3.2-3，只返回 ✓ / ✗）：git show PRE_REV 的 candle_portfolio.py → 临时目录（sha1 要等于 PRE_CP_SHA1）；子进程（同一个 python、
    cwd = quant_breakout/、冻结缓存、bullbear_study.load 读主进程存下的同一份 pickle）先把旧源码以模块名 candle_portfolio 载入，再算 Z / E / J 的 B4
    成交表与权益历史的规范化 sha256；主进程用改后的代码（钩子缺省）算同样的（here：接线 W1 已算好的就直接用）→ 三个年代逐个相同才 ✓。
    只读 git，不改 git 状态。"""
    here = here or {e: run_acct(W, e, hashes=True, em_tick=era_tick(W, e, tbf[e]))["sha"] for e in N225_ERAS}
    out = {"eras": {}, "ok": False, "why": None}
    tmp = tempfile.mkdtemp(prefix="nkt_pre_")
    try:
        old = subprocess.run(["git", "show", f"{PRE_REV}:quant_breakout/scripts/candle_portfolio.py"], capture_output=True, check=True,
                             cwd=ROOT).stdout
        if hashlib.sha1(old).hexdigest() != PRE_CP_SHA1:
            out["why"] = "git show PRE_REV 的旧文件 sha1 ≠ PRE_CP_SHA1"
            return out
        (Path(tmp) / "candle_portfolio_pre.py").write_bytes(old)
        with open(Path(tmp) / "bb.pkl", "wb") as f:
            pickle.dump(store, f)
        code = ("import sys; sys.path.insert(0, {s!r}); sys.path.insert(0, {r!r}); import nkt_study as N; N._pre_worker({t!r})"
                .format(s=str(ROOT / "scripts"), r=str(ROOT), t=tmp))
        env = {**os.environ, "QB_DROP_ZERO_VOL": ZERO_VOL_ENV}
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
        line = [x for x in p.stdout.splitlines() if x.startswith("NKT_PRE_JSON ")]
        if p.returncode != 0 or not line:
            out["why"] = f"子进程失败（返回码 {p.returncode}）"
            return out
        there = json.loads(line[-1][len("NKT_PRE_JSON "):])
        out["old_module"] = there.get("old_module")
        out["eras"] = {e: bool(there.get("sha", {}).get(e) == here[e]) for e in N225_ERAS}
        out["ok"] = bool(there.get("old_module")) and all(out["eras"].values())
        return out
    except Exception as ex:                                                  # noqa: BLE001
        out["why"] = MUD.err_info(ex)
        return out
    finally:
        for fn in ("candle_portfolio_pre.py", "bb.pkl"):
            (Path(tmp) / fn).unlink(missing_ok=True)
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def install_old_cp(src: str):
    """把旧的 candle_portfolio 源码以模块名 candle_portfolio 载入 sys.modules（__file__ = 仓库里的真实路径；要在任何别的模块 import 它之前调用）。"""
    import types
    if "candle_portfolio" in sys.modules:
        raise RuntimeError("candle_portfolio 已经载入过 → 旧源码换不进去")
    real = str(ROOT / "scripts" / "candle_portfolio.py")
    mod = types.ModuleType("candle_portfolio")
    mod.__file__ = real
    sys.modules["candle_portfolio"] = mod
    try:
        exec(compile(src, real, "exec"), mod.__dict__)                       # noqa: S102  登记时的旧源码（git show PRE_REV，sha1 已核对）
    except BaseException:
        sys.modules.pop("candle_portfolio", None)
        raise
    return mod


def _pre_worker(tmp: str) -> None:
    """改前 vs 改后的子进程：旧的 candle_portfolio 以真实路径为 __file__ 载入 → 冻结缓存 → bullbear_study.load 只读 pickle → B4 Z / E / J 的规范化 sha256。
    只打印一行 NKT_PRE_JSON（哈希，不含任何收益数字）。"""
    mod = install_old_cp((Path(tmp) / "candle_portfolio_pre.py").read_text(encoding="utf-8"))
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    MUD.freeze_cache()
    with open(Path(tmp) / "bb.pkl", "rb") as f:
        store = pickle.load(f)
    import bullbear_study as BB
    seen: dict = {}

    def load(*a, **k):                                                       # 同一个键的第 n 次调用 → 主进程第 n 次取到的那份（逐次回放）
        key = _bb_key(a, k)
        cs = _copies(store[key]) if key in store else []
        n = seen.get(key, 0)
        if n >= len(cs):
            raise RuntimeError("改前 vs 改后：bullbear_study.load 的这次调用不在主进程存下的 pickle 里（键不在或调用次数更多）")
        seen[key] = n + 1
        return copy.deepcopy(cs[n])
    orig = BB.load
    BB.load = load
    _swap_load(orig, load)
    import jq_study as JS
    import loop9_common as C9
    W, tbf, _ = MUD.b_load(say=lambda s: None)
    sha = {}
    old_ok = True
    for e in N225_ERAS:
        C9.run_block(W, e, tbf[e])
        eng = JS.RealLotEngine.LAST[-1]
        old_ok &= type(eng).__module__ == "candle_portfolio" and sys.modules["candle_portfolio"] is mod and not hasattr(type(eng), "CHAND_K_DAY")
        sha[e] = {"trades": canon_sha(pd.DataFrame(eng.st.trades)), "history": canon_sha(pd.DataFrame(eng.st.history))}
    print("NKT_PRE_JSON " + json.dumps({"sha": sha, "old_module": bool(old_ok)}), flush=True)


def trades_frame(W: dict, e: str, raw: pd.DataFrame) -> pd.DataFrame:
    """引擎成交 → 窗口内买入、已平仓的日本个股：ticker / fill / exit / reason / hold / net（% ）/ entry_px（同 month_up_dip_study.trades_of 的筛法）。"""
    cols = ["ticker", "fill", "exit", "reason", "hold", "net", "entry_px"]
    if raw is None or not len(raw):
        return pd.DataFrame({c: pd.Series(dtype="datetime64[ns]" if c in ("fill", "exit") else object) for c in cols})
    a, b = W["ctx"][e]["windows"][e]
    a, b = pd.Timestamp(a), pd.Timestamp(b) if b else pd.Timestamp("2026-10-01")
    tr = raw[raw["ticker"].astype(str).str.endswith(".T") & ~raw["ticker"].isin(STOCK_SKIP) & (raw["reason"] != "end")]
    ed = pd.to_datetime(tr["entry_date"])
    tr = tr[((ed >= a) & (ed < b)).to_numpy()].reset_index(drop=True)
    return pd.DataFrame({"ticker": tr["ticker"].astype(str), "fill": pd.to_datetime(tr["entry_date"]), "exit": pd.to_datetime(tr["exit_date"]),
                         "reason": tr["reason"].astype(str), "hold": pd.to_numeric(tr["hold_days"], errors="coerce").to_numpy(float),
                         "net": tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100,
                         "entry_px": tr["entry_px"].to_numpy(float)})


def trig_count(cand_tr: dict, base_tr: dict) -> int:
    """因 NKT 提前卖出的个股笔数 = Z + E + J 候选里「（票, 成交日）也在 B4 里、卖出日更早」的笔数。"""
    n = 0
    for e, c in cand_tr.items():
        b = base_tr.get(e)
        if b is None or not len(c) or not len(b):
            continue
        ex = {(t, pd.Timestamp(f)): pd.Timestamp(x) for t, f, x in zip(b["ticker"], b["fill"], b["exit"])}
        for t, f, x in zip(c["ticker"], c["fill"], c["exit"]):
            y = ex.get((t, pd.Timestamp(f)))
            n += int(y is not None and pd.Timestamp(x) < y)
    return int(n)


def early_sold(cand_tr: pd.DataFrame, base_tr: pd.DataFrame) -> pd.DataFrame:
    """候选里提前卖出的那些笔（与 B4 同一（票, 成交日）、卖出日更早）：两边的 net / hold / reason 并排。"""
    if not len(cand_tr) or not len(base_tr):
        return pd.DataFrame(columns=["ticker", "fill", "net_c", "net_b", "hold_c", "hold_b", "reason_c", "reason_b"])
    m = cand_tr.merge(base_tr, on=["ticker", "fill"], suffixes=("_c", "_b"))
    return m[m["exit_c"] < m["exit_b"]].reset_index(drop=True)


def account_stage(W: dict, tbf: dict, kser: pd.Series, pools: dict, base: dict, say=print) -> dict:
    """账户层第一关（六）：候选 = 带 TBF 的 em_tick + chand_k_day = KSER；base = 本次运行重算的 B4；MIN_TRIG；stage1（posthoc = True）。"""
    t0 = time.time()
    cand, ctr, btr, years = {}, {}, {}, {}
    for e in N225_ERAS:
        tick = era_tick(W, e, tbf[e])
        rc = run_acct(W, e, em_tick=tick, chand_k_day=kser)
        rb = run_acct(W, e, em_tick=tick)
        cand[e] = rc["acct"]
        ctr[e], btr[e] = trades_frame(W, e, rc["trades"]), trades_frame(W, e, rb["trades"])
        years[e] = {"cand": rc["years"], "base": rb["years"]}
        say(f"账户 {e} 完成")
    trig = trig_count(ctr, btr)
    s1 = stage1_of(cand, base, pools)
    verdict = ACCT_LABELS[0] if trig < MIN_TRIG else (ACCT_LABELS[2] if s1["ok"] else ACCT_LABELS[1])
    return {"cand": cand, "base": base, "trig": trig, "stage1": s1, "verdict": verdict, "describe": describe_d8(ctr, btr, years),
            "seconds": round(time.time() - t0)}


def describe_d8(ctr: dict, btr: dict, years: dict) -> dict:
    """D8：每个年代因 NKT 提前卖出的笔数、这些笔在 B4 / 候选里的胜率与每笔、平均持有天数、离场原因构成、逐年收益差。"""
    out = {}
    for e in N225_ERAS:
        es = early_sold(ctr[e], btr[e])
        r = {"early": int(len(es))}
        if len(es):
            r.update({"win_b": float((es["net_b"] > 0).mean() * 100), "win_c": float((es["net_c"] > 0).mean() * 100),
                      "mean_b": float(es["net_b"].mean()), "mean_c": float(es["net_c"].mean()),
                      "hold_b": float(es["hold_b"].mean()), "hold_c": float(es["hold_c"].mean())})
        r["reasons_c"] = {str(k): int(v) for k, v in ctr[e]["reason"].value_counts().items()} if len(ctr[e]) else {}
        r["reasons_b"] = {str(k): int(v) for k, v in btr[e]["reason"].value_counts().items()} if len(btr[e]) else {}
        yc, yb = years[e]["cand"], years[e]["base"]
        r["years_diff"] = {y: (None if yc.get(y) is None or yb.get(y) is None else float(yc[y]) - float(yb[y])) for y in sorted(set(yc) | set(yb))}
        out[e] = r
    return out


# ───────────────────────── 只数个数（登记前） ─────────────────────────
def _dose_arrays(P: dict, frames: dict, nk_index, slip: float) -> dict:
    """十一 B-3 的平铺数组（每个池子）：日历剂量的日経位置、持仓剂量代理的候选日位置与段、候选触发日总数、信号日的日経位置。
    px = 下一行开盘 × (1 + 滑点)，不管跳空过滤；不跑离场模拟。"""
    out = {}
    for s in POOLS:
        X = P[s]
        cal, hp, hseg, sigd = [], [], [0], []
        ncand = used = 0
        for t, d, sm in zip(X["ticker"], X["date"], X["sm"]):
            df = frames[sm].get(t)
            if df is None or pd.Timestamp(d) not in df.index:
                continue
            pos = int(df.index.get_loc(pd.Timestamp(d)))
            sigd.append(pd.Timestamp(d))
            kk = pos + 1
            if kk >= len(df):
                continue
            used += 1
            px = float(df["Open"].to_numpy(float)[kk]) * (1 + slip)
            ch3, ch2 = _flags(df, kk, px)
            hi = min(len(df) - 1, kk + DOSE_ROWS - 1)
            cal.append(df.index[kk:hi + 1])
            f3 = np.flatnonzero(ch3[kk:hi + 1])
            hend = kk + int(f3[0]) - 1 if len(f3) else hi
            tt = np.arange(kk, hend + 1)
            tt = tt[ch2[tt] & ~ch3[tt]] if len(tt) else tt
            hp.append(df.index[tt])
            hseg.append(hseg[-1] + len(tt))
            ce = min(len(df) - 1, pos + END_BARS)
            t2 = np.arange(kk, ce + 1)
            ncand += int((ch2[t2] & ~ch3[t2]).sum())
        cd = pd.DatetimeIndex(np.concatenate([x.to_numpy() for x in cal])) if cal else pd.DatetimeIndex([])
        hd = pd.DatetimeIndex(np.concatenate([x.to_numpy() for x in hp])) if hp else pd.DatetimeIndex([])
        out[s] = {"used": used, "cal_pos": weak_pos(nk_index, cd) if len(cd) else np.zeros(0, np.int64), "cal_dates": cd,
                  "hp_pos": weak_pos(nk_index, hd) if len(hd) else np.zeros(0, np.int64), "hp_seg": np.asarray(hseg, np.int64),
                  "cand_days": ncand, "sig_pos": weak_pos(nk_index, pd.DatetimeIndex(sigd)) if sigd else np.zeros(0, np.int64)}
    return out


def _at(z: np.ndarray, pos: np.ndarray) -> np.ndarray:
    v = np.zeros(len(pos), bool)
    ok = pos >= 0
    v[ok] = z[pos[ok]]
    return v


def exposure_dose(DA: dict, w, grid) -> dict:
    """(a) 日历剂量 [成交日, 成交日 + 59 行] 的 weak 占比；(b) 持仓剂量代理（有 weak 且 ch2 非 ch3 的日子的信号数）：真实与 400 个平移。"""
    w = np.asarray(w, bool)
    out = {}
    for s, A in DA.items():
        def cal_share(z):
            v = _at(z, A["cal_pos"])
            return float(v.mean()) if len(v) else float("nan")

        def hold_n(z):
            v = _at(z, A["hp_pos"])
            if not len(v):
                return 0
            cs = np.r_[0, np.cumsum(v)]
            return int(((cs[A["hp_seg"][1:]] - cs[A["hp_seg"][:-1]]) > 0).sum())
        cr = cal_share(w)
        hr = hold_n(w)
        cs_ = [cal_share(rolled(w, x)) for x in grid]
        hs_ = [hold_n(rolled(w, x)) for x in grid]
        hd = dist(hs_)
        out[s] = {"signals_used": int(A["used"]), "cal_real": cr, "cal_shift": {**dist(cs_), "pct": pct_of(cr, cs_)},
                  "hold_real": hr, "hold_shift": {**hd, "pct": pct_of(hr, hs_)},
                  "hold_outside": bool(hd.get("n") and (hr < hd["q05"] - EPS or hr > hd["q95"] + EPS)), "cand_days": int(A["cand_days"]),
                  "sig_weak": int(_at(w, A["sig_pos"]).sum()), "sig_n": int(len(A["sig_pos"]))}
    return out


def window_shift_shares(nk_index, w, grid) -> dict:
    """平移后各窗口（Z / E / J）的 weak 占比（只数天数）：真实值与 400 个平移的最小 / 中位 / 最大。"""
    ix = pd.DatetimeIndex(nk_index)
    w = np.asarray(w, bool)
    out = {}
    for k, (a, b) in NK_WINDOWS.items():
        m = (ix >= pd.Timestamp(a)) & (ix <= pd.Timestamp(b))
        if not m.any():
            out[k] = {"real": None, "min": None, "median": None, "max": None}
            continue
        vals = [float(rolled(w, s)[m].mean()) for s in grid]
        out[k] = {"real": float(w[m].mean()), "min": float(np.min(vals)), "median": float(np.median(vals)), "max": float(np.max(vals))}
    return out


def b4_band_counts(W: dict, b4_raw: dict, nk_index, w) -> dict:
    """十一 B-4：B4 实际成交里，持有期（成交日〜卖出日前第二个交易日）出现「weak 且 peak − 3·ATR ≤ c < peak − 2·ATR」的笔数（预估 NKT 会提前卖的笔数，
    不含路径依赖）。peak 从成交价起、每天取 max(peak, 最高价)。"""
    w = np.asarray(w, bool)
    out = {}
    tot = 0
    for e in N225_ERAS:
        tr = trades_frame(W, e, b4_raw[e])
        fa = W["SM"][e]["fa"]
        hit = 0
        for t, fill, ex, epx in zip(tr["ticker"], tr["fill"], tr["exit"], tr["entry_px"]):
            df = fa.get(t)
            if df is None or pd.Timestamp(fill) not in df.index or pd.Timestamp(ex) not in df.index:
                continue
            kk, xe = int(df.index.get_loc(pd.Timestamp(fill))), int(df.index.get_loc(pd.Timestamp(ex)))
            hi = xe - 2
            if hi < kk:
                continue
            h = df["High"].to_numpy(float)[kk:hi + 1]
            c = df["Close"].to_numpy(float)[kk:hi + 1]
            a = df["atr"].to_numpy(float)[kk:hi + 1]
            peak = np.maximum(np.maximum.accumulate(np.where(np.isfinite(h), h, -np.inf)), float(epx))
            with np.errstate(invalid="ignore"):
                band = np.isfinite(a) & (c >= peak - K_BASE * a) & (c < peak - K_WEAK * a)
            wk = _at(w, weak_pos(nk_index, df.index[kk:hi + 1]))
            hit += int((band & wk).any())
        out[e] = {"trades": int(len(tr)), "ref": B4_TRADES_REF[e], "hit": int(hit)}
        tot += hit
    out["total"] = int(tot)
    out["may_rarely_trigger"] = bool(tot < MIN_TRIG)
    return out


def id_check(var_dir=None, scan_repo: bool = True) -> dict:
    """ID 核对（十一 B-9）：NKT 不在 research_loop11.previous_ids()、var/research_loop11.json 的做法 ID（没有这个文件 = 没有）、RESERVED_IDS、
    research_registry.json 里别的条目（script 不含 nkt_study.py 的 —— 本研究自己的登记 / 结果条目不算；候选 dict 与字符串两种写法都认）的候选 ID、
    仓库全文（scan_repo；git 跟踪的 + 未忽略的未跟踪文本文件；本研究自己的文件与 var/out/nkt_study.* 除外）。var_dir：缺省 = 仓库的 var（测试用临时目录）。"""
    import research_loop11 as R11
    var = Path(var_dir) if var_dir is not None else ROOT / "var"
    out = {"previous_ids": ID not in R11.previous_ids(var), "reserved": ID not in R11.RESERVED_IDS}
    try:
        p11 = var / "research_loop11.json"
        st = json.loads(p11.read_text(encoding="utf-8")) if p11.exists() else {}
        out["loop11"] = ID not in {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or []}
    except Exception:                                                        # noqa: BLE001
        out["loop11"] = False
    try:
        pr = var / "research_registry.json"
        reg = json.loads(pr.read_text(encoding="utf-8")) if pr.exists() else []
        lines = [x.get("line") for x in reg if "nkt_study.py" not in str(x.get("script") or "")
                 and ID in {str(c.get("id")) if isinstance(c, dict) else str(c) for c in (x.get("candidates") or [])}]
        out["registry"] = not lines
        out["registry_hits"] = lines
    except Exception:                                                        # noqa: BLE001
        out["registry"] = False
    if not scan_repo:
        out["ok"] = all(out[k] for k in ("previous_ids", "reserved", "loop11", "registry"))
        return out
    hits = []
    try:
        top = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip())
        files = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, check=True,
                               cwd=top).stdout.decode("utf-8", "replace").split("\0")
        known = []
        for fn in files:
            if not fn or fn in OWN_FILES or fn.startswith("quant_breakout/var/out/nkt_study") or "/var/cache/" in fn:
                continue
            p = top / fn
            try:
                b = p.read_bytes()
            except OSError:
                continue
            if b"\0" in b[:8192]:
                continue
            if ID.encode() in b:
                (known if fn in ID_COMPANION or fn in ID_DOCS else hits).append(fn)
        out["repo_hits"] = hits
        out["repo_known"] = known                                            # 同日的 WXA 与登记材料按名字提到本研究：只列出，不算重用
        out["repo"] = not hits
    except Exception as ex:                                                  # noqa: BLE001
        out["repo_hits"] = [f"（读不出：{type(ex).__name__}）"]
        out["repo"] = False
    out["ok"] = all(out[k] for k in ("previous_ids", "reserved", "loop11", "registry", "repo"))
    return out


# ───────────────────────── 只描述 ─────────────────────────
def _group(d: np.ndarray, m: np.ndarray) -> dict:
    x = d[np.asarray(m, bool)]
    return {"n": int(len(x)), "mean": float(x.mean()) if len(x) else None}


def describe(F: dict, info: dict, w, grid, DA: dict, nk_index) -> dict:
    """D1〜D7（只描述，不能升级为判定）。"""
    w = np.asarray(w, bool)
    out: dict = {"D1": {}, "D2": {}, "D3": {}, "D4": {}, "D5": {}, "D6": {}, "D7": {}}
    real = {s: eval_z(F[s], w) for s in POOLS}
    one = {s: eval_z(F[s], np.ones(len(w), bool)) for s in POOLS}
    for s in POOLS:
        nb = F[s]["nb"]
        nv, ch = real[s]
        d = nv - nb
        st = info["pools"][s]
        dc = d[ch]
        out["D1"][s] = {**{k: st[k] for k in ("n", "c", "x", "win_b", "win_v", "dwin", "dbar", "g")},
                        "median_diff": float(np.median(d)) if len(d) else None,
                        "changed_better": float((dc > LOOKUP_TOL).mean()) if len(dc) else None,
                        "changed_worse": float((dc < -LOOKUP_TOL).mean()) if len(dc) else None, "changed_mean": float(dc.mean()) if len(dc) else None,
                        "excluded": int(F[s]["excluded"])}
        big = nb <= BIG_LOSS
        out["D2"][s] = {"n": int(big.sum()), "diff_mean": float(d[big].mean()) if big.any() else None,
                        "x6_q05": float(np.quantile(nb, 0.05)) if len(nb) else None, "x6_min": float(nb.min()) if len(nb) else None,
                        "nkt_q05": float(np.quantile(nv, 0.05)) if len(nv) else None, "nkt_min": float(nv.min()) if len(nv) else None}
        o = pool_stats(nb, *one[s])
        out["D3"][s] = {"x6": 0.0, "nkt": {"dbar": st["dbar"], "g": st["g"], "dwin": st["dwin"]},
                        "always_k2": {"dbar": o["dbar"], "g": o["g"], "dwin": o["dwin"], "c": o["c"]}}
        pl = info["placebo"]["pools"][s]
        xs, ys = np.asarray(pl["x"], float), np.asarray(pl["dbar"], float)
        if len(xs) and np.isfinite(xs).all() and np.isfinite(ys).all():
            vx = float(np.var(xs))
            b = float(np.cov(xs, ys, bias=True)[0, 1] / vx) if vx > 0 else 0.0
            a = float(ys.mean() - b * xs.mean())
            es = ys - (a + b * xs)
            er = float(st["dbar"] - (a + b * st["x"])) if np.isfinite(st["x"]) else None
            reg = {"a": a, "b": b, "resid_real": er, "resid_pct": pct_of(er, es), "extrapolate": bool(st["x"] < xs.min() or st["x"] > xs.max())}
        else:
            reg = None
        out["D4"][s] = {"dbar": {**dist(pl["dbar"]), "real_pct": info["pct"][s]["dbar"]}, "g": {**dist(pl["g"]), "real_pct": info["pct"][s]["g"]},
                        "c": {**dist(pl["c"]), "real": st["c"], "real_pct": info["pct"][s]["c"]}, "x": st["x"], "regress": reg}
    out["D4"]["T"] = {**dist(info["placebo"]["T"]), "real_pct": pct_of(info["T"], info["placebo"]["T"])}
    out["D4"]["G"] = {**dist(info["placebo"]["G"]), "real_pct": pct_of(info["G"], info["placebo"]["G"])}
    out["D4"]["calendar"] = {s: {k: v for k, v in r.items() if k in ("cal_real", "cal_shift")} for s, r in exposure_dose(DA, w, grid).items()}
    out["D4"]["windows"] = window_shift_shares(nk_index, w, grid)
    out["D4"]["corr"] = info["corr"]
    FN = F["N"]
    nv, ch = real["N"]
    d = nv - FN["nb"]
    era = np.asarray(FN["era"], dtype=object)
    for e in N225_ERAS:
        m = era == e
        out["D5"][e] = {"n": int(m.sum()), "dbar": float(d[m].mean()) if m.any() else None, "g": float(d[m].sum() / max(int(ch[m].sum()), 1)) if m.any() else None}
    yr = FN["date"].year.to_numpy() if FN["n"] else np.zeros(0, int)
    out["D5"]["years"] = {str(int(y)): {"n": int((yr == y).sum()), "dbar": float(d[yr == y].mean()),
                                        "g": float(d[yr == y].sum() / max(int(ch[yr == y].sum()), 1))} for y in sorted(set(yr.tolist()))}
    dd = np.concatenate([real[s][0] - F[s]["nb"] for s in POOLS])
    cc = np.concatenate([real[s][1] for s in POOLS])
    fills = pd.DatetimeIndex(np.concatenate([F[s]["fill"].to_numpy() for s in POOLS])) if sum(F[s]["n"] for s in POOLS) else pd.DatetimeIndex([])
    for k, (a, b) in V_WINDOWS.items():
        m = cc & np.asarray((fills >= pd.Timestamp(a)) & (fills <= pd.Timestamp(b)))
        out["D6"][k] = {"window": [a, b], **_group(dd, m)}
    out["D6"]["note"] = "事后：按已知的市场历史挑的窗口，只描述"
    rs = np.asarray([r for s in POOLS for r in F[s]["x6_reason"]], dtype=object)
    grp = np.where(np.isin(rs, ["chandelier", "stop", "max_hold"]), rs, "other")
    out["D7"]["by_x6_reason"] = {g: _group(dd, cc & (grp == g)) for g in ("chandelier", "stop", "max_hold", "other")}
    sigw = np.concatenate([_at(w, weak_pos(nk_index, F[s]["date"])) if F[s]["n"] else np.zeros(0, bool) for s in POOLS])
    out["D7"]["by_signal_weak"] = {"weak": _group(dd, sigw), "not_weak": _group(dd, ~sigw)}
    return out


# ───────────────────────── 流程 ─────────────────────────
def peak_mem_mb() -> dict:
    return MUD.peak_mem_mb()


def load_w(say=print) -> tuple[dict, dict, dict]:
    """B4 的全部输入（month_up_dip_study.b_load：loop10_common.load + trendline_study.tbf_gates）。"""
    return MUD.b_load(say)


def nikkei(say=print) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    rows, info = nikkei_rows()
    state = nikkei_state(rows)
    say(f"日経 {len(state)} 行（weak {int(state['weak'].sum())} 行、NA {int((~state['known']).sum())} 行）")
    return rows, info, state


def prep(say=print) -> dict:
    """--prep：冻结缓存 + 代码指纹 + 日経状态 + 先决条件 / 接线 / 改前 vs 改后 / R1 + 池子查表与 (a)(b)(c) + 只数个数。不算、不打印任何收益。"""
    import loop11_common as LC
    t0 = time.time()
    code = check_code(strict=False)
    frozen = MUD.freeze_cache()
    rows, ninfo, state = nikkei(say)
    nk_index, w = pd.DatetimeIndex(state.index), state["weak"].to_numpy(bool)
    store: dict = {}
    live = live_fp(store)
    cpre = consts_check()
    W, tbf, tbf_pool = load_w(say)
    bt, rt = LC.bt_rt()
    pre = prereq_b4(W, tbf)
    say("B4 重算 = 参照：" + "、".join(f"{e} {'✓' if pre['same_ref'][e] else '✗'}" for e in N225_ERAS)
        + "；exit_tick 接线（8 键）：" + "、".join(f"{e} {'✓' if pre['wired'][e] else '✗'}" for e in N225_ERAS))
    wiring = hook_wiring(W, tbf, nk_index, pre["base"])
    say("钩子接线 W1〜W5：" + "；".join(f"{e} " + "".join("✓" if v else "✗" for v in r.values()) for e, r in wiring["eras"].items())
        + "；W2〜W5 逐位 = W1：" + "；".join(f"{e} " + "".join("✓" if v else "✗" for v in r.values()) for e, r in wiring["sha_eras"].items()))
    gidx, days = wiring.pop("gidx"), wiring.pop("days")
    stale = check_stale(nk_index, days)
    b4raw, here = wiring.pop("trades"), wiring.pop("sha")
    say(f"账户逐日推进的日子的最旧天数 ≤ {MAX_STALE_DAYS}：✓")
    pvp = pre_vs_post(W, tbf, store, here)
    say(f"改前 vs 改后：{'✓' if pvp['ok'] else '✗'}" + (f"（{pvp['why']}）" if pvp.get("why") else ""))
    r1 = hook_vs_params_td(W, tbf, nk_index)
    say("R1（全 2.0 = PARAMS_TD k 2）：" + "、".join(f"{e} {'✓' if v else '✗'}" for e, v in r1["eras"].items())
        + "；逐位：" + "、".join(f"{e} {'✓' if v else '✗'}" for e, v in r1["sha_eras"].items()))
    r2 = hook_positive_b4(W, tbf, nk_index, b4raw, gidx)
    say(f"R2（B4 的一笔：d 那一行 2.0 → d′ 卖；d′ 那一行 2.0 → 不变）：{'✓' if r2['ok'] else '✗'}"
        + ("" if r2["picked"] else "（没有合适的笔）"))
    P = pool_signals(W, tbf, tbf_pool)
    frames = pool_frames(W)
    t_lk = time.time()
    LK = build_lookups(P, frames, W["p0"], bt, rt, say)
    t_lk = round(time.time() - t_lk)
    sstale = check_stale(nk_index, {s: pd.DatetimeIndex(np.concatenate([L["cdates"].to_numpy() for L in LK[s] if L["paired"]] or [np.zeros(0, "datetime64[ns]")]))
                                    for s in POOLS})
    nbx = nb_exact_check(LK, frames, W["p0"], bt, rt)
    say(f"(a) nb 逐位：{'✓' if nbx['ok'] else '✗'}（{nbx['n'] - nbx['bad']} / {nbx['n']}）")
    bm = base_match_check(LK, P)
    say("(b) base_match：" + "、".join(f"{s} {'✓' if (bm[s]['frac'] or 0) >= BASE_MATCH_MIN else '✗'}（{bm[s]['match']} / {bm[s]['n']}）" for s in OTHER_POOLS))
    grid = shift_grid(len(w))
    lc = lookup_check(LK, frames, synth_z(w, grid), nk_index, W["p0"], bt, rt, say)
    DA = _dose_arrays(P, frames, nk_index, bt.exec_cfg.slippage_pct / 100)
    dose = exposure_dose(DA, w, grid)
    band = b4_band_counts(W, b4raw, nk_index, w)
    ids = id_check()
    say(f"ID 核对：{'✓' if ids['ok'] else '✗'}")
    data_fp = MUD.data_fp(fp_items(state, rows, P, frames))
    lov = live_overlap(store, rows)
    pool_ref = {s: int(len(P[s])) == int(POOL_REF[s]) for s in OTHER_POOLS}
    say("池子信号数 = 已公开（W / Jx / Zx）：" + "、".join(f"{s} {'✓' if v else '✗'}" for s, v in pool_ref.items())
        + f"；^N225 实时与缓存一致的比例 ≥ {LIVE_MIN}：{'✓' if lov['ok'] else '✗'}")
    checks = {"code": bool(code["ok"]), "b_precheck": bool(cpre["ok"]), "b4_same_ref": all(pre["same_ref"].values()),
              "exit_tick_wiring": all(pre["wired"].values()), "hook_wiring": bool(wiring["ok"]), "hook_wiring_sha": bool(wiring["sha_ok"]),
              "gidx_stale": True, "single_stale": True, "pre_vs_post": bool(pvp["ok"]), "R1": bool(r1["ok"]), "R1_sha": bool(r1["sha_ok"]),
              "R2": bool(r2["ok"]), "nb_exact": bool(nbx["ok"]), "base_match": bool(bm["ok"]), "lookup_synth": bool(lc["ok"]),
              "pool_ref": all(pool_ref.values()), "live_n225": bool(lov["ok"]), "rt": bool(abs(rt - RT_REF) < RT_TOL), "chand_none": True,
              "id_check": bool(ids["ok"])}
    counts = {"nikkei": nikkei_counts(rows, state, ninfo),
              "pools": {s: {"signals": int(len(P[s])), "with_data": int(sum(L["why"] not in ("no_data", "no_signal_row") for L in LK[s])),
                            "paired": int(sum(L["paired"] for L in LK[s])), "excluded": int(sum(L["excluded"] for L in LK[s])),
                            "x6_nan": int(sum(L["why"] == "x6_nan" for L in LK[s])), "no_fill": int(sum(L["why"] in ("no_fill", "short") for L in LK[s])),
                            "sig_weak": dose[s]["sig_weak"], "ref": POOL_REF.get(s)} for s in POOLS},
              "n_by_era": {e: int((P["N"]["era"] == e).sum()) for e in N225_ERAS}, "overlap": pool_overlap(P),
              "dose": dose, "lookup_runs": {s: int(sum(L["runs"] for L in LK[s])) for s in POOLS}, "lookup_seconds": t_lk,
              "b4_band": band, "grid": {"N": int(len(w)), "M": len(grid), "min": int(min(grid)), "max": int(max(grid)),
                                        "step": (len(w) - 2 * MIN_SHIFT) / (len(grid) - 1), "unique": len(set(grid)) == len(grid)},
              "window_shift": window_shift_shares(nk_index, w, grid),
              "stale": {"accounts": stale, "single": sstale,
                        "gidx_not_stepped": {e: int(len(pd.DatetimeIndex(gidx[e]).difference(days[e]))) for e in N225_ERAS}},
              "live": {"fp": list(live), "n225_overlap": lov, "repeat": live_repeat(store)}, "R2": r2, "pool_ref": pool_ref, "id": ids}
    prep_counts = {"checks": checks, **counts, "elapsed_s": round(time.time() - t0), "peak_mem": peak_mem_mb()}
    out = {"git": MUD.git_info(), "code": code, "frozen": frozen, "data_fp": data_fp, "b_precheck": cpre, "rt_ok": checks["rt"],
           "prereq": {"b4_same_ref": pre["same_ref"], "exit_tick_wiring": pre["wired"], "hook_wiring": wiring["eras"],
                      "hook_wiring_sha": wiring["sha_eras"], "pre_vs_post": pvp, "R1": r1["eras"], "R1_sha": r1["sha_eras"], "R2": r2,
                      "nb_exact": nbx, "base_match": bm, "lookup_synth": lc},
           "prep_counts": prep_counts, "elapsed_s": round(time.time() - t0), "peak_mem": peak_mem_mb()}
    say("核对：" + "、".join(f"{k} {'✓' if v else '✗'}" for k, v in checks.items()))
    say(f"要写进常数（登记提交）：DATA_FP = {data_fp!r}；CP_SRC_SHA = {code['cp_src_sha']!r}；KS_SRC_SHA = {code['ks_src_sha']!r}；"
        "PREP_COUNTS = 下面 JSON 的 prep_counts")
    return out


def prep_ok(pc: dict | None) -> list[str]:
    """PREP_COUNTS 里 --prep 的核对：没登记 / 缺项 / 有 ✗ → 返回问题列表。"""
    if not pc:
        return ["PREP_COUNTS 还没登记"]
    ch = pc.get("checks") or {}
    return [k for k in PREP_CHECKS if ch.get(k) is not True]


def run(say=print, save=None) -> dict:
    """--run（只运行一次）：见文件开头十二。save(res) = 把到那时为止的结果写进 partial。第 3 步之后出错 → 照实记下、照常返回。"""
    import loop11_common as LC
    t0 = time.time()
    save = save or (lambda r: None)
    code = check_code(strict=True)
    if DATA_FP is None or PREP_COUNTS is None:
        raise SystemExit("DATA_FP / PREP_COUNTS 还没登记（先 --prep，写进常数并提交）→ 停")
    bad = prep_ok(PREP_COUNTS)
    if bad:
        raise SystemExit(f"PREP_COUNTS 里 --prep 的核对不全是 ✓：{bad} → 停")
    cpre = consts_check()
    if not cpre["ok"]:
        raise SystemExit(f"先决条件不过（{'；'.join(cpre['why'])}）→ 停（还没有算任何结果）")
    regs = reg_status()
    if not regs["ok"]:
        raise SystemExit(f"登记状态不对（{'；'.join(regs['why'])}）→ 停（还没有算任何结果）")
    frozen = MUD.freeze_cache()
    git = MUD.git_info()
    rows, ninfo, state = nikkei(say)
    nk_index, w = pd.DatetimeIndex(state.index), state["weak"].to_numpy(bool)
    store: dict = {}
    live = live_fp(store)                                                   # 只记录：实时序列指纹 + ^N225 与缓存一致的比例（不作为停止条件）
    W, tbf, tbf_pool = load_w(say)
    lov = live_overlap(store, rows)
    lrep = live_repeat(store)
    live_fp(None)                                                           # 之后不再存副本（省内存）
    P = pool_signals(W, tbf, tbf_pool)
    frames = pool_frames(W)
    fp = MUD.data_fp(fp_items(state, rows, P, frames))
    if fp != DATA_FP:
        raise SystemExit(f"数据指纹 {fp} ≠ 登记的 {DATA_FP}（缓存变了）→ 停")
    bt, rt = LC.bt_rt()
    if abs(rt - RT_REF) >= RT_TOL:
        raise SystemExit(f"成本 RT 和登记的 {RT_REF} 差太多 → 停")
    # 第 2 步：只涉及 X6 基准（不过 → 停、不写任何输出）
    pre = prereq_b4(W, tbf)
    if not (pre["ok"] and all(pre["same_ref"].values()) and all(pre["wired"].values())):
        raise SystemExit("B4 重算 / exit_tick 接线不过 → 停（还没有任何 NKT 结果；可以运行前修正）")
    wiring = hook_wiring(W, tbf, nk_index, pre["base"])
    if not (wiring["ok"] and wiring["sha_ok"]):
        raise SystemExit("钩子接线 W1〜W5（8 键 / 逐位）不过 → 停（还没有任何 NKT 结果）")
    gidx, days = wiring.pop("gidx"), wiring.pop("days")
    stale = check_stale(nk_index, days)
    b4raw = wiring.pop("trades")
    wiring.pop("sha")
    # 正向对照 R1 / R2 重做（不碰真实 z）：钩子能不能生效还取决于 CP_SRC_SHA 管不到的代码（qbreak/unified.py 的 _check_exits 经 self._p(t) 取离场参数、
    # MixEngine 的父类链）；W1〜W5 的序列本来就不改变结果，钩子悄悄失效时照样全部 ✓ → 这里不过就停（还没写 partial = 运行前可修正）
    r1 = hook_vs_params_td(W, tbf, nk_index)
    r2 = hook_positive_b4(W, tbf, nk_index, b4raw, gidx)
    del b4raw
    if not (r1["ok"] and r1["sha_ok"] and r2["ok"]):
        raise SystemExit("正向对照 R1 / R2 不过（钩子可能没有生效）→ 停（还没有任何 NKT 结果；可以运行前修正）")
    say("先决条件：B4 = 参照 ✓、接线 ✓、最旧天数 ✓、正向对照 R1 ✓ R2 ✓")
    LK = build_lookups(P, frames, W["p0"], bt, rt, say)
    sstale = check_stale(nk_index, {s: pd.DatetimeIndex(np.concatenate([L["cdates"].to_numpy() for L in LK[s] if L["paired"]] or [np.zeros(0, "datetime64[ns]")]))
                                    for s in POOLS})
    nbx = nb_exact_check(LK, frames, W["p0"], bt, rt)
    bm = base_match_check(LK, P)
    if not (nbx["ok"] and bm["ok"]):
        raise SystemExit("nb 逐位 / base_match 不过 → 停（只涉及 X6 基准；可以运行前修正）")
    say("nb 逐位 ✓、base_match ✓")
    grid = shift_grid(len(w))
    pchk = PREP_COUNTS.get("checks") or {}
    res: dict = {"registered": registered(), "git": git, "code": code, "reg_status": regs, "data_fp": fp, "frozen": frozen, "live_fp": list(live),
                 "live_overlap": lov, "live_repeat": lrep, "rt": rt,
                 "prereq": {"consts": cpre, "b4": {"same_ref": pre["same_ref"], "base": pre["base"]}, "exit_tick_wiring": pre["wired"],
                            "wiring": wiring["eras"], "wiring_sha": wiring["sha_eras"], "gidx_stale": stale,
                            "gidx_not_stepped": {e: int(len(pd.DatetimeIndex(gidx[e]).difference(days[e]))) for e in N225_ERAS},
                            "single_stale": sstale, "nb_exact": nbx, "base_match": bm,
                            "R1": bool(r1["ok"]), "R1_sha": bool(r1["sha_ok"]), "R2": bool(r2["ok"]),
                            "R1_eras": r1["eras"], "R1_sha_eras": r1["sha_eras"], "R2_detail": r2,     # --run 第 2 步重做的（--prep 的在 PREP_COUNTS）
                            **{k: pchk.get(c) for k, c in (("pre_vs_post", "pre_vs_post"), ("lookup_check_synth", "lookup_synth"),
                                                           ("pool_ref", "pool_ref"), ("live_n225", "live_n225"))}},
                 "counts": {s: {"signals": int(len(P[s])), "paired": int(sum(L["paired"] for L in LK[s])),
                                "excluded": int(sum(L["excluded"] for L in LK[s])), "runs": int(sum(L["runs"] for L in LK[s]))} for s in POOLS},
                 "verdict": STOP_ERROR}
    # 第 3 步：第一次碰真实 z 之前先写 partial —— 之后被 Ctrl-C / 杀掉 / 内存不够，也留下记录（算跑过：照实记录、由用户决定，不重跑）
    res["info"] = {"started": STARTED_3}
    res["say"] = say_verdict(STOP_ERROR, False)
    res["elapsed_s"] = round(time.time() - t0)
    save(res)

    def _fail(ex: BaseException, key: str, verdict: str) -> None:
        """第 3 步之后出错：只照实记下（异常类型名 + 代码位置），先写 partial；Ctrl-C 等（不是 Exception / SystemExit）写完再往上抛。"""
        res[key] = {"error": MUD.err_info(ex), "started": STARTED_3} if key == "info" else {"error": MUD.err_info(ex)}
        res["verdict"] = verdict
        inf = res.get("info") if isinstance(res.get("info"), dict) else {}
        res["say"] = say_verdict(verdict, bool(inf.get("dose_outside")))          # 账户层出错：信息检查已经通过 → 有剂量限定时照样加限定语
        res["elapsed_s"] = round(time.time() - t0)
        save(res)
        if not isinstance(ex, (Exception, SystemExit)):
            raise ex

    try:
        lc = lookup_check(LK, frames, {"real": w}, nk_index, W["p0"], bt, rt, say)
        res["prereq"]["lookup_check_real"] = lc
        if not lc["ok"]:
            res["info"] = {"stopped": "真实 z 的查表 = 直接跑不过：不出判定（这次运行算用掉）"}
            res["verdict"] = STOP_LOOKUP
            res["say"] = say_verdict(STOP_LOOKUP, False)
            res["elapsed_s"] = round(time.time() - t0)
            save(res)
            return res
        F = {s: flatten(LK[s], nk_index) for s in POOLS}
        info = info_check(F, w, grid, say)
        res["info"] = info
        res["verdict"] = info["verdict"]
        res["say"] = say_verdict(info["verdict"], bool(info.get("dose_outside")), (info.get("mde") or {}).get("T"), (info.get("mde") or {}).get("G"))
        res["elapsed_s"] = round(time.time() - t0)
        save(res)
        say("信息检查完成（判定只写在文件里）")
    except BaseException as ex:                                              # noqa: BLE001
        _fail(ex, "info", STOP_ERROR)
        return res
    if info["verdict"] == INFO_PASS:
        try:
            acc = account_stage(W, tbf, k_series(state), info["pools"], pre["base"], say=lambda m: None)   # 不打印进度：账户层在跑本身就透露了信息检查的判定
            res["account"] = acc
            res["verdict"] = acc["verdict"]
        except BaseException as ex:                                          # noqa: BLE001
            _fail(ex, "account", STOP_ACCOUNT)
        res["elapsed_s"] = round(time.time() - t0)
        save(res)
    else:
        res["account"] = {"note": "信息检查不过 → 不进账户层（没有计算）"}
    try:
        DA = _dose_arrays(P, frames, nk_index, bt.exec_cfg.slippage_pct / 100)
        res["describe"] = describe(F, info, w, grid, DA, nk_index)
    except BaseException as ex:                                              # noqa: BLE001
        res["describe"] = {"error": MUD.err_info(ex)}
        if not isinstance(ex, (Exception, SystemExit)):
            save(res)
            raise
    res["say"] = say_verdict(res["verdict"], bool(info.get("dose_outside")), (info.get("mde") or {}).get("T"), (info.get("mde") or {}).get("G"))
    res["elapsed_s"] = round(time.time() - t0)
    res["peak_mem"] = peak_mem_mb()
    return res

REGISTERED = ("ID", "FAMILY", "K_BASE", "K_WEAK", "NK_TICKER", "NK_YEARS", "MAX_STALE_DAYS", "END_BARS", "MAX_HOLD", "POOLS", "POOL_FOLD", "POOL_SM",
              "POOL_ERA", "N225_ERAS", "OTHER_POOLS", "MIN_SHIFT", "N_SHIFT", "Q", "DOSE_Q", "MIN_CHANGED", "MIN_TRIG", "POSTHOC", "EPS", "FP", "B4_TOL",
              "B4_REF", "RT_REF", "RT_TOL", "BASE_MATCH_MIN", "BASE_MATCH_TOL", "LOOKUP_TOL", "LIVE_TOL", "SYNTH_Z", "SYNTH_ROLL", "W5_CUT", "DOSE_ROWS",
              "BIG_LOSS", "V_WINDOWS", "NK_WINDOWS", "JPX_FROM", "POOL_REF", "B4_TRADES_REF", "STOCK_SKIP", "SLOPE_BARS", "ZERO_VOL_ENV", "KLINE_SRC_SHA",
              "KS_SRC_SHA", "CP_SRC_SHA", "PRE_REV", "PRE_CP_SHA1", "DATA_FP", "PREP_COUNTS", "PREP_CHECKS", "OWN_FILES", "ID_COMPANION", "ID_DOCS",
              "INFO_LABELS", "ACCT_LABELS", "DOSE_LABELS", "LIVE_MIN", "R2_MARGIN", "WXA_REQUIRED", "WXA_SCRIPT", "SELF_FILES", "STARTED_3",
              "VERDICT_SAY", "DOSE_NOTE", "EXPECT")


def registered() -> dict:
    """json 的 registered：全部登记常数。"""
    g = globals()
    return {k: g[k] for k in REGISTERED}


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:+.3f}") -> str:
    try:
        return "—" if v is None or not np.isfinite(float(v)) else fmt.format(float(v))
    except (TypeError, ValueError):
        return "—"


def _ck(v) -> str:
    return "✓" if v is True else ("✗" if v is False else "—")


def report(res: dict) -> str:
    """md（十三）：开头（代码 rev、指纹、先决条件）→ 〇 一句话 → 一 信息检查 → 二 账户第一关 → 三 只描述 → 四 登记前个数对照 → 五 局限。"""
    g = res.get("git") or {}
    info = res.get("info") or {}
    pre = res.get("prereq") or {}
    L = ["# 日経转弱的日子，把持仓的吊灯止损从 3×ATR 收到 2×ATR（NKT；只运行一次）", "",
         f"代码 {g.get('rev', '?')}" + (f"（scripts/ 或 qbreak/ 下有未提交的改动：{', '.join(g.get('dirty_files') or [])}）" if g.get("dirty") else "")
         + f"；DATA_FP {res.get('data_fp')}；规则指纹 {(pre.get('consts') or {}).get('fingerprint')}（登记 {FP}）；"
         f"代码指纹 kline {(res.get('code') or {}).get('kline_src_sha')} / kline_series {(res.get('code') or {}).get('ks_src_sha')} / "
         f"candle_portfolio {(res.get('code') or {}).get('cp_src_sha')}；实时序列 {len(res.get('live_fp') or [])} 条（见 json live_fp）；"
         f"^N225 实时与缓存一致的比例 {_f((res.get('live_overlap') or {}).get('frac'), '{:.4f}')}"
         f"（登记前 {_f((((res.get('registered') or {}).get('PREP_COUNTS') or {}).get('live') or {}).get('n225_overlap', {}).get('frac'), '{:.4f}')}；只记录）。",
         "先决条件：B4 = 参照 " + "、".join(f"{e} {_ck(((pre.get('b4') or {}).get('same_ref') or {}).get(e))}" for e in N225_ERAS)
         + "；exit_tick 接线 " + "、".join(f"{e} {_ck((pre.get('exit_tick_wiring') or {}).get(e))}" for e in N225_ERAS)
         + "；钩子接线 W1〜W5 " + "、".join(f"{e} " + "".join(_ck(v) for v in ((pre.get('wiring') or {}).get(e) or {}).values()) for e in N225_ERAS)
         + "（W2〜W5 逐位 = W1 " + "、".join(f"{e} " + "".join(_ck(v) for v in ((pre.get('wiring_sha') or {}).get(e) or {}).values()) for e in N225_ERAS)
         + f"）；nb 逐位 {_ck((pre.get('nb_exact') or {}).get('ok'))}；base_match {_ck((pre.get('base_match') or {}).get('ok'))}；"
         f"正向对照 R1 {_ck(pre.get('R1'))}（逐位 {_ck(pre.get('R1_sha'))}）、R2 {_ck(pre.get('R2'))}（--prep 与 --run 都做）；"
         f"（--prep）改前 vs 改后 {_ck(pre.get('pre_vs_post'))}、"
         f"查表 = 直接跑（6 个非真实序列）{_ck(pre.get('lookup_check_synth'))}、池子信号数 = 已公开 {_ck(pre.get('pool_ref'))}、"
         f"^N225 实时与缓存一致 {_ck(pre.get('live_n225'))}；"
         f"查表 = 直接跑（真实）{_ck((pre.get('lookup_check_real') or {}).get('ok'))}。",
         "判定规则摘要：四个池子（N / W / Jx / Zx）的假想单笔「NKT − X6」配对；T = 四个 d̄ 等权、G = 四个 g 等权；"
         "四个 d̄ 都 > 0、T 与 G 都严格超过 400 次整段循环平移的 95 分位、每个池子换卖点 ≥ 20 笔 → 进账户层第一关（research_loop11.stage1，posthoc）。", "",
         "## 〇 一句话", "", f"**{res.get('verdict')}**：{res.get('say', '')}", ""]
    if info.get("pools"):
        L += ["## 一 信息检查", "", "| 池子 | 配对 | 换卖点 c | x | X6 胜率 | NKT 胜率 | d̄（pp/笔） | g（pp） | 平移 d̄ 中位 / 95 分位 | d̄ 真实分位 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for s in POOLS:
            p = info["pools"][s]
            pl = info["placebo"]["pools"][s]["dbar"]
            L.append(f"| {s} | {p['n']} | {p['c']} | {_f(p['x'], '{:.3f}')} | {_f(p['win_b'], '{:.1f}')}% | {_f(p['win_v'], '{:.1f}')}% | {_f(p['dbar'])} | "
                     f"{_f(p['g'])} | {_f(np.median(pl))} / {_f(np.quantile(pl, Q))} | {_f(info['pct'][s]['dbar'], '{:.2f}')} |")
        co = info.get("corr") or {}
        L += ["", f"T = {_f(info['T'])} pp/笔（平移 95 分位 {_f(info.get('q95_T'))}；经验 p {_f(info.get('p_T'), '{:.4f}')}）；"
                  f"G = {_f(info['G'])} pp（平移 95 分位 {_f(info.get('q95_G'))}；经验 p {_f(info.get('p_G'), '{:.4f}')}）。",
              f"相邻平移的相关：T 的 L {_f((co.get('T') or {}).get('L'), '{:.1f}')} 行、K_eff {_f((co.get('T') or {}).get('K_eff'), '{:.1f}')}、"
              f"最小可达 p {_f((co.get('T') or {}).get('p_min'), '{:.4f}')}；G 的 L {_f((co.get('G') or {}).get('L'), '{:.1f}')} 行、"
              f"K_eff {_f((co.get('G') or {}).get('K_eff'), '{:.1f}')}。检出力 MDE_T {_f((info.get('mde') or {}).get('T'))} pp/笔、"
              f"MDE_G {_f((info.get('mde') or {}).get('G'))} pp。剂量在平移 5〜95% 之外：{'是' if info.get('dose_outside') else '否'}。",
              f"信息检查判定：**{info.get('verdict')}**（{info.get('why')}）；查表 NaN 剔除：{info.get('excluded')}。", ""]
    elif info:
        L += ["## 一 信息检查", "", f"没有完成：{info.get('stopped') or info.get('error')}", ""]
    acc = res.get("account")
    L += ["## 二 账户第一关", ""]
    if acc and acc.get("cand"):
        L += ["| 年代 | Calmar（B4 → 候选） | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|"]
        for e in N225_ERAS:
            b, c = acc["base"][e], acc["cand"][e]
            L.append(f"| {e} | {_f(b.get('calmar'))} → {_f(c.get('calmar'))} | {_f(b.get('dd'), '{:.2f}')} → {_f(c.get('dd'), '{:.2f}')}% | "
                     f"{_f(c.get('h1'))} / {_f(c.get('h2'))} | {b.get('n')} → {c.get('n')} | {_f(b.get('win'), '{:.1f}')} → {_f(c.get('win'), '{:.1f}')}% | "
                     f"{_f(b.get('mean'), '{:+.2f}')} → {_f(c.get('mean'), '{:+.2f}')}% |")
        s1 = acc["stage1"]
        import research_loop11 as R11
        if acc.get("verdict") == ACCT_LABELS[0]:                             # 几乎不触发：不下第一关结论（stage1 只记在 json，作描述）
            s1_line = "几乎不触发 → 不下第一关结论（stage1 只记在 json，作描述）"
        else:
            s1_line = ("；".join(f"路线 {r} " + "、".join(f"{k} {_ck(bool(s1['routes'][r][k]))}" for k in R11.CHECKS[r]) for r in ("A", "B"))
                       + f" → {'过（' + '、'.join(s1['ok_routes']) + '）' if s1['ok'] else '不过'}")
        L += ["", f"提前卖出的笔数（Z + E + J）：{acc['trig']}（< {MIN_TRIG} →「几乎不触发」）。第一关：{s1_line}。账户层判定：**{acc['verdict']}**。",
              "V4 / V6 用的池子配对（信息检查的同一组数，未四舍五入）：" + "；".join(
                  f"{x} 换卖点 {v['changed']}、胜率差 {_f(v['dwin'], '{:+.2f}')} pp、每笔差 {_f(v['dmean'])} pp"
                  for x, v in (other_of(info["pools"]) if info.get("pools") else {}).items()), ""]
    else:
        L += [str((acc or {}).get("note") or (acc or {}).get("error") or "没有计算"), ""]
    d = res.get("describe") or {}
    L += ["## 三 只描述（D1〜D8；不能升级为判定）", ""]
    if d.get("D1"):
        L += ["- D1 每个池子：" + "；".join(f"{s} 配对 {v['n']}、换卖点 {v['c']}（变好 {_f(v['changed_better'], '{:.0%}')} / 变差 {_f(v['changed_worse'], '{:.0%}')}、"
                                          f"平均 {_f(v['changed_mean'])}）、中位差 {_f(v['median_diff'])}" for s, v in d["D1"].items()),
              "- D2 大跌（X6 ≤ −7%）：" + "；".join(f"{s} {v['n']} 笔、NKT − X6 {_f(v['diff_mean'])}；5% 分位 X6 {_f(v['x6_q05'], '{:+.2f}')} / "
                                                f"NKT {_f(v['nkt_q05'], '{:+.2f}')}、最小 {_f(v['x6_min'], '{:+.2f}')} / {_f(v['nkt_min'], '{:+.2f}')}"
                                                for s, v in d["D2"].items()),
              "- D3 三档（X6 = 0 / NKT / 一直 k 2）的 d̄：" + "；".join(f"{s} 0 / {_f(v['nkt']['dbar'])} / {_f(v['always_k2']['dbar'])}" for s, v in d["D3"].items()),
              "- D4 剂量回归（d̄_s = a + b·x_s）的真实残差与分位：" + "；".join(
                  f"{s} {_f((v.get('regress') or {}).get('resid_real'))}（{_f((v.get('regress') or {}).get('resid_pct'), '{:.2f}')}"
                  f"{'、外推' if (v.get('regress') or {}).get('extrapolate') else ''}）；c 真实 {v['c'].get('real')} / 平移 {_f(v['c'].get('q05'), '{:.0f}')}〜"
                  f"{_f(v['c'].get('q95'), '{:.0f}')}" for s, v in d["D4"].items() if s in POOLS),
              "  日历剂量（成交日起 60 行 weak 占比）真实 / 平移中位：" + "；".join(
                  f"{s} {_f(v['cal_real'], '{:.3f}')} / {_f(v['cal_shift'].get('median'), '{:.3f}')}" for s, v in d["D4"]["calendar"].items()),
              "- D5 N 池子按年代：" + "；".join(f"{e} {v['n']} 个 d̄ {_f(v['dbar'])} g {_f(v['g'])}" for e, v in d["D5"].items() if e in N225_ERAS),
              "- D6 V 形反弹窗口（事后、只描述）：" + "；".join(f"{k} {v['n']} 笔 {_f(v['mean'])}" for k, v in d["D6"].items() if k != "note"),
              "- D7 换卖点按 X6 原来的离场原因：" + "；".join(f"{k} {v['n']} 笔 {_f(v['mean'])}" for k, v in d["D7"]["by_x6_reason"].items())
              + "；信号日 weak / 不 weak 的 d̄：" + " / ".join(f"{_f(v['mean'])}（{v['n']}）" for v in d["D7"]["by_signal_weak"].values())]
    elif d.get("error"):
        L.append(f"出错：{d['error']}")
    if acc and acc.get("describe"):
        L.append("- D8 提前卖出：" + "；".join(f"{e} {v['early']} 笔" + (f"（B4 胜率 {_f(v['win_b'], '{:.0f}')}% → {_f(v['win_c'], '{:.0f}')}%、"
                                                                   f"每笔 {_f(v['mean_b'], '{:+.2f}')} → {_f(v['mean_c'], '{:+.2f}')}%）" if v["early"] else "")
                                          for e, v in acc["describe"].items()))
    pc = (res.get("registered") or {}).get("PREP_COUNTS") or {}
    L += ["", "## 四 登记前个数对照", "",
          "池子信号 / 配对 / 查表 NaN 剔除（登记前 → 运行时）：" + "；".join(
              f"{s} {((pc.get('pools') or {}).get(s) or {}).get('signals')} / {((pc.get('pools') or {}).get(s) or {}).get('paired')} / "
              f"{((pc.get('pools') or {}).get(s) or {}).get('excluded')} → {(res.get('counts') or {}).get(s, {}).get('signals')} / "
              f"{(res.get('counts') or {}).get(s, {}).get('paired')} / {(res.get('counts') or {}).get(s, {}).get('excluded')}" for s in POOLS),
          "持仓剂量代理（登记前，真实 / 平移 5〜95%）：" + "；".join(
              f"{s} {(((pc.get('dose') or {}).get(s) or {}).get('hold_real'))} / {_f((((pc.get('dose') or {}).get(s) or {}).get('hold_shift') or {}).get('q05'), '{:.0f}')}"
              f"〜{_f((((pc.get('dose') or {}).get(s) or {}).get('hold_shift') or {}).get('q95'), '{:.0f}')}" for s in POOLS)
          + f"；B4 持有期碰到「weak 且在吊灯带里」的笔数（登记前）{(pc.get('b4_band') or {}).get('total')}。",
          f"事前预期：{EXPECT}。", "",
          "## 五 局限与结论上限", "",
          "样本小（B4 114 笔）；池子不是没看过的数据；平移安慰剂只处理到一阶、相邻平移高度相关（K_eff 远小于 400）、单侧 5%；单笔 ≠ 账户；"
          "指数缺 3 个交易日、牛熊 / 汇率序列联网读取；定义单一（面板日K「下降」）；成本只扣来回手续费；V4 / V6 与信息检查不独立。",
          "信息检查最多「通过 → 进账户层」（有剂量限定语时最多「和随便挑日子收紧不同」）；账户第一关最多「第一关通过（要另行登记第二关）」；两关都过最多「更好候选」。"
          "任何结果都不自动改模拟盘 / 执行器 / 例行任务 / 面板 / 参数；进模拟盘要用户在对话里明确同意并记进 sim_changes.md。", "",
          f"用时 {res.get('elapsed_s')} s。只有汇总统计，没有个股名单和逐笔价格。非投资建议。"]
    return "\n".join(L) + "\n"


def out_dir() -> Path:
    """结果只写在 var/out（不能换目录）。"""
    return MUD.out_dir()


def run_guard(d: Path) -> None:
    """只运行一次：.json / .partial.json / .md、.json.tmp / .partial.json.tmp 任何一个已经存在 → 停。"""
    for f in (OUT_JSON, OUT_PARTIAL, OUT_MD, OUT_JSON + ".tmp", OUT_PARTIAL + ".tmp"):
        if (d / f).exists():
            raise SystemExit(f"{d / f} 已经存在（只运行一次；中途停下的也算跑过：照实记录、由用户决定，不重跑）→ 停")


def write_json(path: Path, obj) -> None:
    MUD.write_json(path, obj)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NKT：日経转弱的日子把吊灯止损收到 2×ATR（--prep 只数个数；--run 只运行一次）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prep", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    t0 = time.time()
    say = lambda s_: print(f"{s_}；{time.time() - t0:.0f}s", flush=True)     # noqa: E731
    if a.prep:
        out = prep(say)
        print(json.dumps(out, ensure_ascii=False, indent=1, default=MUD._jsonable))
        return 0
    d = out_dir()
    run_guard(d)
    d.mkdir(parents=True, exist_ok=True)
    res = run(say, save=lambda r: write_json(d / OUT_PARTIAL, r))
    write_json(d / OUT_JSON, res)                                            # 先写 json（md 生成出错也不丢结果）
    (d / OUT_MD).write_text(report(res), encoding="utf-8")
    (d / OUT_PARTIAL).unlink(missing_ok=True)
    print(f"完成：{d / OUT_JSON}、{d / OUT_MD}（判定和数字只在文件里）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
