"""combo_study.py — 各层怎么搭配：买点质量 × 牛熊距离 × 新仓倍数 × 宏观触发 × 威胁指数 × 健康度（横展开）
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「结合现在所有的研究结果，来研究如何互相搭配才能选出接下来的最优股票 / 判断牛熊距离、新仓倍数、宏观触发、威胁指数等等，进行横展开」。

一、描述（不参与判定）：日経225 股票池每只票各自独立的突破交易（现行参数，2006-10〜），按信号日当时的状态分组，
  前半（2006-10〜2015-12）/ 后半（2016〜）各自的笔数、胜率、每笔期望：
  日経牛熊（牛 / 熊）、离翻转价位（< −5%、−5〜0、0〜5、5〜10、10〜20、≥ 20%）、美股牛熊、威胁指数（日経：< 40、40〜60、60〜80、≥ 80 分）、
  健康度（< 50、50〜75、≥ 75；qbreak/macro_now.health_series，美股宽度没有历史不含）、量化状态层（0 / 0.75 / 1 倍）、
  宏观倍数（< 1 / = 1）、量比（五分位）。两半方向一致的才算「有规律」。
  另做消融（也只描述）：S0C2 去掉宏观层 / 去掉板块倾斜 / 去掉量化状态层，各少了多少。
二、候选（S0C2 其余设定不变；规则事先写死，不拟合）
  C1 量比优先：同一天名额不够时，先买信号当天量比（成交量 ÷ 20 日均量）大的（现在是按代码顺序）；
  C2 美股熊市时，日本个股的新仓减半（美股牛熊现在只管 1655）；
  C3 日経离翻转价位 ±5% 以内时，新仓减半（牛熊快要变的时候少下注）；
  C4 健康度 < 50 分时，新仓减半；
  C5 = C1 + C2 + C3 + C4 一起。
  状态都用信号日收盘时已知的值（日本收盘 + 美国收盘之后决策，下一交易日 09:00 成交）。
三、判定（事先写定）：20 年 Calmar ≥ 现行 + 0.05，且两半（2006-10〜2015-12 / 2016-01〜）Calmar 都不低于现行，
  且 20 年最大回撤不比现行深 2 pp 以上，且近 5 年 Calmar 不低于现行 → 通过；多个通过取 20 年 Calmar 最高的。
  通过只是提议：先进前向记录（另行登记），模拟盘改不改由用户确认；没有通过 → 维持现行的搭配。
四、局限：同一段历史上已经做过很多研究（多重比较），所以规则事先写死、门槛不放宽；股票池是现在的成分；回测的一手按复权价；税前。
登记前做过的检查：tests/test_combo_study.py（离翻转价位的距离、状态 → 下一交易日成交的系数不看未来、量比优先的分数、分组统计、判定）。
输出：var/out/combo_study.md / .json
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
import adaptive_study as AD                                                  # noqa: E402
import capital_study as CS                                                   # noqa: E402
import earnings_study as ES                                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

W20, SPLIT = "2006-10-01", "2016-01-01"
NEAR_PCT, HEALTH_LOW, HALF = 5.0, 50.0, 0.5
CALMAR_UP, DD_TOL = 0.05, 2.0
CANDS = {"C1": "C1 量比优先", "C2": "C2 美股熊市 → 日本个股新仓减半", "C3": "C3 日経离翻转价位 ±5% 内 → 新仓减半",
         "C4": "C4 健康度 < 50 → 新仓减半", "C5": "C5 = C1 + C2 + C3 + C4"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def flip_distance(close: pd.Series, bear: pd.Series, L: int = 250, b: float = 0.03) -> pd.Series:
    """离翻转价位的距离（%）：牛市 = 收盘 ÷（L 日线 × (1 − b)）− 1（正 = 还有余地）；熊市 = 收盘 ÷（L 日线 × (1 + b)）− 1（负）。"""
    c = close.astype(float)
    ma = c.rolling(L).mean()
    br = bear.reindex(c.index).ffill().fillna(False).astype(bool)
    level = np.where(br, ma * (1 + b), ma * (1 - b))
    return (c / level - 1) * 100


def fill_scale(factor: pd.Series, g: pd.DatetimeIndex) -> pd.Series:
    """信号日收盘时的系数 → 下一交易日（g 上的下一天）成交的新仓系数；没有值 = 1。"""
    f = factor.sort_index()
    f = f.reindex(f.index.union(g)).ffill().reindex(g)
    return f.shift(1).fillna(1.0)


def asof_values(s: pd.Series, dates) -> np.ndarray:
    """每个日期（可以重复）当时最新的值（≤ 该日，向前填）。"""
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="last")]
    u = pd.DatetimeIndex(pd.unique(pd.DatetimeIndex(dates)))
    v = s.reindex(s.index.union(u)).ffill()
    return v.reindex(pd.DatetimeIndex(dates)).to_numpy()


def vol_prio(ind: dict) -> dict:
    """C1：(代码, 信号日) → 当天的量比。"""
    out = {}
    for t, df in ind.items():
        e = df["entry"].astype(bool).to_numpy()
        if "vol_ratio" not in df.columns or not e.any():
            continue
        v = df["vol_ratio"].to_numpy(float)
        for d, x in zip(df.index[e], v[e]):
            if np.isfinite(x):
                out[(t, d)] = float(x)
    return out


def bucket_table(T: pd.DataFrame, col: str, edges=None, labels=None, halves=((W20, "2015-12-31"), (SPLIT, None))) -> list[dict]:
    """按一个状态列分组：每组在前半 / 后半的笔数、胜率 %、每笔期望 %。edges 给了就按区间分，否则按原值分。"""
    x = T[col]
    if edges is not None:
        grp = pd.cut(x.astype(float), edges, labels=labels, right=False)
    else:
        grp = x
    rows = []
    for g in (labels if labels is not None else sorted(grp.dropna().unique())):
        row = {"group": str(g)}
        for i, (a, b) in enumerate(halves, 1):
            m = (grp == g) & (T["sig_date"] >= pd.Timestamp(a))
            if b:
                m &= T["sig_date"] <= pd.Timestamp(b)
            s = T[m]
            row[f"n{i}"] = int(len(s))
            row[f"win{i}"] = round(float(s["win"].mean()) * 100, 1) if len(s) else None
            row[f"exp{i}"] = round(float(s["net"].mean()), 3) if len(s) else None
        rows.append(row)
    return rows


def summarize(eq: pd.Series) -> dict:
    last5 = (eq.dropna().index[-1] - pd.DateOffset(years=5)).strftime("%Y-%m-%d") if len(eq.dropna()) else None
    return {"all": CS.seg_stats(eq), "h1": CS.seg_stats(eq, W20, SPLIT), "h2": CS.seg_stats(eq, SPLIT), "w5": CS.seg_stats(eq, last5)}


def _c(x):
    return -9.0 if x is None else float(x)


def decide(R: dict, base: dict) -> dict:
    per, ok = {}, []
    for k in CANDS:
        if k not in R:
            continue
        r, f = R[k], []
        if _c(r["all"]["calmar"]) < _c(base["all"]["calmar"]) + CALMAR_UP:
            f.append(f"20 年 Calmar {r['all']['calmar']} < 现行 {base['all']['calmar']} + {CALMAR_UP}")
        for h, lab in (("h1", "前半"), ("h2", "后半"), ("w5", "近 5 年")):
            if _c(r[h]["calmar"]) < _c(base[h]["calmar"]):
                f.append(f"{lab} Calmar {r[h]['calmar']} < 现行 {base[h]['calmar']}")
        if r["all"]["dd"] is None or base["all"]["dd"] is None or r["all"]["dd"] < base["all"]["dd"] - DD_TOL:
            f.append(f"20 年最大回撤 {r['all']['dd']}% 比现行 {base['all']['dd']}% 深 {DD_TOL} pp 以上")
        per[k] = f
        if not f:
            ok.append((_c(r["all"]["calmar"]), k))
    return {"per": per, "best": max(ok)[1] if ok else None}


def main() -> int:
    from qbreak import factors as F
    from qbreak import macro_now as MN
    from qbreak import threat as TH
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.macro import features_at, features_frame, load_macro_series, macro_mult
    from qbreak.regime import quant_regime_series
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/combo_study.py", "scripts/adaptive_study.py", "scripts/capital_study.py",
                            "qbreak/macro_now.py", "qbreak/threat.py", "qbreak/macro.py", "qbreak/regime.py", "qbreak/unified.py",
                            "qbreak/strategy.py"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    ind = dict(IndicatorCache(data_n).all(p))
    run = AD.make_runner(data_n)
    B = run(ind, p)
    base = summarize(B["equity"])
    g = B["equity"].index
    idx, bear = run.ctx["idx"], run.ctx["bear"]
    jp_close = idx["JP"]["Close"].astype(float)
    dist = flip_distance(jp_close, bear["JP"])
    ti = TH.load_inputs()
    built = TH.build(ti)
    thr = {m: built[m][0] for m in built}
    frame = features_frame(load_macro_series(d21))
    try:
        hy = F.fred("BAMLH0A0HYM2") * 100
    except Exception:                                                        # noqa: BLE001
        hy = None
    H = MN.health_series(frame, jp_close, ti["jgb"], hy, thr)
    qr = quant_regime_series(idx["JP"])
    mm = pd.Series({d: macro_mult(features_at(frame, d), None, "JP")[0] for d in jp_close.index[jp_close.index >= "2006-01-01"]})
    print(f"准备 {time.time() - t0:.0f}s", flush=True)

    # 一、描述：独立交易 × 信号日的状态
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    T = ES.outcomes(ind, p, bt)
    T = T[T["sig_date"] >= pd.Timestamp(W20)].reset_index(drop=True)
    at = lambda s: asof_values(s, T["sig_date"])                              # noqa: E731
    T["jp_state"] = np.where(at(bear["JP"].astype(float)) > 0.5, "熊", "牛")
    T["us_state"] = np.where(at(bear["US"].astype(float)) > 0.5, "熊", "牛")
    T["dist"] = at(dist)
    T["threat_jp"] = at(thr["JP"])
    T["health"] = at(H["score"])
    T["qr"] = at(qr)
    T["macro"] = np.where(at(mm) < 1, "< 1（有触发）", "= 1")
    T["vol_ratio"] = [float(ind[t]["vol_ratio"].get(d, np.nan)) for t, d in zip(T["ticker"], T["sig_date"])]
    T["win"] = T["win"].astype(float)
    q = T["vol_ratio"].quantile([0.2, 0.4, 0.6, 0.8]).tolist()
    desc = {"日経牛熊": bucket_table(T, "jp_state"), "美股牛熊": bucket_table(T, "us_state"),
            "离翻转价位（%）": bucket_table(T, "dist", [-1e9, -5, 0, 5, 10, 20, 1e9], ["< −5", "−5〜0", "0〜5", "5〜10", "10〜20", "≥ 20"]),
            "威胁指数 日経（分）": bucket_table(T, "threat_jp", [-1, 40, 60, 80, 101], ["< 40", "40〜60", "60〜80", "≥ 80"]),
            "健康度（分）": bucket_table(T, "health", [-1, 50, 75, 101], ["< 50", "50〜75", "≥ 75"]),
            "量化状态层（倍）": bucket_table(T, "qr"), "宏观倍数": bucket_table(T, "macro"),
            "量比（五分位）": bucket_table(T, "vol_ratio", [-1e9, *q, 1e9], ["最低 1/5", "2", "3", "4", "最高 1/5"])}
    print(f"描述 {len(T)} 笔，{time.time() - t0:.0f}s", flush=True)

    # 消融（描述）
    abl = {}
    for k, lay in (("去掉宏观层", (False, True, True)), ("去掉板块倾斜", (True, False, True)), ("去掉量化状态层", (True, True, False))):
        abl[k] = summarize(run(ind, p, layers=lay)["equity"])

    # 二、候选
    us_bear = bear["US"].astype(float)
    s2 = fill_scale(pd.Series(np.where(us_bear > 0.5, HALF, 1.0), index=us_bear.index), g)
    s3 = fill_scale(pd.Series(np.where(dist.abs() < NEAR_PCT, HALF, 1.0), index=dist.index).where(dist.notna(), 1.0), g)
    s4 = fill_scale(pd.Series(np.where(H["score"] < HEALTH_LOW, HALF, 1.0), index=H.index).where(H["score"].notna(), 1.0), g)
    pr = vol_prio(ind)
    R, info = {}, {}
    for k, kw in (("C1", {"prio": pr}), ("C2", {"scale": s2}), ("C3", {"scale": s3}), ("C4", {"scale": s4}),
                  ("C5", {"prio": pr, "scale": s2 * s3 * s4})):
        r = run(ind, p, **kw)
        R[k] = summarize(r["equity"])
        info[k] = {"trades": r["trades"], "win": r["win"]}
        print(k, R[k]["all"], f"{time.time() - t0:.0f}s", flush=True)
    share = {"C2": float((s2 < 1).mean()), "C3": float((s3 < 1).mean()), "C4": float((s4 < 1).mean())}
    V = decide(R, base)
    report(base, {"trades": B["trades"], "win": B["win"]}, R, info, share, V, desc, abl, len(T), head, t0)
    return 0


def report(base, binfo, R, info, share, V, desc, abl, n_tr, head, t0) -> None:
    fa = lambda v, f="{:.3f}": "—" if v is None else f.format(v)                     # noqa: E731
    row = lambda name, r, i: (f"| {name} | {fa(r['all']['cagr'], '{:.2f}')}% / {fa(r['all']['dd'], '{:.2f}')}% / {fa(r['all']['calmar'])} | "  # noqa: E731
                              f"{fa(r['h1']['calmar'])} / {fa(r['h2']['calmar'])} | {fa(r['w5']['calmar'])} | {i['trades']} 笔 / {fa(i['win'], '{:.1f}')}% |")
    say(f"# 各层怎么搭配：买点 × 牛熊距离 × 新仓倍数 × 宏观 × 威胁 × 健康度（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say("规则见 scripts/combo_study.py 开头（先提交后运行）。")
    say("\n## 一、按当时的状态分组（日経225 股票池各自独立的突破交易，" + f"{n_tr} 笔；前半 2006-10〜2015-12 / 后半 2016〜）")
    for name, rows in desc.items():
        say(f"\n**{name}**\n")
        say("| 组 | 前半 笔数 / 胜率 / 每笔 | 后半 笔数 / 胜率 / 每笔 |")
        say("|---|---|---|")
        for r in rows:
            say(f"| {r['group']} | {r['n1']} 笔 / {fa(r['win1'], '{:.1f}')}% / {fa(r['exp1'], '{:+.2f}')}% | "
                f"{r['n2']} 笔 / {fa(r['win2'], '{:.1f}')}% / {fa(r['exp2'], '{:+.2f}')}% |")
    say("\n## 消融（S0C2，只描述）")
    say("| 去掉哪一层 | 20 年 年化 / 回撤 / Calmar | 前半 / 后半 Calmar | 近 5 年 Calmar |")
    say("|---|---|---|---|")
    say(f"| （现行，全部都有） | {fa(base['all']['cagr'], '{:.2f}')}% / {fa(base['all']['dd'], '{:.2f}')}% / {fa(base['all']['calmar'])} | "
        f"{fa(base['h1']['calmar'])} / {fa(base['h2']['calmar'])} | {fa(base['w5']['calmar'])} |")
    for k, r in abl.items():
        say(f"| {k} | {fa(r['all']['cagr'], '{:.2f}')}% / {fa(r['all']['dd'], '{:.2f}')}% / {fa(r['all']['calmar'])} | "
            f"{fa(r['h1']['calmar'])} / {fa(r['h2']['calmar'])} | {fa(r['w5']['calmar'])} |")
    say("\n## 二、候选（S0C2）")
    say("| 方案 | 20 年 年化 / 回撤 / Calmar | 前半 / 后半 Calmar | 近 5 年 Calmar | 个股笔数 / 胜率 |")
    say("|---|---|---|---|---|")
    say(row("现行", base, binfo))
    for k in CANDS:
        if k in R:
            say(row(CANDS[k], R[k], info[k]))
    say(f"\n减半生效的交易日比例：C2 {share['C2'] * 100:.1f}%、C3 {share['C3'] * 100:.1f}%、C4 {share['C4'] * 100:.1f}%")
    say("\n## 三、判定（20 年 Calmar ≥ 现行 + 0.05、两半与近 5 年都不低于现行、20 年回撤不深 2 pp 以上）")
    for k, f in V["per"].items():
        say(f"- {CANDS[k]}：{'通过' if not f else '不通过（' + '；'.join(f) + '）'}")
    say(f"\n**提议：{CANDS[V['best']]}**（先进前向记录，模拟盘改不改由用户确认）" if V["best"] else "\n**没有搭配明显好于现行 → 维持现行。**")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "combo_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "base": base, "results": R, "info": info, "share": share, "decision": V,
                                              "describe": desc, "ablation": abl}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
