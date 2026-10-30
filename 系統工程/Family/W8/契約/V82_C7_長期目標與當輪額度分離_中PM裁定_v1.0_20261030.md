# Family中PM正式裁定：C7長期目標與當輪額度分離 v1.0

日期：2026-10-30（台灣時間）
裁定人：Family中PM／全專案總PM，依Owner已授權之專案治理與工程協調權。
狀態：APPROVED_FOR_IMPLEMENTATION；待Codex施工及中PM獨立驗收，未放行Production／交易。
適用工程：PR59，施工起點 d66774c7c124e6bb4524bedd4e49b16081a15c40。
正式scope/profile：FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1。
本文件是版本化整合契約裁定，不修改V70/V82投資門檻、九階比例、倍率、既有客戶核准權重或49/13欄。

## 1. 裁定與依據

採用提案B，限上述新scope。正式V82.md v1.21.0工程63-A/B/C、工程37-F及已核准三層量化正式v1.0 CMR9.1/CMR-ALLOC-01已明定：
- Project保存核准長期目標；V70提供同輪總股票戰術Ceiling。
- 先扣既有曝險、有效Buy reservation及其他承諾，再與已授權實際可新增資金取MIN。
- 已超額只使本輪新增容量0並保留overage，沒有自動強制賣出。
2026-10-30已Fresh Read Drive正式V82.md，仍為v1.21.0；原核准v1.0 DOCX與工程profile hash一致。

現contract69 §4與C-W7-v1.2.0是「同一用途的當輪Final Target須等於V70 bucket，並做protected/residual整合」；Family來源卻將EXISTING_LONG_TERM_APPROVAL輸入該當輪路徑。新scope須分開兩個用途，而非假確認或刪比較。
原v1.2.0當輪scope保持原行為與相容測試；沒有新scope、正式schema/profile/來源資格者，不能自動切換新路徑。

## 2. 兩個視圖、分母與來源

A. approved_long_term_target：沿本人正式已確認版本、權重、確認者/時間/原件hash。Project Target Position金額只用本人已核准投資池及原正式投影；禁止以目前NAV、手邊現金、新增資金或V70比例替換核准金額分母。舊文件已知金額與目前有效核准分母分列。缺分母停在相依金額UNKNOWN。

B. same_run_v70_total_ceiling：只消費原V70正式輸出的總額度及其明確Accounting Base/Currency、snapshot/run/as-of、source與原Work3提供的account/domain預算。只有比例而沒有合法base/amount則不得推算。V70的S0/B0/C/T公式保持原Owner；單檔cap不得壓整個總股票池，新增現金授權不得冒充總配置cap。

兩視圖均綁本人client/portfolio、有效版本、owner/account/domain、共同run、cutoff、FX、來源hash；原approval可以早於run，但其有效性與原確認證據須驗證。READ_EXISTING_APPROVAL只讀既有長期核准，不創造新的當輪CONFIRM或簽名事件。

Drift沿Work6原計算與完整Current/Final universe：權重Drift=Final-Current，Current權重的NAV分母與Project Target金額分母分開標示；不得混用兩個base做金額差。所有金額如須換算，沿原合法FX與Work64口徑。報告仍只消費C正式結果，不另算一套。

## 3. 曝險扣抵與共享資金：直接沿正式工程63

ceiling = MIN(原V70正規化總額度, 實際適用且同base的既有client/global股票總池caps)
occupied = confirmed_stock_exposure + effective_active_buy_reservations + other_existing_committed_stock_exposure - only_confirmed_released_or_reduced_exposure
overage = MAX(occupied - ceiling, 0)
incremental_room = MAX(ceiling - occupied, 0)
incremental_capacity = MIN(incremental_room, available_authorized_incremental_funding)

不適用cap明列NONE/NOT_APPLICABLE；實際Required cap UNKNOWN按依賴處理。已知occupied>=ceiling時新增0，原未知cash等欄保留。
已成交部位、Open/Partial/CancelPending/ReplacePending承諾、已確認釋放各有唯一事件/intent/owner識別，明列其計入層。禁止同筆成交與reservation在同一occupancy重算，禁止把未成交Sell或建議釋放當已釋放。
總池occupancy與cash是兩種不同限制：各自核對同一經濟事件的來源，net available-to-trade已扣reserved則不再從cash重扣；不是把兩種限制金額相加扣兩次。
上游若已提供net incremental room，必須具原producer/口徑/已扣事件的可驗證receipt；消費者驗回原工程63關係後沿用，不再當gross重扣。沒有該證明則回原gross資料鏈，不猜其為net。
每account/domain使用自己可用已結算且已授權資金；全戶股票總額度若跨account，使用原跨資產allocator先守本bucket cash、再守共享stock pool；不得把全戶cap各複製一次給每檔/每帳戶。
日切片依原固定G0/B0及spent/committed、CMR-ALLOC-01順序分配，合計新/增加Buy不超capacity；再套各檔Gap/明確cap/費用/lot與37-F原MIN。SGOV可動用規劃池、券商已結算現金分列。

## 4. protected、Target與舊契約兼容

保留既有已核准配置及原protected來源/Preference Lock、禁止動作、帳戶隔離。protected有效輸出仍HOLD_PROTECTED、effective Final=真正Current、Drift=0；原核准長期快照獨立原樣保留，兩視圖來源及差異明列。
原protected/權限衝突所要求的治理返回仍沿用，不能藉新scope解除保護或改客戶目標。若只是工程63所指既有曝險超總Ceiling，保留overage、新Buy=0，不強迫重配或賣出。
新scope不將長期權重再按V70 bucket做residual縮放，亦不把未部署額改寫為新長期現金/SGOV權重。原當輪scope仍執行contract69 §4及CONFIRMED_TARGET_WOULD_CHANGE。
任何protected、資產分類、分母或同base資格仍無法判定，輸出原具名缺項/治理返回，不以豁免旗標通過。

## 5. schema、status與Gate

新scope採明確versioned input/profile及schema/manifest，雙視圖/occupancy/來源證據放於獲准nested evidence/sidecar，不增加49/13欄。Codex須在本次PR同步contract69的新scope附錄/相依schema/source lock/adapter/消費者/回歸，不只在某個operator旗標略過舊guard。
既有六項C7 hard checks：protected、drift、radar六軸、funding schema、account isolation、no cross-account funding，全部保留。新增scope/兩視圖/63-B守恆/同輪來源驗證通過後，最多輸出原READY_FOR_PM_GATE。
READY_FOR_PM_GATE仍須中PM獨立Gate，舊pm_gate/a78_a79/work8 release約束保留；本裁定只放行施工，不自動放行C7 runtime/Production/Gate D/E。Required financial包或根事實不齊仍用原狀態/具名issues，不能把partial改OK。

## 6. 最小施工範圍與責任

原V82 Codex沿PR59依序：
1. 把本裁定與最新main治理commit納入原分支，鎖新scope schema與正式呼叫鏈。
2. Work6/Work7來源adapter與C7版本分支分開長期核准及同輪cap；復用原protected/Drift/Radar/資金驗證。
3. Family W5/Work3/Work4/Work9與member_financial_chain接同輪原producer financial_sources.<asset>。填的是原producer pack，不直接貼native結果；核准金額/FX/訂單/資金scope逐一核對。
4. 依既有合格source槽補根事實，按可用原件完成四戶實際金融鏈；不同戶不借DB、bundle、現金或來源身份。VEA/00956等尚缺正式主profile者列具名分類工項，禁止偷套別檔尺。
5. 真實Gap/permission/session/對帳成立後才初始化本人cycle；序列writer+SQLite CAS+寫前重查+備份+原Drive ID+讀回，正向plan以同request/intent/after-cycle digest驗保存。四戶目前的空ledger資源成果保留。
6. 原報告PR60獨立施工，金融原件以正式consumer契約供報告線；共用README/Checkpoint由中PM維護。

工程class/安全/own_history/financial pack來源組裝屬Codex續工；外部確實未取得、方法資格不足、已知資料待接、C7 scope施工狀態分列。中PM負責版本與Owner界線、依賴協調、獨立驗收及Gate。

## 7. 必跑驗收（下列新scope案例尚待Codex施工）

| 案例 | 必要結果 |
|---|---|
| 舊scope桶不等/完全相等 | 原RETURN_TO_V70或原流程保持，其他Gate照驗 |
| 新scope缺任一有效雙視圖/金額base/run/owner/FX | 原具名拒收；不自行走舊長期假CONFIRM |
| 新scope長期目標與V70上限不同 | 原長期權重/金額與Drift保持；用63-B約束新增 |
| Target450000、Projected300000、成熟/未成熟、乘數1 | Gap150000；slice37500/22500，再套cash/fees/lot |
| ceiling100、confirmed110、Buy承諾5、無已確認釋放 | occupied115、overage15、incremental0；無強制賣出 |
| ceiling100、confirmed60、Buy10、其他承諾5、confirmed release0、authorized funding50 | room25、capacity25；同事件不重算 |
| net cash20已扣reserved10、Gap50 | cash限制仍20，不重扣成10 |
| protected超限/禁止動作/權限衝突 | 鎖及原治理處理保留；單純總曝險超限新增0 |
| 多檔/多account競爭、共享stock cap | 同bucket cash與全pool容量各守一次；未知影響共享比例按原規則 |
| 原C7六個hard checks任一失敗 | 保留原返回/Gate；不以新scope覆蓋 |
| 來源時點/跨戶/DB target version mismatch | 明確拒收 |
| 同日重跑、部分成交、取消/替換待確認、確認釋放、Drive跨環境讀回 | G0/B0固定、未確認不釋放、重跑不重複占額 |
| 四戶真實pack/正向或已知0/具名缺項 | 同一最終commit逐戶回交，不把合成金額當本人實跑 |

回交需含新舊scope結果、正式契約→函式→producer→consumer→測試映射、原49/13/schema兼容證據、四戶request/context/result/call_trace、逐檔根依賴、金融pack及Ledger讀回，私人原件放Drive根/TEMP，公開PR只放程式/合成QA/去私人化裁決。
