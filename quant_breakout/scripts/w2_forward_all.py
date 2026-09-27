"""w2_forward_all.py — W2 的全市场前向检验（2026-09-27 事先登记；用户：「登记 W2 前向记录，加全市场版」）。

来由：W2（周线量比 ≥ 1.0 的突破才买，2026-09-27 启用）的证据都来自看过多次的历史数据（allstock_posthoc：全市场 2016〜2026
每笔 +0.25% vs +0.10%，11 年里 9 年更好；成交额低的三分之一没有效果）。日経225 + 扩大池的每日记录（scripts/score_forward.py 第八节）
每年只有约 250 笔，要很多年才有结论 → 这里在全市场（每年约 1,000 笔）上用**登记之后才发生的数据**检验，规则现在写定，以后不改。

一、对象
  东证一般市场（プライム / スタンダード / グロース）的内国普通股：信号日严格早于那天的最近一个月末上市一览（scripts/allstock_data.py
  同一口径；TOKYO PRO MARKET 与 ETF 等不算）；信号 = 现行突破（参数 = 复核时的现行日本参数去掉 W2，与 score_forward 第八节同一口径），
  信号日 ≥ 2026-09-28。
  主：信号日的 20 天平均成交额（收盘 × 成交量，allstock_study 的 lturn）≥ ¥500 万；另报：不限成交额的全部。
二、结果：每只票单独、一次一仓、现行卖出规则、扣立花 ¥25 万一笔的来回成本（allstock_study.train_all 同一套）；只算已平仓的。
三、分组：W2 保留（周线量比 ≥ 1.0 或缺值）/ 挡掉（< 1.0）；周线量比 = qbreak/mtf.py weekly_volume_ratio（东证日历补下一个交易日），
  与实盘 W2 同一个定义；门槛 1.0 在这里写定，不跟着参数变。
四、判定（每年一次：复核日第一次到达 2027-09-28、2028-09-28、2029-09-28、2030-09-28、2031-09-28 之后的那次复核；其他时候只报告进度）
  差 = 保留 − 挡掉的每笔平均净收益 pp；区间 = 按信号月聚类的自助法 2,000 次（种子 20260927）。都用主对象（成交额 ≥ ¥500 万）：
  失效警报：「挡掉 − 保留」的 95% 区间下限 > 0 → 提议关掉 W2；
  证实：「保留 − 挡掉」的 99% 区间下限 > 0 → 记为「新数据证实 W2」。
  另报（不判定）：不限成交额的全部、日経225（今天的成分）与其他、各年的笔数 / 胜率 / 每笔。
  检出力（每年约 1,000 笔、每笔标准差约 5.9%、保留约 45%；80%）：每笔差 1 pp 约 1〜1.3 年、0.5 pp 约 4.5 年、0.3 pp 约 12 年。
  警报 / 证实都只是提议：改模拟盘与执行器要用户在对话里确认，并记 var/sim_changes.md。
五、数据：J-Quants（批量日线 + 月末上市一览）；复核时先补齐本地缓存（原始数据只在 var/cache/jquants/，不入库）。
  输出（只有统计）：var/out/w2_forward_all_review.md / .json；var/out/w2_forward_all_history.csv（只追加：每次复核一行、判定过的年份）。
六、复核：python scripts/w2_forward_all.py --review（要 J-Quants 的键；Mac：bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python
  scripts/w2_forward_all.py --review）。
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak import w2_forward as W2F                                         # noqa: E402

FORWARD_START = "2026-09-28"
W2_CUT = 1.0
LIQ_MIN_YEN = 5_000_000
JUDGE_DATES = ("2027-09-28", "2028-09-28", "2029-09-28", "2030-09-28", "2031-09-28")
BOOT_N, SEED = 2000, 20260927

LIQ_LOG = math.log10(LIQ_MIN_YEN)                                             # allstock_study 的 lturn = log10(20 天平均成交额)
HIST = "w2_forward_all_history.csv"
LINES: list[str] = []
assert W2_CUT == W2F.W2_CUT and JUDGE_DATES == W2F.JUDGE_DATES and (BOOT_N, SEED) == (W2F.BOOT_N, W2F.SEED)   # 登记值与共用模块一致


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_ends(after, until) -> list[str]:
    """after 之后、until 为止每个月的最后一个东证交易日（要补的月末上市一览）。"""
    from qbreak.calendar_jp import is_trading_day, prev_trading_day
    a, u = pd.Timestamp(after), pd.Timestamp(until)
    out = []
    for p in pd.period_range(a.to_period("M"), u.to_period("M"), freq="M"):
        d = p.to_timestamp(how="end").date()
        if not is_trading_day(d):
            d = prev_trading_day(d)
        if a < pd.Timestamp(d) <= u:
            out.append(d.isoformat())
    return out


def refresh(log=print, today=None) -> dict:
    """补齐 J-Quants 缓存：批量日线（已下载且没变的跳过）+ 新的月末上市一览。原始数据只在缓存目录（不入库）。"""
    from qbreak import jq_data as JD
    from qbreak import pit_data as PD
    from qbreak import jquants as JQ
    c = JQ.JQuants()
    files = JD.bulk_download(c, "/equities/bars/daily", log=log)
    have = PD.master_files()
    new = month_ends(max(have) if have else pd.Timestamp(FORWARD_START) - pd.Timedelta(days=40),
                     pd.Timestamp(today) if today is not None else pd.Timestamp.today())
    for d in new:
        JQ.master_cached(c, d)
    return {"bar_files": len(files), "new_snapshots": new}


def forward_trades(T: pd.DataFrame) -> pd.DataFrame:
    """allstock_study.train_all 的交易 → 信号日 ≥ FORWARD_START 的已平仓交易 + W2 标记 + 是否主对象（成交额 ≥ ¥500 万）。"""
    if not len(T):
        return T.assign(w2_keep=pd.Series(dtype=int), main=pd.Series(dtype=bool))
    F = T[pd.to_datetime(T["sig_date"]) >= pd.Timestamp(FORWARD_START)].copy()
    F["sig_date"] = pd.to_datetime(F["sig_date"])
    F["w2_keep"] = W2F.keep_flag(F["w5v"])
    F["main"] = F["lturn"].to_numpy(float) >= LIQ_LOG                        # 缺值 → 不是主对象
    return F.reset_index(drop=True)


def decide(ev: dict, hist: pd.DataFrame | None, today) -> dict:
    """每年一次（JUDGE_DATES）：失效警报 95% / 证实 99%；判定过的年份记进历史，不再判定。"""
    year = W2F.due_date(today, JUDGE_DATES, W2F.history_done(hist, "all", "w2_year"))
    return {"year": year, "alarm": W2F.alarm(ev) if year else None, "confirmed": W2F.confirmed(ev) if year else None}


def by_year(F: pd.DataFrame) -> dict:
    out = {}
    for y, g in F.groupby(F["sig_date"].dt.year):
        k = g["w2_keep"].to_numpy(int)
        out[int(y)] = {"keep": W2F.stat(g.loc[k == 1, "net"]), "drop": W2F.stat(g.loc[k == 0, "net"])}
    return out


def review(fetch: bool = True) -> int:
    import allstock_data as AD
    import allstock_study as S
    from bullbear_study import SYM, load
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    today = pd.Timestamp.today().normalize()
    info = refresh(log=lambda s: print(s, file=sys.stderr, flush=True)) if fetch else {"skipped": "没有补数据（--no-fetch）"}
    A = AD.load(rebuild=fetch)
    last_bar = A["days"][-1]
    p = SF.no_w2_params(load_params(market="JP"))
    T, n_st = S.train_all(A, p, S.market_frame(load(*SYM["JP"])["Close"]), start=FORWARD_START)
    del A
    F = forward_trades(T)
    n225 = set(universe("JP", "broad"))
    F["n225"] = F["ticker"].isin(n225)
    M = F[F["main"]]
    ev = W2F.evaluate(M, date_col="sig_date")
    hist_fp = paths.out_dir() / HIST
    hist = pd.read_csv(hist_fp) if hist_fp.exists() else pd.DataFrame()
    V = decide(ev, hist, today)
    side = {"全部（不限成交额）": W2F.evaluate(F, date_col="sig_date", n=0) if len(F) else {"n": 0},
            "主对象里的日経225 股票池": W2F.evaluate(M[M["n225"]], date_col="sig_date", n=0) if len(M) else {"n": 0},
            "主对象里的其他股票": W2F.evaluate(M[~M["n225"]], date_col="sig_date", n=0) if len(M) else {"n": 0}}
    say(f"# W2 全市场前向检验复核（{today.date()}）")
    say(f"规则见 scripts/w2_forward_all.py 开头（2026-09-27 登记）。数据到 {last_bar.date()}；{n_st} 只里信号日 ≥ {FORWARD_START} 的已平仓交易 "
        f"{len(F)} 笔（主对象 = 20 天平均成交额 ≥ ¥{LIQ_MIN_YEN / 1e4:.0f} 万：{len(M)} 笔）。")
    say("\n## 主对象：W2 保留 vs 挡掉")
    say(W2F.summary_line(ev) if ev["n"] else "还没有已平仓的信号")
    lines = W2F.verdict_lines(ev, f"{V['year']} 这一年" if V["year"] else None, f"{V['year']} 这一年" if V["year"] else None)
    for x in lines:
        say(f"- {x}")
    if not lines:
        nxt = next((d for d in JUDGE_DATES if pd.Timestamp(d) > today), None)
        say(f"只报告进度（下一次判定：{nxt} 之后的复核）" if nxt else "五次年度判定都已做完（只报告）")
    say("\n## 另报（不判定）")
    for k, e in side.items():
        say(f"- {k}：" + (W2F.summary_line(e) if e.get("n") else "0 笔"))
    yr = by_year(M) if len(M) else {}
    if yr:
        say("\n| 信号年 | W2 保留 | 挡掉 |")
        say("|---|---|---|")
        f = lambda s: f"{s['n']} 笔 / {s['win']:.1f}% / {s['mean']:+.2f}%" if s.get("n") else "—"             # noqa: E731
        for y, v in yr.items():
            say(f"| {y} | {f(v['keep'])} | {f(v['drop'])} |")
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"\n代码版本 {code}；用时 {time.time() - t0:.0f}s")
    out = paths.out_dir() / "w2_forward_all_review"
    Path(f"{out}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{out}.json").write_text(json.dumps({"run": str(today.date()), "data_through": str(last_bar.date()), "refresh": info,
                                               "n_all": int(len(F)), "main": ev, "decision": V, "side": side, "by_year": yr,
                                               "code": code}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    row = {"run": str(today.date()), "scope": "all", "data_through": str(last_bar.date()), "closed": ev["n"], "w2_year": V["year"],
           "w2_diff": ev.get("diff"), "w2_lo95": ev.get("lo95"), "w2_hi95": ev.get("hi95"), "w2_lo99": ev.get("lo99"),
           "w2_hi99": ev.get("hi99"), "w2_alarm": V["alarm"], "w2_confirmed": V["confirmed"], "code": code}
    pd.concat([hist, pd.DataFrame([row])], ignore_index=True).to_csv(hist_fp, index=False)   # 只追加
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", required=True, help="复核（先补齐 J-Quants 缓存）")
    ap.add_argument("--no-fetch", action="store_true", help="不补数据，用现有缓存（试跑用）")
    a = ap.parse_args(argv)
    return review(fetch=not a.no_fetch)


if __name__ == "__main__":
    raise SystemExit(main())
