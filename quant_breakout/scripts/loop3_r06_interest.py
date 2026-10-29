"""loop3_r06_interest.py — 第三个研究循环第 6 轮（用户的题）：「借款利率上升、利润越来越盖不住利息 → 不开日本个股新仓」
IBS（按行业）/ IBA（全产业）两个做法（2026-10-02 登记；先提交后只运行一次；用掉 2 个做法 → 9 / 20）。

用户（2026-10-02）：「如果利率过高的话公司向银行借款会很高但是利润率并没有覆盖掉贷款类似这些也有可能会影响当前经济
  把这类的研究也放到现在的研究进行考虑」。
循环的规则：scripts/research_loop3.py（本轮两个做法都是 kind = "signal"）；基准 B1：scripts/loop2_common.py；
买点闸门的接法：IBS = candle_portfolio 的 em_tick {(票, 信号日): 倍数}；IBA = em_mult（按日的倍数，第二个循环 YSG / 第一个循环 ERG 原样）；
成交日 = 信号日的下一个交易日；倍数 0 = 这个候选不开、钱留在核心、名额给下一个候选。
为什么这样做（照实写）：
  - 以前没做过「企业利息负担」：利率研究（2026-09 的日本利率 × 日経、加息 / 降息预期、各期限国债、短债 vs 政策利率）看的是利率本身；
    家庭信贷研究（household_credit_study）看的是家庭；投资流向研究用过同一份法人企業統計，但只用设备投资。→ 新数据、新家族，不是事后组合（S7 不适用）。
  - 用户说的机制 =「利率高 → 借款成本高 → 利润盖不住利息」。最直接的量 = インタレスト・カバレッジ・レシオ（ICR，日本的标准定义：
    （営業利益 + 受取利息等）÷ 支払利息等）与借款利率（支払利息等 ÷ 有利子負債）。
  - 两种读法各一个做法（同一次登记、都在看任何收益之前写定）：
    IBS（微观）= 只挡「利息负担比全产业重、而且正在加重」的行业的新仓（利息对负债轻的行业 —— 机械、电机、零售，ICR 30 倍以上 —— 几乎无关）；
    IBA（宏观，你说的「影响当前经济」）= 全产业的利息负担在加重时，日本个股一律不开新仓。
    登记前的规模核对（只数状态与信号个数，不看收益）：IBS 只挡到 B1 会买的信号 Z 0 / E 4 / J 8 个 → 账户差必然很小、单独测说明不了问题 →
    同时登记 IBA（全产业状态在能用的时点上是 2008-03〜2009-02、2019-06〜2020-08、2023-06〜2026-09，现在仍在其中）。
  - 美国一侧（核心 = 纳指 100）不做做法：纳指 100 的公司现金多、利息负担小，与这个机制关系弱；美国的利息负担只描述（D1〜D3），不算做法。
  - 同一会话另一个只读检查（不跑候选、只看 B1）的整体判断照实写：按现在的规则剩下的题第二关都很难（≤ 1%）；本轮做是因为用户要求把这个题放进来。
共同的数据与量（参数都是「比一年前」「比全产业」，没有学出来的 → S6 不适用；改变个股买点 → S5 适用；不是事后 → S7 不适用）：
  - 財務省「法人企業統計調査」季報（e-Stat statsDataId=0003060191，金融業・保険業以外），規模 25 = 資本金 10 億円以上（全数调查；
    资本金小的抽样每年 4〜6 月期换样本 → 不用）；項目 081 営業利益、082 受取利息等、084 支払利息等、有利子負債 = 015 + 016（金融機関 / その他の
    短期借入金）+ 019 社債 + 020 + 021（金融機関 / その他の長期借入金）。原表只在 var/cache/mof/（不入库）。
  - 每个季度 t（都用 4 个季度的合计）：ICR = Σ(営業利益 + 受取利息等) ÷ Σ支払利息等；借款利率 r = Σ支払利息等 ÷ 有利子負債 4 季平均 × 100（%/年）。
  - 什么时候能用：季度 t 从「季末那个月 + 3 个月」的月末起（qbreak/invest_flow.avail_month_end：公布在 + 3 个月的第 1 个工作日 08:50 JST，
    保守地用月末；2020Q1 确报 7-27 → + 4），到下一个季度能用为止。日本信号日 d 用 d 那天（向后填）的状态。
做法 IBS（按行业）：
  - MOF 业种 → 東証业种用 qbreak/invest_flow.MOF_TSE（27 个；医薬品 / ゴム製品 / 銀行 / 証券 / 保険 / 空運 没有对应 → 永远不挡）；
    票的东证业种 = var/industry_s33.json + var/policy_extra_pool.json（今天的分类）。
  - 「利息负担重且在加重」S_g(t) = ICR_g(t) < ICR_g(t − 4)（比一年前更盖不住）且 r_g(t) > r_g(t − 4)（借款利率比一年前高）
    且 ICR_g(t) < 全产业（104）的 ICR(t)（利息负担比平均重）；算不出的 = False。
  - 信号日 d 票 t 的业种在 S_g → 这个候选的新仓倍数 × 0（em_tick）；已有的持仓、离场、核心（FJE）、判断层全部同 B1。
做法 IBA（全产业）：
  - 「全产业的利息负担在加重」A(t) = ICR_全产业(t) < ICR_全产业(t − 4) 且 r_全产业(t) > r_全产业(t − 4)（同样的「比一年前」，不比别的）。
  - 信号日 d 在 A → 那天的日本个股新仓倍数 × 0（em_mult：loop_r12_trendgate.gate_factor + loop_common.fill_scale，YSG 原样）；其余同 B1。
S5（两个做法各自）：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折的规则），
  被挡的信号去掉之后，保留的逐笔胜率差、每笔差都要 ≥ 0（IBS 按票的业种挡；IBA = loop_r12_trendgate.other_stocks 原样）。
第一关：research_loop3.stage1（= research_loop2.stage1；trade = W / Jx 的差，lenses = None，posthoc = None），两个做法各自判定。
第二关（第一关全过的才做；另行登记（提交）后只运行一次）：kind = "signal"，形状预定 ——
  IBS：整个行业状态面板（营业日 × 27 个业种）在 2000-01-03〜2026-09-30 的营业日上用同一个 k 整体循环平移；
  IBA：全产业状态（营业日）在同一段营业日上整体循环平移；k ∈ [250, N − 250]，research_loop3.shift_ks 同一组种子 s = 0〜399；
  其余不动；统计量 = Calmar 差合计，要严格大于 400 次的最大值。细节在那时写定。
接线核对（登记前，不看候选的收益）：① IBS 要挡的每一对倍数换成 1（em_tick 全 1）→ J 的账户与 B1 逐项相同；② IBA 状态全 False（倍数全 1）→ 同样相同；
  ③ J 的 em_tick 对数 > 0、J 里 IBA 状态中的日本交易日 > 0。
规模核对（登记前，不看收益）：见 sim_changes 的登记一节（--scale）。
只描述（不参与判定）：
  D1 现在的读数（日本：全产业与各业种的 ICR、借款利率与一年前比、哪些业种在状态中；美国：非金融企业的利息负担（Z.1 支付利息 ÷（NIPA 税前利润 +
     支付利息））、平均借款利率（Z.1 支付利息 ÷ 债券 + 贷款）、穆迪 Baa 收益率 − 平均借款利率（新借的钱比旧债贵多少）；BIS 17 国非金融企业
     债务偿还比率 DSR 最新值与一年变化）。
  D2 全产业「ICR 变差且借款利率上升」的历史段（日本 1960〜、美国 1953〜，同样的「比一年前」、同样 + 3 个月才用）。
  D3 状态中 vs 不在状态中（月末取样，之后 12 个月 / 4 个季度）：日経225 / S&P500 的涨跌、实际 GDP 增长（日本 1994〜、美国 1947〜）、
     日本工业生产（1960〜2023）、美国之后 12 个月内有没有 NBER 衰退。
  D4 横向（BIS 17 国）：非金融企业 DSR 比一年前高（季末 + 6 个月才用：BIS 大约季末后 5〜6 个月公布）vs 不高 → 之后 12 个月本国股指（本币、
     价格指数）；有 2000 年以前起的指数数据的国家才算（没有的照实列出）。
  另：各年代状态中的比例、B1 会买的信号落在状态中的个数（IBS 按业种）、账户的个股笔数与每年收益差、W / Jx 被挡信号的胜率 / 每笔。
事前预期（照实写，按一般的市场历史估计，不是这个项目的结果）：
  - IBS：只挡到十来个信号 → 账户的差很小，S1（+0.03）几乎过不了；第一关约 5%。
  - IBA：Z 不动；E 挡掉 2008-03〜2009-02 的新仓（金融危机里的假突破多 → 可能为正）；J 挡掉 2019-06〜2020-08 与 2023-06〜2026-09 的新仓
    （约 J 的一半日子；钱留在纳指核心；2020-03 的暴跌前后可能为正，2023〜2026 日本股票强 → 可能为负）→ 第一关约 15%，第二关约 10%。
  - 两个合起来「更好候选」约 1〜2%。
  - D3：美国「利息负担加重」之后 4 个季度 GDP 增长偏低、衰退多（1989〜90、2000〜01、2007〜08）的可能性大；股指之后 12 个月的差不一定（股价先走）；
    D4：DSR 上升之后的股指收益平均略低，但各国不一致。
运行：python scripts/loop3_r06_interest.py（第一关 + 只描述 D1〜D4）；--scale（只数规模、不算收益）；--wiring（登记前的接线核对）；
     --now（只算 D1 + D2：现在的读数与历史段，不看收益）。输出 var/out/loop3_r06_interest.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 6
IDS = ("IBS", "IBA")
FAMILY = "个股层·企业利息负担"
POSTHOC = False
KIND = "signal"
SIZE = "25"                                                                  # 資本金 10 億円以上（全数调查）
ALL = "104"                                                                  # 全産業（除く金融保険業）
OP, RECV, PAID = "081", "082", "084"                                         # 営業利益 / 受取利息等 / 支払利息等
DEBT = ("015", "016", "019", "020", "021")                                   # 短期借入金 ×2 + 社債 + 長期借入金 ×2
ITEMS = (*DEBT, OP, RECV, PAID, "013", "086", "139")                         # 013 資産合計 / 086 経常利益 / 139 借入金利子率（只描述）
MOF_FILE = "ssc_interest_ind_q.csv"
BIS_URL = "https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip"
BIS_FILE = "WS_DSR_csv_flat.zip"
BIS_LAG = 6                                                                  # BIS DSR：季末 + 6 个月的月末才用
SHIFT_FROM = "2000-01-03"
OUT = "loop3_r06_interest"
US_FRED = {"paid": "BOGZ1FA106130001Q", "debt": "BCNSDODNS", "pbt": "A464RC1Q027SBEA"}   # 百万美元 SAAR / 百万美元 / 十亿美元 SAAR
BIS_INDEX = {"US": "^GSPC", "JP": "^N225", "AU": "^AXJO", "BE": "^BFX", "CA": "^GSPTSE", "DE": "^GDAXI", "DK": "^OMXC25", "ES": "^IBEX",
             "FI": "^OMXH25", "FR": "^FCHI", "GB": "^FTSE", "IT": "FTSEMIB.MI", "KR": "^KS11", "NL": "^AEX", "NO": None,
             "PT": "PSI20.LS", "SE": "^OMX"}
BIS_FULL_FROM = "2000-12-31"                                                 # 指数从这天以前就有的国家才算进 D4


# ───────────────────────── 数据（原表只在 var/cache/，不入库） ─────────────────────────
def fetch_mof(refresh: bool = False) -> pd.DataFrame:
    """規模 25 × 全部业种 × ITEMS 的季度长表（size / ind / q / item / value，百万円）→ var/cache/mof/ssc_interest_ind_q.csv。"""
    from qbreak import paths
    fp = paths.sub("cache") / "mof" / MOF_FILE
    if fp.exists() and not refresh:
        return pd.read_csv(fp, dtype={"size": str, "ind": str, "item": str})
    from curl_cffi import requests as cr

    from qbreak import invest_flow as IF
    base = "https://www.e-stat.go.jp/"
    S = cr.Session(impersonate="chrome")
    S.get(f"{base}dbview?sid={IF.SID}", timeout=60).raise_for_status()
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}dbview?sid={IF.SID}",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    m = S.post(f"{base}dbview/api_get_model?sid={IF.SID}", data="", headers=hdr, timeout=120).json()
    want = {}
    for mt in m["matters"].values():
        name = str(mt.get("matterName") or "")
        if "調査項目" in name:
            want[mt["matterId"]] = set(ITEMS)
        elif "規模" in name:
            want[mt["matterId"]] = {SIZE}
    if len(want) != 2:
        raise RuntimeError(f"e-Stat 维度名对不上：{[mt.get('matterName') for mt in m['matters'].values()]}")
    df = IF.parse_estat_csv(IF._download(IF.SID, want))
    fp.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(fp, index=False)
    return pd.read_csv(fp, dtype={"size": str, "ind": str, "item": str})


def group_table(df: pd.DataFrame, codes) -> pd.DataFrame:
    """长表 → 季度（连续的 PeriodIndex）× 项目，几个 MOF 业种码加总（百万円）。"""
    from qbreak import invest_flow as IF
    x = df[(df["size"].astype(str) == SIZE) & df["ind"].astype(str).isin([str(c) for c in codes])]
    t = x.pivot_table(index="q", columns="item", values="value", aggfunc="sum")
    if t.empty:
        return t
    t.index = pd.PeriodIndex([IF.q_period(q) for q in t.index], freq="Q")
    t = t.sort_index()
    return t.reindex(pd.period_range(t.index.min(), t.index.max(), freq="Q"))


def coverage(x: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(ICR, r)：4 季合计（営業利益 + 受取利息等）÷ 4 季合计支払利息等；4 季合计支払利息等 ÷ 有利子負債 4 季平均 × 100（%/年）。
    缺一个季度 → 那几个 4 季窗口算不出（NaN）；支払利息等 / 有利子負債 ≤ 0 → NaN。"""
    paid = x[PAID].rolling(4).sum()
    earn = (x[OP] + x[RECV]).rolling(4).sum()
    debt = x[list(DEBT)].sum(axis=1, min_count=len(DEBT)).rolling(4).mean()
    icr = earn / paid.where(paid > 0)
    r = paid / debt.where(debt > 0) * 100
    return icr, r


def squeeze_q(icr: pd.Series, r: pd.Series, icr_all: pd.Series | None = None) -> pd.Series:
    """季度：ICR 比一年前低 且 借款利率比一年前高（且给了 icr_all 时：ICR 低于全产业同一季）→ True；算不出的 = False。"""
    ok = icr.notna() & icr.shift(4).notna() & r.notna() & r.shift(4).notna()
    st = (icr < icr.shift(4)) & (r > r.shift(4))
    if icr_all is not None:
        a = icr_all.reindex(icr.index)
        ok &= a.notna()
        st &= icr < a
    return (st & ok).astype(bool)


def avail_index(periods) -> pd.DatetimeIndex:
    from qbreak import invest_flow as IF
    return pd.DatetimeIndex([IF.avail_month_end(p) for p in periods])


def to_daily(st_q: pd.Series, days, avail=None) -> pd.Series:
    """季度状态 → 从能用的那天起（缺省 = invest_flow.avail_month_end），向后填到 days（之前 = False）。"""
    idx = avail_index(st_q.index) if avail is None else pd.DatetimeIndex(avail)
    av = pd.Series(st_q.to_numpy(bool), index=idx)
    av = av[~av.index.duplicated(keep="last")].sort_index()
    days = pd.DatetimeIndex(days)
    return av.astype(float).reindex(days.union(av.index)).ffill().reindex(days).fillna(0.0) > 0.5


def sector_states(df: pd.DataFrame, days) -> pd.DataFrame:
    """日子 × 東証业种（invest_flow.MOF_TSE 的 27 个）：「利息负担重且在加重」S_g。"""
    from qbreak import invest_flow as IF
    icr_all, _ = coverage(group_table(df, [ALL]))
    out = {}
    for sec, codes in IF.MOF_TSE.items():
        icr, r = coverage(group_table(df, codes))
        out[sec] = to_daily(squeeze_q(icr, r, icr_all), days)
    return pd.DataFrame(out, index=pd.DatetimeIndex(days))


def agg_daily(df: pd.DataFrame, days) -> pd.Series:
    """IBA：全产业（104）「ICR 比一年前低且借款利率比一年前高」，按能用的时点向后填到 days。"""
    icr_all, r_all = coverage(group_table(df, [ALL]))
    return to_daily(squeeze_q(icr_all, r_all), days)


def ticker_sectors() -> dict[str, str]:
    """票 → 東証业种（今天的分类：var/industry_s33.json + var/policy_extra_pool.json）；只留 MOF_TSE 里有的业种（其余 = 永远不挡）。"""
    import policy_event_data as PD

    from qbreak import invest_flow as IF
    mp = {**PD.s33_map(), **PD.extra_pool()}
    return {t: s for t, s in mp.items() if s in IF.MOF_TSE}


# ───────────────────────── 闸门（纯函数，tests/test_loop3_r06.py） ─────────────────────────
def gated_at(states: pd.DataFrame, sec: dict[str, str], tickers, dates) -> np.ndarray:
    """每个（票, 信号日）：票的业种那天（向后填）在不在状态中；业种对不上 / 那天之前没有状态 = False。"""
    t = [str(x) for x in np.asarray(tickers)]
    d = pd.DatetimeIndex(pd.to_datetime(np.asarray(dates)))
    if not len(t):
        return np.zeros(0, bool)
    u = d.unique()
    S = states.astype(float).reindex(u.union(states.index)).ffill().reindex(u).fillna(0.0) > 0.5
    arr, pos = S.to_numpy(bool), S.index.get_indexer(d)
    cols = {c: i for i, c in enumerate(S.columns)}
    out = np.zeros(len(t), bool)
    for k, (tk, p) in enumerate(zip(t, pos)):
        c = cols.get(sec.get(tk))
        if c is not None and p >= 0:
            out[k] = arr[p, c]
    return out


def gate_ticks(states: pd.DataFrame, sec: dict[str, str], names, days, f: float = 0.0) -> dict:
    """em_tick {(票, 信号日): f}：names × days 里，票的业种那天在状态中的每一对（成交日 = 下一个交易日；f = 0 → 不开）。"""
    days = pd.DatetimeIndex(days)
    S = states.astype(float).reindex(days.union(states.index)).ffill().reindex(days).fillna(0.0) > 0.5
    out = {}
    for t in names:
        s = sec.get(str(t))
        if s is None or s not in S.columns:
            continue
        for d in S.index[S[s].to_numpy(bool)]:
            out[(str(t), d)] = float(f)
    return out


def era_names(W: dict, e: str) -> list[str]:
    ctx = W["ctx"][e]
    return [str(ctx["names"][j]) for j in ctx["cols"]]


def era_ticks(W: dict, e: str, states: pd.DataFrame, sec: dict[str, str], f: float = 0.0) -> dict:
    return gate_ticks(states, sec, era_names(W, e), W["ctx"][e]["days"], f)


def other_stocks(W: dict, states: pd.DataFrame, sec: dict[str, str]) -> dict:
    """S5：W / Jx 里 B1 会买的信号（W2 + C；C 用 E / J 那一折）去掉业种在状态中的之后，保留 vs 全部。"""
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        tk, dt = X["ticker"].to_numpy()[kc], X["date"].to_numpy()[kc]
        net = X["net"].to_numpy(float)[kc]
        g = gated_at(states, sec, tk, dt)
        dl = CA.delta(net, ~g)
        gone = net[g]
        out[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"],
                  "gone_n": int(len(gone)), "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                  "gone_mean": float(gone.mean()) if len(gone) else None,
                  "unmapped": int(sum(1 for x in tk if str(x) not in sec))}
    return out


def iba_mult(W: dict, e: str, agg: pd.Series) -> pd.Series:
    """IBA 的新仓倍数（按成交日）：信号日在全产业状态中 → 0（loop_r12_trendgate.gate_factor + loop_common.fill_scale，YSG 原样）。"""
    import loop_common as LCM
    import loop_r12_trendgate as G12
    days = W["ctx"][e]["days"]
    return LCM.fill_scale(G12.gate_factor(agg, days), days)


def other_stocks_iba(W: dict, agg: pd.Series) -> dict:
    """IBA 的 S5：W / Jx 里 B1 会买的信号去掉状态中那些日子的之后，保留 vs 全部（loop_r12_trendgate.other_stocks 原样）。"""
    import loop_r12_trendgate as G12
    return G12.other_stocks(W, agg)


# ───────────────────────── 规模（不看收益） ─────────────────────────
def window_mask(idx: pd.DatetimeIndex, a, b) -> np.ndarray:
    return (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b or L2.J_END))


def scale(W: dict, states: pd.DataFrame, sec: dict[str, str], agg: pd.Series) -> dict:
    """各年代：IBS「业种 × 日」在状态中的比例、平均几个业种、B1 会买的信号（W2 + C 留一年代）落在状态中的个数（按业种）；
    IBA 状态中占日本交易日的比例与段数、落在状态中的信号个数；W / Jx 同样；1987〜2000。"""
    import combo_all_common as CA
    import loop_r12_trendgate as G12
    D, A = W["D"], W["A"]
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        S = states[window_mask(states.index, a, b)]
        rules = CA.fit_c([D[x] for x in L2.ERAS if x != e])
        X = A[e][CA.apply_c(rules, A[e])]
        g = gated_at(states, sec, X["ticker"].to_numpy(), X["date"].to_numpy())
        by = pd.Series([sec.get(str(t)) for t in X["ticker"].to_numpy()[g]]).value_counts()
        dsc = G12.describe(W, e, agg)
        out[e] = {"sector_day_pct": round(float(S.to_numpy().mean() * 100), 1), "avg_sectors": round(float(S.sum(axis=1).mean()), 2),
                  "signals": int(len(X)), "gated": int(g.sum()), "unmapped": int(sum(1 for t in X["ticker"] if str(t) not in sec)),
                  "by_sector": {str(k): int(v) for k, v in by.items()},
                  "agg_pct": dsc["chop_pct"], "agg_episodes": dsc["episodes"], "agg_gated": int(G12.chop_at(agg, X["date"].to_numpy()).sum())}
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        g = gated_at(states, sec, X["ticker"].to_numpy(), X["date"].to_numpy())
        out[s] = {"signals": int(len(X)), "gated": int(g.sum()), "agg_gated": int(G12.chop_at(agg, X["date"].to_numpy()).sum())}
    S = states[window_mask(states.index, "1987-01-01", "2000-12-31")]
    out["1987-2000"] = {"sector_day_pct": round(float(S.to_numpy().mean() * 100), 1) if len(S) else None}
    return out


# ───────────────────────── 只描述 D1〜D4 ─────────────────────────
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 4) if np.isfinite(f) else None


def us_quarterly() -> pd.DataFrame:
    """美国非金融企业（季度）：icr =（税前利润 + 支付利息）÷ 支付利息（4 季平均的 SAAR）、r = 支付利息 ÷ 债券 + 贷款（4 季平均，%/年）。"""
    from qbreak import factors as F
    q = lambda s: s.groupby(pd.PeriodIndex(s.index, freq="Q")).last()    # noqa: E731
    paid = q(F.fred(US_FRED["paid"], max_age_h=240)) / 1000.0              # 百万 → 十亿美元（SAAR）
    debt = q(F.fred(US_FRED["debt"], max_age_h=240)) / 1000.0
    pbt = q(F.fred(US_FRED["pbt"], max_age_h=240))
    x = pd.DataFrame({"paid": paid, "debt": debt, "pbt": pbt}).dropna()
    x = x.reindex(pd.period_range(x.index.min(), x.index.max(), freq="Q"))
    pm = x["paid"].rolling(4).mean()
    x["icr"] = (x["pbt"] + x["paid"]).rolling(4).mean() / pm.where(pm > 0)
    x["r"] = pm / x["debt"].rolling(4).mean() * 100
    return x


def us_avail(periods) -> pd.DatetimeIndex:
    """美国 Z.1 / NIPA：季末那个月 + 3 个月的月末才用（Z.1 约季末后 10 周、NIPA 利润第二次估计约 2 个月）。"""
    return pd.DatetimeIndex([(p.asfreq("M", "end") + 3).to_timestamp(how="end").normalize() for p in periods])


def bis_dsr(refresh: bool = False) -> pd.DataFrame:
    """BIS 非金融企业债务偿还比率（%，季度 × 国家代码）→ 原文件只在 var/cache/bis/。"""
    from qbreak import paths
    from qbreak.factors import _get
    fp = paths.sub("cache") / "bis" / BIS_FILE
    if refresh or not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(_get(BIS_URL, timeout=120))
    z = zipfile.ZipFile(fp)
    d = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    col = lambda p: next(c for c in d.columns if c.startswith(p))         # noqa: E731
    d = d[d[col("DSR_BORROWERS")].astype(str).str.startswith("N")]
    cty = d[col("BORROWERS_CTY")].astype(str).str.split(":").str[0]
    per = pd.PeriodIndex(d[col("TIME_PERIOD")].astype(str).str.replace("-", ""), freq="Q")
    t = pd.DataFrame({"cty": cty.to_numpy(), "q": per, "v": pd.to_numeric(d[col("OBS_VALUE")], errors="coerce").to_numpy()})
    return t.pivot_table(index="q", columns="cty", values="v").sort_index()


def month_ends(a: str, b: str) -> pd.DatetimeIndex:
    return pd.date_range(a, b, freq="ME")


def fwd_return(close: pd.Series, me: pd.DatetimeIndex, months: int = 12) -> pd.Series:
    """每个月末 → 之后 months 个月的价格涨跌（%）：那个月末（或之前最后一个收盘）到 months 个月之后的月末。"""
    c = close.dropna().sort_index()
    at = c.reindex(c.index.union(me)).ffill().reindex(me)
    later = c.reindex(c.index.union(me + pd.offsets.MonthEnd(months))).ffill().reindex(me + pd.offsets.MonthEnd(months))
    r = (later.to_numpy() / at.to_numpy() - 1) * 100
    ok = (me + pd.offsets.MonthEnd(months)) <= c.index[-1]
    return pd.Series(np.where(ok & (at.index >= c.index[0]), r, np.nan), index=me)


def split_stats(state: pd.Series, y: pd.Series) -> dict:
    """状态中 vs 不在：月数、平均、中位数、差（状态中 − 不在）。"""
    s = state.reindex(y.index).fillna(False).astype(bool)
    v = y.dropna()
    s = s.reindex(v.index)
    on, off = v[s], v[~s]
    m = lambda x: _num(x.mean()) if len(x) else None                       # noqa: E731
    md = lambda x: _num(x.median()) if len(x) else None                    # noqa: E731
    return {"n_on": int(len(on)), "n_off": int(len(off)), "mean_on": m(on), "mean_off": m(off), "med_on": md(on), "med_off": md(off),
            "diff": None if not len(on) or not len(off) else _num(on.mean() - off.mean())}


def gdp4(g: pd.Series, me: pd.DatetimeIndex) -> pd.Series:
    """每个月末 → 那个季度到 4 个季度之后的实际 GDP 增长（%）；没有数据 = NaN。"""
    q = g.groupby(pd.PeriodIndex(g.index, freq="Q")).last()
    pq = pd.PeriodIndex(me, freq="Q")
    a, b = q.reindex(pq).to_numpy(float), q.reindex(pq + 4).to_numpy(float)
    return pd.Series((b / a - 1) * 100, index=me)


def lvl12(s: pd.Series, me: pd.DatetimeIndex) -> pd.Series:
    """每个月末 → 那个月到 12 个月之后的变化（%，月度水平，例：工业生产）；没有数据 = NaN。"""
    m = s.groupby(pd.PeriodIndex(s.index, freq="M")).last()
    pm = pd.PeriodIndex(me, freq="M")
    return pd.Series((m.reindex(pm + 12).to_numpy(float) / m.reindex(pm).to_numpy(float) - 1) * 100, index=me)


def rec12(s: pd.Series, me: pd.DatetimeIndex) -> pd.Series:
    """每个月末 → 之后 12 个月里有没有衰退月（USREC = 1）：100 / 0；12 个月还没过完 = NaN。"""
    m = s.groupby(pd.PeriodIndex(s.index, freq="M")).last()
    pm = pd.PeriodIndex(me, freq="M")
    v = [np.nan if (p + 12) > m.index[-1] else float(m.reindex([p + k for k in range(1, 13)]).fillna(0).max() > 0) * 100 for p in pm]
    return pd.Series(v, index=me)


def segments(state: pd.Series) -> list[str]:
    """月末状态 → 段（YYYY-MM〜YYYY-MM）。"""
    v = state.astype(bool).to_numpy()
    idx = state.index
    out, k = [], 0
    while k < len(v):
        if v[k]:
            j = k
            while j + 1 < len(v) and v[j + 1]:
                j += 1
            out.append(f"{idx[k]:%Y-%m}〜{idx[j]:%Y-%m}")
            k = j + 1
        else:
            k += 1
    return out


def describe_now(df: pd.DataFrame) -> dict:
    """D1 现在的读数 + D2 历史段（只有状态，不看任何收益 → 登记前也可以看）。"""
    from qbreak import factors as F
    from qbreak import invest_flow as IF
    out: dict = {}
    # D1 日本现在
    icr_all, r_all = coverage(group_table(df, [ALL]))
    last = icr_all.dropna().index[-1]
    jp = {"quarter": str(last), "avail": str(IF.avail_month_end(last).date()), "icr": _num(icr_all[last]), "icr_1y": _num(icr_all[last - 4]),
          "r": _num(r_all[last]), "r_1y": _num(r_all[last - 4]), "burden_pct": _num(100.0 / icr_all[last]),
          "agg_squeeze": bool(squeeze_q(icr_all, r_all).get(last, False))}
    secs = []
    for sec, codes in IF.MOF_TSE.items():
        icr, r = coverage(group_table(df, codes))
        st = squeeze_q(icr, r, icr_all)
        secs.append({"sector": sec, "icr": _num(icr.get(last)), "icr_1y": _num(icr.get(last - 4)), "r": _num(r.get(last)),
                     "r_1y": _num(r.get(last - 4)), "state": bool(st.get(last, False))})
    jp["sectors"] = secs
    out["jp_now"] = jp
    # D1 美国现在
    us = us_quarterly()
    ul = us["icr"].dropna().index[-1]
    baa = F.fred("BAA", max_age_h=240)
    baa_q = baa.groupby(pd.PeriodIndex(baa.index, freq="Q")).mean()
    out["us_now"] = {"quarter": str(ul), "avail": str(us_avail([ul])[0].date()), "icr": _num(us["icr"][ul]), "icr_1y": _num(us["icr"][ul - 4]),
                     "burden_pct": _num(100.0 / us["icr"][ul]), "r": _num(us["r"][ul]), "r_1y": _num(us["r"][ul - 4]),
                     "baa_q": _num(baa_q.get(ul)), "baa_last": _num(baa.iloc[-1]), "baa_last_month": f"{baa.index[-1]:%Y-%m}",
                     "refi_gap": _num(baa_q.get(ul) - us["r"][ul]) if ul in baa_q.index else None,
                     "agg_squeeze": bool(squeeze_q(us["icr"], us["r"]).get(ul, False))}
    dsr = bis_dsr()
    dl = dsr.dropna(how="all").index[-1]
    out["bis_now"] = {"quarter": str(dl), "dsr": {c: _num(dsr[c].get(dl)) for c in dsr.columns},
                      "chg_1y": {c: _num(dsr[c].get(dl) - dsr[c].get(dl - 4)) for c in dsr.columns}}
    jst, ust = agg_states(df)
    out["jp_segments"], out["us_segments"] = segments(jst), segments(ust)
    return out


def agg_states(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """全产业「ICR 变差且借款利率上升」的月末状态（日本 1960〜、美国 1953〜；能用的时点）。"""
    icr_all, r_all = coverage(group_table(df, [ALL]))
    us = us_quarterly()
    jst = to_daily(squeeze_q(icr_all, r_all), month_ends("1960-01-31", L2.J_END))
    ust = to_daily(squeeze_q(us["icr"], us["r"]), month_ends("1953-01-31", L2.J_END), avail=us_avail(us.index))
    return jst, ust


def describe_after(df: pd.DataFrame) -> dict:
    """D3 状态中 vs 不在之后的股指 / GDP / 工业生产 / 衰退；D4 BIS 17 国横向（有收益 → 只在登记后的那一次运行里算）。"""
    from qbreak import factors as F
    out: dict = {}
    jst, ust = agg_states(df)
    me_jp, me_us = jst.index, ust.index
    dsr = bis_dsr()
    n225, spx = F.yf_close("^N225", max_age_h=240), F.yf_close("^GSPC", max_age_h=240)
    jgdp, ugdp = F.fred("JPNRGDPEXP", max_age_h=240), F.fred("GDPC1", max_age_h=240)
    iip, rec = F.fred("JPNPROINDMISMEI", max_age_h=240), F.fred("USREC", max_age_h=240)
    out["jp_after"] = {"n225_12m": split_stats(jst, fwd_return(n225, me_jp)), "gdp_4q": split_stats(jst, gdp4(jgdp, me_jp)),
                       "iip_12m": split_stats(jst, lvl12(iip, me_jp))}
    out["us_after"] = {"spx_12m": split_stats(ust, fwd_return(spx, me_us)), "gdp_4q": split_stats(ust, gdp4(ugdp, me_us)),
                       "recession_12m_pct": split_stats(ust, rec12(rec, me_us))}
    # D4 BIS 17 国
    up = (dsr - dsr.shift(4)) > 0
    up = up.where(dsr.notna() & dsr.shift(4).notna(), False)
    bis_av = pd.DatetimeIndex([(p.asfreq("M", "end") + BIS_LAG).to_timestamp(how="end").normalize() for p in up.index])
    rows, pool_on, pool_off = {}, [], []
    for c in up.columns:
        sym = BIS_INDEX.get(c)
        if not sym:
            rows[c] = {"index": None, "note": "没有指数数据"}
            continue
        try:
            px = F.yf_close(sym, max_age_h=240)
        except Exception as ex:                                              # noqa: BLE001
            rows[c] = {"index": sym, "note": f"取不到：{str(ex)[:60]}"}
            continue
        if px.dropna().index[0] > pd.Timestamp(BIS_FULL_FROM):
            rows[c] = {"index": sym, "note": f"指数从 {px.dropna().index[0]:%Y-%m} 起 → 不算"}
            continue
        me = month_ends("1999-01-31", L2.J_END)
        st = to_daily(up[c], me, avail=bis_av)
        y = fwd_return(px, me)
        s = split_stats(st, y)
        rows[c] = {"index": sym, **s}
        v = y.dropna()
        sm = st.reindex(v.index).fillna(False).astype(bool)
        pool_on += list(v[sm])
        pool_off += list(v[~sm])
    out["bis_after"] = rows
    out["bis_pool"] = {"n_on": len(pool_on), "n_off": len(pool_off), "mean_on": _num(np.mean(pool_on)) if pool_on else None,
                       "mean_off": _num(np.mean(pool_off)) if pool_off else None,
                       "countries": [c for c, r in rows.items() if "n_on" in r],
                       "worse_on": [c for c, r in rows.items() if r.get("diff") is not None and r["diff"] < 0]}
    return out


def describe(df: pd.DataFrame) -> dict:
    """D1〜D4（只描述，不参与判定）。"""
    return {**describe_now(df), **describe_after(df)}


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r06_interest.py", "scripts/loop2_common.py",
                                 "scripts/loop_common.py", "scripts/research_loop3.py", "scripts/research_loop2.py",
                                 "scripts/candle_portfolio.py", "scripts/policy_event_data.py", "qbreak/invest_flow.py",
                                 "var/industry_s33.json", "var/policy_extra_pool.json", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def inputs(W: dict | None = None) -> tuple[pd.DataFrame, dict[str, str], pd.Series]:
    days = pd.bdate_range("1985-01-01", L2.J_END)
    df = fetch_mof()
    return sector_states(df, days), ticker_sectors(), agg_daily(df, days)


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    states, sec, agg = inputs(W)
    reg = R2.load_state().get("baseline") or {}
    base, cand, trades = {}, {"IBS": {}, "IBA": {}}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        tk = era_ticks(W, e, states, sec)
        rs = L2.run(W, e, em_tick=tk) if tk else rb
        ra = L2.run(W, e, em_mult=iba_mult(W, e, agg))
        base[e] = {**_acct(rb), "years": rb.get("years")}
        cand["IBS"][e] = {**_acct(rs), "years": rs.get("years")}
        cand["IBA"][e] = {**_acct(ra), "years": ra.get("years")}
        trades[e] = {"B1": rb["n"], "IBS": rs["n"], "IBA": ra["n"], "ticks": len(tk)}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = {"IBS": other_stocks(W, states, sec), "IBA": other_stocks_iba(W, agg)}
    s1 = {k: R2.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "scale": scale(W, states, sec, agg), "desc": describe(fetch_mof()), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def now_lines(d: dict) -> list[str]:
    j, u, b = d["jp_now"], d["us_now"], d["bis_now"]
    L = ["", "## 只描述（不参与判定）", "",
         f"- D1 日本（法人企業統計 資本金 10 億円以上、金融保険以外，{j['quarter']}，{j['avail']} 起可用）：ICR {_f(j['icr'], '{:.1f}')} 倍"
         f"（一年前 {_f(j['icr_1y'], '{:.1f}')} 倍；利息占（営業利益 + 受取利息等）{_f(j['burden_pct'], '{:.1f}')}%）、借款利率 {_f(j['r'], '{:.2f}')}%"
         f"（一年前 {_f(j['r_1y'], '{:.2f}')}%）；全产业「ICR 变差且利率上升」：{'是' if j['agg_squeeze'] else '否'}"]
    on = [s for s in j["sectors"] if s["state"]]
    L.append("  - 现在在状态中的业种（ICR 低于全产业、比一年前低、借款利率比一年前高）：" + ("、".join(
        f"{s['sector']}（ICR {_f(s['icr'], '{:.1f}')} ← {_f(s['icr_1y'], '{:.1f}')} 倍、利率 {_f(s['r'], '{:.2f}')} ← {_f(s['r_1y'], '{:.2f}')}%）" for s in on) or "无"))
    L.append(f"- D1 美国（非金融企业，Z.1 + NIPA，{u['quarter']}，{u['avail']} 起可用）：ICR {_f(u['icr'], '{:.1f}')} 倍（一年前 {_f(u['icr_1y'], '{:.1f}')}；"
             f"利息占税前利润 + 利息 {_f(u['burden_pct'], '{:.1f}')}%）、平均借款利率 {_f(u['r'], '{:.2f}')}%（一年前 {_f(u['r_1y'], '{:.2f}')}%）；"
             f"穆迪 Baa 收益率 同季平均 {_f(u['baa_q'], '{:.2f}')}%（{u['baa_last_month']} {_f(u['baa_last'], '{:.2f}')}%）→ 新借比旧债贵 {_f(u['refi_gap'], '{:+.2f}')} pp；"
             f"全产业「ICR 变差且利率上升」：{'是' if u['agg_squeeze'] else '否'}")
    ds = b["dsr"]
    L.append(f"- D1 BIS 非金融企业债务偿还比率（{b['quarter']}）：" + "、".join(
        f"{c} {_f(ds[c], '{:.1f}')}%（{_f(b['chg_1y'][c], '{:+.1f}')}）" for c in sorted(ds) if ds[c] is not None))
    L.append("- D2 全产业「ICR 变差且借款利率上升」的段（月末、能用的时点）：日本 " + "、".join(d["jp_segments"]) + "；美国 " + "、".join(d["us_segments"]))
    return L


def after_lines(d: dict) -> list[str]:
    L = []
    st = lambda x, u_: (f"状态中 {_f(x['mean_on'], '{:+.1f}')}{u_}（{x['n_on']} 个月）vs 不在 {_f(x['mean_off'], '{:+.1f}')}{u_}（{x['n_off']}）"   # noqa: E731
                        f"→ 差 {_f(x['diff'], '{:+.1f}')}")
    ja, ua = d["jp_after"], d["us_after"]
    L.append(f"- D3 日本之后：日経225 12 个月 {st(ja['n225_12m'], '%')}；实际 GDP 4 个季度（1994〜）{st(ja['gdp_4q'], '%')}；工业生产 12 个月 {st(ja['iip_12m'], '%')}")
    L.append(f"- D3 美国之后：S&P500 12 个月 {st(ua['spx_12m'], '%')}；实际 GDP 4 个季度 {st(ua['gdp_4q'], '%')}；12 个月内有 NBER 衰退的比例 {st(ua['recession_12m_pct'], '%')}")
    bp = d["bis_pool"]
    L.append(f"- D4 BIS 横向（DSR 比一年前高、季末 + 6 个月才用 → 之后 12 个月本国股指，价格）：合计 状态中 {_f(bp['mean_on'], '{:+.1f}')}%（{bp['n_on']} 个国家·月）"
             f" vs 不在 {_f(bp['mean_off'], '{:+.1f}')}%（{bp['n_off']}）；{len(bp['countries'])} 国里状态中更差的 {len(bp['worse_on'])} 国（{'、'.join(bp['worse_on'])}）")
    L.append("  - " + "；".join(f"{c} {r['index']}：{_f(r.get('diff'), '{:+.1f}')} pp" if "n_on" in r else f"{c}：{r['note']}" for c, r in d["bis_after"].items()))
    return L


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    name = {"IBS": "按行业（利息负担比全产业重且在加重的行业不开新仓）", "IBA": "全产业（全产业的利息负担在加重时日本个股一律不开新仓）"}
    L = [f"# 第三个研究循环第 6 轮：借款利率上升、利润越来越盖不住利息 → 不开日本个股新仓 IBS / IBA（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r06_interest.py 开头）", ""]
    for k in IDS:
        s1, os_ = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{name[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(os_['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(os_['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(os_['Jx']['dwin'], '{:+.2f}')} / {_f(os_['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | IBS（Calmar 差） | IBA（Calmar 差） | 个股笔数 B1 → IBS / IBA |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['IBS'][e])}（{_f(res['stage1']['IBS']['d'][e], '{:+.3f}')}） | "
                 f"{cell(res['cand']['IBA'][e])}（{_f(res['stage1']['IBA']['d'][e], '{:+.3f}')}） | {t['B1']} → {t['IBS']} / {t['IBA']} |")
    sc = res["scale"]
    L += ["", "规模与挡掉的（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：IBS「业种 × 日」在状态中 {_f(x['sector_day_pct'], '{:.1f}')}%（平均 {_f(x['avg_sectors'], '{:.2f}')} 个业种），"
                 f"B1 会买的信号 {x['signals']} 个里挡 {x['gated']} 个（" + ("、".join(f"{k} {v}" for k, v in x["by_sector"].items()) or "无")
                 + f"；没有对应 MOF 业种的 {x['unmapped']} 个）；IBA 状态中占日本交易日 {_f(x['agg_pct'], '{:.1f}')}%（{x['agg_episodes']} 段）、挡 {x['agg_gated']} 个")
    for k in IDS:
        for s in ("W", "Jx"):
            o = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：B1 会买的信号 {o['n']} 个，挡掉 {o['gone_n']} 个（胜率 {_f(o['gone_win'], '{:.1f}')}%、每笔 {_f(o['gone_mean'], '{:+.2f}')}%）；"
                     f"保留 {o['kept']} 个 → 胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    L += now_lines(res["desc"]) + after_lines(res["desc"])
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。数据仅对本次取数时点有效。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数规模（不跑账户、不看收益）。"""
    W = L2.load()
    states, sec, agg = inputs(W)
    print(json.dumps(scale(W, states, sec, agg), ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① IBS 要挡的每一对倍数换成 1 → 账户与 B1 逐项相同；② IBA 状态全 False → 同样相同；
    ③ J 的 em_tick 对数 > 0、J 里 IBA 状态中的日本交易日 > 0（不跑 IBS / IBA 本身、不看收益）。"""
    W = L2.load()
    states, sec, agg = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    ones = era_ticks(W, "J", states, sec, f=1.0)
    r1 = L2.run(W, "J", em_tick=ones)
    r0 = L2.run(W, "J", em_mult=iba_mult(W, "J", pd.Series(False, index=agg.index)))
    same1 = all(rb.get(x) == r1.get(x) for x in keys)
    same0 = all(rb.get(x) == r0.get(x) for x in keys)
    days_j = int((iba_mult(W, "J", agg) == 0).sum())
    print(json.dumps({"ibs_ones_same_as_b1": same1, "iba_never_same_as_b1": same0, "ticks_J": len(ones), "iba_zero_days_J": days_j},
                     ensure_ascii=False))
    return 0 if same1 and same0 and len(ones) > 0 and days_j > 0 else 1


def now_only() -> int:
    """D1 + D2（只有状态与现在的读数，不看收益）。"""
    print("\n".join(now_lines(describe_now(fetch_mof()))))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 6 轮：IBS / IBA（利息负担在加重时不开日本个股新仓：按行业 / 全产业）")
    ap.add_argument("--scale", action="store_true", help="只数规模（不算收益）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（J；不看 IBS 的收益）")
    ap.add_argument("--now", action="store_true", help="只算 D1 + D2（现在的读数与历史段，不看收益）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    if a.now:
        return now_only()
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
