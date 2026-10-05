"""tbf.py — TBF「像起跌点就不买」：加进模拟盘 / 执行器的选股判断（2026-10-06 用户：「把 TBF 加进现在的选股判断」）。

来源：scripts/turn_shape_combo.py（登记 23e248a，结果 b36c893）。照实写：那次检验 TBF **第一关没过**（路线 B 全过：合起来胜率 50.73% → 57.01%、
每笔 +3.25% → +4.05%、W / Jx 2022〜 / Zx 同方向；只差 V7：评分模型没见过的 J 后一半（2022〜）账户 Calmar −0.026，容许 −0.02；账户合计只 +0.016，
改善主要在 2001〜2016）。用户看了这些结果之后明确要求加进选股判断（var/sim_changes.md 2026-10-06「配置变更（用户要求）：TBF」）。
规则（与研究同一套，一点不改）：
一 评分模型冻结 = turn_shape_wide U2（日线尺度，登记 2757571）与 turn_shape_mtf（周 / 月线尺度，登记 de4b60c）的「下跌模型」（像起跌点）；
   参数 var/tbf_model.json（scripts/turn_shape_combo.py 用登记的代码重拟合、与结果文件逐个核对过的那一份，scripts/tbf_export.py 导出；只有参数、没有行情）。
二 特征 = scripts/turn_shape_study.py 的 46 个（日线 18 / 周线 14 / 月线 11 / σ60（向前填补口径）/ log 时价总额 / 12-1 动量），同一组公式（下面照抄，
   tests/test_tbf.py 与研究的函数逐格核对）；log 时价总额一律当缺值；缺的特征标准化后补 0；分数 = clip(截距 + Σ 系数 × 标准化特征, ±30)。
   周 / 月线只用已完成的 K 线；实盘的数据只到今天 → 完成的判断用「这些日子 + 东证的下一个交易日」（qbreak/mtf.live_calendar，与 W2 同一个做法），
   这样周五 / 月末收盘时这一周 / 这个月已算完成，与回测一致。
三 信号日收盘：今天的股票池（日経225）里 45 个特征（log 时价总额除外）都算得出的票，三个尺度的下跌模型分数各自排百分位（平均名次 ÷ 个数）；
   > 90% =「最像」；三个尺度里至少两个「最像」→ 这只票明天不开新仓（个股倍数 0）。算不出的票 / 不在股票池的票 = 不挡。
四 运行：云端 sim-day 在引擎决策之前算 → var/tbf.json（今天被挡的全部票 + 候选的三个百分位）；Mac 执行器由 scripts/liveu.sh 同步同一个文件、
   用同一张名单。文件日期对不上 / 没有文件 / 算不了 → 不生效（= 原规则，日报与执行器日志标出）。var/sim.json 的 "tbf": {"enabled": true} 是开关；
   基准账户（原规则）不加。
五 前向记录（只追加、不改、不补写）：var/out/tbf_forward.csv —— 每个决策日的每个买入候选一行（三个百分位、挡不挡、参照只数）。
   复核（2026-10-06 与采用同时登记，那时没有任何数据）：每年一次（2027-10-05 … 2031-10-05 之后的第一次季度复核），候选 ∩ scripts/score_forward.py 每日记录里
   同一天、同一只的日経225 W2 信号，按 X6 成熟配对（信号日之后 ≥ 65 根 K 线）分「挡 / 不挡」：不挡 − 挡 的 X6 每笔 95% 上限 < 0 → 失效警报（提议关掉）；
   99% 下限 > 0 → 证实；任一组 < 10 笔 → 不判定。
非投资建议。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

FILE = "tbf.json"
MODEL_FILE = "tbf_model.json"
FORWARD = "tbf_forward.csv"
SINCE = "2026-10-05"                                 # 第一次作用的决策（10-05 收盘 → 10-06 成交）
SCALES = ("D", "W", "M")
TOP = 0.90
MIN_SCALES = 2
SIG_N = 60
FWD_COLS = ("date", "ticker", "pct_d", "pct_w", "pct_m", "n_top", "skip", "n_ref")


# ───────────────────────── 特征（照抄 scripts/turn_shape_study.py；tests/test_tbf.py 核对） ─────────────────────────
def _sh(a: np.ndarray, k: int) -> np.ndarray:
    out = np.full(a.shape, np.nan)
    if k < len(a):
        out[k:] = a[:len(a) - k]
    return out


def _ratio(a, b):
    with np.errstate(invalid="ignore", divide="ignore"):
        return a / b


def _rmean(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).mean().to_numpy()


def _rmax(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).max().to_numpy()


def _rmin(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).min().to_numpy()


def _rstd(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).std().to_numpy()


def _ffill(a: np.ndarray) -> np.ndarray:
    return pd.DataFrame(a).ffill().to_numpy(float)


def _atr(H: np.ndarray, L: np.ndarray, C: np.ndarray, n: int = 14) -> np.ndarray:
    pc = _sh(C, 1)
    tr = np.fmax(H - L, np.fmax(np.abs(H - pc), np.abs(L - pc)))
    tr = np.where(np.isfinite(pc), tr, H - L)
    return pd.DataFrame(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


def _rsi(C: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(C, axis=0, prepend=np.nan)
    upm = pd.DataFrame(np.where(np.isfinite(d), np.clip(d, 0, None), np.nan)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    dnm = pd.DataFrame(np.where(np.isfinite(d), np.clip(-d, 0, None), np.nan)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    rs = _ratio(upm, np.where(dnm == 0, np.nan, dnm))
    out = 100 - 100 / (1 + rs)
    return np.where((dnm == 0) & np.isfinite(upm), 100.0, out)


def _run_len(C: np.ndarray, cap: int = 7) -> np.ndarray:
    T, N = C.shape
    out = np.full((T, N), np.nan)
    prev = np.zeros(N)
    for t in range(1, T):
        with np.errstate(invalid="ignore"):
            up, dn = C[t] > C[t - 1], C[t] < C[t - 1]
        cur = np.where(up, np.where(prev > 0, prev + 1, 1), np.where(dn, np.where(prev < 0, prev - 1, -1), 0))
        prev = np.clip(cur, -cap, cap)
        out[t] = prev
    return out


def _shape(O, H, L, C):
    rng = np.where(H - L > 0, H - L, np.nan)
    return _ratio(C - O, rng), _ratio(H - np.fmax(O, C), rng), _ratio(np.fmin(O, C) - L, rng)


def _bar_panels(P: dict, days: pd.DatetimeIndex, freq: str, cal: pd.DatetimeIndex) -> tuple[dict, np.ndarray]:
    """日线宽表 → 周 / 月线宽表（只留已完成的周期；完成按 cal 判断）+ 每个交易日 → 当天收盘时已完成的最近一根的位置（没有 → −1）。"""
    from .mtf import completion_days, period_key
    key = period_key(days, freq)
    comp = completion_days(cal, freq)
    agg = {}
    for k, how in (("O", "first"), ("H", "max"), ("L", "min"), ("C", "last"), ("V", "sum")):
        g = pd.DataFrame(P[k]).groupby(key, sort=True)
        agg[k] = g.sum(min_count=1) if how == "sum" else getattr(g, how)()
    keep = agg["C"].index.isin(comp.index)
    cdays = pd.DatetimeIndex(comp.reindex(agg["C"].index[keep]).to_numpy())
    bars = {k: v[keep].to_numpy(float) for k, v in agg.items()}
    pos = np.searchsorted(cdays.to_numpy(dtype="datetime64[ns]"), days.to_numpy(dtype="datetime64[ns]"), side="right") - 1
    return bars, pos


def _on_days(Bv: np.ndarray, pos: np.ndarray) -> np.ndarray:
    out = np.full((len(pos), Bv.shape[1]), np.nan)
    ok = pos >= 0
    out[ok] = Bv[pos[ok]]
    return out


def features(P: dict, days: pd.DatetimeIndex, cal: pd.DatetimeIndex | None = None):
    """宽表（O / H / L / C / V，days × 票）→ 逐个产生 (特征名, 宽表)；46 个，log 时价总额 = 缺值。cal = 判断周 / 月线完成的日历（缺省 = days）。"""
    P = {k: np.asarray(P[k], float) for k in ("O", "H", "L", "C", "V")}
    O, H, L, C, V = P["O"], P["H"], P["L"], P["C"], P["V"]
    cal = days if cal is None else cal
    with np.errstate(invalid="ignore", divide="ignore"):
        yield "d_r5", _ratio(C, _sh(C, 5)) - 1
        yield "d_r20", _ratio(C, _sh(C, 20)) - 1
        yield "d_r60", _ratio(C, _sh(C, 60)) - 1
        yield "d_dd60", _ratio(C, _rmax(C, 60)) - 1
        yield "d_up60", _ratio(C, _rmin(C, 60)) - 1
        m25 = _rmean(C, 25)
        yield "d_ma25", _ratio(C, m25) - 1
        yield "d_ma25s", _ratio(m25, _sh(m25, 5)) - 1
        yield "d_ma75", _ratio(C, _rmean(C, 75)) - 1
        yield "d_rsi14", _rsi(C, 14)
        bw = _ratio(4 * _rstd(C, 20), _rmean(C, 20))
        yield "d_bbw", _ratio(bw, _rmean(bw, 120))
        yield "d_vr", _ratio(V, _sh(_rmean(V, 20), 1))
        yield "d_vr5", _ratio(_rmean(V, 5), _sh(_rmean(V, 20), 5))
        b, u, lo = _shape(O, H, L, C)
        yield "d_body", b
        yield "d_ush", u
        yield "d_lsh", lo
        yield "d_size", _ratio(H - L, _sh(_atr(H, L, C), 1))
        yield "d_gap", _ratio(O, _sh(C, 1)) - 1
        yield "d_run", _run_len(C)
        yield "lmc", np.full(C.shape, np.nan)
        yield "mom12", _ratio(_sh(C, 21), _sh(C, 252)) - 1
        Cf = _ffill(C)
        yield "sig60", _rstd(np.diff(np.log(Cf), axis=0, prepend=np.nan), SIG_N)
        for freq, px in (("W", "w"), ("M", "m")):
            B, pos = _bar_panels(P, days, freq, cal)
            bO, bH, bL, bC, bV = B["O"], B["H"], B["L"], B["C"], B["V"]
            b, u, lo = _shape(bO, bH, bL, bC)
            if px == "w":
                m13 = _rmean(bC, 13)
                fe = {"w_r4": _ratio(bC, _sh(bC, 4)) - 1, "w_r13": _ratio(bC, _sh(bC, 13)) - 1, "w_r26": _ratio(bC, _sh(bC, 26)) - 1,
                      "w_ma13": _ratio(bC, m13) - 1, "w_ma13s": _ratio(m13, _sh(m13, 4)) - 1, "w_ma26": _ratio(bC, _rmean(bC, 26)) - 1,
                      "w_rsi14": _rsi(bC, 14), "w_vr": _ratio(bV, _sh(_rmean(bV, 10), 1)), "w_body": b, "w_ush": u, "w_lsh": lo,
                      "w_run": _run_len(bC), "w_dd52": _ratio(bC, _rmax(bC, 52)) - 1,
                      "w_pos52": _ratio(bC - _rmin(bC, 52), _rmax(bC, 52) - _rmin(bC, 52))}
            else:
                m12 = _rmean(bC, 12)
                fe = {"m_r3": _ratio(bC, _sh(bC, 3)) - 1, "m_r12": _ratio(bC, _sh(bC, 12)) - 1, "m_ma12": _ratio(bC, m12) - 1,
                      "m_ma12s": _ratio(m12, _sh(m12, 3)) - 1, "m_rsi6": _rsi(bC, 6), "m_vr": _ratio(bV, _sh(_rmean(bV, 6), 1)),
                      "m_body": b, "m_ush": u, "m_lsh": lo, "m_run": _run_len(bC), "m_dd12": _ratio(bC, _rmax(bC, 12)) - 1}
            for name, arr in fe.items():
                yield name, _on_days(arr, pos)


# ───────────────────────── 模型与打分 ─────────────────────────
def load_model(path=None) -> dict:
    """var/tbf_model.json → {"feats": [...], "scales": {尺度: {lo, hi, mu, sd, w（numpy）}}}。"""
    from . import paths
    fp = Path(path) if path is not None else paths.PROJECT_ROOT / "var" / MODEL_FILE
    d = json.loads(fp.read_text(encoding="utf-8"))
    sc = {k: {x: np.asarray(v[x], float) for x in ("lo", "hi", "mu", "sd", "w")} for k, v in d["scales"].items()}
    return {"feats": list(d["feats"]), "scales": sc}


def score_panel(P: dict, days: pd.DatetimeIndex, model: dict, cal: pd.DatetimeIndex | None = None) -> tuple[dict, np.ndarray]:
    """→ ({尺度: 下跌模型分数宽表（收盘缺 → NaN）}, 45 个特征都有值的格)。"""
    feats = model["feats"]
    idx = {f: i for i, f in enumerate(feats)}
    C = np.asarray(P["C"], float)
    acc = {k: np.full(C.shape, float(m["w"][0])) for k, m in model["scales"].items()}
    complete = np.ones(C.shape, bool)
    seen = []
    for name, arr in features(P, days, cal):
        i = idx[name]
        seen.append(name)
        if name != "lmc":
            complete &= np.isfinite(arr)
        for k, m in model["scales"].items():
            with np.errstate(invalid="ignore"):
                z = (np.clip(arr, m["lo"][i], m["hi"][i]) - m["mu"][i]) / m["sd"][i]
            acc[k] += float(m["w"][1 + i]) * np.where(np.isfinite(z), z, 0.0)
    if sorted(seen) != sorted(feats):
        raise AssertionError(f"特征不齐：{sorted(set(feats) ^ set(seen))}")
    fin = np.isfinite(C)                                   # float32：与研究（turn_shape_combo.score_panel）同一精度，排名逐个相同
    return {k: np.where(fin, np.clip(v, -30, 30), np.nan).astype(np.float32) for k, v in acc.items()}, complete & fin


def pct_row(score: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """一行（一天）：ok 的票里按分数排百分位（平均名次 ÷ 个数）；不在 ok 里 = NaN（与研究的 turn_shape_combo.pct_rank 同一个算法）。"""
    s = pd.Series(np.where(np.asarray(ok, bool) & np.isfinite(score), score, np.nan))
    return s.rank(pct=True).to_numpy(float)


def decide(pcts: dict) -> dict:
    """{尺度: 百分位} → {"top": [最像的尺度], "n_top": 个数, "skip": 至少两个尺度最像}。百分位缺 = 不算最像。"""
    top = [k for k in SCALES if pcts.get(k) is not None and np.isfinite(pcts[k]) and pcts[k] > TOP]
    return {"top": top, "n_top": len(top), "skip": len(top) >= MIN_SCALES}


def compute(ind: dict, bar_date: str, pool: list[str], cands=(), model: dict | None = None) -> dict:
    """云端 sim-day：今天股票池的票（ind 里有行情的）→ 三个尺度的百分位 → 被挡的全部票 + 候选的明细。
    ind = {票: DataFrame（Open / High / Low / Close / Volume）}；最新一天不是 bar_date → 不生效（errors 写原因）。"""
    from .candles import panel
    from .mtf import live_calendar
    model = model or load_model()
    names = [t for t in pool if t in ind and ind[t] is not None and len(ind[t])]
    if not names:
        return payload(bar_date, {}, [], 0, {"行情": "股票池里没有行情"})
    days = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
    days = days[days <= pd.Timestamp(bar_date)]
    if not len(days) or str(days[-1].date()) != str(bar_date):
        return payload(bar_date, {}, [], 0, {"行情": f"股票池行情的最后一天 {str(days[-1].date()) if len(days) else '—'} 不是 {bar_date}"})
    P = panel({t: ind[t] for t in names}, days, names)
    sc, comp = score_panel(P, days, model, live_calendar(days))
    k = len(days) - 1
    ok = comp[k]
    pr = {s: pct_row(sc[s][k], ok) for s in SCALES}
    flags, cand = [], {}
    cset = set(cands or ())
    for j, t in enumerate(names):
        p = {s: (None if not np.isfinite(pr[s][j]) else round(float(pr[s][j]), 4)) for s in SCALES}
        r = decide({s: (np.nan if p[s] is None else p[s]) for s in SCALES})
        if r["skip"]:
            flags.append(t)
        if t in cset:
            cand[t] = {"pct": p, "top": r["top"], "skip": r["skip"], "scored": bool(ok[j])}
    for t in cset - set(cand):
        cand[t] = {"pct": {s: None for s in SCALES}, "top": [], "skip": False, "scored": False}
    return payload(bar_date, cand, sorted(flags), int(ok.sum()), {})


def payload(as_of: str, stocks: dict, skip_all: list[str], n_ref: int, errors: dict | None = None, enabled: bool = True) -> dict:
    return {"as_of": str(as_of), "enabled": bool(enabled), "n_ref": int(n_ref), "skip_all": list(skip_all), "stocks": stocks,
            "errors": errors or {}, "rule": f"三个尺度（日 / 周 / 月线）的下跌模型里至少 {MIN_SCALES} 个在当天股票池里排前 {round((1 - TOP) * 100)}% → 不开新仓"}


# ───────────────────────── 每天的文件（云端算、执行器读）─────────────────────────
def load(path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def apply(tmult: dict | None, pl: dict | None, as_of: str | None) -> tuple[dict, dict | None]:
    """{票: 倍数} + TBF → 新的 {票: 倍数}（被挡的票 = 0）与用到的文件 | None（没有 / 关着 / 日期对不上 / 有错 → 原样）。"""
    tm = dict(tmult or {})
    if not pl or not pl.get("enabled") or not as_of or str(pl.get("as_of")) != str(as_of) or (pl.get("errors") or {}).get("行情"):
        return tm, None
    for t in pl.get("skip_all") or []:
        tm[t] = 0.0
    return tm, pl


def brief(pl: dict | None, as_of: str | None, enabled: bool) -> dict:
    """日报 / 执行器日志：{enabled, applied, as_of, n_ref, skipped（候选里被挡的）, kept, skip_all_n, why}。"""
    if not enabled:
        return {"enabled": False}
    if not pl:
        return {"enabled": True, "applied": False, "bar_date": as_of, "why": f"没有 {FILE}（云端还没算 / 没同步到本机）→ 今天按原规则"}
    ok = apply({}, pl, as_of)[1] is not None
    st = pl.get("stocks") or {}
    err = dict(pl.get("errors") or {})
    why = None if ok else (err.get("行情") or (f"TBF 的文件是 {pl.get('as_of')} 的，最新 K 线 {as_of} → 今天按原规则" if pl.get("enabled") else "TBF 的文件标着关闭"))
    return {"enabled": True, "applied": ok, "as_of": pl.get("as_of"), "bar_date": as_of, "n_ref": pl.get("n_ref"),
            "skipped": sorted(t for t, v in st.items() if v.get("skip")), "kept": sorted(t for t, v in st.items() if not v.get("skip")),
            "skip_all_n": len(pl.get("skip_all") or []), "errors": err, "why": why}


def text(b: dict) -> str:
    """一行文字（执行器日志 / 页面）。"""
    if not b.get("enabled"):
        return ""
    if not b.get("applied"):
        return f"- ★ TBF（像起跌点就不买）没生效：{b.get('why') or '—'}"
    sk = b.get("skipped") or []
    n = len(sk) + len(b.get("kept") or [])
    return (f"- TBF 像起跌点就不买（{b.get('as_of')}）：股票池 {b.get('n_ref')} 只里 {b.get('skip_all_n')} 只「像起跌点」；候选 {n} 只，"
            + (f"不买 {len(sk)} 只：{'、'.join(sk[:8])}" if sk else "没有要挡的"))


def summary(pl: dict | None, as_of: str | None, enabled: bool) -> dict:
    b = brief(pl, as_of, enabled)
    if enabled and pl:
        b["stocks"] = pl.get("stocks") or {}
    return b


# ───────────────────────── 前向记录（只追加）─────────────────────────
def forward_rows(pl: dict | None) -> list[dict]:
    if not pl or not pl.get("enabled") or (pl.get("errors") or {}).get("行情"):
        return []
    out = []
    for t, v in sorted((pl.get("stocks") or {}).items()):
        p = v.get("pct") or {}
        out.append({"date": pl.get("as_of"), "ticker": t, "pct_d": p.get("D"), "pct_w": p.get("W"), "pct_m": p.get("M"),
                    "n_top": len(v.get("top") or []), "skip": int(bool(v.get("skip"))), "n_ref": pl.get("n_ref")})
    return out


def append_forward(pl: dict | None, path) -> int:
    """var/out/tbf_forward.csv：同一天已经记过 → 不再写（重跑不重复）；只追加，不改旧行。返回新写的行数。"""
    rows = forward_rows(pl)
    if not rows:
        return 0
    fp = Path(path)
    if fp.exists():
        try:
            old = pd.read_csv(fp, dtype=str)
            if str(pl.get("as_of")) in set(old["date"].astype(str)):
                return 0
        except (OSError, ValueError, KeyError):
            return 0
    df = pd.DataFrame(rows, columns=list(FWD_COLS))
    fp.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(fp, mode="a", header=not fp.exists(), index=False)
    return len(df)
