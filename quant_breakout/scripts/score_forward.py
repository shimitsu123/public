"""score_forward.py — 买点「质量分」的前向记录：登记（2026-09-26）、冻结配比（--freeze）、复核（--review）。

为什么要前向记录：score_study（登记 600ba6d，结果 7eb72e1）里 F1〜F5 都没通过，但有几个现象（量比、F2 / F3 的分数、
「行业已经涨过一段的突破更差」、个股相对行业强度）值得验证。这 20 年的数据已经看过了，再从里面挑就是数据挖掘；
只有登记之后才发生的信号是真正的样本外。

一、记录什么（qbreak/score_forward.py；云端 sim-day 每天自动追加到 var/out/score_forward.csv；不影响交易）
  2026-09-28 起，日経225 股票池的每个买入信号（不管模拟盘有没有买）：日期、代码、行业、模拟盘当天有没有计划买入、收盘、
  量比、真突破、距箱顶 %、15 个因子的原值、F1〜F5 的分数与「保留」标记（分数 ≥ 冻结的门槛）、记录日、模型编号。
  同一个「日期 × 票」只保留最早记下的那次（不改、不补写；每次运行看最近 5 个交易日，只补漏记的）。
  记录失败会出现在日报「数据完整性」里。
二、冻结的配比（var/score_forward_model.json；登记时 --freeze 生成一次，之后不改）
  与 score_study 同一套因子与方法（qbreak/signal_score.py）；训练样本 = 2026-09-25 为止已平仓的全部交易（每只票单独、一次一仓、
  现行出场规则）；F1 等权 / F2 逻辑回归（L2，交叉验证选惩罚）/ F3 IC 加权 / F4 只用行业 / F5 只用个股；门槛 = 训练样本分数的 1/3 分位。
三、结果（赚没赚）不写进记录：复核时用那时的行情、每只票单独、一次一仓、现行出场规则、扣 ¥25 万一笔的来回手续费算
  （与 score_study 相同）；只算已平仓的；记录里的信号在重算的行情里对不上的，单独列出、不算。
四、事先写定的前向假设（方向与 score_study 的样本外观察一致，但那是事后观察，所以要新数据验证）
  主假设（2 个）：P1 F2（逻辑回归）的分数 → 赚钱：AUC 的区间下限 > 0.5
                  P2 量比（对数）→ 赚钱：AUC 的区间下限 > 0.5
  次假设（只报告「倾向」，不单独作为改规则的依据）：
    S1 F3 保留的信号：胜率比全部信号高（差的区间下限 > 0）且每笔期望不低于全部
    S2 行业 20 日动量、行业 60 日动量 → 赚钱：AUC 的区间上限 < 0.5（行业已经涨过一段的突破更差）
    S3 个股相对行业强度 → 赚钱：AUC 的区间下限 > 0.5
    另报：F1 / F4 / F5、真突破的 AUC。
  判定时点：已平仓的信号第一次达到 100、200、400 笔时各判定一次（其他时候只报告进度，不判定）。
  每个时点主假设用 99% 区间（控制 3 次查看 × 2 个主假设的误判），次假设用 95%。区间 = 按信号月聚类的自助法 2,000 次（种子 20260926）。
  检出力的现实（按过去 13 年每年约 36 个信号）：100 笔约 3 年、只能分辨 AUC ≈ 0.70 以上的效果；200 笔约 0.64；400 笔（约 11 年）约 0.60
  （80% 检出力）。score_study 里量比的样本外 AUC 是 0.594 —— 以这个股票池的信号频率，前向记录是防止数据挖掘的长期保险，不是快速答案。
  主假设成立 → 另写一份事先登记的组合研究（用这个分数跳过 / 排序），通过门槛且用户确认后才可能改模拟盘；只凭前向记录不改规则。
五、复核：python scripts/score_forward.py --review（只读 var/out/score_forward.csv，不改、不补写）
  → var/out/score_forward_review.md / .json，并追加 var/out/score_forward_review_history.csv。
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
from qbreak import paths                                                     # noqa: E402
from qbreak import score_forward as SF                                       # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

TRAIN_END = "2026-09-26"                         # 训练样本：信号日与平仓日都在这之前
CHECKPOINTS = (100, 200, 400)
BOOT_N, SEED = 2000, 20260926
NOTIONAL = 250_000
# 变量 → (说明, 事先方向：+1 = 越大越赚钱, 主 / 次)
HYP = {"F2": ("F2 逻辑回归分数", 1, "P1"), "vol": ("量比（对数）", 1, "P2"),
       "ind_mom20": ("行业 20 日动量", -1, "S2"), "ind_mom60": ("行业 60 日动量", -1, "S2"), "rel_ind60": ("个股相对行业", 1, "S3"),
       "F1": ("F1 等权分数", 1, "另报"), "F3": ("F3 IC 加权分数", 1, "另报"), "F4": ("F4 只用行业", 1, "另报"),
       "F5": ("F5 只用个股", 1, "另报"), "breakout": ("真突破", 1, "另报")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 冻结 ──
def freeze(force: bool = False) -> Path:
    import signal_study as SS
    import score_study as Z
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    fp = paths.home() / SF.MODEL_FILE
    if fp.exists() and not force:
        raise SystemExit(f"{fp} 已存在（冻结后不改）；确实要重建请加 --force 并在 sim_changes.md 写明原因")
    p = load_params(market="JP")
    data = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    ind0 = dict(IndicatorCache(data).all(p))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    panel = S.feature_panel(ind0, load(*SYM["JP"])["Close"])
    rows = S.signal_rows(panel, ind0, SS.START)
    T = Z.label(SS.trades(ind0, p, bt), ind0, rows, gidx)
    cut = pd.Timestamp(TRAIN_END)
    tr = T[(T["sig_date"] < cut) & (T["exit_date"] < cut)]
    models = {k: S.fit(*Z.CANDS[k], tr) for k in SF.KEYS}
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=Path(__file__).resolve().parent).stdout.strip()
    meta = {"id": f"v1-{tr['exit_date'].max():%Y%m%d}", "trained_through": str(tr["exit_date"].max().date()),
            "n_train": int(len(tr)), "win_train": round(float(tr["win"].mean()) * 100, 2), "code": head,
            "created": str(pd.Timestamp.today().date()), "forward_start": SF.FORWARD_START,
            "note": "score_study 同一套因子与方法；登记后不改（scripts/score_forward.py）"}
    SF.save_model(models, meta, fp)
    print(json.dumps(meta, ensure_ascii=False), {k: round(m.thr, 4) for k, m in models.items()})
    return fp


# ── 复核 ──
def trades_from(ind: dict, p, bt, start: str) -> pd.DataFrame:
    from qbreak.engine import run_backtest
    fee = bt.exec_cfg.fee
    rt = (fee(NOTIONAL) * 2) / NOTIONAL * 100
    rows = []
    for t, df in ind.items():
        try:
            r = run_backtest({t: df}, p, bt, start=start)
        except ValueError:
            continue
        tr = r.trades.copy()
        if len(tr):
            tr["ticker"] = t
            ix = df.index
            tr["sig_date"] = [ix[ix.searchsorted(pd.Timestamp(d)) - 1] for d in tr["entry_date"]]
            rows.append(tr)
    if not rows:
        return pd.DataFrame(columns=["ticker", "sig_date", "entry_date", "exit_date", "ret_pct", "net", "win", "reason"])
    T = pd.concat(rows, ignore_index=True)
    T["net"] = T["ret_pct"] - rt
    T["win"] = (T["net"] > 0).astype(float)
    return T


def match(log: pd.DataFrame, T: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """记录里的信号 ← 重算的交易（按信号日 × 票）；只留已平仓的。"""
    L = log.copy()
    L["date"] = pd.to_datetime(L["date"])
    R = T[["ticker", "sig_date", "exit_date", "net", "win", "reason"]].rename(columns={"sig_date": "date"})
    R["date"] = pd.to_datetime(R["date"])
    M = L.merge(R, on=["date", "ticker"], how="left")
    cnt = {"logged": int(len(L)), "matched": int(M["net"].notna().sum()),
           "open": int((M["reason"] == "end").sum()), "unmatched": int(M["net"].isna().sum())}
    C = M[M["net"].notna() & (M["reason"] != "end")].reset_index(drop=True)
    cnt["closed"] = int(len(C))
    return C, cnt


def boot_ci(C: pd.DataFrame, cols: list[str], seed: int = SEED) -> np.ndarray:
    mon = C["date"].dt.to_period("M").to_numpy()
    groups = [np.flatnonzero(mon == m) for m in np.unique(mon)]
    rng = np.random.default_rng(seed)
    V = C[cols].to_numpy(float)
    y = C["win"].to_numpy(float)
    out = np.full((BOOT_N, len(cols)), np.nan)
    for b in range(BOOT_N):
        idx = np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))])
        for j in range(len(cols)):
            a = auc_np(V[idx, j], y[idx])
            out[b, j] = np.nan if a is None else a
    return out


def evaluate(C: pd.DataFrame, cnt: dict) -> dict:
    ev = {"count": cnt, "win": round(float(C["win"].mean()) * 100, 2) if len(C) else None,
          "exp": round(float(C["net"].mean()), 3) if len(C) else None, "auc": {}}
    cols = [c for c in HYP if c in C.columns]
    B = boot_ci(C, cols) if len(C) >= 10 else np.full((1, len(cols)), np.nan)
    for j, c in enumerate(cols):
        a = auc_np(C[c], C["win"]) if len(C) else None
        q = lambda p: round(float(np.nanpercentile(B[:, j], p)), 4) if np.isfinite(B[:, j]).any() else None   # noqa: E731
        ev["auc"][c] = {"auc": None if a is None else round(a, 4), "lo95": q(2.5), "hi95": q(97.5), "lo99": q(0.5), "hi99": q(99.5)}
    if "F3_keep" in C.columns and len(C):                      # S1：F3 保留的 vs 全部
        from signal_study import boot
        K = C[C["F3_keep"] == 1]
        b = boot(C.assign(entry_date=C["date"]), K.assign(entry_date=K["date"]), SEED) if len(K) >= 5 else {}
        ev["f3_keep"] = {"n": int(len(K)), "win": round(float(K["win"].mean()) * 100, 2) if len(K) else None,
                         "exp": round(float(K["net"].mean()), 3) if len(K) else None, **b}
    return ev


def decide(ev: dict, history: pd.DataFrame | None = None) -> dict:
    n = ev["count"]["closed"]
    done = set() if history is None or history.empty else {int(x) for x in history.get("checkpoint", pd.Series(dtype=float)).dropna()}
    cp = max([c for c in CHECKPOINTS if n >= c], default=None)
    if cp is None or cp in done:
        nxt = min([c for c in CHECKPOINTS if c > n and c not in done], default=None)
        return {"checkpoint": None, "text": f"只报告进度：已平仓 {n} 笔（下一个判定时点 {nxt} 笔）" if nxt else f"已平仓 {n} 笔；三个判定时点都已做完"}
    res = {}
    for c, (lab, sgn, kind) in HYP.items():
        a = ev["auc"].get(c) or {}
        if kind not in ("P1", "P2", "S2", "S3") or a.get("auc") is None:
            continue
        lo, hi = (a["lo99"], a["hi99"]) if kind.startswith("P") else (a["lo95"], a["hi95"])
        ok = (lo is not None and lo > 0.5) if sgn > 0 else (hi is not None and hi < 0.5)
        res[c] = {"hyp": kind, "label": lab, "ok": bool(ok), "range": [lo, hi], "level": "99%" if kind.startswith("P") else "95%"}
    k = ev.get("f3_keep") or {}
    res["F3_keep"] = {"hyp": "S1", "label": "F3 保留的信号", "ok": bool(k.get("dwin_lo", -1) > 0 and (k.get("exp") or -9) >= (ev["exp"] or 9)),
                      "range": [k.get("dwin_lo"), k.get("dwin_hi")], "level": "95%"}
    return {"checkpoint": cp, "results": res}


def review() -> int:
    from qbreak.config import BacktestConfig, DataConfig
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    fp = paths.out_dir() / SF.LOG_FILE
    log = pd.read_csv(fp, dtype={"date": str, "ticker": str}) if fp.exists() else pd.DataFrame(columns=["date", "ticker"])
    say(f"# 买点「质量分」前向记录复核（{pd.Timestamp.today().date()}）")
    say(f"记录 {len(log)} 个信号（{SF.FORWARD_START}〜{log['date'].max() if len(log) else '—'}）；规则见 scripts/score_forward.py 开头。")
    ev: dict = {"count": {"logged": int(len(log)), "closed": 0}}
    if len(log):
        p = load_params(market="JP")
        data = load_universe(sorted(set(log["ticker"])), DataConfig(provider="yfinance", years=3, allow_synthetic=False).validate())
        ind = dict(IndicatorCache(data).all(p))
        bt = BacktestConfig.for_market("JP", 3, "tachibana")
        bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
        C, cnt = match(log, trades_from(ind, p, bt, SF.FORWARD_START))
        ev = evaluate(C, cnt)
        say(f"对上行情的 {cnt['matched']} 个（持有中 {cnt['open']}、对不上 {cnt['unmatched']}）；已平仓 {cnt['closed']} 笔"
            + (f"，胜率 {ev['win']}%，每笔期望 {ev['exp']:+.2f}%" if cnt["closed"] else ""))
        say("\n| 变量 | 事先方向 | 假设 | AUC | 95% 区间 | 99% 区间 |")
        say("|---|---|---|---|---|---|")
        for c, a in ev["auc"].items():
            lab, sgn, kind = HYP[c]
            say(f"| {c} {lab} | {'+' if sgn > 0 else '−'} | {kind} | {a['auc'] if a['auc'] is not None else '—'} | "
                f"{a['lo95']}〜{a['hi95']} | {a['lo99']}〜{a['hi99']} |")
        k = ev.get("f3_keep") or {}
        if k:
            say(f"\nF3 保留的信号 {k['n']} 笔：胜率 {k['win']}%、每笔 {k['exp']}%（全部 {ev['win']}% / {ev['exp']}%）；"
                f"胜率差 95% 区间 {k.get('dwin_lo')}〜{k.get('dwin_hi')} pp")
    hist_fp = paths.out_dir() / "score_forward_review_history.csv"
    hist = pd.read_csv(hist_fp) if hist_fp.exists() else pd.DataFrame()
    V = decide(ev, hist) if ev["count"].get("closed") else {"checkpoint": None, "text": "还没有已平仓的信号"}
    if V.get("checkpoint"):
        say(f"\n## 判定（已平仓第一次达到 {V['checkpoint']} 笔；主假设 99% 区间、次假设 95%）")
        for c, r in V["results"].items():
            say(f"- {r['hyp']} {r['label']}：{'成立' if r['ok'] else '不成立'}（{r['level']} 区间 {r['range'][0]}〜{r['range'][1]}）")
        if any(r["ok"] for r in V["results"].values() if r["hyp"].startswith("P")):
            say("主假设成立 → 需要另写一份事先登记的组合研究；模拟盘规则不变（改需用户确认）。")
    else:
        say(f"\n{V['text']}")
    out = paths.out_dir() / "score_forward_review"
    Path(f"{out}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{out}.json").write_text(json.dumps({"eval": ev, "decision": V}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    row = {"run": str(pd.Timestamp.today().date()), "logged": ev["count"].get("logged"), "closed": ev["count"].get("closed"),
           "checkpoint": V.get("checkpoint"), **{f"auc_{c}": (a or {}).get("auc") for c, a in (ev.get("auc") or {}).items()}}
    pd.concat([hist, pd.DataFrame([row])], ignore_index=True).to_csv(hist_fp, index=False)
    print(f"{time.time() - t0:.0f}s")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", action="store_true", help="登记时生成冻结的配比（只做一次）")
    g.add_argument("--review", action="store_true", help="复核前向记录")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.freeze:
        freeze(a.force)
        return 0
    return review()


if __name__ == "__main__":
    raise SystemExit(main())
