"""jp_watch_review.py — 日経前瞻观察的复核（规则 2026-09-25 事先写定，之后不改）。

用户要求（2026-09-25）：日経也做和美股「金银比 + 商品波动」同样的前瞻观察。
取舍：美股那一对在日経历史上无效（金银比两段 AUC 0.594 / 0.504、商品波动 0.525 / 0.468）→ 按同一挑法（前后两段都有效），
  用因子调查（scripts/threat_factor_survey.py）里加进现行模型后日経两段都有增益的 8 个因素（qbreak/survey.py JP_WATCH；
  停更的 OECD 中国先行指数除外）：新兴市场股相对美股下跌、美国 10 年实际利率急升、短观大企业制造业景气下降、
  短观中小企业非制造业景气下降、初请失业金上升、等权相对市值加权下跌、日银一年加息幅度、日本企业物价同比加速。
观察分：Wj = 这 8 个因素历史百分位的平均（0–100）；对照 W2 = 金银比 + 商品波动（与美股同一公式，按日経交易日算）；
  各自在自己历史里 ≥80 分位 = 预警、≥90 分位 = 警戒。只展示，不参与交易。
记录：每次日报运行把最近 5 个日本交易日写进 var/out/jp_watch_forward.csv（已记日期保留最早值，只补漏记的日子），同时记现行 A0（日経）与其百分位。
检验（只用之后 60 个交易日已经走完的记录；事件 = 日経之后 60 个交易日内最低收盘比当天跌 ≥10%）：
  与美股同一套判定（qbreak/threat.py watch_decision / warn80_decision，只在前瞻期内 ≥3 次 ≥10% 下跌、≥500 天结果已知之后）：
  90 分位：AUC ≥ 0.65、比 A0 高 ≥ 0.05、半数以上下跌事前警戒 → 建议加进日报的日経威胁指数（需用户确认）；AUC < 0.55 → 建议停止观察；
  80 分位：≥2/3 下跌事前到过 80、预警后发生率 ≥ 基准 1.5 倍、且不低于 A0 的 80 分位线 → 建议标成日経预警（需用户确认）。
  Wj 为主、W2 为对照，分别判定。不论结论如何都不自动改交易规则。
披露：8 个因素是看过 2011 年后结果才挑的（两段都有增益），下面的「样本内参考」偏乐观，只作对照。
每季度复核时运行（例行任务），输出 var/out/jp_watch_review.md / .json。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import survey as SV                                              # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak.bullbear import date_phases                                      # noqa: E402

EVAL0, SPLIT = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01")
NAMES = {"Wj": "Wj（日経自己的 8 个因素）", "W2": "W2（金银比 + 商品波动，对照）", "A0": "A0 现行威胁指数"}


def fmt(v):
    return "—" if v is None or v != v else f"{v:.3f}"


def in_sample(d: dict) -> dict:
    """样本内参考（偏乐观）：用全历史重算 Wj / W2 / A0。"""
    F = TH.build_all(d, TH.load_extra_all())
    raw_ex, close = F["JP"]
    feats = pd.concat([raw_ex, SV.features(raw_ex.index, SV.load_raw(), jp_market=True)], axis=1)
    feats = feats.loc[:, ~feats.columns.duplicated()]
    cols = [c for c in SV.JP_WATCH if c in feats]
    pct = pd.DataFrame({c: TH.expanding_pct(feats[c]) for c in dict.fromkeys(cols + ["gold_silver", "commod_vol"] + TH.JP_COLS)})
    series = {"Wj": TH._eq(pct[cols]), "W2": pct[["gold_silver", "commod_vol"]].mean(axis=1, skipna=False) * 100,
              "A0": TH._eq(pct[TH.JP_COLS])}
    fdd = TH.forward_drawdown(close, 60)
    tp, _ = date_phases(close.dropna(), 0.10, 0.10)
    peaks = [p for p in tp[tp["kind"] == "peak"]["date"] if p >= EVAL0]
    ev10 = (fdd <= -0.10).astype(float).where(fdd.notna())
    out = {}
    for name, s in series.items():
        r = {}
        for lvl in (0.10, 0.15):
            ev = (fdd <= -lvl).astype(float).where(fdd.notna())
            m = (s.index >= EVAL0) & s.notna() & ev.notna()
            a, e = s[m], ev[m]
            r[f"auc{int(lvl * 100)}"] = [TH.auc(a[a.index < SPLIT], e[a.index < SPLIT]), TH.auc(a[a.index >= SPLIT], e[a.index >= SPLIT])]
        pc = TH.expanding_pct(s)
        for thr, tag in ((0.9, "hits90"), (0.8, "hits80")):
            q = pc >= thr
            r[tag] = [sum(bool(q.loc[:p].tail(61).any()) for p in peaks), len(peaks)]
        m = (pc.index >= EVAL0) & ev10.notna()
        base = float(ev10[m].mean())
        on = m & (pc >= 0.8)
        r["lift80"] = round(float(ev10[on].mean()) / base, 2) if on.any() and base else None
        out[name] = r
    return out


def main() -> int:
    t0 = time.time()
    d = TH.load_inputs()
    lines = [f"# 日経前瞻观察：Wj（日経自己的 8 个因素）/ 对照 W2（金银比 + 商品波动）（复核 {pd.Timestamp.today().date()}；"
             f"日経数据截至 {d['n225'].index[-1].date()}）"]
    out: dict = {}
    fp_log = paths.out_dir() / "jp_watch_forward.csv"
    if fp_log.exists() and len(pd.read_csv(fp_log)):
        r = TH.watch_review_generic(pd.read_csv(fp_log), d["n225"], {"Wj": "Wj_pct", "W2": "W2_pct"}, market="日経")
        out["forward"] = r
        lines.append(f"\n## 前瞻（{r['first']} 起，{r['days']} 天，其中结果已知 {r['known']} 天、事件日 {r['event_days']} 天；"
                     f"A0 的 AUC {fmt(r['auc_A0'])}）")
        for sc, x in r["scores"].items():
            eps = x["episodes"]
            lines += [f"- {NAMES[sc]}：AUC {fmt(x['auc'])}；警戒（≥90）{x['days90']} 天、之后下跌比例 {fmt(x['hit90'])}；"
                      f"预警（≥80）{x['days80']} 天、比例 {fmt(x['hit80'])}；前瞻期内 ≥10% 下跌 {len(eps)} 次"
                      + (f"（事前警戒 {sum(e['alert90'] for e in eps)}、预警 {sum(e['warn80'] for e in eps)}）" if eps else ""),
                      f"  判定（事先规则）：90 分位 —— {x['decision90']}；80 分位 —— {x['decision80']}"]
    else:
        lines.append("\n还没有前瞻记录（第一次日报运行后开始）。")
    try:
        ins = in_sample(d)
        out["in_sample"] = ins
        lines += ["\n## 样本内参考（偏乐观：Wj 的因素是看过 2011 年后结果才挑的，不作判定依据）",
                  "| 指标 | 跌≥10% AUC 1995–2010 / 2011– | 跌≥15% AUC | 下跌前 60 日内到过 90 分位 | 到过 80 分位 | ≥80 分位日的下跌发生率 / 基准 |",
                  "|---|---|---|---|---|---|"]
        for name in ("Wj", "W2", "A0"):
            x = ins[name]
            lines.append(f"| {NAMES[name]} | {fmt(x['auc10'][0])} / {fmt(x['auc10'][1])} | {fmt(x['auc15'][0])} / {fmt(x['auc15'][1])} | "
                         f"{x['hits90'][0]} / {x['hits90'][1]} | {x['hits80'][0]} / {x['hits80'][1]} | {x['lift80']} 倍 |")
    except Exception as e:                                               # noqa: BLE001
        lines.append(f"\n（样本内参考计算失败：{e}）")
    lines.append(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "jp_watch_review"
    Path(f"{fp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
