"""crash_mainline_posthoc.py — crash_mainline_study（登记 a28290b / 736f739）的事后描述（2026-09-29；只描述，不参与判定，不改任何规则）。

登记的判定：一、二、三都不通过 → A。这里补两件判定里没有的描述，帮助读结果：
  一 「跌到多深」的曲线：只看指数（不要求个股比例），每个深度在更长的历史里之后 60 个交易日的超额 —— 日経225 1965〜2000 / 2001〜2026、
     美国市场 1926〜2026（门槛按波动折算 k）；登记的判定只对「最好的格子」看了独立数据，这里把每个深度都列出来。
  二 「3 个月判定的时代主线」下一季还领先吗（用户 2026-09-28 要求时代主线从 12 个月改为每 3 个月判定）：
     每个日历季度按業種相对收益排前 7（美国 49 行业前 10）→ 下一季的相对收益（减全部業種等权平均）；对照 = 同一时点的 12-1 个月排名前 7 / 前 10。
     日本 = 時点 TOPIX 1000（J2，2017〜2026）与日経225 + 另一批股票（E + W，2006〜2016）的業種等权；美国 = Ken French 49 行业（1926〜2026）。
输出：var/out/crash_mainline_posthoc.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import crash_mainline_study as CM                                            # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []
DEPTHS = (-3.0, -6.0, -9.0, -12.0, -15.0, -20.0)
SPANS = {"日経225 1965〜2000": ("1965-01-01", "2000-12-31"), "日経225 2001〜2026": ("2001-01-04", "2026-09-30")}


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def depth_curve(close: pd.Series, dev: pd.Series, spans: dict, scale: float = 1.0) -> dict:
    c, dates = close.to_numpy(float), close.index
    R = {h: CM.fwd_all(c, h) for h in CM.HORIZONS}
    U = CM.uncond(R, dates, spans)
    out = {}
    for d in DEPTHS:
        T = CM.event_table(CM.depth_events(dev.to_numpy(float), None, d * scale, 0), dates, c, R, spans, U)
        out[d] = {k: CM.cell_stats(T[T["era"] == k], {k: spans[k]}) for k in spans}
    return out


def quarter_persistence(C: np.ndarray, M: np.ndarray, days: pd.DatetimeIndex, groups: np.ndarray, k: int, min_group: int,
                        a: str, b: str) -> dict:
    """每个季度：这一季相对收益前 k 名（3 个月）与 12-1 个月前 k 名 → 下一季的相对收益（减全部業種等权平均，%）。"""
    _, REL = CM.rel_returns(C, M)
    qs = pd.period_range(pd.Timestamp(a), pd.Timestamp(b), freq="Q")
    res = {"q3": [], "m12": [], "rank_corr": []}
    for q in qs[:-1]:
        rows = np.flatnonzero((days >= q.start_time) & (days <= q.end_time.normalize()))
        nxt = q + 1
        rows_n = np.flatnonzero((days >= nxt.start_time) & (days <= nxt.end_time.normalize()))
        if len(rows) < 40 or len(rows_n) < 40:
            continue
        e = rows[-1] + 1
        sc = CM.group_scores(REL, groups, rows, min_group)
        sn = CM.group_scores(REL, groups, rows_n, min_group)
        s12 = CM.group_scores(REL, groups, np.arange(max(0, e - 252), max(0, e - 21)), min_group) if e >= 252 else {}
        common = [g for g in sc if g in sn]
        if len(common) < 2 * k:
            continue
        avg = np.mean([sn[g] for g in common])
        top = CM.top_k({g: sc[g] for g in common}, k)
        res["q3"].append(np.mean([sn[g] for g in top]) - avg)
        c12 = [g for g in s12 if g in sn]
        if len(c12) >= 2 * k:
            res["m12"].append(np.mean([sn[g] for g in CM.top_k({g: s12[g] for g in c12}, k)]) - avg)
        res["rank_corr"].append(CM.spearman(np.array([sc[g] for g in common]), np.array([sn[g] for g in common])))
    return {key: CM.summarize(v) for key, v in res.items()}


def main() -> int:
    t0 = time.time()
    say(f"# 大跌入场深度 × 时代主线：事后描述（{pd.Timestamp.today().date()}；只描述，不参与判定）")
    say("登记的判定（var/out/crash_mainline_study.md）不变：一、二、三都不通过 → A。这里只补两张描述用的表。")
    nk = CM.n225()
    dv = CM.line_dev(nk)
    um = CM.us_market()
    ud = CM.line_dev(um)
    k_idx = CM.idx_sd(um, "1965-01-01", "2026-09-30") / CM.idx_sd(nk, "1965-01-01", "2026-09-30")
    jp = depth_curve(nk, dv, SPANS)
    us = depth_curve(um, ud, {"美国市场 1926〜2026": CM.US_ALL}, k_idx)
    out = {"k_idx": k_idx, "jp": {str(d): v for d, v in jp.items()}, "us": {str(d): v for d, v in us.items()}}
    say("\n## 一、只看指数：13 周线乖离第一次到这个深度 → 下一个交易日收盘买，之后 60 个交易日的超额（减同一时期全部交易日的平均）")
    say(f"美国的门槛 = 日本 × {k_idx:.2f}（波动折算）。格式：段数 / 平均超额（95% 区间）/ 涨的比例 / 买后 60 天内平均还跌")
    cols = list(SPANS) + ["美国市场 1926〜2026"]
    say("\n| 深度 | " + " | ".join(cols) + " |")
    say("|---|" + "---|" * len(cols))
    for d in DEPTHS:
        cells = []
        for k in cols:
            st = (us[d] if k.startswith("美国") else jp[d])[k]
            cells.append("—" if not st.get("n") else
                         f"{st['n']} / {st['mean']:+.2f}%（{CM.fmt(st.get('lo'), '{:+.1f}')}〜{CM.fmt(st.get('hi'), '{:+.1f}')}）/ {st['win']:.0f}% / {st['mae']:+.1f}%")
        say(f"| ≤ {d:+.0f}% | " + " | ".join(cells) + " |")
    say("\n## 二、「3 个月判定的时代主线」下一季还领先吗（每个日历季度一个起点）")
    say("前 k 名（日本 7 个業種、美国 10 个行业）下一季的相对收益 − 全部業種平均（%）；秩相关 = 这一季与下一季业种排名的相关。对照 = 同一时点 12-1 个月前 k 名。")
    P = CM.jp_panels()
    s33 = CM.s33_map()
    res = {}
    for tag, (a, b) in (("J2", ("2017-01-01", "2026-09-30")), ("E", ("2006-10-01", "2016-12-31")), ("W", ("2006-10-01", "2016-12-31")),
                        ("Z", ("2001-01-01", "2006-09-30"))):
        S = P[tag]
        groups = np.array([s33.get(t, "") for t in S["names"]], dtype=object)
        res[tag] = quarter_persistence(S["C"], S["M"], S["days"], groups, 7, CM.MIN_GROUP, a, b)
    ind = CM.us_ind49()
    r = ind.copy()
    first = r.apply(lambda s: s.first_valid_index())
    Cu = (1 + r.fillna(0.0)).cumprod()
    for col in Cu.columns:
        if first[col] is not None:
            Cu.loc[Cu.index < first[col], col] = np.nan
    res["US"] = quarter_persistence(Cu.to_numpy(float), np.isfinite(Cu.to_numpy(float)), pd.DatetimeIndex(Cu.index),
                                    np.array(list(Cu.columns), dtype=object), 10, 1, "1927-01-01", "2026-06-30")
    lab = {"J2": "時点 TOPIX 1000 2017〜2026", "E": "日経225 2006〜2016", "W": "另一批 668 只 2006〜2016", "Z": "日経225 2001〜2006",
           "US": "美国 49 行业 1927〜2026"}
    say("\n| 样本 | 季度数 | 3 个月前 k 名：下一季超额（95% 区间）/ 为正的比例 | 12-1 个月前 k 名：下一季超额 / 为正 | 两季排名的秩相关 |")
    say("|---|---|---|---|---|")
    for t, v in res.items():
        q3, m12, rc = v["q3"], v["m12"], v["rank_corr"]
        say(f"| {lab[t]} | {q3.get('n', 0)} | {CM.fmt(q3.get('mean'), '{:+.2f}')}%（{CM.fmt(q3.get('lo'), '{:+.2f}')}〜{CM.fmt(q3.get('hi'), '{:+.2f}')}）/ "
            f"{CM.fmt(q3.get('pos'), '{:.0f}')}% | {CM.fmt(m12.get('mean'), '{:+.2f}')}% / {CM.fmt(m12.get('pos'), '{:.0f}')}% | {CM.fmt(rc.get('mean'), '{:+.3f}')} |")
    out["persistence"] = res
    out["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {out['elapsed_s']} s）。事后描述，不参与判定；非投资建议。")
    fp = paths.out_dir() / "crash_mainline_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
