Attribute VB_Name = "RssBridge"
'==============================================================================
' RssBridge.bas — Python(qbreak) ⇄ Excel ⇄ マーケットスピード II RSS 的唯一接口层
'
' 为什么要有这一层：
'   RSS 的発注関数签名会随年度更新（官方「RSS 関数一覧」PDF 每年改），
'   把它写死在 Python 里等于每年坏一次。所以 Python 只认下面三个稳定契约：
'
'       QB_PlaceOrder(payloadJson)  -> {"ok":true,"order_id":"...","filled_qty":0,...}
'       QB_QueryOrder(clientId)     -> {"ok":true,"filled_qty":100,"filled_px":2500,...}
'       QB_CancelOrder(clientId)    -> {"ok":true}
'
'   版本差异全部关在本文件的 ★TODO★ 区块里，你只需要按当期 PDF 填一次。
'
' 安装：Excel → Alt+F11 → 文件 → 导入文件 → 选择本文件
'       然后先运行 QB_SetupSheets（自动建表和命名区域），再运行 QB_SelfTest
'
' 前提：Windows + 桌面版 Excel + MarketSpeed II 已登录 + RSS 显示「接続」
'       + 功能区上把状态切到「発注可」（未切换时発注関数一律失败）
'==============================================================================
Option Explicit

Private Const SH_QUOTE As String = "Quote"
Private Const SH_POS   As String = "Pos"
Private Const SH_CTRL  As String = "Ctrl"
Private Const SH_LOG   As String = "OrderLog"

'==============================================================================
' 一次性初始化：建表 + 命名区域
'==============================================================================
Public Sub QB_SetupSheets()
    Dim ws As Worksheet
    EnsureSheet SH_QUOTE: EnsureSheet SH_POS: EnsureSheet SH_CTRL: EnsureSheet SH_LOG

    With Sheets(SH_QUOTE)
        .Range("A1").Value = "銘柄コード"
        .Range("B1").Value = "現在値"
        .Range("C1").Value = "始値"
        .Range("D1").Value = "高値"
        .Range("E1").Value = "安値"
        .Range("F1").Value = "出来高"
        ' ★ A 列填你的股票池代码（如 7203），B:F 填 RSS 行情函数，例如：
        '    B2: =RssMarket($A2,"現在値")   C2: =RssMarket($A2,"始値")
        '    D2: =RssMarket($A2,"高値")     E2: =RssMarket($A2,"安値")
        '    F2: =RssMarket($A2,"出来高")
        '    函数名/引数名务必对照当期「RSS 関数一覧」PDF 核对后再填。
    End With

    With Sheets(SH_POS)
        .Range("A1").Value = "銘柄コード"
        .Range("B1").Value = "保有数量"
        .Range("C1").Value = "平均取得単価"
        .Range("E1").Value = "買付余力"
        ' ★ A:C 用 RSS 的「保有株式」系列函数拉取；E2 填「買付可能額」
        .Range("E2").Name = "CASH"
    End With

    With Sheets(SH_CTRL)
        .Range("A1").Value = "ARM（人工解锁：填 ARMED 才允许发单，收盘后清空）"
        .Range("B1").Name = "ARM"
        .Range("B1").Value = ""
        .Range("B1").Interior.Color = RGB(255, 235, 156)
        .Range("A2").Value = "最終更新"
        .Range("B2").Name = "LASTUPDATE"
    End With

    With Sheets(SH_LOG)
        .Range("A1:H1").Value = Array("時刻", "client_id", "code", "side", "qty", _
                                      "price", "order_id", "result")
    End With
    MsgBox "表已就绪。请在 Quote/Pos 里填入 RSS 函数，再运行 QB_SelfTest。", vbInformation
End Sub

Private Sub EnsureSheet(nm As String)
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = Sheets(nm)
    On Error GoTo 0
    If ws Is Nothing Then Sheets.Add(After:=Sheets(Sheets.Count)).Name = nm
End Sub

'==============================================================================
' 自检：把"实盘当天才发现配置不对"提前到今天
'==============================================================================
Public Function QB_SelfTest() As String
    Dim msg As String, ok As Boolean
    ok = True
    msg = "── RSS Bridge 自检 ──" & vbCrLf
    msg = msg & CheckSheet(SH_QUOTE, ok) & CheckSheet(SH_POS, ok) & CheckSheet(SH_CTRL, ok)
    msg = msg & CheckName("CASH", ok) & CheckName("ARM", ok)

    Dim v As Variant
    v = Sheets(SH_QUOTE).Range("B2").Value
    If IsNumeric(v) And v > 0 Then
        msg = msg & "[OK] Quote!B2 取到报价 " & v & vbCrLf
    Else
        msg = msg & "[NG] Quote!B2 没有数字报价 → MarketSpeed II 未登录 / RSS 未接続 / 函数名不对" & vbCrLf
        ok = False
    End If

    v = Range("CASH").Value
    If IsNumeric(v) Then
        msg = msg & "[OK] 買付余力 " & Format(v, "#,##0") & vbCrLf
    Else
        msg = msg & "[NG] Pos!CASH 读不到余力" & vbCrLf
        ok = False
    End If

    msg = msg & IIf(UCase(Trim(CStr(Range("ARM").Value))) = "ARMED", _
                    "[!!] ARM = ARMED（当前允许发单）" & vbCrLf, _
                    "[OK] ARM 未解锁（当前禁止发单）" & vbCrLf)
    msg = msg & IIf(ok, "=> 通过", "=> 有问题，修好之前不要实盘")
    QB_SelfTest = msg
    MsgBox msg, IIf(ok, vbInformation, vbExclamation)
End Function

Private Function CheckSheet(nm As String, ByRef ok As Boolean) As String
    On Error Resume Next
    Dim ws As Worksheet: Set ws = Sheets(nm)
    On Error GoTo 0
    If ws Is Nothing Then ok = False: CheckSheet = "[NG] 缺少工作表 " & nm & vbCrLf _
    Else CheckSheet = "[OK] 工作表 " & nm & vbCrLf
End Function

Private Function CheckName(nm As String, ByRef ok As Boolean) As String
    On Error Resume Next
    Dim r As Range: Set r = Range(nm)
    On Error GoTo 0
    If r Is Nothing Then ok = False: CheckName = "[NG] 缺少命名区域 " & nm & vbCrLf _
    Else CheckName = "[OK] 命名区域 " & nm & vbCrLf
End Function

'==============================================================================
' 发单：Python 调用的唯一入口
'==============================================================================
Public Function QB_PlaceOrder(ByVal payloadJson As String) As String
    Dim clientId As String, code As String, side As String
    Dim qty As Long, price As Double, trigger As Double
    Dim orderType As String, condition As String

    clientId = JsonStr(payloadJson, "client_id")
    code = JsonStr(payloadJson, "code")
    side = UCase(JsonStr(payloadJson, "side"))
    orderType = UCase(JsonStr(payloadJson, "order_type"))
    condition = UCase(JsonStr(payloadJson, "condition"))
    qty = CLng(JsonNum(payloadJson, "qty"))
    price = JsonNum(payloadJson, "price")
    trigger = JsonNum(payloadJson, "trigger")

    ' ── 双保险：VBA 这一侧也检查 ARM。Python 被改坏也发不出去 ──
    If UCase(Trim(CStr(Range("ARM").Value))) <> "ARMED" Then
        QB_PlaceOrder = "{""ok"":false,""error"":""ARM not set in Excel""}"
        Exit Function
    End If
    If qty <= 0 Or code = "" Then
        QB_PlaceOrder = "{""ok"":false,""error"":""bad payload""}"
        Exit Function
    End If

    On Error GoTo EH
    Dim orderId As String

    '======================= ★TODO★ 按当期「RSS 関数一覧」PDF 填写 =======================
    ' 下面是**占位实现**，会直接返回 not_implemented。实盘前必须替换成真实调用。
    '
    ' MARKETSPEED II RSS 的発注是「VBA から呼ぶ関数」，典型形态是：
    '     ret = Application.Run("RssOrder系の関数名", 引数1, 引数2, ...)
    ' 或在工作表上写入参数后触发。两种做法都可以，只要本函数最终把
    ' 券商返回的注文番号放进 orderId 即可。
    '
    ' 填写时逐项对照 PDF 确认：
    '   • 関数名（年度更新，2021 年 MS2 RSS 上线后改过多次）
    '   • 売買区分（1=買 / 3=売 之类的取值）
    '   • 執行条件（成行/指値/逆指値，本桥用 orderType: LIMIT / STOP）
    '   • 注文条件（寄付＝OPENING / 引け / 通常，本桥用 condition）
    '   • 口座区分（特定/一般/NISA。自动交易**不要**用 NISA：额度会被来回买卖浪费掉）
    '   • 有効期限（当日 / GTC）
    '
    ' 参考骨架（**函数名与参数顺序必须以 PDF 为准**）：
    '   orderId = Application.Run("RssOrderStock", code, _
    '                             IIf(side = "BUY", 1, 3), _
    '                             qty, _
    '                             IIf(orderType = "STOP", trigger, price), _
    '                             orderType, condition)
    '
    QB_PlaceOrder = "{""ok"":false,""error"":""QB_PlaceOrder not_implemented: " & _
                    "请按 RSS 関数一覧 PDF 填写本函数""}"
    LogOrder clientId, code, side, qty, price, "", "NOT_IMPLEMENTED"
    Exit Function
    '====================================================================================

    ' 真实实现填好后，把上面两行删掉，启用下面这段：
    ' LogOrder clientId, code, side, qty, price, orderId, "SENT"
    ' QB_PlaceOrder = "{""ok"":true,""order_id"":""" & orderId & """,""client_id"":""" & _
    '                 clientId & """,""filled_qty"":0,""filled_px"":0,""status"":""SENT""}"
    ' Exit Function

EH:
    LogOrder clientId, code, side, qty, price, "", "ERROR:" & Err.Description
    QB_PlaceOrder = "{""ok"":false,""error"":""" & JsonEscape(Err.Description) & """}"
End Function

'==============================================================================
' 约定（成交）查询：Python 发单后会反复调用它核对数量
'==============================================================================
Public Function QB_QueryOrder(ByVal clientId As String) As String
    On Error GoTo EH
    Dim orderId As String, filledQty As Long, filledPx As Double, st As String
    orderId = LookupOrderId(clientId)
    If orderId = "" Then
        QB_QueryOrder = "{""ok"":false,""error"":""unknown client_id""}"
        Exit Function
    End If

    '======================= ★TODO★ 填写约定查询 =======================
    ' 用 RSS 的「注文状況 / 約定」系列函数按 orderId 取回：
    '   filledQty = Application.Run("RssOrderStatus", orderId, "約定数量")
    '   filledPx  = Application.Run("RssOrderStatus", orderId, "約定単価")
    '   st        = Application.Run("RssOrderStatus", orderId, "状態")
    ' 注意：RSS 值刷新有延迟，Python 侧已经在 15 秒内轮询，这里直接读当前值即可。
    QB_QueryOrder = "{""ok"":false,""error"":""QB_QueryOrder not_implemented""}"
    Exit Function
    '===================================================================

EH:
    QB_QueryOrder = "{""ok"":false,""error"":""" & JsonEscape(Err.Description) & """}"
End Function

Public Function QB_CancelOrder(ByVal clientId As String) As String
    On Error GoTo EH
    Dim orderId As String
    orderId = LookupOrderId(clientId)
    If orderId = "" Then QB_CancelOrder = "{""ok"":false,""error"":""unknown""}": Exit Function
    '======================= ★TODO★ 填写撤单 =======================
    ' Application.Run "RssOrderCancel", orderId
    QB_CancelOrder = "{""ok"":false,""error"":""QB_CancelOrder not_implemented""}"
    Exit Function
EH:
    QB_CancelOrder = "{""ok"":false,""error"":""" & JsonEscape(Err.Description) & """}"
End Function

'==============================================================================
' 工具：订单台账 + 极简 JSON（VBA 没有内置 JSON；payload 格式由本桥自己约定，够用）
'==============================================================================
Private Sub LogOrder(clientId As String, code As String, side As String, qty As Long, _
                     price As Double, orderId As String, result As String)
    Dim ws As Worksheet, r As Long
    Set ws = Sheets(SH_LOG)
    r = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row + 1
    ws.Cells(r, 1).Value = Now
    ws.Cells(r, 2).Value = clientId
    ws.Cells(r, 3).Value = code
    ws.Cells(r, 4).Value = side
    ws.Cells(r, 5).Value = qty
    ws.Cells(r, 6).Value = price
    ws.Cells(r, 7).Value = orderId
    ws.Cells(r, 8).Value = result
    Range("LASTUPDATE").Value = Now
End Sub

Private Function LookupOrderId(clientId As String) As String
    Dim ws As Worksheet, r As Long
    Set ws = Sheets(SH_LOG)
    For r = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row To 2 Step -1
        If CStr(ws.Cells(r, 2).Value) = clientId Then
            LookupOrderId = CStr(ws.Cells(r, 7).Value)
            Exit Function
        End If
    Next r
End Function

Private Function JsonStr(s As String, key As String) As String
    Dim i As Long, j As Long, pat As String
    pat = """" & key & """:"""
    i = InStr(1, s, pat, vbTextCompare)
    If i = 0 Then Exit Function
    i = i + Len(pat)
    j = InStr(i, s, """")
    If j = 0 Then Exit Function
    JsonStr = Mid$(s, i, j - i)
End Function

Private Function JsonNum(s As String, key As String) As Double
    Dim i As Long, j As Long, pat As String, buf As String
    pat = """" & key & """:"
    i = InStr(1, s, pat, vbTextCompare)
    If i = 0 Then Exit Function
    i = i + Len(pat)
    Do While i <= Len(s)
        Dim ch As String
        ch = Mid$(s, i, 1)
        If InStr("0123456789.-+eE", ch) > 0 Then
            buf = buf & ch
        ElseIf buf <> "" Then
            Exit Do
        ElseIf ch <> " " Then
            Exit Do
        End If
        i = i + 1
    Loop
    If buf <> "" Then JsonNum = CDbl(Val(buf))
End Function

Private Function JsonEscape(s As String) As String
    JsonEscape = Replace(Replace(s, "\", "\\"), """", "\""")
End Function
