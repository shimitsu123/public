"""research_loop14.py — 第十四个研究循环：选股（以前没测过的角度）—— 7 个做法在任何一个运行之前一次登记完
（2026-10-24 登记 = 本提交；之后不改规则、不改做法清单；要改只能由用户在对话里明确要求）。

用户（2026-10-24）：「继续研究可以超越当前选股的算法 直到研究出来之前都不要停止」。第十三个循环 10 / 10 用完、没找到。
〇 基准 B4、池子、两条路线（A / B 三个年代；J 只有 2016-10 以后的数据）、第一关 / 第二关的判定：照第十二个循环（scripts/research_loop12.py 的
   stage1_all / stage1_j / stage2），第二关种子 numpy.random.default_rng([20261024, 14, s])。
   照实写：这 7 个是在看过以前约 150 个做法的结果之后挑的（每个的具体特征以前没算过）→ 路线 A / B 一律按「事后」判（stage1_all 的 posthoc = True，
   多一条 V6：Zx 池子也要过）；路线 J 照第十二个循环（没有 Zx）。同一家族 ≤ 3（这里每个家族 1 个）。
一 做法（满足 → 不买；缺值 / 数据不够 → 不挡；「分位」= 那个年代全部 W2 信号里的分位，池子用对应年代的：W → E、Jx → J、Zx → Z）：
   CNQ〔选股·与核心相关〕信号日为止 120 个东证交易日，个股收盘日收益与日元计纳指（equity_idle_study.on_jp：前一个美国收盘 × 东证当天早上的
       USD/JPY；纳指 = ndx_tr）日收益的相关 ≥ 67 分位 → 不买（日本个股是用核心的钱买的：和核心同涨同跌的票不分散）；有效对 < 80 → 不挡 —— A / B
   PRF〔选股·前次突破失败〕信号日前 60〜5 个交易日里第一个「收盘 > 之前 120 天最高收盘」的日子 j，j 之后到信号日前一天的最高收盘 < j 的收盘 × 1.05
       → 不买（上一次突破没走出来、又来一次）—— A / B
   GAP〔选股·跳空突破〕信号日开盘 > 前一天最高 × 1.01 → 不买（跳空的突破容易回补；方向在文献里不确定，照实写）—— A / B
   OVN〔选股·隔夜收益〕信号日为止 60 个交易日：Σ ln(开盘 ÷ 前收) − Σ ln(收盘 ÷ 开盘) ≥ 80 分位 → 不买（涨幅主要来自隔夜 = 散户情绪；Aboody 等 2018）—— A / B
   AGR〔选股·资产增长〕最近一份年度（FY）决算短信的总资产 ÷ 上一份年度的 − 1 ≥ 20% → 不买（Cooper, Gulen & Schill 2008）；两份开示日相差
       300〜430 天才算；金融业（银行 / 保险 / 证券 / 其他金融）不适用；最近一份超过 400 天 → 不挡 —— J
   ISS〔选股·股数增加〕同样两份年度短信：（期末发行股数 − 期末自己株式数）增加 ≥ 3% 且 < 40% → 不买（增发稀释；Pontiff & Woodgate 2008；
       ≥ 40% 多半是股票分割，不算）—— J
   PAY〔选股·予想配当性向〕最近一份决算短信的予想配当性向（FY 短信用下期予想、季度短信用当期予想）≥ 100% → 不买（分得比赚得多，难持续）；
       超过 200 天 → 不挡 —— J
二 运行：分两轮（A / B 一轮、J 一轮），每一轮先做接线核对（全 False = B4、只数挡掉的个数）写进 sim_changes，再运行一次；接线核对发现定义上的硬伤
   （几乎不挡 / 全挡）→ 照实写、那个做法记「作废（登记时的硬伤）」，不改定义、不补新的。第一关过的 → 另外登记第二关（随机挡 400 / 800 次）再跑。
   去掉的（照实写，登记前核对以前的做法时发现）：「长期反转」（3 年涨得多 → 不买）第五个循环第 6 轮 LTR 已经以仓位的形式测过 → 不重复。
三 停：更好候选出现 / 7 个跑完 / 用户说停。事前预期：大概率找不到（第九〜十三个循环 83 个做法真正的「更好候选」0）。非投资建议。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_loop12 as R12                                                # noqa: E402
import research_loop13 as R13                                                # noqa: E402

SEED = (20261024, 14)
POSTHOC = True
PLAN = [("CNQ", "选股·与核心相关", "AB"), ("PRF", "选股·前次突破失败", "AB"), ("GAP", "选股·跳空突破", "AB"),
        ("OVN", "选股·隔夜收益", "AB"), ("AGR", "选股·资产增长", "J"), ("ISS", "选股·股数增加", "J"), ("PAY", "选股·予想配当性向", "J")]
stage1_j, stage2, verdict = R12.stage1_j, R12.stage2, R12.verdict


def stage1_all(cand: dict, base: dict, other: dict | None) -> dict:
    return R12.stage1_all(cand, base, other, posthoc=POSTHOC)


def random_block(n: int, frac: float, seed: int):
    import numpy as np
    return np.random.default_rng([*SEED, int(seed)]).random(n) < float(frac)


def check_plan() -> None:
    """ID 不和以前（第一〜十三个循环与其他研究）重复、家族 ≤ 3。"""
    used = R12.used_ids() | {a["id"] for r in R12.load_state()["rounds"] for a in r["approaches"]} | {i for i, _, _ in R13.PLAN}
    fam: dict[str, int] = {}
    for i, f, _ in PLAN:
        if i in used:
            raise ValueError(f"ID {i} 用过了")
        fam[f] = fam.get(f, 0) + 1
        if fam[f] > 3:
            raise ValueError(f"家族 {f} 超过 3 个")


if __name__ == "__main__":
    check_plan()
    print("\n".join(f"{i}\t{f}\t{r}" for i, f, r in PLAN))
