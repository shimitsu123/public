"""jquants.py — J-Quants API V2 客户端（JPX 官方数据；用于无幸存者偏差的研究与数据核对，日常交易不依赖它）。

认证：环境变量 JQUANTS_API_KEY → 请求头 x-api-key（J-Quants 网站仪表盘发行，无有效期；绝不要写进仓库或聊天）。
档位：环境变量 JQUANTS_PLAN = free / light / standard / premium（决定限速；不设按 free 最保守）。
  限速（2026-09-24 核对）：Free 5 次/分、Light 60、Standard 120、Premium 500；超过返回 HTTP 429。
  历史深度：Free 2 年（延迟 12 周）、Light 5 年、Standard 10 年、Premium 20 年（2008-05-07 起）。
端点（官方 V2 Quick Start）：/equities/master（上市一览，可按过去日期查询 → 时点股票池）、
  /equities/bars/daily（调整前后四本值）、/fins/earnings-date（决算发表预定日）、/markets/calendar、
  /indices/bars/daily/topix（Light+）、/bulk/list + /bulk/get（Light+，CSV 批量下载）。
缓存：var/cache/jquants/（var/cache 已被 .gitignore 忽略）。仓库是公开的，J-Quants 规约禁止再分发原始数据 → 缓存绝不能入库。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time

import pandas as pd

from . import paths
from .utils import setup_logging

log = setup_logging("jquants")

API = "https://api.jquants.com/v2"
RATE_PER_MIN = {"free": 5, "light": 60, "standard": 120, "premium": 500}
HISTORY_YEARS = {"free": 2, "light": 5, "standard": 10, "premium": 20}


class JQuantsError(RuntimeError):
    pass


def _curl_get(url: str, params: dict, headers: dict, timeout: int = 60) -> tuple[int, dict]:
    """curl_cffi（yfinance 的依赖）→ (HTTP 状态, JSON)。"""
    from curl_cffi import requests as cr
    r = cr.get(url, params=params, headers=headers, impersonate="chrome", timeout=timeout)
    try:
        body = r.json()
    except (ValueError, json.JSONDecodeError):
        body = {"message": r.text[:300]}
    return r.status_code, body


class JQuants:
    def __init__(self, api_key: str | None = None, plan: str | None = None,
                 http=None, sleep=time.sleep, clock=time.monotonic):
        self.key = api_key if api_key is not None else os.environ.get("JQUANTS_API_KEY", "")
        if not self.key:
            raise JQuantsError("没有设置 JQUANTS_API_KEY（在 J-Quants 仪表盘发行 API キー，放进环境变量；不要写进仓库）")
        self.plan = (plan or os.environ.get("JQUANTS_PLAN") or "free").lower()
        if self.plan not in RATE_PER_MIN:
            raise JQuantsError(f"JQUANTS_PLAN={self.plan} 无效（free / light / standard / premium）")
        self.min_interval = 60.0 / RATE_PER_MIN[self.plan] * 1.05
        self._http, self._sleep, self._clock = http or _curl_get, sleep, clock
        self._last = -1e9
        self.calls = 0

    # ── 基础请求：限速 + 429 退避 + 分页 ──
    def _once(self, path: str, params: dict) -> tuple[int, dict]:
        wait = self.min_interval - (self._clock() - self._last)
        if wait > 0:
            self._sleep(wait)
        status, body = self._http(f"{API}{path}", params, {"x-api-key": self.key})
        self._last = self._clock()
        self.calls += 1
        return status, body

    def get(self, path: str, **params) -> list[dict]:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        rows: list[dict] = []
        tries = 0
        while True:
            status, body = self._once(path, params)
            if status == 429 and tries < 3:                   # 超过限速：等一分钟再试
                tries += 1
                log.warning("J-Quants 429（限速），等待 60 秒后重试 %s", path)
                self._sleep(60)
                continue
            if status != 200:
                raise JQuantsError(f"{path} HTTP {status}: {body.get('message', body)}")
            rows += body.get("data") or []
            nxt = body.get("pagination_key")
            if not nxt:
                return rows
            params = {**params, "pagination_key": nxt}

    def try_get(self, path: str, **params) -> tuple[bool, str, list[dict]]:
        """档位探测用：成功 → (True, "", rows)；失败 → (False, 原因, [])。"""
        try:
            return True, "", self.get(path, **params)
        except JQuantsError as e:
            return False, str(e), []

    # ── 常用数据 ──
    def master(self, date: str | None = None, code: str | None = None) -> pd.DataFrame:
        return pd.DataFrame(self.get("/equities/master", date=date, code=code))

    def daily(self, code: str | None = None, date: str | None = None,
              frm: str | None = None, to: str | None = None) -> pd.DataFrame:
        return pd.DataFrame(self.get("/equities/bars/daily", code=code, date=date, **{"from": frm, "to": to}))

    def earnings_dates(self, code: str | None = None, date: str | None = None) -> pd.DataFrame:
        return pd.DataFrame(self.get("/fins/earnings-date", code=code, date=date))


# ────────────────────────── 一键检查（run.py jquants-check）──────────────────────────
def _code_col(df: pd.DataFrame) -> str | None:
    for c in ("Code", "code", "LocalCode"):
        if c in df.columns:
            return c
    return None


def check(client: JQuants, today: dt.date | None = None) -> dict:
    """确认：API キー有效、档位能用哪些端点、数据可取的最近 / 最早日期、历史日线是否包含后来退市的股票。
    请求数控制在 8～9 次（Free 档 5 次/分钟，约 2 分钟跑完）。"""
    today = today or dt.date.today()
    out: dict = {"plan_setting": client.plan, "endpoints": {}}
    ok, why, now = client.try_get("/equities/master")
    out["key_ok"] = ok
    if not ok:
        out["error"] = why
        return out
    now_df = pd.DataFrame(now)
    cc = _code_col(now_df)
    out["listed_now"] = int(now_df[cc].nunique()) if cc else len(now_df)
    codes = [str(c) for c in now_df[cc]] if cc else []
    sample = next((c for c in codes if c.startswith("7203")), codes[0] if codes else "72030")   # 用一览里的代码格式
    # 最近可取的日线：Free 延迟 12 周
    recent = (today - dt.timedelta(days=10)).isoformat()
    ok_r, why_r, rows_r = client.try_get("/equities/bars/daily", code=sample, **{"from": recent, "to": today.isoformat()})
    out["recent_daily_ok"] = bool(ok_r and rows_r)
    out["recent_daily_note"] = "" if out["recent_daily_ok"] else (why_r or "近期数据不可取（Free 档有 12 周延迟）")
    # 档位专属端点
    for path, need, params in (("/indices/bars/daily/topix", "light", {"from": (today - dt.timedelta(days=200)).isoformat()}),
                               ("/fins/dividend", "premium", {"code": sample})):
        ok_e, why_e, _ = client.try_get(path, **params)
        out["endpoints"][path] = {"ok": ok_e, "needs": need, "note": "" if ok_e else why_e[:160]}
    # 历史窗口起点：按设置的档位推算，再实际取一次
    yrs = HISTORY_YEARS[client.plan]
    delay = 84 if client.plan == "free" else 0
    start = today - dt.timedelta(days=int(365.25 * yrs) - 14 + delay)
    probe_d = start.isoformat()
    ok_m, why_m, then = client.try_get("/equities/master", date=probe_d)
    out["history_probe_date"] = probe_d
    out["history_master_ok"] = ok_m
    if not ok_m:
        out["history_note"] = why_m[:200]
        return out
    then_df = pd.DataFrame(then)
    c2 = _code_col(then_df)
    gone = sorted(set(then_df[c2]) - set(now_df[cc])) if (c2 and cc) else []
    out["delisted_since_probe"] = len(gone)
    # 取一只后来退市的股票，看历史日线里有没有它
    out["delisted_in_daily"] = None
    if gone:
        code = gone[0]
        end = (start + dt.timedelta(days=30)).isoformat()
        ok_d, why_d, rows_d = client.try_get("/equities/bars/daily", code=code, **{"from": probe_d, "to": end})
        out["delisted_sample"] = code
        out["delisted_in_daily"] = bool(ok_d and rows_d)
        if not ok_d:
            out["delisted_note"] = why_d[:200]
    out["calls"] = client.calls
    return out


def summarize(r: dict) -> str:
    if not r.get("key_ok"):
        return f"✗ API キー无效或无法连接：{r.get('error', '')}"
    L = [f"✓ API キー有效；当前上市 {r.get('listed_now')} 只（JQUANTS_PLAN={r['plan_setting']}）",
         f"{'✓' if r.get('recent_daily_ok') else '—'} 最近 10 天日线{'可取' if r.get('recent_daily_ok') else '不可取：' + r.get('recent_daily_note', '')}"]
    for p, e in r.get("endpoints", {}).items():
        L.append(f"{'✓' if e['ok'] else '—'} {p}（需要 {e['needs']} 档）{'' if e['ok'] else '：' + e['note']}")
    if r.get("history_master_ok"):
        L.append(f"✓ {r['history_probe_date']} 时点的上市一览可取（时点股票池）；此后退市 {r.get('delisted_since_probe')} 只")
        d = r.get("delisted_in_daily")
        if d is True:
            L.append(f"✓ 退市股 {r.get('delisted_sample')} 的历史日线可取 → 能做无幸存者偏差回测")
        elif d is False:
            L.append(f"✗ 退市股 {r.get('delisted_sample')} 的历史日线取不到 {r.get('delisted_note', '')} → 幸存者偏差无法完全去除")
    else:
        L.append(f"— {r.get('history_probe_date')} 时点数据不可取：{r.get('history_note', '')}（JQUANTS_PLAN 是否与实际档位一致？）")
    L.append(f"本次请求 {r.get('calls', '?')} 次")
    return "\n".join(L)


def cache_dir():
    return paths.sub("cache/jquants")
