"""loop9_r07_sentliq.py — 第九个研究循环（选股成功率）第 7 轮：隔夜情绪 ONS、成交额波动 LVV
（2026-10-04 登记；先提交后只运行一次；用掉 2 个做法 → 13 / 20；新家族「选股·隔夜情绪」1 / 3、「选股·成交额波动」1 / 3）。

循环的规则：scripts/research_loop9.py；共用：scripts/loop9_common.py；复用第 1 轮的纯函数（scripts/loop9_r01_market.py：b3_trade_keys）。
来历（照实写）：第 6 轮运行前开了一次文献检索（只查论文、不碰本仓库的任何结果文件），要找「与第一〜九个循环都不同、2001〜2026 用价量就能算」的选股条件；
  结论是「在这个设定下先验想法基本用完」，只剩 3 个弱 / 很弱的候选（另 6 个查过后排除：salience、配对偏离、CGO、Nikkei 超配股、36 个月市场状态、VRP）。
  本轮取其中两个（第三个「对 VIX 的 β」没有日本证据、ID 也与第二个循环的 VXB 重名 → 不登记、不占名额）。都不是任何一轮结果的变体（S7 不适用）。
为什么：
  - ONS（隔夜情绪）：Aboody, Even-Tov, Lehavy & Trueman（2018，JFQA 53(2)）：散户情绪集中在开盘前，隔夜收益高的票之后相对回落。
    规则：信号日上一个完整日历月里（至少 15 个交易日），每天隔夜收益（开盘 ÷ 前一天收盘 − 1）的平均在池子里排前 10%（百分位 > 0.9）→ 不买。
    照实写：论文按年排序、持有 12 个月；这里改成「信号日的上一个月」—— 这是唯一的改动，登记时写明。日本证据混合（Lou, Polk & Skouras 2019 在含日本的
    9 个市场复现了隔夜 / 日内两段各自延续、互相反转；同类信号在日本不预测收益：Hajiyev, Keiber & Luczak 2024）→ 先验弱。
    与 GPT（买入那天开盘跳空）、C 的 gap（信号日自己的跳空）不同：这里是一个月的累计。
  - LVV（成交额波动）：Chordia, Subrahmanyam & Anshuman（2001，JFE 59(1)）：成交额忽大忽小（间歇的关注 / 投机）的票之后收益低；日本：Chang, Faff & Hwang
    （2010，PBFJ 18(1)）东证各市场都显著为负。照实写：Hou, Xue & Zhang（2020，RFS 33(5)）按大盘股口径复现不显著 → 大型股（日経225）先验很弱。
    规则：截至上月末 6 个月的日成交额（收盘 × 成交量，円）的变异系数（标准差 ÷ 平均，至少 50 天）在池子里排前 10% → 不买。
做法：都按个股挡（kind = "stock"）：（票, 信号日）成立 → em_tick 0；其余全部同 B3。阈值（上个月、15 天、前 10%；6 个月、50 天、前 10%）一次写定（S6 不适用）；S5、S8 适用。
  - 都在「那个池子」里排：Z / E / J 用各自账户的日経225 池子，W / Jx 用各自的池子；都只用上个月月底以前的数据（不用信号日当月的数据）。
  - 数据清洗（与 qbreak/data.repair_jp_artifacts 同一个门槛，一次写定）：开盘 ÷ 前一天收盘在 0.6〜1.7 之外 → 当作坏数据不用；成交量 0 → 当作没有。
S5：W / Jx 里 B3 会买的信号按同样的定义挡。第二关（第一关全过的才做；另行登记）：kind = stock（逐个信号随机挡，同样比例；种子 [20261004, s]）。
登记前的规模核对与接线核对（只数个数、不看收益；2026-10-04）：ONS 挡掉 W2 信号 Z 4 / 97、E 5 / 155、J 7 / 173，碰到 B3 成交 0 / 0 / 2；W 16 / 438、Jx 25 / 792。
  LVV 挡掉 7 / 9 / 7，碰到成交 2 / 2 / 2；W 37、Jx 50。三个年代「空集合 = B3」✓。
事前预期（写在看结果之前；按上面的个数改写过一次，照实写）：两个都只碰到很少的成交（ONS 2 笔、LVV 6 笔）→ 账户的差很小，S1（合计 ≥ +0.03）很难过；
  文献先验弱 / 很弱 → 第一关各约 1〜2%；「更好候选」各约 0.2%。照实写：前 6 轮的读法是「账户层的判定对少量成交接近抛硬币、真正有信息的是 W / Jx」，
  而这里 W / Jx 也只挡到 16〜50 个。
运行：python scripts/loop9_r07_sentliq.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop9_r07_sentliq.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop9_common as C9                                                    # noqa: E402
import loop9_r01_market as R1                                                # noqa: E402
import research_loop9 as R9                                                  # noqa: E402

ROUND = 7
IDS = ("ONS", "LVV")
FAMILY = {"ONS": "选股·隔夜情绪", "LVV": "选股·成交额波动"}
KINDS = {"ONS": "stock", "LVV": "stock"}
POSTHOC = False
ON_MIN, TOP = 15, 0.9
LV_MONTHS, LV_MIN = 6, 50
OPEN_OK = (0.6, 1.7)
OUT = "loop9_r07_sentliq"


# ───────────────────────── 纯函数（tests/test_loop9_r07.py） ─────────────────────────
def overnight_returns(fa: dict) -> pd.DataFrame:
    """日期 × 票：开盘 ÷ 前一根 K 线收盘 − 1（各票自己的前一根；比值在 OPEN_OK 之外 → NaN）。"""
    out = {}
    for t, df in fa.items():
        o, c = df["Open"].astype(float), df["Close"].astype(float).shift(1)
        r = o / c
        out[t] = (r - 1).where((r >= OPEN_OK[0]) & (r <= OPEN_OK[1]))
    return pd.DataFrame(out).sort_index()


def monthly_mean(R: pd.DataFrame, min_n: int = ON_MIN) -> pd.DataFrame:
    """月 × 票：那个月的平均（有效天数 < min_n → NaN）。索引 = 月（Period）。"""
    g = R.groupby(R.index.to_period("M"))
    return g.mean().where(g.count() >= min_n)


def turnover_value(fa: dict) -> pd.DataFrame:
    """日期 × 票：收盘 × 成交量（円；成交量 0 → NaN）。"""
    V = pd.DataFrame({t: (df["Close"].astype(float) * df["Volume"].astype(float)) for t, df in fa.items()}).sort_index()
    return V.where(V > 0)


def cv_months(TV: pd.DataFrame, months: int = LV_MONTHS, min_n: int = LV_MIN) -> pd.DataFrame:
    """月 × 票：截至这个月月底的 months 个月里日成交额的变异系数（样本标准差 ÷ 平均；有效天数 < min_n → NaN）。"""
    per = TV.index.to_period("M")
    g = TV.groupby(per)
    n, s, ss = g.count(), g.sum(), (TV ** 2).groupby(per).sum()
    n6, s6, ss6 = (x.rolling(months, min_periods=months).sum() for x in (n, s, ss))
    mean = s6 / n6
    var = (ss6 - s6 ** 2 / n6) / (n6 - 1)
    cv = np.sqrt(var.clip(lower=0)) / mean
    return cv.where(n6 >= min_n)


def month_pct(M: pd.DataFrame) -> pd.DataFrame:
    return M.rank(axis=1, pct=True)


def prev_month_gate(tickers, dates, P: pd.DataFrame, top: float = TOP) -> np.ndarray:
    """（票, 信号日 d）：d 的上一个日历月的百分位 > top → True；没有 → 不挡。"""
    out = np.zeros(len(tickers), bool)
    cols = set(P.columns)
    for i, (t, d) in enumerate(zip(tickers, pd.to_datetime(np.asarray(dates)))):
        m = d.to_period("M") - 1
        if t not in cols or m not in P.index:
            continue
        v = P.at[m, t]
        out[i] = bool(np.isfinite(v) and v > top)
    return out


# ───────────────────────── 输入 ─────────────────────────
def pool_pcts(fa: dict) -> dict:
    return {"ONS": month_pct(monthly_mean(overnight_returns(fa))), "LVV": month_pct(cv_months(turnover_value(fa)))}


def gates(W: dict):
    out = {k: {} for k in IDS}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        P = pool_pcts(W["SM"][e]["fa"])
        for k in IDS:
            out[k][e] = prev_month_gate(S["ticker"].to_numpy(), S["date"].to_numpy(), P[k])
    return out


def other_fns() -> dict:
    cache: dict = {}

    def fn_of(k):
        def fn(s, X, fa):
            if s not in cache:
                cache[s] = pool_pcts(fa)
            return prev_month_gate(X["ticker"].to_numpy(), X["date"].to_numpy(), cache[s][k])
        return fn
    return {k: fn_of(k) for k in IDS}


def scale(W: dict, g: dict) -> dict:
    out = {}
    for e in C9.ERAS:
        S = C9.signals(W, e)
        idx = {(str(t), pd.Timestamp(d)): i for i, (t, d) in enumerate(zip(S["ticker"], S["date"]))}
        pos = [idx.get(k) for k in R1.b3_trade_keys(W, e)]
        out[e] = {"signals": len(S), "b3_trades": len(pos),
                  **{k: {"signals_blocked": int(np.asarray(g[k][e]).sum()),
                         "trades_blocked": int(sum(bool(g[k][e][i]) for i in pos if i is not None))} for k in IDS}}
    return out


def other_scale(W: dict, fns: dict) -> dict:
    import combo_all_common as CA
    out = {}
    for s, fold, sm in C9.OTHER:
        D = W["D"][s]
        X = D[CA.apply_c(W["c_fold"][fold], D)].reset_index(drop=True)
        out[s] = {"n": len(X), **{k: int(np.asarray(fn(s, X, W["SM"][sm]["fa"])).sum()) for k, fn in fns.items()}}
    return out


def wiring() -> int:
    t0 = time.time()
    W = C9.load()
    g = gates(W)
    ok = True
    for e in C9.ERAS:
        base = C9.acct(C9.L6.run(W, e))
        empty = C9.acct(C9.run_block(W, e, np.zeros(len(C9.signals(W, e)), bool)))
        same = all((base[k] == empty[k]) or (base[k] is not None and empty[k] is not None and abs(float(base[k]) - float(empty[k])) < 1e-12)
                   for k in C9.KEYS)
        S = C9.signals(W, e)
        n = {k: len(C9.tick_of(S["ticker"], S["date"], g[k][e])) for k in IDS}
        ok &= same and all(v > 0 for v in n.values())
        print(f"{e}：空集合 = B3 {'✓' if same else '✗'}；em_tick 对数 " + "、".join(f"{k} {v}" for k, v in n.items()), flush=True)
    print("规模（只数个数）：" + json.dumps(scale(W, g), ensure_ascii=False))
    print("W / Jx（只数个数）：" + json.dumps(other_scale(W, other_fns()), ensure_ascii=False))
    print(f"接线核对 {'通过' if ok else '不通过'}（{time.time() - t0:.0f}s）")
    return 0 if ok else 2


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = C9.git_head("scripts/loop9_r07_sentliq.py", "scripts/loop9_r01_market.py")
    W = C9.load()
    g = gates(W)
    print(f"闸门算完（{time.time() - t0:.0f}s）", flush=True)
    r = C9.stage_one(W, g, other_fns(), posthoc=None, log=lambda m: print(m, flush=True))
    reg = R9.load_state().get("baseline") or {}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or r["base"][e]["calmar"] is None
                 else round(r["base"][e]["calmar"] - reg[e]["calmar"], 4)) for e in C9.ERAS}
    res = {"loop": 9, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KINDS, "code": code, "dirty": dirty,
           **r, "drift": drift, "scale": scale(W, g), "seconds": round(time.time() - t0)}
    text = C9.render(res, f"# 第九个研究循环第 {ROUND} 轮：ONS 上个月隔夜收益在池子前 10% 不买 / LVV 6 个月成交额变异系数在池子前 10% 不买（第一关；规则见脚本开头）")
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环第 7 轮：ONS / LVV（第一关）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
