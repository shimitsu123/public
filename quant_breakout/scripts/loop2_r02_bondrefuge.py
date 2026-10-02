"""loop2_r02_bondrefuge.py — 第二个研究循环第 2 轮：「美股熊市里拿对冲版美国 7〜10 年国债」TBH（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 2 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py。
为什么挑这个题（照实写）：
  - 选题前只看过 B1 本身的诊断（scratch，不入库）：个股层平均只占权益 11〜18%（E 有 78% 的日子一只个股都没有），
    离场 / 仓位 / 执行改个股的做法对账户的上限很小（09-30 赢家加仓的作弊上限也只有 +0.047）；账户主要是闲置资金那一层。
    B1 在美股熊市（S&P500 250 日线 ±3%、连续 5 天）里闲置资金全部是现金：Z 2001〜2003-05、E 2008、2010、2011、2015〜16、J 2018-12、2020、2022、2025 共约 16% 的日子一分钱不赚。
  - 用户要求优先新数据；对冲版美国国债 ETF（1482）与美国 7 / 10 年国债收益率（FRED DGS7 / DGS10）是这个项目没有用过的数据。
  - 以前做过的（不重复）：2026-09-27 R10（refuge_study 1fd9ec8）熊市换「不对冲」的黄金 / 美国长债（TLT × USD/JPY）→ 没通过，
    原因写在结果里：2008 年日元升值，外币资产按日元计也亏（2008-01〜2009-07 长债 −9.5%）；第一个循环第 6 轮 BXU（133A 美元短期国债）也是外币。
    这一轮针对的正是这个失败原因：拿「对冲汇率」的版本，按日元计不受日元升值影响。→ 设计是在看过 R10（同一批 E / J 数据）的结果之后做的，
    不是两个已看过规则的组合，但为保守按「事后」处理：S7 适用（没看过的 1987〜2000 只有核心的 Calmar 差要 > 0）。
  - 汇率对冲家族（什么时候对冲纳指）不再加；这一轮的对冲只是「这只债券 ETF 本来就是对冲版」，不按汇率择时 → 家族「核心·熊市避险资产」。
做法（参数事先写定、没调 → S6 不适用；不改个股买卖 → S5 不适用）：
  TBH：B1 的美股牛熊分界是「熊」且「对冲版美债自己的牛熊」是「牛」→ 闲置资金拿 1482（iシェアーズ・コア 米国債 7-10年 ETF 為替ヘッジあり），
    否则同 B1（美股牛：FJE 对冲中 → 2845、否则 1545；美股熊且债券不是牛 → 现金）。
    债券自己的牛熊 = 模拟盘同一个检测器、同一组参数（var/bullbear.json：250 日线 ±3%、连续 5 天，qbreak/bullbear.ma_band），
    套在 1482 的合成价（东证交易日，= 前一个美国收盘的值）上 → 不加新参数；只为躲开 2022 那种「股债一起跌」的通胀熊市（事先就知道的历史，照实写）。
  1482 合成价（全程同一做法，东证 d 日 = 前一个美国收盘）：
    美元总收益 = 7 年与 10 年固定期限国债收益率（FRED DGS7 / DGS10）的平均当作 8.5 年平价债（1482 加权平均残存 8.49 年），
      每天 = 新收益率下的价格 − 1 + 前一天收益率 × 天数 / 365（不算骑乘收益 → 比 IEF 每年约低 0.8 pp，偏保守）；
    对冲 = fxhedge_study.hedged_index 同一个口径（+ (日本拆借 − 联邦基金) / 252；2845 的合成价同一做法）；
    费用 = 信託報酬 税込 0.154% + 另扣 0.6%（登记前核对：这样合成的对冲版比真实 1482 在 2017〜2026 逐年平均高 0.61 pp —— 期货基差与其他费用；
      只用全部年份的跟踪差，不分牛熊）；价格水平按 2026-08-31 的真实收盘 ¥1,537。
  费用表：qbreak/fees.py 加 1482.T（一手 1 口、滑点 0.05%；BlackRock ファクトシート 2026-08 版 + Yahoo 到 2026-09-30 的成交额，见那一行的注释）。
  接线：债券一直「熊」（= 从不拿 1482）时必须与 B1 完全相同（tests/test_loop2_r02.py 查结构；登记前跑过一次三个年代的数字一致检查）。
第一关：research_loop2.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 TBH − B1 的 Calmar 差）。
  1987〜2000 只有核心：日元计纳指（第 1 轮 / 第 15 轮 old_core 同一个合成价与口径：前一天收盘的状态决定当天，换仓按换掉的比例扣 0.1%），
  美股熊且债券牛 → 对冲版美债合成价（同上，美国日期；债券的牛熊再晚一天用，因为 FRED 的收益率第二天才公布）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次，「同样多、同样形状的随机改动」在那时写定。
只描述（不参与判定）：各年代美股熊的日子比例、其中债券牛（拿 1482）的比例与段数、拿着的那几段 1482 合成价的连乘收益、核心换仓笔数。
事前预期（照实写，按一般的市场历史估计，不是这个项目的结果）：2001〜2003、2008、2010、2011、2020 美股熊时美债多半上涨，2022 债券自己是熊 → 现金；
  Z 可能 +0.05〜+0.25、E +0.05〜+0.20、J ±0.02；风险：对冲成本（2001〜2007 美国利率高）、2009 上半年美债下跌、检测器转熊慢；
  第一关约 35%，「更好候选」约 10%。
运行：python scripts/loop2_r02_bondrefuge.py（第一关）。输出 var/out/loop2_r02_bondrefuge.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 2
IDS = ("TBH",)
FAMILY = "核心·熊市避险资产"
POSTHOC = True                                                              # 看过 R10 的失败原因之后设计 → 按事后处理（S7 适用）
BOND_T, BD_KEY = "1482.T", "US_BD"
TENOR = 8.5                                                                 # 年：7 年与 10 年的平均收益率当作 8.5 年平价债
TRUST_FEE, BASIS = 0.154, 0.6                                               # 年 %：信託報酬（税込）+ 对冲版合成价相对真实 1482 的跟踪差
REF_DATE, REF_PX = "2026-08-31", 1537.0                                     # 1482 的真实收盘（Yahoo）
BOND_START = "1986-01-01"
OLD = ("1987-01-01", "2000-12-31")
OUT = "loop2_r02_bondrefuge"


# ───────────────────────── 规则（纯函数，tests/test_loop2_r02.py） ─────────────────────────
def par_bond_tr(yield_pct: pd.Series, tenor: float = TENOR) -> pd.Series:
    """固定期限平价债的美元总收益指数（从 1 起）：每天 = 按前一天收益率作票息、新收益率下的价格 − 1 + 前一天收益率 × 天数 / 365（半年付息）。"""
    y = yield_pct.dropna().sort_index().astype(float) / 100
    y0 = y.shift(1)
    disc = (1 + y / 2) ** (-2 * tenor)
    price = (y0 / y) * (1 - disc) + disc
    dt = y.index.to_series().diff().dt.days.to_numpy(float) / 365.0
    r = (price - 1 + y0 * dt).fillna(0.0)
    return (1 + r).cumprod()


def bond_usd() -> pd.Series:
    """美国 7〜10 年国债的美元总收益（美国日期）：DGS7 与 DGS10 两个都有的日子取平均收益率。"""
    from qbreak import factors
    y = pd.concat([factors.fred("DGS7", max_age_h=1e9), factors.fred("DGS10", max_age_h=1e9)], axis=1).dropna().mean(axis=1)
    return par_bond_tr(y)


def bond_hedged(usd_tr: pd.Series) -> pd.Series:
    """对冲版（日元，美国日期）：hedged_index（2845 合成价同一口径）再扣 信託報酬 + 跟踪差。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    from qbreak import factors
    h = FX.hedged_index(usd_tr, factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9))
    return EI.grow(h, -(TRUST_FEE + BASIS))


def bond_close(inp: dict, hedged: pd.Series | None = None, start: str = BOND_START) -> pd.Series:
    """东证交易日的 1482 合成收盘（d 日 = 前一个美国收盘的值），按 REF_DATE 的真实收盘定水平。
    从 1986 年起（日本拆借利率 1985-08 起才有 → 对冲从那时起才算得对；检测器的 250 日线到 Z 的开头早已就绪）。"""
    import equity_idle_study as EI
    h = bond_hedged(bond_usd()) if hedged is None else hedged
    days = inp["n225"].index[inp["n225"].index >= pd.Timestamp(start)]
    c = EI.on_jp(h, None, days).dropna()
    return c * (REF_PX / float(c.asof(pd.Timestamp(REF_DATE))))


def trend_on(close: pd.Series, det: dict | None = None) -> pd.Series:
    """债券自己的牛熊：模拟盘同一个检测器、同一组参数（var/bullbear.json；det 只给测试用）→ True = 牛（还没有判定的开头 = False）。"""
    from qbreak.bullbear import BULL, Detector, load_config
    d = det or load_config()["detector"]
    c = close.dropna()
    st = np.asarray(Detector(d["kind"], d["params"]).states(c))
    return pd.Series(st == BULL, index=c.index)


def tbh_over(bear_us: pd.Series, bond_on: pd.Series, frame: pd.DataFrame) -> dict:
    """在 B1 上加第三只核心 1482：它的「熊」= 美股牛 或 债券不是牛（两个都 True 才拿）；B1 的 1545 / 2845 不动（loop2_common 按键合并）。"""
    import loop_r04_yensurge as Y
    return {"cfg_over": {"core": {"1545.T": 1.0, Y.HEDGE_T: 1.0, BOND_T: 1.0},
                         "core_index": {"1545.T": Y.UH_KEY, Y.HEDGE_T: Y.HG_KEY, BOND_T: BD_KEY}, "core_mode": "follow"},
            "extra_core": {BOND_T: frame},
            "extra_bear": {BD_KEY: Y.or_series(~bear_us.astype(bool), ~bond_on.astype(bool))}}


def held(bear_us: pd.Series, bond_on: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """idx 上「拿 1482」= 美股熊且债券牛（各自向后填；没有值 = 不拿）。"""
    import loop_r04_yensurge as Y
    idx = pd.DatetimeIndex(idx)
    m = (~Y.or_series(~bear_us.astype(bool), ~bond_on.astype(bool))).astype(float)
    return m.reindex(idx.union(m.index)).ffill().reindex(idx).fillna(0.0) > 0.5


def core_weights(bear: pd.Series, hedge: pd.Series, bond: pd.Series) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓：美股牛 → 纳指（对冲中 → 对冲版 h、否则 u）；美股熊且债券牛 → 债券 b；其余现金。"""
    b, h, o = bear.astype(bool), hedge.astype(bool), bond.astype(bool)
    return pd.DataFrame({"u": (~b & ~h).astype(float), "h": (~b & h).astype(float), "b": (b & o).astype(float)}, index=bear.index)


def segments(mask: pd.Series) -> int:
    v = mask.astype(bool).to_numpy()
    return int(v[0]) + int(((~v[:-1]) & v[1:]).sum()) if len(v) else 0


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def core_trades(e: str, W: dict) -> dict:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    out: dict = {}
    for x in eng.st.core_trades:
        if x[0] >= a and (b is None or x[0] < b):
            out[x[1]] = out.get(x[1], 0) + 1
    return out


def describe(W: dict, e: str, bond_on: pd.Series, close: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    days = close.index[(close.index >= pd.Timestamp(a)) & ((close.index < pd.Timestamp(b)) if b else True)]
    bus = W["bear"]["US"].astype(float).reindex(days.union(W["bear"]["US"].index)).ffill().reindex(days).fillna(0.0) > 0.5
    hd = held(W["bear"]["US"], bond_on, days)
    r = close.reindex(days).pct_change().fillna(0.0)
    hl = hd.shift(1, fill_value=False)                                      # 前一天定、当天拿
    return {"bear_pct": round(float(bus.mean() * 100), 1), "held_pct_of_bear": round(float(hd[bus].mean() * 100), 1) if bus.any() else None,
            "segments": segments(hd), "held_ret_pct": round(float((np.prod(1 + r[hl].to_numpy()) - 1) * 100), 2) if hl.any() else 0.0}


def old_core(W: dict, uni: pd.Series, use_bond: bool) -> dict:
    """只描述 + S7：1987〜2000 只有核心。纳指两种合成价与第 1 轮 / 第 15 轮 old_core 相同；债券 = 对冲版美债合成价（美国日期）、
    债券牛熊在美国日期上算、再晚一天用（FRED 收益率第二天公布）；持仓由前一天收盘的状态决定，换掉的比例 × 0.1%。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    import halloween_study as HW
    from qbreak import factors
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    ntr = EI.ndx_tr(inp)
    unh = EI.grow(ntr, -EI.FEE["1545.T"])
    unh = (unh * dex.reindex(unh.index.union(dex.index)).ffill().reindex(unh.index)).dropna()
    hed = FX.hedged_index(EI.grow(ntr, -0.22), factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9))
    bnd_us = bond_hedged(bond_usd())
    bnd_us = bnd_us[bnd_us.index >= pd.Timestamp(BOND_START)]
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, hed, bnd = unh.reindex(idx), ff(hed), ff(bnd_us)
    bear = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    hdg = ff(uni).fillna(0.0) > 0.5
    on = (ff(trend_on(bnd_us).shift(1, fill_value=False)).fillna(0.0) > 0.5) if use_bond else pd.Series(False, index=idx)
    w = core_weights(bear, hdg, on).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0) + w["b"] * bnd.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float(w["b"].mean() * 100), 1)
    return out


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r02_bondrefuge.py", "scripts/loop2_common.py",
                                 "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    close = bond_close(W["inp"])
    on = trend_on(close)
    ov = tbh_over(W["bear"]["US"], on, EI.frame_close(close))
    reg = R2.load_state().get("baseline") or {}
    base, cand, ctr, desc = {}, {"TBH": {}}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        ctr[e] = {"B1": core_trades(e, W)}
        base[e] = _acct(rb)
        base[e]["years"] = rb.get("years")
        rc = L2.run(W, e, **ov)
        ctr[e]["TBH"] = core_trades(e, W)
        cand["TBH"][e] = _acct(rc)
        cand["TBH"][e]["years"] = rc.get("years")
        desc[e] = describe(W, e, on, close)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, False), "TBH": old_core(W, uni, True)}
    unseen = None if old["B1"]["calmar"] is None or old["TBH"]["calmar"] is None else old["TBH"]["calmar"] - old["B1"]["calmar"]
    s1 = {"TBH": R2.stage1(cand["TBH"], base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base, "cand": cand,
           "stage1": s1, "drift": drift, "core_trades": ctr, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["TBH"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 2 轮：美股熊市里拿对冲版美国 7〜10 年国债 TBH（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r02_bondrefuge.py 开头）", "",
         f"- **TBH（美股熊且对冲版美债自己是牛 → 闲置资金拿 1482，否则同 B1）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | TBH（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TBH'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：美股熊的日子 {_f(d['bear_pct'], '{:.1f}')}%，其中拿 1482 {_f(d['held_pct_of_bear'], '{:.1f}')}%（{d['segments']} 段，"
                 f"拿着时 1482 合成价连乘 {_f(d['held_ret_pct'], '{:+.2f}')}%）；核心换仓 B1 {sum(c['B1'].values())} → TBH {sum(c['TBH'].values())} 笔"
                 f"（1482 {c['TBH'].get(BOND_T, 0)} 笔）")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["TBH"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（TBH − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心、日元计纳指 + FJE）：B1 的开关 {oc(o['B1'])}；TBH {oc(o['TBH'])}（拿债券的日子 {o['TBH']['bond_days_pct']}%）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(stage_one())
