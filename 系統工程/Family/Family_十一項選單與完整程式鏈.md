# Family 十一項選單與完整程式鏈

最後修改日期：2026/10/24（台灣時間）
文件版本：v1.0.0
文件狀態：正式決策與程式閱讀核對紀錄；工程接線尚未全部完成
核定依據：指揮官於本對話要求保存至 Google Drive 與 GitHub 的完整對照。
責任：Family 中PM接續定位、接線、測試與文件同步；本次僅保存規劃與核對結果，不新增功能驗收或交易授權。

## 1. 最新決定與證據範圍

Mentor 負責訪談、流程與路由；正式程式負責投資計算與判斷；GPT 負責自然、溫暖、清楚的口語表達。
配置比例、金額、標的、價格條件、評分、買賣方向、優先順序及 SGOV 可動用額度，依正式程式輸出。
總經與新聞摘要依已核對來源；涉及投資動作時，轉正式分析流程，GPT 不自行衍生第二套看法。

本次已讀本對話取得的 Mentor v3.21.0 與 Family/W5、C Runtime、Family/W6、Family/W7 程式副本。內容是該副本的閱讀核對，不等同全部最新遠端程式已重跑或十一項已端到端驗收。
既有取用版本曾固定為 05543bd4f62575d2580c6e8f1ed6b96a556959ec；本紀錄不得據此推定其他歷史包全部同一 commit。
「已核對」表示已讀到程式與呼叫關係；「待接／待核對」是工程待辦，不是宣告程式一定不存在。
已核對的 W5 分析程式仍含 ISOLATED_TEST_STAGING、production=HOLD、trade_action=NO_TRADE；Mentor bridge 含 execution_advice_allowed=False。實際使用須保留這些狀態。

重要落差：舊 Mentor 含由 AI／人工 Legacy 流程產生初始長期股債基準及建議配置的規則。依指揮官最新決定，應補為正式程式來源，不能以口語指示當作演算法已實作。本紀錄保存此決定與遷移待辦，尚未改寫 Mentor 母檔或執行引擎。

## 2. 十一項選單與完整流程

| 編號／畫面文字 | 用途 | 從資料到結果的流程 |
|---|---|---|
| 🌱 01｜第一次建倉 | 從首次訪談開始，建立目標配置與首次投入安排。 | Mentor 首次訪談 → 結構化個人條件、投資池、偏好與限制 → 建立目前持倉／現金快照 → 初始股債基準及建議配置產生流程〔待補正式程式〕 → A 目標配置鏈 → B 當下部署鏈 → 報告與保存。 |
| 📋 02｜查看我的資料與持倉 | 查看個人資料、投資目標、持倉與現金。 | 登入核對 → 本人 Joseph.db → family_input.read_snapshot() → 目前持倉及現金整理〔入口待接〕 → 顯示明細及資料日期。讀取歷史快照不等於已計算目前持倉。 |
| 🧭 03｜檢視與調整目標配置 | 檢視理想配置，討論保留、減少或換入哪些標的。 | 既有訪談＋目前配置＋原目標 → Mentor 整理調整需求 → A → 顯示目標及差異 → 保存分析版本。重大人生、資金條件或框架變動按規則返回 V70。 |
| ⚖️ 04｜評估現在如何買賣與調整 | 評估續抱、買賣、換標的及 SGOV 運用。 | 持倉＋正式目標＋各帳戶資金＋上游 V70 結果＋市場資料 → B → 正式動作及理由 → 口語說明。完整賣出／換股計畫仍待確認接線。不限於新增資金。 |
| 💰 05｜安排新增投資資金 | 安排新增資金的配置與投入步驟。 | Mentor 新增資金事件 → 確認金額、帳戶、用途及期限 → 更新投資池 → 必要時 A → B → C 保存。事件入口待接；沿用既有訪談。 |
| 🌐 06｜查看目前總體經濟情況 | 了解目前景氣、市場環境與總經分析。 | HappyHelp 正式總經頁面 → 讀取已發布分析及資料日期 → 整理既有結論、數字與情境 → 口語說明。確切頁面、讀取入口及上游產製程式待核對；不把頁面讀取當成重新計算 V70。 |
| 📰 07｜查看今日重大財經新聞 | 掌握影響整體市場的重要事件。 | 新聞查詢 → 原始來源與事件時間核對 → 去重 → 整理重大消息、來源及日期 → 摘要。是待落實的查詢流程，尚未確認專用程式，不另造已存在的函式名。 |
| 🔎 08｜查看我的投資標的相關新聞 | 查看與持倉標的及產業相關的重要消息。 | 本人 DB → read_snapshot() → 目前持倉清單 → 逐標的新聞查詢 → 核對來源與日期 → 按標的整理。投資動作轉 A／B；持倉到查詢的入口待接。 |
| 🌿 09｜更新生活狀況與投資需求 | 更新生活變化、資金需求與投資偏好。 | 原資料 → Mentor 差異訪談 → 結構化變更 → C 保存 → 判定是否影響資產框架 → 必要時 V70／A／B。只補必要缺項。 |
| 📝 10｜記錄交易與資金變動 | 記錄成交、配息、入出金及轉倉。 | 整理實際事件 → C 內呼叫對應交易 handler → 更新交易、持倉及現金 → 回報保存結果。業務 handler 與寫入接線待完成；建議、掛單、成交分開。 |
| 📑 11｜查看配置分析與報告 | 查看配置比較、分析結果與已完成報告。 | 舊報告：定位本人報告 → 讀取與呈現。新報告：本人快照＋目標＋同輪結果 → D 報告鏈 → 保存與交付。 |

一般問題、研究與截圖直接說，由 Mentor 分流。登出／修改密碼放選單底部，依實際支援狀態處理，不佔十一項。
首次建倉、調整既有配置、當下部署與新增資金是不同情境；01、03、04、05共用引擎，但入口資料與目的不同。

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

W6/runtime/README.md明示HTML／工作簿製作腳本及輸入保存在Drive完整包；正式產製與圖表入口仍須取得該包核對。
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
- Google Drive根目錄：Family_十一項選單與完整程式鏈.md
- GitHub：系統工程/Family/Family_十一項選單與完整程式鏈.md

## 8. 工程待辦與完成判準

1. 定位並程式化初始S0/B0與建議配置來源；先核對現有工程，避免重做。
2. 接妥本人持倉／現金最新狀態整理，以及首次建倉的初始快照。
3. 補齊賣出／換股完整鏈，區分分析、建議、掛單與成交。
4. 查明雷達分數的正式上游計算。
5. 核對HappyHelp總經頁面、資料日期、讀取入口與上游產製鏈。
6. 核對既有新聞搜尋／分類／去重規則及程式，再接重大新聞與持倉新聞兩個入口。
7. 接妥新增資金、個人資料及交易handler與保存流程。
8. 從Drive完整包核對W6正式製圖／HTML／工作簿入口。
9. 依本文件同步專案指示與參考文件，十一項一致；先前v1.10下載文件仍是七項版，待更新。
10. 逐項測試正常、缺資料、工具失敗與重複操作；核對每項輸出與口語呈現一致。

本次保存完成代表決策與核對紀錄已落檔，不增加既有Gate或功能PASS。工程仍由Family中PM循序承接。

## 9. 相依與變更紀錄

2026/10/24 v1.0.0：首次保存指揮官核定的十一項選單、A/B/C/D程式鏈、已核對與待接界線、GPT表達規則與後續工程待辦。
本次只新增紀錄；未修改Mentor、V70、V82、V75、W5/W6/W7執行程式、正式DB、報告模板或既有部署。
專案兩份安裝文件與Mentor舊Legacy流程：列為待同步；本次不宣稱完成系統級改版。
