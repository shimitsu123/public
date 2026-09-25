"""us_watch_review.py — 美股前瞻观察「金银比 + 商品波动」的复核（规则 2026-09-25 事先写定，之后不改）。

用户要求（2026-09-25）：对威胁指数 v3 里美股两个半段都有效的两个因素做前瞻观察。
为什么只能前瞻：这两个因素是在看过 2011 年后的结果之后挑出来的，用历史数据再检验一定偏乐观（下面的「样本内参考」只供对照）。
观察分（qbreak/threat.py us_watch_series）：
  金银比上升 = 黄金 / 白银（期货）60 日变化的历史百分位；商品波动 = S&P GSCI 20 日年化波动的历史百分位；
  W = 两者平均（0–100）；W_pct = W 在自己历史里的百分位，≥90 = 警戒。当天美国收盘后可算。
记录：每次日报运行把最近 5 个美国交易日的读数写进 var/out/us_watch_forward.csv（已记过的日期保留最早那次，只补漏记的日子），
  同时记现行威胁指数 A0 与其百分位作对照。第一条记录的日期即前瞻起点。
检验（只用之后 60 个交易日已经走完的记录；事件 = 之后 60 个交易日内最低收盘比当天跌 ≥10%）：
  主指标 AUC(W) 与同一期间的 AUC(A0)；辅助：前瞻期内每次 ≥10% 下跌（高点 → 回落 10% 确认）之前 60 个交易日内 W_pct 是否到过 90；
  警戒日之后真的发生下跌的比例。
判定（只在前瞻期内 ≥3 次 ≥10% 下跌、且 ≥500 天结果已知之后做）：
  AUC(W) ≥ 0.65、≥ AUC(A0) + 0.05、且 ≥ 一半的下跌事前有警戒 → 建议把 W 加进日报的美股威胁指数显示（需要用户确认）；
  AUC(W) < 0.55 → 建议停止观察；其他 → 继续观察。到 2029-09-25 仍不满足判定条件时，汇报现状请用户决定。
  不论结论如何都不自动改交易规则。
补登（2026-09-25，用户要求；此时前瞻记录只有 5 天、没有任何结果已知；上面 90 分位的规则不变）：
  另设 80 分位「预警」线（W_pct ≥ 80），与 90 分位「警戒」一起用同一份记录检验。同样在 ≥3 次下跌、≥500 天结果已知之后判定：
  ≥2/3 的下跌事前 60 个交易日内到过 80、预警日之后的下跌发生率 ≥ 前瞻期基准发生率的 1.5 倍、且事前预警比例不低于 A0 的 80 分位线
  → 建议在日报把 W ≥ 80 标成美股预警（需要用户确认）；否则维持观察。
  披露：提出 80 分位是因为样本内 90 分位警戒只在 27 次下跌中的 6 次之前出现（看过样本内结果），所以同样只能靠前瞻检验。
每季度复核时运行（例行任务），输出 var/out/us_watch_review.md / .json。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak.bullbear import date_phases                                      # noqa: E402

EVAL0, SPLIT = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01")


def fmt(v):
    return "—" if v is None else f"{v:.3f}"


def in_sample(d: dict, x: dict) -> dict:
    """样本内参考（偏乐观：因素是看过这段结果才挑的）。"""
    raw, close = TH.build_all(d, x)["US"]
    pct = pd.DataFrame({c: TH.expanding_pct(raw[c]) for c in TH.US_COLS + TH.US_WATCH})
    w = TH.us_watch_series(pct)["W"]
    a0 = TH._eq(pct[TH.US_COLS])
    fdd = TH.forward_drawdown(close, 60)
    out = {}
    for lvl in (0.10, 0.15):
        ev = (fdd <= -lvl).astype(float).where(fdd.notna())
        for name, s in (("W", w), ("A0", a0)):
            m = (s.index >= EVAL0) & s.notna() & ev.notna()
            a, e = s[m], ev[m]
            out[f"{name}_{int(lvl * 100)}"] = [TH.auc(a[a.index < SPLIT], e[a.index < SPLIT]), TH.auc(a[a.index >= SPLIT], e[a.index >= SPLIT])]
    tp, _ = date_phases(close.dropna(), 0.10, 0.10)
    peaks = [p for p in tp[tp["kind"] == "peak"]["date"] if p >= EVAL0]
    ev10 = (fdd <= -0.10).astype(float).where(fdd.notna())
    for name, s in (("W", w), ("A0", a0)):
        pc = TH.expanding_pct(s)
        for thr, tag in ((0.9, "hits"), (0.8, "hits80")):
            q = pc >= thr
            out[f"{name}_{tag}"] = [sum(bool(q.loc[:p].tail(61).any()) for p in peaks), len(peaks)]
        m = (pc.index >= EVAL0) & ev10.notna()
        base = float(ev10[m].mean())
        on = m & (pc >= 0.8)
        out[f"{name}_lift80"] = round(float(ev10[on].mean()) / base, 2) if on.any() and base else None
    return out


def main() -> int:
    t0 = time.time()
    d = TH.load_inputs()
    lines = [f"# 美股前瞻观察：金银比 + 商品波动（复核 {pd.Timestamp.today().date()}；S&P500 数据截至 {d['spx'].index[-1].date()}）"]
    fp_log = paths.out_dir() / "us_watch_forward.csv"
    out: dict = {}
    if fp_log.exists() and len(pd.read_csv(fp_log)):
        r = TH.watch_review(pd.read_csv(fp_log), d["spx"])
        out["forward"] = r
        lines += [f"\n## 前瞻（{r['first']} 起，{r['days']} 天，其中结果已知 {r['known']} 天、事件日 {r['event_days']} 天）",
                  f"- AUC：W {fmt(r['auc_W'])}，现行 A0 {fmt(r['auc_A0'])}",
                  f"- 警戒（≥90）{r['alert_days']} 天，之后 60 日内真的跌 ≥10% 的比例 {fmt(r['alert_hit'])}；"
                  f"预警（≥80）{r['warn80_days']} 天，比例 {fmt(r['warn80_hit'])}；前瞻期基准发生率 {fmt(r['base_rate'])}",
                  "- 前瞻期内 ≥10% 下跌：" + ("；".join(f"{e['peak']} 高点（W 事前警戒 {'有' if e['W_alert'] else '无'} / 预警 "
                                                     f"{'有' if e['W_warn80'] else '无'}，A0 警戒 {'有' if e['A0_alert'] else '无'} / 预警 "
                                                     f"{'有' if e['A0_warn80'] else '无'}）" for e in r["episodes"]) or "还没有"),
                  f"\n判定（事先规则）：90 分位警戒 —— {r['decision']}；80 分位预警 —— {r['decision80']}"]
    else:
        lines.append("\n还没有前瞻记录（第一次日报运行后开始）。")
    try:
        ins = in_sample(d, TH.load_extra_all())
        out["in_sample"] = ins
        lines += ["\n## 样本内参考（偏乐观：两个因素是看过 2011 年后结果才挑的，不作判定依据）",
                  "| 指标 | 跌≥10% AUC 1995–2010 / 2011– | 跌≥15% AUC 1995–2010 / 2011– | 下跌前 60 日内到过 90 分位 | 到过 80 分位 | ≥80 分位日的下跌发生率 / 基准 |",
                  "|---|---|---|---|---|---|"]
        for name, lab in (("W", "W（金银比 + 商品波动）"), ("A0", "A0 现行威胁指数")):
            a10, a15, h, h8 = ins[f"{name}_10"], ins[f"{name}_15"], ins[f"{name}_hits"], ins[f"{name}_hits80"]
            lines.append(f"| {lab} | {fmt(a10[0])} / {fmt(a10[1])} | {fmt(a15[0])} / {fmt(a15[1])} | {h[0]} / {h[1]} | "
                         f"{h8[0]} / {h8[1]} | {ins[f'{name}_lift80']} 倍 |")
    except Exception as e:                                               # noqa: BLE001
        lines.append(f"\n（样本内参考计算失败：{e}）")
    lines.append(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "us_watch_review"
    Path(f"{fp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
