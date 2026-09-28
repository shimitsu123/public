"""rebound_posthoc.py — 超跌反弹（rebound_study 77539c6）的事后诊断（2026-09-28；只描述，不参与判定，不改任何规则）。

rebound_study 按事先规则没有候选入选。结果里看到三件事，这里只拆开来看、不做新的挑选：
  一 13 周线 −25% 的深跌（E2 = N6）逐笔在 2017〜2026 胜率 74〜82%、每笔 +8.8〜10%，加上「大盘不在大跌」过滤（M1）后 2017〜2026 时点 TOPIX 1000
     每笔 −0.17% → 深跌的收益是不是集中在少数几次全市场暴跌（按年份、按大盘状态拆）；
  二 2017〜2026 的组合里 E2M0 与 E2M1 的账户结果完全相同 → 暴跌那几天组合是不是本来就不开新仓（数组合实际买到的超跌笔数、没买的原因）；
  三 超跌反弹那一部分资金闲置时拿 1655 + 牛熊分界（登记的做法）→ 同一框架一笔超跌都不买（只有 1655 + 牛熊分界）时的账户，
     用来分清账户的变化有多少来自超跌买入、多少来自 1655。
做法：与 rebound_study 相同的函数与数据（E2 = N6 事件、XA 到期卖、−15% 止损、最多 20 个交易日）；E / J / J2（组合只有 E / J）。
输出：var/out/rebound_posthoc.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import madev_event as ME                                                     # noqa: E402
import rebound_study as RB                                                   # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []
SLEEVES = (("M0", "只有超跌反弹 M0", None), ("M1", "只有超跌反弹 M1", -6.0), ("OFF", "一笔超跌都不买（只有 1655 + 牛熊分界）", "off"))


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def by_group(T: pd.DataFrame, col: str) -> list[dict]:
    tot = float(T["net"].sum()) if len(T) else 0.0
    out = []
    for g, x in T.groupby(col):
        v = x["net"].to_numpy(float)
        out.append({col: str(g), "n": int(len(v)), "win": float((v > 0).mean() * 100), "mean": float(v.mean()),
                    "share_of_profit": float(v.sum() / tot * 100) if tot else None})
    return out


def cell(s: dict) -> str:
    return f"{RB.fmt(s.get('cagr'), '{:.2f}')}% / {RB.fmt(s.get('dd'), '{:.2f}')}% / {RB.fmt(s.get('calmar'), '{:.3f}')}"


def main() -> int:
    import jq_study as JS
    import leap_confirm as LF
    import sell_confirm as SCF
    from bullbear_study import SYM, load
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    st = RB.index_dev_state(load(*SYM["JP"]))
    say(f"# 超跌反弹的事后诊断（{pd.Timestamp.today().date()}；只描述，不参与判定）")
    say("深跌 E2（13 周线 ≤ −25%、下一个交易日仍 ≤ −25%）+ XA（到期卖、−15% 止损、最多 20 个交易日），与 rebound_study 同一套函数。")
    out = {}
    for tag in ("E", "J", "J2"):
        S = ME.load_sample(tag, p0)
        EV, alld = RB.events_of(S, ["N6"])
        ec = RB.exit_cols(S, sorted(alld["N6"]), "XA", "W", 13)
        T = RB.dip_trades(S, EV["N6"], ec, RB.dip_params(p0, 20), bt, rt)
        T["year"] = pd.to_datetime(T["date"]).dt.year
        T["market"] = np.where(RB.market_ok(T["date"], st, -6.0), "大盘没在大跌", "大盘在大跌（指数 13 周线 ≤ −6%）")
        yr = by_group(T, "year")
        mk = by_group(T, "market")
        out[tag] = {"by_year": yr, "by_market": mk, "n": int(len(T))}
        say(f"\n## {tag}：逐笔 {len(T)} 笔")
        say("| 大盘状态 | 笔数 | 胜率 | 每笔 | 占总收益 |")
        say("|---|---|---|---|---|")
        for r in mk:
            say(f"| {r['market']} | {r['n']} | {r['win']:.1f}% | {r['mean']:+.2f}% | {r['share_of_profit']:.0f}% |")
        say("| 年份 | 笔数 | 胜率 | 每笔 | 占总收益 |")
        say("|---|---|---|---|---|")
        for r in yr:
            say(f"| {r['year']} | {r['n']} | {r['win']:.1f}% | {r['mean']:+.2f}% | {r['share_of_profit']:.0f}% |")
        if tag in ("E", "J"):
            ctx, fa = S["ctx"], S["fa"]
            run_fn = LF.runner(ctx, fa)
            wa, wb = ctx["windows"][tag]
            LF.run(ctx, run_fn, LF.with_mask(fa, S["keep"]), p)
            eq0 = RB.last_equity()
            res = {"现行": RB.acct_stats(eq0, wa, wb)}
            for m, _, thr in SLEEVES:
                ok = {} if thr == "off" else {t: ds[RB.market_ok(ds, st, thr)] for t, ds in alld["N6"].items()}
                fdip = {t: df.assign(entry=np.isin(df.index, ok.get(t, pd.DatetimeIndex([]))), dead_cross=ec.get(t, np.zeros(len(df), bool)))
                        for t, df in fa.items()}
                LF.run(ctx, run_fn, fdip, RB.dip_params(p, 20))
                eng = JS.RealLotEngine.LAST[-1]
                eqd = RB.last_equity()
                tr = pd.DataFrame(eng.st.trades)
                tr = tr[(tr["ticker"] != "1655.T") & (tr["reason"] != "end")] if len(tr) else tr
                sig = int(sum(np.asarray(df["entry"], bool).sum() for df in fdip.values()))
                res[m] = {"signals": sig, "taken": int(len(tr)), "skipped": {str(k): int(v) for k, v in eng.skipped.items()},
                          "only": RB.acct_stats(eqd, wa, wb), "75/25": RB.acct_stats(RB.blend(eq0, eqd, RB.W_DIP), wa, wb)}
            out[tag]["portfolio"] = res
            say("\n组合（只有超跌反弹这一部分）：" + "；".join(
                f"{m} 信号 {res[m]['signals']} 个、实际买到 {res[m]['taken']} 笔、没买的原因 "
                + ("、".join(f"{k} {v}" for k, v in res[m]["skipped"].items() if v) or "无")
                for m, _, thr in SLEEVES if thr != "off"))
            say("| 账户（年化 / 最大回撤 / Calmar） | 这一部分单独 | 75% 现行 + 25% 这一部分 |")
            say("|---|---|---|")
            say(f"| 现行（S0C2 + W2） | {cell(res['现行'])} | — |")
            for m, zh, _ in SLEEVES:
                say(f"| {zh} | {cell(res[m]['only'])} | {cell(res[m]['75/25'])} |")
    out["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {out['elapsed_s']} s）。事后描述，不参与判定；非投资建议。")
    fp = paths.out_dir() / "rebound_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
