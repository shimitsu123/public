"""cost_sales_forward.py — 「成本 × 销售」的日报显示与 S2 前向记录（2026-09-28 用户确认「改 做显示 做前向记录」；只展示 / 只记录，不影响交易）。

依据：scripts/cost_sales_study.py（登记 12a49c7，结果 7e80596，var/out/cost_sales_study.md）—— 原材料在涨的月份（横截面 COST3 平均 > 0），
  销售好（短観 売上高计划按同一次调查比自己，横截面前一半）且 COST3⁺ ≥ 0.1 的业种里，按「间接占比」IND3⁺ ÷ COST3⁺ 分上半（偏间接）/ 下半
  （偏直接）：之后 3 个月 偏间接 − 偏直接 = +1.227%（NW t 2.65，125 个月，2006-10〜2026-08），不看销售的基准只有 +0.333%（配对差 +0.82，t 2.10）。
  S1（销售盖过成本）无效；个股层 S4 / S5（用它挑突破的票）不成立 —— 所以这里只到行业层，不给个股打标签。
定义与研究完全相同（直接调用 scripts/cost_sales_study.py 的 pos_signals / s2_sets / indirect_share / split_spread 与同一批数据：
  日银企业物价 4 种原材料（发布滞后 1 个月）、2020 产业连关表的直接 / 间接份额 var/io_indirect_2020.json、短観 売上高计划 按可用日取当时最新一次调查）；
  横截面 = 研究登记的 18 个東証业种（CS）。
一 日报显示（每个月第一次 sim-day 算一次上个月末的快照，缓存 var/out/cost_sales_now.json）：
  是否「成本上升的月份」；成本上升时列出 S2 的业种按间接占比分成 偏间接 / 偏直接（中间的不算）；不到 4 个业种 → 这个月不分组（研究里也不算）。
二 前向记录（事先写定，提交后不改；var/out/cost_sales_forward.csv 只追加，同一个 (asof, industry) 只留最早那次，不改、不补写）：
  2026-10-01 起每个月第一次 sim-day 运行时记上个月末（asof = YYYY-MM）18 个业种的 COST3⁺ / DIR3⁺ / IND3⁺ / 间接占比 / SALES / 秩 /
  「成本上升的月份」/ 是否在 S2 / S2b（= 同样月份 COST3⁺ ≥ 0.1 的全部业种，不看销售）—— 当时能取到的数（BOJ 事后修订不回写）。
  复核（scripts/cost_sales_forward.py --review；季度复核加不加要用户确认）：每个 asof 月 t，业种之后 3 个月（t+1〜t+3）的月度相对收益之和
  （東証业种、TOPIX 1000 的 927 只 + 日経225 等权，scripts/transmit_study.load_industry_returns 同一口径，复核当时的名单）→
    x_S2(t) = split_spread（S2、间接占比、至少 4 个业种；研究同一函数）；x_S2b(t) 同样用 S2b；d(t) = x_S2 − x_S2b。
  判定（只看 x_S2；记录的 asof 月 ≥ 36 个起每次复核都判，≥ 60 个时第二次也是最后一次）：
    有 x_S2 值的月 ≥ 12 个 且 平均 > 0 且 Newey–West t（4 阶）≥ 1.645 → 「前向复现」（日报标签改为「前向记录也成立」，只是标签）；
    平均 ≤ 0 → 「前向没复现」（日报标签改为「前向没复现：只作历史参考」；要不要撤掉显示由用户决定）；
    其余 →「未定」：36〜59 个月继续记录；到 60 个月仍未定 →「证据不足」，维持只展示。
  另报（不进判定）：d(t) 的平均与 t（销售这一条件的增量）、命中率、S2b。
  检出力（照实写）：成本上升的月份约 6 成、4 个业种以上的约 85% → 36 个月约 18 个值；历史效应下 t 期望约 1.0，「复现」的概率约 1/4 ——
  所以「未定」是最可能的结果，不代表失效；「没复现」只看点估计 ≤ 0。
三 不做：不改模拟盘 / 执行器 / 股票池 / 仓位；不给个股打「偏间接」标签（个股层 S4 / S5 不成立）；非投资建议。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths

FORWARD_START = "2026-10-01"
LOG_FILE = "cost_sales_forward.csv"
NOW_FILE = "cost_sales_now.json"
COLS = ["logged_on", "asof", "industry", "cost_up", "cost3p", "dir3p", "ind3p", "share", "sales", "sales_rank", "in_s2", "in_s2b"]
JUDGE_MONTHS, FINAL_MONTHS, MIN_N, T_MIN, LAGS = 36, 60, 12, 1.645, 4
STUDY = {"S2": 1.227, "S2_t": 2.65, "S2_n": 125, "S2b": 0.333, "pair": 0.82, "pair_t": 2.10, "top3": 2.29, "top3_t": 3.66,
         "period": "2006-10〜2026-08", "reg": "12a49c7", "res": "7e80596"}


def _study():
    """scripts/cost_sales_study.py（定义与研究相同）；它 import 时设的研究用环境变量 QB_DROP_ZERO_VOL 不留在这个进程里。"""
    sp = str(paths.PROJECT_ROOT / "scripts")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    had = "QB_DROP_ZERO_VOL" in os.environ
    import cost_sales_study as CSS
    if not had:
        os.environ.pop("QB_DROP_ZERO_VOL", None)
    return CSS


def month_end_before(today) -> pd.Timestamp:
    """今天之前最后一个月末（= 上个月末）。"""
    t = pd.Timestamp(str(today)[:10])
    return (t.replace(day=1) - pd.Timedelta(days=1)).normalize()


def panels_at(t: pd.Timestamp, CSS=None) -> dict[str, pd.DataFrame]:
    """月末 t 的 D3p / I3p / D3 / I3 / SALES（18 个业种；研究同一套数据与函数）。"""
    CSS = CSS or _study()
    TS, TK = CSS.TS, CSS.TK
    months = pd.DatetimeIndex([pd.Timestamp(t)])
    ex = TS.load_exposures(CSS.CS)                                     # 读 var/io_indirect_2020.json（方法一致时不重算）
    P = pd.DataFrame({k: TS.cgpi(c) for k, c in TS.SHOCK_CGPI.items()})
    m0 = pd.Timestamp(t).to_period("M").to_timestamp()
    P = P.reindex(P.index.union(pd.DatetimeIndex([m0])))              # 研究的 price_change 按行错开 1 个月（发布滞后）：索引要覆盖 t 所在的月（值留空）
    sig = CSS.pos_signals(P, ex, months, CSS.CS, 3)
    S = TK.load_sales()
    need = {c for g in CSS.CS for c in TK.TSE.get(g, [])} | set(TK.SALES_OLD.values())
    bad = [c for c in TK.MISSING if "102CFY" in c and c[5:9] in need]
    if bad:
        raise RuntimeError(f"短観売上高 取不到：{bad}")
    SALES = TK.to_tse(TK.sales_strength(S, months), CSS.CS).reindex(columns=CSS.CS)
    return {**{k: v.reindex(columns=CSS.CS) for k, v in sig.items()}, "SALES": SALES}


def snapshot(X: dict[str, pd.DataFrame], t: pd.Timestamp, CSS=None) -> dict:
    """月末 t 的快照：18 个业种的数值、S2 / S2b 成员、按间接占比分组（研究 split_spread 的分法：秩在中线的不算）。"""
    CSS = CSS or _study()
    t = pd.Timestamp(t)
    D3p, I3p, D3, I3, SALES = (X[k] for k in ("D3p", "I3p", "D3", "I3", "SALES"))
    S2, S2b = CSS.s2_sets(D3p, I3p, D3, I3, SALES)
    SH = CSS.indirect_share(D3p, I3p)
    rk = CSS.rank_pct(SALES)
    net = float((D3 + I3).loc[t].mean())
    rows = []
    for j in CSS.CS:
        f = lambda A: None if pd.isna(A.at[t, j]) else round(float(A.at[t, j]), 4)          # noqa: E731
        rows.append({"industry": j, "cost3p": f(D3p + I3p), "dir3p": f(D3p), "ind3p": f(I3p), "share": f(SH), "sales": f(SALES),
                     "sales_rank": f(rk), "in_s2": bool(S2.at[t, j]), "in_s2b": bool(S2b.at[t, j])})
    groups = split_groups({r["industry"]: r["share"] for r in rows if r["in_s2"]}, CSS.MIN_SET)
    return {"asof": t.strftime("%Y-%m"), "month_end": str(t.date()), "cost_up": net > 0, "cost_net": round(net, 4),
            "rows": rows, "groups": groups, "n_s2": int(S2.loc[t].sum()), "n_s2b": int(S2b.loc[t].sum())}


def split_groups(share: dict[str, float | None], min_n: int = 4) -> dict:
    """研究 split_spread 的分法（没有收益，只分组）：有间接占比的业种按秩分上半（偏间接）/ 下半（偏直接），秩正好在中线的不算。"""
    k = pd.Series({j: v for j, v in share.items() if v is not None and np.isfinite(v)}, dtype=float)
    if len(k) < min_n:
        return {"ok": False, "n": int(len(k)), "indirect": [], "direct": [], "middle": sorted(k.index)}
    r = k.rank(method="average")
    mid = (len(k) + 1) / 2
    srt = lambda idx: sorted(idx, key=lambda j: -k[j])                                     # noqa: E731
    return {"ok": True, "n": int(len(k)), "indirect": srt(r[r > mid].index), "direct": srt(r[r < mid].index),
            "middle": srt(r[r == mid].index)}


# ── 前向记录 ──
def due(asof: str, today: str, path: Path) -> bool:
    if str(today) < FORWARD_START:
        return False
    if not path.exists():
        return True
    old = pd.read_csv(path, dtype={"asof": str})
    return asof not in set(old["asof"])


def rows_for_log(snap: dict, today: str) -> list[dict]:
    return [{"logged_on": str(today), "asof": snap["asof"], "industry": r["industry"], "cost_up": int(bool(snap["cost_up"])),
             **{k: r[k] for k in ("cost3p", "dir3p", "ind3p", "share", "sales", "sales_rank")},
             "in_s2": int(r["in_s2"]), "in_s2b": int(r["in_s2b"])} for r in snap["rows"]]


def append(path: Path, rows: list[dict]) -> int:
    """只追加；同一个 (asof, industry) 已经有了就不写。返回新增行数。"""
    if not rows:
        return 0
    new = pd.DataFrame(rows, columns=COLS)
    if path.exists():
        old = pd.read_csv(path, dtype={"asof": str, "industry": str})
        seen = set(zip(old["asof"], old["industry"]))
        new = new[[(a, g) not in seen for a, g in zip(new["asof"], new["industry"])]]
        if new.empty:
            return 0
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return int(len(new))


def status(path: Path) -> dict:
    if not path.exists():
        return {"months": 0, "first": None, "last": None, "cost_up_months": 0}
    d = pd.read_csv(path, dtype={"asof": str})
    m = d.groupby("asof")["cost_up"].max()
    return {"months": int(m.size), "first": str(m.index.min()), "last": str(m.index.max()), "cost_up_months": int(m.sum())}


# ── 复核（事先写定的判定）──
def forward_series(log: pd.DataFrame, Y3: pd.DataFrame, CSS=None) -> pd.DataFrame:
    """每个 asof 月：x_S2、x_S2b、d（研究的 split_spread；Y3 = 月末 × 业种 之后 3 个月相对收益之和 %，索引 = 月末）。"""
    CSS = CSS or _study()
    out = []
    for a, g in log.groupby("asof"):
        t = pd.Timestamp(a + "-01") + pd.offsets.MonthEnd(0)
        if t not in Y3.index or Y3.loc[t].isna().all():
            continue
        g = g.set_index("industry")
        sh = pd.DataFrame([g["share"].astype(float)], index=[t])
        s2 = pd.DataFrame([g["in_s2"].astype(bool)], index=[t])
        s2b = pd.DataFrame([g["in_s2b"].astype(bool)], index=[t])
        x = CSS.split_spread(Y3, s2, sh, CSS.MIN_SET)
        xb = CSS.split_spread(Y3, s2b, sh, CSS.MIN_SET)
        out.append({"asof": a, "x_s2": float(x.iloc[0]) if len(x) else np.nan, "x_s2b": float(xb.iloc[0]) if len(xb) else np.nan})
    df = pd.DataFrame(out, columns=["asof", "x_s2", "x_s2b"])
    df["d"] = df["x_s2"] - df["x_s2b"]
    return df


def _nw_t(x: np.ndarray, lags: int = LAGS) -> float | None:
    """Newey–West t（4 阶）：与研究同一个函数（qbreak/supply_chain.ic_stats）。"""
    from .supply_chain import ic_stats
    x = x[np.isfinite(x)]
    return ic_stats(pd.Series(x), lags)["t"] if len(x) >= 3 else None


def judge(fs: pd.DataFrame, months_logged: int) -> dict:
    """规则见开头第二节：记录 ≥ 36 个月起判；≥ 60 个月是最后一次。"""
    x = fs["x_s2"].to_numpy(float) if len(fs) else np.array([])
    x = x[np.isfinite(x)]
    d = fs["d"].to_numpy(float) if len(fs) else np.array([])
    d = d[np.isfinite(d)]
    out = {"months_logged": int(months_logged), "n": int(len(x)), "mean": float(x.mean()) if len(x) else None, "t": _nw_t(x),
           "hit": float((x > 0).mean() * 100) if len(x) else None, "pair_n": int(len(d)),
           "pair_mean": float(d.mean()) if len(d) else None, "pair_t": _nw_t(d)}
    if months_logged < JUDGE_MONTHS:
        out["verdict"] = f"只报告进度（记满 {JUDGE_MONTHS} 个月才判定）"
    elif out["n"] >= MIN_N and out["mean"] is not None and out["mean"] > 0 and (out["t"] or 0) >= T_MIN:
        out["verdict"] = "前向复现"
    elif out["mean"] is not None and out["mean"] <= 0:
        out["verdict"] = "前向没复现"
    else:
        out["verdict"] = "证据不足（维持只展示）" if months_logged >= FINAL_MONTHS else "未定（继续记录）"
    return out


# ── sim-day 用：日报块 + 前向记录 ──
def panel(today, out_dir: Path | None = None, compute=None) -> dict:
    """上个月末的快照（每个月算一次，缓存）；到了该记的时候追加前向记录。失败只记原因，不影响交易。"""
    out_dir = Path(out_dir or paths.out_dir())
    t = month_end_before(today)
    fp = out_dir / NOW_FILE
    snap = None
    if fp.exists():
        try:
            c = json.loads(fp.read_text(encoding="utf-8"))
            snap = c if c.get("asof") == t.strftime("%Y-%m") and c.get("rows") else None
        except Exception:                                                  # noqa: BLE001
            snap = None
    if snap is None:
        snap = (compute or _compute)(t)
        snap["computed_on"] = str(today)[:10]
        fp.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    log = out_dir / LOG_FILE
    snap["forward_new"] = append(log, rows_for_log(snap, str(today)[:10])) if due(snap["asof"], str(today)[:10], log) else 0
    snap["forward"] = status(log)
    snap["study"] = STUDY
    return snap


def _compute(t: pd.Timestamp) -> dict:
    CSS = _study()
    return snapshot(panels_at(t, CSS), t, CSS)
