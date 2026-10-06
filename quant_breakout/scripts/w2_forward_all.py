"""w2_forward_all.py — W2 的全市场前向检验（2026-09-27 事先登记；用户：「登记 W2 前向记录，加全市场版」）。

来由：W2（周线量比 ≥ 1.0 的突破才买，2026-09-27 启用）的证据都来自看过多次的历史数据（allstock_posthoc：全市场 2016〜2026
每笔 +0.25% vs +0.10%，11 年里 9 年更好；成交额低的三分之一没有效果）。日経225 + 扩大池的每日记录（scripts/score_forward.py 第八节）
每年只有约 250 笔，要很多年才有结论 → 这里在全市场（每年约 1,000 笔）上用**登记之后才发生的数据**检验，规则现在写定，以后不改。

一、对象
  东证一般市场（プライム / スタンダード / グロース）的内国普通股：信号日严格早于那天的最近一个月末上市一览（scripts/allstock_data.py
  同一口径；TOKYO PRO MARKET 与 ETF 等不算）；信号 = 现行突破（参数 = 复核时的现行日本参数去掉 W2，与 score_forward 第八节同一口径），
  信号日 ≥ 2026-09-28。
  主：信号日的 20 天平均成交额（收盘 × 成交量，allstock_study 的 lturn）≥ ¥500 万；另报：不限成交额的全部。
二、结果：每只票单独、一次一仓、现行卖出规则、扣立花 ¥25 万一笔的来回成本（allstock_study.train_all 同一套）；只算已平仓的。
三、分组：W2 保留（周线量比 ≥ 1.0 或缺值）/ 挡掉（< 1.0）；周线量比 = qbreak/mtf.py weekly_volume_ratio（东证日历补下一个交易日），
  与实盘 W2 同一个定义；门槛 1.0 在这里写定，不跟着参数变。
四、判定（每年一次：复核日第一次到达 2027-09-28、2028-09-28、2029-09-28、2030-09-28、2031-09-28 之后的那次复核；其他时候只报告进度）
  差 = 保留 − 挡掉的每笔平均净收益 pp；区间 = 按信号月聚类的自助法 2,000 次（种子 20260927）。都用主对象（成交额 ≥ ¥500 万）：
  失效警报：「挡掉 − 保留」的 95% 区间下限 > 0 → 提议关掉 W2；
  证实：「保留 − 挡掉」的 99% 区间下限 > 0 → 记为「新数据证实 W2」。
  另报（不判定）：不限成交额的全部、日経225（今天的成分）与其他、各年的笔数 / 胜率 / 每笔。
  检出力（每年约 1,000 笔、每笔标准差约 5.9%、保留约 45%；80%）：每笔差 1 pp 约 1〜1.3 年、0.5 pp 约 4.5 年、0.3 pp 约 12 年。
  警报 / 证实都只是提议：改模拟盘与执行器要用户在对话里确认，并记 var/sim_changes.md。
五、数据：J-Quants（批量日线 + 月末上市一览）；复核时先补齐本地缓存（原始数据只在 var/cache/jquants/，不入库）。
  输出（只有统计）：var/out/w2_forward_all_review.md / .json；var/out/w2_forward_all_history.csv（只追加：每次复核一行、判定过的年份）。
六、复核：python scripts/w2_forward_all.py --review（要 J-Quants 的键；Mac：bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python
  scripts/w2_forward_all.py --review）。
七、追加登记 K2 / USW（2026-09-27 同日；用户「F 前向记录」；定义 qbreak/idio_forward.py，与 scripts/score_forward.py 第九节同一规则）
  每笔登记之后的交易另算：突破日量比（J-Quants 成交量，之前 20 日均量）、对日経225 的 β（信号周之前一周为止 104 周的周收益回归，
  日経225 用 yfinance）、K2 标记；所在東証 33 业种（复核时最新的月末上市一览 S33Nm）→ 美国对应行业 12 个月强弱百分位、USW 标记。
  假设与判定（主对象）：K2：全部突破里 K2 = 1 的每笔净收益 > 其余；USW：W2 保留里 USW = 1 的 > 其余（us12 缺值不算）；
  每年一次（与 W2 同一组日期）：证实 = 99% 区间下限 > 0；否定 = 反向 95% 区间下限 > 0；其他时候只报告进度。另报日経225 / 其他。
  检出力（主对象每年约 1,000 笔）：K2 差 1.5 pp、USW 差 2 pp 各约 1 年。证实 / 否定都只是记录，改规则要另写登记的研究并经用户确认。
八、追加登记 卖法 X6「吊灯止损」（2026-09-28，用户「㉛ 选 ① 走前向记录」；与 scripts/score_forward.py 第十节同一做法，qbreak/exit_forward.py）
  - 对象：复核时用同一份 J-Quants 行情，给登记之后有已平仓交易的票重建指标表（现行参数去掉 W2），信号日 ≥ 2026-09-28、上市一览是一般市场
    的日子的全部突破；每个信号单独配对模拟（现行 / 只把死叉换成吊灯止损：最高价从买入价起算、当天的 Wilder ATR14、k = 3；其余卖法两边相同），
    只用成熟的配对（信号日之后 ≥ 65 根 K 线、两边都已平仓）。W2 标记（周线量比 ≥ 1.0 或缺值 = 保留）与主对象（成交额 ≥ ¥500 万）同第一〜三节。
  - 主假设（事先方向：X6 每笔 > 现行）：主对象里 W2 保留的成熟配对，配对差（X6 − 现行 的净收益 pp）的平均；
    区间 = 按信号月聚类的自助法 2,000 次（种子 20260928）。判定（每年一次，与 W2 同一组日期 2027-09-28 … 2031-09-28 之后的那次复核；
    做过的年份不再做）：证实 = 99% 区间下限 > 0；否定 = 95% 区间上限 < 0（→ 结束跟踪，记录照留）；其他 = 未定。
  - 次假设（只报告倾向，不单独作为任何依据）：主对象里不管 W2 的全部突破，配对差的 95% 区间下限 > 0。
    另报（不判定）：不限成交额（W2 保留）、主对象里的日経225 股票池（W2 保留）；两边的胜率 / 每笔 / 持有中位、X6 的出场原因。
  - 检出力（按 E / J 校准外推，scripts/x6_forward_calib.py；99% 下限 > 0、80%）：主对象 W2 保留每年约 450 笔 → 差 1 pp 约 1.6〜2 年、
    0.5 pp 约 6〜8 年；不管 W2 的全部每年约 1,000 笔 → 差 1 pp 约 0.6〜0.9 年。小盘股波动更大，实际多半更慢。
  - 证实也只是记录：改模拟盘另写一份事先登记的组合研究，并经用户确认。算不了（例外）→ 报告里写原因，不影响第一〜七节。
九、追加登记 卖出判定 R4「抛物线 SAR 翻转代替死叉」（2026-09-28；与 scripts/score_forward.py 第十一节同一做法与判定，qbreak/exit_forward.py）
  - 对象与配对同第八节（同一批配对多跑一边：只把死叉换成 SAR 从价格下方翻到上方的那天收盘）；主对象里 W2 保留、成熟、两边都已平仓的配对。
  - 判定（每年一次，与第八节同一组日期；做过的年份不再做）：证实 = 胜率差 99% 区间下限 > 0 且每笔差 95% 区间下限 > −0.30 pp；
    否定 = 胜率差 95% 区间上限 < 0 或每笔差 95% 区间上限 < −0.30 pp；其他 = 未定。另报：主对象里不管 W2 的全部、不限成交额、日経225 部分。
  - 来由与局限：卖出判定确认里事后看到（胜率 +4.2 pp、每笔 −0.03 pp，没看过的数据）；2006〜2016 日経225 不一致 → 只能靠这里的新数据。
    检出力（胜率差 +4 pp，99% 下限、80%）：主对象 W2 保留每年约 450 笔 → 约 2 年。证实也只是记录，改模拟盘要另做登记的组合研究并经用户确认。
十、追加登记 第十个研究循环最接近的三个选股闸门 HWN / X2G / JRM（2026-10-05，用户「把 HWN、X2G、JRM 加进前向检验」；只记录、不交易；
  定义与统计 qbreak/gate_forward.py）
  - 来由：第十个研究循环（scripts/research_loop10.py：20 / 20 用完、没找到「胜率提高、账户不变差」的更好候选）最接近的三个 ——
    HWN（5〜10 月不开新仓；Halloween 效应，不是事后）合起来胜率 +3.94 pp、六个样本都同方向，只差 V3（Z 账户 −0.350）；
    X2G（x2 ≤ 0 不买；事后）+3.88 pp，只差 V3（Z −0.132）；JRM（日経落后核心 ≥ 10 pp 的日子不开新仓；事后）+3.17 pp、三个年代账户都更好，
    只差 V6（Zx −0.96 pp）。都是在看过多次的历史数据上找到的 → 只有登记之后才发生的信号才是真正的样本外。
  - 对象：第八节的配对（同一份 J-Quants 行情、同一批信号）里信号日 ≥ 2026-10-06（登记日的下一个东证交易日）、成熟、两边都已平仓的；
    结果 = X6 那一边的净收益（模拟盘 2026-09-30 起的离场 = X6；与第十个循环 V4 / V6 的「假想单笔」同一个结果定义）。
    主样本 = 主对象（成交额 ≥ ¥500 万）里 W2 保留的（B3 只买 W2 保留的）。照实写：C 只作用在日経225，这里不加（与研究的 V4 池子差一个 C）。
  - 三个闸门（定义照第十个循环登记、运行过的代码，一个字不改；1 = 挡）：HWN 信号日的月份在 5〜10 月；X2G x2 ≤ 0（x2 = 复核时最新的
    月末上市一览的 33 业种 → qbreak/score_forward.x2_load / x2_lookup：信号日当天或之前已可用的最近一次短観；缺值 → 不挡）；
    JRM 日経225（^N225）最近 60 个交易日涨幅 − 1545 同期涨幅 ≤ −0.10（1545 = yfinance 1545.T 的真实收盘；研究里是合成价 = 纳指总收益 ×
    美元日元，60 天涨幅上差别很小；一天变动超过 ±30% 的当作没调整的分割、那一天的变动记为 0；核心按日経的日子取之前最后一个值；
    不够 60 天 → 不挡）。
  - 假设（事先方向，每个闸门各自）：不挡的胜率 > 挡的，且每笔不更低。胜率差 / 每笔差 = 不挡 − 挡（pp）；区间 = 按信号月聚类的自助法
    2,000 次（种子 20261005）。
  - 判定（每年一次：与 W2 同一组日期 2027-09-28 … 2031-09-28 之后的那次复核；做过的年份不再做；每次用到那时为止的全部成熟样本）：
      证实 = 胜率差的 99% 区间下限 > 0，且每笔差的点估计 ≥ 0（第十个循环 V1：每笔不降）→ 记为「新数据证实」；
      否定 = 胜率差的 95% 区间上限 < 0，或每笔差的 95% 区间上限 < 0 → 记为「新数据否定」，这个闸门结束跟踪（记录照留）；
      其他 = 未定；挡 / 不挡 任一组 < 10 笔或 < 3 个信号月 → 「样本不够、不判定」（也算做过那一年）。
    另报（不判定）：主对象里的日経225（今天的成分）、不限成交额（W2 保留）、主对象里不管 W2 的全部；HWN 按日历月的笔数 / 胜率 / 每笔；标记缺值的笔数。
  - 多重检验（照实写）：3 个闸门 × 最多 5 次判定；每次证实用 99%（单侧 0.5%）→ 15 次合起来误判最多约 7.5%。
  - 检出力：登记后另跑 scripts/gate_forward_calib.py（只用已看过的历史池子 W / Jx / Zx 估计区间的宽度，不是检验），结果记在 sim_changes.md。
    事前的看法：HWN / JRM 是按日子挡 → 新证据按「月」累积，不是按「笔」（一年 12 个月里 HWN 6 个挡、6 个不挡）→ 多半要很多年；
    X2G 按业种挡、同一个月里两组都有 → 快一些。
  - 证实 / 否定都只是记录：HWN / X2G 没过的是账户（Z 年代的 V3），单笔的前向检验回答不了账户的问题；要改模拟盘另写一份事先登记的
    账户研究，并经用户确认。算不了（短観 / 1545 / 日経取不到）→ 那个闸门这次的列为空、报告里写原因，不影响另外两个与第一〜九节。
十一、追加登记 趋势线研究最接近的做法 TQ08「日线支撑线短（第一个锚点到信号日 ≤ 75 根）的不买」（2026-10-07，用户〔74〕选 ②
  「把 TQ08 加进全市场前向检验」；只记录、不交易；定义与统计 qbreak/tq08_forward.py）
  - 来由：趋势线的质地特征研究（scripts/trendline_select_study.py，登记 603712a + 2f4f5af、只运行一次、结果 284f898）16 个「挡一端」做法里
    最接近的：W / Jx 池子里 B4 会买的信号，挡 d_sup_len ≤ 75 根的那约三分之一 → Jx 胜率 +2.75 pp / 每笔 +0.307 pp（保留 − 全部）、
    W 同向（+1.27 / +0.590）；但只在「重排组标签再挑最差一端」对照的 86.5 分位（门槛 95）→ 没有入围（Zx 与日経225 账户按规则没看）。
    挡哪一端是看了 Jx 的结果挑的 → 只有登记之后才发生的信号才是真正的样本外。
  - 对象：第八节的配对（同一份 J-Quants 行情、同一批信号）里信号日 ≥ 2026-10-08（登记日的下一个东证交易日）、成熟、两边都已平仓的；
    结果 = X6 那一边的净收益（同第十节）；主样本 = 主对象（成交额 ≥ ¥500 万）里 W2 保留的。照实写：研究的池子还有 C（只作用在日経225）
    与 TBF（模拟盘 B4 的一部分），这里都不加（同第十节不加 C）。
  - 标记（定义照研究一个字不改；1 = 挡）：d_sup_len = 信号日的日线支撑线的第一个锚点到信号日的根数（trendline_select_study.ticker_features
    的 F08；qbreak/trendline.py scan，k / L / gap / R = 5 / 250 / 10 / 60、容差 0.3 × ATR14、只用到信号日为止的 K 线）；
    ≤ 75 根（研究冻结的三分位界线 BOUNDS["F08"][0] = 75）→ 挡；没有支撑线 / 76 根以上 / 收盘有值的行不到 60 根 → 不挡。
    行情 = 第八节同一份 J-Quants 复权日线，每只票取收盘与开盘都有值的日子（candle_study.frames_from 同一个取法）。
  - 假设（事先方向）：不挡的胜率 > 挡的，且每笔不更低。胜率差 / 每笔差 = 不挡 − 挡（pp）；区间 = 按信号月聚类的自助法 2,000 次（种子 20261007）。
  - 判定（每年一次：与 W2 同一组日期 2027-09-28 … 2031-09-28 之后的那次复核；做过的年份不再做；每次用到那时为止的全部成熟样本）：同第十节 ——
      证实 = 胜率差的 99% 区间下限 > 0，且每笔差的点估计 ≥ 0 → 记为「新数据证实」；
      否定 = 胜率差的 95% 区间上限 < 0，或每笔差的 95% 区间上限 < 0 → 记为「新数据否定」，结束跟踪（记录照留）；
      其他 = 未定；挡 / 不挡 任一组 < 10 笔或 < 3 个信号月 → 「样本不够、不判定」（也算做过那一年）。
    另报（不判定）：主对象里的日経225（今天的成分）、不限成交额（W2 保留）、主对象里不管 W2 的全部；挡的比例；没有支撑线 / 没有特征行的笔数。
  - 检出力（事前粗估，照实写）：主对象 W2 保留每年约 450 笔成熟配对、挡约三分之一 → 胜率差的标准误一年约 5 pp（按月聚类约 6〜7.5 pp）；
    研究里 Jx 的「不挡 − 挡」约 +8 pp（= 保留 − 全部 ÷ 挡的比例；看了结果挑出来的，多半偏大）→ 就算真有 +8 pp，99% 下限 > 0
    也要约 6〜10 年；+4 pp 要 25 年以上 → 5 次判定里多半是「未定」，比较快能回答的是「方向反过来」（否定）。
  - 多重检验（照实写）：1 个做法 × 最多 5 次判定，证实用 99%（单侧 0.5%）→ 合起来误判最多约 2.5%；研究里本来就比了 16 个做法、挑了最接近的一个。
  - 证实 / 否定都只是记录：要改模拟盘另写一份事先登记的账户研究（日経225 三个年代的 B4 账户 + 没看过的 Zx），并经用户确认。
    算不了 → 这一节这次为空、报告里写原因，不影响第一〜十节。
"""
from __future__ import annotations

import json
import math
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
from qbreak import exit_forward as EF                                        # noqa: E402
from qbreak import gate_forward as GF                                        # noqa: E402
from qbreak import idio_forward as IF                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import tq08_forward as TQ                                        # noqa: E402
from qbreak import w2_forward as W2F                                         # noqa: E402

FORWARD_START = "2026-09-28"
W2_CUT = 1.0
LIQ_MIN_YEN = 5_000_000
JUDGE_DATES = ("2027-09-28", "2028-09-28", "2029-09-28", "2030-09-28", "2031-09-28")
BOOT_N, SEED = 2000, 20260927

LIQ_LOG = math.log10(LIQ_MIN_YEN)                                             # allstock_study 的 lturn = log10(20 天平均成交额)
HIST = "w2_forward_all_history.csv"
LINES: list[str] = []
assert W2_CUT == W2F.W2_CUT and JUDGE_DATES == W2F.JUDGE_DATES and (BOOT_N, SEED) == (W2F.BOOT_N, W2F.SEED)   # 登记值与共用模块一致
assert IF.JUDGE_DATES == JUDGE_DATES and EF.JUDGE_DATES == JUDGE_DATES and GF.JUDGE_DATES == JUDGE_DATES and TQ.JUDGE_DATES == JUDGE_DATES


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_ends(after, until) -> list[str]:
    """after 之后、until 为止每个月的最后一个东证交易日（要补的月末上市一览）。"""
    from qbreak.calendar_jp import is_trading_day, prev_trading_day
    a, u = pd.Timestamp(after), pd.Timestamp(until)
    out = []
    for p in pd.period_range(a.to_period("M"), u.to_period("M"), freq="M"):
        d = p.to_timestamp(how="end").date()
        if not is_trading_day(d):
            d = prev_trading_day(d)
        if a < pd.Timestamp(d) <= u:
            out.append(d.isoformat())
    return out


def refresh(log=print, today=None) -> dict:
    """补齐 J-Quants 缓存：批量日线（已下载且没变的跳过）+ 新的月末上市一览。原始数据只在缓存目录（不入库）。"""
    from qbreak import jq_data as JD
    from qbreak import pit_data as PD
    from qbreak import jquants as JQ
    c = JQ.JQuants()
    files = JD.bulk_download(c, "/equities/bars/daily", log=log)
    have = PD.master_files()
    new = month_ends(max(have) if have else pd.Timestamp(FORWARD_START) - pd.Timedelta(days=40),
                     pd.Timestamp(today) if today is not None else pd.Timestamp.today())
    for d in new:
        JQ.master_cached(c, d)
    return {"bar_files": len(files), "new_snapshots": new}


def forward_trades(T: pd.DataFrame) -> pd.DataFrame:
    """allstock_study.train_all 的交易 → 信号日 ≥ FORWARD_START 的已平仓交易 + W2 标记 + 是否主对象（成交额 ≥ ¥500 万）。"""
    if not len(T):
        return T.assign(w2_keep=pd.Series(dtype=int), main=pd.Series(dtype=bool))
    F = T[pd.to_datetime(T["sig_date"]) >= pd.Timestamp(FORWARD_START)].copy()
    F["sig_date"] = pd.to_datetime(F["sig_date"])
    F["w2_keep"] = W2F.keep_flag(F["w5v"])
    F["main"] = F["lturn"].to_numpy(float) >= LIQ_LOG                        # 缺值 → 不是主对象
    return F.reset_index(drop=True)


def s33_of(s33: dict[str, str], t: str) -> str | None:
    """交易表的代码（4 位 + .T 或 5 位）→ 上市一览的 33 业种名。"""
    c = str(t).split(".")[0]
    return s33.get(t) or s33.get(c) or s33.get(c + "0") or s33.get(c[:4]) if s33 else None


def s33_map_from_master() -> dict[str, str]:
    """复核时最新的月末上市一览 → {代码: 33 业种名}（5 位代码与 4 位 + .T 都放进去）。"""
    from qbreak import pit_data as PD
    files = PD.master_files()
    if not files:
        return {}
    m = pd.read_csv(files[max(files)], dtype=str)
    out = {}
    for code, name in zip(m["Code"].astype(str), m["S33Nm"].astype(str)):
        out[code] = name
        if len(code) == 5 and code.endswith("0"):
            out[code[:4] + ".T"] = name
    return out


def idio_all(F: pd.DataFrame, A: dict, mkt_close: pd.Series | None, us_pct: pd.DataFrame | None, s33: dict[str, str] | None) -> pd.DataFrame:
    """第七节：登记之后的每笔交易 → vr1、b_n225、k2_keep、us12、usw_keep（qbreak/idio_forward.py 同一定义；面板 = A 的 C / V）。"""
    if not len(F):
        return F.assign(**{c: pd.Series(dtype=float) for c in IF.COLS})
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    V = pd.DataFrame(A["V"], index=days, columns=names)
    VR = V / V.shift(1).rolling(20, min_periods=15).mean()
    C = pd.DataFrame(A["C"], index=days, columns=names)
    Yw = C.resample("W-FRI").last().pct_change(fill_method=None).clip(-0.5, 0.5)
    m_w = IF.weekly_returns(mkt_close) if mkt_close is not None else None
    vr, bt, us = [], [], []
    for t, d in zip(F["ticker"], pd.to_datetime(F["sig_date"])):
        v = VR.at[d, t] if (t in VR.columns and d in VR.index) else np.nan
        vr.append(round(float(v), 4) if np.isfinite(v) else np.nan)
        b = IF.beta_asof(Yw[t], m_w, d) if (m_w is not None and t in Yw.columns) else float("nan")
        bt.append(round(b, 4) if np.isfinite(b) else np.nan)
        u = IF.us12_at(us_pct, s33_of(s33 or {}, t), d)
        us.append(round(u, 4) if np.isfinite(u) else np.nan)
    out = F.copy()
    out["vr1"], out["b_n225"], out["k2_keep"] = vr, bt, IF.k2_flag(vr, bt)
    out["us12"], out["usw_keep"] = us, IF.usw_flag(us)
    return out


def x6_pairs(A: dict, T: pd.DataFrame, p, mk: pd.DataFrame) -> pd.DataFrame:
    """第八节：T（登记之后的已平仓交易）里出现过的票 → 用同一份行情重建指标表 → 这些票信号日 ≥ FORWARD_START、上市一览是一般市场的
    日子的全部突破，逐个配对模拟 现行 / X6（qbreak/exit_forward.py）；每个信号带上 w5v、w2_keep、lturn、main（成交额 ≥ ¥500 万）。
    成熟的信号（之后 ≥ 65 根 K 线）一定有更早或同一笔已平仓交易 → 这些票覆盖全部成熟信号。"""
    import allstock_study as S
    import candle_study as CS_
    import pit_retrain_study as PRS
    from qbreak.config import BacktestConfig
    cols = ["ticker", "sig_date", "w5v", "lturn", "w2_keep", "main"]
    if not len(T):
        return pd.DataFrame(columns=cols + ["status", "mature"])
    names = list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    idx = [col[t] for t in sorted(set(T["ticker"])) if t in col]
    sub = {x: np.asarray(A[x][:, idx], np.float64) for x in "OHLCV"}
    fr = CS_.frames_from(sub, A["days"], [names[j] for j in idx], list(range(len(idx))), p, {"listed": A["listed"][:, idx]})
    bt = BacktestConfig.for_market("JP", 21, "tachibana")                     # 与 candle_posthoc.trades 相同（每只票单独、一次一仓）
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rt = bt.exec_cfg.fee(PRS.NOTIONAL) * 2 / PRS.NOTIONAL * 100
    rows = []
    for t, df in fr.items():
        e = df["entry"].to_numpy(bool) & df["listed"].to_numpy(bool) & np.asarray(df.index >= pd.Timestamp(FORWARD_START))
        if not e.any():
            continue
        f = S.stock_features(df, mk)
        for d in df.index[e]:
            rows.append({"ticker": t, "sig_date": d, "w5v": f.at[d, "w5v"], "lturn": f.at[d, "lturn"]})
    if not rows:
        return pd.DataFrame(columns=cols + ["status", "mature"])
    sig = pd.DataFrame(rows)
    sig["w2_keep"] = W2F.keep_flag(sig["w5v"])
    sig["main"] = sig["lturn"].to_numpy(float) >= LIQ_LOG                    # 缺值 → 不是主对象
    return EF.pairs_frame(fr, sig, p, bt, rt, date_col="sig_date")


def x6_eval(P: pd.DataFrame, hist: pd.DataFrame | None, today, n225: set[str]) -> dict:
    """第八节：主 = 主对象里 W2 保留的成熟配对，每年一次判定；次 = 主对象里不管 W2 的全部（95%，只报告倾向）；另报不判定。"""
    if not len(P):
        P = pd.DataFrame(columns=["ticker", "sig_date", "w2_keep", "main", "status", "mature"])
    main = P["main"].astype(bool).to_numpy()
    keep = pd.to_numeric(P["w2_keep"], errors="coerce").to_numpy(float) == 1
    nn = P["ticker"].isin(n225).to_numpy()
    ev = EF.evaluate(P[main & keep], date_col="sig_date")
    year = W2F.due_date(today, EF.JUDGE_DATES, W2F.history_done(hist, "all_X6", "x6_year"))
    sec = EF.evaluate(P[main], date_col="sig_date")
    side = {"不限成交额（W2 保留）": EF.evaluate(P[keep], date_col="sig_date"),
            "主对象里的日経225 股票池（W2 保留）": EF.evaluate(P[main & keep & nn], date_col="sig_date")}
    e4 = EF.evaluate_r4(P[main & keep], date_col="sig_date")                  # 第九节：R4（同一批配对多跑的一边）
    r4 = {"eval": e4, "year": W2F.due_date(today, EF.JUDGE_DATES, W2F.history_done(hist, "all_R4", "r4_year")),
          "secondary": EF.evaluate_r4(P[main], date_col="sig_date"),
          "side": {"不限成交额（W2 保留）": EF.evaluate_r4(P[keep], date_col="sig_date"),
                   "主对象里的日経225 股票池（W2 保留）": EF.evaluate_r4(P[main & keep & nn], date_col="sig_date")}}
    return {"eval": ev, "year": year, "secondary": sec, "sec_ok": bool(sec.get("lo95") is not None and sec["lo95"] > 0) if year else None,
            "side": side, "r4": r4}


def x2_values(tickers, dates, s33: dict[str, str] | None, fetch=None) -> np.ndarray | None:
    """第十节：每个信号的 x2（复核时最新的月末上市一览的 33 业种 → qbreak/score_forward.x2_load / x2_lookup）；没有业种 → None。"""
    from qbreak import score_forward as SF
    m = {t: s33_of(s33 or {}, t) for t in set(tickers)}
    m = {t: v for t, v in m.items() if v}
    if not m:
        return None
    return SF.x2_lookup(SF.x2_load(m, fetch), list(dates), list(tickers))[0]


def gate_frame(PX: pd.DataFrame, x2_fn, n225: pd.Series | None, core: pd.Series | None, note: list | None = None) -> pd.DataFrame:
    """第十节：第八节的配对 → 信号日 ≥ GF.FORWARD_START、成熟、两边都已平仓的 + x2 / 三个闸门的标记。
    x2_fn(tickers, dates) → x2 数组（取不到抛异常 → X2G 这次为空、原因记进 note）。"""
    U = EF.usable(PX) if PX is not None and len(PX) else pd.DataFrame(columns=["ticker", "sig_date", "w2_keep", "main", "net_x6"])
    if len(U):
        U = U[pd.to_datetime(U["sig_date"]) >= pd.Timestamp(GF.FORWARD_START)].reset_index(drop=True)
    x2 = None
    if len(U):
        try:
            x2 = x2_fn(list(U["ticker"]), list(pd.to_datetime(U["sig_date"])))
            if x2 is None and note is not None:
                note.append("X2G 这次算不了（上市一览的业种取不到）")
        except Exception as e:                                                # noqa: BLE001
            if note is not None:
                note.append(f"X2G 这次算不了（短観 / 业种取不到）：{type(e).__name__}: {e}")
    return GF.add_flags(U, x2, n225, core)


def gate_eval(G: pd.DataFrame, hist: pd.DataFrame | None, today, n225_set: set[str]) -> dict:
    """第十节：主 = 主对象里 W2 保留的（每年一次判定）；另报不判定。"""
    if not len(G):
        G = G.assign(main=pd.Series(dtype=bool), w2_keep=pd.Series(dtype=float))
    main = G["main"].astype(bool).to_numpy()
    keep = pd.to_numeric(G["w2_keep"], errors="coerce").to_numpy(float) == 1
    nn = G["ticker"].isin(n225_set).to_numpy() if len(G) else np.zeros(0, bool)
    r = GF.review(G[main & keep], hist, today, prefix="all_")
    side = {name: {k: GF.evaluate(G[m], f"g_{k.lower()}") for k in GF.IDS}
            for name, m in (("主对象里的日経225 股票池（W2 保留）", main & keep & nn), ("不限成交额（W2 保留）", keep),
                            ("主对象里不管 W2 的全部", main))}
    return {"main": r, "side": side, "hwn_month": GF.by_month(G[main & keep]),
            "jrm_on": round(float(np.nanmean(pd.to_numeric(G["g_jrm"], errors="coerce"))) * 100, 1) if len(G) and G["g_jrm"].notna().any() else None,
            "x2_missing": int(G["x2"].isna().sum()) if len(G) else 0, "n_usable": int(len(G))}


def tq08_values(A: dict, PX: pd.DataFrame | None) -> pd.DataFrame:
    """第十一节：第八节的配对里信号日 ≥ TQ.FORWARD_START 的票 → 同一份 J-Quants 行情（A 的 O / H / L / C；每只票取收盘与开盘都有值的日子 =
    candle_study.frames_from 同一个取法）→ 每个（票, 信号日）的 d_sup_len 与有没有特征行（qbreak/tq08_forward.sup_len）。"""
    cols = ["ticker", "sig_date", "d_sup_len", "tq08_row"]
    if PX is None or not len(PX):
        return pd.DataFrame(columns=cols)
    S = PX[pd.to_datetime(PX["sig_date"]) >= pd.Timestamp(TQ.FORWARD_START)]
    if not len(S):
        return pd.DataFrame(columns=cols)
    days = pd.DatetimeIndex(A["days"])
    col = {t: j for j, t in enumerate(A["names"])}
    rows = []
    for t, g in S.groupby("ticker"):
        v, j = None, col.get(t)
        if j is not None:
            ok = np.isfinite(np.asarray(A["C"][:, j], float)) & np.isfinite(np.asarray(A["O"][:, j], float))
            df = pd.DataFrame({k: np.asarray(A[x][ok, j], np.float64) for k, x in (("Open", "O"), ("High", "H"), ("Low", "L"), ("Close", "C"))},
                              index=days[ok])
            v = TQ.sup_len(df)
        for d in pd.to_datetime(g["sig_date"]).unique():
            x, has = TQ.value_at(v, d)
            rows.append({"ticker": t, "sig_date": pd.Timestamp(d), "d_sup_len": x, "tq08_row": has})
    return pd.DataFrame(rows, columns=cols)


def tq08_frame(PX: pd.DataFrame | None, V: pd.DataFrame | None) -> pd.DataFrame:
    """第十一节：第八节的配对 → 信号日 ≥ TQ.FORWARD_START、成熟、两边都已平仓的 + d_sup_len 与 TQ08 的标记（1 = 挡；没有值 → 不挡）。"""
    U = EF.usable(PX) if PX is not None and len(PX) else pd.DataFrame(columns=["ticker", "sig_date", "w2_keep", "main", "net_x6"])
    if len(U):
        U = U[pd.to_datetime(U["sig_date"]) >= pd.Timestamp(TQ.FORWARD_START)].reset_index(drop=True)
    if not len(U):
        return U.assign(d_sup_len=pd.Series(dtype=float), tq08_row=pd.Series(dtype=bool), **{TQ.FLAG: pd.Series(dtype=int)})
    U = U.assign(sig_date=pd.to_datetime(U["sig_date"]))
    V = V if V is not None and len(V) else pd.DataFrame(columns=["ticker", "sig_date", "d_sup_len", "tq08_row"])
    V = V.assign(sig_date=pd.to_datetime(V["sig_date"])).drop_duplicates(["ticker", "sig_date"])
    M = U.merge(V, on=["ticker", "sig_date"], how="left")
    M["tq08_row"] = M["tq08_row"].astype("boolean").fillna(False).astype(bool)
    M["d_sup_len"] = pd.to_numeric(M["d_sup_len"], errors="coerce")
    M[TQ.FLAG] = TQ.flag(M["d_sup_len"], M["tq08_row"])
    return M


def tq08_eval(Q: pd.DataFrame, hist: pd.DataFrame | None, today, n225_set: set[str]) -> dict:
    """第十一节：主 = 主对象里 W2 保留的（每年一次判定）；另报不判定。"""
    if not len(Q):
        Q = Q.assign(main=pd.Series(dtype=bool), w2_keep=pd.Series(dtype=float))
    main = Q["main"].astype(bool).to_numpy()
    keep = pd.to_numeric(Q["w2_keep"], errors="coerce").to_numpy(float) == 1
    nn = Q["ticker"].isin(n225_set).to_numpy() if len(Q) else np.zeros(0, bool)
    r = TQ.review(Q[main & keep], hist, today, prefix="all_")
    side = {name: TQ.evaluate(Q[m]) for name, m in (("主对象里的日経225 股票池（W2 保留）", main & keep & nn),
                                                    ("不限成交额（W2 保留）", keep), ("主对象里不管 W2 的全部", main))}
    mk = Q[main & keep]
    fl = pd.to_numeric(mk[TQ.FLAG], errors="coerce").to_numpy(float) if len(mk) else np.zeros(0)
    row = mk["tq08_row"].to_numpy(bool) if len(mk) else np.zeros(0, bool)
    dl = pd.to_numeric(mk["d_sup_len"], errors="coerce").to_numpy(float) if len(mk) else np.zeros(0)
    return {"main": r, "side": side, "n_usable": int(len(Q)), "n_main": int(len(mk)),
            "blocked_pct": round(float(np.nanmean(fl)) * 100, 1) if len(fl) else None,
            "no_line": int((row & ~np.isfinite(dl)).sum()), "no_row": int((~row).sum())}


def decide(ev: dict, hist: pd.DataFrame | None, today) -> dict:
    """每年一次（JUDGE_DATES）：失效警报 95% / 证实 99%；判定过的年份记进历史，不再判定。"""
    year = W2F.due_date(today, JUDGE_DATES, W2F.history_done(hist, "all", "w2_year"))
    return {"year": year, "alarm": W2F.alarm(ev) if year else None, "confirmed": W2F.confirmed(ev) if year else None}


def by_year(F: pd.DataFrame) -> dict:
    out = {}
    for y, g in F.groupby(F["sig_date"].dt.year):
        k = g["w2_keep"].to_numpy(int)
        out[int(y)] = {"keep": W2F.stat(g.loc[k == 1, "net"]), "drop": W2F.stat(g.loc[k == 0, "net"])}
    return out


def review(fetch: bool = True) -> int:
    import allstock_data as AD
    import allstock_study as S
    from bullbear_study import SYM, load
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    today = pd.Timestamp.today().normalize()
    info = refresh(log=lambda s: print(s, file=sys.stderr, flush=True)) if fetch else {"skipped": "没有补数据（--no-fetch）"}
    A = AD.load(rebuild=fetch)
    last_bar = A["days"][-1]
    p = SF.no_w2_params(load_params(market="JP"))
    jp_close = load(*SYM["JP"])["Close"]
    mk = S.market_frame(jp_close)
    T, n_st = S.train_all(A, p, mk, start=FORWARD_START)
    F = forward_trades(T)
    x6_note = []
    try:                                                                      # 第八节：卖法 X6 的配对（算不了 → 另报原因，不影响 W2 / K2 / USW）
        PX = x6_pairs(A, T, p, mk)
    except Exception as e:                                                    # noqa: BLE001
        PX = None
        x6_note.append(f"X6 的配对这次算不了：{type(e).__name__}: {e}")
    tq_note, TQV = [], None
    if PX is not None:                                                        # 第十一节：TQ08 的 d_sup_len（要行情，在 del A 之前算）
        try:
            TQV = tq08_values(A, PX)
        except Exception as e:                                                # noqa: BLE001
            tq_note.append(f"第十一节这次算不了（d_sup_len）：{type(e).__name__}: {e}")
    else:
        tq_note.append("第八节的配对这次算不了 → 第十一节也算不了")
    idio_note = []
    us_pct = s33 = None
    try:                                                                      # 第七节：K2 / USW 的输入（取不到 → 对应列为空，另报原因）
        from qbreak import factors as FX
        us_pct = IF.us_rank_asof(FX.ff_industries(49, "vw"))
    except Exception as e:                                                    # noqa: BLE001
        idio_note.append(f"美国 49 行业取不到：{type(e).__name__}: {e}")
    try:
        s33 = s33_map_from_master()
    except Exception as e:                                                    # noqa: BLE001
        idio_note.append(f"上市一览的业种取不到：{type(e).__name__}: {e}")
    F = idio_all(F, A, jp_close, us_pct, s33)
    del A
    n225 = set(universe("JP", "broad"))
    F["n225"] = F["ticker"].isin(n225)
    M = F[F["main"]]
    ev = W2F.evaluate(M, date_col="sig_date")
    hist_fp = paths.out_dir() / HIST
    hist = pd.read_csv(hist_fp) if hist_fp.exists() else pd.DataFrame()
    V = decide(ev, hist, today)
    x6 = x6_eval(PX, hist, today, n225) if PX is not None else None
    g10, g10_note = None, []
    if PX is not None:                                                        # 第十节：HWN / X2G / JRM（只记录；算不了 → 另报原因）
        core = None
        try:
            core = load(GF.CORE_TICKER, "2000-01-01")["Close"]
        except Exception as e:                                                # noqa: BLE001
            g10_note.append(f"JRM 这次算不了（{GF.CORE_TICKER} 取不到）：{type(e).__name__}: {e}")
        try:
            G = gate_frame(PX, lambda tk, ds: x2_values(tk, ds, s33), jp_close, core, g10_note)
            g10 = gate_eval(G, hist, today, n225)
        except Exception as e:                                                # noqa: BLE001
            g10_note.append(f"第十节这次算不了：{type(e).__name__}: {e}")
    else:
        g10_note.append("第八节的配对这次算不了 → 第十节也算不了")
    tq = None
    if TQV is not None:                                                       # 第十一节：TQ08（只记录；算不了 → 另报原因）
        try:
            tq = tq08_eval(tq08_frame(PX, TQV), hist, today, n225)
        except Exception as e:                                                # noqa: BLE001
            tq_note.append(f"第十一节这次算不了：{type(e).__name__}: {e}")
    side = {"全部（不限成交额）": W2F.evaluate(F, date_col="sig_date", n=0) if len(F) else {"n": 0},
            "主对象里的日経225 股票池": W2F.evaluate(M[M["n225"]], date_col="sig_date", n=0) if len(M) else {"n": 0},
            "主对象里的其他股票": W2F.evaluate(M[~M["n225"]], date_col="sig_date", n=0) if len(M) else {"n": 0}}
    say(f"# W2 全市场前向检验复核（{today.date()}）")
    say(f"规则见 scripts/w2_forward_all.py 开头（2026-09-27 登记）。数据到 {last_bar.date()}；{n_st} 只里信号日 ≥ {FORWARD_START} 的已平仓交易 "
        f"{len(F)} 笔（主对象 = 20 天平均成交额 ≥ ¥{LIQ_MIN_YEN / 1e4:.0f} 万：{len(M)} 笔）。")
    say("\n## 主对象：W2 保留 vs 挡掉")
    say(W2F.summary_line(ev) if ev["n"] else "还没有已平仓的信号")
    lines = W2F.verdict_lines(ev, f"{V['year']} 这一年" if V["year"] else None, f"{V['year']} 这一年" if V["year"] else None)
    for x in lines:
        say(f"- {x}")
    if not lines:
        nxt = next((d for d in JUDGE_DATES if pd.Timestamp(d) > today), None)
        say(f"只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "五次年度判定都已做完（只报告）")
    say("\n## 另报（不判定）")
    for k, e in side.items():
        say(f"- {k}：" + (W2F.summary_line(e) if e.get("n") else "0 笔"))
    idio = IF.review_pair(M, hist, today, scope_prefix="all_", date_col="sig_date", seg_col=None)
    say("\n## K2 / USW（第七节，主对象）：标记 vs 其余")
    for x in IF.say_lines(idio, today=today):
        say(x)
    if len(M):
        f2 = lambda s: f"{s['n']} 笔 {s['mean']:+.2f}%" if s.get("n") else "0 笔"                                 # noqa: E731
        for key, col, base_ in (("K2", "k2_keep", M), ("USW", "usw_keep", M[pd.to_numeric(M["w2_keep"], errors="coerce") == 1])):
            kv = pd.to_numeric(base_[col], errors="coerce").to_numpy(float)
            say(f"  - {key} 分段（只描述）：" + "；".join(
                f"{g} 标记 {f2(W2F.stat(base_.loc[m & (kv == 1), 'net']))} / 其余 {f2(W2F.stat(base_.loc[m & (kv == 0), 'net']))}"
                for g, m in (("日経225", base_["n225"].to_numpy(bool)), ("其他", ~base_["n225"].to_numpy(bool)))))
    for x in idio_note:
        say(f"  - {x}")
    say("\n## 卖法 X6（第八节，主对象、W2 保留、成熟配对）：同一个信号 现行 vs 吊灯止损")
    if x6 is not None:
        say(EF.summary_line(x6["eval"]))
        lines = EF.verdict_lines(x6["eval"], f"{x6['year']} 这一年" if x6["year"] else None)
        for x in lines:
            say(f"- {x}")
        if not lines:
            nxt = next((d for d in JUDGE_DATES if pd.Timestamp(d) > today), None)
            say(f"只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "五次年度判定都已做完（只报告）")
        sec = x6["secondary"]
        say(f"- 次假设（主对象里不管 W2 的全部，95%，只报告倾向）：{EF.summary_line(sec)}"
            + (f" → 这一年{'倾向成立' if x6['sec_ok'] else '倾向不成立'}" if x6["year"] else ""))
        for k, e in x6["side"].items():
            say(f"- 另报 {k}：{EF.summary_line(e)}")
        r4 = x6["r4"]                                                         # 第九节
        say("\n## 卖出判定 R4（第九节，主对象、W2 保留、成熟配对）：同一个信号 现行 vs 抛物线 SAR 翻转")
        say(EF.r4_summary_line(r4["eval"]))
        lines = EF.r4_verdict_lines(r4["eval"], f"{r4['year']} 这一年" if r4["year"] else None)
        for x in lines:
            say(f"- {x}")
        if not lines:
            nxt = next((d for d in JUDGE_DATES if pd.Timestamp(d) > today), None)
            say(f"只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "五次年度判定都已做完（只报告）")
        say(f"- 另报 主对象里不管 W2 的全部：{EF.r4_summary_line(r4['secondary'])}")
        for k, e in r4["side"].items():
            say(f"- 另报 {k}：{EF.r4_summary_line(e)}")
    for x in x6_note:
        say(f"- {x}")
    say(f"\n## 第十个循环最接近的三个选股闸门（第十节，主对象、W2 保留、信号日 ≥ {GF.FORWARD_START}、成熟、X6 离场的结果）：不挡 vs 挡")
    if g10 is not None:
        for x in GF.verdict_lines(g10["main"], today=today):
            say(x)
        for name, evs in g10["side"].items():
            say(f"- 另报 {name}：" + "；".join(f"{k} 胜率差 " + (f"{e['dwin']:+.1f} pp（{e['keep']['n']} / {e['block']['n']} 笔）"
                                                                if e.get("dwin") is not None else "—") for k, e in evs.items()))
        if g10["hwn_month"]:
            f = lambda s: f"{s['n']} 笔 {s['win']:.0f}% {s['mean']:+.2f}%" if s.get("n") else "—"                  # noqa: E731
            say("- 另报 HWN 按日历月（只描述）：" + "；".join(f"{m} 月 {f(s)}" for m, s in g10["hwn_month"].items()))
        say(f"- JRM 成立的信号占 {g10['jrm_on']}%；x2 缺值 {g10['x2_missing']} 笔（缺值不挡）" if g10["jrm_on"] is not None
            else f"- x2 缺值 {g10['x2_missing']} 笔（缺值不挡）")
    for x in g10_note:
        say(f"- {x}")
    say(f"\n## 趋势线 TQ08（第十一节，主对象、W2 保留、信号日 ≥ {TQ.FORWARD_START}、成熟、X6 离场的结果）：不挡 vs 挡")
    if tq is not None:
        for x in TQ.verdict_lines(tq["main"], today=today):
            say(x)
        for name, e in tq["side"].items():
            say(f"- 另报 {name}：{GF.summary_line(e)}")
        say(f"- 主样本 {tq['n_main']} 笔里挡的占 {tq['blocked_pct'] if tq['blocked_pct'] is not None else '—'}%；"
            f"没有支撑线 {tq['no_line']} 笔、没有特征行 {tq['no_row']} 笔（都算不挡）")
    for x in tq_note:
        say(f"- {x}")
    yr = by_year(M) if len(M) else {}
    if yr:
        say("\n| 信号年 | W2 保留 | 挡掉 |")
        say("|---|---|---|")
        f = lambda s: f"{s['n']} 笔 / {s['win']:.1f}% / {s['mean']:+.2f}%" if s.get("n") else "—"             # noqa: E731
        for y, v in yr.items():
            say(f"| {y} | {f(v['keep'])} | {f(v['drop'])} |")
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"\n代码版本 {code}；用时 {time.time() - t0:.0f}s")
    out = paths.out_dir() / "w2_forward_all_review"
    Path(f"{out}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{out}.json").write_text(json.dumps({"run": str(today.date()), "data_through": str(last_bar.date()), "refresh": info,
                                               "n_all": int(len(F)), "main": ev, "decision": V, "side": side, "by_year": yr,
                                               "idio": idio, "idio_note": idio_note, "x6": x6, "x6_note": x6_note,
                                               "g10": g10, "g10_note": g10_note, "tq08": tq, "tq08_note": tq_note, "code": code},
                                              ensure_ascii=False, indent=1,
                                              default=float), encoding="utf-8")
    row = {"run": str(today.date()), "scope": "all", "data_through": str(last_bar.date()), "closed": ev["n"], "w2_year": V["year"],
           "w2_diff": ev.get("diff"), "w2_lo95": ev.get("lo95"), "w2_hi95": ev.get("hi95"), "w2_lo99": ev.get("lo99"),
           "w2_hi99": ev.get("hi99"), "w2_alarm": V["alarm"], "w2_confirmed": V["confirmed"], "code": code}
    rows = [row] + IF.history_rows(idio, str(today.date()), "all_", {"data_through": str(last_bar.date()), "code": code})   # 第七节
    if x6 is not None:                                                        # 第八节：判定过的年份下次不再判定
        rows.append(EF.history_row(x6["eval"], str(today.date()), "all_X6", "x6_year", x6["year"],
                                   {"data_through": str(last_bar.date()), "code": code, "x6_sec_ok": x6["sec_ok"]}))
        rows.append(EF.r4_history_row(x6["r4"]["eval"], str(today.date()), "all_R4", "r4_year", x6["r4"]["year"],
                                      {"data_through": str(last_bar.date()), "code": code}))          # 第九节
    if g10 is not None:                                                       # 第十节：判定过的年份下次不再判定
        rows += GF.history_rows(g10["main"], str(today.date()), "all_", {"data_through": str(last_bar.date()), "code": code})
    if tq is not None:                                                        # 第十一节：判定过的年份下次不再判定
        rows.append(TQ.history_row(tq["main"], str(today.date()), "all_", {"data_through": str(last_bar.date()), "code": code}))
    pd.concat([hist, pd.DataFrame(rows)], ignore_index=True).to_csv(hist_fp, index=False)   # 只追加
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", required=True, help="复核（先补齐 J-Quants 缓存）")
    ap.add_argument("--no-fetch", action="store_true", help="不补数据，用现有缓存（试跑用）")
    a = ap.parse_args(argv)
    return review(fetch=not a.no_fetch)


if __name__ == "__main__":
    raise SystemExit(main())
