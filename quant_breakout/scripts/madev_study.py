"""madev_study.py — 你图里的卖点：「脱离周 / 月线，下一周 / 月还严重脱离对应的均线 → 卖」加到现行卖点上，胜率与收益率怎么样
（2026-09-28 事先登记：规则先提交再运行一次，结果出来不改规则）。

用户（2026-09-28，附图：一根大阳线把价格拉到均线上方很远，下一根小 K 线（长上影）仍停在高处，两条均线远在下方）：
  「把现行的卖点加上这个图中脱离周/月线 在下周/月严重脱离对应线的话就卖 进行研究 判断收益率和胜率怎么样」。
以前做过的（不重复，照实写）：sell_explore（1805abc）A5「收盘比 25 日均线高 10% 以上也卖」（日线乖离）只在 27% 的交易里出现、卖对率两个年代相反；
  mtf_study（fe49536）周 / 月线的见顶事件（周线 MACD 死叉、周线高潮、月线 RSI ≥ 80、跌破上周最低、连涨 5 周后第一根阴线、周线收盘 < 10 周线）
  几乎不改变结果；过热回落类（RSI 70 回落、KD 80 以上死叉）提高胜率但把赢家卖早（sell_confirm c9149d1 在没看过的数据上确认）。
  这次是新的：周 / 月线「离均线的距离」（乖离率）连续两根都很大才卖 —— 以前没有做过。

一 规则（= 现行卖点 + 这一条；买点与其他卖法完全不变）
  周线 / 月线：qbreak/mtf.py 的 bars（ISO 周 / 日历月；这一周 / 这个月最后一个交易日收盘时完成；只用已经完成的 K 线）。
  均线 = 最近 n 根已完成 K 线收盘的简单平均（含这一根；不够 n 根 → 不判断）；乖离 = 收盘 ÷ 均线 − 1。「严重脱离」= 乖离 ≥ θ。
  θ 按下面「登记前的诊断」（只看价格分布，没看任何交易）取 E / J 两段日経225 全部已完成 K 线的 95 / 99 分位，取整到 5%。
  两根（你的规则）：这一根与这只票上一根已完成 K 线的乖离都 ≥ θ（上一根 = 脱离、这一根 = 还严重脱离）→ 这一根完成那天收盘成立 → 次日开盘卖；
  一根（对照：不等下一根）：这一根 ≥ θ 就卖。
  实现：成立的那天并进指标表的 dead_cross 列（回测引擎本来就是「收盘成立 → 次日开盘卖」）；止损 −7%、跟踪 12%、止盈 +25%、放量阴线、
  最长 60 个交易日、MACD 死叉都照旧，持有中哪一个先成立就按哪一个卖。成立那天这只票没有 K 线 → 之后第一根（qbreak/mtf.event_on）。
  变体（8 个，事先写定；D1 / D5 = 你的规则的周线 / 月线版）：
    D1 13 周线、θ 15%、两根      D2 13 周线、θ 25%、两根
    D3 26 周线、θ 25%、两根      D4 26 周线、θ 40%、两根
    D5 12 个月线、θ 35%、两根    D6 12 个月线、θ 55%、两根
    D7 13 周线、θ 15%、一根      D8 12 个月线、θ 35%、一根
登记前的诊断（2026-09-28；只看价格：E = 2006-10〜2016-09 日経225 208 只、J = 2017-01〜2026-09 J-Quants 日経225 213 只的全部已完成 K 线
  收盘离均线的分布；没有算任何交易或收益）：
  13 周线 21.0 万根：P90 +11.4%、P95 +15.4%、P99 +25.1%（E / J 各自 P95 15.5 / 15.1%、P99 24.9 / 25.6%）
  26 周线 20.8 万根：P90 +17.6%、P95 +23.8%、P99 +39.4%
  12 个月线 4.7 万根：P90 +24.8%、P95 +33.5%、P99 +56.4%
  （24 个月线 P95 +51.8%、P99 +91.1%：比持有期长太多，不用）
二 数据（四段；这一条规则在哪段都没有用过；四段以前都做过别的研究）
  Z = 2001-01〜2006-09（yfinance 今天的日経225，去掉成交量 0 的假行；scripts/leap_confirm.py）；
  E = 2006-10〜2016-09（yfinance 今天的日経225）；J = 2017-01〜2026-09（J-Quants 今天的日経225，真实一手）；
  W = 另一批股票（扩大池 714 只：TOPIX 1000 里日経225 以外）2006-10〜2016-09（scripts/sell_confirm.wide_context）。
  J 的行情从 2016-09 开始 → 26 周线 2017-03、12 个月线 2017-08 以前算不出（那之前的交易这一条不会成立，照实报告）。
三 做法
  A 逐信号配对（与 sell_confirm、X6 前向记录同一做法）：每个 W2 保留的突破（现行参数去掉 W2 的突破 ∧ 周线量比 ≥ 1.0 或缺值），只留这一个
    买入信号，回测引擎跑「现行」与每个变体（两边买入相同，只差 dead_cross 列）；扣 ¥25 万一笔的来回手续费；两边都已平仓的才算。
    胜率 = 净收益 > 0 的比例；每笔 = 平均净收益（%）；「提前卖」= 变体的卖出日早于现行的对数。
  B 组合（S0C2 + W2，与 sell_explore 同一框架；Z / E / J）：年化、最大回撤、Calmar、个股胜率、每笔、笔数。
    核对：「死叉 ∨ 全 False」必须与现行完全相同，否则停止。
四 判定（每个变体各自；运行前写定）
  合并 = Z + E + J + W 的全部配对；95% 区间 = 按信号所在的日历月聚类的自助法 2,000 次（种子 20260928；E 与 W 同月合为一簇，偏保守）。
  0「几乎不触发」：合并的提前卖 < 20 对或 < 合并配对的 2%（对胜率、收益率没有可测的影响）；
  1「胜率与收益率都提高」：合并每笔差 95% 下限 > 0、合并胜率差 ≥ 0，且 Z / E / J / W 每段的胜率差与每笔差都 ≥ 0（点估计），
    且组合 Z / E / J 各自 Calmar 不低于现行 0.01 以上、最大回撤不比现行深 2 pp 以上 → 结论上限：提议加进模拟盘（要你在对话里确认、记 sim_changes）；
  2「提高胜率、每笔更差（取舍）」：合并胜率差 95% 下限 > 0 且合并每笔差 < 0；
  3「提高收益率、胜率更低」：合并每笔差 95% 下限 > 0 且合并胜率差 < 0；
  4「每笔显著更差」：合并每笔差 95% 上限 < 0；
  5 其余 →「没有可测的差别」（Z / E / J / W 点估计都 ≥ 0 的另注「方向一致但不显著」）。按 0→1→2→3→4→5 的顺序取第一个。
  8 个变体一起看会有偶然的「成立」：1 要求四段每段同方向 + 组合守门，就是为了挡这个；不做别的挑选，不看结果后改 θ。
五 另报（只描述）：各段现行 / 变体的胜率、平均赚 / 亏、每笔、持有中位；提前卖的那些对：现行 vs 变体的每笔、卖出后 10 个交易日收盘比卖价低的比例
  （卖对率）、卖出后 20 个交易日的平均涨跌；组合的年化 / 回撤 / Calmar。
六 局限：只用收盘判断（没用盘中）；今天的日経225 与扩大池有幸存者偏差；四段以前做过很多别的检验；调整后价（yfinance 含分红调整、J-Quants 只调拆股）；
  税前。模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/madev_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import mtf                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

VARIANTS: dict[str, dict] = {
    "D1": {"freq": "W", "n": 13, "theta": 15.0, "k": 2, "zh": "13 周线、连续两根收盘都比均线高 15% 以上（你的规则·周线）"},
    "D2": {"freq": "W", "n": 13, "theta": 25.0, "k": 2, "zh": "13 周线、连续两根高 25% 以上"},
    "D3": {"freq": "W", "n": 26, "theta": 25.0, "k": 2, "zh": "26 周线、连续两根高 25% 以上"},
    "D4": {"freq": "W", "n": 26, "theta": 40.0, "k": 2, "zh": "26 周线、连续两根高 40% 以上"},
    "D5": {"freq": "M", "n": 12, "theta": 35.0, "k": 2, "zh": "12 个月线、连续两根收盘都比均线高 35% 以上（你的规则·月线）"},
    "D6": {"freq": "M", "n": 12, "theta": 55.0, "k": 2, "zh": "12 个月线、连续两根高 55% 以上"},
    "D7": {"freq": "W", "n": 13, "theta": 15.0, "k": 1, "zh": "13 周线、一根高 15% 以上就卖（不等下一周）"},
    "D8": {"freq": "M", "n": 12, "theta": 35.0, "k": 1, "zh": "12 个月线、一根高 35% 以上就卖（不等下个月）"},
}
SAMPLES = ("Z", "E", "J", "W")
PORT_SAMPLES = ("Z", "E", "J")
MIN_CHANGED, MIN_CHANGED_FRAC = 20, 0.02
CAL_TOL, DD_TOL = 0.01, 2.0
FWD_A, FWD_B = 10, 20
BOOT_N, SEED = 2000, 20260928
LABELS = {0: "几乎不触发", 1: "胜率与收益率都提高", 2: "提高胜率、每笔更差（取舍）", 3: "提高收益率、胜率更低", 4: "每笔显著更差",
          5: "没有可测的差别"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 规则（纯函数，有测试）─────────────────────────
def dev_of(b: pd.DataFrame, n: int) -> pd.Series:
    """已完成的周 / 月线（qbreak/mtf.bars）→ 乖离（收盘 ÷ 最近 n 根收盘平均 − 1；不够 n 根 → NaN），index = 完成日。"""
    c = b["Close"].astype(float)
    return c / c.rolling(n, min_periods=n).mean() - 1


def dev_bars(raw: pd.DataFrame, days: pd.DatetimeIndex, freq: str, n: int) -> pd.Series:
    """一只票的日线 → 已完成周 / 月线的乖离。"""
    return dev_of(mtf.bars(raw, days, freq), n)


def flag_of(dev: pd.Series, idx: pd.DatetimeIndex, v: dict) -> pd.Series:
    """乖离 → 变体 v 的卖出判定（日线日期上的布尔）：完成日那天成立（k = 2：这一根与这只票上一根已完成 K 线都 ≥ θ）；
    这只票那天没有 K 线 → 之后第一根。"""
    hit = (dev >= v["theta"] / 100).to_numpy(bool)                         # NaN → False
    if v["k"] == 2:
        hit = hit & np.r_[False, hit[:-1]]
    return mtf.event_on(pd.Series(hit.astype(float), index=dev.index), idx)


def dev_flag(raw: pd.DataFrame, days: pd.DatetimeIndex, v: dict) -> pd.Series:
    """一只票的日线 → 变体 v 的卖出判定（日线日期上的布尔）。"""
    return flag_of(dev_bars(raw, days, v["freq"], v["n"]), raw.index, v)


def raw_of(P: dict, days: pd.DatetimeIndex, j: int) -> pd.DataFrame:
    """宽表的第 j 只票 → 日线（开盘与收盘都有值的日子；与 leap_confirm.w2_keep、candle_study.frames_from 同一口径）。"""
    ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
    return pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                         "Volume": P["V"][ok, j]}, index=days[ok])


def flags_for(ctx: dict, fr: dict[str, pd.DataFrame], keys=None) -> dict[str, dict[str, np.ndarray]]:
    """{变体: {票: 与 fr[票] 同一日期的布尔数组}}。"""
    keys = list(keys or VARIANTS)
    col = {t: j for j, t in enumerate(ctx["names"])}
    out: dict[str, dict[str, np.ndarray]] = {k: {} for k in keys}
    for t, df in fr.items():
        raw = raw_of(ctx["P"], ctx["days"], col[t])
        bars = {fq: mtf.bars(raw, ctx["days"], fq) for fq in {VARIANTS[k]["freq"] for k in keys}}     # 每只票每种周期只聚合一次
        for k in keys:
            v = VARIANTS[k]
            out[k][t] = flag_of(dev_of(bars[v["freq"]], v["n"]), raw.index, v).reindex(df.index, fill_value=False).to_numpy(bool)
    return out


def with_rule(fr: dict[str, pd.DataFrame], flags: dict[str, np.ndarray] | None) -> dict[str, pd.DataFrame]:
    """dead_cross ∨ 规则（flags = None → 原样）。"""
    if flags is None:
        return fr
    return {t: df.assign(dead_cross=df["dead_cross"].to_numpy(bool) | np.asarray(flags.get(t, np.zeros(len(df), bool)), bool))
            for t, df in fr.items()}


# ───────────────────────── 判定（纯函数，有测试）─────────────────────────
def port_ok(port: dict | None) -> bool:
    """port：{段: {"cur": {calmar, dd}, "var": {calmar, dd}}}；Z / E / J 每段 Calmar 不低 0.01 以上、回撤不深 2 pp 以上。"""
    if not port:
        return False
    for tag in PORT_SAMPLES:
        c, v = (port.get(tag) or {}).get("cur") or {}, (port.get(tag) or {}).get("var") or {}
        if None in (c.get("calmar"), v.get("calmar"), c.get("dd"), v.get("dd")):
            return False
        if v["calmar"] < c["calmar"] - CAL_TOL or v["dd"] < c["dd"] - DD_TOL:
            return False
    return True


def verdict(pool: dict, per: dict[str, dict], port: dict | None) -> dict:
    """pool：合并的 {n, changed, dwin, dmean, dwin_lo, dwin_hi, dmean_lo, dmean_hi}；per：{段: {dwin, dmean}}。"""
    n, ch = pool.get("n", 0), pool.get("changed", 0)
    same = all((per.get(t) or {}).get("dwin") is not None and per[t]["dwin"] >= 0 and per[t]["dmean"] >= 0 for t in SAMPLES)
    pok = port_ok(port)
    if ch < MIN_CHANGED or (n and ch < MIN_CHANGED_FRAC * n):
        code = 0
    elif pool.get("dmean_lo", -1) > 0 and pool["dwin"] >= 0 and same and pok:
        code = 1
    elif pool.get("dwin_lo", -1) > 0 and pool["dmean"] < 0:
        code = 2
    elif pool.get("dmean_lo", -1) > 0 and pool["dwin"] < 0:
        code = 3
    elif pool.get("dmean_hi", 1) < 0:
        code = 4
    else:
        code = 5
    lab = LABELS[code] + ("（方向一致但不显著）" if code == 5 and same else "")
    return {"code": code, "label": lab, "same_direction": same, "port_ok": pok}


# ───────────────────────── 逐信号配对 ─────────────────────────
def paired(fr: dict[str, pd.DataFrame], sigs: pd.DataFrame, flags: dict[str, dict[str, np.ndarray]], p, bt, rt: float,
           end_bars: int = 90) -> pd.DataFrame:
    """每个信号一行：现行的 net / hold / 卖出日；每个变体的 net_k / hold_k / exit_k / early_k（卖出日早于现行）/ fwd10_k / fwd20_k（提前卖的那些：
    卖出后 10 / 20 个交易日收盘 ÷ 卖价 − 1，%）。任何一边没卖出 → 该变体为空。"""
    import sell_confirm as SCF
    rows = []
    for r in sigs.to_dict("records"):
        t, d = r["ticker"], pd.Timestamp(r["date"])
        df = fr.get(t)
        if df is None or d not in df.index:
            continue
        pos = int(df.index.get_loc(d))
        end = df.index[min(len(df) - 1, pos + end_bars)]
        f = df.assign(entry=np.asarray(df.index == d))
        a = SCF.one_trade(t, f, d, p, bt, end)
        if a is None or a["reason"] == "end":
            continue
        row = {**r, "entry_date": a["entry_date"], "exit_date": a["exit_date"], "reason": a["reason"], "hold": int(a["hold_days"]),
               "net": float(a["ret_pct"]) - rt}
        close = df["Close"].to_numpy(float)
        for k, fl in flags.items():
            g = fl.get(t)
            if g is None or not g[pos:pos + end_bars + 1].any():
                b = a                                                          # 这个信号之后 end_bars 根里这一条不成立 → 与现行相同
            else:
                b = SCF.one_trade(t, f.assign(dead_cross=df["dead_cross"].to_numpy(bool) | g), d, p, bt, end)
            ok = b is not None and b["reason"] != "end" and b["entry_date"] == a["entry_date"]
            row[f"net_{k}"] = float(b["ret_pct"]) - rt if ok else np.nan
            row[f"hold_{k}"] = int(b["hold_days"]) if ok else np.nan
            early = bool(ok and pd.Timestamp(b["exit_date"]) < pd.Timestamp(a["exit_date"]))
            row[f"early_{k}"] = early
            for m, col in ((FWD_A, "fwd10"), (FWD_B, "fwd20")):
                v = np.nan
                if early:
                    q = int(df.index.get_loc(pd.Timestamp(b["exit_date"])))
                    if q + m < len(close) and np.isfinite(close[q + m]):
                        v = (close[q + m] / float(b["exit_px"]) - 1) * 100
                row[f"{col}_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def _stats(x: np.ndarray) -> dict:
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0}
    w, lo = x[x > 0], x[x <= 0]
    return {"n": int(len(x)), "win": float((x > 0).mean() * 100), "mean": float(x.mean()),
            "avg_win": float(w.mean()) if len(w) else None, "avg_loss": float(lo.mean()) if len(lo) else None}


def compare(P: pd.DataFrame, key: str, ci: bool = True) -> dict:
    """变体 vs 现行（两边都有结果的配对）；ci：按信号所在日历月聚类的 95% 区间。"""
    import sell_confirm as SCF
    if not len(P) or f"net_{key}" not in P.columns:
        return {"n": 0, "changed": 0}
    m = np.isfinite(P[f"net_{key}"].to_numpy(float))
    if not m.any():
        return {"n": 0, "changed": 0}
    c, v = P.loc[m, "net"].to_numpy(float), P.loc[m, f"net_{key}"].to_numpy(float)
    sc, sv = _stats(c), _stats(v)
    e = P.loc[m, f"early_{key}"].to_numpy(bool)
    out = {"n": int(m.sum()), "changed": int(e.sum()), "win_cur": sc["win"], "win": sv["win"], "dwin": sv["win"] - sc["win"],
           "mean_cur": sc["mean"], "mean": sv["mean"], "dmean": sv["mean"] - sc["mean"], "avg_win_cur": sc["avg_win"], "avg_win": sv["avg_win"],
           "avg_loss_cur": sc["avg_loss"], "avg_loss": sv["avg_loss"], "hold_cur": float(np.median(P.loc[m, "hold"])),
           "hold": float(np.nanmedian(P.loc[m, f"hold_{key}"]))}
    if e.any():
        out["early_cur_mean"] = float(c[e].mean())
        out["early_var_mean"] = float(v[e].mean())
        f10 = P.loc[m, f"fwd10_{key}"].to_numpy(float)[e]
        f20 = P.loc[m, f"fwd20_{key}"].to_numpy(float)[e]
        out["right10"] = float((f10[np.isfinite(f10)] < 0).mean() * 100) if np.isfinite(f10).any() else None
        out["fwd20"] = float(np.nanmean(f20)) if np.isfinite(f20).any() else None
    if ci and m.sum() >= 10:
        out.update(SCF.boot_pair(c, v, pd.to_datetime(P.loc[m, "date"]).dt.to_period("M").to_numpy(), n=BOOT_N, seed=SEED))
    return out


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def main() -> int:
    import bsh_common as BC
    import leap_confirm as LF
    import sell_confirm as SCF
    import sell_explore as SX
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    keys = list(VARIANTS)
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 周 / 月线严重脱离均线就卖：加到现行卖点上的胜率与收益率（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/madev_study.py 开头（运行前写定）。逐信号配对（只留一个买入信号、只差这一条卖法）+ 组合（S0C2 + W2）。")
    sets: dict[str, pd.DataFrame] = {}
    port: dict[str, dict] = {}
    prof: dict[str, dict] = {}
    for tag in SAMPLES:
        t1 = time.time()
        if tag == "W":
            ctx, fa = SCF.wide_context(p0)
            a, b = SCF.W_WIN
        else:
            ctx = LF.context(tag)
            fa = LF.frames(ctx, p0)
            a, b = ctx["start"], ctx["end"] or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        keep = LF.w2_keep(ctx, fa)
        fl = flags_for(ctx, fa, keys)
        S = SCF.signals_of(fa, keep, a, b)
        P = paired(fa, S, fl, p0, bt, rt)
        P["set"] = tag
        sets[tag] = P
        if tag in PORT_SAMPLES:
            run_fn = LF.runner(ctx, fa)
            fw = LF.with_mask(fa, keep)
            r0 = LF.run(ctx, run_fn, fw, p)
            tr0 = BC.last_trades(a, b)
            base = SX.summ(r0, tag)
            rn = LF.run(ctx, run_fn, with_rule(fw, {t: np.zeros(len(df), bool) for t, df in fw.items()}), p)
            trn = BC.last_trades(a, b)
            same = SX.summ(rn, tag) == base and len(trn) == len(tr0) and np.allclose(trn["net"].to_numpy(float), tr0["net"].to_numpy(float))
            say(f"- {tag} 核对（死叉 ∨ 全 False）：{'与现行完全相同' if same else '★ 不同 —— 停止'}")
            if not same:
                raise SystemExit(f"{tag} 核对不一致")
            port[tag] = {"现行": base}
            prof[tag] = {"现行": BC.trade_profile(tr0)}
            for k in keys:
                port[tag][k] = SX.summ(LF.run(ctx, run_fn, with_rule(fw, fl[k]), p), tag)
                prof[tag][k] = BC.trade_profile(BC.last_trades(a, b))
        say(f"- {tag}（{a}〜{b}）：W2 保留的信号 {len(S)} 个 → 两边都已平仓的 {len(P)} 对；{round(time.time() - t1)} s")
    ALL = pd.concat([sets[t] for t in SAMPLES], ignore_index=True)
    cmp = {tag: {k: compare(P, k) for k in keys} for tag, P in sets.items()}
    cmp["ALL"] = {k: compare(ALL, k) for k in keys}
    V = {}
    for k in keys:
        pk = {tag: {"cur": port[tag]["现行"], "var": port[tag][k]} for tag in PORT_SAMPLES}
        V[k] = verdict(cmp["ALL"][k], {t: cmp[t][k] for t in SAMPLES}, pk)

    say("\n## 一、判定（合并 = Z + E + J + W 的全部配对；运行前写定）")
    for k in keys:
        x = cmp["ALL"][k]
        say(f"- **{k} {VARIANTS[k]['zh']}**：{x['n']} 对，提前卖 {x['changed']} 对（{x['changed'] / max(1, x['n']) * 100:.1f}%）；"
            f"胜率 {x['win_cur']:.1f}% → {x['win']:.1f}%（差 {x['dwin']:+.1f} pp，95% 区间 {fmt(x.get('dwin_lo'), '{:+.1f}')}〜{fmt(x.get('dwin_hi'), '{:+.1f}')}）；"
            f"每笔 {x['mean_cur']:+.2f}% → {x['mean']:+.2f}%（差 {x['dmean']:+.2f} pp，{fmt(x.get('dmean_lo'))}〜{fmt(x.get('dmean_hi'))}）"
            f" → **{V[k]['label']}**")
    say("\n## 二、各段（胜率差 pp / 每笔差 pp；提前卖的对数 / 全部对数）")
    say("| 变体 | Z | E | J | W |")
    say("|---|---|---|---|---|")
    for k in keys:
        cells = []
        for tag in SAMPLES:
            x = cmp[tag][k]
            cells.append("—" if not x.get("n") else f"{x['dwin']:+.1f} / {x['dmean']:+.2f}（{x['changed']} / {x['n']}）")
        say(f"| {k} | " + " | ".join(cells) + " |")
    say("\n## 三、各段现行 vs 变体（胜率、平均赚 / 亏、每笔、持有中位）")
    say("| 变体 | 段 | 胜率 现行 → 变体 | 平均赚 现行 → 变体 | 平均亏 现行 → 变体 | 每笔 现行 → 变体 | 持有中位 |")
    say("|---|---|---|---|---|---|---|")
    for k in keys:
        for tag in SAMPLES:
            x = cmp[tag][k]
            if not x.get("n"):
                continue
            say(f"| {k} | {tag} | {x['win_cur']:.1f}% → {x['win']:.1f}% | {fmt(x['avg_win_cur'])}% → {fmt(x['avg_win'])}% | "
                f"{fmt(x['avg_loss_cur'])}% → {fmt(x['avg_loss'])}% | {x['mean_cur']:+.2f}% → {x['mean']:+.2f}% | {x['hold_cur']:.0f} → {x['hold']:.0f} 天 |")
    say("\n## 四、提前卖的那些对（合并；只描述）：现行的每笔 vs 变体的每笔、卖出后 10 个交易日收盘比卖价低的比例（卖对率）、卖出后 20 个交易日平均涨跌")
    say("| 变体 | 提前卖 | 这些对 现行每笔 | 变体每笔 | 卖对率（10 日） | 卖出后 20 日平均 |")
    say("|---|---|---|---|---|---|")
    for k in keys:
        x = cmp["ALL"][k]
        say(f"| {k} | {x['changed']} 对 | {fmt(x.get('early_cur_mean'))}% | {fmt(x.get('early_var_mean'))}% | {fmt(x.get('right10'), '{:.1f}')}% | "
            f"{fmt(x.get('fwd20'))}% |")
    say("\n## 五、组合（S0C2 + W2；年化 / 最大回撤 / Calmar / 个股胜率 / 每笔 / 笔数）")
    say("| 变体 | Z | E | J |")
    say("|---|---|---|---|")
    for k in ["现行", *keys]:
        cells = []
        for tag in PORT_SAMPLES:
            s = port[tag][k]
            cells.append(f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')} / "
                         f"{fmt(s.get('win'), '{:.1f}')}% / {fmt(s.get('mean'))}% / {s.get('n')}")
        say(f"| {k} | " + " | ".join(cells) + " |")
    say("\n组合守门（Z / E / J 每段 Calmar 不低 0.01 以上、回撤不深 2 pp 以上）：" + "、".join(f"{k} {'过' if V[k]['port_ok'] else '不过'}" for k in keys))
    say("\n变体说明：" + "；".join(f"{k} {v['zh']}" for k, v in VARIANTS.items()))
    out = {"code": code, "compare": cmp, "verdict": V, "portfolio": port, "profile": prof,
           "counts": {t: int(len(P)) for t, P in sets.items()}, "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {out['elapsed_s']} s）。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / "madev_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
