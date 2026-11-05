"""macro_now.py — 仪表盘的「市场健康度」与「消费 / 零售等新数据」（只作展示，不参与交易）。

健康度：每一项用策略宏观层自己的阈值上色（qbreak/macro.py 的 TH，也就是日报「宏观触发」那一套）——
  没到「偏高」线 = 正常，≥「偏高」= 注意，≥「压力 / 恐慌」= 警戒；日経 离 250 日线用牛熊分界的 ±3% 带；
  威胁指数 ≥ 80 分 = 警戒（日报历史检验用的线）、60〜80 = 注意；美股宽度 < 25% = 注意（宏观层同一条线）。
  综合分 = （正常 1 分、注意 0.5 分、警戒 0 分）的平均 × 100。
新数据：FRED 的美国零售销售、密歇根消费者信心、初次申请失业金、失业率、非农就业、CPI，日本消费者态度指数（OECD 口径）；
  每项给最新值、上一期、变化、数据期、「改善 / 恶化」（按常识：零售 / 信心 / 就业走强 = 景气好；失业 / 通胀走高 = 压力）、
  会影响哪些行业（文字说明，不是模型），以及第一次看到这期数据的时间（NEW_HOURS 小时内标「新」）。
collect() 取数（网络，有缓存）；build() / health() / releases() 只做计算（测试用合成数据）。
"""
from __future__ import annotations

import datetime as dt
import logging
import math

import numpy as np
import pandas as pd

from . import paths
from .calendar_jp import now_jst
from .macro import TH
from .utils import read_json, write_json

log = logging.getLogger(__name__)

SPARK_N = 120                                   # 健康度迷你折线：最近约半年的交易日
REL_N = 24                                      # 新数据迷你折线：最近 24 期
NEW_HOURS = 24
THREAT_WARN, THREAT_BAD = 60.0, 80.0

# 健康度：键 → (标签, 单位, 注意线, 警戒线, 越高越危险, 说明)
TILES = {
    "n225_ma": ("日経 离 250 日线", "%", None, None, None, "牛熊分界 = 250 日线 ±3%：> +3% 正常、±3% 以内注意、< −3% 警戒"),
    "vix": ("VIX 恐慌指数", "pt", TH["vix_high"], TH["vix_panic"], True, f"≥ {TH['vix_high']:g} 注意、≥ {TH['vix_panic']:g} 警戒"),
    "us10y": ("美国 10 年期利率", "%", TH["us10y_high"], TH["us10y_stress"], True,
              f"≥ {TH['us10y_high']:g}% 注意（高估值成长 ×0.5）、≥ {TH['us10y_stress']:g}% 警戒"),
    "jgb10y": ("日本 10 年期利率", "%", TH["jgb10y_high"], TH["jgb10y_stress"], True,
               f"≥ {TH['jgb10y_high']:g}% 注意、≥ {TH['jgb10y_stress']:g}% 警戒"),
    "usdjpy": ("美元日元", "円/USD", TH["usdjpy_watch"], None, True, f"≥ {TH['usdjpy_watch']:g} = 介入警戒区（出口股 ×0.75）"),
    "brent": ("布伦特原油", "USD/桶", TH["oil_high"], TH["oil_extreme"], True,
              f"≥ {TH['oil_high']:g} 注意、≥ {TH['oil_extreme']:g} 警戒；20 日涨 ≥ {TH['oil_shock20_pct']:g}% 也算注意"),
    "hy": ("美国高收益债利差", "bp", TH["hy_oas_wide"], TH["hy_oas_stress"], True,
           f"≥ {TH['hy_oas_wide']:g} 注意、≥ {TH['hy_oas_stress']:g} 警戒（信用紧张）"),
    "breadth": ("美股宽度（站上 50 日线）", "%", TH["breadth_weak"], None, False, f"< {TH['breadth_weak']:g}% 注意（少数大票撑指数）"),
    "threat_us": ("威胁指数 美股", "分", THREAT_WARN, THREAT_BAD, True, "≥ 60 注意、≥ 80 警戒（只说明风险高低，不预测哪天）"),
    "threat_jp": ("威胁指数 日経", "分", THREAT_WARN, THREAT_BAD, True, "≥ 60 注意、≥ 80 警戒"),
}

# 新数据：(键, FRED 代码, 标签, 单位, 变换, 好的方向, 上升时的影响, 下降时的影响)
RELEASES = [
    ("us_retail", "RSAFS", "美国零售销售", "% 环比", "mom", 1,
     "美国消费偏强 → 零售 / 可选消费顺风；利率不易下降", "美国消费偏弱 → 零售 / 可选消费逆风；利率预期下降"),
    ("us_sent", "UMCSENT", "美国消费者信心（密歇根）", "pt", "level", 1,
     "消费意愿回升 → 零售 / 可选消费顺风", "消费意愿下降 → 零售 / 可选消费逆风"),
    ("jp_conf", "CSCICP02JPM460S", "日本消费者态度指数", "pt", "level", 1,
     "日本消费意愿回升 → 零售 / 食品 / 内需顺风", "日本消费意愿下降 → 零售 / 内需逆风"),
    ("us_claims", "ICSA", "美国初次申请失业金（每周）", "万人", "k10", -1,
     "裁员增加 → 景气放缓信号；利率预期下降，防御业种相对占优", "裁员减少 → 就业稳健"),
    ("us_unrate", "UNRATE", "美国失业率", "%", "level", -1,
     "失业率上升 → 景气放缓风险（威胁指数的失业率项也会升）", "失业率下降 → 就业稳健"),
    ("us_payroll", "PAYEMS", "美国非农就业（月增）", "万人", "diff10", 1,
     "就业强 → 利率上行、美元偏强（日元偏弱 → 出口股顺风）", "就业弱 → 利率预期下降、日元偏强（出口股逆风）"),
    ("us_cpi", "CPIAUCSL", "美国 CPI（同比）", "%", "yoy", -1,
     "通胀升温 → 利率上行压力、高估值成长逆风", "通胀降温 → 利率压力减轻、成长股顺风"),
]
REL_BY_KEY = {r[0]: r for r in RELEASES}


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def status(v: float | None, warn: float | None, bad: float | None, higher_is_worse: bool = True) -> str:
    """正常 good / 注意 warn / 警戒 bad / 无数据 none。"""
    if v is None:
        return "none"
    if higher_is_worse:
        if bad is not None and v >= bad:
            return "bad"
        return "warn" if warn is not None and v >= warn else "good"
    if bad is not None and v <= bad:
        return "bad"
    return "warn" if warn is not None and v < warn else "good"


def _tail(s: pd.Series | None, n: int) -> list:
    if s is None or not len(s):
        return []
    return [None if not np.isfinite(v) else round(float(v), 4) for v in s.dropna().iloc[-n:].to_numpy(float)]


def _tile(key: str, s: pd.Series | None, value: float | None = None, asof: str | None = None, extra: str = "") -> dict:
    lab, unit, warn, bad, hiw, note = TILES[key]
    v = _f(value) if value is not None else (_f(s.dropna().iloc[-1]) if s is not None and len(s.dropna()) else None)
    if key == "n225_ma":
        st = "none" if v is None else ("good" if v > 3 else ("bad" if v < -3 else "warn"))
    else:
        st = status(v, warn, bad, bool(hiw))
    if asof is None and s is not None and len(s.dropna()):
        asof = str(s.dropna().index[-1].date())
    return {"key": key, "label": lab, "unit": unit, "value": None if v is None else round(v, 2), "status": st,
            "note": note + extra, "ref": warn, "spark": _tail(s, SPARK_N), "asof": asof}


def health(frame: pd.DataFrame | None = None, n225: pd.Series | None = None, jgb: pd.Series | None = None,
           hy_bp: pd.Series | None = None, overlay: dict | None = None, threat: dict | None = None) -> dict:
    """frame = qbreak.macro.features_frame（brent / brent_chg20_pct / us10y / vix / usdjpy，与宏观层同一口径）。"""
    fr = frame if frame is not None else pd.DataFrame()
    col = lambda k: fr[k].dropna() if k in fr.columns else None                                   # noqa: E731
    tiles = []
    if n225 is not None and len(n225.dropna()) > 250:
        c = n225.dropna()
        tiles.append(_tile("n225_ma", (c / c.rolling(250).mean() - 1) * 100))
    else:
        tiles.append(_tile("n225_ma", None))
    tiles.append(_tile("vix", col("vix")))
    tiles.append(_tile("us10y", col("us10y")))
    tiles.append(_tile("jgb10y", jgb.dropna() if jgb is not None else None))
    tiles.append(_tile("usdjpy", col("usdjpy")))
    b = _tile("brent", col("brent"))
    ch = col("brent_chg20_pct")
    c20 = _f(ch.iloc[-1]) if ch is not None and len(ch) else None
    if c20 is not None:
        b["note"] += f"；近 20 日 {c20:+.1f}%"
        if c20 >= TH["oil_shock20_pct"] and b["status"] == "good":
            b["status"] = "warn"
    tiles.append(b)
    ov = overlay or {}
    tiles.append(_tile("hy", hy_bp.dropna() if hy_bp is not None else None,
                       value=ov.get("hy_oas_bp") if hy_bp is None else None, asof=ov.get("as_of") if hy_bp is None else None))
    tiles.append(_tile("breadth", None, value=ov.get("breadth_pct"), asof=ov.get("as_of"),
                       extra="（来自市场风险报告，没有历史曲线）" if ov.get("breadth_pct") is not None else ""))
    for m in ("US", "JP"):
        s = (threat or {}).get(m)
        tiles.append(_tile(f"threat_{m.lower()}", s.dropna() if s is not None else None))
    pts = {"good": 1.0, "warn": 0.5, "bad": 0.0}
    have = [t for t in tiles if t["status"] in pts]
    score = round(sum(pts[t["status"]] for t in have) / len(have) * 100) if have else None
    cnt = {k: sum(t["status"] == k for t in tiles) for k in ("good", "warn", "bad", "none")}
    return {"tiles": tiles, "score": score, "counts": cnt}


def _pts(v: pd.Series, warn, bad, higher_is_worse: bool = True) -> pd.Series:
    """逐日的状态分：正常 1、注意 0.5、警戒 0、缺值 NaN（与 status() 同一套规则）。"""
    v = v.astype(float)
    out = pd.Series(1.0, index=v.index)
    if higher_is_worse:
        if warn is not None:
            out[v >= warn] = 0.5
        if bad is not None:
            out[v >= bad] = 0.0
    else:
        if warn is not None:
            out[v < warn] = 0.5
        if bad is not None:
            out[v <= bad] = 0.0
    out[v.isna()] = np.nan
    return out


def health_series(frame: pd.DataFrame | None = None, n225: pd.Series | None = None, jgb: pd.Series | None = None,
                  hy_bp: pd.Series | None = None, threat: dict | None = None) -> pd.DataFrame:
    """逐日的健康度（研究用，与 health() 同一套阈值；美股宽度没有历史 → 不含）：各项状态分 + score（有数据的项平均 × 100）。
    各序列按日期并起来、向前填（每一天只用到那天为止已知的值）。"""
    cols: dict[str, pd.Series] = {}
    if n225 is not None and len(n225.dropna()) > 250:
        c = n225.dropna().astype(float)
        d = (c / c.rolling(250).mean() - 1) * 100
        cols["n225_ma"] = pd.Series(np.where(d > 3, 1.0, np.where(d < -3, 0.0, 0.5)), index=d.index).where(d.notna())
    fr = frame if frame is not None else pd.DataFrame()
    for k in ("vix", "us10y", "usdjpy"):
        if k in fr.columns:
            _, _, warn, bad, hiw, _ = TILES[k]
            cols[k] = _pts(fr[k].dropna(), warn, bad, bool(hiw))
    if "brent" in fr.columns:
        b = _pts(fr["brent"].dropna(), TILES["brent"][2], TILES["brent"][3])
        if "brent_chg20_pct" in fr.columns:
            shock = fr["brent_chg20_pct"].reindex(b.index) >= TH["oil_shock20_pct"]
            b = b.where(~(shock & (b == 1.0)), 0.5)
        cols["brent"] = b
    if jgb is not None:
        cols["jgb10y"] = _pts(jgb.dropna(), TILES["jgb10y"][2], TILES["jgb10y"][3])
    if hy_bp is not None:
        cols["hy"] = _pts(hy_bp.dropna(), TILES["hy"][2], TILES["hy"][3])
    for m in ("US", "JP"):
        s = (threat or {}).get(m)
        if s is not None:
            cols[f"threat_{m.lower()}"] = _pts(s.dropna(), THREAT_WARN, THREAT_BAD)
    if not cols:
        return pd.DataFrame(columns=["score"])
    df = pd.concat(cols, axis=1).sort_index().ffill()
    df["score"] = df.mean(axis=1, skipna=True) * 100
    return df


def transform(s: pd.Series, how: str) -> pd.Series:
    s = s.dropna().astype(float)
    if how == "mom":
        return s.pct_change() * 100
    if how == "yoy":
        return (s / s.shift(12) - 1) * 100
    if how == "k10":
        return s / 10000                                                     # 人 → 万人
    if how == "diff10":
        return s.diff() / 10                                                 # 千人 → 万人
    return s


def _period(ts: pd.Timestamp, how: str, weekly: bool) -> str:
    return str(ts.date()) if weekly else ts.strftime("%Y-%m")


def releases(raw: dict[str, pd.Series], seen: dict | None = None, now: dt.datetime | None = None) -> tuple[list[dict], dict]:
    """raw = {键: FRED 原始系列}。返回（各项的最新一期，更新后的「第一次看到」表）。seen = {键: {"obs": 数据期, "seen": ISO 时间}}。"""
    now = now or now_jst()
    seen = dict(seen or {})
    out = []
    for key, fid, lab, unit, how, good_dir, up_txt, dn_txt in RELEASES:
        s = raw.get(key)
        if s is None or len(s.dropna()) < 3:
            out.append({"key": key, "label": lab, "unit": unit, "value": None, "error": "没取到"})
            continue
        x = transform(s, how).dropna()
        if len(x) < 2:
            out.append({"key": key, "label": lab, "unit": unit, "value": None, "error": "期数不够"})
            continue
        weekly = how == "k10"
        last, prev = float(x.iloc[-1]), float(x.iloc[-2])
        chg = last - prev
        tol = 1e-9 + 0.02 * (float(x.iloc[-REL_N:].std()) if len(x) > 3 else 0.0)
        good = 0 if abs(chg) <= tol else (1 if chg * good_dir > 0 else -1)
        obs = _period(x.index[-1], how, weekly)
        rec = seen.get(key)
        if rec is None:                                                      # 第一次运行：只记下现在的数据期，不算「新」
            rec = seen[key] = {"obs": obs, "seen": None}
        elif rec.get("obs") != obs:
            rec = seen[key] = {"obs": obs, "seen": now.isoformat(timespec="minutes")}
        try:
            age_h = (now - dt.datetime.fromisoformat(rec["seen"])).total_seconds() / 3600
        except (KeyError, ValueError, TypeError):
            age_h = None
        avg12 = float(x.iloc[-13:-1].mean()) if len(x) >= 13 else None
        out.append({"key": key, "label": lab, "unit": unit, "value": round(last, 2), "prev": round(prev, 2), "chg": round(chg, 2),
                    "obs": obs, "good": good, "avg12": None if avg12 is None else round(avg12, 2),
                    "impact": up_txt if chg > 0 else (dn_txt if chg < 0 else "持平"),
                    "spark": _tail(x, REL_N), "seen": rec.get("seen"), "new": age_h is not None and 0 <= age_h < NEW_HOURS})
    return out, seen


def upcoming(events: list[dict], today: dt.date, days: int = 21) -> list[dict]:
    """接下来 days 天的已知大事件（var/macro_events.json）。"""
    out = []
    for e in events or []:
        try:
            d = dt.date.fromisoformat(str(e.get("date"))[:10])
        except ValueError:
            continue
        if today <= d <= today + dt.timedelta(days=days):
            out.append({"date": str(d), "kind": e.get("kind"), "home": e.get("home"), "name": e.get("name") or ""})
    return sorted(out, key=lambda z: z["date"])


def collect(max_age_h: float = 12.0, overlay: dict | None = None, with_health: bool = True) -> dict:
    """取数 + 计算（网络；每一块单独 try，取不到的写 error）。max_age_h = FRED 缓存小时数（Mac 的实时监控用 1）。"""
    from . import factors as F
    now = now_jst()
    out: dict = {"generated": now.strftime("%Y-%m-%d %H:%M JST")}
    if with_health:
        try:
            from . import threat as T
            from .config import DataConfig
            from .macro import features_frame, load_macro_series
            frame = features_frame(load_macro_series(DataConfig(provider="yfinance", years=2, allow_synthetic=False).validate()))
            ti = T.load_inputs()
            thr = {}
            try:
                built = T.build(ti)
                thr = {m: built[m][0] for m in built}
            except Exception as e:                                          # noqa: BLE001
                log.warning("威胁指数序列失败（仪表盘）：%s", e)
            try:
                hy = F.fred("BAMLH0A0HYM2") * 100
            except Exception:                                               # noqa: BLE001
                hy = None
            out["health"] = health(frame, ti["n225"], ti["jgb"], hy, overlay, thr)
        except Exception as e:                                              # noqa: BLE001
            log.warning("市场健康度失败（只影响仪表盘）：%s", e)
            out["health"] = {"error": f"{type(e).__name__}: {e}"}
    raw = {}
    for key, fid, *_ in RELEASES:
        try:
            raw[key] = F.fred(fid, max_age_h)
        except Exception as e:                                              # noqa: BLE001
            log.warning("FRED %s 失败：%s", fid, e)
    sp = paths.state_dir() / "macro_seen.json"
    rel, seen = releases(raw, read_json(sp, {}) or {}, now)
    write_json(sp, seen)
    out["releases"] = rel
    ev = (read_json(paths.home() / "macro_events.json", {}) or {}).get("events") or []
    out["events"] = upcoming(ev, now.date())
    return out


def write(d: dict) -> None:
    write_json(paths.out_dir() / "macro_now.json", d)


def load() -> dict:
    return read_json(paths.out_dir() / "macro_now.json", {}) or {}
