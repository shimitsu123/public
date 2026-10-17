"""combo_all_posthoc.py — 事后核对（只描述、不改判定）：「全部研究的关联搭配」（登记 7f2ca59、结果 729c4ee）里通过的 C「市场状态 × 个股特征」到底有多可靠。

C 按事先写定的五条全部通过，但证据集中在 J（2017〜2026 的日経225），别的股票 W / Jx 只是不变差 → 在决定前向记录还是改模拟盘之前，做这几项事后核对
（都是看过结果之后才想到的检查，写明「事后」，不改登记的判定）：
  1 复现：用同一套代码重建样本，C 的逐笔统计应与登记运行完全一致（不一致 → 停下）。
  2 学习安慰剂：每个学习年代把「每笔净收益」在信号之间随机打乱（特征不动 = 特征与结果的关系被打断），照同样的流程学 C、放到检验年代，200 次
    → 检验年代（与三年代合并）的每笔差 / 胜率差的分布；真实结果排在第几分位 = 「C 学到的东西」比「随便学到的规则」好多少。
  3 J 的两半：2017-01〜2021-12 / 2022-01〜2026-09 各自的保留 − 全部；J 每年。
  4 去掉一个特征：检验 J 那一折，起作用的格子里去掉每一个入选特征后 J 的每笔差 / 胜率差；只用一个特征时的每笔差。
  5 C 起作用的时间：每个年代「日経在 200 日线上且 VIX < 20」的信号比例；现在（最近一个交易日）是不是在这一格。
  6 前向记录要用的规则：用 Z + E + J 三个年代一起学的 C（只列出来，不评估 —— 它的样本外只能靠以后的新数据）。
样本表缓存到 var/cache/combo_all_panel.pkl（不入库）。输出 var/out/combo_all_posthoc.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import os
import pickle
import subprocess
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
import combo_all_common as CA                                                # noqa: E402
import combo_all_study as CS                                                 # noqa: E402
from qbreak import paths                                                     # noqa: E402

N_PERM = 200
CACHE = "combo_all_panel.pkl"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def build_panel() -> tuple[dict, dict, dict]:
    """登记运行同一套代码重建 D（有结果）/ A（全部信号）；另返回市场状态表的最后一行。"""
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    import sell_confirm as SCF
    fp = paths.sub("cache") / CACHE
    if fp.exists():
        with open(fp, "rb") as f:
            return pickle.load(f)
    p0 = SF.no_w2_params(load_params(market="JP"))
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    n225_today = set(universe("JP", "broad"))
    SM = CS.load_samples(p0, None)
    B = CS.feature_base(p0, None)
    D, A = {}, {}
    for s in CS.SAMPLES:
        a, b = CS.WIN[s]
        src = SM["J2"] if s == "Jx" else SM[s]
        S = CS.signals(src["fa"], src["keep"], src["mem"], a, b, exclude=n225_today if s == "Jx" else None)
        S = CS.add_features(S, src["fa"], B)
        A[s] = S
        D[s] = CS.outcomes(S, src["fa"], p0, bt, rt)
    mk = B["mk"]
    now = {"date": str(mk.index[-1].date()), "n225_ma200": float(mk["n225_ma200"].iloc[-1]), "vix": float(mk["vix"].iloc[-1])}
    out = (D, A, now)
    with open(fp, "wb") as f:
        pickle.dump(out, f)
    return out


def fold_c(D: dict, e: str, net_col: str = "net") -> tuple[dict, np.ndarray]:
    trains = [D[x].assign(net=D[x][net_col]) for x in CA.ERAS if x != e]
    rules = CA.fit_c(trains)
    return rules, CA.apply_c(rules, D[e])


def main() -> int:
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    say(f"# 事后核对：全部研究的关联搭配里通过的 C（{pd.Timestamp.today().date()}；代码 {code}；只描述，不改登记 7f2ca59 的判定）")
    D, A, now = build_panel()
    reg = json.loads((paths.out_dir() / "combo_all_study.json").read_text(encoding="utf-8"))

    # 1 复现
    say("\n## 一、复现（应与登记运行完全一致）")
    keep = {e: fold_c(D, e)[1] for e in CA.ERAS}
    keep["W"] = CA.apply_c(fold_c(D, "E")[0], D["W"])
    keep["Jx"] = CA.apply_c(fold_c(D, "J")[0], D["Jx"])
    same = True
    for s in CS.SAMPLES:
        x = CA.delta(D[s]["net"].to_numpy(float), keep[s])
        r = reg["stats"]["C"]["samples"][s]
        ok = x["n"] == r["n"] and x["kept"] == r["kept"] and abs(x["dmean"] - r["dmean"]) < 1e-3 and abs(x["dwin"] - r["dwin"]) < 1e-3
        same &= ok
        say(f"- {s}：{x['n']} 笔、保留 {x['kept']}；胜率差 {fmt(x['dwin'], '{:+.2f}')} pp、每笔差 {fmt(x['dmean'], '{:+.3f}')} pp → {'一致' if ok else '**不一致**'}")
    if not same:
        say("复现不一致 → 停止（不做后面的核对）")
        (paths.out_dir() / "combo_all_posthoc.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
        return 1

    # 2 学习安慰剂
    say(f"\n## 二、学习安慰剂（学习年代的结果在信号之间随机打乱，照同样流程学 C → 检验年代；{N_PERM} 次）")
    rng = np.random.default_rng(CA.SEED)
    real = {e: CA.delta(D[e]["net"].to_numpy(float), keep[e]) for e in CA.ERAS}
    pooled_net = np.concatenate([D[e]["net"].to_numpy(float) for e in CA.ERAS])
    real_pool = CA.delta(pooled_net, np.concatenate([keep[e] for e in CA.ERAS]))
    perm = {e: {"dmean": [], "dwin": []} for e in CA.ERAS}
    perm_pool = {"dmean": [], "dwin": []}
    for b in range(N_PERM):
        sh = {x: D[x].assign(net=rng.permutation(D[x]["net"].to_numpy(float))) for x in CA.ERAS}
        ks = []
        for e in CA.ERAS:
            rules = CA.fit_c([sh[x] for x in CA.ERAS if x != e])
            k = CA.apply_c(rules, D[e])
            ks.append(k)
            d = CA.delta(D[e]["net"].to_numpy(float), k)
            perm[e]["dmean"].append(d["dmean"])
            perm[e]["dwin"].append(d["dwin"])
        d = CA.delta(pooled_net, np.concatenate(ks))
        perm_pool["dmean"].append(d["dmean"])
        perm_pool["dwin"].append(d["dwin"])
    pct = lambda v, arr: float(np.mean(np.asarray(arr, float) < v) * 100)              # noqa: E731
    PL = {}
    for e in CA.ERAS + ("合并",):
        rv = real_pool if e == "合并" else real[e]
        pv = perm_pool if e == "合并" else perm[e]
        PL[e] = {"real_dmean": rv["dmean"], "real_dwin": rv["dwin"], "q95_dmean": float(np.nanpercentile(pv["dmean"], 95)),
                 "q95_dwin": float(np.nanpercentile(pv["dwin"], 95)), "pct_dmean": pct(rv["dmean"], pv["dmean"]), "pct_dwin": pct(rv["dwin"], pv["dwin"]),
                 "med_dmean": float(np.nanmedian(pv["dmean"]))}
        say(f"- {e}：真实 每笔差 {fmt(rv['dmean'])} pp（打乱后中位 {fmt(PL[e]['med_dmean'])}、95 分位 {fmt(PL[e]['q95_dmean'])}；排在 {PL[e]['pct_dmean']:.0f} 分位）；"
            f"胜率差 {fmt(rv['dwin'], '{:+.1f}')} pp（95 分位 {fmt(PL[e]['q95_dwin'], '{:+.1f}')}；{PL[e]['pct_dwin']:.0f} 分位）")

    # 3 J 的两半与每年
    say("\n## 三、J（2017〜2026）的两半与每年（检验 J 那一折的决定）")
    J = D["J"].assign(keep=keep["J"], y=pd.to_datetime(D["J"]["date"]).dt.year)
    halves = {"2017〜2021": J[J["y"] <= 2021], "2022〜2026": J[J["y"] >= 2022]}
    HV = {}
    for k, g in halves.items():
        x = CA.delta(g["net"].to_numpy(float), g["keep"].to_numpy(bool))
        HV[k] = x
        say(f"- {k}：{x['n']} 笔、保留 {x['kept']}；胜率 {fmt(x['win_all'], '{:.1f}')}% → {fmt(x['win'], '{:.1f}')}%（{fmt(x['dwin'], '{:+.1f}')} pp）；"
            f"每笔 {fmt(x['mean_all'])}% → {fmt(x['mean'])}%（{fmt(x['dmean'])} pp）")
    YR = {}
    rows = []
    for y, g in J.groupby("y"):
        x = CA.delta(g["net"].to_numpy(float), g["keep"].to_numpy(bool))
        rm = g[~g["keep"]]["net"].to_numpy(float)
        YR[int(y)] = {**x, "skipped_mean": float(rm.mean()) if len(rm) else None}
        rows.append(f"{y}：{x['n']} 笔跳过 {x['n'] - x['kept']}（被跳过的每笔 {fmt(float(rm.mean()) if len(rm) else None)}%、保留的 {fmt(x['mean'])}%）")
    say("- 每年：" + "；".join(rows))
    better = sum(1 for v in YR.values() if v["n"] > v["kept"] and v["skipped_mean"] is not None and v["skipped_mean"] < v["mean"])
    say(f"- 有跳过的年份里，被跳过的每笔比保留的差：{better} / {sum(1 for v in YR.values() if v['n'] > v['kept'])} 年")

    # 4 去掉一个特征 / 只用一个特征（检验 J 那一折、起作用的格子）
    say("\n## 四、检验 J 那一折：去掉一个特征 / 只用一个特征")
    rules_j, _ = fold_c(D, "J")
    act = {k: r for k, r in rules_j.items() if r is not None and r["sel"]}
    AB = {}
    for k, r in act.items():
        for f in list(r["sel"]):
            r2 = {**r, "sel": {g: s for g, s in r["sel"].items() if g != f}}
            trains = [D[x] for x in CA.ERAS if x != "J"]
            sub = [T[CA.cell_of(T) == k] for T in trains]
            pooled = pd.concat(sub, ignore_index=True)
            r2["thr"] = CA.threshold(CA.score(pooled, r2["sel"], r2["cut"]))
            r1 = {**r, "sel": {f: r["sel"][f]}}
            r1["thr"] = CA.threshold(CA.score(pooled, r1["sel"], r1["cut"]))
            res = {}
            for lab, rr in (("drop", r2), ("only", r1)):
                kk = CA.apply_c({**rules_j, k: rr}, D["J"])
                res[lab] = CA.delta(D["J"]["net"].to_numpy(float), kk)
            AB[f] = res
            fam, zh, _ = CA.FEATURES[f]
            say(f"- {f}{'+' if r['sel'][f] > 0 else '−'}（{zh}）：去掉后 J 每笔差 {fmt(res['drop']['dmean'])} pp / 胜率差 {fmt(res['drop']['dwin'], '{:+.1f}')} pp；"
                f"只用它 {fmt(res['only']['dmean'])} pp / {fmt(res['only']['dwin'], '{:+.1f}')} pp（保留 {fmt(res['only']['frac'] * 100, '{:.0f}')}%）")

    # 5 起作用的时间与现在
    say("\n## 五、C 起作用的时间（日経在 200 日线上且 VIX < 20 的信号比例）与现在")
    ON = {}
    for s in CS.SAMPLES:
        c = CA.cell_of(A[s])
        ON[s] = float(np.mean(c == 2) * 100) if len(c) else None
    say("- " + "；".join(f"{s} {fmt(ON[s], '{:.0f}')}%" for s in CS.SAMPLES))
    cell_now = 2 * int(now["n225_ma200"] >= 0) + int(now["vix"] >= CA.C_VIX)
    lab = {0: "200 日线下 · VIX < 20", 1: "200 日线下 · VIX ≥ 20", 2: "200 日线上 · VIX < 20", 3: "200 日线上 · VIX ≥ 20"}
    say(f"- 现在（{now['date']}）：日経离 200 日线 {now['n225_ma200'] * 100:+.1f}%、VIX（前一天）{now['vix']:.1f} → {lab[cell_now]}"
        f"{'（C 起作用的那一格）' if cell_now == 2 else '（C 不起作用）'}（仅对本次数据时点有效）")

    # 6 三个年代一起学的规则（前向记录要用的）
    rules_all = CA.fit_c([D[e] for e in CA.ERAS])
    say("\n## 六、用 Z + E + J 三个年代一起学的 C（前向记录如果做，就冻结这一份；这里不评估）")
    say("- " + CS.rule_text("C", rules_all))
    for k, r in rules_all.items():
        if r is not None:
            say(f"- 格子 {lab[k]}：三等分切点与门槛（分数 < {r['thr']:.1f} → 跳过）：" + "、".join(
                f"{f}{'+' if s > 0 else '−'}（{r['cut'][f][0]:.3g} / {r['cut'][f][1]:.3g}）" for f, s in r["sel"].items()))
    say(f"\n用时 {round(time.time() - t0)} s。非投资建议。")
    out = paths.out_dir()
    (out / "combo_all_posthoc.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    payload = {"code": code, "reproduced": same, "learning_placebo": PL, "j_halves": HV, "j_years": YR, "ablation": AB, "on_share": ON, "now": now,
               "cell_now": cell_now, "rules_all": CS.rule_text("C", rules_all),
               "rules_all_detail": {str(k): (None if r is None else {"sel": r["sel"], "cut": r["cut"], "thr": r["thr"], "n": r["n"]}) for k, r in rules_all.items()}}
    (out / "combo_all_posthoc.json").write_text(json.dumps(CS._clean(payload), ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
