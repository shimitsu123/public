"""era_outlook.py — 时代主线展望：现在哪些行业 / 业种 / 主题处在「最近 12 个月领先」（只描述，不是买卖建议；2026-09-27）。

依据（era_study 登记 825bd56 的结果）：美国 49 行业 1926〜2026，过去 12 个月（跳过最近 1 个月）最强的 10 个行业之后一个月平均每年比全部行业等权
多 +3.65%（t 4.34，1931〜1962 / 1963〜1994 / 1995〜2026 三段都为正）；日本東証 33 业种两段 +4.7% / +4.9%（t 1.5 / 2.4）。
但 3〜10 年的领先反而反转（过去 5 年前 10 名之后 5 年仍在前 10 名的只有 19%，随机 22%）→「时代」只能用最近 12 个月认出来，
看得很清楚的长期冠军之后平均反而落后。所以这里的「未来」= 之后几个月〜1 年左右，每个月用新数据重排（= 跟着时代自己更新）。
内容：
  美国 49 行业（Ken French）M12 前 10 / 后 10；「长期冠军但最近转弱」（过去 60 个月前 10、过去 12 个月不在前 20）= 反转风险；
  日本東証 33 业种（J-Quants 全部股票，时价总额加权）M12 前 7 / 后 7；12 个主题（qbreak/themes.py，成员等权）M12 排名；
  前几名业种 / 主题里日経225 股票池（立花能买）的成员按各自 12-1 个月涨幅排的前几只（只是「这个板块里谁最强」的观察名单）。
输出：var/out/era_outlook.md / .json（只有统计；不含 J-Quants 原始数据）。
--review：时代主线前向记录（qbreak/era_forward.py，2026-10 起每月一次）的复核 → var/out/era_forward_review.md / .json + 历史（只追加）。
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import era_study as ES                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak.us_industry import FF49_CN                                       # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def dot(s: str) -> str:
    """業種名的中点统一成全角（J-Quants 用半角「･」，JPX 用「・」）。"""
    return str(s).replace("･", "・")


def m12_rank(R: pd.DataFrame) -> pd.Series:
    """最后一行的 M12 分数（第 t−11 … t−1 个月的累计对数收益 %；跳过最后一个月）；从高到低。"""
    return ES.past_log(R, 12).iloc[-1].dropna().sort_values(ascending=False)


def theme_returns_jq(A: dict) -> pd.DataFrame:
    """12 个主题：成员（J-Quants 调整后收盘）月收益等权 %。"""
    from qbreak import themes as TH
    days, names = A["days"], A["names"]
    col = {t: j for j, t in enumerate(names)}
    ends = pd.Series(days, index=days).groupby(days.to_period("M")).last()
    ei = days.get_indexer(pd.DatetimeIndex(ends.to_numpy()))
    C = A["C"][ei].astype(float)
    r = (C[1:] / C[:-1] - 1) * 100
    idx = pd.DatetimeIndex(ends.to_numpy()[1:]).to_period("M").to_timestamp()
    out = {}
    for k, (cn, ja, codes, _) in TH.THEMES.items():
        js = [col[f"{c}.T"] for c in codes if f"{c}.T" in col]
        if len(js) >= TH.MIN_MEMBERS:
            x = r[:, js]
            n = np.isfinite(x).sum(axis=1)
            out[f"{k} {cn}"] = np.where(n >= TH.MIN_MEMBERS, np.nansum(x, axis=1) / np.maximum(n, 1), np.nan)
    return pd.DataFrame(out, index=idx)


def stock_m12(A: dict) -> pd.Series:
    """每只票最后一行的 12-1 个月涨幅 %（月末收盘；跳过最后一个月）。"""
    days = A["days"]
    ends = pd.Series(days, index=days).groupby(days.to_period("M")).last()
    ei = days.get_indexer(pd.DatetimeIndex(ends.to_numpy()))
    C = A["C"][ei].astype(float)
    if len(C) < 13:
        return pd.Series(dtype=float)
    v = (C[-2] / C[-13] - 1) * 100
    return pd.Series(v, index=A["names"]).dropna()


def main() -> int:
    import allstock_data as AD
    from qbreak import factors as F
    from qbreak import themes as TH
    from qbreak.config import universe
    t0 = time.time()
    R = F.ff_industries(49, "vw")
    us = m12_rank(R)
    us60 = ES.past_log(R, 60).iloc[-1].dropna().sort_values(ascending=False)
    cn = lambda c: f"{c}（{FF49_CN.get(c, c)}）"                                                 # noqa: E731
    A = AD.load()
    RJ = ES.jp_sector_returns_jq()
    RJ.columns = [dot(c) for c in RJ.columns]
    jp = m12_rank(RJ)
    RT = theme_returns_jq(A)
    th = m12_rank(RT)
    sm = stock_m12(A)
    jn = json.loads((paths.home() / "jpx_names.json").read_text(encoding="utf-8"))                # JPX 公开的名称快照（不用 J-Quants 的原始数据）
    jn = jn.get("names", jn)
    name = {f"{c}.T": (v.get("name", "") if isinstance(v, dict) else str(v)) for c, v in jn.items()}
    s33 = json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"]       # JPX 的 33 业种
    sec = {f"{c}.T": dot(v) for c, v in s33.items()}
    pool = set(universe("JP", "broad"))
    out = {"asof_us": str(R.index[-1].date()), "asof_jp": str(RJ.index[-1].date()),
           "us_top": [(k, float(v)) for k, v in us.iloc[:10].items()], "us_bottom": [(k, float(v)) for k, v in us.iloc[-10:].items()],
           "us_fading": [k for k in us60.index[:10] if k not in set(us.index[:20])],
           "jp_top": [(k, float(v)) for k, v in jp.iloc[:7].items()], "jp_bottom": [(k, float(v)) for k, v in jp.iloc[-7:].items()],
           "themes": [(k, float(v)) for k, v in th.items()], "watch": {}}
    say("# 时代主线展望：现在「最近 12 个月领先」的行业 / 业种 / 主题（只描述，不是买卖建议）")
    say(f"依据与读法见 scripts/era_outlook.py 开头。美国数据到 {R.index[-1]:%Y-%m}（Ken French，约晚 1 个月）；日本到 {RJ.index[-1]:%Y-%m}"
        "（J-Quants；最后一个月跳过不算）。分数 = 12-1 个月的累计对数收益 %。")
    say("\n## 美国 49 行业")
    say("- 领先（前 10）：" + "、".join(f"{cn(k)} {v:+.0f}" for k, v in out["us_top"]))
    say("- 落后（后 10）：" + "、".join(f"{cn(k)} {v:+.0f}" for k, v in out["us_bottom"]))
    say("- 长期冠军但最近转弱（过去 60 个月前 10、过去 12 个月不在前 20 → 历史上反转的风险最大）：" + ("、".join(cn(k) for k in out["us_fading"]) or "无"))
    say("\n## 日本東証 33 业种（J-Quants 全部股票，时价总额加权）")
    say("- 领先（前 7）：" + "、".join(f"{k} {v:+.0f}" for k, v in out["jp_top"]))
    say("- 落后（后 7）：" + "、".join(f"{k} {v:+.0f}" for k, v in out["jp_bottom"]))
    say("\n## 日本 12 个主题（成员等权；AI 链 = T3〜T7、T9〜T11）")
    for k, v in th.items():
        say(f"- {k}：{v:+.0f}")
    say("\n## 领先业种 / 主题里，日経225 股票池（立花能买）各自 12-1 个月涨幅最高的几只（观察名单，不是买卖建议）")
    for k, _ in out["jp_top"][:5]:
        mem = [t for t in pool if sec.get(t) == k and t in sm.index]
        top = sm.reindex(mem).dropna().sort_values(ascending=False)[:4]
        out["watch"][k] = [(t, name.get(t, ""), float(v)) for t, v in top.items()]
        say(f"- {k}：" + ("、".join(f"{t.split('.')[0]} {name.get(t, '')} {v:+.0f}%" for t, v in top.items()) or "股票池里没有"))
    for k, _ in list(th.items())[:3]:
        code = k.split()[0]
        mem = [f"{c}.T" for c in TH.THEMES[code][2] if f"{c}.T" in pool and f"{c}.T" in sm.index]
        top = sm.reindex(mem).dropna().sort_values(ascending=False)[:4]
        out["watch"][k] = [(t, name.get(t, ""), float(v)) for t, v in top.items()]
        say(f"- {k}：" + ("、".join(f"{t.split('.')[0]} {name.get(t, '')} {v:+.0f}%" for t, v in top.items()) or "股票池里没有"))
    say("\n读法：历史上这些「最近 12 个月领先」的板块之后平均还会跑赢，但不是每个月都赢 —— 前 10 / 前 7 组合比全部平均好的月份："
        "美国 1931〜2026 58%（按 12 个月算 70%）、日本 2006〜2016 57%（68%）、2016〜2026 61%（83%）；"
        "领先 3〜5 年以上的板块之后平均反而落后。每个月会用新数据重排；个股层的交易规则不因为这个排名改变（evolve_study 的 V5 另外检验）。")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "era_outlook"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


def review() -> int:
    """时代主线前向记录的复核（规则见 qbreak/era_forward.py 开头）：只读 var/out/era_forward.csv，不改、不补写。"""
    import math
    from qbreak import era_forward as EF
    from qbreak import factors as F
    from qbreak import theme_monitor as TM
    from qbreak import themes as TH
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    t0 = time.time()
    fp = paths.out_dir() / EF.LOG_FILE
    say(f"# 时代主线前向记录复核（{pd.Timestamp.today().date()}）")
    if not fp.exists():
        say("还没有记录（2026-10 第一次运行起每月记一次）。")
        _write("era_forward_review", {"n": 0})
        return 0
    log = pd.read_csv(fp, dtype={"asof": str, "group": str, "market": str})
    starts = [pd.Timestamp(a + "-01") if "Q" not in a else pd.Period(a, freq="Q").start_time for a in log["asof"].unique()]
    first = min(starts)
    years = max(3, math.ceil((pd.Timestamp.today() - first).days / 365) + 2)
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    want = sorted(set(s33) | {f"{c}.T" for c in TH.members()})
    data = load_universe(want, DataConfig(provider="yfinance", years=min(21, years), allow_synthetic=False).validate())
    _, rel, _ = TM.group_panel(TM.log_returns(data), s33)
    relm = rel.groupby(rel.index.to_period("M")).sum(min_count=10)
    relm.index = [str(p) for p in relm.index]
    relq = rel.groupby(rel.index.to_period("Q")).sum(min_count=40)                  # 3 个月判定的复核用（季度相对收益）
    relq.index = [f"{p.year}Q{p.quarter}" for p in relq.index]
    R = F.ff_industries(49, "vw")
    L = np.log1p(R / 100.0) * 100
    relu = L.sub(L.mean(axis=1), axis=0)
    relu.index = [str(d)[:7] for d in relu.index]
    out = {}
    for mk, rm, name in (("JP-S33", relm, "日本東証业种 前 7"), ("JP-TH", relm, "日本主题 前 3"), ("US-FF49", relu, "美国 49 行业 前 10")):
        s1, s12 = EF.score_next(log, rm, mk, 1), EF.score_next(log, rm, mk, 12)
        j1, j12 = EF.judge(s1), EF.judge(s12)
        out[mk] = {"next1": j1, "next12": j12, "months_logged": int(log[log["market"] == mk]["asof"].nunique())}
        fa = lambda v, f="{:+.2f}": "—" if v is None else f.format(v)                              # noqa: E731
        say(f"- {name}：记了 {out[mk]['months_logged']} 个月；之后 1 个月的相对收益 {j1['n']} 个月 平均 {fa(j1['mean'])}%"
            f"（比平均好的月份 {fa(j1['hit'], '{:.0f}')}%，95% 区间 {fa(j1.get('lo95'))}〜{fa(j1.get('hi95'))}）；"
            f"之后 12 个月 {j12['n']} 个 平均 {fa(j12['mean'])}%")
        if mk == "JP-S33":
            say("  判定：" + ("**失效**（记满 36 个月、95% 区间上限 < 0 → 日报不再叫它时代主线、要重新研究；改日报要用户确认）" if j1["failed"]
                            else ("未失效" if j1["judged"] else f"只报告进度（记满 {EF.JUDGE_MONTHS} 个月才判定）")))
    for mk, name in (("JP-S33Q", "日本東证业种 3 个月判定 前 7"), ("JP-THQ", "日本主题 3 个月判定 前 3")):
        s1 = EF.score_next(log, relq, mk, 1)
        j1 = EF.judge(s1, EF.JUDGE_QUARTERS)
        out[mk] = {"next1": j1, "quarters_logged": int(log[log["market"] == mk]["asof"].nunique())}
        fa = lambda v, f="{:+.2f}": "—" if v is None else f.format(v)                              # noqa: E731
        say(f"- {name}：记了 {out[mk]['quarters_logged']} 个季度；下一季的相对收益 {j1['n']} 个季度 平均 {fa(j1['mean'])}%"
            f"（比平均好的季度 {fa(j1['hit'], '{:.0f}')}%，95% 区间 {fa(j1.get('lo95'))}〜{fa(j1.get('hi95'))}）")
        if mk == "JP-S33Q":
            say("  判定：" + ("**失效**（记满 12 个季度、95% 区间上限 < 0 → 3 个月的主线在新数据里不延续；改日报要用户确认）" if j1["failed"]
                            else ("未失效" if j1["judged"] else f"只报告进度（记满 {EF.JUDGE_QUARTERS} 个季度才判定）")))
    inf = log[log["market"] == "JP-INFQ"]
    if len(inf):
        last_q = sorted(inf["asof"].unique())[-1]
        top = inf[inf["asof"] == last_q].sort_values("rank").head(5)
        say(f"- 影响占比（{last_q}）：" + "、".join(f"{g} {v:.1f}%" for g, v in zip(top["group"], top["score"])))
    say(f"\n用时 {time.time() - t0:.0f}s")
    _write("era_forward_review", out)
    hist = paths.out_dir() / "era_forward_review_history.csv"
    row = {"run": str(pd.Timestamp.today().date()), **{f"{k}_n": v["next1"]["n"] for k, v in out.items()},
           **{f"{k}_mean": v["next1"]["mean"] for k, v in out.items()}, "failed": out.get("JP-S33", {}).get("next1", {}).get("failed")}
    old = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
    pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(hist, index=False)       # 只追加
    return 0


def _write(stem: str, obj: dict) -> None:
    fp = paths.out_dir() / stem
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(review() if "--review" in sys.argv else main())
