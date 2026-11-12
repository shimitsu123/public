"""leap2_s5_explore.py — 「选股本身的质的飞跃」第 S5 轮探索：宏观敏感度（β）高的票的突破（只描述、不登记；E / J，Z 不看）。

机器学习研究（scripts/ml_study.py，J-Quants 2019〜2026 样本外）里两期同号的单因子：对 USD/JPY、美 10Y、WTI、日経的 β 高的票更好
（看了留出期才知道 → 当时只能前向检验）。这里在两个年代的突破交易上看：信号日为止过去 104 周的周收益回归（每个因素单独、控制不控制日経都看）
  b_n225  对日経225 的 β；b_fx 对 USD/JPY 的 β（控制日経）；b_us10 对美国 10 年利率周变化（控制日経）；b_wti 对 WTI 周收益（控制日経）
逐笔 = 第 1 轮缓存的单独交易（今天的日経225 + 扩大池、现行卖出规则、扣成本）；看 W2 保留的；每个 β 按那个年代的三分位。
美国 / 汇率 / 原油的周数据只用到信号日所在那一周之前一周（与日本同一周的美国收盘在日本收盘之后）。
输出：var/out/leap2_s5_explore.md / .json（只有统计）
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
from leap2_s3_explore import tercile_table                                   # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
WEEKS = 104
BETAS = [("b_n225", "对日経225 的 β"), ("b_fx", "对 USD/JPY 的 β（控制日経）"), ("b_us10", "对美国 10 年利率的 β（控制日経）"),
         ("b_wti", "对 WTI 的 β（控制日経）")]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def weekly(s: pd.Series) -> pd.Series:
    """日收盘 → 周五为止的周收盘（W-FRI）。"""
    return s.dropna().resample("W-FRI").last()


def rolling_betas(y: pd.DataFrame, x: pd.DataFrame, ctrl: str | None, weeks: int = WEEKS) -> dict[str, pd.DataFrame]:
    """y = 周 × 票 的周收益；x = 周 × 因素 的周变化（已经错开到「当时已知」）。每个因素 f：过去 weeks 周的回归 y ~ f（+ ctrl）
    的 f 系数（周 × 票，只用那一周为止）。用 numpy 逐周算（最少 2/3 的周有值）。"""
    Y = y.to_numpy(float)
    out = {}
    for f in x.columns:
        cols = [f] + ([ctrl] if ctrl and f != ctrl else [])
        X = x[cols].to_numpy(float)
        B = np.full(Y.shape, np.nan)
        for k in range(weeks, len(y)):
            xs, ys = X[k - weeks + 1:k + 1], Y[k - weeks + 1:k + 1]
            okx = np.isfinite(xs).all(axis=1)
            A = np.column_stack([np.ones(okx.sum()), xs[okx]])
            ysub = ys[okx]
            for j in range(Y.shape[1]):
                ok = np.isfinite(ysub[:, j])
                if ok.sum() < weeks * 2 // 3:
                    continue
                coef, *_ = np.linalg.lstsq(A[ok], ysub[ok, j], rcond=None)
                B[k, j] = coef[1]
        out[f] = pd.DataFrame(B, index=y.index, columns=y.columns)
    return out


def main() -> int:
    import leap_data as LD
    from bullbear_study import load
    t0 = time.time()
    T = pd.read_pickle(paths.sub("cache") / "leap_r1_trades.pkl")
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    LC.assert_explore_dates(T["sig_date"])
    names = sorted(T["ticker"].unique())
    data = LD.ohlcv(names)
    C = pd.DataFrame({t: data[t]["Close"] for t in names if t in data}).sort_index()
    del data
    Yw = C.resample("W-FRI").last().pct_change(fill_method=None)
    n225 = weekly(load("^N225", "1998-01-01")["Close"]).pct_change()
    fx = weekly(load("JPY=X", "1998-01-01")["Close"].where(lambda s: (s > 60) & (s < 250))).pct_change()
    us10 = weekly(load("^TNX", "1998-01-01")["Close"]).diff()
    wti = weekly(load("CL=F", "2000-01-01")["Close"].where(lambda s: s > 1)).pct_change()
    X = pd.DataFrame({"n225": n225, "fx": fx.shift(1), "us10": us10.shift(1), "wti": wti.shift(1)}).reindex(Yw.index)   # 美国 / 汇率 / 原油：前一周
    Yw = Yw.clip(-0.5, 0.5)
    B = {"b_n225": rolling_betas(Yw, X[["n225"]], None)["n225"]}
    for f in ("fx", "us10", "wti"):
        B[f"b_{f}"] = rolling_betas(Yw, X[[f, "n225"]], "n225")[f]
    wk = T["sig_date"].dt.to_period("W-FRI").dt.start_time - pd.Timedelta(days=1)     # 信号日所在周之前的那个周五 → 只用上一周为止的 β
    for k, M in B.items():
        idx = M.index.searchsorted(wk.to_numpy(), side="right") - 1
        T[k] = [M.iat[i, M.columns.get_loc(t)] if (i >= 0 and t in M.columns) else np.nan for i, t in zip(idx, T["ticker"])]
    say(f"# 「选股本身的质的飞跃」第 S5 轮探索：宏观敏感度（β）高的票的突破（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s5_explore.py 开头。格子 = 笔数 / 胜率 / 每笔净收益；低 / 中 / 高 = 那个年代 W2 交易按 β 三分位。")
    out = {}
    for era, (a, b) in ERAS.items():
        for uni, U in (("日経225 + 扩大池", T), ("日経225", T[T["n225"]])):
            V = U[(U["sig_date"] >= pd.Timestamp(a)) & (U["sig_date"] < pd.Timestamp(b)) & U["w2"]]
            say(f"\n## {era} · {uni} · W2 保留（{len(V)} 笔：胜率 {(V['net'] > 0).mean() * 100:.1f}%、每笔 {V['net'].mean():+.2f}%）")
            say("| β | 覆盖 | 低 | 中 | 高 | 高 − 低：胜率 pp / 每笔 pp | 高 > 低 的年数 |")
            say("|---|---|---|---|---|---|---|")
            for f, lab in BETAS:
                r = tercile_table(V, f)
                out[f"{era}/{uni}/{f}"] = r
                if r:
                    fm = lambda s: f"{s['n']} / {s['win']:.0f}% / {s['mean']:+.2f}%"                                     # noqa: E731
                    say(f"| {lab} | {V[f].notna().mean() * 100:.0f}% | {fm(r['low'])} | {fm(r['mid'])} | {fm(r['high'])} | "
                        f"{r['d_win']:+.1f} / {r['d_mean']:+.2f} | {r['years'][0]}/{r['years'][1]} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s5_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
