"""tachibana_sim.py — 立花 e支店 API 的模拟交易所（只用于演练，不连任何网络）。

用历史 K 线撮合，应答用 TachibanaSpec 的字段名（v4r10）。执行器走的是**真实的立花适配器代码**：登录与虚拟 URL 解密、
发单字段、寄付 / 当日限り、約定照会、现物持仓、买付可能額 —— 只有网络那一层换成这里。

撮合规则 = 回测的成交假设（演练与回测的差异只来自真实下单的约束，不来自撮合假设）：
  • 寄付注文：第 k 天开盘价 ± 滑点（个股 0.10%，1655 0.02%）成交；寄付指値只在开盘价 ≤ 指値时成交，否则失效
  • 卖单遇到当天一整天ストップ安（与引擎同一判断）→ 不成交、失效
  • 开盘后下的当日限り指値：开盘价 ≤ 指値（买）就按开盘价 + 滑点立即成交；否则收盘失效（这里没有盘中价格路径）
  • 手续费：立花個別コース（与回测同一函数）；买付可能額 = 现金 − 未成交买单的预留（指値 × 股数 + 手续费）
  • 受理检查：买付余力不足 / 可卖股数不足 → 业务错误（sResultCode ≠ 0），适配器报成 REJECTED（与真实 API 相同的路径）；
    限价不在呼値的格子上（按一手与执行日选表：2027-03-01 起分表、一手 1 口的 ETF 用 O 表）/ 在当天的制限値幅（前日終値 ± 値幅）之外 /
    卖单股数不是一手的整数倍（单元未満株不能用普通注文卖）→ 也是业务错误（真实交易所 / 立花同样不受理）
  • 时价：交易时间里给现在值 / 始値 = 当天开盘价；前日終値 = 上一交易日的收盘（开盘前也给，与真实 API 相同）
"""
from __future__ import annotations

import base64

from ..tick import price_limit_jp, tick_size
from .tachibana import Credentials, TachibanaSpec


class SimExchange:
    """eng：演练用的 UnifiedEngine（只读它的行情数组、费用与滑点）；cash：起始现金（円）。
    时间推进由演练驱动：open(k) 开盘撮合 → [开盘后的单立即撮合] → close_day() 收盘失效 → set_day(k+1) 之后的单属于下一交易日。"""
    is_sim = True                               # 立花适配器据此不拿真实的本番会话锁（〔77〕C TA-14）

    def __init__(self, eng, cash: float, spec: TachibanaSpec | None = None):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        self.eng, self.spec = eng, spec or TachibanaSpec()
        self.spec.min_interval_s = 0.0
        self.cash = float(cash)
        self.pos: dict[str, int] = {}
        self.book_value: dict[str, float] = {}
        self.orders: dict[str, dict] = {}
        self.k, self.day_k, self.phase = -1, -1, "closed"
        self._no = 0
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = self._key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption())
        self.calls: dict[str, int] = {}
        self.tick_on = None                     # 呼値表按哪天选（None = 今天，与引擎 / 适配器的取整相同；测试可以设 2027-03-01 之后）
        self.order_time = ""                    # 注文一覧的受付时刻（YYYYMMDDHHMMSS；测试设，状态不明的单找候选用）

    def creds(self) -> Credentials:
        return Credentials("SIM-AUTH-ID", self.pem, "sim-second-pw")

    # ── 时间推进 ──
    def _day(self, k: int) -> str:
        g = self.eng.gidx
        return g[k].strftime("%Y%m%d") if 0 <= k < len(g) else "99991231"

    def set_day(self, k: int) -> None:
        """之后受理的注文属于第 k 个交易日（收盘后 / 次日开盘前下的寄付单）。"""
        self.day_k, self.phase = k, "pre"

    def open(self, k: int) -> None:
        """第 k 天开盘：撮合当天的寄付注文（先卖后买；现金只在成交时变动，受理时已按余力检查过）。"""
        s, eng = self.spec, self.eng
        self.k = self.day_k = k
        day = self._day(k)
        todo = [o for o in self.orders.values() if o["status"] == "1" and o["day"] == day and o["cond"] == s.cond_opening]
        for o in sorted(todo, key=lambda o: (o["side"] == "BUY", o["no"])):
            j = eng.col[o["ticker"]]
            if not eng.A.has[k, j]:
                o["status"] = "12"                              # 停牌：全部失効
                continue
            op = float(eng.A.open[k, j])
            if o["side"] == "SELL":
                if eng._locked(k, j) == "down":
                    o["status"] = "12"                          # ストップ安張り付き：寄付で約定せず
                    continue
            elif not self._buy_ok(o, op):
                o["status"] = "12"                              # 寄付指値に届かず
                continue
            self._fill(o, op)
        self.phase = "open"

    def close_day(self) -> None:
        """收盘：当天没成交的注文全部失效（当日限り）。"""
        day = self._day(self.k)
        for o in self.orders.values():
            if o["status"] == "1" and o["day"] == day:
                o["status"] = "12"
        self.phase = "closed"

    # ── 撮合与记账 ──
    def _slip(self, t: str) -> float:
        eng = self.eng
        return eng.c_slip[t] if t in eng.core_set else eng.slip["JP"]

    def _fee(self, t: str, side: str):
        eng = self.eng
        return eng.c_fee[t][side] if t in eng.core_set else eng.fees["JP"]

    @staticmethod
    def _on_grid(px: float, t: str) -> float:
        """历史行情是复权价，不在呼値格子上（例如 188.52）；真实的约定价一定在格子上 → 比较限价前先取最近的呼値。"""
        u = tick_size(px, t)
        return round(round(px / u) * u, 4)

    def _buy_ok(self, o: dict, op: float) -> bool:
        return not o["lim"] or self._on_grid(op, o["ticker"]) <= o["lim"] + 1e-9

    def _fill(self, o: dict, op: float) -> None:
        t, q = o["ticker"], int(o["qty"])
        if o["side"] == "BUY":
            px = op * (1 + self._slip(t))
            self.cash -= px * q + self._fee(t, "BUY")(px * q)
            self.pos[t] = self.pos.get(t, 0) + q
            self.book_value[t] = self.book_value.get(t, 0.0) + px * q
        else:
            px = op * (1 - self._slip(t))
            self.cash += px * q - self._fee(t, "SELL")(px * q)
            held = self.pos.get(t, 0)
            self.book_value[t] = self.book_value.get(t, 0.0) * (held - q) / held if held else 0.0
            self.pos[t] = held - q
            if self.pos[t] <= 0:
                self.pos.pop(t, None)
                self.book_value.pop(t, None)
        o.update(filled=q, px=px, status="10")

    def _reserved(self) -> float:
        return sum(o["lim"] * o["qty"] + self._fee(o["ticker"], "BUY")(o["lim"] * o["qty"])
                   for o in self.orders.values() if o["status"] == "1" and o["side"] == "BUY")

    def buying_power(self) -> float:
        return self.cash - self._reserved()

    def _sellable(self, t: str) -> int:
        return self.pos.get(t, 0) - sum(o["qty"] for o in self.orders.values()
                                        if o["status"] == "1" and o["side"] == "SELL" and o["ticker"] == t)

    # ── API 应答 ──
    @staticmethod
    def _ok(**kw) -> dict:
        return {"p_errno": "0", "sResultCode": "0", **kw}

    @staticmethod
    def _err(code: str, text: str) -> dict:
        return {"p_errno": "0", "sResultCode": code, "sResultText": text}

    def _enc(self, url: str) -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        ct = self._key.public_key().encrypt(url.encode("ascii"), padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        return base64.b64encode(ct).decode("ascii")

    def get_json(self, url: str, payload: dict) -> dict:
        s = self.spec
        clm = payload.get(s.f_clmid, "")
        self.calls[clm] = self.calls.get(clm, 0) + 1
        h = {s.clm_login: self._login, s.clm_new_order: self._new_order, s.clm_order_detail: self._detail,
             s.clm_positions: self._positions, s.clm_buying_power: self._bp, s.clm_price: self._price,
             s.clm_cancel_order: self._cancel, s.clm_order_list: self._list,
             s.clm_issue_mst: self._mst, s.clm_issue_mkt: self._mst_mkt, s.clm_issue_kisei: self._mst_kisei}.get(clm)
        return h(payload) if h else self._ok(sCLMID=clm)

    # ── マスタ：演练里的票都是东证、普通、没有规制；売買単位 = 引擎的一手 ──
    def _codes(self) -> list[tuple[str, int]]:
        eng = self.eng
        return [(t.split(".")[0], int(eng.lots[j])) for t, j in eng.col.items() if t.endswith(".T")]

    def _mst(self, p: dict) -> dict:
        s = self.spec
        return self._ok(**{s.r_issue_mst: [{"sIssueCode": c, "sYusenSizyou": "00", "sBaibaiTani": str(lot), "sBaibaiTeisiC": " "}
                                           for c, lot in self._codes()]})

    def _mst_mkt(self, p: dict) -> dict:
        s = self.spec
        return self._ok(**{s.r_issue_mkt: [{"sIssueCode": c, "sZyouzyouSizyou": "00", "sIssueKubunC": " ", "sZyouzyouKubun": "01",
                                            "sZyouzyouHaisiDay": "00000000"} for c, _ in self._codes()]})

    def _mst_kisei(self, p: dict) -> dict:
        return self._ok(**{self.spec.r_issue_kisei: ""})                 # 没有规制：仕様上空列表是 ""

    def _login(self, p: dict) -> dict:
        s = self.spec
        if p.get(s.f_auth_id) != "SIM-AUTH-ID":
            return {"p_errno": "0", "sResultCode": "10031", "sResultText": "認証 ID が違います"}
        return self._ok(**{s.f_tax: s.tax_specific, s.key_unread: "0",
                           **{k: self._enc(f"sim://{k}/") for k in (s.key_url_request, s.key_url_master, s.key_url_price,
                                                                  s.key_url_event, s.key_url_event_ws)}})

    def _new_order(self, p: dict) -> dict:
        s, eng = self.spec, self.eng
        if not p.get(s.f_second_pw):
            return self._err("991003", "第二暗証番号がありません")
        t = f"{p.get(s.f_code)}.T"
        if t not in eng.col:
            return self._err("991010", "銘柄コードが不正です")
        side = "BUY" if p.get(s.f_side) == s.side_buy else "SELL"
        qty, cond, price = int(p.get(s.f_qty) or 0), p.get(s.f_condition), str(p.get(s.f_price) or "")
        lim = 0.0 if price in (s.price_market, s.price_none, "") else float(price)
        if qty <= 0:
            return self._err("991011", "数量が不正です")
        j = eng.col[t]
        lot = int(eng.lots[j])
        if side == "SELL" and lot > 1 and qty % lot:
            return self._err("991022", f"単元未満株は通常の注文では売れません（売買単位 {lot}）")
        if lim > 0:
            u = tick_size(lim, t, self.tick_on, lot)
            if abs(lim / u - round(lim / u)) > 1e-6:
                return self._err("991013", f"呼値の単位が不正です（{lim:g}、呼値 {u:g}）")
            prev = self._prev_close(j)
            if prev > 0 and not (prev - price_limit_jp(prev) - 1e-9 <= lim <= prev + price_limit_jp(prev) + 1e-9):
                return self._err("991014", f"値幅制限の範囲外です（{lim:g}、基準 {prev:g} ± {price_limit_jp(prev):g}）")
        if side == "BUY":
            if lim <= 0:
                return self._err("991012", "演練では成行の買いは受け付けません")
            need = lim * qty + self._fee(t, "BUY")(lim * qty)
            if need > self.buying_power() + 1e-9:
                return self._err("991020", f"買付余力が不足しています（必要 {need:,.0f} / 余力 {self.buying_power():,.0f}）")
        elif self._sellable(t) < qty:
            return self._err("991021", f"売付可能数量が不足しています（{self._sellable(t)} < {qty}）")
        self._no += 1
        o = {"no": f"S{self._no:07d}", "day": self._day(self.day_k), "ticker": t, "side": side, "qty": qty,
             "lim": lim, "cond": cond, "filled": 0, "px": 0.0, "status": "1", "at": self.order_time}
        self.orders[o["no"]] = o
        if cond == s.cond_normal and self.phase == "open":       # 开盘后的当日限り：按开盘价立即撮合
            if eng.A.has[self.k, j]:
                op = float(eng.A.open[self.k, j])
                if side == "SELL" or self._buy_ok(o, op):
                    self._fill(o, op)
        return self._ok(**{s.f_order_no: o["no"], s.f_order_date: o["day"]})

    def _detail(self, p: dict) -> dict:
        s = self.spec
        o = self.orders.get(str(p.get(s.f_order_no)))
        if o is None or o["day"] != p.get(s.f_order_date):
            return self._err("991030", "該当する注文がありません")
        ex = [{s.r_exec_qty: str(o["filled"]), s.r_exec_px: repr(o["px"])}] if o["filled"] else ""
        return self._ok(**{s.r_status_code: o["status"], s.r_filled_qty: str(o["filled"]),
                           s.r_filled_px: repr(o["px"]) if o["filled"] else "", s.r_exec_list: ex})

    def _positions(self, p: dict) -> dict:
        s = self.spec
        rows = [{s.r_pos_code: t.split(".")[0], s.r_pos_qty: str(q), s.r_pos_sellable: str(self._sellable(t)),
                 s.r_pos_avg: repr(self.book_value.get(t, 0.0) / q)} for t, q in sorted(self.pos.items()) if q > 0]
        return self._ok(**{s.r_positions: rows or ""})

    def _bp(self, p: dict) -> dict:
        return self._ok(**{self.spec.r_cash: repr(self.buying_power())})

    def _price(self, p: dict) -> dict:
        s, eng = self.spec, self.eng
        rows = []
        for code in str(p.get(s.f_target_codes) or "").split(","):
            t, row = f"{code}.T", {s.r_price_code: code}
            j = eng.col.get(t)
            live = self.phase == "open" and j is not None and 0 <= self.k and eng.A.has[self.k, j]
            op = repr(float(eng.A.open[self.k, j])) if live else ""
            pc = self._prev_close(j) if j is not None else 0.0
            row.update({s.r_price: op, s.r_open: op, s.r_high: "", s.r_low: "", s.r_volume: "",
                        s.r_prev_close: repr(pc) if pc > 0 else ""})
            rows.append(row)
        return {"p_errno": "0", s.r_price_list: rows}

    def _prev_close(self, j: int) -> float:
        """前日終値（値幅的基準）：交易时间里 = 当天的上一交易日收盘；开盘前 / 收盘后 = 受理日（set_day 的那天）的上一交易日收盘。"""
        eng = self.eng
        i = (self.k if self.phase == "open" else self.day_k) - 1
        if not (0 <= i < len(eng.gidx)) or not eng.A.has[i, j]:
            return 0.0
        return float(eng.A.close[i, j])

    def _cancel(self, p: dict) -> dict:
        s = self.spec
        o = self.orders.get(str(p.get(s.f_order_no)))
        if o is None or o["status"] != "1":
            return self._err("991031", "取消できる注文がありません")
        o["status"] = "7"
        return self._ok()

    def _list(self, p: dict) -> dict:
        s = self.spec
        rows = [{s.r_list_order_no: o["no"], s.r_list_filled_qty: str(o["filled"]), s.r_list_code: o["ticker"].split(".")[0],
                 s.r_list_side: s.side_buy if o["side"] == "BUY" else s.side_sell, s.r_list_qty: str(o["qty"]),
                 s.r_list_price: repr(o["lim"]) if o["lim"] else "0", s.r_list_filled_px: repr(o["px"]) if o["filled"] else "",
                 s.r_list_status_code: o["status"], s.r_list_time: o.get("at") or ""}
                for o in self.orders.values() if o["day"] == self._day(self.day_k)]
        return self._ok(**{s.r_order_list: rows or ""})
