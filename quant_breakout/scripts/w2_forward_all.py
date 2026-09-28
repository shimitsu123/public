"""w2_forward_all.py — W2 的全市场前向检验（2026-09-27 事先登记；用户：「登记 W2 前向记录，加全市场版」）。

来由：W2（周线量比 ≥ 1.0 的突破才买，2026-09-27 启用）的证据都来自看过多次的历史数据（allstock_posthoc：全市场 2016〜2026
每笔 +0.25% vs +0.10%，11 年里 9 年更好；成交额低的三分之一没有效果）。日経225 + 扩大池的每日记录（scripts/score_forward.py 第八节）
每年只有约 250 笔，要很多年才有结论 → 这里在全市场（每年约 1,000 笔）上用**登记之后才发生的数据**检验，规则现在写定，以后不改。

一、对象
  东证一般市场（プライム / スタンダード / グロース）的内国普通股：信号日严格早于那天的最近一个月末上市一览（scripts/allstock_data.py
  同一口径；TOKYO PRO MARKET 与 ETF 等不算）；信号 = 现行突破（参数 = 复核时的现行日本参数去掉 W2，与 score_forward 第八节同一口径），
  信号日 ≥ 2026-09-28。
  主：信号日的 20 天平均成交额（收盘 × 成交量，allstock_study 的 lturn）≥ ¥500 万；另报：不限成交额的全部。
二、结果：每只票单独、一次一仓、现行卖出规则、扣立花 ¥25 万一笔的来回成本（allstock_study.train_all 同一套）；只算已平仓的。
三、分组：W2 保留（周线量比 ≥ 1.0 或缺值）/ 挡掉（< 1.0）；周线量比 = qbreak/mtf.py weekly_volume_ratio（东证日历补下一个交易日），
  与实盘 W2 同一个定义；门槛 1.0 在这里写定，不跟着参数变。
四、判定（每年一次：复核日第一次到达 2027-09-28、2028-09-28、2029-09-28、2030-09-28、2031-09-28 之后的那次复核；其他时候只报告进度）
  差 = 保留 − 挡掉的每笔平均净收益 pp；区间 = 按信号月聚类的自助法 2,000 次（种子 20260927）。都用主对象（成交额 ≥ ¥500 万）：
  失效警报：「挡掉 − 保留」的 95% 区间下限 > 0 → 提议关掉 W2；
  证实：「保留 − 挡掉」的 99% 区间下限 > 0 → 记为「新数据证实 W2」。
  另报（不判定）：不限成交额的全部、日経225（今天的成分）与其他、各年的笔数 / 胜率 / 每笔。
  检出力（每年约 1,000 笔、每笔标准差约 5.9%、保留约 45%；80%）：每笔差 1 pp 约 1〜1.3 年、0.5 pp 约 4.5 年、0.3 pp 约 12 年。
  警报 / 证实都只是提议：改模拟盘与执行器要用户在对话里确认，并记 var/sim_changes.md。
五、数据：J-Quants（批量日线 + 月末上市一览）；复核时先补齐本地缓存（原始数据只在 var/cache/jquants/，不入库）。
  输出（只有统计）：var/out/w2_forward_all_review.md / .json；var/out/w2_forward_all_history.csv（只追加：每次复核一行、判定过的年份）。
六、复核：python scripts/w2_forward_all.py --review（要 J-Quants 的键；Mac：bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python
  scripts/w2_forward_all.py --review）。
七、追加登记 K2 / USW（2026-09-27 同日；用户「F 前向记录」；定义 qbreak/idio_forward.py，与 scripts/score_forward.py 第九节同一规则）
  每笔登记之后的交易另算：突破日量比（J-Quants 成交量，之前 20 日均量）、对日経225 的 β（信号周之前一周为止 104 周的周收益回归，
  日経225 用 yfinance）、K2 标记；所在東証 33 业种（复核时最新的月末上市一览 S33Nm）→ 美国对应行业 12 个月强弱百分位、USW 标记。
  假设与判定（主对象）：K2：全部突破里 K2 = 1 的每笔净收益 > 其余；USW：W2 保留里 USW = 1 的 > 其余（us12 缺值不算）；
  每年一次（与 W2 同一组日期）：证实 = 99% 区间下限 > 0；否定 = 反向 95% 区间下限 > 0；其他时候只报告进度。另报日経225 / 其他。
  检出力（主对象每年约 1,000 笔）：K2 差 1.5 pp、USW 差 2 pp 各约 1 年。证实 / 否定都只是记录，改规则要另写登记的研究并经用户确认。
八、追加登记 卖法 X6「吊灯止损」（2026-09-28，用户「㉛ 选 ① 走前向记录」；与 scripts/score_forward.py 第十节同一做法，qbreak/exit_forward.py）
  - 对象：复核时用同一份 J-Quants 行情，给登记之后有已平仓交易的票重建指标表（现行参数去掉 W2），信号日 ≥ 2026-09-28、上市一览是一般市场
    的日子的全部突破；每个信号单独配对模拟（现行 / 只把死叉换成吊灯止损：最高价从买入价起算、当天的 Wilder ATR14、k = 3；其余卖法两边相同），
    只用成熟的配对（信号日之后 ≥ 65 根 K 线、两边都已平仓）。W2 标记（周线量比 ≥ 1.0 或缺值 = 保留）与主对象（成交额 ≥ ¥500 万）同第一〜三节。
  - 主假设（事先方向：X6 每笔 > 现行）：主对象里 W2 保留的成熟配对，配对差（X6 − 现行 的净收益 pp）的平均；
    区间 = 按信号月聚类的自助法 2,000 次（种子 20260928）。判定（每年一次，与 W2 同一组日期 2027-09-28 … 2031-09-28 之后的那次复核；
    做过的年份不再做）：证实 = 99% 区间下限 > 0；否定 = 95% 区间上限 < 0（→ 结束跟踪，记录照留）；其他 = 未定。
  - 次假设（只报告倾向，不单独作为任何依据）：主对象里不管 W2 的全部突破，配对差的 95% 区间下限 > 0。
    另报（不判定）：不限成交额（W2 保留）、主对象里的日経225 股票池（W2 保留）；两边的胜率 / 每笔 / 持有中位、X6 的出场原因。
  - 检出力（按 E / J 校准外推，scripts/x6_forward_calib.py；99% 下限 > 0、80%）：主对象 W2 保留每年约 450 笔 → 差 1 pp 约 1.6〜2 年、
    0.5 pp 约 6〜8 年；不管 W2 的全部每年约 1,000 笔 → 差 1 pp 约 0.6〜0.9 年。小盘股波动更大，实际多半更慢。
  - 证实也只是记录：改模拟盘另写一份事先登记的组合研究，并经用户确认。算不了（例外）→ 报告里写原因，不影响第一〜七节。
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import exit_forward as EF                                        # noqa: E402
from qbreak import idio_forward as IF                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import w2_forward as W2F                                         # noqa: E402

FORWARD_START = "2026-09-28"
W2_CUT = 1.0
LIQ_MIN_YEN = 5_000_000
JUDGE_DATES = ("2027-09-28", "2028-09-28", "2029-09-28", "2030-09-28", "2031-09-28")
BOOT_N, SEED = 2000, 20260927

LIQ_LOG = math.log10(LIQ_MIN_YEN)                                             # allstock_study 的 lturn = log10(20 天平均成交额)
HIST = "w2_forward_all_history.csv"
LINES: list[str] = []
assert W2_CUT == W2F.W2_CUT and JUDGE_DATES == W2F.JUDGE_DATES and (BOOT_N, SEED) == (W2F.BOOT_N, W2F.SEED)   # 登记值与共用模块一致
assert IF.JUDGE_DATES == JUDGE_DATES and EF.JUDGE_DATES == JUDGE_DATES


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_ends(after, until) -> list[str]:
    """after 之后、until 为止每个月的最后一个东证交易日（要补的月末上市一览）。"""
    from qbreak.calendar_jp import is_trading_day, prev_trading_day
    a, u = pd.Timestamp(after), pd.Timestamp(until)
    out = []
    for p in pd.period_range(a.to_period("M"), u.to_period("M"), freq="M"):
        d = p.to_timestamp(how="end").date()
        if not is_trading_day(d):
            d = prev_trading_day(d)
        if a < pd.Timestamp(d) <= u:
            out.append(d.isoformat())
    return out


def refresh(log=print, today=None) -> dict:
    """补齐 J-Quants 缓存：批量日线（已下载且没变的跳过）+ 新的月末上市一览。原始数据只在缓存目录（不入库）。"""
    from qbreak import jq_data as JD
    from qbreak import pit_data as PD
    from qbreak import jquants as JQ
    c = JQ.JQuants()
    files = JD.bulk_download(c, "/equities/bars/daily", log=log)
    have = PD.master_files()
    new = month_ends(max(have) if have else pd.Timestamp(FORWARD_START) - pd.Timedelta(days=40),
                     pd.Timestamp(today) if today is not None else pd.Timestamp.today())
    for d in new:
        JQ.master_cached(c, d)
    return {"bar_files": len(files), "new_snapshots": new}


def forward_trades(T: pd.DataFrame) -> pd.DataFrame:
    """allstock_study.train_all 的交易 → 信号日 ≥ FORWARD_START 的已平仓交易 + W2 标记 + 是否主对象（成交额 ≥ ¥500 万）。"""
    if not len(T):
        return T.assign(w2_keep=pd.Series(dtype=int), main=pd.Series(dtype=bool))
    F = T[pd.to_datetime(T["sig_date"]) >= pd.Timestamp(FORWARD_START)].copy()
    F["sig_date"] = pd.to_datetime(F["sig_date"])
    F["w2_keep"] = W2F.keep_flag(F["w5v"])
    F["main"] = F["lturn"].to_numpy(float) >= LIQ_LOG                        # 缺值 → 不是主对象
    return F.reset_index(drop=True)


def s33_of(s33: dict[str, str], t: str) -> str | None:
    """交易表的代码（4 位 + .T 或 5 位）→ 上市一览的 33 业种名。"""
    c = str(t).split(".")[0]
    return s33.get(t) or s33.get(c) or s33.get(c + "0") or s33.get(c[:4]) if s33 else None


def s33_map_from_master() -> dict[str, str]:
    """复核时最新的月末上市一览 → {代码: 33 业种名}（5 位代码与 4 位 + .T 都放进去）。"""
    from qbreak import pit_data as PD
    files = PD.master_files()
    if not files:
        return {}
    m = pd.read_csv(files[max(files)], dtype=str)
    out = {}
    for code, name in zip(m["Code"].astype(str), m["S33Nm"].astype(str)):
        out[code] = name
        if len(code) == 5 and code.endswith("0"):
            out[code[:4] + ".T"] = name
    return out


def idio_all(F: pd.DataFrame, A: dict, mkt_close: pd.Series | None, us_pct: pd.DataFrame | None, s33: dict[str, str] | None) -> pd.DataFrame:
    """第七节：登记之后的每笔交易 → vr1、b_n225、k2_keep、us12、usw_keep（qbreak/idio_forward.py 同一定义；面板 = A 的 C / V）。"""
    if not len(F):
        return F.assign(**{c: pd.Series(dtype=float) for c in IF.COLS})
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    V = pd.DataFrame(A["V"], index=days, columns=names)
    VR = V / V.shift(1).rolling(20, min_periods=15).mean()
    C = pd.DataFrame(A["C"], index=days, columns=names)
    Yw = C.resample("W-FRI").last().pct_change(fill_method=None).clip(-0.5, 0.5)
    m_w = IF.weekly_returns(mkt_close) if mkt_close is not None else None
    vr, bt, us = [], [], []
    for t, d in zip(F["ticker"], pd.to_datetime(F["sig_date"])):
        v = VR.at[d, t] if (t in VR.columns and d in VR.index) else np.nan
        vr.append(round(float(v), 4) if np.isfinite(v) else np.nan)
        b = IF.beta_asof(Yw[t], m_w, d) if (m_w is not None and t in Yw.columns) else float("nan")
        bt.append(round(b, 4) if np.isfinite(b) else np.nan)
        u = IF.us12_at(us_pct, s33_of(s33 or {}, t), d)
        us.append(round(u, 4) if np.isfinite(u) else np.nan)
    out = F.copy()
    out["vr1"], out["b_n225"], out["k2_keep"] = vr, bt, IF.k2_flag(vr, bt)
    out["us12"], out["usw_keep"] = us, IF.usw_flag(us)
    return out


def x6_pairs(A: dict, T: pd.DataFrame, p, mk: pd.DataFrame) -> pd.DataFrame:
    """第八节：T（登记之后的已平仓交易）里出现过的票 → 用同一份行情重建指标表 → 这些票信号日 ≥ FORWARD_START、上市一览是一般市场的
    日子的全部突破，逐个配对模拟 现行 / X6（qbreak/exit_forward.py）；每个信号带上 w5v、w2_keep、lturn、main（成交额 ≥ ¥500 万）。
    成熟的信号（之后 ≥ 65 根 K 线）一定有更早或同一笔已平仓交易 → 这些票覆盖全部成熟信号。"""
    import allstock_study as S
    import candle_study as CS_
    import pit_retrain_study as PRS
    from qbreak.config import BacktestConfig
    cols = ["ticker", "sig_date", "w5v", "lturn", "w2_keep", "main"]
    if not len(T):
        return pd.DataFrame(columns=cols + ["status", "mature"])
    names = list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    idx = [col[t] for t in sorted(set(T["ticker"])) if t in col]
    sub = {x: np.asarray(A[x][:, idx], np.float64) for x in "OHLCV"}
    fr = CS_.frames_from(sub, A["days"], [names[j] for j in idx], list(range(len(idx))), p, {"listed": A["listed"][:, idx]})
    bt = BacktestConfig.for_market("JP", 21, "tachibana")                     # 与 candle_posthoc.trades 相同（每只票单独、一次一仓）
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rt = bt.exec_cfg.fee(PRS.NOTIONAL) * 2 / PRS.NOTIONAL * 100
    rows = []
    for t, df in fr.items():
        e = df["entry"].to_numpy(bool) & df["listed"].to_numpy(bool) & np.asarray(df.index >= pd.Timestamp(FORWARD_START))
        if not e.any():
            continue
        f = S.stock_features(df, mk)
        for d in df.index[e]:
            rows.append({"ticker": t, "sig_date": d, "w5v": f.at[d, "w5v"], "lturn": f.at[d, "lturn"]})
    if not rows:
        return pd.DataFrame(columns=cols + ["status", "mature"])
    sig = pd.DataFrame(rows)
    sig["w2_keep"] = W2F.keep_flag(sig["w5v"])
    sig["main"] = sig["lturn"].to_numpy(float) >= LIQ_LOG                    # 缺值 → 不是主对象
    return EF.pairs_frame(fr, sig, p, bt, rt, date_col="sig_date")


def x6_eval(P: pd.DataFrame, hist: pd.DataFrame | None, today, n225: set[str]) -> dict:
    """第八节：主 = 主对象里 W2 保留的成熟配对，每年一次判定；次 = 主对象里不管 W2 的全部（95%，只报告倾向）；另报不判定。"""
    if not len(P):
        P = pd.DataFrame(columns=["ticker", "sig_date", "w2_keep", "main", "status", "mature"])
    main = P["main"].astype(bool).to_numpy()
    keep = pd.to_numeric(P["w2_keep"], errors="coerce").to_numpy(float) == 1
    nn = P["ticker"].isin(n225).to_numpy()
    ev = EF.evaluate(P[main & keep], date_col="sig_date")
    year = W2F.due_date(today, EF.JUDGE_DATES, W2F.history_done(hist, "all_X6", "x6_year"))
    sec = EF.evaluate(P[main], date_col="sig_date")
    side = {"不限成交额（W2 保留）": EF.evaluate(P[keep], date_col="sig_date"),
            "主对象里的日経225 股票池（W2 保留）": EF.evaluate(P[main & keep & nn], date_col="sig_date")}
    return {"eval": ev, "year": year, "secondary": sec, "sec_ok": bool(sec.get("lo95") is not None and sec["lo95"] > 0) if year else None,
            "side": side}


def decide(ev: dict, hist: pd.DataFrame | None, today) -> dict:
    """每年一次（JUDGE_DATES）：失效警报 95% / 证实 99%；判定过的年份记进历史，不再判定。"""
    year = W2F.due_date(today, JUDGE_DATES, W2F.history_done(hist, "all", "w2_year"))
    return {"year": year, "alarm": W2F.alarm(ev) if year else None, "confirmed": W2F.confirmed(ev) if year else None}


def by_year(F: pd.DataFrame) -> dict:
    out = {}
    for y, g in F.groupby(F["sig_date"].dt.year):
        k = g["w2_keep"].to_numpy(int)
        out[int(y)] = {"keep": W2F.stat(g.loc[k == 1, "net"]), "drop": W2F.stat(g.loc[k == 0, "net"])}
    return out


def review(fetch: bool = True) -> int:
    import allstock_data as AD
    import allstock_study as S
    from bullbear_study import SYM, load
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    today = pd.Timestamp.today().normalize()
    info = refresh(log=lambda s: print(s, file=sys.stderr, flush=True)) if fetch else {"skipped": "没有补数据（--no-fetch）"}
    A = AD.load(rebuild=fetch)
    last_bar = A["days"][-1]
    p = SF.no_w2_params(load_params(market="JP"))
    jp_close = load(*SYM["JP"])["Close"]
    mk = S.market_frame(jp_close)
    T, n_st = S.train_all(A, p, mk, start=FORWARD_START)
    F = forward_trades(T)
    x6_note = []
    try:                                                                      # 第八节：卖法 X6 的配对（算不了 → 另报原因，不影响 W2 / K2 / USW）
        PX = x6_pairs(A, T, p, mk)
    except Exception as e:                                                    # noqa: BLE001
        PX = None
        x6_note.append(f"X6 的配对这次算不了：{type(e).__name__}: {e}")
    idio_note = []
    us_pct = s33 = None
    try:                                                                      # 第七节：K2 / USW 的输入（取不到 → 对应列为空，另报原因）
        from qbreak import factors as FX
        us_pct = IF.us_rank_asof(FX.ff_industries(49, "vw"))
    except Exception as e:                                                    # noqa: BLE001
        idio_note.append(f"美国 49 行业取不到：{type(e).__name__}: {e}")
    try:
        s33 = s33_map_from_master()
    except Exception as e:                                                    # noqa: BLE001
        idio_note.append(f"上市一览的业种取不到：{type(e).__name__}: {e}")
    F = idio_all(F, A, jp_close, us_pct, s33)
    del A
    n225 = set(universe("JP", "broad"))
    F["n225"] = F["ticker"].isin(n225)
    M = F[F["main"]]
    ev = W2F.evaluate(M, date_col="sig_date")
    hist_fp = paths.out_dir() / HIST
    hist = pd.read_csv(hist_fp) if hist_fp.exists() else pd.DataFrame()
    V = decide(ev, hist, today)
    x6 = x6_eval(PX, hist, today, n225) if PX is not None else None
    side = {"全部（不限成交额）": W2F.evaluate(F, date_col="sig_date", n=0) if len(F) else {"n": 0},
            "主对象里的日経225 股票池": W2F.evaluate(M[M["n225"]], date_col="sig_date", n=0) if len(M) else {"n": 0},
            "主对象里的其他股票": W2F.evaluate(M[~M["n225"]], date_col="sig_date", n=0) if len(M) else {"n": 0}}
    say(f"# W2 全市场前向检验复核（{today.date()}）")
    say(f"规则见 scripts/w2_forward_all.py 开头（2026-09-27 登记）。数据到 {last_bar.date()}；{n_st} 只里信号日 ≥ {FORWARD_START} 的已平仓交易 "
        f"{len(F)} 笔（主对象 = 20 天平均成交额 ≥ ¥{LIQ_MIN_YEN / 1e4:.0f} 万：{len(M)} 笔）。")
    say("\n## 主对象：W2 保留 vs 挡掉")
    say(W2F.summary_line(ev) if ev["n"] else "还没有已平仓的信号")
    lines = W2F.verdict_lines(ev, f"{V['year']} 这一年" if V["year"] else None, f"{V['year']} 这一年" if V["year"] else None)
    for x in lines:
        say(f"- {x}")
    if not lines:
        nxt = next((d for d in JUDGE_DATES if pd.Timestamp(d) > today), None)
        say(f"只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "五次年度判定都已做完（只报告）")
    say("\n## 另报（不判定）")
    for k, e in side.items():
        say(f"- {k}：" + (W2F.summary_line(e) if e.get("n") else "0 笔"))
    idio = IF.review_pair(M, hist, today, scope_prefix="all_", date_col="sig_date", seg_col=None)
    say("\n## K2 / USW（第七节，主对象）：标记 vs 其余")
    for x in IF.say_lines(idio, today=today):
        say(x)
    if len(M):
        f2 = lambda s: f"{s['n']} 笔 {s['mean']:+.2f}%" if s.get("n") else "0 笔"                                 # noqa: E731
        for key, col, base_ in (("K2", "k2_keep", M), ("USW", "usw_keep", M[pd.to_numeric(M["w2_keep"], errors="coerce") == 1])):
            kv = pd.to_numeric(base_[col], errors="coerce").to_numpy(float)
            say(f"  - {key} 分段（只描述）：" + "；".join(
                f"{g} 标记 {f2(W2F.stat(base_.loc[m & (kv == 1), 'net']))} / 其余 {f2(W2F.stat(base_.loc[m & (kv == 0), 'net']))}"
                for g, m in (("日経225", base_["n225"].to_numpy(bool)), ("其他", ~base_["n225"].to_numpy(bool)))))
    for x in idio_note:
        say(f"  - {x}")
    say("\n## 卖法 X6（第八节，主对象、W2 保留、成熟配对）：同一个信号 现行 vs 吊灯止损")
    if x6 is not None:
        say(EF.summary_line(x6["eval"]))
        lines = EF.verdict_lines(x6["eval"], f"{x6['year']} 这一年" if x6["year"] else None)
        for x in lines:
            say(f"- {x}")
        if not lines:
            nxt = next((d for d in JUDGE_DATES if pd.Timestamp(d) > today), None)
            say(f"只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "五次年度判定都已做完（只报告）")
        sec = x6["secondary"]
        say(f"- 次假设（主对象里不管 W2 的全部，95%，只报告倾向）：{EF.summary_line(sec)}"
            + (f" → 这一年{'倾向成立' if x6['sec_ok'] else '倾向不成立'}" if x6["year"] else ""))
        for k, e in x6["side"].items():
            say(f"- 另报 {k}：{EF.summary_line(e)}")
    for x in x6_note:
        say(f"- {x}")
    yr = by_year(M) if len(M) else {}
    if yr:
        say("\n| 信号年 | W2 保留 | 挡掉 |")
        say("|---|---|---|")
        f = lambda s: f"{s['n']} 笔 / {s['win']:.1f}% / {s['mean']:+.2f}%" if s.get("n") else "—"             # noqa: E731
        for y, v in yr.items():
            say(f"| {y} | {f(v['keep'])} | {f(v['drop'])} |")
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"\n代码版本 {code}；用时 {time.time() - t0:.0f}s")
    out = paths.out_dir() / "w2_forward_all_review"
    Path(f"{out}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{out}.json").write_text(json.dumps({"run": str(today.date()), "data_through": str(last_bar.date()), "refresh": info,
                                               "n_all": int(len(F)), "main": ev, "decision": V, "side": side, "by_year": yr,
                                               "idio": idio, "idio_note": idio_note, "x6": x6, "x6_note": x6_note, "code": code},
                                              ensure_ascii=False, indent=1,
                                              default=float), encoding="utf-8")
    row = {"run": str(today.date()), "scope": "all", "data_through": str(last_bar.date()), "closed": ev["n"], "w2_year": V["year"],
           "w2_diff": ev.get("diff"), "w2_lo95": ev.get("lo95"), "w2_hi95": ev.get("hi95"), "w2_lo99": ev.get("lo99"),
           "w2_hi99": ev.get("hi99"), "w2_alarm": V["alarm"], "w2_confirmed": V["confirmed"], "code": code}
    rows = [row] + IF.history_rows(idio, str(today.date()), "all_", {"data_through": str(last_bar.date()), "code": code})   # 第七节
    if x6 is not None:                                                        # 第八节：判定过的年份下次不再判定
        rows.append(EF.history_row(x6["eval"], str(today.date()), "all_X6", "x6_year", x6["year"],
                                   {"data_through": str(last_bar.date()), "code": code, "x6_sec_ok": x6["sec_ok"]}))
    pd.concat([hist, pd.DataFrame(rows)], ignore_index=True).to_csv(hist_fp, index=False)   # 只追加
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", required=True, help="复核（先补齐 J-Quants 缓存）")
    ap.add_argument("--no-fetch", action="store_true", help="不补数据，用现有缓存（试跑用）")
    a = ap.parse_args(argv)
    return review(fetch=not a.no_fetch)


if __name__ == "__main__":
    raise SystemExit(main())
