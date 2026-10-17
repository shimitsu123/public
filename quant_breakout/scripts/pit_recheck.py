"""pit_recheck.py — 事后核对（不是新的登记检验；读法写在这里、先提交再运行）：用「近似时点日経225」重算现行与 W2。

用户（2026-09-28）：「分析为什么越靠近现在胜率什么的就会变弱 并把这部分变弱的解决后优化到模型里面进行再研究」。
来由（scripts/decay_diag.py → var/out/decay_diag.md，只描述）：逐笔看 E（2006〜2016）与 J（2017〜）每笔一样（+0.74% vs +0.76%，t −0.03）；
  Z（2001〜2006）多 +2.0 pp 但 t 只有 1.7〜1.8，一半的笔数在 2005 年（每笔 +4.57%），去掉 2005 年只多 +0.15 pp；按当时是否成员拆开，
  「后来才被选进」的票（后见之明）并不更好。→ 「越来越弱」不是结构性衰退；要修的是评价口径：以前 Z / E / J 都用「今天的日経225」回看过去。
这里把研究框架改成可选的「近似时点日経225」（qbreak/n225_history.py：今天的成员只在被选进之后的年份、2001 年以后被剔除且仍上市的旧成员
  只在成员年份才允许开新仓；进出那一年不算），组合回测的其余部分（scripts/leap_confirm.py：S0C2 + 现行买卖、Z / E 已去掉 Yahoo 休市假行、
  J 用 J-Quants）一律不改，重算：
  A 现行（W2）与 不加 W2 × {今天的名单, 近似时点名单} × Z / E / J：组合年化 / 回撤 / Calmar、组合里的个股笔数 · 每笔 · 胜率；
  B 每个窗口「去掉最好的一个日历年」后的每笔（只描述）。
读法（事先写定）：
  R1 Z 的每笔：近似时点 ≥ 今天名单 − 0.5 ×（今天名单 Z − E 的差）→「Z 的优势不是股票池后见之明造成的」；否则「Z 被股票池后见之明抬高」。
  R2 W2：近似时点下每个窗口的（现行 − 不加 W2）每笔差；≤ 0 的窗口 ≥ 2 个 →「W2 的历史证据在近似时点股票池下变弱，交给 W2 前向记录判定」；
     否则「W2 的历史证据不受股票池口径影响」。
  两条都只影响预期与文档，模拟盘 / 执行器 / W2 / 股票池一律不改；以后的研究在 Z / E 另报近似时点的结果（leap_confirm 的 pit 选项）。
局限：旧成员里倒闭 / 被收购而退市的没有行情（42 只里约 13 只）；成员只按年份；J 的旧成员只取 J-Quants 面板里有的。
输出：var/out/pit_recheck.md / .json
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
from qbreak import n225_history as H                                         # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def last_trades() -> pd.DataFrame:
    """刚跑完的组合里的个股交易（不含 1655、不含期末未平仓）：entry_date、net %。"""
    import jq_study as JS
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    if not len(tr):
        return pd.DataFrame(columns=["entry_date", "net"])
    tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")].copy()
    tr["net"] = tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100
    tr["entry_date"] = pd.to_datetime(tr["entry_date"])
    return tr[["ticker", "entry_date", "net"]]


def ex_best_year(tr: pd.DataFrame, a: str, b: str | None) -> dict:
    """窗口内的每笔；去掉每笔平均最高的那个日历年后的每笔与胜率。"""
    m = (tr["entry_date"] >= pd.Timestamp(a)) & ((tr["entry_date"] <= pd.Timestamp(b)) if b else True)
    x = tr[m]
    if not len(x):
        return {"best_year": None, "n": 0, "mean": None, "win": None}
    y = x["entry_date"].dt.year
    best = int(x.groupby(y)["net"].mean().idxmax())
    z = x[y != best]
    return {"best_year": best, "n": int(len(z)), "mean": round(float(z["net"].mean()), 3) if len(z) else None,
            "win": round(float((z["net"] > 0).mean() * 100), 1) if len(z) else None}


def j_pit_context(ctx: dict) -> dict:
    """J 的近似时点：今天的成员 + J-Quants 面板里有的旧成员（cols 与真实一手比例表一起扩）。"""
    D = ctx["D"]
    nm = ctx["names"]
    want = set(H.pit_names([nm[j] for j in ctx["cols"]]))
    cols = [j for j, t in enumerate(nm) if t in want and np.isfinite(ctx["P"]["C"][:, j]).any()]
    ratio = {nm[j]: pd.Series(D["ratio"][:, j], index=ctx["days"]) for j in cols}
    return {**ctx, "cols": cols, "ratio": ratio}


def window(era: str, p) -> dict:
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.config import universe
    t0 = time.time()
    p0 = SF.no_w2_params(p)
    out = {}
    today = list(universe("JP", "broad"))
    ctxs = {"today": LF.context(era)}
    ctxs["pit"] = LF.context(era, names=H.pit_names(today)) if era in ("Z", "E") else j_pit_context(ctxs["today"])
    a, b = ctxs["today"]["windows"][era]
    for u, ctx in ctxs.items():
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        keep = LF.w2_keep(ctx, fa)
        if u == "pit":
            mem = H.member_mask(fa)
            keep = {t: keep[t] & mem[t] for t in fa}
            fa = LF.with_mask(fa, mem)
        res = {}
        for k, fr in (("现行", LF.with_mask(fa, keep)), ("不加 W2", fa)):
            r = LF.run(ctx, run_fn, fr, p)
            res[k] = {"port": r[era], "ex_best": ex_best_year(last_trades(), a, b)}
        out[u] = {"res": res, "names": len(fa)}
    out["secs"] = round(time.time() - t0)
    return out


def cell(r: dict) -> str:
    s = r["port"]
    f = lambda v, fmt: "—" if v is None else fmt.format(v)                  # noqa: E731
    return (f"{f(s.get('cagr'), '{:.2f}')}% / {f(s.get('dd'), '{:.2f}')}% / {f(s.get('calmar'), '{:.3f}')} · {s.get('n')} 笔 "
            f"{f(s.get('mean'), '{:+.2f}')}% / {f(s.get('win'), '{:.1f}')}%")


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    root = str(paths.PROJECT_ROOT)
    code = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", "scripts/pit_recheck.py", "qbreak/n225_history.py",
                                 "scripts/leap_confirm.py"], capture_output=True, text=True).stdout.strip())
    p = load_params(market="JP")
    W = {era: window(era, p) for era in ("Z", "E", "J")}
    say(f"# 事后核对：近似时点日経225 重算现行与 W2（{pd.Timestamp.today().date()}；git {code}{'（脏）' if dirty else ''}）")
    say("读法见 scripts/pit_recheck.py 开头（先提交再运行）。各格 = 组合年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔 / 胜率。")
    say("\n| 窗口 | 方案 | 今天的名单 | 近似时点名单 | 去掉最好的一年（今天 → 近似时点） |")
    say("|---|---|---|---|---|")
    for era in ("Z", "E", "J"):
        for k in ("现行", "不加 W2"):
            rt, rp = W[era]["today"]["res"][k], W[era]["pit"]["res"][k]
            et, ep = rt["ex_best"], rp["ex_best"]
            fe = lambda e: "—" if not e.get("n") else f"去 {e['best_year']}：{e['n']} 笔 {e['mean']:+.2f}% / {e['win']:.0f}%"   # noqa: E731
            say(f"| {era} | {k} | {cell(rt)} | {cell(rp)} | {fe(et)} → {fe(ep)} |")
    m = lambda era, u, k: W[era][u]["res"][k]["port"].get("mean")             # noqa: E731
    gap = m("Z", "today", "现行") - m("E", "today", "现行")
    r1_ok = m("Z", "pit", "现行") >= m("Z", "today", "现行") - 0.5 * gap
    r1 = "Z 的优势不是股票池后见之明造成的" if r1_ok else "Z 被股票池后见之明抬高"
    w2d = {era: round(m(era, "pit", "现行") - m(era, "pit", "不加 W2"), 3) for era in ("Z", "E", "J")}
    r2 = ("W2 的历史证据在近似时点股票池下变弱，交给 W2 前向记录判定" if sum(v <= 0 for v in w2d.values()) >= 2
          else "W2 的历史证据不受股票池口径影响")
    say("\n## 读法（事先写定）")
    say(f"- R1：Z 现行每笔 今天的名单 {m('Z', 'today', '现行'):+.2f}% → 近似时点 {m('Z', 'pit', '现行'):+.2f}%（Z − E 的差 {gap:+.2f} pp，"
        f"门槛 = 今天 − 一半）→ **{r1}**。")
    say(f"- R2：近似时点下 W2 每笔的增益 Z {w2d['Z']:+.2f} / E {w2d['E']:+.2f} / J {w2d['J']:+.2f} pp → **{r2}**。")
    say("- 两条都只影响预期与文档；模拟盘 / 执行器 / W2 / 股票池不改。")
    out = {"git": code, "dirty": dirty, "windows": W, "R1": r1, "R2": r2, "w2_gain_pit": w2d, "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {out['elapsed_s']} s）。非投资建议。")
    fp = paths.out_dir() / "pit_recheck"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
