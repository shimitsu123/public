"""threat_index_v3_study.py — 威胁指数 v3：再加 贵金属 / 铜 / 天然气 / 粮食 / 商品综合 / 银行信贷（破产的代理）/ 地缘风险，
并试「按类别平衡」的合成，能否更准（事先写定，先提交后运行，结果出来不改规则）。

用户问（2026-09-25 晚）：继续优化威胁程度算法，横展开因子：破产数量、黄金、白银、矿产、各类燃气原材料价格、地缘风险。
新因素（qbreak/threat.py V3_EXTRA / JP_V3_ONLY；方向统一为越高越危险；只用当时已公布的数据，时滞见 raw_features_v3）：
  黄金 60 日涨幅（避险）、金银比 60 日变化、铜 60 日跌幅、天然气 60 日涨幅、粮食（小麦 / 玉米 / 大豆）60 日平均涨幅、
  商品综合 S&P GSCI 60 日涨幅、GSCI 20 日波动、银行收紧企业贷款（SLOOS 净收紧比例）、企业贷款拖欠率 / 核销率 4 季变化、
  地缘政治风险 GPR 30 日均值、GPR 30 日 / 1 年均值（急升）、政策不确定性 EPU 30 日均值；
  日経另加：短观 银行贷款态度 / 企业资金周转 DI 4 季恶化、日本 LNG 价格 12 个月涨幅（IMF 月度）、涉日地缘风险（GPR 国别，3 个月均值）。
  破产件数：没有可免费下载的长期序列（FRED 无；東京商工リサーチ / 帝国データバンク只公开年表或近月报告）→ 用上面的银行信贷指标代替。
  GPR（Caldara & Iacoviello，CC BY）用的是现行版本，最近几周为初值会修订（轻微前视，披露）。
合成方式（与 v1 A0、v2 最佳 A2 对照）：
  B1 全部 v3 因素等权    B2 训练期（1995–2010）单因素 AUC ≥ 0.55 的 v3 因素等权
  B3 类别平衡（threat.CATEGORY 8 类：先类内平均、再类间等权）    B4 类别平衡，只用 B2 选入的因素
目标与评估同 v2：之后 60 个交易日内最低收盘比当天跌 ≥10%（另报 ≥15%）；前半 1995–2010 / 后半 2011–。
判定（事先规则，这次分市场判定）：每个市场，B1～B4 中后半 AUC（≥10%）最高者为挑战者；若
  (a) 后半 AUC ≥ A0 + 0.03，且 (b) ≥15% 下跌的后半 AUC 不低于 A0，且 (c) 挑战者为 B1 / B3（不训练）时前半 AUC ≥ A0 − 0.02
  → 该市场日报的威胁指数换成挑战者；否则保留 A0。
  披露：分市场判定是在已知 v2 结果（美股 A2 后半比 A0 高 0.064、日経反而低）之后定的，美股若替换不算独立的样本外证据；
  所以从下一次日报起每天把 A0 与 B1～B4 的读数记到 var/out/threat_forward.csv，季度复核时做真正的样本外比较。
  替换后的交易用法：同 threat_index_study（O1 美股 → 1655 清仓、O2 日本 → 个股新仓 ×0.5、O3 两者；阈值为该指数自身历史
  90 / 80 分位；对应市场后半 AUC ≥ 0.65 且 S0C2 20 年 Calmar ≥ 现行 + 0.03、年化 ≥ 现行 − 0.5pp、回撤不深于现行）。
  与判定无关、一律执行：日报威胁卡片显示新因素的当前百分位（观察用）。
另报：每个新因素单独的 AUC、每个类别单独的 AUC、历次 ≥10% 下跌前 60 日内是否到过该指数自身 90 分位。
输出 var/out/threat_index_v3_study.md / .json；替换的市场写进 var/threat_index.json（method / cols，日报用）。
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
from qbreak import threat as TH                                              # noqa: E402
from qbreak.bullbear import date_phases                                      # noqa: E402
from threat_index_study import ON, episodes, evaluate, hysteresis, run_s0c2, s0c2_setup   # noqa: E402

EVAL0, SPLIT = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01")
LAB = {"A0": "A0 现行 v1", "V2A2": "v2 最佳（A2）", "B1": "B1 全部等权", "B2": "B2 训练期选因素",
       "B3": "B3 类别平衡", "B4": "B4 类别平衡（只用选入因素）"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def fmt(v):
    return "—" if v is None else f"{v:.3f}"


def auc_split(s: pd.Series, ev: pd.Series) -> dict:
    m = (s.index >= EVAL0) & s.notna() & ev.notna()
    a, e = s[m], ev[m]
    return {"all": TH.auc(a, e), "h1": TH.auc(a[a.index < SPLIT], e[a.index < SPLIT]),
            "h2": TH.auc(a[a.index >= SPLIT], e[a.index >= SPLIT])}


def eq(p: pd.DataFrame) -> pd.Series:
    if p.shape[1] == 0:
        return pd.Series(np.nan, index=p.index)
    return (p.mean(axis=1) * 100).where(p.notna().sum(axis=1) >= max(1, p.shape[1] // 2))


def main() -> int:
    t0 = time.time()
    d = TH.load_inputs()
    x = TH.load_extra_all()
    F = TH.build_all(d, x)
    say(f"# 威胁指数 v3：贵金属 / 铜 / 天然气 / 粮食 / 商品综合 / 银行信贷 / 地缘风险 + 类别平衡（{pd.Timestamp.today().date()}；"
        f"数据截至 S&P500 {d['spx'].index[-1].date()} / 日経 {d['n225'].index[-1].date()}；{time.time() - t0:.0f}s）")
    out, idx_all, pick = {}, {}, {}
    for m in ("US", "JP"):
        raw, close = F[m]
        v1 = TH.US_COLS if m == "US" else TH.JP_COLS
        v2 = TH.US_V2 if m == "US" else TH.JP_V2
        v3 = TH.US_V3 if m == "US" else TH.JP_V3
        new = [c for c in v3 if c not in v2]
        pct = pd.DataFrame({c: TH.expanding_pct(raw[c]) for c in v3})
        fdd = TH.forward_drawdown(close, 60)
        ev10 = (fdd <= -0.10).astype(float).where(fdd.notna())
        ev15 = (fdd <= -0.15).astype(float).where(fdd.notna())
        single = {c: auc_split(pct[c], ev10) for c in v3}
        sel2 = [c for c in v2 if (single[c]["h1"] or 0) >= 0.55]
        sel3 = [c for c in v3 if (single[c]["h1"] or 0) >= 0.55]
        cand = {"A0": eq(pct[v1]), "V2A2": eq(pct[sel2]), "B1": eq(pct[v3]), "B2": eq(pct[sel3]),
                "B3": TH.category_mean(pct[v3]), "B4": TH.category_mean(pct[sel3]) if sel3 else pd.Series(np.nan, index=pct.index)}
        idx_all[m] = cand
        res = {k: {"ev10": auc_split(v, ev10), "ev15": auc_split(v, ev15)} for k, v in cand.items()}
        tp, _ = date_phases(close.dropna(), 0.10, 0.10)
        peaks = [p for p in tp[tp["kind"] == "peak"]["date"] if p >= EVAL0]
        for k, v in cand.items():
            q90 = TH.expanding_pct(v, min_n=750) >= 0.9
            res[k]["warn_hits"] = [sum(bool(q90.loc[:p].tail(61).any()) for p in peaks), len(peaks)]
        cats = {c: [k for k in ks if k in v3] for c, ks in TH.CATEGORY.items()}
        cat_auc = {c: auc_split(eq(pct[ks]), ev10) for c, ks in cats.items() if ks}
        out[m] = {"single_new": {c: single[c] for c in new}, "selected_v2": sel2, "selected_v3": sel3, "cands": res,
                  "category_auc": cat_auc}
        name = "S&P500" if m == "US" else "日経225"
        say(f"\n## {name}：新因素单独的 AUC（之后 60 日跌 ≥10%；前半 1995–2010 / 后半 2011–）")
        say("| 新因素 | 前半 | 后半 | B2 选入 |")
        say("|---|---|---|---|")
        for c in sorted(new, key=lambda c: -(single[c]["h2"] or 0)):
            say(f"| {TH.LABELS[c]} | {fmt(single[c]['h1'])} | {fmt(single[c]['h2'])} | {'是' if c in sel3 else ''} |")
        say(f"\n类别单独的 AUC（前半 / 后半）：" + "；".join(f"{c} {fmt(a['h1'])} / {fmt(a['h2'])}" for c, a in cat_auc.items()))
        say("\n| 合成方式 | 跌≥10% AUC 前半 / 后半 | 跌≥15% AUC 前半 / 后半 | 下跌前 60 日内到过自身 90 分位 |")
        say("|---|---|---|---|")
        for k, r in res.items():
            say(f"| {LAB[k]} | {fmt(r['ev10']['h1'])} / {fmt(r['ev10']['h2'])} | {fmt(r['ev15']['h1'])} / {fmt(r['ev15']['h2'])} | "
                f"{r['warn_hits'][0]} / {r['warn_hits'][1]} |")
        # ── 判定（分市场）──
        ch = max(("B1", "B2", "B3", "B4"), key=lambda k: res[k]["ev10"]["h2"] or 0)
        a0, c = res["A0"], res[ch]
        ok_a = (c["ev10"]["h2"] or 0) >= (a0["ev10"]["h2"] or 0) + 0.03
        ok_b = (c["ev15"]["h2"] or 0) >= (a0["ev15"]["h2"] or 0)
        ok_c = ch in ("B2", "B4") or (c["ev10"]["h1"] or 0) >= (a0["ev10"]["h1"] or 0) - 0.02
        pick[m] = ch if (ok_a and ok_b and ok_c) else "A0"
        out[m].update({"challenger": ch, "checks": {"a": ok_a, "b": ok_b, "c": ok_c}, "pick": pick[m]})
        say(f"\n判定（事先规则）：挑战者 {LAB[ch]}（后半 {fmt(c['ev10']['h2'])}，A0 {fmt(a0['ev10']['h2'])}）；"
            f"(a) 高 ≥0.03 {'满足' if ok_a else '不满足'}，(b) ≥15% 不低于 A0 {'满足' if ok_b else '不满足'}，"
            f"(c) 前半不差于 A0−0.02 {'满足' if ok_c else '不满足'} → "
            f"{'日报威胁指数换成 ' + LAB[ch] if pick[m] != 'A0' else '保留 A0'}")

    # ── 替换后的交易用法 ──
    if any(v != "A0" for v in pick.values()):
        S = s0c2_setup()
        base = run_s0c2(S, S["bear"]["US"], S["em_jp"])
        port, ok = {"now": base}, []
        g = S["grid"]
        o1 = em2 = None
        if pick["US"] != "A0":
            pu = TH.expanding_pct(idx_all["US"][pick["US"]], 750) * 100
            stress = hysteresis(pu, 90, 80).reindex(S["bear"]["US"].index).fillna(False).astype(bool)
            o1 = (S["bear"]["US"] | stress).astype(bool)
            port["O1"] = run_s0c2(S, o1, S["em_jp"])
        if pick["JP"] != "A0":
            pj = TH.expanding_pct(idx_all["JP"][pick["JP"]], 750) * 100
            hot = (pj.reindex(g.union(pj.index)).ffill().reindex(g) >= 90).shift(1).fillna(False)
            em2 = S["em_jp"].mul(np.where(hot.to_numpy(bool), 0.5, 1.0), axis=0)
            port["O2"] = run_s0c2(S, S["bear"]["US"], em2)
        if o1 is not None and em2 is not None:
            port["O3"] = run_s0c2(S, o1, em2)
        need = {"O1": ["US"], "O2": ["JP"], "O3": ["US", "JP"]}
        say("\n## 替换后的交易用法（S0C2 组合 20 年）")
        for k in [k for k in ("O1", "O2", "O3") if k in port]:
            a_ok = all((out[mm]["cands"][pick[mm]]["ev10"]["h2"] or 0) >= 0.65 for mm in need[k])
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
            if pick[m] == "A0":
                continue
            _, close = F[m]
            v = idx_all[m][pick[m]]
            e = evaluate(v, close)
            eps = episodes(v, close)
            cols = TH.US_V3 if m == "US" else TH.JP_V3
            table[m] = {"method": pick[m], "cols": out[m]["selected_v3"] if pick[m] in ("B2", "B4") else cols,
                        "auc_h1": e["auc_h1"], "auc_h2": e["auc_h2"], "base_rate": e["base_rate"], "deciles": e["deciles"],
                        "episodes_hit80": [sum(x["hit80_before"] for x in eps), len(eps)], "on": ON}
        table["generated_v3"] = str(pd.Timestamp.today().date())
        tf.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    out["pick"] = pick
    say(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "threat_index_v3_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
