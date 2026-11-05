"""loop12_r02_fund2.py — 第十二个研究循环第 2 轮：J-Quants 决算进度 / 现金流 / 信用倍率当买入过滤（规则 scripts/research_loop12.py 路线 J）。
（2026-10-12 登记；先提交后只运行一次。）

做法（数据只有 2016-10 以后 → 路线 J：J 年代 + Jx 池；Z / E 不挡；看过第 1 轮的结果之后设计，但不是第 1 轮做法的变体）：
  PRG〔选股·业绩指引〕：最近一次季度（1Q〜3Q）决算短信的利润进度率（累计实绩 ÷ 当期予想 × 100）比季节基准（25 / 50 / 75%）低 10 pp 以上 → 不买
       （利润档同第 1 轮；予想 ≤ 0 → 算不出、不挡；开示离信号日 > 120 天 → 太旧、不挡）。
  FCN〔选股·财务质量〕：最近一个年度（FY）决算的自由现金流（营业 CF + 投资 CF）< 0 → 不买（400 天以内）。
  MRH〔选股·信用〕：信号日能用的最近一周信用倍率（买残 ÷ 卖残；公布日的下一个交易日起才用）≥ J 信号的 80 分位 → 不买（多头拥挤；
       以前测过的是「信用余额 ÷ 成交量」与 4 周变化，没测过倍率本身；卖残 0 → 算不出、不挡；30 天以内）。
  缺值不挡；都不是事后组合。
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

ROUND = 2
IDS = ("PRG", "FCN", "MRH")
FAMILY = {"PRG": "选股·业绩指引", "FCN": "选股·财务质量", "MRH": "选股·信用"}
OUT = "loop12_r02_fund2"
PRG_MIN, MR_Q = -10.0, 80
_M: dict = {}


def margin(W: dict) -> pd.DataFrame:
    import jq_extra_data as JX
    if "m" not in _M:
        days = pd.DatetimeIndex(sorted(set(W["ctx"]["J"]["days"])))
        M = JX.margin_weekly(days)
        _M["m"] = M.rename(columns={"avail": "adate"})[["ticker", "adate", "ratio"]].rename(columns={"adate": "date"})
    return _M["m"]


def features(F: pd.DataFrame, tickers, dates, fa: dict, W: dict | None = None) -> pd.DataFrame:
    prg = LC.asof(F, "prg", tickers, dates, stale_days=120)
    fcf = LC.asof(F, "fcf", tickers, dates, stale_days=400)
    mr = LC.asof(margin(W), "ratio", tickers, dates, stale_days=30) if W is not None else np.full(len(tickers), np.nan)
    return pd.DataFrame({"prg": prg, "fcf": fcf, "mr": mr})


def gates_of(X: pd.DataFrame, mr_cut: float) -> dict[str, np.ndarray]:
    return {"PRG": (X["prg"] < PRG_MIN).fillna(False).to_numpy(bool),
            "FCN": (X["fcf"] < 0).fillna(False).to_numpy(bool),
            "MRH": (X["mr"] >= mr_cut).fillna(False).to_numpy(bool)}


def build(W: dict) -> dict:
    F = LC.derive(LC.fins_rows())
    S = LC.signals(W, "J")
    XJ = features(F, S["ticker"], S["date"], W["SM"]["J"]["fa"], W)
    cut = float(np.nanpercentile(XJ["mr"], MR_Q))
    gJ = gates_of(XJ, cut)
    XP = {}
    for s in ("Jx",):
        X = LC.pool_x(W, s)
        XP[s] = features(F, X["ticker"], X["date"], W["SM"]["J2"]["fa"], W)
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
    print(json.dumps({"same_as_b4": bool(same), "mr_cut": round(B["cut"], 3), "coverage": B["coverage"],
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
    res = {"loop": 12, "round": ROUND, "ids": list(IDS), "family": FAMILY, "code": code, "dirty": dirty, "mr_cut": B["cut"],
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
    L = [f"# 第十二个研究循环第 2 轮：决算进度 / 现金流 / 信用倍率当买入过滤 PRG / FCN / MRH（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则 scripts/research_loop12.py 路线 J）", "",
         f"基准 B4（B3 + TBF）的 J 年代：Calmar {_f(b['calmar'])}、最大回撤 {_f(b['dd'], '{:.2f}')}%、两半 {_f(b['h1'])} / {_f(b['h2'])}、"
         f"个股 {b['n']} 笔、胜率 {_f(b['win'], '{:.1f}')}%、每笔 {_f(b['mean'], '{:+.2f}')}%；信用倍率门槛（J 信号 80 分位）{res['mr_cut']:.2f}；"
         f"特征覆盖（J 信号 {res['coverage']['signals']} 个）：进度 {res['coverage']['prg']}、FCF {res['coverage']['fcf']}、倍率 {res['coverage']['mr']}", "",
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
