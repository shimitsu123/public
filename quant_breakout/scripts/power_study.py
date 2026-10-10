"""power_study.py — 检验力测算（statistical power）：以前用的两种第二关，能有多大把握认出「真的有用」的减仓规则
（2026-10-04 登记；先提交后只运行一次；第七个研究循环结束后「换别的方向」的第一步；只描述，不改模拟盘、不改任何循环的判定）。

用户（2026-10-04，待办 ㊿）：「④ 换别的方向继续研究」。为什么先做这个（照实写）：
  - 七个研究循环约 112 个做法，两关都过、站得住的只有 BCU；择时类在第二关里一个都没过（单一序列：随机平移的最大值在中位以上 2.5〜4.0 个标准差，
    候选只有 1.4〜2.6；第七个循环 17 个市场合并：三个波动类规则都只比随机中位好 +0.005〜+0.012）。
  - 独立扫描（只读子任务，2026-10-04）：剩下的「找新规则」方向两关都过的概率都 < 3%（最好的日経225 新采用事件约 2%），建议先量检验力。
  - 「都没过」有两种可能：规则真的没用，或者检验太严、真有用的也认不出来。两种的下一步完全不同 → 先量清楚，再由用户决定怎么继续。
一 合成规则（知道答案的「半个先知」；只用来量检验，不是交易规则）：
  - 每个市场（第七个循环的 17 个 + 美国 S&P500）在窗口 WINDOW = 1998-01-01〜2026-09-30：危险日 = 自己是牛的日子里、
    「之后 20 个交易日的收益」（d 收盘 → d + 20 收盘）落在窗口内牛市日子最差 10% 的那天（只有事后才知道）；连续的危险日 = 一段。
  - 技能 q（认出的比例）：每一段以概率 q 被认出 —— 用这一段第一天所在月份的同一个随机数（17 + 1 个市场共用 → 全球同时的大跌要认一起认、
    要漏一起漏，更像真实规则），随机数 < q 就认出；认出的段从段开始后第 L 个交易日起、持续同样长（L = 0 = 先知；L = 5 = 晚 5 天才认出）。
  - 噪音：另外在窗口内的牛市日子里随机放信号段（长度从这个市场的危险段长度里抽、起点随机；与危险日无关 → 碰到危险日的比例 ≈ 本来的 10%），
    噪音天数 = 0.5 × 危险日总数（与 q 无关，各市场各自抽）→ q = 0 = 只有噪音 = 没有技能的规则（量偶然过关）；q = 0.5 时认出的与噪音大约一样多。
    （登记前在合成随机游走上试跑时发现：噪音若只放在「不是危险日」的日子，q = 0 会系统地避开最差的日子、变成「反技能」→ 改成与危险日无关。）
  - 熊市里补同样密度（fill_off）：窗口内「不是牛」的日子补上随机信号段，密度 = 信号在牛市日子里的密度（这些日子本来就是现金、对规则自己没有影响）
    → 平移以后落在牛市日子里的信号与原信号一样多（真实规则在熊市里也照样算信号；不补的话随机对照落在牛市里的信号会少两〜四成，比较就混进了「多少」）。
  - 动作：牛 ∧ 信号 → 指数 2/3（同 VCX / VCT 的 1/3 现金）；其余同基准（自己的牛熊分界：牛 100%、其余现金）；收盘决定、下一个交易日生效、换仓扣 0.1% × 换的比例。
二 检验（与以前的第二关同一写法、同一组函数）：
  - 横展开 = 第七个循环三的 C1〜C3（research_loop7.judge）：17 个市场、同一 k 平移信号 400 次（research_loop7.shift_ks，与第七个循环相同的 k）、
    合并平均严格大于 400 次的最大值、≥ 12 / 17 为正、前后两半都 > 0。
  - 单一序列 = 第二〜六个循环第二关的同一个思路（账户换成 S&P500 指数本身，快很多）：美国一个市场、信号在窗口内平移 400 次（同一组 k），
    全窗口 Δ > 0 且严格大于 400 次的最大值。
三 设计：q ∈ QS = (0, 0.1, 0.25, 0.5, 1.0) × L ∈ LAGS = (0, 5)，每格 SEEDS = 10 个合成规则
  （月份随机数 numpy.random.default_rng([20261009, iq, L, s, 0])；第 j 个市场的误报与熊市补的段 default_rng([20261009, iq, L, s, 1 + j])）→ 100 个规则，每个两种检验都跑。
四 读法（事先写定）：
  - 检验力 = 一格里「过」的比例。横展开在 q = 0.5、L = 5 这一格 ≥ 50% →「检验力够」；< 20% →「检验力不够」；之间 =「一般」。单一序列同样读。
  - 最低能认出的技能 = L = 5 那一行里「过」的比例 ≥ 50% 的最小 q（两种检验各一个；到 q = 1 也不到一半 = 没有）。
  - q = 0 两格（20 个没有技能的规则）「过」的比例 = 偶然过关率（按设计应约 0.25%，> 5% 就照实写「检验本身有问题」）。
  - 校准（只描述）：第七个循环三个真实规则（VCX / VTX / VSX）的「合并 Δ − 400 次随机的中位」与各格合成规则的同一个量比，看它们大约相当于多大的 q。
  - 怎么用：「检验力够」而真实规则都没过 → 它们的技能比 q = 0.5 低很多，继续找同类规则意义不大；「检验力不够」→ 以前的「没过」不能说明规则没用，
    要不要换检验方法（只对以后的研究、要用户同意）由用户决定。都不改模拟盘、不改以前任何一轮的判定。
原始数据（Yahoo 的指数日线）只在内存，不入库；输出只存导出的数字。
运行：python scripts/power_study.py（只运行一次；--workers 4）；--scale（只数危险日 / 段）。输出 var/out/power_study.md / .json。非投资建议。
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
import research_loop7 as R7                                                  # noqa: E402

WINDOW = R7.WINDOW
H, TAIL = 20, 0.10
KEEP = 2.0 / 3.0
FA_RATIO = 0.5
QS = (0.0, 0.1, 0.25, 0.5, 1.0)
LAGS = (0, 5)
SEEDS = 10
SEED = 20261009
POWER_OK, POWER_LOW = 0.5, 0.2
REAL = {"VCX": "loop7_r01_vctx.json", "VTX": "loop7_r02_voltarget.json", "VSX": "loop7_r03_volshock.json"}
OUT = "power_study"


# ───────────────────────── 合成规则（纯函数，tests/test_power_study.py） ─────────────────────────
def in_window(idx: pd.DatetimeIndex, w=WINDOW) -> np.ndarray:
    return np.asarray((idx >= pd.Timestamp(w[0])) & (idx <= pd.Timestamp(w[1])))


def fwd_ret(close: pd.Series, h: int = H) -> pd.Series:
    """d 收盘 → d + h 收盘的收益（最后 h 天没有）。"""
    c = close.astype(float)
    return c.shift(-h) / c - 1.0


def danger(close: pd.Series, bull: pd.Series, w=WINDOW, h: int = H, tail: float = TAIL) -> pd.Series:
    """窗口内牛市日子里、之后 h 天收益 ≤ 这些日子的 tail 分位 → 危险日（事后才知道）。"""
    f = fwd_ret(close, h)
    b = bull.reindex(close.index).fillna(False).astype(bool).to_numpy()
    ok = b & in_window(close.index, w) & f.notna().to_numpy()
    thr = float(np.quantile(f.to_numpy()[ok], tail)) if ok.any() else -np.inf
    return pd.Series(ok & (f.fillna(np.inf).to_numpy() <= thr), index=close.index)


def runs(flag: pd.Series) -> list[tuple[int, int]]:
    """连续 True 的段（位置，含两端）。"""
    v = np.asarray(flag, dtype=bool)
    if not len(v):
        return []
    d = np.diff(np.concatenate([[0], v.astype(int), [0]]))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def month_draws(q_idx: int, lag: int, s: int, w=WINDOW) -> dict[str, float]:
    """一个合成规则：窗口内每个月一个 [0, 1) 随机数（所有市场共用）。"""
    months = pd.period_range(pd.Timestamp(w[0]), pd.Timestamp(w[1]), freq="M").strftime("%Y-%m").tolist()
    u = np.random.default_rng([SEED, int(q_idx), int(lag), int(s), 0]).random(len(months))
    return dict(zip(months, u.tolist()))


def synth(close: pd.Series, bull: pd.Series, dflag: pd.Series, q: float, lag: int, mu: dict[str, float], rng: np.random.Generator,
          fa_ratio: float = FA_RATIO, w=WINDOW) -> pd.Series:
    """合成信号：认出的危险段（晚 lag 天、同样长）∪ 噪音段（窗口内的牛市日子、与危险日无关，天数 = fa_ratio × 危险日总数）；窗外 = False。"""
    idx = close.index
    n = len(idx)
    dv = dflag.reindex(idx).fillna(False).to_numpy(bool)
    inw = in_window(idx, w)
    b = bull.reindex(idx).fillna(False).to_numpy(bool)
    s = np.zeros(n, bool)
    rs = runs(dv)
    for a, z in rs:
        if mu.get(idx[a].strftime("%Y-%m"), 1.0) < q:
            s[min(a + lag, n - 1):min(z + lag, n - 1) + 1] = True
    ok = b & inw
    cand = np.flatnonzero(ok)
    target = int(round(fa_ratio * dv.sum()))
    lens = [z - a + 1 for a, z in rs] or [5]
    fa = np.zeros(n, bool)
    tries = 0
    while int(fa.sum()) < target and len(cand) and tries < 200000:
        ln, st = int(rng.choice(lens)), int(rng.choice(cand))
        seg = np.arange(st, min(st + ln, n))
        fa[seg[ok[seg]]] = True
        tries += 1
    return pd.Series((s | fa) & inw, index=idx)


def fill_off(sig: pd.Series, bull: pd.Series, lens: list[int], rng: np.random.Generator, w=WINDOW) -> pd.Series:
    """窗口内「不是牛」的日子补上同样密度的随机信号段（自己不起作用：那些日子本来就是现金）
    → 平移后的随机信号落在牛市日子的密度与原信号一样（真实规则在熊市里也照样算信号）。"""
    idx = sig.index
    n = len(idx)
    inw = in_window(idx, w)
    b = bull.reindex(idx).fillna(False).to_numpy(bool)
    s = sig.to_numpy(bool).copy()
    on, off = b & inw, ~b & inw
    target = int(round(float(s[on].mean()) * off.sum())) if on.any() else 0
    cand = np.flatnonzero(off)
    lens = [int(x) for x in lens] or [5]
    tries = 0
    while int((s & off).sum()) < target and len(cand) and tries < 200000:
        ln, st = int(rng.choice(lens)), int(rng.choice(cand))
        seg = np.arange(st, min(st + ln, n))
        s[seg[off[seg]]] = True
        tries += 1
    return pd.Series(s & inw, index=idx)


def ratio_of(sig: pd.Series) -> pd.Series:
    """信号 → 牛市里的仓位比例（信号 → 2/3，其余 1）；平移比例 = 平移信号。"""
    return pd.Series(np.where(sig.to_numpy(bool), KEEP, 1.0), index=sig.index)


def single_judge(real: float | None, plac: list[float | None]) -> dict:
    """单一序列：Δ > 0 且严格大于 400 次的最大值（有算不出的 = 不过）。"""
    if real is None or any(x is None for x in plac):
        return {"ok": False, "real": real, "max": None, "pct": None}
    pv = np.array(plac, float)
    return {"ok": bool(real > 0 and real > float(pv.max())), "real": round(float(real), 6), "max": round(float(pv.max()), 6),
            "median": round(float(np.median(pv)), 6), "pct": round(float((pv < real).mean() * 100), 1)}


def power_label(rate: float) -> str:
    return "检验力够" if rate >= POWER_OK - 1e-12 else ("检验力不够" if rate < POWER_LOW - 1e-12 else "一般")


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs() -> dict:
    keys = list(R7.MARKETS) + list(R7.SOURCE)
    closes = R7.load_markets(keys)
    bad = [m for m, c in closes.items() if m in R7.MARKETS and not R7.eligible(c)]
    if bad:
        raise RuntimeError(f"数据不够：{bad}")
    bulls = {m: R7.bull(c) for m, c in closes.items()}
    dangers = {m: danger(closes[m], bulls[m]) for m in keys}
    spans = {m: P2.spans_of(closes[m]) for m in keys}
    n_min = min(len(R7.window_days(closes[m])) for m in R7.MARKETS)
    return {"keys": keys, "closes": closes, "bulls": bulls, "dangers": dangers, "spans": spans,
            "ks": R7.shift_ks(n_min), "ks_us": R7.shift_ks(len(R7.window_days(closes["US"])))}


def scale(I: dict) -> dict:
    out = {}
    for m in I["keys"]:
        idx = I["closes"][m].index
        inw = in_window(idx)
        b = I["bulls"][m].reindex(idx).fillna(False).to_numpy(bool) & inw
        d = I["dangers"][m].to_numpy(bool)
        rs = runs(d)
        out[m] = {"bull_days": int(b.sum()), "danger_days": int(d.sum()), "danger_pct_of_bull": round(float(d.sum() / max(b.sum(), 1) * 100), 1),
                  "runs": len(rs), "run_len_median": float(np.median([z - a + 1 for a, z in rs])) if rs else None}
    return out


# ───────────────────────── 运行 ─────────────────────────
_G: dict = {}


def one_rule(task: tuple[int, int, int]) -> dict:
    """一个合成规则：生成 18 个市场的信号 → 横展开 C1〜C3 + 美国单一序列。"""
    iq, lag, s = task
    I = _G["I"]
    q = QS[iq]
    mu = month_draws(iq, lag, s)
    ratios = {}
    for j, m in enumerate(I["keys"]):
        rng = np.random.default_rng([SEED, iq, lag, s, 1 + j])
        sig = synth(I["closes"][m], I["bulls"][m], I["dangers"][m], q, lag, mu, rng)
        ratios[m] = ratio_of(fill_off(sig, I["bulls"][m], [z - a + 1 for a, z in runs(I["dangers"][m])], rng))
    keys = list(R7.MARKETS)
    sub = lambda kk: ({m: I["closes"][m] for m in kk}, {m: ratios[m] for m in kk}, {m: I["bulls"][m] for m in kk})   # noqa: E731
    cl, ra, bu = sub(keys)
    real = P2.deltas_num(cl, ra, bu, None, {m: I["spans"][m] for m in keys})
    plac = []
    for k in I["ks"]:
        r = P2.deltas_num(cl, ra, bu, k, {m: I["spans"][m][:1] for m in keys})
        full = [v[0] for v in r.values()]
        plac.append(None if any(x is None for x in full) else float(np.mean(full)))
    jd = R7.judge(real, plac)
    cu, rau, buu = sub(["US"])
    us_real = P2.deltas_num(cu, rau, buu, None, {"US": I["spans"]["US"][:1]})["US"][0]
    us_plac = [P2.deltas_num(cu, rau, buu, k, {"US": I["spans"]["US"][:1]})["US"][0] for k in I["ks_us"]]
    sj = single_judge(us_real, us_plac)
    on = {m: I["bulls"][m].reindex(I["closes"][m].index).fillna(False).to_numpy(bool) & in_window(I["closes"][m].index) for m in I["keys"]}
    sig_on = {m: float((ratios[m].to_numpy() < 1.0 - 1e-12)[on[m]].mean() * 100) for m in I["keys"]}
    return {"q": q, "lag": lag, "seed": s, "cross_ok": bool(jd.get("ok")), "C1": jd.get("C1"), "C2": jd.get("C2"), "C3": jd.get("C3"),
            "pooled": jd.get("pooled"), "plac_median": (jd.get("q") or {}).get(50), "plac_max": jd.get("max"), "positive": jd.get("positive"),
            "excess": None if jd.get("pooled") is None else round(jd["pooled"] - (jd.get("q") or {}).get(50, 0.0), 6),
            "single_ok": sj["ok"], "us_real": sj.get("real"), "us_max": sj.get("max"), "us_pct": sj.get("pct"),
            "sig_bull_pct_mean": round(float(np.mean([sig_on[m] for m in R7.MARKETS])), 1), "sig_bull_pct_us": round(sig_on["US"], 1)}


def real_excess(out_dir: Path) -> dict:
    """校准：第七个循环三个真实规则的「合并 Δ − 400 次随机中位」（读已存的结果，不重跑）。"""
    res = {}
    for k, fn in REAL.items():
        d = json.loads((out_dir / fn).read_text(encoding="utf-8"))
        jd = d.get("stage2") or (d.get("cross") or {}).get("judge") or {}
        res[k] = {"pooled": jd.get("pooled"), "median": (jd.get("q") or {}).get("50"),
                  "excess": None if jd.get("pooled") is None else round(jd["pooled"] - (jd.get("q") or {}).get("50", 0.0), 6)}
    return res


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/power_study.py", "scripts/loop7_r02_voltarget.py",
                                 "scripts/research_loop7.py", "qbreak/bullbear.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def tasks() -> list[tuple[int, int, int]]:
    return [(iq, lag, s) for iq in range(len(QS)) for lag in LAGS for s in range(SEEDS)]


def run(workers: int) -> int:
    import multiprocessing as mp
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    I = inputs()
    _G["I"] = I
    tk = tasks()
    rows = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, r in enumerate(pool.imap(one_rule, tk)):
                rows.append(r)
                if (i + 1) % 10 == 0:
                    print(f"合成规则 {i + 1} / {len(tk)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i, t in enumerate(tk):
            rows.append(one_rule(t))
            if (i + 1) % 10 == 0:
                print(f"合成规则 {i + 1} / {len(tk)}（{time.time() - t0:.0f}s）", flush=True)
    cells = []
    for q in QS:
        for lag in LAGS:
            g = [r for r in rows if r["q"] == q and r["lag"] == lag]
            cells.append({"q": q, "lag": lag, "n": len(g), "cross_rate": round(float(np.mean([r["cross_ok"] for r in g])), 3),
                          "single_rate": round(float(np.mean([r["single_ok"] for r in g])), 3),
                          "C1_rate": round(float(np.mean([bool(r["C1"]) for r in g])), 3), "C2_rate": round(float(np.mean([bool(r["C2"]) for r in g])), 3),
                          "excess_median": round(float(np.median([r["excess"] for r in g if r["excess"] is not None])), 6),
                          "us_pct_median": round(float(np.median([r["us_pct"] for r in g if r["us_pct"] is not None])), 1),
                          "positive_median": float(np.median([r["positive"] for r in g if r["positive"] is not None])),
                          "sig_bull_pct_median": round(float(np.median([r["sig_bull_pct_mean"] for r in g])), 1)})
    key = next(c for c in cells if c["q"] == 0.5 and c["lag"] == 5)
    min_q = lambda rk: min([c["q"] for c in cells if c["lag"] == 5 and c["q"] > 0 and c[rk] >= POWER_OK - 1e-12], default=None)   # noqa: E731
    null = [r for r in rows if r["q"] == 0.0]
    res = {"study": OUT, "code": code, "dirty": dirty, "window": list(WINDOW), "design": {"QS": QS, "LAGS": LAGS, "SEEDS": SEEDS, "H": H, "TAIL": TAIL,
           "FA_RATIO": FA_RATIO, "KEEP": KEEP}, "scale": scale(I), "rows": rows, "cells": cells,
           "verdict": {"cross": power_label(key["cross_rate"]), "single": power_label(key["single_rate"]),
                       "null_cross_rate": round(float(np.mean([r["cross_ok"] for r in null])), 3),
                       "null_single_rate": round(float(np.mean([r["single_ok"] for r in null])), 3),
                       "min_q_cross": min_q("cross_rate"), "min_q_single": min_q("single_rate")},
           "real": real_excess(paths.out_dir()), "seconds": round(time.time() - t0)}
    write(res)
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    v = res["verdict"]
    L = [f"# 检验力测算：以前的两种第二关能多大把握认出「真的有用」的减仓规则（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/power_study.py 开头）", "",
         f"**横展开（17 个市场合并）：{v['cross']}；单一序列（S&P500 一个市场）：{v['single']}**（看 q = 0.5、L = 5 那一格：认出一半的危险段、晚 5 天、噪音与认对的差不多一样多）。"
         f"没有技能的规则（q = 0）偶然过关：横展开 {v['null_cross_rate'] * 100:.1f}%、单一序列 {v['null_single_rate'] * 100:.1f}%。"
         f"有一半把握认出的最低技能（L = 5）：横展开 {'q = ' + format(v['min_q_cross'], '.2f') if v['min_q_cross'] is not None else '没有'}、"
         f"单一序列 {'q = ' + format(v['min_q_single'], '.2f') if v['min_q_single'] is not None else '没有'}。", "",
         "| 技能 q（认出的比例） | 晚几天认出 L | 规则数 | 牛市日子里减仓的比例（17 个市场平均的中位） | 横展开过的比例 | 其中 C1 / C2 过的比例 | 单一序列过的比例 | 合并 Δ − 随机中位（中位） | 美国在随机里的百分位（中位） | 为正的市场（中位） |",
         "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for c in res["cells"]:
        L.append(f"| {c['q']:.2f} | {c['lag']} 天 | {c['n']} | {c['sig_bull_pct_median']:.1f}% | {c['cross_rate'] * 100:.0f}% | {c['C1_rate'] * 100:.0f}% / {c['C2_rate'] * 100:.0f}% | "
                 f"{c['single_rate'] * 100:.0f}% | {c['excess_median']:+.4f} | {c['us_pct_median']:.1f} | {c['positive_median']:.0f} / 17 |")
    L += ["", "校准（只描述）：第七个循环三个真实规则的「合并 Δ − 400 次随机中位」：" + "、".join(
        f"{k} {x['excess']:+.4f}" for k, x in res["real"].items() if x.get("excess") is not None) + "（与上表同一个量比）。", "",
          "危险日（只数日子）：" + "、".join(f"{m} {x['danger_days']} 天 / {x['runs']} 段" for m, x in res["scale"].items()), "",
          f"合成规则 = 只用来量检验的「半个先知」，不是交易规则；动作 = 牛 ∧ 信号 → 指数 2/3；检验与第七个循环 / 以前第二关同一组函数与平移量。用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    I = inputs()
    print(json.dumps(scale(I), ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检验力测算（合成的「半个先知」减仓规则 → 两种第二关的通过率）")
    ap.add_argument("--scale", action="store_true", help="只数危险日 / 段（不算任何规则的收益）")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    return scale_only() if a.scale else run(a.workers)


if __name__ == "__main__":
    raise SystemExit(main())
