"""model_switch_study.py — 「按当前局势判断用哪个模型、自动切换」第三轮：先检验「下个月哪个模型更好」能不能从现在的局势预测
（2026-10-05 登记；用户：「进行按照当前局势进行判断用哪个模型比较好自动切换交易模型研究」；先提交后只运行一次；登记后代码不改）

以前做过的（结论不变，这次不重复）：
- core_switch_study（6c64038，2026-09-30）：核心层 8 个模型按状态表（S1）、过去 36 个月择优（S2）、等权（S3）、全叠加（S4）切换 → 都不通过；
  「每月事后选对」的上限极高，但按过去 36 个月选追不上（模型好坏一段一换）。
- phase_model_study（709f309）：核心层按手写四种局面（预计大涨 / 预计大跌 / 熊 / 普通牛）学「局面 → 模型」→ 都不通过；只有「预计大涨」三个年代方向一致。
- 按月调参（c4b673c、fcccdb0）、按政策状态调参（19330f4）、按大盘效率比换卖法（regime_exit_explore，只探索）→ 都没用。
这次新的：① 判断「局势」换成数据驱动的方法 + 短窗口：KNN 相似局势（8 个状态变量）、HMM 隐藏局势、模型动量 1 / 3 / 12 个月（以前只试过 36 个月）、
趋势 × 波动 6 格；② 菜单除了核心层的 8 个模型，加上个股层的三种卖法；③ 按研究习惯（局面 → 模型类先看局面有没有信息）先过「可预测性」门槛，
过了才另外登记账户级的切换检验。

菜单（每个模型的「月结果」）：
- 核心层 K（只有核心，1990-01〜2026-09；core_switch_study 的同一套合成价与配比、修正后的汇率口径、换手成本 0.1%）：
  A S&P500 + 牛熊 / Q 纳指 1545 + 牛熊（现行，判定里的「现行」）/ B 常配黄金 20% / C 日元走强时对冲 / D 5〜10 月核心 50% / E 深跌加仓 / F 择强指数 / G 晚卖守卫；
  月结果 = 月末净值的变化（%）；当月月末就知道（lag 0）。
- 个股层 S（日経225 W2 信号 Z / E / J + 扩大池 Zx / W / Jx 里 B3 会买的信号；第十一个循环的假想单笔，扣来回成本）：
  tight 收紧（吊灯 k 2、最长 60 天）/ base B3（k 3、60 天，现行）/ wide 放宽（k 4、90 天）；
  某月的结果 = 信号日在那个月、三种卖法都有结果的信号的每笔平均（%）；要等卖出 → 5 个月后才算已知（lag 5）。
状态（每月末，只用到那天为止的数据；日経 / S&P500 = Yahoo 缓存，VIX / USD/JPY / 美国 10 年 / Baa − 10 年 = FRED）：
  KNN 的 8 个变量：日経 离 200 日线（%）、日経 60 日实现波动（%）、日経 60 日效率比、S&P500 离 200 日线（%）、VIX、USD/JPY 63 日涨跌（%）、
  美国 10 年国债 126 日变化（pp）、Baa − 10 年信用利差（pp）→ 到当月为止的扩张窗口标准化（≥ 36 个月）；
  HMM 的 4 个变量：S&P500 月对数收益、log(S&P500 21 日实现波动)、日経 月对数收益、log(日経 21 日实现波动)
  （两态、每年 1 月末用到那时的全部月份重新拟合、第一次 ≥ 60 个月；状态按 S&P500 波动从低到高编号）；
  TAB：S&P500 / 日経 离 200 日线的正负（两个都正 / 一正一负 / 都负）× VIX 是否 ≥ 到当月为止的中位数。
判断法（每月末决定下个月用哪个模型）：KNN（最近 12 个月、至少 24 个已知月）、HMM（同状态 ≥ 12 个已知月，否则现行）、
  MOM1 / MOM3 / MOM12（最近 1 / 3 / 12 个已知月平均最好）、TAB（同格 ≥ 12 个已知月，否则现行）。
  每个菜单只算「全部判断法都给得出选择」的共同月份（核心层 1996-01 起的结果月）。
门槛（事先写定；12 个检验 = 2 个菜单 × 6 个判断法；四条都要）：
  ① g =「选到的模型 − 菜单等权平均」的平均 > 0 且 Newey–West t（3 期）≥ 2.0；
  ② 三个年代的 g 平均都 > 0（K：P 1996-01〜2006-09 / E 2006-10〜2016-09 / J 2016-10〜2026-09；S：Z 2001-01〜2006-09 / E 2006-10〜2016-09 /
     J 2017-01〜2026-09，按结果月）；
  ③ h =「选到的 − 现行（K = Q，S = base）」的平均 > 0；
  ④ 选择序列整体循环错开（12 个月以上的全部错法）的对照：经验 p ≤ 0.05 ÷ 12 ≈ 0.0042（Bonferroni）。
  过了的（菜单 × 判断法）→ 另外登记账户级的切换检验（第二关，用户决定）；都不过 →「现在看得到的局势判断不出下个月哪个模型更好」→ 不做切换。
另报（不判定）：每月事后选对的上限、各年代事后最好的固定模型、各判断法选各模型的比例、现在（2026-09 月末）各判断法会选哪个。
事前预期：以前两次核心层切换与按月调参都不过、统计复查里研究循环的做法三个年代方向与随机无异 → 通过的可能约 5〜10%。
运行：python scripts/model_switch_study.py [--check]（--check = 登记前核对：只数个数，不看任何收益；个股层的假想单笔存进
var/cache/model_switch_singles.pkl（不入库），正式运行直接读）。输出 var/out/model_switch_study.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from qbreak import model_switch as MS                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

OUT = "model_switch_study"
FIRST, LAST = "1990-01", "2026-09"
K_MODELS = ("A", "Q", "B", "C", "D", "E", "F", "G")
K_NAMES = {"A": "S&P500 + 牛熊", "Q": "纳指 + 牛熊（现行）", "B": "常配黄金 20%", "C": "日元走强时对冲", "D": "5〜10 月核心 50%",
           "E": "深跌加仓", "F": "择强指数", "G": "晚卖守卫"}
S_MODELS = ("tight", "base", "wide")
S_NAMES = {"tight": "收紧 k 2 / 60 天", "base": "B3 k 3 / 60 天（现行）", "wide": "放宽 k 4 / 90 天"}
MENUS = {"K": {"models": K_MODELS, "base": "Q", "lag": 0,
               "eras": {"P": ("1996-01", "2006-09"), "E": ("2006-10", "2016-09"), "J": ("2016-10", "2026-09")}},
         "S": {"models": S_MODELS, "base": "base", "lag": 5,
               "eras": {"Z": ("2001-01", "2006-09"), "E": ("2006-10", "2016-09"), "J": ("2017-01", "2026-09")}}}
METHODS = ("KNN", "HMM", "MOM1", "MOM3", "MOM12", "TAB")
KNN_K, KNN_MIN, MAP_MIN, Z_MIN, HMM_MIN = 12, 24, 12, 36, 60
MIN_SHIFT = 12
P_MAX = 0.05 / 12
T_MIN = 2.0
K_START = "1996-01"                                                          # 核心层共同结果月的起点（状态与 HMM 的预热之后）
POOL_ERA = {"Zx": "Z", "W": "E", "Jx": "J"}
SINGLES = "model_switch_singles.pkl"


# ───────────────────────── 状态 ─────────────────────────
def _close(name: str) -> pd.Series:
    from qbreak import trade_links as TL
    return TL.daily_close(paths.sub("cache"), name)


def _fred(sid: str) -> pd.Series:
    from qbreak import factors
    return factors.fred(sid, max_age_h=1e9).dropna()


def state_frames(months: pd.PeriodIndex) -> dict:
    """→ {"Z": KNN 的 8 个标准化变量, "X": 原值, "F": HMM 的 4 个变量, "cells": TAB 的格}。"""
    n225, spx = _close("idx_N225"), _close("idx_GSPC")
    vix, fx, us10, baa = _fred("VIXCLS"), _fred("DEXJPUS"), _fred("DGS10"), _fred("BAA10Y")
    X = pd.DataFrame({
        "n225_gap": MS.month_end(MS.sma_gap(n225), months),
        "n225_vol": MS.month_end(MS.realized_vol(n225, 60), months),
        "n225_er": MS.month_end(MS.efficiency_ratio(n225, 60), months),
        "spx_gap": MS.month_end(MS.sma_gap(spx), months),
        "vix": MS.month_end(vix, months),
        "usdjpy_63": MS.month_end((fx / fx.shift(63) - 1) * 100, months),
        "us10_126": MS.month_end(us10 - us10.shift(126), months),
        "baa10y": MS.month_end(baa, months),
    })
    mspx, mn = MS.month_end(spx, months), MS.month_end(n225, months)
    F = pd.DataFrame({"spx_r": np.log(mspx / mspx.shift(1)), "spx_v": np.log(MS.month_end(MS.realized_vol(spx, 21), months)),
                      "n225_r": np.log(mn / mn.shift(1)), "n225_v": np.log(MS.month_end(MS.realized_vol(n225, 21), months))})
    return {"X": X, "Z": MS.expanding_z(X, Z_MIN), "F": F,
            "cells": MS.trend_vol_cells(X["spx_gap"], X["n225_gap"], X["vix"], Z_MIN)}


# ───────────────────────── 菜单的月结果 ─────────────────────────
def core_menu(months: pd.PeriodIndex) -> pd.DataFrame:
    import core_switch_study as CS
    d = CS.load_data()
    out = {}
    for m in K_MODELS:
        eq = CS.core_sim(CS.model_weights(m, d["S"]), d["R"])
        me = eq.groupby(eq.index.to_period("M")).last()
        out[m] = me.pct_change() * 100
    return pd.DataFrame(out).reindex(months)


def build_singles(log=print) -> pd.DataFrame:
    """每个信号三种卖法的假想单笔（扣来回成本，%）：日経225 W2 信号（Z / E / J）+ 扩大池 B3 会买的信号（Zx / W / Jx）。"""
    import loop10_common as C10
    import loop11_common as LC
    import loop11_r01_cycle as R1
    W = LC.load()
    p0 = W["p0"]
    bt, rt = LC.bt_rt()
    rows = []

    def add(pool, era, X, fa):
        for t, d in zip(X["ticker"], pd.to_datetime(X["date"])):
            df = fa.get(t)
            r = {"pool": pool, "era": era, "ticker": str(t), "date": d}
            for m in S_MODELS:
                r[m] = float("nan") if df is None else LC.single_net(t, df, d, p0, bt, rt, R1.OPTIONS[m])
            rows.append(r)

    for e in LC.ERAS:
        S = LC.signals(W, e)
        add("N225", e, S, W["SM"][e]["fa"])
        log(f"日経225 {e}：{len(S)} 个信号")
    for s, fold, sm in C10.OTHER:
        if s in W["D"]:
            X = C10.kept_pool(W, s, fold)
            add(s, POOL_ERA[s], X, W["SM"][sm]["fa"])
            log(f"{s}：{len(X)} 个信号")
    return pd.DataFrame(rows)


def singles(log=print) -> pd.DataFrame:
    fp = paths.sub("cache") / SINGLES
    if fp.exists():
        return pickle.loads(fp.read_bytes())
    T = build_singles(log)
    fp.write_bytes(pickle.dumps(T))
    return T


def stock_menu(T: pd.DataFrame, months: pd.PeriodIndex) -> pd.DataFrame:
    """信号月 → 三种卖法都有结果的信号的每笔平均（%）。"""
    ok = T[list(S_MODELS)].notna().all(axis=1)
    X = T[ok].assign(m=pd.to_datetime(T.loc[ok, "date"]).dt.to_period("M"))
    return X.groupby("m")[list(S_MODELS)].mean().reindex(months)


# ───────────────────────── 判断与门槛 ─────────────────────────
def picks_for(method: str, st: dict, hmm_lab: pd.Series, P: pd.DataFrame, lag: int, base: str, months) -> pd.Series:
    out = {}
    for t in months:
        if method == "KNN":
            m = MS.knn_pick(st["Z"], P, t, lag, KNN_K, KNN_MIN)
        elif method == "HMM":
            m = MS.map_pick(hmm_lab, P, t, lag, MAP_MIN, base)
        elif method.startswith("MOM"):
            m = MS.mom_pick(P, t, lag, int(method[3:]))
        elif method == "TAB":
            m = MS.map_pick(st["cells"], P, t, lag, MAP_MIN, base)
        else:
            raise ValueError(method)
        out[t] = m
    return pd.Series(out, dtype=object)


def common_window(PK: dict[str, pd.Series], P: pd.DataFrame, start: str | None) -> list:
    """全部判断法都给得出选择、而且下一个月有结果的决定月。"""
    ts = None
    for s in PK.values():
        ok = set(s.dropna().index)
        ts = ok if ts is None else ts & ok
    ts = sorted(t for t in (ts or set()) if (t + 1) in P.index and P.loc[t + 1].notna().any())
    if start:
        ts = [t for t in ts if t + 1 >= pd.Period(start, "M")]
    return ts


def oracle(P: pd.DataFrame, ts: list) -> float | None:
    v = [float(P.loc[t + 1].max() - P.loc[t + 1].dropna().mean()) for t in ts if P.loc[t + 1].notna().any()]
    return round(float(np.mean(v)), 4) if v else None


def fixed_best(P: pd.DataFrame, ts: list, eras: dict) -> dict:
    out = {}
    for k, (a, b) in eras.items():
        u = [t + 1 for t in ts if pd.Period(a, "M") <= t + 1 <= pd.Period(b, "M")]
        if u:
            m = P.loc[u].mean()
            out[k] = {"best": str(m.idxmax()), "mean": {c: round(float(v), 3) for c, v in m.items()}}
    return out


def run_menu(name: str, P: pd.DataFrame, st: dict, hmm_lab: pd.Series, months, log=print) -> dict:
    cfg = MENUS[name]
    PK = {m: picks_for(m, st, hmm_lab, P, cfg["lag"], cfg["base"], months) for m in METHODS}
    ts = common_window(PK, P, K_START if name == "K" else None)
    res = {"window": [str(ts[0] + 1), str(ts[-1] + 1)] if ts else None, "n_dec": len(ts), "methods": {}}
    for m in METHODS:
        pk = PK[m].reindex(ts)
        G = MS.gains(pk, P, cfg["base"])
        pl = MS.shift_placebo(pk, P, cfg["base"], MIN_SHIFT)
        gt = MS.gate(G, cfg["eras"], pl, P_MAX, T_MIN)
        gt["share"] = {k: round(float(v) * 100, 1) for k, v in pk.value_counts(normalize=True).items()}
        res["methods"][m] = gt
        log(f"{name} {m}：{'通过' if gt['pass'] else '不通过'}")
    res["oracle"] = oracle(P, ts)
    res["fixed"] = fixed_best(P, ts, cfg["eras"])
    last = months[-1]
    res["now"] = {m: PK[m].get(last) for m in METHODS}
    return res


# ───────────────────────── 输出 ─────────────────────────
def _f(v, nd=3, sign=True):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def render(o: dict) -> str:
    ck = lambda b: "✓" if b else "✗"                                        # noqa: E731
    L = ["# 按当前局势判断用哪个模型（第三轮）：「下个月哪个模型更好」能不能预测？（登记后只运行一次；规则见脚本开头）", "",
         f"代码 {o['code']}；12 个检验（2 个菜单 × 6 个判断法）；通过要四条都满足（④ 经验 p ≤ {P_MAX:.4f}）。", "",
         "## 结论", f"- 通过的：{'、'.join(o['passed']) if o['passed'] else '没有'}"]
    for name, title, unit, names in (("K", "核心层 8 个模型（只有核心）", "月收益 %", K_NAMES), ("S", "个股层 三种卖法（假想单笔）", "每笔 %", S_NAMES)):
        r = o[name]
        eras = list(MENUS[name]["eras"])
        L += ["", f"## {title}：g = 选到的 − 菜单等权（{unit}）；h = 选到的 − 现行",
              f"结果月 {r['window'][0] if r['window'] else '—'}〜{r['window'][1] if r['window'] else '—'}（{r['n_dec']} 个决定月）；"
              f"每月事后选对的上限 g = {_f(r['oracle'])}。", "",
              "| 判断法 | g | t | " + " | ".join(f"{e} 的 g" for e in eras) + " | h | 经验 p | ① ② ③ ④ | 选得最多的 |",
              "|---|---|---|" + "---|" * len(eras) + "---|---|---|---|"]
        for m in METHODS:
            x = r["methods"][m]
            top = "、".join(f"{k} {v}%" for k, v in list(sorted(x.get("share", {}).items(), key=lambda kv: -kv[1]))[:2])
            L.append(f"| {m} | {_f(x.get('g'))} | {x.get('t')} | " + " | ".join(_f(x['eras'].get(e)) for e in eras) +
                     f" | {_f(x.get('h'))} | {x.get('p')} | {' '.join(ck(c) for c in x['c'])} | {top} |")
        L += ["", "各年代事后最好的固定模型（只描述）：" + "；".join(f"{k} {v['best']}" for k, v in r["fixed"].items()),
              "现在（2026-09 月末）各判断法会选：" + "、".join(f"{m} → {r['now'].get(m) or '—'}" for m in METHODS),
              "模型：" + "、".join(f"{k} = {v}" for k, v in names.items())]
    L += ["", "读法：四条都过的才另外登记账户级的切换检验（第二关）；都不过 = 现在看得到的局势判断不出下个月哪个模型更好 → 不做切换、模拟盘不变。",
          "核心层是「只有核心」的月收益（账户里两层会互相拖累，以前的经验是只看核心会高估）；个股层是假想单笔（不是账户）。非投资建议。"]
    return "\n".join(L) + "\n"


def check(log=print) -> int:
    """登记前核对：只数个数（不看任何收益）。"""
    months = pd.period_range(FIRST, LAST, freq="M")
    st = state_frames(months)
    log(f"状态：8 个变量都有值（标准化后）的月份 {int(st['Z'].notna().all(axis=1).sum())} 个，第一个 {st['Z'].dropna().index.min()}；"
        f"HMM 变量 {int(st['F'].notna().all(axis=1).sum())} 个月；TAB 格 {int(st['cells'].notna().sum())} 个月（{st['cells'].nunique()} 种）")
    lab = MS.hmm_labels(st["F"], min_n=HMM_MIN, order_col=1)
    log(f"HMM 标签 {int(lab.notna().sum())} 个月，第一个 {lab.dropna().index.min()}")
    P = core_menu(months)
    log(f"核心层：8 个模型都有月结果的月份 {int(P.notna().all(axis=1).sum())} 个（{P.dropna().index.min()}〜{P.dropna().index.max()}）")
    T = singles(log)
    ok = T[list(S_MODELS)].notna().all(axis=1)
    cnt = T[ok].groupby(["era", "pool"]).size()
    log("个股层：三种卖法都有结果的信号 " + "、".join(f"{e}/{p} {int(n)}" for (e, p), n in cnt.items()) + f"（合计 {int(ok.sum())} / {len(T)}）")
    S = stock_menu(T, months)
    log(f"个股层：有信号的月份 {int(S.notna().any(axis=1).sum())} 个")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只数个数，不看任何收益")
    a = ap.parse_args()
    if a.check:
        return check()
    t0 = time.time()
    code = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    months = pd.period_range(FIRST, LAST, freq="M")
    st = state_frames(months)
    lab = MS.hmm_labels(st["F"], min_n=HMM_MIN, order_col=1).reindex(months)
    o = {"code": code}
    o["K"] = run_menu("K", core_menu(months), st, lab, months)
    o["S"] = run_menu("S", stock_menu(singles(), months), st, lab, months)
    o["passed"] = [f"{n} {m}" for n in ("K", "S") for m in METHODS if o[n]["methods"][m]["pass"]]
    text = render(o)
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    print(f"用时 {time.time() - t0:.0f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
