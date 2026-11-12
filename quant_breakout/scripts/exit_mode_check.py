"""exit_mode_check.py — 模拟盘的离场里加进卖法 X6 / R4：几种加法放在账户历史上会怎样、选哪一种（2026-09-29 登记；只跑一次，看完不改规则）。

用户（2026-09-29）：「把卖法 X6 / R4 也加进离场」。用户已经决定加 → 这里不决定「加不加」，只按事先写定的规则决定「怎么加」，结果照实报告。
X6 / R4 本来都是「代替死叉」的卖法（qbreak/exit_forward.py：X6 = 收盘 < 持有以来最高价 − 3 × ATR14；R4 = 抛物线 SAR 翻到价格上方），
两个一起加有几种方式 → qbreak/exit_rules.py 的五种（同一次提交写定）：
  DC 现行（MACD 死叉）；X6 吊灯止损代替死叉；R4 SAR 翻转代替死叉；X6R4 吊灯或 SAR 哪个先到（不看死叉）；ALL 死叉、吊灯、SAR 哪个先到。
  止损 −7%、跟踪 12%、止盈 +25%、放量阴线、最长 60 个交易日、买点、W2、仓位都不变。

零 账户：与 scripts/fwd_judgment_check.py 的 V0 相同（S0C2 + W2、日経225 突破 4 个名额 × 25%、闲置资金买 1655、T0、立花费用、
   新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜；当时真实的一手）。窗口 E 2006-10〜2016-09、J 2017-01〜；Z 2001〜2006-09 只描述。
   卖法只用 qbreak/unified.py 引擎里的实现（与模拟盘 / 执行器同一段代码）；R4 的 SAR 列按 qbreak/exit_forward.sar_flip 加在指标表上。
一 核对（任何一条不成立 → 停止、不选）：
   ① DC 在带 SAR 列的指标表上与原表完全相同（多一列不改任何东西）；
   ② X6 与研究用引擎 scripts/bsh_common（BSHEngine 的 X6，bsh_explore 用过的实现）在 E / J 上完全相同（Calmar、笔数、逐笔净收益）；
   ③ R4 与「把 dead_cross 列换成 sar_flip」（scripts/sell_common 的做法）在 E / J 上完全相同。
二 选择（事先写定）：在 X6 / R4 / X6R4 / ALL 里，按 min(E 的 Calmar 差, J 的 Calmar 差)（差 = 方式 − DC）最大的选；
   两个方式的这个值相差 < 0.005 → 先选只有一条的（X6、R4 优先于 X6R4、ALL），再比 Z 的 Calmar。
   读法（与前向记录判断层同一个）：选中的方式 E、J 的 Calmar 都比 DC 高 ≥ 0.02 →「历史上有帮助」；都低 ≥ 0.02 →「历史上有害（建议你重新考虑）」；
   其余「差不多」。有害也照你的决定加，但汇报时写在第一行。
三 照实写：X6、R4 都是在 E / J 上探索出来的（bsh_explore、sell_explore），Z 与扩大池用于 R4 的确认（sell_confirm）→ 这里没有「没看过的数据」，
   选择只是在你要求的几种加法里挑历史上最不坏的，不是新证据；前向记录（score_forward 第十〜十一节、w2_forward_all 第八〜九节）照旧
   比「死叉 vs X6 / R4」，用登记之后的新信号检验。
输出：var/out/exit_mode_check.md / .json。非投资建议。
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
from qbreak import exit_forward as EF                                        # noqa: E402
from qbreak import exit_rules as EXR                                         # noqa: E402
from qbreak import paths                                                     # noqa: E402

TAGS = ("E", "J", "Z")
JUDGE = ("E", "J")
CANDS = ("X6", "R4", "X6R4", "ALL")
SINGLE = ("X6", "R4")
GAIN, TIE = 0.02, 0.005
NEEDS_SAR = {m for m, v in EXR.MODES.items() if v["exit_sar_flip"]}


def pick(acct: dict) -> tuple[str, dict]:
    """事先写定的选择：min(E 差, J 差) 最大；相差 < TIE → 只有一条的优先，再比 Z。返回 (方式, {方式: 分数})。"""
    score = {m: min(acct[t][m]["calmar"] - acct[t]["DC"]["calmar"] for t in JUDGE) for m in CANDS}
    best = max(score.values())
    near = [m for m in CANDS if best - score[m] < TIE]
    near.sort(key=lambda m: (m not in SINGLE, -(acct.get("Z", {}).get(m, {}).get("calmar") or -9.0), CANDS.index(m)))
    return near[0], score


def reading(acct: dict, m: str) -> str:
    d = [acct[t][m]["calmar"] - acct[t]["DC"]["calmar"] for t in JUDGE]
    if all(x >= GAIN - 1e-12 for x in d):
        return "历史上有帮助"
    if all(x <= -GAIN + 1e-12 for x in d):
        return "历史上有害（建议你重新考虑）"
    return "差不多"


def with_sar(fr: dict) -> dict:
    return {t: df.assign(sar_flip=EF.sar_flip(df)) for t, df in fr.items()}


def _same(r1: dict, r2: dict, t1: pd.DataFrame, t2: pd.DataFrame, tag: str) -> bool:
    a, b = r1[tag], r2[tag]
    keys = ("cagr", "dd", "calmar", "n")
    return all(a[k] == b[k] for k in keys) and len(t1) == len(t2) and np.allclose(t1["net"].to_numpy(float), t2["net"].to_numpy(float))


def main() -> int:
    import bsh_common as BC
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    acct: dict = {t: {} for t in TAGS}
    prof: dict = {t: {} for t in TAGS}
    checks: dict = {}
    for tag in TAGS:
        ctx = LF.context(tag)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        fs = with_sar(fw)
        a, b = ctx["windows"][tag]
        trades = {}
        for m in EXR.MODES:
            r = LF.run(ctx, run_fn, fs if m in NEEDS_SAR else fw, EXR.apply(p, m))
            tr = BC.last_trades(a, b)
            acct[tag][m] = {x: r[tag][x] for x in ("cagr", "dd", "calmar", "n", "mean", "win")}
            prof[tag][m] = BC.trade_profile(tr)
            trades[m] = (r, tr)
        r_dc2 = LF.run(ctx, run_fn, fs, EXR.apply(p, "DC"))                                       # ① 多一列不改任何东西
        checks.setdefault("①", {})[tag] = _same(trades["DC"][0], r_dc2, trades["DC"][1], BC.last_trades(a, b), tag)
        if tag in JUDGE:
            ctx["era"] = tag
            rx, trx = BC.run_variant(ctx, run_fn, fw, p, "X6")                                    # ② 研究用引擎的 X6
            checks.setdefault("②", {})[tag] = _same(trades["X6"][0], rx, trades["X6"][1], trx, tag)
            fr4 = {t: df.assign(dead_cross=EF.sar_flip(df)) for t, df in fw.items()}             # ③ 死叉列换成 SAR 翻转
            r4 = LF.run(ctx, run_fn, fr4, EXR.apply(p, "DC"))
            checks.setdefault("③", {})[tag] = _same(trades["R4"][0], r4, trades["R4"][1], BC.last_trades(a, b), tag)
        print(f"{tag} 完成（{time.time() - t0:.0f}s）：" + "、".join(f"{m} {acct[tag][m]['calmar']:.3f}" for m in EXR.MODES), flush=True)
    ok = all(all(v.values()) for v in checks.values())
    chosen, score = pick(acct) if ok else (None, {})
    rd = reading(acct, chosen) if chosen else None
    L = ["# 离场里加进卖法 X6 / R4：几种加法的账户历史与选择（2026-09-29 登记，只跑一次；规则见本脚本开头与 qbreak/exit_rules.py）", "",
         "核对：" + "；".join(f"{k} " + "、".join(f"{t} {'相同' if v else '★ 不同'}" for t, v in d.items()) for k, d in checks.items()), ""]
    if not ok:
        L.append("★ 核对不成立 → 按规则停止，不选。")
    else:
        L.append(f"选中：**{chosen} {EXR.LABELS[chosen]}**（min(E 差, J 差) = {score[chosen]:+.3f}）；读法：**{rd}**")
    L += ["", "| 方式 | " + " | ".join(f"{t} 年化 / 最大回撤 / Calmar / 个股笔数" for t in TAGS) + " | 选择分 |", "|---|" + "---|" * (len(TAGS) + 1)]
    for m in EXR.MODES:
        L.append(f"| {m} {EXR.LABELS[m]} | " + " | ".join(
            f"{acct[t][m]['cagr']:+.2f}% / {acct[t][m]['dd']:.2f}% / {acct[t][m]['calmar']:.3f} / {acct[t][m]['n']}" for t in TAGS)
            + f" | {'—' if m not in score else f'{score[m]:+.3f}'} |")
    L += ["", "逐笔（窗口内买入的个股交易；每笔净收益 %、胜率、持有中位天数、出场原因占比）："]
    for t in TAGS:
        for m in EXR.MODES:
            pr = prof[t][m]
            if not pr.get("n"):
                L.append(f"- {t} {m}：没有交易")
                continue
            rs = "、".join(f"{k} {v:.0f}%" for k, v in list(pr["reasons"].items())[:5])
            L.append(f"- {t} {m}：{pr['n']} 笔，每笔 {pr['mean']:+.2f}%，胜率 {pr['win']:.1f}%，持有中位 {pr['hold']:.0f} 天；{rs}")
    L += ["", "照实写：X6、R4 都是在 E / J 上探索出来的，Z 与扩大池用于 R4 的确认 → 这里没有没看过的数据，只是在你要求的几种加法里挑历史上最不坏的。"
          "X6 / R4 前向记录照旧比「死叉 vs X6 / R4」。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "exit_mode_check"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"checks": checks, "chosen": chosen, "reading": rd, "score": score, "accounts": acct,
                                              "profiles": prof}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
