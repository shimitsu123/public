"""heldout_study.py — 「没参与过设计的股票」检验：买点质量分的几个现象，在日経225 以外的 TOPIX 1000 股票上还成立吗？
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）

为什么：量比、F2 分数、「行业已经涨过的突破更差」、个股相对行业强度，都是在日経225 股票池 2013〜 的样本外结果里看到的
（score_study 7eb72e1）。前向记录要一两年以上；而 TOPIX 1000 里另外 716 只股票的历史信号从来没用来设计过任何规则 ——
用它们检验同样的假设，是现在就能拿到的样本外证据。局限：股票不同，但时期相同（大盘环境的影响是共同的），所以比前向检验弱。

一、样本（登记前只数过信号，没看任何结果）
  var/universe_wide.json（冻结，東証上場銘柄一覧 2026-08-31 版）：T500x（TOPIX 500 里日経225 股票池以外）249 只、
  S1x（TOPIX Small 1 里的其余）467 只；同样剔除航空 / 陆运 / 仓储物流。信号日 2013-01〜2026-09（与 score_study 的样本外相同）：
  T500x 724 个、S1x 1,608 个。每只票单独、一次一仓、现行出场规则、扣 ¥25 万一笔的来回手续费（与 score_study 相同）。
二、打分（与前向记录同一套因子；qbreak/signal_score.py、qbreak/wide_universe.py）
  每一年用「日経225 股票池里、这一年之前已平仓的交易」定的配比（score_study 的逐年模型 F1〜F5）给扩大池这一年的信号打分；
  行业因子对照日経225 同组成员（東証 33 业种 → 现有分组的对照表事先写定）。
三、假设（与前向记录相同；方向事先写定）
  主 P1 F2 分数 → 赚钱（AUC > 0.5）；P2 量比 → 赚钱（AUC > 0.5）
  次 S1 F3 保留的（分数 ≥ 当年门槛）胜率比全部高、每笔期望不低；S2 行业 20 / 60 日动量 → 更差（AUC < 0.5）；
     S3 个股相对行业 → 更好（AUC > 0.5）；另报 F1 / F4 / F5、真突破。
四、判定（事先写定）
  主假设「在没用过的股票上成立」= T500x 的 AUC 99% 区间在事先方向上不含 0.5，且 T500x 两个半段（2013〜2019 / 2020〜）的点估计
    都在事先方向，且 S1x 的点估计也在事先方向。
  次假设：T500x 的 95% 区间在事先方向上不含 0.5（S1：保留的胜率差 95% 区间下限 > 0 且每笔期望不低于全部）。
  区间 = 按信号月聚类的自助法 2,000 次（种子 20260926）。另报 S1x 与两段合并的同样数字。
五、之后
  主假设成立 → 提议一份事先登记的 S0C2 组合研究（用这个分数跳过 / 排序）；结果出来并且用户确认之前，模拟盘规则不变。
  主假设不成立 → 这个现象很可能只是日経225 这 20 年的偶然，前向记录照旧继续。
  登记前做过的检查：tests/test_wide_universe.py（扩大池的行业因子 = 日経225 同组成员的平均、对照表覆盖、合成行情全流程）。
输出：var/out/heldout_study.md / .json
"""
from __future__ import annotations

import json
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
import score_forward as SFR                                                  # noqa: E402
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import wide_universe as W                                        # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

OOS0, HALVES, SEED = Z.OOS0, Z.HALVES, 20260926
HYP = SFR.HYP
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def score_by_year(rows: pd.DataFrame, models: dict[str, dict]) -> pd.DataFrame:
    """rows（扩大池的信号）按年份用对应年份的日経225 模型打分：列 F1〜F5 与 F1_thr〜F5_thr。"""
    out = rows.copy()
    for k in models:
        out[k], out[f"{k}_thr"] = np.nan, np.nan
    yr = out["date"].dt.year.to_numpy()
    for k, ms in models.items():
        for y, m in ms.items():
            sel = yr == y
            if sel.any():
                out.loc[sel, k] = m.score(out[sel])
                out.loc[sel, f"{k}_thr"] = m.thr
    return out


def outcomes(ind: dict, p, bt) -> pd.DataFrame:
    T = SS.trades(ind, p, bt)
    T["sig_date"] = pd.DatetimeIndex([ind[x.ticker].index[ind[x.ticker].index.searchsorted(x.entry_date) - 1] for x in T.itertuples()])
    return T


def evaluate_seg(D: pd.DataFrame) -> dict:
    """一个分段（已按 2013〜 过滤）的主 / 次假设数字。D：交易 + 信号日的因子与分数，列 date = 信号日。"""
    ev = SFR.evaluate(D, {"closed": int(len(D))})
    ev["halves"] = {h: {c: (round(a, 4) if (a := auc_np(Z.span(D, w, "date")[c], Z.span(D, w, "date")["win"])) is not None else None)
                        for c in HYP if c in D.columns} for h, w in HALVES.items()}
    ev["n_halves"] = {h: int(len(Z.span(D, w, "date"))) for h, w in HALVES.items()}
    if "F3" in D.columns:
        K = D[D["F3"] >= D["F3_thr"]]
        b = SS.boot(D.assign(entry_date=D["date"]), K.assign(entry_date=K["date"]), SEED) if len(K) >= 5 else {}
        ev["f3_keep"] = {"n": int(len(K)), "win": round(float(K["win"].mean()) * 100, 2) if len(K) else None,
                         "exp": round(float(K["net"].mean()), 3) if len(K) else None, **b}
    return ev


def decide(E: dict) -> dict:
    t5, s1 = E["T500x"], E["S1x"]
    res = {}
    for c, (lab, sgn, kind) in HYP.items():
        a = t5["auc"].get(c) or {}
        if a.get("auc") is None or kind == "另报":
            continue
        if kind.startswith("P"):
            lo, hi = a["lo99"], a["hi99"]
            ci_ok = (lo is not None and lo > 0.5) if sgn > 0 else (hi is not None and hi < 0.5)
            halves_ok = all(v is not None and (v - 0.5) * sgn > 0 for v in (t5["halves"][h].get(c) for h in HALVES))
            s1v = (s1["auc"].get(c) or {}).get("auc")
            s1_ok = s1v is not None and (s1v - 0.5) * sgn > 0
            fails = [x for x, ok in (("T500x 99% 区间含 0.5", ci_ok), ("T500x 两个半段不都在事先方向", halves_ok),
                                     ("S1x 点估计不在事先方向", s1_ok)) if not ok]
            res[c] = {"hyp": kind, "label": lab, "ok": not fails, "fails": fails, "range": [lo, hi], "level": "99%"}
        else:
            lo, hi = a["lo95"], a["hi95"]
            ok = (lo is not None and lo > 0.5) if sgn > 0 else (hi is not None and hi < 0.5)
            res[c] = {"hyp": kind, "label": lab, "ok": bool(ok), "fails": [] if ok else ["T500x 95% 区间含 0.5"], "range": [lo, hi],
                      "level": "95%"}
    k = t5.get("f3_keep") or {}
    ok = bool(k.get("dwin_lo", -1) > 0 and (k.get("exp") or -9) >= (t5["exp"] or 9))
    res["F3_keep"] = {"hyp": "S1", "label": "F3 保留的信号", "ok": ok, "fails": [] if ok else ["胜率差区间下限不大于 0 或期望更低"],
                      "range": [k.get("dwin_lo"), k.get("dwin_hi")], "level": "95%"}
    return res


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/heldout_study.py", "scripts/score_study.py",
                            "scripts/score_forward.py", "scripts/signal_study.py", "qbreak/signal_score.py", "qbreak/wide_universe.py",
                            "qbreak/weights.py", "qbreak/engine.py", "qbreak/strategy.py", "qbreak/sectors.py", "var/universe_wide.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    ind_n = dict(IndicatorCache(data_n).all(p))
    doc = W.load()
    data_x = load_universe(W.tickers(doc), d21)
    ind_x = dict(IndicatorCache(data_x).all(p))
    ic = load(*SYM["JP"])["Close"]
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind_n.values()])))
    rows_n = S.signal_rows(S.feature_panel(ind_n, ic), ind_n, SS.START)
    T_n = Z.label(SS.trades(ind_n, p, bt), ind_n, rows_n, gidx)
    models = {k: S.walk_forward(rows_n, T_n, kind, cols, Z.YEARS)[1] for k, (kind, cols) in Z.CANDS.items()}
    print("日経225 逐年模型", {k: len(v) for k, v in models.items()}, f"{time.time() - t0:.0f}s", flush=True)
    rows_x = S.signal_rows(W.feature_panel_wide(ind_x, ind_n, ic, W.group_of(doc)), ind_x, OOS0)
    rows_x = score_by_year(rows_x, models)
    rows_x["breakout"] = [int(bool(ind_x[t].loc[d, "breakout"])) if pd.notna(ind_x[t].loc[d, "breakout"]) else 0
                          for t, d in zip(rows_x["ticker"], rows_x["date"])]
    T_x = outcomes(ind_x, p, bt)
    D = T_x[T_x["sig_date"] >= pd.Timestamp(OOS0)][["ticker", "sig_date", "net", "win", "reason"]].rename(columns={"sig_date": "date"})
    D = D.merge(rows_x, on=["date", "ticker"], how="left")
    D["win"] = D["win"].astype(float)
    seg = W.segment_of(doc)
    D["segment"] = D["ticker"].map(seg)
    print("扩大池", {s: int((D["segment"] == s).sum()) for s in ("T500x", "S1x")}, "对不上信号的", int(D["F2"].isna().sum()),
          f"{time.time() - t0:.0f}s", flush=True)
    E = {s: evaluate_seg(D[D["segment"] == s].reset_index(drop=True)) for s in ("T500x", "S1x")}
    E["合并"] = evaluate_seg(D.reset_index(drop=True))
    V = decide(E)
    ref = json.loads((paths.out_dir() / "score_study.json").read_text(encoding="utf-8"))
    uni_ref = (ref.get("extra") or {}).get("univariate") or {}
    say(f"# 「没参与过设计的股票」检验：买点质量分的现象在 TOPIX 1000 其余股票上还成立吗（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say(f"扩大池 T500x {len(W.tickers(doc, 'T500x'))} 只、S1x {len(W.tickers(doc, 'S1x'))} 只（var/universe_wide.json）；信号日 2013〜；"
        "每年用日経225 之前已平仓的交易定的配比打分。规则见 scripts/heldout_study.py 开头（先提交后运行）。")
    say("\n| 分段 | 已平仓 | 胜率 | 每笔期望 | 两半笔数 |")
    say("|---|---|---|---|---|")
    for s, e in E.items():
        say(f"| {s} | {e['count']['closed']} 笔 | {e['win']}% | {e['exp']:+.2f}% | {e['n_halves']['O1']} / {e['n_halves']['O2']} |")
    say("\n## AUC（0.5 = 瞎猜；按事先方向，> 0.5 = 与假设一致，行业动量是 < 0.5 才一致）")
    say("| 变量 | 方向 | 假设 | 日経225 样本外（score_study） | T500x（95% / 99% 区间） | T500x 两半 | S1x | 合并 |")
    say("|---|---|---|---|---|---|---|---|")
    for c, (lab, sgn, kind) in HYP.items():
        a5, a1, am = (E[s]["auc"].get(c) or {} for s in ("T500x", "S1x", "合并"))
        hv = " / ".join(str(E["T500x"]["halves"][h].get(c)) for h in HALVES)
        refv = (uni_ref.get(c) or {}).get("auc") if c in S.ALL else ((ref.get("results") or {}).get(c) or {}).get("auc", {}).get("all")
        say(f"| {lab if lab.startswith(c) else f'{c} {lab}'} | {'+' if sgn > 0 else '−'} | {kind} | {refv if refv is not None else '—'} | {a5.get('auc')}（{a5.get('lo95')}〜{a5.get('hi95')} / "
            f"{a5.get('lo99')}〜{a5.get('hi99')}） | {hv} | {a1.get('auc')} | {am.get('auc')} |")
    for s in ("T500x", "S1x"):
        k = E[s].get("f3_keep") or {}
        if k:
            say(f"\n{s}：F3 保留的 {k['n']} 笔 胜率 {k['win']}%、每笔 {k['exp']:+.2f}%（全部 {E[s]['win']}% / {E[s]['exp']:+.2f}%）；"
                f"胜率差 95% 区间 {k.get('dwin_lo')}〜{k.get('dwin_hi')} pp，期望差 {k.get('dexp_lo')}〜{k.get('dexp_hi')} pp")
    say("\n## 判定（事先规则：主假设 = T500x 99% 区间在事先方向不含 0.5 + T500x 两半都在事先方向 + S1x 点估计在事先方向；次假设 = T500x 95%）")
    for c, r in V.items():
        say(f"- {r['hyp']} {r['label']}：{'成立' if r['ok'] else '不成立'}（{r['level']} 区间 {r['range'][0]}〜{r['range'][1]}）"
            + ("" if r["ok"] else "：" + "；".join(r["fails"])))
    main_ok = [c for c, r in V.items() if r["hyp"].startswith("P") and r["ok"]]
    say(f"\n主假设成立：{'、'.join(main_ok)} → 提议另写一份事先登记的 S0C2 组合研究；模拟盘规则不变（改需用户确认）。" if main_ok
        else "\n主假设在没用过的股票上都不成立 → 不提议组合研究；前向记录照旧继续。")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "heldout_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "decision": V, "eval": E}, ensure_ascii=False, indent=1, default=float),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
