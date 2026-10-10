"""era_study.py — 「时代主线」：领先行业能持续多久，跟着时代走（长期领先的行业）是否比「只看最近 12 个月最强的行业」更好
（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：用户（2026-09-27）「跟随时代模型也进入到以后模型的生成判定中，例如以前是机械时代，然后到了互联网，然后到了今天的 AI，
横展开一下，然后根据所有数据来推测未来哪些模块股票会受益」。
一、数据：Ken French 49 行业（CRSP，含已退市公司 → 没有幸存者偏差），价值加权月收益 1926-07〜2026-08（qbreak/factors.ff_industries）。
  相对收益 = 对数收益 − 当月有数据的行业平均。
二、描述（不判定）：每十年相对收益最高 / 最低的 5 个行业（「时代」）、每 5 年最强的 3 个；
  领先的持续性 —— 过去 N 年（1 / 3 / 5 / 10）相对收益的名次与之后 N 年名次的秩相关（每年末一个起点）；
  过去 5 年前 10 名在之后 1 / 3 / 5 年仍在前 10 名的比例（随机 ≈ 10 / 有数据的行业数）。
三、检验（每个月末按规则选 10 个行业、等权持有下一个月；排名跳过最近 1 个月；排名要用的月份都有数据的行业才参加；不计成本）
  B0  有数据的全部行业等权（基准）
  M12 过去 12 个月（跳过最近 1 个月）涨得最多的 10 个 —— 行业动量，文献已知 → 对照
  E36 过去 36 个月（跳过 1 个月）最多的 10 个
  E60 过去 60 个月（跳过 1 个月）最多的 10 个 ——「时代领先」
  ER  12 个月名次与 60 个月名次（百分位）的平均最高的 10 个 ——「长期领先且最近仍强 = 时代在延续」
  EN  12 个月名次 − 60 个月名次最大的 10 个 ——「最近变强、长期还不算领先 = 新时代的苗头」
四、判定：三段（S1 1931-07〜1962-12 / S2 1963-01〜1994-12 / S3 1995-01〜2026-08）各自「候选 − M12」的年化超额；
  通过 = 三段都 > 0，且全期「候选 − M12」月度差的 t 值（Newey–West 12 个月）≥ 2.0。
  通过 →「跟着时代走比只看最近 12 个月更好」成立；这个研究不改任何交易规则，结果只作为「时代主线」排序（日报 / 前向记录）用哪一种的依据：
  有通过的 → 用通过的里全期 t 值最高的；都不通过 → 用 M12（已知有效的最简单的那个），并照实写「长期领先没有额外价值」。
  另报：各规则相对 B0 的年化超额、t 值、相对 B0 累计的最大回撤、每月平均换手（换掉的行业比例）。
五、日本（只描述，时间短、不判定）：東証 33 业种 —— 2006-01〜2016-09：日経225 + 扩大池（yfinance，今天的成员，业种等权）；
  2016-11〜2026-08：J-Quants 全部股票（一般市场，按上月末时价总额加权，时点上市一览）。同样的规则选 7 个（≈ 20%），报告相对 B0 与 M12。
六、局限：美国的行业划分（SIC）跟不上新产业（例：AI 算力分散在 Chips / Hardw / Softw / ElcEq / Util）；不计成本与税；
  过去一百年只有一个市场，「时代」的次数有限（十年一格只有 10 格）；日本两段口径不同、都很短、有幸存者偏差（前一段）。
登记前做过的检查：tests/test_era_study.py（排名只用跳过最近 1 个月之前的数据、持有下一个月、缺数据的行业不参加、NW t 值）。
输出：var/out/era_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
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
from qbreak import paths                                                     # noqa: E402
from qbreak.us_industry import FF49_CN                                       # noqa: E402

K_US, K_JP = 10, 7
SUBS = {"S1": ("1931-07-01", "1962-12-31"), "S2": ("1963-01-01", "1994-12-31"), "S3": ("1995-01-01", "2026-08-31")}
CANDS = {"M12": "过去 12 个月最强（行业动量，对照）", "E36": "过去 36 个月最强", "E60": "过去 60 个月最强（时代领先）",
         "ER": "12 个月与 60 个月名次平均（时代在延续）", "EN": "12 个月名次 − 60 个月名次（新时代的苗头）"}
NW_LAGS, T_MIN = 12, 2.0
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 排名与组合（有测试）──
def past_log(R: pd.DataFrame, n: int) -> pd.DataFrame:
    """行 t（月）：第 t−n+1 … t−1 个月的累计对数收益 %（跳过最近的第 t 个月）；任何一个月缺 → 缺值。用于持有第 t+1 个月。"""
    L = np.log1p(R / 100.0) * 100
    return L.shift(1).rolling(n - 1, min_periods=n - 1).sum()


def scores(R: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """各规则在每个月末的分数（越大越好）；行 t 的分数用于持有 t+1。"""
    p12, p36, p60 = past_log(R, 12), past_log(R, 36), past_log(R, 60)
    both = p12.notna() & p60.notna()
    r12 = p12.where(both).rank(axis=1, pct=True)
    r60 = p60.where(both).rank(axis=1, pct=True)
    return {"M12": p12, "E36": p36, "E60": p60, "ER": (r12 + r60) / 2, "EN": r12 - r60}


def select_top(S: pd.DataFrame, k: int) -> pd.DataFrame:
    """每行分数最高的 k 个 → 布尔（分数缺值的不选；并列按列顺序）。"""
    r = S.rank(axis=1, ascending=False, method="first")
    return r.le(k) & S.notna()


def backtest(R: pd.DataFrame, sel: pd.DataFrame) -> pd.Series:
    """行 t 选中的行业等权持有第 t+1 个月 → 每月收益 %（index = 持有的月份）；没有选中的月 = 缺值。"""
    hold = sel.shift(1).fillna(False).astype(bool)
    x = R.where(hold & R.notna())
    n = x.notna().sum(axis=1)
    return (x.sum(axis=1) / n).where(n > 0)


def turnover(sel: pd.DataFrame) -> float:
    """每月换掉的比例平均（本月选中、下月不选的 ÷ 选中数）。"""
    a = sel.astype(bool)
    prev = a.shift(1).fillna(False).astype(bool)
    n = prev.sum(axis=1)
    out = (prev & ~a).sum(axis=1) / n.where(n > 0)
    return float(out.mean())


def nw_t(x: pd.Series, lags: int = NW_LAGS) -> float:
    """Newey–West t 值（均值 = 0 的检验）。"""
    v = pd.Series(x).dropna().to_numpy(float)
    n = len(v)
    if n < lags + 10:
        return float("nan")
    e = v - v.mean()
    s = e @ e / n
    for k in range(1, lags + 1):
        w = 1 - k / (lags + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    return float(v.mean() / np.sqrt(s / n)) if s > 0 else float("nan")


def seg_stats(x: pd.Series, a: str | None = None, b: str | None = None) -> dict:
    """每月超额（pp）的一段：年化、t 值、年化夏普、累计（加总）的最大回撤、月数。"""
    s = x.dropna()
    if a:
        s = s[s.index >= pd.Timestamp(a)]
    if b:
        s = s[s.index <= pd.Timestamp(b)]
    if len(s) < 24:
        return {"n": int(len(s))}
    c = s.cumsum()
    return {"n": int(len(s)), "ann": float(s.mean() * 12), "t": nw_t(s), "sharpe": float(s.mean() / s.std() * np.sqrt(12)) if s.std() > 0 else None,
            "mdd": float((c - c.cummax()).min())}


# ── 描述 ──
def relative(R: pd.DataFrame) -> pd.DataFrame:
    L = np.log1p(R / 100.0) * 100
    return L.sub(L.mean(axis=1), axis=0)


def decade_leaders(Rel: pd.DataFrame, k: int = 5) -> dict:
    out = {}
    for d0 in range(1930, 2030, 10):
        s = Rel[(Rel.index.year >= d0) & (Rel.index.year < d0 + 10)]
        if len(s) < 24:
            continue
        tot = s.sum(min_count=24).dropna().sort_values()
        out[f"{d0}s"] = {"top": [(c, round(float(v), 1)) for c, v in tot[::-1][:k].items()],
                         "bottom": [(c, round(float(v), 1)) for c, v in tot[:k].items()], "months": int(len(s))}
    return out


def persistence(Rel: pd.DataFrame, years: int) -> dict:
    """每年末：过去 years 年相对收益的名次与之后 years 年的秩相关；按段平均。"""
    m = 12 * years
    C = Rel.rolling(m, min_periods=m).sum()
    fut = C.shift(-m)
    rows = []
    for t in C.index[C.index.month == 12]:
        a, b = C.loc[t], fut.loc[t]
        ok = a.notna() & b.notna()
        if ok.sum() >= 20:
            rows.append((t, float(a[ok].rank().corr(b[ok].rank()))))
    s = pd.Series(dict(rows))
    out = {"all": float(s.mean()) if len(s) else None, "n": int(len(s))}
    for k, (a, b) in SUBS.items():
        z = s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]
        out[k] = float(z.mean()) if len(z) else None
    return out


def stay_top(Rel: pd.DataFrame, k: int = 10) -> dict:
    """每年末：过去 5 年前 k 名 → 之后 1 / 3 / 5 年仍在前 k 名的比例（随机 ≈ k / 有数据的行业数）。"""
    past = Rel.rolling(60, min_periods=60).sum()
    out = {}
    for h in (1, 3, 5):
        fut = Rel.rolling(12 * h, min_periods=12 * h).sum().shift(-12 * h)
        hit, base = [], []
        for t in past.index[past.index.month == 12]:
            a, b = past.loc[t], fut.loc[t]
            ok = a.notna() & b.notna()
            if ok.sum() < 20:
                continue
            ta = set(a[ok].sort_values()[::-1][:k].index)
            tb = set(b[ok].sort_values()[::-1][:k].index)
            hit.append(len(ta & tb) / k)
            base.append(k / ok.sum())
        out[h] = {"stay": float(np.mean(hit)) if hit else None, "random": float(np.mean(base)) if base else None, "n": len(hit)}
    return out


def run_rules(R: pd.DataFrame, k: int) -> dict:
    """各规则的每月收益、相对 B0 的超额、换手。"""
    b0 = R.mean(axis=1).shift(0)
    S = scores(R)
    out = {"B0": b0}
    sel = {}
    for c in CANDS:
        sel[c] = select_top(S[c], k)
        out[c] = backtest(R, sel[c])
    ex = {c: (out[c] - b0) for c in CANDS}
    return {"ret": out, "ex": ex, "turn": {c: turnover(sel[c]) for c in CANDS}, "sel": sel}


def main() -> int:
    from qbreak import factors as F
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/era_study.py"], capture_output=True, text=True).stdout.strip())
    R = F.ff_industries(49, "vw")
    R = R[R.index <= pd.Timestamp("2026-08-31")]
    Rel = relative(R)
    cn = lambda c: f"{c} {FF49_CN.get(c, c)}"                                                  # noqa: E731
    say("# 时代主线：领先行业能持续多久、跟着时代走有没有用（登记检验，2026-09-27）")
    say(f"规则见 scripts/era_study.py 开头（先提交后运行）。美国 49 行业（Ken French，含退市公司）{R.index[0]:%Y-%m}〜{R.index[-1]:%Y-%m}，价值加权月收益。")
    say("\n## 一、每十年相对最强 / 最弱的 5 个行业（相对收益 = 对数收益 − 当月行业平均，十年加总，%）")
    dec = decade_leaders(Rel)
    for d, v in dec.items():
        say(f"- {d}：强 " + "、".join(f"{cn(c)} {x:+.0f}" for c, x in v["top"]) + "｜弱 " + "、".join(f"{cn(c)} {x:+.0f}" for c, x in v["bottom"]))
    say("\n## 二、领先能持续多久（过去 N 年名次与之后 N 年名次的秩相关，每年末一个起点的平均；> 0 = 持续、< 0 = 反转）")
    per = {y: persistence(Rel, y) for y in (1, 3, 5, 10)}
    say("| N 年 | 全期 | 1931〜1962 | 1963〜1994 | 1995〜2026 |")
    say("|---|---|---|---|---|")
    fa = lambda v, f="{:+.3f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    for y, v in per.items():
        say(f"| {y} | {fa(v['all'])} | {fa(v['S1'])} | {fa(v['S2'])} | {fa(v['S3'])} |")
    st = stay_top(Rel)
    say("过去 5 年前 10 名之后仍在前 10 名的比例：" + "；".join(f"之后 {h} 年 {fa(v['stay'], '{:.0%}')}（随机 {fa(v['random'], '{:.0%}')}）" for h, v in st.items()))
    rr = run_rules(R, K_US)
    say("\n## 三、检验：各规则相对「全部行业等权」的年化超额（%）/ t 值（NW 12）")
    say("| 规则 | 全期 | 1931-07〜1962 | 1963〜1994 | 1995〜2026-08 | 每月换手 |")
    say("|---|---|---|---|---|---|")
    stats = {}
    for c in CANDS:
        ex = rr["ex"][c]
        stats[c] = {"all": seg_stats(ex, "1931-07-01"), **{k: seg_stats(ex, a, b) for k, (a, b) in SUBS.items()}}
        cell = lambda s: "—" if "ann" not in s else f"{s['ann']:+.2f}% / t {s['t']:+.2f}"          # noqa: E731
        say(f"| {c} {CANDS[c]} | {cell(stats[c]['all'])} | {cell(stats[c]['S1'])} | {cell(stats[c]['S2'])} | {cell(stats[c]['S3'])} | "
            f"{rr['turn'][c]:.0%} |")
    say("\n## 四、判定：候选 − M12（年化 %，t 值 NW 12）；通过 = 三段都 > 0 且全期 t ≥ 2.0")
    say("| 候选 | 全期 | 1931-07〜1962 | 1963〜1994 | 1995〜2026-08 | 判定 |")
    say("|---|---|---|---|---|---|")
    vs, passed = {}, []
    for c in ("E36", "E60", "ER", "EN"):
        d = rr["ret"][c] - rr["ret"]["M12"]
        vs[c] = {"all": seg_stats(d, "1931-07-01"), **{k: seg_stats(d, a, b) for k, (a, b) in SUBS.items()}}
        ok = all(vs[c][k].get("ann", -1) > 0 for k in SUBS) and (vs[c]["all"].get("t") or 0) >= T_MIN
        if ok:
            passed.append(c)
        cell = lambda s: "—" if "ann" not in s else f"{s['ann']:+.2f}% / t {s['t']:+.2f}"          # noqa: E731
        say(f"| {c} {CANDS[c]} | {cell(vs[c]['all'])} | {cell(vs[c]['S1'])} | {cell(vs[c]['S2'])} | {cell(vs[c]['S3'])} | {'✓' if ok else '✗'} |")
    use = max(passed, key=lambda c: vs[c]["all"]["t"]) if passed else "M12"
    say(f"\n**结论：{'、'.join(passed) + ' 通过' if passed else '没有候选通过'} → 「时代主线」排序用 {use}（{CANDS[use]}）。**")
    now = {c: rr["sel"][c].iloc[-1] for c in CANDS}
    sc = scores(R)
    say(f"\n## 五、现在（{R.index[-1]:%Y-%m} 末）各规则选中的行业（只描述；{use} = 本研究的结论用的那个）")
    for c in CANDS:
        top = sc[c].iloc[-1].dropna().sort_values()[::-1][:K_US]
        say(f"- {c}：" + "、".join(cn(x) for x in top.index))
    jp = japan(say)
    say(f"\n代码版本 {code}" + ("（★ 与提交的版本不同）" if dirty else "（与提交的版本相同）") + f"；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "decades": dec, "persistence": per, "stay_top": st, "stats_vs_b0": stats, "vs_m12": vs,
           "passed": passed, "use": use, "now": {c: list(sc[c].iloc[-1].dropna().sort_values()[::-1][:K_US].index) for c in CANDS},
           "japan": jp}
    fp = paths.out_dir() / "era_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


# ── 日本（只描述）──
def jp_sector_returns_jq() -> pd.DataFrame:
    """J-Quants 全部股票（一般市场、时点上市一览）→ 東証 33 业种的月收益 %（按上月末时价总额加权）。"""
    import allstock_data as AD
    A = AD.load()
    days, names = A["days"], A["names"]
    snaps = AD.snapshots()
    s33 = {}
    for d in sorted(snaps):
        m = snaps[d]
        for code, nm in zip(m["Code"].astype(str), m.get("S33Nm", pd.Series("", index=m.index)).astype(str)):
            if len(code) == 5 and code.endswith("0") and nm not in ("", "nan", "その他", "-"):
                s33[code[:4] + ".T"] = nm
    ends = pd.Series(days, index=days).groupby(days.to_period("M")).last()
    ei = days.get_indexer(pd.DatetimeIndex(ends.to_numpy()))
    C, MC, LI = A["C"][ei].astype(float), A["MC"][ei].astype(float), A["listed"][ei]
    r = (C[1:] / C[:-1] - 1) * 100
    w = np.where(LI[1:] & np.isfinite(r) & np.isfinite(MC[:-1]) & (MC[:-1] > 0), MC[:-1], 0.0)
    sec = np.array([s33.get(t, "") for t in names])
    out = {}
    for s in sorted(set(sec) - {""}):
        j = sec == s
        num = np.nansum(np.where(w[:, j] > 0, r[:, j] * w[:, j], 0.0), axis=1)
        den = w[:, j].sum(axis=1)
        out[s] = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    idx = pd.DatetimeIndex(ends.to_numpy()[1:]).to_period("M").to_timestamp()
    return pd.DataFrame(out, index=idx)


def jp_sector_returns_yf() -> pd.DataFrame:
    """2006〜2016：日経225 + 扩大池（yfinance，今天的成员）→ 東証 33 业种等权月收益 %。"""
    import candle_data as CD
    import wvol_wide as WW
    from qbreak import wide_universe as WU
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    D = CD.load()
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
    Pw, dw, nw = WW.panel(load_universe(WU.tickers(WU.load()), d21), "2005-09-01", "2016-11-30")
    C = pd.concat([pd.DataFrame(D["E"]["C"], index=D["edays"], columns=D["enames"]), pd.DataFrame(Pw["C"], index=dw, columns=nw)], axis=1)
    C = C.loc[:, ~C.columns.duplicated()]
    s33 = json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"]
    me = C.groupby(C.index.to_period("M")).last()
    r = me.pct_change() * 100
    r.index = r.index.to_timestamp()
    sec = pd.Series({t: s33.get(t.split(".")[0], "") for t in r.columns})
    out = {s: r[list(sec[sec == s].index)].mean(axis=1) for s in sorted(set(sec) - {""}) if (sec == s).sum() >= 2}
    return pd.DataFrame(out)


def japan(say_) -> dict:
    out = {}
    say_("\n## 六、日本（只描述，不判定）：東証 33 业种，同样的规则选 7 个，相对全部业种等权的年化超额（%）/ t 值")
    for key, name, fn, a, b in (("yf", "2006-01〜2016-09（日経225 + 扩大池，等权）", jp_sector_returns_yf, "2006-01-01", "2016-09-30"),
                                ("jq", "2016-11〜2026-08（J-Quants 全部股票，时价总额加权）", jp_sector_returns_jq, "2016-11-01", "2026-08-31")):
        try:
            R = fn()
        except Exception as e:                                           # noqa: BLE001
            say_(f"- {name}：取不到（{type(e).__name__}: {e}）")
            continue
        R = R[(R.index >= pd.Timestamp(a)) & (R.index <= pd.Timestamp(b))].dropna(axis=1, how="all")
        rr = run_rules(R, K_JP)
        row = {c: seg_stats(rr["ex"][c], a, b) for c in CANDS}
        vs = {c: seg_stats(rr["ret"][c] - rr["ret"]["M12"], a, b) for c in ("E36", "E60", "ER", "EN")}
        cell = lambda s: "—" if "ann" not in s else f"{s['ann']:+.2f}% / t {s['t']:+.2f}"                # noqa: E731
        say_(f"- {name}（{R.shape[1]} 个业种）：相对等权 " + "；".join(f"{c} {cell(row[c])}" for c in CANDS)
             + "｜减 M12：" + "；".join(f"{c} {cell(vs[c])}" for c in vs))
        sc = scores(R)
        out[key] = {"vs_b0": row, "vs_m12": vs, "now": {c: list(sc[c].iloc[-1].dropna().sort_values()[::-1][:K_JP].index) for c in CANDS},
                    "last": str(R.index[-1].date())}
        if key == "jq":
            for c in ("M12", "ER", "EN"):
                say_(f"  现在（{R.index[-1]:%Y-%m} 末）{c}：" + "、".join(out[key]["now"][c]))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
