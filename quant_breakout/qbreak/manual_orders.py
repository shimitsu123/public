"""manual_orders.py — 手动指令：页面（qbreak/panel.py）或命令行（run.py manual）上点「卖出 / 调仓 / 买入 / 闲置资金比例」，
执行器（qbreak/live_unified.py）下单。页面只把指令追加到数据目录的 manual/requests_<账本>.jsonl；下单的永远是执行器，
闸门与平时相同（HALT / ARM / 持仓核对 / 单笔上限 / 资格检查），所以手动操作不会让第二天的持仓核对停下。

指令（kind）：
  sell     卖出一只个股的全部；之后 block_days 个交易日不自动买回（默认 20；0 = 不限制；-1 = 一直，直到 unblock）
  trim     把一只个股减到总权益的 pct %（命令行用；只能减）
  adjust   调仓（unit = shares 股数 / yen 金额 / pct 占总权益 %，value = 目标；单元向下取整）：少于现在 → 卖出多的部分；
           多于现在 → 加仓（只加已经持有的票；单只最多占总权益 34%；资格检查 / 立花能不能买 / 不买回 / 决算前 / 新仓倍数 0 的不加；
           只做一次）。加仓后成本按股数加权平均，止损 / 峰值 / 持有天数不变。
  buy      买入一只还没拿的个股（unit = rule 按规则的仓位〔默认〕/ shares / yen / pct）：与规则的新仓同一套闸门
           （占名额〔最多 4 只〕、不能买核心 ETF、最多到总权益、资格检查 / 立花能不能买 / 不买回 / 决算前 / 新仓倍数 0）；只做一次；
           买入后与规则的持仓一样（止损按 ATR、规则离场）。fund = split：钱不够从持仓平摊凑（同批写的 adjust 带 fund_for）；
           fund = all（2026-10-13）：其他持仓全部卖出、只拿这只 + 现金（同批：个股 adjust → 0、corefix clear、core pct=0，带 fund_for）：整批只在早上的决策里做
           （同批的比例 / 固定口数读到时只是 pending，那次决策先过 _allin_gate 再 _allin_apply_core 生效；被挡 → _allin_abort 整批作废；盘中 / 补单窗口 → 整批 hold）；
           股数 = 总权益上限再按钱截；撤回 / 撤销撤回同批一起：cancel_plan / cancel_request / uncancel_request（同批卖单已在交易所 → 拒绝）。
  core     闲置资金（核心 ETF）比例：规则的目标额 × pct %（100 = 照规则；0 = 留现金）。从下一次决策起一直有效
  corefix  核心 ETF 固定口数（units）/ 恢复按规则（clear）。什么时候下单与买卖同一个时段口径（D1；2026-10-15 用户「盘中下的单应该是
           进行实时成交的」）：盘中写的 → 马上（--phase now 的 fix_moves，按现价限价）；早上的决策之后、开盘前 / 午休写的 → 09:00 / 12:30
           开盘后第一次盘中运行马上（不是寄付）；早上的决策之前写的 → 那次决策读到；15:25 之后 / 休市日 → 下一次决策（corefix_fill）
  unblock  解除「不自动买回」（2026-10-13：读到时只记 lift_from = 写的时刻之后第一次 07:40 决策的成交日，那次决策起才不挡；
           不会买回、也不马上买；block_id = 页面看到的那个设定，设定换了 / 解除了就不动）
  cancel   撤回一条还没下的指令（target = 指令 id）；已经发到交易所的单用 cancel_order 撤
  cancel_order  撤单：撤执行器今天已经发到交易所、还挂着的一笔单（cid = 执行器的单号；面板「今天要成交的单」的「撤单」）→ 面板马上叫
           执行器（--phase cancel；qbreak/live_ops.py）；已经成交的部分撤不了；撤掉的卖单如果规则明天还要卖会再下
「赢家加仓」研究没有通过、没触发信号的票没有回测验证：加仓 / 买入都是用户自己的决定，会让账户和云端模拟盘不一致。

什么时候下单（2026-10-07 用户：「当天买入卖出的话在交易时间段就直接进行买入卖出 在交易时间之前的话就等交易时间的时候进行交易」）：
  盘中（09:00〜11:30、12:30〜15:25）点的 → 马上下单：面板叫执行器跑 --phase now（约 1〜3 分钟）；限价单按现价，
      买入的限价不超过决策日收盘 ×1.03（与寄付相同）；钱不够先卖核心 ETF（今天开盘有单的不动）。
  开盘前点的 → 今天开盘：07:40 的运行之前 → 那次运行一起下寄付单；之后、08:55 之前的卖出 → 重试加进今天的寄付单；
      其余 → 09:00 开盘后马上下（--phase now）。午休（11:30〜12:30）点的 → 12:30 后场开盘后。
  收盘后（15:25 起）/ 休市日点的 → 下一个交易日早上的运行（开盘的寄付单）。
  今天开盘已经有执行器的单的票（规则 / 手动），盘中不再下第二笔 → 明天早上的运行处理（明天开盘）。
状态：pending 等下单 → placed 已下单（盘中的单当场成交或挂着）→ done 完成（第二天早上对账时记进账本）；
      rejected 没执行（理由）/ cancelled 已撤回 / superseded 规则也要卖（按规则的单）。
给人看的文字里的票一律「代码 名字」（qbreak/names.label：「7203 トヨタ自動車」「1482 对冲版美国 7〜10 年国债」；2026-10-15 用户：只写代码不知道是哪只）：
  describe / 拒绝的理由 / 执行器写进指令记录的 msg / 事件行都用它；指令 id、cid（U2026-10-14-SELL-1545.T）、要复制的命令、
  数据字段（ticker、fund_holdings 的 t、fund_all 的 also…）照旧只写代码。以前存下的 msg 显示时（msg_text）过 names.annotate 补名字。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re

from . import names, paths
from .calendar_jp import JST, is_trading_day, next_trading_day, now_jst, prev_trading_day

KINDS = ("sell", "trim", "adjust", "buy", "core", "corefix", "unblock", "cancel", "cancel_order", "uncancel")
POS_KINDS = ("sell", "trim", "adjust")  # 针对一只持仓的指令
ORDER_KINDS = POS_KINDS + ("buy",)      # 会变成单的指令（同一只票同时只能有一条没处理完的）
UNITS = {"shares": "股", "yen": "円", "pct": "%"}
BUY_UNITS = {"rule": "按规则的仓位", **UNITS}
BLOCK_DEFAULT = 20                      # 手动卖出后多少个交易日不自动买回（默认）
BLOCK_WHERE = "「交易」→ 点开最下面的「已结束 / 不是今天的」→「手动卖出后不自动买回」"   # 「解除」/「恢复按规则」在哪（复核 7，2026-10-16：收起来了）
BLOCK_MAX = 250
MANUAL_CAP_PCT = 100.0                  # 手动买入 / 加仓的上限（2026-10-12 用户：「不要设上限」→ 最多到总权益；钱不够从持仓平摊凑）。规则的新仓仍按 max_position_pct
CAP_PCT = 34.0                          # 加仓上限：单只个股占总权益 %（执行器写进账本的 manual.cap_pct = 引擎的 max_position_pct；没有就用这个）
MAX_POS = 4                             # 个股名额（执行器写进账本的 manual.max_positions = 引擎的 max_positions；没有就用这个）
LOT = 100                               # 页面 / 命令行估算用的单元（东证个股 100 股；执行器按引擎的单元）
CUTOFF = dt.time(8, 55)                 # 寄付注文的最后时刻（与 live_unified.MORNING_CUTOFF 相同）
SESSION = ((dt.time(9, 0), dt.time(11, 30)), (dt.time(12, 30), dt.time(15, 25)))   # 盘中马上下单的时间（前場 / 後場；15:25 起是收盘竞价）
RETRY_S = 600                           # 盘中没下成的指令（取不到现价等）：过多久再试
LABEL = {"sell": "卖出全部", "trim": "减仓", "adjust": "调仓", "buy": "买入", "core": "闲置资金比例", "corefix": "固定 ETF 口数", "unblock": "解除不买回",
         "cancel": "撤回指令", "cancel_order": "撤单", "uncancel": "撤销撤回"}
CANCEL_UNTIL = dt.time(15, 30)          # 撤单：交易日这个时刻之前面板马上叫执行器（之后今天没成交的单都已失效）
GROUP_MAX = 12                          # 整组撤单（2026-10-16 用户：一起下的买单和卖单一起撤）：一组最多几笔（超过 → 一笔笔撤）
GROUP_RECHECK_S = 60                    # 整组撤单：买单的撤单立花还没确认 → 卖单先不撤，过这么多秒再查一次
GROUP_WAIT_MAX_S = 600                  # 整组撤单：最多等这么久（按时间，不按次数）→ 之后卖单不撤、请你在立花网站看
GROUP_LAST_S = 180                      # 整组撤单：收盘（15:30）前这么多秒起不再等（面板 15:30 之后不再叫撤单的运行：等到收盘之后就没人收尾；复核 2026-10-16）
RUN_AT = dt.time(7, 40)                 # 早上决策的运行时刻（与 mac_login.RUN_AFTER / launchd 的 07:40 相同）：解除不买回从这之后第一次决策起生效
NEXT_DECISION = "下一次决策（交易日 07:40）起生效"   # 不知道现在几点时的写法；知道 → next_decision(now)「下一次决策（10/19 07:40）起生效」
UNK_LATER = "先登记那笔状态不明的单（见通知），登记之后的下一次决策处理"   # 盘中前面有一笔下单结果不明 → 剩下的指令（执行器 now_phase；登记之前执行器一次都不跑，不是「明天开盘」；2026-10-14 复核）
UNK_LATER_BUY = ("先登记那笔状态不明的单（见通知）；登记之后：买到的部分照记，没买到 → 这条指令结束（只做一次）")   # 已下单的手动买入 / 加仓，
#                                         它的单状态不明：登记 0 股 → 对账时指令结束（只做一次），不是「下一次决策处理」（面板「交易」；复核 4，2026-10-16）
HALT_WAIT_MSG = "HALT 中：解除后照原样执行"   # HALT 期间等着的手动指令的说明（2026-10-13：以前一直写「等执行器下单」）
HALT_DONE_MSG = "HALT 已解除 → 照原样执行"
# HALT 期间读到的闲置资金比例 / 固定口数（读到就生效；2026-10-14）。D1 之后不只等下一次决策：解除时还没照它排过单的，盘中面板马上叫执行器
# 按现价下（now_due / corefix_pending）—— 复核 UI F1（2026-10-16）：以前一律写「解除后下一次决策照它买卖 ETF」，盘中删 HALT 当场就下了单
HALT_CORE_AFTER = "盘中解除会马上按现价下单；开盘前 / 午休解除 → 开盘后马上；HALT 中的决策已经为它排过单（被挡下）的 / 收盘后解除 → 下一次决策"
HALT_CORE_MSG = f"HALT 中：解除后照它买卖 ETF（{HALT_CORE_AFTER}）"
HALT_CORE_DONE = f"HALT 已解除 → 照它买卖 ETF（{HALT_CORE_AFTER}）"
_CID = re.compile(r"^U(\d{4}-\d{2}-\d{2})-(BUY|SELL)-([0-9][0-9A-Z]{3}\.T)(-[0-9A-Za-z]{1,20})?$")
STATUS = {"pending": "等下单", "placed": "已下单", "done": "完成", "rejected": "没执行", "cancelled": "已撤回", "voided": "已撤销",
          "superseded": "按规则的单卖"}
REASON_TEXT = {"manual": "手动卖出", "manual_trim": "手动减仓", "manual_add": "手动加仓", "manual_buy": "手动买入",
               "manual_fund": "为手动买入先卖核心 ETF",
               "core_fix": "照你写的固定口数（盘中）", "fix_fund": "为固定口数先卖核心 ETF（盘中）"}   # D1（2026-10-15）：盘中照固定口数调的单
ACTIVE = ("pending", "placed")
KEEP_ITEMS = 200                        # 执行器账本里只留最近这么多条指令记录（Manual.settle；删掉的记进水位 manual.pruned，不会再被读成新指令）
_TICKER = re.compile(r"^[0-9][0-9A-Z]{3}\.T$")


def requests_path(tag: str):
    """指令文件（只追加）：<数据目录>/manual/requests_<账本标签>.jsonl —— 页面与命令行写，执行器读。"""
    return paths.sub("manual") / f"requests_{tag}.jsonl"


def normalize(req: dict) -> dict:
    """检查指令的格式（不看账本）：类型、代码、比例、天数。不合格 → ValueError（中文说明）。"""
    kind = str(req.get("kind") or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"不认识的指令 {kind!r}（可用：{'、'.join(KINDS)}）")
    out = {"kind": kind}
    if kind in ("sell", "trim", "adjust", "buy", "unblock"):
        t = str(req.get("ticker") or "").strip().upper()
        if t and "." not in t:
            t += ".T"
        if not _TICKER.match(t):
            raise ValueError(f"代码 {t or '—'} 不对（东证 4 位代码，例 7203 或 7203.T）")
        out["ticker"] = t
    if kind == "core" and req.get("ticker"):              # 持有的核心 ETF 的卖出 / 调仓（换算成比例；票与目标口数只用来显示）
        t = str(req.get("ticker") or "").strip().upper()
        if "." not in t:
            t += ".T"
        if not _TICKER.match(t):
            raise ValueError(f"代码 {t} 不对（东证 4 位代码，例 1545 或 1545.T）")
        out["ticker"] = t
        try:
            tg = int(req.get("target", 0))
        except (TypeError, ValueError):
            raise ValueError("目标口数要是整数") from None
        if not 0 <= tg <= 10_000_000:
            raise ValueError("目标口数要在 0〜10,000,000 之间")
        out["target"] = tg
    if kind == "corefix":                                 # 核心 ETF 固定口数（2026-10-11 用户：持仓里的纳指 ETF、对冲美债也要能买入）
        t = str(req.get("ticker") or "").strip().upper()
        if "." not in t:
            t += ".T"
        if not _TICKER.match(t):
            raise ValueError(f"代码 {t} 不对（东证 4 位代码，例 1545 或 1482.T）")
        out["ticker"] = t
        if req.get("clear"):
            out["clear"] = True
        else:
            try:
                u = int(req.get("units"))
            except (TypeError, ValueError):
                raise ValueError("要给口数（整数；0 = 固定不拿）") from None
            if not 0 <= u <= 10_000_000:
                raise ValueError("口数要在 0〜10,000,000 之间")
            out["units"] = u
            if req.get("from_kind") in ("sell", "trim", "adjust"):   # 固定口数的 ETF 上点的卖出全部 / 减仓 / 调仓换算来的（2026-10-13）
                out["from_kind"] = str(req["from_kind"])
    if kind in ("trim", "core"):
        try:
            pct = float(req.get("pct"))
        except (TypeError, ValueError):
            raise ValueError("要给比例（%）") from None
        if not math.isfinite(pct) or not 0 <= pct <= 100:
            raise ValueError("比例要在 0〜100% 之间")
        out["pct"] = round(pct, 2)
    if kind == "adjust" or kind == "buy":
        unit = str(req.get("unit") or ("rule" if kind == "buy" else "")).strip().lower()
        if unit not in (BUY_UNITS if kind == "buy" else UNITS):
            raise ValueError("调整要给单位：shares（股数）/ yen（金额 円）/ pct（占总权益 %）" if kind == "adjust" else
                             "买入的单位：rule（按规则的仓位，默认）/ shares（股数）/ yen（金额 円）/ pct（占总权益 %）")
        out["unit"] = unit
        if unit != "rule":
            out["value"] = _target_value(unit, req.get("value"), positive=kind == "buy")
    if kind == "sell":
        bd = req.get("block_days", BLOCK_DEFAULT)
        try:
            bd = int(bd)
        except (TypeError, ValueError):
            raise ValueError("不买回的天数要是整数（0 = 不限制，-1 = 一直）") from None
        if not -1 <= bd <= BLOCK_MAX:
            raise ValueError(f"不买回的天数要在 -1〜{BLOCK_MAX} 之间")
        out["block_days"] = bd
    if kind == "cancel_order":
        cid = str(req.get("cid") or "").strip()
        m = _CID.match(cid)
        if not m:
            raise ValueError("撤单要给执行器的单号（例 U2026-10-08-SELL-7203.T）")
        out["cid"], out["ticker"] = cid, m.group(3)
        dp = str(req.get("deps") or "").strip()            # 撤凑钱的卖单时，靠它的钱的买单：cancel = 一起撤 / keep = 只撤卖单（D2；2026-10-15）
        if dp:
            if dp not in ("cancel", "keep"):
                raise ValueError("deps 只能是 cancel（一起撤买单）或 keep（只撤卖单）")
            out["deps"] = dp
        g = req.get("grp")                                  # 整组撤单（2026-10-16）：同一组里你确认过的其他单（cid 列表；一次点击一条记录）
        if g is not None and g != "" and g != []:
            if not isinstance(g, list):
                raise ValueError("grp 要是 cid 的列表")
            if out.get("deps") != "cancel":
                raise ValueError("整组撤单（grp）要和 deps=cancel 一起写")
            gl = []
            for c in g:
                c = str(c or "").strip()
                mg = _CID.match(c)
                if not mg:
                    raise ValueError("同一组的单 " + c + " 不是执行器的单号")
                if mg.group(1) != m.group(1):
                    raise ValueError("同一组的单 " + c + " 不是同一天的决策")
                if c != cid and c not in gl:
                    gl.append(c)
            if len(gl) > GROUP_MAX - 1:
                raise ValueError("同一组最多 " + str(GROUP_MAX) + " 笔")
            if gl:
                out["grp"] = gl
    if kind == "unblock" and req.get("block_id"):           # 面板带上它看到的那个「不买回」设定的 id（2026-10-13）：设定换了 / 解除了 → 执行器不动新的
        bid = str(req.get("block_id") or "").strip()
        if not re.fullmatch(r"M[0-9A-Za-z_.\-]{1,80}", bid):
            raise ValueError("block_id 不对（「不买回」设定的 id，例 M20261006-081500-sell-7203）")
        out["block_id"] = bid
    if kind in ("cancel", "uncancel"):                    # uncancel（2026-10-12）：target = 那条撤回指令的 id
        tg = str(req.get("target") or "").strip()
        if not re.fullmatch(r"M[0-9A-Za-z_\-]{6,60}", tg):     # 撤单指令的 id 带下划线（…-cancel_order-1545；2026-10-16 事后：以前撤回不了）
            raise ValueError("撤回要给指令 id（例 M20261006-081500-sell-7203）")
        out["target"] = tg
    if kind in ("adjust", "buy", "corefix", "core", "sell"):   # 买入钱不够 → 从持仓平摊凑（2026-10-12）：买的那条记 fund，凑钱卖的那几条记 fund_for
        if str(req.get("fund") or "") in ("split", "all"):   # all（2026-10-13）：拖到最大 = 其他持仓全部卖出、只拿这只 + 现金
            out["fund"] = str(req["fund"])
        ff = str(req.get("fund_for") or "").strip().upper()
        if ff and _TICKER.match(ff):
            out["fund_for"] = ff
        if str(req.get("batch") or "") == "all":            # 「全部换成 X」的同批（与 split 的凑钱卖出区分；2026-10-13）
            out["batch"] = "all"
        for key in ("prev_pct", "prev_units"):              # 「其他全部卖出」写的比例 / 固定口数：原来的值（撤不了时说明）
            if req.get(key) is not None:
                try:
                    out[key] = round(float(req[key]), 2) if key == "prev_pct" else int(req[key])
                except (TypeError, ValueError):
                    pass
    if kind == "adjust":                                  # 写入时的方向（+1 加 / −1 减）与股数（2026-10-13）：执行时按新价格换算后方向反了 → 不执行
        try:
            d = int(req.get("dir") or 0)
            if d in (1, -1):
                out["dir"] = d
            if req.get("cur0") is not None and int(req["cur0"]) >= 0:
                out["cur0"] = int(req["cur0"])
        except (TypeError, ValueError):
            pass
    if kind == "buy" and out.get("fund") == "all":         # 「全部换成」原定哪天开盘做、写入时 X 的收盘（2026-10-13）：推迟执行时说明
        try:
            if req.get("allin_fill"):
                out["allin_fill"] = dt.date.fromisoformat(str(req["allin_fill"])[:10]).isoformat()
            xc = float(req.get("x_close") or 0)
            if math.isfinite(xc) and xc > 0:
                out["x_close"] = round(xc, 4)
        except (TypeError, ValueError):
            pass
    note = " ".join(str(req.get("note") or "").split())
    if note:
        out["note"] = note[:200]
    out["source"] = re.sub(r"[^0-9A-Za-z_\-]", "", str(req.get("source") or "cli"))[:20] or "cli"
    return out


def _target_value(unit: str, raw, positive: bool = False):
    """调整 / 买入的目标值：shares → 整数股；yen → 整数円；pct → 0〜100（两位小数）。positive：买入要 > 0。"""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError("要给目标值（股数 / 金额 円 / 占总权益 %）") from None
    if not math.isfinite(v) or v < 0:
        raise ValueError("目标值不能是负数")
    if positive and v <= 0:
        raise ValueError("买入的目标要大于 0（股数 / 金额 円 / 占总权益 %）")
    if unit == "shares":
        if v != int(v) or v > 10_000_000:
            raise ValueError("目标股数要是 0〜10,000,000 的整数")
        return int(v)
    if unit == "yen":
        if v > 1e10:
            raise ValueError("目标金额太大")
        return int(round(v))
    if v > 100:
        raise ValueError("比例要在 0〜100% 之间")
    return round(v, 2)


def append(tag: str, req: dict, clock=None) -> dict:
    """追加一条指令（先 normalize）；返回带 id / at 的记录。一行一条 JSON，O_APPEND 写入（同一台机器上多个写的人也不会互相覆盖）。"""
    rec = normalize(req)
    now = (clock or now_jst)()
    rec["at"] = now.isoformat(timespec="seconds")
    rec["id"] = f"M{now:%Y%m%d-%H%M%S}-{rec['kind']}" + (f"-{rec['ticker'].split('.')[0]}" if rec.get("ticker") else "")
    have = {r.get("id") for r in read_all(tag)}
    base, n = rec["id"], 2
    while rec["id"] in have:                                 # 同一秒的第二条
        rec["id"] = f"{base}-{n}"
        n += 1
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(requests_path(tag), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    return rec


def append_many(tag: str, reqs: list[dict], clock=None) -> list[dict]:
    """一次写几条指令（同一时刻、一次 os.write）：执行器不会只读到一半（「全部换成 X」整批 / 同批撤回；2026-10-13）。"""
    now = (clock or now_jst)()
    have = {r.get("id") for r in read_all(tag)}
    out, lines = [], []
    for req in reqs:
        rec = normalize(req)
        rec["at"] = now.isoformat(timespec="seconds")
        rec["id"] = f"M{now:%Y%m%d-%H%M%S}-{rec['kind']}" + (f"-{rec['ticker'].split('.')[0]}" if rec.get("ticker") else "")
        base, n = rec["id"], 2
        while rec["id"] in have:
            rec["id"] = f"{base}-{n}"
            n += 1
        have.add(rec["id"])
        out.append(rec)
        lines.append(json.dumps(rec, ensure_ascii=False) + "\n")
    if lines:
        fd = os.open(requests_path(tag), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, "".join(lines).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
    return out


def read_all(tag: str) -> list[dict]:
    """全部指令（按写入顺序）；坏行跳过。"""
    p = requests_path(tag)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("id") and r.get("kind") in KINDS:
            out.append(r)
    return out


PAPER_IDLE = "模拟账户的执行器没装：指令不会被执行；要在立花下单请选「立花」"


def paper_refuse(tag: str, agents=None) -> str | None:
    """往模拟账户写手动指令之前（面板 submit 与 run.py manual 同一个判断；2026-10-14 G13）：模拟账户的执行器
    （LaunchAgent com.qbreak.liveu.paper）没装、立花本番（com.qbreak.liveu.morning）装了 → 拒绝的原因（写了也没人执行，
    却以为下了单）；模拟账户装着 / 两个都没装（不在 Mac 上、只看）/ 立花的账本 → None（照旧）。只看 plist 在不在，不调 launchctl。
    agents：LaunchAgents 目录（默认 paths.launch_agents()，QBREAK_LAUNCH_AGENTS 可改；测试注入）。"""
    from pathlib import Path
    if not str(tag or "").startswith("paper"):
        return None
    ag = Path(agents) if agents is not None else paths.launch_agents()
    if (ag / f"{paths.PAPER_AGENT}.plist").exists() or not (ag / f"{paths.LIVE_AGENT}.plist").exists():
        return None
    return PAPER_IDLE


def is_pruned(r: dict, man: dict | None) -> bool:
    """指令文件里的这条是执行器整理账本时删掉的旧记录（Manual.settle 只留最近 KEEP_ITEMS 条；2026-10-14 G1）→ True。
    指令文件只追加、从不清理，以前按「id 不在账本里」判断新指令，删掉的旧记录会被当成新指令再读一次（几周前被拒的卖出全部又卖、
    最早的比例 0% 每次都读回来）。账本 manual.pruned 记水位：at = 删掉的记录里最晚的写入时刻、ids = 正好在这个时刻写的那几条；
    at 早于水位、或等于水位且 id 在 ids 里、又不在账本里的 = 删掉的。新写的指令时刻总晚于已经读过的（同一秒的看 ids），不会被挡。"""
    p = (man or {}).get("pruned") or {}
    mark = str(p.get("at") or "")
    if not mark or r.get("id") in ((man or {}).get("items") or {}):
        return False
    ra = str(r.get("at") or "")
    return ra < mark or (ra == mark and r.get("id") in set(p.get("ids") or ()))


def read_known(tag: str, book: dict | None) -> list[dict]:
    """指令文件里的指令，去掉执行器整理账本时删掉的旧记录（is_pruned）：判断「新 / 还没读 / 同批」都用它（2026-10-14 G1）。"""
    man = (book or {}).get("manual") or {}
    return [r for r in read_all(tag) if not is_pruned(r, man)]


def unseen(tag: str, book: dict | None) -> list[dict]:
    """指令文件里执行器还没读进账本的指令（页面显示「等执行器读」用）；整理账本时删掉的旧记录不算（2026-10-14 G1）。"""
    have = set(((book or {}).get("manual") or {}).get("items") or {})
    return [r for r in read_known(tag, book) if r["id"] not in have]


def add_trading_days(d: dt.date, n: int) -> dt.date:
    x = d
    for _ in range(max(0, int(n))):
        x = next_trading_day(x)
    return x


def lift_day(at, clock=None) -> dt.date:
    """「解除不买回」从哪天开盘成交的决策起不挡（2026-10-13）= 写的时刻（at，JST）之后第一次 07:40 决策的成交日：交易日 07:40 之前写的 → 当天；
    之后 / 休市日 → 下一个交易日。补跑的旧 K 线（成交日更早）照旧挡（解除不追溯）。at 读不了 → 按现在。"""
    try:
        w = dt.datetime.fromisoformat(str(at))
        w = w.astimezone(JST) if w.tzinfo else w
    except (TypeError, ValueError):
        w = (clock or now_jst)()
    d = w.date()
    return d if is_trading_day(d) and w.time() < RUN_AT else next_trading_day(d)


def rebuy_day(until) -> dt.date | None:
    """「不买回」到 until（K 线日）时，规则最早哪天开盘才可能买回：until 之后那根 K 线出信号 → 再下一个交易日开盘（= until + 2 个交易日）。"""
    if until is None:
        return None
    try:
        return add_trading_days(dt.date.fromisoformat(str(until)[:10]), 2)
    except ValueError:
        return None


def block_text(b: dict) -> str:
    """一个「不买回」设定的一句话（面板 / 日志）：到 10/28（最早 10/30 开盘才可能买回）/ 一直，直到解除 / 解除中（10/14 07:40 的决策起）。"""
    if (b or {}).get("lift_from"):
        return f"解除中（{str(b['lift_from'])[5:].replace('-', '/')} 07:40 的决策起不挡）"
    u = (b or {}).get("until")
    if u is None:
        return "一直，直到解除"
    r = rebuy_day(u)
    return f"到 {u}" + (f"（最早 {r:%m/%d} 开盘才可能买回）" if r else "")


def position_pct(state: dict) -> dict:
    """账本状态（dict）里每只个股占总权益的 %（按最近收盘 last_close；权益 = 历史最后一行）。"""
    hist = state.get("history") or []
    eq = float(hist[-1][1]) if hist else 0.0
    out = {}
    for t, p in (state.get("pos") or {}).items():
        px = float(p.get("last_close") or p.get("entry_px") or 0)
        out[t] = round(int(p.get("shares") or 0) * px / eq * 100, 2) if eq > 0 else None
    return out


def target_shares(unit: str, value, eq: float, px: float, lot: int = LOT) -> int:
    """调整的目标 → 股数（单元向下取整）：shares 直接用；yen = 金额 ÷ 价格；pct = 权益 × % ÷ 价格。"""
    v = float(value)
    if unit == "shares":
        raw = v
    elif px <= 0:
        return 0
    elif unit == "yen":
        raw = v / px
    else:
        raw = eq * v / 100 / px if eq > 0 else 0.0
    return max(0, int(math.floor(raw / lot + 1e-9)) * lot)


def fmt_target(r: dict) -> str:
    """调整 / 买入的目标值（带单位）：300 股 / ¥500,000 / 20% / 按规则的仓位。"""
    u, v = r.get("unit"), r.get("value")
    if u == "rule":
        return BUY_UNITS["rule"]
    if v is None:
        return "—"
    if u == "shares":
        return f"{int(v):,} 股"
    if u == "yen":
        return f"¥{float(v):,.0f}"
    return f"{float(v):g}%"


def mmdd(at) -> str:
    """ISO 时刻 / 日期 → MM/DD（读不了 → —）。"""
    s = str(at or "")
    return s[5:10].replace("-", "/") if len(s) >= 10 else "—"


def halt_text(it: dict) -> str:
    """HALT 期间等着的指令的说明（2026-10-13 resume-other-3）：解除后照原样执行 + 写于哪天。"""
    return f"{HALT_WAIT_MSG}（写于 {mmdd(it.get('at'))}）"


def halt_core(items, unread=(), dropped=()) -> list[dict]:
    """HALT 中改的闲置资金比例 / 固定口数（2026-10-14）：账本里标了 halt 的（HALT 中读到、已生效）+ 还没读的 core / corefix
    （「全部换成」的同批不算：跟着那条买入）；按写入时刻排。面板 HALT 卡片 / manual list 用。"""
    out = [it for it in items if it.get("halt") and it.get("kind") in ("core", "corefix")]
    out += [r for r in unread if r.get("kind") in ("core", "corefix") and not r.get("fund_for") and r.get("id") not in dropped]
    return sorted(out, key=lambda x: str(x.get("at") or ""))


def halt_core_line(todo: list[dict]) -> str:
    """HALT 中改的闲置资金比例 / 固定口数一条条写出来：id 说明 写于 MM/DD（2026-10-14）。"""
    return "；".join(f"{it['id']} {describe(it)} 写于 {mmdd(it.get('at'))}" for it in todo)


def describe(r: dict, lab=None) -> str:
    """一条指令的一句话：卖出全部 7203 トヨタ自動車 / 减仓 7203 トヨタ自動車 10% / 调仓 7203 トヨタ自動車 → 300 股 /
    买入 7203 トヨタ自動車（按规则的仓位）/ 闲置资金比例 80% / 撤单 1545 纳斯达克 100（U2026-10-14-SELL-1545.T）。
    lab：票 → 文字（默认 names.label =「代码 名字」，2026-10-15 用户：只写代码不知道是哪只）；只在拼票的地方用，cid 原样
    （以前面板 _named 对整句 str.replace，连 cid 也改坏）。要旧写法（「7203.T」）传 lab=str。"""
    lab = lab or names.label
    k = r.get("kind")
    if k == "cancel_order":
        head = f"撤单 {lab(r['ticker']) if r.get('ticker') else ''}（{r.get('cid') or '—'}）".replace("撤单 （", "撤单（")
        g = [str(c) for c in r.get("grp") or [] if c]
        if not g:
            return head
        parts = []
        for c in g:                                        # 整组撤单（2026-10-16）：同一组的其他单写成「买 1482 …」（代码带名字）
            mg = _CID.match(c)
            if mg:
                parts.append(("买" if mg.group(2) == "BUY" else "卖") + " " + lab(mg.group(3)))
            else:
                parts.append(c)
        return head + " + 同一组 " + str(len(g)) + " 笔（" + "、".join(parts) + "）"
    if k == "corefix":
        u = f"{int(r.get('units') or 0):,} 口"           # 名字可能以数字结尾（「1545 纳斯达克 100」）：默认写法隔一个「：」（names.qty；2026-10-15 复核）
        return (f"{lab(r['ticker'])} 恢复按规则" if r.get("clear")
                else f"固定 {names.qty(r['ticker'], u) if lab is names.label else lab(r['ticker']) + ' ' + u}（不按规则自动调）")
    if k == "core" and r.get("ticker"):
        tg = int(r.get("target") or 0)
        if tg <= 0:
            return f"卖出全部 {lab(r['ticker'])}（之后停买闲置资金 ETF）"
        return f"调仓 {lab(r['ticker'])} → 约 {tg:,} 口（闲置资金比例 {float(r['pct']):g}%）"
    if k == "buy" and r.get("fund") == "all":
        return f"全部换成这只 {lab(r['ticker'])}（其他全卖；股数由执行器按全卖之后的钱定）"
    s = LABEL.get(k, str(k)) + (f" {lab(r['ticker'])}" if r.get("ticker") else "")
    if k == "buy" and r.get("unit", "rule") == "rule":
        s += f"（{BUY_UNITS['rule']}）"
    elif k in ("adjust", "buy"):
        s += f" → {fmt_target(r)}"
    elif r.get("pct") is not None:
        s += f" {float(r['pct']):g}%"
    return s


def cap_text(cur: int, px: float, eq: float, cap_pct: float, lot: int = LOT) -> str:
    """加不了仓的理由（单只上限）：已经到上限，或者再加 1 个单元就超过上限。"""
    now = cur * px / eq * 100 if eq > 0 else 0.0
    if now >= cap_pct:
        return f"现在约占权益 {now:.1f}%，已经到单只上限 {cap_pct:g}%：不能再加"
    nxt = (cur + lot) * px / eq * 100 if eq > 0 else 0.0
    return f"现在约占权益 {now:.1f}%，再加 {lot:,} 股就约占 {nxt:.1f}%，超过单只上限 {cap_pct:g}%：不能再加"


def adjust_plan(rec: dict, state: dict, cap_pct: float = CAP_PCT, lot: int = LOT) -> dict:
    """按账本里的最近收盘与权益估算一条调整（页面 / 命令行的预览与检查；执行器下单前按决策时的收盘再算一次）：
    {"cur", "want"（目标换成的股数）, "target"（加仓时按上限截过）, "delta"（+ 买 / − 卖）, "px", "eq", "cur_pct", "new_pct",
     "capped"（被单只上限截了）, "cap_pct"}。"""
    pos = (state.get("pos") or {}).get(rec.get("ticker")) or {}
    hist = state.get("history") or []
    eq = float(hist[-1][1]) if hist else 0.0
    px = float(pos.get("last_close") or pos.get("entry_px") or 0)
    cur = int(pos.get("shares") or 0)
    want = target_shares(rec["unit"], rec["value"], eq, px, lot)
    tgt, capped = want, False
    if want > cur and eq > 0 and px > 0:
        cap = int(math.floor(eq * cap_pct / 100 / px / lot + 1e-9)) * lot
        if want > cap:
            tgt, capped = max(cap, cur), True
    pct = (lambda n: round(n * px / eq * 100, 2) if eq > 0 and px > 0 else None)
    return {"cur": cur, "want": want, "target": tgt, "delta": tgt - cur, "px": px, "eq": eq, "cur_pct": pct(cur),
            "new_pct": pct(tgt), "capped": capped, "cap_pct": cap_pct}


def adjust_flip_why(rec: dict, cur: int, want: int) -> str | None:
    """调仓执行前的方向检查（执行器两处同用；2026-10-13）：凑钱的卖出（fund_for）现在已经不高于目标 → 不卖（绝不改成买入）；
    写入时预览的方向（dir：+1 加 / −1 减）和现在按 ¥ / % 换算的方向相反 → 不执行。没问题 → None。"""
    if rec.get("fund_for") and want >= cur:
        return f"凑钱卖出：现在 {cur:,} 股已经不高于目标 {want:,} 股 → 不卖（不会改成买入）"
    d = int(rec.get("dir") or 0)
    if d and want != cur and (want > cur) != (d > 0):
        return f"价格变了：按 ¥ / % 换算后变成{'买入' if want > cur else '卖出'}，没执行，请重新调"
    return None


CASH_BUF_PCT = 1.0                      # 执行器的现金缓冲（config.cash_buffer_pct）：页面估算「现在能用的现金」用


def pre_reconcile(pj: dict | None, now: dt.datetime | None = None) -> bool:
    """现在写的指令会在对账之前执行吗（2026-10-16 复核）：成交日就是今天、而且现在是开盘前 / 盘中 / 午休（timing 不是 next）→ 执行器当天
    盘中按账本（还没对账）看持仓、同一只今天不再下第二笔（busy_today）。收盘后 / 周末 / 休市日写的 → 下一次决策执行，那时已经对过账
    （live_unified：先 _reconcile 再处理手动指令）。pj = live_ops.held_now 的结果；没有已知的成交 → False。"""
    now = now or now_jst()
    return bool((pj or {}).get("has")) and (pj or {}).get("fill_day") == now.date().isoformat() and timing(now)[0] != "next"


def fund_holdings(book: dict | None, tag: str | None = None, now: dt.datetime | None = None) -> dict:
    """「买入钱不够 → 从持仓平摊凑」用的数字（页面 CFG 与提交时的检查同一份）：
    {"cash": 现在能用的现金（(账本现金 − 立花的出金预留) × (1 − 缓冲)）, "reserve": 扣掉的出金预留,
     "hold": [{"t", "kind": stock / core, "cur", "px", "lot", "name"}],
     "busy": [还有没处理完的指令 / 规则在卖的票：不拿来凑]}。价格 = 账本里的最近收盘（估算）。
    name：名字（names.name；查不到 None）—— 买入 / 调仓框「从持仓凑钱」的预览行用（2026-10-15 用户：只写代码不知道是哪只）。
    持仓与现金按 live_ops.held_now（账本 + 今天已知的成交；2026-10-16）：凑钱的指令在下一次决策（对账之后）/ 盘中按交易所的现金执行，
    那时现金已含今天的成交（10/16：账本 ¥192 对 ¥10,020）；成交日当天开盘前 / 盘中 / 午休（pre_reconcile）有成交的票当天动不了（busy_today）
    → 放进 busy；收盘后 / 周末写的在对账之后的决策里执行 → 不挡（2026-10-16 复核：以前周末也全挡，1545 / 1482 凑不了钱）。
    今天买进的个股同样：当天对账前执行 → busy（today_why 也挡它的卖出）；对账之后执行 → 能凑（2026-10-16 二次复核：以前一直挡）。"""
    from . import live_ops as LO
    now = now or now_jst()
    pj = LO.held_now(book, tag, now=now)
    st = pj["state"]
    man = (book or {}).get("manual") or {}
    waiting = unseen(tag, book) if tag else []
    live = _settled_later(_live(man.get("items") or {}, waiting, ORDER_KINDS), book, pj, now)   # 今天已全部成交、对账时完成的不算（四次复核）
    busy = {r.get("ticker") for r in live if r.get("ticker")}
    busy |= set(st.get("pending_exit") or {})
    if pre_reconcile(pj, now):                             # 成交日当天、对账之前执行：今天有成交的（卖光的也在这里）当天动不了
        busy |= {f["ticker"] for f in pj.get("fills") or []}
    hold = []
    for t, p in (st.get("pos") or {}).items():
        px = float(p.get("last_close") or p.get("entry_px") or 0)
        hold.append({"t": t, "kind": "stock", "cur": int(p.get("shares") or 0), "px": px, "lot": LOT, "name": names.name(t)})
    for t, u in (st.get("core_units") or {}).items():
        c = core_info(book, t)
        px = float((c or {}).get("px") or (st.get("core_last") or {}).get(t) or 0)
        if int(u or 0) > 0:
            hold.append({"t": t, "kind": "core", "cur": int(u), "px": px, "lot": core_lot(book, t), "name": names.name(t)})
    paper = str(tag).startswith("paper") if tag else "Paper" in str((book or {}).get("broker") or "")
    if paper:
        rsv = 0.0
    else:                                                  # 出金预留（立花）：执行器的决策与盘中买入都不拿它买（G4；2026-10-14）
        from .live_unified import reserve_jpy
        rsv = float(reserve_jpy(book))
    cash = max(0.0, float(st.get("cash_jpy") or 0) - rsv) * (1 - CASH_BUF_PCT / 100)
    selling = {r.get("ticker") for r in live if _to_zero(r)}
    return {"cash": round(cash), "reserve": round(rsv), "hold": hold, "busy": sorted(busy), "exiting": sorted(st.get("pending_exit") or {}),
            "selling": sorted(selling - set(st.get("pending_exit") or {})),               # 已有卖出全部指令的（会卖、所得能用）
            "core_pct": core_pct_now(tag, book) if tag else float(man.get("core_pct", 100.0)),   # 「其他全部卖出」的预览用（2026-10-13）
            "fix": sorted(man.get("core_fix") or {})}


def fund_all(book: dict | None, tag: str | None, ticker: str, now: dt.datetime | None = None) -> dict:
    """「其他全部卖出，只拿这只 + 现金」（2026-10-13 用户：买新股时把持仓拖到最大 = 把其他的都卖掉来买这只；全卖也不够 100 股就留现金）：
    提交时要写的指令 → {"sells": [(票, 股数, 收盘)], "skip": [(票, 为什么不用写)], "core_pct": 现在的闲置资金比例, "core_clear": [有固定口数的 ETF],
    "cores": [(ETF, 口数)], "blocked": 不能做的原因 / None}。个股写成同批的卖出全部（设「不买回」）；规则已在卖的也写（执行时由规则卖、只设「不买回」，2026-10-13）；
    已有手动卖出全部的指令的不重复写；有别的没处理完的指令（减仓 / 加仓）的票 → blocked（先撤回它）；核心 ETF 用闲置资金比例 0%（卖出全部 + 停买），
    有固定口数的先取消；还没被执行器读的固定口数指令 → blocked；别的票还没下单的买入指令 → blocked（同一次决策买进、不会被卖；2026-10-14）。
    写入之后才拿的个股 / ETF 执行时一起卖（Manual.apply）。
    今天已知的成交（live_ops.held_now；2026-10-16）：今天卖光的个股 / 核心 ETF → skip（不再写空的卖出）；今天买进的个股（账本里还没有，对账前写不进
    同批的卖出全部）→ "bought"（代码；整批在对账之后的那次决策里做，_allin_sweep 把那时拿着的 X 以外的个股一起卖 → 不挡；2026-10-16 复核：
    以前挡住、周末 / 盘后都点不了）；核心 ETF 的口数按投影（只是说明）。"""
    from . import live_ops as LO
    st = (book or {}).get("state") or {}
    man = (book or {}).get("manual") or {}
    waiting = unseen(tag, book) if tag else []
    pj = LO.held_now(book, tag, now=now)
    now = now or now_jst()
    pre = pre_reconcile(pj, now)
    live = _settled_later(_live(man.get("items") or {}, waiting, ORDER_KINDS), book, pj, now)   # 今天已全部成交、对账时完成的不挡（四次复核）
    pend = st.get("pending_exit") or {}
    ppos = ((pj.get("state") or {}).get("pos") or {}) if pj.get("has") and not pre else None   # 对账之后执行：股数按含今天已成交的持仓
    out = {"sells": [], "skip": [], "cores": [], "blocked": None,
           "core_pct": core_pct_now(tag, book) if tag else float(man.get("core_pct", 100.0)), "core_clear": sorted(man.get("core_fix") or {})}
    out["day_word"] = pj.get("day_word") or "今天"
    out["bought"] = [x for x in pj.get("new") or [] if x != ticker and ((pj.get("by_ticker") or {}).get(x) or {}).get("kind") == "stock"]
    #                                                      今天买进的个股（对账之后算持仓）：执行时由 _allin_sweep 一起卖（只放代码 = 数据）
    sws = pj.get("when_sp") or LO.hn_sp(pj.get("when"))
    for t, p in sorted((st.get("pos") or {}).items()):
        cur = int(p.get("shares") or 0)
        if t == ticker or cur <= 0:
            continue
        if t in (pj.get("sold_out") or []):
            b0 = (pj.get("by_ticker") or {}).get(t) or {}
            out["skip"].append((t, f"{pj.get('day_word') or '今天'}已卖出全部 {int(b0.get('sell') or 0):,} 股（{sws}对账后正式记账）"))
            continue
        if pend.get(t) == "manual":
            out["skip"].append((t, f"已在卖出全部（{_exit_text(pend[t])}）"))
            continue
        mine = [r for r in live if r.get("ticker") == t]
        if mine and all(_to_zero(r) for r in mine):
            out["skip"].append((t, "已有卖出全部的指令"))
            continue
        if mine:
            out["blocked"] = f"{names.label(t)} 有没处理完的指令（{mine[-1].get('id')}）：先撤回它"
            return out
        if ppos is not None and t in ppos:                 # 今天减过的（对账之后执行时拿着的是剩下的）
            cur = int((ppos.get(t) or {}).get("shares") or cur)
        out["sells"].append((t, cur, float(p.get("last_close") or p.get("entry_px") or 0)))
    for t, u in sorted((pj.get("core_units") or {}).items()):   # 口数按投影（今天卖光的不列；只是说明）
        if int(u or 0) > 0:
            out["cores"].append((t, int(u)))
    for t in pj.get("sold_out") or []:                     # 今天卖光的核心 ETF：不用再卖（只是说明，比例 0% 那一句不再列它）
        b0 = (pj.get("by_ticker") or {}).get(t) or {}
        if t != ticker and b0.get("kind") == "core":
            out["skip"].append((t, f"{pj.get('day_word') or '今天'}已卖出全部 {int(b0.get('sell') or 0):,} 口（{sws}对账后正式记账）"))
    buys = [r for r in live if r.get("kind") == "buy" and r.get("ticker") != ticker]
    later = [r for r in buys if r.get("status", "pending") != "placed"]   # 还没下单的买入：和整批同一次决策买进、执行时不会被卖（2026-10-14）
    if later:
        out["blocked"] = (f"{names.label(later[0]['ticker'])} 有还没执行的买入指令（{later[0].get('id')}）：它会和「全部换成」在同一次决策里买进、"
                          "留着不卖 → 先撤回它（全部换成之后只拿这只）")
        return out
    out["also"] = sorted({t for t in (st.get("plan") or {}) if t not in (st.get("pos") or {}) and t != ticker}
                         | {r.get("ticker") for r in buys})   # 另外开盘还会买的（规则的开盘计划 / 已下单的买入指令）：执行时拿着就一起卖
    #                                                           （只放代码 = 数据；写成文字时用 names.labels，2026-10-15）
    gone = cancelled(waiting)
    if any(r.get("kind") == "corefix" and not r.get("clear") and r["id"] not in gone for r in waiting):
        out["blocked"] = "有还没被执行器读的「固定口数」指令：先撤回它"
    return out


def fund_split(cost: float, fh: dict, skip: str | None = None) -> dict | None:
    """买入要花 cost 円、现金不够 → 差额按金额平摊到每只持仓（个股 + 核心 ETF；skip = 要买的这只、busy 的不算）：
    每只先分「差额 ÷ 只数」，不够分的那只卖完、剩下的再平摊（注水法）；个股按单元取最接近的整数单元，
    核心 ETF 补足剩下的（向上取整到单元）；还不够 → 个股再加单元（一单元金额小的先加）。
    → {"short", "rows": [{"t", "kind", "cur", "sell", "yen", "after"}], "got", "left"（凑不齐的）}；现金够 → None。
    页面的 fundSplit（qbreak/panel.py 的 JS）与这里同一个算法。"""
    short = float(cost) - float(fh.get("cash") or 0)
    if short <= 0:
        return None
    busy = set(fh.get("busy") or [])
    H = [dict(h) for h in fh.get("hold") or [] if h["t"] != skip and h["t"] not in busy and h["cur"] > 0 and h["px"] > 0]
    H.sort(key=lambda h: (h["cur"] * h["px"], h["t"]))
    rem, k = short, len(H)
    for h in H:
        h["give"] = min(h["cur"] * h["px"], rem / k)
        rem -= h["give"]
        k -= 1
    got = 0.0
    for h in H:
        h["sell"] = 0
        if h["kind"] == "stock":
            h["sell"] = min(h["cur"], int(round(h["give"] / h["px"] / h["lot"])) * h["lot"])
            got += h["sell"] * h["px"]
    cores = [h for h in H if h["kind"] == "core"]
    need, k = short - got, len(cores)
    for h in sorted(cores, key=lambda h: (h["cur"] * h["px"], h["t"])):
        g = min(h["cur"] * h["px"], max(0.0, need) / k)
        h["sell"] = min(h["cur"], int(math.ceil(g / h["px"] / h["lot"] - 1e-9)) * h["lot"])
        need -= h["sell"] * h["px"]
        k -= 1
        got += h["sell"] * h["px"]
    while got < short:                                     # 还不够：个股再加一个单元（一单元金额小的先加）
        room = [h for h in H if h["kind"] == "stock" and h["sell"] + h["lot"] <= h["cur"]]
        if not room:
            break
        h = min(room, key=lambda h: (h["lot"] * h["px"], h["t"]))
        h["sell"] += h["lot"]
        got += h["lot"] * h["px"]
    rows = [{"t": h["t"], "kind": h["kind"], "cur": h["cur"], "sell": h["sell"], "yen": round(h["sell"] * h["px"]),
             "after": h["cur"] - h["sell"]} for h in sorted(H, key=lambda h: h["t"]) if h["sell"] > 0]
    return {"short": round(short), "rows": rows, "got": round(got), "left": round(max(0.0, short - got))}


def _exit_text(why: str) -> str:
    """卖出理由的中文（MACD 死叉 / 止损 / 手动卖出…；qbreak/holding_view.EXIT_TEXT）。"""
    try:
        from .holding_view import EXIT_TEXT
    except Exception:                                       # noqa: BLE001
        EXIT_TEXT = {}
    return EXIT_TEXT.get(str(why)) or REASON_TEXT.get(str(why)) or str(why)


def voided(recs: list[dict]) -> set:
    """被「撤销撤回」作废的撤回指令 id（2026-10-12 用户：「撤回指令也可以撤回，退回到下单、去掉撤销记录」）。"""
    return {r.get("target") for r in recs if r.get("kind") == "uncancel"}


def cancelled(waiting: list[dict]) -> set:
    """指令文件里执行器还没读的撤回指向的指令 id（页面：这些不再算「在处理」、不再给撤回按钮）；被撤销的撤回不算。"""
    void = voided(waiting)
    return {r.get("target") for r in waiting if r.get("kind") == "cancel" and r.get("id") not in void}


def cancel_cids(r: dict | None) -> list[str]:
    """一条撤单指令（cancel_order）要撤的单：主单 + 整组撤单的同一组（grp；2026-10-16）→ [cid]（去掉空的、重复的）。"""
    r = r or {}
    out = []
    for c in [r.get("cid")] + list(r.get("grp") or []):
        c = str(c or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def handling_cids(r: dict | None) -> list[str]:
    """一条还在处理的撤单指令要撤 / 在等的单（面板「撤单中」、live_ops.asked_cids / cancel_jobs 共用）= cancel_cids + 在等立花确认撤单的单（grp_wait）。
    同一组的其余几笔由 live_ops.cancel_scope 盖着（同一组同时只有一个撤单；简化 2026-10-16）。"""
    out = cancel_cids(r)
    for c in (r or {}).get("grp_wait") or []:
        c = str(c or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def _live(items: dict, waiting: list[dict], kinds) -> list[dict]:
    """还没处理完的指令（账本里 pending / placed 且没在撤回 + 指令文件里执行器还没读、也没被撤回的）。"""
    out = [it for it in items.values() if it.get("kind") in kinds and it.get("status") in ACTIVE and not it.get("cancel_req")]
    gone = cancelled(waiting)
    return out + [r for r in waiting if r.get("kind") in kinds and r["id"] not in gone]


def fund_companions(target: dict, recs: list[dict]) -> list[dict]:
    """「从持仓平摊凑」（fund = split）/「其他全部卖出」（fund = all）的买入同一次提交写的卖出 / 闲置资金指令
    （fund_for = 这只票、同一时刻写的）：撤回买入时一起撤。"""
    if target.get("fund") not in ("split", "all"):
        return []
    return [r for r in recs if r.get("fund_for") == target.get("ticker") and r.get("at") == target.get("at") and r.get("id") != target.get("id")]


def allin_member(r: dict) -> bool:
    """「全部换成 X」整批的一员：买入（fund=all）或同批（batch=all；比例 / 固定口数带 fund_for 的也是）。split 的凑钱卖出不算。"""
    return (r.get("kind") == "buy" and r.get("fund") == "all") or r.get("batch") == "all" or (
        r.get("kind") in ("core", "corefix") and bool(r.get("fund_for")))


def batch_buy(c: dict, recs) -> dict | None:
    """同批指令 c 所属的「全部换成 X」买入（同一只票、同一时刻、fund=all）。"""
    ff = c.get("fund_for")
    if not ff:
        return None
    return next((r for r in recs if r.get("kind") == "buy" and r.get("ticker") == ff and r.get("at") == c.get("at")
                 and r.get("fund") == "all"), None)


def live_allin(tag: str | None, book: dict | None) -> list[dict]:
    """还没处理完的「全部换成 X」买入（账本里 pending / placed 且没在撤回 + 还没读、也没被撤回的）。"""
    items = ((book or {}).get("manual") or {}).get("items") or {}
    waiting = unseen(tag, book) if tag else []
    return [r for r in _live(items, waiting, ("buy",)) if r.get("fund") == "all"]


def allin_busy_text(la: list[dict]) -> str | None:
    """有没处理完的「全部换成 X」时为什么现在不能改闲置资金比例 / 固定口数：已下单（今天在执行）→ 等对账；还在等决策 → 先撤回整批
    （以前一律叫你撤回，已下单的撤回会被拒；2026-10-14）。"""
    if not la:
        return None
    x = next((r for r in la if r.get("status") == "placed"), la[0])
    if x.get("status") == "placed":
        return (f"「全部换成 {names.label(x['ticker'])}」今天已下单、在执行：等执行器下一次运行对账、这批处理完之后"
                "再改闲置资金比例 / 固定口数")
    return f"「全部换成 {names.label(x['ticker'])}」在等决策（里面有闲置资金比例 / 固定口数）：先撤回它（整批一起撤），再改"


def batch_blocks(book: dict | None) -> list[dict]:
    """「全部换成 X」卖掉、现在还在「不自动买回」里的票，按批分组（2026-10-13：一批 = 同一只 X、同一次提交〔买入那条的 at〕；
    以前按 X 合并，两批换成同一只会一起解除）→ [{"x", "at", "since", "until"（批里最晚的；None = 一直）, "members": [{"t", "id", "state",
    "lift_from", "until"}]}]，按 at 排。state：卖出中（还拿着、开盘卖单已排）/ 等卖出（还拿着）/ sold（已卖出）。面板「恢复按规则」用。"""
    man = (book or {}).get("manual") or {}
    st = (book or {}).get("state") or {}
    items = man.get("items") or {}
    pos, pend = st.get("pos") or {}, st.get("pending_exit") or {}
    groups: dict[tuple, dict] = {}
    for t, b in sorted((man.get("blocks") or {}).items()):
        it = items.get(b.get("id")) or {}
        x = b.get("fund_for") or (it.get("fund_for") if it.get("batch") == "all" else None)
        if not x:
            continue
        at = str(b.get("batch_at") or it.get("at") or "")
        g = groups.setdefault((x, at), {"x": x, "at": at, "since": b.get("since"), "until": b.get("until"), "members": []})
        if str(b.get("since") or "") < str(g["since"] or "~"):
            g["since"] = b.get("since")
        if g["members"] and (g["until"] is None or b.get("until") is None):
            g["until"] = None
        elif str(b.get("until") or "") > str(g["until"] or ""):
            g["until"] = b.get("until")
        state = ("卖出中" if pend.get(t) else "等卖出") if t in pos else "sold"
        g["members"].append({"t": t, "id": b.get("id"), "state": state, "lift_from": b.get("lift_from"), "until": b.get("until")})
    return sorted(groups.values(), key=lambda g: (g["at"], g["x"]))


def lifting(tag: str | None, book: dict | None) -> set:
    """正在解除「不买回」的票（2026-10-13）：执行器还没读的解除（没被撤回、对得上现在的设定）+ 读了、等下一次决策生效的（blocks[t].lift_from）。"""
    blocks = ((book or {}).get("manual") or {}).get("blocks") or {}
    waiting = unseen(tag, book) if tag else []
    gone = cancelled(waiting)
    out = {r.get("ticker") for r in waiting if r.get("kind") == "unblock" and r["id"] not in gone and r.get("ticker") in blocks
           and (not r.get("block_id") or r.get("block_id") == (blocks.get(r.get("ticker")) or {}).get("id"))}
    return out | {t for t, b in blocks.items() if (b or {}).get("lift_from")}


def next_decision(now: dt.datetime | None = None) -> str:
    """「下一次决策（10/19 07:40）起生效」：带日期（复核 UI F5，2026-10-16：解除不买回的等待行 / manual list 以前写没有日期的
    「下一次决策（交易日 07:40）起生效」，周五收盘后写的实际是下周一、祝日前后更晚）。"""
    from .live_ops import next_decision_text
    return f"下一次决策（{next_decision_text(now or now_jst())}）起生效"


def unblock_why(t: str, book: dict | None, tag: str | None = None, block_id: str | None = None) -> str | None:
    """能不能写「解除不买回」（面板 / 命令行与 check 同一个口径）：没有设定 / 设定换了（页面过时）/ 已经在解除 / 有一条还没读的解除 → 理由。"""
    b = ((((book or {}).get("manual") or {}).get("blocks") or {}).get(t))
    lt = names.label(t)
    if not b:
        return f"{lt} 没有「不自动买回」的设定"
    if block_id and block_id != b.get("id"):
        return f"{lt} 的不自动买回已经换成别的设定（页面过时：刷新之后再点）"
    if b.get("lift_from"):
        return f"{lt} 的不自动买回已经在解除（{block_text(b)}）"
    waiting = unseen(tag, book) if tag else []
    gone = cancelled(waiting)
    if any(r.get("kind") == "unblock" and r.get("ticker") == t and r["id"] not in gone for r in waiting):
        return f"{lt} 已经在解除：等执行器读（{next_decision()}）"
    return None


def companions_in(target: dict, items: dict) -> list[dict]:
    """执行器账本里同一次提交写的同批指令（fund_companions 的账本版）。"""
    return fund_companions(target, list(items.values()))


LIVE_ORDER = ("SENDING", "SENT", "PARTIAL", "ERROR")   # 还挂在交易所（或状态不明）的单


def _at_exchange(book: dict, c: dict) -> bool:
    """同批的这条指令，它的单是不是还挂在交易所（寄付已受理 / 盘中已发、还没成交完；状态不明也算）：撤回指令撤不了。
    还没生效 / 没下单的（pending、比例 / 固定口数还在等决策）一律不算；撤单撤掉 / 失效 / 已成交的不算。"""
    st = book.get("state") or {}
    d = st.get("last_date")
    live = [o for o in book.get("orders") or [] if o.get("decided_on") == d and o.get("side") == "SELL" and o.get("status") in LIVE_ORDER]
    if c.get("kind") in POS_KINDS:
        if c.get("status") != "placed" or c.get("cancel_req"):
            return False
        return any(o.get("ticker") == c.get("ticker") and o.get("reason") in ("manual", "manual_trim") for o in live)
    if c.get("kind") in ("core", "corefix"):                # 比例 0% / 取消固定口数：只有在这次决策里生效了，这次决策的核心卖单才是它的
        return c.get("status") == "done" and c.get("decided_on") == d and any(o.get("kind") == "core" for o in live)
    return False


def allin_halt_note(book: dict | None) -> str | None:
    """HALT 前的提醒（2026-10-13）：这次决策的「全部换成 X」同批卖单已在交易所、X 的买单还等着开盘后补 → HALT 之后卖单照样成交、
    X 不会买（钱留现金）。没有这种情况 → None。"""
    book = book or {}
    d = (book.get("state") or {}).get("last_date")
    items = ((book.get("manual") or {}).get("items") or {})
    orders = [o for o in book.get("orders") or [] if o.get("decided_on") == d]
    xs = []
    for b in items.values():
        if not (b.get("kind") == "buy" and b.get("fund") == "all" and b.get("status") == "placed" and b.get("decided_on") == d):
            continue
        x = b.get("ticker")
        if not any(o.get("ticker") == x and o.get("side") == "BUY" and o.get("status") == "DEFERRED" for o in orders):
            continue
        mine = {c.get("ticker") for c in companions_in(b, items) if c.get("kind") in POS_KINDS and c.get("status") == "placed"}
        if any(o.get("side") == "SELL" and o.get("status") in LIVE_ORDER
               and (o.get("kind") == "core" or (o.get("ticker") in mine and o.get("reason") in ("manual", "manual_trim")))
               for o in orders):                            # 这次决策的核心卖单也是同批（过了闸门 = 比例 0%）
            xs.append(x)
    if not xs:
        return None
    x = names.labels(xs)
    return f"「全部换成 {x}」的卖单已在交易所会成交，{x} 不会买（钱留现金）；要整批不做，先用「撤单」撤卖单"


def cancel_plan(tag: str, book: dict | None, target: str, now: dt.datetime | None = None, sm: dict | None = None) -> dict:
    """撤回一条指令会怎样（只读；面板按钮与 cancel_request 同一口径）：{"why": 不能撤的原因 / None, "target", "todo": 一起撤的同批,
    "stuck": 撤不了的（读到就生效的比例 / 固定口数…）, "sent": 单还挂在交易所的同批（撤回指令撤不了 → 要用「撤单」）}。"""
    book = book or {}
    try:
        rec = normalize({"kind": "cancel", "target": target, "source": "panel"})
    except ValueError as e:
        return {"why": str(e), "target": None, "todo": [], "stuck": [], "sent": []}
    why = check(rec, book, tag, sm=sm, now=now)
    items = (book.get("manual") or {}).get("items") or {}
    waiting = unseen(tag, book)
    byid = {x["id"]: x for x in read_known(tag, book)}    # 整理账本时删掉的旧记录不算（2026-10-14 G1）
    byid.update(items)                                     # 执行器读过的以账本里的为准（有状态）；同一条不重复
    tg = byid.get(target) or {}
    gone = cancelled(waiting)
    todo, stuck, sent = [], [], []
    for c in fund_companions(tg, list(byid.values())):
        st_c = (items.get(c["id"]) or {}).get("status", "pending")
        if c["id"] in gone or c.get("cancel_req"):          # 已经在撤回中
            continue
        if _at_exchange(book, c):
            sent.append(c)
            continue
        if st_c not in ACTIVE:
            if c.get("kind") in ("core", "corefix") and st_c == "done":
                stuck.append(c)                            # 已经生效、单不在交易所（或已成交）：撤不了
            continue
        w = _cancel_why(c["id"], items, waiting, now=now)
        if w:
            (sent if w == NOW_NO_CANCEL else stuck).append(c)
            continue
        todo.append(c)
    return {"why": why, "target": tg, "todo": todo, "stuck": stuck, "sent": sent}


def cancel_request(tag: str, book: dict | None, target: str, now: dt.datetime | None = None, source: str = "cli",
                   sm: dict | None = None) -> tuple[bool, str, dict | None]:
    """撤回一条指令（面板与命令行共用，2026-10-13）：是「从持仓平摊凑」/「全部换成 X」的买入 → 同一次写的卖出 / 闲置资金指令一起撤
    （一次写进文件）；「全部换成」的同批卖单还挂在交易所 → 拒绝（只撤买入会变成「全卖不买」：先用「撤单」撤卖单）；
    平摊凑钱的卖单还挂着 → 照撤买入、说明卖单要用「撤单」；读到就生效的比例 / 固定口数撤不了 → 写进说明。→ (成功?, 说明, 撤回那条记录)。"""
    book = book or {}
    plan = cancel_plan(tag, book, target, now=now, sm=sm)
    if plan["why"]:
        return False, f"没写：{plan['why']}", None
    tg, todo, stuck, sent = plan["target"], plan["todo"], plan["stuck"], plan["sent"]
    if sent and tg.get("fund") == "all":
        return (False, f"没写：同批的 {len(sent)} 条（{'、'.join(describe(c) for c in sent)}）的单还挂在交易所，撤回指令撤不了；"
                       "只撤买入会变成「全卖不买」→ 要撤：先用「今天要成交的单」的「撤单」撤掉那几笔卖单（撤掉之后再撤回这条），或者不撤", None)
    clock = (lambda: now) if now else None
    recs = append_many(tag, [{"kind": "cancel", "target": target, "source": source}]
                       + [{"kind": "cancel", "target": c["id"], "source": source} for c in todo], clock=clock)
    rec = recs[0]
    msg = f"已写：撤回 {target_text(target, tg)}"               # 只写 id 看不出是哪只：补上撤的是什么（2026-10-15）
    if tg.get("kind") == "cancel_order":                    # 撤回撤单（2026-10-16 事后）
        msg += "：执行器读到之后不撤这笔单（还挂着的照常挂着、还没发出的照常发；HALT 中不发）"
    if todo:
        msg += (f"；为这笔买入写的 {len(todo)} 条卖出 / 闲置资金指令也撤回" if tg.get("fund") == "all" else f"；为它凑钱的 {len(todo)} 条卖出也撤回")
    for c in stuck:
        if c.get("kind") == "core":
            pv = c.get("prev_pct")
            msg += (f"；闲置资金比例 {pv:g}% → 0% 已经生效，撤不了：要恢复把比例设回 {pv:g}%（面板「按别的比例恢复」/ manual core --pct {pv:g}）"
                    if pv is not None else "；闲置资金比例 0% 已经生效，撤不了：要恢复点「确认买入：恢复闲置资金买入 ETF」")
        elif c.get("kind") == "corefix":
            msg += f"；{names.label(c.get('ticker'))} 的固定口数已取消（撤不了）：要的话重新点「固定口数…」"
        else:
            msg += f"；{describe(c)} 撤不了（{status_text(c) if c.get('status') else '已处理'}）"
    if sent:
        msg += f"；凑钱的 {len(sent)} 条卖单已经挂在交易所，撤回指令撤不了：要撤用「今天要成交的单」的「撤单」"
    return True, msg, rec


def target_text(target, tg: dict | None) -> str:
    """撤回的那条指令：「M20261015-081235-corefix-1482（固定 1482 对冲版美国 7〜10 年国债 678 口（不按规则自动调））」——
    只写 id 看不出是哪只（2026-10-15 用户：只写代码不知道是哪只）；找不到那条 → 只写 id。"""
    return f"{target}（{describe(tg)}）" if tg and tg.get("kind") else str(target)


def wait_word(r: dict | None) -> str:
    """指令还没处理时的状态词：会变成单的（卖出 / 减仓 / 调仓 / 买入）= 等下单；比例 / 解除不是单 = 等执行器读（2026-10-14）。
    固定口数 / 恢复按规则（不是「全部换成」的同批）当天按时段下单（D1；2026-10-15）→ 等下单；什么时候见 corefix_fill。"""
    r = r or {}
    return "等下单" if r.get("kind") in ORDER_KINDS or (r.get("kind") == "corefix" and not r.get("fund_for")) else "等执行器读"


def wait_text(r: dict | None, now: dt.datetime, book: dict | None, tag: str | None = None) -> str:
    """执行器还没读 / 还在等的指令：状态词 + 什么时候（具体时刻 / 日期；D1 / D5，2026-10-15：以前还没读的一律「等执行器读（下一次运行）」，
    固定口数没有日期）。面板的等待行、run.py --status / manual list 共用；时段口径与 now_due / due / 执行器一致。"""
    r = r or {}
    k, w = r.get("kind"), wait_word(r)
    if k == "corefix" and not r.get("fund_for"):
        return f"{w}：{corefix_fill(now, book, tag)['text']}"
    if allin_member(r):
        return f"{w}：{allin_when(now, book, tag)}整批"
    if k in ORDER_KINDS:
        return f"{w}：{when_for(now, book, r.get('ticker'))}"
    if k == "core":
        return f"{w}：读到就生效，核心 ETF {when_for(now, book)}照新比例调"
    if k == "unblock":
        return f"{w}：{next_decision(now)}"
    return w


def uncancel_request(tag: str, book: dict | None, cancel_id: str, now: dt.datetime | None = None,
                     source: str = "cli", sm: dict | None = None) -> tuple[bool, str, dict | None]:
    """撤销一条撤回（面板与命令行共用）：撤的是「平摊凑钱 / 其他全部卖出」的买入 → 同批指令的撤回一起撤销；
    有一条撤销不了（已被执行器读到并处理）→ 整个拒绝（要的话重新提交一次）。说明里写恢复之后什么时候、按什么价处理
    （与面板确认框同一句 uncancel_when；HALT 中写明解除后才处理；2026-10-13）。"""
    book = book or {}
    try:
        rec = normalize({"kind": "uncancel", "target": cancel_id, "source": source})
    except ValueError as e:
        return False, f"没写：{e}", None
    why = check(rec, book, tag, sm=sm, now=now)
    if why:
        return False, f"没写：{why}", None
    items = (book.get("manual") or {}).get("items") or {}
    waiting = unseen(tag, book)
    byid = {x["id"]: x for x in read_known(tag, book)}    # 整理账本时删掉的旧记录不算（2026-10-14 G1）
    byid.update(items)
    allr = list(byid.values())
    c = byid.get(cancel_id) or {}
    tg = byid.get(c.get("target")) or {}
    extra, back = [], []
    if tg.get("fund") in ("split", "all"):                 # 能不能整批恢复 check 已经查过：这里只收集同批的撤回
        void = voided(waiting)
        for cp in fund_companions(tg, allr):
            cc = next((x for x in allr if x.get("kind") == "cancel" and x.get("target") == cp["id"] and x["id"] not in void
                       and x.get("status") != "voided"), None)
            if cc is not None:
                extra.append(cc["id"])
                back.append(cp)
    clock = (lambda: now) if now else None
    recs = append_many(tag, [{"kind": "uncancel", "target": cancel_id, "source": source}]
                       + [{"kind": "uncancel", "target": cid, "source": source} for cid in extra], clock=clock)
    rec = recs[0]
    st = book.get("state") or {}
    if tg.get("fund") == "split" and back:                 # 凑钱的卖出：写清卖多少（check 已经保证现在还会卖；2026-10-13）
        rows = []
        for cp in back:
            a = adjust_plan(cp, st, MANUAL_CAP_PCT) if cp.get("kind") == "adjust" else None
            rows.append(f"{names.label(cp.get('ticker'))} 卖 {a['cur'] - a['want']:,} 股（{a['cur']:,} → {a['want']:,} 股）" if a else describe(cp))
        head = "（凑钱的卖出一起恢复：" + "、".join(rows) + "）"
    else:
        head = f"（同批的 {len(extra)} 条卖出 / 闲置资金指令一起恢复）" if extra else ""
    msg = (f"已写：撤销撤回 → 原来的指令恢复「{wait_word(tg)}」{head}，那条撤回不再显示；"   # 比例 / 固定口数 / 解除不是单（2026-10-14）
           + uncancel_when(tg, now or now_jst(), book, tag))
    if paths.halt_file().exists() and (tg.get("kind") in ORDER_KINDS + ("core",)):
        msg += "；★ HALT 生效中（解除后才处理）"
    return True, msg, rec


def _to_zero(r: dict) -> bool:
    """卖出全部，或减仓 / 调整到 0（这只票的名额在同一次决策里空出来）。"""
    k = r.get("kind")
    return k == "sell" or (k == "trim" and float(r.get("pct") or 0) <= 0) or (
        k == "adjust" and r.get("unit") in UNITS and float(r.get("value") or 0) <= 0)


def core_tickers(book: dict) -> set:
    """核心 ETF（不能手动买，用闲置资金比例调）：执行器写进账本的 manual.core + 拿着的 + 闲置资金各方式里的 ETF。"""
    st = (book or {}).get("state") or {}
    out = set(((book or {}).get("manual") or {}).get("core") or []) | set(st.get("core_units") or {})
    try:
        from .idle_cash import NAMES
        out |= set(NAMES)
    except Exception:                                       # noqa: BLE001
        pass
    return out


def core_lot(book: dict | None, t: str) -> int:
    """核心 ETF 一手几口：执行器记的（core_rule.lot）→ 立花的 ETF 表（qbreak/fees.py）→ 1。"""
    n = int((((book or {}).get("core_rule") or {}).get("lot") or {}).get(t) or 0)
    if n > 0:
        return n
    try:
        from .fees import DEFAULT_BROKER, etf_cost
        return max(1, int(etf_cost(DEFAULT_BROKER["JP"], t, "JP").get("lot") or 1))
    except Exception:                                       # noqa: BLE001
        return 1


def core_u100_est(cur, plan) -> int:
    """执行器还没用新代码决策过（账本没有 core_rule.units100）时，「闲置资金比例 100% 时的规则目标口数」的估算
    （2026-10-07 用户「ETF的话也要可以进行调仓 现在的button我看是非活性」）= 现在的口数 + 最近一次决策排的开盘单（买 + / 卖 −）。
    那次决策的比例是 100%（以前的代码没有比例）；规则在再平衡带（总权益的 10%）以内不调 → 与准确的目标可能差一点；
    下一次决策写入准确的数（之后按准确的数）。plan = (方向, 口数) 或 None。"""
    side, n = (list(plan or []) + [None, 0])[:2]
    d = int(n or 0) if side == "BUY" else -int(n or 0) if side == "SELL" else 0
    return max(0, int(cur or 0) + d)


def core_u100s(book: dict | None) -> tuple[dict, bool]:
    """各只核心 ETF 的规则目标口数（闲置资金比例 100% 时）→ ({票: 口数}, 是不是估算)。执行器算过（core_rule.units100）→ 用它；
    还没算过、比例也还是 100%（没改过）→ 按 core_u100_est 估算（与执行器 now_phase 同一个算法）；比例改过却没算过 → ({}, False)。"""
    cr = (book or {}).get("core_rule") or {}
    if cr.get("units100"):
        return {t: int(n) for t, n in cr["units100"].items()}, False
    pct = float(((book or {}).get("manual") or {}).get("core_pct", 100.0))
    if abs(float(cr.get("applied", 100.0)) - 100.0) > 1e-9 or abs(pct - 100.0) > 1e-9:
        return {}, False
    st = (book or {}).get("state") or {}
    units, plan = st.get("core_units") or {}, st.get("core_plan") or {}
    out = {t: core_u100_est(units.get(t, 0), plan.get(t)) for t in sorted(set(units) | set(plan))}
    return {t: n for t, n in out.items() if n > 0 or int(units.get(t, 0) or 0) > 0}, True


def core_info(book: dict | None, t: str, pj: dict | None = None) -> dict | None:
    """一只核心 ETF 的调仓用数字：{"cur" 现在口数, "u100" 规则目标（闲置资金比例 100% 时；最近一次决策算的）, "px", "lot", "eq",
    "pct" 现在的比例, "selling" 规则这次在卖它, "approx" 规则目标是估算的（执行器还没算过：core_u100s）}；
    不是核心 ETF / 规则目标估不了 → None。pj（live_ops.held_now 的结果）给了 → cur / eq 含今天已成交（core_rec；2026-10-16 二次复核）。"""
    st = (book or {}).get("state") or {}
    cr = (book or {}).get("core_rule") or {}
    u100s, approx = core_u100s(book)
    if t not in core_tickers(book or {}) or t not in u100s:
        return None
    hist = st.get("history") or []
    px = float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)
    plan = (st.get("core_plan") or {}).get(t) or []
    cur = int((st.get("core_units") or {}).get(t, 0))
    u100 = int(u100s.get(t, 0))
    eq = float(hist[-1][1]) if hist else 0.0
    if pj and pj.get("has"):                               # 含今天已成交（对账前的预计）
        cur = int(((pj.get("state") or {}).get("core_units") or {}).get(t, 0))
        eq = float(pj["equity"]) if pj.get("equity") is not None else eq
    return {"cur": cur, "u100": u100, "px": px, "lot": core_lot(book, t),
            "eq": eq, "pct": float(((book or {}).get("manual") or {}).get("core_pct", 100.0)),
            "selling": u100 <= 0 or (len(plan) == 2 and plan[0] == "SELL" and int(plan[1]) >= cur > 0), "approx": approx}


def core_effects(book: dict | None, pct: float, skip: str | None = None, keep_fixed: bool = False,
                 tag: str | None = None) -> list[tuple[str, int, int]]:
    """闲置资金比例改成 pct 时，各只核心 ETF（skip 以外）现在的口数 → 新比例下的目标口数（只列会变的）：[(票, 现在, 目标)]。
    比例对全部核心 ETF 一起生效（规则同时拿两只以上时，调一只另一只也跟着变）。固定口数的 ETF 不跟比例（2026-10-13）→ 不列；
    keep_fixed：也列（「全部换成」：固定口数同批取消、之后按比例 0% 卖出）。tag：执行器还没读的固定口数 / 恢复按规则也算上（2026-10-14）。
    现在的口数按 live_ops.held_now（含今天已成交；只是说明文字，2026-10-16）。"""
    from . import live_ops as LO
    st = LO.held_now(book, tag)["state"]
    fixed = set() if keep_fixed else set(core_fixed(book, tag))
    u100s = dict(core_u100s(book)[0])                        # 执行器还没算过 → 估算（比例还是 100% 时）
    if float(pct) <= 0:                                     # 比例 0%：拿着的都卖（执行器还没算过规则目标额的也一样）
        u100s.update({t: u100s.get(t, 0) for t, u in (st.get("core_units") or {}).items() if int(u) > 0})
    out = []
    for t, n100 in sorted(u100s.items()):
        cur, lot = int((st.get("core_units") or {}).get(t, 0)), core_lot(book, t)
        tg = int(math.floor(int(n100) * float(pct) / 100 / lot + 1e-9)) * lot
        if t != skip and t not in fixed and tg != cur and (cur > 0 or tg > 0):
            out.append((t, cur, tg))
    return out


def core_fixed(book: dict | None, tag: str | None = None) -> dict:
    """固定口数的核心 ETF → {票: 口数}（manual.core_fix：不按规则 / 闲置资金比例自动调；2026-10-13）。给了 tag → 执行器还没读的
    固定 / 恢复按规则指令也算上（按写的顺序；已经点了撤回的、「全部换成」同批等决策的不算）。"""
    out = {str(t): int(u) for t, u in ((((book or {}).get("manual") or {}).get("core_fix")) or {}).items()}
    waiting = unseen(tag, book) if tag else []
    gone = cancelled(waiting) if waiting else set()
    for r in waiting:
        if r.get("kind") != "corefix" or r["id"] in gone or r.get("fund_for"):
            continue
        if r.get("clear"):
            out.pop(r.get("ticker"), None)
        else:
            out[r["ticker"]] = int(r.get("units") or 0)
    return out


def fix_applied(book: dict | None) -> dict:
    """最近一次照固定口数排了单的口数（core_rule.fix_applied：决策或盘中的 fix_moves 按它排了单之后记；D1，2026-10-15）→ {票: 口数}。
    旧账本没有这个字段 → 当成现在的 manual.core_fix（不追溯：升级之前的固定口数已经由那时的决策排过单）。"""
    b = book or {}
    app = (b.get("core_rule") or {}).get("fix_applied")
    if app is None:
        app = (b.get("manual") or {}).get("core_fix") or {}
    return {str(t): int(u) for t, u in app.items()}


def corefix_pending(book: dict | None, tag: str | None = None, now: dt.datetime | None = None) -> dict:
    """固定口数（manual.core_fix；给了 tag → 含执行器还没读的 corefix，「全部换成」的同批不算）≠ 最近一次照它排了单的口数（fix_applied）
    的核心 ETF → {票: 固定口数 | None（恢复按规则）}（D1；2026-10-15：以前固定口数只在下一次决策生效，盘中 / 开盘前写的整天「等执行器读」）。
    面板（now_due）与执行器（now_phase 的 fix_moves）同一个判断。执行器还没决策过（没有 core_rule）→ {}（早上的决策会读到）。
    now 给了：这只今天已经说了「下一次决策再调」（core_rule.fix_defer：同一个固定口数）→ 不算（写了新的固定口数 → 又算）。"""
    b = book or {}
    cr = b.get("core_rule") or {}
    if not cr:
        return {}
    app, cur = fix_applied(b), core_fixed(b, tag)
    out = {t: cur.get(t) for t in sorted(set(cur) | set(app)) if cur.get(t) != app.get(t)}
    if now is not None:
        today = now.date().isoformat()
        fd = cr.get("fix_defer") or {}
        out = {t: u for t, u in out.items()
               if not ((fd.get(t) or {}).get("day") == today and (fd.get(t) or {}).get("units", -1) == u)}
    return out


OPEN_ST =("PLANNED", "DEFERRED", "SENDING", "SENT", "PARTIAL", "ERROR")   # 执行器的单还没结束（等下单 / 开盘后 / 发送中 / 已下单 / 部分成交 / 结果不明）


def orders_today(book: dict | None, now: dt.datetime, t: str | None = None, open_only: bool = False) -> list[dict]:
    """账本当前决策里成交日是今天、还活着的执行器的单（live_ops.busy：成交过 / 在交易所 / 发送中 / 状态不明 / 钱还会来的等开盘后 /
    今天还会再发的计划；撤了 / 不下 / 被拒 / 失效 / 盘中没到交易所 / 凑钱的卖单没了的孤儿不算 = 与执行器 now_phase「今天已经有执行器的单」
    同一个判断；2026-10-13，D4 2026-10-15：以前撤了的单也算，撤单之后当天写不了新的）。t：只看这只；open_only：只看还没结束的（OPEN_ST）。
    今天早上的决策还没跑（成交日不是今天）→ []。"""
    from . import live_ops as LO
    st = (book or {}).get("state") or {}
    d = st.get("last_date")
    try:
        if not d or next_trading_day(dt.date.fromisoformat(str(d)[:10])) != now.date():
            return []
    except ValueError:
        return []
    out = []
    cur = [o for o in (book or {}).get("orders") or [] if o.get("decided_on") == d]
    for o in cur:
        if t is not None and o.get("ticker") != t:
            continue
        if not LO.busy(o, cur, now, now.date()):
            continue
        if open_only and o.get("status") not in OPEN_ST:
            continue
        out.append(o)
    return out


def busy_today(book: dict | None, t: str, now: dt.datetime) -> bool:
    """这只票今天已经有执行器还活着的单吗（D4；2026-10-15）：执行器 now_phase「这只今天已经有执行器的单 → 明天开盘」、
    手动指令「什么时候下」的说明（when_for）、面板共用 live_ops.busy 一处逻辑。同一只票当天执行器只下一笔（成交过的照算）。"""
    return bool(orders_today(book, now, t))


def today_why(book: dict | None, t: str | None, kind: str | None, tag: str | None = None,
              now: dt.datetime | None = None, rec: dict | None = None) -> str | None:
    """今天已成交、还没对账的票，写手动指令前挡一下（窄的写入守卫；2026-10-16 用户卖出 1545、买入 1482 后「持仓里没反应」）→ 理由 / None。
    只挡执行器真的会做错 / 做不了的（2026-10-16 二次复核）。现在写的指令什么时候执行：pre_reconcile（成交日当天开盘前 / 盘中 / 午休）→
    当天按账本（还没对账）、同一只当天不再下第二笔；否则（收盘后 / 周末 / 休市日 / 下一个交易日早上）→ 下一次决策，那时已经对过账。
      今天已经卖光的（个股 / 核心 ETF）：再点卖出 / 减仓 / 调到 0 → 不用再点（旧页面上再点「卖出全部 1545」会变成闲置资金比例 0%、停买 ETF）；
        调仓往上 → 核心 ETF 用「固定口数…」/「闲置资金比例」、个股用「买入」（对账之后是 0，调仓不适用）；个股再买 → 当天挡（对账之后才能再买），
        对账之后执行的 → 不挡（照名额、资格等别的检查）。
      今天买进的个股：再买 → 已经买进（要加仓用「调仓」）；卖出 / 减仓 / 调仓 → 当天挡（执行器当天不动它，盘中调仓往上会被拒），
        对账之后执行的 → 不挡（check 按含今天已成交的持仓看）。
    按 live_ops.held_now（与页面显示同一个数）；rec = 要写的指令（判断「调到 0」）；其余 → None。"""
    if not t or (kind not in POS_KINDS and kind != "buy"):
        return None
    from . import live_ops as LO
    now = now or now_jst()
    pj = LO.held_now(book, tag, now=now)
    b = (pj.get("by_ticker") or {}).get(t) if pj.get("has") else None
    if not b:
        return None
    pre = pre_reconcile(pj, now)
    lt, dw = names.label(t), pj.get("day_word") or "今天"
    sw = pj.get("when_sp") or LO.hn_sp(pj.get("when") or pj.get("settle") or "下一次执行器运行")   # 「10/19（周一）07:40 对账」/「下一次执行器运行对账」
    core = b.get("kind") == "core"
    u = "口" if core else "股"
    if t in (pj.get("sold_out") or []):
        done = f"{lt} {dw}已经卖出全部 {int(b.get('sell') or 0):,} {u}（{sw}对账后正式记账）"
        if kind == "buy":
            return f"{done}：对账之后（收盘后 15:25 起写）才能再买" if pre else None
        if kind in ("sell", "trim") or _to_zero(rec or {"kind": kind}):
            return f"{done}，不用再点"
        if core:
            return f"{done}：要买回用「固定口数…」或「闲置资金比例」（对账之后口数是 0，调仓不适用）"
        return f"{done}：要买回用「买入」（对账之后没有持仓，调仓不适用）"
    if core or t not in (pj.get("new") or []):
        return None
    n = int(b.get("buy") or 0)
    if kind == "buy":
        return (f"{lt} {dw}已经买进 {n:,} 股（{sw}对账之后才算持仓）："
                + ("要加仓收盘后（15:25 起）用「调仓」（下一个交易日开盘执行）" if pre else "要加仓用「调仓」（对账之后执行）"))
    if pre:
        return (f"{lt} {dw}刚买进 {n:,} 股：今天盘中执行器不再动它（账本{sw}对账才记上）；"
                "收盘后（15:25 起）再写卖出 / 调仓 → 下一个交易日开盘执行")
    return None


def _order_word(o: dict) -> str:
    """「今天开盘已排的 1545 纳斯达克 100 卖 1,130 口」（盘中的单：今天盘中已下的）。"""
    n = int(o.get("sent_qty") or o.get("qty") or 0)
    return (f"今天{'盘中已下' if o.get('phase') == 'now' else '开盘已排'}的 {names.label(o.get('ticker'))} "
            f"{'买' if o.get('side') == 'BUY' else '卖'} {n:,} 口")


def pj_got(pj: dict | None) -> dict:
    """held_now 的结果 → {单号: 已经算进投影的成交数}。"""
    got: dict = {}
    for f in (pj or {}).get("fills") or []:
        got[str(f.get("cid"))] = got.get(str(f.get("cid")), 0) + int(f.get("qty") or 0)
    return got


def pj_done(o: dict, pj: dict | None, got: dict | None = None) -> bool:
    """这张执行器的单已经全部成交了吗：账本里 FILLED 且成交数 ≥ 发出数，或 held_now（pj）里它不在等成交、已知的成交 ≥ 发出数
    （立花的单对账前一直是 SENT，成交只有盘中确认 / 快照知道 —— 执行器 fix_prep 盘中查注文同一个判断；2026-10-16 三次复核）。部分成交 → False。"""
    n = int(o.get("sent_qty") or o.get("qty") or 0)
    if o.get("status") == "FILLED" and int(o.get("filled_qty") or 0) >= n:
        return True
    c = str(o.get("cid"))
    got = pj_got(pj) if got is None else got
    return c not in {str(p.get("cid")) for p in (pj or {}).get("pending") or []} and got.get(c, 0) >= n > 0


def _exch_words(os_: list, pj: dict | None, got: dict | None = None) -> tuple[str, str]:
    """盘中那条路：同一只今天已经在交易所的单 → (已经全部成交的那句, 还在等成交的单的说法)；空 = 没有。
    已经全部成交的（pj_done）已经算进现在的口数，执行器不等它（fix_prep）；部分成交的只写还剩的口数。"""
    got = pj_got(pj) if got is None else got
    done = [o for o in os_ if pj_done(o, pj, got)]
    snap = {str(f.get("cid")) for f in (pj or {}).get("fills") or [] if f.get("src") == "snapshot"}
    dw = ("、".join(_order_word(o) for o in done) + " 已成交（" + ("快照，" if any(str(o.get("cid")) in snap for o in done) else "")
          + "对账前的预计）→ 已算进现在的口数") if done else ""
    ws = []
    for o in os_:
        if o in done:
            continue
        g = got.get(str(o.get("cid")), 0)
        n = int(o.get("sent_qty") or o.get("qty") or 0)
        ws.append(_order_word(o) + (f"（已成交 {g:,} 口，还剩 {n - g:,} 口）" if 0 < g < n else ""))
    return dw, "、".join(ws)


def today_dead(book: dict | None, tag: str | None = None, now: dt.datetime | None = None) -> tuple[set, dict]:
    """当前决策里不会再做事的执行器的单（面板「交易」的「撤单中」/「不会下单（预计）」同一个判断；2026-10-15 复核：
    「恢复按规则」的确认框、提交说明以前把凑钱的卖单撤了、一定买不起的 1482.T 买 678 口写成「照常」，「交易」却写「不会下单」）→
    (撤单中的 cid, {一定下不成的买单的 cid: live_ops.outlook 的那一行（reason / gone）})。D5（2026-10-15）起只用 outlook 判断
    （HALT 不算：这里说的是钱）。算不成 → 不下结论（空）。只读。"""
    from . import live_ops as LO
    try:
        waiting = unseen(tag, book) if tag else []
        ol = LO.outlook(book, waiting, now, tag=tag, halt=False, instr=False)
        return ol["asked"], {c: r for c, r in ol["orders"].items() if r["cls"] == "fund"}
    except (TypeError, ValueError, KeyError, AttributeError):
        return set(), {}


def _dead_word(o: dict, asked: set, unf: dict) -> str:
    """不会再做事的单那句的括号：撤单中 / 资金来源的卖单已撤、开盘时现金不够一单元。"""
    if str(o.get("cid")) in asked:
        return "（撤单中）"
    x = unf.get(str(o.get("cid"))) or {}
    return "（" + ("资金来源的卖单已撤，" if x.get("gone") else "开盘时现金不够一单元，") + "预计不会下单：见「交易」→「已结束 / 不是今天的」）"


def corefix_clear_text(book: dict | None, t: str, tag: str | None = None, now: dt.datetime | None = None) -> str:
    """「恢复按规则」（取消固定口数）之后会怎样（页面确认框 / 提交说明 / 命令行共用；2026-10-13）：规则自己的目标（core_rule.rule100，
    不固定时的口数，含牛熊）× 现在的闲置资金比例 对比 现在的口数（+ 今天的单成交之后）→ 下一次决策卖 / 买多少；停买中（比例 0%）→ 全部卖出；
    差额在再平衡带（总权益的 10%）以内 → 规则可能不动；今天已经有这只的执行器的单 → 照常（要不做：撤单），下一次决策起照规则、可能反向买卖；
    撤单中 / 开盘时一定下不成的（today_dead：「交易」写「不会下单（预计）」的）不算进成交后的口数、写「预计不会下单」（2026-10-15 复核）。
    盘中 / 开盘后马上的那条路（corefix_fill 的 intraday；D1，2026-10-15）：执行器 now_phase 照规则目标 × 比例直接调（不看再平衡带）；
    同一只今天还没发出的核心单被取代、已经在交易所的先等它成交 / 撤掉（已知全部成交的 = pj_done：已算进口数、不等）；口数 = 账本 + 今天已经成交的。
    按最近一次决策的收盘估算；执行器按当时的数算。
    现在的口数 = live_ops.held_now（账本 + 成交日已知的成交；周末 / 休市日 / 07:40 之前也算 —— 2026-10-16 复核：以前只在成交日当天
    看今天的单，周六说「规则现在不拿 → 不会买」，其实下一次决策要卖掉 10/16 买进的 650 口）+ 今天还活着的单还没成交的部分。"""
    from . import live_ops as LO
    now = now or now_jst()
    st = (book or {}).get("state") or {}
    cr = (book or {}).get("core_rule") or {}
    cur = int((st.get("core_units") or {}).get(t, 0))
    pj = LO.held_now(book, tag, now=now)
    pjc = int((pj.get("core_units") or {}).get(t, 0) or 0)   # 含成交日已知的成交（对账前；2026-10-16）
    got = pj_got(pj)                                       # 每笔单已经算进 held_now 的成交口数
    lot = core_lot(book, t)
    pct = core_pct_now(tag, book)
    fill = corefix_fill(now, book, tag)
    nowp = bool(fill["intraday"])
    mine = orders_today(book, now, t)
    asked, unf = today_dead(book, tag, now)
    dead = [o for o in mine if o.get("status") in OPEN_ST and (str(o.get("cid")) in asked or str(o.get("cid")) in unf)]
    dcid = {str(o.get("cid")) for o in dead}
    after = pjc
    for o in mine:                                         # 今天还活着的单：已经成交的在 pjc 里；没结束的再加还没成交的部分
        if str(o.get("cid")) in dcid or (nowp and o.get("status") in ("PLANNED", "DEFERRED")):
            continue                                       # 撤单中 / 一定下不成（「交易」写「不会下单」的）：只算已经成交的（2026-10-15 复核）；
        #                                                    盘中那条路：还没发出的被取代（D1）
        if o.get("status") not in OPEN_ST:
            continue                                       # 结束了的：成交口数已经在 pjc 里
        left = max(0, int(o.get("sent_qty") or o.get("qty") or 0) - got.get(str(o.get("cid")), 0))
        after += left if o.get("side") == "BUY" else -left
    after = max(0, after)
    nd = "" if nowp else "下一次决策"
    head = (f"{fill['text']}调到规则现在的口数，之后每天照规则（美股牛熊 / 股债相关 × 闲置资金比例）自动买卖" if nowp else
            "下一次决策（交易日 07:40）起这只 ETF 又按规则（美股牛熊 / 股债相关 × 闲置资金比例）自动买卖")
    tail = f"，今天的单成交后约 {after:,} 口" if after != pjc else ""
    if pjc != cur:
        now_u = f"现在 {pjc:,} 口（{pj.get('head') or '含今天已成交'}；账本 {cur:,} 口）" + tail
    else:
        now_u = f"现在 {cur:,} 口" + tail
    r100 = (cr.get("rule100") or {}).get(t)
    if pct <= 0:
        plan = (f"停买中（闲置资金比例 0%）→ {nd}全部卖出 {after:,} 口（{now_u}）" if after > 0 else
                "停买中（闲置资金比例 0%）→ 不会买")
    elif r100 is None:
        plan = ("规则自己的目标执行器还没算过 → 盘中不调，下一次决策照规则" if nowp else
                "规则自己的目标执行器下一次决策才算（之后面板显示）")
    else:
        tgt = int(math.floor(int(r100) * pct / 100 / lot + 1e-9)) * lot
        lab = f"规则现在 {tgt:,} 口" + (f"（规则目标 {int(r100):,} × 闲置资金比例 {pct:g}%）" if pct < 100 else "") + f"（{now_u}）"
        px = float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)
        hist = st.get("history") or []
        eq = float(hist[-1][1]) if hist else 0.0
        band = float(cr.get("band_pct") or 10.0) / 100 * eq
        diff = tgt - after
        if tgt <= 0:
            plan = (f"规则现在不拿（熊市 / 换 ETF）→ {nd}全部卖出 {after:,} 口" if after > 0 else "规则现在不拿 → 不会买")
        elif diff == 0:
            plan = lab + " → 不用买卖"
        elif not nowp and px > 0 and eq > 0 and abs(diff) * px <= band:
            plan = (lab + f" → 差 {abs(diff):,} 口在再平衡带（总权益的 {band / eq * 100:g}%）以内：规则可能不"
                    + ("买，钱可能留现金" if diff > 0 else "卖，口数先不动"))
        else:
            plan = lab + f" → {nd}{'买' if diff > 0 else '卖'} {abs(diff):,} 口"
    out = head + "：" + plan
    live = [o for o in mine if o.get("status") in OPEN_ST and str(o.get("cid")) not in dcid]
    if nowp:                                               # 盘中那条路（D1）：没发出的被取代、在交易所的先等
        uns = [o for o in mine if o.get("status") in ("PLANNED", "DEFERRED")]
        dw, ws = _exch_words([o for o in live if o not in uns], pj, got)
        if uns:
            out += "；" + "、".join(_order_word(o) for o in uns) + " 还没发出：被这条取代（执行器不再发）"
        if dw:
            out += "；" + dw
        if ws:
            out += "；" + ws + " 还挂着：先等它成交 / 撤掉，再按成交后的口数调"
        dead = [o for o in dead if o not in uns]
    elif live:
        out += ("；" + "、".join(_order_word(o) for o in live) + "照常（要不做：「今天要成交的单」→ 撤单）；下一次决策起照规则，可能反向买卖")
    if dead:
        out += "；" + "、".join(_order_word(o) + _dead_word(o, asked, unf) for o in dead)
    return out


def resume_info(book: dict | None, tag: str | None = None, now: dt.datetime | None = None, pct: float = 100.0) -> dict:
    """停买中点「确认买入」/「恢复成 N%」（闲置资金比例 0% → N%）之后什么时候买（页面卡片 / 确认框 / 提交说明 / 命令行共用；2026-10-13）→
    {"none": 规则现在不拿任何（不固定的）核心 ETF（不会马上买）, "late": [今天已经有执行器的单的 ETF（盘中不再调它）], "when", "late_when",
    "text": 一句话}。规则拿的 ETF 都没有今天的单 → text 照「什么时候下单」（马上 / 开盘…）。
    pct < 100（「恢复成 N%」）：说「按规则目标额的 N% 买入 / 之后每天按 N% 调」，不说照规则（2026-10-14）。"""
    full = float(pct) >= 100 - 1e-9
    buy = "照规则买入" if full else f"按规则目标额的 {float(pct):g}% 买入"
    after = "之后每天照规则调" if full else f"之后每天按 {float(pct):g}% 调"
    now = now or now_jst()
    when = when_text(now)
    cr = (book or {}).get("core_rule") or {}
    fixed = core_fixed(book, tag)
    u = {t: int(n) for t, n in (cr.get("units100") or {}).items() if t not in fixed}
    nd = next_trading_day(now.date())
    late_when = "明天开盘" if nd == now.date() + dt.timedelta(days=1) else f"{nd:%m/%d} 开盘"
    out = {"none": False, "late": [], "when": when, "late_when": late_when}
    if cr.get("units100") is not None and not any(n > 0 for n in u.values()):
        out.update(none=True, text="规则现在不拿 ETF：确认后不会马上买；之后规则转为拿时自动" + ("照规则买" if full else f"按规则目标额的 {float(pct):g}% 买")
                   + "（不再只提醒）")
        return out
    want = [t for t, n in sorted(u.items()) if n > 0]
    if timing(now)[0] != "next":
        out["late"] = [t for t in want if orders_today(book, now, t)]
    late = out["late"]                                     # late 是数据（只放代码）；文字里写「代码 名字」（2026-10-15）
    if late and len(late) == len(want):
        out["text"] = f"确认后{late_when}{buy}（{names.labels(late)} 今天已经有执行器的单：盘中不再调）；{after}"
    elif late:
        out["text"] = f"确认后{when}{buy}（{names.labels(late)} 今天已经有执行器的单：{late_when}再买）；{after}"
    else:
        out["text"] = f"确认后{when}{buy}，{after}"
    return out


# ── 固定口数 / 恢复按规则：写之前先给「确认下单 / 取消下单」（2026-10-15 用户：「每天在盘中的时候固定口数点击确定的话要出现确认下单和
#    取消下单的确认不要直接下单」；10/14 19:21 把 1482.T 固定成 678 口，第二天早上的决策为了凑钱排了卖出全部 1545.T —— 写之前没看到）──
CORE_GAP_PCT = 3.0                      # 执行器给固定口数凑钱时多卖的跳空余量（引擎 max_entry_gap_pct；粗算用）
CORE_BUY_LIMIT = 1.02                   # 早上决策的核心 ETF 买单：寄付指値 = 收盘 ×1.02（qbreak/unified.py 的 orders_for）


def corefix_fill(now: dt.datetime, book: dict | None, tag: str | None = None, lock: bool = True) -> dict:
    """固定口数 / 恢复按规则什么时候变成单（D1；2026-10-15 用户「盘中下的单应该是进行实时成交的」：与卖出 / 买入同一个时段口径，
    以前一律「下一次决策 07:40 读到 → 那天 09:00 开盘」，盘中 / 开盘前写的整天「等执行器读」）：
      盘中（09:00〜11:30、12:30〜15:25）写的 → 马上（面板叫 --phase now：按现价限价；模拟账户当场成交）；
      今天早上的决策之后、开盘前 / 午休写的 → 09:00 / 12:30 开盘后第一次盘中运行马上下（按现价限价，不是寄付）；
      今天早上的决策之前写的 → 那次决策读到 → 今天 09:00 开盘（寄付；执行器正在跑、这次没读到 → 09:00 开盘后马上）；
      15:25 之后 / 休市日 → 下一次决策（MM/DD 07:40）→ MM/DD 09:00 开盘。
    早上的运行没完成、已过寄付截止（08:55）→ 补跑那次决策读到（立花 08:55 之后补跑错过寄付：核心 ETF 的单今天不发，B13）。
    与面板什么时候叫执行器（now_due / corefix_pending）同一个判断（tests/test_corefix_now.py 的参数化测试会查）。
    → {"mode": "now" | "open" | "lunch" | "decision" | "behind", "day": 下单的日子, "intraday": 盘中按现价下（now / open / lunch）,
       "behind": 早上的运行没完成且已过寄付截止, "busy": 执行器正在跑（这次没读到）, "text": 一句话}。
    lock=False：不看执行器的锁（执行器自己读指令时写说明用：锁是它自己拿着的）。"""
    st = (book or {}).get("state") or {}
    ld = str(st.get("last_date") or "")
    try:
        last = dt.date.fromisoformat(ld[:10])
    except ValueError:
        last = prev_trading_day(now.date())
    mode, d = timing(now)
    today = now.date()
    paper = str(tag or "").startswith("paper")
    undecided = bool(ld) and is_trading_day(today) and ld < prev_trading_day(today).isoformat()   # 今天早上的决策还没做（与 morning_behind 同）
    busy = False
    if undecided and now.time() >= CUTOFF:
        nxt = next_trading_day(today)
        if paper:
            text = (f"今天早上的运行还没完成：补跑那次决策时读到、照它排单（面板会自动补跑）；没补跑 → {nxt:%m/%d} 07:40 的决策、"
                    f"{nxt:%m/%d} 09:00 开盘下单")
        else:                                              # 立花：08:55 之后补跑的那次决策错过寄付，核心 ETF 的单今天不发（B13；2026-10-15 复核）
            text = (f"今天早上的运行还没完成：立花 08:55 之后补跑的那次决策错过寄付，核心 ETF 的单今天不发（B13）→ "
                    f"{nxt:%m/%d} 07:40 的决策读到、{nxt:%m/%d} 09:00 开盘下单（立花不自动补跑）")
        return {"mode": "behind", "day": today, "intraday": False, "behind": True, "busy": False, "text": text}
    if undecided:                                          # 早上的决策之前（交易日 08:55 之前）：那次决策读到 → 今天 09:00 开盘（寄付）
        if tag and lock:
            try:
                from .live_unified import lock_held
                busy = lock_held(paths.state_dir() / f"live_unified_{tag}.lock")
            except Exception:                               # noqa: BLE001
                busy = False
        text = "今天早上的决策（07:40）读到 → 今天 09:00 开盘（寄付）"
        if busy:
            text += "（执行器正在跑：这次没读到 → 今天 09:00 开盘后马上，按现价限价）"
        return {"mode": "decision", "day": today, "intraday": False, "behind": False, "busy": busy, "text": text}
    if not (book or {}).get("core_rule"):                  # 执行器还没做过核心 ETF 的决策（新账本 / 从没决策过）：corefix_pending 是 {}，
        day = next_trading_day(next_trading_day(last))     # 盘中的路不排 → 第一次决策时照它排单（审查 promise F4；2026-10-16：以前说「马上」）
        if not ld and is_trading_day(today) and now.time() < CUTOFF:
            day = today                                     # 还没跑过：今天 07:40 的第一次运行
        while day < d:
            day = next_trading_day(day)
        return {"mode": "decision", "day": day, "intraday": False, "behind": False, "busy": False,
                "text": f"{day:%m/%d} 07:40 的决策 → {day:%m/%d} 09:00 开盘（执行器还没做过核心 ETF 的决策：第一次决策时照它排单）"}
    if mode == "now":
        return {"mode": "now", "day": today, "intraday": True, "behind": False, "busy": False,
                "text": "马上（盘中）按现价下单" + ("（模拟账户当场成交）" if paper else "")}
    if mode in ("open", "lunch"):
        at = "今天 09:00 开盘后" if mode == "open" else "12:30 后场开盘后"
        return {"mode": mode, "day": today, "intraday": True, "behind": False, "busy": False,
                "text": f"{at}马上（按现价限价，不是寄付）"}
    day = next_trading_day(next_trading_day(last))         # 下一次决策 = 上一次决策的 K 线之后那根的决策，成交日是再下一个交易日
    while day < d:                                         # 执行器几天没跑：下一次运行补到最新的 K 线
        day = next_trading_day(day)
    return {"mode": "decision", "day": day, "intraday": False, "behind": False, "busy": False,
            "text": f"{day:%m/%d} 07:40 的决策 → {day:%m/%d} 09:00 开盘"}


def _etf_slip(t: str) -> float:
    """核心 ETF 的滑点（比例；引擎 c_slip 同一个来源：qbreak/fees.etf_cost）。"""
    try:
        from .fees import DEFAULT_BROKER, etf_cost
        return float(etf_cost(DEFAULT_BROKER["JP"], t, "JP").get("slip_pct", 0.1)) / 100
    except Exception:                                       # noqa: BLE001
        return 0.001


def _plan_now(t, clear, units, tgt, px, lot, fx0, fx1, cash, eq, pct, hold, paper: bool, led: dict | None = None,
              busy=()) -> dict:
    """corefix_plan 的盘中那条路（执行器 now_phase 的 fix_buy / fund_src 同一个算法；D1，2026-10-15）：这只 现在 → 目标，先卖后买；
    买入（模拟账户按现价 + 滑点、立花按限价 现价 +0.5% 估；现价 = 最近收盘）钱不够（现金 ×(1 − 现金缓冲)）→ 别的不固定的核心 ETF
    大的先卖、按缺多少卖。凑钱的候选照 fund_src（2026-10-16 二次复核 F1：以前按含今天成交的口数、也算今天已经有单的）：
    led = 账本的口数（执行器的 cores）、今天已经有执行器的单的（busy）不拿来凑；现金 + 能卖的全卖也不够买 1 个单元 → 不下
    （later：今天有单的卖了才够 → 「今天已经有执行器的单」，否则「不够买 1 个单元」；下一次决策照它调）；卖了也不够全部 → 只买够的（fit）。"""
    moves, short, fit, later = [], 0, None, ""
    led = units if led is None else led
    cu, tg = units.get(t, 0), tgt.get(t)
    skipped = []
    if tg is not None and tg != cu and t in px:
        k = tg - cu
        main = {"t": t, "side": "BUY" if k > 0 else "SELL", "qty": abs(k), "px": px[t], "fixed": t in fx1, "fund": 0,
                "cur": cu, "tgt": tg, "rule": clear}
        moves.append(main)
        if k > 0:
            buf = 1 - CASH_BUF_PCT / 100
            up = px[t] * (1 + (_etf_slip(t) if paper else NOW_BUY_BUF))

            def need(q: int) -> float:
                return q * up + fee_jp(q * up)
            if need(k) > cash * buf:
                cand = sorted((u for u in px if u != t and u not in fx1 and int(led.get(u, 0) or 0) > 0),
                              key=lambda x: -int(led.get(x, 0)) * px[x])
                skipped = [u for u in cand if u in busy]
                cand = [u for u in cand if u not in busy]

                def full(u) -> float:
                    v = int(led[u]) * px[u] * (1 - _etf_slip(u))
                    return v - fee_jp(v)
                room = cash * buf + sum(full(u) for u in cand) * buf
                if need(lot[t]) > room:
                    bz = sum(int(led[u]) * px[u] for u in skipped)
                    later = ("凑钱要卖的核心 ETF " + "、".join(names.label(u) for u in skipped) + " 今天已经有执行器的单"
                             if skipped and need(lot[t]) <= room + bz * buf else "现金 + 不固定的核心 ETF 不够买 1 个单元")
                    moves = []
                else:
                    lack = need(k) / buf - cash                  # 卖出所得也要先扣缓冲（执行器 fund 的 short 同一个口径）
                    got = 0.0
                    for u in cand:
                        if lack <= 0:
                            break
                        net = px[u] * (1 - _etf_slip(u))
                        n = min(int(led[u]), int(math.ceil(lack / max(net * 0.995, 1e-9) / lot[u])) * lot[u])
                        if n <= 0:
                            continue
                        moves.append({"t": u, "side": "SELL", "qty": n, "px": px[u], "fixed": False, "fund": n, "cur": units.get(u, 0),
                                      "tgt": units.get(u, 0) - n, "rule": u in hold})
                        lack -= n * net - fee_jp(n * net)
                        got += n * net - fee_jp(n * net)
                    short = round(max(0.0, lack * buf))
                    q = k
                    while q > 0 and need(q) > (cash + got) * buf:
                        q -= lot[t]
                    if q < k:                                    # 执行器：「现金只够 q 口（还差…：下一次决策照它调）」
                        fit = max(0, q)
                        main["qty"] = fit
    return {"t": t, "clear": clear, "cur": cu, "target": tg, "old_fix": fx0.get(t), "moves": moves,
            "cash": round(cash), "short": short, "eq": eq, "pct": pct, "hold": hold, "busy": skipped, "fit": fit, "later": later}


def corefix_plan(book: dict | None, tag: str | None, rec: dict, sm: dict | None = None, stock_sells=(), intraday: bool = False,
                 now: dt.datetime | None = None) -> dict:
    """固定口数 / 恢复按规则写进去之后，下一次决策大概怎样排核心 ETF 的单（确认框、命令行用；只是预计）。
    照执行器的 _decide_core / _fund_fixed（qbreak/unified.py）粗算：核心 ETF 的钱 = (总权益 − 继续拿的个股) × 闲置资金比例；
    固定口数的先拿走它的金额（按收盘），剩下的给规则现在拿的、没固定的 ETF（汇总的 idle_cash.hold；几只时平分）；固定的正好调到那个口数，
    别的差额超过再平衡带（总权益的 10%）才调；固定的要买、钱不够 → 别的 ETF 再卖（最多卖到它们的目标；多卖跳空余量 3%）；
    恢复按规则的那只按规则自己的目标（core_rule.rule100 × 比例，与 corefix_clear_text 同一个数）。stock_sells：这次一起写的凑钱个股
    [(票, 股数, 价)]（下一次决策时已经卖掉）。价格 = 最近一次决策的收盘、现金 = 账本的 —— 规则的新仓 / 个股信号也会用钱，执行器按当时的数重新算。
    → {"t", "clear", "cur", "target", "old_fix", "moves": [{"t", "side", "qty", "px", "fixed", "fund"（其中为固定口数凑钱多卖的）, "cur", "tgt", "rule"}],
       "cash", "short"（这样卖了也还差的 円）, "eq", "pct", "hold"}
    intraday（D1；2026-10-15）：盘中 / 开盘后马上下的那条路（执行器 now_phase 的 fix_moves）—— 只调这一只到目标；买入钱不够 → 先卖别的
    （不固定的）核心 ETF 补足（按缺多少卖，大的先卖；不调到它们的规则目标），别的 ETF 的再平衡留给下一次决策。
    现在口数 / 个股 / 现金 / 权益 = 账本 + 今天已经成交的（live_ops.held_now；执行器的 fix_moves 同一个口径；下一次决策在对账之后，
    那时账本就是这个数 —— 2026-10-16 起两条路都用它，以前下一次决策的那条用旧口数、现金）。"""
    from . import live_ops as LO
    pj = LO.held_now(book, tag, now=now)
    st = pj["state"]
    cr = (book or {}).get("core_rule") or {}
    t, clear = str(rec.get("ticker")), bool(rec.get("clear"))
    fx0 = core_fixed(book, tag)
    fx1 = dict(fx0)
    if clear:
        fx1.pop(t, None)
    else:
        fx1[t] = int(rec.get("units") or 0)
    units = {u: int(n or 0) for u, n in (st.get("core_units") or {}).items()}   # 已含今天已成交的（held_now）
    px = {}
    for u in sorted(set(units) | set(cr.get("units100") or {}) | set(fx1) | {t}):
        p = float((cr.get("px") or {}).get(u) or (st.get("core_last") or {}).get(u) or 0)
        if p > 0:
            px[u] = p
    lot = {u: core_lot(book, u) for u in px}
    pend, sold = st.get("pending_exit") or {}, {}
    for s, n, _p in stock_sells:
        sold[s] = sold.get(s, 0) + int(n)
    stock_after = freed = 0.0                              # 继续拿的个股 / 那次决策之前卖掉的个股（规则在卖的 + 这次凑钱的）
    for s, p in (st.get("pos") or {}).items():
        sh, pp = int(p.get("shares") or 0), float(p.get("last_close") or p.get("entry_px") or 0)
        go = sh if s in pend else min(sh, sold.get(s, 0))
        stock_after += (sh - go) * pp
        freed += go * pp
    hist = st.get("history") or []
    cash = float(st.get("cash_jpy") or 0) + freed          # 投影的现金（含今天已成交）
    eq = (float(pj["equity"]) if pj.get("equity") is not None else
          float(hist[-1][1]) if hist else cash + stock_after + sum(units.get(u, 0) * px[u] for u in px))
    pct = core_pct_now(tag, book)
    pool = max(0.0, max(0.0, eq - stock_after) * pct / 100 - sum(n * px[u] for u, n in fx1.items() if u in px))
    ic = ((sm or {}).get("idle_cash") or {}).get("hold")
    if ic is None:                                         # 汇总没有（旧的）：最近一次决策的规则目标 > 0 的
        ic = ([u for u, n in (cr.get("units100") or {}).items() if int(n) > 0 and u not in fx0]
              + [u for u, n in (cr.get("rule100") or {}).items() if int(n) > 0])
    hold = [u for u in dict.fromkeys(ic) if u in px and u not in fx1]
    tgt, rule = {}, set()
    r100 = (cr.get("rule100") or {}).get(t)
    if clear and t in px and r100 is not None:             # 恢复按规则的那只：规则自己的目标 × 比例（执行器算好的；与 corefix_clear_text 同一个数）
        tgt[t] = int(math.floor(int(r100) * pct / 100 / lot[t] + 1e-9)) * lot[t]
        pool = max(0.0, pool - tgt[t] * px[t])
        hold = [u for u in hold if u != t]
        rule.add(t)
    for u in px:
        if u in tgt:
            continue
        if u in fx1:
            tgt[u] = int(fx1[u])
        elif u in hold:
            tgt[u] = int(math.floor(pool / len(hold) / px[u] / lot[u] + 1e-9)) * lot[u]
            rule.add(u)
        else:
            tgt[u] = 0
    if intraday:
        if clear and r100 is None:                         # 规则自己的目标执行器还没算过：盘中不调（执行器 fix_moves 同样）
            tgt.pop(t, None)
        led = {u: int(n or 0) for u, n in (((book or {}).get("state") or {}).get("core_units") or {}).items()}   # 执行器的 cores：账本
        busy = {str(o.get("ticker")) for o in orders_today(book, now or now_jst())}
        return _plan_now(t, clear, units, tgt, px, lot, fx0, fx1, cash, eq, pct, hold, str(tag or "").startswith("paper"),
                         led=led, busy=busy)
    band = float(cr.get("band_pct") or 10.0) / 100 * eq
    if abs(pct - float(cr.get("applied", pct))) > 1e-9:    # 比例改过、还没照新比例调过 → 那次直接调到目标（执行器 core_exact）
        band = 0.0
    od = {}
    for u in px:
        cu, tg, bd = units.get(u, 0), tgt[u], 0.0 if u in fx1 else band
        s = cu - tg if tg < cu and (tg == 0 or (cu - tg) * px[u] > bd) else 0
        b = tg - cu if tg > cu and (tg - cu) * px[u] > bd else 0
        od[u] = [s, b, 0]
    sl = {u: _etf_slip(u) for u in px}

    def net(u, n):
        return n * px[u] * (1 - sl[u]) - fee_jp(n * px[u] * (1 - sl[u])) if n > 0 else 0.0

    def cost(u, n):
        return n * px[u] * (1 + sl[u]) + fee_jp(n * px[u] * (1 + sl[u])) if n > 0 else 0.0

    def free():
        return cash + sum(net(u, v[0]) for u, v in od.items()) - sum(cost(u, v[1]) for u, v in od.items() if u not in fx1)
    want = sum(cost(u, od[u][1]) for u in fx1 if u in od)
    lack = (want - free()) * (1 + CORE_GAP_PCT / 100)
    if want > 0 and lack > 0:                              # 固定的要买、钱不够：别的（没固定的）ETF 再卖，最多卖到它们的目标（_fund_fixed）
        for u in sorted((u for u in od if u not in fx1), key=lambda x: -units.get(x, 0) * px[x]):
            room = units.get(u, 0) - tgt[u] - od[u][0]
            if room <= 0 or lack <= 0:
                continue
            n = min(room, int(math.ceil(lack / px[u] / lot[u])) * lot[u])
            while n < room and net(u, n) < lack:
                n += lot[u]
            od[u][0] += n
            od[u][2] += n
            lack -= net(u, n)
    moves = []
    for u in sorted(od, key=lambda x: (x != t, x)):
        s, b, f = od[u]
        if s or b:
            moves.append({"t": u, "side": "SELL" if s else "BUY", "qty": int(s or b), "px": px[u], "fixed": u in fx1, "fund": int(f),
                          "cur": units.get(u, 0), "tgt": tgt[u], "rule": u in rule})
    return {"t": t, "clear": clear, "cur": units.get(t, 0), "target": tgt.get(t), "old_fix": fx0.get(t), "moves": moves,
            "cash": round(cash), "short": round(max(0.0, want - free())) if want > 0 else 0, "eq": eq, "pct": pct, "hold": hold}


def _qpx(t: str, px: float, quotes: dict | None, now: dt.datetime, close_day) -> tuple[float, str]:
    """估金额用的价：现价（Yahoo 1 分钟线，约晚 20 分钟）有就用，没有 → 最近收盘。→ (价, 「Yahoo 10:12 的价」/「10/14 收盘」)。"""
    q = (quotes or {}).get(t) or {}
    try:
        p = float(q.get("px") or 0)
    except (TypeError, ValueError):
        p = 0.0
    if p > 0:
        at = str(q.get("at") or "")
        hm = (at[11:16] if at[:10] == now.date().isoformat() else f"{at[5:7]}/{at[8:10]} {at[11:16]}") if len(at) >= 16 else ""
        return p, f"Yahoo {hm + ' ' if hm else ''}的价，约晚 {DELAY_MIN} 分钟"
    return px, f"{str(close_day or '')[5:].replace('-', '/') or '最近'} 收盘"


def corefix_preview(book: dict | None, tag: str | None, rec: dict, now: dt.datetime, sm: dict | None = None, stock_sells=(),
                    quotes: dict | None = None, halt: bool = False, when: str | None = None) -> dict:
    """固定口数 / 恢复按规则的「确认下单」框（页面与命令行共用；2026-10-15）→ {"title", "text", "token", "danger", "plan", "fill"}：
    这只现在 → 目标口数、买 / 卖多少、估算金额（现价约晚 20 分钟；估算、税前）、现金够不够 / 不够卖哪几只多少、什么时候（corefix_fill：
    盘中马上 / 开盘后马上 / 那次决策；D1）、按什么价、固定之后一直有效直到「恢复按规则」、今天还挂着的单、HALT。
    盘中那条路（fill["intraday"]）的预计的单 = 执行器 now_phase 的 fix_moves（只调这只；钱不够先卖别的不固定的核心 ETF），
    同一只今天还没发出的核心单被这条取代、已经在交易所的先等它成交 / 撤掉（已知全部成交的不等：pj_done）；决策那条路 = 下一次决策预计排的单（照旧）。
    stock_sells：凑钱的个股 [(票, 股数, 价)]（写进去后按 when 卖出，不等那次决策）。quotes：{票: {"px", "at"}}（只影响金额的估算）。
    token：要写的东西（不含现价）→ 页面的「确认下单」带回来，服务器重算一样才写（账本 / 时间段变了 → 再确认一次）。"""
    import hashlib
    from . import live_ops as LO
    fill = corefix_fill(now, book, tag)
    nowp = bool(fill["intraday"])                         # 盘中 / 开盘后马上按现价下（D1）
    plan = corefix_plan(book, tag, rec, sm, stock_sells, intraday=nowp, now=now)
    st = (book or {}).get("state") or {}
    paper = str(tag or "").startswith("paper")
    t, cur, tg = plan["t"], plan["cur"], plan["target"]
    day = st.get("last_date")
    L = []
    k = (tg - cur) if tg is not None else 0
    act = (f"买入 {k:,} 口" if k > 0 else f"卖出 {-k:,} 口" if k < 0 else "口数不变")
    if plan["clear"]:
        title = f"确认下单：{names.label(t)} 恢复按规则"          # 票都写「代码 名字」（2026-10-15 用户：只写代码不知道是哪只）
        L.append(f"{names.label(t)}：取消手动固定" + (f" {int(plan['old_fix']):,} 口" if plan["old_fix"] is not None else "")
                 + (f" → 恢复按规则：预计 {cur:,} → {tg:,} 口（{act}）" if tg is not None else " → 恢复按规则（规则的目标执行器下一次决策才算）"))
    else:
        title = f"确认下单：{names.label(t)} 固定 {int(rec.get('units') or 0):,} 口"
        L.append(f"{names.label(t)}：现在 {cur:,} 口 → 固定 {int(rec.get('units') or 0):,} 口（{act}）"
                 + (f"；现在手动固定 {int(plan['old_fix']):,} 口" if plan["old_fix"] is not None else ""))
        if rec.get("from_kind"):
            L.append(f"你点的是「{LABEL.get(rec['from_kind'], rec['from_kind'])}」：这只是手动固定的 → 只改它的固定口数（别的 ETF 与闲置资金比例不变）")
    mv = {m["t"]: m for m in plan["moves"]}
    if k and t in mv:
        p, src = _qpx(t, mv[t]["px"], quotes, now, day)
        L.append(f"估算：{abs(k):,} 口 × 约 {yen_px(p)} ≈ ¥{abs(k) * p:,.0f}（{src}；估算、税前、不含手续费）")
    cday = str(day or '最近')[5:].replace('-', '/')
    if plan["moves"]:
        L.append(f"预计马上要下的核心 ETF 单（按 {cday} 收盘与账本现金粗算；下单时按现价重算）：" if nowp else
                 f"下一次决策预计排的核心 ETF 单（按 {cday} 收盘与账本现金粗算）：")
        for m in plan["moves"]:
            p, src = _qpx(m["t"], m["px"], quotes, now, day)
            sell = m["side"] == "SELL"
            if m["t"] == t:
                why = "恢复按规则" if plan["clear"] else "固定口数"
            elif nowp:
                why = f"给 {names.label(t)} 凑钱（现金不够；先卖、卖出的钱到了才买）"
            elif m["fixed"]:
                why = "这只是手动固定的"
            elif not m["rule"]:
                why = "规则现在不拿（熊市 / 换 ETF），不改也会卖"
            elif sell and m["fund"]:
                why = f"给 {names.label(t)} 腾钱（固定的金额先从闲置资金里拿走；钱不够再多卖 {m['fund']:,} 口）"
            elif sell:
                why = f"给 {names.label(t)} 腾钱（固定的金额先从闲置资金里拿走，剩下的才给它）"
            else:
                why = "多出来的闲置资金照规则买回"
            L.append(f"· {'卖出' if sell else '买入'} {names.label(m['t'])} 约 {m['qty']:,} 口（约 ¥{m['qty'] * p:,.0f}；"
                     f"{m['cur']:,} → {m['cur'] - m['qty'] if sell else m['cur'] + m['qty']:,} 口）：{why}")
        if nowp:
            L.append("别的 ETF 照规则的再平衡（再平衡带 / 闲置资金比例）留给下一次决策")
    elif nowp and tg is None:
        L.append("规则自己的目标执行器还没算过 → 盘中不调，下一次决策照规则")
    elif nowp and plan.get("later"):                       # 执行器 fix_buy：现金 + 能卖的核心 ETF 也不够买 1 个单元 → 这次不下（2026-10-16 二次复核 F1）
        L.append(f"这次不下：{names.label(t)} 要买 {k:,} 口，{plan['later']}（现金约 ¥{plan['cash']:,}）→ 下一次决策照它调")
    else:
        L.append("预计不用买卖核心 ETF（口数已经一样）" if nowp else "下一次决策预计不用买卖核心 ETF（差额在再平衡带以内 / 口数已经一样）")
    buy_fix = any(m["side"] == "BUY" and m["t"] == t for m in plan["moves"]) if nowp else \
        any(m["side"] == "BUY" and m["fixed"] for m in plan["moves"])
    if buy_fix:
        others = [m for m in plan["moves"] if m["side"] == "SELL" and not m["fixed"] and m["t"] != t]
        if nowp and plan.get("busy"):                      # 执行器 fund_src：今天已经有执行器的单的核心 ETF 不拿来凑钱
            L.append("、".join(names.label(u) for u in plan["busy"]) + " 今天已经有执行器的单 → 不拿来凑钱（同一只当天只下一笔）")
        if others:
            L.append(f"现金约 ¥{plan['cash']:,}：不够 → 执行器" + ("先卖" if nowp else "在那次决策里先卖") + "上面的 "
                     + "、".join(f"{names.label(m['t'])} 约 {m['qty']:,} 口" for m in others) + " 补足")
        elif plan["short"] > 0:
            L.append(f"现金约 ¥{plan['cash']:,}：不够，也没有别的（没固定的" + ("、今天没有单的" if nowp and plan.get("busy") else "")
                     + "）核心 ETF 可卖")
        else:
            L.append(f"现金约 ¥{plan['cash']:,}：够，不用卖别的 ETF")
        if nowp and plan.get("fit") is not None:           # 执行器 fix_buy：「现金只够 q 口（还差…：下一次决策照它调）」
            L.append(f"★ 现金只够约 {plan['fit']:,} 口（还差约 {k - plan['fit']:,} 口：下一次决策照它调）；"
                     "执行器下单时按当时的现价与现金再算")
        elif plan["short"] > 0:
            L.append(f"★ 这样卖了也还差约 ¥{plan['short']:,}：执行器"
                     + ("下单时按当时的现价与现金检查" if nowp else "开盘后按开盘价检查") + "、钱不够就少买（减口数）")
    if stock_sells:
        L.append(f"凑钱的个股（现在写进去、{when or when_for(now, book)}卖出，" + ("与这只 ETF 同一次运行、先卖）：" if nowp else "不等那次决策）：")
                 + "、".join(f"{names.label(s)} 卖 {int(n):,} 股（约 ¥{int(n) * float(p):,.0f}）" for s, n, p in stock_sells))
    L.append("什么时候：" + fill["text"])
    sells = any(m["side"] == "SELL" for m in plan["moves"])
    buys = any(m["side"] == "BUY" for m in plan["moves"])
    if (sells or buys) and nowp:                           # 盘中那条路：按现价（D1）；买入的限价上限 收盘 ×1.02（M14）
        up = (f"现价超过收盘 ×{CORE_BUY_LIMIT:g} → 这次不买，{RETRY_S // 60} 分钟后再试")
        if paper:
            L.append(f"按什么价：模拟账户按执行器下单那一刻的 Yahoo 现价（约晚 {DELAY_MIN} 分钟，含滑点）成交"
                     + (f"；买入{up}" if buys else "") + ("；先卖后买，钱不够少买" if sells and buys else ""))
        else:
            L.append("按什么价：立花在执行器下单那一刻取实时现价：" + "；".join(
                ([] if not sells else ["卖 = 限价 现价 −0.5%"])
                + ([] if not buys else [f"买 = 限价 min(现价 +0.5%, 收盘 ×{CORE_BUY_LIMIT:g})（{up}）"]))
                + ("；凑钱的卖单成交了才买（还没成交 → 等，" + f"{RETRY_S // 60} 分钟后再看）" if sells and buys else ""))
    elif sells or buys:
        if paper:
            L.append("按什么价：模拟账户按那天的开盘价（含滑点）成交" + ("；买入在卖出之后，钱不够少买" if sells and buys else ""))
        else:
            L.append("按什么价：" + "；".join(([] if not sells else ["卖 = 寄付成行（按开盘价）"])
                                              + ([] if not buys else [f"买 = 寄付指値 收盘 ×{CORE_BUY_LIMIT:g}（开盘价更高 → 寄付不成交）"
                                                                      + (f"；开盘前余力不够的部分（要等卖出的钱）在开盘后（09:05 / 09:20）按余力补下："
                                                                         f"当日限价 ≤ 收盘 ×{CORE_BUY_LIMIT:g}（不够减口数；不看开盘跳空，"
                                                                         "开盘价更高、盘中价格回落到限价以下仍可能成交）" if sells else "")])))   # live_unified._place_deferred（2026-10-15 复核）
    if plan["clear"]:
        L.append(f"之后这只 ETF 每天照规则（美股牛熊 / 股债相关 × 闲置资金比例 {plan['pct']:g}%）自动买卖")
    else:
        L.append(f"固定之后每天都调回 {int(rec.get('units') or 0):,} 口：不按规则（牛熊 / 股债相关）、不跟闲置资金比例自动调，"
                 "一直有效，直到点「恢复按规则」")
    live = [o for o in orders_today(book, now, open_only=True) if o.get("kind") == "core"]
    asked, unf = today_dead(book, tag, now) if live else (set(), {})
    if nowp:                                               # 盘中那条路：同一只今天的核心单 —— 没发出的被取代、在交易所的先等（D1）
        uns = [o for o in live if o.get("ticker") == t and o.get("status") in ("PLANNED", "DEFERRED")]
        dw, ws = _exch_words([o for o in live if o.get("ticker") == t and o not in uns and str(o.get("cid")) not in asked],
                             LO.held_now(book, tag, now=now))
        if uns:
            L.append("、".join(_order_word(o) for o in uns) + " 还没发出 → 被这条取代（执行器不再发）")
        if dw:
            L.append(dw)
        if ws:
            L.append(ws + " 已经在交易所 → 先等它成交 / 撤掉（「今天要成交的单」→ 撤单），再按成交后的口数调（一会儿再试）")
        live = [o for o in live if o.get("ticker") != t or str(o.get("cid")) in asked]
    dead = [o for o in live if str(o.get("cid")) in asked or str(o.get("cid")) in unf]   # 「交易」写「撤单中 / 不会下单（预计）」的：不写「照常」（2026-10-15 复核）
    live = [o for o in live if o not in dead]
    if live:
        L.append("今天还有执行器的单：" + "、".join(_order_word(o) + ("（开盘后钱够才下）" if o.get("status") == "DEFERRED" else "") for o in live)
                 + " → 照常（要不做：「今天要成交的单」→ 撤单）；成交的话" + ("执行器按成交后的口数算" if nowp else "下一次决策按成交后的口数再算"))
    if dead:
        L.append("今天的单里：" + "、".join(_order_word(o) + _dead_word(o, asked, unf) for o in dead))
    if halt:
        L.append(f"★ HALT 生效中：{HALT_CORE_MSG}")
    L.append("以上是预计：执行器下单时按当时的现价、现金重新算（规则的新仓 / 个股信号也会用钱）" if nowp else
             "以上是预计：执行器在那次决策按当时的收盘、现金重新算（规则的新仓 / 个股信号也会用钱）")
    key = {"t": t, "clear": plan["clear"], "units": rec.get("units"), "from": rec.get("from_kind"), "cur": cur, "old": plan["old_fix"],
           "later": plan.get("later") or "",
           "moves": [(m["t"], m["side"], m["qty"]) for m in plan["moves"]], "stocks": [(s, int(n)) for s, n, _p in stock_sells],
           "day": fill["day"].isoformat(), "behind": fill["behind"], "mode": fill["mode"], "halt": bool(halt)}
    token = hashlib.sha1(json.dumps(key, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return {"title": title, "text": "\n".join(L), "token": token, "danger": k < 0, "plan": plan, "fill": fill}


def _fix_rec(rec: dict, book: dict | None, t: str, held: int, fixed: int, eq: float | None = None, hd: str = "") -> dict:
    """固定口数的 ETF 的卖出全部 / 减仓 / 调仓 → 固定口数指令（kind corefix，units = 目标口数；from_kind 记原来点的是什么）。
    held / eq：含今天已成交（core_rec 给；不给 eq → 账本最近的总权益）；hd：说明里「现在 … 口」后面加的「（含今天已成交）」。"""
    k = rec["kind"]
    st = (book or {}).get("state") or {}
    lt = names.label(t)                                    # 给人看的「代码 名字」（2026-10-15）
    if k == "sell":
        if held <= 0 and fixed <= 0:
            raise ValueError(f"现在没有 {lt}（固定 0 口）")
        tg = 0
    else:
        cr = (book or {}).get("core_rule") or {}
        px = float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)
        hist = st.get("history") or []
        if eq is None:
            eq = float(hist[-1][1]) if hist else 0.0
        lot = core_lot(book, t)
        if px <= 0 or eq <= 0:
            raise ValueError(f"账本里没有 {lt} 的收盘价 / 总权益（执行器跑过一次之后再调）")
        if k == "trim":
            tg = int(math.floor(eq * float(rec["pct"]) / 100 / px / lot + 1e-9)) * lot
            if tg >= held:
                raise ValueError(f"{lt} 现在{hd}约占权益 {held * px / eq * 100:.1f}%，目标 {float(rec['pct']):g}% 不低于现在："
                                 "减仓只能减不能加（要加用「固定口数…」）")
        else:
            tg = target_shares(rec["unit"], rec["value"], eq, px, lot)
    if tg == fixed:
        raise ValueError(f"{lt} 已经固定 {fixed:,} 口：不用改（要按规则用「恢复按规则」）")
    out = {"kind": "corefix", "ticker": t, "units": int(tg), "from_kind": k, "source": rec.get("source") or "cli"}
    if rec.get("note"):
        out["note"] = rec["note"]
    return out


def core_pct_for(tg: int, u100: int, lot: int) -> float:
    """目标口数 → 闲置资金比例（%，两位小数）：取「规则目标 × 比例」按单元向下取整后正好是 tg 的最小比例（直接四舍五入可能少一个单元）。"""
    if u100 <= 0:
        return 0.0
    p = math.ceil(tg / u100 * 10000 - 1e-9) / 100
    if int(math.floor(u100 * p / 100 / lot + 1e-9)) * lot != tg:
        p = round(tg / u100 * 100, 2)
    return p


def core_rec(rec: dict, book: dict | None, tag: str | None = None, now: dt.datetime | None = None) -> dict | None:
    """持有的核心 ETF 的卖出全部 / 减仓 / 调仓 → 「闲置资金比例」指令（规则每天把核心 ETF 调回「目标额 × 比例」，
    只改这一次的单留不住）。比例 = 目标口数 ÷ 规则目标（比例 100% 时的口数）；对全部核心 ETF 一起生效。
    固定口数的 ETF → 改它的固定口数（corefix；卖出全部 = 固定 0 口；2026-10-13）。不是核心 ETF → None；调不了 → ValueError（说明）。"""
    t, k = rec.get("ticker"), rec.get("kind")
    if k not in POS_KINDS or not t or t not in core_tickers(book or {}):
        return None
    why = today_why(book, t, k, tag, now=now, rec=rec)     # 今天已经卖光的：不用再点（2026-10-16）
    if why:
        raise ValueError(why)
    from . import live_ops as LO                           # 口数 / 总权益含今天已成交（2026-10-16 二次复核：以前按账本 →「现在没有」「约占 0.0%」）：
    pj = LO.held_now(book, tag, now=now)                   # 固定口数在对账之后、或盘中按 账本 + 今天的成交（fix_prep）调；比例在对账之后的决策调
    held = int(((pj.get("state") or {}).get("core_units") or {}).get(t, 0))   # （今天有单的盘中不调：core_moves「今天已经有执行器的单」）
    hd = f"（{pj['head']}）" if pj.get("has") and t in (pj.get("by_ticker") or {}) else ""
    fixed = core_fixed(book, tag)
    if t in fixed:                                          # 固定口数的 ETF：只改它自己的固定口数（不换算成比例 → 别的 ETF 不跟着变；2026-10-13）
        return _fix_rec(rec, book, t, held, fixed[t], eq=float(pj["equity"]) if pj.get("has") and pj.get("equity") is not None else None,
                        hd=hd)
    lt = names.label(t)                                    # 给人看的「代码 名字」（2026-10-15）
    if k == "sell":                                         # 卖出全部 = 比例 0%：不用规则目标额（执行器还没算过也能卖）；之后停买，要你确认才买
        if held <= 0:
            raise ValueError(f"现在没有 {lt}")
        out = {"kind": "core", "pct": 0.0, "ticker": t, "target": 0, "source": rec.get("source") or "cli"}
        if rec.get("note"):
            out["note"] = rec["note"]
        return out
    c = core_info(book, t, pj)
    if c is None or c["cur"] <= 0:
        raise ValueError(f"现在没有 {lt}（或闲置资金比例改过、执行器还没算过它的目标额：下一次运行之后再调）")
    if c["selling"]:
        raise ValueError(f"规则这次在卖 {lt}（熊市 / 换了 ETF）：开盘卖出，不用调")
    if c["px"] <= 0:
        raise ValueError(f"账本里没有 {lt} 的收盘价（执行器跑过一次之后再调）")
    if k == "trim":
        tg = int(math.floor(c["eq"] * float(rec["pct"]) / 100 / c["px"] / c["lot"] + 1e-9)) * c["lot"] if c["eq"] > 0 else 0
        if tg >= c["cur"]:
            raise ValueError(f"{lt} 现在{hd}约占权益 {c['cur'] * c['px'] / c['eq'] * 100:.1f}%，目标 {float(rec['pct']):g}% 不低于现在："
                             "减仓只能减不能加（要加用「调仓」）")
    else:
        tg = target_shares(rec["unit"], rec["value"], c["eq"], c["px"], c["lot"])
    tg = min(tg, c["u100"])
    out = {"kind": "core", "pct": core_pct_for(tg, c["u100"], c["lot"]), "ticker": t, "target": tg,
           "source": rec.get("source") or "cli"}
    if rec.get("note"):
        out["note"] = rec["note"]
    return out


DEAD_BUY = ("SKIPPED", "BLOCKED", "EXPIRED", "REJECTED", "CANCELLED", "MISSED", "UNFILLED")   # 开盘的买单这样结束（一股没成交）= 今天不会再买


def plan_live(plan, orders, d) -> set:
    """计划里的个股买入（规则的新仓 / 早上的手动买入）去掉「这次决策的买单都结束了、一股没成交」的（跳空 / 被挡 / 失效…：今天不会再买）
    → 还算「排在开盘买入」、还占名额的票（G14；2026-10-14：以前开盘被跳过的新仓到第二天对账前一直占着名额、挡着同一只的手动买入）。
    orders：执行器的单（ExecOrder 或账本里的 dict）；d：决策日；还没有单的照算（还没下）。页面、命令行、执行器盘中共用。"""
    def g(o, k):
        return o.get(k) if isinstance(o, dict) else getattr(o, k, None)
    dead: dict = {}
    for o in orders or []:
        if g(o, "decided_on") != d or g(o, "side") != "BUY" or g(o, "kind") != "stock" or g(o, "phase") == "now":
            continue
        t = g(o, "ticker")
        dead[t] = dead.get(t, True) and g(o, "status") in DEAD_BUY and int(g(o, "filled_qty") or 0) <= 0
    return {t for t in plan or {} if not dead.get(t, False)}


def live_plan(book: dict | None) -> set:
    """账本的开盘计划里还算数的买入（plan_live；页面 / 命令行用）。"""
    st = (book or {}).get("state") or {}
    return plan_live(st.get("plan") or {}, list((book or {}).get("orders") or []), st.get("last_date"))


def slots(book: dict, tag: str | None = None, going=None, now: dt.datetime | None = None, with_today: bool = False) -> dict:
    """个股名额的估算（页面 / 命令行；执行器在决策时按当时的持仓再算）：下一次决策时还拿着的（不算排在开盘卖出、
    有卖出全部 / 减到 0 指令的、going 里这次就要卖到 0 的）+ 已经排定的买入（规则的计划 + 手动买入指令）→ {"held", "buys", "used", "max", "free"}（with_today=True 时再加 "today"）。
    开盘的买单已经结束、一股没成交的计划不算（live_plan；2026-10-14 G14）。
    含今天已知的成交（live_ops.held_now；2026-10-16 复核）：今天买进的个股算拿着（不再同时算进排定买入）；今天卖光的个股 —— 现在写的指令在
    对账之后执行（收盘后 / 周末，pre_reconcile 为假）→ 不算，成交日当天盘中 / 开盘前写的 → 执行器当时按账本看、照算。
    today = 今天的成交让数字和只看账本时不一样（页面写「（含今天已成交）」）；head = 那句的写法（成交日不是今天 →「含 10/16（周五）已成交」）。"""
    from . import live_ops as LO
    now = now or now_jst()
    st = (book or {}).get("state") or {}
    man = (book or {}).get("manual") or {}
    waiting = unseen(tag, book) if tag else []
    live = _live(man.get("items") or {}, waiting, ORDER_KINDS)
    pos, pend = st.get("pos") or {}, st.get("pending_exit") or {}
    gone = {r.get("ticker") for r in live if _to_zero(r)} | set(going or ())
    plan = live_plan(book)
    ibuy = {r.get("ticker") for r in live if r.get("kind") == "buy"}

    def count(have: set) -> tuple[int, int]:
        h = [t for t in have if t not in pend and t not in gone]
        return len(h), len(({t for t in plan if t not in have} | ibuy) - have)

    h0, b0 = count(set(pos))                               # 只看账本
    pj = LO.held_now(book, tag, now=now)
    bt = pj.get("by_ticker") or {}
    have = set(pos) | {t for t in pj.get("new") or [] if (bt.get(t) or {}).get("kind") == "stock"}
    if not pre_reconcile(pj, now):
        have -= set(pj.get("sold_out") or [])
    nh, nb = count(have)
    mx = int(man.get("max_positions") or MAX_POS)
    out = {"held": nh, "buys": nb, "used": nh + nb, "max": mx, "free": max(0, mx - nh - nb)}
    if with_today:
        out["today"] = (nh, nb) != (h0, b0)
        out["head"] = pj.get("head") or LO.hn_head(pj.get("day_word"))   # 「含今天已成交」/「含 10/16（周五）已成交」（周末 / 早上的运行之前）
    return out


def core_pct_now(tag: str | None, book: dict | None) -> float:
    """现在的闲置资金比例（%）：执行器还没读的比例指令算最新的（已经点了撤回的不算）。0 = 停买闲置资金 ETF。"""
    waiting = unseen(tag, book) if tag else []
    late = [r for r in waiting if r.get("kind") == "core" and r["id"] not in cancelled(waiting) and not r.get("fund_for")]   # 整批的比例等决策才生效
    return float(late[-1]["pct"]) if late else float(((book or {}).get("manual") or {}).get("core_pct", 100.0))


LEG_REASONS = {"buy": ("manual_buy",), "sell": ("manual",), "add": ("manual_add",), "trim": ("manual_trim",)}


def _placed_filled(it: dict, book: dict | None, pj: dict | None = None) -> bool:
    """已下单（placed）的手动买卖指令今天已经全部成交 → 下一次对账时执行器把它记成完成（Manual.on_fill / settle），
    对账之后执行的新指令不会被它挡（check 的「已经有一条没处理完的手动指令」、fund_all 的「有没处理完的指令」、fund_holdings 的 busy
    都不算它；只在 not pre_reconcile 时用；2026-10-16 二次复核 F2 的买入 → 四次复核推广到卖出 / 减仓 / 调仓）。
    全部成交 = pj_done（账本 FILLED，或 held_now 已知的成交 ≥ 发出数：立花的寄付单对账前整天是 SENT、成交只有快照知道）：
      卖出 / 减仓 / 调到 0：含今天已成交的持仓里这只已经没了（settle：持仓没了 → 完成），而且这只没有还在等成交 / 结果不明的单；
      减仓 / 调仓往下（manual.trims）：当前决策里它的 manual_trim 单都全部成交、合计 ≥ 计划要卖的股数（只成交了一段不算）；
      买入 / 调仓往上（manual.buys / adds）：当前决策里它的 manual_buy / manual_add 单都全部成交（on_fill：有成交就完成）。
    部分成交 / SENDING / ERROR / 算不成 → False（照旧算没处理完）。"""
    k = it.get("kind")
    if k not in ORDER_KINDS or it.get("status") != "placed" or it.get("cancel_req") or not (pj or {}).get("has"):
        return False
    t = it.get("ticker")
    if not t or t in {p.get("ticker") for p in (pj or {}).get("pending") or []}:
        return False
    st = (book or {}).get("state") or {}
    man = (book or {}).get("manual") or {}
    led = st.get("pos") or {}
    if k in POS_KINDS and t in led and t not in (((pj or {}).get("state") or {}).get("pos") or {}):
        return True                                        # 今天已经卖光（settle：持仓没了 → 完成）
    mine = lambda key: ((man.get(key) or {}).get(t) or {}).get("id") == it.get("id")   # noqa: E731
    if k == "buy":
        leg, need = "buy", 0
    elif k in ("trim", "adjust") and mine("trims"):
        leg, need = "trim", int(((man.get("trims") or {}).get(t) or {}).get("shares") or 0)
    elif k == "adjust" and mine("adds"):
        leg, need = "add", 0
    else:                                                  # 卖出全部还拿着一部分 / 找不到它的那一段 → 没处理完
        return False
    d = st.get("last_date")
    os_ = [o for o in (book or {}).get("orders") or [] if o.get("decided_on") == d and o.get("ticker") == t
           and o.get("reason") in LEG_REASONS[leg]]
    got = pj_got(pj)
    if not os_ or not all(pj_done(o, pj, got) for o in os_):
        return False
    return sum(int(o.get("sent_qty") or o.get("qty") or 0) for o in os_) >= need


def _settled_later(items: list[dict], book: dict | None, pj: dict | None, now: dt.datetime) -> list[dict]:
    """去掉今天已经全部成交、对账时就完成的指令（_placed_filled）—— 只在现在写的会在对账之后执行时（not pre_reconcile）；
    成交日当天对账之前执行的照旧都算（执行器当天按账本看、同一只不再下第二笔）。"""
    if pre_reconcile(pj, now):
        return list(items)
    return [r for r in items if not _placed_filled(r, book, pj)]


def check(rec: dict, book: dict, tag: str | None = None, sm: dict | None = None, now: dt.datetime | None = None, going=None) -> str | None:
    """下指令时对着执行器账本看一眼（页面 / 命令行用；执行器下单前还会按最新的收盘再查一次）：不行 → 理由；行 → None。
    tag：账本标签（给了就连指令文件里执行器还没读的指令一起看，避免同一只票点两次）。
    sm：执行器的汇总（给了就看「建议的股票」里这只票的资格检查：被挡的不让写）。"""
    st = (book or {}).get("state") or {}
    waiting = unseen(tag, book) if tag else []
    pos = st.get("pos") or {}
    man = (book or {}).get("manual") or {}
    items = man.get("items") or {}
    k = rec["kind"]
    t = rec.get("ticker")
    lt = names.label(t) if t else ""                       # 理由里写「代码 名字」（用户手输代码时回显名字，输错也看得出；2026-10-15）
    why = today_why(book, t, k, tag, now=now, rec=rec)     # 今天已成交、还没对账的票（2026-10-16）
    if why:
        return why
    if k in ORDER_KINDS:                                   # 存在性 / 在卖按含今天已成交的持仓（today_why 挡掉了当天对账前执行、结果不一样的；
        from . import live_ops as LO                       # 其余的投影与执行时的持仓一样；2026-10-16 二次复核：周末 / 盘后写今天买进的卖出）
        pj_ = LO.held_now(book, tag, now=now)
        pst = pj_["state"]
        pos = pst.get("pos") or {}
        if k == "buy":
            if t in pos:
                return f"{lt} 已经持有：要加仓用「调仓」"
            if t in core_tickers(book):
                return f"{lt} 是核心 ETF：不能手动买（用「闲置资金比例」调）"
            if t in live_plan(book):                       # 开盘被跳过 / 被挡、一股没买的不算（G14；2026-10-14）
                return f"{lt} 已经排在开盘买入（规则的信号），不用再点"
        else:
            if t not in pos:
                return f"执行器的账本里没有 {lt} 这只持仓（核心 ETF 用「闲置资金比例」调）"
            why = (pst.get("pending_exit") or {}).get(t)
            if why and not (rec.get("batch") == "all" and k == "sell" and why != "manual"):   # 「全部换成」同批：规则在卖的也写（执行时只设不买回，2026-10-13）
                return f"{lt} 已经在卖出全部（{_exit_text(why)}），不用再点"
        act = [r for r in _live(items, waiting, ORDER_KINDS) if r.get("ticker") == t]
        act = _settled_later(act, book, pj_, now or now_jst())   # 今天已经全部成交的手动指令：对账时先记成完成，之后才执行这条
        #                                                          （二次复核 F2 的买入；四次复核：卖出 / 减仓 / 调仓、写买入也一样）
        if act:
            return f"{lt} 已经有一条没处理完的手动指令（{act[-1].get('id')}）：先撤回它，或等它完成"
    if k == "buy":
        row = next((r for r in ((sm or {}).get("suggest") or {}).get("rows") or [] if r.get("ticker") == t), None)
        rb = (row or {}).get("buy") or {}
        hard = rb.get("block")
        if hard and (rb.get("block_kind") == "manual" or str(hard).startswith("手动卖出后不")) and (
                t in lifting(tag, book) or t not in (man.get("blocks") or {})):
            hard = None                                    # 「建议的股票」是上一次决策时的：不买回已经在解除 / 已经没了 → 不挡（执行器下单前按最新的再查；2026-10-13）
        if hard:
            return f"{lt} 不能买：{hard}"
        if rec.get("fund") != "all":                     # 「全部换成 X」还没下单：这只会在同一次决策里买进、执行时不卖（2026-10-14）
            la = [r for r in live_allin(tag, book) if r.get("ticker") != t and r.get("status", "pending") != "placed"]
            if la:
                return (f"「全部换成 {names.label(la[0]['ticker'])}」在等决策：{lt} 会和它在同一次决策里买进、留着不卖（和只拿那一只矛盾）"
                        "→ 先撤回那条，或等它做完再买")
        s = slots(book, tag, going, now=now)               # going：这次提交同时要卖到 0 的票（「其他全部卖出」）
        if s["free"] <= 0:
            return (f"个股名额已满（拿着 {s['held']} 只 + 排定买入 {s['buys']} 只，上限 {s['max']} 只）：要买先卖出一只"
                    "（卖出先处理，再处理买入）")
    if k in ("trim", "adjust"):                            # 差额按含今天已成交的持仓（执行器在对账之后按实际持仓执行；2026-10-16）
        from . import live_ops as LO
        pst = LO.held_now(book, tag, now=now)["state"]
    if k == "trim":
        cur = position_pct(pst).get(t)
        if cur is not None and rec["pct"] >= cur:
            return f"{lt} 现在约占权益 {cur:.1f}%，目标 {rec['pct']:g}% 不低于现在：减仓只能减不能加（要加用「调仓」）"
    if k == "adjust":
        a = adjust_plan(rec, pst, MANUAL_CAP_PCT)
        if a["px"] <= 0 or a["eq"] <= 0:
            return f"账本里没有 {lt} 的收盘价 / 总权益（执行器跑过一次之后再调）"
        if a["want"] == a["cur"]:
            return f"{lt} 现在 {a['cur']:,} 股，目标 {fmt_target(rec)} 换算也是 {a['want']:,} 股：不用调"
        if a["want"] > a["cur"] and a["delta"] <= 0:
            return f"{lt} {cap_text(a['cur'], a['px'], a['eq'], a['cap_pct'], LOT)}"
    if k in ("core", "corefix") and not rec.get("fund_for"):   # 在 corefix 的「恢复按规则」提前返回之前（2026-10-13）
        la = allin_busy_text(live_allin(tag, book))      # 已下单 / 还在等决策 分开说（2026-10-14）
        if la:
            return la
    if k == "corefix":
        if t not in core_tickers(book):                    # 核心 ETF 有十几只：列前 6 只 +「等 N 只」
            return f"{lt} 不是核心 ETF（核心：{names.labels(sorted(core_tickers(book)), limit=6) or '—'}）"
        fix = (man.get("core_fix") or {})
        if rec.get("clear"):
            return None if t in fix else f"{lt} 本来就是按规则（没有固定口数）"
        lot = core_lot(book, t)
        if lot > 1 and int(rec["units"]) % lot:
            return f"{lt} 的单元是 {lot:,} 口：口数要是 {lot:,} 的倍数"
        c = core_info(book, t) or {}
        px, eq = float(c.get("px") or 0), float(c.get("eq") or 0)
        if px > 0 and eq > 0 and int(rec["units"]) * px > eq * 1.001:
            n = int(rec["units"])
            return names.qty(t, f"{n:,} 口约 ¥{n * px:,.0f}，超过总权益 ¥{eq:,.0f}")
    if k == "core":
        cur = core_pct_now(tag, book)
        if abs(float(rec["pct"]) - cur) < 0.005:
            if t and cur <= 0:
                return f"已经在停买闲置资金 ETF（比例 0%）：{lt} 在执行器下一次运行时卖出"
            return (f"{lt} 换算成闲置资金比例还是 {cur:g}%：不用调" if t else f"闲置资金比例现在就是 {cur:g}%：不用改")
    if k == "cancel_order":                                # 单号（cid）原样，前面写是哪只（2026-10-15）
        from .live_ops import cancel_why
        o = next((x for x in (book or {}).get("orders") or [] if x.get("cid") == rec["cid"]), None)
        if o is None:
            return f"账本里没有 {lt} 的单 {rec['cid']}（已经对账过了？）"
        why = cancel_why(o, book, now or now_jst(), str(tag or "").startswith("paper"))
        if why:
            return f"{lt} 的单 {rec['cid']} 撤不了：{why}"
        from . import live_ops as LO
        why = LO.cancel_conflict(rec, book, LO.cancel_jobs(book, waiting, now or now_jst()))   # 同一组同时只有一个撤单（简化 2026-10-16）：
        if why:                                            # 还在处理的撤单（账本里 pending / 还没读的）盖着这一组 → 先拒绝，等它结束再撤
            return why
        if rec.get("grp"):                                 # 整组撤单（2026-10-16）：同一组的每一笔都要在账本里、在服务器算出的这一组里
            orders = [x for x in (book or {}).get("orders") or [] if isinstance(x, dict)]
            by = {str(x.get("cid")): x for x in orders}
            mem = {str(x.get("cid")) for x in LO.group_members(o, orders, book)}   # 含靠这一组卖单的钱、已经发出的买单（复核 6）
            for c in rec["grp"]:
                mg = _CID.match(str(c))
                lc = names.label(mg.group(3)) if mg else ""
                if c not in by:
                    return f"同一组的单 {lc} {c} 账本里没有（页面是旧的？刷新再点）"
                if c not in mem:
                    return f"{lc} 的单 {c} 不在 {lt} 这一组里：没写"
    if k == "unblock":                                     # 2026-10-13：同一只不重复写；页面过时（设定换了）不写
        return unblock_why(t, book, tag, rec.get("block_id"))
    if k == "uncancel":
        return _uncancel_why(rec["target"], items, waiting, book=book, tag=tag, sm=sm, now=now)
    if k == "cancel":
        tg0 = items.get(rec["target"]) or next((r for r in waiting if r.get("id") == rec["target"]), None)
        if tg0 is not None and tg0.get("kind") == "cancel_order":   # 撤回撤单（2026-10-16 事后）：只在执行器读到之前
            return withdraw_order_why(tg0, items, waiting, tag)
        if tg0 is not None and allin_member(tg0) and tg0.get("kind") != "buy":
            b0 = batch_buy(tg0, list(items.values()) + waiting)
            if b0 is not None and (b0.get("status") in ACTIVE or b0["id"] not in items) and b0["id"] not in cancelled(waiting) \
                    and not b0.get("cancel_req"):
                return f"这是「全部换成 {names.label(tg0['fund_for'])}」的同批指令：撤回买入那条（整批一起撤）"
        return _cancel_why(rec["target"], items, waiting, now=now)
    return None


def group_prune(r: dict, book: dict | None, now: dt.datetime | None, paper: bool, waiting=()) -> tuple[dict, list[str]]:
    """整组撤单（grp；2026-10-16）写进去之前：去掉同一组里现在撤不了（live_ops.grp_why）的单 →（记录, 说明）。
    只防页面过期（你点的时候能撤、现在不能了）；执行器撤的时候按重算的整组再判断一次（先撤买单、确认没成交再撤卖单）。
    账本里找不到的不在这里去掉（check 会说「页面是旧的」）；同一组已经有撤单在处理 → 不去掉，交给 check 整条拒绝（同一组同时只有一个撤单）。
    全都去掉了 → ValueError（不写：只撤主单要你再点一次「撤单」）。"""
    g = list((r or {}).get("grp") or [])
    if not g:
        return r, []
    from . import live_ops as LO
    now = now or now_jst()
    by = {str(x.get("cid")): x for x in (book or {}).get("orders") or [] if isinstance(x, dict)}
    if LO.cancel_conflict(r, book, LO.cancel_jobs(book, waiting, now)):   # 同一组已经有撤单在处理：不去掉什么，交给 check 说理由
        return r, []
    keep, notes = [], []
    for c in g:
        o = by.get(str(c))
        if o is None:
            keep.append(c)
            continue
        why = LO.grp_why(o, book, now, paper)
        if why is None:
            keep.append(c)
            continue
        side = "买" if o.get("side") == "BUY" else "卖"
        notes.append(f"{side} {names.label(o.get('ticker'))}（{c}）现在撤不了：{why}")
    if not keep:
        raise ValueError("同一组的其他单现在都撤不了（" + "；".join(notes) + "）：没写。只撤这一笔：刷新页面后点「撤单」")
    out = dict(r)
    out["grp"] = keep
    return out, notes


def order_started(it: dict | None) -> bool:
    """撤单的运行已经在做这条撤单指令了吗（发了撤单、在等立花确认买单的撤单：grp_wait / recheck_at…；命令行 --group 直接建的也是）。
    撤单的运行在运行锁里读、做、记结果，一次做完；没做完的才留下这些「等」字段。"""
    it = it or {}
    return any(it.get(k) for k in ("grp_wait", "grp_wait0", "recheck_at", "grp_legacy", "grp_all"))


def withdraw_order_why(r: dict, items: dict, waiting: list[dict], tag: str | None = None) -> str | None:
    """一条撤单指令（cancel_order）能不能撤回（2026-10-16 事后）：撤单的运行还没做它（执行器还没读 / 别的运行读了、还没轮到撤单的运行）、
    执行器也没在运行 → 能（撤回之后那笔单不再算「撤单中」，执行器照常发 / 照常挂着）。撤单的运行已经在做（发到立花、在等确认）/ 做完了、
    执行器正在运行（可能正在撤）、已经在撤回中 → 不能。执行器读撤回的时候再看一次（Manual.ingest：那时撤单已经开始做 → 这条撤回拒绝、不动撤单）。"""
    rid = str(r.get("id") or "")
    what = target_text(rid, r)
    it = items.get(rid)
    if it is not None and it.get("status") not in ACTIVE:
        return f"{what} 已经是「{status_text(it)}」，撤回不了"
    if it is not None and order_started(it):
        return (f"{what} 撤单的运行已经在撤（已经发到立花、在等立花确认），撤回不了：撤掉的单不会恢复，"
                "要的话重新下买卖指令")
    if rid in cancelled(waiting):
        return f"{what} 已经在撤回中"
    if tag:
        try:
            from .live_unified import lock_held
            busy = lock_held(paths.state_dir() / f"live_unified_{tag}.lock")
        except Exception:                                   # noqa: BLE001  看不了锁：当成在运行（撤回是可选的，撤单照做更安全）
            busy = True
        if busy:
            return (f"执行器正在运行（可能正在撤 {what}），现在撤回不了：等它跑完刷新页面再看"
                    "（多半已经撤了；还没撤的话再撤回）")
    return None


def withdrawn_orders(waiting: list[dict], items: dict | None = None) -> set:
    """被撤回、撤单的运行还没做的撤单指令（指令文件里还没读、没被撤销的撤回指着它；撤单指令还没读，或读了、还没开始撤）→ {撤单指令 id}：
    执行器读到撤回时不撤、页面 / 发单前的保护 / 对账都不再算「撤单中」（2026-10-16 事后）。"""
    gone = cancelled(waiting)
    out = {r.get("id") for r in waiting if r.get("kind") == "cancel_order" and r.get("id") in gone}
    for k, it in (items or {}).items():
        if (k in gone and isinstance(it, dict) and it.get("kind") == "cancel_order" and it.get("status") == "pending"
                and not order_started(it)):
            out.add(k)
    return out


def _cancel_why(target: str, items: dict, waiting: list[dict], now: dt.datetime | None = None) -> str | None:
    """一条指令本身能不能撤回（不看整批规则）。盘中已下单的按 now_cancel_why（15:30 之后失效的盘中卖出可以撤回；G16）。"""
    if True:
        it = items.get(target)
        if it is None:
            if target in cancelled(waiting):              # 指令 id 后面写撤的是什么（只写 id 看不出是哪只；2026-10-15）
                return f"指令 {target_text(target, next((r for r in waiting if r.get('id') == target), None))} 已经在撤回中"
            if any(r["id"] == target for r in waiting):
                return None
            return f"没有指令 {target}"
        if it.get("status") not in ACTIVE:
            return f"指令 {target_text(target, it)} 已经是「{status_text(it)}」，撤不了"
        if it.get("cancel_req"):
            return f"指令 {target_text(target, it)} 已经在撤回中"
        if it.get("now") and it.get("status") == "placed":
            return now_cancel_why(it, now or now_jst())
    return None


def _uncancel_why(cid: str, items: dict, waiting: list[dict], book: dict | None = None, tag: str | None = None,
                  sm: dict | None = None, now: dt.datetime | None = None) -> str | None:
    """「撤销撤回」能不能做：撤回还没被执行器读 → 能；读了 → 原来的买卖指令被它撤成「已撤回」或标着「撤回中」才能恢复
    （闲置资金比例 / 固定口数 / 解除不买回 读到时就定了，撤销不了）。原来那只票现在有别的指令在处理 → 不行（同一只票同时只能一条）。
    给了 book（2026-10-13）：撤回之后同一只票又写过别的买卖指令 → 不行（恢复旧的会盖掉之后的决定）；凑钱的卖出现在已经不卖了 → 不行；
    「全部换成 X」按现在的账本重查（fund_all 被挡 / X 已经持有 / 买入本身的检查 / 撤回之后又做过别的「全部换成」→ 请重新提交）。"""
    c = items.get(cid) or next((r for r in waiting if r.get("id") == cid), None)
    if c is None or c.get("kind") != "cancel":
        return f"没有撤回指令 {cid}"
    if cid in voided(waiting) or c.get("status") == "voided":
        return "这条撤回已经撤销过了"
    tid = c.get("target")
    tg = items.get(tid) or next((r for r in waiting if r.get("id") == tid), None)
    if tg is None:
        return f"找不到它撤回的指令 {tid}"
    if tg.get("kind") == "cancel_order":                   # 撤单的撤回（2026-10-16 事后）：恢复撤单不走这里
        return "撤单的撤回撤销不了：还要撤这笔单，请重新点「撤单」"
    if cid in items:                                       # 执行器已经读了这条撤回
        ok = (tg.get("status") == "cancelled" and tg.get("kind") in ORDER_KINDS) or tg.get("cancel_req") == cid
        if not ok:
            return f"这条撤回已经处理完（原来的指令：{status_text(tg) if tg.get('status') else '—'}），撤销不了：要的话重新下一次指令"
    if tg.get("kind") in ORDER_KINDS and tg.get("ticker"):
        others = [r for r in _live(items, waiting, ORDER_KINDS) if r.get("ticker") == tg["ticker"] and r.get("id") != tid]
        if others:
            return f"{names.label(tg['ticker'])} 现在已经有别的指令在处理（{describe(others[0])}）：先撤回那条"
    if tg.get("kind") == "unblock":                        # 同一只已经有别的解除在等执行器读（2026-10-13）：恢复这条会重复
        gone = cancelled(waiting)
        if any(r.get("kind") == "unblock" and r.get("ticker") == tg.get("ticker") and r["id"] != tid and r["id"] not in gone for r in waiting):
            return f"{names.label(tg.get('ticker'))} 已经有别的解除在等执行器读：不用恢复这条"
    allr = list(items.values()) + [r for r in waiting if r["id"] not in items]
    if allin_member(tg) and tg.get("kind") != "buy":       # 「全部换成」的同批：只能整批跟着买入那条一起恢复（split 的凑钱卖出可以单独恢复）
        return f"这是「全部换成 {names.label(tg.get('fund_for'))}」的同批指令：要恢复请撤销买入那条的撤回（整批一起）"
    if tg.get("fund") == "all":
        others = [r for r in live_allin_recs(items, waiting) if r.get("id") != tid]
        if others:
            return f"「全部换成 {names.label(others[0]['ticker'])}」还在处理：同时只能有一个「全部换成」"
    comps = fund_companions(tg, allr) if tg.get("fund") in ("split", "all") else []
    ids = {tid} | {cp["id"] for cp in comps}
    st = (book.get("state") or {}) if book is not None else None
    if book is not None:                                   # 2026-10-13：撤回之后这只票又有过别的指令 / 凑钱的卖出已经不卖了 → 不恢复
        w = _later_why(tg, c, allr, ids) or (_fund_sell_why(tg, st) if batch_buy(tg, allr) is None else None)
        if w:
            return w
    if tg.get("fund") in ("split", "all"):                 # 买入那条：同批的撤回也都要能撤销，否则整个不行
        void = voided(waiting)
        for cp in comps:
            cc = next((x for x in allr if x.get("kind") == "cancel" and x.get("target") == cp["id"] and x["id"] not in void
                       and x.get("status") != "voided"), None)
            if cc is None:
                continue
            w = _uncancel_why_one(cc["id"], items, waiting, ids, st=st if tg.get("fund") == "split" else None)
            if w:
                return f"同批的「{describe(cp)}」的撤回撤销不了（{w}）→ 要的话重新提交一次"
    if book is not None and tg.get("kind") == "buy" and tg.get("fund") == "all":
        w = _allin_recheck(tg, ids, allr, items, waiting, book, tag, sm, now)
        if w:
            return f"「全部换成 {names.label(tg.get('ticker'))}」按现在的账本重新检查没通过（{w}）：请重新提交「全部换成」"
    return None


def _later_why(tg: dict, c: dict, allr: list[dict], skip=()) -> str | None:
    """撤回（c）之后，同一只票又写过别的买卖指令（不管状态；同批的不算）→ 恢复旧的会盖掉之后的决定（2026-10-13）。"""
    t = tg.get("ticker")
    if tg.get("kind") not in ORDER_KINDS or not t:
        return None
    ca, skip = str(c.get("at") or ""), set(skip) | {tg.get("id")}
    later = [r for r in allr if r.get("kind") in ORDER_KINDS and r.get("ticker") == t and r.get("id") not in skip
             and str(r.get("at") or "") > ca]
    return f"撤回之后 {names.label(t)} 已经有过别的指令（{later[0]['id']}）：请重新下" if later else None


def _fund_sell_why(tg: dict, st: dict | None) -> str | None:
    """凑钱的卖出（adjust 带 fund_for）恢复之前看现在的持仓（2026-10-13）：已经不拿 / 现在已经不高于目标 → 恢复了也不会卖（绝不改成买入）。"""
    if st is None or tg.get("kind") != "adjust" or not tg.get("fund_for"):
        return None
    t = tg.get("ticker")
    cur = int(((st.get("pos") or {}).get(t) or {}).get("shares") or 0)
    if cur <= 0:
        return f"{names.label(t)} 现在已经不持有：凑钱的卖出用不上"
    want = adjust_plan(tg, st, MANUAL_CAP_PCT)["want"]
    if want >= cur:
        return f"{names.label(t)} 现在 {cur:,} 股，已经不高于凑钱卖出的目标 {want:,} 股：恢复了也不会卖"
    return None


def _as_cancelled(book: dict, ids) -> dict:
    """账本的一个看法：ids 这几条当作已撤回（撤销撤回前按现在的账本重查「全部换成」用；不改原来的账本）。"""
    man = book.get("manual") or {}
    items = {k: ({**v, "status": "cancelled"} if k in ids else v) for k, v in (man.get("items") or {}).items()}
    return {**book, "manual": {**man, "items": items}}


def _allin_recheck(tg: dict, ids, allr: list[dict], items: dict, waiting: list[dict], book: dict, tag: str | None,
                   sm: dict | None, now: dt.datetime | None) -> str | None:
    """「全部换成 X」撤销撤回之前按现在的账本重查（2026-10-13）：X 已经持有 / 撤回之后又做过别的「全部换成」/ fund_all 被挡
    （持仓上有别的没处理完的指令、有还没读的固定口数）/ 买入本身过不了 check（名额、资格 …）→ 理由。执行时拿着的都卖、比例 0%、
    取消全部固定口数（Manual._allin_sweep / _allin_apply_core），所以写入之后多拿的票不用在这里比。"""
    X = tg.get("ticker")
    if X in (((book.get("state") or {}).get("pos")) or {}):
        return f"{names.label(X)} 现在已经持有"
    gone = cancelled(waiting)
    later = [r for r in allr if r.get("kind") == "buy" and r.get("fund") == "all" and r.get("id") not in ids
             and str(r.get("at") or "") > str(tg.get("at") or "")
             and (r.get("status") in ("done", "placed", "pending") if r["id"] in items else r["id"] not in gone)]
    if later:
        return f"撤回之后已经有过「全部换成 {names.label(later[0].get('ticker'))}」（{later[0]['id']}）"
    view = _as_cancelled(book, ids)                        # 同批自己（还在撤回中）不算「别的指令」
    fa = fund_all(view, tag, X, now=now)
    if fa["blocked"]:
        return fa["blocked"]
    rec = {k: tg[k] for k in ("kind", "ticker", "unit", "value", "pct", "fund") if k in tg}
    return check(rec, view, tag, sm=sm, now=now, going={t for t, _c, _p in fa["sells"]})


def live_allin_recs(items: dict, waiting: list[dict]) -> list[dict]:
    return [r for r in _live(items, waiting, ("buy",)) if r.get("fund") == "all"]


def _uncancel_why_one(cid: str, items: dict, waiting: list[dict], batch_ids=(), st: dict | None = None) -> str | None:
    """一条撤回自己能不能撤销（不看同批规则）；它恢复的那只票现在有别的指令（同批以外）在处理 → 不行。
    st（平摊凑钱的同批才给；2026-10-13）：撤回之后这只票又写过别的指令 / 凑钱的卖出现在已经不卖了（不拿 / 不高于目标）→ 不行。"""
    c = items.get(cid) or next((r for r in waiting if r.get("id") == cid), None)
    if c is None or c.get("kind") != "cancel":
        return f"没有撤回指令 {cid}"
    if cid in voided(waiting) or c.get("status") == "voided":
        return "已经撤销过"
    tid = c.get("target")
    tg = items.get(tid) or next((r for r in waiting if r.get("id") == tid), None)
    if tg is None:
        return f"找不到它撤回的指令 {tid}"
    if cid in items:
        ok = (tg.get("status") == "cancelled" and (tg.get("kind") in ORDER_KINDS or tg.get("fund_for"))) or tg.get("cancel_req") == cid
        if not ok:
            return f"已经处理完（原来的指令：{status_text(tg) if tg.get('status') else '—'}）"
    if tg.get("kind") in ORDER_KINDS and tg.get("ticker"):
        busy = [r for r in _live(items, waiting, ORDER_KINDS) if r.get("ticker") == tg["ticker"] and r.get("id") not in set(batch_ids) | {tid}]
        if busy:
            return f"{names.label(tg['ticker'])} 现在已经有别的指令在处理（{describe(busy[0])}）：先撤回那条"
    if st is not None:
        allr = list(items.values()) + [r for r in waiting if r["id"] not in items]
        return _later_why(tg, c, allr, batch_ids) or _fund_sell_why(tg, st)
    return None


NOW_NO_CANCEL = ("盘中的单已经发到交易所，撤回指令撤不了：用面板「今天要成交的单」的「撤单」撤（已经成交的部分撤不了），"
                 "或在立花网站 / 手机网站撤")
NOW_FILLED_NO_CANCEL = ("盘中的单已经全部成交，撤不了（下一次早上的对账之后这条完成；收盘后〔15:25 起〕写这只的新指令不用等它，"
                        "对账之后执行）")                   # 四次复核：以前写「明天早上」（周五 / 连休前不对），也没说之后能直接写
NOW_BUY_LAPSED = "盘中的买单已在 15:30 失效（没成交的部分不会再买）：下一次早上的对账之后这条指令结束，不用撤"
NOW_SELL_WITHDRAWN = "盘中的单已在 15:30 失效 → 下一次开盘不再卖（下一次早上的对账之后结束；已经成交的部分照记）"


def now_sell_withdrawn(it: dict) -> str:
    """15:30 失效的盘中卖出撤回之后怎样（G16 复核，2026-10-14：以前写「明天 / 今天」，第二天早上、周末看就不对）：按下单那天写。"""
    d = mmdd(it.get("fill_day"))
    return f"{d} 盘中的单已在 15:30 失效：撤回之后下一次开盘不再卖（下一次早上的对账之后结束；{d} 已经成交的部分照记）"


def now_expired(it: dict, now: dt.datetime) -> bool:
    """盘中下的单（now）在交易所已经失效：当日限り → 成交日早于今天，或就是今天、已过 15:30（G16；2026-10-14）。"""
    fd = str(it.get("fill_day") or "")
    if not fd:
        return False
    today = now.date().isoformat()
    return fd < today or (fd == today and now.time() >= CANCEL_UNTIL)


def now_cancel_why(it: dict, now: dt.datetime) -> str | None:
    """盘中已下单的指令能不能撤回（G16；2026-10-14：以前 15:30 之后这里叫你用「撤单」、「撤单」又说已收盘不用撤，
    没成交的手动卖出第二天开盘照样再卖、撤不掉）：交易时间里单还挂在交易所 → NOW_NO_CANCEL（用「撤单」）；
    全部成交了 → 撤不了；15:30 之后单已失效 → 卖出可以撤回（明天不再卖，对账之后生效；到下一次决策之前都行），
    买入不用撤（对账之后结束、不会再买）。不是盘中已下单的 → None。"""
    if not (it.get("now") and it.get("status") == "placed"):
        return None
    if int((it.get("fill") or {}).get("qty") or 0) >= int(it.get("shares") or 0) > 0:
        return NOW_FILLED_NO_CANCEL
    if not now_expired(it, now):
        return NOW_NO_CANCEL
    if it.get("side") == "BUY":
        return NOW_BUY_LAPSED
    return None


RULE_TEXT = "盘中点的马上下单；开盘前、午休点的等开盘；收盘后点的等下一个交易日开盘"


def timing(now: dt.datetime) -> tuple[str, dt.date]:
    """现在点下去什么时候下单：("now", 今天) 盘中 → 马上；("open", 今天) 开盘前 → 今天开盘；("lunch", 今天) 午休 → 12:30 后场开盘；
    ("next", 下一个交易日) 收盘后（15:25 起）/ 休市日 → 下一个交易日开盘。"""
    d, t = now.date(), now.time()
    if is_trading_day(d):
        if t < SESSION[0][0]:
            return "open", d
        if any(a <= t < b for a, b in SESSION):
            return "now", d
        if t < SESSION[1][0]:
            return "lunch", d
    return "next", next_trading_day(d)


OPEN_NOW_TXT = "今天 09:00 开盘后马上（按现价，不是寄付）"   # 寄付截止（08:55）〜09:00 写的：赶不上寄付，开盘后第一次盘中运行按现价下


def when_text(now: dt.datetime) -> str:
    """一句话：马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘。
    08:55〜09:00（D7 / M19；2026-10-15）：寄付已经截止，开盘后由盘中的路按现价下 →「今天 09:00 开盘后马上（按现价，不是寄付）」
    （以前写「今天 09:00 开盘」，读起来像寄付）。"""
    mode, d = timing(now)
    if mode == "open" and now.time() >= CUTOFF:
        return OPEN_NOW_TXT
    return {"now": "马上（盘中）", "open": "今天 09:00 开盘", "lunch": "12:30 后场开盘"}.get(mode) or f"{d:%m/%d} 开盘"


def morning_behind(book: dict | None, now: dt.datetime) -> bool:
    """交易日、执行器账本的上一次决策（state.last_date）还在前一个交易日之前 = 今天早上的运行还没完成（与 now_due / 执行器 now_phase
    同一个判断：这时盘中的路不下单，等早上的运行先处理）。没有账本 / 账本里没有决策日（还没跑过）→ False（照常的说法）。"""
    st = (book or {}).get("state") or {}
    ld = str(st.get("last_date") or "")
    return bool(ld) and is_trading_day(now.date()) and ld < prev_trading_day(now.date()).isoformat()


def when_for(now: dt.datetime, book: dict | None, ticker: str | None = None) -> str:
    """when_text 加上「今天早上的运行还没完成」（G9；2026-10-14）：盘中 / 午休点的，但今天早上的运行还没完成（Mac 07:40 睡着、
    运行失败…）→ 不是马上：补跑早上的运行之后才下（模拟账户：面板会自动补跑；立花：只按定时任务 / 你说再跑），没补跑 → 下一个交易日开盘。
    ticker：这只今天已经有执行器还活着的单（busy_today；D4，2026-10-15）→ 盘中不下第二笔：下一个交易日开盘。
    面板的「现在点买卖 → …」、确认框、提交后的提示、命令行同一句。"""
    mode, d = timing(now)
    late_open = mode == "open" and now.time() >= CUTOFF
    if (mode in ("now", "lunch") or late_open) and morning_behind(book, now):
        return f"补跑早上的运行之后（今天早上的运行还没完成；没补跑 → {next_trading_day(d):%m/%d} 开盘）"
    if mode == "open" and now.time() >= RUN_AT and morning_behind(book, now):   # 开盘前也看（M19；2026-10-15：以前照写「今天 09:00 开盘」）
        return (f"今天早上的运行完成之后（{RUN_AT:%H:%M} 的运行还没完成：完成了 → 今天 09:00 开盘；"
                f"08:55 之前没完成 → 补跑之后，没补跑 → {next_trading_day(d):%m/%d} 开盘）")
    if ticker and (mode in ("now", "lunch") or late_open) and busy_today(book, ticker, now):
        return f"{next_trading_day(d):%m/%d} 开盘（{names.label(ticker)} 今天已经有执行器的单：同一只当天只下一笔）"
    return when_text(now)


def allin_fill(now: dt.datetime, book: dict | None, tag: str | None = None) -> dt.date:
    """「全部换成这只」整批实际在哪天开盘做：下一次决策 = 上一次决策的 K 线（state.last_date）之后那根 K 线的决策，成交日是再下一个交易日；
    那天已经过了寄付截止（08:55）/ 执行器正在跑（这次读不到）→ 再往后一个交易日。祝日 / 年末年始前后也对。"""
    st = (book or {}).get("state") or {}
    try:
        last = dt.date.fromisoformat(str(st.get("last_date"))[:10])
    except (TypeError, ValueError):
        last = prev_trading_day(now.date())
    fill = next_trading_day(next_trading_day(last))
    busy = False
    if tag:
        try:
            from .live_unified import lock_held
            busy = lock_held(paths.state_dir() / f"live_unified_{tag}.lock")
        except Exception:                                   # noqa: BLE001
            busy = False
    while fill < now.date() or (fill == now.date() and (now.time() >= CUTOFF or busy)):
        fill = next_trading_day(fill)
    return fill


def allin_when(now: dt.datetime, book: dict | None, tag: str | None = None) -> str:
    """allin_fill 的文字：今天 → 「今天 09:00 开盘」；否则「MM/DD 开盘」。"""
    f = allin_fill(now, book, tag)
    return "今天 09:00 开盘" if f == now.date() else f"{f:%m/%d} 开盘"


def uncancel_when(tg: dict | None, now: dt.datetime, book: dict | None, tag: str | None = None) -> str:
    """撤销撤回之后，恢复的指令什么时候、按什么价处理（面板确认框的 data-when 与 uncancel_request 的说明同一句；2026-10-13）：
    「全部换成 X」→ allin_when 那次决策整批先卖后买（卖出那时拿着的全部；列出现在拿着的）；买卖 → 和新写一条一样
    （盘中马上按现价下单、午休等后场、开盘前 / 收盘后等开盘：order_basis）；比例 → 读到就生效；固定口数 → corefix_fill（D1）；解除 → 下一次决策起。"""
    tg = tg or {}
    k, t = tg.get("kind"), tg.get("ticker")
    st = (book or {}).get("state") or {}
    if k == "buy" and tg.get("fund") == "all":             # 票都写「代码 名字」（2026-10-15）
        held = [names.qty(x, f"{int(p.get('shares') or 0):,} 股") for x, p in sorted((st.get("pos") or {}).items())
                if x != t and int(p.get("shares") or 0) > 0]
        held += [names.qty(x, f"{int(u):,} 口") for x, u in sorted((st.get("core_units") or {}).items()) if int(u or 0) > 0]
        return (f"{allin_when(now, book, tag)}整批先卖后买（那次决策先过闸门）：卖出那时拿着的 {names.label(t)} 以外的全部个股和 ETF"
                f"（现在：{'、'.join(held) if held else '没有别的'}）、闲置资金比例 0%、取消全部固定口数")
    if k in ORDER_KINDS:
        side = "BUY" if k == "buy" else "SELL"
        if k == "adjust" and not tg.get("fund_for"):
            try:
                d = int(tg.get("dir") or 0) or adjust_plan(tg, st, MANUAL_CAP_PCT)["delta"]
            except (KeyError, TypeError, ValueError):
                d = 0
            side = "BUY" if d > 0 else "SELL"
        mode = timing(now)[0]
        if mode in ("now", "lunch") and morning_behind(book, now):       # 今天早上的运行还没完成：不是马上（G9；2026-10-14）
            return (f"{when_for(now, book)}下单：" + order_basis(str(tag or "").startswith("paper"), now, side)
                    + ("（凑钱的卖出同一时间先卖）" if k == "buy" and tg.get("fund") == "split" else ""))
        out = ("马上（盘中）下单：" if mode == "now" else "") + order_basis(str(tag or "").startswith("paper"), now, side)
        return out + ("（凑钱的卖出同一时间先卖）" if k == "buy" and tg.get("fund") == "split" else "")
    if k == "core":
        return f"执行器读到就生效：核心 ETF {when_for(now, book)}照新比例调"
    if k == "corefix":                                     # 与新写一条一样的时段口径（D1；2026-10-15：以前一律「下一次决策起」）
        return "照它调：" + corefix_fill(now, book, tag)["text"]
    if k == "unblock":
        return next_decision(now)
    return "执行器下一次运行时处理"


def next_window(now: dt.datetime) -> tuple[dt.date, bool]:
    """现在点下去哪一天下单：(日期, 是不是今天)。交易日 15:25 之前 → 今天；之后 / 休市日 → 下一个交易日。"""
    mode, d = timing(now)
    return d, mode != "next"


def due(tag: str, book: dict | None, now: dt.datetime | None = None) -> bool:
    """今天开盘之前还来得及寄付（交易日、08:55 之前）、而且有要变成寄付单的手动指令（还没读的卖出 / 减仓 / 调仓 / 撤回，或读了还在等的；
    等 09:00 开盘的买入 / 加仓不算）→ 早上的运行已经完成时，重试（08:35 / 页面）要再跑一次，把它加进今天开盘的单。"""
    now = now or now_jst()
    if not is_trading_day(now.date()) or now.time() >= CUTOFF or paths.halt_file().exists():
        return False                                        # HALT 时不算（与 now_due 相同；重试在 HALT 中本来就什么都不做 → 2026-10-14 复核：
    #                                                         以前面板 07:45〜08:55 每 3 分钟叫一次什么都不做的 --retry）
    if any(r["kind"] in POS_KINDS + ("cancel", "uncancel") and not allin_member(r) for r in unseen(tag, book)):
        return True
    items = ((book or {}).get("manual") or {}).get("items") or {}
    today = now.date().isoformat()
    return any((it.get("status") == "pending" and it.get("kind") in POS_KINDS and not it.get("wait")
                and it.get("hold") != today and not allin_member(it))       # 「全部换成」整批只在决策里做：补单不处理它（2026-10-13 修：以前每 3 分钟叫一次）
               or (it.get("status") == "placed" and it.get("cancel_req")) for it in items.values())


def cancel_due(tag: str, book: dict | None, now: dt.datetime | None = None) -> bool:
    """有要执行器撤的单（执行器还没读的撤单指令，或读了还在等的）、而且是交易日 15:30 之前 → 面板叫执行器跑一次 --phase cancel
    （开盘前 / 盘中都可以，不看「今天早上的运行完成没有」；HALT 时也叫：撤单只会减少风险）。"""
    now = now or now_jst()
    if not is_trading_day(now.date()) or now.time() >= CANCEL_UNTIL:
        return False
    w = unseen(tag, book)
    items = ((book or {}).get("manual") or {}).get("items") or {}
    gone = withdrawn_orders(w, items)                      # 撤回了的撤单：不为它叫（2026-10-16 事后）
    if any(r["kind"] == "cancel_order" and r["id"] not in gone for r in w):
        return True
    return any(it.get("kind") == "cancel_order" and it.get("status") == "pending" and _recheck_due(it, now) and k not in gone
               for k, it in items.items())


def _recheck_due(it: dict, now: dt.datetime) -> bool:
    """整组撤单在等立花确认买单的撤单（recheck_at；2026-10-16）：到了这个时刻才再跑一次 --phase cancel（不每 30 秒抢着跑、把盘中 / 开盘后的运行饿着）；
    没有 / 读不了 → 算到了。"""
    v = it.get("recheck_at")
    if not v:
        return True
    try:
        t = dt.datetime.fromisoformat(str(v))
        if t.tzinfo is None:
            t = t.replace(tzinfo=JST)
        n = now if now.tzinfo else now.replace(tzinfo=JST)
        return t <= n
    except (TypeError, ValueError):
        return True


def grp_wait_stale(it: dict | None, now: dt.datetime) -> bool:
    """还在等立花确认买单撤单的整组撤单（grp_wait）已经过了那天的收盘（15:30 之后 / 开始等的那天已过）→ True：今天没成交的单都已失效，
    不再等（cancel_book 不吵地结束它、面板不再显示「撤单中」；复核 2026-10-16：以前等到第二天 00:00 才处理、还推一条 ★ 说买单还挂着）。"""
    if not isinstance(it, dict) or not it.get("grp_wait"):
        return False
    try:
        t = dt.datetime.fromisoformat(str(it.get("grp_wait0") or it.get("recheck_at") or ""))
    except (TypeError, ValueError):
        return False
    t = t.astimezone(JST) if t.tzinfo else t.replace(tzinfo=JST)
    n = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    return t.date() != n.date() or n.time() >= CANCEL_UNTIL


def core_pending(book: dict | None, now: dt.datetime | None = None) -> float | None:
    """闲置资金比例改了（manual.core_pct）、核心 ETF 还没照它调（≠ core_rule.applied）→ 新比例（%）；否则 None。与执行器的 _core_pending
    同一个判断（now_due 也用这一个；复核 3，2026-10-16 抽出来：「交易」的「还没照它调」那一行、持仓的「还没照它调完」照它写）：
      now 没给 = 下一次决策会不会照新比例调（执行器还没算过规则目标额 units100 → 上一次决策的比例 = 100%）；
      now 给了 = 盘中那条路（now_phase）会不会调：有 units100 → 规则目标额是上一次决策算的（decided_on = last_date）；没有 → 手上有核心 ETF
        （或排着核心的单）才调（卖出全部照样卖）；今天已经说了「下一次决策再调」（core_rule.defer = 今天）→ 不算。
    盘中照新比例的单没成交完、下一次决策再调（core_rule.redo）不在这里（那几笔单在「交易」照常显示）。只读。"""
    b = book or {}
    cr = b.get("core_rule") or {}
    st = b.get("state") or {}
    want = float((b.get("manual") or {}).get("core_pct", 100.0))
    if cr.get("units100"):
        if now is not None and cr.get("decided_on") != st.get("last_date"):
            return None
        pend = abs(want - float(cr.get("applied", cr.get("pct", want)))) > 1e-9
    else:                                                   # 执行器还没算过规则目标额：卖出全部（比例 0%）照样卖；别的比例按估算的目标调（core_u100s）
        pend = abs(want - float(cr.get("applied", 100.0))) > 1e-9
        if pend and now is not None:
            pend = any(int(u) > 0 for u in (st.get("core_units") or {}).values()) or bool(st.get("core_plan"))
    if not pend or (now is not None and cr.get("defer") == now.date().isoformat()):
        return None
    return want


def core_applied(book: dict | None) -> float:
    """核心 ETF 上一次照它调的闲置资金比例（%）= core_pending 拿来比的那个数（core_rule.applied；有 units100 → 没记就是 pct；
    执行器还没算过规则目标额 → 100%）。「交易」里「还没照它调」的比例那一行的「撤回：比例改回 X%」用（2026-10-17：改回它 = core_pending 不再成立，
    下一次运行不照新比例调）。只读。"""
    b = book or {}
    cr = b.get("core_rule") or {}
    want = float((b.get("manual") or {}).get("core_pct", 100.0))
    try:
        if cr.get("units100"):
            return float(cr.get("applied", cr.get("pct", want)))
        return float(cr.get("applied", 100.0))
    except (TypeError, ValueError):
        return 100.0


def core_wait(book: dict | None, tag: str | None = None, waiting=None) -> dict | None:
    """读了、还没照它调的闲置资金比例（core_pending）→ {"pct": 新比例, "item": 最新生效的那条比例指令（执行器 now_phase 写说明的那一条：
    状态完成、按写入时刻最后的；没有 → None）}；没有 / 指令文件里还有没读的比例指令（读到就换成它，「交易」里是那一行）→ None。
    waiting：没读的指令（None = 给了 tag 就读指令文件）。「交易」的 core: 那一行、那条指令的「生效中 · 还没照它调」用（复核 3，2026-10-16：
    以前读了之后指令「完成」、收进「已结束」，数字少 1，HALT 解除后照样马上卖 —— 与固定口数的 FIX_WAIT 同一个处理）。只读。"""
    pct = core_pending(book)
    if pct is None:
        return None
    if waiting is None:
        waiting = unseen(tag, book) if tag else []
    gone = cancelled(waiting)
    void = voided(waiting)
    if any(isinstance(r, dict) and r.get("kind") == "core" and not r.get("fund_for") and r.get("id") not in gone
           and r.get("id") not in void for r in waiting):
        return None
    done = sorted((it for it in ((((book or {}).get("manual") or {}).get("items")) or {}).values()
                   if isinstance(it, dict) and it.get("kind") == "core" and it.get("status") == "done"), key=lambda x: x.get("at", ""))
    return {"pct": pct, "item": done[-1] if done else None}


def now_due(tag: str, book: dict | None, now: dt.datetime | None = None) -> bool:
    """盘中（timing = now）、今天早上的运行已经完成、有要马上下的手动指令（执行器还没读的买卖，或读了还在等的；
    「明天再处理」的、RETRY_S 秒内试过的不算；HALT 时不算）→ 面板叫执行器跑一次 --phase now。
    固定口数（D1；2026-10-15）：执行器还没读的 corefix（「全部换成」的同批除外），或固定口数 ≠ 最近一次照它排了单的口数
    （corefix_pending；core_rule.fix_tried 的 RETRY_S 退避、fix_defer「下一次决策再调」与比例同一个口径）也算。"""
    now = now or now_jst()
    if timing(now)[0] != "now" or paths.halt_file().exists():
        return False
    st = (book or {}).get("state") or {}
    if str(st.get("last_date") or "") < prev_trading_day(now.date()).isoformat():
        return False                                        # 今天早上的运行还没完成（它会先处理这些指令）
    cr = (book or {}).get("core_rule") or {}
    if any(r["kind"] in ORDER_KINDS + ("core", "uncancel")
           or (r["kind"] == "corefix" and not r.get("fund_for") and cr)   # 没有 core_rule → 执行器盘中不排（corefix_pending {}），等第一次决策
           for r in unseen(tag, book)):
        return True
    today = now.date().isoformat()
    if corefix_pending(book, tag, now):                     # 固定口数改了、还没照它调（与执行器 now_phase 的 fix_moves 同一个判断；D1）
        try:
            age = (now - dt.datetime.fromisoformat(str(cr["fix_tried"]))).total_seconds() if cr.get("fix_tried") else None
        except (TypeError, ValueError):
            age = None
        if age is None or age >= RETRY_S:
            return True
    if core_pending(book, now) is not None:                 # 改了闲置资金比例、还没照它调（与执行器的 _core_pending 同一个判断）
        try:
            age = (now - dt.datetime.fromisoformat(str(cr["tried"]))).total_seconds() if cr.get("tried") else None
        except (TypeError, ValueError):
            age = None
        if age is None or age >= RETRY_S:
            return True
    for it in (((book or {}).get("manual") or {}).get("items") or {}).values():
        if it.get("status") != "pending" or it.get("kind") not in ORDER_KINDS or it.get("hold") == today:
            continue
        try:
            age = (now - dt.datetime.fromisoformat(str(it["tried"]))).total_seconds() if it.get("tried") else None
        except (TypeError, ValueError):
            age = None
        if age is None or age >= RETRY_S:
            return True
    return False


def rolled_over(it: dict, now: dt.datetime) -> dt.date | None:
    """盘中试过、没下成（取不到现价 / 早上的运行还没完成 / 这次运行不下单…：tried）、那天的盘中已经结束（15:25 起）的买卖指令 →
    接下来哪天开盘处理（那天早上的决策照常把它变成寄付单）；不是这种 → None（G18；2026-10-14：以前收盘后还写「10 分钟后再试」）。
    HALT 中等着的、「明天开盘」（hold）、等上一笔 / 等开盘（wait）、「全部换成」整批不算；那天的开盘也过了（早上的运行没跑）→ None。"""
    if (it.get("status") != "pending" or it.get("kind") not in ORDER_KINDS or not it.get("tried") or it.get("hold")
            or it.get("wait") or allin_member(it) or str(it.get("msg") or "").startswith(HALT_WAIT_MSG)):
        return None
    try:
        d = dt.datetime.fromisoformat(str(it["tried"])).date()
    except (TypeError, ValueError):
        return None
    if now.date() < d or (now.date() == d and now.time() < SESSION[1][1]):
        return None
    nd = next_trading_day(d)
    if now.date() > nd or (now.date() == nd and now.time() >= CUTOFF):
        return None
    return nd


def rolled_text(it: dict, now: dt.datetime) -> str | None:
    """rolled_over 的状态文字：「今天盘中没下成 → 10/15 开盘（寄付）」（前一天试的写「10/14 盘中没下成 → …」）。"""
    nd = rolled_over(it, now)
    if nd is None:
        return None
    d = dt.datetime.fromisoformat(str(it["tried"])).date()
    return ("今天" if d == now.date() else f"{d:%m/%d} ") + f"盘中没下成 → {nd:%m/%d} 开盘（寄付）"


_RETRY_TAIL = re.compile(r"[，,：:；;]?\s*\d+ 分钟后再试")


def now_lapsed(it: dict, now: dt.datetime | None) -> bool:
    """盘中已下单、没全部成交、单已在交易所失效（当日限り：15:30 之后 / 之后的日子；还没到下一次早上的对账）（G16 复核，2026-10-14）。"""
    return (now is not None and it.get("status") == "placed" and bool(it.get("now")) and now_expired(it, now)
            and int((it.get("fill") or {}).get("qty") or 0) < int(it.get("shares") or 0))


def msg_text(it: dict, now: dt.datetime | None = None) -> str:
    """页面 / 日志显示的说明：盘中已经结束、改到开盘的（rolled_over）去掉「N 分钟后再试」（G18）；
    盘中的单已失效、还没对账的（now_lapsed）按下单那天说清之后怎样（以前一直写「已下单，等成交（今天有效）」；G16 复核）。
    以前存下的 msg 里只有代码（「等 6758.T 的上一笔成交」）→ 显示时过 names.annotate 补名字（只是显示，账本里的 msg 不改；
    id / cid / 命令行不动；2026-10-15 用户：只写代码不知道是哪只）。"""
    m = names.annotate(str(it.get("msg") or ""))
    if now_lapsed(it, now) and not it.get("cancel_req"):
        d, q, n = mmdd(it.get("fill_day")), int((it.get("fill") or {}).get("qty") or 0), int(it.get("shares") or 0)
        part = f"（成交 {q:,} / {n:,} 股）" if q > 0 else ""
        if it.get("side") == "BUY":
            return f"{d} 盘中的买单已在 15:30 失效{part}：没成交的部分不会再买，下一次早上的对账之后这条指令结束"
        return f"{d} 盘中的卖单已在 15:30 失效{part}：没卖掉的部分下一次开盘再卖（不想再卖就撤回）"
    return _RETRY_TAIL.sub("", m) if now is not None and rolled_over(it, now) else m


def hold_text(it: dict, now: dt.datetime) -> str:
    """「明天再处理」（hold = 那天：这只那天已经有执行器的单）的指令哪天开盘处理（页面的状态；复核 2026-10-16：以前不看日子一律「明天开盘」——
    前一天 hold 的在今天 07:00 的「今天要成交的单」里写「明天开盘」，周五 hold 的在「另有 1 条等 10/19（周一）开盘」里也写「明天开盘」）：
      HALT 中 → 「等下单」（解除后照原样执行：行的说明写着）；
      hold 在今天之前、今天是交易日：08:55 之前 →「今天开盘」（今天早上的运行 / 08:35 的重试把它排进今天开盘的单：hold 只管那一天）；
        过了 08:55 还是 hold（今天早上的运行没完成）→「等下单」（模拟账户补跑之后盘中下 / 立花下一个交易日：行的说明与分块写着）；
      别的 → 下一个交易日：明天 →「明天开盘」，不是明天 →「10/19（周一）开盘」（与「另有 … 等 10/19（周一）开盘」同一个写法：live_ops.md_wd）。"""
    from .live_ops import md_wd
    if paths.halt_file().exists():
        return STATUS["pending"]
    d = now.date()
    try:
        h = dt.date.fromisoformat(str(it.get("hold"))[:10])
    except ValueError:
        h = d
    if h < d and is_trading_day(d):
        return "今天开盘" if now.time() < CUTOFF else STATUS["pending"]
    nd = next_trading_day(d)
    return "明天开盘" if nd == d + dt.timedelta(days=1) else f"{md_wd(nd)}开盘"


def status_text(it: dict, now: dt.datetime | None = None) -> str:
    """指令的状态（页面 / 日志）：盘中的单分「盘中已成交 / 盘中已下单」（now 给了、单已在 15:30 失效 →「盘中的单已失效」；G16 复核）；
    明天再处理的写「明天开盘」（前面有一笔状态不明 →「等登记状态不明的单」；G3 复核；now 给了 → 按日子写「今天开盘」/「明天开盘」/
    「10/19（周一）开盘」：hold_text，复核 2026-10-16）；
    now（页面 / 命令行）：盘中没下成、盘中已经结束的写「今天盘中没下成 → MM/DD 开盘（寄付）」（G18）；等上一笔成交的写「等上一笔成交」（G10）。"""
    s = it.get("status")
    if s == "placed" and it.get("now"):
        if now_lapsed(it, now):
            return "盘中部分成交，其余已失效" if it.get("fill") else "盘中的单已失效"
        return "盘中已成交" if it.get("fill") else "盘中已下单"
    u = it.get("unsent") or {}
    if s == "placed" and u.get("last"):                    # 这次的单没发出（被挡 / 被拒）：卖出等再下；被拒的买入不再重下（G7；2026-10-14）
        return "没发出，等再下" if u.get("retry", True) else "没发出（只做一次）"
    if s == "pending" and allin_member(it):
        return "等下一次决策（整批）"
    if s == "pending" and it.get("hold"):
        if UNK_LATER in str(it.get("msg") or ""):
            return "等登记状态不明的单"
        return "明天开盘" if now is None else hold_text(it, now)   # now 没给（执行器的事件 / 汇总）→ 照旧
    if s == "pending" and it.get("wait") == "prev":
        return "等上一笔成交"
    if s == "pending" and now is not None:
        r = rolled_text(it, now)
        if r:
            return r
    return STATUS.get(s, str(s))


FIX_WAIT = "生效中 · 还没照它调"


def fix_status_text(it: dict, items, book: dict | None, tag: str | None = None) -> str | None:
    """固定口数指令（corefix）执行器已经读了（完成）、但还没照它排单（corefix_pending）→「生效中 · 还没照它调」；别的 → None。
    闲置资金比例（core）同样：最新生效的那条、比例还没照它调（core_wait）→「生效中 · 还没照它调」（复核 3，2026-10-16）。
    只看这只最新的那条 corefix（含恢复按规则）；与 now_due / 执行器同一个判断（2026-10-16 复核：以前写「完成」，像是已经调好了）。
    给了 tag、这只还有执行器没读的 corefix（撤回了的、「全部换成」同批的不算）→ None：读到就换成它（与 core_wait 同一个处理）。"""
    if it.get("kind") == "core" and it.get("status") == "done":   # 闲置资金比例读了、还没照它调（core_wait；复核 3，2026-10-16）
        try:
            cw = core_wait(book, tag)
        except Exception:                                    # noqa: BLE001  展示用：算不出就照旧写「完成」
            return None
        return FIX_WAIT if cw and cw["item"] is not None and cw["item"].get("id") == it.get("id") else None
    if it.get("kind") != "corefix" or it.get("status") != "done" or it.get("clear"):
        return None
    t = it.get("ticker")
    same = [x for x in items if x.get("kind") == "corefix" and x.get("ticker") == t and x.get("status") == "done"]
    if not same or max(same, key=lambda x: str(x.get("at") or "")).get("id") != it.get("id"):
        return None
    try:
        if tag:                                              # 这只还有执行器没读的固定口数 / 恢复按规则（读到就换成它，「交易」里是那一行；
            w = unseen(tag, book)                            # 与 core_wait、outlook 的 unread_fix 同一个过滤）→ 这条不再是「还没照它调」的那一条
            gone = cancelled(w) if w else set()              # （复核 2026-10-16：以前口数相同时两条都算，读了之后数字少 1）
            if any(r.get("kind") == "corefix" and r.get("ticker") == t and r.get("id") not in gone and not r.get("fund_for") for r in w):
                return None
        p = corefix_pending(book, tag)
    except Exception:                                        # noqa: BLE001  展示用：算不出就照旧写「完成」
        return None
    return FIX_WAIT if t in p and p[t] == int(it.get("units") or 0) else None


def entry_why(eng, t: str, i: int) -> str | None:
    """买入 / 加仓的闸门（与规则的新仓相同）：资格检查 / 手动卖出后不买回（entry_gate_fn）、决算前（entry_block_fn）、新仓倍数 0。"""
    why = eng.entry_gate_fn(t, i) if eng.entry_gate_fn is not None else None
    mg = getattr(eng, "manual_gate_fn", None)              # 挡的是「手动卖出后不买回」→ 换成手动的口径（2026-10-13：解除了就不挡；挡的话说清楚怎么解除）
    if why and mg is not None and why == mg(t, i):
        why = mg(t, i, manual=True)
    if not why and eng.entry_block_fn is not None:
        why = eng.entry_block_fn(t, i)
    if not why and float(eng._entry_mult(t, i)) <= 0:
        why = "规则现在不开新仓（新仓倍数是 0）"
    return why


def buy_size(eng, it: dict, eq: float, px: float, lot: int, em: float) -> tuple[int, str]:
    """买入的股数（单元向下取整，还没按上限 / 现金截）与说明：按规则的仓位 = 权益 × position_pct × 新仓倍数（≤ 单只上限；
    与统一决策的新仓同一个算法，价格含滑点）；或目标（股数 / 金额 / 占权益 %）。"""
    cfg = eng.cfg
    if it.get("unit", "rule") == "rule":
        budget = min(eq * cfg.position_pct * min(1.0, em), eq * cfg.max_position_pct)
        pxs = px * (1 + eng.slip["JP"])
        return (int(math.floor(budget / pxs / lot)) * lot,
                f"按规则的仓位（权益 ×{cfg.position_pct * 100:g}%" + (f" × 新仓倍数 {em:g}" if em < 1 else "") + "）")
    return target_shares(it["unit"], it["value"], eq, px, lot), f"目标 {fmt_target(it)}"


def _when(it: dict, bar: str) -> str:
    """成交说明里的「盘中 / 开盘」：盘中下的单（now）在下单那天成交 → 盘中；没成交、改到之后的开盘卖的 → 开盘。"""
    return "盘中" if it.get("now") and str(it.get("fill_day") or "") == str(bar) else "开盘"


def _wait_text(now: dt.datetime, fill_day: dt.date) -> str:
    """开盘前的补单不做的买入 / 加仓：成交日就是今天 → 09:00 开盘后马上下（盘中的运行）；否则 → 那天早上的运行（开盘的寄付单）。"""
    if now.date() == fill_day:
        return "09:00 开盘后马上下单（盘中）"
    return f"{fill_day:%m/%d} 早上的运行下单（开盘买）"


def _who(it: dict) -> str:
    """事件行「手动指令 <id>：<这里> <说明>」：有票 →「代码 名字」（2026-10-15 用户：只写代码不知道是哪只）；
    闲置资金比例那条没有票 →「闲置资金」（以前有的地方写成「None」）。"""
    return names.label(it.get("ticker")) if it.get("ticker") else "闲置资金"


class Manual:
    """执行器里的手动指令：读指令文件 → 在下一次能下寄付单的运行里变成单 → 成交后记完成。状态都在执行器账本的 book["manual"]。"""

    def __init__(self, book: dict, tag: str, clock=None):
        self.book, self.tag, self.clock = book, tag, clock or now_jst
        m = book.setdefault("manual", {})
        m.setdefault("items", {})
        m.setdefault("blocks", {})
        m.setdefault("trims", {})
        m.setdefault("adds", {})
        m.setdefault("buys", {})
        m.setdefault("core_pct", 100.0)
        m["tag"] = tag
        self.m = m
        self.halt_backlog: str | None = None          # 这次运行：HALT 解除后照原样执行的积压指令（汇总 / 通知；halt_mark）
        self._read_now: list[str] = []                   # 这次运行读到、当场生效的 core / corefix（HALT 中 → halt_mark 标 halt；2026-10-14）

    # ── 设定 ──
    @property
    def core_pct(self) -> float:
        return float(self.m.get("core_pct", 100.0))

    def block_reason(self, t: str, day, manual: bool = False) -> str | None:
        """t 在 day（决策用的 K 线日）还在「手动卖出后不自动买回」期内 → 理由。按 K 线算（2026-10-13）：K 线日 ≤ until 的决策都挡；
        解除（lift_from）从成交日 ≥ lift_from 的决策起才不挡（补跑的旧 K 线不追溯）。manual：手动买入 / 加仓的口径 ——
        已经解除（等下一次决策）就不挡；挡的时候说清楚规则和手动都不买、要先解除。"""
        b = (self.m.get("blocks") or {}).get(t)
        if not b:
            return None
        until = b.get("until")
        d = day.date() if hasattr(day, "date") else day
        lf = b.get("lift_from")
        if lf and (manual or next_trading_day(d).isoformat() >= str(lf)):
            return None
        if until is None or str(d) <= str(until):
            per = "一直，直到解除" if until is None else f"到 {until}"
            if manual:
                return f"手动卖出后不买回（{per}；规则和手动都不买）：要买先在{BLOCK_WHERE}点「解除」/「恢复按规则」"
            return f"手动卖出后不自动买回（{per}）"
        return None

    def _set_block(self, t: str, days: int, decided: dt.date, rid: str, it: dict | None = None) -> None:
        if days == 0:
            return
        until = None if days < 0 else add_trading_days(decided, days).isoformat()
        b = {"until": until, "since": decided.isoformat(), "id": rid}
        if it and it.get("batch") == "all" and it.get("fund_for"):   # 「全部换成 X」的同批：记下是哪一批（指令记录只留 200 条，面板按批解除要用）
            b.update(fund_for=it["fund_for"], batch_at=it.get("at"))
        self.m["blocks"][t] = b

    def cancelling(self, t: str) -> bool:
        """t 有撤回中的手动指令（对账之后就撤）。"""
        return any(it.get("cancel_req") for it in self._active_for(t, ORDER_KINDS))

    def _active_for(self, t: str, kinds=POS_KINDS) -> list[dict]:
        return [it for it in self.m["items"].values()
                if it.get("ticker") == t and it.get("kind") in kinds and it.get("status") == "placed"]

    def _fresh_prev(self, tg: dict | None) -> None:
        """恢复的「全部换成」同批比例 0%：prev_pct（之后撤不了时提示「把比例设回 N%」用）按现在的比例（撤回期间可能改过；2026-10-13）。"""
        if tg is not None and tg.get("kind") == "core" and tg.get("fund_for"):
            tg["prev_pct"] = self.core_pct

    # ── 读指令 ──
    def ingest(self, only=None) -> list[tuple[str, str]]:
        """新指令 → items（pending）；core 当场生效、unblock 记 lift_from（下一次决策起生效）；cancel：等执行器的马上撤，已交给执行器的记下「撤回中」
        （settle 在对账之后处理）；cancel_order（撤单）：等执行器撤（--phase cancel）。only：只读这几种（撤单的运行只读撤单，
        别的留给平时的运行）。返回 [(级别, 说明)]。"""
        msgs = []
        items = self.m["items"]
        recs = read_all(self.tag)
        new = [r for r in recs if r["id"] not in items and not is_pruned(r, self.m)   # 整理账本时删掉的旧记录不再读（2026-10-14 G1）
               and (only is None or r["kind"] in only)]
        void = voided(recs)                                   # 被「撤销撤回」作废的撤回
        dropped = {r.get("target") for r in new if r["kind"] == "cancel" and r["id"] not in void}   # 执行器读到之前就被撤回的（比例 / 解除是读到就生效的）
        wd = {r.get("target"): r["id"] for r in recs if r["kind"] == "cancel" and r["id"] not in void and r["id"] not in items
              and not is_pruned(r, self.m)}               # 还没读的撤回（撤单的运行只读撤单，也要认得撤回：2026-10-16 事后）
        for k0, it0 in items.items():                         # 读了、撤单的运行还没做的撤单被撤回：先记「已撤回」（撤单的运行不再撤它）
            if (isinstance(it0, dict) and k0 in wd and it0.get("kind") == "cancel_order" and it0.get("status") == "pending"
                    and not order_started(it0)):
                it0.update(status="cancelled", msg=f"撤单的运行做之前就撤回了（{wd[k0]}）：不撤单", withdrawn_by=wd[k0])
                msgs.append(("info", f"手动指令 {k0}：{describe(it0)} → {it0['msg']}"))
        for r in new:
            it = {**r, "status": "pending"}
            items[r["id"]] = it
            k = r["kind"]
            if k in ("core", "unblock", "corefix") and r["id"] in dropped:   # corefix：读到就生效 → 读到之前撤回的不生效（2026-10-12）
                it.update(status="cancelled", msg="执行器读到之前就撤回了")
            elif k in ("core", "corefix") and r.get("fund_for"):   # 「全部换成 X」的同批：等那次决策先过闸门再一起生效（2026-10-13）
                it["msg"] = f"等「全部换成 {names.label(r['fund_for'])}」的决策一起生效"   # msg 里的票写「代码 名字」（2026-10-15）
            elif k == "core":
                self._read_now.append(r["id"])
                self.m["core_pct"] = float(r["pct"])
                if float(r["pct"]) <= 0:                     # 停买闲置资金 ETF（卖出全部 / 比例 0%）：之后出现买入信号只提醒，你确认才买
                    self.m["core_pause"] = {"since": self.clock().date().isoformat(), "id": r["id"], "ticker": r.get("ticker")}
                else:
                    self.m.pop("core_pause", None)
                    self.m.pop("core_signal", None)
                it.update(status="done", msg=(f"卖出全部 {names.label(r['ticker'])}，之后停买闲置资金 ETF（出现买入信号会提醒，你确认才买）"
                                              if float(r["pct"]) <= 0 and r.get("ticker") else f"闲置资金比例设为 {r['pct']:g}%"
                                              + (f"（{names.label(r['ticker'])} 约 {int(r.get('target') or 0):,} 口）" if r.get("ticker") else "")))
            elif k == "corefix":
                self._read_now.append(r["id"])
                fx = self.m.setdefault("core_fix", {})
                lt = names.label(r["ticker"])
                when = corefix_fill(self.clock(), self.book, self.tag, lock=False)["text"]   # 什么时候照它调（D1；2026-10-15：以前一律「下一次决策起」）
                if r.get("clear"):
                    fx.pop(r["ticker"], None)
                    it.update(status="done", msg=f"{lt} 恢复按规则（{when}）")
                else:
                    fx[r["ticker"]] = int(r["units"])
                    it.update(status="done", msg=f"{lt} 固定 {int(r['units']):,} 口（{when}；其余闲置资金照规则）")
            elif k == "unblock":                             # 2026-10-13：不当场去掉，记 lift_from（下一次决策起才不挡；补跑的旧 K 线不追溯）
                b = self.m["blocks"].get(r["ticker"])
                lt = names.label(r["ticker"])
                if not b:
                    it.update(status="rejected", msg=f"{lt} 本来就没有「不自动买回」")
                elif r.get("block_id") and r["block_id"] != b.get("id"):
                    it.update(status="rejected", msg=f"{lt} 的不自动买回已经换成别的设定 / 已经解除：这条不动它（要解除请在页面上重新点）")
                elif b.get("lift_from"):
                    it.update(status="rejected", msg=f"{lt} 的不自动买回已经在解除（{block_text(b)}）")
                else:
                    lf = lift_day(r.get("at"), self.clock)
                    b.update(lift_from=lf.isoformat(), lift_id=r["id"])
                    it.update(status="done", msg=f"{lt} 解除「不自动买回」：{lf:%m/%d} 07:40 的决策起不挡（不会买回，也不马上买；之后出买入信号规则才可能买）")
            elif k == "cancel" and r["id"] in void:              # 读到之前就被撤销了：这条撤回不生效
                it.update(status="voided", msg="这条撤回已撤销")
            elif k == "uncancel":
                c = items.get(r["target"])
                tg = items.get((c or {}).get("target"))
                what = describe(tg) if tg else (c or {}).get("target")   # 2026-10-13：比例那条没有代码（以前写成「None」）
                if c is not None and c.get("status") == "voided":
                    self._fresh_prev(tg)
                    it.update(status="done", msg=f"撤销撤回：{what} 照原来的指令处理")
                elif c is not None and tg is not None and tg.get("status") == "cancelled" and (tg.get("kind") in ORDER_KINDS or tg.get("fund_for")):
                    self._fresh_prev(tg)
                    tg.update(status="pending", msg="撤回已撤销：恢复等下单")
                    for f in ("cancel_req", "wait", "hold", "tried"):   # 2026-10-13 修：cancel_req 残留会让下一次决策又撤一次
                        tg.pop(f, None)
                    c.update(status="voided", msg="这条撤回已撤销")
                    it.update(status="done", msg=f"撤销撤回：{what} 恢复等下单")
                elif c is not None and tg is not None and tg.get("cancel_req") == c.get("id"):
                    tg.pop("cancel_req", None)
                    c.update(status="voided", msg="这条撤回已撤销")
                    it.update(status="done", msg=f"撤销撤回：{what} 照原来的指令继续")
                else:
                    it.update(status="rejected", msg="这条撤回已经处理完，撤销不了：要的话重新下一次指令")
            elif k == "cancel_order" and r["id"] in wd:         # 读到之前就被撤回的撤单：不撤（那笔单照常发 / 照常挂着；2026-10-16 事后）
                it.update(status="cancelled", msg=f"执行器读到之前就撤回了（{wd[r['id']]}）：不撤单", withdrawn_by=wd[r["id"]])
            elif k == "cancel":                                  # 撤的是什么写在 id 后面（只写 id 看不出是哪只；2026-10-15 target_text）
                tg = items.get(r["target"])
                tt = target_text(r["target"], tg)
                if tg is not None and tg.get("kind") == "cancel_order":   # 撤回撤单：只有读到之前撤回的算数（读了可能已经发到立花）
                    if tg.get("status") == "cancelled" and tg.get("withdrawn_by") == r["id"]:
                        it.update(status="done", msg=f"撤回 {tt}：不撤单")
                    else:
                        it.update(status="rejected", msg=f"{tt}：撤单的运行已经在撤 / 已经做完（可能已经发到立花），撤回不了")
                elif tg is not None and tg.get("status") == "pending":
                    tg.update(status="cancelled", msg=f"已撤回（{r['id']}）")
                    for f in ("wait", "hold", "tried"):
                        tg.pop(f, None)
                    it.update(status="done", msg=f"撤回 {tt}")
                elif tg is not None and tg.get("status") == "cancelled" and r["target"] in dropped:
                    it.update(status="done", msg=f"撤回 {tt}")
                elif tg is not None and tg.get("status") == "placed" and tg.get("now") and now_cancel_why(tg, self.clock()):
                    it.update(status="rejected", msg=f"{tt}：{now_cancel_why(tg, self.clock())}")
                elif tg is not None and tg.get("status") == "placed" and tg.get("now") and not tg.get("cancel_req"):
                    tg["cancel_req"] = r["id"]                # 15:30 之后失效的盘中卖出：对账之后撤（待卖 / 减仓去掉，明天不再卖；G16）
                    it.update(status="done", msg=f"撤回 {tt}：{now_sell_withdrawn(tg)}")
                elif tg is not None and tg.get("status") == "placed" and not tg.get("cancel_req"):
                    tg["cancel_req"] = r["id"]
                    it.update(status="done", msg=f"撤回 {tt}：之后不再下（已经发到交易所的单用「今天要成交的单」的「撤单」撤）")
                else:
                    # 也写撤的是什么（2026-10-15 复核；找不到那条 → 只写 id，照旧「M… 不是…」）
                    it.update(status="rejected", msg=f"{tt}{'' if tt.endswith('）') else ' '}不是还没完成的指令，撤不了")
            elif k == "cancel_order":
                it["msg"] = (f"等执行器整组撤单（{len(cancel_cids(it))} 笔）" if it.get("grp") else "等执行器撤单")
            else:
                it["msg"] = "等执行器下单"
            msgs.append(("info", f"手动指令 {r['id']}：{describe(r)} → {it['msg']}"))
        return msgs

    def pending(self, kinds=POS_KINDS) -> list[dict]:
        return sorted((it for it in self.m["items"].values() if it.get("status") == "pending" and it.get("kind") in kinds),
                      key=lambda x: x.get("at", ""))

    def _halt_msgs(self, todo=None) -> None:
        """HALT 中：等着的指令写「HALT 中：解除后照原样执行（写于 MM/DD）」（一样就不改，免得账本来回变）。"""
        for it in (self.pending(ORDER_KINDS) if todo is None else todo):
            msg = halt_text(it)
            if it.get("msg") != msg:
                it["msg"] = msg

    def halt_mark(self, halted: bool) -> list[tuple[str, str]]:
        """每次运行读完指令之后（2026-10-13 resume-other-3）：HALT 中 → 账本记下 halt_seen（第一次看到 / 最后一次看到的时刻）、
        等着的指令写明解除后照原样执行；HALT 已解除、上一次还记着 halt_seen → 去掉标记，有积压的指令 → warn 列出每条（id 票 种类 写于 MM/DD），
        self.halt_backlog 记下这段文字（这次运行的汇总 / 通知用）。返回 [(级别, 说明)]。
        2026-10-14：HALT 中读到的闲置资金比例 / 固定口数（读到就生效、ETF 等解除后的决策）标 halt、说明写明，解除时也列进积压。"""
        now = self.clock().isoformat(timespec="seconds")
        items = self.m["items"]
        read, self._read_now = self._read_now, []
        if halted:
            hs = self.m.get("halt_seen") if isinstance(self.m.get("halt_seen"), dict) else {}
            self.m["halt_seen"] = {"since": hs.get("since") or now, "last": now}
            self._halt_msgs()
            for rid in read:
                it = items.get(rid)
                if it is not None and it.get("status") == "done" and not it.get("fund_for") and not it.get("halt"):
                    it.update(halt=True, msg=f"{it.get('msg') or describe(it)}（{HALT_CORE_MSG}）")
            return []
        etf = sorted((it for it in items.values() if it.get("halt") and it.get("kind") in ("core", "corefix")),
                     key=lambda x: str(x.get("at") or ""))
        for it in etf:
            it.pop("halt", None)
            it["msg"] = str(it.get("msg") or "").replace(HALT_CORE_MSG, HALT_CORE_DONE)
        hs = self.m.pop("halt_seen", None)
        if not hs:
            return []
        todo = self.pending(ORDER_KINDS)
        if not todo and not etf:
            return []
        for it in todo:
            if str(it.get("msg") or "").startswith(HALT_WAIT_MSG):
                it["msg"] = f"{HALT_DONE_MSG}（写于 {mmdd(it.get('at'))}）"
        since = (hs.get("since") if isinstance(hs, dict) else None) or ""
        head = (f"{len(todo)} 条手动指令在 HALT 期间等着，现在照原样执行："
                + "；".join(f"{it['id']} {names.label(it.get('ticker'))} {LABEL.get(it.get('kind'), it.get('kind'))} 写于 {mmdd(it.get('at'))}"
                            for it in todo) if todo else "")
        tail = (f"HALT 期间改的闲置资金比例 / 固定口数 {len(etf)} 条，照它买卖 ETF（{HALT_CORE_AFTER}）：{halt_core_line(etf)}" if etf else "")
        self.halt_backlog = ("。".join(x for x in (head, tail) if x)
                             + (f"（HALT 从 {mmdd(since)} 起）" if since else "")
                             + ("。要不做：面板「撤回」或 liveu.sh manual cancel <id>" if todo else "")
                             + ("。要改回：面板「闲置资金」重新设比例 / 固定口数（liveu.sh manual core --pct N / manual corefix <ETF> --clear）" if etf else ""))
        return [("warn", self.halt_backlog)]

    def has_work(self) -> bool:
        """还有要变成单的手动指令（等执行器的 sell / trim / adjust / buy）或要处理的撤回。"""
        return bool(self.pending(ORDER_KINDS)) or any(it.get("cancel_req") and it.get("status") == "placed"
                                                     for it in self.m["items"].values())

    # ── 变成单 ──
    def apply(self, eng, i: int, fill_day: dt.date, halted: bool = False, deciding: bool = True, blocked: bool = False,
              allin_check=None) -> list[tuple[str, str]]:
        """第 i 根 K 线收盘后的决策之前（deciding = True）或同一决策补单之前（False）：等着的 sell / trim / adjust / buy → 开盘的寄付单。
        补跑的旧 K 线（成交日已经过了）不处理；HALT 时不动；成交日 08:55 之后寄付来不及 → 留着，开盘后由盘中的运行（now_phase）下。
        加仓 / 买入只在 deciding（统一决策要先给它留钱、买入还占名额）；同一决策补单时留着（wait），09:00 开盘后由盘中的运行下。
        先处理卖出 / 减仓 / 调仓，再处理买入（同一次决策里先卖出一只、空出的名额给买入）。
        blocked（这次运行不下单）：「全部换成」整批、买入、调仓往上、平摊凑钱的整组都留到下一次能下单的决策（2026-10-13：以前买入被当成没买到）。
        平摊凑钱（fund = split）的买入在任何卖出之前先过不涉及钱的闸门（_buy_gate）：被挡 → 买入和凑钱的卖出一起不做（2026-10-13）；
        平摊凑钱的加仓（调仓往上）同样先过 _add_gate（2026-10-14）。
        allin_check(票, i)：执行器替「全部换成」/ 平摊凑钱的买入在卖出之前先做下单时才查的检查（资格检查、立花能不能买、LU-15 前日終値）→ 理由 / None；
        普通的买入 / 加仓排进计划之前也查（规则会为它卖核心 ETF；G5 / G15，2026-10-14）。
        返回 [(级别, 说明)]。"""
        decided = eng.gidx[i].date()
        orphan = self._allin_orphans(decided)               # 买入已经结束的「全部换成」：同批还 pending 的一律作废（整批不做）
        todo = sorted(self.pending(ORDER_KINDS), key=lambda x: (x["kind"] == "buy", x.get("at", "")))
        if not todo:
            return orphan
        now = self.clock()
        if now.date() > fill_day:
            return orphan
        if now.date() == fill_day and now.time() >= CUTOFF:
            n_all = sum(1 for x in todo if allin_member(x))  # 「全部换成」整批只在决策里做：不是开盘后马上下（2026-10-13）
            out = list(orphan)
            if len(todo) > n_all:
                out.append(("info", f"手动指令 {len(todo) - n_all} 条：过了 {CUTOFF:%H:%M}，寄付来不及 → 开盘后马上下（盘中）"))
            if n_all:
                out.append(("info", f"「全部换成」整批 {n_all} 条：过了 {CUTOFF:%H:%M}，寄付来不及 → 全部换成整批：等下一次决策"))
            return out
        if halted:
            self._halt_msgs(todo)                           # 每条写明：HALT 中，解除后照原样执行（写于 MM/DD）
            return orphan + [("warn", f"手动指令 {len(todo)} 条没处理：HALT 生效中（解除之后照原样执行）")]
        st, out = eng.st, list(orphan)
        today = now.date().isoformat()
        allin = {x["ticker"]: x for x in todo if x["kind"] == "buy" and x.get("fund") == "all"}   # 「全部换成 X」：整批只在决策里做（2026-10-13）
        split = {x["ticker"]: x for x in todo if x.get("fund") == "split" and not x.get("fund_for")
                 and x["kind"] in ("buy", "adjust")}         # 平摊凑钱的买入 / 加仓（调仓往上；2026-10-14：以前只管买入）

        def group(b: dict) -> list[dict]:                   # 同一次提交写的凑钱卖出（同一只买入、同一时刻）
            return [c for c in todo if c is not b and c.get("fund_for") == b["ticker"] and c.get("at") == b.get("at")]
        if blocked:                                         # 这次运行不下单（行情落后 / 冒烟测试 / 持仓对不上）：买的一侧留到下一次能下单的决策
            grouped = {c["id"] for b in split.values() for c in group(b)}
            held = set()
            for x in todo:
                if allin_member(x):
                    msg = "这次运行不下单 → 「全部换成」整批等下一次决策"
                elif x["kind"] == "buy" or x["id"] in grouped or self._adds(eng, i, x):
                    msg = "这次运行不下单 → 等下一次能下单的决策"
                else:
                    continue                                # 卖出 / 减仓照常变成单（这次挡住，之后的运行再下）
                for f in ("wait", "tried"):
                    x.pop(f, None)
                x.update(hold=today, msg=msg)
                held.add(x["id"])
                out.append(("info", f"手动指令 {x['id']}：{_who(x)} {msg}"))
            todo = [x for x in todo if x["id"] not in held]
            allin, split = {}, {}
        waiting = set()
        for b in list(split.values()):                      # 平摊凑钱：卖出之前先过买入 / 加仓的闸门（被挡 → 整组不做，什么都不卖）
            grp = group(b)
            add = b["kind"] == "adjust"
            what, verb = ("加仓", "不加仓") if add else ("买入", "不买")
            if add:
                why, hold = self._add_gate(eng, i, b)
                why = why or (None if hold else self._ext_check(allin_check, b["ticker"], i))
            else:
                why, hold = (self._buy_gate(eng, i, b, going={c["ticker"] for c in grp if _to_zero(c)})
                             or self._ext_check(allin_check, b["ticker"], i)), None
            if why:
                out += self._group_reject(b, grp, decided, f"{verb}：{why} → 凑钱的卖出也不做",
                                          f"{what} {names.label(b['ticker'])} 被挡 → 凑钱的卖出也不做")
                split.pop(b["ticker"], None)
            elif hold or not deciding:                      # 买入 / 加仓要等 09:00 开盘后（盘中的运行）或上一笔还没成交完：凑钱的卖出也一起等（先卖后买）
                for c in grp:
                    for f in ("hold", "tried"):
                        c.pop(f, None)
                    c.update(wait=True, msg=f"与{what} {names.label(b['ticker'])} 一起：" + (hold or "开盘后盘中先卖后买"))
                    waiting.add(c["id"])
                    out.append(("info", f"手动指令 {c['id']}：{_who(c)} {c['msg']}"))
        if deciding and allin:                              # 先查不涉及钱的闸门：被挡 → 整批不做（什么都没动）；过了 → 比例 0% / 取消固定口数 / 补齐要卖的
            for it in list(allin.values()):
                why = self._allin_gate(eng, i, it, allin_check)
                if why:
                    out += self._allin_abort(eng, it, decided, why)
                    allin.pop(it["ticker"], None)
                    continue
                out += self._allin_apply_core(eng, it, decided)
                out += self._allin_sweep(eng, it, todo, decided)
        todo = sorted((x for x in todo if x.get("status") == "pending" and x["id"] not in waiting),
                      key=lambda x: (x["kind"] == "buy", x.get("at", "")))
        for it in todo:
            t = it["ticker"]
            lt = names.label(t)                             # 事件行 / msg 里写「代码 名字」（指令 id 不动；2026-10-15）
            ps = st.pos.get(t)
            rule = st.pending_exit.get(t)
            for f in ("wait", "hold", "tried", "fund_wait"):   # fund_wait：盘中等凑钱的核心卖单成交（执行器 now_phase）→ 新的决策不再等
                it.pop(f, None)
            if not deciding and it.get("fund_for") in allin and it.get("at") == allin[it["fund_for"]].get("at"):
                it.update(hold=today, msg=f"与「全部换成 {names.label(it['fund_for'])}」一起等下一次决策（先过闸门再先卖后买）")
                out.append(("info", f"手动指令 {it['id']}：{lt} {it['msg']}"))
                continue
            if it["kind"] == "buy":
                if not deciding and it.get("fund") == "all":     # 全部换成这只：整批只在决策里做 → 下一次决策（闸门也在那时查）
                    it.update(hold=today, msg="全部换成这只：整批等下一次决策（先过闸门，再先卖后买）")
                elif ps is not None:
                    it.update(status="rejected", msg="已经持有：要加仓用「调仓」")
                elif not deciding:
                    it.update(wait=True, msg=_wait_text(now, fill_day))
                else:
                    self._buy(eng, i, it, decided, fill_day, pre=None if it.get("fund") in ("all", "split") else allin_check)
                    if it.get("fund") == "all":
                        it["msg"] += self._allin_late(eng, i, it, fill_day)
                lvl = "warn" if it["status"] == "rejected" else "info"
                out.append((lvl, f"手动指令 {it['id']}：{lt} {it['msg']}"))
                continue
            batch = allin_member(it) and it.get("fund_for") in allin   # 「全部换成」同批（闸门已过）
            if ps is None:
                if batch and it["kind"] == "sell":           # 规则已经先卖掉了：照样设不自动买回（2026-10-13）
                    self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"], it)
                    it.update(status="superseded", decided_on=str(decided), fill_day=str(fill_day),
                              msg="已经不在持仓（规则已先卖出）→ 设不自动买回")
                else:
                    it.update(status="rejected", msg="执行器的账本里没有这只持仓（已经卖掉了？）")
            elif rule == "manual":
                it.update(status="rejected", msg="已经在卖出全部，不用再点")
            elif rule:
                it.update(status="superseded", decided_on=str(decided), fill_day=str(fill_day),
                          msg=(f"规则已在卖出（{_exit_text(rule)}）→ 按规则的单卖、设不自动买回" if batch and it["kind"] == "sell"
                               else f"规则也要卖出全部（{rule}），按规则的单卖"))
                if it["kind"] == "sell":
                    self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"], it)
            elif batch and t in self.m["trims"] and t not in self.m["adds"]:   # 还没卖完的减仓：整只卖出盖过它
                old = self.m["trims"].pop(t)
                oi = self.m["items"].get(old.get("id")) or {}
                it["undo_trim"] = {"trim": old, "status": oi.get("status"), "msg": oi.get("msg")}   # 整批退回时还原
                if oi.get("status") == "placed":
                    oi.update(status="superseded", msg=f"「全部换成 {names.label(it['fund_for'])}」整只卖出 → 这笔减仓不再单独下")
                self._place(eng, i, it, ps, decided, fill_day)
            elif t in self.m["trims"] or t in self.m["adds"]:
                # 等上一笔成交（G10；2026-10-14）：标 wait = "prev" → 开盘前的补单（MO.due）不再每 3 分钟叫一次执行器；
                # 上一笔第二天早上对账记完之后，那次决策照常处理（apply 开头会去掉 wait）
                prev = self.m["trims"].get(t) or self.m["adds"].get(t) or {}
                pi = self.m["items"].get(prev.get("id")) or {}
                try:
                    pf = max(dt.date.fromisoformat(str(pi.get("fill_day") or "")[:10]), fill_day)
                except ValueError:
                    pf = fill_day
                it.update(wait="prev", msg=f"等 {lt} 的上一笔成交（最早 {next_trading_day(pf):%m/%d} 早上的决策）")
                out.append(("info", f"手动指令 {it['id']}：{lt} {it['msg']}"))
                continue
            elif it["kind"] == "adjust":
                self._adjust(eng, i, it, ps, decided, fill_day, deciding, pre=None if it.get("fund") == "split" else allin_check)
                if it["status"] == "pending":
                    out.append(("info", f"手动指令 {it['id']}：{lt} {it['msg']}"))
                    continue
            else:
                self._place(eng, i, it, ps, decided, fill_day)
            out.append(("warn" if it["status"] == "rejected" else "info", f"手动指令 {it['id']}：{lt} {it['msg']}"))
        return out

    def _adds(self, eng, i: int, it: dict) -> bool:
        """调仓按第 i 天收盘换算是往上加（这次运行不下单时留到下一次决策）。凑钱的卖出（fund_for）不算。"""
        if it.get("kind") != "adjust" or it.get("fund_for"):
            return False
        ps = eng.st.pos.get(it["ticker"])
        if ps is None:
            return False
        try:
            eq, px, lot = self._numbers(eng, i, it["ticker"])
            return px > 0 and eq > 0 and target_shares(it["unit"], it["value"], eq, px, lot) > int(ps.shares)
        except Exception:                                   # noqa: BLE001  算不了 → 照原来的路走（_adjust 会说明）
            return False

    def _add_gate(self, eng, i: int, it: dict) -> tuple[str | None, str | None]:
        """平摊凑钱的加仓（调仓往上、fund = split）在凑钱的卖出之前先过的闸门（与 _adjust / _add 同一套不涉及钱的；2026-10-14：
        以前只管买入，加仓被挡时凑钱的卖出照样成交）→ (被挡的理由, 要一起等的理由)。"""
        t, st = it["ticker"], eng.st
        ps = st.pos.get(t)
        if ps is None:
            return "执行器的账本里没有这只持仓（已经卖掉了？）", None
        rule = st.pending_exit.get(t)
        if rule:
            return f"已经在卖出全部（{_exit_text(rule)}）", None
        if t in self.m["trims"] or t in self.m["adds"]:
            return None, "同一只票的上一笔手动单还没成交完：成交后再一起处理"
        try:
            eq, px, lot = self._numbers(eng, i, t)
        except Exception:                                   # noqa: BLE001
            return "没有收盘价 / 总权益，算不了", None
        if not (px > 0 and eq > 0):
            return "没有收盘价 / 总权益，算不了", None
        cur, want = int(ps.shares), target_shares(it["unit"], it["value"], eq, px, lot)
        fw = adjust_flip_why(it, cur, want)
        if fw:
            return fw, None
        if want <= cur:
            return f"按现在的收盘换算不是加仓了（现在 {cur:,} 股，目标换算 {want:,} 股）", None
        why = entry_why(eng, t, i)
        if why:
            return why, None
        cap = int(math.floor(eq * MANUAL_CAP_PCT / 100 / px / lot + 1e-9)) * lot
        if (min(want, cap) - cur) // lot * lot <= 0:
            return f"现在 {cur:,} 股：{cap_text(cur, px, eq, MANUAL_CAP_PCT, lot)}", None
        return None, None

    @staticmethod
    def _ext_check(fn, t: str, i: int) -> str | None:
        """执行器给的下单前检查（allin_check）：没有 → None；出错 → 当作被挡（先不卖）。"""
        if fn is None:
            return None
        try:
            return fn(t, i)
        except Exception as e:                              # noqa: BLE001
            return f"下单前检查出错（{type(e).__name__}）：先不做"

    def _group_reject(self, b: dict, grp: list[dict], decided: dt.date, msg_b: str, msg_c: str) -> list[tuple[str, str]]:
        """买入和同一次提交写的凑钱卖出一起不做。"""
        out = []
        for x, msg in [(b, msg_b)] + [(c, msg_c) for c in grp if c.get("status") == "pending"]:
            x.update(status="rejected", decided_on=str(decided), msg=msg)
            for f in ("wait", "hold", "tried"):
                x.pop(f, None)
            out.append(("warn" if x is b else "info", f"手动指令 {x['id']}：{_who(x)} {msg}"))
        return out

    def _buy_gate(self, eng, i: int, it: dict, going=()) -> str | None:
        """买入在卖出之前先过一遍不涉及钱的闸门（和 _buy 同一套）：不过 → 理由。名额按 going（同一次要卖到 0 的票）卖完之后算。
        「全部换成」与「平摊凑钱」共用（2026-10-13）。"""
        t, st, cfg = it["ticker"], eng.st, eng.cfg
        j = eng.col.get(t)
        if t in eng.core_set:
            return "核心 ETF 不能手动买"
        if t in st.pos:
            return "已经持有：要加仓用「调仓」"
        if j is None or not eng.A.has[i, j]:
            return f"没有 {names.label(t)} 的行情（不在股票池？停牌？）"
        if t in st.plan:
            return "已经排在开盘买入（规则的信号）"
        why = entry_why(eng, t, i)
        if why:
            return why
        n_after = len([x for x in st.pos if x not in st.pending_exit and x not in set(going)])
        if n_after + len(st.plan) >= cfg.max_positions:
            return f"个股名额已满（卖完之后还拿着 {n_after} 只 + 排定买入 {len(st.plan)} 只，上限 {cfg.max_positions} 只）"
        eq, px, _lot = self._numbers(eng, i, t)
        if not (px > 0 and eq > 0):
            return "没有收盘价 / 总权益，算不了"
        return None

    def _allin_gate(self, eng, i: int, it: dict, allin_check=None) -> str | None:
        """「全部换成 X」的买入在卖出之前的闸门：名额按 X 以外的持仓全部卖掉算（执行时拿着的都卖，包括写指令之后才拿的）；
        再加执行器的下单前检查（资格检查、LU-15 前日終値；2026-10-13：以前卖单发出之后买单才被挡）。"""
        t = it["ticker"]
        return self._buy_gate(eng, i, it, going={x for x in eng.st.pos if x != t}) or self._ext_check(allin_check, t, i)

    def _allin_orphans(self, decided: dt.date) -> list[tuple[str, str]]:
        """「全部换成 X」的同批还 pending、但它的买入已经不在等了（被拒 / 撤回 / 没买到 / 找不到）→ 同批作废，不单独执行。"""
        out, items = [], self.m["items"]
        for c in list(items.values()):
            if c.get("status") != "pending" or not allin_member(c) or c.get("kind") == "buy":
                continue
            b = batch_buy(c, items.values())
            if b is not None and b.get("status") in ("pending", "placed"):
                continue
            c.update(status="rejected", decided_on=str(decided),
                     msg=f"「全部换成 {names.label(c.get('fund_for'))}」的买入{('已结束（' + status_text(b) + '）') if b else '不在'} → 整批不做")
            for f in ("wait", "hold", "tried"):
                c.pop(f, None)
            out.append(("warn", f"手动指令 {c['id']}：{_who(c)} {c['msg']}"))
        return out

    def _allin_abort(self, eng, it: dict, decided: dt.date, why: str) -> list[tuple[str, str]]:
        """买入被挡 → 这笔「其他全部卖出」整批不做：同批还没处理的卖出 / 比例 / 固定口数都作废（它们在这之前什么都没动）。"""
        lt, out = names.label(it["ticker"]), []
        it.update(status="rejected", decided_on=str(decided), msg=f"不买：{why} → 整批不做（其他持仓不卖，闲置资金比例 / 固定口数不变）")
        out.append(("warn", f"手动指令 {it['id']}：{lt} {it['msg']}"))
        for c in companions_in(it, self.m["items"]):
            if c.get("status") != "pending":
                continue
            c.update(status="rejected", decided_on=str(decided), msg=f"买入 {lt} 被挡 → 整批不做")
            for f in ("wait", "hold", "tried"):
                c.pop(f, None)
            out.append(("info", f"手动指令 {c['id']}：{_who(c)} {c['msg']}"))
        return out

    def _allin_apply_core(self, eng, it: dict, decided: dt.date) -> list[tuple[str, str]]:
        """闸门过了：闲置资金比例 0%（停买）、取消全部固定口数 —— 不管同批里有没有比例 / 固定口数的指令（写指令之后才改的比例 /
        才固定的口数也一起；2026-10-13）。同一次决策里核心 ETF 就按它卖。原来的比例 / 固定口数 / 停买记在 it["undo_core"]
        （这次运行一笔卖单都没发出 → allin_rollback 恢复）与 core_pause 的 prev_pct / prev_fix（之后页面整批恢复用）。"""
        out, m, X = [], self.m, it["ticker"]
        prev_pct, prev_fix = self.core_pct, {t: int(u) for t, u in (m.get("core_fix") or {}).items()}
        it["undo_core"] = {"pct": prev_pct, "fix": prev_fix, "pause": m.get("core_pause"), "signal": m.get("core_signal")}
        comps = [c for c in companions_in(it, m["items"]) if c.get("status") == "pending"]
        cid, lx = None, names.label(X)                      # 文字里写「代码 名字」（2026-10-15）
        for c in comps:
            if c.get("kind") == "core":
                cid = c["id"]
                c.update(status="done", decided_on=str(decided), msg=f"闲置资金比例设为 0%（与「全部换成 {lx}」一起生效）")
            elif c.get("kind") == "corefix" and c.get("clear"):
                c.update(status="done", decided_on=str(decided), msg=f"{names.label(c['ticker'])} 取消固定口数（与「全部换成 {lx}」一起生效）")
            else:
                continue
            out.append(("info", f"手动指令 {c['id']}：{_who(c)} {c['msg']}"))
        if prev_pct > 0 and cid is None:
            out.append(("info", f"闲置资金比例 {prev_pct:g}% → 0%：与「全部换成 {lx}」一起停买闲置资金 ETF（写指令之后改过比例）"))
        left = sorted(set(prev_fix) - {c["ticker"] for c in comps if c.get("kind") == "corefix" and c.get("clear")})
        if left:
            out.append(("info", f"取消固定口数：{names.labels(left)}（写指令之后才固定的：与「全部换成 {lx}」一起取消，之后按比例 0% 卖出）"))
        old = m.get("core_pause") if prev_pct <= 0 else None
        pause = dict(old) if old else {"since": self.clock().date().isoformat(), "id": cid or it["id"], "ticker": None, "prev_pct": prev_pct}
        if prev_fix:
            pause["prev_fix"] = prev_fix
        pause["allin"] = X
        m["core_pct"], m["core_pause"], m["core_fix"] = 0.0, pause, {}
        eng.core_scale, eng.core_fix = 0.0, {}
        return out

    def _allin_sweep(self, eng, it: dict, todo: list[dict], decided: dt.date) -> list[tuple[str, str]]:
        """闸门过了：执行时拿着的 X 以外的个股全部卖出（全部换成 X 之后只剩 X + 现金；2026-10-13）。写指令之后才拿的（规则 / 别的指令
        买进的）→ 补一条同批的卖出全部（auto，同样的不买回天数）加进这次的待办；规则已在卖的由主循环设不自动买回；已有手动卖出全部的不动。
        先把这些票原来的待卖 / 不买回记在 it["undo"]（这次运行一笔卖单都没发出 → allin_rollback 恢复）。"""
        X, st, items = it["ticker"], eng.st, self.m["items"]
        comps = [c for c in todo if c is not it and c.get("fund_for") == X and c.get("at") == it.get("at") and c.get("kind") in POS_KINDS]
        mine = {c["ticker"] for c in comps}
        days = next((int(c.get("block_days", BLOCK_DEFAULT)) for c in comps if c.get("kind") == "sell"), BLOCK_DEFAULT)
        blocks = self.m["blocks"]
        it["undo"] = {t: {"pe": st.pending_exit.get(t), "block": dict(blocks[t]) if t in blocks else None}
                      for t in sorted((set(st.pos) - {X}) | mine)}
        out = []
        for t in sorted(st.pos):
            if t == X or t in mine or st.pending_exit.get(t) == "manual":
                continue
            base = rid = f"{it['id']}-auto-{t.split('.')[0]}"
            n = 2
            while rid in items:
                rid, n = f"{base}-{n}", n + 1
            c = {"id": rid, "kind": "sell", "ticker": t, "block_days": days, "fund_for": X, "batch": "all", "at": it.get("at"),
                 "source": "auto", "auto": True, "status": "pending", "msg": "写指令之后才拿的 → 一起卖"}
            items[rid] = c
            todo.append(c)
            out.append(("info", f"手动指令 {rid}：{names.label(t)} 写指令之后才拿的 → 与「全部换成 {names.label(X)}」一起卖"))
        return out

    @staticmethod
    def _allin_late(eng, i: int, it: dict, fill_day: dt.date) -> str:
        """「全部换成」比写入时预计的那天晚做（HALT / 晚跑 / 运行被挡）→ 一句说明（原定哪天、X 的收盘变了多少）；按时 → ""。"""
        af = it.get("allin_fill")
        if not af or fill_day.isoformat() <= str(af):
            return ""
        try:
            txt = f"；原定 {dt.date.fromisoformat(str(af)):%m/%d} 没做（HALT / 晚跑 / 运行被挡）"
        except ValueError:
            return ""
        a = float(it.get("x_close") or 0)
        try:
            b = float(eng._px_close(it["ticker"], i) or 0)
        except Exception:                                   # noqa: BLE001
            b = 0.0
        if a > 0 and b > 0:
            txt += f"；{names.label(it['ticker'])} 收盘 ¥{a:,g} → ¥{b:,g}（{(b / a - 1) * 100:+.1f}%）"
        return txt

    def allin_rollback(self, eng, it: dict, why: str) -> list[tuple[str, str]]:
        """「全部换成 X」这次决策过了闸门、但这次运行一笔同批卖单都没发出（异常熔断 / 整个运行被挡 / 适配器挡下，2026-10-13）→ 整批退回：
        待卖 / 不买回 / 闲置资金比例 / 固定口数 / 停买恢复成过闸门之前，同批指令回到「等下一次决策」，补的同批卖出（auto）删掉。"""
        st, m, X = eng.st, self.m, it["ticker"]
        d, today = it.get("decided_on"), self.clock().date().isoformat()
        for t, u in (it.pop("undo", None) or {}).items():
            if u.get("pe"):
                st.pending_exit[t] = u["pe"]
            else:
                st.pending_exit.pop(t, None)
            if u.get("block"):
                m["blocks"][t] = u["block"]
            else:
                m["blocks"].pop(t, None)
        uc = it.pop("undo_core", None)
        if uc is not None:
            m["core_pct"] = float(uc.get("pct", 100.0))
            m["core_fix"] = {t: int(u) for t, u in (uc.get("fix") or {}).items()}
            for key in ("core_pause", "core_signal"):
                if uc.get(key.split("_")[1]):
                    m[key] = uc[key.split("_")[1]]
                else:
                    m.pop(key, None)
            eng.core_scale, eng.core_fix = m["core_pct"] / 100, dict(m["core_fix"])
        lx = names.label(X)                                 # 文字里写「代码 名字」（2026-10-15）
        msg = f"「全部换成 {lx}」这次没下成（{why}）→ 整批退回，等下一次决策"
        ids, restore_trim = set(), []
        for c in companions_in(it, m["items"]):
            if c.get("auto"):
                m["items"].pop(c["id"], None)
                continue
            if c.get("decided_on") != d:
                continue
            ids.add(c["id"])
            for f in ("decided_on", "fill_day", "shares", "side", "done_on", "fill", "limit"):
                c.pop(f, None)
            ut = c.pop("undo_trim", None)                   # 被整只卖出盖过的减仓：还原
            if ut:
                restore_trim.append((c["ticker"], ut))
            c.update(status="pending", hold=today,
                     msg=(f"等「全部换成 {lx}」的决策一起生效" if c.get("kind") in ("core", "corefix") else msg))
        for t, x in list(m["trims"].items()):
            if x.get("id") in ids:
                m["trims"].pop(t)
        for t, ut in restore_trim:
            m["trims"][t] = ut["trim"]
            oi = m["items"].get((ut["trim"] or {}).get("id")) or {}
            if oi and ut.get("status"):
                oi.update(status=ut["status"], msg=ut.get("msg") or oi.get("msg"))
        if (m["buys"].get(X) or {}).get("id") == it["id"]:
            m["buys"].pop(X)
            st.plan.pop(X, None)
        for f in ("decided_on", "fill_day", "shares", "side", "limit"):
            it.pop(f, None)
        it.update(status="pending", hold=today, msg=msg)
        return [("warn", f"手动指令 {it['id']}：{lx} {msg}（持仓、不自动买回、闲置资金比例 / 固定口数恢复原样）")]

    @staticmethod
    def _numbers(eng, i: int, t: str) -> tuple[float, float, int]:
        """(第 i 天收盘后的总权益, t 的收盘, t 的单元)。出金预留只从「能买的钱」里扣（add_room），不改 % 目标的换算。"""
        return float(eng.equity(i)), float(eng._px_close(t, i)), (int(eng.lots[eng.col[t]]) if t in eng.col else LOT)

    def _place(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, target: int | None = None) -> None:
        """卖出全部（sell）/ 减到 pct %（trim）/ 减到 target 股（adjust 的减仓方向）→ 开盘的寄付成行卖单。"""
        t, st = it["ticker"], eng.st
        sell_all, n_sell = it["kind"] == "sell", None
        eq, px, lot = self._numbers(eng, i, t)
        if not sell_all:
            if target is None:
                target = int(math.floor(eq * float(it["pct"]) / 100 / px / lot)) * lot if px > 0 and eq > 0 else 0
            n_sell = int(ps.shares) - max(0, target)
            if n_sell <= 0:
                it.update(status="rejected", msg=f"现在 {ps.shares:,} 股约占权益 {ps.shares * px / eq * 100:.1f}%，不高于目标：不用减")
                return
            sell_all = target <= 0
        if sell_all:
            st.pending_exit[t] = "manual"
            if it["kind"] == "sell":
                self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"], it)
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(ps.shares), side="SELL",
                      msg=f"{fill_day:%m/%d} 开盘卖出全部 {ps.shares:,} 股")
        else:
            self.m["trims"][t] = {"id": it["id"], "shares": int(n_sell), "target": int(target), "decided_on": str(decided)}
            new_pct = target * px / eq * 100 if eq > 0 else 0.0
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(n_sell), side="SELL",
                      msg=f"{fill_day:%m/%d} 开盘卖出 {n_sell:,} 股（{ps.shares:,} → {target:,} 股，约占权益 {new_pct:.1f}%）")

    def _adjust(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, deciding: bool, pre=None) -> None:
        """调仓：按第 i 天收盘与权益把目标换成股数 → 少于现在 → 卖出多的部分；多于现在 → 加仓（闸门见模块说明）；一样 → 不用调。
        凑钱的卖出（fund_for）绝不变成买入；写入时预览的方向（dir）和现在换算的方向相反 → 不执行（2026-10-13）。
        pre：执行器的下单前检查（加仓时；见 _add）。"""
        t = it["ticker"]
        eq, px, lot = self._numbers(eng, i, t)
        cur = int(ps.shares)
        want = target_shares(it["unit"], it["value"], eq, px, lot)
        why = adjust_flip_why(it, cur, want)
        if why:
            it.update(status="rejected", decided_on=str(decided), msg=why)
            return
        if want == cur:
            it.update(status="rejected", msg=f"现在 {cur:,} 股，目标 {fmt_target(it)} 换算也是 {want:,} 股：不用调")
            return
        if want < cur:
            self._place(eng, i, it, ps, decided, fill_day, target=want)
            return
        if not deciding:
            it.update(wait=True, msg=_wait_text(self.clock(), fill_day))
            return
        self._add(eng, i, it, ps, decided, fill_day, want, pre=pre)

    @staticmethod
    def _pre_why(pre, t: str, i: int) -> str | None:
        """普通的买入 / 加仓：执行器的下单前检查（资格检查、立花能不能买、LU-15 前日終値；allin_check）在排进计划之前先做
        （G5 / G15；2026-10-14：以前规则先为它卖了核心 ETF、开盘时买单才被挡）→ 理由 / None。检查本身出错 → None
        （照常排进计划：发单时执行器还会再查；与「全部换成」的出错先不做不同 —— 这里没有先卖的）。"""
        if pre is None:
            return None
        try:
            return pre(t, i)
        except Exception:                                   # noqa: BLE001
            return None

    def _add(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, want: int, pre=None) -> None:
        t, st, cfg = it["ticker"], eng.st, eng.cfg
        eq, px, lot = self._numbers(eng, i, t)
        cur = int(ps.shares)
        why = entry_why(eng, t, i)
        if why:
            it.update(status="rejected", decided_on=str(decided), msg=f"不加仓：{why}")
            return
        if not (px > 0 and eq > 0):
            it.update(status="rejected", decided_on=str(decided), msg="没有收盘价 / 总权益，算不了")
            return
        why = self._pre_why(pre, t, i)
        if why:                                             # 开盘时会被挡的：不排进计划（规则不为它卖核心 ETF；G5 / G15）
            it.update(status="rejected", decided_on=str(decided), msg=f"不加仓：{why}（只做一次）")
            return
        cap_pct = MANUAL_CAP_PCT                            # 手动加仓：最多到总权益（2026-10-12；规则的新仓仍按 max_position_pct）
        cap = int(math.floor(eq * cap_pct / 100 / px / lot + 1e-9)) * lot
        add = (min(want, cap) - cur) // lot * lot
        notes = []
        if want > cap:
            notes.append(f"超过{'总权益' if cap_pct >= 100 else f'单只上限 {cap_pct:g}%'}，截到 {cap:,} 股")
        if add <= 0:
            it.update(status="rejected", decided_on=str(decided), msg=f"现在 {cur:,} 股：{cap_text(cur, px, eq, cap_pct, lot)}")
            return
        room = eng.add_room(t, i)
        if room < add:
            notes.append(f"现金只够 {room:,} 股")
            add = room
        if add <= 0:
            it.update(status="rejected", decided_on=str(decided), msg="现金 + 核心 ETF 不够买 1 个单元：不加")
            return
        gap = eng.ex["JP"].max_entry_gap_pct                # 执行器只做东证
        from .tick import round_to_tick
        lim = round_to_tick(px * (1 + gap / 100), t, "BUY")
        st.add_plan[t] = [px, int(add), str(decided), it["id"]]
        self.m["adds"][t] = {"id": it["id"], "shares": int(add), "target": cur + int(add), "decided_on": str(decided),
                             "limit": lim}
        it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(add), side="BUY", limit=lim,
                  msg=f"{fill_day:%m/%d} 开盘买入 {add:,} 股（限价 ¥{lim:,g}；{cur:,} → {cur + add:,} 股，"
                      f"约占权益 {(cur + add) * px / eq * 100:.1f}%）" + "".join(f"；{n}" for n in notes))

    def _buy(self, eng, i: int, it: dict, decided: dt.date, fill_day: dt.date, pre=None) -> None:
        """手动买入（新开仓）：与规则的新仓同一套闸门（资格检查 / 决算前 / 新仓倍数 0 / 名额），按规则的仓位或目标定股数
        （单只上限 34%、现金 + 核心 ETF 能凑出的钱），放进统一决策的 plan（开盘的寄付指値；统一决策先给它留钱）。
        pre：执行器的下单前检查（资格检查、立花能不能买、LU-15；_pre_why）—— 过不了的不排进计划（G5 / G15；2026-10-14）。"""
        t, st, cfg = it["ticker"], eng.st, eng.cfg

        def no(msg: str) -> None:
            it.update(status="rejected", decided_on=str(decided), msg=msg)
        j = eng.col.get(t)
        if t in eng.core_set:
            return no("核心 ETF 不能手动买（用「闲置资金比例」调）")
        if j is None or not eng.A.has[i, j]:
            return no(f"没有 {names.label(t)} 在 {decided} 的行情（不在股票池？停牌？）：不买")
        if t in st.plan:
            return no("已经排在开盘买入（规则的信号）：不用再点")
        why = entry_why(eng, t, i)
        if why:
            return no(f"不买：{why}")
        n_after = len(st.pos) - sum(1 for x in st.pending_exit if x in st.pos)
        if n_after + len(st.plan) >= cfg.max_positions:
            return no(f"个股名额已满（拿着 {n_after} 只" + (f" + 排定买入 {len(st.plan)} 只" if st.plan else "")
                      + f"，上限 {cfg.max_positions} 只）：要买先卖出一只")
        eq, px, lot = self._numbers(eng, i, t)
        if not (px > 0 and eq > 0):
            return no("没有收盘价 / 总权益，算不了")
        why = self._pre_why(pre, t, i)
        if why:                                             # 开盘时会被挡的：不排进计划（规则不为它卖核心 ETF；G5 / G15）
            return no(f"不买：{why}（只做一次）")
        em = float(eng._entry_mult(t, i))
        want, basis = buy_size(eng, it, eq, px, lot, em)
        cap_pct = MANUAL_CAP_PCT                            # 手动买入：最多到总权益（「按规则」的仓位本身仍 ≤ max_position_pct）
        cap = int(math.floor(eq * cap_pct / 100 / px / lot + 1e-9)) * lot
        notes = []
        if it.get("fund") == "all":                         # 其他全部卖出、只拿这只：股数 = 全卖之后能买的最多（总权益上限；再按钱截）
            want, basis = cap, "全部换成这只（按总权益）"
        elif want > cap:
            notes.append(f"超过{'总权益' if cap_pct >= 100 else f'单只上限 {cap_pct:g}%'}，截到 {cap:,} 股")
            want = cap
        if want <= 0:
            return no(f"{basis}不够买 1 个单元（{lot:,} 股 ≈ ¥{lot * px:,.0f}）：不买")
        room = eng.add_room(t, i, buffer=it.get("fund") != "all")   # 全部换成这只：不留 1% 现金缓冲，按全卖之后的钱买到最后一手（2026-10-13 用户）
        if room < want:
            notes.append(f"现金只够 {room:,} 股")
            want = room
        if want <= 0:
            return no("现金 + 核心 ETF 不够买 1 个单元：不买")
        gap = eng.ex["JP"].max_entry_gap_pct
        from .tick import round_to_tick
        lim = round_to_tick(px * (1 + gap / 100), t, "BUY")
        st.plan[t] = [px, int(want), str(decided)]
        self.m["buys"][t] = {"id": it["id"], "shares": int(want), "decided_on": str(decided), "limit": lim, "allin": it.get("fund") == "all"}
        sig = bool(eng.A.entry[i, j])
        it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(want), side="BUY", limit=lim,
                  msg=f"{fill_day:%m/%d} 开盘买入 {want:,} 股（限价 ¥{lim:,g}；约 ¥{want * px:,.0f}，约占权益 {want * px / eq * 100:.1f}%；"
                      f"{basis}）" + "".join(f"；{n}" for n in notes) + ("" if sig else "；★ 没有买入信号：是你自己的决定"))

    def trim_orders(self, st) -> list[tuple[str, int, str]]:
        """这次决策要下的减仓卖单 [(票, 股数, 指令 id)]：规则已经要全部卖的票不下（按规则的单）。"""
        out = []
        for t, x in list(self.m["trims"].items()):
            ps = st.pos.get(t)
            if ps is None:
                self.m["trims"].pop(t, None)
                continue
            if t in st.pending_exit:
                continue
            n = min(int(x["shares"]), int(ps.shares))
            if n > 0:
                out.append((t, n, x["id"]))
        return out

    # ── 成交 → 完成 ──
    def requeue(self, ticker: str, reason: str, bar: str, why: str) -> bool:
        """开盘的手动买入 / 加仓因为系统原因一股没买（异常熔断 / HALT / 开盘后补单没跑 / 请求没发出…；执行器 _system_miss）：
        不当成「没买到 → 只做一次」，指令回到「等下单」，对账之后这次的决策重新处理（闸门、股数、钱都按新的收盘再算）——
        与「这次运行不下单 → 等下一次能下单的决策」同一口径（G21；2026-10-14）。「全部换成」、撤回中的不走这里 → False（照旧 on_fill）。"""
        key = "adds" if reason == "manual_add" else "buys"
        x = self.m[key].get(ticker)
        it = self.m["items"].get((x or {}).get("id")) or {}
        if not x or x.get("allin") or it.get("fund") == "all" or it.get("cancel_req") or it.get("status") != "placed":
            return False
        self.m[key].pop(ticker, None)
        for f in ("decided_on", "fill_day", "shares", "side", "limit", "now", "fill", "hold", "wait", "tried"):
            it.pop(f, None)
        u = {k: v for k, v in (it.get("unsent") or {}).items() if k == "n"}   # 「没发出」是那一次的单（2026-10-14 复核：留着 last → 新的单下了
        if u:                                                                  # 还显示「没发出，等再下」）；连续天数 n 留着（G7）
            it["unsent"] = u
        else:
            it.pop("unsent", None)
        it.update(status="pending", msg=f"{bar} 开盘没下成（{str(why)[:120]}）→ 系统原因，不算没买到：等下一次能下单的决策")
        return True

    def _item_for(self, ticker: str, reason: str) -> dict | None:
        """这笔手动单（reason manual / manual_trim / manual_add / manual_buy）对应的、已下单的指令；没有 → None。"""
        key = {"manual_trim": "trims", "manual_add": "adds", "manual_buy": "buys"}.get(reason)
        if key:
            it = self.m["items"].get((self.m[key].get(ticker) or {}).get("id"))
            return it if it is not None and it.get("status") == "placed" else None
        skip = {(self.m["trims"].get(ticker) or {}).get("id"), (self.m["adds"].get(ticker) or {}).get("id")}
        return next((it for it in self._active_for(ticker) if it["id"] not in skip), None)

    def on_not_sent(self, ticker: str, reason: str, day: str, why: str, st=None, final: bool = False,
                    halt: bool = False, retry: bool = True) -> dict | None:
        """手动指令的单没发出（BLOCKED / REJECTED：被挡、被拒，单根本没到交易所；G7，2026-10-14：以前说明一直停在「MM/DD 开盘卖出全部」，
        看不出没发出、也不知道之后会再下）。day = 这笔单的成交日。
        卖出 / 减仓：指令留着（待卖 / 减仓照旧 → 下一次决策重新下），说明写「MM/DD 没发出（原因）→ 下一次决策再下」；
        同一条连续几个成交日没发出记进 unsent（n；HALT 的日子不算也不中断，09:30 自检 2 天以上标 ★）。
        买入 / 加仓：下单时（final=False）只记说明（被挡的同一决策之后的运行还会再试；retry=False：被券商拒绝的不再重下）；
        对账时不是系统原因（final=True）→ 结束（只做一次，on_fill 的口径），返回这条指令（作废）。"""
        it = self._item_for(ticker, reason)
        if it is None:
            return None
        day, why = str(day), str(why or "被挡")[:120]
        buy = reason in ("manual_add", "manual_buy")
        if buy and final:
            it.pop("unsent", None)
            return self.on_fill(ticker, reason, 0, 0.0, day, st, why=why, sent=False)
        u = dict(it.get("unsent") or {})
        if u.get("last") != day:
            u["msg0"] = str(it.get("msg") or "")[:300]    # 同一天之后的运行发出了 → 说明恢复（on_sent）
            if not halt:
                u["n"] = int(u.get("n") or 0) + 1
        u.update(last=day, why=why, halt=bool(halt), retry=bool(retry or not buy))
        it["unsent"] = u
        if buy:
            it["msg"] = f"{mmdd(day)} 没发出（{why}）→ " + ("之后的运行再试" if retry else "不再重下：明天早上对账之后结束（只做一次）")
        else:
            it["msg"] = f"{mmdd(day)} 没发出（{why}）→ " + ("HALT 解除后的决策再下" if halt else "下一次决策再下")
        return None

    def on_sent(self, ticker: str, reason: str, day: str, qty: int, decided: str, how: str = "开盘") -> None:
        """手动指令的单这次发出了（受理 / 状态不明；G7，2026-10-14）：清掉「没发出」的记录（同一天先没发出、之后的运行发出了 → 说明恢复）；
        卖出 / 减仓是之后的决策重新下的（成交日变了、盘中下的没成交改到开盘卖）→ 成交日、决策日、股数与说明跟着更新
        （以前一直显示第一次的成交日 / 「盘中已下单」）。how：开盘 / 当日限价（错过寄付）。"""
        it = self._item_for(ticker, reason)
        if it is None:
            return
        u = it.pop("unsent", None) or {}
        day = str(day)
        same = str(it.get("fill_day") or "") == day and not it.get("now")
        back = u.get("msg0") if u.get("last") == day else None
        if reason not in ("manual", "manual_trim") or (same and how == "开盘"):
            if same and back:
                it["msg"] = back
            return
        prev = "" if same else str(it.get("msg") or "").split(" → ")[0]
        it.pop("now", None)
        it.update(fill_day=day, decided_on=str(decided), shares=int(qty),
                  msg=f"{mmdd(day)} {how}{'卖出' if same else '再卖'} {int(qty):,} 股" + (f"（上次：{prev}）" if prev else ""))

    def on_odd(self, ticker: str, reason: str, qty: int, px: float, bar: str, rest: int) -> dict | None:
        """手动卖出全部 / 减仓成交之后，要卖的只剩零股（不足一手；立花的 API 普通注文卖不了）→ 这条指令结束（G22；2026-10-14：以前一直
        「已下单」、之后每天建一笔「零股：这笔不下」的单）。待卖由执行器去掉、减仓这里去掉；零股记在账本 odd_lots（通知 / 面板），
        在立花网站卖完说一声登记（liveu.sh adopt）。模拟账户不拆零股（整笔按模型卖，与模型相同），不会走到这里。"""
        it = self._item_for(ticker, reason)
        if it is None:
            return None
        if reason == "manual_trim":
            self.m["trims"].pop(ticker, None)
        it.pop("unsent", None)
        sold = f"{bar} {_when(it, bar)}卖出 {int(qty):,} 股 @ ¥{float(px):,.2f}；" if qty > 0 else ""
        it.update(status="done", done_on=bar, fill={"qty": int(qty), "px": round(float(px), 2)},
                  msg=f"{sold}剩 {int(rest):,} 股零股：API 卖不了，请在立花网站卖后说一声登记（adopt）")
        return it

    def on_fill(self, ticker: str, reason: str, qty: int, px: float, bar: str, st, why: str = "",
                sent: bool = True) -> dict | None:
        """执行器对账时每笔手动单（reason manual / manual_trim / manual_add / manual_buy）的结果（qty = 0：没成交；why = 单的说明）。
        bar = 成交日；盘中下的单（item 的 now，成交日同一天）写「盘中」，否则写「开盘」。
        卖出 / 减仓没成交：why（例「登记为没成交」：状态不明的单 --resolve 0 股；G11）代替「没成交」。
        买入 / 加仓一股没买、指令结束（作废，不是你撤回的）→ 记 void_on（日报「★ 手动买入作废」）并返回这条指令（执行器记 warn；G17，
        2026-10-14）；sent=False：单根本没发出（被挡 / 被拒）→ 写「没下成」。其余 → None。"""
        fill = {"qty": int(qty), "px": round(float(px), 2)}
        if reason in ("manual_add", "manual_buy"):
            add = reason == "manual_add"
            x = self.m["adds" if add else "buys"].pop(ticker, None)
            if not x:
                return None
            it = self.m["items"].get(x["id"]) or {}
            when = _when(it, bar)
            late = "；撤回来不及：交易所的单已经成交" if it.get("cancel_req") else ""
            done = "加仓完成" if add else "新仓，之后按规则止损 / 离场"
            if qty <= 0 and it.get("cancel_req"):
                it.update(status="cancelled", done_on=bar, msg=f"已撤回（{it['cancel_req']}）：{bar} 没有买")
            elif qty <= 0:
                it.update(status="rejected", done_on=bar, void_on=bar,
                          msg=f"{bar} {when}{'没买到' if sent else '没下成'}{('（' + why + '）') if why else ''}"
                              f" → 只做一次，要{'加' if add else '买'}请再点一次")
                it.pop("unsent", None)
                return it
            elif qty < int(x["shares"]):
                it.update(status="done", done_on=bar, fill=fill,
                          msg=f"{bar} {when}买入 {qty:,} 股 @ ¥{px:,.2f}（计划 {int(x['shares']):,} 股，只成交一部分；{done}）{late}")
            else:
                it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} {when}买入 {qty:,} 股 @ ¥{px:,.2f}（{done}）{late}")
            return None
        miss = f"的单{why}" if why else "没成交"             # 卖出 / 减仓没成交（why：登记为没成交，G11）
        if reason == "manual_trim":
            x = self.m["trims"].get(ticker)
            if not x:
                return None
            it = self.m["items"].get(x["id"]) or {}
            when = _when(it, bar)
            if qty <= 0:
                it["msg"] = f"{bar} {when}{miss} → 下一开盘再卖"
                return None
            left = int(x["shares"]) - int(qty)
            if left > 0 and ticker in st.pos:
                x["shares"] = left                          # 部分成交：剩下的下一次再卖
                it["msg"] = f"{bar} {when}卖出 {qty:,} 股 @ ¥{px:,.2f}，还差 {left:,} 股（下一开盘再卖）"
                return None
            self.m["trims"].pop(ticker, None)
            it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} {when}卖出 {qty:,} 股 @ ¥{px:,.2f}（减仓完成）")
            return None
        for it in self._active_for(ticker):
            if (self.m["trims"].get(ticker) or {}).get("id") == it["id"] or (self.m["adds"].get(ticker) or {}).get("id") == it["id"]:
                continue
            when = _when(it, bar)
            if ticker not in st.pos:
                it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} {when}卖出 {qty:,} 股 @ ¥{px:,.2f}（全部卖出）"
                          + ("；撤回来不及：交易所的单已经成交" if it.get("cancel_req") else ""))
            elif qty > 0:
                it["msg"] = f"{bar} {when}只成交 {qty:,} 股 @ ¥{px:,.2f}，剩下的下一开盘再卖"
            else:
                it["msg"] = f"{bar} {when}{miss} → 下一开盘再卖"
        return None

    def settle(self, st, sent: set | None = None, sent_add: set | None = None) -> list[tuple[str, str]]:
        """对账之后（或没有新交易日时下单之前）：撤回中的指令 → 交易所那边没有在途的单就撤（之后不再重下）；
        持仓已经没了的 → 完成；对账过了还没结果的加仓 → 结束；过期的「不买回」去掉；只留最近 200 条记录。
        sent / sent_add = 这次决策里已经发到交易所的手动卖单 / 买单（加仓、买入）的票。"""
        out, sent, sent_add = [], set(sent or ()), set(sent_add or ())
        for key, plan, what in (("adds", st.add_plan, "加"), ("buys", st.plan, "买")):
            for t, x in list(self.m[key].items()):           # 对账已经过了（决策日早于账本的决策日）、却没有成交记录的加仓 / 买入
                if st.last_date and str(x.get("decided_on") or "") < str(st.last_date) and t not in plan:
                    self.m[key].pop(t, None)
                    it = self.m["items"].get(x["id"]) or {}
                    if it.get("status") == "placed":
                        it.update(status="rejected", msg=f"这笔{'加仓' if what == '加' else '买入'}没有成交记录 → 结束"
                                                         f"（要{what}请再点一次）")
                        if not it.get("cancel_req"):           # 作废（不是你撤回的）：日报「★ 手动买入作废」+ warn（G17；2026-10-14）
                            it.update(done_on=st.last_date, void_on=st.last_date)
                            it.pop("unsent", None)
                            out.append(("warn", f"★ 手动{'加仓' if what == '加' else '买入'} {names.label(t)} 作废：{it['msg']}"))
        for it in self.m["items"].values():
            if it.get("status") != "placed" or it.get("kind") not in ORDER_KINDS:
                continue
            t = it.get("ticker")
            if it["kind"] == "buy":                          # 手动买入：交易所那边还没有这笔单（没发出 / 留到开盘后）→ 撤
                if (self.m["buys"].get(t) or {}).get("id") != it["id"] or not it.get("cancel_req") or t in sent_add:
                    continue
                self.m["buys"].pop(t, None)
                st.plan.pop(t, None)
                it.update(status="cancelled", msg=f"已撤回（{it['cancel_req']}）：这笔买入不下")
                out.append(("info", f"手动指令 {it['id']}：{names.label(t)} {it['msg']}"))
                continue
            mine_trim = (self.m["trims"].get(t) or {}).get("id") == it["id"]
            mine_add = (self.m["adds"].get(t) or {}).get("id") == it["id"]
            if mine_add:
                if not it.get("cancel_req") or t in sent_add:
                    continue
                self.m["adds"].pop(t, None)
                st.add_plan.pop(t, None)
                it.update(status="cancelled", msg=f"已撤回（{it['cancel_req']}）：这笔加仓不下")
                out.append(("info", f"手动指令 {it['id']}：{names.label(t)} {it['msg']}"))
                continue
            if t not in st.pos:
                if mine_trim:
                    self.m["trims"].pop(t, None)
                it.setdefault("done_on", st.last_date)
                it["status"] = "done"
                if it.get("cancel_req"):
                    it["msg"] = "撤回来不及：已经卖出了"
                continue
            if not it.get("cancel_req") or t in sent:
                continue
            if it["kind"] == "sell" or not mine_trim:
                if st.pending_exit.get(t) == "manual":
                    st.pending_exit.pop(t)
                b = self.m["blocks"].get(t)
                if b and b.get("id") == it["id"]:
                    self.m["blocks"].pop(t)
            if mine_trim:
                self.m["trims"].pop(t, None)
            it.pop("unsent", None)
            it.update(status="cancelled", msg=f"已撤回（{it['cancel_req']}）："     # G16（复核：按下单那天写，不写「明天」）
                                              + (f"{mmdd(it.get('fill_day'))} 盘中的单已失效，之后不再卖" if it.get("now") else "之后不再下这笔卖单"))
            out.append(("info", f"手动指令 {it['id']}：{names.label(t)} {it['msg']}"))
        out += self.prune_blocks(st.last_date)
        items = self.m["items"]
        if len(items) > KEEP_ITEMS:
            old = sorted(items, key=lambda x: str(items[x].get("at") or ""))[:len(items) - KEEP_ITEMS]
            self._mark_pruned([items.pop(k) for k in old if items[k].get("status") not in ACTIVE])
        return out

    def _mark_pruned(self, gone: list[dict]) -> None:
        """删掉的旧记录记进水位 manual.pruned（is_pruned 用；2026-10-14 G1）：at = 删掉过的里最晚的写入时刻（只往后走），
        ids = 正好在这个时刻写的那几条（同一秒还留着的不算删掉）。"""
        ats = [str(x.get("at") or "") for x in gone]
        if not any(ats):
            return
        p = self.m.get("pruned") or {}
        mark = max(ats + [str(p.get("at") or "")])
        ids = set(p.get("ids") or ()) if str(p.get("at") or "") == mark else set()
        ids |= {x["id"] for x, a in zip(gone, ats) if a == mark and x.get("id")}
        self.m["pruned"] = {"at": mark, "ids": sorted(ids)}

    def prune_blocks(self, last) -> list[tuple[str, str]]:
        """到期 / 解除生效的「不买回」去掉（2026-10-13：按账本的 K 线 last_date，不按时钟 —— 补跑的旧 K 线不会提前放开）：
        until < last_date（之后的决策都不挡了）→ 到期；下一根 K 线的成交日 ≥ lift_from → 解除生效。"""
        try:
            last_d = dt.date.fromisoformat(str(last)[:10]) if last else None
        except ValueError:
            last_d = None
        if last_d is None:
            return []
        out, nxt = [], next_trading_day(last_d).isoformat()
        for t, b in list(self.m["blocks"].items()):
            if b.get("lift_from") and nxt >= str(b["lift_from"]):
                self.m["blocks"].pop(t)
                out.append(("info", f"{names.label(t)} 的不自动买回已解除（{str(b['lift_from'])[5:].replace('-', '/')} 07:40 的决策起）：之后出买入信号规则可能买"))
            elif b.get("until") is not None and str(b["until"]) < last_d.isoformat():
                self.m["blocks"].pop(t)
                out.append(("info", f"{names.label(t)} 的不自动买回到期（到 {b['until']}）：之后出买入信号规则可能买回"))
        return out

    # ── 汇报 ──
    def summary(self) -> dict:
        items = sorted(self.m["items"].values(), key=lambda x: x.get("at", ""), reverse=True)
        keep = ("id", "at", "kind", "ticker", "cid", "pct", "unit", "value", "block_days", "target", "status", "msg", "decided_on",
                "fill_day", "done_on", "fill", "shares", "side", "limit", "source", "note", "cancel_req", "wait", "now", "hold",
                "unsent", "void_on", "units", "clear", "fund", "fund_for", "from_kind")   # describe 要的（固定口数 / 恢复按规则 / 全部换成；2026-10-15：日志写成「固定 1482.T 0 口」）
        return {"core_pct": self.core_pct, "core_pause": self.m.get("core_pause"), "core_signal": self.m.get("core_signal"),
                "blocks": dict(self.m["blocks"]), "trims": dict(self.m["trims"]),
                "adds": dict(self.m["adds"]), "buys": dict(self.m["buys"]), "cap_pct": self.m.get("cap_pct"),
                "max_positions": self.m.get("max_positions"),
                "items": [{k: v for k, v in it.items() if k in keep} for it in items[:30]],
                "active": sum(1 for it in items if it.get("status") in ACTIVE),
                "halt_backlog": self.halt_backlog}


def active(sm: dict | None) -> bool:
    """有手动操作在影响账户（闲置资金比例不是 100%、有「不买回」、有没完成的指令、做过卖出 / 减仓 / 加仓 / 买入）→ 与云端模拟盘不同是预期的。"""
    sm = sm or {}
    return (float(sm.get("core_pct", 100.0)) != 100.0 or bool(sm.get("blocks")) or bool(sm.get("trims"))
            or bool(sm.get("adds")) or bool(sm.get("buys")) or bool(sm.get("active"))
            or any(it.get("status") == "done" and it.get("kind") in ORDER_KINDS for it in sm.get("items") or []))


TAX_PCT = 20.315                        # 特定口座（源泉徴収あり）的税率 %：卖出的预计收益「税后约」用（只是估算）


def fee_jp(notional: float) -> float:
    """日本股票 / ETF 一笔的手续费（qbreak/fees：立花 個別コース，模拟账户也按它；只用来估算卖出收益）。"""
    from .fees import BROKERS, DEFAULT_BROKER, FeeSchedule
    tiers = BROKERS[DEFAULT_BROKER["JP"]]["markets"]["JP"].get("commission_tiers") or ()
    return FeeSchedule(tiers=tuple(tiers))(notional)


def core_cost(st: dict | None, t: str) -> dict | None:
    """核心 ETF 现在这些口数的成本：账本的成交记录（state.core_trades：[日期, 票, BUY/SELL, 口数, 成交价, 手续费]）按移动平均算
    （买入手续费算进成本；卖出按比例减）→ {"units", "avg_px"（不含手续费）, "cost"（含买入手续费）, "since"（这一段从哪天开始拿）}；
    记录对不上现在的口数（拆股、记录不全）→ None。"""
    st = st or {}
    units, cost, pcost, since = 0, 0.0, 0.0, None
    for row in st.get("core_trades") or []:
        try:
            d, tk, side, u, px, f = row[:6]
            u, px, f = int(u), float(px), float(f or 0)
        except (TypeError, ValueError):
            return None
        if tk != t or u <= 0:
            continue
        if side == "BUY":
            if units <= 0:
                since = str(d)
            units, cost, pcost = units + u, cost + u * px + f, pcost + u * px
        elif units > 0:
            k = min(u, units) / units
            cost, pcost, units = cost * (1 - k), pcost * (1 - k), units - min(u, units)
            if units == 0:
                cost, pcost, since = 0.0, 0.0, None
    held = int((st.get("core_units") or {}).get(t, 0) or 0)
    if held <= 0 or units != held:
        return None
    return {"units": units, "avg_px": pcost / units, "cost": cost, "since": since}


def est_skip(pj: dict | None, t: str | None) -> str | None:
    """t 今天已有成交、还没对账（live_ops.held_now 的 by_ticker）→ 不给卖出的预计收益（sell_estimate 按账本的成本 / 股数算，
    对账之前对不上：10/16 的 1655 早上卖了 210 口，命令行按账本 1,130 口写「卖 1,060 口约 ¥742,000」，执行器对账后只卖 850 口）→ 那句话；
    没有成交 → None。面板 /api/quotes 与 liveu.sh manual 同一个判断（2026-10-16 四次复核）。"""
    pj = pj or {}
    b = (pj.get("by_ticker") or {}).get(t) if t and pj.get("has") else None
    if not b:
        return None
    from .live_ops import hn_sp
    sw = pj.get("when_sp") or hn_sp(pj.get("when") or "下一次执行器运行")
    u = "口" if b.get("kind") == "core" else "股"
    return (f"{names.label(t)} {pj.get('day_word') or '今天'}已有成交（对账前）：成本 / {u}数{sw}对账之后才准"
            " → 预计收益对账之后再看（现在不估）")


def sell_estimate(book: dict | None, t: str, px: float | None = None, at: str | None = None, sm: dict | None = None,
                  shares: int | None = None) -> dict | None:
    """卖出的预计收益（2026-10-07 用户：「点击卖出全部的时候要显示预计收益 和买的时候股价和成交股价 收益率等等」；只展示、估算）。
    个股：成本 = 账本的买入成交价（加仓后是加权平均）× 股数 + 买入手续费（按全部股数的一笔算、卖一部分按比例）；
    「买的时候的股价」= 买入信号那天的收盘（执行器汇总的 holding_view；有的话）。核心 ETF：成交记录的移动平均（core_cost）。
    px：现价（现价接口的 Yahoo 1 分钟线）；没给 → 账本里的最近收盘。手续费按立花 個別コース（fee_jp）；收益是税前。
    shares：卖几股 / 口（默认全部）。不是拿着的票 → None；成本算不出 → 只有卖出金额（没有 pnl）。"""
    st = (book or {}).get("state") or {}
    p = (st.get("pos") or {}).get(t)
    cc = None
    if p is not None:
        if str(p.get("market") or "JP").upper() != "JP" or not str(t).upper().endswith(".T"):
            return None                                              # 美股（美元、别的手续费）不估
        kind, held = "stock", int(p.get("shares") or 0)
        entry = float(p.get("entry_px") or 0) or None
        last = float(p.get("last_close") or 0)
        info = {"entry_date": p.get("entry_date"), "hold": int(p.get("hold") or 0)}
        hv = next((r for r in (((sm or {}).get("holding_view") or {}).get("holdings") or []) if r.get("ticker") == t), None)
        w = (hv or {}).get("why") or {}
        if w.get("signal_date") and w.get("close"):
            info.update(sig_date=str(w["signal_date"]), sig_close=round(float(w["close"]), 2))
    else:
        held = int((st.get("core_units") or {}).get(t, 0) or 0)
        if held <= 0:
            return None
        kind = "core"
        cc = core_cost(st, t)
        entry = cc["avg_px"] if cc else None
        last = float((st.get("core_last") or {}).get(t) or (((book or {}).get("core_rule") or {}).get("px") or {}).get(t) or 0)
        info = {"since": cc["since"]} if cc and cc.get("since") else {}
    n = held if shares is None else max(0, min(int(shares), held))
    live = bool(px) and float(px) > 0
    price = float(px) if live else last
    if n <= 0 or not price > 0:
        return None
    proceeds = price * n
    sell_fee = fee_jp(proceeds)
    out = {"t": t, "kind": kind, "n": n, "held": held, "px": round(price, 2), "src": "live" if live else "close",
           "at": at if live else None, "close_date": st.get("last_date"), "proceeds": round(proceeds), "sell_fee": round(sell_fee),
           **info}
    if entry:
        if kind == "stock":
            cost, buy_fee = entry * n, fee_jp(entry * held) * n / held
        else:
            base = cc["cost"] * n / held
            cost = entry * n
            buy_fee = base - cost
        base = cost + buy_fee
        pnl = proceeds - sell_fee - base
        out.update(entry_px=round(entry, 2), cost=round(cost), buy_fee=round(buy_fee), pnl=round(pnl),
                   ret_pct=round((price / entry - 1) * 100, 2), net_pct=round(pnl / base * 100, 2) if base > 0 else None)
    return out


def sale_note(tag: str, now: dt.datetime) -> str:
    """卖出的成交价会是什么（估算用的一句话）：盘中 → 模拟账户按现价、立花限价 = 现价 −0.5%；其他时间 → 按开盘价（寄付）。"""
    if timing(now)[0] == "now":
        return "模拟账户：盘中马上按现价成交" if tag.startswith("paper") else "立花：盘中马上卖，限价 = 现价 −0.5%，成交价可能略低"
    return f"实际在{when_text(now)}成交，按那时的价格"


DELAY_MIN = 20                                              # Yahoo 1 分钟线大约晚这么多分钟（显示用）
NOW_BUY_BUF = 0.005                                         # 盘中买单的限价：现价 +0.5%（执行器 live_unified 用同一个数；个股不超过决策日收盘 ×1.03、
#                                                             核心 ETF 不超过 ×CORE_BUY_LIMIT 1.02：M14，2026-10-15）
SESSION_MIN = 300                                           # 东证一天的交易时间（09:00〜11:30 + 12:30〜15:30，分钟）


def order_basis(paper: bool, now: dt.datetime, side: str) -> str:
    """下单用什么价（一句话；2026-10-07 用户「现在卖出的时候看到的股价差了20分钟 不能直接知道当时股价的话能依据什么价位进行下单」）。
    页面上的现价是 Yahoo 1 分钟线（约晚 20 分钟），只用来看和估算；下单时：
    立花 + 盘中 → 执行器下单那一刻向立花取实时现在值：卖 = 限价 现在值 −0.5%、买 = 限价 min(现在值 +0.5%, 决策日收盘 ×1.03)；
    模拟账户 + 盘中 → 按执行器运行那一刻的 Yahoo 现价（也晚约 20 分钟）成交；午休 → 12:30 后场开始后同上；
    开盘前 / 收盘后 → 卖 = 寄付成行（按开盘价）、买 = 寄付指値 收盘 ×1.03（开盘价更高就不买；开盘后才处理的按实时现价、限价同上）。"""
    mode = timing(now)[0]
    if mode in ("now", "lunch"):
        head = "12:30 后场开始后，" if mode == "lunch" else ""
        if paper:
            return head + "模拟账户按执行器下单那一刻的 Yahoo 现价成交（与页面一样约晚 20 分钟" + (
                "）" if side == "SELL" else "；现价超过收盘 ×1.03 → 不买）")
        return (head + "立花在执行器下单那一刻取实时现价，" + ("限价 = 实时现价 −0.5%（成交多在限价〜现价之间）" if side == "SELL"
                else "限价 = min(实时现价 +0.5%, 收盘 ×1.03)（现价已超过收盘 ×1.03 → 不买）"))
    when = when_text(now)
    return (f"{when}按开盘价卖（寄付成行）" if side == "SELL"
            else f"{when}买：寄付指値 = 收盘 ×1.03（开盘价更高就不买；开盘后才处理的按实时现价，限价同样 ≤ 收盘 ×1.03）")


def delay_range(sigma_d: float | None, minutes: float | None) -> float | None:
    """现价晚了 minutes 分钟：这段时间里价格通常（约 95%）在 ±几 % 以内 = 2 × 日波动 × √(分钟 ÷ 一天的交易分钟)（只是估算）。"""
    try:
        s, m = float(sigma_d), float(minutes)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(s) and s > 0 and math.isfinite(m) and m > 0):
        return None
    return round(2 * s * math.sqrt(min(m, SESSION_MIN) / SESSION_MIN) * 100, 2)


def ytd_gain(book: dict | None, day) -> float | None:
    """账本里 day 那一年的已实现损益合计（円；特定口座的源泉徴収按它通算；qbreak/tax_ytd.py）。算不了 → None（照旧按单笔 20.315%）。"""
    try:
        from .tax_ytd import ytd
        return float(ytd((book or {}).get("state") or {}, str(day)[:4], upto=str(day)[:10])["gain"])
    except Exception:                                       # noqa: BLE001  只是展示
        return None


def est_lines(e: dict | None, note: str = "", ytd_gain: float | None = None) -> list[str]:
    """卖出的预计收益几行（面板的卖出确认框、命令行）：买入 → 现价 / 预计卖出 → 预计收益与收益率 → 手续费、税。"""
    if not e:
        return []
    u = "口" if e.get("kind") == "core" else "股"
    md = lambda d: str(d or "")[5:10].replace("-", "/")                 # noqa: E731
    out = []
    if e.get("kind") == "stock":
        if e.get("entry_px"):
            out.append("买入：" + (f"{md(e['sig_date'])} 收盘 {yen_px(e['sig_close'])} 出信号 → " if e.get("sig_date") else "")
                       + (f"{md(e.get('entry_date'))} " if e.get("entry_date") else "")
                       + f"成交 {yen_px(e['entry_px'])} × {e['n']:,} {u}（成本约 ¥{e['cost']:,}）")
    elif e.get("entry_px"):
        out.append(f"买入：平均成本 {yen_px(e['entry_px'])} × {e['n']:,} {u}（成本约 ¥{e['cost']:,}"
                   + (f"，{md(e['since'])} 起陆续买入" if e.get("since") else "") + "）")
    else:
        out.append("买入成本：成交记录对不上现在的口数，算不出收益（只看卖出金额）")
    hm = str(e.get("at") or "")[11:16]
    out.append((f"现价 {yen_px(e['px'])}（{hm}，Yahoo 约晚 20 分钟）" if e.get("src") == "live"
                else f"最近收盘 {yen_px(e['px'])}（{md(e.get('close_date'))}）")
               + f" → 预计卖出约 ¥{e['proceeds']:,}" + (f"（{note}）" if note else ""))
    if e.get("pnl") is not None:
        pnl = int(e["pnl"])
        out.append(f"预计收益 {_sg(pnl)}¥{abs(pnl):,}"
                   + (f"（{_sg(e['net_pct'])}{abs(e['net_pct']):.2f}%；" if e.get("net_pct") is not None else "（")
                   + f"股价 {_sg(e['ret_pct'])}{abs(e['ret_pct']):.2f}%）" + (f" · 持有 {e['hold']} 个交易日" if e.get("hold") else ""))
        fees = int(e.get("buy_fee") or 0) + int(e.get("sell_fee") or 0)
        if ytd_gain is None:
            out.append(f"已扣两边手续费约 ¥{fees:,}；税前" + (f"，税后约 ¥{round(pnl * (1 - TAX_PCT / 100)):,}（特定口座按 {TAX_PCT:g}% 算）"
                                                             if pnl > 0 else ""))
        else:                                               # T7：按今年已实现的损益通算（特定口座的源泉徴収是年内累计算的）
            from .tax_ytd import withheld
            dtax = round(withheld(float(ytd_gain) + pnl) - withheld(float(ytd_gain)))
            g = int(round(float(ytd_gain)))
            what = (f"这笔约代扣 ¥{dtax:,}，税后约 ¥{pnl - dtax:,}" if dtax > 0 else
                    f"这笔约退还已扣的 ¥{-dtax:,}" if dtax < 0 else "这笔不扣也不退")
            out.append(f"已扣两边手续费约 ¥{fees:,}；税前。按今年已实现 {_sg(g)}¥{abs(g):,} 通算：{what}"
                       f"（特定口座 {TAX_PCT:g}%，估算；以取引報告書为准）")
    else:
        out.append(f"卖出手续费约 ¥{int(e.get('sell_fee') or 0):,}")
    return out


def _sg(v) -> str:
    """正负号：0 以上 +，负数 −（与日报的写法一样）。"""
    return "+" if float(v) >= 0 else "−"


def yen_px(v) -> str:
    """股价的写法：整数不带小数（¥2,500），有零头的带到最多 2 位（¥691.67、¥893.5）。"""
    v = float(v)
    return f"¥{v:,.0f}" if abs(v - round(v)) < 0.005 else "¥" + f"{v:,.2f}".rstrip("0").rstrip(".")


def signal_text(sg: dict | None) -> str:
    """闲置资金 ETF 的买入信号一句话：规则想买 1545 纳斯达克 100 约 110 口（约 ¥2,277,000）（票写「代码 名字」：2026-10-15 用户：只写代码不知道是哪只）。"""
    xs = [f"{names.label(x['ticker'])} 约 {int(x.get('units') or 0):,} 口" + (f"（约 ¥{float(x['yen']):,.0f}）" if x.get("yen") else "")
          for x in (sg or {}).get("items") or []]
    return "规则想买 " + "、".join(xs) if xs else "规则想买核心 ETF"


def lines(sm: dict | None, today: str | None = None, now: dt.datetime | None = None, book: dict | None = None,
          tag: str | None = None) -> list[str]:
    """日志 / 通知用：手动指令的几行（没有就空）。today = 这一天完成的也列出来；now → 状态按那一刻（盘中没下成、改到开盘：G18）。
    book（manual list）→ 还没照它调的固定口数写「生效中 · 还没照它调」（fix_status_text）。"""
    sm = sm or {}
    out = []
    cp, sg = sm.get("core_pause"), sm.get("core_signal")
    if cp:
        out.append(f"- 闲置资金买入 ETF：停着（{cp.get('since') or '—'} 起" + (f"，卖出 {names.label(cp['ticker'])}" if cp.get("ticker") else "")
                   + "）：钱留现金；出现买入信号会提醒，你确认才买")
    elif float(sm.get("core_pct", 100.0)) != 100.0:
        out.append(f"- 闲置资金比例：手动设为规则目标额的 {float(sm['core_pct']):g}%（改回 100% 就照规则）")
    if cp and sg:
        out.append(f"- ★ 闲置资金 ETF 买入信号（{sg.get('date')} 收盘）：" + signal_text(sg)
                   + "：确认后才买（面板「确认买入」，或 liveu.sh manual core --pct 100）")
    if sm.get("halt_backlog"):                              # 这次运行：HALT 解除后照原样执行的积压指令（2026-10-13）
        out.append(f"- ★ {sm['halt_backlog']}")
    for t, b in (sm.get("blocks") or {}).items():
        out.append(f"- {names.label(t)}：不自动买回（{block_text(b)}）")
    for it in sm.get("items") or []:
        if it.get("status") in ACTIVE or (today and str(it.get("done_on") or "") >= today) \
                or (today and str(it.get("at") or "")[:10] >= today):
            m = msg_text(it, now)
            st = (fix_status_text(it, sm.get("items") or [], book, tag) if book is not None else None) or status_text(it, now)
            out.append(f"- 手动 {describe(it)}：{st}" + (f"（{m}）" if m else ""))
    return out


__all__ = ["KINDS", "POS_KINDS", "ORDER_KINDS", "UNITS", "BUY_UNITS", "BLOCK_DEFAULT", "CAP_PCT", "MAX_POS", "SESSION", "Manual",
           "append", "read_all", "read_known", "is_pruned", "KEEP_ITEMS", "PAPER_IDLE", "paper_refuse", "unseen", "cancelled", "normalize", "batch_blocks", "lifting", "unblock_why", "lift_day", "rebuy_day",
           "block_text", "FIX_WAIT", "fix_status_text", "core_pending", "core_wait", "NEXT_DECISION", "next_decision", "RUN_AT", "HALT_WAIT_MSG", "HALT_DONE_MSG", "HALT_CORE_MSG", "HALT_CORE_AFTER", "halt_text", "halt_core", "halt_core_line", "mmdd", "check", "slots", "core_tickers", "core_info", "core_rec", "core_pct_for", "core_effects", "core_lot", "core_u100_est", "core_u100s", "core_fixed", "orders_today", "busy_today", "today_why", "OPEN_ST",
           "corefix_clear_text", "resume_info", "wait_word", "wait_text", "fix_applied", "corefix_pending", "allin_busy_text", "order_basis", "delay_range", "DELAY_MIN", "timing", "when_text", "when_for", "morning_behind",
           "next_window", "due", "cancel_due", "CANCEL_UNTIL", "grp_wait_stale", "cancel_cids", "handling_cids", "group_prune",
           "RULE_TEXT", "UNK_LATER", "UNK_LATER_BUY", "NOW_NO_CANCEL", "NOW_FILLED_NO_CANCEL", "NOW_BUY_LAPSED", "NOW_SELL_WITHDRAWN", "now_sell_withdrawn", "now_lapsed", "now_expired", "now_cancel_why",
           "now_due", "status_text", "hold_text", "rolled_over", "rolled_text", "msg_text", "entry_why", "buy_size", "requests_path", "position_pct", "target_shares", "adjust_plan",
           "cap_text", "fmt_target", "describe", "active", "lines", "signal_text", "core_pct_now",
           "fee_jp", "core_cost", "est_skip", "sell_estimate", "sale_note", "est_lines", "yen_px", "TAX_PCT", "LABEL", "STATUS", "REASON_TEXT"]
