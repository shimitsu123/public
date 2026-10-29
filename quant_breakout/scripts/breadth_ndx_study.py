"""breadth_ndx_study.py — 行业分化（美国 49 行业的宽度）→ 之后的纳指 100（核心 ETF 1545 的标的）（2026-10-11 登记；先提交后只运行一次）。

用户（2026-10-11）：「纳斯达克 ETF 的指数是根据各个行业推算出来的，根据每个行业的影响占比和现在该行业的趋势横展开，应该可以得出一定区间内 ETF 的走向」
→「做行业分化研究」。指数 = 各行业加权和（恒等式），加权趋势 ≈ 指数自己的趋势（现行 S&P500 牛熊分界已经在用、纳指自己的趋势 NXC 今天没通过）；
加权和之外的新信息只有「涨得宽 / 窄」（多少行业跟着涨）。以前相近的：日本突破的市场宽度确认 B1〜B4、成分股离散度 DSP、时代主线 M12（都没通过）。

一、宽度 B(d)：Ken French 49 行业（价值加权、日收益、CRSP；var/cache/ff_daily/，不入库）各自累计成 指数，收在自己 200 日简单均线上方的比例（0〜1）。参数事先定、不调。
二、样本：每个美国交易月的最后一个交易日 d（49 行业与纳指都有数），只取美股牛市（equity_idle_study.bears 的 US = False，即现行的 S&P500 牛熊分界）。
三、目标：纳指 100 总收益（美元，equity_idle_study.ndx_tr）d → d + 63 个交易日的收益。
四、主判定：秩相关 IC = corr(rank B, rank 之后 63 日收益)（预期为正：涨得越宽越好）。
  **有信息** = 1987-01〜2005-12 的 IC > 0 且 2006-01〜2026-05 的 IC > 0，且 2006〜2026 只用不重叠的季度月末（3 / 6 / 9 / 12 月）样本、
  B 与之后 63 日收益的秩相关做 Fisher z 检验（正态近似）单侧 p < 0.10。
  否则「没有信息」→ 停。有信息 → 另行登记规则（例：牛市里宽度 < 某水平时核心 ETF 先卖 1/3），按第六个循环的两关判定。
五、只描述（不参与判定）：控制纳指自己 12 个月动量后的偏相关（秩残差）；宽度 < 50% 与 ≥ 50% 时之后 63 日平均收益与个数（两段）；
  最新一个月末的宽度。
事前预期：宽度的说法在美国证据偏弱；指数涨得窄的时期（1998〜99、2020〜24 的大型科技）之后有时继续涨 → 大概率没有信息。
运行：python scripts/breadth_ndx_study.py → var/out/breadth_ndx_study.md / .json（只有汇总数字）。非投资建议。
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = "breadth_ndx_study"
MA_N, H = 200, 63
TRAIN, TEST = ("1987-01-01", "2005-12-31"), ("2006-01-01", "2026-05-31")
P_MAX = 0.10


# ───────────────────────── 规则（纯函数，tests/test_breadth_ndx_study.py） ─────────────────────────
def breadth(R_pct: pd.DataFrame, n: int = MA_N) -> pd.Series:
    """行业日收益（%）→ 每天收在自己 n 日均线上方的行业比例（均线算得出的行业里）。"""
    lv = (1 + R_pct.fillna(0) / 100).cumprod()
    ma = lv.rolling(n, min_periods=n).mean()
    ok = ma.notna()
    return ((lv > ma) & ok).sum(axis=1) / ok.sum(axis=1).replace(0, np.nan)


def sample(B: pd.Series, tr: pd.Series, bear: pd.Series) -> pd.DataFrame:
    """每个月最后一个共同交易日 d（美股牛）→ {B, fwd（之后 H 日收益）, mom12（之前 252 日收益）}。"""
    days = B.dropna().index.intersection(tr.dropna().index)
    tr = tr.reindex(days)
    fwd = tr.shift(-H) / tr - 1
    mom = tr / tr.shift(252) - 1
    me = pd.Series(days, index=days).groupby(days.to_period("M")).max()
    rows = []
    for d in me.values:
        d = pd.Timestamp(d)
        b = bear.reindex([d], method="ffill").iloc[0] if len(bear) else False
        if bool(b) or not np.isfinite(fwd.get(d, np.nan)):
            continue
        rows.append({"d": d, "B": float(B[d]), "fwd": float(fwd[d]), "mom12": float(mom.get(d, np.nan))})
    return pd.DataFrame(rows).set_index("d") if rows else pd.DataFrame(columns=["B", "fwd", "mom12"])


def rank_ic(x: pd.Series, y: pd.Series) -> float:
    m = x.notna() & y.notna()
    return float(x[m].rank().corr(y[m].rank())) if m.sum() >= 5 else float("nan")


def fisher_p(r: float, n: int) -> float | None:
    """单侧（r > 0）的 Fisher z 检验 p（正态近似）。"""
    if n <= 3 or not np.isfinite(r) or abs(r) >= 1:
        return None
    z = math.atanh(r) * math.sqrt(n - 3)
    return 0.5 * math.erfc(z / math.sqrt(2))


def verdict(S: pd.DataFrame) -> dict:
    tr = S[(S.index >= pd.Timestamp(TRAIN[0])) & (S.index <= pd.Timestamp(TRAIN[1]))]
    te = S[(S.index >= pd.Timestamp(TEST[0])) & (S.index <= pd.Timestamp(TEST[1]))]
    q = te[te.index.month.isin([3, 6, 9, 12])]
    ic_tr, ic_te, ic_q = rank_ic(tr["B"], tr["fwd"]), rank_ic(te["B"], te["fwd"]), rank_ic(q["B"], q["fwd"])
    p = fisher_p(ic_q, len(q))
    ok = bool(np.isfinite(ic_tr) and np.isfinite(ic_te) and ic_tr > 0 and ic_te > 0 and p is not None and p < P_MAX)
    return {"ic_train": round(ic_tr, 4), "ic_test": round(ic_te, 4), "ic_test_q": round(ic_q, 4), "n_train": len(tr), "n_test": len(te),
            "n_q": len(q), "p": None if p is None else round(p, 4), "info": ok}


def partial_ic(S: pd.DataFrame) -> float:
    """控制 12 个月动量：B 与 fwd 各自对 mom12 的秩做线性回归后的残差相关。"""
    s = S.dropna()
    if len(s) < 10:
        return float("nan")
    rb, rf, rm = s["B"].rank(), s["fwd"].rank(), s["mom12"].rank()

    def resid(y):
        X = np.c_[np.ones(len(rm)), rm.to_numpy()]
        beta = np.linalg.lstsq(X, y.to_numpy(), rcond=None)[0]
        return y.to_numpy() - X @ beta
    return float(np.corrcoef(resid(rb), resid(rf))[0, 1])


def main() -> int:
    import equity_idle_study as EI
    import report_judgment_backtest as R
    from qbreak import paths
    t0 = time.time()
    B = breadth(R.ff49_daily())
    inp = EI.load_inputs()
    tr = EI.ndx_tr(inp)
    bear = EI.bears(inp)["US"].astype(bool)
    S = sample(B, tr, bear)
    res = {"study": OUT, "verdict": verdict(S)}
    desc = {}
    for tag, (a, b) in (("train", TRAIN), ("test", TEST)):
        s = S[(S.index >= pd.Timestamp(a)) & (S.index <= pd.Timestamp(b))]
        lo, hi = s[s["B"] < 0.5], s[s["B"] >= 0.5]
        desc[tag] = {"partial_ic": round(partial_ic(s), 4),
                     "narrow": {"n": len(lo), "fwd_pct": round(float(lo["fwd"].mean() * 100), 2) if len(lo) else None},
                     "broad": {"n": len(hi), "fwd_pct": round(float(hi["fwd"].mean() * 100), 2) if len(hi) else None}}
    res["desc"] = desc
    res["latest"] = {"date": str(B.dropna().index[-1].date()), "breadth": round(float(B.dropna().iloc[-1]), 3)}
    res["seconds"] = round(time.time() - t0)
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    v, d = res["verdict"], res["desc"]
    L = [f"# 行业分化（美国 49 行业的宽度）→ 之后 3 个月的纳指 100（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/breadth_ndx_study.py 开头）", "",
         f"**{'有信息 → 另行登记规则检验' if v['info'] else '没有信息 → 停'}**：美股牛市的月末，宽度与之后 63 日收益的秩相关 1987〜2005 {v['ic_train']:+.4f}（{v['n_train']} 个月）、"
         f"2006〜2026 {v['ic_test']:+.4f}（{v['n_test']}）；2006〜 不重叠季度 {v['ic_test_q']:+.4f}（{v['n_q']} 个）单侧 p = {v['p']}（要 < {P_MAX}，两段都 > 0）", "",
         "只描述：", ""]
    for tag, nm in (("train", "1987〜2005"), ("test", "2006〜2026")):
        x = d[tag]
        L.append(f"- {nm}：控制 12 个月动量后的偏相关 {x['partial_ic']:+.4f}；宽度 < 50%（窄）之后 3 个月平均 {x['narrow']['fwd_pct']}%（{x['narrow']['n']} 个月）、"
                 f"≥ 50%（宽）{x['broad']['fwd_pct']}%（{x['broad']['n']} 个月）")
    L += [f"- 最新：{res['latest']['date']} 的宽度 {res['latest']['breadth'] * 100:.0f}%（49 行业里收在 200 日线上方的比例）", "",
          f"只研究，不改模拟盘 / 执行器。用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
