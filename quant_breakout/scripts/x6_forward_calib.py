"""x6_forward_calib.py — 卖法 X6 前向记录的登记前校准（2026-09-28；只用已经看过的 E / J，不是检验）。

两件事：
1) 核对：逐信号配对模拟（qbreak/exit_forward.py）的「现行」一边 = 回测引擎一只票一次一仓算出来的交易
   （同一个信号 → 同一个买入日 / 卖出日 / 收益 / 出场原因）。
2) 检出力：E / J 里今天的日経225 的突破（W2 保留的；另报不管 W2 的全部），逐信号 X6 − 现行 的配对差：平均、标准差、
   按信号月聚类的标准误、每年信号数 → 估计前向记录大约要多少笔、多少年才分辨得出。
   X6 本身是看过 E / J 之后挑出来的：这里的平均值只作参照，不算证据；前向记录才是检验。
输出：var/out/x6_forward_calib.md / .json。
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
from qbreak import exit_forward as EF                                       # noqa: E402
from qbreak import paths                                                    # noqa: E402

NOTIONAL = 250_000
END_BARS = 90                                  # 只算到信号日之后 90 根 K 线（最长持有 60 天，足够两边平仓）
Z_99_80 = 2.576 + 0.842                        # 99% 区间下限 > 0、检出力 80% 要的「平均 / 标准误」
PER_YEAR = {"每日记录（日経225 + 扩大池，W2 保留）": 110, "全市场主对象（成交额 ≥ ¥500 万，W2 保留）": 450}   # 登记时的预计（W2 登记的每年笔数 × 保留约 45%）


def bt_single():
    from qbreak.config import BacktestConfig
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    return bt


def signals(fa: dict, keep: dict | None, a: str, b: str) -> pd.DataFrame:
    rows = []
    for t, df in fa.items():
        e = df["entry"].to_numpy(bool) & (df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b))
        if keep is not None:
            e &= keep[t]
        rows += [{"ticker": t, "date": d} for d in df.index[e]]
    return pd.DataFrame(rows, columns=["ticker", "date"])


def one_at_a_time(fa: dict, keep: dict, p, bt, a: str, b: str) -> pd.DataFrame:
    """核对用：每只票单独、一次一仓（引擎原样），W2 保留的信号、交易窗口 [a, b]。"""
    from qbreak.engine import run_backtest
    rows = []
    for t, df in fa.items():
        e = df["entry"].to_numpy(bool) & keep[t] & (df.index <= pd.Timestamp(b))
        if not e.any():
            continue
        r = run_backtest({t: df.assign(entry=e)}, p, bt, start=a)
        tr = r.trades[r.trades["reason"] != "end"].copy()
        if len(tr):
            tr["ticker"] = t
            tr["date"] = [df.index[df.index.searchsorted(pd.Timestamp(x)) - 1] for x in tr["entry_date"]]
            rows.append(tr)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ticker", "date"])


def check(P: pd.DataFrame, T: pd.DataFrame) -> dict:
    """配对的现行一边 vs 一次一仓的交易（同一信号）：卖出日 / 收益 / 原因都要一样。"""
    M = T.merge(P, on=["ticker", "date"], how="left")
    ok = M["net_cur"].notna()
    same = ok & (pd.to_datetime(M["exit_date"]) == pd.to_datetime(M["exit_cur"])) & (M["reason"] == M["reason_cur"])
    rt = M["ret_pct"] - M["net_cur"]
    same &= (rt - rt[ok].median()).abs() < 1e-6
    return {"trades": int(len(M)), "found": int(ok.sum()), "same": int(same.sum())}


def per_year(P: pd.DataFrame) -> dict:
    U = EF.usable(P)
    out = {}
    for y, g in U.groupby(pd.to_datetime(U["date"]).dt.year):
        out[int(y)] = {"n": int(len(g)), "cur": round(float(g["net_cur"].mean()), 2), "x6": round(float(g["net_x6"].mean()), 2),
                       "d": round(float(g["d"].mean()), 2)}
    return out


def power(ev: dict, B_sd: float) -> dict:
    """按校准的聚类标准误外推：分辨 Δ pp（99% 下限 > 0、80%）要的配对数 n = n_cal × (Z × SE_cal / Δ)²。"""
    out = {}
    for dlt in (0.5, 1.0, 1.5):
        n = int(np.ceil(ev["n"] * (Z_99_80 * B_sd / dlt) ** 2))
        out[str(dlt)] = {"n": n, **{k: round(n / v, 1) for k, v in PER_YEAR.items()}}
    return out


def main() -> int:
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = SF.no_w2_params(load_params(market="JP"))
    bt = bt_single()
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    L = [f"# X6 前向记录的登记前校准（{pd.Timestamp.today().date()}；只用已看过的 E / J，不是检验）",
         "逐信号配对：只留一个买入信号、回测引擎跑两次（现行 / 死叉换成吊灯止损），买入完全相同；成熟 = 信号日之后 ≥ "
         f"{EF.MATURE_BARS} 根 K 线。股票池 = 今天的日経225；来回手续费 {rt:.3f}%（¥25 万一笔）。", ""]
    out = {}
    for era in ("E", "J"):
        ctx = LF.context(era)
        fa = LF.frames(ctx, p)
        keep = LF.w2_keep(ctx, fa)
        a, b = ctx["start"], ctx["end"] or str(pd.DatetimeIndex(ctx["days"])[-1].date())     # J 的窗口没有终点 → 数据最后一天
        res = {}
        for key, kp in (("w2", keep), ("all", None)):
            S = signals(fa, kp, a, b)
            P = EF.pairs_frame(fa, S, p, bt, rt, end_bars=END_BARS)
            ev = EF.evaluate(P)
            U = EF.usable(P)
            B = EF.boot_mean(U["d"], U["date"]) if len(U) else np.array([np.nan])
            yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
            res[key] = {"ev": ev, "se_cluster": round(float(np.std(B)), 3), "per_year_signals": round(len(S) / yrs, 1),
                        "by_year": per_year(P)}
            if key == "w2":
                res[key]["check"] = check(P, one_at_a_time(fa, keep, p, bt, a, b))
                res[key]["power"] = power(ev, float(np.std(B)))
        out[era] = res
        w, al = res["w2"], res["all"]
        c = w["check"]
        L.append(f"## {era}（{a}〜{b}）")
        L.append(f"- 核对：一次一仓的 {c['trades']} 笔里 {c['found']} 笔在配对里找到、{c['same']} 笔卖出日 / 收益 / 原因完全相同"
                 + ("（全部一致）" if c["same"] == c["trades"] else "（**有不一致**）"))
        L.append(f"- W2 保留：每年 {w['per_year_signals']} 个信号；{EF.summary_line(w['ev'])}")
        L.append(f"  配对差标准差 {w['ev'].get('sd')} pp、按月聚类的标准误 {w['se_cluster']} pp；X6 出场原因 {w['ev'].get('reasons_x6')}")
        L.append(f"- 全部突破（不管 W2，另报）：每年 {al['per_year_signals']} 个信号；{EF.summary_line(al['ev'])}")
        L.append("- 各年（W2 保留，成熟配对）：" + "；".join(f"{y} {v['n']} 笔 {v['d']:+.2f}" for y, v in w["by_year"].items()))
        L.append("- 检出力（按这个聚类标准误外推；99% 区间下限 > 0、80%）：" + "；".join(
            f"差 {dl} pp 要约 {v['n']} 笔（" + "、".join(f"{k.split('（')[0]} {yrs_} 年" for k, yrs_ in v.items() if k != "n") + "）"
            for dl, v in w["power"].items()))
        L.append("")
    L += ["读法：配对差的平均是看过 E / J 之后的数字（X6 就是从这里挑的），只作参照；前向记录用登记之后的信号才算检验。",
          "扩大池 / 全市场的小盘股波动更大，配对差的标准差多半更大 → 上面的年数偏乐观。",
          f"（耗时 {round(time.time() - t0)} s）。校准，只描述；非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "x6_forward_calib"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
