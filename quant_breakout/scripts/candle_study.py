"""candle_study.py — K 线图形研究的登记检验：缩量押し目（上升趋势中的缩量急跌）买入（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

用户：「按照这个类似图形的特点，从过去十年的数据里面分析出第二天以后会涨一段时间的图形还有快到顶该卖了的转换点图形，分析后再进行测试
看选择的股票胜率 在一定区间的总收益如何，持续研究 6 个小时左右如何能让策略达到登记门槛…考虑没有考虑过的方法」。

一、怎么来的（探索只用 2017-01〜2021-12；scripts/candle_explore.py，记录 var/out/candle_explore_1〜12.md，全部只有探索期的统计）
  试过（岔路都写出来）：① 30 个经典 K 线形态（酒田五法 + 西方）× 8 个情境 = 267 个组合 → 0 个通过（打乱对照也是 0），传统方向大多相反
  （短期反转）；② 15 个连续 K 线特征分十档 → 反转有但每 5 日只有 0.1〜0.3%（< 来回成本 0.35%）；③ 押し目网格 167 个组合 →
  「跌得越深、量越缩 → 之后越涨」单调；④ 押し目逐笔 4 种定义 × 5 种卖法；⑤ 现行突破持仓 + 13 个见顶 K 线离场（胜率 +2〜6 pp、
  每笔只好 0.1〜0.2 pp；组合更差）；⑥ 相似 K 线检索（kNN）与 K 线提升树 → T2 的 IC ≈ 0（失败）；⑦ 押し目参数附近 / 每年 / 扎堆、指値买；
  ⑧〜⑩ 放进 S0C2 组合（大盘股里押し目太少 → 时点 TOPIX 1000）；⑪ 二番底 / 逆三尊 / 三尊天井 / 二重天井 → 都没用；⑫ 搭配与指値。
  用户图中的上影陽線另外登记检验过（78c7b3d：「第二天大概率涨」不成立）。
二、押し目（qbreak/candles.pullback，定义固定）：那天收盘时 ① 最近 5 个交易日跌 ≥ 10%；② 最近 5 天均量 ≤ 之前 20 天均量 × 0.85；
  ③ 收盘在 150 日线上、150 日线比 20 天前高；④ 当天最低没跌破前 20 天最低。只在时点 TOPIX 1000（U2）成员的日子。
三、候选（S0C2 = var/sim.json 同一套设定、一手放宽关；1655 牛熊择时、宏观 / 板块 / 量化状态层、回撤 HALT、一手按当时真实股价；
  押し目仓位：满 10 个交易日在下一交易日开盘卖，7% 止损 / 25% 止盈 / 12% 跟踪止损照现行，不看日线死叉）
  C1 只做押し目（TOPIX 1000），押し目不受新仓倍数限制，第二天开盘买
  C2 只做押し目（TOPIX 1000），受新仓倍数限制（宏观 / 板块 / 量化状态层照现行）
  C3 只做押し目，不受限制，第二天指値买 = 信号日收盘 − 0.3 × ATR(14)（最低价碰到才成交，成交价 = min(开盘, 指値)；碰不到这笔不买）
  C4 只做押し目，不受限制，开盘买，收盘回到 5 日线上就在下一交易日开盘卖（最多 10 日）
  C5 现行突破（TOPIX 500 成员）+ 押し目（TOPIX 1000，押し目不受限制、开盘买、10 日）
  「现行」= 现行突破信号、时点 TOPIX 500（U1）成员（与 ml_study / mtf_study 同一口径）
四、判定（V / H 与以前相同；R、E 这次写成下面这样）
  V 验证期 2022-01〜2023-09：Calmar > 现行，且最大回撤不比现行深 2 pp 以上
  H 留出期 2023-10〜 与两个半段（2025-04 分）各自：Calmar ≥ 现行 + 0.05，且最大回撤不比现行深
  R 全窗口 2017-01〜：Calmar ≥「只有 1655（个股不买）」与「现行（今天的日経225）」两者中较高的（比「什么都不做只拿 1655」好）
  E 没用过的年代 2006-10〜2016-09（yfinance 今天的日経225 213 只）：同一个押し目规则、同一种买法与卖法的逐笔（每只票单独、扣成本）
    每笔平均净收益 > 0 且盈亏比 > 1（C1 / C2 / C5 = 开盘买持有 10 日；C3 = 指値（近似：只换买入价，卖出日与卖出价不变）；C4 = 回到 5 日线）
  都满足 → 通过；多个通过 → 提议验证期 Calmar 最高的（一样取编号小的）。通过也只是提议：模拟盘改不改要用户在对话里确认；
  改的话还要先做实盘准备（TOPIX 1000 的行情、指値下单），另记 sim_changes。都不通过 → 维持现行。
五、另报（只描述）：各方案 验证期 / 留出期 的区间总收益、个股胜率与平均持有；每年的收益；押し目逐笔 验证期 / 留出期 / 2006〜2016。
六、局限：押し目 2017〜2021 只有约 150〜230 次（TOPIX 1000），组合里 5 年约 60〜100 笔；2006〜2016 只有日経225 185 次，集中在 2013 年与
  2009 年；探索期（2017〜2021）也在全窗口里（R 部分偏乐观）；指値在逐笔 E 里是近似；税前；实盘要 TOPIX 1000 的行情与指値下单
  （现在的执行器只下日経225 的寄付）。
登记前做过的检查：tests/test_candles.py（押し目定义、不偷看）、tests/test_candle_study.py（候选的构造、门槛）、
  探索期里同一套代码跑过 C1〜C5 的前身（candle_explore_9 / 10 / 12）。
输出：var/out/candle_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candle_data as CD                                                     # noqa: E402
import candle_portfolio as CP                                                # noqa: E402
import ml_study as MS                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import candles as K                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

TRADE_START = PRS.TRADE_START
VAL, HOLD, H1, H2 = ("2022-01-01", "2023-10-01"), ("2023-10-01", None), ("2023-10-01", "2025-04-01"), ("2025-04-01", None)
WINDOWS = {"all": (TRADE_START, None), "va": VAL, "ho": HOLD, "h1": H1, "h2": H2}
E0 = ("2006-10-01", "2016-10-01")
HOLD_PB, LIMIT_K = 10, 0.3
CANDS = {"C1": "只做押し目（TOPIX 1000，不受新仓倍数限制，开盘买，10 日）", "C2": "只做押し目（受新仓倍数限制，开盘买，10 日）",
         "C3": "只做押し目（不受限制，指値 收盘 − 0.3 ATR，10 日）", "C4": "只做押し目（不受限制，开盘买，回到 5 日线就卖，最多 10 日）",
         "C5": "现行突破（TOPIX 500）+ 押し目（TOPIX 1000，不受限制，10 日）"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def r_fails(r: dict, core: dict, cur0: dict) -> list[str]:
    need = max(MS._c(core["all"]["calmar"]), MS._c(cur0["all"]["calmar"]))
    return [] if MS._c(r["all"]["calmar"]) >= need else [f"全窗口 Calmar {r['all']['calmar']} < 只有 1655 {core['all']['calmar']} / 现行（日経225）{cur0['all']['calmar']}"]


def e_fails(s: dict) -> list[str]:
    if not s.get("n"):
        return ["2006〜2016 没有交易"]
    f = []
    if not s["mean"] > 0:
        f.append(f"2006〜2016 每笔平均 {s['mean']:+.2f}% ≤ 0")
    if not (np.isfinite(s["pf"]) and s["pf"] > 1):
        f.append(f"2006〜2016 盈亏比 {s['pf']:.2f} ≤ 1")
    return f


def tstat(T: pd.DataFrame, a=None, b=None) -> dict:
    x = T
    if len(x) and a is not None:
        x = x[(x["sig_date"] >= pd.Timestamp(a)) & ((x["sig_date"] < pd.Timestamp(b)) if b else True)]
    net = x["net"].to_numpy(float) if len(x) else np.array([])
    if not len(net):
        return {"n": 0}
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    return {"n": int(len(net)), "win": round(float((net > 0).mean() * 100), 2), "mean": round(float(net.mean()), 3),
            "pf": round(float(pos / neg), 3) if neg > 0 else float("nan"), "hold": round(float(x["hold_days"].mean()), 1)}


def limit_adjust(T: pd.DataFrame, P: dict, days: pd.DatetimeIndex, names: list[str], k: float, slip: float) -> pd.DataFrame:
    """逐笔的指値近似：第二天最低价碰到 信号日收盘 − k × ATR 才成交（成交价 = min(开盘, 指値)），卖出日与卖出价不变；没碰到的删掉。"""
    if not len(T):
        return T
    a = K.atr(P["H"], P["L"], P["C"])
    col = {t: j for j, t in enumerate(names)}
    di = {d: i for i, d in enumerate(days)}
    keep, net = [], []
    for r in T.itertuples(index=False):
        j, i = col.get(r.ticker), di.get(pd.Timestamp(r.entry_date))
        if j is None or i is None or i < 1:
            keep.append(False)
            net.append(np.nan)
            continue
        lim = P["C"][i - 1, j] - k * a[i - 1, j]
        if not (P["L"][i, j] <= lim):
            keep.append(False)
            net.append(np.nan)
            continue
        fill = min(P["O"][i, j], lim)
        keep.append(True)
        net.append((r.exit_px / (fill * (1 + slip)) - 1) * 100 - (r.ret_pct - r.net))
    out = T.copy()
    out["net"] = net
    return out[np.array(keep, bool)]


def frames_from(P: dict, days: pd.DatetimeIndex, names: list[str], cols: list[int], p0, extra: dict[str, np.ndarray]) -> dict[str, pd.DataFrame]:
    """宽表 → 每只票的 compute_indicators（现行参数；相对强度过滤是关的）+ 额外的列（日期 × 票 的布尔宽表）。"""
    from qbreak.strategy import compute_indicators
    out = {}
    for j in cols:
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        if ok.sum() < 80:
            continue
        df = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                           "Volume": P["V"][ok, j]}, index=days[ok])
        ind = compute_indicators(df, p0, None)
        for k, v in extra.items():
            ind[k] = v[ok, j]
        out[names[j]] = ind
    return out


def main() -> int:
    from qbreak.config import ExecConfig
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/candle_study.py", "scripts/candle_portfolio.py",
                                 "scripts/candle_data.py", "qbreak/candles.py"], capture_output=True, text=True).stdout.strip())
    D = CD.load()
    days, P, names = D["days"], D["P"], D["names"]
    mem0, mem1, mem2 = D["mem"]["U0"], D["mem"]["U1"], D["mem"]["U2"]
    p0 = load_params(market="JP")
    slip = ExecConfig.for_market("JP", "tachibana").slippage_pct / 100
    last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    end = pd.Timestamp(PRS.WINDOW[1])
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < end - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    pbm = K.pullback(P)
    with np.errstate(invalid="ignore"):
        ab5 = np.asarray(P["C"] > K.rolling_mean(P["C"], 5), bool)
    c2 = [j for j in range(len(names)) if mem2[:, j].any()]
    fr = frames_from(P, days, names, c2, p0, {"pb": pbm & mem2, "in1": mem1, "ab5": ab5})
    ratio = {t: pd.Series(D["ratio"][:, names.index(t)], index=days) for t in fr}
    closes = pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days)
    run = CP.make_runner(closes, ratio, WINDOWS)
    brk = {t: df["entry"].to_numpy(bool) & df["in1"].to_numpy(bool) for t, df in fr.items()}
    pbf = {t: df["pb"].to_numpy(bool) for t, df in fr.items()}
    only = {t: df.assign(entry=pbf[t], dead_cross=False) for t, df in fr.items()}
    only5 = {t: df.assign(entry=pbf[t], dead_cross=df["ab5"].to_numpy(bool)) for t, df in fr.items()}
    pb_all = {t: set(df.index[pbf[t]]) for t, df in fr.items()}
    pb_mix = {t: set(df.index[pbf[t] & ~brk[t]]) for t, df in fr.items()}
    R = {}
    R["现行"] = run({t: df.assign(entry=brk[t]) for t, df in fr.items()}, p0)
    R["只有 1655"] = run({t: df.assign(entry=False) for t, df in fr.items()}, p0)
    R["C1"] = run(only, p0, pb=pb_all, hold_pb=HOLD_PB, pb_free=True)
    R["C2"] = run(only, p0, pb=pb_all, hold_pb=HOLD_PB, pb_free=False)
    R["C3"] = run(only, p0, pb=pb_all, hold_pb=HOLD_PB, pb_free=True, limit_k=LIMIT_K)
    R["C4"] = run(only5, p0, pb=pb_all, hold_pb=HOLD_PB, pb_free=True, pb_use_dead=True)
    R["C5"] = run({t: df.assign(entry=brk[t] | pbf[t]) for t, df in fr.items()}, p0, pb=pb_mix, hold_pb=HOLD_PB, pb_free=True)
    c0 = [j for j in range(len(names)) if mem0[:, j].any()]
    f0 = frames_from(P, days, names, c0, p0, {})
    run0 = CP.make_runner(pd.DataFrame({t: f0[t]["Close"] for t in f0}).reindex(days),
                          {t: pd.Series(D["ratio"][:, names.index(t)], index=days) for t in f0}, WINDOWS)
    R["现行（今天的日経225）"] = run0(f0, p0)
    # ── 逐笔：押し目（U2，J-Quants）与 2006〜2016（yfinance 日経225） ──
    p10 = replace(p0, max_hold_days=HOLD_PB)
    ind_open = {t: df.assign(entry=pbf[t], dead_cross=False) for t, df in fr.items()}
    ind_sma5 = {t: df.assign(entry=pbf[t], dead_cross=df["ab5"].to_numpy(bool)) for t, df in fr.items()}
    TJ = {"open": PRS.indep_trades(ind_open, p10, PRS.PitEngine.DELIST), "sma5": PRS.indep_trades(ind_sma5, p10, PRS.PitEngine.DELIST)}
    TJ["limit"] = limit_adjust(TJ["open"], P, days, names, LIMIT_K, slip)
    E, ed, en = D["E"], D["edays"], D["enames"]
    epb = K.pullback(E) & CD.period_mask(ed, "E0")[:, None]
    with np.errstate(invalid="ignore"):
        eab5 = np.asarray(E["C"] > K.rolling_mean(E["C"], 5), bool)
    fe = frames_from(E, ed, en, list(range(len(en))), p0, {"pb": epb, "ab5": eab5})
    TE = {"open": PRS.indep_trades({t: df.assign(entry=df["pb"].to_numpy(bool), dead_cross=False) for t, df in fe.items()}, p10, {}),
          "sma5": PRS.indep_trades({t: df.assign(entry=df["pb"].to_numpy(bool), dead_cross=df["ab5"].to_numpy(bool)) for t, df in fe.items()},
                                   p10, {})}
    TE["limit"] = limit_adjust(TE["open"], E, ed, en, LIMIT_K, slip)
    e_of = {"C1": "open", "C2": "open", "C3": "limit", "C4": "sma5", "C5": "open"}
    ES = {k: tstat(v, *E0) for k, v in TE.items()}
    # ── 判定 ──
    base, core, cur0 = R["现行"], R["只有 1655"], R["现行（今天的日経225）"]
    fails, passed = {}, {}
    for c in CANDS:
        vf = MS.v_fails(R[c], base)
        hf = MS.h_fails(R[c], base) if not vf else None
        rf = r_fails(R[c], core, cur0) if (not vf and not hf) else None
        ef = e_fails(ES[e_of[c]]) if (not vf and not hf and not rf) else None
        fails[c] = {"V": vf, "H": hf, "R": rf, "E": ef}
        if not vf and not hf and not rf and not ef:
            passed[c] = R[c]
    best = MS.choose(passed) if passed else None
    # ── 输出 ──
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("# K 线图形研究：缩量押し目买入（登记检验，2026-09-27）")
    say("规则见 scripts/candle_study.py 开头（先提交后运行）；探索记录 var/out/candle_explore_1〜12.md（只用 2017〜2021）。"
        "S0C2 = var/sim.json 同一套设定；J-Quants 行情、一手按当时真实股价；各格 = 年化 / 最大回撤 / Calmar。")
    say("\n## 组合")
    say("| 方案 | 全窗口 2017-01〜 | 验证期 2022-01〜2023-09（区间总收益） | 留出期 2023-10〜（区间总收益） | 留出前半 | 留出后半 | 个股笔数 / 胜率（验证 / 留出）/ 平均持有 | V | H | R | E |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for k in ["现行", "现行（今天的日経225）", "只有 1655"] + list(CANDS):
        r = R[k]
        g = fails.get(k)
        mark = lambda x: "—" if x is None else ("✓" if not x else "✗")                                           # noqa: E731
        lab = k if k not in CANDS else f"{k} {CANDS[k]}"
        say(f"| {lab} | {cell(r['all'])} | {cell(r['va'])}（{fa(r['va'].get('tot'), '{:+.1f}')}%） | {cell(r['ho'])}（{fa(r['ho'].get('tot'), '{:+.1f}')}%） | "
            f"{cell(r['h1'])} | {cell(r['h2'])} | {r['trades']} / {fa(r.get('win_va'), '{:.1f}%')} / {fa(r.get('win_ho'), '{:.1f}%')} / {fa(r.get('hold'), '{:.1f}')} 天 | "
            + (" | ".join(mark(g[x]) for x in ("V", "H", "R", "E")) if g else "— | — | — | —") + " |")
    for c, g in fails.items():
        msg = [m for x in ("V", "H", "R", "E") for m in (g[x] or [])]
        if msg:
            say(f"- {c}：" + "；".join(msg))
    say("\n## 每年的收益（%，只描述）")
    yrs = sorted(set().union(*[set(R[k]["years"]) for k in R]))
    say("| 方案 | " + " | ".join(yrs) + " |")
    say("|---|" + "---|" * len(yrs))
    for k in ["现行", "只有 1655"] + list(CANDS):
        say(f"| {k} | " + " | ".join(fa(R[k]["years"].get(y), "{:+.1f}") for y in yrs) + " |")
    say("\n## 押し目的逐笔（每只票单独、扣成本；格式 = 笔数 / 胜率 / 每笔平均净收益 / 盈亏比 / 平均持有）")
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])} / {fa(s['hold'], '{:.1f}')} 天"   # noqa: E731
    say("| 买法 / 卖法 | 探索期 2017〜2021 | 验证期 2022-01〜2023-09 | 留出期 2023-10〜 | 2006-10〜2016-09（日経225，yfinance） |")
    say("|---|---|---|---|---|")
    TS = {}
    for k, lab in (("open", "开盘买、10 日"), ("limit", "指値 收盘 − 0.3 ATR、10 日（近似）"), ("sma5", "开盘买、回到 5 日线就卖")):
        TS[k] = {"T": tstat(TJ[k], "2017-01-01", "2022-01-01"), "V": tstat(TJ[k], *VAL), "H": tstat(TJ[k], HOLD[0], None), "E0": ES[k]}
        say(f"| {lab} | {c4(TS[k]['T'])} | {c4(TS[k]['V'])} | {c4(TS[k]['H'])} | {c4(TS[k]['E0'])} |")
    if best:
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；实盘还要先准备 TOPIX 1000 的行情"
            + ("与指値下单" if best == "C3" else "") + "）。**" + (f"另外也通过的：{'、'.join(k for k in passed if k != best)}。" if len(passed) > 1 else ""))
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "R": R, "fails": fails, "passed": list(passed), "proposal": best, "trades": TS}
    fp = paths.out_dir() / "candle_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
