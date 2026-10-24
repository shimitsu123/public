"""layer_tax_study.py — 税后看个股层：B4 的日本个股层扣税之后，还比「个股层关掉、只拿核心」多不多（登记检验；只描述 + 事先写定的读法）。
（2026-10-06 用户：「结合现在的研究结果 还有哪些方向可以提高收益率和胜率 继续研究」；与 scripts/nisa_tax_study.py 同一天登记、各运行一次）
规则先提交（登记）再运行一次；看到结果之后不改规则。

〇 为什么（照实写）
  1 事后诊断（2026-10-03 scripts/loop4_oracle_diag.py，账户 B1，税前）：个股层的贡献（B1 − 个股层关掉）Calmar Z +0.603、E +0.134、J 只有 +0.014。
    个股层每一笔都实现收益（马上交税）；核心 ETF 多半长期拿着、收益到卖出才交税（递延）→ 扣税之后个股层的贡献会更小，J 可能变成负的。以前没有按税后量过。
  2 「胜率」只在个股层有意义；如果个股层税后不比只拿核心好，提高个股胜率的研究对用户实际留下的钱帮助有限 → 先量清楚。
  3 税的算法与 nisa_tax_study 完全相同（import 它的 overlay / stats_of / ledger_of，不另写）。
一 账户（研究引擎，¥100 万起；年代 Z 2001-01-04〜2006-09-30、E 2006-10-01〜2016-09-30、J 2017-01-04〜2026-09-30，同 nisa_tax_study）：
  B4 = 模拟盘规则（B3 + TBF；规则指纹 1241753c8f2529c6）；
  O0 = B4 但这个年代全部 W2 信号都不开（em_tick 全 0 = 个股层关掉；核心 / 闲置资金 Q1B / 倍数 / 牛熊一切照旧；与 loop4_oracle_diag 的 O0 同一做法）。
  先决条件：指纹 = 1241753c8f2529c6、B4 重算 = turn_shape_combo 的 TBF（nisa_tax_study.same_b4：个股笔数与胜率相同、Calmar 差 ≤ 0.005）、
  O0 的个股笔数 = 0。不满足就停。（运行前修正 2026-10-06：原来是「Calmar 差 ≤ 0.0005」，第一次运行在 E 停下 = 当天数据缓存刷新的漂移，
  见 nisa_tax_study 一；停之前只打印了 Z 的税前 Δ +7.28 pp 与 O0 的 Calmar 0.532，没有任何税后结果。）
二 税：nisa_tax_study 的 overlay（源泉徴収あり、清算口径、新 NISA 额度 / 上限）；做法 P0、P0c、N1〜N4（O0 没有个股 → N1 = N2、N3 = P0，照算）。
三 量：个股层的税后贡献 Δ = B4 税后年化 − O0 税后年化（同一个做法、同一个规模；pp）；税前 Δ（同一口径：引擎全期的每日权益）也报；
  规模 ¥100 万（读法用）/ ¥300 万 / ¥1,000 万（只描述）。
四 读法（运行前写定；只描述，不改模拟盘、不改个股层）：
  - 「税后还有贡献」的年代 = P0、¥100 万下 Δ > 0 的年代；「税后没有贡献」= Δ ≤ 0（照实列出）。
  - 「税前有、税后没有」= 税前 Δ > 0 且 P0 税后 Δ ≤ 0 的年代 → 写明「这个年代的个股层只在税前有用」。
  - 「NISA 能救回来」= P0 税后 Δ ≤ 0、但 N3（只个股放 NISA）或 N1 下 Δ > 0 的年代。
  - 三个年代 P0 税后 Δ 都 ≤ 0 →「个股层税后三个年代都不比只拿核心好」（汇报第一行写，要用户决定要不要缩小 / 关掉个股层或个股放 NISA）。
  - 任何读法都只是提议：关掉 / 缩小个股层、改放 NISA 是策略的大改动，要用户决定并记 sim_changes；模拟盘 / 执行器不因这次研究改。
五 事前预期（运行前写）：税前 Δ（年化）Z 约 +6〜8 pp、E 约 +1〜3 pp、J 约 0〜+1 pp（2026-10-03 的诊断是 B1，B4 多了 TBF）；
  P0 税后 Δ ≤ 0 的可能：J 约 60%、E 约 25%、Z 约 0%；N3 / N1 让 J 回到 > 0 的可能约一半。
六 另报（只描述）：两个账户的税合计、特定口座实现的收益（个股 / 核心）、核心 ETF 的买卖次数；J 每年的税后收益（B4 P0、O0 P0）。
七 局限：同 nisa_tax_study 第七节（今天的税制套历史、按比例缩小、分红只在卖出时交税、退税时点简化）；O0 是同一套引擎的「个股层关掉」，
  核心的买卖时点与 B4 不同（不用为个股腾钱）→ 两个账户的差 = 个股层 + 它带来的核心换手；不是另一种策略的检验。非投资建议、也不是税务意见。
输出：var/out/layer_tax_study.md / .json（只有统计，不含个股代码）。
  python scripts/layer_tax_study.py --run    （登记之后只运行一次）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nisa_tax_study as NT                                                  # noqa: E402

ERAS = NT.ERAS
POLICIES = NT.POLICIES
SIZES = NT.SIZES
DECIDE_SIZE = NT.DECIDE_SIZE
FP = NT.FP
B4_TOL = NT.B4_TOL
RESCUE = ("N3", "N1")
OUT_MD, OUT_JSON = "layer_tax_study.md", "layer_tax_study.json"


def read(pre_d: dict, at_d: dict) -> dict:
    """四的读法。pre_d = {年代: 税前 Δ}；at_d = {做法: {年代: 税后 Δ}}（¥100 万；pp）。"""
    p0 = at_d["P0"]
    pos = [e for e in ERAS if p0[e] is not None and p0[e] > 0]
    nonpos = [e for e in ERAS if p0[e] is not None and p0[e] <= 0]
    pre_only = [e for e in nonpos if pre_d.get(e) is not None and pre_d[e] > 0]
    rescue = {e: [p for p in RESCUE if (at_d.get(p) or {}).get(e) is not None and at_d[p][e] > 0] for e in nonpos}
    return {"positive": pos, "nonpositive": nonpos, "pre_only": pre_only, "rescue": {e: v for e, v in rescue.items() if v},
            "all_nonpositive": len(nonpos) == len(ERAS)}


def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/layer_tax_study.py", "scripts/nisa_tax_study.py"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def _row(o: dict) -> dict:
    st = o["stats"]
    return {**NT.stats_of(o["series"]), "tax_paid": round(st["tax_paid"], 0), "real_stock": round(st["real_stock"], 0),
            "real_core": round(st["real_core"], 0), "nisa_share": round(st["nisa_share"], 2)}


def run(say=print) -> dict:
    import jq_study as JS
    import loop10_common as C10
    import loop9_common as C9
    import research_loop as RL
    from qbreak import paths
    t0 = time.time()
    fp_now = RL.rules_fingerprint(paths.PROJECT_ROOT / "var")
    if fp_now != FP:
        raise SystemExit(f"先决条件不满足：模拟盘规则指纹 {fp_now} ≠ 登记时的 {FP} → 停")
    W = C10.load()
    say(f"载入 B3 + Zx：{time.time() - t0:.0f}s")
    tbf = NT.tbf_flags(W, say)
    ref = json.loads((paths.PROJECT_ROOT / "var" / "out" / "turn_shape_combo.json").read_text(encoding="utf-8"))["cand"]["TBF"]
    res: dict = {"git": git_info(), "fingerprint": fp_now, "acct": {}, "ledger": {}, "pre": {}, "at": {}, "delta": {}, "pre_delta": {}, "yearly_J": {}}
    for e in ERAS:
        S = C9.signals(W, e)
        g = tbf[e]
        if len(g) != len(S):
            raise SystemExit("TBF 旗子与信号对不上 → 停")
        b4 = C9.acct(C9.run_block(W, e, g))
        if not NT.same_b4(b4, ref[e]):
            raise SystemExit(f"先决条件不满足：{e} B4 重算 {b4} ≠ turn_shape_combo 的 TBF {ref[e]} → 停")
        LB = NT.ledger_of(JS.RealLotEngine.LAST[-1])
        o0 = C9.acct(C9.run_block(W, e, np.ones(len(S), bool)))
        LO = NT.ledger_of(JS.RealLotEngine.LAST[-1])
        if LO["trades"]:
            raise SystemExit(f"先决条件不满足：{e} O0 还有 {len(LO['trades'])} 笔个股 → 停")
        res["acct"][e] = {"B4": b4, "O0": o0}
        res["ledger"][e] = {k: {"stock_trades": len(L["trades"]), "core_trades": len(L["core"]),
                                "core_sells": sum(1 for c in L["core"] if str(c[2]).upper() == "SELL")} for k, L in (("B4", LB), ("O0", LO))}
        pre = {k: NT.stats_of(L["eq"] * (DECIDE_SIZE / NT.BASE)) for k, L in (("B4", LB), ("O0", LO))}
        res["pre"][e] = pre
        res["pre_delta"][e] = round(pre["B4"]["cagr"] - pre["O0"]["cagr"], 3)
        say(f"{e}：B4 = TBF（Calmar {b4['calmar']}）、O0 Calmar {o0['calmar']}（个股 0 笔）；税前 Δ {res['pre_delta'][e]:+.2f} pp；{time.time() - t0:.0f}s")
        for A in SIZES:
            for p in POLICIES:
                ob = NT.overlay(LB["trades"], LB["core"], LB["eq"], p, A, LB["end_core"])
                oo = NT.overlay(LO["trades"], LO["core"], LO["eq"], p, A, LO["end_core"])
                rb, ro = _row(ob), _row(oo)
                res["at"].setdefault(str(A), {}).setdefault(p, {})[e] = {"B4": rb, "O0": ro}
                res["delta"].setdefault(str(A), {}).setdefault(p, {})[e] = round(rb["cagr"] - ro["cagr"], 3)
                if e == "J" and A == DECIDE_SIZE and p == "P0":
                    res["yearly_J"] = {"B4": NT.yearly(ob["series"]), "O0": NT.yearly(oo["series"]),
                                       "B4_pre": NT.yearly(LB["eq"]), "O0_pre": NT.yearly(LO["eq"])}
    res["read"] = read(res["pre_delta"], res["delta"][str(DECIDE_SIZE)])
    res["elapsed_s"] = round(time.time() - t0)
    return res


def report(res: dict) -> str:
    f = NT._f
    A0 = str(DECIDE_SIZE)
    L = [f"# 税后看个股层：B4 vs 个股层关掉（O0）（登记检验；代码 {res['git']['rev']}{' + 未提交的改动' if res['git']['dirty'] else ''}）",
         "规则见 scripts/layer_tax_study.py 开头（先提交、只运行一次）；税的算法 = scripts/nisa_tax_study.py。今天的税制套到全部年代（假设）。非投资建议，也不是税务意见。", "",
         "## 一、¥100 万起（年化 / 最大回撤 · 期末）", "", "| 口径 | 账户 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 |", "|---|---|---|---|---|"]
    cell = lambda s: f"{f(s.get('cagr'))}% / {f(s.get('dd'))}% · {NT._yen(s.get('final'))}"  # noqa: E731
    for k in ("B4", "O0"):
        L.append(f"| 税前 | {k} | " + " | ".join(cell(res["pre"][e][k]) for e in ERAS) + " |")
    for p in POLICIES:
        for k in ("B4", "O0"):
            L.append(f"| 税后 {p} {NT.LABEL[p]} | {k} | " + " | ".join(cell(res["at"][A0][p][e][k]) for e in ERAS) + " |")
    L += ["", "## 二、个股层的贡献 Δ = B4 − O0（年化，pp）", "", "| 口径 | Z | E | J |", "|---|---|---|---|",
          "| 税前 | " + " | ".join(f"{res['pre_delta'][e]:+.2f}" for e in ERAS) + " |"]
    for A in SIZES:
        for p in POLICIES:
            L.append(f"| ¥{A // 10000:,} 万 税后 {p} | " + " | ".join(f"{res['delta'][str(A)][p][e]:+.2f}" for e in ERAS) + " |")
    r = res["read"]
    L += ["", "## 三、读法（事先写定）", "",
          f"- P0 税后还有贡献的年代：{'、'.join(r['positive']) or '无'}；没有贡献的：{'、'.join(r['nonpositive']) or '无'}",
          f"- 税前有、税后没有（这个年代的个股层只在税前有用）：{'、'.join(r['pre_only']) or '无'}",
          f"- NISA 能救回来（N3 / N1 下 Δ > 0）：" + ("；".join(f"{e}：{'、'.join(v)}" for e, v in r["rescue"].items()) or "无"),
          f"- **{'个股层税后三个年代都不比只拿核心好（要用户决定要不要缩小 / 关掉个股层或个股放 NISA）' if r['all_nonpositive'] else '个股层税后至少在一个年代比只拿核心好'}**",
          "- 只是读法：模拟盘 / 执行器不因这次研究改。", "",
          "## 四、税与换手（¥100 万、P0）", "", "| 年代 | B4 税合计 | O0 税合计 | B4 实现：个股 / 核心 | 核心买卖次数 B4 / O0（其中卖） |", "|---|---|---|---|---|"]
    for e in ERAS:
        b, o = res["at"][A0]["P0"][e]["B4"], res["at"][A0]["P0"][e]["O0"]
        lb, lo = res["ledger"][e]["B4"], res["ledger"][e]["O0"]
        L.append(f"| {e} | {NT._yen(b['tax_paid'])} | {NT._yen(o['tax_paid'])} | {NT._yen(b['real_stock'])} / {NT._yen(b['real_core'])} | "
                 f"{lb['core_trades']}（{lb['core_sells']}） / {lo['core_trades']}（{lo['core_sells']}） |")
    yj = res.get("yearly_J") or {}
    L += ["", "## 五、J 每年（%；¥100 万）", "", "| 年 | B4 税前 | O0 税前 | B4 税后 P0 | O0 税后 P0 |", "|---|---|---|---|---|"]
    for y in sorted((yj.get("B4_pre") or {}).keys()):
        L.append(f"| {y} | {f(yj['B4_pre'].get(y))} | {f(yj['O0_pre'].get(y))} | {f(yj['B4'].get(y))} | {f(yj['O0'].get(y))} |")
    L += ["", f"用时 {res.get('elapsed_s')} s。局限见脚本开头第七节。非投资建议、不是税务意见。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", required=True)
    ap.parse_args(argv)
    from qbreak import paths
    res = run()
    od = paths.out_dir()
    (od / OUT_MD).write_text(report(res), encoding="utf-8")
    (od / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
