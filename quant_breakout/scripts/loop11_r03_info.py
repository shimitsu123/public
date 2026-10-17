"""loop11_r03_info.py — 第十一个研究循环（卖法：按股票种类 / 周期区分）第 3 轮：
FRG 按个股涨跌的「连续性」（信息离散度）/ BTK 按对日経的 β 分三档（每一档的参数从训练数据学）/ SMK 按所在业种的 12-1 个月动量
（2026-10-05 登记；**在看第 2 轮结果之前设计**；先提交后只运行一次；用掉 3 个做法 → 9 / 20；新家族「卖法·信息离散度」（ID 原定 FIP，登记前核对发现以前的循环用过 → FRG）「卖法·对日経 β（学参数）」
「卖法·业种动量」各 1 / 3）。

循环的规则：scripts/research_loop11.py；共用：scripts/loop11_common.py；参数菜单、学参数的规则（R1.choose）、逐年前推的截止日都复用第 1 轮已登记、
没改的纯函数（scripts/loop11_r01_cycle.py）；学参数的流程复用第 2 轮（scripts/loop11_r02_sector.py 的 train_table / maps_of 写法，这里按档）。
三个都**不是事后**（V6 不适用，Zx 只报告）；BTK 学参数 → V5 适用。菜单：收紧 TIGHT = k 2、60 天；B3 = k 3、60 天；放宽 WIDE = k 4、90 天。
  - FRG：信号日为止 250 个交易日的信息离散度 ID = sign(这段时间涨跌) ×（下跌天数占比 − 上涨天数占比）（Da, Gurun & Warachka 2014「frog in the pan」）：
    ID 低（≤ 下分位：顺着趋势的方向「一点一点」地走 = 信息连续到来）→ WIDE（动量更持久）；ID 高（≥ 上分位：靠少数几天的大跳 = 信息离散）→ TIGHT；其余 / 算不了 → B3。
  - BTK：对日経的 β（研究面板 b_n225：信号周之前 104 周的周收益回归）三分之一 / 三分之二分位分三档；每一档用 TIGHT / B3 / WIDE 哪一套按第 1 轮 VOK
    同一个规则学（候选 = 三个年代全部训练；V5 = 留一年代 + 逐年前推）。先验照实写：高 β 跟着大盘走（大盘的趋势长短决定）、低 β 是个别消息 —— 方向说不准，交给数据学。
  - SMK：所在東証业种的 12-1 个月动量（研究面板 sec：业种成员对数收益等权）：业种强（≥ 上分位）→ WIDE（行业动量持续，Moskowitz & Grinblatt 1999）；
    业种弱（≤ 下分位）→ TIGHT；其余 / 缺值 → B3。
门槛（三分之一 / 三分之二分位；只用 Z / E / J 全部 425 个日経225 W2 信号的特征分布 = 只数个数、没看结果；--scale 算出、登记时写进 CUTS）：
  FRG −0.04 / 0.00（中位 −0.02；ID 是天数占比、有很多相同的值 → 「高」档 = ID ≥ 0）、BTK 0.5886 / 0.873（中位 0.72）、SMK 0.3333 / 0.6291（研究面板 sec 是业种强弱的分位，中位 0.48）。
照实写：本轮的设计（脚本）在第 2 轮结果出来之前写好；门槛是第 2 轮结果出来之后只数个数定的（三分位、机械规则）。
V4 / V6：W / Jx / Zx 里 B3 会买的信号按同一个函数分档（BTK 用候选学到的那一套）→ 同一个信号「候选 vs X6」配对假想单笔。
第二关（第一关过了的才做；另行登记）：每个年代把种类标签随机重排。
事前预期（写在看第 2 轮结果之前）：第一关各约 4〜6%；「更好候选」各约 2%。
运行：python scripts/loop11_r03_info.py --scale / --wiring / 不加参数 = 第一关（只运行一次）。输出 var/out/loop11_r03_info.md / .json。非投资建议。
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

ROUND = 3
IDS = ("FRG", "BTK", "SMK")
FAMILY = {"FRG": "卖法·信息离散度", "BTK": "卖法·对日経 β（学参数）", "SMK": "卖法·业种动量"}
KINDS = {k: "label" for k in IDS}
POSTHOC = {k: False for k in IDS}
TIGHT, WIDE, OPTIONS = R1.TIGHT, R1.WIDE, R1.OPTIONS
NAMES = {"FRG": ("low", "mid", "high"), "BTK": ("low", "mid", "high"), "SMK": ("low", "mid", "high")}
MENUS = {"FRG": {"low": WIDE, "high": TIGHT}, "BTK": OPTIONS, "SMK": {"low": TIGHT, "high": WIDE}}
CUTS: dict[str, tuple[float, float] | None] = {"FRG": (-0.04, 0.0), "BTK": (0.5886, 0.873), "SMK": (0.3333, 0.6291)}
# ↑ 登记时由 --scale 写定（425 个日経225 W2 信号的三分之一 / 三分之二分位；算得出的 FRG 402、BTK 416、SMK 383；只数个数）
FIP_N = 250
OUT = "loop11_r03_info"


# ───────────────────────── 纯函数（tests/test_loop11_r03.py） ─────────────────────────
def info_discreteness(close: np.ndarray, pos: int, n: int = FIP_N) -> float:
    """位置 pos（含）为止 n 个交易日：sign(净涨跌) ×（下跌天数占比 − 上涨天数占比）；不够 / 有缺值 / 净涨跌为 0 → NaN。"""
    if pos < n:
        return float("nan")
    c = np.asarray(close[pos - n:pos + 1], float)
    if not np.all(np.isfinite(c)) or c[0] <= 0:
        return float("nan")
    r = np.diff(c)
    tot = c[-1] / c[0] - 1
    if tot == 0:
        return float("nan")
    return float(np.sign(tot) * ((r < 0).mean() - (r > 0).mean()))


# ───────────────────────── 特征 / 标签 ─────────────────────────
PANEL_COL = {"BTK": "b_n225", "SMK": "sec"}


def feature(k: str, X: pd.DataFrame, fa: dict) -> np.ndarray:
    if k in PANEL_COL:
        c = PANEL_COL[k]
        return pd.to_numeric(X[c], errors="coerce").to_numpy(float) if c in X.columns else np.full(len(X), np.nan)
    out = np.full(len(X), np.nan)
    for i, (t, d) in enumerate(zip(X["ticker"], pd.to_datetime(X["date"]))):
        df = fa.get(t)
        if df is None or d not in df.index:
            continue
        out[i] = info_discreteness(df["Close"].to_numpy(float), int(df.index.get_loc(d)))
    return out


def labels_of(k: str, X: pd.DataFrame, fa: dict, s33=None) -> np.ndarray:
    lo, hi = CUTS[k]
    return LC.label3(feature(k, X, fa), lo, hi, NAMES[k])


# ───────────────────────── BTK：学（规则 = 第 1 轮 VOK 的 choose） ─────────────────────────
def learn_map(T: pd.DataFrame) -> dict[str, str]:
    out = {}
    for g in NAMES["BTK"]:
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
            return apply_map(lab, maps["full"]) if k == "BTK" else lab
        return fn
    return {k: fn_of(k) for k in IDS}


# ───────────────────────── 登记前：只数个数 ─────────────────────────
def scale_mode() -> int:
    t0 = time.time()
    W = LC.load()
    out = {}
    for k in IDS:
        x = np.concatenate([feature(k, LC.signals(W, e), W["SM"][e]["fa"]) for e in LC.ERAS])
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
    s33: dict = {}
    lab = all_labels(W, s33)
    dummy = {"FRG": MENUS["FRG"], "BTK": {"low": TIGHT, "mid": TIGHT, "high": WIDE}, "SMK": MENUS["SMK"]}
    ok = LC.wiring(W, lab, dummy)
    print("规模（只数个数）：" + json.dumps(LC.scale(W, lab), ensure_ascii=False))
    pool = {}
    for s, fold, sm in LC.OTHER:
        X = LC.C10.kept_pool(W, s, fold)
        fa = W["SM"][sm]["fa"]
        pool[s] = {k: {str(a): int(b) for a, b in pd.Series(labels_of(k, X, fa, s33)).value_counts().items()} for k in IDS}
        pool[s]["n"] = len(X)
    print("W / Jx / Zx 每档个数（只数个数）：" + json.dumps(pool, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one_mode() -> int:
    _ready()
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_r03_info.py", "scripts/loop11_r01_cycle.py")
    W = LC.load()
    s33: dict = {}
    lab = all_labels(W, s33)
    T = train_table(W, lab["BTK"])
    maps = maps_of(T)
    bc, bl = lens_labels(W, lab["BTK"], maps)
    print(f"BTK 学到的：候选 {maps['full']}；留一年代 {maps['loeo']}（{time.time() - t0:.0f}s）", flush=True)
    labels = {"FRG": lab["FRG"], "BTK": bc, "SMK": lab["SMK"]}
    r = LC.stage_one(W, labels, MENUS, label_fns(maps, s33), POSTHOC, lenses={"BTK": bl}, log=lambda m: print(m, flush=True))
    reg = R11.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in LC.ERAS}
    res = {"loop": 11, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "cuts": CUTS, "menus": MENUS,
           "btk_maps": {"full": maps["full"], "loeo": maps["loeo"], "fwd": {str(y): m for y, m in maps["fwd"].items()}},
           **r, "drift": drift, "scale": LC.scale(W, lab), "seconds": round(time.time() - t0)}
    text = LC.render(res, f"# 第十一个研究循环第 {ROUND} 轮：FRG 信息离散度 / BTK 对日経 β（学参数）/ SMK 业种动量（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环第 3 轮：FRG / BTK / SMK（第一关）")
    ap.add_argument("--scale", action="store_true", help="登记前：特征分布（只数个数）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_mode()
    return wiring_mode() if a.wiring else stage_one_mode()


if __name__ == "__main__":
    raise SystemExit(main())
