"""loop12_r07_cal.py — 第十二个研究循环第 7 轮（最后 3 个名额）：决算后 / 权利落ち前 / 长假前（规则 scripts/research_loop12.py）。
（2026-10-12 登记；先提交后只运行一次。看过第 1〜6 轮之后设计，但不是它们的变体；以前没当过买入过滤。）

  PED〔选股·决算后〕：信号日是这家公司最近一次决算短信开示日之后的第 1〜3 个交易日（开示多在收盘后 → 第 1 个交易日 = 第一次反应）→ 不买（路线 J）。
  DXD〔选股·权利落ち〕：信号日在 3 月或 9 月的最后 10 个交易日之内（中间 / 期末分红的权利确定前，有为分红的买盘、之后除权）→ 不买（三个年代、路线 A / B）。
  HOL〔选股·长假前〕：成交日（信号日的下一个交易日）起的 3 个交易日里，有一天之后是 ≥ 4 个日历日的休市（黄金周、年末年始、银周等）→ 不买（三个年代、路线 A / B）。
池子用同样的定义（Jx 的决算日期同样来自 J-Quants；DXD / HOL 只看日历）。都不是事后组合。第二关另行登记。
运行：python scripts/loop12_r07_cal.py；--wiring。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402
import loop12_r01_fund as R1                                                 # noqa: E402
import loop12_r06_flow as R6                                                 # noqa: E402
import research_loop12 as R12                                                # noqa: E402

ROUND = 7
IDS = ("PED", "DXD", "HOL")
FAMILY = {"PED": "选股·决算后", "DXD": "选股·权利落ち", "HOL": "选股·长假前"}
OUT = "loop12_r07_cal"
PED_N, DXD_N, HOL_N, HOL_GAP = 3, 10, 3, 4


def trading_days(a="1999-01-01", b="2027-12-31") -> pd.DatetimeIndex:
    from qbreak.calendar_jp import is_trading_day
    return pd.DatetimeIndex([d for d in pd.date_range(a, b) if is_trading_day(d.date())])


def ped_gate(disc: dict, days: pd.DatetimeIndex, tickers, dates) -> np.ndarray:
    out = []
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates))):
        x = disc.get(str(t))
        if x is None:
            out.append(False)
            continue
        k = int(np.searchsorted(x, np.datetime64(d), side="left")) - 1
        if k < 0:
            out.append(False)
            continue
        n = int(days.searchsorted(d, side="right") - days.searchsorted(pd.Timestamp(x[k]), side="right"))   # (开示日, 信号日] 的交易日数
        out.append(1 <= n <= PED_N)
    return np.array(out, bool)


def dxd_gate(days: pd.DatetimeIndex, dates) -> np.ndarray:
    s = pd.Series(days, index=days)
    lastn = set()
    for (y, m), g in s.groupby([days.year, days.month]):
        if m in (3, 9):
            lastn |= set(g.iloc[-DXD_N:])
    return np.array([pd.Timestamp(d) in lastn for d in pd.to_datetime(np.asarray(dates))], bool)


def hol_gate(days: pd.DatetimeIndex, dates) -> np.ndarray:
    gap = pd.Series((days[1:] - days[:-1]).days, index=days[:-1])
    out = []
    for d in pd.to_datetime(np.asarray(dates)):
        i = days.searchsorted(d, side="right")                                # 成交日的位置
        w = days[i:i + HOL_N]
        out.append(bool(len(w)) and any(gap.get(x, 1) >= HOL_GAP for x in w))
    return np.array(out, bool)


def build(W: dict) -> dict:
    F = LC.fins_rows()
    disc = {t: np.sort(g["date"].drop_duplicates().to_numpy("datetime64[ns]")) for t, g in F.groupby("ticker")}
    days = trading_days()
    S = LC.signals(W, "J")
    XJx = LC.pool_x(W, "Jx")
    g = {"PED": {"J": ped_gate(disc, days, S["ticker"], S["date"])}, "DXD": {}, "HOL": {}}
    gp = {"PED": {"Jx": ped_gate(disc, days, XJx["ticker"], XJx["date"])}, "DXD": {}, "HOL": {}}
    for e in LC.ERAS:
        dt_ = LC.signals(W, e)["date"]
        g["DXD"][e], g["HOL"][e] = dxd_gate(days, dt_), hol_gate(days, dt_)
    for s in ("W", "Jx", "Zx"):
        if s in W["D"]:
            dt_ = LC.pool_x(W, s)["date"]
            gp["DXD"][s], gp["HOL"][s] = dxd_gate(days, dt_), hol_gate(days, dt_)
    return {"g": g, "gp": gp}


def wiring() -> int:
    W = LC.load()
    B = build(W)
    same = all(LC.run_b4(W, e, np.zeros(len(LC.signals(W, e)), bool)) == LC.run_b4(W, e) for e in LC.ERAS)
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    print(json.dumps({"same_as_b4": bool(same),
                      "blocked_extra": {"PED": int((B["g"]["PED"]["J"] & ~tbf["J"]).sum()),
                                        "DXD": {e: int((B["g"]["DXD"][e] & ~tbf[e]).sum()) for e in LC.ERAS},
                                        "HOL": {e: int((B["g"]["HOL"][e] & ~tbf[e]).sum()) for e in LC.ERAS}},
                      "pool_blocked": {k: {s: int(v.sum()) for s, v in B["gp"][k].items()} for k in IDS}}, ensure_ascii=False))
    return 0 if same else 1


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = R1.git_head()
    W = LC.load()
    B = build(W)
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    res = {"loop": 12, "round": ROUND, "ids": list(IDS), "family": FAMILY, "code": code, "dirty": dirty, "base": base,
           "cand": {}, "stage1": {}, "other": {}, "frac": {}}
    cand = dict(base)
    cand["J"] = LC.run_b4(W, "J", B["g"]["PED"]["J"])
    other = LC.other_stocks(W, lambda s, X: B["gp"]["PED"]["Jx"] if s == "Jx" else np.zeros(len(X), bool))
    res["cand"]["PED"], res["other"]["PED"] = cand, other
    res["frac"]["PED"] = {"J": float((B["g"]["PED"]["J"] & ~tbf["J"]).mean())}
    res["stage1"]["PED"] = R12.stage1_j(cand["J"], base["J"], other.get("Jx"))
    for k in ("DXD", "HOL"):
        cand = {e: LC.run_b4(W, e, B["g"][k][e]) for e in LC.ERAS}
        other = LC.other_stocks(W, lambda s, X, _k=k: B["gp"][_k].get(s, np.zeros(len(X), bool)))
        res["cand"][k], res["other"][k] = cand, other
        res["frac"][k] = {e: float((B["g"][k][e] & ~tbf[e]).mean()) for e in LC.ERAS}
        res["stage1"][k] = R12.stage1_all(cand, base, other)
    res["seconds"] = round(time.time() - t0)
    f = R1._f
    L = [f"# 第十二个研究循环第 7 轮：决算后 / 权利落ち前 / 长假前 PED / DXD / HOL（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", ""]
    s, o = res["stage1"]["PED"], res["other"]["PED"].get("Jx") or {}
    d = s["d"]
    L.append(f"- **PED**（选股·决算后，路线 J）：J Calmar 差 {f(d['calmar'], '{:+.3f}')}、胜率差 {f(d['win'], '{:+.2f}')} pp、每笔差 {f(d['mean'], '{:+.3f}')} pp、"
             f"两半 {f(d['h1'], '{:+.3f}')} / {f(d['h2'], '{:+.3f}')}、多挡 {res['frac']['PED']['J'] * 100:.1f}%；Jx 挡 {o.get('gone_n')} / {o.get('n')}、"
             f"保留的胜率差 {f(o.get('dwin'), '{:+.2f}')} pp、每笔差 {f(o.get('dmean'), '{:+.3f}')} pp；JA {'✓' if s['routes']['JA']['ok'] else '✗'}、"
             f"JB {'✓' if s['routes']['JB']['ok'] else '✗'} → **{'第一关全过' if s['ok'] else R12.FAIL1}**")
    for k in ("DXD", "HOL"):
        s = res["stage1"][k]
        A, Bq, o = s["routes"]["A"], s["routes"]["B"], res["other"][k]
        L.append(f"- **{k}**（{FAMILY[k]}，路线 A / B）：" + "、".join(
            f"{e} Calmar {f(base[e]['calmar'])} → {f(res['cand'][k][e]['calmar'])}、胜率 {f(base[e]['win'], '{:.1f}')} → {f(res['cand'][k][e]['win'], '{:.1f}')}%"
            f"（多挡 {res['frac'][k][e] * 100:.1f}%）" for e in LC.ERAS)
            + f"；路线 A（合计 {f(A['sum'], '{:+.3f}')}）" + "、".join(f"{x} {'✓' if A[x] else '✗'}" for x in ("A1", "A2", "A3", "V4"))
            + f"；路线 B（胜率差 {f(Bq['dwin'], '{:+.2f}')} pp、每笔 {f(Bq['dmean'], '{:+.3f}')} pp）" + "、".join(f"{x} {'✓' if Bq[x] else '✗'}" for x in ("B1", "B2", "B3", "V4"))
            + "；" + "；".join(f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}、{f(o[x]['dwin'], '{:+.2f}')} pp、{f(o[x]['dmean'], '{:+.3f}')} pp" for x in ("W", "Jx", "Zx") if x in o)
            + f" → **{'第一关全过' if s['ok'] else R12.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
