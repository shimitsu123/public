"""loop12_r03_fund3.py — 第十二个研究循环第 3 轮：自有资本比率 / 销售增长 / 营业利润率变化当买入过滤（规则 scripts/research_loop12.py 路线 J）。
（2026-10-12 登记；先提交后只运行一次。）

做法（路线 J；看过第 1、2 轮的结果之后设计，但不是它们的变体）：
  EQL〔选股·财务质量〕：最近一次决算短信的自有资本比率 < 30% → 不买；银行 / 保险 / 证券・商品先物 / 其他金融（东证 33 业种）不适用（不挡）。
  SAG〔选股·成长〕：最近一次决算短信的累计销售额 ÷ 上年同期（同一期间类型、决算期末早一年）− 1 < 0 → 不买（销售额 ≤ 0 或缺 → 不挡）。
  OMG〔选股·利润率〕：最近一次决算短信的累计营业利润率（营业利润 ÷ 销售额）比上年同期低 1 pp 以上 → 不买（没有营业利润的公司 → 不挡）。
  都只用开示日 < 信号日、400 天以内的；缺值不挡；都不是事后组合。
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

ROUND = 3
IDS = ("EQL", "SAG", "OMG")
FAMILY = {"EQL": "选股·财务质量", "SAG": "选股·成长", "OMG": "选股·利润率"}
OUT = "loop12_r03_fund3"
EQ_MIN, SAG_MAX, OMG_MAX = 0.30, 0.0, -1.0
FIN_S33 = {"銀行業", "保険業", "証券、商品先物取引業", "その他金融業"}


def derive3(F: pd.DataFrame) -> pd.DataFrame:
    """每条决算短信：eqar、sag（累计销售额同比 %）、omg（累计营业利润率同比 pp）；上年同期 = 同一 ticker、同一期间类型、决算期末早一年。"""
    F = F.copy()
    F["fy"] = F["fye"].str[:4]
    F["key"] = F["ticker"] + "|" + F["per"]
    last = {}
    rows = []
    for r in F.sort_values(["ticker", "date"], kind="mergesort").to_dict("records"):
        prev = last.get((r["key"], str(int(r["fy"]) - 1) if r["fy"].isdigit() else ""))
        s, op = r["Sales"], r["OP"]
        sag = omg = np.nan
        if prev is not None and np.isfinite(s) and np.isfinite(prev["Sales"]) and prev["Sales"] > 0 and s > 0:
            sag = (s / prev["Sales"] - 1) * 100
            if np.isfinite(op) and np.isfinite(prev["OP"]):
                omg = (op / s - prev["OP"] / prev["Sales"]) * 100
        if r["fy"].isdigit():
            last[(r["key"], r["fy"])] = {"Sales": s, "OP": op}
        rows.append({"ticker": r["ticker"], "date": r["date"], "eqar": r["EqAR"], "sag": sag, "omg": omg})
    return pd.DataFrame(rows)


def _fin(tickers) -> np.ndarray:
    import json as _j
    from qbreak import paths
    s33 = (_j.loads((paths.PROJECT_ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8")).get("s33") or {})
    return np.array([s33.get(str(t).split(".")[0], "") in FIN_S33 for t in tickers], bool)


def features(F: pd.DataFrame, tickers, dates, fa: dict, W: dict | None = None) -> pd.DataFrame:
    eq = LC.asof(F, "eqar", tickers, dates)
    eq = np.where(_fin(tickers), np.nan, eq)
    return pd.DataFrame({"eqar": eq, "sag": LC.asof(F, "sag", tickers, dates), "omg": LC.asof(F, "omg", tickers, dates)})


def gates_of(X: pd.DataFrame, _cut: float = 0.0) -> dict[str, np.ndarray]:
    return {"EQL": (X["eqar"] < EQ_MIN).fillna(False).to_numpy(bool),
            "SAG": (X["sag"] < SAG_MAX).fillna(False).to_numpy(bool),
            "OMG": (X["omg"] < OMG_MAX).fillna(False).to_numpy(bool)}


def build(W: dict) -> dict:
    F = derive3(LC.fins_rows())
    S = LC.signals(W, "J")
    XJ = features(F, S["ticker"], S["date"], W["SM"]["J"]["fa"], W)
    cut = 0.0
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
    print(json.dumps({"same_as_b4": bool(same), "cut": 0, "coverage": B["coverage"],
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
    res = {"loop": 12, "round": ROUND, "ids": list(IDS), "family": FAMILY, "code": code, "dirty": dirty, "cut": 0,
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
    L = [f"# 第十二个研究循环第 3 轮：自有资本比率 / 销售增长 / 营业利润率变化 EQL / SAG / OMG（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则 scripts/research_loop12.py 路线 J）", "",
         f"基准 B4（B3 + TBF）的 J 年代：Calmar {_f(b['calmar'])}、最大回撤 {_f(b['dd'], '{:.2f}')}%、两半 {_f(b['h1'])} / {_f(b['h2'])}、"
         f"个股 {b['n']} 笔、胜率 {_f(b['win'], '{:.1f}')}%、每笔 {_f(b['mean'], '{:+.2f}')}%；"
         f"特征覆盖（J 信号 {res['coverage']['signals']} 个）：自有资本比率 {res['coverage']['eqar']}、销售同比 {res['coverage']['sag']}、利润率同比 {res['coverage']['omg']}", "",
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
