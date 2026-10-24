"""household_spend.py — 総務省「家計調査」（家計収支編・二人以上の世帯・品目分類）的月度品目支出 → 研究用的取数模块（只取数，不做分析）。

数据（2026-10-11 查到；仅对检索时点有效）：
  e-Stat 统计 00200561「家計調査」/ 家計収支編 / 二人以上の世帯 / 品目分類，全国（地域 00000），世帯区分 03「二人以上の世帯（2000年～）」，月次：
    • statsDataId=0004023601  品目分類 010「品目分類（2025年改定）（総数：金額）」 —— 1 世帯当たり 1 か月間の支出金額（円）
    • statsDataId=0004023602  品目分類 011「品目分類（2025年改定）（総数：数量）」 —— 1 世帯当たり購入数量（单位见各品目：
      米 kg、牛乳 / ビール / 発泡酒 / ガソリン l、清酒 / 焼酎 / ウイスキー / ワイン / チューハイ ml、肉 / 魚 / 野菜 / パン / 卵 g、電気 kWh；
      只有部分品目有数量，大分类（果物、外食、被服…）没有）
    两张表的時間軸都从 1985-01 列起，但世帯区分 03 从 2000-01 才有数（之前是「農林漁家世帯を除く」的 01，口径不同 → 不用）；
    2026-10-09 更新到 2026-08。2025 年改定的表把过去的数按新分类遡及集計（stat.go.jp/data/kakei/change2025.html）；
    2026-10-11 实测：2025 年版与 2020 年版（0003343671 / 0003343670）重叠的月份（品目各 120〜300 个月），这里用的 50 个品目
    金额与数量的差都 ≤ 0.5% → 2025 年版一张表就覆盖 2000-01〜2026-08，旧表实际没有补进任何月份。
  后备 / 核对：statsDataId=0003343671（2020年改定・総数：金額，月次，到 2024-12）、0003343670（2020年改定・総数：数量）。
    chain() 只用旧表补「新表某品目第一个有数的月之前」的月份（不交错）；同一月份两表都有时用新表。品目代码两版相同。
    更旧的分类版（不用：2025 年版已遡及到 2000-01）：平成27年改定 0003125169（金額）/ 0003125093（数量），
    平成22年改定 0003021328（金額），平成17年改定 0002070023（金額）/ 0002070020（数量）。

  取数走 e-Stat 网页「表ダウンロード」的内部接口（不要 appId；非公开接口，可能会变；复用 qbreak/invest_flow._download）。
  原表只缓存在 <数据目录>/cache/estat/（var/cache/ 已 gitignore；e-Stat 的数据本身可以公开，但这里照仓库的习惯不入库原表）。

已知的口径变化 / 断层（用的时候要注意）：
  • 2000-01：世帯区分 03 起点（含農林漁家世帯）。
  • 2015-01 / 2020-01 / 2025-01：收支项目分类改定（新表已遡及集計；个别品目的内容变了，例如
    「913 他の化粧品（2014年までは915を含む）」「389 他の飲料のその他（2014年までは38Yスポーツドリンクを含む）」）。
  • 2018-01：调查票（家計簿）改正（记入方式变了，消费支出有偏高的影响；統計局另外公表「変動調整値」，这里不调整）。
  • 发泡酒（011100060）：2000〜2003 只有発泡酒，2004 年起「ビール風（新ジャンル）」出现后算进同一品目 → 内容随市场变；
    チューハイ・カクテル 2015-01 才设（之前在「他の酒」）；カップ麺 / ミネラルウォーター 2005-01 起；電気代 的数量（kWh）2005-01 起。
  • 2025-01：「発泡酒・ビール風アルコール飲料」改名「発泡酒」（2023-10 酒税改正后新ジャンル表示为発泡酒；只是改名，代码 011100060 不变）。
  • 2019-10 消费税 8→10%（前月的抢购 / 之后的反动）、2020〜2022 新冠（外食 / 宿泊 / パック旅行 断崖式下跌）是行为变化，不是口径断层。
  • 样本约 9,000 户（二人以上）→ 小品目（ウイスキー、ワイン、パック旅行…）月度噪音很大。

公布时点（as-of 对齐用；e-Stat 公表予定 https://www.e-stat.go.jp/release-calendar/statistics/00200561 ，2026-10-11 查）：
  月次「二人以上の世帯」= 调查月的「翌々月上旬〜中旬」08:30 JST（第 4〜12 天）。实测 / 预定：
  2025-12→2026-02-06、2026-01→03-10、02→04-07、03→05-12、04→06-05、05→07-07、06→08-07、07→09-04、08→10-09、
  09→11-10、10→12-08、11→2027-01-08。滞后约 36〜42 天。
  → available_from(month)：保守地从「调查月 + 2 个月」的月末起才用（例：2026-08 → 2026-10-31）。
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import pandas as pd

from . import paths

STAT_CODE = "00200561"
CHECKED = "2026-10-11"
RELEASE_URL = "https://www.e-stat.go.jp/release-calendar/statistics/00200561"

# (statsDataId, kind, 改定) —— 新的在前；chain 时新表优先
SOURCES: list[tuple[str, str, str]] = [
    ("0004023601", "yen", "2025"),
    ("0004023602", "qty", "2025"),
    ("0003343671", "yen", "2020"),
    ("0003343670", "qty", "2020"),
]
HOUSEHOLD = "03"            # 二人以上の世帯（2000年～）
AREA = "00000"              # 全国
FIRST_MONTH = "2000-01"

# 品目代码（2020 / 2025 年改定相同）→ 简称
ITEMS: dict[str, str] = {
    "001100000": "消費支出",
    "010000000": "食料",
    "010110001": "米", "010120000": "パン", "010130000": "麺類", "010130050": "カップ麺",
    "010210000": "生鮮魚介",
    "010310000": "生鮮肉", "010310010": "牛肉", "010310020": "豚肉", "010310030": "鶏肉",
    "010410001": "牛乳", "010420000": "乳製品", "010430001": "卵",
    "010510000": "生鮮野菜", "010600000": "果物",
    "010800000": "菓子類", "010900000": "調理食品",
    "011000000": "飲料", "011010000": "茶類", "011020000": "コーヒー・ココア", "011030000": "他の飲料",
    "011030020": "炭酸飲料", "011030010": "果実・野菜ジュース", "011030050": "ミネラルウォーター",
    "011100000": "酒類", "011100010": "清酒", "011100020": "焼酎", "011100030": "ビール", "011100040": "ウイスキー",
    "011100050": "ワイン", "011100060": "発泡酒", "011100070": "チューハイ・カクテル",
    "011200000": "外食", "011210000": "一般外食", "011220001": "学校給食",
    "100140001": "たばこ",
    "030100000": "電気代", "030200000": "ガス代",
    "070230010": "ガソリン",
    "100121040": "石けん類・化粧品",
    "060100000": "医薬品",
    "050000000": "被服及び履物",
    "040000000": "家具・家事用品",
    "090000000": "教養娯楽", "090410001": "宿泊料", "090420000": "パック旅行費",
    "070300000": "通信", "070300030": "携帯電話通信料",
    "070200000": "自動車等関係費",
}
MAP_FILE = paths.PROJECT_ROOT / "var" / "household_items.json"


def cache_dir() -> Path:
    p = paths.sub("cache") / "estat"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ───────────────────────── 取数 ─────────────────────────
def _want(sid: str, items: list[str]) -> tuple[dict[int, set[str]], dict]:
    """按维度名找 matterId（品目 / 世帯区分 / 地域）；接口的编号不保证固定。"""
    from curl_cffi import requests as cr
    base = "https://www.e-stat.go.jp/"
    S = cr.Session(impersonate="chrome")
    S.get(f"{base}dbview?sid={sid}", timeout=60).raise_for_status()
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}dbview?sid={sid}",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    m = S.post(f"{base}dbview/api_get_model?sid={sid}", data="", headers=hdr, timeout=120).json()
    if not isinstance(m, dict) or not isinstance(m.get("matters"), dict) or not m["matters"]:
        raise RuntimeError(f"e-Stat 返回的表结构是空的（{sid}；可能被限流，过一会儿再试）")
    want: dict[int, set[str]] = {}
    for mt in m["matters"].values():
        name = str(mt.get("matterName") or "")
        codes = {e["code"] for e in mt["listData"].values()}
        if "品目" in name:
            want[mt["matterId"]] = set(items) & codes
        elif "世帯区分" in name:
            want[mt["matterId"]] = {HOUSEHOLD}
        elif "地域" in name:
            want[mt["matterId"]] = {AREA}
    if len(want) != 3:
        raise RuntimeError(f"e-Stat 维度名对不上（{sid}）：{[mt.get('matterName') for mt in m['matters'].values()]}")
    return want, m


def download(sid: str, items: list[str] | None = None, refresh: bool = False, retries: int = 3, wait: int = 60) -> bytes:
    """一张表（全国・二人以上・全部月份・指定品目）的原始 CSV → <数据目录>/cache/estat/hh_<sid>.csv（不入库）。"""
    fp = cache_dir() / f"hh_{sid}.csv"
    if fp.exists() and not refresh:
        return fp.read_bytes()
    from .invest_flow import _download
    err: Exception | None = None
    for k in range(retries):
        try:
            want, _ = _want(sid, list(items or ITEMS))
            raw = _download(sid, want)
            if "/品目分類".encode() not in raw:
                raise RuntimeError(f"e-Stat 下载的内容不是品目分類的表（{sid}）")
            fp.write_bytes(raw)
            return raw
        except Exception as e:                                            # 网络超时 / 限流 → 等一会儿重试
            err = e
            time.sleep(wait * (k + 1))
    raise RuntimeError(f"e-Stat 取数失败（{sid}）：{err}")


# ───────────────────────── 解析 ─────────────────────────
def _num(s: str) -> float | None:
    v = (s or "").replace(",", "").strip()
    if not v or v in ("***", "*", "-", "…", "X", "x"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _month(code: str) -> str | None:
    """時間軸（月次）代码 YYYY00MMMM（例 2026000808）→ 'YYYY-MM'；不是月（年 / 四半期）→ None。"""
    c = str(code).strip()
    if len(c) != 10 or not c.isdigit():
        return None
    mm = c[-2:]
    if c[-4:-2] != mm or not ("01" <= mm <= "12"):
        return None
    return f"{c[:4]}-{mm}"


def parse_csv(raw: bytes, household: str = HOUSEHOLD, area: str = AREA) -> pd.DataFrame:
    """e-Stat「表ダウンロード」CSV（品目在列：先是「/品目分類… コード」行，再是表头行，再是数据；可能几个文件接在一起）
    → 长表 month / item_code / item_name / value。只留指定的世帯区分与地域、月次。"""
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    out = []
    k = 0
    while k < len(lines):
        ln = lines[k]
        if not (ln.startswith('"",') and "/品目分類" in ln and "コード" in ln):
            k += 1
            continue
        codes = next(csv.reader([ln]))
        j = k + 1
        while j < len(lines) and "時間軸" not in lines[j]:
            j += 1
        if j >= len(lines):
            break
        hdr = next(csv.reader([lines[j]]))
        ix_t = next(i for i, h in enumerate(hdr) if "時間軸" in h and h.endswith("コード"))
        ix_h = next((i for i, h in enumerate(hdr) if "世帯区分" in h and h.endswith("コード")), None)
        ix_a = next((i for i, h in enumerate(hdr) if "地域" in h and h.endswith("コード")), None)
        cols = {i: codes[i] for i in range(len(hdr)) if i < len(codes) and codes[i].isdigit()}
        names = {i: hdr[i].split("【")[0].split(" ", 1)[-1].strip() for i in cols}
        j += 1
        while j < len(lines) and lines[j].startswith('"'):
            r = next(csv.reader([lines[j]]))
            j += 1
            if len(r) < len(hdr):
                continue
            if ix_h is not None and r[ix_h] != household:
                continue
            if ix_a is not None and r[ix_a] != area:
                continue
            mo = _month(r[ix_t])
            if mo is None:
                continue
            for i, code in cols.items():
                v = _num(r[i])
                if v is not None:
                    out.append((mo, code, names[i], v))
        k = j
    return pd.DataFrame(out, columns=["month", "item_code", "item_name", "value"])


# ───────────────────────── 接表 ─────────────────────────
def chain(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """几张长表（month / item_code / item_name / value [/ source]），新的在前 → 每个品目一条连续的序列：
    新表有数的月份全用新表；旧表只补「新表该品目第一个有数的月」之前的月份（不交错、不平均）。"""
    acc: pd.DataFrame | None = None
    for f in frames:
        f = f.dropna(subset=["value"])
        if acc is None or acc.empty:
            acc = f.copy()
            continue
        first = acc.groupby("item_code")["month"].min()
        lim = f["item_code"].map(first)
        add = f[lim.isna() | (f["month"] < lim)]
        acc = pd.concat([acc, add], ignore_index=True)
    if acc is None:
        return pd.DataFrame(columns=["month", "item_code", "item_name", "value"])
    return acc.sort_values(["item_code", "month"]).reset_index(drop=True)


def overlap_diff(new: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    """新旧两表同月同品目的差（核对遡及集計有没有改过去的数）：品目 × 重叠月数 / 最大相对差（%）。"""
    m = new.merge(old, on=["month", "item_code"], suffixes=("", "_old"))
    m = m[m["value_old"] != 0]
    m["rel"] = (m["value"] / m["value_old"] - 1).abs() * 100
    return m.groupby("item_code").agg(n=("rel", "size"), max_rel_pct=("rel", "max")).reset_index()


def fetch(refresh: bool = False, use_old: bool = True, items: list[str] | None = None) -> pd.DataFrame:
    """取数 + 接表 → 整理好的长表 month（YYYY-MM）/ item_code / item_name / yen（円/世帯・月）/ qty（购入数量，没有 = NaN）。
    整理结果也缓存在 cache/estat/household_spend.csv（不入库）。"""
    fp = cache_dir() / "household_spend.csv"
    if fp.exists() and not refresh and items is None:
        return pd.read_csv(fp, dtype={"item_code": str, "month": str, "source": str, "qty_source": str})
    items = list(items or ITEMS)
    by_kind: dict[str, list[pd.DataFrame]] = {"yen": [], "qty": []}
    for sid, kind, rev in SOURCES:
        if rev != "2025" and not use_old:
            continue
        df = parse_csv(download(sid, items, refresh=refresh))
        df = df[df["item_code"].isin(items) & (df["month"] >= FIRST_MONTH)]
        by_kind[kind].append(df.assign(source=sid))
    yen = chain(by_kind["yen"]).rename(columns={"value": "yen"})
    qty = chain(by_kind["qty"]).rename(columns={"value": "qty", "source": "qty_source"})
    out = yen.merge(qty[["month", "item_code", "qty", "qty_source"]], on=["month", "item_code"], how="left")
    out["item_name"] = out["item_code"].map(ITEMS).fillna(out["item_name"])
    out = out[["month", "item_code", "item_name", "yen", "qty", "source", "qty_source"]]
    out = out.sort_values(["item_code", "month"]).reset_index(drop=True)
    if items == list(ITEMS):
        out.to_csv(fp, index=False)
    return out


def load(value: str = "yen", refresh: bool = False) -> pd.DataFrame:
    """宽表：index = month（'YYYY-MM'），列 = 品目简称（ITEMS 的顺序），值 = yen 或 qty。"""
    df = fetch(refresh=refresh)
    w = df.pivot_table(index="month", columns="item_name", values=value, aggfunc="first")
    order = [n for n in ITEMS.values() if n in w.columns]
    return w[order].sort_index()


def available_from(month: str) -> pd.Timestamp:
    """调查月 'YYYY-MM' 的数字从哪天起可以用（保守）：调查月 + 2 个月的月末（实际公布在 + 2 个月的第 4〜12 天 08:30 JST）。"""
    p = pd.Period(month, freq="M") + 2
    return p.to_timestamp(how="end").normalize()


def coverage(df: pd.DataFrame, col: str = "yen") -> pd.DataFrame:
    """每个品目：月数、第一 / 最后的月、中间缺的月数。"""
    rows = []
    for code, g in df.dropna(subset=[col]).groupby("item_code"):
        ms = sorted(g["month"])
        full = pd.period_range(ms[0], ms[-1], freq="M").strftime("%Y-%m")
        rows.append((code, ITEMS.get(code, g["item_name"].iloc[0]), len(ms), ms[0], ms[-1], len(set(full) - set(ms))))
    return pd.DataFrame(rows, columns=["item_code", "item_name", "n", "first", "last", "gaps"])


def item_map() -> dict:
    """var/household_items.json（品目 → 直接相关的上市公司 / 东证 33 业种）。"""
    return json.loads(MAP_FILE.read_text(encoding="utf-8"))
