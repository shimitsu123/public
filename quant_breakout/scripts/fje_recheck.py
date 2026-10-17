"""fje_recheck.py — FJE 按修正口径重新检验（2026-10-03 用户 ㊼ ①「重新检验，不过就撤」；先提交后只运行一次，看完不改规则）。

为什么（照实写）：事后审计（scripts/fx_timing_audit.py；var/sim_changes.md 2026-10-03「事后审计：研究引擎里汇率的时点偏差」）发现：
  Yahoo「JPY=X」标成 d 日的值 ≈ d 日东京早上；研究合成的 1545 东证价以前用「d 之前（不含 d）」的值 → 比信号（DEXJPUS 纽约中午）旧约 17 小时
  → 汇率择时在回测里提前看到了引起信号的那段汇率变动。修正后（第六个循环的账户口径）FJE − B0 的 Calmar 差 Z +0.059、E +0.038、J −0.034。
  用户选 ①：研究口径改成修正口径（scripts/equity_idle_study.fx_on，上一个提交）→ 按修正口径「与当初同一套第一关 + 第二关」重新检验 FJE、
  只运行一次；过了 → 模拟盘照旧；不过 → 撤掉模拟盘与执行器的 FJE（用户事先同意，不再另问）。
做法 —— 与第一个研究循环第 15 轮（scripts/loop_r15_fxeunion.py，登记 80e7649 / 第二关 f1c205c）同一段代码，只是研究口径换了：
  基准 B0 = scripts/loop_common.py（第一个循环的 B0：S0C2 + W2 + C 留一年代 + X6 + 判断层市场层 + 闲置资金 Q1 = 1545 + 美股牛熊）；
  FJE = loop_r15_fxeunion.states / fje_over（FXE 的多数决急升中 或 JBH 的日経熊且日元牛，且美股牛 → 闲置资金拿对冲版纳指 2845；信号仍用 DEXJPUS）。
  第一关 = research_loop.stage1（S1 三个年代 Calmar 差合计 ≥ +0.03、S2 每个年代 ≥ −0.02、S3 最大回撤不深 2 pp 以上、S4 前后两半合计都 ≥ 0；
    S5 / S6 不适用 —— 与当初相同）。
  第二关（第一关全过才做；这次在同一次运行里接着做，规则与当初另行登记的完全相同）：合并后的「对冲中」序列在 2000-01-03〜2026-09-30 整体循环平移 k
    （loop_r15_fxeunion.shifted：numpy.random.default_rng([20261015, s])、k ∈ [250, N − 250]、s = 0〜399；每个随机对照的账户同 _placebo_one），
    统计量 = 三个年代 Calmar 差合计，要严格大于 400 次的最大值（有算不出的 = 不过）。
判定（事先写定，看完不改）：research_loop.verdict =「更好候选」（两关都过）→「保留」（模拟盘不改）；否则 →「撤掉」：模拟盘与执行器的闲置资金
  不再在日元走强时换 2845（美股牛 1545、美股熊且股债负相关 1482、其余现金），从下一个决策起（另一个提交，记进 sim_changes「配置变更」）。
只描述（不参与判定）：与当初第 15 轮（原口径）的数字对照；FJE 状态占美股牛日子的比例与段数（信号没变）；核心换仓笔数；
  没看过的 1987〜2000 只有核心（日元计纳指用 DEXJPUS 同一天的值，不受这次口径影响）。
事前预期（照实写，写在运行之前）：审计（第六个循环的账户口径、费用按 qbreak/fees.py）FJE 修正后 J −0.034 < −0.02 → 第 15 轮的口径（费用略不同）
  多半也是 S2 不过（估计约 85%）→ 多半「撤掉」。
运行：python scripts/fje_recheck.py [--workers 3]（第一关约 5 分钟；第一关全过才接着做第二关，约 10〜15 分钟）→ var/out/fje_recheck.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop_common as LCM                                                    # noqa: E402
import loop_r15_fxeunion as R15                                              # noqa: E402
import research_loop as RL                                                   # noqa: E402

OUT = "fje_recheck"
KEEP, DROP = "保留", "撤掉"
ORIG = ("loop_r15_fxeunion.json", "loop_r15_fxeunion_stage2_FJE.json")      # 当初（原口径）的第一关 / 第二关
FILES = ("scripts/fje_recheck.py", "scripts/equity_idle_study.py", "scripts/loop_common.py", "scripts/research_loop.py",
         "scripts/loop_r15_fxeunion.py", "scripts/loop_r04_yensurge.py", "scripts/loop_r11_fxensemble.py", "scripts/loop_r13_jpbearhedge.py")


def decision(verdict: str) -> str:
    """登记的判定：两关都过（更好候选）→ 保留；其余 → 撤掉。"""
    return KEEP if verdict == RL.FOUND else DROP


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", *FILES], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def original() -> dict:
    """当初（原口径）第 15 轮的数字（只描述）。"""
    from qbreak import paths
    out: dict = {}
    try:
        a = json.loads((paths.out_dir() / ORIG[0]).read_text(encoding="utf-8"))
        out["base"] = {e: a["base"][e]["calmar"] for e in LCM.ERAS}
        out["cand"] = {e: a["cand"]["FJE"][e]["calmar"] for e in LCM.ERAS}
        out["stage1"] = {k: a["stage1"]["FJE"].get(k) for k in ("d", "sum", "S1", "S2", "S3", "S4", "h1", "h2", "ok")}
        b = json.loads((paths.out_dir() / ORIG[1]).read_text(encoding="utf-8"))
        out["stage2"] = {"stat": b["stat"], "max": b["stage2"]["max"], "ge_stat": b["stage2"]["ge_stat"], "verdict": b["verdict"]}
    except (OSError, KeyError, ValueError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def stage_two(W: dict, state: pd.Series, hedged: pd.DataFrame, base: dict, workers: int, t0: float) -> list:
    """第二关：与第 15 轮 stage_two 同一个随机对照（R15._placebo_one、R15.shifted、种子 0〜399）。"""
    import multiprocessing as mp
    R15._G.update({"W": W, "state": state, "hedged": hedged, "base": base})
    seeds = list(range(RL.PLACEBO_N))
    vals: list = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(R15._placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(R15._placebo_one(i))
            if (i + 1) % 40 == 0:
                print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    return vals


def run_once(workers: int = 1) -> dict:
    import equity_idle_study as EI
    import loop_r04_yensurge as Y
    if EI.fx_align() != "same":
        raise SystemExit(f"研究口径不是修正口径（{EI.FX_ALIGN_ENV} = prev）→ 不运行")
    t0 = time.time()
    code, dirty = git_head()
    W = LCM.load()
    fxh, jbh, uni = R15.states(W)
    hedged = Y.hedged_frame(W["inp"])
    ov = R15.fje_over(W, uni, hedged)
    base, cand, ctr, desc = {}, {}, {}, {}
    for e in LCM.ERAS:
        rb = LCM.run(W, e)
        ctr[e] = {"B0": R15.core_trades(e, W)}
        base[e] = R15._acct(rb)
        rc = LCM.run(W, e, **ov)
        ctr[e]["FJE"] = R15.core_trades(e, W)
        cand[e] = R15._acct(rc)
        desc[e] = R15.describe(W, e, fxh, jbh, uni)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = RL.stage1(cand, base)
    s2, vals, q = None, None, {}
    if s1["ok"]:
        bc = {e: base[e]["calmar"] for e in LCM.ERAS}
        stat = round(sum(cand[e]["calmar"] - bc[e] for e in LCM.ERAS), 6)
        vals = stage_two(W, uni, hedged, bc, workers, t0)
        s2 = RL.stage2(stat, vals)
        v = np.array([x for x in vals if x is not None], float)
        q = {k: round(float(np.percentile(v, k)), 4) for k in (50, 95, 99)} if len(v) else {}
    vd = RL.verdict(s1, s2)
    res = {"code": code, "dirty": dirty, "fx_align": EI.fx_align(), "base": base, "cand": cand, "stage1": s1, "stage2": s2, "placebo": vals,
           "q": q, "verdict": vd, "decision": decision(vd), "core_trades": ctr, "describe": desc,
           "old": R15.old_core(W["inp"], W["bear"]["US"], {"FXE": fxh, "JBH": jbh, "FJE": uni}), "original": original(),
           "seconds": round(time.time() - t0)}
    write(res)
    return res


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1, s2, o = res["stage1"], res["stage2"], res["original"]
    L = [f"# FJE 按修正口径重新检验（用户 ㊼ ①；{pd.Timestamp.today().date()}；代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；"
         f"规则见 scripts/fje_recheck.py 开头）", "",
         f"**判定：{res['verdict']} →「{res['decision']}」**（{'模拟盘照旧' if res['decision'] == KEEP else '撤掉模拟盘与执行器的 FJE（另一个提交）'}）", "",
         f"- 第一关：S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2（每个年代 ≥ −0.02）：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用"]
    if s2:
        L.append(f"- 第二关：候选 {_f(s2['stat'], '{:+.4f}')}；400 次随机最大 {_f(s2['max'], '{:+.4f}')}、≥ 候选 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']}；"
                 f"中位数 {_f(res['q'].get(50), '{:+.4f}')}、95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}")
    else:
        L.append("- 第二关：第一关没全过 → 不做（与当初的规则相同）")
    L += ["", "| 年代 | B0 年化 / 最大回撤 / Calmar（前半 / 后半） | FJE（Calmar 差） | 当初（原口径）B0 → FJE |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in LCM.ERAS:
        was = (f"{_f((o.get('base') or {}).get(e))} → {_f((o.get('cand') or {}).get(e))}（{_f(((o.get('stage1') or {}).get('d') or {}).get(e), '{:+.3f}')}）"
               if o.get("base") else "—")
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {was} |")
    if o.get("stage1"):
        L.append(f"\n当初（原口径）：第一关合计 {_f(o['stage1'].get('sum'), '{:+.3f}')}；第二关 {_f((o.get('stage2') or {}).get('stat'), '{:+.3f}')} "
                 f"> 400 次最大 {_f((o.get('stage2') or {}).get('max'), '{:+.3f}')} →「{(o.get('stage2') or {}).get('verdict', '—')}」")
    L += ["", "只描述（不参与判定）："]
    for e in LCM.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：对冲中 {_f(d['in_bull_pct'], '{:.1f}')}%（占美股牛的日子）、{d['episodes']} 段；核心换仓 B0 {c['B0']} → FJE {c['FJE']}")
    od = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的 1987〜2000（只有核心，DEXJPUS 同一天、不受这次口径影响）：B0 的开关 {oc(od['B0'])}；FJE {oc(od['FJE'])}")
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FJE 按修正口径重新检验（用户 ㊼ ①；只运行一次）")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    run_once(a.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
