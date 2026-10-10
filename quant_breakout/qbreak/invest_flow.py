"""invest_flow.py — 按行业的季度设备投资（財務省「法人企業統計調査」季報）→「谁在加大投资、投资的钱流向哪些行业」。

用户（2026-09-29）：「要做一个趋势分析研究 比如现在 ai 投资的变多了相对占比就会变多 房地产投资多了 原材料就会涨等等这类
微不足道的小事也要考虑到进行横展开 依据每三个月的行业统计 来按照这个逻辑来顺便考虑模拟盘的选股」。研究见 scripts/invest_flow_study.py。

数据（2026-09-29 查到；仅对检索时点有效）：
  季報 时系列 e-Stat statsDataId=0003060191（金融業・保険業以外、原数值），規模 25 = 資本金 10 億円以上（全数调查，
  资本金 5 億円未満 的抽样每年 4〜6 月期换样本 → 水平断层，不用）；项目 040 設備投資（新設固定資産合計，含软件；软件 2001Q3 起）、
  225 ソフトウェアを除く。取数走 e-Stat 网页「表ダウンロード」的内部接口（不要 appId；非公开接口，可能会变）→
  原表只在 var/cache/mof/（不入库），研究只存导出的统计。
  公布：季末后第 3 个月第 1 个工作日 08:50 JST（2015〜2026 实测滞后 60〜65 天）→ 保守地「季末那个月 + 3 个月」的月末才用
  （例：4〜6 月期 → 9 月末）；例外：2020 年 1〜3 月期 7-27 才出确报（覆盖了数据库）→ 7 月末才用。
  固定資本マトリックス（民間）2020 年（総務省 2025-02-14；资本财 120 × 投资部门 155，百万円）→ 谁的投资买了哪些资本财；
  再用产业连关表（2020，108 部门，竞争输入型：扣掉进口）的逆矩阵 → 每个东证业种的国内产出里有多少是「哪个行业的设备投资」带来的。
"""
from __future__ import annotations

import base64
import csv
import gzip
import json
import time
import urllib.parse

import numpy as np
import pandas as pd

from . import paths

SID = "0003060191"
ITEMS = {"040": "capex", "225": "capex_ex_sw"}
SIZE = "25"                                               # 資本金 10 億円以上（全数调查）
TOTAL = "104"                                             # 全産業（除く金融保険業）
FCM_URL = "https://www.soumu.go.jp/main_content/000990936.xlsx"   # 2020 年 固定資本マトリックス（民間）
FCM_FILE = "io2020_fcm_private.xlsx"
MOF_FILE = "ssc_capex_q.csv"

# MOF 业种 → 东証业种（「自己加大投资」SELF 用；同一个东証业种的几个 MOF 业种加总；2009Q2 分类改版前后用同一组码加总 = 连续）
MOF_TSE: dict[str, list[str]] = {
    "水産・農林業": ["105"], "鉱業": ["106"], "建設業": ["107"], "食料品": ["109"], "繊維製品": ["110", "111", "163"],
    "パルプ・紙": ["113"], "化学": ["115"], "石油・石炭製品": ["116"], "ガラス・土石製品": ["117"], "鉄鋼": ["118"],
    "非鉄金属": ["119"], "金属製品": ["120"], "機械": ["121", "154"], "電気機器": ["122", "145"], "輸送用機器": ["123", "125"],
    "精密機器": ["124"], "その他製品": ["126", "112", "114"], "電気・ガス業": ["135", "136"], "陸運業": ["131"], "海運業": ["132"],
    "倉庫・運輸関連業": ["133"], "情報・通信業": ["142"], "卸売業": ["127"], "小売業": ["128", "148"], "不動産業": ["130"],
    "サービス業": ["137"], "その他金融業": ["149"]}
# 固定資本マトリックスの投資部門（2 桁 or 列码）→ MOF 业种组（「投资的钱流向哪里」DEM 用）；没有对应的（家计住宅、金融保险、公务、
# 教育研究、医疗福祉、会员团体、分类不明）不算（覆盖率在报告里写明）
FCM_MOF: dict[str, list[str]] = {
    "01": ["105"], "02": ["106"], "03": ["109"], "04": ["110", "111", "163"], "05": ["112", "113"], "06": ["115"], "07": ["116"],
    "08": ["126"], "09": ["117"], "10": ["118"], "11": ["119"], "12": ["120"], "13": ["121", "154"], "14": ["121", "154"],
    "15": ["124"], "16": ["122", "145"], "17": ["122", "145"], "18": ["122", "145"], "19": ["123", "125"], "20": ["126", "114"],
    "21": ["107"], "22": ["135", "136"], "23": ["135", "136"], "24": ["137"], "25-0011": ["127"], "25-0012": ["128"], "27": ["130"],
    "28-0010": ["131"], "28-0020": ["131"], "28-0040": ["132"], "28-0050": ["133"], "28-0060": ["133"], "28-0070": ["133"],
    "28-0080": ["133"], "28-0090": ["133"], "29": ["142"], "34-0010": ["149"], "34-0020": ["137"], "34-0030": ["137"],
    "34-0040": ["137"], "35-0010": ["137"], "35-0020": ["148"], "35-0030": ["137"], "35-0040": ["137"], "35-0050": ["137"],
    "35-0060": ["137"]}


MOF_NAME = {"105": "農林水産", "106": "鉱業", "107": "建設", "109": "食料品", "110": "繊維", "111": "衣服", "112": "木材", "113": "パルプ・紙",
            "114": "印刷", "115": "化学", "116": "石油・石炭", "117": "窯業・土石", "118": "鉄鋼", "119": "非鉄", "120": "金属製品",
            "121": "生産用機械", "122": "電気機械", "123": "自動車", "124": "業務用機械", "125": "その他輸送機械", "126": "その他製造",
            "127": "卸売", "128": "小売", "130": "不動産", "131": "陸運", "132": "水運", "133": "その他運輸", "135": "電気", "136": "ガス・水道",
            "137": "サービス", "138": "広告", "139": "宿泊", "140": "生活関連", "141": "娯楽", "142": "情報通信", "145": "情報通信機械",
            "148": "飲食", "149": "物品賃貸", "154": "はん用機械", "163": "繊維（旧）"}


def group_name(codes: list[str]) -> str:
    return "+".join(codes)


def group_label(g: str, names: dict | None = None) -> str:
    """"121+154" → 「生産用機械 + はん用機械」（「繊維（旧）/ 衣服」这类改版前的码不显示）。"""
    nm = names or MOF_NAME
    parts = [nm.get(c, c) for c in str(g).split("+") if c not in ("111", "163")]
    return " + ".join(parts) if parts else str(g)


# ───────────────────────── 取数（e-Stat 网页的「表ダウンロード」，不要 appId）─────────────────────────
def _gz(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode()


def _download(sid: str, want: dict[int, set[str]], timeout: int = 600) -> bytes:
    """e-Stat DB 的一部分（按 matterId 选代码；没列的 = 全部）→ CSV 字节。复现网页的 api_get_model → api_get_result →
    api_download_create → api_download_run（非公开接口）。"""
    from curl_cffi import requests as cr
    base = "https://www.e-stat.go.jp/"
    S = cr.Session(impersonate="chrome")
    S.get(f"{base}dbview?sid={sid}", timeout=60).raise_for_status()
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}dbview?sid={sid}",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    m = S.post(f"{base}dbview/api_get_model?sid={sid}", data="", headers=hdr, timeout=120).json()
    rows, cols, tops, view_tops = [], [], [], []
    tot_top, tot_col, cells = 1, 1, 1
    for mt in m["matters"].values():
        mid = mt["matterId"]
        entries = list(mt["listData"].values())
        chosen = [e for e in entries if (mid not in want or e["code"] in want[mid])]
        h = {"matterId": mid, "tableName": mt["tableName"], "dispTableName": mt["dispTableName"], "positionNum": mt["positionNum"],
             "matterName": mt["matterName"], "initDisp": mt["initDisp"], "listData": [], "allListData": [],
             "allSelected": 1 if len(chosen) == len(entries) else 0, "allDataSelected": 1 if len(chosen) == len(entries) else 0}
        cells *= len(chosen)
        if mt["position"] in ("row", "col"):
            h["listData"] = [{"name": e["name"], "code": e["code"], "unit": e.get("unitName")} for e in chosen]
            (rows if mt["position"] == "row" else cols).append(h)
            tot_col *= len(chosen) if mt["position"] == "col" else 1
        else:
            h["listData"] = [{"name": chosen[0]["name"], "code": chosen[0]["code"]}]
            h["allListData"] = [{"name": e["name"], "code": e["code"], "unit": e.get("unitName")} for e in chosen]
            tops.append(h)
            if mt["initDisp"] != 0:
                view_tops.append(h)
                tot_top *= len(chosen)

    def slim(h):
        return {"matterId": h["matterId"], "tableName": h["tableName"], "dispTableName": h["dispTableName"],
                "positionNum": h["positionNum"], "listData": [dict(x, explanation="") for x in h["listData"]], "allSelected": h["allSelected"]}
    c = {"rows": _gz([slim(h) for h in rows]), "cols": _gz([slim(h) for h in cols]), "tops": _gz([slim(h) for h in tops]),
         "apiTops": _gz([dict(slim(h), listData=[dict(x, explanation="") for x in h["allListData"]]) for h in tops]),
         "annotationFlg": m.get("annotationFlg", "0"), "rowNoDataDispFlg": m.get("rowNoDataDispFlg", "0"),
         "colNoDataDispFlg": m.get("colNoDataDispFlg", "0"), "commaType": m.get("commaType", "0"), "replaceSpChars": m.get("replaceSpChars", "0"),
         "graphAxis": m.get("graphAxis") or "", "graphBasis": m.get("graphBasis") or "", "graphSort": m.get("graphSort") or "",
         "graphTitle": m.get("graphTitle") or "", "graphType": m.get("graphType") or "", "inputNumberOfCols": m.get("inputNumberOfCols"),
         "inputNumberOfRows": m.get("inputNumberOfRows"), "movementId": 0, "leftMoveFlg": m.get("leftMoveFlg"), "rightMoveFlg": m.get("rightMoveFlg"),
         "underMoveFlg": m.get("underMoveFlg"), "upMoveFlg": m.get("upMoveFlg"), "currentCols": "", "currentRows": "", "mode": "table", "layoutName": ""}
    S.post(f"{base}dbview/api_get_result?sid={sid}", data=urllib.parse.urlencode(c), headers=hdr, timeout=300)
    data = {"rows": _gz(rows), "cols": _gz(cols), "tops": _gz(tops), "viewTops": _gz(view_tops), "topsAll": _gz(tops),
            "annotationFlg": "0", "rowNoDataDispFlg": "1", "colNoDataDispFlg": "1", "commaType": m.get("commaType", "0"),
            "replaceSpChars": m.get("replaceSpChars", "0"), "downloadRange": "0", "fileFormat": "0", "charset": "UTF-8", "bom": "0",
            "titleDispFlg": "1", "codeDispFlg": "1", "auxiliaryCodeDispFlg": "1", "legendDispFlg": m.get("legend_value", "0"),
            "levelCodeDispFlg": m.get("level_code_value", "0"), "totalCellSelected": str(tot_top), "totalCellSelectedCount": str(cells),
            "totalCellCount": str(cells), "totalColSelected": str(tot_col), "title": "dl", "statCode": "", "startNumber": "1",
            "totalNum": "", "toNum": ""}
    parts, n = [], 1
    while True:
        data["startNumber"] = str(n)
        res = S.post(f"{base}dbview/api_download_create?sid={sid}", data=urllib.parse.urlencode(data), headers=hdr, timeout=timeout).json()
        first = res[0] if isinstance(res, list) and res else res
        if not first or "fileList" not in first:
            raise RuntimeError(f"e-Stat 下载失败：{str(res)[:300]}")
        fl = first["fileList"][0]
        run = S.post(f"{base}dbview/api_download_run?sid={sid}", headers=hdr, timeout=timeout,
                     data=urllib.parse.urlencode({"index": fl["fileNo"], "path1": first["filePath"], "name1": fl["fileName"]}))
        run.raise_for_status()
        parts.append(run.content)
        if n == 1 and first.get("totalNum") is not None:
            data["totalNum"], data["toNum"] = str(first.get("totalNum")), str(first.get("toNum"))
        if not first.get("remainNumber"):
            break
        n += 1
        time.sleep(1)
    return b"".join(parts)


def parse_estat_csv(raw: bytes) -> pd.DataFrame:
    """e-Stat 的 CSV（前面是标题 / 凡例，然后「項目コード」行、表头行、数据；数字带千分位，*** = 没有）→
    长表 size / ind / q（年期码，西历年 × 10 + 季号）/ item / value（百万円）。可能是几个文件接在一起。"""
    out = []
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    k = 0
    while k < len(lines):
        if lines[k].startswith('"","') and "コード" in lines[k] and "/調査項目" in lines[k]:
            codes = next(csv.reader([lines[k]]))
            j = k + 1
            while j < len(lines) and not lines[j].startswith('"規模'):
                j += 1
            if j >= len(lines):
                break
            hdr = next(csv.reader([lines[j]]))
            item_cols = {i: codes[i] for i in range(len(hdr)) if i < len(codes) and codes[i] and codes[i][:1].isdigit()}
            j += 1
            while j < len(lines) and lines[j].startswith('"') and not lines[j].startswith('"統計名'):
                r = next(csv.reader([lines[j]]))
                if len(r) >= len(hdr) and r[0].strip().isdigit():
                    for i, it in item_cols.items():
                        v = r[i].replace(",", "").strip()
                        if v and v not in ("***", "*", "-", "…"):
                            try:
                                out.append((r[0], r[3], int(r[6]), it, float(v)))
                            except ValueError:
                                pass
                j += 1
            k = j
        else:
            k += 1
    return pd.DataFrame(out, columns=["size", "ind", "q", "item", "value"])


def fetch_mof(refresh: bool = False) -> pd.DataFrame:
    """设备投资（040 / 225）× 全部业种 × 規模 25 → var/cache/mof/ssc_capex_q.csv（原表不入库）。"""
    fp = paths.sub("cache") / "mof" / MOF_FILE
    if fp.exists() and not refresh:
        return pd.read_csv(fp, dtype={"size": str, "ind": str, "item": str})
    fp.parent.mkdir(parents=True, exist_ok=True)
    raw = _download_by_name()                                               # matterId 按维度名找（接口的编号不保证固定）
    df = parse_estat_csv(raw)
    df.to_csv(fp, index=False)
    return df


def _download_by_name() -> bytes:
    """按维度名找 matterId（調査項目 / 規模），只取 040 / 225 与規模 25。"""
    from curl_cffi import requests as cr
    base = "https://www.e-stat.go.jp/"
    S = cr.Session(impersonate="chrome")
    S.get(f"{base}dbview?sid={SID}", timeout=60).raise_for_status()
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}dbview?sid={SID}",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    m = S.post(f"{base}dbview/api_get_model?sid={SID}", data="", headers=hdr, timeout=120).json()
    want = {}
    for mt in m["matters"].values():
        name = str(mt.get("matterName") or "")
        if "調査項目" in name:
            want[mt["matterId"]] = set(ITEMS)
        elif "規模" in name:
            want[mt["matterId"]] = {SIZE}
    if len(want) != 2:
        raise RuntimeError(f"e-Stat 维度名对不上：{[mt.get('matterName') for mt in m['matters'].values()]}")
    return _download(SID, want)


# ───────────────────────── 季度 → 月末可用 ─────────────────────────
def q_period(q: int) -> pd.Period:
    """年期码（西历年 × 10 + 季号，1 = 1〜3 月）→ 季度。"""
    return pd.Period(year=int(q) // 10, quarter=int(q) % 10, freq="Q")


def avail_month_end(p: pd.Period) -> pd.Timestamp:
    """这个季度的数字从哪个月末起可以用：季末那个月 + 3 个月（公布在 + 3 个月的第 1 个工作日）；2020Q1 确报 7-27 → + 4。"""
    add = 4 if (p.year, p.quarter) == (2020, 1) else 3
    return (p.asfreq("M", "end") + add).to_timestamp(how="end").normalize()


def capex_table(df: pd.DataFrame, item: str = "040") -> pd.DataFrame:
    """长表 → 季度 × MOF 业种码 的设备投资（百万円）。"""
    x = df[(df["size"].astype(str) == SIZE) & (df["item"].astype(str) == item)]
    t = x.pivot_table(index="q", columns="ind", values="value", aggfunc="sum")
    t.index = pd.PeriodIndex([q_period(q) for q in t.index], freq="Q")
    t.columns = [str(c) for c in t.columns]
    return t.sort_index()


def groups(t: pd.DataFrame, gmap: dict[str, list[str]]) -> pd.DataFrame:
    """几个 MOF 业种码加总成一组（缺的码当 0；一个都没有 → NaN）。"""
    out = {}
    for g, codes in gmap.items():
        cs = [c for c in codes if c in t.columns]
        out[g] = t[cs].sum(axis=1, min_count=1) if cs else pd.Series(np.nan, index=t.index)
    return pd.DataFrame(out, index=t.index)


def trailing4(t: pd.DataFrame) -> pd.DataFrame:
    return t.rolling(4, min_periods=4).sum()


def self_signal(G: pd.DataFrame, total: pd.Series) -> pd.DataFrame:
    """占比的趋势：log(4 季合计的占比 ÷ 一年前的占比) × 100（%）。"""
    share = trailing4(G).div(trailing4(total.to_frame()).iloc[:, 0], axis=0)
    share = share.where(share > 0)
    return np.log(share / share.shift(4)) * 100


def growth(G: pd.DataFrame) -> pd.DataFrame:
    """投资额的增速：log(4 季合计 ÷ 一年前的 4 季合计) × 100（%）。"""
    s = trailing4(G).where(lambda v: v > 0)
    return np.log(s / s.shift(4)) * 100


def to_months(Q: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """季度信号 → 月末面板：每个月末用「那时已经公布」的最新一季（avail_month_end ≤ 月末）。"""
    if not len(Q):
        return pd.DataFrame(index=months)
    Qa = Q.copy()
    Qa.index = pd.DatetimeIndex([avail_month_end(p) for p in Q.index])
    Qa = Qa[~Qa.index.duplicated(keep="last")].sort_index()
    return Qa.reindex(Qa.index.union(months)).ffill().reindex(months)


# ───────────────────────── 固定資本マトリックス × 产业连关表 → 谁的投资带来谁的产出 ─────────────────────────
def load_fcm(refresh: bool = False) -> pd.DataFrame:
    """2020 年 固定資本マトリックス（民間）：资本财（108 部门码 = 7 位码的前 3 位，加总）× 投资部门（列码）。"""
    fp = paths.sub("cache") / "io" / FCM_FILE
    if not fp.exists() or refresh:
        import urllib.request
        fp.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(FCM_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:                          # noqa: S310
            fp.write_bytes(r.read())
    df = pd.read_excel(fp, header=None)
    hdr_r = next(i for i in range(10) if str(df.iloc[i, 1]).startswith("資本形成部門コード"))
    cols = [str(v).strip() for v in df.iloc[hdr_r, 2:].tolist()]
    body = df.iloc[hdr_r + 2:, :]
    body = body[body.iloc[:, 0].astype(str).str.match(r"^\d{4}-\d{3}$")]
    code3 = body.iloc[:, 0].astype(str).str[:3]
    vals = body.iloc[:, 2:].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    vals.columns = cols
    vals.index = code3.values
    return vals.groupby(level=0).sum()


def fcm_leaf_columns(F: pd.DataFrame) -> dict[str, list[str]]:
    """FCM_MOF 的键（2 位 = 那一组的全部叶列；列码 = 那一列）→ 实际的列码（不含「-0000」合计列与「うち」列）。"""
    leaf = [c for c in F.columns if not c.endswith("-0000") and c != "00-0000"]
    parent_of_uchi = {c for c in leaf if c[-1] != "0" and c[:-1] + "0" in F.columns}         # 「うち」列（例 22-0011）是上一列的一部分
    leaf = [c for c in leaf if c not in parent_of_uchi]
    out = {}
    for k in FCM_MOF:
        out[k] = [c for c in leaf if (c == k if "-" in k else c[:2] == k)]
    return out


def induced(F: pd.DataFrame, x: pd.DataFrame, X: pd.Series, imports: pd.Series, dom_demand: pd.Series,
            f_unit: float = 1e-3) -> pd.DataFrame:
    """每个投资部门列的资本财需求 f → 国内诱发产出 = [I − (I − M)A]^−1 (I − M) f（竞争输入型，M = 进口 ÷ 国内需要）。返回 108 部门 × 列。
    单位：产业连关表 10 億円、固定資本マトリックス 百万円 → f × f_unit（缺省 1e-3）换成 10 億円。"""
    codes = list(x.index)
    A = (x / X.replace(0, np.nan)).fillna(0.0).to_numpy(float)
    m = (imports.reindex(codes).abs() / dom_demand.reindex(codes).replace(0, np.nan)).fillna(0.0).clip(0, 1).to_numpy(float)
    IM = np.diag(1 - m)
    L = np.linalg.inv(np.eye(len(codes)) - IM @ A)
    f = F.reindex(codes).fillna(0.0).to_numpy(float) * f_unit
    return pd.DataFrame(L @ IM @ f, index=codes, columns=F.columns)


def exposures(Xi: pd.DataFrame, X: pd.Series, tse_of, groups_cols: dict[str, list[str]], industries: list[str]) -> dict:
    """{"e": {东証业种: {投资组: 诱发产出 ÷ 国内生产额}}, "cover": 覆盖的投资额比例}。投资组 = FCM_MOF 的 MOF 码组。"""
    by_tse: dict[str, list[str]] = {}
    for c in Xi.index:
        for t in tse_of(c):
            by_tse.setdefault(t, []).append(c)
    gcols: dict[str, list[str]] = {}
    for k, cols in groups_cols.items():
        gcols.setdefault(group_name(FCM_MOF[k]), []).extend(cols)
    e = {}
    for j in industries:
        J = by_tse.get(j, [])
        if not J:
            continue
        xj = float(X[J].sum())
        if xj <= 0:
            continue
        e[j] = {g: round(float(Xi.loc[J, cols].to_numpy(float).sum()) / xj, 6) for g, cols in gcols.items() if cols}
    return e


def demand_signal(e: dict, g: pd.DataFrame) -> pd.DataFrame:
    """DEM_j = Σ_组 e[j][组] × 该组投资额增速（%）→ j 的国内产出因投资变化预期变动的百分比。g 的列 = 投资组名。"""
    out = {}
    for j, w in e.items():
        cols = [c for c in w if c in g.columns]
        if cols:
            out[j] = sum(w[c] * g[c] for c in cols)
    return pd.DataFrame(out, index=g.index)


# ───────────────────────── 日报的季度快照（㉟，2026-09-29 用户确认；只展示，不改交易）─────────────────────────
SNAP_FILE = "invest_flow_snapshot.json"
STUDY_NOTE = ("研究（登记 5db014b，var/out/invest_flow_study.md）：占比趋势（T1）、投资的钱流向（T2）预测不了之后 3 个月的行业收益，"
              "美国复现（T3）也不成立；投资带动的原材料价格多在同一季度就一起动 → 只作背景")


def q_label(p: pd.Period) -> str:
    return f"{p.year}Q{p.quarter}"


def due_quarter(asof) -> pd.Period:
    """asof 那天「已经可以用」的最新一季（avail_month_end ≤ asof；与研究同一口径：季末那个月 + 3 个月的月末）。"""
    d = pd.Timestamp(asof).normalize()
    p = pd.Period(d, freq="Q")
    while avail_month_end(p) > d:
        p -= 1
    return p


def snapshot(raw: pd.DataFrame, e: dict, asof, top: int = 5, min_share: float = 1.0) -> dict:
    """最新一季（asof 时已可用）的：占比上升 / 下降最多的业种（4 季合计占比 vs 一年前；占比 < min_share% 的小业种波动大，不排）、
    投资额增速、投资的钱流向（DEM：设备投资的变化带来的国内产出变化 %，只列正 / 负）。"""
    capex = capex_table(raw, "040")
    capex = capex[[avail_month_end(p) <= pd.Timestamp(asof).normalize() for p in capex.index]]
    total = capex[TOTAL]
    G = groups(capex, MOF_TSE)
    SQ, gG = self_signal(G, total), growth(G)
    share = trailing4(G).div(trailing4(total.to_frame()).iloc[:, 0], axis=0) * 100
    GD = groups(capex, {group_name(c): c for c in FCM_MOF.values()})
    DEM = demand_signal(e or {}, growth(GD))
    ok = SQ.dropna(how="all")
    if not len(ok):
        raise ValueError("没有可用的季度")
    q = ok.index[-1]

    def rows(s: pd.Series, asc: bool, extra=None) -> list[dict]:
        s = s.dropna().sort_values(ascending=asc).head(top)
        return [{"industry": j, "v": round(float(v), 1), **(extra(j) if extra else {})} for j, v in s.items()]
    big = SQ.loc[q][share.loc[q] >= min_share]

    def self_extra(j):
        return {"share": round(float(share.loc[q, j]), 1), "growth": None if pd.isna(gG.loc[q, j]) else round(float(gG.loc[q, j]), 1)}
    dem = DEM.loc[q] if q in DEM.index else pd.Series(dtype=float)
    tg = growth(total.to_frame("t"))["t"]
    return {"quarter": q_label(q), "period": f"{q.year} 年 {q.quarter * 3 - 2}〜{q.quarter * 3} 月期",
            "avail": avail_month_end(q).date().isoformat(), "asof": str(pd.Timestamp(asof).date()),
            "total_growth": None if pd.isna(tg.get(q)) else round(float(tg[q]), 1),
            "share_up": rows(big[big > 0], False, self_extra), "share_down": rows(big[big < 0], True, self_extra),
            "flow_up": rows(dem[dem >= 0.05], False), "flow_down": rows(dem[dem <= -0.05], True),
            "n_ind": int(SQ.loc[q].notna().sum()), "n_small": int((share.loc[q] < min_share).sum()), "min_share": min_share,
            "source": "財務省 法人企業統計調査 季報（資本金 10 億円以上、原数值；e-Stat 0003060191）+ 2020 年 固定資本マトリックス（var/invest_fcm_2020.json）",
            "note": STUDY_NOTE}


def refresh_snapshot(asof, fetch=None) -> dict:
    """日报用：已存的快照不是最新可用的一季才去 e-Stat 取数（每季一次；取不到就留着旧的并写原因）。只存导出的数字。"""
    fp = paths.home() / SNAP_FILE
    old = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None
    want = q_label(due_quarter(asof))
    if old and old.get("quarter") == want and not old.get("error"):
        return old
    try:
        raw = (fetch or (lambda: fetch_mof(refresh=True)))()
        e = (json.loads((paths.home() / "invest_fcm_2020.json").read_text(encoding="utf-8")) or {}).get("e") or {}
        snap = snapshot(raw, e, asof)
    except Exception as ex:                                              # noqa: BLE001
        msg = f"{type(ex).__name__}: {ex}"[:200]
        if old:
            return {**old, "stale": f"{want} 还没取到（{msg}）；显示的是 {old.get('quarter')}"}
        return {"error": msg, "want": want}
    if snap["quarter"] != want:
        snap["stale"] = f"e-Stat 还没有 {want}（按公布日程应该已有）；显示的是 {snap['quarter']}"
    fp.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return snap
