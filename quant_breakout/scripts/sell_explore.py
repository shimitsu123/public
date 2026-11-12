"""sell_explore.py — 「卖出判定」横展开：探索（只用 E / J；Z 不碰，留给登记之后的一次确认）。2026-09-28。

用户（2026-09-28）：「类似 MACD 死叉的判定 还有哪些判定可以提高成功率」。
来由：现行交易 95〜100% 是 MACD 死叉出场，组合里胜率 42.0%（E / J）、每笔 +0.60 / +0.61%、盈亏比约 1.9；持有期最高点中位在第 6〜7 天、
  到卖出平均回吐 4.1〜4.6 pp（var/out/bsh_explore.md 第四节）→ 看别的「像死叉那样的判定」能不能卖在更好的位置、提高胜率，又不把赚钱的单子卖早。
规则（运行前写定；结果出来不改）：
一 变体：scripts/sell_common.VARIANTS（R 换判定 8 个、A 另外加 5 个、C 死叉要确认 2 个；每个只改「死叉」那一条，买点与其他卖法不变）。
二 窗口与组合：与 bsh_explore 相同（E = 2006-10〜2016-09，yfinance 今天的日経225；J = 2017-01〜2026-09，J-Quants 今天的日経225、真实一手；
   半段 E1 / E2、J1 / J2；S0C2 + W2，scripts/leap_confirm.py 同一框架）。核对：「死叉 ∨ 全 False」的变换必须与现行逐笔相同，否则停止。
三 入选规则（E、J 两个年代都满足；「胜率」= 组合里个股交易扣费后赚钱的比例，买入日落在窗口里的）：
   a 胜率 ≥ 现行 + 4 pp；b 每笔平均净收益 ≥ 现行；c 组合 Calmar ≥ 现行 − 0.01；d 最大回撤不比现行深 2 pp 以上；
   e 4 个半段（E1 / E2 / J1 / J2）里胜率低于现行的最多 1 个。
   排序：min(E, J 的胜率差) 从大到小；同一族（R / A / C）最多 2 个；最多 3 个。
   没有入选 → 这一轮不登记、不用 Z。入选的 → 另写一份登记（Z 确认的规则在看 Z 之前写定、提交）；模拟盘不因为这次探索改。
四 另报（只描述）：
   1 每个变体的胜率 / 每笔 / 平均赚亏 / 盈亏比 / 持有中位 / 出场原因、Calmar / 回撤 / 半段、只有核心的 Calmar；
   2「判定本身卖得准不准」：现行组合的每笔交易，从买入日起 60 个交易日里每个判定第一次成立的那天 t → 次日开盘卖的话：
     成立的比例、卖出后 10 个交易日（t + 11 的收盘）比卖出价低的比例（「卖对率」）、卖出后 10 日的平均涨跌、
     卖出价比现行实际卖出价高的比例与平均差；基准 = MACD 死叉本身、持有期里的每一天（「随便哪天卖」）。
输出：var/out/sell_explore.md / .json（只有统计）。
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
import sell_common as SC                                                    # noqa: E402
from qbreak import paths                                                    # noqa: E402

WIN_UP, CAL_TOL, DD_TOL, MAX_FINAL, MAX_FAM = 4.0, 0.01, 2.0, 3, 2
LOOK, FWD = 60, 10                                                          # 四-2：买入后 60 个交易日里第一次成立；卖出后 10 个交易日
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def summ(r: dict, era: str) -> dict:
    w = r[era]
    h1, h2 = r.get(f"{era}1") or {}, r.get(f"{era}2") or {}
    return {"calmar": w.get("calmar"), "cagr": w.get("cagr"), "dd": w.get("dd"), "n": w.get("n"), "mean": w.get("mean"), "win": w.get("win"),
            "halves": [h1.get("calmar"), h2.get("calmar")], "halves_win": [h1.get("win"), h2.get("win")]}


# ───────────────────────── 入选规则（有测试）─────────────────────────
def qualifies(c: dict, b: dict) -> list[str]:
    """c / b：{年代: summ}（候选 / 现行）。返回没满足的条件（空 = 入选）。"""
    f = []
    lows = 0
    ok = lambda x, y: x is not None and y is not None                                                   # noqa: E731
    for era in ("E", "J"):
        x, y = c.get(era) or {}, b.get(era) or {}
        if not (ok(x.get("win"), y.get("win")) and x["win"] >= y["win"] + WIN_UP):
            f.append(f"{era} 胜率没高 {WIN_UP:.0f} pp")
        if not (ok(x.get("mean"), y.get("mean")) and x["mean"] >= y["mean"]):
            f.append(f"{era} 每笔不如现行")
        if not (ok(x.get("calmar"), y.get("calmar")) and x["calmar"] >= y["calmar"] - CAL_TOL):
            f.append(f"{era} Calmar 低 {CAL_TOL} 以上")
        if not (ok(x.get("dd"), y.get("dd")) and x["dd"] >= y["dd"] - DD_TOL):
            f.append(f"{era} 回撤深 {DD_TOL:.0f} pp 以上")
        for hx, hy in zip(x.get("halves_win") or [None, None], y.get("halves_win") or [None, None]):
            if not (ok(hx, hy) and hx >= hy):
                lows += 1
    if lows > 1:
        f.append(f"半段胜率低于现行 {lows} 个")
    return f


def pick(res: dict, base: dict) -> list[str]:
    """按规则选 ≤ 3 个：min(E, J 的胜率差) 从大到小；同族 ≤ 2。"""
    ok = [k for k in res if not qualifies(res[k], base)]
    score = {k: min(res[k][e]["win"] - base[e]["win"] for e in ("E", "J")) for k in ok}
    out: list[str] = []
    fam: dict[str, int] = {}
    for k in sorted(ok, key=lambda x: (-score[x], x)):
        f = SC.VARIANTS[k]["fam"]
        if fam.get(f, 0) >= MAX_FAM:
            continue
        out.append(k)
        fam[f] = fam.get(f, 0) + 1
        if len(out) >= MAX_FINAL:
            break
    return out


# ───────────────────────── 四-2 判定本身卖得准不准（只描述，有测试）─────────────────────────
def judge_accuracy(fr: dict[str, pd.DataFrame], tr: pd.DataFrame, cache: dict, slip: float,
                   names: list[str] | None = None) -> dict[str, dict]:
    """tr：现行组合的交易（ticker / entry_date / exit_date / exit_px）。每个判定：买入日起 LOOK 个交易日里第一次成立的那天 t →
    次日开盘 ×(1 − 滑点) 卖：卖出后 FWD 个交易日（t + 1 + FWD 的收盘）比卖出价低 = 卖对。另算基准「持有期里的每一天」（到实际卖出前一天）。"""
    names = names or SC.SIGNALS
    acc = {k: {"fire": 0, "right": [], "fwd": [], "vs_exit": []} for k in [*names, "_every_day"]}
    n_tr = 0
    for r in tr.itertuples():
        df = fr.get(r.ticker)
        if df is None:
            continue
        ix = df.index
        i0 = int(ix.searchsorted(pd.Timestamp(r.entry_date)))
        i_exit = int(ix.searchsorted(pd.Timestamp(r.exit_date)))
        if i0 >= len(ix) or ix[i0] != pd.Timestamp(r.entry_date):
            continue
        n_tr += 1
        S = cache.get(r.ticker)
        if S is None:
            S = cache[r.ticker] = SC.signals(df)
        o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)

        def one(key: str, t: int) -> None:
            if t + 1 + FWD >= len(ix):
                return
            px = o[t + 1] * (1 - slip)
            a = acc[key]
            a["fwd"].append((c[t + 1 + FWD] / px - 1) * 100)
            a["right"].append(c[t + 1 + FWD] < px)
            a["vs_exit"].append((px / float(r.exit_px) - 1) * 100)
        hi = min(i0 + LOOK, len(ix))
        for k in names:
            hit = np.flatnonzero(S[k][i0:hi])
            if len(hit):
                acc[k]["fire"] += 1
                one(k, i0 + int(hit[0]))
        for t in range(i0, min(i_exit, len(ix))):
            one("_every_day", t)
    out = {}
    for k, a in acc.items():
        m = len(a["fwd"])
        out[k] = {"trades": n_tr, "fire_pct": round(a["fire"] / n_tr * 100, 1) if n_tr and k != "_every_day" else None, "n": m,
                  "right_pct": round(float(np.mean(a["right"])) * 100, 1) if m else None,
                  "fwd_mean": round(float(np.mean(a["fwd"])), 2) if m else None,
                  "higher_pct": round(float(np.mean(np.array(a["vs_exit"]) > 0)) * 100, 1) if m and k != "_every_day" else None,
                  "vs_exit_mean": round(float(np.mean(a["vs_exit"])), 2) if m and k != "_every_day" else None}
    return out


def fmt_line(k: str, s: dict, pr: dict, base: dict | None) -> str:
    d = (lambda e, f: f"{s[e][f] - base[e][f]:+.1f}" if f == "win" else f"{s[e][f] - base[e][f]:+.3f}") if base else (lambda e, f: "—")
    tp = pr.get("E") or {}, pr.get("J") or {}
    return (f"| {k} | {s['E']['win']}% / {s['J']['win']}% | {d('E', 'win')} / {d('J', 'win')} | {s['E']['mean']}% / {s['J']['mean']}% | "
            f"{s['E']['calmar']} / {s['J']['calmar']} | {d('E', 'calmar')} / {d('J', 'calmar')} | {s['E']['dd']}% / {s['J']['dd']}% | "
            f"{s['E']['halves_win'][0]} · {s['E']['halves_win'][1]} · {s['J']['halves_win'][0]} · {s['J']['halves_win'][1]} | "
            f"{s['E']['n']} / {s['J']['n']} 笔 | "
            + " / ".join(f"{x['payoff']:.2f}" if x.get("payoff") else "—" for x in tp) + " | "
            + " / ".join(f"{x['hold']:.0f}" if x.get("n") else "—" for x in tp) + " |")


def main() -> int:
    import bsh_common as BC
    import leap_common as LC
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.config import ExecConfig
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    slip = ExecConfig.for_market("JP", "tachibana").slippage_pct / 100
    say(f"# 卖出判定 横展开：探索（只用 E / J；{pd.Timestamp.today().date()}）")
    say("规则见 scripts/sell_explore.py 开头（运行前写定）；判定定义 scripts/sell_common.py。组合 = S0C2 + W2，今天的日経225；每个变体只改「死叉」那一条。")
    res: dict[str, dict] = {}
    prof: dict[str, dict] = {}
    base: dict = {}
    core: dict = {}
    accu: dict = {}
    for era in ("E", "J"):
        t1 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        a, b = ctx["windows"][era]
        cache: dict = {}
        r0 = LF.run(ctx, run_fn, fw, p)
        tr0 = BC.last_trades(a, b)
        LC.assert_explore_dates(tr0["entry_date"])                          # 探索只准用 2006-10 以后（Z 留给确认）
        base[era] = summ(r0, era)
        rn = LF.run(ctx, run_fn, SC.exit_transform(fw, "_neutral", cache), p)
        trn = BC.last_trades(a, b)
        same = summ(rn, era) == base[era] and len(trn) == len(tr0) and np.allclose(trn["net"].to_numpy(float), tr0["net"].to_numpy(float))
        say(f"- {era} 核对（死叉 ∨ 全 False 的变换）：{'与现行完全相同' if same else '★ 不同 —— 停止'}")
        if not same:
            raise SystemExit(f"{era} 核对不一致：{summ(rn, era)} vs {base[era]}")
        prof.setdefault("现行", {})[era] = BC.trade_profile(tr0)
        core[era] = summ(LF.run(ctx, run_fn, LF.no_entries(fw), p), era)
        for k in SC.VARIANTS:
            r = LF.run(ctx, run_fn, SC.exit_transform(fw, k, cache), p)
            res.setdefault(k, {})[era] = summ(r, era)
            prof.setdefault(k, {})[era] = BC.trade_profile(BC.last_trades(a, b))
        accu[era] = judge_accuracy(fw, tr0, cache, slip)
        say(f"- {era}：{len(SC.VARIANTS) + 3} 次组合回测，{round(time.time() - t1)} s")
    say("\n## 一、全部变体（E / J；差 = 变体 − 现行；半段胜率 = E1 · E2 · J1 · J2）")
    say("| 变体 | 胜率 E / J | 胜率差 pp | 每笔 E / J | Calmar E / J | Calmar 差 | 最大回撤 E / J | 半段胜率 | 笔数 | 盈亏比 | 持有中位（天）|")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    say(fmt_line("现行", base, prof["现行"], None))
    for k in SC.VARIANTS:
        say(fmt_line(k, res[k], prof[k], base))
    say(f"\n只有核心（不买个股）：Calmar {core['E']['calmar']} / {core['J']['calmar']}")
    say("\n变体说明：" + "；".join(f"{k} {v['zh']}" for k, v in SC.VARIANTS.items()))
    say("\n## 二、入选规则（运行前写定）")
    rows = {k: qualifies(res[k], base) for k in SC.VARIANTS}
    for k, f in rows.items():
        say(f"- {k}：{'入选' if not f else '不入选：' + '；'.join(f)}")
    fin = pick(res, base)
    say(f"\n**入选（按规则，最多 3 个）：{('、'.join(fin)) if fin else '没有'}**" + ("" if fin else " → 这一轮不登记、不用 Z。"))
    say("\n## 三、出场原因、平均赚亏（现行与各变体）")
    for k in ["现行", *SC.VARIANTS]:
        for era in ("E", "J"):
            x = prof[k][era]
            if x.get("n"):
                say(f"- {k} {era}：平均赚 {x['avg_win']:+.2f}% / 平均亏 {x['avg_loss']:+.2f}%、每笔中位 {x['median']:+.2f}%；出场 "
                    + "、".join(f"{a_} {b_:.0f}%" for a_, b_ in x["reasons"].items()))
    say(f"\n## 四、判定本身卖得准不准（只描述；现行组合的每笔交易，买入后 {LOOK} 个交易日里第一次成立 → 次日开盘卖）")
    say(f"卖对率 = 卖出后 {FWD} 个交易日的收盘比卖出价低的比例；「持有期里的每一天」= 随便哪天卖的基准。")
    say("| 判定 | 成立的比例 E / J | 卖对率 E / J | 卖出后 10 日平均 E / J | 卖价高于现行实际卖价的比例 E / J | 与现行卖价的平均差 E / J |")
    say("|---|---|---|---|---|---|")
    lab = {v["sig"]: f"{k} {v['zh'].split('代替')[0].replace('死叉照旧 + ', '').replace('也卖', '')}" for k, v in SC.VARIANTS.items()}
    lab.update({"dead_cross": "MACD 死叉（现行）", "_every_day": "持有期里的每一天（基准）"})
    for k in ["dead_cross", "_every_day", *[v["sig"] for v in SC.VARIANTS.values() if v["mode"] != "and"]]:
        e, j = accu["E"].get(k) or {}, accu["J"].get(k) or {}
        f = lambda d, x, suf="": "—" if d.get(x) is None else f"{d[x]}{suf}"                           # noqa: E731
        say(f"| {lab.get(k, k)} | {f(e, 'fire_pct', '%')} / {f(j, 'fire_pct', '%')} | {f(e, 'right_pct', '%')} / {f(j, 'right_pct', '%')} | "
            f"{f(e, 'fwd_mean', '%')} / {f(j, 'fwd_mean', '%')} | {f(e, 'higher_pct', '%')} / {f(j, 'higher_pct', '%')} | "
            f"{f(e, 'vs_exit_mean', '%')} / {f(j, 'vs_exit_mean', '%')} |")
    out = {"base": base, "core": core, "variants": res, "profiles": prof, "accuracy": accu, "qualify": rows, "finalists": fin,
           "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {out['elapsed_s']} s）。探索，只描述；非投资建议。")
    fp = paths.out_dir() / "sell_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
