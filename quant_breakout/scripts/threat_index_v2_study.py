"""threat_index_v2_study.py — 威胁指数 v2：加更多直接因素 + 四种合成方式，能否更准（事先写定，先提交后运行，结果出来不改规则）。

用户问（2026-09-25）：调整威胁指数算法令其更准确，结合更多直接影响因子，横展开因子。
因素（qbreak/threat.py；方向统一为越高越危险；只用当时已公布的数据）：
  v1 的 8 个（日経 10 个）+ 新增 14 个：金融条件 NFCI、金融压力 STLFSI、初请失业金 13 周变化、10Y−2Y 倒挂、2 年美债 60 日变化、
  美联储一年加息幅度、美元指数 60 日变化、SKEW、VIX / VIX3M、MOVE、铜金比 60 日变化（取负）、离一年高点跌幅、跌破 200 日线幅度、
  近 20 日跌幅；日経另加日元 20 日波动、日银一年加息幅度（美股 22 个、日経 26 个）。
合成方式：
  A0 现行 v1（8 / 10 个因素等权）          A1 全部因素等权平均
  A2 训练期选因素：1995–2010 单因素 AUC ≥ 0.55 的因素等权平均（各市场分别选）
  A3 极端计数：处在各自 80 分位以上的因素占比    A4 滚动逻辑回归：每年初只用已知答案的样本重估（L2 = 1），输出预测概率
目标：之后 60 个交易日内最低收盘比当天跌 ≥10%（另报 ≥15%）。评估 1995-01～，前半 1995–2010 / 后半 2011–
  （A2 / A4 的前半是训练期，只看后半）。
判定（事先规则）：A1～A4 中「后半 AUC 两个市场均值」最高者，若它的后半 AUC 在美股、日経都比 A0 高 ≥ 0.03 → 替换 A0；否则保留 A0。
  替换后重跑交易用法（阈值改为该指数自身的历史 90 / 80 分位）：O1 美股 → 1655 清仓；O2 日本 → 个股新仓 ×0.5；O3 两者；
  采用条件同 threat_index_study（对应市场后半 AUC ≥ 0.65；组合 S0C2 20 年 Calmar ≥ 现行 + 0.03、年化 ≥ 现行 − 0.5pp、
  回撤不深于现行）。
另报：每个因素单独的 AUC（前半 / 后半）、各方式的 ≥15% 下跌 AUC、历次 ≥10% 下跌之前 60 日内是否到过该指数的 90 分位。
输出 var/out/threat_index_v2_study.md / .json；替换时更新 var/threat_index.json（日报用）。
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import factors, paths                                            # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak.bullbear import date_phases                                      # noqa: E402
from threat_index_study import hysteresis, run_s0c2, s0c2_setup             # noqa: E402

EVAL0, SPLIT = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def yf_close(sym: str) -> pd.Series:
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    h = yf.Ticker(sym).history(period="max", auto_adjust=True)
    h.index = h.index.tz_localize(None).normalize()
    c = h[~h.index.duplicated(keep="last")]["Close"]
    return c[c > 0]


def load_extra() -> dict:
    x = {k: factors.fred(k) for k in ("NFCI", "STLFSI4", "ICSA", "T10Y2Y", "DGS2", "DFF")}
    x["JPCALL"] = factors.fred("IRSTCI01JPM156N")
    x["VIX"] = factors.fred("VIXCLS")
    for k, sym in (("DXY", "DX-Y.NYB"), ("SKEW", "^SKEW"), ("VIX3M", "^VIX3M"), ("MOVE", "^MOVE"), ("HG", "HG=F"), ("GC", "GC=F")):
        x[k] = yf_close(sym)
    return x


def features(d: dict, x: dict) -> dict:
    r = d["raw"]
    out = {}
    us_days = d["spx"].index[d["spx"].index >= "1990-01-01"]
    base_us = TH.raw_features(us_days, d["spx"], r["VIXCLS"], r["BAA10Y"], r["DGS10"], r["DGS3MO"], r["DCOILWTICO"], r["UNRATE"])
    out["US"] = (TH.raw_features_v2(base_us, us_days, d["spx"], x), d["spx"].reindex(us_days))
    jp_days = d["n225"].index[d["n225"].index >= "1990-01-01"]
    m = {k: TH.us_asof_for_jp(r[k], jp_days) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")}
    fxj = TH.us_asof_for_jp(d["fx"], jp_days)
    base_jp = TH.raw_features(jp_days, d["n225"], m["VIXCLS"], m["BAA10Y"], m["DGS10"], m["DGS3MO"], m["DCOILWTICO"],
                              r["UNRATE"], usdjpy=fxj, jgb10=d["jgb"].shift(1))
    xj = dict(x)
    for k in ("T10Y2Y", "DGS2", "DFF", "DXY", "SKEW", "VIX", "VIX3M", "MOVE", "HG", "GC"):
        xj[k] = TH.us_asof_for_jp(x[k], jp_days)
    out["JP"] = (TH.raw_features_v2(base_jp, jp_days, d["n225"], xj, usdjpy=fxj, jp=True), d["n225"].reindex(jp_days))
    return out


def auc_split(s: pd.Series, ev: pd.Series) -> dict:
    m = (s.index >= EVAL0) & s.notna() & ev.notna()
    a, e = s[m], ev[m]
    return {"all": TH.auc(a, e), "h1": TH.auc(a[a.index < SPLIT], e[a.index < SPLIT]),
            "h2": TH.auc(a[a.index >= SPLIT], e[a.index >= SPLIT])}


def main() -> int:
    t0 = time.time()
    d = TH.load_inputs()
    x = load_extra()
    F = features(d, x)
    say(f"# 威胁指数 v2：更多直接因素 + 四种合成方式（{pd.Timestamp.today().date()}；数据截至 S&P500 {d['spx'].index[-1].date()} / "
        f"日経 {d['n225'].index[-1].date()}；{time.time() - t0:.0f}s）")
    out, idx_all = {}, {}
    for m in ("US", "JP"):
        raw, close = F[m]
        cols = TH.US_V2 if m == "US" else TH.JP_V2
        v1 = TH.US_COLS if m == "US" else TH.JP_COLS
        pct = pd.DataFrame({c: TH.expanding_pct(raw[c]) for c in cols})
        fdd = TH.forward_drawdown(close, 60)
        ev10 = (fdd <= -0.10).astype(float).where(fdd.notna())
        ev15 = (fdd <= -0.15).astype(float).where(fdd.notna())
        single = {c: auc_split(pct[c], ev10) for c in cols}
        sel = [c for c in cols if (single[c]["h1"] or 0) >= 0.55]
        ok_half = lambda p: p.notna().sum(axis=1) >= max(1, p.shape[1] // 2)            # noqa: E731
        cand = {"A0": (pct[v1].mean(axis=1) * 100).where(ok_half(pct[v1])),
                "A1": (pct.mean(axis=1) * 100).where(ok_half(pct)),
                "A2": (pct[sel].mean(axis=1) * 100).where(ok_half(pct[sel])) if sel else pd.Series(np.nan, index=pct.index),
                "A3": TH.tail_share(pct),
                "A4": TH.walkforward_logit(pct, ev10)}
        idx_all[m] = cand
        res = {k: {"ev10": auc_split(v, ev10), "ev15": auc_split(v, ev15)} for k, v in cand.items()}
        tp, _ = date_phases(close.dropna(), 0.10, 0.10)
        peaks = [p for p in tp[tp["kind"] == "peak"]["date"] if p >= EVAL0]
        for k, v in cand.items():
            q90 = TH.expanding_pct(v, min_n=750) >= 0.9
            hit = sum(bool(q90.loc[:p].tail(61).any()) for p in peaks)
            res[k]["warn_hits"] = [hit, len(peaks)]
        out[m] = {"single": single, "selected_A2": sel, "cands": res}
        say(f"\n## {'S&P500' if m == 'US' else '日経225'}：各因素单独的 AUC（之后 60 日跌 ≥10%；前半 1995–2010 / 后半 2011–）")
        say("| 因素 | 前半 | 后半 | A2 选入 |")
        say("|---|---|---|---|")
        for c in sorted(cols, key=lambda c: -(single[c]["h2"] or 0)):
            say(f"| {TH.LABELS[c]} | {single[c]['h1'] if single[c]['h1'] is None else round(single[c]['h1'], 3)} | "
                f"{single[c]['h2'] if single[c]['h2'] is None else round(single[c]['h2'], 3)} | {'是' if c in sel else ''} |")
        say("\n| 合成方式 | 跌≥10% AUC 前半 / 后半 | 跌≥15% AUC 前半 / 后半 | 下跌前 60 日内到过自身 90 分位 |")
        say("|---|---|---|---|")
        lab = {"A0": "A0 现行 v1", "A1": "A1 全部等权", "A2": "A2 训练期选因素", "A3": "A3 极端计数", "A4": "A4 滚动逻辑回归"}
        for k, r in res.items():
            f10, f15 = r["ev10"], r["ev15"]
            say(f"| {lab[k]} | {fmt(f10['h1'])} / {fmt(f10['h2'])} | {fmt(f15['h1'])} / {fmt(f15['h2'])} | "
                f"{r['warn_hits'][0]} / {r['warn_hits'][1]} |")

    # ── 判定 ──
    mean_h2 = {k: np.mean([out[m]["cands"][k]["ev10"]["h2"] or 0 for m in ("US", "JP")]) for k in ("A1", "A2", "A3", "A4")}
    best = max(mean_h2, key=mean_h2.get)
    beats = all((out[m]["cands"][best]["ev10"]["h2"] or 0) >= (out[m]["cands"]["A0"]["ev10"]["h2"] or 0) + 0.03
                for m in ("US", "JP"))
    pick = best if beats else "A0"
    out["pick"], out["best_challenger"], out["mean_h2"] = pick, best, mean_h2
    say(f"\n判定（事先规则）：挑战者中后半 AUC 均值最高的是 {best}（{mean_h2[best]:.3f}）；"
        f"{'两个市场都比 A0 高 ≥0.03 → 替换' if beats else '没有在两个市场都比 A0 高 0.03 → 保留 A0（v1）'}")

    if pick != "A0":
        S = s0c2_setup()
        base = run_s0c2(S, S["bear"]["US"], S["em_jp"])
        iu, ij = idx_all["US"][pick], idx_all["JP"][pick]
        pu, pj = TH.expanding_pct(iu, 750) * 100, TH.expanding_pct(ij, 750) * 100
        stress = hysteresis(pu, 90, 80).reindex(S["bear"]["US"].index).fillna(False).astype(bool)
        o1 = (S["bear"]["US"] | stress).astype(bool)
        g = S["grid"]
        hot = (pj.reindex(g.union(pj.index)).ffill().reindex(g) >= 90).shift(1).fillna(False)
        em2 = S["em_jp"].mul(np.where(hot.to_numpy(bool), 0.5, 1.0), axis=0)
        port = {"now": base, "O1": run_s0c2(S, o1, S["em_jp"]), "O2": run_s0c2(S, S["bear"]["US"], em2), "O3": run_s0c2(S, o1, em2)}
        out["portfolio"] = port
        need = {"O1": ["US"], "O2": ["JP"], "O3": ["US", "JP"]}
        ok = []
        for k in ("O1", "O2", "O3"):
            a_ok = all((out[m]["cands"][pick]["ev10"]["h2"] or 0) >= 0.65 for m in need[k])
            r = port[k]
            p_ok = ((r["w20_calmar"] or 0) >= (base["w20_calmar"] or 0) + 0.03 and r["w20_cagr"] >= base["w20_cagr"] - 0.5
                    and r["w20_dd"] >= base["w20_dd"])
            if a_ok and p_ok:
                ok.append(k)
            say(f"- {k}：20 年 {r['w20_cagr']}% / {r['w20_dd']:.2f}%（现行 {base['w20_cagr']}% / {base['w20_dd']:.2f}%）；"
                f"AUC 条件 {'满足' if a_ok else '不满足'}，组合条件 {'满足' if p_ok else '不满足'}")
        out["trade_pick"] = max(ok, key=lambda k: port[k]["w20_calmar"] or 0) if ok else None
        say(f"交易用法判定：{out['trade_pick'] or '不用于交易，只在日报展示'}")
    say(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "threat_index_v2_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


def fmt(v):
    return "—" if v is None else f"{v:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
