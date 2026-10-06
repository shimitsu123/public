"""nisa_tax_study.py — 税后收益 × 新 NISA：同一套交易放在哪个账户（特定口座 / NISA 成長投資枠）税后留下的最多（登记检验；会计口径）。
（2026-10-06 用户：「结合现在的研究结果 还有哪些方向可以提高收益率和胜率 继续研究」）
规则先提交（登记）再运行一次；看到结果之后不改规则。

〇 为什么做这个（照实写）
  1 以前的全部研究都按税前比：年化、Calmar、每笔都没扣 20.315% 的税；用户实际留下的是税后。B4 的个股层每年 3〜6 笔，核心 ETF（1545 / 1482）
    随个股买卖（日元不够时卖核心补）与美股牛熊切换反复卖出 → 收益多半当年实现、当年交税。
  2 「找新规则」：2026-10-04 检验力测算后的独立扫描，剩下的方向两关都过的概率都 < 3%；放哪个账户是会计问题，不靠统计运气。
    手续费方案已比较过（立花 vs 楽天，scripts/broker_cost_study.py）；税与 NISA 没做过。
  3 事实（2026-10-06 联网核对，仅对检索时点有效）：上場株式等の譲渡益 20.315%（所得税 15% + 復興特別所得税 0.315% + 住民税 5%）；
    特定口座・源泉徴収あり = 每次卖出按「年初以来的净收益」代扣（同年内亏损自动退还），1 月 1 日重新算；年度净亏损向后 3 年结转要自己确定申告；
    新 NISA 成長投資枠：每年 240 万円（按买入金额）、保有上限 1,200 万円（总 1,800 万円；按簿价）、卖出的簿价第二年恢复；收益免税；
    NISA 的亏损不能与特定口座相抵、不能结转；NISA 一年只能在一家金融机构；立花 e支店 只有成長投資枠、ETF 可以（分配金免税要选株式数比例配分方式）；
    1545（NEXT FUNDS NASDAQ-100 不对冲，nextfunds.jp）与 1482（iシェアーズ・コア 米国債 7-10 年 円ヘッジ，ブラックロック / JPX 资料）都是成長投資枠对象。
  4 登记前只看了个数（没有任何税后结果；临时结构检查）：B4 账本 个股 Z 28 / E 34 / J 52 笔，核心 ETF 成交 Z 63 / E 73 / J 105 次（只有 1545 / 1482），
    每年买入额 ÷ 当年平均权益 的中位 Z 2.07 / E 1.33 / J 2.57 倍（最少 0.72、最多 5.98）→ ¥100 万时一年的买入大约 ¥130〜260 万，与 240 万的额度同一个量级。

一 基准与输入：B4 = B3 + TBF（模拟盘 2026-10-05 收盘的决策起的规则；规则指纹 1241753c8f2529c6）。每个年代（Z 2001-01-04〜2006-09-30、
  E 2006-10-01〜2016-09-30、J 2017-01-04〜2026-09-30）跑一次 B4（研究引擎，¥100 万起），取它的账本：个股成交（买卖日、价、股数、含两边手续费的盈亏）、
  核心 ETF 成交（日、票、买 / 卖、口数、价、手续费）、每天的税前权益、期末还拿着的核心 ETF。
  先决条件：规则指纹 = 1241753c8f2529c6、B4 重算的 Calmar = turn_shape_combo 结果文件里 TBF 的（三个年代差 ≤ 0.0005）；不满足就停。
  交易本身一笔都不改：税只叠在账本上（会计口径）。年化等按引擎全期的每日权益算（E 比研究的窗口多最后一天 2016-09-30；各做法同一口径）。

二 税怎么算（全部做法共用）
  - 个股一笔的应税收益 = 账本的盈亏（卖出额 − 买入额 − 两边手续费，= 譲渡価額 − 取得費 − 委託手数料）。
  - 核心 ETF：每个账户、每只票按移动平均算成本（买入手续费计入成本）；卖出的收益 = 口数 × 价 − 卖出手续费 − 平均成本 × 口数。
  - 特定口座（源泉徴収あり）：G = 当年到这一笔为止的净收益（只算特定口座的部分）；代扣累计 = 20.315% × max(0, G)；每次卖出付「代扣累计的增加」
    （减少 = 退还）；每年最后一个交易日结束后 G、代扣归零（亏损不结转）。
  - 一天之内的顺序与引擎相同：个股卖 → 核心卖 → 个股买 → 核心买（同类按账本的先后）。
  - 年代最后一天：全部清算 —— 引擎期末强平的个股（reason = end）照账本卖出，剩下的核心 ETF 按最后收盘价、引擎的卖出手续费卖出 →
    特定口座部分照样交税（=「清算口径」：没实现的收益也扣掉将来要交的税；NISA 的不扣）。
  - NISA（成長投資枠）：每年（1〜12 月）买入金额（价 × 口数 / 股数，不含手续费）≤ 240 万円；NISA 里持有的簿价 + 今年卖掉的簿价 ≤ 1,200 万円
    （卖掉的簿价 1 月 1 日起恢复）；NISA 的收益不交税、亏损不能抵也不能结转。一笔买入超过剩下的额度 → 按比例（可以是零头）放 NISA、其余放特定口座。
    两个账户手续费相同（立花 NISA 的手续费没有公开 → 对 NISA 保守）。
  - 规模：账户 A = ¥100 万（判定用）、¥300 万、¥1,000 万（只描述）；账本金额 × A ÷ ¥100 万 当作真实金额（假设同一套交易按比例放大；
    大账户能买的一手更多、真实成交会不同 → 只描述）。
  - 税后账户 = 税前账户的「缩小版」：比例 s 从 1 开始，每付（退）一次税 s ← s − 付款 ÷（A ÷ 100 万 × 那天的税前权益）；
    之后真实的收益、买入金额 = 账本 × A ÷ 100 万 × s。税后权益（每天收盘）= A ÷ 100 万 × s × 税前权益；最后一天是扣完清算的税之后的。

三 做法（6 个；交易全部相同，只有放哪个账户 / 怎么结转不同）
  P0  全部特定口座（源泉徴収あり）、不申告 —— 现在默认的口径。
  P0c P0 + 每年确定申告：年度净亏损向后 3 年结转，之后 3 年里有净收益的那一年退还（简化在那一年最后一个交易日退；实际 3〜5 个月后到账）。只描述。
  N1  NISA 优先：每一笔买入（个股、核心 ETF）先放 NISA（额度内），其余特定口座；核心卖出先卖特定口座的（留住 NISA 里的长期仓）。
  N2  只核心放 NISA：1545 / 1482 的买入先放 NISA；个股全放特定口座；核心卖出先卖特定口座的。
  N3  只个股放 NISA：个股的买入先放 NISA；核心全放特定口座。
  N4  NISA 优先（同 N1），但核心卖出先卖 NISA 的（让簿价第二年恢复成额度）。
  N1〜N4 的特定口座部分与 P0 相同（源泉徴収あり、不申告、不结转）。

四 判定（运行前写定）
  主指标 = ¥100 万时的税后年化（清算口径；Z / E / J 各一个：(最后一天 ÷ 第一天)^(1 ÷ 年数) − 1）。
  「推荐」= N1〜N4 里同时满足：a 三个年代税后年化都 ≥ P0 + 0.5 pp；b 三个年代税后最大回撤（每日税后权益）都不比 P0 深 2 pp 以上。
  满足的不止一个 → 取三个年代里「比 P0 多的最小值」最大的那个；差 < 0.01 pp 算相同，按 N2 → N3 → N1 → N4（实现越简单越先）。没有满足的 →「不推荐」。
  「推荐」也只是提议：NISA 一年只能在一家金融机构开，要由用户决定（用户现在的 NISA 在哪里、今年用了多少额度都不知道）；
  执行器要能按单指定课税区分（立花 API 的 sZyoutoekiKazeiC）、记录额度 / 簿价、两个账户分别对账 —— 另外做工程与测试；模拟盘 / 执行器不因这次研究改。
  P0c 只描述（申告的价值）。
五 事前预期（运行前写）：P0 比税前少约 2〜3.5 pp / 年（税前年化的 15〜20%）；N1 / N2 在 ¥100 万时多 +1〜2.5 pp、¥1,000 万时只剩 +0.3〜1 pp；
  N3 只 +0.2〜0.8 pp（个股层小，亏损放进 NISA 还浪费抵扣）；N4 比 N1 差；P0c 比 P0 多 0〜0.3 pp。最可能「推荐」N1 或 N2（约 70%）。
六 另报（只描述）：税前 vs 各做法税后（年化 / 最大回撤 / Calmar / 期末 ¥）、交的税合计、特定口座实现的收益按层（个股 / 核心）分；
  NISA：放进 NISA 的买入额与占比、额度用满的月份、NISA 里免掉的收益与浪费的亏损；¥300 万 / ¥1,000 万 的同一张表；J 每年的税前 / 税后收益。
七 局限：今天的税制与新 NISA 规则套到 2001〜2026（假设；NISA 2014 年才有、新 NISA 2024 年起；2013 年以前是 10% 优惠税率）；交易不变、税后账户按比例缩小
  （整数手、真实的一手限制忽略；NISA 按比例拆零头）；分配金 / 分红包含在复权价里 → 只在卖出时交税（特定口座实际每次到账就扣 → P0 略偏乐观、
  NISA 的好处略偏小）；确定申告的退税时点简化在年末；住民税在 20.315% 里、不考虑配当控除 / 总合课税 / 与分红的损益通算；
  不考虑用户其他账户的收益与亏损；NISA 的买入手续费按特定口座的算（保守）。非投资建议、也不是税务意见（以税务署 / 税理士 / 立花的说明为准）。
输出：var/out/nisa_tax_study.md / .json（只有统计，不含个股代码）。
  python scripts/nisa_tax_study.py --run    （登记之后只运行一次）
"""
from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TAX = 0.20315
QUOTA_Y = 2_400_000.0
CAP = 12_000_000.0
BASE = 1_000_000.0                                                           # 研究引擎的起始资金（var/sim.json capital_jpy）
SIZES = (1_000_000, 3_000_000, 10_000_000)
DECIDE_SIZE = 1_000_000
POLICIES = ("P0", "P0c", "N1", "N2", "N3", "N4")
CANDS = ("N1", "N2", "N3", "N4")
TIE_ORDER = ("N2", "N3", "N1", "N4")
LABEL = {"P0": "全部特定口座", "P0c": "特定口座 + 申告结转", "N1": "NISA 优先（先卖特定）", "N2": "只核心放 NISA",
         "N3": "只个股放 NISA", "N4": "NISA 优先（先卖 NISA）"}
MIN_GAIN, DD_TOL, TIE_EPS = 0.5, 2.0, 0.01
CARRY_YEARS = 3
ERAS = ("Z", "E", "J")
FP = "1241753c8f2529c6"                                                      # B4 = B3 + TBF 的模拟盘规则指纹
B4_TOL = 0.0005
EPS = 1e-9
ORDER = {"SELL_S": 0, "SELL_C": 1, "BUY_S": 2, "BUY_C": 3}                   # 一天之内：个股卖 → 核心卖 → 个股买 → 核心买（与引擎相同）
OUT_MD, OUT_JSON = "nisa_tax_study.md", "nisa_tax_study.json"


def flags(policy: str) -> dict:
    """做法 → {stock_nisa: 个股买入先放 NISA, core_nisa: 核心买入先放 NISA, nisa_first_sell: 核心卖出先卖 NISA 的, carry: 申告结转}。"""
    if policy not in POLICIES:
        raise ValueError(f"没有这个做法：{policy}")
    return {"stock_nisa": policy in ("N1", "N3", "N4"), "core_nisa": policy in ("N1", "N2", "N4"),
            "nisa_first_sell": policy == "N4", "carry": policy == "P0c"}


# ───────────────────────── 账本 → 事件 ─────────────────────────
def build_events(trades: list[dict], core: list) -> list[tuple]:
    """→ [(日期, 顺序, 序号, 种类)]：个股 BUY_S（买入日）+ SELL_S（卖出日；reason = end 的不在这里 → 期末清算），核心 BUY_C / SELL_C。
    按日期 → 一天之内的顺序（ORDER）→ 账本里的先后 排。"""
    ev = []
    for k, t in enumerate(trades):
        ev.append((pd.Timestamp(t["entry_date"]), ORDER["BUY_S"], k, "BUY_S"))
        if t.get("reason") != "end":
            ev.append((pd.Timestamp(t["exit_date"]), ORDER["SELL_S"], k, "SELL_S"))
    for k, c in enumerate(core):
        kind = "BUY_C" if str(c[2]).upper() == "BUY" else "SELL_C"
        ev.append((pd.Timestamp(c[0]), ORDER[kind], k, kind))
    ev.sort(key=lambda x: (x[0], x[1], x[2]))
    return ev


# ───────────────────────── 税后叠加（纯函数，有测试） ─────────────────────────
class _Book:
    """一个做法 × 一个规模的账户状态。金额：real = 真实 ¥；ledger = 账本 ¥（引擎 ¥100 万起）。"""

    def __init__(self, policy: str, A: float, eq: pd.Series):
        self.f = flags(policy)
        self.k = float(A) / BASE
        self.eq = eq
        self.s = 1.0
        self.G = 0.0                                                         # 当年特定口座的净收益（real）
        self.Wh = 0.0                                                        # 当年代扣累计（real）
        self.carry: list[list] = []                                          # [[年, 剩下可结转的亏损（real）]]
        self.used = 0.0                                                      # 当年 NISA 买入额（real）
        self.held = 0.0                                                      # NISA 持有簿价（real）
        self.sold = 0.0                                                      # 今年卖掉的 NISA 簿价（1 月 1 日恢复）
        self.frac: dict[int, float] = {}
        self.book: dict[int, float] = {}
        self.acc: dict[str, dict] = {}
        self.st = {"tax_paid": 0.0, "tax_year": {}, "real_stock": 0.0, "real_core": 0.0, "nisa_buy": 0.0, "all_buy": 0.0,
                   "nisa_gain": 0.0, "nisa_loss": 0.0, "quota_full": {}, "carry_refund": 0.0}

    # 付税 / 退税：s 按那天的税前权益缩小（放大）
    def pay(self, amt: float, d) -> None:
        if abs(amt) < EPS:
            return
        self.s -= amt / (self.k * float(self.eq.loc[d]))
        self.st["tax_paid"] += amt
        y = str(pd.Timestamp(d).year)
        self.st["tax_year"][y] = self.st["tax_year"].get(y, 0.0) + amt

    def realize(self, g: float, d, layer: str) -> None:
        """特定口座实现收益 g（real）：源泉徴収あり 按年初以来的净额补扣 / 退还。"""
        self.G += g
        self.st["real_stock" if layer == "S" else "real_core"] += g
        w = TAX * max(0.0, self.G)
        self.pay(w - self.Wh, d)
        self.Wh = w

    def room(self) -> float:
        return max(0.0, min(QUOTA_Y - self.used, CAP - self.held - self.sold))

    def alloc(self, p_real: float, on: bool, d) -> float:
        """一笔买入（real 金额）放 NISA 的比例。"""
        self.st["all_buy"] += p_real
        if not on or p_real <= 0:
            return 0.0
        f = min(1.0, self.room() / p_real)
        self.used += f * p_real
        self.held += f * p_real
        self.st["nisa_buy"] += f * p_real
        y = str(pd.Timestamp(d).year)
        if y not in self.st["quota_full"] and self.used >= QUOTA_Y - 1.0:
            self.st["quota_full"][y] = pd.Timestamp(d).month
        return f

    def nisa_result(self, g: float) -> None:
        if g >= 0:
            self.st["nisa_gain"] += g
        else:
            self.st["nisa_loss"] += g

    def release(self, b: float) -> None:
        self.held -= b
        self.sold += b
        if self.held < 0 and self.held > -1e-6:
            self.held = 0.0

    # ── 个股 ──
    def buy_stock(self, k: int, t: dict, d) -> None:
        p = self.k * self.s * float(t["entry_px"]) * float(t["shares"])
        f = self.alloc(p, self.f["stock_nisa"], d)
        self.frac[k], self.book[k] = f, f * p

    def sell_stock(self, k: int, t: dict, d) -> None:
        g = self.k * self.s * float(t["pnl"])
        f = self.frac.pop(k, 0.0)
        b = self.book.pop(k, 0.0)
        if f > 0:
            self.nisa_result(f * g)
            self.release(b)
        if f < 1.0:
            self.realize((1.0 - f) * g, d, "S")

    # ── 核心 ETF ──
    def _a(self, tk: str) -> dict:
        return self.acc.setdefault(tk, {"uT": 0.0, "cT": 0.0, "uN": 0.0, "cN": 0.0, "bN": 0.0})

    def buy_core(self, tk: str, units: float, px: float, fee: float, d) -> None:
        a = self._a(tk)
        notional = float(units) * float(px)
        f = self.alloc(self.k * self.s * notional, self.f["core_nisa"], d)
        a["uN"] += f * units
        a["cN"] += f * (notional + fee)
        a["bN"] += f * self.k * self.s * notional
        a["uT"] += (1.0 - f) * units
        a["cT"] += (1.0 - f) * (notional + fee)

    def sell_core(self, tk: str, units: float, px: float, fee: float, d) -> None:
        a = self._a(tk)
        units = float(units)
        have = a["uT"] + a["uN"]
        if units > have * (1 + 1e-9) + 1e-6:
            raise ValueError(f"{tk} {d}：卖 {units} 口 > 账上 {have} 口（账本对不上 → 停）")
        units = min(units, have)
        if self.f["nisa_first_sell"]:
            xN = min(units, a["uN"])
            xT = units - xN
        else:
            xT = min(units, a["uT"])
            xN = units - xT
        xT, xN = min(xT, a["uT"]), min(xN, a["uN"])
        tot = xT + xN
        if xT > EPS:
            cost = a["cT"] * xT / a["uT"]
            g = xT * px - (fee * xT / tot if tot > 0 else 0.0) - cost
            a["cT"] -= cost
            a["uT"] -= xT
            if a["uT"] < 1e-9:
                a["uT"], a["cT"] = 0.0, 0.0
            self.realize(self.k * self.s * g, d, "C")
        if xN > EPS:
            cost = a["cN"] * xN / a["uN"]
            b = a["bN"] * xN / a["uN"]
            g = xN * px - (fee * xN / tot if tot > 0 else 0.0) - cost
            a["cN"] -= cost
            a["bN"] -= b
            a["uN"] -= xN
            if a["uN"] < 1e-9:
                a["uN"], a["cN"], a["bN"] = 0.0, 0.0, 0.0
            self.nisa_result(self.k * self.s * g)
            self.release(b)

    # ── 年末 ──
    def year_end(self, y: int, d) -> None:
        if self.f["carry"]:
            if self.G < 0:
                self.carry.append([y, -self.G])
            elif self.G > 0:
                left = self.G
                for c in sorted(self.carry, key=lambda r: r[0]):
                    if not (y - CARRY_YEARS <= c[0] <= y - 1) or left <= 0:
                        continue
                    u = min(left, c[1])
                    c[1] -= u
                    left -= u
                used = self.G - left
                if used > 0:
                    self.pay(-TAX * used, d)
                    self.st["carry_refund"] += TAX * used
            self.carry = [c for c in self.carry if c[0] >= y - CARRY_YEARS + 1 and c[1] > EPS]
        self.G, self.Wh = 0.0, 0.0
        self.used, self.sold = 0.0, 0.0


def overlay(trades: list[dict], core: list, eq: pd.Series, policy: str, A: float, end_core: dict) -> dict:
    """账本 → 税后每日权益（real ¥）与统计。eq = 税前每日权益（账本 ¥，日期顺序）；end_core = {票: (口数, 最后收盘价, 卖出手续费)}。"""
    eq = eq.sort_index()
    B = _Book(policy, A, eq)
    ev = build_events(trades, core)
    days = eq.index
    bad = [e for e in ev if e[0] not in eq.index]
    if bad:
        raise ValueError(f"有 {len(bad)} 个成交日不在权益的日期里（第一个 {bad[0][0].date()}）→ 停")
    by_day: dict = {}
    for e in ev:
        by_day.setdefault(e[0], []).append(e)
    out = np.empty(len(days))
    last = len(days) - 1
    for i, d in enumerate(days):
        for _, _, k, kind in by_day.get(d, ()):
            if kind == "BUY_S":
                B.buy_stock(k, trades[k], d)
            elif kind == "SELL_S":
                B.sell_stock(k, trades[k], d)
            else:
                c = core[k]
                (B.buy_core if kind == "BUY_C" else B.sell_core)(str(c[1]), float(c[3]), float(c[4]), float(c[5]), d)
        if i == last:                                                        # 期末清算：强平的个股 + 剩下的核心 ETF
            for k, t in enumerate(trades):
                if t.get("reason") == "end":
                    B.sell_stock(k, t, d)
            for tk, (u, px, fee) in sorted(end_core.items()):
                a = B._a(tk)
                have = a["uT"] + a["uN"]
                if abs(have - float(u)) > 1e-6 * max(1.0, float(u)):
                    raise ValueError(f"{tk} 期末：账本叠加后 {have} 口 ≠ 引擎 {u} 口 → 停")
                if u > 0:
                    B.sell_core(tk, float(u), float(px), float(fee), d)
            left = sum(a["uT"] + a["uN"] for a in B.acc.values())
            if left > 1e-6 or B.frac:
                raise ValueError("期末清算后还有没卖的仓 → 停")
        if i == last or days[i + 1].year != d.year:
            B.year_end(d.year, d)
        out[i] = B.k * B.s * float(eq.iloc[i])
    ser = pd.Series(out, index=days)
    st = dict(B.st)
    st["nisa_share"] = (st["nisa_buy"] / st["all_buy"] * 100 if st["all_buy"] > 0 else 0.0)
    return {"series": ser, "stats": st, "s_end": B.s}


def stats_of(series: pd.Series) -> dict:
    """全期每日权益 → 年化 %、最大回撤 %、Calmar、期末 / 起点（与 capital_study.seg_stats 同一算法，不截窗口）。"""
    e = series.dropna()
    if len(e) < 20 or e.iloc[0] <= 0:
        return {"cagr": None, "dd": None, "calmar": None, "final": None, "mult": None}
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = ((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs > 0 else None
    dd = float((e / e.cummax() - 1).min() * 100)
    return {"cagr": None if cagr is None else round(float(cagr), 3), "dd": round(dd, 3),
            "calmar": None if cagr is None or dd >= 0 else round(float(cagr) / abs(dd), 3),
            "final": round(float(e.iloc[-1]), 0), "mult": round(float(e.iloc[-1] / e.iloc[0]), 4)}


def yearly(series: pd.Series) -> dict[str, float]:
    e = series.dropna()
    ye = e.groupby(e.index.year).last()
    prev = pd.concat([pd.Series([e.iloc[0]], index=[ye.index[0] - 1]), ye.iloc[:-1]])
    return {str(y): round(float(ye[y] / prev.iloc[k] - 1) * 100, 2) for k, y in enumerate(ye.index)}


def judge(at: dict) -> dict:
    """at = {做法: {年代: {cagr, dd}}}（¥100 万、税后）→ {per: {做法: {ok, fails, gain}}, pick}（四 a / b 与选法）。"""
    base = at["P0"]
    per = {}
    for p in CANDS:
        fails, gains = [], []
        for e in ERAS:
            x, y = at[p][e], base[e]
            if None in (x.get("cagr"), y.get("cagr"), x.get("dd"), y.get("dd")):
                fails.append(f"{e} 没有值")
                continue
            g = float(x["cagr"]) - float(y["cagr"])
            gains.append(g)
            if g < MIN_GAIN - 1e-9:
                fails.append(f"a {e} 税后年化 {x['cagr']:.2f}% < P0 {y['cagr']:.2f}% + {MIN_GAIN} pp")
            if float(x["dd"]) < float(y["dd"]) - DD_TOL - 1e-9:
                fails.append(f"b {e} 税后回撤 {x['dd']:.2f}% 比 P0 {y['dd']:.2f}% 深 {DD_TOL:.0f} pp 以上")
        per[p] = {"ok": not fails, "fails": fails, "gain": (round(min(gains), 3) if gains else None)}
    ok = [p for p in CANDS if per[p]["ok"]]
    pick = None
    if ok:
        best = max(per[p]["gain"] for p in ok)
        tied = [p for p in ok if best - per[p]["gain"] < TIE_EPS]
        pick = sorted(tied, key=TIE_ORDER.index)[0]
    return {"per": per, "pick": pick}


# ───────────────────────── 运行（登记之后只一次） ─────────────────────────
def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/nisa_tax_study.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def tbf_flags(W: dict, say=print) -> dict:
    """TBF 的旗子：policy_allin_study --prep 的缓存（同一套）；没有就按 turn_shape_combo 重算。先决条件（B4 重算 = TBF）会再核一次。"""
    from qbreak import paths
    cp = paths.sub("cache") / "policy_allin_prep.pkl"
    if cp.exists():
        with open(cp, "rb") as f:
            return {e: np.asarray(v, bool) for e, v in pickle.load(f)["tbf"].items()}
    import turn_shape_combo as TC
    F = TC.load_flags(W, TC.load_models(say)["fits"], say)
    return {e: np.asarray(v, bool) for e, v in TC.gates_of(W, F, "TBF").items()}


def ledger_of(eng) -> dict:
    st = eng.st
    trades = [dict(x) for x in st.trades]
    for t in trades:
        if t.get("market", "JP") != "JP":
            raise SystemExit("账本里有日本以外的个股 → 这个研究只按日本股票算 → 停")
    core = [tuple(x) for x in st.core_trades]
    eq = pd.Series({pd.Timestamp(h[0]): float(h[1]) for h in st.history}).sort_index()
    end_core = {}
    for t, u in st.core_units.items():
        if u and u > 0:
            px = float(st.core_last[t])
            end_core[t] = (float(u), px, float(eng.c_fee[t]["SELL"](u * px)))
    return {"trades": trades, "core": core, "eq": eq, "end_core": end_core}


def run(say=print) -> dict:
    import jq_study as JS
    import loop10_common as C10
    import loop9_common as C9
    import research_loop as RL
    from qbreak import paths
    t0 = time.time()
    fp_now = RL.rules_fingerprint(paths.PROJECT_ROOT / "var")
    if fp_now != FP:
        raise SystemExit(f"先决条件不满足：模拟盘规则指纹 {fp_now} ≠ 登记时的 {FP} → 停")
    W = C10.load()
    say(f"载入 B3 + Zx：{time.time() - t0:.0f}s")
    tbf = tbf_flags(W, say)
    ref = json.loads((paths.PROJECT_ROOT / "var" / "out" / "turn_shape_combo.json").read_text(encoding="utf-8"))["cand"]["TBF"]
    res: dict = {"git": git_info(), "fingerprint": fp_now, "base": {}, "pre": {}, "ledger": {}, "at": {}, "yearly_J": {}}
    for e in ERAS:
        S = C9.signals(W, e)
        g = tbf[e]
        if len(g) != len(S):
            raise SystemExit("TBF 旗子与信号对不上 → 停")
        b4 = C9.acct(C9.run_block(W, e, g))
        if abs(float(b4["calmar"]) - float(ref[e]["calmar"])) > B4_TOL:
            raise SystemExit(f"先决条件不满足：{e} B4 重算 Calmar {b4['calmar']} ≠ turn_shape_combo 的 TBF {ref[e]['calmar']} → 停")
        L = ledger_of(JS.RealLotEngine.LAST[-1])
        res["base"][e] = b4
        res["pre"][e] = stats_of(L["eq"] * (DECIDE_SIZE / BASE))
        res["ledger"][e] = {"stock_trades": len(L["trades"]), "stock_end": sum(1 for t in L["trades"] if t.get("reason") == "end"),
                            "core_trades": len(L["core"]), "core_sells": sum(1 for c in L["core"] if str(c[2]).upper() == "SELL"),
                            "core_end": {t: round(v[0], 2) for t, v in L["end_core"].items()}, "days": int(len(L["eq"])),
                            "first": str(L["eq"].index[0].date()), "last": str(L["eq"].index[-1].date())}
        say(f"{e}：B4 重算 = turn_shape_combo 的 TBF（Calmar {b4['calmar']}）；个股 {len(L['trades'])} 笔、核心 {len(L['core'])} 次；{time.time() - t0:.0f}s")
        for A in SIZES:
            for p in POLICIES:
                o = overlay(L["trades"], L["core"], L["eq"], p, A, L["end_core"])
                st = o["stats"]
                row = {**stats_of(o["series"]), "tax_paid": round(st["tax_paid"], 0), "real_stock": round(st["real_stock"], 0),
                       "real_core": round(st["real_core"], 0), "nisa_buy": round(st["nisa_buy"], 0), "all_buy": round(st["all_buy"], 0),
                       "nisa_share": round(st["nisa_share"], 2), "nisa_gain": round(st["nisa_gain"], 0), "nisa_loss": round(st["nisa_loss"], 0),
                       "quota_full": st["quota_full"], "carry_refund": round(st["carry_refund"], 0),
                       "tax_year": {y: round(v, 0) for y, v in sorted(st["tax_year"].items())}}
                res["at"].setdefault(str(A), {}).setdefault(p, {})[e] = row
                if e == "J" and A == DECIDE_SIZE:
                    res["yearly_J"][p] = yearly(o["series"])
        if e == "J":
            res["yearly_J"]["pre"] = yearly(L["eq"])
    res["judge"] = judge(res["at"][str(DECIDE_SIZE)])
    res["elapsed_s"] = round(time.time() - t0)
    return res


# ───────────────────────── 输出 ─────────────────────────
def _f(v, fmt="{:.2f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def _yen(v) -> str:
    return "—" if v is None else f"¥{v:,.0f}"


def report(res: dict) -> str:
    A0 = str(DECIDE_SIZE)
    at = res["at"][A0]
    L = [f"# 税后收益 × 新 NISA：同一套交易放在哪个账户（登记检验；代码 {res['git']['rev']}{' + 未提交的改动' if res['git']['dirty'] else ''}）",
         "规则见 scripts/nisa_tax_study.py 开头（先提交、只运行一次）。交易 = B4（模拟盘 2026-10-05 收盘的决策起的规则），一笔不改，税只叠在账本上。"
         "今天的税制（20.315%）与新 NISA 规则套到全部年代（假设）。非投资建议，也不是税务意见。", "",
         "## 一、¥100 万起（年化 / 最大回撤 / Calmar · 期末）", "",
         "| 口径 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 |", "|---|---|---|---|"]
    cell = lambda s: f"{_f(s.get('cagr'))}% / {_f(s.get('dd'))}% / {_f(s.get('calmar'), '{:.3f}')} · {_yen(s.get('final'))}"  # noqa: E731
    L.append("| 税前（B4，同一口径） | " + " | ".join(cell(res["pre"][e]) for e in ERAS) + " |")
    for p in POLICIES:
        L.append(f"| {p} {LABEL[p]}（税后） | " + " | ".join(cell(at[p][e]) for e in ERAS) + " |")
    L += ["", "比 P0 多的税后年化（pp）：", ""]
    for p in ("P0c",) + CANDS:
        L.append(f"- {p}：" + "；".join(f"{e} {at[p][e]['cagr'] - at['P0'][e]['cagr']:+.2f}" for e in ERAS))
    L += ["", "税前 → P0 少了（pp / 年）：" + "；".join(f"{e} {res['pre'][e]['cagr'] - at['P0'][e]['cagr']:.2f}" for e in ERAS), "",
          "## 二、判定（事先写定：a 三个年代税后年化都 ≥ P0 + 0.5 pp；b 税后最大回撤不比 P0 深 2 pp 以上；多个满足 → 比 P0 多的最小值最大的）", ""]
    for p in CANDS:
        j = res["judge"]["per"][p]
        L.append(f"- **{p} {LABEL[p]}**：{'满足' if j['ok'] else '不满足'}（三个年代里最少多 {_f(j['gain'], '{:+.2f}')} pp）"
                 + ("" if j["ok"] else "（" + "；".join(j["fails"]) + "）"))
    pk = res["judge"]["pick"]
    L += ["", f"**结论：{('按规则推荐 ' + pk + ' ' + LABEL[pk] + '（只是提议：NISA 在哪家开、今年额度用了多少要用户决定；执行器要另外做按单指定课税区分与额度记录）') if pk else '没有做法满足 → 不推荐，照旧'}**", "",
          "## 三、交的税与 NISA 的用法（¥100 万）", "",
          "| 做法 | 税合计 Z / E / J | 特定口座实现：个股 / 核心（J） | NISA 买入占比 Z / E / J | NISA 免掉的收益 / 浪费的亏损（J） |", "|---|---|---|---|---|"]
    for p in POLICIES:
        r = at[p]
        L.append(f"| {p} | " + " / ".join(_yen(r[e]["tax_paid"]) for e in ERAS) + f" | {_yen(r['J']['real_stock'])} / {_yen(r['J']['real_core'])} | "
                 + " / ".join(f"{r[e]['nisa_share']:.0f}%" for e in ERAS) + f" | {_yen(r['J']['nisa_gain'])} / {_yen(r['J']['nisa_loss'])} |")
    L += ["", "额度用满的月份（J，N1 / N2）：" + "；".join(f"{p} " + (", ".join(f"{y}-{m:02d}" for y, m in sorted(at[p]['J']['quota_full'].items())) or "没用满")
                                                for p in ("N1", "N2")),
          f"P0c 申告结转退回的税（Z / E / J）：" + " / ".join(_yen(at["P0c"][e]["carry_refund"]) for e in ERAS), "",
          "## 四、规模（只描述；账本按比例放大，真实成交会不同）", "",
          "| 规模 | 做法 | Z 税后年化 | E | J | 比 P0 多（Z / E / J，pp） |", "|---|---|---|---|---|---|"]
    for A in SIZES:
        r = res["at"][str(A)]
        for p in ("P0",) + CANDS:
            L.append(f"| ¥{A // 10000:,} 万 | {p} | " + " | ".join(f"{_f(r[p][e]['cagr'])}%" for e in ERAS) + " | "
                     + " / ".join(f"{r[p][e]['cagr'] - r['P0'][e]['cagr']:+.2f}" for e in ERAS) + " |")
    yj = res.get("yearly_J") or {}
    years = sorted((yj.get("pre") or {}).keys())
    L += ["", "## 五、J 每年的收益（%；¥100 万）", "", "| 年 | 税前 | P0 | " + " | ".join(CANDS) + " |", "|---|---|---|" + "---|" * len(CANDS)]
    for y in years:
        L.append(f"| {y} | {_f(yj['pre'].get(y))} | {_f(yj['P0'].get(y))} | " + " | ".join(_f(yj[p].get(y)) for p in CANDS) + " |")
    L += ["", "账本：" + json.dumps(res["ledger"], ensure_ascii=False), "",
          f"用时 {res.get('elapsed_s')} s。局限见脚本开头第七节（今天的税制套历史、按比例缩放、分红只在卖出时交税、退税时点简化）。非投资建议、不是税务意见。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", required=True)
    ap.parse_args(argv)
    from qbreak import paths
    res = run()
    od = paths.out_dir()
    (od / OUT_MD).write_text(report(res), encoding="utf-8")
    (od / OUT_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
