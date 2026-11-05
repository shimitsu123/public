"""size_explore.py — 个股仓位分配（「预测涨幅大的多分配」）第一步：探索（只用 E / J；Z 与另一批股票留给登记之后的确认）。2026-09-28。

用户（2026-09-28）：「每股交易的时候要考虑仓位大小，哪个预测涨幅会大就多分配 进行个股仓位分配研究 综合之前所有的研究来进行这个研究」。
来由：上一轮（var/out/bsh_explore.md）卖法能把每笔变好，但个股仓位小、账户几乎不动；以前「挑 / 不挑」的研究都是 0 或 1，
  这一轮不去掉任何信号，只按信号日就知道的「预测涨幅」给每笔不同的仓位（0.64〜1.36 倍 = 权益的 16〜34%，上限不超过现行的 34%）。
规则（运行前写定；结果出来不改）：
一 变体：scripts/size_common.VARIANTS —— P0 全部加码（对照）、P1 K2 加码、P2 / P3 三指标综合分（三档 / 连续）、
   P4 预测涨幅模型（三指标的 walk-forward 岭回归）、P6 等风险（按 ATR%）、P7 P2 × P6。指标与来源见 size_common.py 开头。
   综合分的历史分位：E 用 2005-09 起的全部信号（今天的日経225、现行 + W2）；J 另加 E 年代的信号作历史（比例量纲一致）；
   模型：训练集 = var/cache/leap2_s6_features.pkl 里日経225 的单独交易（2006-10 起、现行卖法去掉 W2、扣成本），
   只用信号日早于「上个月末 − 90 天」的（已经结束），每月重训；训练不到 300 笔 → 权重 1。
二 窗口与组合：E = 2006-10〜2016-09（yfinance）、J = 2017-01〜2026-09（J-Quants，真实一手）；半段 E1 / E2、J1 / J2；
   S0C2 + W2，scripts/leap_confirm.py 同一框架；研究用引擎 SizeEngine（权重全为 1 时必须与现行一模一样，运行时核对）。
三 对照：P1〜P7 各自把窗口里信号的权重随机打乱 30 次（分布不变）→ 组合 Calmar 的 95% 分位。
四 入选规则（E、J 两个年代都满足）：
   a 组合 Calmar ≥ 现行 + 0.03；b Calmar ≥ P0（全部加码）—— 不是只因为个股仓位变大；c 最大回撤不比现行深 2 pp 以上；
   d Calmar > 打乱权重的 95% 分位（挑得准，不是运气）；e 4 个半段里 Calmar 低于现行的最多 1 个。
   排序：min(E, J 的 Calmar 差) 从大到小，最多 3 个；P0 是对照，不入选。没有入选 → 这一轮不登记、不用 Z 与另一批股票。
五 另报（只描述）：资金加权的每笔收益（Σ 损益 ÷ Σ 买入金额）、平均买入金额、各档信号占比；现行交易的「分数 × 每笔净收益」秩相关。
输出：var/out/size_explore.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import size_common as SZ                                                    # noqa: E402
from qbreak import paths                                                    # noqa: E402

CAL_UP, DD_TOL, MAX_FINAL, N_SHUF = 0.03, 2.0, 3, 30
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 入选规则（有测试）─────────────────────────
def qualifies(c: dict, b: dict, p0: dict, q95: dict | None) -> list[str]:
    """c / b / p0：{年代: {calmar, dd, halves}}（候选 / 现行 / 全部加码）；q95：{年代: 打乱权重 Calmar 的 95% 分位}。"""
    f = []
    lows = 0
    for era in ("E", "J"):
        x, y, z = c.get(era) or {}, b.get(era) or {}, p0.get(era) or {}
        ok = lambda a, k: a.get(k) is not None and np.isfinite(a.get(k))                  # noqa: E731
        if not (ok(x, "calmar") and ok(y, "calmar") and x["calmar"] >= y["calmar"] + CAL_UP):
            f.append(f"{era} Calmar 没高 {CAL_UP}")
        if not (ok(x, "calmar") and ok(z, "calmar") and x["calmar"] >= z["calmar"]):
            f.append(f"{era} 不比全部加码好")
        if not (ok(x, "dd") and ok(y, "dd") and x["dd"] >= y["dd"] - DD_TOL):
            f.append(f"{era} 回撤深 {DD_TOL:.0f} pp 以上")
        q = (q95 or {}).get(era)
        if not (q is not None and ok(x, "calmar") and x["calmar"] > q):
            f.append(f"{era} 没超过打乱权重的 95% 分位")
        for hx, hy in zip(x.get("halves") or [None, None], y.get("halves") or [None, None]):
            if not (hx is not None and hy is not None and hx >= hy):
                lows += 1
    if lows > 1:
        f.append(f"半段低于现行 {lows} 个")
    return f


def pick(res: dict, base: dict, p0: dict, q95: dict) -> list[str]:
    ok = [k for k in res if k != "P0" and not qualifies(res[k], base, p0, q95.get(k))]
    return sorted(ok, key=lambda k: (-min(res[k][e]["calmar"] - base[e]["calmar"] for e in ("E", "J")), k))[:MAX_FINAL]


# ───────────────────────── 信号表 ─────────────────────────
def signal_table(ctx: dict, fw: dict, B: dict) -> pd.DataFrame:
    """每个现行信号（含 W2）一行：票、信号日、量比、周线量比、对日経 β、ATR%。"""
    from leap2_s6b_portfolio import daily_from_weekly
    from leap_r11_explore import vr1
    from qbreak import mtf
    P, days, col = ctx["P"], ctx["days"], {t: j for j, t in enumerate(ctx["names"])}
    rows = []
    for t, df in fw.items():
        e = df["entry"].to_numpy(bool)
        if not e.any():
            continue
        j = col[t]
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        raw = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                            "Volume": P["V"][ok, j]}, index=days[ok])
        w5v = mtf.daily_frame(raw, days)["W5v"].reindex(df.index).to_numpy(float)
        vr = vr1(df)
        beta = daily_from_weekly(B["b_n225"], t, df.index)
        atrp = (df["atr"] / df["Close"]).to_numpy(float) * 100
        for i in np.flatnonzero(e):
            rows.append({"ticker": t, "date": df.index[i], "vr": vr[i], "w5v": w5v[i], "beta": beta[i], "atr_pct": atrp[i]})
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


def add_scores(S: pd.DataFrame, hist: pd.DataFrame | None, train: pd.DataFrame) -> pd.DataFrame:
    """hist：更早年代的信号（只当历史，算分位 / 中位数用）。"""
    H = pd.concat([hist, S], ignore_index=True) if hist is not None and len(hist) else S.copy()
    n0 = len(H) - len(S)
    d = H["date"].to_numpy()
    out = S.copy()
    out["pv"] = SZ.expanding_pct(d, H["vr"].to_numpy(float))[n0:]
    out["pw"] = SZ.expanding_pct(d, H["w5v"].to_numpy(float))[n0:]
    out["pb"] = SZ.expanding_pct(d, H["beta"].to_numpy(float))[n0:]
    out["med_atr"] = SZ.expanding_median(d, H["atr_pct"].to_numpy(float))[n0:]
    sig = pd.DataFrame({"date": out["date"], "lvr": np.log(out["vr"].clip(lower=1e-6)), "lw5v": np.log(out["w5v"].clip(lower=1e-6)),
                        "beta": out["beta"]})
    out["mscore"] = SZ.model_scores(train, sig)
    return out


def load_train() -> pd.DataFrame:
    f = pd.read_pickle(paths.sub("cache") / "leap2_s6_features.pkl")
    f = f[f["seg"] == "N225"].copy()
    return pd.DataFrame({"sig_date": pd.to_datetime(f["sig_date"]), "net": f["net"].astype(float),
                         "lvr": np.log(f["vr1"].astype(float).clip(lower=1e-6)), "lw5v": np.log(f["w5v"].astype(float).clip(lower=1e-6)),
                         "beta": f["b_n225"].astype(float)})


def wdict(S: pd.DataFrame, w: np.ndarray) -> dict:
    return {(t, pd.Timestamp(d)): float(x) for t, d, x in zip(S["ticker"], S["date"], w)}


def summ(r: dict, era: str) -> dict:
    w = r[era]
    return {"calmar": w.get("calmar"), "cagr": w.get("cagr"), "dd": w.get("dd"), "n": w.get("n"), "mean": w.get("mean"), "win": w.get("win"),
            "halves": [(r.get(f"{era}1") or {}).get("calmar"), (r.get(f"{era}2") or {}).get("calmar")]}


def main() -> int:
    import leap_confirm as LF
    from leap2_s6b_portfolio import weekly_betas
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    B = weekly_betas(list(universe("JP", "broad")))
    train = load_train()
    say(f"# 个股仓位分配（预测涨幅大的多分配）：探索（只用 E / J；{pd.Timestamp.today().date()}）")
    say(f"规则见 scripts/size_explore.py 开头（运行前写定）；变体 scripts/size_common.py。模型训练集：日経225 的单独交易 {len(train)} 笔。")
    res: dict = {}
    base, cw, q95, shuf, tiers, corr = {}, {}, {}, {}, {}, {}
    hist = None
    for era in ("E", "J"):
        t1 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        S = add_scores(signal_table(ctx, fw, B), hist, train)
        a, b = ctx["windows"][era]
        in_win = ((S["date"] >= pd.Timestamp(a)) & ((S["date"] <= pd.Timestamp(b)) if b else True)).to_numpy()
        r0, tr0 = SZ.run_weighted(ctx, run_fn, fw, p, None)
        base[era] = summ(r0, era)
        cw.setdefault("现行", {})[era] = SZ.cap_weighted(tr0)
        rn, trn = SZ.run_weighted(ctx, run_fn, fw, p, wdict(S, np.ones(len(S))))
        same = summ(rn, era) == base[era] and len(trn) == len(tr0) and np.allclose(trn["pnl"].to_numpy(float), tr0["pnl"].to_numpy(float))
        say(f"- {era} 引擎核对（权重全为 1）：{'与现行完全相同' if same else '★ 不同 —— 停止'}；窗口里的信号 {int(in_win.sum())} 个")
        if not same:
            raise SystemExit(f"{era} 引擎核对不一致")
        for k, v in SZ.VARIANTS.items():
            w = SZ.weights_for(v["kind"], S)
            r, tr = SZ.run_weighted(ctx, run_fn, fw, p, wdict(S, w))
            res.setdefault(k, {})[era] = summ(r, era)
            cw.setdefault(k, {})[era] = SZ.cap_weighted(tr)
            ww = w[in_win]
            tiers.setdefault(k, {})[era] = {"lo": float((ww < 0.999).mean() * 100), "hi": float((ww > 1.001).mean() * 100),
                                            "mean": float(ww.mean()) if len(ww) else None}
            if k in SZ.SHUFFLE_FOR:
                vals = []
                for s in range(N_SHUF):
                    rs, _ = SZ.run_weighted(ctx, run_fn, fw, p, wdict(S, SZ.shuffle_weights(w, in_win, 100 + s)))
                    vals.append(rs[era].get("calmar"))
                v2 = np.array([x for x in vals if x is not None], float)
                q95.setdefault(k, {})[era] = float(np.percentile(v2, 95)) if len(v2) else None
                shuf.setdefault(k, {})[era] = {"mean": float(v2.mean()) if len(v2) else None, "better": int((v2 >= res[k][era]["calmar"]).sum())}
        # 现行交易：分数 × 每笔净收益（只描述）
        if len(tr0):
            key = {(t, d): i for i, (t, d) in enumerate(zip(S["ticker"], S["date"]))}
            comp = SZ.composite(S["pv"].to_numpy(float), S["pw"].to_numpy(float), S["pb"].to_numpy(float))
            sc = {"综合分": comp, "模型分": S["mscore"].to_numpy(float)}
            days = ctx["days"]
            for nm, arr in sc.items():
                xs, ys = [], []
                for r_ in tr0.itertuples():
                    k_ = int(days.searchsorted(pd.Timestamp(r_.entry_date))) - 1
                    i = key.get((r_.ticker, days[k_])) if k_ >= 0 else None
                    if i is not None and np.isfinite(arr[i]):
                        xs.append(arr[i])
                        ys.append(r_.net)
                rho = float(pd.Series(xs).rank().corr(pd.Series(ys).rank())) if len(xs) >= 10 else None
                corr.setdefault(nm, {})[era] = {"rho": rho, "n": len(xs)}
        hist = S[["date", "vr", "w5v", "beta", "atr_pct"]].copy() if era == "E" else hist
        say(f"- {era}：{round(time.time() - t1)} s")
    say("\n## 一、全部变体（Calmar 差 = 变体 − 现行；打乱 = 打乱权重 30 次的 95% 分位）")
    say("| 变体 | Calmar E / J | 差 E / J | 打乱 95% E / J | 最大回撤 E / J | 年化 E / J | 半段 E1 · E2 · J1 · J2 | 资金加权每笔 E / J | 加码 / 减码的信号 |")
    say("|---|---|---|---|---|---|---|---|---|")

    def row(k, s, c, qq=None, tt=None):
        d = (lambda e: f"{s[e]['calmar'] - base[e]['calmar']:+.3f}") if k != "现行" else (lambda e: "—")
        q = (lambda e: f"{qq[e]:.3f}" if qq and qq.get(e) is not None else "—")                      # noqa: E731
        t_ = (lambda e: f"{tt[e]['hi']:.0f}% / {tt[e]['lo']:.0f}%" if tt else "—")                     # noqa: E731
        return (f"| {k} | {s['E']['calmar']} / {s['J']['calmar']} | {d('E')} / {d('J')} | {q('E')} / {q('J')} | {s['E']['dd']}% / {s['J']['dd']}% | "
                f"{s['E']['cagr']}% / {s['J']['cagr']}% | {s['E']['halves'][0]} · {s['E']['halves'][1]} · {s['J']['halves'][0]} · {s['J']['halves'][1]} | "
                f"{c['E'].get('cw_ret', 0):+.2f}% / {c['J'].get('cw_ret', 0):+.2f}% | {t_('E')} · {t_('J')} |")
    say(row("现行", base, cw["现行"]))
    for k in SZ.VARIANTS:
        say(row(k, res[k], cw[k], q95.get(k), tiers[k]))
    say("\n变体说明：" + "；".join(f"{k} {v['zh']}" for k, v in SZ.VARIANTS.items()))
    say("\n## 二、入选规则（运行前写定）")
    rows = {k: qualifies(res[k], base, res["P0"], q95.get(k)) for k in SZ.VARIANTS if k != "P0"}
    for k, f in rows.items():
        say(f"- {k}：{'入选' if not f else '不入选：' + '；'.join(f)}")
    fin = pick(res, base, res["P0"], q95)
    say(f"\n**入选（按规则，最多 3 个）：{('、'.join(fin)) if fin else '没有'}**" + ("" if fin else " → 这一轮不登记，Z 与另一批股票留着。"))
    say("\n## 三、另报（只描述）")
    for nm, v in corr.items():
        say(f"- 现行交易的{nm} × 每笔净收益 秩相关：" + "、".join(
            f"{e} {x['rho']:+.3f}（{x['n']} 笔）" if x["rho"] is not None else f"{e} —" for e, x in v.items()))
    for k in SZ.SHUFFLE_FOR:
        s = shuf.get(k) or {}
        say(f"- {k} 打乱权重 30 次：平均 Calmar " + "、".join(
            f"{e} {x['mean']:.3f}（≥ 候选的 {x['better']} 次）" for e, x in s.items() if x.get("mean") is not None))
    out = {"base": base, "variants": res, "cap_weighted": cw, "q95": q95, "shuffle": shuf, "tiers": tiers, "corr": corr, "qualify": rows,
           "finalists": fin, "train_n": int(len(train)), "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {out['elapsed_s']} s）。探索，只描述；非投资建议。")
    fp = paths.out_dir() / "size_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
