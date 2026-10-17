"""commodity_fit_study.py — 粮食 / 金属 / 贵金属 / 能源 ETF 对各类股票的影响（横展开），以及把商品加进「宏观顺风度」后
能不能挑出之后表现更好的票（事先写定，先提交后运行，结果出来不改规则）。

用户问（2026-09-25 晚）：不光利率，还要考虑各类粮食、原材料等 ETF 对各类股票的影响，横展开（接上一问：加进候补队列优先级的筛选条件）。
商品（qbreak/sensitivity.py COMMODS；美国挂牌，周五到周五对数周收益 %；日本资产取前一个美国收盘）：
  粮食 DBA 农产品综合 / CORN 玉米 / WEAT 小麦 / SOYB 大豆 / CANE 糖 / KC=F 咖啡 / CC=F 可可
  金属 DBB 工业金属 / CPER 铜 / ALI=F 铝 / TIO=F 铁矿石；贵金属 GLD 金 / SLV 银 / PPLT 铂 / PALL 钯
  能源 WTI 原油（已有，FRED 现货）/ UNG 天然气 / TTF=F 欧洲天然气 / UGA 汽油；综合 DBC
  （=F 为期货连续合约：换月跳空让系数偏小、偏噪；ETF 没有这个问题）
  数据清洗（运行前定）：单日 ±25% 以上、第二天又几乎全部回去的报价视为错价（factors.despike；实测只有 CPER 2014-12-04、2015-02-02）。
资产：日経225 成分股（现行名单，幸存者偏差）；行业：日本 TOPIX-17 行业 ETF 1617–1633（成交稀少，只作分析）、
  美国行业 / 产业 ETF（见 US_ETF）。
方法：
  A 同周联动（只报告）：最近 104 周，资产周收益 ~ 大盘（日本 日経225 / 美国 S&P500）+ 单个商品 → 商品系数（商品涨 1% 时
    该资产相对大盘同周多涨几 %）与 t 值；另报相邻的前一个 104 周同样的系数，统计两段同号的比例（敏感度稳不稳）。
  B 日経225 个股：各商品受益 / 受损前 10（按系数，只列 |t| ≥ 2 的）。
  C 板块条件表（只报告）：各商品近 60 日变化处在全期上 1/3 / 下 1/3 时，日経225 各板块之后 20 日平均超额收益（相对日経）。
  D 扩展顺风度检验（2009-01～；前半 2009–2017 / 后半 2018–；只用当时已知的数据）：5 个宏观因素再加
    农产品综合 DBA、工业金属 DBB、黄金 GLD、天然气 UNG 一起回归（sensitivity.FACTORS_EXT）：
    ① 月末横截面 前 1/5 − 后 1/5 之后 20 日超额收益、秩相关 IC；② 突破信号 顺风（>0）− 逆风（≤0）20 日收益差（按月聚类 t）；
    同一期间 5 因素版的 ①② 作对照。
  E 当前：各商品近 60 日平均周变化；扩展顺风度前后 10 名。
采用规则：
  显示：候补队列的宏观顺风度改用扩展版（说明文字会出现 黄金 / 农产品 / 工业金属 / 天然气），只作参考 —— 用户要求，一律执行；
  交易排序：与 regime_fit_study 同一门槛（①≥+0.5% 且 t≥2、两半都为正；②≥+1.0pp 且 t≥2、两半都为正），
    都通过才另做组合检验（需要的引擎选项届时实现）。
输出 var/out/commodity_fit_study.md / .json。
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import factors, paths                                            # noqa: E402
from qbreak import sensitivity as SN                                         # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak.config import DataConfig, ExecConfig, universe                   # noqa: E402
from qbreak.data import load_universe                                        # noqa: E402
from qbreak.sectors import sector_cn                                         # noqa: E402
from qbreak.strategy import IndicatorCache                                   # noqa: E402
from qbreak.trader import load_params                                        # noqa: E402

START, MID, H = pd.Timestamp("2009-01-01"), pd.Timestamp("2018-01-01"), 20
JP_ETF = {"1617.T": "食品", "1618.T": "能源资源", "1619.T": "建设·资材", "1620.T": "素材·化学", "1621.T": "医药品",
          "1622.T": "汽车·运输机", "1623.T": "钢铁·有色", "1624.T": "机械", "1625.T": "电机·精密", "1626.T": "信息通信·服务",
          "1627.T": "电力·燃气", "1628.T": "运输·物流", "1629.T": "商社·批发", "1630.T": "零售", "1631.T": "银行",
          "1632.T": "金融（除银行）", "1633.T": "不动产"}
US_ETF = {"XLE": "能源", "XLB": "原材料", "XLI": "工业", "XLP": "必需消费", "XLU": "公用事业", "XLF": "金融", "XLK": "科技",
          "XLV": "医疗", "XLY": "可选消费", "XLRE": "房地产", "XLC": "通信", "XME": "金属矿业", "GDX": "金矿股", "KRE": "地区银行",
          "ITB": "住宅建筑", "XRT": "零售", "JETS": "航空", "IYT": "运输", "XOP": "油气开采", "OIH": "油服", "MOO": "农业综合",
          "PBJ": "食品饮料", "SLX": "钢铁", "SMH": "半导体", "IBB": "生物科技", "VNQ": "REIT"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def tstat(x: pd.Series) -> float | None:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else None


def fmt_t(v) -> str:
    return "—" if v is None or v != v else f"{v:.2f}"


def sens_table(rets: dict, W: pd.DataFrame, keys: list[str]) -> tuple[dict, dict]:
    """{资产: {商品: (系数, t)}}（最近 104 周）与前一个 104 周的系数（稳定性用）。"""
    end, prev_end = W.index[-1], W.index[-1 - SN.WEEKS]
    now, prev = {}, {}
    for a, y in rets.items():
        now[a], prev[a] = {}, {}
        for c in keys:
            r = SN.pair_beta(y, W[c], W["mkt"], end)
            p = SN.pair_beta(y, W[c], W["mkt"], prev_end)
            if r is not None:
                now[a][c] = r
            if p is not None:
                prev[a][c] = p
    return now, prev


def same_sign_rate(now: dict, prev: dict, keys: list[str]) -> dict:
    out = {}
    for c in keys:
        pairs = [(now[a][c][0], prev[a][c][0]) for a in now if c in now[a] and c in prev.get(a, {})]
        out[c] = (sum(1 for x, y in pairs if x * y > 0) / len(pairs) * 100) if pairs else None
    return out


def main() -> int:
    t0 = time.time()
    d = TH.load_inputs()
    r = d["raw"]
    keys = list(SN.COMMODS)
    px = {k: factors.despike(factors.yf_close(sym)) for k, (sym, _, _) in SN.COMMODS.items()}
    n225, spx = d["n225"], d["spx"]
    jp_days = n225.index[n225.index >= "2004-01-01"]
    us_days = spx.index[spx.index >= "2004-01-01"]
    lv = SN.factor_levels(jp_days, n225, d["jgb"], r["DGS10"], r["DCOILWTICO"], d["fx"], r["BAA10Y"], extra=px)
    lv_us = SN.factor_levels(us_days, spx, d["jgb"], r["DGS10"], r["DCOILWTICO"], d["fx"], r["BAA10Y"], extra=px, same_day=True)
    W, W_us = SN.weekly_changes(lv), SN.weekly_changes(lv_us)
    keys_all = ["oil"] + keys
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data = load_universe(universe("JP", "broad"), d21)
    rets = {t: SN.stock_weekly(df["Close"], W.index) for t, df in data.items()}
    jp_etf = {k: SN.stock_weekly(factors.despike(factors.yf_close(k)), W.index) for k in JP_ETF}
    us_etf = {k: SN.stock_weekly(factors.despike(factors.yf_close(k)), W_us.index) for k in US_ETF}
    say(f"# 粮食 / 金属 / 贵金属 / 能源 ETF 对各类股票的影响（{pd.Timestamp.today().date()}；日経225 {len(data)} 只、"
        f"TOPIX-17 行业 ETF {len(JP_ETF)}、美国行业 ETF {len(US_ETF)}；数据截至 日本 {jp_days[-1].date()} / 美国 {us_days[-1].date()}）")
    lab = {k: SN.LABEL[k] for k in keys_all}
    out: dict = {"labels": lab}

    # ── A 同周联动 ──
    sj, sj_prev = sens_table(jp_etf, W, keys_all)
    su, su_prev = sens_table(us_etf, W_us, keys_all)
    ss_n, ss_np = sens_table(rets, W, keys_all)
    stab = {"JP_ETF": same_sign_rate(sj, sj_prev, keys_all), "US_ETF": same_sign_rate(su, su_prev, keys_all),
            "N225": same_sign_rate(ss_n, ss_np, keys_all)}
    out["A"] = {"jp_etf": {a: {c: list(v) for c, v in m.items()} for a, m in sj.items()},
                "us_etf": {a: {c: list(v) for c, v in m.items()} for a, m in su.items()}, "stability": stab}
    say("\n## A 同周联动：商品涨 1% 时，各行业相对大盘同周多涨（+）/ 少涨（−）几 %（最近 104 周；* = |t| ≥ 2）")
    say("| 商品 | 日本行业（TOPIX-17 ETF）受益 | 日本行业受损 | 美国行业受益 | 美国行业受损 | 与前 2 年同号比例（日本行业 / 美国行业 / 日経225 个股） |")
    say("|---|---|---|---|---|---|")
    for c in keys_all:
        def top(m, names, rev):
            v = sorted(((a, m[a][c]) for a in m if c in m[a]), key=lambda z: z[1][0], reverse=rev)[:3]
            return "、".join(f"{names[a]} {b:+.2f}{'*' if abs(t) >= 2 else ''}" for a, (b, t) in v)
        st = stab
        say(f"| {lab[c]} | {top(sj, JP_ETF, True)} | {top(sj, JP_ETF, False)} | {top(su, US_ETF, True)} | {top(su, US_ETF, False)} | "
            f"{fmt_t(st['JP_ETF'][c])}% / {fmt_t(st['US_ETF'][c])}% / {fmt_t(st['N225'][c])}% |")

    # ── B 日経225 个股 ──
    say("\n## B 日経225 个股：商品涨 1% 时同周多涨 / 少涨最多的（最近 104 周，控制日経，只列 |t| ≥ 2）")
    tops = {}
    for c in keys_all:
        v = [(t, b, tt) for t, m in ss_n.items() if c in m for b, tt in [m[c]] if abs(tt) >= 2]
        up = sorted([z for z in v if z[1] > 0], key=lambda z: -z[1])[:10]
        dn = sorted([z for z in v if z[1] < 0], key=lambda z: z[1])[:10]
        tops[c] = {"up": [(t, sector_cn(t, "JP"), round(b, 3)) for t, b, _ in up],
                   "down": [(t, sector_cn(t, "JP"), round(b, 3)) for t, b, _ in dn]}
        say(f"- {lab[c]}：受益 " + ("、".join(f"{t}({s} {b:+.2f})" for t, s, b in tops[c]["up"]) or "无显著")
            + "；受损 " + ("、".join(f"{t}({s} {b:+.2f})" for t, s, b in tops[c]["down"]) or "无显著"))
    out["B"] = tops

    # ── D 扩展顺风度检验（先算，C 用同一批月末数据）──
    closes = pd.DataFrame({t: df["Close"] for t, df in data.items()}).reindex(jp_days)
    me = pd.Series(jp_days, index=jp_days).groupby(jp_days.to_period("M")).max()
    me = [x for x in me if x >= START and jp_days.get_loc(x) + H < len(jp_days)]
    versions = {"base": SN.FACTORS, "ext": SN.FACTORS_EXT}
    X = {v: W[f + ["mkt"]] for v, f in versions.items()}
    cs_rows = {v: [] for v in versions}
    sector_rows = []
    for dte in me:
        k = jp_days.get_loc(dte)
        fwd_n = n225.loc[jp_days[k + H]] / n225.loc[dte] - 1
        wend = W.index[W.index <= dte]
        if len(wend) < SN.MIN_WEEKS:
            continue
        tr_all = SN.trend(lv, dte, factors=SN.FACTORS + keys)
        for v, fs in versions.items():
            sc = {}
            for t, y in rets.items():
                s, _ = SN.fit_score(SN.betas(y, X[v], wend[-1]), tr_all, fs)
                c0, c1 = closes.at[dte, t], closes.iloc[k + H][t]
                if s is None or not (c0 == c0 and c1 == c1 and c0 > 0):
                    continue
                sc[t] = (s, c1 / c0 - 1 - fwd_n)
                if v == "ext":
                    sector_rows.append({"date": dte, "sector": sector_cn(t, "JP"), "ex": sc[t][1],
                                        **{c: tr_all.get(c, np.nan) for c in keys}})
            if len(sc) < 50:
                continue
            df = pd.DataFrame(sc, index=["fit", "ex"]).T
            q = df["fit"].rank(pct=True)
            cs_rows[v].append({"date": dte, "spread": df.loc[q > 0.8, "ex"].mean() - df.loc[q <= 0.2, "ex"].mean(),
                               "ic": df["fit"].rank().corr(df["ex"].rank())})
    res1 = {}
    for v in versions:
        cs = pd.DataFrame(cs_rows[v]).set_index("date")
        h1, h2 = cs[cs.index < MID], cs[cs.index >= MID]
        res1[v] = {"months": len(cs), "spread_mean": float(cs["spread"].mean() * 100), "spread_t": tstat(cs["spread"]),
                   "h1": float(h1["spread"].mean() * 100), "h2": float(h2["spread"].mean() * 100),
                   "ic_mean": float(cs["ic"].mean()), "ic_t": tstat(cs["ic"])}
    p = load_params(market="JP")
    ind = dict(IndicatorCache(data).all(p))
    gap = ExecConfig.for_market("JP", "rakuten").max_entry_gap_pct
    res2 = {}
    sig = {v: [] for v in versions}
    for t, df in ind.items():
        O, C = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
        nk = n225.reindex(df.index).ffill()
        for i in np.where(df["entry"].to_numpy(bool))[0]:
            dte = df.index[i]
            if dte < START or i + H >= len(df) or O[i + 1] > C[i] * (1 + gap / 100):
                continue
            wend = W.index[W.index <= dte]
            if not len(wend):
                continue
            tr_all = SN.trend(lv, dte, factors=SN.FACTORS + keys)
            for v, fs in versions.items():
                s, _ = SN.fit_score(SN.betas(rets[t], X[v], wend[-1]), tr_all, fs)
                if s is not None:
                    sig[v].append({"date": dte, "fit": s, "r": C[i + H] / O[i + 1] - 1})
    for v in versions:
        sg = pd.DataFrame(sig[v])
        pos, neg = sg[sg["fit"] > 0], sg[sg["fit"] <= 0]
        mp = pos.groupby(pos["date"].dt.to_period("M"))["r"].mean()
        mn = neg.groupby(neg["date"].dt.to_period("M"))["r"].mean()
        diff = float(pos["r"].mean() - neg["r"].mean()) * 100
        se = math.sqrt(mp.var(ddof=1) / len(mp) + mn.var(ddof=1) / len(mn)) * 100 if len(mp) > 2 and len(mn) > 2 else float("nan")
        hh = lambda a, b: float((a["r"].mean() - b["r"].mean()) * 100)                             # noqa: E731
        res2[v] = {"n": len(sg), "n_pos": len(pos), "diff": diff, "t": diff / se if se == se and se > 0 else None,
                   "h1": hh(pos[pos["date"] < MID], neg[neg["date"] < MID]),
                   "h2": hh(pos[pos["date"] >= MID], neg[neg["date"] >= MID])}
    say("\n## D 扩展顺风度（5 个宏观因素 + 农产品 / 工业金属 / 黄金 / 天然气）能不能挑出之后更好的票（2009-01～）")
    say("| 版本 | ① 月末前 1/5 − 后 1/5（20 日超额） | ① 前半 / 后半 | ① 秩相关 IC | ② 信号 顺风 − 逆风 | ② 前半 / 后半 |")
    say("|---|---|---|---|---|---|")
    for v, name in (("base", "5 因素（现行）"), ("ext", "扩展 9 因素")):
        a, b = res1[v], res2[v]
        say(f"| {name} | {a['spread_mean']:+.2f}%（t {fmt_t(a['spread_t'])}，{a['months']} 个月） | {a['h1']:+.2f}% / {a['h2']:+.2f}% | "
            f"{a['ic_mean']:+.3f}（t {fmt_t(a['ic_t'])}） | {b['diff']:+.2f}pp（t {fmt_t(b['t'])}，{b['n']} 个） | {b['h1']:+.2f} / {b['h2']:+.2f} |")
    e1, e2 = res1["ext"], res2["ext"]
    ok1 = e1["spread_mean"] >= 0.5 and (e1["spread_t"] or 0) >= 2.0 and e1["h1"] > 0 and e1["h2"] > 0
    ok2 = e2["diff"] >= 1.0 and (e2["t"] or 0) >= 2.0 and e2["h1"] > 0 and e2["h2"] > 0
    say(f"\n判定（事先规则）：候补队列的宏观顺风度改用扩展版（只作参考）；交易排序 —— ①{'通过' if ok1 else '未通过'}，"
        f"②{'通过' if ok2 else '未通过'}{'，下一步做组合检验' if ok1 and ok2 else ' → 不用于交易排序'}")
    out["D"] = {"cross_section": res1, "signals": res2, "ok1": bool(ok1), "ok2": bool(ok2), "trade_candidate": bool(ok1 and ok2)}

    # ── C 板块条件表 ──
    sr = pd.DataFrame(sector_rows)
    say("\n## C 各商品近 60 日明显上涨 / 下跌时，日経225 各板块之后 20 日的平均超额收益（相对日経；2009～；只报告）")
    cond = {}
    for c in keys:
        col = sr[c].dropna()
        if col.empty:
            continue
        lo, hi = col.quantile(1 / 3), col.quantile(2 / 3)
        for state, m in (("上涨", sr[c] >= hi), ("下跌", sr[c] <= lo)):
            g = sr[m].groupby("sector")["ex"].agg(["mean", "size"])
            g = g[g["size"] >= 30].sort_values("mean", ascending=False)
            if g.empty:
                continue
            cond[f"{c}|{state}"] = {"best": [(s, round(v * 100, 2)) for s, v in g["mean"].head(3).items()],
                                    "worst": [(s, round(v * 100, 2)) for s, v in g["mean"].tail(3).items()]}
            say(f"- {lab[c]}{state}：较好 " + "、".join(f"{s} {v:+.2f}%" for s, v in cond[f'{c}|{state}']['best'])
                + "；较差 " + "、".join(f"{s} {v:+.2f}%" for s, v in cond[f'{c}|{state}']['worst']))
    out["C"] = cond

    # ── E 当前 ──
    last = jp_days[-1]
    tr_now = SN.trend(lv, last, factors=SN.FACTORS + keys)
    say(f"\n## E 当前（{last.date()}）近 60 个交易日的平均周变化：" + "、".join(f"{lab.get(c, SN.LABEL[c])} {tr_now[c]:+.2f}%"
                                                                     for c in keys if tr_now.get(c) == tr_now.get(c)))
    wend = W.index[W.index <= last][-1]
    cur = {}
    for t, y in rets.items():
        s, why = SN.fit_score(SN.betas(y, X["ext"], wend), tr_now, SN.FACTORS_EXT)
        if s is not None:
            cur[t] = (s, why)
    fs = sorted(cur, key=lambda t: -cur[t][0])
    say("- 扩展顺风度前 10：" + "、".join(f"{t}({sector_cn(t, 'JP')}，{cur[t][1]})" for t in fs[:10]))
    say("- 扩展顺风度后 10：" + "、".join(f"{t}({sector_cn(t, 'JP')}，{cur[t][1]})" for t in fs[-10:]))
    out["E"] = {"trend_now": {c: float(tr_now[c]) for c in tr_now.index if tr_now[c] == tr_now[c]},
                "top": [(t, cur[t][0], cur[t][1]) for t in fs[:10]], "bottom": [(t, cur[t][0], cur[t][1]) for t in fs[-10:]]}
    say(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "commodity_fit_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
