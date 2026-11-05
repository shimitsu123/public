"""loop11_r04_industry.py — 第十一个研究循环（卖法：按股票种类 / 周期区分）第 4 轮：
ICY 按所在业种自己的上涨段长度（业种的周期）/ RSD 按个股与日経的相关（个别行情 vs 跟着大盘）/ DVY 按股息率（价值 vs 成长）
（2026-10-05 登记；**在看第 3 轮结果之前设计**；先提交后只运行一次；用掉 3 个做法 → 12 / 20；新家族「卖法·业种自己的周期」「卖法·个别行情程度」（ID 原定 RSM，以前用过 → RSD）
「卖法·价值成长」各 1 / 3）。

循环的规则：scripts/research_loop11.py；共用：scripts/loop11_common.py（upleg_cycle、label3、tercile_cuts）；菜单复用第 1 轮已登记的 TIGHT / WIDE。
三个都**不是事后**、参数事先写定（V5 / V6 不适用，Zx 只报告）。菜单：收紧 TIGHT = k 2、60 天；B3 = k 3、60 天；放宽 WIDE = k 4、90 天。
  - ICY（用户「每个股票种类周期都不一样」的业种版本）：所在東証 33 业种的等权指数（这个年代的日経225 成员里同一业种的票，日对数收益的平均累加；
    var/industry_s33.json 对应）→ 信号日为止 500 个交易日、反转幅度 = 3 × 「14 日平均每日涨跌幅绝对值」中位数的之字形（ATR 的近似）→ 走完的上涨段天数中位数
    （至少 3 段）= 业种的「上涨周期」；短（≤ 下分位）→ TIGHT、长（≥ 上分位）→ WIDE、其余 / 算不了（没有业种 / 同业种成员 < 3 只）→ B3。
    池子（W / Jx / Zx）的票用对应年代（W → E、Jx → J、Zx → Z）日経225 成员算的同一个业种指数。
  - RSD：研究面板 corr60（个股与日経最近 60 日日收益的相关）；相关低（≤ 下分位：个别消息推动）→ WIDE；相关高（≥ 上分位：跟着大盘走）→ TIGHT。
    文献：残差 / 个别动量比总收益动量更持久（Blitz, Huij & Martens 2011）。
  - DVY：研究面板 dy（股息率 %，缺值 → B3）；股息率低（≤ 下分位：成长型）→ WIDE；股息率高（≥ 上分位：价值型）→ TIGHT。
    文献：动量在成长股（低账面市值比）里更强（Asness 1997）。
门槛（三分之一 / 三分之二分位；只用 Z / E / J 全部 425 个日経225 W2 信号的特征分布 = 只数个数、没看结果；--scale 算出、登记时写进 CUTS）：
  ICY 8 / 10 天（业种指数比个股顺 → 上涨段短；中位 9 天；天数是整数 → 「短」= ≤ 8、「长」= ≥ 10）、RSD 0.4363 / 0.5904、DVY 1.3292% / 2.4253%。
照实写：本轮的设计（脚本）在第 3 轮结果出来之前写好；门槛是只数个数定的（三分位、机械规则）。
第二关（第一关过了的才做；另行登记）：每个年代把种类标签随机重排。
事前预期（写在看第 3 轮结果之前；照实写第 1〜2 轮的读法）：第 1〜2 轮按种类改卖法几乎都在 E 伤账户 —— X6（k 3）本来就是在 E / J 上挑出来的，
  任何偏离在 E / J 上都可能显得更差；第一关各约 3〜5%；「更好候选」各约 1〜2%。
运行：python scripts/loop11_r04_industry.py --scale / --wiring / 不加参数 = 第一关（只运行一次）。输出 var/out/loop11_r04_industry.md / .json。非投资建议。
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
import loop11_r01_cycle as R1                                                # noqa: E402
import research_loop11 as R11                                                # noqa: E402

ROUND = 4
IDS = ("ICY", "RSD", "DVY")
FAMILY = {"ICY": "卖法·业种自己的周期", "RSD": "卖法·个别行情程度", "DVY": "卖法·价值成长"}
KINDS = {k: "label" for k in IDS}
POSTHOC = {k: False for k in IDS}
TIGHT, WIDE = R1.TIGHT, R1.WIDE
NAMES = {"ICY": ("short", "mid", "long"), "RSD": ("low", "mid", "high"), "DVY": ("low", "mid", "high")}
MENUS = {"ICY": {"short": TIGHT, "long": WIDE}, "RSD": {"low": WIDE, "high": TIGHT}, "DVY": {"low": WIDE, "high": TIGHT}}
CUTS: dict[str, tuple[float, float] | None] = {"ICY": (8.0, 10.0), "RSD": (0.4363, 0.5904), "DVY": (1.3292, 2.4253)}
# ↑ 登记时由 --scale 写定（425 个日経225 W2 信号的三分之一 / 三分之二分位；算得出的 ICY 294、RSD 425、DVY 423；业种指数 Z 20 / E 22 / J 22 个；只数个数）
ICY_N, ICY_K, ICY_MIN, ICY_MIN_MEMBERS = 500, 3.0, 3, 3
PANEL_COL = {"RSD": "corr60", "DVY": "dy"}
ERA_OF_POOL = {"W": "E", "Jx": "J", "Zx": "Z"}
OUT = "loop11_r04_industry"


# ───────────────────────── 纯函数（tests/test_loop11_r04.py） ─────────────────────────
def industry_index(closes: pd.DataFrame, members: list[str], min_members: int = ICY_MIN_MEMBERS) -> pd.Series | None:
    """同一业种成员的收盘（列 = 票）→ 等权指数：每天有值的成员的日对数收益平均（成员 < min_members 的日子记 0），累加后取 exp；成员不够 → None。"""
    cols = [c for c in members if c in closes.columns]
    if len(cols) < min_members:
        return None
    lr = np.log(closes[cols].astype(float)).diff()
    cnt = lr.notna().sum(axis=1)
    m = lr.mean(axis=1).where(cnt >= min_members, 0.0).fillna(0.0)
    return np.exp(m.cumsum())


def atr_proxy(level: pd.Series, n: int = 14) -> pd.Series:
    """指数没有高低价 → 用「n 日平均每日涨跌幅绝对值 × 水平」当 ATR 的近似。"""
    return level.pct_change().abs().rolling(n, min_periods=n).mean() * level


# ───────────────────────── 特征 / 标签 ─────────────────────────
def s33_map() -> dict[str, str]:
    from qbreak import paths
    d = json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))
    return d.get("s33") or {}


def industry_levels(W: dict, s33: dict) -> dict:
    """{年代: {业种: (指数水平, ATR 近似)}}（这个年代的日経225 成员）。"""
    out = {}
    for e in LC.ERAS:
        fa = W["SM"][e]["fa"]
        closes = pd.DataFrame({t: df["Close"] for t, df in fa.items()}).sort_index()
        by: dict[str, list[str]] = {}
        for t in closes.columns:
            g = s33.get(str(t).split(".")[0])
            if g:
                by.setdefault(g, []).append(t)
        out[e] = {}
        for g, mem in by.items():
            lv = industry_index(closes, mem)
            if lv is not None:
                out[e][g] = (lv, atr_proxy(lv))
    return out


def icy_feature(X: pd.DataFrame, era: str, IL: dict, s33: dict) -> np.ndarray:
    out = np.full(len(X), np.nan)
    cache: dict = {}
    for i, (t, d) in enumerate(zip(X["ticker"], pd.to_datetime(X["date"]))):
        g = s33.get(str(t).split(".")[0])
        if not g or g not in IL[era]:
            continue
        lv, at = IL[era][g]
        if d not in lv.index:
            continue
        key = (g, d)
        if key not in cache:
            pos = int(lv.index.get_loc(d))
            cache[key] = LC.upleg_cycle(lv.to_numpy(float), at.to_numpy(float), pos, ICY_N, ICY_K, ICY_MIN)
        out[i] = cache[key]
    return out


def feature(k: str, X: pd.DataFrame, era: str, IL: dict, s33: dict) -> np.ndarray:
    if k == "ICY":
        return icy_feature(X, era, IL, s33)
    c = PANEL_COL[k]
    return pd.to_numeric(X[c], errors="coerce").to_numpy(float) if c in X.columns else np.full(len(X), np.nan)


def labels_of(k: str, X: pd.DataFrame, era: str, IL: dict, s33: dict) -> np.ndarray:
    lo, hi = CUTS[k]
    return LC.label3(feature(k, X, era, IL, s33), lo, hi, NAMES[k])


def all_labels(W: dict, IL: dict, s33: dict) -> dict:
    return {k: {e: labels_of(k, LC.signals(W, e), e, IL, s33) for e in LC.ERAS} for k in IDS}


def label_fns(IL: dict, s33: dict) -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            return labels_of(k, X, ERA_OF_POOL[s], IL, s33)
        return fn
    return {k: fn_of(k) for k in IDS}


# ───────────────────────── 登记前：只数个数 ─────────────────────────
def scale_mode() -> int:
    t0 = time.time()
    W = LC.load()
    s33 = s33_map()
    IL = industry_levels(W, s33)
    out = {}
    for k in IDS:
        x = np.concatenate([feature(k, LC.signals(W, e), e, IL, s33) for e in LC.ERAS])
        lo, hi = LC.tercile_cuts(x)
        out[k] = {"n": int(len(x)), "valid": int(np.isfinite(x).sum()), "q1": round(lo, 4), "q2": round(hi, 4),
                  "pct": {p: round(float(np.nanpercentile(x, p)), 4) for p in (10, 25, 50, 75, 90)}}
    out["industries"] = {e: len(v) for e, v in IL.items()}
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
    s33 = s33_map()
    IL = industry_levels(W, s33)
    lab = all_labels(W, IL, s33)
    ok = LC.wiring(W, lab, MENUS)
    print("规模（只数个数）：" + json.dumps(LC.scale(W, lab), ensure_ascii=False))
    pool = {}
    fns = label_fns(IL, s33)
    for s, fold, sm in LC.OTHER:
        X = LC.C10.kept_pool(W, s, fold)
        fa = W["SM"][sm]["fa"]
        pool[s] = {k: {str(a): int(b) for a, b in pd.Series(fns[k](s, X, fa)).value_counts().items()} for k in IDS}
        pool[s]["n"] = len(X)
    print("W / Jx / Zx 每档个数（只数个数）：" + json.dumps(pool, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one_mode() -> int:
    _ready()
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_r04_industry.py", "scripts/loop11_r01_cycle.py")
    W = LC.load()
    s33 = s33_map()
    IL = industry_levels(W, s33)
    lab = all_labels(W, IL, s33)
    r = LC.stage_one(W, lab, MENUS, label_fns(IL, s33), POSTHOC, lenses=None, log=lambda m: print(m, flush=True))
    reg = R11.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in LC.ERAS}
    res = {"loop": 11, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "cuts": CUTS, "menus": MENUS, **r, "drift": drift, "scale": LC.scale(W, lab), "seconds": round(time.time() - t0)}
    text = LC.render(res, f"# 第十一个研究循环第 {ROUND} 轮：ICY 业种自己的周期 / RSD 个别行情程度 / DVY 价值成长（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环第 4 轮：ICY / RSD / DVY（第一关）")
    ap.add_argument("--scale", action="store_true", help="登记前：特征分布（只数个数）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_mode()
    return wiring_mode() if a.wiring else stage_one_mode()


if __name__ == "__main__":
    raise SystemExit(main())
