"""threat_pressure_global.py — 「威胁高 + 压力已释放」= 平均(A0, 100 − 压力) 是否真的比威胁指数 A0 好：21 个外国市场的确认检验
（2026-09-29 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-29）：「确认『威胁高 + 压力已释放』是否真的比 A0 好，在全球市场进行确认」。
来由：pressure_threat_posthoc（b8ba3a8，事后描述）在美国 / 日本的月末上看到 平均(A0, 100 − 综合压力) 的「60 天内跌 ≥ 10%」AUC
  美国 0.757 vs A0 0.669（差的 95% 区间 −0.004〜+0.162，刚好含 0）、日本 0.582 vs 0.557（−0.041〜+0.081）；
  组合的方向（压力取反）是看过 pressure_study（38b648e）之后才定的 → 美国 / 日本不能再当确认。
  这里用 threat_intl_study（H2）同一批 21 个外国市场确认：H2 用它们检验过威胁指数的其他配比，但从没在它们上面看过压力、也没看过这个组合。

一 数据（指数、缓存、去错价、交易日都与 threat_intl_study 相同；时点：欧洲 / 亚太 = 前一个美国收盘，美洲 = 同一天）
  威胁指数 A0（每天）：TH.raw_features 的 8 个因素（VIX、VIX 20 日变化、信用利差走阔、曲线倒挂、利率急升、油价、失业，
    指数波动 rvol 用该市场自己的指数）→ 扩张百分位（≥ 750 个）→ 等权 0〜100（≥ 4 个有值）；与 H2 的 A0 相同。
  压力 P_g（每个月末；= pressure_study 的综合压力去掉宽度 —— 外国市场没有成分股宽度）：6 个分项各取「过去 120 个月末（含本月）里的分位」
    （≥ 60 个月），≥ 4 个有值才平均：
    涨幅 log(收盘 ÷ 500 日最低)、长期乖离 log(收盘 ÷ 250 日线)、平静 −60 日年化波动（都用该市场自己的指数）；
    利率上升（GS10 月均 12 个月变化）、曲线变平 −(GS10 − TB3MS)、信用利差收窄 −(BAA − GS10)（美国、上个月的月均 = 全球利率 / 信用环境）。
  组合：C_rel = (A0 + 100 − P_g) ÷ 2。
  样本：每个市场自己的月末（当月最后一个交易日；还没结束的月份不用），A0（月末当天）、P_g、结果都有值的全部月末。
  目标：月末之后 60 个交易日内最低收盘比月末跌 ≥ 10%（主）/ ≥ 15%（G6）。
二 判定（事先写定；主判定 = 发达 15 市场，欧洲 10 / 其他 5 两个地区等权）
  ΔAUC = AUC(C_rel) − AUC(A0)（同一市场、同一批月末）
  G1 地区均衡 ΔAUC ≥ +0.03
  G2 15 个里 ΔAUC > 0 的 ≥ 10 个，且两个地区的平均都 > 0
  G3 联合区块自助法：主判定市场的月份并集作日历，24 个月一块（环形）、2,000 次（种子 20260929），每次所有市场用同一组月份
     → 地区均衡 ΔAUC 的分布；单侧 p = 其中 ≤ 0 的比例 ≤ 0.05
  G4 两个子期间（〜2010 / 2011〜）的地区均衡 ΔAUC 都 > 0
  G5 新兴 6 市场的 ΔAUC 平均 > 0
  G6 ≥ 15% 的地区均衡 ΔAUC ≥ 0
  全过 = 全球确认成立 → 提议：把 C_rel 作为对照列加进威胁指数前向记录（threat_forward.csv；只记录，不改日报的 0〜100、不影响交易；
    用户确认才加）。任何一条不过 = 不成立 → 维持 A0，C_rel 只留在事后描述里。
三 另报（只描述，不参与判定）：100 − P_g 单独；C_relp（压力只用价格两项 = 涨幅 + 乖离）；美国 / 日本本国同一套（本国已看过，不算确认；
  日本的 A0 = 日报的 10 个因素）；现在各市场的 A0 / P_g / C_rel。
四 事前预期（写死）：G1 过约 35%；G2 过约 45%；G3 过约 25%；全部过约 15%。外国市场的 A0 接近随机（H2：AUC 0.44〜0.57），
  加上「价格已经跌过 / 波动已经变大」（100 − 压力）一部分市场会变好，但地区均衡 +0.03 与自助法同时过不容易。
五 局限：各市场的下跌高度同步（2008、2011、2015、2018、2020、2022）→ 联合自助法按月份一起抽；利率 / 信用用美国的（没有各国自己的）；
  月末样本每个市场约 250〜380 个、事件约 30〜100 个 → 单个市场 AUC 的误差约 ±0.05；P_g 的 6 个分项里 3 个是美国宏观。
输出：var/out/threat_pressure_global.md / .json（只有统计）。非投资建议。
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
from qbreak import paths                                                     # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak import weights as WT                                             # noqa: E402

import pressure_study as PS                                                  # noqa: E402
import threat_intl_study as TI                                               # noqa: E402

H, SPLIT = 60, pd.Timestamp("2011-01-01")
DROP10, DROP15 = -10.0, -15.0
PCOMP = ["runup", "ma", "calm", "rate", "curve", "credit"]
MIN_COMP = 4
MIN_ROWS = 60                                # 一个市场至少 60 个月末（两类都有）才算
G1_MEAN, G2_MIN_N, ALPHA = 0.03, 10, 0.05
BOOT_REPS, BOOT_BLOCK, BOOT_SEED = 2000, 24, 20260929
MARKETS, REGIONS = TI.MARKETS, TI.REGIONS
SCORES = {"A0": "威胁指数 A0", "C_rel": "平均(A0, 100 − 压力)", "P_inv": "100 − 压力", "C_relp": "平均(A0, 100 − 价格压力)"}


# ───────────────────────── 数据 ─────────────────────────
def a0_parts(close: pd.Series, d: dict, early: bool) -> tuple[pd.Series, pd.DataFrame]:
    """外国市场的 A0 与各因素百分位（与 threat_intl_study.build_market / prepare 相同：1990 年起的交易日、rvol 用该市场、
    早收盘市场用前一个美国收盘）。"""
    days = close.index[close.index >= TI.DATA0]
    r = d["raw"]
    keys = ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")
    m = {k: (TH.us_asof_for_jp(r[k], days) if early else r[k]) for k in keys}
    base = TH.raw_features(days, close.reindex(days), m["VIXCLS"], m["BAA10Y"], m["DGS10"], m["DGS3MO"], m["DCOILWTICO"], r["UNRATE"])
    return TH.threat_index(base, TH.US_COLS)


def a0_daily(close: pd.Series, d: dict, early: bool) -> pd.Series:
    return a0_parts(close, d, early)[0]


def macro_parts(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """美国利率 / 曲线 / 信用（pressure_study.us_raw 同一算法：上个月的月均）。"""
    from qbreak import factors as F
    y10, y3, baa = F.fred("GS10"), F.fred("TB3MS"), F.fred("BAA")
    y10l = PS.month_lag1(y10, dates)
    return pd.DataFrame({"rate": y10l - PS.month_lag1(y10.shift(12), dates), "curve": -(y10l - PS.month_lag1(y3, dates)),
                         "credit": -(PS.month_lag1(baa, dates) - y10l)}, index=dates)


def pressure_raw(close: pd.Series, dates: pd.DatetimeIndex, macro: pd.DataFrame) -> pd.DataFrame:
    pp = PS.price_parts(close).reindex(dates)
    return pd.concat([pp[["runup", "ma", "calm"]], macro.reindex(dates)], axis=1)[PCOMP]


def p_scores(raw: pd.DataFrame) -> pd.DataFrame:
    """月末原始分项 → 各分项分位、P_g（≥ 4 个）、P_price（涨幅 + 乖离两个都有）。"""
    pct = pd.DataFrame({k: PS.rolling_pct(raw[k]) for k in PCOMP}, index=raw.index)
    n = pct.notna().sum(axis=1)
    return pd.DataFrame({"P_g": pct.mean(axis=1).where(n >= MIN_COMP), "P_price": pct[["runup", "ma"]].mean(axis=1, skipna=False)},
                        index=raw.index)


def month_asof(daily: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    s = daily.dropna().sort_index()
    pos = s.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    return pd.Series(np.where(pos >= 0, s.to_numpy(float)[np.clip(pos, 0, None)], np.nan), index=dates)


def frame(close: pd.Series, a0: pd.Series, macro_fn=macro_parts) -> pd.DataFrame:
    """一个市场的月末表：A0、P_g、P_price、组合、之后 60 天内最低（%）、事件。只留 A0、P_g、结果都有值的月末。"""
    close = close.dropna()
    dates = PS.month_ends(close)[:-1]                                       # 最后一个月还没结束
    S = p_scores(pressure_raw(close, dates, macro_fn(dates)))
    T = PS.targets(close, dates, hs=(H,))
    X = pd.DataFrame({"A0": month_asof(a0, dates), "P_g": S["P_g"], "P_price": S["P_price"], "min": T[f"min{H}"]}, index=dates)
    X["C_rel"] = (X["A0"] + 100 - X["P_g"]) / 2
    X["P_inv"] = 100 - X["P_g"]
    X["C_relp"] = (X["A0"] + 100 - X["P_price"]) / 2
    X["ev10"] = (X["min"] <= DROP10).astype(float).where(X["min"].notna())
    X["ev15"] = (X["min"] <= DROP15).astype(float).where(X["min"].notna())
    return X[X[["A0", "P_g", "min"]].notna().all(axis=1)]


def now_reading(close: pd.Series, a0: pd.Series, macro_fn=macro_parts) -> dict:
    """最新一天：A0；P_g = 今天的原始分项在「过去 119 个月末 + 今天」里的分位（pressure_study.now_reading 同一算法）。"""
    close = close.dropna()
    dates = PS.month_ends(close)[:-1]
    raw = pressure_raw(close, dates, macro_fn(dates))
    last = pd.DatetimeIndex([close.index[-1]])
    cur = pressure_raw(close, last, macro_fn(last)).iloc[0]
    pct = []
    for k in PCOMP:
        v = cur.get(k)
        hist = raw[k].dropna().iloc[-(PS.WIN_M - 1):]
        if v is None or not np.isfinite(v) or len(hist) + 1 < PS.MIN_M:
            continue
        w = np.append(hist.to_numpy(float), v)
        pct.append(float((w <= v).mean() * 100))
    a = a0.dropna()
    p = float(np.mean(pct)) if len(pct) >= MIN_COMP else None
    a_now = float(a.iloc[-1]) if len(a) else None
    return {"date": str(close.index[-1].date()), "A0": None if a_now is None else round(a_now, 1), "P_g": None if p is None else round(p, 1),
            "C_rel": None if a_now is None or p is None else round((a_now + 100 - p) / 2, 1)}


# ───────────────────────── 评估 ─────────────────────────
def evaluate(X: pd.DataFrame) -> dict:
    """一个市场：各分数的 AUC（≥10% 全部 / 〜2010 / 2011〜，≥15%）与 ΔAUC（对 A0）。"""
    ok = len(X) >= MIN_ROWS and X["ev10"].nunique() == 2
    out = {"n": int(len(X)), "ok": bool(ok), "first": str(X.index[0].date()) if len(X) else None,
           "event_rate": round(float(X["ev10"].mean()), 3) if len(X) else None}
    if not ok:
        return out
    h1 = X.index < SPLIT
    for k in SCORES:
        s = X[k].to_numpy(float)
        out[k] = {"auc10": WT.auc_np(s, X["ev10"].to_numpy(float)), "auc15": WT.auc_np(s, X["ev15"].to_numpy(float)),
                  "sub": [WT.auc_np(s[h1], X["ev10"].to_numpy(float)[h1]), WT.auc_np(s[~h1], X["ev10"].to_numpy(float)[~h1])]}
    for k in SCORES:
        if k == "A0":
            continue
        a, b = out[k], out["A0"]
        dd = lambda x, y: None if x is None or y is None else x - y                                 # noqa: E731
        a["d10"], a["d15"] = dd(a["auc10"], b["auc10"]), dd(a["auc15"], b["auc15"])
        a["d_sub"] = [dd(x, y) for x, y in zip(a["sub"], b["sub"])]
    out["_s"] = {k: X[k].to_numpy(float) for k in ("A0", "C_rel")}
    out["_y"] = X["ev10"].to_numpy(float)
    out["_p"] = X.index.to_period("M")
    return out


def region_mean(vals: dict) -> float | None:
    return TI.region_mean(vals)


def joint_bootstrap(E: dict, keys: list[str], reps: int = BOOT_REPS, block: int = BOOT_BLOCK, seed: int = BOOT_SEED) -> np.ndarray:
    """主判定市场一起抽：日历 = 各市场评估月份的并集；每次抽同一组月份（24 个月一块、环形），各市场取落在其中的月末（可重复）
    → 每次的地区均衡 ΔAUC（C_rel − A0）。"""
    keys = [k for k in keys if E[k].get("ok")]
    cal = pd.PeriodIndex(sorted(set().union(*[set(E[k]["_p"]) for k in keys])), freq="M")
    n = len(cal)
    lists = {}
    for k in keys:
        pos = cal.get_indexer(E[k]["_p"])
        a = np.full(n, -1)
        a[pos] = np.arange(len(pos))
        lists[k] = a
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = np.full(reps, np.nan)
    for r in range(reps):
        st = rng.integers(0, n, nb)
        ii = ((st[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]
        acc = {}
        for k in keys:
            rows = lists[k][ii]
            rows = rows[rows >= 0]
            if len(rows) < MIN_ROWS:
                continue
            yb = E[k]["_y"][rows]
            a0, c = WT.auc_np(E[k]["_s"]["A0"][rows], yb), WT.auc_np(E[k]["_s"]["C_rel"][rows], yb)
            if a0 is not None and c is not None:
                acc[k] = c - a0
        v = region_mean(acc)
        if v is not None:
            out[r] = v
    return out


def judge(E: dict, dev: list[str], em: list[str], boot: np.ndarray) -> dict:
    ok = [k for k in dev if E[k].get("ok")]
    d = {k: E[k]["C_rel"]["d10"] for k in ok}
    d15 = {k: E[k]["C_rel"]["d15"] for k in ok}
    s1 = {k: E[k]["C_rel"]["d_sub"][0] for k in ok}
    s2 = {k: E[k]["C_rel"]["d_sub"][1] for k in ok}
    reg = {g: (float(np.mean([d[k] for k in ks if d.get(k) is not None])) if any(d.get(k) is not None for k in ks) else None)
           for g, ks in REGIONS.items()}
    vals = [v for v in d.values() if v is not None]
    de = [E[k]["C_rel"]["d10"] for k in em if E[k].get("ok") and E[k]["C_rel"]["d10"] is not None]
    bb = boot[np.isfinite(boot)]
    x = {"mean_d": region_mean(d), "region": reg, "n_pos": int(sum(v > 0 for v in vals)), "n_mk": len(vals),
         "boot_p": float((bb <= 0).mean()) if len(bb) else None, "boot_ci": [float(np.quantile(bb, q)) for q in (0.025, 0.975)] if len(bb) else None,
         "sub": [region_mean(s1), region_mean(s2)], "mean_d15": region_mean(d15), "em_mean_d": float(np.mean(de)) if de else None}
    x["checks"] = {"G1 地区均衡 ΔAUC ≥ +0.03": bool(x["mean_d"] is not None and x["mean_d"] >= G1_MEAN),
                   f"G2 ≥ {G2_MIN_N} 个市场 > 0 且两个地区都 > 0": bool(x["n_pos"] >= G2_MIN_N and all(v is not None and v > 0 for v in reg.values())),
                   "G3 联合自助法单侧 p ≤ 0.05": bool(x["boot_p"] is not None and x["boot_p"] <= ALPHA),
                   "G4 两个子期间都 > 0": bool(all(v is not None and v > 0 for v in x["sub"])),
                   "G5 新兴 ΔAUC 平均 > 0": bool(x["em_mean_d"] is not None and x["em_mean_d"] > 0),
                   "G6 ≥15% 地区均衡 ΔAUC ≥ 0": bool(x["mean_d15"] is not None and x["mean_d15"] >= 0)}
    x["pass"] = all(x["checks"].values())
    return x


def region_table(E: dict, dev: list[str], em: list[str], key: str) -> dict:
    """描述用：某个分数的地区均衡 ΔAUC / 市场数 / 新兴平均。"""
    ok = [k for k in dev if E[k].get("ok")]
    d = {k: E[k][key]["d10"] for k in ok}
    de = [E[k][key]["d10"] for k in em if E[k].get("ok") and E[k][key]["d10"] is not None]
    return {"mean_d": region_mean(d), "n_pos": int(sum((v or 0) > 0 for v in d.values())), "n_mk": len(d),
            "sub": [region_mean({k: E[k][key]["d_sub"][0] for k in ok}), region_mean({k: E[k][key]["d_sub"][1] for k in ok})],
            "mean_d15": region_mean({k: E[k][key]["d15"] for k in ok}), "em_mean_d": float(np.mean(de)) if de else None}


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=BOOT_REPS)
    ap.add_argument("--only", default="", help="只跑这些市场（逗号分隔，调试用；判定需要全部市场）")
    ap.add_argument("--check", action="store_true", help="登记前核对：只建各市场的月末表（个数、起止、有值的比例），不算任何 AUC、不看结果")
    a = ap.parse_args()
    t0 = time.time()
    gi = TI.git_info()
    d = TH.load_inputs()
    built = TH.build(d)
    keys = [k for k in ["US", "JP"] + list(MARKETS) if not a.only or k in a.only.split(",")]
    E, NOW, info = {}, {}, {}
    for k in keys:
        if k in ("US", "JP"):
            close, a0 = (d["spx"] if k == "US" else d["n225"]), built[k][0]
        else:
            close, _ = TI.index_close(MARKETS[k][0])
            a0 = a0_daily(close, d, MARKETS[k][3] == "early")
        X = frame(close, a0)
        if a.check:
            print(f"{k}: 月末 {len(X)}（{X.index[0].date() if len(X) else '—'}〜{X.index[-1].date() if len(X) else '—'}）；"
                  f"P_price 有值 {int(X['P_price'].notna().sum())}；A0 起 {a0.first_valid_index()}；{time.time() - t0:.0f}s", flush=True)
            continue
        E[k] = evaluate(X)
        NOW[k] = now_reading(close, a0)
        info[k] = {"n": E[k]["n"], "first": E[k]["first"], "last": str(X.index[-1].date()) if len(X) else None}
    if a.check:
        print("（--check：只核对数据，没有计算任何 AUC）")
        return 0
    dev = [k for k in keys if k in MARKETS and MARKETS[k][2] == "dev"]
    em = [k for k in keys if k in MARKETS and MARKETS[k][2] == "em"]
    boot = joint_bootstrap(E, dev, reps=a.reps)
    J = judge(E, dev, em, boot)
    desc = {k: region_table(E, dev, em, k) for k in ("P_inv", "C_relp")}

    fm = lambda v, f="{:.3f}": "—" if v is None or v != v else f.format(v)                         # noqa: E731
    fd = lambda v: fm(v, "{:+.3f}")                                                                  # noqa: E731
    nm = lambda k: TI.HOME.get(k) or MARKETS[k][1]                                                  # noqa: E731
    L = [f"# 「威胁高 + 压力已释放」全球确认（2026-09-29 登记；git {gi['rev']}{'（脏）' if gi['dirty'] else ''}；只跑一次）", "",
         f"判定（发达 15 市场，事先规则）：**{'全球确认成立' if J['pass'] else '不成立'}**"
         + ("" if J["pass"] else "（没过：" + "、".join(c for c, v in J["checks"].items() if not v) + "）"), "",
         "C_rel = 平均(A0, 100 − 压力)；目标 = 月末之后 60 个交易日内跌 ≥ 10%；ΔAUC = C_rel − A0（同一批月末）", "",
         "| 检查 | 值 | 过 |", "|---|---|---|",
         f"| G1 地区均衡 ΔAUC（欧洲 / 其他） | {fd(J['mean_d'])}（{' / '.join(fd(v) for v in J['region'].values())}） | {'✓' if J['checks']['G1 地区均衡 ΔAUC ≥ +0.03'] else '✗'} |",
         f"| G2 ΔAUC > 0 的市场 | {J['n_pos']} / {J['n_mk']} | {'✓' if list(J['checks'].values())[1] else '✗'} |",
         f"| G3 联合自助法单侧 p（95% 区间） | {fm(J['boot_p'])}（{' 〜 '.join(fd(v) for v in (J['boot_ci'] or [None, None]))}） | {'✓' if list(J['checks'].values())[2] else '✗'} |",
         f"| G4 子期间 〜2010 / 2011〜 | {' / '.join(fd(v) for v in J['sub'])} | {'✓' if list(J['checks'].values())[3] else '✗'} |",
         f"| G5 新兴 6 市场 ΔAUC 平均 | {fd(J['em_mean_d'])} | {'✓' if list(J['checks'].values())[4] else '✗'} |",
         f"| G6 ≥ 15% 地区均衡 ΔAUC | {fd(J['mean_d15'])} | {'✓' if list(J['checks'].values())[5] else '✗'} |", "",
         "## 各市场（月末；AUC ≥ 10%）", "",
         "| 市场 | 组 | 月末数（起） | 事件比例 | A0 | C_rel（Δ） | 100 − 压力（Δ） | C_relp（Δ） | Δ 〜2010 / 2011〜 | ≥15% Δ | 现在 A0 / 压力 / C_rel |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in keys:
        e, n = E[k], NOW[k]
        grp = "本国" if k in TI.HOME else ("发达" if MARKETS[k][2] == "dev" else "新兴")
        cur = f"{fm(n['A0'], '{:.0f}')} / {fm(n['P_g'], '{:.0f}')} / {fm(n['C_rel'], '{:.0f}')}（{n['date']}）"
        if not e.get("ok"):
            L.append(f"| {nm(k)} | {grp} | {e['n']} | — | — | — | — | — | — | — | {cur} |")
            continue
        c, p, q = e["C_rel"], e["P_inv"], e["C_relp"]
        L.append(f"| {nm(k)} | {grp} | {e['n']}（{e['first'][:7]}） | {e['event_rate'] * 100:.0f}% | {fm(e['A0']['auc10'])} | "
                 f"{fm(c['auc10'])}（{fd(c['d10'])}） | {fm(p['auc10'])}（{fd(p['d10'])}） | {fm(q['auc10'])}（{fd(q['d10'])}） | "
                 f"{fd(c['d_sub'][0])} / {fd(c['d_sub'][1])} | {fd(c['d15'])} | {cur} |")
    L += ["", "## 另报（只描述，不参与判定）", ""]
    for k, v in desc.items():
        L.append(f"- {SCORES[k]}：地区均衡 ΔAUC {fd(v['mean_d'])}（> 0 的市场 {v['n_pos']} / {v['n_mk']}）；子期间 {' / '.join(fd(x) for x in v['sub'])}；"
                 f"≥15% {fd(v['mean_d15'])}；新兴 {fd(v['em_mean_d'])}")
    L += ["", "本国（美国 / 日本）已在 pressure_threat_posthoc 看过（那里的压力含宽度、日本用日本国债），这里同一套算法只作对照，不算确认。",
          "结论（事先规则）：" + ("全球确认成立 → 提议把 C_rel 作为对照列加进威胁指数前向记录（用户确认才加；只记录，不改日报、不影响交易）。"
                            if J["pass"] else "不成立 → 维持 A0；「威胁高 + 压力已释放」只留在事后描述里，不进日报、不进前向记录。"),
          f"（耗时 {time.time() - t0:.0f}s）非投资建议。"]
    print("\n".join(L))
    out = {"git": gi, "judge": J, "describe": desc, "now": NOW, "markets": info,
           "eval": {k: {kk: vv for kk, vv in e.items() if not kk.startswith("_")} for k, e in E.items()},
           "boot": {"reps": int(np.isfinite(boot).sum()), "median": float(np.nanmedian(boot)) if np.isfinite(boot).any() else None}}
    fp = paths.out_dir() / ("threat_pressure_global" + ("_partial" if a.only or a.reps != BOOT_REPS else ""))
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
