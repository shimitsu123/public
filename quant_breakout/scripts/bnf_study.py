"""bnf_study.py — 按「日本股神」B・N・F（网名）公开说过的逻辑做买卖点模型，登记检验
（2026-09-29 用户：「日本之前有个股神挣到了200多亿能不能按照他的逻辑来设计买卖点模型」；规则先提交再运行一次，结果出来不改规则）。

〇 他是谁、说过什么（2026-09-29 查看原文；仅对该时点有效）
  - B・N・F：2000 年用 160 万円起步 → 2005 年末 80 億円、2006 年末 157 億円、2007 年末 185 億円、2008 年初 190 億円
    （ja.wikipedia「B・N・F」及其引用的 zakzak 2008-02-07 等）；2005-12 ジェイコム株大量誤発注：取得 7,100 株、6,000 株现金决济 20 億 3,500 万円（同）；
    2009 年末以后不再在媒体露面（同）。
  - 他自己说过的（原文转引自 kabushiki-blog.com/article/80415989.html，该页注明出处）：
    ネットマネー 2006 年 7 月号「B・N・F氏のチャート道場２」：「まず全体を見てください」「下落中の銘柄の底打ちを狙って買いにいく逆張りの場合は、
    25日移動平均線と日足チャートのカイ離率も参考にします」「この手の銘柄は連動した動きをするので、少しでも出遅れているものがあればチャンスかもしれませんね」
    「移動平均カイ離率も時期や銘柄によって目安が違うので注意してください」；
    夕刊フジ（ZAKZAK）2008-01-24：常に１泊２日程度の“スイングトレード”；「２５日移動平均線との乖離（かいり）率だけで逆張りしてもダメ」
    「選定銘柄は相場の上げ下げにかかわらず、大型銘柄のみ。発注は指し値オンリー」；美欧亚股、汇率、先物、雇用统计都看。
  - 第三方整理（不是本人原话，数字只作参考）：25 日线乖离 −20%〜−35% 是买点（大型股 −20% 前后）、止损彻底。
  - 另一位也常被说成「200 多亿」的 cis（2000 年 300 万円 → 2018 年 230 億円，ja.wikipedia「cis (投資家)」）是顺势（順張り）短线 ——
    与现行的突破同一个方向，这里不另做。

一 能复现的与不能复现的
  能（日线）：25 日线乖离逆张（抄底）、只做大型股（今天的日経225）、持有几天、止损、全市场恐慌时买、同业种一起跌之后「出遅れ」的票。
  不能：盘中看板 / 先物实时先回り、一天几十次买卖、误发注那样的一次性机会、他本人的裁量。
  注意：他本人说「只看乖离率去逆张不行」「先看全体」「目安因时期和票而异」→ 这里是机械化的简化版：「全体」只用 BP（指数也恐慌）
  与 BL（同业种已开始反弹）两种近似，B20 / B30 是纯乖离的对照；检验的是「他公开说过的逻辑能不能机械化」，不是检验他本人。
  执行照现行：信号日收盘成立 → 下一个交易日寄付（指値 = 信号收盘 × 1.03，跳空 > 3% 不买）；立花的手续费。

二 候选（4 个；买点不同、卖法相同）
  乖离 d = 收盘 ÷ 25 日均线 − 1（只用到当天收盘）。
  B20：d ≤ −20%（大型股的常见门槛）。
  B30：d ≤ −30%（区间的深端）。
  BP ：B20 且同一天日経225 指数的 25 日线乖离 ≤ −10%（全市场恐慌：ライブドアショック / リーマン / コロナ那种）。
  BL ：B20 且同一个东证 33 业种（日経225 里 ≥ 3 只）当天涨跌的中位数 ≥ +1%、这只票当天涨跌 ≤ 0（同业种已经开始反弹、它还没动 = 出遅れ）；
       业种 = var/industry_s33.json + qbreak/universes.JP_READDED_S33（加回的陸運 / 空運 12 只）。
  卖法（共同）：收盘时乖离回到 ≥ −10%（反弹一半）→ 次日寄付卖；最多拿 5 个交易日；收盘跌到买入价 −10% 止损；
  不用死叉 / 跟踪止损 / 止盈 / 放量阴线 / 决算前。同一天多个候选：乖离越深越先买。

三 资金（和突破分开）：账户 75% 照现行（S0C2 + W2 + X6，与模拟盘同一套），25% 专门做 BNF（同一套 S0C2 框架：4 个名额 × 25%、
  闲置资金拿核心 + 牛熊分界；**不加**宏观 / 状态层的新仓倍数 —— 他的逻辑就是在大家怕的时候买，现有风险层在暴跌时不开新仓，
  上一轮超跌反弹（77539c6）就是被它挡住）；每个月第一个交易日再平衡回 75 / 25（不另扣再平衡费用）。
  另报（只描述）：只有 BNF 那部分、B20 那部分加上现有风险层、那部分一笔都不买（只有核心）。

四 数据与窗口：Z 2001-01〜2006-09（他本人赚钱的年代，Yahoo）、E 2006-10〜2016-09（Yahoo）、J 2017-01〜2026-09（J-Quants）；今天的日経225。
  逐笔 = 每个成立的日子单独一笔（同一只票上一笔卖出之前的信号不算）、扣立花 ¥25 万来回手续费；账户 = 上面的 75 / 25。

五 判定（全部满足才「通过」；运行前写定）
  a 逐笔：Z、E、J 每段 ≥ 20 笔且每笔平均 > 0；E ∪ J 合并每笔平均的 95% 下限 > 0（madev_event.boot_mean：按信号所在日历月聚类的自助法）；
  b 账户（75 / 25）：E、J 各自 Calmar ≥ 现行 + 0.02、最大回撤不比现行深 2 pp 以上；Z Calmar ≥ 现行。
  「通过」→ 只是提议（先做前向记录；要进模拟盘 / 执行器要你另外确认，执行器也要改）；
  没通过、但 Z 的逐笔 ≥ 20 笔且每笔 > 0、Z 账户 Calmar ≥ 现行 →「只在他的年代成立」；其余「不通过」。多个通过：按 min(E, J 的 Calmar 提高) 取 1 个。

六 事前预期（运行前写）：上一轮超跌反弹里深跌的收益几乎都来自 2009 / 2020 的暴跌反弹、2008 是接刀 →
  预期 Z 为正（2001〜2003 熊市里的反弹、2006 ライブドア）、E 被 2008 拖累、J 靠 2020；「通过」的可能性约 15%；BP 在 E / J 可能不到 20 笔；
  他本人说纯乖离不行 → 预期 B20 / B30 弱于 BP / BL。
  （登记前只核对了规则机制、没跑回测：日経225 指数 25 日线乖离 ≤ −10% 的日子 2001〜2006 年合计只有 4 天（2001 年 3、2002 年 1），
  2008 年 22 天、2020 年 11 天 → BP 在 Z 大概率也不到 20 笔（a 不满足、也够不上「只在他的年代成立」）；规则不因此改。）

七 另报（只描述）：按年份的逐笔（尤其 2001〜2003、2006、2008、2009、2020）、出场原因、持有天数；
  ¥100 万时 25% 只有 ¥25 万、一个名额约 ¥6 万（日経225 大多一手就超过）→ 真要做只能 1 个名额，这里的账户是按比例放大的。

八 局限：只用日线收盘与次日开盘；大型股 = 今天的日経225（幸存者偏差）；调整后价；税前；他本人的盘中技巧与裁量不在里面；
  Z / E / J 以前做过很多别的检验。模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/bnf_study.md / .json（只有统计）。  python scripts/bnf_study.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ERAS = ("Z", "E", "J")
CANDS = {"B20": "25 日线乖离 ≤ −20%", "B30": "25 日线乖离 ≤ −30%",
         "BP": "B20 且日経225 指数 25 日线乖离 ≤ −10%（全市场恐慌）",
         "BL": "B20 且同业种当天中位数 ≥ +1%、这只 ≤ 0（出遅れ）"}
DEV_N, DEV_ENTRY, DEV_DEEP, DEV_EXIT = 25, -0.20, -0.30, -0.10
PANIC, LAG_UP, LAG_MIN = -0.10, 0.01, 3
HOLD, STOP = 5, 10.0
W_BNF = 0.25
MIN_N, CAL_UP, DD_TOL = 20, 0.02, 2.0
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 规则（纯函数，有测试）─────────────────────────
def dev25(close: pd.Series) -> pd.Series:
    """收盘 ÷ 25 日均线 − 1（只用到当天收盘；不满 25 根 → NaN）。"""
    c = close.astype(float)
    return c / c.rolling(DEV_N, min_periods=DEV_N).mean() - 1


def exit_signal(dev: pd.Series) -> np.ndarray:
    """卖出判定列：收盘时乖离回到 ≥ −10%（NaN → False）。"""
    d = dev.to_numpy(float)
    with np.errstate(invalid="ignore"):
        return np.isfinite(d) & (d >= DEV_EXIT)


def sector_median(R: pd.DataFrame, sector: dict[str, str], min_members: int = LAG_MIN) -> pd.DataFrame:
    """R：日期 × 票 的当天涨跌 → 同形状：每只票所在业种当天的中位数（业种里 < min_members 只 → NaN）。"""
    out = pd.DataFrame(np.nan, index=R.index, columns=R.columns)
    groups: dict[str, list[str]] = {}
    for t in R.columns:
        s = sector.get(t)
        if s:
            groups.setdefault(s, []).append(t)
    for s, ts in groups.items():
        if len(ts) < min_members:
            continue
        med = R[ts].median(axis=1, skipna=True)
        for t in ts:
            out[t] = med
    return out


def cand_mask(c: str, dev: np.ndarray, panic: np.ndarray, sect_med: np.ndarray, own_ret: np.ndarray) -> np.ndarray:
    """候选 c 在每一天是否成立（数组对齐同一只票的日期）。"""
    with np.errstate(invalid="ignore"):
        b20 = np.isfinite(dev) & (dev <= DEV_ENTRY)
        if c == "B20":
            return b20
        if c == "B30":
            return np.isfinite(dev) & (dev <= DEV_DEEP)
        if c == "BP":
            return b20 & np.asarray(panic, bool)
        if c == "BL":
            return b20 & np.isfinite(sect_med) & (sect_med >= LAG_UP) & np.isfinite(own_ret) & (own_ret <= 0)
    raise ValueError(c)


def bnf_params(p):
    """BNF 的卖法：−10% 止损、最多 5 个交易日、乖离回到 −10%（给在 dead_cross 列）；不用跟踪 / 止盈 / 放量阴线 / 决算前。"""
    return replace(p, stop_loss_pct=STOP, atr_stop_mult=0.0, take_profit_pct=0.0, trailing_stop_pct=0.0, trailing_arm_pct=0.0,
                   max_hold_days=HOLD, exit_on_macd_dead_cross=True, exit_on_climax=False, time_stop_days=0, exit_before_earnings=False)


def verdict(tr: dict[str, dict], pool: dict, acct: dict[str, dict], acct0: dict[str, dict]) -> tuple[str, list[str]]:
    """五 a / b → (标签, 没满足的条件)。tr：{Z/E/J: {n, mean}}；pool：E ∪ J {lo}；acct / acct0：{Z/E/J: {calmar, dd}}。"""
    f = []
    for t in ERAS:
        x = tr.get(t) or {}
        if x.get("n", 0) < MIN_N:
            f.append(f"a {t} 只有 {x.get('n', 0)} 笔（< {MIN_N}）")
        elif not x.get("mean", -1) > 0:
            f.append(f"a {t} 每笔 {x.get('mean', float('nan')):+.2f}% ≤ 0")
    if not (pool.get("lo") is not None and pool["lo"] > 0):
        f.append(f"a E ∪ J 每笔 95% 下限 {pool.get('lo', float('nan')):+.2f}% ≤ 0")
    for t in ("E", "J"):
        x, y = acct.get(t) or {}, acct0.get(t) or {}
        if None in (x.get("calmar"), y.get("calmar"), x.get("dd"), y.get("dd")):
            f.append(f"b {t} 账户没有值")
            continue
        if x["calmar"] < y["calmar"] + CAL_UP:
            f.append(f"b {t} Calmar {x['calmar']:.3f} < 现行 {y['calmar']:.3f} + {CAL_UP}")
        if x["dd"] < y["dd"] - DD_TOL:
            f.append(f"b {t} 回撤 {x['dd']:.2f}% 比现行 {y['dd']:.2f}% 深 {DD_TOL:.0f} pp 以上")
    xz, yz = acct.get("Z") or {}, acct0.get("Z") or {}
    z_ok = None not in (xz.get("calmar"), yz.get("calmar")) and xz["calmar"] >= yz["calmar"]
    if not z_ok:
        f.append("b Z Calmar 低于现行")
    if not f:
        return "通过", f
    z_tr = tr.get("Z") or {}
    if z_tr.get("n", 0) >= MIN_N and z_tr.get("mean", -1) > 0 and z_ok:
        return "只在他的年代成立", f
    return "不通过", f


# ───────────────────────── 计算 ─────────────────────────
def index_panic(nk: pd.DataFrame) -> pd.Series:
    """日経225 指数：25 日线乖离 ≤ −10% 的日子（只用东证交易日）。"""
    from qbreak.calendar_jp import is_trading_day
    c = nk["Close"].astype(float)
    c = c[[is_trading_day(d.date()) for d in c.index]]
    return dev25(c) <= PANIC


def solo_trades(fa: dict, masks: dict[str, np.ndarray], exits: dict[str, np.ndarray], pp, bt, rt: float, a, b, end_bars: int = 30) -> pd.DataFrame:
    """每个成立的日子单独一笔（窗口 [a, b] 内）；同一只票上一笔卖出之前的信号不算。→ ticker / date / net / hold / reason。"""
    import sell_confirm as SCF
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    rows = []
    for t, df in fa.items():
        m = masks.get(t)
        if m is None or not m.any():
            continue
        idx = df.index
        free = pd.Timestamp.min
        f0 = df.assign(dead_cross=exits[t])
        for pos in np.flatnonzero(m):
            d = idx[pos]
            if d < a or d > b or d < free:                                   # 卖出日（寄付卖）当天收盘的信号在卖出之后 → 算
                continue
            end = idx[min(len(idx) - 1, pos + end_bars)]
            x = SCF.one_trade(t, f0.assign(entry=np.asarray(idx == d)), d, pp, bt, end)
            if x is None or x["reason"] == "end":
                continue
            free = pd.Timestamp(x["exit_date"])
            rows.append({"ticker": t, "date": d, "net": float(x["ret_pct"]) - rt, "hold": int(x["hold_days"]),
                         "reason": str(x["reason"]).split("(")[0]})
    return pd.DataFrame(rows, columns=["ticker", "date", "net", "hold", "reason"])


def main() -> int:
    import leap_confirm as LF
    import madev_event as ME
    import rebound_study as RB
    import sell_confirm as SCF
    from bullbear_study import SYM, load
    from qbreak import exit_rules as EXR
    from qbreak import paths
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    pb = bnf_params(p0)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/bnf_study.py"], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parents[1]).stdout.strip())
    from qbreak.universes import JP_READDED_S33
    s33 = {**((read_json(paths.PROJECT_ROOT / "var" / "industry_s33.json", {}) or {}).get("s33") or {}), **JP_READDED_S33}
    panic = index_panic(load(*SYM["JP"]))
    say(f"# B・N・F 的逻辑做买卖点模型（登记检验，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/bnf_study.py 开头（先提交后只跑一次）。逐笔 = 每只票单独、扣立花手续费；账户 = 75% 现行（S0C2 + W2 + X6）+ 25% BNF（不加宏观 / 状态层）。")
    TR: dict[str, dict] = {c: {} for c in CANDS}
    ACCT: dict[str, dict] = {}
    NSIG: dict[str, dict] = {}
    for era in ERAS:
        t1 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, p0)
        keep = LF.w2_keep(ctx, fa)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        D = {t: dev25(df["Close"]) for t, df in fa.items()}
        R = pd.DataFrame({t: df["Close"].astype(float).pct_change() for t, df in fa.items()})
        SM = sector_median(R, {t: s33.get(t.split(".")[0]) for t in fa})
        exits = {t: exit_signal(D[t]) for t in fa}
        masks: dict[str, dict] = {c: {} for c in CANDS}
        prio: dict = {}
        for t, df in fa.items():
            dv = D[t].to_numpy(float)
            pn = panic.reindex(df.index).fillna(False).to_numpy(bool)
            sm = SM[t].reindex(df.index).to_numpy(float)
            own = R[t].reindex(df.index).to_numpy(float)
            for c in CANDS:
                masks[c][t] = cand_mask(c, dv, pn, sm, own)
            for d, v in zip(df.index[masks["B20"][t]], dv[masks["B20"][t]]):
                prio[(t, d)] = -float(v)                                     # 乖离越深越先买
        run_fn = LF.runner(ctx, fa)
        LF.run(ctx, run_fn, LF.with_mask(fa, keep), px)
        eq0 = RB.last_equity()
        ACCT[era] = {"现行": RB.acct_stats(eq0, a, b)}
        LF.run(ctx, run_fn, {t: df.assign(entry=False, dead_cross=exits[t]) for t, df in fa.items()}, pb, mult=False)
        eqn = RB.last_equity()
        ACCT[era]["只有核心（那 25% 一笔都不买）"] = {"75/25": RB.acct_stats(RB.blend(eq0, eqn, W_BNF), a, b), "only": RB.acct_stats(eqn, a, b)}
        for c in CANDS:
            fb = {t: df.assign(entry=masks[c][t], dead_cross=exits[t]) for t, df in fa.items()}
            LF.run(ctx, run_fn, fb, pb, mult=False, priority=prio)
            eqb = RB.last_equity()
            ACCT[era][c] = {"75/25": RB.acct_stats(RB.blend(eq0, eqb, W_BNF), a, b), "only": RB.acct_stats(eqb, a, b)}
            if c == "B20":
                LF.run(ctx, run_fn, fb, pb, mult=True, priority=prio)
                eqm = RB.last_equity()
                ACCT[era]["B20 + 现有风险层"] = {"75/25": RB.acct_stats(RB.blend(eq0, eqm, W_BNF), a, b), "only": RB.acct_stats(eqm, a, b)}
            T = solo_trades(fa, masks[c], exits, pb, bt, rt, a, b)
            T["era"] = era
            TR[c][era] = T
            NSIG.setdefault(era, {})[c] = int(sum(int(((df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b)) & masks[c][t]).sum())
                                                  for t, df in fa.items()))
        say(f"- {era}（{a}〜{b}）：{len(fa)} 只；成立的日子（票 × 日）" + " / ".join(f"{c} {NSIG[era][c]}" for c in CANDS)
            + f"；{round(time.time() - t1)} s")

    res = {}
    for c in CANDS:
        tr = {e: RB.trade_stats(TR[c][e]) for e in ERAS}
        pool = RB.trade_stats(pd.concat([TR[c]["E"], TR[c]["J"]], ignore_index=True), ci=True)
        acct = {e: ACCT[e][c]["75/25"] for e in ERAS}
        acct0 = {e: ACCT[e]["现行"] for e in ERAS}
        lab, fails = verdict(tr, pool, acct, acct0)
        g = [acct[e]["calmar"] - acct0[e]["calmar"] for e in ("E", "J") if acct[e].get("calmar") is not None and acct0[e].get("calmar") is not None]
        res[c] = {"label": lab, "fails": fails, "trades": tr, "pool": pool, "gain": (min(g) if len(g) == 2 else None)}
    passed = sorted([c for c in CANDS if res[c]["label"] == "通过"], key=lambda c: -res[c]["gain"])
    pick = passed[0] if passed else None
    fmt = RB.fmt
    cell = lambda s: f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')}"  # noqa: E731

    say("\n## 一、逐笔（每只票单独、扣成本；笔数 / 胜率 / 每笔 / 持有中位）")
    say("| 候选 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 | E ∪ J 每笔（95% 区间） | 判定 |")
    say("|---|---|---|---|---|---|")
    for c in CANDS:
        r = res[c]
        cells = [("—" if not x.get("n") else f"{x['n']} / {x['win']:.1f}% / {x['mean']:+.2f}% / {x['hold']:.0f} 天") for x in (r["trades"][e] for e in ERAS)]
        pl = r["pool"]
        say(f"| {c} {CANDS[c]} | " + " | ".join(cells) + f" | {fmt(pl.get('mean'))}%（{fmt(pl.get('lo'))}〜{fmt(pl.get('hi'))}） | {r['label']} |")
    say("\n## 二、整个账户（年化 / 最大回撤 / Calmar；75% 现行 + 25% BNF，每月再平衡）")
    say("| 做法 | Z | E | J |")
    say("|---|---|---|---|")
    say("| 现行（100%） | " + " | ".join(cell(ACCT[e]["现行"]) for e in ERAS) + " |")
    for k in ("只有核心（那 25% 一笔都不买）", *CANDS, "B20 + 现有风险层"):
        say(f"| {k} | " + " | ".join(cell(ACCT[e][k]["75/25"]) for e in ERAS) + " |")
    say("\n只有 BNF 那 25%（单独看；闲置时拿核心 + 牛熊分界）：")
    for k in ("只有核心（那 25% 一笔都不买）", *CANDS, "B20 + 现有风险层"):
        say(f"- {k}：" + "；".join(f"{e} {cell(ACCT[e][k]['only'])}" for e in ERAS))
    say("\n## 三、判定（事先写定）")
    for c in CANDS:
        r = res[c]
        say(f"- **{c}**：{r['label']}" + ("" if not r["fails"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n**结论：{('按规则选 ' + pick + '（只是提议：先做前向记录，要进模拟盘要你另外确认）') if pick else '没有候选「通过」→ 模拟盘不变'}**")

    say("\n## 四、按年份（逐笔：笔数 / 每笔；只描述）")
    years = sorted({int(y) for c in CANDS for e in ERAS for y in pd.to_datetime(TR[c][e]["date"]).dt.year})
    say("| 年 | " + " | ".join(CANDS) + " |")
    say("|---|" + "---|" * len(CANDS))
    for y in years:
        row = []
        for c in CANDS:
            T = pd.concat([TR[c][e] for e in ERAS], ignore_index=True)
            T = T[pd.to_datetime(T["date"]).dt.year == y]
            row.append("—" if not len(T) else f"{len(T)} / {T['net'].mean():+.2f}%")
        say(f"| {y} | " + " | ".join(row) + " |")
    say("\n## 五、出场原因（全部窗口合并；% of 笔数）")
    for c in CANDS:
        T = pd.concat([TR[c][e] for e in ERAS], ignore_index=True)
        if len(T):
            rs = T["reason"].value_counts(normalize=True).mul(100).round(0)
            say(f"- {c}：" + "、".join(f"{k} {v:.0f}%" for k, v in rs.items()))
    by_year = {}
    for c in CANDS:
        T = pd.concat([TR[c][e] for e in ERAS], ignore_index=True)
        by_year[c] = {int(y): {"n": int(len(g)), "mean": float(g["net"].mean())} for y, g in T.groupby(pd.to_datetime(T["date"]).dt.year)} if len(T) else {}
    out = {"code": code, "dirty": dirty, "pick": pick, "result": res, "account": ACCT, "signals": NSIG, "trades_by_year": by_year,
           "elapsed_s": round(time.time() - t0)}
    say(f"\n代码版本 {code}{'（有未提交的改动）' if dirty else '（与提交的版本相同）'}；用时 {out['elapsed_s']} s。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / "bnf_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
