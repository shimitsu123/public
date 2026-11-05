"""theme_study.py — 日本细分主题（电力 / 燃气 / 电线 / 重电 / 空调・冷却 / 电气工程 / 数据中心 / 软件・数据库 / 半导体设备・材料 /
电子部件 / 发电设备）+ 「错峰」+ 行业关联，横展开到全部行业（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

研究问题（用户：「继续结合现在错峰、行业关联等等类似的研究方向进行横展开，继续研究提高股票精确度，尽量展开到全行业，现在行业不够全
好像是，比如电费提高电厂怎么样、冷却相关、数据库、AI 关联等等」，优化后）：
  ① 电费 / 燃料：进口燃料（LNG、一般炭、原油）涨价后，电力公司（燃料费调整有 3〜5 个月的时滞）之后几个月怎么样？电费涨了，
     电力公司、高耗电行业（化学、钢铁、有色、纸、玻璃水泥、数据中心）之后怎么样？城市燃气同理。
  ② AI 链：美国半导体（及软件 / 硬件）股、日本半导体设备股先涨，之后电线、重电、空调・冷却、电气工程、数据中心、半导体材料、
     电子部件会不会跟上？电力设备 → 空调 / 电气工程？美国电力股 → 日本电力 / 电线 / 重电？
  ③ 「错峰」：信号与之后收益之间再隔 0 / 3 / 6 个月（效果会不会晚来）。
  ④ 横展开：全部来源（日本 7 种价格、美国 8 个行业、日本 12 个主题）× 全部被预测方（東証 30 业种 + 12 个主题）。
  ⑤ 这些能不能提高突破买点的命中率（比東証 33 业种更细的「主题动量」、「AI 链顺风」）？

一、数据（登记前只看了覆盖：起止日期、成员能否取到行情；没有算任何信号与收益的关系）
  - 主题：qbreak/themes.py THEMES（12 个、88 只；成员按主营业务事先写定，2026-08-31 的 JPX 名单核对过；6920 2010 年、6617 2012 年、
    4980 2015 年、6525 2023 年才上市）。主题日相对收益 = 成员等权对数收益 − TOPIX 1000 929 只的平均；有行情的成员 < 3 只的日子缺值。
  - 行业：東証 30 业种（var/industry_s33.json，与 supply_chain_study 相同）。月度 = 日相对收益之和，2005-10〜2026-08（没过完的月份不用）。
  - 日本价格（日银企业物价，月度，发布滞后 1 个月）：进口 LNG / 一般炭 / 原油（円ベース 品目）、电费（电力・都市ガス・水道 类别，
    夏季电力料金调整后，2005-01 起；原始的事业用电力有夏季料金的季节跳动，所以不用）、城市燃气（品目）、电子部件・デバイス（类别）、
    电力变换装置（品目）。
  - 美国行业（Ken French 49 行业相对收益，us_replication_study 同）：Chips、Hardw、Softw、ElcEq、Util、Mach、Cnstr、Oil。
    美国 M 月的收益在日本 M+1 月开盘前已知（美国月末收盘 = 日本次日清晨）。
  - 信号月 2006-10〜2026-08（239 个月）；两半 2006-10〜2016-08 / 2016-09〜2026-08。
  - 局限：主题成员是现在的名单（幸存者偏差；已退市的 NTTデータ 等不在里面）；「AI 需求」本身 2023 年以后才成为主线，20 年回测
    检验的是这些行业之间长期的关系，不是 AI 本身；数据中心主题只有 3 只；月度样本 239 个月，不多。

二、检验（全部是时间序列回归：之后的相对收益 ~ 过去 w 个月的信号；Newey–West t，滞后 = w + h − 2；
    时间错开的对照 = 来源序列循环错开 ≥ 24 个月；w = 1 / 3 / 6，h = 1 / 3 / 6，错峰 L = 0 / 3 / 6 个月（目标 = t+1+L〜t+L+h））
  TA 用户点名的（事先列出 38 对；主格 w = 3、h = 3、L = 0；P1 / P4a 的燃料 → 电力 / 燃气 另加 L = 3 的格（燃料费调整的时滞；
     事先指定的第二格，按同样的规则单独判定、单独标出））：
     P1 进口 LNG / 一般炭 / 原油 → T1 电力（−）；P2 电费 → T1 电力（+）；
     P3 电费 → 化学 / 鉄鋼 / 非鉄金属 / パルプ・紙 / ガラス・土石製品 / T7 数据中心（−）；P4a 进口 LNG → T2 燃气（−）；P4b 城市燃气价格 → T2（+）；
     D1 美国 Chips → T3 / T4 / T5 / T6 / T7 / T9 / T10 / T11（+）；D2 美国 Softw、Hardw → T9（+）；
     D3 T9 半导体设备 → T3 / T4 / T5 / T6 / T7 / T10 / T11（+）；D4 T3 电线、T4 重电 → T5 空调・冷却、T6 电气工程（+）；
     D5 美国 Util → T1 / T3 / T4（+）；E1 电力变换装置价格 → T4（+）；E2 电子部件价格 → T11（+）。
     每一对「成立」= 主格全期 t 在事先方向、对照（24〜215 个月的每一种错法）的单侧经验 p < 0.05、两半 t 都在事先方向。
     另列 27 个 (w, h, L) 格里两半都 |t| ≥ 1.645 且在事先方向的格。38 对里没有关系时偶然「成立」约 1〜2 对。
  TB 横展开（全部来源 × 全部被预测方 × 27 格）：三个渠道分别做（日本价格 → 行业 / 主题；美国行业 → 日本；主题 → 行业 / 主题，
     不含主题自己、也不含成员过半所在的東証业种）；前半 Benjamini–Hochberg（错误发现率 10%）发现 → 后半同号且单侧 p < 0.05 复现；
     对照 = 等间隔 9 种错法的平均与最少〜最多（实际的复现数要超出对照的最多才算有东西）。
  TC 突破买点（日経225 样本外 2013〜；门槛同 supply_chain_study ①〜④；③ 的组合只用「跳过」、不改排序，因为只有部分股票有分数）：
     W1 主题动量 = 所在主题过去 3 个月的相对收益（只给主题成员的信号打分）；
     W2 AI 链顺风 = 美国 Chips 过去 3 个月的相对收益（只给 AI 链主题 T3 / T4 / T5 / T6 / T7 / T9 / T10 / T11 成员的信号打分）；
     对照 V0 = 所在東証业种过去 3 个月的相对收益（同一批交易上比较）。信号日用当天或之前最近的月末（系统在日美都收盘后的清晨决策）。

三、之后
  - 模拟盘规则不变，除非 W1 / W2 通过门槛并且用户在对话里确认；通过也先进前向记录（另行登记）。
  - TA 主格「成立」、对照经验 p ≤ 0.01、两半 |t| 都 ≥ 1.645 → 提议作为日报的参考显示（要用户确认）；否则只写进研究记录。
  登记前做过的检查：tests/test_themes.py（成员唯一、主题收益、成员不足时缺值、错峰对齐、扫描能发现埋进去的晚到关系、
  时间错开对照）；合成数据全流程跑通：埋进去的「进口 LNG m 月涨价 → 电力主题 m+5 月变差」只在 w = 1、h = 1、L = 3 的格被发现
  （t −9.67 / −11.40，L = 0 / 6 没有），要偷看未公布物价的「一般炭 m 月 → 电力 m+1 月」没有被发现；
  TB 按渠道汇总的复现数被成堆的噪声主导（合成数据里对照的范围 3〜27，埋进去的强关系也超不过）→ 渠道汇总只作参照，
  提议显示改按单对的规则（上一条）；真实数据只看了覆盖。

输出：var/out/theme_study.md / .json / .csv（TB 全部检验，两半并排）
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
import lag_study as LS                                                       # noqa: E402
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
import supply_chain_study as SCS                                             # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import sector_leadlag as SL                                      # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak import themes as TH                                              # noqa: E402
from qbreak import us_industry as UI                                         # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

START_JP, GAP, N_PLACEBO, Q_FDR, P_SHOW = "2006-10-01", 24, 9, 0.10, 0.01
LAGS = (0, 3, 6)
JP_PRICE = {"lng": ("进口 LNG 价格", "PRCG20_2600550011"), "coal": ("进口一般炭价格", "PRCG20_2600550009"),
            "crude": ("进口原油价格", "PRCG20_2600550010"), "power": ("电费（夏季调整后）", "PRCG20_22G2220001"),
            "citygas": ("城市燃气价格", "PRCG20_2202250002"), "elecdev": ("电子部件价格", "PRCG20_2201520001"),
            "pconv": ("电力变换装置价格", "PRCG20_2201650015")}
US_SRC = ["Chips", "Hardw", "Softw", "ElcEq", "Util", "Mach", "Cnstr", "Oil"]
TA_LIST = ([("P1", f"jp:{s}", "T1", -1, True) for s in ("lng", "coal", "crude")]
           + [("P2", "jp:power", "T1", 1, False)]
           + [("P3", "jp:power", t, -1, False) for t in ("化学", "鉄鋼", "非鉄金属", "パルプ・紙", "ガラス・土石製品", "T7")]
           + [("P4a", "jp:lng", "T2", -1, True), ("P4b", "jp:citygas", "T2", 1, False)]
           + [("D1", "us:Chips", t, 1, False) for t in ("T3", "T4", "T5", "T6", "T7", "T9", "T10", "T11")]
           + [("D2", f"us:{s}", "T9", 1, False) for s in ("Softw", "Hardw")]
           + [("D3", "th:T9", t, 1, False) for t in ("T3", "T4", "T5", "T6", "T7", "T10", "T11")]
           + [("D4", f"th:{s}", t, 1, False) for s in ("T3", "T4") for t in ("T5", "T6")]
           + [("D5", "us:Util", t, 1, False) for t in ("T1", "T3", "T4")]
           + [("E1", "jp:pconv", "T4", 1, False), ("E2", "jp:elecdev", "T11", 1, False)])
MAIN, MAIN_L3 = (3, 3, 0), (3, 3, 3)
CANDS = {"W1": "主题动量（主题成员）", "W2": "AI 链顺风（美国 Chips → AI 链主题成员）"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def lab(k: str) -> str:
    """来源 / 被预测方的中文名。"""
    kind, _, key = k.partition(":") if ":" in k else ("", "", k)
    if kind == "jp":
        return JP_PRICE[key][0]
    if kind == "us":
        return f"美国 {key}（{UI.FF49_CN[key]}）"
    key = key or k
    if key in TH.THEMES:
        return f"{key} {TH.THEMES[key][0]}"
    return key


def build_sources(P_jp: pd.DataFrame, Mus: pd.DataFrame, Mj: pd.DataFrame, months: pd.DatetimeIndex) -> dict[int, pd.DataFrame]:
    """{w: 月末 × 来源}：jp:价格（对数变化，发布滞后 1 个月）、us:行业、th:主题（过去 w 个月的相对收益）。"""
    out = {}
    for w in SC.WINDOWS:
        a = SC.price_change(P_jp, months, w).add_prefix("jp:")
        b = SC.past(Mus, w).reindex(months).add_prefix("us:")
        c = SC.past(Mj[list(TH.THEMES)], w).reindex(months).add_prefix("th:")
        out[w] = pd.concat([a, b, c], axis=1)
    return out


def main(argv=None) -> int:
    import argparse
    from qbreak import factors
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-b", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/theme_study.py", "qbreak/themes.py", "qbreak/us_industry.py",
                            "qbreak/supply_chain.py", "qbreak/sector_leadlag.py", "qbreak/factors.py", "scripts/supply_chain_study.py",
                            "scripts/lag_study.py", "scripts/score_study.py", "scripts/signal_study.py", "qbreak/signal_score.py",
                            "qbreak/engine.py", "qbreak/unified.py", "qbreak/strategy.py", "qbreak/data.py", "var/industry_s33.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    data_x = load_universe(W.tickers(W.load()), d21)
    allo = {**data_n, **data_x}
    need = [f"{c}.T" for c in TH.members() if f"{c}.T" not in allo]
    data_t = {**allo, **load_universe(need, d21)} if need else allo
    CC, _ = SL.industry_returns(allo, s33)
    cc_all = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in allo.items() if t in s33}).sort_index()
    Rth = TH.theme_returns(data_t, cc_all.mean(axis=1))
    Mj = SC.monthly(pd.concat([CC, Rth], axis=1))
    Mj = Mj[(Mj.index >= pd.Timestamp("2005-10-31")) & (Mj.index <= CC.index.max())]
    tse = list(CC.columns)
    Mus = UI.relative_log(factors.ff_industries(49, "vw"))[US_SRC]
    P_jp = pd.DataFrame({k: factors.boj_monthly("PR01", code, start="200001") for k, (_, code) in JP_PRICE.items()})
    MON = Mj.index[Mj.index >= pd.Timestamp(START_JP)]
    H = UI.halves(MON)
    FULL = (MON[0], MON[-1])
    X = build_sources(P_jp, Mus, Mj, Mj.index)
    Y = {(h, L): TH.ahead_lag(Mj, h, L) for h in SC.HORIZONS for L in LAGS}
    n_mem = {k: int(sum(f"{c}.T" in data_t for c in v[2])) for k, v in TH.THEMES.items()}
    say(f"# 日本细分主题 + 错峰 + 行业关联：横展开到全部行业（{pd.Timestamp.today().date()}）")
    say(f"被预测方 {Mj.shape[1]} 个（東証 {len(tse)} 业种 + 主题 {len(TH.THEMES)} 个：" + "、".join(f"{k} {v[0]} {n_mem[k]} 只" for k, v in TH.THEMES.items())
        + f"）；信号月 {MON[0].date()}〜{MON[-1].date()}（{len(MON)} 个月）；两半 {H['H1'][0].date()}〜{H['H1'][1].date()} / {H['H2'][0].date()}〜；"
        f"来源：日本价格 {len(JP_PRICE)} 种、美国行业 {len(US_SRC)} 个、主题 {len(TH.THEMES)} 个；错峰 L = {LAGS} 个月。"
        "规则见 scripts/theme_study.py 开头（先提交后运行）。")

    # ── TA 用户点名的 ──
    say("\n## TA) 用户点名的关系（主格 过去 3 个月 → 之后 3 个月、L = 0；事先方向：− = 涨价 / 上涨后跑输，+ = 之后跟涨）")
    say("| 编号 | 来源 → 被预测 | 方向 | 全期 t（对照经验 p） | 两半 t | L = 3 的全期 t（p） | 两半都 |t| ≥ 1.645 且在事先方向的格（w→h 错 L） | 成立 |")
    say("|---|---|---|---|---|---|---|---|")
    TA = []
    for code, src, tgt, sg, l3 in TA_LIST:
        cells = []
        for w in SC.WINDOWS:
            for (h, L), Yk in Y.items():
                xv, yv = X[w][src].reindex(MON).to_numpy(float), Yk[tgt].reindex(MON).to_numpy(float)
                th = [SL.nw_t(xv[np.asarray((MON >= a) & (MON <= b))], yv[np.asarray((MON >= a) & (MON <= b))], w + h - 2)[1] for a, b in H.values()]
                if all(np.isfinite(v) and v * sg >= 1.645 for v in th):
                    cells.append(f"{w}→{h} 错 {L}")
        res = {}
        for tag, (w, h, L) in (("main", MAIN), ("l3", MAIN_L3)):
            if tag == "l3" and not l3:
                continue
            tf, pt = UI.placebo_ts(X[w][src], Y[(h, L)][tgt], MON, FULL, w + h - 2, GAP)
            xv, yv = X[w][src].reindex(MON).to_numpy(float), Y[(h, L)][tgt].reindex(MON).to_numpy(float)
            th = [SL.nw_t(xv[np.asarray((MON >= a) & (MON <= b))], yv[np.asarray((MON >= a) & (MON <= b))], w + h - 2)[1] for a, b in H.values()]
            res[tag] = {"t": round(float(tf), 2), "p": SC.placebo_p(tf, pt, sg), "t_H1": round(float(th[0]), 2), "t_H2": round(float(th[1]), 2)}
        def rule(m: dict) -> bool:
            return bool(np.isfinite(m["t"]) and m["t"] * sg > 0 and m["p"] is not None and m["p"] < 0.05
                        and m["t_H1"] * sg > 0 and m["t_H2"] * sg > 0)
        m = res["main"]
        ok, ok3 = rule(m), (rule(res["l3"]) if "l3" in res else None)
        TA.append({"code": code, "src": src, "target": tgt, "sign": sg, **{f"{k}_{q}": v for k, x in res.items() for q, v in x.items()},
                   "cells": cells, "ok": ok, "ok_l3": ok3})
        l3s = (f"{res['l3']['t']:+.2f}（p {res['l3']['p']}；两半 {res['l3']['t_H1']:+.2f} / {res['l3']['t_H2']:+.2f}）{'✓' if ok3 else '✗'}"
               if "l3" in res else "—")
        say(f"| {code} | {lab(src)} → {lab(tgt)} | {'+' if sg > 0 else '−'} | {m['t']:+.2f}（p {m['p']}） | {m['t_H1']:+.2f} / {m['t_H2']:+.2f} | "
            f"{l3s} | {'、'.join(cells) or '无'} | {'✓' if ok else '✗'} |")
    n_ok = sum(r["ok"] for r in TA)
    say(f"\n{len(TA)} 对里成立 {n_ok} 对（没有关系时偶然约 1〜2 对）：" + ("、".join(f"{r['code']} {lab(r['src'])} → {lab(r['target'])}" for r in TA if r["ok"]) or "无")
        + "；燃料 → 电力 / 燃气 的 L = 3 格成立：" + ("、".join(f"{r['code']} {lab(r['src'])} → {lab(r['target'])}" for r in TA if r["ok_l3"]) or "无"))

    # ── TB 横展开 ──
    t1 = time.time()
    par = TH.parent_overlap({k.split(".")[0]: v for k, v in s33.items()})
    targets = list(Mj.columns)
    fam_pairs = {"日本价格 → 行业 / 主题": [(f"jp:{k}", t) for k in JP_PRICE for t in targets],
                 "美国行业 → 日本": [(f"us:{k}", t) for k in US_SRC for t in targets],
                 "主题 → 行业 / 主题": [(f"th:{k}", t) for k in TH.THEMES for t in targets if t != k and t not in par[k]]}
    SB = pd.concat([TH.scan_lag(X, Y, pr, MON, H, 0, fam) for fam, pr in fam_pairs.items()], ignore_index=True)
    D = TH.replicate_lag(SB, Q_FDR)
    act = UI.summary(D)
    shifts = [GAP + k * (len(MON) - 2 * GAP) // (N_PLACEBO - 1) for k in range(N_PLACEBO)]
    PL = [UI.summary(TH.replicate_lag(pd.concat([TH.scan_lag(X, Y, pr, MON, H, k, fam) for fam, pr in fam_pairs.items()], ignore_index=True), Q_FDR))
          for k in shifts]
    say(f"\n## TB) 横展开（{time.time() - t1:.0f}s）：前半 BH 发现（错误发现率 10%）→ 后半同号复现；错峰 L = {LAGS} 也是检验的一维")
    say(f"对照 = 来源序列循环错开 {', '.join(map(str, shifts))} 个月，重做同样的检验（{N_PLACEBO} 次的平均，发现 / 复现另列最少〜最多；"
        "实际的复现数要超出对照的最多才算横展开里有东西）")
    say("| 渠道 | 检验数 | 前半发现（对照 平均，最少〜最多） | 后半复现（对照） | 前半 |t| ≥ 1.96（对照） | 其中后半同号且 |t| ≥ 1.645（对照） |")
    say("|---|---|---|---|---|---|")
    TBsum = {}
    for fam, x in act.items():
        vals = {q: [z[fam][q] for z in PL if fam in z] for q in ("found", "rep", "sig1_pct", "rep2_pct")}
        pl = {q: float(np.mean(v)) for q, v in vals.items()}
        rg = {q: (int(min(vals[q])), int(max(vals[q]))) for q in ("found", "rep")}
        d = D[(D["family"] == fam) & D["rep"]].assign(m=lambda z: z[["t_H1", "t_H2"]].abs().min(axis=1)).sort_values("m", ascending=False)
        TBsum[fam] = {**x, "placebo": {q: round(v, 2) for q, v in pl.items()}, "placebo_range": rg, "beyond_placebo": bool(x["rep"] > rg["rep"][1]),
                      "top": d.head(15)[["src", "target", "w", "h", "L", "t_H1", "t_H2", "slope_H1", "slope_H2"]].to_dict("records")}
        say(f"| {fam} | {x['n']} | {x['found']}（{pl['found']:.1f}，{rg['found'][0]}〜{rg['found'][1]}） | "
            f"{x['rep']}（{pl['rep']:.1f}，{rg['rep'][0]}〜{rg['rep'][1]}） | {x['sig1_pct']}%（{pl['sig1_pct']:.1f}%） | {x['rep2_pct']}%（{pl['rep2_pct']:.1f}%） |")
    for fam, x in TBsum.items():
        if x["top"]:
            say(f"\n{fam} 复现最强的（两半 |t| 较小的那个排序，最多 15 个）：")
            for r in x["top"]:
                say(f"- {lab(r['src'])} → {lab(r['target'])}（过去 {r['w']} 月 → 错 {r['L']} 月后的 {r['h']} 个月）：t {r['t_H1']:+.2f} / {r['t_H2']:+.2f}")
    prop = [r for r in TA if r["ok"] and r["main_p"] is not None and r["main_p"] <= P_SHOW
            and abs(r["main_t_H1"]) >= 1.645 and abs(r["main_t_H2"]) >= 1.645]
    say(f"\n按登记：TA 主格成立、对照经验 p ≤ {P_SHOW}、两半 |t| 都 ≥ 1.645 → " + ("提议作为日报的参考显示（要用户确认）：" + "、".join(
        f"{lab(r['src'])} → {lab(r['target'])}" for r in prop) if prop else "没有 → 只写进研究记录"))

    out = {"code": head, "TA": TA, "TA_ok": n_ok, "TB": TBsum, "proposal": [f"{r['src']}→{r['target']}" for r in prop],
           "members_loaded": n_mem}
    fp = paths.out_dir() / "theme_study"
    if not args.skip_b:
        out["TC"] = part_c(Mj, Mus, tse, s33, data_n)
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    D.round(4).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


def part_c(Mj: pd.DataFrame, Mus: pd.DataFrame, tse: list[str], s33: dict, data_n: dict) -> dict:
    """突破买点：W1 主题动量、W2 AI 链顺风（只给部分股票打分；组合只跳过）。"""
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t1 = time.time()
    p = load_params(market="JP")
    ind0 = dict(IndicatorCache(data_n).all(p))
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rows = S.signal_rows(S.feature_panel(ind0, load(*SYM["JP"])["Close"]), ind0, SS.START)
    mem = TH.members()
    th_of = [mem.get(t.split(".")[0]) for t in rows["ticker"]]
    ind_of = [s33.get(t) for t in rows["ticker"]]
    rows["w1"] = SCS.daily_lookup(SC.past(Mj[list(TH.THEMES)], 3), rows["date"], th_of)
    chips = pd.DataFrame({"x": SC.past(Mus, 3)["Chips"]})
    ai = np.array([k in TH.AI_CHAIN for k in th_of])
    rows["w2"] = np.where(ai, SCS.daily_lookup(chips, rows["date"], ["x"] * len(rows)), np.nan)
    rows["v0"] = SCS.daily_lookup(SC.past(Mj[tse], 3), rows["date"], ind_of)
    Tn = LS.label_all(SS.trades(ind0, p, bt), ind0, rows, gidx)
    To = Tn[Tn["sig_date"] >= pd.Timestamp(Z.OOS0)]
    run = SS.s0c2_builder(data_n, p)
    base = {"all": SS.stats(To), "halves": {h: SS.stats(Z.span(To, w)) for h, w in Z.HALVES.items()}, "s0c2": Z.s0c2(run, ind0)}
    sc0 = LS.raw_walk_forward(rows, Tn, "v0", Z.YEARS)
    ref = Z.attach(Tn, sc0)
    refo = ref[ref["sig_date"] >= pd.Timestamp(Z.OOS0)]
    R = {}
    for k in CANDS:
        sc = LS.raw_walk_forward(rows, Tn, k.lower(), Z.YEARS)
        r = LS.evaluate_scored(sc, Tn, To, base, ind0, p, bt, run)
        r["s0c2_skip"] = Z.s0c2(run, Z.skip_low(ind0, sc), None)              # 只跳过、不改排序（事先规定）
        r["dauc"] = LS.paired_dauc(r["_To"], refo)
        cov = np.isfinite(r["_To"]["score"].to_numpy())
        r["ref_auc"] = Z.rnd(auc_np(refo[cov]["score"], refo[cov]["win"]))
        r["coverage"] = round(float(cov.mean()) * 100, 1)
        r["n_cov"] = int(cov.sum())
        R[k] = r
        print(k, r["auc"], r["dauc"], flush=True)
    V = SCS.decide(R, base["s0c2"])
    fa = lambda v, f="{:.4f}": "—" if v is None else f.format(v)                     # noqa: E731
    say(f"\n## TC) 突破买点（日経225 样本外 2013〜 全部 {base['all']['n']} 笔，胜率 {base['all']['win']}%；{time.time() - t1:.0f}s）")
    say("| 候选 | 有分数的笔数 | AUC 全期（95% 区间） | 2013〜2019 / 2020〜 | 对照 V0（同一批交易） | AUC 差（95% 区间） | 保留的胜率 前半 / 后半（全部 "
        f"{base['halves']['O1']['win']}% / {base['halves']['O2']['win']}%） | S0C2 只跳过 20 年 |")
    say("|---|---|---|---|---|---|---|---|")
    for k, r in R.items():
        a, d, s = r["auc"], r["dauc"], r["s0c2_skip"]
        say(f"| {k} {CANDS[k]} | {r['n_cov']}（{r['coverage']}%） | {fa(a['all'])}（{fa(a['lo'], '{:.3f}')}〜{fa(a['hi'], '{:.3f}')}） | "
            f"{fa(a['O1'])} / {fa(a['O2'])} | {fa(r['ref_auc'])} | {fa(d['d'], '{:+.4f}')}（{fa(d['lo'], '{:+.4f}')}〜{fa(d['hi'], '{:+.4f}')}） | "
            f"{r['kept']['O1'].get('win')}% / {r['kept']['O2'].get('win')}% | {s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} |")
    s0 = base["s0c2"]
    say(f"\n现行 S0C2 20 年 {s0['w20_cagr']}% / {s0['w20_dd_exact']:.2f}% / Calmar {s0['w20_calmar_exact']:.3f}")
    say("\n## 判定（① AUC ≥ 0.55 且下限 > 0.5；② 两个半段保留的胜率 +3 pp 且期望不降；③ S0C2（只跳过）Calmar 不降、回撤不更深；④ 比对照 V0 AUC +0.02 且下限 > 0）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n通过：{'、'.join(V['passed'])} → 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）。" if V["passed"]
        else "\n主题 / AI 链的候选没有通过 → 维持现行（模拟盘规则不变）。")
    return {"decision": V, "base": base, "results": {k: {q: v for q, v in r.items() if not q.startswith("_")} for k, r in R.items()}}


if __name__ == "__main__":
    raise SystemExit(main())
