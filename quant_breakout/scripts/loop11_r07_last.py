"""loop11_r07_last.py — 第十一个研究循环（卖法：按股票种类 / 周期区分）第 7 轮（最后 2 个做法）：
TCY 按个股自己的上涨周期定「最长持有天数」/ VBK 按突破当天的量能（量比）
（2026-10-05 登记；**在看第 4〜6 轮结果之前设计**；先提交后只运行一次；用掉 2 个做法 → 20 / 20；
TCY 进「卖法·个股上涨段长度」家族（2 / 3）、VBK 新家族「卖法·突破量能」1 / 3）。

循环的规则：scripts/research_loop11.py；共用：scripts/loop11_common.py（upleg_cycle、spec_label）；ULC 的特征复用第 1 轮已登记、没改的函数
（scripts/loop11_r01_cycle.feature("ULC", …)：500 日、3 × ATR% 中位数的之字形、上涨段天数中位数）。
  - TCY（**事后**：第 1 轮 ULC 用同一个特征调吊灯倍数，账户合计 −0.167 → 改成「用周期定持有的时间上限」，V6 适用）：
    用户「每个股票种类周期都不一样」的另一种读法 —— 一只票的上涨段一般走 C 天，那么一笔持仓最长拿 round(1.5 × C) 天（限制在 20〜60 天），
    吊灯倍数照 B3（k 3）；C 算不了 → B3（60 天）。只会把最长持有缩短（B3 是 60 天）→ 短周期的票到时间就卖。
  - VBK（不是事后）：研究面板 vr1（突破当天成交量 ÷ 之前 20 日均量）；量比大（≥ 上分位：放量确认的突破）→ WIDE（k 4、90 天）；
    量比小（≤ 下分位）→ TIGHT（k 2、60 天）；其余 → B3。先验：放量的突破更可能是真的趋势（技术分析的传统说法）；
    照实写：Lee & Swaminathan（2000）说高换手的动量更早反转（那是几个月的换手，不是突破当天的量）→ 先验不强。
门槛（VBK：三分之一 / 三分之二分位；只用 425 个日経225 W2 信号的特征分布 = 只数个数；--scale 算出、登记时写进 CUTS）。参数事先写定（V5 不适用）。
第二关（第一关过了的才做；另行登记）：每个年代把标签随机重排（TCY 的标签 = 每个信号的最长持有天数）。
事前预期（写在看第 4〜6 轮结果之前）：TCY 只缩短持有 → 胜率可能升、每笔多半降；VBK 同前几轮；第一关各约 3%；「更好候选」各约 1%。
运行：python scripts/loop11_r07_last.py --scale / --wiring / 不加参数 = 第一关（只运行一次）。输出 var/out/loop11_r07_last.md / .json。非投资建议。
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

ROUND = 7
IDS = ("TCY", "VBK")
FAMILY = {"TCY": "卖法·个股上涨段长度", "VBK": "卖法·突破量能"}
KINDS = {k: "label" for k in IDS}
POSTHOC = {"TCY": True, "VBK": False}
TIGHT, WIDE = R1.TIGHT, R1.WIDE
TCY_MULT, TCY_MIN, TCY_MAX = 1.5, 20, 60
NAMES = {"VBK": ("low", "mid", "high")}
MENUS = {"TCY": {}, "VBK": {"low": TIGHT, "high": WIDE}}                    # TCY 的标签本身就是参数（spec_label）
CUTS: dict[str, tuple[float, float] | None] = {"VBK": (1.7761, 2.3092)}     # --scale 的三分位（只数个数）
OUT = "loop11_r07_last"


# ───────────────────────── 纯函数（tests/test_loop11_r07.py） ─────────────────────────
def tcy_hold(cycle) -> np.ndarray:
    """上涨周期 C（天）→ 最长持有 = round(1.5 × C)，限制在 20〜60；C 算不了 → 60（B3）。"""
    c = np.asarray(cycle, float)
    h = np.where(np.isfinite(c), np.clip(np.round(TCY_MULT * c), TCY_MIN, TCY_MAX), TCY_MAX)
    return h.astype(int)


def tcy_labels(cycle) -> np.ndarray:
    return np.asarray([LC.spec_label({"k": 3.0, "mh": int(h)}) for h in tcy_hold(cycle)], dtype=object)


# ───────────────────────── 特征 / 标签 ─────────────────────────
def labels_of(k: str, X: pd.DataFrame, fa: dict) -> np.ndarray:
    if k == "TCY":
        return tcy_labels(R1.feature("ULC", X, fa))
    x = pd.to_numeric(X["vr1"], errors="coerce").to_numpy(float) if "vr1" in X.columns else np.full(len(X), np.nan)
    lo, hi = CUTS[k]
    return LC.label3(x, lo, hi, NAMES[k])


def all_labels(W: dict) -> dict:
    return {k: {e: labels_of(k, LC.signals(W, e), W["SM"][e]["fa"]) for e in LC.ERAS} for k in IDS}


def label_fns() -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            return labels_of(k, X, fa)
        return fn
    return {k: fn_of(k) for k in IDS}


def scale_mode() -> int:
    t0 = time.time()
    W = LC.load()
    x = np.concatenate([pd.to_numeric(LC.signals(W, e)["vr1"], errors="coerce").to_numpy(float) for e in LC.ERAS])
    lo, hi = LC.tercile_cuts(x)
    cyc = np.concatenate([R1.feature("ULC", LC.signals(W, e), W["SM"][e]["fa"]) for e in LC.ERAS])
    holds = pd.Series(tcy_hold(cyc)).value_counts().sort_index()
    out = {"VBK": {"n": int(len(x)), "valid": int(np.isfinite(x).sum()), "q1": round(lo, 4), "q2": round(hi, 4),
                   "pct": {p: round(float(np.nanpercentile(x, p)), 4) for p in (10, 25, 50, 75, 90)}},
           "TCY": {"holds": {int(a): int(b) for a, b in holds.items()}}}
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
        fa = W["SM"][sm]["fa"]
        pool[s] = {k: {str(a): int(b) for a, b in pd.Series(labels_of(k, X, fa)).value_counts().items()} for k in IDS}
        pool[s]["n"] = len(X)
    print("W / Jx / Zx 每档个数（只数个数）：" + json.dumps(pool, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one_mode() -> int:
    _ready()
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_r07_last.py", "scripts/loop11_r01_cycle.py")
    W = LC.load()
    lab = all_labels(W)
    r = LC.stage_one(W, lab, MENUS, label_fns(), POSTHOC, lenses=None, log=lambda m: print(m, flush=True))
    reg = R11.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in LC.ERAS}
    res = {"loop": 11, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "cuts": CUTS, "menus": MENUS, "tcy": {"mult": TCY_MULT, "min": TCY_MIN, "max": TCY_MAX},
           **r, "drift": drift, "scale": LC.scale(W, lab), "seconds": round(time.time() - t0)}
    text = LC.render(res, f"# 第十一个研究循环第 {ROUND} 轮：TCY 个股上涨周期定最长持有 / VBK 突破量能（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环第 7 轮：TCY / VBK（第一关）")
    ap.add_argument("--scale", action="store_true", help="登记前：特征分布（只数个数）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_mode()
    return wiring_mode() if a.wiring else stage_one_mode()


if __name__ == "__main__":
    raise SystemExit(main())
