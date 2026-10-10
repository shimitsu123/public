"""allstock_posthoc.py — 事后核对（不参与任何判定，2026-09-27）：allstock_study（登记 1024de5）用的全部股票训练数据（2016-10〜2026-09、
东证一般市场的内国普通股、现行突破信号不加 W2、每只票单独按现行卖出规则做一笔的净收益）上：
① W2（周线量比 ≥ 1.0）在全部股票里逐笔是否也更好——按年、按流动性（20 天平均成交额）三等分、日経225（今天的成分）与其他；
② 18 个特征每一年与净收益的秩相关（哪些方向每年一致）。
输出：var/out/allstock_posthoc.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import allstock_data as AD                                                   # noqa: E402
import allstock_study as S                                                   # noqa: E402
import candle_data as CD                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def stat(x: pd.DataFrame) -> dict:
    net = x["net"].to_numpy(float)
    if not len(net):
        return {"n": 0}
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    return {"n": int(len(net)), "win": float((net > 0).mean() * 100), "mean": float(net.mean()),
            "pf": float(pos / neg) if neg > 0 else float("nan")}


def w2_split(T: pd.DataFrame) -> dict:
    """W2 保留（w5v ≥ 1 或缺值）/ 过滤掉（w5v < 1）的逐笔统计与差。"""
    drop = (T["w5v"] < 1.0).to_numpy()
    k, d = stat(T[~drop]), stat(T[drop])
    return {"keep": k, "drop": d, "diff": (k.get("mean", np.nan) - d.get("mean", np.nan)) if k["n"] and d["n"] else float("nan"),
            "frac": float((~drop).mean()) if len(T) else float("nan")}


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.trader import load_params
    t0 = time.time()
    p0 = load_params(market="JP")
    pb = replace(p0, min_weekly_vol_ratio=0.0)
    mk = S.market_frame(load(*SYM["JP"])["Close"])
    A = AD.load()
    T, n_st = S.train_all(A, pb, mk)
    del A
    D = CD.load()
    n225 = {D["names"][j] for j in range(len(D["names"])) if D["mem"]["U0"][:, j].any()}
    T["year"] = pd.DatetimeIndex(T["sig_date"]).year
    T["n225"] = T["ticker"].isin(n225)
    out: dict = {"n": int(len(T)), "stocks": n_st}
    fa = lambda v, f="{:+.2f}%": "—" if v is None or not np.isfinite(v) else f.format(v)   # noqa: E731
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'], '{:.2f}')}"   # noqa: E731
    say("# 事后核对：全部股票上的 W2 与各特征（不参与任何判定）")
    say(f"数据 = allstock_study（登记 1024de5）的训练数据：{n_st} 只、{len(T)} 笔（2016-10〜2026-09，现行突破不加 W2，每只票单独、扣成本）。")
    say("各格 = 笔数 / 胜率 / 每笔净收益 / 盈亏比；「差」= 保留 − 过滤掉的每笔净收益。")
    say("\n## ① W2 在全部股票里（按年）")
    say("| 年 | 保留的比例 | W2 保留 | W2 过滤掉 | 差 |")
    say("|---|---|---|---|---|")
    out["by_year"] = {}
    for y in sorted(T["year"].unique()):
        r = w2_split(T[T["year"] == y])
        out["by_year"][int(y)] = r
        say(f"| {y} | {r['frac'] * 100:.0f}% | {c4(r['keep'])} | {c4(r['drop'])} | {fa(r['diff'], '{:+.2f} pp')} |")
    r = w2_split(T)
    out["all"] = r
    say(f"| 全期 | {r['frac'] * 100:.0f}% | {c4(r['keep'])} | {c4(r['drop'])} | {fa(r['diff'], '{:+.2f} pp')} |")
    pos_years = sum(1 for v in out["by_year"].values() if np.isfinite(v["diff"]) and v["diff"] > 0)
    say(f"\n差 > 0 的年份：{pos_years} / {len(out['by_year'])}")
    say("\n## ① 续：按流动性（信号日 20 天平均成交额，全部交易三等分）与股票池")
    say("| 组 | 保留的比例 | W2 保留 | W2 过滤掉 | 差 |")
    say("|---|---|---|---|---|")
    q = np.nanquantile(T["lturn"], [1 / 3, 2 / 3])
    grp = {f"流动性低（< ¥{10 ** q[0] / 1e8:.2f} 亿/天）": T["lturn"] < q[0],
           "流动性中": (T["lturn"] >= q[0]) & (T["lturn"] < q[1]),
           f"流动性高（≥ ¥{10 ** q[1] / 1e8:.2f} 亿/天）": T["lturn"] >= q[1],
           "日経225（今天的成分）": T["n225"], "日経225 以外": ~T["n225"]}
    out["groups"] = {}
    for k, m in grp.items():
        r = w2_split(T[m.to_numpy()])
        out["groups"][k] = r
        say(f"| {k} | {r['frac'] * 100:.0f}% | {c4(r['keep'])} | {c4(r['drop'])} | {fa(r['diff'], '{:+.2f} pp')} |")
    say("\n## ② 各特征与净收益的秩相关（按年；+ = 越大越好）")
    ys = sorted(T["year"].unique())
    say("| 特征 | " + " | ".join(str(y) for y in ys) + " | 正的年数 | 全期 |")
    say("|---|" + "---|" * (len(ys) + 2))
    out["feat_ic"] = {}
    for f in S.FEATS:
        row = []
        for y in ys:
            x = T[T["year"] == y]
            ok = x[f].notna()
            row.append(float(x.loc[ok, f].rank().corr(x.loc[ok, "net"].rank())) if ok.sum() > 50 else float("nan"))
        ok = T[f].notna()
        allr = float(T.loc[ok, f].rank().corr(T.loc[ok, "net"].rank()))
        npos = sum(1 for v in row if np.isfinite(v) and v > 0)
        nval = sum(1 for v in row if np.isfinite(v))
        out["feat_ic"][f] = {"years": dict(zip([int(y) for y in ys], row)), "all": allr, "pos": npos, "n": nval}
        say(f"| {f} | " + " | ".join(fa(v, "{:+.3f}") for v in row) + f" | {npos} / {nval} | {fa(allr, '{:+.3f}')} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "allstock_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
