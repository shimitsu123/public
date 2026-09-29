"""fwd_judgment_check.py — 前向记录判断层（qbreak/fwd_judgment.py）的市场层放在历史上会怎样（2026-09-29 登记；只跑一次，看完不改规则）。

用户（2026-09-29）：「威胁高 + 压力已释放加进现在模拟盘选股的策略判断」「现在的前向记录的东西都加入模拟盘选股的判断」。
用户已经决定加进模拟盘 → 这里不是「过不过」的门槛，只是事先写定的历史检验，结果照实报告（交易规则按用户的决定照样加）。
规则 = qbreak/fwd_judgment.py 开头（同一次提交写定）。

零 账户：与 scripts/stack_study.py 的 V0 相同（S0C2 + W2：日経225 突破 4 个名额 × 25%、闲置资金买 1655、T0、立花费用、
   新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜）；判断层（风险报告）与 HALT 没有历史，不在里面。窗口 E 2006-10〜2016-09、J 2017-01〜；Z 2001〜2006-09 只描述。
一 方案（日本个股新仓再乘一个「成交日」倍数 = 信号日收盘时的判定挪到下一个交易日；与原有倍数的合成照引擎：相乘后不超过 1）：
   V0 现行；
   MC 只加 A1（C_rel 日経 ≥ 自身历史 80 分位 → 2 分 → ×0.5）；
   MA 整个市场层（A1〜A6 与深跌抵消 → n = 0 / 1 / ≥2 → ×1 / ×0.75 / ×0.5）。
   读数：qbreak/fwd_judgment.market_history（与实时同一个函数）；A5 K4 用 scripts/energy_study 的 month_factor（同一个 θ −4.626、
   同一套 JODI 数据与公布时滞）；W（美股前瞻）2006-11 才有值、K4 在 JODI 有数据之后才有值 → 之前记 0。
   注意（照实写）：引擎里原有的新仓倍数与这一层是相乘（回测框架的 em_scale），实时模拟盘是取 min —— 两者只在两层同时 < 1 时不同，
   这里按相乘算，结果会比实时略保守。
二 报告（不是门槛）：各窗口 年化 / 最大回撤 / Calmar、个股交易笔数、倍数 < 1 的成交日比例、被跳过的原因（名额满 / 买不起一手 / 宏观）。
   读法（事先写定）：E 与 J 的 Calmar 都比 V0 高 ≥ 0.02 →「历史上有帮助」；都低 ≥ 0.02 →「历史上有害（建议你重新考虑）」；其余「差不多」。
三 个股层（B1〜B7）不做历史检验：多数输入是在同一段历史上挑出来的（F2、K2、USW、时代主线、S2），G1 的事件表、X2 的逐季短観
   在历史上做不全；而且现行账户的个股名额几乎从不满（E 窗口 108 笔里只有 1 次因名额满跳过）→ 排序几乎不起作用，
   s < 0 减半的效果留给「基准账户」（实时对照）去量。
输出：var/out/fwd_judgment_check.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import fwd_judgment as FJ                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

TAGS = ("E", "J", "Z")
JUDGE = ("E", "J")
GAIN = 0.02
K4_THETA = -4.626


def k4_on_series(days: pd.DatetimeIndex) -> pd.Series:
    """K4 成立（信号日收盘时）：energy_study 的 month_factor（θ −4.626）< 1。取不到 → 全部 False。"""
    import energy_study as ES
    from qbreak import energy_demand as E
    try:
        raw = E.load_all()
        months = pd.DatetimeIndex(pd.Series(days, index=days).groupby(days.to_period("M")).tail(1).index)
        sig = E.signals(raw, months)[3]["jp_total"]
        f = ES.month_factor(sig, K4_THETA, pd.DatetimeIndex(days))
        return pd.Series(f.to_numpy() < 1.0, index=days)
    except Exception as e:                                                  # noqa: BLE001
        print(f"K4 历史取不到：{type(e).__name__}: {e}", flush=True)
        return pd.Series(False, index=days)


def daily_mults(H: pd.DataFrame, k4: pd.Series) -> pd.DataFrame:
    """每个日本交易日（信号日收盘）的判定：MC 与 MA 的倍数、MA 的分数。"""
    rows = []
    for d, r in H.iterrows():
        items = FJ.market_items(r.to_dict(), bool(k4.get(d, False)))
        n, m = FJ.market_mult(items)
        mc = 0.5 if items.get("A1") else 1.0
        rows.append({"date": d, "MC": mc, "MA": m, "n": n, **{k: bool(v) if v is not None else False for k, v in items.items()}})
    return pd.DataFrame(rows).set_index("date")


def fill_scale(factor: pd.Series, g: pd.DatetimeIndex) -> pd.Series:
    """信号日收盘时的倍数 → 下一个交易日（g 上）成交的新仓倍数（scripts/combo_study.fill_scale 同一写法）。"""
    f = factor.sort_index()
    f = f.reindex(f.index.union(g)).ffill().reindex(g)
    return f.shift(1).fillna(1.0)


def reading(acct: dict, v: str) -> str:
    d = [acct[t][v]["calmar"] - acct[t]["V0"]["calmar"] for t in JUDGE]
    if all(x >= GAIN - 1e-12 for x in d):
        return "历史上有帮助"
    if all(x <= -GAIN + 1e-12 for x in d):
        return "历史上有害（建议你重新考虑）"
    return "差不多"


def main() -> int:
    import leap_confirm as LF
    import madev_event as ME
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    H = FJ.market_history()
    k4 = k4_on_series(H.index)
    M = daily_mults(H, k4)
    print(f"市场层读数 {H.index[0].date()}〜{H.index[-1].date()}（{time.time() - t0:.0f}s）", flush=True)
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    acct, share, extra = {}, {}, {}
    for tag in TAGS:
        S = ME.load_sample(tag, p0)
        ctx = S["ctx"]
        run_fn = LF.runner(ctx, S["fa"])
        fw = LF.with_mask(S["fa"], S["keep"])
        a, b = ctx["windows"][tag]
        g = pd.DatetimeIndex(ctx["days"])
        acct[tag], share[tag], extra[tag] = {}, {}, {}
        for v in ("V0", "MC", "MA"):
            kw = {} if v == "V0" else {"em_scale": fill_scale(M[v], g)}
            r = LF.run(ctx, run_fn, fw, p, **kw)
            acct[tag][v] = {x: r[tag][x] for x in ("cagr", "dd", "calmar", "n", "mean", "win")}
            eng = __import__("jq_study").RealLotEngine.LAST[-1]
            extra[tag][v] = {k: int(eng.skipped.get(k, 0)) for k in ("full", "lot", "macro", "cash")}
            if v != "V0":
                sc = fill_scale(M[v], g)
                w = (g >= pd.Timestamp(a)) & ((g < pd.Timestamp(b)) if b else True)
                share[tag][v] = {"lt1": round(float((sc[w] < 1).mean() * 100), 1), "half": round(float((sc[w] <= 0.5).mean() * 100), 1)}
        print(f"{tag} 完成（{time.time() - t0:.0f}s）", flush=True)
    rd = {v: reading(acct, v) for v in ("MC", "MA")}
    names = {"V0": "现行", "MC": "只加 C_rel（威胁高 + 压力已释放）", "MA": "整个市场层（A1〜A6、深跌抵消）"}
    L = ["# 前向记录判断层：市场层放在历史上会怎样（2026-09-29 登记，只跑一次；规则见 qbreak/fwd_judgment.py 与本脚本开头）", "",
         "用户已决定加进模拟盘 → 不是门槛，只报告。读法（事先写定）：" + "；".join(f"{names[k]} **{v}**" for k, v in rd.items()), "",
         "| 方案 | " + " | ".join(f"{t} 年化 / 最大回撤 / Calmar / 个股笔数" for t in TAGS) + " |", "|---|" + "---|" * len(TAGS)]
    for v in names:
        L.append(f"| {v} {names[v]} | " + " | ".join(
            f"{acct[t][v]['cagr']:+.2f}% / {acct[t][v]['dd']:.2f}% / {acct[t][v]['calmar']:.3f} / {acct[t][v]['n']}" for t in TAGS) + " |")
    L += ["", "倍数 < 1 的成交日比例（×0.5 的比例）：" + "；".join(
        f"{t} " + "、".join(f"{v} {share[t][v]['lt1']}%（{share[t][v]['half']}%）" for v in ("MC", "MA")) for t in TAGS),
          "被跳过（名额满 / 买不起一手 / 宏观 / 现金）：" + "；".join(
        f"{t} " + "、".join(f"{v} {extra[t][v]['full']} / {extra[t][v]['lot']} / {extra[t][v]['macro']} / {extra[t][v]['cash']}" for v in names) for t in TAGS),
          "", "各项在历史上警示的比例（日本交易日，2006-10 起）：" + "、".join(
        f"{k} {M.loc[M.index >= '2006-10-01', k].mean() * 100:.0f}%" for k in ("A1", "A2", "A3", "A4", "A5", "A6", "A+")),
          "", "个股层（B1〜B7）不做历史检验（见脚本开头第三节）；实时由基准账户对照。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "fwd_judgment_check"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"reading": rd, "accounts": acct, "share": share, "skipped": extra,
                                              "warn_share": {k: round(float(M.loc[M.index >= '2006-10-01', k].mean() * 100), 1)
                                                             for k in ("A1", "A2", "A3", "A4", "A5", "A6", "A+")}},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
