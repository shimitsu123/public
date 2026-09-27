"""fins_event_data.py — 決算 / 会社予想修正的「开示事件」表，和「开示本身当买点」的逐笔回测（数据层；候选与判定在 scripts/fins_event_study.py）。

数据：J-Quants Standard 決算短信サマリー批量文件（qbreak/jq_data.py DATASETS["fins"]，全市场 2016-09 起；原始数据只在缓存、不入库）
  + 全市场日线面板（scripts/allstock_data.py：调整后 OHLCV、R = 未调整收盘 ÷ 调整后收盘、VA 成交额、上市掩码）。
事件表（每条开示一行）：code / ticker、date 开示日、time 开示时刻、doc 文件类型、per 期间、fy 予想对应的决算期末、fc 予想值、
  rev 与同一决算期上一次予想相比的修正 %（第一次出现的予想 → 缺值；qbreak/jq_data.fins_events 同一算法，利润档 = 营业 → 经常 → 净利润）、
  yoy 累计实绩对上年同期 %、after_close 开示时刻 ≥ 收盘时刻（缺时刻当 True）、sig_day 信号日 = 开示日当天或之前最后一个交易日
  （不管盘中还是盘后开示，都在 sig_day 的下一个交易日开盘买 → 偏保守）；lot_yen 信号日一手（100 股）的真实金额、va20 信号日前 20 日平均成交额
  （只作描述 / 分段，不作过滤：用户 2026-09-27「取消小盘股受一手金额和流动性限制」）。
events_full（研究用的完整事件表，events_table 的超集）另加：
  只留 {1Q,2Q,3Q,FY}FinancialStatements_{Consolidated,NonConsolidated}_{JP,IFRS,US} 与 EarnForecastRevision（不要 REIT、股息修正、外国、其他期间）；
  fy12 当期决算期 = 12 个月；first 同一键的第一次开示（決算短信：(文件类型, 决算期末, 期间)；予想修正：(决算期末, 开示日)），
  之后同键的行 = 订正（数字没变 → rev = 0）；retro / chg_acc / chg_sub / chg_scope 遡及修正 / 会计估计变更 / 连结子公司异动 / 连结范围变更标记；
  level 这一行用的利润档（按这一行有值的列：OP → OdP → NP，不看公司全历史）；pos 新旧予想都 > 0（亏损缩小不算上修）；
  rev_np 净利润予想的修正 %；act 累计实绩；yoy 只在上年同期 > 0 且上年也是 12 个月决算期时定义；
  FY 行：g_next 下期予想 ÷ 当期实绩 − 1（两者 > 0）、beat 当期实绩对最后一次予想 %；div_rev 年度予想股息对同期上一次 %（描述用）；
  t0 开示日之后第一个交易日、r 反应日（盘中开示且当天是交易日 → 当天；否则 t0）；收盘时刻 2024-11-05 起 15:30、之前 15:00。
逐笔：event_trades —— 事件所在的票按现行参数算指标表（compute_indicators：MACD 死叉等出场用），entry 改成「sig_day = 事件」，
  每只票单独、一次一仓、现行卖出规则、扣立花 ¥25 万一笔的来回成本（scripts/candle_posthoc.trades 同一套）；返回每笔 + 对应事件的字段。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import jq_data as JD                                             # noqa: E402
from qbreak import jquants as JQ                                             # noqa: E402

EVENT_COLS = ["code", "ticker", "date", "time", "doc", "per", "fy", "fc", "rev", "yoy", "after_close", "sig_day"]
AFTER_CLOSE = "15:00"
CLOSE_CHANGE, CLOSE_OLD, CLOSE_NEW = pd.Timestamp("2024-11-05"), "15:00", "15:30"      # 東証 2024-11-05 起收盘 15:30
EXTRA_COLS = ["DiscNo", "RetroRst", "ChgAcEst", "MatChgSub", "SigChgInC", "FDivAnn"]
FS_RE = re.compile(r"^(1Q|2Q|3Q|FY)FinancialStatements_(Consolidated|NonConsolidated)_(JP|IFRS|US)$")
REV_DOC = "EarnForecastRevision"
PERIODS = ("1Q", "2Q", "3Q", "FY")
LEVELS = (("OP", "FOP", "NxFOP"), ("OdP", "FOdP", "NxFOdP"), ("NP", "FNP", "NxFNp"))
FULL_COLS = ["code", "ticker", "date", "time", "disc_no", "doc", "per", "fy", "fy12", "first", "retro", "chg_acc", "chg_sub", "chg_scope",
             "level", "fc", "fc_prev", "rev", "pos", "rev_np", "act", "yoy", "g_next", "beat", "div_rev",
             "after_close", "sig_day", "t0", "r"]


def load_fins(refresh: bool = False, extra: bool = False) -> pd.DataFrame:
    path, cols = JD.DATASETS["fins"]
    if refresh:
        files = JD.bulk_download(JQ.JQuants(), path, log=lambda s: print(s, file=sys.stderr, flush=True))
    else:
        d = JD.bulk_dir() / path.strip("/")
        files = sorted(d.glob("historical/*/*.csv.gz")) + sorted(d.glob("historical/*.csv.gz")) + sorted(d.glob("live/*.csv.gz"))
    return JD.read_bulk(files, cols + (EXTRA_COLS if extra else []))


def signal_days(dates, days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """开示日 → 当天或之前最后一个交易日（days 升序）；早于第一个交易日 → NaT。"""
    d = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    k = days.searchsorted(d.to_numpy(), side="right") - 1
    out = days.to_numpy()[np.clip(k, 0, len(days) - 1)]
    return pd.DatetimeIndex(np.where(k >= 0, out, np.datetime64("NaT")))


def next_days(dates, days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """开示日 → 之后第一个交易日；数据末尾之后 → NaT。"""
    d = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    k = days.searchsorted(d.to_numpy(), side="right")
    out = days.to_numpy()[np.clip(k, 0, len(days) - 1)]
    return pd.DatetimeIndex(np.where(k < len(days), out, np.datetime64("NaT")))


def close_time(dates) -> pd.Series:
    d = pd.to_datetime(pd.Series(dates))
    return pd.Series(np.where(d >= CLOSE_CHANGE, CLOSE_NEW, CLOSE_OLD), index=d.index)


def fy_months(st, en) -> pd.Series:
    s, e = pd.to_datetime(pd.Series(st), errors="coerce"), pd.to_datetime(pd.Series(en), errors="coerce")
    return (e.dt.year - s.dt.year) * 12 + (e.dt.month - s.dt.month) + 1


def _flag(s) -> pd.Series:
    return s.fillna("").astype(str).str.lower().eq("true") if s is not None else None


def events_table(F: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """決算短信全表 → 事件表（EVENT_COLS）。fins_events 的行序 = 按 (DiscDate, DiscTime) 稳定排序后的 F 行序，据此对回文件类型与时刻。"""
    rows = []
    sort_cols = ["DiscDate", "DiscTime"] if "DiscTime" in F.columns else ["DiscDate"]
    for code, g in F.groupby("Code"):
        t = JQ.to_yf(code)
        if t is None:
            continue
        gs = g.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
        ev = JD.fins_events(gs)
        if ev.empty or len(ev) != len(gs):
            continue
        tm = gs["DiscTime"].fillna("").astype(str) if "DiscTime" in gs.columns else pd.Series("", index=gs.index)
        for k in range(len(gs)):
            r = ev.iloc[k]
            rows.append((str(code), t, pd.Timestamp(r["date"]), tm.iat[k], str(gs.at[k, "DocType"] or ""), str(gs.at[k, "CurPerType"] or ""),
                         r["fy"], r["fc"], r["rev"], r["yoy"]))
    E = pd.DataFrame(rows, columns=EVENT_COLS[:10])
    if not len(E):
        return pd.DataFrame(columns=EVENT_COLS)
    tm = E["time"].astype(str)
    E["after_close"] = (tm == "") | (tm >= AFTER_CLOSE)
    E["sig_day"] = signal_days(E["date"], days)
    return E.dropna(subset=["sig_day"]).reset_index(drop=True)


def _pct(new, old) -> float:
    if new is None or old is None or not (np.isfinite(new) and np.isfinite(old)) or old == 0:
        return np.nan
    return (new - old) / abs(old) * 100


def events_full(F: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """決算短信全表（load_fins(extra=True)）→ 研究用完整事件表（FULL_COLS；见模块开头）。"""
    F = F.copy()
    doc = F["DocType"].fillna("").astype(str)
    F = F[(doc.str.match(FS_RE) | (doc == REV_DOC)) & F["CurPerType"].isin(PERIODS)].copy()
    for c in ("OP", "OdP", "NP", "FOP", "FOdP", "FNP", "NxFOP", "NxFOdP", "NxFNp", "FDivAnn"):
        F[c] = JD.num(F[c]) if c in F.columns else np.nan
    for c in EXTRA_COLS:
        if c not in F.columns:
            F[c] = "" if c == "DiscNo" else np.nan
    F["DiscTime"] = F["DiscTime"].fillna("").astype(str) if "DiscTime" in F.columns else ""
    F["DiscNo"] = F["DiscNo"].fillna("").astype(str)
    F["disc_d"] = pd.to_datetime(F["DiscDate"])
    F["fy12_"] = fy_months(F["CurFYSt"], F["CurFYEn"]).eq(12).to_numpy()
    for c, k in (("RetroRst", "retro_"), ("ChgAcEst", "acc_"), ("MatChgSub", "sub_"), ("SigChgInC", "scope_")):
        F[k] = _flag(F[c]).to_numpy()
    rows = []
    for code, g in F.groupby("Code"):
        t = JQ.to_yf(code)
        if t is None:
            continue
        g = g.sort_values(["disc_d", "DiscTime", "DiscNo"], kind="mergesort")
        last_fc, last_div, actual, seen = {}, {}, {}, set()
        for r in g.itertuples(index=False):
            rd = r._asdict()
            d, per, dt = rd["disc_d"], str(rd["CurPerType"]), str(rd["DocType"])
            is_fy, is_rev, fy12 = per == "FY" and dt.startswith("FY"), dt == REV_DOC, bool(rd["fy12_"])
            key = (dt, rd["CurFYEn"], d) if is_rev else (dt, rd["CurFYEn"], per)
            first = key not in seen
            seen.add(key)
            level, f_col, nx_col, a_col = "", "", "", ""
            for a, f, nx in LEVELS:
                if any(pd.notna(rd.get(c)) for c in (a, f, nx)):
                    level, a_col, f_col, nx_col = a, a, f, nx
                    break
            fy, fc = (rd.get("NxtFYEn"), rd.get(nx_col)) if is_fy else (rd.get("CurFYEn"), rd.get(f_col))
            fc = float(fc) if level and pd.notna(fc) else np.nan
            prev = last_fc.get((fy, level)) if level else None
            rev = _pct(fc, prev) if np.isfinite(fc) else np.nan
            pos = bool(np.isfinite(fc) and fc > 0 and prev is not None and prev > 0)
            fnp = rd.get("NxFNp") if is_fy else rd.get("FNP")
            fnp = float(fnp) if pd.notna(fnp) else np.nan
            rev_np = _pct(fnp, last_fc.get((fy, "NP"))) if np.isfinite(fnp) else np.nan
            act = float(rd.get(a_col)) if level and pd.notna(rd.get(a_col)) else np.nan
            yoy = g_next = beat = np.nan
            fye = str(rd.get("CurFYEn") or "")
            if not is_rev and np.isfinite(act) and fye and fy12:
                prev_fye = str(int(fye[:4]) - 1) + fye[4:]
                ly = actual.get((prev_fye, per, level))
                if ly is not None and ly > 0:
                    yoy = _pct(act, ly)
                if first:
                    actual[(fye, per, level)] = act
            if is_fy and np.isfinite(act):
                last_cur = last_fc.get((fye, level))
                beat = _pct(act, last_cur) if last_cur is not None else np.nan
                if act > 0 and np.isfinite(fc) and fc > 0:
                    g_next = _pct(fc, act)
            div = rd.get("FDivAnn")
            div = float(div) if pd.notna(div) else np.nan
            div_rev = _pct(div, last_div.get(fye)) if (not is_fy and np.isfinite(div)) else np.nan
            if np.isfinite(fc):
                last_fc[(fy, level)] = fc
            if np.isfinite(fnp):
                last_fc[(fy, "NP")] = fnp
            if not is_fy and np.isfinite(div):
                last_div[fye] = div
            rows.append((str(code), t, d, rd["DiscTime"], rd["DiscNo"], dt, per, fy, fy12, first, bool(rd["retro_"]), bool(rd["acc_"]), bool(rd["sub_"]),
                         bool(rd["scope_"]), level, fc, np.nan if prev is None else float(prev), rev, pos, rev_np, act, yoy, g_next, beat, div_rev))
    E = pd.DataFrame(rows, columns=FULL_COLS[:25])
    if not len(E):
        return pd.DataFrame(columns=FULL_COLS)
    tm = E["time"].astype(str)
    E["after_close"] = (tm == "") | (tm >= close_time(E["date"]).to_numpy())
    E["sig_day"] = signal_days(E["date"], days)
    E["t0"] = next_days(E["date"], days)
    on_day = E["date"].isin(days)
    E["r"] = pd.DatetimeIndex(np.where(on_day & ~E["after_close"], E["date"].to_numpy(), E["t0"].to_numpy()))
    return E.dropna(subset=["sig_day"]).reset_index(drop=True)


def describe_events(A: dict, E: pd.DataFrame) -> pd.DataFrame:
    """事件表 + 面板 → 加描述字段（对不上的缺值）：lot_yen 信号日一手真实金额（调整后收盘 × R × 100）、va20 信号日前 20 日平均成交额（円）、
    mc 信号日市值；有 t0 / r 列时再加：listed_t0 t0 那天在时点股票池、gap_t0 t0 开盘对信号日收盘 %（引擎 > 3% 放弃）、
    react 反应日 r 收盘对前一交易日 %、react_d r 收盘对开示日前一交易日 %、vr_r r 日量 ÷ 前 20 日均量、up_r r 日收阳（收 ≥ 开）、
    split_near [信号日−1, t0] 内 R 跳变 > 1%（拆股 / 并股；不用进场后的信息）。"""
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    di = pd.Index(days)
    C, R, O, V = A["C"], A["R"], A["O"], A["V"]
    VA = pd.DataFrame(A["VA"], index=days, columns=names).rolling(20, min_periods=10).mean().shift(1).to_numpy()
    VM = pd.DataFrame(V, index=days, columns=names).rolling(20, min_periods=10).mean().shift(1).to_numpy()
    MC = A.get("MC")
    full = "t0" in E.columns and "r" in E.columns
    n = len(E)
    lot, va, mc = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    listed, gap, react, react_d, vr, up, split = (np.full(n, np.nan) for _ in range(7))
    for k, (t, d) in enumerate(zip(E["ticker"], E["sig_day"])):
        j = col.get(t)
        i = di.get_loc(d) if (j is not None and d in di) else None
        if i is None:
            continue
        c, r = float(C[i, j]), float(R[i, j])
        if np.isfinite(c) and np.isfinite(r) and r > 0:
            lot[k] = c * r * 100
        va[k] = float(VA[i, j])
        if MC is not None:
            mc[k] = float(MC[i, j])
        if not full:
            continue
        t0, rr = E["t0"].iat[k], E["r"].iat[k]
        i0 = di.get_loc(t0) if pd.notna(t0) and t0 in di else None
        ir = di.get_loc(rr) if pd.notna(rr) and rr in di else None
        if i0 is not None:
            listed[k] = float(A["listed"][i0, j])
            if np.isfinite(c) and c > 0 and np.isfinite(O[i0, j]):
                gap[k] = (O[i0, j] / c - 1) * 100
            lo, hi = max(0, i - 1), i0
            rr_ = R[lo:hi + 1, j]
            if np.isfinite(rr_).all() and len(rr_) > 1:
                split[k] = float(np.any(np.abs(np.diff(rr_) / rr_[:-1]) > 0.01))
        if ir is not None and ir >= 1:
            cr, cp = float(C[ir, j]), float(C[ir - 1, j])
            if np.isfinite(cr) and np.isfinite(cp) and cp > 0:
                react[k] = (cr / cp - 1) * 100
            cd = float(C[i - 1, j]) if i >= 1 else np.nan                                # 开示日前一交易日（信号日的前一天）
            if np.isfinite(cr) and np.isfinite(cd) and cd > 0:
                react_d[k] = (cr / cd - 1) * 100
            if np.isfinite(VM[ir, j]) and VM[ir, j] > 0:
                vr[k] = float(V[ir, j]) / float(VM[ir, j])
            if np.isfinite(cr) and np.isfinite(O[ir, j]):
                up[k] = float(cr >= O[ir, j])
    out = E.copy()
    out["lot_yen"], out["va20"], out["mc"] = lot, va, mc
    if full:
        out["listed_t0"], out["gap_t0"], out["react"], out["react_d"], out["vr_r"], out["up_r"], out["split_near"] = listed, gap, react, react_d, vr, up, split
    return out


def event_frames(A: dict, ev_sel: pd.DataFrame, p) -> dict[str, pd.DataFrame]:
    """ev_sel（事件表的子集）→ {票: 指标表}，entry = 那只票的 sig_day（面板里有行情的日子才算）。"""
    from qbreak.strategy import compute_indicators
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    col = {t: j for j, t in enumerate(names)}
    out = {}
    for t, g in ev_sel.groupby("ticker"):
        j = col.get(t)
        if j is None:
            continue
        ok = np.isfinite(A["C"][:, j]) & np.isfinite(A["O"][:, j])
        if ok.sum() < 80:
            continue
        df = pd.DataFrame({"Open": A["O"][ok, j], "High": A["H"][ok, j], "Low": A["L"][ok, j], "Close": A["C"][ok, j],
                           "Volume": A["V"][ok, j]}, index=days[ok]).astype(float)
        ind = compute_indicators(df, p)
        ind["entry"] = ind.index.isin(pd.DatetimeIndex(g["sig_day"]))
        if ind["entry"].any():
            out[t] = ind
    return out


def event_trades(A: dict, ev_sel: pd.DataFrame, p, start: str) -> pd.DataFrame:
    """事件当买点的逐笔（candle_posthoc.trades：一次一仓、现行卖出、扣成本）+ 对应事件的字段（同一票同一天多条开示 → 取第一条）。"""
    import candle_posthoc as CPH
    fr = event_frames(A, ev_sel, p)
    if not fr:
        return pd.DataFrame(columns=["ticker", "sig_date", "net", "hold_days", "entry_date"])
    T = CPH.trades(fr, p, start)
    if not len(T):
        return T
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    key = ev_sel.drop_duplicates(subset=["ticker", "sig_day"]).set_index(["ticker", "sig_day"])
    keep = [c for c in ("date", "time", "doc", "per", "rev", "yoy", "after_close", "lot_yen", "va20") if c in key.columns]
    J = key[keep].reindex(pd.MultiIndex.from_arrays([T["ticker"], T["sig_date"]]))
    for c in keep:
        T[f"ev_{c}"] = J[c].to_numpy()
    return T.reset_index(drop=True)
