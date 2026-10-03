"""vsx_us_history.py — VSX「牛市里只在波动冲击时减仓」的美国长历史核对（2026-10-04 登记；先提交后只运行一次；只给用户决定（待办 ㊾）作参考）。

来由（照实写）：第七个研究循环第 3 轮 VSX（登记 9c959ba，只运行一次）在账户上第一关全过（+0.594，含没看过的 1987〜2000 +0.057），
  但 17 个独立市场不成立（合并 +0.001、7 / 17 为正），美国 S&P 500 1998〜2026 +0.124 → 只在美国成立。循环按规则停下（待办 ㊾）。
  「只在美国成立」可能是美国自己的规律（例如按波动调仓位的资金在美国最多 → 波动升高后的卖压更强），也可能只是美国这几十年的运气。
  能分开这两种的数据：VSX 从没碰过的美国更早的历史 —— S&P 500（Yahoo ^GSPC，1927-12-30 起的日收盘；1957 年以前是 S&P 的 90 只综合指数）
  1929〜1986 共 58 年（账户的 S7 用的是 1987〜2000 的纳指，横展开用的是 1998〜2026），里面有 1929〜32、1937〜38、1940、1946、1962、1966、
  1969〜70、1973〜74、1980〜82 的下跌。这是看过 VSX 第二关不过之后才加的核对（事后）：**不改第七个循环的判定（VSX = 第二关不过）、不改模拟盘**；
  结果只用来给用户决定 ㊾ 时参考（例如要不要把 VSX 加进前向记录）。
规则（全部事先写定；VSX 一字不改 = scripts/loop7_r03_volshock.shock_ratio；基准与费用同第七个循环的横展开）：
  - 指数：S&P 500 价格指数（本币）。窗口 WINDOW = 1929-01-02〜1986-12-31（σ250 与牛熊分界都用 1927-12-30 起的全部历史、只用到当天为止）。
  - 基准：S&P 自己的牛熊分界（模拟盘同一个检测器与参数）→ 牛 100%、其余现金；候选：牛 → 指数 × VSX 比例、其余现金。
    收盘决定、下一个交易日起生效；换仓扣 0.1% × 换的比例；现金 0（research_loop7.nav / calmar）。
  - 统计量：窗口内 Calmar 差 Δ（候选 − 基准）。
  - U1：Δ > 0 且严格大于 400 次随机的最大值（比例序列在窗口内的交易日上整体循环平移 k，k ∈ [250, N − 250]，
    numpy.random.default_rng([20261008, 0, s])，s = 0〜399；窗外不动；基准不动）。
  - U2：六段（1929〜1939、1940〜1949、1950〜1959、1960〜1969、1970〜1979、1980〜1986，各自重新起算 Calmar）里 Δ > 0 的 ≥ 4 段（2/3）。
  - U3：窗口按交易日一分为二，两半的 Δ 都 > 0。
  - 结论：「强支持」= U1 ∧ U2 ∧ U3；「弱支持」= Δ > 0 ∧ U2 ∧ U3 ∧ Δ 至少是随机的第 95 百分位（不到 U1）；其余 =「不支持」。
    强 / 弱支持 → 在 ㊾ 里把「VSX 加进前向记录」写成推荐；不支持 → 推荐「结束」。采用（改模拟盘）在任何情况下都要用户另说。
只描述（不参与结论）：六段各自的 Δ、两个账户的年化 / 最大回撤、牛的日子里比例 < 1 的比例、随机的分位数。
多重检验（照实写）：这是第七个循环停下之后追加的一次核对（只一次、只 VSX 一个）；事前预期写在登记（var/sim_changes.md）里、看结果之前。
原始数据（Yahoo 的指数日线）只在内存，不入库；输出只存导出的数字。
运行：python scripts/vsx_us_history.py（只运行一次）；--scale（只数日子）。输出 var/out/vsx_us_history.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop7_r02_voltarget as P2                                             # noqa: E402
import loop7_r03_volshock as P3                                              # noqa: E402
import research_loop7 as R7                                                  # noqa: E402

SYMBOL, DATA_START = "^GSPC", "1927-01-01"
WINDOW = ("1929-01-02", "1986-12-31")
DECADES = (("1929-01-02", "1939-12-31"), ("1940-01-01", "1949-12-31"), ("1950-01-01", "1959-12-31"),
           ("1960-01-01", "1969-12-31"), ("1970-01-01", "1979-12-31"), ("1980-01-01", "1986-12-31"))
PLACEBO_N, SEED, GAP = 400, 20261008, 250
DECADE_NEED = 4
PCT_WEAK = 95.0
OUT = "vsx_us_history"
STRONG, WEAK, NONE = "强支持", "弱支持", "不支持"


# ───────────────────────── 纯函数（tests/test_vsx_us_history.py） ─────────────────────────
def window_days(idx: pd.DatetimeIndex, w=WINDOW) -> pd.DatetimeIndex:
    return idx[(idx >= pd.Timestamp(w[0])) & (idx <= pd.Timestamp(w[1]))]


def shift_ks(n: int, seeds=range(PLACEBO_N), gap: int = GAP) -> list[int]:
    if n <= 2 * gap:
        raise ValueError(f"窗口太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([SEED, 0, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


def deltas(close: pd.Series, bull: pd.Series, ratio: pd.Series, k: int | None, spans: list[tuple[str, str]]) -> list[float | None]:
    """各段 Calmar（候选 = 牛 × 窗口内平移 k 的比例）− 基准（牛 100%）；平移 = loop7_r02_voltarget.shifted_num（窗口换成本核对的）。"""
    base = R7.nav(close, bull.astype(float))
    cand = R7.nav(close, P2.expo(bull, P2.shifted_num(ratio, k, WINDOW)))
    out = []
    for a, z in spans:
        cb, cc = R7.calmar(base, a, z), R7.calmar(cand, a, z)
        out.append(None if cb is None or cc is None else cc - cb)
    return out


def spans_of(close: pd.Series) -> list[tuple[str, str]]:
    """[全窗口, 前一半, 后一半, 六段 …]（都按这个指数自己的交易日）。"""
    days = window_days(close.index)
    h1, h2 = R7.halves(days)
    return [(str(days[0].date()), str(days[-1].date())), h1, h2] + [tuple(d) for d in DECADES]


def verdict(real: list[float | None], plac: list[float | None]) -> dict:
    """real = deltas(k=None)；plac = 400 次随机的全窗口 Δ。"""
    full, h1, h2, dec = real[0], real[1], real[2], real[3:]
    if full is None or any(x is None for x in plac):
        return {"verdict": NONE, "why": "有算不出的", "U1": False, "U2": False, "U3": False}
    pv = np.array(plac, float)
    pos = int(sum(1 for x in dec if x is not None and x > 0))
    u1 = full > 0 and full > float(pv.max())
    u2 = pos >= DECADE_NEED
    u3 = h1 is not None and h2 is not None and h1 > 0 and h2 > 0
    pct = float((pv < full).mean() * 100)
    if u1 and u2 and u3:
        v = STRONG
    elif full > 0 and u2 and u3 and pct >= PCT_WEAK:
        v = WEAK
    else:
        v = NONE
    return {"verdict": v, "U1": bool(u1), "U2": bool(u2), "U3": bool(u3), "full": round(full, 6), "h1": None if h1 is None else round(h1, 6),
            "h2": None if h2 is None else round(h2, 6), "decades": [None if x is None else round(x, 6) for x in dec], "decades_pos": pos,
            "pctile": round(pct, 1), "max": round(float(pv.max()), 6), "ge_stat": int((pv >= full).sum()),
            "q": {q: round(float(np.percentile(pv, q)), 6) for q in (50, 95, 99)}}


# ───────────────────────── 运行 ─────────────────────────
def inputs() -> dict:
    c = R7.load_close(SYMBOL, DATA_START)
    if c.index[0] > pd.Timestamp("1928-01-31") or c.index[-1] < pd.Timestamp(WINDOW[1]):
        raise RuntimeError(f"数据不够：{c.index[0].date()}〜{c.index[-1].date()}")
    return {"close": c, "bull": R7.bull(c), "ratio": P3.shock_ratio(c)}


def scale(I: dict) -> dict:
    out = {}
    for name, (a, z) in [("window", WINDOW)] + [(f"{d[0][:4]}〜{d[1][:4]}", d) for d in DECADES]:
        days = window_days(I["close"].index, (a, z))
        b = I["bull"].reindex(days).fillna(False).astype(bool)
        out[name] = {"days": int(len(days)), "bull_pct": round(float(b.mean() * 100), 1), **P2.cut_share(b, I["ratio"].reindex(days))}
    return out


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/vsx_us_history.py", "scripts/loop7_r03_volshock.py",
                                 "scripts/loop7_r02_voltarget.py", "scripts/research_loop7.py", "qbreak/vct_forward.py", "qbreak/bullbear.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def run() -> int:
    t0 = time.time()
    code, dirty = git_head()
    I = inputs()
    c, b, x = I["close"], I["bull"], I["ratio"]
    sp = spans_of(c)
    real = deltas(c, b, x, None, sp)
    n = len(window_days(c.index))
    ks = shift_ks(n)
    plac = []
    for i, k in enumerate(ks):
        plac.append(deltas(c, b, x, k, sp[:1])[0])
        if (i + 1) % 100 == 0:
            print(f"随机 {i + 1} / {len(ks)}（{time.time() - t0:.0f}s）", flush=True)
    vd = verdict(real, plac)
    base, cand = R7.nav(c, b.astype(float)), R7.nav(c, P2.expo(b, x))
    def stats(nv, a, z):
        s = nv[(nv.index >= pd.Timestamp(a)) & (nv.index <= pd.Timestamp(z))]
        s = s / s.iloc[0]
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        return {"cagr": round((float(s.iloc[-1]) ** (1 / yrs) - 1) * 100, 2), "dd": round(float((s / s.cummax() - 1).min()) * 100, 2),
                "calmar": None if R7.calmar(nv, a, z) is None else round(R7.calmar(nv, a, z), 3)}
    acct = {nm: {"B": stats(base, a, z), "VSX": stats(cand, a, z)} for nm, (a, z) in [("window", sp[0])] + [(f"{d[0][:4]}〜{d[1][:4]}", d) for d in DECADES]}
    res = {"study": "vsx_us_history", "code": code, "dirty": dirty, "symbol": SYMBOL, "window": list(WINDOW), "n": n, "spans": sp, "real": real,
           "ks": ks, "placebo": plac, "verdict": vd, "acct": acct, "scale": scale(I), "seconds": round(time.time() - t0)}
    write(res)
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    f = P2._f
    v = res["verdict"]
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# VSX 美国长历史核对：S&P 500 1929〜1986（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/vsx_us_history.py 开头）", "",
         f"**{v['verdict']}** —— 不改第七个循环的判定（VSX = 第二关不过）、不改模拟盘；只给待办 ㊾ 作参考。", "",
         f"- U1 {yn(v.get('U1'))}：全窗口 Δ {f(v.get('full'))}（400 次随机平移最大 {f(v.get('max'))}、≥ 候选 {v.get('ge_stat')} 次、约第 {f(v.get('pctile'), '{:.1f}')} 百分位；"
         f"中位 {f((v.get('q') or {}).get(50))}、95 分位 {f((v.get('q') or {}).get(95))}、99 分位 {f((v.get('q') or {}).get(99))}）",
         f"- U2 {yn(v.get('U2'))}：六段里 Δ > 0 的 {v.get('decades_pos')} 段（要 ≥ {DECADE_NEED}）",
         f"- U3 {yn(v.get('U3'))}：两半 {f(v.get('h1'))} / {f(v.get('h2'))}", "",
         "| 时期 | 交易日 | 牛的比例 | 牛里比例 < 1 | 基准 年化 / 回撤 / Calmar | VSX 年化 / 回撤 / Calmar | Δ |", "|---|---:|---:|---:|---|---|---:|"]
    names = ["window"] + [f"{d[0][:4]}〜{d[1][:4]}" for d in DECADES]
    dvals = [res["real"][0]] + list(res["real"][3:])
    for nm, dv in zip(names, dvals):
        s, a = res["scale"][nm], res["acct"][nm]
        cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'], '{:.3f}')}"   # noqa: E731
        L.append(f"| {'全窗口 1929〜1986' if nm == 'window' else nm} | {s['days']} | {s['bull_pct']}% | {f(s['cut_pct'], '{:.1f}')}% | "
                 f"{cell(a['B'])} | {cell(a['VSX'])} | {f(dv)} |")
    L += ["", f"随机 = 比例序列在窗口内（{res['n']} 个交易日）整体循环平移 k（种子 [20261008, 0, s]）；基准 = S&P 自己的牛熊分界（牛 100%、其余现金）；"
          "收盘决定、下一个交易日生效；换仓扣 0.1% × 换的比例。1957 年以前的 ^GSPC 是 S&P 的 90 只综合指数。", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    I = inputs()
    print(json.dumps({"start": str(I["close"].index[0].date()), "n": int(len(window_days(I["close"].index))), "scale": scale(I)},
                     ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="VSX 美国长历史核对（S&P 500 1929〜1986）")
    ap.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else run()


if __name__ == "__main__":
    raise SystemExit(main())
