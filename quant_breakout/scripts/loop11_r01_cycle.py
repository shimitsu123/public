"""loop11_r01_cycle.py — 第十一个研究循环（卖法：按股票种类 / 周期区分）第 1 轮：
ULC 按个股自己的上涨段长度（周期）/ ERK 按个股一年来走势的顺滑度（效率比）/ VOK 按波动分档（每一档的参数从训练数据学）
（2026-10-05 登记；先提交后只运行一次；用掉 3 个做法 → 3 / 20；新家族「卖法·个股上涨段长度」「卖法·个股趋势顺滑度」「卖法·波动分档（学参数）」各 1 / 3）。

循环的规则：scripts/research_loop11.py；共用：scripts/loop11_common.py。ID 登记前已用 research_loop11.check_new_approaches 核对。
三个都**不是事后**（本项目从来没有按股票种类区分卖法；方向按趋势跟随的道理与文献事先写定 / 按事先写定的程序学）→ V6 不适用（Zx 只报告）。
参数菜单（只换吊灯倍数 k 与最长持有天数，其余照 B3 的 X6）：收紧 TIGHT = k 2、60 天；B3 = k 3、60 天；放宽 WIDE = k 4、90 天。
  - ULC（用户「每个股票种类周期都不一样」最直接的版本）：信号日为止 500 个交易日的收盘，按「反转幅度 = 3 × 这段时间 ATR% 的中位数」划之字形
    （3 × ATR = X6 吊灯止损同一个尺度），走完的上涨段（低点 → 下一个高点）的天数中位数 = 这只票的「上涨周期」（loop11_common.upleg_cycle；
    至少 3 段）。周期短（≤ 三分之一分位）→ TIGHT（涨一段很快就回，早点锁住）；周期长（≥ 三分之二分位）→ WIDE（让长趋势走完）；其余 / 算不了 → B3。
    照实写（登记前只数个数）：原来设计的「以往突破到最高点的天数」（loop11_common.past_cycle）只有 55 / 425 个信号算得出（突破对每只票是稀有事件）
    → 改成每只票都算得出的上涨段长度；这个改动只看了「算得出的个数」，没看任何结果。
  - ERK：信号日为止 250 个交易日的效率比 |净涨跌| ÷ 每天涨跌绝对值之和（loop11_common.efficiency_ratio；0〜1，越大走势越顺）。
    顺滑（≥ 三分之二分位）→ WIDE（趋势顺的票回撤一下还会继续）；来回震荡（≤ 三分之一分位）→ TIGHT（涨了会还回去）；其余 / 算不了 → B3。
    文献：Da, Gurun & Warachka（2014）连续小步的动量更持久；趋势跟随在有自相关的序列上才赚。
  - VOK：ATR%（研究面板 atrp：ATR14 ÷ 收盘）三分之一 / 三分之二分位分三档；每一档用 TIGHT / B3 / WIDE 哪一套**从训练数据学**：
    训练 = 日経225 W2 信号的假想单笔（三套参数各算一次）；每一档：训练每笔平均不低于 B3 那一套的里面，选训练胜率最高的（平手 → B3）；
    那一档训练笔数 < 20 → B3。候选 = 三个年代全部当训练；V5：留一年代（每个年代用另外两个年代学）+ 逐年前推（每年只用那年 1 月 1 日 − 120 天之前的信号学）。
    先验照实写：信息不确定性高（波动大）的股票动量更强（Zhang 2006）→ 放宽，但低波动异象 → 收紧，两种说法相反 → 交给数据学、用两种检验把关。
门槛（三分之一 / 三分之二分位；只用 Z / E / J 全部日経225 W2 信号的特征分布 = 只数个数、没看结果；--scale 算出、登记时写进 CUTS）：
  ULC 17.5 / 25.5 天（中位 21 天；353 / 425 个算得出）、ERK 0.0248 / 0.0582（中位 0.039；402 / 425）、VOK ATR% 1.64% / 2.03%（中位 1.82%；425 / 425）。
V4 / V6：W / Jx / Zx 里 B3 会买的信号按同一个函数算特征、同一组门槛分档（VOK 用候选学到的那一套对应）→ 同一个信号「候选 vs X6」配对假想单笔。
第二关（第一关过了的才做；另行登记）：每个年代把种类标签随机重排（research_loop11.permute_labels）。
事前预期（写在看结果之前）：卖法对账户影响小（个股只占资金 11〜18%）→ 路线 A 很难；TIGHT 会提高胜率、降每笔，WIDE 相反 → 路线 B 要两头都对；
  B3 只有 140 笔，单个年代噪声大。第一关各约 4〜6%；「更好候选」各约 2%。
运行：python scripts/loop11_r01_cycle.py --scale（登记前：特征分布与每档个数，只数个数）；--wiring（登记前的接线核对）；不加参数 = 第一关（只运行一次）。
输出 var/out/loop11_r01_cycle.md / .json。非投资建议。
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
import loop11_common as LC                                                   # noqa: E402
import research_loop11 as R11                                                # noqa: E402

ROUND = 1
IDS = ("ULC", "ERK", "VOK")
FAMILY = {"ULC": "卖法·个股上涨段长度", "ERK": "卖法·个股趋势顺滑度", "VOK": "卖法·波动分档（学参数）"}
KINDS = {k: "label" for k in IDS}
POSTHOC = {k: False for k in IDS}
TIGHT, WIDE = {"k": 2.0, "mh": 60}, {"k": 4.0, "mh": 90}
OPTIONS = {"tight": TIGHT, "base": dict(LC.BASE_SPEC), "wide": WIDE}
NAMES = {"ULC": ("short", "mid", "long"), "ERK": ("low", "mid", "high"), "VOK": ("low", "mid", "high")}
MENUS = {"ULC": {"short": TIGHT, "long": WIDE}, "ERK": {"low": TIGHT, "high": WIDE}, "VOK": OPTIONS}
CUTS: dict[str, tuple[float, float] | None] = {"ULC": (17.5, 25.5), "ERK": (0.0248, 0.0582), "VOK": (0.0164, 0.0203)}
# ↑ 登记时由 --scale 写定（Z / E / J 全部 425 个日経225 W2 信号的三分之一 / 三分之二分位；算得出的：ULC 353、ERK 402、VOK 425；只数个数）
ULC_N, ULC_K, ULC_MIN = 500, 3.0, 3
ER_N = 250
MIN_TRAIN = 20
WF_GAP_DAYS = 120
OUT = "loop11_r01_cycle"
EPS = 1e-12


# ───────────────────────── 特征（信号日收盘为止已知） ─────────────────────────
def feature(k: str, X: pd.DataFrame, fa: dict) -> np.ndarray:
    """ULC：上涨段长度中位数；ERK：250 日效率比；VOK：atrp（研究面板）。X = 有 ticker / date 的信号表。"""
    if k == "VOK":
        return pd.to_numeric(X["atrp"], errors="coerce").to_numpy(float) if "atrp" in X.columns else np.full(len(X), np.nan)
    out = np.full(len(X), np.nan)
    for i, (t, d) in enumerate(zip(X["ticker"], pd.to_datetime(X["date"]))):
        df = fa.get(t)
        if df is None or d not in df.index:
            continue
        pos = int(df.index.get_loc(d))
        c = df["Close"].to_numpy(float)
        if k == "ULC":
            out[i] = LC.upleg_cycle(c, df["atr"].to_numpy(float), pos, ULC_N, ULC_K, ULC_MIN)
        else:
            out[i] = LC.efficiency_ratio(c, pos, ER_N)
    return out


def labels_of(k: str, x) -> np.ndarray:
    lo, hi = CUTS[k]
    return LC.label3(x, lo, hi, NAMES[k])


# ───────────────────────── VOK：从训练数据学每一档用哪一套（纯函数；tests/test_loop11_r01.py） ─────────────────────────
def choose(nets: dict[str, np.ndarray]) -> str:
    """一档的训练假想单笔（三套参数各一列，同一批信号）→ 每笔平均不低于 B3 的里面训练胜率最高的；平手 → B3；< MIN_TRAIN 笔 → B3。"""
    ok = np.ones(len(nets["base"]), bool)
    for v in nets.values():
        ok &= np.isfinite(np.asarray(v, float))
    if ok.sum() < MIN_TRAIN:
        return "base"
    st = {o: (float((np.asarray(v, float)[ok] > 0).mean()), float(np.asarray(v, float)[ok].mean())) for o, v in nets.items()}
    elig = [o for o in OPTIONS if st[o][1] >= st["base"][1] - EPS]
    return max(elig, key=lambda o: (st[o][0], o == "base"))


def learn_map(T: pd.DataFrame) -> dict[str, str]:
    """训练表（label、net_tight / net_base / net_wide）→ {档: 用哪一套}；没出现的档 → B3。"""
    out = {}
    for lab in NAMES["VOK"]:
        g = T[T["label"] == lab]
        out[lab] = choose({o: g[f"net_{o}"].to_numpy(float) for o in OPTIONS}) if len(g) else "base"
    return out


def apply_map(labels, mp: dict[str, str]) -> list[str]:
    return [mp.get(lab, "base") if lab != LC.NA else "base" for lab in labels]


def wf_cut(d) -> pd.Timestamp:
    """逐年前推：信号日 d 那年 1 月 1 日 − 120 天（训练只用信号日 ≤ 这一天的）。"""
    return pd.Timestamp(year=pd.Timestamp(d).year, month=1, day=1) - pd.Timedelta(days=WF_GAP_DAYS)


# ───────────────────────── 输入 ─────────────────────────
def all_labels(W: dict) -> dict:
    """{做法: {年代: 种类标签（与 signals 同序）}}（VOK 是档，不是学到的那一套）。"""
    out = {k: {} for k in IDS}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        fa = W["SM"][e]["fa"]
        for k in IDS:
            out[k][e] = labels_of(k, feature(k, S, fa))
    return out


def vok_train_table(W: dict, lab: dict) -> pd.DataFrame:
    """日経225 W2 信号的假想单笔（TIGHT / B3 / WIDE 各一次）+ 档 + 信号日 + 年代。"""
    p0 = W["p0"]
    bt, rt = LC.bt_rt()
    rows = []
    for e in LC.ERAS:
        S = LC.signals(W, e)
        fa = W["SM"][e]["fa"]
        for i, (t, d) in enumerate(zip(S["ticker"], pd.to_datetime(S["date"]))):
            df = fa.get(t)
            r = {"era": e, "i": i, "date": d, "label": lab[e][i]}
            for o, s in OPTIONS.items():
                r[f"net_{o}"] = LC.single_net(t, df, d, p0, bt, rt, s) if df is not None else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


def vok_maps(T: pd.DataFrame) -> dict:
    """候选（三个年代全部训练）、留一年代、逐年前推的对应表。"""
    full = learn_map(T)
    loeo = {e: learn_map(T[T["era"] != e]) for e in LC.ERAS}
    years = sorted({int(pd.Timestamp(d).year) for d in T["date"]})
    fwd = {y: learn_map(T[pd.to_datetime(T["date"]) <= wf_cut(f"{y}-06-30")]) for y in years}
    return {"full": full, "loeo": loeo, "fwd": fwd}


def vok_labels(W: dict, lab: dict, maps: dict) -> tuple[dict, dict]:
    """候选的标签（用哪一套）与 V5 两种检验的参数标签（spec_label）。"""
    cand, loeo, fwd = {}, {}, {}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        cand[e] = apply_map(lab[e], maps["full"])
        loeo[e] = [LC.spec_label(OPTIONS[o]) for o in apply_map(lab[e], maps["loeo"][e])]
        fwd[e] = [LC.spec_label(OPTIONS[maps["fwd"][pd.Timestamp(d).year].get(l, "base") if l != LC.NA else "base"])
                  for l, d in zip(lab[e], pd.to_datetime(S["date"]))]
    return cand, {"loeo": loeo, "fwd": fwd}


def label_fns(maps: dict | None) -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            lab = labels_of(k, feature(k, X, fa))
            return apply_map(lab, maps["full"]) if k == "VOK" else lab
        return fn
    return {k: fn_of(k) for k in IDS}


# ───────────────────────── 登记前：只数个数 ─────────────────────────
def scale_mode() -> int:
    t0 = time.time()
    W = LC.load()
    feats = {k: [] for k in IDS}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        for k in IDS:
            feats[k].append(feature(k, S, W["SM"][e]["fa"]))
    out = {}
    for k in IDS:
        x = np.concatenate(feats[k])
        lo, hi = LC.tercile_cuts(x)
        out[k] = {"n": int(len(x)), "valid": int(np.isfinite(x).sum()), "q1": round(lo, 4), "q2": round(hi, 4),
                  "pct": {p: round(float(np.nanpercentile(x, p)), 4) for p in (10, 25, 50, 75, 90)}}
    print("特征分布（只数个数）：" + json.dumps(out, ensure_ascii=False))
    print(f"用时 {time.time() - t0:.0f}s")
    return 0


def _ready() -> None:
    if any(v is None for v in CUTS.values()):
        raise SystemExit("CUTS 还没写定（先 --scale，登记时写进代码）")


def wiring_mode() -> int:
    _ready()
    t0 = time.time()
    st = R11.load_state()
    R11.check_new_approaches(st, [{"id": k, "family": FAMILY[k], "kind": KINDS[k], "posthoc": POSTHOC[k], "verdict": R11.FAIL1} for k in IDS],
                             R11.previous_ids(Path(__file__).resolve().parents[1] / "var"))
    W = LC.load()
    lab = all_labels(W)
    dummy = {"ULC": MENUS["ULC"], "ERK": MENUS["ERK"], "VOK": {"low": TIGHT, "mid": TIGHT, "high": WIDE}}
    ok = LC.wiring(W, lab, dummy)
    print("规模（只数个数）：" + json.dumps(LC.scale(W, lab), ensure_ascii=False))
    pool = {}
    for s, fold, sm in LC.OTHER:
        X = LC.C10.kept_pool(W, s, fold)
        fa = W["SM"][sm]["fa"]
        pool[s] = {k: {str(a): int(b) for a, b in pd.Series(labels_of(k, feature(k, X, fa))).value_counts().items()} for k in IDS}
        pool[s]["n"] = len(X)
    print("W / Jx / Zx 每档个数（只数个数）：" + json.dumps(pool, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one_mode() -> int:
    _ready()
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_r01_cycle.py")
    W = LC.load()
    lab = all_labels(W)
    T = vok_train_table(W, lab["VOK"])
    maps = vok_maps(T)
    vc, vl = vok_labels(W, lab["VOK"], maps)
    print(f"VOK 学到的：候选 {maps['full']}；留一年代 {maps['loeo']}（{time.time() - t0:.0f}s）", flush=True)
    labels = {"ULC": lab["ULC"], "ERK": lab["ERK"], "VOK": vc}
    r = LC.stage_one(W, labels, MENUS, label_fns(maps), POSTHOC, lenses={"VOK": vl}, log=lambda m: print(m, flush=True))
    reg = R11.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in LC.ERAS}
    res = {"loop": 11, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "cuts": CUTS, "menus": MENUS, "vok_maps": {"full": maps["full"], "loeo": maps["loeo"], "fwd": {str(y): m for y, m in maps["fwd"].items()}},
           **r, "drift": drift, "scale": LC.scale(W, {k: lab[k] for k in IDS}), "seconds": round(time.time() - t0)}
    text = LC.render(res, f"# 第十一个研究循环第 {ROUND} 轮：ULC 个股上涨段长度 / ERK 个股走势顺滑度 / VOK 波动分档（学参数）（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环第 1 轮：ULC / ERK / VOK（第一关）")
    ap.add_argument("--scale", action="store_true", help="登记前：特征分布（只数个数）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_mode()
    return wiring_mode() if a.wiring else stage_one_mode()


if __name__ == "__main__":
    raise SystemExit(main())
