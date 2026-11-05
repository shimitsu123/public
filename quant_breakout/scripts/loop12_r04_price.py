"""loop12_r04_price.py — 第十二个研究循环第 4 轮：三个年代都有数据的新角度（彩票型 / 个股季节性 / 年内低位）（规则 scripts/research_loop12.py 路线 A / B）。
（2026-10-12 登记；先提交后只运行一次。看过第 1〜3 轮之后设计，但不是它们的变体 → 不是事后组合，V6 不适用。）

做法（只用信号日为止的日线；门槛「前 / 后 20%」= 那个年代全部 W2 信号（N225）里的分位，登记时只用特征分布算；池子用对应年代的门槛：W → E、Jx → J、Zx → Z）：
  MXR〔选股·彩票型〕：信号日之前 21 个交易日（不含信号日）里最大的单日涨幅 ≥ 该年代信号的 80 分位 → 不买（MAX 效应：Bali, Cakici & Whitelaw 2011）。
  SSM〔选股·个股季节性〕：成交月（信号日的下一个交易日所在的日历月）这只票过去 1〜10 年同一个日历月的平均月收益（至少 5 年）≤ 该年代信号的 20 分位 → 不买
       （个股季节性：Heston & Sadka 2008；不够 5 年 → 不挡）。
  LOW〔选股·位置〕：信号日收盘 ÷ 之前 250 个交易日（含信号日）最低收盘 − 1 < 20% → 不买（年内低位附近的突破）。
第一关：research_loop12.stage1_all（路线 A / B + V4：W、Jx 同方向）。第二关另行登记。
运行：python scripts/loop12_r04_price.py（第一关）；--wiring（登记前：全 False = B4、只数挡掉的个数）。输出 var/out/loop12_r04_price.md / .json。非投资建议。
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
import research_loop12 as R12                                                # noqa: E402

ROUND = 4
IDS = ("MXR", "SSM", "LOW")
FAMILY = {"MXR": "选股·彩票型", "SSM": "选股·个股季节性", "LOW": "选股·位置"}
OUT = "loop12_r04_price"
SM_OF = {"Z": "Z", "E": "E", "J": "J", "W": "W", "Jx": "J2", "Zx": "Zx"}
ERA_OF = {"W": "E", "Jx": "J", "Zx": "Z"}
MXR_Q, SSM_Q, LOW_MAX = 80, 20, 0.20


def feats_one(df: pd.DataFrame | None, d: pd.Timestamp) -> tuple[float, float, float]:
    if df is None or d not in df.index:
        return np.nan, np.nan, np.nan
    c = df["Close"].astype(float)
    i = c.index.get_loc(d)
    r = c.pct_change()
    mx = float(r.iloc[max(0, i - 21):i].max()) if i >= 21 else np.nan
    lo = float(c.iloc[max(0, i - 249):i + 1].min()) if i >= 249 else np.nan
    low = float(c.iloc[i] / lo - 1) if lo and np.isfinite(lo) and lo > 0 else np.nan
    m = c.iloc[:i + 1].resample("ME").last().pct_change().dropna()     # 只用信号日为止的月收益（最后一个月可能不完整 → 不用这一年的）
    fill_m = (d + pd.offsets.BDay(1)).month
    past = m[(m.index.month == fill_m) & (m.index.year < d.year) & (m.index.year >= d.year - 10)]
    ssm = float(past.mean()) if len(past) >= 5 else np.nan
    return mx, ssm, low


def features(fa: dict, tickers, dates) -> pd.DataFrame:
    rows = [feats_one(fa.get(str(t)), pd.Timestamp(d)) for t, d in zip(tickers, pd.to_datetime(np.asarray(dates)))]
    return pd.DataFrame(rows, columns=["mxr", "ssm", "low"])


def gates_of(X: pd.DataFrame, cut: dict) -> dict[str, np.ndarray]:
    return {"MXR": (X["mxr"] >= cut["mxr"]).fillna(False).to_numpy(bool),
            "SSM": (X["ssm"] <= cut["ssm"]).fillna(False).to_numpy(bool),
            "LOW": (X["low"] < LOW_MAX).fillna(False).to_numpy(bool)}


def build(W: dict) -> dict:
    XS, cut, g = {}, {}, {}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        XS[e] = features(W["SM"][SM_OF[e]]["fa"], S["ticker"], S["date"])
        cut[e] = {"mxr": float(np.nanpercentile(XS[e]["mxr"], MXR_Q)), "ssm": float(np.nanpercentile(XS[e]["ssm"], SSM_Q))}
        g[e] = gates_of(XS[e], cut[e])
    XP = {}
    for s in ("W", "Jx", "Zx"):
        if s in W["D"]:
            X = LC.pool_x(W, s)
            XP[s] = features(W["SM"][SM_OF[s]]["fa"], X["ticker"], X["date"])
    cov = {e: {k: int(XS[e][k].notna().sum()) for k in XS[e].columns} | {"signals": int(len(XS[e]))} for e in LC.ERAS}
    return {"XS": XS, "cut": cut, "g": g, "XP": XP, "coverage": cov}


def pool_gate(B: dict, k: str):
    def fn(s, X):
        if s not in B["XP"]:
            return np.zeros(len(X), bool)
        return gates_of(B["XP"][s], B["cut"][ERA_OF[s]])[k]
    return fn


def wiring() -> int:
    W = LC.load()
    B = build(W)
    same = all(LC.run_b4(W, e, np.zeros(len(LC.signals(W, e)), bool)) == LC.run_b4(W, e) for e in LC.ERAS)
    extra = {k: {e: int((B["g"][e][k] & ~np.asarray(W["tbf"][e], bool)).sum()) for e in LC.ERAS} for k in IDS}
    pools = {k: {s: int(pool_gate(B, k)(s, LC.pool_x(W, s)).sum()) for s in B["XP"]} for k in IDS}
    print(json.dumps({"same_as_b4": bool(same), "cut": B["cut"], "coverage": B["coverage"], "blocked_extra": extra, "pool_blocked": pools,
                      "pool_n": {s: int(len(B["XP"][s])) for s in B["XP"]}}, ensure_ascii=False, default=float))
    return 0 if same else 1


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = R1.git_head()
    W = LC.load()
    B = build(W)
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    res = {"loop": 12, "round": ROUND, "ids": list(IDS), "family": FAMILY, "code": code, "dirty": dirty, "cut": B["cut"], "coverage": B["coverage"],
           "base": base, "cand": {}, "stage1": {}, "other": {}, "frac": {}}
    for k in IDS:
        cand = {e: LC.run_b4(W, e, B["g"][e][k]) for e in LC.ERAS}
        other = LC.other_stocks(W, pool_gate(B, k))
        res["cand"][k], res["other"][k] = cand, other
        res["frac"][k] = {e: float((B["g"][e][k] & ~np.asarray(W["tbf"][e], bool)).mean()) for e in LC.ERAS}
        res["stage1"][k] = R12.stage1_all(cand, base, other)
        print(f"{k} 完成（{time.time() - t0:.0f}s）", flush=True)
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    import research_loop10 as R10
    f = R1._f
    L = [f"# 第十二个研究循环第 4 轮：彩票型 / 个股季节性 / 年内低位 MXR / SSM / LOW（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；路线 A / B）", "",
         "| 做法 | 年代 | Calmar（B4 → 候选） | 胜率 | 每笔 | 多挡的比例 |", "|---|---|---|---|---|---|"]
    for k in res["ids"]:
        for e in LC.ERAS:
            b, c = res["base"][e], res["cand"][k][e]
            L.append(f"| {k} | {e} | {f(b['calmar'])} → {f(c['calmar'])} | {f(b['win'], '{:.1f}')} → {f(c['win'], '{:.1f}')}% | "
                     f"{f(b['mean'], '{:+.2f}')} → {f(c['mean'], '{:+.2f}')}% | {res['frac'][k][e] * 100:.1f}% |")
    L += ["", "## 第一关", ""]
    for k in res["ids"]:
        s = res["stage1"][k]
        A, Bq = s["routes"]["A"], s["routes"]["B"]
        o = res["other"][k]
        pools = "；".join(f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}、保留的胜率差 {f(o[x]['dwin'], '{:+.2f}')} pp、每笔差 {f(o[x]['dmean'], '{:+.3f}')} pp"
                         for x in ("W", "Jx", "Zx") if x in o)
        L.append(f"- **{k}**（{FAMILY[k]}）：路线 A " + "、".join(f"{x} {'✓' if A[x] else '✗'}" for x in ("A1", "A2", "A3", "V4"))
                 + f"（Calmar 差合计 {f(A['sum'], '{:+.3f}')}）；路线 B " + "、".join(f"{x} {'✓' if Bq[x] else '✗'}" for x in ("B1", "B2", "B3", "V4"))
                 + f"（合起来胜率差 {f(Bq['dwin'], '{:+.2f}')} pp、每笔 {f(Bq['dmean'], '{:+.3f}')} pp）；{pools} → **{'第一关全过' if s['ok'] else R12.FAIL1}**")
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
