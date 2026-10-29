"""deepdip_regime_posthoc.py — 深跌加仓在牛市有优势还是在熊市有优势（事后描述，2026-09-29；用户问；不参与任何判定、不改任何规则）。

用户：「深跌加仓在牛有优势还是在熊有优势」。
做法：四个市场历史上所有「13 周线乖离第一次 ≤ 门槛」的事件（与前向记录 qbreak/deepdip_forward.py 同一定义、同一门槛：
日経225 −15%、S&P 500 −12%、DAX −14%、FTSE 100 −11.2%；同一套函数算结果），按事件日那天的牛熊分界分成「牛」与「熊」
（与 T0 同一规则：250 日线 ×0.97 之下连续 5 天 → 熊、×1.03 之上连续 5 天 → 牛；用各自指数自己的），比较下一个交易日收盘买之后
60 个交易日的超额（减事件前 10 年平均）、涨的比例、60 天内最低、120 天涨跌。日本另报按 S&P 500 的 T0（模拟盘用的那一个）分。
另读 var/out/stack_study.json：账户层 D1（只用熊市现金）与 D2（不管牛熊）只在 T0 = 牛的事件上不同 → 牛市那几次加仓对账户的差。
这些事件以前都看过（crash_mainline_posthoc、deepdip_intl_check），这里只是换一种分法描述。非投资建议。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import deepdip_forward as DF                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402

N_BOOT, SEED = 5000, 20260929


def t0_bear(c: pd.Series) -> pd.Series:
    from qbreak.bullbear import BEAR, Detector, load_config
    d = load_config()["detector"]
    c = c.dropna()
    return pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(c)) == BEAR, index=c.index)


def state_on(bear: pd.Series, d) -> bool:
    """事件日（收盘时）那天的牛熊：当天或之前最后一个状态（美股的状态放到日本日期上时同样向前取）。"""
    s = bear[bear.index <= pd.Timestamp(d)]
    return bool(s.iloc[-1]) if len(s) else False


def summarize(rows: list[dict]) -> dict:
    done = [r for r in rows if r.get("x60") is not None]
    if not done:
        return {"n": 0}
    f = lambda k: round(float(np.nanmean([np.nan if r.get(k) is None else r[k] for r in done])), 2)   # noqa: E731
    return {"n": len(done), "x60": f("x60"), "xe60": f("xe60"), "win": round(float(np.mean([r["r60"] > 0 for r in done]) * 100), 1),
            "mae60": f("mae60"), "r120": f("r120"), "r20": f("r20")}


def diff_ci(rows: list[dict], n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """熊 − 牛 的 60 日超额平均差；95% 区间 = 同一次大跌（跨市场相距 ≤ 90 天）整段重抽。"""
    done = [r for r in rows if r.get("x60") is not None]
    bear = [r for r in done if r["bear"]]
    bull = [r for r in done if not r["bear"]]
    if len(bear) < 2 or len(bull) < 2:
        return {"diff": None}
    d0 = float(np.mean([r["x60"] for r in bear]) - np.mean([r["x60"] for r in bull]))
    lab = DF.episode_labels([r["date"] for r in done])
    groups: dict[int, list[dict]] = {}
    for r, g in zip(done, lab):
        groups.setdefault(g, []).append(r)
    keys = sorted(groups)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        pick = [r for k in rng.integers(0, len(keys), len(keys)) for r in groups[keys[k]]]
        b1 = [r["x60"] for r in pick if r["bear"]]
        b0 = [r["x60"] for r in pick if not r["bear"]]
        if b1 and b0:
            vals.append(np.mean(b1) - np.mean(b0))
    return {"diff": round(d0, 2), "lo": round(float(np.percentile(vals, 2.5)), 2), "hi": round(float(np.percentile(vals, 97.5)), 2),
            "episodes": len(keys)}


def account_rows(fp: Path, spx_bear: pd.Series, jp_days: pd.DatetimeIndex, hold: int = 60) -> list[dict]:
    """stack_study：D1 只在 T0 = 熊的日子持有，D2 窗口内一直持有 → 两者只在「事件时 T0 = 牛」的日子不同。
    T0 状态直接从 S&P 500 的牛熊分界读（放到日本交易日上，与引擎相同）；D2 − D1 = 牛市那几天也买的账户差（60 / 120 天）。"""
    if not fp.exists():
        return []
    js = json.loads(fp.read_text(encoding="utf-8"))
    out = []
    for tag, ev in js.get("episodes", {}).items():
        for a, b in zip(ev.get("D1", []), ev.get("D2", [])):
            d = pd.Timestamp(a["date"])
            k = int(jp_days.searchsorted(d))
            win = jp_days[k:k + hold]
            st = [state_on(spx_bear, x) for x in win]
            first = next((str(x.date()) for x, v in zip(win, st) if v), None)
            out.append({"window": tag, "date": a["date"], "bear_at_event": bool(st[0]) if st else None, "first_bear": first,
                        "d60": round(b["r60"] - a["r60"], 2), "d120": round(b["r120"] - a["r120"], 2)})
    return out


def main() -> int:
    import deepdip_intl_check as IC
    from bullbear_study import load
    rows = []
    closes = {}
    for mk, spec in DF.MARKETS.items():
        c = DF.drop_partial(load(spec["symbol"], "1900-01-01"), spec["session"])["Close"].astype(float).dropna()
        closes[mk] = c
        bear = t0_bear(c)
        for r in IC.event_rows(mk, c, spec["thr"]):
            r["bear"] = state_on(bear, r["date"])
            rows.append(r)
    spx_bear = t0_bear(closes["US"])
    for r in rows:
        if r["market"] == "JP":
            r["spx_bear"] = state_on(spx_bear, r["date"])
    by = {}
    for mk in [*DF.MARKETS, "ALL"]:
        sub = rows if mk == "ALL" else [r for r in rows if r["market"] == mk]
        by[mk] = {"熊": summarize([r for r in sub if r["bear"]]), "牛": summarize([r for r in sub if not r["bear"]])}
    jp = [r for r in rows if r["market"] == "JP"]
    by_spx = {"熊": summarize([r for r in jp if r["spx_bear"]]), "牛": summarize([r for r in jp if not r["spx_bear"]])}
    ci = diff_ci(rows)
    acct = account_rows(paths.out_dir() / "stack_study.json", spx_bear, closes["JP"].index)
    fm = lambda v, f="{:+.2f}%": "—" if v is None else f.format(v)                                  # noqa: E731
    name = {**{k: v["name"] for k, v in DF.MARKETS.items()}, "ALL": "四个市场合并"}
    L = ["# 深跌加仓：牛市里有优势还是熊市里有优势（事后描述，2026-09-29；不参与判定、不改规则）", "",
         "事件 = 13 周线乖离第一次 ≤ 门槛（日経225 −15%、S&P 500 −12%、DAX −14%、FTSE 100 −11.2%）；牛 / 熊 = 事件日那天各自指数的牛熊分界（与 T0 同一规则）。",
         "结果 = 下一个交易日收盘买之后：60 日超额（减事件前 10 年平均）/ 60 天涨的比例 / 60 天内最低 / 120 天涨跌。", "",
         "| 市场 | 熊：个数 / 60 日超额 / 涨的比例 / 最低 / 120 天 | 牛：个数 / 60 日超额 / 涨的比例 / 最低 / 120 天 |", "|---|---|---|"]
    for mk, v in by.items():
        cells = []
        for k in ("熊", "牛"):
            s = v[k]
            cells.append("—" if not s.get("n") else f"{s['n']} / {fm(s['x60'])} / {s['win']:.0f}% / {fm(s['mae60'])} / {fm(s['r120'])}")
        L.append(f"| {name[mk]} | " + " | ".join(cells) + " |")
    L += ["", f"合并的差（熊 − 牛，60 日超额）：{fm(ci.get('diff'))}（95% 区间 {fm(ci.get('lo'))}〜{fm(ci.get('hi'))}，按大跌段整段重抽；"
          f"独立的大跌段 {ci.get('episodes', '—')} 个）",
          "日経225 按 S&P 500 的牛熊分界（模拟盘用的那一个）分：" + "；".join(
              f"{k} {s['n']} 个 {fm(s['x60'])}、涨的比例 {s['win']:.0f}%" for k, s in by_spx.items() if s.get("n")), "",
          "## 每个事件", "", "| 市场 | 事件日 | 牛熊 | 乖离 | 60 天 | 120 天 | 60 天内最低 | 60 日超额 |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["date"], r["market"])):
        L.append(f"| {name[r['market']]} | {r['date']} | {'熊' if r['bear'] else '牛'}"
                 + (f"（S&P {'熊' if r.get('spx_bear') else '牛'}）" if r["market"] == "JP" else "")
                 + f" | {r['dev']:+.1f}% | {fm(r['r60'])} | {fm(r['r120'])} | {fm(r['mae60'])} | {fm(r['x60'])} |")
    if acct:
        L += ["", "## 账户层（stack_study：D2 − D1 只来自 T0 = 牛时也买的那几次）", ""]
        for a in acct:
            how = ("T0 = 熊，两种同时买" if a["bear_at_event"] else
                   (f"事件时 T0 = 牛：D2 当天买，D1 等到 {a['first_bear']} 转熊才买" if a["first_bear"] else "T0 = 牛：只有 D2 买"))
            L.append(f"- {a['window']} {a['date']}：{how}；D2 − D1 60 / 120 天 {a['d60']:+.1f} / {a['d120']:+.1f} pp")
    L += ["", "这些事件以前都看过（crash_mainline_posthoc、deepdip_intl_check），这里只是换一种分法描述；事件少、同一次大跌在几个市场各算一个。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "deepdip_regime_posthoc"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"by_market": by, "jp_by_spx": by_spx, "diff": ci, "account": acct, "events": rows},
                                             ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
