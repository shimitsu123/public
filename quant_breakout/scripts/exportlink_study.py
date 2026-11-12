"""exportlink_study.py — 出口股 × 海外股票 / 外需（日差 / 月差）→ 买点（2026-09-28 登记，登记之后才运行一次）。

用户（2026-09-28）：「研究日本的出口股票直接/间接相关的 如果相关国外的股票/需求变化的时候 利用日/月差可以影响到国内的 做个分析看看能不能对买点有帮助」。
以前做过的（var/out/research_map.md，不重复）：美国行业 ETF → 日本 30 个业种（业种平均）只有「昨晚 → 第二天日内」、约 0.1〜0.2%，第 6〜20 天几乎没有
  （leadlag_study）；外部因子当天 / 隔夜就反映（lag_study）；美国生产 / 订单、日韩出口 → 业种「股价领先实体数据」、多数方向相反（fund_study F3）；
  原材料的间接传导没有时间差（transmit_study）；拿业种领先分挑突破不通过（leadlag K2）。
这一轮新的：① 个股层面：每只票自己挑联动最强的美国行业 ETF（每年用之前 2 年挑），不是业种平均；② 分直接出口 / 间接（素材零部件）/ 内需
  量传导时间（隔夜 / 第 1 天 / 第 2〜5 天 / 第 6〜20 天）；③ 月差用 20 / 60 个美国交易日的动量、「海外先涨、自己还没跟上」、韩国出口；
  ④ 直接当突破买点的过滤，并按上一轮（buyq_study）的教训加「日経225 两个年代都同方向」。
规则（运行前写定；结果出来不改）：
一 分组（東証 33 业种，var/industry_s33.json）：直接出口 = 輸送用機器 / 電気機器 / 機械 / 精密機器；间接（素材 / 零部件）= 化学 / ゴム製品 /
   ガラス・土石製品 / 鉄鋼 / 非鉄金属 / 金属製品 / 繊維製品；其余 = 内需（对照）。
二 海外联动（scripts/exportlink_common.py）：7 个出口相关的美国行业 ETF（SMH 半导体、XLK 科技、XLI 工业、XLB 原材料、XLY 可选消费（含汽车）、
   XME 金属矿业、SLX 钢铁）相对 SPY 的日对数收益（yfinance 缓存，截至 2026-09-25；运行时不重新下载）。
   「隔夜海外」= 美国日期 ∈ [D, Dn) 之和（D 收盘后、Dn 开盘前收盘的美国交易日；执行器 Dn 07:40 运行时已知）。每只票每年年初用之前 2 年
   （≥ 200 天）的「D 收盘 → Dn 收盘」相对收益，挑相关最高的 ETF（相关 > 0 就用；都 ≤ 0 → 特征缺值）。
   月差特征：联动 ETF 最近 20 / 60 个美国交易日（到 Dn 开盘前）的相对收益之和；追赶 = 20 日 ETF − 这只票近 20 个交易日的相对涨幅（到 D 收盘）。
   外需数据：韩国出口（FRED XTEXVA01KRM667S）3 个月对数变化；m 月的数据从 m + 3 月 1 日起才用。
   日本个股相对收益 = 对数收益 − 同一份行情宽表全部股票的等权平均（E / Z：日経225；W：扩大池；J2 / J：J-Quants 1,378 只）。
三 Part A（只描述，不判定交易；标签的条件写死）：个股相对收益对「隔夜海外（按训练期标准差标准化）」的面板回归，四段 =
   隔夜（D 收盘 → Dn 开盘）/ 第 1 天日内 / 第 2〜5 天 / 第 6〜20 天；月差 = Dn 开盘 → D+20 收盘 对 20 / 60 日动量（标准化）、追赶、韩国出口
   （后两个按样本标准差标准化）。每组（直接 / 间接 / 内需）× 两个年代（E = yfinance 今天的日経225 2006-10〜2016-09；J2 = J-Quants
   时点 TOPIX 1000 成员 2017〜2026-09）。两边 1% / 99% 截尾；t = 每天得分和的 Newey–West（滞后 = 窗口长度 + 5）。
   标签：「第 1 天还在走」= 直接或间接组 第 1 天日内斜率与隔夜同号、两个年代 t ≥ 2；「拖到第 2〜5 天」= 第 2〜5 天同样；
   「月差存在」= 20 或 60 日动量 → 之后 20 日，两个年代同号且 |t| ≥ 2；
   「间接比直接慢」= 两个年代都是 间接组（第 1 天日内 + 第 2〜5 天）占四段合计的比例 > 直接组。
四 Part B 买点（逐信号：每个 W2 保留的突破只留这一个买入信号、现行卖法单独跑、扣 ¥25 万一笔的来回手续费；scripts/buyq_study 同一做法）：
   变体 EX1〜EX7（scripts/exportlink_common.VARIANTS）只过滤范围内（直接 / 间接）的突破，范围外与缺值 → 保留；统计只在「范围内且特征有值」
   （过滤真正作用得到的）信号里比：「差」= 保留的 − 这些信号全部（= 现行）。
   探索：J2（主样本）、E（方向）、J（J-Quants 今天的日経225 2017〜，方向）、组合（S0C2 + W2 + 过滤，E / J，scripts/leap_confirm 同一框架）。
   入选（全部满足）：a J2 与 E 的保留比例（范围内）30〜90%；b J2 胜率差 ≥ +2.0 pp 且每笔差 ≥ +0.20 pp；c J2 每笔差 > 随机对照 95 分位
   （范围内按「股票 × 周」随机保留同样比例，200 次，种子 20260928）；d E 与 J 都是胜率差 ≥ 0 且每笔差 ≥ 0；
   e 组合 E、J 的 Calmar 不比现行低 0.02 以上、最大回撤不比现行深 2 pp 以上。
   排序：J2 每笔差从大到小；最多 3 个，同一族最多 2 个。没有入选 → 这一轮到此为止，Z 与 W 不用（留着）。
五 确认（入选的每个；Z = yfinance 今天的日経225 2001-01〜2006-09；W = 扩大池 714 只 2006-10〜2016-09；C = Z + W，只在范围内）：
   「确认」= C 每笔差 95% 区间下限 > 0、C 胜率差 ≥ +1.0 pp、Z 与 W 每笔差都 ≥ 0（区间 = 按信号月聚类的自助法 2,000 次，种子 20260928）；
   「方向一致」= 没到「确认」但 C 每笔差 > 0 且胜率差 > 0；其余「不通过」。
   结论上限：「确认」→ 提议前向记录或改模拟盘（都要你在对话里确认、记进 sim_changes）；「方向一致」→ 最多提议前向记录；「不通过」→ 维持现行。
   这一轮不改模拟盘 / 执行器。
登记前看过的（只看特征，没看任何之后的收益）：真实数据冒烟测试的用时与覆盖；E 的出口股每年「最佳联动相关」中位约 0.11〜0.14，
   23 个 ETF 里挑时会挑到 GDX / PBJ 这类与出口无关的（多重比较的噪声）→ 候选缩到上面 7 个出口相关的；统计范围改成「特征有值」；
   7 个里再要求相关 ≥ 0.10 时 E 的出口股信号只有 8 / 40 个有联动 → 改成「相关 > 0 的最高那个」（出口股按业种事先认定是外需相关，
   数据只负责挑是哪个海外行业；这样 E 40 / 40、J2 每年约 1,100〜1,250 只有联动；J2 的 2017 年没有之前 2 年的数据 → 没有联动、只会被保留）。
六 事前预期（写死）：以前业种层面「美国行业昨晚 → 日本第二天日内」成立、但只有 1 天、每次约 0.1〜0.2%；外需数据「股价领先实体数据」
   → 最可能 = Part A「第 1 天还在走」成立、「拖到第 2〜5 天」与「月差存在」不成立；Part B 入选 0〜1 个、确认的机会不到两成。
输出：var/out/exportlink_study.md / .json（只有统计，没有个股行情）。
"""
from __future__ import annotations

import json
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
import buyq_common as BQ                                                    # noqa: E402
import buyq_study as BS                                                     # noqa: E402
import exportlink_common as EL                                              # noqa: E402
from qbreak import paths                                                    # noqa: E402

NOTIONAL = 250_000
W_WIN = ("2006-10-01", "2016-09-30")
HIST = {"E": ("2003-01-01", "2016-12-30"), "W": ("2003-01-01", "2017-03-31")}
A_WIN = {"E": ("2006-10-01", "2016-09-30"), "J2": ("2017-01-04", None)}
SEG = {"on": ("隔夜", 1), "id1": ("第 1 天日内", 1), "r2_5": ("第 2〜5 天", 4), "r6_20": ("第 6〜20 天", 15)}
GROUPS = {"direct": "直接出口", "indirect": "间接（素材 / 零部件）", "domestic": "内需（对照）"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


# ───────────────────────── 数据 ─────────────────────────
def us_data() -> tuple[pd.DataFrame, pd.Series, dict]:
    """缓存里的美国 ETF / SPY（不重新下载，登记与运行用同一份）+ 韩国出口。"""
    from qbreak import factors
    rd = lambda n: factors._read(factors._dir() / f"{n}.csv")                                            # noqa: E731
    closes = {a: factors.despike(rd(f"yf_{a}")) for a in EL.US_ASSETS}
    spy = factors.despike(rd("yf_SPY"))
    kr = rd("fred_XTEXVA01KRM667S")
    cover = {a: [str(s.index[0].date()), str(s.index[-1].date())] for a, s in {**closes, "SPY": spy}.items()}
    cover["KR_exports"] = [str(kr.index[0].date()), str(kr.index[-1].date())]
    return EL.us_rel_returns(closes, spy), kr, cover


def feature_panel(P: dict, days, names: list[str], R: pd.DataFrame, kr: pd.Series, years: list[int]) -> dict:
    days = pd.DatetimeIndex(days)
    comps = EL.jp_components(P["O"], P["C"])
    X1 = EL.overnight_sum(R, days)
    M20, M60 = EL.momentum_sum(R, days, 20), EL.momentum_sum(R, days, 60)
    links = EL.fit_links(comps["cc1"], X1, days, list(names), years)
    LP = EL.link_panels(links, X1, M20, M60, days, list(names))
    return {"days": days, "names": list(names), "col": {t: j for j, t in enumerate(names)}, "comps": comps, "links": links,
            "LP": LP, "kr3": EL.kr3_on(days, kr)}


def attach(S: pd.DataFrame, F: dict, s33: dict) -> pd.DataFrame:
    """信号表加 group / ov / m20 / m60 / gap / kr3 / rho（行情宽表里没有这只票或这一天 → 缺值）。"""
    di = F["days"].get_indexer(pd.to_datetime(S["date"]))
    cj = np.array([F["col"].get(t, -1) for t in S["ticker"]])
    ok = (di >= 0) & (cj >= 0)
    out = S.copy()
    out["group"] = [EL.group_of(t, s33) for t in S["ticker"]]
    for k in ("ov", "m20", "m60", "rho"):
        v = np.full(len(S), np.nan)
        v[ok] = F["LP"][k][di[ok], cj[ok]]
        out[k] = v
    s20 = np.full(len(S), np.nan)
    s20[ok] = F["comps"]["s20"][di[ok], cj[ok]]
    out["gap"] = out["m20"].to_numpy(float) - s20
    kr = np.full(len(S), np.nan)
    kr[di >= 0] = F["kr3"][di[di >= 0]]
    out["kr3"] = kr
    return out


def build(tag: str, p0, bt, rt: float, s33: dict, R: pd.DataFrame, kr: pd.Series, base: dict | None = None) -> dict:
    import leap_confirm as LF
    import sell_confirm as SCF
    t0 = time.time()
    if tag == "W":
        from qbreak import wide_universe as WU
        ctx, fa = SCF.wide_context(p0)
        a, b = W_WIN
        keep, mem = LF.w2_keep(ctx, fa), {}
        Ph, dh, nh = LF.yf_panel(WU.tickers(WU.load()), *HIST["W"])
        F = feature_panel(Ph, dh, nh, R, kr, list(range(2006, 2017)))
    else:
        ctx = LF.context({"J2": "J"}.get(tag, tag), jmem="U2" if tag == "J2" else "U0")
        a, b = ctx["start"], ctx["end"] or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        if tag == "J" and base is not None:
            fa = {t: base["fa"][t] for t in (ctx["names"][j] for j in ctx["cols"]) if t in base["fa"]}
            keep, F = {t: base["keep"][t] for t in fa}, base["F"]
        else:
            fa = LF.frames(ctx, p0)
            keep = LF.w2_keep(ctx, fa)
            if tag == "E":
                from qbreak.config import universe
                Ph, dh, nh = LF.yf_panel(list(universe("JP", "broad")), *HIST["E"])
                F = feature_panel(Ph, dh, nh, R, kr, list(range(2006, 2017)))
            elif tag == "Z":
                F = feature_panel(ctx["P"], ctx["days"], ctx["names"], R, kr, list(range(2001, 2007)))
            else:
                F = feature_panel(ctx["P"], ctx["days"], ctx["names"], R, kr, list(range(2017, 2027)))
        mem = LF.member_mask(ctx, fa) if tag == "J2" else {}
    Sall = attach(BS.all_signals(fa, keep, mem), F, s33)
    d = pd.to_datetime(Sall["date"])
    S = BS.single_trades(fa, Sall[(d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b))].reset_index(drop=True), p0, bt, rt)
    exp = S["group"].isin(("direct", "indirect"))
    say(f"- {tag}（{a}〜{b}）：指标表 {len(fa)} 只；W2 保留的信号（全部年份）{len(Sall)} 个 → 窗口内有结果的 {len(S)} 个"
        f"（直接 {int((S['group'] == 'direct').sum())}、间接 {int((S['group'] == 'indirect').sum())}；其中有海外联动的 "
        f"{int((exp & np.isfinite(S['m20'])).sum())} / {int(exp.sum())}）；{round(time.time() - t0)} s")
    return {"ctx": ctx, "fa": fa, "keep": keep, "Sall": Sall, "S": S, "F": F, "a": a, "b": b}


# ───────────────────────── Part A ─────────────────────────
def part_a(tag: str, F: dict, s33: dict, mem: np.ndarray | None) -> dict:
    days = F["days"]
    a, b = A_WIN[tag]
    win = (days >= pd.Timestamp(a)) & ((days <= pd.Timestamp(b)) if b else True)
    grp = np.array([EL.group_of(t, s33) for t in F["names"]])
    LP, C = F["LP"], F["comps"]
    out: dict = {"links": {}}
    for g in GROUPS:
        base = win[:, None] & (grp == g)[None, :]
        if mem is not None:
            base = base & mem
        has = base & np.isfinite(LP["z1"])
        cells = int(base.sum())
        r = {"cells": cells, "linked": float(has.sum() / cells) if cells else np.nan, "seg": {}, "mon": {}}
        for k, (_, h) in SEG.items():
            r["seg"][k] = EL.pooled_nw(C[k], LP["z1"], has, h + 5)
        for k, x in (("z20", LP["z20"]), ("z60", LP["z60"])):
            r["mon"][k] = EL.pooled_nw(C["r20"], x, base & np.isfinite(x), 25)
        gap = LP["m20"] - C["s20"]
        m = base & np.isfinite(gap)
        sd = float(np.nanstd(gap[m])) if m.any() else np.nan
        r["mon"]["gap"] = EL.pooled_nw(C["r20"], gap / sd if sd and sd > 0 else gap, m, 25)
        kr = np.repeat(F["kr3"][:, None], len(F["names"]), axis=1)
        m = base & np.isfinite(kr)
        sd = float(np.nanstd(kr[m])) if m.any() else np.nan
        r["mon"]["kr3"] = EL.pooled_nw(C["r20"], kr / sd if sd and sd > 0 else kr, m, 25)
        tot = sum(abs(r["seg"][k]["b"]) for k in SEG if np.isfinite(r["seg"][k]["b"]))
        r["late_share"] = ((abs(r["seg"]["id1"]["b"]) + abs(r["seg"]["r2_5"]["b"])) / tot) if tot else np.nan
        out[g] = r
        yr = days.year.to_numpy()
        cnt: dict[str, int] = {}
        rhos = []
        for y, lk in F["links"].items():
            if not np.any(win & (yr == y)):
                continue
            for t, (asset, rho, _) in lk.items():
                if EL.group_of(t, s33) == g:
                    cnt[asset] = cnt.get(asset, 0) + 1
                    rhos.append(rho)
        out["links"][g] = {"top": sorted(cnt.items(), key=lambda kv: -kv[1])[:4], "rho_med": float(np.median(rhos)) if rhos else np.nan,
                           "n": int(sum(cnt.values()))}
    return out


def labels(A: dict) -> dict:
    """三 的标签（写死的条件）。"""
    def same(k, g):
        on = [A[t][g]["seg"]["on"]["b"] for t in ("E", "J2")]
        x = [A[t][g]["seg"][k] for t in ("E", "J2")]
        return all(np.sign(x[i]["b"]) == np.sign(on[i]) and abs(x[i]["t"]) >= 2 for i in range(2))
    mon = any(all(np.isfinite(A[t][g]["mon"][k]["t"]) and abs(A[t][g]["mon"][k]["t"]) >= 2 for t in ("E", "J2"))
              and np.sign(A["E"][g]["mon"][k]["b"]) == np.sign(A["J2"][g]["mon"][k]["b"])
              for g in ("direct", "indirect") for k in ("z20", "z60"))
    return {"day1": any(same("id1", g) for g in ("direct", "indirect")), "day2_5": any(same("r2_5", g) for g in ("direct", "indirect")),
            "month": bool(mon), "indirect_slower": all(A[t]["indirect"]["late_share"] > A[t]["direct"]["late_share"] for t in ("E", "J2"))}


# ───────────────────────── Part B ─────────────────────────
def per_set(S: pd.DataFrame, placebo: bool = False) -> dict:
    out = {}
    net = S["net"].to_numpy(float)
    for k, v in EL.VARIANTS.items():
        sc = EL.scope_mask(S, k)
        kp = EL.keep_mask(S, k)
        x = BQ.delta(net[sc], kp[sc])
        if placebo and x["kept"]:
            x.update(BQ.placebo(net[sc], S["ticker"].to_numpy()[sc], S["week"].to_numpy()[sc], x["frac"]))
        f = S[v["col"]].to_numpy(float)[sc]
        x["rho"] = BQ.spearman(f, net[sc])
        x["nan_pct"] = float((~np.isfinite(f)).mean() * 100) if sc.any() else np.nan
        out[k] = x
    return out


def masks(fa: dict, Sall: pd.DataFrame, key: str) -> dict[str, np.ndarray]:
    kp = EL.keep_mask(Sall, key)
    out = {t: np.ones(len(df), bool) for t, df in fa.items()}
    for t, d, ok in zip(Sall["ticker"], Sall["date"], kp):
        if not ok:
            out[t][fa[t].index.get_loc(d)] = False
    return out


def portfolio(B: dict, p, era: str, keys) -> tuple[dict, dict]:
    import leap_confirm as LF
    import sell_explore as SX
    ctx, fa = B["ctx"], B["fa"]
    run_fn = LF.runner(ctx, fa)
    fw = LF.with_mask(fa, B["keep"])
    base = SX.summ(LF.run(ctx, run_fn, fw, p), era)
    return base, {k: SX.summ(LF.run(ctx, run_fn, LF.with_mask(fw, masks(fa, B["Sall"], k)), p), era) for k in keys}


def main() -> int:
    import sell_confirm as SCF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    s33 = BS.sector_map()
    keys = list(EL.VARIANTS)
    R, kr, cover = us_data()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 出口股 × 海外股票 / 外需：日差 / 月差 → 买点（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/exportlink_study.py 开头（运行前写定）；共用部分 scripts/exportlink_common.py。")
    say(f"美国 ETF 缓存：{min(v[0] for k, v in cover.items() if k != 'KR_exports')}〜{max(v[1] for k, v in cover.items() if k != 'KR_exports')}；"
        f"韩国出口 {cover['KR_exports'][0]}〜{cover['KR_exports'][1]}")
    say("\n## 〇、样本")
    B = {"J2": build("J2", p0, bt, rt, s33, R, kr)}
    B["J"] = build("J", p0, bt, rt, s33, R, kr, base=B["J2"])
    B["E"] = build("E", p0, bt, rt, s33, R, kr)

    say("\n## 一、Part A：海外涨跌传到日本个股要多久（只描述；斜率 = 海外联动 ETF 涨 1 个标准差，个股相对收益 %，括号 = t）")
    memJ = B["J2"]["ctx"]["D"]["mem"]["U2"]
    A = {"E": part_a("E", B["E"]["F"], s33, None), "J2": part_a("J2", B["J2"]["F"], s33, memJ)}
    say("| 组 | 年代 | 股票·日（有联动的比例） | 隔夜 | 第 1 天日内 | 第 2〜5 天 | 第 6〜20 天 | 第 1〜5 天占四段合计 |")
    say("|---|---|---|---|---|---|---|---|")
    for g, gz in GROUPS.items():
        for t in ("E", "J2"):
            r = A[t][g]
            cells = " | ".join(f"{fmt(r['seg'][k]['b'], '{:+.3f}')}（{fmt(r['seg'][k]['t'], '{:+.1f}')}）" for k in SEG)
            say(f"| {gz} | {t} | {r['cells']:,}（{fmt(r['linked'] * 100 if np.isfinite(r['linked']) else None, '{:.0f}')}%） | {cells} | "
                f"{fmt(r['late_share'] * 100 if np.isfinite(r['late_share']) else None, '{:.0f}')}% |")
    say("\n| 组 | 年代 | 20 日动量 → 之后 20 日 | 60 日动量 → 之后 20 日 | 追赶（海外先涨）→ 之后 20 日 | 韩国出口 3 个月 → 之后 20 日 |")
    say("|---|---|---|---|---|---|")
    for g, gz in GROUPS.items():
        for t in ("E", "J2"):
            r = A[t][g]["mon"]
            say(f"| {gz} | {t} | " + " | ".join(f"{fmt(r[k]['b'], '{:+.3f}')}（{fmt(r[k]['t'], '{:+.1f}')}）" for k in ("z20", "z60", "gap", "kr3")) + " |")
    say("\n联动的 ETF（每只票每年挑一次；最多的 4 个，括号 = 票·年数；相关中位数）：")
    for g, gz in GROUPS.items():
        for t in ("E", "J2"):
            lk = A[t]["links"][g]
            say(f"- {gz} {t}：" + "、".join(f"{a}（{n}）" for a, n in lk["top"]) + f"；相关中位 {fmt(lk['rho_med'], '{:.2f}')}（{lk['n']} 票·年）")
    L = labels(A)
    say(f"\n标签（写死的条件）：第 1 天还在走 **{'是' if L['day1'] else '否'}**；拖到第 2〜5 天 **{'是' if L['day2_5'] else '否'}**；"
        f"月差存在 **{'是' if L['month'] else '否'}**；间接比直接慢 **{'是' if L['indirect_slower'] else '否'}**")

    say("\n## 二、Part B：拿来当突破买点的过滤（探索；运行前写定的入选规则；统计只在范围内的信号里比）")
    st = {"J2": per_set(B["J2"]["S"], placebo=True), "E": per_set(B["E"]["S"]), "J": per_set(B["J"]["S"])}
    base_E, port_E = portfolio(B["E"], p, "E", keys)
    base_J, port_J = portfolio(B["J"], p, "J", keys)
    base = {"E": base_E, "J": base_J}
    res = {}
    for k in keys:
        port = {"E": port_E[k], "J": port_J[k]}
        res[k] = {"j2": st["J2"][k], "e": st["E"][k], "j": st["J"][k], "port": port}
        res[k]["fails"] = EL.qualifies(res[k]["j2"], res[k]["e"], res[k]["j"], port, base)
    final = EL.pick(res)
    for tag in ("J2", "E", "J"):
        S = B[tag]["S"]
        exp = S[S["group"].isin(("direct", "indirect"))]
        x = BQ._st(exp["net"].to_numpy(float))
        say(f"- 现行 {tag} 出口股（直接 + 间接）：{x['n']} 个信号，胜率 {fmt(x['win'], '{:.1f}')}%，每笔 {fmt(x['mean'])}%")
    say(f"- 组合现行（S0C2 + W2）：E Calmar {fmt(base_E['calmar'], '{:.3f}')}；J {fmt(base_J['calmar'], '{:.3f}')}")
    say("\n| 变体 | J2 范围内 / 保留 | J2 胜率差 | J2 每笔差（随机 95 分位） | E 胜率差 / 每笔差 | J 胜率差 / 每笔差 | 组合 Calmar E / J | 结果 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in keys:
        j2, e, j, pt = res[k]["j2"], res[k]["e"], res[k]["j"], res[k]["port"]
        say(f"| {k} {EL.VARIANTS[k]['zh']} | {j2['n']} / {fmt(j2['frac'] * 100 if j2['n'] else None, '{:.0f}')}% | {fmt(j2['dwin'], '{:+.1f}')} pp | "
            f"{fmt(j2['dmean'])} pp（{fmt(j2.get('dmean_q95'))}） | {fmt(e['dwin'], '{:+.1f}')} / {fmt(e['dmean'])} pp | "
            f"{fmt(j['dwin'], '{:+.1f}')} / {fmt(j['dmean'])} pp | {fmt(pt['E']['calmar'], '{:.3f}')} / {fmt(pt['J']['calmar'], '{:.3f}')} | "
            + ("**入选**" if k in final else ("✓（没排上）" if not res[k]["fails"] else "✗ " + "；".join(res[k]["fails"]))) + " |")
    say(f"\n- 入选：{('、'.join(final)) if final else '没有'}" + ("" if final else " → 按规则这一轮到此为止，Z 与另一批股票（W）不用、留着；模拟盘不变。"))

    conf: dict = {}
    if final:
        say("\n## 三、确认（没看过的数据：Z = 2001〜2006 日経225；W = 另一批股票 714 只 2006〜2016；C = 两者合起来，只在范围内）")
        B["Z"] = build("Z", p0, bt, rt, s33, R, kr)
        B["W"] = build("W", p0, bt, rt, s33, R, kr)
        C = pd.concat([B["Z"]["S"], B["W"]["S"]], ignore_index=True)
        st["Z"], st["W"], st["C"] = per_set(B["Z"]["S"]), per_set(B["W"]["S"]), per_set(C)
        base_Z, port_Z = portfolio(B["Z"], p, "Z", final)
        for k in final:
            sc = EL.scope_mask(C, k)
            c = {**st["C"][k], **BQ.boot_delta(C["net"].to_numpy(float)[sc], EL.keep_mask(C, k)[sc], C["month"].to_numpy()[sc])}
            v = BQ.verdict(c, st["Z"][k], st["W"][k])
            conf[k] = {"C": c, "Z": st["Z"][k], "W": st["W"][k], "verdict": v, "port_Z": port_Z[k]}
            say(f"- {k} {EL.VARIANTS[k]['zh']}：C 范围内 {c['n']} 个、保留 {fmt(c['frac'] * 100, '{:.0f}')}%；胜率 {fmt(c['win_all'], '{:.1f}')}% → "
                f"{fmt(c['win'], '{:.1f}')}%（差 {fmt(c['dwin'], '{:+.1f}')} pp，95% 区间 {fmt(c['dwin_lo'], '{:+.1f}')}〜{fmt(c['dwin_hi'], '{:+.1f}')}）；"
                f"每笔 {fmt(c['mean_all'])}% → {fmt(c['mean'])}%（差 {fmt(c['dmean'])} pp，95% 区间 {fmt(c['dmean_lo'])}〜{fmt(c['dmean_hi'])}）；"
                f"Z 每笔差 {fmt(st['Z'][k]['dmean'])} pp、W {fmt(st['W'][k]['dmean'])} pp → **{v}**")
            say(f"  - Z 组合（只描述）：Calmar {fmt(base_Z['calmar'], '{:.3f}')} → {fmt(port_Z[k]['calmar'], '{:.3f}')}，"
                f"回撤 {fmt(base_Z['dd'], '{:.2f}')}% → {fmt(port_Z[k]['dd'], '{:.2f}')}%")
        conf["_base_Z"] = base_Z

    say("\n## 四、另报（只描述）：范围内各特征与每笔净收益的秩相关 / 保留 − 去掉 的每笔（胜率）/ 缺值")
    tags = [t for t in ("J2", "E", "J", "Z", "W") if t in st]
    say("| 变体 | " + " | ".join(tags) + " |")
    say("|---|" + "---|" * len(tags))
    for k in keys:
        cells = []
        for t in tags:
            x = st[t][k]
            part = x["kept"] and x["kept"] < x["n"]
            cells.append(f"{fmt(x['rho'], '{:+.3f}')} / {fmt(x['mean'] - x['mean_rm'] if part else None)} pp"
                         f"（{fmt(x['win'] - x['win_rm'] if part else None, '{:+.1f}')} pp）/ {fmt(x['nan_pct'], '{:.0f}')}%")
        say(f"| {k} | " + " | ".join(cells) + " |")
    say(f"\n用时 {round(time.time() - t0)} s。非投资建议。")

    out = paths.out_dir()
    (out / "exportlink_study.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    payload = {"code": code, "cover": cover, "partA": {t: {g: A[t][g] for g in GROUPS} | {"links": A[t]["links"]} for t in A}, "labels": L,
               "base": {t: BQ._st(B[t]["S"]["net"].to_numpy(float)) for t in B}, "port_base": base, "res": res, "final": final,
               "confirm": conf, "stats": st}
    (out / "exportlink_study.json").write_text(json.dumps(BS._clean(payload), ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
