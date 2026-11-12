"""buyq_study.py — 买点信号质量：「新角度」一轮（探索 + 一次确认；2026-09-28 登记，登记之后才运行一次）。

用户（2026-09-28）：「继续探索买点信号质量」（上一轮结论：想让胜率和每笔一起提高，只能靠买点本身的质量；现在在用的只有 W2）。
已经做过、这一轮不重复的（var/out/research_map.md「选股/买点」）：突破日量比 / 周线量比（W2 采用、V1〜V4、M1〜M3）、质量分 F1〜F5、
  决算 / 供需 / 信用 / 自社株（E1〜E3、N1〜N5）、β / 相关（K2 前向记录）、行情 / 宏观 / 宽度 / VIX（时代依赖）、K 线形态 267 组、多周期 R1、
  52 周高点 / 布林收缩 / 长期趋势 / 真突破（signal_study E1〜E4）、MACD 零轴 / 次日确认 / 首次信号（bsh_explore B1〜B7）、
  S6 / S7 的 45 个指标（业种强弱、收盘位置 clv、突破前量 vtrend、跳空、corr60 …）、仓位 P0〜P7、全部因子机器学习 K1〜K5。
这一轮只看以前没测过的四类「突破的质地」（scripts/buyq_common.VARIANTS，阈值取自然值，不调）：
  A 个股性格：Q1 趋势性（方差比）、Q2 放量上涨之后有没有跟进、Q3 大盘跌日抗不抗跌；
  B 箱体结构：Q4 低点抬高、Q5 箱顶测试 ≥ 2 次、Q6 贴着箱顶；
  C 信号日：Q7 相对这只票自己平时是不是少见的放量；
  D 业种：Q8 同业种里是不是孤立的突破（不是整个业种一起动）。
规则（运行前写定；结果出来不改）：
一 变体：每个 = 现行信号（现行参数 + W2）再加一个过滤；特征只用信号日收盘为止的数据；缺值（历史不够、业种不明）→ 保留。
二 单位与样本：逐信号 —— 每个 W2 保留的信号只留这一个买入信号，回测引擎（现行卖法与成交假设，scripts/sell_confirm.one_trade 同一做法）
   单独跑一次，扣 ¥25 万一笔的来回手续费；没买到 / 没卖出的不算。胜率 = 净收益 > 0 的比例；每笔 = 平均净收益；
   「差」= 保留的信号 − 全部信号（= 现行）。大盘（Q2 / Q3）= 同一份行情宽表里全部股票的等权日收益
   （J2 / J：J-Quants 宽表 1,378 只；E / Z：今天的日経225；W：扩大池）。
   探索：J2 = J-Quants 时点 TOPIX 1000（成员的日子才算信号，无幸存者偏差）2017-01〜2026-09（主样本）；
        E = yfinance 今天的日経225 2006-10〜2016-09（方向核对）；
        组合（S0C2 + W2 + 过滤；scripts/leap_confirm 同一框架，名额不够时按代码顺序）：E 与 J（J-Quants 今天的日経225，真实一手）。
   确认（探索没用过；只对入选的做一次）：Z = yfinance 今天的日経225 2001-01〜2006-09（去掉休市假行）；
        W = 扩大池 714 只（TOPIX 1000 里日経225 以外，var/universe_wide.json）2006-10〜2016-09；C = Z + W 合起来。
   业种（Q8）= var/industry_s33.json；「同业种的信号」只数同一个样本里的票。
三 入选（探索；全部满足）：
   a J2 与 E 的保留比例都在 30〜90%；
   b J2：胜率差 ≥ +2.0 pp 且 每笔差 ≥ +0.20 pp；
   c J2：每笔差 > 随机对照的 95 分位（按「股票 × 周」随机保留同样比例，200 次，种子 20260928）；
   d E：胜率差 ≥ 0 且 每笔差 ≥ 0；
   e 组合（E、J 各自）：Calmar 不比现行低 0.02 以上、最大回撤不比现行深 2 pp 以上。
   排序：J2 每笔差从大到小；最多 3 个，同一族最多 2 个。没有入选 → 这一轮到此为止，Z 与 W 不用（留着）。
四 确认（入选的每个；区间 = 按信号月聚类的自助法 2,000 次，种子 20260928）：
   「确认」= C 的每笔差 95% 区间下限 > 0、C 的胜率差 ≥ +1.0 pp、Z 与 W 各自的每笔差 ≥ 0；
   「方向一致」= 没到「确认」，但 C 的每笔差 > 0 且胜率差 > 0；其余「不通过」。
   结论的上限：「确认」→ 提议前向记录或改模拟盘（都要你在对话里确认、记进 sim_changes）；「方向一致」→ 最多提议前向记录；
   「不通过」→ 维持现行。这一轮不改模拟盘 / 执行器。
五 另报（只描述，不判定）：各特征的连续值与每笔净收益的秩相关（J2 / E / J；确认时加 Z / W）；保留组 vs 去掉组；
   J（今天的日経225）的逐信号结果；各特征的缺值比例；入选者在 Z 的组合回测。
事前预期（写死）：以前二十多轮买点研究只有 W2 通过，大样本下单个特征的 AUC 多在 0.50〜0.55 → 8 个里入选 0〜1 个最可能；
   入选的在没看过的数据上「确认」的机会不到两成。
输出：var/out/buyq_study.md / .json（只有统计）。
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
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import buyq_common as BQ                                                    # noqa: E402
from qbreak import paths                                                    # noqa: E402

NOTIONAL = 250_000
END_BARS = 90                                                               # 只算到信号日之后 90 根 K 线（最长持有 60 天）
W_WIN = ("2006-10-01", "2016-09-30")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def sector_map() -> dict[str, str]:
    return json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"]


# ───────────────────────── 信号、特征、逐信号交易 ─────────────────────────
def all_signals(fa: dict, keep: dict, mem: dict) -> pd.DataFrame:
    """指标表里全部 W2 保留（∧ 那天是成员）的信号（不限窗口；特征、组合掩码都要用）。"""
    rows = []
    for t, df in fa.items():
        e = df["entry"].to_numpy(bool) & np.asarray(keep[t], bool) & np.asarray(mem.get(t, np.ones(len(df), bool)), bool)
        rows += [{"ticker": t, "date": d} for d in df.index[e]]
    return pd.DataFrame(rows, columns=["ticker", "date"])


def add_features(fa: dict, S: pd.DataFrame, P: dict, days: pd.DatetimeIndex, sector: dict) -> pd.DataFrame:
    mret, mcum = BQ.market_proxy(P["C"], pd.DatetimeIndex(days))
    rows, cache = [], {}
    for r in S.itertuples(index=False):
        df = fa[r.ticker]
        if r.ticker not in cache:
            cache[r.ticker] = (mret.reindex(df.index).to_numpy(float), mcum.reindex(df.index).to_numpy(float))
        mr, mc = cache[r.ticker]
        rows.append(BQ.stock_features(df, int(df.index.get_loc(r.date)), mr, mc))
    F = pd.DataFrame(rows, index=S.index, columns=[c for c in BQ.FEATURES if c != "peers"])
    F["peers"] = BQ.peer_counts(S, pd.DatetimeIndex(days), sector)
    return pd.concat([S, F], axis=1)


def single_trades(fa: dict, S: pd.DataFrame, p, bt, rt: float) -> pd.DataFrame:
    """每个信号单独跑现行卖法 → S 加 net / hold / reason / exit_date（没买到、没卖出的去掉）。"""
    import sell_confirm as SCF
    rows = []
    for k, r in enumerate(S.itertuples(index=False)):
        df, d = fa[r.ticker], pd.Timestamp(r.date)
        pos = int(df.index.get_loc(d))
        a = SCF.one_trade(r.ticker, df.assign(entry=np.asarray(df.index == d)), d, p, bt, df.index[min(len(df) - 1, pos + END_BARS)])
        if a is None or a["reason"] == "end":
            continue
        rows.append({"k": k, "net": float(a["ret_pct"]) - rt, "hold": int(a["hold_days"]), "reason": a["reason"],
                     "exit_date": pd.Timestamp(a["exit_date"])})
    T = pd.DataFrame(rows, columns=["k", "net", "hold", "reason", "exit_date"]).set_index("k")
    out = S.iloc[T.index].copy().reset_index(drop=True)
    for c in T.columns:
        out[c] = T[c].to_numpy()
    d = pd.to_datetime(out["date"])
    out["month"] = d.dt.strftime("%Y-%m")
    out["week"] = d.dt.to_period("W").astype(str)
    return out


def build(tag: str, p0, bt, rt: float, sector: dict, base: dict | None = None) -> dict:
    """tag：J2 / J / E / Z / W → {ctx, fa, keep, Sall（全部信号 + 特征）, S（窗口内、有结果的信号）, a, b}。
    J 可以传 base = J2 的结果（同一份 J-Quants 宽表）→ 只取今天的日経225 的指标表，不重算。"""
    import leap_confirm as LF
    import sell_confirm as SCF
    t0 = time.time()
    if tag == "W":
        ctx, fa = SCF.wide_context(p0)
        a, b = W_WIN
        keep = LF.w2_keep(ctx, fa)
        mem: dict = {}
    else:
        ctx = LF.context({"J2": "J"}.get(tag, tag), jmem="U2" if tag == "J2" else "U0")
        if tag == "J" and base is not None:
            fa = {t: base["fa"][t] for t in (ctx["names"][j] for j in ctx["cols"]) if t in base["fa"]}
            keep = {t: base["keep"][t] for t in fa}
        else:
            fa = LF.frames(ctx, p0)
            keep = LF.w2_keep(ctx, fa)
        mem = LF.member_mask(ctx, fa) if tag == "J2" else {}
        a, b = ctx["start"], ctx["end"] or str(pd.DatetimeIndex(ctx["days"])[-1].date())
    Sall = add_features(fa, all_signals(fa, keep, mem), ctx["P"], ctx["days"], sector)
    d = pd.to_datetime(Sall["date"])
    S = single_trades(fa, Sall[(d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b))].reset_index(drop=True), p0, bt, rt)
    say(f"- {tag}（{a}〜{b}）：指标表 {len(fa)} 只；W2 保留的信号（全部年份）{len(Sall)} 个 → 窗口内有结果的 {len(S)} 个；{round(time.time() - t0)} s")
    return {"ctx": ctx, "fa": fa, "keep": keep, "Sall": Sall, "S": S, "a": a, "b": b}


def masks(fa: dict, Sall: pd.DataFrame, key: str) -> dict[str, np.ndarray]:
    """组合回测用：每只票每天 True，只有「W2 保留的信号日 ∧ 过滤不通过」为 False。"""
    kp = BQ.keep_of(Sall, key)
    out = {t: np.ones(len(df), bool) for t, df in fa.items()}
    for t, d, ok in zip(Sall["ticker"], Sall["date"], kp):
        if not ok:
            out[t][fa[t].index.get_loc(d)] = False
    return out


def portfolio(B: dict, p, era: str, keys) -> tuple[dict, dict]:
    import leap_confirm as LF
    import sell_explore as SX
    ctx, fa = B["ctx"], B["fa"]
    run_fn = LF.runner(ctx, fa)
    fw = LF.with_mask(fa, B["keep"])
    base = SX.summ(LF.run(ctx, run_fn, fw, p), era)
    return base, {k: SX.summ(LF.run(ctx, run_fn, LF.with_mask(fw, masks(fa, B["Sall"], k)), p), era) for k in keys}


# ───────────────────────── 统计 ─────────────────────────
def per_set(S: pd.DataFrame, placebo: bool = False) -> dict:
    net = S["net"].to_numpy(float)
    out = {}
    for k in BQ.VARIANTS:
        kp = BQ.keep_of(S, k)
        x = BQ.delta(net, kp)
        if placebo and x["kept"]:
            x.update(BQ.placebo(net, S["ticker"].to_numpy(), S["week"].to_numpy(), x["frac"]))
        x["rho"] = BQ.spearman(S[BQ.VARIANTS[k]["col"]].to_numpy(float), net)
        x["nan_pct"] = float((~np.isfinite(S[BQ.VARIANTS[k]["col"]].to_numpy(float))).mean() * 100)
        out[k] = x
    return out


def base_line(S: pd.DataFrame) -> dict:
    x = BQ._st(S["net"].to_numpy(float))
    return {**x, "hold_med": float(S["hold"].median()) if len(S) else np.nan}


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main() -> int:
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    import sell_confirm as SCF
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    sector = sector_map()
    keys = list(BQ.VARIANTS)
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 买点信号质量：新角度一轮（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/buyq_study.py 开头（运行前写定）；特征与判定 scripts/buyq_common.py；逐信号 = 只留这一个买入信号、现行卖法单独跑。")
    say("\n## 〇、样本")
    B = {"J2": build("J2", p0, bt, rt, sector)}
    B["J"] = build("J", p0, bt, rt, sector, base=B["J2"])
    B["E"] = build("E", p0, bt, rt, sector)
    st = {"J2": per_set(B["J2"]["S"], placebo=True), "E": per_set(B["E"]["S"]), "J": per_set(B["J"]["S"])}
    base_E, port_E = portfolio(B["E"], p, "E", keys)
    base_J, port_J = portfolio(B["J"], p, "J", keys)
    base = {"E": base_E, "J": base_J}
    res = {}
    for k in keys:
        port = {"E": port_E[k], "J": port_J[k]}
        res[k] = {"j2": st["J2"][k], "e": st["E"][k], "j": st["J"][k], "port": port}
        res[k]["fails"] = BQ.qualifies(res[k]["j2"], res[k]["e"], port, base)
    final = BQ.pick(res)

    say("\n## 一、探索（J2 主样本 + E 方向 + 组合；运行前写定的入选规则）")
    for tag in ("J2", "E", "J"):
        x = base_line(B[tag]["S"])
        say(f"- 现行 {tag}：{x['n']} 个信号，胜率 {fmt(x['win'], '{:.1f}')}%，每笔 {fmt(x['mean'])}%，平均赚 {fmt(x['avg_win'])}% / 平均亏 "
            f"{fmt(x['avg_loss'])}%，持有中位 {fmt(x['hold_med'], '{:.0f}')} 天")
    say(f"- 组合现行（S0C2 + W2）：E Calmar {fmt(base_E['calmar'], '{:.3f}')}（年化 {fmt(base_E['cagr'], '{:.2f}')}%、回撤 {fmt(base_E['dd'], '{:.2f}')}%）；"
        f"J {fmt(base_J['calmar'], '{:.3f}')}（{fmt(base_J['cagr'], '{:.2f}')}%、{fmt(base_J['dd'], '{:.2f}')}%）")
    say("\n| 变体 | J2 保留 | J2 胜率差 | J2 每笔差（随机 95 分位） | E 保留 | E 胜率差 / 每笔差 | 组合 Calmar E / J（现行 "
        f"{fmt(base_E['calmar'], '{:.3f}')} / {fmt(base_J['calmar'], '{:.3f}')}） | 结果 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in keys:
        j2, e, pt = res[k]["j2"], res[k]["e"], res[k]["port"]
        say(f"| {k} {BQ.VARIANTS[k]['zh']} | {fmt(j2['frac'] * 100 if j2['n'] else None, '{:.0f}')}% | {fmt(j2['dwin'], '{:+.1f}')} pp | "
            f"{fmt(j2['dmean'])} pp（{fmt(j2.get('dmean_q95'))}） | {fmt(e['frac'] * 100 if e['n'] else None, '{:.0f}')}% | "
            f"{fmt(e['dwin'], '{:+.1f}')} / {fmt(e['dmean'])} pp | {fmt(pt['E']['calmar'], '{:.3f}')} / {fmt(pt['J']['calmar'], '{:.3f}')} | "
            + ("**入选**" if k in final else ("✓（没排上）" if not res[k]["fails"] else "✗ " + "；".join(res[k]["fails"]))) + " |")
    say(f"\n- 入选：{('、'.join(final)) if final else '没有'}"
        + ("" if final else " → 按规则这一轮到此为止，Z 与另一批股票（W）不用、留着；模拟盘不变。"))

    conf: dict = {}
    if final:
        say("\n## 二、确认（没看过的数据：Z = 2001〜2006 日経225；W = 另一批股票 714 只 2006〜2016；C = 两者合起来）")
        B["Z"] = build("Z", p0, bt, rt, sector)
        B["W"] = build("W", p0, bt, rt, sector)
        C = pd.concat([B["Z"]["S"], B["W"]["S"]], ignore_index=True)
        st["Z"], st["W"], st["C"] = per_set(B["Z"]["S"]), per_set(B["W"]["S"]), per_set(C)
        base_Z, port_Z = portfolio(B["Z"], p, "Z", final)
        for tag in ("Z", "W"):
            x = base_line(B[tag]["S"])
            say(f"- 现行 {tag}：{x['n']} 个信号，胜率 {fmt(x['win'], '{:.1f}')}%，每笔 {fmt(x['mean'])}%")
        for k in final:
            kc = BQ.keep_of(C, k)
            c = {**st["C"][k], **BQ.boot_delta(C["net"].to_numpy(float), kc, C["month"].to_numpy())}
            v = BQ.verdict(c, st["Z"][k], st["W"][k])
            conf[k] = {"C": c, "Z": st["Z"][k], "W": st["W"][k], "verdict": v, "port_Z": port_Z[k]}
            say(f"- {k} {BQ.VARIANTS[k]['zh']}：C {c['n']} 个信号、保留 {fmt(c['frac'] * 100, '{:.0f}')}%；胜率 {fmt(c['win_all'], '{:.1f}')}% → "
                f"{fmt(c['win'], '{:.1f}')}%（差 {fmt(c['dwin'], '{:+.1f}')} pp，95% 区间 {fmt(c['dwin_lo'], '{:+.1f}')}〜{fmt(c['dwin_hi'], '{:+.1f}')}）；"
                f"每笔 {fmt(c['mean_all'])}% → {fmt(c['mean'])}%（差 {fmt(c['dmean'])} pp，95% 区间 {fmt(c['dmean_lo'])}〜{fmt(c['dmean_hi'])}）；"
                f"Z 每笔差 {fmt(st['Z'][k]['dmean'])} pp、W {fmt(st['W'][k]['dmean'])} pp → **{v}**")
            say(f"  - Z 组合（只描述）：Calmar {fmt(base_Z['calmar'], '{:.3f}')} → {fmt(port_Z[k]['calmar'], '{:.3f}')}，"
                f"回撤 {fmt(base_Z['dd'], '{:.2f}')}% → {fmt(port_Z[k]['dd'], '{:.2f}')}%")
        conf["_base_Z"] = base_Z

    say("\n## 三、另报（只描述）：各特征 × 每笔净收益")
    tags = [t for t in ("J2", "E", "J", "Z", "W") if t in st]
    say("| 变体 | " + " | ".join(f"{t} 秩相关 / 保留 − 去掉 每笔（胜率）/ 缺值" for t in tags) + " |")
    say("|---|" + "---|" * len(tags))
    for k in keys:
        cells = []
        for t in tags:
            x = st[t][k]
            cells.append(f"{fmt(x['rho'], '{:+.3f}')} / {fmt(x['mean'] - x['mean_rm'] if x['kept'] and x['kept'] < x['n'] else None)} pp"
                         f"（{fmt(x['win'] - x['win_rm'] if x['kept'] and x['kept'] < x['n'] else None, '{:+.1f}')} pp）/ {fmt(x['nan_pct'], '{:.0f}')}%")
        say(f"| {k} | " + " | ".join(cells) + " |")
    say(f"\n用时 {round(time.time() - t0)} s。非投资建议。")

    out = paths.out_dir()
    (out / "buyq_study.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    payload = {"code": code, "base": {t: base_line(B[t]["S"]) for t in B}, "port_base": base, "res": res, "final": final, "confirm": conf,
               "stats": {t: st[t] for t in st}}
    (out / "buyq_study.json").write_text(json.dumps(_clean(payload), ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
