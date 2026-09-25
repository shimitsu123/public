"""threat_weight_study.py — 威胁指数因素配比最优化：各种配比方式的严格样本外比较 + 用现在的数据预测之后 60 个交易日
（事先写定，先提交后运行，结果出来不改规则）。

用户要求（2026-09-25）：现在的所有因子进行配比最优化，做各类配比试验，得出最接近实际影响的配比，根据现在的数据预测未来。
已知的限制（写在前面）：v2 研究里「滚动逻辑回归」配权在 2011 年后反而比等权差（美股 0.561 vs 0.613、日経 0.512 vs 0.516）——
  1995 年以来独立的 ≥10% 下跌美股只有约 27 次、日経约 48 次，拟合近 100 个权重很容易过拟合。
  所以这次每种方法都带防过拟合的设计，并且只按严格的样本外（逐年滚动重估）结果判定。

因素（每个市场）：现行 v1 / v2 / v3（qbreak/threat.py US_V3 / JP_V3）+ 因子调查（qbreak/survey.py）全部，去掉数据源已停更的
  （survey.stale：本次为 OECD 先行指数 美 / 日 / 中、日本消费者信心、Shiller CAPE）→ 本次美股 95、日経 103 个，22 个领域。
  每个因素 = 扩张窗口百分位（同 v1；方向已统一为越高越危险；只用当时已公布的数据）；x = 百分位 − 0.5，缺值记 0（中性）。
目标：y = 之后 60 个交易日内最低收盘比当天跌 ≥10%（主），另报 ≥15%。
配比方式（A0 为基准；其余 11 种都是 x 的线性加权 分数 = b0 + x·β，只是权重的来历不同；qbreak/weights.py）：
  A0      现行 v1（美股 8 / 日経 10 个等权，原样）
  EW      全部因素等权                           DOM     领域均衡：22 个领域内先平均，再各领域等权
  AUCW    按训练期单因素 AUC 超过 0.5 的部分加权     TOP10   训练期单因素 AUC 最高的 10 个等权
  STAB    训练期前后两半都有效：权重 ∝ max(两半 AUC 的较小值 − 0.5, 0)（AUCW / TOP10 / STAB 全为 0 时退回 EW）
  A0NN    只给现行 v1 的因素重新配权（非负 L2 逻辑回归）
  RIDGE   全部因素 L2 逻辑回归                      LASSO   全部因素 L1 逻辑回归（稀疏，自动挑因素）
  NNRIDGE 全部因素非负 L2 逻辑回归（权重 ≥ 0：因素都已定向为越高越危险）
  PRIOR   向等权收缩的逻辑回归：等权分不受惩罚，各因素偏离等权的部分受 L2 惩罚
  DOMLR   22 个领域分的非负 L2 逻辑回归
  目标函数 = 平均对数损失 + 惩罚（截距不惩罚）。惩罚强度：L2 从 {0.0001, 0.001, 0.01, 0.1, 1}、L1 从 λmax × {0.02, 0.05, 0.1, 0.2, 0.5}
  里用训练期内的时间序列交叉验证选：训练样本按时间分 5 段，每段轮流作验证，验证段前后 60 个交易日的样本不进训练；
  取验证 AUC 平均最高者，差 < 0.002 时取惩罚更强的；有效段 < 2 时取中间值。
滚动样本外（walk-forward）：2005～2026 每年第一个交易日重估一次，只用 1995-01 起、答案已知（该日之前 60 个交易日以前）的样本，
  训练样本每 5 个交易日取 1 个（降低重叠）；该次的权重用于该年每一天。
  u = 当天分数在「该次训练样本分数分布」里的位置（0–1，101 个分位点线性插值）——跨年可比，不受权重尺度变化影响；A0 同样处理。
概率：每年重估时，用 2005 年起到该日、答案已知的过去样本外 u 做 Platt 校准（p = σ(a + b·u)），≥10% 与 ≥15% 各一套；
  气候预报 = 同一段数据的发生率。所有方式（含 A0）用同一段校准数据。
评估（主评估期 2011-01 起到答案已知的最后一天；只用所有方式都有值的日子，每种方式与 A0 在同一批日子上比）：
  AUC（用 u；跌 ≥10% / ≥15%；另报原始分数的 AUC）、Brier 技能分 BSS（相对气候预报）、子期间 2011–2018 / 2019– 的 ΔAUC、
  循环区块自助法（区块 250 个交易日、2000 次、种子 0）ΔAUC 的 5% 分位；
  描述：历次 ≥10% 下跌（高点 → 回落 10% 确认）之前 60 个交易日内 u 到过 0.9 / 0.8 的次数、u 与之后 60 日最大跌幅的秩相关、
  权重稳定性（各年重估权重与最终权重的秩相关平均、各因素在各年重估里权重为正的比例）。
判定（事先规则，每个市场分别）：同时满足
  ① AUC(≥10%) ≥ A0 + 0.03；② AUC(≥15%) ≥ A0；③ 自助法 ΔAUC 的 5% 分位 > 0；④ 两个子期间 ΔAUC 都 > 0；⑤ BSS(≥10%) > 0
  → 通过；通过者中取 AUC(≥10%) 最高的一个：日报显示它的预测概率、主要来源与配比（威胁指数 0–100 本身不自动替换，替换需用户确认）。
  没有通过者 → 日报显示「现行指数折算的概率」（A0 的 Platt 校准），配比优化结果只写进研究报告。不论结论如何都不改交易规则。
用现在的数据预测未来：每种方式用全部答案已知的样本（同一套交叉验证）重估最终权重，并用 2005 年起全部答案已知的样本外 u
  重新做 Platt 校准；给出今天「之后 60 个交易日内跌 ≥10% / ≥15%」的概率与基准发生率；配比 = 最终权重的占比（|β| 之和 = 100%），
  按因素与领域列出。最终权重与校准冻结到 var/threat_weights.json（第一次运行写入；之后只有每年 1 月复核时用 --refit 按同一套规则重估，
  其他时候不动）。
前瞻：从下一次日报起，每天用冻结的权重把各方式「跌 ≥10%」的概率记进 var/out/threat_weight_forward.csv（每个日期 × 市场保留最早值），
  季度复核时按 scripts/threat_forward_review.py 同一条前瞻判定规则检验（≥3 次 ≥10% 下跌、≥500 天结果已知之后）。
披露：因素清单是在看过部分历史结果之后设计的（v2 / v3 / 调查）；11 种方式 × 2 个市场一起比，某个方式碰巧过线的机会变大
  —— 所以加了自助法与子期间一致性两条；样本外期间的独立下跌次数少（运行时列出）。
输出 var/out/threat_weight_study.md / .json、var/threat_weights.json。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import survey as SV                                              # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak import weights as WT                                             # noqa: E402
from qbreak.bullbear import date_phases                                      # noqa: E402

EVAL0 = pd.Timestamp("1995-01-01")          # 训练样本起点
CAL0 = pd.Timestamp("2005-01-01")           # 样本外 u（= 校准数据）起点
OOS0 = pd.Timestamp("2011-01-01")           # 主评估期起点
SUB = pd.Timestamp("2019-01-01")            # 子期间分界
YEARS = list(range(2005, max(2026, pd.Timestamp.today().year) + 1))   # 逐年：本次 2005–2026；以后每年 1 月 --refit 时自然多一年
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def f3(v) -> str:
    return "—" if v is None or v != v else f"{v:.3f}"


def fd(v) -> str:
    return "—" if v is None or v != v else f"{v:+.3f}"


def pc(v) -> str:
    return "—" if v is None or v != v else f"{v * 100:.1f}%"


def universe(feats: pd.DataFrame, m: str, stale: dict) -> list[str]:
    base = TH.US_V3 if m == "US" else TH.JP_V3
    return [c for c in base if c in feats] + [k for k in SV.KEYS if k in feats and k not in base and k not in stale]


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30 or np.ptp(a[m]) == 0 or np.ptp(b[m]) == 0:        # 常数（如等权）没有秩相关
        return None
    ra, rb = pd.Series(a[m]).rank().to_numpy(), pd.Series(b[m]).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def episodes_hits(u: pd.Series, close: pd.Series, start: pd.Timestamp) -> dict:
    """历次 ≥10% 下跌（高点 → 回落 10% 确认）之前 60 个交易日内 u 到过 0.9 / 0.8 的次数。"""
    tp, _ = date_phases(close.dropna(), 0.10, 0.10)
    peaks = [p for p in tp[tp["kind"] == "peak"]["date"] if p >= start]
    h9 = sum(bool((u.loc[:p].tail(61) >= 0.9).any()) for p in peaks)
    h8 = sum(bool((u.loc[:p].tail(61) >= 0.8).any()) for p in peaks)
    return {"n": len(peaks), "hits90": h9, "hits80": h8, "peaks": [str(p.date()) for p in peaks]}


def norm_weights(beta: np.ndarray, cols: list[str]) -> dict[str, float]:
    s = float(np.abs(beta).sum())
    return {c: float(b / s) for c, b in zip(cols, beta) if b != 0} if s > 0 else {}


def run_market(m: str, F: dict, raw_sv: dict, stale: dict) -> dict:
    t0 = time.time()
    raw_ex, close = F[m]
    feats = pd.concat([raw_ex, SV.features(raw_ex.index, raw_sv, jp_market=(m == "JP"))], axis=1)
    feats = feats.loc[:, ~feats.columns.duplicated()]
    cols = universe(feats, m, stale)
    a0_cols = TH.US_COLS if m == "US" else TH.JP_COLS
    pct = pd.DataFrame({c: TH.expanding_pct(feats[c]) for c in cols})
    X = (pct - 0.5).fillna(0.0)
    a0 = TH._eq(pct[a0_cols])
    close = close.reindex(X.index)
    fdd = TH.forward_drawdown(close, WT.HORIZON)
    y10 = (fdd <= -0.10).astype(float).where(fdd.notna())
    y15 = (fdd <= -0.15).astype(float).where(fdd.notna())
    dom = {**SV.EXISTING_DOMAIN, **SV.DOMAIN}
    meta = {"cols": cols, "domain": {c: dom[c] for c in cols}, "a0_idx": [cols.index(c) for c in a0_cols]}
    name = "S&P500" if m == "US" else "日経225"
    say(f"\n## {name}：因素 {len(cols)} 个（{len(set(meta['domain'].values()))} 个领域）；逐年重估 {YEARS[0]}–{YEARS[-1]}")
    raw_s, u, fits = WT.walk_forward(X, y10, WT.SCHEMES, meta, YEARS, EVAL0, fixed={"A0": a0}, log=say)
    names = ["A0"] + WT.SCHEMES
    p10, p15, c10, c15 = {}, {}, {}, {}
    for k in names:
        p10[k], c10[k] = WT.calibrate_walk_forward(u[k], y10, YEARS, CAL0)
        p15[k], c15[k] = WT.calibrate_walk_forward(u[k], y15, YEARS, CAL0)
    idx = X.index
    mask = (idx >= OOS0) & y10.notna().to_numpy()
    for k in names:
        mask &= u[k].notna().to_numpy() & p10[k].notna().to_numpy()
    ev = {}
    yv, y15v = y10.to_numpy()[mask], y15.to_numpy()[mask]
    sub1 = idx[mask] < SUB
    depth = -fdd.to_numpy()[mask]
    for k in names:
        uk = u[k].to_numpy()[mask]
        pk, ck = p10[k].to_numpy()[mask], c10[k].to_numpy()[mask]
        b = float(np.mean((pk - yv) ** 2))
        bc = float(np.mean((ck - yv) ** 2))
        ev[k] = {"auc10": WT.auc_np(uk, yv), "auc15": WT.auc_np(uk, y15v),
                 "auc10_raw": WT.auc_np(raw_s[k].to_numpy()[mask], yv),
                 "auc10_sub": [WT.auc_np(uk[sub1], yv[sub1]), WT.auc_np(uk[~sub1], yv[~sub1])],
                 "brier10": b, "bss10": 1 - b / bc if bc > 0 else None,
                 "spearman_depth": spearman(uk, depth),
                 **episodes_hits(u[k].where(idx >= CAL0), close, OOS0)}
    base_u = u["A0"].to_numpy()[mask]
    boot = WT.block_bootstrap_delta({k: u[k].to_numpy()[mask] for k in WT.SCHEMES}, base_u, yv)
    for k in WT.SCHEMES:
        x = ev[k]
        a, a0e = x["auc10"], ev["A0"]
        x["d_auc10"] = None if a is None or a0e["auc10"] is None else a - a0e["auc10"]
        x["d_sub"] = [None if s is None or s0 is None else s - s0 for s, s0 in zip(x["auc10_sub"], a0e["auc10_sub"])]
        bb = boot[k][np.isfinite(boot[k])]
        x["boot_p05"] = float(np.quantile(bb, 0.05)) if len(bb) else None
        x["checks"] = {"①AUC≥A0+0.03": bool(x["d_auc10"] is not None and x["d_auc10"] >= 0.03),
                       "②≥15% AUC≥A0": bool(x["auc15"] is not None and a0e["auc15"] is not None and x["auc15"] >= a0e["auc15"]),
                       "③自助法5%分位>0": bool(x["boot_p05"] is not None and x["boot_p05"] > 0),
                       "④两个子期间都>0": bool(all(d is not None and d > 0 for d in x["d_sub"])),
                       "⑤BSS>0": bool(x["bss10"] is not None and x["bss10"] > 0)}
        x["pass"] = all(x["checks"].values())
    passed = [k for k in WT.SCHEMES if ev[k]["pass"]]
    adopted = max(passed, key=lambda k: ev[k]["auc10"]) if passed else None
    best = max(WT.SCHEMES, key=lambda k: ev[k]["auc10"] or 0)
    oos_days = int(mask.sum())
    say(f"\n主评估期 {idx[mask][0].date()} ～ {idx[mask][-1].date()}（{oos_days} 天；事件日比例 {pc(float(yv.mean()))}；"
        f"期间 ≥10% 下跌 {ev['A0']['n']} 次：{'、'.join(ev['A0']['peaks'])}）")
    say("| 方式 | AUC ≥10%（u） | ΔAUC vs A0 | 自助法 5% 分位 | ΔAUC 2011–18 / 2019– | AUC ≥15% | BSS | 下跌前到过 0.9 / 0.8 | 与跌幅秩相关 | 通过 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for k in names:
        x = ev[k]
        say(f"| {k} {WT.NAMES[k]} | {f3(x['auc10'])}（原始 {f3(x['auc10_raw'])}） | {fd(x.get('d_auc10'))} | {fd(x.get('boot_p05'))} | "
            f"{' / '.join(fd(d) for d in x.get('d_sub', [None, None]))} | {f3(x['auc15'])} | {fd(x['bss10'])} | "
            f"{x['hits90']} / {x['hits80']}（共 {x['n']}） | {f3(x['spearman_depth'])} | "
            f"{'基准' if k == 'A0' else ('是' if x['pass'] else '否：' + '、'.join(c for c, ok in x['checks'].items() if not ok))} |")
    say(f"\n判定（事先规则）：" + (f"{adopted}（{WT.NAMES[adopted]}）通过 → 日报显示它的预测概率与配比（替换 0–100 指数需用户确认）"
                            if adopted else f"没有方式通过 → 日报显示现行指数折算的概率；样本外 AUC 最高的是 {best}（{WT.NAMES[best]}）"))

    # ── 最终权重（全部答案已知的样本）+ 校准 + 今天的预测 ──
    yn = y10.to_numpy(float)
    tr = WT.train_positions(idx, yn, len(idx), EVAL0)
    known = idx[tr[-1]] if len(tr) else None
    Xn = X.to_numpy(float)
    final = {}
    cal_mask = (idx >= CAL0) & y10.notna().to_numpy()
    base10 = float(y10[cal_mask].mean())
    base15 = float(y15[cal_mask & y15.notna().to_numpy()].mean())
    for k in names:
        if k == "A0":
            sc_tr, sc_today, b0, beta, info = a0.to_numpy(float)[tr], float(a0.iloc[-1]), None, None, {}
        else:
            w, info = WT.fit_scheme(k, Xn[tr], yn[tr], tr, meta)
            b0, beta = float(w[0]), w[1:]
            sc_tr, sc_today = w[0] + Xn[tr] @ beta, float(w[0] + Xn[-1] @ beta)
        q = WT.quantiles(sc_tr)
        uk = u[k].to_numpy()
        a10 = WT.platt(uk[cal_mask], yn[cal_mask])
        m15 = cal_mask & y15.notna().to_numpy()
        a15 = WT.platt(uk[m15], y15.to_numpy()[m15])
        ut = float(WT.to_u([sc_today], q)[0])
        final[k] = {"b0": b0, "beta": ({c: float(b) for c, b in zip(cols, beta) if b != 0} if beta is not None else None),
                    "q": [float(v) for v in q], "cal10": list(a10), "cal15": list(a15), "u_today": ut,
                    "p10_today": WT.prob(list(a10), ut), "p15_today": WT.prob(list(a15), ut),
                    "info": {kk: vv for kk, vv in info.items() if kk in ("lam", "cv", "ew_coef", "dom_coef")},
                    "oos": {kk: ev[k].get(kk) for kk in ("auc10", "auc15", "d_auc10", "boot_p05", "bss10", "pass")}}
    show = adopted or best
    say(f"\n### 用现在的数据预测：{idx[-1].date()} 之后 60 个交易日（答案已知的训练样本到 {known.date() if known is not None else '—'}）")
    say(f"基准发生率（2005 年起）：跌 ≥10% {pc(base10)}、跌 ≥15% {pc(base15)}")
    say("| 方式 | 今天在训练期分布里的位置 u | 跌 ≥10% 概率 | 跌 ≥15% 概率 | 样本外 AUC |")
    say("|---|---|---|---|---|")
    for k in names:
        x = final[k]
        say(f"| {k} {WT.NAMES[k]} | {f3(x['u_today'])} | {pc(x['p10_today'])} | {pc(x['p15_today'])} | {f3(ev[k]['auc10'])} |")
    # ── 配比（最终权重的占比）与稳定性 ──
    stab = {}
    for k in WT.SCHEMES:
        fb = np.array(final[k]["beta"] and [final[k]["beta"].get(c, 0.0) for c in cols] or np.zeros(len(cols)))
        rs = [spearman(np.array(f["beta"]), fb) for f in fits[k] if f.get("beta")]
        pos = np.mean([np.array(f["beta"]) > 0 for f in fits[k]], axis=0) if fits[k] else np.zeros(len(cols))
        rs = [r for r in rs if r is not None and r == r]
        stab[k] = {"rank_corr_to_final": float(np.mean(rs)) if rs else None,
                   "pos_share": {c: float(v) for c, v in zip(cols, pos)},
                   "lam_by_year": {f["year"]: f["info"].get("lam") for f in fits[k] if "lam" in f.get("info", {})}}
    lab = {**TH.LABELS, **SV.LABELS}
    for k in dict.fromkeys([show, "NNRIDGE", "PRIOR"]):
        fb = np.array([final[k]["beta"].get(c, 0.0) for c in cols])
        nw = norm_weights(fb, cols)
        doms: dict[str, float] = {}
        for c, v in nw.items():
            doms[meta["domain"][c]] = doms.get(meta["domain"][c], 0.0) + v
        tag = "（判定采用）" if k == adopted else ("（样本外 AUC 最高，未通过判定，只作参考）" if k == show else "（参考）")
        say(f"\n### 配比：{k} {WT.NAMES[k]}{tag}；各年重估权重与最终权重的秩相关平均 {f3(stab[k]['rank_corr_to_final'])}")
        say("领域占比：" + "、".join(f"{d} {v * 100:.0f}%" for d, v in sorted(doms.items(), key=lambda kv: -abs(kv[1]))[:10]))
        say("| 因素 | 领域 | 占比 | 各年权重为正的比例 | 今天分位 |")
        say("|---|---|---|---|---|")
        for c, v in sorted(nw.items(), key=lambda kv: -abs(kv[1]))[:15]:
            say(f"| {lab.get(c, c)} | {meta['domain'][c]} | {v * 100:+.1f}% | {stab[k]['pos_share'][c] * 100:.0f}% | "
                f"{pct[c].iloc[-1] * 100:.0f} |")
    say(f"\n（{name} 用时 {time.time() - t0:.0f}s）")
    return {"cols": cols, "a0_cols": a0_cols, "eval": ev, "adopted": adopted, "best": best, "final": final,
            "stability": stab, "base10": base10, "base15": base15, "label_known_until": str(known.date()) if known is not None else None,
            "data_date": str(idx[-1].date()), "oos_days": oos_days}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refit", action="store_true", help="按同一套规则重估并覆盖 var/threat_weights.json（每年 1 月复核用）")
    a = ap.parse_args()
    t0 = time.time()
    today = pd.Timestamp.today().normalize()
    d = TH.load_inputs()
    F = TH.build_all(d, TH.load_extra_all())
    raw_sv = SV.load_raw()
    stale = SV.stale(raw_sv, today)
    say(f"# 威胁指数因素配比最优化（{today.date()}；数据截至 S&P500 {d['spx'].index[-1].date()} / 日経 {d['n225'].index[-1].date()}）")
    say("停更、不用的因素：" + ("、".join(f"{SV.LABELS.get(k, k)}（最后 {v}）" for k, v in stale.items()) or "无"))
    res = {m: run_market(m, F, raw_sv, stale) for m in ("US", "JP")}
    fp_w = paths.home() / "threat_weights.json"
    if a.refit or not fp_w.exists():
        W = {"fit_date": str(today.date()), "rule": "scripts/threat_weight_study.py（2026-09-25 事先登记）"}
        for m, r in res.items():
            W[m] = {"cols": r["cols"], "a0_cols": r["a0_cols"], "adopted": r["adopted"], "best": r["best"],
                    "base10": r["base10"], "base15": r["base15"], "label_known_until": r["label_known_until"],
                    "schemes": {k: {kk: v[kk] for kk in ("b0", "beta", "q", "cal10", "cal15", "oos")} for k, v in r["final"].items()}}
        fp_w.write_text(json.dumps(W, ensure_ascii=False, indent=1), encoding="utf-8")
        say(f"\n权重与校准已冻结到 {fp_w.relative_to(paths.home().parent)}（之后只在每年 1 月复核时 --refit）")
    else:
        say("\n（复核模式：没有改动冻结的权重 var/threat_weights.json）")
    fp_log = paths.out_dir() / "threat_weight_forward.csv"
    if fp_log.exists() and len(pd.read_csv(fp_log)):
        fr = TH.forward_review(pd.read_csv(fp_log), {"US": d["spx"], "JP": d["n225"]})
        res["forward"] = fr
        for m, r in fr.items():
            say(f"\n前瞻（{m}，{r['first']} 起 {r['days']} 天，结果已知 {r['known']} 天）：{r['decision']}")
    say(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "threat_weight_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
