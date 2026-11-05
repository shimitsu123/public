"""div_explore.py — 探索（只用权利付最终日在 2017-01〜2021-12 的 10 次；2022 年以后不看）：配当の権利取り（研究路线图 R4）——
3 月 / 9 月权利确定日之前，予想配当利回り高的股票是不是比其他股票涨得多（2026-09-27）。

机制：个人投资者为了拿配当 / 优待在权利付最终日之前买入（「権利取り」），之后权利落ち日卖出；这是制度造成的、时点固定的买盘。
做法（都只用当时已知的信息）：
  权利付最终日 L = 当月最后一个交易日往前 2 个交易日（2019-07-16 结算周期缩短之前是 3 个）；
  开盘买入日 t0 = L 往前 N−1 个交易日（N = 5 / 10 / 15），L 收盘卖出（落ち之前，不含配当）；
  股票池 = t0 时的时点 TOPIX 1000 成员里 3 月决算的公司；予想配当 = t0 之前最近一次决算短信的当期予想
  （3 月 = 期末 FDivFY、9 月 = 中间 FDiv2Q；没有当期的就用上期 FY 短信里的下期予想 NxFDiv…）；
  利回り = 予想配当 ÷ t0 前一天的真实收盘价（调整后价格 × 真实一手比例）；收益用调整后价格；超额 = 减去同一次事件全体的等权平均。
原始数据只在 var/cache/jquants/（已 gitignore），这里只有统计。
输出：var/out/div_explore.md / .json（只有统计）
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
from qbreak import paths                                                     # noqa: E402

FINS = Path(__file__).resolve().parents[1] / "var" / "cache" / "jquants" / "bulk" / "fins" / "summary"
T2_FROM = pd.Timestamp("2019-07-16")                                         # 结算周期 T+3 → T+2
EXPLORE_END = pd.Timestamp("2022-01-01")
NS = (5, 10, 15)
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def last_cum_day(days: pd.DatetimeIndex, year: int, month: int) -> int | None:
    """权利付最终日在 days 里的位置（当月最后一个交易日往前 2 / 3 个交易日）。"""
    m = np.where((days.year == year) & (days.month == month))[0]
    if not len(m):
        return None
    lag = 2 if days[m[-1]] >= T2_FROM else 3
    return int(m[-1] - lag)


def load_fins() -> pd.DataFrame:
    cols = ["DiscDate", "Code", "CurPerType", "CurFYEn", "FDiv2Q", "FDivFY", "NxFDiv2Q", "NxFDivFY"]
    fs = sorted((FINS / "historical").glob("*/*.csv.gz")) + sorted((FINS / "live").glob("*.csv.gz"))
    out = []
    for f in fs:
        d = pd.read_csv(f, usecols=lambda c: c in cols, dtype={"Code": str}, compression="gzip")
        out.append(d)
    F = pd.concat(out, ignore_index=True).drop_duplicates()
    F["DiscDate"] = pd.to_datetime(F["DiscDate"])
    F["CurFYEn"] = pd.to_datetime(F["CurFYEn"], errors="coerce")
    for c in ("FDiv2Q", "FDivFY", "NxFDiv2Q", "NxFDivFY"):
        F[c] = pd.to_numeric(F[c], errors="coerce")
    F["t"] = F["Code"].astype(str).str[:4] + ".T"
    return F.sort_values("DiscDate")


def forecast_div(F: pd.DataFrame, t0: pd.Timestamp, month: int) -> pd.Series:
    """{票: t0 之前已知的、这次权利确定日的予想配当（円 / 股）}；只要 3 月决算的公司。"""
    fy = pd.Timestamp(t0.year if month == 3 else t0.year + 1, 3, 31)
    col, nx = ("FDivFY", "NxFDivFY") if month == 3 else ("FDiv2Q", "NxFDiv2Q")
    k = F[F["DiscDate"] < t0]
    cur = k[k["CurFYEn"] == fy].groupby("t").last()[col]
    prev = k[(k["CurFYEn"] == fy - pd.DateOffset(years=1)) & (k["CurPerType"] == "FY")].groupby("t").last()[nx]
    out = cur.combine_first(prev)
    return out[np.isfinite(out)]


def events(days: pd.DatetimeIndex, y0: int = 2017, y1: int = 2026) -> list[tuple[int, int, int]]:
    ev = []
    for y in range(y0, y1 + 1):
        for m in (3, 9):
            L = last_cum_day(days, y, m)
            if L is not None and L >= max(NS) and days[L] + pd.Timedelta(days=10) <= days[-1] + pd.Timedelta(days=10):
                ev.append((y, m, L))
    return ev


def event_table(D: dict, F: pd.DataFrame, ev: list, n: int) -> pd.DataFrame:
    P, days, names, mem, ratio = D["P"], D["days"], D["names"], D["mem"]["U2"], D["ratio"]
    col = {t: j for j, t in enumerate(names)}
    rows = []
    for y, m, L in ev:
        i0 = L - n + 1
        t0 = days[i0]
        div = forecast_div(F, t0, m)
        for t, dv in div.items():
            j = col.get(t)
            if j is None or not mem[i0, j]:
                continue
            o, c, pc, rt = P["O"][i0, j], P["C"][L, j], P["C"][i0 - 1, j], ratio[i0 - 1, j]
            if not (np.isfinite(o) and np.isfinite(c) and np.isfinite(pc) and np.isfinite(rt)) or o <= 0 or pc <= 0:
                continue
            rows.append({"event": f"{y}-{m:02d}", "L": days[L], "t": t, "yield": dv / (pc * rt) * 100, "ret": (c / o - 1) * 100})
    T = pd.DataFrame(rows)
    if len(T):
        T["ex"] = T["ret"] - T.groupby("event")["ret"].transform("mean")
        T["q"] = T.groupby("event")["yield"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False) + 1)
    return T


def main() -> int:
    t0 = time.time()
    import candle_data as CD
    D = CD.load()
    F = load_fins()
    ev = [e for e in events(D["days"]) if D["days"][e[2]] < EXPLORE_END]
    res: dict = {}
    say("# 探索：配当の権利取り（3 月 / 9 月权利付最终日之前；只用 2017〜2021 的 10 次）")
    say("股票池 = 时点 TOPIX 1000 里 3 月决算的公司；利回り = 当时已知的予想配当 ÷ 前一天真实收盘；收益 = t0 开盘买、权利付最终日收盘卖（不含配当、未扣成本）；"
        "超额 = 减去同一次事件全体等权平均。Q5 = 利回り最高的五分之一。")
    say("权利付最终日：" + "、".join(f"{y}-{m:02d} → {D['days'][L].date()}" for y, m, L in ev))
    for n in NS:
        T = event_table(D, F, ev, n)
        g = T.groupby("q")["ex"].agg(["mean", "count"])
        per = T[T["q"] == 5].groupby("event")["ex"].mean()
        per1 = T[T["q"] == 1].groupby("event")["ex"].mean()
        raw5 = T[T["q"] == 5].groupby("event")["ret"].mean()
        res[n] = {"quint": g.to_dict(), "q5_by_event": per.to_dict(), "q1_by_event": per1.to_dict(), "q5_raw": raw5.to_dict()}
        say(f"\n## 持有 {n} 个交易日（t0 开盘 → 权利付最终日收盘）：{len(T)} 个「票 × 事件」")
        say("| 利回り五分位 | Q1（最低） | Q2 | Q3 | Q4 | Q5（最高） | Q5 − Q1 |")
        say("|---|---|---|---|---|---|---|")
        say("| 平均超额 %（笔数） | " + " | ".join(f"{g.loc[q, 'mean']:+.2f}（{int(g.loc[q, 'count'])}）" for q in range(1, 6))
            + f" | {g.loc[5, 'mean'] - g.loc[1, 'mean']:+.2f} |")
        yq = T.groupby("q")["yield"].median()
        say("| 利回り中位数 % | " + " | ".join(f"{yq.loc[q]:.2f}" for q in range(1, 6)) + " | — |")
        say("| 事件 | " + " | ".join(per.index) + " |")
        say("|---|" + "---|" * len(per))
        say("| Q5 超额 % | " + " | ".join(f"{v:+.2f}" for v in per.to_numpy()) + " |")
        say("| Q5 绝对收益 % | " + " | ".join(f"{v:+.2f}" for v in raw5.to_numpy()) + " |")
        say(f"Q5 超额为正的事件：{int((per > 0).sum())} / {len(per)}；3 月 {per[[k for k in per.index if k.endswith('-03')]].mean():+.2f}%、"
            f"9 月 {per[[k for k in per.index if k.endswith('-09')]].mean():+.2f}%")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "div_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
