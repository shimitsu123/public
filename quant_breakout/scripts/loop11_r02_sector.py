"""loop11_r02_sector.py — 第十一个研究循环（卖法：按股票种类 / 周期区分）第 2 轮：
SCY 按业种景气循环分三类（每一类的参数从训练数据学）/ SZK 按规模（流动性）/ VRK 按个股收益的自相关（方差比）
（2026-10-05 登记；**在看第 1 轮结果之前设计**；先提交后只运行一次；用掉 3 个做法 → 6 / 20；新家族「卖法·业种景气循环（学参数）」
「卖法·规模流动性」「卖法·个股自相关（方差比）」各 1 / 3）。

循环的规则：scripts/research_loop11.py；共用：scripts/loop11_common.py；参数菜单、学参数的规则（choose：每笔不低于 B3 的里面训练胜率最高、
平手 → B3、< 20 笔 → B3）、逐年前推的截止日都复用第 1 轮已登记、没改的纯函数（scripts/loop11_r01_cycle.py）。ID 登记前核对。
三个都**不是事后**（V6 不适用，Zx 只报告）；SCY 要学参数 → V5 适用。菜单：收紧 TIGHT = k 2、60 天；B3 = k 3、60 天；放宽 WIDE = k 4、90 天。
  - SCY：東証 33 业种（var/industry_s33.json，2026-08-31 版；历史年代也按这个对应）事先分三类 ——
    景气敏感 cyc（鉱業、石油・石炭、鉄鋼、非鉄、化学、ガラス・土石、パルプ・紙、金属製品、機械、輸送用機器、電気機器、精密機器、海運、空運、卸売、
    ゴム、繊維、建設、その他製品）/ 防御 def（食料品、医薬品、電気・ガス、陸運、情報・通信、小売、サービス、水産・農林、倉庫・運輸）/
    金融不动产 fin（銀行、保険、その他金融、証券、不動産）；没有业种 → B3。每一类用哪一套按第 1 轮 VOK 同一个规则学（候选 = 三个年代全部训练；
    V5 = 留一年代 + 逐年前推）。先验照实写：景气循环股跟着几年一轮的景气走（趋势长）、防御股多是个别消息（趋势短）—— 但也有相反的说法，交给数据学。
  - SZK：信号日 20 天平均成交额（研究面板 lturn，log10 円）三分之一 / 三分之二分位；成交额小（≤ 下分位）→ WIDE、成交额大（≥ 上分位）→ TIGHT、其余 → B3。
    文献：Hong, Lim & Stein（2000）—— 小的、没人跟的股票消息扩散慢、动量更持久；大的消息很快反映 → 突破之后更容易回头。
  - VRK：信号日为止 250 个交易日的方差比 VR(10) = 10 日对数收益（重叠）的方差 ÷（10 × 日对数收益的方差）（loop11_r02_sector.variance_ratio）；
    VR 高（≥ 上分位：收益正自相关 = 走趋势）→ WIDE；VR 低（≤ 下分位：负自相关 = 来回）→ TIGHT；其余 / 算不了 → B3。文献：Lo & MacKinlay（1988）。
门槛（三分之一 / 三分之二分位；只用 Z / E / J 全部 425 个日経225 W2 信号的特征分布 = 只数个数、没看结果；--scale 算出、登记时写进 CUTS）：
  SZK lturn 9.1557 / 9.5445（20 天平均成交额约 14.3 億円 / 35.0 億円）、VRK 0.7111 / 0.8765（中位 0.78）。
照实写：本轮的设计（脚本）在第 1 轮结果出来之前写好；门槛是第 1 轮结果出来之后只数个数定的（三分位、机械规则）。
V4 / V6：W / Jx / Zx 里 B3 会买的信号按同一个函数分类（SCY 用候选学到的那一套）→ 同一个信号「候选 vs X6」配对假想单笔。
第二关（第一关过了的才做；另行登记）：每个年代把种类标签随机重排。
事前预期（写在看任何结果之前）：同第 1 轮 —— 第一关各约 4〜6%；「更好候选」各约 2%。
运行：python scripts/loop11_r02_sector.py --scale / --wiring / 不加参数 = 第一关（只运行一次）。输出 var/out/loop11_r02_sector.md / .json。非投资建议。
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

ROUND = 2
IDS = ("SCY", "SZK", "VRK")
FAMILY = {"SCY": "卖法·业种景气循环（学参数）", "SZK": "卖法·规模流动性", "VRK": "卖法·个股自相关（方差比）"}
KINDS = {k: "label" for k in IDS}
POSTHOC = {k: False for k in IDS}
TIGHT, WIDE, OPTIONS = R1.TIGHT, R1.WIDE, R1.OPTIONS
GROUPS = {
    "cyc": ("鉱業", "石油・石炭製品", "鉄鋼", "非鉄金属", "化学", "ガラス・土石製品", "パルプ・紙", "金属製品", "機械", "輸送用機器", "電気機器",
            "精密機器", "海運業", "空運業", "卸売業", "ゴム製品", "繊維製品", "建設業", "その他製品"),
    "def": ("食料品", "医薬品", "電気・ガス業", "陸運業", "情報・通信業", "小売業", "サービス業", "水産・農林業", "倉庫・運輸関連業"),
    "fin": ("銀行業", "保険業", "その他金融業", "証券、商品先物取引業", "不動産業"),
}
NAMES = {"SZK": ("low", "mid", "high"), "VRK": ("low", "mid", "high")}
MENUS = {"SCY": OPTIONS, "SZK": {"low": WIDE, "high": TIGHT}, "VRK": {"low": TIGHT, "high": WIDE}}
CUTS: dict[str, tuple[float, float] | None] = {"SZK": (9.1557, 9.5445), "VRK": (0.7111, 0.8765)}
# ↑ 登记时由 --scale 写定（425 个日経225 W2 信号的三分之一 / 三分之二分位；算得出的 SZK 425、VRK 402；SCY：cyc 185 / def 162 / fin 38 / 没有业种 40；只数个数）
VR_N, VR_Q = 250, 10
OUT = "loop11_r02_sector"


# ───────────────────────── 纯函数（tests/test_loop11_r02.py） ─────────────────────────
def variance_ratio(close: np.ndarray, pos: int, n: int = VR_N, q: int = VR_Q) -> float:
    """位置 pos（含）为止 n 个交易日的 VR(q)：q 日对数收益（重叠）的方差 ÷（q × 日对数收益的方差）；不够 / 有缺值 → NaN。"""
    if pos < n:
        return float("nan")
    c = np.asarray(close[pos - n:pos + 1], float)
    if not np.all(np.isfinite(c)) or np.any(c <= 0):
        return float("nan")
    lc = np.log(c)
    r1 = np.diff(lc)
    rq = lc[q:] - lc[:-q]
    v1 = r1.var(ddof=1)
    return float(rq.var(ddof=1) / (q * v1)) if v1 > 0 and len(rq) > 1 else float("nan")


def group_of(s33_name: str | None) -> str:
    for g, names in GROUPS.items():
        if s33_name in names:
            return g
    return LC.NA


def s33_map() -> dict[str, str]:
    from qbreak import paths
    d = json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))
    return d.get("s33") or {}


def sector_labels(tickers, s33: dict[str, str]) -> np.ndarray:
    return np.asarray([group_of(s33.get(str(t).split(".")[0])) for t in tickers], dtype=object)


# ───────────────────────── 特征 / 标签 ─────────────────────────
def feature(k: str, X: pd.DataFrame, fa: dict) -> np.ndarray:
    if k == "SZK":
        return pd.to_numeric(X["lturn"], errors="coerce").to_numpy(float) if "lturn" in X.columns else np.full(len(X), np.nan)
    out = np.full(len(X), np.nan)
    for i, (t, d) in enumerate(zip(X["ticker"], pd.to_datetime(X["date"]))):
        df = fa.get(t)
        if df is None or d not in df.index:
            continue
        out[i] = variance_ratio(df["Close"].to_numpy(float), int(df.index.get_loc(d)))
    return out


def labels_of(k: str, X: pd.DataFrame, fa: dict, s33: dict) -> np.ndarray:
    if k == "SCY":
        return sector_labels(X["ticker"], s33)
    lo, hi = CUTS[k]
    return LC.label3(feature(k, X, fa), lo, hi, NAMES[k])


# ───────────────────────── SCY：学（规则 = 第 1 轮 VOK 的 choose） ─────────────────────────
def learn_map(T: pd.DataFrame) -> dict[str, str]:
    out = {}
    for g in GROUPS:
        x = T[T["label"] == g]
        out[g] = R1.choose({o: x[f"net_{o}"].to_numpy(float) for o in OPTIONS}) if len(x) else "base"
    return out


def apply_map(labels, mp: dict[str, str]) -> list[str]:
    return [mp.get(lab, "base") if lab != LC.NA else "base" for lab in labels]


def train_table(W: dict, lab: dict) -> pd.DataFrame:
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


def maps_of(T: pd.DataFrame) -> dict:
    full = learn_map(T)
    loeo = {e: learn_map(T[T["era"] != e]) for e in LC.ERAS}
    years = sorted({int(pd.Timestamp(d).year) for d in T["date"]})
    fwd = {y: learn_map(T[pd.to_datetime(T["date"]) <= R1.wf_cut(f"{y}-06-30")]) for y in years}
    return {"full": full, "loeo": loeo, "fwd": fwd}


def lens_labels(W: dict, lab: dict, maps: dict) -> tuple[dict, dict]:
    cand, loeo, fwd = {}, {}, {}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        cand[e] = apply_map(lab[e], maps["full"])
        loeo[e] = [LC.spec_label(OPTIONS[o]) for o in apply_map(lab[e], maps["loeo"][e])]
        fwd[e] = [LC.spec_label(OPTIONS[maps["fwd"][pd.Timestamp(d).year].get(l, "base") if l != LC.NA else "base"])
                  for l, d in zip(lab[e], pd.to_datetime(S["date"]))]
    return cand, {"loeo": loeo, "fwd": fwd}


def all_labels(W: dict, s33: dict) -> dict:
    out = {k: {} for k in IDS}
    for e in LC.ERAS:
        S = LC.signals(W, e)
        for k in IDS:
            out[k][e] = labels_of(k, S, W["SM"][e]["fa"], s33)
    return out


def label_fns(maps: dict | None, s33: dict) -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            lab = labels_of(k, X, fa, s33)
            return apply_map(lab, maps["full"]) if k == "SCY" else lab
        return fn
    return {k: fn_of(k) for k in IDS}


# ───────────────────────── 登记前：只数个数 ─────────────────────────
def scale_mode() -> int:
    t0 = time.time()
    W = LC.load()
    s33 = s33_map()
    out = {}
    for k in ("SZK", "VRK"):
        x = np.concatenate([feature(k, LC.signals(W, e), W["SM"][e]["fa"]) for e in LC.ERAS])
        lo, hi = LC.tercile_cuts(x)
        out[k] = {"n": int(len(x)), "valid": int(np.isfinite(x).sum()), "q1": round(lo, 4), "q2": round(hi, 4),
                  "pct": {p: round(float(np.nanpercentile(x, p)), 4) for p in (10, 25, 50, 75, 90)}}
    sc = pd.Series(np.concatenate([sector_labels(LC.signals(W, e)["ticker"], s33) for e in LC.ERAS])).value_counts()
    out["SCY"] = {str(a): int(b) for a, b in sc.items()}
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
    lab = all_labels(W, s33)
    dummy = {"SCY": {"cyc": WIDE, "def": TIGHT, "fin": TIGHT}, "SZK": MENUS["SZK"], "VRK": MENUS["VRK"]}
    ok = LC.wiring(W, lab, dummy)
    print("规模（只数个数）：" + json.dumps(LC.scale(W, lab), ensure_ascii=False))
    pool = {}
    for s, fold, sm in LC.OTHER:
        X = LC.C10.kept_pool(W, s, fold)
        fa = W["SM"][sm]["fa"]
        pool[s] = {k: {str(a): int(b) for a, b in pd.Series(labels_of(k, X, fa, s33)).value_counts().items()} for k in IDS}
        pool[s]["n"] = len(X)
    print("W / Jx / Zx 每类个数（只数个数）：" + json.dumps(pool, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one_mode() -> int:
    _ready()
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_r02_sector.py", "scripts/loop11_r01_cycle.py")
    W = LC.load()
    s33 = s33_map()
    lab = all_labels(W, s33)
    T = train_table(W, lab["SCY"])
    maps = maps_of(T)
    sc, sl = lens_labels(W, lab["SCY"], maps)
    print(f"SCY 学到的：候选 {maps['full']}；留一年代 {maps['loeo']}（{time.time() - t0:.0f}s）", flush=True)
    labels = {"SCY": sc, "SZK": lab["SZK"], "VRK": lab["VRK"]}
    r = LC.stage_one(W, labels, MENUS, label_fns(maps, s33), POSTHOC, lenses={"SCY": sl}, log=lambda m: print(m, flush=True))
    reg = R11.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in LC.ERAS}
    res = {"loop": 11, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "cuts": CUTS, "groups": GROUPS, "menus": MENUS,
           "scy_maps": {"full": maps["full"], "loeo": maps["loeo"], "fwd": {str(y): m for y, m in maps["fwd"].items()}},
           **r, "drift": drift, "scale": LC.scale(W, lab), "seconds": round(time.time() - t0)}
    text = LC.render(res, f"# 第十一个研究循环第 {ROUND} 轮：SCY 业种景气循环（学参数）/ SZK 规模流动性 / VRK 个股方差比（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环第 2 轮：SCY / SZK / VRK（第一关）")
    ap.add_argument("--scale", action="store_true", help="登记前：特征分布（只数个数）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_mode()
    return wiring_mode() if a.wiring else stage_one_mode()


if __name__ == "__main__":
    raise SystemExit(main())
