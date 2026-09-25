"""threat_forward_review.py — 威胁指数各版本的前瞻检验（规则 2026-09-25 事先写定，之后不改）。

记录：var/out/threat_forward.csv 每天一行 × 市场，列 = 各版本当天的读数（日报运行时算出、已记的日期不改）：
  A0  现行 v1                          A0x 去掉「利率曲线倒挂」「油价冲击」（用户 2026-09-25 要求加入）
  B1～B4  v3 研究的四种合成             S   因子调查的组合（A0 + 1995–2010 选入的因素）
为什么只能前瞻：这些版本都是看过历史结果之后提出的 —— A0x 是因子调查里「拿掉后两段都更好」的两个（样本内发现），
  B / S 在历史检验里没有胜出但保留对照。历史数字（下面「样本内参考」）偏乐观，不作判定依据。
检验：每个市场，只用之后 60 个交易日已经走完的记录；事件 = 之后 60 个交易日内最低收盘比当天跌 ≥10%（另报 ≥15%）；
  每个版本与 A0 在同一批日子上比 AUC。
判定（每个市场分别，只在该市场前瞻期内 ≥3 次 ≥10% 下跌、且 ≥500 天结果已知之后）：
  AUC 比 A0 高 ≥0.03、且 ≥15% 下跌的 AUC 不低于 A0 的版本 → 取 AUC 最高的一个，建议日报改用（需要用户确认）；否则继续记录。
  不论结论如何都不自动改日报或交易规则。每季度复核时运行（例行任务），输出 var/out/threat_forward_review.md / .json。
补登（2026-09-25，用户要求；此时这些列还没有任何记录）：日経再加 8 个版本「A0+因素」= 现行 v1 再加日経前瞻观察 Wj 的一个因素
  （新兴市场相对美股、美国实际利率急升、短观大企业、短观中小非制造业、初请失业金、等权 / 市值加权、日银加息、日本企业物价加速），
  用同一条判定规则。披露：日経一共比 14 个版本，某个版本碰巧过线的机会比只比一个时大；这 8 个因素也是看过 2011 年后结果才挑的
  （因子调查里加进现行模型两段都有增益，调查里的 ΔAUC 列为样本内参考）。
补登（2026-09-25，用户要求；此时这些列还没有任何记录）：美股再加 2 个版本「A0+金银比上升」「A0+商品波动」
  （现行 v1 再加美股前瞻观察的一个因素），同一条判定规则。美股一共比 8 个版本；这两个因素也是看过 2011 年后结果才挑的。
补登（2026-09-25，用户要求；此时这一列还没有任何记录）：美股再加「A0+W」= 现行 v1 再加金银比与商品波动两个因素（等权），
  同一条判定规则；美股一共比 9 个版本。样本内参考在下面单独列出（偏乐观）。
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

EVAL0, SPLIT = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01")


def fmt(v):
    return "—" if v is None or v != v else f"{v:.3f}"


def in_sample(d: dict) -> dict:
    """A0x 与 A0 的样本内参考（偏乐观：A0x 是看过这段结果才提出的）。"""
    built = TH.build(d)
    out = {}
    for m in ("US", "JP"):
        _, pct = built[m]
        close = d["spx"] if m == "US" else d["n225"]
        close = close.reindex(pct.index)
        v1 = TH.US_COLS if m == "US" else TH.JP_COLS
        a0 = TH._eq(pct[v1])
        ax = TH._eq(pct[[c for c in v1 if c not in TH.A0X_DROP]])
        fdd = TH.forward_drawdown(close, 60)
        r = {}
        for lvl in (0.10, 0.15):
            ev = (fdd <= -lvl).astype(float).where(fdd.notna())
            for name, s in (("A0", a0), ("A0x", ax)):
                m_ = (s.index >= EVAL0) & s.notna() & ev.notna() & a0.notna() & ax.notna()
                a, e = s[m_], ev[m_]
                r[f"{name}_{int(lvl * 100)}"] = [TH.auc(a[a.index < SPLIT], e[a.index < SPLIT]),
                                                 TH.auc(a[a.index >= SPLIT], e[a.index >= SPLIT])]
        out[m] = r
    return out


def in_sample_w(d: dict) -> dict:
    """「现行 + 金银比 + 商品波动」（美股）的样本内参考（偏乐观：两个因素是看过 2011 年后结果才挑的）。"""
    raw, close = TH.build_all(d, TH.load_extra_all())["US"]
    pct = pd.DataFrame({c: TH.expanding_pct(raw[c]) for c in TH.US_COLS + TH.US_WATCH})
    a0, aw = TH._eq(pct[TH.US_COLS]), TH._eq(pct[TH.US_COLS + TH.US_WATCH])
    fdd = TH.forward_drawdown(close, 60)
    r = {}
    for lvl in (0.10, 0.15):
        ev = (fdd <= -lvl).astype(float).where(fdd.notna())
        for name, s in (("A0", a0), ("A0+W", aw)):
            m_ = (s.index >= EVAL0) & s.notna() & ev.notna() & a0.notna() & aw.notna()
            a, e = s[m_], ev[m_]
            r[f"{name}_{int(lvl * 100)}"] = [TH.auc(a[a.index < SPLIT], e[a.index < SPLIT]), TH.auc(a[a.index >= SPLIT], e[a.index >= SPLIT])]
    return r


def main() -> int:
    t0 = time.time()
    d = TH.load_inputs()
    lines = [f"# 威胁指数各版本的前瞻检验（复核 {pd.Timestamp.today().date()}；S&P500 截至 {d['spx'].index[-1].date()} / "
             f"日経 {d['n225'].index[-1].date()}）"]
    out: dict = {}
    fp_log = paths.out_dir() / "threat_forward.csv"
    if fp_log.exists() and len(pd.read_csv(fp_log)):
        fr = TH.forward_review(pd.read_csv(fp_log), {"US": d["spx"], "JP": d["n225"]})
        out["forward"] = fr
        for m, name in (("US", "S&P500"), ("JP", "日経225")):
            r = fr.get(m)
            if not r:
                continue
            lines += [f"\n## {name}：{r['first']} 起 {r['days']} 天，结果已知 {r['known']} 天、事件日 {r['event_days']} 天；"
                      f"前瞻期内 ≥10% 下跌 {len(r['episodes'])} 次",
                      "| 版本 | 对照天数 | AUC（跌≥10%）版本 / A0 | AUC（跌≥15%）版本 / A0 |", "|---|---|---|---|"]
            for v, x in r["variants"].items():
                lines.append(f"| {TH.forward_label(v)} | {x.get('n', 0)} | {fmt(x.get('auc10'))} / {fmt(x.get('auc10_A0'))} | "
                             f"{fmt(x.get('auc15'))} / {fmt(x.get('auc15_A0'))} |")
            lines.append(f"\n判定（事先规则）：{r['decision']}")
    else:
        lines.append("\n还没有前瞻记录。")
    try:
        ins = in_sample(d)
        out["in_sample"] = ins
        lines += ["\n## 样本内参考：去掉曲线倒挂与油价冲击（偏乐观，不作判定依据）",
                  "| 市场 | 版本 | 跌≥10% AUC 1995–2010 / 2011– | 跌≥15% AUC 1995–2010 / 2011– |", "|---|---|---|---|"]
        for m, name in (("US", "S&P500"), ("JP", "日経225")):
            for v in ("A0", "A0x"):
                a10, a15 = ins[m][f"{v}_10"], ins[m][f"{v}_15"]
                lines.append(f"| {name} | {TH.FORWARD_LABELS[v]} | {fmt(a10[0])} / {fmt(a10[1])} | {fmt(a15[0])} / {fmt(a15[1])} |")
        sv = json.loads((paths.out_dir() / "threat_factor_survey.json").read_text(encoding="utf-8"))
        iw = in_sample_w(d)
        out["in_sample_w"] = iw
        lines += ["\n## 样本内参考：美股「现行 + 金银比 + 商品波动」（偏乐观，不作判定依据）",
                  "| 版本 | 跌≥10% AUC 1995–2010 / 2011– | 跌≥15% AUC 1995–2010 / 2011– |", "|---|---|---|"]
        for v in ("A0", "A0+W"):
            lines.append(f"| {TH.forward_label(v)} | {fmt(iw[v + '_10'][0])} / {fmt(iw[v + '_10'][1])} | "
                         f"{fmt(iw[v + '_15'][0])} / {fmt(iw[v + '_15'][1])} |")
        from qbreak.survey import JP_WATCH
        lines += ["\n## 样本内参考：「现行 + 单个观察因素」（因子调查里加进现行模型的 ΔAUC，偏乐观）",
                  "| 市场 | 版本 | ΔAUC 1995–2010 / 2011– | 单独 AUC 1995–2010 / 2011– |", "|---|---|---|---|"]
        for m, name, fs in (("US", "S&P500", TH.US_WATCH), ("JP", "日経225", JP_WATCH)):
            rows = (sv.get(m) or {}).get("factors") or {}
            for f in fs:
                x = rows.get(f) or {}
                dl, sg = x.get("delta") or [None, None], x.get("single") or [None, None]
                lines.append(f"| {name} | {TH.forward_label('A0+' + f)} | {fmt(dl[0])} / {fmt(dl[1])} | {fmt(sg[0])} / {fmt(sg[1])} |")
    except Exception as e:                                               # noqa: BLE001
        lines.append(f"\n（样本内参考计算失败：{e}）")
    lines.append(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "threat_forward_review"
    Path(f"{fp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
