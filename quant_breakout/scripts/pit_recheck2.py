"""pit_recheck2.py — 事后核对（不是新的登记检验；读法写在这里、先提交再运行、只运行一次）：把「W2」与「池子」的结论在时点名单上再核一遍，
用现行框架（S0C2 + X6 离场 + 纳指 1545 核心；scripts/leap_confirm.py 同一套组合回测）。

用户（2026-09-30）：「把 W2 与池子的结论在时点名单上再核一遍」。
以前的证据都用「今天的日経225」（幸存者偏差）：W2 对「随机保留同样多」的对照（09-27 复核；09-30 w2mtf：E 0.320 > 随机 95 分位 0.306、
  J 0.400 ≈ 中位 0.396）、第 13 轮的开天眼上限（只做事后赚钱的 W2 突破，日経225 里 E 0.352 < 门槛 0.398 → 要 TOPIX 500 级的池子）；
  09-28 的近似时点核对（scripts/pit_recheck.py）只看了 W2 的每笔增益，而且是旧框架（1655 核心、MACD 死叉离场）。
时点名单（两种，能拿到的都用）：
  ① 近似时点日経225（qbreak/n225_history.py：今天的成员只在被选进之后的年份、2001 年以后被剔除且仍上市的旧成员只在成员年份才允许开新仓，
     进出那一年不算；Z / E 用 yfinance、J 用 J-Quants）——Z 2001-01〜2006-09、E 2006-10〜2016-09、J 2017-01〜；
  ② 时点 TOPIX 500 / TOPIX 1000（J-Quants 每月末上市一览，2016-10 起；只在成员的日子才有信号，leap_confirm.member_mask）——只有 J。
  2006〜2016 的时点 TOPIX 名单要 J-Quants Premium（2008-05 起；没有买）→ 那一段只能核日経225；这一点写进结论，不猜。
算什么（每个名单；「今天的日経225」也算一遍作对照，同一段代码）：
  A W2 结论：现行（W2）、不加 W2、随机保留同样多（scripts/w2mtf_study.random_keep：从没有 W2 的信号里随机保留与 W2 同样多，30 种子；
    中位 / 5 分位 / 95 分位）；
  B 优化方向：今天（w2mtf，6dcebb0）最接近的两个候选——只把周量比回看改成 20 周 W(20, 1.0)、突破日 ≥ 2 倍 + W(20, 1.0)——代替 W2；
  C 池子（开天眼上限）：O1 = 只做「单独交易事后净收益 > 0」的 W2 突破（candle_posthoc.trades，与第 13 轮同一标签法：每只票单独、现行卖出规则、
    扣成本；同一只票上一笔没卖的信号没有标签 → 不做），与「质的飞跃」门槛 = 现行 Calmar + leap_common.CALMAR_UP（Z 0.05 / E、J 0.10）比。
读法（事先写定；四条都只影响预期与文档，模拟盘 / 执行器 / W2 / 股票池一律不改）：
  R1 「W2 在 2006〜2016 是真的」：近似时点 E 的现行 Calmar > 随机 95 分位 → 不变；否则 → 变弱（交给 W2 前向记录）。
  R2 「W2 在 2017〜2026 只等于随机」：近似时点日経225 J、时点 TOPIX 500、时点 TOPIX 1000 三个池子里，现行落在随机 5〜95 分位之间的 ≥ 2 个 → 不变；
     高于 95 分位的 ≥ 2 个 → 时点池上反而成立；低于 5 分位的 ≥ 2 个 → 时点池上更差。
  R3 「量的搭法没有优化方向」：两个候选在近似时点 E 与 J 各自的 Calmar 增益都 < +0.02（w2mtf 的 a）→ 不变；
     某个候选 E、J 都 ≥ +0.02 → 时点名单上有差别（只描述；要用得另外登记）。
  R4 「日経225 里怎么挑都到不了门槛、要扩大池」：近似时点 E 的 O1 < 门槛 → 前半句不变；时点 TOPIX 500 J 的 O1 ≥ 门槛 → 后半句不变；
     任一相反 → 写「第 13 轮的结论在时点名单上要改」。
局限：旧成员里倒闭 / 被收购而退市的没有行情（残余的幸存者偏差）；成员只按年份；O1 的标签用单独交易（MACD 死叉离场；账户用 X6），
  与第 13 轮相同；随机对照只控制「少做同样多」。
输出：var/out/pit_recheck2.md / .json（只有统计）
"""
from __future__ import annotations

import json
import os
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
import leap_common as LC                                                     # noqa: E402
from qbreak import n225_history as H                                         # noqa: E402
from qbreak import paths                                                     # noqa: E402

SEEDS = 30
POOLS = (("Z", "today"), ("Z", "pit"), ("E", "today"), ("E", "pit"), ("J", "today"), ("J", "pit"), ("J", "U1"), ("J", "U2"))
POOL_ZH = {"today": "今天的日経225", "pit": "近似时点日経225", "U1": "时点 TOPIX 500", "U2": "时点 TOPIX 1000"}
CANDS = ("d1.5·W20/1·M0", "d2·W20/1·M0")                                    # 今天 w2mtf 最接近的两个（E + J 差合计 +0.017 / +0.024）
CAND_ZH = {"d1.5·W20/1·M0": "回看 20 周 W(20, 1.0)", "d2·W20/1·M0": "突破日 ≥ 2 倍 + W(20, 1.0)"}
GAIN = 0.02                                                                  # R3：各自 Calmar 增益 ≥ +0.02 才算「有差别」（w2mtf 的 a）
CUR, NOW2, O1 = "现行（W2）", "不加 W2", "O1 只做事后赚钱的"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 读法（纯函数，tests/test_pit_recheck2.py 检验） ─────────────────────────
def rule_r1(out: dict) -> tuple[bool, str]:
    x = out["E/pit"]
    c, q = x["res"][CUR]["calmar"], x["placebo"]["q95"]
    ok = c is not None and q is not None and c > q
    return ok, (f"近似时点 E：现行 {c:.3f} {'>' if ok else '≤'} 随机 95 分位 {q:.3f} → " + ("**W2 在 2006〜2016 的证据不变**" if ok else "**W2 在 2006〜2016 的证据变弱（交给 W2 前向记录）**"))


def rule_r2(out: dict) -> tuple[str, str]:
    pos = {}
    for key in ("J/pit", "J/U1", "J/U2"):
        x = out[key]
        c, lo, hi = x["res"][CUR]["calmar"], x["placebo"]["q05"], x["placebo"]["q95"]
        pos[key] = "缺" if c is None or lo is None or hi is None else ("高" if c > hi else ("低" if c < lo else "中"))
    n_mid, n_hi, n_lo = [sum(1 for v in pos.values() if v == k) for k in ("中", "高", "低")]
    if n_hi >= 2:
        lab = "时点池上反而成立"
    elif n_lo >= 2:
        lab = "时点池上更差"
    elif n_mid >= 2:
        lab = "不变（只等于随机）"
    else:
        lab = "三个池子不一致"
    txt = "；".join(f"{POOL_ZH[k.split('/')[1]]} {out[k]['res'][CUR]['calmar']:.3f} 在随机 5〜95 分位 {out[k]['placebo']['q05']:.3f}〜{out[k]['placebo']['q95']:.3f} 之{'内' if pos[k] == '中' else ('上' if pos[k] == '高' else '下')}"
                   for k in pos if pos[k] != "缺")
    return lab, f"{txt} → **W2 在 2017〜2026：{lab}**"


def gains(out: dict, k: str) -> dict[str, float | None]:
    g = {}
    for era in ("E", "J"):
        x = out[f"{era}/pit"]["res"]
        a, b = x[k]["calmar"], x[CUR]["calmar"]
        g[era] = None if a is None or b is None else round(a - b, 3)
    return g


def rule_r3(out: dict) -> tuple[bool, str]:
    parts, changed = [], []
    for k in CANDS:
        g = gains(out, k)
        both = all(v is not None and v >= GAIN for v in g.values())
        if both:
            changed.append(k)
        parts.append(f"{CAND_ZH[k]} E {g['E']:+.3f} / J {g['J']:+.3f}" if None not in g.values() else f"{CAND_ZH[k]} —")
    ok = not changed
    return ok, "；".join(parts) + " → " + ("**量的搭法没有优化方向：不变**" if ok else f"**时点名单上有差别（{'、'.join(CAND_ZH[k] for k in changed)}，只描述、要用得另外登记）**")


def rule_r4(out: dict) -> tuple[bool, str]:
    e, j = out["E/pit"], out["J/U1"]
    oe, be = e["res"][O1]["calmar"], e["bar"]
    oj, bj = j["res"][O1]["calmar"], j["bar"]
    a_ok = oe is not None and oe < be
    b_ok = oj is not None and oj >= bj
    txt = (f"近似时点 E：O1 {oe:.3f} {'<' if a_ok else '≥'} 门槛 {be:.3f}；时点 TOPIX 500 J：O1 {oj:.3f} {'≥' if b_ok else '<'} 门槛 {bj:.3f} → "
           + ("**第 13 轮的结论不变（日経225 里怎么挑都到不了，扩大池的上限仍在门槛之上）**" if a_ok and b_ok
              else "**第 13 轮的结论在时点名单上要改**（" + ("日経225 里的开天眼到了门槛" if not a_ok else "") + ("；" if not a_ok and not b_ok else "") + ("扩大池的开天眼也到不了" if not b_ok else "") + "）"))
    return a_ok and b_ok, txt


# ───────────────────────── 数据 ─────────────────────────
def load_pool(era: str, pool: str, p0, smoke: bool = False) -> tuple[dict, dict]:
    """(ctx, 指标表 fa)：fa 的 entry = 不加 W2 的突破，且只在成员的日子（today → 全部）。"""
    import leap_confirm as LF
    import pit_recheck as PR
    from qbreak.config import universe
    if era in ("Z", "E"):
        today = list(universe("JP", "broad"))
        names = today if pool == "today" else H.pit_names(today)
        if smoke:
            names = names[:10] + (sorted(H.REMOVED)[:3] if pool == "pit" else [])
        ctx = LF.context(era, names=names)
    else:
        ctx = LF.context("J") if pool in ("today", "pit") else LF.context("J", jmem=pool)
        if pool == "pit":
            ctx = PR.j_pit_context(ctx)
        if smoke:
            ctx["cols"] = ctx["cols"][:12]
    fa = LF.frames(ctx, p0)
    mem = H.member_mask(fa) if pool == "pit" else (LF.member_mask(ctx, fa) if pool in ("U1", "U2") else None)
    if mem is not None:
        fa = LF.with_mask(fa, mem)
    return ctx, fa


def oracle_keep(fr: dict, label: dict, rule) -> dict[str, np.ndarray]:
    """leap_r13_oracle 同一做法：{(票, 信号日): 单独交易的净收益 %} → entry 且 rule(净收益) 才保留（没有标签 → 不保留）。"""
    out = {}
    for t, df in fr.items():
        ent = df["entry"].to_numpy(bool)
        k = np.zeros(len(df), bool)
        for i in np.flatnonzero(ent):
            v = label.get((t, df.index[i]))
            k[i] = v is not None and bool(rule(v))
        out[t] = k
    return out


def seg(r: dict, era: str) -> dict:
    x = r[era]
    return {"cagr": x.get("cagr"), "dd": x.get("dd"), "calmar": x.get("calmar"), "n": x.get("n"), "mean": x.get("mean"), "win": x.get("win"),
            "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")]}


def cell(s: dict | None) -> str:
    if not s or s.get("calmar") is None:
        return "—"
    f = lambda v, fmt: "—" if v is None else fmt.format(v)                  # noqa: E731
    return f"{f(s['cagr'], '{:.2f}')}% / {f(s['dd'], '{:.2f}')}% / {f(s['calmar'], '{:.3f}')} · {s.get('n') or 0} 笔 {f(s.get('mean'), '{:+.2f}')}% / {f(s.get('win'), '{:.1f}')}%"


# ───────────────────────── 主流程 ─────────────────────────
def main(argv=None) -> int:
    import candle_posthoc as CPH
    import leap_confirm as LF
    import w2mtf_study as W
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    argv = list(sys.argv[1:] if argv is None else argv)
    smoke = "--smoke" in argv or os.environ.get("QBREAK_SMOKE") == "1"
    seeds = 2 if smoke else SEEDS
    t0 = time.time()
    root = str(paths.PROJECT_ROOT)
    code = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    watched = ["scripts/pit_recheck2.py", "scripts/pit_recheck.py", "qbreak/n225_history.py", "scripts/leap_confirm.py", "scripts/w2mtf_study.py",
               "scripts/candle_portfolio.py", "scripts/candle_posthoc.py"]
    dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", *watched], capture_output=True, text=True).stdout.strip())
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    assert float(p.min_weekly_vol_ratio) == 1.0 and float(px.vol_mult) == 1.5, (p.min_weekly_vol_ratio, px.vol_mult)
    say(f"# 事后核对：W2 与池子的结论在时点名单上再核一遍（{pd.Timestamp.today().date()}；代码 {code}{'（脏）' if dirty else ''}；现行框架 S0C2 + X6 + 纳指 1545）")
    say("读法见 scripts/pit_recheck2.py 开头（先提交再运行）。各格 = 组合年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔 / 胜率；「信号」= 窗口内不加 W2 的突破数 → W2 保留数。")
    OUT: dict[str, dict] = {}
    for era, pool in POOLS:
        t1 = time.time()
        ctx, fa = load_pool(era, pool, p0, smoke)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        run_fn = LF.runner(ctx, fa)
        keep = LF.w2_keep(ctx, fa)
        fr_w2 = LF.with_mask(fa, keep)

        def run_keep(fr: dict) -> dict:
            return seg(LF.run(ctx, run_fn, fr, px), era)

        res = {CUR: run_keep(fr_w2), NOW2: run_keep(fa)}
        raw_n = W.kept_count(fa, {t: np.ones(len(df), bool) for t, df in fa.items()}, a, b)
        n_w2 = W.kept_count(fa, keep, a, b)
        pl = []
        for s in range(seeds):
            r = LF.run(ctx, run_fn, LF.with_mask(fa, W.random_keep(fa, a, b, n_w2, seed=1000 * s + 7)), px)
            pl.append(r[era]["calmar"])
        v = np.array([x for x in pl if x is not None], float)
        placebo = {"median": (round(float(np.median(v)), 3) if len(v) else None), "q05": (round(float(np.percentile(v, 5)), 3) if len(v) else None),
                   "q95": (round(float(np.percentile(v, 95)), 3) if len(v) else None), "vals": pl}
        R = W.ratios(ctx, fa)
        kept = {CUR: n_w2}
        for k in CANDS:
            kc = {t: W.keep_mask(R[t], W.VARIANTS[k]) for t in fa}
            res[k] = run_keep(LF.with_mask(fa, kc))
            kept[k] = W.kept_count(fa, kc, a, b)
        T = CPH.trades(fr_w2, p, a)
        T["sig_date"] = pd.to_datetime(T["sig_date"])
        T = T[T["sig_date"] >= pd.Timestamp(a)]
        label = {(t, d): float(x) for t, d, x in zip(T["ticker"], T["sig_date"], T["net"])}
        ko = oracle_keep(fr_w2, label, lambda x: x > 0)
        res[O1] = run_keep(LF.with_mask(fr_w2, ko))
        kept[O1] = W.kept_count(fa, ko, a, b)
        bar = None if res[CUR]["calmar"] is None else round(res[CUR]["calmar"] + LC.CALMAR_UP[era], 3)
        OUT[f"{era}/{pool}"] = {"era": era, "pool": pool, "names": len(fa), "window": [a, b], "raw_n": raw_n, "kept": kept, "res": res, "placebo": placebo,
                                "bar": bar, "standalone": {"n": int(len(T)), "win": (round(float((T["net"] > 0).mean() * 100), 1) if len(T) else None)},
                                "secs": round(time.time() - t1)}
        say(f"- {era} {POOL_ZH[pool]}：{len(fa)} 只；信号 {raw_n} → W2 {n_w2}；现行 {cell(res[CUR])}；随机中位 {placebo['median']}；{round(time.time() - t1)} s")
    if smoke:
        say("\n（--smoke：只做接线检查，不写结果）")
        return 0
    say("\n## 一、W2 结论（现行 vs 不加 W2 vs 随机保留同样多；Calmar 与随机的 5 / 50 / 95 分位）")
    say("| 窗口 | 名单 | 只数 · 信号 → W2 | 现行（W2） | 不加 W2 | 随机 5 / 50 / 95 分位 | 现行在随机里的位置 |")
    say("|---|---|---|---|---|---|---|")
    for key, x in OUT.items():
        c, q = x["res"][CUR]["calmar"], x["placebo"]
        pos = "—" if c is None or q["q05"] is None else ("高于 95 分位" if c > q["q95"] else ("低于 5 分位" if c < q["q05"] else "5〜95 之间"))
        say(f"| {x['era']} | {POOL_ZH[x['pool']]} | {x['names']} · {x['raw_n']} → {x['kept'][CUR]} | {cell(x['res'][CUR])} | {cell(x['res'][NOW2])} | "
            f"{q['q05']} / {q['median']} / {q['q95']} | {pos} |")
    say("\n## 二、优化方向（今天最接近的两个候选代替 W2；Calmar · 比现行）")
    say("| 窗口 | 名单 | " + " | ".join(CAND_ZH[k] for k in CANDS) + " |")
    say("|---|---|" + "---|" * len(CANDS))
    for key, x in OUT.items():
        cells = []
        for k in CANDS:
            s, b0 = x["res"][k], x["res"][CUR]["calmar"]
            cells.append("—" if s["calmar"] is None or b0 is None else f"{s['calmar']:.3f}（{s['calmar'] - b0:+.3f}；信号 {x['kept'][k]}、{s['n']} 笔）")
        say(f"| {x['era']} | {POOL_ZH[x['pool']]} | " + " | ".join(cells) + " |")
    say("\n## 三、池子（开天眼上限 O1 = 只做事后赚钱的 W2 突破 vs 质的飞跃门槛 = 现行 + CALMAR_UP）")
    say("| 窗口 | 名单 | 单独交易 笔数 / 胜率 | O1（保留的信号） | 门槛 | 到不到 |")
    say("|---|---|---|---|---|---|")
    for key, x in OUT.items():
        o, st = x["res"][O1], x["standalone"]
        say(f"| {x['era']} | {POOL_ZH[x['pool']]} | {st['n']} / {st['win']}% | {cell(o)}（{x['kept'][O1]}） | {x['bar']} | "
            f"{'—' if o['calmar'] is None or x['bar'] is None else ('到了' if o['calmar'] >= x['bar'] else '到不了')} |")
    r1, r2, r3, r4 = rule_r1(OUT), rule_r2(OUT), rule_r3(OUT), rule_r4(OUT)
    say("\n## 读法（事先写定）")
    say(f"- R1 {r1[1]}")
    say(f"- R2 {r2[1]}")
    say(f"- R3 {r3[1]}")
    say(f"- R4 {r4[1]}")
    say("- 2006〜2016 的时点 TOPIX 名单要 J-Quants Premium（没有）→ 「扩大池」那一半只在 2017〜2026 核过；四条都只影响预期与文档，模拟盘 / 执行器 / W2 / 股票池不改。")
    say(f"- 用时 {time.time() - t0:.0f} s。非投资建议。")
    out = {"git": code, "dirty": dirty, "pools": OUT, "R1": {"ok": r1[0], "text": r1[1]}, "R2": {"label": r2[0], "text": r2[1]},
           "R3": {"ok": r3[0], "text": r3[1]}, "R4": {"ok": r4[0], "text": r4[1]}, "cands": list(CANDS), "seeds": seeds, "elapsed_s": round(time.time() - t0)}
    fp = paths.out_dir() / "pit_recheck2"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
