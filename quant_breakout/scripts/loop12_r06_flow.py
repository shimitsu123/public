"""loop12_r06_flow.py — 第十二个研究循环第 6 轮：信用规制 / 业种空売り比率（路线 J）+ 宏观顺风度（路线 A / B）（规则 scripts/research_loop12.py）。
（2026-10-12 登记；先提交后只运行一次。看过第 1〜5 轮之后设计，但不是它们的变体；数据都是以前没用过的。）

  MAL〔选股·信用〕：J-Quants 信用取引規制 / 日々公表（markets/margin-alert）里，这只票有一条公表日在信号日之前 14 个日历日以内（不含信号日）→ 不买
       （交易所 / 証金认为过热的票；原因不分；路线 J）。
  SSS〔选股·空売り〕：这只票所属东证 33 业种（J-Quants 上市一览，最近一份早于信号日的月末快照）的空売り比率 =（价格规制有 + 无的空卖）÷（实卖 + 空卖）金额，
       信号日之前 20 个交易日的平均，处于这个业种之前 250 个交易日同样平均的 80 分位以上 → 不买（业种被大量做空；路线 J）。
  TWD〔选股·宏观顺风〕：顺风度 = Σ（个股对 美元日元 / 美 10 年利率 / WTI 的周敏感度 b_fx / b_us10 / b_wti（研究面板现成的，控制日経）
       × 信号日之前 13 周这个因子的累计周变化（combo_all_study.feature_base 的因子周表，同一单位））≤ 该年代信号的 20 分位 → 不买（宏观逆风；三个年代、路线 A / B；
       池子用对应年代的门槛；缺值不挡）。
登记前去掉 MAL（照实写）：接线核对只数个数 → 日経225 的 J 信号里只会多挡 1 个（大型股几乎不进日々公表），检验不出东西，不占做法名额。
都不是事后组合。第二关另行登记。运行：python scripts/loop12_r06_flow.py；--wiring。非投资建议。
"""
from __future__ import annotations

import argparse
import glob
import gzip
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402
import loop12_r01_fund as R1                                                 # noqa: E402
import research_loop12 as R12                                                # noqa: E402

ROUND = 6
IDS = ("SSS", "TWD")                                                      # MAL 登记前去掉（见开头）
FAMILY = {"MAL": "选股·信用", "SSS": "选股·空売り", "TWD": "选股·宏观顺风"}
OUT = "loop12_r06_flow"
ERA_OF = {"W": "E", "Jx": "J", "Zx": "Z"}
MAL_DAYS, SSS_N, SSS_LB, SSS_Q, TWD_W, TWD_Q = 14, 20, 250, 0.80, 13, 20


def _bulk(sub: str) -> pd.DataFrame:
    from qbreak import jq_data as JD
    fs = sorted(glob.glob(str(JD.bulk_dir() / sub / "**" / "*.csv.gz"), recursive=True))
    return pd.concat([pd.read_csv(io.BytesIO(gzip.decompress(open(f, "rb").read())), dtype=str) for f in fs], ignore_index=True)


def mal_gate(alerts: pd.DataFrame, tickers, dates) -> np.ndarray:
    by = {t: np.sort(g["pub"].to_numpy("datetime64[ns]")) for t, g in alerts.groupby("ticker")}
    out = []
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates)).to_numpy("datetime64[ns]")):
        x = by.get(str(t))
        if x is None:
            out.append(False)
            continue
        k = int(np.searchsorted(x, d, side="left")) - 1
        out.append(k >= 0 and (d - x[k]) <= np.timedelta64(MAL_DAYS, "D"))
    return np.array(out, bool)


def sector_pct() -> pd.DataFrame:
    """业种 × 日：之前 20 日平均空売り比率在这个业种之前 250 日里的分位（只用当天以前的；当天公布 → 信号日只用到前一天）。"""
    R = _bulk("markets/short-ratio")
    for c in ("SellExShortVa", "ShrtWithResVa", "ShrtNoResVa"):
        R[c] = pd.to_numeric(R[c], errors="coerce")
    R["r"] = (R["ShrtWithResVa"] + R["ShrtNoResVa"]) / (R["SellExShortVa"] + R["ShrtWithResVa"] + R["ShrtNoResVa"])
    P = R.pivot_table(index=pd.to_datetime(R["Date"]), columns="S33", values="r").sort_index()
    m = P.rolling(SSS_N, min_periods=SSS_N).mean()
    pct = m.rolling(SSS_LB, min_periods=120).apply(lambda x: (x[:-1] < x[-1]).mean() if np.isfinite(x[-1]) else np.nan, raw=True)
    return pct


def s33_of(tickers, dates) -> list:
    from qbreak import pit_data as PD
    snaps = {d: pd.read_csv(fp, dtype=str).set_index("Code")["S33"] for d, fp in PD.master_files().items()}
    keys = sorted(snaps)
    out = []
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates))):
        k = [x for x in keys if x < d]
        code = str(t).split(".")[0] + "0"
        out.append(snaps[k[-1]].get(code) if k else None)
    return out


def sss_gate(pct: pd.DataFrame, tickers, dates) -> np.ndarray:
    secs = s33_of(tickers, dates)
    out = []
    for s, d in zip(secs, pd.to_datetime(np.asarray(dates))):
        if s is None or s not in pct.columns:
            out.append(False)
            continue
        v = pct[s][pct.index < d].dropna()
        out.append(bool(len(v) and v.iloc[-1] >= SSS_Q))
    return np.array(out, bool)


def twd(X: pd.DataFrame, Fw: pd.DataFrame) -> np.ndarray:
    """X 有 date / b_fx / b_us10 / b_wti；Fw = 因子周表（fx / us10 / wti 的周变化）。"""
    cs = Fw[["fx", "us10", "wti"]].cumsum()
    out = []
    for r in X.itertuples(index=False):
        d = pd.Timestamp(r.date)
        k = cs.index.searchsorted(d, side="left") - 1
        if k - TWD_W < 0:
            out.append(np.nan)
            continue
        ch = cs.iloc[k] - cs.iloc[k - TWD_W]
        b = np.array([r.b_fx, r.b_us10, r.b_wti], float)
        out.append(float(np.nansum(b * ch.to_numpy(float))) if np.isfinite(b).all() else np.nan)
    return np.array(out, float)


def build(W: dict) -> dict:
    import combo_all_study as CS
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    import jq_extra_data as JX
    A = _bulk("markets/margin-alert")
    alerts = pd.DataFrame({"ticker": JX._tickers(A["Code"]), "pub": pd.to_datetime(A["PubDate"])}).dropna()
    pct = sector_pct()
    S = LC.signals(W, "J")
    XJx = LC.pool_x(W, "Jx")
    gJ = {"MAL": mal_gate(alerts, S["ticker"], S["date"]), "SSS": sss_gate(pct, S["ticker"], S["date"])}
    gP = {"MAL": mal_gate(alerts, XJx["ticker"], XJx["date"]), "SSS": sss_gate(pct, XJx["ticker"], XJx["date"])}
    B = CS.feature_base(SF.no_w2_params(load_params(market="JP")), None)
    Fw = B["X"]
    tw, cut, gT = {}, {}, {}
    for e in LC.ERAS:
        tw[e] = twd(LC.signals(W, e), Fw)
        cut[e] = float(np.nanpercentile(tw[e], TWD_Q))
        gT[e] = np.nan_to_num(tw[e], nan=np.inf) <= cut[e]
    gTP = {}
    for s in ("W", "Jx", "Zx"):
        if s in W["D"]:
            X = LC.pool_x(W, s)
            gTP[s] = np.nan_to_num(twd(X, Fw), nan=np.inf) <= cut[ERA_OF[s]]
    cov = {"twd": {e: int(np.isfinite(tw[e]).sum()) for e in LC.ERAS}}
    return {"gJ": gJ, "gP": gP, "gT": gT, "gTP": gTP, "cut": cut, "coverage": cov}


def wiring() -> int:
    W = LC.load()
    B = build(W)
    same = all(LC.run_b4(W, e, np.zeros(len(LC.signals(W, e)), bool)) == LC.run_b4(W, e) for e in LC.ERAS)
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    print(json.dumps({"same_as_b4": bool(same), "twd_cut": B["cut"], "coverage": B["coverage"],
                      "blocked_extra": {"MAL": int((B["gJ"]["MAL"] & ~tbf["J"]).sum()), "SSS": int((B["gJ"]["SSS"] & ~tbf["J"]).sum()),
                                        "TWD": {e: int((B["gT"][e] & ~tbf[e]).sum()) for e in LC.ERAS}},
                      "pool_blocked": {"MAL": int(B["gP"]["MAL"].sum()), "SSS": int(B["gP"]["SSS"].sum()), "TWD": {s: int(v.sum()) for s, v in B["gTP"].items()}}},
                     ensure_ascii=False, default=float))
    return 0 if same else 1


def stage_one() -> int:
    from qbreak import paths
    import loop12_r05_mix as R5
    t0 = time.time()
    code, dirty = R1.git_head()
    W = LC.load()
    B = build(W)
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    res = {"loop": 12, "round": ROUND, "ids": list(IDS), "family": FAMILY, "code": code, "dirty": dirty, "per_cut": 0.0, "twd_cut": B["cut"],
           "coverage": {"signals": int(len(LC.signals(W, "J"))), "per": 0, "fgr": 0}, "base": base, "cand": {}, "stage1": {}, "other": {}, "frac": {}}
    for k in ("SSS",):
        cand = dict(base)
        cand["J"] = LC.run_b4(W, "J", B["gJ"][k])
        other = LC.other_stocks(W, lambda s, X, _g=B["gP"][k]: _g if s == "Jx" else np.zeros(len(X), bool))
        res["cand"][k], res["other"][k] = cand, other
        res["frac"][k] = {"J": float((B["gJ"][k] & ~tbf["J"]).mean())}
        res["stage1"][k] = R12.stage1_j(cand["J"], base["J"], other.get("Jx"))
    cand = {e: LC.run_b4(W, e, B["gT"][e]) for e in LC.ERAS}
    other = LC.other_stocks(W, lambda s, X: B["gTP"].get(s, np.zeros(len(X), bool)))
    res["cand"]["TWD"], res["other"]["TWD"] = cand, other
    res["frac"]["TWD"] = {e: float((B["gT"][e] & ~tbf[e]).mean()) for e in LC.ERAS}
    res["stage1"]["TWD"] = R12.stage1_all(cand, base, other)
    res["seconds"] = round(time.time() - t0)
    R5.FAMILY.update(FAMILY)
    text = R5_render(res)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def R5_render(res: dict) -> str:
    f = R1._f
    L = [f"# 第十二个研究循环第 6 轮：业种空売り比率 / 宏观顺风度 SSS / TWD（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}）", ""]
    for k in ("SSS",):
        s, o = res["stage1"][k], res["other"][k].get("Jx") or {}
        d = s["d"]
        L.append(f"- **{k}**（{FAMILY[k]}，路线 J）：J Calmar 差 {f(d['calmar'], '{:+.3f}')}、胜率差 {f(d['win'], '{:+.2f}')} pp、每笔差 {f(d['mean'], '{:+.3f}')} pp、"
                 f"两半 {f(d['h1'], '{:+.3f}')} / {f(d['h2'], '{:+.3f}')}、多挡 {res['frac'][k]['J'] * 100:.1f}%；Jx 挡 {o.get('gone_n')} / {o.get('n')}、"
                 f"保留的胜率差 {f(o.get('dwin'), '{:+.2f}')} pp、每笔差 {f(o.get('dmean'), '{:+.3f}')} pp；JA {'✓' if s['routes']['JA']['ok'] else '✗'}、"
                 f"JB {'✓' if s['routes']['JB']['ok'] else '✗'} → **{'第一关全过' if s['ok'] else R12.FAIL1}**")
    s = res["stage1"]["TWD"]
    A, Bq, o = s["routes"]["A"], s["routes"]["B"], res["other"]["TWD"]
    L.append(f"- **TWD**（选股·宏观顺风，路线 A / B）：" + "、".join(
        f"{e} Calmar {f(res['base'][e]['calmar'])} → {f(res['cand']['TWD'][e]['calmar'])}、胜率 {f(res['base'][e]['win'], '{:.1f}')} → {f(res['cand']['TWD'][e]['win'], '{:.1f}')}%"
        for e in LC.ERAS) + f"；路线 A（合计 {f(A['sum'], '{:+.3f}')}）" + "、".join(f"{x} {'✓' if A[x] else '✗'}" for x in ("A1", "A2", "A3", "V4"))
        + f"；路线 B（胜率差 {f(Bq['dwin'], '{:+.2f}')} pp、每笔 {f(Bq['dmean'], '{:+.3f}')} pp）" + "、".join(f"{x} {'✓' if Bq[x] else '✗'}" for x in ("B1", "B2", "B3", "V4"))
        + "；" + "；".join(f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}、{f(o[x]['dwin'], '{:+.2f}')} pp、{f(o[x]['dmean'], '{:+.3f}')} pp" for x in ("W", "Jx", "Zx") if x in o)
        + f" → **{'第一关全过' if s['ok'] else R12.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
