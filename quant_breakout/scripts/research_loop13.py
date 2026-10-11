"""research_loop13.py — 第十三个研究循环：选股（以前没测过的日历 / 结构 / 宏观 / J-Quants 角度）—— 10 个做法在任何一个运行之前一次登记完
（2026-10-12 登记 = 本提交；之后不改规则、不改做法清单；要改只能由用户在对话里明确要求）。

用户（2026-10-12）：「继续进行选股的研究…8 小时不停止，直到找到比现在更好的选股算法」。第十二个循环 20 / 20 用完、没找到（最接近 FCN / OMG / DXD）。
和第十二个循环的不同（照实写）：**10 个做法的定义与门槛全部在这里写定、先登记再运行任何一个**（不会「看了前几轮再定下一轮」）；
DXD / 业绩恶化类的变体不在清单里（那会是事后挑选）。
〇 基准、候选、池子、两条路线（A / B 三个年代；J 只有 2016-10 以后的数据）、第一关 / 第二关的判定：全部照第十二个循环（scripts/research_loop12.py 的
   stage1_all / stage1_j / stage2），第二关种子换成 numpy.random.default_rng([20261012, 13, s])。上限 = 下面的 10 个；同一家族 ≤ 3。
一 做法（满足 → 不买；缺值 → 不挡；门槛「分位」= 那个年代全部 W2 信号里的分位，池子用对应年代的：W → E、Jx → J、Zx → Z）：
   SQW〔选股·日历〕信号日在当月 SQ 日（第 2 个星期五；休市 → 前一个交易日）所在的那一周（周一〜周五）—— A / B
   YRE〔选股·日历〕信号日在 12 月的最后 10 个交易日 —— A / B
   MON〔选股·日历〕信号日是星期五（成交日是下周第一个交易日）—— A / B
   IDX〔选股·指数入替〕信号日在 10 月第 1 个交易日之前的 15 个交易日之内（日経225 定期入替的生效前；4 月的入替不是每年都有 → 只看 10 月）—— A / B
   VCP〔选股·波动收缩〕信号日前一天为止的 ATR10 ÷ ATR50 ≥ 该年代信号的 80 分位（突破前没有收缩）—— A / B
   DDS〔选股·深跌〕信号日为止 250 个交易日里的最大回撤（峰到谷）≤ −40% —— A / B
   CSE〔选股·信用利差〕美国 BAA − 10 年国债利差（FRED BAA10Y，信号日之前最近的值）比 20 个交易日前扩大 ≥ 0.20 pp —— A / B
   FYB〔选股·业绩意外〕信号日之前 90 天内有年度（FY）决算短信，且实绩利润 ÷ 这个决算期最后一次会社予想 − 1 < −5% —— J
   SRN〔选股·空売り〕信号日之前 20 个交易日内，这只票的 ≥ 0.5% 空卖方数（空売り残高報告）增加过 —— J
   CHR〔选股·现金〕最近一次决算短信的 现金及等价物 ÷ 总资产 ≥ 30%（银行 / 保险 / 证券 / 其他金融不适用）—— J
二 运行：分几轮跑，每一轮先做接线核对（全 False = B4、只数挡掉的个数）写进 sim_changes，再运行一次；接线核对发现定义上的硬伤（例：几乎不挡 / 全挡）
   → 照实写、那个做法记「作废（登记时的硬伤）」，不改定义、不补新的。
三 停：更好候选出现 / 10 个跑完 / 用户说停。事前预期：大概率找不到（第九〜十二个循环 73 个做法第一关全过 0）。非投资建议。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_loop12 as R12                                                # noqa: E402

STATE_FILE = "research_loop13.json"
SEED = (20261012, 13)
PLAN = [("SQW", "选股·日历", "AB"), ("YRE", "选股·日历", "AB"), ("MON", "选股·日历", "AB"), ("IDX", "选股·指数入替", "AB"),
        ("VCP", "选股·波动收缩", "AB"), ("DDS", "选股·深跌", "AB"), ("CSE", "选股·信用利差", "AB"),
        ("FYB", "选股·业绩意外", "J"), ("SRN", "选股·空売り", "J"), ("CHR", "选股·现金", "J")]
stage1_all, stage1_j, stage2, verdict = R12.stage1_all, R12.stage1_j, R12.stage2, R12.verdict


def random_block(n: int, frac: float, seed: int):
    import numpy as np
    return np.random.default_rng([*SEED, int(seed)]).random(n) < float(frac)


def state_path():
    from qbreak import paths
    return paths.home() / STATE_FILE


def load_state() -> dict:
    p = state_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"loop": 13, "registered": "2026-10-12", "plan": [{"id": i, "family": f, "route": r, "verdict": None} for i, f, r in PLAN]}


def set_verdict(st: dict, aid: str, v: str, note: str | None = None) -> dict:
    for a in st["plan"]:
        if a["id"] == aid:
            a["verdict"] = v
            if note:
                a["note"] = note
            return st
    raise KeyError(aid)


def check_plan() -> None:
    """ID 不和以前重复、家族 ≤ 3。"""
    used = R12.used_ids() | {a["id"] for r in R12.load_state()["rounds"] for a in r["approaches"]}
    fam: dict[str, int] = {}
    for i, f, _ in PLAN:
        if i in used:
            raise ValueError(f"ID {i} 用过了")
        fam[f] = fam.get(f, 0) + 1
        if fam[f] > 3:
            raise ValueError(f"家族 {f} 超过 3 个")


if __name__ == "__main__":
    check_plan()
    print(json.dumps(load_state(), ensure_ascii=False, indent=1))
