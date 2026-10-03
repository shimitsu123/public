"""tune_study.py — 选股参数的联合调参 → 验证：能不能同时提高胜率与每笔收益（2026-09-28 登记，登记之后才运行一次）。

用户（2026-09-28）：「现在选择股票法进行类似设定个参数进行调参后然后进行验证 提高胜率和收益率的研究」。
以前做过的（不重复）：param_study（2026-09-26）43 个参数「每次只改一个」、看组合 Calmar，发现期挑出的「出货日上限 4」验证期不通过；
  adaptive_study 36 组（箱体 × MACD）每年重选，A1 / A3 差一点（Calmar +0.045 / +0.048 < +0.05）；pit_retrain 重训的一组验证期更差。
这一轮新的：① 9 个买点参数**一起**调（网格 13,122 组里：现行 + 17 个一步邻居 + 随机 150 组 = 168 组）；② 目标直接是用户要的
  「胜率与每笔收益」（逐信号，样本大：J-Quants 时点 TOPIX 1000 2017〜 约 1,100 个信号 + 日経225 2006〜2016）；③ 先量「调参会不会过拟合」
  （组合对称交叉验证 CSCV 的 PBO）；④「每年重调一次」这个做法本身在样本外好不好（walk-forward）；⑤ 选出的一组用没看过参数的数据验证一次。
规则（运行前写定；结果出来不改）：
一 参数网格（scripts/tune_common.GRID；卖法 = 现行，MACD 死叉与放量阴线跟着那一组的 MACD / 均量天数）：
   箱体天数 40 / 60 / 90；箱体振幅 10 / 15 / 20%；放量倍数 1.2 / 1.5 / 2.0；均量天数 10 / 20 / 50；MACD（快 / 慢）8/21、12/26（信号线 9）；
   离 0 轴带宽 0.5 / 1.0 / 2.0%；出货日上限 4 / 6 / 关；上影 / 实体上限 2 / 3 / 关；周线量比（W2）关 / 1.0 / 1.3。现行 = 60 / 15 / 1.5 / 20 /
   12-26 / 1.0 / 6 / 3 / 1.0。168 组 = 现行 + 一步邻居 17 + 随机 150（种子 20260928，不重复）。
   买点用「零件」拼（tune_common.entry_mask），现行一组必须与 compute_indicators + leap_confirm.w2_keep 逐个信号相同（运行时核对：
   J2 全部年份 1,112 个、E 141 个、J 173 个；不同就停）。
二 单位：逐信号 —— 每个信号只留这一个买入信号，回测引擎单独跑（scripts/sell_confirm.one_trade），扣 ¥25 万一笔的来回手续费；卖出了的才算。
   探索（调参）样本：J2 = J-Quants 时点 TOPIX 1000 成员 2017-01〜2026-09；E = yfinance 今天的日経225 2006-10〜2016-09；
   J = J-Quants 今天的日経225 2017〜（J2 的子集，实际交易的股票池）。
三 静态调参 P*：168 组里，E / J2 / J 三个样本都满足「交易数 ≥ 现行的 40%、胜率 ≥ 现行、每笔 ≥ 现行」的组中，
   分数 = min(E 每笔差, J2 每笔差) 最高的一组；没有 → P* = 现行（到此为止，不做验证）。
四 过拟合检验（只描述也参与判定）：10 个块（E 2006-10 起每 2 年 5 块、J2 2017 起每 2 年 5 块），5 块当样本内、5 块当样本外的全部 252 种分法：
   样本内每笔最高（交易数 ≥ 现行 40%）的一组，在样本外的名次；PBO = 名次低于中位数的比例（0.5 左右 = 调参等于随便挑）。
五 walk-forward（「每年重调」这个做法本身）：E 轨道 2009〜2016 每年、J2 轨道 2019〜2026 每年，用之前（同一样本、从样本开头到上一年底）的交易
   按三的规则（只看这一个样本）挑一组，用在这一年；和现行同一年的交易比。标签「调参有用」= 两条轨道都是 胜率差 ≥ 0 且 每笔差 ≥ 0；
   另报 J（日経225）轨道（J2 挑的组用在日経225 的股票上）。
六 验证（只对 P*，且 P* ≠ 现行；数据 = 没用于调参的 Z = yfinance 今天的日経225 2001-01〜2006-09（去掉休市假行）、
   W = 扩大池 714 只 2006-10〜2016-09；C = Z + W）：
   「通过」= PBO < 0.5、C 每笔差 95% 区间下限 > 0、C 胜率差 ≥ +2.0 pp、Z 与 W 各自每笔差 ≥ 0、组合（S0C2 + P*，E 与 J）Calmar 不比现行低 0.02 以上
   且回撤不深 2 pp 以上；「方向一致」= C 每笔差 > 0 且胜率差 > 0；其余「不通过」。区间 = 按信号月聚类的自助法 2,000 次（两组交易不同 → 抽月份，
   两组各用抽到那些月的交易），种子 20260928。
   结论上限：「通过」→ 提议前向记录与另做组合研究（改模拟盘 / 执行器要用户确认、记 sim_changes）；「方向一致」→ 最多提议前向记录；
   「不通过」→ 维持现行参数。这一轮不改模拟盘 / 执行器。
七 另报（只描述）：一步邻居 17 组各自在 E / J2 / J 的胜率差 / 每笔差（参数敏感度）；P* 的一步邻居平均（是不是孤立的尖峰）；Z 的组合。
登记前看过的（只看个数与以前已知的现行数字，没看任何别的组的收益）：零件法与 compute_indicators 一致（E 208 只、J2 前 300 只，0 个不同）；
   每组信号个数 0〜2,916；要跑的交易约 8 万笔；新管线里现行一组重现已知的 E 127 笔 42.5% / +0.70%、组合 Calmar 0.285。
事前预期（写死）：以前两轮调参都没过验证、阈值只有中等持续性 → PBO 多半 0.4〜0.6；P* 在没看过的数据上「通过」的机会不到两成。
输出：var/out/tune_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune_common as TC                                                    # noqa: E402
from qbreak import paths                                                    # noqa: E402

NOTIONAL = 250_000
END_BARS = 90
WIN = {"E": ("2006-10-01", "2016-09-30"), "J2": ("2017-01-04", None), "J": ("2017-01-04", None),
       "Z": ("2001-01-04", "2006-09-30"), "W": ("2006-10-01", "2016-09-30")}
BASE_ALL = {"J2": 1112, "E": 141, "J": 173}                                  # 现行一组全部年份的信号数（以前各研究的口径）
BLOCKS = ([("E", f"{2006 + 2 * i}-10-01", f"{2008 + 2 * i}-09-30") for i in range(5)]
          + [("J2", f"{2017 + 2 * i}-01-01", f"{2018 + 2 * i}-12-31") for i in range(5)])
WF = {"E": list(range(2009, 2017)), "J2": list(range(2019, 2027))}
WF_START = {"E": "2006-10-01", "J2": "2017-01-04"}
LINES: list[str] = []
G: dict = {}                                                                # 分进程共用（fork）


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


# ───────────────────────── 一只票：零件 → 各组信号 → 交易 ─────────────────────────
def _ticker(j: int) -> dict:
    from qbreak import mtf
    import sell_confirm as SCF
    P, days, names = G["P"], G["days"], G["names"]
    ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
    if ok.sum() < 80:
        return {}
    t = names[j]
    df = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                       "Volume": P["V"][ok, j]}, index=days[ok])
    w5v = mtf.daily_frame(df, days)["W5v"].reindex(df.index).to_numpy(float)
    Pt = TC.parts(df, G["p0"], w5v)
    out = {"t": t, "sig": {}, "trades": {}}
    a, b = G["win"]
    win = (df.index >= pd.Timestamp(a)) & ((df.index <= pd.Timestamp(b)) if b else True)
    masks = {"main": G["mem"][ok, j] if G["mem"] is not None else np.ones(len(df), bool)}
    if G.get("also_all") and t in G["also_all"]:
        masks["all"] = np.ones(len(df), bool)
    need = set()
    for i, s in enumerate(G["sets"]):
        e = TC.entry_mask(Pt, s, G["p0"])
        for mk, mm in masks.items():
            em = e & mm
            out["sig"][(i, mk)] = (int(em.sum()), [d for d in df.index[em & win]])
            need |= {(TC.variant(s), d) for d in df.index[em & win]}
    for v, d in need:
        fr = Pt["frames"][v]
        pos = int(fr.index.get_loc(d))
        pv = TC.params_for(G["p0"], {**TC.CURRENT, "macd": (v[0], v[1]), "vol_ma_n": v[2]})
        r = SCF.one_trade(t, fr.assign(entry=np.asarray(fr.index == d)), d, pv, G["bt"], fr.index[min(len(fr) - 1, pos + END_BARS)])
        if r is not None and r["reason"] != "end":
            out["trades"][(v, d)] = float(r["ret_pct"]) - G["rt"]
    return out


def run_context(tag: str, ctx: dict, cols: list[int], mem, sets: list[dict], p0, bt, rt, also_all=None, procs: int = 4) -> dict:
    """→ {"all": {(组, mask): 全部年份信号数}, "T": {(组, mask): 交易表}}。"""
    G.update({"P": ctx["P"], "days": pd.DatetimeIndex(ctx["days"]), "names": ctx["names"], "mem": mem, "sets": sets, "p0": p0, "bt": bt,
              "rt": rt, "win": WIN[tag], "also_all": also_all})
    t0 = time.time()
    with mp.get_context("fork").Pool(procs) as pool:
        res = [r for r in pool.imap_unordered(_ticker, cols, chunksize=4) if r]
    cnt: dict = {}
    rows: dict = {}
    for r in res:
        for (i, mk), (n_all, dates) in r["sig"].items():
            cnt[(i, mk)] = cnt.get((i, mk), 0) + n_all
            v = TC.variant(sets[i])
            for d in dates:
                net = r["trades"].get((v, d))
                if net is not None:
                    rows.setdefault((i, mk), []).append((r["t"], d, net))
    T = {}
    for key in set(cnt) | set(rows):
        x = pd.DataFrame(rows.get(key, []), columns=["ticker", "entry_date", "net"])
        x["month"] = pd.to_datetime(x["entry_date"]).dt.strftime("%Y-%m") if len(x) else []
        x["year"] = pd.to_datetime(x["entry_date"]).dt.year if len(x) else []
        T[key] = x
    say(f"- {tag}：{len(res)} 只；{len(sets)} 组；要跑的交易 {sum(len(r['trades']) for r in res):,} 笔；{round(time.time() - t0)} s")
    return {"all": cnt, "T": T}


# ───────────────────────── 组合（S0C2）─────────────────────────
def portfolio(ctx: dict, s: dict, p, p0) -> dict:
    """这一组参数的买点（全部年份，W2 按研究口径）+ 那一组的卖法列 → S0C2 组合（leap_confirm 同一框架）。"""
    import leap_confirm as LF
    import sell_explore as SX
    from qbreak import mtf
    P, days, names = ctx["P"], pd.DatetimeIndex(ctx["days"]), ctx["names"]
    fr = {}
    for j in ctx["cols"]:
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        if ok.sum() < 80:
            continue
        df = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                           "Volume": P["V"][ok, j]}, index=days[ok])
        w5v = mtf.daily_frame(df, days)["W5v"].reindex(df.index).to_numpy(float)
        Pt = TC.parts(df, p0, w5v)
        f = Pt["frames"][TC.variant(s)]
        fr[names[j]] = f.assign(entry=TC.entry_mask(Pt, s, p0))
    run_fn = LF.runner(ctx, fr)
    era = ctx.get("era", "J")
    return SX.summ(LF.run(ctx, run_fn, fr, TC.params_for(p, s)), era)


def per_sample(R: dict, i: int, mk: str = "main") -> dict:
    t = R["T"].get((i, mk))
    return TC.stats(t["net"].to_numpy(float)) if t is not None and len(t) else {"n": 0, "win": np.nan, "mean": np.nan}


def main() -> int:
    import leap_confirm as LF
    import sell_confirm as SCF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    sets = TC.sample_sets()
    ids = [TC.set_id(s) for s in sets]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 选股参数的联合调参 → 验证（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/tune_study.py 开头（运行前写定）；共用部分 scripts/tune_common.py；逐信号 = 每个信号单独跑现行卖法、扣手续费。")
    say("\n## 〇、样本与核对")
    cJ2 = LF.context("J", jmem="U2")
    u0 = set(LF.context("J")["names"][j] for j in LF.context("J")["cols"])
    RJ = run_context("J2", cJ2, cJ2["cols"], cJ2["D"]["mem"]["U2"], sets, p0, bt, rt, also_all=u0)
    cE = LF.context("E")
    RE = run_context("E", cE, cE["cols"], None, sets, p0, bt, rt)
    S = {"J2": {i: per_sample(RJ, i) for i in range(len(sets))}, "E": {i: per_sample(RE, i) for i in range(len(sets))},
         "J": {i: per_sample(RJ, i, "all") for i in range(len(sets))}}
    got = {"J2": RJ["all"].get((0, "main")), "E": RE["all"].get((0, "main")), "J": RJ["all"].get((0, "all"))}
    say(f"- 核对：现行一组全部年份的信号 J2 {got['J2']} / E {got['E']} / J {got['J']}（应为 {BASE_ALL['J2']} / {BASE_ALL['E']} / {BASE_ALL['J']}）")
    if got != BASE_ALL:
        raise SystemExit("现行一组与以前的口径不同，停止（按登记）")
    for tg in ("J2", "E", "J"):
        x = S[tg][0]
        say(f"- 现行 {tg}：{x['n']} 笔，胜率 {fmt(x['win'], '{:.1f}')}%，每笔 {fmt(x['mean'])}%")

    # 三 静态调参
    st = {ids[i]: {tg: S[tg][i] for tg in S} for i in range(len(sets))}
    star = TC.choose(st, ids[0], ("E", "J2", "J"))
    i_star = ids.index(star)
    elig = [i for i in range(1, len(sets)) if all(S[tg][i]["n"] >= TC.ELIG_N * S[tg][0]["n"] for tg in S)]
    better = [i for i in elig if all(S[tg][i]["win"] >= S[tg][0]["win"] and S[tg][i]["mean"] >= S[tg][0]["mean"] for tg in S)]
    say("\n## 一、静态调参（168 组里挑 P*）")
    say(f"- 交易数够（三个样本都 ≥ 现行 40%）的 {len(elig)} 组；其中三个样本胜率与每笔都不比现行差的 {len(better)} 组")
    say(f"- P* = **{TC.label(sets[i_star])}**" + ("（没有更好的一组 → 维持现行，不做验证）" if i_star == 0 else ""))
    say("\n| 组 | E 笔数 / 胜率 / 每笔 | J2 笔数 / 胜率 / 每笔 | J 笔数 / 胜率 / 每笔 |")
    say("|---|---|---|---|")
    top = sorted(better, key=lambda i: -min(S["E"][i]["mean"] - S["E"][0]["mean"], S["J2"][i]["mean"] - S["J2"][0]["mean"]))[:8]
    for i in [0] + top:
        say(f"| {'**' if i == i_star else ''}{TC.label(sets[i])}{'**' if i == i_star else ''} | " + " | ".join(
            f"{S[tg][i]['n']} / {fmt(S[tg][i]['win'], '{:.1f}')}% / {fmt(S[tg][i]['mean'])}%" for tg in ("E", "J2", "J")) + " |")

    # 四 PBO
    Tall = {i: pd.concat([RE["T"].get((i, "main"), pd.DataFrame(columns=["entry_date", "net"])).assign(sample="E"),
                          RJ["T"].get((i, "main"), pd.DataFrame(columns=["entry_date", "net"])).assign(sample="J2")], ignore_index=True)
            for i in range(len(sets))}
    Sb, Nb, _ = TC.block_table(Tall, BLOCKS)
    pb = TC.pbo(Sb, Nb, base=0)
    say(f"\n## 二、过拟合检验（CSCV）：PBO = **{fmt(pb['pbo'], '{:.2f}')}**（{pb['splits']} 种分法；样本内最好的一组在样本外的名次中位 {fmt(pb['median_rank'], '{:.2f}')}；"
        f"0.5 左右 = 调参等于随便挑）")

    # 五 walk-forward
    say("\n## 三、每年重调（walk-forward，样本外）")
    wf = {}
    for tg, R, mk in (("E", RE, "main"), ("J2", RJ, "main")):
        chosen_rows, base_rows, jrows, jbase = [], [], [], []
        for y in WF[tg]:
            trn = {}
            for i in range(len(sets)):
                t = R["T"].get((i, mk))
                x = t[(pd.to_datetime(t["entry_date"]) >= pd.Timestamp(WF_START[tg])) & (t["year"] < y)] if t is not None and len(t) else None
                trn[ids[i]] = {tg: TC.stats(x["net"].to_numpy(float)) if x is not None else {"n": 0, "win": np.nan, "mean": np.nan}}
            k = ids.index(TC.choose(trn, ids[0], (tg,)))
            for i_, acc in ((k, chosen_rows), (0, base_rows)):
                t = R["T"].get((i_, mk))
                if t is not None and len(t):
                    acc.append(t[t["year"] == y])
            if tg == "J2":
                for i_, acc in ((k, jrows), (0, jbase)):
                    t = RJ["T"].get((i_, "all"))
                    if t is not None and len(t):
                        acc.append(t[t["year"] == y])
            wf.setdefault(tg + "_picks", []).append((y, TC.label(sets[k])))
        for name, a, b in ((tg, chosen_rows, base_rows), *((("J", jrows, jbase),) if tg == "J2" else ())):
            A = pd.concat(a, ignore_index=True) if a else pd.DataFrame(columns=["net"])
            Bq = pd.concat(b, ignore_index=True) if b else pd.DataFrame(columns=["net"])
            sa, sb = TC.stats(A["net"].to_numpy(float)), TC.stats(Bq["net"].to_numpy(float))
            wf[name] = {"wf": sa, "cur": sb, "dwin": sa["win"] - sb["win"], "dmean": sa["mean"] - sb["mean"]}
            say(f"- {name} 轨道（{WF[tg][0]}〜{WF[tg][-1]}）：重调 {sa['n']} 笔 {fmt(sa['win'], '{:.1f}')}% / {fmt(sa['mean'])}% vs 现行 {sb['n']} 笔 "
                f"{fmt(sb['win'], '{:.1f}')}% / {fmt(sb['mean'])}%（胜率差 {fmt(wf[name]['dwin'], '{:+.1f}')} pp、每笔差 {fmt(wf[name]['dmean'])} pp）")
    useful = all(wf[t]["dwin"] >= 0 and wf[t]["dmean"] >= 0 for t in ("E", "J2"))
    say(f"- 每年选中的：E {'；'.join(f'{y} {lab}' for y, lab in wf['E_picks'])}")
    say(f"- 每年选中的：J2 {'；'.join(f'{y} {lab}' for y, lab in wf['J2_picks'])}")
    say(f"- 标签「调参有用」（两条轨道胜率差与每笔差都 ≥ 0）：**{'是' if useful else '否'}**")

    # 七 敏感度
    say("\n## 四、另报：一步邻居（只改一个参数）的敏感度（胜率差 pp / 每笔差 pp）")
    say("| 改动 | E | J2 | J |")
    say("|---|---|---|---|")
    for i in range(1, 18):
        say(f"| {TC.label(sets[i])} | " + " | ".join(
            f"{S[tg][i]['n']} 笔 {fmt(S[tg][i]['win'] - S[tg][0]['win'], '{:+.1f}')} / {fmt(S[tg][i]['mean'] - S[tg][0]['mean'])}" for tg in ("E", "J2", "J")) + " |")

    conf: dict = {"verdict": "不做（P* = 现行）"}
    if i_star != 0:
        s_star = sets[i_star]
        nb = [i for i in range(1, len(sets)) if sum(sets[i][k] != s_star[k] for k in TC.GRID) == 1]
        if nb:
            say(f"- P* 的一步邻居（在 168 组里的 {len(nb)} 组）平均每笔差：E {fmt(np.nanmean([S['E'][i]['mean'] - S['E'][0]['mean'] for i in nb]))} pp、"
                f"J2 {fmt(np.nanmean([S['J2'][i]['mean'] - S['J2'][0]['mean'] for i in nb]))} pp")
        say("\n## 五、验证（没用于调参的数据：Z = 2001〜2006 日経225；W = 另一批股票 714 只 2006〜2016；C = 两者合起来）")
        two = [sets[0], s_star]
        cZ = LF.context("Z")
        RZ = run_context("Z", cZ, cZ["cols"], None, two, p0, bt, rt)
        import sell_confirm as SCF2
        cWctx, _ = SCF2.wide_context(p0)
        cW = {**cWctx, "cols": list(range(len(cWctx["names"])))}
        RW = run_context("W", cW, cW["cols"], None, two, p0, bt, rt)
        tz = {i: RZ["T"].get((i, "main"), pd.DataFrame(columns=["net", "month"])) for i in (0, 1)}
        tw = {i: RW["T"].get((i, "main"), pd.DataFrame(columns=["net", "month"])) for i in (0, 1)}
        tc = {i: pd.concat([tz[i], tw[i]], ignore_index=True) for i in (0, 1)}
        d = {}
        for nm, tt in (("Z", tz), ("W", tw), ("C", tc)):
            a, b = TC.stats(tt[1]["net"].to_numpy(float)), TC.stats(tt[0]["net"].to_numpy(float))
            d[nm] = {"star": a, "cur": b, "dwin": a["win"] - b["win"], "dmean": a["mean"] - b["mean"]}
        d["C"].update(TC.boot_unpaired(tc[1], tc[0]))
        pe = {"cur": portfolio({**cE, "era": "E"}, sets[0], p, p0), "star": portfolio({**cE, "era": "E"}, s_star, p, p0)}
        cJ = LF.context("J")
        pj = {"cur": portfolio({**cJ, "era": "J"}, sets[0], p, p0), "star": portfolio({**cJ, "era": "J"}, s_star, p, p0)}
        port_ok = all(x["star"]["calmar"] is not None and x["cur"]["calmar"] is not None and x["star"]["calmar"] >= x["cur"]["calmar"] - TC.CAL_TOL
                      and x["star"]["dd"] >= x["cur"]["dd"] - TC.DD_TOL for x in (pe, pj))
        v = TC.verdict(pb["pbo"], d["C"], d["Z"], d["W"], port_ok)
        for nm in ("Z", "W", "C"):
            x = d[nm]
            say(f"- {nm}：P* {x['star']['n']} 笔 {fmt(x['star']['win'], '{:.1f}')}% / {fmt(x['star']['mean'])}% vs 现行 {x['cur']['n']} 笔 "
                f"{fmt(x['cur']['win'], '{:.1f}')}% / {fmt(x['cur']['mean'])}%（胜率差 {fmt(x['dwin'], '{:+.1f}')} pp、每笔差 {fmt(x['dmean'])} pp"
                + (f"；95% 区间 胜率 {fmt(x['dwin_lo'], '{:+.1f}')}〜{fmt(x['dwin_hi'], '{:+.1f}')}、每笔 {fmt(x['dmean_lo'])}〜{fmt(x['dmean_hi'])}" if nm == "C" else "") + "）")
        say(f"- 组合（S0C2）Calmar：E {fmt(pe['cur']['calmar'], '{:.3f}')} → {fmt(pe['star']['calmar'], '{:.3f}')}（回撤 {fmt(pe['cur']['dd'], '{:.2f}')}% → "
            f"{fmt(pe['star']['dd'], '{:.2f}')}%）；J {fmt(pj['cur']['calmar'], '{:.3f}')} → {fmt(pj['star']['calmar'], '{:.3f}')}（{fmt(pj['cur']['dd'], '{:.2f}')}% → "
            f"{fmt(pj['star']['dd'], '{:.2f}')}%）")
        say(f"- **判定：{v}**（PBO {fmt(pb['pbo'], '{:.2f}')}；组合守门 {'过' if port_ok else '没过'}）")
        pz = {"cur": portfolio({**cZ, "era": "Z"}, sets[0], p, p0), "star": portfolio({**cZ, "era": "Z"}, s_star, p, p0)}
        say(f"- 另报：Z 组合 Calmar {fmt(pz['cur']['calmar'], '{:.3f}')} → {fmt(pz['star']['calmar'], '{:.3f}')}")
        conf = {"verdict": v, "d": d, "port": {"E": pe, "J": pj, "Z": pz}, "port_ok": port_ok}
    say(f"\n用时 {round(time.time() - t0)} s。非投资建议。")

    out = paths.out_dir()
    (out / "tune_study.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    import buyq_study as BS
    payload = {"code": code, "sets": [{"id": ids[i], "label": TC.label(sets[i]), **{tg: S[tg][i] for tg in S}} for i in range(len(sets))],
               "star": TC.label(sets[i_star]), "pbo": pb, "wf": wf, "useful": useful, "confirm": conf}
    (out / "tune_study.json").write_text(json.dumps(BS._clean(payload), ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
