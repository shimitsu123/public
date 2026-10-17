"""jpx_list.py — JPX「東証上場銘柄一覧」（data_j.xlsx，每月更新；公开数据）：公司名、市场区分、33 业种。
用途：日报 / 关联对比里显示公司名；找「新出现的公司」（最新名单里有、基准快照 var/jpx_codes_base.json 里没有的内国株；
scripts/theme_link_check.py --new-listings）。名称快照 var/jpx_names.json 只存 TOPIX 1000（industry_s33.json）+ 主题成员 + 日経225。
给人看的「代码 名字」统一用 qbreak/names.py（2026-10-15；这里的 names() / label() 保留给研究脚本，names() 不给路径时也转调它）。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from . import paths

URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx"
NAMES_FILE, BASE_FILE = "jpx_names.json", "jpx_codes_base.json"
DOMESTIC = ("プライム（内国株式）", "スタンダード（内国株式）", "グロース（内国株式）")


def parse(raw: bytes | str | Path) -> pd.DataFrame:
    """data_j.xlsx → DataFrame（列：code, name, market, s33, size, date）。"""
    src = io.BytesIO(raw) if isinstance(raw, (bytes, bytearray)) else raw
    J = pd.read_excel(src, dtype=str)
    return pd.DataFrame({"code": J["コード"].str.strip(), "name": J["銘柄名"].str.strip(), "market": J["市場・商品区分"],
                         "s33": J["33業種区分"], "size": J["規模区分"], "date": J["日付"]})


def fetch() -> pd.DataFrame:
    """最新的名单（缓存 24 小时，var/cache/factors/jpx_list.csv）。"""
    from .factors import _cached, _get
    return _cached("jpx_list", lambda: parse(_get(URL, timeout=120)).set_index("code"), 24.0).reset_index()


def names(path: Path | None = None) -> dict[str, str]:
    """代码 → 公司名（名称快照；没有文件时空）。不给 path → 数据目录的快照，没有就用仓库 var/ 的（qbreak/names.py；
    2026-10-15：Mac 的数据目录没有 jpx_names.json，以前这里返回空 → 日报 / 研究脚本在 Mac 上只剩代码）。"""
    if not path:
        from .names import jpx_snapshot
        return jpx_snapshot()
    fp = Path(path)
    return (json.loads(fp.read_text(encoding="utf-8")) or {}).get("names", {}) if fp.exists() else {}


def label(ticker: str, nm: dict[str, str] | None = None) -> str:
    """「5803.T」→「5803 フジクラ」（没有名字就只写代码）。nm 不给 → qbreak/names.py 的 label（含 ETF 名字表）。"""
    if nm is None:
        from .names import label as _label
        return _label(ticker)
    code = ticker.split(".")[0]
    return f"{code} {nm[code]}" if code in nm else code


def base_codes(path: Path | None = None) -> set[str]:
    """基准快照里的内国株代码（2026-08-31 版）。"""
    fp = Path(path or paths.home() / BASE_FILE)
    return set((json.loads(fp.read_text(encoding="utf-8")) or {}).get("codes", [])) if fp.exists() else set()


def base_asof(path: Path | None = None) -> str:
    fp = Path(path or paths.home() / BASE_FILE)
    return str((json.loads(fp.read_text(encoding="utf-8")) or {}).get("as_of", "—")) if fp.exists() else "—"
