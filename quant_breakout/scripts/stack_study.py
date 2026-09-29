"""stack_study.py — 牛熊分界 × 风险层 × 深跌加仓：叠加起来对整个账户的影响（2026-09-29 登记；只跑一次，看完不改规则）。

用户：「现有的牛熊分界（把 1655 转成现金）和风险层（停开新仓）在做相反的事。检测两者叠加对整个账户的影响」。
上一轮说的「相反」是指：大跌时深跌加仓（买）与现有两层（1655 转现金、停开新仓）方向相反。这里两件事都检验：
（一）现有两层各自与一起对账户的作用（拆解，只描述）；（二）把深跌加仓叠到现行账户上（有判定）。

零 账户：与 rebound_study 相同的现行账户（S0C2 + W2：日経225 突破 4 个名额 × 25%、闲置资金买 1655、T0 = S&P 500 连续 5 天在
   250 日线 ×0.97 之下 → 1655 那份转现金、连续 5 天在 ×1.03 之上 → 买回；立花证券费用；新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜）。
   判断层（行动四选一）与 45% 回撤 HALT 不在回测里（没有历史），这里检验不了。窗口：E 2006-10〜2016-09、J 2017-01〜；
   Z 2001-01〜2006-09 只描述。
一 拆解（只描述，不据此改任何规则；改牛熊分界 / 风险层要你明确要求）：
   V0 现行；V1 关牛熊分界（1655 一直拿着）；V2 关风险层（新仓倍数一律 1）；V3 两个都关。
二 深跌加仓（事件 = 日経225 13 周线乖离第一次 ≤ −15%，与 qbreak/deepdip_forward.py 同一定义；事件日收盘决定 → 下一个交易日开盘买
   日経225 ETF 1321（Yahoo 从 2009-01 才有，之前用日経225 + 年 1.8% 股息拼接），拿 60 个交易日，之后按引擎的核心仓位规则卖掉）：
   D1 只用熊市现金：牛熊分界 = 熊（1655 那份本来是现金）时才买，目标 = 核心目标额 × 25%（≈ 权益的 23〜25%）；牛市时不做。
   D2 不管牛熊：牛市时核心目标额里 1655 : 1321 = 3 : 1；熊市时 1321 = 核心目标额 × 25%，其余现金。
   D0（正确性检查，不是候选）：同一套设置但 1321 从不买 → 必须与 V0 相同（E、J、Z 的 Calmar 差都 ≤ 0.001），否则程序停下，不算 D1 / D2。
三 判定（事先写定，D1 / D2 各判一次）：E 与 J 的 Calmar 都 ≥ V0 + 0.02，且两个窗口的最大回撤都不比 V0 深 2 pp 以上 →「提议」
   （改模拟盘要你确认）；其余「不通过」。
四 另报（只描述）：每个深跌事件（2001〜2026）之后 60 / 120 个交易日各方案的账户涨跌与 120 天内最低（相对事件日）。
输出：var/out/stack_study.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import deepdip_forward as DF                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402

DD_THR, HOLD, SLICE, DIV_1321 = -15.0, 60, 0.25, 1.8
MIN_GAIN, MAX_DD_WORSE, D0_TOL = 0.02, 2.0, 0.001
TAGS = ("E", "J", "Z")                                                       # Z 只描述
JUDGE = ("E", "J")
EP_H = (60, 120)
NAMES = {"V0": "现行", "V1": "关牛熊分界（1655 一直拿着）", "V2": "关风险层（新仓倍数一律 1）", "V3": "两个都关",
         "D1": "现行 + 深跌加仓（只用熊市现金）", "D2": "现行 + 深跌加仓（不管牛熊）"}


def dd_events() -> list[pd.Timestamp]:
    """日経225 13 周线乖离第一次 ≤ −15% 的日子（全历史；与前向记录同一套函数）。"""
    import crash_mainline_study as CM
    nk = CM.n225()
    return list(DF.events(DF.line_dev(nk).iloc[:-1], DD_THR))


def window_mask(days: pd.DatetimeIndex, events, hold: int = HOLD) -> pd.Series:
    """决定日（收盘）在事件日起 hold 个交易日内 → True（下一个交易日开盘买，第 hold 个决定日之后卖）。事件日不在日历里 → 从下一天算。"""
    days = pd.DatetimeIndex(days)
    on = np.zeros(len(days), bool)
    for d in events:
        k = int(days.searchsorted(pd.Timestamp(d)))
        if k < len(days):
            on[k:k + hold] = True
    return pd.Series(on, index=days)


def on_days(s: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """布尔 Series 放到另一个日历上（向前填，与引擎读牛熊的方式相同）。"""
    return s.reindex(pd.DatetimeIndex(days).union(s.index)).ffill().reindex(days).fillna(False).astype(bool)


def dd_series(days: pd.DatetimeIndex, events, us_bear: pd.Series, kind: str) -> tuple[pd.Series, pd.Series]:
    """(1321 的「熊」= 不持有, 1321 的核心比例)。D0：一直不持有；D1：窗口内且美股熊才持有；D2：窗口内就持有。
    比例：美股熊时 = SLICE（1321 是唯一的核心，只拿核心目标额的 25%）；美股牛时 = 1（按权重 1655 : 1321 = 3 : 1 分）。"""
    w = window_mask(days, events)
    ub = on_days(us_bear, days)
    hold = {"D0": pd.Series(False, index=days), "D1": w & ub, "D2": w}[kind]
    return ~hold, pd.Series(np.where(ub.to_numpy(), SLICE, 1.0), index=days)


def frame_1321(years: int):
    """1321（日経225 ETF）引擎用 K 线：Yahoo 有的日子用 1321，之前用日経225 + 年 1.8% 股息拼接（与 1655 的拼法相同）。"""
    from bullbear_study import load
    from qbreak.config import DataConfig
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    etf = load_universe(["1321.T"], DataConfig(provider="yfinance", years=years, allow_synthetic=False).validate())["1321.T"]
    return core_frame(etf, load("^N225", "1965-01-01"), div_yield_pct=DIV_1321)


def engine_cls():
    import candle_portfolio as CP

    class StackEngine(CP.MixEngine):
        """与 MixEngine 相同；DD_EXPO 不为空时给「DD」核心键一个按日的比例（MixEngine 对另加的牛熊键一律给 1）。"""
        DD_EXPO: pd.Series | None = None

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            s = StackEngine.DD_EXPO
            if s is not None and "DD" in self.bear:
                self.core_expo["DD"] = s.reindex(self.gidx.union(s.index)).ffill().reindex(self.gidx).fillna(1.0).to_numpy(float)
    return StackEngine


def us_bear_series() -> pd.Series:
    """引擎用的同一个 T0（S&P 500，var/bullbear.json 的探测器）。"""
    from bullbear_study import SYM, load
    from qbreak.bullbear import BEAR, Detector, load_config
    d = load_config()["detector"]
    c = load(*SYM["US"])["Close"]
    return pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(c)) == BEAR, index=c.index)


def ep_stats(eq: pd.Series, events, hs=EP_H) -> list[dict]:
    """每个事件：事件日收盘的账户 → 之后 60 / 120 个交易日的涨跌、120 天内最低（相对事件日）。"""
    out = []
    eq = eq.dropna()
    for d in events:
        k = int(eq.index.searchsorted(pd.Timestamp(d)))
        if k >= len(eq) or k + max(hs) >= len(eq):
            continue
        e0 = float(eq.iloc[k])
        r = {"date": str(pd.Timestamp(d).date())}
        for h in hs:
            r[f"r{h}"] = round((float(eq.iloc[k + h]) / e0 - 1) * 100, 2)
        r["low"] = round((float(eq.iloc[k + 1:k + max(hs) + 1].min()) / e0 - 1) * 100, 2)
        out.append(r)
    return out


def verdict(acct: dict, kind: str) -> dict:
    """acct[tag][variant] = {cagr, dd, calmar}。D1 / D2：E、J 的 Calmar 都 ≥ V0 + 0.02 且回撤都不深 2 pp 以上 →「提议」。"""
    rows = {}
    ok = True
    for tag in JUDGE:
        b, v = acct[tag]["V0"], acct[tag][kind]
        dc, dd = v["calmar"] - b["calmar"], v["dd"] - b["dd"]                # 回撤是负数：dd 差 < 0 = 更深
        rows[tag] = {"d_calmar": round(dc, 3), "d_dd": round(dd, 2)}
        ok &= dc >= MIN_GAIN - 1e-12 and dd >= -MAX_DD_WORSE - 1e-12
    return {"label": "提议" if ok else "不通过", **rows}


def main() -> int:
    import leap_confirm as LF
    import madev_event as ME
    import rebound_study as RB
    import candle_portfolio as CP
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    events = dd_events()
    ub = us_bear_series()
    Eng = engine_cls()
    acct, eps, D0 = {}, {}, {}
    for tag in TAGS:
        S = ME.load_sample(tag, p0)
        ctx = S["ctx"]
        run_fn = LF.runner(ctx, S["fa"])
        fw = LF.with_mask(S["fa"], S["keep"])
        a, b = ctx["windows"][tag]
        nb = pd.Series(False, index=pd.bdate_range("1999-01-01", "2027-12-31"))
        kw = {"V0": {}, "V1": {"extra_bear": {"NB": nb}, "cfg_over": {"core_index": {"1655.T": "NB"}}},
              "V2": {"mult": False}, "V3": {"mult": False, "extra_bear": {"NB": nb}, "cfg_over": {"core_index": {"1655.T": "NB"}}}}
        acct[tag], eps[tag] = {}, {}
        for v, k in kw.items():
            r = LF.run(ctx, run_fn, fw, p, **k)
            acct[tag][v] = {x: r[tag][x] for x in ("cagr", "dd", "calmar")}
            eps[tag][v] = ep_stats(RB.last_equity(), [d for d in events if pd.Timestamp(a) <= d and (not b or d < pd.Timestamp(b))])
        x1321 = frame_1321(ctx.get("years") or 27)
        days = x1321.index
        old = CP.MixEngine
        CP.MixEngine = Eng
        try:
            for kind in ("D0", "D1", "D2"):
                bear_dd, expo = dd_series(days, events, ub, kind)
                Eng.DD_EXPO = expo
                r = LF.run(ctx, run_fn, fw, p, extra_core={"1321.T": x1321}, extra_bear={"DD": bear_dd},
                           cfg_over={"core": {"1655.T": 1.0, "1321.T": 1 / 3}, "core_index": {"1655.T": "US", "1321.T": "DD"},
                                     "core_mode": "follow"})
                st = {x: r[tag][x] for x in ("cagr", "dd", "calmar")}
                if kind == "D0":
                    D0[tag] = st
                    if abs(st["calmar"] - acct[tag]["V0"]["calmar"]) > D0_TOL:
                        raise SystemExit(f"D0 与 V0 不同（{tag}：{st} vs {acct[tag]['V0']}）→ 实现有问题，停下，不算 D1 / D2")
                    continue
                acct[tag][kind] = st
                eps[tag][kind] = ep_stats(RB.last_equity(), [d for d in events if pd.Timestamp(a) <= d and (not b or d < pd.Timestamp(b))])
        finally:
            CP.MixEngine = old
            Eng.DD_EXPO = None
        print(f"{tag} 完成（{time.time() - t0:.0f} 秒）", flush=True)
    ver = {k: verdict(acct, k) for k in ("D1", "D2")}
    L = ["# 牛熊分界 × 风险层 × 深跌加仓：叠加对账户的影响（2026-09-29 登记，只跑一次；规则见 scripts/stack_study.py 开头）", "",
         "判定（深跌加仓，E 与 J 的 Calmar 都 ≥ 现行 + 0.02 且回撤都不深 2 pp 以上 →「提议」）："
         + "；".join(f"{NAMES[k]} **{v['label']}**" for k, v in ver.items()), "",
         "| 方案 | " + " | ".join(f"{t} 年化 / 最大回撤 / Calmar" for t in TAGS) + " |", "|---|" + "---|" * len(TAGS)]
    for v in NAMES:
        L.append(f"| {v} {NAMES[v]} | " + " | ".join(
            f"{acct[t][v]['cagr']:+.2f}% / {acct[t][v]['dd']:.2f}% / {acct[t][v]['calmar']:.3f}" if v in acct[t] else "—" for t in TAGS) + " |")
    L += ["", "正确性检查 D0（加了 1321 但从不买）：" + "；".join(f"{t} Calmar {D0[t]['calmar']:.3f}（现行 {acct[t]['V0']['calmar']:.3f}）" for t in TAGS),
          "", "## 每个深跌事件之后的账户（相对事件日收盘）", "",
          "| 窗口 | 事件日 | " + " | ".join(f"{v} 60 / 120 天、最低" for v in NAMES) + " |", "|---|---|" + "---|" * len(NAMES)]
    for t in TAGS:
        for i, e in enumerate(eps[t]["V0"]):
            cells = []
            for v in NAMES:
                x = eps[t].get(v, [])
                x = x[i] if i < len(x) else None
                cells.append("—" if x is None else f"{x['r60']:+.1f} / {x['r120']:+.1f}%、{x['low']:+.1f}%")
            L.append(f"| {t} | {e['date']} | " + " | ".join(cells) + " |")
    L += ["", "现行账户的判断层（行动四选一）与 45% 回撤 HALT 没有历史，不在回测里。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "stack_study"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"verdict": ver, "accounts": acct, "d0": D0, "episodes": eps,
                                              "events": [str(d.date()) for d in events]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
