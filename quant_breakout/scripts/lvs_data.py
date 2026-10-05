"""lvs_data.py — 大量保有報告書（EDINET；J-Quants /v2/edinet/large-volume-shareholders，Standard 已含、提出日 2021-07-01 起）的取数与整理。

用途：研究「大量保有 × 全市場 W2 突破」（scripts/lvs_study.py）。只作研究，不进交易。
原始记录含个人的姓名、住址、借款对象 → 只放已 gitignore 的 var/cache/jquants/edinet_lvs/（每个提出日一个 JSON），绝不入库；
整理后的表（var/cache/jquants/out/lvs_filings.pkl）只留代码、日期、比例与几个布尔 / 分类字段，同样只在缓存里；仓库里只放汇总数字。
取数：按提出日（工作日）逐日取，已经取过的日子不重取（最近 7 天每次重取，订正会补进来）；Standard 120 次 / 分钟（qbreak.jquants 限速）。
用法：python scripts/lvs_data.py --fetch（取数）；--build（整理成表）；--summary（只数个数）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                      # noqa: E402

START = "2021-07-01"
API_PATH = "/edinet/large-volume-shareholders"
SUB = "edinet_lvs"
OUT_PKL = "lvs_filings.pkl"
REFETCH_DAYS = 7
NEW_TYPES = ("1", "4")                                                         # 大量保有書類種別：1 大量保有報告書 / 4 同（特例対象株券等）
_PUNCT = re.compile(r"[\s。｡．.、,，・\-－―ー（）()「」]")
_NEG_END = re.compile(r"(ません|なし|無し|無|ない|なく|せず)$")                     # 「該当事項はございません」「当該事項なし」「予定はない」= 没有
_IMP = re.compile(r"重要提案")


def cache_dir() -> Path:
    d = paths.home() / "cache" / "jquants" / SUB
    d.mkdir(parents=True, exist_ok=True)
    return d


def out_path() -> Path:
    d = paths.home() / "cache" / "jquants" / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d / OUT_PKL


def weekdays(start: str, end: str) -> list[str]:
    return [str(d.date()) for d in pd.bdate_range(start, end)]


def fetch(start: str = START, end: str | None = None, client=None, say=None) -> dict:
    """提出日 start〜end 的工作日逐日取；已有文件且不在最近 REFETCH_DAYS 天的不重取。"""
    from qbreak.jquants import JQuants
    say = say or (lambda m: print(m, flush=True))
    c = client or JQuants(plan="standard")
    end = end or str(dt.date.today())
    recent = str((pd.Timestamp(end) - pd.Timedelta(days=REFETCH_DAYS)).date())
    n_new = n_rows = 0
    days = weekdays(start, end)
    for i, d in enumerate(days):
        fp = cache_dir() / f"{d}.json"
        if fp.exists() and d < recent:
            continue
        rows = c.get(API_PATH, date=d)
        fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        n_new += 1
        n_rows += len(rows)
        if n_new % 100 == 0:
            say(f"取了 {n_new} 天（到 {d}；{i + 1} / {len(days)}）")
    return {"days": len(days), "fetched": n_new, "rows": n_rows}


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def substantive(text) -> bool:
    """「重要提案行為等」一栏是否有实际内容：去掉空白与标点后为空、或以否定结尾（ません / なし / 無 / ない …）= 没有；
    「重要提案行為等を行う可能性がある」「…ことがあります」= 有。只用于描述（imp），不进任何候选。"""
    t = _PUNCT.sub("", _txt(text))
    return bool(t) and not _NEG_END.search(t)


def parse_doc(doc: dict) -> dict:
    """一份报告 → 一行（不含姓名、住址等个人信息）。"""
    hs = doc.get("Hldrs") or []
    buy_m = sell_m = buy_o = sell_o = False
    for h in hs:
        for a in h.get("AcqDisp") or []:
            mk, tx = _txt(a.get("MktCode")), _txt(a.get("TxnTypeCode"))
            buy_m |= mk == "1" and tx == "1"
            sell_m |= mk == "1" and tx == "2"
            buy_o |= mk == "2" and tx == "1"
            sell_o |= mk == "2" and tx == "2"
    purp = " / ".join(sorted({_txt(h.get("HldgPurp")) for h in hs if _txt(h.get("HldgPurp"))}))
    imp_any = any(substantive(h.get("ImpProp")) for h in hs)
    purp_imp = bool(_IMP.search(purp))
    r, rl = doc.get("TotalShsRatio"), doc.get("TotalShsRatioLast")
    code = _txt(doc.get("Code"))
    return {"doc_id": _txt(doc.get("DocId")), "par_doc_id": _txt(doc.get("ParDocId")), "code": code,
            "ticker": (code[:4] + ".T") if len(code) >= 4 else None,
            "sub_date": _txt(doc.get("SubDate")), "sub_time": _txt(doc.get("SubTime")), "rpt_date": _txt(doc.get("RptOblgDate")),
            "doc_type": _txt(doc.get("DocTypeCode")), "lh_type": _txt(doc.get("LargeHldgTypeCode")),
            "ratio": float(r) if r is not None else np.nan, "ratio_last": float(rl) if rl is not None else np.nan,
            "n_hldr": len(hs), "corp": any(_txt(h.get("LargeHldrTypeCode")) == "2" for h in hs),
            "indiv": any(_txt(h.get("LargeHldrTypeCode")) == "1" for h in hs),
            "purpose": purp, "imp": bool(imp_any or purp_imp), "buy_mkt": buy_m, "sell_mkt": sell_m, "buy_off": buy_o, "sell_off": sell_o}


def build(say=print) -> pd.DataFrame:
    rows = []
    for fp in sorted(cache_dir().glob("*.json")):
        for doc in json.loads(fp.read_text(encoding="utf-8")) or []:
            rows.append(parse_doc(doc))
    T = pd.DataFrame(rows)
    if len(T):
        T = T.drop_duplicates(subset=["doc_id"]).reset_index(drop=True)
        T["sub_date"] = pd.to_datetime(T["sub_date"])
        T["d_ratio"] = np.where(T["lh_type"].isin(NEW_TYPES), T["ratio"], T["ratio"] - T["ratio_last"])     # 新进（1 / 4 特例）= 整个比例
    T.to_pickle(out_path())
    say(f"整理了 {len(T)} 份 → {out_path()}")
    return T


def summary(T: pd.DataFrame) -> dict:
    """只数个数（不看任何收益）。"""
    if not len(T):
        return {"n": 0}
    o = T[T["doc_type"] == "350"]
    return {"n": int(len(T)), "n_350": int(len(o)), "n_360": int((T["doc_type"] == "360").sum()),
            "first": str(T["sub_date"].min().date()), "last": str(T["sub_date"].max().date()),
            "lh_type": o["lh_type"].value_counts().to_dict(), "issuers": int(o["ticker"].nunique()),
            "inc": int((o["d_ratio"] > 0).sum()), "dec": int((o["d_ratio"] < 0).sum()),
            "buy_mkt": int(o["buy_mkt"].sum()), "sell_mkt": int(o["sell_mkt"].sum()), "imp": int(o["imp"].sum()),
            "inc_buy_mkt": int(((o["d_ratio"] > 0) & o["buy_mkt"]).sum()), "dec_sell_mkt": int(((o["d_ratio"] < 0) & o["sell_mkt"]).sum()),
            "by_year": o.groupby(o["sub_date"].dt.year).size().to_dict()}


def load() -> pd.DataFrame:
    fp = out_path()
    if not fp.exists():
        raise SystemExit(f"缺 {fp}：先运行 python scripts/lvs_data.py --fetch --build")
    T = pd.read_pickle(fp)
    T["sub_date"] = pd.to_datetime(T["sub_date"])
    return T


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="大量保有報告書：取数 / 整理 / 只数个数")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--end", default=None)
    a = ap.parse_args(argv)
    if a.fetch:
        print(json.dumps(fetch(end=a.end), ensure_ascii=False), flush=True)
    if a.build:
        build()
    if a.summary:
        print(json.dumps(summary(load()), ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
