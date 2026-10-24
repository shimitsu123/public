"""timing3_study.py — 顶底 / 牛熊分界第三轮：给「快」加独立确认，提高准确度（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

一、为什么是这几个方向（第二轮：d3fb402 登记、7f003cc 结果；这一轮是看过那些结果之后设计的）
  - T7 双速离场让识别变准：样本外平衡准确率 美 0.772→0.820、日 0.707→0.723，熊市识别中位延迟 美 39.5→20、日 30→21.5 交易日，
    S0C2 20 年回撤 −35.10%→−27.85%；但日本样本外误报 3→9 次、日本 2006– Calmar 0.212→0.111、美 1990–2005 0.468→0.449。
  - T8 信用加快离场的平衡准确率最高（美 0.832、日 0.737），日本 2006– Calmar +0.055、滚动前推 7 折没有一折输给 T0；
    但美国两个半段都更差（0.403 / 0.309）。
  - T11 V 形回补把回补延迟从 美 98 缩到 10.5 交易日，但在多段下跌的熊市里反复被套（互联网泡沫 −23.5% vs −8.6%，S0C2 回撤 −43.67%）。
  → 共同的问题：「快」本身带来误报 / 被套。这一轮不改快速条件的参数，只给它加一个独立的确认。

二、候选（qbreak/timing.py 的 T12〜T15；参数全部沿用第二轮 / T3，或取常用值；不做网格搜索）
  T12 快速离场要信用确认：T0 之外，「T7 的快速条件（收在 250 日线下且距 250 日最高收盘 −10%，连续 2 天）且 Baa−10Y 利差
      高于其 250 日均值（T3 的信用条件）」→ 立即转熊；回补同 T0。利差 1986 年起才有，之前 = T0。
  T13 快速离场要另一个大市场确认：T0 之外，「T7 的快速条件 且 另一个大市场收在它自己的 250 日线下」→ 立即转熊；回补同 T0。
      另一个市场：美股（S&P500、纳斯达克）用日経（同一天已收盘），其他市场用 S&P500（前一天收盘）。
  T14 V 形回补要趋势确认：T11 的提前回补（熊市里自最低收盘 +20% → 转牛；回到 250 日线上方之前自回补后最高收盘 −10% → 再转熊；
      回到线上方后恢复 T0），另要当天「收在 50 日线上 且 50 日线比 20 个交易日前高」（50 日 / 20 日为常用值）。离场同 T0。
  T15 两头都改：离场同 T12，回补同 T14。
  时滞与第二轮相同：指数用当天收盘；美股信号在日本次日早上已知，日経信号晚一天执行；Baa 利差滞后 1 个美国营业日，
  日経与独立市场用的利差再晚一天。

三、评价
  1)〜5) 与第二轮完全相同（直接调用 scripts/timing2_study.py 的函数）：美 ^GSPC / 日 ^N225 的分界准确度（训练 ≤2005 /
     样本外 2006–）、指数层 Calmar 两半段（美：日元计价 S&P500 总收益；日：日経 + 股息 1.6%/年；日元现金、每次切换 0.02%）、
     S0C2 组合 20 年（现行立花费用，只换美股的牛熊序列）、滚动前推 7 折、自助法区间（平稳块 250 天 ×2,000，种子 20260926）。
  6) 独立市场（设计时没看过：之前的牛熊研究只用过 ^GSPC 与 ^N225；登记前只查了这些指数的起止日期与单日 >25% 的跳动，
     没有算任何分界结果）：德 ^GDAXI、英 ^FTSE、法 ^FCHI、瑞士 ^SSMI、荷兰 ^AEX、加拿大 ^GSPTSE、澳洲 ^AXJO、香港 ^HSI、
     台湾 ^TWII、美国纳斯达克 ^IXIC（10 个，欧洲 5 个彼此相关），各自全部历史（去掉当天可能未收盘的 K 线），事后标注同样 20%/20%。
     指标（bullbear.evaluate）：平衡准确率、熊市识别中位延迟、误报 / 漏报、每年切换、择时 Calmar（牛持指数 / 熊持现金，
     价格指数不含股息，现金 0%，每次切换 0.10%，信号次日生效）。第二轮的 T7 / T8 / T11 作为对照也列出（不参与判定）。

四、采用门槛（全部满足才算「通过」，否则维持 T0）
  ① 指数层 Calmar：美、日各两个半段（共 4 个）都 ≥ T0 + 0.05（同第二轮，用户指定）
  ② S0C2 20 年最大回撤不比 T0 深（同第二轮）
  ③ 样本外熊市识别中位延迟：美、日都不比 T0 长（同第二轮）
  ④ 样本外平衡准确率：美、日都不低于 T0（新：这一轮的目标是提高准确度）
  ⑤ 独立市场：平衡准确率不低于 T0 的市场过半，且择时 Calmar 不低于 T0 的市场过半；有数据的市场不到 5 个 → 不满足
     （新：候选是看过第二轮结果才设计的，美、日的数据已经「用过」，用没看过的市场抵消这个偏差）
  另报（不改判定，醒目标出）：第二轮的全部另报项（各半段年化 ≥ T0 − 0.5 pp、S0C2 20 年年化 ≥ T0 − 0.3 pp、S0C2 5 年回撤 ≥ −30%、
  自助法「差 ≥ +0.05」比例 < 50%、滚动前推过半输给 T0、样本外误报 / 漏报比 T0 多），以及独立市场里误报多于 T0 的市场过半。

五、之后（同第二轮）
  - 不改模拟盘的交易规则，除非候选通过门槛、并且用户在对话里确认。
  - 通过的候选：加进季度复核的观察名单（与 T2 / T3 并列），从下一个交易日起前向记录一个季度，之后的季度复核再决定；
    多个通过时按 4 个 Calmar 差的平均排序（差 < 0.02 取每年切换少的）。
  - 季度复核：`python scripts/timing3_study.py --review --only T0,<通过的候选>`（同一套规则，只加数据；
    输出 var/out/timing3_review_<日期>.*，并在 var/out/timing3_review_history.csv 追加一行）。
  登记前做过的检查：合成行情上全流程跑通（含独立市场的代码路径）。美日部分用的是第二轮已验证过的函数；
  独立市场的真实数据在登记之前一次都没有跑过。
  局限：美、日两个市场的结果对这一轮的候选偏乐观（设计时看过）；独立市场与美股高度同步（全球性熊市），不是完全独立的样本；
  确认条件（信用、另一个市场）在 2008、2020 这类全球性下跌里几乎总是成立，所以这一轮主要改变的是「局部下跌」里的误报。

输出：var/out/timing3_study.md / .json / .csv
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak import timing as T                                               # noqa: E402
from qbreak.bullbear import BEAR, _sma, date_phases, evaluate                # noqa: E402
import timing2_study as S2                                                   # noqa: E402
from bullbear_study import load                                              # noqa: E402
from timing_study import EPISODES, asof                                      # noqa: E402

KEYS = list(T.STATES3)                                        # T0 + T12〜T15
REFS = list(T.REF3)                                           # 第二轮对照（只在独立市场列出）
MKTS = S2.MKTS
DELTA = S2.DELTA
INDEP = {"^GDAXI": "德国 DAX", "^FTSE": "英国 FTSE100", "^FCHI": "法国 CAC40", "^SSMI": "瑞士 SMI", "^AEX": "荷兰 AEX",
         "^GSPTSE": "加拿大 TSX", "^AXJO": "澳洲 ASX200", "^HSI": "香港 恒生", "^TWII": "台湾 加权", "^IXIC": "美国 纳斯达克综合"}
US_LIKE = {"^IXIC"}                                           # 与 S&P500 同时收盘：「另一个市场」用日経（同一天）
MIN_INDEP = 5
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def below_ma(close: pd.Series) -> pd.Series:
    """每天是否收在自己的 250 日线下（只用当天为止的收盘）。"""
    v = close.to_numpy(float)
    ma = _sma(v, T.L)
    return pd.Series(np.where(np.isnan(ma), np.nan, (v < ma).astype(float)), index=close.index)


def add_other(D: dict) -> dict:
    """T13 用的「另一个大市场在 250 日线下」：美股用日経（同一天已收盘），日経用 S&P500（前一天）。"""
    nk_b, sp_b = below_ma(D["n225"]), below_ma(D["spx"])
    D["f"]["US"]["other_below"] = asof(nk_b, D["spx"].index) > 0.5
    D["f"]["JP"]["other_below"] = asof(sp_b, D["n225"].index - pd.Timedelta(days=1)) > 0.5
    D["below"] = {"US": sp_b, "JP": nk_b}
    return D


def run_detectors(D: dict, keys, registry: dict) -> dict:
    out = {}
    for k in keys:
        out[k] = {}
        for m in MKTS:
            c, f = D["close"][m], D["f"][m]
            st = registry[k](c, f)
            out[k][m] = {"states": st, "expo": pd.Series((st != BEAR).astype(float), index=c.index)}
    return out


# ── 6) 独立市场 ──
def indep_markets(D: dict, keys, refs) -> dict:
    today = pd.Timestamp.today().normalize()
    f_us = D["f"]["US"]
    out = {}
    for tk, name in INDEP.items():
        try:
            c = load(tk, "1950-01-01")["Close"].dropna()
        except Exception as e:                                                # noqa: BLE001
            out[tk] = {"name": name, "error": str(e)[:120]}
            continue
        c = c[(c > 0) & (c.index < today)]
        if len(c) < T.L + 300:
            out[tk] = {"name": name, "error": f"数据太短（{len(c)} 天）"}
            continue
        f = pd.DataFrame({col: asof(f_us[col], c.index - pd.Timedelta(days=1)) for col in ("baa", "baa_ma250")}, index=c.index)
        other = D["below"]["JP"] if tk in US_LIKE else D["below"]["US"]
        lag = pd.Timedelta(days=0) if tk in US_LIKE else pd.Timedelta(days=1)
        f["other_below"] = asof(other, c.index - lag) > 0.5
        lab = date_phases(c)[1]
        row = {"name": name, "from": str(c.index[0].date()), "to": str(c.index[-1].date())}
        for k in list(keys) + list(refs):
            reg = T.STATES3 if k in T.STATES3 else T.REF3
            e = evaluate(reg[k](c, f), lab, c)
            row[k] = {q: e.get(q) for q in ("bal_acc", "bear_phases", "bear_lag_med", "bull_lag_med", "false_alarms",
                                             "missed_bears", "switches_per_yr", "sw_cagr", "sw_dd", "sw_calmar", "bh_calmar")}
        out[tk] = row
        print("独立市场", tk, {k: (row[k]["bal_acc"], row[k]["sw_calmar"]) for k in list(keys) + list(refs)}, flush=True)
    return out


def _ge(a, b) -> bool:
    return a is not None and b is not None and np.isfinite(a) and np.isfinite(b) and a >= b


def indep_counts(I: dict, k: str) -> dict:
    ok = [r for r in I.values() if "error" not in r]
    return {"n": len(ok), "ba": sum(_ge(r[k]["bal_acc"], r["T0"]["bal_acc"]) for r in ok),
            "calmar": sum(_ge(r[k]["sw_calmar"], r["T0"]["sw_calmar"]) for r in ok),
            "more_fa": sum((r[k]["false_alarms"] or 0) > (r["T0"]["false_alarms"] or 0) for r in ok)}


# ── 判定（事先规则）──
def decide(A, B, C, WF, BS, I, keys) -> dict:
    base = S2.decide(A, B, C, WF, BS, keys)                  # ①②③ 与第二轮的全部另报
    for k, r in base["per"].items():
        for m in MKTS:
            bk, b0 = C[m][k]["oos"].get("bal_acc"), C[m]["T0"]["oos"].get("bal_acc")
            if not _ge(bk, b0):
                r["fails"].append(f"{m} 样本外平衡准确率 {bk} < T0 {b0}")
        n = indep_counts(I, k)
        r["indep"] = n
        if n["n"] < MIN_INDEP:
            r["fails"].append(f"独立市场只有 {n['n']} 个有数据（< {MIN_INDEP}）")
        else:
            if n["ba"] * 2 <= n["n"]:
                r["fails"].append(f"独立市场平衡准确率不低于 T0 的只有 {n['ba']}/{n['n']}")
            if n["calmar"] * 2 <= n["n"]:
                r["fails"].append(f"独立市场择时 Calmar 不低于 T0 的只有 {n['calmar']}/{n['n']}")
            if n["more_fa"] * 2 > n["n"]:
                r["warnings"].append(f"独立市场误报多于 T0 的有 {n['more_fa']}/{n['n']}")
        r["pass"] = not r["fails"]
    passed = [k for k in base["per"] if base["per"][k]["pass"]]
    order = []
    if passed:
        top = max(base["per"][k]["mean_calmar_gain"] for k in passed)
        near = sorted([k for k in passed if base["per"][k]["mean_calmar_gain"] >= top - 0.02],
                      key=lambda k: base["per"][k]["mean_sw_yr"])
        order = near + sorted([k for k in passed if k not in near], key=lambda k: -base["per"][k]["mean_calmar_gain"])
    return {"per": base["per"], "passed": order}


# ── 汇报 ──
def report(D, C, A, B, WF, BS, I, V, keys, refs, t0, head, review) -> None:
    lab = T.LABELS3
    say(f"# 顶底 / 牛熊分界第三轮：给「快」加独立确认（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say(f"数据截至：S&P500 {D['spx'].index[-1].date()}，日経 {D['n225'].index[-1].date()}，Baa 利差 "
        f"{D['raw']['BAA10Y'].dropna().index[-1].date()}；规则见 scripts/timing3_study.py 开头（先提交后运行）。"
        + ("季度复核模式。" if review else ""))
    say("\n## 1) 分界的准确度：美 ^GSPC / 日 ^N225（事后标注 20%/20%；训练 ≤2005 / 样本外 2006–）")
    say("| 候选 | 市场 | 平衡准确率 训练 / 样本外 | 熊市识别中位延迟 训练 / 样本外 | 回补中位延迟 训练 / 样本外 | 误报 训练 / 样本外 | "
        "漏报 训练 / 样本外 | 每年切换 样本外 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in keys:
        for m in MKTS:
            tr, te = C[m][k]["train"], C[m][k]["oos"]
            say(f"| {k} {lab[k]} | {m} | {tr['bal_acc']} / {te['bal_acc']} | {tr['bear_lag_med']} / {te['bear_lag_med']} 交易日 | "
                f"{tr['bull_lag_med']} / {te['bull_lag_med']} 交易日 | {tr['false_alarms']} / {te['false_alarms']} 次 | "
                f"{tr['missed_bears']} / {te['missed_bears']} 次 | {te['switches_per_yr']} 次 |")
    for m, name in (("US", "美：日元计价 S&P500 总收益（≈1655）"), ("JP", "日：日経225 + 股息 1.6%/年")):
        say(f"\n## 2) 指数层择时 {name}，熊市拿日元现金")
        say("| 方案 | 1990–2005 年化 / 回撤 / Calmar | 2006– 年化 / 回撤 / Calmar | 每年切换 | 持有时间 |")
        say("|---|---|---|---|---|")
        for k in ["BH"] + list(keys):
            r = A[m][k]
            say(f"| {'买入持有' if k == 'BH' else f'{k} {lab[k]}'} | {r['H1']['cagr']}% / {r['H1']['dd']}% / {r['H1']['calmar']} | "
                f"{r['H2']['cagr']}% / {r['H2']['dd']}% / {r['H2']['calmar']} | {r['ALL']['sw_yr']} 次 | {r['ALL']['invested']}% |")
    say(f"\n## 3) S0C2 组合（统一引擎，{B['broker']} 费用，只换美股牛熊序列）")
    say("| 方案 | 20 年年化 / 回撤 / Calmar | 5 年年化 / 回撤 | 20 年 1655 调仓笔数 |")
    say("|---|---|---|---|")
    for k in keys:
        r = B[k]
        say(f"| {k} | {r['w20_cagr']}% / {r['w20_dd_exact']:.2f}% / {r['w20_calmar']} | {r['w5_cagr']}% / {r['w5_dd_exact']:.2f}% | "
            f"{r['w20_core_trades']} 笔 |")
    say("\n## 4) 滚动前推（每 5 年一折的指数层 Calmar）")
    for m in MKTS:
        say(f"\n{m}：")
        say("| 候选 | " + " | ".join(x["fold"] for x in WF[m]["T0"]) + " | 输给 T0 的折数 |")
        say("|---|" + "---|" * (len(S2.FOLDS) + 1))
        for k in keys:
            lost = sum(1 for x, y in zip(WF[m][k], WF[m]["T0"])
                       if x["calmar_exact"] is not None and y["calmar_exact"] is not None and x["calmar_exact"] < y["calmar_exact"])
            say(f"| {k} | " + " | ".join(str(x["calmar"]) for x in WF[m][k]) + f" | {'—' if k == 'T0' else f'{lost}/{len(S2.FOLDS)}'} |")
    say(f"\n## 5) 不确定性（自助法 {S2.BOOT_N} 次；Calmar 差 = 候选 − T0 的 90% 区间，「≥ +{DELTA}」= 达到门槛的比例）")
    say("| 候选 | 美 1990–2005 | 美 2006– | 日 1990–2005 | 日 2006– | 样本外熊市识别延迟差（交易日，90% 区间） |")
    say("|---|---|---|---|---|---|")
    for k in keys:
        if k == "T0":
            continue
        cells = [f"{BS[m][k][h]['p05']:+.3f}〜{BS[m][k][h]['p95']:+.3f}（≥ +{DELTA}：{BS[m][k][h]['share_ge_delta'] * 100:.0f}%）"
                 for m in MKTS for h in ("H1", "H2")]
        lag = "；".join(f"{m} " + (f"{BS[m][k]['lag']['p05']:+.1f}〜{BS[m][k]['lag']['p95']:+.1f}（{BS[m][k]['lag']['n']} 段）"
                                    if "p05" in BS[m][k]["lag"] else f"段数不足（{BS[m][k]['lag']['n']}）") for m in MKTS)
        say(f"| {k} | " + " | ".join(cells) + f" | {lag} |")
    say("\n## 6) 独立市场（设计时没看过；全部历史；择时 = 牛持指数 / 熊持现金，价格指数、现金 0%、每次切换 0.10%）")
    cols = list(keys) + list(refs)
    say("平衡准确率 / 择时 Calmar / 熊市识别中位延迟（交易日）/ 误报（次）：")
    say("| 市场（期间，熊市段数） | " + " | ".join(cols) + " | 买入持有 Calmar |")
    say("|---|" + "---|" * (len(cols) + 1))
    for tk, r in I.items():
        if "error" in r:
            say(f"| {r['name']} {tk} | " + " | ".join("—" for _ in cols) + f" | 没有数据：{r['error']} |")
            continue
        cells = [f"{r[k]['bal_acc']} / {r[k]['sw_calmar']} / {r[k]['bear_lag_med']} / {r[k]['false_alarms']}" for k in cols]
        say(f"| {r['name']} {tk}（{r['from'][:4]}–{r['to'][:4]}，{r['T0']['bear_phases']} 段） | " + " | ".join(cells)
            + f" | {r['T0']['bh_calmar']} |")
    say("\n不低于 T0 的市场数（平衡准确率 / 择时 Calmar；误报多于 T0 的市场数）：")
    for k in cols:
        if k == "T0":
            continue
        n = indep_counts(I, k)
        say(f"- {k} {lab[k]}：{n['ba']}/{n['n']} · {n['calmar']}/{n['n']}（误报更多 {n['more_fa']}/{n['n']}）")
    say("\n## 7) 样本外每一段熊市（离场延迟 / 离场时距高点；回补延迟 / 回补时距底部）")
    for m in MKTS:
        say(f"\n{m}：")
        say("| 熊市（高点→底部，跌幅） | " + " | ".join(keys) + " |")
        say("|---|" + "---|" * len(keys))
        for i, e in enumerate(C[m]["T0"]["episodes_oos"]):
            cells = []
            for k in keys:
                x = C[m][k]["episodes_oos"][i]
                ex = f"{x['exit_lag']} 天 {x['dd_at_exit_pct']}%" if x["exit_lag"] is not None else "漏报"
                re = f"{x['reentry_lag']} 天 {x['gain_at_reentry_pct']:+.1f}%" if x["reentry_lag"] is not None else "—"
                cells.append(f"离 {ex}；回 {re}")
            say(f"| {e['peak']}→{e['trough']}（{e['depth_pct']}%） | " + " | ".join(cells) + " |")
    say("\n## 8) 美股 9 次下跌（日元计；「跌」= 顶→底，「后 12 月」= 底后一年）")
    heads = [f"{en}|{tag}" for en, _, _ in EPISODES for tag in ("跌", "后12月")]
    say("| 方案 | " + " | ".join(h.replace("|", " ") for h in heads) + " |")
    say("|---|" + "---|" * len(heads))
    for k in ["BH"] + list(keys):
        say(f"| {k} | " + " | ".join(f"{A['US'][k]['episodes'].get(h, '—')}%" for h in heads) + " |")
    say("\n## 判定（事先规则：① 美、日各两半段 Calmar ≥ T0 + 0.05；② S0C2 20 年回撤不比 T0 深；③ 样本外识别延迟美、日都不增加；"
        "④ 样本外平衡准确率美、日都不低于 T0；⑤ 独立市场平衡准确率与择时 Calmar 都在过半市场里不低于 T0）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）")
            + (f"。另报：{'；'.join(r['warnings'])}" if r["warnings"] else "")
            + f"。4 个 Calmar 差的平均 {r['mean_calmar_gain']:+.3f}")
    if V["passed"]:
        say(f"\n通过：{'、'.join(V['passed'])} → 加进季度复核观察名单，前向记录一个季度再决定；模拟盘规则不变（改需用户确认）。")
    else:
        say("\n没有候选通过 → 维持 T0（模拟盘规则不变）。")
    say(f"\n代码版本 {head}")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只比较这些候选（逗号分隔，须含 T0）")
    ap.add_argument("--review", action="store_true", help="季度复核：输出带日期的文件并追加历史")
    args = ap.parse_args(argv)
    keys = args.only.split(",") if args.only else KEYS
    if "T0" not in keys or any(k not in T.STATES3 for k in keys):
        raise SystemExit(f"--only 必须包含 T0，且只能是 {KEYS}")
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/timing3_study.py", "scripts/timing2_study.py",
                            "qbreak/timing.py", "qbreak/unified.py", "qbreak/bullbear.py"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    D = add_other(S2.load_inputs())
    R = run_detectors(D, keys, T.STATES3)
    C = S2.classification(D, R, keys)
    P = S2.index_prices(D)
    A, EQ = S2.index_tests(P, R, keys)
    WF = S2.walk_forward(D, P, R, keys)
    BS = S2.bootstrap(EQ, C, keys)
    refs = [] if args.review else REFS
    I = indep_markets(D, keys, refs)
    B = S2.s0c2(D, R, keys)
    V = decide(A, B, C, WF, BS, I, keys)
    report(D, C, A, B, WF, BS, I, V, keys, refs, t0, head, args.review)
    fp = paths.out_dir() / ("timing3_study" if not args.review else f"timing3_review_{pd.Timestamp.today().date()}")
    if args.review:
        hist = paths.out_dir() / "timing3_review_history.csv"
        row = {"run": str(pd.Timestamp.today().date()), "data_end": str(D["spx"].index[-1].date()), "passed": "|".join(V["passed"])}
        for k in keys:
            for m in MKTS:
                row.update({f"{k}_{m}_H1_calmar": A[m][k]["H1"]["calmar"], f"{k}_{m}_H2_calmar": A[m][k]["H2"]["calmar"],
                            f"{k}_{m}_lag_oos": C[m][k]["oos"].get("bear_lag_med"), f"{k}_{m}_ba_oos": C[m][k]["oos"].get("bal_acc")})
            row.update({f"{k}_B20_cagr": B[k]["w20_cagr"], f"{k}_B20_dd": round(B[k]["w20_dd_exact"], 2)})
        old = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
        pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(hist, index=False)
    strip = lambda d: {k: v for k, v in d.items() if k != "episodes"}                        # noqa: E731
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "decision": V, "classification": C,
                                              "index": {m: {k: strip(v) for k, v in A[m].items()} for m in MKTS},
                                              "index_episodes_us": {k: A["US"][k]["episodes"] for k in A["US"]},
                                              "s0c2": B, "walk_forward": WF, "bootstrap": BS, "independent": I},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    rows = []
    for k in keys:
        row = {"cand": k, "label": T.LABELS3[k], "pass": V["per"].get(k, {}).get("pass")}
        for m in MKTS:
            for h in ("H1", "H2", "ALL"):
                row.update({f"{m}_{h}_{q}": A[m][k][h][q] for q in ("cagr", "dd", "calmar", "sw_yr")})
            row.update({f"{m}_oos_{q}": C[m][k]["oos"].get(q) for q in ("bal_acc", "bear_lag_med", "bull_lag_med",
                                                                         "false_alarms", "missed_bears")})
        row.update({q: B[k][q] for q in ("w20_cagr", "w20_dd", "w5_cagr", "w5_dd", "w20_core_trades")})
        if k != "T0":
            n = indep_counts(I, k)
            row.update({"indep_n": n["n"], "indep_ba_ge": n["ba"], "indep_calmar_ge": n["calmar"], "indep_more_fa": n["more_fa"]})
        rows.append(row)
    pd.DataFrame(rows).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
