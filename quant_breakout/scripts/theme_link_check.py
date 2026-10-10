"""theme_link_check.py — 新出现的行业 / 主题 / 公司，先和现有的東証 30 业种 + 12 个主题做关联对比（2026-09-26 用户要求：
「以后新出现的行业什么的都要和现有的行业进行关联性对比」「随着时间和科技的发展每个行业的影响度也都要考虑到」）。只是描述，不改交易。

三种用法（结果写 var/out/theme_link_<名>.md / .json）：
  python scripts/theme_link_check.py --name 数据中心电力 --codes 5803,5801,6501,6503,1942
      一组代码当作新主题：① 和每个现有组的同步程度（日相对收益的相关：全期 / 近 3 年 / 近 1 年）与成员分布；
      ② 影响度（与日経225 的 R²）历年变化；③ 月度领先 / 滞后（过去 3 个月 → 之后 3 个月，两个方向，Newey–West t +
      时间错开对照的经验 p（双侧））；④ 一句话归类（和现有的某组几乎一样 / 有关但不一样 / 和现有的都不像）。
  python scripts/theme_link_check.py --emerging
      日报「新出现的联动」检测到的股票群（qbreak/theme_monitor.py emerging），逐个做 ①〜④。
  python scripts/theme_link_check.py --new-listings
      JPX 最新名单里有、基准快照 var/jpx_codes_base.json（2026-08-31 的全部内国株代码）里没有的公司（新上市），
      每家和现有组的同步程度（有 ≥ 60 个交易日行情才算）→ 最像哪个现有业种 / 主题。
正式把新主题加进 qbreak/themes.py 之前先跑这个，结果与决定写进 var/sim_changes.md（改主题表要用户同意）。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import sector_leadlag as SL                                      # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak import theme_monitor as TM                                       # noqa: E402
from qbreak import themes as TH                                              # noqa: E402

GAP, MIN_MONTHS, W, H = 24, 60, 3, 3
SIM_SAME, SIM_REL = 0.8, 0.5


def basket(lr: pd.DataFrame, tickers: list[str]) -> pd.Series:
    """成员等权的日收益（%）；有行情的成员 < max(2, 一半) 的日子缺值。"""
    have = [t for t in tickers if t in lr.columns]
    if not have:
        return pd.Series(np.nan, index=lr.index)
    need = max(2, math.ceil(len(have) / 2)) if len(have) > 1 else 1
    sub = lr[have]
    return sub.mean(axis=1).where(sub.notna().sum(axis=1) >= need)


def similarity(b_rel: pd.Series, rel: pd.DataFrame) -> pd.DataFrame:
    """和每个现有组的日相对收益相关：全期 / 近 3 年（756 天）/ 近 1 年（250 天）。"""
    rows = {}
    for g in rel.columns:
        x = pd.concat([b_rel, rel[g]], axis=1).dropna()
        rows[g] = {k: (round(float(x.iloc[-n:].corr().iloc[0, 1]), 2) if len(x.iloc[-n:]) >= min(n, 120) else None)
                   for k, n in (("all", len(x)), ("y3", 756), ("y1", 250))}
    return pd.DataFrame(rows).T


def leadlag(b_rel: pd.Series, rel: pd.DataFrame) -> pd.DataFrame:
    """月度：新组过去 3 个月 → 现有组之后 3 个月，与反方向；t 与时间错开对照的双侧经验 p。"""
    M = SC.monthly(pd.concat([rel, b_rel.rename("__new")], axis=1))
    M = M[M["__new"].notna()]
    if len(M) < MIN_MONTHS:
        return pd.DataFrame()
    X, Y = SC.past(M, W), SC.ahead(M, H)
    months = M.index
    rows = []
    for g in rel.columns:
        for direction, (src, tgt) in (("新 → 现有", ("__new", g)), ("现有 → 新", (g, "__new"))):
            xv, yv = X[src].to_numpy(float), Y[tgt].to_numpy(float)
            t0 = SL.nw_t(xv, yv, W + H - 2)[1]
            pt = np.array([SL.nw_t(np.roll(xv, k), yv, W + H - 2)[1] for k in range(GAP, len(months) - GAP + 1)], float)
            a, b = SC.placebo_p(t0, pt, 1), SC.placebo_p(t0, pt, -1)
            p2 = None if a is None or b is None else round(min(1.0, 2 * min(a, b)), 4)
            rows.append({"group": g, "direction": direction, "t": round(float(t0), 2) if np.isfinite(t0) else None, "p": p2})
    return pd.DataFrame(rows)


def verdict(sim: pd.DataFrame) -> str:
    s = sim["y1"].dropna()
    if s.empty:
        return "行情不够，无法归类"
    g, v = s.idxmax(), float(s.max())
    if v >= SIM_SAME:
        return f"和现有的「{g}」几乎一样（近 1 年相关 {v:.2f}）→ 可以当作它的一部分看"
    if v >= SIM_REL:
        return f"和「{g}」有关但不完全一样（近 1 年相关 {v:.2f}）→ 可以作为新主题观察，同时看它和「{g}」的差别"
    return f"和现有的业种 / 主题都不太像（最高是「{g}」{v:.2f}）→ 新的独立主题候选"


def profile(name: str, tickers: list[str], lr: pd.DataFrame, s33: dict, rel: pd.DataFrame, mkt: pd.Series,
            idx_ret: pd.Series, nm: dict) -> tuple[dict, list[str]]:
    from collections import Counter
    mem = TH.members()
    b_raw = basket(lr, tickers)
    b_rel = b_raw - mkt
    sim = similarity(b_rel, rel)
    inf = TM.influence_by_year(b_raw.to_frame(name), idx_ret).get(name, {})
    now = TM.influence(b_raw.to_frame(name), idx_ret).get(name)
    ll = leadlag(b_rel, rel)
    have = [t for t in tickers if t in lr.columns]
    first = b_raw.first_valid_index()
    inds = Counter(s33.get(t, "（不在 TOPIX 1000）") for t in have)
    ths = Counter(mem.get(t.split(".")[0]) for t in have if mem.get(t.split(".")[0]))
    lab = lambda t: f"{t.split('.')[0]} {nm.get(t.split('.')[0], '')}".strip()     # noqa: E731
    gl = lambda g: f"{g} {TH.THEMES[g][0]}" if g in TH.THEMES else g                  # noqa: E731
    top = sim.sort_values("y1", ascending=False).head(8)
    L = [f"## {name}", "",
         f"成员 {len(have)} / {len(tickers)} 只有行情（{'、'.join(lab(t) for t in have[:20])}{' …' if len(have) > 20 else ''}）；"
         f"组的行情从 {first.date() if first is not None else '—'} 起；业种分布：{'、'.join(f'{k} {v}' for k, v in inds.most_common())}"
         + (f"；已在主题：{'、'.join(f'{gl(k)} {v}' for k, v in ths.most_common())}" if ths else ""), "",
         f"**归类**：{verdict(sim)}", "",
         "① 和现有组的同步程度（日相对收益的相关系数；近 1 年最高的 8 个）", "",
         "| 现有组 | 全期 | 近 3 年 | 近 1 年 |", "|---|---|---|---|"]
    L += [f"| {gl(g)} | {r['all']} | {r['y3']} | {r['y1']} |" for g, r in top.iterrows()]
    ys = sorted(inf)
    L += ["", f"② 影响度（与日経225 的同步度 R²）：近 1 年 {now}；历年 "
          + ("、".join(f"{y} {inf[y]}" for y in ys[::max(1, len(ys) // 8)] + ([ys[-1]] if ys and ys[-1] not in ys[::max(1, len(ys) // 8)] else []))
             if ys else "（不足一整年）"), ""]
    if ll.empty:
        L += [f"③ 月度领先 / 滞后：行情不足 {MIN_MONTHS} 个月，不做", ""]
    else:
        sig = ll[(ll["p"].notna()) & (ll["p"] < 0.05)].sort_values("p")
        L += [f"③ 月度领先 / 滞后（过去 {W} 个月 → 之后 {H} 个月；{len(ll)} 个检验里对照经验 p < 0.05 的 {len(sig)} 个，"
              f"没有关系时偶然约 {len(ll) * 0.05:.0f} 个）", ""]
        L += [f"- {r.direction}：{gl(r.group)} t {r.t:+.2f}（p {r.p}）" for r in sig.head(8).itertuples()] or ["- 无"]
        L.append("")
    out = {"name": name, "members": have, "n_wanted": len(tickers), "start": str(first.date()) if first is not None else None,
           "industries": dict(inds), "themes": dict(ths), "similarity": sim.reset_index().rename(columns={"index": "group"}).to_dict("records"),
           "influence_now": now, "influence_by_year": inf, "verdict": verdict(sim),
           "leadlag": ll.to_dict("records") if not ll.empty else []}
    return out, L


def slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z぀-ヿ一-鿿]+", "_", s).strip("_")[:40] or "theme"


def main(argv=None) -> int:
    from qbreak import jpx_list as JL
    from qbreak.config import BENCHMARK, DataConfig
    from qbreak.data import load_universe
    from qbreak.trader import drop_partial_bar
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--codes", help="逗号分隔的代码，例 5803,5801,6501")
    ap.add_argument("--emerging", action="store_true")
    ap.add_argument("--new-listings", action="store_true")
    a = ap.parse_args(argv)
    if not (a.codes or a.emerging or a.new_listings):
        ap.error("要 --codes（+ --name）、--emerging 或 --new-listings 之一")
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    nm = JL.names()
    base = sorted(set(s33) | {f"{c}.T" for c in TH.members()})
    extra: list[str] = []
    new_list, jdate = None, "—"
    if a.codes:
        extra = [f"{c.strip()}.T" for c in a.codes.split(",") if c.strip()]
    if a.new_listings:
        J = JL.fetch()
        J = J[J["market"].isin(JL.DOMESTIC)]
        jdate = str(J["date"].iloc[0]) if len(J) else "—"
        new_list = J[~J["code"].isin(JL.base_codes())]
        nm.update(dict(zip(J["code"], J["name"])))
        extra += [f"{c}.T" for c in new_list["code"]]
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data = {t: drop_partial_bar(df, "JP") for t, df in load_universe(sorted(set(base) | set(extra)), d21).items()}
    ix = drop_partial_bar(load_universe([BENCHMARK["JP"]], d21)[BENCHMARK["JP"]], "JP")
    lr = TM.log_returns(data)
    raw, rel, mkt = TM.group_panel(lr, s33)
    idx_ret = np.log(ix["Close"]).diff() * 100
    jobs: list[tuple[str, list[str]]] = []
    if a.codes:
        jobs.append((a.name or "新主题", extra[:len(a.codes.split(","))]))
    if a.emerging:
        e = TM.emerging(lr.iloc[-(TM.RECENT + TM.PRIOR + 5):], s33, rel.iloc[-(TM.RECENT + TM.PRIOR + 5):],
                        mkt.iloc[-(TM.RECENT + TM.PRIOR + 5):])
        for k, c in enumerate(e.get("clusters") or [], 1):
            jobs.append((f"新联动群{k}（{c['kind']}，{c['n']} 只）", c.get("all_members") or c["members"]))
    L_all = [f"# 新出现的行业 / 主题 和现有行业的关联对比（{pd.Timestamp.today().date()}；数据截至 {lr.index[-1].date()}）", "",
             "只是描述，不是买卖信号；要正式加进主题表（qbreak/themes.py）先经用户同意，并写进 var/sim_changes.md。", ""]
    res = {}
    for name, ts in jobs:
        out, L = profile(name, ts, lr, s33, rel, mkt, idx_ret, nm)
        res[name] = out
        L_all += L
        print("\n".join(L))
    if new_list is not None:
        rows = []
        for c, n, g in zip(new_list["code"], new_list["name"], new_list["s33"]):
            t = f"{c}.T"
            if t not in lr.columns or lr[t].notna().sum() < 60:
                rows.append((c, n, g, "行情 < 60 个交易日", ""))
                continue
            sim = similarity(lr[t] - mkt, rel)["y1"].dropna().sort_values(ascending=False)
            rows.append((c, n, g, "、".join(f"{k} {v:.2f}" for k, v in sim.head(3).items()), verdict(similarity(lr[t] - mkt, rel))))
        L = ["## 新出现的公司（最新 JPX 名单里有、基准快照 var/jpx_codes_base.json 里没有的内国株）", "",
             f"JPX 名单 {jdate} 版（基准 {JL.base_asof()} 版）：新出现 {len(new_list)} 家", ""]
        L += (["| 代码 | 公司 | 東証业种 | 最像的现有组（近 1 年相关） | 归类 |", "|---|---|---|---|---|"]
              + [f"| {c} | {n} | {g} | {s} | {v} |" for c, n, g, s, v in rows]) if rows else ["（没有）"]
        L_all += L + [""]
        res["new_listings"] = [dict(zip(("code", "name", "s33", "similar", "verdict"), r)) for r in rows]
        print("\n".join(L))
    tag = slug(a.name or ("emerging" if a.emerging else "new_listings"))
    fp = paths.out_dir() / f"theme_link_{tag}"
    Path(f"{fp}.md").write_text("\n".join(L_all) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\n写入 {fp}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
