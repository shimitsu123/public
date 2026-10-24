"""judgment_layer_study.py — 待办〔71〕③：模拟盘的「判断层」（市场风险报告：避险 → 新仓 ×0、减仓观察 → ×0.5）放进 B4 账户，对个股层到底有没有好处
（2026-10-24 登记 = 本提交；之后不改、只运行一次）。

用户（2026-10-24）：「结合上述的回答的问题进行对应的最优修改」—— 复核里排第一的方法问题：判断层在模拟盘 / 实盘里一直生效（run.py _plan_inputs：
scale = reg.mult，含 overlay_mult），但回测里没有（qbreak/regime.py 开头写明）；2026-09-29〜10-22 的报告约 14 / 19 个交易日是「避险」，
新仓一直 ×0。2026-10-06 的检验（scripts/report_judgment_backtest.py，登记 79be1b5）只看了指数：避险之后 20 日内跌 5% 更常见（V2 准），
但方向不准（V1）、按状态拿指数不比一直拿着好（V3）；当时写明「判断层对个股层到底有没有好处（放进 B4 账户比）这次没检验」（HANDOFF〔71〕③）。
看过的（照实写）：上面指数层面的结果、最近的报告多是避险；没看过的：B4 账户加上判断层之后的任何数字 → posthoc = None（不是看了账户结果才定的组合；S7 不适用）。

〇 基准 B4 = B3 + TBF（loop9_common.tick_of 的 TBF em_tick；先决条件同 core_bullmix_study：规则指纹 + B4 重算 = kshape_link_study.B4_PREP，不满足就停）。
一 判断层的历史重现 = report_judgment_backtest.build 的日本状态 st_jp（红线 J1 汇率 / J2 日债 / J3 指数 / J4 半导体 / J5 广度 + 大卖周，
   核心红线 J1 / J2；避险 = 红线 ≥ 2 条且其中有核心红线；只用当时已知的数据；规则、阈值原样 import，不在这里改）。
   模拟盘 var/market_regime.json 的「JP」= 报告对日本的行动，晚报写在东证收盘之后 → 东证日 t 的状态管信号日 t 的新仓（第二天开盘成交），同模拟盘。
二 候选（倍数 = qbreak/regime.ACTION_MULT 原样：避险 0、减仓观察 0.5、观望 / 加仓观察 1；乘在那个信号的新仓倍数上，TBF 挡的照旧 0）：
   JL  = 日本状态 st_jp（主候选，判定）。
   只描述（不判定）：JLT = 报告的总行动 st_all（日本与它之前最后一个美国交易日的状态取更严的）；JL0 = 只有避险 → 0（减仓观察不减）。
三 判定（事先写定）：
   第一关 = research_loop2.stage1（S1 三个年代 Calmar 差合计 ≥ +0.03、S2 每个年代 ≥ −0.02、S3 最大回撤不深 2 pp 以上、S4 前后两半合计都 ≥ 0；
   S5 不适用（不改选股）、S6 不适用（不学参数）、S7 不适用（posthoc = None））。
   第二关（不管第一关过不过都算，供读法用）：st_jp 在 2000-01-04 起的东证日上整体循环平移 k（research_loop10.shift_ks，平移 ≥ 250 日，种子 0〜PLACEBO_N−1），
   每个种子三个年代的 Calmar 差合计（同一个 B4 基准）→ 分布。
   读法（只描述，不改模拟盘）：
   - 「判断层对个股层有用」= 第一关全过 且 JL 的合计 > 随机平移的 95 分位；
   - 「判断层让账户变差」= JL 的合计 ≤ −0.03；另写「而且时点比随机还差」（合计 < 随机平移的 5 分位）或「差在挡掉的量，不在时点」（≥ 5 分位）；
   - 其余 =「看不出作用」。
   任何读法都不改模拟盘 / 执行器 / 判断层：要不要停用或改判断层由用户决定（〔71〕的选项），并记 sim_changes。
四 只描述：各年代 st_jp 各状态的天数比例、被挡（×0）/ 减半（×0.5）的信号个数（不含 TBF 已挡的）、个股笔数 / 胜率；
   模拟盘 var/market_regime.json 的 git 历史里报告的 JP 行动（2026-09-29 起每天最后一版）与同一天的重现状态（数据够的日子）。
五 事前预期（看结果之前）：判断层多挡的是高波动的日子，以前「按日子挡」的研究（第九 / 十个循环 kind = date）大多第一关不过；
   B4 的个股层每年只有几笔、占权益约 1 成 → 账户差多半很小（合计 ±0.03 以内的可能约 60%），「有用」约 10%，「变差」约 30%。
六 局限：重现是把报告的红线机械化的近似（同 report_judgment_backtest 第八节）；实际报告是每天人工 / AI 综合判断，最近避险的频率（约 14 / 19 天）
   比重现的历史频率（J 年代约 18%）高得多 → 本研究回答的是「按这套红线的判断层」，不是「最近这样频繁避险的判断层」；日経225 成分用今天的名单；税前。
运行：python scripts/judgment_layer_study.py --run（只运行一次；输出已存在就拒绝）→ var/out/judgment_layer_study.md / .json。非投资建议。
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

ERAS = ("Z", "E", "J")
OUT = "judgment_layer_study"
POSTHOC = None
PRIMARY = "JL"
DESCRIBE = ("JLT", "JL0")
PLACEBO_N = 200
PLACEBO_FROM = "2000-01-04"
HARM = -0.03
LIVE_FROM = "2026-09-29"
KEYS = ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")


# ───────────────────────── 规则（纯函数；tests/test_judgment_layer_study.py） ─────────────────────────
def mult_of(state: str, kind: str = "JL") -> float:
    """状态 → 新仓倍数（qbreak/regime.ACTION_MULT 原样；JL0 = 只有避险 → 0）。"""
    from qbreak.regime import ACTION_MULT
    m = float(ACTION_MULT.get(str(state), 1.0))
    if kind == "JL0":
        return 0.0 if m <= 0 else 1.0
    return m


def state_on(dates, state: pd.Series, default: str = "观望") -> list[str]:
    """信号日 → 那天（或之前最后一个东证日）的状态；比序列还早 → default。"""
    s = state.sort_index()
    idx = s.index
    out = []
    for d in pd.to_datetime(np.asarray(dates)):
        i = idx.searchsorted(d, side="right") - 1
        out.append(str(s.iloc[i]) if i >= 0 else default)
    return out


def ticks_with(base: dict, tickers, dates, states: list[str], kind: str = "JL") -> tuple[dict, int, int]:
    """B4 的 em_tick（TBF 挡的 = 0）+ 判断层的倍数 → 新的 em_tick、多挡（×0）的个数、减半的个数（都不含 TBF 已挡的）。"""
    out = dict(base)
    n0 = nh = 0
    for t, d, s in zip(tickers, pd.to_datetime(np.asarray(dates)), states):
        key = (str(t), pd.Timestamp(d))
        if key in base and float(base[key]) <= 0:
            continue
        f = mult_of(s, kind)
        if f >= 1.0:
            continue
        out[key] = float(base.get(key, 1.0)) * f
        if f <= 0:
            n0 += 1
        else:
            nh += 1
    return out, n0, nh


def shift_state(state: pd.Series, k: int) -> pd.Series:
    """状态序列整体循环平移 k 个交易日（np.roll；日子不动）。"""
    return pd.Series(np.roll(state.to_numpy(), int(k)), index=state.index)


def pct(xs, q: float) -> float | None:
    v = [float(x) for x in xs if x is not None and np.isfinite(x)]
    return float(np.percentile(v, q)) if v else None


def verdict(s1: dict, total: float | None, pl: list) -> str:
    """三的读法。"""
    p95, p05 = pct(pl, 95), pct(pl, 5)
    if total is None:
        return "算不出"
    if s1.get("ok") and p95 is not None and total > p95:
        return "判断层对个股层有用"
    if total <= HARM:
        if p05 is not None and total < p05:
            return "判断层让账户变差（而且时点比随机还差）"
        return "判断层让账户变差（差在挡掉的量，不在时点）"
    return "看不出作用"


def state_share(state: pd.Series, a, b) -> dict:
    """[a, b) 里各状态的天数比例（%）。"""
    s = state[(state.index >= pd.Timestamp(a)) & (state.index < pd.Timestamp(b))]
    if s.empty:
        return {}
    vc = s.value_counts(normalize=True) * 100
    return {str(k): round(float(v), 1) for k, v in vc.items()}


def live_actions(root: Path, since: str = LIVE_FROM) -> dict:
    """var/market_regime.json 的 git 历史 → {日期 as_of: 报告的 JP 行动}（同一天多版取最后一版）。"""
    rel = "quant_breakout/var/market_regime.json"
    try:
        revs = subprocess.run(["git", "-C", str(root), "log", "--format=%H", f"--since={since}", "--", rel],
                              capture_output=True, text=True).stdout.split()
    except Exception:                                                        # noqa: BLE001
        return {}
    out: dict = {}
    for h in reversed(revs):
        try:
            d = json.loads(subprocess.run(["git", "-C", str(root), "show", f"{h}:{rel}"], capture_output=True, text=True).stdout)
        except Exception:                                                    # noqa: BLE001
            continue
        a = str(d.get("as_of") or "")[:10]
        act = str((d.get("JP") or {}).get("action") or "")
        if a and act:
            out[a] = act
    return dict(sorted(out.items()))


# ───────────────────────── 运行 ─────────────────────────
def git_info() -> dict:
    root = Path(__file__).resolve().parents[2]
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "quant_breakout/scripts", "quant_breakout/qbreak"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def run(say=print) -> dict:
    import jq_study as JS
    import kshape_link_study as KS
    import loop6_common as L6
    import loop9_common as C9
    import loop10_common as C10
    import report_judgment_backtest as RJ
    import research_loop2 as R2
    import research_loop10 as R10
    import trendline_study as TS
    t0 = time.time()
    W = C10.load()
    say(f"载入：{time.time() - t0:.0f}s")
    tbf, _ = TS.tbf_gates(W, say)
    pre = KS.prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit("先决条件不满足 → 停")
    B = RJ.build(RJ.load_inputs(say))
    st = {"JL": B["st_jp"], "JLT": B["st_all"], "JL0": B["st_jp"]}
    say(f"判断层重现：日本到 {B['ends']['n225']}（{time.time() - t0:.0f}s）")
    S = {e: C9.signals(W, e) for e in ERAS}
    base_t = {e: C9.tick_of(S[e]["ticker"], S[e]["date"], tbf[e]) for e in ERAS}

    def acct(e: str, tick: dict) -> dict:
        r = L6.run(W, e, em_tick=tick) if tick else L6.run(W, e)
        _ = JS.RealLotEngine.LAST[-1]
        return {**{k: r.get(k) for k in KEYS}, "years": r.get("years")}

    base = {e: acct(e, base_t[e]) for e in ERAS}
    same = {e: KS.same_prep(base[e], KS.B4_PREP[e]) for e in ERAS}
    if not all(same.values()):
        raise SystemExit(f"B4 重算 ≠ 登记值 → 停：{same}")
    say(f"B4 基准（{time.time() - t0:.0f}s）")

    def cand_of(kind: str, state: pd.Series) -> tuple[dict, dict]:
        c, cnt = {}, {}
        for e in ERAS:
            tk, n0, nh = ticks_with(base_t[e], S[e]["ticker"], S[e]["date"], state_on(S[e]["date"], state), kind)
            c[e] = acct(e, tk)
            cnt[e] = {"blocked": n0, "halved": nh, "signals": int(len(S[e]))}
        return c, cnt

    res: dict = {"study": OUT, "git": git_info(), "posthoc": POSTHOC, "prereq": {k: v for k, v in pre.items() if k != "base"},
                 "b4_same": same, "base": base, "ends": B["ends"], "cands": {}}
    for kind in (PRIMARY,) + DESCRIBE:
        c, cnt = cand_of(kind, st[kind])
        s1 = R2.stage1(c, base, posthoc=POSTHOC)
        res["cands"][kind] = {"acct": c, "counts": cnt, "stage1": s1}
        say(f"{kind}：合计 {s1['sum']}（{time.time() - t0:.0f}s）")

    # 第二关：JL 的状态序列循环平移
    sj = st[PRIMARY]
    sj = sj[sj.index >= pd.Timestamp(PLACEBO_FROM)]
    ks = R10.shift_ks(len(sj), range(PLACEBO_N))
    pl = []
    for i, k in enumerate(ks):
        c, _ = cand_of(PRIMARY, shift_state(sj, k))
        pl.append(R2.stage1(c, base, posthoc=POSTHOC)["sum"])
        if (i + 1) % 20 == 0:
            say(f"平移 {i + 1} / {PLACEBO_N}（{time.time() - t0:.0f}s）")
    tot = res["cands"][PRIMARY]["stage1"]["sum"]
    res["placebo"] = {"n": PLACEBO_N, "sums": pl, "p05": pct(pl, 5), "p50": pct(pl, 50), "p95": pct(pl, 95),
                      "rank_pct": None if tot is None else round(float(np.mean([x < tot for x in pl if x is not None]) * 100), 1)}
    res["verdict"] = verdict(res["cands"][PRIMARY]["stage1"], tot, pl)
    shares = {}
    for e in ERAS:
        a, b = TS._win(*W["ctx"][e]["windows"][e])
        shares[e] = {k: state_share(st[k], a, b) for k in ("JL", "JLT")}
    res["shares"] = shares
    live = live_actions(Path(__file__).resolve().parents[2])
    res["live"] = [{"date": d, "report": a, "recon": (state_on([d], st[PRIMARY])[0] if pd.Timestamp(d) <= st[PRIMARY].index[-1] else None)}
                   for d, a in live.items()]
    res["elapsed_s"] = round(time.time() - t0)
    return res


def _f(v, f="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def report(res: dict) -> str:
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    B = res["base"]
    c0 = res["cands"][PRIMARY]
    s = c0["stage1"]
    pl = res["placebo"]
    L = [f"# 判断层（市场风险报告的避险 / 减仓观察）放进 B4 账户（待办〔71〕③；JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/judgment_layer_study.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件 {res['prereq'].get('ok')}；B4 = 登记值 {all(res['b4_same'].values())}；"
         f"数据到 日経 {res['ends'].get('n225')}、USD/JPY {res['ends'].get('usdjpy')}、JGB10Y {res['ends'].get('jgb10y')}；用时 {res['elapsed_s']} s。", "",
         f"**读法：{res['verdict']}**", "",
         f"- JL（日本状态，主候选）：S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；"
         f"第一关 {yn(s['ok'])}（S5 / S6 / S7 不适用）",
         f"- 随机平移 {pl['n']} 次的合计：5 分位 {_f(pl['p05'])}、中位 {_f(pl['p50'])}、95 分位 {_f(pl['p95'])}；JL 比 {_f(pl['rank_pct'], '{:.1f}')}% 的随机好", ""]
    for k in DESCRIBE:
        x = res["cands"][k]["stage1"]
        L.append(f"- 只描述 {k}（{'报告的总行动：日本与美国取更严的' if k == 'JLT' else '只有避险 → 0'}）：合计 {_f(x['sum'])}（"
                 + " / ".join(f"{e} {_f(x['d'][e])}" for e in ERAS) + "）")
    L += ["", "| 年代 | B4 年化 / 最大回撤 / Calmar / 笔数 / 胜率 | " + " | ".join(f"{k}（Calmar 差）" for k in res["cands"]) + " |",
          "|---|---|" + "---|" * len(res["cands"])]
    cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')} / "      # noqa: E731
                      f"{x.get('n')} 笔 / {_f(x.get('win'), '{:.1f}')}%")
    for e in ERAS:
        L.append(f"| {e} | {cell(B[e])} | " + " | ".join(f"{cell(c['acct'][e])}（{_f(c['stage1']['d'][e])}）" for c in res["cands"].values()) + " |")
    L += ["", "只描述（不参与判定）："]
    for e in ERAS:
        sh = res["shares"][e]
        L.append(f"- {e}：日本状态的天数比例 " + "、".join(f"{k} {v}%" for k, v in sh["JL"].items())
                 + "；总行动 " + "、".join(f"{k} {v}%" for k, v in sh["JLT"].items())
                 + "；JL 多挡 / 减半的信号 " + f"{c0['counts'][e]['blocked']} / {c0['counts'][e]['halved']}（共 {c0['counts'][e]['signals']} 个信号）")
    if res.get("live"):
        L.append("- 模拟盘用的报告（JP 行动）vs 同一天的重现：" + "；".join(
            f"{x['date'][5:]} {x['report']} / {x['recon'] or '数据未到'}" for x in res["live"]))
    L += ["", "不改模拟盘 / 执行器 / 判断层；要不要停用或改判断层由用户决定（〔71〕），并记 sim_changes。非投资建议。"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    from qbreak import paths
    ap = argparse.ArgumentParser(description="判断层放进 B4 账户（〔71〕③）")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 0
    out = paths.out_dir()
    if (out / f"{OUT}.json").exists():
        print(f"{OUT}.json 已存在 → 只运行一次，不再运行")
        return 1
    res = run()
    text = report(res)
    print(text)
    (out / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (out / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
