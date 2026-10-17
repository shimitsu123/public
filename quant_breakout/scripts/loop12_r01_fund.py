"""loop12_r01_fund.py — 第十二个研究循环第 1 轮：J-Quants 决算数据当买入过滤（以前没用过的三个角度；规则 scripts/research_loop12.py 路线 J）。
（2026-10-12 登记；先提交后只运行一次。）

做法（数据只有 2016-10 以后 → 路线 J：J 年代 + Jx 池；Z / E 不挡）：
  PBH〔选股·估值〕：信号日的 PBR = 信号日收盘 ÷ 最近一次决算短信的 BPS（开示日 < 信号日、400 天以内）；
       PBR ≥ 门槛 → 不买。门槛 = J 年代全部 W2 信号（N225）的 PBR 的 80 分位（登记时只用特征分布算、写进结果；Jx 用同一个数）。
  ROL〔选股·财务质量〕：最近一次决算短信的 ROE < 5%（J-Quants 字段是比率 → < 0.05）→ 不买（常用的「资本效率低」线；事先定、不调）。
  NXG〔选股·业绩指引〕：最近一次年度决算（FY）给的下期利润予想 ÷ 本期实绩 − 1 < 0（指引下调）→ 不买
       （利润档：有营业利润用营业利润，银行 / 保险用经常利润，再没有用净利润；本期实绩 ≤ 0 → 算不出、不挡）。
  缺值（没有决算数据 / 太旧）→ 不挡。都不是事后组合（以前没用过这些数据当过滤）→ V6 不适用。
第一关：research_loop12.stage1_j（JA / JB + Jx 同方向）；三个年代路线 A / B 只报告（Z / E 不变）。第二关另行登记。
运行：python scripts/loop12_r01_fund.py（第一关）；--wiring（登记前：全 False = B4、只数挡掉的个数，不看结果）。
输出 var/out/loop12_r01_fund.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402
import research_loop12 as R12                                                # noqa: E402

ROUND = 1
IDS = ("PBH", "ROL", "NXG")
FAMILY = {"PBH": "选股·估值", "ROL": "选股·财务质量", "NXG": "选股·业绩指引"}
OUT = "loop12_r01_fund"
PBR_Q, ROE_MIN, NXG_MAX = 80, 0.05, 0.0                            # J-Quants 的 ROE 是比率（0.073 = 7.3%）


def features(F: pd.DataFrame, tickers, dates, fa: dict) -> pd.DataFrame:
    bps = LC.asof(F, "BPS", tickers, dates)
    px = LC.close_at(fa, tickers, dates)
    pbr = np.where(bps > 0, px / np.where(bps > 0, bps, np.nan), np.nan)
    return pd.DataFrame({"pbr": pbr, "roe": LC.asof(F, "roe", tickers, dates), "nxg": LC.asof(F, "nxg", tickers, dates)})


def gates_of(X: pd.DataFrame, pbr_cut: float) -> dict[str, np.ndarray]:
    return {"PBH": (X["pbr"] >= pbr_cut).fillna(False).to_numpy(bool),
            "ROL": (X["roe"] < ROE_MIN).fillna(False).to_numpy(bool),
            "NXG": (X["nxg"] < NXG_MAX).fillna(False).to_numpy(bool)}


def build(W: dict) -> dict:
    F = LC.derive(LC.fins_rows())
    S = LC.signals(W, "J")
    XJ = features(F, S["ticker"], S["date"], W["SM"]["J"]["fa"])
    cut = float(np.nanpercentile(XJ["pbr"], PBR_Q))
    gJ = gates_of(XJ, cut)
    XP = {}
    for s in ("Jx",):
        X = LC.pool_x(W, s)
        XP[s] = features(F, X["ticker"], X["date"], W["SM"]["J2"]["fa"])
    return {"F": F, "XJ": XJ, "cut": cut, "gJ": gJ, "XP": XP,
            "coverage": {k: int(XJ[k].notna().sum()) for k in XJ.columns} | {"signals": int(len(S))}}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[2]
    h = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "quant_breakout/scripts", "quant_breakout/qbreak"],
                                capture_output=True, text=True).stdout.strip())
    return h, dirty


def wiring() -> int:
    W = LC.load()
    B = build(W)
    S = LC.signals(W, "J")
    tbf = np.asarray(W["tbf"]["J"], bool)
    same = LC.run_b4(W, "J", np.zeros(len(S), bool)) == LC.run_b4(W, "J")
    print(json.dumps({"same_as_b4": bool(same), "pbr_cut": round(B["cut"], 3), "coverage": B["coverage"],
                      "blocked_extra": {k: int((g & ~tbf).sum()) for k, g in B["gJ"].items()},
                      "jx_blocked": {k: int(v.sum()) for k, v in gates_of(B["XP"]["Jx"], B["cut"]).items()},
                      "jx_n": int(len(B["XP"]["Jx"]))}, ensure_ascii=False))
    return 0 if same else 1


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = LC.load()
    B = build(W)
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    res = {"loop": 12, "round": ROUND, "ids": list(IDS), "family": FAMILY, "code": code, "dirty": dirty, "pbr_cut": B["cut"],
           "coverage": B["coverage"], "base": base, "cand": {}, "stage1": {}, "stage1_all": {}, "other": {}, "frac": {}}
    S = LC.signals(W, "J")
    tbf = np.asarray(W["tbf"]["J"], bool)
    for k in IDS:
        g = B["gJ"][k]
        cand = dict(base)
        cand["J"] = LC.run_b4(W, "J", g)
        jx_gate = gates_of(B["XP"]["Jx"], B["cut"])[k]
        other = LC.other_stocks(W, lambda s, X, _g=jx_gate: _g if s == "Jx" else np.zeros(len(X), bool))
        res["cand"][k] = cand
        res["other"][k] = other
        res["frac"][k] = {"J": float((g & ~tbf).sum() / len(S))}
        res["stage1"][k] = R12.stage1_j(cand["J"], base["J"], other.get("Jx"))
        res["stage1_all"][k] = R12.stage1_all(cand, base, other)
        print(f"{k} 完成（{time.time() - t0:.0f}s）", flush=True)
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}"):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    b = res["base"]["J"]
    L = [f"# 第十二个研究循环第 1 轮：J-Quants 决算数据当买入过滤 PBH / ROL / NXG（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则 scripts/research_loop12.py 路线 J）", "",
         f"基准 B4（B3 + TBF）的 J 年代：Calmar {_f(b['calmar'])}、最大回撤 {_f(b['dd'], '{:.2f}')}%、两半 {_f(b['h1'])} / {_f(b['h2'])}、"
         f"个股 {b['n']} 笔、胜率 {_f(b['win'], '{:.1f}')}%、每笔 {_f(b['mean'], '{:+.2f}')}%；PBR 门槛（J 信号 80 分位）{res['pbr_cut']:.2f}；"
         f"特征覆盖（J 信号 {res['coverage']['signals']} 个）：PBR {res['coverage']['pbr']}、ROE {res['coverage']['roe']}、指引 {res['coverage']['nxg']}", "",
         "| 做法 | J：Calmar 差 | 胜率差 | 每笔差 | 两半差 | 回撤差 | 多挡的信号比例 | Jx：挡 / 全部、保留的胜率差、每笔差 | JA | JB | 第一关 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in res["ids"]:
        s = res["stage1"][k]
        d = s["d"]
        o = res["other"][k].get("Jx") or {}
        L.append(f"| {k}（{FAMILY[k]}） | {_f(d['calmar'], '{:+.3f}')} | {_f(d['win'], '{:+.2f}')} pp | {_f(d['mean'], '{:+.3f}')} pp | "
                 f"{_f(d['h1'], '{:+.3f}')} / {_f(d['h2'], '{:+.3f}')} | {_f(d['dd'], '{:+.2f}')} pp | {res['frac'][k]['J'] * 100:.1f}% | "
                 f"{o.get('gone_n')} / {o.get('n')}、{_f(o.get('dwin'), '{:+.2f}')} pp、{_f(o.get('dmean'), '{:+.3f}')} pp | "
                 f"{'✓' if s['routes']['JA']['ok'] else '✗'} | {'✓' if s['routes']['JB']['ok'] else '✗'} | "
                 f"**{'全过 → 另行登记第二关' if s['ok'] else R12.FAIL1}** |")
    L += ["", f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring", action="store_true")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
