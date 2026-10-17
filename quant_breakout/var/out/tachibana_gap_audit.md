# 立花实盘还缺什么：缺口盘点（只读；2026-10-09）

用户 2026-10-09：「现在立花证券的交易还缺什么东西会比较完善方便」。方法：5 个领域（立花适配器 / 实盘执行器 / Mac 运维 / 面板与手机 / 账户·税·NISA）各一个只读审查 → 每个领域一个对抗核对（逐条去代码里反驳）→ 一个补漏审查；另外两个联网核对立花官方信息（只用官方页面，2026-10-09 检索，仅对本次检索时点有效）。共 99 条：82 条经对抗核对（属实 58、部分属实 24、不成立 0），补漏 17 条附证据、没有单独核对，核对时另补出 18 条（列在各领域末尾）。A2、A3、A6 由主会话再抽查过代码。没有改任何代码、没有登录立花、没有下单。

下面先按「要不要在上实盘前做」分组，再附全部条目（含核对结论与证据 file:line，行号以 2026-10-09 的代码为准）。修法都是工程，不改交易规则；标「涉及交易规则」的要用户决定。

## A 上实盘前必须修（会漏单 / 下错单 / 出事没人知道；只改工程，不改交易规则）

- **A1** 通知到不了手机 + 没有「Mac 没跑」的提醒（死人开关）（条目 LU-04、OPS-01、UX-03、LU-05、OPS-02）
- **A2** 08:35 重试会绕过持仓核对：07:40 因「持仓与券商不一致」挡住的单，08:35 没有新 K 线时只走 place()、不调 check_broker → 照样发出（本会话抽查属实：live_unified.py morning() / run_bar()；run.py --retry）
- **A3** 09:05 / 09:20 开盘后补单的单笔上限仍是默认 ¥30 万（没按权益 ×1.05）→ 换核心 ETF 等大单被挡（本会话抽查属实）（条目 LU-01）
- **A4** 面板 / 手机看不到执行器这次跑成没有、哪些单被挡 / 被拒 / 状态不明；通知的一行摘要也不提示（条目 UX-01、UX-02）
- **A5** probe / デモ发单检查会误判通过，没测主力单型「寄付指値买」，gate 不看测试时间 / 版本（条目 TA-02）
- **A6** 公开仓库防呆：立花账本 / probe 结果 / 仕様文件 / ARM / HALT 不在 .gitignore，没设 QBREAK_HOME 时会写进仓库 var/（本会话 git check-ignore 属实）（条目 C-03）
- **A7** 盘中执行器失败时面板每 60 秒重叫一次：通知轰炸 + 反复登录立花（官方：频繁访问可能停用 API）（条目 UX-04、C-01）

## B 建议补（更稳、出事时好处理）

- **B1** 撤单：HALT 撤不掉已发出的单；适配器有 cancel_order，执行器 / 面板没接（条目 TA-03、LU-07、UX-05）
- **B2** 状态不明的单：只能人工查注文一覧再手打 --resolve；登录失败（肯定没发出）也被记成状态不明（条目 TA-04、LU-06、OPS-11）
- **B3** 持仓不一致之后没有修复工具；API / Mac 故障日在网页上人工代下后没法登记（条目 LU-08、C-06）
- **B4** 实盘账本没有备份（条目 LU-09、OPS-03）
- **B5** 前一晚只读预检（交付書面未読 / 密钥 / 维护）+ 交付書面更新预告 + API 版本提醒在发布日后消失 + 没有定期自检（条目 TA-08、C-04、TA-09、OPS-07、OPS-09）
- **B6** 实盘每天自动用开发分支最新代码：固定版本 / 依赖锁 / 单次运行异常熔断 / 系统更新后的防护（条目 LU-17、C-10、C-11、OPS-08）
- **B7** 取价失败或 09:05 还没寄り付き → 当天开盘后买单全部放弃、理由写错、09:20 不补（条目 TA-01、LU-02）
- **B8** 约定确认不看状态码（被拒 / 失效显示成「挂着」）（条目 TA-05）
- **B9** 盘中卖单在ストップ安附近被拒（限价低于値幅下限）（条目 C-02）
- **B10** 数据依赖：云端文件过期时通知只是 info；行情只有 Yahoo；个别行情落后时当天离场判断被跳过（条目 C-08、C-09、LU-03）
- **B11** 实盘起始本金按 sim.json 的 ¥100 万算（收益与第一天提醒会错，下单不受影响）（条目 LU-10）
- **B12** 上线后面板 / 页面默认还是已经停掉的模拟账户；ARM 判定面板与适配器不一致（条目 LU-20、OPS-06、UX-11、UX-12）
- **B13** 07:40 与 08:35 都没在 08:55 前完成 → 当天止损 / 规则卖单整天不下（文档写了「那天不下单」，可加开盘后当日限价卖的补救，要你同意）
- **B14** 上线值守清单 / 退出实盘预案 / 换 Mac 步骤 / 立花侧最后停止手段（利用設定「無効化」）/ 跑完 logout（条目 C-07、OPS-04、C-05）
- **B15** 文档过时：逆指値「永远在岗的保险」是旧守护进程的说法；立花没有原生 App；MACOS 还写 1655（条目 LU-16、C-17、OPS-16、T8）
- **B16** 其他小项：钥匙串锁着时提示错误、时钟偏差、仕様覆盖文件冻住默认值、错误码对照表、单元未满株、拆股当天的单、临时休市（条目 TA-07、TA-16、TA-10、OPS-05、C-15、C-14、LU-22、C-13、TA-11、TA-12、TA-15、LU-21、OPS-12、OPS-15、LU-12、LU-13、LU-15）

## C 方便（锦上添花）

- **C1** 当天看成交（现在要到第二天 07:40；官方推荐用 EVENT I/F 推送，不轮询）（条目 TA-06、UX-06）
- **C2** 「立花那边实际是什么」视图（余力 / 注文一覧 / 持仓 vs 账本）；同一账户只能一个会话（条目 UX-07、TA-14）
- **C3** 手机上的损益摘要、今天的单、最近成交、当天日志；盘中写指令后自动刷新（条目 UX-10、OPS-10、UX-16）
- **C4** 入出金在面板登记；出金时卖出的钱第二天又被买回 ETF（条目 UX-14、LU-19）
- **C5** 上线门槛进度上面板；CSV 导出；年内已实现损益与代扣税；代扣税被误报成「请登记入出金」（条目 UX-15、UX-18、T7、UX-09、T3、UX-08、T4、T5）
- **C6** 交易时段 Mac 睡着 → 手机面板打不开、盘中手动单下不了（条目 OPS-13、UX-13）
- **C7** 其他：页面文字过时、开户当天一条龙引导、日志轮换、执行质量汇总、每年的账户 / 税务清单（条目 UX-17、OPS-14、OPS-15、LU-18、OPS-17）

## D 你自己要做的（开户与立花一侧；官方信息 2026-10-09 检索，仅对本次检索时点有效）

- **D1** 开户：邮寄书面 + 簡易書留，没有 eKYC，官方 2026-05-26 起说比平时慢（没给天数）→ 想 2026-12-24 之后接着上实盘的话，开户是关键路径（条目 C-16）
- **D2** 开户时的设定：特定口座（源泉徴収あり）、手数料 個別コース、配当受取 株式数比例配分方式（会同时改变楽天等全部券商账户的领取方式）、MRF / 余力口径确认（条目 LU-14、T6）
- **D3** パスキー：2026-12-12（手机网站）/ 12-18（标准 Web）起交易与出金必须用パスキー；官方设备列表没有 Mac（用 iPhone）；网页撤单也要它 → 开户后马上注册，最好有备用设备（条目 C-16）
- **D4** 如果你或家属是日経225 某家公司的内部者：名单只放 Mac 本机（不进仓库），属于股票池变更，要你同意（条目 C-12）

## E 涉及交易规则（要你决定、先研究或登记，不在工程范围）

- **E1** 「先用较小金额跑 1〜2 周」没有具体做法（小额时多数个股一手就超过 25% 名额）（条目 LU-11）
- **E2** 券商侧逆指値（盘中灾难止损）：适配器有接口，执行器不用；要不要挂属于规则（条目 TA-17）
- **E3** 〔72〕N2 核心 ETF 放 NISA：制度与 API 都可以，但 NISA 买单只能「指値・無条件・当日中」→ 现行寄付指値不能用，代码 6 处要改（工作量大），研究的开盘价成交假设要重看（条目 T1、T2、TA-13）

## 官方信息摘要（2026-10-09 检索，仅对本次检索时点有效）

### 立花証券・ｅ支店・ＡＰＩ 现状核对（2026-10-09 JST 检索，仅对本次检索时点有效）：版本、登录认证、服务时间、使用规则、下单能力、EVENT I/F 推送

- **(1a) 现行 API 版本**（high）：v4r10 仍是现行版本。官方专用页标题写「v4.10-000 at 2026.09.27」；参考手册写「現在リリースのバージョンはｅ支店・ＡＰＩ（ｖ４ｒ１０）です」，本番 URL https://kabuka.e-shiten.jp/e_api_v4r10/ 、デモ https://demo-kabuka.e-shiten.jp/e_api_v4r10/。改版履歴：2026.08.29 v4r10 平行リリース；2026.09.27「ｅ支店・ＡＰＩ（ｖ４ｒ９）廃止」，同日信用残情報問合取得的项目名称改了（只改手册，I/F 不变；数据从东证 09-28/29 16:00 起按日配信）。手册还写明：后续版平行リリース后「３０日前後」停用旧版，通知只在本页「リリース＆改定情報」发布。  
  来源：https://www.e-shiten.jp/e_api/mfds_json_api_menu.html（页面标注 2026.09.27（HTTP Last-Modified 2026-09-25）；参考手册 mfds_json_api_ref_text.html Revision 2026-09-01）
- **(1b) 2026-09-27 之后有没有新的版本发布 / 废止通知**（high）：没找到。查过：/api/（最新一条 2026-07-28）、/api/info.html（2026-08-01 以后没有条目）、API 专用页改版履歴（最新 2026.09.27 v4r9 廃止）、/important_info/（09-27 之后只有 2026-10-01 的「信用取引金利 引き上げ」和「金融先物取引業協会退会」，后者是因为 2026-07 已停止くりっく365，对客户没有影响，两条都和 API 无关）。官方 GitHub（e-shiten-jp，由 /api/ 页链接）上有两个示例库在 2026-10-08 更新过（e_api_Excel_pubkey.xlsm、e_api_get_price_from_file_pubkey_tmp.py），但不是版本通知；后者 README 里写的还是 v4r9 的 demo URL。首页上 2026-09-27 08:00〜17:00 的全系统维护通知已经放进 HTML 注释（不再显示，属于过去的事）。  
  来源：https://www.e-shiten.jp/api/info.html（2026-10-09 检索）
- **(2a) 登录认证：电话认证、公开钥、AuthID**（high）：API 从 2026-06-27 起不要电话认证：2026-05-13 的日程写「2026.06.27～ v4r8 廃止，v4r9 本番只用公開鍵暗号化方式，API 用電話番号認証は不要」；专用页写「電話認証廃止（ｖ４ｒ８の廃止時）」。现在的登录要求只送 sAuthId（{"sCLMID":"CLMAuthLoginRequest","sAuthId":…}）；应答里的 5 个虚拟 URL（REQUEST / MASTER / PRICE / EVENT / EVENT-WebSocket）用登记的公开钥加密，要用秘密钥解密。前提条件：(1) 标准 Web 登记パスキー并用パスキー登录；(2) 在「お客様情報 → 設定情報 → ｅ支店・API 利用設定」把利用有無设成「利用する」（默认「利用しない」）；(3) 生成秘密键 / 公开键并登记公开键。AuthID 手册说「登録」那一屏才能下载秘密键，离开就只能重新登记 / 重新发行。官方也写：パスキー被解除（未登録）时 API 登录会报错。本番和デモ要各自一套 AuthID / 键（デモ不需要パスキー）。  
  来源：https://www.e-shiten.jp/api/20260513.html（2026-05-13 通知；AuthID 手册 PDF 2026-06-05（https://www.e-shiten.jp/pdf/authidmanual.pdf）；变更概要说明书 2026.08.29 改定版（https://www.e-shiten.jp/e_api/e_api_v4r9_overview.pdf））
- **(2b) 第二暗証番号**（high）：每个新规 / 订正 / 取消注文都必须带 sSecondPassword。不管标准 Web 的「暗証番号省略」怎么设，API 都要第二暗証；登录应答的 sSecondPasswordOmit 固定为 0。密码里有 # + / : = 这些符号时要做 URL 编码（Q&A）。  
  来源：https://www.e-shiten.jp/e_api/mfds_json_api_menu.html（2026.09.27（专用页「４．ご利用にあたって」第3条）；参考手册 2026-09-01）
- **(2c) 会话（虚拟 URL）的有效期**（high）：每次认证都会新发虚拟 URL，同时让之前的失效（1 顧客 1 仮想URL）。下面任何一件先发生就失效：多重认证（同一账户再次登录）、ログアウト、e支店系统闭局（03:30）、利用設定改成「利用しない」、利用設定画面上按「無効化」、运营方锁定 API。失效之后不能再恢复。REQUEST I/F 和 EVENT I/F 各只能有 1 个连接，失效时一起失效；EVENT 是「後要求勝ち」（后来的连接把前面的挤掉）。官方建议用完就 logout（可选）。另外，金商法交付書面没读（sKinsyouhouMidokuFlg=1）时登录应答正常、但不发虚拟 URL。登录应答还带 sUpdateInformWebDocument（交付書面更新预定日）和 sUpdateInformAPISpecFunction（API 发布预定日），用来提前通知。  
  来源：https://www.e-shiten.jp/QA/answer14.html（Q&A 2026-10-09 检索（页面无日期）；专用页 2026.09.27「７．仮想ＵＲＬについて」）
- **(2d) 其他认证 / 连接条件（IP、时钟、通知邮件）**（high）：只能用 IPv4（错误 10005「IPアドレスに誤りがあります」= 用了 IPv6 或 IP 不正常）。利用設定画面可以选登记「固定IPアドレス」，登记后 login 和其他请求都会核对来源 IP；AuthID 手册写「接続元を固定IPに限定する設定（IP制限）を行ってのご利用を強く推奨」。p_sd_date 比服务器时刻慢 30 秒以上会报 p_errno=8 → 机器要用 NTP 对时。p_no 必须递增，否则 p_errno=6。从 v4r9 起有「ログインメール」和「設定変更メール」。Q&A 还提到：有的大规模 NAT 线路连续请求约 240 次后就没有回应（是线路的限制）。2026-12-12〜18 起，标准 Web / 智能手机交易和出金必须用パスキー登录；那份通知没提到 API（API 本来就以登记パスキー为前提）。  
  来源：https://www.e-shiten.jp/e_api/e_api_v4r9_overview.pdf（变更概要 2026.08.29；REQUEST I/F 仕様 PDF e_api_request_if_v4r10.pdf 2026.08.29；パスキー通知 https://www.e-shiten.jp/important_info/20260708.html（8/3 更新））
- **(2e) 交付書面改定（会挡住 API）**（high）：2026-10-01 改定了上場有価証券等書面等。2026-09-30 16:30 以后没确认的客户，首次登录会显示「未読書面ご確認のお願い」；官方特别写到 API 用户必须在 PC 网站上确认（没读就不发虚拟 URL）。  
  来源：https://www.e-shiten.jp/important_info/20260911.html（2026-09-11）
- **(3) 服务时间 / 维护 / 不能用的时段**（high）：每天 03:30〜05:30 因数据更新停止登录（年末年始可能变）。股票注文 / 订正 / 取消：0:00〜15:30 收当日分；15:30〜16:30「値洗い中 受付停止」（行情原因最多可能延长约 30 分钟）；16:30〜23:59 收翌営業日分。现引现渡到 15:40。API 只在 e支店系统运转时可用；系统保守或故障时 API 和标准 Web 一样不能用；API 子系统单独故障时，要在标准 Web 上查询和订正 / 取消。デモ環境：登录 8:30〜27:00（含周末和节假日），约定时段 9:00〜11:30、12:30〜15:00、15:10〜27:00；成行一律按 100 円成交；9000 号段的代码不成交；数据每天重置。时价历史（CLMMfdsGetMarketPriceHistory）在 18:00〜次日 03:30 更新；マスタ建议在 05:30〜08:00 取。  
  来源：https://www.e-shiten.jp/Service/Time.html（2026-10-09 检索（页面无日期）；デモ：https://www.e-shiten.jp/Service/demo.html）
- **(4) 使用规则：频率限制、轮询、自动交易条件、申请与费用**（high）：费用：免费（「利用料金 無料 0円」），对象是日本株（现物和信用）。没找到单独的「API 利用申請」：门槛是开户 + パスキー + 在利用設定画面设成「利用する」+ 登记公开键 + 读完各种书面。官方明确可以自己写「自動売買ロボットプログラム」下单，但订单确认要由客户自己的程序做，并且要接受全部风险。流量限制「秒１０件」（这是订单的设计上限，官方并没有让所有请求都达到这个上限的容量）。REQUEST I/F 是一问一答（并行请求不保证）；PRICE 一次最多 120 个代码。2026-03-10「お願い」：08:00〜15:30 不要大量频繁调用 CLMMfdsGetMarketPrice，也不要频繁轮询照会，必要时会停用；不公开安全的访问次数。Q&A：各种可能额不应该用轮询，应该用 EVENT I/F 的约定通知作为触发，再去查询。专用页：判断过负荷时可能停用账户。当社提供的信息「蓄積、編集および加工等は禁止」（インターネット取引規程第18条：只能用于自己投资，不能提供给第三者，不能造成负荷）。在报了内幕人申告的个股上，API 不能新规或订正，只能取消。  
  来源：https://www.e-shiten.jp/api/20260310.html（2026-03-10 通知（页内无日期）；专用页 2026.09.27「４．ご利用にあたって」第6〜10条；规程 PDF 2026-04-14（https://www.e-shiten.jp/TorihikiRule/stipulation/pdf/int_kitei.pdf））
- **(5a) 下单能力：逆指値、寄付指値、执行条件、期限、市场**（high）：CLMKabuNewOrder 的参数：sSizyouC 只有「00：東証」；sBaibaiKubun 1 売 / 3 買 / 5 現渡 / 7 現引；sCondition 0 指定なし / 2 寄付 / 4 引け / 6 不成（寄付 + 价格 = 寄付指値）；sOrderPrice 0 = 成行，其他值 = 指値；sOrderExpireDay 0 = 当日，或 YYYYMMDD（最多 10 个营业日）；sGyakusasiOrderType 0 通常 / 1 逆指値 / 2 通常＋逆指値，配 sGyakusasiZyouken（触发价）和 sGyakusasiPrice（0 = 成行）；sGenkinShinyouKubun 0 现物 / 2・4 制度信用 / 6・8 一般信用。API 功能表里没有「連続注文」（Web 上有）；歩み値取不到（Q&A）。逆指値按市场上真实成交价触发，特別気配不算；临近前后场收盘触发时，可能来不及发到市场。  
  来源：https://www.e-shiten.jp/e_api/mfds_json_api_ref_text.html（参考手册 Revision 2026-09-01；逆指値 Q&A https://www.e-shiten.jp/QA/answer09.html）
- **(5b) 注文订正 / 取消**（high）：CLMKabuCorrectOrder 用注文番号 + 営業日指定，可以改执行条件、价格（含改成成行）、数量（只能减，不能加）、期限、逆指値条件 / 价格，都要带第二暗証。不能把「通常」改成「逆指値」，要先取消再重下（Web Q&A）。可以取消，也可以一括取消。新規→取消、新規→訂正、訂正→訂正、訂正→取消 接得太紧时，后一个请求可能因为前一个还在处理而报错 → 先用注文一覧等确认已经反映，再发下一个。服务器故障时可能只看到 HTTPS 层的错误、没有应答：这时下单有没有成功不确定，要先查注文一覧，再决定要不要重下。  
  来源：https://www.e-shiten.jp/e_api/mfds_json_api_ref_text.html（参考手册 2026-09-01；Q&A answer14 / answer09（2026-10-09 检索））
- **(5c) NISA（成長投資枠）能不能经 API 下单；口座区分参数**（high）：能。sZyoutoekiKazeiC：1 特定 / 3 一般 / 5 NISA（旧一般 NISA，2024 年起只能卖）/ 6 N成長（成長投資枠）。登录应答的 sHikazeiKouzaKubun 表示有没有开 NISA；还有 NISA 成長投資可能額、売付可能株数(N成長) 等字段。限制（Web Q&A + API 错误码 11041〜11045 一致）：NISA 买入只能指値，不能成行；执行条件只能无条件，所以不能寄付 / 引け / 不成；期限只能当日中；逆指値 / 通常＋逆指値 / 连续注文的子注文都不能指定 NISA 买入。NISA 卖出可以成行，也可以逆指値。超过年度额度（240 万円）的单不能下。立花只有成長投資枠（没有つみたて枠），一部分 ETF 不在立花 NISA 的对象里（错误 11107「当該銘柄はNISA口座への買付ができません」）。具体是哪些 ETF：没找到清单（查过 QA/answer12、serviceitem、Service/nisa.html、API 手册的マスタ项目）。  
  来源：https://www.e-shiten.jp/QA/answer12.html（Q&A 2026-10-09 检索；参考手册 2026-09-01）
- **(5d) ETF 交易**（high）：ETF / ETN 的买卖方法和普通股票相同，走同一个 CLMKabuNewOrder，也能做信用；数量单位是「口」，页面上显示为「株」。API 错误码 11175：ETF 从上市当天约 8:00 起才能下单。  
  来源：https://www.e-shiten.jp/TorihikiRule/rule/etf.html（2026-10-09 检索（页面无日期））
- **(6) 推送 / 约定通知（EVENT I/F）**（high）：有。有两种连接方式：HTTP chunk 版（sUrlEvent），以及 v4r7 起的 WebSocket 版（sUrlEventWebSocket，日文字段用 BASE64）。p_evt_cmd 可选：ST（出错后断开）、KP（5 秒没有通知就发 keepalive）、FD（时价，间引き）、EC（注文約定通知：接上时把当天的全部通知重发一遍，之后有事就推）、NS（新闻）、SS（系统状态）、US（运用状态）。EC 也包括从标准 Web、智能手机、API 任一渠道下的注文，以及受付、约定、失效（含失效理由码）、约定价和约定量、注文 / 约定状态。只能连 1 条（后来的连接胜出）；推送是 best effort，应答和通知的先后可能颠倒。v4r10 把系统状态和运用状态从 マスタ 里删了，改成只用 EVENT I/F。EVENT 规格书目前还是 api_event_if_v4r7.pdf（Update 2025.05.31），v4r10 的手册仍然链接它。  
  来源：https://www.e-shiten.jp/e_api/api_event_if_v4r7.pdf（PDF Update 2025.05.31（服务器 Last-Modified 2026-08-31）；专用页 2026.09.27「６．注文約定通知」）

### 立花証券ｅ支店 账户实务（手续费 / NISA / 入出金 / 开户 / 通知 / 2026 年与 API 有关的变化 / 东证收盘规则）——2026-10-09 JST 检索，仅对本次检索时点有效

- **(1) 現物手数料 個別コース（1 注文ごと、税込、報告書等電子交付）**（high）：约定代金（税込）：10万円まで 77円 / 20万 99円 / 50万 187円 / 100万 341円 / 150万 407円 / 300万 473円 / 600万 814円 / 1,000万 869円 / 1,000万超 1,100円。ETF・REIT 等「株式と同様」の扱い。単元未満株 0.55%（最低 1円）。与仓库 qbreak/fees.py 的 TACHIBANA_KOBETSU（2026-09-25 核对）完全一致。页面本身没有写更新日期。  
  来源：https://www.e-shiten.jp/TorihikiRule/cost/（页面无日期；2026-10-09 检索）
- **(1) 現物手数料 定額コース（1 日约定代金合计、税込）**（high）：12万円まで 無料 / 20万 176円 / 50万 253円 / 100万 506円 / 200万 759円 / 300万 1,012円 / 400万 1,265円 / 500万 1,518円 / 600万 1,771円 / 700万 2,024円 / 800万 2,277円 / 900万 2,530円 / 1,000万 2,783円 / 之后每 100万 +253円。12万円以下的单下单时先按每单 176円 暂扣，数据更新时重算。信用手续费两种コース都是 0円。与 fees.py 的 TACHIBANA_TEIGAKU + tachibana_teigaku() 一致。怎么在两种コース之间切换、生效时间、新开户默认是哪一种：手续费页面都没写（not found）。  
  来源：https://www.e-shiten.jp/TorihikiRule/cost/（页面无日期；2026-10-09 检索）
- **(1) 新开户的现物手续费免费期**（high）：首页 2026-10-09 仍有链接「現物手数料3か月間無料！」，指向 2018-07-13 的说明：新开「証券口座」的客户，从口座開設完了日的下一个营业日起「約3ヶ月間（60営業日・約定日ベース）」，「現物株式(ＮＩＳＡを含む)の買付および売付」免费；端株不在范围内；只适用于「報告書電子交付」的客户；先按当前コース收费，次日早上的批处理（3:30〜5:30）重算成 0円；解约后再开户不适用；「予告なく変更する場合があります」；没有写截止日期。仓库里写的「新开户前 60 营业日 0 円」与此一致。  
  来源：https://www.e-shiten.jp/important_info/180713.html（2018-07-13（2026-10-09 仍从首页 https://www.e-shiten.jp/ 链接））
- **(2) e支店 有没有 NISA（成長投資枠 / つみたて投資枠）**（high）：只有成長投資枠：「※e支店では「つみたて投資枠」はお取り扱いしておりません」；ジュニアNISA 也没有。要先开证券口座，再申请 NISA。成長投資枠里的株式手续费「現物株式の手数料コースに準じます」（不是免费）。每年 240万円、成長投資枠终身 1,200万円（总额 1,800万円），卖出后释放的额度从第二年起才能再用。  
  来源：https://www.e-shiten.jp/QA/answer12.html（页面无日期；2026-10-09 检索）
- **(2) e支店 NISA 的下单规则**（high）：原文：口座区分选「Ｎ成長」，「単価指定は指値のみ（成行注文はできません。）、執行条件は無条件、注文期限は当日中のみ選択可能」；「連続注文の子注文」「逆指値注文／ダブル注文」不能指定 NISA；卖出可以用成行。不在范围内：整理・監理銘柄等（制度上）；e支店还不受理「ETF銘柄の一部の銘柄や外国投資法人債券（銘柄名がWisdomTreeから始まるもの）」。ETF 分配金 / 股息要免税，必须选「株式数比例配分方式」（要通过书面手续向 Support Center 申请），而且一选就适用于本人在所有券商的全部账户（包括楽天）。  
  来源：https://www.e-shiten.jp/QA/answer12.html（页面无日期；2026-10-09 检索）
- **(2) 1545 / 1482 能不能用成長投資枠买**（high）：资产运用业协会（原投资信托协会，旧网址 toushin.or.jp 会跳到 imaj.or.jp）的「上場投資信託（ETF）・上場投資法人（REIT等）対象商品リスト」（最终更新 2026/10/8）里，「対象商品一覧」这张表收录了：15450 ＮＥＸＴ ＦＵＮＤＳ ＮＡＳＤＡＱ－１００（為替ヘッジなし）連動型上場投信（野村、年1回决算、つみたて非対象）和 14820 ｉシェアーズ・コア 米国債７－１０年 ＥＴＦ（為替ヘッジあり）（BlackRock、四半期决算、つみたて非対象）。两只都在成長投資枠的对象里。e支店写明不受理的只有 WisdomTree 系等「一部」，没有逐只的清单，所以「e支店具体能不能买这两只」没有在官方页面上逐只确认过（开户后要在下单画面确认）。  
  来源：https://www.imaj.or.jp/find/nisa_growth_productslist/（2026-10-08（列表更新日））
- **(2) 能不能通过 API 做 NISA 交易**（high）：可以（据官方 API reference，ref_text 修订版 2026-09-01）：CLMKabuNewOrder 的 sZyoutoekiKazeiC =「6：N成長（2024年から取り扱い開始、NISA成長投資枠）」；5：NISA（旧一般 NISA，2024 年起只能卖）。余力应答里有 sNseityouTousiKanougaku（NISA成長投資可能額），资产应答里有 N成長 的评估额。登录应答 CLMAuthLoginAck 的 sZyoutoekiKazeiC 只写了 1：特定 / 3：一般 / 5：NISA。注意：仓库适配器（qbreak/brokers/tachibana.py:634、:644）用的是登录应答的值，所以现在永远不会发 6（N成長）的单。  
  来源：https://www.e-shiten.jp/e_api/mfds_json_api_ref_text.html（2026-09-01（文件修订号））
- **(3) 入金方法（即时入金 / 汇款）**（high）：只能银行汇款，汇到每个客户专用的入金账户（みずほ銀行 シラカバ支店 普通，收款人名义 立花証券株式会社；账号登录后在「お客様情報」里看）。「リアルタイム入金や即時入金サービスはお取り扱いしておりません」，没有网银即时入金。汇款手续费由客户承担。系统每 15 分钟查一次到账，平日 9:00〜15:00 确认到的当天处理，其他时间顺延到下一个营业日。开户完成前不能入金。没有写最低入金额。  
  来源：https://www.e-shiten.jp/TorihikiRule/rule/payment_1.html（页面无日期；2026-10-09 检索（另见 https://www.e-shiten.jp/QA/answer04.html））
- **(3) 預金口座定額振替サービス（每月自动扣款入金）**（high）：原则上每月 26 日扣款（遇休息日顺延），最低「5,000円以上、1円単位」，没有上限，免费（当社负担）；原则上扣款日 5 个营业日后「午前9：30以降」到证券账户；新登记 / 变更在收到书面后最长要 2〜3 个月；连续 3 次扣款失败会暂停。可用的银行要看みずほファクター的 PDF 列表。  
  来源：https://www.e-shiten.jp/TorihikiRule/rule/furikae.html（2024-06-24（开始服务的通知））
- **(3) 出金的时间**（high）：「出金依頼は毎営業日の14:00を受付締切」，过了截止时间按下一个营业日处理；每个营业日汇款一次，到账时间看收款银行（不保证当天或第二天到）；汇款手续费由当社负担；每天上限 3億円；只能汇到登记的本人银行账户；路径是网页「入出金・振替 → 入出金 → 出金依頼」+ 第二暗証番号；没找到能用 API 出金的说明。2026-05-30 起出金申请要做客户认证，出金申请 / 取消会发通知邮件；2026-12-12 起出金必须用パスキー登录（见第 (6) 项）。  
  来源：https://www.e-shiten.jp/TorihikiRule/rule/payment_2.html（页面无日期；2026-10-09 检索）
- **(4) 开户的步骤与所需时间**（high）：两条路：通常开户 = 网上填表 → 公司寄来书面 → 签名盖章后寄回；クイック开户 = 网上填表 → 自己用 A4 纸打印 10 页，寄回第 1〜6 页（送料免费）。两条路都要附不同的 2 种本人确认书类 + マイナンバー（例：マイナンバーカード复印件、驾照复印件、住民票原件）；没有 eKYC（手机拍照认证）。审查通过后，写有ユーザID・第一 / 第二暗証番号・顧客コード・専用入金账户的「お取引口座開設のお知らせ」用「簡易書留（転送不要）」寄到登记住址。官方没写要几天（天数 not found）；2026-05-26 的通知说申请太多，「申込書類の発送および口座開設手続き」比平时慢，开户页面上也还挂着延迟的说明。已经有 e支店 账户、或要在立花开第二个账户的都不受理；2017-09 起不受理法人账户。  
  来源：https://www.e-shiten.jp/Service/flow.html（flow 页无日期；延迟通知 https://www.e-shiten.jp/important_info/20260526.html（2026-05-26））
- **(4) 特定口座（源泉徴収あり）怎么选**（medium）：开户申请表里可以选 特定口座（源泉徴収あり / なし）或 一般口座（据开户页面判读：页面编码是乱码，内容是推断出来的）。开户后也能从「お客様情報」申请特定口座（要寄回书面、附 2 种本人确认书类与マイナンバー）。改源泉徴収あり / なし：只能在当年特定口座里还没有发生计算（还没有卖出、结算、收股息）时改；下一年的变更每年 11 月上旬起受理。要用特定口座收股息，必须选「株式数比例配分方式」。2017-10-07 以后开的特定口座会同时开特定管理口座。  
  来源：https://www.e-shiten.jp/QA/answer06.html（页面无日期；2026-10-09 检索（开户表单：https://kouza.e-shiten.jp/actr/））
- **(5) 约定通知 / 邮件通知 / App 推送**（medium）：有「株式約定メール・未約定メール」：登录后在「お客様情報」画面的设定信息里开关（触发时机官方没写）。登录通知邮件：2025-06-04 16:00 起「お客様の証券口座にログインがあった場合」发到注册邮箱 1，「配信停止や設定解除はできません」；通知页面列的对象只有标准 Web 和手机网站，API 登录会不会发没有写（MACOS.md 写的是每次登录都会收到）。2026-05-30 起パスキー的注册 / 删除、出金申请 / 取消也会发邮件。没找到原生 App 和推送通知：只有手机专用网站（https://kabuka.e-shiten.jp/mfds_smp.php）和 BRiSK Next。API 有 EVENT I/F（含 WebSocket 版）的「注文約定通知」；登录应答还有 sUpdateInformWebDocument（交付书面更新预定日）和 sUpdateInformAPISpecFunction（API 发布预定日）这两个预告字段。  
  来源：https://www.e-shiten.jp/QA/answer11.html（登录邮件 https://www.e-shiten.jp/important_info/20250602.html（2025-06-02）；API 字段 ref_text 2026-09-01）
- **(6) 2026 年：パスキー强制（交易与出金）**（high）：「2026年12月12日より、パスキー認証を必須」：之后「お取引、ご出金のご利用には必ずパスキーによるログインが必要」。手机专用网站从 12/12（六）维护结束后开始；标准 Web 预定 12/18（五）16:20〜16:45 维护后改成只能用パスキー登录。没设パスキー的人只能查余力和持仓。通知全文没有提到 API（API 受不受影响：not found / 官方没写）。v4r10 的 API 登录 = 认证 ID + RSA 私钥，但打开 API 利用设定、注册公钥都要先用パスキー登录标准 Web。官方列的パスキー设备：Windows 11、iOS / iPadOS 17 以上、Android 10 以上（推荐 14 以上）；没有列 Mac（MACOS.md 已写「macOS 動作未確認，可用 iPhone」）。  
  来源：https://www.e-shiten.jp/important_info/20260708.html（2026-07-08（8/3 更新）；设备列表 https://www.e-shiten.jp/important_info/20260123.html（5/31 更新））
- **(6) 2026 年：API 版本、认证与使用请求**（high）：现行版本 v4r10（2026-08-29（六）发布，地址 https://kabuka.e-shiten.jp/e_api_v4r10/ ，デモ https://demo-kabuka.e-shiten.jp/e_api_v4r10/ ），v4r9 已于 2026-09-27 停止；改版目的是改成「各個別情報毎問合取得Ｉ／Ｆ」来取主数据（master），减轻系统负荷。v4r8 已于 2026-06-27 废止；从那天起 API 只用公开密钥方式登录、不需要电话认证。API 利用设定默认是「利用しない」，要自己改成「利用する」并注册公钥。v4r8 / v4r9 起加了功能 ID 检查：「マニュアル記載以外の値を指定時、20秒WAIT後にエラー応答」。使用请求（2026-03-10）：8:00〜15:30 是把客户的单发往交易所的时段，请避免高负荷请求（大量、频繁地调 CLMMfdsGetMarketPrice，或频繁轮询）；不公开具体次数上限；影响到其他客户时会先警告，严重的会停用 API。日线历史 18:00〜次日 3:30 更新；建议在 5:30〜8:00 取主数据。デモ和本番的 AuthID / 密钥分开。仓库适配器已经是 v4r10，与此一致。  
  来源：https://www.e-shiten.jp/api/20260728.html（2026-07-28（8/18 更新）；https://www.e-shiten.jp/api/20260310.html；https://www.e-shiten.jp/api/20260327.html（4/24 更新）；https://www.e-shiten.jp/api/20260513.html）
- **(6) 2026 年：交付书面改定（会挡 API 登录）**（high）：2026-10-01 改定版：「上場有価証券等書面（e支店用）」「金銭・有価証券の預託、記帳及び振替に関する契約のご説明」（有信用账户的再加「信用取引の契約締結前交付書面」）。理由是 2026 年 9 月底退出金融先物取引業協会。9/30 16:30 以后第一次登录，如果有未读书面，要点「同意してホーム画面へ進む」，不同意就不能登录、不能交易；用 API 的人「PCサイトでの確認が必要」。仓库 HANDOFF 已经记了（还没开户的话，开户后第一次登录时一起确认就行）。  
  来源：https://www.e-shiten.jp/important_info/20260911.html（2026-09-11）
- **(6) e支店 的服务时间（与执行器有关）**（high）：3:30〜5:30 因数据更新停止登录；注文・訂正・取消：0:00〜15:30 受理当日的单，15:30〜16:30 值洗い中停止受理，16:30〜23:59 受理下一个营业日的单（15:30 / 16:30 视行情可能推迟约 30 分钟）；現引・現渡 当日分到 15:40；端株 11:00〜11:40、15:00〜16:30 停止受理；股价板从 5:30 起可用；「年末年始はサービス時間が変更になる場合があります」（2026 年末的具体安排：not found）。另外，2026-09-27（日）8:00〜17:00 做过一次全系统停机维护（首页通知）。  
  来源：https://www.e-shiten.jp/Service/Time.html（页面无日期；2026-10-09 检索）
- **(6) 东证交易时间 / 收盘竞价规则（现在与预定的变更）**（high）：2024-11-05 起后场收到 15:30：15:25 结束连续竞价（ザラバ），15:25〜15:30 是クロージング・オークション的受理时间（プレ・クロージング，这段时间不成交，可以新下单 / 改单 / 撤单），15:30 板寄せ。东证另有「注文取消し等の重点監視」指引。已决定的变化：ランダムクローズ方式（收盘板寄せ的时刻每个营业日在一定范围内随机决定）2027-10-12 起实施（现行クロージング・オークション的参考图标注适用到 2027-10-08）；WG 报告（2026-04-22）里的方案是 15:29:30〜15:30:00 这 30 秒，最终范围以 2026-08-06 的规程改正为准，这次没有逐条核对。  
  来源：https://www.jpx.co.jp/equities/trading/strengthening/（2026-08-06（页面更新日）；随机收盘的时间范围：medium）
- **(6) 东证呼値（tick size）变更**（high）：2027-03-01 起，从按指数分类（TOPIX500 构成股）定呼値，改成按个股流动性（STR, Spread to Tick Ratio）指定呼値表；规则改正文件 2026-04-22（WG 报告）、2026-05-22、2026-08-06。现行表：TOPIX500 构成股 1,000円以下 0.1円、3,000円以下 0.5円……；交易单位 1 口的 ETF 等 1,000円以下 1円……仓库 qbreak/tick.py 已按 2026-08-06 版写了 2027 年的处理（还没公布各股分表时，用 C 表兜底）。  
  来源：https://www.jpx.co.jp/equities/trading/domestic/07.html（2026-08-06（页面更新日））
- **(6) 东证休市日（近期）**（high）：2026-10-12（一）スポーツの日 休市；2026-11-03（二）、11-23（一）休市；2026-12-31（四）休市（所以 12-30 是最后一个交易日）；2027-01-01〜01-03 休市；2027-01-11（一）休市。  
  来源：https://www.jpx.co.jp/corporate/about-jpx/calendar/index.html（2026-02-06（页面更新日））
- **(6) 其他 2026 年通知（与只做现物的关系不大）**（medium）：2026-10-01：信用买方金利 2.50% → 2.94%（2026-10-19 约定的新建仓起适用，已有建仓从 10-21 起）；2026-10-01：退出金融先物取引業協会。首页还列着 2025 年的行政处分（关东财务局 2025-04-08、日本证券业协会 2025-06-18、东证 / 大阪交易所 2025-06-20）和业务改善的后续（2026-01-07 明确经营责任、2026-02-20 人事变动）；这些是外部链接，内容这次没有读。系统故障报告页最新一条是 2021-10-21。  
  来源：https://www.e-shiten.jp/important_info/20261001-2.html（2026-10-01（通知列表 https://www.e-shiten.jp/ 2026-10-09 检索））

## 全部条目（审查 → 对抗核对）

### 立花 API 适配器（qbreak/brokers/tachibana.py、base.py、tachibana_sim.py、tests/test_tachibana.py，以及直接调用它的 probe / gate / 执行器接口）

- **TA-01 取价 API 整个失败时被当成「没有开盘价」：09:05 的开盘后买单会全部被放弃，09:20 也不会再试**（重要；部分属实；做的人 claude_code；工作量 S）
  - 说明：成立，但范围比原文窄。整个断网时不会悄悄放弃：open_phase 先调 quote_detail（异常被吞掉，返回 {}），接着 _place_deferred 会先调 b.positions() / b.cash()，这两个读不到就直接抛异常，DEFERRED 保留下来，09:20 会重试。只有取价这一路单独失败时才会悄悄放弃：PRICE 虚拟 URL 出错、价格应答 p_errno≠0、开盘高峰被限流等，而 REQUEST 这一路是好的。这时每一笔 DEFERRED 都变成 SKIPPED，理由写成「没有开盘价……模型也不买」，09:20 也不补。开盘时价格服务最忙，这种情况不算罕见。不会亏钱，也不会让持仓状态不明，后果是当天的买入全部漏掉、理由也写错。
  - 证据：qbreak/brokers/tachibana.py:460-466（except → log.debug → continue）；qbreak/live_unified.py:538-539（先取价）；qbreak/live_unified.py:461 与 :464（之后才调 positions / cash，断网时在这里抛出）；qbreak/live_unified.py:476-478（op 为空 → skip「模型也不买」）；qbreak/live_unified.py:1708-1711（open_pending 只认 DEFERRED）
  - 修法：quote_detail 区分「调用失败」和「字段为空」：调用失败时记 warning，并抛 BrokerError（或带失败标记返回）。open_phase 取价失败时保留 DEFERRED，事件记 error 并发通知，交给 09:20 重试。加对应单元测试（FakeTransport.fail_next 设成 clm_price）。
- **TA-02 probe 和 デモ发单检查会误判通过，覆盖面也缺主力单型**（上实盘前；核对属实；做的人 both；工作量 M）
  - 说明：probe 的「取价」「注文一覧」两步不会判失败：quote_detail / open_orders 吞掉异常，返回 {} / []，结果没有 ★，就算 OK；盘外取价本来就是 {}，也分不出是正常还是出错。order-test 测了当日指値买、寄付成行卖、撤单，也核对了明细字段（fields_missing），但没测执行器最常用的「寄付指値买」（sCondition=2 加价格）。gate 只看 ok，不看测了多久、测的是哪个版本。原文要求核对 CLMOrderList 的 r_list_* 和 r_pos_sellable，这部分理由不足：生产代码根本没用这两个字段，只有做 TA-04 时才需要。上线前唯一的验证就是这里，取价字段名如果错了会被当成通过，上线后开盘后补单和盘中手动单会悄悄失效，所以放在上线前处理。
  - 证据：run.py:3859-3862（取价 / 注文一覧步骤）；run.py:3866-3868（good = "★" not in r_）；qbreak/brokers/tachibana.py:464-466、771-776（吞异常）；run.py:3769-3811（order-test 内容，没有 cond=2 加价格的买单）；qbreak/live_gate.py:124-138（不看时间 / 版本）；grep r_list_order_no / r_pos_sellable：只在 tachibana.py 的定义和 tachibana_sim.py 里出现
  - 修法：probe 里取价 / 注文一覧调用失败就判 NG；交易时间内取价为空也判 NG，盘外显示「—」。order-test 加：寄付指値买 → 按注文番号撤单；盘中指値卖；核对 CLMOrderList 与 positions 的可卖股数字段名。结果文件记 API 版本（base URL）和时间；gate 在版本变了或超过约 30 天时要求重新测。
- **TA-03 HALT 撤不掉已经发出的单，系统里也没有撤单入口**（重要；核对属实；做的人 both；工作量 M）
  - 说明：成立。适配器的 cancel_order 只有 probe 在用。执行器、面板、liveu.sh 都没有撤交易所里挂着的单的入口。手动指令的「撤回」只能撤还没发出的；已经发出的早上寄付单，只会记一句「撤回来不及」。HALT 和远程停止都明确说不撤已发出的单。也没有订正。
  - 证据：grep cancel_order：只有 qbreak/brokers/tachibana.py:750/769 与 run.py:3806；qbreak/manual_orders.py:545-549（NOW_NO_CANCEL）；qbreak/manual_orders.py:995、1031（「撤回来不及：交易所的单已经成交」）；qbreak/panel.py:1534-1535（盘中已发出的单页面撤不了）；qbreak/live_unified.py apply_remote_halt 的 docstring（已发出的单不撤）
  - 修法：加 `liveu.sh cancel-open --broker tachibana`：只撤账本里今天 SENT / PARTIAL、有注文番号的执行器单，撤完用 order_status 确认，并写进账本 / 日志。用户在对话里明确说「停并撤单」才执行；可以选「HALT + 撤单」。面板对盘中挂单给「撤单」按钮（写指令，由执行器撤）。订正以后再说。
- **TA-04 一笔单状态不明（网络超时）会让第二天早上整个停下，只能人工去立花网页查**（重要；核对属实；做的人 both；工作量 M）
  - 说明：成立。还有一点让它更常发生：_place 把发单时的所有非 BrokerError 异常都记成 ERROR（状态不明），连「肯定没发出去」的情况也一样，比如 DNS 解析失败、连接被拒、TLS 握手失败，见 missed 第 2 条。状态不明之后，run_bar / now_phase 整体停下，规则的卖单也不下，只能人工 --resolve。
  - 证据：qbreak/brokers/tachibana.py:667-670（except Exception → ERROR）；qbreak/live_unified.py:55（UNKNOWN 含 ERROR）；qbreak/live_unified.py:1162-1167（run_bar）与 596-601（now_phase）遇状态不明就停；qbreak/brokers/tachibana_sim.py:252-256（_list 只有注文番号和约定数）
  - 修法：状态不明时只读查 CLMOrderList（今天、同代码），按 买卖 / 股数 / 条件 / 时间 找候选，把「候选注文番号、约定股数、均价」写进页面 / 通知，附上 --resolve 命令草稿。登记仍要用户在对话里确认。CLMOrderList 的代码、売買区分、受付时间字段先在デモ核对。
- **TA-05 约定确认不看状态码：被拒 / 失效的单会显示成「挂着等成交」**（方便；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立：_confirm 只看约定股数，status_code 只写进 Order.extra['broker_status']，执行器 _send 没把它抄进账本；对账也只用股数和均价。影响有限：寄付单不走 _confirm，第二天的对账按约定股数记账，结果是对的（没成交就记 UNFILLED，手动全卖会在下一开盘再卖）。只有盘中的手动单，在交易所侧失效 / 出错时页面会一直显示「等成交」，事后也查不到原因。所以降级为方便性问题。
  - 证据：qbreak/brokers/tachibana.py:684-701；qbreak/brokers/tachibana.py:693（broker_status 只放 extra）；qbreak/live_unified.py:358-360（_send 只抄 broker_id / order_date / note）；qbreak/live_unified.py:986-993；grep status_code / sWarning：除定义、sim、probe 外没有使用
  - 修法：在 spec 里定义终态码（7 取消完了 / 12 全部失効 / 受付エラー等，以デモ核对为准）。_confirm 遇到终态马上停轮询，返回 REJECTED / EXPIRED，并带上 sOrderStatus 文本。对账时把 status_code / status 写进 ExecOrder.note。顺带记录应答里的警告类字段。
- **TA-06 当天的成交当天看不到：寄付单和盘中单要到第二天 07:40 才知道**（重要；部分属实；做的人 claude_code；工作量 M）
  - 说明：大体成立，有一处不准：盘中单发出后，_confirm 会每秒查一次 order_status、最多查 20 秒，当场成交的能马上显示。原文说 order_status「只在第二天对账用」，不对。但早上的寄付单、开盘后补的单、20 秒内没成交的盘中指値，当天都看不到成交；09:05 / 09:20 的运行也不刷新约定；EVENT / WebSocket 的 URL 解密了但没有用。每天都会碰到，用户只能去立花 App 上看。
  - 证据：qbreak/brokers/tachibana.py:676-679（寄付单不确认约定）；qbreak/brokers/tachibana.py:681-707（_confirm 最多 20 秒）；scripts/install_launchd_live_u.sh:98-101（只有 4 个时点）；qbreak/live_unified.py:519-540（open_phase 不查早上那些单的约定）；qbreak/brokers/tachibana.py:393（EVENT URL 只解密不用）
  - 修法：加一个只读的「约定刷新」：09:20 的运行顺带做，另加 11:35 / 15:35 的 LaunchAgent（或盘中 --phase now 顺带）。对今天 SENT / PARTIAL 的单调 order_status，成交写进 summary / 页面 / 通知，不改模型状态，正式记账仍在第二天 07:40。长期可以改用 EVENT I/F 推送。
- **TA-07 钥匙串读不到时提示写成「缺少认证 ID / 第二暗証番号」，会把人引到错误的方向**（方便；部分属实；做的人 claude_code；工作量 S）
  - 说明：代码行为成立：_keychain 不管什么原因读失败都当「没有」，stderr 丢掉了，提示会写成「缺少认证 ID / 第二暗証番号」，让人以为要重新存密钥。gate 只查条目在不在（不加 -w），确认不了定时任务能不能真的读出来。不过发生的条件比较少见：LaunchAgent 跑在已登录的 GUI 会话里，登录钥匙串默认是解锁的；条目是用 security 自己建的，ACL 里就有它，读的时候不会弹授权框。降级为方便性问题。
  - 证据：qbreak/brokers/tachibana.py:205-215；qbreak/brokers/tachibana.py:245-248、256-257、622-624；qbreak/live_gate.py:140
  - 修法：_keychain 返回值和原因：按退出码 / stderr 分出「没有条目」和「钥匙串锁着 / 不允许交互」，给不同的提示（例如「请解锁登录钥匙串 / 系统设置里不要在睡眠时锁定钥匙串」）。gate 加一项：用和定时任务相同的方式试读一次，只报成功与否，不显示值。
- **TA-08 交付書面未読、维护、密钥失效都要到 07:40 才发现，没有提前预检**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立：没有提前登录的预检，第一次登录就是 07:40 的正式运行。交付書面未読、维护、密钥 / 认证失效都要到那时才发现，交付書面又只能在 PC 的标准 Web 上读。scripts/ 里只有手动的 probe，没有定时的。
  - 证据：qbreak/brokers/tachibana.py:390-391；scripts/install_launchd_live_u.sh:98-101；grep probe scripts/*.sh：只有 liveu.sh:20、186-188 的手动入口
  - 修法：每个交易日前一天晚上（例如 20:00，避开 03:30〜05:30）加一个只读预检：登录 → 取余力 → 登出，失败就发通知，写清原因和要做什么。注意每次登录会收到一封ログインメール，频率定为每天 1 次。
- **TA-09 API 版本提醒在新版本发布当天之后就消失了，旧版本停用时会突然登录不上**（重要；核对属实；做的人 both；工作量 S）
  - 说明：成立：提醒只在 next_release ≥ 今天时出现（run.py:3452 与 tachibana.py:411），发布日之后到旧版本停用之前这段（v4r9 停用前约 1 个月）没有提醒。发布之后这个字段会显示什么，要等实际看到才知道。还有一点：旧版本停用后，登录多半返回 HTTP 404 或非 JSON 应答，HttpTransport 抛出的是原生 HTTPError / JSONDecodeError，不是 BrokerError，所以 login() 里那句带 4 个原因的提示根本不会出现，run.py 也不会走「立花 API 出错」那条通知路径（见 missed 第 1 条）。
  - 证据：run.py:3451-3453；qbreak/brokers/tachibana.py:64-65（URL 写死 v4r10）；qbreak/brokers/tachibana.py:384-389（_check 之前的网络 / HTTP 错误不经过这个提示）；qbreak/brokers/tachibana.py:292-294（urlopen / json.loads 抛原生异常）
  - 修法：把第一次看到的发布日存进账本，只要 base URL 的版本号还低于新版本，就每天提醒（页面 + 通知 + gate 显示「未完成」）。登录遇到 HTTP 404 或非 JSON 应答时，提示「可能是旧版本已停用」。新仕様由用户在对话里确认后再改默认值。
- **TA-10 仕様覆盖文件会把所有默认值冻住，代码升级后不起作用**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立，而且比原文说的更可能发生：MACOS.md:369 让用户运行 `tachibana-probe --demo --dump-spec`，MACOS.md:430 的上线清单还要求「已对着官方仕様書改过 tachibana_spec.json」。按文档走一定会生成这个文件，而 dump 写的是全部字段，包括 base_live / base_demo。之后代码把默认值升到新版本，这个文件里的旧值照样整个覆盖，加载时只记一条 log.info。文档写的路径是 var/，Mac 上实际是 $QBREAK_HOME（~/.qbreak/home）。
  - 证据：qbreak/brokers/tachibana.py:185-201；MACOS.md:369、373、430；qbreak/paths.py:20-24（home = QBREAK_HOME 或 var）
  - 修法：dump 只写与默认值不同的键，或者带上版本号。加载时如果覆盖了 base_* 且与代码默认值的版本不同，就在页面和通知里警告，gate 也显示。改正文档里的路径。
- **TA-11 2027-03-01 呼値改正后，一手 1 口的 ETF 会算出不合法的限价**（方便；部分属实；做的人 claude_code；工作量 S）
  - 说明：代码确实没传 lot，也没传执行日（所有 round_to_tick 调用都没有 lot），2027-03 起一手 1 口的 ETF 会按 C 表取整，模拟交易所也查不出来。但只读核算后，受影响的只有一手 1 口、价格 ≤ ¥500 的 ETF：100〜500 円带 C 表是 0.5、≤100 円带是 0.1，都不是 O 表 1 円的整数倍。现在规则会用到的 1655、1545（一手 10 口）不受影响；1482（一手 1 口，约 ¥1,485）按 C 表取整成 1484，在 O 表上也合法。原文列的 1329 / 2558 / 1540 / 133A 价格都在 ¥1,000 以上，C 表的呼値是 O 表的整数倍，也不受影响。降级为方便性问题，2027-03 之前补上即可。
  - 证据：只读计算：round_to_tick(350.7,'2243.T','BUY',on=2027-03-02)=350.5，加 lot=1 = 350.0；1482.T 1485.3 → 1484.0（tick 2，在 O 表上合法）；1545.T、1655.T 一手 10 口，按 C 表；qbreak/brokers/tachibana.py:602、607；grep round_to_tick(：没有任何调用传 lot；qbreak/brokers/tachibana_sim.py:93-96；var/sim.json：core 1655.T，闲置资金 Q1B（1545 / 1482）
  - 修法：_place 把 lot（立花マスタ的 sBaibaiTani 或执行器的 eng.lots）和执行日传给 round_to_tick。2027-01 JPX 公布分表后填 STR_CLASS。在デモ核对立花マスタ有没有呼値単位，有就直接用立花的。模拟交易所用独立的呼値表检查限价在不在格子上。要在 2027-03-01 之前做完。
- **TA-12 盘中卖单在适配器取不到现价时会变成成行**（方便；部分属实；做的人 claude_code；工作量 S）
  - 说明：代码路径成立：卖单 limit=None，适配器第二次取价失败时 px=0，会发成行。但 now_phase 已经先取过一次价，没价格就不下卖单（core 卖单也一样）。所以要出问题，必须是执行器那次取价成功、紧接着适配器自己那次（内部已经重试 3 次）又失败，时间窗很窄。卖的又是日経225 的大票 / ETF，按成行成交的损失有限。属于设计上前后不一致，降级为方便性问题。
  - 证据：qbreak/live_unified.py:352（卖单 limit=None）；qbreak/live_unified.py:737-740、684-687（卖之前已经要求有现价）；qbreak/brokers/tachibana.py:594-597、605-607、645；qbreak/brokers/tachibana.py:614-615（只挡买单）
  - 修法：盘中卖单由执行器用已经取到的现价算好指値（卖向上取整）再传给适配器。适配器在不是寄付、没有指値、又取不到现价时返回 BLOCKED（稍后重试），不发成行。
- **TA-13 不支持 NISA：执行不了「核心 ETF 放 NISA（N2）」，持仓也不分課税区分**（重要；部分属实；做的人 both；工作量 L）
  - 说明：说适配器不能按单指定課税区分、持仓把各区分合计，这是事实。但这已经是 HANDOFF〔72〕里登记的待决事项：选项是 ① 用 N2 时另做执行器工程，② 只展示，③ 不用。用户没决定之前，全部按特定口座运行没有缺口。只有用户自己在 NISA 里买了同一只票时，才会出现「核对显示一致、卖单却被拒」的情况。
  - 证据：HANDOFF.md:906（〔72〕N2 要用户先确认，再另做执行器工程）；qbreak/brokers/tachibana.py:640（固定用 self._tax）；qbreak/brokers/tachibana.py:493-509（合计各区分）
  - 修法：用户决定采用 N2 之后：发单可以按单指定 sZyoutoekiKazeiC；positions 保留每个課税区分的明细（股数 / 可卖股数）；卖单按持仓所在的区分发；记录 NISA 年度额度。NISA 成長投資枠的代码先在デモ核对。
- **TA-14 同一账户只能有一个会话：probe / dry-run 会把执行器的会话踢掉；面板的立花账本只能显示晚 20 分钟的价**（方便；核对属实；做的人 claude_code；工作量 M）
  - 说明：成立：RunLock 是按账本加的（tachibana / tachibana_dryrun / tachibana_demo 各一把），probe 不拿锁，所以可能和 07:40 的运行同时登录本番，互相把对方的会话踢掉。被踢的一方只重登一次。面板的立花账本现价用 Yahoo（约晚 20 分钟）。MACOS.md 第 3 步还要用户直接跑本番的 dry-run。
  - 证据：run.py:3217-3221、3236（每个账本各自一把锁）；run.py:3840-3880（probe 不拿 RunLock）；qbreak/brokers/tachibana.py:428-438；qbreak/panel.py:19
  - 修法：所有会登录本番的命令（live-u、dry-run、probe）共用一把「立花本番会话锁」。执行器每次运行时顺便把立花的现价快照（带时刻）写到本机，面板对立花账本优先显示它。日志记录每次登录的时间，方便和ログインメール对照。
- **TA-15 本番和デモ共用一个 ARM；提示说「收盘后清空」，但没有任何东西去清**（方便；部分属实；做的人 both；工作量 S）
  - 说明：ARM 本番 / デモ共用、提示里「收盘后清空」是旧 daemon 时代的话而代码里没有清空（每天全自动本来就需要 ARM 一直在），这两点成立。面板只看文件在不在、不看内容是 ARMED，也不看 QBREAK_ARM 环境变量，这点也成立。但路线图里没有「デモ上跑执行器、要建 ARM」这一步：order-test 自己把 require_arm 设成 False（run.py:3776），所以共用 ARM 的风险很低。
  - 证据：qbreak/brokers/tachibana.py:520-526、536-537；qbreak/panel.py:1361、1389；run.py:3776（order-test 关掉 ARM 检查）；MACOS.md:128-137（路线图没有 live-u --demo 加 ARM）
  - 修法：ARM 按环境分开（例如内容写 ARMED-LIVE / ARMED-DEMO，或用单独的 ARM_demo 文件）；面板按内容判断；改正提示文字（是否自动清空由用户决定）。改 ARM 的含义要用户同意。
- **TA-16 不检查 Mac 时钟偏差（p_sd_date 要在服务器时间 ±30 秒内）**（方便；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立：p_sd_date 直接用本机时间，没有任何时钟偏差检查；doctor 也不查。macOS 默认自动对时，出问题的概率低。
  - 证据：qbreak/brokers/tachibana.py:360；grep ntp / sntp / 时钟 / Date 头：qbreak、run.py、scripts 里都没有
  - 修法：HttpTransport 读应答的 HTTP Date 头算时差：>10 秒记 warning，>25 秒先不发单，提示「Mac 时钟不准（系统设置 → 日期与时间 → 自动设置）」。
- **TA-17 券商侧逆指値（盘中止损保险）实盘执行器没有用**（方便；核对属实；做的人 both；工作量 L；涉及交易规则）
  - 说明：成立：place_protective_stop 只有旧的 daemon 在用，live-u 没有调用。真要用就是改离场规则（changes_trading_rules=true），要先研究、再由用户决定，不属于工程缺口。
  - 证据：qbreak/brokers/tachibana.py:718-723；grep place_protective_stop：只在 daemon.py / rakuten_rss.py 出现；qbreak/live_unified.py：没有调用
  - 修法：如果要做：先登记一项「只防极端暴跌的灾难止损」研究，再按结果和用户同意决定；不在执行层直接加。
### 实盘执行器（qbreak/live_unified.py、qbreak/unified.py、qbreak/manual_orders.py、qbreak/live_gate.py、run.py live-u 路径；只读审查，2026-10-09）

- **LU-01 09:05 开盘后补单的单笔上限没按权益设，仍用默认的 30 万円**（上实盘前；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实。09:05 / 09:20 是新进程，broker 的上限是 run.py 传入的默认 ¥300,000。open_phase() 不按权益设上限（只有 place() 与 now_phase() 设）。典型场景是核心 ETF 切换（1545→1482）或卖个股后买核心：开盘前余力约为 0，整笔核心买单约 ¥100 万都留到开盘后，在 _preflight 里被 BLOCKED。入金超过约 ¥120 万后，个股名额也会超过 ¥30 万。另外，适配器层的 BLOCKED 不会写进 ux.blocked，所以通知只发 info 级别（见 missed）。演练里 open_phase 用的是前一天 place() 留在同一个 broker 对象上的上限，所以测不出来。
  - 证据：run.py:3399-3405：TachibanaBroker(max_order_value=a.max_order_value or 300_000)，auto_cap=True；qbreak/live_unified.py:380-381、603-604：只有 place / now_phase 设上限；qbreak/live_unified.py:519-541：open_phase 不设上限；qbreak/brokers/tachibana.py:533-534：notional > max_order_value 时 BLOCKED；qbreak/live_unified.py:1708-1711：open_pending 只认 DEFERRED，09:20 重试不再试；qbreak/live_unified.py:1287-1301：rehearse 跨天复用同一个 broker 对象
  - 修法：open_phase() 开头同样按账本决策日的权益设定 b.max_order_value（或者把 auto cap 移进 _send 统一处理）；补一个「每个阶段新建 broker」的测试；开盘后被 BLOCKED 的单也要让 09:20 重试看得到。
- **LU-02 09:05 取不到价、或股票还没寄り付き 时，补单直接放弃，理由写错，也不重试**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：机制属实，但发生条件比原说法窄。网络整体断掉时，_place_deferred 开头的 b.positions() / b.cash() 会抛 BrokerError，整次运行中断，单仍是 DEFERRED，09:20 会重试。真正会被放弃的是两种情况：①取价这一次请求失败或被暂时拒绝（返回空值）；②09:05 还没寄り付き 的票（特別気配）。这两种都会被标成 SKIPPED，理由写的是「模型也不买」，这不对：模型按日线开盘价，晚开盘也照样买。结果是少买、和模型出现分叉，不会下错单，所以降为 important。
  - 证据：qbreak/live_unified.py:538-539：open_phase 一次性调用 quote_detail；qbreak/brokers/tachibana.py:461-466：取价异常只记 log.debug，然后 continue；qbreak/live_unified.py:477-480：没有始値就 SKIPPED「模型也不买」；qbreak/live_unified.py:452-453：positions() 在取价之后调用，整体断网时会抛错，不会走到 SKIPPED；qbreak/live_unified.py:1708-1711：open_pending 只认 DEFERRED
  - 修法：把「取价整体失败」和「有现价但还没有始値」分开：前者报错、单保持 DEFERRED、发通知；后者单保持 DEFERRED，到 09:20 重试仍没有始値才放弃。放弃时记 model_diff 和真实原因。补测试：取价异常、寄り遅れ。
- **LU-03 个别行情落后时，状态照样推进；重试只补发旧决策的单；落后那只当天的止损检查永远被跳过**（重要；核对属实；做的人 claude_code；工作量 M）
  - 说明：属实。行情落后只调用 ux.block()，run_bar 照常对账、做 close_phase 并存盘。数据缺的那只票 A.has=False，当天不检查离场、不计持有天数。08:35 重试时 idxs 为空，只走 place(k) 补发旧决策的单，不重算；那一天的离场判断以后也不会补。需要注意：云端模拟盘遇到缺数据时也是跳过，所以这是数据完整性问题，不是实盘独有的问题。
  - 证据：run.py:3417-3425：落后只 ux.block；qbreak/live_unified.py:1171-1196：block 时仍 close_phase 并存盘；qbreak/unified.py:537-538：if not A.has[i, j]: continue；qbreak/live_unified.py:1210-1219：没有新 K 线时只 place(k)；qbreak/data.py:604：LAGGING 只是登记，不补数据
  - 修法：落后的票涉及持仓、核心 ETF 或指数时，在 run_bar 之前抛 ExecutorError，状态不推进，让 08:35 重试用新数据完整重算一遍；到 08:50 仍然落后，再按现在的方式挡住下单并通知。
- **LU-04 实盘告警到不了手机：webhook / 邮件没有接进定时任务**（上实盘前；核对属实；做的人 both；工作量 S）
  - 说明：属实。notify 只读 os.environ。launchd 的 plist 只带 QBREAK_LIVEU_HOME / QBREAK_PYTHON 等几个变量；liveu.sh 只从钥匙串读 J-Quants 的密钥，不读通知地址；也没有手机推送（手机面板是拉取式的，没有 Push）。执行器停下、持仓不一致这类警报只出现在 Mac 的通知中心，人不在 Mac 前就看不到，止损可能好几天没人发现。
  - 证据：qbreak/notify.py:22-45：只读 QBREAK_WEBHOOK / QBREAK_SMTP 环境变量；scripts/install_launchd_live_u.sh:74-81：EnvironmentVariables 不含通知设置；scripts/liveu.sh:88-89：只有 qbreak-jquants 从钥匙串读；scripts/ 里搜 WEBHOOK 没有结果；qbreak/panel*.py 搜 serviceWorker / PushManager / Notification(：没有；qbreak/live_gate.py:101-196：门槛和准备里都没有通知通道这一项；MACOS.md:436 / README.md:881：export QBREAK_WEBHOOK（launchd 读不到）
  - 修法：liveu.sh 在 run / news 时从钥匙串读通知地址进这个进程（例如服务名 qbreak-webhook，由用户自己用 security add-generic-password 存，不回显）；加一条 `liveu.sh notify-test` 发测试消息；gate 的「准备」加一项「手机能收到通知」。
- **LU-05 没有「Mac 没跑」的告警（死人开关）**（重要；核对属实；做的人 both；工作量 M）
  - 说明：属实，但有部分缓解：pmset 工作日唤醒（gate ⑦ 会检查）、08:35 / 09:20 重试、launchd 醒来后补跑错过的定时任务。登录时的自动补跑（mac_login）故意不补跑立花本番。Mac 关机或断网一整天时，没有任何外部方会发现：云端看不到本机账本，live-u 路径没有心跳。
  - 证据：qbreak/live_unified.py:1208-1209：恢复运行后只记一条 warn；qbreak/mac_login.py:42-43：立花本番登录时不补跑；搜 heartbeat：只有旧守护进程 qbreak/daemon.py；live_unified.py / liveu.sh 里都没有；MACOS.md §8 表：都错过 → 那天没下单
  - 修法：每次 morning / open 运行成功后 ping 一个心跳 URL（地址存钥匙串）；外部服务在交易日 09:30 前没收到 ping 就推送到手机。也可以用 LU-04 的每日摘要代替：没收到摘要就算异常。页面显示「最近一次成功运行」的时间。
- **LU-06 状态不明的单只能人工查注文一覧、再手打 --resolve，期间整个执行器停摆；登录失败也被当成状态不明**（重要；核对属实；做的人 claude_code；工作量 M）
  - 说明：主张属实，一条证据要更正：order_status 执行器其实在用（_collect_fills 按注文番号对账）。没用到的是注文一覧 open_orders。状态不明的单没有注文番号，要自动匹配就得靠注文一覧，这部分确实缺。「发单前登录失败 → ERROR → 当作状态不明」也属实，而且能走到：08:35 重试没有新 K 线时，place() 先发卖单、不先调 positions / cash；这时网络断了，login 抛错，_place 会把它记成 ERROR，第二天整个执行器停下。
  - 证据：qbreak/brokers/tachibana.py:632-637：login 失败 → ERROR（实际肯定没发出去）；qbreak/live_unified.py:54-55、1173-1178：UNKNOWN 包含 ERROR，run_bar 抛 ExecutorError；qbreak/live_unified.py:421-423：place 先发卖单，之后才调 b.cash()；qbreak/live_unified.py:990：order_status 已在用（更正原证据）；qbreak/brokers/tachibana.py:771-776：open_orders 只有 run.py:3862 的 probe 用；qbreak/panel.py 搜 resolve / UNKNOWN / 状态不明：没有
  - 修法：① 发单前就失败的（登录、凭证）改记为 BLOCKED，可以重试；② 出现状态不明时，先只读查当天的注文一覧 / 明細，按票、方向、股数、时间能唯一匹配就自动登记并写日志，匹配不上才停下并推送到手机（附上候选单）；③ 面板上显示状态不明的单，加「确认登记」按钮（仍要用户点）。
- **LU-07 已经发到交易所的单撤不了，盘中单也没人跟进**（重要；核对属实；做的人 claude_code；工作量 M）
  - 说明：属实。适配器的 cancel_order 已经实现，门槛④也验证过撤单，账本里存了 broker_id 和 order_date，但执行器、面板、liveu.sh 都没有撤单入口。HALT 只挡新单。盘中单发出后不再跟踪，要到第二天早上对账才知道结果。
  - 证据：qbreak/brokers/tachibana.py:750-765：cancel_order 已实现，HALT 时也允许；qbreak/live_unified.py：搜 cancel_order / .cancel( 没有调用；qbreak/manual_orders.py:549：NOW_NO_CANCEL；qbreak/live_gate.py:136-143：门槛④ 验证按注文番号撤单
  - 修法：加 `liveu.sh cancel-open --broker tachibana`，面板 / 手机加「停止下单并撤销未成交的单」：对当天 SENT / PARTIAL 的执行器单逐笔调用 cancel_order 并记进账本（撤单只会减少风险，HALT 时也允许）。盘中单下单后 N 分钟只读查一次成交并通知。撤单会让实盘和模型不同，所以只由用户触发。
- **LU-08 持仓不一致之后没有修复工具；一处不一致就停掉全部下单**（重要；核对属实；做的人 both；工作量 M）
  - 说明：属实。check_broker 只要有一只票对不上就挡住全部单，包括其他持仓的止损卖出。修复工具只有 --resolve，它只能改单，不能改持仓。股数差只对 10 天内登记过的拆股比例容忍。
  - 证据：qbreak/live_unified.py:1093-1118：任何一只不一致就 block 全部；qbreak/live_unified.py:1103-1110：只容忍 splits 里登记的比例；run.py:4163：只有 --resolve / --filled / --px；搜 adopt / repair / 修正账本：run.py、live_unified.py、liveu.sh、panel.py 都没有
  - 修法：加 `liveu.sh repair --broker tachibana`，先自动备份账本，再列出差异；每只票选「按立花股数更新（拆股 / 并股）」「从账本去掉（已经变现金 / 已经人工卖出）」或「保持」，要用户逐只确认，结果写进日志。另一个可选项：不一致只涉及某几只时，其余持仓的卖单照常下（这改变闸门行为，要用户同意）。
- **LU-09 实盘账本没有备份；文件坏了会从 ¥100 万的空账本重来**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实。不过账本是原子写入（atomic_write_text），坏文件的概率不大。更实际的风险是磁盘或误删。坏了以后 read_json 会把文件改名为 .corrupt、返回空，执行器按 capital_jpy 新开一个账本：有持仓时会被持仓核对挡住，天天如此；空仓时就悄悄从头开始。out/ 里的汇总有持仓与止损价，但没有峰值、持有天数、在途单、入出金、手动指令，不能用来恢复。
  - 证据：qbreak/utils.py:36-47：坏文件改名后返回默认值；qbreak/live_unified.py:102-105：load_state → UState(cash=capital)；qbreak/live_unified.py:145-153：save 用 atomic_write_text，没有历史版本；搜 backup / 备份：run.py、live_unified.py、liveu.sh 都没有（utils.py:62 只是日志轮换）
  - 修法：每次 save 前把上一版复制到 state/backup/（按日轮换，保留 30 份）；立花账本读坏时抛 ExecutorError 停下并通知，不自动新开账本；页面上写「最近一次备份」。备份不放进仓库（公开仓库，而且含持仓）。
- **LU-10 实盘的起始本金按 sim.json 的 ¥100 万算，入金不同时收益和第一天的提醒都会错**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实，但严重度高估：下单和仓位只按券商的買付可能額算（决策在现金同步之后），不受影响。受影响的只有累计收益、页面上的「起始 ¥100 万」，以及第一天的误报：入金额和 ¥100 万差 ≥ ¥5 万时，_match_flows 会提示「请登记入出金」，照做的话投入本金会被重复计算。降为 important。
  - 证据：run.py:3393：load_state(book, ucfg.capital_jpy)；run.py:3478-3480：daily_text / invested_jpy 按 capital_jpy 算；qbreak/desktop_page.py:101-110；qbreak/live_unified.py:1144-1158：没有历史时 eq = 现金；|差| ≥ 5 万就提示登记；qbreak/live_unified.py:1181-1184：现金同步在 close_phase（决策）之前
  - 修法：立花账本第一次核对成功时，记下 live_start {日期, 買付可能額}；之后的收益基准 = 它 + 登记过的入出金；第一次现金同步不发提醒。
- **LU-11 「先用较小金额跑 1〜2 周」没有具体做法，也没定加到计划金额的标准**（重要；核对属实；做的人 both；工作量 M；涉及交易规则）
  - 说明：属实。只有「先用较小金额跑 1〜2 周」这句话，代码里没有试运行资金上限，也没写加到计划金额的判定标准。sim.json 的个股名额是 position_pct 0.25、one_lot_cap_pct 0，小额时大多数票买一手就超过名额，试运行基本只会买核心 ETF。选项 C（加资金上限）要改仓位，属于改交易规则。
  - 证据：qbreak/live_gate.py:203：只有文字提示；var/sim.json unified：position_pct 0.25、one_lot_cap_pct 0.0、max_positions 4；HANDOFF.md:1231：¥100 万时 213 只里 140 只一手就超过名额
  - 修法：先由用户定方案：A 全额入金，头 2 周看执行质量报告（LU-18，不改规则）；B 小额入金，接受只测到 ETF；C 加「试运行资金上限」（会改仓位 → 要先登记、记进 sim_changes、用户同意）。不论选哪个，入金前都先做只读试算：金额 X 时股票池里一手买得起的有几只；并事先写下加到计划金额的判定条件。
- **LU-12 上线初期和云端比较，会天天报「拿的票不同」**（方便；部分属实；做的人 claude_code；工作量 S）
  - 说明：机制属实：实盘第一次运行不继承云端的持仓（模拟账户会从云端起步，立花不会）。但按现在的状态（2026-10-08 云端没有个股，只有 1545 4,110 口），上线时只有第一天会因为核心 ETF 还没成交而报不同，第二天起就一致，不会天天报。只有上线时云端正拿着个股，才会连续几周报「拿的票不同」。降为 convenience。
  - 证据：run.py:1538-1545：第一次运行只取最新一天；run.py:3388-3392：从云端起步只对 paper；qbreak/live_unified.py:1339-1356：立花模式只比品种；var/state/unified_state.json：pos 为空，core 1545.T 4110
  - 修法：记下实盘开始日；比较时，云端在开始日之前买进的个股标为「上线前的持仓，预期不同」，不发 warn，只对开始日之后的新买卖报不一致；页面上显示「还剩几只旧持仓没换完」。
- **LU-13 上线检查（gate 的「准备」部分）少了几项**（重要；核对属实；做的人 both；工作量 S）
  - 说明：属实。gate 的「准备」只看本番只读检查、钥匙串、私钥、cryptography、定时任务文件是否加载、pmset。没有检查：launchd 环境下真的跑成过（目前只有在终端里做的 probe）、通知通道、Mac 时区是否为 JST（安装脚本只 echo 提醒）、doctor。dry-run（MACOS 第 3 步）用的是单独的账本 _dryrun，不污染实盘账本，但 gate 也不检查它做过没有。
  - 证据：qbreak/live_gate.py:101-196：check() 的全部检查项；scripts/install_launchd_live_u.sh:54-55：时区只 echo；run.py:3217-3221：dry-run / demo 各用一份账本；MACOS.md:134、139：上线步骤第 3、5 步
  - 修法：只加进「准备」，门槛数字不变：立花账本里至少有 1 次定时任务成功运行，且单都因为没 ARM 被挡（说明 launchd 下登录和核对都正常）；时区为 +0900；通知测试成功；doctor 通过。上线后头几天，把开盘前余力和核对结果列在页面上。
- **LU-14 开户时要做的账户设定还没进清单（配当受取方式等）**（重要；核对属实；做的人 user_action；工作量 S）
  - 说明：属实。开户清单里只写了「特定口座（源泉徴収あり）」，没写配当金受領方式（株式数比例配分方式）。不设的话，个股分红和 ETF 分配金不进立花账户，执行器又以買付可能額为准，等于这部分收益不在这个账户里，也不能在特定口座里做损益通算。不影响下单，所以是 important、需要用户自己操作；MRF / 自动 sweep 有没有、算不算进買付可能額，也要开户时确认。
  - 证据：MACOS.md:323-324：开户步骤只写了特定口座；搜「比例配分方式 / 受領方式」：只在 HANDOFF.md:906 的 NISA 选项里出现；run.py:3429：实盘 credit_dividends=False（按 paper 传）；live_unified.py:1119-1131：现金以買付可能額为准
  - 修法：在 MACOS §2 开户步骤里加上「配当金受領方式 = 株式数比例配分方式」和上面两项确认；gate 的「参考」加一行，让用户自报已经设定。
- **LU-15 下单前不拿立花自己的前日終値核对 Yahoo 行情**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实：执行器不拿立花的 pPRP（前日終値）核对 Yahoo 行情。但修复建议里「挡住那只票的单」与用户 2026-09-28 的决定（行情交叉核对「先只报警」）不一致：挡单要用户另外同意；只报警、写进页面和通知，则可以直接做。
  - 证据：qbreak/brokers/tachibana.py:453-479：quote_detail 返回 prev_close；搜 prev_close：执行器路径没有，只有 run.py:3779 的 probe 用；run.py:1592、1938-1940：price check 只在云端 sim-day 里跑，注明用户决定「先只报警」
  - 修法：07:40 核对之后，对持仓、要下单的票和核心 ETF 取一次 pPRP（一次请求，最多 120 只）；与 Yahoo 最新收盘差超过 1%（排除当天拆股）就挡住那只票的单并通知。这只是数据闸门，不改规则。
- **LU-16 盘中没有任何提醒，立花那边也没有保护单（文档里还留着旧说法）**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实。执行器只在 07:40 / 09:05 看行情，盘中对持仓没有任何价格提醒；place_protective_stop 存在但执行器不调用。MACOS §8 表的后几行和「逆指値是永远在岗的保险」那句，以及 README 上线清单里的 --protective-stop，说的都是旧守护进程，现行执行器不挂逆指値，容易让人以为有券商侧保护。盘中提醒本身是方便功能；文档会误导人，所以整体算 important。
  - 证据：qbreak/config.py:193：stop_fill_mode = next_open；qbreak/brokers/tachibana.py:718-723：place_protective_stop，live_unified 里没有调用；MACOS.md:462-466：§8 表与「一句话」；README.md:877：--protective-stop 打开；qbreak/news.py / dashboard.py：只有消息的行业影响，没有持仓价位提醒
  - 修法：只提醒、不下单：面板 / 仪表盘本来就在取现价，持仓盘中跌破止损价、跌幅 ≥ 8% 或ストップ安时推送到手机（依赖 LU-04），附一句「要卖就点卖出」；改正 MACOS §8 和 README 的说法。灾难逆指値另外立研究项。
- **LU-17 实盘每天早上自动使用开发分支的最新代码**（重要；核对属实；做的人 both；工作量 M）
  - 说明：属实。立花早上 07:40（以及 08:35 重试、开盘前面板触发的 --retry）每次运行前都 git pull --ff-only 开发分支，再拷入 sim.json 等配置。当天推上去的代码第二天就直接进实盘，没有固定版本，也没有「先在模拟账户跑过一天」这一关；只有 open / now 阶段不 pull。
  - 证据：scripts/liveu.sh:203-224：不是 open / now 阶段就先 git pull；scripts/liveu.sh:44-50：sync_inputs；CLAUDE.md：~/qbreak-src 每个交易日 07:40 只 git pull
  - 修法：立花用单独的工作树或标签（例如 live-ok）：数据文件照常每天拉；代码只有在「模拟账户用这个提交成功跑过至少 1 个交易日、测试也通过」之后才前进。页面上显示实盘用的代码版本；需要紧急修复时，用户可以手动让它前进。
- **LU-18 没有实盘执行质量的汇总（试运行要靠它判断能不能加钱）**（重要；部分属实；做的人 claude_code；工作量 M）
  - 说明：主张属实：没有跨天的执行质量汇总。证据要更正：cash_drift 不是「只写不读」，register_flow 会读最近 5 条来匹配入出金。账本的 history 保留 250 天的单（含 ref_px、limit、filled_px），数据都在，缺的只是汇总报告。只有把它当成「加到计划金额」的判断依据时，才算 important。
  - 证据：qbreak/live_unified.py:1125-1126：写 cash_drift；1650：register_flow 读（更正）；qbreak/live_unified.py:148、1085-1087：history 保留 250 天的单；搜 滑点 / 执行质量 / slippage：desktop_page.py、panel.py 里都没有
  - 修法：加 `liveu.sh quality --broker tachibana`（只读）和页面上的一节：按 history 汇总成交价差（bp）、费用与税的差、没成交 / 被挡 / 放弃的次数、与云端的持仓差；配合 LU-11 事先写下的判定条件使用。
- **LU-19 出金不方便：卖出的钱第二天又会被规则买回 ETF**（方便；核对属实；做的人 both；工作量 M）
  - 说明：属实。flow 只影响收益显示；卖出得到的现金在出金之前，会被下一次决策当作闲置资金买回 ETF，现在只能手动把闲置资金比例改成 0 再改回来。修复建议里的 --reserve 会把这笔钱从权益里扣掉，从而影响个股仓位的金额，等于改仓位，要用户同意（建议按 changes_trading_rules 处理）。
  - 证据：qbreak/live_unified.py:1639-1641：register_flow 写明不影响下单；qbreak/live_unified.py:1119-1131：现金 = 買付可能額，直接进决策
  - 修法：加 `liveu.sh flow -300000 --reserve`：在出金到账前，把这笔钱从可用现金和权益里扣掉（等于提前出金；现金不够时按规则先卖核心 ETF），看到出金到账后自动解除。这样算算不算改仓位，请用户确认。
- **LU-20 上线后面板默认还是模拟账户，而模拟账户的定时任务已被卸载**（重要；核对属实；做的人 both；工作量 S）
  - 说明：属实。切换到 tachibana 时会卸载 com.qbreak.liveu.paper，而面板不带 book 参数时默认是 paper。之后在默认页点的指令写进一个已经不再运行的模拟账本；盘中这条路要求「早上的运行已完成」，所以指令会一直等着。另外，登录自启动上线后仍然只打开 page_paper.html（见 missed）。
  - 证据：scripts/install_launchd_live_u.sh:15、93-94：切换模式时卸载 paper；qbreak/panel.py:2014-2016：_book_of 默认 paper；qbreak/live_unified.py:579-580：盘中要求早上的运行已完成
  - 修法：二选一，由用户定：上线后面板默认打开立花，模拟账户页标「已停止」并禁用按钮；或者保留模拟账户的定时任务并行运行，作为同一份 Mac 数据下的模型参照。确认框里醒目地写出账本名。
- **LU-21 盘中手动单不看早上「持仓不一致」的结果**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实。self.blocked 只在内存里，不写进账本；now_phase 只查 HALT、时间、早上跑过没有、K 线、状态不明的单，以及卖出时券商股数是否不少于账本，买入 / 加仓不看早上的持仓核对结果。更严重的同类问题是 08:35 的自动重试，见 missed 第 1 条。
  - 证据：qbreak/live_unified.py:1118、1235：block 只存在内存和汇总里；qbreak/live_unified.py:569-589：now_phase 的闸门；qbreak/live_unified.py:757-758：只有卖出检查 held
  - 修法：把当天早上的 block 原因写进账本；遇到持仓不一致或状态不明时，盘中这条路拒绝下单（卖出是否放行可选，要用户同意），面板上显示原因。
- **LU-22 拆股权利落ち当天早上下的单，按拆股前的股数和价格**（方便；核对属实；做的人 claude_code；工作量 M）
  - 说明：属实，但很少发生。权利落ち日早上下的单按拆股前的股数和限价；拆股记录要到第二天处理那根 K 线时才从 yfinance 进来。寄付买单只买到计划金额的 1/k；并股可能留下端株，进而触发持仓核对停下。
  - 证据：qbreak/live_unified.py:1179-1180：corp(k) 只处理已收盘的 K 线；qbreak/unified.py:944-979：apply_corp_actions 只看已经发生的；qbreak/live_unified.py:1154-1169：on_corp_action 调整账本里的单
  - 修法：07:40 时，对要下单和持有的票查 JPX / J-Quants 的分割 / 併合预定：成交日正好是权利落ち日的，按比例调整股数和限价（或者当天不买并报警）；并股后出现端株时报警给用户。
### Mac 上的运维：liveu.sh / mac_setup.sh / install_launchd_*.sh / notify.py / daemon.py / MACOS.md / HANDOFF 运行手册

- **OPS-01 推送到手机的通知通道没接上（只有 Mac 本机通知）**（上实盘前；核对属实；做的人 both；工作量 S）
  - 说明：属实。notify.send 只读环境变量（notify.py:23,35）；立花 4 个 plist 的 EnvironmentVariables 没有 QBREAK_WEBHOOK / SMTP（install_launchd_live_u.sh:74-81），liveu.sh 也不像 jq 那样从钥匙串读（liveu.sh:85-90 只有 J-Quants）。run.py 里锁失败、执行器停下、每日汇总这几处其实都调用了 notify.send（run.py:3240-3243、3441-3444、3485-3491），只是因为没配置，什么都不发。崩溃这条路径（liveu.sh:263-268）只走 osascript；后面那次 --status --alert 也没带 --notify。MACOS.md:436 还写着「export QBREAK_WEBHOOK」，这种写法到不了 launchd。另外 gate 不检查 osascript 通知有没有被允许（install_launchd_live_u.sh:129 只提醒一句）。上实盘后人多半不在 Mac 前，执行器被挡（不下单，也不执行离场）时没人知道，所以维持 before_live。
  - 证据：qbreak/notify.py:23,35；scripts/install_launchd_live_u.sh:74-81；scripts/liveu.sh:53-57,263-268；run.py:3240-3243,3441-3444,3485-3491（调用了 send，但没有配置可用）；MACOS.md:436（export 的变量进不了 launchd）；grep QBREAK_WEBHOOK|qbreak-notify 于 scripts/*.sh：没有
  - 修法：钥匙串服务名 qbreak-notify 存 webhook URL（Discord / Slack / ntfy 都行），liveu.sh 启动时读进进程环境、不回显；崩溃路径与锁失败也走 notify.send；加 liveu.sh notify-test；gate 加「推送通道已设置」一项。用户自己建频道，在终端用 security add-generic-password -w 存。
- **OPS-02 没有死人开关：Mac 没跑就没人知道**（上实盘前；核对属实；做的人 both；工作量 M）
  - 说明：属实，而且比原文说的更要紧：现行 live-u 没有挂在券商侧的逆指値兜底（live_unified.py 里没有 protective / place_protective_stop 的调用），离场全靠 Mac 每天早上运行。Mac 关机、停在登录窗口或合盖几天，离场单就一直不下，而且没有任何外部提醒。立花模式下，登录任务因为模拟操盘的 plist 不在了，直接判定为「没装模拟操盘」，打开的是旧的 page_paper.html，不会提醒今天的立花运行没完成（mac_login.py:40-43,60）。过时提示只出现在页面里（desktop_page.py:235-241）。
  - 证据：qbreak/mac_login.py:40-43,60；qbreak/desktop_page.py:235-241；grep protective|place_protective_stop 于 qbreak/live_unified.py：没有；grep heartbeat|healthcheck|hc-ping|dead.man：只有旧守护进程 daemon.py:189；HANDOFF.md:1235-1237
  - 修法：每个交易日早上的运行结束后（被挡下没下单也算），向外部死人开关服务（healthchecks 一类，URL 存钥匙串）ping 一次；在服务端设「交易日 09:30 JST 前没收到 → 邮件 / 推送到手机」。立花模式的登录任务发现今天早上没完成 → 本机通知并打开 page_tachibana。立花每次 API 登录发的ログインメール可以当人工的旁证。要让云端例行任务参与，改例行任务需用户确认。
- **OPS-03 实盘账本只有一份，没有备份也没有恢复办法**（重要；部分属实；做的人 claude_code；工作量 S）
  - 说明：已有部分防护：写入是原子的（utils.py:19-29，先写临时文件再 os.replace，但没有 fsync）；账本损坏时会改名成 .corrupt.<时刻> 保留下来并记 error（utils.py:36-47）；账本没了、但券商那边有持仓时，持仓核对会挡住下单（live_unified.py:1093-1118），出错时偏向安全。真正缺的是：没有按日期的账本快照和恢复命令，也没有「按券商持仓重建账本」的办法（止损线、买入日、手动指令、入出金都只在这一份账本里）。会损失的是「几天不能自动离场」，不会下错单，所以降为 important。
  - 证据：qbreak/utils.py:19-29,36-47；qbreak/live_unified.py:101-104,145-153,1093-1118；grep backup|snapshot|.bak|copy2 于 live_unified.py / manual_orders.py / utils.py / run.py：没有
  - 修法：每天早上运行结束（或每次 save 之前）把账本复制到 state/backup/日期时刻.json，保留 30〜60 份；加 liveu.sh restore-book <时刻>（只在 HALT 存在时可用）；文档写明 Time Machine 要加密（私钥 PEM 没有加密）。
- **OPS-04 换 Mac 没有步骤，还可能两台 Mac 同时下单**（重要；核对属实；做的人 both；工作量 M）
  - 说明：属实。ARM 只检查文件内容是不是 ARMED（run.py:47-52），不绑定机器；运行锁是本机的 fcntl；执行器不读注文一覧，open_orders 只在 probe 里用（run.py:3862）。has_client_id 只查本进程内存里的 _sent_ids（tachibana.py:579-580），管不到另一台 Mac 发的单。立花「再次登录会让旧的虚拟 URL 失效」（tachibana.py:14），两台 Mac 会互相踢掉会话，但每次调用都会自动重登一次（tachibana.py:424-437），所以挡不住重复下单。文档里搜不到「迁移 / 换 Mac / Time Machine」。
  - 证据：run.py:47-52；run.py:3862；qbreak/brokers/tachibana.py:14,579-580,424-437；grep 迁移|新 Mac|换 Mac|Time Machine 于 MACOS.md / HANDOFF.md / README.md：没有
  - 修法：MACOS.md 加「换 Mac」一节：先在旧 Mac 上 HALT 并卸载立花任务 → 拷数据 → 新 Mac 跑 mac_setup → gate → 用户明确说了才 ARM。ARM 文件写入本机硬件 UUID，执行器发单时对不上就当作没 ARM；早上发单前查一次注文一覧，发现账本里没有的当日单就不下单并提醒。
- **OPS-05 仕様覆盖文件的位置文档写错，也不入库**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实，而且波及面更大：MACOS.md §4 的 `python3 run.py tachibana-probe --demo --dump-spec`（MACOS.md:370）和 §1.6 第 3 步的 `python3 run.py live-u --broker tachibana --dry-run --no-clock`（MACOS.md:134）都没设 QBREAK_HOME，还用的是系统 python3（3.9）。照着做，spec 模板、probe 结果、dry-run 账本都会写进 ~/qbreak-src/var/（这些路径都没被 gitignore），而 gate 读的是 ~/.qbreak/home/out/tachibana_probe_*.json，会一直显示「还没做」。不过 gate 的 ④⑤ 是用经 liveu.sh 跑出来的结果来判定的，覆盖文件放错地方会表现为 probe 不通过，不会悄悄上线，所以降为 important（开户第一天必然会碰到）。
  - 证据：qbreak/brokers/tachibana.py:184-201（paths.home()/tachibana_spec.json）；qbreak/paths.py:20-24（没设 QBREAK_HOME 时 = 仓库 var/）；scripts/liveu.sh:38,44-51（sync_inputs 没有 tachibana_spec.json）；MACOS.md:133-134,370,373；HANDOFF.md:1173；git check-ignore var/tachibana_spec.json var/state/live_unified_tachibana_dryrun.json：都没被忽略；qbreak/live_gate.py:124,135（读 out_dir 下的 probe 结果）
  - 修法：把 tachibana_spec.json 放进仓库 var/（在 ~/qbreak-dev 里改、全部测试通过再推），并加进 sync_inputs；或者文档改成 ~/.qbreak/home/tachibana_spec.json，同时在 gate 和页面上显示「仕様覆盖生效中：覆盖了哪些键」。
- **OPS-06 上实盘后，面板 / 手机 / 命令的默认账本还是已经停掉的模拟账户**（重要；部分属实；做的人 claude_code；工作量 S）
  - 说明：面板顶部有账本标签，可以切到「立花（本番）」（panel.py:1383，books() 在 :92-94），模拟账本上有「模拟账户：…」的提示（panel.py:1389-1390），所以不是没法切换。确实有的问题：默认是 paper（panel.py:2015-2017，手机也一样，:2179）；manual 默认 --broker paper（run.py:4193），而 flow 默认是 tachibana（liveu.sh:168），两边的默认值不一致；立花模式下登录任务打开的是停住的 page_paper.html（mac_login.py:60）；停掉的模拟账本没有「已停，不再推进」的标识。
  - 证据：qbreak/panel.py:92-94,1383,1389-1390,2015-2017,2179；run.py:4193；scripts/liveu.sh:168；qbreak/mac_login.py:40-43,60；scripts/install_launchd_live_u.sh:94-102
  - 修法：按装的是哪种定时任务（com.qbreak.liveu.morning 在不在），或 ~/.qbreak/home 下一个 BOOK 文件，决定默认账本：面板首页、manual 的默认值、登录时打开的页面都跟着切；模拟账本标上「已停，不再推进」。CLAUDE.md 里「没说账本就用模拟账户」这条要改的话，需用户同意。
- **OPS-07 立花 API 版本提醒一过发布日就消失**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实。页面通知和登录日志都只在 next_release ≥ 今天时出现（run.py:3451-3454；tachibana.py:411-412）；next_release 不写进账本，只在 probe 结果里记一次（run.py:3878）；也没有任何东西去看官方的 API 公告页。从发布到旧版停用（v4r9 那次约 1 个月，README.md:499）正是最需要动手的时候，反而不提醒。版本号是 TachibanaSpec 的默认值（tachibana.py:64-65），可以用 spec 文件覆盖。
  - 证据：run.py:3451-3454,3878；qbreak/brokers/tachibana.py:64-65,408-412；README.md:499；grep e-shiten.jp/api 于 qbreak/*.py（不含 brokers）/ run.py：只在注释里
  - 修法：账本记下看到过的下一版发布日，直到 base_live 的版本号升到新版才消掉提醒，过了发布日改成 ★；news 任务每周取一次 https://www.e-shiten.jp/api/（公开页面，只读），发现新版本或废止日就在仪表盘和通知里提示。
- **OPS-08 系统更新、重启、Python 环境坏掉时没有防护**（重要；核对属实；做的人 both；工作量 S）
  - 说明：三点都属实。① 搜不到关于系统更新 / FileVault / 自动登录的说明。② 早上那次运行 git pull 失败时，读的是工作区里旧的 var/HALT_REMOTE（liveu.sh:236），提示文字只提到「旧代码」（liveu.sh:218），07:40 的寄付单可能在收不到远程停止的情况下照样发出；要到 09:05 的开盘阶段才 fetch @{u}（liveu.sh:237-242）。③ venv 不能用时会退回系统 python3（liveu.sh:40）；最终会以「运行没有完成」的形式报出来（liveu.sh:263-268），并非完全静默，但看不出原因是 venv；立花模式下 mac_setup 只在 venv 可执行时才 pip（mac_setup.sh:40-42），不会重建。
  - 证据：scripts/liveu.sh:40,213-219,236-242,263-268；scripts/mac_setup.sh:36-42；grep FileVault|自动登录|自动更新|softwareupdate 于 *.md / scripts：没有
  - 修法：liveu.sh run 时 venv 不能用就直接报「虚拟环境坏了 → 运行 mac_setup.sh」，不退回系统 Python；mac_setup 在立花模式下也检查、必要时重建 venv；pull 失败时照开盘阶段的做法 git fetch + show @{u}:var/HALT_REMOTE，fetch 也失败就在提醒里写明「远程停止收不到」；MACOS.md 加「系统更新」一节（升级后跑一次 mac_setup + gate）。系统设置由用户自己改。
- **OPS-09 没有定期自检；gate 只在有人问时才跑，查得也不全**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实。gate 只查本番两项钥匙串、私钥、cryptography、定时任务、pmset（live_gate.py:139-176）；probe 的结果不看日期（:136-138）；不查时钟偏差、时区、磁盘、Tailscale。时区只在安装时提醒一次（install_launchd_live_u.sh:54-55）。执行器的时间判断用 JST（check_clock，live_unified.py:281-291），但 launchd 按本地时间触发：时区一变，07:40 的任务可能在 JST 前一天夜里运行，用旧的判断层下单。登录失败的提示没提时钟（tachibana.py:387-389）。doctor 还在查旧守护进程（run.py:3959,3968）。
  - 证据：qbreak/live_gate.py:28-31,133-138,139-176；scripts/install_launchd_live_u.sh:54-55；qbreak/live_unified.py:281-291；qbreak/brokers/tachibana.py:15,387-389；run.py:3959,3968；grep sntp|ntp|statvfs|disk_usage|时钟 于 qbreak / scripts / run.py：没有
  - 修法：加 liveu.sh health（只读）：上面各项 + 定时任务已加载 + venv + pmset + 最近一次早上的运行是否成功；装一个每周一 07:00 的 LaunchAgent 跑它，有 ★ 就通过 OPS-01 的通道推送；liveu.sh run 开头发现时区不是 +0900 就报警、这次不下单；登录失败提示加上「Mac 时钟有没有自动对时」。
- **OPS-10 手机 / 面板看不到执行器今天做了什么**（重要；核对属实；做的人 claude_code；工作量 M）
  - 说明：属实。面板只显示 HALT、ARM、核心停买信号的警告（panel.py:1385-1394）、持仓 / ETF / 建议的股票、手动指令（:1542）。sm 里的 blocked、执行器的 orders（SENT / REJECTED / ERROR）、events、notices、compare 都没有渲染；book['orders'] 只用来看核心 ETF（:1374-1376）；完整页面只是本机文件（:1559），手机看不到。
  - 证据：qbreak/panel.py:1374-1376,1385-1394,1542,1559；grep blocked|notices|needs_user|REJECTED 于 qbreak/panel.py：没有渲染
  - 修法：面板账本卡片下面加「今天的执行器」一节（复用 summary / daily_text 里的 blocked、orders 状态、needs_user、error 事件、notices），手机端同样显示；状态不明的单标红，并写「去立花网站核对」。
- **OPS-11 状态不明的单：提示里的登记命令不能照抄**（方便；部分属实；做的人 claude_code；工作量 S）
  - 说明：MACOS.md:119 和 HANDOFF.md:1179 的示例其实已经带了 --broker tachibana；`bash scripts/liveu.sh --broker tachibana --resolve <cid> --filled N --px P` 经 liveu.sh 末尾的通用分支（:282-283）已经能用，而且会设好 QBREAK_HOME 并拿运行锁。真正缺的是：执行器和 gate 提示里的命令没有 --broker tachibana（live_unified.py:600,1177；live_gate.py:119），照抄会去模拟账本里找，报 KeyError，好在没有害处；resolve_order 不检查这一单原来是不是状态不明（live_unified.py:1240-1252）。降为 convenience。
  - 证据：qbreak/live_unified.py:600,1177,1240-1252；qbreak/live_gate.py:119；MACOS.md:119；HANDOFF.md:1179（已带 --broker tachibana）；scripts/liveu.sh:282-283（通用分支）；run.py:3236,3335（resolve 前先拿锁）
  - 修法：加 bash scripts/liveu.sh resolve <cid> --filled N --px P（默认用已安装的账本），所有提示都改成这条；resolve 只接受状态是 SENDING / ERROR 的单。Claude 仍然只在用户这次对话里明确说了才执行。
- **OPS-12 第二暗証 / 密钥没有更换步骤；暗証错了还会连着发单**（重要；部分属实；做的人 claude_code；工作量 S）
  - 说明：「第二暗証缺失要等被拒才发现」不成立：适配器在发出之前就会因为 second_password 为空把单挡下（BLOCKED，不发出；tachibana.py:620-623）；gate ⑥ 会检查钥匙串里有没有 qbreak-tachibana-2nd（live_gate.py:28-29,139-149）。成立的部分：被拒（REJECTED）之后，执行器同一次运行还会接着发后面的单，不区分认证类的拒单（live_unified.py:344-372；tachibana.py:660-665）；暗証连错会不会锁账户，要对照官方说明；没有换密钥 / 改暗証的步骤（MACOS.md §3 只写了第一次放置，:338-361）。
  - 证据：qbreak/brokers/tachibana.py:236-258,620-623,660-665；qbreak/live_gate.py:28-29,139-149；qbreak/live_unified.py:344-372；MACOS.md:338-361,495
  - 修法：进入下单阶段前第二暗証为空 → block「钥匙串里没有第二暗証」；拒单信息里有暗証 / 認証一类的字样 → 这次运行后面的单全部停下并通知；MACOS.md §3 加「换密钥 / 改暗証」步骤（值只让用户在终端里自己输入）。
- **OPS-13 手机盘中下单要 Mac 醒着，但没有「交易时段保持清醒」的选项**（方便；核对属实；做的人 both；工作量 S）
  - 说明：属实。立花模式下 caffeinate 只到 09:25（liveu.sh:270-279），HANDOFF.md:191 已把这条写作限制；之后盘中用手机下手动指令时，Mac 可能已经睡着。
  - 证据：scripts/liveu.sh:270-279；HANDOFF.md:191；grep AWAKE|防止自动睡眠：没有
  - 修法：加一个可选开关（例如 ~/.qbreak/home/AWAKE_MARKET）：交易日、接着电源时，09:00〜15:30 用 caffeinate -i 保持清醒；或者在文档里写「系统设置 → 电池 → 电源适配器：显示器关闭时防止自动睡眠」。
- **OPS-14 开户当天没有一条龙的引导命令，清单也缺几项**（方便；部分属实；做的人 claude_code；工作量 M）
  - 说明：「ログインメール」已经写进文档（MACOS.md:332；README.md:500；tachibana.py:12），不算缺。成立的部分：没有 onboard 一类逐步引导的命令（liveu.sh 子命令里没有）；gate 不查デモ凭证；§2 清单里没有配当金受領方式（只在 nisa_tax_study.py:13 和 HANDOFF 〔72〕的 NISA 上下文里出现）；ETF 第一次买入要不要先确认目論見書，没有核对过（如果需要而没确认，核心 ETF 的 API 买单可能被拒，待开户后确认）。
  - 证据：MACOS.md:319-336（§2；ログインメール在 :332）；README.md:500；scripts/liveu.sh 1-34 行的子命令列表：没有 onboard；grep 比例配分|配当金受領|目論見書：只有 nisa_tax_study.py:13、HANDOFF.md:898,906
  - 修法：加 liveu.sh onboard：逐步检查（钥匙串项有没有、私钥权限、デモ / 本番 probe 的结果和日期、dry-run 做过没有、定时任务、pmset、gate），只打印下一步，可以重复跑；不读、不显示任何密钥，不建 ARM。§2 清单补上配当金受領方式、ETF 目論見書确认、ログインメール。
- **OPS-15 日志和缓存不轮换，也不查磁盘**（方便；核对属实；做的人 claude_code；工作量 S）
  - 说明：属实。只有 qbreak.log 会轮换（utils.py:58-62），launchd 的 .out / .err 只追加；J-Quants 每天写 gz、不清理（jq_live.py:58-64）；没有磁盘检查。增长很慢，维持 convenience。
  - 证据：qbreak/utils.py:58-63；qbreak/jq_live.py:58-64；scripts/install_launchd_news.sh:63-64；grep newsyslog|statvfs|disk_usage|prune：没有
  - 修法：在每周自检或登录任务里，把超过 5 MB 的 .out / .err 截到只剩最后 N 行（或者装一份 newsyslog 配置）；J-Quants 的 live 缓存只保留 N 天；health 检查磁盘不足 5 GB 时报警。
- **OPS-16 旧方案的文档和 doctor 输出会误导**（重要；部分属实；做的人 claude_code；工作量 S）
  - 说明：§7 清单开头已经注明哪些是「旧的分市场方案」（MACOS.md:426-427）。但 §7 正文里的 ARM / HALT 代码块（MACOS.md:440-449：echo ARMED > var/ARM、echo "手工停止" > var/HALT），以及 §10 FAQ（:493 daemon.err、:497 var/ARM、:498 echo x > var/HALT）没有标注。Mac 上的执行器只看 ~/.qbreak/home/HALT（paths.py:57-59 + liveu.sh:38），照文档写 var/HALT 停不下实盘，这是安全隐患，所以升为 important。§8 写「逆指値仍挂在券商侧」，对现行 live-u 不成立（MACOS.md:461-467）；§5 的唤醒时间是 08:40（:399），和现行的 07:30 冲突（这一点 gate 会查出来）。doctor 会把人引去装旧守护进程（run.py:3968）。
  - 证据：MACOS.md:426-427,440-449,461-467,493-498；qbreak/paths.py:57-59；scripts/liveu.sh:38；run.py:3959,3968
  - 修法：§7 / §10 改成 live-u 的版本，或整节标「旧方案，勿用」；doctor 改成查 com.qbreak.liveu.* / panel / news 有没有加载，ARM 按 ~/.qbreak/home 显示。
- **OPS-17 每年的账户 / 税务事务没有清单**（方便；核对属实；做的人 user_action；工作量 S）
  - 说明：属实。CHECK_TIMELINE「六 每年」只有研究、日历和税率常数（:104-113），没有年間取引報告書 / 申告结转一类的账户事务；相关内容只出现在 nisa_tax_study.py 的注释里。只是提醒类，由用户自己做。
  - 证据：CHECK_TIMELINE.md:104-113；grep 年間取引報告書|確定申告|繰越 于 *.md：没有（只在 scripts/nisa_tax_study.py:11,44）
  - 修法：CHECK_TIMELINE「每年」加：1 月下载年間取引報告書；亏损的年份考虑申告结转；确认税率和口座区分（gate 已显示课税区分）。只作提醒，不给税务建议。
### 用户侧便利性：操作面板（panel.py / panel_phone.py）、Mac 账本页（desktop_page.py → page_<账本>.html）、holding_view / core_exit / suggest、云端日报 report_unified.py，以及它们在 broker=tachibana 模式下的表现

- **UX-01 面板（尤其手机）看不到执行器这次有没有跑成、有没有被挡、有没有状态不明的单**（上实盘前；核对属实；做的人 claude_code；工作量 M）
  - 说明：成立。面板只读账本与汇总（panel.py:97-99），render 里不用 sm['blocked'] / events / now_at（grep 只命中 CSS 的 pointer-events）；警告只有 HALT / 没有 ARM / 模拟账户 / ETF 买入信号（panel.py:1386-1393）。执行器出错路径（run.py:3435-3445）只调 page() 写 Mac 本地页并通知，汇总文件不更新，所以手机上看到的是上一次的数据，也没有过时提示。补充一点：「手动指令」那几行会显示每条指令的 msg（panel.py:1529-1538），盘中状态不明的会写「下单结果不明，请在立花的注文一覧确认」（live_unified.py:655-656）。看不到的是规则单、blocked 和运行失败。严重度维持 before_live（理由：上线后人不在 Mac 前时，这是唯一的信息入口）。
  - 证据：qbreak/panel.py:97-99；qbreak/panel.py:1386-1393；grep 'blocked|events|now_at' qbreak/panel.py：只有 CSS 里的 pointer-events；run.py:3435-3445（出错只调 page() 和通知）；qbreak/desktop_page.py:86-90,236-242（过时提示 / 标红只在 Mac 本地页）
  - 修法：执行器每条路径（含出错）在 out/ 写一个小的 run_status_<账本>.json（时间、阶段 morning/open/now、结果 ok/blocked/failed、原因、状态不明的单的 cid 与代码、最近 5 条 warn/error）；面板顶部卡片读它：最近一次运行时间 + 结果徽章，blocked/failed/状态不明 用红色并写「要做什么」（例：在立花 App 的注文一覧确认后在 Mac 对话里说…），超过应有更新时间显示过时提示（复用 desktop_page 的 _STALE_JS 逻辑）。只展示，不改交易。
- **UX-02 通知的标题 / 一行摘要不提示「被拒 / 状态不明的单」与 error 事件**（上实盘前；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立。bad 只看 blocked / 与云端不一致 / notices / ETF 信号（run.py:3486-3488）；daily_text 的 short 不统计 ERROR / REJECTED / BLOCKED 的单，也不统计 error 事件（live_unified.py:1418-1444）；_now_report 的级别固定是 info（run.py:3577）。补充：ARM 内容不对时，适配器把单挡成 BLOCKED（tachibana.py:535-537），这不是 ux.block，所以 sm['blocked'] 为空，通知也不会写「★ 没下单」。正文里会逐笔列出状态，但 Mac 通知只显示 short 一行，而 webhook 实际又没接上（见 UX-03）。
  - 证据：run.py:3486-3488；qbreak/live_unified.py:1417-1444；run.py:3575-3577；qbreak/live_unified.py:360-367（ERROR 记为 error 事件，但不进 short）；qbreak/brokers/tachibana.py:535-537（未 ARM → BLOCKED，不经过 ux.block）
  - 修法：daily_text / _now_report 的 short 加「★ 状态不明的单 N 笔：去立花注文一覧确认」「★ 被拒 N 笔」「★ 错误 N 条」，并把这些情况并入 bad（warn）。纯展示与通知，S 级改动 + 测试。
- **UX-03 手机推送实际上没接通：webhook 只读环境变量，定时任务拿不到**（上实盘前；核对属实；做的人 both；工作量 M）
  - 说明：成立。notify 只读 os.environ 里的 QBREAK_WEBHOOK / QBREAK_SMTP（notify.py:22-37）；live / panel 的 plist 的 EnvironmentVariables 里没有它们（install_launchd_live_u.sh:72-79、install_launchd_panel.sh:52-59）；liveu.sh 只从钥匙串读 qbreak-jquants；gate 和 mac_setup 也不检查通知通道（grep notify|webhook 没有结果）。LINE Notify 字样已经过时，而且代码发的是 JSON，本来也不兼容 LINE Notify。修法更简单：适配器里已经有 _keychain()（tachibana.py:205），notify.py 照同样的方式从钥匙串读（服务名例如 qbreak-webhook）即可，不用改 plist。
  - 证据：qbreak/notify.py:5,22-37；scripts/install_launchd_live_u.sh:72-79；scripts/install_launchd_panel.sh:52-59；scripts/liveu.sh jq 分支（钥匙串只读 qbreak-jquants）；grep 'notify|webhook' qbreak/live_gate.py scripts/mac_setup.sh：没有；qbreak/brokers/tachibana.py:205-215（现成的钥匙串读取函数）
  - 修法：liveu.sh 的 run / news 分支像 jq 一样从钥匙串（服务名如 qbreak-webhook）读进该进程环境、绝不回显；mac_setup.sh 只检查「是否已设置」。用户自己选通道（Discord webhook / ntfy 私有主题 / Pushover 等）并用 security add-generic-password 存入；推送内容只放汇总（不含账户号）。之后加一个 liveu.sh notify-test。删掉 LINE Notify 字样。
- **UX-04 盘中执行器失败时面板每分钟重叫一次：通知轰炸 + 反复登录立花**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：机制成立：Trigger 没有失败退避（panel.py:1692-1727，NOW_GAP_S=60，loop 每 30 秒检查一次）；ingest 只改内存（manual_orders.py:720-770）；now_phase 在状态不明时 raise 在 save 之前（live_unified.py:596-599），b.positions() 也不在 try 里（live_unified.py:630）。所以未读指令一直是未读，now_due 一直为真，每分钟一次 liveu.sh run --phase now，每次都 mac_notify + webhook「执行器停下」（run.py:3435-3445）。登录是幂等请求，每次最多重试 3 次（tachibana.py:367,384）。严重度降为 important：不会发错单；登录只用认证 ID + 私钥，没有密码，所以看不到「连续失败锁账户」的证据，主要是通知轰炸和频繁访问 API。
  - 证据：qbreak/panel.py:69,1692-1727,1743-1748；qbreak/manual_orders.py:592-628,720-770；qbreak/live_unified.py:556-558,596-599,630；run.py:3435-3445；qbreak/brokers/tachibana.py:367,378-386
  - 修法：Trigger 记录每个账本最近一次子进程的退出码；非 0 时指数退避（如 1→5→15→30 分钟，盘中最多 N 次）并在面板显示「上次失败：原因，下次重试时间」；或执行器在 now_phase 出错前先把 ingest 的结果与 tried 时间戳 save。同一原因的失败通知同日只发一次。
- **UX-05 已经发到交易所的单撤不了（面板 / 执行器都不调立花的取消）**（重要；核对属实；做的人 both；工作量 L）
  - 说明：成立。grep cancel_order 只在 run.py:3806（probe --order-test）和适配器定义里出现；执行器、面板和 HALT 都不撤已发出的单。面板对已发出的单只记 cancel_req（manual_orders.py:758-760）；盘中的单直接拒绝撤回（manual_orders.py:755-756）；对话框文字（panel.py:590,598）也写了要去立花网站 / App 上撤。
  - 证据：grep 'cancel_order|\.cancel(' qbreak run.py：只有 run.py:3806 和 tachibana.py:750-769；qbreak/manual_orders.py:752-762；qbreak/panel.py:590,598,1531-1532；HANDOFF.md:1224（已知限制：开盘后的买单不能从面板撤）
  - 修法：新增手动指令 kind=cancel_sent（单个注文）与「HALT 并撤掉今天未成交的单」：由执行器在 RunLock 下执行（--phase now 或独立 --phase cancel），对 SENT/PARTIAL 且有 broker_id 的单调 cancel_order，再用 order_status 记下部分成交，账本标记 CANCELLED，第二天对账照常。先在デモ环境验证（门槛 ④ 已有撤单检查），全部测试通过再上。不改规则：撤单后的仓位差由第二天的规则决策照常处理。
- **UX-06 实盘当天看不到成交结果：成交要到第二天 07:40 才查**（重要；核对属实；做的人 claude_code；工作量 M）
  - 说明：成立。立花的成交只在 run_bar 的 _collect_fills 里用 order_status 查（live_unified.py:977-995,1183）；open_phase 不查早上的单（live_unified.py:519-541）；定时只有 07:40 / 08:35 / 09:05 / 09:20（install_launchd_live_u.sh:101-107）。补充：盘中下的单在 _confirm 里会轮询 confirm_timeout_s 秒（tachibana.py:673-690），之后就不再查了。所以寄付单和挂着没成交的盘中限价单，当天都不知道结果。
  - 证据：qbreak/live_unified.py:977-995,1171-1183；qbreak/live_unified.py:519-541；scripts/install_launchd_live_u.sh:101-107；qbreak/brokers/tachibana.py:673-690
  - 修法：加一个只读的收盘后运行（例 15:45，LaunchAgent com.qbreak.liveu.close）：在 RunLock 下对今天的单逐个 order_status，把「成交 N 股 @ 均价 / 未成交 / 失効」写到汇总与 UX-01 的状态文件，并发一条「今天的成交」通知；不改模型状态（正式对账仍在第二天早上），不发单。15:30〜16:30 值洗い期间的 API 行为先在デモ确认。
- **UX-07 没有「立花那边实际是什么」的视图（保有 / 余力 / 注文一覧 vs 账本）**（重要；核对属实；做的人 claude_code；工作量 M）
  - 说明：成立。check_broker 读了 positions() 和 cash()，只拿来比较、记 cash_drift，没有保存券商的快照（live_unified.py:1093-1131）；summary 里没有券商侧的数字（live_unified.py:1223-1236）；probe 只数注文件数（run.py:3862）；--status 不连券商。面板显示的都是账本（模型）的数字。
  - 证据：qbreak/live_unified.py:1093-1131；qbreak/live_unified.py:1223-1236；run.py:3862；run.py:3340-3345（--status 只读账本）
  - 修法：每次运行（含 UX-06 的收盘后运行）把券商快照写进 out/broker_snapshot_<账本>.json：各票保有 / 売付可能数量 / 概算簿価、買付可能額、今天的注文一覧（代码、方向、数量、状态、約定数量），不含账户号与密钥；面板实盘标签加「立花那边」卡片，与账本逐行比较、差异标红，并注明快照时间（面板本身仍不连立花）。另给 liveu.sh broker（只读、RunLock 下）随时刷新一次。
- **UX-08 现金差不拆分：每天 warn 噪音，税 / 分红 / 免手续费期会误报「请登记入出金」**（方便；部分属实；做的人 claude_code；工作量 M）
  - 说明：「现金差 ≥ ¥1 就记 warn」成立（live_unified.py:1121-1124）；实盘不记分红（run.py:3429）、新开户 60 个营业日免手续费没计入（report_unified.py:400）也成立，所以 warn 噪音会出现在 Mac 页「最近的提醒」（desktop_page.py:236-240）。但「源泉税被当成没登记的入出金」夸大了：提醒门槛是 max(¥50,000, 权益 2%)（live_unified.py:1144-1146），按现在约 ¥100 万的规模，单笔税和分红基本到不了。降为 convenience。
  - 证据：qbreak/live_unified.py:1119-1131,1144-1152；run.py:3429；qbreak/report_unified.py:400；qbreak/desktop_page.py:236-240
  - 修法：把现金差按可解释项拆分并分级：①已登记入出金 ②当天卖出盈利 × 20.315% 的源泉税估算 ③权利确定日持有 × 每股分红（公司行为数据）④手续费差；能解释的记 info 并在页面列「税 / 分红 / 手续费」明细，解释不了的才 warn。只影响显示与提醒，不影响下单。
- **UX-09 没有已实现损益 / 年内税额视图；税后估算忽略年内损益通算；看不到课税区分**（方便；核对属实；做的人 both；工作量 M）
  - 说明：事实成立：state.trades 里有 pnl_jpy（unified.py:348-350），但 desktop_page / panel 都不显示；税后估算固定按 20.315%（manual_orders.py:1124,1286），已经标明是估算；positions() 按课税区分合并（tachibana.py:493-509），下单用账户的默认区分。这些都是看数和记账上的不便，不影响下单正确性，降为 convenience。（拿着 NISA 和特定两个区分的同一只票时卖单可能被拒，这属于执行器那一块，而且只在采用 NISA〔72〕之后才会出现。）
  - 证据：qbreak/unified.py:119,348-350；grep 'trades|pnl' qbreak/desktop_page.py qbreak/panel.py：只有 JS 里的预计收益；qbreak/manual_orders.py:1124,1286；qbreak/brokers/tachibana.py:493-509,639
  - 修法：账本页 + 面板加「已实现损益」卡片：最近 N 笔（买卖日、股数、价、手续费、损益）、年初至今合计、按特定口座规则估算的已扣 / 应扣税（只是估算，以立花年間取引報告書为准）；卖出确认框的税后估算按年内累计损益调整。持仓行显示课税区分（来自快照 UX-07）。NISA 下单另按〔72〕由用户决定。
- **UX-10 手机面板没有损益摘要、今天的单、最近成交、当天日志**（方便；核对属实；做的人 claude_code；工作量 M）
  - 说明：成立。面板顶部只有总权益和现金（panel.py:1396-1398）；当日 / 累计损益、这次的单、最近成交、日志只在 Mac 本地的账本页（desktop_page.py:99-123,177-209,227-233）；手机端口只开放 / /pair /api/chart /api/quotes（panel.py:2157）。
  - 证据：qbreak/panel.py:1395-1401；qbreak/desktop_page.py:99-123,177-233；qbreak/panel.py:2157
  - 修法：面板加只读卡片：当日 / 累计损益（复用 desktop_page 的 invested_jpy / flows_in_change）、迷你权益曲线、今天的单（规则 + 手动，状态中文化）、最近 10 笔成交、日志最新一节；可折叠，手机优先。数据只在 Mac 本机，不入库。
- **UX-11 实盘账本缺少醒目的「真钱」标识，面板默认打开模拟账户**（重要；部分属实；做的人 claude_code；工作量 S）
  - 说明：没有 ?book 时默认打开模拟账户（panel.py:2015-2017），确认框只对模拟账户附说明（panel.py:342,1102），这两点成立。但面板也有识别：顶部标签和账本卡片标题都写「立花（本番）」（panel.py:65,1383,1395），立花没解锁时还有红色警告。缺的是醒目的「真钱」标识，以及确认框里写账本名。另外，Mac 账本页对 tachibana_demo / dryrun 也写「qbreak 立花实盘」（desktop_page.py:80,283-285），会把デモ当成实盘。维持 important。
  - 证据：qbreak/panel.py:2015-2017；qbreak/panel.py:342,1102；qbreak/panel.py:65,1383,1395；qbreak/desktop_page.py:80,283-285
  - 修法：立花本番标签用不同的强调色顶栏 +「真钱 · 立花本番」徽章；所有确认框标题前加账本名，本番的确认按钮写「在立花下单」；ARM 已解锁时默认打开立花标签（或记住上次的标签，localStorage 失败也能用）。
- **UX-12 ARM 判定不一致：面板只看文件在不在，适配器要求内容是 ARMED**（重要；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立。面板用的是 (home/ARM).exists()（panel.py:1361,1388），manual 命令也一样（run.py:3706）；适配器、run._armed、live_gate 都要求文件内容是 ARMED，或设了 QBREAK_ARM 环境变量（tachibana.py:520-526、run.py:47-52、live_gate.py:180-181）。ARM 内容不对时，面板不警告，适配器把每一笔挡成 BLOCKED（规则卖单也一样），而且按 UX-02，通知不会标「没下单」。
  - 证据：qbreak/panel.py:1361,1388-1389；run.py:3706；qbreak/brokers/tachibana.py:520-526,535-537；run.py:47-52；qbreak/live_gate.py:180-181
  - 修法：抽一个 paths.armed() 共用（与适配器同一判断），面板 / manual / gate 都用它；面板显示三态：已解锁 / 未解锁 / ARM 文件存在但内容不对（单会被挡）。只读判断，不建、不删 ARM。
- **UX-13 交易时间里 Mac 睡着 → 手机面板打不开、盘中手动单下不了**（重要；核对属实；做的人 both；工作量 S）
  - 说明：成立，HANDOFF 里已经列为限制：caffeinate 只保持到 09:25（liveu.sh 末尾的 hold 计算）；面板的 LaunchAgent 不防睡眠（install_launchd_panel.sh:43-49 直接运行 liveu.sh panel）；手机超时会提示「Mac 可能在睡眠」（panel.py:299-301）。
  - 证据：HANDOFF.md:191；scripts/liveu.sh run 分支末尾（caffeinate -i -t 到 09:25）；scripts/install_launchd_panel.sh:43-49；qbreak/panel.py:299-301
  - 修法：可选：立花本番装好后，加一个交易日 09:00〜15:30 的 caffeinate -i -s LaunchAgent（只在接电源时），或在 gate / 面板的「手机」卡片提示设置；耗电与是否合盖由用户决定。
- **UX-14 入出金只能在命令行登记，面板没有入口**（方便；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立。面板和 manual_orders 里都没有 flow / 入金 / 出金（grep 只命中 CSS 的 overflow）；入出金只能用 liveu.sh flow 登记（run.py:3249-3258）。
  - 证据：grep 'flow|入金|出金' qbreak/panel.py qbreak/manual_orders.py：没有业务代码；run.py:3249-3258；qbreak/live_unified.py:1150-1152
  - 修法：面板实盘标签加「登记入金 / 出金」表单（金额、日期、备注），走与 /api/request 相同的令牌 / CSRF / 限流，写一条指令由执行器在 RunLock 下调 register_flow（不直接改账本）；显示已登记、待到账的入出金。只影响收益显示，不下单。
- **UX-15 上线门槛与路线图进度不在面板上；dry-run 账本面板看不到**（方便；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立。面板不引用 live_gate；BOOKS 里没有 tachibana_dryrun（panel.py:65），books() 只列 BOOKS 里的标签（panel.py:92-94）；dry-run 用单独一份账本（run.py:3217-3221）。
  - 证据：grep 'live_gate|gate' qbreak/panel.py：只有手机路径密钥的 split_gate；qbreak/panel.py:65,92-94；run.py:3217-3221
  - 修法：面板加只读「上线准备」卡片：调用 live_gate 的检查函数（只读、不打印密钥）显示 ✓/✗ 与下一步一句话；BOOKS 加 tachibana_dryrun（只读显示，或该账本禁用写按钮）。
- **UX-16 盘中写了指令后面板不自动更新结果**（方便；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立。提交后 2.2 秒 reload 一次（panel.py:306）；页面没有定时刷新，只有切回前台时刷新现价（panel.py:1065）；也没有查询状态的 GET 接口（panel.py:2040-2056,2157）。
  - 证据：qbreak/panel.py:306；qbreak/panel.py:1059-1065；qbreak/panel.py:2040-2056,2157
  - 修法：加只读 GET /api/status?book=…（手动指令状态 + UX-01 的运行状态），提交后每 10 秒轮询约 2 分钟，状态变了就更新那一行并 toast；手机端口同样要本人认证。
- **UX-17 账本页文字过时 / 未中文化：核心 ETF 写成 S&P500，单子状态是英文代码**（方便；部分属实；做的人 claude_code；工作量 S）
  - 说明：持仓表把核心 ETF 一律写成「闲置资金（S&P500）」（desktop_page.py:171），这和现在的 Q1B（1545 / 1482；var/sim.json idle_cash.mode=Q1B）不符；状态列直接显示英文代码（desktop_page.py:194）。牛熊行的「S&P500」是美股牛熊判定的标签，本身没错，只有「（1655 择时）」过时（desktop_page.py:131）。
  - 证据：qbreak/desktop_page.py:131,171,194；var/sim.json idle_cash.mode = Q1B
  - 修法：核心 ETF 名称从 holding_view / idle_cash 取；状态用中文映射（已发出 / 已成交 / 部分成交 / 开盘后再下 / 被挡 / 被拒 / 状态不明）。
- **UX-18 没有交易记录导出（CSV）**（方便；核对属实；做的人 claude_code；工作量 S）
  - 说明：成立。live_unified.py 里没有 csv；live-u 的参数里也没有导出（run.py:4151-4187）。
  - 证据：grep 'csv' qbreak/live_unified.py：没有；run.py:4151-4187（live-u 参数）
  - 修法：liveu.sh export --broker tachibana [--year 2027]：在 Mac 本地 out/ 写 trades / fills / flows / cash_drift 的 CSV（UTF-8 BOM，不入库、不含账户号）；面板可加下载链接（本机端口）。
### 账户类型 / 税 / NISA / 费用（立花实盘）

- **T1 〔72〕N2（核心 ETF 的买入放 NISA）被代码挡住，现在做不了**（方便；核对属实；做的人 both；工作量 L）
  - 说明：事实属实：所有单都用登录应答的同一个课税区分，buy/sell 和 BaseBroker 都没有 tax 参数；positions() 把各区分的行合计；core_units 只按票记；qbreak/ 里没有 NISA 额度账本；tachibana_sim 登录只回「1 特定」；MACOS.md:324 的 NISA 下单限制没写来源。但这不是新发现的缺口：HANDOFF.md:906〔72〕① 已经写明，用 N2 前要另做这套执行器工程（按单指定 sZyoutoekiKazeiC、额度 / 簿价、两个账户分别对账）。现在的方案只在特定口座交易，这一项只有用户选〔72〕① 才需要做，对上线的安全性没有影响 → 严重度降为 convenience（选了 ① 之后再升为 important，工作量 L）。
  - 证据：qbreak/brokers/tachibana.py:640 s.f_tax: self._tax or s.tax_specific；qbreak/brokers/tachibana.py:709-716 buy/sell 签名没有课税区分参数；qbreak/brokers/base.py:76-84 同样没有；qbreak/brokers/tachibana.py:493-509 positions() 按代码合计；qbreak/brokers/tachibana_sim.py:178 登录只回 tax_specific；grep -rni nisa qbreak/：只命中 tachibana.py 的注释和 policy_events.py；HANDOFF.md:906〔72〕① 已列出这套工程是前提
  - 修法：先由用户决定（这次对话里说）：今年的 NISA 开在哪家、今年额度用了多少、立花 NISA 能不能买 1545 / 1482、能用哪些下单条件、NISA 的手续费是多少、选不选株式数比例配分方式。决定之后：TachibanaSpec 加 NISA 的区分代码（「6 N成長」等）和持仓行里课税区分的字段名（按仕様書 / デモ确认）；Broker.buy/sell 加 tax 参数；持仓按（票, 区分）记；状态的 core_units 拆成特定 / NISA；新建 qbreak/nisa_quota.py 记额度和簿价，1 月恢复额度；核心买单「NISA 额度内的整单元 + 其余放特定」，卖出先卖特定（N2 的定义）；tachibana_sim 加 NISA 的持仓行和额度不足的错误码；probe / 上线门槛显示 NISA 开没开、还剩多少额度；本番先用最小单位试一次。全部测试通过再上线。
- **T2 持仓不分课税区分：同一只票在 NISA 或别的口座里有持仓时，核对会停下、卖单会从错的口座卖**（重要；部分属实；做的人 claude_code；工作量 M）
  - 说明：「核对会停下」属实：一只执行器管的票（股票池或核心 1545/1482）如果同时在立花 NISA 或一般区分里有持仓，合计股数和状态对不上，check_broker 每天都会挡住、不下单。「卖单会从错的口座卖 / 数量包含 NISA 部分 → 被拒」不成立：核对不一致时根本不会发单；卖出数量来自状态，不来自券商合计；盘中手动卖用的是 min(状态, 券商合计)，按账户默认的特定区分卖，特定区分里正好有状态里那么多股。所以后果是「卡住、不下单」，不会多卖，也不会出现持仓不明。另外 MACOS.md:141 第 6 步已经提醒「同一账户里不要人工买卖执行器管的票」，但写的是过时的「股票池 + 1655」（核心现在是 1545 + 1482）。仍然有价值：probe 按区分分开列持仓，非执行器区分的持仓只提醒、不停。严重度维持 important（取决于用户是否在立花开 NISA）。
  - 证据：qbreak/live_unified.py:1097-1117 held 用的是合计股数，不一致 → self.block；qbreak/live_unified.py:693、757-758、799 盘中卖出取 min(账本, held)；qbreak/brokers/tachibana.py:180 r_pos_sellable 在适配器里没用到（grep 只在 tachibana_sim.py:225）；MACOS.md:141 第 6 步写的是「股票池 + 1655」；var/sim.json idle_cash.mode = Q1B；qbreak/idle_cash.py:65 Q1B = 1545 + 1482
  - 修法：positions() 保留每一行的课税区分（字段名按仕様书确认），只把执行器自己用的区分算作执行器的持仓；其他区分（NISA 等）归到「执行器不管的持仓」，只提醒、不停；卖单数量 ≤ 该区分的売付可能数量；probe 按课税区分分开列持仓；加对应的测试；MACOS 第 6 步补一句「NISA 里的同一只票不要和执行器的票重叠，或先做完这项」。
- **T3 盈利卖出的代扣税被误报成「现金突然变化，请登记入出金」**（方便；部分属实；做的人 claude_code；工作量 M）
  - 说明：代扣税部分属实：模型现金不扣譲渡益税，第二天同步现金时差额 ≥ max(¥50,000, 权益 2%) 就会提示「如果是入金 / 出金请登记 flow」，提示里没有提到税；测试也只覆盖了 ¥1,234。分红部分不成立：实盘执行器在除息日不把分红记进现金（credit_dividends=paper，立花时为 False），只下调止损和峰值，分红等真正到账时经现金同步进来，所以不会出现「除息日记了、2〜3 个月后才到」的差。频率也被高估：按现在 ¥100 万的本金，一天要实现 ≥ ¥246,000 的收益（约权益 25%）才会触发提示。这条提示是条件句，而且只影响收益展示，不影响下单。严重度降为 convenience；修法照旧（提示里写「可能是譲渡益税或退税（预计 ¥X）」，同年内亏损的还付也一样）。
  - 证据：qbreak/live_unified.py:1119-1131 现金差 → 以券商为准；qbreak/live_unified.py:1145-1152 阈值 max(50,000, 2% 权益)，提示 liveu.sh flow；run.py:3429 apply_corp_actions(..., credit_dividends=paper)；qbreak/unified.py:947、974 实盘 div_net=0，不入账；tests/test_live_unified.py:239-251 只测了 −1,234；qbreak/desktop_page.py:99-104 登记的 flow 只影响展示的收益
  - 修法：执行器从账本算「特定口座今年 1 月 1 日以来的已实现损益」（个股按账本，核心按移动平均），得到预计代扣的累计值；判断现金差之前，先扣掉最近几天卖出的预计代扣或退还、预计到账的分红，剩下的才拿去比对入出金；提示改成「可能是譲渡益税（预计 ¥X），不是入出金就不用登记」；页面注明「实盘收益已扣已实现部分的税」；tachibana_sim 加可选的源泉徴収，测试加大额盈利的场景。只影响展示和提醒，不影响下单。
- **T4 卖出后余力什么时候扣税没验证过；补钱卖核心只留了 3% 余量，个股买单可能被减股或放弃**（重要；部分属实；做的人 both；工作量 S）
  - 说明：机制属实：卖核心补钱时 need = short ×1.03，按税前净额算（个股预算另外留了 1% 现金，cash_buffer_pct）；实盘 09:05 按券商余力减股，日志写「与模型相同」。但后果比原说法轻：减股或放弃之后，状态按实际成交记账，第二天核对一致，不会停也不会出现持仓不明；分开的是「实盘 vs 云端模拟盘」，不是执行器自己的账。要等立花在约定日就从余力里扣税（未验证），并且核心浮盈很大时才会发生：税占卖出额 = 20.315% × g/(1+g)，浮盈 30% → 4.7%，15% → 2.7%，超过 3% + 1% 的余量才会少买。MACOS 第 5 步的验证清单确实没有「扣税时点」。严重度维持 important，修法只做 ①②（加验证项、改日志措辞），不改仓位。
  - 证据：qbreak/unified.py:857-866 need = short × (1 + 3%)，按税前净额；qbreak/config.py:184 max_entry_gap_pct 3.0；qbreak/config.py:238 cash_buffer_pct 1.0（qbreak/unified.py:750）；qbreak/live_unified.py:488-501 按 bp 减股，日志写「与模型相同」；qbreak/live_unified.py:998-1006 实际成交写回状态；MACOS.md:139-140 第 5 步没有扣税时点
  - 修法：① MACOS 第 5 步加一条：头几次核心盈利卖出后，记下余力变化，看税是在约定日还是受渡日扣（用户看日志，或 Claude 读 --status）；② 实盘减股或放弃时，如果余力差额接近预计代扣，日志 / 通知写明「疑似譲渡益税预扣导致」，不再写「与模型相同」；③ 如果想在实盘多卖一点核心来补税，那属于改仓位，要用户同意并记进 sim_changes（这一步默认不做）。
- **T5 上线门槛对账户课税区分只当参考，遇到 NISA 区分还写「没问题」；也分不出有没有源泉徴収**（重要；部分属实；做的人 both；工作量 S）
  - 说明：属实：门槛对任何不是 1 的值都写「执行器按口座的区分发单，没问题」，值是 5 / 6（NISA）也一样；适配器不管值是什么都直接发单；probe 只记录 sZyoutoekiKazeiC，看不出源泉徴収あり / なし（grep「源泉」在 qbreak/ 里只有 manual_orders 的税率注释）。减轻的因素：MACOS.md:437 的上线清单有人工确认项「账户是特定口座，不是 NISA」；登录应答里的这个账户级区分会不会出现 5 / 6 没有确认过（NISA 通常是单独的区分）。修法便宜（适配器遇到 5 / 6 就 BLOCKED；门槛把 5 / 6 标成 ★），严重度维持 important。
  - 证据：qbreak/live_gate.py:177-179 不是 1 → 「没问题」；qbreak/brokers/tachibana.py:407、640 登录值直接用于全部单，没有校验；run.py:3857、3878 probe 只记 tax；MACOS.md:437 人工清单「账户是特定口座，不是 NISA」；grep 源泉 qbreak/*.py：只有 manual_orders.py:1124 和 config.py:191 的注释
  - 修法：适配器：_tax 不是 1（或用户明确同意过的 3）就拒绝发单（BLOCKED，写明原因）；门槛：1 → OK，3 → ★ 要用户确认（要自己申告），5 / 6 → ★ 挡住；probe 另外记录登录应答里有没有源泉徴収、配当特定、NISA 开设这几个区分（只记代码、不记金额），门槛显示「特定口座（源泉徴収あり / なし）」；加测试。
- **T6 开户清单缺「手数料コース = 個別コース」和「配当受取方式 = 株式数比例配分方式」**（重要；部分属实；做的人 both；工作量 S）
  - 说明：开户清单缺这两项属实：MACOS §2 第 1 步只写了特定口座（源泉徴収あり），没有手数料コース、配当受取方式和特定口座的配当受入。但两点理由不成立或被夸大：① 实盘模型除息日不记分红（run.py:3429），所以不存在「模型按除息日记的分红每次都对不上」；② 個別 / 定額的差别很小（README.md:507：每年 ¥12,844 对 ¥14,941），余力减股的循环看的是券商的实际余力，不会因此下错单；前 60 个营业日免费 fees.py:88 已经注明「未计入」，而且算多了手续费只会更保守。真正的后果：不选株式数比例配分方式的话，1545 / 1482 的分配金和个股分红会进银行或变成领收证，不进证券账户（实盘收益展示里少了这部分，用户还要自己去领），将来用 NISA 也不免税。不会亏钱或下错单 → 从 before_live 降为 important（开户就是下一步，补一行的成本很低）。
  - 证据：MACOS.md:323-324 开户只写了特定口座；grep 比例配分|配当受取|配当受入 *.md *.py（不含 var/）：只有 scripts/nisa_tax_study.py:13；run.py:3429 credit_dividends=paper；qbreak/unified.py:947；README.md:507 個別 ¥12,844/年 vs 定額 ¥14,941/年；qbreak/fees.py:88 已注明免费期未计入
  - 修法：MACOS §2 第 1 步加：手数料コース选個別コース；配当受取方式选株式数比例配分方式（注明会影响其他证券公司）；特定口座选「配当受入あり」。门槛的参考区加一行「手数料コース / 配当受取方式：请在立花网页确认」（API 读不到就只提醒）；fees 加一个可选的免费期截止日，估算在免费期内显示 0 円。
- **T7 没有按年看的税：今年已实现多少、已代扣多少、这笔卖出会代扣还是退税**（方便；核对属实；做的人 claude_code；工作量 M）
  - 说明：属实：没有年初以来的已实现损益和预计代扣；卖出预计「税后约」= 单笔收益 × (1 − 20.315%)，只在收益 > 0 时显示，不考虑今年前面的亏损，也不显示退税；live_unified / desktop_page / panel / report_unified 里都没有年度汇总；CHECK_TIMELINE 只检查税制有没有变。只影响展示，以立花的年間取引報告書为准。
  - 证据：qbreak/manual_orders.py:1124、1286-1287；grep 年初|YTD|ytd|今年 qbreak/desktop_page.py panel.py report_unified.py live_unified.py：没有；qbreak/report.py:139-142 全期合计（旧的云端日报）；CHECK_TIMELINE.md:113
  - 修法：复用 T3 的「今年的特定口座账本」：面板 / 手机 / 日报加一行「今年已实现 ¥X、预计已代扣 ¥Y」；卖出确认框写「按今年已实现算，这笔约代扣 ¥A / 退税 ¥B」；CHECK_TIMELINE 1 月加一条「去年特定口座净亏损 → 可以考虑确定申告结转（只提醒）」。只展示，以立花的年间取引报告书为准。
- **T8 文档对 NISA 的说法互相矛盾，NISA 下单限制没写来源**（方便；部分属实；做的人 claude_code；工作量 S）
  - 说明：MACOS.md:324「NISA 买单只能当日限价、不能逆指値」没写来源和日期，属实。「互相矛盾」说重了：〔72〕N2 只是待用户决定的提议，原文就写了要先确认、另做工程；不过 MACOS.md:324/437、REVIEW.md:178、README.md:878、excel/README_excel.md:46 都只写「不要用 NISA」，没有补「〔72〕① 是可选项」，读者可能会困惑。只改文档。
  - 证据：MACOS.md:324、437；REVIEW.md:178；README.md:878；excel/README_excel.md:46；HANDOFF.md:906〔72〕写明前提要用户确认、要另做工程
  - 修法：统一写法：「执行器默认只在特定口座（源泉徴収あり）交易；〔72〕① N2 是可选项，要先做 T1 的工程、由用户决定」；NISA 下单限制改成「待向立花确认」，或补上来源 URL 和查询日期。只改文档，不改规则。
### 补漏（completeness critic）

- **C-01 已提的几个修法和立花的使用规则冲突；面板每分钟重叫一次，可能让 API 被停用**（重要；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：立花的规定有两条：2026-03-10 的「お願い」要求 08:00〜15:30 不要频繁取现价或轮询照会，判断为过负荷可能停用 API；インターネット取引規程第18条禁止把当社提供的信息「蓄積、編集、加工」。以下修法要按这两条来做：TA-06 / UX-06 提议在 11:35、15:35 轮询 order_status，应改用 EVENT I/F 的 EC 推送，或者每天只查一次；TA-14 提议把立花现价快照写到本机给面板用，UX-07 提议写券商快照，写的话只能是本机的临时文件，带时刻、当天覆盖、绝不入库。UX-04 的情况更急：执行器失败后面板每 60 秒重新登录一次，一直到 15:25，可能被立花判成过负荷而停用 API，这个应当在上线前修好。
  - 证据：qbreak/panel.py:69 NOW_GAP_S = 60；panel.py:1692-1727 失败后不退避；qbreak/brokers/tachibana.py:549-564（銘柄マスタ每天缓存到本机，只供自己用，问题不大）；官方 https://www.e-shiten.jp/api/20260310.html（不要高频轮询，必要时停用）；官方规程 int_kitei.pdf 第18条（只能用于自己的投资，禁止蓄積・加工）
  - 修法：先做 UX-04 的失败退避，并且同一原因一天只通知一次。约定刷新改用 EVENT EC（官方推荐「EC 触发 → 再查」），或者收盘后只读查一次。所有立花行情和快照只放 ~/.qbreak/home、当天覆盖；.gitignore 和测试把它们排除在仓库外（见 C-03）。
- **C-02 盘中手动卖出在ストップ安附近会被拒：限价比制限値幅的下限还低**（重要；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：盘中卖单由执行器传 limit=None，适配器自己按「现价 −0.5%」挂指値，没有和当天的制限値幅比较。股价贴着ストップ安（或离下限不到 0.5%）时，算出的限价低于下限，交易所和券商不受理，单子变成 REJECTED。这正是最需要卖的时候（暴跌、手机上点「卖出」）。正确的做法是按下限价挂单，参加比例配分。tick.py 已经有 price_limit_jp，立花取价的结果里也有前日終値（prev_close），只是没用上。
  - 证据：qbreak/live_unified.py:352（卖单 limit=None）；qbreak/brokers/tachibana.py:605-607（ref × (1 − 0.5%)，不夹到値幅范围内）；qbreak/tick.py:117 price_limit_jp：搜了 qbreak/brokers、live_unified.py，都没有用到；qbreak/brokers/tachibana.py:453-456（quote_detail 返回 prev_close）
  - 修法：盘中指値：卖 = max(现价 ×0.995, 前日終値 − 値幅) 向上取到呼値；买 = min(…, 前日終値 + 値幅)。页面和通知写明「ストップ安：按下限挂单，可能比例配分 / 不成交」。用模拟交易所补一个ストップ安的测试；拒单错误码在デモ上核对。
- **C-03 公开仓库：立花的账本、probe 结果、ARM 一旦写进仓库的 var/，既没被 gitignore，也没有防呆**（上实盘前；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：没设 QBREAK_HOME 时，数据目录就是仓库的 var/（paths.py）。MACOS.md 有几条命令（--dry-run、--dump-spec）没带 QBREAK_HOME；在 ~/qbreak-dev 里排查时也可能直接跑 run.py。这样会在 var/ 下生成 live_unified_tachibana*.json（真实持仓、现金、单子、入出金）、tachibana_probe_*.json、tachibana_spec.json、ARM / HALT，而这些路径都没被 gitignore。仓库里已经有先例：模拟账本 var/state/live_unified_paper*.json 是被跟踪的；研究流程又是「提交推送」，一次 git add var/ 就会把真实账户的数据推到公开仓库，而且撤不回。J-Quants 有 gitignore 测试，立花没有。
  - 证据：git check-ignore（都没被忽略）：var/state/live_unified_tachibana.json、var/out/live_unified_tachibana.json、var/out/tachibana_probe_live.json、var/tachibana_spec.json、var/ARM、var/HALT；qbreak/paths.py:20-24（默认 = 仓库 var/）；git ls-files var：var/state/live_unified_paper.json 等已入库（先例）；run.py：只有 doctor（3930）提到 QBREAK_HOME，没有拦截；tests/test_jq_live.py 有 gitignore 检查；搜 tachibana 的同类测试：没有
  - 修法：.gitignore 加 var/state/live_unified_tachibana*、var/out/live_unified_tachibana*、var/out/tachibana_probe_*、var/out/page_tachibana*、var/tachibana_spec.json、var/ARM、var/HALT；--broker tachibana 和 tachibana-probe 遇到数据目录在仓库内时直接拒绝运行，提示改用 liveu.sh；补测试（参照 test_jq_live）；改正 MACOS.md 里的命令。
- **C-04 没读交付書面更新的预告（sUpdateInformWebDocument）**（重要；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：登录应答里有两个预告字段：API 发布日（sUpdateInformAPISpecFunction）和交付書面更新预定日（sUpdateInformWebDocument）。代码只读了前一个。书面一改定，用户没在 PC 上读完之前，API 登录正常但不发虚拟 URL，当天全自动停摆。2026-10-01 刚改定过一次。如果能提前几天提醒「X 日起有新书面，请先在 PC 网页读完」，就能避开这种停摆。
  - 证据：qbreak/brokers/tachibana.py:77（只有 key_next_release = sUpdateInformAPISpecFunction）；grep sUpdateInformWebDocument：qbreak/、run.py 里都没有；qbreak/brokers/tachibana.py:390-391（未読 → BrokerError）；官方 https://www.e-shiten.jp/important_info/20260911.html；参考手册 2026-09-01 的 CLMAuthLoginAck
  - 修法：TachibanaSpec 加 key_doc_update；登录时记下这个字段，写进账本和页面；预定日前 5 个交易日起每天发 warn 通知；gate 的「参考」显示它。字段名在デモ上核对。可以和 TA-08 的前一晚预检合在一起做。
- **C-05 立花那一侧的最后停止手段没写进预案；执行器跑完从不 logout**（重要；补漏，未单独核对；做的人 both；工作量 S）
  - 说明：现在的停止手段（HALT / 手机 / 云端）都要靠 Mac 的执行器自己去读。如果 Mac 失控、联系不上，或者云端 Claude、GitHub、Tailscale 出故障，就没有能立刻生效的办法。立花官方有一个现成的开关：标准 Web 的「ｅ支店・API 利用設定」改成「利用しない」或按「無効化」，会让虚拟 URL 马上失效、API 发不了单。但 MACOS / HANDOFF / CLAUDE.md 都没把它写成紧急停止手段（2026-12-12 起登录这个页面要パスキー）。另外，执行器、probe 跑完从不 logout，虚拟 URL 一直有效到 03:30。官方建议用完就登出；怀疑密钥泄露时也应该用无效化来处理。
  - 证据：grep 無効化 / 利用しない：MACOS.md、HANDOFF.md、README.md、CLAUDE.md、tachibana.py 都没有；qbreak/brokers/tachibana.py:414-422（有 logout()）；grep logout：run.py、live_unified.py 都没有调用；官方 Q&A https://www.e-shiten.jp/QA/answer14.html（仮想URL 失效条件：無効化 / 利用しない / ログアウト）
  - 修法：MACOS §8 和 HANDOFF「在 Mac 对话里怎么问」加一条「最后手段」：立花网页 → 利用設定 → 無効化（会让 API 立即失效，恢复要重新设置），注明撤单仍要在网页上做。执行器每次运行结束（finally）调用 logout；补测试，确认 logout 失败不影响结果。
- **C-06 立花 API 或 Mac 出故障的那天，没有「人工代下、事后登记」的流程**（重要；补漏，未单独核对；做的人 both；工作量 M）
  - 说明：立花官方写明 API 子系统故障时要在标准 Web 上操作。Mac 坏了、断网一整天，或者 API 故障时，今天该卖（止损 / 规则卖出）的单不会下。用户如果自己在立花网页上照着下，第二天持仓核对一定不一致，执行器整个停下：--resolve 只能登记执行器自己的单，又没有「把用户在网页上下的单当作执行器成交登记进来」的工具。结果是「不下单」和「手动下单后系统卡住」两头都不好。用户在手机上也看不到「今天本该下哪些单」。
  - 证据：MACOS.md:458（都错过 → 那天没下单）；qbreak/live_unified.py:1240-1252（resolve_order 只改执行器自己的单）；qbreak/live_unified.py:1093-1118（持仓不一致 → 全部挡住）；grep 人工代下 / adopt / 手工下单：run.py、live_unified.py、liveu.sh、MACOS.md 都没有；官方参考手册（API 子系统故障时在标准 Web 上查询、订正、取消）
  - 修法：① 每次运行把「今天的规则单」（票、方向、股数、条件、限价）写进面板和手机可见的状态（复用 UX-01）；② 加 liveu.sh adopt --broker tachibana <票> <方向> <股数> <均价> <日期>：先备份账本，把用户在网页上实际成交的单按执行器的成交登记（止损线按规则重算），要用户在对话里明确说才执行；③ MACOS §8 写「故障日照单在网页上下 → 第二天 adopt」的步骤。
- **C-07 没有上线当天的值守清单，也没有「退出实盘 / 回到模拟」的预案**（重要；补漏，未单独核对；做的人 both；工作量 S）
  - 说明：路线图写到「第一天：从最新收盘的决策开始」就结束了。缺的有：第一天和头几天该在哪几个时刻看什么（07:40 发了哪些单、09:05 是否补单、第二天 07:40 对账、余力按约定基准还是受渡基准）；哪种情况马上 HALT。也没有退出预案：要回到只模拟时，立花里的持仓怎么处理（继续由执行器管，还是卖掉再卸载）；install_launchd_live_u.sh paper 会把立花的任务全卸掉，留下的持仓就没有止损在管；模拟账本停了几周再开会和云端对不上。另外 gate ① 只数「最近连续一致」的天数、不看日期，装了立花任务、模拟账户停了以后，① 会一直显示 OK。
  - 证据：MACOS.md:128-141（步骤 1〜6，没有值守和退出）；grep 回退 / 退出实盘 / 停止实盘：MACOS.md、HANDOFF.md、README.md 都没有；scripts/install_launchd_live_u.sh:93-94（换模式就全部卸载，不管持仓）；qbreak/live_gate.py:60-68 streak()（不看最近一次比较的日期）
  - 修法：MACOS §1.6 加两节。「上线头 5 个交易日」：各时刻看什么、哪种情况 HALT、看哪个页面。「退出实盘」：HALT → 用户决定持仓是卖掉（manual sell）还是继续由执行器管 → 卸载或保留任务 → 模拟账户从云端重新起步。gate ① 加「最近一次比较在 N 个交易日以内」，过期显示 ★。
- **C-08 实盘依赖云端例行任务：云端的文件过期时照样下单，通知只是 info**（重要；补漏，未单独核对；做的人 both；工作量 S）
  - 说明：Mac 上的执行器不自己算判断层（fwd_judgment）、关联搭配 C、TBF，用的是云端例行任务算好、推上来的文件。文件日期和决策日对不上时，这三层自动不生效，按原规则下单。立花模式最多等到 08:30，过了就照常下单。这时通知只在一行里加「★ 判断层没生效」，级别是 info，不算「bad」。云端停摆有几种可能：Routine 被停、订阅暂停、Claude 或 GitHub 故障。一停，实盘就悄悄换成另一套规则，可能连续很多天，而云端模拟盘也停了，没法比较。
  - 证据：run.py:917、936、947（Mac 读云端的 fwd_judgment / combo_c / tbf）；qbreak/fwd_judgment.py:235（日期不对 → 不生效）；qbreak/live_unified.py:1431-1439（只在一行里加 ★）；run.py:3488（bad 不包含这三项 → 通知级别 info）；scripts/liveu.sh:229（立花等到 08:30 就继续）
  - 修法：工程部分（不改规则）：这三层不生效、或云端数据超过 1 个交易日没更新时，通知升为 warn，页面和手机显示「云端已 N 天没更新」，连续 2 天就推送。停摆时是照原规则下单还是只卖不买，由用户决定（属于交易规则，要记进 sim_changes）。
- **C-09 行情只有 Yahoo 一个来源：Yahoo 断了或 yfinance 坏了，整天不下单（包括止损卖出）**（重要；补漏，未单独核对；做的人 both；工作量 M）
  - 说明：实盘的决策和止损只用 Yahoo 的日线。Yahoo 连不上就退回本地缓存，结果行情落后，整天全部挡住，规则卖单也不下。Yahoo 改接口导致 yfinance 不能用的事以前多次发生过，修起来要在 Mac 上 pip install -U yfinance，而 mac_setup.sh 不带 -U，不会自动升级。Mac 上已经有付费的 J-Quants Standard（日线可以在本机用），但只用于展示和研究，没有作为备用数据源。
  - 证据：run.py:3385（yahoo 不通 → provider=csv）；run.py:3417-3425（行情落后 → ux.block，全部不下单）；qbreak/config.py:359-364（允许的域名只有 Yahoo 系）；requirements.txt yfinance>=0.2.40；scripts/mac_setup.sh:42（pip install -r，不带 -U）；run.py:2348（jq-live：只展示 / 研究）
  - 修法：先做最小的：yfinance 取不到时，通知写明原因和修法（「运行 mac_setup 升级 yfinance」，或者由 Claude 执行）；mac_setup 加一个可选的 yfinance 升级开关。再考虑：日本股票和 ETF 的日线缺失时，用本机 J-Quants 补最新一天（只在 Mac 上，不入库），而且只用于持仓的离场判断。数据源不同可能让决策和云端不一样，范围由用户决定。
- **C-10 依赖版本没锁：云端测试用的版本和 Mac 实际跑的可能不同**（重要；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：requirements.txt 只写了下限（pandas>=2.0 等），没有锁定版本的文件。云端现在是 pandas 3.0.6 / numpy 2.4.6 / yfinance 1.7.0，测试全在这套版本上跑。Mac 的 venv 如果是之前建的，pip install -r 不带 -U，还会是旧版本（例如 pandas 2.x）；换 Mac 或重建 venv 又会装到当时最新的版本。pandas 3 改了 copy-on-write 和字符串类型等行为，可能让决策出现细小差异，上线后又没有模拟账户可以比较。日志和账本也不记版本。
  - 证据：requirements.txt（只有 >=，没有锁定文件）；scripts/mac_setup.sh:42、scripts/install_launchd_live_u.sh:45（pip install -r）；只读查询云端：pandas 3.0.6、numpy 2.4.6、yfinance 1.7.0；run.py:3926（doctor 会打印版本，但每天的日志里没有）
  - 修法：加 requirements.lock（pip freeze，云端测试通过的那一套），mac_setup 按它安装；执行器每次运行把 python / pandas / numpy / yfinance 的版本和 git 提交写进日志；gate 的「准备」加一项「Mac 的版本和锁定文件一致」。
- **C-11 没有单次运行的异常熔断（发单笔数 / 金额超过规则可能的上限就挡住）**（重要；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：每天 07:40 都自动用开发分支的最新代码（LU-17），只有单笔上限（权益 ×1.05），没有「这一次运行总共发了多少」的检查。如果代码有 bug，比如每天把持仓卖光再买回、重复下单，或者股数多算 10 倍（会被余力挡一部分），在现物账户里一天的损失是手续费加价差，但会连续几天发生，要等用户看页面才会发现。规则本身有上限：个股最多 4 只，核心 ETF 最多 2 只，每只每天最多一买一卖。按这个上限设熔断，正常运行不可能触发，也就不改规则。
  - 证据：grep max_orders / daily_cap / 当日上限 / turnover：live_unified.py、tachibana.py、manual_orders.py、panel.py 都没有；qbreak/brokers/tachibana.py:528-535（只检查单笔）；var/sim.json unified.max_positions = 4；scripts/liveu.sh:209-224（每天早上 git pull）
  - 修法：UnifiedExecutor 在发单前统计这次运行的规则单：笔数 > (max_positions + 核心 ETF 数) × 2，或者买卖总额 > 权益 ×2.2 → 全部挡住（BLOCKED），发 warn 通知，写明「异常熔断：请看日志」。手动指令另外计。补测试。
- **C-12 没有内部者 / 个人禁止买卖的名单**（重要；补漏，未单独核对；做的人 both；工作量 S；涉及交易规则）
  - 说明：立花官方：在已申报内部者（内部者登録）的个股上，API 不能新规或订正，只能取消。用户本人或家属如果是股票池（日経225）里某家公司的内部者，执行器照规则买它，会被拒单（REJECTED，原因不清楚），法律上也有内幕交易的风险。现在只有卖出时才能设「不买回」，没有「从一开始就不碰」的名单。这份名单会暴露个人信息（工作单位），不能写进公开仓库。
  - 证据：grep insider / インサイダー / 内部者 / blocklist：qbreak/、run.py、*.md 都没有；qbreak/manual_orders.py:6、112-119（block_days 只能跟着卖出设）；官方 Q&A / 参考手册（内部者申告的个股：API 只能取消）
  - 修法：先由用户确认有没有这种情况。有的话：在 ~/.qbreak/home/restricted.json（不入库）放代码，执行器的资格闸门（entry_gate_fn / core_gate_fn）对实盘账本挡买入，页面只显示「个人限制 N 只」，不显示代码。这样实盘会和模拟盘不同、等于改了股票池，要用户同意并记进 sim_changes（不写具体代码）。
- **C-13 临时休市（交易所全天故障、新增的特别休日）要改代码才能恢复**（方便；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：休市日只按规则算，再加写死的 TSE_CLOSED。发生像 2020-10-01 那样的全天停止，或者临时用特别法新增休日（比如大喪の礼），日历会把那天当成交易日。下一个交易日早上，「应有的 K 线」那天没有，执行器就挡住全部下单，规则卖单也一起停。当天早上已经发出的单，交易所不开就全部作废或顺延。现在只能等 Claude 改 calendar_jp.py 并推送；季度体检只对照到 2027-12。
  - 证据：qbreak/calendar_jp.py:57（TSE_CLOSED 写死）；qbreak/trader.py:80-89（expected_last_bar 按日历算）；run.py:3418-3421（行情只到 X（应有 Y）→ 挡住）
  - 修法：加一个本机的覆盖文件 ~/.qbreak/home/extra_closed.json（用户在对话里确认后由 Claude 写），日历读它；或者日経平均和全部股票都没有那一天的 K 线、且 J-Quants 的交易日历也不认那天时，自动当作休市并通知。
- **C-14 单元未满株（拆股 / 合并后多出的零股）卖不掉的情况没处理，模拟交易所也查不出来**（方便；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：「必须是一手的整数倍」只检查买单。拆股（例如 1:1.5）或合并之后，持仓可能变成 150 股这类数。规则卖出时会照 150 股发普通单，立花可能拒绝；单元未满的部分要走端株交易，手续费 0.55%，而且 11:00〜11:40、15:00〜16:30 不受理，API 能不能下端株单也不清楚。被拒之后卖单天天重发、天天被拒。模拟交易所不检查卖单股数，演练发现不了。和 LU-22 相关，这里补的是卖出这一侧。
  - 证据：qbreak/tradable.py:118（只检查买单）；qbreak/brokers/tachibana.py:714-716（sell 不检查一手的整数倍）；qbreak/brokers/tachibana_sim.py:159-164（只有マスタ，卖单不检查一手）；官方手续费页（単元未満株 0.55%）、服务时间页（端株不受理的时段）
  - 修法：卖单把股数拆成「整数手」和「零股」：整数手照常下，零股记成待处理并通知用户（在网页上卖，或者确认 API 有端株下单之后再做）；模拟交易所加卖单的一手检查；在デモ上确认 API 能不能下单元未满的单。
- **C-15 立花的错误码没有对照表：拒单、登录失败只显示原文**（方便；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：_check 只把 p_errno / sResultCode 和原文拼起来显示。登录失败的提示只列了 4 个原因，没包括官方写明的这些：p_errno=8（Mac 时钟比服务器慢 30 秒以上）、10005（用了 IPv6，或者登记了固定 IP 后 IP 变了）、パスキー被解除、API 因过负荷被停用、旧版本已停用。发单被拒的常见原因（余力不足、值幅之外、差金決済限制、内部者、NISA 11041〜11045 / 11107）也都看不懂。适配器没有强制用 IPv4。
  - 证据：qbreak/brokers/tachibana.py:369-376（只拼原文）；qbreak/brokers/tachibana.py:386-389（登录失败只列 4 个原因）；grep 10005 / AF_INET / getaddrinfo：tachibana.py 里都没有；官方 e_api_v4r9_overview.pdf、REQUEST I/F 仕様（10005 只能用 IPv4、p_errno=8 时刻差）
  - 修法：spec 里加 {错误码: 中文原因 + 要做什么} 的表，_check 和日志、通知都附上；登录失败的提示补上时钟、IP、パスキー、停用、版本几项；第一次 probe --demo 时记下实际出现的错误码，补充这张表；HttpTransport 加一个可选项，强制走 IPv4。
- **C-16 开户与 12 月起立花一侧的变化要提前安排（用户来做）**（重要；补漏，未单独核对；做的人 user_action；工作量 S）
  - 说明：① 开户要邮寄纸面材料，ID 用簡易書留寄来，没有 eKYC；2026-05-26 起官方说手续比平时慢，没给天数。想在 2026-12-24 模拟期结束后接着上实盘，开户就是关键路径。② 新开户现物手续费免费 60 个营业日，从开户完成的下一个营业日开始算，不等开始交易；デモ、probe、入金这些准备会吃掉一部分免费期。③ 2026-12-12（手机网站）/ 12-18（标准 Web）起，交易和出金必须用パスキー登录；而在网页上撤单是 HALT 之外唯一的人工撤单办法，所以パスキー设备丢了，就既撤不了单、也出不了金。官方的设备列表里没有 Mac，MACOS 也只写了一台 iPhone，没有备用设备。④ 入金只能银行汇款，平日 9:00〜15:00 确认到账才当天反映。
  - 证据：HANDOFF.md:14、24（模拟期到 2026-12-24；还没开户）；MACOS.md:325（パスキー只提到一台 iPhone）；官方 https://www.e-shiten.jp/important_info/20260708.html（12-12 / 12-18 パスキー强制）、/important_info/180713.html（免费 60 营业日）、/important_info/20260526.html（开户手续变慢）、/TorihikiRule/rule/payment_1.html（入金）
  - 修法：由用户决定什么时候申请开户（参考：免费期和上线日期尽量重叠）；开户后马上注册パスキー，如果立花允许，再登记一台备用设备；在 HANDOFF 的待办写下这几个日期；Claude 把 MACOS §2 补成按日期排列的清单。
- **C-17 文档与官方现状不一致（2026-10-09 检索，仅对本次检索时点有效）**（方便；补漏，未单独核对；做的人 claude_code；工作量 S）
  - 说明：① CLAUDE.md、面板、manual_orders 都写「要撤在立花网站 / App 上撤」：官方没有原生 App，只有手机专用网站（kabuka.e-shiten.jp/mfds_smp.php）和 BRiSK Next，而且 12-12 起要用パスキー登录。提示里应该给出具体网址和路径。② MACOS.md:325 写「标准 Web 首次登录（电话认证一次）」：官方说电话认证随 v4r8 废止（2026-06-27）停用，标准 Web 首次登录还要不要电话认证没有确认。③ MACOS.md:332 写「每次登录会收到ログインメール」：官方的登录邮件通知只列了标准 Web 和手机网站，API 登录会不会发邮件没写，要在第一次 probe 时实测。④ HANDOFF〔72〕N2 只列了「1545 / 1482 能不能在 NISA 买」这一项待确认：官方规定 NISA 买单只能「指値・無条件・当日中」，所以执行器现在的寄付指値（sCondition=2）不能用于 NISA，nisa_tax_study 按开盘价成交的假设也要重新看。资产运用业协会 2026-10-08 版的名单里，两只都在成長投資枠的对象内，但 e支店有没有逐只受理没有确认。
  - 证据：qbreak/manual_orders.py:549；qbreak/panel.py:598、1555；CLAUDE.md（「立花网站 / App 上撤」）；MACOS.md:325、332；HANDOFF.md:906〔72〕；官方 QA/answer11.html、QA/answer12.html、api/20260513.html；https://www.imaj.or.jp/find/nisa_growth_productslist/
  - 修法：只改文档和提示文字：①写手机网站的 URL 和撤单的路径；②③标「待开户后确认」；④在〔72〕的选项里补上「NISA 买单只能当日・無条件・指値 → 成交方式不同，N2 的效果要重新估算（是否采用属于规则，由用户决定）」。

#### 核对时补出的（立花 API 适配器（qbreak/brokers/tach…）
- M1（important）只读调用的网络 / HTTP / JSON 错误没有转成 BrokerError，出错通知会漏到手机：_send 经 utils.retry 重试后，抛出的是原生的 URLError / HTTPError / TimeoutError / JSONDecodeError（qbreak/brokers/tachibana.py:363-367、292-294）。positions()、cash()、login() 都直接把它们抛出来（496、513、384）。check_broker（qbreak/live_unified.py:1097、1119）和 _place_deferred（461、464）也不包一层。run.py:3435 只接 (ExecutorError, BrokerError)，所以「立花 API 出错」那条路径（写页面提示 + notify.send 的 webhook / 邮件）整个被跳过。只剩 liveu.sh:262-267 的 mac_alert，它只弹 Mac 本机通知。结果：立花维护、断网、旧版本停用导致 404 时，用户不在 Mac 旁边就收不到推送，那天不下单、也不卖。修法：适配器在 _send 边界把非业务异常统一包成 BrokerError（保留类型名），或者 run.py 加一层兜底同样走通知；补对应测试（目前 tests/test_tachibana.py 只有 fail_next=clm_new_order 一种）。
- M2（important）「肯定没发出去」的单被记成状态不明：_place 在发单前登录失败时，日志写的是「登录失败，未发单」，返回的却是 status=ERROR（qbreak/brokers/tachibana.py:632-637）；执行器把 ERROR 算作 UNKNOWN（qbreak/live_unified.py:55），下一次运行整体停下，要人工 --resolve 填 0。发单调用里 DNS 解析失败、连接被拒、TLS 握手失败这些请求根本没发出去的错误，也一样记成 ERROR（667-670）。应该分成 BLOCKED（可以重试）和 ERROR（真的不知道）两种，能少很多 TA-04 那种人工处理。
- M3（convenience）受理应答里没有注文番号时，仍按 SENT 记账：tachibana.py:672-675 不检查 sOrderNumber / sEigyouDay 是否为空；执行器 _collect_fills 会跳过没有 broker_id 的单（qbreak/live_unified.py:988 的 `and o.broker_id`），已经成交的也当成 0 股（UNFILLED），要到第二天的持仓核对不一致才停下。デモ order-test 只对当日指値买检查了 broker_id（run.py:3788），寄付单（676-678）没检查。应答缺这两个字段时，应该直接记 ERROR 并报警。
- M4（important，开户后第一笔交易要核对）持仓是按约定基准还是受渡基准，没有列入验证项：MACOS.md:139 只列了「开盘前买付可能額」デモ验证不了。CLMGenbutuKabuList 的残株数如果按受渡基准（T+2），买入 / 卖出后第二天 07:40 的 check_broker（qbreak/live_unified.py:1097-1118）会因为股数对不上而停下，而且会连停两天。デモ每天重置，验证不了。应把它写进上线后头几天的核对清单（第一笔成交的第二天早上，看 status 里的持仓和 r_pos_qty / r_pos_sellable），必要时让 positions 按约定基准计算。

#### 核对时补出的（实盘执行器（qbreak/live_unified.py、q…）
- 【before_live】08:35 自动重试会绕过持仓核对。07:40 因「持仓与券商不一致」全部 BLOCKED 时，morning_done 因为有 BLOCKED 单返回 False（live_unified.py:1698-1706），08:35 重试照常运行。可这时没有新 K 线，走的是 morning([]) → place(k)（live_unified.py:1210-1219），不调用 check_broker（它只在 run_bar 里调用，live_unified.py:1184）；新进程的 self.blocked 是 None，place() 只看 self.blocked 和 _gate（live_unified.py:379）。结果：被挡的规则单 55 分钟后照样发出。HALT 和行情落后每次都会重查（run.py:3417-3425），唯独持仓不一致不会。修复：同一决策补单前也做一次只读的持仓核对，或者把当天的 block 原因写进账本，重试时沿用。
- 【important】适配器层被挡或被拒的单不算「没下单」。单笔上限、未 ARM、第二暗証番号缺失、銘柄マスタ取不到、立花拒绝（例如余力不足）这类 BLOCKED / REJECTED 只计进 stats，不写进 ux.blocked（live_unified.py:365-367）。于是 summary 的 blocked 是 None（1235），通知短讯里没有「★ 没下单」（1421-1422），通知级别是 info（run.py:3485-3490），返回码 0（run.py:3507）。LU-01 那种开盘后整单被挡，用户收到的也是普通通知。
- 【important】07:40 和 08:35 两次都没在 08:55 前完成时（例如断网），当天的止损和规则卖单整天不下：_gate 在 08:55 后把单挡成 BLOCKED（live_unified.py:303-304）；09:05 的 open_phase 只处理 DEFERRED 买单（live_unified.py:519-541）；盘中路径 now_phase 只处理手动指令。没有「早上错过 → 开盘后挂当日限价卖单」的兜底，止损要晚一天（MACOS §8：都错过 → 那天没下单）。
- 【convenience】上线后登录自启动仍然只打开 page_paper.html（qbreak/mac_login.py:58-60），不打开 page_tachibana.html；模拟账户停了以后，这个页面就一直停在旧数据上。

#### 核对时补出的（Mac 上的运维：liveu.sh / mac_setup.…）
- 【important】07:40 自动 git pull 后，最新提交直接用于真钱执行器：Mac 上不跑冒烟测试，日志 / 账本 / 页面不记 commit 和配置的版本，sync_inputs 每天覆盖 sim.json 等配置也不提示有变化，出问题没有回滚到某个版本的办法（scripts/liveu.sh:44-51,213；grep commit|git rev-parse|HEAD|pytest 于 liveu.sh / live_unified.py / desktop_page.py / mac_setup.sh：没有）。建议：每次运行把 git rev-parse HEAD 和配置的哈希写进日志；sim.json 与昨天不同就在页面 / 通知里标出来；可选只跟某个 tag（不涉及交易规则）
- 【important】现行 live-u 没有券商侧逆指値兜底（只有旧守护进程有 --protective-stop：run.py:3188,3192,4026；live_unified.py 里没有 place_protective_stop 的调用），离场全靠 Mac 每天早上运行。MACOS.md §8（:461-467）「逆指値是永远在岗的保险 / 不要把止损只交给进程」对现行方案不成立，会让人以为有兜底。文档要先改正；要不要加券商侧止损属于交易规则（changes_trading_rules=true），需用户决定并另做研究
- 【convenience】本番 probe（liveu.sh probe）不拿运行锁，也不避开 07:30〜09:25：立花「再次登录会让旧的虚拟 URL 失效」（tachibana.py:14），在执行器运行中跑 probe 会切断执行器的会话；虽然每次调用会自动重登一次（tachibana.py:424-437），仍建议这个时段的 probe 先等运行锁或直接拒绝（run.py:3844-3856 没有 RunLock）
- 【convenience】立花模式的 mac_setup 看到立花任务已装就不重装 plist（mac_setup.sh:36-42），之后 install_launchd_live_u.sh 里 plist 层面的改动（环境变量、PATH、时间）不会自动生效，推送通道这类改动要另外处理

#### 核对时补出的（用户侧便利性：操作面板（panel.py / panel_p…）
- 【建议 before_live】今天早上的运行没完成时（07:40 ExecutorError / 立花登录失败 / Mac 睡过了 07:40 和 08:35），面板照样写「现在点买卖 → 马上（盘中）下单」，提交后也回「已写：卖出 X 全部 → 马上（盘中）卖出」。但 now_due 因为 last_date < 前一交易日直接返回 False，Trigger 也不留任何记录就跳过，所以这条指令整天停在「等下单」，没有任何说明，要到下一次早上成功运行时才变成寄付单。用户以为已经卖了，其实没卖。证据：panel.py:1352（when = MO.when_text(now)，只看时间）、manual_orders.py:567-570、manual_orders.py:599-600、panel.py:1704-1709（not now_due → continue，不打日志）、panel.py:1524-1528（只显示「等下单」）、submit 的提示 panel.py:1640-1650 只对 HALT 加了说明。修法（只做展示）：面板和 submit 用 morning_done 判断，没完成时写「今天早上的运行没完成：这条要等执行器恢复后才下」并标红。
- 【convenience】状态不明的单只能在 Mac 上用 run.py live-u --resolve <cid> --filled --px 登记；面板和手机上没有「哪些单状态不明、cid 是什么、立花注文番号、下单时间、要去立花的哪里核对」的列表。证据：grep 'resolve|RESOLVED' qbreak/panel.py qbreak/panel_phone.py 没有相关代码；cid 只出现在 ExecutorError 的消息里（live_unified.py:596-599,1173-1177）。按 CLAUDE.md，--resolve 要用户在对话里明确说才做，所以面板只需列出信息，不要做一键登记。
- 【convenience】Mac 账本页和桌面链接对 tachibana_demo / tachibana_dryrun 也用「qbreak 立花实盘」的标题和文件名（desktop_page.py:80,283-285），デモ / dry-run 的页面会被看成真钱的实盘页面。

#### 核对时补出的（账户类型 / 税 / NISA / 费用（立花实盘）…）
- MACOS.md:141 上线第 6 步（以及 MACOS.md:79）还写「股票池 + 1655」，但核心 ETF 现在是 1545 + 1482（var/sim.json idle_cash.mode=Q1B；qbreak/idle_cash.py:65）。这是唯一提醒用户「别手动买卖执行器管的票」的地方，写错了票。用户如果在立花手动买卖 1545 / 1482（或放进 NISA），check_broker（qbreak/live_unified.py:1103-1117）每天都会挡住。要改文档（S），important。
- 第一个代理的现状摘要有一处前提错误：实盘执行器在除息日不记分红（run.py:3429 credit_dividends=paper；qbreak/unified.py:947、974 div_net=0，只下调止损 / 峰值），分红等实际入账时经现金同步进来。T3 / T6 里关于分红的推理都要据此更正。相关的小缺口：实盘页面的日收益（qbreak/desktop_page.py:104）在除息日因价格下跌显示亏损，几个月后分红到账又显示为一天的收益，没有标注，属于 convenience。
- 入出金的匹配容差只有 ¥5,000 或金额的 3%（qbreak/live_unified.py:1598）。入金到账的同一天如果有较大的代扣税或亏损退税（還付）混在现金差里，登记过的 flow 可能对不上，就会提示「金额写错？还没到账？」。和 T3 同一个修法（先扣掉预计的税 / 退税再匹配），convenience。

只有代码与官方公开信息的汇总，没有账户信息、密钥或个人信息。非投资建议。
