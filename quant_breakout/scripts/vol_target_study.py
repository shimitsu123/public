"""vol_target_study.py — 指数仓位加「波动率管理」能否更好？（事先登记，跑之前写定，结果出来不改规则）

对象：现行进取档的主要收益来源 = 指数仓位（日本 1329 / 日経225，美国 SPYM / S&P500）。
数据：指数价格（US ^GSPC 1955～，JP ^N225 1975～）+ 估计股息（US 2.5%/年、JP 1.5%/年，按持仓比例计）
      + 现金利率（US 联邦基金 DFF；JP 日银コール O/N，1998 年前用 JGB 1 年）。决策在收盘，次日生效；
      换仓成本 0.05% × 仓位变动。
方案：
  B  现行：牛熊分界（250 日线 ±3%、连续 5 天）→ 熊市 0 仓，牛市满仓
  V1 波动率管理：仓位 = min(1, 目标波动 / 近 20 日实现波动)，变动 ≥ 0.10 才调整
  V2 B × V1：熊市 0 仓；牛市按 V1
  H  买入持有（参照）
  目标波动 = 训练期（≤2005）近 20 日实现波动的中位数（各市场各自算）。
检验期 2006-01～今天（样本外），前后两半 2006～2015 / 2016～。
采用条件（与本系统其他研究同口径）：检验期 Calmar ≥ B + 0.1，年化不低于 B 0.5pp 以上，前后两半 Calmar 都 ≥ B。
两者都达标取 Calmar 高者；都不达标维持 B。
输出 var/out/vol_target_study.md / .json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import factors as F                                            # noqa: E402
from qbreak import paths                                                    # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                    # noqa: E402
from bullbear_study import load                                             # noqa: E402

SPEC = {"US": ("^GSPC", "1955-01-01", 2.5), "JP": ("^N225", "1975-01-01", 1.5)}
TEST0, MID = "2006-01-01", "2016-01-01"
BAND, COST = 0.10, 0.0005
LINES: list[str] = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def cash_rate(m: str, D: pd.DatetimeIndex, lv: pd.DataFrame) -> pd.Series:
    import factor_study as FS
    if m == "US":
        r = FS.asof(lv["fed_funds"], D, 0)
    else:
        r = FS.asof(lv["boj_call"], D, 1).fillna(FS.asof(lv["jgb1y"], D, 1))
    return (r.fillna(0.0) / 100).clip(lower=-0.01)


def vol_weights(lr: pd.Series, target: float) -> pd.Series:
    vol = lr.rolling(20).std() * np.sqrt(252)
    raw = (target / vol).clip(upper=1.0).fillna(1.0).to_numpy()
    w, cur = np.empty(len(raw)), 1.0
    for i, x in enumerate(raw):
        if abs(x - cur) >= BAND or (x >= 0.999 and cur < 1.0):
            cur = x
        w[i] = cur
    return pd.Series(w, index=lr.index)


def simulate(close: pd.Series, w: pd.Series, cash: pd.Series, div_pct: float, start, end=None) -> pd.Series:
    r = close.pct_change().fillna(0.0)
    pos = w.shift(1).fillna(1.0)                                  # 收盘决定，次日生效
    ret = pos * (r + div_pct / 100 / 252) + (1 - pos) * cash.shift(1).fillna(0.0) / 252 - pos.diff().abs().fillna(0) * COST
    ret = ret[(ret.index >= pd.Timestamp(start)) & ((ret.index < pd.Timestamp(end)) if end else True)]
    return (1 + ret).cumprod()


def stats(eq: pd.Series, w: pd.Series | None = None) -> dict:
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = float((eq / eq.cummax() - 1).min())
    d = eq.pct_change().dropna()
    out = {"cagr": round(float(cagr) * 100, 2), "mdd": round(dd * 100, 1),
           "calmar": round(float(cagr) / abs(dd), 3) if dd < 0 else None,
           "sharpe": round(float(d.mean() / d.std() * np.sqrt(252)), 2)}
    if w is not None:
        ww = w.reindex(eq.index)
        out["avg_exposure"] = round(float(ww.mean()), 2)
        out["turnover_per_year"] = round(float(ww.diff().abs().sum() / yrs), 2)
    return out


def main() -> int:
    lv = F.macro_levels()
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    out = {}
    say(f"# 指数仓位的波动率管理（{pd.Timestamp.today().date()}，训练 ≤2005，检验 {TEST0}～）")
    for m, (sym, start, div) in SPEC.items():
        c = load(sym, "1950-01-01")["Close"]
        c = c[c.index >= pd.Timestamp(start) - pd.Timedelta(days=500)]
        lr = np.log(c).diff()
        vol = lr.rolling(20).std() * np.sqrt(252)
        target = float(vol[(vol.index >= start) & (vol.index < TEST0)].median())
        bull = pd.Series((np.asarray(det.states(c)) != BEAR).astype(float), index=c.index)
        vw = vol_weights(lr, target)
        W = {"B 现行牛熊择时": bull, "V1 波动率管理": vw, "V2 择时 × 波动率": bull * vw,
             "H 买入持有": pd.Series(1.0, index=c.index)}
        cash = cash_rate(m, c.index, lv)
        say(f"\n## {m}（{sym}，目标波动 {target * 100:.1f}%/年，股息估计 {div}%/年，现金 = {'联邦基金' if m == 'US' else '日银 O/N（1998 前 JGB1Y）'}）")
        say("| 方案 | 检验期 年化 | 最大回撤 | Calmar | 夏普 | 平均仓位 | 年换手 | 2006-15 Calmar | 2016- Calmar |")
        say("|---|---|---|---|---|---|---|---|---|")
        res = {}
        for k, w in W.items():
            full = stats(simulate(c, w, cash, div, TEST0), w)
            h1 = stats(simulate(c, w, cash, div, TEST0, MID))
            h2 = stats(simulate(c, w, cash, div, MID))
            res[k] = {**full, "h1_calmar": h1["calmar"], "h2_calmar": h2["calmar"]}
            say(f"| {k} | {full['cagr']}% | {full['mdd']}% | {full['calmar']} | {full['sharpe']} | "
                f"{full.get('avg_exposure')} | {full.get('turnover_per_year')} | {h1['calmar']} | {h2['calmar']} |")
        b = res["B 现行牛熊择时"]
        ok = [k for k in ("V1 波动率管理", "V2 择时 × 波动率")
              if (res[k]["calmar"] or -9) >= (b["calmar"] or -9) + 0.1 and res[k]["cagr"] >= b["cagr"] - 0.5
              and (res[k]["h1_calmar"] or -9) >= (b["h1_calmar"] or -9) and (res[k]["h2_calmar"] or -9) >= (b["h2_calmar"] or -9)]
        pick = max(ok, key=lambda k: res[k]["calmar"]) if ok else "B 现行牛熊择时"
        say(f"判定（事先规则）：{pick}")
        out[m] = {"target_vol": round(target, 4), "results": res, "pick": pick}
    fp = paths.out_dir() / "vol_target_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
