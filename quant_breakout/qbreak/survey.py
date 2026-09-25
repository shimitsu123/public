"""survey.py — 威胁指数因子调查：覆盖各经济领域的候选因素（研究见 scripts/threat_factor_survey.py）。

每个因素：领域、中文名、变换（kind）、数据源、发布时滞、方向（sign：乘上后「越高越危险」）、发布地（决定日本 / 美国交易日的可得时点）。
时滞约定（只用当时已公布的数据）：
  d_*（日度）  lag = 营业日数：美国交易日 shift(lag)；日本交易日先取「前一个美国收盘」（发布地 US / CN / KR / 汇率）再 shift(lag)；
               日本发布（財務省 JGB）→ 日本交易日 shift(1)、美国交易日当天可用。
  w_* / m_* / q_*（周 / 月 / 季）lag = 日历日：值在「索引日期 + lag」起可用（月度索引 = 月初、FRED 季度索引 = 季初、短观 = 调查季末）；
               美国发布的序列对日本交易日再多等 1 天。
变换在原始频率上做完再按可得时点对齐到交易日；日度的 60 日变化在交易日网格上算。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .threat import _daily, us_asof_for_jp, weekly_available

# (键, 领域, 中文名, 变换, 数据源, 时滞, 方向, 发布地)
SPECS = [
    ("fed_bs", "货币政策 / 流动性", "美联储资产负债表收缩（13 周）", "w_pct13", ["fred:WALCL"], 2, -1, "US"),
    ("reserves", "货币政策 / 流动性", "银行准备金减少（13 周）", "w_pct13", ["fred:WRESBAL"], 2, -1, "US"),
    ("m2_us", "货币政策 / 流动性", "美国 M2 增速放缓", "m_yoy", ["fred:M2SL"], 58, -1, "US"),
    ("m2_jp", "货币政策 / 流动性", "日本 M2 增速放缓", "m_yoy", ["boj:MD02:MAM1NAM2M2MO"], 45, -1, "JP"),
    ("real_ff", "货币政策 / 流动性", "美国实际政策利率偏高（联邦基金 − CPI 同比）", "m_realff", ["fred:FEDFUNDS", "fred:CPIAUCSL"], 50, 1, "US"),
    ("term_prem", "利率 / 曲线", "美债 10 年期限溢价上升", "d_chg60", ["fred:THREEFYTP10"], 5, 1, "US"),
    ("real10", "利率 / 曲线", "美国 10 年实际利率急升", "d_chg60", ["fred:DFII10"], 1, 1, "US"),
    ("bei_shock", "利率 / 曲线", "通胀预期（10 年 BEI）剧烈变化", "d_abschg60", ["fred:T10YIE"], 1, 1, "US"),
    ("us_long", "财政", "美债 30 年 − 10 年扩大（财政 / 期限风险）", "d_sprchg60", ["fred:DGS30", "fred:DGS10"], 1, 1, "US"),
    ("jgb_super", "财政", "日债 30 年 − 10 年扩大（日本财政风险）", "d_sprchg60", ["mof:30Y", "mof:10Y"], 1, 1, "JP"),
    ("baa_aaa", "信用 / 破产代理", "Baa − Aaa 利差走阔（违约溢价）", "d_sprchg60", ["fred:DBAA", "fred:DAAA"], 1, 1, "US"),
    ("cp_spread", "信用 / 破产代理", "商业票据 − 国库券利差（短期融资压力）", "d_sprlevel", ["fred:DCPF3M", "fred:DTB3"], 3, 1, "US"),
    ("hy_rel", "信用 / 破产代理", "高收益债相对国债下跌（HYG / IEF）", "d_ratiopct60", ["yf:HYG", "yf:IEF"], 0, -1, "US"),
    ("ig_rel", "信用 / 破产代理", "投资级债相对国债下跌（LQD / IEF）", "d_ratiopct60", ["yf:LQD", "yf:IEF"], 0, -1, "US"),
    ("cpi_accel", "通胀", "美国 CPI 同比加速（6 个月）", "m_yoyaccel", ["fred:CPIAUCSL"], 50, 1, "US"),
    ("core_cpi", "通胀", "美国核心 CPI 同比偏高", "m_yoy", ["fred:CPILFESL"], 50, 1, "US"),
    ("jp_cgpi", "通胀", "日本企业物价同比加速（6 个月）", "m_yoyaccel", ["boj:PR01:PRCG20_2200000000"], 45, 1, "JP"),
    ("ip_us", "增长 / 景气", "美国工业生产同比下滑", "m_yoy", ["fred:INDPRO"], 50, -1, "US"),
    ("cfnai", "增长 / 景气", "芝加哥联储全国活动指数走弱（3 个月均值）", "m_ma3", ["fred:CFNAI"], 58, -1, "US"),
    ("philly", "增长 / 景气", "费城联储制造业景气走弱（3 个月均值）", "m_ma3", ["fred:GACDFSA066MSFRBPHI"], 24, -1, "US"),
    ("empire", "增长 / 景气", "纽约联储制造业景气走弱（3 个月均值）", "m_ma3", ["fred:GACDISA066MSFRBNY"], 20, -1, "US"),
    ("cli_us", "增长 / 景气", "OECD 先行指数（美国）6 个月下滑", "m_chg6", ["fred:USALOLITONOSTSAM"], 75, -1, "US"),
    ("cli_jp", "增长 / 景气", "OECD 先行指数（日本）6 个月下滑", "m_chg6", ["fred:JPNLOLITONOSTSAM"], 75, -1, "US"),
    ("ip_jp", "增长 / 景气", "日本制造业生产同比下滑", "m_level", ["fred:JPNPRMNTO01GYSAM"], 75, -1, "US"),
    ("tankan_big", "增长 / 景气", "短观 大企业制造业景气 DI 下降（1 季）", "q_chg1", ["tankan:TK99F1000601GCQ01000"], 5, -1, "JP"),
    ("tankan_small", "增长 / 景气", "短观 中小企业非制造业景气 DI 下降（1 季）", "q_chg1", ["tankan:TK99F2000601GCQ03000"], 5, -1, "JP"),
    ("payrolls", "就业", "美国非农 3 个月增幅放缓", "m_pct3", ["fred:PAYEMS"], 40, -1, "US"),
    ("cont_claims", "就业", "持续领取失业金人数同比上升", "w_yoy", ["fred:CCSA"], 12, 1, "US"),
    ("temp_help", "就业", "临时工就业同比下滑", "m_yoy", ["fred:TEMPHELPS"], 40, -1, "US"),
    ("jolts", "就业", "职位空缺同比下滑", "m_yoy", ["fred:JTSJOL"], 70, -1, "US"),
    ("jp_unemp", "就业", "日本失业率上升（Sahm 型）", "m_sahm", ["fred:LRUNTTTTJPM156S"], 62, 1, "US"),
    ("tankan_emp", "就业", "短观 雇用人员 DI 上升（人手转为过剩，4 季）", "q_chg4", ["tankan:TK99F0000608GCQ00000"], 5, 1, "JP"),
    ("retail", "消费", "美国实际零售同比下滑", "m_yoy", ["fred:RRSFS"], 50, -1, "US"),
    ("umich", "消费", "密歇根消费者信心 6 个月下滑", "m_chg6", ["fred:UMCSENT"], 62, -1, "US"),
    ("cc_jp", "消费", "日本消费者信心 6 个月下滑（OECD）", "m_chg6", ["fred:CSCICP03JPM665S"], 60, -1, "US"),
    ("starts", "住房", "美国新屋开工同比下滑", "m_yoy", ["fred:HOUST"], 50, -1, "US"),
    ("permits", "住房", "美国建筑许可 6 个月下滑", "m_pct6", ["fred:PERMIT"], 50, -1, "US"),
    ("mortgage", "住房", "30 年房贷利率 26 周上升", "w_chg26", ["fred:MORTGAGE30US"], 1, 1, "US"),
    ("homebuild_rel", "住房", "住宅建筑股相对大盘下跌（HGX）", "d_ratiopct60", ["yf:^HGX", "yf:^GSPC"], 0, -1, "US"),
    ("jp_exports", "贸易 / 外需", "日本出口同比下滑", "m_yoy", ["fred:XTEXVA01JPM664S"], 60, -1, "US"),
    ("kr_exports", "贸易 / 外需", "韩国出口同比下滑（全球贸易风向标）", "m_yoy", ["fred:XTEXVA01KRM664S"], 60, -1, "US"),
    ("tpu", "地缘 / 不确定性", "贸易政策不确定性（TPU，3 个月均值）", "m_ma3", ["tpu:TPU"], 40, 1, "US"),
    ("epu_eq", "地缘 / 不确定性", "股市相关政策不确定性（30 日均值）", "c_ma30", ["fred:WLEMUINDXD"], 2, 1, "US"),
    ("em_rel", "全球 / 中国", "新兴市场股相对美股下跌（EEM / SPY）", "d_ratiopct60", ["yf:EEM", "yf:SPY"], 0, -1, "US"),
    ("china_eq", "全球 / 中国", "上证指数 60 日下跌", "d_pct60", ["yf:000001.SS"], 0, -1, "CN"),
    ("korea_eq", "全球 / 中国", "韩国 KOSPI 60 日下跌", "d_pct60", ["yf:^KS11"], 0, -1, "CN"),
    ("cny", "全球 / 中国", "人民币贬值（60 日）", "d_pct60", ["yf:CNY=X"], 0, 1, "US"),
    ("krw", "全球 / 中国", "韩元贬值（60 日）", "d_pct60", ["yf:KRW=X"], 0, 1, "US"),
    ("cli_cn", "全球 / 中国", "OECD 先行指数（中国）6 个月下滑", "m_chg6", ["fred:CHNLOLITONOSTSAM"], 75, -1, "US"),
    ("reer_jp", "汇率", "日元实际有效汇率 3 个月升值", "m_pct3", ["fred:RBJPBIS"], 50, 1, "US"),
    ("audjpy", "汇率", "澳元兑日元下跌（避险 / 套息平仓）", "d_pct60", ["yf:AUDJPY=X"], 0, -1, "US"),
    ("oil_vol", "商品", "原油波动率（OVX）", "d_level", ["yf:^OVX"], 0, 1, "US"),
    ("transports", "运输 / 物流", "道琼斯运输股相对工业股下跌", "d_ratiopct60", ["yf:^DJT", "yf:^DJI"], 0, -1, "US"),
    ("truck", "运输 / 物流", "美国卡车货运量同比下滑", "m_yoy", ["fred:TRUCKD11"], 55, -1, "US"),
    ("semis_rel", "科技周期", "半导体股相对大盘下跌（SOX）", "d_ratiopct60", ["yf:^SOX", "yf:^GSPC"], 0, -1, "US"),
    ("banks_rel", "银行", "银行股相对大盘下跌（BKX）", "d_ratiopct60", ["yf:^BKX", "yf:^GSPC"], 0, -1, "US"),
    ("deposits", "银行", "美国银行存款同比下滑", "w_yoy", ["fred:DPSACBW027SBOG"], 10, -1, "US"),
    ("bank_credit", "银行", "美国银行信贷同比放缓", "w_yoy", ["fred:TOTBKCR"], 10, -1, "US"),
    ("smallcap", "市场内部", "小盘股相对大盘下跌（Russell 2000）", "d_ratiopct60", ["yf:^RUT", "yf:^GSPC"], 0, -1, "US"),
    ("breadth", "市场内部", "等权相对市值加权下跌（RSP / SPY）", "d_ratiopct60", ["yf:RSP", "yf:SPY"], 0, -1, "US"),
    ("defensive", "市场内部", "防御板块跑赢周期板块（XLU+XLP / XLY+XLI）", "d_ratio2pct60", ["yf:XLU", "yf:XLP", "yf:XLY", "yf:XLI"], 0, 1, "US"),
    ("vvix", "市场内部", "波动率的波动率（VVIX）", "d_level", ["yf:^VVIX"], 0, 1, "US"),
    ("cape", "估值", "Shiller CAPE 偏高", "m_level", ["shiller:CAPE"], 45, 1, "US"),
    ("buffett", "估值", "美股总市值 / GDP 偏高", "q_ratio", ["fred:NCBEILQ027S", "fred:GDP"], 165, 1, "US"),
    ("profits", "企业盈利", "美国企业利润同比下滑", "q_yoy", ["fred:CP"], 150, -1, "US"),
]
# 现行 v1 / v2 / v3 因素所属领域（调查表里一起列出）
EXISTING_DOMAIN = {
    "vix": "市场波动", "vix_d20": "市场波动", "rvol": "市场波动", "vix_term": "市场波动", "move": "市场波动", "skew": "市场波动",
    "yen_vol": "市场波动",
    "credit": "信用 / 破产代理", "nfci": "信用 / 破产代理", "stlfsi": "信用 / 破产代理", "sloos": "信用 / 破产代理",
    "delinq": "信用 / 破产代理", "chargeoff": "信用 / 破产代理", "tankan_lend": "信用 / 破产代理", "tankan_cash": "信用 / 破产代理",
    "curve": "利率 / 曲线", "curve2": "利率 / 曲线", "rates": "利率 / 曲线", "rates2": "利率 / 曲线", "jgb": "利率 / 曲线",
    "fed": "货币政策 / 流动性", "boj": "货币政策 / 流动性",
    "oil": "商品", "cu_au": "商品", "gold": "商品", "gold_silver": "商品", "copper": "商品", "natgas": "商品", "grains": "商品",
    "commod": "商品", "commod_vol": "商品", "jp_lng": "商品",
    "jobs": "就业", "claims": "就业", "dd52": "市场趋势", "trend": "市场趋势", "mom20": "市场趋势",
    "dollar": "汇率", "yen": "汇率", "gpr": "地缘 / 不确定性", "gpr_jump": "地缘 / 不确定性", "epu": "地缘 / 不确定性",
    "gpr_jp": "地缘 / 不确定性"}
KEYS = [s[0] for s in SPECS]
LABELS = {s[0]: s[2] for s in SPECS}
DOMAIN = {s[0]: s[1] for s in SPECS}


def sources() -> set[str]:
    return {src for s in SPECS for src in s[4]}


def load_raw(srcs: set[str] | None = None) -> dict[str, pd.Series]:
    """下载（有缓存）调查用的全部原始序列：{数据源: 序列}。"""
    from . import factors as F
    out = {}
    jgb = None
    for src in sorted(srcs or sources()):
        kind, _, ident = src.partition(":")
        if kind == "fred":
            out[src] = F.fred(ident)
        elif kind == "yf":
            out[src] = F.despike(F.yf_close(ident))
        elif kind == "boj":
            db, code = ident.split(":")
            out[src] = F.boj_monthly(db, code, "200304" if db == "MD02" else "196001")
        elif kind == "tankan":
            out[src] = F.tankan(ident)
        elif kind == "mof":
            jgb = jgb if jgb is not None else F.jgb_curve()
            out[src] = jgb[ident].dropna()
        elif kind == "tpu":
            out[src] = F.tpu_monthly()
        elif kind == "shiller":
            out[src] = F.shiller_cape()
    return out


def _native(kind: str, xs: list[pd.Series]) -> pd.Series:
    """周 / 月 / 季序列在原始频率上的变换（索引不变）。"""
    x = xs[0].dropna()
    if kind == "w_pct13":
        return x / x.shift(13) - 1
    if kind == "w_yoy":
        return x / x.shift(52) - 1
    if kind == "w_chg26":
        return x - x.shift(26)
    if kind == "m_yoy":
        return x / x.shift(12) - 1
    if kind == "m_yoyaccel":
        y = x / x.shift(12) - 1
        return y - y.shift(6)
    if kind == "m_ma3":
        return x.rolling(3).mean()
    if kind == "m_chg6":
        return x - x.shift(6)
    if kind == "m_pct6":
        return x / x.shift(6) - 1
    if kind == "m_pct3":
        return x / x.shift(3) - 1
    if kind == "m_level":
        return x
    if kind == "m_sahm":
        a = x.rolling(3).mean()
        return a - a.rolling(12).min()
    if kind == "m_realff":
        ff = xs[0].dropna()
        cpi = xs[1].dropna()
        return (ff - (cpi / cpi.shift(12) - 1) * 100).dropna()
    if kind == "q_chg1":
        return x - x.shift(1)
    if kind == "q_chg4":
        return x - x.shift(4)
    if kind == "q_yoy":
        return x / x.shift(4) - 1
    if kind == "q_ratio":
        y = xs[1].dropna()
        return (x / y.reindex(x.index)).dropna()
    if kind == "c_ma30":                                   # 日历日度（每天都有值）的 30 日均值
        return x.rolling(30, min_periods=20).mean()
    raise ValueError(kind)


def _asof_days(s: pd.Series, days: pd.DatetimeIndex, jp_market: bool, country: str, lag: int) -> pd.Series:
    """日度序列 → 交易日（按发布地与营业日时滞）。"""
    if jp_market and country != "JP":
        v = us_asof_for_jp(s, days)                        # 日本交易日：用前一个海外收盘
        return v.shift(lag)
    if jp_market and country == "JP":
        return _daily(s, days).shift(max(lag, 1))
    if country == "JP":                                     # 日本发布、美国交易日：当天（日本早于美国）
        return _daily(s, days)
    return _daily(s, days).shift(lag)


def features(days: pd.DatetimeIndex, raw: dict[str, pd.Series], jp_market: bool) -> pd.DataFrame:
    """调查因素在该市场交易日上的值（已乘方向：越高越危险）。"""
    out = {}
    for key, _, _, kind, srcs, lag, sign, country in SPECS:
        xs = [raw.get(s) for s in srcs]
        if any(x is None or x.dropna().empty for x in xs):
            continue
        if kind.startswith("d_"):
            v = [_asof_days(x, days, jp_market, country, lag) for x in xs]
            if kind == "d_chg60":
                f = v[0] - v[0].shift(60)
            elif kind == "d_abschg60":
                f = (v[0] - v[0].shift(60)).abs()
            elif kind == "d_pct60":
                f = v[0] / v[0].shift(60) - 1
            elif kind == "d_level":
                f = v[0]
            elif kind == "d_sprchg60":
                sp = v[0] - v[1]
                f = sp - sp.shift(60)
            elif kind == "d_sprlevel":
                f = v[0] - v[1]
            elif kind == "d_ratiopct60":
                r = v[0] / v[1]
                f = r / r.shift(60) - 1
            elif kind == "d_ratio2pct60":
                r = (v[0] + v[1]) / (v[2] + v[3])
                f = r / r.shift(60) - 1
            else:
                raise ValueError(kind)
        else:
            nat = _native(kind, xs).dropna()
            extra = 1 if (jp_market and country == "US") else 0
            f = weekly_available(nat, days, lag + extra)
        out[key] = f * sign
    return pd.DataFrame(out, index=days)


def stale(raw: dict[str, pd.Series], today: pd.Timestamp, max_age_days: int = 200) -> dict[str, str]:
    """数据源已停更（最后一个值早于 today − max_age_days）的因素：{键: 最后日期}。季度序列放宽到 300 天。"""
    out = {}
    for key, _, _, kind, srcs, _, _, _ in SPECS:
        for s in srcs:
            x = raw.get(s)
            if x is None or x.dropna().empty:
                out[key] = "取不到"
                continue
            last = x.dropna().index[-1]
            lim = 300 if kind.startswith("q_") else max_age_days
            if last < today - pd.Timedelta(days=lim):
                out[key] = str(last.date())
    return out


def readings(F: dict, raw: dict[str, pd.Series], sel: dict[str, list[str]], a0_cols: dict[str, list[str]]) -> dict:
    """日报用：各领域当前的危险度百分位（领域内不在 A0 的因素平均）与组合 S（A0 + 调查选入因素）的最新读数（前瞻记录）。
    F = threat.build_all(...)；sel / a0_cols：{"US": [...], "JP": [...]}。"""
    from .threat import expanding_pct
    dom = {**EXISTING_DOMAIN, **DOMAIN}
    out = {}
    for m in ("US", "JP"):
        raw_ex, _ = F[m]
        feats = pd.concat([raw_ex, features(raw_ex.index, raw, jp_market=(m == "JP"))], axis=1)
        a0 = [c for c in a0_cols[m] if c in feats]
        others = [c for c in feats.columns if c not in a0 and c in dom]
        pct = pd.DataFrame({c: expanding_pct(feats[c]) for c in a0 + others})
        s_cols = a0 + [c for c in sel.get(m, []) if c in pct]
        s = pct[s_cols].mean(axis=1) * 100
        s = s.where(pct[s_cols].notna().sum(axis=1) >= max(1, len(s_cols) // 2))
        last = pct.iloc[-1]
        doms = {}
        for c in others:
            if last[c] == last[c]:
                doms.setdefault(dom[c], []).append(float(last[c]))
        out[m] = {"date": str(pct.index[-1].date()), "S": round(float(s.iloc[-1]), 1) if s.iloc[-1] == s.iloc[-1] else None,
                  "domains": {d: round(float(np.mean(v)) * 100) for d, v in doms.items()}}
    return out


def survey_selection() -> tuple[dict, dict]:
    """调查研究的结果：({"US"/"JP": 选入 S 的因素}, {"US"/"JP": {领域: 分类}})；没有研究结果时为空。"""
    from . import paths
    from .utils import read_json
    r = read_json(paths.out_dir() / "threat_factor_survey.json", {}) or {}
    sel = {m: (r.get(m) or {}).get("selected") or [] for m in ("US", "JP")}
    cls = {m: {d: v.get("class") for d, v in ((r.get(m) or {}).get("domains") or {}).items()} for m in ("US", "JP")}
    return sel, cls


# ═══════════ 日経前瞻观察（用户 2026-09-25 要求；规则见 scripts/jp_watch_review.py，只从该日起记录）═══════════
# 美股的「金银比 + 商品波动」在日経历史上无效（两段 AUC 约 0.59 / 0.50、0.53 / 0.47）→ 按同一挑法，用因子调查里
# 对日経两段都有增益的因素（停更的 OECD 中国先行指数除外）组成 Wj；美股那一对放在日経上作对照（W2）。
JP_WATCH = ["em_rel", "real10", "tankan_big", "tankan_small", "claims", "breadth", "boj", "jp_cgpi"]


def jp_watch_rows(F: dict, raw: dict[str, pd.Series], n: int = 5) -> list[dict]:
    """最近 n 个日本交易日的日経观察读数：Wj（8 个因素）与 W2（金银比 + 商品波动）及各自在自身历史里的百分位，A0 作对照。"""
    from .threat import JP_COLS, _eq, expanding_pct
    raw_ex, _ = F["JP"]
    feats = pd.concat([raw_ex, features(raw_ex.index, raw, jp_market=True)], axis=1)
    feats = feats.loc[:, ~feats.columns.duplicated()]
    wj_cols = [c for c in JP_WATCH if c in feats]
    pct = pd.DataFrame({c: expanding_pct(feats[c]) for c in dict.fromkeys(wj_cols + ["gold_silver", "commod_vol"] + JP_COLS)})
    wj = _eq(pct[wj_cols])
    w2 = pct[["gold_silver", "commod_vol"]].mean(axis=1, skipna=False) * 100
    a0 = _eq(pct[JP_COLS])
    df = pd.DataFrame({"Wj": wj, "Wj_pct": expanding_pct(wj) * 100, "W2": w2, "W2_pct": expanding_pct(w2) * 100,
                       "A0": a0, "A0_pct": expanding_pct(a0) * 100})
    for c in wj_cols:
        df[f"p_{c}"] = pct[c] * 100
    for c in wj_cols:                                                     # 现行 A0 再加这一个因素（等权；前瞻对照用，2026-09-25 补登）
        df[f"A0+{c}"] = _eq(pct[JP_COLS + [c]])
    df["A0+Wj"] = _eq(pct[JP_COLS + wj_cols])                             # 现行 A0 再加 Wj 全部因素（等权；前瞻对照用，2026-09-25 补登）
    r = lambda v: round(float(v), 2) if v == v else None                              # noqa: E731
    return [{"date": str(d.date()), **{k: r(v) for k, v in row.items()}} for d, row in df.dropna(subset=["Wj"]).tail(n).iterrows()]
