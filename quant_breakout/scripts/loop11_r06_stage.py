"""loop11_r06_stage.py — 第十一个研究循环（卖法：按股票种类 / 周期区分）第 6 轮（三个都是**事后**）：
SZS 只把「成交额小」的票放宽 / TAG 按突破前已经涨了多少（趋势阶段）/ N52 按离 52 周高点多远
（2026-10-05 登记；**在看第 4〜5 轮结果之前设计**；先提交后只运行一次；用掉 3 个做法 → 18 / 20；新家族「卖法·小票放宽（单边）」
「卖法·趋势阶段」「卖法·52 周高点」各 1 / 3）。

循环的规则：scripts/research_loop11.py；共用：scripts/loop11_common.py；菜单复用第 1 轮已登记的 TIGHT / WIDE（k 2、60 天 / k 4、90 天）。
三个都按以前看过的结果设计 → **事后**，V6 适用（Zx 也要同方向）；参数事先写定（V5 不适用）。照实写各自看过什么：
  - SZS：第 2 轮 SZK（成交额小放宽、大收紧）伤账户，但「成交额小 → 放宽」在 W / Jx / Zx 三个池子每笔都更好 → 这里只做单边：
    lturn ≤ 9.1557（第 2 轮同一个门槛）→ WIDE，其余照 B3。照实写：池子几乎都在「小」那一档，第 2 轮已经看过这三个池子放宽的结果 → V4 / V6 不算没看过。
  - TAG：研究面板 r120（信号日为止 120 个交易日涨跌）；突破前已经涨很多（≥ 上分位：趋势后段）→ TIGHT；涨得少（≤ 下分位：趋势早段）→ WIDE。
    先验：Lee & Swaminathan（2000）动量生命周期；照实写：第十个循环 CGO / H5G 看到「从低位起来的突破在 2001〜2016 反而更好」→ 方向是看过结果后定的。
  - N52：研究面板 hi52（收盘 ÷ 52 周最高）；在高点附近（≥ 上分位）→ WIDE（George & Hwang 2004：52 周高点附近的动量不回头）；离得远（≤ 下分位）→ TIGHT。
    照实写：与 TAG 方向部分相反（同一笔可能一个说放宽一个说收紧），两个都登记、各自判定；第十个循环 H5G（离高点 > 15% 不买）胜率只 +0.18 pp。
门槛（TAG / N52：三分之一 / 三分之二分位；只用 425 个日経225 W2 信号的特征分布 = 只数个数；--scale 算出、登记时写进 CUTS）。
第二关（第一关过了的才做；另行登记）：每个年代把种类标签随机重排。
事前预期（写在看第 4〜5 轮结果之前）：第 1〜3 轮按种类改卖法几乎都伤 E / Z 的账户；第一关各约 3%；「更好候选」各约 1%。
运行：python scripts/loop11_r06_stage.py --scale / --wiring / 不加参数 = 第一关（只运行一次）。输出 var/out/loop11_r06_stage.md / .json。非投资建议。
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

ROUND = 6
IDS = ("SZS", "TAG", "N52")
FAMILY = {"SZS": "卖法·小票放宽（单边）", "TAG": "卖法·趋势阶段", "N52": "卖法·52 周高点"}
KINDS = {k: "label" for k in IDS}
POSTHOC = {k: True for k in IDS}
TIGHT, WIDE = R1.TIGHT, R1.WIDE
SZS_CUT = 9.1557                                                             # 第 2 轮 SZK 的下分位（同一个门槛）
NAMES = {"TAG": ("low", "mid", "high"), "N52": ("low", "mid", "high")}
MENUS = {"SZS": {"small": WIDE}, "TAG": {"low": WIDE, "high": TIGHT}, "N52": {"low": TIGHT, "high": WIDE}}
CUTS: dict[str, tuple[float, float] | None] = {"TAG": (0.0133, 0.1065), "N52": (0.8965, 0.9558)}   # --scale 的三分位（只数个数）
PANEL_COL = {"SZS": "lturn", "TAG": "r120", "N52": "hi52"}
OUT = "loop11_r06_stage"


def feature(k: str, X: pd.DataFrame) -> np.ndarray:
    c = PANEL_COL[k]
    return pd.to_numeric(X[c], errors="coerce").to_numpy(float) if c in X.columns else np.full(len(X), np.nan)


def labels_of(k: str, X: pd.DataFrame) -> np.ndarray:
    x = feature(k, X)
    if k == "SZS":
        with np.errstate(invalid="ignore"):
            return np.where(np.isfinite(x) & (x <= SZS_CUT), "small", "base").astype(object)
    lo, hi = CUTS[k]
    return LC.label3(x, lo, hi, NAMES[k])


def all_labels(W: dict) -> dict:
    return {k: {e: labels_of(k, LC.signals(W, e)) for e in LC.ERAS} for k in IDS}


def label_fns() -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            return labels_of(k, X)
        return fn
    return {k: fn_of(k) for k in IDS}


def scale_mode() -> int:
    t0 = time.time()
    W = LC.load()
    out = {}
    for k in IDS:
        x = np.concatenate([feature(k, LC.signals(W, e)) for e in LC.ERAS])
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
    ok = LC.wiring(W, lab, MENUS)
    print("规模（只数个数）：" + json.dumps(LC.scale(W, lab), ensure_ascii=False))
    pool = {}
    for s, fold, sm in LC.OTHER:
        X = LC.C10.kept_pool(W, s, fold)
        pool[s] = {k: {str(a): int(b) for a, b in pd.Series(labels_of(k, X)).value_counts().items()} for k in IDS}
        pool[s]["n"] = len(X)
    print("W / Jx / Zx 每档个数（只数个数）：" + json.dumps(pool, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one_mode() -> int:
    _ready()
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_r06_stage.py", "scripts/loop11_r01_cycle.py")
    W = LC.load()
    lab = all_labels(W)
    r = LC.stage_one(W, lab, MENUS, label_fns(), POSTHOC, lenses=None, log=lambda m: print(m, flush=True))
    reg = R11.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in LC.ERAS}
    res = {"loop": 11, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "cuts": {**CUTS, "SZS": SZS_CUT}, "menus": MENUS, **r, "drift": drift, "scale": LC.scale(W, lab), "seconds": round(time.time() - t0)}
    text = LC.render(res, f"# 第十一个研究循环第 {ROUND} 轮：SZS 小票放宽（单边）/ TAG 趋势阶段 / N52 52 周高点（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环第 6 轮：SZS / TAG / N52（第一关）")
    ap.add_argument("--scale", action="store_true", help="登记前：特征分布（只数个数）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_mode()
    return wiring_mode() if a.wiring else stage_one_mode()


if __name__ == "__main__":
    raise SystemExit(main())
