最後修改日期時間：2026/10/25 09:28（台灣時間）
# Family 十四項選單與完整程式鏈

版本：v1.1.0｜2026-10-24｜Joseph v1.13

最新決定：開場介紹後請輸入密碼；完成每件工作完整顯示十四項；07直接連https://happihelp.com/；報告以台灣日期時間另存並保留歷次，12查上次、13產生最新。

|編號|功能|操作鍵|規則／入口|
|---|---|---|---|
|01|第一次建倉|`first_allocation`|[01_第一次建倉.md](menu/01_第一次建倉.md)|
|02|查看我的資料與持倉|`read_portfolio`|依Sources同版路由與正式handler|
|03|檢視與調整目標配置|`adjust_target`|[03_目標配置調整.md](menu/03_目標配置調整.md)|
|04|評估現在各標的物投入速度|`deployment_pace`|[04_買賣與持倉調整.md](menu/04_買賣與持倉調整.md)|
|05|尋找新標的物|`research_candidates`|[04_尋找新標的物.md](menu/04_尋找新標的物.md)|
|06|安排新增投資資金|`new_funding`|[05_新增資金安排.md](menu/05_新增資金安排.md)|
|07|查看目前總體經濟情況|`macro_link`|[07_總經網站.md](menu/07_總經網站.md)|
|08|查看今日重大財經新聞|`market_news`|依Sources同版路由與正式handler|
|09|查看我的投資標的相關新聞|`holding_news`|依Sources同版路由與正式handler|
|10|更新生活狀況與投資需求|`update_profile`|依Sources同版路由與正式handler|
|11|記錄交易與資金變動|`record_event`|依Sources同版路由與正式handler|
|12|查看上次我的配置報告|`previous_report`|[12_查看配置報告.md](menu/12_查看配置報告.md)|
|13|產生我的最新配置報告|`generate_report`|[11_產生配置報告.md](menu/11_產生配置報告.md)|
|14|帳號：登出／修改密碼|`account`|[14_帳號管理.md](menu/14_帳號管理.md)|

最新路由見[menu/README.md](menu/README.md)。原GitHub檔名維持穩定；Joseph專案兩份指示保存在正式Drive原ID。

## 3. A｜目標配置鏈（Loop 1）

| 順序 | 程式／資料 | 工作 |
|---|---|---|
| 1 | 目前配置、建議配置、V70框架、調整需求 | 準備完整輸入；初始建議配置來源仍需補成正式程式。 |
| 2 | mentor_adjustment_loop.py → work6/adjustment_loop.py → run_mentor_adjustment_loop() | 核對需求、處理偏好及指定保留部位、分配剩餘配置，判斷是否返回V70。 |
| 3 | 配置決策引擎.py → work5/core_engine.py → run_configuration_engine() | 評估傳入建議配置；具備正式確認證據時，也評估正式目標。 |
| 4 | work2/benchmark_reader.py | 讀取基準、來源綁定與資料品質。 |
| 5 | work3/engine.py → evaluate_performance_risk() | 評估績效與風險。 |
| 6 | work4/engine.py → evaluate_lookthrough_exposure() | 評估穿透曝險。 |
| 7 | 調整流程輸出 | 建議配置、正式目標狀態、差異及歷史；雷達資料由上游供應，再整理及驗證。 |

第4～6是引擎內部相依，不是家人逐步回答的問卷。
run_configuration_engine主要評估輸入配置，不能描述為已能從訪談自動產生全部標的與比例。
run_mentor_adjustment_loop需要KNOWN Current及Proposed；缺少時回報缺項。
PROPOSAL_READY與FINAL_TARGET_CONFIRMED分開；正式目標需實際配置內容的確認證據，不退化成「要不要繼續」。
資產類別框架、資金期限、提領需求、人生階段或風險能力重大改變，按RETURN_TO_V70路由；Loop 2不反向改長期目標。

## 4. B｜當下部署鏈（Loop 2）

| 順序 | 程式 | 工作 |
|---|---|---|
| 1 | family_runner.py → FamilyRunner.analyze() | 接收request、native_bundle、context_provider與同輪資料。 |
| 2 | family_boundary.py | 身分及輸入邊界核對。 |
| 3 | 來源接入模組（下表） | 核對目標、持倉、資金、總經、股票、債券、技術資料及日期來源。 |
| 4 | c7_engine.py → work7.asset_framework → run_asset_framework_integration() | 資產框架整合。 |
| 5 | native_pipeline.py → run_native_pipeline() | 組織股票、債券與後續整合。 |
| 6A | stock_engine.py → C8C9 Work4 → livingwater_v82_runtime | 建立輸入、核對資金、核心規則、部署模式、部位缺口與買進計畫。 |
| 6B | bond_engine.py → v75_runtime → C8C9 Work5 | 債券輸入驗證、條件評估、部署決策、合計額度及未部署資金、正式輸出。 |
| 7 | funding_bridge.py＋funding_guard.py＋C8C9 Work6 | 帳戶資金隔離、合計額度與實際部署金額核對。 |
| 8 | sgov_bridge.py＋C8C9 Work7 | SGOV角色、實體金額及重複計算核對。 |
| 9 | permission_bridge.py＋C8C9 Work8 | 指定保留部位；保留原風險訊號與最終客戶動作的區別。 |
| 10 | C8C9 Work9 → build_unified_deployment() | 統一股票、債券、資金、SGOV、保留部位結果。 |
| 11 | mentor_bridge.py → explain_native()＋reason_catalog.json | 正式動作及理由解釋。未知代碼保留待解釋；不補造理由。 |
| 12 | GPT呈現 | 調整語氣、排版及用詞，保留數字、方向、條件及證據。 |

### 來源接入及共用相依

- 目標／持倉：target_source_bridge.py、bond_target_bridge.py、position_source_bridge.py。
- 資金／總經：funding_bridge.py、macro_source_bridge.py、v70_source_bridge.py。
- 股票／債券：stock_source_bridge.py、bond_source_bridge.py。
- 技術資料：family_technical_bridge.py；更深的技術產製／資料抓取鏈仍需追查，不以檔名存在宣稱已驗收。
- 分析重試與重用：recovery_bridge.py。
- 載入與相依核對：runtime_loader.py、verify_dependencies.py。
- 部位單位投影：有C7計算結果時使用target_units.py。
- 戰術預算限制：tactical_budget.py。

### 已確認股票函式鏈

C8C9 Work4.build_v82_runtime_input
→ V82.validate_and_bind_funding
→ tactical_cap
→ evaluate_core_rule_state
→ select_deployment_mode
→ resolve_deployment_stage
→ calculate_position_gap
→ build_buy_execution_plan
→ assemble_stock_output
→ 後續資金／SGOV／持倉保護／統一結果。

此鏈明確包含買進計畫；賣出與換股完整數量、時序、資金釋放及成交後再投入鏈，尚未核實完成。不得以這條買進鏈替代全部買賣功能。

### 已確認債券函式鏈

C8C9 Work5.build_v75_runtime_input
→ validate_v75_run_input
→ v75_runtime.predicates評估及work3狀態組裝
→ evaluate_step10
→ build_decision
→ proportional_scale_decisions
→ calculate_v75_undeployed_to_sgov
→ assemble_final_snapshot
→ evaluate_runtime_ready
→ C8C9 Work5.consume_v75_runtime_ready
→ 後續統一結果。
具體分支依資料及資格條件執行，非每檔都無條件走完全鏈。

V70是這條鏈的上游結果來源。v70_source_bridge驗證與綁定已有V70結果，不能說FamilyRunner每次自動重算V70。
SGOV必須區分防守保留與等待部署用途，同一金額不重複計算，尊重本人最新限制。
mentor_bridge已明確拒絕llm_suggested_changes，錯誤代碼MODEL_FINANCIAL_MUTATION_REJECTED；自然語言層仍需核對與正式結果一致。

## 5. C｜資料保存鏈

變更需求
→ Coordinator.update(resource, principal, request_id, epoch, operation, payload)
→ 權限、操作及輸入核對
→ 固定鎖／取得與恢復目前資料
→ epoch版本核對
→ transaction()在SQLite交易內呼叫已註冊handler
→ 重複請求辨識
→ _commit()提交、備份、保存與讀回驗證
→ 回報結果、版本與備份資訊。

個人資料、成交、配息、入出金及轉倉需要各自handler，共用寫入器不自行推定業務內容。
簡易JosephLogin與Coordinator需要的驗證身分之間尚有接線；本文件不改登入政策、不新增金鑰要求。
已計算、待保存、已保存分開回報；分析建議不更新成實際持倉。

## 6. D｜報告鏈

| 已核對程式 | 實際用途 |
|---|---|
| current_report_bridge.py → bind_current_report() | 綁定有日期的報告資料、目標及選用W5結果。 |
| report_receiver.py → assemble()／receive_action() | 整理報告資料並接收分析動作。 |
| report_receiver.py → render_review() | 診斷用HTML，不等於完整家人版正式報告。 |
| performance_reference.py | 既有歷史數值的加權參考，不代替正式回測或攻防分數來源。 |

W6/runtime/README.md明示HTML／工作簿製作腳本及輸入保存在Drive完整包；正式產製原件已從W6完整包定位；參數化接線與真實產製驗收由總PM續作。
資料整理程式不是完整renderer；正式報告須使用同一人、同輪分析、正確模板及資料日期。報告重做前依檔案管理讀正式母模。

## 7. 正式路徑與來源

GitHub儲存庫：https://github.com/a23882005/LivingWaterAI

- Mentor：系統工程/MENTOR主程式/Mentor.md
- Family讀取、分析及說明：系統工程/Family/W5/
- C配置、偏好調整及資產框架：系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/
- C8C9整合模組：上述正式Runtime/C8C9_RUNTIME/
- 報告中間程式：系統工程/Family/W6/runtime/
- 寫入協調：系統工程/Family/W7/資料存取管理.py
- 帳號與本人DB仍依既有私有資源設定定位；本紀錄不放密碼、token、私有DB內容或帳戶數字。

本文件正式保存位置：
- Google Drive根目錄：Family_十四項選單與完整程式鏈.md
- GitHub：系統工程/Family/Family_十四項選單與完整程式鏈.md

## 8. 本輪成果與後續接線

本輪已完成十四項程式路由、開場與登入接續、工作完成後完整選單、總經直接連結、報告日期時間命名／保留／上次查閱模組及其本機合成驗證。詳W7/Joseph_v1_13_SYNC.md。
後續由總PM本人沿正式B07及B16完成：私人身分與writer整合、正式renderer參數化、私有報告folder與同一writer lock設定、舊成功報告索引核實、真人專案端到端驗收。原初始配置正式生成、研究及新聞handler、賣出換股等既有工序沿Checkpoint接續。
W7 B01～B06 PASS、B07 IN_PROGRESS、6/23；Production HOLD、交易NONE、W4取消、RM17凍結。


<!-- USER_PROGRAM_ATLAS_LOCATION_REGISTRATION_20261031 -->
## 2026/10/31｜使用者要求之文件位置登錄（非中PM驗收裁定）

依使用者要求新增[全系統程式盤點與 V82 流程對照索引](https://github.com/a23882005/LivingWaterAI/blob/family/w8-complete-04-joseph-mou/%E7%B3%BB%E7%B5%B1%E5%B7%A5%E7%A8%8B/%E5%85%A8%E7%B3%BB%E7%B5%B1%E7%A8%8B%E5%BC%8F%E7%9B%A4%E9%BB%9E%E8%88%87V82%E6%B5%81%E7%A8%8B%E5%B0%8D%E7%85%A7/README.md)，保存於 `系統工程/全系統程式盤點與V82流程對照/`；閱讀版、頁次導航及完整程式位置見該入口。

程式盤點固定於 PR59 `5163116bcdedaabbc3cf09ae091ca96968a26fdd`：531 個原始碼檔（Python 525、PHP 4、CJS 2；含測試、工具及5個備份），不是531個獨立功能。main `591cf6256dc8942d68cf4441529b4b08391624b5` 對照為363個，兩分支不相加。11個HTML另列、不混入531。

此登錄僅為文件位置／來源對照交接，不代表中PM獨立驗收、PR合併、正式部署或金融Gate通過；原Owner、權限、規則、Checkpoint與驗收裁定完整保留，Production HOLD／交易NONE不變。舊文件中的數量、版本及交接包校驗值仍是各自歷史截點，不以本次盤點覆蓋。
