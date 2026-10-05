"""industry_cycle_study.py — 业种「影响力」的周期（待办〔59〕）：影响力（市值占比）到顶 → 之后到头？刚起步、逐年增加但股价没反应 → 之后会涨？
（2026-10-05 登记；先提交后只运行一次；只研究、不改模拟盘 / 执行器）

用户原话（2026-10-05）：「按照种类的意思是想在一定时期某个业种会特别强 涨到一定高度的时候就会 bubble 然后又有其他的业种像雨后春笋一样出来
  想做这个分析优化现在算法 比如添加个参数分析现在这个业种影响力 如果影响力到顶峰了应该就到头了 有些业种其实刚起步在逐年增加但是股市还没有反应的
  或者公司和国家关系逐渐密切之类的」
以前没做过（2026-10-05 盘点）：业种市值占比 / 泡沫式暴涨 → 之后的收益与崩盘概率；基本面占比多年上升而股价没涨。做过且没过的相关研究：
行业动量当个股过滤（AUC 0.44〜0.50）、长期领先业种（R16 E36 / E60 比 12-1 动量差；美国过去 5 / 10 年与之后 5 / 10 年的秩相关 −0.12 / −0.19）、
业种闸门进账户（V5 / A4 / SEC / ISM / SBW …）、1 年以内的基本面信号（fund_study / invest_flow）、出口联动（exportlink / trade_fx）。

数据
  美国：Ken French 49 行业（CRSP，含已退市 → 没有幸存者偏差）1926-07〜2026-08 月度：价值加权收益；家数 × 平均规模 = 市值（月末）；
        年度 Sum of BE / Sum of ME × 上年 12 月末市值 = 账面权益 BE（qbreak/industry_influence.ff_panel）。
  日本：TOPIX-17 业种 —— 月收益 = NEXT FUNDS TOPIX-17 ETF（1617〜1633，2008-03 上市）月末收盘（价格收益，不含分红）；
        市值 = 2016-09 起 J-Quants 全部内国普通股的时价总额按当月的 17 业种加总（真值），之前用 ETF 的涨跌从 2016-09 往回推（splice_caps）；
        1629（商社・卸売）的 Yahoo 数据 2015-07 才开始 → 之前往回推市值时用 TOPIX ETF（1306）的涨跌代替（占比不跳），结果统计不算它 2015-07 前的月份；
        基本面 = 財務省 法人企業統計（資本金 10 億円以上）売上高 078，用既有的 MOF → 東証 33 对应（qbreak/invest_flow.MOF_TSE）合到 17 业种；
        医薬品在 MOF 里含在化学 → 与「素材・化学」合并；銀行 / 金融（除く銀行）没有可比数据 → E 的检验不含（14 组）。
        東証 33 业种（真值 2016-09〜）只用于「现在的状态」表（只描述）。
定义（qbreak/industry_influence.py；全部只用当月为止的数据）
  P 到顶区：占比 ≥ 36 个月前的 2 倍、= 60 个月（含当月）最高、≥ 平均占比（美国 1/49、日本 1/17）。
  R 到头确认：最近 24 个月里有过 P、当月占比比最近 24 个月最高点低 20% 以上。
  E 起步：基本面占比连续 3 年上升、3 年累计 ≥ +20%（相对），同期市值占比升得比它少（股价没跟上），且判定时不在 P。
        美国每年 6 月末判（BE = 上一财年；市值占比用上年 12 月末，与 BE 同一时点）；日本每年 9 月末判（4〜6 月季 9 月上旬公布；4 个季度合计到 6 月）。
  同一业种同一种事件至少隔 24 个月；前向 = 之后 24 个月相对市场（价值加权）的累计对数超额；崩 = 之后 24 个月内从判定时起算的累计总收益最低 ≤ −40%。
判定（事先写定，qbreak/industry_influence.verdict）
  H1-P「影响力到顶 → 之后跑输」：美国全样本 P 事件的 24 个月超额 − 全部业种月的平均 < 0，且按日历年整块重抽（2,000 次）的 95% 区间上限 < 0；
       前后两半（事件日 < / ≥ 1976-01）的差都 < 0；日本（TOPIX-17）事件 ≥ 3 个时差也要 < 0（< 3 个 → 「日本样本不够」，只按美国判，照实写）。
  H1-R「到头确认 → 继续跑输」：同上。
  H2-E「起步 → 之后跑赢」：方向反过来（差 > 0、区间下限 > 0、两半 > 0、日本 > 0）；基准 = 同一判定月（美国 6 月 / 日本 9 月）的全部业种。
  只描述：崩的概率（P / R vs 全部）、12 个月超额、Greenwood-Shleifer-You（2019）式「过去 24 个月相对市场 ≥ +100%」之后的崩盘率（复现用）、
  美国与日本现在各业种的状态（占比、3 年变化、P / R / E、日本的成交额占比）。
  通过的话：另外登记「进 B3 的账户检验」（例：R / P 业种不开新仓、E 业种优先），那之前不改模拟盘。
  H3「公司与国家关系变密切」：现在没有按国别的出口 / 公司地区销售数据 → 这次不检验（结果里写明需要的数据）。
事前预期（写在运行前）：P 之后崩的概率明显变高（GSY 2019：相对市场 +100% 时约 53%），但平均超额区间多半含 0 → H1-P 过的可能约 30%；
  R → 继续跑输约 40%；E → 文献方向不一（投资多的业种之后收益低 vs 价值），以前多次看到「价格领先实体数据」→ 约 20%。
运行：python scripts/industry_cycle_study.py --data（登记前：只数个数 / 覆盖）/ 不加参数 = 只运行一次。
输出 var/out/industry_cycle_study.md / .json（只放占比与统计，不放 J-Quants 原始数据）。非投资建议。
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
from qbreak import industry_influence as II                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

OUT = "industry_cycle_study"
SEED = 20261005
BOOT_N = 2000
H_MAIN, H_SHORT = 24, 12
US_SPLIT = pd.Timestamp("1976-01-01")
GSY_LOG = float(np.log(2.0))                                                 # 过去 24 个月相对市场 +100%
US_E_MONTH, JP_E_MONTH = 6, 9
MOF_SALES_FILE = "ssc_sales_ind_q.csv"


# ───────────────────────── 数据 ─────────────────────────
def us_data() -> dict:
    P = II.ff_panel(II.ff_text(49))
    ret, me = P["ret"], P["me_end"]
    return {"ret": ret, "me": me, "share": II.shares(me), "mkt": II.market_ret(ret, me), "be": P["be"], "me_dec": P["me_dec"]}


def jq_sector_monthly() -> dict:
    """J-Quants 全部内国普通股 → 月末时价总额（百万円）与当月売買代金（円）按当月的 17 / 33 业种加总（2016-09〜）。"""
    import allstock_data as AD
    from qbreak.jquants import to_yf
    D = AD.load()
    days = D["days"]
    names = D["names"]
    mc = pd.DataFrame(D["MC"], index=days, columns=names)
    va = pd.DataFrame(D["VA"], index=days, columns=names)
    lst = pd.DataFrame(D["listed"], index=days, columns=names)
    mc = mc.where(lst & (mc > 0))
    snaps = AD.snapshots()
    sdates = sorted(snaps)
    maps = {}
    for sd in sdates:
        m = snaps[sd]
        maps[sd] = {to_yf(c): (int(s17) if str(s17).isdigit() else None, II.norm_s33(s33))
                    for c, s17, s33 in zip(m["Code"].astype(str), m["S17"], m["S33Nm"]) if to_yf(c)}
    month = days.to_period("M")
    caps17, caps33, va17, va33 = {}, {}, {}, {}
    for p in sorted(set(month)):
        dd = days[month == p]
        last = dd[-1]
        sd = max([s for s in sdates if s <= last], default=sdates[0])
        mp = maps[sd]
        cap_row = mc.loc[dd].ffill().iloc[-1]
        va_sum = va.loc[dd].sum(min_count=1)
        k17 = pd.Series({t: mp.get(t, (None, None))[0] for t in names})
        k33 = pd.Series({t: mp.get(t, (None, None))[1] for t in names})
        ts = p.to_timestamp()
        caps17[ts] = cap_row.groupby(k17).sum(min_count=1)
        caps33[ts] = cap_row.groupby(k33).sum(min_count=1)
        va17[ts] = va_sum.groupby(k17).sum(min_count=1)
        va33[ts] = va_sum.groupby(k33).sum(min_count=1)
    f = lambda d: pd.DataFrame(d).T.sort_index().astype(float)               # noqa: E731
    c17 = f(caps17)
    c17 = c17[[k for k in c17.columns if k in II.S17_NAMES]]
    c33 = f(caps33)
    c33 = c33[[k for k in c33.columns if k in II.S33_TO_S17]]
    v17 = f(va17)
    v17 = v17[[k for k in v17.columns if k in II.S17_NAMES]]
    v33 = f(va33)
    v33 = v33[[k for k in v33.columns if k in II.S33_TO_S17]]
    return {"caps17": c17, "caps33": c33, "va17": v17, "va33": v33, "last_day": str(days[-1].date())}


def topix_ret() -> pd.Series:
    """TOPIX ETF（1306）月收益 %：只用来补 17 业种 ETF 缺的月份、往回推市值（1629 商社・卸売 的 Yahoo 数据 2015-07 才开始）。"""
    fps = sorted(paths.sub("cache").glob("1306.T_*y.csv"), key=lambda q: int(q.stem.split("_")[-1][:-1]), reverse=True)
    return II.month_end_close(fps[0]).pct_change() * 100


def jp_data(jq: dict | None = None) -> dict:
    ret = II.jp17_returns(paths.sub("cache"))
    jq = jq or jq_sector_monthly()
    tp = topix_ret().reindex(ret.index)
    ret_bf = ret.apply(lambda c: c.fillna(tp))                               # 只用于往回推市值（占比不跳）；结果统计仍用原来的（缺的月份不算）
    caps = II.splice_caps(jq["caps17"], ret_bf)
    caps = caps.loc[caps.index >= ret.dropna(how="all").index[0] - pd.offsets.MonthBegin(1)]
    share = II.shares(caps)
    mkt = II.market_ret(ret.reindex(caps.index), caps)
    return {"ret": ret.reindex(caps.index), "caps": caps, "share": share, "mkt": mkt, "jq": jq}


def jp_groups(jp: dict) -> dict:
    """E 用的 14 组：组的市值（17 业种加总）与组收益（组内按上月末市值加权）。"""
    caps, ret = jp["caps"], jp["ret"]
    gcaps, gret = {}, {}
    for g, ks in II.E_GROUPS.items():
        gcaps[g] = caps[ks].sum(axis=1, min_count=1)
        w = caps[ks].shift(1).where(ret[ks].notna())
        gret[g] = (w * ret[ks]).sum(axis=1, min_count=1) / w.sum(axis=1, min_count=1)
    return {"caps": pd.DataFrame(gcaps), "ret": pd.DataFrame(gret)}


def mof_sales(refresh: bool = False) -> pd.DataFrame:
    df = II.fetch_mof_items(("078",), MOF_SALES_FILE, refresh=refresh)
    return II.mof_fy_sum(df, "078", II.mof_groups(), end_q=2)


# ───────────────────────── 信号 ─────────────────────────
def pr_signals(share: pd.DataFrame) -> dict:
    pz = II.peak_zone(share)
    rs = II.rollover(share, pz)
    return {"P_state": pz, "R_state": rs, "P": II.first_events(pz), "R": II.first_events(rs)}


def annual_to_month(flag: pd.DataFrame, month: int, index: pd.DatetimeIndex) -> pd.DataFrame:
    """年度 bool（行 = 年）→ 月度 bool（只有每年 month 那一行可能 True）。"""
    out = pd.DataFrame(False, index=index, columns=flag.columns)
    for y in flag.index:
        ts = pd.Timestamp(int(y), month, 1)
        if ts in out.index:
            out.loc[ts] = flag.loc[y].reindex(out.columns).fillna(False).astype(bool).to_numpy()
    return out


def e_us(us: dict, p_state: pd.DataFrame) -> pd.DataFrame:
    e = II.emerging(II.shares(us["be"]), II.shares(us["me_dec"]))
    m = annual_to_month(e, US_E_MONTH, us["share"].index)
    return II.first_events(m & ~p_state.reindex_like(m).fillna(False).astype(bool))


def e_jp(jp: dict, gj: dict, sales: pd.DataFrame, p_state17: pd.DataFrame) -> pd.DataFrame:
    gcap = gj["caps"]
    sep = gcap[gcap.index.month == JP_E_MONTH]
    mk = sep.copy()
    mk.index = pd.Index(sep.index.year, name="year")
    yrs = sorted(set(mk.index) & set(sales.index))
    fund = II.shares(sales.reindex(yrs)[list(gcap.columns)])
    mkt = II.shares(mk.reindex(yrs)[list(gcap.columns)])
    e = II.emerging(fund, mkt)
    m = annual_to_month(e, JP_E_MONTH, gcap.index)
    pg = pd.DataFrame({g: p_state17.reindex(gcap.index)[ks].any(axis=1) for g, ks in II.E_GROUPS.items()})
    return II.first_events(m & ~pg.fillna(False).astype(bool))


def gsy_events(ret: pd.DataFrame, mkt: pd.Series) -> pd.DataFrame:
    ex = np.log1p(ret / 100.0).sub(np.log1p(mkt / 100.0), axis=0)
    past = ex.rolling(24, min_periods=24).sum()
    return II.first_events((past >= GSY_LOG).fillna(False))


# ───────────────────────── 统计 ─────────────────────────
def outcome_tables(ret: pd.DataFrame, mkt: pd.Series) -> dict:
    return {"f24": II.fwd_log_net(ret, mkt, H_MAIN), "f12": II.fwd_log_net(ret, mkt, H_SHORT), "crash": II.crash_fwd(ret)}


def compare(ev: pd.DataFrame, oc: dict, base_mask: pd.DataFrame | None = None, split: pd.Timestamp | None = None) -> dict:
    """事件 vs 基准（全部业种月；base_mask 给定 → 只用那些格子，例：每年 6 月）：24 / 12 个月超额与崩的概率；split → 前后两半。"""
    rows = II.event_rows(ev, f24=oc["f24"], f12=oc["f12"], crash=oc["crash"])
    base_src = {k: (v.where(base_mask.reindex_like(v).fillna(False).astype(bool)) if base_mask is not None else v) for k, v in oc.items()}
    base = II.all_rows(f24=base_src["f24"], f12=base_src["f12"], crash=base_src["crash"])

    def block(r, b):
        st = II.year_block_diff(r, b, "f24", n=BOOT_N, seed=SEED)
        c = r["crash"].dropna()
        cb = b["crash"].dropna()
        st.update({"n_events": int(len(r)), "f12": None if r["f12"].dropna().empty else float(r["f12"].mean()),
                   "f12_base": None if b["f12"].dropna().empty else float(b["f12"].mean()),
                   "crash": None if c.empty else float(c.mean()), "crash_n": int(len(c)), "crash_base": None if cb.empty else float(cb.mean())})
        return st
    out = {"all": block(rows, base)}
    if split is not None:
        out["h1"] = block(rows[rows["date"] < split], base[base["date"] < split])
        out["h2"] = block(rows[rows["date"] >= split], base[base["date"] >= split])
    out["events"] = [{"date": str(d.date())[:7], "ind": str(i), "f24": None if pd.isna(f) else round(float(f), 4),
                      "crash": None if pd.isna(c) else int(c)} for d, i, f, c in zip(rows["date"], rows["ind"], rows["f24"], rows["crash"])]
    return out


def month_mask(index: pd.DatetimeIndex, columns, month: int) -> pd.DataFrame:
    return pd.DataFrame(np.repeat((index.month == month)[:, None], len(columns), axis=1), index=index, columns=columns)


# ───────────────────────── 现在的状态（只描述） ─────────────────────────
def state_table(share: pd.DataFrame, names=None, va_share: pd.DataFrame | None = None, e_flag: pd.Series | None = None) -> list[dict]:
    sig = pr_signals(share)
    t = share.dropna(how="all").index[-1]
    i = list(share.index).index(t)
    prev = share.iloc[i - 36] if i >= 36 else pd.Series(np.nan, index=share.columns)
    hi60 = share.iloc[max(0, i - 59): i + 1].max()
    rows = []
    for c in share.columns:
        s = share.at[t, c]
        if pd.isna(s):
            continue
        r = {"ind": names.get(c, str(c)) if names else str(c), "share": round(float(s) * 100, 2),
             "x3y": None if pd.isna(prev.get(c)) or prev.get(c) == 0 else round(float(s / prev[c]), 2),
             "hi60": bool(s >= hi60[c] * (1 - 1e-12)) if i >= 59 else None,
             "P": bool(sig["P_state"].at[t, c]), "R": bool(sig["R_state"].at[t, c])}
        if va_share is not None and c in va_share.columns:
            vt = va_share.dropna(how="all").index[-1]
            j = list(va_share.index).index(vt)
            r["va_share"] = round(float(va_share.at[vt, c]) * 100, 2)
            r["va_x3y"] = round(float(va_share.at[vt, c] / va_share.iloc[j - 36][c]), 2) if j >= 36 and va_share.iloc[j - 36][c] > 0 else None
        if e_flag is not None:
            r["E"] = bool(e_flag.get(c, False))
        rows.append(r)
    return sorted(rows, key=lambda x: -x["share"])


# ───────────────────────── 两个模式 ─────────────────────────
def build_all(log=print) -> dict:
    t0 = time.time()
    us = us_data()
    log(f"美国：{us['share'].dropna(how='all').index[0].date()}〜{us['share'].dropna(how='all').index[-1].date()}，"
        f"{us['share'].shape[1]} 业种；BE {int(us['be'].notna().any(axis=1).sum())} 年（{time.time() - t0:.0f}s）")
    jp = jp_data()
    gj = jp_groups(jp)
    sales = mof_sales()
    log(f"日本：TOPIX-17 {jp['share'].dropna(how='all').index[0].date()}〜{jp['share'].dropna(how='all').index[-1].date()}，"
        f"真值从 {jp['jq']['caps17'].dropna(how='all').index[0].date()}；MOF 売上高 {sales.index[0]}〜{sales.index[-1]} 年（{time.time() - t0:.0f}s）")
    return {"us": us, "jp": jp, "gj": gj, "sales": sales}


def signals_all(B: dict) -> dict:
    us, jp, gj, sales = B["us"], B["jp"], B["gj"], B["sales"]
    su = pr_signals(us["share"])
    sj = pr_signals(jp["share"])
    return {"us": su, "jp": sj, "us_E": e_us(us, su["P_state"]), "jp_E": e_jp(jp, gj, sales, sj["P_state"]),
            "us_gsy": gsy_events(us["ret"], us["mkt"])}


def counts(ev: pd.DataFrame, split=None) -> dict:
    n = int(ev.to_numpy().sum())
    out = {"n": n}
    if split is not None:
        out["h1"] = int(ev[ev.index < split].to_numpy().sum())
        out["h2"] = n - out["h1"]
    return out


def data_mode() -> int:
    t0 = time.time()
    B = build_all()
    S = signals_all(B)
    c = {"us_P": counts(S["us"]["P"], US_SPLIT), "us_R": counts(S["us"]["R"], US_SPLIT), "us_E": counts(S["us_E"], US_SPLIT),
         "us_gsy": counts(S["us_gsy"], US_SPLIT), "jp_P": counts(S["jp"]["P"]), "jp_R": counts(S["jp"]["R"]), "jp_E": counts(S["jp_E"])}
    jq = B["jp"]["jq"]
    print("事件个数（只数个数，不看结果）：" + json.dumps(c, ensure_ascii=False))
    print(f"J-Quants 最后一天 {jq['last_day']}；17 业种真值 {jq['caps17'].shape}、33 业种 {jq['caps33'].shape}；"
          f"ETF 收益 {B['jp']['ret'].dropna(how='all').index[0].date()} 起；用时 {time.time() - t0:.0f}s")
    return 0


def run_mode() -> int:
    t0 = time.time()
    import subprocess
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "scripts/industry_cycle_study.py", "qbreak/industry_influence.py"],
                                capture_output=True, text=True).stdout.strip())
    B = build_all(log=lambda m: print(m, flush=True))
    S = signals_all(B)
    us, jp, gj = B["us"], B["jp"], B["gj"]
    oc_us = outcome_tables(us["ret"], us["mkt"])
    oc_jp = outcome_tables(jp["ret"], jp["mkt"])
    oc_jg = outcome_tables(gj["ret"], jp["mkt"])
    res = {}
    for key, ev_us, ev_jp, sign, oc_j, mask_us, mask_jp in (
            ("P", S["us"]["P"], S["jp"]["P"], -1, oc_jp, None, None),
            ("R", S["us"]["R"], S["jp"]["R"], -1, oc_jp, None, None),
            ("E", S["us_E"], S["jp_E"], +1, oc_jg, month_mask(us["share"].index, us["share"].columns, US_E_MONTH),
             month_mask(gj["caps"].index, gj["caps"].columns, JP_E_MONTH))):
        u = compare(ev_us, oc_us, mask_us, US_SPLIT)
        j = compare(ev_jp, oc_j, mask_jp)
        v = II.verdict(u["all"], u["h1"], u["h2"], {"n": j["all"]["n"], "diff": j["all"]["diff"]}, sign)
        res[key] = {"us": u, "jp": j, "verdict": v}
    gsy = compare(S["us_gsy"], oc_us, None, US_SPLIT)
    e_now = S["jp_E"].iloc[-12:].any()
    state = {"jp33": state_table(B["jp"]["jq"]["caps33"].pipe(II.shares), None, B["jp"]["jq"]["va33"].pipe(II.shares)),
             "jp17": state_table(jp["share"], II.S17_NAMES, B["jp"]["jq"]["va17"].pipe(II.shares)),
             "jp_e_groups_last12m": [g for g, v in e_now.items() if v],
             "us49": state_table(us["share"])}
    out = {"code": code, "dirty": dirty, "seconds": round(time.time() - t0), "seed": SEED, "boot_n": BOOT_N,
           "results": {k: {"verdict": v["verdict"], "us": {h: v["us"][h] for h in ("all", "h1", "h2")}, "jp": v["jp"]["all"],
                           "us_events": v["us"]["events"], "jp_events": v["jp"]["events"]} for k, v in res.items()},
           "gsy": {h: gsy[h] for h in ("all", "h1", "h2")}, "state": state, "jq_last_day": jp["jq"]["last_day"]}
    text = render(out)
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def _pp(x, k=100.0, nd=2) -> str:
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x * k:+.{nd}f}"


def render(o: dict) -> str:
    name = {"P": "H1-P 影响力到顶区 → 之后跑输？", "R": "H1-R 到顶后掉 20%（到头确认）→ 继续跑输？", "E": "H2-E 起步（基本面占比连升 3 年、股价没跟上）→ 之后跑赢？"}
    L = ["# 业种「影响力」的周期：到顶 → 到头？刚起步 → 之后会涨？（规则见脚本开头；登记后只运行一次）", "",
         f"代码 {o['code']}{'（有未提交改动）' if o['dirty'] else ''}；重抽 {o['boot_n']} 次（种子 {o['seed']}）；J-Quants 到 {o['jq_last_day']}。"
         "超额 = 之后 24 个月相对市场的累计对数超额（×100 ≈ %）；崩 = 之后 24 个月内跌 40% 以上的比例。", ""]
    for k in ("P", "R", "E"):
        r = o["results"][k]
        v = r["verdict"]
        L.append(f"## {name[k]} → **{v['label']}**")
        L.append("| 样本 | 事件数 | 24 个月超额（事件） | 基准 | 差 | 95% 区间 | 12 个月超额 | 崩的概率（事件 / 基准） |")
        L.append("|---|---|---|---|---|---|---|---|")
        for lab, st in (("美国 全部", r["us"]["all"]), ("美国 1926〜1975", r["us"]["h1"]), ("美国 1976〜", r["us"]["h2"]), ("日本 TOPIX-17", r["jp"])):
            L.append(f"| {lab} | {st['n_events']} | {_pp(st['mean'])} | {_pp(st['base'])} | {_pp(st['diff'])} | "
                     f"{_pp(st['lo'])} 〜 {_pp(st['hi'])} | {_pp(st['f12'])} vs {_pp(st['f12_base'])} | "
                     f"{_pct(st['crash'])} / {_pct(st['crash_base'])} |")
        L.append(f"- 判定：美国全样本 {'✓' if v['full_ok'] else '✗'}、两半 {'✓' if v['halves_ok'] else '✗'}、日本 "
                 f"{'样本不够（' + str(v['jp_n']) + ' 个）' if v['jp_ok'] is None else ('✓' if v['jp_ok'] else '✗')}")
        ev = [e for e in r["us_events"] if e["f24"] is not None]
        if ev:
            L.append("- 美国事件（最近 12 个）：" + "、".join(f"{e['date']} {e['ind']}（{_pp(e['f24'])}）" for e in ev[-12:]))
        if r["jp_events"]:
            L.append("- 日本事件：" + "、".join(f"{e['date']} {II.S17_NAMES.get(int(e['ind']), e['ind']) if str(e['ind']).isdigit() else '素材・化学＋医薬品'}"
                                              f"（{_pp(e['f24']) if e['f24'] is not None else '还没到 24 个月'}）" for e in r["jp_events"]))
        L.append("")
    g = o["gsy"]["all"]
    L += ["## 复现：Greenwood-Shleifer-You（2019）「过去 24 个月相对市场 ≥ +100%」之后（只描述；这里用比值：业种 ÷ 市场 ≥ 2 倍）",
          f"美国 {g['n_events']} 次：之后 24 个月崩的概率 {_pct(g['crash'])}（全部业种月 "
          f"{_pct(g['crash_base'])}）；24 个月超额 {_pp(g['mean'])}（基准 {_pp(g['base'])}，"
          f"差 {_pp(g['diff'])}，95% 区间 {_pp(g['lo'])} 〜 {_pp(g['hi'])}）。GSY 1926〜2014：+100% 时崩的概率约 53%。", ""]
    st = o["state"]
    L += ["## 现在的状态（只描述，不进交易）", "### 日本 東証 33 业种（J-Quants 真值）",
          "| 业种 | 市值占比 | 3 年前的几倍 | 60 个月新高 | P | R | 成交额占比 | 成交额占比 3 年前的几倍 |", "|---|---|---|---|---|---|---|---|"]
    for r in st["jp33"]:
        L.append(f"| {r['ind']} | {r['share']:.2f}% | {r['x3y'] if r['x3y'] is not None else '—'} | {'是' if r['hi60'] else ('—' if r['hi60'] is None else '否')} | "
                 f"{'★' if r['P'] else ''} | {'▼' if r['R'] else ''} | {r.get('va_share', '—')}% | {r.get('va_x3y') or '—'} |")
    L += ["", "### 日本 TOPIX-17（2016-09 前为往回推）",
          "| 业种 | 市值占比 | 3 年前的几倍 | 60 个月新高 | P | R |", "|---|---|---|---|---|---|"]
    for r in st["jp17"]:
        L.append(f"| {r['ind']} | {r['share']:.2f}% | {r['x3y'] if r['x3y'] is not None else '—'} | {'是' if r['hi60'] else '否'} | {'★' if r['P'] else ''} | {'▼' if r['R'] else ''} |")
    L.append(f"- 最近 12 个月里是 E（起步）的组：{('、'.join(st['jp_e_groups_last12m']) or '没有')}")
    L += ["", "### 美国 49 行业（占比前 10）", "| 行业 | 市值占比 | 3 年前的几倍 | 60 个月新高 | P | R |", "|---|---|---|---|---|---|"]
    for r in st["us49"][:10]:
        L.append(f"| {r['ind']} | {r['share']:.2f}% | {r['x3y'] if r['x3y'] is not None else '—'} | {'是' if r['hi60'] else '否'} | {'★' if r['P'] else ''} | {'▼' if r['R'] else ''} |")
    L += ["", "H3「公司与国家关系变密切」这次没有检验：要按国别 × 品类的出口（税関 普通貿易統計，1988〜）或公司的地区别销售（有価証券報告書 XBRL）。",
          "", f"用时 {o['seconds']} s。只研究、不改模拟盘与执行器。非投资建议。"]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="业种影响力周期（H1-P / H1-R / H2-E）")
    ap.add_argument("--data", action="store_true", help="登记前：取数并只数事件个数")
    a = ap.parse_args(argv)
    return data_mode() if a.data else run_mode()


if __name__ == "__main__":
    raise SystemExit(main())
