"""loop11_cycle_describe.py — 只描述（不是第十一个循环的做法、不算 20 个里面、不改任何规则）：回答用户「有可能每个股票种类周期都不一样？」
（2026-10-05 登记；在第 6〜7 轮结果出来之前写好、先提交后只运行一次；数字只用来解释「种类之间周期差多少」「按种类换卖法为什么没用」）。

对象：日経225 W2 信号（Z 2001〜2006 / E 2006〜2016 / J 2017〜2026，共 425 个 = 第十一个循环用的同一批）。
种类（都用第十一个循环里已登记、没改的定义与门槛）：
  - 业种三类：第 2 轮 SCY 的「景气循环 cyc / 防御 def / 金融地产 fin」（東証 33 业种 2026-08-31 版；对不上 → other）
  - 成交额三档：第 2 轮 SZK 的门槛（20 天平均成交额 lturn ≤ 9.1557 小 / ≥ 9.5445 大）
  - 波动三档：第 1 轮 VOK 的门槛（atrp ≤ 0.0164 低 / ≥ 0.0203 高）
每个「种类 × 年代」：
  1. 周期：个股自己的上涨段天数中位数 C（第 1 轮 ULC：500 日、3 × ATR 的之字形）—— 这一档 C 的中位数（天）；
  2. 三套卖法（第 1 轮的 TIGHT k 2 / 60 天、B3 k 3 / 60 天、WIDE k 4 / 90 天）的假想单笔（combo_all_study.outcomes 同一做法，扣来回成本）：
     胜率、每笔；每笔最高的那一套 = 「这一档这个年代最好的卖法」；三个年代是不是同一套 = 「稳不稳」。
假想单笔不是账户（不管仓位、资金占用、同时持有几只），只描述。非投资建议。
运行：python scripts/loop11_cycle_describe.py（只运行一次）。输出 var/out/loop11_cycle_describe.md / .json。
"""
from __future__ import annotations

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
import loop11_r02_sector as R2                                               # noqa: E402

OPTIONS = R1.OPTIONS                                                         # tight / base / wide
SIZE_CUTS = (9.1557, 9.5445)                                                 # 第 2 轮 SZK
VOL_CUTS = R1.CUTS["VOK"]                                                    # 第 1 轮 VOK
DIMS = {"sector": ("cyc", "def", "fin"), "size": ("low", "mid", "high"), "vol": ("low", "mid", "high")}
MIN_N = 10                                                                   # 一格少于 10 笔 → 不判「最好」
OUT = "loop11_cycle_describe"


# ───────────────────────── 纯函数（tests/test_loop11_cycle_describe.py） ─────────────────────────
def cell(df: pd.DataFrame) -> dict:
    """一格（同一种类同一年代）：周期中位数、三套卖法的胜率 / 每笔、每笔最高的那一套（三套都算得出的信号才算；< MIN_N → best = None）。"""
    c = pd.to_numeric(df["cycle"], errors="coerce")
    ok = np.ones(len(df), bool)
    for m in OPTIONS:
        ok &= np.isfinite(pd.to_numeric(df[f"net_{m}"], errors="coerce").to_numpy(float))
    out = {"n": int(len(df)), "n_cycle": int(c.notna().sum()), "cycle_med": None if c.notna().sum() == 0 else round(float(c.median()), 1),
           "n_trade": int(ok.sum())}
    for m in OPTIONS:
        x = pd.to_numeric(df[f"net_{m}"], errors="coerce").to_numpy(float)[ok]
        out[m] = {"win": None if not len(x) else round(float((x > 0).mean() * 100), 1), "mean": None if not len(x) else round(float(x.mean()), 2)}
    out["best"] = None if ok.sum() < MIN_N else max(OPTIONS, key=lambda m: (out[m]["mean"], m == "base"))
    return out


def stable(bests: list) -> str:
    """三个年代最好的那一套：都一样 → 那一套；有算不了的 → 「样本不够」；不一样 → 「年代间换」。"""
    if any(b is None for b in bests):
        return "样本不够"
    return bests[0] if len(set(bests)) == 1 else "年代间换"


def summarize(df: pd.DataFrame) -> dict:
    """df：每个信号一行（era、sector、size、vol、cycle、net_tight / net_base / net_wide）→ {维度: {档: {年代 / all: cell, stable}}}。"""
    res = {}
    for dim, groups in DIMS.items():
        res[dim] = {}
        for g in groups:
            sub = df[df[dim] == g]
            r = {e: cell(sub[sub["era"] == e]) for e in LC.ERAS}
            r["all"] = cell(sub)
            r["stable"] = stable([r[e]["best"] for e in LC.ERAS])
            res[dim][g] = r
    res["all"] = {e: cell(df[df["era"] == e]) for e in LC.ERAS}
    res["all"]["all"] = cell(df)
    return res


# ───────────────────────── 计算 ─────────────────────────
def build(W: dict, log=print) -> pd.DataFrame:
    p0 = W["p0"]
    bt, rt = LC.bt_rt()
    s33 = R2.s33_map()
    rows = []
    for e in LC.ERAS:
        S = LC.signals(W, e)
        fa = W["SM"][e]["fa"]
        cyc = R1.feature("ULC", S, fa)
        sec = R2.sector_labels(S["ticker"], s33)
        size = LC.label3(pd.to_numeric(S["lturn"], errors="coerce").to_numpy(float), *SIZE_CUTS)
        vol = LC.label3(pd.to_numeric(S["atrp"], errors="coerce").to_numpy(float), *VOL_CUTS)
        for i, (t, d) in enumerate(zip(S["ticker"], pd.to_datetime(S["date"]))):
            df = fa.get(t)
            r = {"era": e, "ticker": str(t), "date": d.strftime("%Y-%m-%d"), "sector": sec[i], "size": size[i], "vol": vol[i], "cycle": cyc[i]}
            for m, spec in OPTIONS.items():
                r[f"net_{m}"] = float("nan") if df is None else LC.single_net(t, df, d, p0, bt, rt, spec)
            rows.append(r)
        log(f"{e}：{len(S)} 个信号")
    return pd.DataFrame(rows)


def render(res: dict, meta: dict) -> str:
    name = {"tight": "收紧 k 2", "base": "B3 k 3", "wide": "放宽 k 4 / 90 天", None: "—"}
    dimname = {"sector": "业种三类", "size": "成交额三档", "vol": "波动三档"}
    gname = {"cyc": "景气循环", "def": "防御", "fin": "金融地产", "low": "低 / 小", "mid": "中", "high": "高 / 大"}
    L = ["# 只描述：不同种类的股票，上涨周期与「最好的卖法」差多少（日経225 W2 信号 425 个；规则见脚本开头）", "",
         f"代码 {meta['code']}{'（有未提交改动）' if meta['dirty'] else ''}；周期 = 个股自己的上涨段天数中位数（第 1 轮 ULC）；假想单笔扣来回成本、不是账户。", "",
         "| 种类 | 档 | 周期中位数（天）Z / E / J | 最好的卖法 Z / E / J | 三个年代稳不稳 | 合起来：胜率 收紧 / B3 / 放宽 | 合起来：每笔 收紧 / B3 / 放宽 |",
         "|---|---|---|---|---|---|---|"]
    for dim, groups in DIMS.items():
        for g in groups:
            r = res[dim][g]
            cy = " / ".join("—" if r[e]["cycle_med"] is None else f"{r[e]['cycle_med']:.0f}" for e in LC.ERAS)
            be = " / ".join(name[r[e]["best"]] for e in LC.ERAS)
            a = r["all"]
            wins = " / ".join("—" if a[m]["win"] is None else f"{a[m]['win']:.1f}%" for m in OPTIONS)
            means = " / ".join("—" if a[m]["mean"] is None else f"{a[m]['mean']:+.2f}%" for m in OPTIONS)
            st = name.get(r["stable"], r["stable"])
            L.append(f"| {dimname[dim]} | {gname[g]}（{a['n']} 个） | {cy} | {be} | {st} | {wins} | {means} |")
    a = res["all"]
    L += ["", "全部 425 个：周期中位数 Z / E / J = " + " / ".join("—" if a[e]["cycle_med"] is None else f"{a[e]['cycle_med']:.0f} 天" for e in LC.ERAS)
          + "；最好的卖法 " + " / ".join(name[a[e]["best"]] for e in LC.ERAS) + "。", "",
          f"一格少于 {MIN_N} 笔不判「最好」。用时 {meta['seconds']} s。非投资建议。"]
    return "\n".join(L) + "\n"


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = LC.git_head("scripts/loop11_cycle_describe.py", "scripts/loop11_r01_cycle.py", "scripts/loop11_r02_sector.py")
    W = LC.load()
    df = build(W, log=lambda m: print(m, flush=True))
    res = summarize(df)
    meta = {"code": code, "dirty": dirty, "seconds": round(time.time() - t0)}
    text = render(res, meta)
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps({**meta, "options": OPTIONS, "size_cuts": SIZE_CUTS, "vol_cuts": VOL_CUTS,
                                                             "result": res}, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
