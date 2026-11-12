"""loop8_r04_foreign.py — 第八个研究循环（新的独立信息来源）第 4 轮：资金流·投资部门别 —— 外国投资者最近 13 周的净买入占成交额 → 信息检查 + 规则 FFL
（2026-10-04 登记；先提交后只运行一次；来源「资金流·投资部门别」1 / 3；不是事后（投資部門別売買状況这个项目从没用过）→ S7 不适用）。

用户（2026-10-04）：「进行真正提高，需要新的、独立的信息来源的研究」。循环的规则：scripts/research_loop8.py 开头。
为什么（照实写）：
  - 第 1〜3 轮：期权溢价（风险补偿）、融资余额（发表之后不成立）都转不成更好的规则；还剩「谁在买卖」—— 日本市场里成交约六〜七成是外国投资者。
  - 文献方向 +：Froot, O'Connell & Seasholes（2001, Journal of Financial Economics）跨国资金流入之后的 60 天价格继续上涨（约一半的影响在 15 天以内）；
    Kamesaka, Nofsinger & Kawakita（2003, Journal of Banking & Finance）日本 1980〜1997：外国投资者的买卖成绩好、个人差。
  - 新不新：JPX 投資部門別売買状況（任何投资者类别的买卖）这个项目从没用过（数据盘点只用过信用残、决算、股价）。
数据（登记前只核对了板块名与日期，没算任何收益；J-Quants 原始数据只在 var/cache/jquants/）：J-Quants /equities/investor-types（Standard：2016-10 起），
  板块 TokyoNagoya（东证 + 名证全部，2016〜2026 一直存在），每周一行：FrgnBal = 外国投资者买 − 卖（円）、TotTot = 全部投资者买 + 卖（円）、PubDate = 公布日。
信号：决定日 = 日経 225 的每个已结束月末 t；取 PubDate ≤ t 的最近 13 周（不够 13 周 = 空）：FX_t = Σ FrgnBal ÷ Σ TotTot（外国投资者净买入占成交的比例）。
A 信息检查（只有一个市场）：样本 = 日経已结束的月末（FX 与目标都有值，约 2016-12〜2026-06）；目标 = 之后第 1 个交易日起 63 个交易日的日経对数收益；方向 +；
  联合区块自助法（一个市场 = 区块自助法；12 个月一块、2,000 次、种子 20261015）→ 单侧 p；I1 IC > 0 且 p ≤ 0.10；I2 样本按月末个数分成前后两半，两半的 IC 都 > 0；
  I3 文献之后（2001 年以后 = 全部样本）IC > 0（与 I1 的方向条件相同，照实写）。
B 规则 FFL（A 过了才运行；规则现在写定）：月末 FX_t < 0（最近 13 周外国投资者净卖出）→ 下一个月里日本个股的新仓倍数 × 0（信号日向后填；
  成交日 = 下一个交易日：第一个循环 ERG 的 gate_factor + loop_common.fill_scale 原样，与 B3 的判断层倍数相乘）；已有的持仓、离场、核心全部同 B3。
  只挡 2017-01-01 以后的信号日（之前数据不够 13 周、也让 E 年代不受影响）→ Z / E 与 B3 相同。第一关：research_loop6.stage1（S1〜S4 + S5：W / Jx 里 B3 会买的信号去掉被挡的之后，
  保留的逐笔胜率差、每笔差 ≥ 0 —— loop_r12_trendgate.other_stocks 原样；S7 不适用）。
  第二关（只有 1 个市场 → 单一序列）：第一关全过才运行；日本交易日上的「被挡」序列在 2017-01-01〜J 的最后一天整体循环平移 k 400 次
  （k ∈ [250, N − 250]，numpy default_rng([20261016, 0, s])）；Z / E 不受影响 → 只重算 J；research_loop.stage2（候选三个年代 Calmar 差合计严格大于 400 次的最大值）。
判定：A 不过 → 信息检查不过；A 过 → 更好候选 / 第一关不过 / 第二关不过。
只描述：前后两半的 IC、21 天目标的 IC、FX 五分位之后 63 天的平均收益、牛市月末 FX < 0 与 ≥ 0 之后的平均收益、个人投资者（IndBal）与信托银行（TrstBnkBal）同样算法的 IC。
接线核对（--wiring，不看任何收益）：倍数全 1 → 三个年代与 B3 逐项相同；真实的「被挡」序列 → Z / E 与 B3 逐项相同（2016 年以前没有数据）。
规模（--scale，只数日子）：FX 从哪个月末起、FX < 0 的月末比例（全部 / 日経牛）、J 里被挡的日本交易日比例与段数、最新的 FX。
运行：python scripts/loop8_r04_foreign.py（只运行一次；第二关在同一次运行里、第一关全过才算）；--scale；--wiring。输出 var/out/loop8_r04_foreign.md / .json。非投资建议。
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
import research_loop7 as R7                                                  # noqa: E402
import research_loop8 as RL8                                                 # noqa: E402

ROUND = 4
FAMILY = "资金流·投资部门别"
IDS = ("FFL",)
POSTHOC = False
WEEKS = 13
SECTION = "TokyoNagoya"
DATA_FROM = "2016-10-05"                                                     # J-Quants Standard 的起点（2016-10-04〜）
GATE_FROM = SHIFT_FROM = "2017-01-01"                                       # 2017 年以前不挡（E 年代不受影响）；第二关也从这天起平移
H_SHORT = 21
SEED_INFO, SEED_S2 = 20261015, 20261016
PLACEBO_N, SHIFT_GAP = 400, 250
OUT = "loop8_r04_foreign"
COLS = ("PubDate", "StDate", "EnDate", "Section", "FrgnBal", "TotTot", "IndBal", "TrstBnkBal")


def _f(v, f="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


# ───────────────────────── 数据 ─────────────────────────
def fetch_investor_types(to: str | None = None) -> pd.DataFrame:
    """J-Quants 周度投资部门别（全部板块）→ 只留需要的列；缓存在 var/cache/jquants/（不入库）。"""
    from qbreak import jquants as JQ
    cache = JQ.cache_dir() / "investor_types.csv"
    to = to or str(pd.Timestamp.now(tz="Asia/Tokyo").date())
    if cache.exists() and time.time() - cache.stat().st_mtime < 24 * 3600:
        return pd.read_csv(cache)
    rows = JQ.JQuants().get("/equities/investor-types", **{"from": DATA_FROM, "to": to})
    df = pd.DataFrame(rows)
    df = df[[c for c in COLS if c in df.columns]]
    df.to_csv(cache, index=False)
    return df


def weekly(df: pd.DataFrame, col: str = "FrgnBal", section: str = SECTION) -> pd.DataFrame:
    """某个板块的周度行：PubDate、EnDate、净额、成交（同一周的更正版也留着；用哪一版由 flow_share 按决定日挑）。"""
    d = df[df["Section"] == section].copy()
    d["PubDate"], d["EnDate"] = pd.to_datetime(d["PubDate"]), pd.to_datetime(d["EnDate"])
    d = d.sort_values(["EnDate", "PubDate"])
    return pd.DataFrame({"pub": d["PubDate"].to_numpy(), "end": d["EnDate"].to_numpy(),
                         "net": pd.to_numeric(d[col], errors="coerce").to_numpy(float),
                         "tot": pd.to_numeric(d["TotTot"], errors="coerce").to_numpy(float)})


# ───────────────────────── 信号与规则（纯函数，tests/test_loop8_r04.py） ─────────────────────────
def flow_share(w: pd.DataFrame, dates: pd.DatetimeIndex, weeks: int = WEEKS) -> pd.Series:
    """决定日 t：公布日 ≤ t 的各周（同一周有更正的，用 t 以前最后公布的那一版）里最近 weeks 周，Σ 净额 ÷ Σ 成交；不够 weeks 周 / 成交 ≤ 0 → 空。"""
    out = []
    for t in pd.DatetimeIndex(dates):
        x = w[w["pub"] <= t].sort_values(["end", "pub"]).drop_duplicates("end", keep="last").tail(weeks)
        ok = len(x) == weeks and np.isfinite(x["net"]).all() and np.isfinite(x["tot"]).all() and float(x["tot"].sum()) > 0
        out.append(float(x["net"].sum() / x["tot"].sum()) if ok else np.nan)
    return pd.Series(out, index=pd.DatetimeIndex(dates), dtype=float)


def signal(close: pd.Series, w: pd.DataFrame) -> pd.Series:
    return flow_share(w, RL8.month_ends_done(close))


def gate_flags(close: pd.Series, fx: pd.Series) -> pd.Series:
    """每个日本交易日：最近一个已结束月末（含当天）的 FX < 0 → 真（下一个月不开新仓）；FX 空 / 第一个月末之前 / GATE_FROM 之前 → 假。"""
    c = close.dropna().sort_index()
    me = RL8.month_ends_done(c)
    v = fx.reindex(me)
    f_me = pd.Series(np.where(v.to_numpy(float) < 0, 1.0, 0.0), index=me)
    f_me[v.isna()] = 0.0
    s = f_me.reindex(c.index.union(me)).ffill().reindex(c.index).fillna(0.0)
    return pd.Series((s.to_numpy(float) > 0.5) & (c.index >= pd.Timestamp(GATE_FROM)), index=c.index)


def samples(close: pd.Series, x: pd.Series, h: int = RL8.H) -> pd.DataFrame:
    d = RL8.month_ends_done(close)
    return pd.DataFrame({"x": x.reindex(d), "y": RL8.fwd_log_ret(close, d, h)}, index=d).dropna()


def halves_ic(s: pd.DataFrame) -> tuple[float | None, float | None]:
    m = len(s) // 2
    return RL8.spearman(s["x"].iloc[:m], s["y"].iloc[:m]), RL8.spearman(s["x"].iloc[m:], s["y"].iloc[m:])


def shifted(flags: pd.Series, k: int | None, a: str = SHIFT_FROM, b: str | None = None) -> pd.Series:
    """第二关：「被挡」序列在 [a, b]（日本交易日）整体循环平移 k；窗外不动；None = 不平移。"""
    s = flags.astype(bool).copy()
    if k is None:
        return s
    i = s.index[(s.index >= pd.Timestamp(a)) & ((s.index <= pd.Timestamp(b)) if b else True)]
    s.loc[i] = np.roll(s.loc[i].to_numpy(bool), int(k))
    return s


def shift_ks(n: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([SEED_S2, 0, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


# ───────────────────────── 输入 ─────────────────────────
def inputs() -> dict:
    raw = fetch_investor_types()
    c = R7.load_close("^N225")
    w = weekly(raw)
    fx = signal(c, w)
    extra = {k: signal(c, weekly(raw, col)) for k, col in (("ind", "IndBal"), ("trust", "TrstBnkBal"))}
    return {"close": c, "w": w, "fx": fx, "extra": extra, "bull": R7.bull(c), "flags": gate_flags(c, fx)}


# ───────────────────────── A 信息检查 ─────────────────────────
def quintile_means(df: pd.DataFrame) -> list[float | None]:
    if len(df) < 25:
        return [None] * 5
    q = pd.qcut(df["x"].rank(method="first"), 5, labels=False)
    return [round(float(df["y"][q == i].mean() * 100), 2) for i in range(5)]


def info_check(D: dict) -> dict:
    s = samples(D["close"], D["fx"])
    ic = RL8.spearman(s["x"], s["y"])
    h = halves_ic(s)
    boot = RL8.joint_bootstrap({"JP": s}, seed=SEED_INFO)
    jd = RL8.info_judge({"JP": ic}, {"JP": ic}, boot, sign=+1, halves=h)
    s21 = samples(D["close"], D["fx"], H_SHORT)
    b = D["bull"].reindex(s.index).fillna(False).astype(bool)
    neg, pos = s[b & (s["x"] < 0)], s[b & (s["x"] >= 0)]
    ex = {k: RL8.spearman(samples(D["close"], v)["x"], samples(D["close"], v)["y"]) for k, v in D["extra"].items()}
    return {"judge": jd, "ic": ic, "halves": list(h), "n": int(len(s)), "first": str(s.index[0].date()) if len(s) else None,
            "last": str(s.index[-1].date()) if len(s) else None, "ic21": RL8.spearman(s21["x"], s21["y"]), "quintiles_pct": quintile_means(s),
            "bull_neg": {"n": int(len(neg)), "mean_pct": round(float(neg["y"].mean() * 100), 2) if len(neg) else None},
            "bull_pos": {"n": int(len(pos)), "mean_pct": round(float(pos["y"].mean() * 100), 2) if len(pos) else None}, "extra_ic": ex}


def scale(D: dict) -> dict:
    x = D["fx"].dropna()
    b = D["bull"].reindex(x.index).fillna(False).astype(bool)
    f = D["flags"]
    j = f[(f.index >= pd.Timestamp("2017-01-01"))]
    seg = int((j.to_numpy()[1:] & ~j.to_numpy()[:-1]).sum() + (1 if len(j) and j.iloc[0] else 0))
    return {"fx_from": str(x.index[0].date()) if len(x) else None, "n": int(len(x)), "neg_pct": round(float((x < 0).mean() * 100), 1) if len(x) else None,
            "neg_bull_pct": round(float((x[b] < 0).mean() * 100), 1) if b.any() else None,
            "blocked_days_2017_pct": round(float(j.mean() * 100), 1) if len(j) else None, "blocked_segments": seg,
            "weeks": int(len(D["w"])), "latest": {"date": str(x.index[-1].date()), "fx_pct": round(float(x.iloc[-1] * 100), 3)} if len(x) else None}


# ───────────────────────── B 规则检验 ─────────────────────────
def em_mult(W: dict, e: str, flags: pd.Series) -> pd.Series:
    """新仓倍数（按成交日）：信号日被挡 → 0（ERG 的 gate_factor + loop_common.fill_scale 原样）。"""
    import loop_common as LCM
    import loop_r12_trendgate as G12
    days = W["ctx"][e]["days"]
    return LCM.fill_scale(G12.gate_factor(flags, days), days)


def stage_one(W: dict, D: dict) -> dict:
    import loop6_common as L6
    import loop_r12_trendgate as G12
    import research_loop6 as R6
    t0 = time.time()
    flags = D["flags"]
    reg = RL8.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        rc = L6.run(W, e, em_mult=em_mult(W, e, flags))
        base[e] = {k: rb.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")} | {"years": rb.get("years")}
        cand[e] = {k: rc.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")} | {"years": rc.get("years")}
        trades[e] = {"B3": rb.get("n"), "FFL": rc.get("n")}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = G12.other_stocks(W, flags)
    s1 = R6.stage1(cand, base, trade=os_, posthoc=None)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "stock_trades": trades, "other_stocks": os_, "drift": drift,
            "seconds": round(time.time() - t0)}


_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    import loop6_common as L6
    W, flags, base, ks, fixed = _G["W"], _G["flags"], _G["base"], _G["ks"], _G["fixed"]
    try:
        f = shifted(flags, ks[int(seed)], SHIFT_FROM, _G["end"])
        c = L6.run(W, "J", em_mult=em_mult(W, "J", f))["calmar"]
        if c is None or base["J"] is None:
            return None
        return round(float(fixed + c - base["J"]), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(W: dict, D: dict, a: dict, workers: int) -> dict:
    """单一序列第二关（第一关全过才调用）：「被挡」序列在 2017-01-01〜J 的最后一天整体循环平移 400 次；Z / E 不受影响（差固定），只重算 J。"""
    import multiprocessing as mp
    import loop2_common as L2
    import research_loop as RL
    t0 = time.time()
    base = {e: a["base"][e]["calmar"] for e in a["base"]}
    fixed = float(sum(a["stage1"]["d"][e] for e in ("Z", "E")))
    stat = round(float(a["stage1"]["sum"]), 6)
    f = D["flags"]
    n = int(((f.index >= pd.Timestamp(SHIFT_FROM)) & (f.index <= pd.Timestamp(L2.J_END))).sum())
    ks = shift_ks(n)
    _G.update({"W": W, "flags": f, "base": base, "ks": ks, "fixed": fixed, "end": L2.J_END})
    vals, seeds = [], list(range(PLACEBO_N))
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"随机 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
    s2 = RL.stage2(stat, vals)
    v = np.array([x for x in vals if x is not None], float)
    return {"stage2": s2, "n": n, "ks": ks, "placebo": vals, "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
            "seconds": round(time.time() - t0)}


# ───────────────────────── 运行 ─────────────────────────
def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop8_r04_foreign.py", "scripts/research_loop8.py",
                                 "scripts/loop_r12_trendgate.py", "qbreak/bullbear.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def run_all(workers: int = 3) -> int:
    t0 = time.time()
    code, dirty = git_head()
    D = inputs()
    A = info_check(D)
    res = {"loop": 8, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "scale": scale(D), "info": A}
    if not A["judge"]["ok"]:
        res["verdict"] = RL8.FAIL_INFO
    else:
        import loop6_common as L6
        W = L6.load3()
        a = stage_one(W, D)
        res["account"] = a
        if a["ok"]:
            b = stage_two(W, D, a, workers)
            res["single"] = b
            res["verdict"] = R7.FOUND if b["stage2"]["ok"] else R7.FAIL2
        else:
            res["verdict"] = R7.FAIL1
    res["seconds"] = round(time.time() - t0)
    write(res)
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    A, jd, sc = res["info"], res["info"]["judge"], res["scale"]
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    L = [f"# 第八个研究循环第 4 轮：资金流·投资部门别（外国投资者最近 13 周净买入占成交）→ 信息检查 + 规则 FFL（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop8_r04_foreign.py 开头）", "", f"**{res['verdict']}**", "",
         f"## A 信息检查（日本一个市场，方向 +）：{'过' if jd['ok'] else '不过'}",
         f"I1 {yn(jd['I1'])}（IC {_f(A['ic'])}，区块自助法单侧 p = {_f(jd['p'], '{:.3f}')}，要 ≤ 0.10；90% 区间 {' 〜 '.join(_f(v) for v in (jd.get('boot_ci') or [None, None]))}）；"
         f"I2 {yn(jd['I2'])}（前后两半 {_f(A['halves'][0])} / {_f(A['halves'][1])}）；I3 {yn(jd['I3'])}（全部样本都在文献之后）",
         f"样本 {A['n']} 个月末（{(A['first'] or '—')[:7]}〜{(A['last'] or '—')[:7]}）；21 天目标 IC {_f(A['ic21'])}；FX 五分位之后 63 天平均收益（低 → 高，%）"
         f"{' / '.join(_f(v, '{:+.2f}') for v in A['quintiles_pct'])}；日経牛市月末 FX < 0：{A['bull_neg']['n']} 次 {_f(A['bull_neg']['mean_pct'], '{:+.2f}')}%，"
         f"FX ≥ 0：{A['bull_pos']['n']} 次 {_f(A['bull_pos']['mean_pct'], '{:+.2f}')}%",
         "只描述：同样算法的 IC —— 个人投资者 " + _f(A["extra_ic"].get("ind")) + "、信托银行 " + _f(A["extra_ic"].get("trust")),
         f"规模：FX 从 {sc['fx_from']}（{sc['n']} 个月末）、FX < 0 的月末 {sc['neg_pct']}%（日経牛市月末 {sc['neg_bull_pct']}%）、2017 年以后被挡的日本交易日 "
         f"{sc['blocked_days_2017_pct']}%（{sc['blocked_segments']} 段）；最新 {(sc['latest'] or {}).get('date')} FX = {(sc['latest'] or {}).get('fx_pct')}%"]
    if "account" in res:
        import loop6_common as L6
        a = res["account"]
        s = a["stage1"]
        cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                          f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
        L += ["", f"## B 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
              f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；S5：{yn(s['S5'])}；S6 / S7 不适用", "",
              "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | FFL（Calmar 差） |", "|---|---|---|"]
        for e in L6.ERAS:
            L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
        L.append("个股笔数：" + "；".join(f"{e} B3 {a['stock_trades'][e]['B3']} → FFL {a['stock_trades'][e]['FFL']}" for e in L6.ERAS))
        L.append("S5（W / Jx）：" + json.dumps(a["other_stocks"], ensure_ascii=False, default=float))
    if "single" in res:
        b = res["single"]
        s2 = b["stage2"]
        L += ["", f"## B 第二关（单一序列，400 次循环平移）：{'过' if s2['ok'] else '不过'}",
              f"候选 {_f(s2['stat'], '{:+.4f}')}；400 次最大 {_f(s2['max'], '{:+.4f}')}、中位 {_f(b['q'].get(50), '{:+.4f}')}；≥ 候选 {s2['ge_stat']} 次；N = {b['n']}"]
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    print(json.dumps(scale(inputs()), ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    """登记前用（不看任何收益）：倍数全 1 → 三个年代与 B3 逐项相同；真实的「被挡」序列 → Z / E 与 B3 逐项相同。"""
    import loop6_common as L6
    D = inputs()
    W = L6.load3()
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    none = pd.Series(False, index=D["flags"].index)
    same0 = {e: bool(all(L6.run(W, e).get(x) == L6.run(W, e, em_mult=em_mult(W, e, none)).get(x) for x in keys)) for e in L6.ERAS}
    same_ze = {e: bool(all(L6.run(W, e).get(x) == L6.run(W, e, em_mult=em_mult(W, e, D["flags"])).get(x) for x in keys)) for e in ("Z", "E")}
    out = {"none_same_as_b3": same0, "real_flags_ze_same": same_ze}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if (all(same0.values()) and all(same_ze.values())) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第八个研究循环第 4 轮：资金流·投资部门别 → 信息检查 + 规则 FFL")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看任何收益）")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return run_all(a.workers)


if __name__ == "__main__":
    raise SystemExit(main())
