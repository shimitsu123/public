"""threat_factor_survey.py — 威胁指数因子调查：各经济领域的因素，逐个「放进现行模型」看对日経 / 美股有没有帮助
（事先写定，先提交后运行，结果出来不改规则）。

用户要求（2026-09-25）：做威胁指数因子的调查，因子覆盖和经济有关的各个领域，每一个都要带到当前模型结合来看是否对日経 / 美股有影响。
因素：现行 v1（美股 8 / 日経 10 个）+ v2 / v3 已研究的（美股 27 / 日経 33 个）+ qbreak/survey.py 新增约 65 个，
  共 22 个领域：货币政策 / 流动性、利率 / 曲线、财政、信用 / 破产代理、通胀、增长 / 景气、就业、消费、住房、贸易 / 外需、
  地缘 / 不确定性、全球 / 中国、汇率、商品、运输 / 物流、科技周期、银行、市场内部、市场波动、市场趋势、估值、企业盈利。
  每个因素换成扩张窗口百分位（同 v1）；方向统一为越高越危险；只用当时已公布的数据（时滞见 survey.py）。
事件：之后 60 个交易日内最低收盘比当天跌 ≥10%（另报 ≥15%）；前半 1995–2010 / 后半 2011–。
检验（每个市场分别）：
  ① 不在现行模型里的因素 f：现行模型 A0 的因素再加 f 等权平均（f 算一个因素）→ 与 A0 的 AUC 差 ΔAUC（前半 / 后半；另报 ≥15% 的后半），
     只在两者都有值的日子比较；并报 f 单独的 AUC。分类：两段都提升（两段 ΔAUC 都 ≥ +0.005）/ 只前半 / 只后半 / 都没有。
  ② 已在现行模型里的因素：拿掉它之后 AUC 变多少（留一法），看它在现行模型里有没有用。
  ③ 领域：同一领域里不在 A0 的因素先平均成一个领域分，作为一个因素加进 A0 → ΔAUC（前半 / 后半）；另报领域分单独的 AUC。
  ④ 诚实的组合检验：只用前半（1995–2010）挑因素 —— ① 的前半 ΔAUC ≥ +0.005、数据源没停更、2008 年以前就有百分位（前半至少 3 年）
     → A0 + 选入因素等权平均（记作 S），看后半 AUC。
判定（事先规则，分市场）：S 的后半 AUC ≥ A0 + 0.03 且 ≥15% 下跌的后半 AUC 不低于 A0 → 该市场日报的威胁指数换成 S，否则保留 A0。
  替换后的交易用法同 threat_index_study（O1 美股 → 1655 清仓、O2 日本 → 个股新仓 ×0.5；阈值为自身历史 90 / 80 分位；
  对应市场后半 AUC ≥ 0.65 且 S0C2 20 年 Calmar ≥ 现行 + 0.03、年化 ≥ 现行 − 0.5pp、回撤不深于现行）。
  不论判定如何：S 的读数从下一次日报起每天记进 var/out/threat_forward.csv（列 S），做真正的样本外比较；
  日报威胁卡片加「各领域当前读数」（领域分的当前百分位，只作观察）。
披露：v2 / v3 的因素之前已看过后半单独 AUC；④ 的选择只用前半，但因素清单是在那之后设计的，仍有轻微的信息泄漏。
  停更的数据源（Shiller CAPE、OECD 先行指数与消费者信心等）只在 ①～③ 里作历史参考，不进 ④。
输出 var/out/threat_factor_survey.md / .json；替换的市场写进 var/threat_index.json（method = "S"、cols）。
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
from qbreak import paths                                                     # noqa: E402
from qbreak import survey as SV                                              # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from threat_index_study import ON, episodes, evaluate, hysteresis, run_s0c2, s0c2_setup   # noqa: E402

EVAL0, SPLIT, H1_COVER = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01"), pd.Timestamp("2008-01-01")
EPS = 0.005
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def f3(v) -> str:
    return "—" if v is None or v != v else f"{v:.3f}"


def fd(v) -> str:
    return "—" if v is None or v != v else f"{v:+.3f}"


def eqw(p: pd.DataFrame) -> pd.Series:
    if p.shape[1] == 0:
        return pd.Series(np.nan, index=p.index)
    return (p.mean(axis=1) * 100).where(p.notna().sum(axis=1) >= max(1, p.shape[1] // 2))


def halves_auc(s: pd.Series, ev: pd.Series, mask: pd.Series) -> tuple:
    m = mask & s.notna() & ev.notna() & (s.index >= EVAL0)
    a, e = s[m], ev[m]
    return TH.auc(a[a.index < SPLIT], e[a.index < SPLIT]), TH.auc(a[a.index >= SPLIT], e[a.index >= SPLIT])


def delta(new: pd.Series, base: pd.Series, ev: pd.Series) -> tuple:
    """同一批日子上 new 与 base 的 AUC 差（前半, 后半）。"""
    m = new.notna() & base.notna()
    n1, n2 = halves_auc(new, ev, m)
    b1, b2 = halves_auc(base, ev, m)
    d = lambda x, y: None if x is None or y is None else x - y                  # noqa: E731
    return d(n1, b1), d(n2, b2)


def klass(d1, d2) -> str:
    p1, p2 = (d1 or 0) >= EPS, (d2 or 0) >= EPS
    return "两段都提升" if p1 and p2 else ("只前半" if p1 else ("只后半" if p2 else "都没有"))


def main() -> int:
    t0 = time.time()
    today = pd.Timestamp.today().normalize()
    d = TH.load_inputs()
    x = TH.load_extra_all()
    F = TH.build_all(d, x)
    raw_sv = SV.load_raw()
    stale = SV.stale(raw_sv, today)
    say(f"# 威胁指数因子调查：22 个经济领域，逐个放进现行模型（{today.date()}；数据截至 S&P500 {d['spx'].index[-1].date()} / "
        f"日経 {d['n225'].index[-1].date()}；{time.time() - t0:.0f}s）")
    say("停更的数据源（只作历史参考）：" + ("、".join(f"{SV.LABELS.get(k, k)}（最后 {v}）" for k, v in stale.items()) or "无"))
    dom = {**SV.EXISTING_DOMAIN, **SV.DOMAIN}
    lab = {**TH.LABELS, **SV.LABELS}
    out, idx_all, pick = {"stale": stale}, {}, {}
    for m in ("US", "JP"):
        raw_ex, close = F[m]
        days = raw_ex.index
        feats = pd.concat([raw_ex, SV.features(days, raw_sv, jp_market=(m == "JP"))], axis=1)
        a0_cols = TH.US_COLS if m == "US" else TH.JP_COLS
        ex_cols = [c for c in (TH.US_V3 if m == "US" else TH.JP_V3) if c not in a0_cols]
        cand = ex_cols + [k for k in SV.KEYS if k in feats]
        pct = pd.DataFrame({c: TH.expanding_pct(feats[c]) for c in a0_cols + cand})
        fdd = TH.forward_drawdown(close, 60)
        ev10 = (fdd <= -0.10).astype(float).where(fdd.notna())
        ev15 = (fdd <= -0.15).astype(float).where(fdd.notna())
        a0 = eqw(pct[a0_cols])
        a0_auc = halves_auc(a0, ev10, a0.notna())
        rows = {}
        for f in cand:                                                        # ① 加进现行模型
            cf = eqw(pct[a0_cols + [f]])
            d1, d2 = delta(cf, a0, ev10)
            _, d15 = delta(cf, a0, ev15)
            s1, s2 = halves_auc(pct[f], ev10, pct[f].notna())
            first = pct[f].first_valid_index()
            rows[f] = {"domain": dom.get(f, "其他"), "label": lab.get(f, f), "single": [s1, s2], "delta": [d1, d2], "delta15_h2": d15,
                       "class": klass(d1, d2), "first": str(first.date()) if first is not None else None,
                       "stale": stale.get(f), "now": round(float(pct[f].dropna().iloc[-1]) * 100) if pct[f].notna().any() else None}
        loo = {}
        for f in a0_cols:                                                     # ② 现行模型里的因素：拿掉它
            rest = [c for c in a0_cols if c != f]
            dd1, dd2 = delta(a0, eqw(pct[rest]), ev10)
            s1, s2 = halves_auc(pct[f], ev10, pct[f].notna())
            loo[f] = {"domain": dom.get(f, "其他"), "label": lab.get(f, f), "single": [s1, s2], "contrib": [dd1, dd2],
                      "now": round(float(pct[f].dropna().iloc[-1]) * 100) if pct[f].notna().any() else None}
        doms = {}
        for dname in sorted({rows[f]["domain"] for f in rows}):                # ③ 领域
            fs = [f for f in rows if rows[f]["domain"] == dname]
            dscore = pct[fs].mean(axis=1)
            both = pd.concat([pct[a0_cols], dscore.rename("_dom")], axis=1)
            cd = eqw(both)
            d1, d2 = delta(cd, a0, ev10)
            s1, s2 = halves_auc(dscore, ev10, dscore.notna())
            doms[dname] = {"n": len(fs), "single": [s1, s2], "delta": [d1, d2], "class": klass(d1, d2),
                           "now": round(float(dscore.dropna().iloc[-1]) * 100) if dscore.notna().any() else None,
                           "factors": fs}
        sel = [f for f in cand if (rows[f]["delta"][0] or 0) >= EPS and not rows[f]["stale"]
               and rows[f]["first"] is not None and pd.Timestamp(rows[f]["first"]) < H1_COVER]
        s_idx = eqw(pct[a0_cols + sel]) if sel else a0
        s10, s15, a15 = halves_auc(s_idx, ev10, s_idx.notna()), halves_auc(s_idx, ev15, s_idx.notna()), halves_auc(a0, ev15, a0.notna())
        ok_a = (s10[1] or 0) >= (a0_auc[1] or 0) + 0.03
        ok_b = (s15[1] or 0) >= (a15[1] or 0)
        pick[m] = "S" if (sel and ok_a and ok_b) else "A0"
        idx_all[m] = {"A0": a0, "S": s_idx, "close": close}
        out[m] = {"a0_auc": a0_auc, "a0_auc15": a15, "factors": rows, "a0_members": loo, "domains": doms, "selected": sel,
                  "S_auc": s10, "S_auc15": s15, "checks": {"a": ok_a, "b": ok_b}, "pick": pick[m]}

    # ── 输出 ──
    for m, name in (("US", "S&P500"), ("JP", "日経225")):
        o = out[m]
        say(f"\n## {name}：现行模型 A0 的 AUC 前半 {f3(o['a0_auc'][0])} / 后半 {f3(o['a0_auc'][1])}")
        say("\n### ③ 各领域放进现行模型（领域内不在 A0 的因素先平均成一个分数）")
        say("| 领域 | 因素数 | 领域分单独 AUC 前 / 后 | 加进 A0 后 ΔAUC 前 / 后 | 分类 | 当前分位 |")
        say("|---|---|---|---|---|---|")
        for dn, v in sorted(o["domains"].items(), key=lambda kv: -((kv[1]["delta"][1] or -1) + (kv[1]["delta"][0] or -1))):
            say(f"| {dn} | {v['n']} | {f3(v['single'][0])} / {f3(v['single'][1])} | {fd(v['delta'][0])} / {fd(v['delta'][1])} | "
                f"{v['class']} | {v['now'] if v['now'] is not None else '—'} |")
        say("\n### ② 现行模型里的因素：拿掉它 AUC 会少多少（正数 = 它有用）")
        say("| 因素 | 领域 | 单独 AUC 前 / 后 | 贡献 前 / 后 | 当前分位 |")
        say("|---|---|---|---|---|")
        for f, v in o["a0_members"].items():
            say(f"| {v['label']} | {v['domain']} | {f3(v['single'][0])} / {f3(v['single'][1])} | {fd(v['contrib'][0])} / {fd(v['contrib'][1])} | "
                f"{v['now'] if v['now'] is not None else '—'} |")
        say("\n### ① 每个因素放进现行模型（按领域；★ = 两段都提升）")
        say("| 领域 | 因素 | 单独 AUC 前 / 后 | 加进 A0 ΔAUC 前 / 后 | ≥15% 后半 Δ | 当前分位 | 备注 |")
        say("|---|---|---|---|---|---|---|")
        for f, v in sorted(o["factors"].items(), key=lambda kv: (kv[1]["domain"], -((kv[1]["delta"][1] or -1)))):
            note = "；".join(x for x in [f"停更 {v['stale']}" if v["stale"] else "", f"{v['first'][:4]} 起" if v["first"] and v["first"] > "2000" else "",
                                        "选入 S" if f in o["selected"] else ""] if x)
            say(f"| {v['domain']} | {'★ ' if v['class'] == '两段都提升' else ''}{v['label']} | {f3(v['single'][0])} / {f3(v['single'][1])} | "
                f"{fd(v['delta'][0])} / {fd(v['delta'][1])} | {fd(v['delta15_h2'])} | {v['now'] if v['now'] is not None else '—'} | {note} |")
        n2 = sum(1 for v in o["factors"].values() if v["class"] == "两段都提升")
        say(f"\n两段都提升的因素 {n2} / {len(o['factors'])} 个。")
        say(f"\n### ④ 只用前半挑因素的组合 S（{len(o['selected'])} 个：" + "、".join(lab.get(f, f) for f in o["selected"]) + "）")
        say(f"S：前半 {f3(o['S_auc'][0])}（样本内）/ 后半 {f3(o['S_auc'][1])}；≥15% 后半 {f3(o['S_auc15'][1])}（A0 {f3(o['a0_auc15'][1])}）")
        say(f"判定（事先规则）：后半比 A0 高 ≥0.03 {'满足' if o['checks']['a'] else '不满足'}，≥15% 不低于 A0 {'满足' if o['checks']['b'] else '不满足'} → "
            f"{'日报的威胁指数换成 S' if o['pick'] == 'S' else '保留 A0'}")

    if any(v == "S" for v in pick.values()):
        S = s0c2_setup()
        base = run_s0c2(S, S["bear"]["US"], S["em_jp"])
        port, ok, g = {"now": base}, [], S["grid"]
        o1 = em2 = None
        if pick["US"] == "S":
            pu = TH.expanding_pct(idx_all["US"]["S"], 750) * 100
            o1 = (S["bear"]["US"] | hysteresis(pu, 90, 80).reindex(S["bear"]["US"].index).fillna(False).astype(bool)).astype(bool)
            port["O1"] = run_s0c2(S, o1, S["em_jp"])
        if pick["JP"] == "S":
            pj = TH.expanding_pct(idx_all["JP"]["S"], 750) * 100
            hot = (pj.reindex(g.union(pj.index)).ffill().reindex(g) >= 90).shift(1).fillna(False)
            em2 = S["em_jp"].mul(np.where(hot.to_numpy(bool), 0.5, 1.0), axis=0)
            port["O2"] = run_s0c2(S, S["bear"]["US"], em2)
        if o1 is not None and em2 is not None:
            port["O3"] = run_s0c2(S, o1, em2)
        need = {"O1": ["US"], "O2": ["JP"], "O3": ["US", "JP"]}
        say("\n## 替换后的交易用法（S0C2 组合 20 年）")
        for k in [k for k in ("O1", "O2", "O3") if k in port]:
            a_ok = all((out[mm]["S_auc"][1] or 0) >= 0.65 for mm in need[k])
            r = port[k]
            p_ok = ((r["w20_calmar"] or 0) >= (base["w20_calmar"] or 0) + 0.03 and r["w20_cagr"] >= base["w20_cagr"] - 0.5
                    and r["w20_dd"] >= base["w20_dd"])
            if a_ok and p_ok:
                ok.append(k)
            say(f"- {k}：20 年 {r['w20_cagr']}% / {r['w20_dd']:.2f}%（现行 {base['w20_cagr']}% / {base['w20_dd']:.2f}%）；"
                f"AUC 条件 {'满足' if a_ok else '不满足'}，组合条件 {'满足' if p_ok else '不满足'}")
        out["portfolio"] = port
        out["trade_pick"] = max(ok, key=lambda k: port[k]["w20_calmar"] or 0) if ok else None
        say(f"交易用法判定：{out['trade_pick'] or '不用于交易，只在日报展示'}")
        tf = paths.home() / "threat_index.json"
        table = json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else {}
        for m in ("US", "JP"):
            if pick[m] != "S":
                continue
            v, close = idx_all[m]["S"], idx_all[m]["close"]
            e, eps = evaluate(v, close), episodes(v, close)
            table[m] = {"method": "S", "cols": (TH.US_COLS if m == "US" else TH.JP_COLS) + out[m]["selected"],
                        "auc_h1": e["auc_h1"], "auc_h2": e["auc_h2"], "base_rate": e["base_rate"], "deciles": e["deciles"],
                        "episodes_hit80": [sum(z["hit80_before"] for z in eps), len(eps)], "on": ON}
        table["generated_survey"] = str(today.date())
        tf.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    out["pick"] = pick
    say(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "threat_factor_survey"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
