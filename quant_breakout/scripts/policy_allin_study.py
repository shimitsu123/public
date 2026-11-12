"""policy_allin_study.py — 去掉每只 25% 的上限：候选股票的买点与「政策 / 发展方向」的相关性调查，特别相关的就全仓（登记检验）。
（2026-10-06 用户：「进行取消25%规定，进行候选股票买点相关性调查 结合当前政策和发展方向等等 如果什么股票特别相关就可以直接全买那个的研究」）
规则先提交（登记）再运行一次；看到结果之后不改规则。

〇 已经知道的（不重复做；照实写）
  1 去掉 25% 上限、资金自由分配（2026-09-30，scripts/free_alloc_study.py）：按候选数 / 波动 / 半凯利 / 全仓一只 F1〜F5 都不如现行，
    随机 f 安慰剂的中位也低于现行，集中只在 2001〜2006 的全面牛市里赚；半凯利只有 E 12% / J 5%（现行 25% 已偏大）→ 无条件的集中不行。
    这次的新东西：只在「特别相关」（政策 / 主线）时集中，其余照旧 25%。
  2 时代主线（12-1 个月最强的业种）在业种层面有证据（日本比等权 +4.7〜4.9% / 年，2026-09-27 era_study）；但「只买领先一半业种的突破」
    （evolve_study V5）E 0.359 / J 0.344 不如现行 0.388 / 0.389；与主线篮子相关高的票，大跌后的反弹 / 暂时顶后的下跌都不更强（2026-09-29）。
  3 政策：以前只有「事件反应库」G1（日银 / Fed / 关税 / 半导体补助 …，只描述 + 前向记录），没有把「产业政策点名的业种」放到买点上检验过 → 新。

一 基准 B4 = B3 + TBF（模拟盘 2026-10-05 收盘的决策起的规则；规则指纹 1241753c8f2529c6）：scripts/loop10_common.load（B3 + Zx）上，
  TBF 用研究同一套「最像」旗子（scripts/turn_shape_combo.py 的缓存）挡（em_tick 0）。先决条件：B4 重算 = turn_shape_combo 结果文件里 TBF 的账户
  （三个年代 Calmar 差 ≤ 0.0005）、规则指纹 = 1241753c8f2529c6、「f ≡ 25% + 去掉上限」的账户 = B4（逐项相同）。

二 相关性（只用信号日收盘为止已知的；三种，各自独立算）
  M 主线：信号日那天，东证 33 业种（J-Quants 銘柄マスタ 2016-10〜2026-09 月末快照里这只票最后一次的 S33；没有的票不计）的 12-1 个月涨幅
    （收盘向前填 ≤ 5 天后，第 −21 个交易日 ÷ 第 −252 个交易日 − 1，与 qbreak/theme_monitor 的 r12 同口径）按业种等权平均（≥ 3 只有值），
    排名前 7 的业种 =「主线」（与日报「时代主线：业种前 7」同一口径）；这只票的业种在主线里 → M。
    参照的票：Z = 日経225（今天）+ Zx，E = 日経225 + W，J = 时点 TOPIX 1000（U2，那一天是成员的）。
    登记前只看了个数（没有任何结果）：前 3 时每个年代只有 4〜7 个信号被标为 M（检验不了）→ 改成前 7。
  P 政策：var/industrial_policy.csv（登记时冻结，48 条：2001〜2026 政府 / 阁议决定、法律成立、补助等点名产业的政策；日期 + 出处 + 点名的产业 → 东证 33 业种；
    2026-10-06 联网核对，仅对检索时点有效）。只用 focus = 1 的 22 条「专门针对一个产业的决定」（IT 战略、机器人新战略、碳中和宣言、半导体 / 数字产业战略、
    半导体补助、安保三文件、GX 基本方针、能源基本计划、AI 法 / AI 基本计划、造船路线图 / 基金、防卫装备转移）；
    综合性的成长战略、经济对策、骨太、「17 个战略领域」这类一次点名十几个业种的（focus = 0）只记录、不算（点名太宽 → 不是「特别相关」）。
    信号日之前 1〜365 天内（不含信号日当天）被 focus = 1 的决定点名的业种 → P。
  R 相关：信号日为止 250 个交易日（≥ 200 天两边都有值），这只票的日收益与「主线篮子」（那天主线 3 个业种的参照票等权、不含自己）的相关系数，
    在当天的排名池（日経225 信号 = 日経225；池子信号 = 那个池子的票）里排百分位；> 90% → R。
三 候选（只换这只票的预算：预算 = 权益 × f × 同一套倍数（宏观 / 判断层，上限 1），f ≤ 100%、不借钱；名额 4、一手、现金照旧）
  A1 主线全仓：M → f = 100%，其余 25%。     A2 政策全仓：P → 100%，其余 25%。     A3 主线且政策：M ∧ P → 100%，其余 25%。
  A4 相关全仓：R → 100%，其余 25%。         A5 只买相关的并全仓：M ∨ P → 100%，其余不买（0）。     TBF 挡的照旧不买（0）。
  实现：研究引擎 cfg_over(position_pct 1.0, max_position_pct 1.0) + em_tick{(票, 信号日): f}，每个 W2 信号都给 f（缺一个就停）。
四 判定（全部满足才「通过」；运行前写定）
  能检验的年代：E、J 里 TBF 没挡的日経225 W2 信号被这个候选标为「相关」的 ≥ 10 个（登记前个数，见 sim_changes）；E、J 都不能检验 →「无法检验」（不通过）。
  a 账户：能检验的年代 Calmar ≥ B4 + 0.02 且最大回撤不比 B4 深 2 pp 以上；其余年代（含 Z）Calmar ≥ B4 − 0.02。
  b 不是「集中」本身的功劳：能检验的年代 Calmar > 安慰剂 95 分位（同一年代、同样多的信号随机全仓，其余同候选；E / J 各 200 次、Z 100 次只描述）。
  c 真的用上了：能检验的年代账户 ≥ 20 笔、其中全仓的 ≥ 5 笔。
  d 相关性本身有信息：能检验的年代对应的池子（E → W 2006〜2016、J → Jx 2022-01〜）里 B4 会买的信号（W2 + 那一折的 C，假想单笔 X6）
    「相关的 − 不相关的」每笔平均 ≥ 0（每组 ≥ 10 个；A5 = M ∨ P、A3 = M ∧ P）。
  只有一个年代能检验时照样判，但写明「只有 E / J 一个年代能检验」（证据弱一级）。
  多个通过：按 min(E, J 的 Calmar 提高) 取 1 个。「通过」也只是提议：先前向记录；进模拟盘 / 执行器要用户另外确认（全仓一只的回撤风险另写）。
  另报「收益率优先」读法（只描述）：E、J 年化 ≥ B4 + 2 pp 且回撤不深 5 pp 以上、Z 年化 ≥ B4 − 1 pp。
五 事前预期（运行前写）：A1 / A4 不过（〇 2）；A2 在 2013 年以前几乎不起作用、2021 年以后点名的业种很宽 → E 不到 +0.02 或 b 不过；
  A3 信号太少 → c 不过；A5 笔数少、回撤深 → a 或 c 不过；「通过」约 5%。最可能：全仓让 J 的年化更高但回撤更深，Calmar 不过、安慰剂也差不多。
六 另报（只描述）：相关性调查 —— 日経225 全部 W2 信号（三个年代）与三个池子里 M / P / R 各自「是 / 否」的个数、胜率、每笔；B4 实际成交的笔里相关的占比；
  各候选全仓的笔数 / 每笔 / 胜率、资金占用；今天（数据最后一天）的主线 3 个业种、政策点名的业种（var/industrial_policy.csv，截至 2026-10-05）。
七 局限：今天的日経225（幸存者偏差）；Z / E 的业种分类用 2016-10 以后的快照（之前退市的票不计入业种平均）；J-Quants 行情从 2016-09 开始 →
  J 的 12-1 个月动量 2017-09 以后、250 天相关 2017-07 以后才算得出（之前的信号当「不相关」= 25%）；政策表是人工整理的（只收官方出处或主要报道可查的决定；
  经产省页面 403 的 3 条只核到 URL 日期；映射到 33 业种是粗的，例如「半导体」= 電気機器）；调整后价、税前；不加仓不减仓。
  模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/policy_allin_study.md / .json（只有统计，不含个股代码）。
  python scripts/policy_allin_study.py --prep   （只数个数：每个年代 / 池子被标为 M / P / R 的信号有多少，不算任何结果）
  python scripts/policy_allin_study.py --run    （登记之后只运行一次）
"""
from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

IDS = ("A1", "A2", "A3", "A4", "A5")
LABEL = {"A1": "主线全仓", "A2": "政策全仓", "A3": "主线且政策全仓", "A4": "相关全仓", "A5": "只买相关的并全仓"}
REL = {"A1": "M", "A2": "P", "A3": "MP", "A4": "R", "A5": "MorP"}             # 哪种相关性
OTHERS_F = {"A1": 0.25, "A2": 0.25, "A3": 0.25, "A4": 0.25, "A5": 0.0}         # 不相关的信号的 f
ERAS = ("Z", "E", "J")
POOLS = (("W", "E"), ("Jx", "J"), ("Zx", "Z"))                               # (池子, 用哪个年代的参照票 / C 的那一折)
TOP_IND, MIN_MEMBERS = 7, 3
MOM_FAR, MOM_NEAR, FFILL_MAX = 252, 21, 5
POLICY_DAYS = 365
CORR_N, CORR_MIN, CORR_TOP = 250, 200, 0.90
F_NOW, F_ALL = 0.25, 1.0
CFG_FREE = {"position_pct": 1.0, "max_position_pct": 1.0}
PLACEBO = {"Z": 100, "E": 200, "J": 200}
SEED = 20261006
CAL_UP, DD_TOL, Z_TOL, MIN_TRADES, MIN_ALLIN, ACTIVE_MIN = 0.02, 2.0, 0.02, 20, 5, 10
POOL_MIN, JX_FROM = 10, "2022-01-01"
RET_UP, RET_DD_TOL, RET_Z_TOL = 2.0, 5.0, 1.0
FP = "1241753c8f2529c6"                                                      # B4 = B3 + TBF 的模拟盘规则指纹
B4_TOL = 0.0005
POLICY_FILE = "industrial_policy.csv"
PREP_CACHE = "policy_allin_prep.pkl"
OUT_MD, OUT_JSON = "policy_allin_study.md", "policy_allin_study.json"
EXCLUDE_S33 = {"その他", "-", ""}                                             # ETF / REIT 等（不是 33 业种）


# ───────────────────────── 业种、主线、政策、相关（纯函数，有测试） ─────────────────────────
def norm_s33(s) -> str:
    """业种名统一写法：J-Quants 銘柄マスタ有的用半角中点「･」（情報･通信業），有的用全角「・」（水産・农林業）→ 一律全角「・」。"""
    return str(s).replace("\uff65", "\u30fb").strip()


def s33_map(master_dir) -> dict[str, str]:
    """J-Quants 銘柄マスタ的月末快照（日期顺序）→ {"7203.T": "輸送用機器"}；后面的快照覆盖前面的（= 最后一次出现时的分类）。"""
    out: dict[str, str] = {}
    for fp in sorted(Path(master_dir).glob("*.csv")):
        df = pd.read_csv(fp, usecols=["Code", "S33Nm"], dtype=str)
        for c, s in zip(df["Code"], df["S33Nm"]):
            if isinstance(c, str) and len(c) >= 4 and isinstance(s, str) and norm_s33(s) not in EXCLUDE_S33:
                out[c[:4] + ".T"] = norm_s33(s)
    return out


def mom_12_1(C: pd.DataFrame) -> pd.DataFrame:
    """日期 × 票 的收盘 → 12-1 个月涨幅（向前填 ≤ 5 天；第 −21 ÷ 第 −252 个交易日 − 1）。"""
    Cf = C.ffill(limit=FFILL_MAX)
    with np.errstate(invalid="ignore", divide="ignore"):
        return Cf.shift(MOM_NEAR) / Cf.shift(MOM_FAR) - 1


def industry_scores(R: pd.DataFrame, ind_of: dict, member: pd.DataFrame | None = None, min_members: int = MIN_MEMBERS) -> pd.DataFrame:
    """12-1 个月涨幅（日期 × 票）→ 日期 × 业种 的等权平均（那天是成员、有值的票 ≥ min_members 才算，否则 NaN）。没有业种的票不计。"""
    if member is not None:
        R = R.where(member.reindex(index=R.index, columns=R.columns).fillna(False).astype(bool))
    groups: dict[str, list] = {}
    for t in R.columns:
        s = ind_of.get(t)
        if s:
            groups.setdefault(s, []).append(t)
    out = {}
    for s, cols in sorted(groups.items()):
        X = R[cols]
        n = X.notna().sum(axis=1)
        out[s] = X.mean(axis=1).where(n >= min_members)
    return pd.DataFrame(out, index=R.index)


def top_industries(scores: pd.DataFrame, k: int = TOP_IND) -> pd.Series:
    """每一天：分数最高的 k 个业种（同分按业种名）→ frozenset；那天有分数的业种不足 k 个 → 有几个算几个。"""
    out = {}
    cols = list(scores.columns)
    for d, row in scores.iterrows():
        v = row.dropna()
        if not len(v):
            out[d] = frozenset()
            continue
        order = sorted(v.index, key=lambda s: (-float(v[s]), cols.index(s)))
        out[d] = frozenset(order[:k])
    return pd.Series(out, dtype=object)


def load_policy(path, focus_only: bool = True) -> pd.DataFrame:
    """var/industrial_policy.csv → DataFrame（date: Timestamp、s33_list: list[str]）；focus_only = 只要 focus = 1 的（P 用的）。"""
    df = pd.read_csv(path, dtype=str).fillna("")
    if focus_only:
        df = df[df["focus"].astype(str).str.strip() == "1"].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["s33_list"] = [[norm_s33(x) for x in s.split(";") if x.strip()] for s in df["s33"]]
    return df.sort_values("date").reset_index(drop=True)


def policy_active(table: pd.DataFrame, ind: str | None, d, days: int = POLICY_DAYS) -> bool:
    """信号日 d 之前 1〜days 天内（不含 d 当天）有政策点名了业种 ind。"""
    if not ind:
        return False
    d = pd.Timestamp(d)
    m = (table["date"] < d) & (table["date"] >= d - pd.Timedelta(days=days))
    return any(ind in lst for lst in table.loc[m, "s33_list"])


def policy_industries(table: pd.DataFrame, d, days: int = POLICY_DAYS) -> list[str]:
    d = pd.Timestamp(d)
    m = (table["date"] < d) & (table["date"] >= d - pd.Timedelta(days=days))
    return sorted({s for lst in table.loc[m, "s33_list"] for s in lst})


def corr_pct(Rd: pd.DataFrame, d, basket: list[str], rank_cols: list[str], n: int = CORR_N, min_n: int = CORR_MIN) -> pd.Series:
    """信号日 d 为止 n 个交易日：rank_cols 每只票的日收益 与 篮子（basket 等权、不含自己）的相关 → 在 rank_cols 里的百分位（平均名次 ÷ 个数）。"""
    W = Rd.loc[:pd.Timestamp(d)].iloc[-n:]
    rank_cols = [c for c in rank_cols if c in W.columns]
    basket = [c for c in basket if c in W.columns]
    if not len(W) or not basket or not rank_cols:
        return pd.Series(np.nan, index=rank_cols, dtype=float)
    B = W[basket].to_numpy(float)
    ssum = np.nansum(B, axis=1)
    scnt = np.isfinite(B).sum(axis=1).astype(float)
    X = W[rank_cols].to_numpy(float)
    inb = np.isin(np.asarray(rank_cols), np.asarray(basket))[None, :]
    num = ssum[:, None] - np.where(inb, np.nan_to_num(X, nan=0.0), 0.0)
    den = scnt[:, None] - np.where(inb, np.isfinite(X), False)
    with np.errstate(invalid="ignore", divide="ignore"):
        bj = np.where(den >= 1, num / np.where(den >= 1, den, 1), np.nan)
    ok = np.isfinite(X) & np.isfinite(bj)
    cnt = ok.sum(axis=0)
    Xz, Bz = np.where(ok, X, 0.0), np.where(ok, bj, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx, mb = Xz.sum(axis=0) / cnt, Bz.sum(axis=0) / cnt
        cx, cb = np.where(ok, X - mx, 0.0), np.where(ok, bj - mb, 0.0)
        c = (cx * cb).sum(axis=0) / np.sqrt((cx ** 2).sum(axis=0) * (cb ** 2).sum(axis=0))
    c = np.where(cnt >= min_n, c, np.nan)
    return pd.Series(c, index=rank_cols, dtype=float).rank(pct=True)


def flag_rows(tickers, dates, ind_of: dict, top: pd.Series, table: pd.DataFrame, rpct_of) -> pd.DataFrame:
    """信号（票, 信号日）→ ind / M / P / R（rpct_of(票, 日) → 百分位或 NaN）/ MP / MorP。"""
    rows = []
    tix = pd.DatetimeIndex(top.index)
    for t, d in zip(tickers, pd.to_datetime(np.asarray(dates))):
        ind = ind_of.get(str(t))
        i = int(tix.searchsorted(d, side="right")) - 1
        top_d = top.iloc[i] if i >= 0 and tix[i] == d else frozenset()
        m = bool(ind is not None and ind in top_d)
        p = policy_active(table, ind, d)
        rp = rpct_of(str(t), d)
        r = bool(rp is not None and np.isfinite(rp) and rp > CORR_TOP)
        rows.append({"ticker": str(t), "date": d, "ind": ind, "M": m, "P": p, "R": r, "rpct": rp, "MP": m and p, "MorP": m or p})
    return pd.DataFrame(rows)


def em_for(S: pd.DataFrame, tbf: np.ndarray, rel: np.ndarray, others: float) -> dict:
    """这个年代全部 W2 信号（与 loop9_common.signals 同序）→ em_tick {(票, 信号日): f}：TBF 挡的 0、相关的 100%、其余 others。"""
    out = {}
    for t, d, g, r in zip(S["ticker"], pd.to_datetime(S["date"]), np.asarray(tbf, bool), np.asarray(rel, bool)):
        out[(str(t), pd.Timestamp(d))] = 0.0 if g else (F_ALL if r else float(others))
    return out


def placebo_rel(tbf: np.ndarray, n_rel: int, rng: np.random.Generator) -> np.ndarray:
    """安慰剂：TBF 没挡的信号里随机挑 n_rel 个当「相关」。"""
    tbf = np.asarray(tbf, bool)
    idx = np.flatnonzero(~tbf)
    out = np.zeros(len(tbf), bool)
    if n_rel > 0 and len(idx):
        out[rng.choice(idx, size=min(n_rel, len(idx)), replace=False)] = True
    return out


def judge(cand: dict, base: dict, pl95: dict, allin: dict, pools: dict, active: dict) -> dict:
    """四 a〜d → {ok, fails, gain, active}。cand / base = {年代: 账户}；pl95 = {年代: 安慰剂 Calmar 95 分位}；allin = {年代: 全仓的笔数}；
    pools = {"W": {...}, "Jx": {...}}（每个：n_rel / n_not / diff）；active = {年代: 能不能检验（登记前个数 ≥ 10）}。"""
    f = []
    act = [e for e in ("E", "J") if active.get(e)]
    if not act:
        return {"ok": False, "fails": ["E、J 都不能检验（被标为相关的信号都 < 10 个）→ 无法检验"], "gain": None, "active": act}
    for e in ("Z", "E", "J"):
        x, y = cand.get(e) or {}, base.get(e) or {}
        if None in (x.get("calmar"), y.get("calmar"), x.get("dd"), y.get("dd")):
            f.append(f"a {e} 账户没有值")
            continue
        if e in act:
            if x["calmar"] < y["calmar"] + CAL_UP - 1e-12:
                f.append(f"a {e} Calmar {x['calmar']:.3f} < B4 {y['calmar']:.3f} + {CAL_UP}")
            if x["dd"] < y["dd"] - DD_TOL - 1e-12:
                f.append(f"a {e} 回撤 {x['dd']:.2f}% 比 B4 {y['dd']:.2f}% 深 {DD_TOL:.0f} pp 以上")
            p = pl95.get(e)
            if p is None or not x["calmar"] > p:
                f.append(f"b {e} Calmar {x['calmar']:.3f} ≤ 安慰剂 95 分位 {('—' if p is None else f'{p:.3f}')}")
            if (x.get("n") or 0) < MIN_TRADES:
                f.append(f"c {e} 账户只有 {x.get('n') or 0} 笔（< {MIN_TRADES}）")
            if (allin.get(e) or 0) < MIN_ALLIN:
                f.append(f"c {e} 全仓的只有 {allin.get(e) or 0} 笔（< {MIN_ALLIN}）")
        elif x["calmar"] < y["calmar"] - Z_TOL - 1e-12:
            f.append(f"a {e} Calmar {x['calmar']:.3f} < B4 {y['calmar']:.3f} − {Z_TOL}（不能检验的年代只要求不差）")
    for s_, e in (("W", "E"), ("Jx", "J")):
        if e not in act:
            continue
        q = pools.get(s_) or {}
        if (q.get("n_rel") or 0) < POOL_MIN or (q.get("n_not") or 0) < POOL_MIN:
            f.append(f"d {s_} 样本不够（相关 {q.get('n_rel') or 0} / 不相关 {q.get('n_not') or 0} 个）")
        elif q.get("diff") is None or q["diff"] < 0:
            f.append(f"d {s_} 相关的每笔比不相关的低 {q.get('diff')} pp")
    g = [cand[e]["calmar"] - base[e]["calmar"] for e in act
         if (cand.get(e) or {}).get("calmar") is not None and (base.get(e) or {}).get("calmar") is not None]
    return {"ok": not f, "fails": f, "gain": (min(g) if g else None), "active": act}


def ret_reading(cand: dict, base: dict) -> dict:
    f = []
    for e in ("E", "J"):
        x, y = cand.get(e) or {}, base.get(e) or {}
        if None in (x.get("cagr"), y.get("cagr"), x.get("dd"), y.get("dd")):
            f.append(f"{e} 没有值")
            continue
        if x["cagr"] < y["cagr"] + RET_UP:
            f.append(f"{e} 年化 {x['cagr']:.2f}% < B4 {y['cagr']:.2f}% + {RET_UP:.0f} pp")
        if x["dd"] < y["dd"] - RET_DD_TOL:
            f.append(f"{e} 回撤 {x['dd']:.2f}% 比 B4 深 {RET_DD_TOL:.0f} pp 以上")
    xz, yz = cand.get("Z") or {}, base.get("Z") or {}
    if xz.get("cagr") is not None and yz.get("cagr") is not None and xz["cagr"] < yz["cagr"] - RET_Z_TOL:
        f.append(f"Z 年化 {xz['cagr']:.2f}% < B4 {yz['cagr']:.2f}% − {RET_Z_TOL:.0f} pp")
    return {"ok": not f, "fails": f}


def group_stats(net: np.ndarray, flag: np.ndarray) -> dict:
    """假想单笔：相关 / 不相关 两组的个数、胜率、每笔与差（相关 − 不相关）。"""
    net = np.asarray(net, float)
    flag = np.asarray(flag, bool)
    ok = np.isfinite(net)
    a, b = net[ok & flag], net[ok & ~flag]
    d = {"n_rel": int(len(a)), "n_not": int(len(b)),
         "win_rel": (round(float((a > 0).mean() * 100), 2) if len(a) else None), "win_not": (round(float((b > 0).mean() * 100), 2) if len(b) else None),
         "mean_rel": (round(float(a.mean()), 3) if len(a) else None), "mean_not": (round(float(b.mean()), 3) if len(b) else None)}
    d["diff"] = (round(d["mean_rel"] - d["mean_not"], 3) if len(a) and len(b) else None)
    return d


# ───────────────────────── 输入（行情 → 业种分数 / 主线 / 相关） ─────────────────────────
def close_of(frames: dict) -> pd.DataFrame:
    return pd.DataFrame({t: df["Close"].astype(float) for t, df in frames.items() if df is not None and len(df)}).sort_index()


def era_universe(W: dict, e: str) -> dict:
    """{C: 收盘（日期 × 票）, member: 那天是不是参照（J = U2）| None, n225: [...], pool: (池子名, 那个池子的票) }。"""
    if e == "J":
        D = W["SM"]["J2"]["ctx"]["D"]
        days = pd.DatetimeIndex(D["days"])
        names = list(D["names"])
        C = pd.DataFrame(np.asarray(D["P"]["C"], float), index=days, columns=names)
        mem = pd.DataFrame(np.asarray(D["mem"]["U2"], bool), index=days, columns=names)
        n225 = sorted(W["SM"]["J"]["fa"])
        jx = [t for t in names if t not in set(n225)]
        return {"C": C, "member": mem, "n225": n225, "pool": ("Jx", jx)}
    other = "Zx" if e == "Z" else "W"
    fr = {**W["SM"][other]["fa"], **W["SM"][e]["fa"]}
    C = close_of(fr)
    return {"C": C, "member": None, "n225": sorted(W["SM"][e]["fa"]), "pool": (other, sorted(W["SM"][other]["fa"]))}


def era_inputs(W: dict, e: str, ind_of: dict) -> dict:
    U = era_universe(W, e)
    R = mom_12_1(U["C"])
    sc = industry_scores(R, ind_of, U["member"])
    top = top_industries(sc)
    Rd = U["C"].ffill(limit=FFILL_MAX).pct_change(fill_method=None)
    Rd = Rd.where(U["C"].notna())
    if U["member"] is not None:
        Rd_m = Rd.where(U["member"].reindex(index=Rd.index, columns=Rd.columns).fillna(False).astype(bool))
    else:
        Rd_m = Rd
    return {"U": U, "scores": sc, "top": top, "Rd": Rd, "Rd_m": Rd_m}


def rpct_fn(inp: dict, ind_of: dict, rank_set: str):
    """→ f(票, 日) = 那天这只票在排名池里的相关百分位（按日缓存）。rank_set = "n225" / "pool"。"""
    U, top, Rd = inp["U"], inp["top"], inp["Rd"]
    mem = U["member"]
    cache: dict = {}
    tix = pd.DatetimeIndex(top.index)

    def basket_at(d) -> list[str]:
        i = int(tix.searchsorted(d, side="right")) - 1
        if i < 0:
            return []
        inds = top.iloc[i]
        cols = [t for t in U["C"].columns if ind_of.get(t) in inds]
        if mem is not None:
            row = mem.loc[:d].iloc[-1] if len(mem.loc[:d]) else None
            cols = [t for t in cols if row is not None and bool(row.get(t, False))]
        return cols

    def ranks_at(d) -> list[str]:
        if rank_set == "n225":
            return list(U["n225"])
        cols = list(U["pool"][1])
        if mem is not None:
            row = mem.loc[:d].iloc[-1] if len(mem.loc[:d]) else None
            cols = [t for t in cols if row is not None and bool(row.get(t, False))]
        return cols

    def f(t: str, d) -> float | None:
        d = pd.Timestamp(d)
        if d not in cache:
            cache[d] = corr_pct(Rd, d, basket_at(d), ranks_at(d))
        v = cache[d].get(t)
        return None if v is None or not np.isfinite(v) else float(v)
    return f


# ───────────────────────── 只数个数（登记前） ─────────────────────────
def prep(say=print) -> dict:
    """每个年代 / 池子：信号数与被标为 M / P / R / MP / MorP 的个数（不算任何结果）；缓存旗子给 --run 用（同一份）。"""
    import loop10_common as C10
    import loop9_common as C9
    import turn_shape_combo as TC
    from qbreak import paths
    t0 = time.time()
    W = C10.load()
    say(f"载入 B3 + Zx：{time.time() - t0:.0f}s")
    F = TC.load_flags(W, TC.load_models(say)["fits"], say)
    tbf = TC.gates_of(W, F, "TBF")
    ind_of = s33_map(paths.sub("cache") / "jquants" / "master")
    table = load_policy(paths.PROJECT_ROOT / "var" / POLICY_FILE)
    out = {"n_s33": len(ind_of), "policy_rows": int(len(table)), "eras": {}, "pools": {}, "flags": {}, "tbf": {e: np.asarray(tbf[e], bool) for e in ERAS}}
    for e in ERAS:
        inp = era_inputs(W, e, ind_of)
        S = C9.signals(W, e)
        fl = flag_rows(S["ticker"], S["date"], ind_of, inp["top"], table, rpct_fn(inp, ind_of, "n225"))
        out["flags"][e] = fl
        g = out["tbf"][e]
        cnt = {k: int(fl[k][~g].sum()) for k in ("M", "P", "R", "MP", "MorP")}
        out["eras"][e] = {"signals": int(len(S)), "not_tbf": int((~g).sum()), "no_ind": int(fl["ind"].isna().sum()), **cnt,
                          "top_days": int(sum(1 for v in inp["top"] if len(v) == TOP_IND))}
        say(f"{e}：W2 信号 {len(S)} 个（TBF 没挡 {(~g).sum()}）；M {cnt['M']} / P {cnt['P']} / R {cnt['R']} / M∧P {cnt['MP']} / M∨P {cnt['MorP']}；{time.time() - t0:.0f}s")
        pool, _ = POOLS[[p[1] for p in POOLS].index(e)]
        fold = e
        X = C10.kept_pool(W, pool, fold)
        flp = flag_rows(X["ticker"], X["date"], ind_of, inp["top"], table, rpct_fn(inp, ind_of, "pool"))
        out["flags"][pool] = flp
        if pool == "Jx":
            mm = (pd.to_datetime(X["date"]) >= pd.Timestamp(JX_FROM)).to_numpy()
            out["pools"]["Jx_from"] = {k: int(flp[k][mm].sum()) for k in ("M", "P", "R", "MP", "MorP")} | {"signals": int(mm.sum())}
        out["pools"][pool] = {"signals": int(len(X)), **{k: int(flp[k].sum()) for k in ("M", "P", "R", "MP", "MorP")}}
        say(f"池子 {pool}：B4 会买的信号 {len(X)} 个；M {out['pools'][pool]['M']} / P {out['pools'][pool]['P']} / R {out['pools'][pool]['R']}")
    with open(paths.sub("cache") / PREP_CACHE, "wb") as f:
        pickle.dump(out, f)
    out["elapsed_s"] = round(time.time() - t0)
    return out


# ───────────────────────── 运行（登记之后只一次） ─────────────────────────
def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/policy_allin_study.py", "var/industrial_policy.csv",
                                     "scripts/candle_portfolio.py", "scripts/turn_shape_combo.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def allin_trades(tr: pd.DataFrame, em: dict, days: pd.DatetimeIndex) -> dict:
    """账户的笔里，信号是「全仓」的（成交日 = 信号日的下一个交易日）：笔数 / 每笔 / 胜率 / 平均投入（÷ 当天权益，近似用成交额 ÷ 初始以来最高权益不准 → 只报成交额）。"""
    if not len(tr):
        return {"n": 0}
    allin = set()
    for (t, d), f in em.items():
        if f >= F_ALL - 1e-12:
            i = int(days.searchsorted(pd.Timestamp(d), side="right"))
            if i < len(days):
                allin.add((t, str(days[i].date())))
    key = [(str(t), str(d)[:10]) in allin for t, d in zip(tr["ticker"], tr["entry_date"])]
    x = tr[np.asarray(key, bool)]
    if not len(x):
        return {"n": 0}
    net = x["pnl"].to_numpy(float) / (x["shares"].to_numpy(float) * x["entry_px"].to_numpy(float)) * 100
    return {"n": int(len(x)), "mean": round(float(net.mean()), 3), "win": round(float((net > 0).mean() * 100), 2),
            "max_loss": round(float(net.min()), 3)}


def run(say=print) -> dict:
    import jq_study as JS
    import loop10_common as C10
    import loop9_common as C9
    import research_loop as RL
    from qbreak import paths
    t0 = time.time()
    fp_now = RL.rules_fingerprint(paths.PROJECT_ROOT / "var")
    if fp_now != FP:
        raise SystemExit(f"先决条件不满足：模拟盘规则指纹 {fp_now} ≠ 登记时的 {FP} → 停")
    cp = paths.sub("cache") / PREP_CACHE
    if not cp.exists():
        raise SystemExit("没有 --prep 的缓存 → 先 --prep（登记前只数个数的同一份）")
    with open(cp, "rb") as f:
        PR = pickle.load(f)
    W = C10.load()
    tbf = PR["tbf"]
    ref = json.loads((paths.PROJECT_ROOT / "var" / "out" / "turn_shape_combo.json").read_text(encoding="utf-8"))["cand"]["TBF"]
    res: dict = {"git": git_info(), "fingerprint": fp_now, "prep": {k: v for k, v in PR.items() if k not in ("flags", "tbf")},
                 "base": {}, "cand": {}, "allin": {}, "placebo": {}, "pl95": {}, "plmed": {}, "pools": {}, "survey": {}, "judge": {}, "ret": {}}

    def acct_with(e: str, em: dict | None) -> tuple[dict, pd.DataFrame]:
        r = C10.L6.run(W, e, em_tick=em, cfg_over=CFG_FREE) if em is not None else C10.L6.run(W, e)
        eng = JS.RealLotEngine.LAST[-1]
        tr = pd.DataFrame(eng.st.trades)
        if len(tr):
            tr = tr[(tr["reason"] != "end") & tr["ticker"].astype(str).str.endswith(".T")
                    & ~tr["ticker"].isin(["1545.T", "1482.T", "1655.T", "2845.T"])]
        return C9.acct(r), tr

    for e in ERAS:
        S = C9.signals(W, e)
        g = tbf[e]
        assert len(g) == len(S), "TBF 旗子与信号对不上 → 停"
        b4 = C9.acct(C9.run_block(W, e, g))
        if abs(float(b4["calmar"]) - float(ref[e]["calmar"])) > B4_TOL:
            raise SystemExit(f"先决条件不满足：{e} B4 重算 Calmar {b4['calmar']} ≠ turn_shape_combo 的 TBF {ref[e]['calmar']} → 停")
        em0 = em_for(S, g, np.zeros(len(S), bool), F_NOW)
        r0, _ = acct_with(e, em0)
        same = all(r0.get(k) == b4.get(k) for k in ("calmar", "n", "cagr", "dd"))
        if not same:
            raise SystemExit(f"先决条件不满足：{e}「f ≡ 25% + 去掉上限」{r0} ≠ B4 {b4} → 停")
        res["base"][e] = b4
        say(f"{e}：B4 重算 = turn_shape_combo 的 TBF（Calmar {b4['calmar']}）、f ≡ 25% 重建一致；{time.time() - t0:.0f}s")
    days_of = {e: pd.DatetimeIndex(W["ctx"][e]["days"]) for e in ERAS}
    for k in IDS:
        res["cand"][k], res["allin"][k], res["placebo"][k], res["pl95"][k], res["plmed"][k] = {}, {}, {}, {}, {}
        for e in ERAS:
            S = C9.signals(W, e)
            g = tbf[e]
            rel = PR["flags"][e][REL[k]].to_numpy(bool) & ~g
            em = em_for(S, g, rel, OTHERS_F[k])
            if len(em) != len(S):
                raise SystemExit("em_tick 少了信号 → 停")
            row, tr = acct_with(e, em)
            res["cand"][k][e] = row
            res["allin"][k][e] = allin_trades(tr, em, days_of[e])
            rng = np.random.default_rng(SEED + 1000 * IDS.index(k) + ERAS.index(e))
            pl = []
            for _ in range(PLACEBO[e]):
                pr = placebo_rel(g, int(rel.sum()), rng)
                prow, _ = acct_with(e, em_for(S, g, pr, OTHERS_F[k]))
                pl.append(prow.get("calmar"))
            pl = [float(x) for x in pl if x is not None]
            res["placebo"][k][e] = pl
            res["pl95"][k][e] = (float(np.percentile(pl, 95)) if pl else None)
            res["plmed"][k][e] = (float(np.median(pl)) if pl else None)
            say(f"{k} {e}：相关 {int(rel.sum())} 个信号 → Calmar {row.get('calmar')}（B4 {res['base'][e]['calmar']}）、安慰剂中位 {res['plmed'][k][e]} / 95 分位 "
                f"{res['pl95'][k][e]}；全仓成交 {res['allin'][k][e].get('n')} 笔；{time.time() - t0:.0f}s")
        q = {}
        for s, e in (("W", "E"), ("Jx", "J"), ("Zx", "Z")):
            X = C10.kept_pool(W, s, e)
            fl = PR["flags"][s]
            mm = np.ones(len(X), bool) if s != "Jx" else (pd.to_datetime(X["date"]) >= pd.Timestamp(JX_FROM)).to_numpy()
            q[s] = group_stats(X["net"].to_numpy(float)[mm], fl[REL[k]].to_numpy(bool)[mm])
        res["pools"][k] = q
        active = {e: int(PR["eras"][e][REL[k]]) >= ACTIVE_MIN for e in ERAS}
        res["judge"][k] = judge(res["cand"][k], res["base"], res["pl95"][k], {e: res["allin"][k][e].get("n") or 0 for e in ERAS}, q, active)
        res["ret"][k] = ret_reading(res["cand"][k], res["base"])
    for e in ERAS:                                                            # 相关性调查（只描述）：日経225 全部 W2 信号的假想单笔
        Dn = W["D"][e].reset_index(drop=True)
        S = C9.signals(W, e)
        fl = PR["flags"][e].assign(key=[f"{t}|{str(d)[:10]}" for t, d in zip(S["ticker"], S["date"])]).set_index("key")
        keys = [f"{t}|{str(pd.Timestamp(d).date())}" for t, d in zip(Dn["ticker"], Dn["date"])]
        sub = fl.reindex(keys)
        res["survey"][e] = {c: group_stats(Dn["net"].to_numpy(float), sub[c].fillna(False).to_numpy(bool)) for c in ("M", "P", "R", "MP", "MorP")}
    passed = sorted([k for k in IDS if res["judge"][k]["ok"]], key=lambda k: -(res["judge"][k]["gain"] or 0))
    res["pick"] = passed[0] if passed else None
    res["now"] = snapshot(W)
    res["elapsed_s"] = round(time.time() - t0)
    return res


def snapshot(W: dict) -> dict:
    """今天（J-Quants 面板最后一天）的主线 3 个业种与政策点名的业种（只描述，不含个股）。"""
    from qbreak import paths
    ind_of = s33_map(paths.sub("cache") / "jquants" / "master")
    inp = era_inputs(W, "J", ind_of)
    d = inp["top"].index[-1]
    sc = inp["scores"].loc[d].dropna().sort_values(ascending=False)
    table = load_policy(paths.PROJECT_ROOT / "var" / POLICY_FILE)
    wide = load_policy(paths.PROJECT_ROOT / "var" / POLICY_FILE, focus_only=False)
    asof = pd.Timestamp("2026-10-05")
    return {"date": str(pd.Timestamp(d).date()), "top": [{"ind": s, "r12_1_pct": round(float(sc[s]) * 100, 2)} for s in list(sc.index[:TOP_IND])],
            "next": [{"ind": s, "r12_1_pct": round(float(sc[s]) * 100, 2)} for s in list(sc.index[TOP_IND:TOP_IND + 3])],
            "policy_asof": str(asof.date()), "policy_inds": policy_industries(table, asof + pd.Timedelta(days=1)),
            "policy_inds_wide": policy_industries(wide, asof + pd.Timedelta(days=1))}


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def report(res: dict) -> str:
    L = [f"# 去掉 25% 上限：买点与政策 / 发展方向的相关性 → 特别相关的就全仓（登记检验；代码 {res['git']['rev']}{' + 未提交的改动' if res['git']['dirty'] else ''}）",
         "规则见 scripts/policy_allin_study.py 开头（先提交、只运行一次）。基准 B4 = B3 + TBF（模拟盘 2026-10-05 收盘的决策起的规则）。非投资建议。", ""]
    base = res["base"]
    cell = lambda s: f"{_f(s.get('cagr'), '{:.2f}')}% / {_f(s.get('dd'), '{:.2f}')}% / {_f(s.get('calmar'), '{:.3f}')} · {s.get('n') or 0} 笔 {_f(s.get('mean'), '{:+.2f}')}% 胜 {_f(s.get('win'), '{:.1f}')}%"  # noqa: E731
    L += ["## 一、整个账户（年化 / 最大回撤 / Calmar · 个股笔数 每笔 胜率）", "", "| 做法 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 |", "|---|---|---|---|",
          "| B4（现行 4 × 25% + TBF） | " + " | ".join(cell(base[e]) for e in ERAS) + " |"]
    for k in IDS:
        L.append(f"| {k} {LABEL[k]} | " + " | ".join(cell(res["cand"][k][e]) for e in ERAS) + " |")
    L += ["", "全仓的笔（笔数 / 每笔 / 胜率 / 最大一笔亏损）与安慰剂（同样多的信号随机全仓；Calmar 中位 / 95 分位）：", ""]
    for k in IDS:
        L.append(f"- {k}：" + "；".join(
            f"{e} 全仓 {res['allin'][k][e].get('n', 0)} 笔 {_f(res['allin'][k][e].get('mean'), '{:+.2f}')}% 胜 {_f(res['allin'][k][e].get('win'), '{:.0f}')}% "
            f"最差 {_f(res['allin'][k][e].get('max_loss'), '{:+.1f}')}%，安慰剂 {_f(res['plmed'][k][e], '{:.3f}')} / {_f(res['pl95'][k][e], '{:.3f}')}" for e in ERAS))
    L += ["", "## 二、判定（事先写定：a E / J Calmar ≥ B4 + 0.02、回撤不深 2 pp、Z ≥ B4 − 0.02；b E / J > 安慰剂 95 分位；c E / J ≥ 20 笔、全仓 ≥ 5 笔；"
          "d 池子 W 与 Jx 2022〜「相关 − 不相关」每笔 ≥ 0）", ""]
    for k in IDS:
        j = res["judge"][k]
        L.append(f"- **{k} {LABEL[k]}**（能检验的年代：{'、'.join(j.get('active') or []) or '无'}）：{'通过' if j['ok'] else '不通过'}"
                 + ("" if j["ok"] else "（" + "；".join(j["fails"]) + "）")
                 + ("（只有一个年代能检验，证据弱一级）" if j["ok"] and len(j.get("active") or []) == 1 else ""))
    L += ["", f"**结论：{('按规则选 ' + res['pick'] + '（只是提议：先前向记录；进模拟盘要你另外确认）') if res.get('pick') else '没有候选「通过」→ 模拟盘不变'}**", "",
          "## 三、另报「收益率优先」读法（只描述：E / J 年化 ≥ B4 + 2 pp 且回撤不深 5 pp、Z ≥ B4 − 1 pp）", ""]
    for k in IDS:
        r = res["ret"][k]
        L.append(f"- {k}：{'满足' if r['ok'] else '不满足'}" + ("" if r["ok"] else "（" + "；".join(r["fails"]) + "）"))
    L += ["", "## 四、相关性调查（假想单笔 X6，扣费用；相关 vs 不相关：个数 · 胜率 · 每笔；差 = 相关 − 不相关）", "",
          "| 样本 | 相关性 | 相关 | 不相关 | 每笔差 |", "|---|---|---|---|---|"]
    for e in ERAS:
        for c, nm in (("M", "主线 M"), ("P", "政策 P"), ("R", "相关 R"), ("MP", "M 且 P"), ("MorP", "M 或 P")):
            q = res["survey"][e][c]
            L.append(f"| 日経225 {e} | {nm} | {q['n_rel']} · {_f(q['win_rel'], '{:.1f}')}% · {_f(q['mean_rel'], '{:+.2f}')}% | "
                     f"{q['n_not']} · {_f(q['win_not'], '{:.1f}')}% · {_f(q['mean_not'], '{:+.2f}')}% | {_f(q['diff'], '{:+.2f}')} pp |")
    for k in IDS:
        for s in ("W", "Jx", "Zx"):
            q = res["pools"][k][s]
            L.append(f"| 池子 {s}{' 2022〜' if s == 'Jx' else ''} | {k} 的相关性 | {q['n_rel']} · {_f(q['win_rel'], '{:.1f}')}% · {_f(q['mean_rel'], '{:+.2f}')}% | "
                     f"{q['n_not']} · {_f(q['win_not'], '{:.1f}')}% · {_f(q['mean_not'], '{:+.2f}')}% | {_f(q['diff'], '{:+.2f}')} pp |")
    nw = res.get("now") or {}
    L += ["", f"## 五、现在（只描述，仅对本次数据时点有效）", "",
          f"- 主线（{nw.get('date')}，12-1 个月业种等权涨幅前 {TOP_IND}）：" + "、".join(f"{x['ind']}（{x['r12_1_pct']:+.1f}%）" for x in nw.get("top") or [])
          + "；之后：" + "、".join(f"{x['ind']}（{x['r12_1_pct']:+.1f}%）" for x in nw.get("next") or []),
          f"- 政策点名（{nw.get('policy_asof')} 之前 365 天，var/industrial_policy.csv）：专门针对一个产业的决定（P 用的）"
          + ("、".join(nw.get("policy_inds") or []) or "—") + "；连综合性的成长战略一起算：" + ("、".join(nw.get("policy_inds_wide") or []) or "—"),
          "", "登记前个数：" + json.dumps(res["prep"].get("eras"), ensure_ascii=False), "",
          f"用时 {res.get('elapsed_s')} s。非投资建议。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prep", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from qbreak import paths
    if a.prep:
        out = prep()
        print(json.dumps({k: v for k, v in out.items() if k not in ("flags", "tbf")}, ensure_ascii=False, indent=1, default=str))
        return 0
    res = run()
    od = paths.out_dir()
    (od / OUT_MD).write_text(report(res), encoding="utf-8")
    slim = {k: v for k, v in res.items() if k != "placebo"}
    slim["placebo_n"] = {k: {e: len(v) for e, v in res["placebo"][k].items()} for k in IDS}
    (od / OUT_JSON).write_text(json.dumps(slim, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
