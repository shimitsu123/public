"""bear_sleeve_study.py — 熊市状态下用什么算法（指数层面，60 年以上数据）。

只在分界算法判定为「熊」的日子里比较（牛市日子里 = 现金，不计入）：
  BA0 现金
  BA1 1 倍反向，熊市全程持有（宣布熊 → 次日买；宣布牛 → 次日卖）
  BA2 1 倍反向 + 从持有期最高点回撤 10% 止损，止损后本段熊市不再进
  BA3 超跌反弹（Connors）：RSI(2) < 10 次日收盘买指数，收盘 > 5 日均线次日收盘卖，熊市结束强制卖
  BA4 BA3 + 买入后跌 8% 止损
事先登记的选择规则：训练期（≤2005）两个指数的「熊市状态内」收益都 > 0 且 Calmar 最高者；
都不满足 → 现金。样本外 2006～ 报告。反向的成本用 2006 年后实测校准的年化拖累（JP 2.5%，US −0.57%）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                            # noqa: E402
from qbreak.bullbear import Detector, load_config                  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bullbear_study import SYM, TRAIN, TEST, load                  # noqa: E402

INV_DRAG = {"JP": 2.50, "US": -0.57}


def rsi2(c: pd.Series) -> np.ndarray:
    d = c.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    au, ad = up.ewm(alpha=1 / 2, adjust=False).mean(), dn.ewm(alpha=1 / 2, adjust=False).mean()
    rs = au / ad.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100).values


def sleeve_returns(close: pd.Series, bear: np.ndarray, kind: str, market: str) -> np.ndarray:
    """逐日收益（收盘到收盘；信号在 t 收盘，t+1 收盘起持有 → 保守，不吃隔夜跳空）。"""
    r = close.pct_change().fillna(0).values
    n = len(r)
    out = np.zeros(n)
    if kind == "BA0":
        return out
    if kind in ("BA1", "BA2"):
        drag = INV_DRAG[market] / 100 / 252
        hold, stopped, val, peak = False, False, 1.0, 1.0
        for t in range(1, n):
            if hold:
                out[t] = -r[t] - drag
                val *= 1 + out[t]
                peak = max(peak, val)
                if kind == "BA2" and val <= peak * 0.90:
                    hold, stopped = False, True
            if bear[t] and not bear[t - 1]:
                stopped = False
            want = bear[t] and not stopped
            if want and not hold:
                hold, val, peak = True, 1.0, 1.0
            elif not want and hold:
                hold = False
        return out
    rs, sma5 = rsi2(close), close.rolling(5).mean().values
    c = close.values
    hold, entry = False, 0.0
    for t in range(1, n):
        if hold:
            out[t] = r[t]
            if (c[t] > sma5[t]) or (not bear[t]) or (kind == "BA4" and c[t] <= entry * 0.92):
                hold = False
        elif bear[t] and rs[t] < 10:
            hold, entry = True, c[t]           # 今天收盘确认 → 明天起计收益（近似次日收盘买）
    return out


def stats(x: np.ndarray, idx: pd.DatetimeIndex, m: np.ndarray) -> dict:
    x = x[m]
    d = idx[m]
    yrs = (d[-1] - d[0]).days / 365.25
    eq = np.cumprod(1 + x)
    cagr = eq[-1] ** (1 / yrs) - 1
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    active = x != 0
    return {"cagr": round(cagr * 100, 2), "dd": round(dd * 100, 2), "calmar": round(cagr / abs(dd), 3) if dd < 0 else None,
            "total": round((eq[-1] - 1) * 100, 1), "active_days": int(active.sum())}


def main() -> int:
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    rows = []
    for m in ("US", "JP"):
        d = load(*SYM[m])
        st = det.states(d["Close"], (cfg.get("hmm") or {}).get(m))
        bear = st == -1
        for kind in ("BA0", "BA1", "BA2", "BA3", "BA4"):
            x = sleeve_returns(d["Close"], bear, kind, m)
            for per, (a, b) in (("train", TRAIN[m]), ("test", TEST)):
                msk = (d.index >= a) & ((d.index <= b) if b else True)
                rows.append({"market": m, "sleeve": kind, "period": per, **stats(x, d.index, msk)})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    tr = df[df["period"] == "train"].pivot(index="sleeve", columns="market", values=["cagr", "calmar"])
    ok = [s for s in ("BA1", "BA2", "BA3", "BA4") if (tr.loc[s, ("cagr", "US")] > 0) and (tr.loc[s, ("cagr", "JP")] > 0)]
    best = max(ok, key=lambda s: (tr.loc[s, ("calmar", "US")] or 0) + (tr.loc[s, ("calmar", "JP")] or 0)) if ok else "BA0"
    print("\n训练期两个指数都为正收益的：", ok, "→ 选定", best)
    df.to_csv(paths.out_dir() / "bear_sleeve_study.csv", index=False, encoding="utf-8-sig")
    cfg["bear_sleeve_index_study"] = {"selected": best, "eligible": ok}
    (paths.home() / "bullbear.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
