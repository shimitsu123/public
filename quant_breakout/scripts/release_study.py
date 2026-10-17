"""release_study.py — 用价格压力预测「即将会跌」：压力高过之后开始释放 → 之后 60 个交易日内会不会跌 ≥ 10%
（2026-09-29 先登记研究框架，再只在探索数据上挑候选，挑好后再登记，最后在没看过的数据上只确认一次；看完不改规则）。

用户：「利用之前的价格压力做一个可以预测即将会跌的研究」。
以前知道的（pressure_study，38b648e）：价格压力的「水平」本身没有预警力，60 天还是反的（美国 AUC 0.33：涨得越多之后越不容易大跌）；
能预测近期大跌的是「已经在跌」（跌破 200 日线、波动、信用利差扩大：threat 研究）。所以这里检验用户直觉的下一步：
「压力高过、然后开始释放」时，是不是比「一样开始回落、但之前没有高压」更容易接着大跌——压力的价值 = 同一个释放信号有没有高压的差。

零 价格压力（每天；与 pressure_study 同一定义，只是按天）：P = 平均(离 500 个交易日最低收盘的涨幅、250 日线乖离) 各自在过去 2,520 个交易日
   （含当天、至少 1,260 个）里的分位（≤ 它的比例 × 100）。
一 目标：t 日收盘之后 60 个交易日内最低收盘 ÷ t 收盘 − 1 ≤ −10%（与威胁指数同一个目标）；另报 20 天内 ≤ −5%。
二 候选（44 个；事件 = 条件第一次成立、且之前 60 个交易日里都不成立的那天）：
   A 高压 + 回落：过去 L 天 P 的最高 ≥ H，且收盘比 20 日最高低 D% 以上；L ∈ {20, 60}、H ∈ {70, 80, 90}、D ∈ {3, 5, 7}；对照 = 只有「比 20 日最高低 D%」。
   B 高压 + 跌破 50 日线：过去 L 天 P 的最高 ≥ H，且收盘 < 50 日均线；L、H 同上；对照 = 只有「跌破 50 日线」。
   C 压力骤降：过去 L 天 P 的最高 ≥ H，且 P 比那个最高低了 K 以上；L、H 同上，K ∈ {20, 30, 40}；对照 = 只有「P 比过去 L 天最高低了 K 以上」。
   D 极端压力（吹顶）：P ≥ H′，H′ ∈ {95, 98}；对照 = 全部日子的比例（独立市场合并时，每个市场每 20 个交易日取一天代表「全部日子」，
     免得日子多的市场压过事件）。
   另报（不是候选）：跌破 200 日线（已知最好的「已经在跌」信号）。
三 数据：
   探索 = 美国 S&P 500（^GSPC）1950〜1999、日本 日経225（^N225）1970〜1999（事件日在这些年里）。
   确认（探索时不看）= 美国 2000〜、日本 2000〜（60 天之后的数据要齐），以及以前只用于威胁指数的 21 个独立市场（threat_intl_study 的缓存：
   欧洲 10、其他发达 5、新兴 6；全历史；这个信号从来没在上面算过）。
四 挑选（事先写定，只看探索数据）：两个市场都 ≥ 10 个事件的候选里，按「min(美国, 日本) 的（命中率 − 对照命中率）」从高到低，
   分数 > 0 且命中率都高于全部日子的比例才算，最多 5 个、每类最多 2 个；分数一样 → 事件多的优先。一个都没有 → 到此为止（不做确认）。
五 判定（事先写定，每个登记的候选各判一次）：
   ① 美国 2000〜 与 日本 2000〜：各自事件 ≥ 5 个，命中率 ≥ 全部日子的比例 + 10 pp，且 ≥ 对照命中率 + 5 pp；
   ② 21 个独立市场：合并的（命中率 − 对照命中率）≥ +5 pp 且 95% 区间下限 > 0（事件按跨市场 90 天内同一次大跌整段重抽，2,000 次，
      种子 20260929），并且在事件 ≥ 5 个的市场里 ≥ 60% 的市场命中率 ≥ 对照；
   ①② 都满足 →「通过」（提议日报加一栏 + 前向记录；要用到交易另外登记账户层检验、要你确认）；其余「不通过」。
用法：python scripts/release_study.py --explore（只算探索数据）→ 把挑出来的写进 REGISTERED 并提交 → python scripts/release_study.py --confirm。
输出：var/out/release_explore.md / .json、var/out/release_study.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import deepdip_forward as DF                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402

RUNUP_D, MA_D, PCT_W, PCT_MIN = 500, 250, 2520, 1260
H_FWD, DROP, H_SHORT, DROP_SHORT = 60, -10.0, 20, -5.0
REFRACT = 60
LS, HS, DS, KS, HX = (20, 60), (70, 80, 90), (3, 5, 7), (20, 30, 40), (95, 98)
EXPLORE = {"US": ("^GSPC", "1950-01-01", "1999-12-31"), "JP": ("^N225", "1970-01-01", "1999-12-31")}
CONFIRM_FROM = "2000-01-01"
MIN_EXPLORE_N, MAX_PICK, MAX_PER_FAMILY = 10, 5, 2
MIN_N, LIFT_BASE, LIFT_REF, MKT_SHARE = 5, 10.0, 5.0, 60.0
N_BOOT, SEED = 2000, 20260929
REGISTERED: list[str] = []                                                   # 探索之后按第四节写进来并提交，再做 --confirm


# ─────────────── 每天的量 ───────────────
def pressure(c: pd.Series) -> pd.Series:
    """价格压力（0〜100）：离两年低点的涨幅与 250 日线乖离，各自在过去 2,520 个交易日里的分位，取平均。"""
    c = c.dropna().astype(float)
    runup = np.log(c / c.rolling(RUNUP_D, min_periods=RUNUP_D).min())
    ma = np.log(c / c.rolling(MA_D, min_periods=MA_D).mean())
    pr = [x.rolling(PCT_W, min_periods=PCT_MIN).rank(method="max", pct=True) * 100 for x in (runup, ma)]
    return (pr[0] + pr[1]) / 2


def frame(c: pd.Series) -> pd.DataFrame:
    """一个市场每天的：P、过去 L 天 P 的最高、比 20 日最高低多少、是否在 50 / 200 日线之下、目标。"""
    c = c.dropna().astype(float)
    P = pressure(c)
    a = c.to_numpy(float)
    n = len(a)
    f = pd.DataFrame(index=c.index)
    f["close"], f["P"] = a, P.to_numpy(float)
    for L in LS:
        f[f"Pmax{L}"] = P.rolling(L, min_periods=L).max().to_numpy(float)
    f["dd20"] = (c / c.rolling(20, min_periods=20).max() - 1).to_numpy(float) * 100
    f["below50"] = (c < c.rolling(50, min_periods=50).mean()).to_numpy(bool) & c.rolling(50, min_periods=50).mean().notna().to_numpy()
    f["below200"] = (c < c.rolling(200, min_periods=200).mean()).to_numpy(bool) & c.rolling(200, min_periods=200).mean().notna().to_numpy()
    for h, thr, nm in ((H_FWD, DROP, "y60"), (H_SHORT, DROP_SHORT, "y20")):
        y = np.full(n, np.nan)
        rt = np.full(n, np.nan)
        for i in range(n - h):
            y[i] = float((a[i + 1:i + h + 1].min() / a[i] - 1) * 100 <= thr)
            rt[i] = (a[i + h] / a[i] - 1) * 100
        f[nm] = y
        if h == H_FWD:
            f["ret60"] = rt
    return f


# ─────────────── 候选 ───────────────
def candidates() -> dict[str, dict]:
    """{id: {family, cond(f) → 布尔, ref: 对照 id 或 None（全部日子）}}；对照也放在同一个表里（family = "ref"）。"""
    C = {}
    for D in DS:
        C[f"R_dd{D}"] = {"family": "ref", "desc": f"比 20 日最高低 ≥ {D}%", "cond": lambda f, D=D: f["dd20"] <= -D}
    C["R_ma50"] = {"family": "ref", "desc": "跌破 50 日线", "cond": lambda f: f["below50"]}
    for L in LS:
        for K in KS:
            C[f"R_drop{L}_{K}"] = {"family": "ref", "desc": f"P 比过去 {L} 天最高低 ≥ {K}", "cond": lambda f, L=L, K=K: (f[f"Pmax{L}"] - f["P"]) >= K}
    C["REF200"] = {"family": "ref", "desc": "跌破 200 日线（已知信号，只作参考）", "cond": lambda f: f["below200"]}
    for L in LS:
        for H in HS:
            for D in DS:
                C[f"A_L{L}_H{H}_D{D}"] = {"family": "A", "ref": f"R_dd{D}", "desc": f"过去 {L} 天 P 最高 ≥ {H} 且比 20 日最高低 ≥ {D}%",
                                          "cond": lambda f, L=L, H=H, D=D: (f[f"Pmax{L}"] >= H) & (f["dd20"] <= -D)}
            C[f"B_L{L}_H{H}"] = {"family": "B", "ref": "R_ma50", "desc": f"过去 {L} 天 P 最高 ≥ {H} 且跌破 50 日线",
                                 "cond": lambda f, L=L, H=H: (f[f"Pmax{L}"] >= H) & f["below50"]}
            for K in KS:
                C[f"C_L{L}_H{H}_K{K}"] = {"family": "C", "ref": f"R_drop{L}_{K}", "desc": f"过去 {L} 天 P 最高 ≥ {H} 且 P 比最高低 ≥ {K}",
                                          "cond": lambda f, L=L, H=H, K=K: (f[f"Pmax{L}"] >= H) & ((f[f"Pmax{L}"] - f["P"]) >= K)}
    for H in HX:
        C[f"D_P{H}"] = {"family": "D", "ref": None, "desc": f"P ≥ {H}（极端压力）", "cond": lambda f, H=H: f["P"] >= H}
    return C


def events(cond: pd.Series, refract: int = REFRACT) -> pd.DatetimeIndex:
    """条件第一次成立、且之前 refract 个交易日里都不成立的那天。"""
    c = cond.fillna(False).astype(bool)
    prev = c.shift(1, fill_value=False).astype(float).rolling(refract, min_periods=1).max().to_numpy() > 0
    return c.index[c.to_numpy() & ~prev]


def stats(f: pd.DataFrame, ev: pd.DatetimeIndex, a: str | None = None, b: str | None = None) -> dict:
    """事件（在 [a, b] 里、有 60 天结果的）的命中率、20 天命中率、之后 60 天平均涨跌；全部日子的比例。"""
    m = pd.Series(True, index=f.index)
    if a:
        m &= f.index >= pd.Timestamp(a)
    if b:
        m &= f.index <= pd.Timestamp(b)
    base = f.loc[m, "y60"].dropna()
    e = f.loc[f.index.isin(ev) & m.to_numpy()]
    e = e[e["y60"].notna()]
    return {"n": int(len(e)), "hit": None if not len(e) else round(float(e["y60"].mean() * 100), 1),
            "hit20": None if not len(e) else round(float(e["y20"].mean() * 100), 1),
            "ret60": None if not len(e) else round(float(e["ret60"].mean()), 2),
            "base": None if not len(base) else round(float(base.mean() * 100), 1), "dates": [str(d.date()) for d in e.index]}


def run_market(f: pd.DataFrame, ids, C, a=None, b=None) -> dict:
    need = set(ids) | {C[i]["ref"] for i in ids if C[i].get("ref")} | {"REF200"}
    return {i: stats(f, events(C[i]["cond"](f)), a, b) for i in need}


def score(res: dict, cid: str, C: dict) -> float | None:
    """探索的分数：min(美国, 日本) 的（命中率 − 对照命中率）；对照 = None → 全部日子的比例。"""
    vals = []
    for mk in ("US", "JP"):
        r = res[mk][cid]
        ref = C[cid].get("ref")
        rb = res[mk][ref]["hit"] if ref else r["base"]
        if r["hit"] is None or rb is None:
            return None
        vals.append(r["hit"] - rb)
    return round(min(vals), 1)


def pick(res: dict, C: dict) -> list[str]:
    """第四节：两个市场都 ≥ 10 个事件、分数 > 0、命中率都高于全部日子 → 按分数（再按事件数）取最多 5 个、每类最多 2 个。"""
    rows = []
    for cid, c in C.items():
        if c["family"] == "ref":
            continue
        if any(res[mk][cid]["n"] < MIN_EXPLORE_N for mk in ("US", "JP")):
            continue
        s = score(res, cid, C)
        if s is None or s <= 0 or any(res[mk][cid]["hit"] <= res[mk][cid]["base"] for mk in ("US", "JP")):
            continue
        rows.append((s, res["US"][cid]["n"] + res["JP"][cid]["n"], cid))
    out, per = [], {}
    for s, n, cid in sorted(rows, key=lambda x: (-x[0], -x[1], x[2])):
        fam = C[cid]["family"]
        if per.get(fam, 0) >= MAX_PER_FAMILY:
            continue
        out.append(cid)
        per[fam] = per.get(fam, 0) + 1
        if len(out) >= MAX_PICK:
            break
    return out


def pooled_diff(ev_rows: list[dict], n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """ev_rows：{date, kind ∈ {cand, ref}, y}（多个市场合在一起）→ 命中率差（候选 − 对照）与 95% 区间（跨市场 90 天内同一次大跌整段重抽）。"""
    if not ev_rows:
        return {"diff": None}
    lab = DF.episode_labels([r["date"] for r in ev_rows])
    groups: dict[int, list[dict]] = {}
    for r, g in zip(ev_rows, lab):
        groups.setdefault(g, []).append(r)

    def d(rows):
        c = [r["y"] for r in rows if r["kind"] == "cand"]
        f = [r["y"] for r in rows if r["kind"] == "ref"]
        return None if not c or not f else (np.mean(c) - np.mean(f)) * 100
    d0 = d(ev_rows)
    keys = sorted(groups)
    rng = np.random.default_rng(seed)
    vals = [v for v in (d([r for k in rng.integers(0, len(keys), len(keys)) for r in groups[keys[k]]]) for _ in range(n_boot)) if v is not None]
    if d0 is None or not vals:
        return {"diff": None}
    return {"diff": round(float(d0), 1), "lo": round(float(np.percentile(vals, 2.5)), 1), "hi": round(float(np.percentile(vals, 97.5)), 1),
            "episodes": len(keys)}


def verdict(home: dict, intl: dict, cid: str, C: dict) -> dict:
    """第五节。home = {US/JP: {id: stats}}（2000〜）；intl = {pooled: pooled_diff, share: 市场比例, n_mkts: 有 ≥ 5 个事件的市场数}。"""
    ref = C[cid].get("ref")
    ok1, why = True, []
    for mk in ("US", "JP"):
        r = home[mk][cid]
        rb = home[mk][ref]["hit"] if ref else r["base"]
        if r["n"] < MIN_N or r["hit"] is None or rb is None:
            ok1 = False
            why.append(f"{mk} 事件不足")
            continue
        if r["hit"] < r["base"] + LIFT_BASE or r["hit"] < rb + LIFT_REF:
            ok1 = False
            why.append(f"{mk} {r['hit']:.0f}%（全部 {r['base']:.0f}%、对照 {rb:.0f}%）")
    p = intl.get("pooled") or {}
    ok2 = (p.get("diff") is not None and p["diff"] >= LIFT_REF and p.get("lo", -1) > 0 and (intl.get("share") or 0) >= MKT_SHARE)
    if not ok2:
        why.append(f"独立市场 差 {p.get('diff')}（区间 {p.get('lo')}〜{p.get('hi')}）、市场比例 {intl.get('share')}%")
    return {"label": "通过" if ok1 and ok2 else "不通过", "why": why}


# ─────────────── 数据 ───────────────
def home_close(sym: str) -> pd.Series:
    from bullbear_study import load
    return load(sym, "1900-01-01")["Close"].astype(float)


def intl_closes() -> dict[str, pd.Series]:
    import threat_intl_study as TI
    out = {}
    for k, (sym, *_rest) in TI.MARKETS.items():
        try:
            out[k] = TI.index_close(sym)[0]
        except Exception as e:                                               # noqa: BLE001
            print(f"{k} 取不到：{e}")
    return out


def explore() -> int:
    C = candidates()
    ids = [k for k, v in C.items() if v["family"] != "ref"]
    res = {}
    for mk, (sym, a, b) in EXPLORE.items():
        f = frame(home_close(sym))
        res[mk] = run_market(f, ids, C, a, b)
    chosen = pick(res, C)
    rows = []
    for cid in ids:
        rows.append((score(res, cid, C), cid))
    rows.sort(key=lambda x: (-(x[0] if x[0] is not None else -999), x[1]))
    L = ["# 压力释放预警：探索（只看美国 1950〜1999、日本 1970〜1999；2026-09-29；规则见 scripts/release_study.py 开头）", "",
         f"挑出来（第四节的规则）：{'、'.join(chosen) if chosen else '没有 → 到此为止，不做确认'}", "",
         "| 候选 | 说明 | 美国 事件 / 命中 / 对照 / 全部 | 日本 事件 / 命中 / 对照 / 全部 | 分数（min 命中 − 对照） |", "|---|---|---|---|---|"]
    for s, cid in rows:
        cells = []
        for mk in ("US", "JP"):
            r = res[mk][cid]
            ref = C[cid].get("ref")
            rb = res[mk][ref]["hit"] if ref else r["base"]
            cells.append(f"{r['n']} / {r['hit'] if r['hit'] is not None else '—'}% / {rb if rb is not None else '—'}% / {r['base']}%")
        L.append(f"| {cid} | {C[cid]['desc']} | {cells[0]} | {cells[1]} | {s if s is not None else '—'} |")
    L += ["", "对照（只有释放、没有压力条件）与参考：" + "；".join(
        f"{k}（{C[k]['desc']}）美国 {res['US'][k]['n']} 个 {res['US'][k]['hit']}%、日本 {res['JP'][k]['n']} 个 {res['JP'][k]['hit']}%"
        for k in C if C[k]["family"] == "ref" and k in res["US"]), "", "命中 = 事件之后 60 个交易日内跌 ≥ 10% 的比例；全部 = 所有日子的比例。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "release_explore"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"chosen": chosen, "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def confirm() -> int:
    if not REGISTERED:
        print("REGISTERED 是空的：探索没有挑出候选（或还没登记）→ 不做确认")
        return 0
    C = candidates()
    home = {}
    for mk, (sym, _a, _b) in EXPLORE.items():
        home[mk] = run_market(frame(home_close(sym)), REGISTERED, C, CONFIRM_FROM, None)
    intl_raw = {k: frame(c) for k, c in intl_closes().items()}
    intl = {}
    for cid in REGISTERED:
        ref = C[cid].get("ref")
        rows, per = [], {}
        for k, f in intl_raw.items():
            ec = events(C[cid]["cond"](f))
            er = events(C[ref]["cond"](f)) if ref else f.index[f["y60"].notna()]
            sc, sr = stats(f, ec), stats(f, er)
            per[k] = {"n": sc["n"], "hit": sc["hit"], "ref_hit": sr["hit"], "ref_n": sr["n"]}
            yv = f["y60"]
            rows += [{"date": d, "kind": "cand", "y": float(yv.loc[d])} for d in ec if np.isfinite(yv.loc[d])]
            if ref:
                rows += [{"date": d, "kind": "ref", "y": float(yv.loc[d])} for d in er if np.isfinite(yv.loc[d])]
            else:                                                            # 对照 = 全部日子：每个市场按日子数加进去太多 → 用那个市场的比例当一个「对照事件」的权重
                rows += [{"date": d, "kind": "ref", "y": float(yv.loc[d])} for d in f.index[f["y60"].notna()][::20]]
        elig = [v for v in per.values() if v["n"] >= MIN_N and v["hit"] is not None and v["ref_hit"] is not None]
        share = round(100 * np.mean([v["hit"] >= v["ref_hit"] for v in elig]), 1) if elig else None
        intl[cid] = {"pooled": pooled_diff(rows), "share": share, "n_mkts": len(elig), "per": per}
    ver = {cid: verdict(home, intl[cid], cid, C) for cid in REGISTERED}
    L = ["# 压力释放预警：确认（美国 / 日本 2000〜、21 个独立市场；只跑一次；2026-09-29；规则见 scripts/release_study.py 开头）", ""]
    for cid in REGISTERED:
        ref = C[cid].get("ref")
        L.append(f"## {cid}：{C[cid]['desc']} → **{ver[cid]['label']}**")
        for mk in ("US", "JP"):
            r = home[mk][cid]
            rb = home[mk][ref] if ref else None
            L.append(f"- {mk} 2000〜：事件 {r['n']} 个、之后 60 天内跌 ≥ 10% {r['hit']}%（全部日子 {r['base']}%；对照 "
                     + (f"{rb['n']} 个 {rb['hit']}%" if rb else "= 全部日子") + f"）、20 天内跌 ≥ 5% {r['hit20']}%、之后 60 天平均 {r['ret60']}%；"
                     f"参考 跌破 200 日线 {home[mk]['REF200']['n']} 个 {home[mk]['REF200']['hit']}%")
        p = intl[cid]["pooled"]
        L.append(f"- 独立市场：合并差（候选 − 对照）{p.get('diff')} pp（95% 区间 {p.get('lo')}〜{p.get('hi')}，{p.get('episodes')} 段）；"
                 f"事件 ≥ 5 个的 {intl[cid]['n_mkts']} 个市场里命中率 ≥ 对照的比例 {intl[cid]['share']}%")
        if ver[cid]["why"]:
            L.append("- 没过的条件：" + "；".join(ver[cid]["why"]))
        L.append("")
    L.append("命中 = 事件之后 60 个交易日内跌 ≥ 10% 的比例。非投资建议。")
    print("\n".join(L))
    fp = paths.out_dir() / "release_study"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"registered": REGISTERED, "verdict": ver, "home": home, "intl": intl}, ensure_ascii=False, indent=1,
                                             default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(explore() if "--explore" in sys.argv else confirm() if "--confirm" in sys.argv else (print(__doc__) or 0))
