"""theme_influence.py — 各主题 / 東証业种的「影响度」历年值 → var/theme_influence.json（日报「影响度的变化」用；只作展示）。

影响度 = 这一组的日收益与日経225 日收益的相关系数平方（R²），每个日历年单独算（该年有效交易日 ≥ 200）：
「日経每天的涨跌里，有多少和这一组同步」。随着产业结构变化（例 半导体在日経里的分量变大）会变 → 每年 1 月跑一次，加上刚结束的一年。
口径与 qbreak/theme_monitor.py 相同（组 = 成员等权；主题成员不足 3 只的日子缺值）。只用已经结束的年份。
用法：python scripts/theme_influence.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import theme_monitor as TM                                       # noqa: E402
from qbreak import themes as TH                                              # noqa: E402


def main() -> int:
    import numpy as np
    from qbreak.config import BENCHMARK, DataConfig
    from qbreak.data import load_universe
    from qbreak.trader import drop_partial_bar
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    want = sorted(set(s33) | {f"{c}.T" for c in TH.members()})
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data = {t: drop_partial_bar(df, "JP") for t, df in load_universe(want, d21).items()}
    ix = drop_partial_bar(load_universe([BENCHMARK["JP"]], d21)[BENCHMARK["JP"]], "JP")
    lr = TM.log_returns(data)
    raw, _, _ = TM.group_panel(lr, s33)
    this_year = pd.Timestamp.today().year
    raw = raw[raw.index.year < this_year]                                   # 只用已经结束的年份
    hist = TM.influence_by_year(raw, np.log(ix["Close"]).diff() * 100)
    out = {"index": BENCHMARK["JP"], "definition": "组的日收益与日経225 日收益的相关系数平方（R²），每个日历年单独算",
           "years": [int(y) for y in sorted({int(y) for h in hist.values() for y in h})],
           "generated": str(pd.Timestamp.today().date()), "groups": hist}
    fp = paths.home() / "theme_influence.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"写入 {fp}（{len(hist)} 组，{out['years'][0]}〜{out['years'][-1]}）")
    for k in TH.THEMES:
        h = hist.get(k, {})
        ys = sorted(h)
        if ys:
            print(k, TH.THEMES[k][0], {y: h[y] for y in ys[::5] + ([ys[-1]] if ys[-1] not in ys[::5] else [])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
