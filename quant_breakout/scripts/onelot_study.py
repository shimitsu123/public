"""onelot_study.py — 「一手放宽」重新检验（2026-10-24 登记 = 本提交；之后不改规则、只运行一次）。

用户（2026-10-24）：「重新登记一次「一手放宽」的检验」。背景：现在每只个股按权益 25% 买（模拟账户约 ¥24.4 万），一手（100 股）放不进就跳过；
按 2026-10-23 收盘，日経225 里 140 只（62%）一手 > 名额。以前：scripts/capital_study.py（2026-09-26，yfinance、旧 S0C2）U2「一手 ≤ 权益 50%」通过 →
用户确认启用 → 生效前 J-Quants 口径事后更差、撤回（2026-09-27）；scripts/capital_scale_study.py（2026-10-12，旧 S0C2 + 1655）N1 四栏都变好但差一栏门槛。
这两次都不是现在的规则（没有 TBF、核心是 1655）→ 这次用现在的基准 B4 重测。照实写：以前的结果都看过 → 这次按「事后」，门槛照第十二个循环的量级。

〇 基准 B4 = 第十二个循环的 B4（scripts/loop12_common.run_b4：B3 + TBF，判断层、W2 + C、X6、4 个名额 × 25%、单只 ≤ 34%、核心 1545 / 1482 Q1B、立花费用）。
   候选 = 同一个 B4，只改引擎参数 one_lot_cap_pct（qbreak/unified.py：按名额买不到一手、但一手 ≤ 权益 × 这个比例 × min(1, 宏观倍数) 且现金够 → 买一手；
   执行器用的是同一个引擎、同一个参数 var/sim.json unified.one_lot_cap_pct）：
   L50 = 0.50（主候选 = 9 月的 U2）；L34 = 0.34（= 单只上限）、L100 = 1.00 —— 只描述，不能凭这次采用。
一 口径：J 年代（2017-01〜2026-09；J-Quants 行情、一手按当时真实股价、退市卖出）是唯一真实的检验；Z / E 年代的一手按复权后的价格（以前的价格被
   之后的拆股调低 → 一手看起来便宜，「一手太贵」几乎不出现）→ 只看「不变差」。资金 ¥100 万（sim.json），另测 ¥80 万 / ¥120 万（起点资金不同、
   哪些票买得起不同 → 看结果是不是碰巧）。
二 L50「通过」= 同时满足（事先写定）：
   P1 J Calmar ≥ B4 + 0.03；P2 J 前半 / 后半 Calmar 都 ≥ B4 − 0.02；P3 J 最大回撤不比 B4 深 2 pp 以上；
   P4 ¥80 万、¥120 万起点：J Calmar 都 ≥ 同资金的 B4；P5 多买到的交易（L50 有、B4 没有的：同一只票同一个买入日）≥ 5 笔且每笔平均净收益 > 0；
   P6 Z / E：Calmar 都 ≥ B4 − 0.02。
   通过 → 只提议「先加前向记录（影子账户）」，用户决定；不改模拟盘 / 执行器。不过 → 维持现行（one_lot_cap_pct = 0）。
三 另外描述：「一手太贵」跳过数、个股笔数 / 胜率、多买到的交易的明细（票、买入日、占当时权益 %、净收益 %、盈亏 ¥）、单只最大占权益 %、
   多买到的交易里最大的一笔亏损（¥ 与占权益 %）。
四 局限：税前；样本只有一个真实年代（约 10 年、B4 57 笔）；高价股的一手占比大 → 单只集中，回测的平均掩盖个别大亏的风险。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402

VARIANTS = {"L50": 0.50, "L34": 0.34, "L100": 1.00}
PRIMARY = "L50"
CAPITALS = (800_000, 1_200_000)
CAL_UP, HALF_TOL, DD_TOL, ERA_TOL, MIN_EXTRA = 0.03, 0.02, 2.0, 0.02, 5
CORE = {"1545.T", "1482.T", "1655.T"}


def run_one(W: dict, e: str, cap: float | None = None, capital: float | None = None) -> dict:
    """B4（cap / capital 都是 None）或 B4 + 一手放宽 → {acct, trades, skipped, history}。"""
    import jq_study as JS
    import loop6_common as L6
    import loop9_common as C9
    S = LC.signals(W, e)
    tick = C9.tick_of(S["ticker"], S["date"], np.asarray(W["tbf"][e], bool))
    co = {}
    if cap is not None:
        co["one_lot_cap_pct"] = float(cap)
    if capital is not None:
        co["capital_jpy"] = float(capital)
    kw = {"em_tick": tick} if tick else {}
    if co:
        kw["cfg_over"] = co
    a = C9.acct(L6.run(W, e, **kw))
    eng = JS.RealLotEngine.LAST[-1]
    tr = pd.DataFrame(eng.st.trades)
    if len(tr):
        tr = tr[(tr["reason"] != "end") & (~tr["ticker"].isin(CORE))].copy()
    hist = pd.Series({pd.Timestamp(h[0]): float(h[1]) for h in eng.st.history if h[0]})
    return {"acct": a, "trades": tr, "skipped": {k: int(v) for k, v in eng.skipped.items()}, "history": hist}


def in_window(tr: pd.DataFrame, W: dict, e: str) -> pd.DataFrame:
    a, b = W["ctx"][e]["windows"][e]
    if not len(tr):
        return tr
    d = pd.to_datetime(tr["entry_date"])
    return tr[((d >= pd.Timestamp(a)) & ((d <= pd.Timestamp(b)) if b else True)).to_numpy()]


def net_pct(tr: pd.DataFrame) -> np.ndarray:
    if not len(tr):
        return np.array([])
    return tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100


def weight_pct(tr: pd.DataFrame, hist: pd.Series) -> np.ndarray:
    """买入金额 ÷ 买入日（前一天收盘后）的权益 %。"""
    if not len(tr) or not len(hist):
        return np.full(len(tr), np.nan)
    h = hist.sort_index()
    out = []
    for d, s, p in zip(pd.to_datetime(tr["entry_date"]), tr["shares"].astype(float), tr["entry_px"].astype(float)):
        k = int(h.index.searchsorted(d, side="left")) - 1
        out.append(s * p / h.iloc[k] * 100 if k >= 0 else np.nan)
    return np.array(out, float)


def extra_trades(cand: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    if not len(cand):
        return cand
    key = set(zip(base["ticker"], base["entry_date"])) if len(base) else set()
    return cand[[(t, d) not in key for t, d in zip(cand["ticker"], cand["entry_date"])]]


def judge(J: dict, BJ: dict, cap_res: dict, extra_net: np.ndarray, ze: dict, bze: dict) -> dict:
    """J / BJ = 候选 / B4 的 J 账户；cap_res = {资金: (候选 Calmar, B4 Calmar)}；ze / bze = {Z / E: Calmar}。"""
    def ok(x):
        return x is not None and np.isfinite(float(x))
    c, b = J.get("calmar"), BJ.get("calmar")
    p = {"P1": ok(c) and ok(b) and c >= b + CAL_UP - 1e-9,
         "P2": all(ok(J.get(h)) and ok(BJ.get(h)) and J[h] >= BJ[h] - HALF_TOL - 1e-9 for h in ("h1", "h2")),
         "P3": ok(J.get("dd")) and ok(BJ.get("dd")) and J["dd"] >= BJ["dd"] - DD_TOL - 1e-9,
         "P4": bool(cap_res) and all(ok(x) and ok(y) and x >= y - 1e-9 for x, y in cap_res.values()),
         "P5": len(extra_net) >= MIN_EXTRA and float(np.mean(extra_net)) > 0,
         "P6": all(ok(ze.get(e)) and ok(bze.get(e)) and ze[e] >= bze[e] - ERA_TOL - 1e-9 for e in ("Z", "E"))}
    return {"checks": {k: bool(v) for k, v in p.items()}, "pass": bool(all(p.values()))}


def summarize(r: dict, W: dict, e: str) -> dict:
    tr = in_window(r["trades"], W, e)
    n = net_pct(tr)
    w = weight_pct(tr, r["history"])
    return {"acct": r["acct"], "lot_skips": r["skipped"].get("lot", 0), "n": int(len(tr)),
            "win": float((n > 0).mean() * 100) if len(n) else None, "mean": float(n.mean()) if len(n) else None,
            "max_w": float(np.nanmax(w)) if len(w) and np.isfinite(w).any() else None}


def run(say=print) -> dict:
    import loop12_r01_fund as R1
    t0 = time.time()
    code, dirty = R1.git_head()
    W = LC.load()
    res = {"code": code, "dirty": dirty, "base": {}, "cand": {}, "extra": {}, "capital": {}, "judge": {}}
    B = {e: run_one(W, e) for e in LC.ERAS}
    ref = {e: LC.run_b4(W, e) for e in LC.ERAS}
    res["wiring"] = {e: B[e]["acct"] == ref[e] for e in LC.ERAS}
    zero = {e: run_one(W, e, cap=0.0)["acct"] == ref[e] for e in LC.ERAS}
    res["wiring_zero"] = zero
    if not all(res["wiring"].values()) or not all(zero.values()):
        raise RuntimeError(f"接线核对没过：{res['wiring']} / {zero}")
    res["base"] = {e: summarize(B[e], W, e) for e in LC.ERAS}
    BC = {cap: run_one(W, "J", capital=cap) for cap in CAPITALS}
    res["base_capital"] = {str(c): summarize(BC[c], W, "J") for c in CAPITALS}
    say(f"B4 完成（{time.time() - t0:.0f}s）")
    for k, cap in VARIANTS.items():
        C = {e: run_one(W, e, cap=cap) for e in LC.ERAS}
        res["cand"][k] = {e: summarize(C[e], W, e) for e in LC.ERAS}
        trJ, bJ = in_window(C["J"]["trades"], W, "J"), in_window(B["J"]["trades"], W, "J")
        ex = extra_trades(trJ, bJ)
        gone = extra_trades(bJ, trJ)
        en, gn = net_pct(ex), net_pct(gone)
        ew = weight_pct(ex, C["J"]["history"])
        rows = []
        for (t, d, pnl), nn, ww in zip(ex[["ticker", "entry_date", "pnl_jpy"]].itertuples(index=False), en, ew):
            rows.append({"ticker": t, "entry": str(d), "w": None if not np.isfinite(ww) else round(float(ww), 1), "net": round(float(nn), 2),
                         "pnl_jpy": float(pnl), "loss_w": None})
        hist = C["J"]["history"].sort_index()
        for r_ in rows:
            k_ = int(hist.index.searchsorted(pd.Timestamp(r_["entry"]), side="left")) - 1
            r_["loss_w"] = round(r_["pnl_jpy"] / hist.iloc[k_] * 100, 2) if k_ >= 0 else None
        res["extra"][k] = {"n": int(len(ex)), "mean": float(en.mean()) if len(en) else None, "win": float((en > 0).mean() * 100) if len(en) else None,
                           "sum_jpy": float(ex["pnl_jpy"].sum()) if len(ex) else 0.0, "rows": rows,
                           "gone_n": int(len(gone)), "gone_mean": float(gn.mean()) if len(gn) else None}
        CC = {cap_: run_one(W, "J", cap=cap, capital=cap_) for cap_ in CAPITALS}
        res["capital"][k] = {str(c): summarize(CC[c], W, "J") for c in CAPITALS}
        cap_res = {c: (CC[c]["acct"]["calmar"], BC[c]["acct"]["calmar"]) for c in CAPITALS}
        res["judge"][k] = judge(C["J"]["acct"], B["J"]["acct"], cap_res, en,
                                {e: C[e]["acct"]["calmar"] for e in ("Z", "E")}, {e: B[e]["acct"]["calmar"] for e in ("Z", "E")})
        say(f"{k} 完成（{time.time() - t0:.0f}s）")
    res["seconds"] = round(time.time() - t0)
    return res


def _f(x, f="{:.3f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def report(res: dict) -> str:
    j = res["judge"][PRIMARY]
    L = [f"# 「一手放宽」重新检验（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；"
         f"规则 scripts/onelot_study.py）", "",
         f"**主候选 {PRIMARY}（一手 ≤ 权益 50%）：{'通过 → 提议先加前向记录（用户决定）' if j['pass'] else '不通过 → 维持现行'}**　"
         + "、".join(f"{k} {'✓' if v else '✗'}" for k, v in j["checks"].items()), "",
         "| 方案 | 年代 | 年化 / 最大回撤 / Calmar | 前半 / 后半 Calmar | 一手太贵跳过 | 个股笔数 / 胜率 / 每笔 | 单只最大占权益 |", "|---|---|---|---|---|---|---|"]
    rows = [("B4 现行", res["base"])] + [(f"{k}（一手 ≤ {int(v * 100)}%）", res["cand"][k]) for k, v in VARIANTS.items()]
    for nm, S in rows:
        for e in LC.ERAS:
            s = S[e]
            a = s["acct"]
            L.append(f"| {nm} | {e} | {_f(a.get('cagr'), '{:.2f}')}% / {_f(a.get('dd'), '{:.2f}')}% / {_f(a.get('calmar'))} | {_f(a.get('h1'))} / {_f(a.get('h2'))} | "
                     f"{s['lot_skips']} | {s['n']} / {_f(s['win'], '{:.1f}')}% / {_f(s['mean'], '{:+.2f}')}% | {_f(s['max_w'], '{:.1f}')}% |")
    L += ["", "## 起点资金不同（J 年代 Calmar）", "| 方案 | " + " | ".join(f"¥{c // 10000} 万" for c in CAPITALS) + " |", "|---|" + "---|" * len(CAPITALS)]
    L.append("| B4 现行 | " + " | ".join(_f(res["base_capital"][str(c)]["acct"]["calmar"]) for c in CAPITALS) + " |")
    for k in VARIANTS:
        L.append(f"| {k} | " + " | ".join(_f(res["capital"][k][str(c)]["acct"]["calmar"]) for c in CAPITALS) + " |")
    L += ["", "## J 年代多买到的交易（候选有、B4 没有的）"]
    for k in VARIANTS:
        x = res["extra"][k]
        worst = min(x["rows"], key=lambda r: r["pnl_jpy"]) if x["rows"] else None
        L.append(f"- {k}：{x['n']} 笔、每笔 {_f(x['mean'], '{:+.2f}')}%、胜率 {_f(x['win'], '{:.1f}')}%、合计 {x['sum_jpy']:+,.0f} 円；"
                 f"因此没买的（B4 有、候选没有）{x['gone_n']} 笔、每笔 {_f(x['gone_mean'], '{:+.2f}')}%"
                 + (f"；最大的一笔亏损 {worst['ticker']} {worst['entry']} {worst['pnl_jpy']:+,.0f} 円（占当时权益 {_f(worst['loss_w'], '{:+.2f}')}%、买入时占 {_f(worst['w'], '{:.1f}')}%）"
                    if worst and worst["pnl_jpy"] < 0 else ""))
    x = res["extra"][PRIMARY]
    if x["rows"]:
        L += ["", f"{PRIMARY} 多买到的明细：", "| 票 | 买入日 | 买入时占权益 | 净收益 | 盈亏 | 占当时权益 |", "|---|---|---|---|---|---|"]
        for r in sorted(x["rows"], key=lambda r: r["entry"]):
            L.append(f"| {r['ticker']} | {r['entry']} | {_f(r['w'], '{:.1f}')}% | {r['net']:+.2f}% | {r['pnl_jpy']:+,.0f} 円 | {_f(r['loss_w'], '{:+.2f}')}% |")
    L += ["", "J = 2017-01〜2026-09（J-Quants 行情、一手按当时真实股价）；Z / E 的一手按复权价格（几乎不出现「一手太贵」）→ 只看不变差。",
          f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    return "\n".join(L)


def main(argv=None) -> int:
    from qbreak import paths
    res = run()
    text = report(res)
    print(text)
    (paths.out_dir() / "onelot_study.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / "onelot_study.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
