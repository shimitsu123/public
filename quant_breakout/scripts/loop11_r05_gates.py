"""loop11_r05_gates.py — 第十一个研究循环（卖法：按股票种类 / 周期区分）第 5 轮：把第十个循环最接近的三个选股闸门改成「照买、但卖得快」——
HWT 5〜10 月的突破收紧 / X2T 顾客业种短観没有改善（x2 ≤ 0）的突破收紧 / JRT 日経落后核心 ≥ 10 pp 的日子的突破收紧
（2026-10-05 登记；**在看第 3〜4 轮结果之前设计**；先提交后只运行一次；用掉 3 个做法 → 15 / 20；新家族「卖法·选股闸门改收紧」3 / 3）。

来由（照实写）：第十个循环里 HWN / X2G / JRM 把挡掉的信号的胜率拉高了（+3.2〜+3.9 pp），但「挡掉」= 少买 → 2001〜2006（Z）的账户变差（HWN −0.350、X2G −0.132）。
这里不挡，照样买，只是这一笔用收紧的卖法（TIGHT = 吊灯 k 2、60 天；其余照 X6）：如果那些信号确实更容易失败，早点卖能少亏，又不减少成交。
三个都是**事后**（按第十个循环的结果设计）→ V6 适用：没看过的 Zx 也要同方向。门槛 / 定义照第十个循环一个字不改：
  - HWT：信号月 5〜10（scripts/loop10_r07_final.season_gate）；
  - X2T：x2 ≤ 0（研究面板 x2；缺值 → B3；scripts/loop10_r02_diagfeat.feature_gate 同一个比较）；
  - JRT：日経 60 个交易日涨幅 − 核心（1545 合成价）同期涨幅 ≤ −0.10（scripts/loop10_r01_weakvote.rel_gap_days；那一天的全部信号）。
其余全部同 B3；不标记的信号照 B3。V4 / V6：W / Jx / Zx 用同一个函数标记（JRT 用同一条日序列）。参数事先写定（V5 不适用）。
第二关（第一关过了的才做；另行登记）：每个年代把「收紧 / 不收紧」的标签随机重排（research_loop11.permute_labels）。
事前预期（写在看第 3〜4 轮结果之前）：收紧会提高胜率、降每笔（以前的卖法研究）；HWT 标记约一半的信号 → 影响最大；第一关各约 4〜6%；「更好候选」各约 2%。
运行：python scripts/loop11_r05_gates.py --wiring（登记前的接线核对，只数个数）/ 不加参数 = 第一关（只运行一次）。
输出 var/out/loop11_r05_gates.md / .json。非投资建议。
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

ROUND = 5
IDS = ("HWT", "X2T", "JRT")
FAMILY = {k: "卖法·选股闸门改收紧" for k in IDS}
KINDS = {k: "label" for k in IDS}
POSTHOC = {k: True for k in IDS}
TIGHT = R1.TIGHT
MENU = {"flag": TIGHT}
MENUS = {k: MENU for k in IDS}
OUT = "loop11_r05_gates"


# ───────────────────────── 标记（定义 = 第十个循环的闸门） ─────────────────────────
def jrm_series(W: dict) -> pd.Series:
    import loop10_r01_weakvote as RW
    import loop9_r01_market as M9
    import loop9_r03_relative as R3
    return RW.rel_gap_days(M9.n225(W), R3.core_close(W))


def flags(k: str, X: pd.DataFrame, jrm: pd.Series | None) -> np.ndarray:
    """1 = 收紧（与第十个循环的「挡」同一个条件）。"""
    import loop10_r02_diagfeat as RD
    import loop10_r07_final as R7
    import loop9_r01_market as M9
    if k == "HWT":
        return R7.season_gate(X["date"])
    if k == "X2T":
        return RD.feature_gate(X, ("x2", "<=", 0.0))
    return M9.on_days(jrm, pd.DatetimeIndex(pd.to_datetime(X["date"])))


def labels_of(k: str, X: pd.DataFrame, jrm) -> np.ndarray:
    return np.where(np.asarray(flags(k, X, jrm), bool), "flag", "base").astype(object)


def all_labels(W: dict, jrm) -> dict:
    return {k: {e: labels_of(k, LC.signals(W, e), jrm) for e in LC.ERAS} for k in IDS}


def label_fns(jrm) -> dict:
    def fn_of(k):
        def fn(s, X, fa):
            return labels_of(k, X, jrm)
        return fn
    return {k: fn_of(k) for k in IDS}


# ───────────────────────── 登记前：只数个数 ─────────────────────────
def wiring_mode() -> int:
    t0 = time.time()
    st = R11.load_state()
    R11.check_new_approaches(st, [{"id": k, "family": FAMILY[k], "kind": KINDS[k], "posthoc": POSTHOC[k], "verdict": R11.FAIL1} for k in IDS],
                             R11.previous_ids(Path(__file__).resolve().parents[1] / "var"))
    W = LC.load()
    jrm = jrm_series(W)
    lab = all_labels(W, jrm)
    ok = LC.wiring(W, lab, MENUS)
    print("规模（只数个数）：" + json.dumps(LC.scale(W, lab), ensure_ascii=False))
    pool = {}
    fns = label_fns(jrm)
    for s, fold, sm in LC.OTHER:
        X = LC.C10.kept_pool(W, s, fold)
        pool[s] = {k: {str(a): int(b) for a, b in pd.Series(fns[k](s, X, None)).value_counts().items()} for k in IDS}
        pool[s]["n"] = len(X)
    print("W / Jx / Zx 标记个数（只数个数）：" + json.dumps(pool, ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（ID 核对通过；{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one_mode() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_r05_gates.py", "scripts/loop11_r01_cycle.py", "scripts/loop10_r01_weakvote.py",
                              "scripts/loop10_r02_diagfeat.py", "scripts/loop10_r07_final.py")
    W = LC.load()
    jrm = jrm_series(W)
    lab = all_labels(W, jrm)
    r = LC.stage_one(W, lab, MENUS, label_fns(jrm), POSTHOC, lenses=None, log=lambda m: print(m, flush=True))
    reg = R11.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in LC.ERAS}
    res = {"loop": 11, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           "menus": MENUS, **r, "drift": drift, "scale": LC.scale(W, lab), "seconds": round(time.time() - t0)}
    text = LC.render(res, f"# 第十一个研究循环第 {ROUND} 轮：HWT 5〜10 月 / X2T x2 ≤ 0 / JRT 日経落后核心 的突破收紧卖法（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环第 5 轮：HWT / X2T / JRT（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring_mode() if a.wiring else stage_one_mode()


if __name__ == "__main__":
    raise SystemExit(main())
