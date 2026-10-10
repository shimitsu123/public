"""leap_r3_explore.py — 「质的飞跃」第 3 轮探索：个股交易比「同一段时间拿核心」多赚多少（只描述、不登记；只用 2006-10 以后）。

第 1〜2 轮的教训：账户里个股仓位用的钱本来会放在核心（S&P500 日元计）→ 个股要比同一段时间的核心赚得多，账户才会更好。
这里对第 1 轮的独立交易（var/cache/leap_r1_trades.pkl：日経225 + 扩大池、现行突破去掉 W2、扣成本）算
  超额 = 这笔的净收益 − 同一段时间（信号日收盘 → 卖出那天）核心的收益（S&P500 × USD/JPY，东证日历，另加股息 1.3%/年），
再看信号日就知道的市场条件能不能分出「这时候买日本个股比拿核心好」：
  rel12 = 日経225 与 核心 的 12-1 个月对数涨跌之差；fx63 = USD/JPY 近 63 个交易日涨跌 %；vix = 前一个美股收盘的 VIX；
  n200 = 日経225 离 200 日线；美国 / 日本 牛熊（现行牛熊分界）。
输出：var/out/leap_r3_explore.md / .json（只有统计）
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
import leap_common as LC                                                     # noqa: E402
import leap_r1_explore as R1                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
DIV = 1.3
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def core_over(core: pd.Series, sig: pd.Series, hold: pd.Series) -> np.ndarray:
    """信号日收盘 → 卖出那天（信号日后第 hold + 1 个交易日）的核心收益 %（含股息估计）。"""
    idx = core.index
    i = idx.searchsorted(pd.to_datetime(sig).to_numpy())
    j = np.minimum(i + hold.to_numpy(int) + 1, len(idx) - 1)
    c = core.to_numpy(float)
    ok = (i < len(idx)) & (idx[np.minimum(i, len(idx) - 1)] == pd.to_datetime(sig).to_numpy())
    r = (c[j] / c[np.minimum(i, len(idx) - 1)] - 1) * 100 + DIV * (j - i) / 252
    return np.where(ok, r, np.nan)


def tstats(g: pd.DataFrame) -> dict:
    if not len(g):
        return {"n": 0}
    return {"n": int(len(g)), "net": round(float(g["net"].mean()), 3), "core": round(float(g["core"].mean()), 3),
            "ex": round(float(g["ex"].mean()), 3), "win": round(float((g["net"] > 0).mean() * 100), 1),
            "beat": round(float((g["ex"] > 0).mean() * 100), 1)}


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.bullbear import BEAR, Detector, load_config
    from unified_study import spx_jpy_on_jp_days
    t0 = time.time()
    T = pd.read_pickle(paths.sub("cache") / "leap_r1_trades.pkl")
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    LC.assert_explore_dates(T["sig_date"])
    jp, us = load(*SYM["JP"]), load(*SYM["US"])
    fx = load("JPY=X", "2000-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    core = spx_jpy_on_jp_days(us, fx, jp.index)["Close"]
    T["core"] = core_over(core, T["sig_date"], T["hold_days"])
    T["ex"] = T["net"] - T["core"]
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {m: pd.Series(np.asarray(det.states(x["Close"])) == BEAR, index=x.index) for m, x in (("JP", jp), ("US", us))}
    n = jp["Close"]
    lj = np.log(n)
    lc = np.log(core)
    cond = pd.DataFrame(index=jp.index)
    cond["rel12"] = (lj.shift(21) - lj.shift(252)) - (lc.reindex(jp.index).shift(21) - lc.reindex(jp.index).shift(252))
    cond["fx63"] = (fx.reindex(jp.index).ffill() / fx.reindex(jp.index).ffill().shift(63) - 1) * 100
    vix = load("^VIX", "1999-01-01")["Close"]
    cond["vix"] = vix.reindex(jp.index.union(vix.index)).ffill().shift(1).reindex(jp.index)
    cond["n200"] = n / n.rolling(200).mean() - 1
    cond["us_bear"] = bear["US"].reindex(jp.index.union(bear["US"].index)).ffill().reindex(jp.index).astype(float)
    cond["jp_bear"] = bear["JP"].reindex(jp.index).astype(float)
    T = T.join(cond, on="sig_date")
    T = T[T["ex"].notna()]
    say(f"# 「质的飞跃」第 3 轮探索：个股交易 vs 同一段时间的核心（只描述，{pd.Timestamp.today().date()}）")
    say("超额 = 这笔净收益 − 同一段时间核心（S&P500 × USD/JPY + 股息 1.3%/年）的收益；赢核心 = 超额 > 0 的比例。")
    out = {}
    for era, (a, b) in ERAS.items():
        E = T[(T["sig_date"] >= pd.Timestamp(a)) & (T["sig_date"] < pd.Timestamp(b))]
        out[era] = {}
        for sub, V in (("全部突破", E), ("W2 保留", E[E["w2"]]), ("W2 保留 · 日経225", E[E["w2"] & E["n225"]])):
            say(f"\n## {era} {a[:7]}〜{b[:7]} · {sub}：{tstats(V)}")
            res = {}
            say("| 条件 | 低 1/3：n / 每笔 / 核心 / 超额 / 赢核心 | 中 | 高 1/3 | 高 − 低 超额 pp |")
            say("|---|---|---|---|---|")
            for c in ("rel12", "fx63", "vix", "n200", "dy", "vol60"):
                q = pd.qcut(V[c].rank(method="first"), 3, labels=False) if V[c].notna().sum() >= 30 else pd.Series(np.nan, index=V.index)
                rows = [tstats(V[q == k]) for k in range(3)]
                res[c] = rows
                f = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['net']:+.2f} / {s['core']:+.2f} / {s['ex']:+.2f} / {s['beat']:.0f}%"   # noqa: E731
                d = rows[2].get("ex", np.nan) - rows[0].get("ex", np.nan) if rows[0].get("n") and rows[2].get("n") else np.nan
                say(f"| {c} | {f(rows[0])} | {f(rows[1])} | {f(rows[2])} | {d:+.2f} |")
            for c, lab in (("us_bear", "美国熊市"), ("jp_bear", "日本熊市")):
                r0, r1 = tstats(V[V[c] == 0]), tstats(V[V[c] == 1])
                res[c] = [r0, r1]
                say(f"| {lab}：否 → 是 | {r0} | — | {r1} | — |")
            out[era][sub] = res
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r3_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
