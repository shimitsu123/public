"""cost_sales_forward.py — 「成本 × 销售」S2 前向记录的复核 / 当前分组（规则见 qbreak/cost_sales_forward.py 开头，2026-09-28 登记）。

  python scripts/cost_sales_forward.py --show     上个月末的分组（与日报同一段代码；只读，不写前向记录）
  python scripts/cost_sales_forward.py --review   复核：只读 var/out/cost_sales_forward.csv（不改、不补写）→ var/out/cost_sales_forward_review.md / .json
                                                  + var/out/cost_sales_forward_review_history.csv（只追加）
行业收益：东证业种的月度相对收益（TOPIX 1000 的 927 只 + 日経225 等权，scripts/transmit_study.load_industry_returns 同一口径；只用已经结束的月份）。
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import cost_sales_forward as CF                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def industry_monthly(years: int) -> pd.DataFrame:
    """东证业种的月度相对收益（%），只留已经结束的月份。"""
    import json as _json
    from qbreak import sector_leadlag as SL
    from qbreak import supply_chain as SC
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    s33 = {f"{c}.T": v for c, v in _json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    d = DataConfig(provider="yfinance", years=years, allow_synthetic=False).validate()
    allo = {**load_universe(universe("JP", "broad"), d), **load_universe(W.tickers(W.load()), d)}
    CC, _ = SL.industry_returns(allo, s33)
    M = SC.monthly(CC)
    this_month = pd.Timestamp.today().to_period("M").to_timestamp("M")
    return M[M.index < this_month]


def show() -> int:
    t = CF.month_end_before(pd.Timestamp.today())
    CSS = CF._study()
    s = CF.snapshot(CF.panels_at(t, CSS), t, CSS)
    print(f"成本 × 销售（S2）{s['month_end']} 末：原材料{'在涨' if s['cost_up'] else '没在涨'}（成本净变化平均 {s['cost_net']:+.2f}%）")
    g = s["groups"]
    if s["cost_up"] and g["ok"]:
        print(f"  偏间接：{'、'.join(g['indirect'])}\n  偏直接：{'、'.join(g['direct'])}" + (f"\n  中间（不算）：{'、'.join(g['middle'])}" if g["middle"] else ""))
    elif s["cost_up"]:
        print(f"  销售好且成本上涨的业种只有 {g['n']} 个（不到 4 个）→ 不分组")
    print("只展示，不改交易；非投资建议。")
    return 0


def review() -> int:
    from qbreak import supply_chain as SC
    t0 = time.time()
    fp = paths.out_dir() / CF.LOG_FILE
    say(f"# 成本 × 销售 S2 前向记录复核（{pd.Timestamp.today().date()}；规则见 qbreak/cost_sales_forward.py 开头）")
    if not fp.exists():
        say("还没有记录（2026-10-01 起每月第一次 sim-day 记上个月末）。")
        _write({"months_logged": 0, "verdict": "还没有记录"})
        return 0
    log = pd.read_csv(fp, dtype={"asof": str, "industry": str})
    st = CF.status(fp)
    first = pd.Timestamp(st["first"] + "-01")
    years = max(2, math.ceil((pd.Timestamp.today() - first).days / 365) + 1)
    M = industry_monthly(years)
    CSS = CF._study()
    Y3 = SC.ahead(M, 3).reindex(columns=CSS.CS)
    fs = CF.forward_series(log, Y3, CSS)
    j = CF.judge(fs, st["months"])
    fa = lambda v, f="{:+.2f}": "—" if v is None or (isinstance(v, float) and v != v) else f.format(v)      # noqa: E731
    say(f"- 记录 {st['months']} 个月（{st['first']}〜{st['last']}），其中原材料在涨 {st['cost_up_months']} 个月；"
        f"之后 3 个月已知、S2 能分组的月 {j['n']} 个")
    say(f"- S2 偏间接 − 偏直接：平均 {fa(j['mean'])}%（NW t {fa(j['t'])}，比 0 好的月份 {fa(j['hit'], '{:.0f}')}%）；"
        f"历史 +{CF.STUDY['S2']}%（t {CF.STUDY['S2_t']}）")
    say(f"- 另报（不进判定）：销售这一条件的增量 S2 − S2b 平均 {fa(j['pair_mean'])} pp（t {fa(j['pair_t'])}，{j['pair_n']} 个月）")
    say(f"- 判定：**{j['verdict']}**")
    if len(fs):
        say("\n| asof | S2 偏间接 − 偏直接 | S2b（不看销售） |\n|---|---|---|")
        for _, r in fs.iterrows():
            say(f"| {r['asof']} | {fa(r['x_s2'])}% | {fa(r['x_s2b'])}% |")
    say(f"\n用时 {time.time() - t0:.0f}s。只展示 / 只记录，不改交易；非投资建议。")
    _write({**j, "series": fs.to_dict("records"), "status": st})
    hist = paths.out_dir() / "cost_sales_forward_review_history.csv"
    row = {"run": str(pd.Timestamp.today().date()), "months_logged": st["months"], "n": j["n"], "mean": j["mean"], "t": j["t"],
           "verdict": j["verdict"]}
    pd.DataFrame([row]).to_csv(hist, mode="a", header=not hist.exists(), index=False)       # 只追加
    return 0


def _write(obj: dict) -> None:
    fp = paths.out_dir() / "cost_sales_forward_review"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(review() if "--review" in sys.argv else show())
