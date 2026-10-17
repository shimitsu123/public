"""policy_event_verify.py — 事件表来源核对（机械）：逐行取 source_url（经环境代理），HTTP 200 且页面 / PDF 文本含该事件日期（或 boj.or.jp / federalreserve.gov
官方文件名里含日期）→ verified = 今天、checked_hash = 内容 sha256 前 8 位、http_status；取不到 / 不含日期 → verified 留空（只描述、不计入判定），
http_status 记下原因。不改其它列；结果只是「来源可达且日期对得上」，不代表分类正确。
用法：python scripts/policy_event_verify.py [--in var/policy_events.csv] [--out var/policy_events.csv] [--cache var/cache/policy_verify.json] [--only-blank] [--workers 3]
Mac 上打得开 meti / kantei 时也用它（同一规则）；手工核对用 run.py policy-event check（checked_hash = manual）。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                      # noqa: E402
from qbreak import policy_events as PEV                                       # noqa: E402

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
URL_DATE_DOMAINS = ("boj.or.jp", "federalreserve.gov")


def date_patterns(d: dt.date) -> list[str]:
    y, m, day = d.year, d.month, d.day
    return [d.isoformat(), f"{y}年{m}月{day}日", f"{y}年{m:02d}月{day:02d}日", f"{y}年 {m}月 {day}日", f"{MONTHS[m - 1]} {day}, {y}", f"{MONTHS[m - 1]} {day:02d}, {y}",
            f"{day} {MONTHS[m - 1]} {y}", f"{MONTHS[m - 1][:3]}. {day}, {y}", f"{MONTHS[m - 1][:3]} {day}, {y}", f"{y}/{m:02d}/{day:02d}", f"{y}/{m}/{day}", f"{m}/{day}/{y}",
            f"{y}{m:02d}{day:02d}", f"{y}.{m:02d}.{day:02d}", f"{y}.{m}.{day}", f"{y},{MONTHS[m - 1][:3]},{day}",                   # 財務省 CSV：2010,Sep,15
            f"令和{y - 2018}年{m}月{day}日" if y >= 2019 else f"平成{y - 1988}年{m}月{day}日",
            f"令和{y - 2018}年,{m}月,{day}日" if y >= 2019 else f"平成{y - 1988}年,{m}月,{day}日"]


def url_has_date(url: str, d: dt.date) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not any(host == x or host.endswith("." + x) for x in URL_DATE_DOMAINS):
        return False
    yymmdd, ymd = d.strftime("%y%m%d"), d.strftime("%Y%m%d")
    return yymmdd in url or ymd in url


def fetch(url: str, timeout: int = 40) -> tuple[int, bytes]:
    try:
        r = subprocess.run(["curl", "-sS", "-L", "-m", str(timeout), "-A", "Mozilla/5.0 (policy-event-verify)", "-o", "-", "-w", "\n%{http_code}", url],
                           capture_output=True, timeout=timeout + 10)
        body, _, code = r.stdout.rpartition(b"\n")
        return int(code or 0), body
    except Exception:                                                        # noqa: BLE001
        return 0, b""


def text_of(url: str, body: bytes) -> str:
    if body[:4] == b"%PDF":
        try:
            r = subprocess.run(["pdftotext", "-", "-"], input=body, capture_output=True, timeout=60)
            if r.returncode == 0 and r.stdout:
                return r.stdout.decode("utf-8", "ignore")
        except Exception:                                                    # noqa: BLE001
            pass
        return body.decode("latin-1", "ignore")
    for enc in ("utf-8", "shift_jis", "euc-jp", "cp932"):
        try:
            return body.decode(enc)
        except Exception:                                                    # noqa: BLE001
            continue
    return body.decode("utf-8", "ignore")


MOF_CSV = "foreign_exchange_intervention_operations.csv"
_ERA = {"平成": 1988, "令和": 2018, "昭和": 1925}


def mof_csv_dates(text: str) -> set[str]:
    """財務省介入 CSV（同月内の 2 日目以降は年・月セルが空 = 结合セル）→ 前方填充して実施日集合。"""
    out, y, m = set(), None, None
    for line in unicodedata.normalize("NFKC", text).splitlines():
        cells = line.split(",")
        if len(cells) < 6:
            continue
        c0, c1, c2 = cells[0].strip(), cells[1].strip(), cells[2].strip()
        mm = re.fullmatch(r"(平成|令和|昭和)(\d+)年", c0)
        if mm:
            y = _ERA[mm.group(1)] + int(mm.group(2))
        if re.fullmatch(r"\d+月", c1):
            m = int(c1[:-1])
        if re.fullmatch(r"\d+日", c2) and y and m:
            out.add(f"{y}-{m:02d}-{int(c2[:-1]):02d}")
    return out


def check_row(url: str, d: dt.date, cache: dict) -> dict:
    key = url
    if key not in cache:
        code, body = fetch(url)
        cache[key] = {"status": code, "hash": hashlib.sha256(body).hexdigest()[:8] if body else "", "text": text_of(url, body)[:2_000_000] if body else ""}
    c = cache[key]
    txt = unicodedata.normalize("NFKC", c["text"])                                       # 全角数字 / 空白 → 半角
    ok_date = any(p in txt for p in date_patterns(d)) or url_has_date(url, d)
    if not ok_date and url.endswith(MOF_CSV):
        ok_date = d.isoformat() in mof_csv_dates(c["text"])
    return {"status": c["status"], "hash": c["hash"], "date_ok": bool(ok_date)}


def run(inp: Path, out: Path, cache_fp: Path, only_blank: bool, workers: int, today: str) -> dict:
    E = pd.read_csv(inp, dtype=str).fillna("")
    for c in PEV.EVENT_COLS:
        if c not in E.columns:
            E[c] = ""
    cache = json.loads(cache_fp.read_text(encoding="utf-8")) if cache_fp.exists() else {}
    todo = [i for i, r in E.iterrows() if r["source_url"] and (not only_blank or not r["verified"])]
    urls = sorted({E.at[i, "source_url"] for i in todo if E.at[i, "source_url"] not in cache})
    print(f"行 {len(E)}，待核 {len(todo)}，要取 {len(urls)} 个 URL", flush=True)

    def _f(u):
        code, body = fetch(u)
        return u, {"status": code, "hash": hashlib.sha256(body).hexdigest()[:8] if body else "", "text": text_of(u, body)[:2_000_000] if body else ""}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for k, (u, c) in enumerate(ex.map(_f, urls), 1):
            cache[u] = c
            if k % 50 == 0:
                print(f"  取到 {k}/{len(urls)}", flush=True)
                cache_fp.parent.mkdir(parents=True, exist_ok=True)
                cache_fp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    cache_fp.parent.mkdir(parents=True, exist_ok=True)
    cache_fp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    n_ok = n_nodate = n_fail = 0
    for i in todo:
        r = E.loc[i]
        if r["checked_hash"] == "manual" and r["verified"]:
            continue
        res = check_row(r["source_url"], pd.Timestamp(r["date"]).date(), cache)
        E.at[i, "http_status"] = str(res["status"]) + ("" if res["status"] == 200 else "") + ("" if res["date_ok"] or res["status"] != 200 else "_nodate")
        if res["status"] == 200 and res["date_ok"]:
            E.at[i, "verified"], E.at[i, "checked_hash"] = today, res["hash"]
            n_ok += 1
        else:
            E.at[i, "verified"], E.at[i, "checked_hash"] = "", ""
            if res["status"] == 200:
                n_nodate += 1
            else:
                n_fail += 1
    E[PEV.EVENT_COLS].to_csv(out, index=False)
    summ = {"verified": n_ok, "reachable_nodate": n_nodate, "unreachable": n_fail, "by_host": {}}
    for i in todo:
        h = (urlparse(E.at[i, "source_url"]).hostname or "").replace("www.", "")
        s = E.at[i, "http_status"]
        summ["by_host"].setdefault(h, {}).setdefault(s, 0)
        summ["by_host"][h][s] += 1
    return summ


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(paths.PROJECT_ROOT / "var" / "policy_events.csv"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache", default=str(Path(paths.cache_dir()) / "policy_verify.json"))
    ap.add_argument("--only-blank", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--today", default=PEV.today_jst().isoformat())
    a = ap.parse_args(argv)
    summ = run(Path(a.inp), Path(a.out or a.inp), Path(a.cache), a.only_blank, a.workers, a.today)
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
