"""shadow.py — 影子账户（「判断型」选股：规则以外、按当天的日报 / 宏观 / 威胁指数 / 消息做的判断；只前向记录，不影响模拟盘与交易）。
规则、流程与评估标准见 scripts/shadow_account.py 开头（2026-09-26 事先登记：先提交后记录）。

账户口径与模拟盘相同：¥1,000,000、2026-09-28 开始、2026-12-24 收盘结束；立花 個別コース手续费、个股滑点 0.10%、ETF 按登记的滑点；
信号当天（09:00 JST 之前）决定、当天 09:00 开盘价成交（第二天早上按真实开盘价撮合）；分红税后（× 79.685%）入账、拆股调整股数
（与模拟盘 qbreak/unified.apply_corp_action 同一口径）。只做多、不加杠杆；日経225 成分股最多 4 只、单只买入 ≤ 权益 35%；ETF 只有 1655.T / 1329.T。
文件：状态 <数据目录>/state/shadow_state.json；只追加的记录 out/shadow_decisions.jsonl（每天的判断）、out/shadow_trades.csv（成交）、
out/shadow_equity.csv（每个交易日收盘：影子 vs 规则账户）；当天摘要 out/shadow_today.json（日报用）。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import paths

START, END = "2026-09-28", "2026-12-24"
CAPITAL = 1_000_000.0
ETFS = ("1655.T", "1329.T")
MAX_STOCKS, MAX_STOCK_W, STOCK_LOT = 4, 0.35, 100
DECIDE_BY = dt.time(9, 0)
BROKER = "tachibana"
STATE_FILE, DECISIONS, TRADES, EQUITY, TODAY = ("shadow_state.json", "shadow_decisions.jsonl", "shadow_trades.csv",
                                                "shadow_equity.csv", "shadow_today.json")
EQUITY_COLS = ["date", "shadow_equity", "rule_equity", "shadow_ret_pct", "rule_ret_pct", "diff_pp"]
TRADE_COLS = ["date", "ticker", "side", "shares", "px", "fee", "pnl", "reason", "for_date"]


# ────────────────────────── 成本（与模拟盘同一张费用表）──────────────────────────
def lot_of(t: str) -> int:
    from .fees import etf_cost
    return int(etf_cost(BROKER, t, "JP").get("lot", 1)) if t in ETFS else STOCK_LOT


def slip_of(t: str) -> float:
    from .fees import etf_cost, market_fees
    return float(etf_cost(BROKER, t, "JP")["slip_pct"] if t in ETFS else market_fees(BROKER, "JP")["slippage_pct"]) / 100


def fee_of(t: str, side: str):
    from .fees import etf_cost, market_fees, side_fee
    if t in ETFS:
        return side_fee(etf_cost(BROKER, t, "JP"), side)
    tiers = market_fees(BROKER, "JP").get("commission_tiers") or ()
    return side_fee({"buy_fee_tiers": tiers, "sell_fee_tiers": tiers}, side)


# ────────────────────────── 状态 ──────────────────────────
@dataclass
class SState:
    cash: float = CAPITAL
    pos: dict = field(default_factory=dict)          # 票 → {"shares", "cost"（每股，含买入手续费）, "entry_date", "last_close"}
    pending: list = field(default_factory=list)      # 待成交：{"for_date", "ticker", "side", "shares", "reason", "decided_at"}
    last_date: str | None = None
    history: list = field(default_factory=list)      # [日期, 权益, 现金]
    corp_done: list = field(default_factory=list)
    corp_log: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SState":
        return cls(**{k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__})


def load_state(fp: Path | None = None) -> SState:
    fp = Path(fp or paths.state_dir() / STATE_FILE)
    return SState.from_dict(json.loads(fp.read_text(encoding="utf-8"))) if fp.exists() else SState()


def save_state(st: SState, fp: Path | None = None) -> None:
    from .utils import atomic_write_text
    atomic_write_text(Path(fp or paths.state_dir() / STATE_FILE), json.dumps(st.to_dict(), ensure_ascii=False, indent=1, default=float))


def equity(st: SState) -> float:
    return float(st.cash + sum(p["shares"] * p["last_close"] for p in st.pos.values()))


def n_stocks(pos: dict) -> int:
    return sum(1 for t, p in pos.items() if t not in ETFS and p["shares"] > 0)


# ────────────────────────── 判断的检查（09:00 JST 之前、规则内）──────────────────────────
def decided_dates(fp: Path | None = None) -> set[str]:
    fp = Path(fp or paths.out_dir() / DECISIONS)
    if not fp.exists():
        return set()
    return {json.loads(ln)["for_date"] for ln in fp.read_text(encoding="utf-8").splitlines() if ln.strip()}


def validate(dec: dict, st: SState, now: dt.datetime, universe: set[str], ref_px: dict[str, float],
             already: set[str]) -> tuple[dict | None, list[str]]:
    """→（规范化后的判断, 错误）。有任何错误 → 整份判断不记录（09:00 之前可以改好再交）。"""
    from .calendar_jp import is_trading_day
    err: list[str] = []
    fd = str(dec.get("for_date") or "")
    if fd != now.date().isoformat():
        err.append(f"for_date {fd or '—'} 不是今天 {now.date()}（只能决定今天 09:00 开盘的单）")
    elif not is_trading_day(now.date()):
        err.append(f"{fd} 不是交易日")
    elif not (START <= fd <= END):
        err.append(f"{fd} 不在记录期间 {START}〜{END}")
    if now.time() >= DECIDE_BY:
        err.append(f"已过 {DECIDE_BY:%H:%M} JST（{now:%H:%M}）：今天的寄付来不及，不记录")
    if fd in already:
        err.append(f"{fd} 已经有判断记录（只追加，不改）")
    view = str(dec.get("view") or "").strip()
    if not view:
        err.append("缺一句话判断（view）")
    orders, seen = [], set()
    eq = equity(st)
    buy_cost, sell_cash = 0.0, 0.0
    new_stocks = 0
    for o in dec.get("orders") or []:
        t, side, reason = str(o.get("ticker") or ""), str(o.get("side") or "").upper(), str(o.get("reason") or "").strip()
        try:
            q = int(o.get("shares"))
        except (TypeError, ValueError):
            q = 0
        if t in seen:
            err.append(f"{t} 出现两次")
        seen.add(t)
        if t not in universe and t not in ETFS:
            err.append(f"{t} 不在可选范围（日経225 成分股 + {' / '.join(ETFS)}）")
            continue
        if side not in ("BUY", "SELL"):
            err.append(f"{t} 的方向 {side or '—'} 不是 BUY / SELL")
            continue
        if not reason:
            err.append(f"{t} 缺理由")
        if q <= 0:
            err.append(f"{t} 股数 {o.get('shares')} 不对")
            continue
        px = ref_px.get(t)
        if not px or not np.isfinite(px):
            err.append(f"{t} 取不到参考价（最近收盘）")
            continue
        held = int((st.pos.get(t) or {}).get("shares") or 0)
        if side == "SELL":
            if q > held:
                err.append(f"{t} 卖 {q} 股 > 持有 {held} 股")
            sell_cash += q * px * (1 - slip_of(t)) - fee_of(t, "SELL")(q * px)
        else:
            if q % lot_of(t):
                err.append(f"{t} 买 {q} 股不是 {lot_of(t)} 的倍数")
            if t not in ETFS:
                if held == 0:
                    new_stocks += 1
                if (q + held) * px > MAX_STOCK_W * eq:
                    err.append(f"{t} 买后市值 ¥{(q + held) * px:,.0f} > 权益 ¥{eq:,.0f} × {MAX_STOCK_W:.0%}")
            buy_cost += q * px * (1 + slip_of(t)) + fee_of(t, "BUY")(q * px)
        orders.append({"ticker": t, "side": side, "shares": q, "reason": reason, "ref_px": round(float(px), 2)})
    full_sell = {o["ticker"] for o in orders if o["side"] == "SELL" and o["shares"] >= int((st.pos.get(o["ticker"]) or {}).get("shares") or 0)}
    after = n_stocks({t: p for t, p in st.pos.items() if t not in full_sell}) + new_stocks
    if after > MAX_STOCKS:
        err.append(f"个股会变成 {after} 只 > {MAX_STOCKS} 只")
    if buy_cost > st.cash + sell_cash + 1e-6:
        err.append(f"买入约 ¥{buy_cost:,.0f} > 现金 ¥{st.cash:,.0f} + 卖出约 ¥{sell_cash:,.0f}（不加杠杆）")
    if err:
        return None, err
    return {"for_date": fd, "decided_at": now.isoformat(timespec="seconds"), "view": view, "orders": orders,
            "inputs": str(dec.get("inputs") or ""), "equity_before": round(eq), "cash_before": round(st.cash),
            "positions_before": {t: p["shares"] for t, p in st.pos.items()}}, []


def record_decision(st: SState, rec: dict, fp: Path | None = None) -> None:
    """只追加：判断写进 shadow_decisions.jsonl，单子进待成交。"""
    fp = Path(fp or paths.out_dir() / DECISIONS)
    fp.parent.mkdir(parents=True, exist_ok=True)
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    for o in rec["orders"]:
        st.pending.append({"for_date": rec["for_date"], "ticker": o["ticker"], "side": o["side"], "shares": o["shares"],
                           "reason": o["reason"], "decided_at": rec["decided_at"]})


# ────────────────────────── 每天推进（成交、公司行为、收盘估值）──────────────────────────
def apply_corp(st: SState, t: str, date: str, dividend: float = 0.0, split: float = 0.0) -> str | None:
    from .corpactions import DIV_NET
    key = f"{t}|{date}"
    p = st.pos.get(t)
    if key in st.corp_done or not p:
        return None
    notes = []
    k = float(split or 0)
    if k > 0 and abs(k - 1) > 1e-9:
        old = p["shares"]
        p["shares"] = int(old * k + 1e-6)
        p["cost"], p["last_close"] = p["cost"] / k, p["last_close"] / k
        notes.append(f"株式分割 1:{k:g}（{old}→{p['shares']} 株）")
    dv = float(dividend or 0)
    if dv > 0:
        net = dv * p["shares"] * DIV_NET["JP"]
        st.cash += net
        notes.append(f"配当落ち {dv:g} × {p['shares']:,} → 税后 ¥{net:,.2f}")
    if not notes:
        return None
    st.corp_done.append(key)
    st.corp_log.append({"date": date, "ticker": t, "note": "；".join(notes)})
    return "；".join(notes)


def process_day(st: SState, d: str, bars: dict[str, dict], corp=None) -> list[dict]:
    """推进一个交易日 d：(上次, d] 的公司行为 → d 开盘成交待成交单（先卖后买）→ d 收盘估值。bars：票 → {"open", "close"}。"""
    trades = []
    if corp is not None and st.last_date:
        for t in sorted(st.pos):
            for a in corp(t, st.last_date, d) or []:
                apply_corp(st, t, a["date"], a.get("dividend") or 0.0, a.get("split") or 0.0)
    due = [o for o in st.pending if o["for_date"] <= d]
    st.pending = [o for o in st.pending if o["for_date"] > d]

    def done(o, side, q, px, fee, pnl, why):
        trades.append({"date": d, "ticker": o["ticker"], "side": side, "shares": q, "px": round(px, 2), "fee": round(fee),
                       "pnl": None if pnl is None else round(pnl), "reason": why, "for_date": o["for_date"]})

    for o in [x for x in due if x["side"] == "SELL"] + [x for x in due if x["side"] == "BUY"]:
        t, b = o["ticker"], bars.get(o["ticker"]) or {}
        op = b.get("open")
        if o["for_date"] < d:
            done(o, "CANCEL", 0, 0.0, 0.0, None, f"{o['for_date']} 没有成交（没有那一天的 K 线）→ 取消")
            continue
        if not op or not np.isfinite(op):
            done(o, "CANCEL", 0, 0.0, 0.0, None, "没有开盘价（停牌 / 行情缺）→ 取消")
            continue
        if o["side"] == "SELL":
            p = st.pos.get(t)
            q = min(int(o["shares"]), int(p["shares"]) if p else 0)
            if q <= 0:
                done(o, "CANCEL", 0, 0.0, 0.0, None, "没有持仓 → 取消")
                continue
            px = op * (1 - slip_of(t))
            fee = fee_of(t, "SELL")(q * px)
            st.cash += q * px - fee
            pnl = (px - p["cost"]) * q - fee
            p["shares"] -= q
            if p["shares"] <= 0:
                del st.pos[t]
            done(o, "SELL", q, px, fee, pnl, o["reason"])
        else:
            px = op * (1 + slip_of(t))
            fee_f, lot, q = fee_of(t, "BUY"), lot_of(t), int(o["shares"])
            if t not in ETFS and t not in st.pos and n_stocks(st.pos) >= MAX_STOCKS:
                done(o, "CANCEL", 0, 0.0, 0.0, None, f"个股已有 {MAX_STOCKS} 只 → 取消")
                continue
            while q > 0 and q * px + fee_f(q * px) > st.cash + 1e-6:
                q -= lot
            if q <= 0:
                done(o, "CANCEL", 0, 0.0, 0.0, None, "现金不够 → 取消")
                continue
            fee = fee_f(q * px)
            st.cash -= q * px + fee
            p = st.pos.get(t)
            if p:
                tot = p["shares"] + q
                p["cost"] = (p["cost"] * p["shares"] + px * q + fee) / tot
                p["shares"] = tot
            else:
                st.pos[t] = {"shares": q, "cost": (px * q + fee) / q, "entry_date": d, "last_close": op}
            done(o, "BUY", q, px, fee, None, o["reason"] + ("" if q == int(o["shares"]) else f"（现金不够，只买 {q} 股）"))
    for t, p in st.pos.items():
        c = (bars.get(t) or {}).get("close")
        if c and np.isfinite(c):
            p["last_close"] = float(c)
    st.history.append([d, round(equity(st), 2), round(st.cash, 2)])
    st.last_date = d
    return trades


def append_rows(fp: Path, cols: list[str], rows: list[dict], key: str | None = None) -> int:
    """只追加（key 给了：已有同一个 key 的行不再写）。返回写了几行。"""
    fp = Path(fp)
    have = set()
    if key and fp.exists():
        with fp.open(encoding="utf-8", newline="") as f:
            have = {r[key] for r in csv.DictReader(f)}
    new = [r for r in rows if not key or str(r[key]) not in have]
    if not new:
        return 0
    first = not fp.exists() or fp.stat().st_size == 0
    fp.parent.mkdir(parents=True, exist_ok=True)
    with fp.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if first:
            w.writeheader()
        for r in new:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return len(new)


def rule_equity() -> dict[str, float]:
    """规则账户（云端模拟盘）每个交易日的权益：var/state/unified_state.json 的 history。"""
    from .utils import read_json
    st = read_json(paths.state_dir() / "unified_state.json", {}) or {}
    return {str(h[0]): float(h[1]) for h in st.get("history") or [] if len(h) > 1 and h[1] is not None}


def equity_rows(st: SState, rule: dict[str, float], since: str | None = None) -> list[dict]:
    out = []
    for d, eq, _ in st.history:
        if since and d <= since:
            continue
        r = rule.get(d)
        sr, rr = (eq / CAPITAL - 1) * 100, (None if r is None else (r / CAPITAL - 1) * 100)
        out.append({"date": d, "shadow_equity": round(eq), "rule_equity": None if r is None else round(r),
                    "shadow_ret_pct": round(sr, 3), "rule_ret_pct": None if rr is None else round(rr, 3),
                    "diff_pp": None if rr is None else round(sr - rr, 3)})
    return out


def today_summary(st: SState, rule: dict[str, float], last_decision: dict | None, note: str = "") -> dict:
    eq = equity(st)
    r = rule.get(st.last_date or "")
    return {"as_of": st.last_date, "equity_jpy": round(eq), "cash_jpy": round(st.cash), "ret_pct": round((eq / CAPITAL - 1) * 100, 2),
            "rule_equity_jpy": None if r is None else round(r),
            "diff_pp": None if r is None else round((eq - r) / CAPITAL * 100, 2),
            "positions": {t: {"shares": p["shares"], "cost": round(p["cost"], 2), "close": round(p["last_close"], 2),
                              "value": round(p["shares"] * p["last_close"]), "pnl_pct": round((p["last_close"] / p["cost"] - 1) * 100, 2)}
                          for t, p in st.pos.items()},
            "pending": st.pending, "last_decision": last_decision, "note": note, "period": [START, END]}


def last_decision(fp: Path | None = None) -> dict | None:
    fp = Path(fp or paths.out_dir() / DECISIONS)
    if not fp.exists():
        return None
    lines = [ln for ln in fp.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


# ────────────────────────── 评估（事先写定，见 scripts/shadow_account.py 第四节）──────────────────────────
def block_boot_ci(x: np.ndarray, block: int = 5, n: int = 5000, seed: int = 20261224) -> tuple[float | None, float | None]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 2 * block:
        return None, None
    rng = np.random.default_rng(seed)
    k = int(np.ceil(len(x) / block))
    starts = np.arange(len(x) - block + 1)
    means = np.empty(n)
    for i in range(n):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.choice(starts, k)])[:len(x)]
        means[i] = x[idx].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def max_dd(eq: np.ndarray) -> float:
    eq = np.asarray(eq, float)
    return float((eq / np.maximum.accumulate(eq) - 1).min() * 100) if len(eq) else 0.0


def evaluate(rows: list[dict], decided: set[str], trading_days: list[str]) -> dict:
    """rows：shadow_equity.csv 的行（期间内）；decided：有判断记录的交易日；trading_days：期间内的交易日。"""
    rows = [r for r in rows if r.get("rule_equity") not in (None, "") and START <= r["date"] <= END]
    if len(rows) < 2:
        return {"verdict": "数据不够（两个账户同时有值的交易日 < 2 天）", "n": len(rows)}
    s = np.array([CAPITAL] + [float(r["shadow_equity"]) for r in rows])
    b = np.array([CAPITAL] + [float(r["rule_equity"]) for r in rows])
    rs, rb = s[1:] / s[:-1] - 1, b[1:] / b[:-1] - 1
    e = (rs - rb) * 1e4                                                     # 基点 / 天
    lo, hi = block_boot_ci(e)
    tot_s, tot_b = (s[-1] / CAPITAL - 1) * 100, (b[-1] / CAPITAL - 1) * 100
    dd_s, dd_b = max_dd(s), max_dd(b)
    cov = len(set(trading_days) & decided) / max(1, len(trading_days)) * 100
    crit = {"累计收益差 > 0": tot_s - tot_b > 0, "日超额收益 95% 下限 > 0": lo is not None and lo > 0,
            "最大回撤不比规则账户深 2 pp 以上": dd_s >= dd_b - 2.0, "判断覆盖率 ≥ 90%": cov >= 90.0}
    if all(crit.values()):
        verdict = "判断型更好（只是记录：模拟盘与交易都不改；提议再记 3 个月，并把反复出现的判断理由写成可回测的规则另行登记研究）"
    elif hi is not None and hi < 0:
        verdict = "判断型更差"
    else:
        verdict = "分不出来（3 个月太短）"
    return {"n": len(rows), "shadow_ret_pct": round(tot_s, 2), "rule_ret_pct": round(tot_b, 2), "diff_pp": round(tot_s - tot_b, 2),
            "shadow_dd_pct": round(dd_s, 2), "rule_dd_pct": round(dd_b, 2), "excess_bp_day": round(float(e.mean()), 2),
            "ci95_bp_day": [None if lo is None else round(lo, 2), None if hi is None else round(hi, 2)], "coverage_pct": round(cov, 1),
            "criteria": crit, "verdict": verdict}
