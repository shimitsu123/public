"""candle_user_test.py — 用户图中的 K 线形状（上影陽線）第二天是不是大概率涨（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

用户：「如果出现图中形状的话第二天大概率可以涨，分析一下」（图：阳线、上影线很长、下影线很短）。
这是用户事先给的假设（不是从数据里挖出来的）→ 直接在全部时期检验，不需要探索期。

一、形状（qbreak/candles.py，比例都 ÷ 当天振幅，振幅 = 高 − 低；ATR 用前一天的 ATR(14)）
  LUB（基本）：阳线（收 > 开）；上影 ≥ 振幅 40%；下影 ≤ 15%；实体 ≥ 20%；振幅 ≥ 1.0 ATR（不是很小的 K 线）
  变体：LUB_any = 不要求振幅；LUB_strict = 上影 ≥ 实体、下影 ≤ 实体的 25%、实体 ≥ 振幅 25%、振幅 ≥ 1.2 ATR
  情境（LUB 基本各自分开看）：下跌后（前一天收盘 < 25 日线）/ 上涨后（>）；上影冲过前 20 天最高但收盘没站上（被打回）/
    收盘也站上前 20 天最高；放量（≥ 前 20 天均量 1.5 倍）/ 不放量
二、比较对象：同一时期、同一股票池的全部 K 线（基准）；另报全部阳线
三、看什么
  ① 第二天收盘 > 今天收盘 的比例（用户说的「第二天涨」）；平均 n1_cc（第二天收盘 / 今天收盘 − 1）
  ② 我们买得到的部分（执行器在第二天开盘买）：g1 第二天开盘 / 今天收盘 − 1；n1_oc 第二天 收盘 / 开盘 − 1
  ③ 之后：第二天开盘买、5 / 20 个交易日后开盘卖，减同一天全部样本的平均（超额）
  95% 区间：按月聚类的自助法 2,000 次（种子 20260927）；「差」= 形状 − 基准。
四、时期与股票池：E0 2006-10〜2016-09（yfinance 今天的日経225，J-Quants 之前的年代）；T 2017〜2021、V 2022-01〜2023-09、
  H 2023-10〜2026-09（J-Quants 时点 TOPIX 1000 的每日成员）；另报今天的日経225（J-Quants）T / V / H。
五、判定（事先写定；只报告，不改模拟盘）
  「第二天大概率涨」成立 = 4 个时期（E0 / T / V / H，TOPIX 1000 口径）都：① 的比例 ≥ 50%，且比基准高（差的 95% 区间下限 > 0）
  「开盘买得到的上涨」成立 = 4 个时期都：n1_oc 平均 > 0 且 5 日超额平均 > 0（两者 95% 区间下限都 > 0）
登记前做过的检查：tests/test_candles.py（用户图中形状的几何、形态不看未来、经典形态例子、目标与超额）、tests/test_candle_user_test.py；
  只数过出现次数（不看结果）：LUB 基本 E0 5,481 / T 13,968 / V 4,334 / H 9,342 次（全部 K 线的约 1.1〜1.4%）；LUB_any 20,215〜54,788；
  LUB_strict 1,006〜3,485。
输出：var/out/candle_user_test.md / .json（只有统计）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candle_data as CD                                                     # noqa: E402
from qbreak import candles as K                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

N_BOOT, SEED = 2000, 20260927
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_ids(days) -> np.ndarray:
    return (days.year * 100 + days.month).to_numpy()


def boot_diff(yp: np.ndarray, mp: np.ndarray, yb: np.ndarray, mb: np.ndarray, n: int = N_BOOT, seed: int = SEED) -> tuple:
    """「形状的平均 − 基准的平均」与按月聚类的自助法 95% 区间（月份一起抽：同一个月的形状与基准一起进出）。"""
    if not len(yp) or not len(yb):
        return float("nan"), float("nan"), float("nan"), float("nan")
    um, inv = np.unique(np.r_[mp, mb], return_inverse=True)
    ip, ib = inv[:len(mp)], inv[len(mp):]
    k = len(um)
    sp, cp = np.bincount(ip, yp, k), np.bincount(ip, minlength=k).astype(float)
    sb, cb = np.bincount(ib, yb, k), np.bincount(ib, minlength=k).astype(float)
    pick = np.random.default_rng(seed).integers(0, k, size=(n, k))
    Sp, Cp, Sb, Cb = sp[pick].sum(1), cp[pick].sum(1), sb[pick].sum(1), cb[pick].sum(1)
    ok = (Cp > 0) & (Cb > 0)
    d = Sp[ok] / Cp[ok] - Sb[ok] / Cb[ok]
    lo, hi = np.percentile(d, [2.5, 97.5]) if len(d) else (np.nan, np.nan)
    return float(yp.mean()), float(yp.mean() - yb.mean()), float(lo), float(hi)


def shapes(P: dict) -> tuple[dict, dict, dict]:
    g = K.geometry(P)
    x = K.context(P, g)
    pat = K.patterns(P, g, x)
    with np.errstate(invalid="ignore"):
        s = {"LUB": pat["LUB"],
             "LUB_any": g["bull"] & (g["up_r"] >= 0.4) & (g["lo_r"] <= 0.15) & (g["body_r"] >= 0.2),
             "LUB_strict": g["bull"] & (g["up"] >= g["ab"]) & (g["lo"] <= 0.25 * g["ab"]) & (g["body_r"] >= 0.25) & (g["size"] >= 1.2),
             "阳线（全部）": g["bull"]}
        c = {"下跌后（前一天 < 25 日线）": pat["LUB"] & x["dn_tr"], "上涨后（前一天 > 25 日线）": pat["LUB"] & x["up_tr"],
             "上影冲过 20 日最高、收盘被打回": pat["LUB"] & x["hi20_poke"] & ~x["hi20_close"],
             "收盘也站上 20 日最高": pat["LUB"] & x["hi20_close"],
             "放量（≥ 1.5 倍）": pat["LUB"] & x["vsurge"], "不放量": pat["LUB"] & ~x["vsurge"]}
    return {k: np.asarray(v, bool) for k, v in s.items()}, {k: np.asarray(v, bool) for k, v in c.items()}, g


def measure(mask: np.ndarray, base: np.ndarray, T: dict, mids: np.ndarray, rows: np.ndarray) -> dict:
    """一个形状在一个时期的全部指标。mask / base：日期 × 票；rows：这个时期的行。"""
    out = {}
    R = np.broadcast_to(mids[:, None], mask.shape)
    for key in ("up1", "n1_cc", "g1", "n1_oc", "x5", "x20"):
        Y = T[key]
        fin = np.isfinite(Y) & rows[:, None]
        a, b = mask & fin, base & fin
        yp, yb = Y[a], Y[b]
        m, d, lo, hi = boot_diff(yp, R[a], yb, R[b])
        out[key] = {"n": int(a.sum()), "mean": m, "diff": d, "lo": lo, "hi": hi}
    return out


def main() -> int:
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/candle_user_test.py", "scripts/candle_data.py",
                                 "qbreak/candles.py"], capture_output=True, text=True).stdout.strip())
    D = CD.load()
    res: dict = {}
    books = {}
    for src in ("J", "E"):
        P = D["P"] if src == "J" else D["E"]
        days = D["days"] if src == "J" else D["edays"]
        s, c, g = shapes(P)
        t = K.targets(P, horizons=(5, 20))
        mems = {"U2": D["mem"]["U2"], "U0": D["mem"]["U0"]} if src == "J" else {"E": np.isfinite(P["C"])}
        for u, mem in mems.items():
            T = {"up1": np.where(np.isfinite(t["n1_cc"]), (t["n1_cc"] > 0).astype(float), np.nan), "n1_cc": t["n1_cc"], "g1": t["g1"],
                 "n1_oc": t["n1_oc"], "x5": K.excess(t["f5"], mem & g["ok"]), "x20": K.excess(t["f20"], mem & g["ok"])}
            books[(src, u)] = (s, c, g["ok"] & mem, T, month_ids(days), days)
    fmt = lambda v, f: "—" if v is None or not np.isfinite(v) else f.format(v)                          # noqa: E731
    pct = lambda r: f"{fmt(r['mean'] * 100, '{:.1f}%')}（{fmt(r['diff'] * 100, '{:+.1f}')} pp，{fmt(r['lo'] * 100, '{:+.1f}')}〜{fmt(r['hi'] * 100, '{:+.1f}')}）"   # noqa: E731
    mn = lambda r: f"{fmt(r['mean'] * 100, '{:+.2f}%')}（{fmt(r['lo'] * 100, '{:+.2f}')}〜{fmt(r['hi'] * 100, '{:+.2f}')}）"   # noqa: E731
    cols = [("E", "E", "E0"), ("J", "U2", "T"), ("J", "U2", "V"), ("J", "U2", "H")]
    cols_u0 = [("J", "U0", "T"), ("J", "U0", "V"), ("J", "U0", "H")]

    def run(names, which, colset):
        out = {}
        for nm in names:
            for src, u, per in colset:
                s, c, base, T, mids, days = books[(src, u)]
                mask = (s if which == "s" else c)[nm] & base
                out[(nm, src, u, per)] = measure(mask, base, T, mids, CD.period_mask(days, per))
        return out
    S = run(["LUB", "LUB_any", "LUB_strict", "阳线（全部）"], "s", cols)
    S0 = run(["LUB"], "s", cols_u0)
    Cx = run(list(books[("J", "U2")][1]), "c", cols)
    say("# 用户图中的 K 线形状（上影陽線）：第二天是不是大概率涨（2026-09-27）")
    say("规则见 scripts/candle_user_test.py 开头（先提交后运行）。E0 = 2006-10〜2016-09 yfinance 今天的日経225；T / V / H = J-Quants 时点 TOPIX 1000 成员。")
    say("括号 = 与全部 K 线（基准）的差与按月聚类 95% 区间；n = 形状出现的次数。")
    say("\n## ① 第二天收盘 > 今天收盘 的比例")
    say("| 形状 | " + " | ".join(CD.PERIOD_NAMES[p] for _, _, p in cols) + " |")
    say("|---|---|---|---|---|")
    for nm in ["LUB", "LUB_any", "LUB_strict", "阳线（全部）"]:
        say(f"| {nm} | " + " | ".join(f"{pct(S[(nm, s_, u, p)]['up1'])} n={S[(nm, s_, u, p)]['up1']['n']:,}" for s_, u, p in cols) + " |")
    base_row = []
    for s_, u, p in cols:
        s, c, base, T, mids, days = books[(s_, u)]
        rows = CD.period_mask(days, p)[:, None]
        y = T["up1"][base & rows & np.isfinite(T["up1"])]
        base_row.append(f"{y.mean() * 100:.1f}% n={len(y):,}")
    say("| 全部 K 线（基准） | " + " | ".join(base_row) + " |")
    say("| LUB（今天的日経225，J-Quants） | — | " + " | ".join(f"{pct(S0[('LUB', 'J', 'U0', p)]['up1'])} n={S0[('LUB', 'J', 'U0', p)]['up1']['n']:,}" for _, _, p in cols_u0) + " |")
    for key, title in (("n1_cc", "第二天收盘 / 今天收盘 − 1 的平均"), ("g1", "第二天开盘 / 今天收盘 − 1（跳空）的平均"),
                       ("n1_oc", "第二天开盘买、收盘卖（我们买得到的第一天）"), ("x5", "第二天开盘买、5 个交易日后开盘卖的超额"),
                       ("x20", "第二天开盘买、20 个交易日后开盘卖的超额")):
        say(f"\n## {'②' if key in ('n1_cc', 'g1', 'n1_oc') else '③'} {title}")
        say("| 形状 | " + " | ".join(CD.PERIOD_NAMES[p] for _, _, p in cols) + " |")
        say("|---|---|---|---|---|")
        for nm in ["LUB", "LUB_any", "LUB_strict", "阳线（全部）"]:
            say(f"| {nm} | " + " | ".join(mn(S[(nm, s_, u, p)][key]) for s_, u, p in cols) + " |")
        say("| LUB（今天的日経225） | — | " + " | ".join(mn(S0[("LUB", "J", "U0", p)][key]) for _, _, p in cols_u0) + " |")
    say("\n## ④ 情境（LUB 基本）：第二天收盘涨的比例 / 第二天开盘买收盘卖 / 5 日超额")
    say("| 情境 | " + " | ".join(CD.PERIOD_NAMES[p] for _, _, p in cols) + " |")
    say("|---|---|---|---|---|")
    for nm in books[("J", "U2")][1]:
        cells = []
        for s_, u, p in cols:
            r = Cx[(nm, s_, u, p)]
            cells.append(f"{fmt(r['up1']['mean'] * 100, '{:.1f}%')} / {fmt(r['n1_oc']['mean'] * 100, '{:+.2f}%')} / "
                         f"{fmt(r['x5']['mean'] * 100, '{:+.2f}%')}（n={r['up1']['n']:,}）")
        say(f"| {nm} | " + " | ".join(cells) + " |")
    lub = [S[("LUB", s_, u, p)] for s_, u, p in cols]
    ok1 = all(r["up1"]["mean"] >= 0.5 and r["up1"]["lo"] > 0 for r in lub)
    ok2 = all(r["n1_oc"]["mean"] > 0 and r["n1_oc"]["lo"] > 0 and r["x5"]["mean"] > 0 and r["x5"]["lo"] > 0 for r in lub)
    say("\n## 判定（事先写定）")
    say(f"- 「第二天大概率涨」：{'成立' if ok1 else '不成立'}（4 个时期的比例：" + "、".join(f"{r['up1']['mean'] * 100:.1f}%" for r in lub)
        + "；与基准的差区间下限：" + "、".join(f"{r['up1']['lo'] * 100:+.1f} pp" for r in lub) + "）")
    say(f"- 「开盘买得到的上涨」：{'成立' if ok2 else '不成立'}（第二天开盘买收盘卖：" + "、".join(f"{r['n1_oc']['mean'] * 100:+.2f}%" for r in lub)
        + "；5 日超额：" + "、".join(f"{r['x5']['mean'] * 100:+.2f}%" for r in lub) + "）")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    res = {"code": code, "dirty": dirty, "verdict": {"next_day_up": ok1, "tradable": ok2},
           "S": {"|".join(k): v for k, v in S.items()}, "S_U0": {"|".join(k): v for k, v in S0.items()},
           "context": {"|".join(k): v for k, v in Cx.items()}}
    fp = paths.out_dir() / "candle_user_test"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
