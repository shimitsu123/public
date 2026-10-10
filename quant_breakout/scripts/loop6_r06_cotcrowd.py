"""loop6_r06_cotcrowd.py — 第六个研究循环第二段（基准 B2 = 采用后的模拟盘 B1 + BCU）第 6 轮：「日元投机空头拥挤时，一回落就先对冲」CRW
（2026-10-03 登记；先提交后只运行一次；家族「核心·汇率对冲」第二段 1 / 3（用户 2026-10-03 在待办 ㊻ 解除这一段的禁令）；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：「本段解除「汇率对冲」家族禁令（最多 3 个做法），接着做 / 然后照现行规则继续」。循环的规则：scripts/research_loop6.py（开头七、八与末尾一节）；
基准 B2：scripts/loop6_common.py。
为什么做这个（照实写）：
  - 只看 B2 的诊断（2026-10-03，本会话；不跑任何候选）：美股牛、B2 没对冲（拿 1545）的日子里，日元走强让核心亏得最多的 20 天窗口是
    2013-05-22〜06-18（USD/JPY −6.3%）、2020-02-20〜03-19（−6.0%）、2009-11〜12（−6.0%）、2026-01〜02（−5.8%）、2011-02〜03（−5.6%）、
    2025-01〜02（−5.5%）、2023-07〜08（−5.3%）、2024-07〜08（−5.3%）、2003-08〜09、2004-03〜04、2006-04〜05、2007-02〜03、2013-07〜08、2023-11〜12；
    FJE（多数决的急升 或 日経熊且日元牛）多半在急升开始几天之后才对冲 —— 亏在最前面那几天。
  - 机制：日元套利交易拥挤时（投机者大量做空日元），日元一走强就有止损与平仓的连锁（Brunnermeier, Nagel & Pedersen 2008「Carry Trades and Currency
    Crashes」：投机者的期货仓位预示套利货币的崩跌风险）。CFTC 的持仓报告（Commitments of Traders）在本仓库里没用过 = 新信息；1986 年起有数据 → 能算 S7。
  - 以前的汇率对冲（第一个循环 FXH / FXC / RDH / RFH / FXE / JBH / FJH / FJE、循环以外 F1）都只看价格 / 利差 / 股市；RFH（日元与美股都在 50 日线下）
    因为来回换、换仓成本第一关不过。这里只在「拥挤」时才看 20 日线，不拥挤时什么都不加。
  → 看过 B2 的诊断与以前的汇率对冲结果之后设计 → 按事后处理，S7 适用（没看过的 1987〜2000 只有核心，候选 − B2 > 0）。
做法 CRW（参数事先写定：20 分位、3 年、20 日线 —— 20 日线与 FXE 的结束条件相同；没有从数据学出来的参数 → S6 不适用；不改个股 → S5 不适用）：
  - 数据：CFTC 期货持仓报告（Legacy、Futures Only）里的日元期货（CFTC Contract Market Code 097741；原 IMM、现 CME）：
    投机净仓位占比 P = (非商业多头 − 非商业空头) / 未平仓合约（All）；文件 https://www.cftc.gov/files/dea/history/deacot*.zip，
    原始数据只放 var/cache/cftc/（不入库）。1990 年以前只用每月最后一份（当时只公布月底的数据）。
  - 拥挤（每份报告 r）：P_r < 0 且 P_r ≤ 过去 3 年（as-of 日期在 (T_r − 1095 天, T_r]）里这些报告 P 的 20 分位（含本份；pandas 线性插值）；
    窗口里最早一份距 T_r 不到 730 天 → 不算拥挤。
  - 什么时候能用（不看未来；照 CFTC 公开的历史与停摆补发表写定，宁可晚不可早）：as-of 日期 T（周二）的报告
    2001 年起 → T + 6 天（周五 15:30 ET 公布，节日顺延到周一也赶得上周二东证开盘）；1990〜2000 年（半月 / 两周一次公布）→ T + 13 天；
    1990 年以前（每月 11〜12 日公布上月底的数据）→ T + 21 天；
    政府停摆（照 CFTC 的补发安排，统一用补发完的那天）：T ∈ 2013-10-01〜10-29 → 2013-11-08；T ∈ 2018-12-24〜2019-02-26 → 2019-03-08；
    T ∈ 2025-09-30〜2026-01-13 → 2026-01-20。这一天（美国日期）的值从下一个东证开盘起用（引擎「美国 d 日 → 东证 d+1 开盘」同一个对齐）。
  - 状态（美国交易日 d，USD/JPY = FRED DEXJPUS，与 FJE 同一个）：不在对冲中、d 日已知的最新报告是拥挤、USD/JPY < 自己的 20 日均线 → 开始；
    对冲中、USD/JPY > 20 日均线 → 结束（= FXE 的结束条件；结束不看拥挤）。
  - 接法：B2 的「对冲中」= FJE；候选 = FJE 或 CRW（各自向后填之后取「或」）→ 美股牛时对冲中拿对冲版纳指 2845，否则 1545；美股熊照 B2（负相关 1482，否则现金）。
    函数 = 第 3 轮同一个（loop6_r03_earlyreturn.over：fxh_over + tbh_over，「美股熊」用 B2 自己的）。个股层、判断层、费用全部同 B2。
第一关：research_loop6.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 CRW − B2 的 Calmar 差；只有核心的口径 = 第 3 轮 old_core，
  只把「对冲中」换成 FJE 或 CRW）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号 = CRW 的「对冲中」（东证日上：
  d 之前（含 d）最近一个美国日期的值）在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），
  窗外不动；B2（FJE、美股牛熊、BCU 的相关条件、1482 价格）不动。候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
接线核对（登记前，不看候选的结果）：① 拥挤永远是 False → 三个年代与 B2 逐项相同；② old_core 用 B2 自己的「对冲中」= 第 2 轮记录的 B2 只有核心 Calmar；
  ③ 不看未来：只用某一天以前的报告与汇率算出的 CRW，与用全部数据算出的、在那一天以前逐日相同。
只描述（不参与判定）：各年代拥挤报告的比例、CRW 对冲的天数 / 段 / 占牛市日子的比例、其中 FJE 本来就对冲的天数；核心换仓笔数；1987〜2000 的段；
  每年收益差；最新一份报告与最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r06_cotcrowd.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 CRW [--workers N]（第二关）。
输出 var/out/loop6_r06_cotcrowd.md / .json（第二关 loop6_r06_cotcrowd_stage2_CRW.md / .json）。非投资建议。

第二关（2026-10-03 第一关全过（合计 +0.229）之后另行登记；登记 = 加这一段的那次提交，之后不改、只运行一次，`--stage2 CRW --workers 3`；第一关与 --stage2 的代码不改）：
  形状 = 第一关登记时写定的那一个 —— CRW 的「对冲中」（东证日上）在 2000-01-04〜2026-09-30 的 6,549 个东证交易日上整体循环平移 k
  （research_loop6.shift_ks(n, 0)：numpy.random.default_rng([20261006, 0, s])，s = 0〜399），窗外不动；B2（FJE、美股牛熊、BCU 的相关条件、1482 价格）不动；
  每次三个年代都跑，统计量 = Calmar 差合计（对同一次运行的 B2）；CRW 要严格大于 400 次的最大值（research_loop6.stage2；有算不出的 = 不过）。
  另加只描述（不参与判定）：`--stage2ref CRW --workers 3` —— 只平移「拥挤」标记（美国交易日上、d 日已知的最新报告的拥挤与否）在 2000-01-04〜2026-09-30 的
  美国交易日上整体循环平移 k（k ∈ [250, N − 250]，种子 numpy.random.default_rng([20261006, 3, s])，s = 0〜399；窗外照真实的），USD/JPY 与 20 日线照真实的、
  状态机照样重算 → 回答「好处来自 CFTC 的持仓信息，还是只要在随便哪段日子里『跌破 20 日线就对冲』就有」；报候选在 400 次里的百分位。
  输出 var/out/loop6_r06_cotcrowd_stage2ref_CRW.md / .json。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop6_common as L6                                                    # noqa: E402
import loop6_r03_earlyreturn as N3                                           # noqa: E402
import loop6_r04_fastexit as Z4                                              # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 6
IDS = ("CRW",)
FAMILY = {"CRW": "核心·汇率对冲"}
KIND = {"CRW": "signal"}
POSTHOC = True
CODE = "097741"                                                              # 日元期货（IMM → CME）
Q, WIN_DAYS, MIN_SPAN = 0.20, 1095, 730                                      # 20 分位、过去 3 年、窗口里至少 2 年
LAG_NOW, LAG_9000, LAG_OLD = 6, 13, 21                                       # 2001 年起 / 1990〜2000 / 1990 年以前（日历天）
NOW_FROM, MONTHLY_BEFORE = "2001-01-01", "1990-01-01"
SHUTDOWNS = (("2013-10-01", "2013-10-29", "2013-11-08"),                    # (as-of 从, 到, 能用的那天)
             ("2018-12-24", "2019-02-26", "2019-03-08"),
             ("2025-09-30", "2026-01-13", "2026-01-20"))
MA_N = 20
CFTC_URL = "https://www.cftc.gov/files/dea/history/"
OLD = N3.OLD
REF2 = N3.REF2                                                               # 接线核对 ②：第 2 轮记录的 B2 只有核心
OUT = "loop6_r06_cotcrowd"
on_idx = N3.on_idx
over = N3.over
era_days = N3.era_days


# ───────────────────────── 数据（原始文件只在 var/cache/cftc/） ─────────────────────────
def cache_dir() -> Path:
    from qbreak import paths
    d = paths.home() / "cache" / "cftc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cot_files(last_year: int) -> list[str]:
    return ["deacot1986_2016.zip"] + [f"deacot{y}.zip" for y in range(2017, int(last_year) + 1)]


def fetch_cot(last_year: int | None = None) -> list[Path]:
    """缺的文件才下载（CFTC 公开数据）；返回本地文件。"""
    import urllib.request
    last_year = last_year or pd.Timestamp.now(tz="Asia/Tokyo").year
    out = []
    for fn in cot_files(last_year):
        p = cache_dir() / fn
        if not p.exists() or p.stat().st_size == 0:
            with urllib.request.urlopen(CFTC_URL + fn, timeout=120) as r:
                p.write_bytes(r.read())
        out.append(p)
    return out


def parse_cot(raw: bytes) -> pd.DataFrame:
    """一个 deacot 文件（zip）→ 日元期货的行：as-of 日期、未平仓、非商业多 / 空。"""
    z = zipfile.ZipFile(io.BytesIO(raw))
    with z.open(z.namelist()[0]) as f:
        df = pd.read_csv(f, encoding="latin-1", low_memory=False, dtype=str)
    col = {c.strip(): c for c in df.columns}
    d = pd.DataFrame({"date": pd.to_datetime(df[col["As of Date in Form YYYY-MM-DD"]].str.strip()),
                      "code": df[col["CFTC Contract Market Code"]].str.strip().str.zfill(6),
                      "oi": pd.to_numeric(df[col["Open Interest (All)"]], errors="coerce"),
                      "ncl": pd.to_numeric(df[col["Noncommercial Positions-Long (All)"]], errors="coerce"),
                      "ncs": pd.to_numeric(df[col["Noncommercial Positions-Short (All)"]], errors="coerce")})
    return d[d["code"] == CODE].drop(columns="code")


def load_cot(files: list[Path] | None = None) -> pd.DataFrame:
    files = files if files is not None else fetch_cot()
    d = pd.concat([parse_cot(Path(p).read_bytes()) for p in files])
    d = d.dropna().drop_duplicates("date", keep="last").sort_values("date").set_index("date")
    return d[d["oi"] > 0]


# ───────────────────────── 规则（纯函数，tests/test_loop6_r06.py） ─────────────────────────
def net_share(cot: pd.DataFrame) -> pd.Series:
    """投机净仓位占比 P = (非商业多 − 非商业空) / 未平仓（负 = 净做空日元）；1990 年以前只留每月最后一份。"""
    p = (cot["ncl"] - cot["ncs"]) / cot["oi"]
    old = p.index < pd.Timestamp(MONTHLY_BEFORE)
    ym = p.index.to_period("M")
    last_in_month = ~pd.Series(ym, index=p.index).duplicated(keep="last").to_numpy()
    return p[~old | last_in_month].astype(float)


def crowded_flags(p: pd.Series, q: float = Q, win: int = WIN_DAYS, span: int = MIN_SPAN) -> pd.DataFrame:
    """每份报告：P、过去 3 年（含本份）的 q 分位、拥挤（P < 0 且 P ≤ 分位；窗口不到 2 年 → False）。只用 as-of 不晚于本份的报告。"""
    p = p.sort_index()
    dates, vals = p.index, p.to_numpy(float)
    qs, ok = np.full(len(p), np.nan), np.zeros(len(p), bool)
    for i, t in enumerate(dates):
        m = (dates > t - pd.Timedelta(days=win)) & (dates <= t)
        if (t - dates[m][0]).days < span:
            continue
        qs[i] = float(np.quantile(vals[m], q))
        ok[i] = vals[i] < 0 and vals[i] <= qs[i]
    return pd.DataFrame({"P": vals, "q": qs, "crowded": ok}, index=dates)


def known_date(asof) -> pd.Timestamp:
    """as-of 日期的报告从哪一天（美国日期）起算已知（之后的第一个东证开盘起用）。"""
    t = pd.Timestamp(asof)
    for a, b, k in SHUTDOWNS:
        if pd.Timestamp(a) <= t <= pd.Timestamp(b):
            return pd.Timestamp(k)
    if t >= pd.Timestamp(NOW_FROM):
        return t + pd.Timedelta(days=LAG_NOW)
    if t >= pd.Timestamp(MONTHLY_BEFORE):
        return t + pd.Timedelta(days=LAG_9000)
    return t + pd.Timedelta(days=LAG_OLD)


def crowded_known(flags: pd.DataFrame) -> pd.Series:
    """按「已知的那天」排的拥挤标记（同一天有几份 → 用 as-of 最新的那份）。"""
    k = pd.Series([known_date(t) for t in flags.index], index=flags.index)
    s = pd.Series(flags["crowded"].to_numpy(bool), index=pd.DatetimeIndex(k.to_numpy()))
    s = s[~s.index.duplicated(keep="last")]
    return s.sort_index()


def crw_state(fx: pd.Series, crowded_us: pd.Series, ma_n: int = MA_N) -> pd.Series:
    """CRW 的「对冲中」（美国交易日）：不在对冲中、拥挤、USD/JPY < 20 日均线 → 开始；对冲中、USD/JPY > 20 日均线 → 结束。"""
    s = fx.dropna().sort_index().astype(float)
    ma = s.rolling(ma_n, min_periods=ma_n).mean().to_numpy()
    c = on_idx(crowded_us, s.index).to_numpy(bool)
    v = s.to_numpy()
    on, out = False, np.zeros(len(s), bool)
    for i in range(len(s)):
        if np.isfinite(ma[i]):
            if not on and c[i] and v[i] < ma[i]:
                on = True
            elif on and v[i] > ma[i]:
                on = False
        out[i] = on
    return pd.Series(out, index=s.index)


def candidate_uni(uni_b2: pd.Series, crw: pd.Series) -> pd.Series:
    """候选的「对冲中」= B2 的（FJE）或 CRW（各自向后填之后取「或」）。"""
    import loop_r04_yensurge as Y
    return Y.or_series(uni_b2, crw)


def shifted_crw(crw_t: pd.Series, k: int | None) -> pd.Series:
    """第二关：CRW 的「对冲中」（东证日上）在 2000-01-04〜J 的最后一天上整体循环平移 k（None = 不平移），窗外不动。"""
    return Z4.shifted_zone(crw_t, k)


def placebo_ks(n: int) -> list[int]:
    return R6.shift_ks(n, 0)


def segments(s: pd.Series) -> list[list]:
    """布尔序列的连续段：[[开始, 结束, 天数], ...]。"""
    v = s.to_numpy(bool)
    out, i = [], 0
    while i < len(v):
        if v[i]:
            j = i
            while j + 1 < len(v) and v[j + 1]:
                j += 1
            out.append([str(s.index[i].date()), str(s.index[j].date()), int(j - i + 1)])
            i = j + 1
        else:
            i += 1
    return out


def crw_days(crw_t: pd.Series, spx_t: pd.Series, fje_t: pd.Series, days: pd.DatetimeIndex) -> dict:
    """这段东证日里：CRW 对冲的天数、其中美股牛（核心起作用）的、其中 FJE 本来就对冲的、新加的；段数与最长（只数日子）。"""
    days = pd.DatetimeIndex(days)
    c, b, f = on_idx(crw_t, days), on_idx(spx_t, days), on_idx(fje_t, days)
    bull = ~b
    new = c & bull & ~f
    sg = segments(c & bull)
    return {"crw_days": int(c.sum()), "crw_bull_days": int((c & bull).sum()), "fje_already": int((c & bull & f).sum()),
            "new_days": int(new.sum()), "pct_of_bull": round(float(new.sum() / max(int(bull.sum()), 1) * 100), 1),
            "segments": len(sg), "longest": max([x[2] for x in sg], default=0)}


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict, cot: pd.DataFrame | None = None) -> dict:
    """B2 的输入（W["bcu"]）+ FJE 的「对冲中」+ COT 拥挤 + CRW（美国日 / 东证日）+ 候选的「对冲中」。"""
    import loop2_common as L2
    import loop_r04_yensurge as Y
    M = dict(W["bcu"])
    days = M["on_b"].index
    _, _, uni = L2.fje_states(W)
    cot = load_cot() if cot is None else cot
    flags = crowded_flags(net_share(cot))
    kn = crowded_known(flags)
    dex = W["inp"]["dexjp"].dropna()
    crw_us = crw_state(dex, on_idx(kn, dex.index))
    crw_t = on_idx(crw_us, days)
    M.update({"days": days, "uni": uni, "hf": Y.hedged_frame(W["inp"]), "flags": flags, "known": kn, "crw_us": crw_us, "crw_t": crw_t,
              "spx_t": on_idx(W["bear"]["US"], days), "fje_t": on_idx(uni, days), "uni_c": candidate_uni(uni, crw_t),
              "uni_c_us": candidate_uni(uni, crw_us)})
    return M


def scale(W: dict, M: dict) -> dict:
    out = {e: crw_days(M["crw_t"], M["spx_t"], M["fje_t"], era_days(W, e)) for e in L6.ERAS}
    fl = M["flags"]
    for e in L6.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        m = (fl.index >= pd.Timestamp(a)) & ((fl.index < pd.Timestamp(b)) if b else True)
        out[e]["crowded_report_pct"] = round(float(fl["crowded"][m].mean() * 100), 1) if m.any() else None
    w = R6.shift_window(M["crw_t"])
    out["crw_share_2000_2026"] = round(float(w.mean() * 100), 1)
    out["shift_n"] = len(w)
    cu = M["crw_us"]
    old = cu[(cu.index >= pd.Timestamp(OLD[0])) & (cu.index <= pd.Timestamp(OLD[1]))]
    out["old_segments"] = len(segments(old))
    out["old_days_pct"] = round(float(old.mean() * 100), 1) if len(old) else None
    lr = fl.iloc[-1]
    dex = W["inp"]["dexjp"].dropna()
    ma = dex.rolling(MA_N, min_periods=MA_N).mean()
    out["latest"] = {"report_asof": str(fl.index[-1].date()), "known_from": str(known_date(fl.index[-1]).date()),
                     "P_pct": round(float(lr["P"]) * 100, 1), "q20_pct": None if not np.isfinite(lr["q"]) else round(float(lr["q"]) * 100, 1),
                     "crowded": bool(lr["crowded"]), "usdjpy_date": str(dex.index[-1].date()), "usdjpy": round(float(dex.iloc[-1]), 2),
                     "ma20": round(float(ma.iloc[-1]), 2), "crw_on": bool(cu.iloc[-1])}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


_f = N3._f
git_head = N3.git_head


def stage_one() -> int:
    import loop2_r05_ddbrake as R5
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L6.load()
    M = inputs(W)
    ov = over(W, W["bear"]["US"], M["uni_c"], M["hf"], M["on_b"], M["fb"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"CRW": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["CRW"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B2": nb, "CRW": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B2": N3.old_core(W, M["uni"], W["bear"]["US"]), "CRW": N3.old_core(W, M["uni_c_us"], W["bear"]["US"])}
    unseen = None if old["B2"]["calmar"] is None or old["CRW"]["calmar"] is None else old["CRW"]["calmar"] - old["B2"]["calmar"]
    s1 = {"CRW": R6.stage1(cand["CRW"], base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    res = {"loop": 6, "segment": 2, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "scale": scale(W, M), "core_trades": trades, "old": old,
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s = res["stage1"]["CRW"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第二段第 6 轮：日元投机空头拥挤时，一回落就先对冲 CRW（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r06_cotcrowd.py 开头；基准 B2 = B1 + BCU）", "",
         f"- **CRW：{'第一关全过 → 另行登记第二关（CRW 对冲中循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B2 年化 / 最大回撤 / Calmar（前半 / 后半） | CRW（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['CRW'][e])}（{_f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：拥挤的报告 {_f(x['crowded_report_pct'], '{:.1f}')}%；CRW 对冲 {x['crw_days']} 天（美股牛 {x['crw_bull_days']} 天，其中 FJE 本来就对冲 "
                 f"{x['fje_already']} 天、新加 {x['new_days']} 天 = 牛市日子的 {x['pct_of_bull']}%；{x['segments']} 段、最长 {x['longest']} 天）；"
                 f"核心换仓 B2 {res['core_trades'][e]['B2']} → CRW {res['core_trades'][e]['CRW']} 笔")
    lt = sc["latest"]
    L.append(f"- CRW 在 2000〜2026 全部东证日里的比例 {sc['crw_share_2000_2026']}%；1987〜2000 {sc['old_segments']} 段（{_f(sc['old_days_pct'], '{:.1f}')}% 的日子）；"
             f"最新一份报告（as-of {lt['report_asof']}，{lt['known_from']} 起可用）P {lt['P_pct']}%（3 年 20 分位 {_f(lt['q20_pct'], '{:.1f}')}%）"
             f"→ {'拥挤' if lt['crowded'] else '不拥挤'}；USD/JPY {lt['usdjpy']}（{lt['usdjpy_date']}，20 日线 {lt['ma20']}）；CRW {'对冲中' if lt['crw_on'] else '不对冲'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%）" for k in ("B2", "CRW")))
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["CRW"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（CRW − B2，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B2 与第二段登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B2）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load()
    M = inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def no_lookahead(W: dict, cot: pd.DataFrame, cut: str) -> bool:
    """接线核对 ③：只用 cut 以前已知的报告与汇率算出的 CRW = 全部数据算出的（cut 以前逐日相同）。"""
    dex = W["inp"]["dexjp"].dropna()
    full = crw_state(dex, on_idx(crowded_known(crowded_flags(net_share(cot))), dex.index))
    c = pd.Timestamp(cut)
    cot_cut = cot[[known_date(t) <= c for t in cot.index]]
    part = crw_state(dex[dex.index <= c], on_idx(crowded_known(crowded_flags(net_share(cot_cut))), dex.index[dex.index <= c]))
    return bool(part.equals(full[full.index <= c]))


def wiring() -> int:
    """登记前用：① 拥挤永远是 False → 三个年代与 B2 逐项相同；② old_core(B2 的对冲中) = 第 2 轮记录的 B2 只有核心；③ 不看未来（几个切点）。"""
    from qbreak import paths
    W = L6.load()
    cot = load_cot()
    M = inputs(W, cot)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    never = candidate_uni(M["uni"], pd.Series(False, index=M["days"]))
    ov1 = over(W, W["bear"]["US"], never, M["hf"], M["on_b"], M["fb"])
    same_b2 = {}
    for e in L6.ERAS:
        rb, r1 = L6.run(W, e), L6.run(W, e, **ov1)
        same_b2[e] = bool(all(rb.get(x) == r1.get(x) for x in keys))
    oc = N3.old_core(W, M["uni"], W["bear"]["US"])["calmar"]
    ref2 = json.loads((paths.out_dir() / REF2).read_text(encoding="utf-8"))["old"]["B2"]["calmar"]
    cuts = ("1995-06-30", "2008-09-15", "2019-01-31", "2024-08-05")
    nla = {c: no_lookahead(W, cot, c) for c in cuts}
    out = {"never_crowded_same_as_b2": same_b2, "old_core_b2_same": bool(oc == ref2), "no_lookahead": nla,
           "reports": len(cot), "first_report": str(cot.index[0].date()), "last_report": str(cot.index[-1].date())}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b2.values()) and out["old_core_b2_same"] and all(nla.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = CRW 的对冲中循环平移） ─────────────────────────
_G: dict = {}


def _run_sum(W: dict, M: dict, uni_c: pd.Series, base: dict):
    kw = over(W, W["bear"]["US"], uni_c, M["hf"], M["on_b"], M["fb"])
    tot = 0.0
    for e in L6.ERAS:
        c = L6.run(W, e, **kw)["calmar"]
        if c is None or base[e] is None:
            return None
        tot += c - base[e]
    return round(float(tot), 6)


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        return _run_sum(W, M, candidate_uni(M["uni"], shifted_crw(M["crw_t"], ks[int(seed)])), base)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(k: str, workers: int) -> int:
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = L6.load()
    M = inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = over(W, W["bear"]["US"], M["uni_c"], M["hf"], M["on_b"], M["fb"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["crw_t"]))
    ks = placebo_ks(n)
    _G.update({"W": W, "M": M, "base": base, "ks": ks})
    vals = Z4._pool(_placebo_one, list(range(R6.PLACEBO_N)), workers, t0, "随机改动")
    s2 = R6.stage2(stat, vals)
    vd = R6.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "kind": KIND[k], "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat,
           "stage1_stat": s1["sum"], "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 6 轮 第二关：{k} vs 400 次 CRW 对冲中循环平移（{KIND[k]}；B2 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B2 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


# ───── 只描述（不参与判定；第二关登记时加）：只平移「拥挤」标记、USD/JPY 照真实的 ─────
REF_KIND = 3                                                                 # 种子 [20261006, 3, s]（research_loop6 的 0 / 1 / 2 之外）


def ref_ks(n: int, seeds=range(R6.PLACEBO_N), gap: int = R6.SHIFT_GAP) -> list[int]:
    """只描述用的平移量：numpy.random.default_rng([20261006, 3, s]).integers(gap, n − gap + 1)。"""
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([R6.LOOP_SEED, REF_KIND, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


def shifted_crowded(crowded_us: pd.Series, k: int | None) -> pd.Series:
    """「拥挤」标记（美国交易日上）在 2000-01-04〜J 的最后一天上整体循环平移 k（None = 不平移），窗外不动。"""
    return Z4.shifted_zone(crowded_us, k)


def ref_crw(dex: pd.Series, crowded_us: pd.Series, days: pd.DatetimeIndex, k: int | None) -> pd.Series:
    """只平移拥挤标记、USD/JPY 照真实的重算 CRW → 东证日上的「对冲中」。"""
    return on_idx(crw_state(dex, shifted_crowded(crowded_us, k)), days)


def _placebo_ref_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        return _run_sum(W, M, candidate_uni(M["uni"], ref_crw(M["dex"], M["crowd_us"], M["days"], ks[int(seed)])), base)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two_ref(k: str, workers: int) -> int:
    """只描述（不参与判定）：只平移「拥挤」标记的 400 次随机对照，报候选的百分位。"""
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做")
        return 1
    code, dirty = git_head()
    W = L6.load()
    M = inputs(W)
    dex = W["inp"]["dexjp"].dropna()
    M["dex"], M["crowd_us"] = dex, on_idx(M["known"], dex.index)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = over(W, W["bear"]["US"], M["uni_c"], M["hf"], M["on_b"], M["fb"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["crowd_us"]))
    ks = ref_ks(n)
    _G.update({"W": W, "M": M, "base": base, "ks": ks})
    vals = Z4._pool(_placebo_ref_one, list(range(R6.PLACEBO_N)), workers, t0, "随机改动（只平移拥挤标记）")
    s2 = R6.stage2(stat, vals)
    v = np.array([x for x in vals if x is not None], float)
    pct = round(float((v < stat).mean() * 100), 2) if len(v) else None
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "shape": "只平移 CFTC「拥挤」标记（美国交易日上），USD/JPY 与 20 日线照真实的重算",
           "describe_only": True, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "n": n, "placebo": vals, "max": s2["max"],
           "ge_stat": s2["ge_stat"], "valid": s2["valid"], "pct_below": pct,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 6 轮 只描述（不参与判定）：{k} vs 只平移「拥挤」标记的 400 次随机对照（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"候选的 Calmar 差合计 {stat:+.4f}；随机（拥挤标记在 {n} 个美国交易日上循环平移、USD/JPY 照真实的重算）比候选低的 {_f(pct, '{:.2f}')}%、"
         f"最大 {_f(s2['max'], '{:+.4f}')}、≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B2 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。只描述，判定只看 --stage2。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2ref_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2ref_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第二段第 6 轮：CRW（日元投机空头拥挤时，一回落就先对冲）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
    g.add_argument("--stage2", choices=IDS, help="第二关（第一关全过才做）")
    g.add_argument("--stage2ref", choices=IDS, help="只描述：只平移「拥挤」标记的随机对照（不参与判定）")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    if a.stage2:
        return stage_two(a.stage2, a.workers)
    if a.stage2ref:
        return stage_two_ref(a.stage2ref, a.workers)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
